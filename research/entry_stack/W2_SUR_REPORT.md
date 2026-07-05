# W2 Spring Reclaim (U&R) Phase-0 Report — Entry-Stack Expansion

**Status:** W2 study report only — no promotion decision (RUL-3).
**Date:** 2026-07-05
**Species:** S14 — Spring Reclaim (U&R), horizon_class=rotational, phase0.
**Family:** esx_ur_phase0 (budget=36).

> **SMOKE RUN** — reduced bootstrap (50 resamples). Results are indicative, not final.

## NC Yardstick (RUL-3 mandatory preamble)

Per masterplan §10 RUL-3: the null-competitors appear as the first table.
Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.
NC-2 proximity top-tercile deep stop5 coef = −0.0427 [−0.044, −0.031]* (significant).
The S-UR candidate 'beats NC-2' only if its coefficient retains CI-excluding-0
AFTER entry_quality-band fixed effects (DEFERRED: cycles.py pipeline required).

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |
|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | −0.0019 | [−0.016, +0.008] | no | 89.1% |
| deep | NC-1B (ticks=0) | +0.0001 | [−0.015, +0.007] | no | 90.8% |
| deep | NC-2 (prox top-tercile) | −0.0427 | [−0.044, −0.031] * | YES * | 33.4% |
| baskets | NC-1A (T1-only) | −0.0036 | [−0.011, +0.006] | no | 85.9% |
| baskets | NC-1B (ticks=0) | +0.0099 | [+0.002, +0.015] * | YES * | 90.9% |
| baskets | NC-2 (prox top-tercile) | −0.1012 | [−0.108, −0.096] * | YES * | 34.0% |

NC-2 proximity note: the NC-2 full marginality test (coefficient survives eq-band FE)
is DEFERRED. NC-2 full marginality test (coefficient survives eq-band FE after adding entry_quality band as additional fixed effects) is DEFERRED. The cycles.py pipeline (multi_cycle, mtf_state, early_state, regime_state) required per-fire is computationally infeasible at this scale. No offline cache of cand_price/dcl_price exists. NC-2 is DESCRIPTIVE-ONLY until deferred test runs.

## COILED-FIRE Recall Clause Note

COILED-FIRE recall is DEFERRED to this study PR (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated until the full cycles.py pipeline is run per-fire over all gate dates. This note serves as the operational DEFERRED stamp. U&R recall (share of gate fires with U&R event within +/-5 bars) is reported as a proxy.

## Species Bar Summary (mechanical, state met/not-met per clause)

Per masterplan §5: non-inferiority + superiority + n >= 150 + recall + independence.
NO promotion decision is made in this report (RUL-3).

| Clause | Value | Met? |
|---|---|---|
| n_standalone >= 150 | 17727 | YES |
| n_coiled >= 150 | 9473 | YES |
| n_gatefire >= 150 | 2212 | YES |
| Stop5 non-inferiority (CI_lo > -1pp) | 0.0213 | YES |
| Superiority CI-excl-0 on >=1 axis | ['stop5', 'cushion_rot'] | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60%) | 14.6% | YES |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

## Panel: deep

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS STAMP: absolute rates on surviving deep-panel names only. Comparisons within-era are directionally valid.

### Form: n21_k2_standalone

- Total events: 14075
- Deduped episodes: 14075
- Gradable: 13938
- N treatment: 13938 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0250 | [+0.021, +0.039] * * | 0.0610 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0162 | [+0.006, +0.021] * * | 0.0335 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0022 | [-0.020, +0.003] | 0.0026 | 0.2000 | 0.2286 | no |
| dead_money | -0.0007 | [-0.002, +0.000] | -0.0015 | 0.1600 | 0.2133 | no |
| cushion_rot | 0.0082 | [-0.008, +0.015] | 0.0266 | 0.6800 | 0.6800 | no |
| mae63 | -0.0049 | [-0.009, -0.003] * * | -0.0123 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0103 | [-0.028, -0.004] * * | -0.0380 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | 0.0103 | [+0.004, +0.028] * * | 0.0380 | 0.0000 | 0.0000 | YES |

