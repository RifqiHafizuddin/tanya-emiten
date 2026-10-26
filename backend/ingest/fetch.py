"""Polite discovery and download of annual reports from company IR sites (D43, guardrail 1).

Every request: robots.txt allowed for our honest User-Agent, >= request_delay_seconds per host, no retries
around blocks. idx.co.id is never fetched (its terms forbid scraping).
"""
import csv
import hashlib
import re
import time
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
import yaml

from backend.config import ROOT, config

PDF_DIR = ROOT / "corpus" / "pdf"
INBOX = ROOT / "corpus" / "inbox"
MANIFEST = ROOT / "corpus" / "manifest.csv"
MANIFEST_FIELDS = ["doc_id", "ticker", "type", "year", "period", "source_url", "sha256", "bytes", "fetched_at"]
BLOCKED_HOSTS = {"idx.co.id", "www.idx.co.id"}

FOLLOW = re.compile(r"investor|hubungan.investor|annual|tahunan|laporan|report|publikasi|publication|\bir\b", re.I)
EXCLUDE = re.compile(
    r"sustainab|keberlanjutan|summary|ringkas|expose|paparan|presentation|keuangan|financial.statement|"
    r"interim|quarter|triwulan|kuartal|gcg|governance.report|rups|agm|egm|prospek|dividen",
    re.I,
)


class Polite:
    """HTTP client that honours robots.txt and a per-host delay."""

    def __init__(self):
        # Verify TLS against the OS trust store: some IR servers send incomplete chains that the OS can complete
        # but certifi cannot. Verification stays on.
        import truststore

        truststore.inject_into_ssl()
        cfg = config()["fetch"]
        self.ua, self.delay, self.timeout = cfg["user_agent"], cfg["request_delay_seconds"], cfg["timeout_seconds"]
        self.session = requests.Session()
        self.session.headers["User-Agent"] = self.ua
        self.robots: dict[str, RobotFileParser | None] = {}
        self.last: dict[str, float] = {}

    def _wait(self, host: str) -> None:
        gap = time.monotonic() - self.last.get(host, 0)
        if gap < self.delay:
            time.sleep(self.delay - gap)
        self.last[host] = time.monotonic()

    def allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        if parts.hostname in BLOCKED_HOSTS:
            return False
        base = f"{parts.scheme}://{parts.netloc}"
        if base not in self.robots:
            self._wait(parts.netloc)
            rp = RobotFileParser()
            try:
                r = self.session.get(base + "/robots.txt", timeout=30)
                # No robots.txt (4xx) means no restrictions; 5xx or network errors mean we don't know: stay out.
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
                self.robots[base] = rp if r.status_code < 500 else None
            except requests.RequestException:
                self.robots[base] = None
        rp = self.robots[base]
        return rp is not None and rp.can_fetch(self.ua, url)

    def get(self, url: str, **kwargs) -> requests.Response | None:
        if not self.allowed(url):
            print(f"  robots.txt disallows (or unreadable): {url}")
            return None
        self._wait(urlsplit(url).netloc)
        try:
            return self.session.get(url, timeout=self.timeout, **kwargs)
        except requests.RequestException as e:
            print(f"  network error {type(e).__name__}: {url}")
            return None


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._text: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._href, self._text = dict(attrs).get("href"), []

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)

    def handle_endtag(self, tag):
        if tag == "a" and self._href:
            self.links.append((self._href, " ".join("".join(self._text).split())))
            self._href = None


def links(html: str, base: str) -> list[tuple[str, str]]:
    parser = _Links()
    parser.feed(html)
    return [(urljoin(base, href), text) for href, text in parser.links if not href.startswith(("mailto:", "tel:", "#"))]


def score_report_pdf(url: str, text: str, year: int) -> int:
    """>0 if (url, anchor text) looks like the full annual report PDF for `year`."""
    blob = f"{url} {text}"
    if ".pdf" not in url.lower() or str(year) not in blob or EXCLUDE.search(blob):
        return 0
    s = 0
    s += 3 if re.search(r"annual.?report|laporan.?tahunan|\bAR\b|_AR|AR_|-AR|AR-|AR\d{4}", blob, re.I) else 0
    s += 1 if re.search(r"full|lengkap|final", blob, re.I) else 0
    s -= 1 if re.search(r"\b(ID|IND|indonesia|bahasa)\b", text, re.I) else 0  # prefer EN/bilingual editions
    return s


def discover(client: Polite, start_urls: list[str], year: int, max_pages: int = 12) -> list[tuple[int, str, str]]:
    """Breadth-first walk (same host, IR-looking links only) collecting candidate report PDFs, best first."""
    queue, seen, found = list(start_urls), set(), {}
    while queue and len(seen) < max_pages:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        r = client.get(url)
        if r is None or r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            continue
        host = urlsplit(url).hostname
        title = re.search(r"<title[^>]*>(.*?)</title>", r.text, re.I | re.S)
        listing = re.search(r"annual|tahunan", url + " " + (title.group(1) if title else ""), re.I)
        for href, text in links(r.text, r.url):
            s = score_report_pdf(href, text, year)
            if s == 0 and listing and ".pdf" in href.lower() and not EXCLUDE.search(f"{href} {text}"):
                s = 1  # unlabeled PDF on an annual-report listing page (opaque storage names); content check decides
            if s > 0:
                found[href] = max(found.get(href, (0, ""))[0], s), text
            elif urlsplit(href).hostname == host and FOLLOW.search(f"{href} {text}") and ".pdf" not in href.lower():
                queue.append(href.split("#")[0])
    return sorted(((s, u, t) for u, (s, t) in found.items()), reverse=True)


