---
key: AAPL-CF-CASH-CONCEPT-OCCURS-TWICE
claim: >
  Apple's FY2025 10-K cash-flow presentation repeats
  us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents
  twice: preferredLabel periodStartLabel (beginning balances) then
  periodEndLabel (ending balances).
falsifier: >
  parse_presentation_tree on aapl-20250927_pre.xml for
  http://www.apple.com/role/CONSOLIDATEDSTATEMENTSOFCASHFLOWS yields fewer
  than two occurrences of that concept, or both share the same preferred
  label role.
so_what: >
  Do not collapse presentation rows into one concept → row. Bind the
  displayed beginning cash row to periodStartLabel and the ending row to
  periodEndLabel.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  engine/fundamental_forensics/statement_graph.py:687
  tests/test_fundamental_forensics_financial_statement_service.py::test_cash_flow_order_is_filing_native_and_splits_beginning_ending_cash
scope:
  - macro
  - engine/fundamental_forensics/statement_graph.py
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

The cash concept is two presentation occurrences, not one fact looked up twice.
