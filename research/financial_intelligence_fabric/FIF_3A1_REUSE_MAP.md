# FIF-3A1 reuse map (frozen before code)

Verified 2026-08-22 against worktree `claude/fif-3a1` at `origin/main` `bc0a9cd89640`.
Decisions: `DEC:FIF-2-DONE-STATEMENTS-MOVE-TO-FIF-3`, `DEC:FIF-3A1-REUSE-MAP`.

## Identity (BINDING_OK)

| Layer | Exact ID | Source | CIK 0000320193 |
|---|---|---|---|
| Issuer | `ISS:US-XNAS-AAPL` | `data/reference/issuer_master.parquet` | `cik` column |
| Security | `SEC:US-XNAS-AAPL` | `data/reference/security_master.parquet` | `issuer_cik` |
| Listing | `US-XNAS-AAPL` | `security_master.listing_key` | derived listing key |
| Source filer | `0000320193` | accession prefix / XBRL entity identifier | IS the CIK |

Helpers: `lib.dataos.identity.security_id` / `issuer_id` (listing-key pure functions), `IssuerMaster.issuer_of_security`, `engine.fundamental_forensics.sec_document_spine.canonical_cik`. There is no `cik → issuer_id` helper; FIF-3A1 reads `issuer_master.parquet` and joins on `cik`. Ticker `AAPL` is a vendor alias only.

Request `entity_id` must be `ISS:US-XNAS-AAPL`. Packet/statement `cik` and `source_entity_id` remain `0000320193`. Do not mint `mmx.issuer.aapl`. Do not set `entity_id == CIK`.

## Package

Keep accession `0000320193-25-000079`, primary `aapl-20250927.htm`. No newer 10-K is treated as golden in-repo (`0000320193-26-000018` is an 8-K). B4F retained 1 of 93 (`retain_selected_filing`). FIF-3A1 expands retention only to members actually referenced for XBRL statement reconstruction (primary iXBRL, schema, presentation/calculation/definition/label). All other index members stay `not_requested`. Capture once into `tests/fixtures/fundamental_forensics/aapl_10k_2025/`. HTTP path is offline.

Reuse: `archive_index_url`, `archive_document_url`, `SecFilingArchiveCollector` (capture only), member-state vocabulary `stored|not_requested|missing|rejected_by_policy`.

Forbidden: R2 attested writer, `publish_query_snapshot`, FF-1 PR #5898, request-time SEC, Source Registry 2.0.

## XBRL / statements

`MUST_BUILD_MINIMAL_STATEMENT_CELL_TREE`. `statement_cell.v1` is masterplan prose only. Reuse `parse_sec_filing_document` for facts/contexts/units. Build bounded presentation/calculation/label walk. Optional metric mapping via existing `MetricRegistry` concept aliases after the tree exists; unmapped rows survive. Duplicate same-concept/same-context facts fail closed or expose ambiguity — never first-row-wins.

## Consumer

Sibling: `POST /api/forensics/v1/financial/{query,revisions,packet}` in `app/forensics.py`. New route `POST /api/forensics/v1/financial/statements`. Auth first, private/no-store, `X-FIF-Response-SHA256`. Request names canonical issuer + accession explicitly. No ticker. No implicit now. Default FIF-2 query/revision/packet providers stay unavailable/503. Production attested issuer service stays NOT_BUILT.
