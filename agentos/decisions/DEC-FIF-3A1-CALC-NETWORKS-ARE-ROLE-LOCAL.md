---
key: FIF-3A1-CALC-NETWORKS-ARE-ROLE-LOCAL
question: >
  May a primary statement consume calculation relationships from any
  network that shares a parent concept?
answer: >
  No. Preserve xlink:role when parsing calculation networks. A primary
  statement may consume only the calculation relationships belonging to
  its exact statement role. Same parent in two roles with different
  children is not merged.
rationale: >
  Sol REQUEST_CHANGES on PR #6268. Collapsing calc arcs across roles
  contaminates GrossProfit (and similar parents) with children that
  belong to another statement.
alternatives:
  - option: Merge all calculationLink networks by parent concept
    why_not: Cross-role children become formula dependencies of the wrong statement.
evidence:
  - "engine/fundamental_forensics/statement_graph.py parse_calculations returns dict[role_uri, dict[parent, children]]"
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_calculation_relationships_are_role_local"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
confidence: high
reversibility: easy
decided_by: ceo-sol
decided_at: 2026-08-23
---

Calculation relationships are role-local. Missing xlink:role is an error.
