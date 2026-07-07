# W2 Squeeze Release (S-SQ) Phase-0 Report — Entry-Stack Expansion

**Status:** W2 study report only — no promotion decision (RUL-3).
**Date:** 2026-07-05
**Species:** S16 — Squeeze Release, horizon_class=rotational, phase0.
**Species note:** S14=Failed breakout, S15=Spring Reclaim are taken on origin/main. Squeeze Release uses S16 (next free number, verified at registration).
**Family:** esx_sq_phase0 (budget=12).

## HEADLINE — Per-Form Honest Verdict

**Sign convention:** stop5 is an ADVERSE outcome. MORE POSITIVE coefficient = MORE stops (WORSE).
Non-inferiority = CI upper bound < +0.01. Superiority on stop5 = CI upper bound < 0.0.

**Per-form primary results (deep panel, defaults cfg) — ALL NUMBERS FROM THIS RUN:**

| Form | stop5 coef | 95% CI_hi | Non-inferior (CI_hi<+0.01)? | Superior (CI_hi<0)? | Independence (co-fire<=60%) | zone_held_21 coef (context) |
|---|---|---|---|---|---|---|
| standalone (deep, defaults) | -0.0118 | 0.0022 | YES | NO | PASS (41.9%) | -0.0222 |
| COILED-intersection (deep, defaults) | 0.0080 | 0.0450 | NO | NO | PASS (48.0%) | -0.0312 |
| gatefire-proximity (deep, defaults) | -0.0192 | -0.0050 | YES | YES | N/A-STRUCTURAL (81.6%) | -0.0005 |

**Adjacency (R2 per RUL-2):** H2 aged-quiet-base arming is the nearest falsified relative. S16 acts ONLY on the confirmed FIRED_UP release bar (direction + vol confirmed) — confirmation vs anticipation. An arming variant is BANNED from this family. This distinction must hold empirically or the species fails.

**HONEST FINDING (AS MEASURED IN THIS RUN):** See per-form species bar summary below.
Nulls and kills printed with equal care as wins.
**Adjudication belongs to the orchestrator, not this study.**

## NC Yardstick (RUL-3 mandatory preamble)

**Source: W1-NC artifact** (`research/entry_stack/W1_NC_REPORT.md`).
Numbers below are parsed from that file at runtime — NOT hardcoded.
Per masterplan §10 RUL-3: null-competitors appear as the first table.
Reading: stop5 is adverse — a BETTER signal has a MORE NEGATIVE coefficient.
The S-SQ candidate 'beats NC-2' only if its stop5 coefficient retains CI-excluding-0 AFTER entry_quality-band fixed effects (tested for gatefire form; see NC-2 Marginality below).

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |
|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | -0.0019 | [-0.016, +0.008] | no | 89.1% |
| deep | NC-1B (ticks=0) | 0.0001 | [-0.015, +0.007] | no | 90.8% |
| deep | NC-2 (prox top-tercile) | -0.0427 | [-0.044, -0.031] * | YES * | 33.4% |
| baskets | NC-1A (T1-only) | -0.0036 | [-0.011, +0.006] | no | 85.9% |
| baskets | NC-1B (ticks=0) | 0.0099 | [+0.002, +0.015] * | YES * | 90.9% |
| baskets | NC-2 (prox top-tercile) | -0.1012 | [-0.108, -0.096] * | YES * | 34.0% |

NC-2 proximity note: NC-2 PARTIAL: proximity component only (EQ_W_PROX=0.52 of total). PROXY-INPUT LIMITATION: the 63-bar close-min pivot is a PROXY for the true cand_price/dcl_price pivot (cycles.py:1705-1706). NC-2 marginality test for gatefire form only (proximity confounding is the primary alternative explanation for any stop5 improvement in that form). NC-2 is DESCRIPTIVE-ONLY for standalone and COILED forms.

## COILED-FIRE Recall Clause Note

COILED-FIRE recall is DEFERRED (per W0_BASELINES.md §COILED/COILED-FIRE Recall Recompute). The recall clause (recall >= half of COILED-FIRE recall) cannot be fully evaluated until the full cycles.py pipeline is run per-fire over all gate dates. S-SQ proxy reported as TREATMENT-SHARE-OF-POOL (n_treatment / (n_treatment + n_control)): this is NOT the +/-5-bar gate-fire recall (n_near / total_gf) as used in S-UR; the recall clause is DEFERRED so this proxy feeds no verdict, it is cosmetic only.

## Independence Clause (Per-Form Co-Fire Shares)

Per-form co-fire shares at +/-3 TRUE TRADING BARS (deep panel, defaults cfg):
Co-fire computed on each form's OWN event subset (L1 law: same as S-UR).

| Form | Co-fire share | n near | Independence clause (<=60%) |
|---|---|---|---|
| standalone | 41.9% | 2345 | PASS |
| COILED-intersection | 48.0% | — | PASS |
| gatefire-proximity | 81.6% | 2345 | N/A-STRUCTURAL |

**DESIGN NOTE — GATEFIRE FORM INDEPENDENCE IS N/A-STRUCTURAL:** The gatefire form selects S-SQ events WITHIN ±5 BARS of gate fires (form definition). It is structurally gate-dependent. The ±3-bar co-fire check uses a tighter radius. Verdict: N/A-STRUCTURAL (same reasoning as S-UR gatefire form).

Aggregate co-fire share (standalone forms): 41.3%
Independence clause threshold: <= 60%

## Delisted Panel Status

DELISTED ARM: NOT APPLICABLE — the delisted panel (data/breadth/_closes_delisted.parquet) is close-only and does not contain H/L columns. engine/vol_squeeze.assess_series requires H/L for the TTM-squeeze arm of the compression detection gate. Without H/L the compression threshold is looser (BBWP+HVP only, no TTM), changing the fidelity-pinned event definition. Per masterplan §1 fact table row 3: 'NOT for H/L-dependent species (S-SQ)'. This panel cannot run this species. Results are based on deep and baskets panels only.

