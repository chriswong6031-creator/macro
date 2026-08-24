---
key: AAPL-Q3-DURATION-FAMILIES-SHARE-END-DATE
claim: >
  Apple's FY2026 Q3 10-Q operations table displays four duration columns
  whose two end dates each serve both a three-month family and a
  nine-month family (2026-06-27 and 2025-06-28). Cash flow displays only
  the nine-month pair.
falsifier: >
  parse_displayed_primary_table on aapl-20260627.htm for CONDENSED
  CONSOLIDATED STATEMENTS OF OPERATIONS yields fewer than four ISO header
  dates, or same-column duration contexts for the two 2026-06-27 columns
  share one start_date.
so_what: >
  Do not bind duration columns by end date first-match. Bind each displayed
  column by complete period from same-column facts.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  tests/fixtures/fundamental_forensics/aapl_10q_2026q3/members/aapl-20260627.htm
  engine/fundamental_forensics/statement_graph.py _columns_from_display
scope:
  - macro
  - engine/fundamental_forensics/statement_graph.py
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

Q3 operations is 3M+9M, not a 10-K three-year duration shape.
