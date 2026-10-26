"""Tanya Emiten CLI (§11). Each step reads the previous step's output, fails loudly if missing, and is resumable."""
import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="run.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate", help="apply pending SQL migrations to DATABASE_URL")
    p_fetch = sub.add_parser("fetch", help="polite download of annual reports from company IR sites (D43)")
    p_fetch.add_argument("--kind", choices=["annual"], default="annual")
    p_fetch.add_argument("--tickers", nargs="*", help="limit to these tickers")
    p_ingest = sub.add_parser("ingest", help="parse + chunk every fetched annual report")
    p_ingest.add_argument("--kind", choices=["annual"], default="annual")
    p_ingest.add_argument("--tickers", nargs="*", help="limit to these tickers")
    p_ingest.add_argument("--force", action="store_true", help="re-parse even if output exists")
    p_ingest.add_argument("--no-ocr", action="store_true", help="skip the hosted OCR step (uses cached OCR only)")
    p_index = sub.add_parser("index", help="embed chunks, load Postgres, upload crops")
    p_index.add_argument("--tickers", nargs="*", help="limit to these tickers")
    p_ask = sub.add_parser("ask", help="answer one question, print claims and citations")
    p_ask.add_argument("question")
    p_eval = sub.add_parser("eval", help="golden set -> eval/reports/ (retrieval metrics; --answers adds LLM answers)")
    p_eval.add_argument("--subset", type=int, help="every n-th question, this many in total")
    p_eval.add_argument("--answers", action="store_true", help="also run the full answer pipeline (uses LLM quota)")
    args = parser.parse_args(argv)

    if args.cmd == "migrate":
        from backend.db import migrate

        applied = migrate()
        print("applied:", ", ".join(applied) if applied else "nothing (up to date)")
    elif args.cmd == "fetch":
        from backend.ingest.fetch import fetch_annual

        return fetch_annual(args.tickers)
    elif args.cmd == "ingest":
        return ingest_annual(args.tickers, args.force, args.no_ocr)
    elif args.cmd == "index":
        return index(args.tickers)
    elif args.cmd == "ask":
        import json

        from backend.answer import respond

        print(json.dumps(respond(args.question), ensure_ascii=False, indent=2))
    elif args.cmd == "eval":
        from backend.evaluate import run

        return run(args.subset, args.answers)
    return 0


# Free-tier guards (guardrail 7, docs/free_tier.md): stop before Neon (DB, D54) and Supabase Storage limits, not after.
DB_LIMIT_BYTES, STORAGE_LIMIT_BYTES = 1024**3, 1024**3


def index(tickers: list[str] | None) -> int:
    import json

    from backend.ingest import embed
    from backend.ingest.fetch import read_manifest
    from backend.ingest.ocr import CROPS_DIR
    from backend.ingest.parse_pdf import PARSED_DIR

    manifest = read_manifest()
    embed.load_companies()
    embed.ensure_bucket()
    for doc_id, row in manifest.items():
        if tickers and row["ticker"] not in tickers:
            continue
        chunks_path = PARSED_DIR.parent / "chunks" / f"{doc_id}.jsonl"
        if not chunks_path.exists():
            print(f"{doc_id}: no chunks yet, run `python run.py ingest` first")
            continue
        parsed = json.loads((PARSED_DIR / f"{doc_id}.json").read_text(encoding="utf-8"))
        figures = json.loads((PARSED_DIR.parent / "figures" / f"{doc_id}.json").read_text(encoding="utf-8"))
        chunks = embed.load_chunks_file(doc_id)
        new_bytes = sum((CROPS_DIR / f["storage_path"]).stat().st_size for f in figures if f.get("storage_path"))
        if embed.storage_bytes() + new_bytes > 0.9 * STORAGE_LIMIT_BYTES:
            print(f"STOP {doc_id}: crops would pass 90% of the 1 GB Storage limit")
            return 1
        vectors = embed.embed_chunks(doc_id, chunks)
        uploaded = embed.upload_crops(figures)
        embed.load_document(row, parsed, figures, chunks, vectors)
        db_bytes = _db_bytes()
        if db_bytes > 0.7 * DB_LIMIT_BYTES:
            db_bytes = _db_bytes(compact=True)
        print(f"{doc_id}: {len(chunks)} chunks, {uploaded} crops; DB now {db_bytes / 1024**2:.0f} MB")
        if db_bytes > 0.7 * DB_LIMIT_BYTES:
            print("STOP: database passed 70% of the 1 GB Neon limit (owner decides the next mitigation)")
            return 1
    from backend.db import connect

    with connect() as conn:  # cached answers were built from the old chunks
        conn.execute("delete from answer_cache")
        conn.commit()
    print(f"DB after compacting: {_db_bytes(compact=True) / 1024**2:.0f} MB")
    return 0


