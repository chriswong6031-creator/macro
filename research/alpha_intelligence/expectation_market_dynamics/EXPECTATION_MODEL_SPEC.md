# K3E-0 Expectation Model Specification

## 1. Model target

The expectation side estimates a **distribution of observable source
expectations**, not management truth, intrinsic value or the market's complete
belief. It preserves source, actor, method, metric, horizon, population and
clock so incompatible expectations cannot be averaged into false precision.

The canonical conceptual result is:

```text
ExpectationSurface
  subject_ref
  as_known_at
  source_family
  metric
  unit/currency
  fiscal_period/horizon
  population_receipt
  raw_observation_refs
  deterministic_baseline
  challenger_inferences[]
  disagreement
  change_state
  coverage/freshness/correction
  estimability
  authority
```

This is a deterministic/versioned view or research artifact, not a truth store.
MAS-119 retains ownership of common catalyst `ExpectationBaseline` federation.
Until it accepts a common contract, K3E types remain explicitly local and
owner-referenced.

## 2. Observation invariants

1. One observation is one provider payload value for one subject, metric,
   horizon and observation clock.
2. Provider horizon labels are retained verbatim. Fiscal-period mapping is a
   separately receipted derivation and may be unknown.
3. Analyst count is a denominator, not confidence. Missing contributor history
   means population turnover is unknown.
4. Mean/low/high do not imply a distribution beyond those reported statistics.
5. Negative EPS, zero-crossings, fiscal rollovers, currencies and unit changes
   must not be forced through percentage-change math.
6. Corrections append; no later payload changes the earlier as-known-at state.
   Same-session retries deduplicate, while later scheduled observations preserve
   the fact that an unchanged value was observed again.
7. Absence, ambiguity and rights restrictions are typed observations.

## 3. Baseline ladder

Evaluation must begin with boring, interpretable baselines before advanced
models. Each baseline emits its own support and abstention reason.

| ID | Baseline | Purpose |
|---|---|---|
| `B0_LAST` | last valid same-source observation | Persistence benchmark |
| `B1_EWMA` | time-decayed level/change, clock-aware | Smooth prospective revision path |
| `B2_ROBUST_SLOPE` | Theil–Sen or predeclared robust slope over observed vintages | Revision direction without single-point dominance |
| `B3_CROSS_HORIZON` | deterministic near/far-horizon shape and roll transition | Detect horizon disagreement without collapsing it |
| `B4_PANEL_DISAGREE` | normalized range/dispersion only where scale math is valid | Preserve disagreement as a leg |
| `B5_SEASONAL_NAIVE` | comparable fiscal-period prior where PIT support exists | Fiscal baseline; absent if historical comparable is missing |

No baseline emits a buy/sell label, fair value, price target or universal score.

## 4. Challenger ladder

Advanced candidates are earned sequentially:

1. robust change-point detection (for example BOCPD) with fixed priors and
   sensitivity analysis;
2. hierarchical partial pooling by source/metric/horizon only after panel
   coverage and leakage checks;
3. latent dynamic expectation state with explicit observation equations,
   missingness and posterior calibration;
4. multi-source synthesis only when rights, identity and common-clock support
   are proven and source-family disagreement remains visible.

The advanced model cannot tune on the final evaluation era. It must beat the
appropriate baseline in utility and calibration, not merely in in-sample fit.
Failure or parity preserves the baseline or `UNESTIMABLE` result.

## 5. Change representation

Change is vector-valued:

```text
level_change
robust_slope
change_point_probability
near_vs_far_horizon_shape
dispersion_change
analyst_count_change
fiscal_roll_state
correction_state
```

Every component has `value`, `support_n`, `clock_span`, `method_version` and
`estimability`. Negative-EPS and zero-crossing cases use absolute/unit-aware
change or abstain; percentage deltas are forbidden where the denominator does
not support their interpretation.

## 6. Estimability

An expectation component is `UNESTIMABLE` when any required input is absent,
ambiguous, rights-blocked, stale beyond protocol, too thin, clock-invalid or
outside method support. Required reason codes include:

```text
NO_OBSERVATIONS
INSUFFICIENT_VINTAGES
UNKNOWN_HORIZON_MAPPING
IDENTITY_AMBIGUOUS
FISCAL_ROLL_AMBIGUOUS
UNIT_OR_CURRENCY_BREAK
PANEL_TOO_THIN
SOURCE_RATE_LIMITED
SOURCE_RIGHTS_BLOCKED
CORRECTION_CHAIN_AMBIGUOUS
METHOD_OUT_OF_SUPPORT
```

A populated sibling component never fills an unestimable one.

## 7. Output boundary

Expectation results may describe level, change, disagreement and evidence
quality. They do not assert what the market expects, what the company will earn,
what the security is worth or whether to transact. Those distinctions remain
visible in every projection.
