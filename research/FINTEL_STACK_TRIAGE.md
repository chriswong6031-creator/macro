# Fintel-Alternatives Data-Stack — Have / Free / Paid Triage

*Produced by a 4-agent triage workflow (codebase capability map · free-tooling deep-dive · paid-vendor cost/value → synthesis), 2026-06-21. Source: `Fintel_Alternatives_and_Institutional_Data_Stack.md`.*

## Bottom line
We already pull **~90% of Fintel's raw data free and keyless** (13F, insider Forms 3/4/5, ETF holdings, the EDGAR filing index, Finnhub recommendation trends). Every genuine gap is either a **derived-analytics quality layer** that is build-free on data we already hold, or one of **two raw gaps that are also free** (OpenFIGI CUSIP master + the post-2024 13D/G XML mandate). **No paid 13F/filing subscription is warranted.** The only defensible *future* spend is Quiver scoped strictly to Congress/lobbying — and even that is maybe-later, not now.

## Triage matrix

| Capability | Status | Where / cheapest source | Verdict |
|---|---|---|---|
| 13F holdings (raw) | Have | `edgar_13f.py:148`, `smart_money.py:323` (curated ~17 funds, 6Q) | already-done |
| Insider Forms 3/4/5 (raw) | Have | `sec_insider.py:94`,`:299` PIT panel 2006→now | already-done |
| ETF holdings (raw) | Have | `etf_holdings.py:59` (6 sponsors, daily) | already-done |
| 13D/G beneficial ownership (raw) | Have event / Free fields | `special_situations.py:43` detects form; **fields = free post-2024 XML** | build-free |
| Filing index / near-real-time | Have T+0 EOD / Free intraday | `special_situations.py:60`; getcurrent/RSS ~10min | build-free |
| Full-text filing search | Have narrow / Free general | `special_situations.py:61` `_EFTS` | build-free |
| CUSIP→ticker master | Partial (~60 seed) | **OpenFIGI** `/v3/mapping` free/keyless; `smart_money.py:119` | **build-free (top win)** |
| Analyst rating trends (raw) | Have | `finnhub_altdata.py:77` → `analyst_upgrade_cluster` | already-done |
| Consensus targets / per-analyst | Paid-only | Finnhub Premium ~$50 or Benzinga +$99 | defer (Phase 2) |
| N-PORT fund holdings | Free-gettable | EDGAR XML since 2019 (+60d lag); EdgarTools | skip-for-now |
| Conviction Score (derived) | Partial 3/5 | `smart_money.py:59`,`:213` accumulation_trend | build-free |
| Position-initiation (derived) | Have | `smart_money.py:182` diff_snapshots `action='new'` | already-done |
| Beneficial-ownership regime (derived) | Partial | `special_situations.py:46`,`:72` + needs XML fields | build-free |
| Activist-intent (13D Item 4 LLM) | Missing | reuse `research_paper`/`news_llm` + 13D accession | build-free |
| Institutional clustering (derived) | Partial | `smart_money.py:59` vip; needs manager-quality weight | build-free |
| **Manager-Quality Score (derived)** | **Missing — keystone** | 6Q snapshots + `brain/outcomes.py` Brier loop | **build-free** |
| ETF/fund flow-pressure (equities) | Partial (realized Δ) | `holdings.py:175`; weights × AUM | build-free |
| Per-insider historical accuracy | Partial | `insider_panel.parquet` 2006→now + outcomes | build-free |

