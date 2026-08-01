# Calcbench Full-Parity Program

## Clean-room product, data, semantic, delivery, and QA roadmap for MastermindX

| Field | Value |
|---|---|
| Status | Canonical active full-parity program |
| As of | 2026-08-01 |
| Current build | Wave 2 — accession source spine and disclosure intelligence |
| Audience | MastermindX, Fundamental Forensics, Neural Web, Prophet, product, data engineering |
| Canonical file | `research/CALCBENCH_FULL_PARITY_PROGRAM_AND_WAVE_2_BUILD_DOCKET_2026-08-01.md` |
| Relationship to prior memo | Keeps the prior clean-room architecture and cost analysis, but supersedes its narrow product-scope exclusion. Full functional parity is now the operator objective. |
| Authority boundary | Context and review-priority only. No new ranking, sizing, gating, or trading authority. |

---

## 0. Decision

MastermindX will pursue **full functional parity with Calcbench over data we can lawfully source and normalize**, while building a better user experience and a proprietary interpretation layer.

“Full parity” means all four systems are in scope:

1. immutable filing and document corpus;
2. versioned normalization, point-in-time, revision, derivation, and QA engines;
3. analyst workbenches, query API, exports, alerts, and Excel delivery; and
4. specialist footnote, dimensional, non-GAAP, proxy, filer, and industry datasets.

It does not mean copying Calcbench code, proprietary mappings, protected API output, branding, or interface geometry. The implementation is clean-room and evidence-first.

The current public Calcbench catalog exposes:

- 1,460 standardized metrics: 152 face-statement, 1,277 footnote, and 31 ratios;
- 66 XBRL note categories;
- 24 10-K/10-Q section categories;
- 9 non-XBRL disclosure types;
- 31 8-K item categories; and
- 25 dimensional breakout families.

The live MastermindX v1 owns a premium single-company workbench, nine normalized US-GAAP metrics, five deterministic detectors, a private R2 state plane, and context-only Brain/Neural Web reads. That is the launch pad, not parity.

---

## 1. Parity ledger

| ID | Calcbench capability | Current MastermindX state | Required parity build | Difficulty |
|---|---|---|---|---:|
| P1 | Company, entity, security, SIC/NAICS, index, peer, and portfolio master | Partial ticker/CIK/sector metadata | Bitemporal entity-security-universe ledger and historical memberships | Medium |
| P2 | Recent-filings feed with readiness and latency receipts | Company submissions source only | Accession-complete manifest, related documents, processing clocks, filters, alerts, export | Medium |
| P3 | Immutable filing/document corpus | Company Facts and Submissions JSON only | Primary HTML, exhibits, XBRL packages, proxy, 8-K, comments, checksums, corrections | High |
| P4 | Raw XBRL query | Company Facts projection collapses contexts/dimensions | Facts, contexts, units, dimensions, concepts, relationships, source spans, duplicates | High |
| P5 | As-reported statements | Compact normalized period table | Presentation order, filed labels, extensions, OCI/equity, calculated Q4 status, per-cell trace | High |
| P6 | 1,460 standardized metrics and ratios | Nine metrics | Versioned mapping DSL, derivation DAG, confidence tiers, exception queue, sector rules | Very high |
| P7 | Original/latest/PIT/revision views | First/latest kernel slice | Full source, system, rule, computation, and publication clocks plus typed lineage | High |
| P8 | Reversible source trace | SEC index and Company Facts links | Number to formula to facts to exact filing/table/text span | High |
| P9 | Filing-quality metadata | Narrow repair collectors | Unified sign, scale, date, DEI, duplicate, extension, revision, and parser QA engine | High |
| P10 | Interactive disclosures and redlines | No filing text corpus in v1 | Normalized HTML, section taxonomy, table/paragraph spans, search, alignment, structural diff | High |
| P11 | Non-XBRL earnings, non-GAAP, KPI, and guidance data | Separate narrow collectors | Release/exhibit table parser, definition identity, ranges, reconciliation, preliminary/final linkage | Very high |
| P12 | Generalized Q4, TTM, ratio, calendar/fiscal, FX, and split calculations | A few projections and five formulas | Typed period algebra and vintage-aware dependency DAG | High |
| P13 | Segments and specialist breakouts | Narrow geography collector | Axis/member identity graph and 25 registered dimensional datasets | Very high |
| P14 | Multi-company, bulk query, analytics, API, exports, and Excel | One private state endpoint | Query plane, peer grids, common-size analytics, jobs, formulas, trace, refresh, notifications | High |
| P15 | Filer, auditor, proxy, and compensation suite | Absent | Issuer QA portal, audit flags/fees, proxy people/entity graph, compensation tables | Very high |

