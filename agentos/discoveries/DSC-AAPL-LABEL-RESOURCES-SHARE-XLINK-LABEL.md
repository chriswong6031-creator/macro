---
key: AAPL-LABEL-RESOURCES-SHARE-XLINK-LABEL
claim: >
  Apple's 2025 10-K label linkbase reuses one xlink:label key for multiple
  label resources (standard, terse, documentation) on the same concept, so
  a dict keyed only by xlink:label keeps the last role and drops Net sales.
falsifier: >
  python3 parse of tests/fixtures/fundamental_forensics/aapl_10k_2025/members/aapl-20250927_lab.xml
  showing every label resource has a unique xlink:label, or Revenue terseLabel
  surviving a last-write-wins dict keyed only by xlink:label.
so_what: >
  Label parsers must store resources as a list per xlink:label and attach
  every role when walking labelArc. Never assume one resource per key.
kind: landmine
verified_at: 2026-08-22
verified_by: >
  engine/fundamental_forensics/statement_graph.py:238 parse_labels;
  python3 -c "from engine.fundamental_forensics.statement_graph import parse_labels, LABEL_TERSE; from pathlib import Path; labels=parse_labels(Path('tests/fixtures/fundamental_forensics/aapl_10k_2025/members/aapl-20250927_lab.xml').read_bytes()); print(labels[('us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax', LABEL_TERSE)])"

scope:
  - macro
  - engine/fundamental_forensics/statement_graph.py
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

Apple FY2025 10-K `aapl-20250927_lab.xml` uses one `labelLink` (671 locs,
1452 labels, 671 arcs). Several concepts, including
`us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax`, attach
standard, terse, and documentation labels to the same `xlink:label`.
A mapping `resources[key] = (role, text)` silently drops terse "Net sales".
