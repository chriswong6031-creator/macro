# A3 HTF Oscillator Motion Report — Entry-Stack Expansion Amendment 3

**Amendment:** research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md
**Families:** esx_htf_turn (A, 12 trials), esx_htf_turn_dose (B, 2),
  esx_washout_x_turn (C, 8), esx_sub_x_turn (D, 2). Total: 24 new trials.
**Verdict ceiling:** DISPLAY-CANDIDATE / NULL / KILLED (RUL-28).
**CHIP promotion:** BLOCKED until true eq_band lands (RUL-28).
The word 'validated' deliberately absent.

> **ADJUDICATED** (Amendment §F, 2026-07-06): A1 weekly-turn = DISPLAY-CANDIDATE-CAVEATED
> (baskets-only, ~⅔ proximity); A3m monthly-turn = **NULL by non-replication** (deep-only win,
> fails baskets OOS — overrides the mechanical DISPLAY-CANDIDATE below); A2 = NULL; B = NULL/
> descriptive (not proximity-de-confounded); C = **KILLED** (proximity shadow, adverse
> marginality — the operator's literal 2W-washout×turn seed dies); D = NULL (cross-panel sign
> flip). The per-family mechanical stamps below are inputs to §F, not the final ruling.

## NC Yardstick (RUL-3) — from W1_NC_REPORT.md

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall |
|---|---|---|---|---|---|
| deep | NC-1A (T1-only) | -0.0019 | [-0.016, +0.008] | no | 89.1% |
| deep | NC-1B (ticks=0) | 0.0001 | [-0.015, +0.007] | no | 90.8% |
| deep | NC-2 (prox top-tercile) | -0.0427 | [-0.044, -0.031] * | YES * | 33.4% |
| baskets | NC-1A (T1-only) | -0.0036 | [-0.011, +0.006] | no | 85.9% |
| baskets | NC-1B (ticks=0) | 0.0099 | [+0.002, +0.015] * | YES * | 90.9% |
| baskets | NC-2 (prox top-tercile) | -0.1012 | [-0.108, -0.096] * | YES * | 34.0% |

---

## Panel: DEEP

**SURVIVOR BIAS: absolute rates on surviving names only. Within-stratum comparisons are directionally valid under this constraint.**

- Total fires: 38,250
- Gradable fires: 37,722
- Any A-rung operative CI-excluding-0: YES

### Family A — esx_htf_turn (12 trials)

RUL-28: CHIP promotion BLOCKED until eq_band. Verdict: DISPLAY-CANDIDATE / NULL / KILLED.
RUL-29: Operative read for A1 = ¬wbull subset. Pooled read carries wbull FE covariate.

#### Rung A1_w_hist_rising

- Computable fires (feature non-NaN): 36,918
- Burn-in dropped: 804
- ¬wbull subset n: 22,544

**Admission-leg decomposition (RUL-29 mandatory):**

| wbull | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 22,544 | 11.8% | -0.0483 |
| 1 | 14,374 | 11.3% | -0.0470 |

**Read-1 (pooled)** — carries wbull FE covariate (RUL-29):

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0025 | [-0.008, +0.015] | 0.4920 | no |
| mae21 | +0.0008 | [-0.002, +0.002] | 0.9660 | no |
| zone_held_21 | +0.0039 | [-0.017, +0.014] | 0.9040 | no |

**Read-2 (OPERATIVE — ¬wbull subset):**
Recall (compute_recall): 0.813 (30670/37722)

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0102 | [-0.011, +0.022] | 0.5060 | no |
| mae21 | -0.0002 | [-0.004, +0.002] | 0.3520 | no |
| zone_held_21 | -0.0089 | [-0.037, +0.005] | 0.1260 | no |

**Kill-arm battery — +nc2_band FE (RUL-30):**

- stop5: coef=+0.0027 [-0.009, +0.017] CI-excl-0=no (n_dropped_extra_fe=0)

