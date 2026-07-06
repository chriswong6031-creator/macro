# W1 S-TS ADX Residual Study — Entry-Stack Expansion

**Status:** W1 report only — no promotion, no product change.
**Candidate:** S-TS (F6) — ADX trend-strength residual (STRATUM, expect-null).
**Date:** 2026-07-05

---

## NC Yardstick (RUL-3) — Reproduced from W1_NC_REPORT.md

Per §10 RUL-3: null-competitors appear as the FIRST table. The S-TS coefficients
are shown after this yardstick for comparison.

Direction note: stop5 is an ADVERSE outcome — a better stratum has a MORE NEGATIVE
stop5 coefficient. For liftoff the coefficient should be MORE POSITIVE.

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? | Recall (treat arm) |
|---|---|---|---|---|---|
| deep    | NC-1A (T1-only)       | -0.0019 | [-0.016, +0.008] | no   | 89.1% |
| deep    | NC-1B (ticks=0)       |  0.0001 | [-0.015, +0.007] | no   | 90.8% |
| deep    | NC-2 (prox top-tercile)| -0.0427 | [-0.044, -0.031] | YES *| 33.4% |
| baskets | NC-1A (T1-only)       | -0.0036 | [-0.011, +0.006] | no   | 85.9% |
| baskets | NC-1B (ticks=0)       |  0.0099 | [+0.002, +0.015] | YES *| 90.9% |
| baskets | NC-2 (prox top-tercile)| -0.1012 | [-0.108, -0.096] | YES *| 34.0% |

Source: research/entry_stack/W1_NC_REPORT.md (2026-07-05).

---

## Adjacency Citation (R2 — RUL-2)

**Nearest falsified relatives:**
1. Trend/location guards (rising MAs, ATR-contraction, higher-low): **FALSIFIED** as
   exposure artifacts (DURABLE_BOTTOM_FRAMEWORK.md:606; masterplan §2/§3).
2. CT-LANE result: counter-trend buyable fires NOT-WORSE than aligned (n=7,392,
   −0.16/−0.6pp; masterplan §2/§3). Directional alignment hard-blocks unjustified.

**Mechanical difference from falsified relatives:**
ADX14 measures trend *energy* directionlessly — it does NOT require alignment with
a moving average or a directional price structure. The falsified guards required
directional confirmation. ADX makes no directional claim; it asks only whether the
market is in a 'trending' state by volatility/momentum energy metrics.
This distinction is exactly why the question remains open (never studied in this
repo — census 3A); these priors make the prior hostile, not dispositive.

---

## Pre-Registered Expect-Null Declaration (RUL-5)

The registered expectation is a NULL. Quoting masterplan §3 F6:
> "Expectation: pre-registered expect-null. Value = a citable kill (or a surprise
> worth having)."

Non-null is defined ONLY as: **pooled FE coefficient with BH-adjusted CI excluding 0**.
Single-era excursions are NOISE by pre-registration — they are printed below but
cannot satisfy the non-null bar.

If non-null is found, the next step is baskets OOS replication — that is not
decided by this script. The script prints the result; adjudication is upstream.

---

## Trial Registration

Family: `esx_ts_adx` (budget=4, pre-registered at W0).
4 trial configs logged: 1 def × 2 panels × 2 era-splits.

---

## Stratum Operationalization (§3 F6 + RUL-F6-OPDEF)

The masterplan §3 F6 pre-registered "ADX14 rising-vs-low at fire" as the S-TS
candidate. The specific operationalization below was chosen by the W1 builder
(no alternative threshold or lookback was tested before reading results) and is
frozen via **RUL-F6-OPDEF** appended to §3 F6 in
`research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`. Any change requires a
new ruling per RUL-7.

- **Stratum A (adx_rising=1):** `adx14 > 20 AND adx14 > adx14_at_(bar−5)` at fire bar.
  - `level_threshold = 20.0` (conventional "trending" floor; no alternative tested pre-read)
  - `lookback = 5 bars` (one trading week; no alternative tested pre-read)
- **Stratum B (adx_rising=0):** complement.
- ADX14 via `engine.stock_technicals.adx_dmi(high, low, close, n=14)`.
- Close-only fires: EXCLUDED (printed below, not silently zeroed).
- Lookback for ADX: strictly prior bars including fire date. No lookahead.

---

## Free Context Columns — NO-INFERENCE BANNER

