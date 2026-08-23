# EVAL-0 Evaluation Preregistration Freeze

**Status at K3E-0:** architecture template frozen; EVAL-0 must instantiate and
commit the immutable protocol hash before advanced model tuning or outcome
inspection.

## 1. Questions

1. Do prospective expectation dynamics improve description/prediction of fixed
   future response estimands beyond price-only and last-observation baselines?
2. Which source/metric/horizon families are estimable, calibrated and stable
   across eras?
3. Does any coupling/assimilation representation add incremental value over its
   decomposed legs?
4. Are abstentions well targeted, or do they selectively hide adverse cases?

## 2. Unit and population

Primary unit: one issuer/security, expectation metric, fiscal target/horizon and
new as-known-at observation episode. Multiple fires/dates from the same
underlying change are not independent episodes.

The protocol reports:

- distinct issuers and episodes;
- source/metric/horizon coverage and exclusions;
- analyst/contributor denominators where known;
- delisted/renamed/share-class exclusions;
- whether the current regime and motivating live exemplars fall inside the
  winning cell; and
- clustered uncertainty at issuer and economic-episode levels as appropriate.

## 3. Time splits

All splits are chronological and fixed before advanced fitting:

1. accrual/warm-up era (no claims; establishes minimum vintages);
2. development era for deterministic baseline and challenger fitting;
3. calibration era for thresholds/uncertainty only;
4. locked holdout era for one final comparison; and
5. prospective shadow era for operational drift and correction behavior.

Exact dates depend on natural SRC-A1 accrual and vendor history availability;
EVAL-0 must publish them before inspecting the corresponding outcomes. If the
history is too short, the honest result is `EVALUATION_NOT_YET_MATURE`.

## 4. Baselines

Minimum comparators:

- no-change / last observation;
- price-only response state;
- simple EWMA/robust slope expectation change;
- calendar/fiscal-roll naive;
- market and peer-relative raw response;
- owner-native DRL/residual where estimable; and
- decomposed-leg model versus any proposed coupling/phase projection.

The advanced model must beat the relevant simple baseline net of coverage,
calibration, complexity and turnover. A higher in-sample fit is irrelevant.

## 5. Outcomes and horizons

Predeclare market-session horizons (candidate set: 1, 5, 21, 63 sessions) and
the lawful first session. Outcomes remain decomposed:

- raw, market-relative, peer-relative and owner-residual returns;
- realized volatility/volume/liquidity response;
- options response where prerequisites pass;
- direction/persistence/time-to-response estimands; and
- calibration of probabilistic outputs, if any.

No single return becomes truth. Family-specific primary outcomes and materiality
bands must be chosen before fitting.

## 6. Metrics

Report coverage and error together. Depending on estimand:

- MAE/median absolute error and robust scale-aware error;
- Brier/log score and reliability diagrams for probabilities;
- rank correlation only as a research diagnostic, never production rank
  authority;
- decision-curve or utility analysis only with predeclared costs and no trade
  authority;
- bootstrap/clustered confidence intervals; and
- improvement over baseline with multiplicity-adjusted uncertainty.

Every table prints included/excluded denominators, distinct episodes, coverage,
dominant degradation and adverse/null results.

## 7. Leakage and PIT guards

- Join inputs by what was available at the prediction clock, never latest row.
- Freeze correction chains and source generations for each run.
- Do not use actual fiscal period mappings or constituent/peer membership learned
  after the anchor unless the owner proves PIT availability.
- Purge/embargo overlapping outcome windows where necessary.
- Fit transformations and hyperparameters inside training eras only.
- Keep the final holdout inaccessible to tuning scripts where practical.
- Re-run coverage against motivating live exemplars and the current regime
  before any conclusion.

## 8. Missingness and abstention audit

Missing observations are not imputed across source families by default.
Evaluation reports performance on:

1. the eligible/covered subset;
2. the full intended population with abstentions;
3. major reason-code strata; and
4. an adversarial comparison of covered versus abstained outcomes.

A model that looks good only by abstaining on difficult episodes does not pass.

## 9. Multiple testing and promotion

Families, horizons, metrics, feature sets and challengers form the declared
hypothesis family. EVAL-0 freezes a false-discovery or hierarchical testing
procedure and the number of permitted final looks. Exploratory results are
labeled exploratory and cannot promote.

Promotion requires all of:

- adequate episode-honest N and coverage;
- out-of-sample improvement over the correct baseline;
- calibration/stability across predeclared eras and key strata;
- adverse/null results retained;
- independent red-team review against the intended use case;
- owner acceptance through existing Eval OS/Prophet gates; and
- a separate authority decision. K3E cannot self-promote.

## 10. Immutable EVAL-0 artifact

EVAL-0 must commit a machine-readable protocol carrying:

```text
schema/version
protocol_id and content hash
source families and exact input versions
unit/population
eras and embargo
primary/secondary estimands
horizons
baselines/challengers
metrics
exclusions/missingness
hypothesis family/multiplicity
minimum support/promotion thresholds
allowed final looks
authority (all false)
```

Any amendment appends a new version with rationale before the affected result;
it never overwrites the original preregistration.
