# Pre-Registration V3 Factor — MRI Track M Challenger (PCA + Ridge)

**Frozen:** 2026-07-08 (written BEFORE backtest_v3_factor.py is run)
**Program:** Macro Release Intelligence (MRI), Track M — PR-M (Wave 10)
**Branch:** claude/mri-w10-track-m
**Spec attempt:** #1 of 1 (per MRI-R21: one multifactor challenger, no re-spec after results)
**Status:** FROZEN — no model spec changes after this commit
**Authority:** MRI-R21, masterplan §11, §11.1 Track M

Anti-mining commitment: this document is committed BEFORE the backtest is run. No
hyperparameters, feature weights, kill-rule interpretations, PCA dimensions, or lambda
may change after results are observed. Per MRI-R21 and masterplan §6: if the kill rule
fires for a target, that target ships benchmark_only/no_shadow; max 1 spec attempt for
Track M. No feature or weight iteration after observing results.

---

## 0. Scope

This pre-registration covers the CHALLENGER model only. The champion (v2 ridge)
continues to hold its existing results and ledger rows unchanged. The challenger
(v3_factor) is evaluated in parallel and may shadow-row the ledger ONLY if it beats
naive in both the full window AND the 2021+ slice. Shadow-wiring is deferred to
Round 2 (serial integration pass). This round: prereg + backtest + results only.

Targets: cpi_headline, cpi_core, nfp.

The challenger may NEVER gate, score, or size positions. display_only=True,
authority=False on all outputs.

---

## 1. Data Sources

### 1.1 ALFRED Vintaged Series (PIT via realtime_start filter)

These series are read through the existing `knowable_series()` function which returns
initial-print values (earliest realtime_start per period) filtered to realtime_start <= asof.

| Series | FRED ID | Use |
|--------|---------|-----|
| CPI Headline | CPIAUCSL | Target (MoM %) + own lags 1–3 |
| CPI Core | CPILFESL | Target (MoM %) + own lags 1–3 |
| NFP | PAYEMS | Target (level change, thousands) + own change lags 1–3 |
| Sticky CPI | STICKCPIM157SFRBATL | CPI family: sticky_mom |
| Median CPI | MEDCPIM158SFRBCLE | CPI family: median_mom |
| Flex CPI | FLEXCPIM157SFRBATL | CPI family: flex_mom |
| PPI Final Demand | PPIFIS | CPI family: ppi_fis_mom; available 2014-02+ in vintages |
| PPI Services (ex. trade) | PPIFES | CPI family: ppi_fes_mom; available 2010-04+ in vintages |
| ICSA (initial claims) | ICSA | NFP family: survey-week claims; vintaged 2009+ |
| CCSA (continued claims) | CCSA | NFP family: survey-week claims; vintaged 2009+ |

**PIT treatment:** All vintaged series use the standard champion `knowable_series()` function.
The walk-forward step_asof for each historical observation is one day before that
observation's realtime_start — identical to the champion protocol.

### 1.2 Non-Vintaged / Asof-Blind Series (declared revision_optimistic or unrevised)

| Series | Source file | PIT treatment | Declared status |
|--------|-------------|---------------|-----------------|
| DTWEXBGS (broad dollar) | data/fred/DTWEXBGS.parquet | asof-filtered index <= asof | revision_optimistic (not ALFRED-vintaged) |
| GASREGW (gasoline) | data/fred/GASREGW.parquet | asof-filtered index <= asof | unrevised (weekly price, not revised) |
| PPIFES (PPI services ex-trade) | data/fred/PPIFES.parquet | asof-filtered index <= asof | revision_optimistic (also in vintages for lag; direct parquet for MoM computation) |
| PPIFIS (PPI final demand) | data/fred/PPIFIS.parquet | asof-filtered index <= asof | revision_optimistic (also in vintages for lag) |
| AWHMAN (mfg hours) | data/fred/AWHMAN.parquet | asof-filtered index <= asof | revision_optimistic |
| ADPMNUSNERSA (ADP payrolls) | data/fred/ADPMNUSNERSA.parquet | asof-filtered index <= asof | revision_optimistic (see §1.3 ADP caveat) |
| Withheld taxes | data/treasury/withheld_taxes.parquet | asof-filtered | unrevised |

