# Dislocation Intelligence — Turn 5 Source Architecture Freeze

**Date:** 2026-08-20  
**Program:** Alpha Intelligence Expansion K3-E / K4-F-G / K5-K6  
**Authority:** research and architecture only; no rank, gate, size, candidate origination, Prophet/Radar/Fusion integration, execution or trade authority

## 0. Executive ruling

The source estate is sufficient to begin a blind cross-issuer extraction program, but it is **not** already a Dislocation P0 manifest.

Turn 5 proved three different facts:

1. The repository contains substantial historical SEC metadata and exact acceptance-time coverage.
2. A frozen semantics-first SEC full-text-search lexicon finds ample 8-K and 6-K candidate capacity in every temporary-event family and control family.
3. No existing artifact simultaneously provides broad-universe selection, exact public clocks, exact source-document identity, evidence spans, economic-episode identity, and audited temporary-versus-structural classification.

The missing organ is a **source acquisition and evidence-convergence view**, not another market scanner.

## 1. Production research receipts

### 1.1 Local source-only census

Draft PR #6061 ran in a sparse workspace containing selected `data/edgar/*` artifacts and no price, OHLC, intraday, Price Pressure or washout path.

- `PRICE_FIREWALL=PASS`
- network access: none
- price/outcome access: false
- two outputs byte-identical
- output SHA-256: `2afc9a1ad3893703b4b0aac662b44420317ba979035787992d277ec4745064ac`
- artifact ID: `9400729355`
- PR #6061 closed unmerged

### 1.2 SEC full-text-search capacity census

Draft PR #6062 checked out only its research query script.

- `PRICE_FIREWALL=PASS`
- only permitted network host: `efts.sec.gov`
- price/outcome access: false
- frozen lexicon SHA-256: `c164b5b3d0cfa8365a685e88662b00d8ad338957886fd51771286bf3c137cb58`
- output SHA-256: `24d691251c0f2bedb1d15d283bdd33df938f5e81030d116b23318b40cdacbe35`
- 292 query/form/window cells completed
- artifact ID: `9401355421`
- PR #6062 closed unmerged

Neither ephemeral executable entered production.

## 2. Existing source estate

| Source | Live capability | What it unlocks | Missing for P0 |
|---|---|---|---|
| `data/edgar/material_8k_events.parquet` | 50,936 accessions, 664 tickers, material item codes | Structured seed and accession identity | Narrative-basket scope; date-only filing clock; no exact source document or accepted-at |
| `data/edgar/earnings_8k_dates.parquet` | 98,975 Item-2.02 rows, 1,314 tickers, exact acceptance timestamps | Long-history expectation-reset anchor | Committed schema lacks accession/form/report-date fields now expected by its collector contract |
| Broad SEC source plane | Exact SEC Submissions bytes for a broad issuer universe in private content-addressed storage | Canonical source bytes and independent poll/accept/file/retrieval clocks | Historical-shard recovery must be proven for each selected P0 accession |
| SEC document spine | Filing/document manifests, archive URLs, exact acceptance clock, hashes, retrieval receipts and source spans | Canonical evidence receipt plane | No Dislocation packet consumer yet |
| SEC Full Text Search | Full filing-and-attachment candidate search | Semantics-first 8-K/6-K discovery | Hit is not an event, classification, clock or receipt |
| SEDAR+ public website | Human public access | Manual research | Automated scraping and database construction are rights-blocked |
| SEDAR+ Data Distribution Service | Licensed bulk distribution | Rights-safe native Canadian source lane | Not connected or licensed in this program |

### 2.1 Material 8-K measurements

- rows/accessions: **50,936**
- distinct tickers: **664**
- distinct CIKs: **666**
- filing span: **2004-08-25 through 2026-08-19**
- exact accepted-at field: **absent**
- filing-date precision: **date-only**
- `_first_seen`: collector-era operational observation, not historical public availability
- primary universe: existing narrative-basket membership, not a blind market universe

### 2.2 Item-2.02 measurements

- rows: **98,975**
- distinct tickers/CIKs: **1,314**
- exact acceptance span: **2004-08-24T00:51:41Z through 2026-07-02T20:31:36Z**
- 2022–2025 rows: **21,694**
- committed columns: `ticker`, `cik`, `filing_date`, `acceptance_datetime`, `items`
- current collector contract also expects accession, form and report date

Do not infer missing accession identity from ticker and date. P0 must regenerate or bypass this stale committed schema through the canonical filing/document spine.

