# OTA W0.2 — Intraday-True Pass — Build Spec (pre-registered)

**Program:** Oracle Turn Asymmetry ([masterplan](../ORACLE_TURN_ASYMMETRY_MASTERPLAN_BY_FABLE.md) §W0.2). Authored by Fable 2026-07-05. Committed before the harness runs; choices frozen (amendments logged here with adjudicator countersign).
**Purpose:** measure what W0.1's close-only approximation cannot — true intraday stop-touch and excursion — and CALIBRATE W0.1 (the concordance delta is the headline deliverable, not a new event study). DESCRIPTIVE only; "validated" banned; no trial-ledger/nightly/site writes.

## 1. Population law (no re-enumeration)
W0.2 regrades **exactly the event rows committed in `research/oracle_asymmetry/W0_1_events_graded.csv`** (same families, same trigger dates, same dedup variants, same σ20 values). No event enumeration code runs. Rows whose node lacks OHLC coverage at trigger (XLC < 2018-09-19; XLRE < 2015-10-07; anything < store start) are marked `ohlc_coverage=false` and excluded from intraday tables (counted, never silently dropped).

## 2. Data
- **New one-shot collector** `scripts/collect_sector_etf_ohlc.py`: yfinance `auto_adjust=False`, period=max, for XLK XLV XLF XLY XLC XLI XLP XLE XLU XLRE XLB SPY → `data/yahoo_ohlc/{T}.parquet` (columns open/high/low/close/adj_close/volume; gitignored heavy store, committed manifest JSON with row counts + date ranges + pull timestamp under `research/oracle_asymmetry/W0_2_ohlc_manifest.json`). Loud-error; no scheduling (one-shot research pull; freshness is irrelevant to a historical re-grade).
- **Same-basis law:** ALL W0.2 math (entry fill, barriers, MFE/MAE) uses the UNADJUSTED series from this store — entry price = unadjusted close, stop/target touches = unadjusted low/high. Never mix with data/yahoo div-adjusted closes. Dividend drag over 21–63d (~0.2–0.5%) is second-order vs σ21 (5–12%) — stated in the atlas honesty header, not corrected.
- **Vendor cross-check:** for the 2021-07-06+ overlap, compare yahoo-pulled H/L vs `data/massive_stock_day/{T}.parquet` H/L (MAIN data dir, read-only): report % of bars with |Δ|>0.2% per ticker. Divergence >2% of bars on any ticker = STOP and report (do not proceed silently).

## 3. Grader
New function **in the W0.2 module only** (do NOT modify `engine/grading.py`): `terminal_state_hl(ohlc, signal_date, *, stop_mult, cushion_mult, liftoff_mult, liftoff_horizon, dead_band, dead_cap)` — barrier race where stop-touch = daily **low** ≤ entry×stop_mult (for longs), target-touch = daily **high** ≥ entry×liftoff_mult; same-bar straddle → stop wins (house tie law); dead-money logic on closes as in W0.1. Short-side (ep_onset_out): touches mirrored (high for stop, low for target) on the raw series — no series inversion for H/L (inversion distorts high/low semantics); implement direction explicitly and unit-test both sides. σ and barriers: reuse the ROW's σ20 from the CSV (frozen — do not recompute), applied to the unadjusted entry price. MFE/MAE from H/L extremes in R units.

## 4. Outputs
1. `research/oracle_asymmetry/W0_2_events_graded.csv` — same key columns as W0.1 + `ohlc_coverage`, intraday state/R/MFE/MAE columns.
2. `research/ORACLE_ASYMMETRY_ATLAS_W02.md` — (a) intraday-true versions of the W0.1 headline tables (families × rot21/pos63, first21 variants); (b) **the CONCORDANCE section (headline)**: per family — % of events whose terminal state CHANGED close→intraday (esp. DEAD/CLEAN→STOPPED), Δ stop-touch rate, Δ win rate, Δ median policy R, MAE understatement distribution (mae_R_intraday − mae_R_close); (c) coverage table (rows excluded per node); (d) vendor cross-check results. Every table: honesty header ("unadjusted OHLC; dividend drag unmodeled"), n + excluded count.
3. Tests (synthetic OHLC fixtures): long stop-touch via low with close above stop (the case close-only misses); short-side mirrored touches; straddle→stop; coverage exclusion; frozen-σ reuse.

## 5. Fidelity gate (runs FIRST)
- Row-for-row join to W0_1_events_graded.csv must be exact (same event count per family; abort on any unmatched row).
- OHLC store sanity: each ticker's unadjusted close within 0.1% of massive close on 3 random overlap dates (splits handled by comparing returns, not levels, if a level mismatch is a clean integer ratio).

## 6. Prohibitions
No modification of any existing engine/ or scripts/ file (W0.1's regrade script included — W0.2 is a separate module `scripts/oracle_asymmetry_intraday.py` importing from it only if import-safe). No re-enumeration. No writes to MAIN data dir; the new OHLC store lands in the WORKTREE's gitignored data/yahoo_ohlc/ (script must create it locally; note: the store is reproducible from the committed collector + manifest).

## Amendment log
- **G3 method (2026-07-05):** Spec §2 says "report % of bars with |Δ|>0.2% per ticker" which implies a same-day level comparison. The implementation instead uses day-over-day H/L returns (pct_change of high vs pct_change of high) to cancel split multipliers, consistent with the spec's "clean integer ratio" clause for split handling. This is an approved implementation amendment: a within-day level ratio normalized by prior close would equally cancel splits and match the spec's |Δ| language, but the returns-of-H vs returns-of-H approach achieves the same split-cancellation goal. Because reported divergences are ≤0.2% of bars, no current data is masked. The returns-based interpretation is retained as the approved method.
- **G2 price basis (2026-07-05):** G2 now compares unadjusted OHLC close to massive_stock_day unadjusted close (both same basis), consistent with spec §5 "MASSIVE close" and spec §2 "unadjusted series." The original implementation compared against data/yahoo div-adjusted closes, producing a basis mismatch that made the gate non-aborting. Fixed: gate now aborts (sys.exit 1) on breach.
- **G1 enforcement (2026-07-05):** G1 now performs actual per-family count assertions and duplicate-key checks rather than printing a static PASS. Abort on any empty population, missing families, or duplicate primary-key rows.
- **Concordance MAE basis disclosure (2026-07-05):** Added explicit BASIS NOTE in atlas that mae_R_hl_21 (intraday leg) is unadjusted-OHLC while mae_R_21 (close leg, W0.1) is div-adjusted, so the delta over-states understatement by up to dividend drag (~0.2–0.5%).
- **Median R label (2026-07-05):** Renamed "Median policy R intraday" to "Median policy R (intraday stop-overlay)" in atlas to accurately signal that non-STOPPED rows carry close-basis R, and ΔR measures the effect of added intraday stops only.
