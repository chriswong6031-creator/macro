---
key: COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY
claim: >
  The synthetic Company Facts fixture converts into a raw ledger that retains
  FY2023 revenue 1050 and 1060, but the core 50-metric query kernel never
  returns those values as governed `revenue` cells because every converted row
  has dimensions_known=false and consolidated_only contracts refuse them as
  unknown_dimension_scope.
falsifier: >
  A core-registry BitemporalMetricQueryEngine.query_cell("FIXT", "revenue",
  FY2023 duration, latest_known_as_of after the 2024 filing) against
  convert_companyfacts_to_raw_ledger(companyfacts_versions.json,
  submissions_versions.json) returning CellState.VALUE with value 1050 or 1060.
so_what: >
  FIF-1 must not treat companyfacts_versions.json as a drop-in input to
  load_core_metric_registry(). Do not monkeypatch _fact_dimensions_allowed, do
  not relabel attested_occurrence as revenue, and do not infer revision_of from
  filing order. Re-spec the golden packet onto filing-package-shaped facts
  (dimensions_known=true, typed revision lineage) or wait for an explicit
  dimensions-unknown overlay that is not the B4 one-concept evidence bridge.
kind: landmine
verified_at: 2026-08-16
verified_by: >
  Worktree probe on origin/main 3b0c7dbbcc4d: conversion retained 39 events
  including us-gaap Revenue 1050 (0000000001-24-000001) and 1060
  (0000000001-25-000001), both event_type=filed, revision_of=None,
  dimensions_known=False. query_cell after 2024-12-31 and after 2025-12-31
  both returned not_evaluable reason unknown_dimension_scope. Pre-2024-filing
  cutoff returned missing_standard_fact. Existing pin:
  tests/test_fundamental_forensics_attested_occurrence_governance.py
  test_evidence_bundle_selects_unknown_dimensions_but_core_rejects_them.
scope:
  - macro
  - engine/fundamental_forensics/query.py
  - engine/fundamental_forensics/companyfacts_ledger.py
  - tests/fixtures/fundamental_forensics/companyfacts_versions.json
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

## What was measured

On `claude/fif-1-golden-financial-intelligence-packet` at
`3b0c7dbbcc4d`, the FIF-1 fixtures converted without network:

- 39 raw-ledger events
- FY2023 revenue original `1050` accession `0000000001-24-000001`
- FY2023 revenue later `1060` accession `0000000001-25-000001`
- both `filed`, no `revision_of`, `dimensions_known=False`
- extension `fixture:CustomerCount` remains unmapped

Core-catalog `query_cell` for `revenue` / FY2023:

| cutoff | policy | result |
|---|---|---|
| source 2024-01-01 | as_reported | missing (`missing_standard_fact`) |
| source 2024-12-31 | as_reported | not_evaluable (`unknown_dimension_scope`) |
| source 2024-12-31 | latest_known_as_of | not_evaluable (`unknown_dimension_scope`) |
| source 2025-12-31 | latest_known_as_of | not_evaluable (`unknown_dimension_scope`) |
| source 2025-12-31 | latest_restated | not_evaluable (`unknown_dimension_scope`) |

Recorded cutoff was `2026-08-05T12:00:02Z` so the 2026-08-02 registry pack was visible.
An earlier recorded cutoff of `2026-08-01T12:00:02Z` raised `UnsupportedMetricError: revenue`
because the catalog is not yet visible.

## Why a packet workaround is illegal here

`BitemporalMetricQueryEngine._fact_dimensions_allowed` admits consolidated_only
only when `dimensions_known` is true and the context has no dimensions. Company
Facts conversion deliberately sets `dimensions_known=False`. The isolated B4
bridge (`build_attested_occurrence_governance_bundle`) can select one such row
as metric `attested_occurrence` at confidence D; `GovernanceBundle` validation
rejects relabeling that contract as `revenue`.

Query-kernel temporal laws (1050 vs 1060) are proven in
`tests/test_fundamental_forensics_query.py` on synthetic `sec-edgar` facts with
`dimensions_known=True` and explicit `revision_of`. They are not proven on this
Company Facts fixture through the core catalog.
