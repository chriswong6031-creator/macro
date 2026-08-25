---
key: K3E-OPPORTUNITY-EVIDENCE-VECTOR-CONTRACT
question: >
  What is the one canonical, typed Opportunity Evidence Vector contract (Alpha
  Intelligence K3-E) that lets future OpportunityCase/Market OS consumers understand
  an opportunity without a fused score — and how are its semantics made executable
  without building a store, a ranker, or any Prophet/Radar coupling?
answer: >
  K3-E freezes opportunity_evidence.vector.v1: a typed, deterministic VIEW/JOIN
  projection over canonical owner outputs for one subject at one PIT decision time.
  Wire: contracts/opportunity_evidence/vector.v1.schema.json (closed) +
  slot_registry.v1.json (the executable family-mapping receipt); semantics:
  lib/opportunity_evidence.py (fail-closed validator with stable K3E_R### codes +
  pure in-memory composer); proofs: golden/hostile fixtures with byte/SHA receipts
  and a mutation-kill matrix. Slots freeze
  {construct, state, asof, known_at, value_or_null, coverage_flag} plus K1
  object_class, K1-exact missingness, registry-pinned clock-class bindings over
  unrenamed owner-native fields, owner_ref, derivation, provenance (no LLM member),
  peer-basis disclosure, and variation receipts. The seven authenticated-MO legs
  (observed / inferred / market-reflection / strongest-unresolved-fact /
  failed-unavailable-gates / next-observable / entry-availability) are independent
  required projections. Aggregates are denominator receipts only; dominant
  degradation is mandatory; adverse states never become zero or neutral. Residuals
  are owner-read from the DRL seam (engine.price_pressure.ledger.read_ledger) and
  engine/residual_alpha.py, never re-derived; the dislocation decomposition emits
  named per-term components with an executable reconstitution kill; the impairment
  axis is recorded as UNOWNED; ETF-flow states derive from observed artifact
  variation; every slot maps to exactly one governed fusion family (verbatim
  research/prophet_fusion/families.yml member, join test-enforced), research_only,
  or candidate_new_family routed to K5/Eval OS. Neither Prophet nor Radar consumes
  or writes the vector; entry availability is an owner READ under
  DEC:PROPHET-LAB-B5A-RECUT's read-only verbs; the authority envelope is the exact
  K1 all-false set including can_open_entry. No store, path, synapse row, or
  consumer is created or armed. Delivery is one bounded PR held DRAFT/HOLD-FOR-SOL.
rationale: >
  Sol's K3-E commission (2026-08-25) binds the accepted E0 laws and C0 §4.1
  rulings 1–6 plus the authenticated-MO rider. The E0 census already ruled the
  boring baseline: the nearest existing bag is the US Context Vector, and a view
  over existing stores is the only lawful shape — a new store would duplicate an
  owner. Making the semantics executable (validator + hostile fixtures) is the
  smallest closed artifact that prevents the ten commissioned failure modes from
  shipping later inside a consumer. Reusing K1's clock classes, object classes,
  and missingness enums verbatim (test-enforced equality) closes the fifth-PIT-
  vocabulary risk permanently.
alternatives:
  - option: Extend the US Context Vector producer (engine/us_context_vector.py) with opportunity columns instead of freezing a view contract
    why_not: >
      That is a store change owned by the Prophet US roadmap, not lane E; it would
      couple the vector's semantics to the nightly producer before any consumer is
      authorized, and E0's Q1 default (view / research join; do not mint a second
      per-name nightly store) rules it out.
  - option: Express the vector purely as K1 EvidenceBlocks/Recipes with no new schema
    why_not: >
      K1's 13-owner vocabulary covers governance-plane owners, not the market-data
      artifacts most slots read (DRL ledger, revisions, FINRA SI, options stores);
      forcing those through K1 owner rows would require growing K1's vocabulary —
      changing the accepted K1 surface, which this commission forbids. The vector
      instead reuses K1's clock/missingness/object-class vocabulary verbatim and
      carries optional efr_ refs where a K1 owner exists.
  - option: Include lifecycle staging (NEGLECTED→…) and pair-relative slots in the v1 wire
    why_not: >
      NEGLECTED is not yet a data state (E0 Q6) and pair outcomes are winner-library
      convenience samples; putting them on the wire invites exactly the
      narrative-fills-UNKNOWN failure the casebooks warn against. They stay research
      vocabulary outside the contract.
evidence:
  - "Sol K3-E commission 2026-08-25 (session charter); protected Skillpack pin 51f9942733b86e550bb9169d2a43462bd28e774f; Macro base pin 2c20168df5d9e711825f7fca5983b4bbab69711d"
  - "C0 §4.1 E0 adjudication ACCEPTED-with-conditions: research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md (rulings 1–6 disposed in the freeze packet §5)"
  - "K1 accepted vocabulary: contracts/evidence_foundation/ (clock classes, missingness, object classes reused verbatim; enum-equality test in the K3-E suite)"
  - "Fusion family law: research/prophet_fusion/families.yml (one-column-one-family; registry join asserted by the K3-E suite on every run)"
  - "DRL ownership boundary: engine/price_pressure/ (residual-shock + filing-coverage family only; grep for 'impair' over its masterplan and code exits 1 — the impairment axis is unowned)"
  - "Market OS seam: contracts/market_os/security_state.v1.schema.json legs.opportunity_context ships market_incorporation/dislocation refs null/NOT_COVERED (engine/security_state.py:969-994) — the typed gap this object can later fill under a separate commission"
  - "Freeze packet: research/opportunity_evidence/K3E_OPPORTUNITY_EVIDENCE_VECTOR_CONTRACT_FREEZE_2026-08-25.md (binding-law disposition, family-mapping receipt, mutation matrix, owner gaps)"
affects:
  - "research/opportunity_evidence/"
  - "contracts/opportunity_evidence/"
  - "lib/opportunity_evidence.py"
  - "agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md"
confidence: high
reversibility: easy
decided_by: fable
decided_at: 2026-08-25
---

## Grounds

The commission's observable mission is a frozen contract, not a build: the value is
that every later consumer (K5 OpportunityCase, Market OS security-state views)
inherits typed, fail-closed semantics instead of re-inventing them, and that the ten
named failure modes (scalar reconstruction, missing→neutral, clock collapse,
double-family homing, residual re-derivation, cause-from-ε, identity laundering,
Prophet/Radar leakage, look-ahead, LLM origination) are killed executable-first —
each with a fixture that fails today, not a prose warning that decays.

## Boundaries

The contract carries zero authority and arms nothing. The PR is DRAFT/HOLD-FOR-SOL;
merge, any consumer wiring, K3-D, K5, any store, and any promotion each require
their own authorization. Statistical evidence and economic-cause hypotheses remain
two objects; instrument verdicts remain footnotes to the tape's dual-read.
