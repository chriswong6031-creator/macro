---
key: AAPL-UNLINKED-VINTAGES-REQUIRE-TYPED-REVISION-LINEAGE
claim: >
  After both AAPL golden filings are visible, a comparative instant such
  as us-gaap:Assets at 2025-09-27 exists independently in 10-K
  0000320193-25-000079 and 10-Q 0000320193-26-000020 as separate
  duplicate roots with no revision_of, so the canonical query kernel
  returns NOT_EVALUABLE with reason "unlinked source vintages require
  an explicit typed revision lineage" rather than selecting the later
  filing by timestamp.
falsifier: >
  Query total_assets instant 2025-09-27 against the A3 golden ledger
  with source_snapshot_at and recorded_at after both fixture clocks
  and receive VALUE, or find revision_of set on either golden
  occurrence.
so_what: >
  Do not invent revision_of or call the 10-Q a revision of the 10-K
  merely because it repeats a comparative value. A later real-revision
  or reprint wave must add explicit typed lineage before comparative
  overlap can resolve.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  tests/test_fundamental_forensics_ixbrl_raw_ledger.py::test_unlinked_vintages_are_not_evaluable
scope:
  - macro
  - engine/fundamental_forensics/ixbrl_raw_ledger.py
  - engine/fundamental_forensics/query.py
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

This is required A3 behavior and must not be "fixed" by timestamp fusion.