**Note on PPIFIS/PPIFES**: both series have ALFRED vintages (used by the champion for
lag-1 features) AND direct parquet files. The v3 feature builder reads MoM momentum
for these series from the direct parquet (asof-filtered index), which is declared
revision_optimistic. This is consistent with the champion's treatment of PPIFIS in
the CPI component engine.

### 1.3 ADP Caveats (FROZEN — transcribed from champion)

**Caveat 1 — asof-blind read:** ADP does not have ALFRED vintage tracking in this
repository. The ADP parquet (ADPMNUSNERSA) is read with index <= asof as a proxy for
PIT-safety, but any ADP revisions within a given month cannot be accounted for. This
is declared `revision_optimistic_legs`. Shared limitation with awhman_mom.

**Caveat 2 — 2022 methodology redesign:** ADP redesigned its methodology in August 2022.
The redesigned series (post-2022-08) uses different seasonal adjustment and industry
classifications compared to pre-2022 data. Era-split evaluation (2021+ vs pre) captures
the most exposed slice. The 2022+ era should be treated as a regime break for ADP; the
feature may behave differently before and after.

**Caveat 3 — data start:** ADPMNUSNERSA in this repo starts 2010-01, so adp_change
is computable from 2010-02. Pre-2010 NFP training rows will have adp_change = None
(dropped in complete-case).

### 1.4 Shelter Nowcast (reused from champion V2)

The `shelter_nowcast` feature for CPI targets is reused exactly as computed by the
champion's `build_cpi_features()` function. See PREREG_V2.md §2 for the full spec
(ZORI + CPI shelter blend, k=0.35, divergence guard). Available ~2016-01+. Pre-2016
steps: shelter_nowcast = None (dropped from complete-case for those steps).

### 1.5 EXPINF / Breakeven Exclusion

EXPINF series and inflation breakevens (e.g., T5YIE, T10YIE, MICH) are EXCLUDED.
Reason (per MRI-R21): these are whole-history re-revisers that contaminate the
walk-forward with future-vintage information. This exclusion is frozen; no attempt
to include them later in this spec.

---

## 2. Feature Panel — FROZEN

### 2.1 CPI Headline Feature Set

All features z-scored (expanding window, standardize before SVD). Complete-case: rows
with ANY null in the available prediction features are dropped from training.

| # | Feature name | Construction | PIT source | Start |
|---|--------------|--------------|------------|-------|
| 1 | cpi_hl_mom_lag1 | MoM % CPIAUCSL initial-print, lag 1 | ALFRED vintage | 1997-01+ |
| 2 | cpi_hl_mom_lag2 | MoM % CPIAUCSL initial-print, lag 2 | ALFRED vintage | 1997-02+ |
| 3 | cpi_hl_mom_lag3 | MoM % CPIAUCSL initial-print, lag 3 | ALFRED vintage | 1997-03+ |
| 4 | sticky_mom_lag1 | MoM % STICKCPIM157SFRBATL, lag 1 | ALFRED vintage | 2014-03+ |
| 5 | median_mom_lag1 | MoM % MEDCPIM158SFRBCLE, lag 1 | ALFRED vintage | 2014-02+ |
| 6 | flex_mom_lag1 | MoM % FLEXCPIM157SFRBATL, lag 1 | ALFRED vintage | 2014-03+ |
| 7 | ppi_fis_mom_lag1 | MoM % PPIFIS, lag 1 | ALFRED vintage | 2014-03+ |
| 8 | ppi_fes_mom_lag1 | MoM % PPIFES, lag 1 | ALFRED vintage | 2010-05+ |
| 9 | gasoline_mom | Avg MoM % change GASREGW over ref month M | parquet, unrevised | 2006+ |
| 10 | shelter_nowcast | ZORI+CPI shelter blend per PREREG_V2.md §2 | parquet, revision_optimistic | ~2016-01+ |
| 11 | dollar_mom | MoM % change DTWEXBGS (monthly avg from daily) | parquet, revision_optimistic | 2006-02+ |

Order is PRESERVED — own 3 lags first (for AR3 baseline compatibility).

