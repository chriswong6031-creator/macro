# A3 Structural / Vol-Transition Report — Entry-Stack Expansion Amendment 3

**Amendment:** research/ENTRY_STACK_EXPANSION_AMENDMENT3_BY_FABLE.md
**Families:** esx_decline_geometry (E, 4), esx_underwater (F, 4),
  esx_vol_transition (G, 4). Total: 12 new trials.
**Verdict ceiling:** DISPLAY-CANDIDATE / NULL / KILLED (RUL-28).
**CHIP promotion:** BLOCKED until true eq_band lands (RUL-28).
The word 'validated' deliberately absent.

> **ADJUDICATED** (Amendment §F, 2026-07-06): E `decline_geometry` (flush) = **DISPLAY-CANDIDATE**
> — the program's one clean, cross-panel, full-battery survivor (ships display-only to the
> bottom_sensors envelope + shadow ledger). F `underwater` = **ADVERSE-CONTEXT** (real AVOID sign,
> survives age63 arm; de-escalation-eligible, never a buy chip). G `vol_transition` = **NULL**
> (expect-null confirmed). See §F for the deployment ruling and clocks.

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

### Family E — esx_decline_geometry (4 trials)

Two-sided framing. Flush = top tercile (few large down-days); Grind = bottom tercile.
Mechanism: flush = forced supply that empties; grind = voluntary distribution that persists.

- Computable fires: 37,586
- Burn-in dropped: 136
- n_flush (tercile 2): 12,768
- n_grind (tercile 0): 12,610

**Contrast (i): flush vs grind (restricted to top+bottom terciles):**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0142 | [-0.026, -0.007] * | 0.0000 | YES |
| mae21 | +0.0031 | [+0.001, +0.005] * | 0.0000 | YES |
| zone_held_21 | +0.0054 | [-0.007, +0.017] | 0.3560 | no |

**Contrast (ii): flush vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0100 | [-0.016, -0.003] * | 0.0000 | YES |
| mae21 | +0.0023 | [+0.001, +0.003] * | 0.0080 | YES |
| zone_held_21 | +0.0079 | [-0.002, +0.015] | 0.1640 | no |

**Kill-arm battery:**

*flush vs grind:*
- nc2_band|stop5: coef=-0.0277 [-0.039, -0.012] * CI-excl-0=YES (n_dropped_extra=0)
- rv63_tercile|stop5: coef=-0.0144 [-0.028, -0.003] * CI-excl-0=YES (n_dropped_extra=0)

*flush vs rest:*
- nc2_band|stop5: coef=-0.0206 [-0.026, -0.008] * CI-excl-0=YES (n_dropped_extra=0)
- rv63_tercile|stop5: coef=-0.0114 [-0.018, -0.002] * CI-excl-0=YES (n_dropped_extra=0)

