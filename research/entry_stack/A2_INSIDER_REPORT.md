# A2 W2a — esx_insider_sponsor Phase-0 Study Report

**Family:** `esx_insider_sponsor` (budget declared: 12 / consumed: 10 / reserve: 2)
**Status:** Phase-0 study report only — no promotion, no product change (RUL-4).
**Amendment:** Entry-Stack Expansion Amendment 2 (A2 RUL-26).
**Date:** 2026-07-05

**Reserve consumption (2026-07-05):** trials I1w x2 (deep, baskets) were registered from the family reserve AFTER the initial 8-trial read, motivated by the washout confound in I1 (its control pool includes non-washout fires, so the I1 contrast conflates the washout state with the cluster itself). The I1w mask restricts both arms to washed-out computable fires; the stratum isolates the cluster's marginal effect. Post-initial-read registration is stamped here for trial-ledger transparency; BH q<=0.10 is applied across ALL 10 consumed trials.

**CHIP PROMOTION IMPOSSIBLE THIS WAVE:** NC-2 eq_band remains DEFERRED (A2 §C3).
Results are printed, verdict section states the NC-2 incompleteness explicitly.

---

## Adjacency Citation (R2 — RUL-2)

**Primary prior:** `research/INSIDER_FACTOR.md` §6 — binding verdict:
> 'Ship as an ORTHOGONAL conviction/confirmer leg, expressed LONG-ONLY. NOT a standalone dollar-neutral alpha sizer. The L/S fails DSR outright.'

This study tests whether fire-conditioned insider cluster patterns improve
stop5 (primary) and mae21 (co-primary) outcomes at 21d under the program
grader. It is a confirmer-entry study, not a standalone alpha claim.

**Secondary prior:** SUE-insider NEUTRAL study (from INSIDER_FACTOR.md §5
and ENTRY_STACK_EXPANSION_AMENDMENT2_BY_FABLE.md §A): SUE deep-PIT IC 0.038→0.0006
(HAC t 0.06, demoted to display). Repair-layer is hostile — insider cluster
conditioned on price washout (not earnings) may be mechanically distinct.

**Known-date law (A2 RUL-23, frozen):** `filing_date` is the known_date for
all I1/I2/I3 forms. The ≤2-business-day legal trade→file lag is the only
look-ahead risk; all windows are trading-day arithmetic (v1.1 fix).
ins_cluster_post15 (pit_at_entry=False) is EXCLUDED as a stratum.

---

## NC Yardstick (RUL-3) — First Table

> Per §10 RUL-3: null-competitors appear as the FIRST table in every
> subsequent W1/W2 report. Source: research/entry_stack/W1_NC_REPORT.md.
> Note which CIs are marked [proxy] or [low-block caveat].

## YARDSTICK — Reference Numbers for Every Later W1/W2 Report (RUL-3)

Per §10 RUL-3: null-competitors appear as the FIRST table in every
subsequent W1/W2 report. A candidate 'beats the null-competitors' when its
stratum FE coefficients clear the bar below with CI excluding 0, AND at
better or equal recall. Direction note: stop5 is an adverse outcome —
a BETTER signal has a MORE NEGATIVE stop5 coefficient (fewer stops); a
candidate must be more negative on stop5 (not merely numerically larger).
For beneficial outcomes (rotational_liftoff, positional_liftoff) the
candidate must have a higher (more positive) coefficient. The full NC-2
marginality test (coefficient survives entry_quality-band FE) remains
DEFERRED (cycles.py pipeline required).

### CI caveat (RUL-7 freeze, 2026-07-05):
At n≥400/arm with baseline stop5 ~12%, difference-SE ≈ 2.3pp. A bare 2pp
point-estimate rarely clears CI-excluding-0 at minimum n. The CI-excluding-0
clause is the operative promotion bar — not the 2pp level alone.

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | N blocks | N treat | N ctrl | Recall (treat arm) |
|---|---|---|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | -0.0019 | [-0.016, +0.008] | no | 8597 | 33,604 | 4,118 | 89.1% |
| deep | NC-1B (ticks=0) | 0.0001 | [-0.015, +0.007] | no | 8597 | 34,250 | 3,472 | 90.8% |
| deep | NC-2 (prox top-tercile) | -0.0427 | [-0.044, -0.031] * | YES * | 8597 | 12,585 | 25,137 | 33.4% |
| baskets | NC-1A (T1-only) | -0.0036 | [-0.011, +0.006] | no | 266 | 92,021 | 15,106 | 85.9% |
| baskets | NC-1B (ticks=0) | 0.0099 | [+0.002, +0.015] * | YES * | 266 | 97,353 | 9,774 | 90.9% |
| baskets | NC-2 (prox top-tercile) | -0.1012 | [-0.108, -0.096] * | YES * | 266 | 36,391 | 70,736 | 34.0% |

