---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: claude/cs-v2-w1b-closed-bundle
model: sonnet
ended_because: ci_handoff
mission: >
  W1B correction on merged #6012: make re-observation/revision persistence
  obey the accession-wide closed-manifest-bundle contract. Do not start W2.
state_before: >
  W1A merged as #6012. Sol accepted format-2 event identity, no fresh
  legacy:{source_id} child identities, and bundle-level re-observation.
  classify_bundle_against_published still returned only changed members in
  append, so a revision could persist an incomplete N+1 bundle.
changed:
  - path: engine/capital_structure/source_identity.py
    what: >
      classify_bundle_against_published persist=all candidates on revision,
      empty on re_observed; changed is diagnostic. Added
      refine_evidence_ids_for_semantic_compare for legacy→coordinate
      comparison-only identity refinement.
  - path: collectors/sec_capital_structure.py
    what: >
      Children always parent to the candidate complete manifest_id.
      Revision appends decision persist (whole bundle), not changed members.
  - path: scripts/compile_capital_structure_events.py
    what: >
      Semantic compare refines historical legacy child evidence_ids onto
      later coordinate-bound ids so identity migration is not a correction.
  - path: tests/test_capital_structure_closed_bundle.py
    what: Hostile collector E2E closed-bundle cases plus historical refinement.
  - path: agentos/decisions/DEC-CS-V2-CLOSED-BUNDLE-ATOMIC-PERSISTENCE.md
    what: Bundle-atomic persist law.
verified:
  - claim: W1 hostile suite plus W1B closed-bundle regressions pass locally
    command: >
      python3.12 -m pytest tests/test_capital_structure_closed_bundle.py
      tests/test_capital_structure_evidence_identity.py
      tests/test_capital_structure_event_spine.py
      tests/test_capital_structure_compiler.py
      tests/test_sec_capital_structure.py
      tests/test_append_only_base_fence.py -q
    result: 69 passed
unverified:
  - claim: Natural post-W1B collector → Capital Structure chain production proof
    what_would_verify: First scheduled CS job after W1B merge; no second dispatch
unresolved:
  - Sol acceptance of W1B; do not merge until accepted
  - Production proof on the natural CS path after merge
  - W2 live-tail still not started
next_actions:
  - Make attributable CI green on the W1B PR
  - Hand to Sol; do not start W2
  - After merge, prove the natural scheduled collector → CS chain
do_not_redo:
  - Reopen W0 architecture
  - Start W2 live-tail / MAX_FILINGS / work-class split
  - Rewrite historical manifest_id or event_id bytes
  - Mint legacy:{source_id} as a new child occurrence key
  - Hash source.manifest_ids or PIT clocks into post-W1 event identity
  - Shortcut re-observation on the complete row alone
  - Persist only the changed members of an N+1 closed bundle
danger_areas:
  - Dual-read event identity: historical format 1 vs post-W1 format 2
  - Closed bundle: every N+1 child must parent the N+1 complete
  - Identity refinement is comparison-only; do not rewrite v1 rows
prs: []
decisions:
  - DEC:CS-V2-CLOSED-BUNDLE-ATOMIC-PERSISTENCE
---

W1B is a persistence correction on merged #6012. Hand to Sol. Do not start W2.
The CS job already calls the whole-generation append-only fence
(DEC:CS-V2-WHOLE-GENERATION-APPEND-ONLY-FENCE, daily.yml capital_structure push).
Do not revive the stale claim that the CS push lacks that fence.
