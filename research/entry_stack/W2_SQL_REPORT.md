# W2 S-QL Quality Holdability Overlay — Entry-Stack Expansion

**Status:** W2 report only — no promotion, no product change (RUL-3).
**Date:** 2026-07-05

**Lane:** S-QL (§3 F5). HOLDABILITY STUDY ONLY.
**Horizon doctrine (RUL-13):** 63d/126d metrics are the HOLDABILITY lane only.
Entry timing is NOT under test in this lane. 21d context tables are printed
with an explicit banner; no entry-timing claims may be derived from them.

**PIT basis:** `assumed-120d-lag`.
fundamentals_panel.parquet asof_date = period_end + 120d FLAT (std=0).
This is an assumed lag, not per-filer SEC filing dates.
A fire is eligible for a FY row only when asof_date <= fire_date.

**Adjacency (R2 per RUL-2):**
- Nearest falsified relative: CN quality floors on reversal HURT (§3 F5).
  Mechanical difference: US-only, stratum (not gate), holdability horizon.
- US residual momentum falsified: this is fundamental accounting quality,
  not price momentum.

**Quality defs:**
- Piotroski F-score: 7-point variant from fundamentals_panel columns
  (cur_assets/cur_liab absent from panel — 7 instead of 9 tests).
- Altman Z-score (approx): 4-leg proxy using equity/assets, ni/assets,
  cfo/assets, revenue/assets (NOT the canonical Altman Z — panel lacks
  cur_assets/cur_liab/retained_earnings/op_income). Cross-sectional rank only.
- Sloan accrual: (ni - cfo) / assets. Reversed for tercile: T2 = lowest
  accruals = best accounting quality. STANDALONE ONLY (no interaction arm
  per masterplan §3 F5).

---

## NC Yardstick (RUL-3: must appear first)

Reference from W1_NC_REPORT.md — the bar S-QL must beat to claim value beyond
tier/freshness/proximity. Key values (deep panel, stop5 co-primary):

| Panel | NC | Stop5 coef | 95% CI | CI excl 0? |
|---|---|---|---|---|
| deep    | NC-1A (T1-only)      | -0.0019 | [-0.016, +0.008] | no |
| deep    | NC-1B (ticks=0)      |  0.0001 | [-0.015, +0.007] | no |
| deep    | NC-2 (prox top-3ile) | -0.0427 | [-0.044, -0.031] | YES |
| baskets | NC-1A (T1-only)      | -0.0036 | [-0.011, +0.006] | no |
| baskets | NC-1B (ticks=0)      |  0.0099 | [+0.002, +0.015] | YES |
| baskets | NC-2 (prox top-3ile) | -0.1012 | [-0.108, -0.096] | YES |

NC-2 stop5 coef is -4.3pp (deep) / -10.1pp (baskets) at top-proximity tercile.
Quality candidates must add value BEYOND proximity (marginality test via
entry_quality-band FE — DEFERRED to S-UR PR per W1 NC report).

---

## Trial Registration

Family: `esx_ql_overlay` (budget=12, pre-registered at W0).
12 trials: 3 quality defs × 2 horizons × 2 forms
(interaction arms: Piotroski/Altman only; Sloan standalone only).

---

## Headline Numbers (T3-vs-T1 deltas per def per panel)

Format: pos_liftoff Δ=... [CI]; dead_money Δ=... [CI]; recall T2=%; n_T2; n_T0
Direction: pos_liftoff (+) = better; dead_money (-) = better.
CI-excl-0 = bootstrap 95% CI excludes zero. BH-rej = BH q<=0.10 rejected.

### Panel: DEEP

- **piotroski**: pos_liftoff Δ=+0.019 [CI-incl-0]; dead_money Δ=-0.000 [CI-incl-0] (recall T2=18.8%) n_T2=1755 n_T0=4613
- **altman**: pos_liftoff Δ=+0.022 [CI-incl-0]; dead_money Δ=+0.000 [CI-incl-0] (recall T2=33.2%) n_T2=3725 n_T0=3768
- **sloan**: pos_liftoff Δ=+0.028 [CI-incl-0]; dead_money Δ=-0.002 [CI-incl-0] (recall T2=33.6%) n_T2=3338 n_T0=3291