## 3. SEC candidate-capacity result

The following numbers prove retrieval capacity only. Raw hit totals double-count phrases, documents and amendments; first-page unique IDs are a sample, not a complete pool.

| Family | Modern first-page unique docs | Sample CIKs | Raw hits, not deduped |
|---|---:|---:|---:|
| `PHYSICAL_MECHANICAL_INTERRUPTION` | 1,497 | 98 | 2,690 |
| `EXTERNAL_HUMAN_INTERRUPTION` | 863 | 79 | 13,085 |
| `CYBER_OR_IT_INTERRUPTION` | 1,080 | 63 | 19,497 |
| `WEATHER_OR_PHYSICAL_DISASTER` | 1,602 | 85 | 23,983 |
| `TEMPORARY_EXPECTATION_RESET` | 644 | 97 | 1,096 |
| `STRUCTURAL_IMPAIRMENT_CONTROL` | 1,771 | 116 | 106,243 |
| `RESOLVED_BEFORE_DISCLOSURE_CONTROL` | 217 | 74 | 217 |

Every primary temporary family has hundreds of distinct modern-era candidate documents in both 8-K and 6-K lanes. Candidate scarcity is not the limiting problem.

## 4. SEC FTS landmines

- Form filters admitted `8-K/A` and `6-K/A`; exact client-side base-form normalization is mandatory.
- Twenty phrase/form/window cells reached the SEC 10,000-result ceiling.
- A complete extractor must recursively split capped date ranges until every leaf is below the ceiling and then page every leaf to exhaustion.
- Broad phrases such as `going concern`, `unauthorized access`, `earthquake`, `civil unrest` and `severe weather` are noisy.
- Query phrase is candidate provenance, never event-family evidence.
- SEC corrections can move results; query responses and exact source documents must be content-hashed and frozen.
- Amendments are correction transitions and are not episode origins by default.

An incomplete query leaf is `INCOMPLETE_QUERY_CELL`, not zero.

## 5. Rights-safe scope amendment P0.1

The confirmatory source universe is amended from “U.S. and Canadian public issuers” to:

> **SEC-reporting issuers whose event truth is reconstructable from exact 8-K, 8-K/A, 6-K or 6-K/A filing and document receipts.**

This includes eligible U.S. issuers and foreign private issuers. A later runner may project venue-neutral event truth onto a lawfully mapped U.S., ADR or home-market listing, but event selection and classification remain price-blind.

Native SEDAR+ issuers without adequate SEC filings are excluded from P0 confirmatory extraction until Mastermind has:

1. a licensed SEDAR+ Data Distribution Service or equivalent first-party source;
2. a rights-approved storage and redistribution contract;
3. exact public-availability clocks;
4. a canonical issuer/document identity join.

The public SEDAR+ website must not be scraped or used to construct a database.

This is not a reduction of the international vision. It prevents the P0 evidence experiment from obtaining geographic breadth through a rights-unsafe source plane. SEC 6-K is the lawful foreign-issuer bridge while the licensed Canadian lane is built separately.

## 6. Canonical source architecture

```text
Frozen QueryCell
    ↓
Raw SEC FTS QueryReceipt
    ↓
CandidateHit (unclassified)
    ↓
SEC Submissions FilingReceipt
    ↓
SEC Document-Spine receipts and exact bytes
    ↓
EvidenceSpan proposals
    ↓
Independent source-only audit
    ↓
EventTransition
    ↓
EconomicEpisode
    ↓
Frozen price-blind Source Manifest
    ─────────────── HASH FREEZE ───────────────
    ↓
Separate eligibility / market / counterfactual runner
```

No new universal event store is created. SEC bytes and filing/document receipts remain owned by the broad SEC source plane and document spine. P0 writes a research manifest/view under Alpha Intelligence.

### Canonical ownership

| Concern | Owner | P0 action |
|---|---|---|
| Exact SEC Submissions bytes | Broad SEC source plane / Research Vault | consume; do not duplicate |
| Acceptance, filed, retrieval and recorded clocks | Broad SEC source plane | preserve independently |
| Filing/document identity, URLs, hashes and spans | `sec_document_spine` | consume through owner |
| Issuer/event identity | Company Intelligence / Data OS identity | join; do not create ticker truth |
| Query receipt and source manifest | P0 research artifact | freeze under Alpha Intelligence |
| Prices/counterfactuals | Separate runner after manifest freeze | technically absent from source workspace |
| Outcome grading | Canonical Path Survival / Evaluation OS | later; no new grader |

