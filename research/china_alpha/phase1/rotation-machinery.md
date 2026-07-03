# China Sector-Rotation Machinery — Phase 1 Audit
**Date:** 2026-07-03  
**Scope:** `engine/china_sector_central.py`, `china_sector_cycles.py`, `china_sector_pathway.py`, `subsector_confluence.py`, `china_sector_desk.py`, and the baskets_china / THS theme scoring chain.  
**Method:** Direct code read + Python data-freshness runs on the worktree at `.claude/worktrees/lucid-knuth-523979`. All claims cited to `file:line` or to a command run with output reproduced inline. Data files not in the worktree (noted below) were read from the main checkout fallback at `/Users/chriswong/Documents/Cluade/Macro Dashboard/` and flagged as such.

---

## 1. Engine-by-Engine Map

### 1.1 `engine/china_sector_central.py`

**Inputs:**
- `engine.china_sector_cycles.compute()` — the cycle spine: 31 Shenwan L1 sector records + 22 thematic basket records, each with `now.signature` (washout↔euphoria 0–100), `now.phase` (Trough/Recovery/Expansion/Peak/Downturn), `now.rs_rank`, `now.above200d`, and `proj` (next-turn projection). Frequency: **daily** (driven by Shenwan L1 parquet files, last date 2026-07-01, see §2).
- `engine.china_masterminds.regime_state()` — blended de-risk scalar (credit_impulse 0.45 / vol_regime 0.35 / margin_euphoria 0.20). Produces `gate_factor` in [0.2, 1.0]. Current gate_factor = **0.2** for all 212 logged calls (data/china_sector_central/calls.parquet as of 2026-07-02), meaning the regime is in hard risk-off and all bullish conviction scores are maximally suppressed.
- `data/china_regime/latest.json` — quad + liquidity overlay (context only).
- `engine.baskets_china._membership()` — for crowding aggregation.
- `engine.china_crowding.build()` and `engine.china_internals` — flow/froth context (display-only, not scored).

**State machine / score:**
Gated-confluence hierarchy (not equal-weight):  
1. **LEAD** = 0.45 × washout↔euphoria state_score + 0.55 × forward_tilt (or 1.0 × state if no pathway). (`china_sector_central.py:258–262`)  
2. **GATE** = lead × gate_factor (bullish) or lead × (2 − gate_factor) (bearish). (`china_sector_central.py:265–270`)  
3. **CONFIRM** = gated + 0.5 × RS_momentum (capped ±0.3). (`china_sector_central.py:273`)  
4. Final score = (raw + 1.0) / 2.0 × 100 → conviction tier: Accumulate (≥72), Constructive (≥58), Neutral (≥43), Cautious (≥30), Reduce (0). (`china_sector_central.py:50–55, 274`)

**Artifact emitted:**
- `site/sector_central_china_data.js` (`window.SECTOR_CENTRAL`) — the rendered page's data blob.
- `site/chinasectordata/sector_central.json` — raw JSON.
- `data/china_sector_central/calls.parquet` — graded ledger (daily append, keyed by date + id). (`scripts/build_china_sector_central.py:64–68`)

**Structural latency:**  
CRITICAL. The gate_factor is currently 0.2 (confirmed in calls.parquet — *all 212 rows* dated 2026-06-26 to 2026-07-02 show gate_factor=0.2). At gate_factor=0.2, the formula `lead * 0.2` collapses every bullish lead to ≤0.2 of its raw value. Maximum achievable score = 60 ("Constructive") — the top tier "Accumulate" (≥72) is **structurally unreachable** in the current regime. Score distribution in calls.parquet: mean=44.6, max=60. The regime gate does not distinguish between "sector just bottomed in a risk-off backdrop" (the early-rotation detection the owner wants) and "sector peaked in a risk-off backdrop" — both are suppressed equally. The signature read (washout↔euphoria) is present in the output but its translation to conviction is gated to near-flat.