## Volume Coverage Table (Mechanism-Faithful Events)

**BLOCKER FIX:** The prior loaders dropped `volume`, leaving `vol_ok=None` in `assess()` so every FIRED_UP fired on price break ALONE. This table verifies the fix: volume must be present and `volume_confirmed` must be True/False (never NaN) on all OHLCV names.

**Mechanism-faithful set** = events with `volume_confirmed == True`. Events with `volume_confirmed == False` are volume-ABSENT or below threshold. Events with `volume_confirmed` missing (NaN) indicate tickers without volume in the raw store — these are excluded from the mechanism-faithful count. Per task brief: 'if any names genuinely lack volume, exclude their events from the mechanism-faithful set with counts printed.'

### Spot-Check: Volume Loading Verification (AAPL + 3 sampled names)

| Panel | Ticker | has_volume | n_rows | vol_nonzero | vol_null |
|---|---|---|---|---|---|
| deep | AAPL | True | 11480 | 11479 | 0 |
| deep | ABBV | True | 3395 | 3395 | 0 |
| deep | ABNB | True | 1395 | 1395 | 0 |
| deep | ABT | True | 11668 | 11668 | 0 |
| baskets | AAPL | True | 3143 | 3143 | 0 |
| baskets | A | True | 3140 | 3140 | 0 |
| baskets | AAL | True | 3140 | 3140 | 0 |
| baskets | AAMI | True | 2949 | 2949 | 0 |

### Per-Panel Volume-Confirmed Summary (defaults cfg events)

| Panel | Total events | volume_confirmed=True | volume_confirmed=False | volume_confirmed=NaN (missing) | % mechanism-faithful |
|---|---|---|---|---|---|
| deep | 5602 | 2618 | 2975 | 9 | 46.7% |
| baskets | 16926 | 8483 | 8427 | 16 | 50.1% |

> **volume_confirmed=True** = direction break AND vol >= 1.3x 20d avg (the S16 mechanism definition). **volume_confirmed=False** = price broke the squeeze box but volume was below the 1.3x threshold — price-break-only, not mechanism-faithful. The species bar uses ALL FIRED_UP events (the registered event set); the mechanism-faithful fraction is a diagnostic.

## BH Correction Scope

Family-wide BH: one BH pass pooling ALL cells x forms x outcomes of esx_sq_phase0.
Pool includes defaults + all 3 named sensitivities (pctile20, relwin2, volconf15) × all forms × all panels. Pool excludes stop_vol_21 (mechanical mirror of zone_held_21) and days_to_10 (collider).
BH q <= 0.1 threshold applied to all pooled cells.

## Event Counts

- Deep panel FIRED_UP onsets (defaults cfg): 5602
- Baskets panel FIRED_UP onsets (defaults cfg): 16926

## Sensitivity Analysis (Registered 12-Trial Budget)

Per masterplan §5 trial-ledger: `esx_sq_phase0` budget=12 covers 'frozen state grid × 2 panels × 3 forms + 3 named sensitivities (pctile_thresh=20; release_window=2; vol_confirm=1.5)'. Each sensitivity is enumerated, graded, and analyzed independently. volconf15 is now meaningful with volume flowing (BLOCKER FIX applied).

| Sensitivity | Panel | n_events | stop5 coef (standalone) | 95% CI_hi | BH rej? |
|---|---|---|---|---|---|
| pctile20 | deep | 4837 | -0.0155 | -0.0004 | YES |
| pctile20 | baskets | 14111 | -0.0358 | 0.0037 | no |
| relwin2 | deep | 4899 | -0.0149 | -0.0006 | YES |
| relwin2 | baskets | 14824 | -0.0325 | 0.0064 | no |
| volconf15 | deep | 5602 | -0.0118 | 0.0022 | no |
| volconf15 | baskets | 16926 | -0.0341 | 0.0053 | no |

### Sensitivity: pctile20

Config override vs defaults: `{'pctile_thresh': 20}`
Merged cfg: pctile_thresh=20, min_duration=5, release_window=3, vol_confirm=1.3

**Panel deep:**
- FIRED_UP onsets: 4837
  Effect table (standalone form, R1 FE):

  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |
  |---|---|---|---|---|---|
  | stop5 | -0.0155 | [-0.023, -0.000] * | 0.0440 | 0.0840 | YES |
  | fwd_mdd_21 | 0.0021 | [+0.000, +0.003] * | 0.0500 | 0.0933 | YES |
  | rotational_liftoff | -0.0147 | [-0.030, -0.005] * | 0.0160 | 0.0458 | YES |
  | positional_liftoff | -0.0043 | [-0.020, -0.001] * | 0.0340 | 0.0714 | YES |
  | dead_money | 0.0012 | [-0.001, +0.003] | 0.3840 | 0.4962 | no |
  | cushion_rot | -0.0117 | [-0.029, -0.004] * | 0.0180 | 0.0458 | YES |
  | zone_held_21 | -0.0192 | [-0.037, -0.015] * | 0.0000 | 0.0000 | YES |
  | stop_vol_21 | 0.0192 | [+0.015, +0.037] * | 0.0000 | — | no |
  | days_to_10 | 1.5858 | [+0.598, +3.175] * | 0.0100 | — | no |