## 7. Blind candidate-selection protocol

### 7.1 Frozen query-cell identity

```text
(event_family, exact_phrase, base_form, date_shard)
```

The phrase lexicon and base forms are frozen before extraction. No term may change after market outcomes are visible.

### 7.2 Complete retrieval

For every query cell:

1. query SEC FTS;
2. recursively split capped cells by date;
3. page every leaf to exhaustion;
4. store exact response hash, parameters, retrieval clock and result IDs;
5. exact-filter base form client-side;
6. retain `/A` as amendments/corrections;
7. deduplicate documents by SEC hit ID and filings by `(CIK, accession)` while preserving every phrase/query edge.

### 7.3 Deterministic review order

Seed: `DISLOCATION-P0-SOURCE-2026-08-20-v1`

```text
selection_key = SHA256(seed | family | era | base_form | cik | accession)
```

Review ascending `selection_key`. The extractor cannot skip a row except through a typed refusal. All reviewed candidates and refusals remain in the audit ledger.

### 7.4 Source-manifest overbuild target

The source-only manifest is larger than the eventual price-eligible panel because the extractor cannot see price or liquidity.

| Family/control | Source target | Modern | Development | 8-K | 6-K |
|---|---:|---:|---:|---:|---:|
| Each of five temporary families | 48 | 32 | 16 | 32 | 16 |
| Structural impairment control | 48 | 32 | 16 | 32 | 16 |
| Resolved-before-disclosure control | 24 | 16 | 8 | 16 | 8 |
| Macro/industry-wide control | 24, subject to blind capacity pilot | 16 | 8 | 16 | 8 |

Maximum planned source origins: **336**. The later price/coverage runner may refuse rows; it may not request outcome-informed top-ups.

## 8. Source acquisition and evidence contract

### 8.1 Observable capability

Given a frozen SEC query cell, Mastermind must produce a price-blind packet that answers:

- which exact filing/document matched;
- when the SEC source became public;
- which issuer and event identity it belongs to;
- which exact spans support each proposed field;
- what remains unknown, unavailable, corrected or rights-blocked;
- whether an independent auditor accepted the transition.

This is independently useful before a trade rule exists: Event Intelligence and OpportunityCase can explain adverse company events with correction-safe receipts.

### 8.2 Clock law

| Clock | Meaning | Failure behavior |
|---|---|---|
| `accepted_at` | SEC acceptance timestamp and P0 SEC-source decision clock | missing exact clock refuses primary inclusion |
| `filed_on` | SEC date-only filing label | never promoted to intraday time |
| `document_retrieved_at` | exact archive-byte fetch time | operational provenance only |
| `recorded_at` | receipt durable-store time | never event time |
| `event_occurred_at` | earliest occurrence explicitly stated by source | `UNKNOWN` if silent |
| `earliest_public_source_at` | earlier first-party release time when exactly verified | optional; SEC acceptance is conservative fallback |
| `mitigation_available_at` | first verified mitigation transition | null until exact source |
| `resolution_available_at` | first verified resolution transition | null until exact source |

### 8.3 Evidence-span law

Every populated economic field must have an accepted span carrying:

- source-document ID and content SHA;
- byte/character offsets;
- exact short excerpt;
- field/claim supported;
- extraction method and model/version when applicable;
- auditor verdict;
- correction state.

No model-generated probability or master score is allowed.

### 8.4 Independent economic axes

- event family;
- affected scope;
- new adverse information at t0;
- adverse uncertainty and duration state;
- recoverability evidence type;
- asset integrity;
- quantified production/revenue/cash impact;
- balance-sheet/covenant/liquidity risk;
- financing/dilution need;
- mitigation state;
- resolved-before-disclosure state;
- management control locus;
- disclosure lag;
- evidence completeness;
- rights and reconstruction state.

`intent_orchestration` is fixed to `UNKNOWN` and excluded.

### 8.5 Typed nulls

`UNKNOWN`, `UNAVAILABLE`, `RIGHTS_BLOCKED`, `NOT_APPLICABLE`, `EXPLICIT_NONE`, `ABSENT_IN_SEARCH_SCOPE`, `CORRECTED`, and `QUARANTINED` remain distinct. No null becomes zero, “safe,” “temporary,” or “no impairment.”

### 8.6 Correction behavior

- retain original filing and amendment;
- make amendment relationship explicit;
- converge duplicate release/exhibit documents on one transition;
- retain mitigation/resolution as new transitions rather than rewriting the origin;
- preserve SEC corrections/removals as correction edges;
- never mutate a frozen manifest after outcome access; invalidate and rerun under a new version.