def load_sources() -> dict:
    return yaml.safe_load((ROOT / config()["annual_reports"]["sources_file"]).read_text(encoding="utf-8"))


def read_manifest() -> dict[str, dict]:
    if not MANIFEST.exists():
        return {}
    with MANIFEST.open(encoding="utf-8", newline="") as f:
        return {row["doc_id"]: row for row in csv.DictReader(f)}


def write_manifest(rows: dict[str, dict]) -> None:
    with MANIFEST.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: r["doc_id"]))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def looks_like_annual_report(path: Path, year: int) -> bool:
    """A full annual report is long and names itself with the year ("Annual Report 2025", "2025 Laporan Tahunan")
    in its opening pages. No digits may sit in between, so "Annual Report 2024 ... 2025" does not pass."""
    from backend.ingest.parse_pdf import open_pdf

    try:
        with open_pdf(path) as pdf:
            if len(pdf.pages) < 80:
                return False
            opening = " ".join((p.extract_text() or "") for p in pdf.pages[:8])
    except Exception:
        return False
    title = r"(annual\s+report|laporan\s+tahunan)"
    return bool(re.search(rf"{title}[^0-9]{{0,60}}{year}|{year}[^0-9]{{0,60}}{title}", opening, re.I))


def download(client: Polite, url: str, path: Path, year: int, verify: bool = True) -> str | None:
    """Fetch `url` to `path`; discovered URLs (`verify`) must pass the content check, pinned ones were checked by
    hand (some covers are images without text). Returns the final URL, or None with the reason printed."""
    r = client.get(url, stream=True)
    if r is None:
        print(f"  skip (robots.txt disallows or network error): {url}")
        return None
    ctype = r.headers.get("content-type", "")
    if r.status_code != 200 or not ctype.startswith(("application/pdf", "application/octet")):
        print(f"  skip (HTTP {r.status_code} {ctype}): {url}")
        return None
    tmp = path.with_suffix(".part")
    with tmp.open("wb") as f:
        for block in r.iter_content(1 << 20):
            f.write(block)
    if tmp.read_bytes()[:5] != b"%PDF-" or (verify and not looks_like_annual_report(tmp, year)):
        tmp.unlink()
        print(f"  skip (not a full {year} annual report): {url}")
        return None
    tmp.replace(path)
    return r.url


def fetch_annual(tickers: list[str] | None = None) -> int:
    """Download each source's `pdf` (discovering candidates from `pages` when absent). Resumable via the manifest."""
    sources, manifest, client = load_sources(), read_manifest(), Polite()
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    failures = []
    for year in config()["annual_reports"]["fiscal_years"]:
        for ticker, src in sources.items():
            if tickers and ticker not in tickers:
                continue
            doc_id, path = f"{ticker}-AR-{year}", PDF_DIR / f"{ticker}-AR-{year}.pdf"
            if doc_id in manifest and path.exists() and sha256(path) == manifest[doc_id]["sha256"]:
                continue
            manual = INBOX / f"{doc_id}.pdf"
            if manual.exists():  # owner's manual download (guardrail 1 fallback); the link points at the IR page
                if not looks_like_annual_report(manual, year):
                    failures.append((ticker, f"{manual.name} in corpus/inbox is not a full {year} annual report"))
                    continue
                manual.replace(path)
                final = (src.get("pages") or ["manual download"])[0]
                manifest[doc_id] = dict(
                    doc_id=doc_id, ticker=ticker, type="annual_report", year=year, period="FY", source_url=final,
                    sha256=sha256(path), bytes=path.stat().st_size,
                    fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
                )
                write_manifest(manifest)
                print(f"{ticker}: registered manual download ({path.stat().st_size / 1e6:.1f} MB)")
                continue
            pinned = (src.get("pdf") or {}).get(year)
            candidates = [pinned] if pinned else [u for _, u, _ in discover(client, src.get("pages", []), year)][:3]
            final = None
            for url in candidates:
                final = download(client, url, path, year, verify=not pinned)
                if final:
                    break
            if not final:
                failures.append((ticker, f"no valid report among {len(candidates)} candidate(s)"))
                continue
            manifest[doc_id] = dict(
                doc_id=doc_id, ticker=ticker, type="annual_report", year=year, period="FY", source_url=final,
                sha256=sha256(path), bytes=path.stat().st_size,
                fetched_at=datetime.now(UTC).isoformat(timespec="seconds"),
            )
            write_manifest(manifest)
            print(f"{ticker}: {path.stat().st_size / 1e6:.1f} MB from {final}")
    for ticker, why in failures:
        print(f"MISSING {ticker}: {why}")
    return 1 if failures else 0