### 2.2 CPI Core Feature Set

Same as headline EXCEPT gasoline_mom is EXCLUDED (gasoline not in core basket by definition).

| # | Feature name | Construction | PIT source | Start |
|---|--------------|--------------|------------|-------|
| 1 | cpi_core_mom_lag1 | MoM % CPILFESL initial-print, lag 1 | ALFRED vintage | 1997-01+ |
| 2 | cpi_core_mom_lag2 | MoM % CPILFESL initial-print, lag 2 | ALFRED vintage | 1997-02+ |
| 3 | cpi_core_mom_lag3 | MoM % CPILFESL initial-print, lag 3 | ALFRED vintage | 1997-03+ |
| 4 | sticky_mom_lag1 | MoM % STICKCPIM157SFRBATL, lag 1 | ALFRED vintage | 2014-03+ |
| 5 | median_mom_lag1 | MoM % MEDCPIM158SFRBCLE, lag 1 | ALFRED vintage | 2014-02+ |
| 6 | flex_mom_lag1 | MoM % FLEXCPIM157SFRBATL, lag 1 | ALFRED vintage | 2014-03+ |
| 7 | ppi_fis_mom_lag1 | MoM % PPIFIS, lag 1 | ALFRED vintage | 2014-03+ |
| 8 | ppi_fes_mom_lag1 | MoM % PPIFES, lag 1 | ALFRED vintage | 2010-05+ |
| 9 | shelter_nowcast | ZORI+CPI shelter blend per PREREG_V2.md §2 | parquet, revision_optimistic | ~2016-01+ |
| 10 | dollar_mom | MoM % change DTWEXBGS (monthly avg from daily) | parquet, revision_optimistic | 2006-02+ |

### 2.3 NFP Feature Set

| # | Feature name | Construction | PIT source | Start |
|---|--------------|--------------|------------|-------|
| 1 | nfp_change_lag1 | Level change PAYEMS initial-print, lag 1 | ALFRED vintage | 1997-01+ |
| 2 | nfp_change_lag2 | Level change PAYEMS initial-print, lag 2 | ALFRED vintage | 1997-02+ |
| 3 | nfp_change_lag3 | Level change PAYEMS initial-print, lag 3 | ALFRED vintage | 1997-03+ |
| 4 | claims_survey_week_icsa | Avg ICSA initial-print in survey-week for ref_month | ALFRED vintage | 2009-05+ |
| 5 | claims_survey_week_ccsa | Avg CCSA initial-print in survey-week for ref_month | ALFRED vintage | 2009-09+ |
| 6 | withheld_tax_yoy | YoY % change in withheld taxes (survey-week) | unrevised parquet | 2024-02+ |
| 7 | awhman_mom | MoM change in mfg hours (AWHMAN) | parquet, revision_optimistic | 2010+ |
| 8 | adp_change | Contemporaneous ADP payroll change (M), thousands | parquet, revision_optimistic | 2010-02+ |
| 9 | dollar_mom | MoM % change DTWEXBGS (monthly avg from daily) | parquet, revision_optimistic | 2006-02+ |

---

## 3. Model Specification — FROZEN

### 3.1 Overview

The v3_factor model replaces the champion's direct ridge on raw features with a
dimensionality-reduction step (PCA via SVD) followed by ridge on latent factors.

The design is: complete-case feature matrix → z-score (expanding window) → PCA top-3
factors via pure-numpy SVD → ridge(lambda=1.0) on [3 PCA factors + naive anchor].
The naive anchor (own MoM lag-1) is appended as a 4th predictor to preserve the
autoregressive baseline within the latent-factor design.

### 3.2 Step-by-Step Algorithm (FROZEN)

**Step 1 — Complete-case selection:**
Given prediction row x_pred (p-dimensional), identify which features are non-null.
Let K = set of available feature indices in x_pred.
From the training matrix X_train (n x p), keep only rows where ALL features in K
are non-null. Call this X_cc (m x |K|) and y_cc (m,).
If |K| = 0 or m < MIN_TRAIN_OBS (60): return None (no prediction).

