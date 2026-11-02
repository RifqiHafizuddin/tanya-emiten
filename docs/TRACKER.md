# Work tracker

Shared status board for the owner and the assistant. The assistant updates it as work moves; the owner can edit any
row. Status: ⬜ to do · 🟡 in progress · ✅ done · ⛔ blocked (see notes).

**Phase:** MVP 1 (§10) — 1a ingestion + 1b golden set and retrieval, demo live.
**Live:** UI https://tanya-emiten.vercel.app · API https://rifqih-tanya-emiten-api.hf.space
**Last updated:** 2026-11-02

## Active work

| ID | Task | Who | Status | Updated | Notes |
|---|---|---|---|---|---|
| A1 | Ingest the remaining reports (OCR + assembly) | Assistant | ✅ | 10-27 01:10 | All 29 ingested, none failed. |
| A2 | Index finished reports on Neon | Assistant | ✅ | 10-27 01:10 | All 29 searchable. Neon 266 MB of 1 GB. |
| A3 | Draft golden questions for the 11 uncovered companies | Assistant | ✅ | 10-26 17:05 | 27 drafts approved and merged into `eval/golden.jsonl`. UNTR's 3 withdrawn (wrong-year PDF). |
| A4 | Langfuse tracing: one trace per answer, feedback as a score | Assistant | ✅ | 10-26 19:10 | Live: a question on the Space produced a full trace (ask → steps → generations). |
| A5 | Full eval on all 121 golden questions | Assistant | ✅ | 11-02 | `eval/reports/eval_20261102.md`: hybrid recall@6 **0.862** (Bahasa 0.787), refusals 100% unanswerable / 100% advice, answered 78%, cited expected page 63%, repairs 17%, local latency p50 3.0 s. README updated. |
| A6 | Retrieval improvements from the eval numbers | Assistant | ⬜ | | Targets already met. 15 misses at 6; most expect a front highlights page ranked 7th–12th (recall@12 0.936). Optional: boost summary sections. |
| A7 | Answer conflicting figures (e.g. BBCA NPL 1.7% vs 0.96%) by naming scope or both values | Assistant | 🟡 | 10-26 19:50 | `prompts/system.v3.md`: rule 8 (give each value with its scope) + rule 3 (copy numbers as the quote writes them). v3 beats v2 (answered 0.654 vs 0.596, cited expected page 0.538 vs 0.442, refusals unchanged at 100%); deployed to the Space. Of 18 wrong refusals: 12 retrieval (A6), 5 number check (4 = a year missing from the quote, see O6), 2 table quotes. |
| A8 | Security review: repo, git history, Space, Vercel bundle, API, Storage, dependencies, CI | Subagent | ✅ | 10-26 22:00 | No critical/high, no leaked secrets, 0 known dependency CVEs. 3 medium (cache poisoning, cached hits unlimited, global cap exhaustable via spoofed IP), 6 low. Fixes await owner (O7). |
| A9 | Coverage gate: questions naming only companies outside the library get a direct answer (no search, no LLM) | Assistant | ✅ | 10-26 21:45 | Owner chose A. Unknown tickers (DOID) and LQ45 reports not loaded (ASII) both handled; tests added; live on the Space (verified with the DOID question). Not covered: non-LQ45 names in words ("Delta Dunia"). |
| A10 | Prompt v4: opinion-style questions about a company's outlook are answered from the report (attributed, no own view) | Assistant | ✅ | 10-26 23:30 | Owner approved. Advice refused 16/16 (12 golden + 4 probes), unanswerable 14/14. Live on the Space. |
| A11 | Outlook vocabulary: "projection", "take", "think" don't reach GOTO's Business Outlook / Targets 2026 pages | Assistant | ✅ | 10-27 00:05 | Outlook questions add outlook/prospects/prospek/targets/guidance/proyeksi + 2026 to lexical search; opinion words dropped. Recall unchanged (hybrid@6 0.846, same misses), MRR 0.621 → 0.636. GOTO question now answered from p.57/p.47. Live. |
| A12 | Latency: connection pool + fewer DB round trips per answer | Assistant | 🟡 | 11-02 | Deployed. Neighbour fetch 1 query instead of 6 (output identical on 42 hits); cache insert joined to save_turn. Live search step (minus translate) 4.7 s → 2.4 s. End-to-end not measurable yet: Gemini 503/504 at 09:10–09:20 UTC. Re-measured 11:25 UTC (5 fresh questions, Gemini back): warm 17–21 s, one 40 s, cold 27 s. Not at target. Langfuse split (warm): translate call (small model) 1.6–7.7 s, 28.8 s once; search minus translate ~2.6 s; answer call 1–4 s; DB before first step ~1.8 s; verify + save ~2.5–3.5 s. The translate call is now the largest cost, then DB round trips to Singapore. Owner decision pending on the next fix. Found: "What was BBCA's net interest margin in 2025?" was refused (to check). |

## Owner to-do