**Era × stratum table (RUL-28): n_agree=1/4 eras — sign-stable ≥3/4: NO**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 2335 | 2123 | +0.0247 | + |
| 2016-2019 | 2203 | 2009 | -0.0179 | - |
| 2020-2022 | 1794 | 1621 | -0.0110 | - |
| 2023-2026 | 1848 | 1670 | -0.0133 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 109 | 11271 | +0.0142 | + |
| B | 110 | 11273 | +0.0090 | + |

**Verdict (stop5 operative read): NULL (CI includes 0 on operative read)**
CHIP promotion blocked until true eq_band (RUL-28).

#### Rung A2_w2_stoch_turn

- Computable fires (feature non-NaN): 37,193
- Burn-in dropped: 529
- ¬wbull subset n: 22,552

**Admission-leg decomposition (RUL-29 mandatory):**

| wbull | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 22,552 | 11.8% | -0.0483 |
| 1 | 14,381 | 11.3% | -0.0470 |

**Read-1 (pooled)**:

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0074 | [-0.014, +0.001] | 0.0640 | no |
| mae21 | +0.0009 | [-0.000, +0.002] | 0.1440 | no |
| zone_held_21 | -0.0024 | [-0.011, +0.007] | 0.6720 | no |

**Read-2 (robustness — ¬wbull subset):**
Recall (compute_recall): 0.298 (11256/37722)

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0033 | [-0.014, +0.012] | 0.9220 | no |
| mae21 | +0.0001 | [-0.002, +0.002] | 0.8480 | no |
| zone_held_21 | -0.0010 | [-0.013, +0.019] | 0.7480 | no |

**Kill-arm battery — +nc2_band FE (RUL-30):**

- stop5: coef=-0.0132 [-0.021, -0.002] * CI-excl-0=YES (n_dropped_extra_fe=0)

**Era × stratum table (RUL-28): n_agree=3/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 2335 | 394 | -0.0293 | - |
| 2016-2019 | 2203 | 386 | -0.0004 | - |
| 2020-2022 | 1795 | 279 | +0.0044 | + |
| 2023-2026 | 1848 | 303 | -0.0045 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 109 | 11277 | -0.0097 | - |
| B | 110 | 11275 | -0.0059 | - |

**Verdict (stop5 operative read): NULL (CI includes 0 on operative read)**
CHIP promotion blocked until true eq_band (RUL-28).

#### Rung A3m_m_stoch_turn

- Computable fires (feature non-NaN): 35,751
- Burn-in dropped: 1,971
- ¬wbull subset n: 21,829

**Admission-leg decomposition (RUL-29 mandatory):**

| wbull | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 21,829 | 11.6% | -0.0478 |
| 1 | 13,922 | 11.1% | -0.0468 |

**Read-1 (pooled)**:

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0093 | [-0.015, +0.000] | 0.0560 | no |
| mae21 | +0.0024 | [+0.001, +0.003] * | 0.0000 | YES |
| zone_held_21 | -0.0019 | [-0.011, +0.008] | 0.6800 | no |

**Read-2 (robustness — ¬wbull subset):**
Recall (compute_recall): 0.330 (12438/37722)

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0240 | [-0.034, -0.008] * | 0.0000 | YES |
| mae21 | +0.0046 | [+0.003, +0.007] * | 0.0000 | YES |
| zone_held_21 | +0.0114 | [-0.010, +0.028] | 0.3400 | no |

**Kill-arm battery — +nc2_band FE (RUL-30):**

- stop5: coef=-0.0322 [-0.039, -0.018] * CI-excl-0=YES (n_dropped_extra_fe=0)

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 2294 | 265 | -0.0184 | - |
| 2016-2019 | 2192 | 326 | -0.0223 | - |
| 2020-2022 | 1773 | 199 | -0.0170 | - |
| 2023-2026 | 1839 | 258 | -0.0136 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 108 | 10917 | -0.0246 | - |
| B | 109 | 10912 | -0.0261 | - |

**Verdict (stop5 operative read): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

### Family B — esx_htf_turn_dose (2 trials)

**UNLOCKED: >=1 A-rung operative read has CI-excluding-0.**

- Dropped (NaN in any rung column): 1,971
- Estimable fires: 35,751

**Per-level descriptive table (no CI):**