**Panel baskets:**
- FIRED_UP onsets: 14111
  Effect table (standalone form, R1 FE):

  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |
  |---|---|---|---|---|---|
  | stop5 | -0.0358 | [-0.038, +0.004] | 0.1000 | 0.1714 | no |
  | fwd_mdd_21 | 0.0105 | [+0.001, +0.011] * | 0.0040 | 0.0160 | YES |
  | rotational_liftoff | -0.0246 | [-0.041, -0.010] * | 0.0040 | 0.0160 | YES |
  | positional_liftoff | 0.0021 | [-0.032, +0.006] | 0.7420 | 0.7791 | no |
  | dead_money | -0.0000 | [-0.000, +0.005] | 0.8280 | 0.8420 | no |
  | cushion_rot | -0.0180 | [-0.039, -0.008] * | 0.0000 | 0.0000 | YES |
  | zone_held_21 | -0.0222 | [-0.059, -0.016] * | 0.0020 | 0.0099 | YES |
  | stop_vol_21 | 0.0222 | [+0.016, +0.059] * | 0.0020 | — | no |
  | days_to_10 | 2.7827 | [+1.664, +5.337] * | 0.0140 | — | no |


### Sensitivity: relwin2

Config override vs defaults: `{'release_window': 2}`
Merged cfg: pctile_thresh=25, min_duration=5, release_window=2, vol_confirm=1.3

**Panel deep:**
- FIRED_UP onsets: 4899
  Effect table (standalone form, R1 FE):

  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |
  |---|---|---|---|---|---|
  | stop5 | -0.0149 | [-0.019, -0.001] * | 0.0400 | 0.0781 | YES |
  | fwd_mdd_21 | 0.0023 | [+0.000, +0.003] * | 0.0140 | 0.0436 | YES |
  | rotational_liftoff | -0.0143 | [-0.026, -0.005] * | 0.0060 | 0.0229 | YES |
  | positional_liftoff | -0.0083 | [-0.022, -0.004] * | 0.0080 | 0.0269 | YES |
  | dead_money | 0.0020 | [-0.000, +0.003] | 0.1080 | 0.1814 | no |
  | cushion_rot | -0.0084 | [-0.025, +0.000] | 0.0560 | 0.1023 | no |
  | zone_held_21 | -0.0175 | [-0.036, -0.015] * | 0.0000 | 0.0000 | YES |
  | stop_vol_21 | 0.0175 | [+0.015, +0.036] * | 0.0000 | — | no |
  | days_to_10 | 2.4972 | [+1.532, +3.683] * | 0.0000 | — | no |

**Panel baskets:**
- FIRED_UP onsets: 14824
  Effect table (standalone form, R1 FE):

  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |
  |---|---|---|---|---|---|
  | stop5 | -0.0325 | [-0.035, +0.006] | 0.1380 | 0.2108 | no |
  | fwd_mdd_21 | 0.0099 | [+0.002, +0.010] * | 0.0000 | 0.0000 | YES |
  | rotational_liftoff | -0.0271 | [-0.042, -0.004] * | 0.0240 | 0.0560 | YES |
  | positional_liftoff | 0.0012 | [-0.023, +0.017] | 0.6860 | 0.7294 | no |
  | dead_money | 0.0001 | [-0.000, +0.004] | 0.5060 | 0.6020 | no |
  | cushion_rot | -0.0205 | [-0.047, -0.014] * | 0.0040 | 0.0160 | YES |
  | zone_held_21 | -0.0168 | [-0.040, -0.007] * | 0.0040 | 0.0160 | YES |
  | stop_vol_21 | 0.0168 | [+0.007, +0.040] * | 0.0040 | — | no |
  | days_to_10 | 2.9020 | [+1.859, +6.029] * | 0.0000 | — | no |


### Sensitivity: volconf15

Config override vs defaults: `{'vol_confirm': 1.5}`
Merged cfg: pctile_thresh=25, min_duration=5, release_window=3, vol_confirm=1.5

**Panel deep:**
- FIRED_UP onsets: 5602
  Effect table (standalone form, R1 FE):

  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |
  |---|---|---|---|---|---|
  | stop5 | -0.0118 | [-0.016, +0.002] | 0.1260 | 0.1960 | no |
  | fwd_mdd_21 | 0.0021 | [+0.000, +0.002] * | 0.0280 | 0.0619 | YES |
  | rotational_liftoff | -0.0187 | [-0.031, -0.012] * | 0.0000 | 0.0000 | YES |
  | positional_liftoff | -0.0092 | [-0.021, -0.003] * | 0.0080 | 0.0269 | YES |
  | dead_money | 0.0021 | [-0.000, +0.004] | 0.0920 | 0.1610 | no |
  | cushion_rot | -0.0097 | [-0.026, -0.003] * | 0.0180 | 0.0458 | YES |
  | zone_held_21 | -0.0222 | [-0.040, -0.019] * | 0.0000 | 0.0000 | YES |
  | stop_vol_21 | 0.0222 | [+0.019, +0.040] * | 0.0000 | — | no |
  | days_to_10 | 2.3787 | [+1.656, +3.567] * | 0.0000 | — | no |

**Panel baskets:**
- FIRED_UP onsets: 16926
  Effect table (standalone form, R1 FE):

  | Outcome | Coef | 95% CI | p | BH q (family) | BH rej? |
  |---|---|---|---|---|---|
  | stop5 | -0.0341 | [-0.036, +0.005] | 0.1260 | 0.1960 | no |
  | fwd_mdd_21 | 0.0100 | [+0.002, +0.010] * | 0.0000 | 0.0000 | YES |
  | rotational_liftoff | -0.0246 | [-0.040, -0.005] * | 0.0220 | 0.0528 | YES |
  | positional_liftoff | 0.0022 | [-0.020, +0.015] | 0.5160 | 0.6020 | no |
  | dead_money | 0.0004 | [+0.000, +0.005] * | 0.0400 | 0.0781 | YES |
  | cushion_rot | -0.0182 | [-0.044, -0.008] * | 0.0180 | 0.0458 | YES |
  | zone_held_21 | -0.0180 | [-0.047, -0.014] * | 0.0000 | 0.0000 | YES |
  | stop_vol_21 | 0.0180 | [+0.014, +0.047] * | 0.0000 | — | no |
  | days_to_10 | 2.7549 | [+1.717, +5.596] * | 0.0000 | — | no |


