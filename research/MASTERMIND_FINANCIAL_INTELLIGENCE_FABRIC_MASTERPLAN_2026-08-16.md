# Mastermind Financial Intelligence Fabric
## Filing Forensics, Fundamental Forensics, Financial Statements, Disclosures, Point-in-Time Data, and Accounting Intelligence

**Status:** Replacement masterplan and program reset  
**Date:** 2026-08-16  
**Program:** `fundamental-forensics`  
**Infrastructure name:** **Mastermind Financial Intelligence Fabric (FIF)**  
**Primary customer product:** **Filing Forensics**  
**Primary intelligence engine:** **Fundamental Forensics**  
**Benchmark:** Calcbench capability parity, followed by product and intelligence superiority  
**Authority at birth:** Evidence, display, and research context only  
**Repository audited:** `mastermindx-market-intelligence/macro`  
**Audit baseline observed:** `main` at `021553985cbe6bf950413c7cb10fc302d05a9633`  
**Current related work observed:** PR #5794 open for FF-0 freshness truth; PR #5799 open for Earnings Intelligence E0; legacy attested-history Wave 0B still blocked on the protected writer credential.

---

# 1. Executive decision

The prior “Calcbench parity” effort must not be discarded, but it must be **reclassified**.

It is not a finished product and it is not close to Calcbench product parity. It is a collection of serious but incompletely activated foundations:

- immutable-evidence and provenance components;
- a governed 50-metric registry;
- a bounded bitemporal query kernel;
- Company Facts occurrence and filing-clock logic;
- disclosure acquisition and diff machinery;
- an attested-history publication design;
- a private current-state projection;
- a thin Filing Forensics page.

The fundamental problem is not that nothing was built. The problem is that the program spent too much effort proving storage, attestation, and safety properties before it proved the central user and machine workflows that justify the system. It then allowed the thin, separate nine-metric customer projection to stand in for the much more capable canonical query machinery.

The correct reset is:

> Build one governed Financial Intelligence Fabric that turns every company filing and earnings event into reversible financial facts, statements, disclosure changes, forensic findings, peer context, and receipt-bearing intelligence packets. Serve that one fabric through Filing Forensics, Fundamental Forensics, Earnings Intelligence, Terminal company analysis, stock dossiers, Neural Web, Mastermind AI, exports, and eventually Prophet shadow research.

“Calcbench parity” remains an **external capability ledger**, not the product name and not the implementation architecture.

The target is not a Calcbench clone. The target is a better system:

- Calcbench-quality source coverage, statements, revisions, disclosures, peer analysis, exports, and point-in-time truth;
- a substantially better change-first product experience;
- explanation of economic significance instead of only grids;
- peer rarity, corroboration, contradiction, catalysts, invalidation, uncertainty, and market-reaction context;
- one intelligence plane that enriches the rest of Mastermind.

---

# 2. Blunt assessment of where the project stands

## 2.1 Where it exists

The customer-facing route exists at:

`/fundamental_forensics.html`

It is labeled **Filing Forensics** in the Research mega-menu, with the description “Find the accounting changes worth reviewing.” The route is not presented as a first-class destination on the public homepage, which helps explain why it is hard to find.

The implementation is spread across:

- `engine/fundamental_forensics/`
- `app/forensics.py`
- `scripts/build_fundamental_forensics.py`
- `scripts/run_fundamental_forensics_wave2.py`
- `templates/fundamental_forensics.html.j2`
- `templates/fundamental_forensics.js`
- `templates/fundamental_forensics.css`
- corresponding generated `site/` files
- `data/fundamental_forensics/`
- `.github/workflows/filing-forensics-sec.yml`
- attested-history workflows and contracts
- tests under `tests/test_fundamental_forensics_*`
- research and AgentOS handoffs for the Calcbench/Filing Forensics program.

## 2.2 What the current customer product actually does

The current broad-universe customer projection is deliberately described in its own source as a **display-only projection**, not the canonical engine.

It currently reduces the world to nine metrics:

1. revenue;
2. gross profit;
3. receivables;
4. inventory;
5. operating cash flow;
6. capital expenditures;
7. operating income;
8. net income;
9. contract liabilities.

It currently runs five broad detectors:

1. margin compression;
2. receivables stretch;
3. inventory build;
4. rising capital intensity;
5. rising accruals.

It generally compares a latest available period with a prior-year matched period, retains a limited recent history, and can attach a bounded disclosure comparison for a small fixed issuer set.

That is a useful prototype. It is not a financial intelligence platform, a filing research workstation, or Calcbench parity.

## 2.3 What the deeper infrastructure already does

The repo has more valuable machinery than the page reveals:

- a governed 50-metric closed-world registry with direct and formula metrics;
- explicit mapping and formula rule versions and digests;
- a deterministic bitemporal query kernel;
- required source-event and system-recorded cutoffs;
- three query policies: as reported, latest known as of a historical cutoff, and latest restated;
- bounded cell counts and explicit query limits;
- cell-level provenance including accession, source URL and digest, concept, taxonomy, unit, period, rule IDs, rule digests, and formula dependencies;
- an immutable Company Facts occurrence ledger;
- explicit acknowledgment that Company Facts alone is not the filing package;
- filing-clock joins using SEC submissions;
- disclosure acquisition and accession-aware 10-K/10-Q comparison;
- immutable source bundles and content-addressed evidence;
- private-state delivery;
- an attested-history store, reader, seed, verifier, admission, operator, and publication framework;
- Neural Web context projection.

This is the load-bearing salvageable core.

## 2.4 Production reality

The current production state is materially weaker than the code inventory suggests.

The public summary committed in the repo reports:

- 1,492 companies;
- 1,054 findings;
- source generation time of 2026-07-12.

By 2026-08-16 that snapshot was stale. PR #5794 was created to make current, stale, degraded, and unavailable states visible and to prevent render time from being mislabeled as source freshness. That PR was still open at the time of this audit.

The accession-aware SEC disclosure lane is a fixed 12-company technology-heavy universe. It acquires a bounded set of recent 10-K and 10-Q primary documents and publishes disclosure projections. That is useful for proving the mechanism, but it is not broad company coverage.

The attested-history routes currently serve latest, root, and detail **receipts**. They do not yet expose a general financial statement, normalized metric, peer, disclosure, or bulk query API. The canonical handoff states that no production issuer has passed the complete seed, independent admission, read-only replay, and first-v2-publication sequence.

The Neural Web integration reads a compact current Filing Forensics snapshot. It explicitly identifies the basis as snapshot-not-point-in-time and refuses to leak that snapshot backwards into historical dates. This is safe, but it means the desired historical financial context plane does not exist in production yet.

## 2.5 Honest maturity estimate

These are reasoned estimates rather than mechanically measured percentages:

| Dimension | Estimated maturity |
|---|---:|
| Provenance and temporal foundations | 25–35% of the eventual platform |
| Broad source acquisition and corpus | 10–20% |
| Semantic normalization breadth | 5–15% |
| Calcbench-equivalent customer workflows | 5–10% |
| Cross-Mastermind integration | 5–10% |
| Better-than-Calcbench intelligence product | under 5% |
| Operationally proven, broad, point-in-time production system | under 5% |

The right conclusion is not “start over.” It is “stop mistaking foundation code for completed product, converge the foundations, and re-sequence delivery.”

---

# 3. Benchmark: what Calcbench is actually strong at

The useful benchmark is not Calcbench’s dated interface. The useful benchmark is its end-to-end operating model.

Calcbench combines:

- near-real-time ingestion of filings and earnings releases;
- as-reported financial statements;
- standardized metrics;
- original, latest, revision, and point-in-time views;
- source trace for each number;
- interactive disclosure and footnote search;
- peer and multi-company comparisons;
- segments and breakouts;
- non-GAAP metrics, guidance, KPIs, and earnings-release data;
- API delivery;
- Excel workflows;
- bulk query and export;
- specialist filing, filer, auditor, proxy, compensation, and transaction datasets.