---

## Panel: DEEP

**SURVIVOR BIAS STAMP:** SURVIVOR BIAS: absolute rates on surviving names only; comparisons between strata are valid within this constraint.
**PIT basis:** assumed-120d-lag

- Total fires loaded: 38,250
- Gradable fires: 37,722
- FE granularity: `date` (frozen per RUL-12)

### Coverage Report

Fires on names without EDGAR coverage are excluded from BOTH arms.

- Fires without any EDGAR-eligible ticker: 6,482 fires (37 tickers)
- Piotroski coverage (gradable fires): 9,335 / 37722
- Altman coverage (gradable fires): 11,218 / 37722
- Sloan coverage (gradable fires): 9,927 / 37722

### Piotroski F-score

Quality def: `piotroski` | Tercile col: `piotroski_t`
n quality non-null (gradable): 1755 T2, 4613 T0
Recall T2 (top quality): 18.8% | Recall T0 (bottom quality): 49.4%

#### Tercile Descriptive Table (survivor bias; no controls)

| tercile | tercile_label | n_fires | positional_liftoff_mean | dead_money_mean | fwd_mdd_126_mean | stop5_mean | rotational_liftoff_mean |
|---|---|---|---|---|---|---|---|
| 0 | bottom_quality | 4,613 | 32.3% | 0.3% | -10.3% | 10.0% | 21.1% |
| 1 | mid_quality | 2,967 | 34.6% | 0.1% | -10.2% | 7.9% | 21.4% |
| 2 | top_quality | 1,755 | 34.3% | 0.1% | -9.8% | 10.1% | 23.5% |

#### Holdability Effect (T2 vs T0, R1 FE, positional/126d primary)

#### Holdability R1 FE Table

N total (pre-drop): 6,368 | N estimation-sample (post-drop): 5,381 | N blocks: 1844
N treatment: 1,755 | N control: 4,613
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| positional_liftoff | 0.0187 | [-0.023, +0.045] | 0.0280 | 0.4680 | 0.6460 | no |
| dead_money | -0.0002 | [-0.005, +0.002] | -0.0017 | 0.6460 | 0.6460 | no |
| fwd_mdd_126 | 0.0075 | [-0.001, +0.012] | 0.0057 | 0.1100 | 0.3300 | no |

#### 21d Context Table

> **ENTRY-TIMING FENCE (RUL-13):** The 21d metrics below are printed as
> CONTEXT ONLY. This lane tests HOLDABILITY, not entry timing. No entry-
> timing claims may be derived from the 21d table. Per Amendment 1 RUL-13:
> 63d/126d are the only endpoints that decide an S-QL verdict.

#### 21d Context R1 FE Table (CONTEXT ONLY)

N total (pre-drop): 6,368 | N estimation-sample (post-drop): 5,381 | N blocks: 1844
N treatment: 1,755 | N control: 4,613
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | -0.0080 | [-0.013, +0.029] | 0.0044 | 0.5120 | 0.6620 | no |
| rotational_liftoff | 0.0008 | [-0.023, +0.034] | 0.0326 | 0.6620 | 0.6620 | no |
| zone_held_21 | -0.0013 | [-0.035, +0.019] | 0.0056 | 0.5700 | 0.6620 | no |
| stop_vol_21 | 0.0013 | [-0.019, +0.035] | -0.0056 | 0.5700 | 0.6620 | no |

#### Era × Tercile Table (program eras)

| era | tercile | n_fires | stop5_rate | pos_liftoff | dead_money |
|---|---|---|---|---|---|
| 2012-2015 | 0 | 1231 | 6.6% | 33.6% | 0.2% |
| 2012-2015 | 1 | 631 | 4.3% | 37.7% | 0.3% |
| 2012-2015 | 2 | 290 | 4.8% | 34.8% | 0.7% |
| 2016-2019 | 0 | 1269 | 8.3% | 31.5% | 0.4% |
| 2016-2019 | 1 | 771 | 4.8% | 31.8% | 0.0% |
| 2016-2019 | 2 | 302 | 8.3% | 35.4% | 0.0% |
| 2020-2022 | 0 | 918 | 15.2% | 30.0% | 0.0% |
| 2020-2022 | 1 | 694 | 11.2% | 37.5% | 0.0% |
| 2020-2022 | 2 | 451 | 14.6% | 33.7% | 0.0% |
| 2023-2026 | 0 | 975 | 10.2% | 34.5% | 0.0% |
| 2023-2026 | 1 | 721 | 9.8% | 33.4% | 0.1% |
| 2023-2026 | 2 | 629 | 9.7% | 35.1% | 0.0% |