## 9. Typed refusal registry

At minimum:

- `INCOMPLETE_QUERY_CELL`
- `FORM_MISMATCH`
- `AMENDMENT_NOT_ORIGIN`
- `FILING_RECEIPT_UNAVAILABLE`
- `ACCEPTED_AT_UNAVAILABLE`
- `DOCUMENT_UNAVAILABLE`
- `SOURCE_HASH_MISMATCH`
- `RIGHTS_BLOCKED`
- `IDENTITY_UNRESOLVED`
- `DUPLICATE_TRANSITION`
- `NOT_AN_ADVERSE_EVENT`
- `RECOVERABILITY_UNSUPPORTED`
- `STRUCTURAL_OR_AMBIGUOUS`
- `DESIGN_TOUCHED`
- `SOURCE_CAPACITY_SHORTFALL`

No refusal is converted to an event or zero.

## 10. Frozen vertical waves

### P0-S0 — deterministic 20-candidate source packet

One independently useful research PR:

- complete and hash query cells;
- select 20 candidates deterministically across all families and controls;
- join exact SEC filing/document receipts;
- emit source packets and typed refusals;
- provide a real machine-readable audit consumer;
- test firewall, clocks, amendments, duplicates, hashes and byte identity.

### P0-S1 — blind semantic pilot

Grok receives only the 20 source packets and proposes evidence-backed transitions. A separate Fable/Opus seat audits every row.

### P0-S2 — full source-manifest extraction

Expand through the frozen candidate order to the source targets. Prices remain absent.

### P0-S3 — freeze and independent audit

Register manifest hash, trial budget, quotas/concentration and source-audit PASS.

### P0-R1 — separate market/counterfactual replay

Only after P0-S3 may a different runner join eligibility, prices, matched-k, synthetic control, placebos, costs and outcomes.

## 11. P0-S0 acceptance proof

- market-data paths physically absent;
- network hosts restricted to official SEC endpoints;
- every query leaf below the cap and fully paginated;
- exact client-side base-form filtering;
- 20 deterministic candidates reproduce byte-identically;
- every accepted candidate has exact CIK/accession/accepted-at;
- every source document has a content hash and archive receipt;
- amendments never silently become origins;
- date-only clock refuses primary inclusion;
- source packet consumer renders typed failures;
- all authority flags false;
- rerun emits identical packet-manifest SHA.

Green CI without 20 real packets through the canonical source path is not completion.

## 12. No-rebuild boundaries

Do not:

- turn `material_8k_events` into a second filing truth store;
- use `_first_seen` as a historical public clock;
- infer Item-2.02 accession by ticker/date;
- store bulk raw filings in Git;
- infer event family from FTS phrase;
- scrape SEDAR+;
- let the model choose candidate order;
- expose market data to extractor/auditor;
- create a Dislocation Score;
- feed Prophet, Radar or Fusion;
- create a second grader or lifecycle store.

## 13. Capability ledger

| Capability | State |
|---|---|
| Price-blind local-source workspace | **PROVEN** |
| Price-blind SEC FTS workspace | **PROVEN** |
| Candidate capacity for five temporary families | **PROVEN** |
| Candidate capacity for both 8-K and 6-K | **PROVEN** |
| Exact SEC filing/document receipt primitives | **BUILT** |
| P0 consumption of canonical document spine | **NOT BUILT** |
| Historical material-event accepted-at join | **PARTIAL** |
| Item-2.02 accession identity in committed store | **BROKEN / STALE SCHEMA** |
| Native Canadian automated public-site lane | **REJECTED BY RIGHTS** |
| Licensed SEDAR+ DDS lane | **NOT CONNECTED** |
| Deterministic complete candidate pool | **NOT BUILT** |
| Audited 20-case source pilot | **NOT BUILT** |
| Frozen ≥120 eligible-event manifest | **NOT BUILT** |
| Any market/model authority | **REJECTED AT BIRTH** |

## 14. Stop condition and exact next action

Turn 5 stops at source-estate adjudication and architecture freeze. Search hits are not promoted to events.

The next vertical slice is:

> Given a frozen query cell, generate 20 deterministic, price-blind candidate packets with exact filing clocks, document identity, content hashes, evidence-span capacity, typed failures and an independent audit consumer.

Only after that P0-S0/S1 pilot passes may the program expand to the full blind source manifest.