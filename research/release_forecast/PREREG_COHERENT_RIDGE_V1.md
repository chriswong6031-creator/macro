# PREREG — `coherent_ridge_v1` CPI shadow

**Frozen:** 2026-08-11, before the first `coherent_ridge_v1` forward-ledger row
**Attempt:** 1 of 1 for this construction
**Registry:** `config/release_forecast_model_registry.yml`
**Model / model epoch:** `coherent_ridge_v1`
**Target epoch:** `alfred_same_release_vintage_proxy_v1`
**Status:** `shadow_candidate`

This document freezes the construction before forward accrual. It contains no observed
performance result. Historical or forward results may not be used to alter this model
epoch. Any feature, target, fit, interval, eligibility, or authority change requires a
new preregistration and a new model epoch.

## 1. Scope and authority

The candidate emits headline and core CPI MoM projections only. Its callable is
`engine.release_cpi_coherent_shadow.project_cpi_coherent_shadow(...)`, and its output
schema is `release_cpi_coherent_shadow.v1`.

Every output must carry `display_only=true`, `authority=false`, and
`promotion_authorized=false`. Forward scoring is evaluation only: the model may not
rank or score assets, gate signals, size positions, escalate alerts, trade, or acquire
Prophet or Neural Web authority.

The model has zero weight in `combined_v1` and is not an eligible input to it. It also
has zero weight and no eligibility in the future `internal_ensemble_v1`. There is no
automatic promotion or promotion-review route in this model epoch.

## 2. Target and truth receipt

The fitted target is `published_proxy_1dp` from the Wave 2A
`alfred_same_release_vintage_proxy_v1` history. `official_first_print_v1` remains
withheld. A candidate run must fail closed unless all three governed artifacts exist,
validate, and agree:

- `data/release_forecast/cpi_truth/alfred_same_release_vintage_proxy_v1.json`;
- `data/release_forecast/cpi_truth/parity_report.json`; and
- `data/release_forecast/cpi_truth/build_completion.json`.

The output truth receipt binds the history path, SHA-256, byte length and
`history_hash`; the parity path, SHA-256 and byte length; and the completion path,
SHA-256, byte length and `evidence_available_at` clock. The completion receipt must
prove the history and parity belong to the same completed Wave 2A corpus. Missing,
stale, inconsistent, or tampered evidence emits no candidate point or ledger row.

Own-target lags are exact-calendar prior `published_proxy_1dp` rows from this coherent
history. Cross-vintage reconstruction of a target or lag is forbidden.

## 3. Frozen feature vectors

Feature order is part of the model contract.

Headline:

1. `cpi_hl_mom_lag1`
2. `cpi_hl_mom_lag2`
3. `cpi_hl_mom_lag3`
4. `sticky_mom_lag1`
5. `median_mom_lag1`
6. `flex_mom_lag1`
7. `gasoline_mom`
8. `ppi_mom_lag1`

Core:

1. `cpi_core_mom_lag1`
2. `cpi_core_mom_lag2`
3. `cpi_core_mom_lag3`
4. `sticky_mom_lag1`
5. `median_mom_lag1`
6. `flex_mom_lag1`
7. `ppi_mom_lag1`

The non-target vintage features use `STICKCPIM157SFRBATL`,
`MEDCPIM158SFRBCLE`, `FLEXCPIM157SFRBATL`, and `PPIFIS`, filtered to the latest
vintage row for the exact source period with `realtime_start <= decision asof`.
Sticky and flexible CPI use the exact target-minus-one calendar month value directly.
Median CPI uses the exact target-minus-one annualized value transformed as
`((1 + value / 100) ** (1 / 12) - 1) * 100`. PPIFIS uses exact target-minus-one and
target-minus-two index levels transformed as
`(level_t_minus_1 / level_t_minus_2 - 1) * 100`. A missing exact period fails the
complete-case gate; a later available period is never substituted.

Headline gasoline uses timestamp-filtered, unrevised `GASREGW` observations from the
exact target and prior calendar months, with every admitted timestamp strictly before
the decision asof. Its feature is
`(mean(target-month observations) / mean(prior-month observations) - 1) * 100`; both
calendar months must be complete. Shelter/ZORI and revision-optimistic parquet legs
are excluded. Every admitted numeric feature must be finite.

## 4. Training and point construction

- Expanding chronological window; refit at every historical and live step.
- Decision cutoff is release date minus one calendar day and must equal the requested
  asof. The live target period must be the exact calendar month after the latest
  eligible coherent label. Every training label's
  release date must be on or before that cutoff. A live release date must be strictly
  after the requested asof.
- Fixed complete-case vector. No column dropping, imputation, or baseline fallback.
- Fewer than 60 complete prior rows, or any missing live feature, fails closed.
- Train-only z-scoring with sample standard deviation (`ddof=1`); a zero-variance
  scale is set to 1.
- Ridge lambda is 1.0. An intercept is included and is not penalized.
- Solve the closed form with NumPy `solve`; use `lstsq` only for numerical
  singularity, never as an empirical model alternative.
- Preserve the unrounded estimate as `point_raw`. Publish points only after Decimal
  `ROUND_HALF_UP` rounding to one decimal place.

## 5. Frozen interval construction

At each historical out-of-sample step, residual is
`actual_raw_target - raw_ridge_point`. The interval uses empirical 10th, 25th, 50th,
75th, and 90th percentiles with NumPy linear interpolation and strictly prior OOS
residuals. At least 24 prior OOS residuals are required; the live step uses all prior
OOS residuals. There is no interval fallback. Each raw band endpoint is
`point_raw + residual_quantile`. After construction, p10/p25 round down toward
negative infinity, p75/p90 round up toward positive infinity, and p50 rounds
half-up, each to one decimal place. Published rounding therefore cannot narrow
the raw empirical interval.

## 6. Publication and evaluation

An eligible run may appear as a `shadow_projection` row with exact model, target,
input, truth, training and interval receipts. Historical replay may never be appended
to the forward ledger. Forward scoring must compare like-for-like target epochs and
must use genuinely forward rows; it is evidence collection, not decision authority.

The current champion, `combined_v1`, its input list, displayed primary forecast,
coefficients, weights, and all downstream authority remain unchanged. A later review
may inspect genuinely forward evidence, but it cannot amend this epoch or silently
insert this candidate into a combined forecast.
