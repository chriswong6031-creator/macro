# Pre-Registration V1 — Macro Release Intelligence: CPI & NFP Projection Models

**Frozen:** 2026-07-07  
**Program:** Macro Release Intelligence (MRI), PR-B  
**Branch:** feat/mri-w2-release-forecast  
**Status:** FROZEN — no model spec changes after this commit

---

## 0. Purpose and Anti-Mining Commitment

This document pre-registers the EXACT model specifications, feature sets, and kill rules for the
CPI and NFP walk-forward projection models BEFORE any backtest results are observed. Per the
masterplan anti-mining law: exactly ONE model spec per release type is declared here, frozen.
No weight tuning after results are seen. If v1 beats naive, that is printed. If v1 loses to naive,
that is ALSO printed. Results are not fixed.

---

## 1. Data Sources and PIT Law

### 1.1 Vintage (ALFRED) Sources — PIT-safe by realtime_start filter
All ALFRED-vintaged series obey the PIT law automatically: a value for period P is usable at
decision date D only if its `realtime_start <= D`. The `knowable_series(vintages, series, asof)`
function enforces this filter. No hand-waving is needed for publication lags — the ALFRED
realtime_start timestamps encode the actual publication date.

Series with ALFRED vintages in `data/fred_vintage/vintages.parquet`:
- `CPIAUCSL` — CPI All Urban Consumers (headline), monthly, 1997-01 to present
- `CPILFESL` — CPI Less Food & Energy (core), monthly, 1997-01 to present
- `PAYEMS` — Total Nonfarm Payrolls, monthly, 1997-01 to present
- `STICKCPIM157SFRBATL` — Sticky CPI, monthly, **2014-03 to present** (earlier: absent)
- `MEDCPIM158SFRBCLE` — Median CPI, monthly, **2014-02 to present** (earlier: absent)
- `FLEXCPIM157SFRBATL` — Flexible CPI, monthly, **2014-03 to present** (earlier: absent)
- `PPIFIS` — PPI Final Demand, monthly, **2014-03 to present** (earlier: absent)
- `ICSA` — Initial Claims (weekly), **2009-06 to present**
- `IC4WSA` — Initial Claims 4-Week Average (weekly), **2009-06 to present**
- `CCSA` — Continued Claims (weekly), **2009-09 to present**

### 1.2 Non-Vintaged Sources — declared as revision-optimistic or unrevised

**`AWHMAN` (Average Weekly Hours Manufacturing)** — `revision_optimistic_legs` list  
Sourced from `data/fred/AWHMAN.parquet` (latest-revised values). Used as proxy for "last
knowable" MoM at decision date D. The AWHMAN release schedule: published alongside NFP on
the first Friday of the next month. At decision date D (i.e., the day before NFP release for
month M), the last knowable AWHMAN is for month M-1. The revised value used here may differ
from the initial print; declared optimistic because the series is lightly revised in practice
(typical revision < 0.1 hours). **This leg is in the `revision_optimistic_legs` provenance.**

**`GASREGW` (Weekly Gasoline Prices)** — `unrevised_legs` list  
Sourced from `data/fred/GASREGW.parquet` when PR-A lands. This is an administrative survey
price series, essentially unrevised. If the file is absent, this leg is DROPPED and recorded in
provenance as `gasoline_absent: true`. **This leg is in the `unrevised_legs` provenance.**

**`data/treasury/withheld_taxes.parquet` (Daily Withheld Tax Receipts)** — `unrevised_legs` list  
Administrative Treasury fiscal data. Unrevised. Start date: **2023-02-14** (earliest available).
Used to compute YoY growth in rolling 30-day withheld taxes, aligned to the NFP survey reference
period. Due to this start date, the withheld-tax feature is only available from approximately
2024-02-14 onward (when a year-ago comparison exists). For prediction dates before 2024-02,
this leg is absent and treated as a zero-weighted dropped feature. **This leg is in the
`unrevised_legs` provenance.**

---

## 2. CPI Headline MoM — Spec v1 (FROZEN)

### 2.1 Target Variable
`cpi_headline_mom`: the initial-print MoM % change of CPIAUCSL for reference month M.  
Computed as: `(value[M] / value[M-1] - 1) * 100` on initial-print levels.

### 2.2 Decision Date
Prediction for month M is made at decision date D = the trading day before the CPIAUCSL
release for month M (i.e., the day before `realtime_start[M]` for CPIAUCSL). In the backtest,
D is computed from the ALFRED release calendar.

