# Dislocation P0 — Blind Selection Freeze Contract

**Date:** 2026-08-20  
**Wave:** P0-A1  
**Authority:** research / source-only; no rank, gate, size, candidate origination, Prophet, Radar, Fusion, execution or trade authority

> **P0-A1R supersession pointer (2026-08-22):** This #6117-era contract remains
> historical provenance. Resumed P0-A1R selection, sampling, 04d authority, quarantine,
> owner consumption, and stop law are controlled by
> `DISLOCATION_P0_A1R_SOURCE_LAW_AMENDMENT_2026-08-22.md` and
> `DEC:DISLOCATION-P0-A1R-SOURCE-LAW-RECONCILIATION`. Do not silently rewrite the
> historical claims below or treat them as P0-A1R authority.

## Binding freeze

This contract recorded #6117 candidate *selection law* before any price join. It does
not freeze event classification. A search hit is not an economic episode. Its P0-A1R
supersession is explicit above.

Executable freeze sources, in precedence order:

1. Chairman Dislocation Intelligence outcome.
2. `DISLOCATION_CROSS_ISSUER_P0_PREREG_2026-08-20.md`.
3. `DISLOCATION_TURN5_SOURCE_ARCHITECTURE_FREEZE_2026-08-20.md` (PR #6068, unmerged at wave start; carried into this tree as the Turn-5 source law).
4. This contract and `contracts/DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json`.
5. `contracts/DISLOCATION_P0_SOURCE_CANDIDATE_SCHEMA.json`.
6. Existing SEC document-spine / identity / evidence owners.
7. Implementation convenience last.

## Query ledger reconstruction

The P0-A1 dispatch named:

- `DISLOCATION_P0_BLIND_SELECTION_FREEZE_CONTRACT.md`
- `DISLOCATION_P0_SOURCE_QUERY_LEDGER_V1.json`
- query-ledger SHA-256 `04d502e398a0f2ae65df7b2f9d5156305094f7b10ca104da08792d7219c1f83c`
- sample seed `ec34136d9ed11f0070a5eed0a0225f465f8095d3f3cd228b752b3c27c9f1e876`

Those two files were **not present** on GitHub `origin/main`, PR #6068, or the attached A1 handoff directory. Reconstructing a file that hashes to `04d502e…` without the original bytes would be a silent substitution.

The executable ledger is therefore reconstructed from the Turn-5 frozen lexicon (PR #6062, SHA-256 `c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58`) plus the Turn-5 selection protocol and quotas. Canonical reconstructed ledger SHA-256:

`496537f5d3822c160c93afb3cbccf55f6334028e20094979e1de797e6aab3b36`

The reconstructed ledger records the missing A1 SHA as `UNVERIFIED_ABSENT_SOURCE_FILE` and does not claim identity with it.

Selection seed used for ranking is the Turn-5 schema constant:

```text
DISLOCATION-P0-SOURCE-2026-08-20-v1
```

```text
selection_key = SHA256(seed | family | era | base_form | cik | accession)
```

Review order is ascending `selection_key`. The extractor cannot skip a row except through a typed refusal.

## Allowlist / denylist

Allowed sources:

- SEC 8-K / 8-K/A / 6-K / 6-K/A filings and exhibits
- official SEC hosts only: `efts.sec.gov`, `data.sec.gov`, `www.sec.gov`

Denied:

- prices, OHLC, volume, charts, DRL, Prophet, Radar, winner/failure casebooks, EXK replay outputs
- SEDAR+ public-site scraping
- inferring Item 2.02 accession from ticker/date
- inventing MACRO_OR_INDUSTRY_WIDE phrases (no frozen lexicon entries; family is `SOURCE_CAPACITY_SHORTFALL`)

Event years: 2016-01-01 through 2025-12-31. Modern confirmatory era: 2022-2025.

## Exclusions

- Endeavour Silver / EXK / CIK `0001015647` by ticker, CIK, or name substring `endeavour silver`
- US ticker `EDR` is **not** a blanket exclusion
- `/A` amendments are retained as correction transitions and are not origins by default
- metals/mining rows may appear in the source queue and must be tagged; they are parked for later external validation and cannot carry confirmatory N

## Quotas (source overbuild, before price eligibility)

| Family | Source target | Modern | Development | 8-K | 6-K |
|---|---:|---:|---:|---:|---:|
| Each of five temporary families | 48 | 32 | 16 | 32 | 16 |
| Structural impairment control | 48 | 32 | 16 | 32 | 16 |
| Resolved-before-disclosure control | 24 | 16 | 8 | 16 | 8 |
| Macro/industry-wide control | 24 | 16 | 8 | 16 | 8 |

Macro/industry-wide is blocked until a frozen phrase cell exists. Maximum planned source origins remain 336. Issuer cap before audit: five candidates.

A1 floors: ≥320 raw selected candidates; ≥48 per primary family before adjudication; ≥150 modern-era; ≥160 economic episode origins after first extraction.

## Clock law

- `accepted_at` is the SEC acceptance timestamp and the only primary inference clock
- `filed_on` is date-only and never promoted
- missing exact clock → `DATE_ONLY_REFUSED` or `ACCEPTED_AT_UNAVAILABLE`
- no backfill of missing source times

## Stop

Stop before market-data join. Do not ask whether any candidate recovered.
