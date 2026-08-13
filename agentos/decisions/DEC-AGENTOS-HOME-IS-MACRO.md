---
key: AGENTOS-HOME-IS-MACRO
question: >
  Which repository should host the Agent OS store, given that strategic state lives in
  Mastermind and duplicate_control_planes is a standing prohibition?
answer: >
  Macro Dashboard, at agentos/, with cross-repo sessions writing through
  scripts/agentos.py against the sibling checkout.
rationale: >
  The fleet law, the five hooks, the Active Build Map, DO_NOT_REBUILD, and the context index
  all already live in Macro, and the Phase 0 census calls Macro's layer "the de-facto Executive
  OS today" (§1.8). Most sessions run here. Splitting the knowledge plane from the tooling that
  generates and validates it would create exactly the cross-repo authority hop the census warns
  about. This does not violate Macro CLAUDE.md's prohibition on a second strategic state,
  control plane, or authority map, because the store contains none of those three: it holds no
  strategy (it cites strategic_state.yml), grants no authority, and dispatches nothing.
alternatives:
  - option: Mastermind, beside control_plane/ and strategic_state.yml
    why_not: >
      control_plane/ is Codex-worker-process shaped and strategic_state.yml explicitly
      disclaims being a control plane. Placing work identity there would associate it with
      runtime authority, which invariant I1 forbids. Most sessions would also be writing
      cross-repo for every record.
  - option: A new dedicated repository
    why_not: >
      A fourth checkout on every machine, and it separates records from the validator, the
      generator, and the ABM/DNR artifacts they join against. The brief asks for consolidation
      over proliferation.
  - option: Per-repo agentos/ directories merged at generation time
    why_not: >
      Breaks Charter P7 (one source of truth per concept) and makes key uniqueness
      unenforceable. Retained only as a fallback if cross-repo write friction proves real.
evidence:
  - "research/EXECUTIVE_OS_PHASE0_CENSUS.md §1.8 — Macro fleet-governance layer is the de-facto Executive OS today"
  - "Mastermind config/strategic_state.yml — 'WHAT THIS FILE IS NOT: not a control plane, a scheduler, or a job queue'"
  - "Mastermind config/strategic_state.yml constraints — duplicate_control_planes: prohibited"
  - "Macro CLAUDE.md §Executive OS — do not create a second strategic state, control plane, or authority map in this repo"
affects: [WS:AGENT-OS]
confidence: medium
reversibility: costly
decided_by: opus-architecture-session
decided_at: 2026-08-12
review_by: 2026-10-12
---

## Grounds

The load-bearing test is invariant I1: Agent OS never decides whether something may run. A
store that cannot gate execution is not a control plane regardless of which repository holds
it, which is what makes the Macro placement compatible with both prohibitions.

## Open risk

Cross-repo write ergonomics are unproven. If Terminal and Mastermind sessions find the
path-resolved CLI frictional in practice, the fallback is per-repo directories merged at
generation — strictly worse for P7, hence a fallback rather than the plan.