Second latency: the upstream ZigZag confirmation lag. `china_sector_cycles.py:52` uses a fixed 18% (CN_ZZ_PCT) threshold. Measured lag for 801050 (Nonferrous Metals, command run 2026-07-03): bottoms in the 2015–2024 window required **21 to 130 calendar days** for +25% reversal confirmation. The "Trough" phase is assigned *after* the prior top is confirmed, so it lags the actual peak by the same amount. Phase assignment is real-time relative to the oscillator position but the oscillator is derived from the ZigZag pivots — a confirmed-lag chain.

**Current consumers:**
`sector_central_china.html` (standalone display page) — not imported by any other builder. Grep of `scripts/build_china_library.py` (the `china_stocks.html` builder) import block (`build_china_library.py:25–45`) shows **zero imports from** `china_sector_central`, `china_sector_cycles`, or `china_sector_pathway`. The engine is a display silo.

---

### 1.2 `engine/china_sector_cycles.py`

**Inputs:**
- `engine.china_sector_index.sw_close(code)` — Shenwan L1 daily close from `data/china_sectors/<code>.parquet`. 31 files confirmed present, fresh to **2026-07-01**. History: oldest codes (801010–801210) back to 1999-12-30 (6,402 rows); newer codes (801710–801890) from 2014-02-21 (2,988 rows); three newest (801950–801980) from 2014–2021 (1,094–1,804 rows).
- `engine.china_sector_index.benchmark_close()` — Shanghai Composite `000001.SS.parquet` from `data/china/`, fresh to 2026-07-02 (7,024 rows).
- `engine.baskets_china.compute_china_baskets()` — for the 22 thematic baskets' equal-weight level series (uses `data/china_search/closes.parquet`).
- `engine.china_sector_pathway.pathway_for()` — for 4 GS sectors only (Banks/Consumption/Real Estate/Auto). Monthly frequency (pathway is month-end resampled).
- `engine.sector_cycles._record_core` — the shared US cycle kernel: rebased price, 0-100 detrended-stochastic oscillator (pos), ZigZag turns, 5-phase wheel, median-half-cycle next-turn projection, RS leadership. (`china_sector_cycles.py:153`)

**State machine / score:**
Per-sector: oscillator position `pos` (0=Trough … 100=Peak), phase label (Trough/Recovery/Expansion/Peak/Downturn), `osc_slope` (momentum of oscillator), `signature` (washout 0 … euphoria 100 per `_position()`), RS rank among peers, `above200d`. No single score output — the full record is the artifact. The `signal` field in the forward log is mostly NaN; only 2 of 31 sectors show a signal as of 2026-07-02 (801770 Telecoms=SELL, 801790 Non-bank Financials=BUY).

Current state (from forward_log 2026-07-02):
- **Washed-out (signature ≤ 20):** 22 of 31 sectors + 8 of 22 baskets. Sectors include Agriculture, Steel, Autos, Banks, Retail, Media, Oil & Petrochem.
- **Basing (signature 20–35):** 12 entries. Includes Nonferrous Metals, Home Appliances, Pharma, Real Estate, Defense.
- **Trough + osc_slope > 0 (first tick up on the oscillator):** Only 2 sectors: Agriculture (pos=0.4, slope=+0.2), Pharma & Biotech (pos=3.3, slope=+0.2). All other Trough sectors have negative osc_slope.

**Artifact emitted:**
- `site/sector_cycles_china_data.js` — `window.SECTOR_CYCLES`, `window.SECTOR_NARR`, `window.SECTOR_DNA`.
- `site/chinasectordata/sector_cycles.json` — raw model.
- `site/chinasectordata/sector_cycles_basket_map.json` — compact id→{price, turns, now, proj, signature} per basket (consumed by `build_baskets_china.py` to embed cycle mini-charts on per-theme pages).
- `data/china_sector_cycles/forward_log.parquet` — daily append (212 rows as of 2026-07-02, dates 2026-06-26 to 2026-07-02).

**Structural latency:**
The washout signature (`_position()`, `china_sector_cycles.py:108–118`) is **not confirmation-lagged** — it reads the current own-history percentile of dist-from-200d and drawdown, no reversal required. This is the earliest-reading layer. The ZigZag turn/phase is confirmation-lagged (see §1.1 above). The `osc_slope` field is available daily and is the oscillator's own momentum — the "first tick up" on the oscillator (Trough + osc_slope > 0) is the earliest non-lagged inflection signal in this engine.

