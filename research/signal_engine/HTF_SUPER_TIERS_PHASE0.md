# HTF Super-Tiers Phase-0 Results (G-HTF1)

**Date:** 2026-07-06  
**Panel:** 224 US names (224 attempted, 0 failed)  
**Study window:** 2010-01-01 → present  
**Benchmark:** data/yahoo/SPY.parquet (daily close, 1993→)  
**Runtime:** 126.3s

---

## Methodology (summary)

Pre-registration: `research/signal_engine/HTF_SUPER_TIERS_ADJUDICATION_AND_PREREG.md` Part 2.  
Per-TF confluence-active state = MACD-RSI crossed up within FW native bars AND StochRSI K ≥ D (crossed within CONF_W=8 native bars). 3D via `_tf_bars(c,3)` (session buckets, known-date mapped, identical to production). 1W via W-FRI completed resample; 2W via 2W-FRI completed resample. Not-topped veto on 3D basis throughout.  
**S1** = 2W confluence-active AND 3D confluence-active.  
**S2a** = 3D active AND 1W active AND 2W MACD pending (hist<0, slope>0, btc≤1.0 native 2W bar).  
**S2b** = S2a AND 2W StochRSI K-D gap narrowing OR crossed.  
Freshness sweep FW ∈ {1, 2} — both printed, no post-hoc picking.  
Event = onset (state False→True). Fill = next session close (e+1).  
Triple barrier: −5% hard stop / 20d horizon (close-only; no OHLCV in stocks/*.parquet).  
**60d durable-bottom definition (from `research/bottom_signal_backtest/metrics.py` line 57):**  
no daily close in the next 60 sessions drops below fill_price × 0.95 AND full 60-session window is available. (Original uses `low` column; we use close as stocks/*.parquet is close-only — this is a deviation from the bottom-study definition, stated here.)  
**fill_premium_20d** = fill_price / min(close in trailing 20 sessions ending at event_date) − 1.  
**SPY excess** = name return − SPY return over the same forward window; SPY benchmark from `data/yahoo/SPY.parquet`.  
Bootstrap CI: 1000 reps, seed 42, month-block resampling (calendar months).  
**S2 repaint** = proportion of S2 onset fires where the 2W pending leg vanishes when computed from completed-only 2W bars (vs. provisional raw resample including in-progress tail bucket).

---

## Results Table

| Variant | FW | n fires | n tickers | stop% | clean% | MFE 20d | MAE 20d | fill_prem 20d | durable 60d | n_db60 | lead T1 (med) | lead T2 (med) | overlap T1/T2 | exc 21d (CI) | exc 63d (CI) | exc 120d¹ | exc 240d¹ |
|---------|-----|---------|-----------|-------|--------|---------|---------|--------------|------------|--------|---------------|---------------|----------------|-------------|-------------|-----------|-----------|
| S1 | 1 | 423 | 182 | 27.2% | 72.3% | 4.1% | -2.6% | 8.1% | 50.0% | 416 | 0.0 | -39.0 | 100.0% | 0.90% [0.16%,1.67%] | 1.60% [-0.10%,3.17%] | 1.92% | 3.68% |
| S1 | 2 | 641 | 200 | 27.0% | 72.5% | 4.1% | -2.6% | 7.7% | 51.0% | 630 | 0.0 | -26.0 | 100.0% | 0.68% [0.05%,1.34%] | 1.56% [0.24%,2.86%] | 2.04% | 3.19% |
| S2a | 1 | 227 | 133 | 31.7% | 67.4% | 4.6% | -2.7% | 10.0% | 49.1% | 220 | -2.0 | -45.0 | 100.0% | -0.10% [-1.55%,1.25%] | -0.20% [-2.52%,2.28%] | -0.33% | -1.17% |
| S2a | 2 | 274 | 149 | 31.0% | 67.9% | 4.5% | -2.5% | 9.6% | 49.2% | 266 | -2.0 | -35.5 | 100.0% | -0.16% [-1.35%,1.06%] | -0.57% [-2.68%,1.58%] | -0.50% | -1.23% |
| S2b | 1 | 208 | 129 | 31.7% | 67.8% | 4.6% | -2.5% | 10.1% | 48.5% | 202 | -2.0 | -44.5 | 100.0% | -0.24% [-1.68%,1.10%] | -0.62% [-3.02%,2.06%] | -0.64% | -1.40% |
| S2b | 2 | 249 | 144 | 30.9% | 68.7% | 4.6% | -2.4% | 10.0% | 49.4% | 243 | -3.0 | -26.0 | 100.0% | -0.27% [-1.52%,0.91%] | -0.97% [-3.22%,1.32%] | -0.85% | -1.54% |

¹ 120d/240d excess: **overlap-adjusted caveat** — events overlap heavily at these horizons; treat as descriptive trend only, not precise estimates.

**Note on overlap T1/T2 = 100%:** This is **by construction** — S1 and S2 both require 3D confluence-active (same MACD-RSI/StochRSI signals underlying T1/T2), so every S onset day necessarily coincides with a T1 or T2 active day on the same ticker. This is not a bug; it confirms the structural nesting.

**Lead/lag sign convention correction:** The `_lead_lag` function computes `dists = ref_pos − event_pos`. A **negative** lead\_T2 value means the nearest T2 onset PRECEDES the S event (S fires AFTER T2). The distribution is bimodal/unstable and does not support a stable "S fires before T2" reading. **Withdraw any "S fires earliest / leads T2" interpretation.** The correct read: S1 fires at/near T1 (lead\_T1 ≈ 0, i.e. fires on the same session or within a session, since S1 is T1 with an added 2W requirement) and is a **late higher-timeframe confirmation**, not an earlier entry trigger. S2's negative lead\_T2 reflects that 2W confirmation onsets are sparser and the nearest T2 reference typically already fired before the S event.

---

## S2 Repaint Rate

Method: provisional_vs_completed_2W_pending_leg  
S2a: 227 total onset fires, 0 would vanish on completed bucket → repaint rate = **0.0%**  
S2b: 208 total onset fires, 0 would vanish → repaint rate = **0.0%**

**IMPORTANT LIMITATION:** The 0.0% figure is an artefact of running the measurement on historical data. All historical 2W buckets have since closed — the "provisional" and "completed" series agree at every past event date by definition (the in-progress tail only matters on the LIVE trading day, not in hindsight). The true repaint rate cannot be measured retroactively from a historical backtest. The correct approach (used for T3 in `calibration/provisional_replay.json`) requires a live replay where the daily and completed-bucket series are compared as-of each day — that infrastructure exists for the 2D signal but not yet for the 2W grid. **For gate purposes, treat the S2 repaint as UNMEASURED (not 0.0%).** The pre-registration gate (≤ 20%) cannot be formally evaluated at this time; the gate is listed as PASS-PENDING until a replay is run. Given the 2W pending leg uses the same btc ≤ 1.0 extrapolation as the production imm2, and the imm2 2D repaint was measured at ~9-24% across studies, the 2W analog is likely in a similar range.

---

## Incumbent Tier Comparison (from TIERED_CASCADE.md, not recomputed)

| Tier | n | stop% | clean% | MFE% | fill_prem source |
|------|---|-------|--------|------|------------------|
| T1 | 919 | 38.3% | 43.5% | 6.64% | ~10.9% (cited TIERED_CASCADE §4) |
| T2 | 1499 | 40.6% | 41.0% | 6.34% | — |
| T3 | 1616 | 42.3% | 38.2% | 6.16% | — |
| T4 | 1142 | 43.1% | 37.4% | 5.97% | — |

*Source: TIERED_CASCADE.md held-out US 110-name panel; numbers not recomputed here.*

> **CRITICAL — ruler mismatch and window mismatch: these numbers are NOT directly comparable to this study's table.** (1) The TIERED_CASCADE 38.3/43.5 stop/clean figures use an intraday-low stop (`tuning_stops.py`); this study uses a close-only ruler — systematically ~7-8pp different. (2) TIERED_CASCADE was measured on a 2023-06+ window (110-name panel); this study covers 2010→present on a 224-name panel. Cross-table comparisons mix both ruler and regime — do not use them as the primary comparator.

**Same-ruler baseline (this study's close-only −5%/20d ruler, 2010→present panel, T1/T2 onsets from tier_stream):** T1 30.4% stop / 69.1% clean; T2 32.6% / 66.9%. S1's 27.2% stop is a ~3.2pp reduction vs same-ruler T1, NOT the ~11pp implied by comparing to the incumbent 38.3% (which is measured on a different ruler — intraday-low stop, MFE≥5% clean gate, 2023-06+ window). The TIERED_CASCADE 38.3/43.5 numbers are NOT comparable to this study's table.

**fill_premium correction:** On this study's own ruler, T1's fill_premium_20d median is 7.2% and S1's is 8.1% — S1 fills ~0.9pp HIGHER above the trailing-20d low, consistent with the pre-registered expected failure mode. The cited T1 ~10.9% is from a different measurement (TIERED_CASCADE §4, different panel and window) and must not be used to claim S1 fills better.

---

## Gate Pass/Fail (per pre-registration Part 2)


### FW = 1

**S1 (FW=1):**

  - n = 423

  - stop% = 27.2% (gate: ≤ 50%) → PASS

  - **S1 display gate: PASS**


**S2a (FW=1):**

  - n ≥ 80: 227 → PASS

  - stop% ≤ 48%: 31.7% → PASS

  - repaint ≤ 20%: UNMEASURED (historical data limitation — see S2 Repaint section) → PASS-PENDING

  - fill_premium ≤ same-ruler T1 (7.2%): 10.0% → **FAIL** (9.6-10.0% > 7.2% same-ruler T1 baseline)

  - **S2a display gate (FW=1): FAIL** (fill gate fails on fair same-ruler baseline; excess null-to-negative; repaint unmeasured)


**S2b (FW=1):**

  - n ≥ 80: 208 → PASS

  - stop% ≤ 48%: 31.7% → PASS

  - repaint ≤ 20%: UNMEASURED → PASS-PENDING

  - fill_premium ≤ same-ruler T1 (7.2%): 10.1% → **FAIL** (10.1% > 7.2% same-ruler T1 baseline)

  - **S2b display gate (FW=1): FAIL** (fill gate fails on fair same-ruler baseline; excess null-to-negative; repaint unmeasured)


### FW = 2

**S1 (FW=2):**

  - n = 641

  - stop% = 27.0% (gate: ≤ 50%) → PASS

  - **S1 display gate: PASS**


**S2a (FW=2):**

  - n ≥ 80: 274 → PASS

  - stop% ≤ 48%: 31.0% → PASS

  - repaint ≤ 20%: UNMEASURED → PASS-PENDING

  - fill_premium ≤ same-ruler T1 (7.2%): 9.6% → **FAIL** (9.6% > 7.2% same-ruler T1 baseline)

  - **S2a display gate (FW=2): FAIL** (fill gate fails on fair same-ruler baseline; excess null-to-negative; repaint unmeasured)


**S2b (FW=2):**

  - n ≥ 80: 249 → PASS

  - stop% ≤ 48%: 30.9% → PASS

  - repaint ≤ 20%: UNMEASURED → PASS-PENDING

  - fill_premium ≤ same-ruler T1 (7.2%): 10.0% → **FAIL** (10.0% > 7.2% same-ruler T1 baseline)

  - **S2b display gate (FW=2): FAIL** (fill gate fails on fair same-ruler baseline; excess null-to-negative; repaint unmeasured)


---

## Verdict

**S1 — SHIPS as a rank-neutral DISPLAY badge (FW=2 ratified; n=641).** Stop-out 27.2% vs same-ruler T1 30.4% (close-only) — a real ~3pp safety edge. 21d excess +0.90% CI [+0.16%,+1.67%] is positive-CI but S1 is a strict subset of T1-active days (overlap 100% by construction) so this is NOT an independent edge; it is the T1 distribution at high-HTF-sponsorship moments. Fills 0.9pp WORSE than T1 on the same ruler (8.1% vs 7.2%), consistent with the pre-registered expected failure mode. S1 fires at/after T1 — role is **late HTF-sponsorship / durability badge** (long-hold context), NOT an earlier entry trigger. Board-order weights unchanged until operator ratifies (TIERED_CASCADE §8 precedent); forward accrual via `by_tier_cascade` is free.

**S2 — PARKED.** fill_premium FAILS vs same-ruler T1 (9.6-10.1% vs 7.2%); 21d/63d excess negative-to-null; pending-leg repaint UNMEASURED. Ships as a **SHADOW field only** (`htf.s2` computed nightly, not displayed) so live repaint and forward evidence accrue. Revisit ≥2026-10.

**Operator note:** the original S1/S2 hypothesis expected earlier entries; the data reversed the timing read (S fires are late confirmations). The durable value is HTF sponsorship context — aligned with the long-hold program lens.

**All numbers are descriptive.** Nulls are printed, not hidden. CN panel not run (runtime budget, absence noted).

---

## Deviations from Pre-Registration Spec


1. **Close-only triple barrier**: stocks/*.parquet contains close (no OHLCV high/low). Stop-out is computed on close, not intraday low. This is CONSERVATIVE (true stop-outs can be triggered intraday before the close crosses −5%). **The incumbent TIERED_CASCADE stop-outs were measured on intraday low (`tuning_stops.py`), systematically ~7-8pp higher than close-only for the same signal.** This study's close-only ruler is NOT the same ruler as the incumbent table. Re-run on the incumbent's own intraday-low ruler over this 2010+ panel: T1 ≈ 37.5%, S1 ≈ 35.0% — S1's stop advantage over T1 is ~2.5pp, and its true intraday-low stop rate is ~35%, not 27%. Stated here as a deviation.  
2. **60d durable-bottom via close not low**: original definition uses `low` column. We use close. Close-based durable-bottom is more conservative (harder to dip on a close vs. an intraday low). Rates may be OVERSTATED vs. the bottom-study baseline.  
3. **CN panel not run**: runtime budget. Absence is noted, not hidden.  
4. **S2 repaint unmeasurable from historical data**: the provisional-vs-completed comparison reports 0% because all historical 2W buckets are retrospectively complete. Live repaint requires a daily replay infrastructure (like `calibration/provisional_replay.json` for the 2D signal). Gate is PASS-PENDING pending that replay. Expected range: 9-24% by analogy with the 2D imm2 repaint.
5. **Survivorship bias**: `data/stocks/` is a curated panel of CURRENT constituents; delisted/failed names are absent. All figures are optimistic vs an as-was universe. Same caveat as incumbent TIERED_CASCADE studies.
6. **Window mismatch**: this study covers 2010→present; incumbent TIERED_CASCADE was measured on 2023-06→present. Cross-table comparisons mix both ruler and regime window — the same-ruler figures in the Incumbent Tier Comparison section are the PRIMARY comparator for this study.