Its moat is not simply downloading EDGAR. Its moat is accumulated semantic normalization, revision lineage, document coverage, quality control, and workflow integration.

Mastermind must eventually match the useful capabilities while exceeding the experience and intelligence.

## 3.1 Capability gap ledger

| Capability | Current Mastermind state | Required target |
|---|---|---|
| Entity and security identity | Partial, spread across systems | Canonical issuer/security/CIK/LEI/exchange identity with historical mappings |
| Filing discovery | Exists in bounded lanes | Broad incremental discovery with explicit acceptance and capture clocks |
| Immutable source archive | Strong foundations | Broad production corpus with replay, DR, rights, and completeness ledgers |
| Raw XBRL facts | Company Facts occurrence ledger exists | Filing-package facts, contexts, dimensions, presentation, calculations, labels, footnotes |
| As-reported statements | Not a first-class product | Full statement tree, filing order, units, scaling, calculations, source trace |
| Standardized metrics | Governed 50-metric core | Material line coverage, domain packs, mapping QA, extensions, industry models |
| Point-in-time and revisions | Strong kernel, weak activation | Production query service, historical replay, original/latest/restated views everywhere |
| Reversible trace | Strong cell provenance design | One-click trace in every UI/API/export surface |
| Filing quality | Five broad detectors | Versioned detector registry, coverage abstention, gold sets, peer rarity |
| Disclosures and redlines | Bounded 12-name lane | Broad topic/section/footnote search, structured blocks, cross-period and cross-peer comparison |
| Earnings releases | Separate program, incomplete convergence | Shared event spine and claim/fact model for release, filing, transcript, slides, guidance |
| Non-GAAP, KPI, guidance | Largely missing here | Structured metrics and reconciliations with source spans and period semantics |
| Derived periods and ratios | Some formulas | Q4 derivation, TTM, fiscal/calendar views, FX/split policy, audited formula catalog |
| Segments and dimensions | Missing as product | Segment/geography/product/customer dimensions and presentation-aware breakouts |
| Peer and bulk analysis | Missing | Saved peer sets, industry baselines, rarity, bulk query, asynchronous exports |
| API | Receipts and private snapshot only | Governed query, document, packet, peer, search, and export APIs |
| Excel | Missing | Same query contract through formula builder and source trace |
| Specialist datasets | Mostly missing | Tax, debt, leases, revenue recognition, SBC, M&A, controls, auditor, proxy, compensation |
| Intelligence integration | Compact snapshot context | Receipt-bearing point-in-time packets to Terminal, dossiers, Neural Web, and research |
| Outcome learning | Missing | Prospective event/outcome ledger and calibrated detector performance |
| User experience | Thin single-company workbench | Push-first discovery, dossiers, grids, documents, peers, alerts, and explainable intelligence |

---

# 4. Why the original program stalled

## 4.1 It used parity as an architecture rather than a benchmark

“Build Calcbench parity” is too broad for an autonomous coding session. It contains dozens of independent products and years of semantic accumulation. Without a frozen vertical slice, the agent can always find another prerequisite.

The program needed explicit user jobs such as:

- “Show the original and restated AAPL revenue values as the market knew them on two dates.”
- “Show every material change in BAC’s latest 10-Q, with exact source proof and peer rarity.”
- “Compare CAT’s latest margins, working capital, guidance, and segment mix with five peers.”
- “Feed a receipt-bearing accounting-change packet into a stock dossier.”

Instead it was allowed to work on generalized parity infrastructure without a near-term product proof.

## 4.2 It placed attestation on the critical path too early

The attested-history system is valuable. It is also a specialized publication-control problem. The program allowed seed credentials, object-store admission, operator packets, and replay proof to dominate the work before a single complete analyst workflow existed.

The corrected law is:

- attestation is mandatory before claiming production point-in-time truth;
- attestation is not allowed to block fixture-backed query contracts, golden issuer packets, mapping QA, or product design;
- no live production surface may silently fall back from attested to unattested data;
- the two lanes proceed independently until promotion.

## 4.3 The product projection bypassed the canonical engine

The canonical query machinery supports 50 governed metrics, three vintage policies, temporal cutoffs, formula dependencies, and rich provenance.

The customer page is built from a separate nine-metric projection and five-detector loop.

This created the worst possible state:

- the sophisticated engine is invisible;
- the visible product is too weak;
- each can appear “complete” within its own narrow test suite;
- the system does not prove that the same value and receipt flow through UI, API, export, Terminal, and Neural Web.

## 4.4 It lacked a capability maturity ledger

The program repeatedly treated “file exists” or “test passes” as completion. Every capability must instead carry one of these states:

0. **Absent**
1. **Designed**
2. **Code-present**
3. **Fixture-proven**
4. **Production-source-wired**
5. **Live-data-proven**
6. **User-visible**
7. **Measured and reliable**
8. **Scaled and independently closed**

No wave may call a capability complete below the maturity level required by its acceptance contract.

## 4.5 It lacked a product owner and a data owner

Filing Forensics, Fundamental Forensics, Calcbench parity, attested history, earnings, Terminal company analysis, and Neural Web were treated as adjacent workstreams without a single canonical ownership model.

The replacement ownership model is:

- **Financial Intelligence Fabric** owns source, temporal, semantic, query, evidence, and packet truth.
- **Filing Forensics** owns the main customer research experience.
- **Fundamental Forensics** owns deterministic change and anomaly discovery over the Fabric.
- **Earnings Intelligence** owns earnings event truth and its product experience, while consuming and contributing to the shared source/event/fact contracts.
- **Terminal** owns workstation composition and interaction, not financial truth.
- **Neural Web** owns context routing and memory, not accounting calculations or signal origination.
- **Prophet** owns its governed decision path; Financial Intelligence may enter only through context/shadow contracts until independently promoted.

## 4.6 Autonomous sessions were not bounded by stop conditions

The prior sessions were allowed to:

- discover new prerequisites;
- redesign adjacent systems;
- create infrastructure without a user-facing output;
- chase production credentials;
- expand tests and governance indefinitely;
- call documentation or seed scaffolding a phase completion.

Every future handoff must have:

- one primary user or machine capability;
- a strict allowed-file list;
- a strict forbidden-file list;
- fixed fixtures and expected values;
- explicit non-goals;
- measurable acceptance;
- a stop-after-PR rule;
- an exit report separating code-present, production-wired, live-proven, and user-visible.

---

# 5. Strategic reset: one platform, three visible faces

## 5.1 Financial Intelligence Fabric

This is the infrastructure and semantic layer. It is not a separate marketing product.

It owns:

- company and security identity;
- source discovery and immutable source packages;
- source clocks and capture lineage;
- filing and company event identity;
- raw facts and document fragments;
- statements and presentation trees;
- metric normalization and formulas;
- revisions and point-in-time policies;
- disclosures, sections, topics, and footnotes;
- query contracts;
- evidence receipts;
- coverage, quality, and freshness state;
- reusable financial intelligence packets.

## 5.2 Filing Forensics

This is the analyst-facing product.

It answers:

- What changed?
- What is unusual?
- Why might it matter?
- Is it company-specific or industry-wide?
- What changed in the numbers, text, presentation, definitions, or assumptions?
- Where is the exact source?
- What did the market know at the time?
- What would make this benign, bullish, bearish, or unresolved?
- What should the analyst examine next?

## 5.3 Fundamental Forensics

This is the discovery and research engine.

It produces:

- typed accounting and disclosure findings;
- novelty and peer-rarity context;
- deterministic economic decompositions;
- contradiction and corroboration checks;
- evidence-backed hypotheses;
- outcome observations;
- research-grade context packets.

It does not originate trades, scores, or escalations with an LLM.

## 5.4 The benchmark ledger