#### Interaction Arm: Quality T2 × Washout T2 vs rest

Stratum = 1 iff quality tercile = 2 (top) AND washout depth tercile = 2 (deep).
Tests whether the quality holdability premium concentrates in deep-washout fires.

#### Interaction R1 FE Table

N total (pre-drop): 9,335 | N estimation-sample (post-drop): 8,512 | N blocks: 2216
N treatment: 604 | N control: 8,731
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| positional_liftoff | 0.0028 | [-0.062, +0.023] | 0.0103 | 0.3100 | 0.3100 | no |
| dead_money | -0.0018 | [-0.004, +0.000] | -0.0021 | 0.1600 | 0.2400 | no |
| fwd_mdd_126 | 0.0204 | [+0.008, +0.023] * | 0.0170 | 0.0000 | 0.0000 | YES |

### Altman Z-score (approx)

Quality def: `altman` | Tercile col: `altman_t`
n quality non-null (gradable): 3725 T2, 3768 T0
Recall T2 (top quality): 33.2% | Recall T0 (bottom quality): 33.6%

#### Tercile Descriptive Table (survivor bias; no controls)

| tercile | tercile_label | n_fires | positional_liftoff_mean | dead_money_mean | fwd_mdd_126_mean | stop5_mean | rotational_liftoff_mean |
|---|---|---|---|---|---|---|---|
| 0 | bottom_quality | 3,768 | 32.6% | 0.3% | -10.1% | 9.6% | 19.0% |
| 1 | mid_quality | 3,725 | 31.3% | 0.2% | -10.2% | 9.3% | 20.3% |
| 2 | top_quality | 3,725 | 36.4% | 0.2% | -10.2% | 9.6% | 25.5% |

#### Holdability Effect (T2 vs T0, R1 FE, positional/126d primary)

#### Holdability R1 FE Table

N total (pre-drop): 7,493 | N estimation-sample (post-drop): 6,522 | N blocks: 2060
N treatment: 3,725 | N control: 3,768
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| positional_liftoff | 0.0222 | [-0.006, +0.048] | 0.0339 | 0.1260 | 0.3780 | no |
| dead_money | 0.0000 | [-0.003, +0.003] | -0.0006 | 0.8320 | 0.8320 | no |
| fwd_mdd_126 | -0.0008 | [-0.007, +0.005] | -0.0012 | 0.7500 | 0.8320 | no |

#### 21d Context Table

> **ENTRY-TIMING FENCE (RUL-13):** The 21d metrics below are printed as
> CONTEXT ONLY. This lane tests HOLDABILITY, not entry timing. No entry-
> timing claims may be derived from the 21d table. Per Amendment 1 RUL-13:
> 63d/126d are the only endpoints that decide an S-QL verdict.

#### 21d Context R1 FE Table (CONTEXT ONLY)

N total (pre-drop): 7,493 | N estimation-sample (post-drop): 6,522 | N blocks: 2060
N treatment: 3,725 | N control: 3,768
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0056 | [-0.012, +0.019] | 0.0046 | 0.6680 | 0.8140 | no |
| rotational_liftoff | 0.0548 | [+0.038, +0.084] * | 0.0605 | 0.0000 | 0.0000 | YES |
| zone_held_21 | 0.0075 | [-0.018, +0.024] | 0.0024 | 0.8140 | 0.8140 | no |
| stop_vol_21 | -0.0075 | [-0.024, +0.018] | -0.0024 | 0.8140 | 0.8140 | no |

#### Era × Tercile Table (program eras)