| n_turn_legs | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 1,982 | 12.4% | -0.0492 |
| 1 | 18,240 | 12.0% | -0.0482 |
| 2 | 11,857 | 10.8% | -0.0462 |
| 3 | 3,672 | 10.4% | -0.0465 |

**Ordinal per-unit coefficient (n_turn_legs as numeric stratum):**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0075 | [-0.011, -0.001] * | 0.0240 | YES |
| mae21 | +0.0012 | [+0.000, +0.002] * | 0.0000 | YES |
| zone_held_21 | -0.0013 | [-0.007, +0.004] | 0.6140 | no |

CHIP promotion blocked until true eq_band (RUL-28).

### Family C — esx_washout_x_turn (8 trials)

Pre-registered expectation: raw interaction most proximity-exposed; proxy-FE arm expected to bite. Thin-cell law: n_treat < 400 → DESCRIPTIVE stamp.

#### Form C1_deep_x_A1

- n_treat contrast-i (within-deep turn-vs-not): 15,441
- n_treat contrast-ii (deep&turn vs rest): 15,441

**Contrast (i): within-deep turn-vs-not:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0043 | [-0.008, +0.026] | 0.3440 | no |
| mae21 | -0.0007 | [-0.004, +0.001] | 0.3260 | no |
| zone_held_21 | +0.0084 | [-0.016, +0.023] | 0.6280 | no |

**Contrast (ii): deep&turn vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0175 | [+0.011, +0.024] * | 0.0000 | YES |
| mae21 | -0.0038 | [-0.005, -0.003] * | 0.0000 | YES |
| zone_held_21 | -0.0068 | [-0.014, +0.003] | 0.2180 | no |

**Kill-arm battery:**

- +nc2_band FE (contrast-i) | stop5: coef=+0.0140 [-0.012, +0.033] CI-excl-0=no
- +nc2_band FE (contrast-ii) | stop5: coef=+0.0320 [+0.022, +0.041] * CI-excl-0=YES
- +rv63_tercile FE (contrast-i, RUL-30) | stop5: coef=+0.0139 [-0.009, +0.035] CI-excl-0=no
- +rv63_tercile FE (contrast-ii, RUL-30) | stop5: coef=+0.0109 [+0.004, +0.021] * CI-excl-0=YES
- Marginality interaction | stop5: coef=+0.0237 [+0.003, +0.041] * CI-excl-0=YES

