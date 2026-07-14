# Pre-Registration — MRI Track T: Mixed-Frequency Energy Accumulator (mf_energy v1)

**Frozen:** 2026-07-10 (written BEFORE backtest_mf_energy_v1.py is run)
**Program:** Macro Release Intelligence (MRI), Track T — W11-C (Wave 11, Round 1 parallel science)
**Branch:** claude/mri-w11-track-t
**Spec attempt:** #1 of 1 (MRI-R36: kill rule at T-1 vs strongest naive; per §6 anti-mining, max 1 attempt for Track T; no re-spec after results are observed)
**Status:** FROZEN — no model spec changes after this commit
**Authority:** MRI-R36, masterplan §12.3 Track T

Anti-mining commitment: this document is committed BEFORE any backtest is run. No
hyperparameters, feature weights, kill-rule interpretations, or feature construction
changes may occur after results are observed. Per masterplan §6: if the kill rule fires,
Track T ships benchmark_only and is not shadowed. There is no attempt #2 for Track T.

---

## 0. Scope and Motivation

**Target:** `cpi_headline` ONLY (CPIAUCSL MoM % SA, ALFRED initial prints).
**Shadow tag:** `mf_energy`
**Model class:** Mixed-frequency energy accumulator (Cleveland-style within-month energy accumulation).

**Motivation (from masterplan §12.3 MRI-R36):** The champion model is lag-based; institutional
CPI headline edges come from within-month energy accumulation (research REC-1/REC-12).
DCOILWTICO (WTI crude daily) is collected and effectively unrevised. GASREGW (weekly retail
gasoline, U.S. city average) is available from 1990. Both are at higher frequency than the monthly
CPI headline — this model builds an explicit within-month energy accumulator before falling back
to a statistical ex-energy AR.

This is a NEW FILES ONLY implementation: no edits to engine/release_forecast.py,
scripts/build_release_forecast.py, or any other existing producer/engine file.

---

## 1. Data Sources

### 1.1 GASREGW — Weekly Retail Gasoline (Regular, All Formulations)

**FRED ID:** GASREGW
**File:** `data/fred/GASREGW.parquet`
**Index:** DatetimeIndex, weekly (Monday of each reporting week)
**Column:** `gasoline_regular_weekly` (USD/gallon)
**Available:** 1990-08-20 onward (present in worktree)
**Revision status:** Effectively unrevised (BLS survey, no substantial revisions)
**PIT treatment:** Treated as `unrevised_legs` in provenance. At decision date D (asof), only
weeks whose Monday date <= D are available. No look-ahead: a week's price must have its
index date <= asof to be usable.
**Kill rule:** No-lookahead test in tests/test_release_mf_energy.py confirms that a WTI value
after asof does not change the nowcast.

### 1.2 DCOILWTICO — Daily WTI Crude Oil Price

**FRED ID:** DCOILWTICO
**File:** `data/fred/DCOILWTICO.parquet`
**Index:** DatetimeIndex, daily (business days)
**Column:** `wti_crude` (USD/barrel)
**Available:** 1986-01-02 onward (present in worktree)
**Revision status:** Effectively unrevised (EIA spot price)
**PIT treatment:** Treated as `unrevised_legs` in provenance. At decision date D (asof), only
days <= D are available. NaN rows (holidays, non-trading days) are excluded.
**No lookahead:** WTI values dated strictly after asof must NEVER appear in the
nowcast or training data (enforced in the accumulator and tested in test_release_mf_energy.py).

### 1.3 CPIAUCSL — CPI Headline (ALFRED Vintage Store)

**FRED ID:** CPIAUCSL
**Vintage file:** `data/fred_vintage/vintages.parquet` (shared store)
**Access:** Via `knowable_series(vintages, 'CPIAUCSL', asof)` from engine.release_forecast
**PIT treatment:** Full PIT — only initial prints with realtime_start <= asof are used.
**Target:** MoM % change = (value_M / value_{M-1} - 1) * 100. From ALFRED initial prints.

### 1.4 BLS CPI Relative Importance Weights

