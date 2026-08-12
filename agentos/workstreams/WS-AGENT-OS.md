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
    status: in_progress
    next_action: Land this PR; then rule on conflicts C1 and C2.
  - id: W1
    title: "Phase 1 — adoption: CLAUDE.md/AGENTS.md sections, handoff protocol in use, <=10 backfilled decisions"
    status: todo
    depends_on: [W0]
  - id: W2
    title: "Phase 2 — status generator + mastermind status CEO brief"
    status: todo
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
  - DEC:AGENTOS-NO-TASK-STORE
  - DEC:AGENTOS-FILE-PER-RECORD
  - DEC:AGENTOS-HOME-IS-MACRO
discoveries:
  - DSC:GOVERNANCE-JSONL-NOT-TRACKED
  - DSC:EXECUTIVE-OS-NO-PROGRAM-ROW
  - DSC:CENSUS-POSTDATES-PHASE1B
landmines:
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
needs_ceo:
  question: >
    Two conflicts between the Agent OS brief and the merged Phase 0 census. C1 — task
    registry: the brief asks for a first-class Task entity; census §5.6 ruled sub-PR
    granularity a non-goal. C2 — session tracking: the brief asks for heartbeats and
    stale-task detection; census §6.3 forbids a session-tracking service.
  options:
    - "Side with the census: waves inside workstreams (C1), advisory claim (C2)"
    - "Override the census: build a real task store and a session registry"
  recommendation: >
    Side with the census on both. Waves supply the dependency graph and next-action the
    brief actually needs at ~4 fields instead of 20; the advisory claim plus git worktree
    list and PR-collision data cover the collision goal. Override C1 only if you want work
    items assigned to workers by someone other than the worker — that is a dispatcher, and
    it belongs in control_plane/.
  by_when: 2026-08-19
next_action: Land Phase 0, then rule on C1 and C2.
created: 2026-08-12
updated: 2026-08-12
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