| era | tercile | n_fires | stop5_rate | pos_liftoff | dead_money |
|---|---|---|---|---|---|
| 2012-2015 | 0 | 801 | 6.9% | 32.8% | 0.6% |
| 2012-2015 | 1 | 798 | 4.4% | 33.0% | 0.2% |
| 2012-2015 | 2 | 794 | 5.3% | 37.5% | 0.1% |
| 2016-2019 | 0 | 929 | 6.5% | 30.8% | 0.3% |
| 2016-2019 | 1 | 920 | 7.9% | 29.6% | 0.0% |
| 2016-2019 | 2 | 918 | 7.5% | 36.1% | 0.3% |
| 2020-2022 | 0 | 807 | 13.0% | 31.0% | 0.0% |
| 2020-2022 | 1 | 793 | 14.5% | 31.1% | 0.0% |
| 2020-2022 | 2 | 795 | 13.3% | 36.7% | 0.0% |
| 2023-2026 | 0 | 854 | 10.3% | 35.4% | 0.0% |
| 2023-2026 | 1 | 845 | 9.3% | 33.6% | 0.0% |
| 2023-2026 | 2 | 846 | 10.6% | 34.5% | 0.1% |

#### Interaction Arm: Quality T2 × Washout T2 vs rest

Stratum = 1 iff quality tercile = 2 (top) AND washout depth tercile = 2 (deep).
Tests whether the quality holdability premium concentrates in deep-washout fires.

#### Interaction R1 FE Table

N total (pre-drop): 11,218 | N estimation-sample (post-drop): 10,444 | N blocks: 2468
N treatment: 1,136 | N control: 10,082
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| positional_liftoff | 0.0240 | [-0.021, +0.041] | 0.0112 | 0.5660 | 0.7180 | no |
| dead_money | -0.0013 | [-0.003, +0.002] | -0.0012 | 0.7180 | 0.7180 | no |
| fwd_mdd_126 | 0.0117 | [+0.004, +0.016] * | 0.0039 | 0.0000 | 0.0000 | YES |

### Sloan accrual (T2=low-accruals=best quality)

Quality def: `sloan` | Tercile col: `sloan_t`
n quality non-null (gradable): 3338 T2, 3291 T0
Recall T2 (top quality): 33.6% | Recall T0 (bottom quality): 33.1%

#### Tercile Descriptive Table (survivor bias; no controls)

| tercile | tercile_label | n_fires | positional_liftoff_mean | dead_money_mean | fwd_mdd_126_mean | stop5_mean | rotational_liftoff_mean |
|---|---|---|---|---|---|---|---|
| 0 | bottom_quality | 3,291 | 32.6% | 0.2% | -9.6% | 9.1% | 21.2% |
| 1 | mid_quality | 3,298 | 33.8% | 0.4% | -9.2% | 8.4% | 19.2% |
| 2 | top_quality | 3,338 | 34.2% | 0.1% | -11.3% | 10.9% | 24.7% |

#### Holdability Effect (T2 vs T0, R1 FE, positional/126d primary)

#### Holdability R1 FE Table

N total (pre-drop): 6,629 | N estimation-sample (post-drop): 5,607 | N blocks: 1968
N treatment: 3,338 | N control: 3,291
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| positional_liftoff | 0.0277 | [-0.008, +0.047] | 0.0154 | 0.1780 | 0.1780 | no |
| dead_money | -0.0025 | [-0.006, +0.001] | -0.0015 | 0.1160 | 0.1740 | no |
| fwd_mdd_126 | -0.0145 | [-0.022, -0.009] * | -0.0167 | 0.0000 | 0.0000 | YES |

#### 21d Context Table

> **ENTRY-TIMING FENCE (RUL-13):** The 21d metrics below are printed as
> CONTEXT ONLY. This lane tests HOLDABILITY, not entry timing. No entry-
> timing claims may be derived from the 21d table. Per Amendment 1 RUL-13:
> 63d/126d are the only endpoints that decide an S-QL verdict.

#### 21d Context R1 FE Table (CONTEXT ONLY)

