---
key: MARKET-MEMORY-W2C
title: Market Memory W2C prospective activation recovery
objective: >
  Keep the first honest W2C prospective opportunity on a live, exact activation
  chain. Done for M0A when the earliest causal production failure is repaired,
  merged, and verified without weakening PIT or authority and without backfilling
  a missed row. Later waves start only after that live proof.
status: awaiting_ci
program: market-memory
p0: US_PROPHET_ENTRY_TIMING
repos: [macro]
owner: coo-fable
class: build
blast_radius: reversible
ambiguity: scoped
owns_paths:
  - lib/massive_ticker.py
  - engine/neuralweb/market_memory_technical_observation.py
waves:
  - id: M0A
    title: First-cause production repair for W2C prospective activation
    status: awaiting_ci
    next_action: >
      Merge the nested __case_v1 technical-intake PR, then verify production
      technicals against the live listing. Do not start M0B in the same session.
  - id: M0B
    title: Next proven causal blocker only (not started)
    status: todo
    depends_on: [M0A]
    next_action: >
      Start only after M0A is live. If context freshness still blocks owner replay
      before 2026-08-18 04:30 UTC, that is the next PR.
next_action: >
  Own the M0A PR through merge and production technicals verification, then stop.
  Do not repair context freshness, API restart, or mixed-root residue in M0A.
do_not_redo:
  - Do not reject leftover mixed-case root names in the same PR as admitting canonical nested __case_v1 paths.
  - Do not backfill a missed W2C row or fabricate the first opportunity.
  - Do not weaken PIT, authority, or freshness validators to make the timer look armed.
  - Do not edit app/deploy/update.sh or deploy tests owned by PR #5804.
landmines:
  - Nested-path admission must round-trip artifact_relative_path. Any slash, mixed-case nested name, or hex that decodes to an uppercase ticker reopens traversal and identity-fold bugs.
  - Experience timer enabled-but-inactive is not proof the owner is healthy.
  - Context freshness 36h wall-clock vs weekend-valid Friday regime is a later blocker and currently masks technicals in replay order.
---

M0A closeout: `agentos/handoffs/MARKET_MEMORY_M0A_CLOSEOUT_2026-08-16.md`.
