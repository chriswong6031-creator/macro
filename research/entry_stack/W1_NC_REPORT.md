# W1 Null-Competitor Report — Entry-Stack Expansion

**Status:** W1 report only — no promotion, no product change (RUL-3).
**Date:** 2026-07-05

Per masterplan §10 RUL-3: null-competitors run FIRST and appear as the
first table in every subsequent W1/W2 report. The YARDSTICK section
at the end of this document is the authoritative reference for later reports.

**Adjacency (R2 per RUL-2):**
- NC-1 (tier/freshness subsetting): no falsified relative — this is a
  first-principles question about whether simple subsetting already buys
  the asymmetry. Mechanical difference from any species candidate:
  NC-1 uses ONLY existing tier/ticks columns, adds no new information.
- NC-2 (entry_quality proxy): nearest falsified relative = volume-confirmation
  confirmers (H4, dead). Mechanical difference: entry_quality is a multi-axis
  proximity+freshness+momentum composite, not a volume-based screen.

---

## Trial Registration

Family: `esx_null_competitors` (budget=4, pre-registered at W0).
4 trial configs logged: 2 NC × 2 panels (deep / baskets).

---

## Panel: DEEP

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only; comparisons between strata are valid within this constraint.

- Total fires: 38,250
- Gradable fires: 37,722
- FE granularity: `date` (frozen per RUL-12)

### NC-1A: T1-only vs T1+T2+T3

**Recall of T1-only arm:** 89.1% (33,604 of 37,722 gradable fires)
**Recall COST:** 10.9% of fires dropped by restricting to T1

#### NC-1A Effect Table (R1 FE, fast block bootstrap)

N total (pre-drop): 37,722 | N estimation-sample (post-drop): 34,660 | N blocks: 8597
N treatment: 33,604 | N control: 4,118
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0019 | [-0.016, +0.008] | -0.0088 | 0.4940 | 0.8645 | no |
| rotational_liftoff | -0.0086 | [-0.025, +0.007] | -0.0170 | 0.3140 | 0.8633 | no |
| positional_liftoff | 0.0091 | [-0.011, +0.026] | 0.0148 | 0.3700 | 0.8633 | no |
| dead_money | 0.0001 | [-0.002, +0.002] | 0.0002 | 0.9740 | 0.9740 | no |
| cushion_rot | -0.0018 | [-0.022, +0.016] | -0.0042 | 0.6920 | 0.9688 | no |
| mae63 | -0.0000 | [-0.003, +0.003] | 0.0042 | 0.8580 | 0.9740 | no |
| mfe63 | -0.0046 | [-0.011, +0.001] | -0.0098 | 0.0920 | 0.6440 | no |

#### NC-1A Era summary (program eras, stop5 rate by stratum)

| era | nc1_t1_only | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 341 | 8.2% | -0.0638 |
| 2012-2015 | 1.0 | 3384 | 6.2% | -0.0624 |
| 2016-2019 | 0.0 | 352 | 7.4% | -0.0805 |
| 2016-2019 | 1.0 | 3363 | 7.5% | -0.0689 |
| 2020-2022 | 0.0 | 329 | 12.5% | -0.1030 |
| 2020-2022 | 1.0 | 2644 | 14.6% | -0.0960 |
| 2023-2026 | 0.0 | 302 | 10.9% | -0.0832 |
| 2023-2026 | 1.0 | 2727 | 9.7% | -0.0767 |

### NC-1B: ticks==0 (freshest) vs all

**Recall of ticks==0 arm:** 90.8% (34,250 of 37,722 gradable fires)
**Recall COST:** 9.2% of fires dropped by restricting to ticks=0

#### NC-1B Effect Table (R1 FE, fast block bootstrap)

