"""Hosted PaddleOCR (D47) layout for every page (D55). Resumable: one cached result per job.

Jobs hold <= parsing.ocr_max_pages_per_job pages (the API ignores pages beyond 100) and <= ocr_max_job_mb. The
sub-PDF for a job is built with pymupdf from the original pages; results land in data/ocr/<doc_id>/job_<k>.json
with the page mapping.
"""
import json
import re
import time
from pathlib import Path

import pymupdf
import requests

from backend.config import ROOT, config, env
from backend.net import retry

OCR_DIR = ROOT / "data" / "ocr"

def _submit(pdf_bytes: bytes, model: str) -> str:
    r = retry(lambda: requests.post(
        env("PADDLEOCR_API_URL"),
        headers={"Authorization": f"bearer {env('PADDLEOCR_API_KEY')}"},
        files={"file": ("pages.pdf", pdf_bytes, "application/pdf")},
        # Unwarping and orientation fixes are for photographed paper; on a PDF they move the boxes off the PDF's own
        # coordinates, which the hybrid assembly (D55) relies on.
        data={"model": model, "optionalPayload": json.dumps(
            {"useLayoutDetection": True, "useChartRecognition": True, "useDocUnwarping": False,
             "useDocOrientationClassify": False, "temperature": 0})},
        timeout=300,
    ))
    if r.status_code == 429:
        raise OCRQuotaExceeded("PaddleOCR daily page quota reached; re-run tomorrow (cached pages are kept)")
    r.raise_for_status()
    return r.json()["data"]["jobId"]


def _poll(job_id: str, timeout_s: int = 3600) -> list[dict]:
    url, headers = f"{env('PADDLEOCR_API_URL')}/{job_id}", {"Authorization": f"bearer {env('PADDLEOCR_API_KEY')}"}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        d = retry(lambda: requests.get(url, headers=headers, timeout=60)).json()["data"]
        if d["state"] == "done":
            text = retry(lambda u=d["resultUrl"]["jsonUrl"]: requests.get(u, timeout=300)).text
            lines = [json.loads(line) for line in text.strip().splitlines()]
            return [res for line in lines for res in line["result"]["layoutParsingResults"]]
        if d["state"] == "failed":
            raise RuntimeError(f"OCR job {job_id} failed: {d.get('errorMsg')}")
        time.sleep(10)
    raise TimeoutError(f"OCR job {job_id} still running after {timeout_s}s")


class OCRQuotaExceeded(RuntimeError):
    """HTTP 429 from the OCR service: stop the run, resume from the cache another day."""


def _sub_pdf(src: pymupdf.Document, pages: list[int]) -> bytes:
    sub = pymupdf.open()
    for n in pages:
        sub.insert_pdf(src, from_page=n - 1, to_page=n - 1)
    data = sub.tobytes(garbage=3, deflate=True)
    sub.close()
    return data


def _page_image_pdf(src: pymupdf.Document, n: int) -> bytes:
    """A single page too large to upload (huge embedded images), re-drawn as one JPEG at the OCR's 144 dpi."""
    page = src[n - 1]
    pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
    out = pymupdf.open()
    out.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect,
                                                                               stream=pix.tobytes("jpeg", 80))
    data = out.tobytes(deflate=True)
    out.close()
    return data


