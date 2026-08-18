---
key: D11F-PIT-SAFE-AGENCY-FALLBACK
question: >
  When an award-action observation does not itself assert awarding_agency, which
  snapshot agency may the projector copy onto that action event?
answer: >
  Only a same-award snapshot whose known_at is already visible at the action's
  own known_at (source_known_at <= action_known_at), chosen deterministically
  by known_at DESC, source state version DESC, then source identity ASC.
  A populated awarding_agency cell is not direct evidence when
  source_field_presence says the field was absent. Funding agency stays
  excluded. Fallback writes evidence.derivations method
  award_snapshot_agency_fallback.v1 using the existing derivation grammar
  (method, formula_version, classification, ref_id, known_at, basis_refs, detail)
  so the snapshot is not pretended to be the action receipt. Projector
  canonicalize_agency() is unchanged. Event identity stays the action's
  immutable source seed; PIT filtering makes the agency payload stable across
  rebuilds that later observe future snapshots.
rationale: >
  Government Revenue is a point-in-time causal system. Latest-snapshot inherit
  at build cutoff lets a T2 snapshot contaminate a T1 action under the same
  event_id, which D2/D3 would then harden as historical truth. PIT-qualified
  selection is the smallest change that preserves D1.1 canonicalize work
  without rewriting collectors or event IDs.
alternatives:
  - option: Keep latest-snapshot-at-build-cutoff inherit from DEC:D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT
    why_not: >
      A later snapshot would mutate earlier action agency under the same
      immutable event_id. Replay invariance fails.
  - option: Put agency or fallback identity into the event_id hash
    why_not: >
      Unnecessary if PIT filtering makes the payload intrinsically stable.
      Changing IDs would look like new events when eligible evidence arrives.
  - option: Extend government_procurement_event.v2 derivation with new fields
    why_not: >
      method/ref_id/known_at/basis_refs/detail already name the snapshot,
      receipt, clocks, and temporal rule. additionalProperties is false.
  - option: Teach the browser to parse Python and ignore projector provenance
    why_not: Still forbidden. D1.1 canonicalize stays in the projector.
supersedes:
  - DEC:D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT
evidence:
  - "tests/test_government_revenue_award_events.py::test_d11f_past_snapshot_is_legal_agency_fallback"
  - "tests/test_government_revenue_award_events.py::test_d11f_future_snapshot_cannot_fill_earlier_action_agency"
  - "tests/test_government_revenue_award_events.py::test_d11f_replay_keeps_t1_action_identity_and_payload_stable"
  - "tests/test_government_revenue_award_events.py::test_d11f_unasserted_action_agency_is_not_source_truth"
  - "tests/test_government_revenue_award_events.py::test_d11f_same_clock_snapshots_select_deterministically_not_by_frame_order"
  - "tests/test_government_revenue_award_events.py::test_d11_p00032_recovers_award_snapshot_agency_without_changing_clocks_or_amount"
  - "engine/government_revenue/award_events.py _select_pit_snapshot_agency / _snapshot_agency_fallback_derivation"
affects:
  - WS:DEFENSE-PROCUREMENT-V3
  - engine/government_revenue/award_events.py
  - tests/test_government_revenue_award_events.py
confidence: high
reversibility: easy
decided_by: session-d1-1f-pit-safe-agency
decided_at: 2026-08-18
---

Canonicalize remains projector-side. The only reversal is latest-at-cutoff
snapshot inherit. D2 is still unauthorized.
