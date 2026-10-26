# TANYAEMITEN.md — Tanya Emiten (IDX fundamentals assistant)

> Spec for Claude Code. Read fully before writing code. Build phase by phase; do not start a phase until the previous phase's acceptance criteria pass.
> The project owner supervises this build. Every decision in §2 was made by the owner on 2026-10-25. **Do not change a §2 decision, add a paid service, or add a framework without asking the owner first.** When a phase needs a choice that is not in §2, stop and ask, offering 2–3 options with trade-offs and a recommendation.
> "Tanya Emiten" is a working name (open decision, §14). Move this file to the root of its own repo before starting.

## 1. Goal

A public, zero-cost web assistant that answers questions about the fundamentals of LQ45 companies listed on the Indonesia Stock Exchange (IDX), in Bahasa Indonesia or English.

- **Narrative questions** ("why did BBRI's credit costs rise?", "apa strategi digital BBCA?") are answered from the companies' **annual reports** (yearly PDFs) by retrieval-augmented generation. Every claim cites a page, and the answer shows **image crops** of the pages, tables or charts it relied on.
- **Number questions** ("BBCA net profit Q2 2025", "compare NIM of the big 4 banks over 8 quarters") are answered from **quarterly financial statements** loaded into structured tables, never from PDF text. Answers show the numbers and a chart.
- Later phases add peer comparison, share prices and valuation, forecasts with uncertainty, and fundamental signals that are explained with the management commentary that accounts for them.

The project exists to demonstrate, with measured numbers, the skills AI-engineering postings ask for most: agents and tool calling, RAG, SQL, LLM evaluation, a deployed full-stack app, and clear communication of results.

### Market evidence (from the Jakarta AI Market Readout, Oct 2026)
Share of relevant postings asking for each skill: Indonesia n = 80, international n = 184.

| Skill | Indonesia | International | Where this project shows it |
|---|---|---|---|
| AI agents | 39% | 43% | Router agent over RAG + numeric tools (MVP 2), signal explanation (MVP 4) |
| SQL | 38% | 24% | Facts schema, typed tools (MVP 2), guarded text-to-SQL (MVP 3) |
| RAG | 36% | 43% | Hybrid retrieval over annual reports (MVP 1) |
| Prompt engineering | 29% | 33% | Structured, cited answers; query rewriting (MVP 1, 3) |
| LLM evaluation | 19% | 32% | Golden set, CI eval gate, Langfuse traces (every MVP) |
| Vector database · embeddings | 14% · 9% | 28% · 23% | pgvector + multilingual-e5 (MVP 1) |
| CI/CD · Docker | 16% · 11% | 19% · 15% | GitHub Actions, Docker Space (MVP 1 onward) |
| GCP (AWS / Azure for reference) | 14% (18 / 14) | 23% (28 / 25) | Not used in the zero-cost build; see §14 |
| LangGraph · LangChain | 5% · 9% | 20% · 24% | LangGraph from MVP 2 |
| MCP | 1% | 15% | MCP server stretch (MVP 5) |
| Multimodal AI · document AI/OCR | 4% · ~4% | 7% · ~3% | Page/table/chart crops, PaddleOCR (MVP 1) |
| Gemini · OpenAI API · Claude | 8% · 15% · 14% | 8% · 13% · 11% | Gemini by default behind a provider adapter |

Other findings that shape the design:
- "Agents and workflow automation" is the top use case (ID 42.5%), RAG/knowledge assistants the second.
- Credit risk appears in 13.8% of Indonesian postings vs 1.6% international; bank health signals in MVP 4 speak to it.
- Forecasting/time series is a use case in 20 postings; the MVP 4 forecast ladder is the classic-DS part of this project.
- Postings that name a document corpus mostly name financial and insurance paperwork (Kredivo, CoverGo, AME Research, Jatis Mobile).
- Communication is in 65% of Indonesian postings: the README write-up and demo are deliverables, not extras.

### Non-goals
- **No investment advice** until the owner decides otherwise at MVP 4: never buy / sell / hold calls, target prices or "undervalued" verdicts.
- No paid service of any kind. A feature that cannot run on a free tier waits or is cut.
- No user accounts or login. Public demo, rate-limited.
- No bypassing of bot protection, CAPTCHAs, or site terms to get data (see guardrail 1).
- No hosting or re-publishing of the companies' PDFs.
- No real-time or intraday prices.

## 2. Decision log (owner's calls, 2026-10-25)

