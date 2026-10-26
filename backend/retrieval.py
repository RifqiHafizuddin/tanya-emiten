"""Hybrid retrieval (D16, D31-D34, §6.3): understand -> filter -> lexical + dense -> RRF -> clean up -> expand/pack."""
import re
from dataclasses import dataclass, field
from functools import cache

import yaml

from backend.config import ROOT, config
from backend.db import connect
from backend.ingest.parse_pdf import detect_lang

STOP = set(
    "the a an of to in for on and or is are was were be by with what why how which who when does did do its it"
    " this that from as at than vs versus about between"
    " yang dan di ke dari untuk pada apa apakah mengapa kenapa bagaimana berapa siapa kapan adalah ini itu"
    " dengan atau tahun dalam oleh se bagi tentang antara".split()
)


@dataclass
class Query:
    text: str
    lang: str
    tickers: list[str]
    years: list[int]
    terms: list[str] = field(default_factory=list)


@cache
def aliases() -> list[tuple[re.Pattern, str]]:
    data = yaml.safe_load((ROOT / "corpus" / "aliases.yaml").read_text(encoding="utf-8"))
    pairs = [(t, t) for t in data] + [(a, t) for t, names in data.items() for a in names]
    # Longest names first so "Bank Mandiri" wins over "Mandiri" and "Indofood CBP" over "Indofood".
    pairs.sort(key=lambda p: -len(p[0]))
    return [(re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])", re.I), t) for name, t in pairs]


def understand(question: str) -> Query:
    """Language, companies (alias table, D32) and fiscal years by regex. No LLM call."""
    tickers, rest = [], question
    for pattern, ticker in aliases():
        if pattern.search(rest):
            if ticker not in tickers:
                tickers.append(ticker)
            rest = pattern.sub(" ", rest)  # a matched name must not match again as a shorter alias
    years = sorted({int(y) for y in re.findall(r"(?<!\d)(20[12]\d)(?!\d)", question)})
    fy = config()["annual_reports"]["fiscal_years"]
    years = [y for y in years if y in fy] or fy
    lang = detect_lang(question) or ("id" if re.search(r"\b(apa|kenapa|mengapa|bagaimana|berapa)\b", question, re.I)
                                     else "en")
    # Terms from what is left after removing company names: the company is a filter, and its name is in every one
    # of its chunks' headers, so as a term it only adds noise (ts_rank_cd has no IDF to discount it).
    terms = [w for w in re.findall(r"[\w&-]{2,}", rest.lower()) if w not in STOP and not w.isdigit()]
    return Query(question, "en" if lang == "mixed" else lang, tickers, years, terms)


def _tsquery(terms: list[str]) -> str:
    out = []
    for t in terms:
        t = re.sub(r"[^\w]", "", t)
        parts = re.findall(r"[^\W\d_]+|\d+", t)
        if len(parts) > 1:  # "cet1" also matches "CET 1" as written in the report
            out.append(f"({t} | {' <-> '.join(parts)})")
        elif t:
            out.append(t)
    return " | ".join(out)


def _filters(q: Query, tickers: list[str] | None) -> tuple[str, list]:
    sql, args = "fiscal_year = any(%s)", [q.years]
    if tickers:
        sql += " and ticker = any(%s)"
        args.append(tickers)
    return sql, args


def lexical(conn, q: Query, tickers: list[str] | None, extra_terms: list[str] = (), k: int | None = None):
    k = k or config()["retrieval"]["k_lexical"]
    tsq = _tsquery(q.terms + list(extra_terms))
    if not tsq:
        return []
    where, args = _filters(q, tickers)
    return conn.execute(
        f"""select chunk_id from chunks, to_tsquery('simple', %s) tq
            where to_tsvector('simple', text) @@ tq and {where}
            order by ts_rank_cd(to_tsvector('simple', text), tq) desc limit %s""",
        [tsq, *args, k],
    ).fetchall()


def dense(conn, vector: str, q: Query, tickers: list[str] | None, k: int | None = None):
    k = k or config()["retrieval"]["k_dense"]
    where, args = _filters(q, tickers)
    conn.execute("set local hnsw.iterative_scan = relaxed_order")  # keep k results after filtering (pgvector 0.8)
    return conn.execute(
        f"select chunk_id from chunks where {where} order by embedding <=> %s::halfvec limit %s",
        [*args, vector, k],
    ).fetchall()


def rrf(*rankings: list[str], k: int) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda x: -x[1])


def query_vector(text: str) -> str:
    from backend.ingest.embed import model

    v = model().encode([f"query: {text}"], normalize_embeddings=True)[0]
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


