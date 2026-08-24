---
key: AAPL-A1-A2-CROSS-FILING-OVERLAP-CENSUS
claim: >
  Against the accepted A3 AAPL ledger SHA
  ba149bd55d929d843f353e91bbf68147791fb8b4a20c258426ea2eb7527019d8 there are
  exactly 133 logical-key overlaps between A1 0000320193-25-000079 and A2
  0000320193-26-000020 of which 131 are exact complete confirmation candidates,
  1 is precision-different but interval-consistent us-gaap LongTermDebt at
  2025-09-27, and 1 is a changed-value us-gaap OtherAssetsNoncurrent at
  2025-09-27. Fifteen of the 131 are empty-dimension core-mapped non-nil query
  parents including total_assets 359241000000.
falsifier: >
  Re-run python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
  on that ledger SHA and observe any other class_counts, a duration overlap,
  or a different control class for us-gaap Assets instant 2025-09-27.
so_what: >
  A later confirmation implementation may mint XBRL_CONFIRMATION only for the
  exact 131, must not confirm OtherAssetsNoncurrent, must not treat LongTermDebt
  90678M vs 90700M as v1 exact confirmation, and should drive core query tests
  from the 15 consolidated mapped rows. Do not estimate these populations.
kind: data
verified_at: 2026-08-24
verified_by: >
  python3 research/financial_intelligence_fabric/replay_fif3a4r_aapl_overlap_census.py
  at HEAD 2df738a154acc6feae96e2ad0a6d289d3ab0f4a7
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
