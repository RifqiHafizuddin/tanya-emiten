# Annual reports that need a manual download (FY2025)

22 of 45 FY2025 reports were fetched automatically from company IR sites (2026-10-26). The rest are listed below.
Guardrail 1 applies: where a site's robots.txt forbids crawling or bot protection blocks us, we never work around it.

**How:** download the full FY2025 annual report (not the sustainability report or financial statements). Save it as
`corpus/inbox/<TICKER>-AR-2025.pdf`, e.g. `corpus/inbox/BBNI-AR-2025.pdf`, then run `python run.py fetch`. The
fetcher checks each file (80+ pages, "Annual Report 2025" / "Laporan Tahunan 2025" on the opening pages) and
registers it.

## Blocked for bots: must be manual

| Ticker | Why | Where |
|---|---|---|
| AKRA | Cloudflare challenge page | https://www.akr.co.id/annual-report |
| BBNI | robots.txt redirects in a loop (bot protection) | https://www.bni.co.id/Portals/1/BNI/Perusahaan/HubunganInvestor/Docs/BNI-AR2025-Indonesia.pdf |
| CPIN | robots.txt unreadable to scripts (WAF) | https://cp.co.id/wp-content/uploads/2026/04/Annual-Report-CPIN-2025.pdf |
| GOTO | robots.txt `Disallow: /` on the file host | https://www.gotocompany.com/investor-relations/en/annual-reports |
| INDF | robots.txt disallows `/uploads/` | https://www.indofood.com/investor-relation/annual-report |
| MAPI | robots.txt disallows `/wp-content` and `*.pdf` | https://www.map.co.id/investor/annual-sustainability-reports/ |
| UNVR | HTTP 403 to non-browser clients | https://www.unilever.co.id/files/annual-reports-2025.pdf |

## Not found automatically (JavaScript-only pages or unknown IR location)

Manual download is the quickest route. Alternatively, paste the IR page URL and I'll pin it in `corpus/sources.yaml`.

| Ticker | Company | Best lead |
|---|---|---|
| ADMR | Alamtri Minerals Indonesia | IR site unknown |
| ANTM | Aneka Tambang | https://www.antam.com/en/company-report/annual-report (viewer, no direct link) |
| ASII | Astra International | astra.co.id investor relations (only results releases found) |
| BRPT | Barito Pacific | IR site unknown |
| BUMI | Bumi Resources | https://www.bumiresources.com/ |
| DEWA | Darma Henwa | IR site unknown |
| EMTK | Elang Mahkota Teknologi | https://www.emtek.co.id/ |
| EXCL | XLSMART Telecom Sejahtera | IR site unknown |
| HRTA | Hartadinata Abadi | hartadinata.com is a parked domain; IR site unknown |
| INKP | Indah Kiat Pulp & Paper | IR site unknown |
| ISAT | Indosat Ooredoo Hutchison | https://ioh.co.id/en/ioh-investor#annualReport |
| KLBF | Kalbe Farma | https://www.kalbe.co.id/ (2025 report not found yet) |
| PGAS | Perusahaan Gas Negara | https://pgn.co.id/financial-information |
| PGEO | Pertamina Geothermal Energy | https://www.pge.pertamina.com/en/report/2025 (only statements listed) |
| PTBA | Bukit Asam | https://www.ptba.co.id/laporan/laporan-tahunan |
| SCMA | Surya Citra Media | https://www.scm.co.id/ |