COLUMNS = ("chunk_id, doc_id, ticker, fiscal_year, page_start, page_end, section_path, seq, kind, lang, pair_id, "
           "text, figure_id")


def _rows(conn, ids: list[str]) -> dict[str, dict]:
    if not ids:
        return {}
    cur = conn.execute(f"select {COLUMNS} from chunks where chunk_id = any(%s)", [ids])
    names = [d.name for d in cur.description]
    return {r[0]: dict(zip(names, r, strict=True)) for r in cur.fetchall()}


def clean(ranked: list[tuple[str, float]], rows: dict[str, dict], q: Query, unscoped: bool) -> list[dict]:
    """Collapse bilingual pairs (prefer the question's language), drop near-duplicates, cap per page/company."""
    cfg = config()["retrieval"]
    out, seen_pairs, seen_text, per_page, per_company = [], {}, set(), {}, {}
    for chunk_id, score in ranked:
        r = rows.get(chunk_id)
        if not r:
            continue
        body = r["text"].split("\n", 1)[-1]
        key = re.sub(r"\W+", "", body.lower())[:200]
        if key in seen_text:
            continue
        if r["pair_id"]:
            j = seen_pairs.get(r["pair_id"])
            if j is not None:  # the other language of an already selected pair: swap in if it matches the question
                if r["lang"] == q.lang and out[j]["lang"] != q.lang:
                    out[j] = {**r, "score": out[j]["score"]}
                continue
        page = (r["doc_id"], r["page_start"])
        if per_page.get(page, 0) >= cfg["max_per_page"]:
            continue
        if unscoped and per_company.get(r["ticker"], 0) >= cfg["max_per_company_when_unscoped"]:
            continue
        per_page[page] = per_page.get(page, 0) + 1
        per_company[r["ticker"]] = per_company.get(r["ticker"], 0) + 1
        seen_text.add(key)
        if r["pair_id"]:
            seen_pairs[r["pair_id"]] = len(out)
        out.append({**r, "score": score})
    return out


def expand_and_pack(conn, hits: list[dict]) -> list[dict]:
    """Top final_k hits, each with its previous/next chunk of the same section and language (small-to-big),
    strongest first, within context_token_budget."""
    from backend.ingest.chunk import ntok

    cfg_r, n = config()["retrieval"], config()["chunking"]["expand_neighbours"]
    budget, packed, used = cfg_r["context_token_budget"], [], 0
    for h in hits[: cfg_r["final_k"]]:
        neighbours = conn.execute(
            f"""select {COLUMNS} from chunks where doc_id = %s and kind = 'text' and seq between %s and %s
                and seq <> %s and section_path is not distinct from %s and lang is not distinct from %s order by seq""",
            [h["doc_id"], h["seq"] - n, h["seq"] + n, h["seq"], h["section_path"], h["lang"]],
        ).fetchall() if h["kind"] == "text" else []
        before = [r[11].split("\n", 1)[-1] for r in neighbours if r[7] < h["seq"]]
        after = [r[11].split("\n", 1)[-1] for r in neighbours if r[7] > h["seq"]]
        cost = ntok(h["text"])
        if used + cost > budget and packed:
            break
        context = h["text"]
        for extra in before[::-1] + after:  # add neighbours while the budget allows
            t = ntok(extra)
            if used + cost + t > budget:
                break
            cost += t
            context = f"{extra}\n{context}" if extra in before else f"{context}\n{extra}"
        used += cost
        packed.append({**h, "context": context, "tokens": cost})
    return packed


def retrieve(question: str, extra_terms: list[str] = (), method: str = "hybrid",
             pack: bool = True) -> tuple[Query, list[dict]]:
    """Full pipeline. Entity split (D31): one retrieval per resolved ticker, merged; no ticker -> all companies
    with the per-company cap (D33). `extra_terms` carries the translated query terms for the lexical side.
    `method` (hybrid | lexical | dense) and `pack=False` (cleaned ranking, no expansion) exist for the eval."""
    q = understand(question)
    k = config()["retrieval"]["rrf_k"]
    vector = query_vector(question) if method != "lexical" else None
    with connect() as conn, conn.transaction():
        rankings = []
        for scope in ([[t] for t in q.tickers] or [None]):
            if method != "dense":
                rankings.append([r[0] for r in lexical(conn, q, scope, extra_terms)])
            if method != "lexical":
                rankings.append([r[0] for r in dense(conn, vector, q, scope)])
        ranked = rrf(*rankings, k=k)
        rows = _rows(conn, [c for c, _ in ranked])
        hits = clean(ranked, rows, q, unscoped=not q.tickers)
        return q, expand_and_pack(conn, hits) if pack else hits
