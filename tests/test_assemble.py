from backend.ingest.assemble import _group_languages, repair_numbers, share_found
from backend.ingest.chunk import heading_level, paragraphs


def test_ocr_table_accepted_only_when_it_holds_the_pdf_text():
    pdf = "Revenue Pendapatan 1,874 Net Profit Laba Bersih 490"
    assert share_found(pdf, "Revenue | Pendapatan | 1,874 | Net Profit | Laba Bersih | 490") == 1.0
    assert share_found(pdf, "Revenue | 1,874") < 0.8


def test_misread_numbers_are_repaired_from_the_pdf():
    rows = [["Total", "61.0230"], ["Kas", "12,345"]]
    assert repair_numbers(rows, ["61,023.0", "12,345"]) == [["Total", "61,023.0"], ["Kas", "12,345"]]


def test_ambiguous_numbers_are_left_alone():
    rows = [["x", "1.234"]]
    assert repair_numbers(rows, ["1,234", "12.34"]) == rows  # two PDF numbers share the digits


def line(text, title=None, brk=False, size=10.0):
    return {"text": text, "size": size, "bold": False, "top": 0.0, "x0": 0.0, "title": title, "break": brk}


def test_side_by_side_languages_pair_and_short_units_follow_their_neighbours():
    id_text = "Perseroan mencatat laba yang dapat diatribusikan kepada pemilik dan dengan ini " * 4
    en_text = "The company recorded profit that is attributable to the owners and with this " * 4
    cols = _group_languages([(None, [line("Ikhtisar")]), ("id", [line(id_text)]), ("en", [line(en_text)])])
    assert [c["lang"] for c in cols] == ["id", "en"]
    assert all(c.get("pair") for c in cols)
    assert cols[0]["lines"][0]["text"] == "Ikhtisar"


def test_only_layout_titles_are_headings():
    assert heading_level(line("Financial Review", title="para"), 10.0) == 2
    assert heading_level(line("Financial Review", title="doc"), 10.0) == 1
    assert heading_level(line("Big but not a title", size=30.0), 10.0) == 0  # layout page, no title region
    assert heading_level({"text": "Big heading", "size": 30.0, "bold": False}, 10.0) == 1  # no layout: by size


def test_a_new_region_starts_a_new_paragraph():
    units = paragraphs([line("First region text.", brk=True), line("Second region text.", brk=True)], 10.0)
    assert [u[0] for u in units] == ["First region text.", "Second region text."]


def test_unwarped_layout_results_are_not_trusted():
    from backend.ingest.ocr import aligned

    warped = {"pruned": {"doc_preprocessor_res": {"model_settings": {"use_doc_unwarping": True}}}}
    flat = {"pruned": {"doc_preprocessor_res": {"model_settings": {"use_doc_unwarping": False}}}}
    assert not aligned(warped) and aligned(flat) and aligned({"pruned": {}})


def test_text_outside_the_visible_page_is_ignored():
    import io

    import pdfplumber
    import pymupdf

    from backend.ingest.assemble import assemble_page

    doc = pymupdf.open()
    page = doc.new_page(width=300, height=400)
    page.insert_text((20, 50), "Visible words on this page")
    page.insert_text((320, 50), "Facing page words")  # beyond the right edge, as in a cut spread
    with pdfplumber.open(io.BytesIO(doc.tobytes())) as pdf:
        out = assemble_page(pdf.pages[0], 1, None, 10)
    text = " ".join(line["text"] for col in out["columns"] for line in col["lines"])
    assert "Visible" in text and "Facing" not in text


def test_chart_values_count_only_when_the_pdf_text_has_them():
    from backend.ingest.assemble import chart_agreement

    md = "| Year | Laba |\n| --- | --- |\n| 2024 | 48,639 |\n| 2025 | 54,836 |"
    assert chart_agreement(md, ["2024", "2025", "48.639", "54.836"]) == 1.0  # separators differ, digits match
    invented = "| Category | Value |\n| --- | --- |\n| Category 1 | 100 |\n| Category 2 | 75 |"
    assert chart_agreement(invented, []) < 0.8
    assert chart_agreement("| Year |\n| --- |\n| 2025 |", ["2025"]) is None  # nothing to verify: years only
