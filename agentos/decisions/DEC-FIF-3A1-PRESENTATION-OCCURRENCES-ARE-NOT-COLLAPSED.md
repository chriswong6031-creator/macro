---
key: FIF-3A1-PRESENTATION-OCCURRENCES-ARE-NOT-COLLAPSED
question: >
  May a presentation tree collapse repeated concept occurrences into one
  concept → row lookup?
answer: >
  No. Preserve each presentation occurrence. Apple's cash concept occurs
  twice in the cash-flow statement: the displayed beginning row binds to
  periodStartLabel and the ending row to periodEndLabel. A reported cell
  whose value came from an iXBRL fact stays direct_or_calculated=direct;
  formula_dependencies may expose the filing calculation network without
  implying Mastermind calculated the value.
rationale: >
  Sol REQUEST_CHANGES on PR #6268. Last-wins concept dict assigned
  periodEndLabel to both cash rows. Overwriting direct with calculated
  because a calc arc exists misstated the source of the displayed number.
alternatives:
  - option: Keep one preferred label per concept
    why_not: Beginning and ending cash are distinct presentation occurrences.
  - option: Mark calculated whenever formula_dependencies exist
    why_not: The displayed value is still the iXBRL fact.
evidence:
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_cash_flow_order_is_filing_native_and_splits_beginning_ending_cash"
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_reported_ixbrl_fact_stays_direct_when_calc_network_exists"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-23
---

Presentation occurrences are not a concept dict. Direct means an iXBRL fact supplied the cell.
