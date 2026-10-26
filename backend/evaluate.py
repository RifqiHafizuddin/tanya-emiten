"""Golden-set evaluation (§6.3 metrics, §6.6, MVP 1b/1c). Writes eval/reports/eval_YYYYMMDD.md and an eval_runs row.

Retrieval: a retrieved chunk is relevant when it comes from the expected document and covers an expected page.
recall@k = share of answerable questions with a relevant chunk in the top k; MRR over the whole cleaned ranking;
nDCG@k with binary gains, each expected page counted once, ideal = min(k, number of expected pages).
"""
import json
import math
import statistics
import time
from datetime import date

from backend import retrieval
from backend.answer import respond, translated_terms
from backend.config import ROOT, config

GOLDEN = ROOT / "eval" / "golden.jsonl"
REPORTS = ROOT / "eval" / "reports"
KS = (4, 6, 8, 12)
METHODS = ("lexical", "dense", "hybrid")
ANSWERABLE = ("fact", "table", "chart")


def load(subset: int | None = None) -> list[dict]:
    rows = [json.loads(line) for line in GOLDEN.open(encoding="utf-8") if line.strip()]
    if subset:  # every n-th item, so a subset keeps the mix of types and languages
        rows = rows[:: max(1, len(rows) // subset)][:subset]
    return rows


def gains(hits: list[dict], item: dict) -> list[int]:
    """1 for each hit that covers an expected page not covered by an earlier hit."""
    expected, seen, out = set(item["expected_pages"]), set(), []
    for h in hits:
        pages = set()
        if h["doc_id"] == item["expected_doc"]:
            pages = set(range(h["page_start"], h["page_end"] + 1)) & (expected - seen)
        seen |= pages
        out.append(1 if pages else 0)
    return out


def retrieval_metrics(results: list[tuple[dict, list[int]]]) -> dict:
    m = {}
    for k in KS:
        m[f"recall@{k}"] = statistics.mean(1.0 if any(g[:k]) else 0.0 for _, g in results)
        m[f"ndcg@{k}"] = statistics.mean(
            sum(x / math.log2(i + 2) for i, x in enumerate(g[:k]))
            / sum(1 / math.log2(i + 2) for i in range(min(k, len(item["expected_pages"]))))
            for item, g in results)
    m["mrr"] = statistics.mean(next((1 / (i + 1) for i, x in enumerate(g) if x), 0.0) for _, g in results)
    return {k: round(v, 3) for k, v in m.items()}


def eval_retrieval(items: list[dict]) -> dict:
    answerable = [i for i in items if i["type"] in ANSWERABLE]
    out = {}
    for method in METHODS:
        results = []
        for item in answerable:
            extra = translated_terms(item["question"]) if method != "dense" else []
            _, hits = retrieval.retrieve(item["question"], extra, method=method, pack=False)
            results.append((item, gains(hits, item)))
        out[method] = {"all": retrieval_metrics(results),
                       "id": retrieval_metrics([r for r in results if r[0]["lang"] == "id"]),
                       "misses@6": [item["id"] for item, g in results if not any(g[:6])]}
    return out


def eval_answers(items: list[dict]) -> dict:
    rows = []
    for item in items:
        t0 = time.time()
        try:
            res = respond(item["question"])
        except Exception as e:  # quota or provider errors are reported, not hidden
            rows.append({"id": item["id"], "type": item["type"], "error": f"{type(e).__name__}: {e}"})
            continue
        pages = {(c["doc_id"], c["page"]) for c in res["claims"]}
        rows.append({
            "id": item["id"], "type": item["type"], "lang": item["lang"], "refusal": res["refusal"],
            "cited_expected": any(d == item["expected_doc"] and p in item["expected_pages"] for d, p in pages),
            "claims": len(res["claims"]), "repair": res["repair_used"], "latency_ms": res["latency_ms"],
            "tokens": res.get("tokens", 0)})
        time.sleep(max(0.0, 8 - (time.time() - t0)))  # stay under 15 RPM on the answer model
    ok = [r for r in rows if "error" not in r]

    def rate(sel, key):
        sel = list(sel)
        return round(sum(1 for r in sel if r[key]) / len(sel), 3) if sel else None

    lat = sorted(r["latency_ms"] for r in ok) or [0]
    return {
        "refused_unanswerable": rate((r for r in ok if r["type"] == "unanswerable"), "refusal"),
        "refused_advice": rate((r for r in ok if r["type"] == "advice"), "refusal"),
        "answered": round(1 - (rate((r for r in ok if r["type"] in ANSWERABLE), "refusal") or 0), 3),
        "cited_expected_page": rate((r for r in ok if r["type"] in ANSWERABLE), "cited_expected"),
        "repair_rate": rate(ok, "repair"),
        "latency_p50_ms": lat[len(lat) // 2], "latency_p95_ms": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
        "mean_tokens": round(statistics.mean(r["tokens"] for r in ok)) if ok else 0,
        "errors": [r for r in rows if "error" in r],
        "rows": rows,
    }


def report(items: list[dict], ret: dict | None, ans: dict | None) -> str:
    drafts = sum(1 for i in items if i.get("status") == "draft")
    lines = [f"# Eval {date.today().isoformat()}", "",
             f"Golden set: {len(items)} questions ({drafts} still drafts, D50); prompt "
             f"system.v{config()['llm']['prompt_versions']['system']}.", ""]
    if ret:
        lines += ["## Retrieval (answerable questions)", "",
                  "| method | " + " | ".join(f"recall@{k}" for k in KS) + " | MRR | nDCG@6 | recall@6 (Bahasa) |",
                  "|---" * (len(KS) + 4) + "|"]
        for method, r in ret.items():
            a = r["all"]
            lines.append(f"| {method} | " + " | ".join(f"{a[f'recall@{k}']:.3f}" for k in KS)
                         + f" | {a['mrr']:.3f} | {a['ndcg@6']:.3f} | {r['id']['recall@6']:.3f} |")
        lines += ["", f"Hybrid misses at 6: {', '.join(ret['hybrid']['misses@6']) or 'none'}", ""]
    if ans:
        lines += ["## Answers", ""] + [f"- {k}: {v}" for k, v in ans.items() if k not in ("rows", "errors")]
        lines += [f"- errors: {len(ans['errors'])}", "", "| id | type | refusal | cited expected page | claims |"
                  " repair | latency ms |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {r['id']} | {r['type']} | {r['refusal']} | {r['cited_expected']} | {r['claims']} | "
                  f"{r['repair']} | {r['latency_ms']} |" for r in ans["rows"] if "error" not in r]
    return "\n".join(lines) + "\n"


def run(subset: int | None = None, answers: bool = False) -> int:
    from backend.db import connect

    items = load(subset)
    ret = eval_retrieval(items)
    ans = eval_answers(items) if answers else None
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"eval_{date.today():%Y%m%d}.md"
    path.write_text(report(items, ret, ans), encoding="utf-8")
    metrics = {"n": len(items), "retrieval": ret, "answers": {k: v for k, v in (ans or {}).items() if k != "rows"}}
    with connect() as conn:
        conn.execute("insert into eval_runs (phase, metrics) values (%s, %s)", ["mvp1", json.dumps(metrics)])
    print(path.read_text(encoding="utf-8"))
    return 0