## Per-Form Species Bar Summary (no cross-form cherry-picking)

Per masterplan §5: each form evaluated independently.
NO promotion decision made in this report (RUL-3).

### Species Bar: standalone (deep, defaults)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 5559 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=-0.0118 CI_hi=0.0022 | YES |
| Stop5 superiority (CI_hi < 0) | CI_hi=0.0022 | NO |
| Superiority CI-excl-0 on >=1 constitution axis | none | NO |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-SQ proxy (treatment-share-of-pool)=12.8% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 41.9% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0222 CI=[-0.0400,-0.0187] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; feeds no clause in this study; informs whether fixed −5% stop mismeasures high-vol washout entries.

### Species Bar: COILED-intersection (deep, defaults)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 461 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=0.0080 CI_hi=0.0450 | NO |
| Stop5 superiority (CI_hi < 0) | CI_hi=0.0450 | NO |
| Superiority CI-excl-0 on >=1 constitution axis | none | NO |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-SQ proxy (treatment-share-of-pool)=1.2% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 48.0% | YES |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0312 CI=[-0.0778,-0.0185] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; feeds no clause in this study; informs whether fixed −5% stop mismeasures high-vol washout entries.

### Species Bar: gatefire-proximity (deep, defaults)

| Clause | Value | Met? |
|---|---|---|
| n_events >= 150 | 2850 | YES |
| Stop5 non-inferiority (CI_hi < +0.01) | coef=-0.0192 CI_hi=-0.0050 | YES |
| Stop5 superiority (CI_hi < 0) | CI_hi=-0.0050 | YES |
| Superiority CI-excl-0 on >=1 constitution axis | ['stop5'] | YES |
| Era sign-stability (>=3/4 eras) | YES (>=3/4 eras) | YES |
| Recall clause (>= half COILED-FIRE recall) | S-SQ proxy (treatment-share-of-pool)=7.0% threshold=DEFERRED | DEFERRED |
| Independence clause (co-fire <= 60% at ±3 bars) | 81.6% | N/A (structurally gate-dependent: form defined by gate-fire proximity) |
| zone_held_21 (ADJUDICATION CONTEXT, no clause) | coef=-0.0005 CI=[-0.0162,0.0087] | — |

> **RECALL CLAUSE NOTE:** DEFERRED: COILED-FIRE recall requires full cycles.py pipeline per-fire. Cannot evaluate recall clause from this study alone. See W0_BASELINES.md DEFERRALS §COILED/COILED-FIRE Recall Recompute.

> **zone_held_21 NOTE (RUL-14):** zone_held_21 is the registered bar under the program constitution; feeds no clause in this study; informs whether fixed −5% stop mismeasures high-vol washout entries.

## Panel: deep

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS STAMP: absolute rates on surviving deep-panel names only. Comparisons within-era are directionally valid.

### Form: standalone

- Total FIRED_UP onsets: 5602
- Deduped episodes: 5602
- Gradable: 5559
- N treatment: 5559 | N control: 37722
- Recall (treatment / all): 12.8%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0118 | [-0.016, +0.002] | -0.0356 | 0.1260 | 0.1960 | no | 0.128 |
| fwd_mdd_21 | 0.0021 | [+0.000, +0.002] * * | 0.0063 | 0.0280 | 0.0619 | YES | 0.128 |
| rotational_liftoff | -0.0187 | [-0.031, -0.012] * * | -0.0531 | 0.0000 | 0.0000 | YES | 0.128 |
| positional_liftoff | -0.0092 | [-0.021, -0.003] * * | -0.0161 | 0.0080 | 0.0269 | YES | 0.128 |
| dead_money | 0.0021 | [-0.000, +0.004] | 0.0017 | 0.0920 | 0.1610 | no | 0.128 |
| cushion_rot | -0.0097 | [-0.026, -0.003] * * | -0.0394 | 0.0180 | 0.0458 | YES | 0.128 |
| zone_held_21 | -0.0222 | [-0.040, -0.019] * * | -0.0279 | 0.0000 | 0.0000 | YES | 0.128 |
| stop_vol_21 | 0.0222 | [+0.019, +0.040] * * | 0.0279 | 0.0000 | — | no | 0.128 |
| days_to_10 | 2.3787 | [+1.656, +3.567] * * | 5.4378 | 0.0000 | — | no | 0.128 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_ssq | panel | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean |
|---|---|---|---|---|---|---|---|---|
| pre_2012 | 0 | deep | 24280 | 13.1% | 26.5% | 34.5% | 0.3% | -0.0880 |
| pre_2012 | 1 | deep | 3497 | 9.2% | 21.1% | 33.1% | 0.5% | -0.0759 |
| 2012-2015 | 0 | deep | 3725 | 6.4% | 16.0% | 33.8% | 0.4% | -0.0625 |
| 2012-2015 | 1 | deep | 573 | 5.6% | 14.0% | 33.9% | 0.2% | -0.0572 |
| 2016-2019 | 0 | deep | 3715 | 7.5% | 18.6% | 33.0% | 0.2% | -0.0700 |
| 2016-2019 | 1 | deep | 617 | 3.7% | 15.1% | 32.9% | 0.5% | -0.0742 |
| 2020-2022 | 0 | deep | 2973 | 14.4% | 29.9% | 32.6% | 0.0% | -0.0968 |
| 2020-2022 | 1 | deep | 342 | 8.2% | 22.8% | 27.8% | 0.3% | -0.1036 |
| 2023-2026 | 0 | deep | 3029 | 9.8% | 25.7% | 35.8% | 0.0% | -0.0774 |
| 2023-2026 | 1 | deep | 530 | 7.9% | 21.1% | 31.9% | 0.4% | -0.0784 |