### Form: n21_k2_coiled

- Total events: 7460
- Deduped episodes: 7460
- Gradable: 7379
- N treatment: 7379 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0523 | [+0.039, +0.064] * * | 0.1184 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0561 | [+0.041, +0.069] * * | 0.0878 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0070 | [-0.017, +0.014] | 0.0098 | 0.7200 | 0.7200 | no |
| dead_money | -0.0009 | [-0.002, -0.000] * * | -0.0021 | 0.0400 | 0.0457 | YES |
| cushion_rot | 0.0475 | [+0.026, +0.055] * * | 0.0620 | 0.0000 | 0.0000 | YES |
| mae63 | -0.0148 | [-0.019, -0.011] * * | -0.0281 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0174 | [-0.034, -0.010] * * | -0.0437 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | 0.0174 | [+0.010, +0.034] * * | 0.0437 | 0.0000 | 0.0000 | YES |

### Form: n21_k2_gatefire

- Total events: 1669
- Deduped episodes: 1669
- Gradable: 1639
- N treatment: 1639 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0227 | [-0.034, -0.007] * * | -0.0377 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.1259 | [+0.109, +0.162] * * | 0.2137 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0666 | [+0.030, +0.091] * * | 0.1457 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0012 | [-0.003, -0.000] * * | -0.0019 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.1325 | [+0.100, +0.153] * * | 0.2251 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0070 | [+0.001, +0.010] * * | 0.0106 | 0.0400 | 0.0400 | YES |
| zone_held_21 | 0.0422 | [+0.020, +0.052] * * | 0.0564 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | -0.0422 | [-0.052, -0.020] * * | -0.0564 | 0.0000 | 0.0000 | YES |

### Form: n21_k3_standalone

- Total events: 17727
- Deduped episodes: 17727
- Gradable: 17551
- N treatment: 17551 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0244 | [+0.021, +0.037] * * | 0.0562 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0197 | [+0.007, +0.023] * * | 0.0326 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0011 | [-0.016, +0.003] | 0.0033 | 0.2000 | 0.2286 | no |
| dead_money | -0.0005 | [-0.001, -0.000] * * | -0.0014 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.0113 | [-0.008, +0.014] | 0.0253 | 0.6400 | 0.6400 | no |
| mae63 | -0.0045 | [-0.007, -0.003] * * | -0.0119 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0076 | [-0.021, +0.000] | -0.0363 | 0.0800 | 0.1067 | no |
| stop_vol_21 | 0.0076 | [-0.000, +0.021] | 0.0363 | 0.0800 | 0.1067 | no |

### Form: n21_k3_coiled

- Total events: 9473
- Deduped episodes: 9473
- Gradable: 9370
- N treatment: 9370 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0467 | [+0.036, +0.057] * * | 0.1092 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0571 | [+0.038, +0.066] * * | 0.0858 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0093 | [-0.009, +0.013] | 0.0097 | 0.4800 | 0.4800 | no |
| dead_money | -0.0009 | [-0.002, -0.000] * * | -0.0022 | 0.0400 | 0.0457 | YES |
| cushion_rot | 0.0463 | [+0.025, +0.051] * * | 0.0607 | 0.0000 | 0.0000 | YES |
| mae63 | -0.0135 | [-0.017, -0.010] * * | -0.0277 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0127 | [-0.025, -0.004] * * | -0.0423 | 0.0400 | 0.0457 | YES |
| stop_vol_21 | 0.0127 | [+0.004, +0.025] * * | 0.0423 | 0.0400 | 0.0457 | YES |

### Form: n21_k3_gatefire