N total (pre-drop): 37,722 | N estimation-sample (post-drop): 34,660 | N blocks: 8597
N treatment: 34,250 | N control: 3,472
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0001 | [-0.015, +0.007] | -0.0029 | 0.4060 | 0.7105 | no |
| rotational_liftoff | 0.0044 | [-0.015, +0.016] | 0.0004 | 0.9940 | 0.9940 | no |
| positional_liftoff | 0.0170 | [-0.005, +0.028] | 0.0165 | 0.2160 | 0.7105 | no |
| dead_money | -0.0031 | [-0.006, -0.001] * | -0.0020 | 0.0060 | 0.0420 | YES |
| cushion_rot | 0.0063 | [-0.013, +0.022] | 0.0041 | 0.6400 | 0.8960 | no |
| mae63 | -0.0015 | [-0.004, +0.001] | 0.0004 | 0.3140 | 0.7105 | no |
| mfe63 | 0.0001 | [-0.005, +0.004] | 0.0006 | 0.8020 | 0.9357 | no |

#### NC-1B Era summary (program eras, stop5 rate by stratum)

| era | nc1_fresh0 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 339 | 5.6% | -0.0661 |
| 2012-2015 | 1.0 | 3386 | 6.5% | -0.0621 |
| 2016-2019 | 0.0 | 321 | 5.0% | -0.0706 |
| 2016-2019 | 1.0 | 3394 | 7.7% | -0.0699 |
| 2020-2022 | 0.0 | 261 | 13.0% | -0.1053 |
| 2020-2022 | 1.0 | 2712 | 14.5% | -0.0960 |
| 2023-2026 | 0.0 | 288 | 9.4% | -0.0788 |
| 2023-2026 | 1.0 | 2741 | 9.9% | -0.0772 |

### NC-2: Entry-Quality Proximity Proxy (Partial)

> **DEFERRAL STAMP:** NC-2 PARTIAL: proximity component only (EQ_W_PROX=0.52 of total). PROXY-INPUT LIMITATION (finding 4): the engine (cycles.py:1705-1706) uses cand_price/dcl_price as the proximity pivot; this implementation uses a naive 63-bar close-minimum PROXY. No offline cache of cand_price/dcl_price exists. This is a proxy-INPUT, not merely a proxy-composite — NC-2 is DESCRIPTIVE-ONLY until the full deferred test with the real cycle pivot runs. DEFERRED components: freshness (EQ_W_FRESH=0.30) and momentum (EQ_W_MOM=0.18) require the full cycles.py call chain (multi_cycle, mtf_state, early_state, regime_state) per fire — computationally infeasible offline at this scale. The full NC-2 marginality test (coefficient survives eq-band FE in the R1 model) is deferred to the S-UR phase0 PR. Known limitation: proximity correlates with NC-1B (ticks=0 fires are typically closer to the rolling low pivot).

Proxy: proximity-only (EQ_W_PROX=0.52 of total) | Rolling window: 63 bars | Gradable with proxy: 38,250

Proximity stats: mean=0.5519, p25=0.2285, p50=0.5734, p75=0.7937

#### NC-2 Band Outcome Table (descriptive; survivor bias applies)

| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |
|---|---|---|---|---|---|---|---|---|
| 0 | bottom_tercile | 12,545 | 17.8% | 29.8% | 33.3% | 0.1% | -0.1041 | 0.1613 |
| 1 | mid_tercile | 12,592 | 10.0% | 23.9% | 34.8% | 0.3% | -0.0795 | 0.1191 |
| 2 | top_tercile | 12,585 | 7.2% | 20.9% | 34.6% | 0.5% | -0.0672 | 0.1047 |

Top-tercile recall: 33.4% (12,585 of 37,722)

#### NC-2 Top-tercile vs rest (R1 FE, proximity proxy)

N total (pre-drop): 37,722 | N estimation-sample (post-drop): 34,660 | N blocks: 8597
N treatment: 12,585 | N control: 25,137
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0427 | [-0.044, -0.031] * | -0.0672 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | -0.0339 | [-0.043, -0.022] * | -0.0585 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0129 | [-0.001, +0.022] | 0.0093 | 0.0800 | 0.0800 | YES |
| dead_money | 0.0029 | [+0.002, +0.005] * | 0.0031 | 0.0000 | 0.0000 | YES |
| cushion_rot | -0.0170 | [-0.028, -0.004] * | -0.0375 | 0.0140 | 0.0163 | YES |
| mae63 | 0.0191 | [+0.016, +0.020] * | 0.0248 | 0.0000 | 0.0000 | YES |
| mfe63 | -0.0226 | [-0.025, -0.020] * | -0.0346 | 0.0000 | 0.0000 | YES |

