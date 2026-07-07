# Backtest Results V2 — MRI CPI Component Upgrade (Shelter Leg)

**Run date:** 2026-07-07
**Spec:** research/release_forecast/PREREG_V2.md (frozen before run)
**Changes vs V1:** shelter_nowcast leg added to cpi_headline (feature 9) and cpi_core (feature 8).
**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs — UNCHANGED
**Kill rule:** model MAE >= naive MAE in BOTH full AND 2021+ slice -> benchmark_only — UNCHANGED
**NFP:** unchanged from V1 — not re-run.

---

## AMENDMENTS — B1 Shelter Look-Ahead Leak Fix (2026-07-07)

**Bug fix applied before these results were generated.** This is NOT a new spec attempt.

**B1 — Look-ahead leak in `_get_shelter_mom_last`** (engine/release_components_cpi.py):

Prior code filtered CUSR0000SAH1 with `shelter_df.index <= asof_ts` (asof being the day
before the target CPI release). Because CUSR0000SAH1 is a latest-revised parquet (not
ALFRED-vintaged), the parquet contains months M and M+1 that had not yet released at
decision date D. These were improperly admitted.

Fix: cap at `(asof_period - 2).to_timestamp(how="E")`. For asof in month M+1 (the day
before M's release), this restricts shelter to month M-1 — exactly what PREREG_V2.md §2.3
states ("the last knowable shelter print is for month M-1"). This restores the frozen spec;
it is a bug fix, not a new spec change.

**Impact**: the reviewer's independent measurement predicted post-fix core 2021+ ≈ 0.1219 and
headline 2021+ ≈ 0.2162. The actual corrected numbers are core 2021+ = 0.1386 and headline
2021+ = 0.2253. Both targets remain active (kill rule requires BOTH full AND 2021+ to fail;
cpi_core full = 0.0936 still beats naive 0.0991). Deviation from reviewer prediction is
flagged for orchestrator review; the corrected numbers below are ground truth.

**M4 — n_with_shelter_active diagnostic**: prior code used `n_features_used >= 9` as a proxy
for shelter_nowcast presence. Fix: annotate `shelter_nowcast_present` directly from the
feature row in `_wf_cpi_full` and count it directly. Corrected count: 292 / 292 for both
targets (shelter_nowcast is non-null for ALL predictions because the BLS momentum fallback
activates whenever CUSR0000SAH1 data is available, which goes back to 1953. The 'ZORI-active'
window starts ~2016; see ZORI ablation section below for ZORI's marginal contribution).

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

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.2260 | 0.2610 | 0.2618 | 0.2162 | 0.3074 | 0.3403 | 76.5% | 0.728 | [0.667, 0.782] | 228 |
| pre-2010 | 96 | 0.2663 | 0.3340 | 0.3408 | 0.2650 | 0.3697 | 0.4156 | 61.1% | 0.688 | [0.588, 0.773] | 93 |
| 2010–2020-02 | 122 | 0.1891 | 0.2081 | 0.2072 | 0.1713 | 0.2350 | 0.2643 | 86.9% | 0.803 | [0.687, 0.884] | 61 |
| COVID (2020-03..06) | 4 | 0.5541 | 0.5611 | 0.6513 | 0.4266 | 0.5678 | 0.5775 | 0.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1208 | 0.1477 | 0.2616 | 0.1021 | 0.1640 | 0.1597 | 100.0% | 0.667 | [0.300, 0.903] | 6 |
| 2021+ | 64 | 0.2253 | 0.2442 | 0.2233 | 0.2263 | 0.3132 | 0.3361 | 76.6% | 0.719 | [0.599, 0.814] | 64 |
| 2015+ (stable feature set, supplementary) | 136 | 0.2190 | 0.2303 | 0.2209 | 0.1968 | 0.2908 | 0.3035 | 79.4% | 0.729 | [0.627, 0.812] | 85 |

### V1 vs V2 Comparison Table

Key question: does the shelter leg fix cpi_core's 2021+ loss to naive (V1: MAE model=0.1355 vs naive=0.1297)?

| Era | n | MAE_v1 | MAE_v2 | MAE_naive | Cov_v1 | Cov_v2 | Skew_HR_v1 | Skew_HR_v2 |
|-----|---|--------|--------|-----------|--------|--------|------------|------------|
| Full | 292 | 0.2251 | 0.2260 | 0.2610 | 78.4% | 76.5% | 0.706 | 0.728 |
| pre-2010 | 96 | 0.2650 | 0.2663 | 0.3340 | 62.5% | 61.1% | 0.688 | 0.688 |
| 2010–2020-02 | 122 | 0.1891 | 0.1891 | 0.2081 | 87.7% | 86.9% | 0.770 | 0.803 |
| 2021+ | 64 | 0.2246 | 0.2253 | 0.2442 | 81.2% | 76.6% | 0.672 | 0.719 |
| 2015+ (stable feature set) | 136 | 0.2172 | 0.2190 | 0.2303 | 82.3% | 79.4% | 0.682 | 0.729 |
| 2016+ (shelter active) | 124 | — | 0.2172 | 0.2296 | — | 78.2% | — | 0.729 |

### Kill Rule Detail (V2)

- Full window: MAE model=0.2260 vs naive=0.2610
- 2021+ slice: MAE model=0.2253 vs naive=0.2442
- Kill triggered: NO -> active

---
## cpi_core

**V2 Status:** active
**Kill rule V2:** NOT triggered. Model beats naive in at least one window.
**Total predictions:** 292
**Predictions with shelter active:** 292

### V2 Era-Split Metrics

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.0936 | 0.0991 | 0.0991 | 0.0900 | 0.1301 | 0.1337 | 77.2% | 0.630 | [0.565, 0.690] | 227 |
| pre-2010 | 96 | 0.0832 | 0.0935 | 0.0866 | 0.0821 | 0.1031 | 0.1187 | 81.9% | 0.685 | [0.584, 0.771] | 92 |
| 2010–2020-02 | 122 | 0.0721 | 0.0735 | 0.0722 | 0.0621 | 0.0931 | 0.0959 | 83.6% | 0.607 | [0.481, 0.719] | 61 |
| COVID (2020-03..06) | 4 | 0.2247 | 0.3383 | 0.3323 | 0.2626 | 0.3229 | 0.3399 | 50.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1287 | 0.2225 | 0.2532 | 0.1334 | 0.1704 | 0.2361 | 50.0% | 0.833 | [0.436, 0.970] | 6 |
| 2021+ | 64 | 0.1386 | 0.1297 | 0.1401 | 0.1402 | 0.1885 | 0.1746 | 64.1% | 0.547 | [0.426, 0.663] | 64 |
| 2015+ (stable feature set, supplementary) | 136 | 0.1148 | 0.1185 | 0.1218 | 0.1078 | 0.1614 | 0.1593 | 67.7% | 0.600 | [0.494, 0.698] | 85 |

### V1 vs V2 Comparison Table

Key question: does the shelter leg fix cpi_core's 2021+ loss to naive (V1: MAE model=0.1355 vs naive=0.1297)?

| Era | n | MAE_v1 | MAE_v2 | MAE_naive | Cov_v1 | Cov_v2 | Skew_HR_v1 | Skew_HR_v2 |
|-----|---|--------|--------|-----------|--------|--------|------------|------------|
| Full | 292 | 0.0924 | 0.0936 | 0.0991 | 76.5% | 77.2% | 0.639 | 0.630 |
| pre-2010 | 96 | 0.0821 | 0.0832 | 0.0935 | 81.9% | 81.9% | 0.685 | 0.685 |
| 2010–2020-02 | 122 | 0.0721 | 0.0721 | 0.0735 | 82.8% | 83.6% | 0.623 | 0.607 |
| 2021+ | 64 | 0.1355 | 0.1386 | 0.1297 | 62.5% | 64.1% | 0.562 | 0.547 |
| 2015+ (stable feature set) | 136 | 0.1130 | 0.1148 | 0.1185 | 66.2% | 67.7% | 0.624 | 0.600 |
| 2016+ (shelter active) | 124 | — | 0.1190 | 0.1231 | — | 66.1% | — | 0.600 |

### Kill Rule Detail (V2)

- Full window: MAE model=0.0936 vs naive=0.0991
- 2021+ slice: MAE model=0.1386 vs naive=0.1297
- Kill triggered: NO -> active

### cpi_core 2021+ VERDICT (primary question)

- V1 MAE model (2021+): 0.1355
- V2 MAE model (2021+): 0.1386
- Naive MAE (2021+): 0.1297
- **VERDICT: NOT FIXED** — cpi_core still loses to naive in 2021+.
  V2 MAE 0.1386 vs naive 0.1297.
  Change vs V1: 0.0031 pp worsened.

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

## ZORI Marginal Contribution (Ablation)

Run on post-B1-corrected code. ZORI-OFF = `_load_zori_national` returns None for all steps
(shelter_nowcast falls back to pure BLS momentum, k=0). ZORI-ON = shipped spec. All other
parameters unchanged.

| Target | Window | MAE (ZORI-ON) | MAE (ZORI-OFF) | Delta (ON-OFF) | Verdict |
|--------|--------|---------------|----------------|----------------|---------|
| cpi_headline | Full (292) | 0.2260 | 0.2272 | -0.0012 | **ZORI HELPS** |
| cpi_headline | 2021+ (64) | 0.2253 | 0.2279 | -0.0026 | **ZORI HELPS** |
| cpi_headline | 2016+ (124) | 0.2172 | 0.2200 | -0.0028 | **ZORI HELPS** |
| cpi_core | Full (292) | 0.0936 | 0.0930 | +0.0006 | **ZORI HURTS** |
| cpi_core | 2021+ (64) | 0.1386 | 0.1358 | +0.0028 | **ZORI HURTS** |
| cpi_core | 2016+ (124) | 0.1190 | 0.1177 | +0.0013 | **ZORI HURTS** |

**Summary:**
- **cpi_headline**: ZORI helps in all windows (−0.0012 to −0.0028 pp MAE). ZORI adds value.
- **cpi_core**: ZORI hurts in all windows (+0.0006 to +0.0028 pp MAE). ZORI slightly degrades core.

**SHIPPED SPEC REMAINS ZORI-ON.** Per the spec-attempt ledger, retiring a leg from the same
backtest that measured it would constitute within-sample mining (the ablation uses the same
data that generated these results). ZORI retirement requires forward-ledger evidence or a
program-level adjudication with a separate held-out window.

Note on ZORI-OFF "N with shelter active = 292": even ZORI-OFF shows shelter_nowcast non-null
for all 292 steps because the BLS momentum fallback (k=0, pure cpi_shelter_mom_last) is always
available from the 1953 history. The 2016+ window isolates where ZORI actually contributes.

---

## Corrected Per-Target Verdicts vs Kill Rule

Kill rule: model MAE >= naive MAE in BOTH full AND 2021+ → benchmark_only.

| Target | Full MAE model | Full MAE naive | 2021+ MAE model | 2021+ MAE naive | Kill? | Status |
|--------|---------------|----------------|-----------------|-----------------|-------|--------|
| cpi_headline | 0.2260 | 0.2610 | 0.2253 | 0.2442 | NO | **active** |
| cpi_core | 0.0936 | 0.0991 | 0.1386 | 0.1297 | NO (full beats naive) | **active** |

- **cpi_headline**: beats naive in BOTH full (0.2260 < 0.2610) AND 2021+ (0.2253 < 0.2442). Kill not triggered.
- **cpi_core**: beats naive on full (0.0936 < 0.0991) but loses on 2021+ (0.1386 > 0.1297). Kill rule requires BOTH to fail — since full beats naive, kill NOT triggered. Status: active.
  - Note: cpi_core 2021+ still losses to naive after the B1 fix. The leaky code showed a false fix (0.1244 < 0.1297). The corrected code shows the shelter leg modestly worsens 2021+ performance vs V1 (0.1386 vs 0.1355). ZORI is the main contributor to the degradation (+0.0028 pp in 2021+).
  - cpi_core remains active because full-window performance still beats naive. The 2021+ degradation is a concern but does not trigger kill.