- Total events: 2212
- Deduped episodes: 2212
- Gradable: 2177
- N treatment: 2177 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0266 | [-0.033, -0.009] * * | -0.0395 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.1252 | [+0.102, +0.147] * * | 0.2045 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0766 | [+0.046, +0.100] * * | 0.1400 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0014 | [-0.003, -0.001] * * | -0.0021 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.1422 | [+0.123, +0.157] * * | 0.2227 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0068 | [+0.002, +0.010] * * | 0.0098 | 0.0000 | 0.0000 | YES |
| zone_held_21 | 0.0422 | [+0.021, +0.055] * * | 0.0560 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | -0.0422 | [-0.055, -0.021] * * | -0.0560 | 0.0000 | 0.0000 | YES |

### Form: n21_k5_standalone

- Total events: 22054
- Deduped episodes: 22054
- Gradable: 21827
- N treatment: 21827 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0261 | [+0.023, +0.036] * * | 0.0588 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0157 | [+0.007, +0.018] * * | 0.0234 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0012 | [-0.014, +0.004] | -0.0015 | 0.2800 | 0.3200 | no |
| dead_money | -0.0008 | [-0.001, -0.000] * * | -0.0015 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.0058 | [-0.010, +0.011] | 0.0143 | 0.9600 | 0.9600 | no |
| mae63 | -0.0055 | [-0.009, -0.004] * * | -0.0115 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0061 | [-0.017, -0.001] * * | -0.0320 | 0.0400 | 0.0533 | YES |
| stop_vol_21 | 0.0061 | [+0.001, +0.017] * * | 0.0320 | 0.0400 | 0.0533 | YES |

### Form: n21_k5_coiled

- Total events: 11935
- Deduped episodes: 11935
- Gradable: 11800
- N treatment: 11800 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0499 | [+0.042, +0.058] * * | 0.1119 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0434 | [+0.030, +0.049] * * | 0.0711 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0025 | [-0.010, +0.009] | -0.0002 | 0.9600 | 0.9600 | no |
| dead_money | -0.0012 | [-0.003, -0.001] * * | -0.0023 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.0347 | [+0.016, +0.041] * * | 0.0487 | 0.0000 | 0.0000 | YES |
| mae63 | -0.0155 | [-0.018, -0.012] * * | -0.0274 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0124 | [-0.024, -0.004] * * | -0.0392 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | 0.0124 | [+0.004, +0.024] * * | 0.0392 | 0.0000 | 0.0000 | YES |

### Form: n21_k5_gatefire

- Total events: 3034
- Deduped episodes: 3034
- Gradable: 2984
- N treatment: 2984 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0258 | [-0.034, -0.013] * * | -0.0348 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.1232 | [+0.106, +0.143] * * | 0.1899 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0867 | [+0.061, +0.108] * * | 0.1329 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0011 | [-0.002, -0.000] * * | -0.0018 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.1397 | [+0.119, +0.149] * * | 0.2079 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0051 | [+0.001, +0.007] * * | 0.0080 | 0.0400 | 0.0400 | YES |
| zone_held_21 | 0.0482 | [+0.032, +0.058] * * | 0.0607 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | -0.0482 | [-0.058, -0.032] * * | -0.0607 | 0.0000 | 0.0000 | YES |

### Form: n63_k2_standalone

- Total events: 6874
- Deduped episodes: 6874
- Gradable: 6825
- N treatment: 6825 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0325 | [+0.022, +0.050] * * | 0.0995 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0241 | [+0.008, +0.040] * * | 0.0565 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0100 | [-0.032, +0.003] | 0.0040 | 0.0800 | 0.1067 | no |
| dead_money | -0.0001 | [-0.002, +0.002] | -0.0015 | 0.6000 | 0.6400 | no |
| cushion_rot | 0.0101 | [-0.011, +0.014] | 0.0410 | 0.6400 | 0.6400 | no |
| mae63 | -0.0087 | [-0.013, -0.006] * * | -0.0198 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0123 | [-0.029, -0.005] * * | -0.0414 | 0.0400 | 0.0640 | YES |
| stop_vol_21 | 0.0123 | [+0.005, +0.029] * * | 0.0414 | 0.0400 | 0.0640 | YES |

