"""MVP 1 fixed pipeline (D35, §6.4): understand -> retrieve -> generate -> verify -> [repair once] -> respond.

Guardrails enforced here in code: advice refusal (5), every claim carries a verbatim quote from a retrieved chunk (3),
numbers only inside verified quotes (2), crops only from retrieved figures (4), retrieved text inside data tags (6).
"""
import re
import time
import unicodedata
from collections.abc import Callable
from html import escape

from pydantic import BaseModel, Field

from backend import llm, retrieval
from backend.config import ROOT, config, env

DISCLAIMER = {
    "en": "Based only on the companies' annual reports. Not investment advice.",
    "id": "Hanya berdasarkan laporan tahunan perusahaan. Bukan saran investasi.",
}
ADVICE = re.compile(
    r"\b(should i (buy|sell|hold)|buy or sell|worth buying|target price|price target|undervalued|overvalued|"
    r"good (stock|investment) to buy|beli atau jual|layak dibeli|sebaiknya (beli|jual|saya beli)|harga target|"
    r"target harga|murah atau mahal|saham (yang )?bagus untuk dibeli|rekomendasi (beli|jual|saham))\b",
    re.I,
)
NUMBER = re.compile(r"\d[\d.,]*")
IMAGE_KINDS = ("chart", "diagram")  # D56: only these have crops; tables are text chunks


class Claim(BaseModel):
    text: str
    chunk_ids: list[str]
    quote: str


class FigureRef(BaseModel):
    figure_id: str
    why: str


class Answer(BaseModel):
    lang: str = Field(description="id or en: the language of the question")
    refusal: bool
    refusal_reason: str | None = None
    # Required, claims first: Gemini omits optional fields, and answered with figures only.
    claims: list[Claim]
    figures: list[FigureRef]


def prompt_text(name: str) -> tuple[str, str]:
    version = config()["llm"]["prompt_versions"][name]
    return (ROOT / "prompts" / f"{name}.v{version}.md").read_text(encoding="utf-8"), f"{name}.v{version}"