**Step 2 — Z-scoring:**
Compute mean_k and std_k from X_cc (training rows only; expanding-window).
std_k[j] = 1.0 if std_k[j] == 0 (constant column).
Z_cc = (X_cc - mean_k) / std_k (training rows).
z_pred = (x_pred[K] - mean_k) / std_k (prediction row).

**Step 3 — SVD/PCA (top-3 factors):**
Compute U, S, Vt = np.linalg.svd(Z_cc, full_matrices=False).
F_train = U[:, :3] * S[:3]   # (m x 3) — latent factor scores for training rows
  (equivalent to Z_cc @ Vt[:3, :].T)
f_pred = z_pred @ Vt[:3, :].T  # (3,) — latent factor scores for prediction row

If the training matrix has fewer than 3 components (|K| < 3), use min(|K|, 3) components.

**Step 4 — Naive anchor:**
naive_lag1 = z_pred[0]   (z-scored own-lag-1, always the first feature by construction)
If the own-lag-1 feature is absent (z_pred[0] is NaN → not in K), naive_anchor = 0.0.

Append naive_lag1 to both training and prediction design matrices:
F_train_aug = [F_train | naive_lag1_train_col]   # (m x 4)
f_pred_aug  = [f_pred   | naive_lag1]            # (4,)

where naive_lag1_train_col = z_own_lag1 for training rows (z-scored, using same mean_k/std_k
for feature index 0).

**Step 5 — Ridge:**
beta = (F_train_aug' F_train_aug + lambda*I)^{-1} F_train_aug' y_cc
point = f_pred_aug @ beta

lambda = RIDGE_LAMBDA = 1.0 (same as champion, frozen).

**Step 6 — Bias column:**
A bias (intercept) column of ones is appended to F_train_aug before ridge fit,
making the design matrix (m x 5): [F1, F2, F3, naive_anchor, 1].
f_pred_aug becomes (5,): [f1, f2, f3, naive_anchor, 1].

### 3.3 Number of PCA Factors

Top-3 factors (or fewer if |K| < 3). Frozen; no scree-plot selection.

### 3.4 Lambda

RIDGE_LAMBDA = 1.0. Same as champion. Frozen.

### 3.5 Walk-Forward Protocol

Identical to champion:
- Expanding window (all data before index i as training).
- MIN_TRAIN_OBS = 60 (same as champion).
- Per-step refit (SVD + ridge at each step).
- Residual errors accumulated for quantile computation.
- Quantiles (p10/p25/p50/p75/p90) from empirical residual distribution per champion
  `_compute_quantiles()` (reused directly from engine/release_forecast.py).
- COVID months (2020-03..2020-06) excluded from ERA STATS (printed separately; same
  as champion).
- MIN_QUANTILE_OBS = 24 (same as champion).

### 3.6 AR3 Baseline

AR3 is computed from own lags 1-3 (features 0-2 by construction) using ridge, identical
to the champion's _walk_forward AR3 logic. This is the same baseline used to assess
relative performance.

---

## 4. Kill Rule — FROZEN (MRI-R21 / §11.1 Track M)

The challenger is marked **benchmark_only** (NOT shadowed) if:

- Challenger MAE >= naive_prior MAE in the FULL window **AND** in the 2021+ slice.

Both conditions must hold; failing only one does NOT trigger the kill.

Notes:
- "Full window" for NFP is the 2010+ evaluation window (per champion prereg §4.1).
- COVID months (2020-03..06) are excluded from era stats but not from training.
- If kill triggers: that target ships benchmark_only; the shadow-wiring for that target
  is skipped in Round 2. Record in RESULTS_V3_FACTOR.md and append to DO_NOT_REBUILD.md
  if appropriate.
- Max 1 spec attempt for Track M (MRI-R21 charter).

---

## 5. Evaluation Metrics — FROZEN

Per era (pre_2010, 2010_2020, covid, 2020_recovery, 2021_plus, full):
- n: number of predictions in era.
- MAE model, MAE naive, MAE trailing3m, MAE AR3 (for NFP: trailing3m).
- RMSE model, RMSE naive.
- p10-p90 coverage: fraction of actuals in [p10, p90] interval.
- Skew HR (conditional): fraction of predictions where sign(model - naive) == sign(actual - naive),
  restricted to steps where model takes a stance (model != naive). Wilson 95% CI.

Head-to-head vs champion:
- Same walk-forward folds, same feature inputs.
- Champion run via `run_walk_forward_full()` from engine.release_forecast.
- Report: side-by-side MAE_v3 vs MAE_champion vs MAE_naive per era.

---

## 6. PIT Law

**Vintaged legs:** All ALFRED-vintaged series use `knowable_series()` with
realtime_start <= step_asof filter. Initial prints only.

**Non-vintaged legs:** dollar_mom (DTWEXBGS), gasoline_mom (GASREGW), ppi_fes/ppi_fis
from parquet, shelter_nowcast, awhman_mom, adp_change, withheld_tax_yoy — all read
from parquet with index <= step_asof. Declared `revision_optimistic_legs` or
`unrevised_legs` as appropriate.

**Walk-forward step_asof:** one day before the target print's realtime_start (same as
champion). This ensures all features reflect information knowable at the decision date.