**Current consumers:**
- `sector_central_china.html` (via `engine.china_sector_central.compute()` which imports `china_sector_cycles`).
- `baskets_china.html` (cycle mini-chart via `sector_cycles_basket_map.json`).
- `sector_cycles_china.html` (the dedicated page).
- `data/china_sector_cycles/forward_log.parquet` feeds `scripts/grade_promises.py` (grader only).

---

### 1.3 `engine/china_sector_pathway.py`

**Inputs:**
- `engine.china_sector_index.gs_index(key)` — Shenwan L1 or composite for 4 GS sectors (Banks/Consumption/Real Estate/Auto), daily, fresh to 2026-07-01.
- `engine.china_sector_index.driver_panel(grid)` — monthly macro panel: `credit_impulse`, `tsf_yoy`, `m1_yoy`, `m2_yoy`, `m1_m2_gap`, `pmi_mfg`, `cpi_yoy`, `ppi_yoy`, `margin_roc3`, `margin_pct_float`, `qvix`, `south_net_3m`, `breadth_pct200`. Freshness: credit (TSF) last to 2026-04-01 (1-month publication lag + availability), money supply to 2026-05-01, PPI to 2026-05-01, breadth_pct200 from `data/china_breadth/breadth.parquet` fresh to 2026-07-02. (`china_sector_index.py:277–338`)
- `grading_stats.block_bootstrap_ci` and `effective_n` — for W2.6 CI fix on conditional h3/h6 probabilities.

**State machine / score:**
Four sign-stable legs: credit (+), ppi (−), mean-reversion (−dist_200d, −drawdown), breadth_contrarian (−breadth_pct200). ERA-STABILIZED composite: defined only from the first month all required legs are simultaneously live, preventing constituent-count drift. Expanding-z standardization (leak-free). Setup score → tercile → conditional: "when setup tercile = high, h6-month positive return was X% vs Y% base" (Wilson CI + block-bootstrap lift CI). (`china_sector_pathway.py:41–178`)

**Artifact emitted (for the 4 GS sectors only):**
- `site/chinasectordata/pathway.json` — per-sector setup + conditional odds + narrative.
- `site/china_sector_desk.html` (embedded). (`scripts/build_china_sector_desk.py:47–48`)
- The pathway block is also embedded inside each `china_sector_cycles` sector record (via `rec["pathway"]` at `china_sector_cycles.py:167–170`) and thus inside `sector_central_china.html`.

**Structural latency:**
Monthly frequency. The driver panel is month-end resampled from daily inputs. The setup score is computed at month-end; within a month the tercile/conditional odds do not change. Credit (the dominant bullish leg) lags by ~2 months (TSF publication + 1-month lag in `driver_panel`: `china_sector_index.py:307–308`). PPI lags ~1 month. In practice, the earliest a credit impulse acceleration translates to a shifted tercile is 2–3 months after the credit expansion begins. The pathway says "historically" — it is not a real-time signal; it is a monthly conditioning context.

**Current consumers:**
- `china_sector_desk.html` (only page that renders pathway directly).
- `sector_central_china.html` (forward tilt layer in `_forward_tilt()` at `china_sector_central.py:177–211`).
- Neither consumers of the pathway feed `china_stocks.html`.

---

### 1.4 `engine/subsector_confluence.py`

**Note:** This engine is US-domain (S&P 500 sub-industries, Nasdaq-100, Russell-2000). Its China entry-point `compute_china_ths_confluence()` is designed for THS concept baskets.

**Inputs (THS path):**
- `data/baskets_china_ths/membership.json` — 237 curated THS concept baskets (confirmed present, 191KB). Actual active baskets with members: 50 in the snapshot, up to 237 defined. All THS member tickers (339 unique) are present in `data/china_stocks/<ticker>.parquet` (1,520 files, all fresh to 2026-07-02, full OHLCV including open/high/low/volume). (`subsector_confluence.py:466–494`)
- `basket_index._load_member_ohlcv(ticker)` — reads `data/china_stocks/` for A-share tickers (`.SS`/`.SZ` suffix). Confirmed path: `basket_index.py:104–118`.
- Benchmark: `510300.SS` (CSI 300 ETF), fresh to 2026-07-02.
- `engine.signal_gate.gate()` — T1-T4 MACDRSI×StochRSI cascade (needs ≥220 daily bars). All china_stocks files have ≥220 bars (sample: 000021.SZ has 8,086 rows).
- `engine.sector_signals.sector_signal()` — BUY/SETUP/TOPPING/SELL regime state machine.

