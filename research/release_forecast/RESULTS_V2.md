# Backtest Results V2 — MRI CPI Component Upgrade (Shelter Leg)

**Run date:** 2026-07-10
**Spec:** research/release_forecast/PREREG_V2.md (frozen before run)
**Changes vs V1:** shelter_nowcast leg added to cpi_headline (feature 9) and cpi_core (feature 8).
**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs — UNCHANGED
**Kill rule:** model MAE >= naive MAE in BOTH full AND 2021+ slice -> benchmark_only — UNCHANGED
**NFP:** unchanged from V1 — not re-run.

## Summary

| Release | Status | N predictions | N with shelter active |
|---------|--------|---------------|-----------------------|
| cpi_headline | **active** | 292 | 292 |
| cpi_core | **active** | 292 | 292 |

---
## cpi_headline

**V2 Status:** active
**Kill rule V2:** NOT triggered. Model beats naive in at least one window.
**Total predictions:** 292
**Predictions with shelter active:** 292

### V2 Era-Split Metrics

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | MAE ExpandMean* | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|-----------------|------------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.1590 | 0.2610 | 0.2618 | 0.2162 | 0.2323 | 0.2064 | 0.3403 | 71.3% | 0.798 | [0.741, 0.845] | 228 |
| pre-2010 | 96 | 0.1415 | 0.3340 | 0.3408 | 0.2650 | 0.2753 | 0.1957 | 0.4156 | 65.3% | 0.892 | [0.813, 0.941] | 93 |
| 2010–2020-02 | 122 | 0.1659 | 0.2081 | 0.2072 | 0.1713 | 0.1817 | 0.2105 | 0.2643 | 70.5% | 0.820 | [0.705, 0.896] | 61 |
| COVID (2020-03..06) | 4 | 0.2479 | 0.5611 | 0.6513 | 0.4266 | 0.5459 | 0.2643 | 0.5775 | 50.0% | 1.000 | [0.510, 1.000] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.0880 | 0.1477 | 0.2616 | 0.1021 | 0.1654 | 0.1527 | 0.1597 | 83.3% | 0.833 | [0.436, 0.970] | 6 |
| 2021+ | 64 | 0.1732 | 0.2442 | 0.2233 | 0.2263 | 0.2516 | 0.2142 | 0.3361 | 79.7% | 0.625 | [0.503, 0.733] | 64 |
| 2015+ (stable feature set, supplementary) | 136 | 0.1812 | 0.2303 | 0.2209 | 0.1968 | 0.2107 | 0.2259 | 0.3035 | 72.1% | 0.682 | [0.577, 0.772] | 85 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history; strictly no-lookahead. Strongest naive = min(MAE Naive, MAE ExpandMean, trailing MAE).

### V1 vs V2 Comparison Table

Key question: does the shelter leg fix cpi_core's 2021+ loss to naive (V1: MAE model=0.1355 vs naive=0.1297)?

| Era | n | MAE_v1 | MAE_v2 | MAE_naive | Cov_v1 | Cov_v2 | Skew_HR_v1 | Skew_HR_v2 |
|-----|---|--------|--------|-----------|--------|--------|------------|------------|
| Full | 292 | 0.1590 | 0.1590 | 0.2610 | 71.3% | 71.3% | 0.798 | 0.798 |
| pre-2010 | 96 | 0.1415 | 0.1415 | 0.3340 | 65.3% | 65.3% | 0.892 | 0.892 |
| 2010–2020-02 | 122 | 0.1659 | 0.1659 | 0.2081 | 70.5% | 70.5% | 0.820 | 0.820 |
| 2021+ | 64 | 0.1732 | 0.1732 | 0.2442 | 79.7% | 79.7% | 0.625 | 0.625 |
| 2015+ (stable feature set) | 136 | 0.1812 | 0.1812 | 0.2303 | 72.1% | 72.1% | 0.682 | 0.682 |
| 2016+ (shelter active) | 124 | — | 0.1757 | 0.2296 | — | 72.6% | — | 0.682 |

### Kill Rule Detail (V2)

- Full window: MAE model=0.1590 vs naive=0.2610
- 2021+ slice: MAE model=0.1732 vs naive=0.2442
- Kill triggered: NO -> active

---
## cpi_core

**V2 Status:** active
**Kill rule V2:** NOT triggered. Model beats naive in at least one window.
**Total predictions:** 292
**Predictions with shelter active:** 292