## Free wins worth grabbing now (ranked)
1. **OpenFIGI CUSIP master** — highest EV, LOW effort. Today only ~60 ARK-seeded CUSIPs + fuzzy issuer-name matching resolve (`smart_money.py:119` `cusip_ticker_seed` / `resolve_tickers:137`), leaving foreign/ADR/renamed 13F lines unresolved and **hidden**. Free/keyless 250 IDs/min. Wire `collectors/openfigi.py` → committed parquet cusip→ticker cache feeding `cusip_map` into `resolve_tickers()`.
2. **Structured 13D/G XML fields** — since 2024-12-18 Schedule 13D/13G are mandatory machine-readable XML. `special_situations.py:43` detects the event but opens nothing. Parse reporting-person, % of class, sole/shared voting+dispositive → real 5%-crossing / 13G→13D regime, keyed by issuer CIK. MED effort.
3. **EdgarTools as parser-only** — adopt for the *new* 13D/G + N-PORT XML; do NOT rip out working `edgar_13f.py`/`sec_insider.py`. Route through our `edgar.py` identity/pacing. MIT, commit-safe.
4. **General EFTS full-text search tool** — expose `search_filing_text(query,form,date)` over existing `_EFTS`. Confirms sec-api.io SKIP. LOW.
5. **Idle Polygon endpoints (13F/Form4/short)** — leave idle. They resell the same EDGAR/FINRA we ingest; switching adds lock-in + breaks the raw-accession audit trail for zero new signal. Keep the key for GEX only.

## Paid vendors — buy or skip
- **sec-api.io** — SKIP (convenience reseller of free EDGAR/FINRA; internal use needs $199–239 Business tier).
- **FMP Ultimate ($149/mo)** — SKIP (only unique = ETF/fund-holdings + normalized targets; Finnhub Premium + free SEC covers it; ToS bars customer-facing display).
- **Quiver Trader ($75/mo)** — MAYBE-LATER, scoped **only** to Congress/lobbying (everything else duplicates free EDGAR); pull Congress free from House/Senate e-filing first.
- **WhaleWisdom ($90–150/qtr)** — SKIP for automation (tiers throttle API to 50–200 filers, no live feed); at most one $90 quarter as a manual cross-check.
- **Intrinio ($150–1,600+/mo)** — SKIP (licensing/redistribution play; revisit only if the dashboard goes customer-facing).

## Where the real edge is
Both docs **and** the JPM/SBSW case study point the same way: the edge is **not** owning the same public filings Fintel resells — it's the derived analytics on data we already pull.
- **Manager-Quality Score (keystone)** — replay filing-date-aligned forward returns of each curated fund's new/add/trim/exit (6Q snapshots in `data/smart_money/<slug>/` + `brain/outcomes.py` Brier loop) so a high-quality filer's add outweighs a mediocre one's. WhaleWisdom's paid manager-performance analog, built free.
- **Custodian / passive-vs-active aggregation guard** — the JPM/SBSW lesson: naive 13F/13G aggregation double-counts custodians/index holders, inflating "smart-money" conviction. Our curated active-fund universe excludes these *by construction*; the guard matters precisely if we widen past it.
- **Institutional clustering, quality-weighted** — `smart_money.py:59` counts holders this cycle but doesn't flag "N *high-quality* managers initiated the SAME name"; falls out free once Manager-Quality exists.

## Recommended next moves (ranked, free-first)
1. **OpenFIGI collector + cache** → unhide the full 13F info-table (LOW; unblocks every downstream smart-money metric).
2. **Manager-Quality Score** off 6Q snapshots + outcomes loop — keystone that converts smart-money *context* into *edge*.
3. **Structured 13D/G XML parse** → beneficial-ownership regime (5%-crossings, 13G→13D) pairing with special-sits desk (MED).
4. **13D Item 4 activist-intent LLM** — reuse Brain/`research_paper` on the 13D accession.
5. **Per-insider historical accuracy** off `insider_panel.parquet` + outcomes loop.
6. **Phase 2 (analyst accuracy)** — generalize EFTS search now (free); defer Finnhub-Premium/Benzinga for consensus targets + per-analyst until specced. N-PORT flow-pressure last (heaviest lift, +60d lag).

> Cross-cutting prerequisite (from the case-study review): **fix the quarter-end look-ahead** — persist `filing_date` → `available_on`, use it as the scoring as-of, guard-test that no scoring path reads `period_end`/`ReportPeriod`.
