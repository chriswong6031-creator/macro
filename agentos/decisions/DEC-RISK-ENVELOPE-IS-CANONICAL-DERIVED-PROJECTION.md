---
key: RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION
question: >
  Is the cross-repository risk contract a new truth store with its own history
  and authority, or a derived projection composed from existing owned organs?
answer: >
  A derived projection. site/riskdata/risk_envelope.json is the settled
  cross-repository contract; site/live/risk_envelope.json is its live
  provisional sibling. Both are produced through one pure composer
  (engine/risk_envelope.py, future) so the live path may supply fresher allowed
  inputs but can never fork state or policy logic. The envelope is not a truth
  store, owns no forward ledger, and is not an authority source: its top-level
  authority booleans (rank/gate/size/execute) are permanently false, and every
  action must trace to an individually registered policy object.
rationale: >
  Mastermind already owns event history (Chronicle), action firing ledgers
  (Reflex Registry), grading (QLedger/Evaluation OS), and artifact registration
  (Synapse). A second truth plane would drift from the first — the exact
  duplicate-control-plane failure the org has banned repeatedly. A pure
  composer makes settled and live states byte-comparable, testable
  (same inputs → same semantic output), and keeps "what the user saw" derivable
  from inputs plus definition version. Authority lives in policy objects, not
  in a document, so consumers can never treat a rendered file as a gate.
alternatives:
  - option: Envelope as a new persistent risk database advancing its own history
    why_not: >
      Second event store — forbidden by command packet law 7 and the freeze
      durable-history ruling (§4); nightly forward-ledger advancement is owned
      elsewhere and duplicate ledgers are how track records become unauditable.
  - option: Separate live and settled composers
    why_not: >
      Two implementations of the same semantics guarantee fork drift; the
      incident already showed live and settled surfaces disagreeing without a
      lawful explanation.
  - option: Envelope carries authority directly (a gate flag consumers obey)
    why_not: >
      An envelope-wide threshold would manufacture policy without promotion,
      scope, or counterfactual receipts — the fused-shield failure in another
      shape (see DEC:SCOPED-REFLEX-CONSTRAINTS-NOT-FUSED-SHIELD).
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §5 (contract, canonical paths, authority booleans), §4 (topology)"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §5 laws 6-8, §11 GD-2/GD-3 packets"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "engine/risk_envelope.py (future)"
  - "scripts/build_risk_envelope.py (future)"
  - "scripts/build_live_risk_envelope.py (future)"
  - "site/riskdata/risk_envelope.json + site/live/risk_envelope.json (future)"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19 (§4-§5). GD-2/GD-3 implement the two
builders against one composer; GD-0A lands the contract's identity only.

## What would reopen this

A Sol-level architecture act. If GD-2 archaeology finds the pure-composer
shape cannot express a required lawful behavior (e.g., a correction flow that
needs state the composer may not hold), the finding escalates to Sol rather
than quietly granting the envelope storage or authority.