### Form: coiled

- Total FIRED_UP onsets: 467
- Deduped episodes: 467
- Gradable: 461
- N treatment: 461 | N control: 37722
- Recall (treatment / all): 1.2%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | 0.0080 | [-0.004, +0.045] | -0.0167 | 0.1460 | 0.2190 | no | 0.012 |
| fwd_mdd_21 | -0.0021 | [-0.007, -0.001] * * | -0.0021 | 0.0300 | 0.0646 | YES | 0.012 |
| rotational_liftoff | 0.0173 | [-0.019, +0.031] | 0.0315 | 0.5680 | 0.6448 | no | 0.012 |
| positional_liftoff | 0.0049 | [-0.060, +0.024] | 0.0288 | 0.3260 | 0.4489 | no | 0.012 |
| dead_money | 0.0015 | [-0.002, +0.009] | -0.0003 | 0.3060 | 0.4284 | no | 0.012 |
| cushion_rot | 0.0253 | [-0.029, +0.052] | 0.0326 | 0.6120 | 0.6742 | no | 0.012 |
| zone_held_21 | -0.0312 | [-0.078, -0.019] * * | -0.0385 | 0.0020 | 0.0099 | YES | 0.012 |
| stop_vol_21 | 0.0312 | [+0.019, +0.078] * * | 0.0385 | 0.0020 | — | no | 0.012 |
| days_to_10 | 0.4721 | [-1.492, +4.208] | -2.2262 | 0.2880 | — | no | 0.012 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_ssq | panel | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean |
|---|---|---|---|---|---|---|---|---|
| pre_2012 | 0 | deep | 24280 | 13.1% | 26.5% | 34.5% | 0.3% | -0.0880 |
| pre_2012 | 1 | deep | 337 | 11.9% | 29.1% | 34.1% | 0.3% | -0.0969 |
| 2012-2015 | 0 | deep | 3725 | 6.4% | 16.0% | 33.8% | 0.4% | -0.0625 |
| 2012-2015 | 1 | deep | 21 | 9.5% | 19.1% | 38.1% | 0.0% | -0.0678 |
| 2016-2019 | 0 | deep | 3715 | 7.5% | 18.6% | 33.0% | 0.2% | -0.0700 |
| 2016-2019 | 1 | deep | 29 | 0.0% | 13.8% | 37.9% | 0.0% | -0.0790 |
| 2020-2022 | 0 | deep | 2973 | 14.4% | 29.9% | 32.6% | 0.0% | -0.0968 |
| 2020-2022 | 1 | deep | 26 | 7.7% | 46.2% | 57.7% | 0.0% | -0.0846 |
| 2023-2026 | 0 | deep | 3029 | 9.8% | 25.7% | 35.8% | 0.0% | -0.0774 |
| 2023-2026 | 1 | deep | 48 | 2.1% | 20.8% | 43.8% | 0.0% | -0.0647 |

### Form: gatefire

- Total FIRED_UP onsets: 2874
- Deduped episodes: 2874
- Gradable: 2850
- N treatment: 2850 | N control: 37722
- Recall (treatment / all): 7.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0192 | [-0.025, -0.005] * * | -0.0503 | 0.0120 | 0.0388 | YES | 0.070 |
| fwd_mdd_21 | 0.0051 | [+0.003, +0.006] * * | 0.0100 | 0.0000 | 0.0000 | YES | 0.070 |
| rotational_liftoff | 0.0025 | [-0.012, +0.015] | -0.0330 | 0.9720 | 0.9720 | no | 0.070 |
| positional_liftoff | 0.0087 | [-0.007, +0.022] | 0.0112 | 0.3460 | 0.4640 | no | 0.070 |
| dead_money | 0.0011 | [-0.001, +0.003] | 0.0004 | 0.2900 | 0.4200 | no | 0.070 |
| cushion_rot | 0.0092 | [-0.010, +0.021] | -0.0131 | 0.4280 | 0.5287 | no | 0.070 |
| zone_held_21 | -0.0005 | [-0.016, +0.009] | -0.0041 | 0.6860 | 0.7294 | no | 0.070 |
| stop_vol_21 | 0.0005 | [-0.009, +0.016] | 0.0041 | 0.6860 | — | no | 0.070 |
| days_to_10 | 0.5218 | [-0.603, +2.798] | 3.6096 | 0.1940 | — | no | 0.070 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_ssq | panel | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean |
|---|---|---|---|---|---|---|---|---|
| pre_2012 | 0 | deep | 24280 | 13.1% | 26.5% | 34.5% | 0.3% | -0.0880 |
| pre_2012 | 1 | deep | 1832 | 7.9% | 22.4% | 35.8% | 0.3% | -0.0715 |
| 2012-2015 | 0 | deep | 3725 | 6.4% | 16.0% | 33.8% | 0.4% | -0.0625 |
| 2012-2015 | 1 | deep | 277 | 3.2% | 17.0% | 38.6% | 0.0% | -0.0525 |
| 2016-2019 | 0 | deep | 3715 | 7.5% | 18.6% | 33.0% | 0.2% | -0.0700 |
| 2016-2019 | 1 | deep | 297 | 3.7% | 15.2% | 33.7% | 1.0% | -0.0721 |
| 2020-2022 | 0 | deep | 2973 | 14.4% | 29.9% | 32.6% | 0.0% | -0.0968 |
| 2020-2022 | 1 | deep | 178 | 3.4% | 27.0% | 37.1% | 0.0% | -0.0870 |
| 2023-2026 | 0 | deep | 3029 | 9.8% | 25.7% | 35.8% | 0.0% | -0.0774 |
| 2023-2026 | 1 | deep | 266 | 6.4% | 24.1% | 29.3% | 0.4% | -0.0772 |