**¬bear_ctx decomposition (kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 27792 | -0.0073 | no |
| bear | 6537 | -0.0236 | YES |

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 3708 | 1246 | -0.0154 | - |
| 2016-2019 | 3704 | 1303 | -0.0165 | - |
| 2020-2022 | 2973 | 870 | -0.0146 | - |
| 2023-2026 | 3029 | 1185 | -0.0214 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 109 | 18865 | -0.0214 | - |
| B | 110 | 18721 | -0.0009 | - |

**Verdict (flush-vs-rest stop5): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

### Family F — esx_underwater (4 trials)

Two-sided framing. Long = top tercile (longest underwater); Short = bottom tercile.
NOTE: primitive time_underwater_series SATURATES at ~window bars and can RESET on
interim peaks within the trailing window. Values describe bars since trailing peak,
bounded at approximately window-1.
Pure-age kill-arm (age63_tercile) proves F is not H2 re-derived.

- Computable fires: 37,336
- n_long (tercile 2): 13,652
- n_short (tercile 0): 12,151

**Contrast (i): long vs short:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0290 | [+0.021, +0.040] * | 0.0000 | YES |
| mae21 | -0.0061 | [-0.007, -0.003] * | 0.0000 | YES |
| zone_held_21 | -0.0192 | [-0.027, -0.002] * | 0.0240 | YES |

**Contrast (ii): long vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0235 | [+0.020, +0.035] * | 0.0000 | YES |
| mae21 | -0.0052 | [-0.007, -0.004] * | 0.0000 | YES |
| zone_held_21 | -0.0158 | [-0.025, -0.007] * | 0.0000 | YES |

**Kill-arm battery (+nc2_band, +age63_tercile, ¬bear_ctx):**

- nc2_band|stop5: coef=+0.0292 [+0.022, +0.041] * CI-excl-0=YES (n_dropped_extra=0)
- age63_tercile|stop5: coef=+0.0211 [+0.018, +0.035] * CI-excl-0=YES (n_dropped_extra=0)

**¬bear_ctx decomposition (kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 27707 | +0.0216 | YES |
| bear | 6506 | +0.0327 | YES |

**Kill-only diagnostic: window=126 re-read (named, not a registered primary):**

- stop5: coef=+0.0180 [+0.011, +0.026] * CI-excl-0=YES

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 3707 | 1338 | +0.0368 | + |
| 2016-2019 | 3706 | 1286 | +0.0137 | + |
| 2020-2022 | 2961 | 1226 | +0.0316 | + |
| 2023-2026 | 3028 | 1018 | +0.0103 | + |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 109 | 18721 | +0.0187 | + |
| B | 110 | 18615 | +0.0299 | + |

**Verdict (long-vs-rest stop5): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

### Family G — esx_vol_transition (4 trials)

**PRE-REGISTERED EXPECT-NULL (RUL-5).** Registered expectation IS a null.
This family settles whether ANY vol-family conditioning survives once vol
LEVEL is controlled (vol_ts is a term-structure ratio, not a level).
Non-null requires: pooled BH-adjusted CI-excluding-0 AND rv63_tercile FE
arm (BINDING per RUL-32) also CI-excluding-0. Sign-stable ≥3/4 eras required.

- Computable fires (vol_falling non-NaN): 37,721
- vol_falling=1 (treatment): 16,580
- vol_elevated=1 (elevated arm): 9,319

**Contrast (i): vol_falling vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0070 | [-0.014, -0.001] * | 0.0280 | YES |
| mae21 | -0.0004 | [-0.001, +0.001] | 0.4500 | no |
| zone_held_21 | -0.0154 | [-0.022, -0.007] * | 0.0000 | YES |

**Contrast (ii): vol_falling vs vol_elevated:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0057 | [-0.019, -0.001] * | 0.0380 | YES |
| mae21 | -0.0014 | [-0.002, +0.001] | 0.2580 | no |
| zone_held_21 | -0.0466 | [-0.055, -0.032] * | 0.0000 | YES |

**Kill-arm battery (+rv63_tercile BINDING, +nc2_band, ¬bear_ctx):**

- nc2_band|stop5: coef=-0.0091 [-0.019, -0.003] * CI-excl-0=YES (n_dropped_extra=0)
- rv63_tercile|stop5: coef=-0.0058 [-0.016, -0.001] * CI-excl-0=YES (n_dropped_extra=0)

**¬bear_ctx decomposition (kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 27846 | -0.0088 | YES |
| bear | 6548 | +0.0038 | no |

**Era × stratum table (RUL-28): n_agree=1/4 eras — sign-stable ≥3/4: NO**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 3725 | 1710 | +0.0051 | + |
| 2016-2019 | 3715 | 1833 | +0.0026 | + |
| 2020-2022 | 2973 | 1413 | -0.0019 | - |
| 2023-2026 | 3029 | 1411 | +0.0083 | + |

**Ticker-half sign agreement (RUL-28 baskets): DISAGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 109 | 18915 | -0.0127 | - |
| B | 110 | 18806 | +0.0025 | + |

**NULL (era-stability gate)** — pooled + rv63 arm CI-excl-0 but era sign
stability fails: 1/4 eras agree.

CHIP promotion blocked until true eq_band (RUL-28).

---

## Panel: BASKETS

**SURVIVOR BIAS: absolute rates on surviving names only. Within-stratum comparisons are directionally valid under this constraint.**

- Total fires: 113,542
- Gradable fires: 107,127

### Family E — esx_decline_geometry (4 trials)

Two-sided framing. Flush = top tercile (few large down-days); Grind = bottom tercile.
Mechanism: flush = forced supply that empties; grind = voluntary distribution that persists.

- Computable fires: 106,816
- Burn-in dropped: 311
- n_flush (tercile 2): 35,805
- n_grind (tercile 0): 35,609

**Contrast (i): flush vs grind (restricted to top+bottom terciles):**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0404 | [-0.048, -0.034] * | 0.0000 | YES |
| mae21 | +0.0086 | [+0.007, +0.010] * | 0.0000 | YES |
| zone_held_21 | +0.0168 | [+0.009, +0.025] * | 0.0000 | YES |

**Contrast (ii): flush vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0234 | [-0.029, -0.017] * | 0.0000 | YES |
| mae21 | +0.0046 | [+0.003, +0.006] * | 0.0000 | YES |
| zone_held_21 | +0.0104 | [+0.004, +0.016] * | 0.0040 | YES |

**Kill-arm battery:**

*flush vs grind:*
- nc2_band|stop5: coef=-0.0552 [-0.062, -0.048] * CI-excl-0=YES (n_dropped_extra=0)
- rv63_tercile|stop5: coef=-0.0365 [-0.042, -0.031] * CI-excl-0=YES (n_dropped_extra=0)

*flush vs rest:*
- nc2_band|stop5: coef=-0.0335 [-0.039, -0.028] * CI-excl-0=YES (n_dropped_extra=0)
- rv63_tercile|stop5: coef=-0.0285 [-0.033, -0.023] * CI-excl-0=YES (n_dropped_extra=0)

**¬bear_ctx decomposition (kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 93151 | -0.0218 | YES |
| bear | 13665 | -0.0336 | YES |

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 10789 | 3690 | -0.0236 | - |
| 2016-2019 | 33038 | 11165 | -0.0141 | - |
| 2020-2022 | 29748 | 8711 | -0.0211 | - |
| 2023-2026 | 33241 | 12239 | -0.0337 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 1234 | 53939 | -0.0309 | - |
| B | 1234 | 52877 | -0.0144 | - |

**Verdict (flush-vs-rest stop5): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

### Family F — esx_underwater (4 trials)

Two-sided framing. Long = top tercile (longest underwater); Short = bottom tercile.
NOTE: primitive time_underwater_series SATURATES at ~window bars and can RESET on
interim peaks within the trailing window. Values describe bars since trailing peak,
bounded at approximately window-1.
Pure-age kill-arm (age63_tercile) proves F is not H2 re-derived.

- Computable fires: 102,237
- n_long (tercile 2): 36,441
- n_short (tercile 0): 32,817

**Contrast (i): long vs short:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0747 | [+0.067, +0.083] * | 0.0000 | YES |
| mae21 | -0.0179 | [-0.020, -0.016] * | 0.0000 | YES |
| zone_held_21 | -0.0296 | [-0.042, -0.020] * | 0.0000 | YES |

**Contrast (ii): long vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | +0.0631 | [+0.057, +0.069] * | 0.0000 | YES |
| mae21 | -0.0156 | [-0.017, -0.014] * | 0.0000 | YES |
| zone_held_21 | -0.0275 | [-0.035, -0.019] * | 0.0000 | YES |

**Kill-arm battery (+nc2_band, +age63_tercile, ¬bear_ctx):**

- nc2_band|stop5: coef=+0.0591 [+0.053, +0.065] * CI-excl-0=YES (n_dropped_extra=0)
- age63_tercile|stop5: coef=+0.0590 [+0.052, +0.064] * CI-excl-0=YES (n_dropped_extra=0)

**¬bear_ctx decomposition (kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 88699 | +0.0627 | YES |
| bear | 13538 | +0.0655 | YES |

**Kill-only diagnostic: window=126 re-read (named, not a registered primary):**

- stop5: coef=+0.0523 [+0.046, +0.059] * CI-excl-0=YES

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 7381 | 2622 | +0.0778 | + |
| 2016-2019 | 32766 | 11901 | +0.0646 | + |
| 2020-2022 | 29062 | 11135 | +0.0636 | + |
| 2023-2026 | 33028 | 10783 | +0.0575 | + |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 1223 | 51591 | +0.0595 | + |
| B | 1224 | 50646 | +0.0675 | + |

**Verdict (long-vs-rest stop5): DISPLAY-CANDIDATE (CI-excl-0 + era-sign-stable >=3/4 + ticker-half agree; RUL-28 ceiling)**
CHIP promotion blocked until true eq_band (RUL-28).

### Family G — esx_vol_transition (4 trials)

**PRE-REGISTERED EXPECT-NULL (RUL-5).** Registered expectation IS a null.
This family settles whether ANY vol-family conditioning survives once vol
LEVEL is controlled (vol_ts is a term-structure ratio, not a level).
Non-null requires: pooled BH-adjusted CI-excluding-0 AND rv63_tercile FE
arm (BINDING per RUL-32) also CI-excluding-0. Sign-stable ≥3/4 eras required.

- Computable fires (vol_falling non-NaN): 107,121
- vol_falling=1 (treatment): 45,751
- vol_elevated=1 (elevated arm): 27,717

**Contrast (i): vol_falling vs rest:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0174 | [-0.022, -0.013] * | 0.0000 | YES |
| mae21 | +0.0035 | [+0.003, +0.004] * | 0.0000 | YES |
| zone_held_21 | -0.0080 | [-0.013, -0.003] * | 0.0000 | YES |

**Contrast (ii): vol_falling vs vol_elevated:**

| Outcome | Coef | 95% CI | p | CI excl 0? |
|---|---|---|---|---|
| stop5 | -0.0305 | [-0.036, -0.024] * | 0.0000 | YES |
| mae21 | +0.0056 | [+0.004, +0.007] * | 0.0000 | YES |
| zone_held_21 | -0.0300 | [-0.039, -0.024] * | 0.0000 | YES |

**Kill-arm battery (+rv63_tercile BINDING, +nc2_band, ¬bear_ctx):**

- nc2_band|stop5: coef=-0.0095 [-0.014, -0.006] * CI-excl-0=YES (n_dropped_extra=0)
- rv63_tercile|stop5: coef=-0.0088 [-0.012, -0.005] * CI-excl-0=YES (n_dropped_extra=0)

**¬bear_ctx decomposition (kill-only per RUL-30):**

| Context | n | stop5 coef | CI-excl-0? |
|---|---|---|---|
| notbear | 93405 | -0.0200 | YES |
| bear | 13716 | +0.0009 | no |

**Era × stratum table (RUL-28): n_agree=4/4 eras — sign-stable ≥3/4: YES**

| Era | n_total | n_treatment | coef | sign |
|---|---|---|---|---|
| 2012-2015 | 10876 | 4745 | -0.0218 | - |
| 2016-2019 | 33189 | 14560 | -0.0168 | - |
| 2020-2022 | 29794 | 13132 | -0.0144 | - |
| 2023-2026 | 33262 | 13314 | -0.0192 | - |

**Ticker-half sign agreement (RUL-28 baskets): AGREE**

| Half | tickers_n | n_total | coef | sign |
|---|---|---|---|---|
| A | 1234 | 54152 | -0.0176 | - |
| B | 1234 | 52969 | -0.0167 | - |

**POSSIBLE NON-NULL** — pooled CI-excluding-0 AND rv63_tercile arm
CI-excluding-0 AND era-sign-stable >=3/4. Per RUL-5 EXPECT-NULL protocol,
replication on baskets also required before any discussion.

CHIP promotion blocked until true eq_band (RUL-28).

---

## Program Summary

| Family | Trials | Expectation | Verdict ceiling |
|---|---|---|---|
| esx_decline_geometry (E) | 4 | Two-sided | DISPLAY-CANDIDATE / NULL / KILLED |
| esx_underwater (F)       | 4 | Two-sided | DISPLAY-CANDIDATE / NULL / KILLED |
| esx_vol_transition (G)   | 4 | EXPECT-NULL (RUL-5) | NULL / or non-null if rv63 arm also excl-0 |

CHIP promotion blocked for ALL A3 families until true eq_band lands (RUL-28).

*Generated by `scripts/research/run_a3_struct.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*The word 'validated' deliberately absent (CI-enforced).*