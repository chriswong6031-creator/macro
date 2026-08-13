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
    status: in_progress
    pr: 5556
    depends_on: [W0]
    next_action: >
      Adoption instructions + backfill are in PR. Gate status: DEC>=10 met (19);
      DSC>=5 met on the corpus-total reading the Phase 1 commissioning handoff
      specifies (5 total; 2 postdate Phase 0); UNMET: >=3 handoffs written by
      sessions other than the scaffolding sessions, from real work — accrues as
      live workstream sessions stop; do not manufacture records to close it.
  - id: W2
    title: "Phase 2 — status generator + mastermind status CEO brief"
    status: done
    pr: 5472
    depends_on: [W0]
  - id: W3
    title: "Phase 3 — compile-context over the existing context index"
    status: todo
    depends_on: [W0]
  - id: W4
    title: "Phase 4 — hook auto-capture at ship-loop boundaries (report-only)"
    status: todo
    depends_on: [W1, W2]
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
discoveries:
  - DSC:GOVERNANCE-JSONL-NOT-TRACKED
  - DSC:EXECUTIVE-OS-NO-PROGRAM-ROW
  - DSC:CENSUS-POSTDATES-PHASE1B
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
  Close W1's remaining gate: >=3 genuine handoffs from sessions other than the
  scaffolding sessions, accrued from real work as adopted instructions take effect.
  Then Phase 3 (compile-context), which gains the agenda-integration wave that
  retires the UNBLOCKED list. All five conflicts remain ruled: C1 no task store,
  C2 claims advisory-only, C3 readiness feeds the agenda, C4 stores stay separate,
  C5 CXI-R12 overruled.
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