#### NC-2 Marginality (gatefire-proximity form only)

Proximity confounding test: NC-2 proximity-band FE added to stop5 R1 model.
- stop5 coef with NC-2 band FE: -0.0186 CI=[-0.0240, -0.0031] CI-excl-0: YES *
- N treatment with computable proximity: 2850
- Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 2850/2850; N control = 37722.

## Panel: baskets

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS STAMP: absolute rates on surviving baskets-panel names only. Comparisons within-era are directionally valid.

### Form: standalone

- Total FIRED_UP onsets: 16926
- Deduped episodes: 16926
- Gradable: 16003
- N treatment: 16003 | N control: 107127
- Recall (treatment / all): 13.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0341 | [-0.036, +0.005] | -0.0241 | 0.1260 | 0.1960 | no | 0.130 |
| fwd_mdd_21 | 0.0100 | [+0.002, +0.010] * * | 0.0044 | 0.0000 | 0.0000 | YES | 0.130 |
| rotational_liftoff | -0.0246 | [-0.040, -0.005] * * | -0.0336 | 0.0220 | 0.0528 | YES | 0.130 |
| positional_liftoff | 0.0022 | [-0.020, +0.015] | -0.0147 | 0.5160 | 0.6020 | no | 0.130 |
| dead_money | 0.0004 | [+0.000, +0.005] * * | 0.0010 | 0.0400 | 0.0781 | YES | 0.130 |
| cushion_rot | -0.0182 | [-0.044, -0.008] * * | -0.0333 | 0.0180 | 0.0458 | YES | 0.130 |
| zone_held_21 | -0.0180 | [-0.047, -0.014] * * | -0.0449 | 0.0000 | 0.0000 | YES | 0.130 |
| stop_vol_21 | 0.0180 | [+0.014, +0.047] * * | 0.0449 | 0.0000 | — | no | 0.130 |
| days_to_10 | 2.7549 | [+1.717, +5.596] * * | 2.5335 | 0.0000 | — | no | 0.130 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_ssq | panel | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean |
|---|---|---|---|---|---|---|---|---|
| 2012-2015 | 0 | baskets | 10880 | 16.0% | 22.0% | 24.1% | 0.5% | -0.1167 |
| 2012-2015 | 1 | baskets | 1162 | 16.3% | 19.4% | 22.3% | 0.3% | -0.1120 |
| 2016-2019 | 0 | baskets | 33191 | 14.3% | 26.7% | 32.9% | 0.3% | -0.1054 |
| 2016-2019 | 1 | baskets | 5570 | 12.1% | 23.1% | 31.3% | 0.4% | -0.1091 |
| 2020-2022 | 0 | baskets | 29794 | 26.1% | 33.0% | 29.7% | 0.3% | -0.1449 |
| 2020-2022 | 1 | baskets | 4001 | 20.5% | 28.7% | 27.8% | 0.4% | -0.1419 |
| 2023-2026 | 0 | baskets | 33262 | 21.4% | 33.4% | 33.2% | 0.1% | -0.1302 |
| 2023-2026 | 1 | baskets | 5270 | 21.3% | 30.6% | 31.2% | 0.2% | -0.1267 |

### Form: coiled

- Total FIRED_UP onsets: 272
- Deduped episodes: 272
- Gradable: 257
- N treatment: 257 | N control: 107127
- Recall (treatment / all): 0.2%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.1191 | [-0.160, +0.051] | -0.1014 | 0.3620 | 0.4751 | no | 0.002 |
| fwd_mdd_21 | 0.0329 | [-0.011, +0.042] | 0.0234 | 0.5600 | 0.6444 | no | 0.002 |
| rotational_liftoff | -0.0544 | [-0.106, +0.066] | -0.0339 | 0.3480 | 0.4640 | no | 0.002 |
| positional_liftoff | 0.0300 | [-0.077, +0.078] | 0.0330 | 0.8320 | 0.8420 | no | 0.002 |
| dead_money | -0.0049 | [-0.007, +0.000] | -0.0025 | 0.4280 | 0.5287 | no | 0.002 |
| cushion_rot | -0.0192 | [-0.094, +0.052] | -0.0042 | 0.6040 | 0.6742 | no | 0.002 |
| zone_held_21 | 0.0394 | [-0.102, +0.101] | 0.0029 | 0.8240 | 0.8420 | no | 0.002 |
| stop_vol_21 | -0.0394 | [-0.101, +0.102] | -0.0029 | 0.8240 | — | no | 0.002 |
| days_to_10 | 9.2647 | [-2.480, +15.020] | 4.8408 | 0.1240 | — | no | 0.002 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_ssq | panel | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean |
|---|---|---|---|---|---|---|---|---|
| 2012-2015 | 0 | baskets | 10880 | 16.0% | 22.0% | 24.1% | 0.5% | -0.1167 |
| 2012-2015 | 1 | baskets | 12 | 16.7% | 16.7% | 25.0% | 0.0% | -0.1457 |
| 2016-2019 | 0 | baskets | 33191 | 14.3% | 26.7% | 32.9% | 0.3% | -0.1054 |
| 2016-2019 | 1 | baskets | 66 | 1.5% | 27.3% | 40.9% | 0.0% | -0.0628 |
| 2020-2022 | 0 | baskets | 29794 | 26.1% | 33.0% | 29.7% | 0.3% | -0.1449 |
| 2020-2022 | 1 | baskets | 70 | 14.3% | 34.3% | 41.4% | 0.0% | -0.0799 |
| 2023-2026 | 0 | baskets | 33262 | 21.4% | 33.4% | 33.2% | 0.1% | -0.1302 |
| 2023-2026 | 1 | baskets | 109 | 11.0% | 22.0% | 27.5% | 0.0% | -0.0868 |