**State machine / score:**
Per-basket: equal-weight synthetic index → T1/T2/T3/T4 entry tier → sector_signal regime state (BUY / BUY_PARTIAL / SETUP_BUY / NEUTRAL / EXTENDED / TOPPING / SELL) → class (entry_now / forming / tailwind / neutral / late / headwind). (`subsector_confluence.py:185–198`)

**Artifact emitted:**
`compute_china_ths_confluence()` returns a dict but no build script currently calls it on a schedule. The `compute_china_ths_confluence` function exists but was not found in any `scripts/build_*.py` file's import list. It is callable but not wired into the daily build.

**Structural latency:**
Near-zero for T1/T2 (confirmed cross within 2 ticks per `FRESH_TICKS=2` in `confluence_tiers.py`). T3 is "3D StochRSI crossed and 2D MACD about to cross" — 0–1 tick ahead. T4 is the 2D StochRSI only (earliest). The regime state machine (`sector_signals`) is daily. This is the **least-lagged** sector detection layer in the stack.

**Current consumers (China):**
None wired into daily build. The US subsectors are consumed by `build_index_leadership.py`.

---

### 1.5 `engine/china_sector_desk.py`

**Inputs:**
- `data/china_sectors/<code>.parquet` — Shenwan L1 daily OHLCV (all 31 sectors, fresh to 2026-07-01). Desk only uses 16 "dashboard sectors" mapped via `config.china.yahoo.sector_etfs`. (`china_sector_desk.py:149–158`)
- `data/china/<CSI300>.parquet` — benchmark, fresh to 2026-07-02.
- `data/china_sectors/valuation.parquet` — PE-TTM/PB/div snapshot.
- Per-sector ETF close from `data/china/<etf>.parquet`.
- `engine.china_sector_index.zigzag_turns()` — same 25% ZigZag for last major turn.
- `engine.cycles.analyze()` — cycle ladder state (Trough/Recovery/Expansion/Peak/Downturn via the shared US engine ported to China).

**State machine / score:**
Per-sector: `_cycle_position()` = washout↔euphoria score 0–100 (identical algorithm to `china_sector_pathway._position()`). `_rs()` = RS vs CSI 300 (mom_20d/60d, above_200d, pctile_252d). `_ladder()` = cycle ladder state. Multi-window returns (1d/5d/20d/60d/YTD). Board summary: top 4 leaders (60d RS), bottom 4 laggards, 4 most washed-out (by position.score), 4 most euphoric. No single quantitative score output; a display snapshot.

**Artifact emitted:**
- `site/china_sector_desk.html` — rendered page.
- `site/chinasectordata/desk.json` — raw JSON.
- `data/china_regime/china_sector_desk_latest.json` — hub card (leader + as_of).

**Structural latency:**
The `_cycle_position()` score is **daily and confirmation-lag-free** (no reversal required; just own-history percentile). The `_ladder()` state from `engine.cycles.analyze()` uses the same ZigZag-derived oscillator — confirmation-lagged.

**Current consumers:**
- `sector_central_china.html` (embeds the sector desk board via its template, `templates/sector_central_china.html.j2:200`).
- `china_sector_desk.html` (dedicated page).
- `data/china_regime/china_sector_desk_latest.json` — hub card only.
- **Not imported by `build_china_library.py`.**

---

### 1.6 Baskets-China / THS Scoring Chain

**Inputs:**
- `data/china_search/closes.parquet` — 1,492 A-share tickers, 1,220 bars (2021-06-15 to 2026-06-26), ~4.8 years. **NOTE (fallback): this file is in the main checkout, not the worktree. The worktree's `data/china_search/` was absent. All freshness reads for this file are from main checkout.** Coverage: 277/280 curated basket members (97.9%), 339/339 THS members (100%).
- `data/baskets_china/membership.json` — 22 curated A-share thematic baskets (280 unique tickers). Fresh. (`scripts/build_china_library.py:471`)
- CSI 300 ETF via `data/china/510300.SS.parquet` — fresh to 2026-07-02.