### V2 Era-Split Metrics

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | MAE ExpandMean* | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|-----------------|------------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.0936 | 0.0991 | 0.0991 | 0.0900 | 0.0999 | 0.1301 | 0.1337 | 77.2% | 0.630 | [0.565, 0.690] | 227 |
| pre-2010 | 96 | 0.0832 | 0.0935 | 0.0866 | 0.0821 | 0.0780 | 0.1031 | 0.1187 | 81.9% | 0.685 | [0.584, 0.771] | 92 |
| 2010–2020-02 | 122 | 0.0721 | 0.0735 | 0.0722 | 0.0621 | 0.0640 | 0.0931 | 0.0959 | 83.6% | 0.607 | [0.481, 0.719] | 61 |
| COVID (2020-03..06) | 4 | 0.2247 | 0.3383 | 0.3323 | 0.2626 | 0.2913 | 0.3229 | 0.3399 | 50.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1287 | 0.2225 | 0.2532 | 0.1334 | 0.1681 | 0.1704 | 0.2361 | 50.0% | 0.833 | [0.436, 0.970] | 6 |
| 2021+ | 64 | 0.1386 | 0.1297 | 0.1401 | 0.1402 | 0.1823 | 0.1885 | 0.1746 | 64.1% | 0.547 | [0.426, 0.663] | 64 |
| 2015+ (stable feature set, supplementary) | 136 | 0.1148 | 0.1185 | 0.1218 | 0.1078 | 0.1307 | 0.1614 | 0.1593 | 67.7% | 0.600 | [0.494, 0.698] | 85 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history; strictly no-lookahead. Strongest naive = min(MAE Naive, MAE ExpandMean, trailing MAE).

### V1 vs V2 Comparison Table

Key question: does the shelter leg fix cpi_core's 2021+ loss to naive (V1: MAE model=0.1355 vs naive=0.1297)?

| Era | n | MAE_v1 | MAE_v2 | MAE_naive | Cov_v1 | Cov_v2 | Skew_HR_v1 | Skew_HR_v2 |
|-----|---|--------|--------|-----------|--------|--------|------------|------------|
| Full | 292 | 0.0936 | 0.0936 | 0.0991 | 77.2% | 77.2% | 0.630 | 0.630 |
| pre-2010 | 96 | 0.0832 | 0.0832 | 0.0935 | 81.9% | 81.9% | 0.685 | 0.685 |
| 2010–2020-02 | 122 | 0.0721 | 0.0721 | 0.0735 | 83.6% | 83.6% | 0.607 | 0.607 |
| 2021+ | 64 | 0.1386 | 0.1386 | 0.1297 | 64.1% | 64.1% | 0.547 | 0.547 |
| 2015+ (stable feature set) | 136 | 0.1148 | 0.1148 | 0.1185 | 67.7% | 67.7% | 0.600 | 0.600 |
| 2016+ (shelter active) | 124 | — | 0.1190 | 0.1231 | — | 66.1% | — | 0.600 |

### Kill Rule Detail (V2)

- Full window: MAE model=0.0936 vs naive=0.0991
- 2021+ slice: MAE model=0.1386 vs naive=0.1297
- Kill triggered: NO -> active

### cpi_core 2021+ VERDICT (primary question)

- V1 MAE model (2021+): 0.1386
- V2 MAE model (2021+): 0.1386
- Naive MAE (2021+): 0.1297
- **VERDICT: NOT FIXED** — cpi_core still loses to naive in 2021+.
  V2 MAE 0.1386 vs naive 0.1297.
  Change vs V1: 0.0000 pp worsened.

---
## Data Sources Used in V2

- **ZORI:** `data/zori/national.parquet` (fetched by `scripts/collect_zori.py`)
  - History: 2015-01-31 through latest available (137 months as of 2026-07-07)
  - PIT lag: 45 days conservative (PREREG_V2.md §1.1)
  - Revision status: revision_optimistic (Zillow re-benchmarks periodically)
  - Knowability: ZORI for month M is usable at decision date D if M_end_of_month + 45 days <= D

- **CPI Shelter (CUSR0000SAH1):** `data/fred/CUSR0000SAH1.parquet`
  - Latest-revised (not ALFRED-vintaged) — declared revision_optimistic
  - Full history available from 1947-01

- **Shelter nowcast:** (1-k)*cpi_shelter_mom_last + k*zori_signal, k=0.35 frozen
  - Divergence guard: k halved to 0.175 when |zori_signal - cpi_shelter_mom| > 3*sigma_24m
  - First usable in predictions: ~2016-01 (when ZORI lease-reset window M-12..M-6 has data)

*Pre-registered spec frozen before any results were observed. Anti-mining: 2 of 2 attempts used.*

---
## §12 Restatement (2026-07-10, MRI-R28b)

expanding_mean benchmark added to era tables above (REPORTED, non-binding per MRI-R28b).
V2 verdicts stand as frozen. All §12 new tracks use the STRONGEST naive as kill benchmark.
See RESULTS_V1.md §12 Restatement for per-target vs-strongest-naive detail.

---

## MRI-R30 Recalibration (2026-07-10) — Vol-Scaled Residual Quantile Bands

