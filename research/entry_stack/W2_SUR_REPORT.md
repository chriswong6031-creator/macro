# W2 Spring Reclaim (U&R) Phase-0 Report — Entry-Stack Expansion

**Status:** W2 study report only — no promotion decision (RUL-3).
**Date:** 2026-07-05
**Species:** S15 — Spring Reclaim (U&R), horizon_class=rotational, phase0.
**Species note:** S14 was assigned to 'Failed breakout' (PR #1457) before this branch. Spring Reclaim uses S15 (next free number).
**Family:** esx_ur_phase0 (budget=36).

## HEADLINE — Honest Verdict Under Corrected Sign Convention

**Sign convention:** stop5 is an ADVERSE outcome. A MORE POSITIVE coefficient means
MORE stops (WORSE). Non-inferiority = CI upper bound < +0.01.
Superiority on stop5 = CI upper bound < 0.0 (significantly fewer stops).

**Per-form primary results (deep panel, primary cell n21/k3) — ALL NUMBERS FROM THIS RUN:**

| Form | stop5 coef | 95% CI_hi | Non-inferior (CI_hi<+0.01)? | Superior (CI_hi<0)? | Independence (co-fire<=60%) | zone_held_21 coef (context) |
|---|---|---|---|---|---|---|
| standalone (n21/k3/deep) | 0.0244 | 0.0376 | NO | NO | PASS (4.5%) | -0.0076 |
| COILED-intersection (n21/k3/deep) | 0.0460 | 0.0625 | NO | NO | PASS (7.5%) | -0.0113 |
| gatefire-proximity (n21/k3/deep) | -0.0266 | -0.0096 | YES | NO (NC-2 nullified) | N/A-STRUCTURAL (36.4%) | 0.0422 |

**HONEST FINDING (AS MEASURED IN THIS RUN):**
- The standalone and COILED-intersection forms show stop5 SIGNIFICANTLY WORSE
  than the incumbent gate baseline (positive coef, CI entirely above 0).
  Both FAIL non-inferiority and FAIL superiority.
- The gatefire-proximity form: independence clause is N/A-STRUCTURAL (form defined by gate-fire proximity).
  The ±3-bar co-fire check uses a tighter radius than the form definition (±5 bars); events
  in the (3-bar, 5-bar] band escape the co-fire count, producing a spuriously low 36.4% share
  that would incorrectly 'pass' the ≤60% threshold. The form is NOT an independent trigger species.
- The gatefire NC-2 marginality result (band FE): CI=[-0.0251, 0.0045] includes 0 after proximity
  de-confounding — the stop5 improvement does NOT survive the confound test. Superiority clause
  is nullified — marked 'NO (NC-2 nullified)' in the table above.
- Nulls and kills printed with equal care as wins.
**Adjudication belongs to the orchestrator, not this study.**

## NC Yardstick (RUL-3 mandatory preamble)

**Source: W1-NC artifact** (`research/entry_stack/W1_NC_REPORT.md`).
Numbers below are parsed from that file at runtime — NOT hardcoded in this script.
Per masterplan §10 RUL-3: null-competitors appear as the first table.
Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.
The S-UR candidate 'beats NC-2' only if its stop5 coefficient retains CI-excluding-0
AFTER entry_quality-band fixed effects (tested for gatefire form; see NC-2 Marginality below).

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |
|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | -0.0019 | [-0.016, +0.008] | no | 89.1% |
| deep | NC-1B (ticks=0) | 0.0001 | [-0.015, +0.007] | no | 90.8% |
| deep | NC-2 (prox top-tercile) | -0.0427 | [-0.044, -0.031] * | YES * | 33.4% |
| baskets | NC-1A (T1-only) | -0.0036 | [-0.011, +0.006] | no | 85.9% |
| baskets | NC-1B (ticks=0) | 0.0099 | [+0.002, +0.015] * | YES * | 90.9% |
| baskets | NC-2 (prox top-tercile) | -0.1012 | [-0.108, -0.096] * | YES * | 34.0% |

NC-2 proximity note: NC-2 full marginality test (coefficient survives eq-band FE after adding entry_quality band as additional fixed effects) is DEFERRED for standalone and COILED forms. For the gatefire-proximity form (the only form with stop5 improvement), the NC-2 band FE was applied using the 63-bar close-min PROXY pivot — see NC-2 Marginality section below. The true cand_price/dcl_price pivot (cycles.py:1705-1706) remains infeasible offline. NC-2 is DESCRIPTIVE-ONLY for standalone and COILED forms until deferred test runs.

## COILED-FIRE Recall Clause Note

COILED-FIRE recall is DEFERRED (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated until the full cycles.py pipeline is run per-fire over all gate dates. This note serves as the operational DEFERRED stamp. U&R recall (share of gate fires with U&R event within +/-5 bars) is reported as a proxy.

## Independence Clause (Per-Form Co-Fire Shares)

Per-form co-fire shares at +/-3 TRUE TRADING BARS (primary cell n21/k3, deep panel):
Co-fire computed on each form's OWN event subset, not on the shared event set.

| Form | Co-fire share | n near | Independence clause (<=60%) |
|---|---|---|---|
| standalone | 4.5% | 805 | PASS |
| COILED-intersection | 7.5% | — | PASS |
| gatefire-proximity | 36.4% | 805 | N/A-STRUCTURAL |

**DESIGN NOTE — GATEFIRE FORM INDEPENDENCE IS N/A-STRUCTURAL:** The gatefire form selects U&R events WITHIN ±5 BARS of gate fires (form definition, F2). It is structurally gate-dependent: independence is not a meaningful clause for this form. The ±3-bar co-fire check uses a TIGHTER radius than the form radius (±5 bars). Events in the (3-bar, 5-bar] band are included in the form but NOT counted as co-fires at ±3 bars, producing a measured share of 36.4% that falls below the 60% threshold — but this is an artifact of the radius mismatch, not evidence of independence. The form requires a gate fire as a prerequisite by construction. Verdict: N/A-STRUCTURAL (independence clause does not apply).

Aggregate co-fire share (standalone forms, all cells): 4.4%
Independence clause threshold: <= 60%
Note: the FORM uses +/-5 bars (per masterplan F2 frozen parameter).
The independence clause uses +/-3 TRUE TRADING BARS on the price index.

## Delisted Panel Status

Loaded from /Users/chriswong/Documents/Cluade/Macro Dashboard/data/breadth/_closes_delisted.parquet (16221 rows).

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
| Stop5 non-inferiority (CI_hi < +0.01) | coef=0.0244 CI_hi=0.0376 | NO |
| Stop5 superiority (CI_hi < 0) | CI_hi=0.0376 | NO |
| Superiority CI-excl-0 on >=1 constitution axis | none | NO |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 4.5% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0076 CI=[-0.0189,-0.0005] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; the vol-zone contrast (zone_held_21 vs stop5) informs whether a fixed −5% stop mismeasures high-vol washout entries. This metric feeds no clause in this study.

### Species Bar: COILED-intersection (n21/k3/deep)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 4392 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=0.0460 CI_hi=0.0625 | NO |
| Stop5 superiority (CI_hi < 0) | CI_hi=0.0625 | NO |
| Superiority CI-excl-0 on >=1 constitution axis | ['dead_money', 'cushion_rot'] | YES |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 7.5% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0113 CI=[-0.0282,0.0001] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; the vol-zone contrast (zone_held_21 vs stop5) informs whether a fixed −5% stop mismeasures high-vol washout entries. This metric feeds no clause in this study.

### Species Bar: gatefire-proximity (n21/k3/deep)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 2212 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=-0.0266 CI_hi=-0.0096 | YES |
| Stop5 superiority (CI_hi < 0) | CI_hi=-0.0096 | NO (NC-2 nullified: CI includes 0 after proximity band FE) |
| Superiority CI-excl-0 on >=1 constitution axis | ['stop5', 'dead_money', 'cushion_rot'] | NO (NC-2 nullified: gatefire stop5 CI includes 0 after proximity de-confounding) |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-UR=5.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 36.4% | N/A (structurally gate-dependent: form defined by gate-fire proximity; independence clause does not apply) |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=0.0422 CI=[0.0230,0.0556] | — |

> **NC-2 NULLIFICATION NOTE (FINDING 2 FIX):** The NC-2 marginality test (line 391 below, band FE result) shows stop5 coef=-0.0173 CI=[-0.0251, +0.0045] — CI INCLUDES ZERO after proximity de-confounding. The stop5 improvement does not survive the confound test. Superiority clauses above are marked NULLIFIED accordingly. Under CLAUDE.md 'display-only until gauntleted', presenting superiority as YES when the study's own NC-2 result nullifies it would be an unearned escalation.

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
| stop5 | 0.0250 | [+0.020, +0.040] * * | 0.0610 | 0.0000 | 0.0000 | YES | 0.270 |
| fwd_mdd_21 | -0.0042 | [-0.007, -0.003] * * | -0.0125 | 0.0000 | 0.0000 | YES | 0.270 |
| rotational_liftoff | 0.0162 | [+0.008, +0.022] * * | 0.0335 | 0.0000 | 0.0000 | YES | 0.270 |
| positional_liftoff | -0.0022 | [-0.021, +0.003] | 0.0026 | 0.1300 | 0.2389 | no | 0.270 |
| dead_money | -0.0007 | [-0.002, +0.000] | -0.0015 | 0.1860 | 0.3255 | no | 0.270 |
| cushion_rot | 0.0082 | [-0.007, +0.014] | 0.0266 | 0.5240 | 0.6877 | no | 0.270 |
| zone_held_21 | -0.0103 | [-0.026, -0.004] * * | -0.0380 | 0.0000 | 0.0000 | YES | 0.270 |
| stop_vol_21 | 0.0103 | [+0.004, +0.026] * * | 0.0380 | 0.0000 | — | no | 0.270 |
| days_to_10 | -1.3115 | [-1.880, -0.350] * * | -3.6246 | 0.0040 | — | no | 0.270 |

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
| stop5 | 0.0555 | [+0.040, +0.077] * * | 0.1480 | 0.0000 | 0.0000 | YES | 0.083 |
| fwd_mdd_21 | -0.0108 | [-0.016, -0.009] * * | -0.0266 | 0.0000 | 0.0000 | YES | 0.083 |
| rotational_liftoff | 0.0443 | [+0.019, +0.060] * * | 0.1047 | 0.0020 | 0.0066 | YES | 0.083 |
| positional_liftoff | -0.0104 | [-0.045, +0.005] | 0.0188 | 0.1100 | 0.2086 | no | 0.083 |
| dead_money | -0.0015 | [-0.003, -0.000] * * | -0.0023 | 0.0300 | 0.0735 | YES | 0.083 |
| cushion_rot | 0.0247 | [-0.006, +0.041] | 0.0693 | 0.1480 | 0.2686 | no | 0.083 |
| zone_held_21 | -0.0137 | [-0.039, +0.000] | -0.0311 | 0.0520 | 0.1084 | no | 0.083 |
| stop_vol_21 | 0.0137 | [-0.000, +0.039] | 0.0311 | 0.0520 | — | no | 0.083 |
| days_to_10 | -4.6198 | [-4.839, -2.528] * * | -11.9594 | 0.0000 | — | no | 0.083 |

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
| stop5 | -0.0227 | [-0.033, -0.005] * * | -0.0377 | 0.0060 | 0.0168 | YES | 0.042 |
| fwd_mdd_21 | 0.0063 | [+0.002, +0.009] * * | 0.0087 | 0.0040 | 0.0120 | YES | 0.042 |
| rotational_liftoff | 0.1259 | [+0.103, +0.164] * * | 0.2137 | 0.0000 | 0.0000 | YES | 0.042 |
| positional_liftoff | 0.0666 | [+0.030, +0.093] * * | 0.1457 | 0.0000 | 0.0000 | YES | 0.042 |
| dead_money | -0.0012 | [-0.003, -0.000] * * | -0.0019 | 0.0340 | 0.0806 | YES | 0.042 |
| cushion_rot | 0.1325 | [+0.096, +0.155] * * | 0.2251 | 0.0000 | 0.0000 | YES | 0.042 |
| zone_held_21 | 0.0422 | [+0.019, +0.056] * * | 0.0564 | 0.0040 | 0.0120 | YES | 0.042 |
| stop_vol_21 | -0.0422 | [-0.056, -0.019] * * | -0.0564 | 0.0040 | — | no | 0.042 |
| days_to_10 | -4.8179 | [-7.137, -2.784] * * | -12.7259 | 0.0000 | — | no | 0.042 |

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
| stop5 | 0.0244 | [+0.020, +0.038] * * | 0.0562 | 0.0000 | 0.0000 | YES | 0.318 |
| fwd_mdd_21 | -0.0039 | [-0.006, -0.003] * * | -0.0116 | 0.0000 | 0.0000 | YES | 0.318 |
| rotational_liftoff | 0.0197 | [+0.009, +0.025] * * | 0.0326 | 0.0000 | 0.0000 | YES | 0.318 |
| positional_liftoff | -0.0011 | [-0.018, +0.003] | 0.0033 | 0.1880 | 0.3271 | no | 0.318 |
| dead_money | -0.0005 | [-0.002, +0.000] | -0.0014 | 0.1200 | 0.2262 | no | 0.318 |
| cushion_rot | 0.0113 | [-0.006, +0.017] | 0.0253 | 0.2940 | 0.4749 | no | 0.318 |
| zone_held_21 | -0.0076 | [-0.019, -0.001] * * | -0.0363 | 0.0340 | 0.0806 | YES | 0.318 |
| stop_vol_21 | 0.0076 | [+0.001, +0.019] * * | 0.0363 | 0.0340 | — | no | 0.318 |
| days_to_10 | -1.6912 | [-2.349, -0.822] * * | -3.6206 | 0.0020 | — | no | 0.318 |

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
| stop5 | 0.0460 | [+0.032, +0.063] * * | 0.1365 | 0.0000 | 0.0000 | YES | 0.103 |
| fwd_mdd_21 | -0.0096 | [-0.012, -0.008] * * | -0.0251 | 0.0000 | 0.0000 | YES | 0.103 |
| rotational_liftoff | 0.0509 | [+0.024, +0.059] * * | 0.1033 | 0.0000 | 0.0000 | YES | 0.103 |
| positional_liftoff | -0.0099 | [-0.043, +0.000] | 0.0155 | 0.0540 | 0.1118 | no | 0.103 |
| dead_money | -0.0013 | [-0.003, -0.000] * * | -0.0024 | 0.0180 | 0.0473 | YES | 0.103 |
| cushion_rot | 0.0297 | [+0.001, +0.038] * * | 0.0689 | 0.0440 | 0.0987 | YES | 0.103 |
| zone_held_21 | -0.0113 | [-0.028, +0.000] | -0.0309 | 0.0520 | 0.1084 | no | 0.103 |
| stop_vol_21 | 0.0113 | [-0.000, +0.028] | 0.0309 | 0.0520 | — | no | 0.103 |
| days_to_10 | -4.9929 | [-5.625, -3.251] * * | -12.0058 | 0.0000 | — | no | 0.103 |

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
| stop5 | -0.0266 | [-0.033, -0.010] * * | -0.0395 | 0.0000 | 0.0000 | YES | 0.055 |
| fwd_mdd_21 | 0.0063 | [+0.004, +0.008] * * | 0.0085 | 0.0000 | 0.0000 | YES | 0.055 |
| rotational_liftoff | 0.1252 | [+0.099, +0.157] * * | 0.2045 | 0.0000 | 0.0000 | YES | 0.055 |
| positional_liftoff | 0.0766 | [+0.044, +0.102] * * | 0.1400 | 0.0000 | 0.0000 | YES | 0.055 |
| dead_money | -0.0014 | [-0.003, -0.000] * * | -0.0021 | 0.0100 | 0.0275 | YES | 0.055 |
| cushion_rot | 0.1422 | [+0.119, +0.160] * * | 0.2227 | 0.0000 | 0.0000 | YES | 0.055 |
| zone_held_21 | 0.0422 | [+0.023, +0.056] * * | 0.0560 | 0.0000 | 0.0000 | YES | 0.055 |
| stop_vol_21 | -0.0422 | [-0.056, -0.023] * * | -0.0560 | 0.0000 | — | no | 0.055 |
| days_to_10 | -5.8854 | [-8.384, -4.367] * * | -12.9611 | 0.0000 | — | no | 0.055 |

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

- stop5 coef with NC-2 band FE: -0.0173 CI=[-0.0251, 0.0045] CI-excl-0: no
- N treatment with computable proximity: 2177
- Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 2177/2177; N control = 37722.

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
| stop5 | 0.0261 | [+0.022, +0.037] * * | 0.0588 | 0.0000 | 0.0000 | YES | 0.367 |
| fwd_mdd_21 | -0.0043 | [-0.007, -0.004] * * | -0.0112 | 0.0000 | 0.0000 | YES | 0.367 |
| rotational_liftoff | 0.0157 | [+0.005, +0.020] * * | 0.0234 | 0.0040 | 0.0120 | YES | 0.367 |
| positional_liftoff | -0.0012 | [-0.014, +0.004] | -0.0015 | 0.3080 | 0.4895 | no | 0.367 |
| dead_money | -0.0008 | [-0.002, -0.000] * * | -0.0015 | 0.0080 | 0.0222 | YES | 0.367 |
| cushion_rot | 0.0058 | [-0.010, +0.012] | 0.0143 | 0.7980 | 0.9537 | no | 0.367 |
| zone_held_21 | -0.0061 | [-0.017, -0.001] * * | -0.0320 | 0.0340 | 0.0806 | YES | 0.367 |
| stop_vol_21 | 0.0061 | [+0.001, +0.017] * * | 0.0320 | 0.0340 | — | no | 0.367 |
| days_to_10 | -1.4585 | [-1.971, -0.660] * * | -3.0350 | 0.0000 | — | no | 0.367 |

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
| stop5 | 0.0504 | [+0.039, +0.063] * * | 0.1439 | 0.0000 | 0.0000 | YES | 0.128 |
| fwd_mdd_21 | -0.0102 | [-0.013, -0.009] * * | -0.0250 | 0.0000 | 0.0000 | YES | 0.128 |
| rotational_liftoff | 0.0377 | [+0.015, +0.046] * * | 0.0836 | 0.0000 | 0.0000 | YES | 0.128 |
| positional_liftoff | -0.0127 | [-0.039, -0.002] * * | -0.0001 | 0.0260 | 0.0653 | YES | 0.128 |
| dead_money | -0.0017 | [-0.003, -0.001] * * | -0.0024 | 0.0040 | 0.0120 | YES | 0.128 |
| cushion_rot | 0.0226 | [-0.000, +0.028] | 0.0526 | 0.0580 | 0.1184 | no | 0.128 |
| zone_held_21 | -0.0130 | [-0.027, -0.001] * * | -0.0324 | 0.0360 | 0.0840 | YES | 0.128 |
| stop_vol_21 | 0.0130 | [+0.001, +0.027] * * | 0.0324 | 0.0360 | — | no | 0.128 |
| days_to_10 | -4.4405 | [-5.363, -2.957] * * | -10.7909 | 0.0000 | — | no | 0.128 |

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
| stop5 | -0.0258 | [-0.033, -0.013] * * | -0.0348 | 0.0000 | 0.0000 | YES | 0.073 |
| fwd_mdd_21 | 0.0062 | [+0.004, +0.008] * * | 0.0080 | 0.0000 | 0.0000 | YES | 0.073 |
| rotational_liftoff | 0.1232 | [+0.101, +0.152] * * | 0.1899 | 0.0000 | 0.0000 | YES | 0.073 |
| positional_liftoff | 0.0867 | [+0.056, +0.111] * * | 0.1329 | 0.0000 | 0.0000 | YES | 0.073 |
| dead_money | -0.0011 | [-0.002, +0.000] | -0.0018 | 0.0620 | 0.1248 | no | 0.073 |
| cushion_rot | 0.1397 | [+0.117, +0.152] * * | 0.2079 | 0.0000 | 0.0000 | YES | 0.073 |
| zone_held_21 | 0.0482 | [+0.033, +0.059] * * | 0.0607 | 0.0000 | 0.0000 | YES | 0.073 |
| stop_vol_21 | -0.0482 | [-0.059, -0.033] * * | -0.0607 | 0.0000 | — | no | 0.073 |
| days_to_10 | -6.8400 | [-8.517, -5.382] * * | -12.4153 | 0.0000 | — | no | 0.073 |

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
| stop5 | 0.0325 | [+0.022, +0.051] * * | 0.0995 | 0.0000 | 0.0000 | YES | 0.153 |
| fwd_mdd_21 | -0.0065 | [-0.010, -0.005] * * | -0.0202 | 0.0000 | 0.0000 | YES | 0.153 |
| rotational_liftoff | 0.0241 | [+0.007, +0.036] * * | 0.0565 | 0.0040 | 0.0120 | YES | 0.153 |
| positional_liftoff | -0.0100 | [-0.034, +0.003] | 0.0040 | 0.1040 | 0.1998 | no | 0.153 |
| dead_money | -0.0001 | [-0.002, +0.002] | -0.0015 | 0.7980 | 0.9537 | no | 0.153 |
| cushion_rot | 0.0101 | [-0.012, +0.016] | 0.0410 | 0.6640 | 0.8307 | no | 0.153 |
| zone_held_21 | -0.0123 | [-0.029, -0.005] * * | -0.0414 | 0.0160 | 0.0428 | YES | 0.153 |
| stop_vol_21 | 0.0123 | [+0.005, +0.029] * * | 0.0414 | 0.0160 | — | no | 0.153 |
| days_to_10 | -2.3468 | [-3.349, -1.169] * * | -6.8702 | 0.0000 | — | no | 0.153 |

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
| stop5 | 0.0613 | [+0.044, +0.085] * * | 0.1635 | 0.0000 | 0.0000 | YES | 0.069 |
| fwd_mdd_21 | -0.0103 | [-0.016, -0.008] * * | -0.0284 | 0.0000 | 0.0000 | YES | 0.069 |
| rotational_liftoff | 0.0333 | [+0.001, +0.050] * * | 0.1025 | 0.0400 | 0.0912 | YES | 0.069 |
| positional_liftoff | -0.0162 | [-0.059, +0.003] | 0.0150 | 0.0700 | 0.1400 | no | 0.069 |
| dead_money | -0.0013 | [-0.003, +0.000] | -0.0022 | 0.1320 | 0.2410 | no | 0.069 |
| cushion_rot | 0.0128 | [-0.021, +0.026] | 0.0651 | 0.8580 | 1.0000 | no | 0.069 |
| zone_held_21 | -0.0098 | [-0.039, +0.006] | -0.0314 | 0.1620 | 0.2904 | no | 0.069 |
| stop_vol_21 | 0.0098 | [-0.006, +0.039] | 0.0314 | 0.1620 | — | no | 0.069 |
| days_to_10 | -4.2059 | [-4.874, -1.957] * * | -12.3705 | 0.0000 | — | no | 0.069 |

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
| stop5 | -0.0068 | [-0.025, +0.007] | -0.0138 | 0.2740 | 0.4451 | no | 0.027 |
| fwd_mdd_21 | 0.0043 | [-0.000, +0.009] | 0.0050 | 0.0600 | 0.1217 | no | 0.027 |
| rotational_liftoff | 0.1340 | [+0.099, +0.187] * * | 0.2473 | 0.0000 | 0.0000 | YES | 0.027 |
| positional_liftoff | 0.0672 | [+0.018, +0.106] * * | 0.1629 | 0.0040 | 0.0120 | YES | 0.027 |
| dead_money | -0.0014 | [-0.002, +0.000] | -0.0026 | 0.2400 | 0.3986 | no | 0.027 |
| cushion_rot | 0.1161 | [+0.083, +0.147] * * | 0.2311 | 0.0000 | 0.0000 | YES | 0.027 |
| zone_held_21 | 0.0380 | [+0.016, +0.057] * * | 0.0506 | 0.0000 | 0.0000 | YES | 0.027 |
| stop_vol_21 | -0.0380 | [-0.057, -0.016] * * | -0.0506 | 0.0000 | — | no | 0.027 |
| days_to_10 | -6.9174 | [-9.093, -3.687] * * | -16.3412 | 0.0000 | — | no | 0.027 |

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
| stop5 | 0.0294 | [+0.022, +0.045] * * | 0.0941 | 0.0000 | 0.0000 | YES | 0.184 |
| fwd_mdd_21 | -0.0060 | [-0.008, -0.005] * * | -0.0189 | 0.0000 | 0.0000 | YES | 0.184 |
| rotational_liftoff | 0.0294 | [+0.010, +0.040] * * | 0.0555 | 0.0000 | 0.0000 | YES | 0.184 |
| positional_liftoff | -0.0107 | [-0.032, -0.000] * * | 0.0009 | 0.0480 | 0.1030 | no | 0.184 |
| dead_money | -0.0002 | [-0.002, +0.001] | -0.0016 | 0.5760 | 0.7395 | no | 0.184 |
| cushion_rot | 0.0168 | [-0.007, +0.025] | 0.0401 | 0.2060 | 0.3542 | no | 0.184 |
| zone_held_21 | -0.0090 | [-0.020, -0.001] * * | -0.0384 | 0.0300 | 0.0735 | YES | 0.184 |
| stop_vol_21 | 0.0090 | [+0.001, +0.020] * * | 0.0384 | 0.0300 | — | no | 0.184 |
| days_to_10 | -2.4661 | [-3.334, -1.355] * * | -6.9782 | 0.0000 | — | no | 0.184 |

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
| stop5 | 0.0528 | [+0.039, +0.071] * * | 0.1489 | 0.0000 | 0.0000 | YES | 0.087 |
| fwd_mdd_21 | -0.0091 | [-0.012, -0.007] * * | -0.0265 | 0.0000 | 0.0000 | YES | 0.087 |
| rotational_liftoff | 0.0482 | [+0.018, +0.060] * * | 0.1053 | 0.0020 | 0.0066 | YES | 0.087 |
| positional_liftoff | -0.0158 | [-0.053, -0.000] * * | 0.0129 | 0.0460 | 0.1025 | no | 0.087 |
| dead_money | -0.0012 | [-0.003, +0.000] | -0.0023 | 0.0800 | 0.1579 | no | 0.087 |
| cushion_rot | 0.0249 | [-0.004, +0.034] | 0.0692 | 0.1220 | 0.2285 | no | 0.087 |
| zone_held_21 | -0.0111 | [-0.030, +0.003] | -0.0311 | 0.1060 | 0.2024 | no | 0.087 |
| stop_vol_21 | 0.0111 | [-0.003, +0.030] | 0.0311 | 0.1060 | — | no | 0.087 |
| days_to_10 | -4.6098 | [-5.428, -2.719] * * | -12.5298 | 0.0000 | — | no | 0.087 |

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
| stop5 | -0.0176 | [-0.030, -0.003] * * | -0.0188 | 0.0180 | 0.0473 | YES | 0.035 |
| fwd_mdd_21 | 0.0047 | [+0.001, +0.008] * * | 0.0045 | 0.0060 | 0.0168 | YES | 0.035 |
| rotational_liftoff | 0.1314 | [+0.098, +0.171] * * | 0.2270 | 0.0000 | 0.0000 | YES | 0.035 |
| positional_liftoff | 0.0693 | [+0.029, +0.104] * * | 0.1484 | 0.0000 | 0.0000 | YES | 0.035 |
| dead_money | -0.0015 | [-0.003, -0.000] * * | -0.0026 | 0.0400 | 0.0912 | YES | 0.035 |
| cushion_rot | 0.1291 | [+0.108, +0.154] * * | 0.2229 | 0.0000 | 0.0000 | YES | 0.035 |
| zone_held_21 | 0.0428 | [+0.024, +0.060] * * | 0.0542 | 0.0000 | 0.0000 | YES | 0.035 |
| stop_vol_21 | -0.0428 | [-0.060, -0.024] * * | -0.0542 | 0.0000 | — | no | 0.035 |
| days_to_10 | -7.0722 | [-9.377, -4.794] * * | -15.1984 | 0.0000 | — | no | 0.035 |

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
| stop5 | 0.0324 | [+0.026, +0.043] * * | 0.0976 | 0.0000 | 0.0000 | YES | 0.218 |
| fwd_mdd_21 | -0.0063 | [-0.008, -0.005] * * | -0.0188 | 0.0000 | 0.0000 | YES | 0.218 |
| rotational_liftoff | 0.0193 | [+0.002, +0.028] * * | 0.0407 | 0.0220 | 0.0567 | YES | 0.218 |
| positional_liftoff | -0.0141 | [-0.029, -0.002] * * | -0.0090 | 0.0240 | 0.0608 | YES | 0.218 |
| dead_money | -0.0005 | [-0.002, +0.001] | -0.0018 | 0.2420 | 0.3997 | no | 0.218 |
| cushion_rot | 0.0102 | [-0.012, +0.019] | 0.0256 | 0.5760 | 0.7395 | no | 0.218 |
| zone_held_21 | -0.0065 | [-0.017, +0.001] | -0.0366 | 0.0720 | 0.1430 | no | 0.218 |
| stop_vol_21 | 0.0065 | [-0.001, +0.017] | 0.0366 | 0.0720 | — | no | 0.218 |
| days_to_10 | -1.9339 | [-2.872, -0.975] * * | -6.0683 | 0.0000 | — | no | 0.218 |

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
| stop5 | 0.0578 | [+0.046, +0.072] * * | 0.1578 | 0.0000 | 0.0000 | YES | 0.107 |
| fwd_mdd_21 | -0.0104 | [-0.013, -0.008] * * | -0.0271 | 0.0000 | 0.0000 | YES | 0.107 |
| rotational_liftoff | 0.0348 | [+0.011, +0.043] * * | 0.0839 | 0.0020 | 0.0066 | YES | 0.107 |
| positional_liftoff | -0.0194 | [-0.048, -0.004] * * | -0.0047 | 0.0220 | 0.0567 | YES | 0.107 |
| dead_money | -0.0012 | [-0.003, -0.000] * * | -0.0024 | 0.0400 | 0.0912 | YES | 0.107 |
| cushion_rot | 0.0157 | [-0.010, +0.021] | 0.0501 | 0.3460 | 0.5354 | no | 0.107 |
| zone_held_21 | -0.0143 | [-0.031, +0.000] | -0.0350 | 0.0520 | 0.1084 | no | 0.107 |
| stop_vol_21 | 0.0143 | [-0.000, +0.031] | 0.0350 | 0.0520 | — | no | 0.107 |
| days_to_10 | -4.3198 | [-5.102, -2.581] * * | -11.1094 | 0.0000 | — | no | 0.107 |

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
| stop5 | -0.0178 | [-0.032, -0.007] * * | -0.0123 | 0.0060 | 0.0168 | YES | 0.047 |
| fwd_mdd_21 | 0.0053 | [+0.003, +0.008] * * | 0.0037 | 0.0020 | 0.0066 | YES | 0.047 |
| rotational_liftoff | 0.1264 | [+0.101, +0.163] * * | 0.2035 | 0.0000 | 0.0000 | YES | 0.047 |
| positional_liftoff | 0.0826 | [+0.051, +0.122] * * | 0.1345 | 0.0000 | 0.0000 | YES | 0.047 |
| dead_money | -0.0016 | [-0.003, -0.000] * * | -0.0026 | 0.0360 | 0.0840 | YES | 0.047 |
| cushion_rot | 0.1312 | [+0.109, +0.155] * * | 0.2058 | 0.0000 | 0.0000 | YES | 0.047 |
| zone_held_21 | 0.0544 | [+0.037, +0.068] * * | 0.0573 | 0.0000 | 0.0000 | YES | 0.047 |
| stop_vol_21 | -0.0544 | [-0.068, -0.037] * * | -0.0573 | 0.0000 | — | no | 0.047 |
| days_to_10 | -7.9520 | [-10.111, -6.042] * * | -14.4552 | 0.0000 | — | no | 0.047 |

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

## Panel: baskets

> **NOTE (FINDING 4):** The baskets panel is run as a WHOLE — there is no dev/holdout half-split in this study. Any claim that baskets results span dev/holdout halves is incorrect.

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS STAMP: absolute rates on surviving basket names only. Comparisons within-era are directionally valid.

### Form: n21_k2_standalone

- Total events: 37857
- Deduped episodes: 37857
- Gradable: 36431
- N treatment: 36431 | N control: 107127
- Recall (treatment / all): 25.4%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0142 | [-0.017, +0.030] | 0.0239 | 0.7420 | 0.8977 | no | 0.254 |
| fwd_mdd_21 | 0.0072 | [-0.000, +0.007] | -0.0055 | 0.0520 | 0.1084 | no | 0.254 |
| rotational_liftoff | -0.0081 | [-0.026, +0.010] | 0.0198 | 0.2240 | 0.3763 | no | 0.254 |
| positional_liftoff | 0.0036 | [-0.022, +0.014] | 0.0176 | 0.5380 | 0.7030 | no | 0.254 |
| dead_money | 0.0021 | [-0.001, +0.003] | 0.0019 | 0.2400 | 0.3986 | no | 0.254 |
| cushion_rot | 0.0054 | [-0.023, +0.017] | 0.0264 | 0.4540 | 0.6296 | no | 0.254 |
| zone_held_21 | 0.0127 | [-0.035, +0.015] | -0.0152 | 0.7360 | 0.8941 | no | 0.254 |
| stop_vol_21 | -0.0127 | [-0.015, +0.035] | 0.0152 | 0.7360 | — | no | 0.254 |
| days_to_10 | 1.4451 | [-1.361, +1.604] | -1.0031 | 0.5740 | — | no | 0.254 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 5271 | 17.5% | 24.9% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 11329 | 15.7% | 30.7% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 10423 | 34.9% | 31.8% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 9408 | 19.1% | 38.0% |

### Form: n21_k2_coiled

- Total events: 2364
- Deduped episodes: 2364
- Gradable: 2258
- N treatment: 2258 | N control: 107127
- Recall (treatment / all): 2.1%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1045 | [-0.145, +0.065] | 0.0119 | 0.7280 | 0.8881 | no | 0.021 |
| fwd_mdd_21 | 0.0279 | [-0.004, +0.035] | 0.0078 | 0.4040 | 0.5909 | no | 0.021 |
| rotational_liftoff | -0.0039 | [-0.026, +0.039] | 0.1009 | 0.9920 | 1.0000 | no | 0.021 |
| positional_liftoff | 0.0391 | [-0.048, +0.080] | 0.0987 | 0.5180 | 0.6829 | no | 0.021 |
| dead_money | -0.0037 | [-0.004, -0.000] * * | -0.0025 | 0.0480 | 0.1030 | no | 0.021 |
| cushion_rot | 0.0424 | [-0.061, +0.075] | 0.1186 | 0.5500 | 0.7155 | no | 0.021 |
| zone_held_21 | 0.0671 | [-0.020, +0.089] | 0.0573 | 0.3880 | 0.5820 | no | 0.021 |
| stop_vol_21 | -0.0671 | [-0.089, +0.020] | -0.0573 | 0.3880 | — | no | 0.021 |
| days_to_10 | 4.6790 | [-5.625, +6.714] | -6.6669 | 0.7560 | — | no | 0.021 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 145 | 13.8% | 22.8% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 599 | 10.2% | 38.2% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 875 | 36.9% | 42.6% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 639 | 11.1% | 42.6% |

### Form: n21_k2_gatefire

- Total events: 5378
- Deduped episodes: 5378
- Gradable: 5153
- N treatment: 5153 | N control: 107127
- Recall (treatment / all): 4.6%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0782 | [-0.082, -0.012] * * | -0.0809 | 0.0020 | 0.0066 | YES | 0.046 |
| fwd_mdd_21 | 0.0174 | [+0.009, +0.018] * * | 0.0161 | 0.0000 | 0.0000 | YES | 0.046 |
| rotational_liftoff | 0.1309 | [+0.065, +0.142] * * | 0.1953 | 0.0000 | 0.0000 | YES | 0.046 |
| positional_liftoff | 0.0991 | [+0.020, +0.108] * * | 0.1500 | 0.0060 | 0.0168 | YES | 0.046 |
| dead_money | -0.0018 | [-0.002, +0.006] | -0.0004 | 0.5900 | 0.7509 | no | 0.046 |
| cushion_rot | 0.1612 | [+0.121, +0.187] * * | 0.2155 | 0.0000 | 0.0000 | YES | 0.046 |
| zone_held_21 | 0.0650 | [+0.021, +0.073] * * | 0.0771 | 0.0000 | 0.0000 | YES | 0.046 |
| stop_vol_21 | -0.0650 | [-0.073, -0.021] * * | -0.0771 | 0.0000 | — | no | 0.046 |
| days_to_10 | -5.5437 | [-8.296, -3.317] * * | -9.2028 | 0.0020 | — | no | 0.046 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 953 | 11.0% | 42.3% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 1648 | 10.9% | 45.9% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 1095 | 14.2% | 52.8% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 1457 | 11.7% | 55.8% |

### Form: n21_k3_standalone

- Total events: 47789
- Deduped episodes: 47789
- Gradable: 45952
- N treatment: 45952 | N control: 107127
- Recall (treatment / all): 30.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0137 | [-0.016, +0.023] | 0.0190 | 0.7120 | 0.8758 | no | 0.300 |
| fwd_mdd_21 | 0.0063 | [-0.001, +0.007] | -0.0052 | 0.1520 | 0.2742 | no | 0.300 |
| rotational_liftoff | -0.0082 | [-0.022, +0.007] | 0.0207 | 0.1640 | 0.2922 | no | 0.300 |
| positional_liftoff | 0.0014 | [-0.025, +0.008] | 0.0183 | 0.9500 | 1.0000 | no | 0.300 |
| dead_money | 0.0018 | [-0.001, +0.002] | 0.0016 | 0.3280 | 0.5129 | no | 0.300 |
| cushion_rot | 0.0037 | [-0.023, +0.015] | 0.0259 | 0.4820 | 0.6561 | no | 0.300 |
| zone_held_21 | 0.0114 | [-0.030, +0.014] | -0.0146 | 0.7280 | 0.8881 | no | 0.300 |
| stop_vol_21 | -0.0114 | [-0.014, +0.030] | 0.0146 | 0.7280 | — | no | 0.300 |
| days_to_10 | 1.4913 | [-1.450, +1.626] | -1.0321 | 0.5000 | — | no | 0.300 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 6775 | 17.4% | 24.0% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 14063 | 16.2% | 30.3% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 13085 | 33.2% | 32.5% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 12029 | 18.6% | 38.4% |

### Form: n21_k3_coiled

- Total events: 3020
- Deduped episodes: 3020
- Gradable: 2876
- N treatment: 2876 | N control: 107127
- Recall (treatment / all): 2.6%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1084 | [-0.145, +0.051] | -0.0033 | 0.6620 | 0.8307 | no | 0.026 |
| fwd_mdd_21 | 0.0276 | [-0.005, +0.035] | 0.0088 | 0.4380 | 0.6161 | no | 0.026 |
| rotational_liftoff | -0.0015 | [-0.025, +0.036] | 0.0984 | 0.8860 | 1.0000 | no | 0.026 |
| positional_liftoff | 0.0448 | [-0.046, +0.091] | 0.1022 | 0.4180 | 0.6024 | no | 0.026 |
| dead_money | -0.0037 | [-0.004, -0.000] * * | -0.0025 | 0.0480 | 0.1030 | no | 0.026 |
| cushion_rot | 0.0455 | [-0.050, +0.080] | 0.1144 | 0.4920 | 0.6652 | no | 0.026 |
| zone_held_21 | 0.0649 | [-0.007, +0.088] | 0.0535 | 0.1840 | 0.3255 | no | 0.026 |
| stop_vol_21 | -0.0649 | [-0.088, +0.007] | -0.0535 | 0.1840 | — | no | 0.026 |
| days_to_10 | 4.2695 | [-5.912, +6.434] | -6.3376 | 0.7580 | — | no | 0.026 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 234 | 15.8% | 20.1% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 746 | 11.4% | 37.0% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 1064 | 34.4% | 42.1% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 832 | 8.9% | 45.3% |

### Form: n21_k3_gatefire

- Total events: 7148
- Deduped episodes: 7148
- Gradable: 6842
- N treatment: 6842 | N control: 107127
- Recall (treatment / all): 6.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0743 | [-0.077, -0.018] * * | -0.0807 | 0.0000 | 0.0000 | YES | 0.060 |
| fwd_mdd_21 | 0.0167 | [+0.007, +0.017] * * | 0.0154 | 0.0000 | 0.0000 | YES | 0.060 |
| rotational_liftoff | 0.1288 | [+0.074, +0.139] * * | 0.1910 | 0.0000 | 0.0000 | YES | 0.060 |
| positional_liftoff | 0.0933 | [+0.030, +0.102] * * | 0.1434 | 0.0020 | 0.0066 | YES | 0.060 |
| dead_money | -0.0018 | [-0.002, +0.004] | -0.0003 | 0.5000 | 0.6652 | no | 0.060 |
| cushion_rot | 0.1552 | [+0.119, +0.170] * * | 0.2088 | 0.0000 | 0.0000 | YES | 0.060 |
| zone_held_21 | 0.0648 | [+0.012, +0.070] * * | 0.0749 | 0.0120 | 0.0327 | YES | 0.060 |
| stop_vol_21 | -0.0648 | [-0.070, -0.012] * * | -0.0749 | 0.0120 | — | no | 0.060 |
| days_to_10 | -5.3693 | [-9.556, -4.999] * * | -9.2559 | 0.0000 | — | no | 0.060 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 1327 | 10.5% | 39.7% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 2083 | 11.1% | 46.2% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 1541 | 14.5% | 52.8% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 1891 | 11.5% | 55.8% |

### Form: n21_k5_standalone

- Total events: 59360
- Deduped episodes: 59360
- Gradable: 57107
- N treatment: 57107 | N control: 107127
- Recall (treatment / all): 34.8%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0155 | [-0.018, +0.015] | 0.0194 | 0.3940 | 0.5880 | no | 0.348 |
| fwd_mdd_21 | 0.0058 | [-0.000, +0.006] | -0.0051 | 0.0940 | 0.1830 | no | 0.348 |
| rotational_liftoff | -0.0092 | [-0.019, +0.007] | 0.0149 | 0.2240 | 0.3763 | no | 0.348 |
| positional_liftoff | -0.0012 | [-0.017, +0.006] | 0.0104 | 0.2980 | 0.4788 | no | 0.348 |
| dead_money | 0.0014 | [-0.001, +0.002] | 0.0013 | 0.4540 | 0.6296 | no | 0.348 |
| cushion_rot | 0.0024 | [-0.014, +0.020] | 0.0186 | 0.3620 | 0.5514 | no | 0.348 |
| zone_held_21 | 0.0143 | [-0.021, +0.016] | -0.0127 | 0.5800 | 0.7414 | no | 0.348 |
| stop_vol_21 | -0.0143 | [-0.016, +0.021] | 0.0127 | 0.5800 | — | no | 0.348 |
| days_to_10 | 1.4116 | [-1.903, +1.575] | -0.7542 | 0.6260 | — | no | 0.348 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 8397 | 17.3% | 23.8% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 17374 | 16.2% | 30.4% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 16375 | 33.4% | 31.8% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 14961 | 18.5% | 37.0% |

### Form: n21_k5_coiled

- Total events: 3994
- Deduped episodes: 3994
- Gradable: 3800
- N treatment: 3800 | N control: 107127
- Recall (treatment / all): 3.4%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1129 | [-0.143, +0.031] | 0.0009 | 0.3960 | 0.5880 | no | 0.034 |
| fwd_mdd_21 | 0.0283 | [-0.003, +0.035] | 0.0081 | 0.3060 | 0.4889 | no | 0.034 |
| rotational_liftoff | -0.0116 | [-0.028, +0.034] | 0.0749 | 0.7900 | 0.9519 | no | 0.034 |
| positional_liftoff | 0.0311 | [-0.038, +0.061] | 0.0744 | 0.4280 | 0.6108 | no | 0.034 |
| dead_money | -0.0036 | [-0.004, -0.000] * * | -0.0025 | 0.0040 | 0.0120 | YES | 0.034 |
| cushion_rot | 0.0353 | [-0.032, +0.061] | 0.0925 | 0.3740 | 0.5668 | no | 0.034 |
| zone_held_21 | 0.0665 | [-0.006, +0.089] | 0.0480 | 0.1300 | 0.2389 | no | 0.034 |
| stop_vol_21 | -0.0665 | [-0.089, +0.006] | -0.0480 | 0.1300 | — | no | 0.034 |
| days_to_10 | 4.2155 | [-5.563, +6.471] | -5.5936 | 0.7600 | — | no | 0.034 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 309 | 15.9% | 20.4% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 1000 | 11.8% | 37.6% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 1432 | 34.4% | 38.3% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 1059 | 9.5% | 41.6% |

### Form: n21_k5_gatefire

- Total events: 9546
- Deduped episodes: 9546
- Gradable: 9133
- N treatment: 9133 | N control: 107127
- Recall (treatment / all): 7.9%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0740 | [-0.076, -0.023] * * | -0.0756 | 0.0000 | 0.0000 | YES | 0.079 |
| fwd_mdd_21 | 0.0163 | [+0.007, +0.017] * * | 0.0146 | 0.0000 | 0.0000 | YES | 0.079 |
| rotational_liftoff | 0.1203 | [+0.079, +0.133] * * | 0.1795 | 0.0000 | 0.0000 | YES | 0.079 |
| positional_liftoff | 0.0867 | [+0.030, +0.091] * * | 0.1324 | 0.0000 | 0.0000 | YES | 0.079 |
| dead_money | -0.0019 | [-0.002, +0.002] | -0.0004 | 0.4180 | 0.6024 | no | 0.079 |
| cushion_rot | 0.1470 | [+0.125, +0.174] * * | 0.1977 | 0.0000 | 0.0000 | YES | 0.079 |
| zone_held_21 | 0.0649 | [+0.015, +0.068] * * | 0.0760 | 0.0060 | 0.0168 | YES | 0.079 |
| stop_vol_21 | -0.0649 | [-0.068, -0.015] * * | -0.0760 | 0.0060 | — | no | 0.079 |
| days_to_10 | -5.4035 | [-9.269, -5.079] * * | -9.2090 | 0.0000 | — | no | 0.079 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 1739 | 10.3% | 38.3% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 2727 | 11.4% | 45.9% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 2149 | 16.3% | 50.9% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 2518 | 11.6% | 54.4% |

### Form: n63_k2_standalone

- Total events: 19666
- Deduped episodes: 19666
- Gradable: 19068
- N treatment: 19068 | N control: 107127
- Recall (treatment / all): 15.1%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0056 | [+0.003, +0.040] * * | 0.0594 | 0.0000 | 0.0000 | YES | 0.151 |
| fwd_mdd_21 | 0.0023 | [-0.001, +0.005] | -0.0149 | 0.1020 | 0.1973 | no | 0.151 |
| rotational_liftoff | -0.0059 | [-0.021, +0.031] | 0.0474 | 0.4380 | 0.6161 | no | 0.151 |
| positional_liftoff | -0.0025 | [-0.046, +0.008] | 0.0291 | 0.2600 | 0.4247 | no | 0.151 |
| dead_money | -0.0005 | [-0.001, +0.002] | 0.0002 | 0.4080 | 0.5938 | no | 0.151 |
| cushion_rot | 0.0093 | [-0.041, +0.025] | 0.0459 | 0.4600 | 0.6349 | no | 0.151 |
| zone_held_21 | 0.0090 | [-0.028, +0.029] | -0.0236 | 0.3520 | 0.5390 | no | 0.151 |
| stop_vol_21 | -0.0090 | [-0.029, +0.028] | 0.0236 | 0.3520 | — | no | 0.151 |
| days_to_10 | 0.7091 | [-3.069, +0.990] | -4.1347 | 0.6780 | — | no | 0.151 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 2590 | 18.3% | 28.1% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 5564 | 19.2% | 32.2% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 5833 | 41.2% | 34.2% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 5081 | 19.5% | 41.7% |

### Form: n63_k2_coiled

- Total events: 1957
- Deduped episodes: 1957
- Gradable: 1884
- N treatment: 1884 | N control: 107127
- Recall (treatment / all): 1.7%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1017 | [-0.147, +0.068] | 0.0234 | 0.7040 | 0.8696 | no | 0.017 |
| fwd_mdd_21 | 0.0290 | [-0.003, +0.037] | 0.0080 | 0.2100 | 0.3590 | no | 0.017 |
| rotational_liftoff | -0.0025 | [-0.027, +0.038] | 0.1165 | 0.9120 | 1.0000 | no | 0.017 |
| positional_liftoff | 0.0360 | [-0.055, +0.082] | 0.1098 | 0.6400 | 0.8076 | no | 0.017 |
| dead_money | -0.0034 | [-0.004, -0.000] * * | -0.0025 | 0.0480 | 0.1030 | no | 0.017 |
| cushion_rot | 0.0471 | [-0.062, +0.084] | 0.1333 | 0.4480 | 0.6272 | no | 0.017 |
| zone_held_21 | 0.0898 | [+0.002, +0.121] * * | 0.0734 | 0.0440 | 0.0987 | YES | 0.017 |
| stop_vol_21 | -0.0898 | [-0.121, -0.002] * * | -0.0734 | 0.0440 | — | no | 0.017 |
| days_to_10 | 5.0618 | [-5.479, +7.169] | -7.4795 | 0.7400 | — | no | 0.017 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 125 | 12.8% | 24.8% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 499 | 10.8% | 39.7% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 728 | 39.7% | 43.3% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 532 | 11.1% | 45.7% |

### Form: n63_k2_gatefire

- Total events: 3415
- Deduped episodes: 3415
- Gradable: 3319
- N treatment: 3319 | N control: 107127
- Recall (treatment / all): 3.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0676 | [-0.072, +0.004] | -0.0651 | 0.0860 | 0.1686 | no | 0.030 |
| fwd_mdd_21 | 0.0147 | [+0.008, +0.019] * * | 0.0128 | 0.0000 | 0.0000 | YES | 0.030 |
| rotational_liftoff | 0.1447 | [+0.099, +0.204] * * | 0.2215 | 0.0000 | 0.0000 | YES | 0.030 |
| positional_liftoff | 0.1041 | [+0.036, +0.143] * * | 0.1613 | 0.0040 | 0.0120 | YES | 0.030 |
| dead_money | -0.0013 | [-0.002, +0.010] | -0.0001 | 0.5100 | 0.6754 | no | 0.030 |
| cushion_rot | 0.1605 | [+0.101, +0.213] * * | 0.2248 | 0.0000 | 0.0000 | YES | 0.030 |
| zone_held_21 | 0.0598 | [+0.029, +0.092] * * | 0.0715 | 0.0020 | 0.0066 | YES | 0.030 |
| stop_vol_21 | -0.0598 | [-0.092, -0.029] * * | -0.0715 | 0.0020 | — | no | 0.030 |
| days_to_10 | -6.0335 | [-10.366, -3.858] * * | -10.9997 | 0.0020 | — | no | 0.030 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 689 | 12.0% | 44.3% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 976 | 13.5% | 48.4% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 709 | 16.1% | 55.9% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 945 | 12.5% | 58.8% |

### Form: n63_k3_standalone

- Total events: 24613
- Deduped episodes: 24613
- Gradable: 23808
- N treatment: 23808 | N control: 107127
- Recall (treatment / all): 18.2%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0059 | [+0.003, +0.032] * * | 0.0549 | 0.0060 | 0.0168 | YES | 0.182 |
| fwd_mdd_21 | 0.0019 | [-0.001, +0.004] | -0.0142 | 0.1280 | 0.2382 | no | 0.182 |
| rotational_liftoff | -0.0063 | [-0.027, +0.026] | 0.0456 | 0.4020 | 0.5909 | no | 0.182 |
| positional_liftoff | -0.0049 | [-0.039, +0.013] | 0.0270 | 0.2000 | 0.3459 | no | 0.182 |
| dead_money | -0.0004 | [-0.001, +0.002] | 0.0001 | 0.4700 | 0.6457 | no | 0.182 |
| cushion_rot | 0.0077 | [-0.032, +0.027] | 0.0424 | 0.3980 | 0.5880 | no | 0.182 |
| zone_held_21 | 0.0104 | [-0.018, +0.024] | -0.0218 | 0.3200 | 0.5031 | no | 0.182 |
| stop_vol_21 | -0.0104 | [-0.024, +0.018] | 0.0218 | 0.3200 | — | no | 0.182 |
| days_to_10 | 0.8358 | [-3.531, +1.112] | -4.0895 | 0.7140 | — | no | 0.182 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 3380 | 18.7% | 26.6% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 6788 | 19.5% | 31.9% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 7147 | 40.0% | 34.1% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 6493 | 19.2% | 42.2% |

### Form: n63_k3_coiled

- Total events: 2500
- Deduped episodes: 2500
- Gradable: 2404
- N treatment: 2404 | N control: 107127
- Recall (treatment / all): 2.2%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1048 | [-0.145, +0.053] | 0.0070 | 0.7000 | 0.8684 | no | 0.022 |
| fwd_mdd_21 | 0.0281 | [-0.005, +0.037] | 0.0089 | 0.3400 | 0.5289 | no | 0.022 |
| rotational_liftoff | -0.0046 | [-0.034, +0.032] | 0.1111 | 0.8480 | 1.0000 | no | 0.022 |
| positional_liftoff | 0.0377 | [-0.056, +0.084] | 0.1096 | 0.6240 | 0.7908 | no | 0.022 |
| dead_money | -0.0034 | [-0.004, -0.000] * * | -0.0025 | 0.0480 | 0.1030 | no | 0.022 |
| cushion_rot | 0.0485 | [-0.058, +0.086] | 0.1263 | 0.4960 | 0.6652 | no | 0.022 |
| zone_held_21 | 0.0817 | [+0.003, +0.110] * * | 0.0678 | 0.0280 | 0.0698 | YES | 0.022 |
| stop_vol_21 | -0.0817 | [-0.110, -0.003] * * | -0.0678 | 0.0280 | — | no | 0.022 |
| days_to_10 | 4.6387 | [-5.076, +6.613] | -7.1253 | 0.7340 | — | no | 0.022 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 207 | 15.9% | 20.8% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 614 | 11.7% | 38.1% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 888 | 36.8% | 42.3% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 695 | 8.9% | 48.5% |

### Form: n63_k3_gatefire

- Total events: 4553
- Deduped episodes: 4553
- Gradable: 4406
- N treatment: 4406 | N control: 107127
- Recall (treatment / all): 4.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0629 | [-0.066, -0.006] * * | -0.0639 | 0.0320 | 0.0778 | YES | 0.040 |
| fwd_mdd_21 | 0.0138 | [+0.007, +0.016] * * | 0.0118 | 0.0000 | 0.0000 | YES | 0.040 |
| rotational_liftoff | 0.1353 | [+0.079, +0.177] * * | 0.2094 | 0.0000 | 0.0000 | YES | 0.040 |
| positional_liftoff | 0.0906 | [+0.036, +0.125] * * | 0.1464 | 0.0060 | 0.0168 | YES | 0.040 |
| dead_money | -0.0018 | [-0.002, +0.007] | -0.0002 | 0.5000 | 0.6652 | no | 0.040 |
| cushion_rot | 0.1527 | [+0.106, +0.189] * * | 0.2147 | 0.0000 | 0.0000 | YES | 0.040 |
| zone_held_21 | 0.0602 | [+0.024, +0.069] * * | 0.0707 | 0.0000 | 0.0000 | YES | 0.040 |
| stop_vol_21 | -0.0602 | [-0.069, -0.024] * * | -0.0707 | 0.0000 | — | no | 0.040 |
| days_to_10 | -5.5149 | [-10.541, -4.903] * * | -10.6886 | 0.0000 | — | no | 0.040 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 969 | 12.0% | 40.8% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 1220 | 13.6% | 47.8% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 984 | 17.1% | 54.5% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 1233 | 12.2% | 59.1% |

### Form: n63_k5_standalone

- Total events: 30445
- Deduped episodes: 30445
- Gradable: 29435
- N treatment: 29435 | N control: 107127
- Recall (treatment / all): 21.6%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0011 | [-0.008, +0.021] | 0.0554 | 0.3840 | 0.5790 | no | 0.216 |
| fwd_mdd_21 | 0.0019 | [-0.001, +0.004] | -0.0140 | 0.1860 | 0.3255 | no | 0.216 |
| rotational_liftoff | -0.0071 | [-0.029, +0.014] | 0.0355 | 0.2440 | 0.4008 | no | 0.216 |
| positional_liftoff | -0.0076 | [-0.041, -0.003] * * | 0.0157 | 0.0240 | 0.0608 | YES | 0.216 |
| dead_money | -0.0004 | [-0.002, +0.001] | 0.0000 | 0.3480 | 0.5357 | no | 0.216 |
| cushion_rot | 0.0047 | [-0.031, +0.017] | 0.0318 | 0.4960 | 0.6652 | no | 0.216 |
| zone_held_21 | 0.0138 | [-0.016, +0.026] | -0.0208 | 0.2200 | 0.3739 | no | 0.216 |
| stop_vol_21 | -0.0138 | [-0.026, +0.016] | 0.0208 | 0.2200 | — | no | 0.216 |
| days_to_10 | 0.7031 | [-2.682, +0.955] | -3.7437 | 0.6500 | — | no | 0.216 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 4130 | 18.9% | 25.9% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 8469 | 19.4% | 31.8% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 8896 | 40.1% | 32.6% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 7940 | 19.1% | 40.6% |

### Form: n63_k5_coiled

- Total events: 3298
- Deduped episodes: 3298
- Gradable: 3166
- N treatment: 3166 | N control: 107127
- Recall (treatment / all): 2.9%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1085 | [-0.139, +0.038] | 0.0145 | 0.4380 | 0.6161 | no | 0.029 |
| fwd_mdd_21 | 0.0283 | [-0.004, +0.035] | 0.0073 | 0.3140 | 0.4963 | no | 0.029 |
| rotational_liftoff | -0.0154 | [-0.031, +0.026] | 0.0828 | 0.5580 | 0.7227 | no | 0.029 |
| positional_liftoff | 0.0250 | [-0.050, +0.054] | 0.0776 | 0.6900 | 0.8596 | no | 0.029 |
| dead_money | -0.0036 | [-0.004, -0.000] * * | -0.0025 | 0.0160 | 0.0428 | YES | 0.029 |
| cushion_rot | 0.0380 | [-0.042, +0.063] | 0.1008 | 0.4260 | 0.6108 | no | 0.029 |
| zone_held_21 | 0.0801 | [-0.001, +0.106] | 0.0584 | 0.0560 | 0.1151 | no | 0.029 |
| stop_vol_21 | -0.0801 | [-0.106, +0.001] | -0.0584 | 0.0560 | — | no | 0.029 |
| days_to_10 | 4.5626 | [-5.343, +6.554] | -6.1691 | 0.7560 | — | no | 0.029 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 268 | 15.7% | 21.3% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 832 | 12.3% | 38.0% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 1194 | 37.6% | 38.0% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 872 | 9.5% | 44.5% |

### Form: n63_k5_gatefire

- Total events: 6120
- Deduped episodes: 6120
- Gradable: 5899
- N treatment: 5899 | N control: 107127
- Recall (treatment / all): 5.2%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0623 | [-0.064, -0.022] * * | -0.0569 | 0.0000 | 0.0000 | YES | 0.052 |
| fwd_mdd_21 | 0.0130 | [+0.007, +0.014] * * | 0.0105 | 0.0000 | 0.0000 | YES | 0.052 |
| rotational_liftoff | 0.1219 | [+0.065, +0.158] * * | 0.1920 | 0.0000 | 0.0000 | YES | 0.052 |
| positional_liftoff | 0.0827 | [+0.022, +0.090] * * | 0.1331 | 0.0040 | 0.0120 | YES | 0.052 |
| dead_money | -0.0022 | [-0.003, +0.005] | -0.0005 | 0.4780 | 0.6536 | no | 0.052 |
| cushion_rot | 0.1414 | [+0.111, +0.176] * * | 0.1993 | 0.0000 | 0.0000 | YES | 0.052 |
| zone_held_21 | 0.0576 | [+0.024, +0.062] * * | 0.0696 | 0.0000 | 0.0000 | YES | 0.052 |
| stop_vol_21 | -0.0576 | [-0.062, -0.024] * * | -0.0696 | 0.0000 | — | no | 0.052 |
| days_to_10 | -5.4878 | [-9.459, -5.061] * * | -10.5524 | 0.0000 | — | no | 0.052 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| 2012-2015 | 0 | 10880 | 16.0% | 22.0% |
| 2012-2015 | 1 | 1236 | 11.7% | 39.3% |
| 2016-2019 | 0 | 33191 | 14.3% | 26.7% |
| 2016-2019 | 1 | 1635 | 14.1% | 47.1% |
| 2020-2022 | 0 | 29794 | 26.1% | 33.0% |
| 2020-2022 | 1 | 1388 | 19.3% | 51.2% |
| 2023-2026 | 0 | 33262 | 21.4% | 33.4% |
| 2023-2026 | 1 | 1640 | 12.3% | 57.0% |

## Panel: delisted

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS STAMP: delisted close-only panel — ex-members included.

### Form: n21_k2_standalone

- Total events: 5927
- Deduped episodes: 5927
- Gradable: 5695
- N treatment: 5695 | N control: 0
- Recall (treatment / all): 100.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| fwd_mdd_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| rotational_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| positional_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| dead_money | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| cushion_rot | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| zone_held_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| stop_vol_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |
| days_to_10 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **INSUFFICIENT DATA**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 1 | 2727 | 37.4% | 37.0% |
| 2012-2015 | 1 | 766 | 44.8% | 35.5% |
| 2016-2019 | 1 | 701 | 38.4% | 37.4% |
| 2020-2022 | 1 | 840 | 44.0% | 38.1% |
| 2023-2026 | 1 | 661 | 41.6% | 41.1% |

### Form: n21_k2_coiled

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n21_k2_gatefire

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n21_k3_standalone

- Total events: 7316
- Deduped episodes: 7316
- Gradable: 7045
- N treatment: 7045 | N control: 0
- Recall (treatment / all): 100.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| fwd_mdd_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| rotational_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| positional_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| dead_money | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| cushion_rot | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| zone_held_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| stop_vol_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |
| days_to_10 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **INSUFFICIENT DATA**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 1 | 3377 | 36.5% | 36.5% |
| 2012-2015 | 1 | 962 | 41.7% | 36.0% |
| 2016-2019 | 1 | 864 | 36.8% | 37.9% |
| 2020-2022 | 1 | 1014 | 43.4% | 38.4% |
| 2023-2026 | 1 | 828 | 39.4% | 39.7% |

### Form: n21_k3_coiled

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n21_k3_gatefire

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n21_k5_standalone

- Total events: 8869
- Deduped episodes: 8869
- Gradable: 8552
- N treatment: 8552 | N control: 0
- Recall (treatment / all): 100.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| fwd_mdd_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| rotational_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| positional_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| dead_money | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| cushion_rot | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| zone_held_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| stop_vol_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |
| days_to_10 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **INSUFFICIENT DATA**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 1 | 4121 | 36.2% | 34.8% |
| 2012-2015 | 1 | 1177 | 40.5% | 34.1% |
| 2016-2019 | 1 | 1066 | 35.9% | 37.6% |
| 2020-2022 | 1 | 1190 | 43.7% | 36.7% |
| 2023-2026 | 1 | 998 | 39.2% | 38.0% |

### Form: n21_k5_coiled

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n21_k5_gatefire

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n63_k2_standalone

- Total events: 3430
- Deduped episodes: 3430
- Gradable: 3306
- N treatment: 3306 | N control: 0
- Recall (treatment / all): 100.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| fwd_mdd_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| rotational_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| positional_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| dead_money | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| cushion_rot | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| zone_held_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| stop_vol_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |
| days_to_10 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **INSUFFICIENT DATA**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 1 | 1574 | 39.2% | 37.4% |
| 2012-2015 | 1 | 438 | 47.0% | 34.2% |
| 2016-2019 | 1 | 396 | 38.6% | 39.1% |
| 2020-2022 | 1 | 500 | 49.6% | 34.8% |
| 2023-2026 | 1 | 398 | 37.7% | 43.0% |

### Form: n63_k2_coiled

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n63_k2_gatefire

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n63_k3_standalone

- Total events: 4208
- Deduped episodes: 4208
- Gradable: 4065
- N treatment: 4065 | N control: 0
- Recall (treatment / all): 100.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| fwd_mdd_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| rotational_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| positional_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| dead_money | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| cushion_rot | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| zone_held_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| stop_vol_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |
| days_to_10 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **INSUFFICIENT DATA**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 1 | 1924 | 38.5% | 36.6% |
| 2012-2015 | 1 | 558 | 42.1% | 35.7% |
| 2016-2019 | 1 | 484 | 37.0% | 39.1% |
| 2020-2022 | 1 | 604 | 48.8% | 34.8% |
| 2023-2026 | 1 | 495 | 36.8% | 41.8% |

### Form: n63_k3_coiled

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n63_k3_gatefire

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n63_k5_standalone

- Total events: 5032
- Deduped episodes: 5032
- Gradable: 4866
- N treatment: 4866 | N control: 0
- Recall (treatment / all): 100.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| fwd_mdd_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| rotational_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| positional_liftoff | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| dead_money | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| cushion_rot | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| zone_held_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | 1.0000 | no | 1.000 |
| stop_vol_21 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |
| days_to_10 | 0.0000 | [+0.000, +0.000] | — | 1.0000 | — | no | 1.000 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **INSUFFICIENT DATA**

| era | _is_sur | n_fires | stop5_rate | rot_liftoff_rate |
|---|---|---|---|---|
| pre_2012 | 1 | 2306 | 39.0% | 34.7% |
| 2012-2015 | 1 | 682 | 42.1% | 33.3% |
| 2016-2019 | 1 | 584 | 36.1% | 39.4% |
| 2020-2022 | 1 | 696 | 49.0% | 33.6% |
| 2023-2026 | 1 | 598 | 37.0% | 39.8% |

### Form: n63_k5_coiled

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

### Form: n63_k5_gatefire

- Total events: 0
- Deduped episodes: 0
- Gradable: 0
- N treatment: 0 | N control: 0

*No gradable events for this form.*

---

## Holdability Appendix (mae63 — descriptive only, feeds NO verdict clause)

Per RUL-13, mae63 is removed from the primary verdict table. It appears here in a clearly-labeled holdability appendix only. All adjudication is based on the 21d horizon metrics above.

*mae63 was computed but is not reported in this appendix to avoid confusion.*
*If needed for the holdability lane (S-QL §3 F5), it will appear in a separate lane report.*

---

## Methodology Notes

**Weekly-D staleness (FINDING 5 — DOCUMENTED):** The vectorized cohort computation
uses the last completed W-FRI StochRSI D bar at or before each fire date.
engine/coiled.weekly_d_last() (live engine) includes the partial current week's bar.
On non-Friday fire dates, the vectorized D value is up to 4 trading days stale.
The equivalence claim between the vectorized path and weekly_d_last is DROPPED.
The direction of the staleness bias is INDETERMINATE: a stale last-Friday D value
can be higher or lower than the live partial-week D, so cohort_frac (and hence
TRUE-COILED membership via the >=0.40 threshold) can move either way.
The net effect on the COILED form's n is not guaranteed to be conservative.

**NC-2 band FE fix (FINDING 1):** Prior implementation assigned proximity bands
to treatment rows only; control rows got band='unknown', causing perfect FE
separation and mechanically degenerate coef=0.0. Fixed: bands now computed
for BOTH arms so treatment and control co-exist in the same FE cells.

**Per-form co-fire shares (FINDING 2):** Co-fire shares are now computed
on each form's own event subset, not the shared standalone event set.
The gatefire form measures co-fire on its own event subset; the +/-3-bar check differs from the +/-5-bar form definition, so measured co-fire is 36.4%, not 100% (PASS).

**NC yardstick (FINDING 4):** Parsed from W1_NC_REPORT.md at runtime.
Source: W1-NC artifact (research/entry_stack/W1_NC_REPORT.md).

---

*Generated by `scripts/research/run_w2_sur.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*Family: esx_ur_phase0 (budget=36). BH q<=0.1 family-wide (pool excludes stop_vol_21, days_to_10).*
*Survivor bias: absolute rates on surviving names only; comparisons valid within constraint.*
*Sign convention: stop5 is adverse — positive coef = MORE stops (WORSE candidate). Non-inferiority = CI_hi < +0.01.*