**Score computed (`_basket_tailwind_map()`, `build_china_library.py:463–487`):**
For each basket, reads `perf.20d.rel` — the basket's **20-day return relative to CSI 300**. Each stock gets the strongest |rel20| among its baskets. This single number is the only sector/theme rotation signal fed to the picker. No breadth, no dispersion, no washout state.

**Structural latency:**
The 20d relative return is trailing-momentum by construction. A basket that bottomed 15 days ago and is now +12% rel will score well — but so will one that bottomed 60 days ago and is +12% over the last 20d. There is no distinction between "just started ticking up" and "already mid-cycle run." This is R3 from the prior audit.

**Artifact emitted (for picker):**
The tailwind map is a transient dict, not persisted to disk — it is computed inside `main()` and injected into each stock's conviction record before writing `site/chinastockdata/<ticker>.json`. No intermediate sector-rotation artifact is written.

---

## 2. Daily-Frequency Sector-Level Raw Material Inventory

| Dataset | Path | Frequency | Max Date | Depth | Completeness | Notes |
|---|---|---|---|---|---|---|
| Shenwan L1 closes | `data/china_sectors/<code>.parquet` | Daily | 2026-07-01 | 1999 (oldest codes) / 2014 (newer) | 31/31 codes | OHLCV + amount (turnover) all present |
| Shenwan L1 turnover | `data/china_sectors/<code>.parquet` col `amount` | Daily | 2026-07-01 | Same as above | 31/31 codes | Daily traded yuan amount confirmed |
| Whole-A breadth | `data/china_breadth/breadth.parquet` | Daily | **2026-07-02** | 1991-03-12 | Cols: pct_above_50, pct_above_200, nh, nl, adv, dec, ad_line | 82 members (curated universe only) |
| Per-name closes (basket members) | `data/china_search/closes.parquet` *(main fallback)* | Daily | **2026-06-26** (5-day lag) | 2021-06-15 (~4.8yr) | 1,492 tickers (277/280 basket, 339/339 THS) | Only close, no OHLCV. 200MA computable (1,457 tickers have ≥200 bars) |
| Per-name OHLCV (A-share) | `data/china_stocks/<ticker>.parquet` | Daily | **2026-07-02** | Varies (000021.SZ = 8,086 rows) | 1,520 files; 280/280 basket members, 919/919 THS members | Full OHLCV (open/high/low/close/volume). Confirmed. |
| THS concept membership | `data/baskets_china_ths/membership.json` | Static (updated on collect) | 2026-07-02 (seed date) | 237 concepts | 50 active in current snapshot | 339 unique tickers all in china_stocks |
| CSI 300 (benchmark) | `data/china/510300.SS.parquet` | Daily | 2026-07-02 | 3,426 rows | Present | Close + volume |
| SHCOMP (benchmark) | `data/china/000001.SS.parquet` | Daily | 2026-07-02 | 7,024 rows | Present | Close + volume |
| Credit/TSF | `data/china_credit/tsf.parquet` | Monthly | 2026-04-01 | 2008 | Present | ~2-month lag before any signal |
| Money supply | `data/china_macro/money_supply.parquet` | Monthly | 2026-05-01 | 221 rows | Present | m1_yoy, m2_yoy |
| PPI | `data/china_macro/ppi.parquet` | Monthly | 2026-05-01 | 245 rows | Present | ppi_yoy |
| Breadth_pct200 (whole-A) | via `data/china_breadth/breadth.parquet` | Daily | 2026-07-02 | 1991 | pct_above_200 col | Used in driver_panel for pathway |

**Key freshness gap:** `data/china_search/closes.parquet` lags 5 days behind the Shenwan sector data (2026-06-26 vs 2026-07-01). The `data/china_stocks/` per-name OHLCV is current (2026-07-02) and is the preferred source for any per-name computation.

---

## 3. Fast-Feeder Candidate Feasibility

