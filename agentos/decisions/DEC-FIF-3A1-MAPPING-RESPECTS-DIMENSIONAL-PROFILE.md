---
key: FIF-3A1-MAPPING-RESPECTS-DIMENSIONAL-PROFILE
question: >
  May a dimensioned ProductMember or ServiceMember statement row be enriched
  as normalized revenue or cost_of_revenue under the core catalog?
answer: >
  No. The core registry is consolidated_only. The row may retain its exact
  as-reported value, concept, and dimensions, but standardized_metric_id
  stays null / unmapped. Undimensioned Total net sales maps to revenue;
  undimensioned Total cost of sales maps to cost_of_revenue. Do not broaden
  the registry.
rationale: >
  Sol REQUEST_CHANGES on PR #6268. Concept-alias matching without the metric
  contract's dimensional_profile treated segment rows as consolidated totals.
alternatives:
  - option: Map any matching concept alias regardless of dimensions
    why_not: That silently promotes Product/Service members to revenue.
  - option: Broaden the registry to allow member selection
    why_not: Sol forbade broadening the registry for this slice.
evidence:
  - "config/fundamental_forensics/metrics/v1/metric_catalog.yaml dimensional_profile.mode consolidated_only"
  - "tests/test_fundamental_forensics_financial_statement_service.py::test_dimensional_product_service_rows_are_not_enriched_as_consolidated_metrics"
affects:
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
  - engine/fundamental_forensics/statement_graph.py
confidence: high
reversibility: costly
decided_by: ceo-sol
decided_at: 2026-08-23
---

Governed mapping follows the existing metric contract. Dimensioned members stay as-reported.
