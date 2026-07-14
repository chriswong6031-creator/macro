# Backtest Results V1 — Macro Release Intelligence

**Run date:** 2026-07-07
**Spec:** research/release_forecast/PREREG_V1.md (frozen before run)
**Algorithm:** Ridge (lambda=1.0, numpy closed-form), expanding window, min 60 obs
**Era law:** pre-2010 / 2010-01..2020-02 / COVID 2020-03..06 / 2020-07..12 (recovery gap) / 2021+; NFP COVID printed separately
**Kill rule:** model MAE >= naive MAE in BOTH full/2010+ AND 2021+ slice -> benchmark_only

## Summary

| Release | Status | N predictions (total) | N eval predictions |
|---------|--------|-----------------------|--------------------|
| cpi_headline | **active** | 292 | 292 |
| cpi_core | **active** | 292 | 292 |
| nfp | **active** | 293 | 197 |
| claims | **benchmark_only** | 890 | 890 |

*NFP n_eval_predictions = 2010+ only per PREREG_V1.md §4.1; pre-2010 NFP rows trained on but not reported in full-window metrics.*

---
## cpi_headline

**Status:** active
**Kill rule:** NOT triggered. Model beats naive in at least one of: full/2010+ window, 2021+ slice.
**Total predictions:** 292

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3/expanding_mean*; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

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

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- Full window: MAE model=0.1590 vs naive=0.2610
- 2021+ slice: MAE model=0.1732 vs naive=0.2442
- Kill triggered: NO -> active

### Vs Strongest Naive (REPORTED, MRI-R28b — non-binding)

Strongest naive = min(naive_prior, trailing3m/4w, expanding_mean).
- Full window: model MAE=0.1590 vs strongest_naive=0.2323 — margin=0.0733 (BEATS)
- 2021+ slice: model MAE=0.1732 vs strongest_naive=0.2233 — margin=0.0501 (BEATS)

---
## cpi_core

**Status:** active
**Kill rule:** NOT triggered. Model beats naive in at least one of: full/2010+ window, 2021+ slice.
**Total predictions:** 292

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3/expanding_mean*; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

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

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- Full window: MAE model=0.0936 vs naive=0.0991
- 2021+ slice: MAE model=0.1386 vs naive=0.1297
- Kill triggered: NO -> active

### Vs Strongest Naive (REPORTED, MRI-R28b — non-binding)

Strongest naive = min(naive_prior, trailing3m/4w, expanding_mean).
- Full window: model MAE=0.0936 vs strongest_naive=0.0991 — margin=0.0055 (BEATS)
- 2021+ slice: model MAE=0.1386 vs strongest_naive=0.1297 — margin=-0.0089 (LAGS)

---
## nfp

**Status:** active
**Kill rule:** NOT triggered. Model beats naive in at least one of: full/2010+ window, 2021+ slice.
**Total predictions:** 293
**Eval predictions (2010+):** 197

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3/expanding_mean*; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | MAE ExpandMean* | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|-----------------|------------|------------|-------------|---------|---------------|--------|
| Full (2010+, per prereg) | 197 | 372.2171 | 459.8426 | 440.7563 | 635.1929 | 363.6429 | 2161.1911 | 2191.4446 | 73.1% | 0.637 | [0.545, 0.720] | 113 |
| pre-2010 | 96 | 143.2956 | 153.9792 | 143.2222 | 140.2393 | 195.1565 | 202.1443 | 217.4352 | 72.2% | 0.616 | [0.511, 0.712] | 86 |
| 2010–2020-02 | 122 | 160.4827 | 175.4918 | 148.6011 | 144.7864 | 179.0605 | 259.5711 | 270.7632 | 82.0% | 0.646 | [0.525, 0.751] | 65 |
| COVID (2020-03..06) | 4 | 8592.7911 | 11669.0000 | 10420.5833 | 15473.8886 | 7096.6841 | 15012.2715 | 15144.9068 | 25.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 674.8891 | 815.8333 | 1951.8889 | 4523.0662 | 779.5035 | 791.8835 | 1316.4738 | 16.7% | 0.333 | [0.097, 0.700] | 6 |
| 2021+ | 65 | 235.8056 | 270.8923 | 235.4769 | 283.6171 | 257.3618 | 320.6112 | 377.5027 | 64.6% | 0.658 | [0.499, 0.788] | 38 |
| 2010–2020-02 (excl. COVID) | 122 | 160.4827 | 175.4918 | 148.6011 | 144.7864 | 179.0605 | 259.5711 | 270.7632 | 82.0% | 0.646 | [0.525, 0.751] | 65 |
| 2015+ (stable feature set, supplementary) | 137 | 440.0936 | 566.8394 | 549.2190 | 832.5110 | 427.3257 | 2581.6093 | 2618.0781 | 73.0% | 0.636 | [0.543, 0.720] | 110 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history; strictly no-lookahead. Strongest naive = min(MAE Naive, MAE ExpandMean, trailing MAE).

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- 2010+ window (per prereg): MAE model=372.2171 vs naive=459.8426
- 2021+ slice: MAE model=235.8056 vs naive=270.8923
- Kill triggered: NO -> active