**Spec:** research/release_forecast/PREREG_INTERVAL_RECAL_V1.md (frozen before run)
**Implementation:** `engine/release_forecast._compute_quantiles_volscaled` (W=24, MIN_SIGMA_OBS=12)
**Points unchanged** — only the bands move (byte-identity on point estimates verified by test suite).

Coverage falsifiers that triggered recalibration (§6 gate [70%,95%]):
- cpi_core 2021+: **64.1%** (BEFORE) — below 70%
- pce_core 2021+: **67.7%** (BEFORE) — below 70%
- nfp 2021+: **64.6%** (BEFORE) — below 70% (champion; see its section below)

Prereg errata (declared, immaterial): the implementation guards degenerate sigma
with epsilon 1e-10 where PREREG §1.2/§3 wrote literal `sigma > 0` — np.std of a
constant array returns ~7e-18, not exactly 0. Residual scales here are ~0.1–500,
so the epsilon cannot alter any real band; recorded per §6 exactness discipline.

### cpi_headline — BEFORE vs AFTER

| Era | n | p10-p90 BEFORE | p10-p90 AFTER | p25-p75 BEFORE | p25-p75 AFTER | Pinball BEFORE | Pinball AFTER |
|-----|---|----------------|---------------|----------------|---------------|----------------|---------------|
| Full | 292 | 71.3% | 76.9% | 39.6% | 46.3% | 0.294470 | 0.293403 |
| 2021+ | 64 | 79.7% | 73.4% | 42.2% | 42.2% | 0.298165 | 0.299316 |
| 2015+ | 136 | 72.1% | 77.2% | 39.0% | 45.6% | 0.316736 | 0.314082 |

**Verdict:** Coverage remains in [70%,95%] before and after. 2021+ coverage decreases slightly (79.7%→73.4%) but stays within gate. Full-window coverage improves (71.3%→76.9%). Pinball marginally improves on full window.

### cpi_core — BEFORE vs AFTER

| Era | n | p10-p90 BEFORE | p10-p90 AFTER | p25-p75 BEFORE | p25-p75 AFTER | Pinball BEFORE | Pinball AFTER |
|-----|---|----------------|---------------|----------------|---------------|----------------|---------------|
| Full | 292 | 77.2% | 81.3% | 48.9% | 50.4% | 0.171620 | 0.168916 |
| 2021+ | 64 | **64.1%** | **81.2%** | 37.5% | 56.2% | 0.261833 | 0.250759 |
| 2015+ | 136 | 67.7% | 83.1% | 41.9% | 52.9% | 0.216444 | 0.211488 |

**Verdict (PRIMARY — MRI-R30 trigger):** cpi_core 2021+ coverage moves from **64.1%** (below [70%,95%] gate) to **81.2%** (within gate). Pinball improves on all eras. Vol-scaling successfully adapts to the elevated inflation-regime residual dispersion. Forward gate (§6): if coverage exits [70%,95%] after 12 more prints, quantile claims drop from UI.

Note: cpi_core was the primary falsifier target. Before recalibration, the static bands underestimated the 2021+ regime's residual dispersion. Vol-scaling recognizes the widening uncertainty and expands bands appropriately.

### nfp (champion) — BEFORE vs AFTER

| Era | n | p10-p90 BEFORE | p10-p90 AFTER | p25-p75 BEFORE | p25-p75 AFTER | Pinball BEFORE | Pinball AFTER |
|-----|---|----------------|---------------|----------------|---------------|----------------|---------------|
| Full | 293 | 72.9% | 80.3% | 45.0% | 51.7% | 673.90 | 851.08 |
| 2021+ | 65 | **64.6%** | **81.5%** | 38.5% | 58.5% | 451.93 | **1044.81** |

**Verdict (honest trade-off — the recalibration's WORST metric):** nfp 2021+
coverage was itself a §6 falsifier (64.6% < 70%) and moves into gate (81.5%).
But pinball sharpness degrades materially — **2.31× worse in 2021+** (451.93 →
1044.81) and +26% on the full window (673.90 → 851.08). Mechanism: the trailing
σ_t window still carries COVID-era residuals (2020-03..06 shocks of ±10^3–10^4k)
into the early-2020s bands, over-widening NFP intervals long after the shock;
the CPI-family targets do not have residuals of that magnitude, so they gain
coverage without paying comparable sharpness. Per MRI-R30 the spec is ONE
uniform recalibration with no per-target tuning — NFP ships with these wider
bands and the degradation printed. The §6 forward gate governs: if nfp p10–p90
coverage exits [70%,95%] after 12 more forward prints, its quantile claims drop
from the UI; sharpness is additionally tracked via the shipped pinball
scoreboard column (MRI-R31), and a future program-level adjudication may
consider a COVID-exclusion amendment to σ_t as a NEW chartered spec — it is NOT
permitted as a quiet fix under this one-shot recalibration.