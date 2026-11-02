import json

from backend.evaluate import GOLDEN, gains, retrieval_metrics

ITEM = {"expected_doc": "X-AR-2025", "expected_pages": [10, 11]}


def hit(doc, start, end=None):
    return {"doc_id": doc, "page_start": start, "page_end": end or start}


def test_gains_count_each_expected_page_once():
    hits = [hit("Y-AR-2025", 10), hit("X-AR-2025", 9), hit("X-AR-2025", 10), hit("X-AR-2025", 10), hit("X-AR-2025",
                                                                                                   11, 12)]
    assert gains(hits, ITEM) == [0, 0, 1, 0, 1]


def test_metrics_perfect_and_miss():
    m = retrieval_metrics([(ITEM, [1, 1, 0]), (ITEM, [0, 0, 0])])
    assert m["recall@4"] == 0.5
    assert m["mrr"] == 0.5
    assert m["ndcg@4"] == 0.5


def test_golden_set_meets_the_mvp1_mix():
    rows = [json.loads(line) for line in GOLDEN.open(encoding="utf-8")]
    kinds = [r["type"] for r in rows]
    assert len(rows) >= 80
    assert sum(r["lang"] == "id" for r in rows) / len(rows) >= 0.3
    assert kinds.count("table") + kinds.count("chart") >= 15
    assert kinds.count("unanswerable") >= 10 and kinds.count("advice") >= 10
    assert len({t for r in rows for t in r["tickers"]}) >= 20
    assert all(r["expected_pages"] for r in rows if r["type"] in ("fact", "table", "chart"))


def test_judge_sample_is_seeded_and_skips_advice_and_the_answer_text_shows_quotes_and_citations():
    from backend import judge

    a, b = judge.sample(), judge.sample()
    assert [i["id"] for i in a] == [i["id"] for i in b] and len(a) == judge.SAMPLE
    assert all(i["type"] != "advice" for i in a)
    out = {"refusal": False, "claims": [{"text": "NIM was 5.7%.", "ticker": "BBCA", "doc_id": "BBCA-AR-2025",
                                         "page": 16, "quote": "NIM 5,7%"}]}
    assert judge.answer_text(out) == '1. NIM was 5.7%.\n   quote (BBCA FY2025 p.16): "NIM 5,7%"'
    assert judge.answer_text({"refusal": True, "refusal_reason": "Not in the report."}) == "REFUSED: Not in the report."


def test_owner_labels_read_in_any_excel_locale_and_bad_values_are_named(tmp_path):
    import pytest

    from backend import judge

    head = "id;question;owner_supported (yes/no/n/a);owner_correct (yes/no);owner_note\n"
    path = tmp_path / "labels.csv"
    path.write_bytes((head + "g001;Laba é?;NA;Yes;\ng002;x;no;no;\n").encode("cp1252"))
    rows = judge.read_labels(path)
    assert rows["g001"]["owner_supported (yes/no/n/a)"] == "n/a" and rows["g001"]["owner_correct (yes/no)"] == "yes"
    path.write_text(head + "g003;x;ya;yes;\n", encoding="utf-8")
    with pytest.raises(ValueError, match="g003 supported='ya'"):
        judge.read_labels(path)


def test_kappa_is_zero_for_a_judge_that_always_says_yes():
    from backend.judge import kappa

    assert kappa([("yes", "yes")] * 9 + [("yes", "no")]) == 0.0
    assert kappa([("yes", "yes"), ("no", "no")]) == 1.0
