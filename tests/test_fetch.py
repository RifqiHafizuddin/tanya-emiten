import pymupdf

from backend.ingest.fetch import BLOCKED_HOSTS, Polite, links, looks_like_annual_report, score_report_pdf


def make_pdf(path, cover: str, inside: str):
    doc = pymupdf.open()
    for i in range(90):
        doc.new_page().insert_text((72, 72), cover if i == 0 else inside if i >= 2 else "")
    doc.save(path)
    return path


def test_a_sustainability_report_that_mentions_the_annual_report_is_rejected(tmp_path):
    sr = make_pdf(tmp_path / "sr.pdf", "Laporan Keberlanjutan 2025 Sustainability Report", "see Laporan Tahunan 2025")
    ar = make_pdf(tmp_path / "ar.pdf", "Laporan Tahunan 2025 Annual Report", "Sustainability Report 2025")
    assert not looks_like_annual_report(sr, 2025)
    assert looks_like_annual_report(ar, 2025)


def test_links_resolves_relative_and_skips_mailto():
    html = '<a href="/ir/ar.html">Annual <b>Report</b></a><a href="mailto:x@y.z">mail</a>'
    assert links(html, "https://example.com/home") == [("https://example.com/ir/ar.html", "Annual Report")]


def test_scores_full_annual_report_pdf():
    assert score_report_pdf("https://x.com/misc/AR/AR2025-EN.pdf", "Annual Report 2025", 2025) > 0
    assert score_report_pdf("https://x.com/files/ITM_Annual%20Report_2025_full.pdf", "", 2025) > 0
    assert score_report_pdf("https://x.com/laporan-tahunan-2025.pdf", "Laporan Tahunan", 2025) > 0


def test_rejects_wrong_year_non_pdf_and_other_reports():
    assert score_report_pdf("https://x.com/AR2024.pdf", "Annual Report 2024", 2025) == 0
    assert score_report_pdf("https://x.com/annual-report-2025", "Annual Report 2025", 2025) == 0
    assert score_report_pdf("https://x.com/SR2025.pdf", "Sustainability Report 2025", 2025) == 0
    assert score_report_pdf("https://x.com/FY25-public-expose-2025.pdf", "Public Expose 2025", 2025) == 0


def test_idx_is_never_fetched():
    assert "www.idx.co.id" in BLOCKED_HOSTS
    assert Polite().allowed("https://www.idx.co.id/robots.txt") is False