def normalize(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-")
    s = re.sub(r"-\s+", "", s)  # words hyphenated across a line break
    return re.sub(r"\s+", " ", s).strip()


def data_blocks(hits: list[dict]) -> str:
    blocks = []
    for h in hits:
        tag = "figure" if h["figure_id"] and h["kind"] in IMAGE_KINDS else "chunk"
        attrs = f'id="{h["chunk_id"]}" ticker="{h["ticker"]}" page="{h["page_start"]}"'
        if tag == "figure":
            attrs += f' figure="{h["figure_id"]}"'
        blocks.append(f"<{tag} {attrs}>\n{escape(h['context'], quote=False)}\n</{tag}>")
    return "\n\n".join(blocks)


def verify(ans: Answer, hits: list[dict], lang: str) -> tuple[list[Claim], list[FigureRef], list[str]]:
    """Keep only claims/figures that pass every code check; return the error messages for a repair round."""
    by_id = {h["chunk_id"]: h for h in hits}
    images = {h["figure_id"]: h["figure_id"] for h in hits if h["figure_id"] and h["kind"] in IMAGE_KINDS}
    images |= {h["chunk_id"]: h["figure_id"] for h in hits if h["figure_id"] and h["kind"] in IMAGE_KINDS}
    good_claims, good_figures, errors = [], [], []
    if ans.lang != lang and not ans.refusal:
        errors.append(f"Answer language is '{ans.lang}' but the question is in '{lang}'. "
                      f"Write claim texts in '{lang}'.")
    for i, c in enumerate(ans.claims):
        problems = []
        cited = [by_id[cid] for cid in c.chunk_ids if cid in by_id]
        if not cited:
            problems.append(f"cites unknown chunk ids {c.chunk_ids}")
        elif not any(normalize(c.quote) in normalize(h["context"]) for h in cited):
            problems.append("quote is not an exact substring of the cited chunk")
        quote_numbers = {n.strip(".,") for n in NUMBER.findall(c.quote)}
        stray = [n.strip(".,") for n in NUMBER.findall(c.text) if n.strip(".,") not in quote_numbers]
        if stray:
            problems.append(f"numbers {stray} are not in the quote")
        if problems:
            errors.append(f"Claim {i + 1} ({c.text[:60]!r}): " + "; ".join(problems) + ".")
        else:
            good_claims.append(c)
    if not ans.claims and not ans.refusal:
        errors.append("The answer has no claims. Answer with claims (each with a chunk id and a verbatim quote), "
                      "or refuse; figures alone are not an answer.")
    for f in ans.figures:
        if f.figure_id in images:  # the model sometimes names a figure by its chunk id
            good_figures.append(FigureRef(figure_id=images[f.figure_id], why=f.why))
        else:
            errors.append(f"Figure {f.figure_id} is not one of the <figure> blocks; cite figures by their figure "
                          "alias, or leave figures empty.")
    return good_claims, good_figures, errors


def translated_terms(question: str) -> list[str]:
    """Lexical terms of the question in the other language (D31 bilingual transform)."""
    translate, _ = prompt_text("translate")
    try:  # the bilingual query only adds lexical recall; never fail an answer over it
        return retrieval.understand(llm.generate("small", translate, question).text).terms
    except Exception:
        return []


def crop_url(storage_path: str) -> str:
    return f"{env('SUPABASE_URL').rstrip('/')}/storage/v1/object/public/crops/{storage_path}"


def respond(question: str, on_step: Callable[[dict], None] = lambda step: None) -> dict:
    """`on_step` receives progress events for the UI (§6.4 streaming): {"step": name, ...details}."""
    t0 = time.time()
    q = retrieval.understand(question)  # regex only, instant: the UI learns the language from the first step
    on_step({"step": "understanding", "lang": q.lang})
    system, prompt_version = prompt_text("system")
    base = {"question": question, "lang": q.lang, "prompt_version": prompt_version, "disclaimer": DISCLAIMER[q.lang]}
    if ADVICE.search(question):
        reason = {"en": "I can explain what the annual reports say, but I don't give buy, sell or hold "
                        "recommendations or price targets.",
                  "id": "Saya bisa menjelaskan isi laporan tahunan, tetapi tidak memberi rekomendasi beli, jual, "
                        "tahan, atau target harga."}[q.lang]
        return {**base, "refusal": True, "refusal_reason": reason, "claims": [], "figures": [], "retrieved": [],
                "checks": {"advice_rule": True}, "repair_used": False, "latency_ms": int((time.time() - t0) * 1000)}

    on_step({"step": "searching", "tickers": q.tickers, "years": q.years})
    q, hits = retrieval.retrieve(question, translated_terms(question))
    if not hits:
        return {**base, "refusal": True, "refusal_reason": _no_support(q.lang), "claims": [], "figures": [],
                "retrieved": [], "checks": {}, "repair_used": False, "latency_ms": int((time.time() - t0) * 1000)}

    user = f"{data_blocks(hits)}\n\nQuestion ({q.lang}): {question}"
    tokens, repair_used = 0, False
    on_step({"step": "writing", "pages": sorted({(h["ticker"], h["page_start"]) for h in hits})})
    res = llm.generate("answer", system, user, schema=Answer)
    tokens += res.input_tokens + res.output_tokens
    on_step({"step": "checking"})
    claims, figures, errors = verify(res.parsed, hits, q.lang)
    if errors and config()["agent"]["max_repairs"] > 0 and not res.parsed.refusal:
        repair_used = True
        on_step({"step": "repairing", "errors": len(errors)})
        fix = user + "\n\nYour previous answer failed these checks. Fix them, keep only what the data supports:\n- " \
            + "\n- ".join(errors) + f"\n\nPrevious answer:\n{res.text}"
        res2 = llm.generate("answer", system, fix, schema=Answer)
        tokens += res2.input_tokens + res2.output_tokens
        claims, figures, errors = verify(res2.parsed, hits, q.lang)
        res = res2
    refusal = res.parsed.refusal or not claims
    by_id = {h["chunk_id"]: h for h in hits}
    out_claims = []
    for c in claims:
        h = next(by_id[cid] for cid in c.chunk_ids if cid in by_id)
        out_claims.append({"text": c.text, "quote": c.quote, "chunk_id": h["chunk_id"], "ticker": h["ticker"],
                           "page": h["page_start"], "doc_id": h["doc_id"]})
    fig_rows = _figures([f.figure_id for f in figures]) if not refusal else []
    return {
        **base, "refusal": refusal,
        "refusal_reason": (res.parsed.refusal_reason or _no_support(q.lang)) if refusal else None,
        "claims": out_claims if not refusal else [],
        "figures": [{**fr, "why": next(f.why for f in figures if f.figure_id == fr["figure_id"])} for fr in fig_rows],
        "closest_pages": [{"ticker": h["ticker"], "page": h["page_start"], "doc_id": h["doc_id"]} for h in hits[:3]]
        if refusal else [],
        "sources": _sources(sorted({h["doc_id"] for h in hits})),  # doc_id -> IR PDF, linked with #page=N
        "retrieved": [{"chunk_id": h["chunk_id"], "ticker": h["ticker"], "page": h["page_start"],
                       "score": round(h["score"], 4), "kind": h["kind"]} for h in hits],
        "checks": {"errors_after_repair": errors, "claims_kept": len(claims),
                   "claims_proposed": len(res.parsed.claims)},
        "repair_used": repair_used, "tokens": tokens, "model": res.model,
        "latency_ms": int((time.time() - t0) * 1000),
    }


def _no_support(lang: str) -> str:
    return {"en": "I couldn't find support for this in the annual reports I have.",
            "id": "Saya tidak menemukan dukungan untuk pertanyaan ini di laporan tahunan yang tersedia."}[lang]


def _sources(doc_ids: list[str]) -> dict[str, str]:
    from backend.db import connect

    with connect() as conn:
        return dict(conn.execute("select doc_id, source_url from documents where doc_id = any(%s)", [doc_ids]))


def _figures(ids: list[str]) -> list[dict]:
    if not ids:
        return []
    from backend.db import connect

    with connect() as conn:
        rows = conn.execute(
            """select f.figure_id, f.page_no, f.kind, f.caption, f.storage_path, d.source_url, d.ticker
               from figures f join documents d using (doc_id) where f.figure_id = any(%s)""", [ids]).fetchall()
    return [{"figure_id": r[0], "page": r[1], "kind": r[2], "caption": r[3],
             "url": crop_url(r[4]) if r[4] else None, "source_url": r[5], "ticker": r[6]} for r in rows]