---

## 2. Full product-surface scope

Every surface below remains in the program.

| Product surface | Parity contract |
|---|---|
| Company Dashboard | Filing recency, coverage, data quality, recent changes, saved work, and entry points |
| Company In Detail | As-reported statements, annual/quarterly/cumulative views, original/latest, trace, revisions, and report packs |
| Recent Filings | Whole-universe feed, form/date/company filters, associated documents, readiness, latency, alerts, and export |
| Multi-Company | Peer/portfolio selection, fiscal/calendar/TTM/PIT controls, metrics, aggregates, formulas, trace, and export |
| Bulk Data | Metric-company-period query builder, orientation, aggregates, quotas, and asynchronous exports |
| Analytics | Common-size statements, peer average/median/percentile, and point-in-time universe receipts |
| Interactive Disclosures | Section/note/8-K taxonomy, search, list/table views, prior-period comparison, structural redline, and export |
| Segments | Operating/geographic segments and all 25 breakout datasets with dimension/member trace |
| Raw XBRL | Fact, tag, context, unit, dimension, relationship, period, and source-span query |
| Earnings Data / Model | Earnings releases, non-GAAP, KPIs, guidance, preliminary/final reconciliation, and modeling views |
| API | Companies, filings, statements, mapped metrics, raw XBRL, disclosures, non-XBRL, dimensions, and specialist datasets |
| Excel | Standardized, raw, dimensional, and disclosure functions; dynamic arrays; source trace; statement download; refresh |
| Filer Portal | Filing quality, extensions, revisions, validation, and issuer/auditor workflow |
| Professional suite | Auditor flags/fees, M&A/PPA, compensation, ownership, custom queries, alerts, and institution workflows |

---

## 3. Wave 2 — source spine, trace, disclosure, and single-name parity

### Objective

Make a MastermindX finding reversible to an accession, filing document, comparable section, exact source span, and deterministic redline.

### Build lanes

#### W2-A — accession document spine

- canonical filing manifest;
- accepted, filed, observed, recorded, parsed, and published clocks;
- accession/amendment/related-document lineage;
- immutable content-addressed primary documents and receipts;
- SEC archive URLs, ETag/Last-Modified, checksums, and byte lengths;
- atomic writes, corruption repair, retry, pacing, and missing-document states;
- bounded CLI collection kept off the render path.

#### W2-B — disclosure corpus

- normalized filing HTML/text without losing source coordinates;
- stable heading, paragraph, list, and table objects;
- common 10-K/10-Q section classification;
- accounting-policy, risk-factor, MD&A, controls, auditor, and going-concern topics;
- exact char/byte spans and bounded source excerpts;
- content-derived IDs and deterministic serialization.

#### W2-C — structural diff and qualitative detectors

- comparable prior/current section alignment;
- moved-text and boilerplate suppression;
- additions, removals, replacements, and numeric-edit preservation;
- KPI disappearance;
- revenue-recognition/accounting-policy change;
- risk-factor material wording change;
- auditor change;
- ICFR/material-weakness change;
- benign explanations, limitations, and review-priority states;
- no LLM-originated fact or intent claim.

#### W2-D — premium product integration

- disclosure and revision views in Filing Forensics;
- current/prior/redline presentation with topic filters;
- exact SEC receipts reachable in two interactions;
- new findings in the existing ranked review queue;
- bounded context-only Brain and Neural Web summaries;
- private R2 transport, entitlement, no-store, and no-public-payload boundaries unchanged;
- bilingual, keyboard-safe, mobile-safe progressive disclosure.

### Wave 2 exit gates

1. Manifest and document persistence are deterministic and idempotent.
2. Amendments and source revisions never overwrite history.
3. Supported section extraction reaches at least 98% precision on the frozen fixture/gold sample.
4. Moved paragraphs are not emitted as delete-plus-add.
5. Numeric and negation edits remain visible.
6. Every qualitative finding has current/prior filing identity and exact source evidence.
7. Unknown or inapplicable input produces an explicit not-evaluable state.
8. A user reaches the exact filing evidence within two interactions.
9. Private artifacts remain inaccessible without active `site_full` entitlement.
10. No finding can score, rank, size, gate, or originate a trade.