### Form: n63_k2_coiled

- Total events: 4667
- Deduped episodes: 4667
- Gradable: 4628
- N treatment: 4628 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0586 | [+0.044, +0.080] * * | 0.1473 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0513 | [+0.024, +0.076] * * | 0.0978 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0076 | [-0.042, +0.010] | 0.0093 | 0.2800 | 0.2800 | no |
| dead_money | -0.0010 | [-0.002, -0.000] * * | -0.0024 | 0.0400 | 0.0457 | YES |
| cushion_rot | 0.0355 | [+0.004, +0.041] * * | 0.0644 | 0.0400 | 0.0457 | YES |
| mae63 | -0.0166 | [-0.022, -0.013] * * | -0.0311 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0176 | [-0.034, -0.008] * * | -0.0414 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | 0.0176 | [+0.008, +0.034] * * | 0.0414 | 0.0000 | 0.0000 | YES |

### Form: n63_k2_gatefire

- Total events: 1043
- Deduped episodes: 1043
- Gradable: 1027
- N treatment: 1027 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0068 | [-0.027, +0.008] | -0.0138 | 0.2800 | 0.2800 | no |
| rotational_liftoff | 0.1340 | [+0.109, +0.187] * * | 0.2473 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0672 | [+0.025, +0.115] * * | 0.1629 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0014 | [-0.003, +0.000] | -0.0026 | 0.2800 | 0.2800 | no |
| cushion_rot | 0.1161 | [+0.093, +0.154] * * | 0.2311 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0041 | [-0.003, +0.011] | 0.0049 | 0.2400 | 0.2800 | no |
| zone_held_21 | 0.0380 | [+0.018, +0.059] * * | 0.0506 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | -0.0380 | [-0.059, -0.018] * * | -0.0506 | 0.0000 | 0.0000 | YES |

### Form: n63_k3_standalone

- Total events: 8578
- Deduped episodes: 8578
- Gradable: 8512
- N treatment: 8512 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0294 | [+0.022, +0.043] * * | 0.0941 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0294 | [+0.011, +0.036] * * | 0.0555 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0107 | [-0.030, -0.003] * * | 0.0009 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0002 | [-0.002, +0.001] | -0.0016 | 0.4400 | 0.4400 | no |
| cushion_rot | 0.0168 | [-0.004, +0.020] | 0.0401 | 0.2000 | 0.2286 | no |
| mae63 | -0.0082 | [-0.011, -0.006] * * | -0.0194 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0090 | [-0.020, +0.002] | -0.0384 | 0.0800 | 0.1067 | no |
| stop_vol_21 | 0.0090 | [-0.002, +0.020] | 0.0384 | 0.0800 | 0.1067 | no |

### Form: n63_k3_coiled

- Total events: 5903
- Deduped episodes: 5903
- Gradable: 5852
- N treatment: 5852 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0508 | [+0.043, +0.065] * * | 0.1372 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0549 | [+0.029, +0.067] * * | 0.0947 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0089 | [-0.037, +0.001] | 0.0048 | 0.0800 | 0.0800 | YES |
| dead_money | -0.0011 | [-0.003, -0.000] * * | -0.0024 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.0389 | [+0.012, +0.041] * * | 0.0613 | 0.0000 | 0.0000 | YES |
| mae63 | -0.0157 | [-0.020, -0.013] * * | -0.0307 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0146 | [-0.027, -0.005] * * | -0.0396 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | 0.0146 | [+0.005, +0.027] * * | 0.0396 | 0.0000 | 0.0000 | YES |

### Form: n63_k3_gatefire

