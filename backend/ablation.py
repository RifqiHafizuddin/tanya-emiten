"""Chunking ablation (§6.2, MVP 1 acceptance): retrieval method x chunking x k.

Variants of the text chunks: `section` (production, D29), `page` (one stream per page, long pages split) and
`fixed` (400-token windows with a 50-token overlap, ignoring headings and paragraphs). Table and chart chunks are the
production ones in every variant, so only text chunking changes. A variant is loaded into its own schema (`abl`) next
to the production tables and searched with the same retrieval code; the schema is dropped afterwards.

    python -m backend.ablation            # writes eval/reports/ablation_YYYYMMDD.md
"""
import hashlib
import json
import re
import statistics
from contextlib import contextmanager
from datetime import date

import numpy as np

from backend import evaluate, retrieval
from backend.config import ROOT
from backend.db import connect, pooled
from backend.ingest.chunk import Builder, chunk, ntok, paragraphs, running_lines, tokenizer
from backend.ingest.fetch import read_manifest
from backend.ingest.parse_pdf import detect_lang

PARSED = ROOT / "data" / "parsed"
EMB_DIR = ROOT / "data" / "embeddings_ablation"  # never the production cache: embed_chunks rewrites that file
FIXED_SIZE, FIXED_OVERLAP = 400, 50


def fixed_chunks(parsed: dict, ticker: str, year: int) -> list[dict]:
    """The naive baseline: 400-token windows over the report's text in page order, whatever the language, section or
    paragraph (headings kept as plain text). Per-language streams would let one window span dozens of pages."""
    pages = parsed["pages"]
    skip = running_lines(pages)
    sizes = [ln["size"] for p in pages for c in p["columns"] for ln in c["lines"]]
    body = statistics.median(sizes) if sizes else 10.0
    text, starts = "", []  # starts: (char offset, page) of each paragraph
    for p in pages:
        for col in p["columns"]:
            lines = [ln for ln in col["lines"] if ln["text"].strip().lower() not in skip]
            for t, _ in paragraphs(lines, body):
                starts.append((len(text), p["page_no"]))
                text += t + "\n"
    b = Builder(parsed["doc_id"], ticker, year)
    offsets = tokenizer().encode(text, add_special_tokens=False).offsets
    page_at = lambda pos: max(p for s, p in starts if s <= pos)  # noqa: E731
    for i in range(0, max(1, len(offsets) - FIXED_OVERLAP), FIXED_SIZE - FIXED_OVERLAP):
        window = offsets[i : i + FIXED_SIZE]
        if not window:
            break
        a, z = window[0][0], window[-1][1]
        b.emit(text[a:z].strip(), page_at(a), page_at(z - 1), "-", "text", detect_lang(text[a:z]), None, "fixed")
    return b.chunks


def variant_chunks(variant: str, doc_id: str, ticker: str, year: int) -> list[dict]:
    parsed = json.loads((PARSED / f"{doc_id}.json").read_text(encoding="utf-8"))
    if variant == "page":
        out = [c for c in chunk(parsed, ticker, year, strategy="page") if c["kind"] == "text"]
    else:
        out = fixed_chunks(parsed, ticker, year)
    for i, c in enumerate(out):
        c["chunk_id"], c["seq"] = f"{doc_id}-{variant}-{i:05d}", i
    return out


def embed(variant: str, doc_id: str, chunks: list[dict]) -> np.ndarray:
    from backend.ingest.embed import embed_passages

    path = EMB_DIR / variant / f"{doc_id}.npz"
    path.parent.mkdir(parents=True, exist_ok=True)
    keys = [hashlib.sha1(c["text"].encode()).hexdigest() for c in chunks]
    cached = dict(np.load(path)) if path.exists() else {}
    todo = [i for i, k in enumerate(keys) if k not in cached]
    if todo:
        for i, v in zip(todo, embed_passages([chunks[i]["text"] for i in todo]), strict=True):
            cached[keys[i]] = v.astype(np.float32)
        np.savez_compressed(path, **{k: cached[k] for k in keys})
    return np.stack([cached[k] for k in keys])


