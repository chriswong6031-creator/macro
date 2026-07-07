# Pre-Registration V1 — NFP Decomposition + AHE/Hours Targets

**Frozen:** 2026-07-07
**Program:** Macro Release Intelligence (MRI), PR-H
**Branch:** feat/mri-w7-nfp-decomposition
**Status:** FROZEN — no model spec changes after this commit. Spec-attempt: NFP headline remains on attempt 1 (PREREG_V1.md). This document governs DISPLAY-ONLY decomposition machinery and TWO NEW TARGETS (ahe_mom, awh_level) each on their own attempt 1.

Anti-mining: exactly one spec per new target, frozen before any backtest results are observed.

---

## 0. Purpose and Scope

This document pre-registers:

a. NFP DECOMPOSITION (display-only) — private/government split, birth-death residual prior,
   revision-risk field, attached to the existing NFP projection dict as `components`.
b. NEW TARGET `ahe_mom` — avg hourly earnings MoM %, attempt 1 (frozen spec below).
c. NEW TARGET `awh_level` — avg weekly hours level, persistence-only spec (frozen below).

This PR does NOT change the frozen NFP headline feature spec (PREREG_V1.md §4). The NFP
headline ridge model is unchanged. These additions are purely display machinery and new targets.

---

## 1. Data Sources

### 1.1 ALFRED-Vintaged Series (PIT-safe via realtime_start filter)

| Series | Alias | Vintage Availability | Notes |
|--------|-------|---------------------|-------|
| USPRIV | private payrolls | 1939→ expected | thousands, SA |
| USGOVT | government payrolls | 1939→ expected | thousands, SA |
| CES0500000003 | avg hourly earnings total private | 2006-03→ | $/hr, SA |
| AWHAETP | avg weekly hours total private | 2006-03→ | hrs/wk, SA |
| JTSJOL | JOLTS openings | existing | thousands, SA |
| ICSA | initial claims | existing | weekly level |

PIT law: `knowable_series(vintages, series, asof)` returns only rows where
`realtime_start <= asof`. Only initial prints (earliest realtime_start per period) are used.

### 1.2 Non-Vintaged Sources

- `data/fred/AWHMAN.parquet` — manufacturing hours (existing; revision-optimistic per PREREG_V1.md).
- Walk-forward residual history from the NFP headline model (computed PIT inside the walk-forward).

---

## 2. NFP Decomposition (Display-Only)

### 2.1 Rationale

The BLS birth-death model table is WAF-blocked for automation (no reliable programmatic access).
The lawful substitute is a learned birth-death residual prior computed entirely from the
walk-forward history (PIT). No external table is scraped.

### 2.2 Decomposition Parts

Attached to `project_release("nfp", ...)` output as `components: {...}`.

**a. private_trend**
- Proxy: the model's ridge point prediction mapped to private payrolls space via the trailing
  mean share of USPRIV in PAYEMS. Specifically:
  `private_trend = model_point × mean(USPRIV_initial / PAYEMS_initial over trailing 12 initial prints)`
  where both series' initial prints are knowable at the decision date.
- Confidence classification: **proxy** (claims/withheld/ADP-driven prediction converted to
  private-payrolls space via a stable-but-derived ratio; per Codex §8.2).
- PIT: uses only initial prints of USPRIV and PAYEMS knowable at asof.

**b. government_trend**
- Source: mean of the last 3 USGOVT initial-print MoM changes knowable at asof.
- Confidence classification: **known-ish** (government hiring is slower-moving; the trailing
  3-month mean from initial prints is a low-noise reading even at the first release).
- PIT: uses only initial prints of USGOVT knowable at asof.

**c. birth_death_residual_prior**
- Definition: for each calendar month M (Jan..Dec), the trailing 5-year mean of
  `(PAYEMS_initial_print_MoM_change − model_fitted_value_for_that_step)`
  computed using only walk-forward history available at the decision date (PIT).
  The "model fitted value" for each historical step is the ridge prediction produced by the
  expanding walk-forward for that step — NOT a forward-looking fit.