“Calcbench parity” becomes a maintained capability ledger containing:

- benchmark capability;
- Mastermind owner;
- maturity state;
- issuer and period coverage;
- gold cases;
- source and rights status;
- product surfaces;
- known limitations;
- closure proof.

No vague “parity achieved” claim is allowed. Each ledger row closes independently.

---

# 6. North-star product experience

Calcbench is grid-first. Mastermind should be **change-first, evidence-first, and progressively detailed**.

## 6.1 Home: What Changed Today

The default Filing Forensics landing page should not begin with an empty company search. It should be a ranked research inbox.

Each row or card should show:

- issuer and event;
- filing or earnings event type;
- accepted/published time;
- freshness and coverage state;
- one-sentence human-readable change;
- finding family;
- magnitude and materiality basis;
- peer rarity;
- corroborating and contradicting evidence;
- initial bull, bear, benign, or unresolved framing;
- exact source availability;
- watchlist/portfolio relationship;
- “Open investigation.”

Ranking is a transparent research-priority ordering, not a trading score. It may use deterministic dimensions such as recency, evidence completeness, magnitude, peer rarity, portfolio relevance, and unresolved contradiction. The ordering inputs must be printed.

## 6.2 Company Financial Dossier

A company dossier should contain seven integrated views.

### Overview

- latest event and freshness;
- high-signal changes;
- financial trajectory;
- cash conversion;
- capital allocation;
- balance-sheet pressure;
- dilution and capital structure;
- guidance and KPI state;
- peer position;
- open contradictions;
- upcoming catalysts;
- source coverage.

### Statements

- income statement;
- balance sheet;
- cash flow;
- equity statement;
- as reported versus standardized;
- quarterly, annual, cumulative, combined, TTM, and derived Q4;
- original, latest known as of a date, and latest restated;
- native and converted currency;
- inline revisions;
- source trace on every cell.

### Changes

- numeric changes;
- presentation and reclassification changes;
- tag and definition changes;
- revision history;
- detector findings;
- peer rarity;
- materiality decomposition;
- analyst review state.

### Disclosures

- sections and footnotes;
- added, removed, and rewritten text;
- semantic topic search;
- exact redline;
- prior and current source;
- accounting policies and estimates;
- risk factors;
- controls;
- debt and covenant language;
- legal, customer, supplier, and geographic concentration.

### Earnings

- release, filing, slides, transcript, and market reaction in one event;
- GAAP and non-GAAP results;
- reconciliation bridges;
- guidance history;
- KPI definitions and changes;
- segment and product commentary;
- management claims and exact citations;
- analyst challenge and unanswered questions.

### Peers

- saved and automatic peer sets;
- standardized metrics;
- distributions and percentiles;
- company versus sector trend;
- peer rarity for every finding;
- common-driver versus idiosyncratic change;
- read-through candidates.

### Sources

- source package and manifests;
- accession and filing metadata;
- exact document fragments;
- XBRL facts and contexts;
- transformation lineage;
- mapping rule and formula versions;
- receipt and quality exceptions;
- download/export.

## 6.3 Filing and Document Explorer

This surface should combine:

- document tree;
- rendered filing;
- structured facts;
- footnotes;
- table extraction;
- disclosure blocks;
- prior-period diff;
- search by exact text, concept, topic, or section;
- source-linked number selection;
- analyst annotations;
- export to notebook, CSV, or Excel.

A user should be able to click a number in a statement and see:

1. the standardized metric;
2. the as-reported line;
3. the XBRL concept and context;
4. the filing table;
5. the source document span;
6. prior vintages;
7. mapping and formula rules;
8. related disclosures;
9. peer values.

## 6.4 Peer Lab

Peer Lab should support:

- custom peer groups;
- index, sector, industry, and business-model groups;
- point-in-time membership;
- fiscal and calendar alignment;
- multiple metrics and periods;
- distributions, ranks, and change rates;
- source trace;
- common-driver detection;
- filing-change comparison;
- asynchronous bulk jobs;
- saved views and alerts.

## 6.5 Mastermind AI financial research

Natural language should sit on top of deterministic contracts.

Examples:

- “Show AAPL revenue and gross margin as the market knew them on 2025-02-01.”
- “Which software companies added material customer-concentration language this quarter?”
- “Compare CAT working-capital deterioration with its peer group.”
- “Find companies whose non-GAAP reconciliation excluded a new expense category.”
- “Show every source behind this conclusion.”

The model may:

- translate intent into a governed query;
- retrieve evidence;
- organize findings;
- explain deterministic calculations;
- surface uncertainty;
- generate a cited research narrative.

The model may not:

- invent a metric;
- calculate from ungoverned values;
- fill missing data;
- infer a source citation;
- originate a trading signal or numeric confidence;
- present current data as historical point-in-time truth.

---

# 7. Technical architecture

## 7.1 Architecture overview

```
Official and licensed sources
        │
        ▼
Discovery and source acquisition
        │
        ▼
Immutable source packages + manifests
        │
        ├──────────────► Document/fragment index
        │
        ▼
Raw facts, contexts, dimensions, presentation, calculation, labels
        │
        ▼
Canonical event and temporal spine
        │
        ▼
Statement reconstruction + metric semantic layer
        │
        ▼
Revision/PIT query service + disclosure query service
        │
        ▼
Forensic findings + peer context + event/reaction/outcome layer
        │
        ▼
Financial Intelligence Packet
        │
        ├─ Filing Forensics
        ├─ Earnings Intelligence
        ├─ Terminal company analysis
        ├─ Stock dossiers
        ├─ Neural Web
        ├─ Mastermind AI
        ├─ API/export/Excel
        └─ Prophet shadow research
```

## 7.2 Source hierarchy

### Tier 1: primary truth

- SEC submission metadata;
- accepted filing packages;
- filing primary documents;
- Inline XBRL instance, presentation, calculation, definition, and label data;
- exhibits;
- company earnings releases filed as exhibits;
- official company investor-relations documents;
- official proxy statements and comment-letter records.

### Tier 2: official bulk acceleration

- SEC Company Facts;
- SEC Financial Statement Data Sets;
- SEC Financial Statement and Notes Data Sets;
- SEC RSS and filing index feeds;
- XBRL taxonomy files.

These accelerate coverage and backfill but do not replace the source filing package.

### Tier 3: licensed enrichment

- transcripts;
- consensus;
- alternative company KPIs;
- corporate actions;
- security master;
- market reaction data.

Every licensed field must carry rights and redistribution policy.

### Tier 4: derived Mastermind intelligence

- normalized metrics;
- derived periods;
- changes;
- findings;
- peer context;
- explanations;
- outcomes.

Derived records must always reverse to Tier 1 or explicitly identify a lower source tier.

## 7.3 Canonical contracts

The following contracts should become the shared vocabulary.

### `entity_identity.v1`

- issuer ID;
- legal entity name;
- CIK;
- LEI where available;
- ticker and exchange history;
- security IDs;
- fiscal year end;
- domicile;
- SIC/NAICS/GICS or internal industry;
- effective intervals;
- source receipts.

### `source_document.v1`

- document ID;
- issuer/event linkage;
- source class;
- form and exhibit type;
- accession;
- source URL;
- source bytes digest;
- accepted, published, observed, captured, and recorded clocks;
- content type and encoding;
- amendment lineage;
- rights and entitlement;
- package manifest ID.

### `document_fragment.v1`

- stable fragment ID;
- document and section path;
- page/table/row/cell or character span;
- normalized text;
- original text;
- structural role;
- language;
- digest;
- retrieval index references.

### `company_event.v1`

- event ID;
- issuer;
- event family;
- fiscal period;
- report date;
- expected and actual event clocks;
- related filings, releases, slides, transcripts, and reactions;
- supersession and correction links;
- coverage state.

### `raw_fact_occurrence.v1`

