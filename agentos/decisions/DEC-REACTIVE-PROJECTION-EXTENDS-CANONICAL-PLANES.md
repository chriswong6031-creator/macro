---
key: REACTIVE-PROJECTION-EXTENDS-CANONICAL-PLANES
question: >
  Should Mastermind become responsive by creating a new realtime application/data/event stack, or
  by extending the existing nightly intelligence, Terminal Quote Plane, Macro serving tier,
  Breathing Platform and route-scoped browser owners through a governed projection contract; and
  how must a regular-session public projection avoid consuming Terminal's shared extended-hours
  demand capacity?
answer: >
  Extend the canonical planes. Keep the generated nightly/close-pass artifact as the durable
  baseline. Obtain current observations only from the existing Terminal Quote Plane. Add one
  owner-native `view=regular` option to the existing loopback `/quotes` endpoint so a bounded
  regular-session projection preserves SnapshotFeed/Polygon/Anchor demand while spending zero
  ExtFeed demand and emitting no extended-hours fields. After that owner contract is deployed and
  proven, expose one debranded bounded Macro projection and let exactly one route-scoped controller
  patch the exact rendered Intelligence Hub roster. Observation and intelligence remain separate.
  R1A is delivered by ordered R1A-T and R1A-M child operations; ordered SSE, materiality-gated
  intelligence deltas and additional surfaces remain separate waves.
rationale: >
  Current archaeology proves the expensive parts already exist: durable evidence/ledgers, a
  production Terminal Quote Plane, a proven dossier read-through projection, static-page
  progressive enhancement, Prophet-Live/close-pass machinery and existing identity/publication
  planes. It also proves ordinary Terminal `/quotes` demand is not neutral for this use: every US
  request reaches the global 30-symbol ExtFeed LRU, while the rendered Intelligence Hub can contain
  up to 58 unique Command/Emerging/diversified-Discovery symbols. Repeated public regular-session
  reads through the full view would evict active Terminal extended-hours demand. The correct repair
  belongs inside the existing Terminal quote owner, not in a second feed or Macro imitation.
  Separate Terminal and Macro modifications preserve one carrier per operation while still forming
  one user capability. The resulting vertical proves source, demand, time, correction, access,
  browser ownership and product behavior before transport is generalized.
alternatives:
  - option: Rewrite Macro as a realtime SPA backed by a new canonical database
    why_not: >
      Replaces rather than extends the current production surface, duplicates durable state and
      publication truth, creates a migration program before one user capability, and reopens the
      rejected SPA/database assumptions.
  - option: Install Kafka, Redis, Temporal or a generic event platform first
    why_not: >
      Infrastructure without a proven producer-consumer job. It adds queue/retry/lifecycle
      semantics beside existing owners and cannot make one page useful or truthful by itself.
  - option: Let every page poll the market-data vendor directly
    why_not: >
      Duplicates credentials, normalization, rights enforcement, connection load and freshness
      vocabulary; exposes vendor behavior to browsers and creates independent quote owners.
  - option: Have Macro call ordinary `/quotes` and discard extended fields
    why_not: >
      Discarding fields does not undo demand. The ordinary route calls `ExtFeed.demand` for each US
      symbol and mutates a global 30-symbol LRU shared by Terminal users. R1A may surface up to 58
      unique names and would repeatedly churn that shared capacity outside RTH.
  - option: Limit R1A to thirty symbols or fetch only once after close
    why_not: >
      Still replaces user-demanded ExtFeed membership with product-page demand, arbitrarily narrows
      the accepted Intelligence Hub roster, and leaves a hidden side effect instead of fixing the
      canonical owner contract.
  - option: Create a second regular-session snapshot service in Macro
    why_not: >
      Duplicates Terminal's SnapshotFeed, Polygon demand, anchor handling, credentials, freshness
      and correction behavior. The smallest lawful change is a closed view on the existing owner.
  - option: Continuously rerun models and intelligence on every quote tick
    why_not: >
      Launders observation into authority, creates cost and instability, and violates the promotion
      law for scores/signals/trades.
  - option: Start with a shared SSE/WebSocket bus
    why_not: >
      Transport is not the first unknown. R1A must first prove source, demand, time, correction,
      rights, browser ownership and product behavior through one bounded snapshot. SSE is R1B only
      if measurement justifies it; WebSocket additionally needs a bidirectional job.
evidence:
  - "research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md — existing cadence and no-rebuild rulings"
  - "agentos/workstreams/WS-BREATHING-PLATFORM.md — active same-session product and owner fences"
  - "agentos/workstreams/WS-MARKET-OS.md — product, identity and user-state boundaries"
  - "app/dossier_quote.py — proven public debranded loopback projection precedent"
  - "templates/live.js — existing partial enhancement and duplicate-DOM-owner risk"
  - "mastermind-terminal@86a75b68/hub/hub.js — ordinary /quotes calls the shared demand pass"
  - "mastermind-terminal@86a75b68/hub/lib/quotes.js — US demand reaches SnapshotFeed, Polygon, AnchorCache and ExtFeed"
  - "mastermind-terminal@86a75b68/hub/lib/extfeed.js — ExtFeed is a global 30-symbol LRU across users"
  - "Macro Intelligence Hub builder/template census — at most 30 Command + 14 Emerging + 14 diversified Discovery presentation slots"
  - "GitHub PR #6707 exact five-record R0 carrier"
affects:
  - "WS:BREATHING-PLATFORM"
  - "WS:MARKET-OS"
  - "research/reactive_projection/MASTERMIND_REACTIVE_PROJECTION_PLATFORM_ARCHITECTURE_FREEZE_2026-08-30.md"
  - "docs/superpowers/specs/2026-08-30-reactive-projection-platform-design.md"
  - "docs/superpowers/plans/2026-08-30-reactive-projection-r1a-intelligence-hub.md"
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-08-30
---

# Decision consequences

## Frozen owner and wave law

- One durable baseline plus one allowlisted projection; not two canonical states.
- Terminal Quote Plane remains the quote owner.
- Existing `/quotes` gains only a closed `view=regular`; no second endpoint/source/store.
- Default/full behavior remains compatible.
- Regular view spends zero ExtFeed demand and emits zero ext fields.
- The exact roster is the ordered unique union of Command, Emerging and diversified Discovery presentation rows, at most 58 names.
- Macro caps requests at 60 and must call `view=regular` explicitly.
- One symbol may have many DOM targets; one controller paints all occurrences atomically.
- Macro API is the public projection boundary.
- R1A changes observation only.
- R1A-T and R1A-M have separate operation keys/carriers/STARTs.
- R1B streaming and all intelligence recomputation are separate.
- Failure resolves to delayed, partial, stale, settled, unavailable or baked; never false-live.

## Capability state

- This decision and R0 records: `BUILT_NOT_PROVEN / PRODUCTION_INERT` while PR #6707 is held.
- Terminal `view=regular`: `NOT_BUILT`.
- Macro Market Pulse: `NOT_BUILT`.
- R1A user capability: `NOT_BUILT`.
- Ordered-delta/SSE R1B: `NOT_BUILT`.

## What this record does not do

This record creates no endpoint, branch execution, worker, queue, scheduler, stream, database,
credential, deployment or production capability. It does not START R1A-T or R1A-M. Each child needs
fresh current Chairman-authorized commission, lawful receiver, ACK, continuation, separate START,
reviewed PR, deployment proof and explicit terminal closeout after R0 is accepted and merged.