- Implementation: computed inside the backtest walk-forward; for the live projection, uses
  the most recent 5-year trailing window of (actual − predicted) residuals, grouped by
  calendar month (the month of the target print), using only steps where period is knowable.
- Example: at a March NFP decision date, birth_death_prior = mean of (actual − predicted)
  for all March prints in the trailing 5-year walk-forward history.
- Confidence classification: **residual** (learned from model errors, not from any external
  source; reflects systematic model bias by month-of-year, not true BLS adjustment).
- PIT: the walk-forward residuals used are from strictly prior prediction steps (result_pos
  ordering enforced — no future residuals used).
- Output: scalar (thousands of jobs) for the current reference month.
- Also reported: a 12-month profile (Jan..Dec prior values) in the backtest artifact.

**d. residual**
- `residual = model_point − (private_trend + government_trend + birth_death_residual_prior)`
- Captures the unaccounted portion. Reported for transparency.
- Confidence classification: **residual**.

### 2.3 Revision-Risk Display Field

- Definition: mean and sign-rate of `(latest_revision − first_print)` for PAYEMS over the
  trailing 24 calendar months from available vintage data.
  - `mean_k`: mean of (revised − initial) in thousands of jobs.
  - `pct_upward`: fraction of periods where revised > initial.
- Source: ALFRED vintage parquet — initial-print rows (earliest realtime_start per period)
  vs. the LATEST available value for the same period (most recent realtime_start).
- Attached to the NFP projection output as `revision_risk: {mean_k: float, pct_upward: float}`.
- Descriptive. No authority implications.
- PIT: the "latest" revised value is whatever the most recent vintage row shows as of the
  full dataset (not asof-restricted); the initial-print IS asof-restricted for the comparison.

---

## 3. New Target: ahe_mom — Avg Hourly Earnings MoM %

### 3.1 Target Variable
`ahe_mom`: the initial-print MoM % change of CES0500000003 for reference month M.
Computed as: `(value[M] / value[M-1] - 1) * 100` on initial-print levels.

### 3.2 Decision Date
D = the trading day before the CES0500000003 release for month M (same as NFP — AHE is
released on the same BLS Employment Situation report as NFP). In the backtest, D is
computed from the ALFRED realtime_start of CES0500000003 for each period.

### 3.3 Evaluation Window
2006-03→ (first available vintage period). Minimum 60 observations before first prediction.
Era splits: pre-2010 (if data reaches), 2010-2020-02, 2021+.

### 3.4 Feature Set (FROZEN, Attempt 1)
1. **`ahe_mom_lag1`** — initial-print MoM CES0500000003 for period M-1 (most recent knowable)
2. **`ahe_mom_lag2`** — initial-print MoM CES0500000003 for period M-2
3. **`ahe_mom_lag3`** — initial-print MoM CES0500000003 for period M-3
4. **`awh_mom_last`** — MoM change in AWHAETP initial-print level (hours/wk) for last knowable
   period at D. PIT via ALFRED realtime_start. DROPPED if AWHAETP vintages absent.
5. **`jolts_mom_last`** — MoM % change of JTSJOL initial-print level for last knowable period
   at D. PIT via ALFRED realtime_start. DROPPED if JTSJOL vintages absent.
6. **`icsa_level_z`** — z-score of ICSA initial-print level for the NFP survey reference week
   (week containing the 12th of ref month M), normalized against the trailing 36 initial-print
   ICSA levels knowable at D. Proxy for labor-market tightness. DROPPED if ICSA absent.

All features built PIT-safe via `knowable_series(vintages, series, asof=D)`.

### 3.5 Model Spec (same as PREREG_V1.md §5)
- Ridge (lambda=1.0, closed-form numpy), z-scored features, expanding window, min 60 obs.
- Baselines: naive_prior (last initial print MoM), trailing_3m, AR3 (own 3 lags ridge).