**File:** `data/release_forecast/component_weights/cpi_relative_importance_2026.yml`
**Key used:** `motor_fuel` (weight = 2.981) and `gasoline_all_types` (weight = 2.895)
**Weight to use for energy contribution pass-through:** See §2.2 — `gasoline_all_types` RI weight
= 2.895 (out of 100). This is the direct gasoline-in-headline basis weight.
**Revision status:** `revision_optimistic` — these are frozen BLS 2024-expenditure-weight
December 2025 basis; not ALFRED-vintaged. In effect Jan–Dec 2026.

---

## 2. Model Specification (FROZEN)

### 2.1 Leg 1: Reference-Month Gasoline MoM Nowcast

**Definition:** For a given reference month M (the CPI month being forecast), the gasoline
nowcast at decision date D is:

```
gasoline_ref_month_avg(M, D) = mean of GASREGW weekly prices for weeks whose
                                Monday date falls in calendar month M, where
                                that Monday date <= D (PIT filter)
```

**Published weeks in M:** Weeks with index date in [first_day_M, last_day_M] AND index date <= D.

**Remaining-weeks projection (WTI pass-through):**

When D falls within month M (i.e., there are remaining weeks in M not yet published), the
remaining-week gasoline prices are projected using daily WTI:

(a) Compute `gasoline_wti_beta` via expanding-window OLS of weekly GASREGW CHANGES on trailing
    daily-average WTI CHANGES over the same calendar week, using ALL weeks in [history, M-1]
    (i.e., weeks strictly before reference month M with both GASREGW and WTI data available
    at asof, EXCLUDING any weeks from M itself — no look-ahead). Beta is scalar: the regression
    of `delta_gasoline_weekly` on `delta_wti_weekly_avg` with a bias term.

(b) Compute remaining weeks as: weeks in M whose Monday date > D (the unpublished portion).
    For each remaining week, the WTI "projection" = average daily WTI over trading days in
    that week where date <= D (i.e., partially-complete weeks use available WTI days only;
    zero-WTI-day weeks are excluded). If no remaining weeks exist (D >= last day of M), skip.

(c) projected_gasoline_week = published_wti_mean_week * gasoline_wti_beta[1] + gasoline_wti_beta[0]
    (where gasoline_wti_beta[0]=intercept, gasoline_wti_beta[1]=slope).

(d) TRAINING LAW (strict no-look-ahead): the OLS training data for gasoline_wti_beta uses ONLY
    weeks in calendar months PRIOR TO M (strictly month < M). No weeks from M itself appear in
    beta estimation. This ensures the pass-through coefficient is estimated without knowledge of
    the reference month's outcome.

**Combined reference-month gasoline estimate:**
```
gasoline_est_M = mean([published_weeks_in_M] + [projected_remaining_weeks])
```

**Gasoline MoM:**
```
gasoline_mom_M = (gasoline_est_M / gasoline_est_{M-1} - 1) * 100
```

Where `gasoline_est_{M-1}` is the mean of all published GASREGW weeks in month M-1 (all should
be available at asof since M-1 has already passed). If M-1 has no weeks, gasoline_mom_M = None.

### 2.2 Leg 1: Energy Contribution

```
energy_contrib = gasoline_mom_M * (gasoline_all_types_ri_weight / 100.0) * gamma
```

Where:
- `gasoline_all_types_ri_weight` = 2.895 (from cpi_relative_importance_2026.yml, key `gasoline_all_types`)
- `gamma` = expanding-window OLS coefficient of CPI headline MoM on gasoline MoM, using
  ALFRED initial prints of CPIAUCSL and computed gasoline_mom from the SAME expanding window
  of historical months knowable at asof (training data: all months < M with both series available,
  using the historical GASREGW reference-month averages and ALFRED CPI initial prints as target).
  This gamma captures how much of a 1 pp gasoline MoM moves headline MoM after re-weighting.
  Gamma is a bivariate OLS: `cpi_hl_mom ~ beta0 + gamma * gasoline_mom_historical` estimated
  on the training window (expanding). Gamma = slope coefficient. If insufficient history
  (< 12 obs with both series), gamma = 1.0 (fallback, documented in provenance).
  **No look-ahead:** gamma is estimated on months < M only.
- `revision_optimistic_legs`: gasoline is unrevised; gamma uses CPI ALFRED initial prints (PIT).

### 2.3 Leg 2: Ex-Energy Series

**Definition:**
```
exenergy_mom_M_actual = cpi_hl_mom_M - energy_contrib_M
```