The following columns are CONTEXT-ONLY. They carry:
- No registered family.
- No BH correction.
- No promotion path.
- No CI is reported.
- Breakout alpha (52w-high) is already FALSIFIED (masterplan §2). The dist_52w
  tercile here is OVERHEAD SUPPLY CONTEXT (S-OH candidate, §3 D3) — not breakout.
- Vol-regime overlay already FAILED additive-value vs vol-target (masterplan §3/§2).
  VIX bands here are index-level regime context only.

---

## Panel: DEEP

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only. Comparisons between strata are directionally valid within this constraint.

- Total fires loaded: 38,250
- Gradable fires: 37,722
- FE granularity: `date` (frozen per RUL-12)

### Close-Only Exclusion Report

ADX14 requires H/L panels. Close-only fires (no H/L available) are
excluded from the ADX stratum and printed here (not silently zeroed).

- Fires with no H/L panel: **0**
- Insufficient history (< 28 bars): **0**
- Date not in panel: **0**
- ADX NaN (computation failure): **0**
- Insufficient lag5 history (< 5 bars prior ADX): **0**
- **Total excluded: 0** of 38,250 fires (0.0%)

### ADX14 Distribution at Fire Bars

- Mean: 21.22
- P25 / P50 / P75: 15.69 / 19.77 / 25.07
- Pct ADX > 20 (level condition): 48.6%

### Stratum Sizes

- Stratum A (adx_rising=1, all fires): 8,066
- Stratum B (adx_rising=0, all fires): 30,184
- Excluded (no valid ADX): 0
- Gradable stratum A: 7,966
- Gradable stratum B: 29,756
- Gradable excluded: 0

### Recall

**Stratum A recall** (adx_rising fires as fraction of all gradable with valid ADX):
  21.1% (7,966 of 37,722)
**Recall COST:** 78.9% of fires are Stratum B

#### S-TS ADX Effect Table (R1 FE, block bootstrap)

N total (pre-drop): 37,722 | N estimation-sample (post-drop): 34,660 | N blocks: 8597
N treatment: 7,966 | N control: 29,756
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0031 | [-0.012, +0.005] | -0.0143 | 0.3560 | 0.4153 | no |
| rotational_liftoff | -0.0182 | [-0.031, -0.009] * | -0.0270 | 0.0000 | 0.0000 | YES |
| positional_liftoff | -0.0029 | [-0.013, +0.011] | -0.0032 | 0.8820 | 0.8820 | no |
| dead_money | 0.0012 | [-0.000, +0.002] | 0.0005 | 0.1160 | 0.2707 | no |
| cushion_rot | -0.0120 | [-0.025, -0.001] * | -0.0237 | 0.0340 | 0.1190 | no |
| mae63 | 0.0008 | [-0.001, +0.003] | 0.0042 | 0.2840 | 0.3976 | no |
| mfe63 | 0.0024 | [-0.001, +0.006] | -0.0039 | 0.2340 | 0.3976 | no |

#### Era × Stratum Table (program eras)

| era | adx_rising | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 2938 | 6.9% | -0.0634 |
| 2012-2015 | 1.0 | 787 | 4.3% | -0.0592 |
| 2016-2019 | 0.0 | 2970 | 8.1% | -0.0707 |
| 2016-2019 | 1.0 | 745 | 4.8% | -0.0670 |
| 2020-2022 | 0.0 | 2491 | 14.3% | -0.0974 |
| 2020-2022 | 1.0 | 482 | 14.5% | -0.0936 |
| 2023-2026 | 0.0 | 2470 | 10.0% | -0.0764 |
| 2023-2026 | 1.0 | 559 | 9.1% | -0.0817 |

#### Era-Split Stop5 Coefficients

Per pre-registration (RUL-5): single-era excursions are NOISE. Printed for
completeness; they cannot satisfy the non-null bar.

| Era | N total | N treat | N ctrl | Stop5 coef | 95% CI | CI excl 0? |
|---|---|---|---|---|---|---|
| 2012-2015 | 3,725 | 787 | 2,938 | -0.0330 | [-0.047, -0.013] | YES * |
| 2016-2019 | 3,715 | 745 | 2,970 | -0.0181 | [-0.041, +0.004] | no |
| 2020-2022 | 2,973 | 482 | 2,491 | 0.0089 | [-0.018, +0.048] | no |
| 2023-2026 | 3,029 | 559 | 2,470 | -0.0075 | [-0.038, +0.020] | no |

---

## Panel: BASKETS

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only. Comparisons between strata are directionally valid within this constraint.

- Total fires loaded: 113,542
- Gradable fires: 107,127
- FE granularity: `date` (frozen per RUL-12)

