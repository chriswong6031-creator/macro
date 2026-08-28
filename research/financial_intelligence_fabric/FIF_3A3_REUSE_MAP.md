# FIF-3A3 reuse map (frozen before code)

Verified 2026-08-23 against worktree `claude/fif-3a3` at pickup `origin/main`
`98a297a324f77527880fa25b919f14cee74d4c81` after Sol-observed
`f69348e80d4be151ae62d3d70e38b3ce0924d68f`. Decisions:
`DEC:FIF-1-V1-FROZEN`, `DEC:FIF-3A1-ACCEPTED-GOLDEN-ON-MAIN`,
`DEC:FIF-3A2-ACCEPTED-GOLDEN-ON-MAIN`, `DEC:FIF-3A3-REUSE-MAP`.

Contract-gap ruling: **NO STOP**. The strict parser emits Clark-notation
QNames; the query kernel indexes `taxonomy:concept`. Existing
`TAXONOMY_NAMESPACE_POLICY` in `filing_attestation.py` already maps
US GAAP 2009–2026 and DEI 2009–2026 URIs. FIF-3A3 reuses that table
inside `ixbrl_raw_ledger.canonicalize_clark_qname`. Unknown/custom
namespaces retain Clark identity and stay unmapped. The query kernel
is not patched to guess Clark notation.

## Path (BINDING_OK)

```
admitted AAPL golden package
  → parse_sec_filing_document(...)
  → ixbrl_raw_ledger.convert_parsed_filing (no XML)
  → RawFactLedger + FilingMetadata + core registry
  → GoldenAaplFinancialQueryProvider
  → execute_financial_query(...)
  → POST /api/forensics/v1/financial/query
```

One converter only. Do not create another ledger, metric registry, query
kernel, or financial API.

## Identity

| Layer | Exact ID | Source |
|---|---|---|
| Issuer | `ISS:US-XNAS-AAPL` | IssuerMaster |
| Listing | `US-XNAS-AAPL` | `listing_key` |
| Source filer | `0000320193` | accession / XBRL entity |
| Query ticker | `AAPL` | last segment of Data OS listing_key |
| Document | `sec_document_id(...)` after CIK normalize + accession/role/name spine validation | exported from `sec_document_spine.py`; `320193` ≡ `0000320193` |

Request `entity_id` remains `ISS:US-XNAS-AAPL`. Query kernel entities map
`AAPL → 0000320193`. FIP1 stays `mmx.issuer.fip1`.

## QName / unit law

- `{http://fasb.org/us-gaap/{2009-2026}}Local` → `us-gaap:Local` via `TAXONOMY_NAMESPACE_POLICY`
- `{http://xbrl.sec.gov/dei/{2009-2026}}Local` → `dei:Local`
- `{http://www.xbrl.org/2003/iso4217}USD` → `iso4217:USD`
- `{http://www.xbrl.org/2003/instance}shares` → `xbrli:shares`
- `{http://www.xbrl.org/2003/instance}pure` → `xbrli:pure`
- Apple/custom/SRT/CYD/ECD Clark QNames retain source identity
- `parsed_value` is the parser `normalized_value`; do not reapply sign/scale
- `source_occurrence_key` is parser `fact_id`

## Clocks

- `accepted_at` = SEC acceptance (`source_accepted_at`)
- `recorded_at` = package `fixture_recorded_at`
- FilingMetadata `available_at` = fixture-recorded clock, not SEC acceptance
- mapping/computed/published absent on raw source occurrences
- Both A1 and A2 are `FILED`. Do not set `revision_of`.

## Provider / HTTP

Change only `_financial_query_provider()` to `GoldenAaplFinancialQueryProvider`.
Do not activate revision or packet providers for AAPL.
The query provider source set is frozen to A1 `0000320193-25-000079` and
A2 `0000320193-26-000020` (`GOLDEN_AAPL_QUERY_ACCESSIONS`). It must not
iterate `GOLDEN_AAPL_FIXTURES`.

- AAPL golden query → 200
- Unknown issuer on this available provider → private 400 `unknown entity`
- Corrupt/missing admitted golden source → private 503
- Unlawful `FinancialQueryDataset.delivery` → private 503

Optional `FinancialQueryDataset.delivery`, default absent. The only lawful
non-null object is exact:

```
kind = committed_golden_fixture
attested = false
production_issuer_service = false
```

Wrong kind, true flags, non-booleans, missing keys, or extra keys are
unavailable. FIP1 builders omit delivery → FIF-2A bytes unchanged.
Authority remains `{"class":"context_only","display_only":true}`.

## Explicit non-goals

No real AAPL FIP. No `financial_intelligence_packet.v1` change. No
revision-history invention. No AAPL packet/revision provider. No
disclosure family. No peer set. No Filing Forensics UI. No SEC network
on the request path. No R2 or attested-history write. No Company Facts
substitution. No FIF-3A4.
