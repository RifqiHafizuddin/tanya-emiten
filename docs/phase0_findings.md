# Phase 0 findings

Checked 2026-10-25 by Claude for the owner. This file answers the 8 items in §4.2. Items that need sample files or the owner's accounts are marked **OPEN**, each with a proposed fallback.

## Summary: decisions the owner needs to make

| # | Topic | Finding | Options (recommended first) |
|---|---|---|---|
| A | IDX access (§14) | IDX's Terms of Use **forbid web scraping/crawling** | **Annual reports: scripted, polite download from company IR sites** (owner's choice, 2026-10-25), after a per-site robots/terms check; citations link to the IR copy (D11 adjusted). **Quarterly XLSX/XBRL exist only on IDX**, so they stay manual unless IDX grants permission (see item 2) |
| F | DB size (acceptance box) | Projection **≈ 395 MB (79%)** for D1 + D2, **over 70%** | **Decided 2026-10-25 by the owner: option 1, `halfvec(384)` + expression GIN index (≈ 46%); revisit at MVP 3** |
| B | Back-end host (D9) | HF now requires **PRO ($9/mo) to create Docker Spaces**, which conflicts with D6. The owner's Space [`rifqih/tanya-emiten`](https://huggingface.co/spaces/rifqih/tanya-emiten) is a **Gradio** Space on **ZeroGPU** (`zero-a10g`), not Docker | The owner also has [`rifqih/churn-mlops`](https://huggingface.co/spaces/rifqih/churn-mlops): **`sdk: docker`, `cpu-basic`**, public, currently `RUNTIME_ERROR`. New Spaces can't be created on the free account, but this one can be renamed in Settings and reused. **Decided 2026-10-25 by the owner: rename `churn-mlops` → `tanya-emiten-api` and use it for the FastAPI back end; D9 unchanged** |
| C | LQ45 snapshot (D1) | The current list ends **2026-10-30**. The next quarterly list should be announced ~2026-10-26 and take effect ~2026-11-02 | **Decided 2026-10-25 by the owner: freeze the 3 Aug – 30 Oct 2026 list** (as committed) |
| D | Price source (D21) | IDX daily summary can't be scripted (terms); yfinance is "personal use only" | Decide at sign-off; see item 8 |
| E | Gemini model names (D39, D40) | Free models are known; their RPM/RPD are visible only in AI Studio | Owner pastes the AI Studio rate-limit table; then pick `small`/`answer`/`judge` |

---

## 1. IDX filings access

**robots.txt.** `https://www.idx.co.id/robots.txt` and `https://idx.co.id/robots.txt` both return **404** (fetched 2026-10-25), so there is no robots file. The site is behind **Cloudflare** (`server: cloudflare`, `__cf_bm` bot-management cookie on every response).