| # | Area | Decision | Notes |
|---|---|---|---|
| D1 | Universe | Full LQ45, one frozen snapshot of the constituent list | Record the snapshot date; update only at MVP 5 |
| D2 | Years (annual reports) | Latest fiscal year first (FY2025); a second year at MVP 3 | More years later |
| D3 | Audience | Public demo, no login, rate-limited per visitor | |
| D4 | Language | Bahasa Indonesia + English; answer in the language asked | Golden set in both |
| D5 | Advice line | Analysis only until MVP 4, then the owner decides | |
| D6 | Cost | **Zero.** Free tiers only, limits written down in §4.1 | |
| D7 | Code host | GitHub, with GitHub Actions | |
| D8 | Front end | Next.js on Vercel Hobby | |
| D9 | Back end | FastAPI in a Docker Hugging Face Space (free CPU) | |
| D10 | Database | Supabase free Postgres + pgvector: chunks, vectors, facts, chat and agent history, rate limits, eval runs | |
| D11 | Files | WebP crops in Supabase Storage; PDFs not hosted, answers link to the source file on IDX | |
| D12 | Cache / Redis | None for now; rate limits and answer cache live in Postgres | Revisit only if latency or traffic demands it |
| D13 | LLM | Google Gemini free tier, behind a thin provider adapter | Model name in config, not code |
| D14 | Embeddings | `intfloat/multilingual-e5-small` (384 dims), runs inside the API container | |
| D15 | Parsing | `pdfplumber` for text; PaddleOCR (PP-StructureV3 / PaddleOCR-VL) for scanned pages, tables and charts (chart → table) | Hosted PaddleOCR API if Phase 0 confirms a free quota, else free Colab/Kaggle GPU |
| D16 | Retrieval | Hybrid: Postgres full-text + pgvector, merged by reciprocal rank fusion, after filtering by company and year | Reranker only if the golden set shows it helps |
| D17 | Orchestration | Plain Python + Gemini function calling in MVP 1; LangGraph from MVP 2 | |
| D18 | Eval / tracing | Versioned golden set scored by a script in CI + Langfuse free cloud tier | |
| D19 | Quarterly numbers | IDX XBRL/XLSX financial-statement filings | |
| D20 | Numeric access | Typed tools in MVP 2; guarded read-only text-to-SQL added in MVP 3 | |
| D21 | Prices | Daily closing prices from MVP 3 | Source chosen in Phase 0 |
| D22 | Charts | API returns chart spec + exact numbers; Next.js draws it (with a data table) | |
| D23 | Forecasting | Ladder: seasonal naive → statsforecast (ETS/ARIMA) → one pooled LightGBM; rolling backtests; ship only what beats the baseline; conformal intervals | |
| D24 | Signals | Piotroski F-score, Altman Z (non-banks), bank health checks + unusual-change flags + agent-retrieved explanation | |
| D25 | Chat memory | Store turns in Postgres; rewrite follow-ups into standalone questions; keep companies and periods in focus as structured state | MVP 3 |
| D26 | MCP | MCP server over the typed tools, stretch at MVP 5 | |
| D27 | Image → LLM | Text stand-in per figure (alias id, caption, chart-to-table data); the real crop is attached to the prompt only when OCR confidence is low or the question is about a visual trend. Alias in the prompt, storage path in the DB | §6.1 |
| D28 | Image input | Users cannot upload images | |
| D29 | Chunking | Section-aware chunks (~300–450 tokens, never crossing a heading), tables/charts as their own chunks, metadata header on every chunk, small-to-big expansion at answer time; per-page fallback | §6.2 |
| D30 | Bilingual reports | Keep both languages, linked by `pair_id`; collapse pairs at retrieval and quote in the question's language | §6.2 |
| D31 | Query transforms | Per-entity split (in code) + bilingual second query; HyDE / multi-query only if eval shows misses | §6.3 |
| D32 | Entity detection | Alias table + regex for periods; small LLM extraction only when ambiguous | §6.3 |
| D33 | No company named | Search all 45 with ≤ 2 chunks per company and say which were covered; numeric versions route to tools from MVP 2 | §6.3 |
| D34 | Context size | k = 6 after expansion, ~4k-token budget; 4/8/12 as an ablation | §6.3 |
| D35 | Architecture | MVP 1 fixed pipeline; MVP 2+ router (`numbers` / `reports` / `both`) + bounded plan-and-execute (≤ 4 tool calls, ≤ 1 re-plan, ≤ 1 repair) in LangGraph. No open-ended ReAct loop | §6.4 |
| D36 | Verification failure | Code checks + exactly one repair attempt with the errors listed; still failing → dropped; nothing left → refusal. Repair rate is logged | §6.4 |
| D37 | Streaming | Server-sent progress steps, then the verified answer in one piece | §6.4 |
| D38 | Transparency | Collapsed "how I answered" panel: plan, tool calls with arguments, retrieved pages, checks passed/failed. No raw model reasoning | §6.4 |
| D39 | Model tiering | Small free-tier model for routing, entity fallback, translation, planning; strongest free-tier model for final answers | §6.5 |
| D40 | LLM judge | A different free model, rubric-based, trusted only after ≥ 85% agreement with ~50 owner labels | §6.6 |
| D41 | User feedback | Thumbs up/down + optional reason, linked to the trace; thumbs-down answers become golden-set candidates after owner review | §6.6 |
| D42 | Prompts | Versioned files in the repo; prompt version logged on every trace and eval run; changes go through PRs and the eval gate | §6.5 |

### Phase 0 sign-off (owner, 2026-10-25)

These amend the rows above where they conflict. Evidence is in `docs/phase0_findings.md`.

| # | Area | Decision | Amends |
|---|---|---|---|
| D43 | Annual-report source | Polite scripted download from **company IR sites**, after a per-site robots.txt/terms check. IDX's terms forbid scraping, so nothing is scripted against idx.co.id. Citations link to the IR copy | D11, guardrail 1 |
| D44 | LQ45 snapshot | Frozen list effective 2026-08-03 → 2026-10-30 (`corpus/lq45_snapshot.csv`). LQ45 is rebalanced quarterly | D1, §5 |
| D45 | Back-end host | Existing Docker Space `rifqih/tanya-emiten-api` (renamed from `churn-mlops`; new Docker Spaces need PRO) | D9 |
| D46 | Vector storage | `halfvec(384)` + expression GIN index on `to_tsvector('simple', text)` (no stored tsvector). Revisit at MVP 3 | §4.1, §7 |
| D47 | OCR backend | Hosted PaddleOCR API (`PaddleOCR-VL-1.6`), ≤ 100 pages per job, 20k pages/day. Colab GPU is the fallback | D15 |
| D48 | Models | `answer` = `gemini-3.5-flash-lite`; `small` = `gemini-3.1-flash-lite`; `judge` = Groq `qwen/qwen3.8-27b`, backup `gemma-4-31b-it`. Dedicated Google project recommended | D13, D39, D40 |
| D49 | Price source | None until MVP 3 | D21 |
| D50 | Golden set | Claude drafts every question with expected pages (marked draft); the owner reviews, edits or rejects them before they count | §10 MVP 1b, §14 |
| D51 | Quarterly XLSX/XBRL | IDX-only; source decided at the start of MVP 2 (manual, or written permission from IDX) | D19 |
| D52 | DB connection | Supabase Session pooler URI (IPv4) everywhere; the direct host is IPv6-only | §4 |
| D53 | Crops | Store WebP crops of **tables and charts** (bbox) plus whole-page crops of **scanned pages** only. Text-only claims show the verified quote and a link to the source PDF page. Every-page crops (~1.5 GB at 800 px) don't fit the 1 GB Storage limit | D11, §6.1, MVP 1a |

### MVP 1 decisions (owner, 2026-10-26)

