# Expectation Model Spec

## Objective

Represent observable expectation state as a multi-horizon, missing-aware,
point-in-time surface rather than a single consensus scalar.

## Atomic observation target

Preferred long-run grain:

- issuer / security
- observer / provider / analyst where rights allow
- metric and basis
- fiscal period / horizon
- forecast value, units, currency
- issued / available / known / superseded clocks
- correction state
- coverage provenance

`SRC-A1` only needs to preserve enough raw source shape to make this future
grain recoverable. It does not need to solve every derived field in the first PR.

## Derived expectation surface

Each metric-horizon node should eventually emit:

- fresh mean / fresh median;
- age-weighted consensus;
- coverage total / fresh / stale share;
- dispersion level and change;
- revision breadth, magnitude, coherence, and intensity;
- cross-horizon agreement;
- detected revision clusters;
- change-point state;
- rights / missingness / correction state.

## Initial deterministic baselines

The first honest baselines are deliberately boring:

1. no-change baseline;
2. latest fresh consensus;
3. age-weighted consensus;
4. 30d / 90d revision summaries;
5. fresh median versus stale consensus split.

No advanced challenger may be promoted unless it beats these on preregistered
targets and eras.

## Advanced challengers (later)

- revision-cluster detectors;
- Bayesian online change-point detection;
- latent state-space surfaces;
- analyst / provider skill weighting where rights and PIT discipline allow.

## Null law

The model must prefer:

- `UNESTIMABLE` when coverage is too low;
- `STALE` when the data exist but freshness is poor;
- `MIXED_SIGNAL` when node-level disagreement dominates;
- `RIGHTS_BLOCKED` when richer granularity is known but not lawfully usable.

These are successful outputs.
