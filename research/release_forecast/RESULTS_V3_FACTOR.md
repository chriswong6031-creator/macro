# Results V3 Factor — MRI Track M Challenger (PCA + Ridge)

**Run date:** 2026-07-08
**Spec:** research/release_forecast/PREREG_V3_FACTOR.md (frozen 2026-07-08)
**Model:** v3_factor — PCA top-3 via SVD + ridge(lambda=1.0) on [factors + naive anchor]
**Anti-mining:** backtest run once after prereg commit; no spec changes post-results.

Kill rule: challenger MAE >= naive MAE in BOTH full window AND 2021+ -> benchmark_only/no_shadow

---

## cpi_headline

**v3_factor total predictions:** 292
**champion total predictions:** 292
**Kill rule triggered:** False
**Verdict: SHADOW-ELIGIBLE**

### v3_factor Era-Split Metrics

| Era | n | MAE v3 | MAE Naive | MAE Trail3m | MAE AR3 | MAE ExpandMean* | RMSE v3 | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|--------|-----------|-------------|---------|-----------------|---------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.2231 | 0.261 | 0.2618 | 0.2162 | 0.2323 | 0.2986 | 0.3403 | 75.8% | 0.7692 | [0.69, 0.833] | 130 |
| pre-2010 | 96 | 0.2512 | 0.334 | 0.3408 | 0.265 | 0.2753 | 0.3508 | 0.4156 | 51.4% | 0.9111 | [0.793, 0.965] | 45 |
| 2010–2020-02 | 122 | 0.206 | 0.2081 | 0.2072 | 0.1713 | 0.1817 | 0.2625 | 0.2643 | 86.9% | 0.9091 | [0.623, 0.984] | 11 |
| COVID (2020-03..06) | 4 | 0.3755 | 0.5611 | 0.6513 | 0.4266 | 0.5459 | 0.3917 | 0.5775 | 50.0% | 0.75 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1467 | 0.1477 | 0.2616 | 0.1021 | 0.1654 | 0.1721 | 0.1597 | 100.0% | 0.6667 | [0.3, 0.903] | 6 |
| 2021+ | 64 | 0.2114 | 0.2442 | 0.2233 | 0.2263 | 0.2516 | 0.2802 | 0.3361 | 81.2% | 0.6562 | [0.534, 0.761] | 64 |
| 2015+ (stable feature set, suppl.) | 136 | 0.2075 | 0.2303 | 0.2209 | 0.1968 | 0.2107 | 0.2645 | 0.3035 | 85.3% | 0.6941 | [0.59, 0.782] | 85 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Strongest naive = min(MAE Naive, MAE Trail3m, MAE ExpandMean).

### Kill Rule Detail

- Full window: MAE v3=0.2231 vs naive=0.261
- 2021+ slice: MAE v3=0.2114 vs naive=0.2442
- Kill triggered: NO -> shadow-eligible

### Vs Strongest Naive (REPORTED, MRI-R28b)

- Full window: MAE v3=0.2231 vs strongest_naive=0.2323 — margin=0.0092 (BEATS)
- 2021+ slice: MAE v3=0.2114 vs strongest_naive=0.2233 — margin=0.0119 (BEATS)

### Head-to-Head: v3_factor vs Champion (v2 ridge)

| Era | n | MAE v3 | MAE Champion | MAE Naive | Cov v3 | Cov Champ | Skew HR v3 | Skew HR Champ |
|-----|---|--------|-------------|-----------|--------|-----------|------------|---------------|
| Full | 292 | 0.2231 | 0.159 | 0.261 | 75.8% | 71.3% | 0.7692 | 0.7982 |
| pre-2010 | 96 | 0.2512 | 0.1415 | 0.334 | 51.4% | 65.3% | 0.9111 | 0.8925 |
| 2010–2020-02 | 122 | 0.206 | 0.1659 | 0.2081 | 86.9% | 70.5% | 0.9091 | 0.8197 |
| COVID (2020-03..06) | 4 | 0.3755 | 0.2479 | 0.5611 | 50.0% | 50.0% | 0.75 | 1.0 |
| 2020-07..12 | 6 | 0.1467 | 0.088 | 0.1477 | 100.0% | 83.3% | 0.6667 | 0.8333 |
| 2021+ | 64 | 0.2114 | 0.1732 | 0.2442 | 81.2% | 79.7% | 0.6562 | 0.625 |

---

## cpi_core

**v3_factor total predictions:** 292
**champion total predictions:** 292
**Kill rule triggered:** False
**Verdict: SHADOW-ELIGIBLE**

### v3_factor Era-Split Metrics

