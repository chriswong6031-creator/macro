---
key: AAPL-CF-BEGINNING-CASH-IS-INSTANT-IN-DURATION-COLUMNS
claim: >
  Apple's FY2025 cash-flow table prints three year-end duration columns,
  but the first numeric row (beginning cash) uses instant contexts, so
  binding column periods from that first row fails to find duration
  start dates.
falsifier: >
  reconstruct_statement(cash_flow) succeeding while _columns_from_display
  uses only the first numeric row's contexts, or beginning-cash facts in
  aapl-20250927.htm carrying duration contexts c-1/c-18/c-19.
so_what: >
  Bind duration columns from any duration context in the same displayed
  table whose end_date matches the printed header date. Do not assume
  the first numeric row is a duration fact.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  engine/fundamental_forensics/statement_graph.py:590
  reconstruct_statement(cash_flow) binds duration columns from table duration
  contexts, not beginning-cash instants
scope:
  - macro
  - engine/fundamental_forensics/statement_graph.py
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

Cash-flow column periods must be bound from duration facts in the table,
not from beginning-balance instants that occupy the first numeric row.
