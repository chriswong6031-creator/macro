# statement_cell.v1 — FIF-3A1 as-reported statement tree

Minimal architecture anticipated by
`research/MASTERMIND_FINANCIAL_INTELLIGENCE_FABRIC_MASTERPLAN_2026-08-16.md`.
This is not a generic financial-knowledge graph.

## Request (`fundamental_forensics.financial_statement_request/v1`)

Exact root fields, no extras:

- `schema`
- `entity_id` — canonical Data OS issuer id (`ISS:US-XNAS-AAPL`)
- `accession` — SEC accession (`0000320193-25-000079`)

No ticker. No implicit `now`. No period/policy kernel.

## Response (`fundamental_forensics.financial_statement_response/v1`)

Thin wrapper:

- `schema`
- `entity` — Data OS issuer/security/listing plus source-native `cik` / `source_entity_id`
- `filing` — accession, form, primary document, SEC clocks, fixture-recorded clock
- `package` — full member inventory with `stored` / `not_requested` plus digests
- `statements` — ordered trees
- `coverage` — parser kind and fact/context counts

## Statement

- `statement_type` / `role_uri` / `title`
- `columns` — filing-native periods (duration or instant)
- `row_count` / `rows`

## Row

Row identity is presentation path + order + preferred label, never the metric catalog.

- `order`, `depth`, `concept`, `abstract`
- `as_reported_label`, `preferred_label_role`, `label_role_used`
- `presentation_path`
- `standardized_metric_id` (optional enrichment)
- `mapping_state`: `mapped` | `unmapped` | `ambiguous_mapping`
- `mapping_receipt`
- `formula_dependencies`
- `cells`

## Cell (`statement_cell.v1`)

- statement type/role is on the parent tree
- presentation path/order is on the parent row
- as-reported label is on the parent row
- optional standardized metric is on the parent row
- `value`, `unit`, `scale`, `decimals`, `period`, `dimensions`
- `direct_or_calculated`
- `source_receipt` (document, digest, fact id, concept, context, unit, source span, occurrence count; competing ids/values when `ambiguous`)
- `quality_state`: `available` | `missing_fact` | `nil` | `abstract` | `ambiguous`

Numeric values remain decimal strings. Duplicate agreeing facts keep a representative
and `occurrence_count`. Disagreeing facts are `ambiguous` with `value` null — never
first-row-wins.
