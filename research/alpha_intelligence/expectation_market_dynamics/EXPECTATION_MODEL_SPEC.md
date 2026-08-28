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

## `SRC-A1` raw accrual contract

`SRC-A1` extends the existing revisions owner lane. It must preserve provider
shape before K3E derives surfaces:

- every returned horizon, not only the preferred forward year;
- EPS and revenue expectation records where available;
- provider horizon label and normalized fiscal period when safely derivable;
- metric family, basis, units, currency, value, low/high/mean/median/count
  fields when present;
- provider-issued, source-available, collected, known, and superseded clocks
  when distinguishable;
- raw payload identity or content hash sufficient for idempotent replay;
- collection attempt identity, source endpoint/accessor, ticker/input identity,
  and provider/source degradation state;
- explicit absence for unavailable revenue revisions or analyst-level detail,
  rather than surrogate columns that look richer than the source.

The first implementation may be BUILT_NOT_PROVEN until a natural collection run
prints real multi-horizon observations. Natural proof must include at least one
multi-horizon EPS observation and one revenue observation or a typed provider
absence explaining why revenue was not lawfully observable.

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

Every aggregate must print its denominator: total source records, fresh records,
stale records, dropped records, unavailable records, and rights-blocked records
where those categories apply. A missing denominator makes the aggregate invalid.

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

No challenger may use later market outcomes, later consensus restatements, or
post-event labels to define the earlier expectation state. Analyst/provider
skill weighting is blocked until its training data, clocks, rights, and
held-out evaluation are preregistered.

## Null law

The model must prefer:

- `UNESTIMABLE` when coverage is too low;
- `STALE` when the data exist but freshness is poor;
- `MIXED_SIGNAL` when node-level disagreement dominates;
- `RIGHTS_BLOCKED` when richer granularity is known but not lawfully usable.

These are successful outputs.
