---
key: ANALYTICS-EID-USES-EXISTING-EVENT-PRIMARY-KEY
question: >
  How do new commercial/activation events become idempotent without building a second
  dedupe store, ledger, or event bus?
answer: >
  Every newly implemented registry event carries a required client- or
  authority-derived UUID `eid`, and the collector maps it onto the existing
  analytics_events.id UUID primary key. Retries reuse the same eid; a duplicate primary
  key is ignored (conflict-safe insert) rather than failing the product act; the same
  eid with a different payload is a conflict diagnostic and never overwrites the
  original row. Server-authority events use a deterministic UUID derived from the
  authority event identity plus logical event name. Legacy event wires keep receiving
  server-generated UUIDs until migrated. Malformed or non-UUID ids on new events are
  rejected.
rationale: >
  The existing table already has the needed uniqueness identity in its primary key; a
  parallel dedupe ledger would duplicate state, add a second write path, and still
  require reconciliation against the table. Idempotent delivery is the precondition for
  honest funnel counts (replay on flaky networks must be one row) and for at-least-once
  producers. Using the row id keeps replay semantics queryable with zero schema change.
alternatives:
  - option: A separate dedupe/ledger table keyed by event id
    why_not: >
      Second store for the same identity — rejected by the no-rebuild census; it can
      drift from the table it guards and doubles the failure surface.
  - option: Time-window heuristic dedupe (drop same-looking events within N seconds)
    why_not: >
      Heuristics silently drop real repeat acts and silently keep true duplicates
      outside the window; identity must be explicit, not inferred.
  - option: Exactly-once delivery guarantees in the client queue
    why_not: >
      Exactly-once at the emitter is a fiction over lossy transports; at-least-once with
      idempotent acceptance is the honest contract.
evidence:
  - supabase/migrations/0004_analytics.sql (analytics_events.id UUID primary key already exists)
  - research/commercial_activation/PROJECT_SOL_RETURN_V1_COMMERCIAL_ACTIVATION_20260903.md §6.2-§6.3 (envelope and idempotency contract)
  - research/commercial_activation/CLAUDE_ORCHESTRATOR_HANDOFF_V1_CA1A_EVENT_SPINE_20260903.md §10-§11 (collector mapping and replay behavior)
affects:
  - "WS:COMMERCIAL-ACTIVATION"
  - app/main.py
  - config/growth_events.yml
confidence: high
reversibility: costly
decided_by: chairman
decided_at: 2026-09-04
---

Ratified by direct Chairman grant to session claude/mmx-commercial-activation-03fe73 on
2026-09-04. CA1A implements this for the four early-funnel wires; no other event gains
an eid requirement until its own wave.
