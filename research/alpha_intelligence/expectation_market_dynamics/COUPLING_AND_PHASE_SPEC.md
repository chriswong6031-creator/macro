# Coupling And Phase Spec

## Mission

Describe how expectation and market-response processes interact through time.
This is a descriptive read-model, not a score.

## Required emitted sub-objects

1. expectation state summary
2. market-response state summary
3. lag / synchronization estimate
4. disagreement state
5. coupling state
6. phase label
7. denominator / degradation / next-observable receipt

## Candidate descriptive states

- `MARKET_LEADING`
- `EXPECTATIONS_LEADING`
- `STREET_CATCHUP`
- `SYNCHRONIZED_RERATING`
- `EXPECTATIONS_CONTINUE_MARKET_STALLS`
- `MARKET_EXTENDS_EXPECTATIONS_STALE`
- `OPPOSING_SIGN`
- `HIGH_DISAGREEMENT`
- `TRANSITIONING`
- `UNESTIMABLE`

## Emission law

Every state must be backed by printed components. A phase may never be the only
thing emitted.

Minimum printed explanation:

- expectation direction / freshness / disagreement
- market direction / residual context / options context where available
- estimated lag or why lag is not estimable
- dominant degradation
- next observable that would resolve the ambiguity

## Prohibited forms

- a scalar "belief score"
- a scalar "gap score"
- a scalar "opportunity score"
- a hidden blend whose denominator or dropped legs are not printed
