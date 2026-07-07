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

Columns: MAE/RMSE vs model/naive/trailing3m/ar3; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.2251 | 0.2610 | 0.2618 | 0.2162 | 0.3042 | 0.3403 | 78.4% | 0.706 | [0.644, 0.761] | 228 |
| pre-2010 | 96 | 0.2650 | 0.3340 | 0.3408 | 0.2650 | 0.3670 | 0.4156 | 62.5% | 0.688 | [0.588, 0.773] | 93 |
| 2010–2020-02 | 122 | 0.1891 | 0.2081 | 0.2072 | 0.1713 | 0.2349 | 0.2643 | 87.7% | 0.770 | [0.651, 0.858] | 61 |
| COVID (2020-03..06) | 4 | 0.5294 | 0.5611 | 0.6513 | 0.4266 | 0.5462 | 0.5775 | 0.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1201 | 0.1477 | 0.2616 | 0.1021 | 0.1508 | 0.1597 | 100.0% | 0.667 | [0.300, 0.903] | 6 |
| 2021+ | 64 | 0.2246 | 0.2442 | 0.2233 | 0.2263 | 0.3068 | 0.3361 | 81.2% | 0.672 | [0.550, 0.774] | 64 |
| 2015+ (stable feature set, supplementary) | 136 | 0.2172 | 0.2303 | 0.2209 | 0.1968 | 0.2857 | 0.3035 | 82.3% | 0.682 | [0.577, 0.772] | 85 |

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- Full window: MAE model=0.2251 vs naive=0.2610
- 2021+ slice: MAE model=0.2246 vs naive=0.2442
- Kill triggered: NO -> active

---
## cpi_core

**Status:** active
**Kill rule:** NOT triggered. Model beats naive in at least one of: full/2010+ window, 2021+ slice.
**Total predictions:** 292

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.0924 | 0.0991 | 0.0991 | 0.0900 | 0.1294 | 0.1337 | 76.5% | 0.639 | [0.574, 0.698] | 227 |
| pre-2010 | 96 | 0.0821 | 0.0935 | 0.0866 | 0.0821 | 0.1020 | 0.1187 | 81.9% | 0.685 | [0.584, 0.771] | 92 |
| 2010–2020-02 | 122 | 0.0721 | 0.0735 | 0.0722 | 0.0621 | 0.0937 | 0.0959 | 82.8% | 0.623 | [0.497, 0.734] | 61 |
| COVID (2020-03..06) | 4 | 0.2206 | 0.3383 | 0.3323 | 0.2626 | 0.3136 | 0.3399 | 50.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1259 | 0.2225 | 0.2532 | 0.1334 | 0.1678 | 0.2361 | 50.0% | 0.833 | [0.436, 0.970] | 6 |
| 2021+ | 64 | 0.1355 | 0.1297 | 0.1401 | 0.1402 | 0.1879 | 0.1746 | 62.5% | 0.562 | [0.441, 0.677] | 64 |
| 2015+ (stable feature set, supplementary) | 136 | 0.1130 | 0.1185 | 0.1218 | 0.1078 | 0.1605 | 0.1593 | 66.2% | 0.624 | [0.517, 0.719] | 85 |

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- Full window: MAE model=0.0924 vs naive=0.0991
- 2021+ slice: MAE model=0.1355 vs naive=0.1297
- Kill triggered: NO -> active

---
## nfp

**Status:** active
**Kill rule:** NOT triggered. Model beats naive in at least one of: full/2010+ window, 2021+ slice.
**Total predictions:** 293
**Eval predictions (2010+):** 197

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

