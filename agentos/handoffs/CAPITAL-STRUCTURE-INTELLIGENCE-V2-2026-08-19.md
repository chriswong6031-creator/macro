---
workstream: WS:CAPITAL-STRUCTURE-INTELLIGENCE-V2
session: claude/cs-v2-w1a-identity-correction
model: sonnet
ended_because: ci_handoff
mission: >
  W1A correction on merged #5959: make post-W1 event-version identity
  clock-independent, forbid new legacy:{source_id} child occurrence writes,
  adjudicate re-observation at bundle level, and document first_known_at as
  the verified-retention clock frozen at canonical publication. Do not start W2.
state_before: >
  W1 merged as #5959 / b7004b132509. Sol verdict: merged but not accepted.
  build_event_version still hashed the full event body including
  source.manifest_ids and PIT clocks. _manifest_record fell back to
  legacy:{source_id} when child byte coordinates were absent. Re-observation
  short-circuited on the complete row. Schema called first_known_at a Git
  publication timestamp while the collector stored retrieved_at.
changed:
  - path: engine/capital_structure/event_spine.py
    what: >
      Added identity_format 2. Post-W1 events with evidence_ids hash
      event_identity_preimage (semantic state + evidence_ids + correction
      chain) excluding manifest_ids and point_in_time clocks. Historical
      events omit identity_format and keep the full-body hash.
  - path: scripts/compile_capital_structure_events.py
    what: _validate_event_identity dual-reads via compute_event_id.
  - path: contracts/capital_structure_event.schema.json
    what: Optional version.identity_format const 2.
  - path: engine/capital_structure/source_identity.py
    what: >
      ChildOccurrenceUnbound, writable_child_occurrence, interpretation_fingerprint,
      classify_bundle_against_published. Read-side legacy:{source_id} projection
      unchanged for historical v1 children.
  - path: collectors/sec_capital_structure.py
    what: >
      New child writes require parent byte coordinates or raise
      ChildOccurrenceUnbound. Re-observation is bundle-level via
      classify_bundle_against_published and evidence_id_from_manifest.
  - path: contracts/capital_structure_source_manifest.schema.json
    what: first_known_at description is verified-retention clock, not Git commit time.
  - path: agentos/decisions/DEC-CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK.md
    what: Clock adjudication for first_known_at.
  - path: tests/test_capital_structure_event_spine.py
    what: Independent post-W1 event_id, correction, A→B→A, historical format-1 hash.
  - path: tests/test_capital_structure_evidence_identity.py
    what: Independent compile, no new legacy child ID, bundle re-observation cases.
verified:
  - claim: W1 hostile suite plus W1A regressions pass locally
    command: >
      python3.12 -m pytest tests/test_capital_structure_event_spine.py
      tests/test_capital_structure_evidence_identity.py
      tests/test_capital_structure_compiler.py
      tests/test_capital_structure_legacy_compat.py
      tests/test_sec_capital_structure.py
      tests/test_capital_structure_ingestion_health.py
      tests/test_capital_structure_pit.py
      tests/test_capital_structure_graph.py
      tests/test_capital_structure_contracts.py
      tests/test_capital_structure_source_identity.py
      tests/test_daily_capital_structure_job.py
      tests/test_append_only_base_fence.py -q
    result: 249 passed
  - claim: agentos records validate
    command: python3.12 scripts/agentos.py validate
    result: 0 error(s)
unverified:
  - claim: Natural post-W1A scheduled CS job production proof
    what_would_verify: First daily capital_structure job after W1A merge; no second dispatch
unresolved:
  - Sol acceptance of W1A; do not merge until accepted
  - Production proof on the natural CS path after merge
  - W2 live-tail still not started
next_actions:
  - Make attributable CI green on the W1A PR
  - Hand to Sol; do not start W2
  - After merge, prove the natural scheduled CS path
do_not_redo:
  - Reopen W0 architecture
  - Start W2 live-tail / MAX_FILINGS / work-class split
  - Rewrite historical manifest_id or event_id bytes
  - Mint legacy:{source_id} as a new child occurrence key
  - Hash source.manifest_ids or PIT clocks into post-W1 event identity
  - Shortcut re-observation on the complete row alone
danger_areas:
  - Dual-read event identity: historical format 1 vs post-W1 format 2
  - ChildOccurrenceUnbound must defer the bundle, not invent an ID
  - classify_bundle_against_published must use evidence_id_from_manifest for v1 rows
prs: []
decisions:
  - DEC:CS-V2-FIRST-KNOWN-AT-IS-CANONICAL-RETENTION-CLOCK
---

W1A is a corrective wave on merged #5959. Hand to Sol. Do not start W2.
