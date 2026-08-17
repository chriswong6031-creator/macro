---
key: GOVREV-MAY-ACTION-AUGUST-KNOWN-AT
claim: >
  Compact Change-Tape row "New obligation observed — HC101319C0006" (IRDM) is
  USAspending funding-only action P00032 with action_date 2026-05-12 and
  first-observed known_at 2026-08-12T23:50:04.442107Z; is_late_discovery is true
  and the dollars are federal_action_obligation 18416666.66, not GAAP revenue.
falsifier: >
  USAspending GET /api/v2/awards/CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-/ plus
  POST /api/v2/transactions/ no longer returning action
  CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0 with action_date 2026-05-12
  and federal_action_obligation 18416666.66, or HEAD
  data/government_revenue/award_action_versions.parquet for that action_id
  showing a first_seen_at on 2026-05-12.
so_what: >
  Do not treat this row as an August catalyst or as Iridium revenue. Report
  source_effective_at (date only) separately from known_at. A later D1 title
  change is allowed; inferring a publication timestamp or filling empty agency
  from DISA is not.
kind: data
verified_at: 2026-08-16
verified_by: >
  USAspending transactions 200 for award id 306425727; collection_receipts.jsonl
  receipt usaspending:usaspending-3be22546a4a9a6b9a46a7469:actions:1d52f66cfa31a196:2a07ba19681a3c9d
  observed_at 2026-08-12T23:50:04.442107Z record_count 33; parquet action version
  event_eligible true; live #gov-data event govws-a6c70850a9cbdce9fa3e7f3b;
  research/defense_intelligence/D0R_GOLDEN_AWARD_CHANGE_LINEAGE.md
scope: [macro]
confidence: verified
---

May funding ingested in August remains a May obligation with an August known-at.
