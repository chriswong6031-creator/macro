# FIF-3A2 reuse map (frozen before code)

Verified 2026-08-23 against worktree `claude/fif-3a2` at `origin/main`
`0a23f1ffcedc7d8a3838b05ef137742eb1d809a1`. Independent SEC recovery of
accession `0000320193-26-000020` plus bounded Earnings-reader archaeology.
Decisions: `DEC:FIF-3A1-ACCEPTED-GOLDEN-ON-MAIN`, `DEC:FIF-3A2-REUSE-MAP`.

Contract-gap ruling: **NO STOP**. `statement_cell.v1` column objects already
carry `{kind, start, end, label}`. Q3 income durations that share an end date
are distinguishable by complete period (start+end) taken from the iXBRL
context of facts in that displayed column. Do not invent "Three Months Ended"
label heuristics as identity. A1 10-K column-count hardwires, member-name
literals, and annual role URIs are implementation limits, not a cell-contract
hole.

## Identity (BINDING_OK — unchanged)

| Layer | Exact ID | Source |
|---|---|---|
| Issuer | `ISS:US-XNAS-AAPL` | IssuerMaster |
| Security | `SEC:US-XNAS-AAPL` | IssuerMaster |
| Listing | `US-XNAS-AAPL` | `listing_key` |
| Source filer | `0000320193` | accession / XBRL entity |

Request `entity_id` remains `ISS:US-XNAS-AAPL`. No ticker. No latest.

## Bounded golden filing set

Generalize `GoldenAaplStatementProvider` from one accession to the exact set.
Still no ticker inference and no latest.

| Accession | Form | Fixture | Notes |
|---|---|---|---|
| `0000320193-25-000079` | 10-K | `tests/fixtures/fundamental_forensics/aapl_10k_2025/` | A1 accepted. Response SHA must remain `25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184`. |
| `0000320193-26-000020` | 10-Q | `tests/fixtures/fundamental_forensics/aapl_10q_2026q3/` | A2. Independently recovered `acceptanceDateTime=2026-07-31T10:01:02.000Z`. Index SHA `3e5dde4c0403da2358df715608c679d66223c8d716a75fe1136d9257ba812fdc` / 6311 bytes / 65 members. |

`0000320193-26-000018` is the results 8-K, not this 10-Q.

## Package admission

Reuse A1 admit law: full index inventory with typed `stored` / `not_requested`,
six retained members (primary iXBRL, schema, presentation, calculation,
definition, label), submissions/acceptance witness, no request-time SEC, no R2,
no attested-history mutation. Replace the A1-only `member_count == 93` hardwire
with "index length equals this package's committed `member_count`". Resolve
linkbase bytes by manifest `role`, never by `aapl-20250927_*` literals.

Q3 retained stems: `aapl-20260627.htm` / `.xsd` / `_pre.xml` / `_cal.xml` /
`_def.xml` / `_lab.xml`.

## Quarterly columns

Do not assume 3 duration / 2 instant. Derive displayed columns from the captured
table. Bind each column by the complete filing period of a same-column duration
(or instant, for the balance sheet) context — not by end date first-match, not
by newest-N. Instant facts that sit inside duration columns (cash beginning
balances) do not define the column period.

Human-reviewed Q3 HTML (titles are filing-displayed):

- Operations: 4 duration columns, 3M/9M × 2026/2025, shared ends `2026-06-27` and `2025-06-28`.
- Balance sheet: 2 instants `2026-06-27`, `2025-09-27`.
- Cash flow: 2 duration columns, 9M only.

Do not reconstruct comprehensive-income or equity statements in this wave.
A1 three primary types remain the served set.

Q3 presentation roles are condensed+Unaudited and live on the Q3 package
manifest. A1 packages without `statement_roles` keep
`PRIMARY_STATEMENT_ROLES` / `STATEMENT_TITLES`.

## Event link

Add optional top-level `related_event_ref` only when the golden package carries
it. Omit the key entirely for the A1 10-K so canonical JSON stays
byte-identical. Allowed fields only:

```json
{
  "plane": "company_intelligence/event_workspaces",
  "event_id": "evt_cik0000320193_2026q3_results",
  "relation": "same_fiscal_results_period",
  "source_filing_distinction": {
    "earnings_release_8k_accession": "0000320193-26-000018",
    "periodic_report_accession": "0000320193-26-000020"
  }
}
```

No `generation_id`. No workspace payload. No request-time Earnings fetch.
Acceptance tests may call `read_event_workspace` to prove the event currently
resolves; that proof is not on the statements HTTP path.

## Consumer

Same route `POST /api/forensics/v1/financial/statements`. Same request schema.
Authority remains `{"class":"context_only","display_only":true}`.
`delivery.attested=false`, `delivery.production_issuer_service=false`.

## Forbidden

No `statement_service_v2`. No second provider family. No FIP generalization.
No RawFactLedger. No event_workspace.v1 edit. No FIF-7. No SNOW/CAT/BAC/GOOGL.
No new UI. No generic dimensional engine.