### 2.3 Feature Set (all knowable at D via realtime_start <= D)
1. **`cpi_hl_mom_lag1`** — initial-print MoM CPIAUCSL for month M-1 (the most recent knowable initial print at D)
2. **`cpi_hl_mom_lag2`** — initial-print MoM CPIAUCSL for month M-2
3. **`cpi_hl_mom_lag3`** — initial-print MoM CPIAUCSL for month M-3
4. **`sticky_mom_lag1`** — initial-print MoM STICKCPIM157SFRBATL for last knowable month; **DROPPED for periods before 2014-03** (leg absent)
5. **`median_mom_lag1`** — initial-print MoM MEDCPIM158SFRBCLE for last knowable month; **DROPPED for periods before 2014-02** (leg absent)
6. **`flex_mom_lag1`** — initial-print MoM FLEXCPIM157SFRBATL for last knowable month; **DROPPED for periods before 2014-03** (leg absent)
7. **`gasoline_mom`** — MoM change in weekly gasoline price (GASREGW) from the reference month M (week average) vs M-1 (week average); **DROPPED if GASREGW absent** (PR-A not yet merged)
8. **`ppi_mom_lag1`** — initial-print MoM PPIFIS for last knowable month at D; **DROPPED for periods before 2014-03** (leg absent). NOTE: PPI for month M releases AFTER CPI for month M. The ALFRED realtime_start filter handles this automatically — the last knowable PPI print at CPI decision date D is always for month M-1 or earlier.

PIT note: for each feature, `knowable_series(vintages, series, asof=D)` returns only rows where
`realtime_start <= D`, and we take the most recent such observation.

### 2.4 Feature Construction at Prediction Time
For each prediction step, only features with non-null values are used. Missing legs at a given
step reduce `input_completeness`. The feature matrix is rebuilt column-by-column; any column that
is entirely null for the training window to date is excluded from that step's model.

---

## 3. CPI Core MoM — Spec v1 (FROZEN)

### 3.1 Target Variable
`cpi_core_mom`: the initial-print MoM % change of CPILFESL for reference month M.

### 3.2 Decision Date
Same as CPI headline — the day before the CPILFESL release (same day as CPIAUCSL in practice).

### 3.3 Feature Set
Same as CPI Headline, MINUS feature #7 (gasoline_mom). Rationale: gasoline is excluded from
core CPI by definition.

Features:
1. **`cpi_core_mom_lag1`** — initial-print MoM CPILFESL for month M-1
2. **`cpi_core_mom_lag2`** — initial-print MoM CPILFESL for month M-2
3. **`cpi_core_mom_lag3`** — initial-print MoM CPILFESL for month M-3
4. **`sticky_mom_lag1`** — same as CPI headline spec (2014+ only)
5. **`median_mom_lag1`** — same as CPI headline spec (2014+ only)
6. **`flex_mom_lag1`** — same as CPI headline spec (2014+ only)
7. **`ppi_mom_lag1`** — same as CPI headline spec (2014+ only)

---

## 4. NFP MoM Change (thousands) — Spec v1 (FROZEN)

### 4.1 Target Variable
`nfp_mom_change`: the initial-print month-over-month CHANGE in PAYEMS for reference month M
(in thousands of jobs, i.e., `value[M] - value[M-1]` on initial-print levels).

**NFP evaluation window starts 2010** (claims vintage data begins 2009-06; minimum 60 obs
requires ~60 months of PAYEMS initial prints, which reaches back to 2010 with the claims feature).

### 4.2 Decision Date
Decision date D = the trading day before the PAYEMS release for month M (i.e., before its
`realtime_start` in the ALFRED data).

### 4.3 Feature Set
1. **`nfp_change_lag1`** — initial-print MoM change of PAYEMS for month M-1 (thousands)
2. **`nfp_change_lag2`** — initial-print MoM change of PAYEMS for month M-2 (thousands)
3. **`nfp_change_lag3`** — initial-print MoM change of PAYEMS for month M-3 (thousands)
4. **`claims_survey_week_icsa`** — ICSA averaged over the survey reference week for month M (the week containing the 12th of the month) minus same for month M-1. Uses initial-print ICSA values from ALFRED (realtime_start <= D). **DROPPED for periods before 2010** (claims vintages begin 2009-06, and first 6 months needed for reference-week alignment).
5. **`claims_survey_week_ccsa`** — Same construction as above using CCSA (continued claims). **DROPPED for periods before 2009-09** (CCSA vintages start).
6. **`withheld_tax_yoy`** — YoY % change in 30-day rolling sum of withheld tax receipts centered on the survey reference week for month M. Sourced from `data/treasury/withheld_taxes.parquet` (unrevised). **DROPPED for periods before 2024-02** (withheld_taxes starts 2023-02-14; need 12 months for YoY).
7. **`awhman_mom`** — MoM change in AWHMAN (average manufacturing hours) for month M-1 (the last knowable print at D, since AWHMAN releases with NFP). From `data/fred/AWHMAN.parquet` (revision-optimistic). Full history available.
8. **`adp_change`** — ADP same-month nonfarm employment change if available from `data/fred/ADPNFRPRIVSA.parquet`. **DROPPED if absent** (PR-A not yet merged). In the `unrevised_legs` list (ADP is not revised by FRED in the same way; treated as unrevised administrative data).