### Vs Strongest Naive (REPORTED, MRI-R28b — non-binding)

Strongest naive = min(naive_prior, trailing3m/4w, expanding_mean).
- 2010+ window (per prereg): model MAE=372.2171 vs strongest_naive=363.6429 — margin=-8.5742 (LAGS)
- 2021+ slice: model MAE=235.8056 vs strongest_naive=235.4769 — margin=-0.3287 (LAGS)

---
## claims

**Status:** benchmark_only
**Kill rule triggered:** model MAE >= naive MAE in full/2010+ window AND 2021+ slice.
**Total predictions:** 890

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3/expanding_mean*; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

| Era | n | MAE Model | MAE Naive | MAE Trail4w | MAE AR3 | MAE ExpandMean* | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|-----------------|------------|------------|-------------|---------|---------------|--------|
| Full | 890 | 43.8551 | 27.9135 | 43.7166 | 32.9923 | 175.2787 | 285.3927 | 167.0822 | 80.8% | 0.612 | [0.579, 0.644] | 845 |
| pre-2010 | 30 | 20.1833 | 18.1667 | 18.9250 | 16.1466 | 42.2243 | 27.1199 | 22.0658 | 83.3% | 0.552 | [0.375, 0.716] | 29 |
| 2010–2020-02 | 531 | 12.2622 | 12.4087 | 12.0080 | 11.5155 | 90.7542 | 16.3839 | 16.7695 | 87.4% | 0.644 | [0.601, 0.685] | 503 |
| 2010–2019 (pre-COVID visibility) | 522 | 12.3113 | 12.5000 | 12.0675 | 11.6015 | 90.4094 | 16.4577 | 16.8818 | 87.2% | 0.644 | [0.601, 0.685] | 494 |
| COVID (2020-03..06) | 17 | 1434.1471 | 686.0588 | 1439.9118 | 808.6820 | 2543.1687 | 2053.5285 | 1194.7167 | 5.9% | 0.235 | [0.096, 0.473] | 17 |
| 2020-07..12 (recovery gap) | 26 | 95.2212 | 70.2308 | 95.2885 | 85.5044 | 527.0318 | 123.5329 | 95.9178 | 11.5% | 0.500 | [0.314, 0.686] | 24 |
| 2021+ | 286 | 17.6853 | 14.7552 | 17.5096 | 23.3993 | 172.9757 | 28.9424 | 24.9185 | 79.4% | 0.592 | [0.533, 0.649] | 272 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history; strictly no-lookahead. Strongest naive = min(MAE Naive, MAE ExpandMean, trailing MAE).

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- Full window: MAE model=43.8551 vs naive=27.9135
- 2021+ slice: MAE model=17.6853 vs naive=14.7552
- Kill triggered: YES -> benchmark_only

