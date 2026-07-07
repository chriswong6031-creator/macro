# Pre-Registration V2 — MRI CPI Component Upgrade (Shelter Stock-Adjustment Leg)

**Frozen:** 2026-07-07 (written BEFORE backtest_v2 was run)
**Program:** Macro Release Intelligence (MRI), PR-G
**Branch:** feat/mri-w7-cpi-components
**Spec attempt:** #2 of 2 for BOTH cpi_headline and cpi_core (per masterplan §9, MRI-R18)
**Status:** FROZEN — no model spec changes after this commit

Anti-mining commitment: this document is committed BEFORE the backtest is run. No
hyperparameters, feature weights, or kill-rule interpretations may change after
results are observed. Per the masterplan: if attempt #2 fails a target's kill rule,
that target goes benchmark-only; there is no v3 without a program-level adjudication.

---

## 0. Scope

This pre-registration covers ONLY the CPI family (cpi_headline and cpi_core). NFP
is unchanged from PREREG_V1.md and owned by a parallel agent (engine/release_components_nfp.py).
All NFP spec, kill rules, and results are unchanged.

---

## 1. Data Sources — New in V2

### 1.1 ZORI (Zillow Observed Rent Index) — shelter proxy leg

**Source:** `data/zori/national.parquet` (written by `scripts/collect_zori.py`, which
fetches Zillow's public CSV endpoint keylessly — no paid data, no API key).

**Format:** date-indexed (end-of-month Timestamp), single column `zori` (USD/month,
all-home-types smoothed national series). History: 2015-01-31 through latest available
(137 months as of 2026-07-07, latest = 2026-05-31).

**Publication lag:** Zillow publishes ZORI approximately 30-45 days after the reference
month (source: `scripts/collect_zori.py` docstring: "approximately a 1-month lag";
pit_lag_days=30). Conservative PIT encoding: at decision date D, ZORI data is knowable
only for months t where t.end_of_month + 45 days <= D. Because the lease-reset window
uses months t-12..t-6 relative to the target month (see §2.3a), the most recent month
in this window must have its end-of-month + 45 days <= D. We implement this as: filter
ZORI rows where date + 45 days <= asof date (conservative +1-month lag in practice).

**Revision status:** ZORI is periodically re-benchmarked by Zillow (minor revisions).
Declared: `revision_optimistic_legs`. The series is not ALFRED-vintaged.

### 1.2 CPI Shelter (CUSR0000SAH1) — BLS momentum leg

**Source:** `data/fred/CUSR0000SAH1.parquet` — BLS CPI Shelter series (index levels,
seasonally adjusted, monthly). Column name: `cpi_shelter`. Index: DatetimeIndex
(monthly, first of month convention). History: 1947-01 through latest available.

**Publication lag:** Released on the same day as CPIAUCSL/CPILFESL (the CPI release
day). At decision date D (the day BEFORE the CPI release for month M), the last knowable
shelter print is for month M-1. In walk-forward, the step_asof is the day before
realtime_start of the target print — same PIT alignment as all other features.

**Revision status:** CUSR0000SAH1 is sourced from `data/fred/` (latest-revised, not
ALFRED-vintaged). Declared: `revision_optimistic_legs`. Revisions to shelter CPI are
typically minor; this is the established BLS series.

**Note:** No ALFRED vintage is available for CUSR0000SAH1 in the current parquet at
`data/fred_vintage/vintages.parquet`. The revised basis is declared per the PIT law.

---

## 2. Shelter Stock-Adjustment Model — FROZEN

### 2.1 Overview

The shelter stock-adjustment leg (`shelter_nowcast`) blends two signals:
1. **CPI shelter MoM momentum** (`cpi_shelter_mom_last`) — lagged by 1 month (the last
   knowable initial print of the BLS shelter index before the target month releases).
2. **ZORI lease-reset signal** (`zori_signal`) — the mean ZORI MoM change over the
   lease-reset window months t-12 through t-6 (7 monthly observations (M-6..M-12 inclusive)
   of new-lease rent data that leads CPI shelter via renewal smoothing and the BLS
   6-month quote construction cycle).
   [AMENDMENT 2026-07-07: corrected "6 months" to "7 monthly observations (M-6..M-12 inclusive)";
   the worked example on line 81 and the code (range(6,13)) were already correct — text-only fix.]

### 2.2 ZORI Signal Construction (FROZEN)

Given target month M (the month we are forecasting):
- Lease-reset window: months t-12 through t-6, where t = M.
  Example: forecasting M=2026-06, window = 2025-06 through 2025-12 (7 months).
- ZORI MoM for each month t: (ZORI[t] / ZORI[t-1] - 1) * 100.
- `zori_signal` = mean of ZORI MoM over the 7 monthly observations (M-6..M-12 inclusive)
  that fall in [M-12, M-6]. (Both endpoints inclusive; M-6 is the 6th month back from
  target, M-12 the 12th — 7 months total.)
  [AMENDMENT 2026-07-07: corrected "6 months" → "7 monthly observations (M-6..M-12 inclusive)";
  code was correct; text-only error.]
- ZORI months are end-of-month indexed; month M-k is derived by offsetting M by -k calendar months.
- PIT filter: only ZORI rows where date + 45 days <= asof_date are usable (§1.1).

### 2.3 CPI Shelter MoM Momentum (FROZEN)

- `cpi_shelter_mom_last` = MoM % change in CUSR0000SAH1 for the last knowable month
  at decision date D. Since CPI shelter releases with CPI, the last knowable month at D
  (the day before CPI release for month M) is for month M-1.
- MoM = (CUSR0000SAH1[t] / CUSR0000SAH1[t-1] - 1) * 100.

### 2.4 Blending Formula (FROZEN)

```
shelter_nowcast[M] = (1 - k) * cpi_shelter_mom_last + k * zori_signal
```

Where:
- **k = 0.35** (frozen; no tuning after results).
- `cpi_shelter_mom_last` = last-knowable CPI shelter MoM at D.
- `zori_signal` = mean ZORI MoM over months M-12..M-6 (PIT-filtered).

### 2.5 Divergence Guard (FROZEN)

If |zori_signal - cpi_shelter_mom_last| > 3 * sigma_shelter, then k is halved to 0.175.

Where:
- sigma_shelter = rolling 24-month std of cpi_shelter_mom_last values (computed from
  the same expanding window of shelter MoM values visible at D — no look-ahead).
- Purpose: anti-"Zillow already fell" trap. When ZORI and CPI shelter strongly disagree
  (> 3 sigma), shrink to BLS momentum signal (reduce ZORI weight).
- If sigma_shelter is not available (< 24 months of shelter data), divergence guard is
  bypassed (k remains 0.35).
- The applied k value (0.35 or 0.175) is published in provenance as `shelter_k_applied`.

### 2.6 Missing Data Handling (FROZEN)

- If ZORI data is absent or zori_signal cannot be computed (insufficient PIT-filtered
  rows): `shelter_nowcast` = `cpi_shelter_mom_last` (pure BLS momentum, k falls to 0).
  Recorded in provenance as `zori_signal_absent: true`.
- If cpi_shelter_mom_last is also absent: the shelter_leg feature is set to None and
  dropped from the model (no imputation). Recorded in provenance as `shelter_absent: true`.
- If the lease-reset window contains fewer than 3 usable ZORI months (PIT or coverage
  constraint): zori_signal = None → shelter_nowcast = cpi_shelter_mom_last (fallback).

---

## 3. V2 Feature Sets (FROZEN)

### 3.1 CPI Headline V2

All V1 features PLUS the shelter leg. Feature list (ORDER PRESERVED — walk-forward
and ridge solver depend on consistent ordering):

1. `cpi_hl_mom_lag1` — initial-print MoM CPIAUCSL for month M-1 (unchanged from V1)
2. `cpi_hl_mom_lag2` — initial-print MoM CPIAUCSL for month M-2 (unchanged from V1)
3. `cpi_hl_mom_lag3` — initial-print MoM CPIAUCSL for month M-3 (unchanged from V1)
4. `sticky_mom_lag1` — initial-print MoM STICKCPIM157SFRBATL (2014-03+; unchanged from V1)
5. `median_mom_lag1` — initial-print MoM MEDCPIM158SFRBCLE (2014-02+; unchanged from V1)
6. `flex_mom_lag1` — initial-print MoM FLEXCPIM157SFRBATL (2014-03+; unchanged from V1)
7. `ppi_mom_lag1` — initial-print MoM PPIFIS (2014-03+; unchanged from V1)
8. `gasoline_mom` — weekly gasoline MoM (GASREGW, unrevised; unchanged from V1)
9. `shelter_nowcast` — NEW: shelter stock-adjustment leg per §2 above.
   Available: 2015-01+ (ZORI history starts 2015-01; CPI shelter available full history;
   but lease-reset window requires ZORI months M-12..M-6, so first usable M = 2016-01
   when ZORI has at least 7 months of history). Before 2016-01: shelter_nowcast = None
   (leg dropped for those steps).

### 3.2 CPI Core V2

All V1 features PLUS the shelter leg (gasoline excluded from core by definition):

1. `cpi_core_mom_lag1` — initial-print MoM CPILFESL for month M-1 (unchanged from V1)
2. `cpi_core_mom_lag2` — initial-print MoM CPILFESL for month M-2 (unchanged from V1)
3. `cpi_core_mom_lag3` — initial-print MoM CPILFESL for month M-3 (unchanged from V1)
4. `sticky_mom_lag1` — unchanged from V1
5. `median_mom_lag1` — unchanged from V1
6. `flex_mom_lag1` — unchanged from V1
7. `ppi_mom_lag1` — unchanged from V1
8. `shelter_nowcast` — NEW: same construction as headline (§2 above).

### 3.3 Feature Availability Timeline

| Feature | Available from |
|---------|----------------|
| own lags (all 3) | 1997-05 (first 3 CPIAUCSL/CPILFESL MoM lags) |
| sticky/median/flex/ppi | 2014-02+ (per PREREG_V1.md) |
| gasoline | 2015+ (GASREGW available when PR-A merges) |
| shelter_nowcast | ~2016-01+ (ZORI lease-reset window needs M-12..M-6 ≥ Jan 2015) |

The complete-case design means shelter_nowcast is absent for pre-2016 steps; those
steps train and predict with V1 features only (no change to pre-2016 behavior).

---

## 4. Component Contributions (Display Machinery — FROZEN)

### 4.1 Feature-to-Block Grouping

After model fit, each feature's contribution in percentage-point terms is:
```
contrib_pp[i] = beta_i * z_i
```
where beta_i is the fitted ridge coefficient and z_i is the z-scored feature value.

This follows from the ridge prediction formula: y_hat = sum_i(beta_i * z_i) + bias.
So sum of contrib_pp + bias = point prediction.

Feature blocks (frozen groupings):

| Block name | Features included |
|---|---|
| `energy` | `gasoline_mom` |
| `shelter` | `shelter_nowcast` |
| `core_persistence` | `{own}_lag1`, `{own}_lag2`, `{own}_lag3`, `sticky_mom_lag1`, `median_mom_lag1`, `flex_mom_lag1` |
| `pipeline` | `ppi_mom_lag1` |

For CPI core (no gasoline): `energy` block is absent.

### 4.2 Confidence V2 (FROZEN)

In addition to confidence_v1 (unchanged — interval_rank * input_completeness per V1
spec), a second confidence measure is computed: confidence_v2.

Known/Proxy/Residual classification of blocks:

| Block | Classification | Confidence weight |
|---|---|---|
| `energy` (gasoline) | **known** — direct observed price for reference month | w=1.0 |
| `shelter` (shelter_nowcast) | **proxy** — ZORI leads by ~6m, not a direct measure | w=0.6 |
| `pipeline` (ppi) | **proxy** — leading indicator, PIT-lagged | w=0.6 |
| `core_persistence` (own lags, sticky/median/flex) | **residual** — what features cannot see | w=0.0 |

Note: "residual" here means the block captures autocorrelation structure that the
model sees, but in terms of predictability class, persistence features are categorized
as modeling the residual not-directly-observed component.

confidence_v2 formula (FROZEN):
```
w_block = |contrib_pp[block]| / sum_all_blocks(|contrib_pp|)   (share of |prediction|)
c_raw = sum over blocks of (w_block * confidence_weight[block])
confidence_v2 = c_raw * input_completeness
```
If sum of |contrib_pp| is zero (degenerate prediction), confidence_v2 = 0.

Published alongside confidence (V1) — do NOT remove confidence (V1) from the output dict.

### 4.3 Components Output (FROZEN)

The projection dict gains a new key `components` (list of dicts):

```python
[
    {
        "name": "energy",           # block name
        "contrib_pp": float,        # beta_i * z_i summed over block features
        "confidence": 1.0,          # known/proxy/residual weight (constant per block)
    },
    {
        "name": "shelter",
        "contrib_pp": float,
        "confidence": 0.6,
    },
    {
        "name": "core_persistence",
        "contrib_pp": float,
        "confidence": 0.0,
    },
    {
        "name": "pipeline",
        "contrib_pp": float,
        "confidence": 0.6,
    },
]
```

`components` is None if point prediction is None (no model fit) or if no features
were available. Only blocks with at least one available feature are included.

### 4.4 Tolerance Check

The sum of all contrib_pp values should equal (point - bias), where bias is the
intercept from the ridge fit. In practice, due to z-scoring and complete-case
handling: sum(contrib_pp) may differ from (point - bias) by at most 1e-8 (float
precision). The tests enforce tolerance <= 1e-6.

---

## 5. Known/Proxy/Residual Decomposition — Input Completeness Tracking (FROZEN)

The existing `input_completeness` (fraction of all possible features that are non-null)
is unchanged. Additionally, for v2 we track:

- `w_known` = fraction of |contrib_pp| from "known" blocks.
- `w_proxy` = fraction of |contrib_pp| from "proxy" blocks.
- `w_residual` = fraction of |contrib_pp| from "residual" blocks.
- These three sum to 1.0 (or 0.0 if all zero).
- Published in `confidence_components_v2` alongside confidence_v2.

---

## 6. Kill Rules — V2 (UNCHANGED FROM V1)

Kill rule for spec attempt #2 (FROZEN, identical to PREREG_V1.md §6.4):

Model is marked **`benchmark_only`** if:
- Model MAE >= naive_prior MAE **in the FULL window AND the 2021+ slice**.

Both conditions must hold; failing only one does NOT trigger the kill.

If the kill triggers for a target in v2: that target goes benchmark-only. There is no
v3. The benchmark_only status is recorded in RESULTS_V2.md and a DO_NOT_REBUILD row
is appended to research/DO_NOT_REBUILD.md.

Note on kill rule interpretation: the V1 result for cpi_core is:
- Full: MAE model=0.0924 vs naive=0.0991 → model beats (kill NOT triggered on full)
- 2021+: MAE model=0.1355 vs naive=0.1297 → model loses in 2021+

In V1, cpi_core is ACTIVE because full-window beats naive (kill requires BOTH). V2
must show improvement or neutral in the 2021+ slice to make the model more useful;
but the kill rule is the same threshold.

---

## 7. Evaluation Metrics — V2 (FROZEN)

Identical to PREREG_V1.md §6, with additions:

### 7.1 Era Splits (unchanged)
Same era classification: pre-2010 / 2010-2020 / COVID 2020-03..06 / 2020_recovery /
2021+. Supplementary 2015+ stable-feature row (unchanged).

### 7.2 V1 vs V2 Comparison (new in V2 results)
RESULTS_V2.md reports a side-by-side V1-vs-V2 table per era per target:
Columns: era, n, MAE_v1, MAE_v2, MAE_naive, coverage_v1, coverage_v2, skew_hr_v1, skew_hr_v2.

### 7.3 Additional V2 Metric Rows
- `2015_plus_stable_v2`: predictions with reference month >= 2016-01 (when shelter leg
  becomes available; shelter fully active). This is the primary window to evaluate
  whether the shelter leg adds value.

### 7.4 Conditional Skew HR (unchanged from V1)
Reported as in V1: only steps where sign(model-naive) != 0.

---

## 8. PIT Law — V2 Additions

### 8.1 ZORI PIT
`zori_signal` uses only ZORI rows where date + 45 days <= asof_date (conservative lag).
This is implemented in `engine/release_components_cpi.py` in the `_compute_zori_signal`
function. In the walk-forward backtest, each step's asof is the day before the target
release date (same as V1 convention); the ZORI filter is applied per-step.

### 8.2 Shelter CPI PIT
CUSR0000SAH1 is latest-revised (not ALFRED-vintaged). Declared revision_optimistic.
In walk-forward steps, the series is read with index <= asof to simulate knowability,
but this uses the revised series not the initial print. Per PIT law, this leg is in
`revision_optimistic_legs`.

### 8.3 Provenance Fields Added in V2
- `shelter_nowcast_value`: the computed shelter_nowcast for this step (float | None).
- `zori_signal`: the raw ZORI MoM mean over the lease-reset window (float | None).
- `cpi_shelter_mom_last`: the last knowable CPI shelter MoM (float | None).
- `shelter_k_applied`: the k weight actually used (0.35, 0.175, or 0.0 if fallback).
- `zori_signal_absent`: bool (True if ZORI data was absent or insufficient).
- `shelter_absent`: bool (True if both ZORI and BLS shelter momentum are absent).
- `zori_months_used`: int (number of lease-reset window months with PIT-filtered ZORI data).

---

## 9. Output Contract V2 (Backward Compatible — FROZEN)

All existing keys from PREREG_V1.md §7 are preserved unchanged. New keys added:

```python
{
    # ... all V1 keys unchanged ...
    "components": [                    # NEW — list, None if no model fit
        {
            "name": str,               # block name: energy|shelter|core_persistence|pipeline
            "contrib_pp": float,       # beta_i * z_i sum for the block
            "confidence": float,       # known/proxy/residual weight: 1.0|0.6|0.0
        },
        # ... one entry per block with ≥1 available feature
    ],
    "confidence_v2": float | None,     # NEW — known/proxy/residual weighted confidence
    "confidence_components_v2": {      # NEW
        "w_known": float,
        "w_proxy": float,
        "w_residual": float,
        "c_raw": float,
        "input_completeness": float,
    },
}
```

---

## 10. What Is NOT Changed

- Model class: Ridge (lambda=1.0, numpy, closed-form). UNCHANGED.
- Z-scoring: expanding window. UNCHANGED.
- Walk-forward protocol: expanding window, min 60 obs. UNCHANGED.
- Quantile computation: same residual history accumulation. UNCHANGED.
- Baselines: naive_prior, trailing_3m, ar3. UNCHANGED.
- Confidence V1: interval_rank * input_completeness. UNCHANGED (preserved in output).
- Surprise skew formula. UNCHANGED.
- Kill rule threshold. UNCHANGED.
- NFP model, features, kill rule. UNCHANGED (parallel agent owns NFP).
- Lambda=1.0. UNCHANGED.

---

## 11. Registration Note

This document is committed before the V2 backtest is run. Hash of this file at
commit time constitutes the frozen spec. RESULTS_V2.md will record deviations.
The `2021+` verdict (fixed or benchmark-only) for cpi_core is the primary question;
answer will be stated plainly in RESULTS_V2.md regardless of direction.
