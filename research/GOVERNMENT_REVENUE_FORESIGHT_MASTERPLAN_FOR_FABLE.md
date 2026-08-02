# Government Revenue Foresight — canonical product and implementation masterplan for Fable

> **Canonical deliverable.** This is the single build handoff for the Government Revenue Foresight product. If a chat summary, scratch note, competitor screenshot, or older procurement memo conflicts with this file, this file wins until it is superseded in-repo.
>
> **Resume note:** current shipped implementation state and the next-account start sequence live in `research/GOVERNMENT_REVENUE_FORESIGHT_ACCOUNT_HANDOFF.md`.

- **Status:** canonical full-suite masterplan plus implemented W1 and W2 procurement-delta workbench
- **Evidence cut:** 2026-08-01
- **Primary domain:** U.S. federal contracting, defense programs, grants, OTAs, SBIR/STTR, and public-company revenue exposure
- **Initial authority tier:** display/context only; no rank, size, gate, conviction, or trade authority
- **Intended builders:** Fable plus the MastermindX data, Neural Web, Prophet, and front-end lanes

### Implementation snapshot — 2026-08-01

Implemented through Wave 2 with this handoff:

- a keyless USAspending award-search, bounded award-detail, and fully paginated
  transaction-history collector with rail-specific completeness denominators;
- bitemporal award, action, and daily snapshot ledgers with canonical generated-award identity;
- hash-only append-only USAspending collection receipts that bind each official response
  without persisting raw response bodies or credentials;
- a SAM.gov opportunity collector with bounded pagination, retry/backoff, versioned
  notice/revision/attachment ledgers, exact field diffs, attachment hashes, point-in-time
  replay, atomic last-good preservation, and redacted failure receipts;
- a 21-company defense/aerospace entity seed and lag-aware obligation-velocity engine;
- bounded observed-capacity, net award-action flow, concentration, and rule-based
  period-of-performance expiry context;
- separate aggregate/detail/action freshness and explicit sample-coverage disclosure;
- a governed `government_procurement_workspace.v1` delta feed and
  `government_procurement_event.v1` evidence contract, with backend-owned display priority
  explicitly separated from investment rank;
- bounded read-only workspace, event, opportunity, opportunity-detail, and recompete APIs;
- an investor-first three-pane Changes / Opportunities / Recompetes workbench with source
  receipts, exact revision diffs, issuer-transmission limits, keyboard operation, mobile
  sheets, bilingual UI, and compact first-response hydration;
- a serialized 30-minute best-effort SAM lane that publishes every complete health receipt,
  separates quiet polls from alert-worthy semantic changes, folds daily USAspending evidence
  before Neural Web/Prophet readers start, and re-renders after every rebase;
- Synapse/DAG ownership plus display-only Neural Web/Prophet annotations and versioned
  cross-desk links into Filing Forensics;
- live-source validation on 1,936 awards and 34,181 transaction actions with zero ingest
  errors at this evidence cut.

Operational dependency: no `SAM_API_KEY` repository secret was configured at this evidence
cut. The SAM lane therefore ships fail-closed with an honest unavailable/last-good state;
real opportunity polling begins only after a free server-side SAM key is installed. The
public SAM API exposes the latest active version, so the revision ledger captures versions
observed after activation rather than claiming complete pre-activation history.

Still roadmap—not represented as shipped parity:

- SAM archive reconciliation/full historical version acquisition, saved monitors, typed
  user alerts, and capture/research cases;
- grants, subawards, OTAs, SBIR/STTR progression, DIBBS, forecasts, protests, and DoD
  budget-line ingestion;
- audited UEI/CAGE/subsidiary lineage, subcontractor graph, vehicle/IDIQ seat detection,
  and complete active-award enumeration;
- calibrated likely-bidder, award-value, revenue-timing, and beneficiary models;
- issuer filing/transcript reconciliation, forward validation, and any promotion beyond
  display/context authority;
- capture CRM, proposal workflows, partner discovery, user automations, exports, semantic
  retrieval/RAG, and MCP.

This fence is deliberate: the current desk is a real investor workbench with production
refresh machinery and truthful blocked-source behavior, while the remainder of this
document is the clean-room build program for full capability parity and differentiation.

---

## 1. Executive verdict

HigherGov and GovTribe are not protected by an unknowable analytical engine. Their core value is the operational product wrapped around fragmented public records:

1. normalize many inconsistent procurement datasets;
2. resolve agencies, recipients, vehicles, contracts, opportunities, people, documents, and programs into a traversable graph;
3. retain award-action history rather than only the latest award total;
4. provide fast search, filters, saved searches, alerts, and entity dossiers;
5. add deterministic aggregates, similarity retrieval, document extraction, and workflow automation;
6. sell the time saved by making those pieces reliable and usable.

The broad product category is highly reproducible from original code and lawful primary sources. The hard work is not arithmetic; it is entity resolution, document ingestion, revision-aware history, point-in-time correctness, source reconciliation, and daily operations.

### Build verdict

| Dimension | Assessment | Why |
|---|---:|---|
| Federal award and transaction spine | **9/10 cloneable** | USAspending exposes awards, transactions, recipients, agencies, subawards, and bulk downloads without authentication. |
| Opportunity and amendment monitoring | **9/10 cloneable** | SAM.gov exposes public opportunity metadata and documents with an API key; notices have durable identifiers and revision activity. |
| Market rollups and concentration analytics | **9/10 cloneable** | Mostly group-by, sums, shares, changes, and date-window comparisons over normalized records. |
| Capture CRM, alerts, and workflows | **9/10 cloneable** | Conventional application state and event scheduling. It is not our first differentiator. |
| Search and semantic similarity | **8/10 cloneable** | Hybrid lexical + vector retrieval is straightforward once documents and metadata are clean. |
| Likely-bidder and value estimates | **7/10 cloneable** | Feasible, but labels are sparse and the competitors do not disclose enough to reproduce their exact models. We should build calibrated, auditable alternatives. |
| State/local breadth and private contacts | **4–6/10 cloneable** | Fragmented portals, licensing, anti-bot defenses, public-record requests, and manual operations create the real coverage moat. |
| Full competitor parity | **6.5/10 near term** | Breadth is an operations program, not one feature sprint. |
| Superior investor/defense foresight | **9/10 achievable** | Neither product is organized around public-company revenue, funded backlog quality, earnings deltas, appropriations transmission, or signal-system context. |

**Decision:** build an original investor-first system, not a pixel clone and not a generic GovCon CRM. Reproduce the useful *capabilities* from public facts, then win on what the incumbents do not make primary: “what changed, which listed company is exposed, how economically material is it, what evidence supports the link, and when could it reach reported revenue?”

The durable moat should be:

- a versioned public-company ↔ subsidiary ↔ UEI/CAGE ↔ recipient graph;
- an award-action ledger with no look-ahead leakage;
- a budget-line ↔ program ↔ contract ↔ supplier exposure graph;
- evidence-weighted catalyst dossiers joined to filings, transcripts, guidance, and estimates;
- provenance and staleness visible on every claim;
- forward validation of whether procurement changes anticipated revenue, backlog, guidance, or price behavior.

---

## 2. Scope and interpretation

This product is **Government Revenue Foresight**, initially optimized for defense and government-exposed public companies. It is one specialist desk in a reusable **Vertical Intelligence Workbench** federation, alongside the concurrently built **BioCatalyst** desk and future Shipping, Import/Export, and other vertical desks. The desks share a shell, evidence clock, company identity, catalyst envelope, context contract, and cross-desk hub. They do **not** share specialist scoring engines or silently write into one another's state.

The request's isolated reference to a “biopharma niche” is therefore a real federation requirement—not a reason to distort this desk's ontology. Government Revenue owns the procurement/funding facts for NIH, BARDA, DoD medical, SBIR/STTR, and other government activity. BioCatalyst owns the therapeutic-asset, clinical, regulatory, and scientific interpretation. A cross-desk synthesis can join the two without making either desk a submodule of the other.

This is not a promise to infer classified awards, undisclosed subcontract economics, or exact GAAP revenue from public obligations. It is a disciplined system for extracting the maximum defensible forward information from public procurement evidence.

### Product job

For any covered public company, answer in under 30 seconds:

- What changed since the last close, week, quarter, and earnings call?
- Was the change a new award, exercised option, ceiling increase, funded obligation, de-obligation, extension, recompete, protest, budget movement, or merely an announcement?
- Which parent, subsidiary, program, agency, vehicle, and contract family does it belong to?
- How large is the change relative to the company's government-exposed revenue, reported backlog, and prior award pace?
- Is the evidence funded, authorized-but-unfunded, forecast, inferred, disputed, or stale?
- When is revenue conversion plausible, and what facts would confirm or falsify it?
- Does the event add context to a live Prophet/Neural Web thesis without manufacturing a signal?

---

## 3. Evidence fence: observed, inferred, and unknown

Every competitor statement and every MastermindX output must carry an evidence class.

### 3.1 Directly observed

The following were observed in an authorized HigherGov trial session on 2026-08-01 or in current official product documentation:

- HigherGov navigation exposes global search; federal and state/local opportunities; grants; forecasts; DIBBS; pipelines, pursuits, and activities; partner finder; government buyers; labor pricing; market analysis; contract, vehicle, grant, and awardee records; agencies and people; documents; defense/IT/grant programs; classifications; DoD budget; protests; capital markets; downloads, favorites, saved searches, proposals, FOIA, news, API, and MCP-adjacent workflows.
- HigherGov opportunity detail exposes lifecycle, documents, related opportunities, awards, incumbents, bidders, similar records, estimated competition/value, a match percentage, and an AI document assistant.
- HigherGov award detail exposes award hierarchy, status, history/modifications, funding timeline, subcontracting, competition, and simple derived observations such as end-date extensions and ceiling changes.
- One observed award displayed total obligations, current award value, potential award value, funded percentage, funded backlog, and total backlog. The numbers reconciled exactly as subtraction and division, not as a hidden model.
- HigherGov market analysis returns time-series and category rollups of prime awards, subawards, grants, and subgrants; observed outputs reconciled as grouped obligation sums.
- HigherGov's public docs state that it tracks more than 65 million IDVs, prime contracts, subcontracts, and OTAs since 2000 and more than 8 million grants/subgrants. Its [data-source disclosure](https://docs.highergov.com/more/data-sources) names FPDS, FSRS, USAspending, SAM.gov, Grants.gov, DIBBS, SBIR.gov, agency forecasts, DoD budget material, public-record requests, and proprietary analyst work.
- HigherGov's [current pricing](https://www.highergov.com/pricing/) lists Starter at $500/year, Standard at $2,500/year, and Enterprise as custom. Its [API documentation](https://docs.highergov.com/import-and-export/api) lists 10,000 API records/month with every subscription, opportunity refresh around 20 minutes, and contract/grant/awardee refresh daily.
- GovTribe's current public application and documentation expose federal and state/local opportunities, forecasts, awards and transactions, IDVs/vehicles, vendors, agencies, contacts, files, classifications, major defense acquisition programs, labor rates, reports, capture workflows, teaming, saved searches, exports, integrations, AI conversations/projects/memory/skills, event/schedule automations, and MCP.
- GovTribe supports keyword and semantic search. Its [search guide](https://govtribe.com/docs/govtribe-user-guide/guides/choose-a-search-mode-and-write-queries/) explicitly separates structured filters, exact keyword syntax, and meaning-based retrieval.
- GovTribe automations can start from schedules, record changes, saved-search additions, pipeline changes, and pursuit-stage movement. “Instant” saved-search triggers check every 15 minutes according to the [automation guide](https://govtribe.com/docs/govtribe-user-guide/govtribe-ai/automations/).
- GovTribe's published pursuit probability is user-entered; probable value is estimated value multiplied by that user-entered probability. It must not be represented as a predictive win-probability model.
- GovTribe's [current plan guide](https://govtribe.com/docs/govtribe-user-guide/guides/choose-the-right-govtribe-plan/) lists Launch $1,500/year, Launch Plus $1,900/year, Growth $5,000/year, Growth Plus $6,000/year, and Scale custom; AI/MCP/automation usage is credit-metered separately.

### 3.2 Strongly inferred

These are clean-room engineering inferences from visible inputs and outputs, not claims about competitor source code:

- Funding charts, agency shares, vehicle rankings, contractor rankings, “largest” fields, and most market reports are relational aggregations over transactions and dimensions.
- Recompete lists are primarily contract-end/option-window rules joined to related opportunities, vehicle structure, and incumbent history.
- Similar-record features likely use lexical retrieval and/or vector embeddings over title, description, codes, agency, and documents.
- Likely-bidder features likely combine incumbent/parent history, agency/category experience, geography, vehicle access, set-aside eligibility, recency, and semantic fit; they may include a learned ranker, but exact training labels and calibration are unknown.
- Estimated value likely prefers explicit source ranges, then comparable-award distributions conditioned on agency, category, vehicle, and requirement similarity.
- Opportunity summaries and Q&A are retrieval-augmented generation over source notices and attachments, with metadata inserted as structured context.
- HigherGov's observed client is a server-rendered application augmented by Vue 2, jQuery/DataTables, Bootstrap, charts, and server-side search/chart endpoints. GovTribe presents as a more modern Vue-style application. These facts inform interaction design only; they are not a source-code specification.

### 3.3 Unknown until independently validated

- Competitor source code, database schema, private-source contracts, crawlers, prompts, model vendors, feature weights, training data, bidder-model calibration, and human-review procedures.
- Whether any displayed “odds,” match, value, or likely-bidder percentage is empirically calibrated across time and opportunity class.
- Exact competitor state/local source coverage and effective freshness for every jurisdiction.
- Completeness of competitor proprietary contacts, bidder lists, FOIA documents, and private task-order feeds.
- The amount and timing of revenue any public company will recognize from an award. Obligations, ceilings, funded backlog, company-reported backlog, bookings, and GAAP revenue are distinct quantities.

### 3.4 Labeling law

Use these values in research, UI, and machine artifacts:

```text
evidence_class ∈ {source_reported, derived_deterministic, model_estimate,
                  llm_extracted_unverified, analyst_override}
confidence_state ∈ {confirmed, probable, tentative, unresolved, contradicted}
authority_tier ∈ {display, infrastructure, shadow, scored}
```

No LLM-extracted field becomes `source_reported`. No model estimate is rendered as a fact. No competitor inference is documented as observed.

---

## 4. Competitor product-suite map

This table is a functional benchmark, not an instruction to copy names, layouts, code, or proprietary data.

| Capability | HigherGov | GovTribe | MastermindX decision |
|---|---|---|---|
| Global search | Broad cross-record search | Broad cross-record search | Build hybrid identifier/keyword/semantic search with entity-aware facets. |
| Federal opportunities | SAM plus additional boards and files | SAM opportunity graph | Build from SAM, retain every revision and attachment hash. |
| Agency acquisition forecasts | 70+ claimed agency sources in current docs | Federal forecast records | Start with published federal forecast feeds/documents; source registry per agency. |
| State/local opportunities | Very broad claimed SLED collection | Plus-plan SLED coverage | Defer breadth; build source-adapter framework and priority jurisdictions only. |
| DLA/DIBBS and NSN | Dedicated DIBBS and NSN workflows | Less prominent | High-value defense lane after federal spine; join part/NSN to public suppliers. |
| Grants | Opportunities, programs, awards, subgrants | Opportunities, programs, awards | Ingest Grants.gov + USAspending; activate strongly for NIH/BARDA/energy later. |
| Contract awards | Prime, subcontract, IDV, OTA detail | Awards plus transaction history | Core spine; action ledger is mandatory. |
| Subawards | Search and rollups | Prime/subcontract relationships | Build, but label reporting lag and incomplete subcontract visibility. |
| Vehicles/IDIQs | Vehicle search, hierarchy, rankings | IDV profiles, vehicle analysis | Build vehicle → order graph and participation/conversion metrics. |
| Vendor/recipient profiles | 2.2M observed search universe; subsidiaries, people, award history | Rich vendor profiles and relationships | Recenter on listed parent and subsidiary ownership over time. |
| Agency/buyer profiles | Agencies, offices, people, activity | Agencies, buyers, contacts | Build agency/office demand graph; public contacts are secondary. |
| Defense programs | Curated program profiles and awards | Large major-acquisition-program directory | Build program ontology from budget lines, SAR/DAES/public materials, awards, and issuers. |
| DoD budget explorer | Dedicated line-item pages and justification documents | Major program context | Core differentiator: budget delta → program → awardee → listed-company exposure. |
| Classifications | NAICS, PSC, NSN/FSG/NSG, grant programs | NAICS, PSC, NIGP, UNSPSC | Canonical code dimensions with effective dates and hierarchy. |
| Labor pricing | Large searchable rate table | Large GSA labor-rate dataset | Useful for services-company margin/price pressure; Phase 4. |
| Protests | Contract protest reference | GAO protest records | Add protest event lane and contract/opportunity linkage. |
| M&A / capital markets | Dedicated proprietary module | Not a primary emphasis | Consume existing filings/13G/capital-structure work; do not duplicate it here. |
| Documents | Source files, generated summaries, cross-links | Large government file corpus | Immutable documents, OCR/parser, evidence spans, version diffs, RAG. |
| Opportunity fit | Experience filters and AI match | Recommendations and similarity | Separate deterministic eligibility from learned relevance; calibrate both. |
| Similar records | Similar contracts/opportunities | Keyword/semantic and similar-record workflows | Hybrid BM25 + embeddings + structured rerank; show why each match was retrieved. |
| Likely bidders | Potential-bidder lists | Predictive analytics | Build transparent bidder candidate ranker only after ground-truth evaluation. |
| Estimated value | Displayed range/estimate | Predictive value support | Quantile model with comparable set, interval, and coverage diagnostics. |
| Market analysis | Trends, shares, categories, maps, rankings | Funding and vehicle reports | Build investor materiality, acceleration, displacement, and budget-transmission views. |
| New entrants | Fast-growing/partner views, not a distinct observed report | Dedicated new-entrants report | Build new-winner and share-shift detection by agency/category/program. |
| Partner finder | Experience/registration filters, leaders/growth | Teaming tools | Defer capture-focused UI; graph remains useful for prime/sub exposure. |
| Government buyers | Activity-ranked contacts | Buyer profiles | Use buyer activity as demand context, not outreach software. |
| Pipelines/pursuits/tasks | Custom pipeline stages and activities | Mature capture CRM | Minimal watchlists and research cases only; avoid CRM-first scope creep. |
| Saved searches/alerts | Unlimited searches/alerts; daily recommendations | Unlimited saved searches; event automations | Build declarative monitors that emit typed deltas, not generic email noise. |
| FOIA | Managed request workflow | No equally prominent public workflow | Later operations lane; do not ingest competitor-obtained records. |
| Proposal drafting | Opportunity assistant and proposal actions | AI proposal/capture workflows | Not in investor MVP. Reuse document engine if later required. |
| AI Q&A | Opportunity-specific assistant with documents/profile context | Cross-record AI, projects, memory, skills | Evidence-bound research assistant over our own corpus. |
| AI automations | Saved prompts and API/MCP evolution visible in updates | Mature scheduled/event-triggered beta | Use central command/event bus; no parallel scheduler. |
| MCP/API | REST API; current public Government MCP | MCP plus integrations/personal tokens | Expose read-only typed tools after schemas stabilize. |
| Collaboration/integrations | Teams, Zapier, task-order import | Teams, Zapier, Unanet | Coordinate through central command; defer third-party CRM plumbing. |
| Exports | Plan-dependent per-search limits | Plan-dependent per-export limits | Internal JSON/Parquet/API first; auditable CSV export later. |
| Investor materiality | Capital-markets dataset, but capture UI remains dominant | Not product center | **Primary MastermindX advantage.** |
| Earnings/filing context | Not deeply integrated into observed workflows | Not deeply integrated into observed workflows | **Primary MastermindX advantage.** |
| Forward truth ledger | Not externally visible | Not externally visible | **Mandatory MastermindX advantage.** |

### Product scale and cadence snapshot

Treat all vendor counters as marketing/product counters, not audited coverage.

| Product | Publicly represented scale observed 2026-08-01 | Published cadence | Price anchor |
|---|---|---|---|
| HigherGov | 65M+ IDVs/contracts/subcontracts/OTAs since 2000; 8M+ grants/subgrants; authenticated search showed 5.8M contract opportunities, 144.7K forecasts, 3.1M DIBBS records, and 2.2M awardees | Major sources as often as 15 minutes; public API says opportunities ~20 minutes, awards/awardees daily | Starter $500/year; Standard $2,500/year; Enterprise custom |
| GovTribe | Public data-model counters observed: ~87.8M awards, 128.2M transactions, 4.3M federal opportunities, 2.4M vendors, 2.3M IDVs, 9M government files, 897K labor rates, and ~3.1K DoD programs | Federal opportunities as often as 15 minutes; most other core datasets daily; reconciliation/backfills are part of ongoing operations | Launch $1,500/year; Launch Plus $1,900/year; Growth $5,000/year; Growth Plus $6,000/year; Scale custom; AI credits separate |

GovTribe publishes individual data-model pages for [awards](https://govtribe.com/docs/data-model/data-types/federal-contract-award/), [transactions](https://govtribe.com/docs/data-model/data-types/federal-transaction/), [opportunities](https://govtribe.com/docs/data-model/data-types/federal-contract-opportunity/), [vendors](https://govtribe.com/docs/data-model/data-types/vendor/), [IDVs](https://govtribe.com/docs/data-model/data-types/federal-contract-idv/), [files](https://govtribe.com/docs/data-model/data-types/government-file/), [labor rates](https://govtribe.com/docs/data-model/data-types/gsa-labor-rate/), and [DoD acquisition programs](https://govtribe.com/docs/data-model/data-types/dod-acquisition-program/). Recheck counters before any external publication.

---

## 5. UI and workflow teardown

### 5.1 HigherGov

**What works**

- Persistent left navigation makes the very broad suite discoverable.
- Dense filter builder supports serious market slicing.
- Record types cross-link well: opportunity → award → vehicle → incumbent → agency → people → related records.
- Award pages expose hierarchy, funding status, transaction history, documents, and competition in one place.
- The opportunity assistant is scoped to the record and its documents, which is the right evidence boundary.
- Saved searches and pursuit actions are never far from the research surface.

**What fails for our user**

- The layout is capture-manager-first, not investor-first.
- Dense Bootstrap cards, DataTables, tabs, and large unused regions make the important delta compete with static metadata.
- Historical totals are easier to find than “what changed today and why it matters.”
- Match/odds/value labels can look more certain than their public methodology supports.
- Public-company ownership, reporting segments, backlog disclosure, revenue materiality, and earnings timing are not the organizing spine.
- Provenance exists as links, but confidence, revision history, and source conflict are not visually dominant.

### 5.2 GovTribe

**What works**

- The current dark/navy/cyan visual system is modern; describing the whole product as “years out of date” would be inaccurate.
- Global search, profiles, capture, reports, AI, files, and integrations are cleanly grouped.
- Keyword versus semantic search is explained instead of hidden.
- AI is a workspace with projects, memories, files, skills, automations, and MCP—not merely a summary button.
- Event-triggered automations model the correct abstraction: record changes should start typed workflows.

**What fails for our user**

- The primary mental model remains GovCon discovery/capture, not public-market anticipation.
- The user still needs to translate an award or opportunity into listed-parent exposure, financial materiality, backlog quality, and earnings relevance.
- AI workflow breadth can produce polished activity without solving entity-resolution and point-in-time truth.
- Credit metering encourages a chat-centric layer where deterministic precomputation would often be cheaper and more auditable.
- A broad suite means deeper navigation than an investor needs for the daily “what changed?” decision.

### 5.3 Original MastermindX design law

The landing surface is not a database search box. It is a **delta console**:

1. material changes first;
2. affected listed companies second;
3. funding quality and timing third;
4. source evidence on demand;
5. search/exploration after the alert has been understood.

Progressive disclosure should make the first screen usable in 30 seconds and the underlying record auditable in five minutes.

---

## 6. Clean-room boundary

We are building interoperable capabilities from public facts and public-source data—not copying either vendor's protected implementation.

### Allowed

- Observe normal product behavior under authorized access.
- Read public marketing pages, user guides, data dictionaries, terms, API documentation, and official government sources.
- Record high-level workflows, inputs, outputs, and usability lessons.
- Implement original schemas, calculations, models, code, copy, icons, interaction patterns, and visual design.
- Ingest data directly from government or separately licensed sources under their own terms.
- Validate our outputs independently against primary records.

### Prohibited for this build

- Copy competitor HTML, CSS, JavaScript, prompts, text, images, exports, database records, or branded taxonomy.
- Scrape authenticated competitor pages or automate bulk extraction.
- Circumvent export, rate, plan, or access limits.
- Use a competitor API or subscription to recreate a substitute service where its license forbids that use.
- Reuse proprietary bidder lists, contact enrichment, FOIA collections, or inferred values as training labels.
- Claim parity on data families we have not independently sourced and tested.

This is a load-bearing constraint, not boilerplate. HigherGov's [Terms of Service](https://www.highergov.com/tos/) reserve its services/content beyond public-domain material. GovTribe's [Terms of Use](https://govtribe.com/docs/govtribe-user-guide/terms-of-use/) restrict misuse and resale; its published [API license](https://docs.govtribe.com/user-guide/terms-of-use/api-license-agreement) expressly restricts using that API to replicate its user experience. The production system therefore uses government sources and original computation only.

---

## 7. Official-source acquisition matrix

The source registry is a first-class table. Every adapter must declare access method, cadence, revision behavior, license/terms, backfill method, and health checks.

| Source | What it contributes | Access / auth | Target cadence | Known caveat | Initial lane |
|---|---|---|---|---|---|
| [USAspending API v2](https://api.usaspending.gov/) and [endpoint index](https://api.usaspending.gov/docs/endpoints) | Awards, award actions/transactions, recipients, agencies, federal accounts, subawards, obligations, bulk downloads | No auth currently required | Daily delta; weekly reconciliation; monthly bulk backfill | Revisions, reporting lag, duplicated/changed recipient names, subaward quality | **Ship first** |
| [SAM.gov Opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/) | Active notices, award notices, solicitation IDs, NAICS/PSC, set-asides, POCs, resource links | Public SAM API key required | Every 15 minutes; daily active reconciliation; weekly archive reconciliation | Public API returns latest active version; full version history requires Data Services; documents can change | **Ship second** |
| [SAM.gov API catalog](https://open.gsa.gov/api/) | Entity and hierarchy APIs, contract-award access paths | Key and endpoint-specific roles | Daily | Role/access differences; respect quotas | Phase 1–2 |
| [Grants.gov APIs](https://www.grants.gov/api) and [API guide](https://www.grants.gov/api/api-guide) | Grant forecasts, synopses, packages, applicant/agency data | Some endpoints require help-desk-issued key | Hourly/daily by endpoint | API portfolio is split by applicant/grantor functions | Phase 3 |
| [SBIR/STTR data resources](https://www.sbir.gov/data-resources) | Solicitations/topics, awards, firms, phase, amount, abstracts, UEI | Downloads and API; API was under maintenance at evidence cut | Daily availability check; monthly canonical bulk refresh | Newly added awards need at least 24h; annual completeness lag; bulk files refresh monthly | Phase 3 |
| [DoD Comptroller FY2026 budget material](https://comptroller.defense.gov/Budget-Materials/) and service justification books | P/R exhibits, RDT&E lines, procurement quantities, prior/current/request amounts, program narratives | Public HTML/PDF | On release, then weekly during budget cycle | PDF tables, changing filenames, enacted/request/conference values differ | Phase 2–3 |
| [Acquisition.gov FAR/DFARS](https://www.acquisition.gov/) | Acquisition rules, definitions, public forecasts, classification references | Public | Weekly/monthly | Regulatory context, not award truth | Reference lane |
| [GAO bid protests](https://www.gao.gov/legal/bid-protests) | Docket status, solicitation numbers, decisions, protest outcomes and dates | Public pages/search | Daily | Pending filings and underlying pleadings may not be public; redaction delay | Phase 3 |
| Agency acquisition forecasts | Pre-solicitation demand and likely recompetes | Public HTML, XLSX, PDF, portals | Per-source; generally daily check/quarterly release | Highly fragmented schemas and irregular publication | Phase 2 onward |
| DLA DIBBS / public NSN references | Parts, solicitations, awards, national stock numbers | Source-specific public access | 15–60 minutes where allowed | Authentication, pagination, documents, supplier mapping | Defense Phase 4 |
| Federal Procurement Data System references | Contract-action semantics and source lineage | Primarily accessed through official integrated paths/bulk data | Daily | Transition history and corrections | Supporting |
| [SEC EDGAR data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | CIK mapping, filings, XBRL facts, backlog/revenue disclosures where tagged, submission timing | No API key; descriptive User-Agent required | Real time for submissions; nightly bulk reconciliation | Backlog often appears only in text/tables; segment mapping needs documents | **Consume central engine** |
| Issuer filings, transcripts, presentations | Backlog, bookings, program commentary, guidance, risks, customer concentration | Central document/earnings engine | Event-driven | Company definitions differ from federal measures | **Consume, do not recollect** |
| Congressional appropriations and authorization documents | Program authorization/enactment deltas and earmarked priorities | Congress.gov, committee docs, public PDFs | Event-driven during cycle | Authorization is not appropriation; appropriation is not obligation | Phase 3 |

### Source precedence

For any conflicting field:

```text
source record + latest valid action
    > reconciled official bulk record
    > official linked document extraction
    > deterministic derivation
    > model estimate
    > LLM extraction awaiting verification
```

Do not erase conflict. Store every observed value and expose the selected value, selection rule, and conflict state.

---

## 8. MastermindX product architecture

### 8.1 System shape

```text
Official sources
    ↓
Source adapters + immutable raw objects
    ↓
Normalization + revision ledger + document hashing
    ↓
Entity resolution and temporal ownership graph
    ↓
Award/action/opportunity/program canonical graph
    ↓
Deterministic metric marts + model-estimate lane
    ↓
Government Revenue Foresight API/static artifacts
    ├── Investor-facing command page
    ├── Company/program/award dossiers
    ├── Neural Web context artifact
    ├── Prophet evidence context
    └── Central command events/automation
```

### 8.2 Storage layers

| Layer | Contract | Mutation law |
|---|---|---|
| Raw | Original response/file bytes, request metadata, content hash, source timestamp | Append-only; never overwrite |
| Normalized | Typed source-native rows with parser version | Rebuildable; retain `valid_from`, `valid_to`, and source revision |
| Canonical graph | Resolved entities and edges with provenance/confidence | Versioned; analyst overrides are additive and attributable |
| Metric mart | Point-in-time company/program/agency metrics | Recomputed from canonical ledger; snapshot by `as_of` |
| Event stream | Typed changes between valid snapshots | Append-only with deterministic dedupe key |
| Display artifact | Small JSON contracts for site and agents | Atomic publish; last-good fallback with explicit stale state |
| Forward ledger | Predictions/context states and later outcomes | Append-only shadow record; no retrospective edits |

### 8.3 Core services

1. **Collector registry** — one adapter contract, source health, cursor, quota, retry, checksum, and backfill.
2. **Revision engine** — field-level diffs between versions; distinguishes correction, amendment, new transaction, and source deletion.
3. **Entity resolver** — exact identifiers first, curated aliases second, conservative probabilistic candidates third.
4. **Temporal ownership graph** — public parent, subsidiary, joint venture, recipient, UEI, CAGE, and effective ownership dates.
5. **Award graph** — IDV → definitive contract/order → transaction/modification → subaward; links opportunity and documents.
6. **Program graph** — budget account/line → acquisition program → platform/capability → award → supplier → public parent.
7. **Document intelligence** — parse/OCR, section/table extraction, embeddings, citations, and cross-version document diffs.
8. **Metrics engine** — deterministic formulas below, materiality denominators, and uncertainty propagation.
9. **Model lane** — similarity, value interval, bidder ranking, and entity candidates; always separately labeled and validated.
10. **Serving layer** — static artifacts for the website plus typed internal endpoints/MCP tools where necessary.

### 8.4 Entity resolution policy

Entity resolution is the most important moat and the easiest place to create false alpha.

Resolution order:

1. exact UEI;
2. exact CAGE joined through verified entity registration;
3. exact recipient identifier/source ID;
4. curated subsidiary alias with effective ownership dates;
5. verified joint venture membership and disclosed economics if available;
6. normalized legal name + address + website + parent evidence;
7. model-generated candidate, held in review state.

Never assign a ticker because a company name merely resembles an issuer. Never apply today's parent to an award dated before an acquisition without an effective-date rule. Joint-venture awards remain at the JV node unless economic attribution is explicitly documented; do not split 50/50 by convenience.

### 8.5 Vertical Intelligence Workbench federation

Government Revenue is independently operable but federation-compatible. The architecture is hub-and-spoke at the contract layer, not a shared monolith:

```text
                         Vertical Intelligence Hub
                    ticker 360 · catalyst tape · health
                                   ↑
                     shared versioned envelopes only
                 ┌─────────────────┼─────────────────┐
                 │                 │                 │
      Government Revenue      BioCatalyst      Future verticals
      procurement ontology    asset/clinical   shipping, trade,
      award/action engines    engines          energy, etc.
                 │                 │                 │
                 └──── shared company/document/event substrate ────┘
```

The hub is a reader and router. It does not become the source of truth for a desk's facts, rewrite a desk's confidence, or create a fused authority score.

#### Shared workbench primitives

| Primitive | Shared contract | Desk-local responsibility |
|---|---|---|
| Shell | Navigation, command palette, responsive layout, freshness strip, evidence drawer, saved views | Desk routes, widgets, domain filters, and record dossiers |
| Desk manifest | ID, label, routes, schemas, capabilities, owners, health endpoint, artifact paths | Version and publish its manifest; reject unsupported contract versions |
| Company entity | Canonical ticker/CIK/company ID and temporal parent identity | Domain nodes/aliases and evidence-backed edges to the shared company |
| Document reference | Immutable document ID, hash, URI, parser state, evidence-span format | Domain parsing, extraction schema, and interpretation |
| Event envelope | Identity, desk, subject, clocks, evidence, materiality, authority, typed payload | Domain event taxonomy, dedupe rule, and payload schema |
| Catalyst envelope | Window, state, magnitude semantics, confirmers, falsifiers, confidence, evidence | Domain-specific catalyst logic and validation |
| Evidence clock | Occurred/published/captured/known/effective timestamps and revision | Correct source-time semantics and point-in-time replay |
| Context envelope | Per-ticker facts, freshness, provenance, conflicts, and authority prohibition | Domain facts and explanations; no sibling authority mutation |
| Health envelope | Source lag, coverage, errors, last-good artifact, parser/model versions | Source-specific SLAs and remediation |
| Cross-desk hub | Global catalyst tape, ticker 360, evidence inbox, desk health | Each desk supplies envelopes; hub performs no opaque rescoring |

#### Shared desk manifest

```yaml
schema: vertical_desk_manifest.v1
desk_id: government_revenue
label: Government Revenue Foresight
version: semver
routes:
  command: /government_revenue.html
artifacts:
  display: site/government_revenue_data/latest.json
  context: data/neuralweb/government_revenue_context.json
capabilities:
  - company_context
  - catalyst_events
  - evidence_packets
authority_tier: display
health:
  artifact: data/government_revenue/health.json
owners:
  engine: government_revenue
  shell: vertical_workbench
```

#### Shared event envelope

Desk events travel through one envelope while retaining a namespaced payload:

```yaml
schema: vertical_event.v1
event_id: uuid
desk_id: government_revenue
event_type: procurement.award.action_added
subject_refs:
  - {type: public_company, id: uuid, ticker: LMT}
  - {type: award, id: uuid}
occurred_at: datetime|null
published_at: datetime|null
captured_at: datetime
known_at: datetime
effective_at: datetime|null
as_of: datetime
revision: integer
supersedes_event_id: uuid|null
catalyst:
  catalyst_id: uuid|null
  state: observed | developing | scheduled | resolved | retracted
  horizon_start: date|null
  horizon_end: date|null
  magnitude:
    value: decimal|null
    unit: USD|null
    semantic: obligation | ceiling | budget | opportunity_estimate | other
  confirmers: []
  falsifiers: []
evidence:
  class: source_reported | derived_deterministic | model_estimate | llm_extracted_unverified | analyst_override
  confidence_state: confirmed | probable | tentative | unresolved | contradicted
  refs: []
freshness:
  stale: boolean
  source_age_seconds: integer|null
authority:
  tier: display
  may_influence: []
  may_not_influence: [rank, size, gate, conviction, verdict]
payload_schema: government_revenue.award_action.v1
payload: {}
```

#### Evidence-clock law

The shared clock has distinct meanings:

```text
occurred_at  = when the underlying real-world action occurred
published_at = when the source says it published/released the record
captured_at  = when our collector first stored this exact source version
known_at     = earliest defensible time the system could have used it
effective_at = when the legal/program/contract state becomes effective
as_of        = cutoff used to assemble the current artifact
```

`known_at` is the only default inclusion clock for historical simulation. A desk cannot substitute `occurred_at` merely because it is earlier. The shared shell displays the clock relevant to the user's question and makes late publication/revision visible.

#### Catalyst-federation law

- A desk owns catalysts created from its ontology.
- A sibling may cite a catalyst, add a typed relationship, or publish its own corroborating/contradicting catalyst.
- A sibling may not mutate the originating catalyst's state, confidence, magnitude, or evidence.
- The hub may group related catalysts into a `cross_desk_case`; it may not average them into a fused score.
- Conflicts remain first-class objects with both evidence paths visible.
- Authority is the intersection of permissions, never the union. Joining two display-only contexts cannot create scored authority.

#### Independence requirements

Each desk owns and versions its collectors, domain ontology, canonical domain records, deterministic calculations, model lane, tests, freshness SLAs, and forward ledger. A desk must still build and render if a sibling is unavailable. Cross-desk reads happen through schemas/artifacts/events, never through undocumented direct reads of a sibling's private tables.

---

## 9. Canonical data model

All identifiers are internal UUIDs plus immutable source keys. All money fields store currency and nominal dollars; inflation-adjusted analytics are separate derived fields.

### 9.1 `legal_entity`

```yaml
entity_id: uuid
canonical_name: string
entity_type: public_parent | subsidiary | private_company | joint_venture | nonprofit | government | unknown
uei: [string]
cage_codes: [string]
source_recipient_ids: [{source, id}]
normalized_names: [string]
addresses: [{address, valid_from, valid_to, source_ref}]
website_domains: [string]
active_from: date|null
active_to: date|null
provenance: [evidence_ref]
```

### 9.2 `public_company`

```yaml
company_id: uuid
ticker: string
cik: string
exchange: string
issuer_name: string
reporting_currency: string
fiscal_year_end: string
segments: [{segment_id, name, valid_from, valid_to}]
government_revenue_disclosures: [{period, amount, pct_total, definition, evidence_ref}]
reported_backlog: [{period, amount, definition, evidence_ref}]
```

### 9.3 `ownership_edge`

```yaml
edge_id: uuid
parent_entity_id: uuid
child_entity_id: uuid
relationship: wholly_owned | majority_owned | minority_owned | joint_venture | acquired | divested | alias_of
economic_share: decimal|null
valid_from: date|null
valid_to: date|null
confidence_state: confirmed | probable | tentative | unresolved | contradicted
evidence_refs: [string]
analyst_override_id: string|null
```

### 9.4 `award`

```yaml
award_id: uuid
source_award_ids: [{source, id}]
award_family: contract | idv | grant | cooperative_agreement | ota | sbir | sttr | subaward
piid: string|null
parent_award_id: uuid|null
recipient_entity_id: uuid|null
awarding_agency_id: uuid
funding_agency_id: uuid|null
office_id: uuid|null
vehicle_id: uuid|null
program_ids: [uuid]
naics: string|null
psc: string|null
set_aside: string|null
pricing_type: string|null
competition_type: string|null
number_of_offers: integer|null
start_date: date|null
current_end_date: date|null
potential_end_date: date|null
current_award_amount: decimal|null
potential_award_amount: decimal|null
total_obligated: decimal
description: string|null
place_of_performance: object|null
last_source_update: datetime
valid_from: datetime
valid_to: datetime|null
source_refs: [string]
```

### 9.5 `award_action`

This is the analytical spine. Never collapse it into only the latest award total.

```yaml
action_id: uuid
award_id: uuid
source_action_id: string
action_date: date
fiscal_year: integer
modification_number: string|null
action_type: new_award | funding | option | ceiling_change | extension | deobligation | termination | correction | other
action_obligation: decimal
current_total_obligation: decimal|null
current_award_amount: decimal|null
potential_award_amount: decimal|null
delta_current_award_amount: decimal|null
delta_potential_award_amount: decimal|null
prior_end_date: date|null
new_end_date: date|null
description: string|null
raw_action_code: string|null
source_reported_at: datetime|null
captured_at: datetime
is_correction: boolean
supersedes_action_id: uuid|null
source_refs: [string]
```

### 9.6 `opportunity`

```yaml
opportunity_id: uuid
source: sam | agency_forecast | dibbs | grants | sbir | other
source_notice_id: string
solicitation_number: string|null
revision_id: string
base_notice_type: string|null
current_notice_type: string|null
status: forecast | sources_sought | presolicitation | solicitation | award_notice | cancelled | archived
title: string
description: string|null
agency_id: uuid
office_id: uuid|null
naics: [string]
psc: [string]
set_aside: string|null
posted_at: datetime|null
response_due_at: datetime|null
estimated_value_low: decimal|null
estimated_value_high: decimal|null
value_evidence_class: source_reported | model_estimate | unknown
linked_award_ids: [uuid]
linked_program_ids: [uuid]
incumbent_candidates: [{entity_id, confidence_state, evidence_refs}]
document_ids: [uuid]
valid_from: datetime
valid_to: datetime|null
source_refs: [string]
```

### 9.7 `document`

```yaml
document_id: uuid
source_url: string
record_type: opportunity | award | program | budget_line | protest | filing | transcript
record_id: uuid
title: string|null
mime_type: string|null
published_at: datetime|null
captured_at: datetime
content_sha256: string
parser_version: string
text_uri: string|null
page_count: integer|null
extraction_status: complete | partial | failed | unsupported
source_refs: [string]
```

### 9.8 `budget_program_line`

```yaml
budget_line_id: uuid
fiscal_year: integer
budget_stage: request | authorization | house | senate | conference | enacted | reprogrammed
service: string
appropriation: string
account_code: string|null
line_item_number: string|null
program_element: string|null
program_name: string
budget_activity: string|null
prior_year_actual: decimal|null
current_year_enacted: decimal|null
budget_year_request: decimal|null
quantity: decimal|null
unit_cost: decimal|null
delta_vs_prior: decimal|null
delta_vs_enacted: decimal|null
narrative: string|null
document_id: uuid
evidence_spans: [{page, text_hash, coordinates}]
```

### 9.9 `exposure_edge`

```yaml
exposure_id: uuid
from_type: budget_line | program | opportunity | award | entity
from_id: uuid
to_type: program | award | entity | public_company | segment
to_id: uuid
edge_type: explicit_identifier | named_in_document | award_history | incumbent | supplier | semantic_candidate
economic_weight: decimal|null
confidence_state: confirmed | probable | tentative | unresolved | contradicted
effective_from: date|null
effective_to: date|null
evidence_refs: [string]
model_version: string|null
```

### 9.10 `procurement_event`

```yaml
event_id: uuid
event_type: new_award | obligation_increase | deobligation | ceiling_increase | extension | option_exercised |
            new_idiq_seat | task_order | opportunity_posted | amendment | response_due_change | award_notice |
            recompete_window | protest_filed | protest_resolved | budget_increase | budget_cut |
            sbir_phase_progression | ownership_change | source_correction
event_time: datetime
known_at: datetime
record_ids: [uuid]
public_company_ids: [uuid]
program_ids: [uuid]
materiality: object
evidence_class: string
confidence_state: string
stale: boolean
dedupe_key: string
source_refs: [string]
```

`known_at` is mandatory for point-in-time tests. A later correction does not travel backward into an earlier backtest snapshot.

---

## 10. Exact calculations and labels

The UI must show the formula and input coverage for every nontrivial metric. Null is preferable to fake precision.

Let `O_a` be cumulative obligations for award `a`, `C_a` current award amount, `P_a` potential award amount, and `x_i` an action-level obligation change.

### 10.1 Funding and backlog

```text
net_obligations(a, window) = Σ x_i for valid actions i in window
positive_obligations(a, window) = Σ max(x_i, 0)
deobligations(a, window) = Σ min(x_i, 0)
funded_ratio(a) = O_a / C_a                         if C_a > 0
funded_backlog_proxy(a) = max(C_a - O_a, 0)        if C_a and O_a exist
total_backlog_proxy(a) = max(P_a - O_a, 0)         if P_a and O_a exist
unexercised_ceiling(a) = max(P_a - C_a, 0)         if P_a and C_a exist
```

Label both backlog figures **federal award backlog proxy**, never “company backlog.” `C_a - O_a` can include awarded value not yet obligated, contract structure, reporting corrections, or amounts that never become revenue. Preserve negative raw differences in audit fields even if display is floored at zero.

### 10.2 Award velocity

For company `c`, use ownership edges effective on each action date:

```text
award_velocity_net(c, w) = Σ attributed(x_i) over trailing w calendar days
award_velocity_positive(c, w) = Σ max(attributed(x_i), 0)
award_velocity_count(c, w) = count(distinct valid action_id where attributed(x_i) > 0)
velocity_yoy(c, w) = award_velocity_net(c, w) / award_velocity_net(c, prior-year matched w) - 1
```

For seasonal defense spending, compare matched federal-fiscal periods as well as trailing windows. If the comparison denominator is ≤0 or coverage changed materially, emit null plus a reason instead of a percentage.

Point-in-time surprise:

```text
velocity_surprise_z = (current_w - median(prior matched windows)) /
                      (1.4826 × MAD(prior matched windows))
```

Require at least eight prior matched windows; winsorize only in a separate display field and retain raw values.

### 10.3 Modification impulse

```text
net_ceiling_change(c, w) = Σ delta_potential_award_amount_i
net_current_value_change(c, w) = Σ delta_current_award_amount_i
extension_days_i = new_end_date_i - prior_end_date_i
modification_impulse(c, w) = net_ceiling_change(c, w) /
                             max(abs(trailing_365d_baseline_ceiling_additions), floor)
```

Separate administrative changes, funding actions, corrections, terminations, option exercises, and genuine scope/value changes. Do not treat every modification as commercial momentum.

### 10.4 Book-to-bill proxies

Publish two versions so obligations are not confused with bookings:

```text
funded_inflow_proxy(c, w) = Σ max(attributed(action_obligation_i), 0)
ceiling_booking_proxy(c, w) = Σ max(attributed(delta_potential_award_amount_i), 0)

funded_book_to_bill_proxy = funded_inflow_proxy(TTM) /
                            disclosed_government_revenue(TTM)

ceiling_book_to_bill_proxy = ceiling_booking_proxy(TTM) /
                             disclosed_government_revenue(TTM)
```

If government revenue is undisclosed, use total revenue only with the label `vs_total_revenue`, or emit no ratio. De-obligations appear separately and in net-flow views. Never add the same new-award ceiling again as a modification.

### 10.5 IDIQ participation and conversion

```text
active_vehicle_seats(c) = count(distinct IDVs where c is an eligible holder and current date <= potential_end_date)
new_vehicle_seats(c, w) = count(first-seen eligible IDV relationships in w)
task_order_conversion(c, vehicle, w) = awarded_order_value_to_c /
                                       total_awarded_order_value_on_vehicle
vehicle_utilization(c, vehicle) = obligated_orders_to_c /
                                  max(reported_vehicle_ceiling_share_denominator, null)
```

Do not divide one contractor's orders by the full vehicle ceiling and call it utilization without a clear label; multiple-award ceilings are often shared and not economically allocated.

### 10.6 Agency, program, and category exposure

For dimension `d` and company `c`:

```text
exposure_share(c,d,w) = attributed_positive_obligations(c,d,w) /
                        attributed_positive_obligations(c,all,w)

agency_concentration_hhi(c,w) = Σ_d exposure_share(c,d,w)^2
top_agency_share(c,w) = max_d exposure_share(c,d,w)
program_momentum(p,w) = net_obligations(p,w) - net_obligations(p,matched_prior_w)
```

Render HHI with the number of covered dimensions and “unknown/unmapped” share. A lower unknown share can mechanically change HHI; coverage deltas must be shown.

### 10.7 Competitor displacement and share gain

For agency/category/program market cell `m`:

```text
share(c,m,w) = positive_obligations(c,m,w) / positive_obligations(all,m,w)
share_change(c,m) = share(c,m,current_w) - share(c,m,matched_prior_w)

displacement_event(c_from,c_to,m) requires:
  incumbent evidence for c_from
  + linked recompete/follow-on opportunity
  + award evidence for c_to
  + matching requirement/program/vehicle evidence
```

A falling share is not by itself displacement. Use the displacement label only when the contract lineage is evidenced.

### 10.8 Recompete window

```text
earliest_recompete_date = current_end_date - procurement_lead_days(category, agency)
latest_recompete_date = potential_end_date
days_to_window = earliest_recompete_date - as_of_date
```

Display a **rule-derived window**, not an “expected award date,” unless an official forecast or solicitation supplies one. Vehicle option structure, extension history, protest status, bridge actions, and linked forecasts modify the evidence card; they do not silently rewrite source dates.

### 10.9 SBIR/STTR progression

```text
phase_1_to_2 = same firm/UEI + related topic/technology + later Phase II evidence
production_transition = SBIR/STTR lineage + later non-SBIR award, OTA, program-of-record,
                        subcontract, or explicit issuer/government statement
time_to_phase_2 = Phase II award date - Phase I award date
time_to_production = production evidence date - first related Phase I award date
```

Similarity alone produces `candidate_transition`; it becomes confirmed only with identifier, document, or analyst evidence.

### 10.10 Budget transmission

```text
budget_delta(line, stage) = amount(stage,current_fy) - comparable_amount(previous_stage_or_year)
company_budget_exposure(c,line) = budget_delta(line) × economic_weight(edge)
expected_exposure_range = budget_delta × [low_weight, high_weight]
```

`economic_weight` is null unless documented or empirically estimated with a disclosed method. Never allocate an entire program increase to the largest incumbent. The primary output is a graph of evidence and ranges, not a single beneficiary dollar claim.

Budget stages must remain distinct:

```text
request ≠ authorization ≠ appropriation/enactment ≠ obligation ≠ award ceiling ≠ revenue
```

### 10.11 Materiality

```text
event_vs_revenue = attributable_event_amount / latest_TTM_revenue
event_vs_gov_revenue = attributable_event_amount / latest_TTM_government_revenue
event_vs_reported_backlog = attributable_event_amount / latest_reported_backlog
event_vs_market_cap = attributable_event_amount / market_cap_as_of_event
```

Only calculate with a compatible numerator. An opportunity estimate is not comparable to a funded obligation without a visible funding-quality badge. Market-cap comparison is context, not valuation impact.

### 10.12 Source quality and freshness

```text
age = now - source_effective_timestamp
stale = age > source_specific_SLA
coverage_ratio = mapped_attributable_amount / total_candidate_amount
conflict_rate = conflicting_canonical_fields / checked_canonical_fields
```

Do not collapse these into a mysterious quality score. Show the components.

---

## 11. Predictive and AI engines

### 11.1 Engines worth building

| Engine | Inputs | Output | Validation |
|---|---|---|---|
| Entity candidate resolver | UEI/CAGE, names, addresses, domains, ownership documents | Candidate edge + reason codes | Precision-first labeled set; temporal ownership errors tracked separately |
| Hybrid similarity | BM25, embeddings, agency, NAICS/PSC, value, set-aside, program | Similar records with component contributions | Human relevance labels; NDCG/Recall by record family and time |
| Value interval | Explicit values, comparable awards, agency/category/vehicle, duration, competition | P10/P50/P90 and comparable set | Rolling-origin coverage and interval width; no point-only score |
| Bidder candidate ranker | Incumbency, agency/category experience, vehicle eligibility, set-aside, geography, recency, similarity | Ranked candidate set + reasons | Top-k recall, precision, calibration by opportunity type; time-split only |
| Recompete linker | Contract family, end dates, forecast/notice text, incumbent, office, codes | Candidate follow-on edges | Precision/recall against later linked awards; known-at timestamps |
| Program-beneficiary linker | Program names/aliases, budget lines, awards, issuer text, supplier graph | Exposure candidates + evidence paths | Analyst adjudication and document-level evidence precision |
| Document delta extractor | Prior/current document versions | Added/removed dates, values, requirements, quantities | Field-level exactness and page citation validity |
| Catalyst assessor | Typed events, materiality, funding quality, timing, issuer disclosures | Evidence dossier and falsifiers | Forward ledger vs earnings/backlog/guidance outcomes |

### 11.2 LLM law

LLMs may:

- summarize a retrieved evidence packet;
- propose entity/program/link candidates for deterministic or human review;
- extract fields with page/section citations;
- explain changes and conflicts;
- generate research questions and falsifiers;
- de-escalate a claim when evidence is weak.

LLMs may not:

- originate a trade signal, rank, size, gate, or conviction change;
- convert an unfunded ceiling or budget request into revenue;
- silently resolve entity identity or ownership;
- invent bidder odds, award values, dates, or program mappings;
- promote their own extraction from unverified to confirmed;
- override stale/missing/conflicting source flags.

### 11.3 “Odds” policy

Do not ship a generic “Odds of Award: 83%” badge. Ship separate, auditable concepts:

- `eligibility`: deterministic pass/fail/unknown;
- `relevance`: calibrated retrieval/ranking percentile;
- `competitive_density`: evidence from offers/history/market participants;
- `incumbent_advantage`: evidence components, not a magic percentage;
- `model_win_probability`: prohibited until a time-split labeled outcome set demonstrates calibration and the UI shows uncertainty.

---

## 12. Investor-first information architecture

### 12.1 Top-level surfaces

The shared Workbench shell always exposes **Vertical Hub** and **Ticker 360** before entering a specialist desk. Inside Government Revenue:

1. **Government Revenue Command** — daily delta console and coverage/freshness.
2. **Company Dossier** — public parent, subsidiaries, award velocity, backlog proxies, programs, upcoming events, filings/earnings reconciliation.
3. **Program & Budget Map** — budget stages, line-item deltas, contract families, beneficiaries, evidence paths.
4. **Award & Modification Explorer** — award hierarchy and action ledger.
5. **Opportunity & Recompete Calendar** — official dates, rule-derived windows, amendments, likely public-company exposure.
6. **Agency & Market Map** — demand acceleration, new entrants, share changes, vehicle use, competition.
7. **Evidence Vault** — documents, extracted spans, versions, conflicts, analyst overrides.
8. **Validation Lab** — shadow signals, forward outcomes, calibration, coverage, and failure cases.

The hub's Ticker 360 may place a procurement catalyst next to a BioCatalyst, earnings, ownership, or shipping catalyst. Clicking the card always returns to the owning desk's evidence dossier. The hub does not flatten domain semantics into generic “bullish/bearish” badges.

### 12.2 Command-page wireframe

```text
┌──────────────── Government Revenue Foresight ────────────────┐
│ As of 08:35 ET · Awards daily · Opportunities 11m · 2 stale │
├───────────────────────────────────────────────────────────────┤
│ WHAT CHANGED                                                   │
│ [Funded +$420m] [Ceiling +$1.2b] [3 new IDIQ seats] [2 cuts] │
│ LMT  +$125m obligation · F-35 lot · source-confirmed          │
│ AVAV Phase II → production candidate · 2 evidence paths       │
│ HII  FY budget line +18% · award exposure unresolved          │
├───────────────────────────────────────────────────────────────┤
│ COMPANY HEATMAP            │ CATALYST / RECOMPETE CALENDAR    │
│ Ticker · net delta · pace  │ date · event · evidence · risk   │
│ materiality · coverage     │ official vs rule-derived badge   │
├───────────────────────────────────────────────────────────────┤
│ PROGRAM TRANSMISSION                                           │
│ appropriation → line → program → vehicle → award → subsidiary │
│ show confirmed/probable/tentative edges and unmapped share     │
├───────────────────────────────────────────────────────────────┤
│ EVIDENCE / CONFLICTS                                            │
│ source links · exact changes · stale feeds · unresolved maps   │
└───────────────────────────────────────────────────────────────┘
```

### 12.3 Interaction rules

- Default sort is new information × materiality × evidence quality, not lifetime award value.
- Every dollar has a badge: `obligated`, `current value`, `potential ceiling`, `budget request`, `enacted`, `model range`, or `issuer reported`.
- Every date has a badge: `official`, `contract-derived`, `model-estimated`, or `unknown`.
- Selecting a metric opens its numerator records, denominator, formula, as-of timestamp, coverage, and conflicts.
- Company pages show public parent and attributed subsidiaries before charts.
- Charts support “reported as known then” mode; latest-restated data is never the only historical view.
- Mobile keeps change cards, company materiality, and evidence drawer; broad data tables become drill-down views.
- Motion communicates a new/changed/retracted relationship; it is not decorative.

### 12.4 Visual direction

Use MastermindX's native dark system with high-contrast evidence states. Do not imitate GovTribe's colors or HigherGov's Bootstrap composition. The visual grammar should distinguish:

- teal/blue: source-reported fact;
- green: funded positive change;
- red: de-obligation/cut/termination;
- amber: estimate, conflict, or approaching deadline;
- violet: budget/program context;
- gray: stale, unmapped, or unavailable.

Color never carries meaning alone; pair it with text/icon/state.

---

## 13. Artifact and API contracts

Names below are the target contracts. If the current implementation slice uses a versioned predecessor, add an explicit migration instead of maintaining parallel canonical artifacts.

### 13.1 Public display artifact

`site/government_revenue_data/latest.json`

```json
{
  "schema": "government_revenue.latest.v1",
  "built_at": "ISO-8601",
  "as_of": "ISO-8601",
  "freshness": {"status": "fresh|degraded|stale", "sources": []},
  "coverage": {"companies": 0, "mapped_amount_ratio": null, "unresolved_entities": 0},
  "market": {"windows": {}, "programs": [], "agencies": []},
  "companies": [],
  "events": [],
  "recompetes": [],
  "budget_transmission": [],
  "conflicts": [],
  "disclaimers": []
}
```

### 13.2 Neural Web artifact

`data/neuralweb/government_revenue_context.json`

```json
{
  "schema": "neuralweb.government_revenue_context.v1",
  "built_at": "ISO-8601",
  "as_of": "ISO-8601",
  "authority_tier": "display",
  "may_influence": [],
  "may_not_influence": ["rank", "size", "gate", "conviction", "verdict"],
  "ticker_context": {},
  "program_context": {},
  "freshness": {},
  "provenance": []
}
```

### 13.3 Internal canonical outputs

```text
data/government_revenue/latest.json
data/government_revenue/snapshots/YYYY-MM-DD.json
data/government_revenue/events.jsonl
data/government_revenue/entity_overrides.yml
data/government_revenue/forward_log.jsonl
```

The exact store may later move to Parquet/Postgres/object storage, but the site and Neural Web contracts remain small, versioned, atomic, and independently validated.

### 13.4 Read-only service methods

```text
search_government_records(query, filters, as_of)
get_company_government_context(ticker, as_of)
get_award_history(award_id, as_of)
get_program_exposure(program_id, as_of)
get_material_changes(since, tickers, evidence_min)
get_recompete_calendar(window, tickers)
get_evidence_packet(record_id)
```

Every response returns `schema`, `as_of`, `built_at`, `source_refs`, `stale`, and `coverage`. Mutating pursuit/CRM tools are outside the initial MCP surface.

### 13.5 Shared Workbench envelopes

The desk additionally emits:

```text
data/vertical_workbench/manifests/government_revenue.json
data/vertical_workbench/events/government_revenue.jsonl
data/vertical_workbench/context/government_revenue_latest.json
data/vertical_workbench/health/government_revenue.json
```

If central command defines different canonical paths before implementation, use those paths and retain the schemas—not a duplicate directory tree. The desk-local artifact remains the detailed truth; the Workbench artifacts are bounded projections.

Shared context projection:

```yaml
schema: vertical_context.v1
desk_id: government_revenue
as_of: datetime
built_at: datetime
subject: {type: public_company, id: uuid, ticker: string}
summary_facts: []
catalysts: []
corroborations: []
contradictions: []
open_questions: []
freshness: object
coverage: object
evidence_refs: []
authority:
  tier: display
  may_influence: []
  may_not_influence: [rank, size, gate, conviction, verdict]
```

The `payload` of a cross-desk event and every `summary_fact` must be namespaced/versioned. Shared fields describe delivery semantics; they do not force defense award amounts and clinical-trial endpoints into the same domain schema.

---

## 14. Neural Web and Prophet integration

### 14.1 Authority law

Government Revenue Foresight enters Neural Web and Prophet as **context**, not alpha authority.

```text
government procurement context
    → explain / corroborate / contradict / request review
    ↛ originate signal
    ↛ change rank
    ↛ change position size
    ↛ open or close a gate
    ↛ rewrite conviction or verdict
```

Register artifacts in `config/synapse.yml`; regenerate `docs/SIGNAL_BUS.md` rather than editing the generated registry directly.

### 14.2 Ticker context contract

For each ticker, provide:

```yaml
government_exposure:
  as_of: datetime
  freshness: fresh | degraded | stale
  mapping_coverage: decimal|null
  subsidiaries: []
  award_velocity:
    d30_net: decimal|null
    d90_net: decimal|null
    matched_prior_delta: decimal|null
  funding_quality:
    obligations: decimal|null
    funded_backlog_proxy: decimal|null
    unexercised_ceiling: decimal|null
  concentration:
    top_agencies: []
    top_programs: []
    hhi: decimal|null
  events: []
  recompetes: []
  budget_exposures: []
  contradictions: []
  evidence_refs: []
```

### 14.3 Prophet use

Prophet may use procurement context to add statements such as:

- “Recent award acceleration corroborates management's government-demand claim.”
- “The announced ceiling is largely unfunded; do not treat it as near-term revenue.”
- “A material recompete falls inside the forecast horizon.”
- “Budget-line support is rising, but supplier attribution is unresolved.”
- “The latest de-obligation contradicts the backlog-acceleration narrative.”

Prophet may not convert these into a new directional call. If procurement evidence contradicts an existing signal, it can raise a review/invalidation flag or de-escalate language under existing governance. Any later numeric promotion requires a separately approved shadow study and the repository gauntlet.

### 14.4 Forward ledger

The first predictive use is shadow-only. At each event, freeze:

- information available at `known_at`;
- entity/program mapping state;
- event amount and funding quality;
- expected transmission horizon/range;
- cited supporting and contradicting evidence;
- later issuer backlog/bookings/revenue/guidance outcomes;
- later award modifications or cancellations;
- market reaction only as a secondary evaluation target.

Primary validation target: did the context correctly anticipate a company-level operating change? Price is noisy and must not be the sole truth label.

---

## 15. Coordination with central command, earnings/documents, and 13G work

Do not create a second document store, company master, event scheduler, or ownership database.

### 15.1 Ownership of responsibilities

| Domain | Owning system | Government Revenue Foresight role |
|---|---|---|
| SEC filings, exhibits, XBRL, transcripts, presentations | Central earnings/document engine | Consume document IDs, evidence spans, disclosed revenue/backlog, guidance, and event times |
| Beneficial ownership / 13D / 13G | 13G/ownership engine | Consume ownership events only when relevant to public-company context; do not rebuild filing collection |
| Company/ticker/CIK master | Central command/company registry | Extend through versioned recipient/UEI/CAGE/subsidiary edges; do not fork canonical issuer identity |
| Scheduling, retries, health, secrets | Central command | Register procurement source adapters and events |
| Raw government procurement | Government Revenue Foresight | Own source adapters, raw hashes, normalization, revision history |
| Award/opportunity/program graph | Government Revenue Foresight | Own canonical procurement relationships and metrics |
| Signal authority | Existing Neural Web/Prophet governance | Supply context artifact only |

### 15.2 Event interface

Publish typed central-command events:

```text
procurement.award.created
procurement.award.action_added
procurement.award.corrected
procurement.opportunity.created
procurement.opportunity.amended
procurement.opportunity.deadline_changed
procurement.recompete.window_entered
procurement.protest.status_changed
procurement.budget_line.changed
procurement.entity_mapping.review_required
procurement.source.stale
```

Consumers subscribe; they do not re-poll our data or independently parse the same files.

### 15.3 Cross-engine synthesis packet

When an earnings event is upcoming, central command requests one packet per issuer:

```yaml
ticker: string
earnings_at: datetime
procurement_cutoff: datetime
since_prior_call:
  net_obligations: decimal|null
  positive_obligations: decimal|null
  deobligations: decimal|null
  net_ceiling_change: decimal|null
  major_events: []
  program_budget_changes: []
  recompetes: []
reported_baseline:
  government_revenue: object|null
  backlog: object|null
  management_claims: []
assessment:
  corroborations: []
  contradictions: []
  unresolved_questions: []
evidence_refs: []
```

This packet is qualitative research context. It does not predict EPS by multiplying obligations by an arbitrary revenue-recognition factor.

### 15.4 BioCatalyst collision and coordination contract

Government funding can be simultaneously relevant to procurement and biopharma. That overlap is a join, not an excuse for duplicate engines.

| Object or calculation | Government Revenue owns | BioCatalyst owns | Shared / hub behavior |
|---|---|---|---|
| USAspending/SAM/Grants/SBIR award and opportunity source record | Ingestion, revision, funding semantics, award/action lineage | Read-only reference | One canonical procurement record ID |
| NIH/BARDA/DoD-medical grant or contract amount | Obligation, ceiling, action history, agency/program linkage | Scientific/asset relevance and development implications | Two linked evidence cards, no duplicated dollar fact |
| SBIR Phase I/II funding progression | Award/topic/company lineage and production-contract evidence | Therapeutic/platform/technology interpretation where biomedical | Cross-desk progression case with separate confidence states |
| Drug/biologic/device asset | Government exposure edge only | Canonical asset, indication, mechanism, sponsor, ownership | Shared company ID; BioCatalyst asset ID referenced by edge |
| Clinical trial | Procurement-linked evidence only | Trial registry ingestion, phase, endpoints, enrollment, results | Government desk never recollects the trial registry |
| FDA/regulatory catalyst | None beyond cited contract consequence | Submission, decision, label, regulatory probability/context | Hub may show next to funding event; Government does not score it |
| Company filing/transcript | Consume central document ID and procurement-relevant spans | Consume same document and bio-relevant spans | One document/hash, domain-specific extractions |
| Revenue/backlog materiality | Government award proxies vs disclosed company baselines | Product/asset economics and biotech financing context | Hub shows both denominators and semantic labels |
| Catalyst authority | Display/context only | Its own governed authority contract | Intersection rule; no cross-desk escalation |

#### Collision resolution rules

1. **Source ownership follows the fact.** A BARDA award action belongs to Government Revenue even when it funds a drug; the drug's clinical implication belongs to BioCatalyst.
2. **One document, multiple evidence spans.** Both desks may extract from the same central document but store only domain-specific typed claims linked to the same immutable document ID.
3. **One issuer, domain-local nodes.** The central company ID is shared. Procurement recipient/subsidiary nodes remain here; therapeutic asset/sponsor/license nodes remain in BioCatalyst.
4. **No score laundering.** A high-confidence funded award does not upgrade a tentative clinical thesis, and a strong trial result does not prove government revenue conversion.
5. **No circular corroboration.** If both desks ultimately cite the same source statement, the hub counts one underlying evidence origin, not two independent confirmations.
6. **Contradictions survive federation.** Example: a new BARDA ceiling can coexist with a missed clinical endpoint. The hub displays both instead of resolving them into a directional average.
7. **Clock consistency.** Both desks inherit the same `known_at` for a shared source version; desk-specific derived facts can have later `known_at` values.
8. **Independent failure.** BioCatalyst source failure cannot stale the Government Revenue award ledger, and procurement failure cannot stale clinical data. The cross-desk case shows partial freshness.

#### Cross-desk example

```yaml
cross_desk_case:
  schema: vertical_case.v1
  case_id: uuid
  subject: {type: public_company, id: uuid, ticker: EXAMPLE}
  title: BARDA production funding after clinical milestone
  relationships:
    - from: {desk: government_revenue, catalyst_id: gov-123}
      to: {desk: biocatalyst, catalyst_id: bio-456}
      type: funds_asset_development
      confidence_state: confirmed
      evidence_refs: []
  synthesis:
    status: developing
    corroborations: []
    contradictions: []
    unresolved_questions:
      - Is the obligated amount recognized by the issuer as revenue, cost reimbursement, or deferred funding?
  authority:
    tier: display
    may_influence: []
```

The synthesis is deterministic assembly plus evidence-bound prose. It is not a cross-desk super-score.

---

## 16. Build lanes

Each lane has a deliverable and a hard exit gate. Do not wait for full competitor breadth before shipping useful investor intelligence.

### Lane 0 — production vertical slice

**Goal:** prove the full official-source → normalized metric → page → context-artifact loop.

Build:

- curated defense issuer universe and explicit recipient aliases;
- USAspending pull with offline/last-good behavior;
- company-level obligations, award counts, agencies, simple concentration, and recent changes;
- versioned display JSON and Government Revenue Command page;
- provenance/freshness and “official vs derived” labels;
- Neural Web display/context artifact with empty authority permissions;
- a `vertical_desk_manifest.v1`, `vertical_event.v1` projection, and `vertical_context.v1` projection for the shared Workbench shell;
- a link from the shared Vertical Hub/Ticker 360 contract into the Government Revenue dossier, without requiring BioCatalyst to be online;
- unit tests for formulas, mapping, stale behavior, and schema.

Exit gate:

- live page deployed;
- all displayed numbers reconcile to source requests/fixtures;
- no client secret;
- no fabricated data when the source is unavailable;
- source and build timestamps visible;
- shared Workbench envelope contract tests pass and authority remains display-only after federation;
- `config/synapse.yml` owns the artifact registry entries.

### Lane 1 — federal award-action spine

**Wave 6 receipt:** the first subaward substrate is implemented as an independent,
receipt-bound USAspending rail. It uses exact prime generated-award IDs and native broker
row IDs, preserves semantic versions, and publishes content-addressed canonical/public
dossier twins plus bounded list/detail APIs. Collection is capped at 160 deterministic
parents, 100 rows per page, five pages per parent, 2,000 detail rows per run, and 2,000
public current identities. Parents above 500 reported rows or beyond the run cap publish
verified counts with explicit count-only coverage and no invented details. Reported
subaward amounts remain self-reported subrecipient context—not obligations, outlays,
prime value, backlog, revenue, cash, issuer attribution, or additive value. This receipt
does not claim the full bulk-history lane, issuer/subcontractor mapping, frontend dossier
panel, or signal authority; those remain gated follow-ons.

Build:

- bulk historical contracts, IDVs, grants, and subawards;
- immutable award-action ledger and revision handling;
- temporal subsidiary/parent mapping with analyst overrides;
- funded/total backlog proxies, modification impulse, IDIQ seats/orders, agency/program/category exposure;
- company and award dossiers;
- nightly delta plus weekly/monthly reconciliation.

Exit gate:

- ≥99.5% duplicate-free action IDs on fixtures;
- selected company totals reconcile within documented source semantics;
- ≥98% precision on reviewed public-company mappings; unresolved rows stay unmapped;
- point-in-time replay produces only records known by each cutoff.

### Lane 2 — opportunities, forecasts, and recompetes

**Wave 2 receipt:** the SAM notice/revision/document spine, governed event/workspace
contracts, point-in-time amendment diffs, source-revision semantics, derived expiry
watches, investor workbench, bounded APIs, and frequent semantic change-detection lane
are implemented. Activation against the live source is blocked only on installation of a
server-side `SAM_API_KEY`; no synthetic opportunity is substituted while it is absent.
The current GitHub-hosted lane targets a best-effort 30-minute poll. Complete quiet polls
publish current-state health without creating semantic alerts; failed, incomplete, or
missed polls age stale in both the client and server-side Neural Web/Prophet readers. A
true 15-minute SLA remains a managed-live-plane upgrade, not a present deployment claim.
The forecast registry, award/opportunity family linker, saved monitors, and complete
active/archive reconciliation remain open.

Build:

- SAM API adapter, documents, revisions/amendments, and active/archive reconciliation;
- agency forecast adapter registry;
- award ↔ opportunity and contract-family linker;
- rule-derived recompete windows;
- saved monitors and typed events;
- opportunity/recompete calendar.

Exit gate:

- 30-minute scheduled poll without duplicate alert storms; move to the managed
  live plane before claiming a hard 15-minute SLA;
- amendment field diffs and document hashes validated;
- linked-record precision reported separately from recall;
- official dates visually separated from inferred windows.

### Lane 3 — DoD budget and program transmission

Build:

- budget-book inventory, PDF/table parser, page-level evidence spans;
- request/authorization/appropriation/enacted stage model;
- program alias ontology for Golden Dome/missile defense, hypersonics, drones/autonomy, nuclear, shipbuilding, cyber, space, munitions, and other priority packs;
- program ↔ award ↔ supplier ↔ issuer exposure graph;
- budget delta and beneficiary evidence views.

Exit gate:

- line-item totals reconcile to book summaries;
- every extracted amount links to page evidence;
- no budget stage is collapsed into another;
- issuer attribution precision audited; unmapped share reported.

### Lane 4 — SBIR/OTA, DIBBS, grants, protests, and specialized defense

Build:

- SBIR/STTR bulk and topic lineage;
- candidate Phase I → Phase II → production transitions;
- OTA classification and follow-on lineage;
- DIBBS/NSN/part-supplier graph where permitted;
- GAO protest events and outcome linkage;
- labor-rate and service-pricing context;
- NIH/BARDA/biodefense sector pack on the same substrate.

Exit gate:

- progression labels distinguish candidate vs confirmed;
- public-source licensing and access documented;
- supplier mapping never assumes manufacturer from free-text alone;
- protest and grant lags visible.

### Lane 5 — retrieval, model estimates, and research agent

Build:

- hybrid search and similar records;
- value intervals;
- bidder candidates;
- program-beneficiary candidates;
- evidence-bound RAG across opportunities, budget books, awards, filings, and transcripts;
- read-only MCP tools and central-command automations.

Exit gate:

- time-split evaluation set frozen before tuning;
- value intervals meet stated coverage by record class;
- bidder top-k metrics and calibration published, not cherry-picked;
- every generated assertion cites an evidence span or says unresolved;
- LLM cannot modify canonical facts or signal authority.

### Lane 6 — investor validation and selective promotion

Build:

- forward studies against issuer backlog/bookings/revenue/guidance;
- event studies by funding quality, materiality, company size, and program class;
- ablations for entity mapping, budget edges, and document features;
- shadow catalyst states and falsifiers.

Exit gate:

- minimum sample and holdout periods predeclared;
- no point-in-time leakage;
- stable results across subperiods and company cohorts;
- costs, turnover, and publication lag included where price outcomes are tested;
- any authority promotion receives a separate proposal and repository gauntlet approval.

### Lane 7 — breadth and operational parity

Build only after the investor spine works:

- prioritized SLED adapters;
- licensed/public contact enrichment if economically justified;
- FOIA operations and released-document vault;
- team cases, assignments, comments, exports, and external integrations;
- additional grant/agency/vehicle/program packs.

Exit gate:

- each source has a coverage/freshness SLA;
- unit economics beat purchasing an incumbent seat for the same workflow;
- no source is represented as comprehensive without measured coverage.

---

## 17. Validation and test plan

### 17.1 Unit tests

- obligation, funded-ratio, backlog-proxy, ceiling, HHI, share, velocity, and materiality formulas;
- null/zero/negative/correction cases;
- fiscal-year and timezone boundaries;
- ownership effective dates and acquisition/divestiture cases;
- joint ventures with unknown economic share;
- dedupe and supersession logic;
- stale/source-down behavior;
- schema version and required provenance fields.

### 17.2 Source-contract tests

- frozen official API responses for every adapter;
- pagination, retries, quotas, date ranges, and deleted/archived records;
- document URL expiry and content-hash changes;
- malformed PDF/table/OCR paths;
- source field additions/removals detected before production parse loss.

### 17.3 Reconciliation tests

- transaction sum ↔ current award total for sampled awards, with known correction exceptions;
- company sum ↔ mapped recipient sum;
- program/agency/category rollups ↔ underlying actions;
- page totals ↔ display artifact ↔ canonical mart;
- latest snapshot ↔ prior snapshot + event ledger;
- source bulk download ↔ delta ingestion after backfill.

### 17.4 Entity-resolution tests

Maintain a gold set covering:

- large primes with many subsidiaries;
- acquisitions and divestitures;
- renamed entities;
- JVs and mentor-protégé ventures;
- reused/common names;
- foreign parents and U.S. subsidiaries;
- private entities that must not map to a ticker.

Report precision, recall, unresolved rate, and **wrong-ticker dollar rate**. Optimize precision before recall.

### 17.5 Point-in-time tests

- Every fixture has `known_at` and source capture time.
- Backtests read the version valid at the historical cutoff.
- Later corrections affect later truth but never earlier model inputs.
- Contemporary ownership edges apply; current ownership is not backfilled through history.
- Historical market-cap and filing denominators use contemporaneous values.

### 17.6 Model validation

- rolling-origin train/validation/test, not random row splits;
- dedupe contract families across folds to prevent near-copy leakage;
- metrics by agency, notice type, set-aside, value band, and data availability;
- calibration curves/Brier score for probabilities;
- empirical interval coverage for value ranges;
- top-k recall and NDCG for ranking;
- abstention rate and accuracy when abstaining;
- baseline comparison against simple deterministic rules.

### 17.7 UI validation

- Can a user distinguish obligation, award value, ceiling, budget request, and company backlog without a tooltip?
- Can every headline value be traced to source records in two interactions?
- Are stale/conflicting/unmapped states obvious on desktop and mobile?
- Does keyboard/search navigation work with dense tables?
- Is the first viewport about changes rather than lifetime totals?
- Does the page remain useful when one or more feeds fail?

---

## 18. Operations, freshness, and failure policy

### 18.1 Target cadence

| Data family | Collection | Reconciliation | Stale threshold |
|---|---|---|---|
| SAM active opportunities | 30 minutes best-effort (current); 15 minutes after managed-plane migration | Daily; archived weekly | 90 minutes during expected service hours |
| USAspending award deltas | Daily | Weekly delta and monthly bulk | 48 hours |
| Issuer filings | Central engine, event-driven | Nightly bulk | Per central contract |
| Agency forecasts | Daily source check | Quarterly inventory review | Source-specific |
| DoD/congressional budget docs | Event-driven during budget cycle | Weekly inventory | Source-specific |
| GAO protests | Daily | Weekly | 72 hours |
| SBIR/STTR | Daily availability; monthly bulk | Monthly | 35 days for bulk; API status shown |
| SLED/DIBBS | Adapter-specific | Weekly | Adapter-specific |

### 18.2 Failure policy

- Never replace a failed pull with an empty “fresh” dataset.
- Publish last-good data only with `stale=true`, source age, failure reason, and affected coverage.
- Quarantine schema-breaking payloads; do not partially mutate canonical rows.
- Retry with bounded exponential backoff and jitter.
- Make every run idempotent with source cursor and content hash.
- Reconciliation emits correction/retraction events; it does not silently rewrite the user-visible past.
- Alerts dedupe on typed event identity and meaningful field change, not polling run.

### 18.3 Observability

Minimum source dashboard:

- last request/success/valid record timestamp;
- rows/files seen, inserted, updated, superseded, deleted, rejected;
- lag distribution;
- schema drift;
- mapping coverage and wrong/unresolved review counts;
- reconciliation delta;
- document parse/OCR success;
- alert/event volume and dedupe rate;
- artifact build and publish checksum.

---

## 19. Security and data governance

- Store SAM, Grants.gov, and any licensed API credentials server-side only; never emit them into `site/`, logs, URLs in artifacts, or client JavaScript.
- Sanitize source URLs and query strings before logging.
- Respect source quotas, robots directives where applicable, official bulk-download preferences, and terms.
- Hash and malware-scan downloaded documents before parsing.
- Treat government contact PII as purpose-limited; do not create a broad people-marketing database for the investor MVP.
- Do not ingest classified, controlled, export-restricted, source-selection-sensitive, or improperly disclosed material.
- Analyst overrides require author, timestamp, reason, evidence, prior value, and rollback.
- Separate user workspaces/watchlists from public display artifacts.
- Evidence packets should quote minimally and link to source documents; document access rights travel with the document.
- Dependency/model/parser versions belong in run metadata for reproducibility.

---

## 20. Completion criteria

### The initial product is done when

- a production Government Revenue Command page is live;
- the page is generated from official-source data or an honestly labeled last-good cache;
- the initial defense universe has explicit, reviewed recipient mappings;
- obligations and action counts reconcile to source evidence;
- every amount/date is semantically labeled;
- freshness, mapping coverage, and source failures are visible;
- a versioned Neural Web display/context artifact is registered through `config/synapse.yml`;
- Government Revenue is registered as a Vertical Intelligence Workbench desk with versioned manifest, event, context, evidence-clock, and health envelopes;
- the shared hub can render its company catalyst cards and deep-link to the specialist dossier without reading private desk tables;
- a government-funded biomedical fixture proves the BioCatalyst boundary: one procurement fact, one shared company/document identity, two independent interpretations, and no authority escalation;
- Prophet can retrieve evidence context but cannot change rank, size, gate, conviction, or verdict from it;
- tests cover formulas, mapping, point-in-time behavior, schema, and offline failure;
- the branch is merged, production has advanced to the merge/descendant, and the live page is independently checked.

### Full product parity is done only when

- award, action, opportunity, forecast, document, vehicle, recipient, agency, program, grant, SBIR/OTA, protest, DIBBS/NSN, and selected SLED lanes meet published coverage/freshness SLAs;
- search, similarity, dossiers, alerts, cases, exports, evidence-bound AI, and read-only MCP are production-grade;
- entity and program graphs have measured precision and unresolved coverage;
- value/bidder/recompete models publish out-of-time validation and uncertainty;
- all investor claims are reproducible from point-in-time evidence;
- the forward ledger demonstrates additive operating/earnings context beyond simple award headlines;
- no competitor code, protected content, or proprietary dataset is required to run the system.

### “Stronger than HigherGov/GovTribe” is earned only when

- users can identify material listed-company deltas faster than in either capture-first product;
- budget → program → award → subsidiary → issuer paths are evidence-visible;
- funded obligations are never conflated with ceilings, appropriations, announcements, or GAAP revenue;
- company dossiers reconcile procurement changes with earnings calls, filings, reported backlog, and guidance;
- corrections and failed hypotheses remain visible in a forward truth ledger;
- the product abstains when entity/program attribution is not defensible.

---

## 21. Already covered / excluded fence

### Already covered elsewhere — consume, do not rebuild

- SEC filing and earnings-transcript ingestion/parsing;
- shared document storage, OCR, citation spans, and document search if the central document engine already provides them;
- canonical ticker/CIK/company registry;
- 13D/13G beneficial-ownership collection and interpretation;
- market prices, estimates, earnings calendar, and core Prophet signal computation;
- generic task scheduling, secrets, retries, health checks, and central event routing;
- existing Neural Web governance, artifact registry, signal authority, and promotion gauntlet.

### Excluded from the initial release

- capture CRM parity, proposal writing, bid submission, pricing-to-win, and sales outreach;
- state/local national completeness;
- proprietary contact enrichment;
- paid public-record request operations;
- classified or non-public procurement inference;
- exact revenue-recognition forecasting from obligations alone;
- a universal “odds of award” score;
- autonomous trade origination or automatic authority promotion;
- copying competitor branding, interface, code, copy, or proprietary data.

### Explicit future seams

- NIH/BARDA/biodefense and government-funded biopharma ontology;
- international allied procurement and foreign military sales;
- supply-chain/part-level exposure with licensed or official data;
- SLED adapters prioritized by issuer relevance;
- contractor-facing capture workflows if investor intelligence proves the platform first.

---

## 22. Primary-source index

### Competitor documentation

- HigherGov: [product](https://www.highergov.com/), [pricing](https://www.highergov.com/pricing/), [docs](https://docs.highergov.com/), [data sources](https://docs.highergov.com/more/data-sources), [federal contracts](https://docs.highergov.com/market-intelligence/find-and-analyze-federal-contracts), [federal opportunities](https://docs.highergov.com/find-opportunities/federal-contracts), [API](https://docs.highergov.com/import-and-export/api), [Government MCP](https://www.highergov.com/gov-mcp/), [terms](https://www.highergov.com/tos/).
- GovTribe: [pricing](https://govtribe.com/plans), [plan guide](https://govtribe.com/docs/govtribe-user-guide/guides/choose-the-right-govtribe-plan/), [search modes](https://govtribe.com/docs/govtribe-user-guide/guides/choose-a-search-mode-and-write-queries/), [similar records](https://govtribe.com/docs/govtribe-user-guide/guides/find-similar-records/), [automations](https://govtribe.com/docs/govtribe-user-guide/govtribe-ai/automations/), [MCP](https://govtribe.com/docs/govtribe-user-guide/govtribe-mcp/), [AI capabilities and limits](https://govtribe.com/docs/govtribe-user-guide/govtribe-ai/govtribe-ai-capabilities-and-limits/), [new entrants](https://govtribe.com/docs/govtribe-user-guide/reports/new-entrants/), [terms](https://govtribe.com/docs/govtribe-user-guide/terms-of-use/).

### Government and regulatory sources

- U.S. Treasury: [USAspending API](https://api.usaspending.gov/) and [endpoints](https://api.usaspending.gov/docs/endpoints).
- GSA: [SAM.gov Opportunities API](https://open.gsa.gov/api/get-opportunities-public-api/) and [API catalog](https://open.gsa.gov/api/).
- Grants.gov: [API resources](https://www.grants.gov/api) and [API guide](https://www.grants.gov/api/api-guide).
- SBA: [SBIR/STTR data resources](https://www.sbir.gov/data-resources), [awards](https://www.sbir.gov/awards), and [data dictionary](https://www.sbir.gov/data-resources/data-dictionary).
- DoD: [Comptroller budget materials](https://comptroller.defense.gov/Budget-Materials/).
- GSA/FAR Council: [Acquisition.gov](https://www.acquisition.gov/) and [FAR contract reporting](https://www.acquisition.gov/far/subpart-4.6).
- GAO: [bid protests](https://www.gao.gov/legal/bid-protests), [docket/decision explanation](https://www.gao.gov/legal/bid-protests/faqs), and [recent decisions](https://www.gao.gov/legal/bid-protests/recent).
- SEC: [EDGAR public data APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces).

---

## 23. Final instruction to Fable

Build the narrowest end-to-end slice first, but build it on the final data laws: immutable source evidence, action history, temporal entity ownership, point-in-time replay, visible uncertainty, atomic artifacts, and zero signal authority. Do not spend the first cycles recreating a capture CRM or a 50-filter search page.

The product wins when the user opens it and immediately sees a defensible answer to:

> **What changed in government demand, who is economically exposed, how funded is it, when could it matter, and what evidence would prove us wrong?**