### Vs Strongest Naive (REPORTED, MRI-R28b — non-binding)

Strongest naive = min(naive_prior, trailing3m/4w, expanding_mean).
- Full window: model MAE=43.8551 vs strongest_naive=27.9135 — margin=-15.9416 (LAGS)
- 2021+ slice: model MAE=17.6853 vs strongest_naive=14.7552 — margin=-2.9301 (LAGS)

---
## Notes and Deviations

1. **GASREGW absent**: PR-A not merged at backtest time. Gasoline leg dropped for CPI headline (absent_legs=['gasoline_mom']). All CPI headline predictions are made without gasoline feature.
2. **ADP absent**: PR-A not merged. ADP leg dropped for NFP (absent_legs=['adp_change']).
3. **Withheld taxes**: data starts 2023-02-14; YoY feature available only from ~2024-02. All NFP predictions before 2024-02 run without this leg.
4. **AWHMAN revision-optimistic**: uses latest-revised AWHMAN. Declared in provenance.
5. **Sticky/median/flex CPI and PPI**: absent before 2014-02/03; predictions before this date use only own-lags.
6. **NFP COVID rows**: 2020-03 through 2020-06 in a separate era row; not assigned to the 2010-2020 reference cell per PREREG_V1.md §6.1 (which ends that era at 2020-02).
7. **2020-07..12 recovery gap**: PREREG_V1.md §6.1 does not assign 2020-07..2020-12 to any era. These months are reported separately as '2020_recovery'. See AMENDMENTS section of PREREG_V1.md.
8. **NFP evaluation floor**: per PREREG_V1.md §4.1 'NFP evaluation window starts 2010'. Pre-2010 NFP predictions are EXCLUDED from the NFP full-window metrics ('full_2010_plus' row). Pre-2010 rows still contribute to training.
9. **Complete-case feature selection — CRITICAL DISCLOSURE**: the model uses complete-case training at each step. After the 2014 feature-onset boundary (sticky/median/flex CPI, PPI legs), pre-2014 training rows are dropped whenever post-2014 features are present in the prediction row. This means: (a) the effective training window for post-2014 predictions is NOT the full expanding window — rows before 2014 with missing features are excluded; (b) pooled residual quantiles mix two feature-set regimes (pre-2014 own-lags-only and post-2014 full-feature). Supplementary coverage computed over predictions with reference month >= 2015-01 (stable feature set) is reported in the era table above as '2015+' rows where data permits.
10. **Skew hit-rate is CONDITIONAL**: computed only over predictions where the model takes a directional stance vs naive (sign(model-naive) != 0). n_stance (Skew n column) may be substantially smaller than n_total (n column). Both are printed.
11. **Display-only**: all outputs carry display_only=True, authority=False. No signals or scores originate from this module.
12. **expanding_mean benchmark**: REPORTED (non-binding, MRI-R28b). Walk-forward expanding mean of target's first-print MoM history, computed at each step from prediction results up to (but not including) the current step. Slightly underestimates the true expanding mean (excludes burn-in records in training that precede the first prediction) but is strictly no-lookahead.

*Pre-registered spec frozen before any results were observed. No weight tuning after seeing results.*

---
## §12 Restatement (2026-07-10, MRI-R28/R29/R31)

Per MRI-R28 (strongest-naive law):
- Wave-10 verdicts STAND as frozen — they were honest under the pre-registered rule.
- The benchmark set now includes `expanding_mean` as a REPORTED (non-binding) column.
- All §12 new tracks use the STRONGEST naive (min of naive_prior, trailing3m, expanding_mean) as their kill benchmark.

Wave-10 verdict assessment vs strongest naive (see 'Vs Strongest Naive' sections above for exact numbers):
- **cpi_headline**: champion beat naive_prior in full and 2021+ windows. Expanding_mean may be slightly harder benchmark — see table above.
- **cpi_core**: champion was borderline vs naive_prior in 2021+. Vs strongest naive: beats in full window (margin=+0.0055) but lags in 2021+ (margin=-0.0089, LAGS). Honesty caveat for cpi_core: model lags expanding_mean in 2021+; verdicts stand. See 'Vs Strongest Naive' section above.
- **nfp**: champion beat naive in full (2010+) window; check 2021+ vs expanding_mean above.
- **claims**: see 2021+ vs strongest naive above.

