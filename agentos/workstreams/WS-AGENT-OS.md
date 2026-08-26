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
  - id: MAS65-P0
    title: "MAS-65 — deterministic report-only Agent OS to Linear desired-state compiler"
    status: in_progress
    pr: 6182
    depends_on: [W3]
    next_action: >
      Stay on the sole existing #6182 carrier. Exact frozen Stage-1 candidate is
      db9123181b2d042e1ae53477d066a308284ad73c, reconciled onto Macro main
      571e5c89278feb57648e6b8df1d68e1624b3d0e7 with exactly six P0-owned files.
      Fresh fences 32922618881 are green and semantic CI 32922618935 is running.
      On complete green, persist the exact machine-emitted
      MAS65_LINEAR_PORTFOLIO_PLAN_RECEIPT as one evidence-only seventh file,
      rerun exact-head fences + semantic CI, and return for final Sol P0 review.
      Ordinary later workstream-state movement is expected projector input drift and
      does not by itself invalidate the immutable exact-revision implementation receipt.
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
  - "Mastermind #147 Continuation Delta is constitutional procedure, not a new Agent OS runtime/control plane. Its deterministic implementation is green; its fresh-Sol behavioral release corpus is still unproven and must not be inferred from Slack delivery."
do_not_redo:
  - "Repository reconnaissance: research/EXECUTIVE_OS_PHASE0_CENSUS.md (#5356) censused ~45 components 12h before this session. Do not re-census."
  - "Task leases, heartbeats, LOST reconciliation, CI watchers: all built. executive_runtime.py + executive_supervisor.py (processes); ci_handoff.py + merge-on-green.yml (sessions)."
  - "Do not create a second MAS-65 projector carrier or second Agent OS parser. Continue only on Macro #6182 and reuse scripts.agentos semantics."
  - "Do not restart Mastermind #147 deterministic linter/incident/grounding work absent a concrete receipt-invalidating change; exact head 8209e1f31da15f8effc23a9899a5c5a02d30cab4 passed hosted CI 32911519256."
  - "Do not duplicate/fail over the #147 behavioral-proof operation merely because Slack delivery is idle; MAS-136 records the single delivery carrier and remains blocked on genuine fresh-session evidence."
artifacts:
  - research/MASTERMIND_AGENT_OS_ARCHITECTURE.md
  - research/MASTERMIND_AGENT_OS_STATE_SCHEMA.md
  - research/MASTERMIND_AGENT_HANDOFF_PROTOCOL.md
  - research/MASTERMIND_AGENT_OS_V1_IMPLEMENTATION_PLAN.md
  - research/MASTERMIND_CEO_BRIEF_SPEC.md
next_action: >
  Primary: finish MAS-65 P0 on the sole Macro #6182 carrier. Frozen Stage-1 head
  db9123181b2d042e1ae53477d066a308284ad73c has fresh fences green and semantic
  CI 32922618935 in progress. On green, persist the exact emitted current-revision
  drift receipt as the seventh evidence file, rerun exact-head gates, and return to
  Sol for final P0 acceptance. Do not start MAS-66/P1 until P0 is accepted and the
  dedicated Linear app-actor prerequisite MAS-64 is proven. Independently, MAS-28
  remains calibration-only / report-only. Mastermind #147 / Linear MAS-136 remains
  a separate constitutional replay-prevention release gate: deterministic code is
  PASS, but the required genuine fresh-Sol S1-S8 corpus has no verified ACK/return.
  Agent OS W4 remains separate high-blast-radius report-only hook work and is not
  commissioned by this reconciliation.
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