- issuer and filing;
- concept and taxonomy;
- value and unit;
- decimals and scale;
- start/end/instant;
- dimensions and members;
- context ID;
- accession;
- source fragment;
- source and recorded clocks;
- occurrence digest;
- amendment and duplicate status.

### `statement_cell.v1`

- statement type;
- presentation path and order;
- as-reported label;
- standardized metric when mapped;
- value, unit, scale, period, and dimensions;
- direct or calculated status;
- formula dependencies;
- source receipt;
- mapping receipt;
- quality state.

### `metric_mapping_rule.v1`

- metric ID;
- industry applicability;
- direct concepts;
- extension patterns;
- labels and presentation constraints;
- dimension rules;
- unit and sign rules;
- validity and availability intervals;
- rule version and digest;
- review owner;
- gold examples and known exceptions.

### `normalized_metric_observation.v1`

- entity;
- metric;
- value;
- unit;
- period;
- fiscal/calendar semantics;
- source-event cutoff;
- system-recorded cutoff;
- query policy;
- direct/formula status;
- complete provenance;
- confidence category based on deterministic coverage, not model belief.

### `disclosure_block.v1`

- document and section;
- disclosure family and topic;
- normalized heading;
- text/table spans;
- entities and accounting concepts;
- prior/current links;
- change classification;
- exact redline;
- source receipt.

### `forensic_finding.v1`

- finding ID and version;
- detector ID and version;
- entity and event;
- finding family;
- state: triggered, clear, not evaluable, missing;
- inputs and rules;
- magnitude and materiality basis;
- novelty;
- peer rarity;
- corroboration and contradiction;
- economic interpretation;
- bull, bear, benign, or unresolved scenarios;
- catalyst;
- invalidation;
- uncertainty and limitations;
- evidence receipts;
- authority class.

### `financial_intelligence_packet.v1`

- entity and event;
- exact query policy and cutoffs;
- important statement cells;
- revisions;
- disclosure changes;
- earnings facts;
- forensic findings;
- peer context;
- coverage and quality;
- source receipts;
- stable content hash;
- intended consumers;
- authority class.

### `market_reaction.v1`

- event and knowable time;
- price, volume, volatility, gap, drift, and peer-relative reaction;
- horizon definitions;
- corporate-action adjustments;
- source and recorded clocks.

### `outcome_observation.v1`

- finding or packet;
- predeclared horizon;
- observed outcome;
- benchmark and peer-relative outcome;
- whether hypothesis was supported, contradicted, or unresolved;
- coverage and censoring;
- immutable append-only record.

## 7.4 Temporal laws

The Fabric must preserve multiple clocks rather than collapse them into “date.”

Required clocks include:

- source published time;
- SEC acceptance time;
- first observed time;
- captured time;
- recorded time;
- normalized time;
- computed time;
- published time;
- superseded time;
- mapping-rule available time;
- detector-rule available time.

Required query semantics:

1. **As reported**  
   Return the value in the selected filing without later revisions.

2. **Latest known as of**  
   Return the latest value that was knowable by both the source-event and system-recorded cutoffs.

3. **Latest restated**  
   Return the most recent accepted restatement, clearly labeled as hindsight.

4. **Original versus revised**  
   Return both values and the accession that changed them.

5. **No implicit current time**  
   Research and replay queries must require explicit cutoffs.

6. **No current snapshot backfill**  
   A present snapshot may not be applied to dates before its capture or availability.

7. **Rules are temporal**  
   A mapping or detector version cannot be applied before its declared availability in historical replay unless the query explicitly requests a retrospective research view.

8. **Rendered time is not source freshness**  
   Page or API evaluation time never substitutes for source, build, or publication time.

## 7.5 Storage design

The implementation should evolve the existing Python, Parquet, object-store, and FastAPI stack rather than trigger a broad rewrite.

### Immutable object plane

Use the existing object-store patterns for:

- filing packages;
- source documents;
- manifests;
- source digests;
- normalized partition snapshots;
- attested publication bundles;
- export artifacts.

Object keys must be content-addressed or immutable by version. “Latest” pointers are convenience metadata and must be published last.

### Columnar analytical plane

Use partitioned Parquet for:

- raw facts;
- contexts and dimensions;
- statement cells;
- normalized metrics;
- revisions;
- disclosure blocks;
- findings;
- market reactions;
- outcomes.

Suggested partition dimensions:

- issuer;
- filing year;
- event family;
- statement family;
- metric family;
- source date;
- system-recorded date.

Do not create a single monolithic all-issuer snapshot.

### Operational metadata plane

A small relational or equivalent transactional metadata store should be introduced only for state that benefits from atomic updates:

- entity identity;
- document/event registry;
- job state;
- coverage state;
- quality exceptions;
- saved user queries;
- export jobs;
- alert subscriptions;
- annotation and review state.

It must not become the immutable source of filing bytes or analytical facts.

### Search plane

Use separate indexes for:

- lexical document search;
- structured section/topic filters;
- semantic retrieval over disclosure blocks;
- numeric and concept lookup.

Search indexes are derived and rebuildable. They are never the source of truth.

## 7.6 Query architecture

The existing `MetricQuery` and governed registry should become the nucleus of a reusable service.

Required service families:

- company statement query;
- normalized metric query;
- original/latest/restated comparison;
- revision history;
- raw fact lookup;
- source trace;
- disclosure and footnote search;
- peer query;
- bulk query;
- event packet;
- finding query;
- export job.

Every query response should return:

- data;
- policy and cutoffs;
- coverage;
- missing/not-evaluable states;
- source and governance receipts;
- registry and rule versions;
- stable response digest;
- cache identity.

Normal company queries should be synchronous and bounded. Large peer and bulk queries should create asynchronous jobs.

## 7.7 Identity and period alignment

A large fraction of financial-data failure comes from identity and period mistakes.

The Fabric must explicitly model:

- issuer versus security;
- ticker changes;
- mergers, spin-offs, and predecessor/successor entities;
- fiscal versus calendar periods;
- 52/53-week years;
- non-calendar fiscal year ends;
- quarter versus year-to-date values;
- derived Q4;
- instant versus duration facts;
- continuing versus discontinued operations;
- native versus converted currency;
- split and share adjustments;
- period comparability and reclassification.

No peer analysis may silently compare incompatible periods.

## 7.8 Quality and exception handling

A data-quality system must report, not hide:

- missing documents;
- incomplete filing packages;
- unsupported taxonomies;
- unmapped extensions;
- duplicate or conflicting facts;
- calculation inconsistencies;
- presentation mismatches;
- period ambiguity;
- unit or scale ambiguity;
- unexpected sign;
- source correction;
- mapping override;
- low peer comparability;
- stale source;
- stale publication;
- entitlement lock.

The system must distinguish:

- zero;
- not applicable;
- not disclosed;
- not captured;
- unsupported;
- not evaluable;
- stale;
- locked.

## 7.9 Security and entitlements

The current separation between public shell, private state, and dedicated attested history is directionally correct.

Required rules:

- no private financial rows in public static assets;
- authenticated, tenant-bounded APIs;
- `private, no-store` on sensitive reads;
- no generic fallback from a dedicated data plane to a shared bucket;
- no source credentials or object keys in receipts;
- export jobs inherit the requesting tenant’s entitlement;
- source redistribution follows rights policy;
- search excerpts cannot bypass document entitlement;
- audit logs for exports, bulk jobs, and sensitive source access.

---

# 8. Forensic intelligence architecture

## 8.1 The output is a typed finding, not a black-box score

A useful finding is not “Accounting Risk Score: 72.”

A useful finding says:

- what changed;
- where it changed;
- how large it is;
- whether the comparison is valid;
- whether peers show the same change;
- what economic mechanisms could explain it;
- what supports or contradicts those mechanisms;
- what scenario would make it bullish, bearish, benign, or unresolved;
- what to monitor next;
- what would invalidate the concern;
- which exact sources support every statement.

