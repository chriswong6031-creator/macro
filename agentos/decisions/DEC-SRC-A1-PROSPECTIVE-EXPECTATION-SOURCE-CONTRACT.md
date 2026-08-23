---
key: SRC-A1-PROSPECTIVE-EXPECTATION-SOURCE-CONTRACT
question: >
  Which existing owner, artifacts, clocks, attempt semantics, idempotency and
  correction rules must SRC-A1 use to accrue prospective EPS/revenue expectations
  without creating a second source or requiring a builder to choose the design?
answer: >
  SRC-A1 is an additive source-owner extension of collectors/equity_revisions.py.
  It writes only data/revisions/expectation_observations.parquet and
  data/revisions/expectation_attempts.parquet under the frozen long-form,
  multi-clock, append/supersede contract in the accepted K3E matrices.
  collectors/yf_analyst.py remains the price-target/rating lane; legacy revisions
  artifacts retain their present semantics.
rationale: >
  K3E needs prospective, as-known expectation observations before any derived
  surface can honestly reason about multi-horizon consensus change. The existing
  revisions lane already owns the provider access and revision-breadth artifacts,
  but the accepted SRC-A1 handoff left physical storage, exact clocks, attempt
  receipts, retry behavior, corrections, and rate-limit evidence underspecified.
  Freezing those choices in the owner lane prevents a third analyst store,
  hindsight backfill, silent coverage substitution, and cadence expansion that
  turns provider throttling into apparent data coverage.
alternatives:
  - option: Let a new K3E/Market-Belief store collect raw consensus history
    why_not: >
      Violates DEC:MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE and duplicates
      the existing revisions source owner.
  - option: Extend collectors/yf_analyst.py because it already reads analyst data
    why_not: >
      That collector is the price-target/rating lane; moving prospective
      EPS/revenue collection there would blur physical ownership and legacy semantics.
  - option: Store only the newest values and a freshness date
    why_not: >
      It cannot reconstruct as-known multi-horizon trajectories, corrections,
      nulls, attempts, or rate-limit coverage and invites current-value backfill.
evidence:
  - "DEC:K3E-EXPECTATION-MARKET-DYNAMICS-FREEZE"
  - "DEC:MARKET-BELIEF-IS-COMPOSITION-NOT-TRUTH-STORE"
  - "research/alpha_intelligence/expectation_market_dynamics/DATA_CLOCK_RIGHTS_MATRIX.md"
  - "research/alpha_intelligence/expectation_market_dynamics/OWNER_AND_REUSE_MATRIX.md"
  - "collectors/equity_revisions.py: existing revisions owner and latest/history semantics"
  - "collectors/yf_analyst.py: existing price-target/rating lane"
  - "DNR:KILL-FUSED-COMPOSITE"
  - "DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER"
affects:
  - WS:ALPHA-INTELLIGENCE-INTEGRATION
  - WS:MARKET-OS
  - "collectors/equity_revisions.py"
  - "data/revisions/expectation_observations.parquet"
  - "data/revisions/expectation_attempts.parquet"
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-23
---

This is a records-only physical/source-contract amendment. It authorizes no
runtime/model implementation by itself, no vendor procurement/contact, no fair
value/rank/gate/size/trade/Prophet authority, and no production deployment.
