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