Composite scores may exist only as transparent display summaries with printed components, coverage abstention, fixed versioned construction, and prospective evaluation. The primary product should remain finding-first.

## 8.2 Detector families

### A. Earnings quality and cash conversion

- receivables versus revenue;
- inventory versus sales and cost of sales;
- contract assets and liabilities;
- deferred revenue;
- accruals;
- operating cash flow versus net income;
- non-cash working-capital drivers;
- capitalized costs;
- cash taxes and interest;
- one-time cash benefits.

### B. Margin and operating model

- gross, operating, and incremental margin;
- mix shifts;
- pricing versus volume;
- cost capitalization;
- restructuring;
- stock compensation;
- depreciation and amortization;
- R&D and sales efficiency;
- unit economics and KPI changes.

### C. Balance sheet and capital structure

- debt issuance and maturity;
- covenant changes;
- liquidity runway;
- revolvers;
- convertibles;
- preferred stock;
- ATM and shelf activity;
- dilution;
- buybacks;
- dividends;
- pension and lease obligations;
- contingent consideration;
- off-balance-sheet commitments.

### D. Revisions, restatements, and accounting policy

- amended filings;
- retrospective revisions;
- line reclassification;
- tag or definition changes;
- revenue-recognition policy;
- critical accounting estimates;
- reserve changes;
- useful-life changes;
- valuation methodology;
- material weakness and control remediation.

### E. Disclosure and language change

- new or removed risk factors;
- customer and supplier concentration;
- geographic exposure;
- legal and regulatory contingencies;
- cybersecurity;
- going concern;
- covenant language;
- auditor language;
- internal controls;
- segment reorganization;
- accounting-policy wording;
- quantified versus unquantified disclosures.

### F. Earnings release, guidance, and non-GAAP

- new exclusion categories;
- reconciliation drift;
- changed KPI definitions;
- guidance initiation, withdrawal, narrowing, or widening;
- midpoint change;
- implied quarter;
- segment or geographic guidance;
- management claim versus reported fact;
- release versus filing contradiction.

### G. Peer and sector context

- common versus idiosyncratic change;
- percentile and rarity;
- industry accounting conventions;
- fiscal-period alignment;
- read-through;
- breadth of similar disclosure changes;
- sector-wide cost, demand, credit, or inventory cycle.

### H. Cross-source consistency

- filing versus earnings release;
- filing versus transcript;
- current versus prior management claim;
- statement versus footnote;
- reported KPI versus source definition;
- buyback authorization versus actual execution;
- debt disclosure versus cash-flow activity;
- segment commentary versus segment facts.

## 8.3 Materiality model

Materiality should be multi-dimensional and explicit:

- absolute value;
- percentage of revenue/assets/equity/cash flow;
- change versus prior period;
- deviation from historical range;
- deviation from peers;
- effect on key ratios;
- cash versus non-cash;
- recurring versus one-time;
- balance-sheet persistence;
- covenant or liquidity relevance;
- source prominence;
- management emphasis;
- market sensitivity.

No single threshold works across industries.

## 8.4 Peer rarity

Peer rarity is one of the clearest areas where Mastermind can exceed Calcbench.

For each finding:

- define a point-in-time peer set;
- align fiscal and calendar periods;
- compute comparable values and changes;
- report peer coverage;
- place the issuer in the distribution;
- detect common industry movement;
- identify the nearest analogs;
- abstain when comparable coverage is too weak.

Peer rarity must not be confused with predictive significance. It is research context.

## 8.5 Market reaction and outcomes

Every material event packet should be eligible for a prospective reaction record:

- pre-event expectations when licensed and knowable;
- event time;
- gap and immediate move;
- volume and volatility;
- one-day, five-day, 20-day, and predeclared horizon returns;
- sector and peer-relative returns;
- revisions in subsequent filings;
- whether the hypothesized mechanism emerged.

This enables:

- detector calibration;
- false-positive analysis;
- industry-specific thresholds;
- “similar past cases” retrieval;
- eventual Prophet shadow research.

No detector receives live decision authority merely because it has a plausible story.

## 8.6 LLM boundary

LLMs are useful for:

- document routing;
- candidate extraction;
- structured drafting from evidence;
- explanation;
- contradiction discovery;
- analyst question generation;
- natural-language query translation.

Deterministic code must own:

- values;
- periods;
- units;
- formulas;
- revisions;
- point-in-time cutoffs;
- peer statistics;
- materiality arithmetic;
- source trace;
- authority state.

LLM output must be:

- cited;
- bounded to retrieved evidence;
- labeled as interpretation;
- unable to overwrite canonical facts;
- unable to originate a signal, score, rank, sizing, gate, or escalation.

---

# 9. Integration into Mastermind

## 9.1 Filing Forensics

Filing Forensics becomes the primary full-page customer workspace over the Fabric. The existing page is evolved rather than replaced with a parallel product.

The current private-state projection remains a labeled compatibility path during migration. It must never be silently presented as the canonical point-in-time query plane.

## 9.2 Fundamental Forensics sister session

The sister session owns the recovery sequence:

- FF-0 freshness truth;
- FF-1 broad SEC collector;
- FF-2 verified publication;
- FF-3 cross-universe discovery;
- FF-4 signal analysis packet;
- FF-5 detector registry and gold corpus;
- FF-6 market and sector context;
- FF-7 outcomes and Prophet shadow;
- FF-8 scale.

This masterplan does not create a second sequence. It gives those waves a canonical financial-data substrate and clarifies the product destination.

The mapping is:

| Fundamental Forensics wave | Fabric dependency |
|---|---|
| FF-0 | Fabric health and freshness contract |
| FF-1 | Source discovery, package, and event contracts |
| FF-2 | Publication, coverage, and receipt contracts |
| FF-3 | Finding and peer-context contracts |
| FF-4 | `financial_intelligence_packet.v1` |
| FF-5 | Mapping/detector registry and gold corpus |
| FF-6 | Peer sets, market reaction, and context |
| FF-7 | Outcome ledger and historical replay |
| FF-8 | Broad corpus, SLOs, and cost controls |

## 9.3 Earnings Intelligence

Earnings Intelligence is a sibling central lobe, not a data source to duplicate.

Shared ownership:

- Financial Intelligence Fabric owns filing facts, statement semantics, source documents, temporal rules, and reusable packets.
- Earnings Intelligence owns the earnings event workspace, transcript and Q&A intelligence, and event-level product synthesis.
- Both use `company_event.v1`, `source_document.v1`, `document_fragment.v1`, and compatible claim/fact receipts.
- Filing exhibits and earnings releases are acquired once.
- The E1 AAPL event workspace should consume the shared packet rather than define another financial statement schema.

## 9.4 Terminal company analysis

Terminal should render thin, interactive clients over the same services:

- financial snapshot;
- recent changes;
- statement view;
- filing timeline;
- earnings event;
- peer comparison;
- source drawer;
- alert subscription.

Terminal must not fork the metric registry, point-in-time policy, or detector logic.

## 9.5 Stock dossiers

Every stock dossier should receive a bounded packet containing:

- current financial trajectory;
- latest material changes;
- balance-sheet and cash-conversion state;
- guidance and KPI changes;
- peer rarity;
- open contradictions;
- exact source links;
- freshness and coverage;
- authority and limitations.

The dossier narrative should cite packet receipts rather than scrape the Filing Forensics page.

## 9.6 Neural Web and Cognitive Architecture v2

Neural Web should receive two distinct financial dimensions.

### Current research context

- latest receipt-bearing packet;
- current finding states;
- coverage and freshness;
- source trace availability;
- display/context authority.

### Historical point-in-time context

- packet selected by explicit source-event and system-recorded cutoffs;
- mapping and detector versions available at the time;
- no present-day revisions unless explicitly requested;
- no current snapshot leakage.