def _jobs(src: pymupdf.Document, pages: list[int], max_pages: int, max_bytes: int) -> list[tuple[list[int], bytes]]:
    """Split pages into uploads of <= max_pages and <= max_bytes, halving a batch until it fits."""
    out, todo = [], [pages[k : k + max_pages] for k in range(0, len(pages), max_pages)]
    while todo:
        batch = todo.pop(0)
        data = _sub_pdf(src, batch)
        if len(data) <= max_bytes:
            out.append((batch, data))
        elif len(batch) > 1:
            todo[:0] = [batch[: len(batch) // 2], batch[len(batch) // 2 :]]
        else:
            out.append((batch, _page_image_pdf(src, batch[0])))
    return out


def ocr_document(doc_id: str, pdf_path: Path, n_pages: int) -> list[Path]:
    """Layout for every page (D55). Pages already in the cache (any earlier job file) are not sent again. Submit
    every job first (the service runs them in parallel), then collect."""
    cfg = config()["parsing"]
    out_dir = OCR_DIR / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    # Submitted-but-uncollected jobs survive a crash here, so a re-run polls them instead of paying for the pages again.
    pending_file = out_dir / "pending.json"
    pending = {out_dir / name: (job_id, batch) for name, (job_id, batch) in
               (json.loads(pending_file.read_text(encoding="utf-8")) if pending_file.exists() else {}).items()}
    done = set(load_ocr(doc_id)) | {n for _, batch in pending.values() for n in batch}
    pages = [n for n in range(1, n_pages + 1) if n not in done]
    next_k = len(list(out_dir.glob("job_*.json"))) + len(pending)
    with pymupdf.open(pdf_path) as src:
        for k, (batch, data) in enumerate(_jobs(src, pages, cfg["ocr_max_pages_per_job"],
                                                int(cfg["ocr_max_job_mb"] * 1024**2)), start=next_k):
            pending[out_dir / f"job_{k:03d}.json"] = (_submit(data, cfg["ocr_model"]), batch)
            _save_pending(pending_file, pending)
    for out, (job_id, batch) in list(pending.items()):
        try:
            results = _poll(job_id)
        except RuntimeError:  # the service failed the job: forget it, so a re-run submits those pages again
            del pending[out]
            _save_pending(pending_file, pending)
            raise
        if len(results) != len(batch):
            raise RuntimeError(f"{doc_id}: OCR returned {len(results)} pages for a {len(batch)}-page job")
        # The page images expire with the job; keep only what later steps read.
        keep = [{"page_no": n, "markdown": r["markdown"]["text"], "pruned": r["prunedResult"]}
                for n, r in zip(batch, results, strict=True)]
        out.write_text(json.dumps({"job_id": job_id, "pages": keep}, ensure_ascii=False), encoding="utf-8")
        del pending[out]
        _save_pending(pending_file, pending)
    return sorted(out_dir.glob("job_*.json"))


def _save_pending(path: Path, pending: dict[Path, tuple[str, list[int]]]) -> None:
    if pending:
        path.write_text(json.dumps({p.name: v for p, v in pending.items()}), encoding="utf-8")
    else:
        path.unlink(missing_ok=True)


def aligned(page: dict) -> bool:
    """False for results read with document unwarping (early jobs): their boxes don't match PDF coordinates."""
    settings = (page["pruned"].get("doc_preprocessor_res") or {}).get("model_settings", {})
    return not settings.get("use_doc_unwarping")


def load_ocr(doc_id: str) -> dict[int, dict]:
    """Page -> layout result; later jobs win, unaligned results are ignored."""
    pages = {}
    for f in sorted((OCR_DIR / doc_id).glob("job_*.json")):
        for p in json.loads(f.read_text(encoding="utf-8"))["pages"]:
            if aligned(p):
                pages[p["page_no"]] = p
    return pages


CROPS_DIR = ROOT / "data" / "crops"
CROP_KINDS = {"chart", "diagram"}


def render_crops(doc_id: str, pdf_path: Path, figures: list[dict]) -> int:
    """WebP crop per chart or diagram (D56); tables are text. Sets figure['storage_path']. Always re-rendered: a
    figure id can name a different box after re-parsing."""
    from PIL import Image

    cfg = config()["parsing"]
    out_dir = CROPS_DIR / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    made = 0
    with pymupdf.open(pdf_path) as doc:
        for f in figures:
            if f["kind"] not in CROP_KINDS:
                f["storage_path"] = None
                continue
            f["storage_path"] = f"{doc_id}/{f['figure_id']}.webp"
            out = CROPS_DIR / f["storage_path"]
            page = doc[f["page_no"] - 1]
            x0, top, x1, bottom = f["bbox"]
            clip = pymupdf.Rect(x0 - 4, top - 4, x1 + 4, bottom + 4) & page.rect
            width, quality = cfg["crop_max_width"], 70
            zoom = min(width / max(clip.width, 1), 4.0)
            try:
                pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
                img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                img.save(out, "WEBP", quality=quality, method=4)
                made += 1
            except (MemoryError, RuntimeError) as e:  # e.g. a page embedding a gigantic image
                print(f"  no crop for {f['figure_id']}: {type(e).__name__}: {e}")
                f["storage_path"] = None
    return made


TITLE_LABELS = {"figure_title", "chart_title", "table_title", "paragraph_title", "doc_title"}


def html_table_md(html: str) -> str:
    """OCR tables arrive as HTML; flatten to a markdown table (no colspan handling: cells are kept in order)."""
    rows = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S | re.I):
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)
        rows.append([" ".join(re.sub(r"<[^>]+>", " ", c).split()) for c in cells])
    if not rows:
        return " ".join(re.sub(r"<[^>]+>", " ", html).split())
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    lines = ["| " + " | ".join(c.replace("|", "/") for c in r) + " |" for r in rows]
    return "\n".join(lines[:1] + ["|" + " --- |" * width] + lines[1:])


def _caption(blocks: list[dict], bbox: list[float]) -> str | None:
    """Nearest title-like block just above or below the figure (§6.1)."""
    x0, top, x1, bottom = bbox
    best, best_gap = None, 150.0
    for b in blocks:
        if b["block_label"] not in TITLE_LABELS or not b["block_content"].strip():
            continue
        bx0, btop, bx1, bbottom = b["block_bbox"]
        if bx1 < x0 or bx0 > x1:
            continue
        gap = top - bbottom if bbottom <= top else btop - bottom if btop >= bottom else None
        if gap is not None and 0 <= gap < best_gap:
            best, best_gap = " ".join(b["block_content"].split()), gap
    return best