### Close-Only Exclusion Report

ADX14 requires H/L panels. Close-only fires (no H/L available) are
excluded from the ADX stratum and printed here (not silently zeroed).

- Fires with no H/L panel: **0**
- Insufficient history (< 28 bars): **0**
- Date not in panel: **0**
- ADX NaN (computation failure): **0**
- Insufficient lag5 history (< 5 bars prior ADX): **0**
- **Total excluded: 0** of 113,542 fires (0.0%)

### ADX14 Distribution at Fire Bars

- Mean: 21.39
- P25 / P50 / P75: 15.5 / 19.66 / 25.43
- Pct ADX > 20 (level condition): 48.1%

### Stratum Sizes

- Stratum A (adx_rising=1, all fires): 22,101
- Stratum B (adx_rising=0, all fires): 91,441
- Excluded (no valid ADX): 0
- Gradable stratum A: 20,882
- Gradable stratum B: 86,245
- Gradable excluded: 0

### Recall

**Stratum A recall** (adx_rising fires as fraction of all gradable with valid ADX):
  19.5% (20,882 of 107,127)
**Recall COST:** 80.5% of fires are Stratum B

#### S-TS ADX Effect Table (R1 FE, block bootstrap)

N total (pre-drop): 107,127 | N estimation-sample (post-drop): 106,984 | N blocks: 266
N treatment: 20,882 | N control: 86,245
FE: `date` | Sector fallback: True

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0100 | [+0.003, +0.016] * | 0.0049 | 0.0020 | 0.0035 | YES |
| rotational_liftoff | -0.0000 | [-0.006, +0.007] | -0.0056 | 0.8600 | 0.8600 | no |
| positional_liftoff | 0.0001 | [-0.005, +0.007] | 0.0001 | 0.6980 | 0.8143 | no |
| dead_money | 0.0029 | [+0.002, +0.004] * | 0.0030 | 0.0000 | 0.0000 | YES |
| cushion_rot | -0.0022 | [-0.008, +0.006] | -0.0078 | 0.6960 | 0.8143 | no |
| mae63 | -0.0057 | [-0.007, -0.004] * | -0.0052 | 0.0000 | 0.0000 | YES |
| mfe63 | 0.0213 | [+0.016, +0.029] * | 0.0223 | 0.0000 | 0.0000 | YES |

#### Era × Stratum Table (program eras)

| era | adx_rising | n_fires | stop5_rate | mae63_mean |
|---|---|---|---|---|
| 2012-2015 | 0.0 | 8690 | 15.7% | -0.1168 |
| 2012-2015 | 1.0 | 2190 | 17.0% | -0.1161 |
| 2016-2019 | 0.0 | 26658 | 14.2% | -0.1050 |
| 2016-2019 | 1.0 | 6533 | 14.6% | -0.1074 |
| 2020-2022 | 0.0 | 24542 | 26.2% | -0.1440 |
| 2020-2022 | 1.0 | 5252 | 25.7% | -0.1490 |
| 2023-2026 | 0.0 | 26355 | 21.1% | -0.1278 |
| 2023-2026 | 1.0 | 6907 | 22.8% | -0.1395 |

#### Era-Split Stop5 Coefficients

Per pre-registration (RUL-5): single-era excursions are NOISE. Printed for
completeness; they cannot satisfy the non-null bar.

| Era | N total | N treat | N ctrl | Stop5 coef | 95% CI | CI excl 0? |
|---|---|---|---|---|---|---|
| 2012-2015 | 10,880 | 2,190 | 8,690 | 0.0193 | [-0.003, +0.039] | no |
| 2016-2019 | 33,191 | 6,533 | 26,658 | 0.0033 | [-0.006, +0.013] | no |
| 2020-2022 | 29,794 | 5,252 | 24,542 | 0.0163 | [+0.003, +0.029] | YES * |
| 2023-2026 | 33,262 | 6,907 | 26,355 | 0.0086 | [-0.002, +0.019] | no |

---

## Free Context Columns (No Inference)

These tables are descriptive rate summaries by context band. No CI is computed.
No promotion path. No registered family. See header for NO-INFERENCE BANNER.

### Panel: DEEP

#### S-OH Context: Distance from 52-Week High (tercile bands)

**NO-INFERENCE BANNER:** Descriptive only. No CI, no BH, no promotion path. Context column; not a registered candidate.

| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |
|---|---|---|---|---|---|---|---|---|
| 0.0 | deepest below 52w high | 12,448 | 19.1% | 33.7% | 35.2% | 0.0% | -0.1058 | 0.1677 |
| 1.0 | mid | 12,457 | 8.1% | 21.0% | 34.0% | 0.3% | -0.0735 | 0.1080 |
| 2.0 | closest to 52w high | 12,453 | 7.6% | 19.7% | 33.4% | 0.5% | -0.0708 | 0.1080 |

#### VIX Regime Context: Trailing-10y Percentile Bands

**NO-INFERENCE BANNER:** Descriptive only. No CI, no BH, no promotion path. Context column; not a registered candidate.

| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |
|---|---|---|---|---|---|---|---|---|
| 0.0 | low-vol (VIX < 33rd pctile trail-10y) | 8,295 | 6.4% | 18.0% | 33.5% | 0.4% | -0.0690 | 0.1028 |
| 1.0 | mid-vol (33rd–67th pctile) | 7,486 | 10.3% | 22.0% | 32.9% | 0.2% | -0.0891 | 0.1138 |
| 2.0 | high-vol (VIX > 67th pctile trail-10y) | 7,681 | 19.2% | 31.2% | 33.9% | 0.1% | -0.0987 | 0.1583 |

### Panel: BASKETS

#### S-OH Context: Distance from 52-Week High (tercile bands)

**NO-INFERENCE BANNER:** Descriptive only. No CI, no BH, no promotion path. Context column; not a registered candidate.

| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |
|---|---|---|---|---|---|---|---|---|
| 0.0 | deepest below 52w high | 34,030 | 31.6% | 38.6% | 32.2% | 0.0% | -0.1695 | 0.2820 |
| 1.0 | mid | 34,409 | 15.6% | 28.6% | 31.7% | 0.1% | -0.1060 | 0.1506 |
| 2.0 | closest to 52w high | 33,714 | 13.0% | 23.0% | 29.6% | 0.4% | -0.1008 | 0.1333 |

#### VIX Regime Context: Trailing-10y Percentile Bands

**NO-INFERENCE BANNER:** Descriptive only. No CI, no BH, no promotion path. Context column; not a registered candidate.

| Band | Label | N fires | stop5 | rot_liftoff | pos_liftoff | dead_money | mae63 | mfe63 |
|---|---|---|---|---|---|---|---|---|
| 0.0 | low-vol (VIX < 33rd pctile trail-10y) | 30,970 | 15.4% | 24.8% | 29.3% | 0.3% | -0.1210 | 0.1511 |
| 1.0 | mid-vol (33rd–67th pctile) | 40,215 | 20.1% | 27.8% | 29.9% | 0.3% | -0.1285 | 0.1786 |
| 2.0 | high-vol (VIX > 67th pctile trail-10y) | 35,942 | 23.7% | 37.1% | 34.3% | 0.2% | -0.1253 | 0.2294 |

---

## Verdict

Per masterplan §3 F6 and RUL-5:

The ADX-rising stratum is a **pre-registered expect-null study**.
The verdict is determined solely by: **pooled FE coefficient with BH-adjusted CI
excluding 0 on the primary endpoint (stop5)**.

**Panel DEEP:**
- stop5 coef = -0.0031, 95% CI = [-0.012, +0.005]
- CI excludes 0: NO
- BH q ≤ 0.10 rejected: NO
- **NULL** — CI includes 0 or BH not rejected. Pre-registered expected outcome confirmed.

**Panel BASKETS:**
- stop5 coef = 0.0100, 95% CI = [+0.003, +0.016] *
- CI excludes 0: YES
- BH q ≤ 0.10 rejected: YES
- **POSSIBLE NON-NULL** (both CI-excluding-0 AND BH-rejected). Per RUL-5: baskets OOS replication required before chip discussion. Adjudication is upstream of this script.
- **CHIP PATH FORECLOSED** regardless of OOS outcome: adverse sign (ADX-rising = MORE stops, not fewer); magnitude 1.0pp < 2pp §5 CHIP floor. A CHIP requires a beneficial (negative) stop5 coef ≥ 2pp CI-excluding-0. The only live follow-up would be a HYGIENE/veto evaluation under its own §5 bar — not a chip.

**Summary:** The pre-registered expectation was a null. See individual panel
verdicts above. Single-era excursions in the era table cannot satisfy the non-null
bar and are printed for completeness only (RUL-5).

---

*Generated by `scripts/research/run_w1_sts.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*'validated' word deliberately absent (CI-enforced).*
*No promotion language. Reports only.*