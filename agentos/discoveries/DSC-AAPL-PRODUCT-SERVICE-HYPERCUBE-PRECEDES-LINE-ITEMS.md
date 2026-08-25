---
key: AAPL-PRODUCT-SERVICE-HYPERCUBE-PRECEDES-LINE-ITEMS
claim: >
  Apple's FY2025 10-K presentation network places the Product/Service
  hypercube (Statement [Table], Axis, Domain, members) before Statement
  [Line Items], while aapl-20250927.htm displays Products and Services
  as dimensioned rows under Net sales.
falsifier: >
  A read of tests/fixtures/fundamental_forensics/aapl_10k_2025/members/aapl-20250927_pre.xml
  showing ProductMember after Net sales line items, or an HTML table
  parse of aapl-20250927.htm CONSOLIDATED STATEMENTS OF OPERATIONS whose
  first numeric row is undimensioned Total net sales with no Products row.
so_what: >
  Do not treat raw presentation order as AAPL as-reported composition.
  Reconstruct the captured HTML tables. Do not build a generic segment
  engine from this Apple-specific layout.
kind: landmine
verified_at: 2026-08-23
verified_by: >
  parse_displayed_primary_table on aapl-20250927.htm; reconstruct_primary_statements
  income_statement labels[:4] == Net sales: / Products / Services / Total net sales
scope:
  - macro
  - engine/fundamental_forensics/statement_graph.py
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

Presentation order and displayed HTML order disagree on Apple's Product/Service
breakout. FIF-3A1 follows the HTML tables for the golden vertical only.