| Era | n | MAE v3 | MAE Naive | MAE Trail3m | MAE AR3 | MAE ExpandMean* | RMSE v3 | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|--------|-----------|-------------|---------|-----------------|---------|------------|-------------|---------|---------------|--------|
| Full | 292 | 0.0937 | 0.0991 | 0.0991 | 0.09 | 0.0999 | 0.1286 | 0.1337 | 76.1% | 0.6279 | [0.542, 0.706] | 129 |
| pre-2010 | 96 | 0.0868 | 0.0935 | 0.0866 | 0.0821 | 0.078 | 0.1074 | 0.1187 | 80.6% | 0.6364 | [0.489, 0.762] | 44 |
| 2010–2020-02 | 122 | 0.0734 | 0.0735 | 0.0722 | 0.0621 | 0.064 | 0.0952 | 0.0959 | 80.3% | 0.6364 | [0.354, 0.848] | 11 |
| COVID (2020-03..06) | 4 | 0.2236 | 0.3383 | 0.3323 | 0.2626 | 0.2913 | 0.3145 | 0.3399 | 50.0% | 0.75 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 0.1165 | 0.2225 | 0.2532 | 0.1334 | 0.1681 | 0.1611 | 0.2361 | 83.3% | 1.0 | [0.61, 1.0] | 6 |
| 2021+ | 64 | 0.1326 | 0.1297 | 0.1401 | 0.1402 | 0.1823 | 0.1794 | 0.1746 | 64.1% | 0.5781 | [0.456, 0.691] | 64 |
| 2015+ (stable feature set, suppl.) | 136 | 0.1117 | 0.1185 | 0.1218 | 0.1078 | 0.1307 | 0.1558 | 0.1593 | 69.1% | 0.6235 | [0.517, 0.719] | 85 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Strongest naive = min(MAE Naive, MAE Trail3m, MAE ExpandMean).

### Kill Rule Detail

- Full window: MAE v3=0.0937 vs naive=0.0991
- 2021+ slice: MAE v3=0.1326 vs naive=0.1297
- Kill triggered: NO -> shadow-eligible

### Vs Strongest Naive (REPORTED, MRI-R28b)

- Full window: MAE v3=0.0937 vs strongest_naive=0.0991 — margin=0.0054 (BEATS)
- 2021+ slice: MAE v3=0.1326 vs strongest_naive=0.1297 — margin=-0.0029 (LAGS)

### Head-to-Head: v3_factor vs Champion (v2 ridge)

| Era | n | MAE v3 | MAE Champion | MAE Naive | Cov v3 | Cov Champ | Skew HR v3 | Skew HR Champ |
|-----|---|--------|-------------|-----------|--------|-----------|------------|---------------|
| Full | 292 | 0.0937 | 0.0936 | 0.0991 | 76.1% | 77.2% | 0.6279 | 0.63 |
| pre-2010 | 96 | 0.0868 | 0.0832 | 0.0935 | 80.6% | 81.9% | 0.6364 | 0.6848 |
| 2010–2020-02 | 122 | 0.0734 | 0.0721 | 0.0735 | 80.3% | 83.6% | 0.6364 | 0.6066 |
| COVID (2020-03..06) | 4 | 0.2236 | 0.2247 | 0.3383 | 50.0% | 50.0% | 0.75 | 0.75 |
| 2020-07..12 | 6 | 0.1165 | 0.1287 | 0.2225 | 83.3% | 50.0% | 1.0 | 0.8333 |
| 2021+ | 64 | 0.1326 | 0.1386 | 0.1297 | 64.1% | 64.1% | 0.5781 | 0.5469 |

---

## nfp

**v3_factor total predictions:** 293
**champion total predictions:** 293
**Kill rule triggered:** False
**Verdict: SHADOW-ELIGIBLE**

### v3_factor Era-Split Metrics

| Era | n | MAE v3 | MAE Naive | MAE Trail3m | MAE AR3 | MAE ExpandMean* | RMSE v3 | RMSE Naive | Cov p10-p90 | Skew HR | Wilson 95% CI | Skew n |
|-----|---|--------|-----------|-------------|---------|-----------------|---------|------------|-------------|---------|---------------|--------|
| Full (2010+, per prereg) | 197 | 527.8829 | 459.8426 | 440.7563 | 635.1929 | 363.6429 | 2320.6095 | 2191.4446 | 71.1% | 0.6789 | [0.586, 0.759] | 109 |
| pre-2010 | 96 | 143.1583 | 153.9792 | 143.2222 | 140.2393 | 195.1565 | 205.1859 | 217.4352 | 73.6% | 0.6444 | [0.498, 0.768] | 45 |
| 2010–2020-02 | 122 | 157.1471 | 175.4918 | 148.6011 | 144.7864 | 179.0605 | 256.7018 | 270.7632 | 82.0% | 0.7541 | [0.633, 0.845] | 61 |
| COVID (2020-03..06) | 4 | 11552.1559 | 11669.0 | 10420.5833 | 15473.8886 | 7096.6841 | 13898.7078 | 15144.9068 | 0.0% | 0.75 | [0.301, 0.954] | 4 |
| 2020-07..12 (recovery gap) | 6 | 3592.9109 | 815.8333 | 1951.8889 | 4523.0662 | 779.5035 | 6725.6897 | 1316.4738 | 0.0% | 0.3333 | [0.097, 0.7] | 6 |
| 2021+ | 65 | 262.3831 | 270.8923 | 235.4769 | 283.6171 | 257.3618 | 366.7939 | 377.5027 | 61.5% | 0.6053 | [0.447, 0.744] | 38 |
| 2015+ (stable feature set, suppl.) | 137 | 664.6784 | 566.8394 | 549.219 | 832.511 | 427.3257 | 2773.5125 | 2618.0781 | 69.3% | 0.6789 | [0.586, 0.759] | 109 |