For HISTORICAL months (training data): apply the same `energy_contrib` construction
retrospectively using historical GASREGW and historical CPI initial prints. This creates a
synthetic `exenergy_mom` series for training.

**Note on self-consistency:** Both the energy_contrib and the exenergy_mom series are
constructed from the same `energy_contrib` formula (energy_contrib = gasoline_mom * ri_weight/100 * gamma).
The exenergy series is the DERIVED residual from the CPI initial print. This is PIT-consistent
because CPIAUCSL initial prints are used (not revised figures).

### 2.4 Leg 2: AR(3) + Seasonal Terms on Ex-Energy

```
exenergy_ar_M = AR(3) + sin(2π * ref_month_int / 12) + cos(2π * ref_month_int / 12)
```

Where `ref_month_int` ∈ {1, 2, ..., 12} is the calendar month of the reference period M.

The AR(3) model is estimated via expanding-window OLS (or equivalently ridge λ=1.0 consistent
with the aggregation head) on:
- Features: [exenergy_lag1, exenergy_lag2, exenergy_lag3, sin_term, cos_term]
- Target: historical exenergy_mom from the training window

This sub-model produces `exenergy_ar_M` (scalar, the AR+seasonal predicted value of ex-energy MoM).

### 2.5 Head Model

```
cpi_headline_mom_M ~ ridge(lambda=1.0) on [energy_contrib_M, exenergy_ar_M, sin_term, cos_term]
```

- Features (in this ORDER, frozen): energy_contrib, exenergy_ar, sin_term, cos_term
- Target: CPIAUCSL initial-print MoM % (from ALFRED)
- Estimator: Ridge(lambda=1.0, closed-form numpy, no sklearn/statsmodels/scipy)
- Walk-forward: expanding window, MIN_TRAIN_OBS=60 (consistent with champion)
- Z-scoring: expanding window (mean and std from training set at each step)
- Complete-case: if any feature is None at prediction time, that feature column is dropped
  and training rows with NaN in the remaining columns are excluded (same protocol as champion)
- Quantiles: empirical residual quantiles from the walk-forward residual history,
  MIN_QUANTILE_OBS=24

### 2.6 Dual-Cutoff Evaluation (MRI-R35)

This model is evaluated at BOTH cutoffs per MRI-R35:

**T-1 cutoff:** asof = day before the CPI release date for reference month M.
- At this point, all GASREGW weeks in M should be available (typical BLS publication
  pattern: the last week of M is published before the CPI release day).
- This is the PRIMARY kill-rule evaluation cutoff.
- `cutoff_label = 'T-1'`

