# China Intelligence → CN limit-alpha: data-readiness / PIT integration matrix (2026-08-14)

Status: **DESIGN INPUT, NOT AUTHORITY.** Updated 2026-08-15 with the post-P-B2
accrual-hardening wave (WS:CN-LIMIT-ALPHA, `DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE`).
The 2026-08-14 census still classifies producers; §6 records which class-C families
now accrue lawfully. This document still grants no family any scoring tier.
Rulings here bind *construction shape* (what may be stamped PIT, what must accrue
prospectively); every family still re-earns incremental value under its own
preregistration before touching anything Prophet-facing
(`research/CN_LIMIT_WASHOUT_PROGRAM_V2_2026-08-11.md` §2; DNR:KILL-CN-ADJUSTED-TAPE-
LEGAL-LIMIT reopen chain unmodified).

Compiled by the P-B2 session (WS:CN-LIMIT-ALPHA) from a full producer census with
file:line receipts; the two load-bearing store-semantics rulings (§2, §3) were
re-verified by hand in this checkout.

**Standing composite ban (re-affirmed):** China Intelligence's `opportunity_score` /
conviction composites and the intel-bus digest are display/context constructions
(`engine/china_intel_bus.py` is stamped LEAF · CONTEXT-ONLY). They are NEVER imported
into Prophet or any scoring layer. Only RAW evidence producers below are candidates,
and only through fresh preregistered studies.

---

## §1 Classification key

- **PIT class A** — append-only store with event-time + first-seen/known-at
  discipline; replayable "what was known at T" today.
- **PIT class B** — append-only per-session/per-event history WITHOUT an explicit
  known-at (collection `asof` only, or event-date-only); replayable for collected
  dates with a stated availability assumption.
- **PIT class C** — snapshot overwritten in place; NO in-store history (git
  archaeology of the committed parquet is the only recovery, unindexed and not a
  designed surface). Historical stamping FORBIDDEN; prospective first-seen accrual is
  the only lawful path to evidence tier.
- **PIT class D** — dormant capability: collector exists, correct PIT design, but not
  scheduled; history begins only when a lane arms it.
- **Carrier-independence** — YES means the producer is not a transform of daily OHLCV
  (analyst actions, flows, holdings, filings); NO means it is price-derived and can
  never be "orthogonal evidence" against the washout carrier by construction.

## §2 RULING — TuShare broker 金股 (`broker_recommend`)

`collectors/tushare_broker.py` keeps **exactly one month** of picks:
`_recent_months(3)` walks back up to 2 months, takes the FIRST month with rows,
stamps each row `month` + collection `asof`, and **overwrites** `data/tushare/
broker.parquet` wholesale. There is no per-month history file. **PIT class C.**

Binding consequences:

1. The current artifact is a *latest-month per-name tally*. It must never be
   presented, joined, or backfilled as a historical attention-acceleration tape.
2. Vendor recoverability: the endpoint is month-keyed, so past months' PICK LISTS are
   likely re-fetchable — but the *publication timing within each month* (when a
   broker's list became public) is not in this feed. A backfilled month can carry only
   a "month-labelled, known-at-UNKNOWN" stamp: usable as coarse display context,
   unusable as PIT evidence, because stamping old monthly picks at month-start would
   assert Mastermind knew them before it demonstrably did.
3. The lawful evidence path is **prospective first-seen accrual**: an append-only
   store keyed (month, ticker, broker) with the repo's existing `first_seen` /
   `fetched_at` idiom (the discipline already used by `china_holder_counts`,
   `china_reports`, `china_irm`, `china_omo` — first_seen never overwritten). Evidence
   windows begin at each row's first_seen, not at its month label.

Same law for EVERY class-C snapshot store in §4: no retroactive known-at, prospective
accrual only.

## §3 RULING — sell-side tapes (`forecast_vip` / `report_rc`)

`collectors/tushare_forecast.py` is TWO different stores in one module:

- `forecast_hist.parquet` — append-only, deduped (ticker, ann_date) keep-first, rows
  carry the vendor's announcement date. **PIT class B+** (event-dated, accrual since
  the collector's start; availability assumption = ann_date ≈ public date). The best
  existing sell-side/guidance substrate in the repo.
- `report_rc.parquet` — **FIXED on main, PR #5614** (commit `1e3b16dd2aa`,
  2026-08-14 17:29:28Z). `_accrue_rc` concatenates the existing store and
  keep-firsts on `(ticker, report_date, org_name, author_name, quarter,
  report_title)`. Re-verified 2026-08-15: `tests/test_tushare.py::test_report_rc_accrues_across_windows`
  green; do not redo. **PIT class B** from the first successful refresh after
  that merge. Rows destroyed by the pre-fix overwrite are gone; they were never
  backfilled. The in-store `asof` is the capture stamp, not a vendor publication
  time.

