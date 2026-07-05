# OTA W1 — Onset-Quality Discriminator — Protocol Report

**Pre-registered spec:** research/oracle_asymmetry/W1_SPEC.md
**Seed:** 20260705
**Date:** 2026-07-05

> 'validated' is banned from this file. Every table carries n + base rate.
> Gate verdicts are pre-bound: results are printed as-is.

## 1. Population & Labels

- Population: ep_onset_in × pos63 × matured — **n = 350**
- Good-set (CUSHIONED | CLEAN_LIFTOFF): **n = 170**
- Base rate: **0.4857** (48.6%)

| Era | n | n_good | base_rate |
|-----|---|--------|-----------|

| 1999-2014 | 180 | 95 | 0.5278 |
| 2015-2019 | 60 | 34 | 0.5667 |
| 2020-2022 | 63 | 22 | 0.3492 |
| 2023-2026 | 47 | 19 | 0.4043 |

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
| prev_same_node_outcome | 350 | 0.9629 | 0.1894 |
| sigma20 | 350 | 0.0771 | 0.0520 |

## 3. LOEO Per-Era AUC Table

| Era | n_test | M0 AUC | M1 AUC | M2 AUC | Chosen |
|-----|--------|--------|--------|--------|--------|
| 1999-2014 | 180 | 0.5446 | 0.5233 | 0.5285 | 0.5285 |
| 2015-2019 | 60 | 0.3665 | 0.3857 | 0.4921 | 0.4921 |
| 2020-2022 | 63 | 0.3060 | 0.4756 | 0.4224 | 0.4224 |
| 2023-2026 | 47 | 0.5583 | 0.4173 | 0.4492 | 0.4492 |

**M0 mean AUC: 0.4439**
**M1 mean AUC: 0.4505**
**M2 mean AUC: 0.4731**
**Chosen model: M2 (mean AUC = 0.4731)**

## 4. Shuffled-Label Null Distribution

- n_permutations: 200
- null distribution mean AUC: 0.5048
- observed M2 mean AUC: 0.4731
- p-value (fraction null >= observed): **0.8350**

## 5. Pre-Registered Gate Verdicts

### G-A: FAIL
- FAIL — mean AUC=0.4731, null p=0.8350 — NO ONSET-QUALITY SIGNAL AT n=350 — printed null

### G-B: FAIL
- FAIL — M2=0.4731 < M0=0.4439+0.03 (delta=0.0292) — deliverable IS M0

### G-C: REPORTED
- REPORTED (not gating) — see G-C table below

### 5.1 G-C Lift Tables (reported, not gating)

**Keep-top-40% threshold = 0.5586**
Pooled: n_kept=140/350, good_rate=0.4571, base_rate=0.4857, lift=-0.0286, Wilson 95% LB=0.3769

| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |
|-----|-------|--------|-----------|-----------|------|-----------|
| 1999-2014 | 180 | 77 | 0.5195 | 0.5278 | -0.0083 | 0.4096 |
| 2015-2019 | 60 | 26 | 0.5385 | 0.5667 | -0.0282 | 0.3546 |
| 2020-2022 | 63 | 22 | 0.2273 | 0.3492 | -0.1219 | 0.1012 |
| 2023-2026 | 47 | 15 | 0.3333 | 0.4043 | -0.0709 | 0.1518 |

**Keep-top-60% threshold = 0.4713**
Pooled: n_kept=210/350, good_rate=0.5095, base_rate=0.4857, lift=0.0238, Wilson 95% LB=0.4423

| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |
|-----|-------|--------|-----------|-----------|------|-----------|
| 1999-2014 | 180 | 113 | 0.5664 | 0.5278 | 0.0386 | 0.4743 |
| 2015-2019 | 60 | 36 | 0.5833 | 0.5667 | 0.0167 | 0.422 |
| 2020-2022 | 63 | 36 | 0.3333 | 0.3492 | -0.0159 | 0.2021 |
| 2023-2026 | 47 | 25 | 0.4 | 0.4043 | -0.0043 | 0.234 |

## 6. Calibration (Reliability Table, 5 bins)

**M0**
| Bin | n | mean_pred | actual_rate |
|-----|---|-----------|-------------|
| [0.00, 0.20) | 1 | 0.1425 | 0.0 |
| [0.20, 0.40) | 16 | 0.3536 | 0.6875 |
| [0.40, 0.60) | 333 | 0.4771 | 0.4775 |
| [0.60, 0.80) | 0 | nan | nan |
| [0.80, 1.00) | 0 | nan | nan |

**M2**
| Bin | n | mean_pred | actual_rate |
|-----|---|-----------|-------------|
| [0.00, 0.20) | 13 | 0.1665 | 0.4615 |
| [0.20, 0.40) | 83 | 0.3069 | 0.5181 |
| [0.40, 0.60) | 150 | 0.5091 | 0.4733 |
| [0.60, 0.80) | 103 | 0.6731 | 0.4854 |
| [0.80, 1.00) | 1 | 0.8007 | 0.0 |

## 7. Coefficients / Feature Importances (full-data fit)

> Sign commentary: positive coefficient → higher feature value → higher predicted probability of good outcome (CUSHIONED/CLEAN_LIFTOFF).
> Mechanism-implied signs are noted in brackets.

**M0 coefficients (accel_z_5d, vix_pctile):**
| Feature | Coef | Mechanism sign | Comment |
|---------|------|----------------|---------|
| accel_z_5d | -0.3008 | + | sustained acceleration favors conversion (REVERSED) |
| vix_pctile | -0.1950 | - | high VIX → macro headwind → fewer clean lifts (expected neg) (ok) |

## Appendix A: Secondary Labels (reported, never gate-bearing)

**rot21 good-set:** n=350, good_rate=0.2457

**False-start 5d:** n=350, false_start_rate=0.3086

