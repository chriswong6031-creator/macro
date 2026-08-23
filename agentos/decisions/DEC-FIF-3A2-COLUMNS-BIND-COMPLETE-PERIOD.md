---
key: FIF-3A2-COLUMNS-BIND-COMPLETE-PERIOD
question: >
  How must FIF bind 10-Q duration columns that share an end date?
answer: >
  Column identity is the complete filing period (kind + start + end) taken
  from same-column iXBRL contexts of the preferred kind. End-date first-match
  and newest-N are forbidden. Instant facts that sit in duration columns do
  not define the column. Repeated ISO labels are allowed; they are not the
  disambiguator. No Three Months Ended label heuristic.
rationale: >
  AAPL FY2026 Q3 operations prints four duration columns whose two end dates
  each serve a current-quarter family and a year-to-date family. statement_cell.v1
  already has start+end. Collapsing those columns would mix 3M and 9M facts.
alternatives:
  - option: Keep the A1 expected=3 duration / expected=2 instant hardwire
    why_not: The Q3 income table has four duration columns and cash flow has two.
  - option: STOP as a contract gap
    why_not: The column object can already distinguish the periods without new fields.
evidence:
  - "Q3 income columns 2026-03-29→2026-06-27 vs 2025-09-28→2026-06-27"
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_q3_reconstruct_preserves_quarterly_duration_families"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - contracts/statement_cell.v1.md
  - engine/fundamental_forensics/statement_graph.py
confidence: high
reversibility: costly
decided_by: coo-fable
decided_at: 2026-08-23
---

Quarterly columns bind by complete period, not by end date alone.
