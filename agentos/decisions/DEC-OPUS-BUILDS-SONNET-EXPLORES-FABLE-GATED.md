---
key: OPUS-BUILDS-SONNET-EXPLORES-FABLE-GATED
question: >
  Which model tiers may build shipping code, do user-facing design, run mechanical
  fan-out, and be spawned as frontier judgment — and how is the routing enforced?
answer: >
  Opus builds, reviews, and designs (the `builder`/`reviewer`/`designer` agent types are
  Opus-pinned). Sonnet is narrowed to mechanical NON-code fan-out — census, exploration,
  lookup sweeps — and Haiku to trivial extraction. Fable runs the main loop (planning,
  adjudication, merges, final synthesis) and may be spawned ONLY via the triple
  `orchestrator` agent type + explicit `model: 'fable'` + a `FABLE-WHY: <category>:
  <specific reason>` line that passes the draft-and-review test. Every Agent/Task spawn
  and every Workflow `agent()` call carries explicit routing; a PreToolUse hook denies
  the rest.
rationale: >
  Two operator orders set the tiers: 2026-07-18 "design sessions degraded" — user-facing
  design is judgment work and must never route to sonnet builders — and 2026-07-21
  "sonnet design and building suck too much for our purposes" — code implementation moved
  from Sonnet to Opus, with Sonnet retained only for mechanical non-code sweeps. The
  enforcement hook exists because spawns silently INHERIT the session model: under a
  frontier main loop, an unrouted ×N fan-out burns frontier tokens on mechanical work.
  The Fable gate's test is draft-and-review: a Fable spawn is legitimate only where
  Sonnet-draft + Opus-review would NOT recover the quality (open-ended judgment steering
  major downstream work, long-horizon orchestration with irreversible mid-task decisions,
  taste-as-deliverable creative work). Topic importance alone does not qualify.
alternatives:
  - option: Sonnet builds and designs, Opus reviews (the pre-2026-07-21 arrangement)
    why_not: >
      Operator-observed degraded output on both lanes — the orders' own words. Review did
      not recover the quality; the tier of the AUTHOR was the lever.
  - option: Route everything to the frontier tier
    why_not: >
      Burns frontier context on mechanical work; frontier burn is context × turns
      (DEC:FRONTIER-BURN-IS-CONTEXT-TIMES-TURNS), and bulk fan-outs are the worst case.
  - option: Ad-hoc per-session routing with no hook
    why_not: >
      Inheritance is the silent default, so the failure mode is invisible until the bill.
      The guard denies unrouted spawns precisely because convention did not hold.
evidence:
  - "Macro CLAUDE.md §Model routing (STANDING — token economy) — both operator orders quoted with dates"
  - ".claude/hooks/model_routing_guard.py, wired in .claude/settings.json (PreToolUse on Agent/Task/Workflow)"
  - "Agent-type frontmatter: builder/reviewer/designer Opus-pinned; orchestrator opus-floor with the fable gate"
  - "scripts/metabolism_build.py — autonomous build loop Opus-pinned 2026-07-21 (R-V4-2 amended)"
affects: ["every Agent/Task/Workflow spawn in Macro sessions", ".claude/hooks/model_routing_guard.py"]
confidence: high
reversibility: easy
decided_by: chairman
decided_at: 2026-07-21
---

## Grounds

Backfilled 2026-08-13 (Agent OS Phase 1) from Macro `CLAUDE.md` §Model routing, which
quotes both operator orders. `decided_at` is the build-lane order (2026-07-21); the design
lane was ruled 2026-07-18 and is folded in rather than minted separately, since the two
orders define one routing table.

## What would reopen this

A model-generation change that moves the quality frontier (e.g. a Sonnet-class tier that
passes the operator's design/build bar), or measured evidence that Opus review reliably
recovers Sonnet-draft quality on a lane. Reversal is an operator call, not a session call
— the current table exists because sessions' own tier judgments drifted cheap.
