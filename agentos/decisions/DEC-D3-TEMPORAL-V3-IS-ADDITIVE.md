---
key: D3-TEMPORAL-V3-IS-ADDITIVE
question: >
  Sol's D3 directive names "temporal event v3". Does that require re-minting the
  event contract (government_procurement_event.v2 -> v3), or freezing v3 temporal
  semantics additively on top of the existing contract?
answer: >
  Additive. The event contract string stays government_procurement_event.v2; the
  procurement workspace gains a temporal_contract:
  "government_procurement_temporal.v3" marker plus typed per-rail failure_state
  fields (null | source_unavailable | projection_missing) and a new
  freshness.budget rail block. No event field is added, renamed, or retimed, and
  no source_published_at clock is ever minted — the UI carries the source
  publication clock as a NAMED NULL.
rationale: >
  The D3 archaeology (2026-08-20, main 70b695e882e0) proved the v2 event corpus
  already carries everything the Change Tape needs for temporal truth: distinct
  effective_at/known_at/first_seen_at/last_seen_at, typed award_change.event_type,
  receipt-bound changed_fields[].before/.after, is_late_discovery, and
  prior_source_identity. The misreads were render-side (single winning clock on
  the tape row, unreachable PROJECTION_MISSING, frontend-computed failure
  states). A contract bump would ripple through every validator and consumer for
  zero informational gain.
alternatives: >
  (1) Bump to government_procurement_event.v3 — rejected: churn without new
  information; breaks HAS_WORKSPACE-style consumers for no user-visible truth
  gain. (2) Mint source_published_at — rejected outright: USAspending exposes no
  per-revision publication time; substituting any other clock would assert a
  falsehood (frozen spec §1).
evidence: >
  research/defense_intelligence/DEFENSE_D3_TEMPORAL_CONTRACT_AND_CHANGE_TAPE_SPEC.md
  (frozen spec); contracts/government_revenue/government_procurement_workspace.v2
  .schema.json (additive-only diff, nothing added to required, pre-D3 artifacts
  still validate — pinned by test_committed_canonical_generation_still_satisfies
  _the_shipped_contract); tests/test_government_revenue_temporal_contract.py
  (families T1-T8, 20 tests).
affects: ["engine/government_revenue/workspace.py", "engine/government_revenue/metrics.py", "contracts/government_revenue/government_procurement_workspace.v2.schema.json", "templates/government_revenue.html.j2"]
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-20
---

A later wave may still mint a real event v3; this record only forbids treating
"temporal v3" as requiring one today.
