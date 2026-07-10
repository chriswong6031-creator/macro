# Pre-Registration V1 — NFP First→Third Revision-Direction Model (Track R)

**Frozen:** 2026-07-10
**Program:** Macro Release Intelligence (MRI), W11-D Track R
**Spec authority:** research/MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md §12.3 (MRI-R37)
**Branch:** claude/mri-w11-track-r
**Status:** FROZEN — no model spec changes after this commit. Attempt #1 of 2.

Anti-mining: exactly one spec, frozen before any backtest results are observed.

---

## 0. Purpose and Scope (verbatim from §12.3 MRI-R37)

> Track R (MRI-R37) — NFP first→third revision-direction model, attempt #1 of 2.
> Empirical basis from OUR vintage store: fp-surprise↔revision corr −0.60
> (−0.73 recent non-covid), walk-forward sign hit 63.8% vs 54.3% majority baseline,
> Wilson LB 55.1%, n=127 (research REC-1).

This document pre-registers the frozen target, feature set, estimator, kill rule, and
output contract for Track R. DISPLAY-ONLY: this model does not gate, score, or size
any position. No LLM-originated values. No sklearn, statsmodels, or scipy.stats (house law:
pure numpy/pandas only).

---

## 1. Target Variable (verbatim from §12.3 MRI-R37)

> Frozen target: sign(payems_mom_change[T, vintage=release(T+2)] −
> payems_mom_change[T, vintage=release(T)]) — the first→third revision to the
> MoM change, from a NEW multi-vintage PAYEMS store (ALFRED output_type=2, additive
> collector; the existing output_type=4 first-print pipeline is untouched).

### 1.1 Formal Definition

`target = sign(third_print_MoM_change[T] - first_print_MoM_change[T])`

where:
- `period T` = the NFP reference month
- `first_print_MoM_change[T]` = PAYEMS MoM change (thousands) as published at the
  FIRST release of month T (realtime_start = release(T), i.e., the Employment Situation
  report for month T, published ~5 weeks after month T ends)
- `third_print_MoM_change[T]` = PAYEMS MoM change (thousands) as published at the
  THIRD release of month T (realtime_start = release(T+2), i.e., two monthly Employment
  Situation reports later)

Output classes: `+1` (upward revision), `-1` (downward revision), `0` (no change — treated
as no-signal; excluded from hit-rate denominator per kill-rule evaluation).

MoM change: `value[T] - value[T-1]` on the SAME vintage matrix row (i.e., both the
period-T value and the period-(T-1) value come from the same vintage release for
consistency). In practice, ALFRED output_type=2 provides all vintages; first and third
prints are selected by realtime_start ordering.

### 1.2 Data Requirement

Requires the multi-vintage PAYEMS store:
`data/fred_vintage/payems_all_vintages.parquet`

Schema: `period` (datetime), `realtime_start` (datetime), `realtime_end` (datetime),
`value` (float).

Produced by `scripts/collect_payems_vintages.py` using `fetch_all_vintages("PAYEMS",
output_type=2)` from `collectors/fred.py` (ADDITIVE function; requires FRED_API_KEY).

**Fallback (key absent or store absent):** If the multi-vintage store is unavailable,
fall back to the FIRST→CUMULATIVE revision approximation: use output_type=4
(initial-print) vintages from `data/fred_vintage/vintages.parquet` as the first-print,
and the latest available value per period (most recent realtime_start) as a proxy for
the third print. This fallback is clearly labeled `basis: 'first_to_cumulative_fallback'`
in all outputs. The backtest and engine carry this label.

---

## 2. Feature Set (FROZEN, Attempt #1)

> Frozen features (pre-declared; the prior-revision feature EXCLUDED for leakage):
> fp_surprise_vs_AR1, sin/cos month, ICSA 4m survey-week change (first-print vintages).

All features are PIT-safe: only values with ALFRED realtime_start <= decision date D
are used (via `knowable_series` / `as_of_series`).

### 2.1 Decision Date (D)

D = the day BEFORE the first release (Employment Situation report) for reference month T.
In the walk-forward, D is derived from the realtime_start of the first PAYEMS vintage
for period T minus 1 calendar day.

**Rationale:** the first print lands on the Employment Situation release date. A
revision-direction forecast is made PRE-RELEASE (we do not know the first print yet;
we are predicting whether it will be revised up or down).

### 2.2 Feature 1: `fp_surprise_vs_AR1`

**Definition:** the difference between the first-print PAYEMS MoM change for period
T-1 (the most recent first print at decision date D) and the AR(1) one-step forecast
of that change.