**¬bear_ctx decomposition (descriptive — kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 27455 | +0.0156 | YES |
| bear | 6450 | +0.0225 | YES |

CHIP promotion blocked until true eq_band (RUL-28).

#### Form C2_deep_x_A2

- n_treat contrast-i (within-deep turn-vs-not): 6,462
- n_treat contrast-ii (deep&turn vs rest): 6,462

**Contrast (i): within-deep turn-vs-not:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0095 | [-0.022, +0.003] | 0.1300 | no |
| mae21 | +0.0005 | [-0.001, +0.003] | 0.4020 | no |
| zone_held_21 | -0.0102 | [-0.020, +0.010] | 0.4540 | no |

**Contrast (ii): deep&turn vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0034 | [-0.005, +0.013] | 0.3580 | no |
| mae21 | -0.0017 | [-0.003, -0.000] * | 0.0360 | YES |
| zone_held_21 | -0.0120 | [-0.021, +0.002] | 0.0880 | no |

**Kill-arm battery:**

- +nc2_band FE (contrast-i) | stop5: coef=-0.0206 [-0.031, +0.001] CI-excl-0=no
- +nc2_band FE (contrast-ii) | stop5: coef=+0.0031 [-0.008, +0.014] CI-excl-0=no
- +rv63_tercile FE (contrast-i, RUL-30) | stop5: coef=-0.0154 [-0.031, +0.001] CI-excl-0=no
- +rv63_tercile FE (contrast-ii, RUL-30) | stop5: coef=-0.0023 [-0.014, +0.009] CI-excl-0=no
- Marginality interaction | stop5: coef=+0.0014 [-0.009, +0.018] CI-excl-0=no

**¬bear_ctx decomposition (descriptive — kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 27612 | +0.0029 | no |
| bear | 6487 | +0.0038 | no |

CHIP promotion blocked until true eq_band (RUL-28).

### Family D — esx_sub_x_turn (2 trials)

**UNLOCKED.**

- Estimable fires: 36,918

**r1_interaction_estimate(outcome, sub_deep, w_hist_rising):**

| Outcome | Interaction coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0183 | [-0.001, +0.037] | 0.0640 | no |
| mae21 | -0.0010 | [-0.006, +0.001] | 0.2080 | no |
| zone_held_21 | -0.0220 | [-0.048, +0.001] | 0.0640 | no |

CHIP promotion blocked until true eq_band (RUL-28).

---

## Panel: BASKETS

**SURVIVOR BIAS: absolute rates on surviving names only. Within-stratum comparisons are directionally valid under this constraint.**

- Total fires: 113,542
- Gradable fires: 107,127
- Any A-rung operative CI-excluding-0: YES

### Family A — esx_htf_turn (12 trials)

RUL-28: CHIP promotion BLOCKED until eq_band. Verdict: DISPLAY-CANDIDATE / NULL / KILLED.
RUL-29: Operative read for A1 = ¬wbull subset. Pooled read carries wbull FE covariate.

#### Rung A1_w_hist_rising

- Computable fires (feature non-NaN): 96,989
- Burn-in dropped: 10,138
- ¬wbull subset n: 57,422

**Admission-leg decomposition (RUL-29 mandatory):**

| wbull | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 57,422 | 20.6% | -0.0701 |
| 1 | 39,567 | 19.7% | -0.0709 |

**Read-1 (pooled)** — carries wbull FE covariate (RUL-29):

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0221 | [-0.030, -0.015] * | 0.0000 | YES |
| mae21 | +0.0034 | [+0.002, +0.005] * | 0.0000 | YES |
| zone_held_21 | -0.0024 | [-0.009, +0.005] | 0.5580 | no |

**Read-2 (OPERATIVE — ¬wbull subset):**
Recall (compute_recall): 0.744 (79688/107127)

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0257 | [-0.035, -0.017] * | 0.0000 | YES |
| mae21 | +0.0045 | [+0.003, +0.007] * | 0.0000 | YES |
| zone_held_21 | -0.0095 | [-0.017, +0.003] | 0.1300 | no |

**Kill-arm battery — +nc2_band FE (RUL-30):**

- stop5: coef=-0.0083 [-0.016, -0.002] * CI-excl-0=YES (n_dropped_extra_fe=0)

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 2527 | 2211 | -0.0316 | - |
| 2016-2019 | 18941 | 16862 | -0.0217 | - |
| 2020-2022 | 16502 | 14574 | -0.0472 | - |
| 2023-2026 | 19452 | 17291 | -0.0107 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 1204 | 28949 | -0.0206 | - |
| B | 1204 | 28473 | -0.0299 | - |

**Verdict (stop5 operative read): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

#### Rung A2_w2_stoch_turn

- Computable fires (feature non-NaN): 100,237
- Burn-in dropped: 6,890
- ¬wbull subset n: 57,530

**Admission-leg decomposition (RUL-29 mandatory):**

| wbull | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 57,530 | 20.6% | -0.0702 |
| 1 | 39,628 | 19.7% | -0.0709 |

**Read-1 (pooled)**:

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0066 | [-0.012, -0.002] * | 0.0040 | YES |
| mae21 | +0.0019 | [+0.001, +0.003] * | 0.0040 | YES |
| zone_held_21 | +0.0092 | [+0.003, +0.015] * | 0.0080 | YES |

**Read-2 (robustness — ¬wbull subset):**
Recall (compute_recall): 0.288 (30847/107127)

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0073 | [-0.015, -0.000] * | 0.0500 | YES |
| mae21 | +0.0016 | [-0.000, +0.003] | 0.0660 | no |
| zone_held_21 | +0.0110 | [+0.004, +0.019] * | 0.0020 | YES |

**Kill-arm battery — +nc2_band FE (RUL-30):**

- stop5: coef=-0.0185 [-0.023, -0.013] * CI-excl-0=YES (n_dropped_extra_fe=0)

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 2589 | 416 | -0.0069 | - |
| 2016-2019 | 18955 | 3008 | -0.0135 | - |
| 2020-2022 | 16525 | 2772 | -0.0045 | - |
| 2023-2026 | 19461 | 3157 | -0.0037 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 1204 | 28999 | -0.0083 | - |
| B | 1204 | 28531 | -0.0079 | - |

**Verdict (stop5 operative read): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

#### Rung A3m_m_stoch_turn

- Computable fires (feature non-NaN): 84,084
- Burn-in dropped: 23,043
- ¬wbull subset n: 50,179

**Admission-leg decomposition (RUL-29 mandatory):**

| wbull | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 50,179 | 20.2% | -0.0692 |
| 1 | 33,905 | 19.4% | -0.0692 |

**Read-1 (pooled)**:

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0076 | [-0.016, -0.001] * | 0.0160 | YES |
| mae21 | +0.0019 | [+0.000, +0.004] * | 0.0160 | YES |
| zone_held_21 | +0.0037 | [-0.004, +0.011] | 0.3700 | no |

**Read-2 (robustness — ¬wbull subset):**
Recall (compute_recall): 0.272 (29093/107127)

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0046 | [-0.014, +0.005] | 0.4480 | no |
| mae21 | +0.0013 | [-0.001, +0.003] | 0.2400 | no |
| zone_held_21 | +0.0052 | [-0.005, +0.014] | 0.5200 | no |

**Kill-arm battery — +nc2_band FE (RUL-30):**

- stop5: coef=-0.0516 [-0.058, -0.044] * CI-excl-0=YES (n_dropped_extra_fe=0)

**Era × stratum table (RUL-28): n_agree=1/3 eras — sign-stable ≥3/4: NO**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 0 | 0 | — | — _thin or no-variation_ |
| 2016-2019 | 15987 | 2199 | -0.0226 | - |
| 2020-2022 | 15647 | 1802 | +0.0043 | + |
| 2023-2026 | 18545 | 2660 | +0.0047 | + |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 1177 | 25212 | -0.0100 | - |
| B | 1178 | 24967 | -0.0024 | - |

**Verdict (stop5 operative read): NULL (CI includes 0 on operative read)**
CHIP promotion blocked until true eq_band (RUL-28).

### Family B — esx_htf_turn_dose (2 trials)

**UNLOCKED: >=1 A-rung operative read has CI-excluding-0.**

- Dropped (NaN in any rung column): 23,044
- Estimable fires: 84,083

**Per-level descriptive table (no CI):**

| n_turn_legs | n_fires | stop5_mean | mae21_mean |
|---|---|---|---|
| 0 | 4,852 | 23.2% | -0.0757 |
| 1 | 43,048 | 20.6% | -0.0695 |
| 2 | 27,712 | 18.5% | -0.0683 |
| 3 | 8,471 | 18.7% | -0.0668 |

**Ordinal per-unit coefficient (n_turn_legs as numeric stratum):**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0080 | [-0.012, -0.005] * | 0.0000 | YES |
| mae21 | +0.0018 | [+0.001, +0.003] * | 0.0000 | YES |
| zone_held_21 | +0.0028 | [-0.002, +0.007] | 0.2480 | no |

CHIP promotion blocked until true eq_band (RUL-28).

### Family C — esx_washout_x_turn (8 trials)

Pre-registered expectation: raw interaction most proximity-exposed; proxy-FE arm expected to bite. Thin-cell law: n_treat < 400 → DESCRIPTIVE stamp.

#### Form C1_deep_x_A1

- n_treat contrast-i (within-deep turn-vs-not): 41,720
- n_treat contrast-ii (deep&turn vs rest): 41,720

**Contrast (i): within-deep turn-vs-not:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0130 | [-0.022, -0.006] * | 0.0000 | YES |
| mae21 | +0.0040 | [+0.003, +0.007] * | 0.0000 | YES |
| zone_held_21 | +0.0028 | [-0.006, +0.013] | 0.5140 | no |

**Contrast (ii): deep&turn vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0142 | [+0.009, +0.020] * | 0.0000 | YES |
| mae21 | -0.0033 | [-0.005, -0.002] * | 0.0000 | YES |
| zone_held_21 | -0.0083 | [-0.016, -0.002] * | 0.0040 | YES |

**Kill-arm battery:**

- +nc2_band FE (contrast-i) | stop5: coef=-0.0029 [-0.013, +0.005] CI-excl-0=no
- +nc2_band FE (contrast-ii) | stop5: coef=+0.0426 [+0.037, +0.049] * CI-excl-0=YES
- +rv63_tercile FE (contrast-i, RUL-30) | stop5: coef=-0.0112 [-0.020, -0.004] * CI-excl-0=YES
- +rv63_tercile FE (contrast-ii, RUL-30) | stop5: coef=-0.0006 [-0.005, +0.005] CI-excl-0=no
- Marginality interaction | stop5: coef=+0.0141 [+0.002, +0.028] * CI-excl-0=YES

**¬bear_ctx decomposition (descriptive — kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 83779 | +0.0146 | YES |
| bear | 13210 | +0.0119 | no |

CHIP promotion blocked until true eq_band (RUL-28).

#### Form C2_deep_x_A2

- n_treat contrast-i (within-deep turn-vs-not): 17,786
- n_treat contrast-ii (deep&turn vs rest): 17,786

**Contrast (i): within-deep turn-vs-not:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0090 | [-0.014, -0.000] * | 0.0400 | YES |
| mae21 | +0.0012 | [-0.001, +0.003] | 0.2600 | no |
| zone_held_21 | +0.0080 | [+0.001, +0.015] * | 0.0240 | YES |

**Contrast (ii): deep&turn vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0044 | [-0.002, +0.010] | 0.1440 | no |
| mae21 | -0.0018 | [-0.003, -0.000] * | 0.0200 | YES |
| zone_held_21 | +0.0009 | [-0.006, +0.007] | 0.8300 | no |

**Kill-arm battery:**

- +nc2_band FE (contrast-i) | stop5: coef=-0.0299 [-0.036, -0.023] * CI-excl-0=YES
- +nc2_band FE (contrast-ii) | stop5: coef=+0.0042 [-0.001, +0.011] CI-excl-0=no
- +rv63_tercile FE (contrast-i, RUL-30) | stop5: coef=-0.0078 [-0.013, -0.000] * CI-excl-0=YES
- +rv63_tercile FE (contrast-ii, RUL-30) | stop5: coef=-0.0053 [-0.010, +0.000] CI-excl-0=no
- Marginality interaction | stop5: coef=-0.0023 [-0.011, +0.006] CI-excl-0=no

**¬bear_ctx decomposition (descriptive — kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 86811 | +0.0034 | no |
| bear | 13426 | +0.0097 | no |

CHIP promotion blocked until true eq_band (RUL-28).

### Family D — esx_sub_x_turn (2 trials)

**UNLOCKED.**

- Estimable fires: 96,989

**r1_interaction_estimate(outcome, sub_deep, w_hist_rising):**

| Outcome | Interaction coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0194 | [-0.029, -0.006] * | 0.0020 | YES |
| mae21 | +0.0033 | [+0.001, +0.006] * | 0.0100 | YES |
| zone_held_21 | +0.0013 | [-0.011, +0.014] | 0.8420 | no |

CHIP promotion blocked until true eq_band (RUL-28).

---

## Program Summary

| Family | Trials | Verdict ceiling |
|---|---|---|
| esx_htf_turn (A)       | 12 | DISPLAY-CANDIDATE / NULL / KILLED (RUL-28) |
| esx_htf_turn_dose (B)  |  2 | LOCKED behind A; DESCRIPTIVE if LOCKED |
| esx_washout_x_turn (C) |  8 | DISPLAY-CANDIDATE / NULL / KILLED (RUL-28) |
| esx_sub_x_turn (D)     |  2 | LOCKED behind A; DESCRIPTIVE if LOCKED |

CHIP promotion blocked for ALL A3 families until true eq_band lands (RUL-28).

*Generated by `scripts/research/run_a3_htf.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*The word 'validated' deliberately absent (CI-enforced).*