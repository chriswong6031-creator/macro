---
key: AGENT-OS
title: Mastermind Agent OS — organizational knowledge and work-identity plane
objective: >
  Give the organization a durable record of what work exists, why things were decided,
  what was learned, and what is next — without building a third control plane. Done =
  workstreams, decisions, discoveries, and handoffs are written by live sessions, and
  the CEO reads one generated page instead of reconstructing state by hand.
status: active
program: project-active-build-control
p0: EXECUTIVE_OS
repos: [macro]
owner: chairman
class: adjudication
blast_radius: reversible
ambiguity: open
owns_paths:
  - agentos/**
  - scripts/agentos.py
  - research/MASTERMIND_AGENT_OS_*.md
  - research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md
  - research/MASTERMIND_CEO_BRIEF_SPEC.md
waves:
  - id: W0
    title: Architecture + Phase 0 scaffolding (schemas, validator, seeded records)
    status: done
    pr: 5472
  - id: W1
    title: "Phase 1 — adoption: CLAUDE.md/AGENTS.md sections, handoff protocol in use, <=10 backfilled decisions"
    status: done
    pr: 5556
    depends_on: [W0]
  - id: W2
    title: "Phase 2 — status generator + mastermind status CEO brief"
    status: done
    pr: 5472
    depends_on: [W0]
  - id: W2B
    title: "Phase 2b — publish non-ranked readiness for the canonical improvement agenda"
    status: done
    pr: 5649
    depends_on: [W2]
  - id: W3
    title: "Phase 3 — compile-context over the existing context index"
    status: done
    pr: 5561
    depends_on: [W0]
  - id: W4
    title: "Phase 4 — hook auto-capture at ship-loop boundaries (report-only)"
    status: todo
    depends_on: [W1, W2, W2B]
  - id: MAS28-W0
    title: "MAS-28 — canonical PR-linkage validator V1 records freeze"
    status: done
    pr: 6317
    depends_on: [W3]
  - id: MAS28-W0B
    title: "MAS-28 — three-repository canonical PR-template authoring cutover"
    status: done
    pr: 6135
    depends_on: [MAS28-W0]
  - id: MAS28-W0R
    title: "MAS-28 — R028 per-target evidence-identity reconciliation"
    status: done
    depends_on: [MAS28-W0B]
  - id: MAS28-W1
    title: "MAS-28 — pure report-only PR-linkage validator implementation"
    status: done
    pr: 6383
    depends_on: [MAS28-W0R]
    next_action: >
      None for implementation. The repaired report-only W1 head
      b0f12b97a7209d87ef6d3088a6e5d75d362ceb31 passed fences 32800454604 and
      semantic CI 32800454750, then squash-merged as
      35e83b79ac026345a17d5d2d13774bb74e8a994c on 2026-08-25. The earlier #6328
      squash carried the rejected defect shape and is historical evidence, not W1
      acceptance. Enforcement remains REPORT_ONLY. MAS-28 itself remains
      BUILT_NOT_PROVEN until the separate calibration stop condition is satisfied.
decisions:
  - DEC:AGENTOS-CXI-R12-OVERRULED
  - DEC:AGENTOS-CLAIMS-ARE-NOT-LIVE-ACTIVITY
  - DEC:AGENTOS-READINESS-FEEDS-THE-AGENDA
  - DEC:AGENTOS-DECISION-MEMORY-STAYS-SEPARATE
  - DEC:AGENTOS-NO-TASK-STORE
  - DEC:AGENTOS-FILE-PER-RECORD
  - DEC:AGENTOS-HOME-IS-MACRO
  - DEC:AGENTOS-START-NEXT-VS-AGENDA
  - DEC:AGENTOS-NIGHTLY-IS-THE-ONLY-REGENERATOR
  - DEC:MAS28-PR-LINKAGE-VALIDATOR-V1-REPORT-ONLY
  - DEC:MAS28-R028-TARGET-IDENTITY-RECONCILIATION
discoveries:
  - DSC:GOVERNANCE-JSONL-NOT-TRACKED
  - DSC:EXECUTIVE-OS-NO-PROGRAM-ROW
  - DSC:CENSUS-POSTDATES-PHASE1B
  - DSC:MAS28-AUTHORING-GRAMMAR-DRIFT
  - DSC:MAS28-R028-EVIDENCE-IDENTITY-COLLAPSE
landmines:
  - "PROVISIONAL PARENT: project-active-build-control's registry row says it does_not_own 'Durable program truth', which is exactly what this workstream owns. No agent-os row exists (see DSC:EXECUTIVE-OS-NO-PROGRAM-ROW for the same gap). Minting one was reverted deliberately: config/mastermind_programs.yml and its generated docs/MASTERMIND_SYSTEM_MAP.md belong to the semantic-system-mapping workstream, which the commissioning brief marks ALREADY ASSIGNED, and editing the generated map conflicted with main within hours. The row is that owner's to add."
  - "Two execution control planes already exist. Anything that gates or dispatches belongs in Mastermind control_plane/ or the Macro hook layer — see invariant I1."
  - "Census §6 non-goals are binding and postdate Phase 1A/1B — see DSC:CENSUS-POSTDATES-PHASE1B."
do_not_redo:
  - "Repository reconnaissance: research/EXECUTIVE_OS_PHASE0_CENSUS.md (#5356) censused ~45 components 12h before this session. Do not re-census."
  - "Task leases, heartbeats, LOST reconciliation, CI watchers: all built. executive_runtime.py + executive_supervisor.py (processes); ci_handoff.py + merge-on-green.yml (sessions)."
artifacts:
  - research/MASTERMIND_AGENT_OS_ARCHITECTURE.md
  - research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md
  - research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md
  - research/MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md
  - research/MASTERMIND_CEO_BRIEF_SPEC.md
next_action: >
  MAS-28 W1 implementation is merged and accepted as report-only / BUILT_NOT_PROVEN.
  The next MAS-28 operation is calibration only: run the representative frozen corpus
  required by MAS-28, record false positives, false negatives and incomplete observations,
  and return a recommendation to remain report-only, amend rules, or propose a separate
  bounded enforcement review. Do not arm a hard gate from W1. The pre-existing Agent OS
  Phase 4 W4 remains a separate high-blast-radius report-only hook wave and is still todo;
  this records correction does not commission it.
---

## Context

The commissioning brief describes a missing coordination layer. Reconnaissance found the
coordination layer exists twice — the Macro fleet law governing Claude Code sessions, and the
Mastermind Executive OS governing Codex worker processes (Phase 1C-A as of 2026-08-12 03:53).
What is genuinely missing is the knowledge plane: positive decision records, cross-account
discoveries, a handoff schema, work identity between "program" and "PR", and a CEO rollup.

## Scope boundary

This workstream owns the knowledge plane only. It does not touch either execution plane, and
invariant I1 makes that structural rather than promised: nothing here can block or start work.

## Phase 1 acceptance receipts

The current store contains twelve independent real-work handoff records across eight
non-Agent-OS workstreams. None came from the Agent OS scaffolding/compiler sessions or this
Phase 2b closure session, and every implementation commit is merged to `origin/main`:

- `agentos/handoffs/CN-LIMIT-ALPHA-2026-08-14.md`
- `agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-14-e2big.md`
- `agentos/handoffs/CI-MERGE-CONTROL-PLANE-2026-08-14-exclusive-curation.md`
- `agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-13.md`
- `agentos/handoffs/LIVE-ENTRY-RADAR-2026-08-14.md`
- `agentos/handoffs/PROPHET-CONDITIONAL-FUSION-2026-08-14.md`
- `agentos/handoffs/PROPHET-US-AVAILABILITY-2026-08-14.md`
- `agentos/handoffs/STOCK-IDENTITY-2026-08-13.md`
- `agentos/handoffs/STOCK-IDENTITY-2026-08-14.md`
- `agentos/handoffs/STOCK-IDENTITY-W1A1-2026-08-14.md`
- `agentos/handoffs/WS-EVAL-OS-MEASUREMENT-LAW-2026-08-14.md`
- `agentos/handoffs/WS-EVAL-OS-T1-ENGINE-REGISTRY-2026-08-14.md`

Multiple workstreams authored more than one genuine implementation handoff, so record count
and distinct-workstream count intentionally differ. The Phase 1 adoption handoff, the Phase 3
compiler handoff, and the Phase 2b handoff are excluded: Agent OS implementing Agent OS is not
independent adoption. These are adoption receipts, not manufactured closure records. W3
separately closed when PR #5561 merged; W2B closed only after its Macro producer and Mastermind
consumer passed the deployed cross-repo E2E.

## Phase 2b mapping acceptance

The current Improvement Agenda sources do not author Agent OS workstream/wave identities.
Phase 2b therefore accepts zero production mappings as the only honest initial state: every
real item is N/A until its own source explicitly supplies `agentos_ref`. The E2E must still
prove that Mastermind reads and indexes the real producer, that a synthetic exact tuple joins,
and that title or evidence prose never manufactures a mapping. A future source that gains a
legitimate stable identity may opt in at construction time without changing ranking policy.

## Phase 2b deployed acceptance receipt

Mastermind PR #49 merged as `d74d13e76b46d7d90f7f71e735c3479b2bc991e0`; the deployed
Mastermind checkout was a healthy descendant (`9603b408...`). Macro PR #5649 merged as
`f499006047851d61bc312418b3e75cb404360751`; the live host and Mastermind service namespace
both consumed descendant `9ea1bcb6844c9ca724f45e63bb94081938d3dfbf`.

The live producer exposed 78 identity-sorted readiness records with `degraded: []`, no
`unblocked` or `unblocked_scope` key, and W4 blocked only on the then-open W2B. The deployed
consumer joined an exact `AGENT-OS`/`W2B` tuple, left lowercase `w2b` unknown/unmapped, and
preserved agenda rank bytes. The authoritative agenda write persisted 27 existing items in
their original order: zero authored Agent OS references and 27 structured N/A annotations.
Its JSON, Markdown, internal API, and tunneled UI all agreed; the UI rendered 27 readiness
rows and no browser errors. That is the cross-repo evidence required to mark W2B done.
