---
key: FIF-3A1-DUPLICATES-REACH-CELL-ADJUDICATION
question: >
  Who decides whether duplicate iXBRL occurrences of a displayed fact agree
  or conflict?
answer: >
  Collect every occurrence sharing the displayed fact's proper duplicate
  identity (concept/context/unit). _cell_from_facts remains the authority
  for agreement versus ambiguity. Do not pre-filter to agreeing values.
rationale: >
  Sol REQUEST_CHANGES on PR #6268. _agreeing_occurrences dropped conflicts
  before cell adjudication, so a hostile duplicate never became ambiguous.
alternatives:
  - option: Keep agreeing-only pre-filter and unit-test _cell_from_facts
    why_not: Reconstruction would still hide conflicts.
evidence:
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_conflicting_duplicate_total_net_sales_is_ambiguous_end_to_end"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-23
---

Duplicate identity is concept/context/unit. Ambiguity is decided at the cell.
