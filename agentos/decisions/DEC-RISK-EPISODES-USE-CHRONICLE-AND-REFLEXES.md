---
key: RISK-EPISODES-USE-CHRONICLE-AND-REFLEXES
question: >
  Where does Grey Deer's durable lifecycle history live — a new generic risk
  lifecycle database, or the existing Chronicle / Reflex Registry / QLedger
  planes?
answer: >
  The existing planes. Settled hazard-episode state transitions extend
  Chronicle. Bounded action firings extend the Reflex Registry and are graded
  through QLedger/Evaluation OS. The Signal Episode Atlas remains per-name
  technical-event memory and is not repurposed into a market-wide risk
  lifecycle store. No new generic risk lifecycle database is created, and the
  intraday/live lane never advances any durable ledger.
rationale: >
  Chronicle, the Reflex Registry, and QLedger already carry exactly the three
  record species Grey Deer needs (settled transitions, trigger→action firings,
  graded outcomes), each with existing correction law, nightly advancement
  discipline, and consumers. A new store would duplicate all three, split the
  audit trail for the same episode across planes, and recreate the
  stale-ledger failure the incident exposed (a fresh-looking store nobody
  heartbeats). Extending proven planes also keeps the nightly as the sole
  advancer of forward history — a standing house law.
alternatives:
  - option: New dedicated risk-episode database with its own lifecycle tables
    why_not: >
      Second event store, banned by command packet law 7; splits episode
      history from the planes that already grade and correct it; adds a new
      liveness surface that can silently stall.
  - option: Repurpose the Signal Episode Atlas for market-wide risk episodes
    why_not: >
      The Atlas is per-name event memory; overloading it changes its grain and
      semantics for existing consumers and buries market-level lifecycle in a
      name-keyed store.
  - option: Keep episode state only inside the envelope JSON history
    why_not: >
      The envelope is a derived projection with no forward ledger
      (DEC:RISK-ENVELOPE-IS-CANONICAL-DERIVED-PROJECTION); serving artifacts
      are re-derivable and cannot be the durable audit trail.
evidence:
  - "research/grey_deer/GREY_DEER_RISK_INTELLIGENCE_ARCHITECTURE_FREEZE_2026-08-19.md §4 durable-history ruling"
  - "research/grey_deer/GREY_DEER_FABLE_EXECUTION_COMMAND_PACKET_2026-08-19.md §5 law 7, §8.4 live-vs-settled lane law"
affects:
  - "WS:GREY-DEER-RISK-INTELLIGENCE"
  - "engine/chronicle/"
  - "config/reflexes.yml"
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-19
---

## Grounds

Sol architecture freeze 2026-08-19 (§4). Existing planes were verified as the
owners of settled history, firings, and grading during the freeze's
current-state audit (command packet §3.1).

## What would reopen this

Only a Sol architecture act, triggered by concrete GD-2+ evidence that
Chronicle/Reflex/QLedger structurally cannot carry an episode semantic
(not merely that extending them is more work than a green-field table). Such a
finding is a named program stop condition, escalated — never resolved by
quietly minting a new store.