\* MAE ExpandMean = REPORTED (non-binding, MRI-R28b). Strongest naive = min(MAE Naive, MAE Trail3m, MAE ExpandMean).

### Kill Rule Detail

- 2010+ window (per prereg): MAE v3=527.8829 vs naive=459.8426
- 2021+ slice: MAE v3=262.3831 vs naive=270.8923
- Kill triggered: NO -> shadow-eligible

### Vs Strongest Naive (REPORTED, MRI-R28b)

- 2010+ window (per prereg): MAE v3=527.8829 vs strongest_naive=363.6429 — margin=-164.2400 (LAGS)
- 2021+ slice: MAE v3=262.3831 vs strongest_naive=235.4769 — margin=-26.9062 (LAGS)

### Head-to-Head: v3_factor vs Champion (v2 ridge)

| Era | n | MAE v3 | MAE Champion | MAE Naive | Cov v3 | Cov Champ | Skew HR v3 | Skew HR Champ |
|-----|---|--------|-------------|-----------|--------|-----------|------------|---------------|
| Full (2010+, per prereg) | 197 | 527.8829 | 372.2171 | 459.8426 | 71.1% | 73.1% | 0.6789 | 0.6372 |
| pre-2010 | 96 | 143.1583 | 143.2956 | 153.9792 | 73.6% | 72.2% | 0.6444 | 0.6163 |
| 2010–2020-02 | 122 | 157.1471 | 160.4827 | 175.4918 | 82.0% | 82.0% | 0.7541 | 0.6462 |
| COVID (2020-03..06) | 4 | 11552.1559 | 8592.7911 | 11669.0 | 0.0% | 25.0% | 0.75 | 0.75 |
| 2020-07..12 | 6 | 3592.9109 | 674.8891 | 815.8333 | 0.0% | 16.7% | 0.3333 | 0.3333 |
| 2021+ | 65 | 262.3831 | 235.8056 | 270.8923 | 61.5% | 64.6% | 0.6053 | 0.6579 |

---

## Summary Verdicts

| Target | Full MAE v3 | Full MAE Naive | Full MAE Champ | 2021+ MAE v3 | 2021+ MAE Naive | 2021+ MAE Champ | Kill? | Verdict |
|--------|-------------|----------------|----------------|--------------|-----------------|-----------------|-------|---------|
| cpi_headline | 0.2231 | 0.261 | 0.159 | 0.2114 | 0.2442 | 0.1732 | NO | SHADOW-ELIGIBLE |
| cpi_core | 0.0937 | 0.0991 | 0.0936 | 0.1326 | 0.1297 | 0.1386 | NO | SHADOW-ELIGIBLE |
| nfp | 527.8829 | 459.8426 | 372.2171 | 262.3831 | 270.8923 | 235.8056 | NO | SHADOW-ELIGIBLE |

---

## Data Legs Absent / Caveats

- **ppi_fes_mom_lag1 (PPIFES):** ALFRED vintages start 2010-04; absent pre-2010. Dropped via complete-case.
- **dollar_mom (DTWEXBGS):** Daily series starts 2006-01-02; monthly avg MoM computable from 2006-02. Absent pre-2006. Dropped via complete-case.
- **shelter_nowcast:** Requires ZORI (2015-01+) with 12-month window; first usable ~2016-01. Absent pre-2016. Dropped via complete-case.
- **gasoline_mom (headline only):** GASREGW starts 1990-08; covered full CPI history. Not expected to be absent.
- **adp_change (NFP):** ADPMNUSNERSA starts 2010-01; adp_change computable from 2010-02. ADP 2022-08 methodology redesign = regime break noted.
- **claims_survey_week (NFP):** ICSA/CCSA vintages start 2009-05/2009-09. Absent pre-2009. Dropped via complete-case.
- **withheld_tax_yoy (NFP):** Data starts 2023-02-14; YoY computable ~2024-02. Effectively absent for all historical backtest. Dropped.
- **sticky/median/flex/ppi_fis:** ALFRED vintages start 2014-02/2014-03; absent pre-2014. Dropped. Pre-2014 v3 runs on own lags only (k≤3 features).

---

## §12 Restatement (2026-07-10, MRI-R28b)

expanding_mean benchmark added to era tables above (REPORTED, non-binding per MRI-R28b).
V3_factor verdicts stand as frozen. All §12 new tracks use the STRONGEST naive (min of naive_prior, trailing3m, expanding_mean) as kill benchmark.
See 'Vs Strongest Naive' subsections per target above for exact margins.