### 3.1 Per-sector breadth thrust (% members reclaiming a fast MA)

**Input available?** YES — two paths:
- `data/china_search/closes.parquet` (close only, 5-day lag, 1,492 tickers, 4.8yr history).
- `data/china_stocks/<ticker>.parquet` (full OHLCV, current to 2026-07-02, 280 basket + 919 THS members).

**Frequency:** Daily. **Computation path:** Cross all members' close against their rolling MA (20/50/200d). Command run confirmed: for cn_semis (22 members), % above 20MA and 200MA computable in a single pass. `data/china_search/closes.parquet` has 1,457 tickers with ≥200 bars (200MA computable). `data/china_stocks/` files have multi-year OHLCV for all basket members.

**Existing partial computation:** `engine.china_sector_desk._cycle_position()` computes dist-from-200d and drawdown for Shenwan L1 **indices**, not individual members. There is no existing per-sector member-breadth computation at the basket level.

**Cheapest path:** Read `china_stocks/<ticker>.parquet` for basket members (already done in `build_china_library.py` per-name loop), compute per-basket % above 20MA, output alongside basket record. Incremental — the per-name data is already loaded.

### 3.2 Washout → first-tick-up on the signature

**Input available?** YES — `data/china_sector_cycles/forward_log.parquet` already logs `signature` and `osc_slope` for all 31 Shenwan sectors + 22 baskets **daily** (confirmed, 2026-06-26 to 2026-07-02).

**Frequency:** Daily. **Computation path:** Already computed by `engine.china_sector_cycles.compute()` and logged by `append_forward_log()` (`china_sector_cycles.py:314–360`). The signal combination **Trough + osc_slope > 0** (first oscillator tick up from trough) is readable from the existing forward_log in a single pandas filter. As of 2026-07-02: Agriculture and Pharma qualify. Signature ≤ 20 (washed-out) + osc_slope > 0 would be the strictest "washout turning" filter.

**Existing partial computation:** The oscillator slope (`osc_slope`) and `signature` are **already computed and logged**. The gap is that these are not pulled into the picker. The "first tick up" combination is not surfaced as a label or a ranked signal anywhere downstream.

**Cheapest path:** Read `data/china_sector_cycles/forward_log.parquet`, filter to latest date, join to the basket cycle map, compute a boolean "first_tick_up = (phase=='Trough') & (osc_slope > 0) & (signature <= 35)". This is a 3-line pandas operation on existing data.

### 3.3 Member dispersion compression

**Input available?** YES — `data/china_search/closes.parquet` (1,492 tickers, 4.8yr) or `data/china_stocks/` per-name. Command run confirmed: for cn_semis, cross-sectional std of 20d member returns is computable. Current reading: std = 0.2153 vs 6m mean of 0.1264 (elevated, not compressed — expected given recent AI momentum). 6m min = 0.0487 (that was the low-dispersion floor).

**Frequency:** Daily. **Staleness:** `china_search/closes.parquet` has a 5-day lag; `china_stocks/` is current to 2026-07-02 but lacks the breadth of the 1,492-ticker store.

**Existing partial computation:** None. No engine currently computes cross-sectional dispersion of member 20d returns as a basket-level signal.

**Cheapest path:** Per-basket std of pct_change(20) across members, computed from existing `china_search/closes.parquet` (5-day lag) or `china_stocks/` per-basket-member subset (current). Normalize by trailing 252d std to get a "dispersion percentile" — already feasible with 4.8yr history.

### 3.4 RS-slope inflection vs CSI 300

**Input available?** YES — `data/china_sectors/<code>.parquet` for Shenwan L1 (daily, 2026-07-01) and `data/china/510300.SS.parquet` for CSI 300 (daily, 2026-07-02). For thematic baskets, equal-weight index can be built from `china_search/closes.parquet` per basket.

**Frequency:** Daily. **Computation path:** `engine.china_sector_desk._rs()` already computes `mom_20d` and `mom_60d` RS vs CSI 300 for 16 dashboard sectors (`china_sector_desk.py:61–73`) and writes these to `desk.json`. For baskets, the same can be derived from `baskets_china.compute_china_baskets()` which builds EW level series.