N total (pre-drop): 6,629 | N estimation-sample (post-drop): 5,607 | N blocks: 1968
N treatment: 3,338 | N control: 3,291
FE: `date` | Sector fallback: False

| Outcome | Coef | 95% CI (boot) | Naive diff | p | BH q | BH rej? |
|---|---|---|---|---|---|---|
| stop5 | 0.0169 | [+0.002, +0.037] * | 0.0184 | 0.0360 | 0.0507 | YES |
| rotational_liftoff | 0.0312 | [-0.002, +0.052] | 0.0299 | 0.0720 | 0.0720 | YES |
| zone_held_21 | -0.0202 | [-0.046, -0.001] * | -0.0139 | 0.0380 | 0.0507 | YES |
| stop_vol_21 | 0.0202 | [+0.001, +0.046] * | 0.0139 | 0.0380 | 0.0507 | YES |

#### Era × Tercile Table (program eras)

| era | tercile | n_fires | stop5_rate | pos_liftoff | dead_money |
|---|---|---|---|---|---|
| 2012-2015 | 0 | 709 | 4.7% | 32.3% | 0.1% |
| 2012-2015 | 1 | 715 | 5.5% | 37.3% | 0.6% |
| 2012-2015 | 2 | 721 | 6.7% | 36.2% | 0.3% |
| 2016-2019 | 0 | 785 | 7.4% | 31.5% | 0.0% |
| 2016-2019 | 1 | 780 | 5.6% | 33.1% | 0.5% |
| 2016-2019 | 2 | 794 | 8.2% | 32.4% | 0.1% |
| 2020-2022 | 0 | 672 | 13.8% | 33.2% | 0.0% |
| 2020-2022 | 1 | 678 | 11.5% | 31.1% | 0.0% |
| 2020-2022 | 2 | 685 | 16.1% | 34.4% | 0.0% |
| 2023-2026 | 0 | 771 | 9.7% | 33.7% | 0.0% |
| 2023-2026 | 1 | 770 | 9.3% | 34.3% | 0.0% |
| 2023-2026 | 2 | 776 | 11.2% | 34.4% | 0.1% |

**Interaction arm:** Interaction arm excluded for Sloan per masterplan §3 F5 (interaction arms restricted to full-coverage Piotroski/Altman).

---

## BH FDR Summary (esx_ql_overlay family)

BH q<=0.10 applied within the esx_ql_overlay family.
All p-values from holdability R1 FE tables pooled for the family-level BH panel.

Total holdability tests: 9 | BH rejections (q<=0.10): 1

| Test | p-value | q-value | BH rej? |
|---|---|---|---|
| deep/piotroski/positional_liftoff | 0.4680 | 0.7020 | no |
| deep/piotroski/dead_money | 0.6460 | 0.8306 | no |
| deep/piotroski/fwd_mdd_126 | 0.1100 | 0.2835 | no |
| deep/altman/positional_liftoff | 0.1260 | 0.2835 | no |
| deep/altman/dead_money | 0.8320 | 0.8320 | no |
| deep/altman/fwd_mdd_126 | 0.7500 | 0.8320 | no |
| deep/sloan/positional_liftoff | 0.1780 | 0.3204 | no |
| deep/sloan/dead_money | 0.1160 | 0.2835 | no |
| deep/sloan/fwd_mdd_126 | 0.0000 | 0.0000 | YES |

---

## Null results declaration (mandatory per masterplan §5)

Any outcome with CI-including-0 is a NULL result. Nulls are printed here,
not hidden. A null means the quality tercile does NOT show distinguishable
holdability improvement (beyond tier/date noise) at this sample size.

*No promotion language. The word 'validated' is deliberately absent.*
*Studies only. No product change from this PR.*

---

*Generated by `scripts/research/run_w2_sql.py`*
*Grader: engine/grading.py (program barriers, RUL-9).*
*PIT basis: assumed-120d-lag (fundamentals_panel asof_date = period_end+120d flat).*
*Horizon doctrine: RUL-13 — 63d/126d = holdability lane; 21d printed as context only.*
*R1 estimator: date-FE OLS + block-bootstrap 95% CI (RUL-12).*
*BH q<=0.10 within esx_ql_overlay family.*