def load_variant(variant: str) -> dict:
    """Fill abl.chunks with this variant's text chunks plus the production table/chart chunks."""
    with connect() as conn:
        conn.autocommit = True
        conn.execute("drop schema if exists abl cascade")
        conn.execute("create schema abl")
        conn.execute("create table abl.chunks (like public.chunks)")
        conn.execute("insert into abl.chunks select * from public.chunks where kind <> 'text'")
        n_text, tokens = 0, []
        for doc_id, row in read_manifest().items():
            chunks = variant_chunks(variant, doc_id, row["ticker"], int(row["year"]))
            vectors = embed(variant, doc_id, chunks)
            with conn.cursor().copy(
                    """copy abl.chunks (chunk_id, doc_id, ticker, fiscal_year, page_start, page_end, section_path,
                                        seq, kind, lang, pair_id, text, embedding, chunker) from stdin""") as cp:
                for c, v in zip(chunks, vectors, strict=True):
                    cp.write_row((c["chunk_id"], doc_id, c["ticker"], c["fiscal_year"], c["page_start"],
                                  c["page_end"], c["section_path"], c["seq"], "text",
                                  c["lang"] if c["lang"] in ("id", "en") else None, c["pair_id"], c["text"],
                                  "[" + ",".join(f"{x:.6f}" for x in v) + "]", variant))
            n_text += len(chunks)
            tokens += [ntok(c["text"].split("\n", 1)[1]) for c in chunks]
            print(f"{variant} {doc_id}: {len(chunks)} text chunks", flush=True)
        conn.execute("create index on abl.chunks (ticker, fiscal_year)")
        conn.execute("create index on abl.chunks (doc_id, seq)")
        conn.execute("create index on abl.chunks using gin (to_tsvector('simple', text))")
        conn.execute("create index on abl.chunks using hnsw (embedding halfvec_cosine_ops)")
        conn.execute("analyze abl.chunks")
        db_mb = conn.execute("select pg_database_size(current_database())").fetchone()[0] // 1024**2
    print(f"{variant}: DB {db_mb} MB", flush=True)
    return {"text_chunks": n_text, "mean_tokens": round(statistics.mean(tokens)), "db_mb": f"{db_mb} MB"}


@contextmanager
def search_conn(schema: str | None = None):
    """A pooled connection for retrieval in one variant. ef_search 1000 (the maximum) makes dense search near-exact,
    so the approximation error of the production index (built incrementally) and the ablation ones (built in bulk)
    doesn't differ between variants. SET LOCAL ends with the transaction: the connection goes back to the pool as
    it was."""
    with pooled() as conn:
        conn.execute("set local hnsw.ef_search = 1000")
        if schema:
            conn.execute(f"set local search_path to {schema}, public")
        yield conn


def strict_gains(hits: list[dict], item: dict, field: str = "text") -> list[int]:
    """1 when the hit is from the expected document, covers an expected page and contains the golden evidence. Page
    overlap alone credits a long chunk that only touches an expected page (review, 2026-11-02)."""
    rx, expected = re.compile(item["evidence"], re.I), set(item["expected_pages"])
    return [int(h["doc_id"] == item["expected_doc"] and bool(expected & set(range(h["page_start"], h["page_end"] + 1)))
                and bool(rx.search(" ".join(h[field].split())))) for h in hits]


def evaluate_variant(items: list[dict], terms: dict[str, list[str]], schema: str | None) -> dict:
    answerable = [i for i in items if i["type"] in evaluate.ANSWERABLE]
    retrieval.pooled = lambda: search_conn(schema)
    try:
        out = {}
        for method in evaluate.METHODS:
            pages, strict, ranking = [], [], []
            for item in answerable:
                extra = terms[item["question"]] if method != "dense" else []
                _, hits = retrieval.retrieve(item["question"], extra, method=method, pack=False)
                pages.append((item, evaluate.gains(hits, item)))
                strict.append((item, strict_gains(hits, item)))
                ranking.append([h["chunk_id"] for h in hits])
            out[method] = {"all": evaluate.retrieval_metrics(pages), "strict": evaluate.retrieval_metrics(strict),
                           "id": evaluate.retrieval_metrics([r for r in pages if r[0]["lang"] == "id"]),
                           "ranking": ranking}
        # What the answer model actually gets: top final_k hits, small-to-big, within the context token budget.
        seen, n_packed, tokens = [], [], []
        for item in answerable:
            _, packed = retrieval.retrieve(item["question"], terms[item["question"]])
            seen.append(any(strict_gains(packed, item, field="context")))
            n_packed.append(len(packed))
            tokens.append(sum(h["tokens"] for h in packed))
        out["packed"] = {"evidence_seen": round(statistics.mean(seen), 3),
                         "chunks": round(statistics.mean(n_packed), 1), "tokens": round(statistics.mean(tokens))}
        return out
    finally:
        retrieval.pooled = pooled


