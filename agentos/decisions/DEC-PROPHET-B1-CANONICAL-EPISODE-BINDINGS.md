---
key: PROPHET-B1-CANONICAL-EPISODE-BINDINGS
question: >
  What exact identity, epoch, expert relationship, structural anchor, event-clock,
  and publication bindings make prophet.candidate_episode/v1 canonical without
  creating a second owner for Stock Identity, Entry Radar, TURN WATCH, rankings,
  plans, lifecycle, Availability, or grading?
answer: >
  R1: security_id is the exact Data OS SEC value and the compatibility field
  company_id carries the exact Data OS ISS value; no Prophet-local identifier is
  minted. R2: identity_epoch is epoch_0 only as an explicitly provisional epoch,
  bound to stock_identity.fingerprint_spec.v1 and its exact spec hash; a future real
  epoch appends IDENTITY_SUPERSEDED and never edits or recycles history. R3: Radar
  relationships retain the exact content-addressed mastermind.entry_event.v1 event_id,
  never Radar's ephemeral runtime episode_id or a reconstructed tuple. R4: only a full
  uncapped TURN WATCH row with an evaluated fired trigger and complete reset-low anchor
  may open a natural B1 episode; candidate, Door, and unanchored Radar observations may
  attach to an active episode or emit a closed suppression, and Door R is not B1 re-arm
  authority. R5: event identity is content-addressed over semantic facts including
  occurred_at and known_at but excluding recorded_at; recorded_at is a factual
  materialization clock and retries retain original bytes. Durable publication writes
  one complete immutable generation, validates it, and atomically replaces HEAD.json;
  an unreferenced generation is noncanonical even when internally valid.
rationale: >
  The V4 freeze requires one episode at the grain security identity epoch x structural
  anchor x lifecycle. Data OS already owns security/issuer identity, Stock Identity
  owns epoch semantics, Radar owns expert events, and TURN WATCH owns structural
  discovery. Reusing their exact addresses preserves point-in-time joins and prevents
  ticker/date, expert-key, or runtime-ledger forks. A canonical event address must be
  stable across harmless retries, so the writer clock cannot participate. Finally,
  sequential replacement of ledgers, projections, and receipts cannot be crash-atomic:
  only an immutable complete generation plus one atomic pointer provides a single
  visibility boundary. These bindings keep B1 a canonicalization plane with no rank,
  gate, plan, Availability, or market-verdict authority.
alternatives:
  - option: Key episodes by ticker/date or by an expert detector identifier
    why_not: >
      Tickers are aliases that change and experts are many-to-one observations of one
      candidate episode; either choice fractures history and creates a rival identity
      or Radar authority.
  - option: Treat epoch_0 as final or implement a Prophet-local epoch detector
    why_not: >
      Finality would lie about the current Stock Identity capability, while a local
      detector would duplicate the canonical owner. Explicit provisional state plus
      immutable supersession preserves truth without blocking B1.
  - option: Let candidate snapshots, Doors, or unanchored Radar open episodes
    why_not: >
      None supplies the complete structural reset-low anchor frozen for this wave.
      Guessing an anchor converts display/measurement observations into lifecycle
      authority and makes replay non-auditable.
  - option: Include recorded_at in event identity and accept last-write-wins retries
    why_not: >
      A rerun would create a second semantic fact merely because the machine clock
      changed. Keep-first content addressing makes retries idempotent and conflicting
      semantic bytes fail closed.
  - option: Atomically replace each ledger, projection, and receipt path in sequence
    why_not: >
      No sequence of independent replacements is crash-atomic. A process or machine
      death between renames exposes split truth; a complete immutable generation plus
      one HEAD replacement does not.
evidence:
  - "Chairman-ratified B1 design: docs/superpowers/plans/2026-08-25-b1-canonical-candidate-episode-design.md sections 3-6"
  - "Pure core and validation: commits af3942dcb7da, c0902bbc0285, 800e34aa1505; tests/test_us_candidate_episode.py"
  - "Canonical intake and exact producer identities: commits 756daff72b97, 642df24bd3a8; tests/test_us_candidate_episode_intake.py and tests/test_us_turn_watch.py"
  - "Immutable-generation writer and independent fix reviews: commits 982422be1e8f, 4535a5237309, cde1c285bed2, 0ecd1d193617; tests/test_us_candidate_episode_reconciler.py"
  - "Workflow, CI, and registry authority fence: tests/test_us_candidate_episode_wiring.py"
affects:
  - WS:PROPHET-US-V4-RECOVERY
  - engine/us_candidate_episode.py
  - engine/us_candidate_episode_intake.py
  - scripts/reconcile_us_candidate_episodes.py
  - data/us_prophet_rank/episode_inputs/turn_watch/
  - data/us_prophet_rank/episodes/
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-25
---

## What would reopen this

A ratified Stock Identity epoch interface reopens only R2's provisional adapter and
requires immutable `IDENTITY_SUPERSEDED` events. A new registered source with a proven
structural anchor may reopen R4's source allowlist. Evidence that an atomic filesystem
rename cannot provide the required single visibility boundary on the production store
reopens the HEAD mechanism. Product urgency, a missing anchor, or a desire to reuse
Radar's runtime episode identifier does not reopen any binding.
