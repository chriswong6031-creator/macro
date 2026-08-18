---
key: D11-AGENCY-CANONICALIZE-AND-SNAPSHOT-INHERIT
question: >
  Where should D1.1 recover a truthful human awarding-agency label when the
  published event has either a Python-repr string or a null agency object
  despite USAspending source evidence on the same award?
answer: >
  Canonicalize at the award-event projector. Parse awarding_agency /
  awarding_sub_agency with ast.literal_eval or json.loads, whitelist the
  government_procurement_event.v2 agency fields, and map USAspending
  toptier/subtier/office names. When an action observation omitted
  awarding_agency, copy the latest award-snapshot agency for that
  award_identity. Do not merge funding_agency. Browser agencyName() only
  presents department_name → subagency_name → office_name → name.
rationale: >
  The v2 contract already types agency as an object. A Python-repr string in
  name is an upstream defect. Collector _text(dict) is the first stringify,
  but rewriting those text columns would retouch event_state_sha256 and
  fabricate source revisions. Projector-side parse plus snapshot inherit
  heals the public event without mutating receipts or parquet hashes.
  Frontend Python parsing is forbidden by the D1.1 handoff.
alternatives:
  - option: Flatten nested agency in collectors/usaspending_awards.py _assign_event_text
    why_not: >
      Changing the persisted awarding_agency string changes event_state_sha256
      and would emit fabricated source revisions on the next collect.
  - option: Parse Python literals in government_revenue.html.j2 agencyName()
    why_not: The D1.1 contract forbids a general Python parser in the browser.
  - option: Infer DoD from ticker, NAICS, PSC, or description keywords
    why_not: Explicitly forbidden. Invention is not recovery.
  - option: Leave action-rail agency empty and only heal the 22 snapshot rows
    why_not: >
      P00032 is the golden lineage and lives on the action rail; empty agency
      there is the original D0R projection gap.
evidence:
  - "data/government_revenue/workspace.json bundle grw2-dd9d7af893a7f3c773909351: 478 empty agency objects, 22 Python-repr names"
  - "award_action_versions.parquet P00032 awarding_agency <NA>; source_field_presence omits awarding_agency"
  - "award_event_snapshots.parquet HC101319C0006 awarding_agency Python literal with toptier Department of Defense / subtier DISA"
  - "engine/government_revenue/award_events.py canonicalize_agency / _snapshot_agency_index"
  - "tests/test_government_revenue_award_events.py D1.1 cases A/B/C"
affects:
  - WS:DEFENSE-PROCUREMENT-V3
  - engine/government_revenue/award_events.py
  - engine/government_revenue/workspace.py
  - templates/government_revenue.html.j2
confidence: high
reversibility: easy
decided_by: session-d1-1-agency-semantic
decided_at: 2026-08-17
---

Awarding and funding remain distinct facts. Snapshot inherit is award-key
source evidence, not ticker inference.
