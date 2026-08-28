---
key: CNLI-CARRIER-CONTEXT-NOT-SELECTOR
question: >
  Does structural washout (deep drawdown, basing, under-long-reference, low
  supply elasticity) act as the program's selector, or as carrier/baseline
  context?
answer: >
  Carrier and baseline context only. Washout defines the U1 carrier-matched
  population and baseline ladder rung 3; it is never the new selector, and no
  static-washout construction may be rescued by threshold or gate shopping.
rationale: >
  Prophet already concentrates in washed-out/coiled names, so a washout selector
  adds no incrementality by construction. The preregistered comparison arms
  closed the static-state route at the bar: P-B2 returned NO DISCRIMINATOR at
  the preregistered bar (calibration-governed null) and P-B3 certified the
  frozen 20 cells as NULL=12 / UNINFORMATIVE=8 with zero certified timing and
  zero certified occupancy. The likely incremental information is transition —
  negative supply becoming less effective — measured against the carrier, not
  the carrier itself.
alternatives:
  - option: Static washout occupancy as a standalone selector
    why_not: >
      P-B2 (#5615) and P-B3 (#5729) closed this construction at the
      preregistered bar; CNLI.NC.STATIC_WASHOUT_OCCUPANCY is now a registered
      negative control that may not be removed after outcomes.
  - option: Rescue via new thresholds/gates on the same construction
    why_not: >
      Post-outcome gate shopping; forbidden by the frozen P-B2/P-B3 records and
      the R4 preregistration law. A new construction requires a fresh prereg.
evidence:
  - "research/cn_limit/CN_LIMIT_R6_FINAL_ARCHITECTURE_FREEZE_2026-08-19.md §4.1, §12"
  - "research/cn_prophet_audit/PB3_PERSISTENCE_ROBUST_CERT_2026-08-15.md — NULL=12, UNINFORMATIVE=8"
  - "DSC:CN-PB3-FROZEN-20-NULL-OR-UNINFORMATIVE"
  - "agentos/workstreams/WS-CN-LIMIT-ALPHA.md waves P-B2/P-B3"
affects:
  - "WS:CN-LIMIT-ALPHA"
  - "research/cn_limit/"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

Sol R6 final architecture freeze. The reopen path for any washout-family
selector claim is a fresh preregistered construction through the R4 gauntlet,
never a rerun or re-thresholding of P-B2/P-B3.
