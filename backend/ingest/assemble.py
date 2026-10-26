"""Hybrid page assembly (D55): every page is read twice, by pdfplumber (exact characters, drawn lines) and by
PaddleOCR-VL (regions, labels, reading order). The output keeps the shape chunk.py reads (data/parsed/<doc_id>.json)
plus figures and a per-page quality check.

Rules, each of the form "when a page looks like X, do Y":
- Regions, labels and reading order come from PaddleOCR. Each PDF word goes to the smallest region containing its
  centre (2 pt tolerance). Words in no region form a 'loose' block at the end of the page: nothing is lost.
- A region's text is the PDF's words when it has any; otherwise PaddleOCR's reading, flagged as OCR.
- Headings come only from regions PaddleOCR labels as titles. Running headers, footers and page numbers are dropped.
- Tables: the area is PaddleOCR's box. A ruled table (drawn lines) covering >= 60% of the box gives the grid with
  PDF text; else PaddleOCR's table when its cells hold >= 80% of the box's PDF text (4+-digit numbers the PDF does not
  have are replaced by the one PDF number with the same digits); else whitespace columns inside the box; else the
  box's text, flagged. A box without PDF text (scan) uses PaddleOCR's table. Ruled tables outside every region stay.
- Charts use PaddleOCR's chart-to-table reading, kept only when >= 80% of its numbers are in the PDF's text (the
  image is shown either way). An image region holding >= 8 PDF words is a diagram (its words are the figure's data);
  other images (photos, portraits) are dropped (D56).
- A page without a layout result falls back to the PDF words alone (side-by-side split as before).
"""
import json
import re
import statistics
from collections import Counter
from pathlib import Path

import pymupdf

from backend.config import ROOT, config
from backend.ingest.chunk import table_markdown
from backend.ingest.ocr import _caption, html_table_md
from backend.ingest.parse_pdf import PARSED_DIR, _columns, _lines, classify, detect_lang, open_pdf

QA_DIR = ROOT / "data" / "qa"
DROP = {"header", "footer", "number", "header_image", "footer_image"}
HEADING = {"paragraph_title": "para", "doc_title": "doc"}
FIGURE = {"table", "chart", "image", "seal"}
NUM = re.compile(r"\d[\d.,]{3,}\d")
TOKEN = re.compile(r"[^\W_]+", re.U)


def _area(b) -> float:
    return max(0.0, b[2] - b[0]) * max(0.0, b[3] - b[1])


def _overlap(a, b) -> float:
    return _area((max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])))


def _contains(b, x: float, y: float, tol: float = 2.0) -> bool:
    return b[0] - tol <= x <= b[2] + tol and b[1] - tol <= y <= b[3] + tol


def _tokens(text: str) -> Counter:
    return Counter(t.lower() for t in TOKEN.findall(text))


def _rows_text(rows: list[list[str]]) -> str:
    return " ".join(c for r in rows for c in r)


def _html_rows(html: str) -> list[list[str]]:
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        rows.append([" ".join(re.sub(r"<[^>]+>", " ", c).split()) for c in cells])
    return rows


def share_found(pdf_text: str, other: str) -> float:
    """Share of the PDF's characters (by token) that also appear in `other`."""
    want, have = _tokens(pdf_text), _tokens(other)
    total = sum(len(t) * n for t, n in want.items())
    return sum(len(t) * min(n, have[t]) for t, n in want.items()) / total if total else 0.0


CHART_NUM, YEAR = re.compile(r"\d[\d.,]*\d|\d"), re.compile(r"(19|20)\d\d")
UNVERIFIED_CHART = "(Values read from the chart image could not be checked against the PDF text; see the image.)"


def chart_agreement(md: str, pdf_words: list[str]) -> float | None:
    """Share of a chart reading's numbers that the PDF's own text holds (years skipped: they are axis labels).
    PaddleOCR estimates bars without data labels and invents values for raster charts; those can't be quoted."""
    pdf = {re.sub(r"\D", "", w) for w in pdf_words} - {""}
    nums = [d for n in CHART_NUM.findall(md) if (d := re.sub(r"\D", "", n)) and not YEAR.fullmatch(d)]
    return sum(n in pdf for n in nums) / len(nums) if nums else None