---

## Panel: BASKETS

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only; comparisons between strata are valid within this constraint.

- Total fires: 113,542
- Gradable fires: 107,127
- FE granularity: `date` (frozen per RUL-12)

**BOOTSTRAP CI NOTE (this panel):** Sector coverage < 50%, so block construction uses date-only clustering. This panel produced **266 episode blocks** for the bootstrap. If n_blocks is small (< ~100), CI width understates true sampling uncertainty. Point-estimate coefficients (date-FE OLS) remain valid regardless of block count.

### NC-1A: T1-only vs T1+T2+T3

**Recall of T1-only arm:** 85.9% (92,021 of 107,127 gradable fires)
**Recall COST:** 14.1% of fires dropped by restricting to T1

#### NC-1A Effect Table (R1 FE, fast block bootstrap)

N total (pre-drop): 107,127 | N estimation-sample (post-drop): 106,984 | N blocks: 266
N treatment: 92,021 | N control: 15,106
FE: `date` | Sector fallback: True

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0036 | [-0.011, +0.006] | 0.0036 | 0.5240 | 0.7303 | no |
| rotational_liftoff | -0.0014 | [-0.009, +0.006] | -0.0104 | 0.7880 | 0.7880 | no |
| positional_liftoff | -0.0020 | [-0.010, +0.006] | -0.0069 | 0.6260 | 0.7303 | no |
| dead_money | -0.0018 | [-0.003, -0.000] * | -0.0019 | 0.0060 | 0.0420 | YES |
| cushion_rot | -0.0033 | [-0.011, +0.007] | -0.0156 | 0.5920 | 0.7303 | no |
| mae63 | 0.0024 | [-0.000, +0.005] | 0.0055 | 0.0860 | 0.2007 | no |
| mfe63 | -0.0075 | [-0.016, +0.000] | -0.0031 | 0.0640 | 0.2007 | no |

#### NC-1A Era summary (program eras, stop5 rate by stratum)

| era | nc1_t1_only | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 3352 | 11.8% | -0.1089 |
| 2012-2015 | 1.0 | 7528 | 17.9% | -0.1202 |
| 2016-2019 | 0.0 | 3810 | 15.7% | -0.1167 |
| 2016-2019 | 1.0 | 29381 | 14.1% | -0.1040 |
| 2020-2022 | 0.0 | 4060 | 26.2% | -0.1534 |
| 2020-2022 | 1.0 | 25734 | 26.1% | -0.1436 |
| 2023-2026 | 0.0 | 3884 | 23.6% | -0.1364 |
| 2023-2026 | 1.0 | 29378 | 21.1% | -0.1294 |

### NC-1B: ticks==0 (freshest) vs all

**Recall of ticks==0 arm:** 90.9% (97,353 of 107,127 gradable fires)
**Recall COST:** 9.1% of fires dropped by restricting to ticks=0

#### NC-1B Effect Table (R1 FE, fast block bootstrap)

N total (pre-drop): 107,127 | N estimation-sample (post-drop): 106,984 | N blocks: 266
N treatment: 97,353 | N control: 9,774
FE: `date` | Sector fallback: True

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0099 | [+0.002, +0.015] * | 0.0165 | 0.0120 | 0.0373 | YES |
| rotational_liftoff | 0.0044 | [-0.002, +0.014] | 0.0057 | 0.1140 | 0.1596 | no |
| positional_liftoff | -0.0018 | [-0.008, +0.008] | 0.0012 | 0.9840 | 0.9840 | no |
| dead_money | 0.0011 | [+0.000, +0.002] * | 0.0011 | 0.0080 | 0.0373 | YES |
| cushion_rot | 0.0079 | [+0.002, +0.019] * | 0.0032 | 0.0160 | 0.0373 | YES |
| mae63 | -0.0021 | [-0.004, +0.001] | -0.0006 | 0.1840 | 0.2147 | no |
| mfe63 | 0.0069 | [+0.001, +0.012] * | 0.0088 | 0.0240 | 0.0420 | YES |