### 4.4 Survey Reference Week
The NFP survey reference week contains the 12th of the reference month. We identify all weekly
claim periods (ICSA period = Saturday of the week) where the 12th of month M falls between
period_date and period_date + 6 days. We average ICSA over this week's initial print, then
compute the difference vs the same computation for month M-1.

---

## 5. Model Specification (FROZEN)

### 5.1 Algorithm: Ridge Regression (Closed-Form, numpy Only)
- **No sklearn, no statsmodels, no scipy.stats** (house law).
- Ridge: `beta = (X'X + lambda * I)^{-1} X'y`, implemented in numpy.
- **Lambda = 1.0** (frozen; no cross-validation, no tuning).
- Features are **z-scored** using expanding-window mean and std estimated from the TRAINING rows
  only at each walk-forward step (no future leakage).
- If std of a feature in training window is zero (constant), that feature is dropped for that step.

### 5.2 Walk-Forward Protocol
- **Expanding window**: train on all rows with realtime_start < D, predict the next initial print.
- **Minimum 60 observations** before first prediction is emitted (no partial warm-up predictions).
- **Refit at every step**: the model is re-estimated from scratch at each prediction step; no
  warm-starting.
- **Prediction order**: steps are sorted chronologically by release date (realtime_start of the
  target print). This is the only correct order for an expanding-window walk-forward.

### 5.3 Quantile Intervals
- Residuals `r_t = actual_t - predicted_t` are accumulated from the walk-forward history.
- Quantile intervals (p10, p25, p50, p75, p90) are computed from the expanding residual
  history at each step.
- **Minimum 24 residuals** before quantiles are emitted; before that, quantiles are null.
- The quantile is centered on the ridge point prediction: `p_q = point + quantile(residuals, q)`.

### 5.4 Baselines
Three baselines, computed from the same expanding window of initial prints:
1. **`naive_prior`**: the most recent initial-print value (last known initial print).
2. **`trailing_3m`**: mean of the last 3 initial-print values (same as ar3 lags-only constant).
3. **`ar3`**: ridge (same lambda=1.0, same z-scoring) on OWN 3 lags only (no external features).

---

## 6. Evaluation Metrics (FROZEN)

### 6.1 Era Splits (mandatory per masterplan era law)
- **pre-2010**: reference months 1997-01 through 2009-12
- **2010-2020**: reference months 2010-01 through 2020-02 (pre-COVID)
- **2021+**: reference months 2021-01 through latest available

COVID months (2020-03 through 2020-06) reported as a SEPARATE row in NFP evaluation (both
included and excluded variants). For CPI: COVID months are included in the full-window metrics.

### 6.2 Metrics per Cell
- **MAE** (Mean Absolute Error): `mean(|actual - predicted|)`
- **RMSE** (Root Mean Squared Error): `sqrt(mean((actual - predicted)^2))`
- **n** (number of predictions in cell)
- **Coverage p10-p90**: fraction of actuals falling within [point + p10_residual, point + p90_residual]

### 6.3 Skew Direction Hit-Rate
For each prediction step where both a model point and a naive_prior value exist:
- `hit = 1` if `sign(model_point - naive_prior) == sign(actual - naive_prior)`, else 0.
- Pooled hit-rate across all steps in era.
- **Wilson 95% CI** per era: `_wilson(k=hits, n=total)`.

### 6.4 Kill Rule (FROZEN)
Model is marked **`benchmark_only`** if:
- Model MAE >= naive_prior MAE **in the full window AND the 2021+ slice**.

Both conditions must hold; failing only one does not trigger the kill.

---

## 7. Output Contract

`project_release(release: str, asof: date, root)` returns a dict:

