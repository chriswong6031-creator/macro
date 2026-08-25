# Golden Casebook

This file defines the casebook scaffold for K3E, not outcome claims.

## Purpose

Use a fixed set of named episodes to keep architecture and later evaluations
grounded in real, inspectable expectation / market interaction patterns.

## Required case shapes

1. clean positive expectation revision wave with delayed market catch-up
2. market-first rerating with stale or slow-moving expectations
3. expectations continue while price stalls
4. opposing-sign case where revisions and price disagree
5. high-disagreement / low-coverage case that should end `UNESTIMABLE`
6. post-event cluster case where the old consensus is stale and freshness matters

## Casebook fields

Each case record should eventually pin:

- issuer / security
- episode window
- why this case is informative
- owner-native sources required
- lawful horizons
- expected null / degradation risks
- what a naive single-consensus heuristic would likely get wrong

## Initial named scaffolds

The first merged freeze only names scaffolds, not verdicts:

- `earnings_freshness_break`
- `market_runs_ahead_of_street`
- `street_keeps_revising_price_pauses`
- `mixed_signal_high_dispersion`
- `unestimable_low_coverage`

Populate with real issuers only in later owner-lawful waves.
