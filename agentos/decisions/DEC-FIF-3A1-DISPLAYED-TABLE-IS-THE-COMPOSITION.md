---
key: FIF-3A1-DISPLAYED-TABLE-IS-THE-COMPOSITION
question: >
  For the golden AAPL 2025 10-K, is raw presentation order sufficient
  as-reported composition?
answer: >
  No. Reconstruct the three captured primary HTML tables. Products/Services
  sit under Net sales with dimensioned cells. Hypercube/table/axis metadata
  is not a displayed row. Columns come from the printed header dates bound
  to filing contexts, not support ≥ 5 plus newest-N. This is not permission
  to build a generic segment/dimension engine.
rationale: >
  Apple's Product/Service hypercube appears before line items in the
  presentation linkbase, while aapl-20250927.htm nests Products/Services
  beneath Net sales. Raw traversal dropped dimensioned values and invented
  column selection. Sol required the minimum source-backed composition that
  matches the three captured tables.
alternatives:
  - option: Keep presentation order and leave Products/Services as abstracts
    why_not: That is not the filing the reader sees.
  - option: Build a generic hypercube/dimension engine
    why_not: Sol explicitly withheld that permission; only AAPL 3A1 tables.
evidence:
  - "research/financial_intelligence_fabric/FIF_3A1_AAPL_GOLDEN_REVIEW.md"
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_products_and_services_are_displayed_under_net_sales_with_dimensions"
  - "parse_displayed_primary_table in engine/fundamental_forensics/statement_graph.py"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

AAPL FIF-3A1 display trees follow the captured HTML tables.