---

## 4. Wave 3 — normalized query, point-in-time, peers, and analyst workbench

Build after Wave 2 source contracts are stable:

- 150–300 high-confidence core metrics and all eligible ratios;
- A–C mapping rules plus reviewed extension queue;
- generalized Q4, TTM, calendar/fiscal, ratio, split, and FX DAG;
- true original/latest/as-of query policies;
- company/peer/universe snapshots;
- Multi-Company, Bulk Data, Analytics, and cross-company disclosure search;
- saved screens, peer groups, portfolio research lists, and filing alerts;
- authenticated query/export API with deterministic pagination and receipts;
- CSV, XLSX, and Parquet export jobs;
- Office.js formula-builder design bound to the same query contract.

Wave 3 does not promote forensics into alpha authority. Peer rarity and common-size context remain descriptive until separately measured and ruled.

---

## 5. Wave 4 — specialist and professional-suite parity

All previously excluded capabilities are explicitly in scope as vertical subprograms:

1. operating and geographic segments;
2. the 25 dimensional breakout families;
3. tax, leases, debt instruments, pensions, fair value, derivatives, and investments;
4. M&A/PPA, goodwill/intangibles, restructuring, and concentration;
5. banking, insurance, REIT, energy, utilities, and other industry ontologies;
6. earnings releases, non-GAAP, KPIs, guidance, and preliminary/final reconciliation;
7. auditor fees/flags, controls, proxy, executive/director compensation, and ownership;
8. Raw XBRL Query and Filer Portal;
9. full API, bulk exports, notifications, audit logs, and syndication controls;
10. Excel add-in, statement download, source trace, dynamic arrays, and web spreadsheet;
11. custom-query and institution/issuer workflows.

Each specialist family ships as a registered dataset with its own schema, coverage, QA, and acceptance sample. No anonymous giant dimensional table and no forced comparability.

---

## 6. The 25 breakout-family backlog

1. Operating segments
2. Geographical segments
3. Deferred tax assets
4. Deferred tax liabilities
5. Income-tax reconciliation
6. Effective-tax reconciliation
7. Fair value
8. Pension fair-value assets
9. Fair-value asset Level 3 rollforward
10. Fair-value liability Level 3 rollforward
11. Debt instruments
12. Derivatives and hedging
13. Non-option equity compensation
14. Options by exercise-price range
15. Discontinued-operation disposal groups
16. Intangible assets
17. REIT Schedule III real-estate holdings
18. Customer concentration
19. Supplier concentration
20. Business-combination consideration
21. Purchase-price allocation
22. Acquired intangible assets
23. Equity-method investments
24. Business-combination dataset
25. Pensions

---

## 7. Program acceptance suite

| Gate | Requirement |
|---|---|
| Corpus integrity | Frozen 200-issuer/form sample matches SEC manifests; selected accession documents are complete, checksummed, idempotent, and politely retrieved. |
| Raw fact trace | Sampled facts preserve accession, raw token, transformed value, context, unit, dimensions, scale/sign, source span, and SHA-linked object. |
| Statement fidelity | Presentation order, labels, periods, and filed values match SEC rendering; Q4 is visibly derived. |
| Temporal law | Preliminary filing, amendment, recast, correction, rule revision, 53-week, and stub cases show zero future-source leakage. |
| Mapping quality | A–C values achieve at least 99% agreement on the blinded gold corpus; ambiguity returns review/unknown. |
| Disclosure quality | Supported section precision reaches at least 98%; redlines pass moved-text, table, boilerplate, heading, numeric, negation, and duplicate-Inline-XBRL cases. |
| Query fidelity | Fiscal/calendar/TTM/original/latest, aggregates, filters, and peer statistics match frozen direct calculations. |
| Specialist extraction | Every result includes source span/table identity, parser version, confidence, and coverage; low confidence never masquerades as a normalized fact. |
| API/export | Authorization, quotas, schema versions, pagination, receipts, no-store, and CSV/XLSX/Parquet round trips pass. |
| Workflow/UI | Company to filing to finding to exact source in two actions; prior/current comparison; original/latest; mobile, keyboard, and bilingual parity. |
| Multi-user security | Saved objects are tenant-scoped; private artifacts have no static public URL; exports expire and are recipient-bound. |
| Excel | Windows/Mac/Web workbooks pass custom functions, arrays, refresh, trace, original/latest, and unavailable-data states. |

