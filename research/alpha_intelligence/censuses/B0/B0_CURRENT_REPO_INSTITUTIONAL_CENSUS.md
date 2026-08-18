# B0 — Current-repository institutional census

**Lane:** GROK-B0 (Institutional Research & Capital Allocation Intelligence)
**Date:** 2026-08-18
**Reconciliation pin:** `origin/main` @ `3d12412e561e` (docs(agentos) #5904)
**Authority of this document:** NONE. Research census only. No production scoring, no Prophet change, no new store.
**Parent snapshot:** PASS-0 PR #5910 (`research/alpha_intelligence/MASTERMIND_ALPHA_INTELLIGENCE_EXPANSION_PASS0_2026-08-18.md`) — dated, not a registry. Canonical ownership stays in `config/mastermind_programs.yml`, sibling WS records, and `research/DO_NOT_REBUILD.md`.

Claim tags used below: **CODE VERIFIED** · **PRODUCTION VERIFIED** · **PRIMARY SOURCE VERIFIED** · **INFERRED** · **UNKNOWN**.

---

## 0. One-sentence finding

The repository already owns a **four-tier 13F architecture**, a **curated ~51-CIK smart-money desk**, a **daily ETF/ARK holdings + flow-normalization plane**, and a **context-only company institutional sidecar**. What B is missing is not another 13F collector: it is a **manager-complex ontology**, **intent reconstruction that uses true fund shares-outstanding rather than a same-book proxy**, a **behavior casebook**, and **rights-safe perishable capture of sponsor-current-only holdings / borrow / estimate snapshots**.

---

## 1. Capability table

| Capability | Owner (as coded) | Path / contract | History depth | PIT quality | Live cadence | Corrections | Entity resolution | Open collision |
|---|---|---|---|---|---|---|---|---|
| Universal 13F evidence + census | `engine/institutional_census/` + `config/institutional_13f.yml` | schemas `institutional_13f.config/v1`, `catalog/v1`, `census_public/v1`, `research_bench/v1`; contracts under `contracts/institutional_13f_*.json`; builders `scripts/build_institutional_13f_census.py`, `run_institutional_13f_rolling.py` | SEC bulk zips advertised **2013-Q2 → 2026-Q2** on sec.gov (PRIMARY SOURCE VERIFIED this session); rolling atom + daily/full indexes for current quarter (CODE VERIFIED) | Accession-keyed immutable receipts; clocks `report_period`, `accepted_at`, `first_seen_at`; amendment lineage dedup inside one source family (CODE VERIFIED `aggregate.py`) | Hourly atom 12–20Z weekdays + 06:17Z master-index backstop + Sunday full-index repair (CODE VERIFIED `.github/workflows/smart-money-13f-census.yml`) | 13F-HR/A ingested; 13F-NT is **not** a zero book (`notice_is_zero_portfolio: false`) (CODE VERIFIED) | CUSIP → ticker name-match; public summary requires ≥20% mapping coverage; research bench ≥80% (CODE VERIFIED config) | Adopt, do not rebuild. Cadence recently re-cut (#5850). **Do not route around FF-1P2 STOP #5898.** |
| Curated smart-money desk | `config.yml::smart_money` + `collectors/edgar_13f.py` + `engine/smart_money.py` + `scripts/build_smart_money.py` | 51 CIKs (50 active + Scion `status: closed`); `history_quarters: 12`, `backfill_quarters: 13` | Per-fund last 12–13 quarter-end originals under `data/smart_money/<slug>/<period_end>.parquet` (CODE VERIFIED collector contract; **PRODUCTION VERIFIED of live parquet contents: not done this session — sparse worktree omits `data/`**) | Originals immutable once written; amendments isolated under `amendments/` so they cannot leak into `glob("*.parquet")` scoring paths (CODE VERIFIED); `acceptance_available_date()` is the tradeable clock | Filing-season fast path 6×/US business day (`smart-money-filings.yml` cron `17 13-23/2`); also `build_smart_money` on earlyclose + nightly | Amendments retained separately; value-unit change 2022-12-31 handled at read (CODE VERIFIED) | Curated CIK roster gated by `scripts/verify_13f_ciks.py`; share-class collapse via `config/share_class_equiv.yml` (INFERRED from masterplan + config comments; collapse file not re-read this session) | **Do not expand this roster to the long tail.** Four-tier split is already decided (`research/SMART_MONEY_AUTONOMOUS_13F_SYSTEM_2026-08-08.md`). |
| Company institutional context sidecar | `engine/company_institutional_context/` | `company_institutional_context.v1`, `AUTHORITY = "context_only"` | Tied to curated desk snapshots, not the universal census (CODE VERIFIED contracts.py) | Coverage + missing-manager counts travel with every observation; unfiled ≠ zero (CODE VERIFIED) | Nightly / render consumer of desk snapshots (INFERRED from builder name `scripts/build_company_institutional_context.py`) | Warnings: `current_snapshots_missing`, `comparison_snapshots_missing`, `resolution_partial` | Manager slug + style + grade from smart_money config | None that would justify a second per-ticker 13F projection. |
| ARK daily holdings | `collectors/holdings.py` + `config.yml::holdings.watchlist` | ARKK + ARKW official CSVs on `assets.ark-funds.com` | Forward daily snapshots under `data/holdings/<TICKER>/<YYYY-MM-DD>.parquet`. Historical depth = days the collector actually ran (UNKNOWN without `data/`) | Snapshot as-of from file; flow-normalized diffs via `active_changes_dir` | Nightly collect (CODE VERIFIED `scripts/collect.py` pattern; exact daily.yml line not re-opened) | No amendment concept; a later same-day file overwrites only if bytes differ (etf collector has stale-skip; ARK path similar INFERRED) | Ticker as published by ARK | Rights: ARK site ToS not fully retrieved this session (Cloudflare). See source registry. |
| Broad ETF holdings | `collectors/etf_holdings.py` + `config.yml::etf_holdings` | ~106 configured funds across 14 sponsors (CODE VERIFIED sponsor keys in config.yml; count from `research/ETF_DATA_SOURCES.md` 2026-08-12: 106 + ARKK/ARKW) | Dated backfill: Global X to ~2026-04-09, Roundhill to 2024, Amplify ~10.5 months (CODE VERIFIED recon doc). SSGA / Invesco / VanEck / First Trust / Sprott = **current-only, forward capture only** | `as_of` column + filename; non-equity lines dropped at write; unchanged upstream skips rewrite | Nightly collect; `scripts/backfill_etf.py` for dated sponsors | Sponsor restatements not modeled (UNKNOWN) | Ticker/name as published; CUSIP used for Invesco idType | iShares/Schwab blocked (consent wall). Vanguard unsupported. |
| ETF flow / intent proxy | `collectors/holdings.active_changes_dir` + `engine/holdings_signals.py` + `engine/etf_flows.py` | Lawful approximation already shipped: `expected = Q_{t-1} * SO_proxy`; two SO proxies exist (sum-of-common-shares; median continuing-name ratio) | Window 5d (ARK) / 40d (sector/thematic) | No look-ahead prices required for share-based path; price-residual path on sector-SPDR is a **different** construction | Computed at build from stored snapshots | Split/re-denomination guards exist (`flow_split_*`) | Same ticker identity as holdings snapshots | Do not invent a third SO proxy until the two existing ones are scored as sensors (not as truth). |
| Ownership event wire | `engine/ownership_event_wire.py` | Concatenate 13F deltas + 13D/G + insider clusters; **no fusion** (SM2-R3) | 13F from desk; 13D/G from filings store; insiders from fresher of Quiver vs SEC bulk panel | Native axis stamp + native as-of per row; 13F uses `filing_date` not `period_end` | Nightly compute; ledgers only under `COLLECT_LANE=nightly` | Amendments appear as their own axis events if ingested | Activist vs 13G tagging lives in special-sits (CODE VERIFIED review doc); custodian deny-list recommended, implementation completeness UNKNOWN | `DNR:KILL-POSITIONING-FUSION` — wire must stay unfused. |
| Beneficial ownership / 13D-G | `collectors/beneficial_ownership.py`, `engine/beneficial_ownership.py`, `scripts/validate_activist_ownership.py` | Schedule 13D/13G context | UNKNOWN depth this session | Filing-date based (INFERRED) | UNKNOWN | 13G→13D flip is the high-value event (CODE VERIFIED review doc) | Jurisdiction must be first-class (JSE/SENS ≠ US 13G) — **called out as a prior defect** | Do not score custodian 13G as conviction (`DNR:KILL-OWNERSHIP-BREAKAWAY`). |
| Quiver alt-data (insider / congress / contracts) | `collectors/quiver.py` | Paid Trader-plan API; `data/quiver/<dataset>.parquet`; `_first_seen` PIT | Event log, keep-first | `_first_seen` is the house observation clock | Daily if key present; missing key = blocked, not hard-fail | Later vendor corrections do not overwrite first row | Vendor ticker | Rights: vendor ToS; not a primary 13F source. |
| Quiver 13F *changes* (second tape) | `collectors.quiver.Sec13FChangesAdapter` + `engine/altdata.py::inst_13f_changes` + `engine/altdata_models.py` | `data/quiver/sec13f_changes.parquet`. Channel `smart_money_13f` weight **0.85** and `13f_add` weight **0.40** in `CHANNEL_WEIGHTS`. Marquee substring list includes **Citadel and Renaissance**, which SM2-R6 excludes from the official desk | Vendor event table | Filter is on `ReportPeriod` (quarter-end), **not** `accepted_at` — the 2026-06-21 review's look-ahead is still in the function docstring (CODE VERIFIED `altdata.py:995-1020`) | Quiver live API if keyed | Vendor restatements unknown | Vendor `Fund` string match | **Do not adopt as B's 13F book.** This is the dangerous duplicate: a weighted "convergence" kernel over a vendor 13F, using the non-tradeable clock, and treating class-4 names as marquee. Whether `weighted_score` still reaches any Prophet/allocation path was not exhaustively closed this session (no hit in `us_prophet_fusion.py`; still a scored-looking substrate). |
| IBKR borrow / availability | `collectors/ibkr_borrow.py` | Keyless FTP `usa.txt`; `data/ibkr_borrow/daily/<date>.parquet` | **No backfill.** History = nights collected. | `#BOF` ET stamp on each snapshot | Wired in `scripts/collect.py` (CODE VERIFIED). Dedicated workflow: none found. **Whether nightly actually persists the daily files: PRODUCTION UNKNOWN** (data/ omitted). | N/A | IBKR SYM / ISIN / FIGI | **Highest perishable US institutional-adjacent feed already in-tree.** |
| Analyst consensus snapshot | `collectors/yf_analyst.py` | `data/analyst/targets.parquet`; yfinance `.info` current only | Vendor has no history; house series exists only if the parquet is appended (UNKNOWN — file says "there is no historical series") | `provenance_note='yfinance_info_pit_snapshot'` | Incremental `--stale-days`; not on render path | Overwrite risk if single parquet is replaced (UNKNOWN) | Yahoo ticker | Perishable if not dated. Display/context only. |
| China / HK institutional prior art | Distributed: `collectors/china_flows.py`, `china_holder_counts.py`, `china_fund_issuance.py`, `hk_southbound_holdings.py`, `tushare_moneyflow.py`, `china_block_tape.py`, LHB/margin collectors | No single US-style 13F analogue. Public-fund portfolios, top holders, southbound, Dragon Tiger named seats | Vendor/exchange dependent | Mixed; China clocks are often earlier than US 13F (INFERRED from #5822 plan, not re-verified against live CN artifacts this session) | Asia-close / CN nightly | Unlock / 减持 calendars exist (`cn_holder_sale_calendar.py`) | CN/HK identity is a different plane (`engine/stock_identity/`, theme-graph) | **PR #5822** (draft research masterplan). Reuse *patterns* (named-actor history, PIT receipts, independent families). Do **not** copy LHB/Dragon-Tiger mechanics onto US 13F. |
| Institutional sector intelligence | Program `institutional-sector-intelligence` `subprogram_of` `sector-rotation-intelligence` | `docs/MASTERMIND_SYSTEM_MAP.md` | N/A | Display / sector evidence | Existing sector engines | N/A | Sector ETF holdings (`collectors/sector_holdings.py`) | Not a manager-identity owner. |

---

## 2. Four-tier architecture already decided (do not redesign)

From `research/SMART_MONEY_AUTONOMOUS_13F_SYSTEM_2026-08-08.md` (CODE VERIFIED):

1. **Universal evidence plane** — every 13F-HR, 13F-HR/A, 13F-NT, included-manager relationship; accession-keyed immutable raw. **This is `engine/institutional_census/`.**
2. **Normalized institutional census** — parent/affiliate dedup + passive / quant / custody / strategy classes. **Partially built** (`aggregate.py` + `research_bench` excludes `passive, quant_market_maker, custody, bank, insurer, pension`). Ontology of *discretionary complexes* is the B missing delta.
3. **Research-eligible managers** — ~500–1,000 with PIT identity, history, coverage, interpretable turnover. **Screen exists, not promoted** (`research_bench.status: screened_not_promoted`, `maximum_candidates: 500`, `point_in_time_history_required_for_promotion: true`).
4. **Featured desk** — ~50–150 dossiers. **This is `config.yml::smart_money.funds` (51 slugs).** Expanding it to thousands is explicitly the wrong architecture.

Quant/MM books already excluded from consensus by standing comment: RenTech, Citadel Advisors, Millennium, Two Sigma, DE Shaw, Jane Street, SIG.

---

## 3. Authority and kill rows that bind B

| Row | Binding on B |
|---|---|
| `config/institutional_13f.yml` `classification: context_only`; `may_feed_neural_web: false`; `may_feed_prophet: false`; `may_auto_promote_featured_funds: false` | CODE VERIFIED |
| `DNR:KILL-OWNERSHIP-BREAKAWAY` | 13F/ownership is never a positive breakaway / buy signal |
| `DNR:KILL-SPONSORSHIP-SCORE` | no fused 100-point sponsorship score |
| `DNR:KILL-POSITIONING-FUSION` | no fusion of positioning keys into scores outside Prophet US conditional-fusion arena |
| `DNR:KILL-LLM-ORIGINATION` | this census's prose is not evidence |
| NEXTL-U13 / WA-R2 | 13F may never be a bullish scored signal |
| Signal Commons R3 | no composite across 13F / insider / short / options |
| FF-1P2 STOP PR #5898 + `DEC:FF-1-BROAD-SUBMISSIONS-USES-SEC-BULK-ARCHIVE` | **no B recommendation may route bulk-filings capture around the STOP** (PASS-0 §6 rider) |
| `DSC:13F-ATOM-POLL-BUDGET-IS-700-FILINGS` | settled; do not re-derive |

---

## 4. What is live vs what this session did not production-verify

**CODE VERIFIED:** collectors, engines, configs, workflows, contracts, tests named above exist on `3d12412e561e`.

**NOT PRODUCTION VERIFIED this session:**

- contents or freshness of `data/smart_money/`, `data/etf_holdings/`, `data/holdings/`, `data/institutional_13f/`, `data/ibkr_borrow/` (sparse worktree omits `data/`)
- whether the hourly 13F census is currently succeeding on `macstudio` (cadence was re-cut 2026-08-18 after starving the nightly — `research/PROPHET_OUTAGE_2026_08_17_POSTMORTEM.md`)
- whether IBKR daily files are actually accruing in git
- live site `smart_money.html` / ETF radar payload freshness

---

## 5. China prior art — reuse vs do-not-copy

Read from open draft PR #5822 (first ~120 lines; **not merged**; treat as proposal).

**Reuse (pattern, not tables):**

- independent evidence families with their own clocks
- named-actor history instead of an assumed "smart money" label
- Intelligence interestingness *then* Prophet timing (never multiply two opaque scores)
- PIT replay + coverage-atomic ordering
- ownership/alignment as one family among several, never the ranker

**Do not copy onto US B:**

- Dragon Tiger / 龙虎榜 seat mechanics
- 千股千评 cost fields
- TuShare money-flow taxonomy
- any CN board-derived score as a US 13F input (the #5822 plan itself says `china_intel_hub` raw opportunity is not a lawful Prophet input because it includes board-derived information)

**Reconcile before freezing any manager ontology** (PASS-0 collision #4).
