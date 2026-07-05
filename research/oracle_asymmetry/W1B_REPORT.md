# OTA W1b — Onset-Quality Discriminator (reversion21 label) — Protocol Report

**Pre-registered spec:** research/oracle_asymmetry/W1_SPEC.md §Amendment log (W1b REGISTRATION)
**Label definition (reversion21):** absolute forward return at 21 sessions > 0 (next-bar fill per grading.fill_index; div-adjusted close; TIME-exit only; ABSOLUTE, not SPY-excess).
**Base rate (label=1 / n_labeled):** 0.6829 (68.3%)
**Seed:** 20260705
**Date:** 2026-07-05

> 'validated' is banned from this file. Every table carries n + base rate.
> Gate verdicts are pre-bound: results are printed as-is.
> Pre-stated expectation: LOW — W1's AUCs were sub-coin-flip on primary and secondary labels; W1b exists because the label postdated the wave, not because a different result is expected.
> **SMOKE RUN**: permutation null skipped (0 perms). AUCs are valid; null p-value is not computed.

## 1. Population & Labels

- Population: ep_onset_in × pos63 (matured, filtered to rows with ≥21 fwd bars) — **n = 350**
- label_reversion21=1 (abs fwd_ret_21 > 0): **n = 239**
- Base rate: **0.6829** (68.3%)

| Era | n | n_good | base_rate |
|-----|---|--------|-----------|

| 1999-2014 | 180 | 123 | 0.6833 |
| 2015-2019 | 60 | 41 | 0.6833 |
| 2020-2022 | 63 | 43 | 0.6825 |
| 2023-2026 | 47 | 32 | 0.6809 |

## 2. Feature Coverage (n = matured events with non-NaN)

| Feature | Non-NaN | Mean | Std |
|---------|---------|------|-----|
| accel_z | 350 | 2.0803 | 0.7862 |
| accel_z_5d | 350 | 1.3228 | 0.3584 |
| accel | 350 | 0.0553 | 0.0368 |
| rs_pctile_252d | 343 | 0.6091 | 0.2949 |
| persistence | 350 | 0.5004 | 0.0712 |
| washout_w | 350 | 0.4914 | 0.5006 |
| stochrsi_w_k | 350 | 33.0740 | 23.6452 |
| stochrsi_kd_diff | 350 | 4.0352 | 8.4345 |
| vix_pctile | 348 | 0.5072 | 0.3390 |
| spy_above_200d | 350 | 0.6086 | 0.4888 |
| tlt_ret_10d | 312 | 0.0004 | 0.0276 |
| flow_opp_out_20s | 350 | 1.0371 | 1.3984 |
| flow_same_out_20s | 350 | 0.0686 | 0.2531 |
| active_in_episodes | 350 | 2.2429 | 1.9627 |
| prev_same_node_outcome | 350 | 0.5171 | 0.5004 |
| sigma20 | 350 | 0.0771 | 0.0520 |

## 3. LOEO Per-Era AUC Table

| Era | n_test | M0 AUC | M1 AUC | M2 AUC | Chosen |
|-----|--------|--------|--------|--------|--------|
| 1999-2014 | 180 | 0.5066 | 0.4992 | 0.4862 | 0.4992 |
| 2015-2019 | 60 | 0.4878 | 0.4121 | 0.4377 | 0.4121 |
| 2020-2022 | 63 | 0.3686 | 0.5919 | 0.5186 | 0.5919 |
| 2023-2026 | 47 | 0.5208 | 0.4313 | 0.4896 | 0.4313 |

**M0 mean AUC: 0.4709**
**M1 mean AUC: 0.4836**
**M2 mean AUC: 0.483**
**Chosen model: M1 (mean AUC = 0.4836)**

## 4. Shuffled-Label Null Distribution

- n_permutations: 0
- null distribution mean AUC: nan
- observed M1 mean AUC: 0.4836
- p-value (fraction null >= observed): **nan**

## 5. Pre-Registered Gate Verdicts

### G-A: FAIL
- FAIL — mean AUC=0.4836, null p=nan — NO ONSET-QUALITY SIGNAL AT n=350 — printed null

### G-B: FAIL
- FAIL — M1=0.4836 < M0=0.4709+0.03 (delta=0.0127) — deliverable IS M0

### G-C: REPORTED
- REPORTED (not gating) — see G-C table below

### 5.1 G-C Lift Tables (reported, not gating)

**Keep-top-40% threshold = 0.7172**
Pooled: n_kept=164/350, good_rate=0.689, base_rate=0.6829, lift=0.0062, Wilson 95% LB=0.6145

| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |
|-----|-------|--------|-----------|-----------|------|-----------|
| 1999-2014 | 180 | 99 | 0.6869 | 0.6833 | 0.0035 | 0.59 |
| 2015-2019 | 60 | 27 | 0.6296 | 0.6833 | -0.0537 | 0.4423 |
| 2020-2022 | 63 | 27 | 0.7778 | 0.6825 | 0.0952 | 0.5924 |
| 2023-2026 | 47 | 11 | 0.6364 | 0.6809 | -0.0445 | 0.3538 |

**Keep-top-60% threshold = 0.6659**
Pooled: n_kept=221/350, good_rate=0.6878, base_rate=0.6829, lift=0.0049, Wilson 95% LB=0.6239

| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |
|-----|-------|--------|-----------|-----------|------|-----------|
| 1999-2014 | 180 | 132 | 0.6742 | 0.6833 | -0.0091 | 0.5903 |
| 2015-2019 | 60 | 41 | 0.6585 | 0.6833 | -0.0248 | 0.5055 |
| 2020-2022 | 63 | 32 | 0.7812 | 0.6825 | 0.0987 | 0.6124 |
| 2023-2026 | 47 | 16 | 0.6875 | 0.6809 | 0.0066 | 0.444 |

## 6. Calibration (Reliability Table, 5 bins)

**M0**
| Bin | n | mean_pred | actual_rate |
|-----|---|-----------|-------------|
| [0.00, 0.20) | 0 | nan | nan |
| [0.20, 0.40) | 1 | 0.3474 | 1.0 |
| [0.40, 0.60) | 22 | 0.5619 | 0.5909 |
| [0.60, 0.80) | 319 | 0.6936 | 0.6897 |
| [0.80, 1.00) | 8 | 0.8076 | 0.625 |

**M1**
| Bin | n | mean_pred | actual_rate |
|-----|---|-----------|-------------|
| [0.00, 0.20) | 0 | nan | nan |
| [0.20, 0.40) | 0 | nan | nan |
| [0.40, 0.60) | 45 | 0.5395 | 0.7111 |
| [0.60, 0.80) | 241 | 0.6968 | 0.6888 |
| [0.80, 1.00) | 64 | 0.8543 | 0.6406 |

## 7. Coefficients / Feature Importances (full-data fit)

> Sign commentary: positive coefficient → higher feature value → higher predicted probability of good outcome (CUSHIONED/CLEAN_LIFTOFF).
> Mechanism-implied signs are noted in brackets.

**M0 coefficients (accel_z_5d, vix_pctile):**
| Feature | Coef | Mechanism sign | Comment |
|---------|------|----------------|---------|
| accel_z_5d | -0.2538 | + | sustained acceleration favors conversion (REVERSED) |
| vix_pctile | 0.4835 | - | high VIX → macro headwind → fewer clean lifts (expected neg) (REVERSED) |

**M1 L2 logistic coefficients (all 16 features):**
| Feature | Coef | Mechanism sign | Comment |
|---------|------|----------------|---------|
| accel_z | -0.2747 | + | onset acceleration signal (REVERSED) |
| accel_z_5d | 0.0667 | + | sustained 5-day acceleration (ok) |
| accel | -0.0860 | + | vel_1w - vel_3m momentum (REVERSED) |
| rs_pctile_252d | -0.1462 | + | relative strength vs peers (REVERSED) |
| persistence | -0.0642 | + | trend persistence (REVERSED) |
| washout_w | -0.5662 | + | washout = fuel for recovery (REVERSED) |
| stochrsi_w_k | -0.0029 | - | lower stoch = more room to run (ok) |
| stochrsi_kd_diff | -0.0146 | + | K crossing D = early signal (REVERSED) |
| vix_pctile | 0.2065 | - | high VIX = macro headwind (REVERSED) |
| spy_above_200d | -0.6105 | + | bull tape supports rotation (REVERSED) |
| tlt_ret_10d | -0.0207 | + | TLT rising = bonds supporting risk, or flight-to-quality easing (REVERSED) |
| flow_opp_out_20s | 0.0108 | + | opposite-complex outflows = capital must rotate IN (ok) |
| flow_same_out_20s | -0.0246 | - | same-complex outflows = sector-wide pressure (ok) |
| active_in_episodes | -0.0749 | - | crowded = diminishing marginal returns (ok) |
| prev_same_node_outcome | 0.3075 | + | node momentum in rotation quality (ok) |
| sigma20 | -0.2124 | - | higher vol at onset = noisier signal (ok) |

## Appendix A: Secondary Labels (reported, never gate-bearing)