def production_stats() -> dict:
    from backend.ingest.chunk import CHUNKS_DIR

    texts = [c["text"] for p in sorted(CHUNKS_DIR.glob("*.jsonl")) for line in p.open(encoding="utf-8")
             if (c := json.loads(line))["kind"] == "text"]
    return {"text_chunks": len(texts), "mean_tokens": round(statistics.mean(ntok(t.split("\n", 1)[1]) for t in texts))}


def run() -> int:
    items = evaluate.load()
    # Translate each question once, so every variant searches with exactly the same terms.
    terms = {i["question"]: evaluate.translated_terms(i["question"])
             for i in items if i["type"] in evaluate.ANSWERABLE}
    results, stats = {}, {"section": production_stats()}
    try:
        results["section"] = evaluate_variant(items, terms, None)
        again = evaluate_variant(items, terms, None)["hybrid"]["ranking"]  # run-to-run noise, measured
        noise = sum(a != b for a, b in zip(results["section"]["hybrid"]["ranking"], again, strict=True))
        off = evaluate_variant(items, {q: [] for q in terms}, None)  # §6.3 "with/without transforms"
        results["section, no translation"] = {"hybrid": off["hybrid"], "packed": off["packed"]}
        for variant in ("page", "fixed"):
            stats[variant] = load_variant(variant)
            results[variant] = evaluate_variant(items, terms, "abl")
    finally:
        with connect() as conn:
            conn.execute("drop schema if exists abl cascade")
            conn.commit()
    meta = {"noise": noise, "questions": len(terms), "untranslated": sum(1 for t in terms.values() if not t),
            "reports": len(read_manifest())}
    path = evaluate.REPORTS / f"ablation_{date.today().strftime('%Y%m%d')}.md"
    path.write_text(report(results, stats, meta), encoding="utf-8")
    print(path)
    return 0


def report(results: dict, stats: dict, meta: dict) -> str:
    ks = evaluate.KS
    lines = [f"# Chunking ablation {date.today().isoformat()}", "",
             f"{meta['questions']} answerable golden questions over {meta['reports']} FY2025 reports. Table and chart "
             "chunks are the same in every variant; only text chunking changes. Every variant searches with the same "
             f"translated terms ({meta['untranslated']} questions got none). Dense search runs near-exact "
             "(`hnsw.ef_search` 1000). Run-to-run noise, measured: the same hybrid search twice gave a different "
             f"ranking for {meta['noise']} of {meta['questions']} questions.", "",
             "| chunking | text chunks | mean tokens | DB after load |", "|---|---|---|---|"]
    lines += [f"| {v} | {s['text_chunks']:,} | {s['mean_tokens']} | {s.get('db_mb', '-')} |" for v, s in stats.items()]
    lines += ["", "**Ranked results.** recall@k credits a hit from the expected document that covers an expected page. "
              "Strict also requires the golden evidence (a regex) in the chunk's own text, because a long chunk that "
              "only touches an expected page would otherwise count. k counts chunks, so a variant with bigger chunks "
              "gets more text at the same k: the second table compares equal context.", "",
              "| chunking | method | " + " | ".join(f"recall@{k}" for k in ks)
              + " | strict recall@6 | strict recall@12 | MRR | strict MRR | nDCG@6 | recall@6 (Bahasa) |",
              "|---" * (len(ks) + 8) + "|"]
    for variant, r in results.items():
        for method, m in r.items():
            if method == "packed":
                continue
            a, st = m["all"], m["strict"]
            lines.append(f"| {variant} | {method} | " + " | ".join(f"{a[f'recall@{k}']:.3f}" for k in ks)
                         + f" | {st['recall@6']:.3f} | {st['recall@12']:.3f} | {a['mrr']:.3f} | {st['mrr']:.3f} | "
                         f"{a['ndcg@6']:.3f} | {m['id']['recall@6']:.3f} |")
    lines += ["", "**What the answer model gets (hybrid).** Production packing: the top 6 cleaned hits, each with its "
              "neighbouring chunks, within the 4,000-token context budget. Evidence seen = the golden evidence is in "
              "a packed context from the expected document and page.", "",
              "| chunking | evidence seen | chunks packed | context tokens |", "|---|---|---|---|"]
    lines += [f"| {v} | {r['packed']['evidence_seen']:.3f} | {r['packed']['chunks']} | {r['packed']['tokens']:,} |"
              for v, r in results.items()]
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(run())