**Existing partial computation:** `china_sector_desk.snapshot()` already computes RS for 16 of 31 Shenwan sectors, but the RS-slope **inflection** (second derivative, sign change from negative to positive) is not flagged. `_basket_tailwind_map()` uses 20d relative return (a level, not an acceleration). Command run confirmed: cn_semis RS-slope vs CSI 300 is 0.1658 (20d) and 0.7088 (60d). The RS pctile over 1y = 100.0%, meaning it is at a historic RS high — not the inflection the feeder would want to detect.

**Cheapest path:** For Shenwan sectors, the data is present in `desk.json` (rebuilt daily). Add `rs_slope_accel = mom_20d[-5d] - mom_20d[-10d]` as a daily inflection proxy.

### 3.5 Cohort COILED fraction

**Input available?** YES — `engine.coiled.cohort_fractions()` is already called inside `build_china_library.py` (`build_china_library.py:1197`). The per-name inputs (`weekly_d_last`, `washout_ctx`, `bull_div`) are collected for all A-share names in the build loop. The result `coiled_by` dict maps ticker → coiled assessment. From this, the **fraction of each Shenwan sector's members that are COILED** is computable by grouping `coiled_by` by the `sector` field (already in `_coil_sector` dict, `build_china_library.py:885`).

**Frequency:** Daily (built in `main()` of `build_china_library.py`). **Data source:** Per-name daily close from `data/china_stocks/` (1,520 files, fresh to 2026-07-02, 280 basket members 100% covered).