### Form: gatefire

- Total FIRED_UP onsets: 8563
- Deduped episodes: 8563
- Gradable: 8047
- N treatment: 8047 | N control: 107127
- Recall (treatment / all): 7.0%

#### Effect Table (R1 FE, fast block bootstrap)

**zone_held_21:** vol-scaled band held over fill+1..+21. ADJUDICATION CONTEXT — feeds no clause; informs whether fixed −5% stop mismeasures high-vol washout entries (RUL-14 rationale).

| Outcome | Coef | 95% CI | Naive diff | p | BH q (family) | BH rej (family)? | Recall |
|---|---|---|---|---|---|---|---|
| stop5 | -0.0568 | [-0.059, -0.012] * * | -0.0454 | 0.0020 | 0.0099 | YES | 0.070 |
| fwd_mdd_21 | 0.0135 | [+0.003, +0.014] * * | 0.0078 | 0.0020 | 0.0099 | YES | 0.070 |
| rotational_liftoff | -0.0113 | [-0.032, +0.012] | -0.0102 | 0.2260 | 0.3331 | no | 0.070 |
| positional_liftoff | 0.0135 | [-0.022, +0.025] | 0.0056 | 0.2960 | 0.4214 | no | 0.070 |
| dead_money | -0.0007 | [-0.001, +0.004] | 0.0005 | 0.6180 | 0.6742 | no | 0.070 |
| cushion_rot | 0.0042 | [-0.023, +0.025] | -0.0002 | 0.3940 | 0.5015 | no | 0.070 |
| zone_held_21 | 0.0072 | [-0.037, +0.018] | -0.0162 | 0.4480 | 0.5454 | no | 0.070 |
| stop_vol_21 | -0.0072 | [-0.018, +0.037] | 0.0162 | 0.4480 | — | no | 0.070 |
| days_to_10 | 2.5851 | [+1.500, +6.787] * * | 1.5815 | 0.0060 | — | no | 0.070 |

#### Era table (stop5 rate by stratum, program eras)
Era sign-stability clause: **YES (>=3/4 eras sign-stable)**

| era | _is_ssq | panel | n_fires | stop5_rate | rot_liftoff_rate | pos_liftoff_rate | dead_money_rate | mae63_mean |
|---|---|---|---|---|---|---|---|---|
| 2012-2015 | 0 | baskets | 10880 | 16.0% | 22.0% | 24.1% | 0.5% | -0.1167 |
| 2012-2015 | 1 | baskets | 506 | 13.4% | 20.9% | 23.3% | 0.8% | -0.1109 |
| 2016-2019 | 0 | baskets | 33191 | 14.3% | 26.7% | 32.9% | 0.3% | -0.1054 |
| 2016-2019 | 1 | baskets | 2697 | 10.4% | 25.0% | 33.3% | 0.4% | -0.1061 |
| 2020-2022 | 0 | baskets | 29794 | 26.1% | 33.0% | 29.7% | 0.3% | -0.1449 |
| 2020-2022 | 1 | baskets | 2027 | 17.1% | 31.5% | 31.5% | 0.2% | -0.1331 |
| 2023-2026 | 0 | baskets | 33262 | 21.4% | 33.4% | 33.2% | 0.1% | -0.1302 |
| 2023-2026 | 1 | baskets | 2817 | 19.5% | 32.6% | 32.3% | 0.2% | -0.1249 |

#### NC-2 Marginality (gatefire-proximity form only)

Proximity confounding test: NC-2 proximity-band FE added to stop5 R1 model.
- stop5 coef with NC-2 band FE: -0.0583 CI=[-0.0607, -0.0022] CI-excl-0: YES *
- N treatment with computable proximity: 8047
- Note: NC-2 band FE: proximity proxy = 63-bar close-min pivot (PROXY, not true cand_price/dcl_price). Bands computed for BOTH treatment and control arms (fix: prior version assigned bands to treatment only — degenerate coef=0.0). N treatment with computable proximity = 8047/8047; N control = 107127.


---

*Generated by `scripts/research/run_w2_ssq.py`*
*Species: S16 — Squeeze Release*
*Grader: engine/grading.py (program barriers, RUL-9).*
*'validated' word deliberately absent (CI-enforced).*
*No promotion language. Studies only.*
---

## F3 Kill-Line Assessment (Masterplan §3 F3)

**Kill line (verbatim from masterplan §3 F3):** "if FIRED_UP co-fires >60% within ±3 bars of gate fires, it is not independent — demote to chip candidate at most."

**Kill-line threshold:** co-fire share > 60% within ±3 trading bars of gate fires → DEMOTED to chip-candidate at most.

| Form | Co-fire share | Kill-line threshold | Kill-line result |
|---|---|---|---|
| standalone | 41.9% | <= 60% | **PASSES** (NOT demoted) |
| COILED-intersection | 48.0% | <= 60% | **PASSES** (NOT demoted) |
| gatefire-proximity | 81.6% | N/A-STRUCTURAL | N/A (structurally gate-dependent by form definition) |

**Kill-line verdict:** F3 KILL LINE NOT TRIGGERED. Neither the standalone (41.9%) nor the COILED-intersection (48.0%) form crosses the 60% demote threshold. S16 retains its SPECIES deployment lane classification (not demoted to chip-candidate).

> Note: The gatefire-proximity form's 81.6% co-fire is definitionally expected (the form is DEFINED as events within ±5 bars of gate fires — a ±3-bar co-fire check would always be high for this form). This is structurally N/A per the same reasoning applied in S-UR.

---

## DT-R14 Time-Controlled Recomputation (Mandatory Robustness Pass)

