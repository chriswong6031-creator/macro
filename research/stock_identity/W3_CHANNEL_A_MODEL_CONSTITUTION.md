# Stock Identity W3A — Channel-A Model Constitution (Capacity Budget)

**Wave:** SI-W3A, plan Task 3B. **Binding law:** freeze §4.1b (original masterplan §2.3
control (i), restored). **Authority:** all five axes false — this is a prereg-only
document. **W3 fits nothing.** This registration freezes the LEGAL MODEL CLASS a future
W5Q confirmatory fit must stay inside; it does not itself fit, evaluate or select a model.

## 1. Declared feature subset

`data/stock_identity/ruler/channel_a_constitution_v1.json` → `feature_subset`:

* `f1_kaufman_er_252` — Kaufman efficiency ratio, 252-session window (F1 trendiness).
* `f2_ulcer_252` — Ulcer index, 252-session window (F2 drawdown pain).
* `f4_variance_ratio_k20_756` — variance ratio at lag 20, 756-session window (F4 mean-reversion/momentum).
* `f5_realized_vol_63` — realized volatility, 63-session window (F5 vol regime).
* `f7_atr_dist_50dma_252` — ATR-normalized distance to the 50DMA, 252-session window (F7 trend-following state).

Each is a real column of `data/stock_identity/fingerprints/pilot_fingerprint_v0.parquet`
(`engine/stock_identity/fingerprint.py`'s F1/F2/F4/F5/F7 blocks), verified in
`tests/test_stock_identity_model_constitution.py::test_declared_feature_subset_is_subset_of_real_fingerprint_columns`.
Five features, one per fingerprint family (F1/F2/F4/F5/F7), chosen for breadth across the
fingerprint's trendiness/drawdown/mean-reversion/vol/trend-state families rather than
depth within any one family — a design choice, not a computed statistic.

## 2. Functional form

`functional_form: "additive_monotone"`, `separately_preregistered_form_ref: null`. The
map is additive and monotone in each declared feature; no interaction terms, no
nonlinear basis expansion beyond a single monotone transform per feature. A richer form
would require a real `separately_preregistered_form_ref` document — none exists, so the
form stays at the plain additive-monotone floor.

## 3. `p_eff` counting rule

> One effective parameter per declared feature's own additive-monotone shape term: a
> single monotone transform of that feature contributes exactly 1 to `p_eff`. `p_eff`
> is the sum over the declared `feature_subset` of its declared shape-term count
> (`p_eff_terms`), never a fitted quantity. A richer per-feature shape (e.g. a spline
> with `k` knots) would declare `k` terms for that feature and requires the
> `separately_preregistered_form_ref` above to be non-null.

`p_eff_terms` = `{f1_kaufman_er_252: 1, f2_ulcer_252: 1, f4_variance_ratio_k20_756: 1,
f5_realized_vol_63: 1, f7_atr_dist_50dma_252: 1}` → `count_p_eff() == 5`, deterministic
(`engine.stock_identity.model_constitution.count_p_eff`).

## 4. Capacity law — exact, per training fold

`p_eff <= floor(N_train_names / 10)`, where `N_train_names` is that fold's
post-exclusion training name count. `capacity_denominator = 10` (frozen).
`assert_capacity(p_eff, n_train_names)` raises `CapacityViolation` iff
`p_eff > n_train_names // 10`; the boundary itself is legal
(`p_eff == floor(N_train_names / 10)` passes) — test-pinned at both the boundary and
one-over.

Concretely, with the declared `p_eff = 5`, Channel A needs `N_train_names >= 50` in a
training fold before it may fit at all under this constitution; a fold with fewer names
aborts the read under §5 below rather than shrinking the model silently.

## 5. Enforcement contract

W5Q evaluates `assert_capacity` on every training fold **before any fit**. A violation
**aborts the read** — it never triggers a silent model-shrink, an automatic feature
drop, or a substituted simpler form. This registration document plus
`channel_a_constitution_v1.json` are the sole source of the legal model class; nothing
in W3 (this wave) performs a fit against them.

## 6. No-fitting proof

`engine/stock_identity/model_constitution.py` imports no fitting/estimation library
(`sklearn`, `scipy.optimize`, `statsmodels`, `xgboost`, `lightgbm`, `torch`,
`tensorflow`, `keras`, `cvxpy` — checked by AST import scan) and defines no function
named `fit` or `fit_*` anywhere (checked by AST function-name scan). Both are
test-enforced in `tests/test_stock_identity_model_constitution.py`.