The Neural Web stores and routes context. It does not recompute accounting truth.

## 9.7 Prophet

Initial integration is shadow-only.

Allowed:

- research context;
- feature logging;
- prospective outcome study;
- explanatory display;
- contradiction and risk context.

Not allowed at birth:

- rank changes;
- score changes;
- sizing;
- gates;
- vetoes;
- attention-floor escalation;
- trade origination.

Any future authority requires:

- explicit feature definitions;
- historical PIT replay;
- leakage audit;
- prospective outcome ledger;
- predeclared horizons;
- calibration and false-discovery control;
- operator/CEO promotion;
- registry and contract amendment.

## 9.8 Other lobes

The Fabric should also become the shared financial source for:

- Capital Structure;
- Biocatalyst dilution and financing analysis;
- Government Revenue issuer financial exposure;
- ownership and insider analysis;
- sector intelligence and peer read-through;
- research reports;
- alerts and watchlists;
- Mastermind AI;
- portfolio research and risk review.

Each consumer receives bounded contracts, not direct access to internal object layouts.

---

# 10. Program lanes and concurrency

The program must run through four coordinated lanes.

## Lane A — Attested production truth

Owns:

- legacy Wave 0B credential correction;
- AAPL seed;
- independent admission;
- read-only operator replay;
- v2 publication driver;
- pointer-last publication;
- production receipts;
- disaster recovery.

It is required for production PIT claims. It does not own product design or financial semantics.

## Lane B — Source, semantic, and query fabric

Owns:

- contracts;
- source packages;
- raw facts;
- statements;
- mappings;
- periods;
- revisions;
- query service;
- search;
- quality and coverage.

## Lane C — Product and delivery

Owns:

- Filing Forensics V2;
- Terminal clients;
- dossiers;
- API;
- exports;
- Excel;
- alerts;
- saved work.

## Lane D — Intelligence and learning

Owns:

- detectors;
- peer rarity;
- economic interpretation;
- event and reaction context;
- outcome ledger;
- Neural Web packets;
- Prophet shadow evaluation.

No lane may redesign another lane’s canonical contract without an explicit cross-lane decision.

---

# 11. Replacement roadmap

Time ranges are sequencing estimates, not promises. Each wave ends with a PR-sized or small series of independently reviewable vertical capabilities.

## FIF-0 — Program reset and control plane

**Purpose:** Stop duplicate construction and establish one truth model.

Deliverables:

- this masterplan;
- canonical naming and ownership;
- machine-readable capability maturity ledger;
- current route/data/workflow map;
- benchmark ledger;
- golden issuer and task set;
- shared contract inventory;
- collision map for open PRs;
- explicit legacy W0A–W8 mapping;
- retirement list for duplicate or superseded projections.

Acceptance:

- every existing component has an owner, maturity state, consumer, and disposition;
- no second product, database, or semantic query model is created;
- all future waves cite the same contracts and golden cases.

## Parallel operator task — Close legacy Wave 0B

This is an operational task, not the first coding handoff.

Required order:

1. correct the protected writer S3 access key ID and paired secret;
2. dispatch the bounded AAPL seed from current main;
3. approve the protected environment;
4. require a genuinely successful run;
5. download the exact run-attempt bundle;
6. run the independent verifier against exact SHA/run/attempt;
7. admit only an exact verified bundle;
8. activate the sealed packet through a separate PR;
9. run packet-bound read-only replay;
10. prove zero writes and zero write attempts;
11. mark W0B complete;
12. begin first v2 publication.

No other session should debug SEC acquisition or build a replacement object store to work around this credential.

## FIF-1 — Golden Financial Intelligence Packet

**Purpose:** Convert existing query and provenance machinery into one reusable, deterministic packet.

Scope:

- hermetic fixture-backed packet;
- exact temporal cutoffs;
- direct and formula cells;
- revisions;
- source and governance receipts;
- coverage and limitations;
- stable content hash;
- no network and no R2 writes.

This is the first execution handoff attached to this masterplan.

## FIF-2 — Read-only financial query service

**Purpose:** Expose the existing governed query kernel as an authenticated reusable service.

Endpoints:

- company statements;
- metric observations;
- original/latest/restated;
- revision history;
- cell trace;
- packet read.

Acceptance:

- same fixture query through Python kernel and HTTP returns identical values, policies, receipts, and digest;
- explicit bounds and cutoffs;
- private, no-store;
- no request-time SEC fetch;
- no implicit current time.

This wave should begin only after FF-0 merges or after its app-route conflicts are reconciled.

## FIF-3 — Golden five issuer vertical slice

**Golden issuers:**

- AAPL — large technology, segments, guidance, extensive XBRL;
- SNOW — software, remaining performance obligations, stock compensation, non-GAAP;
- CAT — industrial cyclicality, dealer inventory, segments, backlog;
- BAC — financial institution statements and credit disclosures;
- GOOGL — dual security identity, segments, capex, AI-related investment disclosures.

For each issuer:

- complete recent 10-K/10-Q package;
- submissions and acceptance clocks;
- raw fact ledger;
- as-reported statement tree;
- standardized core metrics;
- revisions;
- one disclosure family;
- one earnings event linkage;
- one peer set;
- one packet;
- one product golden screenshot;
- exact source trace.

Acceptance is human-reviewed, not only schema-valid.

## FIF-4 — Filing Forensics V2 product MVP

Replace the empty-search-first experience with:

- What Changed Today;
- company dossier;
- statement grid;
- changes;
- disclosures;
- source drawer;
- freshness and coverage;
- saved watchlist view.

Migration rule:

- use the canonical query and packet service;
- label any legacy nine-metric fallback;
- never merge unattested and attested values without provenance;
- no separate V2 database or page family.

## FIF-5 — Cross-universe discovery

Scale to an initial 250-issuer operating universe.

Capabilities:

- incremental filing discovery;
- source package capture;
- statement and metric coverage;
- finding generation;
- peer rarity;
- portfolio/watchlist relevance;
- alerting;
- review queue;
- freshness and coverage operations.

Acceptance:

- daily liveness and dead-man switch;
- no stale-green state;
- bounded processing;
- documented failure recovery;
- source-to-product latency reporting;
- 100% of displayed values traced or explicitly absent.

## FIF-6 — Peer Lab and semantic scale

Scale metric normalization and peer workflows.

Targets:

- 250 issuers with deep gold coverage;
- 1,000 issuers with material core statement coverage;
- broader universe through raw/as-reported fallback;
- industry-specific mapping packs;
- custom peer sets;
- fiscal/calendar alignment;
- bulk query;
- asynchronous export.

Mapping quality is measured by material statement coverage, not concept count.

## FIF-7 — Earnings, non-GAAP, KPI, and guidance convergence

Coordinate directly with Earnings Intelligence E1/E2.

Deliver:

- earnings event linkage;
- release and filing source convergence;
- GAAP/non-GAAP reconciliation;
- KPI definitions and history;
- guidance range and midpoint history;
- filing/release/transcript contradiction;
- event workspace packet;
- market reaction.

No duplicate transcript, event, or company-intelligence store.

## FIF-8 — Specialist accounting and disclosure packs

Each pack has its own schema, gold set, domain review, coverage, and acceptance.

Priority packs:

1. debt, liquidity, covenants, and maturities;
2. stock compensation and dilution;
3. segments and geographic/product dimensions;
4. revenue recognition, deferred revenue, and contract balances;
5. tax and uncertain tax positions;
6. leases and off-balance-sheet commitments;
7. M&A, goodwill, intangibles, and impairments;
8. legal contingencies;
9. internal controls, auditor, and going concern;
10. proxy compensation and governance;
11. financial-institution credit, capital, and liquidity;
12. biotech cash runway, financing, and R&D program disclosure.

## FIF-9 — API, exports, and Excel

One query contract serves all channels.

Deliver:

- documented API;
- Python client;
- asynchronous bulk exports;
- CSV/Parquet/JSON;
- source-linked Excel formulas;
- query builder;
- saved templates;
- push notifications or webhooks.

Cross-surface agreement is mandatory: UI, API, export, and Excel must return the same value, policy, vintage, rule version, and receipt.

## FIF-10 — Neural Web, outcomes, and Prophet shadow

Deliver:

- current and historical PIT context packets;
- event and finding outcome ledger;
- similar-case retrieval;
- detector calibration;
- false-positive analysis;
- Neural Web memory binding;
- Prophet shadow features with zero authority.

Promotion is a separate governed decision.

## FIF-11 — Broad scale and independent closure

Close the program against an advertised capability ledger.

Audit domains:

- source completeness;
- statement fidelity;
- temporal law;
- mapping quality;
- disclosure quality;
- specialist extraction;
- search and query fidelity;
- source reversibility;
- tenant isolation;
- cross-surface agreement;
- latency and liveness;
- cost and capacity;
- recovery and DR;
- analyst UX;
- clean-room boundary;
- prospective outcome integrity.

Only audited rows may be marketed as parity.

---

# 12. Acceptance architecture

## 12.1 Golden user tasks

At minimum, every release train must keep these tasks green:

1. Retrieve the original and later-restated value for a metric.
2. Reproduce what was knowable at a historical cutoff.
3. Open the exact filing source for a displayed cell.
4. Explain a formula cell and every dependency.
5. Show missing, unsupported, stale, or locked states without fabricating a value.
6. Compare an issuer with a point-in-time peer group.
7. Find a changed disclosure and show the exact redline.
8. Build a bounded packet for a stock dossier.
9. Return the same value and receipt through UI, API, and export.
10. Refuse a historical query that would leak a current snapshot.

## 12.2 Data gates

- source manifest integrity;
- exact source bytes and digest;
- accession and clock completeness;
- raw occurrence preservation;
- deterministic duplicate handling;
- statement calculation checks;
- period consistency;
- unit and scale consistency;
- mapping rule version;
- coverage abstention;
- source reversibility.

## 12.3 Intelligence gates

- detector preregistration;
- deterministic inputs;
- explicit not-evaluable state;
- human-reviewed gold cases;
- peer coverage;
- printed materiality basis;
- evidence receipts;
- no LLM-originated numeric confidence;
- no trading authority;
- prospective outcome recording from first live use.

## 12.4 Product gates

- complete normal user journey;
- clear first action;
- progressive disclosure;
- source proof within one interaction;
- visible freshness and coverage;
- no machine-centric labels as primary copy;
- bilingual parity where the parent product requires it;
- keyboard and responsive behavior;
- loading, empty, stale, degraded, locked, and error states;
- live deployment verification.

## 12.5 Operational gates

- source-to-product latency;
- run liveness;
- dead-man switch;
- partial versus complete publication policy;
- pointer-last publication;
- bounded retries;
- fair-access compliance;
- object-store and query cost budgets;
- incident and replay procedure;
- backup and recovery proof;
- last-known-good behavior clearly labeled as degraded.

---

# 13. Target SLOs and quality objectives

Initial targets for normal 10-K, 10-Q, and 8-K workflows:

| Objective | Initial target |
|---|---:|
| Filing discovery after SEC availability | p95 under 2 minutes |
| Source package capture | p95 under 5 minutes |
| Core statement availability | p95 under 10 minutes |
| Initial packet availability | p95 under 15 minutes |
| Normal single-company cached query | p95 under 2 seconds |
| Normal single-company cold query | p95 under 5 seconds |
| Bounded peer query | p95 under 5 seconds |
| Displayed numeric cells with exact trace or explicit absence | 100% |
| Silent stale-green states | 0 |
| Request-time SEC fetches | 0 |
| Historical queries using implicit current time | 0 |
| Production values without policy and cutoff | 0 |
| Cross-surface value/vintage disagreement | 0 accepted defects |
| Source package digest mismatch | fail closed |
| Locked source excerpt leakage | 0 |

Coverage objectives should be declared by issuer tier and data family. “12,000 companies” is not meaningful without depth, period, and source-family coverage.

---

# 14. Anti-rabbit-hole operating law

Every execution handoff must comply with these rules.

## 14.1 One PR, one capability

A PR must name:

- one primary user or machine capability;
- one contract;
- one golden case;
- one acceptance suite;
- one deployment or fixture proof;
- one next handoff.

## 14.2 Capability maturity must be printed

Every handoff and PR must distinguish:

- code-present;
- fixture-proven;
- production-source-wired;
- live-data-proven;
- user-visible;
- measured and reliable.

## 14.3 No prerequisite invention

An agent may not create a new prerequisite merely because it would be architecturally elegant. It must either:

- use the frozen contract and fixtures;
- file the blocker;
- stop.

## 14.4 No duplicate control planes

Without an explicit decision, an agent may not create:

- a second filing UI;
- a second company event model;
- a third financial metric query model;
- another source archive;
- a parallel peer engine;
- another Neural Web financial dimension;
- another earnings workspace;
- a second attested-history bucket;
- a separate financial RAG truth store.

## 14.5 No hidden expansion

Not-in-scope sections are binding. “Small cleanup,” “needed refactor,” and “future-proofing” do not override them.

## 14.6 No production claims from fixture tests

Fixtures prove semantics. They do not prove:

- credentials;
- production source access;
- broad coverage;
- live freshness;
- publication;
- user visibility;
- operational reliability.

## 14.7 No live claims without live receipts

A live claim requires:

- deployed commit;
- source clock;
- build/publication clock;
- endpoint or rendered proof;
- exact issuer/event;
- expected value;
- source trace;
- screenshot or machine receipt where applicable.

## 14.8 Mandatory stop-after-PR

After opening and stabilizing the PR, the session stops. It does not begin the next wave.

---

# 15. Current collision and dependency map

## 15.1 FF-0 PR #5794

At audit time this PR is open and owns changes around:

- `app/forensics.py`;
- `engine/fundamental_forensics/private_state.py`;
- new health contract and engine;
- Filing Forensics template, JS, CSS, and generated site;
- CI registrations;
- R2 delivery-plane evidence receipts.

No concurrent handoff should edit those files until the PR merges or is explicitly superseded.

## 15.2 Earnings Intelligence E0 PR #5799

At audit time this PR is open and owns the E0 capability ledger, program decisions, golden-event architecture, and E1/E2 freeze.

The Fabric must consume its final frozen event and workspace contracts. It must not create another Earnings Intelligence program key or duplicate the E1 AAPL event workspace.

## 15.3 Legacy attested-history Wave 0B

The remaining blocker is an operator credential, not missing SEC acquisition code. No coding session should attempt to solve it by creating another bucket, publisher, or seed path.

## 15.4 Safe first coding area

The safest concurrent first build is a new packet contract and hermetic adapter over the existing query kernel, in new files, without touching:

- app routes;
- current UI;
- private state;
- attested publisher;
- earnings E0 documents;
- shared CI files while FF-0 remains open.

That is why FIF-1 is the first handoff.

---

# 16. Program measurement

## 16.1 Product metrics

- time from landing to useful finding;
- percentage of sessions beginning from What Changed Today versus search;
- source-trace open rate;
- dossier completion rate;
- saved investigation and alert rate;
- peer comparison usage;
- export usage;
- analyst correction rate;
- recurring use by covered issuers.

## 16.2 Data metrics

- source family coverage;
- issuer-period coverage;
- material statement-line coverage;
- extension mapping rate;
- disclosure family coverage;
- segment/dimension coverage;
- revision detection recall;
- source reversibility;
- freshness and publication latency.

## 16.3 Intelligence metrics

- triggered, clear, missing, and not-evaluable counts;
- peer-context coverage;
- analyst-confirmed usefulness;
- false-positive and false-negative review;
- time-to-resolution;
- outcome completion by predeclared horizon;
- detector performance by industry and event type.