### 3.6 Quantile Intervals
Same protocol as PREREG_V1.md §5.3: empirical residuals from walk-forward, min 24 obs.

### 3.7 Kill Rule (FROZEN, Attempt 1)
Model marked **benchmark_only** if:
MAE(model) >= MAE(naive_prior) in the full window AND the 2021+ slice.
Both conditions must hold. No second attempt without program-level adjudication.

### 3.8 Evaluation Metrics
Same as PREREG_V1.md §6.2: MAE, RMSE, coverage p10-p90, skew hit-rate + Wilson 95% CI.
Era splits: 2010-2020-02, 2021+. 2021+ era is the primary kill-rule slice.
(Pre-2010 era reported if data permits; AHE vintages begin 2006-03 so pre-2010 may be thin.)

---

## 4. New Target: awh_level — Avg Weekly Hours Level

### 4.1 Target Variable
`awh_level`: the initial-print level of AWHAETP for reference month M (hours/week).

### 4.2 Decision Date
Same as AHE: the day before the AWHAETP release for month M.

### 4.3 Evaluation Window
2006-03→ (first available AWHAETP vintage period).

### 4.4 Feature Spec: PERSISTENCE-ONLY (FROZEN, Attempt 1)
**Spec:** point = last initial-print AWHAETP level knowable at D (pure persistence).
No regression. This target exists as a **labor-demand context line**; hours barely move
month-to-month and a persistence model captures the first-order dynamics.

Quantiles from residual history (actual − last_known_level), same min 24 obs protocol.
Baselines: naive = same as model (the model IS naive here — reported explicitly).

**Explicit no-skill claim:** the model IS the naive baseline for this target. The persistence
model is not expected to beat the naive baseline — it IS the naive baseline. This is disclosed
explicitly in the output as `persistence_only: true`. No kill rule is needed because the model
makes no claim of skill; it exists to provide quantile context for the expected range of the
level print.

---

## 5. Producer Integration

The AHE and AWH targets ride the NFP release date (same BLS Employment Situation report).
`project_release("ahe", asof, root)` and `project_release("awh", asof, root)` are supported.
`scripts/build_release_forecast.py` may add these to `_TRACKED_RELEASES` if wiring is trivial;
otherwise they attach to the NFP block as subfields.

---

## 6. Provenance Declaration

**revision_optimistic_legs:** [] (all series are ALFRED-vintaged with PIT realtime_start filter)
**unrevised_legs:** [] (no non-vintaged legs in the new targets)
**authority:** false — display-only projections; all authority booleans False.

---

## 7. Codex §8.2 Confidence Classification Reference

- **known**: directly observable from initial prints with no model assumption.
- **proxy**: requires a conversion or model step to map to the target space.
- **residual**: learned from model errors; highest uncertainty.

Decomposition:
- government_trend: known-ish (direct initial-print mean from USGOVT).
- private_trend: proxy (ridge prediction mapped through USPRIV share).
- birth_death_residual_prior: residual (learned from walk-forward errors by month).
- residual: residual (unaccounted difference).

---

## 8. Registration Note

This pre-registration is committed BEFORE the backtest is run. The hash of this file at
commit time constitutes the frozen specification. Any deviation must be logged in an
amendment section below.

---

## AMENDMENTS

**AMENDMENT A (2026-07-08, post-review):** the trailing-5yr month-of-year BD residual
prior pool EXCLUDES residuals whose reference month falls in 2020-03..2020-06 (COVID
window — same exclusion window used throughout the MRI program). Reviewer-demonstrated
defect: without exclusion, April decision dates in 2021-2025 inherit the 2020-04 residual
(approximately −19,956k), producing ~−4,000k priors. Declared here as a disclosed
amendment; rule chosen for consistency with the program's existing COVID handling; no
winsorization knob added. Applies to both `build_nfp_components` and
`compute_bd_prior_12month_profile`. Field name `mean_pp_or_k` (§2.3) standardized to
`mean_k` throughout, consistent with the code implementation (n5 fix).
