from backend.answer import ADVICE, Answer, Claim, FigureRef, data_blocks, normalize, verify

HITS = [
    {"chunk_id": "BBRI-AR-2025-00010", "figure_id": None, "kind": "text",
     "context": "[BBRI | Annual Report | FY2025 | MD&A | p.88]\nCost of credit rose to 3.2% in 2025 as the bank "
                "built provisions for the micro seg-\nment."},
    {"chunk_id": "BBRI-AR-2025-00200", "figure_id": "BBRI-25-p212-c1", "kind": "chart",
     "context": "[FIGURE BBRI-25-p212-c1 | chart]\nData: | Year | NPL |"},
]


def answer(*claims, figures=(), lang="en"):
    return Answer(lang=lang, refusal=False, claims=list(claims), figures=list(figures))


def test_verbatim_quote_passes_with_whitespace_and_hyphenation_normalised():
    c = Claim(text="Credit cost rose to 3.2% in 2025.", chunk_ids=["BBRI-AR-2025-00010"],
              quote="Cost of credit rose to 3.2% in 2025 as the bank built provisions for the micro segment")
    kept, _, errors = verify(answer(c), HITS, "en")
    assert kept == [c] and errors == []


def test_paraphrased_quote_is_dropped():
    c = Claim(text="Credit cost increased.", chunk_ids=["BBRI-AR-2025-00010"], quote="credit costs went up a lot")
    kept, _, errors = verify(answer(c), HITS, "en")
    assert kept == [] and "not an exact substring" in errors[0]


def test_number_outside_quote_is_dropped():
    c = Claim(text="Credit cost rose to 4.5% in 2025.", chunk_ids=["BBRI-AR-2025-00010"],
              quote="Cost of credit rose to 3.2% in 2025")
    kept, _, errors = verify(answer(c), HITS, "en")
    assert kept == [] and "4.5" in errors[0]


def test_unknown_chunk_and_figure_are_rejected():
    c = Claim(text="x", chunk_ids=["NOPE"], quote="Cost of credit")
    _, figs, errors = verify(answer(c, figures=[FigureRef(figure_id="BBRI-25-p999-c1", why="w")]), HITS, "en")
    assert figs == [] and len(errors) == 2


def test_retrieved_figure_is_kept():
    _, figs, _ = verify(answer(figures=[FigureRef(figure_id="BBRI-25-p212-c1", why="NPL trend")]), HITS, "en")
    assert [f.figure_id for f in figs] == ["BBRI-25-p212-c1"]


def test_wrong_language_is_flagged():
    c = Claim(text="Credit cost rose.", chunk_ids=["BBRI-AR-2025-00010"], quote="Cost of credit rose")
    _, _, errors = verify(answer(c, lang="en"), HITS, "id")
    assert any("language" in e for e in errors)


def test_advice_requests_are_detected_in_both_languages():
    for q in ["Should I buy BBRI now?", "Apakah BBCA layak dibeli?", "What is the target price of TLKM?",
              "Is UNVR undervalued?", "sebaiknya beli atau jual ANTM?"]:
        assert ADVICE.search(q), q
    for q in ["Why did BBRI's credit cost rise?", "Apa strategi digital BBCA?"]:
        assert not ADVICE.search(q), q


def test_normalize_handles_typographic_quotes():
    assert normalize("BRI’s “micro”  segment") == normalize("BRI's \"micro\" segment")


def test_a_figure_named_by_its_chunk_id_maps_to_its_alias():
    _, figs, errors = verify(answer(figures=[FigureRef(figure_id="BBRI-AR-2025-00200", why="w")]), HITS, "en")
    assert [f.figure_id for f in figs] == ["BBRI-25-p212-c1"]


def test_tables_have_no_image_so_they_are_not_figures():
    table = {**HITS[1], "chunk_id": "BBRI-AR-2025-00300", "figure_id": "BBRI-25-p100-t1", "kind": "table",
             "ticker": "BBRI", "page_start": 100}
    _, figs, errors = verify(answer(figures=[FigureRef(figure_id="BBRI-25-p100-t1", why="w")]), HITS + [table], "en")
    assert not figs and errors
    assert '<chunk id="BBRI-AR-2025-00300"' in data_blocks([table])


def test_figures_without_claims_are_not_an_answer():
    _, _, errors = verify(answer(figures=[FigureRef(figure_id="BBRI-25-p212-c1", why="w")]), HITS, "en")
    assert any("no claims" in e for e in errors)
