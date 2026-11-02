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


def test_ticker_shaped_words_outside_lq45_are_flagged_but_acronyms_and_shouting_are_not():
    assert understand("whats your take on DOID?").unknown == ["DOID"]
    assert understand("BBCA vs DOID").unknown == ["DOID"]
    assert understand("Berapa rasio CASA BBCA?").unknown == []  # finance acronym
    assert understand("WHAT IS BBCA NPL").unknown == []  # all caps: every word would look like a ticker


def test_possessive_names_resolve_with_or_without_apostrophe():
    assert understand("what do you think of GOTOs projection").tickers == ["GOTO"]
    assert understand("What is GOTO's revenue?").tickers == ["GOTO"]
    assert understand("Alfamart’s store count").tickers == ["AMRT"]


def test_outlook_questions_search_outlook_vocabulary_and_drop_opinion_words():
    q = understand("what do you think of GOTOs projection")
    assert q.tickers == ["GOTO"] and {"outlook", "prospek", "targets", "2026"} <= set(q.terms)
    assert not {"you", "think"} & set(q.terms)
    assert "outlook" not in understand("Berapa laba bersih BBCA?").terms
    assert "outlook" not in understand("targeted marketing spend").terms