## §4 The matrix

Cadence "daily/asia" = the asia-close collector shard. Tier = current authority per
`engine/china_signal_lab.py` CHINA_REGISTRY (`scored`/`confirmer`/`display`/`pending`)
or the module's own stamp. "Indep" = carrier-independence per §1.

| Family | Source → store | Coverage | Cadence | History depth | PIT | Indep | Tier | Notes for convergence work |
|---|---|---|---|---|---|---|---|---|
| Price spine (research plane) | yfinance → `data/china_stocks_raw/*.parquet` | 1,847 names (~35% SH/SZ, survivor large-cap) | daily/asia | append-only, deep (2011+) | B | NO (it IS the carrier) | context_only; display for limit work | BACK-ADJUSTED (W-P0 basis note overrides the collector docstring); tolerant-detector plane only; exact plane = spine reopen chain |
| Exact legal-limit spine | TuShare `daily`×`stk_limit` → private store (`china_tushare_spine.py`) | full-A (designed) | NOT SCHEDULED | none yet | D | NO | context_only; THE reopen path | Double-gated (empty trust allowlist + `BULK_HISTORICAL_BACKFILL_READY=False`); no live canary ever; AUTHORITY DECISION pending (operator) — a gate failure is never permission to edit the gate |
| Realized limit pool | Eastmoney zt_pool → `data/china_zt_pool/pool.parquet` | whole market, partial vendor pool | daily/asia | append-only per session (backfillable) | B | partial (vendor's own board calc) | display | Session-calendar-anchored dates (08-08 heal); the detector recall cross-check substrate |
| Money flow (per-name + sector) | TuShare `moneyflow_dc`/`_ind_dc` → snapshot + `moneyflow_hist`/`moneyflow_sector_hist` | whole market | daily/asia | hist stores append-only | B | YES | pending (`flow`) | Ready for prospective evidence windows now; trade-date rows, availability = collection day |
| Margin (per-name) | TuShare `margin_detail` → `margin.parquet` (snapshot) + `margin_hist.parquet` (evidence) | whole market | daily/asia | snapshot + append-only hist | **A− from first live collect after 2026-08-15** | YES | display (`margin_detail`) | Hist keyed `(ticker, trade_date)` keep-first; trade_date ≠ first_seen. Snapshot consumers unchanged. See §6 |
| Chips summary (胜率/成本) | TuShare `cyq_perf` → `chips.parquet` + `chips_hist.parquet` (grid) | whole mkt snapshot; hist = china_search panel only, ~1y grid | daily/asia | partial (panel-restricted grid) | B− | partial (vendor transform of price/volume + holder turnover) | pending (`winner_rate`) | W-P0 S5b already consumes hist; depth insufficient for 2011+ studies — P-C gate |
| Chips distribution (筹码 histogram) | TuShare `cyq_chips` → `data/china_chips_distribution/` partitions | per-ticker per-call | NOT SCHEDULED | none in practice | D (design is A-grade: keep-first immutable + receipts) | partial | pending | The operator's named accumulation footprint; needs an armed accrual lane + quota budget before P-C can charter |
| Broker 金股 | TuShare `broker_recommend` → `broker.parquet` (latest-month snapshot) + `broker_hist.parquet` (evidence) | whole market | daily/asia | snapshot + append-only hist | **A− prospective / C historical (§2 + §6)** | YES | display (`broker_gold`) | Hist keyed `(month, ticker, broker)` keep-first. `known_at` only when vendor month == Asia/Shanghai collection month. Historical months = known_at UNKNOWN. See §6 |
| Guidance + surprises | TuShare `forecast_vip` → `forecast.parquet` + `forecast_hist.parquet` | whole market | daily/asia | append-only, ann_date-stamped | B+ | YES | pending (`forecast_surprise`) | Best-in-repo event-dated fundamental tape; strongest first candidate for a preregistered orthogonal family |
| Analyst reports/revisions | TuShare `report_rc` → `report_rc.parquet` | whole market, trailing 30d | daily/asia | append-only keep-first (#5614) | **B from 2026-08-14 17:29:28Z** | YES | pending (`report_revisions`) | Accrual fix shipped; pre-fix window losses are gone and were not backfilled |
| LHB (龙虎榜 inst/hot-money) | akshare Eastmoney → `data/china_lhb/detail.parquet` | whole market (board events) | daily/asia | append-only per asof (verified `_drip.append_snapshot`) | B | YES | pending (`lhb_inst`) | Institutional-seat split is the clean leg; trailing ~5d aggregation per row |
| Block trades | akshare `stock_dzjy_mrtj` → `detail.parquet` (trailing-window snapshot) + `events.parquet` (evidence) | whole market, trailing ~10d snapshot | daily/asia | snapshot + append-only events | **A− from first live collect after 2026-08-15** | YES | (special-sits only) | Events keyed `(ticker, event_date)` keep-first; event_date ≠ first_seen. Dateless raw rows are dropped, not dated. See §6 |
| Buybacks | akshare `stock_repurchase_em` → `buyback.parquet` (snapshot) + `buyback_hist.parquet` (evidence) | whole market | daily/asia | snapshot + append-only hist | **A− from first live collect after 2026-08-15** | YES | display (`buyback`) | Hist keyed `(ticker, event_date, plan_key)`. Vendor 公告日期 is `event_date`, never `known_at`. Missing/ambiguous publication → first_seen is the clock. See §6 |
| Holder counts (股东户数) | Eastmoney → `china_holder_counts/holder_counts.parquet` | whole market | daily/asia | append-only + `first_seen`/`fetched_at` | **A** | YES | pending (`holder_counts`) | The house PIT idiom exemplar — the pattern every class-C family should adopt |
| Holder sale calendar (减持) | Eastmoney → per collector | whole market | daily/asia | append-only + first_seen; NOTICE_DATE is post-sale | A− | YES | context | Explicit caveat: notice ≠ plan announcement; availability = first_seen only |
| Unlocks (解禁) | akshare → `china_unlocks/{detail,summary}.parquet` | whole market | daily/asia | event rows; append semantics unverified | B? | YES | (special-sits) | Verify append discipline before evidence use |
| Filings / inquiry letters | CNInfo → `china_filings/filings.parquet` | whole market, last-7d/run | daily/asia | append-only keep-first on announcementId, forward-only | A− | YES | (special-sits) | No deep backfill; evidence windows start at collection start |
| Preannounce / pledge / goodwill / ST board | akshare/Eastmoney → various | whole market | daily(/quarterly) | snapshots; ST history append-only from 2026-07 | C (ST: B from 07/2026) | YES | display/context | ST history young; `st_flags_current_only` caveat stamped in microstructure |
| Stock Connect (aggregate) | Eastmoney → `china_connect` | market level | daily/asia | deep (2014-11+), per-column contracts | B | YES | display (`southbound`) | Northbound flows RETIRED post-2024-08-16 (regulatory, permanent); hold_mktcap quarter-end only since 2024-09; no per-name northbound holdings exist anywhere |
| Southbound per-name holdings | → `hk_southbound/holdings.parquet` | HK-listed names only | daily/asia | accruing | B | YES | pending (`southbound_name`) | HK-side instrument — NOT A-share evidence; excluded from this program's families |
| A-H premium | akshare → `hk_ah_official` | ~190 pairs | daily/asia | accrued forward; index reconstructed | B− | NO (price ratio) | display (`ah_premium`) | Cross-market price construct; context only |
| Auction / 集合竞价 / minutes | TuShare addons + minutes plane | single-ticker pilots | NOT SCHEDULED | none | D | partial | pending | P-C's named gate; spine `not_tested` for auction/seal-time; nothing exists to study today |
| Policy / news / narrative | intel-bus facet producers (policy, chinanews, GDELT tone, communique diff) | market/thematic | daily/asia | mixed (tone parquet has history; latest.json snapshots) | B/C mixed | YES | LEAF context-only | Raw facets reusable per-producer AFTER per-store PIT verification; the bus composite itself never |
| Theme/sector cycle state | `china_sector_cycles` forward log + narrative tags | 31 SW sectors + baskets | daily/asia | forward log accrues | B | NO (price-derived cycle kernel + rel-strength/breadth) | scored input to Prophet `theme_timing` | Already inside Prophet — it is the incumbent to beat, not new evidence |
| China Prophet v3 components | `engine/china_board_rank.py` (pure function; inputs assembled in build_china_library) | pick universe | daily/asia | n/a | n/a | NO — all six score channels are price/technical-derived (incl. theme_timing's inputs) | scored (production) | Confirms the program premise: NO carrier-independent evidence currently carries score authority; P-B2 boundary — untouched |

## §5 What this means for the convergence run order (design, not commitments)

1. **Prospective/PIT accrual hardening for the named class-C families is DONE
   (2026-08-15)** — see §6. `report_rc` was already fixed by #5614. Broker / per-name
   margin / block trades / buybacks now write separate keep-first hist stores.
   Display snapshots are unchanged. No authority is implied by accrual
   (display-tier accrual ships freely under house epistemics). Do not score these
   families; do not roll into P-C/P-D from this wave.
2. **Already-usable event-dated tapes** for future preregistered families:
   `forecast_hist` (B+), LHB (B), holder counts (A), filings (A−), moneyflow hist
   (B), zt_pool (B). These can support studies whose windows start at each store's
   accrual start — honestly short for some, and the study floors must say so.
3. **P-C stays gated**: chips-distribution and auction/minutes are dormant
   capabilities (class D) — P-C cannot charter until an accrual lane for 筹码 depth
   and/or the minute plane actually runs, which is a quota/authority decision, not a
   research decision.
4. **The full-A exact plane stays an operator decision**: the spine's double gate is
   working as designed; nothing here touches it.
5. **Nothing in this matrix is a promotion**: any family that later shows raw
   association must still demonstrate INCREMENTAL information over Prophet AND over
   the structural washout carrier in the P-D ablation arena before any scoring role.

*Verified-by-hand in this checkout (2026-08-15): report_rc keep-first accrual
(collectors/tushare_forecast.py `_accrue_rc`, PR #5614); broker/margin/block/buyback
hist writers + `tests/test_cn_intel_pit_accrual.py`. LHB append discipline
(collectors/china_lhb.py) unchanged from the 2026-08-14 census. All other rows
carry census receipts; re-verify store-level claims before building on any single
row.*

---

## §6 Accrual hardening (2026-08-15) — what is now lawful

Dialect (`DEC:CN-INTEL-PIT-HIST-KEEP-FIRST-SEPARATE`): separate hist file; keep-FIRST
on identity (china_trade_detail, not `_drip` keep-last); `first_seen` immutable;
atomic tmp+replace; abort if the existing store is unreadable. Shared helper:
`collectors/_first_seen_store.py`. Evidence studies read the hist file, never
reconstruct history from the current snapshot.

| Family | Evidence store | Identity key | Evidence-start | Still non-PIT |
|---|---|---|---|---|
| report_rc | `data/tushare/report_rc.parquet` (in-place; no snapshot/hist split) | `(ticker, report_date, org_name, author_name, quarter, report_title)` keep-first | First successful refresh after **2026-08-14 17:29:28Z** (#5614). Exact row clock = that row's `asof`. | Rows overwritten before #5614 (unrecoverable). `asof` is capture stamp, not vendor publication time. |
| Broker 金股 | `data/tushare/broker_hist.parquet` | `(month, ticker, broker)` | First successful `tushare_broker.refresh` after this change is live on the asia-close lane. Floor date **2026-08-15**. Exact start = `min(first_seen)` where `pit_eligible`. Store does not exist until that run. | `broker.parquet` (latest-month display). Any hist row with `pit_eligible=False` / `known_at=""`. Vendor month ≠ Asia/Shanghai collection month. Never stamp month-start as `known_at`. |
| Per-name margin | `data/tushare/margin_hist.parquet` | `(ticker, trade_date)` | First successful `tushare_margin.refresh` after live. Floor **2026-08-15**. Exact start = `min(first_seen)`. | `margin.parquet` snapshot. `fin_pctile` (cross-section of that day) is snapshot-only. Pre-PR trade dates were not seeded. The free `china_margin_detail` drip is a different source and was not restated. |
| Block trades | `data/china_block_trades/events.parquet` | `(ticker, event_date)` | First successful `china_block_trades.refresh` after live. Floor **2026-08-15**. Exact start = `min(first_seen)`. | `detail.parquet` trailing-window aggregate. Raw rows with no vendor 交易日期 are dropped (date is not fabricated). Event date ≠ known-at. |
| Buybacks | `data/china_buyback/buyback_hist.parquet` | `(ticker, event_date, plan_key)` | First successful `china_buyback.refresh` after live. Floor **2026-08-15**. Exact start = `min(first_seen)`. | `buyback.parquet` snapshot. Vendor 公告日期 is `event_date` only. `known_at` is always collection `first_seen`. Plan start/end is never the evidence clock. |

Remaining **P-C gates** (unchanged; this wave does not open them):

1. Chips-distribution (`cyq_chips`) accrual lane armed + quota budget (class D today).
2. Auction / 集合竞价 / minute-bar plane actually running (class D today).
3. Full-A exact-plane spine authority decision (double gate stays operator-owned).

Do not score these families. Do not add them to Prophet. Do not run P-B/P-D
comparisons against them. Do not backfill claimed historical PIT evidence.