def repair_numbers(rows: list[list[str]], pdf_words: list[str]) -> list[list[str]]:
    """PaddleOCR misreads digits and separators (61.0230 for 61,023.0); the PDF has the exact number."""
    pdf_nums = {w.strip("()") for w in pdf_words if NUM.fullmatch(w.strip("()"))}
    by_digits: dict[str, list[str]] = {}
    for n in pdf_nums:
        by_digits.setdefault(re.sub(r"\D", "", n), []).append(n)

    def fix(m: re.Match) -> str:
        s = m.group(0)
        if s in pdf_nums:
            return s
        same = by_digits.get(re.sub(r"\D", "", s), [])
        return same[0] if len(same) == 1 else s

    return [[NUM.sub(fix, c) for c in r] for r in rows]


def _md(rows: list[list[str]]) -> str:
    return "\n".join(table_markdown(rows))


def _valid_rows(rows) -> list[list[str]] | None:
    rows = [[" ".join((c or "").split()) for c in r] for r in rows or []]
    filled = sum(1 for r in rows for c in r if c)
    if len(rows) >= 2 and max(len(r) for r in rows) >= 2 and filled >= 2:
        return rows
    return None


def leftover_words(words: list[dict], rows: list[list[str]]) -> list[dict]:
    """PDF words of the box whose tokens the chosen table does not hold (kept as text after it: nothing is lost)."""
    have, out = _tokens(_rows_text(rows)), []
    for w in words:
        need = _tokens(w["text"])
        if need and not all(have[t] >= n for t, n in need.items()):
            out.append(w)
        have -= need
    return out


def route_table(page, box, words: list[dict], ruled: list[dict], ocr_html: str) -> dict:
    """One table region -> rows, their source, leftover PDF words and agreement with PaddleOCR's table.

    Candidates: a ruled table covering >= 60% of the box, PaddleOCR's table (numbers repaired from the PDF) and
    whitespace columns inside the box. Each is scored by the share of the box's PDF text it holds; the best wins,
    with ruled > PaddleOCR > whitespace on ties. PaddleOCR's table needs >= 80%, the others >= 50%. A box without PDF
    text (scan) uses PaddleOCR's table as is."""
    pdf_text = " ".join(w["text"] for w in words)
    ocr_rows = _valid_rows(_html_rows(ocr_html)) if "<t" in ocr_html.lower() else None
    if not words:
        if ocr_rows:
            return {"rows": ocr_rows, "text": None, "source": "ocr", "agreement": None, "leftover": []}
        return {"rows": None, "text": " ".join(re.sub(r"<[^>]+>", " ", ocr_html).split()), "source": "text",
                "agreement": None, "leftover": []}
    candidates = []  # (share, preference, source, rows)
    best = max(ruled, key=lambda r: _overlap(r["bbox"], box), default=None)
    if best and _overlap(best["bbox"], box) >= 0.6 * _area(box):
        best["used"] = True  # inside a PaddleOCR table box: never repeated as an unboxed table
        candidates.append((share_found(pdf_text, _rows_text(best["rows"])), 3, "ruled", best["rows"]))
    if ocr_rows:
        fixed = repair_numbers(ocr_rows, [w["text"] for w in words])
        share = share_found(pdf_text, _rows_text(fixed))
        if share >= 0.8:
            candidates.append((share, 2, "ocr_checked", fixed))
    if not candidates or max(c[0] for c in candidates) < 0.97:
        x0, top, x1, bottom = box
        crop = page.crop((max(0, x0 - 1), max(0, top - 1), min(page.width, x1 + 1), min(page.height, bottom + 1)))
        rows = _valid_rows(crop.extract_table({"vertical_strategy": "text", "horizontal_strategy": "text"}))
        if rows:
            candidates.append((share_found(pdf_text, _rows_text(rows)), 1, "whitespace", rows))
    candidates = [c for c in candidates if c[0] >= 0.5]
    if not candidates:
        return {"rows": None, "text": " ".join(pdf_text.split()), "source": "text", "agreement": None, "leftover": []}
    _, _, source, rows = max(candidates, key=lambda c: (round(c[0], 2), c[1]))
    agreement = None
    if ocr_rows and source in ("ruled", "whitespace"):
        a, b = _tokens(_rows_text(rows)), _tokens(_rows_text(ocr_rows))
        agreement = round(sum((a & b).values()) / max(1, sum((a | b).values())), 2)
    return {"rows": rows, "text": None, "source": source, "agreement": agreement,
            "leftover": leftover_words(words, rows)}


