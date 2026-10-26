"""Embed chunks (e5-small, `passage: ` prefix) and load everything for one document into Postgres + Storage.

Loading is idempotent per document: its rows are deleted (cascade) and re-inserted in one transaction.
Embeddings are cached by chunk-text hash in data/embeddings/ so re-chunking only re-embeds what changed.
"""
import csv
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from functools import cache

import numpy as np
import requests

from backend.config import ROOT, config, env
from backend.db import connect
from backend.ingest.ocr import CROPS_DIR
from backend.net import retry

EMB_DIR = ROOT / "data" / "embeddings"
BUCKET = "crops"
BANKS = {"BBCA", "BBNI", "BBRI", "BBTN", "BMRI"}


@cache
def model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(config()["embedding"]["model"])


def embed_passages(texts: list[str]) -> np.ndarray:
    return model().encode([f"passage: {t}" for t in texts], batch_size=32, normalize_embeddings=True,
                          show_progress_bar=len(texts) > 500)


def embed_chunks(doc_id: str, chunks: list[dict]) -> np.ndarray:
    EMB_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = EMB_DIR / f"{doc_id}.npz"
    keys = [hashlib.sha1(c["text"].encode()).hexdigest() for c in chunks]
    cached = dict(np.load(cache_path)) if cache_path.exists() else {}
    todo = [i for i, k in enumerate(keys) if k not in cached]
    if todo:
        for i, vec in zip(todo, embed_passages([chunks[i]["text"] for i in todo]), strict=True):
            cached[keys[i]] = vec.astype(np.float32)
        np.savez_compressed(cache_path, **{k: cached[k] for k in keys})
    return np.stack([cached[k] for k in keys])


def load_companies() -> None:
    snap = ROOT / config()["universe"]["snapshot_file"]
    with snap.open(encoding="utf-8", newline="") as f, connect() as conn:
        for row in csv.DictReader(f):
            conn.execute(
                """insert into companies (ticker, name, template, lq45_snapshot_date)
                   values (%s, %s, %s, %s)
                   on conflict (ticker) do update set name = excluded.name, template = excluded.template,
                       lq45_snapshot_date = excluded.lq45_snapshot_date""",
                (row["ticker"], row["name"], "bank" if row["ticker"] in BANKS else "general", row["snapshot_date"]),
            )


def _vec(v: np.ndarray) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


def load_document(row: dict, parsed: dict, figures: list[dict], chunks: list[dict], vectors: np.ndarray) -> None:
    doc_id = row["doc_id"]
    langs = {c["lang"] for c in chunks if c["kind"] == "text" and c["lang"] in ("id", "en")}
    paired = sum(1 for c in chunks if c["pair_id"])
    layout = "side_by_side" if paired > len(chunks) / 4 else ("mixed" if len(langs) > 1 else next(iter(langs), None))
    with connect() as conn, conn.transaction():
        conn.execute("delete from documents where doc_id = %s", (doc_id,))
        conn.execute(
            """insert into documents (doc_id, ticker, doc_type, fiscal_year, period, source_url, sha256, pages,
                                      lang_layout, fetched_at)
               values (%s, %s, 'annual_report', %s, %s, %s, %s, %s, %s, %s)""",
            (doc_id, row["ticker"], int(row["year"]), row["period"], row["source_url"], row["sha256"],
             len(parsed["pages"]), layout, row["fetched_at"]),
        )
        with conn.cursor() as cur:
            cur.executemany(
                "insert into pages (doc_id, page_no, kind, char_count, parser) values (%s, %s, %s, %s, %s)",
                [(doc_id, p["page_no"], p["kind"], p["chars"], p.get("parser", "pdfplumber")) for p in parsed["pages"]],
            )
            cur.executemany(
                """insert into figures (figure_id, doc_id, page_no, kind, bbox, storage_path, caption, chart_table_md,
                                        ocr_confidence) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                [(f["figure_id"], doc_id, f["page_no"], f["kind"], [float(v) for v in f["bbox"]], f.get("storage_path"),
                  f["caption"],
                  f["chart_table_md"], f["ocr_confidence"]) for f in figures],
            )
            cur.executemany(
                """insert into chunks (chunk_id, doc_id, ticker, fiscal_year, page_start, page_end, section_path, seq,
                                       kind, lang, pair_id, text, embedding, figure_id, chunker)
                   values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::halfvec, %s, %s)""",
                [(c["chunk_id"], doc_id, c["ticker"], c["fiscal_year"], c["page_start"], c["page_end"],
                  c["section_path"], c["seq"], c["kind"], c["lang"] if c["lang"] in ("id", "en") else None,
                  c["pair_id"], c["text"], _vec(v), c.get("figure_id"), c["chunker"])
                 for c, v in zip(chunks, vectors, strict=True)],
            )


def _storage_headers() -> dict[str, str]:
    key = env("SUPABASE_SERVICE_KEY")
    return {"Authorization": f"Bearer {key}", "apikey": key}


def ensure_bucket() -> None:
    """Public-read bucket: crops are excerpts of public reports (§6); writes need the service key."""
    base = env("SUPABASE_URL").rstrip("/")
    r = retry(lambda: requests.get(f"{base}/storage/v1/bucket/{BUCKET}", headers=_storage_headers(), timeout=30))
    if r.status_code != 200:
        r = requests.post(f"{base}/storage/v1/bucket", headers=_storage_headers(), timeout=30,
                          json={"id": BUCKET, "name": BUCKET, "public": True, "allowed_mime_types": ["image/webp"]})
        r.raise_for_status()


def upload_crops(figures: list[dict]) -> int:
    base, headers = env("SUPABASE_URL").rstrip("/"), _storage_headers()

    def put(f: dict) -> bool:
        path = CROPS_DIR / f["storage_path"]
        r = retry(lambda: requests.post(f"{base}/storage/v1/object/{BUCKET}/{f['storage_path']}",
                                        data=path.read_bytes(), timeout=60,
                                        headers={**headers, "Content-Type": "image/webp", "x-upsert": "true"}))
        return r.ok

    todo = [f for f in figures if f.get("storage_path")]
    with ThreadPoolExecutor(max_workers=8) as pool:
        ok = sum(pool.map(put, todo))
    if ok != len(todo):
        raise RuntimeError(f"uploaded {ok}/{len(todo)} crops")
    return ok


def storage_bytes() -> int:
    """Bytes used in the crops bucket (Supabase's storage.objects metadata), for the free-tier guard."""
    with connect("SUPABASE_DB_URL") as c:
        row = c.execute(
            "select coalesce(sum((metadata->>'size')::bigint), 0) from storage.objects where bucket_id = %s",
            (BUCKET,),
        ).fetchone()
    return int(row[0])


def load_chunks_file(doc_id: str) -> list[dict]:
    with (ROOT / "data" / "chunks" / f"{doc_id}.jsonl").open(encoding="utf-8") as f:
        return [json.loads(line) for line in f]
