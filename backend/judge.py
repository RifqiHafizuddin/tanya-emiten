"""Judge calibration (§6.6, MVP 1e, D40): the owner and the judge label the same answers, blind to each other.

1. `python -m backend.judge sheet`: answer a seeded random sample of golden questions (advice requests excluded:
   their refusal is enforced in code), save the full answers, run the judge and save its verdicts under data/judge/
   (not next to the owner's sheet), and write the owner's labelling sheet. The sheet never shows the verdicts, and
   the verdicts exist before the owner starts, so neither side can see the other.
2. The owner fills `owner_supported` and `owner_correct` in eval/labels/labels_<date>.csv, using the rubric in
   eval/labels/README.md (the same rubric the judge gets).
3. `python -m backend.judge agree <date>`: agreement, Cohen's kappa and per-class counts ->
   eval/reports/judge_<date>.md; the verdicts are copied next to the labels. Judge scores are reported only if both
   agreements are >= 85% on >= 50 answers. The judge prompts are frozen once labelling starts: a new version needs
   fresh labels.

`supported` is judged without the reference (claim vs its own quote only); `correct` is judged against the reference.
"""
import csv
import json
import random
import shutil
import sys
import time
from datetime import date
from typing import Literal

from pydantic import BaseModel

from backend import evaluate, llm
from backend.answer import prompt_text, respond
from backend.config import ROOT

LABELS = ROOT / "eval" / "labels"
VERDICTS = ROOT / "data" / "judge"
SEED, SAMPLE = 20261102, 80  # ~25% refuse: leaves >= 50 answers with claims for `supported`
PASS, MIN_ANSWERS = 0.85, 50
COLUMNS = {"supported": "owner_supported (yes/no/n/a)", "correct": "owner_correct (yes/no)"}
ALLOWED = {"supported": {"yes", "no", "n/a"}, "correct": {"yes", "no"}}


class Supported(BaseModel):
    supported: Literal["yes", "no", "n/a"]
    reason: str


class Correct(BaseModel):
    correct: Literal["yes", "no"]
    reason: str


def answer_text(out: dict) -> str:
    """The answer as the owner and the judge both see it."""
    if out["refusal"]:
        return f"REFUSED: {out.get('refusal_reason') or ''}"
    return "\n".join(f"{i}. {c['text']}\n   quote ({c['ticker']} FY{c['doc_id'].rsplit('-', 1)[-1]} p.{c['page']}): "
                     f"\"{c['quote']}\"" for i, c in enumerate(out["claims"], 1))


def _data(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;")  # only what could close a tag; quotes stay as written


def judge(item: dict, out: dict) -> dict:
    question = f"<question>{_data(item['question'])}</question>"
    answer = f"<answer>\n{_data(answer_text(out))}\n</answer>"
    system, _ = prompt_text("judge_supported")
    s = llm.generate("judge", system, f"{question}\n{answer}", schema=Supported).parsed
    system, _ = prompt_text("judge_correct")
    c = llm.generate("judge", system, f"{question}\n<reference>{_data(item['reference'])}</reference>\n{answer}",
                     schema=Correct).parsed
    return {"supported": s.supported, "correct": c.correct, "reason_supported": s.reason, "reason_correct": c.reason}


def sample() -> list[dict]:
    pool = [i for i in evaluate.load() if i["type"] != "advice"]
    return sorted(random.Random(SEED).sample(pool, SAMPLE), key=lambda i: i["id"])


def sheet() -> int:
    day = date.today().strftime("%Y%m%d")
    LABELS.mkdir(parents=True, exist_ok=True)
    VERDICTS.mkdir(parents=True, exist_ok=True)
    answers = LABELS / f"answers_{day}.jsonl"
    done = {json.loads(line)["id"] for line in answers.open(encoding="utf-8")} if answers.exists() else set()
    for item in sample():  # resumable: a quota stop keeps what is done
        if item["id"] in done:
            continue
        t0 = time.time()
        try:
            out = respond(item["question"])
        except Exception as e:  # kept, not skipped: dropping failures would leave only the easy questions
            out = {"refusal": True, "refusal_reason": f"ERROR (the visitor sees an error): {type(e).__name__}",
                   "claims": [], "error": str(e)[:300]}
        with answers.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"id": item["id"], "answer": out}, ensure_ascii=False) + "\n")
        print(f"{item['id']}: {'refused' if out['refusal'] else len(out['claims'])} claims", flush=True)
        time.sleep(max(0.0, 8 - (time.time() - t0)))  # stay under 15 RPM on the answer model
    items = {i["id"]: i for i in evaluate.load()}
    wanted = {i["id"] for i in sample()}
    rows = [r for r in map(json.loads, answers.open(encoding="utf-8")) if r["id"] in wanted]
    with (VERDICTS / f"judge_verdicts_{day}.jsonl").open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps({"id": r["id"], **judge(items[r["id"]], r["answer"])}, ensure_ascii=False) + "\n")
    with (LABELS / f"labels_{day}.csv").open("w", encoding="utf-8-sig", newline="") as f:  # BOM: Excel reads UTF-8
        w = csv.writer(f)
        w.writerow(["id", "lang", "type", "question", "reference", "answer", "source_pdf", *COLUMNS.values(),
                    "owner_note"])
        for r in rows:
            item, out = items[r["id"]], r["answer"]
            pages = sorted({(c["doc_id"], c["page"]) for c in out["claims"]})
            links = " ".join(f"{out['sources'].get(d, d)}#page={p}" for d, p in pages) if pages else ""
            w.writerow([item["id"], item["lang"], item["type"], item["question"], item["reference"],
                        answer_text(out), links, "", "", ""])
    print(f"{len(rows)} answers -> {LABELS / f'labels_{day}.csv'}")
    return 0