---

## 8. Source and rights boundary

| Input | Clean-room availability | Boundary |
|---|---|---|
| SEC filings, exhibits, proxy, comment letters, and 13F | Public EDGAR | Preserve SEC source history and follow user-agent/rate rules. |
| Company Facts and Submissions | Public SEC APIs | Useful accelerator, not the canonical long-tail/context store. |
| Financial Statement and Notes datasets | Public SEC datasets | Monthly flattened accelerator; raw source evidence remains canonical. |
| Inline XBRL, schemas, linkbases, and rendering | Public filing packages | Parsing is tractable; semantic normalization remains our work. |
| Earnings releases attached to SEC filings | Usually public | Does not guarantee complete real-time wire coverage. |
| Non-filed releases, wire feeds, transcripts, and slides | Source-dependent | Obtain permitted sources or licenses; do not assume free redistribution. |
| Calcbench API and normalized outputs | Separate vendor agreement | Do not use as a backend or redistribute without explicit rights. |
| Calcbench mappings, internal QA, and source code | Proprietary | Recreate behavior clean-room from public sources; do not copy internals. |

---

## 9. Product advantage and moat

Parity is the floor. MastermindX’s differentiated layer is the evidence-ranked interpretation graph:

- every number and text change is reversible to source;
- changes are ranked by review value, not dumped into a grid;
- benign alternatives and missing evidence are printed;
- filing evidence joins existing market, ownership, event, and operating context;
- findings accrue outcomes and calibration without leaking into trading authority;
- the interface is fast, plain-language, bilingual, and mobile-native.

The moat is therefore not storage and not a 500-million-row headline. It is the compound asset created by immutable filing history, versioned semantic rules, correction lineage, analyst exceptions, calibrated detector outcomes, and cross-system context.

---

## 10. Immediate shipping order

1. Accession manifest and immutable primary documents.
2. Section corpus, source spans, and structural redline.
3. Risk, policy, KPI, auditor, and controls detectors.
4. Disclosure and revision workbench views.
5. Recent Filings plus processing-latency receipts.
6. First 50 core metrics and exact cell trace.
7. Multi-company/PIT query plane.
8. Specialist verticals and Excel delivery.

This order maximizes user value while preserving the only sequence that makes full parity trustworthy: **source first, semantics second, delivery third**.

---

## 11. Wave 2 pre-ship implementation checkpoint

The first production slice now implements:

- an accession-aware 10-K/10-Q manifest with acceptance, filing, recording, and compute clocks;
- bounded SEC acquisition with polite pacing, response-size ceilings, failure receipts, immutable compressed documents, checksum repair, and amendment-safe versions;
- a content-addressed private Research R2 snapshot whose latest pointer commits only after object and manifest read-back;
- HTML/Inline XBRL normalization with exact Unicode/UTF-8 spans, generic SEC Item boundaries, tables, paragraphs, headings, and hidden-XBRL exclusion;
- structural alignment, move/boilerplate suppression, numeric edits, bounded redlines, and five deterministic review detectors;
- balanced current/prior source excerpts and detector-matched redlines in the private Filing Forensics workbench;
- aggregated 10-K and 10-Q change feeds, filing trail, source map, bilingual desktop/mobile UI, and context-only Brain/Neural Web projection;
- fail-closed bootstrap/nightly ordering and private-state credentials delivered to the production API only.

The frozen real-corpus dry run covered SMCI, NVDA, AAPL, MSFT, GOOGL, AMZN, META, TSLA, AVGO, PLTR, AMD, and ORCL:

| Check | Result |
|---|---:|
| Primary filing documents retained | 48 |
| Comparable disclosure tracks ready | 24 of 24 |
| Acquisition status | Complete, no partial issuer |
| Uncompressed response bytes admitted | 128,015,069 |
| Content-addressed private snapshot | About 8.6 MB in the local R2 adapter |
| Private browser state | About 1.56 MB gzip / 11.96 MB decoded |
| Disclosure projections attached | 12 of 12 |
| Targeted regression suite | 507 passed |
| Real SMCI two-filing comparison | About 3.2 seconds |

This checkpoint is not a claim of full Calcbench parity. The 200-issuer gold corpus, 98% supported-section precision gate, broad metric/query plane, specialist datasets, exports, API expansion, and Excel delivery remain program gates for Waves 3–4. Until those are measured, this is a production-capable source/disclosure slice—not a completed parity program.
