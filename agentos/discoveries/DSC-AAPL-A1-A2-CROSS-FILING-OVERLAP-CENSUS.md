---
key: AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS
claim: >
  Against the accepted A3 AAPL ledger SHA
  ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8 there are
  exactly 133 logical-key overlaps between A1 0000320193-25-000079 and A2
  0000320193-26-000020. Tightened v1 eligibility yields 130 exact numeric
  confirmation candidates, 1 nil_confirmation_unspecified
  (us-gaap CommitmentsAndContingencies instant 2025-09-27), 1
  precision_consistent_unconfirmed us-gaap LongTermDebt, and 1 changed-value
  us-gaap OtherAssetsNoncurrent. All 133 overlaps share original Clark URI
  http://fasb.org/us-gaap/2025 on both filings (mismatch count 0). Fifteen of
  the 130 are empty-dimension core-mapped query parents including
  total_assets 359241000000; 93 dimensioned exact rows remain lawful lineage
  candidates.
falsifier: >
  Re-run python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
  on that ledger SHA and observe any other class_counts, a duration overlap,
  a namespace mismatch, or a different control class for us-gaap Assets
  instant 2025-09-27.
so_what: >
  A later confirmation implementation may mint lineage xbrl_confirmation only
  for the exact 130 numeric rows, must not confirm OtherAssetsNoncurrent,
  LongTermDebt 90678M vs 90700M, or the CommitmentsAndContingencies nil pair,
  must retain the 93 dimensioned rows as lineage, and should drive core query
  tests from the 15 consolidated mapped rows. Do not estimate these
  populations. Do not load the census JSON into a runtime provider.
kind: data
verified_at: 2026-08-25
verified_by: >
  python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
  after Sol 2026-08-25 bounded amendments; payload SHA
  b1577b04f553c56ba278d2057ecc07a0d23159a1d20a41339b39da4ed24c12a9
scope:
  - macro
  - tests/fixtures/fundamental_forensics/aapl_10k_2025
  - tests/fixtures/fundamental_forensics/aapl_10q_2026q3
  - engine/fundamental_forensics/ixbrl_raw_ledger.py
  - research/financial_intelligence_fabric/FIF_3A4R_AAPL_OVERLAP_CENSUS.json
  - WS:FINANCIAL-INTELLIGENCE-FABRIC
confidence: verified
---

The census JSON is research evidence, not a runtime provider input.
The A4R research census timestamp does not authorize runtime lineage.
v1 stays exact; `_duplicates_agree` does not prove cross-filing equality.