AR(1) forecast: estimated via expanding-window ridge(λ=1.0) on the last 12 first-print
MoM changes knowable at D (same lambda, same z-scoring protocol, min 12 obs for AR).
If fewer than 12 obs are available, use the expanding mean of first-print MoM changes.

`fp_surprise_vs_AR1 = first_print_MoM_change[T-1] - AR1_forecast[T-1]`

**Rationale from §12.3:** fp-surprise↔revision correlation −0.60 (−0.73 recent
non-covid). Large positive surprise (first print > AR1) → tends to be revised DOWN.
Large negative surprise → tends to be revised UP.

**PIT:** uses only first-print PAYEMS initial_print series knowable at D.

**Leakage exclusion:** the prior-revision feature (how T-2's revision turned out) is
EXPLICITLY EXCLUDED per MRI-R37 ("the prior-revision feature EXCLUDED for leakage").
This prevents any indirect look-ahead via the revision history.

### 2.3 Feature 2: `sin_month`

`sin_month = sin(2 * pi * (T.month - 1) / 12)`

Calendar seasonality. T.month is the reference month of the NFP print being predicted.
Pure deterministic, no PIT concern.

### 2.4 Feature 3: `cos_month`

`cos_month = cos(2 * pi * (T.month - 1) / 12)`

Calendar seasonality pair to sin_month.

### 2.5 Feature 4: `icsa_4m_survey_week_change`

**Definition:** the change in the 4-month average of ICSA initial-print levels over the
survey-reference-week for period T-1 vs T-5 (four-month change in the 4-week
average surrounding the survey week).

Survey reference week = the week containing the 12th of the reference month (same
convention as the NFP walk-forward model per PREREG_V1.md §4.4).

`icsa_4m_change = survey_week_icsa(T-1) - survey_week_icsa(T-5)`

where `survey_week_icsa(M)` = the ICSA initial-print level for the week containing
the 12th of month M, using only rows with realtime_start <= D.

**DROPPED** if ICSA vintages unavailable at D (leg absent, recorded in provenance).

**Rationale:** labor market momentum at the survey reference period captures the
underlying hiring pace; the 4-month window smooths weekly noise.

---

## 3. Model Specification (FROZEN)

> Estimator: ridge(λ=1.0) on z-scored features → sign; MIN_TRAIN_OBS=60;
> COVID months excluded from era stats.

### 3.1 Algorithm

- Ridge regression (closed-form numpy): `beta = (X'X + λI)^{-1} X'y`
- **Lambda = 1.0** (frozen; no cross-validation)
- Features z-scored using expanding-window mean and std from training rows only
  (no future leakage; constant features divided by 1)
- Output: `y_hat` (continuous score) → `sign(y_hat)` for the directional call
- If `abs(y_hat) < threshold` the model outputs `none` (no directional lean);
  threshold = `strength_threshold = 0.10` (in z-score units of the residual distribution,
  provides a dead-band for noise). "none" maps to no display.

### 3.2 Walk-Forward Protocol

- **Expanding window**: train on all (period, target) pairs whose target is KNOWN
  (i.e., period T's third print is available) AND whose decision date D < current step
- **Minimum 60 observations** before first prediction is emitted
- **Refit at every step** from scratch
- **COVID exclusion from ERA STATS only**: steps where T ∈ 2020-03..2020-06 are
  run and included in training but EXCLUDED from era-split hit-rate tables

### 3.3 Training Target

In the walk-forward, the target `y_train` = first-minus-third revision sign for
historically completed revision pairs. Only pairs where BOTH first and third print
are available (third print = release(T+2) has landed) can serve as training rows.

### 3.4 Baselines

1. **majority_class**: predict the majority sign class over the expanding training window
2. **sign_of_negative_fp_surprise**: `sign(-fp_surprise_vs_AR1)` — i.e., negative
   surprise → predict upward revision; positive → predict downward (mechanistic baseline)

---

## 4. Kill Rule (FROZEN)

> Kill rule (sign target): walk-forward hit-rate Wilson LB must exceed the majority-class
> base rate in the full non-covid window; else no display.

**Formal kill rule:**

Let:
- `HR` = fraction of non-null, non-zero-target walk-forward steps (full non-covid
  window) where `model_sign == actual_revision_sign`
- `n` = count of such steps
- `Wilson_LB(HR, n)` = lower bound of Wilson 95% CI
- `majority_base_rate` = fraction of non-covid steps where actual revision sign ==
  majority class

**Kill triggered** (no display): `Wilson_LB(HR, n) <= majority_base_rate`

"Full non-covid window" excludes reference months 2020-03..2020-06.

---

## 5. Output Contract (DISPLAY-ONLY)

### 5.1 `compute_revision_lean(asof, root)` Return Value

```python
{
    "lean": "up" | "down" | "none",   # directional call; "none" if model low-confidence
    "strength": float,                 # abs(y_hat) — raw ridge score magnitude
    "model_hit_rate_backtest": float | None,  # walk-forward HR, non-covid full window
    "n_backtest": int | None,          # n steps used
    "basis": "first_to_third" | "first_to_cumulative_fallback",
    "display_only": True,
    "authority": False,
}
```

`lean` is "none" if:
- `abs(y_hat) < strength_threshold (0.10)`, or
- fewer than MIN_TRAIN_OBS (60) training rows available, or
- model is killed (Wilson LB <= majority_base_rate)

### 5.2 `compute_revision_context()` Return Value (DESCRIPTIVE, no model)

```python
{
    "level_bias_annotation": {
        "expansion_mean_cumulative_revision_k": 216,
        "contraction_mean_cumulative_revision_k": -262,
        "note": (
            "LEVEL-BIAS ONLY: expansionary NFP prints tend to be cumulatively "
            "revised up (+216k mean), contractions down (-262k). "
            "This is a level-bias in cumulative revisions — MoM-change bias "
            "is NOT significant and must not be implied. "
            "Era-conditional; sourced from research/release_forecast/PREREG_NFP_REVISION_V1.md."
        ),
        "display_only": True,
        "authority": False,
        "source": "MACRO_RELEASE_INTEL_MASTERPLAN_BY_FABLE.md §12.3 MRI-R37",
    }
}
```

**Critical boundary:** the level-bias annotation is NEVER displayed next to MoM
change projections or combined with the revision_lean directional call in any way
that implies a MoM-change edge. These are SEPARATE display blocks with different
empirical bases.

### 5.3 Scoring

The `revision_lean` field is frozen on the ledger at the T-1 decision date and scored
forward when the third print (T+2 Employment Situation release) lands. Scoring is
tracked by the nightly pipeline (W11-G integration, out of scope for this PR).

---

## 6. Provenance Declaration

**basis:** "first_to_third" when multi-vintage PAYEMS store available; else
"first_to_cumulative_fallback"
**revision_optimistic_legs:** [] (all features are ALFRED-vintaged PIT)
**unrevised_legs:** [] (no non-vintaged legs)
**display_only:** true
**authority:** false — never conditions any calibrated key or scoring signal

---

## 7. Data Adoption: Multi-Vintage PAYEMS Collector

New FRED collector function (ADDITIVE to collectors/fred.py):
`fetch_all_vintages(series_id, output_type=2)` — fetches the full vintage matrix
(all revisions) for a series. Schema: `period`, `realtime_start`, `realtime_end`,
`value`.

New collector script: `scripts/collect_payems_vintages.py`
Output: `data/fred_vintage/payems_all_vintages.parquet`

The existing `fetch_vintages()` / output_type=4 pipeline (initial releases only)
is UNTOUCHED.

---

## 8. Registration Note

This pre-registration is committed BEFORE the backtest is run. The hash of this file
at commit time constitutes the frozen specification. Any deviation must be logged in
an amendment section below.

---

## AMENDMENTS

### Amendment 1: Training-label PIT compliance fix (2026-07-10)

**Filed by:** Track R build agent (attempt #1 re-run).
**Nature:** Implementation bug correction — the frozen spec is UNCHANGED.

**Bug:** `run_revision_walk_forward` in `engine/release_revision_model.py`
trained on all `records[:i]` regardless of whether each row's label (the
third-print MoM direction) had been published by the fold's `decision_date`.
This violated the expanding-window PIT requirement in §3.2 ("train on all
(period, target) pairs whose target is KNOWN ... AND whose decision date D <
current step") — specifically the "target is KNOWN" clause was not enforced.

**Fix:** Each record now carries `label_observable_date` (= `third_release_date`
from `build_revision_target_df`).  At fold i, `run_revision_walk_forward`
filters `records[:i]` to rows where `label_observable_date <= pred_decision`
before building the training matrix.  Rows without `label_observable_date`
(backward-compatible paths) are included unconditionally.

**Prior run (voided):** Wilson LB 0.5375, HR 0.601, n_dir=238 — inflated by
look-ahead, kill verdict was technically correct but founded on contaminated data.

**Corrected run (attempt #1):** Wilson LB 0.5057, HR 0.569, n_dir=239, basis
first_to_third.  Kill STANDS: Wilson LB 0.5057 <= majority_base_rate 0.547.

**Additional nit fixes (no spec change):**
- §1 target definition typo: second term corrected from `vintage=release(T+2)`
  to `vintage=release(T)` to match §12.3 MRI-R37 masterplan verbatim.
- RESULTS note corrected: pre-2010 era directional count noted accurately (n=74,
  not "typically 0"); n_directional reconciliation note added.
