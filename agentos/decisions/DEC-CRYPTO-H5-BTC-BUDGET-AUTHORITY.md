---
key: CRYPTO-H5-BTC-BUDGET-AUTHORITY
question: >
  Should Crypto H5 continue deriving total crypto exposure directly from
  vector/signals.alloc_optimal, or consume the canonical P0A Bitcoin DecisionState?
answer: >
  H5 must consume the canonical decision-bearing final BTC exposure as its total
  crypto budget. The class overlay may only split that budget across BTC, ETH and
  altcoins, with cash as the residual. If the canonical decision is unavailable
  or fails integrity, H5 must fail closed rather than recompute or fall back to
  raw signal state.
rationale: >
  P0A created btc.decision/v1 specifically to make final exposure and user action
  singular, provenance-visible and integrity checked. H5 currently rereads
  signals.alloc_optimal and therefore bypasses those checks while its own UI says
  Bitcoin Vector sets total crypto exposure. That can leave H5 actionable when the
  canonical decision surface is correctly unavailable. Reusing the existing
  decision projection preserves one sizing authority. The existing class overlay
  remains a deterministic split/context layer and gains no authority to size total
  crypto exposure.
alternatives:
  - option: >
      Keep H5 reading signals.alloc_optimal directly because it is the same
      economic source column used by btc.decision/v1.
    why_not: >
      Same source value is not the same authority boundary. The direct read bypasses
      btc.decision/v1 integrity and fail-closed semantics, so two decision-bearing
      consumers can disagree on whether the state is eligible to act on.
  - option: >
      Create a new crypto-wide allocation or sizing model for H5.
    why_not: >
      That would expand P0B into new signal authority, duplicate the existing BTC
      budget owner and violate the program's no-premature-signal-authority boundary.
evidence:
  - >
    PR #6294 merged as f039c86ae037cf75238cfdd1f3d732d9b643dbb7 after the
    exact reconciliation head e573a341e406532748a9ba62e69e8c5444341630 passed
    CI, fence and authority workflows.
  - >
    engine/btc_decision.py at main ce4a33aeeed779530942560c5b05f4df8ab0306c
    defines btc.decision/v1 as the sole final exposure projection and fails closed
    on integrity errors.
  - >
    scripts/build_crypto.py at main ce4a33aeeed779530942560c5b05f4df8ab0306c
    has _allocation() derive H5 total exposure from latest["alloc_optimal"] directly.
  - >
    site/crypto.html at main ce4a33aeeed779530942560c5b05f4df8ab0306c says
    Bitcoin Vector sets total crypto exposure and the class overlay only splits it.
affects:
  - "WS:CRYPTO-INTELLIGENCE"
  - crypto-intelligence
  - scripts/build_vector.py
  - scripts/build_crypto.py
  - templates/crypto.html.j2
  - tests/test_crypto_wave2.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-24
---

# Crypto H5 BTC budget authority

P0B closes one authority seam. It does not redesign the crypto cockpit and it does
not introduce a crypto-wide optimizer.

## Frozen boundary

The total risk budget shown in H5 is a projection of the already-governed final BTC
DecisionState. H5 may deterministically split an available final exposure among BTC,
ETH and altcoins using the existing class overlay, and cash remains the residual to
100%. The overlay cannot originate, raise, lower, rescue or otherwise replace the
total budget.

An unavailable `btc.decision/v1` state is an unavailable H5 budget. No direct
`signals.alloc_optimal` fallback, stale prior value, silent zero, legacy recommendation
or newly invented score may make the shelf look actionable.

## Implementation preference

Prefer extending the existing `crypto.cockpit/v1` display projection with the
already-built P0A DecisionState or the minimum additive fields required for H5 to
consume its status and final exposure. Do not create a second durable DecisionState
file or parallel allocation truth store merely to bridge the two pages.

## What would reverse this decision

Only a separately commissioned architecture decision that changes the program-level
owner of total crypto exposure, with point-in-time replay and forward promotion
proof, may replace Bitcoin DecisionState as H5 budget authority.