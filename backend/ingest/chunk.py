"""Section-aware chunking (D29, D30, §6.2).

Text chunks: 300-450 tokens (e5 tokenizer), split at paragraph then sentence boundaries, never across a heading,
~50-token overlap inside a section, may cross a page break. Tables become their own chunks (split by rows with the
header repeated). Side-by-side ID|EN pages yield one stream per language; chunks from such pages share a pair_id.
Every chunk starts with a contextual header line built from metadata.
"""
import json
import re
import statistics
from functools import cache

from tokenizers import Tokenizer

from backend.config import ROOT, config

CHUNKS_DIR = ROOT / "data" / "chunks"
SENTENCE = re.compile(r"(?<=[.!?;])\s+(?=[A-Z0-9\"“(])")


@cache
def tokenizer() -> Tokenizer:
    return Tokenizer.from_pretrained(config()["embedding"]["model"])


def ntok(text: str) -> int:
    return len(tokenizer().encode(text, add_special_tokens=False).ids)


def toc_paths(toc: list[dict], n_pages: int) -> dict[int, list[str]]:
    """Page -> outline path (top two levels) in force on that page."""
    paths, stack, entries = {}, [], sorted(toc, key=lambda e: e["page"])
    i = 0
    for p in range(1, n_pages + 1):
        while i < len(entries) and entries[i]["page"] <= p:
            e = entries[i]
            if e["level"] <= 2 and e["title"]:
                stack = stack[: e["level"] - 1] + [e["title"]]
            i += 1
        paths[p] = list(stack)
    return paths


def heading_level(line: dict, body_size: float) -> int:
    """0 = body text, 1 = major heading, 2 = sub-heading. With a layout result only title regions are headings
    (document titles or >= 1.3x body size are major); without one, font size relative to the body text decides."""
    text = line["text"].strip()
    if not (3 <= len(text) <= 90) or sum(c.isdigit() for c in text) > len(text) / 3:
        return 0
    if "title" in line:
        if not line["title"]:
            return 0
        return 1 if line["title"] == "doc" or line["size"] >= body_size * 1.3 else 2
    if line["size"] >= body_size * 1.6:
        return 1
    if line["size"] >= body_size * 1.25 or (line["bold"] and line["size"] >= body_size * 1.1 and len(text) < 60):
        return 2
    return 0


def is_junk(text: str) -> bool:
    """Page numbers, navigation tabs ('01 02 03'), lone symbols."""
    return sum(c.isalpha() for c in text) < 3


def paragraphs(lines: list[dict], body_size: float) -> list[tuple[str, int]]:
    """(text, heading_level) units. Consecutive heading lines of one level merge into one heading; a paragraph
    breaks at a heading, at a new layout region, or at a vertical gap larger than ~1.6 line heights."""
    out: list[tuple[str, int]] = []
    buf, prev = [], None
    for line in lines:
        text = line["text"].strip()
        if is_junk(text):
            continue
        level = heading_level(line, body_size)
        if level:
            if buf:
                out.append((" ".join(buf), 0))
                buf = []
            if out and out[-1][1] == level and prev is not None and heading_level(prev, body_size) == level:
                out[-1] = (out[-1][0] + " " + text, level)
            else:
                out.append((text, level))
        else:
            if buf and prev is not None and (line.get("break") or
                                             line["top"] - prev["top"] > 1.6 * max(prev["size"], 6)):
                out.append((" ".join(buf), 0))
                buf = []
            buf.append(text)
        prev = line
    if buf:
        out.append((" ".join(buf), 0))
    return out


