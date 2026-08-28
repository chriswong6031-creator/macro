---
key: ALPHA-INTEL-FABLE-A-CONTRACT-FIRST-DISPATCH
question: >
  The FABLE-A Evidence Mesh commission is gated on "FABLE-00 explicitly confirms
  the ownership/collision check is clean." At wave c0 the collision picture
  cleared substantially (#5894 and #5902 merged), but GROK-A0's own
  recommendation returned a first-class negative result — the physical mesh must
  lose to the boring baseline ("call the owner reader") unless a funded consumer
  needs a cross-store pointer index over >=3 owner_stores — and an adversarial
  review of that recommendation found one blocker (a contract-forbidden identity
  join) plus four majors (missing adoption inventory, belief/observation mixing,
  a disguised identity type, unrouted persistence). FABLE-A's acceptance gate
  also requires FIF queryable through the mesh while FIF is stop-for-Sol-review
  (#5889 DO NOT MERGE; FF-1P2 STOP #5898). Dispatch, hold, or recut?
answer: >
  CONDITIONAL GO — dispatch FABLE-A contract-first with the c0 §5.1 binding
  amendment rider (research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md)
  appended verbatim. FABLE-A's First Wave (archaeology → contract freeze)
  proceeds now, consuming A0's census files unchanged and its recommendation AS
  AMENDED: the cik↔ticker "symbol-directory + cik_map" join branch is STRUCK
  (forbidden by const:false in the symbol-directory completion receipt schema);
  an object_class discriminator separates world observations from forward
  claims/instrument state (or qledger.claim/txi.episode drop from v0); identity
  uses Stock Identity + theme-graph epoch ids, never a minted ticker_store_key;
  clock_class binds to synapse asof_field names; the archaeology additionally
  covers engine/institutional_census/ (the dedup precedent), KnowledgeClock/
  VintagePolicy (surfacing the duplicate definition), engine/qledger_evidence_clock.py,
  and the merged #5902 replay harness. NO physical mesh store/index is built
  until the flip condition is met in operator-decidable terms: a NAMED PR or
  workstream COMMITTED to consume, in one query, native objects across >=3
  owner_stores for one subject without importing those engines — a hypothetical
  consumer does not self-certify it. Any later physical persistence routes
  through Data OS conventions AND registers in config/synapse.yml, never a
  presumed data/evidence_mesh/ path. The FIF acceptance leg runs on fixture
  packets only until Sol rules on FIF-1R3; nothing routes around the FF-1P2
  STOP. Golden fixtures and zero rank/gate/size consumers remain required for
  K1 acceptance.
rationale: >
  This preserves the Chairman's K-graph — K2/K3 contract waves need the mesh
  VOCABULARY, not a built store, so dispatching the contract wave unblocks them —
  while honoring the program law that negative results are first-class and a GO
  is never forced. The expensive, risky half of FABLE-A (a physical cross-store
  index) is exactly the half A0 showed is currently unjustified; the cheap half
  (shared vocabulary + frozen temporal/identity semantics) is what every
  downstream lane would otherwise reinvent, a fifth time. The adversarial review
  confirmed every defect in A0's recommendation is an omission or over-permissive
  clause in an otherwise correct frame — repairable by rider, not grounds to
  re-found the design.
alternatives:
  - option: Unconditional GO — build to the commission's acceptance gates as written
    why_not: >
      Forces a store build past A0's boring-baseline verdict, freezes a
      contract-forbidden identity join (reviewer finding F1), and cannot meet
      the FIF acceptance leg while Sol's ruling is pending — a forced GO on all
      three counts.
  - option: HOLD FABLE-A entirely until a funded consumer exists
    why_not: >
      Leaves the K3-E and K3-D contract waves with no shared observation
      vocabulary, so each lane freezes its own clocks and subject keys — the
      exact interoperability failure the program exists to end. The contract
      wave is cheap and the store gate still holds.
  - option: Recut FABLE-A into a new commission document
    why_not: >
      The commission text is sound; only its inputs needed repair. A rider on
      the existing dispatch keeps the Chairman's pack intact and auditable; a
      rewritten commission would fork the pack's provenance.
evidence:
  - "A0 §8 flip condition verbatim: research/evidence_mesh/A0_MINIMAL_EVIDENCE_MESH_RECOMMENDATION.md:169-175"
  - "Blocker F1: A0 recommendation :122 cik↔ticker 'or' branch vs contracts/symbol_directory/symbol_directory_completion_receipt.v1.schema.json:195 listing_sec_identity_binding_eligible const:false; same join listed forbidden in A0's own census :207, duplication map :163, temporal matrix :143"
  - "Major F2: zero hits for institutional_census / KnowledgeClock / VintagePolicy / 5902 across all seven A0 files (adversarial-review greps); the dedup precedent lives at engine/institutional_census/aggregate.py:146-222"
  - "PASS-0 §7 conditions: research/alpha_intelligence/MASTERMIND_ALPHA_INTELLIGENCE_EXPANSION_PASS0_2026-08-18.md:176-186"
  - "Delta receipts (#5894, #5902 merged; #5889/#5898 open freezes): research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md §2"
  - "FABLE-A commission acceptance list: operator pack mastermind_fanout_FABLE-A_evidence_mesh.md (read in full at c0)"
affects:
  - "research/alpha_intelligence/C0_WAVE0_ADJUDICATION_2026-08-19.md"
  - "agentos/workstreams/WS-ALPHA-INTELLIGENCE-INTEGRATION.md"
  - "research/evidence_mesh/A0_MINIMAL_EVIDENCE_MESH_RECOMMENDATION.md"
confidence: high
reversibility: easy
decided_by: FABLE-00 seat, wave c0
decided_at: 2026-08-19
---

## Grounds

The commission's own dispatch gate hands the GO/NO-GO to the FABLE-00 seat. Wave
c0 held all four inputs: the cleared collision delta, A0's negative result, the
adversarial review of A0's recommendation, and the standing Sol freezes. The
rider converts every reviewer finding into a dispatch condition so the contract
wave inherits repairs, not holes.

## What would reopen this

A named consumer committing to a >=3-owner_store single-query read fires the
flip condition and authorizes the store build (that is the gate working, not a
reversal). An adverse Sol ruling on FIF-1R3 that invalidates a frozen clause, or
a FABLE-A return that cannot honor the rider without a store, comes back to the
FABLE-00 seat for re-adjudication rather than proceeding.