**Reading the yardstick:**
- CI excl 0 = YES: the block-bootstrap 95% CI excludes zero — stratum effect
  distinguishable from no-effect at this sample size.
- CI excl 0 = no: NULL result for that NC stratum — simple subsetting does NOT
  already buy distinguishable asymmetry improvement. A null NC is informative:
  it means new signals have room to add genuine value beyond tier/freshness.
- Later reports must show their candidate's stop5 coef + CI alongside this table.
- N blocks column shows real block counts after bug fixes (1)+(2). Low block counts are flagged with [low-block caveat] inline.

### Null result declaration (mandatory per masterplan §5):
Any NC with CI-including-0 is a NULL — printed here, not hidden.
A NULL means that simple subsetting CANNOT already buy the improvement.
This does NOT mean the full gate is unimportant — only that tier/ticks
subsetting alone is insufficient as a proxy for a new signal.

---

*Generated by `scripts/research/run_w1_nc.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*'validated' word deliberately absent (CI-enforced).*
*No promotion language. Studies only.*

---

## Study Design

**Estimator:** module-level `r1_estimate` (entry_strata_phase0.py) with
`computable_mask`. This path includes mae21 (co-primary, A2 RUL-20),
zone_held_21/stop_vol_21 (RUL-14), and state_rot in EFFECT_OUTCOMES.

**Contrast:** stratum-vs-computable-rest. Treatment = sensor fired within
the computable universe; control = computable-but-silent. Out-of-mask
fires dropped, not zero-coded (A2 §C2 — S7 same-computable-subset discipline).

**Grading:** ONCE per panel (T+1 fill, RUL-9) on the full fire set with
all insider extra_columns attached. All strata run on the same graded frame.

**Era tables:** 2012-2015, 2016-2019, 2020-2022, 2023-2026.

**BH correction:** q≤0.10 within-family across all 10 consumed trials — 8 initial + 2 reserve (stop5 primary).

**Trial registration:**
- Budget declared: 12 | Consumed: 10 | Reserve: 2
- 10 trials = {I1, I1-sens, I2, I3} × 2 panels (initial 8) + I1w reserve × 2 panels

| Trial | Stratum col | Computable mask | Definition |
|---|---|---|---|
| I1 | `ins_cluster_washout` | `ins_computable` | I1: cluster≥2 post-washout |
| I1-sens | `ins_cluster_washout_3` | `ins_computable` | I1-sens: cluster≥3 post-washout |
| I2 | `ins_cluster_pre20` | `ins_computable` | I2: cluster≥2 near-fire (20td) |
| I3 | `ins_netusd_mcap_sn_p80` | `ins_i3_computable` | I3: net_usd/mcap SN p≥80 |
| I1w | `ins_cluster_washout` | `ins_computable_washout` | I1w (RESERVE): cluster≥2 vs washout-alone (within-washout) |

---

## Panel: DEEP

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only.
Within-arm comparisons are directionally valid.

- Total fires loaded: 38,250
- Gradable fires: 37,722

### I1: I1: cluster≥2 post-washout

- Stratum column: `ins_cluster_washout`
- Computable mask: `ins_computable`
- Computable-gradable fires: 17,195
- N treatment (stratum=1): 358
- N control (computable-silent): 16,837
- N blocks: 3,456
- **Recall (stratum coverage): 2.1%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 17,195 | N estimation sample: shown in n_treatment + n_control | N blocks: 3,456
FE: `date` | Sector fallback to date-only blocks: no

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0543 | [0.0176, 0.0896] * | 0.1425 | 0.0080 | 0.0114 | 0.0133 | — | YES |
| mae21 | -0.0143 | [-0.0202, -0.0088] * | -0.0310 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | -0.0358 | [-0.0877, -0.0111] * | -0.0454 | 0.0120 | 0.0133 | — | — | YES |
| stop_vol_21 | 0.0358 | [0.0111, 0.0877] * | 0.0454 | 0.0120 | 0.0133 | — | — | YES |
| rotational_liftoff | 0.0649 | [0.0240, 0.1060] * | 0.1166 | 0.0000 | 0.0000 | — | — | YES |
| positional_liftoff | 0.0057 | [-0.0283, 0.0540] | 0.0072 | 0.4840 | 0.4840 | — | — | no |
| dead_money | -0.0034 | [-0.0077, -0.0005] * | -0.0025 | 0.0080 | 0.0114 | — | — | YES |
| cushion_rot | 0.0535 | [0.0146, 0.0875] * | 0.0904 | 0.0080 | 0.0114 | — | — | YES |
| mae63 | -0.0238 | [-0.0327, -0.0131] * | -0.0457 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0499 | [0.0298, 0.0694] * | 0.0976 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I1 deep)

| era | ins_cluster_washout | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 3352 | 6.3% | -0.0621 |
| 2012-2015 | 1.0 | 30 | 26.7% | -0.1253 |
| 2016-2019 | 0.0 | 3368 | 7.5% | -0.0694 |
| 2016-2019 | 1.0 | 71 | 9.9% | -0.0947 |
| 2020-2022 | 0.0 | 2725 | 13.9% | -0.0959 |
| 2020-2022 | 1.0 | 83 | 25.3% | -0.1007 |
| 2023-2026 | 0.0 | 2875 | 10.0% | -0.0774 |
| 2023-2026 | 1.0 | 44 | 4.5% | -0.0998 |

### I1-sens: I1-sens: cluster≥3 post-washout

- Stratum column: `ins_cluster_washout_3`
- Computable mask: `ins_computable`
- Computable-gradable fires: 17,195
- N treatment (stratum=1): 171
- N control (computable-silent): 17,024
- N blocks: 3,456
- **Recall (stratum coverage): 1.0%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 17,195 | N estimation sample: shown in n_treatment + n_control | N blocks: 3,456
FE: `date` | Sector fallback to date-only blocks: no

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0329 | [-0.0365, 0.0664] | 0.1174 | 0.5280 | 0.5280 | 0.5867 | — | no |
| mae21 | -0.0160 | [-0.0221, -0.0049] * | -0.0286 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | -0.0635 | [-0.1199, -0.0057] * | -0.0570 | 0.0320 | 0.0457 | — | — | YES |
| stop_vol_21 | 0.0635 | [0.0057, 0.1199] * | 0.0570 | 0.0320 | 0.0457 | — | — | YES |
| rotational_liftoff | 0.1008 | [0.0389, 0.1503] * | 0.1697 | 0.0000 | 0.0000 | — | — | YES |
| positional_liftoff | 0.0209 | [-0.0143, 0.0983] | 0.0674 | 0.1440 | 0.1800 | — | — | no |
| dead_money | -0.0029 | [-0.0117, 0.0000] | -0.0025 | 0.2200 | 0.2444 | — | — | no |
| cushion_rot | 0.0651 | [0.0037, 0.1143] * | 0.1245 | 0.0320 | 0.0457 | — | — | YES |
| mae63 | -0.0307 | [-0.0411, -0.0104] * | -0.0451 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0558 | [0.0289, 0.0940] * | 0.1264 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I1-sens deep)

| era | ins_cluster_washout_3 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 3370 | 6.4% | -0.0622 |
| 2012-2015 | 1.0 | 12 | 33.3% | -0.1780 |
| 2016-2019 | 0.0 | 3401 | 7.6% | -0.0695 |
| 2016-2019 | 1.0 | 38 | 2.6% | -0.1063 |
| 2020-2022 | 0.0 | 2772 | 14.2% | -0.0961 |
| 2020-2022 | 1.0 | 36 | 22.2% | -0.0934 |
| 2023-2026 | 0.0 | 2897 | 9.9% | -0.0775 |
| 2023-2026 | 1.0 | 22 | 9.1% | -0.1019 |

### I2: I2: cluster≥2 near-fire (20td)

- Stratum column: `ins_cluster_pre20`
- Computable mask: `ins_computable`
- Computable-gradable fires: 17,195
- N treatment (stratum=1): 306
- N control (computable-silent): 16,889
- N blocks: 3,456
- **Recall (stratum coverage): 1.8%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 17,195 | N estimation sample: shown in n_treatment + n_control | N blocks: 3,456
FE: `date` | Sector fallback to date-only blocks: no

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0228 | [-0.0088, 0.0627] | 0.0858 | 0.1400 | 0.2057 | 0.2000 | — | no |
| mae21 | -0.0053 | [-0.0126, 0.0004] | -0.0199 | 0.0720 | 0.1440 | — | 0.0800 | no |
| zone_held_21 | -0.0068 | [-0.0589, 0.0290] | -0.0431 | 0.6320 | 0.7022 | — | — | no |
| stop_vol_21 | 0.0068 | [-0.0290, 0.0589] | 0.0431 | 0.6320 | 0.7022 | — | — | no |
| rotational_liftoff | 0.0423 | [-0.0013, 0.0841] | 0.0516 | 0.0600 | 0.1440 | — | — | no |
| positional_liftoff | 0.0264 | [-0.0155, 0.0826] | -0.0009 | 0.1440 | 0.2057 | — | — | no |
| dead_money | -0.0023 | [-0.0069, -0.0002] * | -0.0025 | 0.0360 | 0.1200 | — | — | no |
| cushion_rot | -0.0063 | [-0.0496, 0.0452] | -0.0078 | 0.8640 | 0.8640 | — | — | no |
| mae63 | -0.0120 | [-0.0211, -0.0023] * | -0.0349 | 0.0160 | 0.0800 | — | — | YES |
| mfe63 | 0.0332 | [0.0148, 0.0549] * | 0.0452 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I2 deep)

| era | ins_cluster_pre20 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 3349 | 6.3% | -0.0622 |
| 2012-2015 | 1.0 | 33 | 21.2% | -0.1003 |
| 2016-2019 | 0.0 | 3373 | 7.6% | -0.0696 |
| 2016-2019 | 1.0 | 66 | 6.1% | -0.0834 |
| 2020-2022 | 0.0 | 2749 | 14.2% | -0.0958 |
| 2020-2022 | 1.0 | 59 | 18.6% | -0.1077 |
| 2023-2026 | 0.0 | 2883 | 9.9% | -0.0772 |
| 2023-2026 | 1.0 | 36 | 11.1% | -0.1200 |

### I3: I3: net_usd/mcap SN p≥80

- Stratum column: `ins_netusd_mcap_sn_p80`
- Computable mask: `ins_i3_computable`
- Computable-gradable fires: 17,197
- N treatment (stratum=1): 1,379
- N control (computable-silent): 15,818
- N blocks: 3,457
- **Recall (stratum coverage): 8.0%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 17,197 | N estimation sample: shown in n_treatment + n_control | N blocks: 3,457
FE: `date` | Sector fallback to date-only blocks: no

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0292 | [0.0117, 0.0420] * | 0.0440 | 0.0000 | 0.0000 | 0.0000 | — | YES |
| mae21 | -0.0069 | [-0.0098, -0.0039] * | -0.0108 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | 0.0075 | [-0.0111, 0.0278] | -0.0038 | 0.4640 | 0.5156 | — | — | no |
| stop_vol_21 | -0.0075 | [-0.0278, 0.0111] | 0.0038 | 0.4640 | 0.5156 | — | — | no |
| rotational_liftoff | -0.0054 | [-0.0260, 0.0192] | 0.0286 | 0.6520 | 0.6520 | — | — | no |
| positional_liftoff | -0.0282 | [-0.0429, 0.0031] | -0.0114 | 0.1240 | 0.2067 | — | — | no |
| dead_money | -0.0020 | [-0.0039, -0.0008] * | -0.0019 | 0.0000 | 0.0000 | — | — | YES |
| cushion_rot | -0.0139 | [-0.0338, 0.0118] | 0.0143 | 0.3840 | 0.5156 | — | — | no |
| mae63 | -0.0096 | [-0.0138, -0.0053] * | -0.0158 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0215 | [0.0149, 0.0316] * | 0.0310 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I3 deep)

| era | ins_netusd_mcap_sn_p80 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 3188 | 6.1% | -0.0621 |
| 2012-2015 | 1.0 | 194 | 12.4% | -0.0718 |
| 2016-2019 | 0.0 | 3178 | 7.5% | -0.0686 |
| 2016-2019 | 1.0 | 261 | 8.8% | -0.0855 |
| 2020-2022 | 0.0 | 2530 | 14.3% | -0.0949 |
| 2020-2022 | 1.0 | 278 | 14.4% | -0.1072 |
| 2023-2026 | 0.0 | 2666 | 9.5% | -0.0766 |
| 2023-2026 | 1.0 | 253 | 14.6% | -0.0891 |

### I1w: I1w (RESERVE): cluster≥2 vs washout-alone (within-washout)

- Stratum column: `ins_cluster_washout`
- Computable mask: `ins_computable_washout`
- Computable-gradable fires: 5,021
- N treatment (stratum=1): 358
- N control (computable-silent): 4,663
- N blocks: 1,310
- **Recall (stratum coverage): 7.1%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 5,021 | N estimation sample: shown in n_treatment + n_control | N blocks: 1,310
FE: `date` | Sector fallback to date-only blocks: no

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0015 | [-0.0416, 0.0450] | 0.0412 | 0.8920 | 0.9911 | 0.8920 | — | no |
| mae21 | -0.0059 | [-0.0149, -0.0016] * | -0.0112 | 0.0280 | 0.1300 | — | 0.0350 | no |
| zone_held_21 | -0.0264 | [-0.0938, 0.0010] | -0.0294 | 0.0520 | 0.1300 | — | — | no |
| stop_vol_21 | 0.0264 | [-0.0010, 0.0938] | 0.0294 | 0.0520 | 0.1300 | — | — | no |
| rotational_liftoff | 0.0100 | [-0.0361, 0.0640] | -0.0124 | 0.5280 | 0.7543 | — | — | no |
| positional_liftoff | 0.0082 | [-0.0318, 0.0684] | -0.0144 | 0.5040 | 0.7543 | — | — | no |
| dead_money | 0.0000 | [0.0000, 0.0000] | -0.0002 | 1.0000 | 1.0000 | — | — | no |
| cushion_rot | -0.0035 | [-0.0544, 0.0411] | -0.0021 | 0.8840 | 0.9911 | — | — | no |
| mae63 | -0.0043 | [-0.0170, 0.0044] | -0.0170 | 0.1960 | 0.3920 | — | — | no |
| mfe63 | 0.0414 | [0.0183, 0.0814] * | 0.0471 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I1w deep)

| era | ins_cluster_washout | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 505 | 17.6% | -0.1095 |
| 2012-2015 | 1.0 | 30 | 26.7% | -0.1253 |
| 2016-2019 | 0.0 | 661 | 15.1% | -0.0881 |
| 2016-2019 | 1.0 | 71 | 9.9% | -0.0947 |
| 2020-2022 | 0.0 | 1100 | 19.6% | -0.1032 |
| 2020-2022 | 1.0 | 83 | 25.3% | -0.1007 |
| 2023-2026 | 0.0 | 807 | 15.1% | -0.0887 |
| 2023-2026 | 1.0 | 44 | 4.5% | -0.0998 |

---

## Panel: BASKETS

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only.
Within-arm comparisons are directionally valid.

- Total fires loaded: 113,542
- Gradable fires: 107,127

### I1: I1: cluster≥2 post-washout

- Stratum column: `ins_cluster_washout`
- Computable mask: `ins_computable`
- Computable-gradable fires: 91,755
- N treatment (stratum=1): 3,815
- N control (computable-silent): 87,940
- N blocks: 263
- **Recall (stratum coverage): 4.2%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 91,755 | N estimation sample: shown in n_treatment + n_control | N blocks: 263
FE: `date` | Sector fallback to date-only blocks: YES

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0622 | [0.0490, 0.0737] * | 0.0940 | 0.0000 | 0.0000 | 0.0000 | — | YES |
| mae21 | -0.0143 | [-0.0167, -0.0114] * | -0.0182 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | -0.0183 | [-0.0324, -0.0036] * | -0.0171 | 0.0080 | 0.0089 | — | — | YES |
| stop_vol_21 | 0.0183 | [0.0036, 0.0324] * | 0.0171 | 0.0080 | 0.0089 | — | — | YES |
| rotational_liftoff | 0.0421 | [0.0283, 0.0544] * | 0.0752 | 0.0000 | 0.0000 | — | — | YES |
| positional_liftoff | -0.0013 | [-0.0124, 0.0104] | 0.0159 | 0.8680 | 0.8680 | — | — | no |
| dead_money | -0.0006 | [-0.0010, -0.0002] * | -0.0009 | 0.0040 | 0.0057 | — | — | YES |
| cushion_rot | 0.0303 | [0.0156, 0.0449] * | 0.0525 | 0.0000 | 0.0000 | — | — | YES |
| mae63 | -0.0245 | [-0.0290, -0.0203] * | -0.0249 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0346 | [0.0261, 0.0430] * | 0.0664 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I1 baskets)

| era | ins_cluster_washout | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 8188 | 14.4% | -0.1075 |
| 2012-2015 | 1.0 | 269 | 29.7% | -0.1712 |
| 2016-2019 | 0.0 | 26499 | 12.8% | -0.0988 |
| 2016-2019 | 1.0 | 973 | 22.0% | -0.1328 |
| 2020-2022 | 0.0 | 24515 | 24.8% | -0.1400 |
| 2020-2022 | 1.0 | 1265 | 36.0% | -0.1583 |
| 2023-2026 | 0.0 | 28738 | 20.9% | -0.1284 |
| 2023-2026 | 1.0 | 1308 | 25.3% | -0.1379 |

### I1-sens: I1-sens: cluster≥3 post-washout

- Stratum column: `ins_cluster_washout_3`
- Computable mask: `ins_computable`
- Computable-gradable fires: 91,755
- N treatment (stratum=1): 1,869
- N control (computable-silent): 89,886
- N blocks: 263
- **Recall (stratum coverage): 2.0%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 91,755 | N estimation sample: shown in n_treatment + n_control | N blocks: 263
FE: `date` | Sector fallback to date-only blocks: YES

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0777 | [0.0603, 0.0934] * | 0.1113 | 0.0000 | 0.0000 | 0.0000 | — | YES |
| mae21 | -0.0171 | [-0.0208, -0.0135] * | -0.0214 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | -0.0248 | [-0.0476, -0.0055] * | -0.0241 | 0.0200 | 0.0250 | — | — | YES |
| stop_vol_21 | 0.0248 | [0.0055, 0.0476] * | 0.0241 | 0.0200 | 0.0250 | — | — | YES |
| rotational_liftoff | 0.0325 | [0.0130, 0.0498] * | 0.0702 | 0.0000 | 0.0000 | — | — | YES |
| positional_liftoff | -0.0099 | [-0.0230, 0.0056] | 0.0102 | 0.2040 | 0.2040 | — | — | no |
| dead_money | -0.0011 | [-0.0014, -0.0007] * | -0.0011 | 0.0000 | 0.0000 | — | — | YES |
| cushion_rot | 0.0186 | [-0.0035, 0.0351] | 0.0440 | 0.0840 | 0.0933 | — | — | YES |
| mae63 | -0.0269 | [-0.0327, -0.0215] * | -0.0260 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0440 | [0.0324, 0.0577] * | 0.0784 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I1-sens baskets)

| era | ins_cluster_washout_3 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 8319 | 14.5% | -0.1084 |
| 2012-2015 | 1.0 | 138 | 33.3% | -0.1784 |
| 2016-2019 | 0.0 | 27009 | 12.9% | -0.0994 |
| 2016-2019 | 1.0 | 463 | 24.0% | -0.1367 |
| 2020-2022 | 0.0 | 25131 | 25.0% | -0.1405 |
| 2020-2022 | 1.0 | 649 | 38.8% | -0.1553 |
| 2023-2026 | 0.0 | 29427 | 21.0% | -0.1286 |
| 2023-2026 | 1.0 | 619 | 25.2% | -0.1398 |

### I2: I2: cluster≥2 near-fire (20td)

- Stratum column: `ins_cluster_pre20`
- Computable mask: `ins_computable`
- Computable-gradable fires: 91,755
- N treatment (stratum=1): 2,634
- N control (computable-silent): 89,121
- N blocks: 263
- **Recall (stratum coverage): 2.9%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 91,755 | N estimation sample: shown in n_treatment + n_control | N blocks: 263
FE: `date` | Sector fallback to date-only blocks: YES

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0249 | [0.0127, 0.0378] * | 0.0422 | 0.0000 | 0.0000 | 0.0000 | — | YES |
| mae21 | -0.0050 | [-0.0076, -0.0019] * | -0.0076 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | 0.0115 | [-0.0052, 0.0296] | 0.0106 | 0.1920 | 0.3200 | — | — | no |
| stop_vol_21 | -0.0115 | [-0.0296, 0.0052] | -0.0106 | 0.1920 | 0.3200 | — | — | no |
| rotational_liftoff | 0.0037 | [-0.0091, 0.0175] | 0.0027 | 0.4560 | 0.5067 | — | — | no |
| positional_liftoff | -0.0024 | [-0.0130, 0.0118] | -0.0085 | 0.9080 | 0.9080 | — | — | no |
| dead_money | 0.0004 | [-0.0006, 0.0017] | 0.0004 | 0.3880 | 0.4850 | — | — | no |
| cushion_rot | 0.0065 | [-0.0082, 0.0238] | -0.0003 | 0.3560 | 0.4850 | — | — | no |
| mae63 | -0.0069 | [-0.0105, -0.0031] * | -0.0088 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0106 | [0.0033, 0.0197] * | 0.0222 | 0.0040 | 0.0100 | — | — | YES |

#### Era Table (program eras, computable subset, I2 baskets)

| era | ins_cluster_pre20 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 8196 | 14.5% | -0.1088 |
| 2012-2015 | 1.0 | 261 | 24.5% | -0.1318 |
| 2016-2019 | 0.0 | 26687 | 13.0% | -0.0996 |
| 2016-2019 | 1.0 | 785 | 16.3% | -0.1150 |
| 2020-2022 | 0.0 | 25020 | 25.1% | -0.1405 |
| 2020-2022 | 1.0 | 760 | 33.7% | -0.1543 |
| 2023-2026 | 0.0 | 29218 | 21.1% | -0.1290 |
| 2023-2026 | 1.0 | 828 | 20.4% | -0.1224 |

### I3: I3: net_usd/mcap SN p≥80

- Stratum column: `ins_netusd_mcap_sn_p80`
- Computable mask: `ins_i3_computable`
- Computable-gradable fires: 91,793
- N treatment (stratum=1): 16,384
- N control (computable-silent): 75,409
- N blocks: 263
- **Recall (stratum coverage): 17.8%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 91,793 | N estimation sample: shown in n_treatment + n_control | N blocks: 263
FE: `date` | Sector fallback to date-only blocks: YES

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0312 | [0.0259, 0.0371] * | 0.0394 | 0.0000 | 0.0000 | 0.0000 | — | YES |
| mae21 | -0.0061 | [-0.0073, -0.0049] * | -0.0075 | 0.0000 | 0.0000 | — | 0.0000 | YES |
| zone_held_21 | 0.0065 | [0.0010, 0.0128] * | 0.0066 | 0.0240 | 0.0300 | — | — | YES |
| stop_vol_21 | -0.0065 | [-0.0128, -0.0010] * | -0.0066 | 0.0240 | 0.0300 | — | — | YES |
| rotational_liftoff | 0.0191 | [0.0109, 0.0254] * | 0.0306 | 0.0000 | 0.0000 | — | — | YES |
| positional_liftoff | 0.0034 | [-0.0040, 0.0101] | 0.0097 | 0.4520 | 0.4520 | — | — | no |
| dead_money | 0.0013 | [0.0008, 0.0020] * | 0.0013 | 0.0000 | 0.0000 | — | — | YES |
| cushion_rot | 0.0085 | [0.0011, 0.0165] * | 0.0165 | 0.0280 | 0.0311 | — | — | YES |
| mae63 | -0.0113 | [-0.0133, -0.0094] * | -0.0125 | 0.0000 | 0.0000 | — | — | YES |
| mfe63 | 0.0321 | [0.0271, 0.0374] * | 0.0407 | 0.0000 | 0.0000 | — | — | YES |

#### Era Table (program eras, computable subset, I3 baskets)

| era | ins_netusd_mcap_sn_p80 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 6913 | 14.2% | -0.1068 |
| 2012-2015 | 1.0 | 1544 | 17.7% | -0.1216 |
| 2016-2019 | 0.0 | 22833 | 12.2% | -0.0969 |
| 2016-2019 | 1.0 | 4649 | 17.7% | -0.1155 |
| 2020-2022 | 0.0 | 21090 | 24.9% | -0.1397 |
| 2020-2022 | 1.0 | 4701 | 27.7% | -0.1466 |
| 2023-2026 | 0.0 | 24573 | 20.5% | -0.1271 |
| 2023-2026 | 1.0 | 5490 | 23.7% | -0.1367 |

### I1w: I1w (RESERVE): cluster≥2 vs washout-alone (within-washout)

- Stratum column: `ins_cluster_washout`
- Computable mask: `ins_computable_washout`
- Computable-gradable fires: 47,442
- N treatment (stratum=1): 3,815
- N control (computable-silent): 43,627
- N blocks: 261
- **Recall (stratum coverage): 8.0%** of computable-gradable fires in-stratum

#### Effect Table (R1 date-FE, block bootstrap, computable_mask applied)

N total (post-mask): 47,442 | N estimation sample: shown in n_treatment + n_control | N blocks: 261
FE: `date` | Sector fallback to date-only blocks: YES

| Outcome | Coef | 95% CI (boot) | Naive diff | p | Within-trial BH q | Family BH q (stop5) | Family BH q (mae21) | BH rej? |
|---|---|---|---|---|---|---|---|---|
| stop5 | 0.0049 | [-0.0076, 0.0175] | 0.0112 | 0.4160 | 0.8844 | 0.5200 | — | no |
| mae21 | -0.0010 | [-0.0038, 0.0022] | -0.0001 | 0.6760 | 0.8844 | — | 0.6760 | no |
| zone_held_21 | 0.0009 | [-0.0146, 0.0191] | 0.0039 | 0.7440 | 0.8844 | — | — | no |
| stop_vol_21 | -0.0009 | [-0.0191, 0.0146] | -0.0039 | 0.7440 | 0.8844 | — | — | no |
| rotational_liftoff | -0.0042 | [-0.0179, 0.0087] | 0.0040 | 0.4040 | 0.8844 | — | — | no |
| positional_liftoff | -0.0019 | [-0.0135, 0.0098] | 0.0072 | 0.7960 | 0.8844 | — | — | no |
| dead_money | 0.0002 | [-0.0000, 0.0005] | 0.0002 | 0.2760 | 0.8844 | — | — | no |
| cushion_rot | 0.0002 | [-0.0133, 0.0130] | 0.0053 | 0.9640 | 0.9640 | — | — | no |
| mae63 | -0.0010 | [-0.0045, 0.0033] | 0.0050 | 0.6960 | 0.8844 | — | — | no |
| mfe63 | -0.0049 | [-0.0146, 0.0040] | 0.0031 | 0.3160 | 0.8844 | — | — | no |

#### Era Table (program eras, computable subset, I1w baskets)

| era | ins_cluster_washout | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 2731 | 26.2% | -0.1647 |
| 2012-2015 | 1.0 | 269 | 29.7% | -0.1712 |
| 2016-2019 | 0.0 | 10023 | 20.3% | -0.1313 |
| 2016-2019 | 1.0 | 973 | 22.0% | -0.1328 |
| 2020-2022 | 0.0 | 14830 | 31.7% | -0.1595 |
| 2020-2022 | 1.0 | 1265 | 36.0% | -0.1583 |
| 2023-2026 | 0.0 | 16043 | 27.5% | -0.1522 |
| 2023-2026 | 1.0 | 1308 | 25.3% | -0.1379 |

---

## Family-Wide BH Summary (10 consumed trials, q≤0.10)

BH correction runs independently on stop5 (primary) and mae21 (co-primary)
across all 10 consumed trials (8 initial + 2 stamped reserve).

**stop5 family BH:**

| Trial | Panel | p_value | q_value | BH rej? |
|---|---|---|---|---|
| I1 | deep | 0.0080 | 0.0133 | YES |
| I1-sens | deep | 0.5280 | 0.5867 | no |
| I2 | deep | 0.1400 | 0.2000 | no |
| I3 | deep | 0.0000 | 0.0000 | YES |
| I1w | deep | 0.8920 | 0.8920 | no |
| I1 | baskets | 0.0000 | 0.0000 | YES |
| I1-sens | baskets | 0.0000 | 0.0000 | YES |
| I2 | baskets | 0.0000 | 0.0000 | YES |
| I3 | baskets | 0.0000 | 0.0000 | YES |
| I1w | baskets | 0.4160 | 0.5200 | no |

**mae21 family BH:**

| Trial | Panel | p_value | q_value | BH rej? |
|---|---|---|---|---|
| I1 | deep | 0.0000 | 0.0000 | YES |
| I1-sens | deep | 0.0000 | 0.0000 | YES |
| I2 | deep | 0.0720 | 0.0800 | YES |
| I3 | deep | 0.0000 | 0.0000 | YES |
| I1w | deep | 0.0280 | 0.0350 | YES |
| I1 | baskets | 0.0000 | 0.0000 | YES |
| I1-sens | baskets | 0.0000 | 0.0000 | YES |
| I2 | baskets | 0.0000 | 0.0000 | YES |
| I3 | baskets | 0.0000 | 0.0000 | YES |
| I1w | baskets | 0.6760 | 0.6760 | no |

---

## Verdict (Phase-0)

**CHIP promotion bar (A2 RUL-21):** stop5 FE-coef ≥2pp, CI excluding 0,
BH q≤0.10 within the declared family, sign-stable ≥3/4 eras, n≥400 treatment,
beats NC-1 AND NC-2, MFE/|MAE| conjunctive.

**NC-2 eq_band status:** DEFERRED (A2 §C3, cycles.py pipeline required).
CHIP promotion is therefore **impossible this wave regardless of results**.
No promotion decision can be made until NC-2 is computable.

**Null result declaration:** Any trial with CI-including-0 on stop5 is a NULL.
Nulls are printed above, not hidden. A null is informative: insider clustering
conditional on fire does not demonstrably improve stop5 at this sample size.

**Recall note:** I1/I1-sens/I2 are rare events (<<5% of computable fires).
I3 has higher recall but n_treatment is still limited by the computable universe.
Low n_treatment limits power; CI-including-0 does not rule out a true effect.

**Era sign-stability note (RUL-21):** ≥3/4 eras required for CHIP. Check era
tables above for directional consistency.

No promotion language. Report only (RUL-4). These results inform Amendment 2
come-back scheduling and the esx_support_dose dose-response study (RUL-25).

---

*Generated by `scripts/research/run_a2_insider.py`*
*Grader: engine/grading.py (program barriers, RUL-9). T+1 fill.*
*'validated' word deliberately absent (CI-enforced).*
*No promotion language. Phase-0 study report only.*
*Family: esx_insider_sponsor | Budget declared: 12 | Consumed: 10 | Reserve: 2*
*CHIP promotion impossible this wave: NC-2 eq_band DEFERRED (A2 §C3).*
---

## Adjudication (Fable, 2026-07-05; revised post-review 2026-07-06)

Family reading across all 10 trials, no promotion implied:

1. **Unconditional insider strata are adverse at 21d** (I1/I1-sens/I2/I3: stop5 +2.5 to +7.8pp, mae21 deeper, vol-zones break more; CI-excl-0, BH-passing on both panels). Taken alone this would read "insider presence marks worse entries."
2. **The I1w reserve contrast attributes that adversity to the WASHOUT STATE, not the cluster.** Within washed-out computable fires, the cluster's marginal effect on stop5 is a tight null on the well-powered panel (baskets +0.5pp, CI [−0.8, +1.8], n_treat=3,815 — excludes ±2pp in both directions vs the RUL-21 floor) and a wide null on deep (+0.15pp, CI [−4.2, +4.5], underpowered). The paper's F1 entry-confirmer conjecture does not survive at the swing horizon.
3. **The holdability-lane hint is deep-only and weak.** Deep I1w mfe63 is +4.1pp (CI-excl-0, BH-YES), directionally consistent with the grandfathered 63d+ insider priors (`research/INSIDER_FACTOR.md` §6) — but the well-powered baskets panel CONTRADICTS it (mfe63 −0.5pp, CI [−1.5, +0.4], null). Read as a hypothesis for the esx_ql_overlay/S-QL lane at most, not evidence.
4. **Disposition:** no entry chip; no re-run of these contrasts (family reserve now 2). Insider sponsorship remains eligible ONLY as (a) a holdability-lane hypothesis coordinated with the esx_ql_overlay/S-QL lane at 63/126d per RUL-20; (b) a display-only `sponsor_present` envelope field (RUL-19), which these results neither earn nor forbid — display carries no ranking authority. The esx_support_dose leg-count study must NOT count insider presence as an entry-quality leg on this evidence.
5. Era note: I1w deep era signs flip across the four program eras — consistent with a null, not a hidden regime edge.

*This section is an adjudication note on a phase-0 report; it moves no registry state and ships no product change.*