- Total events: 1400
- Deduped episodes: 1400
- Gradable: 1379
- N treatment: 1379 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0176 | [-0.029, -0.004] * * | -0.0188 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.1314 | [+0.103, +0.160] * * | 0.2270 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0693 | [+0.035, +0.108] * * | 0.1484 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0015 | [-0.003, -0.000] * * | -0.0026 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.1291 | [+0.114, +0.152] * * | 0.2229 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0042 | [-0.001, +0.009] | 0.0044 | 0.1600 | 0.1600 | no |
| zone_held_21 | 0.0428 | [+0.024, +0.062] * * | 0.0542 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | -0.0428 | [-0.062, -0.024] * * | -0.0542 | 0.0000 | 0.0000 | YES |

### Form: n63_k5_standalone

- Total events: 10582
- Deduped episodes: 10582
- Gradable: 10494
- N treatment: 10494 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0324 | [+0.026, +0.042] * * | 0.0976 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0193 | [+0.005, +0.024] * * | 0.0407 | 0.0400 | 0.0533 | YES |
| positional_liftoff | -0.0141 | [-0.029, -0.007] * * | -0.0090 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0005 | [-0.002, +0.001] | -0.0018 | 0.2400 | 0.2743 | no |
| cushion_rot | 0.0102 | [-0.007, +0.015] | 0.0256 | 0.6400 | 0.6400 | no |
| mae63 | -0.0092 | [-0.012, -0.007] * * | -0.0195 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0065 | [-0.016, -0.000] * * | -0.0366 | 0.0400 | 0.0533 | YES |
| stop_vol_21 | 0.0065 | [+0.000, +0.016] * * | 0.0366 | 0.0400 | 0.0533 | YES |

### Form: n63_k5_coiled

- Total events: 7354
- Deduped episodes: 7354
- Gradable: 7285
- N treatment: 7285 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0547 | [+0.045, +0.063] * * | 0.1427 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.0418 | [+0.021, +0.048] * * | 0.0767 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0102 | [-0.031, +0.001] | -0.0076 | 0.0800 | 0.0800 | YES |
| dead_money | -0.0014 | [-0.003, -0.001] * * | -0.0024 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.0288 | [+0.006, +0.034] * * | 0.0458 | 0.0000 | 0.0000 | YES |
| mae63 | -0.0170 | [-0.020, -0.014] * * | -0.0313 | 0.0000 | 0.0000 | YES |
| zone_held_21 | -0.0109 | [-0.022, -0.004] * * | -0.0393 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | 0.0109 | [+0.004, +0.022] * * | 0.0393 | 0.0000 | 0.0000 | YES |

### Form: n63_k5_gatefire

- Total events: 1904
- Deduped episodes: 1904
- Gradable: 1872
- N treatment: 1872 | N control: 37722

#### Effect Table (R1 FE, fast block bootstrap)

| Outcome | Coef | 95% CI | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0178 | [-0.031, -0.008] * * | -0.0123 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | 0.1264 | [+0.102, +0.151] * * | 0.2035 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0826 | [+0.054, +0.122] * * | 0.1345 | 0.0000 | 0.0000 | YES |
| dead_money | -0.0016 | [-0.003, -0.000] * * | -0.0026 | 0.0000 | 0.0000 | YES |
| cushion_rot | 0.1312 | [+0.113, +0.154] * * | 0.2058 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0034 | [-0.001, +0.007] | 0.0020 | 0.2000 | 0.2000 | no |
| zone_held_21 | 0.0544 | [+0.036, +0.069] * * | 0.0573 | 0.0000 | 0.0000 | YES |
| stop_vol_21 | -0.0544 | [-0.069, -0.036] * * | -0.0573 | 0.0000 | 0.0000 | YES |

---

*Generated by `scripts/research/run_w2_sur.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*Family: esx_ur_phase0 (budget=36). BH q<=0.10 within family.*
*Survivor bias: absolute rates on surviving names only; comparisons valid within constraint.*