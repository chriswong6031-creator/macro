# W2 Spring Reclaim (U&R) Phase-0 Report — Entry-Stack Expansion

**Status:** W2 study report only — no promotion decision (RUL-3).
**Date:** 2026-07-05
**Species:** S15 — Spring Reclaim (U&R), horizon_class=rotational, phase0.
**Species note:** S14 was assigned to 'Failed breakout' (PR #1457) before this branch. Spring Reclaim uses S15 (next free number).
**Family:** esx_ur_phase0 (budget=36).

> **SMOKE RUN** — reduced bootstrap (50 resamples). Results are indicative, not final.

## HEADLINE — Honest Verdict Under Corrected Sign Convention

**Sign convention:** stop5 is an ADVERSE outcome. A MORE POSITIVE coefficient means
MORE stops (WORSE). Non-inferiority = CI upper bound < +0.01.
Superiority on stop5 = CI upper bound < 0.0 (significantly fewer stops).

**Per-form primary results (deep panel, primary cell n21/k3):**

| Form | stop5 coef | 95% CI | Non-inferior (CI_hi<+0.01)? | Superior (CI_hi<0)? | zone_held_21 coef (context) |
|---|---|---|---|---|---|
| standalone (n21/k3/deep) | 0.0244 | CI_hi=0.0374 | NO | NO | -0.0076 |
| COILED-intersection (n21/k3/deep) | 0.0460 | CI_hi=0.0600 | NO | NO | -0.0113 |
| gatefire-proximity (n21/k3/deep) | -0.0266 | CI_hi=-0.0092 | YES | YES | 0.0422 |

**FINDING:** The standalone (+2.44pp) and COILED-intersection (+4.67pp) forms show
stop5 SIGNIFICANTLY WORSE than the incumbent gate baseline (CI entirely above 0).
Both forms FAIL non-inferiority and FAIL superiority.
Only the gatefire-proximity form shows stop5 improvement (approx −2.3pp, CI excludes 0),
but proximity confounding (NC-2 marginality) is the primary alternative explanation.
Nulls and kills are printed with equal care as wins.
**Adjudication belongs to the orchestrator, not this study.**

## NC Yardstick (RUL-3 mandatory preamble)

Per masterplan §10 RUL-3: the null-competitors appear as the first table.
Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.
NC-2 proximity top-tercile deep stop5 coef = −0.0427 [−0.044, −0.031]* (significant).
The S-UR candidate 'beats NC-2' only if its stop5 coefficient retains CI-excluding-0
AFTER entry_quality-band fixed effects (tested for gatefire form; see NC-2 Marginality below).

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |
|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | −0.0019 | [−0.016, +0.008] | no | 89.1% |
| deep | NC-1B (ticks=0) | +0.0001 | [−0.015, +0.007] | no | 90.8% |
| deep | NC-2 (prox top-tercile) | −0.0427 | [−0.044, −0.031] * | YES * | 33.4% |
| baskets | NC-1A (T1-only) | −0.0036 | [−0.011, +0.006] | no | 85.9% |
| baskets | NC-1B (ticks=0) | +0.0099 | [+0.002, +0.015] * | YES * | 90.9% |
| baskets | NC-2 (prox top-tercile) | −0.1012 | [−0.108, −0.096] * | YES * | 34.0% |

NC-2 proximity note: NC-2 full marginality test (coefficient survives eq-band FE after adding entry_quality band as additional fixed effects) is DEFERRED for standalone and COILED forms. For the gatefire-proximity form (the only form with stop5 improvement), the NC-2 band FE was applied using the 63-bar close-min PROXY pivot — see NC-2 Marginality section below. The true cand_price/dcl_price pivot (cycles.py:1705-1706) remains infeasible offline. NC-2 is DESCRIPTIVE-ONLY for standalone and COILED forms until deferred test runs.

## COILED-FIRE Recall Clause Note

COILED-FIRE recall is DEFERRED (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated until the full cycles.py pipeline is run per-fire over all gate dates. This note serves as the operational DEFERRED stamp. U&R recall (share of gate fires with U&R event within +/-5 bars) is reported as a proxy.

## Independence Clause

Primary-cell co-fire share (independence clause at +/-3 TRUE TRADING BARS):
- n primary-cell events near gate fire at ±3 bars: 805
- Co-fire share (primary cell): 4.5%
- Aggregate co-fire share (all cells): 5.7%
- Independence clause threshold: <= 60%
Note: the FORM uses +/-5 bars (per masterplan F2 frozen parameter).
The independence clause uses +/-3 TRUE TRADING BARS on the price index.

## Delisted Panel Status

DELISTED ARM: SKIPPED — panels=['deep','baskets'] requested; delisted panel not in run scope.

## BH Correction Scope

Family-wide BH: one BH pass pooling ALL cells x forms x outcomes of esx_ur_phase0.
Pool excludes stop_vol_21 (mechanical mirror of zone_held_21) and days_to_10 (collider).
BH q <= 0.1 threshold applied to all pooled cells.

## Per-Form Species Bar Summary (no cross-form cherry-picking)

Per masterplan §5: each form evaluated independently.
NO promotion decision made in this report (RUL-3).

### Species Bar: standalone (n21/k3/deep)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 17727 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=0.0244 CI_hi=0.0374 | NO |
| Stop5 superiority (CI_hi < 0) | CI_hi=0.0374 | NO |
| Superiority CI-excl-0 on >=1 constitution axis | ['dead_money'] | YES |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 4.5% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0076 CI=[-0.0206,0.0002] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; the vol-zone contrast (zone_held_21 vs stop5) informs whether a fixed −5% stop mismeasures high-vol washout entries. This metric feeds no clause in this study.

### Species Bar: COILED-intersection (n21/k3/deep)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 4392 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=0.0460 CI_hi=0.0600 | NO |
| Stop5 superiority (CI_hi < 0) | CI_hi=0.0600 | NO |
| Superiority CI-excl-0 on >=1 constitution axis | ['dead_money', 'cushion_rot'] | YES |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 4.5% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0113 CI=[-0.0283,-0.0017] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; the vol-zone contrast (zone_held_21 vs stop5) informs whether a fixed −5% stop mismeasures high-vol washout entries. This metric feeds no clause in this study.

### Species Bar: gatefire-proximity (n21/k3/deep)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 2212 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=-0.0266 CI_hi=-0.0092 | YES |
| Stop5 superiority (CI_hi < 0) | CI_hi=-0.0092 | YES |
| Superiority CI-excl-0 on >=1 constitution axis | ['stop5', 'dead_money', 'cushion_rot'] | YES |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 4.5% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=0.0422 CI=[0.0212,0.0545] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; the vol-zone contrast (zone_held_21 vs stop5) informs whether a fixed −5% stop mismeasures high-vol washout entries. This metric feeds no clause in this study.

## Panel: deep

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS STAMP: absolute rates on surviving deep-panel names only. Comparisons within-era are directionally valid.

### Form: n21_k2_standalone

- Total events: 14075
- Deduped episodes: 14075
- Gradable: 13938
- N treatment: 13938 | N control: 37722
- Recall (treatment / all): 27.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0250 | [+0.021, +0.039] * * | 0.0610 | 0.0000 | 0.0000 | YES | 0.270 |
| fwd_mdd_21 | -0.0042 | [-0.008, -0.004] * * | -0.0125 | 0.0000 | 0.0000 | YES | 0.270 |
| rotational_liftoff | 0.0162 | [+0.006, +0.021] * * | 0.0335 | 0.0000 | 0.0000 | YES | 0.270 |
| positional_liftoff | -0.0022 | [-0.020, +0.003] | 0.0026 | 0.2000 | 0.2230 | no | 0.270 |
| dead_money | -0.0007 | [-0.002, +0.000] | -0.0015 | 0.1600 | 0.1833 | no | 0.270 |
| cushion_rot | 0.0082 | [-0.008, +0.015] | 0.0266 | 0.6800 | 0.6854 | no | 0.270 |
| zone_held_21 | -0.0103 | [-0.028, -0.004] * * | -0.0380 | 0.0000 | 0.0000 | YES | 0.270 |
| stop_vol_21 | 0.0103 | [+0.004, +0.028] * * | 0.0380 | 0.0000 | — | no | 0.270 |
| days_to_10 | -1.3115 | [-2.004, -0.375] * * | -3.6246 | 0.0000 | — | no | 0.270 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 9216 | 18.4% | 28.1% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 1155 | 11.0% | 22.6% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 1358 | 8.8% | 27.0% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 1249 | 32.6% | 29.8% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 960 | 9.0% | 30.9% |

### Form: n21_k2_coiled

- Total events: 3441
- Deduped episodes: 3441
- Gradable: 3402
- N treatment: 3402 | N control: 37722
- Recall (treatment / all): 8.3%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0555 | [+0.042, +0.075] * * | 0.1480 | 0.0000 | 0.0000 | YES | 0.083 |
| fwd_mdd_21 | -0.0108 | [-0.016, -0.010] * * | -0.0266 | 0.0000 | 0.0000 | YES | 0.083 |
| rotational_liftoff | 0.0443 | [+0.022, +0.069] * * | 0.1047 | 0.0000 | 0.0000 | YES | 0.083 |
| positional_liftoff | -0.0104 | [-0.041, +0.004] | 0.0188 | 0.1200 | 0.1400 | no | 0.083 |
| dead_money | -0.0015 | [-0.003, -0.001] * * | -0.0023 | 0.0000 | 0.0000 | YES | 0.083 |
| cushion_rot | 0.0247 | [-0.005, +0.046] | 0.0693 | 0.1600 | 0.1833 | no | 0.083 |
| zone_held_21 | -0.0137 | [-0.037, -0.001] * * | -0.0311 | 0.0800 | 0.0960 | YES | 0.083 |
| stop_vol_21 | 0.0137 | [+0.001, +0.037] * * | 0.0311 | 0.0800 | — | no | 0.083 |
| days_to_10 | -4.6198 | [-4.846, -2.654] * * | -11.9594 | 0.0000 | — | no | 0.083 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 2366 | 27.4% | 33.6% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 139 | 10.8% | 37.4% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 250 | 10.4% | 39.6% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 395 | 42.5% | 39.0% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 252 | 8.3% | 35.7% |

### Form: n21_k2_gatefire

- Total events: 1669
- Deduped episodes: 1669
- Gradable: 1639
- N treatment: 1639 | N control: 37722
- Recall (treatment / all): 4.2%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0227 | [-0.034, -0.007] * * | -0.0377 | 0.0000 | 0.0000 | YES | 0.042 |
| fwd_mdd_21 | 0.0063 | [+0.002, +0.009] * * | 0.0087 | 0.0000 | 0.0000 | YES | 0.042 |
| rotational_liftoff | 0.1259 | [+0.109, +0.162] * * | 0.2137 | 0.0000 | 0.0000 | YES | 0.042 |
| positional_liftoff | 0.0666 | [+0.030, +0.091] * * | 0.1457 | 0.0000 | 0.0000 | YES | 0.042 |
| dead_money | -0.0012 | [-0.003, -0.000] * * | -0.0019 | 0.0000 | 0.0000 | YES | 0.042 |
| cushion_rot | 0.1325 | [+0.100, +0.153] * * | 0.2251 | 0.0000 | 0.0000 | YES | 0.042 |
| zone_held_21 | 0.0422 | [+0.020, +0.052] * * | 0.0564 | 0.0000 | 0.0000 | YES | 0.042 |
| stop_vol_21 | -0.0422 | [-0.052, -0.020] * * | -0.0564 | 0.0000 | — | no | 0.042 |
| days_to_10 | -4.8179 | [-6.793, -3.593] * * | -12.7259 | 0.0000 | — | no | 0.042 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 1128 | 8.9% | 48.2% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 127 | 3.1% | 37.8% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 159 | 3.1% | 35.2% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 92 | 7.6% | 51.1% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 133 | 6.0% | 41.3% |

### Form: n21_k3_standalone

- Total events: 17727
- Deduped episodes: 17727
- Gradable: 17551
- N treatment: 17551 | N control: 37722
- Recall (treatment / all): 31.8%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0244 | [+0.021, +0.037] * * | 0.0562 | 0.0000 | 0.0000 | YES | 0.318 |
| fwd_mdd_21 | -0.0039 | [-0.006, -0.003] * * | -0.0116 | 0.0000 | 0.0000 | YES | 0.318 |
| rotational_liftoff | 0.0197 | [+0.007, +0.023] * * | 0.0326 | 0.0000 | 0.0000 | YES | 0.318 |
| positional_liftoff | -0.0011 | [-0.016, +0.003] | 0.0033 | 0.2000 | 0.2230 | no | 0.318 |
| dead_money | -0.0005 | [-0.001, -0.000] * * | -0.0014 | 0.0000 | 0.0000 | YES | 0.318 |
| cushion_rot | 0.0113 | [-0.008, +0.014] | 0.0253 | 0.6400 | 0.6556 | no | 0.318 |
| zone_held_21 | -0.0076 | [-0.021, +0.000] | -0.0363 | 0.0800 | 0.0960 | YES | 0.318 |
| stop_vol_21 | 0.0076 | [-0.000, +0.021] | 0.0363 | 0.0800 | — | no | 0.318 |
| days_to_10 | -1.6912 | [-2.236, -0.782] * * | -3.6206 | 0.0000 | — | no | 0.318 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 11485 | 18.2% | 27.8% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 1523 | 10.7% | 21.9% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 1716 | 9.6% | 26.3% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 1570 | 29.4% | 31.0% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 1257 | 8.1% | 32.6% |

### Form: n21_k3_coiled

- Total events: 4392
- Deduped episodes: 4392
- Gradable: 4340
- N treatment: 4340 | N control: 37722
- Recall (treatment / all): 10.3%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0460 | [+0.036, +0.060] * * | 0.1365 | 0.0000 | 0.0000 | YES | 0.103 |
| fwd_mdd_21 | -0.0096 | [-0.012, -0.009] * * | -0.0251 | 0.0000 | 0.0000 | YES | 0.103 |
| rotational_liftoff | 0.0509 | [+0.027, +0.059] * * | 0.1033 | 0.0000 | 0.0000 | YES | 0.103 |
| positional_liftoff | -0.0099 | [-0.039, -0.002] * * | 0.0155 | 0.0400 | 0.0514 | YES | 0.103 |
| dead_money | -0.0013 | [-0.003, -0.001] * * | -0.0024 | 0.0000 | 0.0000 | YES | 0.103 |
| cushion_rot | 0.0297 | [+0.005, +0.030] * * | 0.0689 | 0.0400 | 0.0514 | YES | 0.103 |
| zone_held_21 | -0.0113 | [-0.028, -0.002] * * | -0.0309 | 0.0400 | 0.0514 | YES | 0.103 |
| stop_vol_21 | 0.0113 | [+0.002, +0.028] * * | 0.0309 | 0.0400 | — | no | 0.103 |
| days_to_10 | -4.9929 | [-5.659, -3.150] * * | -12.0058 | 0.0000 | — | no | 0.103 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 2979 | 26.9% | 33.5% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 227 | 13.2% | 33.5% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 319 | 10.3% | 37.6% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 486 | 38.5% | 39.9% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 329 | 6.4% | 40.1% |

### Form: n21_k3_gatefire

- Total events: 2212
- Deduped episodes: 2212
- Gradable: 2177
- N treatment: 2177 | N control: 37722
- Recall (treatment / all): 5.5%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0266 | [-0.033, -0.009] * * | -0.0395 | 0.0000 | 0.0000 | YES | 0.055 |
| fwd_mdd_21 | 0.0063 | [+0.003, +0.008] * * | 0.0085 | 0.0000 | 0.0000 | YES | 0.055 |
| rotational_liftoff | 0.1252 | [+0.102, +0.147] * * | 0.2045 | 0.0000 | 0.0000 | YES | 0.055 |
| positional_liftoff | 0.0766 | [+0.046, +0.100] * * | 0.1400 | 0.0000 | 0.0000 | YES | 0.055 |
| dead_money | -0.0014 | [-0.003, -0.001] * * | -0.0021 | 0.0000 | 0.0000 | YES | 0.055 |
| cushion_rot | 0.1422 | [+0.123, +0.157] * * | 0.2227 | 0.0000 | 0.0000 | YES | 0.055 |
| zone_held_21 | 0.0422 | [+0.021, +0.055] * * | 0.0560 | 0.0000 | 0.0000 | YES | 0.055 |
| stop_vol_21 | -0.0422 | [-0.055, -0.021] * * | -0.0560 | 0.0000 | — | no | 0.055 |
| days_to_10 | -5.8854 | [-8.264, -4.858] * * | -12.9611 | 0.0000 | — | no | 0.055 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 1466 | 8.9% | 46.9% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 190 | 3.7% | 35.8% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 204 | 2.9% | 35.3% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 139 | 6.5% | 51.8% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 178 | 3.9% | 44.9% |

#### NC-2 Marginality (ADDITION B — gatefire-proximity form only)

Reclaim events are definitionally near lows, so proximity confounding is the primary alternative explanation for the gatefire form's stop5 improvement. Proximity bands: 63-bar close-min pivot (PROXY for true cand_price/dcl_price).

- stop5 coef with NC-2 band FE: 0.0000 CI=[0.0000, 0.0000] CI-excl-0: no
- N treatment with computable proximity: 2177
- Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Band added as additional FE to stop5 R1 model. N computable = 2177/2177.

### Form: n21_k5_standalone

- Total events: 22054
- Deduped episodes: 22054
- Gradable: 21827
- N treatment: 21827 | N control: 37722
- Recall (treatment / all): 36.7%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0261 | [+0.023, +0.036] * * | 0.0588 | 0.0000 | 0.0000 | YES | 0.367 |
| fwd_mdd_21 | -0.0043 | [-0.007, -0.004] * * | -0.0112 | 0.0000 | 0.0000 | YES | 0.367 |
| rotational_liftoff | 0.0157 | [+0.007, +0.018] * * | 0.0234 | 0.0000 | 0.0000 | YES | 0.367 |
| positional_liftoff | -0.0012 | [-0.014, +0.004] | -0.0015 | 0.2800 | 0.3015 | no | 0.367 |
| dead_money | -0.0008 | [-0.001, -0.000] * * | -0.0015 | 0.0000 | 0.0000 | YES | 0.367 |
| cushion_rot | 0.0058 | [-0.010, +0.011] | 0.0143 | 0.9600 | 0.9600 | no | 0.367 |
| zone_held_21 | -0.0061 | [-0.017, -0.001] * * | -0.0320 | 0.0400 | 0.0514 | YES | 0.367 |
| stop_vol_21 | 0.0061 | [+0.001, +0.017] * * | 0.0320 | 0.0400 | — | no | 0.367 |
| days_to_10 | -1.4585 | [-1.980, -0.542] * * | -3.0350 | 0.0000 | — | no | 0.367 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 14220 | 18.7% | 27.1% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 1901 | 10.3% | 21.1% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 2170 | 9.5% | 25.8% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 1956 | 30.0% | 30.0% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 1580 | 8.4% | 30.9% |

### Form: n21_k5_coiled

- Total events: 5581
- Deduped episodes: 5581
- Gradable: 5514
- N treatment: 5514 | N control: 37722
- Recall (treatment / all): 12.8%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0504 | [+0.042, +0.063] * * | 0.1439 | 0.0000 | 0.0000 | YES | 0.128 |
| fwd_mdd_21 | -0.0102 | [-0.013, -0.010] * * | -0.0250 | 0.0000 | 0.0000 | YES | 0.128 |
| rotational_liftoff | 0.0377 | [+0.017, +0.040] * * | 0.0836 | 0.0000 | 0.0000 | YES | 0.128 |
| positional_liftoff | -0.0127 | [-0.034, -0.004] * * | -0.0001 | 0.0000 | 0.0000 | YES | 0.128 |
| dead_money | -0.0017 | [-0.003, -0.001] * * | -0.0024 | 0.0000 | 0.0000 | YES | 0.128 |
| cushion_rot | 0.0226 | [+0.002, +0.024] * * | 0.0526 | 0.0400 | 0.0514 | YES | 0.128 |
| zone_held_21 | -0.0130 | [-0.024, -0.006] * * | -0.0324 | 0.0000 | 0.0000 | YES | 0.128 |
| stop_vol_21 | 0.0130 | [+0.006, +0.024] * * | 0.0324 | 0.0000 | — | no | 0.128 |
| days_to_10 | -4.4405 | [-5.155, -2.959] * * | -10.7909 | 0.0000 | — | no | 0.128 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 3728 | 27.9% | 31.8% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 301 | 13.0% | 30.6% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 436 | 11.5% | 37.4% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 635 | 39.2% | 37.2% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 414 | 7.5% | 37.0% |

### Form: n21_k5_gatefire

- Total events: 3034
- Deduped episodes: 3034
- Gradable: 2984
- N treatment: 2984 | N control: 37722
- Recall (treatment / all): 7.3%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0258 | [-0.034, -0.013] * * | -0.0348 | 0.0000 | 0.0000 | YES | 0.073 |
| fwd_mdd_21 | 0.0062 | [+0.003, +0.007] * * | 0.0080 | 0.0000 | 0.0000 | YES | 0.073 |
| rotational_liftoff | 0.1232 | [+0.106, +0.143] * * | 0.1899 | 0.0000 | 0.0000 | YES | 0.073 |
| positional_liftoff | 0.0867 | [+0.061, +0.108] * * | 0.1329 | 0.0000 | 0.0000 | YES | 0.073 |
| dead_money | -0.0011 | [-0.002, -0.000] * * | -0.0018 | 0.0000 | 0.0000 | YES | 0.073 |
| cushion_rot | 0.1397 | [+0.119, +0.149] * * | 0.2079 | 0.0000 | 0.0000 | YES | 0.073 |
| zone_held_21 | 0.0482 | [+0.032, +0.058] * * | 0.0607 | 0.0000 | 0.0000 | YES | 0.073 |
| stop_vol_21 | -0.0482 | [-0.058, -0.032] * * | -0.0607 | 0.0000 | — | no | 0.073 |
| days_to_10 | -6.8400 | [-8.363, -5.925] * * | -12.4153 | 0.0000 | — | no | 0.073 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 2008 | 9.3% | 45.7% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 253 | 3.6% | 32.8% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 297 | 4.4% | 36.7% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 200 | 7.5% | 51.0% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 226 | 4.9% | 39.8% |

### Form: n63_k2_standalone

- Total events: 6874
- Deduped episodes: 6874
- Gradable: 6825
- N treatment: 6825 | N control: 37722
- Recall (treatment / all): 15.3%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0325 | [+0.022, +0.050] * * | 0.0995 | 0.0000 | 0.0000 | YES | 0.153 |
| fwd_mdd_21 | -0.0065 | [-0.010, -0.006] * * | -0.0202 | 0.0000 | 0.0000 | YES | 0.153 |
| rotational_liftoff | 0.0241 | [+0.008, +0.040] * * | 0.0565 | 0.0000 | 0.0000 | YES | 0.153 |
| positional_liftoff | -0.0100 | [-0.032, +0.003] | 0.0040 | 0.0800 | 0.0960 | YES | 0.153 |
| dead_money | -0.0001 | [-0.002, +0.002] | -0.0015 | 0.6000 | 0.6300 | no | 0.153 |
| cushion_rot | 0.0101 | [-0.011, +0.014] | 0.0410 | 0.6400 | 0.6556 | no | 0.153 |
| zone_held_21 | -0.0123 | [-0.029, -0.005] * * | -0.0414 | 0.0400 | 0.0514 | YES | 0.153 |
| stop_vol_21 | 0.0123 | [+0.005, +0.029] * * | 0.0414 | 0.0400 | — | no | 0.153 |
| days_to_10 | -2.3468 | [-3.322, -1.367] * * | -6.8702 | 0.0000 | — | no | 0.153 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 4664 | 21.8% | 29.2% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 450 | 12.9% | 25.8% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 598 | 10.9% | 31.4% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 642 | 40.6% | 34.3% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 471 | 8.3% | 36.5% |

### Form: n63_k2_coiled

- Total events: 2836
- Deduped episodes: 2836
- Gradable: 2812
- N treatment: 2812 | N control: 37722
- Recall (treatment / all): 6.9%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0613 | [+0.045, +0.085] * * | 0.1635 | 0.0000 | 0.0000 | YES | 0.069 |
| fwd_mdd_21 | -0.0103 | [-0.015, -0.009] * * | -0.0284 | 0.0000 | 0.0000 | YES | 0.069 |
| rotational_liftoff | 0.0333 | [+0.004, +0.062] * * | 0.1025 | 0.0000 | 0.0000 | YES | 0.069 |
| positional_liftoff | -0.0162 | [-0.054, +0.004] | 0.0150 | 0.0800 | 0.0960 | YES | 0.069 |
| dead_money | -0.0013 | [-0.003, +0.000] | -0.0022 | 0.0800 | 0.0960 | YES | 0.069 |
| cushion_rot | 0.0128 | [-0.019, +0.030] | 0.0651 | 0.6800 | 0.6854 | no | 0.069 |
| zone_held_21 | -0.0098 | [-0.032, +0.001] | -0.0314 | 0.1200 | 0.1400 | no | 0.069 |
| stop_vol_21 | 0.0098 | [-0.001, +0.032] | 0.0314 | 0.1200 | — | no | 0.069 |
| days_to_10 | -4.2059 | [-4.673, -2.327] * * | -12.3705 | 0.0000 | — | no | 0.069 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 1948 | 29.0% | 32.4% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 118 | 11.9% | 37.3% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 212 | 10.8% | 42.9% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 325 | 46.2% | 41.2% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 209 | 8.1% | 38.3% |

### Form: n63_k2_gatefire

- Total events: 1043
- Deduped episodes: 1043
- Gradable: 1027
- N treatment: 1027 | N control: 37722
- Recall (treatment / all): 2.7%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0068 | [-0.027, +0.008] | -0.0138 | 0.2800 | 0.3015 | no | 0.027 |
| fwd_mdd_21 | 0.0043 | [-0.000, +0.008] | 0.0050 | 0.0800 | 0.0960 | YES | 0.027 |
| rotational_liftoff | 0.1340 | [+0.109, +0.187] * * | 0.2473 | 0.0000 | 0.0000 | YES | 0.027 |
| positional_liftoff | 0.0672 | [+0.025, +0.115] * * | 0.1629 | 0.0000 | 0.0000 | YES | 0.027 |
| dead_money | -0.0014 | [-0.003, +0.000] | -0.0026 | 0.2800 | 0.3015 | no | 0.027 |
| cushion_rot | 0.1161 | [+0.093, +0.154] * * | 0.2311 | 0.0000 | 0.0000 | YES | 0.027 |
| zone_held_21 | 0.0380 | [+0.018, +0.059] * * | 0.0506 | 0.0000 | 0.0000 | YES | 0.027 |
| stop_vol_21 | -0.0380 | [-0.059, -0.018] * * | -0.0506 | 0.0000 | — | no | 0.027 |
| days_to_10 | -6.9174 | [-8.697, -4.563] * * | -16.3412 | 0.0000 | — | no | 0.027 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 743 | 10.8% | 50.1% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 58 | 8.6% | 46.6% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 90 | 4.4% | 40.0% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 50 | 8.0% | 64.0% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 86 | 8.1% | 44.2% |

### Form: n63_k3_standalone

- Total events: 8578
- Deduped episodes: 8578
- Gradable: 8512
- N treatment: 8512 | N control: 37722
- Recall (treatment / all): 18.4%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0294 | [+0.022, +0.043] * * | 0.0941 | 0.0000 | 0.0000 | YES | 0.184 |
| fwd_mdd_21 | -0.0060 | [-0.008, -0.005] * * | -0.0189 | 0.0000 | 0.0000 | YES | 0.184 |
| rotational_liftoff | 0.0294 | [+0.011, +0.036] * * | 0.0555 | 0.0000 | 0.0000 | YES | 0.184 |
| positional_liftoff | -0.0107 | [-0.030, -0.003] * * | 0.0009 | 0.0000 | 0.0000 | YES | 0.184 |
| dead_money | -0.0002 | [-0.002, +0.001] | -0.0016 | 0.4400 | 0.4659 | no | 0.184 |
| cushion_rot | 0.0168 | [-0.004, +0.020] | 0.0401 | 0.2000 | 0.2230 | no | 0.184 |
| zone_held_21 | -0.0090 | [-0.020, +0.002] | -0.0384 | 0.0800 | 0.0960 | YES | 0.184 |
| stop_vol_21 | 0.0090 | [-0.002, +0.020] | 0.0384 | 0.0800 | — | no | 0.184 |
| days_to_10 | -2.4661 | [-3.330, -1.655] * * | -6.9782 | 0.0000 | — | no | 0.184 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 5732 | 21.6% | 29.4% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 636 | 13.1% | 23.1% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 743 | 11.8% | 30.7% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 794 | 37.0% | 35.0% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 607 | 6.8% | 39.0% |

### Form: n63_k3_coiled

- Total events: 3626
- Deduped episodes: 3626
- Gradable: 3595
- N treatment: 3595 | N control: 37722
- Recall (treatment / all): 8.7%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0528 | [+0.042, +0.072] * * | 0.1489 | 0.0000 | 0.0000 | YES | 0.087 |
| fwd_mdd_21 | -0.0091 | [-0.012, -0.008] * * | -0.0265 | 0.0000 | 0.0000 | YES | 0.087 |
| rotational_liftoff | 0.0482 | [+0.019, +0.062] * * | 0.1053 | 0.0000 | 0.0000 | YES | 0.087 |
| positional_liftoff | -0.0158 | [-0.051, -0.002] * * | 0.0129 | 0.0000 | 0.0000 | YES | 0.087 |
| dead_money | -0.0012 | [-0.003, -0.000] * * | -0.0023 | 0.0000 | 0.0000 | YES | 0.087 |
| cushion_rot | 0.0249 | [-0.002, +0.027] | 0.0692 | 0.1200 | 0.1400 | no | 0.087 |
| zone_held_21 | -0.0111 | [-0.027, -0.001] * * | -0.0311 | 0.0400 | 0.0514 | YES | 0.087 |
| stop_vol_21 | 0.0111 | [+0.001, +0.027] * * | 0.0311 | 0.0400 | — | no | 0.087 |
| days_to_10 | -4.6098 | [-5.465, -2.805] * * | -12.5298 | 0.0000 | — | no | 0.087 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 2451 | 28.1% | 32.9% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 198 | 14.1% | 32.3% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 266 | 11.3% | 40.2% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 403 | 41.2% | 41.9% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 277 | 6.5% | 43.0% |

### Form: n63_k3_gatefire

- Total events: 1400
- Deduped episodes: 1400
- Gradable: 1379
- N treatment: 1379 | N control: 37722
- Recall (treatment / all): 3.5%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0176 | [-0.029, -0.004] * * | -0.0188 | 0.0000 | 0.0000 | YES | 0.035 |
| fwd_mdd_21 | 0.0047 | [+0.001, +0.008] * * | 0.0045 | 0.0000 | 0.0000 | YES | 0.035 |
| rotational_liftoff | 0.1314 | [+0.103, +0.160] * * | 0.2270 | 0.0000 | 0.0000 | YES | 0.035 |
| positional_liftoff | 0.0693 | [+0.035, +0.108] * * | 0.1484 | 0.0000 | 0.0000 | YES | 0.035 |
| dead_money | -0.0015 | [-0.003, -0.000] * * | -0.0026 | 0.0000 | 0.0000 | YES | 0.035 |
| cushion_rot | 0.1291 | [+0.114, +0.152] * * | 0.2229 | 0.0000 | 0.0000 | YES | 0.035 |
| zone_held_21 | 0.0428 | [+0.024, +0.062] * * | 0.0542 | 0.0000 | 0.0000 | YES | 0.035 |
| stop_vol_21 | -0.0428 | [-0.062, -0.024] * * | -0.0542 | 0.0000 | — | no | 0.035 |
| days_to_10 | -7.0722 | [-9.294, -5.545] * * | -15.1984 | 0.0000 | — | no | 0.035 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 974 | 10.6% | 48.1% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 104 | 7.7% | 37.5% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 119 | 3.4% | 40.3% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 75 | 5.3% | 62.7% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 107 | 5.6% | 47.7% |

### Form: n63_k5_standalone

- Total events: 10582
- Deduped episodes: 10582
- Gradable: 10494
- N treatment: 10494 | N control: 37722
- Recall (treatment / all): 21.8%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0324 | [+0.026, +0.042] * * | 0.0976 | 0.0000 | 0.0000 | YES | 0.218 |
| fwd_mdd_21 | -0.0063 | [-0.008, -0.006] * * | -0.0188 | 0.0000 | 0.0000 | YES | 0.218 |
| rotational_liftoff | 0.0193 | [+0.005, +0.024] * * | 0.0407 | 0.0400 | 0.0514 | YES | 0.218 |
| positional_liftoff | -0.0141 | [-0.029, -0.007] * * | -0.0090 | 0.0000 | 0.0000 | YES | 0.218 |
| dead_money | -0.0005 | [-0.002, +0.001] | -0.0018 | 0.2400 | 0.2653 | no | 0.218 |
| cushion_rot | 0.0102 | [-0.007, +0.015] | 0.0256 | 0.6400 | 0.6556 | no | 0.218 |
| zone_held_21 | -0.0065 | [-0.016, -0.000] * * | -0.0366 | 0.0400 | 0.0514 | YES | 0.218 |
| stop_vol_21 | 0.0065 | [+0.000, +0.016] * * | 0.0366 | 0.0400 | — | no | 0.218 |
| days_to_10 | -1.9339 | [-2.834, -1.177] * * | -6.0683 | 0.0000 | — | no | 0.218 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 6998 | 22.2% | 28.1% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 779 | 12.4% | 21.9% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 965 | 12.0% | 29.5% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 1003 | 37.7% | 32.3% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 749 | 7.1% | 36.9% |

### Form: n63_k5_coiled

- Total events: 4567
- Deduped episodes: 4567
- Gradable: 4527
- N treatment: 4527 | N control: 37722
- Recall (treatment / all): 10.7%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0578 | [+0.048, +0.072] * * | 0.1578 | 0.0000 | 0.0000 | YES | 0.107 |
| fwd_mdd_21 | -0.0104 | [-0.013, -0.009] * * | -0.0271 | 0.0000 | 0.0000 | YES | 0.107 |
| rotational_liftoff | 0.0348 | [+0.011, +0.041] * * | 0.0839 | 0.0000 | 0.0000 | YES | 0.107 |
| positional_liftoff | -0.0194 | [-0.048, -0.006] * * | -0.0047 | 0.0000 | 0.0000 | YES | 0.107 |
| dead_money | -0.0012 | [-0.003, -0.000] * * | -0.0024 | 0.0000 | 0.0000 | YES | 0.107 |
| cushion_rot | 0.0157 | [-0.009, +0.017] | 0.0501 | 0.4400 | 0.4659 | no | 0.107 |
| zone_held_21 | -0.0143 | [-0.028, -0.006] * * | -0.0350 | 0.0000 | 0.0000 | YES | 0.107 |
| stop_vol_21 | 0.0143 | [+0.006, +0.028] * * | 0.0350 | 0.0000 | — | no | 0.107 |
| days_to_10 | -4.3198 | [-5.186, -2.876] * * | -11.1094 | 0.0000 | — | no | 0.107 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 3032 | 29.2% | 31.1% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 254 | 13.4% | 30.3% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 367 | 12.0% | 38.7% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 530 | 42.6% | 38.3% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 344 | 7.6% | 39.8% |

### Form: n63_k5_gatefire

- Total events: 1904
- Deduped episodes: 1904
- Gradable: 1872
- N treatment: 1872 | N control: 37722
- Recall (treatment / all): 4.7%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0178 | [-0.031, -0.008] * * | -0.0123 | 0.0000 | 0.0000 | YES | 0.047 |
| fwd_mdd_21 | 0.0053 | [+0.002, +0.008] * * | 0.0037 | 0.0000 | 0.0000 | YES | 0.047 |
| rotational_liftoff | 0.1264 | [+0.102, +0.151] * * | 0.2035 | 0.0000 | 0.0000 | YES | 0.047 |
| positional_liftoff | 0.0826 | [+0.054, +0.122] * * | 0.1345 | 0.0000 | 0.0000 | YES | 0.047 |
| dead_money | -0.0016 | [-0.003, -0.000] * * | -0.0026 | 0.0000 | 0.0000 | YES | 0.047 |
| cushion_rot | 0.1312 | [+0.113, +0.154] * * | 0.2058 | 0.0000 | 0.0000 | YES | 0.047 |
| zone_held_21 | 0.0544 | [+0.036, +0.069] * * | 0.0573 | 0.0000 | 0.0000 | YES | 0.047 |
| stop_vol_21 | -0.0544 | [-0.069, -0.036] * * | -0.0573 | 0.0000 | — | no | 0.047 |
| days_to_10 | -7.9520 | [-9.683, -6.379] * * | -14.4552 | 0.0000 | — | no | 0.047 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 0 | 24280 | 13.1% | 26.5% |
| pre_2012 | 1 | 1313 | 11.4% | 46.2% |
| 2012-2015 | 0 | 3725 | 6.4% | 16.0% |
| 2012-2015 | 1 | 136 | 6.6% | 33.1% |
| 2016-2019 | 0 | 3715 | 7.5% | 18.6% |
| 2016-2019 | 1 | 180 | 5.6% | 40.6% |
| 2020-2022 | 0 | 2973 | 14.4% | 29.9% |
| 2020-2022 | 1 | 104 | 9.6% | 56.7% |
| 2023-2026 | 0 | 3029 | 9.8% | 25.7% |
| 2023-2026 | 1 | 139 | 5.0% | 40.3% |

---

## Holdability Appendix (mae63 — descriptive only, feeds NO verdict clause)

Per RUL-13, mae63 is removed from the primary verdict table. It appears here in a clearly-labeled holdability appendix only. All adjudication is based on the 21d horizon metrics above.

*mae63 was computed but is not reported in this appendix to avoid confusion.*
*If needed for the holdability lane (S-QL §3 F5), it will appear in a separate lane report.*

---

*Generated by `scripts/research/run_w2_sur.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*Family: esx_ur_phase0 (budget=36). BH q<=0.1 family-wide (pool excludes stop_vol_21, days_to_10).*
*Survivor bias: absolute rates on surviving names only; comparisons valid within constraint.*
*Sign convention: stop5 is adverse — positive coef = MORE stops (WORSE candidate). Non-inferiority = CI_hi < +0.01.*