def read_labels(path) -> dict[str, dict]:
    """The owner's sheet, as saved by Excel in any locale: comma or semicolon, UTF-8 or the Windows code page."""
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252")
    dialect = csv.Sniffer().sniff(text.splitlines()[0], delimiters=",;\t")
    rows = {r["id"]: r for r in csv.DictReader(text.splitlines(keepends=True), dialect=dialect)}
    bad = []
    for i, r in rows.items():
        for label, col in COLUMNS.items():
            v = r[col].strip().lower()
            v = "n/a" if v in ("na", "n.a.") else v
            if v and v not in ALLOWED[label]:
                bad.append(f"{i} {label}={r[col]!r}")
            r[col] = v
    if bad:
        raise ValueError("labels outside the allowed values (yes/no/n/a): " + ", ".join(bad))
    return rows


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    observed = sum(j == o for j, o in pairs) / n
    classes = {c for p in pairs for c in p}
    expected = sum((sum(j == c for j, _ in pairs) / n) * (sum(o == c for _, o in pairs) / n) for c in classes)
    return 1.0 if expected == 1 else (observed - expected) / (1 - expected)


def agree(day: str, source: str = "labels") -> int:
    """`source` "labels" = the owner's sheet; "panel" = labels from the agent panel (owner decision 2026-11-02),
    reported as such: it calibrates the judge against other models, not against a person."""
    owner = read_labels(LABELS / f"{source}_{day}.csv")
    judged = {v["id"]: v for v in map(json.loads, (VERDICTS / f"judge_verdicts_{day}.jsonl").open(encoding="utf-8"))}
    answerable = {i["id"] for i in evaluate.load() if i["type"] in evaluate.ANSWERABLE}
    cfg = llm.config()["llm"]
    versions = cfg["prompt_versions"]
    who = "agent-panel" if source == "panel" else "owner"
    lines = [f"# Judge calibration {day}", "",
             f"Judge `{cfg['models']['judge']}`, prompts judge_supported.v{versions['judge_supported']} and "
             f"judge_correct.v{versions['judge_correct']}; {who} labels from {source}_{day}.csv. `supported` pairs "
             "where both say n/a (refusals) are left out.", "",
             "| label | answers | agreement | Cohen's kappa | owner no | judge caught owner's no "
             "| judge no, owner yes |", "|---|---|---|---|---|---|---|"]
    ok, why = True, []
    for label, col in COLUMNS.items():
        for scope, ids in (("all", owner.keys()), ("answerable", answerable)):
            if label == "supported" and scope == "answerable":
                continue
            pairs = [(judged[i][label], owner[i][col]) for i in ids if i in owner and owner[i][col] and i in judged]
            if label == "supported":
                pairs = [(j, o) for j, o in pairs if (j, o) != ("n/a", "n/a")]
            if not pairs:
                continue
            rate = sum(j == o for j, o in pairs) / len(pairs)
            owner_no = sum(o == "no" for _, o in pairs)
            caught = sum(j == o == "no" for j, o in pairs)
            lines.append(f"| {label} ({scope}) | {len(pairs)} | {rate:.1%} | {kappa(pairs):.2f} | {owner_no} | "
                         f"{caught} of {owner_no} | {sum(j == 'no' and o == 'yes' for j, o in pairs)} |")
            if scope == "all":
                if rate < PASS:
                    ok, why = False, [*why, f"{label} agreement {rate:.1%} < {PASS:.0%}"]
                if len(pairs) < MIN_ANSWERS:
                    ok, why = False, [*why, f"{label} has {len(pairs)} answers < {MIN_ANSWERS}"]
                if owner_no < 10:
                    why.append(f"caution: only {owner_no} owner 'no' labels for {label}, too few to show the judge "
                               "catches bad answers")
    lines += ["", f"**{'Passes' if ok else 'Does not pass'}** the bar (>= {PASS:.0%} agreement on both labels, "
              f">= {MIN_ANSWERS} answers each). " + ("Judge scores may be reported." if ok else
                                                      "Judge scores are not reported."),
              *[f"- {w}" for w in why], ""]
    path = evaluate.REPORTS / f"judge_{day}{'_panel' if source == 'panel' else ''}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    shutil.copy(VERDICTS / f"judge_verdicts_{day}.jsonl", LABELS / f"judge_verdicts_{day}.jsonl")
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(sheet() if sys.argv[1] == "sheet" else agree(*sys.argv[2:4]))