Per MRI-R29 (bridge claim voided): see RESULTS_CPI_BRIDGE_V1.md for bridge restatement.
Per MRI-R31 (scoring upgrades): skew arm downgraded to DESCRIPTIVE until n>=24; §7 MAE arm unchanged.

---

## Addendum 2026-07-14 — corrected-feature re-run (post CPI June-2026 post-mortem)

**Defect (defect_notices.json DN-001):** `_last_n_mom_lags` applied `pct_change()` to
STICKCPIM157SFRBATL and FLEXCPIM157SFRBATL (already monthly %) and MEDCPIM158SFRBCLE
(already annualized monthly %), double-differentiating the rate series across the full
walk-forward history in BOTH training and serving (e.g. sticky_mom_lag1 = -36.68 instead
of +0.24 at the 2026-07-13 asof). Fixed 2026-07-14 via `_last_n_rate_lags` (raw values;
median de-annualized to monthly-equivalent).

**All numbers in the body above were measured under the defect and cannot support
promotion or kill decisions on their own.** The body is preserved unmodified as the
original record; this addendum is the corrected measurement.

### Corrected backtest results (2026-07-14 re-run) vs original (contaminated)

| Release | Era | Original MAE model | Corrected MAE model | MAE naive | Kill status |
|---------|-----|-------------------:|--------------------:|----------:|-------------|
| cpi_headline | Full | 0.1590 | 0.1570 | 0.2610 | active (unchanged) |
| cpi_headline | 2021+ | 0.1732 | 0.1616 | 0.2442 | active (unchanged) |
| cpi_core | Full | 0.0936 | 0.0925 | 0.0991 | active (unchanged) |
| cpi_core | 2021+ | 0.1386 | 0.1328 | 0.1297 | still lags 2021+ naive; kill requires BOTH windows — not triggered (unchanged) |
| nfp | Full (2010+) | 372.2171 | 372.22 | 459.84 | unaffected (no sticky/median/flex features) |
| claims | Full | 43.8551 | 43.86 | 27.91 | benchmark_only (unchanged; unaffected) |

Full corrected era tables: `results/backtest_v1_summary.json` / `results/backtest_v1_steps.json`
(regenerated 2026-07-14; pre-fix artifacts preserved in git history at the parent of the fix commit).

### Why the point estimates barely moved

The ridge z-scores every feature internally against the training distribution
(`engine/release_forecast.py` `_ridge_predict_with_components`). Training and serving shared
the same corrupted transform, so corrupted values were standardized against an equally
corrupted training distribution and their z-scores stayed in a normal range (corrupted
sticky z = -0.42 vs corrected z = -0.17 at the 2026-07-13 asof; flex shifts from z = -0.07
to z = +0.98). The corrupted features were RETAINED by the model — they were finite numerics,
NOT dropped by complete-case masking (which only drops NaN). Ridge shrinkage on three
low-signal columns left the net point nearly unchanged. Dry-run at asof 2026-07-13:
cpi_headline +0.0818 (defective) -> +0.0807 (corrected); cpi_core +0.2167 -> +0.2272.
The June-2026 cold print (actual -0.4 headline / -0.02 core) is therefore NOT rescued by
this fix — the champion's warm view was structural (lag-persistence features with no
forward-looking core instruments), not a units artifact.

### Scope note on the scoring-path PIT change

The same fix PR changes `scripts/build_release_forecast.py` `_compute_actual_from_print`
to use the prior month's INITIAL print (was: latest revision) when computing scored actuals,
matching the training convention. That change affects only forward-ledger scored rows.
The walk-forward backtest computes actuals from initial prints independently, so the tables
above reflect the feature correction only.
