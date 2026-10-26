"""pdfplumber helpers (D15): language detection, lines, side-by-side columns, page classification. The page reading
itself is in assemble.py (D55). pymupdf only repairs malformed files.
"""
import re
import statistics
from pathlib import Path

import pdfplumber
import pymupdf

from backend.config import ROOT

PARSED_DIR = ROOT / "data" / "parsed"
REPAIRED_DIR = ROOT / "data" / "repaired"

ID_WORDS = set(
    "yang dan dengan untuk pada dari adalah ini dalam tersebut atas oleh sebagai tahun perusahaan juga telah akan"
    " kami serta bagi tidak dapat secara".split()
)
EN_WORDS = set("the and of to in for with is that by as year company also has will which from our were are".split())


def detect_lang(text: str) -> str | None:
    words = re.findall(r"[a-z]+", text.lower())
    i = sum(w in ID_WORDS for w in words)
    e = sum(w in EN_WORDS for w in words)
    if i + e < 6:
        return None
    ratio = i / (i + e)
    return "id" if ratio > 0.65 else "en" if ratio < 0.35 else "mixed"


def open_pdf(path: Path) -> pdfplumber.PDF:
    """pdfplumber cannot read some broken files (e.g. ITMG 2025: 'No /Root object'); pymupdf repairs them."""
    try:
        pdf = pdfplumber.open(path)
        _ = pdf.pages[0]
        return pdf
    except Exception:
        REPAIRED_DIR.mkdir(parents=True, exist_ok=True)
        fixed = REPAIRED_DIR / path.name
        if not fixed.exists():
            with pymupdf.open(path) as doc:
                doc.save(fixed, garbage=3, clean=True)
        return pdfplumber.open(fixed)


def _lines(words: list[dict]) -> list[dict]:
    """Group words into lines by baseline, keep the dominant font size and whether the line is bold."""
    lines: list[list[dict]] = []
    for w in sorted(words, key=lambda w: (round(w["top"]), w["x0"])):
        if lines and abs(lines[-1][0]["top"] - w["top"]) < 3:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = []
    for ws in lines:
        ws.sort(key=lambda w: w["x0"])
        out.append({
            "text": " ".join(w["text"] for w in ws),
            "size": round(statistics.median(w["size"] for w in ws), 1),
            "bold": sum("bold" in w["fontname"].lower() for w in ws) > len(ws) / 2,
            "top": round(ws[0]["top"], 1),
            "x0": round(ws[0]["x0"], 1),
        })
    return out


def _columns(words: list[dict], width: float) -> list[dict]:
    """Split a page into left/right halves when they hold different languages (side-by-side bilingual, D30),
    or when it is a two-column layout; otherwise one column."""
    mid = width / 2
    left = [w for w in words if w["x1"] <= mid + 5]
    right = [w for w in words if w["x0"] >= mid - 5]
    straddling = len(words) - len(left) - len(right)
    if left and right and straddling < 0.05 * len(words):
        ll, rl = detect_lang(" ".join(w["text"] for w in left)), detect_lang(" ".join(w["text"] for w in right))
        cols = [{"lang": ll, "lines": _lines(left)}, {"lang": rl, "lines": _lines(right)}]
        if {ll, rl} == {"id", "en"}:
            for c in cols:
                c["pair"] = True
        return cols
    return [{"lang": detect_lang(" ".join(w["text"] for w in words)), "lines": _lines(words)}]


def classify(page: pdfplumber.page.Page, chars: int, n_tables: int, min_chars: int) -> str:
    area = page.width * page.height
    image_area = sum(max(0, (i["x1"] - i["x0"]) * (i["bottom"] - i["top"])) for i in page.images) / area
    if chars < min_chars:
        return "scanned" if image_area > 0.5 else "image"
    if len(page.curves) + len(page.rects) > 80:  # vector charts and infographics are drawn with many paths
        return "chart"
    if n_tables:
        return "table"
    return "mixed" if image_area > 0.25 else "text"