| Era | n | MAE Model | MAE Naive | MAE Trail3m | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|
| Full (2010+, per prereg) | 197 | 372.2171 | 459.8426 | 440.7563 | 635.1929 | 2161.1911 | 2191.4446 | 73.1% | 0.637 | [0.545, 0.720] | 113 |
| pre-2010 | 96 | 143.2956 | 153.9792 | 143.2222 | 140.2393 | 202.1443 | 217.4352 | 72.2% | 0.616 | [0.511, 0.712] | 86 |
| 2010–2020-02 | 122 | 160.4827 | 175.4918 | 148.6011 | 144.7864 | 259.5711 | 270.7632 | 82.0% | 0.646 | [0.525, 0.751] | 65 |
| COVID (2020-03..06) | 4 | 8592.7911 | 11669.0000 | 10420.5833 | 15473.8886 | 15012.2715 | 15144.9068 | 25.0% | 0.750 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 674.8891 | 815.8333 | 1951.8889 | 4523.0662 | 791.8835 | 1316.4738 | 16.7% | 0.333 | [0.097, 0.700] | 6 |
| 2021+ | 65 | 235.8056 | 270.8923 | 235.4769 | 283.6171 | 320.6112 | 377.5027 | 64.6% | 0.658 | [0.499, 0.788] | 38 |
| 2010–2020-02 (excl. COVID) | 122 | 160.4827 | 175.4918 | 148.6011 | 144.7864 | 259.5711 | 270.7632 | 82.0% | 0.646 | [0.525, 0.751] | 65 |
| 2015+ (stable feature set, supplementary) | 137 | 440.0936 | 566.8394 | 549.2190 | 832.5110 | 2581.6093 | 2618.0781 | 73.0% | 0.636 | [0.543, 0.720] | 110 |

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- 2010+ window (per prereg): MAE model=372.2171 vs naive=459.8426
- 2021+ slice: MAE model=235.8056 vs naive=270.8923
- Kill triggered: NO -> active

---
## claims

**Status:** benchmark_only
**Kill rule triggered:** model MAE >= naive MAE in full/2010+ window AND 2021+ slice.
**Total predictions:** 890

### Era-Split Metrics Table

Columns: MAE/RMSE vs model/naive/trailing3m/ar3; p10-p90 coverage; Skew HR (CONDITIONAL: of predictions where model takes stance vs naive, n_stance of n_total shown in last two columns); Wilson 95% CI.

| Era | n | MAE Model | MAE Naive | MAE Trail4w | MAE AR3 | RMSE Model | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|-----------|-----------|-------------|---------|------------|------------|-------------|---------|---------------|--------|
| Full | 890 | 43.8551 | 27.9135 | 43.7166 | 32.9923 | 285.3927 | 167.0822 | 80.8% | 0.612 | [0.579, 0.644] | 845 |
| pre-2010 | 30 | 20.1833 | 18.1667 | 18.9250 | 16.1466 | 27.1199 | 22.0658 | 83.3% | 0.552 | [0.375, 0.716] | 29 |
| 2010–2020-02 | 531 | 12.2622 | 12.4087 | 12.0080 | 11.5155 | 16.3839 | 16.7695 | 87.4% | 0.644 | [0.601, 0.685] | 503 |
| 2010–2019 (pre-COVID visibility) | 522 | 12.3113 | 12.5000 | 12.0675 | 11.6015 | 16.4577 | 16.8818 | 87.2% | 0.644 | [0.601, 0.685] | 494 |
| COVID (2020-03..06) | 17 | 1434.1471 | 686.0588 | 1439.9118 | 808.6820 | 2053.5285 | 1194.7167 | 5.9% | 0.235 | [0.096, 0.473] | 17 |
| 2020-07..12 (recovery gap) | 26 | 95.2212 | 70.2308 | 95.2885 | 85.5044 | 123.5329 | 95.9178 | 11.5% | 0.500 | [0.314, 0.686] | 24 |
| 2021+ | 286 | 17.6853 | 14.7552 | 17.5096 | 23.3993 | 28.9424 | 24.9185 | 79.4% | 0.592 | [0.533, 0.649] | 272 |

**Skew HR note:** CONDITIONAL hit-rate — only predictions where sign(model-naive) != 0 are counted. 'Skew n' = n_stance (predictions with a directional stance). n_total for the era is the 'n' column.

### Kill Rule Detail

- Full window: MAE model=43.8551 vs naive=27.9135
- 2021+ slice: MAE model=17.6853 vs naive=14.7552
- Kill triggered: YES -> benchmark_only

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

*Pre-registered spec frozen before any results were observed. No weight tuning after seeing results.*