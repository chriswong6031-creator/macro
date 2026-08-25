# Cell B V2 buyback source census — 2026-08-22

Scientific source-capacity verdict: `SOURCE_CENSUS_IDENTITY_OR_RIGHTS_BLOCKED`

This is the commissioned price-blind source census. It does not inspect any market outcome, does not change P0, and grants no Prophet/Fusion/Availability/trade/sizing authority.

## Frozen receipts

- repository/base: `mastermindx-market-intelligence/macro@3d35ec5cd5aee8f11dedbd87136444e1e8bf4497`
- census code commit: `acaf0cd61e21c46e81b880b9c3d7246b6aa60e22`
- canonical manifest file SHA-256: `36bef94006eea85e4fc1e65651aa1ec79a23db1766b9ecdbc7ab9ee2c4c3d276`
- source-receipt-set SHA-256: `e97d1bdfb85c23c749fe98607a064ee9fa5f5e8303169f18ab02b15b20f99098`
- parser: `cell-b-v2-buyback-source-census/2.0.0`

## Exhaustive denominator

- exact non-amended Form 8-K rows: **300,995**
- unique CIKs: **9,885**
- unique filing dates: **1,081**
- range: `2022-03-01..2026-06-30`
- source: all 18 official quarterly EDGAR master indexes; SEC full-text search was not used.
- exact-identity denominator coverage: **54,646 / 300,995** (18.155%); **246,349** rows remain outside the current exact identity plane.

## Source capacity by frozen period

| period | possible roots | discovered roots | admitted | issuers | dates | source N_eff | center floor | tail source floor |
|---|---:|---:|---:|---:|---:|---:|---|---|
| development_through_2024 | 14936 | 3623 | 0 | 0 | 0 | 0.000 | False | False |
| confirmatory_2025 | 5909 | 1551 | 0 | 0 | 0 | 0.000 | False | False |
| replication_2026_h1 | 3099 | 847 | 0 | 0 | 0 | 0.000 | False | False |

## Refusal ledger

### development_through_2024

- `NOT_NEW_AUTHORIZATION`: 11,296
- `INCREASE_EXTENSION_RENEWAL_OR_REMAINING`: 3,416
- `AMOUNT_UNESTIMABLE`: 4
- `TENDER_ASR_OR_NON_DISCRETIONARY`: 15
- `DEBT_PREFERRED_OR_EMPLOYEE_WITHHOLDING`: 1
- `COMPLETED_PURCHASE_ONLY`: 2
- `FINANCIAL_ISSUER`: 19
- `BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE`: 95
- `OVERLAP_MA_OR_MATERIAL_AGREEMENT`: 37
- `OVERLAP_FINANCING`: 2
- `OVERLAP_MANAGEMENT`: 9
- `OVERLAP_RESTRUCTURING`: 3
- `SOURCE_ROOT_UNRESOLVED`: 17
- `CLOCK_UNESTIMABLE`: 20

### confirmatory_2025

- `NOT_NEW_AUTHORIZATION`: 4,351
- `INCREASE_EXTENSION_RENEWAL_OR_REMAINING`: 1,468
- `AMOUNT_UNESTIMABLE`: 2
- `TENDER_ASR_OR_NON_DISCRETIONARY`: 8
- `FINANCIAL_ISSUER`: 6
- `BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE`: 47
- `OVERLAP_MA_OR_MATERIAL_AGREEMENT`: 8
- `OVERLAP_FINANCING`: 1
- `OVERLAP_MANAGEMENT`: 5
- `SOURCE_ROOT_UNRESOLVED`: 7
- `CLOCK_UNESTIMABLE`: 6

### replication_2026_h1

- `NOT_NEW_AUTHORIZATION`: 2,242
- `INCREASE_EXTENSION_RENEWAL_OR_REMAINING`: 782
- `AMOUNT_UNESTIMABLE`: 3
- `TENDER_ASR_OR_NON_DISCRETIONARY`: 8
- `FINANCIAL_ISSUER`: 3
- `BUNDLED_EARNINGS_RESULTS_OR_GUIDANCE`: 31
- `OVERLAP_MA_OR_MATERIAL_AGREEMENT`: 11
- `OVERLAP_FINANCING`: 1
- `OVERLAP_MANAGEMENT`: 7
- `SOURCE_ROOT_UNRESOLVED`: 10
- `CLOCK_UNESTIMABLE`: 1

## Interpretation and limits

- The 300,995-row denominator is exhaustive. Content acquisition is fail-closed behind official Submissions item metadata: every identity-resolved 7.01/8.01 (or item-undeclared) root is retrieved from the exact SEC archive filename; all other denominator rows remain denominator negatives rather than discovered family roots.
- A current ticker is never used as identity. Only exact repository issuer/security/listing rows are eligible; missing historical/delisted coverage is disclosed through denominator-versus-identity counts and cannot be silently promoted.
- The unresolved development identity plane has an upper-bound support ceiling above the center floor. Because those rows cannot be source-adjudicated into or out of the family without exact identity, the terminal verdict is identity/rights blocked rather than an underpowered-family finding. The exact-identity subset is a lower-bound read, not the family denominator.
- SEC acceptance time alone never certifies the family clock. A row is admitted only when an official source document states an exact dated Eastern timestamp that maps wholly to a closed-market interval on the canonical US cash-equity calendar, including early closes and holidays.
- The tail line is source capacity only. It is not a classification or promotion result; any later response-valid subset would have to re-clear its separately frozen gates.
- Adverse or null capacity is accepted as the scientific result. No exclusion, clock rule, amount rule, or family boundary was broadened after the scan.