| ID | Task | Status | Notes |
|---|---|---|---|
| O1 | Review drafted golden questions (A3) | ✅ | All 27 approved 10-26 and added. |
| O2 | Space settings: `LANGFUSE_SECRET_KEY` and `LANGFUSE_PUBLIC_KEY` as **secrets**, `LANGFUSE_HOST` as a **variable** | ✅ | Done 10-26; tracing verified live. |
| O3 | Run the next git batch push | ⬜ | Assistant writes the commands. |
| O6 | Decide how the number check treats years in claims (A7 finding) | ✅ | 10-26: B — a year in a claim must appear in the quote or the cited chunk. Implemented + test. Re-measured: answered 0.654 → 0.712, repairs 49% → 15%, refusals still 100%. Deployed. |
| O7 | Approve security fixes (A8) | ✅ | Approved 10-26; applied and deployed: exact-text cache key, no cached refusals/errors, 7-day expiry, cached hits capped at 100/visitor/day, rightmost X-Forwarded-For (measured: HF appends the client last), 16 KB body cap, 30 s per LLM call with no nested SDK retries, 90 s request cap, docs off. CORS limited in code, but HF's proxy answers CORS itself and echoes any origin. |
| O8 | Space settings: confirm only runtime secrets are set; remove `SUPABASE_ANON_KEY` (unused). Supabase: confirm `storage.objects` has no anon insert/update policies | ⬜ | From A8. |
| O9 | Decide on outlook query expansion (A11) | ✅ | Approved 10-26. |
| O10 | Review 3 redrafted UNTR golden questions (g112 chart, g113 table, g119 unanswerable) | ✅ | Approved 10-27; marked reviewed. Golden set: 121, all reviewed. |
| O11 | Decide the latency fix (connection reuse, fewer DB round trips) | ✅ | 11-02: pool (psycopg_pool) + fewer queries. |
| O4 | Label ≥ 50 answers for judge calibration (1e) | ⬜ | Later. |
| O5 | Download UNTR's FY2025 annual report to `corpus/inbox/UNTR-AR-2025.pdf`, then tell the assistant | ✅ | Registered 10-26: 524 pages, cover "Annual Report 2025". |

## Reports

29 reports registered, all ingested and indexed. "Indexed" = searchable in the live demo.

| Report | Pages | OCR + assembly | Indexed |
|---|---|---|---|
| AADI | 438 | ✅ | ✅ |
| ADRO | 472 | ✅ | ✅ |
| AKRA | 453 | ✅ | ✅ |
| AMMN | 347 | ✅ | ✅ |
| AMRT | 542 | ✅ | ✅ |
| BBCA | 605 | ✅ | ✅ |
| BBNI | 1602 | ✅ | ✅ |
| BBRI | 1407 | ✅ | ✅ |
| BBTN | 1449 | ✅ | ✅ |
| BMRI | 1467 | ✅ | ✅ |
| CPIN | 199 | ✅ | ✅ |
| CUAN | 377 | ✅ | ✅ |
| ESSA | 288 | ✅ | ✅ |
| GOTO | 497 | ✅ | ✅ |
| ICBP | 292 | ✅ | ✅ |
| INCO | 481 | ✅ | ✅ |
| INDF | 298 | ✅ | ✅ |
| INDY | 620 | ✅ | ✅ |
| ITMG | 436 | ✅ | ✅ |
| JPFA | 408 | ✅ | ✅ |
| MAPI | 245 | ✅ | ✅ |
| MBMA | 426 | ✅ | ✅ |
| MDKA | 472 | ✅ | ✅ |
| MEDC | 528 | ✅ | ✅ |
| NCKL | 416 | ✅ | ✅ |
| TLKM | 616 | ✅ | ✅ |
| UNTR | 524 | ✅ | ✅ |
| UNVR | 482 | ✅ | ✅ |
| WIFI | 414 | ✅ | ✅ |

## Done

| Date | What |
|---|---|
| 10-27 | 8 more reports indexed (27 of 29 searchable); 3 UNTR golden questions redrafted from the FY2025 report. |
| 10-26 | Security fixes from A8 live; ticker matching accepts possessives ("GOTOs", "GOTO's"). |
| 10-26 | README for GitHub: summary, answer-pipeline and ingestion flowcharts (Mermaid), early eval numbers, stack, local setup. |
| 10-26 | Number check accepts a year found in the cited chunk (O6): answered 65% → 71%, repairs 49% → 15%. |
| 10-26 | Langfuse tracing live on the Space; UNTR FY2025 report registered (corpus back to 29). |
| 10-26 | Golden set at 118 questions, all owner-reviewed: 28 companies with answerable questions, 32 table/chart, 58 in Bahasa. |
| 10-26 | 27 golden drafts for 10 uncovered companies ready for review. |
| 10-26 | Wrong-year UNTR report caught and removed; fetch check now rejects sustainability reports (UNTR's 2025 SR had slipped through). |
| 10-26 | Langfuse tracing: trace per /ask (step spans, LLM generations, tags), 👍/👎 as a score. |
| 10-26 | Live demo: HF Space API + Vercel UI, end to end with cited answers. |
| 10-26 | CI green on `eb664f5` (lint, tests, Space image build + /health smoke test). |
| 10-26 | Golden set reviewed by 3 evaluator agents; 63 of 91 items fixed (pages, references, regexes, scope). |
| 10-26 | 7 manual downloads registered (AKRA, BBNI, CPIN, GOTO, INDF, MAPI, UNVR); corpus at 29 reports. |
| 10-26 | Ingest crash on a non-ASCII OCR error fixed; OCR jobs survive a crash (pending.json). |
| 10-26 | Chart values checked against PDF text (D57); unverified values hidden. |

## Known issues

| Issue | Impact | Plan |
|---|---|---|
| Short Bahasa questions can be detected as English ("pendapat kamu soal saham BBRI?") | Answer in the wrong language | Small fix to language detection |
| Live answers take 10–17 s on the Space (LLM call now 1–2 s). Langfuse: ~5 s retrieval + ~7 s after the LLM call, mostly DB round trips Space → Neon (Singapore); ~7 new connections per answer | Fails p50 ≤ 10 s on a warm Space | O11: connection reuse + fewer queries |
| Reports state different figures for the same metric (BBCA NPL, ESSA headcount, BTN profit growth) | Answers may cite one figure only | A7 |
