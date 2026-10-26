import pymupdf
import pytest

from backend.ingest import ocr


def fake_result(n):
    return {"markdown": {"text": f"page {n}"}, "prunedResult": {"page": n}}


def test_a_crash_after_submitting_resumes_polling_instead_of_paying_again(tmp_path, monkeypatch):
    pdf = tmp_path / "doc.pdf"
    doc = pymupdf.open()
    for _ in range(3):
        doc.new_page()
    doc.save(pdf)
    monkeypatch.setattr(ocr, "OCR_DIR", tmp_path / "ocr")
    submitted = []
    monkeypatch.setattr(ocr, "_submit", lambda data, model: submitted.append(data) or f"job{len(submitted)}")

    def crash(job_id):
        raise ConnectionError("laptop went to sleep")

    monkeypatch.setattr(ocr, "_poll", crash)
    with pytest.raises(ConnectionError):
        ocr.ocr_document("D", pdf, 3)
    assert len(submitted) == 1 and (tmp_path / "ocr" / "D" / "pending.json").exists()

    monkeypatch.setattr(ocr, "_poll", lambda job_id: [fake_result(n) for n in (1, 2, 3)])
    ocr.ocr_document("D", pdf, 3)
    assert len(submitted) == 1  # no second upload
    assert sorted(ocr.load_ocr("D")) == [1, 2, 3]
    assert not (tmp_path / "ocr" / "D" / "pending.json").exists()