```python
{
    "release": str,              # "cpi_headline" | "cpi_core" | "nfp"
    "asof": str,                 # ISO date
    "point": float | None,       # ridge point estimate
    "p10": float | None,         # 10th percentile of residual distribution
    "p25": float | None,
    "p50": float | None,
    "p75": float | None,
    "p90": float | None,
    "confidence": float | None,  # (1 - pctile(current_width / residual_widths)) * input_completeness
    "confidence_components": {
        "interval_rank": float | None,  # 1 - percentile of this interval width in history
        "input_completeness": float,    # fraction of possible features that were non-null
    },
    "input_completeness": float,
    "benchmark_set": {
        "naive_prior": float | None,
        "trailing_3m": float | None,
        "ar_model": float | None,
        "cleveland_nowcast": None,      # always None (not yet available)
        "market_implied": None,         # always None (not yet available)
    },
    "surprise_skew": {
        "sigma": float | None,          # (point - naive_prior) / residual_std
        "tag": str | None,              # "hotter" | "inline" | "cooler"
        "inline_band": 0.35,            # fixed band: |sigma| <= 0.35 -> "inline"
    },
    "pit_provenance": {
        "revision_optimistic_legs": list[str],
        "unrevised_legs": list[str],
        "absent_legs": list[str],
        "display_only": True,
        "authority": False,
        "n_train": int | None,
        "n_features_used": int | None,
        "gasoline_absent": bool,
        "withheld_tax_start": "2023-02-14",
    },
    "display_only": True,
    "authority": False,
}
```

---

## 8. Provenance Declaration

**revision_optimistic_legs**: ["awhman_mom"]  
**unrevised_legs**: ["gasoline_mom", "withheld_tax_yoy", "adp_change"]  

**authority**: false — this engine produces display-only projections. It does NOT escalate,
de-escalate, or condition any calibrated key. LLMs may not promote outputs of this engine to
signals or scores. Results printed plainly including nulls.

---

## 9. Registration Note

This pre-registration document is committed BEFORE the backtest is run. The hash of this file
at commit time constitutes the frozen specification. Any deviation from this spec must be logged
in a separate amendment file and noted in the RESULTS_V1.md deviations section.

---

## AMENDMENTS (post-run disclosures — 2026-07-07)

**These amendments are post-run disclosures only. They do not change the frozen model specification
(sections 1–8 above). No model weights or hyperparameters were changed after results were observed.**

### AMENDMENT A — Era gap: 2020-07..2020-12 unassigned (disclosed post-run)

PREREG §6.1 defines three eras: pre-2010, 2010-01..2020-02, and 2021-01+. The COVID block
(2020-03..2020-06) is explicitly carved out as a separate row. However, the period 2020-07
through 2020-12 was not assigned to any era in the frozen spec. This six-month "recovery gap"
was identified during the backtest review.

**Resolution:** These months are reported as a separate "2020_recovery" row in RESULTS_V1.md.
The kill rule uses the 2010+ window (NFP) and the full window (CPI), neither of which depends
on how these 6 months are classified. The kill rule outcome is unchanged by this disclosure.

### AMENDMENT B — Complete-case feature selection boundary (disclosed post-run)

The frozen spec (§5.2) describes an expanding-window walk-forward. An unspecified consequence
of the complete-case training design (§2.4, §5.1) is that once post-2014 features (sticky/median/
flex CPI, PPI) are present in the prediction row, pre-2014 training rows WITHOUT those features
are dropped from the training set for that step. This means:

1. The effective training window for post-2014 predictions is shorter than the "full expanding
   window" described in §5.2 — it excludes pre-2014 rows for which new features are missing.
2. Pooled residual quantiles used for coverage computation mix two distinct feature-set regimes:
   an own-lags-only regime (pre-2014 predictions) and a full-feature regime (post-2014 predictions).
   Coverage statistics blending these two populations have a different interpretation than
   within-regime coverage.

**Resolution:** RESULTS_V1.md reports a supplementary "2015+ stable feature set" row in each
era table. This row covers only predictions with reference month >= 2015-01, where the full
feature set is consistently present. No model specification changes were made.

### AMENDMENT C — NFP evaluation floor: pre-2010 rows excluded from "full" metrics (disclosed post-run)

PREREG §4.1 states "NFP evaluation window starts 2010." The walk-forward code trains on all
available PAYEMS history (beginning ~1997), but the first reported results use record indices 60+.
Some pre-2010 predictions are included in the walk-forward output. Per the frozen spec, these
pre-2010 NFP rows must NOT be included in the full-window evaluation metrics. The "full" NFP
metric row is therefore relabeled "full_2010_plus" and pre-2010 NFP predictions are excluded
from the reported n, MAE, RMSE, and coverage statistics. Pre-2010 rows still contribute to
model training (expanding window). This does not affect CPI evaluation.
