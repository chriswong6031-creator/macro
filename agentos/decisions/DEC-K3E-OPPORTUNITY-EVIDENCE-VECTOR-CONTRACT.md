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
  Amended 2026-08-25 by Sol REQUEST_CHANGES on head ac2be650a360 (architecture
  accepted in principle; repaired on the same carrier): (1) the decision clock is
  REFERENCE-BOUND, not asserted (how far that binding authenticates depends on the
  source — see the 2026-08-26 amendment below, which caps the generic path) — the
  free-string t0_source_object and its
  caller_named_pit_object source are deleted from the wire and replaced by a
  required t0_evidence_ref reusing K1 reference.v1 EvidenceRef semantics
  (owner_store, native_identity, native_digest) plus a known minting clock and a
  t0_mode from K1 replay.mode, all authenticated against a registry t0_sources
  section by K3E_R021, which fails a 'live' t0 whose object was minted past that
  source's recording-lag budget; (2) public validation recomputes EVERY mandatory
  denominator including market_reflection and failed_or_unavailable_gates under
  frozen inclusion semantics shared with the composer, where modeled
  market-reflection evidence counts as INCLUDED rather than silently excluded for
  not being observed; (3) Entry Availability ownership is corrected — the leg reads
  ONLY the canonical live actionability surface (engine.entry_signal.assess ->
  prophet.board_read/v1 entry_signal.status, registered as prophet_entry_signal
  with entry_role 'actionability'), Prophet board admission (lane/buyable/eligible)
  is re-classed entry_role 'admission_context' owning no leg and referenceable from
  none, Radar probe availability is typed probe/coverage state and never a
  trade-entry verdict, and an unavailable owner leaves the leg explicitly
  missing/unknown rather than inferred from admission.
  Amended again 2026-08-26 by Sol REQUEST_CHANGES on head 2d9b72c6132518
  (items 2 and 3 ruled PASS; two remaining blockers repaired on the same
  carrier): (A) the GENERIC decision-time path may no longer claim operational
  point-in-time. owner_pit_reference pins no owner_store and no clock class, so
  its store, its minting clock and the bytes behind its digest are all
  caller-declared — it is an accountability receipt (a falsifiable commitment,
  checkable by anyone who fetches the object) and NOT a validation-time
  verification. The registry therefore carries lawful_t0_modes per source,
  owner_pit_reference is restricted to ['retrospective_research'], and K3E_R021
  fails a generic+live vector closed; its max_recording_lag_days is null by
  construction, which is a second independent fence because widening the mode
  list alone still fails closed on the missing budget. Only the four sources
  whose owner_store and clock class validation actually checks may claim 'live',
  and a source with no lawful_t0_modes pin may claim only the weaker mode. No
  owner I/O, producer, or second truth plane is added — the unverifiability is
  named as a standing gap rather than papered over. (B) receipt truth: the
  packet's contract-delta claim of '0 introduced, 0 inherited' was false in its
  second half and is corrected to the exact hosted result on the held head,
  0 introduced / 4 inherited, with the four findings named and attributed to the
  main-side lane that owns them rather than healed from this carrier.
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
  - "Freeze packet: research/opportunity_evidence/K3E_OPPORTUNITY_EVIDENCE_VECTOR_CONTRACT_FREEZE_2026-08-25.md (binding-law disposition, family-mapping receipt, mutation matrix, owner gaps; §7.2 = the Sol REQUEST_CHANGES disposition with named mutation receipts)"
  - "Sol REQUEST_CHANGES on PR #6417 head ac2be650a360 (2026-08-25): architecture accepted in principle, three repairs required on the same carrier — decision-time authentication, denominator integrity, Entry Availability ownership"
  - "Entry actionability owner: engine/entry_signal.py (assess) projected by engine/prophet_board_read.py as SCHEMA 'prophet.board_read/v1' status field — the axis that answers 'should I buy it NOW', distinct from board admission (lane/buyable/eligible)"
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

A second independent red-team then attacked the repair itself and returned
STATUS: FAIL — the durable lesson being that the first repair had added the
right vocabulary while leaving the enforcement reachable around it. Two examples
worth carrying forward. A construct's NAME was the only thing separating the
entry-actionability owner from board admission, because `prophet_entry_signal`
and `prophet_board_lane` share family binding, derivation, and clock classes and
nothing compared a slot's `owner_ref` to its registry pin: a slot could wear the
other owner's name, carry the other owner's payload, and satisfy the Entry
Availability leg with zero findings. And recomputing the `market_reflection`
denominator proved nothing while the leg SET itself was caller-controlled —
deleting the five adverse legs reported 2-of-7 coverage as 2/2 = 100%. The
general rule this contract now encodes: **recomputing an aggregate is integrity
only if the population it counts over is itself fixed**, and **a registry pin
that nothing compares against is documentation, not a constraint.**

Sol's REQUEST_CHANGES sharpened three places where the first cut typed a fact
without proving it. The decision clock is the load-bearing one: a vector whose t0
can be asserted by a caller string is a vector whose entire PIT discipline rests on
good faith, because every look-ahead check downstream measures against that t0. The
repair does not add a new vocabulary — it binds t0 to the same K1 EvidenceRef
semantics the rest of the wire already reuses, and makes the "chose t0 with
hindsight" case fail closed unless the vector visibly declares itself retrospective.
The Entry Availability correction is the same class of error one level up: reading
board ADMISSION (is this name on the board) as if it answered ACTIONABILITY (is an
entry open now) would have let a consumer infer a trade verdict this contract has no
authority to express — so the two roles are now separate registry roles, and
admission owns no leg at all.

Sol's second REQUEST_CHANGES (2026-08-26) closed the one place where that lesson
had been learned only halfway. The second red-team caught the registry
overclaiming what the generic `owner_pit_reference` proves, and the repair
corrected the *description* — an honest boundary note saying the source is an
accountability receipt, not a verification — while leaving that same source free
to declare `t0_mode: "live"`, the wire's word for operational point-in-time. Two
shipped goldens promptly did, one of them justifying it in a comment with "the
decision-time object provably existed at t0," which validation has no way to
know: the store, the recording date, and the bytes behind the digest are all
caller-supplied there, so a zero recording lag computed from a caller's own clock
is arithmetic, not evidence. The durable generalization: **disclosing a limit is
not enforcing it — an artifact that documents its own unverifiability and then
ships the strong claim anyway has documented nothing.** The fix is a permission,
not a warning (`lawful_t0_modes`), and it is deliberately awkward to undo: the
lag budget for that source is null, so re-opening `live` by editing the mode list
alone still fails closed, and a future wave must mint a budget on purpose.

The same standard applies to this session's own receipts. The packet claimed
contract-delta `0 introduced, 0 inherited` when the hosted gate had actually
returned `0 introduced, 4 inherited`; the differential gate's PASS depends only
on the first number, which is exactly why the second one is easy to round off.
Four real main-side findings were erased from the record by a receipt that was
half true. **A receipt that reports only the half that decides the gate is a
summary, not a receipt** — record what the run returned, name what it named, and
attribute it to the lane that owns it.

## Boundaries

The contract carries zero authority and arms nothing. The PR is DRAFT/HOLD-FOR-SOL;
merge, any consumer wiring, K3-D, K5, any store, and any promotion each require
their own authorization. Statistical evidence and economic-cause hypotheses remain
two objects; instrument verdicts remain footnotes to the tape's dual-read.