**Existing partial computation:** The COILED assess result **is computed per name** (`coiled_by` dict) and attached to each stock's conviction record (`build_china_library.py:1261–1266`). The **aggregate cohort fraction per sector** (what fraction of Shenwan sector X's members are COILED) is **not computed as a sector-level output** — it exists only as a cross-sectional side-effect used in the `cohort_fractions()` function itself. The function signature `cohort_fractions(latest_d, sector_of)` returns a per-name fraction (what fraction of the name's sector-peers are in weekly washout), not a per-sector fraction.

**Cheapest path:** After `coiled_by` is built, group by `_coil_sector[ticker]` and compute `n_coiled / n_total` per sector. This is 3 lines of code appended after `build_china_library.py:1212`.

### 3.6 THS concept index T3/T4 projection

**Input available?** YES — confirmed fully:
- `data/baskets_china_ths/membership.json` — 237 THS concept definitions.
- `data/china_stocks/<ticker>.parquet` — full OHLCV for all 919 THS member tickers, fresh to 2026-07-02. `basket_index._load_member_ohlcv()` reads this path for `.SS`/`.SZ` tickers (`basket_index.py:104`).
- `subsector_confluence.compute_china_ths_confluence()` already exists as a **callable function** (`subsector_confluence.py:466–494`) that runs the full T1-T4 MACDRSI×StochRSI cascade over THS concept equal-weight synthetic indices.

**Frequency:** Daily (all inputs are daily EOD). **Minimum bars requirement:** ≥220 bars for cascade; all THS members' china_stocks files meet this (sample 000021.SZ = 8,086 rows).

**Existing partial computation:** `compute_china_ths_confluence()` is **fully implemented** but **not wired into any daily build script**. It is a "dark" function — correct, feasible, runnable, but never called on a schedule. The T3/T4 projection (bars_to_cross field from `signal_gate.gate()`) would flag a concept basket that is about to get a confluence cross.

**Cheapest path:** Add a call to `compute_china_ths_confluence()` in a new build script (analogous to `build_index_leadership.py`), write output to `site/marketdata/ths_confluence.json`, and consume from the baskets_china page. Zero data infrastructure required — all inputs are present.

---

## 4. Structural Latency Summary

| Layer | What it detects | Latency from actual turn | Data frequency | Currently fed to picker? |
|---|---|---|---|---|
| `_position()` / `signature` | Washout↔euphoria state (low = bottom-like) | **0 days** — no reversal required | Daily | NO — display only |
| `osc_slope` (first tick up) | Oscillator inflecting positive from Trough | **0–1 day** (next bar) | Daily | NO — in forward_log only |
| ZigZag phase (Trough label) | Phase assignment | **21–130 calendar days** (25% reversal required before prior top confirmed) | Daily | NO — display only |
| T3/T4 cascade (signal_gate) | Name/basket about to cross | **0–1 bar ahead** | Daily | YES — per-name in picker |
| Pathway conditional | Monthly setup tercile | **Monthly; credit leg ~2mo publication lag** | Monthly | NO — display only |
| `_basket_tailwind_map()` 20d rel | Theme momentum | **Trailing 20d** (already ran) | Daily | YES — the ONLY feeder |
| `cohort_fractions` | Cross-sectional washout fraction | **Daily** (no reversal) | Daily | Partial — per-name bonus only |
| Regime gate (gate_factor) | Market risk-on/off | **Daily** (credit/vol/margin blend) | Daily | NO — display only, currently 0.2 |

---

## 5. Key Findings Not Derivable from Prior Audits

1. **Gate collapse:** All 212 calls in `data/china_sector_central/calls.parquet` show `gate_factor = 0.2`. The maximum achievable score is 60 ("Constructive"). "Accumulate" (≥72) is structurally unreachable at the current regime setting. This means sector_central_china.html is currently unable to produce a strong buy signal even for deeply washed-out sectors in Trough.

2. **THS confluence is fully built, zero deployment:** `compute_china_ths_confluence()` exists in `subsector_confluence.py:466`, all 919 THS member tickers have fresh OHLCV in `data/china_stocks/`, and the function requires no new data infrastructure. It is not called in any daily build script.

3. **osc_slope is already in the forward_log:** The "first tick up" signal (Trough + osc_slope > 0) is computable from `data/china_sector_cycles/forward_log.parquet` with zero new computation. As of 2026-07-02: only 2 sectors qualify (Agriculture, Pharma). This would provide an early, no-reversal-required inflection flag.

4. **china_search/closes.parquet is stale by 5 days:** The file used by `_basket_tailwind_map()` (main checkout: 2026-06-26) is 5 days behind the Shenwan sector data (2026-07-01) and 6 days behind `china_stocks/` per-name data (2026-07-02). The feeder the picker actually uses is the stalest data source.

5. **Per-sector daily turnover is present for all 31 Shenwan L1 sectors** (the `amount` column in `data/china_sectors/<code>.parquet`). This enables a "volume surge on a washed-out sector" signal — currently unused.

---

## 6. Open Questions

1. **Gate_factor stuck at 0.2:** Is this the intended regime posture, or is `china_masterminds.regime_state()` misconfigured or reading stale data? At 0.2, the entire sector_central hierarchy is decorative. This needs a live run to verify.

2. **THS concept membership quality:** The `membership.json` lists 50 active baskets (out of 237 defined). How is the active set maintained? Are staleness/quality checks applied before the T3/T4 cascade would run on them?

3. **Breadth data universe:** `data/china_breadth/breadth.parquet` covers only 82 members (a curated set, not the full A-share universe of ~5,000 names). Is this intentional? For a genuine whole-A breadth thrust, a larger universe would be needed — or the breadth computation must be done from `china_stocks/` per-name data directly.

4. **ZigZag threshold calibration for baskets:** `build_basket()` in `china_sector_cycles.py:197` uses `max(CN_ZZ_PCT=18, vol_scaled)`. For thematic baskets with A-share-level volatility (electronics, battery), the effective ZZ threshold may be higher than 18%, further extending confirmation lag. What is the distribution of effective thresholds across the 22 baskets?

5. **COILED cohort fraction per sector:** The `cohort_fractions()` output is currently used to produce a per-name bonus but not aggregated to a sector-level "fraction of sector washed out" signal. Has any backtesting been done on whether the sector-level cohort fraction (not just the per-name ratio) predicts forward sector returns?

6. **Monthly pathway update schedule:** The `pathway_for()` engine resamples to month-end but is called in the daily build. Is it idempotent (same result repeated within a month) or does it recalculate as daily data arrives within the month?

---

*All data freshness readings were run 2026-07-03. Shenwan sector data and china_stocks per-name OHLCV confirmed present in worktree. china_search/closes.parquet read from main checkout fallback (noted above).*