#### NC-1B Era summary (program eras, stop5 rate by stratum)

| era | nc1_fresh0 | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 1021 | 16.9% | -0.1218 |
| 2012-2015 | 1.0 | 9859 | 15.9% | -0.1162 |
| 2016-2019 | 0.0 | 3002 | 12.9% | -0.1046 |
| 2016-2019 | 1.0 | 30189 | 14.4% | -0.1055 |
| 2020-2022 | 0.0 | 2789 | 22.7% | -0.1434 |
| 2020-2022 | 1.0 | 27005 | 26.4% | -0.1450 |
| 2023-2026 | 0.0 | 2962 | 20.7% | -0.1286 |
| 2023-2026 | 1.0 | 30300 | 21.5% | -0.1304 |

### NC-2: Entry-Quality Proximity Proxy (Partial)

> **DEFERRAL STAMP:** NC-2 PARTIAL: proximity component only (EQ_W_PROX=0.52 of total). PROXY-INPUT LIMITATION (finding 4): the engine (cycles.py:1705-1706) uses cand_price/dcl_price as the proximity pivot; this implementation uses a naive 63-bar close-minimum PROXY. No offline cache of cand_price/dcl_price exists. This is a proxy-INPUT, not merely a proxy-composite — NC-2 is DESCRIPTIVE-ONLY until the full deferred test with the real cycle pivot runs. DEFERRED components: freshness (EQ_W_FRESH=0.30) and momentum (EQ_W_MOM=0.18) require the full cycles.py call chain (multi_cycle, mtf_state, early_state, regime_state) per fire — computationally infeasible offline at this scale. The full NC-2 marginality test (coefficient survives eq-band FE in the R1 model) is deferred to the S-UR phase0 PR. Known limitation: proximity correlates with NC-1B (ticks=0 fires are typically closer to the rolling low pivot).

Proxy: proximity-only (EQ_W_PROX=0.52 of total) | Rolling window: 63 bars | Gradable with proxy: 113,542

Proximity stats: mean=0.4927, p25=0.2, p50=0.4663, p75=0.7403

#### NC-2 Band Outcome Table (descriptive; survivor bias applies)

| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |
|---|---|---|---|---|---|---|---|---|
| 0 | bottom_tercile | 36,380 | 29.7% | 34.6% | 31.1% | 0.0% | -0.1576 | 0.2702 |
| 1 | mid_tercile | 34,356 | 18.0% | 29.6% | 31.1% | 0.1% | -0.1199 | 0.1608 |
| 2 | top_tercile | 36,391 | 12.0% | 25.9% | 31.3% | 0.7% | -0.0980 | 0.1306 |

Top-tercile recall: 34.0% (36,391 of 107,127)

#### NC-2 Top-tercile vs rest (R1 FE, proximity proxy)

N total (pre-drop): 107,127 | N estimation-sample (post-drop): 106,984 | N blocks: 266
N treatment: 36,391 | N control: 70,736
FE: `date` | Sector fallback: True

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.1012 | [-0.108, -0.096] * | -0.1198 | 0.0000 | 0.0000 | YES |
| rotational_liftoff | -0.0533 | [-0.061, -0.045] * | -0.0634 | 0.0000 | 0.0000 | YES |
| positional_liftoff | 0.0066 | [-0.001, +0.015] | 0.0019 | 0.0700 | 0.0700 | YES |
| dead_money | 0.0063 | [+0.005, +0.007] * | 0.0062 | 0.0000 | 0.0000 | YES |
| cushion_rot | -0.0287 | [-0.037, -0.020] * | -0.0325 | 0.0000 | 0.0000 | YES |
| mae63 | 0.0409 | [+0.038, +0.043] * | 0.0411 | 0.0000 | 0.0000 | YES |
| mfe63 | -0.0628 | [-0.068, -0.057] * | -0.0863 | 0.0000 | 0.0000 | YES |

---

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