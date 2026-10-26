from backend.retrieval import _tsquery, rrf, understand


def test_aliases_resolve_tickers_and_short_names():
    q = understand("Why did BRI's credit costs rise compared to Bank Mandiri in 2025?")
    assert q.tickers == ["BMRI", "BBRI"] or sorted(q.tickers) == ["BBRI", "BMRI"]
    assert q.years == [2025]
    assert q.lang == "en"


def test_longest_alias_wins():
    assert understand("strategi Indofood CBP untuk mi instan").tickers == ["ICBP"]
    assert understand("Indofood Sukses Makmur revenue").tickers == ["INDF"]


def test_ticker_symbols_and_bahasa():
    q = understand("Apa strategi digital BBCA dan bagaimana dampaknya?")
    assert q.tickers == ["BBCA"]
    assert q.lang == "id"


def test_no_company_named_and_default_year():
    q = understand("Which companies mention nickel downstreaming?")
    assert q.tickers == []
    assert q.years == [2025]


def test_rrf_rewards_agreement():
    ranked = rrf(["a", "b", "c"], ["b", "a", "d"], k=60)
    assert [c for c, _ in ranked][:2] in (["a", "b"], ["b", "a"])
    assert dict(ranked)["d"] < dict(ranked)["a"]


def test_company_names_are_a_filter_not_search_terms():
    q = understand("What net profit did Alamtri Resources (ADRO) report for 2025?")
    assert q.tickers == ["ADRO"] and "alamtri" not in q.terms and "adro" not in q.terms and "profit" in q.terms


def test_letter_digit_terms_also_match_the_spaced_form():
    assert _tsquery(["cet1", "ratio"]) == "(cet1 | cet <-> 1) | ratio"