def _block_lines(words: list[dict], title: str | None) -> list[dict]:
    lines = _lines(words)
    for i, ln in enumerate(lines):
        ln["title"], ln["break"] = title, i == 0
    return lines


def _ocr_lines(text: str, title: str | None) -> list[dict]:
    out = []
    for i, raw in enumerate(t for t in text.splitlines() if t.strip()):
        out.append({"text": " ".join(raw.lstrip("# ").split()), "size": 10.0, "bold": False, "top": 12.0 * i,
                    "x0": 0.0, "title": title, "break": i == 0, "ocr": True})
    return out


def _split_mixed(words: list[dict], box) -> list[list[dict]]:
    """A region PaddleOCR drew over both halves of a side-by-side ID|EN layout: split it at its middle."""
    mid = (box[0] + box[2]) / 2
    left = [w for w in words if w["x1"] <= mid + 5]
    right = [w for w in words if w["x0"] >= mid - 5]
    if left and right and len(left) + len(right) >= 0.95 * len(words):
        langs = {detect_lang(" ".join(w["text"] for w in ws)) for ws in (left, right)}
        if langs == {"id", "en"}:
            return [left, right]
    return [words]


def assemble_page(page, n: int, ocr: dict | None, min_chars: int) -> dict:
    # Pages cut from a spread keep the facing page's text outside the visible box; it would be cited on this page.
    page = page.within_bbox(page.bbox)
    words = page.dedupe_chars().extract_words(extra_attrs=["size", "fontname"], keep_blank_chars=False)
    total = sum(len(w["text"]) for w in words)
    ruled = [{"bbox": t.bbox, "rows": r} for t in page.find_tables() if (r := _valid_rows(t.extract()))]
    base = {"page_no": n, "chars": total, "size": [round(page.width, 1), round(page.height, 1)],
            "kind": classify(page, total, len(ruled), min_chars)}
    if not ocr:  # no layout result: the previous PDF-only reading
        return {**base, "parser": "pdfplumber", "columns": _columns(words, page.width) if words else [],
                "figures": [{"kind": "table", "bbox": list(t["bbox"]), "rows": t["rows"], "source": "ruled",
                             "agreement": None, "caption": None, "md": _md(t["rows"])} for t in ruled],
                "qa": {"coverage": 1.0, "flags": ["no_layout"]}}

    pr = ocr["pruned"]
    sx, sy = page.width / pr["width"], page.height / pr["height"]
    scores = {tuple(b["coordinate"]): b["score"] for b in pr["layout_det_res"]["boxes"]}
    blocks = []
    for b in pr["parsing_res_list"]:
        x0, top, x1, bottom = b["block_bbox"]
        blocks.append({**b, "box": (x0 * sx, top * sy, x1 * sx, bottom * sy), "words": [],
                       "score": scores.get(tuple(b["block_bbox"]))})
    loose = []
    for w in words:  # smallest region containing the word's centre
        cx, cy = (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2
        inside = [b for b in blocks if _contains(b["box"], cx, cy)]
        (min(inside, key=lambda b: _area(b["box"]))["words"] if inside else loose).append(w)

    units: list[tuple[str | None, list[dict]]] = []  # (lang, lines) in reading order
    figures, flags, dropped, leftover, ocr_text = [], [], 0, 0, False
    for b in blocks:
        label, bw, content = b["block_label"], b["words"], b["block_content"] or ""
        if label in DROP:
            continue
        if label == "table":
            t = route_table(page, b["box"], bw, ruled, content)
            if t["rows"]:
                figures.append({"kind": "table", "bbox": list(b["box"]), "rows": t["rows"], "source": t["source"],
                                "agreement": t["agreement"], "score": b["score"], "block": b, "md": _md(t["rows"])})
            if t["leftover"]:
                units.append((detect_lang(" ".join(w["text"] for w in t["leftover"])),
                              _block_lines(t["leftover"], None)))
                left = sum(len(w["text"]) for w in t["leftover"])
                leftover += left
                if left > 0.1 * sum(len(w["text"]) for w in bw):
                    flags.append("table_leftover")
            elif t["text"]:
                units.append((detect_lang(t["text"]), _ocr_lines(t["text"], None)))
                flags.append("table_as_text")
            ocr_text |= t["source"] == "ocr"
            continue
        if label == "chart":
            md = html_table_md(content) if "<t" in content.lower() else content.strip()
            if md:
                inside = [w["text"] for w in words
                          if _contains(b["box"], (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2, tol=6.0)]
                agreement = chart_agreement(md, inside)
                if agreement is not None and agreement < 0.8:  # same bar as OCR tables (D55); the image still shows
                    md = UNVERIFIED_CHART
                    if "chart_unverified" not in flags:
                        flags.append("chart_unverified")
                figures.append({"kind": "chart", "bbox": list(b["box"]), "rows": None, "source": "ocr_chart",
                                "agreement": agreement, "score": b["score"], "block": b, "md": md})
            continue
        if label in FIGURE:  # image / seal: a diagram when the PDF has text inside it, else a photo (dropped)
            if len(bw) >= 8:
                data = "\n".join(ln["text"] for ln in _lines(bw))
                figures.append({"kind": "diagram", "bbox": list(b["box"]), "rows": None, "source": "pdf",
                                "agreement": None, "score": b["score"], "block": b, "md": data})
            else:
                dropped += sum(len(w["text"]) for w in bw)
            continue
        title = HEADING.get(label)
        if bw:
            for part in _split_mixed(bw, b["box"]):
                units.append((detect_lang(" ".join(w["text"] for w in part)), _block_lines(part, title)))
        elif content.strip():
            units.append((detect_lang(content), _ocr_lines(content, title)))
            ocr_text = True
    for t in ruled:  # ruled tables no region covered: kept, and their words leave the loose block
        mine = [w for w in loose if _contains(t["bbox"], (w["x0"] + w["x1"]) / 2, (w["top"] + w["bottom"]) / 2)]
        if not t.get("used") and len(mine) >= 4:
            loose = [w for w in loose if w not in mine]
            figures.append({"kind": "table", "bbox": list(t["bbox"]), "rows": t["rows"], "source": "ruled_unboxed",
                            "agreement": None, "score": None, "block": None, "md": _md(t["rows"])})
    if loose:
        units.append((detect_lang(" ".join(w["text"] for w in loose)), _block_lines(loose, None)))
        if sum(len(w["text"]) for w in loose) > 0.2 * max(total, 1):
            flags.append("loose_text")

    columns = _group_languages(units)
    coverage = round(1 - dropped / total, 3) if total else 1.0
    if total and coverage < 0.97:
        flags.append("low_coverage")
    if ocr_text and not words:
        flags.append("ocr_only")
    if any(f["agreement"] is not None and f["agreement"] < 0.5 for f in figures):
        flags.append("table_disagrees")
    return {**base, "parser": "hybrid", "columns": columns, "figures": figures,
            "qa": {"coverage": coverage, "flags": flags, "table_leftover_chars": leftover,
                   "tables": [{"source": f["source"], "agreement": f["agreement"]} for f in figures
                              if f["kind"] == "table"]}}


def _group_languages(units: list[tuple[str | None, list[dict]]]) -> list[dict]:
    """One column per language in reading order; short or mixed units join the language around them. Pages with
    substantial ID and EN text are side-by-side bilingual and pair their chunks (D30)."""
    known = [lang if lang in ("id", "en") else None for lang, _ in units]
    for i, lang in enumerate(known):
        if lang is None:
            known[i] = next((x for x in known[i::-1] if x), None) or next((x for x in known[i:] if x), None)
    cols: dict[str, list[dict]] = {}
    for lang, (_, lines) in zip(known, units, strict=True):
        cols.setdefault(lang or "und", []).extend(lines)
    words = {k: sum(len(ln["text"].split()) for ln in v) for k, v in cols.items()}
    pair = words.get("id", 0) >= 30 and words.get("en", 0) >= 30
    return [{"lang": None if k == "und" else k, "lines": v, **({"pair": True} if pair and k != "und" else {})}
            for k, v in cols.items()]


def assemble(doc_id: str, ticker: str, year: int, pdf_path: Path, ocr_pages: dict[int, dict]) -> tuple[dict, list]:
    """Whole document -> (parsed, figures); writes data/parsed/<doc_id>.json and data/qa/<doc_id>.json."""
    min_chars = config()["parsing"]["min_text_chars"]
    with pymupdf.open(pdf_path) as doc:
        toc = [{"level": lvl, "title": " ".join(title.split()), "page": pg} for lvl, title, pg in doc.get_toc()]
    pages, figures, yy = [], [], str(year)[-2:]
    with open_pdf(pdf_path) as pdf:
        for n, page in enumerate(pdf.pages, start=1):
            p = assemble_page(page, n, ocr_pages.get(n), min_chars)
            counts: dict[str, int] = {}
            raw = ocr_pages.get(n, {}).get("pruned", {}).get("parsing_res_list", [])
            for f in p.pop("figures"):
                letter = {"table": "t", "chart": "c", "diagram": "d"}[f["kind"]]
                counts[letter] = counts.get(letter, 0) + 1
                block = f.get("block")
                figures.append({
                    "figure_id": f"{ticker}-{yy}-p{n}-{letter}{counts[letter]}", "doc_id": doc_id, "page_no": n,
                    "kind": f["kind"], "bbox": [round(v, 1) for v in f["bbox"]],
                    "caption": _caption(raw, block["block_bbox"]) if block else None,
                    "chart_table_md": f["md"], "ocr_confidence": f.get("score"), "source": f["source"],
                    "agreement": f.get("agreement"),
                })
            pages.append(p)
            page.flush_cache()
    parsed = {"doc_id": doc_id, "parser": "hybrid", "toc": toc, "pages": pages}
    PARSED_DIR.mkdir(parents=True, exist_ok=True)
    (PARSED_DIR / f"{doc_id}.json").write_text(json.dumps(parsed, ensure_ascii=False), encoding="utf-8")
    write_qa(doc_id, pages)
    return parsed, figures


def write_qa(doc_id: str, pages: list[dict]) -> dict:
    flagged = {p["page_no"]: p["qa"]["flags"] for p in pages if p["qa"]["flags"]}
    agreements = [t["agreement"] for p in pages for t in p["qa"].get("tables", []) if t["agreement"] is not None]
    summary = {
        "doc_id": doc_id, "pages": len(pages),
        "coverage_mean": round(statistics.mean(p["qa"]["coverage"] for p in pages), 4) if pages else None,
        "flag_counts": dict(Counter(f for fs in flagged.values() for f in fs)),
        "table_sources": dict(Counter(t["source"] for p in pages for t in p["qa"].get("tables", []))),
        "table_agreement_mean": round(statistics.mean(agreements), 3) if agreements else None,
        "flagged_pages": flagged,
    }
    QA_DIR.mkdir(parents=True, exist_ok=True)
    (QA_DIR / f"{doc_id}.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    return summary
