---
key: AGENTOS-NO-TASK-STORE
question: >
  Should Agent OS V1 carry a first-class Task entity with per-task records, as the
  commissioning brief requests in PART II and PART XVI?
answer: >
  No. Work decomposes into waves held inline in the workstream record. PRs remain the
  execution object; active_builds.v1 remains the PR-granular registry.
rationale: >
  Census §5.6 already adjudicated that sub-PR granularity is unnecessary for MVP and named
  a task queue an explicit non-goal. A 20-field-per-task ritual fails the brief's own
  principle 3 (minimal friction) at 50 workers, and PR + workstream already carry 18 of the
  20 requested fields between them. Waves supply the only two a PR genuinely lacks —
  depends_on and next_action — at roughly 4 fields, and they match the W0/W1/W2 decomposition
  every masterplan in this repo already uses, so the idiom is settled rather than invented.
alternatives:
  - option: Full Task registry as specified in the brief PART II
    why_not: >
      Duplicates active_builds.v1 at finer granularity; produces thousands of rows that rot
      within a week; contradicts merged census §5.6.
  - option: Tasks as GitHub Issues
    why_not: >
      Puts the work registry behind the 5,000/hr shared REST core bucket that gh_quota_guard.py
      exists to protect, and that ship_loop_guard.py fails closed against. Read-locality is
      the scaling property of the whole design.
evidence:
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §5.6 — merged #5356, 2026-08-11 21:01"
  - "scripts/build_active_build_map.py docstring — active_builds.v1 is PR-granular and advisory"
  - "Macro CLAUDE.md §GitHub quota — REST core is one shared 5,000/hr bucket; ship_loop_guard fails closed"
affects: [WS:AGENT-OS]
confidence: high
reversibility: easy
decided_by: opus-architecture-session
decided_at: 2026-08-12
review_by: 2026-09-12
---

## Grounds

The brief and the merged census disagree here, and the census is the more recent adjudicated
word (21:01 on 2026-08-11, postdating Executive OS Phases 1A and 1B). Confidence is `medium`
rather than `high` because this is a genuine conflict with the commissioning brief, and the
Chairman may rule the other way.

## RATIFIED 2026-08-12 — Chairman ruling C1

"APPROVE CURRENT DESIGN. No first-class Task registry in Agent OS V1. Use workstream waves +
PRs." Confidence raised from `medium` to `high`: this was recorded as a genuine conflict with
the commissioning brief, and the conflict is now resolved rather than outstanding.

## Where the task store DOES go, when it comes

The ruling settles the home as well as the timing: **a true pre-PR Task/Job store will be
introduced later in the Executive OS dispatcher, not in Agent OS, when autonomous assignment
is implemented.** That is the same boundary invariant I1 draws — assigning work to a worker is
execution authority, and execution authority lives in `control_plane/`. So this is not "no task
store ever"; it is "not here, and not until there is a dispatcher to own it."

A future session finding this record should NOT propose a task registry under `agentos/`. It
should ask whether the Executive OS dispatcher exists yet.
