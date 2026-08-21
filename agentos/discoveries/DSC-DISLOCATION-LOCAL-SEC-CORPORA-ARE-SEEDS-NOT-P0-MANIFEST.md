---
key: DISLOCATION-LOCAL-SEC-CORPORA-ARE-SEEDS-NOT-P0-MANIFEST
claim: >
  Macro's committed SEC artifacts contain substantial historical candidate
  metadata, but no artifact simultaneously provides broad-universe selection,
  exact public clocks, source-document identity and hashes, evidence spans,
  economic-episode identity and audited impairment classification required by P0.
falsifier: >
  gh run view 32353471217 --repo mastermindx-market-intelligence/macro --log
  together with a repository read showing one committed artifact that contains
  all required P0 fields would disprove the claim.
so_what: >
  Do not relabel material_8k_events or earnings_8k_dates as the P0 manifest.
  Build a research view that consumes the broad SEC source plane and canonical
  document spine, preserving typed gaps and owner boundaries.
kind: data
verified_at: 2026-08-20
verified_by: "gh run view 32353471217 --repo mastermindx-market-intelligence/macro --log; artifact 9400729355"
scope: [macro, alpha-intelligence, WS:ALPHA-INTELLIGENCE-INTEGRATION]
confidence: verified
---

## Measurements

- `material_8k_events.parquet`: 50,936 accession rows across 664 tickers, with date-only filing labels and collector-era `_first_seen`; no accepted-at or document receipt.
- `earnings_8k_dates.parquet`: 98,975 Item-2.02 rows across 1,314 tickers with exact acceptance clocks, but the committed schema lacks accession, form and report-date columns expected by the current collector.
- Source-census output SHA-256: `2afc9a1ad3893703b4b0aac662b44420317ba979035787992d277ec4745064ac`.