## 16.4 Operational metrics

- acquisition success;
- partial and complete bundles;
- cache hit rate;
- query latency;
- object and compute cost;
- queue depth;
- stale/degraded/unavailable time;
- dead-man alerts;
- replay success;
- recovery time.

---

# 17. Risks and mitigations

## Risk: semantic breadth becomes an endless taxonomy project

**Mitigation:** prioritize material statement coverage and user tasks, not raw concept count. Add industry packs behind gold cases.

## Risk: the product becomes another dense database grid

**Mitigation:** make What Changed Today and evidence-ranked investigations primary. Keep grids as a power tool.

## Risk: LLMs create polished but unsupported accounting conclusions

**Mitigation:** deterministic calculation and temporal engines; citation-bound narrative; no ungoverned numeric output; explicit interpretation labels.

## Risk: current snapshot data leaks into historical research

**Mitigation:** mandatory source and recorded cutoffs; current snapshots unavailable before capture; temporal-law tests.

## Risk: earnings and filings build parallel event models

**Mitigation:** freeze shared `company_event`, source document, fragment, and packet contracts before implementation convergence.

## Risk: attestation blocks product progress again

**Mitigation:** independent lanes. Attestation gates live PIT claims, not fixture and shadow product work.

## Risk: product claims exceed coverage

**Mitigation:** visible coverage per issuer, period, source family, metric family, and disclosure family.

## Risk: broad universe overwhelms source and compute capacity

**Mitigation:** tiered coverage, incremental acquisition, partitioned stores, bounded queries, async bulk jobs, measured cost budgets.

## Risk: autonomous agents return to open-ended infrastructure work

**Mitigation:** strict handoffs, allowed files, expected fixture values, stop conditions, maturity labels, and CEO review after every PR.

---

# 18. Decisions frozen by this masterplan

1. There is one Financial Intelligence Fabric.
2. Filing Forensics is the primary customer product.
3. Fundamental Forensics is the deterministic discovery engine.
4. Calcbench is a benchmark ledger, not the product architecture.
5. The current page evolves; no second filing product is created.
6. The existing query and provenance machinery is reused.
7. The nine-metric projection is a compatibility path, not canonical truth.
8. Attested history is the production PIT publication plane, not a separate customer product.
9. Earnings Intelligence remains a central sibling lobe with shared event and evidence contracts.
10. Terminal renders the Fabric and does not fork it.
11. Neural Web receives context and receipts; it does not calculate financial truth.
12. Prophet receives shadow context only until independent promotion.
13. Every displayed value is traceable or explicitly absent.
14. Historical queries require explicit temporal policy and cutoffs.
15. LLMs explain evidence; they do not originate numbers, confidence, or market authority.
16. One PR delivers one bounded capability and then stops.

---

# 19. Immediate sequence

## Next 24 hours

- Review and merge or disposition FF-0 PR #5794.
- Correct the protected attested-history writer credential and begin the exact Wave 0B operator sequence.
- Review and disposition Earnings E0 PR #5799.
- Start FIF-1 in isolated new files.

## Next 72 hours

- Complete FIF-1 golden packet PR.
- Review it against the temporal fixture laws.
- Freeze the final packet schema.
- Issue FIF-2 handoff for the read-only API only after app-route conflicts clear.
- Select the exact AAPL source package for the first production packet.

## Next two weeks

- Complete first production AAPL attested snapshot.
- Expose the query service.
- Build the golden-five source and semantic slice.
- Produce the Filing Forensics V2 experience blueprint against real packet data.
- Replace vague parity status with the maturity ledger.

---

# 20. Definition of program completion

The program is not complete when:

- a route exists;
- a schema exists;
- a seed workflow exists;
- a test fixture passes;
- a private state loads;
- a receipt endpoint responds;
- a page can display five findings.

The program is complete when an authorized analyst can:

1. open What Changed Today;
2. identify a material filing or earnings change;
3. understand the economics and uncertainty;
4. compare the issuer with a valid point-in-time peer set;
5. inspect original and revised statements;
6. trace every number and narrative claim to exact source evidence;
7. reproduce what was knowable at a historical cutoff;
8. export the same values and receipts through API and Excel;
9. see the same packet in Terminal and the stock dossier;
10. rely on visible freshness, coverage, and quality;
11. have the finding recorded for prospective outcome evaluation;
12. do all of this across an advertised, audited issuer and dataset universe.

That is the minimum standard for calling the Financial Intelligence Fabric a mature Mastermind organ.

---

# Appendix A — Initial source and evidence register

## Repository sources

- `agentos/workstreams/WS-CALCBENCH-FILING-FORENSICS-PARITY.md`
- `agentos/handoffs/CALCBENCH-FILING-FORENSICS-PARITY-2026-08-16.md`
- `research/CALCBENCH_FULL_PARITY_PROGRAM_AND_WAVE_2_BUILD_DOCKET_2026-08-01.md`
- `research/CALCBENCH_FUNDAMENTAL_FORENSICS_ENGINE_ASSESSMENT_AND_BUILD_DOCKET_FOR_FABLE.md`
- `engine/fundamental_forensics/metric_registry.py`
- `engine/fundamental_forensics/query.py`
- `engine/fundamental_forensics/companyfacts_ledger.py`
- `engine/fundamental_forensics/disclosure_projection.py`
- `engine/fundamental_forensics/context_projection.py`
- `engine/neuralweb/context_api.py`
- `scripts/build_fundamental_forensics.py`
- `scripts/run_fundamental_forensics_wave2.py`
- `.github/workflows/filing-forensics-sec.yml`
- `app/forensics.py`
- `templates/fundamental_forensics.html.j2`
- `data/fundamental_forensics/public_summary.json`
- `config/fundamental_forensics/wave2_targets.v1.json`
- `config/mastermind_programs.yml`
- `research/DO_NOT_REBUILD.md`

## Official benchmark sources reviewed

- Calcbench home and product overview
- Company Detail guide
- Earnings release data guide
- Interactive Disclosures guide
- Data sets guide
- Multi-Company guide
- API guide
- Excel Add-in guide
- Calcbench knowledge base and guides index

## Official primary-source references reviewed

- SEC EDGAR APIs
- SEC Inline XBRL resources
- SEC filing RSS and structured disclosure feeds
- SEC Financial Statement Data Sets
- SEC Financial Statement and Notes Data Sets
- SEC fair-access guidance

---

# Appendix B — Initial golden cases

## Temporal fixture

`tests/fixtures/fundamental_forensics/companyfacts_versions.json`

Required truths include:

- 2023 revenue originally reported as 1,050;
- the same 2023 period later appears as 1,060 in the 2025 filing;
- the later value must not appear before its source and recorded cutoffs;
- duplicate original occurrences must resolve deterministically;
- extension facts remain explicit and are not silently mapped.

## Golden issuer set

| Issuer | Primary stress case |
|---|---|
| AAPL | original/restated statements, segments, capex, earnings event |
| SNOW | RPO, stock compensation, non-GAAP, KPI definitions |
| CAT | cyclicality, inventory, backlog, segments, peer read-through |
| BAC | bank statements, credit, capital, liquidity, disclosures |
| GOOGL | identity, segments, capex, dual security, earnings linkage |

---

# Appendix C — Capability maturity template

```yaml
capability_id: statement_query
owner: financial-intelligence-fabric
benchmark: calcbench-company-detail
state: fixture_proven
issuer_coverage:
  deep: 1
  production: 0
period_coverage: fixture_only
source_families:
  - companyfacts_fixture
product_surfaces: []
receipts:
  - tests/test_financial_intelligence_packet.py
blockers:
  - production query endpoint absent
  - first attested issuer not admitted
next_gate: production_source_wired
```

This format should replace prose claims such as “mostly complete.”