**COVID months in training:** COVID-era rows (2020-03..06) ARE included in training but
flagged separately in era tables. They are NOT excluded from the expanding window.

---

## 7. Output Contract — FROZEN

The challenger's `project_release_v3()` returns a dict matching the champion's schema
(PREREG_V1.md §7 / PREREG_V2.md §9) with these additional / modified fields:

```python
{
    # Champion schema keys (all present):
    "release": str,
    "asof": str,           # ISO date
    "point": float | None,
    "p10": float | None,
    "p25": float | None,
    "p50": float | None,
    "p75": float | None,
    "p90": float | None,
    "confidence": None,    # not computed for challenger (future work)
    "confidence_components": None,
    "input_completeness": float,
    "benchmark_set": {
        "naive_prior": float | None,
        "trailing_3m": float | None,
        "ar_model": float | None,
        "cleveland_nowcast": None,
        "market_implied": None,
    },
    "surprise_skew": {
        "sigma": float | None,
        "sigma_scale_pp": float | None,
        "tag": str | None,      # "hotter" | "cooler" | "inline"
        "inline_band": 0.35,
    },
    "pit_provenance": dict,
    # V3-specific additions:
    "model": "v3_factor",      # FROZEN tag — distinguishes challenger from champion
    "n_pca_factors": int,      # number of PCA factors used (1-3)
    "display_only": True,      # ALWAYS True
    "authority": False,        # ALWAYS False
}
```

**Backward-compat note:** `components` and `confidence_v2` are not computed for the
challenger in Round 1 (shadow-wiring deferred). These fields are omitted or None.

---

## 8. Absent Data Legs — Pre-Declared

The following legs are expected to be absent for some or all of the historical backtest
period. Complete-case handling drops them gracefully:

| Leg | Absent period | Effect |
|-----|--------------|--------|
| sticky/median/flex/ppi_fis | Pre-2014 (ALFRED vintage starts 2014) | Dropped from complete-case; model trains on own lags only pre-2014 |
| ppi_fes | Pre-2010-05 (ALFRED vintage) | Dropped pre-2010 |
| gasoline_mom (HL only) | Pre-2006 (GASREGW) | Dropped |
| shelter_nowcast | Pre-2016-01 (ZORI) | Dropped |
| dollar_mom | Pre-2006-02 (DTWEXBGS) | Dropped |
| adp_change (NFP) | Pre-2010-02 | Dropped |
| claims_survey_week (NFP) | Pre-2009-05 (ICSA) / 2009-09 (CCSA) | Dropped |
| withheld_tax_yoy (NFP) | Pre-2024-02 (data start) | Dropped |

Pre-2014 predictions may effectively run on only 3 features (own lags). This is
noted in results; it does not invalidate the full-window metric because the
expanding window accumulates properly.

---

## 9. Registration Note

This document is committed before the V3 backtest is run. Hash of this file at
commit time constitutes the frozen spec. RESULTS_V3_FACTOR.md will record deviations.

The primary question for each target: does v3_factor beat naive in both the full
window and the 2021+ slice? Answer will be stated plainly in RESULTS_V3_FACTOR.md
regardless of direction.