**DT-R14 ruling (verbatim):** 'The 12 declared trials stand as registered (family esx_sq_phase0, budget=12, declared pre-DT-R14). A time-controlled recomputation of the same cells (within-month demeaning of outcomes or month-block bootstrap over fire months) is a MANDATORY robustness pass, not new trials. Verdict may be PASS only where both bases agree; disagreement → DEFER with both printed.'

**Scope:** deep panel, standalone form, defaults cfg, outcome=stop5.
**Budget status:** NOT CHARGED (mandatory robustness pass, not a new trial).
**Control arm:** gate_fires_deep.parquet (same as primary analysis). 5602 treatment + 38250 control, combined for grading.

> **R1 clustering note (Opus review):** data/research/sector_map.csv was absent in the run environment; R1 sector clustering degraded to date-only for the DT-R14 recomputation. Acceptable for phase0; flagged by review.

### Reference: Primary Analysis Result

| Method | stop5 coef | 95% CI | CI_hi | Non-inferior (CI_hi<+0.01)? |
|---|---|---|---|---|
| Primary (R1 date-FE, episode-block bootstrap) | -0.0118 | [-0.016, +0.0022] | 0.0022 | YES |

### DT-R14 Method 1: Month-Block Bootstrap (F2-corrected demeaned estimand)

**Resampling unit:** calendar month of fire date. Months sampled WITH REPLACEMENT.
**F2 fix (Opus review 2026-07-07):** The prior Method 1 computed a naive mean difference treat.mean() - ctrl.mean() inside the month-block resample — this is NOT a time control; it conflates calendar-time confounds with the treatment effect. Corrected: within-month demeaning applied BEFORE the bootstrap resample — stop5_demeaned = stop5 minus monthly mean (pooled treatment + control). Each bootstrap iteration now estimates the demeaned contrast (parallel to Method 2 / OLS with month FE). Result lands near the date-FE estimate (-0.0118) and Method 2 demeaned coefficient (-0.0125), not the naive raw difference (-0.0369 before fix).
**Bootstrap resamples:** 500

| Metric | Value |
|---|---|
| Unique fire months | 761 |
| Valid bootstrap iterations | 500 |
| N treatment | 5559 |
| N control | 37722 |
| Point estimate (mean diff, demeaned) | -0.0125 |
| 95% CI lower | -0.0196 |
| 95% CI upper (CI_hi) | -0.0047 |
| CI excludes 0? | YES |
| Non-inferior (CI_hi < +0.01)? | **YES** |

### DT-R14 Method 2: Within-Month Outcome Demeaning

**Method:** Subtract monthly mean stop5 (pooled treatment + control) from each observation. OLS of demeaned stop5 on _is_ssq with HC3 sandwich SEs (numpy/scipy). Month effects absorbed by demeaning.

| Metric | Value |
|---|---|
| Unique fire months | 761 |
| N treatment | 5559 |
| N control | 37722 |
| OLS coef (_is_ssq) | -0.0125 |
| 95% CI | [-0.0200, -0.0050] |
| p-value | 0.0011 |
| CI excludes 0? | YES |
| Non-inferior (CI_hi < +0.01)? | **YES** |

### DT-R14 Agreement Assessment

| Basis | Non-inferior? | CI_hi |
|---|---|---|
| Primary (R1 date-FE, episode-block bootstrap) | YES | +0.0022 |
| Month-block bootstrap (F2-corrected demeaned) | YES | -0.0047 |
| Within-month demeaning (OLS HC3) | YES | -0.0050 |

**DT-R14 VERDICT: PASS — all three bases agree NON-INFERIOR. CI_hi < +0.01 in all three bases.**

> DT-R14 rule: 'Verdict may be PASS only where both bases agree; disagreement → DEFER with both printed.' Results above are printed with both bases as required regardless of outcome.

> Implementation note (F2-corrected): Month-block bootstrap now applies within-month demeaning BEFORE each bootstrap resample so the estimated contrast is the date-FE-corrected contrast, not the naive raw difference. Within-month demeaning OLS used HC3 sandwich SEs (numpy/scipy; not statsmodels). Both methods are mechanically distinct from the primary analysis episodic-block bootstrap and from each other.

---

## Adjudication Chain (Opus Review 2026-07-07)

**Review verdict:** Opus review 2026-07-07: merge CLEAN-WITH-FIXES (applied); N/A-STRUCTURAL gatefire exemption RATIFIED by Fable for S16 (co-fire definitionally ~100% for the gate-adjacent form; independence-bearing forms standalone 41.9% / COILED 48.0% both pass); phase0→accruing sign-off CONDITIONAL-APPROVED.

**Fixes applied per review (this PR):**
1. F-REG: Rebased esx/ssq onto fresh origin/main; data/species/registry.json = main's current state + S16 only (S11=falsified preserved, T1-T4 HTF note preserved).
2. Item 5: data/experiments/registry_seed.json diff = S16 addition only (species-S15, species-F3_ANTICHASE, species-EI-F1D-RW stripped).
3. F2 (MAJOR): scripts/research/dt_r14_time_control.py Method 1 corrected from naive mean difference to within-month demeaned estimand. Corrected CI_hi=-0.0047 (vs naive -0.0258 before fix; expected near date-FE -0.0118/demeaned -0.0125 — confirmed).
4. Minor: sector_map.csv absence note added (R1 clustering degraded to date-only; acceptable for phase0).

**S16 phase0→accruing transition:**
All three CI_hi < +0.01 (primary +0.0022, Method 1 corrected -0.0047, Method 2 -0.0050). Per CONDITIONAL-APPROVED sign-off, S16 transitioned from phase0 to accruing via `engine/species_registry.transition_validation_status()`. Lifecycle log entry written to data/species/registry.json (reviewer: Opus (review) + Fable (sign-off) 2026-07-07).