**early cutoff:** asof ≈ 25 days before the CPI release date (mid-reference-month).
- Typically asof falls in the final days of month M or the first few days of M+1 (depending
  on M's calendar position relative to the release date).
- At this point, roughly 2-3 GASREGW weeks in M may be available; the remaining weeks
  are projected via the WTI pass-through (Leg 1's accumulator does real work here).
- This is the DESCRIPTIVE comparison cutoff; NOT subject to the kill rule.
- `cutoff_label = 'early'`

The `run_walk_forward_mf` function evaluates both cutoffs. For a given reference month M:
- T-1 step_asof = one day before realtime_start of the initial print (same convention as champion)
- early step_asof = T-1 asof - 25 days (approximation; WTI accumulator provides meaningful signal)

---

## 3. Kill Rule (FROZEN per MRI-R36 + MRI-R28)

Per masterplan §12.3 (Track T) and MRI-R28 (strongest-naive law):

**Kill benchmark (strongest naive):** max of {naive_prior MAE, expanding_mean MAE, trailing_3m MAE}
evaluated over the same walk-forward fold as the model.

**Kill condition (T-1 cutoff ONLY):** Model MAE >= strongest-naive MAE in BOTH:
  (a) the full window (all non-COVID predictions)
  (b) the 2021+ slice (2021-01 onward)

If kill fires → Track T ships benchmark_only; no shadow rows on forward ledger.
If kill does NOT fire → Track T is shadow-eligible; shadow tag `mf_energy`.

**Early cutoff:** Kill rule does NOT apply to the early cutoff. The early-cutoff comparison
against the champion (at its own early-cutoff asof) is descriptive only — it represents
Track T's VALUE CLAIM (does the within-month accumulator add early-read accuracy?). This
comparison is evaluated on the forward ledger only; the backtest provides the descriptive table.

---

## 4. Feature Availability Timeline

| Feature | Available from | Notes |
|---------|----------------|-------|
| gasoline_mom (GASREGW) | 1990-09+ (first month with ≥1 week) | Unrevised |
| wti_beta training data | 1990-09+ | Enough weeks for OLS after ~1yr of data |
| energy_contrib | 1990-09+ | Requires gasoline_mom and gamma |
| exenergy_mom (training) | 1997-02+ | Needs CPIAUCSL initial prints (1997+) |
| exenergy_ar (AR lags) | 1997-05+ (lag 3 of exenergy from 1997-02) | |
| sin/cos month terms | always | Deterministic |
| head model first prediction | ~1997-06 + 60 obs = ~2002-06 | MIN_TRAIN_OBS=60 |

---

## 5. Output Contract (Standard Projection Dict + mf_energy fields)

The `project_release_mf` function returns a dict matching the champion's projection schema:

```python
{
    "release": "cpi_headline",
    "model": "mf_energy",
    "asof": str,                   # ISO date
    "cutoff_label": str,           # 'T-1' or 'early'
    "point": float | None,
    "p10": float | None,
    "p25": float | None,
    "p50": float | None,
    "p75": float | None,
    "p90": float | None,
    "confidence": float | None,
    "input_completeness": float,
    "benchmark_set": {
        "naive_prior": float | None,
        "expanding_mean": float | None,
        "trailing_3m": float | None,
        "ar_model": float | None,
        "cleveland_nowcast": None,    # not implemented in mf_energy (champion handles)
        "market_implied": None,
    },
    "surprise_skew": {
        "sigma": float | None,
        "sigma_scale_pp": float | None,
        "tag": str | None,            # 'hotter' | 'inline' | 'cooler'
        "inline_band": 0.35,
    },
    "mf_energy_components": {
        "gasoline_mom": float | None,
        "energy_contrib": float | None,
        "exenergy_ar": float | None,
        "gasoline_ri_weight": 2.895,
        "gamma": float | None,
        "n_gasoline_weeks_published": int,
        "n_gasoline_weeks_projected": int,
        "gasoline_wti_beta_slope": float | None,
        "gasoline_wti_beta_intercept": float | None,
        "gasoline_wti_n_train": int,
    },
    "pit_provenance": {
        "revision_optimistic_legs": ["cpi_weights"],
        "unrevised_legs": ["gasoline_weekly", "wti_crude"],
        "absent_legs": [],
        "display_only": True,
        "authority": False,
    },
    "display_only": True,
    "authority": False,
}
```

---

## 6. Walk-Forward Protocol (run_walk_forward_mf)

`run_walk_forward_mf(root, cutoff='T-1'|'early')` evaluates BOTH cutoffs in a single call
(internally iterates over reference months and computes both step_asof values per month).

For each reference month M (from ALFRED initial prints of CPIAUCSL):

```
T-1 step_asof = (realtime_start of initial print for M) - 1 day
early step_asof = T-1 step_asof - 25 days
```

The backtest must:
1. Run the full walk-forward at the T-1 cutoff → report kill-rule verdict.
2. Run the full walk-forward at the early cutoff → report descriptive comparison only.
3. For head-to-head vs champion at early cutoff: also run the CHAMPION model
   (engine.release_forecast.run_walk_forward_full('cpi_headline', root)) with the
   SAME early step_asofs — champion features will naturally degrade mid-month.
   The comparison of mf_energy@early vs champion@early is the track's value claim.

---

## 7. ERA Tables (FROZEN)

Per MRI-R9 and MRI-R28:
- Era splits: full / pre_2010 / 2010_2020 / covid (2020-03..06) / 2020_recovery / 2021_plus
- COVID months (2020-03..2020-06) printed separately; NOT assigned to a main era cell
- Full window MAE: includes all non-COVID predictions
- Supplementary: 2021+ slice is REQUIRED for the kill rule
- Metrics per era: n, MAE_model, MAE_naive_prior, MAE_expanding_mean, MAE_trailing3m, MAE_ar_model,
  RMSE_model, coverage_p10_p90, skew_hit_rate, skew_wilson_ci, pinball_loss (5-quantile sum per MRI-R31)
- MAE_strongest_naive = max(MAE_naive_prior, MAE_expanding_mean, MAE_trailing3m) — kill-rule basis

---

## 8. PIT Law Declarations (per MRI-R6)

| Series / Input | PIT status | Declared |
|----------------|------------|----------|
| CPIAUCSL initial prints | PIT-safe via knowable_series | vintaged |
| GASREGW weekly | Unrevised, asof-filtered by date | unrevised_legs |
| DCOILWTICO daily | Unrevised, asof-filtered by date | unrevised_legs |
| CPI RI weights (YAML) | revision_optimistic (not ALFRED) | revision_optimistic_legs |
| gamma (OLS pass-through) | Estimated on training window only | vintaged (CPIAUCSL side) / unrevised (gasoline side) |

---

## 9. What Is NOT Changed

- Champion model (engine/release_forecast.py): UNCHANGED. This file is read-only for Track T.
- Forward ledger producer (scripts/build_release_forecast.py): UNCHANGED. Shadow wiring is
  deferred to W11-G (Round 2 serial integration) per masterplan §12.5.
- Any existing UI/template: UNCHANGED.
- Authority booleans: all False. display_only=True on all outputs.
- Word "validated": banned from user-facing copy (CI-enforced repo-wide).

---

## Amendment 2026-07-14 — energy_contrib formula correction (estimator defect)

**Date:** 2026-07-14
**Author:** Post-mortem fix (CPI June-2026 cold-print)
**Nature:** Estimator defect fix. Original frozen text in §2.2 is NOT modified.

### Original formula (defective)

Section 2.2 of the frozen prereg specified:

```
energy_contrib = gasoline_mom_M * (gasoline_all_types_ri_weight / 100.0) * gamma
```

This was implemented in `engine/release_mf_energy.py` at lines 636 and 1070 (pre-fix).

### The defect: double-discount

Gamma is estimated via bivariate OLS: `cpi_hl_mom ~ beta0 + gamma * gasoline_mom_historical`.
The OLS slope (gamma) is a reduced-form coefficient that **already embeds the basket weight**:
if gasoline moved by 1 pp MoM, gamma captures approximately how many pp of headline CPI
moves — including the pass-through from the ~2.895 pp basket share. Numerically, gamma ≈ 0.039
in the training history, close to the naive estimate ri_weight/100 ≈ 0.029.

By multiplying gamma by `(GASOLINE_RI_WEIGHT / 100.0)` a second time, the implementation
shrank energy_contrib by exactly `1 / (GASOLINE_RI_WEIGHT / 100.0) = 1/0.02895 ≈ 34.5x`
relative to the intent (ledger-confirmed on the 2026-07-13 row: defective energy leg
−0.010876 pp vs corrected −0.37567 pp).

The §2.2 prose states gamma "captures how much of a 1 pp gasoline MoM moves headline MoM
after re-weighting" — this description is consistent with the corrected formula below, not
the implemented one.

### Corrected formula

```
energy_contrib = gasoline_mom_M * gamma
```

GASOLINE_RI_WEIGHT is retained in provenance/components dict for reporting. The constant
is not removed from the codebase.

### June-2026 print context

- Shipped mf_energy point for 2026-06: **−0.206** (computed under defective formula)
- Actual headline CPI June-2026: **−0.4%** MoM
- Under the defective formula, energy leg = −0.0109 pp (gas_mom = −9.592 × ri_weight/100 = 0.02895 × gamma = 0.039165)
- Under the corrected formula, energy leg = **−0.3757 pp** (gas_mom = −9.592 × gamma = 0.039165)
- Causal channel: the ridge head z-scores its features, and z-scores are invariant under
  uniform column scaling — so the correction changes nothing through the direct energy
  channel. The point moves only through the derived ex-energy series
  (`exenergy = target − energy_contrib` now subtracts a 34.5× larger energy term), which
  re-fits the AR(3)+seasonal leg. Corrected 2026-07-13 dry-run point: **−0.2701**
  (vs −0.206 defective, vs −0.4 actual). The full-history backtest MAE worsens slightly
  under the correction — the expected consequence of subtracting a larger, noisier energy
  estimate from the AR target, not evidence against the correction.

All mf_energy backtest results produced before 2026-07-14 reflect the defective formula
throughout the full walk-forward history and **cannot support promotion or kill decisions**.
See RESULTS_MF_ENERGY_V1.md Addendum 2026-07-14 for corrected backtest tables.