def _db_bytes(compact: bool = False) -> int:
    """Database size; `compact` first rebuilds the FTS index, which incremental inserts bloat about 4x."""
    from backend.db import connect

    with connect() as conn:
        if compact:
            conn.autocommit = True
            conn.execute("reindex index chunks_fts_idx")
        return conn.execute("select pg_database_size(current_database())").fetchone()[0]


def ingest_annual(tickers: list[str] | None, force: bool, no_ocr: bool) -> int:
    """OCR layout (hosted, every page) -> hybrid assembly (D55) -> crops -> chunks, per document. OCR results are
    cached per page; --force re-assembles from the cache (no OCR quota)."""
    import json

    import pymupdf

    from backend.ingest.assemble import assemble
    from backend.ingest.chunk import CHUNKS_DIR, chunk, write_chunks
    from backend.ingest.fetch import PDF_DIR, read_manifest
    from backend.ingest.ocr import OCRQuotaExceeded, load_ocr, ocr_document, render_crops

    manifest = read_manifest()
    if not manifest:
        print("corpus/manifest.csv is empty: run `python run.py fetch` first")
        return 1
    failed = 0
    for doc_id, row in manifest.items():
        if tickers and row["ticker"] not in tickers:
            continue
        pdf, ticker, year = PDF_DIR / f"{doc_id}.pdf", row["ticker"], int(row["year"])
        figures_path = CHUNKS_DIR.parent / "figures" / f"{doc_id}.json"
        try:
            with pymupdf.open(pdf) as doc:
                n_pages = doc.page_count
            if not no_ocr:
                ocr_document(doc_id, pdf, n_pages)
            ocr_pages = load_ocr(doc_id)
            if not force and figures_path.exists() and (CHUNKS_DIR / f"{doc_id}.jsonl").exists():
                parsed = json.loads((CHUNKS_DIR.parent / "parsed" / f"{doc_id}.json").read_text(encoding="utf-8"))
                if parsed.get("parser") == "hybrid" and len(ocr_pages) == n_pages:
                    continue
            parsed, figures = assemble(doc_id, ticker, year, pdf, ocr_pages)
            crops = render_crops(doc_id, pdf, figures)
            figures_path.parent.mkdir(parents=True, exist_ok=True)
            figures_path.write_text(json.dumps(figures, ensure_ascii=False), encoding="utf-8")
            chunks = chunk(parsed, ticker, year, figures)
            write_chunks(doc_id, chunks)
        except OCRQuotaExceeded as e:
            print(f"STOP at {doc_id}: {e}")
            return 1
        except Exception as e:  # one bad report must not stop the batch; it is listed and re-run later
            failed += 1
            print(f"FAILED {doc_id}: {type(e).__name__}: {e}")
            continue
        qa = json.loads((CHUNKS_DIR.parent / "qa" / f"{doc_id}.json").read_text(encoding="utf-8"))
        by_kind = {k: sum(c["kind"] == k for c in chunks) for k in ("text", "table", "chart", "diagram")}
        print(f"{doc_id}: {n_pages} pages, layout for {len(ocr_pages)}; coverage {qa['coverage_mean']}; "
              f"flags {qa['flag_counts']}; tables {qa['table_sources']} (agreement {qa['table_agreement_mean']}); "
              f"figures {len(figures)} (+{crops} crops) -> {len(chunks)} chunks {by_kind}")
    return 1 if failed else 0


if __name__ == "__main__":
    # Redirected output defaults to cp1252 on Windows; an OCR error message in Chinese once crashed the whole batch.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    sys.exit(main())