| # | Area | Decision | Amends |
|---|---|---|---|
| D54 | Database host | All Postgres tables on **Neon** free (1 GB per project since 2026-10-02, pgvector). Supabase keeps **Storage** (figure images) only. Measured: 45 reports ≈ 93k chunks ≈ 410 MB after rebuilding the FTS index (≈ 4.4 KB/chunk), i.e. 82% of Supabase's 500 MB but 41% of Neon's 1 GB. The weekly keep-alive pings Supabase (`SUPABASE_DB_URL`), whose Storage pauses with the project | D10, D52 |
| D55 | Parser | Owner's hybrid-parser design: every page read twice (pdfplumber characters + PaddleOCR-VL layout); PaddleOCR decides regions, reading order and headings; the PDF's characters fill them, OCR text only where the PDF has none (flagged); table area = PaddleOCR's box, grid from ruled lines (≥ 60% cover) else PaddleOCR's table (≥ 80% of the PDF's characters, numbers repaired from the PDF) else whitespace columns; OCR jobs ≤ 100 pages and ≤ 3 MB; a per-page quality check (character coverage, OCR-only pages, table agreement with PaddleOCR). Records stay ~300–450-token chunks (§6.2), not 3-page windows, because e5-small reads 512 tokens | D15, D47, §6.1, §6.2 |
| D56 | Figure images | WebP crops of **charts and diagrams** only (PaddleOCR `chart` blocks, and `image` blocks holding text from the PDF). Tables are text chunks; photos, portraits and whole scanned pages get no image. Tables were 91% of crop bytes under D53 | D53 |
| D57 | Chart values | A chart's values (PaddleOCR chart → table) enter its chunk only when ≥ 80% of its numbers appear in the PDF's own text inside the chart box (years excluded). Below that the chunk keeps the caption and says the values are unverified; the image crop is still shown. Measured on 6 reports: 44 of 70 charts pass; failures are raster charts and unlabelled bars whose values PaddleOCR estimates or invents | D55, guardrail 2 |
| D58 | UI styling | Tailwind CSS (no component library) | MVP 1d |

## 3. Guardrails (hard rules)

1. **Polite, permitted data access only.** Check `robots.txt` and the site's terms before scripting any download. ≥ 5 s between requests, honest User-Agent, small batches, resume from where it stopped. **If IDX's bot protection blocks scripted access, do not work around it**: no headless-browser evasion, CAPTCHA solving or proxy rotation. Fall back to the owner downloading files by hand into `corpus/inbox/`, and say so in the README.
2. **Numbers come from tables, never from PDF text.** From MVP 2 onward every number in an answer comes from the `facts` or `prices` tables or a ratio computed from them, with its formula and source filing shown. In MVP 1 (before tables exist) a number may appear only as a verbatim, verified quote with its page.
3. **No uncited claims.** Every sentence of a narrative answer cites a chunk id and carries a verbatim quote from that chunk, verified in code. A claim that fails verification is dropped; an answer left with nothing becomes a refusal that lists the closest pages found.
4. **Images are evidence, not decoration.** An answer may only show crops of figures or pages that were retrieved for that question. Checked in code; a crop outside the retrieved set is removed.
5. **Refuse when unsupported**, in the user's language. This includes advice requests ("should I buy BBRI?") until the owner changes D5.
6. **Retrieved text is data, not instructions.** Report text never changes the system prompt or tool behaviour.
7. **Zero cost, enforced.** Every external service has its free-tier limits recorded in §4.1 and a guard in code (daily caps, backoff on quota errors). Cache every LLM call (key = prompt hash + model). Log tokens per request.
8. **Provider-agnostic, keys in env.** No hardcoded provider, model or key. All LLM calls go through one adapter interface.
9. **Privacy.** Rate limiting stores a salted hash of the visitor's IP, never the IP itself. Chat logs hold no personal data beyond the question text; the UI says questions are logged.
10. **Owner decides.** See the note at the top.

## 4. Stack

Back end and ingestion (Python ≥ 3.12, managed with `uv`):
- `pdfplumber` (text and simple tables), `pymupdf` only to render page images for crops
- `paddleocr` (PP-StructureV3, PaddleOCR-VL) on GPU or via the hosted API, for scanned pages, complex tables and charts
- `sentence-transformers` with `intfloat/multilingual-e5-small` (use the `query: ` / `passage: ` prefixes)
- `psycopg` 3 + `pgvector`; Supabase Postgres; Postgres full-text search (`simple` config) for the lexical side
- `google-genai` SDK behind `LLMClient`; a second adapter (OpenAI-compatible) kept minimal so the provider can be swapped
- `pydantic` v2 for every structured output, `pyyaml` for config
- `fastapi` + `uvicorn`; `langgraph` from MVP 2; `arelle` or `lxml` for XBRL (Phase 0 decides, see §4.2)
- `statsforecast`, `lightgbm`, `pandas` for MVP 4
- `langfuse` SDK for tracing
- `pytest`, `ruff`

Front end: Next.js (App Router, TypeScript), a charting library (Recharts by default), deployed on Vercel Hobby.

Hosting: GitHub (code, Actions), Hugging Face Space (Docker, FastAPI), Supabase (Postgres, Storage), Vercel (Next.js), Langfuse Cloud (traces). Ingestion runs offline on the owner's laptop, or on Colab/Kaggle for GPU steps, and writes to Supabase.

### 4.1 Free-tier budget (fill in exact numbers in Phase 0; do not assume)

| Service | What we use | Limits to record | Known behaviour to design around |
|---|---|---|---|
| Gemini API (free tier) | Answers, query rewrite, routing, LLM judge | Requests/min, requests/day, tokens/min per model | Free-tier prompts may be used by Google to improve products: fine for public reports, never send personal data |
| Supabase (free) | Postgres + pgvector, Storage | DB size (≈ 500 MB), storage (≈ 1 GB), egress | Project pauses after a period of inactivity → weekly keep-alive Action |
| Hugging Face Space (free CPU) | FastAPI + e5 model | CPU/RAM, sleep timeout | Sleeps when idle; cold start includes loading e5 → show "waking up" state in the UI |
| Vercel Hobby | Next.js | Bandwidth, function limits, non-commercial use | API calls go to the Space, not Vercel functions |
| Langfuse Cloud (free) | Traces, scores | Events/month, retention | Sample traces if the limit is near |
| GitHub Actions | CI, eval gate, keep-alive, refresh (MVP 5) | Free minutes (public repo) | Keep the eval subset small on PRs |
| PaddleOCR hosted API | Charts/tables, if available | Free quota, terms | Fallback: Colab/Kaggle GPU |
| Colab / Kaggle | GPU for PaddleOCR | Session length, weekly GPU hours | Make OCR jobs resumable |

Storage estimate for D1 + D2: ~45 reports × ~300 pages ≈ 13k pages → ~40–60k chunks × (384-dim vector + text + index) ≈ 150–250 MB. Phase 0 measures the real number; if it exceeds 70% of the DB limit, stop and ask (options: `halfvec`, fewer chunks per page, dropping one language half of bilingual pages).

### 4.2 Facts to verify in Phase 0 (do not assume)
1. **IDX filings access**: where annual-report PDFs and financial-statement XBRL/XLSX files are linked per ticker and period; how far back they go (expected: XBRL mandatory since Nov 2015; the website selector reportedly shows ~3 years); whether `robots.txt`, terms and bot protection allow polite scripted downloads.
2. **XBRL contents**: which IDX taxonomy templates appear in LQ45 (general, bank, insurance, financing, securities); whether the XLSX files are easier to parse than the XBRL instance; which line items map to the metric dictionary (§5).
3. **Bank ratios**: whether NPL, NIM, CAR, LDR are in the XBRL facts or only in notes/report pages.
4. **The current LQ45 constituent list** and its effective period.
5. **Free-tier limits** for every row of §4.1, and the current Gemini model names on the free tier.
6. **PaddleOCR hosted API**: whether a free quota exists, its limits and terms. Otherwise time PaddleOCR on one report on Colab's free GPU.
7. **Report layout**: share of pages with < 200 extractable characters; how many reports are bilingual side-by-side vs separate language sections; typical size of a report.
8. **Price source (for MVP 3)**: IDX daily trading summary vs Yahoo Finance (`yfinance`): history depth, terms of use, reliability.

## 5. Domain notes (IDX and Indonesian financial reporting)

- **Report types.** *Laporan Tahunan* (annual report): narrative, management discussion (MD&A), governance, often bilingual, 200–500 pages, many charts and photos. *Laporan Keuangan* (financial statements): quarterly; Q1 and Q3 usually unaudited, half-year sometimes reviewed, full year audited. The annual report embeds the audited full-year statements.
- **Filing deadlines** (verify against current OJK rules in Phase 0): quarterly statements roughly 1–3 months after quarter end depending on audit status; audited annual statements by the end of March; annual reports by the end of April. MVP 5's refresh schedule follows these.
- **Year-to-date figures.** Income and cash-flow statements are cumulative: Q2 = 6 months, Q3 = 9 months, Q4 = full year. Derive single quarters: Q1 = 3M, Q2 = 6M − 3M, Q3 = 9M − 6M, Q4 = FY − 9M. Balance-sheet items are point-in-time and are not differenced. Store both `ytd` and `q` values with a `period_type` column.
- **Sector templates.** Banks have no "revenue": the metric dictionary maps *pendapatan bunga* (interest income), *beban bunga*, *pendapatan bunga bersih* (net interest income), loans (*kredit yang diberikan*), deposits (*dana pihak ketiga*), etc. Insurers and financing companies have their own templates. Each canonical metric lists the template-specific line items that feed it.
- **Units and currency.** Filers report in full Rupiah, thousands or millions; some (mostly mining and energy) report in USD. Every fact stores `currency` and `unit_multiplier`. Never convert currency silently; cross-currency comparisons say so and use a stated rate.
- **Restatements.** A later filing may restate prior-period comparatives. Keep every version (`source_filing_id`); "current" = latest filing for that period.
- **Bank health metrics.** NPL gross/net, NIM, CAR (KPMM), LDR, BOPO, CASA ratio. Often reported only in notes or report pages: in MVP 2 these become facts extracted from report tables, tagged `source = report_table` with page, and checked by hand for the golden set.
- **Fundamental scores (MVP 4).** Piotroski F-score (nine binary tests on profitability, leverage/liquidity, efficiency). Altman Z (manufacturing/non-financial variants; **not for banks or insurers**). Banks get a separate health checklist: NPL trend, CAR buffer over the regulatory minimum, LDR range, NIM trend.
- **LQ45** is re-balanced every February and August (verify). Tickers also change names or merge; keep `companies.ticker_history`.
- **Naming.** Use the four-letter IDX ticker as the company key (BBCA, BBRI…). Accept common names and Bahasa aliases in questions ("Bank Mandiri", "BRI", "Telkom").

## 6. Architecture

```
            ┌──────────────── offline ingestion (laptop / Colab) ───────────────┐
IDX PDFs ──►│ fetch → classify pages → pdfplumber | PaddleOCR → chunks + crops │──► Supabase Postgres (chunks, vectors, facts)
IDX XBRL ──►│ fetch → parse XBRL/XLSX → map to metric dictionary → checks       │──► Supabase Storage (WebP crops)
            └───────────────────────────────────────────────────────────────────┘
Browser ──► Next.js (Vercel) ──► FastAPI (HF Space: e5 model, agent, tools) ──► Supabase · Gemini · Langfuse
```

- **Answer flow (MVP 1):** rate-limit check → detect language → resolve companies/years → filtered hybrid retrieval → Gemini structured answer (claims + quotes + figure ids) → verify quotes and figure ids → response with crop URLs (crops sit in a public-read bucket, since they are excerpts of public reports; the Space never holds the Supabase service key).
- **Answer flow (MVP 2+):** a LangGraph router chooses `numbers`, `reports` or `both`; numeric tools query `facts`; narrative goes through the MVP 1 pipeline; the composer merges them, adds a chart spec, and runs the same verification.

### 6.1 Figures and how the LLM "sees" them (D27)
- Every table, chart and cited page gets a `figures` row with a short deterministic alias, e.g. `BBRI-25-p212-c1` (ticker, 2-digit year, page, kind letter `c` chart / `t` table / `p` page, index). The alias is the only image reference that ever enters a prompt; `storage_path` stays in the DB and the API turns it into a URL.
- Each figure also gets a **figure chunk**, which is what is embedded, searched and read by the LLM:
  ```
  [FIGURE BBRI-25-p212-c1 | chart | BBRI Annual Report 2025 | p.212
   Section: Analisis dan Pembahasan Manajemen > Kualitas Kredit]
  Caption: Grafik Kualitas Kredit 2021–2025
  Data: | Tahun | NPL gross | NPL net | ... |      ← PaddleOCR chart-to-table / table markdown
  ```
- The caption is the nearest title-like text above or below the bbox (parser heuristic); if none is found, use the section heading and say `Caption: (none found)`.
- **Vision fallback:** `figures.ocr_confidence` is stored. The real crop is attached to the answer prompt (≤ 2 images) only when a retrieved figure has confidence below `parsing.vision_fallback_below`, or the router/entity step flags a visual-trend question. Count fallbacks per answer.
- The answer cites figures by alias; code checks each alias is in the retrieved set (guardrail 4).
- Not used: image embeddings (CLIP/SigLIP) and page-image retrieval (ColPali): too heavy for free CPU hosting. Mention in the README's "with a budget" section.

### 6.2 Chunking (D29, D30)
- **Section detection:** parse the report's table of contents where present; otherwise detect headings by font size/weight relative to the page's body text (pdfplumber character metadata). Each chunk stores `section_path` (e.g. `MD&A > Kualitas Kredit`).
- **Text chunks:** 300–450 tokens, split at paragraph then sentence boundaries, never across a heading; may cross a page break (store `page_start`, `page_end`); ~50-token overlap between consecutive chunks of the same section.
- **Tables and charts:** their own chunks; a table longer than the limit is split by rows, repeating the header row in each piece.
- **Contextual header:** prepend `[ticker | report | fiscal year | section_path | p.N]` to every chunk's text before embedding and indexing (built from metadata, no LLM).
- **Small-to-big:** at answer time each selected chunk is expanded with its previous and next chunk in the same section, within the token budget.
- **Fallback:** if a report yields no usable headings, chunk per page (split long pages) with overlap; log which reports used it.
- **Bilingual:** detect language per chunk. For side-by-side or paired sections, link the two language versions with `pair_id`. Retrieval collapses a pair to one result and the quote comes from the version in the question's language when it exists.
- **Ablation (MVP 1 eval):** compare against per-page and fixed-400-token chunking.

### 6.3 Retrieval pipeline (D16, D31–D34)
1. **Understand:** detect language; resolve companies with the alias table (`companies.aliases`: tickers, full names, short names like "BRI", "Mandiri"), years and quarters with regex; only an ambiguous question goes to the small model for structured extraction.
2. **Transform:** one retrieval per resolved ticker (entity split), results merged; a translated second query (small model) feeds the lexical side.
3. **Filter first:** `ticker`, `fiscal_year`, `doc_type` in the WHERE clause, before ranking.
4. **Lexical:** Postgres full-text search, `simple` config (no Indonesian stemmer exists in Postgres), `ts_rank_cd`, top 20.
5. **Dense:** e5 embedding of `"query: " + question`; pgvector cosine with an HNSW index, top 20. Passages were embedded as `"passage: " + text`.
6. **Fuse:** reciprocal rank fusion, `score = Σ 1 / (60 + rank)`.
7. **Rerank:** off (D16) until the MVP 3 experiment.
8. **Clean up:** collapse bilingual pairs, drop near-duplicates, at most 2 chunks per page; when no company is named, at most 2 per company (D33) and the answer lists the companies covered.
9. **Expand and pack:** small-to-big, then the top 6 into a ~4k-token budget, strongest first.
- Metrics: recall@k, MRR and nDCG against owner-labelled pages; ablations: lexical-only, dense-only, hybrid; with/without transforms; k = 4/6/8/12.

### 6.4 Agent architecture (D35–D38)
- **MVP 1 (fixed pipeline):** understand → retrieve → generate (structured) → verify → [repair once] → respond.
- **MVP 2+ (LangGraph):** `understand → route → {numbers | reports | both}`. `both` and comparison questions go to a **planner** (small model) that outputs a JSON plan of typed tool calls; an executor validates arguments and runs them (in parallel where independent); a **composer** (answer model) writes the answer from tool results and retrieved chunks; then the same verifier. Limits: ≤ 4 tool calls, ≤ 1 re-plan (when a tool errors or returns empty), ≤ 1 repair. Exceeding a limit returns the partial verified answer plus what could not be done.
- **Tool calling:** the model only proposes `{name, args}`; code validates args with pydantic, executes read-only functions and returns results as tool messages. The model never touches the DB.
- **Verifier (code):** quotes are normalised substrings of their chunk; figure aliases are in the retrieved set; every number in the answer text appears in a tool result or a verified quote; the language matches the question; refusal policy (advice requests). Failures are sent back once with exact error messages; whatever still fails is dropped.
- **Streaming:** `POST /ask` streams server-sent events: `step` events (understanding, searching BBRI 2025, fetching NPL, checking citations) and one final `answer` event with the verified payload.
- **"How I answered" panel:** plan, tool calls and arguments, retrieved pages with scores, checks passed/failed, repair used or not, prompt version. No raw chain-of-thought.

### 6.5 Prompting and models (D13, D39, D42)
- **Prompt order:** system (role, rules, citation and refusal policy, language, output schema) → data blocks in tags (`<chunk id=… page=…>`, `<figure id=…>`, `<tool_result tool=…>`) → 1–2 short examples (a cited answer, a refusal) → the question last.
- **Structured output:** pydantic models → Gemini response schema; validate; on failure retry up to `llm.max_retries_schema` with the validation error.
- **Sampling:** temperature 0 for every step; answers are still not bit-identical across runs, so evals report means over the golden set.
- **Tiering:** `llm.models.small` for routing, entity fallback, translation and planning; `llm.models.answer` for composing; `llm.models.judge` for evaluation. Names come from Phase 0's free-tier check.
- **Prompts:** `prompts/{name}.v{N}.md` (system, router, planner, entity, translate, judge); the active version is set in config and logged with every trace and eval run.
- **Injection defence:** retrieved text only inside data tags with an instruction that tag contents are data; read-only tools; code verification before display; no secrets in prompts.

### 6.6 Evaluation (D18, D40, D41)
- **Offline (CI and on demand):** golden set → retrieval metrics (§6.3); answer metrics: quote-verified rate, claim-supported-by-quote (judge), answer correctness vs reference (judge), numeric exact match, refusal accuracy, router accuracy (MVP 2), follow-up rewrite accuracy (MVP 3); cost metrics: latency p50/p95, tokens per question, repair rate, vision-fallback rate. Results land in `eval/reports/` and `eval_runs`.
- **Judge:** a different free model behind the adapter; rubric prompts versioned like the others; calibrated on ≥ 50 answers labelled by the owner; used for scoring only when agreement ≥ 85%. The README reports the agreement number.
- **Online:** Langfuse traces for every answer; dashboards for refusal rate, repair rate, quota errors, latency; thumbs up/down with optional reason stored in `feedback` and linked to the trace. Thumbs-down answers are reviewed by the owner and may join the golden set.
- **Gate:** PRs run a `pr_subset_size` subset; MVP 5 makes a > 2-point drop fail CI.

## 7. Data model (Postgres; migrations committed)

- `companies(ticker PK, name, aliases[], sector_idxic, subsector, template, reporting_currency, lq45_snapshot_date, ticker_history jsonb)`
- `documents(doc_id PK, ticker, doc_type [annual_report|fin_statement], fiscal_year, period, source_url, sha256, pages, lang_layout, fetched_at)`
- `pages(doc_id, page_no, kind [text|table|chart|image|scanned|mixed], char_count, parser)`
- `chunks(chunk_id PK, doc_id, ticker, fiscal_year, page_start, page_end, section_path, seq, kind [text|table|chart], lang, pair_id null, text, tsv tsvector, embedding vector(384), figure_id null, chunker [section|page])`
- `figures(figure_id PK /* alias, e.g. BBRI-25-p212-c1 */, doc_id, page_no, kind [page|table|chart], bbox, storage_path, caption, chart_table_md, ocr_confidence)`
- `metric_dictionary(metric PK, label_id, label_en, unit_kind, templates jsonb, formula null, description)`
- `facts(ticker, metric, period_end, period_type [q|ytd|fy|instant], value numeric, currency, unit_multiplier, source [xbrl|xlsx|report_table], source_filing_id, page_no null, loaded_at, is_current bool)`
- `prices(ticker, date, close, volume, source)` (MVP 3)
- `conversations(conv_id, created_at, visitor_hash)`, `messages(conv_id, turn, role, content, lang, focus jsonb, prompt_version, trace_id, created_at)`
- `feedback(conv_id, turn, rating [up|down], reason null, created_at)`
- `tool_calls(conv_id, turn, tool, args jsonb, result_summary, latency_ms, ok)`
- `rate_limits(visitor_hash, day, count)`, `answer_cache(key PK, response jsonb, created_at)`
- `eval_runs(run_id, git_sha, phase, metrics jsonb, created_at)`
- `forecasts(ticker, metric, model, origin, horizon, period_end, mean, lo, hi)`, `signals(ticker, period_end, signal, value, severity, explanation_chunk_ids[])` (MVP 4)

## 8. Folder structure (monorepo)

```
tanya-emiten/
├── TANYAEMITEN.md
├── config.yaml
├── run.py                  # CLI (§11)
├── backend/
│   ├── llm.py              # LLMClient + Gemini and OpenAI-compatible adapters + cache + quota guard
│   ├── db.py               # connection, migrations runner
│   ├── migrations/         # numbered .sql files
│   ├── ingest/
│   │   ├── fetch.py        # polite downloader + manifest
│   │   ├── pages.py        # page classification
│   │   ├── parse_pdf.py    # pdfplumber text/tables
│   │   ├── ocr.py          # PaddleOCR (API or local GPU), chart → table, crops
│   │   ├── chunk.py
│   │   ├── embed.py
│   │   └── xbrl.py         # MVP 2: filings → facts
│   ├── retrieval.py        # filters, FTS, vector, RRF
│   ├── answer.py           # prompts, structured answer, quote + figure verification, refusal
│   ├── tools.py            # MVP 2: get_metric, compare_peers, compute_ratio, ...
│   ├── agent.py            # MVP 2: LangGraph router/composer
│   ├── forecast.py         # MVP 4
│   ├── signals.py          # MVP 4
│   ├── api.py              # FastAPI
│   └── mcp_server.py       # MVP 5 stretch
├── prompts/                # versioned prompt files: system.v1.md, router.v1.md, planner.v1.md, judge.v1.md, ...
├── web/                    # Next.js app
├── notebooks/ocr_colab.ipynb   # GPU OCR job, resumable
├── corpus/
│   ├── manifest.csv        # committed: doc_id, ticker, type, year, period, source_url, sha256
│   ├── lq45_snapshot.csv   # committed
│   ├── inbox/              # gitignored: manual downloads
│   └── pdf/, xbrl/         # gitignored
├── eval/
│   ├── golden.jsonl        # committed, hand-checked
│   └── reports/            # committed: eval_YYYYMMDD.md
├── tests/
├── data/                   # gitignored: parsed json, llm cache, logs
├── Dockerfile              # HF Space image (API + e5 weights baked in)
└── .github/workflows/      # ci.yml, keepalive.yml, refresh.yml (MVP 5)
```

Env vars (`.env`, gitignored; `.env.example` committed): `LLM_PROVIDER`, `LLM_API_KEY`, `JUDGE_PROVIDER`, `JUDGE_BASE_URL`, `JUDGE_API_KEY`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_SERVICE_KEY` (ingestion only, never in the Space), `SUPABASE_ANON_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_HOST`, `IP_HASH_SALT`, `PADDLEOCR_API_KEY` (optional). Front end: `NEXT_PUBLIC_API_URL` only.

## 9. config.yaml (initial values)

```yaml
universe:
  index: LQ45
  snapshot_file: corpus/lq45_snapshot.csv
annual_reports:
  fiscal_years: [2025]           # D2; add 2024 at MVP 3
fetch:
  request_delay_seconds: 5
  user_agent: "TanyaEmiten research bot (contact: see README)"
parsing:
  min_text_chars: 200            # below this a page goes to OCR
  ocr_backend: auto              # api | local_gpu; Phase 0 decides
  crop_format: webp
  crop_max_width: 1400
  vision_fallback_below: 0.80    # D27: attach the real crop when ocr_confidence is lower
  vision_max_images: 2
chunking:
  strategy: section              # D29; fallback: page
  min_tokens: 300
  max_tokens: 450
  overlap_tokens: 50
  tables_own_chunk: true
  contextual_header: true
  expand_neighbours: 1           # small-to-big: chunks added on each side
retrieval:
  query_transforms: [entity_split, bilingual]   # D31
  k_lexical: 20
  k_dense: 20
  rrf_k: 60
  final_k: 6                     # D34
  context_token_budget: 4000
  max_per_page: 2
  max_per_company_when_unscoped: 2   # D33
  min_score: null                # set from eval data, not guessed
  reranker: null                 # D16: only if eval justifies
embedding:
  model: intfloat/multilingual-e5-small
  dims: 384
llm:
  models:                        # D39; names filled after the Phase 0 free-tier check
    small: null
    answer: null
    judge: null                  # D40: a different model from `answer`
  prompt_versions: {system: 1, router: 1, planner: 1, entity: 1, translate: 1, judge: 1}
  temperature: 0
  max_output_tokens: 900
  max_retries_schema: 2
agent:                           # D35, D36
  max_tool_calls: 4
  max_replans: 1
  max_repairs: 1
limits:
  questions_per_visitor_per_day: 20
  global_questions_per_day: null # set below the Gemini free-tier daily limit in Phase 0
eval:
  pr_subset_size: 25
forecast:                        # MVP 4
  horizon_quarters: 4
  backtest_origins: 8
  interval: 0.8
```

## 10. Phases

### Phase 0 — Setup and scouting (no product code yet)
- Repo on GitHub, `uv` project, `.gitignore`, `.env.example`, `ruff` + `pytest` in CI.
- Create the Supabase project (enable `vector`), HF Space (Docker), Vercel project, Langfuse project. Record every free-tier limit in `docs/free_tier.md` (§4.1).
- Answer every item in §4.2 and write the findings to `docs/phase0_findings.md`, with links and dates.
- Download 3 sample annual reports (one bank, one consumer, one USD reporter) and their latest quarterly XBRL/XLSX. Measure page kinds, bilingual layout, OCR time per page, chunk count, and projected DB size.
- Smoke-test `LLMClient` (Gemini) with one structured call; smoke-test e5 embeddings in the Space image.

**Acceptance**
- [ ] `docs/phase0_findings.md` answers all 8 items of §4.2; anything unresolved is listed with a proposed fallback.
- [ ] `docs/free_tier.md` has a number for every limit in §4.1.
- [ ] `corpus/lq45_snapshot.csv` committed with its effective date.
- [ ] Projected DB size for D1 + D2 is under 70% of the Supabase limit, or the owner has chosen a mitigation.
- [ ] **Owner sign-off** on the findings before MVP 1 starts (access method, OCR backend, price source).

### MVP 1 — Ask the annual report
**1a. Ingest.** Fetch FY2025 annual reports for all 45 companies (guardrail 1). Classify each page; parse text pages with pdfplumber; send scanned/table/chart pages to PaddleOCR; convert charts to tables (PP-Chart2Table / PaddleOCR-VL); render crops for tables, charts and every page (page crops at low resolution); upload crops to Storage; write `figures` rows with aliases and OCR confidence (§6.1). Chunk as in §6.2 (section-aware, figure chunks, contextual headers, bilingual pairs). Embed and load.

**1b. Golden set and retrieval.** The owner writes ≥ 80 questions (Claude may draft candidates, marked as drafts until the owner edits them): ≥ 30% Bahasa, ≥ 15 needing a table or chart, ≥ 10 unanswerable from the corpus, ≥ 10 advice requests that must be refused, spread over ≥ 20 tickers. Each has expected doc + pages. Build the retrieval pipeline of §6.3; report recall@6, MRR and nDCG for lexical-only, dense-only and hybrid, plus the chunking (§6.2) and k ablations.

**1c. Answers with verified citations and crops.** Structured answer: `claims[{text, chunk_ids, quote}]`, `figures[{figure_id, why}]`, `lang`, `refusal`. Prompts from versioned files (§6.5). Verify as in §6.4 with one repair attempt; drop what still fails; refuse when nothing survives. Vision fallback per §6.1. Disclaimer line in every answer.

**1d. API, UI, deploy.** FastAPI `POST /ask` (server-sent `step` events, then one `answer` event; §6.4), `POST /feedback`, `GET /health`, `GET /companies`; rate limiting and answer cache in Postgres; Langfuse trace per request. Next.js chat page: live progress steps, answer with inline crops (click to enlarge, link to the source PDF on IDX and page number), citation chips, collapsed "how I answered" panel, thumbs up/down with optional reason, language follows the question, "waking up" state for cold starts.

**1e. Judge calibration.** The owner labels ≥ 50 answers (claim supported? answer correct?); run the judge on the same answers and report agreement (§6.6). CI: lint, tests, eval subset on PRs; full eval on demand. Weekly keep-alive Action.

**Acceptance**
- [ ] All 45 FY2025 reports ingested, or the missing ones listed with the reason.
- [ ] Hybrid recall@6 ≥ 0.80 overall and ≥ 0.75 on Bahasa questions; hybrid ≥ the better single method.
- [ ] 100% of displayed quotes verified; 100% of displayed crops come from the retrieved set (both enforced in code, with tests).
- [ ] Refusal rate ≥ 90% on unanswerable questions and 100% on advice requests.
- [ ] Judge–owner agreement ≥ 85% on ≥ 50 labelled answers; judge scores reported only if it passes.
- [ ] Ablation table committed: retrieval method × chunking × k.
- [ ] Owner checks 20 random answers with images: ≥ 16 have a crop that actually helps.
- [ ] Public demo on Vercel + HF Space; p50 latency on a warm Space ≤ 10 s; rate limit verified.
- [ ] `eval/reports/eval_*.md` committed; README has a first "how good is it" section with these numbers.

### MVP 2 — Add the numbers
- Fetch quarterly XBRL/XLSX filings for all 45 companies, as far back as Phase 0 found (target: 2015 onward, at least 12 quarters).
- `metric_dictionary`: ≥ 25 canonical metrics covering the general and bank templates (revenue / interest income, gross profit, operating profit, net profit attributable, total assets, liabilities, equity, cash from operations, capex, loans, deposits, NII…), each with labels in both languages and the line items it maps from.
- Load `facts` with YTD → single-quarter derivation, currency, units, restatement versions; bank ratios from report tables tagged as such.
- Load checks: balance identity (assets = liabilities + equity within 0.5%), four quarters sum to the full year, > 10× jumps flagged for review.
- Typed tools: `get_metric(ticker, metric, periods)`, `compare_peers(tickers, metric, period)`, `compute_ratio(ticker, ratio, periods)` (formula from the dictionary), `list_metrics()`.
- LangGraph router + bounded planner (§6.4): classify `numbers | reports | both`; `both` and comparisons go through plan-and-execute with the limits in config; numeric answers include a chart spec + data table; the plan and tool calls appear in the "how I answered" panel.
- Extend the golden set with ≥ 40 numeric questions (exact expected values, hand-checked from filings) and ≥ 15 mixed questions.

**Acceptance**
- [ ] ≥ 95% of filings pass the balance identity; failures listed in `eval/reports/data_quality_*.md`.
- [ ] Numeric golden questions: ≥ 95% exact (after unit rounding) with correct source filing cited.
- [ ] Router accuracy ≥ 90% on the labelled golden set.
- [ ] No number in any answer that does not come from a tool result (checked in code: every number in the text appears in the tool outputs).
- [ ] UI renders the chart and its data table; MVP 1 metrics do not regress by more than 2 points.

### MVP 3 — Compare and remember
- Peer groups from the IDX-IC sector classification; sector medians in `compare_peers`.
- Daily closing prices (source from Phase 0); valuation ratios P/E, P/BV, dividend yield with formulas and the price date shown.
- Second year of annual reports (FY2024).
- Guarded read-only text-to-SQL: a documented read-only view schema, a read-only DB role, row limit, statement timeout, SQL parse check (single `SELECT` on allowed views); used only when no typed tool fits.
- Chat memory (D25): store turns; rewrite follow-ups into standalone questions; carry `focus = {tickers, periods, metrics}`.
- Reranker experiment (D16): add a free multilingual cross-encoder only if it lifts recall@6 or answer correctness by ≥ 3 points without breaking the latency target; record the result either way.

**Acceptance**
- [ ] ≥ 20 golden follow-up pairs: rewritten question correct in ≥ 90%.
- [ ] Text-to-SQL golden set (≥ 20): ≥ 85% correct results; 0 write or multi-statement queries executed (tests prove the guards).
- [ ] Valuation ratios match a hand calculation for 10 sampled ticker-dates.
- [ ] Reranker decision recorded in the eval report.

### MVP 4 — Forecasts and signals
- **Owner decision first:** the advice line (D5). Implement nothing advice-like until it is recorded in §2.
- Forecast ladder (D23) for 3–5 headline metrics per template, horizon 4 quarters: seasonal naive → `statsforecast` ETS/AutoARIMA per series → one pooled LightGBM across all companies (lags, seasonality, sector, size features). Rolling-origin backtest over the last 8 origins; metric MASE vs seasonal naive; conformal 80% intervals. Ship per metric only the model that beats the baseline; otherwise ship the baseline and say so.
- Signals (D24): Piotroski F-score, Altman Z for eligible non-financials, bank health checklist; unusual-change flags (robust z-score vs own history and vs sector peers). For each flag the agent retrieves the report passages that explain it and cites them; if none are found it says "no explanation found in the report".
- UI: forecast chart with interval band and backtest score; signal cards with formula, inputs, and the cited explanation.

**Acceptance**
- [ ] Backtest table committed: MASE per metric and model; shipped models beat seasonal naive.
- [ ] 80% intervals cover 70–90% of backtest actuals.
- [ ] Scores match a hand calculation for 5 sampled companies.
- [ ] Owner reviews 15 signal explanations: ≥ 12 cite a passage that actually explains the change.

### MVP 5 — Automatic refresh and operations
- `refresh.yml` (GitHub Actions cron) timed around the filing deadlines in §5: detect new filings, ingest idempotently (re-running never duplicates), run load checks, re-run affected forecasts and signals. A failed run opens a GitHub issue with the log.
- LQ45 rebalance handling: new snapshot, ingest new constituents, keep departed ones flagged.
- "Data as of" in every answer and on the home page.
- CI eval gate: PRs fail if golden-set metrics drop by more than 2 points.
- Langfuse dashboard: latency, refusal rate, tool errors, quota errors.
- **Stretch (D26):** `mcp_server.py` exposing `search_reports`, `get_metric`, `compare_peers`, `get_signals` over the same code, with a README section on using it from an MCP client.

**Acceptance**
- [ ] A new quarterly filing appears in answers without manual steps (demonstrated once, logged).
- [ ] Re-running the refresh on unchanged data changes 0 rows.
- [ ] The eval gate blocks a deliberately broken PR (demonstrated once).

## 11. CLI

```
python run.py fetch --kind annual|quarterly [--tickers ...]   # polite download + manifest
python run.py ingest --kind annual|quarterly                   # parse, OCR, chunk, crops / facts
python run.py index                                            # embed + load chunks
python run.py ask "..."                                        # one question, prints answer + citations
python run.py eval [--subset N]                                # golden set → eval/reports/
python run.py serve                                            # local API
python run.py forecast | signals                               # MVP 4
python run.py refresh                                          # MVP 5
```

Each step reads the previous step's output and fails loudly if it is missing. Every step is resumable.

## 12. Write-up (part of every MVP's done)
README sections, updated per MVP: what it does (GIF), architecture diagram, the decision log (§2) with one line of reasoning each, eval numbers with the golden-set description, known failure modes with examples, free-tier limits and what happens when they are hit, and "what I'd do with a budget" (e.g. managed Postgres, reranker API, larger models).

## 13. Definition of done
- **Core portfolio piece:** Phase 0 + MVP 1 + MVP 2 acceptance boxes ticked, public demo live, README answers *"Can I trust a number or a claim this assistant gives me, and how do you know?"* with eval numbers.
- **Extended:** MVP 3–4. **Operations:** MVP 5.

## 14. Open decisions (ask the owner; do not decide silently)

| Decision | When | Default if the owner has no preference |
|---|---|---|
| Product and repo name | Phase 0 | "Tanya Emiten" / `tanya-emiten` |
| Scripted fetch vs manual download | End of Phase 0 | Whatever §4.2 item 1 allows; manual if in doubt |
| OCR backend (hosted API vs Colab/Kaggle GPU) | End of Phase 0 | Colab GPU |
| Price source | End of Phase 0 | IDX daily summary if permitted, else none until decided |
| Mitigation if DB size exceeds 70% of the limit | Phase 0 / MVP 3 | `halfvec` embeddings |
| Who writes the golden set | MVP 1 | Owner writes; Claude drafts candidates marked as drafts |
| Judge model (D40) | End of Phase 0 | The best free model that is not the answer model |
| Model names for `small` / `answer` (D39) | End of Phase 0 | Fastest free-tier model / strongest free-tier model |
| HyDE or multi-query (D31) | MVP 1 eval | Only if vague questions show recall misses |
| Reranker | MVP 3 | Decided by the experiment |
| Redis (D12) | When latency/traffic demands | Not added |
| Advice line (D5) | Start of MVP 4 | Analysis only |
| Whether to also deploy once to a major cloud (AWS/GCP) for the CV signal, with credits | After MVP 2 | No |
