---
workstream: WS:FUNDAMENTAL-FORENSICS
session: claude/ff1-acceptance-time-equivalence-20260824
model: codex
ended_because: blocked
mission: >
  Implement only the Sol-commissioned FF-1R canonical duplicate
  acceptance_datetime representational-equivalence repair, with direct,
  recovery-path, and incremental-path regression proof, then preserve the
  packet in held PR #6391 for Sol review of its exact candidate head.
state_before: >
  Production recovery was frozen after ANGO accession 0001628280-26-048138
  failed closed on acceptance_datetime conflict. Plan
  e252f0a85c193323be128b6de2762c522a0ab86b74d8a2ed15a1f3014695e5a4
  remained cursor/completed 0, backlog 2,571 and null last-successful recovery
  receipt. DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT remained true.
changed:
  - path: engine/fundamental_forensics/broad_sec_store.py
    what: >
      Add one duplicate-fact compatibility helper used only by _merge_filing_rows:
      exact equality first, otherwise valid acceptance_datetime strings compare by
      the frozen _iso_order_key and every other difference remains a conflict.
  - path: tests/test_fundamental_forensics_broad_sec.py
    what: >
      Add direct discriminators, a production-shaped ANGO recovery regression,
      and an ordinary incremental predecessor/successor representation regression.
  - path: agentos/decisions/DEC-FF-1-ACCEPTANCE-DATETIME-COMPARES-BY-INSTANT.md
    what: Record Sol's bounded source-comparison adjudication without changing recovery authority.
  - path: agentos/workstreams/WS-FUNDAMENTAL-FORENSICS.md
    what: Mark the workstream parked while FF-1R remains in_progress and no-dispatch / FF-2 prohibitions remain explicit.
  - path: agentos/handoffs/FUNDAMENTAL-FORENSICS-2026-08-24-FF-1R-ACCEPTANCE-DATETIME-REPAIR.md
    what: Preserve the narrow local handoff and frozen production state for held-PR Sol review.
prs: [6391]
verified:
  - claim: The requested focused tests failed before production code changed.
    command: >
      python3 -m pytest -q tests/test_fundamental_forensics_broad_sec.py::test_duplicate_filing_acceptance_datetime_compares_by_instant_only tests/test_fundamental_forensics_broad_sec.py::test_ff1r_ango_timestamp_representation_reconciles_without_rewriting_legacy_evidence tests/test_fundamental_forensics_broad_sec.py::test_incremental_reads_valid_manifest_larger_than_pointer_envelope
    result: >
      3 failed: canonical Z versus .000Z raised historical_submissions_conflict,
      the ANGO-shaped recovery stopped on that same conflict, and ordinary
      incremental rejected its predecessor duplicate.
  - claim: The focused direct and runtime matrix passed after the minimal helper change.
    command: >
      python3 -m pytest -q tests/test_fundamental_forensics_broad_sec.py::test_duplicate_filing_acceptance_datetime_compares_by_instant_only tests/test_fundamental_forensics_broad_sec.py::test_ff1r_ango_timestamp_representation_reconciles_without_rewriting_legacy_evidence tests/test_fundamental_forensics_broad_sec.py::test_incremental_reads_valid_manifest_larger_than_pointer_envelope
    result: 3 passed; pytest emitted only existing temporary-directory cleanup warnings.
  - claim: The complete broad-SEC suite still passes on the sparse worktree.
    command: python3 -m pytest -q tests/test_fundamental_forensics_broad_sec.py
    result: 120 passed, 1 skipped; only existing temporary-directory cleanup warnings.
  - claim: The locally discovered adjacent EDGAR-index, workflow-lane, and collector tests still pass.
    command: >
      python3 -m pytest -q tests/test_fundamental_forensics_edgar_index.py
      tests/test_filing_forensics_broad_sec_lane.py
      tests/test_edgar_forensics_collector.py
    result: >
      44 passed; expected duplicate master.idx fixture warning and existing
      temporary-directory cleanup warnings only.
  - claim: Agent OS records and whitespace are valid.
    command: python3 scripts/agentos.py validate && git diff --check
    result: >
      Agent OS validation reported 0 errors and 33 pre-existing repository-wide
      warnings; git diff --check exited 0.
unverified:
  - claim: Any production recovery advance, deployment, merge, or live proof.
    what_would_verify: >
      Sol review of PR #6391's exact held candidate head, followed only
      by separately authorized production evidence; no merge or recovery action
      is authorized by this handoff.
unresolved:
  - >
    PR #6391's exact held candidate head requires Sol review. This packet does
    not release a merge or authorize a recovery dispatch.
  - >
    Production remains frozen at cursor/completed 0, backlog 2,571 and null
    last-successful recovery receipt until separately authorized evidence changes it.
next_actions:
  - Sol must review PR #6391's exact held candidate head; do not merge or dispatch recovery.
  - Preserve DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT; it remains the factual
    production witness while DEC:FF-1-ACCEPTANCE-DATETIME-COMPARES-BY-INSTANT
    records the narrow representational-equivalence rule.
  - Do not dispatch recovery, skip ANGO, advance the cursor, change parsers or
    order keys, start prior-quarter recovery, or start FF-2.
do_not_redo:
  - >
    Do not normalize acceptance_datetime text, prefer a source, rewrite legacy
    manifest bytes, weaken other duplicate fields, or make malformed timestamps compatible.
  - >
    Do not change _parse_acceptance or _iso_order_key; both remain frozen.
danger_areas:
  - >
    A comparator that accepts every acceptance_datetime difference would mask a
    real source disagreement. The helper must require two valid strings and equal
    frozen comparison keys.
  - >
    Recovery completion in tests is not production progress. The real plan and
    cursor state remain untouched and frozen.
decisions:
  - DEC:FF-1-ACCEPTANCE-DATETIME-COMPARES-BY-INSTANT
discoveries:
  - DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT
---

## §0. Held state

The packet is PARKED / HOLD-FOR-SOL. The real recovery plan, cursor and
production failure remain frozen; no recovery action is authorized.

## §1. Comparator boundary

The repair retains the first exact duplicate representation, admits only the
same instant expressed with redundant fractional zeroes, and keeps every
substantive disagreement fail-closed.

## §2. ANGO identity boundary

ANGO is canonical subject CIK `0001275187`. Its accession
`0001628280-26-048138` retains the distinct transmitter prefix; master-index
path identity follows the subject CIK, never the transmitter prefix.

## §3. Production truth

`DSC:FF-1R-ANGO-ACCEPTANCE-DATETIME-CONFLICT` remains the true production
failure witness. Its source-adjudication wait is resolved only for valid
same-instant representational equivalence, not for malformed or substantive
time disagreements.

## §4. Lawful next action

PR #6391 is published and held. Sol reviews its exact candidate head. Do not
merge, dispatch recovery, skip ANGO, advance the cursor, or start FF-2.
