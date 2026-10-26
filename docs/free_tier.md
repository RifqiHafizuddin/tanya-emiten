# Free-tier limits (§4.1)

Checked 2026-10-25. Each number says where it came from. **Official** = the vendor's own page; **3rd-party** = blog or guide, not trusted until confirmed; **account** = only visible in the owner's dashboard. Rows marked ⚠ need the owner.

| Service | Limit | Value | Source |
|---|---|---|---|
| **Gemini API (free)** | Models with a free tier | `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite`, `gemini-3-flash-preview`, `gemini-2.5-pro`, `gemini-2.5-flash`, `gemini-2.5-flash-lite`, Gemma 4; embeddings `gemini-embedding-2` | Official, [pricing](https://ai.google.dev/gemini-api/docs/pricing), updated 2026-10-22 |
| | RPM / TPM / RPD per model | `gemini-3.5-flash-lite`: **15 RPM / 250K TPM / 500 RPD**<br>`gemini-3.6-flash`: **5 / 250K / 20**<br>`gemini-3.8-flash`: **5 / 250K / 20**<br>Gemma 4 31B: **30 / 16K / 14.4K**<br>The table lists only models the project has used, so the 2.5 models and 3.1 Flash-Lite are not shown | Account: AI Studio rate-limit page, project "Capstone", pasted by the owner 2026-10-25 |
| | Scope | Limits are **per project, not per key**. "Capstone" is already in use (peak 434/500 RPD on 3.5 Flash-Lite and a rate-limit error in the last 28 days) → use a **separate Google Cloud project** for Tanya Emiten | Official, [rate-limits page](https://ai.google.dev/gemini-api/docs/rate-limits) |
| | Data use | Free-tier content "used to improve our products" | Official, pricing page |
| **Groq (free)**, judge | `qwen/qwen3.8-27b` | **1,000 RPD, 8,000 TPM** (from response headers on the owner's key, 2026-10-25); 30 RPM and 200K TPD per the [docs](https://console.groq.com/docs/rate-limits) base table. Cached tokens don't count; 429 + `retry-after` when exceeded | Account headers + official docs |
| **Supabase (free)** | DB size | 500 MB per project | Official, [pricing](https://supabase.com/pricing) |
| | File storage | 1 GB | Official |
| | Egress | 5 GB + 5 GB cached egress / month | Official |
| | Max upload | 50 MB per file | Official |
| | Projects | 2 active | Official |
| | Pausing | After 7 days of inactivity → weekly keep-alive Action | Official |
| | pgvector | Available as the `vector` extension on all plans (not on the pricing page; standard Supabase extension) | Supabase docs; confirm when the owner enables it |
| **Neon (free)**, Postgres since D54 | DB size | **1 GB per project** (raised from 0.5 GB on 2026-10-02; older docs pages still say 0.5 GB) | Official, [changelog 2026-10-02](https://neon.com/docs/changelog/2026-10-02) |
| | Projects | Up to 100, each with its own compute, storage and egress | Official, same changelog |
| | Compute | Scales to zero after 5 min idle (first query after that is slower); 100 CU-hours per project / month per the FAQ | Official, [FAQ](https://neon.com/faqs/free-plan-limits-and-quotas) |
| **Hugging Face Space** | CPU Basic hardware | 2 vCPU, 16 GB RAM, 50 GB disk (not persistent) | Official, [Spaces overview](https://huggingface.co/docs/hub/spaces-overview) |
| | ⚠ Creating Docker Spaces | **"Gradio and Docker Spaces run on compute and require a paid plan to create: PRO for personal accounts"** (PRO = $9/month). Free accounts can host Static Spaces and up to 2 Gradio Spaces on ZeroGPU | Official, Spaces overview + [pricing](https://huggingface.co/pricing) |
| | Sleep timeout | Sleeps "after a period of time if unused". No number on the current page (it was 48 h historically) | Official (no number) |
| **Vercel Hobby** | Fast Data Transfer | 100 GB / month | Official, [fair use](https://vercel.com/docs/limits/fair-use-guidelines), updated 2026-09-14 |
| | Fast Origin Transfer | 10 GB / month | Official |
| | Function invocations | 1,000,000 / month | Official |
| | Active CPU / memory | 4 h / month; 360 GB-hrs provisioned memory | Official |
| | Function max duration / size | 300 s; 2 GB / 1 vCPU | Official, [limits](https://vercel.com/docs/limits), updated 2026-09-16 |
| | Deployments | 100 / day, 100 builds / hour, 1 concurrent build, 45 min build | Official |
| | Image optimisation | 5K transformations, 300K cache reads, 100K cache writes / month | Official |
| | Use restriction | Non-commercial personal use only (asking for donations is allowed) | Official |
| | Git | Hobby can't connect to repos owned by a GitHub *organization*; the repo must be on a personal account | Official |
| **Langfuse Cloud (Hobby)** | Units | 50k / month (traces + observations + scores all count) | Official, [pricing](https://langfuse.com/pricing) |
| | Retention | 30 days of data access | Official |
| | Users | 2 | Official |
| | API | Ingestion 1,000 req/min; general API 30 req/min; Metrics API 100 req/day | Official |
| | Over limit | No overage on Hobby; enforcement not described → sample traces near the cap | Official (behaviour unstated) |
| **GitHub Actions** | Public repo | Standard runners free (no cap stated) | Official, [billing docs](https://docs.github.com/en/billing/concepts/product-billing/github-actions) |
| | Private repo (Free) | 2,000 min / month, 500 MB artifacts, 10 GB cache per repo | Official |
| **PaddleOCR hosted API** | Free quota | **20,000 pages / day** | Account, confirmed by the owner 2026-10-25 |
| | Per job | No file-size limit; **keep ≤ 100 pages per job** to avoid timeouts; pages beyond that are ignored | Account, confirmed by the owner 2026-10-25 |
| | Access / terms | Needs an AI Studio access token (`PADDLEOCR_ACCESS_TOKEN`); account and data-use terms not readable without signing in ⚠ | [paddleocr.ai docs](https://www.paddleocr.ai/latest/version3.x/inference_deployment/serving/paddleocr_official_api/cli.html) |
| **Kaggle** | GPU | ≈ 30 h / week (floats, resets Saturday 00:00 UTC); 12 h per session | 3rd-party; owner confirms in Kaggle settings ⚠ |
| **Colab (free)** | GPU | No published quota; availability "varies over time"; ≈ 12 h max session | Official FAQ wording + 3rd-party |
| **Render (free)**, only if D9 changes | Web service | 750 instance-h / month per workspace, spins down after 15 min idle (~1 min cold start); 512 MB RAM / 0.1 CPU per Render's pricing page (not on the docs page, verify) | Official, [render.com/docs/free](https://render.com/docs/free) |

## Implications for config

- `limits.global_questions_per_day`: the 3.8/3.6 Flash models allow 20 RPD, so they can't serve public answers. If `answer` = `gemini-3.5-flash-lite` (500 RPD), budget ~1.5 answer calls per question (repairs, schema retries) and leave headroom → **250**. See `phase0_findings.md` §5.
- Langfuse: at ~5–10 observations per answer, 50k units/month ≈ 5–10k answers/month. Fine for a demo.
- Supabase 500 MB was the binding limit (`phase0_findings.md` §7). Measured at MVP 1: ≈ 4.4 KB per chunk after rebuilding the FTS index, 45 reports ≈ 93k chunks ≈ 410 MB → Postgres moved to Neon's 1 GB (D54). Supabase keeps Storage; its keep-alive still matters.
- PaddleOCR: keep each job ≤ 3 MB as well as ≤ 100 pages (larger uploads time out; seen on AMMN), D55.