**Terms of Use** ([idx.co.id/id/syarat-penggunaan](https://www.idx.co.id/id/syarat-penggunaan/), read 2026-10-25). Key clauses, paraphrased:
- Using or redistributing data from the site for **commercial purposes** needs IDX's prior written permission.
- **Non-commercial** use, including quoting, is allowed **with a full source citation plus the date accessed**, and **"tidak diperkenankan menggunakan metode web scrapping/crawling"**. In other words, scraping and crawling are not permitted.
- The site shows listed-company data for **the last 3 years** only. Older data goes through **TICMI** (ticmi.co.id), under TICMI's own terms (paid).
- "IDX", "BEI" and the IDX logo are trademarks; commercial use needs permission.

**Conclusion.** The missing robots.txt does not override an explicit no-scraping clause. **No scripted downloads from idx.co.id.** Per guardrail 1, the owner downloads files by hand into `corpus/inbox/`, and the README says so. Answers must cite the source and the access date. That fits D11 (link to the source file on IDX), as long as `documents.fetched_at` is shown with the citation.

**What is linked per filing** (seen in the browser at [Laporan Keuangan dan Tahunan](https://www.idx.co.id/id/perusahaan-tercatat/laporan-keuangan-dan-tahunan/)). Each quarterly filing card (e.g. AADI 2025 TW1) lists:
- `FinancialStatement-{YYYY}-{I|II|III|Tahunan}-{TICKER}.xlsx` and `.pdf`, both IDX-generated
- `instance.zip` (XBRL instance) and `inlineXBRL.zip`
- the company's own PDFs (full statements, board statement, cover letter)

Filters are report type (Laporan Keuangan / Laporan Tahunan), year (**2022–2026** in the selector) and period (TW1, TW2, TW3, Tahunan).

**History depth.** Only ~3 years via the site (per the terms); the selector shows 2022–2026. The spec's MVP 2 target of "2015 onward" is **not reachable for free from IDX**. A realistic target is ~2022 onward, about 12–16 quarters, which still meets "at least 12 quarters".

**Company IR sites (annual reports).** Checked 2026-10-25 for the 3 sample companies:

| Ticker | robots.txt | Terms | FY2025 report URL | sha256 |
|---|---|---|---|---|
| BBRI | [ir-bri.com](https://www.ir-bri.com/robots.txt): `User-agent: * / Disallow:` (only named bots banned) | [bri.co.id/en/term-of-use](https://bri.co.id/en/term-of-use) covers complaint handling only; no clause on reuse or automated access | `https://www.ir-bri.com/misc/AR/AR2025-EN.pdf` (19.6 MB; IR page lists reports back to 2008) | `1eed5700…6bd0` |
| ICBP | 404 (none) | [Terms of use](https://www.indofoodcbp.com/terms-of-use): copyright/trademark notice, "misuse" prohibited, no scraping clause | `https://www.indofoodcbp.com/uploads/annual/ICBP_2025AR_final.pdf` (17.2 MB) | `fa36ec48…2f30b` |
| ITMG | [itmg.co.id](https://www.itmg.co.id/robots.txt): `User-agent: * / Disallow:` | No terms page linked. An F5 WAF rejected the WebFetch user agent; plain `curl` with an honest UA worked. Never work around a block | `https://www.itmg.co.id/files/investor/ITM_Annual%20Report_2025_full.pdf` (20.2 MB) | `3314e4bb…2c3f` |

Downloaded with `curl` (honest UA naming the repo, 5 s between requests) to `corpus/pdf/` (gitignored). The fetcher must repeat this robots/terms check per company and record the result in the manifest.

**Manual workload to plan for.** MVP 1 needs 45 annual reports; IR sites cover these. MVP 2 needs 45 tickers × ~16 quarters × 1–2 files (xlsx and/or instance.zip), so **~720–1,440 manual downloads**. Raise this again before MVP 2. One option is the companies' own IR sites, each with its own robots/terms to check.

## 2. XBRL contents — **OPEN (needs sample files)**

The IDX-generated XLSX/XBRL files are not on company IR sites; those carry only PDF statements, e.g. ITMG's `ITM Consolidated Financial Statements 6M26.pdf`. Ways to get them without breaking IDX's terms:
1. The owner downloads 3 files once, for Phase 0 only (~2 min).
2. Ask IDX in writing for permission to fetch them politely and automatically, for a non-commercial portfolio project. The terms imply this route for anything beyond normal use; the answer is slow and uncertain.
3. Defer items 2 and 3 to the start of MVP 2 and decide the quarterly source then.

- File types confirmed (item 1): IDX-generated XLSX, XBRL `instance.zip`, `inlineXBRL.zip`.
- Still to check on samples: which taxonomy template each LQ45 company uses. LQ45 has banks (BBCA, BBRI, BMRI, BBNI, BBTN) and no insurers or financing companies, so the general + bank templates are likely enough. Also to check: whether the XLSX is easier to parse than the XBRL instance, and how line items map to §5.
- **Fallback:** parse the IDX `FinancialStatement-*.xlsx` with `pandas`/`openpyxl` (no `arelle` needed) if its sheets carry the same line items with stable labels. Otherwise use `lxml` on the instance.

## 3. Bank ratios (NPL, NIM, CAR, LDR) — **OPEN (needs a bank sample)**

- Expectation, to verify: these are not standard line items in the IDX financial-statement template. They appear in the annual report's "Ikhtisar Keuangan / Rasio Keuangan" table and in the notes.
- **Fallback (already in the spec, §5):** extract them from report tables as `source = report_table` with page numbers, and hand-check them for the golden set.

## 4. LQ45 constituents

- `corpus/lq45_snapshot.csv`: 45 tickers, **effective 2026-08-03 to 2026-10-30**, snapshot date 2026-10-25.
- Source: [Kontan LQ45 table](https://www.kontan.co.id/indeks-lq45), cross-checked with [Wikipedia](https://en.wikipedia.org/wiki/LQ45), which lists the same 44 plus a gap where NCKL belongs, and with news that INDY and NCKL joined and SMGR and TOWR left ([Stockbit Snips](https://snips.stockbit.com/stockbit-research/bei-umumkan-evaluasi-indeks-idx30-lq45-dan-idx80), [Kumparan](https://kumparan.com/kumparanbisnis/bei-ubah-daftar-saham-lq45-idx80-dan-idx30-mulai-berlaku-3-agustus-2026-27sHoiFxpNw)). The IDX announcement PDF itself was not fetched.
- **Spec correction (§5):** LQ45 is now reviewed **quarterly**: announced in Jan/Apr/Jul/Oct, effective Feb/May/Aug/Nov. It is not semi-annual (Feb/Aug). Criteria have included free float, trading days and the High Shareholding Concentration exclusion since 2026-05-04 ([Kompas](https://money.kompas.com/read/2026/04/22/112008826/bei-ubah-kriteria-indeks-idx30-lq45-dan-idx80)).
- **Timing issue (decision C):** this list expires in 5 days. The Aug list was announced Mon 2026-07-27 for 08-03, so the Nov list is likely announced around Mon 2026-10-26 for ~11-02. Recommendation: **wait for the Nov list** and swap the CSV (one file, a few minutes), so that the frozen snapshot is current at MVP 1 launch.
- Sample tickers proposed for Phase 0 measurement: **BBRI** (bank, large, likely bilingual), **ICBP** (consumer), **ITMG** (USD reporter; ADRO, AADI, AMMN, INCO and MEDC also report in USD).

## 5. Free-tier limits and Gemini models

Full table in `docs/free_tier.md`. Material findings:

- **Gemini:** the free-tier models (pricing page updated 2026-10-22) include `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite` and Gemma 4. Per-model limits come from the owner's AI Studio table (2026-10-25): 3.8 and 3.6 Flash allow only **20 RPD**, too few for a public demo or for eval runs. Proposed model tiering (decision E, owner confirms at sign-off):

| Role | Model | Why |
|---|---|---|
| `answer` | `gemini-3.5-flash-lite` | Only Gemini model with a usable daily cap (15 RPM / 500 RPD). Smoke test 2026-10-25: structured output OK in 1.4 s (entities + language correct, 71 tokens) |
| `small` | `gemini-3.1-flash-lite` | Separate quota from `answer`. Free per the pricing page; its RPM/RPD appear in AI Studio after first use (record then). Gemma 4 31B was tried first but **failed the smoke test**: empty structured output, then `503 UNAVAILABLE` (high demand). Too unreliable on the request path |
| `judge` | `gemma-4-31b-it` | Different family from `answer` (D40). 14.4K RPD covers full golden-set runs. Runs offline, so retries with backoff absorb the 503s. Structured output still unproven: parse JSON from text if schema mode keeps failing. The ≥ 85% owner-agreement gate still decides whether it is trusted |

**Judge alternative raised by the owner: Groq `qwen/qwen3.8-27b`.**
- Groq's published base limits (Developer plan): 30 RPM / 1K RPD / 8K TPM / **200K TPD**. Free-tier numbers appear only on the account's [limits page](https://console.groq.com/settings/limits).
- **For:** a different provider *and* model family from `answer`, which is the strongest D40 fit. It's OpenAI-compatible, so it slots straight into the existing `JUDGE_PROVIDER` / `JUDGE_BASE_URL` / `JUDGE_API_KEY` variables.
- **Against:** 200K tokens/day caps judging at ~130–200 calls/day if each prompt stays at ~1–1.5K tokens (claim + quote, or answer + reference). Full golden-set runs would need judgment caching and possibly two days.
- Proposed: Groq Qwen as `judge`, Gemma 4 31B as the backup judge; `small` stays on Gemini so the request path uses a single provider.
- Pending: free-tier numbers and a smoke test.

The key sees these model ids: `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3.5-flash`, `gemini-3.6-flash`, `gemini-3.7-flash`, `gemini-3.8-flash`, `gemini-2.5-flash(-lite)`, `gemini-3-flash-preview`, `gemma-4-31b-it`, `gemma-4-26b-a4b-it`.

Notes:
- `global_questions_per_day` = 250.
- Use a **dedicated Google Cloud project**. The current "Capstone" project already peaks near its 500 RPD.
- 3.8 Flash stays available as a vision fallback (D27): it is called rarely, and only when the cap allows.
- **Hugging Face (decision B):** the docs now say Docker Spaces need PRO to create. The owner's Space (checked 2026-10-25 via the public API) has `sdk: gradio`, requested hardware `zero-a10g`, sleep timeout 172,800 s (48 h), no app file yet, and a leftover title "Pdm Fleet". So D9 as written (Docker on CPU Basic) isn't available. The options are:
  1. **Render free web service (Docker)**. Same FastAPI container, but only ~512 MB RAM, so e5-small has to run via ONNX/int8 (same model and dimensions, so D14 stays) rather than PyTorch. Sleeps after 15 min idle. *Recommended:* it changes only the host and keeps every other decision.
  2. **Gradio Space on free ZeroGPU** (2 allowed; the owner already has one). It's free and has much more RAM than Render. But the SDK is Gradio, not Docker: `app.py` would start FastAPI with Gradio mounted inside, and whether ZeroGPU Spaces serve custom routes and SSE that way needs a ~20-line spike. Gradio is a dependency the stack doesn't list.
  3. **HF PRO at $9/month**. Simplest, but breaks D6 (zero cost).
- **Supabase** 500 MB DB / 1 GB storage / 5 GB egress / pause after 7 days. These match the spec.
- **Vercel Hobby** 100 GB transfer, 1M invocations, non-commercial only. The repo must be under a personal GitHub account, not an org.
- **Langfuse Hobby** 50k units/month, 30-day retention.

## 6. PaddleOCR hosted API — **OPEN (owner has a key; quota and terms to read from the account)**

- 2026-10-25: the owner has a PaddleOCR API key (`PADDLEOCR_API_KEY`, endpoint `PADDLEOCR_API_URL` = `https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`).
- Owner-confirmed account limits: **20,000 pages/day**, no file-size limit, but **keep each job ≤ 100 pages** to avoid timeouts; pages beyond that are ignored. The OCR step must split PDFs into ≤ 100-page jobs. Better still, send only the pages that need OCR (< 200 chars, or containing charts/tables).
- Budget check: 45 reports × ~200 OCR-worthy pages ≈ 9k pages, which fits in one day's quota.
- **Timing (2026-10-25, model `PaddleOCR-VL-1.6`, async jobs API):**
  - 10 ICBP narrative pages with photos: **69 s wall time, 6.9 s/page**
  - 2 financial-highlights pages: 39 s, so each job carries roughly 20–30 s of fixed overhead
  - Batch pages into ≤ 100-page jobs. Sequentially, ~9k pages at ~5 s ≈ 12–13 h, which suits a resumable overnight job
- **Output:** each page returns `markdown`, `prunedResult` (layout blocks), `inputImage` and `outputImages`. Text came back clean. Tables come back as HTML `<table>` markup inside the markdown. **Chart → table conversion was not confirmed** on these pages; check on chart-heavy pages at the start of MVP 1.
- **Recommendation:** OCR backend = **hosted API** (decision for sign-off). Colab/Kaggle GPU stays as the fallback.

- A hosted API exists through Baidu AI Studio (paddleocr.com redirects to aistudio.baidu.com/paddleocr; the page returns 403 to non-browser fetches). Access needs an AI Studio token.
- Quota: Baidu's quota doc says **3,000 pages per model per day** with an increase-request form; a newer "20,000 pages/day" claim is unconfirmed. Per request: ≤ 1,000 pages, ≤ 50 MB upload.
- Not verified: signup requirements (a Baidu account may need a Chinese phone number) and data-use terms.
- **Fallback (spec default):** Colab/Kaggle GPU, made resumable. Timing PaddleOCR on one report needs the samples and a notebook session, so it is deferred until the owner approves the sample downloads.

## 7. Report layout and DB size

Measured 2026-10-25 on the 3 FY2025 reports with pymupdf; pdfplumber was timed on 20 sampled pages each.

| | BBRI (bank) | ICBP (consumer) | ITMG (USD, coal) |
|---|---|---|---|
| Pages / size | **1,407** / 19.6 MB | 292 / 17.2 MB | 436 / 20.2 MB |
| Pages < 200 chars (→ OCR) | 20 (1%) | 38 (13%) | 20 (5%) |
| Pages with images | 41% | 49% | 22% |
| Side-by-side ID │ EN pages | 28% | **72%** | 45% |
| Language edition | Separate English edition, but the embedded audited statements are side-by-side bilingual | Bilingual throughout | Mostly bilingual |
| Embedded audited FS (from first FS marker past 30% of the file) | p.962 → end, 445 pp, 36% of chars | p.168 → end, 124 pp, 53% of chars | p.137 → end, 299 pp, ~71% of chars (likely overcounts) |
| pdfplumber speed | 0.18 s/page | 0.14 s/page | **fails**: `No /Root object` (malformed PDF). pymupdf opens it in repair mode → save a repaired copy, then run pdfplumber |
| Text tokens (chars / 4) | 1.13 M | 211 K | 339 K |
| Text chunks (325 net tokens each) | ~3,480 | ~650 | ~1,050 |

Findings:
- Side-by-side bilingual pages are the norm, not the exception. The chunker must split a page into language columns before chunking; D30 `pair_id` pairs the left and right columns.
- Bank reports are 3–5× larger than others, mostly because of the embedded statements and notes.
- Few pages need OCR for text (1–13%), but 22–49% contain images (photos, charts), so chart → table work is concentrated there.

**Projection for D1 + D2** (45 reports):
- 5 banks × ~3,500 + 40 others × ~850 ≈ 51k text chunks, plus ~10% figure chunks → **~56k chunks**.
- Size per chunk (estimate below) ≈ 7 KB → **≈ 395 MB = 79% of 500 MB. Over the 70% line, so the owner must choose a mitigation.**

| Option | Projected size | Trade-off |
|---|---|---|
| **1. `halfvec(384)` + expression GIN on `to_tsvector('simple', text)`, no stored `tsvector`** (recommended, §14 default) | ~4.1 KB/chunk → **≈ 230 MB (46%)** | Negligible recall loss expected from fp16 (measure in the MVP 1 ablation); lexical query is slightly slower |
| 2. Skip the embedded audited-statement pages in RAG | ≈ 215 MB (43%) | Numbers belong in `facts` anyway (guardrail 2), but narrative notes (risk management, accounting policies) are lost |
| 3. Both | ≈ 125 MB (25%) | Leaves room for the second year at MVP 3; D2 roughly doubles the corpus, so option 1 alone would reach ~92% then |

The size per chunk is a desk estimate:

| Part | Size |
|---|---|
| ~400 tokens of text (TOAST-compressed) | ~1.5 KB |
| `vector(384)` | 1.5 KB |
| HNSW index entry | ~1.9 KB |
| `tsvector` | ~1.2 KB |
| GIN entry | ~0.8 KB |
| Row overhead and b-trees | ~0.3 KB |
| **Total** | **≈ 7 KB** |

MVP 1 ingestion should replace this estimate with `pg_total_relation_size` after loading the first 3 reports.

## 8. Price source (MVP 3)

| Option | History | Terms | Reliability |
|---|---|---|---|
| IDX daily trading summary | Site's ~3-year window | Scraping forbidden; non-commercial quoting allowed with citation | Authoritative, but only by hand, so daily history isn't practical |
| Yahoo Finance via `yfinance` | Long (`.JK` tickers) | yfinance: not affiliated with Yahoo, "intended for personal use only"; Yahoo's ToS restrict automated access and redistribution | Unofficial, breaks occasionally |
| None until decided | — | — | §14 default |

Recommendation: keep the §14 default (**no prices**) for now and revisit before MVP 3. Showing yfinance data on a public site is a terms risk the owner should accept explicitly, not inherit by default.

## Filing deadlines (§5, for MVP 5)

- Annual report: **end of month 4** after fiscal year end (POJK 29/POJK.04/2016, cited in [Telkom's](https://www.telkom.co.id/minio/show/data/lampiran/1774975199026_original_Pemberitahuan-Lap-Keu-Tahunan-TB-2025-pdf.pdf) and [Waskita's](https://investor.waskita.co.id/newsroom/AnnualReport2025-WSKT-att1.pdf) 2025 filings). Dual-listed companies like TLKM may follow foreign rules.
- Periodic financial statements: [POJK 14/POJK.04/2022](https://www.ojk.go.id/id/regulasi/Documents/Pages/Penyampaian-Laporan-Keuangan-Berkala-Emiten-atau-Perusahaan-Publik/POJK%2014%20-%2004%20-%202022.pdf). Annual audited statements are due end of month 3. Interim statements are due 1, 2 or 3 months after period end (unaudited / reviewed / audited). Article text not yet read; verify before MVP 5.

## Phase 0 checklist status

| Spec item | Status |
|---|---|
| `docs/phase0_findings.md`, `docs/free_tier.md`, `corpus/lq45_snapshot.csv` | Written (items 2, 3, 6, 7 open, with fallbacks) |
| Repo on GitHub, `uv` project, `.gitignore`, `.env.example`, CI | Repo [RifqiHafizuddin/tanya-emiten](https://github.com/RifqiHafizuddin/tanya-emiten) exists (public, empty). `.gitignore` and `.env.example` written locally. Local git link, `uv` project and CI not started |
| Supabase/HF/Vercel/Langfuse projects | `.env` has DB, Supabase, LLM and PaddleOCR keys (2026-10-25); Langfuse keys and `IP_HASH_SALT` still empty. **`DATABASE_URL` uses the direct host `db.<ref>.supabase.co`, which is IPv6-only** (no A record). It is unreachable from this network and likely from HF Spaces → replace it with the **Session pooler** URI (IPv4). HF: `churn-mlops` (Docker, cpu-basic) to be renamed `tanya-emiten-api` by the owner; D9 unchanged |
| 3 sample reports + XBRL, measurements, OCR timing | Reports downloaded from IR sites and measured (§7). XBRL/XLSX samples: IDX-only (item 2). OCR timing: waiting for `PADDLEOCR_API_KEY` in `.env` |
| `LLMClient` and e5 smoke tests | Scratch Gemini check done (see §5). `LLMClient` itself and e5-in-the-Space are product code, held until sign-off |