def running_lines(pages: list[dict]) -> set[str]:
    """Lines repeated on many pages (running headers/footers) carry no content and must not become headings."""
    counts: dict[str, int] = {}
    for p in pages:
        for t in {ln["text"].strip().lower() for c in p["columns"] for ln in c["lines"]}:
            counts[t] = counts.get(t, 0) + 1
    floor = max(5, len(pages) // 7)
    return {t for t, n in counts.items() if n >= floor}


def table_markdown(rows: list[list[str]]) -> list[str]:
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    fmt = lambda r: "| " + " | ".join(c.replace("|", "/") for c in r) + " |"  # noqa: E731
    return [fmt(rows[0]), "|" + " --- |" * width] + [fmt(r) for r in rows[1:]]


class Builder:
    def __init__(self, doc_id: str, ticker: str, year: int):
        cfg = config()["chunking"]
        self.doc_id, self.ticker, self.year = doc_id, ticker, year
        self.max, self.min, self.overlap = cfg["max_tokens"], cfg["min_tokens"], cfg["overlap_tokens"]
        self.chunks: list[dict] = []

    def emit(self, text: str, page_start: int, page_end: int, section: str, kind: str, lang, pair_id, chunker,
             figure_id: str | None = None, header: bool = True):
        if header:  # figure chunks carry their own §6.1 header
            text = f"[{self.ticker} | Annual Report | FY{self.year} | {section or '-'} | p.{page_start}]\n{text}"
        self.chunks.append({
            "chunk_id": f"{self.doc_id}-{len(self.chunks):05d}",
            "doc_id": self.doc_id, "ticker": self.ticker, "fiscal_year": self.year,
            "page_start": page_start, "page_end": page_end, "section_path": section or None,
            "seq": len(self.chunks), "kind": kind, "lang": lang, "pair_id": pair_id,
            "text": text, "chunker": chunker, "figure_id": figure_id,
        })


class Stream:
    """Accumulates paragraphs of one language until a heading/section change or the token limit."""

    def __init__(self, builder: Builder, lang: str | None, chunker: str):
        self.b, self.lang, self.chunker = builder, lang, chunker
        self.parts: list[tuple[str, int, int]] = []  # (text, page, tokens)
        self.section, self.pair_id = "", None

    def tokens(self) -> int:
        return sum(t for _, _, t in self.parts)

    def flush(self, keep_overlap: bool = False) -> None:
        if not self.parts:
            return
        text = "\n".join(p for p, _, _ in self.parts)
        self.b.emit(text, self.parts[0][1], self.parts[-1][1], self.section, "text", self.lang, self.pair_id,
                    self.chunker)
        tail = []
        if keep_overlap:  # carry the last sentences (~overlap tokens) into the next chunk of the same section
            for sent in reversed(SENTENCE.split(self.parts[-1][0])):
                t = ntok(sent)
                if sum(x[2] for x in tail) + t > self.b.overlap:
                    break
                tail.insert(0, (sent, self.parts[-1][1], t))
        self.parts, self.pair_id = tail, None

    def add(self, text: str, page: int, section: str, pair_id: str | None) -> None:
        if section != self.section:
            self.flush()
            self.parts, self.section = [], section
        if pair_id and not self.pair_id:
            self.pair_id = pair_id
        t = ntok(text)
        if t > self.b.max:  # oversized paragraph: split by sentences, or by word windows if it is one long run
            pieces = SENTENCE.split(text)
            if len(pieces) == 1:
                words = text.split()
                step = max(1, len(words) * self.b.max // (t + 1))
                pieces = [" ".join(words[i : i + step]) for i in range(0, len(words), step)]
            for piece in pieces:
                self.add(piece, page, section, pair_id)
            return
        if self.tokens() + t > self.b.max:
            self.flush(keep_overlap=True)
        self.parts.append((text, page, t))
        if self.tokens() >= self.b.min and text.rstrip().endswith((".", ":", ";")):
            self.flush(keep_overlap=True)


def merge_small(chunks: list[dict], max_tokens: int, min_tokens: int) -> list[dict]:
    """Merge adjacent text chunks of the same document, section and language while the result stays <= max."""
    out: list[dict] = []
    for c in chunks:
        prev = out[-1] if out else None
        if (prev and c["kind"] == prev["kind"] == "text" and c["section_path"] == prev["section_path"]
                and c["lang"] == prev["lang"] and (prev["_tok"] < min_tokens or c["_tok"] < min_tokens)
                and prev["_tok"] + c["_tok"] <= max_tokens):
            prev["text"] += "\n" + c["text"].split("\n", 1)[1]
            prev["page_end"] = max(prev["page_end"], c["page_end"])
            prev["pair_id"] = prev["pair_id"] or c["pair_id"]
            prev["_tok"] += c["_tok"]
        else:
            out.append(c)
    for i, c in enumerate(out):
        c["seq"] = i
        c["chunk_id"] = f"{c['doc_id']}-{i:05d}"
        del c["_tok"]
    return out


def figure_chunks(b: "Builder", figures: list[dict], section_of: dict[int, str], chunker: str) -> None:
    """§6.1 figure chunks: alias header, section, caption, data; long tables split by rows (header repeated)."""
    for f in figures:
        if not f["chart_table_md"]:
            continue
        section = section_of.get(f["page_no"]) or "-"
        tag = "TABLE" if f["kind"] == "table" else "FIGURE"  # D56: only charts and diagrams are shown as images
        head = (f"[{tag} {f['figure_id']} | {f['kind']} | {b.ticker} Annual Report {b.year} | p.{f['page_no']}\n"
                f" Section: {section}]\nCaption: {f['caption'] or '(none found)'}\nData:")
        rows = f["chart_table_md"].splitlines()
        is_table = len(rows) >= 2 and set(rows[1].replace("|", " ").split()) == {"---"}
        hdr, body = (rows[:2], rows[2:]) if is_table else ([], rows)
        piece: list[str] = []
        for row in body:
            if piece and ntok("\n".join([head] + hdr + piece + [row])) > b.max:
                b.emit("\n".join([head] + hdr + piece), f["page_no"], f["page_no"], section, f["kind"], None, None,
                       chunker, figure_id=f["figure_id"], header=False)
                piece = []
            piece.append(row)
        b.emit("\n".join([head] + hdr + piece), f["page_no"], f["page_no"], section, f["kind"], None, None, chunker,
               figure_id=f["figure_id"], header=False)


def chunk(parsed: dict, ticker: str, year: int, figures: list[dict] | None = None) -> list[dict]:
    pages, figures = parsed["pages"], figures or []
    skip = running_lines(pages)
    for p in pages:
        for c in p["columns"]:
            c["lines"] = [ln for ln in c["lines"] if ln["text"].strip().lower() not in skip]
    sizes = [ln["size"] for p in pages for c in p["columns"] for ln in c["lines"]]
    body = statistics.median(sizes) if sizes else 10.0
    toc = toc_paths(parsed["toc"], len(pages))
    has_structure = bool(parsed["toc"]) or any(
        heading_level(ln, body) for p in pages for c in p["columns"] for ln in c["lines"]
    )
    chunker = "section" if has_structure else "page"
    b = Builder(parsed["doc_id"], ticker, year)
    streams: dict[str, Stream] = {}
    heads: dict[str, list[str]] = {}  # per language stream: [major, sub] heading in force, carried across pages
    section_of: dict[int, str] = {}  # page -> section path, for figure chunks
    for p in pages:
        n = p["page_no"]
        base = toc.get(n, [])
        for col in p["columns"]:
            lang = col["lang"] or "und"
            s = streams.setdefault(lang, Stream(b, col["lang"], chunker))
            h = heads.setdefault(lang, ["", ""])
            pair_id = f"{parsed['doc_id']}-p{n}" if col.get("pair") else None
            for text, level in paragraphs(col["lines"], body):
                if level and chunker == "section":
                    h[:] = [text, ""] if level == 1 else [h[0], text]
                    continue
                # With an outline, it gives the top of the path and detected headings refine it.
                parts = base + [h[1] or h[0]] if base else [h[0], h[1]]
                section = " > ".join(x for x in parts if x)
                section_of.setdefault(n, section)
                s.add(text, n, section if chunker == "section" else f"p.{n}", pair_id)
        section_of.setdefault(n, " > ".join(base) or section_of.get(n - 1, ""))
        if chunker == "page":
            for s in streams.values():
                s.flush()
    for s in streams.values():
        s.flush()
    figure_chunks(b, figures, section_of, chunker)
    for c in b.chunks:
        c["_tok"] = ntok(c["text"].split("\n", 1)[1])
    return merge_small(b.chunks, b.max, b.min)


def write_chunks(doc_id: str, chunks: list[dict]) -> None:
    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)
    with (CHUNKS_DIR / f"{doc_id}.jsonl").open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
