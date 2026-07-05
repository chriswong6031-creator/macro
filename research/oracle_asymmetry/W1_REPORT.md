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
| prev_same_node_outcome | 350 | 0.5171 | 0.5004 |
| sigma20 | 350 | 0.0771 | 0.0520 |

## 3. LOEO Per-Era AUC Table

| Era | n_test | M0 AUC | M1 AUC | M2 AUC | Chosen |
|-----|--------|--------|--------|--------|--------|
| 1999-2014 | 180 | 0.5446 | 0.5077 | 0.5357 | 0.5357 |
| 2015-2019 | 60 | 0.3665 | 0.3925 | 0.5045 | 0.5045 |
| 2020-2022 | 63 | 0.3060 | 0.5067 | 0.4579 | 0.4579 |
| 2023-2026 | 47 | 0.5583 | 0.4417 | 0.4568 | 0.4568 |

**M0 mean AUC: 0.4439**
**M1 mean AUC: 0.4622**
**M2 mean AUC: 0.4887**
**Chosen model: M2 (mean AUC = 0.4887)**

## 4. Shuffled-Label Null Distribution

- n_permutations: 200
- null distribution mean AUC: 0.5037
- observed M2 mean AUC: 0.4887
- p-value (fraction null >= observed): **0.6800**

## 5. Pre-Registered Gate Verdicts

### G-A: FAIL
- FAIL — mean AUC=0.4887, null p=0.6800 — NO ONSET-QUALITY SIGNAL AT n=350 — printed null

### G-B: PASS
- PASS — M2=0.4887 >= M0=0.4439+0.03

### G-C: REPORTED
- REPORTED (not gating) — see G-C table below

### 5.1 G-C Lift Tables (reported, not gating)

**Keep-top-40% threshold = 0.5371**
Pooled: n_kept=141/350, good_rate=0.5106, base_rate=0.4857, lift=0.0249, Wilson 95% LB=0.4289

| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |
|-----|-------|--------|-----------|-----------|------|-----------|
| 1999-2014 | 180 | 81 | 0.5556 | 0.5278 | 0.0278 | 0.4473 |
| 2015-2019 | 60 | 31 | 0.5484 | 0.5667 | -0.0183 | 0.3777 |
| 2020-2022 | 63 | 13 | 0.3077 | 0.3492 | -0.0415 | 0.1268 |
| 2023-2026 | 47 | 16 | 0.375 | 0.4043 | -0.0293 | 0.1848 |

**Keep-top-60% threshold = 0.4292**
Pooled: n_kept=224/350, good_rate=0.4955, base_rate=0.4857, lift=0.0098, Wilson 95% LB=0.4307

| Era | n_era | n_kept | good_rate | base_rate | lift | Wilson LB |
|-----|-------|--------|-----------|-----------|------|-----------|
| 1999-2014 | 180 | 121 | 0.5455 | 0.5278 | 0.0177 | 0.4567 |
| 2015-2019 | 60 | 44 | 0.5682 | 0.5667 | 0.0015 | 0.4222 |
| 2020-2022 | 63 | 33 | 0.303 | 0.3492 | -0.0462 | 0.1738 |
| 2023-2026 | 47 | 26 | 0.3846 | 0.4043 | -0.0196 | 0.2243 |

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
| [0.00, 0.20) | 12 | 0.1637 | 0.4167 |
| [0.20, 0.40) | 95 | 0.3107 | 0.4842 |
| [0.40, 0.60) | 146 | 0.5028 | 0.4589 |
| [0.60, 0.80) | 92 | 0.6793 | 0.5543 |
| [0.80, 1.00) | 5 | 0.8173 | 0.2 |

## 7. Coefficients / Feature Importances (full-data fit)

> Sign commentary: positive coefficient → higher feature value → higher predicted probability of good outcome (CUSHIONED/CLEAN_LIFTOFF).
> Mechanism-implied signs are noted in brackets.

**M0 coefficients (accel_z_5d, vix_pctile):**
| Feature | Coef | Mechanism sign | Comment |
|---------|------|----------------|---------|
| accel_z_5d | -0.3008 | + | sustained acceleration favors conversion (REVERSED) |
| vix_pctile | -0.1950 | - | high VIX → macro headwind → fewer clean lifts (expected neg) (ok) |

**M2 feature importances (HGBC):**
| Feature | Importance | Mechanism sign | Comment |
|---------|-----------|----------------|---------|
| sigma20 | 0.1862 | - | higher vol at onset = noisier signal |
| stochrsi_kd_diff | 0.0839 | + | K crossing D = early signal |
| vix_pctile | 0.0647 | - | high VIX = macro headwind |
| tlt_ret_10d | 0.0503 | + | TLT rising bonds supporting risk |
| accel | 0.0457 | + | vel_1w - vel_3m momentum |
| flow_opp_out_20s | 0.0309 | + | opposite-complex outflows = forced rotation IN |
| spy_above_200d | 0.0262 | + | bull tape supports rotation |
| rs_pctile_252d | 0.0160 | + | relative strength vs peers |
| prev_same_node_outcome | 0.0102 | + | node momentum in rotation quality |
| persistence | 0.0069 | + | trend persistence |
| accel_z_5d | 0.0055 | + | sustained 5-day acceleration |
| active_in_episodes | 0.0002 | - | crowded = diminishing marginal returns |
| accel_z | 0.0000 | + | onset acceleration signal |
| washout_w | 0.0000 | + | washout = fuel for recovery |
| stochrsi_w_k | 0.0000 | - | lower stoch = more room to run |
| flow_same_out_20s | 0.0000 | - | same-complex outflows = sector-wide pressure |

## Appendix A: Secondary Labels (reported, never gate-bearing)

**rot21 good-set:** n=350, good_rate=0.2457

**False-start 5d:** n=350, false_start_rate=0.3086

