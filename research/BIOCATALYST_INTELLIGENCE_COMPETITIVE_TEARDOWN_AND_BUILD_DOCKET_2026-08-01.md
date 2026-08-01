# BioCatalyst Intelligence

## BioPharmCatalyst and BiopharmIQ teardown, clean-room engine reconstruction, sector-platform architecture, and MastermindX build docket

| Field | Value |
|---|---|
| Status | Canonical private research and implementation handoff |
| As of | 2026-08-01, America/Vancouver |
| Audience | Fable, product design, data engineering, ML/quant, Neural Web, Prophet, Mastermind AI |
| Decision | BUILD — reconstruct the useful product contract from primary sources, replace the weak engines, and make biopharma the first pack on a reusable Sector Intelligence Platform |
| Canonical file | research/BIOCATALYST_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md |
| Publication boundary | Private research artifact. Do not publish through reports.html without a separate operator decision. |
| Companion lanes | Corporate Intelligence Spine; Capital Structure Intelligence; HigherGov / defense and procurement; existing Thematic Foresight Desk |

---

## 0. Acceptance gates

This is the binding quality bar for any session commissioned from this docket. A feature is not complete because a table renders or an endpoint returns JSON.

### 0.1 Product acceptance

The complete commercial product is not done unless it provides:

1. one universal Event Explorer instead of separate FDA, PDUFA, trial, earnings, conference, IPO, and historical-calendar applications;
2. one Company Explorer with reusable lenses instead of isolated cash, insider, ownership, M&A, and funding databases;
3. Company, Asset, Trial, and Catalyst Dossiers with evidence, revisions, uncertainty, and an as-of selector;
4. watchlists that can contain companies, assets, indications, targets, trials, catalysts, and saved cohorts;
5. a Change Tape that says what changed, why it matters, what evidence supports it, and which forecasts or portfolios are affected;
6. an authenticated API with pagination, incremental synchronization, point-in-time queries, source IDs, model versions, and service-account controls;
7. an explicit mobile information hierarchy, not horizontally crushed desktop tables; and
8. English and Chinese product parity from the first user-facing wave.

### 0.2 Intelligence acceptance

The intelligence layer is not done unless:

1. every displayed fact resolves to source evidence, observed time, effective time, parser version, and license class;
2. every disclosed date preserves the source's original phrase and interval/bound constraint, separate from any predictive occurrence distribution;
3. trial versions are append-only and endpoint, enrollment, status, site, and timing changes are reproducible;
4. every prediction stores the exact feature snapshot, knowledge cutoff, model version, calibration version, and outcome policy;
5. a point-in-time replay can reconstruct only what the evidence-coverage class establishes for that date, and refuses unsupported precision;
6. baseline models remain visible and challengers cannot replace them without a predeclared evaluation;
7. uncertain identity, ownership, patent, endpoint, and catalyst links remain uncertain rather than being silently merged;
8. stale sources fail visibly stale; and
9. LLMs may retrieve, explain, compare, and de-escalate, but may not originate a signal, score, escalation, or probability.

### 0.3 Prophet and Neural Web acceptance

BioCatalyst is not integrated merely because its JSON exists. Integration is not done unless:

1. one explicit Neural Web reader consumes a versioned sector packet;
2. the packet declares freshness, contradictions, evidence, uncertainty, and authority caps;
3. any Prophet-bound biopharma feature joins only from a frozen point-in-time snapshot;
4. the initial join occurs after selection and cannot alter IDs, order, entry gates, or size;
5. every prediction and outcome, when forecasts begin, accrues in the BioCatalyst-owned append-only forward ledger;
6. stale or contradictory evidence can reduce confidence or trigger abstention before anything can increase rank;
7. identical inputs reproduce identical packets; and
8. every value visible to Prophet has a contribution trace back to primary evidence.

The facts-only beta may emit no prediction at all. Official facts attached after selection are `display/context`, not “shadow forecasts.” The first baseline or model prediction activates the minimal persistent domain ledger and begins as `shadow`; it cannot be represented as a fact or influence IDs/order/gates/size.

### 0.4 Billion-dollar SaaS design acceptance

BioCatalyst will establish the visual and interaction language for a family of niche intelligence products. The UI is not done unless:

1. a cold user understands the state, significance, and next action in five seconds;
2. dense information uses progressive disclosure: glance, inspect, then study;
3. every number is visibly classified as fact, derived estimate, or scenario;
4. a single command bar finds any company, drug, target, indication, trial, filing, catalyst, or saved view;
5. every major object supports time travel, evidence inspection, sharing, export, and natural-language investigation without changing mental models;
6. motion communicates state changes, dependency flow, or temporal revision—never decorative dashboard theater;
7. no surface resembles a generic admin template, spreadsheet with a sidebar, or a direct visual copy of a competitor;
8. desktop, tablet, and mobile each have intentionally composed layouts;
9. typography, density, color, interaction, empty states, loading states, error states, and provenance drawers are specified and visually verified;
10. real production-shaped data, long labels, missing data, contradictory evidence, and stale sources are present in design review; and
11. BioCatalyst, HigherGov, future Shipping and Trade, Mining, Energy, and Agriculture products feel like desks inside one institutional operating system.

### 0.5 Delivery acceptance

The recommended closed beta is not done unless:

- a persistent service lane—not a repository render or best-effort nightly—owns collection schedules, queues, retries, migrations, credentials, watermarks, and canonical object-storage/database writes;
- the core system completes a fourteen-day production soak with per-source opportunity counts, observed attempts, successful fetch/parse/publish counts, freshness-target attainment, completeness drift, and maximum consecutive misses;
- the severity-weighted freshness/error budget in a pre-frozen source-SLO manifest passes for every source the manifest classifies as launch-critical; 99.5% scheduler success alone is insufficient;
- every visible claim has a traceable source;
- any SEC-backed beta feature is enabled only when the landed Corporate Intelligence lane brings material filings to its evidence store within five minutes at p95;
- any issuer-disclosure-backed beta feature is enabled only when its registered owner brings monitored disclosures within fifteen minutes at p95;
- FDA and regulatory-calendar changes arrive within sixty minutes at p95;
- ClinicalTrials.gov changes arrive within two hours of the upstream data timestamp at p95;
- source outages, parser failures, stale data, and model rollback have been drilled;
- endpoint-change extraction clears the pre-sized per-family lower-confidence-bound gates in section 20.3, nominally at least 95% precision and 90% recall;
- entity auto-merges clear the pre-sized per-entity-family lower-confidence-bound gates in section 20.3, nominally at least 99.5% precision, and ambiguous matches enter a review queue; and
- every user-facing surface passes a visual comparison review in dark, light, mobile, and Chinese states.

---

## 1. Executive verdict

### 1.1 The opportunity

Build BioCatalyst Intelligence.

The strongest product is not a pixel clone of BioPharmCatalyst. It is:

> BioPharmCatalyst's investor event coverage
> plus BiopharmIQ's company, private-market, and cohort ontology
> plus MastermindX's temporal evidence graph, financing intelligence, calibrated distributions, market structure, and machine-native reasoning.

BioPharmCatalyst is feature-rich but architecturally old. Its apparent complexity comes from many separately named calendars, screeners, databases, reports, and company tabs that repeatedly expose the same underlying objects. The authenticated frontend and browser-delivered client reveal a conventional Vue/Webpack application backed by Laravel-shaped JSON routes. Most screens are filters over company, drug, event, financial, market, or editorial tables.

The visible analytical engines are weaker than the product breadth suggests:

- historical probability of success is a static therapeutic-area by phase-transition lookup built from a 2016–2021 cohort;
- likelihood of approval is the product of the remaining fixed transition rates;
- live cash is a straight-line extrapolation of the last reported cash using quarterly operating cash flow divided by three;
- runway divides that extrapolated cash by absolute monthly operating cash flow;
- net cash subtracts total liabilities rather than a capital-structure-aware debt measure;
- Catalyst Impact receives precomputed option and community values from the server, but no advanced proprietary pricing method is exposed in the client; and
- most other “engines” are normalized joins, curation, status logic, filters, and historical event tagging.

That makes the build unusually attractive. The hard and defensible work is not copying pages. It is:

1. stable company, security, asset, target, indication, trial, and regulatory identity;
2. immutable source evidence and bitemporal history;
3. accurate change detection;
4. point-in-time outcome cohorts;
5. calibrated probability, timing, financing, and payoff distributions;
6. analyst operations and correction handling; and
7. deep integration into the rest of MastermindX.

### 1.2 Scores

| Target | Feasibility | Judgment |
|---|---:|---|
| BPC-looking frontend | 9/10 | Easy, but strategically wrong |
| BPC functional frontend parity | 8.5/10 | Standard product engineering once schemas exist |
| Current public-source catalyst and trial data | 8/10 | Official ingredients are unusually accessible |
| BPC retail API parity | 9/10 | Its public API is narrow and conventional |
| BPC current-state product parity | 8/10 | Achievable with bounded scope and analyst QA |
| BPC historical database parity | 5/10 | Point-in-time reconstruction and silent failures are the hard part |
| BiopharmIQ public-company feature parity | 8.5/10 | Mostly public data, search, and workflow |
| BiopharmIQ private-company/contact parity | 4–6/10 | Human QA and licensed contact data are the moat |
| Strong calibrated prediction layer | 6/10 to build, 3/10 to prove quickly | Requires longitudinal evidence and a forward ledger |
| Focused eight-week closed-beta prototype | Feasible hypothesis with four technical staff plus analyst support | Commit the date only after W0 measures source, identity, review, and bilingual-QA workload; predictions remain shadow |
| Strategic payoff to MastermindX | 9.5/10 | A defensible vertical plus a reusable sector interface/product kit |

### 1.3 The contrarian conclusion

BPC's weak UI is an advantage to us. It demonstrates demand for the jobs-to-be-done without establishing a high experience bar. We can exceed the visible product quickly if we refuse its information architecture.

The governing product rule is:

> Clone the ontology and user jobs. Do not clone the page sprawl.

All calendars become saved lenses of one Event Explorer. All “analysis databases” become saved lenses of one Company Explorer. Every entity opens into the same dossier grammar. Every change enters one temporal evidence stream. Every screen can be queried by humans, Mastermind AI, and downstream systems through the same contracts.

### 1.4 What not to build

Do not spend the facts-first beta on:

- twenty separate calendar pages;
- podcasts, media, community games, or a branded expert watchlist;
- a second generic document or transcript store;
- a second SEC collector;
- a second cash-runway or dilution engine;
- opaque community votes presented as probability;
- unlicensed analyst targets or options chains;
- a monolithic five-factor score created by multiplying unrelated raw quantities;
- an LLM that invents clinical odds; or
- a biotech-specific platform that cannot support the next sector.

---

## 2. Investigation method and evidence boundary

### 2.1 What was directly inspected

The investigation used normal public and authenticated product access on 2026-08-01. It covered:

- the BioPharmCatalyst public site, pricing, onboarding, FAQ, terms, and API documentation;
- the authenticated navigation, account settings, portfolio tools, notification taxonomy, calendars, screeners, analysis databases, reports, and company pages;
- browser-delivered JavaScript bundles and ordinary frontend network traffic;
- visible request routes, response shapes, filters, columns, counts, and calculations;
- BioPharmCatalyst's public developer API contract;
- BiopharmIQ's official product, pricing, workflow, list-service, and methodology materials;
- the current Macro Dashboard repository and its existing clinical-trial, FDA, SEC, earnings, Neural Web, and Prophet wiring;
- current concurrent Corporate Intelligence and Capital Structure work;
- official ClinicalTrials.gov, FDA, openFDA, SEC, NCBI, NIH, USPTO, and EPO documentation; and
- the existing Thematic Foresight Desk and repo authority laws.

### 2.2 What “frontend code access” means

The browser necessarily receives client JavaScript, route names, component behavior, static assets, and server-returned JSON. That is enough to recover:

- information architecture;
- page states;
- filter and column definitions;
- client-side transformations;
- request and response contracts;
- route families;
- entitlement behavior visible to the account;
- UI component choices; and
- formulas calculated in the client.

It does not provide BioPharmCatalyst's private server repository, database, analyst tools, source-ingestion jobs, hidden normalization rules, or internal quality-control process. Backend reconstruction below is therefore separated into:

| Label | Meaning |
|---|---|
| OBSERVED | Seen directly in the public or authenticated product |
| CLIENT-VERIFIED | Present in browser-delivered code or ordinary network traffic |
| DOCUMENTED | Stated in official product or source documentation |
| RECONCILED | Formula reproduced from multiple displayed inputs and outputs |
| INFERRED | Most plausible implementation; not presented as exact proprietary internals |
| UNKNOWN | Not exposed; must be tested or independently designed |

### 2.3 Operational acquisition boundary

The production system should ingest primary and properly licensed sources, not depend on BioPharmCatalyst pages as a data feed. BPC's published terms restrict automated extraction, redistribution, replication, and look-and-feel copying. The client can be used as a behavioral specification and parity benchmark; any copied assets, annotations, proprietary historical rows, or production data dependency require explicit rights.

This boundary is strategically useful even if broader permission exists: independent schemas, primary-source lineage, and a house-native interface create the stronger product and prevent a competitor's taxonomy, outages, corrections, and licensing terms from becoming our infrastructure.

### 2.4 Confidence summary

| Area | Confidence |
|---|---:|
| Product inventory and navigation | High |
| Frontend stack and visible API families | High |
| BPC filter/column behavior | High |
| Probability-of-success display arithmetic | Medium; displayed multiplication reconciles, cohort construction is unknown |
| Cash display calculations | Medium; inspected rows reconcile, upstream fiscal-period treatment is unknown |
| Exact Catalyst Impact option formula | Low; server-computed |
| BPC human curation workflow | Low |
| BPC database schema and infrastructure | Unknown |
| Independent public-source rebuild feasibility | High |
| Historical point-in-time completeness | Medium-low until measured |

---

## 3. BioPharmCatalyst: full product anatomy

### 3.1 What BPC actually is

BioPharmCatalyst is a curated biotech event database wrapped in:

- forward and historical calendars;
- public-company, drug, and medical-device screeners;
- company pages;
- market, cash, ownership, analyst, option, and transaction overlays;
- saved portfolios and alerts;
- reports and editorial content;
- a low-volume retail API;
- a higher-volume institutional data product; and
- subscription entitlements.

Its operational moat is history and maintenance, not a difficult algorithm. The valuable loop is:

    discover an event
      → normalize company, asset, indication, stage, date, and source
      → revise it when guidance changes
      → attach market and financial context
      → expose it through filters, pages, alerts, and API

### 3.2 Platform and account layer

| Module | Observed job | Parity requirement | MastermindX upgrade |
|---|---|---|---|
| Global search | Find company pages and product objects | Ticker, company, drug, target, indication, NCT, event | Entity-aware command bar, semantic search, recent actions |
| Account and security | Login, password, email, 2FA | Secure account lifecycle | Passkeys, service accounts, auditable sessions |
| Subscription | Trial, monthly/annual plans, payment | Entitlement enforcement | Capability-based entitlements; no blurred-data theater |
| Portfolio Tools | Create and manage ticker portfolios | Multiple named lists | Watch any graph object, not just tickers |
| Portfolio News | Filter news to selected portfolios | Saved-list feed | Material-delta ranking and duplicate suppression |
| Notifications | Email/browser alerts by type and stage | User-selectable delivery | Materiality, confidence, exposure, causality, snooze |
| Newsletter controls | Topic and cadence preferences | Basic preferences | User-generated scheduled intelligence briefs |
| Discord | Link account/community | Optional integration | Slack, Discord, webhook, and team workspace adapters |
| API key | View/generate key on eligible plan | Key lifecycle | Header auth, scopes, rotation, service accounts, logs |
| Export | Table export | CSV | CSV, JSON, Parquet, query manifest |

Observed BPC alert categories include:

- new FDA-calendar entries, approvals, and complete response letters;
- FDA date changes;
- new device events, approvals, and negative outcomes;
- company press-release headlines; and
- historical catalyst additions.

The upgrade is to alert on changed meaning, not merely changed rows.

### 3.3 Calendar and event products

| BPC product | Core fields and workflow | Parity priority | Better MastermindX expression |
|---|---|---:|---|
| FDA Calendar | Company, drug, indication, phase, date, next catalyst, status, designation, note, trial, market/cash filters | Beta parity | Event Explorer: Upcoming Catalysts |
| PDUFA Calendar | PDUFA date, priority review, AdCom, company, drug, notes, options | Beta parity | Event Explorer: Regulatory |
| Catalyst Impact | Catalyst plus option-implied move and community direction/target | Later | Catalyst Dossier: calibrated scenario and market structure |
| Conference Calendar | Conference, presentation, dates, company, abstract date, indication, drugs, links | Post-beta | Event Explorer: Conferences |
| Earnings Calendar | Date, actual/prior/estimate EPS and revenue, surprises, options | Post-beta | Event Explorer: Earnings with transcript/filing deltas |
| IPO Calendar | Upcoming, priced, historical, quiet-period and lockup dates | Post-beta | Event Explorer: IPO and financing |
| Medical Device Calendar | Device milestones and outcomes | Later | Device sector pack/lens |
| Historical FDA Calendar | Historical phase/FDA catalysts and event-day market reaction | Post-beta | Point-in-time Event Explorer and Time Machine |
| Historical Device Calendar | Historical device events | Later | Pathway-specific historical lens |
| JPM Calendar | Company presentation schedule | Post-beta | Conference lens with portfolio collision alerts |

Observed scale on 2026-08-01:

- FDA Calendar: about 991 rows;
- Drug Pipeline: about 10,026 rows; and
- Historical Catalyst Calendar: about 15,600 rows dating to 2009, excluding Phase 1.

These are dated interface counts, not guarantees of unique entities, complete history, or point-in-time integrity.

### 3.4 Company, pipeline, and market products

| BPC product | Core workflow | Parity priority | Upgrade |
|---|---|---:|---|
| Biotech stock universe | Quotes, market cap, price moves, volume, optionability | Beta if licensed | Catalyst-relative performance and liquidity context |
| Movers | Gainers, losers, unusual volume, treemap/bubbles | Post-beta | Abnormal return/volume versus beta, sector, and catalyst state |
| Company directory | Search/filter issuers | Beta parity | Stable identity and corporate-action history |
| Company/CEO screener | Company and management filters | Post-beta | Management guidance, financing, and trial-execution record |
| Company page | Dashboard, financials, pipeline, analysis, insiders, news, options | Beta dossier core | One evidence-backed dossier with time travel |
| Drug Pipeline Database | Asset, indication, stage, status, NCT, catalyst, designation | Beta parity | Asset-indication ontology and versioned trial graph |
| Medical Device Pipeline | Device, pathway, indication, stage | Later | Separate device-specific pack |
| News and press releases | Company evidence stream | Post-beta dependency | Deduplicated claims and “what changed” extraction |
| SEC filings | Filing list and links | Post-beta; consume landed Corporate spine | Structured clinical, financing, partnership, and guidance deltas |
| Price chart | TradingView chart | Beta if licensed | Catalyst markers, revision overlays, event windows |
| Options chain | Expiry, strike, IV, prices, OI | Later, licensed | Implied distribution, skew, liquidity, and event repricing |

The BPC company route uses hash-based tabs:

    Dashboard
    Financials
    Drugs & Catalysts
    Analysis
    Insider Trades
    News
    Options

The visible company payloads include quote and market statistics, 52-week range, cash estimates, insiders, pipeline, upcoming catalysts, foreign approvals, EPS/revenue charts, analyst targets, filings, press releases, and option chains.

### 3.5 Analysis databases and reports

| BPC module | Visible purpose | Parity priority | MastermindX upgrade |
|---|---|---:|---|
| Trial Insights | Trial design, arms, outcomes, enrollment, timing, sites | Beta facts | Complete temporal diffs and change materiality |
| Historical Probability of Success | Phase/therapeutic-area transition rates | Post-beta baseline | Hierarchical survival model with uncertainty and calibration |
| Cash Database | Cash, operating burn, live cash, runway, liabilities, net cash, EV | Post-beta or beta only if Capital Structure lands | Catalyst-specific runway and financing scenarios |
| Foreign Approvals | International regulatory events | Global expansion | Cross-regulator label and outcome read-through |
| Insider Database | Form 4 history | Post-beta | Cluster/non-plan activity and catalyst-relative timing |
| M&A Database | Acquirer, target, dates, size, payment, status | Post-beta | Target scarcity, premiums, asset comparables |
| Analyst Ratings | Ratings and price targets | Later, licensed | Revision dispersion and analyst calibration |
| Hedge Funds | Selected 13F managers and changes | Post-beta | Specialization, concentration, crowding, point-in-time history |
| BPC portfolios | Vendor model portfolios | Later | Transparent rules and attribution |
| Trading Below Cash | Cash-versus-value report | Post-beta saved lens | Capital-structure-aware screen |
| AI in Biotech | Thematic report | Post-beta generated research | Live modality/target/company graph |
| Key Indication Movers | Indication-oriented movement | Post-beta | Catalyst-adjusted landscape movement |
| Market Cap Analysis | Cohort valuation | Post-beta | Enterprise value and scenario valuation |
| Historical Approvals | Approval history | Post-beta | Source-cited regulatory outcome cohorts |
| Historical PoS | Transition statistics | Post-beta | Calibration explorer |
| Conference reports | Event editorial | Post-beta | Automated evidence-linked change brief |
| Partner watchlist / podcast | Editorial distribution | Later or skip | Collaborative transparent analyst workspaces |

### 3.6 Editorial and community

BPC also offers pre-market and post-market updates, weekly watchlists, educational articles, conference reporting, newsletters, a crash course, glossary, podcast/video, partner material, featured publications, Discord/community features, and a help chatbot.

These establish retention and acquisition value, but they are not the first intelligence moat. MastermindX should derive briefs from the same canonical evidence objects used by dossiers and APIs. One evidence packet should produce:

- a user alert;
- a dossier update;
- a daily portfolio brief;
- a research note;
- a Mastermind answer;
- an API event;
- a webhook; and
- a forward-ledger forecast record.

### 3.7 Pricing and public API

On 2026-08-01, BPC's public sign-up surface showed:

| Plan | Monthly | Annual |
|---|---:|---:|
| Premium | $25 | $240 |
| Elite | $50 | $480 |
| Elite Plus | $75 | $660 |

The advertised trial was seven days. Developer API access was attached to Elite Plus annual access, while institutional data/API service was custom.

The documented developer API exposed:

- FDA Calendar;
- Historical Catalysts; and
- PDUFA Calendar.

It supported JSON and CSV, used a query-string API key, exposed no pagination, and documented a rolling limit of 100 calls per endpoint per 24 hours. The institutional product advertised higher limits, point-in-time history, commercial licensing, and support.

This is a low bar to clear. MastermindX should ship:

- Authorization header credentials;
- scoped keys and service accounts;
- cursor pagination;
- updated-since deltas;
- as-of queries;
- signed webhooks;
- JSON, CSV, and Parquet;
- bulk manifests and checksums;
- schema and model changelogs; and
- explicit internal-use and redistribution entitlements.

---

## 4. BiopharmIQ: the additive comparator

### 4.1 Product thesis

BiopharmIQ is “ZoomInfo for biopharma” more than a catalyst-prediction product. It adds:

1. private-company and non-issuer discovery;
2. decision-maker contacts and corporate email patterns;
3. modality, technology, geography, company-type, size, and phase screening;
4. funding and corporate-development Hot Leads;
5. reusable company cohorts across modules; and
6. sales/BD-oriented list delivery and export.

The platform advertised more than 10,000 companies and about 65,000 contacts. Its underlying public ingredients include ClinicalTrials.gov, SEC filings, FDA material, company sites and releases, conference pages, LinkedIn, and industry sources, with AI extraction and human QA.

### 4.2 Current modules

The current public inventory includes:

- Company Screener;
- Contact Search;
- Funding Activity;
- Hot Leads;
- Clinical Trials;
- Catalyst Calendar;
- Alerts and notifications;
- Saved Lists;
- M&A Activity;
- IPO Tracker;
- PDUFA Calendar;
- Historical PDUFA data;
- Biopharma Meetings;
- Biotech Investors;
- Data Directory;
- guides and shortcuts;
- MCP/API access; and
- custom research/list services.

### 4.3 Important filters and workflow

Company discovery supports:

- public/private status and ticker;
- company type;
- market-cap and employee bands;
- country, region, state, and city;
- technology and modality;
- disease and therapeutic area;
- Boolean search over AI-generated technology descriptions;
- most advanced trial phase; and
- pipeline/product type.

The valuable workflow is cohort algebra:

    build a company cohort
      → reuse it in contacts, trials, funding, catalysts, and alerts
      → save, export, or push downstream

MastermindX should generalize that into composable cohorts. A cohort must be usable by:

- every Explorer;
- every alert;
- the API;
- Mastermind;
- research generation;
- Neural Web context; and
- Prophet shadow studies.

### 4.4 Current commercial model

On 2026-08-01, public pricing showed:

| Plan | Quarterly | Annual | Included export credits |
|---|---:|---:|---:|
| Free Individual | Free | Free | 50 plus 10 unlock credits |
| Individual | $300 | $1,000 | 350 per quarter or 2,000 per year |
| Team | $750 | $2,000 | 1,500 per quarter or 7,500 per year |
| Deluxe | $1,000 | $3,500 | 3,000 per quarter or 20,000 per year |
| Standalone MCP/API | $300 | $1,000 | Commercial data access |

Custom lists remained $2–$6 per company with a $500 minimum and CSV, Excel, or Airtable delivery.

### 4.5 What to import and what to leave

Import:

- the private/public company ontology;
- modality and technology descriptions;
- reusable saved cohorts;
- funding and corporate-development change feeds;
- company-to-trial joins;
- optional BD/contact workspace;
- API/MCP commercialization; and
- private-company discovery operations.

Leave:

- credit-metered CSV as the primary machine interface;
- left-navigation module sprawl;
- a generic CRM visual language;
- contact data as a core investor feature; and
- untraceable AI-generated descriptions.

Contact intelligence is a buy-or-license lane unless it becomes strategically central. Public-company, trial, funding, and hot-lead intelligence can be rebuilt.

---

## 5. Frontend and API forensics

### 5.1 Visible stack

The observed BPC client uses:

- Vue;
- Webpack-split bundles;
- Laravel-style server conventions and route behavior;
- PrimeFlex-style layout utilities;
- Stripe;
- Brevo;
- reCAPTCHA;
- TradingView;
- QuoteMedia;
- a third-party chatbot; and
- Stoplight-style API documentation.

Visible JavaScript bundles included vendor Vue, vendor, application, and page-specific chunks. The frontend is conventional, not a technical moat.

### 5.2 UI grammar

The repeated layout pattern is:

    large left navigation
      → module header and optional calendar/table toggle
      → dense filter drawer
      → server-paginated table
      → customizable columns
      → portfolio/watch controls
      → paywalled or blurred fields

Strengths:

- enormous feature discoverability once learned;
- fast power-user filtering;
- useful table density;
- consistent object links;
- broad export and alert affordances; and
- practical investor terminology.

Weaknesses:

- duplicate top-level applications for saved views of the same objects;
- deep, inconsistent navigation;
- old admin-dashboard visual language;
- little source provenance;
- no visible revision history;
- limited confidence and uncertainty representation;
- weak distinction among fact, estimate, and scenario;
- no time-travel mental model;
- no causal “why this changed” layer;
- excessive dependence on static rows;
- weak mobile hierarchy; and
- contradictions or stale values can coexist without explanation.

### 5.3 Observed internal route families

Ordinary FDA-page traffic exposed route families for:

- drug statuses;
- trial stages;
- share-price bands;
- FDA statuses;
- indication types;
- screener preferences;
- conferences;
- next catalysts;
- FDA-calendar pagination;
- company logos; and
- social or community data.

Other observed route families included:

| Surface | Route family |
|---|---|
| FDA Calendar | /api/fda-calendar |
| Historical Catalysts | /api/historical-catalysts-calendar |
| Drug Pipeline | /api/pipeline-table |
| PDUFA | /api/pdufa-events and /api/pdufa-table |
| Catalyst Impact | /api/catalyst-impact |
| Cash Database | /api/cash-table |
| Company Financials | EPS, revenue, cash-burn, and hedge-fund routes |
| Company Pipeline | device, drug, upcoming catalyst, sale, and foreign-approval routes |
| Company Analysis | analyst rating and target routes |
| Company Evidence | news, press-release, and filing routes |
| Company Market Structure | option-chain routes |

The exact private server implementation remains unknown. The route behavior strongly implies a conventional relational backend with server-side filters, preference persistence, computed/materialized values, and curated tables.

### 5.4 FDA Calendar response contract

Observed fields included:

- company name, ticker, identifiers, market fields, and logo;
- drug ID and name;
- indication and therapeutic grouping;
- stage ID, simplified stage, and status;
- ClinicalTrials.gov identifier;
- catalyst date and display text;
- next-catalyst label;
- FDA status;
- note and press link;
- conference metadata;
- estimated primary completion date;
- analyst fields;
- historical likelihood of progressing;
- historical likelihood of approval;
- estimated live cash and cash months;
- insider, shares, float, and market fields;
- last-updated timestamps;
- Trial Insights link; and
- community or social fields.

Observed filters included:

- portfolio;
- price;
- stage;
- indication;
- catalyst date;
- advisory committee;
- optionability;
- next catalyst;
- FDA status;
- conference;
- shares;
- float;
- market capitalization;
- relative volume;
- enterprise value;
- estimated live cash;
- estimated cash months;
- insider ownership; and
- drug designation.

This response is not evidence of a sophisticated prediction service. It is evidence of a wide denormalized read model optimized for a table.

### 5.5 Other visible schemas

Drug Pipeline:

- company, price, drug, NCT, indication, stage, status, catalyst, date, designation, conference;
- optional market, cash, ownership, and financial columns.

Historical Catalysts:

- company, drug, indication, stage, date, catalyst, conference;
- price at event and event-window movement sparkline.

Catalyst Impact:

- company, drug, indication, stage, event, date, note;
- option expiry, call/put, days to expiry, strike, IV, expected move in dollars and percent, expected up/down levels, bid, ask, last, and open interest;
- historical progression/approval rates; and
- community direction, target, and impact fields.

Cash Database:

- last quarter;
- reported cash and equivalents;
- prior cash;
- operating cash flow;
- monthly cash burn;
- estimated live cash;
- estimated cash months;
- liabilities;
- net cash;
- enterprise value;
- options and notes.

Company Dossier:

- quote and market snapshot;
- pipeline and significant drugs;
- upcoming catalysts;
- approvals;
- financial statements and chart series;
- analyst targets;
- insider trades;
- news, press releases, and filings;
- options; and
- cash/burn.

### 5.6 Reconstruction difficulty

| Layer | Difficulty, 1 easy to 10 hard | Why |
|---|---:|---|
| Pixel-level BPC UI | 2 | Conventional components and dated layout |
| Better house-native UI | 6 | High design standard, responsive information density, many states |
| Auth, billing, preferences | 3 | Existing product-shell capability |
| Table/filter/export parity | 3 | Standard server-side query product |
| Current event ingestion | 5 | Multiple sources and entity mapping |
| Current company dossier | 6 | Cross-domain joins and freshness |
| Historical event reconstruction | 8 | Missing and revised history, silent failure bias |
| Entity resolution | 8 | Company, asset, sponsor, owner, indication, target, trial aliases |
| Reliable clinical/change engines | 8 | Version alignment and adjudication |
| Calibrated PoS/timing/EV | 9 | Sparse outcomes, censoring, PIT leakage, nonstationarity |
| Analyst and correction operations | 8 | Persistent human-in-loop maintenance |

### 5.7 Frontend code disposition

The browser-delivered client is useful, but importing its compiled application would make the build worse.

| Use | Decision |
|---|---|
| Navigation and product inventory | Use as a parity checklist |
| Route, filter, column, and response behavior | Use as a behavioral specification |
| Generic interaction details | Reproduce selectively in the house design system |
| Compiled Vue/Webpack bundles | Do not adopt as a codebase |
| BPC component styling and layout | Do not adopt; replace |
| BPC entitlement and query-key patterns | Do not adopt; redesign |
| Server-returned proprietary notes/history | Do not ingest without data rights |
| Public formulas recovered from displayed inputs/outputs | Rebuild transparently as baselines where useful |

Reasons:

- the bundles are compiled deployment artifacts, not a maintainable source repository;
- components are tightly coupled to BPC's route and payload conventions;
- the legacy navigation and table architecture are the main product weakness;
- the target authenticated product uses a different shared stack and design system;
- a clean implementation can preserve the useful jobs while eliminating duplicate pages; and
- our moat must remain primary-source data, temporal evidence, models, and cross-sector integration.

The frontend forensics reduce requirements risk. They do not reduce the value of a house-native implementation.

---

## 6. Visible engine reconstruction

### 6.1 Historical probability of success

BPC's Historical Probability of Success page described a model based on:

- 3,489 drugs;
- 706 companies;
- 590 indications;
- more than sixteen catalyst stages;
- seventeen broad therapeutic groups; and
- a five-year 2016–2021 historical window.

The displayed table contains phase-transition percentages for each therapeutic group. Its arithmetic reconciles as:

    POP(group, phase)
      = a displayed phase-transition rate
        whose exact cohort denominator is not exposed

    LOA(group, current phase)
      = product of every remaining POP
        from current phase through approval

For example, the visible Oncology row showed approximately:

    Phase 1 to Phase 2       60.87%
    Phase 2 to Phase 3       33.71%
    Phase 3 to Regulatory    54.19%
    Regulatory to Approval   88.73%

The displayed Phase 1 likelihood of approval reconciles arithmetically to:

    0.6087 × 0.3371 × 0.5419 × 0.8873 ≈ 9.87%

The reconstruction does not identify BPC's exact denominator, unit of observation, phase-entry rule, skipped-phase handling, multi-indication counting, silent-discontinuation policy, cohort boundary dates, or whether every displayed stage uses an identical risk set. Those remain UNKNOWN.

This is still a useful transparent baseline. It is not a contemporary asset-level prediction engine because it lacks:

- sample counts and uncertainty on the main product surface;
- censoring and competing-risk treatment;
- asset, sponsor, modality, target, biomarker, design, endpoint, geography, and regulatory covariates;
- calendar-time drift;
- time-to-transition;
- selection-bias correction for silent discontinuations;
- point-in-time feature snapshots;
- calibration reporting; and
- a forward ledger.

The correct response is not to discard it. Reproduce a leakage-safe phase-by-therapeutic-area baseline, publish its sample size and interval, and force every challenger to beat it.

### 6.2 Cash, burn, runway, and net cash

Inspected rows reconcile to the following candidate display formulas:

    monthly_cash_burn
      = latest quarterly operating cash flow / 3

    estimated_live_cash
      = last reported cash
        + monthly_cash_burn × elapsed months

    cash_months
      = estimated_live_cash / absolute monthly_cash_burn

    net_cash
      = estimated_live_cash - total liabilities

This produces several predictable errors:

- cumulative year-to-date versus discrete-quarter operating-cash-flow risk in Q2/Q3 unless BPC first-differences upstream;
- working-capital and milestone lumpiness treated as recurring burn;
- financing, debt draws, offerings, warrants, milestones, and partnerships ignored until manually updated;
- total liabilities treated as debt;
- positive operating cash flow can create nonsensical “runway”;
- catalyst-specific timing is absent; and
- forecast uncertainty is hidden.

Before treating the reconstruction as exact, a parity audit must disclose the number of company-quarters tested, fiscal-calendar mix, discrete-quarter derivation, elapsed-month convention, treatment of post-quarter financings, and absolute/relative reconciliation error. Until then these are strong candidate formulas, not identified backend code.

The MastermindX replacement must be supplied by the shared Capital Structure Intelligence plane:

    cash next month
      = cash this month
        - operating burn
        + financing proceeds
        + partnership and milestone receipts
        - debt and milestone payments

Each term is a distribution or dated scenario, not a single extrapolated scalar. BioCatalyst consumes the resulting capital-structure context and asks a domain-specific question:

> What is the probability that this company reaches this catalyst without a financing event, covenant problem, or material dilution?

### 6.3 Catalyst Impact and option-implied movement

The client displays:

- implied volatility;
- expiry and days to expiry;
- strike;
- expected dollar and percent movement;
- expected up/down prices;
- option quotes and open interest;
- community direction and price target; and
- historical probability fields.

The server returns the expected-move values. The exact formula was not exposed. A standard implementation might use spot, annualized IV, and square-root time, or a near-the-money straddle, but that remains INFERRED and must not be represented as BPC's exact method.

The stronger engine should distinguish:

- option-implied move;
- physical probability of clinical outcomes;
- market probability inferred from valuation;
- expected abnormal return by scenario;
- liquidity and slippage;
- volatility crush;
- skew and tail asymmetry;
- financing before or after the event; and
- crowd belief versus contributor calibration.

### 6.4 Calendars, historical events, and company intelligence

The remaining visible product is primarily:

- normalized event records;
- company/drug/trial joins;
- editorial notes;
- server-side screening;
- history;
- market overlays;
- source-link attachment;
- user preferences;
- alert rules; and
- entitlement checks.

That is not dismissive. High-quality temporal curation is hard. It simply locates the moat correctly: in data operations and memory rather than mysterious math.

---

## 7. The build thesis

### 7.1 Product name and promise

Working name: **BioCatalyst Intelligence**

User promise:

> Know what changed, what comes next, how likely it is, what the market implies, and whether the company can financially survive to the event.

The product should answer five questions for every relevant company:

1. What are the next material catalysts, and how certain are their dates?
2. What changed in the trial, endpoint, enrollment, competition, regulatory, or company evidence?
3. What is the calibrated distribution of biological and regulatory outcomes?
4. What is the scenario distribution for value and market response?
5. Can the company reach the event without financing or unacceptable dilution?

### 7.2 Three expressions of one graph

The same intelligence graph serves:

1. **Human cockpit** — compressed portfolio and market awareness.
2. **Research dossiers** — deep company, asset, trial, catalyst, and competitive analysis.
3. **Machine context** — typed, time-safe packets for Mastermind AI, Neural Web, Prophet, alerts, APIs, and sector-to-sector reasoning.

There should be no separate “AI version” of the data. The AI reads the same claims, changes, receipts, uncertainties, and forecasts that the user can inspect.

### 7.3 Why this can become a moat

The public ingredients are accessible. That lowers entry cost but does not eliminate defensibility. The moat compounds through:

- stable identity and alias history;
- temporal ownership of assets;
- every trial version and disclosed date revision;
- outcome adjudication;
- false-positive and correction history;
- comparable-set quality;
- source-to-claim provenance;
- calibrated forecast and analyst track records;
- cross-domain financing and market-response joins;
- workflow memory and saved cohorts;
- customer annotations and scenarios; and
- a reusable sector intelligence kernel.

The product becomes harder to copy every day it records what changed, what it believed, why it believed it, and what happened.

---

## 8. Unmatched product design: the Sector Intelligence Operating System

### 8.1 Design position

The target is not “a nicer biotech dashboard.” It is an institutional research instrument with consumer-grade clarity.

The experience should feel:

- calm under extreme information density;
- fast enough to become muscle memory;
- opinionated without hiding uncertainty;
- cinematic only where motion reveals time, dependency, or state;
- coherent from a one-line alert to a full evidence audit;
- equally native on dark and light themes;
- unmistakably MastermindX; and
- extensible across sectors without becoming a generic template.

The anti-reference is the legacy left-rail admin application. The positive reference is a modern operating system: a stable global shell, a sector-specific instrument panel, and a consistent object grammar.

### 8.2 One suite, many desks

The shared global product switcher should expose a connected family:

    MastermindX
    ├── Market Intelligence
    ├── BioCatalyst Intelligence
    ├── Government & Procurement Intelligence
    ├── Shipping & Trade Intelligence
    ├── Mining Intelligence
    ├── Energy Intelligence
    └── Agriculture Intelligence

This is not a list of unrelated websites. The suite shares:

- authentication and entitlements;
- universal search and command palette;
- saved entities and cohorts;
- alerts and assignments;
- evidence and provenance drawers;
- dossiers and timelines;
- comparison workspaces;
- scenario objects;
- Mastermind conversation;
- API, MCP, webhooks, and audit logs;
- global portfolio and exposure context; and
- a graph of relationships among sectors.

Each desk changes the ontology, models, domain lenses, and visual signature—not the core interaction grammar.

The shared experience is defined by the same research moments, not by giving every desk the same dashboard:

| Research moment | BioCatalyst | Government & Procurement | Shipping & Trade |
|---|---|---|---|
| Find | Company, asset, indication, trial | Agency, program, solicitation, vendor | Vessel, port, lane, importer/exporter, commodity |
| Build cohort | Mechanism/phase/indication universe | Agency/vehicle/NAICS/vendor universe | Route/commodity/port/company universe |
| Inspect | Company/Asset/Trial/Catalyst Dossier | Vendor/Program/Award Dossier | Route/Port/Flow Dossier |
| Detect change | Endpoint, date, status, safety, financing | Solicitation, award, modification, protest, recompete | Dwell, diversion, capacity, manifest, rate, sanction |
| Verify | Registry, regulator, filing, document span | Procurement record, budget, filing, document span | Manifest, customs, port, AIS/source receipt |
| Model consequence | Outcome/timing/financing/value lattice | Win/renewal/revenue/timing cascade | Flow/capacity/inventory/margin scenario |
| Triage action | Watch, investigate, prepare for financing risk | Watch, qualify, investigate, prepare for recompete | Watch, reroute research, investigate exposure |

D0 must prove this matrix deeply with production-shaped fixtures from BioCatalyst, Government & Procurement, and Shipping & Trade. It must also run one production-shaped critical workflow and the complete trust/state atlas through every named desk: Mining permit-to-production, Energy outage/capacity-to-basis, and Agriculture weather/acreage-to-export. Detailed flagship mockups may remain limited to the first three, but no promised desk can pass on a one-line metaphor. A sector switcher plus shared colors is not a suite.

### 8.3 Primary BioCatalyst navigation

The primary navigation should be:

    Cockpit
    Explore
      Companies
      Catalysts
      Trials & Landscape
    Changes
    Research
    Data / API

Global search, portfolio, saved cohorts, current as-of time, data health, sector switcher, and Mastermind live in the utility shell.

The following are not top-level applications:

- FDA Calendar;
- PDUFA Calendar;
- Earnings Calendar;
- Conference Calendar;
- IPO Calendar;
- Historical Calendar;
- Cash Database;
- Insider Database;
- Hedge Funds;
- M&A; and
- Foreign Approvals.

They are saved lenses inside Event Explorer or Company Explorer.

### 8.4 Signature interaction grammar

The suite needs recognizable interaction primitives, not decorative novelty and not biotech nouns masquerading as shared components.

#### A. Decision Sentence

Every glance-tier object uses one compact anatomy:

    Change label (≤6 words) · Meaning (≤12 words) · Action chip

Examples:

- “Enrollment target increased · More participants are now required · Verify”
- “Primary endpoint changed · Prior comparisons may not fit · Verify wording”
- “Competitor stopped for safety · Space opened; class risk rose · Compare evidence”

The one-line sentence is the first object in every dossier, alert, and cockpit item. Panel-level freshness renders once in the header; a row repeats freshness only when it is exceptionally stale, delayed, or temporally distinct. Quantitative axes, model receipts, and technical vocabulary belong behind Inspect and Study.

The action chip comes from a role-aware, non-trading vocabulary—not free-form model prose:

| Role | Permitted glance actions |
|---|---|
| Investor/research user | Watch, Verify, Compare, Review risk, Open dossier |
| Analyst | Investigate, Adjudicate, Compare, Model, Escalate review |
| BD/strategy | Qualify, Map landscape, Compare, Assign research |
| Operations/admin | Assign, Retry, Request access, Resolve, Open incident |

No glance action says buy, sell, size, or raise rank. Tenant roles and permissions determine the visible vocabulary; the underlying fact sentence stays the same.

#### B. Temporal Braid

The shared primitive represents exact points, uncertain windows, revisions, dependencies, and collisions on a scale-preserving chronology. It does not know what a PDUFA date, recompete, vessel call, assay, or harvest is.

BioCatalyst's domain rendering is the **Catalyst Ribbon**, spanning disclosed guidance, trial milestones, regulatory dates, financing capacity, competitor events, and outcomes.

It must show:

- exact dates as points;
- month, quarter, half-year, and fuzzy guidance as honest ranges;
- confidence through edge definition and fill density;
- revisions as connected prior positions rather than overwritten dates;
- source inspection through the same click/tap claim anchor on every device;
- portfolio collisions;
- runway exhaustion and financing windows;
- regulatory dependencies; and
- competitor events on adjacent lanes.

Other domain renderings:

- Government & Procurement: Program Cascade from appropriation to solicitation, award, obligation, modification, and recompete;
- Shipping & Trade: Flow Field across departure, route, diversion, port dwell, discharge, and customs;
- Mining: Project Gate Braid across resource, permit, feasibility, financing, build, and production;
- Energy: molecule/electron path across capacity, outage, storage, basis, and delivery; and
- Agriculture: Supply Wheel across season, weather, acreage, yield, stocks, and export.

#### C. Evidence Thread

The shared claim-level provenance primitive pins identically across desktop, tablet, and mobile. BioCatalyst renders it as an always-available **Evidence Spine**.

Selecting any claim highlights:

- original source span;
- source and retrieval metadata;
- prior values;
- contradictions;
- transformation;
- analyst review;
- downstream forecasts; and
- affected alerts.

The user never hunts for a separate “sources” tab. On a narrow screen the thread collapses to a pinned layer, not a detached sheet that loses the claim anchor.

#### D. Impact Trace

The shared dependency primitive answers: “If this changed, what else moved?”

BioCatalyst's animated introduction is the **Change Pulse**. New evidence briefly travels to affected endpoint and date objects, plus any installed financing, probability, competition, and valuation modules, then settles into a persistent inspectable trace. Reduced-motion mode reveals the same trace without animation; absent modules produce no phantom destinations.

#### E. Scenario Lattice

The shared primitive knows only typed scenario dimensions, dependency edges, branch selection, assumptions, comparison layers, and uncertainty/missing states. It contains no clinical, financing, valuation, vessel, tender, or commodity semantics.

BioCatalyst's **Clinical Scenario Lattice** keeps these domain-owned causal bands aligned instead of blending them into one impressive cone:

    Clinical / regulatory outcome
      ↕
    Event timing
      ↕
    Financing and share count
      ↕
    Fundamental value
      ↕
    Market response

Selecting a branch reveals its assumptions and consequence path. The current market-implied range and prior forecast remain optional domain comparison layers. The glance tier shows only the Decision Sentence; the Clinical Scenario Lattice is Inspect/Study and installs only when its underlying engines exist. The facts-first beta renders evidence and disclosed-state comparisons without fabricated probability/value bands.

#### F. Query Lens

Every table, graph, and dossier supports current state or “changes since”:

- yesterday;
- last filing;
- last earnings call;
- last model run;
- user-selected date; or
- last saved view.

The same query can become a saved cohort, alert, brief, export, API request, or webhook.

#### G. Research Tray

Users can pin claims, charts, evidence, entities, and scenario branches while moving through a long dossier or across companies. The tray preserves comparison context, feeds a research packet, and gives Mastermind a bounded user-selected evidence set.

### 8.5 Cockpit

The flagship is an **Attention Field**, not a permanent sidebar/card/right-rail dashboard.

Desktop composition:

    ┌──────────────────────────────────────────────────────────────────────┐
    │ Command | Portfolio | Sector | As-of | Health | Collapsible lenses  │
    ├──────────────────────────────────────────────────────────────────────┤
    │ NOW                                                                  │
    │ A scale-preserving temporal stream crossed by portfolio exposure     │
    │ bands. Changes, event windows, financing limits, and competitors     │
    │ occupy their real relative time and cluster only when they collide.  │
    │                                                                      │
    │  ◀ recent changes ───── today ───── event windows ───── later ▶      │
    │  ━ held position   endpoint edit        Phase 3 window               │
    │  ─ competitor            safety stop                                 │
    │  ━ watched name                cash-risk band                        │
    ├──────────────────────────────────────────────────────────────────────┤
    │ Select any trace → inline Decision Sentence + Impact Trace           │
    │ Pin to Research Tray | Open dossier | Compare | Watch | Assign       │
    └──────────────────────────────────────────────────────────────────────┘

Saved lenses live in the command bar and a collapsible dock. Selecting an object opens an inline inspection layer rather than permanently surrendering a third of the viewport to a generic “intelligence rail.”

The facts-first field is useful without a single model output. Its launch lanes contain:

- user-owned portfolio/watchlist membership;
- exact source changes and disclosed event intervals;
- current lifecycle/status;
- evidence coverage, contradictions, and freshness;
- linked competitors and user-saved cohorts; and
- landed Corporate/Capital facts only when those dependency planes are healthy.

Its default layout is temporal, not a covert learned ranking: portfolio/watchlist lanes are user-defined; objects are ordered by disclosed/observed time, source publication time, then stable ID. Probability change, expected payoff, financing survival, inferred materiality, and competitive model read-through install as visibly labeled optional bands only when their engines exist and their exact attention consumer has earned the required tier. Until then they cannot reorder the default field.

Density mechanics are part of the contract:

- default window is the last 30 days of changes through the next 180 days; presets are 30d, 90d, 180d, and 1y;
- semantic zoom moves from exact events to week/month clusters while preserving fuzzy-window width and disclosed bounds;
- a default eight visible lanes collapse overflow into named groups with counts; user-pinned lanes never disappear;
- colliding events form an expandable cluster with deterministic chronological order and an exact synchronized list;
- events outside the viewport that meet a user-authored alert/watch rule produce an offscreen marker, never an algorithmic urgency claim;
- the same selection and focus exist in a synchronized accessible queue/list view;
- keyboard order follows lane, time, stable ID; arrow keys navigate the field and Enter opens the same claim anchor; and
- when a month is saturated, aggregation increases before spacing is distorted—empty space never pretends that clustered events are far apart.

Tier-one items use the compact Decision Sentence:

- “Readout narrowed to October · Disclosed timing range tightened · Verify source”
- “Primary endpoint changed · Prior comparisons may not fit · Verify”
- “Completion moved to Q4 · Disclosed timing changed · Verify source”
- “Competitor stopped for safety · Space opened; class risk rose · Compare evidence”
- “FDA meeting added · Engagement increased, not decision certainty · Watch”

Technical receipts move into the evidence drawer.

### 8.6 Universal Event Explorer

Event Explorer combines table, calendar, timeline, and landscape views over one query.

Required lenses:

- Upcoming Catalysts;
- Regulatory / PDUFA;
- Trial Readouts;
- Enrollment and Endpoint Changes;
- Earnings;
- Conferences;
- IPO and Financing;
- Patent and Exclusivity;
- Historical Outcomes; and
- Medical Devices later.

The facts-first beta enables Upcoming Catalysts, Regulatory, Trial Readouts, and Enrollment/Endpoint Changes. Earnings, Conferences, IPO/Financing, Patent/Exclusivity, Historical Outcomes, and Medical Devices install only with their registered source planes; the navigation does not show beautiful empty promises.

Every lens preserves the same:

- filter state;
- selected columns;
- grouping;
- as-of time;
- cohort;
- sharing URL;
- export manifest; and
- alert definition.

The user can turn any query into a saved lens and, as the corresponding product tiers land, a scheduled brief, API call, or webhook without rebuilding it.

### 8.7 Company Dossier

Header:

    Company / ticker / security
    Price / enterprise value when licensed / as-of
    Watch | Compare | Ask | Create scenario when available

Glance tier:

    Decision Sentence
      Change label · Meaning · Action chip

Secondary Inspect strip:

    Next catalyst
    Disclosed date window / current status
    Last material change
    Evidence coverage / contradictions
    Evidence freshness

The facts-only strip ships first and is collapsed to the most consequential two fields by default. Probability, runway/dilution, EV, competition, and market-setup modules appear progressively only when their source/engine exists; unavailable modules are absent or explicitly unavailable, never zero-filled. It expands on request and never asks a cold user to interpret abstract metrics before receiving a plain-language stance.

Main sections:

1. Plain-language thesis and current changes.
2. Catalyst Ribbon.
3. Pipeline and asset-indication tree.
4. Trials and protocol changes.
5. Cash, financing, and capital structure.
6. Competitive landscape.
7. Regulatory, safety, label, patent, and exclusivity timeline.
8. Earnings, transcript, filing, and management-statement deltas.
9. Partnerships and deal economics.
10. Ownership and insiders.
11. Market structure and historical reactions.
12. Evidence and revision ledger.

The beta ships the evidence-backed company/pipeline/trial/regulatory/change sections. Capital, earnings/documents, partnership, IP, ownership, market-reaction, and scenario sections appear only when their registered producers land; the continuous dossier does not reserve giant empty panels for them. Use a sticky section navigator and one continuous reading path, not seven disconnected tabs. The Research Tray lets users pin the trial, financing, competition, claim, or chart they need to keep visible, preventing the continuous dossier from becoming an elegant wall of content.

### 8.8 Catalyst Dossier

Header:

    Event title | asset | indication | company
    Disclosed interval | predictive date if available | state | freshness | watch

Glance tier:

    Decision Sentence
      Change label · Meaning · Action chip

Secondary Inspect strip:

    Disclosed date/state
    Last revision
    Registry/regulator status
    Evidence confidence

This facts-only strip is the launch composition. Probability, expected payoff, financing survival, competitive-model axes, technical setup, and the Clinical Scenario Lattice install progressively behind capability and authority receipts. No combined visualization may imply that biology, timing, financing, fundamental value, and market response are one directly observed probability.

Later Clinical Scenario Lattice branch table:

| Dimension | Failure | Delay | Partial success | Full success |
|---|---:|---:|---:|---:|
| Probability | Distribution | Distribution | Distribution | Distribution |
| Fundamental value | Range | Range | Range | Range |
| Market response | Range | Range | Range | Range |
| Financing path | Scenario | Scenario | Scenario | Scenario |
| Next event | State transition | State transition | State transition | State transition |

Evidence stack:

- original issuer guidance;
- trial design and endpoint hierarchy;
- enrollment and site trajectory;
- protocol and registry changes;
- comparable outcomes;
- regulator history;
- safety and label evidence;
- competitor read-throughs;
- financing context; and
- forecast revision history.

### 8.9 Trial and Competitive Landscape

Desktop:

    ┌─────────────────────┬─────────────────────────────┬──────────────────────┐
    │ Filters             │ Graph / timeline / table    │ Selected object      │
    │ Indication          │ Company → Asset → Target    │ Trial design         │
    │ Target / modality   │ → Indication → Trial        │ Endpoint hierarchy   │
    │ Phase / status      │ → Comparator → Catalyst     │ Enrollment / sites   │
    │ Endpoint / biomarker│                             │ Changes / probability│
    │ Geography           │ Historical as-of scrubber   │ Sources              │
    └─────────────────────┴─────────────────────────────┴──────────────────────┘

The graph is an analytical control, not decoration:

- node size can represent enrollment or addressable population;
- node color represents phase, status, or outcome;
- edges represent shared target, indication, comparator, arm, biomarker, or sponsor;
- time travel reconstructs the competitive field;
- table view remains available;
- every saved landscape can become a competitive-position input; and
- graph layout never substitutes for exact data.

### 8.10 Change Tape and Alert Center

Alert families:

- catalyst date introduced, narrowed, delayed, removed, or resolved;
- endpoint added, removed, reordered, or materially rewritten;
- enrollment target, status, completion date, or study design changed;
- site expansion, contraction, or geographic shift;
- FDA designation, meeting, hold, safety, label, advisory, or decision event;
- competitor result or program discontinuation;
- offering, ATM, shelf, warrant, convertible, debt, or partnership change;
- runway crossing the expected catalyst window;
- management statement contradicting prior disclosure;
- patent, exclusivity, or litigation event;
- material forecast or expected-value revision;
- unusual price, volume, volatility, skew, or option activity near an event; and
- source, parser, or identity-quality degradation.

Each card must answer:

    What changed?
    Why does it matter?
    What was the old value and new value?
    Which company, asset, catalyst, portfolio, and model are affected?
    How material and how certain is it?
    What is the source?
    What should the user inspect next?

Customer triage is a product state vector, not one impossible linear enum:

| Axis | States |
|---|---|
| read_state | unread, read |
| assignment | current owner is unassigned or assigned(user/team); reassignment is retained in assignment_history |
| workflow_phase | new, acknowledged, investigating, awaiting_evidence, closed |
| notification_state | active, snoozed_until, muted_by_rule |
| resolution_outcome | open, dismissed_with_reason, resolved_with_note, superseded_by_correction |

Allowed transitions are explicit: `workflow_phase = closed` if and only if `resolution_outcome != open`; closing requires an outcome; reopening sets the outcome back to `open`, moves the phase to `acknowledged`, and appends a reopen-history event without discarding owner/history. Reading never assigns; snoozing never closes; dismissal requires a reason but preserves canonical truth. Bulk actions declare exactly which axes they mutate, show the affected count, support undo where safe, and never convert “read” into “resolved.”

The system supports bulk acknowledgment, assignment, comments, due dates, saved response rules, duplicate clustering, and portfolio/team views. A corrected alert retains its original text, correction receipt, affected users, and model consequences.

Analyst adjudication is a separate connected lifecycle:

    machine candidate
      → confidence route
      → analyst review
      → accept / correct / split / merge / reject
      → publish correction
      → propagate and audit

Customer dismissal never alters canonical truth. Analyst correction never erases the prior published state.

### 8.11 Research Workbench

The workbench supports:

- side-by-side companies, assets, indications, and trials;
- comparable-set construction;
- evidence notebooks;
- hypothesis and scenario objects;
- saved query manifests;
- time-aligned outcome and market-reaction studies;
- collaborative annotations;
- chart and table composition;
- export to a research packet; and
- citation-preserving Mastermind conversations.

Mastermind should be embedded as an investigator, not a floating chatbot pasted over the product. It can:

- explain the current dossier;
- retrieve evidence;
- compare versions;
- build a sourced comparison set;
- summarize contradictions;
- run bounded scenarios;
- generate a research packet; and
- state what data is missing.

### 8.12 Mobile

Mobile uses the same object hierarchy in a different composition:

- command search and portfolio context remain one tap away;
- the Catalyst Ribbon preserves a compact scale and fuzzy-window width, with vertical detail expanding below the selected time segment;
- the Decision Sentence remains a single-column first object;
- secondary axes appear one at a time in a swipeable Inspect strip, not a two-column metric wall;
- filters open in a full-screen sheet with applied-state summary;
- every claim uses the same click/tap anchor and Evidence Thread pins as a persistent layer;
- tables become priority-column cards with horizontal expansion only on demand;
- comparison mode pins one baseline header and renders selected-object delta rows; the baseline never disappears behind a swipe;
- the Research Tray becomes a bottom dock with a visible pinned-item count;
- alert actions stay thumb-reachable; and
- no critical meaning depends only on hover.

Only one modal layer occupies the narrow viewport. Opening Evidence Thread collapses the Research Tray to its count dock; opening filters closes Evidence after preserving its claim anchor; alert actions remain inline or replace the current layer with explicit back behavior. Closing any layer restores focus to the invoking claim/control. Evidence Thread outranks Research Tray, which outranks optional filters; critical error/permission dialogs pre-empt all and restore the prior stack when dismissed.

### 8.13 Historical mode

Changing as-of time is a mode transition, not a quiet filter.

Historical mode must provide:

- unmistakable persistent chrome;
- “Knowledge frozen at” with timezone;
- separate observed, published/effective, and knowledge-cutoff explanations;
- a “Compare with now” split;
- prior-versus-current ghosting;
- an always-visible return-to-now action;
- disabled live-only actions;
- scenarios cloned from the historical state rather than mutating live scenarios;
- alerts saved as historical queries, never accidentally activated as live rules; and
- historical evidence and model versions preserved throughout navigation and Mastermind conversation.

Changing sector or opening a deep link retains historical mode only after an explicit confirmation if the destination supports it.

### 8.14 Visual system

The final palette and typography must be chosen by the designated high-judgment design lane against the global MastermindX system. D0 must turn the direction below into a versioned token matrix, not leave it as adjectives:

- deep graphite and mineral-black foundations rather than generic navy;
- warm near-white reading surfaces rather than stark white;
- a biopharma spectral accent spanning cyan through violet, used sparingly for identity and dependency flow;
- amber for uncertainty and timing drift;
- red reserved for actual adverse evidence, not decorative heat;
- green reserved for confirmed favorable outcomes, not “interesting”;
- tabular numerals only for figures;
- strong editorial typography for dossier narrative;
- low-radius structural panels mixed with a few distinctive curved timeline forms;
- fine evidence connectors and temporal ghosting as the visual signature; and
- iconography derived from object roles, never a random library soup.

Required D0 token and component contract:

- spacing and layout grid;
- type family, scale, weight, line-height, numeric face, and Chinese pairing;
- compact, standard, and research density modes;
- semantic color channels;
- fact, estimate, and scenario shapes;
- current, historical, fresh, stale, contradictory, selected, focused, disabled, and restricted states;
- focus rings and keyboard movement;
- selection and pinning;
- chart and scale grammar;
- wrapping, truncation, overflow, and long-label rules;
- elevation and layering;
- motion duration, easing, sequence, and reduced-motion substitution;
- empty/loading/error/correction behavior; and
- responsive breakpoints and composition rules.

### 8.15 Failure and trust grammar

The suite shares explicit failure states:

| State | Stable meaning | System response | Available user actions | Downstream consequence |
|---|---|---|---|---|
| Unknown | The system does not know | Name missing evidence and coverage | Inspect sources, report evidence, watch for update | Block dependent inference |
| Unavailable | Registered source/data cannot currently supply it | Explain source/data absence and lawful alternatives | Retry, inspect source health, continue with unaffected data | Block absent fields only |
| Stale | Last good value exceeds freshness budget | Stamp age, source health, and affected outputs | Retry, inspect last good evidence, subscribe to recovery | De-escalate/suppress freshness-sensitive outputs |
| Contradictory | Credible sources disagree | Show claims side by side; preserve both | Compare evidence, assign review, watch resolution | Abstain where conflict is decision-relevant |
| Permission-limited | User cannot inspect/export underlying data | Explain entitlement without leaking restricted data | Request access, use permitted summary | Block restricted evidence/export |
| Parser-degraded | Source arrived but extraction is unreliable | Show raw receipt; suppress affected derivations | Inspect raw evidence, retry, open incident | Derived claims unavailable until repaired |
| Correction-pending | Material issue is under review | Preserve prior state and correction receipt | Subscribe, inspect issue, add evidence | Flag or suppress affected consumers |
| Partially loaded | Independent regions are ready | Render stable regions and name missing ones | Retry missing region, continue, report issue | Unaffected regions remain usable |
| No matching data | Query is valid but empty | Preserve query and explain coverage | Relax a named filter, save/watch query | No result; never substitute near matches silently |

Every state has a shape/icon, plain copy, consequence, next action, evidence behavior, and API status. Red is reserved for adverse evidence, not ordinary technical failure.

### 8.16 Bilingual content contract

D0 must include:

- canonical English and Chinese domain-term registry;
- source-language preservation and translated-summary rules;
- paired glance-tier word budgets;
- Chinese font metrics and line-height;
- long-label and mixed-script fixtures;
- date, number, currency, unit, company, drug, and regulator formatting;
- acronyms with first-use expansion;
- no raw English machine states inside Chinese copy;
- data-tip English/Chinese parity;
- fallback when a translation is missing; and
- review by a domain-fluent reader, not only screenshot presence.

### 8.17 Design production process

Each flagship surface follows:

1. production-data content model;
2. exact interaction specification;
3. shared token matrix and state-atlas harness;
4. cross-sector fixture pass;
5. dark, light, Chinese, tablet, and mobile mockups;
6. committed reference images;
7. implementation by the designated build lane;
8. browser verification against the references;
9. stress cases with long labels, nulls, stale sources, contradictions, permissions, and corrections;
10. accessibility and keyboard review;
11. performance review; and
12. final live visual audit.

No flagship surface is handed off as prose alone.

---

## 9. System architecture

### 9.1 Topology

    OFFICIAL AND LICENSED SOURCES
      ClinicalTrials.gov / AACT
      FDA / openFDA / Drugs@FDA / Orange Book / Purple Book
      SEC EDGAR / issuer IR / corporate documents
      literature / patents / grants / market data
      licensed options, consensus, contacts, and commercial datasets
                         │
                         ▼
    IMMUTABLE RAW AND DOCUMENT PLANE
      content hashes / source rights / fetch receipts / watermarks
                         │
                         ▼
    PARSING AND EVIDENCE PLANE
      documents / spans / structured records / parser versions
                         │
                         ▼
    IDENTITY AND TEMPORAL KNOWLEDGE GRAPH
      companies / securities / assets / targets / indications / trials
      regulatory applications / catalysts / financing / ownership / evidence
      valid time / system time / contradictions / review state
                         │
                         ▼
    DOMAIN ENGINES
      trial changes / timing / PoS / comparables / competition / regulatory
      safety / patent / partnership / financing survival / EV / market response
                         │
                         ▼
    VERSIONED INTELLIGENCE CONTRACTS
      feature snapshots / forecasts / outcomes / alerts / sector packets
                         │
               ┌─────────┼──────────┬─────────────┐
               ▼         ▼          ▼             ▼
             Product   API/MCP   Neural Web     Prophet
               │         │          │             │
               └─────────┴──── Mastermind AI ─────┘

### 9.2 Storage

Recommended logical storage:

- object storage for immutable raw responses, full documents, and bulk snapshots;
- PostgreSQL for bitemporal canonical entities, claims, events, contracts, and workflow state;
- columnar Parquet and ClickHouse for feature history, event studies, screening, and model evaluation;
- search index for lexical retrieval;
- vector index for evidence and comparable retrieval;
- graph projections for competitive and ownership relationships;
- append-only ledgers for forecasts, outcomes, alerts, and authority decisions; and
- Redis or equivalent only for caches and queues, never canonical truth.

The repository should carry compact contracts, model cards, fixtures, manifests, and product snapshots—not the full raw corpus.

### 9.3 Service boundaries

| Service / plane | Owns | Does not own |
|---|---|---|
| Source-specific ingestion owner | Fetch, hash, watermark, retry, and license metadata for its registered sources | Another plane's sources or downstream authority |
| Corporate Intelligence Spine | Generic issuer documents, spans, transcripts, generic company events, and retrieval once landed | ClinicalTrials.gov/FDA ingestion or biopharma ontology |
| Capital Structure Intelligence | Instruments, cash, burn, financing capacity, dilution | Clinical success or catalyst value |
| BioCatalyst domain | ClinicalTrials.gov/FDA source lanes, biopharma identity, asset-indication-trial-regulatory graph, domain forecasts, and its forecast/outcome ledger | Generic SEC/document re-ingestion, capital truth, or house authority |
| Market data | Quotes, corporate actions, options, benchmarks | Clinical forecasts |
| Sector Interface Kit | Contract schemas, connector SDK/helpers, temporal/evidence interfaces, read-side adapters, observability interfaces, and shared UI primitives | Canonical domain data, prediction/outcome ledgers, identity truth, retrieval stores, or authority decisions |
| Neural Web | Constitutional authority policy, A5 tier governance, cross-domain context/contradiction, and read-side federation across registered ledgers | Domain source ingestion, domain-ledger writes, or qledger ownership |
| Prophet | Existing technical selection and permitted conditioned probabilities | Raw document retrieval |
| Mastermind AI | Tool-mediated synthesis, comparison, explanation, and scenarios over registered APIs | Canonical retrieval storage or untraceable score origination |
| Product shell | Auth, billing, user state, saved queries/cohorts, watchlists, alerts, and UI framework | Domain truth |
| Operations plane | Persistent schedulers, queues, migrations, credentials, watermarks, storage lifecycle, and incident response | Scientific interpretation or model authority |

The qledger remains QI-owned. Each sector pack keeps its own domain forecast/outcome ledger. Neural Web supplies the constitutional tier language and federated read-side query layer; it does not migrate those stores into a universal writer.

### 9.4 No direct database coupling

Consumers read versioned contracts, not internal tables. This prevents the first successful biotech prototype from hard-coding itself into Prophet, HigherGov, Shipping, or every future sector.

The external contract family is the stable layer. Storage tables and model implementations may evolve behind it.

---

## 10. Reusable Sector Intelligence Kernel

### 10.1 Boundary

The kernel must know nothing about trials, PDUFA, wells, vessels, tenders, mineral deposits, or crop yields.

“Kernel” means an interface kit, not a central service or universal database. It provides:

- contract schemas and compatibility fixtures;
- connector SDKs, receipt/watermark helpers, and source-registration interfaces;
- bitemporal, evidence, correction, and provenance helper types;
- identity-link interfaces without owning canonical identity rows;
- feature/prediction/outcome envelope interfaces without owning the ledgers;
- read-side federation and query adapters over registered stores;
- observability and health interfaces;
- shared API conventions; and
- shared product-shell and UI primitive contracts.

It explicitly does **not** own immutable source corpora, domain claims/events, evidence spans, entity truth, retrieval indexes, saved-query/user state, prediction/outcome ledgers, or authority decisions. Those remain with the registered source plane, sector pack, product shell, QI, or Neural Web constitution named by the one-writer map.

Each sector pack implements:

    SectorPackV1
      entity_types()
      event_types()
      source_adapters()
      normalizers()
      resolution_rules()
      feature_definitions()
      outcome_policies()
      model_registry()
      card_specs()
      authority_caps()

Each implementation declares its canonical producer, artifact/store, cadence, reader contract, and authority cap. The kit validates those declarations; it never becomes a second writer.

### 10.2 Sector packs

| Pack | Domain-owned objects and events | Cross-sector edges |
|---|---|---|
| Biopharma | asset, target, indication, trial, endpoint, regulatory application, catalyst | procurement, grants, manufacturing, shipping, patents, energy inputs |
| Government / Procurement | agency, program, solicitation, contract, award, budget line, vendor | company revenue, defense supply chain, grants, policy |
| Shipping & Trade | vessel, port, lane, manifest, commodity flow, customs event, freight rate | inventory, supplier, sanctions, demand, commodity pricing |
| Mining | project, deposit, resource, assay, permit, feasibility stage, offtake | equipment, energy, government permits, shipping, commodity balance |
| Oil & Gas | basin, well, rig, permit, completion, pipeline, storage | services, shipping, refining, regulation, macro supply |
| Agriculture | crop, region, acreage, yield, weather event, stock, export flow | fertilizer, energy, shipping, food companies, inflation |

The kernel contract suite must pass against BioCatalyst and a synthetic second sector pack before W8. This is the best defense against accidentally building a biotech monolith.

### 10.3 Cross-sector reasoning

The real long-term advantage is not a collection of vertical SaaS pages. It is a cross-sector graph.

Examples:

- a government biodefense award changes a biotech company's financing survival;
- an FDA manufacturing warning connects to a contract manufacturer and shipping lane;
- a critical-mineral permit affects defense procurement and clean-energy equipment;
- port congestion changes agricultural export availability and fertilizer input timing;
- a cold-chain disruption affects a biologic launch;
- an oil-service procurement surge affects industrial employment and regional credit;
- a new sanction changes vessel behavior, commodity availability, and company margins.

Neural Web should receive these as typed evidence paths, not prose-only correlations.

### 10.4 Relationship to the Thematic Foresight Desk

The existing Foresight Desk owns cross-sector capital migration, policy-to-money evidence, physical bottlenecks, theme context, and its existing promotion path.

Sector packs do not create a second Foresight score. They contribute domain facts, dated events, exposure edges, contradictions, and shadow features through explicit contracts. Foresight may consume them under its own evidence and promotion rules.

---

## 11. Canonical object model and contracts

### 11.1 The canonical unit

The minimum useful unit is not a ticker and not an NCT record. It is:

> asset × indication × temporal owner

One molecule can have multiple indications, owners, partners, trials, regulatory applications, and economics. Ownership and rights can change through licensing, option deals, M&A, regional partnerships, spinouts, or returned assets.

### 11.2 Core graph

    Company
    ├── Security
    │   └── CapitalStructureSnapshot
    ├── OrganizationRole
    └── Program / Asset
        ├── Alias
        ├── Target / Mechanism / Modality
        ├── Indication
        ├── TemporalOwner / RegionalRight
        ├── Partnership / DealEconomics
        ├── Patent / Exclusivity
        ├── RegulatoryApplication
        └── Trial
            ├── Arm / Comparator
            ├── Endpoint
            ├── Eligibility
            ├── EnrollmentSnapshot
            ├── SiteSnapshot
            ├── Result
            └── TrialSnapshot

    Catalyst
    ├── DisclosedDateConstraint
    ├── PredictiveDateDistribution
    ├── State
    ├── Outcome
    ├── Evidence
    ├── Revision
    └── Forecast
        ├── ProbabilityDistribution
        ├── PayoffDistribution
        ├── FinancingSurvival
        ├── CompetitivePosition
        └── MarketSetup

### 11.3 Generic contracts

| Contract | Required purpose |
|---|---|
| source_record.v1 | Source ID, external ID, URI, object pointer/hash, timestamps, parser, license |
| evidence_claim.v1 | Subject, predicate, value/object, source span/JSON path, validity, confidence, contradictions |
| sector_event.v1 | Entities, event type, state, time/distribution, evidence, materiality |
| entity_link.v1 | Source entity, canonical entity, method, confidence, validity, reviewer state |
| feature_snapshot.v1 | Entity, as-of, cutoff, values, missingness, staleness, hashes, feature version |
| prediction.v1 | Target, horizon, scenarios, uncertainty, model/calibration, snapshot, authority |
| outcome_label.v1 | Resolved outcome, resolution time, evidence, policy, revision history |
| authority_manifest.v1 | Publication tier, decision authority, consumers, expiry, kill switch |
| sector_intelligence_packet.v1 | Facts, events, contradictions, features, predictions, freshness, provenance, authority |
| lobe_run.v1 | Timing, source watermarks, output hashes, warnings, failures, model versions |

### 11.4 Biopharma contracts

| Contract | Key fields |
|---|---|
| biopharma_entity.v1 | entity_id, type, canonical name, aliases, identifiers, confidence |
| asset_indication.v1 | asset, indication, owner interval, rights geography, target, modality |
| trial_snapshot.v1 | NCT, version, modules, first seen, effective/published/observed time, hash |
| trial_version_diff.v1 | old/new snapshots, exact diffs, semantic alignment, evidence |
| endpoint_change.v1 | endpoint identity, role, text, timeframe, measure, estimand, change class |
| enrollment_signal.v1 | target, actual, rate, status, site trajectory, timing estimate |
| regulatory_event.v1 | application, agency, event, date/distribution, status, evidence |
| catalyst.v1 | entities, type, disclosed wording/interval constraint, optional predictive-date reference, dependencies, state |
| comparable_set.v1 | target object, candidates, filters, similarity, inclusion/exclusion reasons |
| probability_forecast.v1 | outcome taxonomy, probabilities, intervals, baseline, model, calibration |
| catalyst_ev_distribution.v1 | scenarios, fundamental value, market response, financing, assumptions |
| biocatalyst_context.v1 | compact domain projection for Neural Web/Mastermind/Prophet |

### 11.5 Bitemporal requirements

Every mutable fact stores:

- source system;
- source record ID and URL;
- source content hash;
- source published time;
- source effective time;
- retrieved time;
- first-seen time;
- valid-from and valid-to;
- transaction-from and transaction-to;
- source span or JSON path;
- parser or model version;
- license class;
- confidence;
- contradiction state; and
- analyst review state.

This is the difference between a database and institutional memory.

### 11.6 Controlled vocabulary and version registry

Canonical internal IDs must be stable even when an external vocabulary changes. Every normalized concept stores the vocabulary, code, release/version, mapping method, confidence, effective interval, and license/redistribution class.

Required vocabulary families:

| Concept family | Primary vocabularies / identifiers | Rule |
|---|---|---|
| Drug/substance/product | RxNorm, UNII, INN, ATC, Drugs@FDA application/product IDs | Preserve salt, formulation, route, combination, and regional-name distinctions |
| Disease/indication/phenotype | NCI Thesaurus, UMLS, MeSH, ICD, Orphanet | Store mappings as versioned many-to-many claims; never flatten rare-disease subtypes into a broad parent silently |
| Safety | MedDRA where licensed; source-native label/FAERS terms alongside it | Record MedDRA version and license scope; retain verbatim source term |
| Trial design/data | CDISC controlled terminology plus registry-native values | Use for interoperability, not to rewrite the source record |
| Company/security | LEI, CIK, exchange IDs, FIGI or licensed equivalents | Ownership remains temporal and security-specific |

W0 creates a vocabulary registry, scheduled release watcher, migration policy, regression fixtures, and a “mapping changed because vocabulary changed” event distinct from a source-fact change. Unlicensed vocabularies may be used only within their permitted scope; the API never redistributes restricted term sets by accident.

---

## 12. Data-source architecture

### 12.1 ClinicalTrials.gov and AACT

ClinicalTrials.gov API v2 provides:

- identification;
- overall status and status verification;
- start, primary completion, completion, submission, posting, and update dates;
- sponsor and collaborators;
- phases and design;
- conditions;
- interventions;
- arms;
- eligibility;
- primary, secondary, and other outcomes;
- enrollment;
- sites and contacts;
- results;
- adverse events; and
- documents.

Ingestion:

- poll the API using an overlapping LastUpdatePostDate window;
- archive every raw response;
- record the API data timestamp and page cursor;
- materialize a full trial snapshot;
- diff snapshots;
- reconcile weekly against a full download;
- retain daily AACT snapshots and permanent monthly archives for coarse backfill;
- never overwrite prior versions; and
- distinguish registry changes from protocol-confirmed changes.

ClinicalTrials.gov API v2 is current-state oriented. AACT's permanent monthly snapshots begin in 2017 and help reconstruct history, but cannot create daily point-in-time truth for years where snapshots do not exist. ClinicalTrials.gov's public Record History exposes versions separately from API v2; W1 must run an acquisition feasibility and rights/throughput study rather than assume those versions can be bulk-backfilled.

Every trial carries an evidence-coverage epoch:

| Coverage class | Meaning | Permitted claim |
|---|---|---|
| full_version | Every change version captured from an evidenced source window | Version-level as-of replay within that window |
| monthly_only | AACT monthly snapshots only | Month-end/coarse replay; no daily-change claim |
| current_only | Current API record plus prospective snapshots after first seen | Current state and post-onboarding history only |
| source_document_only | Historical change supported by a dated filing/protocol/publication, not registry history | Claim-specific history only |
| unknown | Coverage cannot establish historical state | No as-of reconstruction |

The API poll creates complete version history only prospectively from launch. No user, backtest, or model may request a finer historical as-of state than the evidence-coverage class supports.

W1 feasibility study:

1. sample Record History depth and access behavior across 200 stratified trials;
2. test version identifiers, timestamps, payload recoverability, and terms;
3. compare recovered versions with AACT month-end states;
4. measure requests, bytes, parser burden, and gaps;
5. define lawful bounded backfill or mark it unavailable;
6. publish coverage by trial and date; and
7. forbid “complete historical version” language until measured.

### 12.2 Global trial and regulator expansion

The facts-first beta is explicitly US-first. It must not claim comprehensive foreign-regulator or global-trial coverage until the corresponding sources and identity rules land.

Staged primary-source expansion:

| Geography | Trial/regulatory sources | Initial product status |
|---|---|---|
| Global registry network | WHO ICTRP and its primary-registry network | Discovery and deduplication feasibility |
| EU/EEA | CTIS, EU Clinical Trials Register legacy records, EMA EPAR and safety material | Global phase G1 |
| United Kingdom | MHRA trial/regulatory and Drug Safety Update | Global phase G1 |
| Canada | Health Canada clinical-trial and drug-product/regulatory sources | Global phase G1 |
| Japan | PMDA, jRCT, and Japanese registry sources | Global phase G2 |
| China | NMPA/CDE and Chinese trial-registry sources | Global phase G2 with native-language identity review |
| Australia/New Zealand | TGA and ANZCTR | Global phase G2 |

Each source requires:

- trial and application identity mapping;
- sponsor/asset/indication normalization;
- version and publication-time semantics;
- document availability and rights;
- language and translation policy;
- regulatory-status mapping without flattening jurisdictional differences;
- source-specific SLO;
- corrections; and
- a coverage label.

“Foreign approval” and “global competitive landscape” are available only for the jurisdictions whose coverage state is visible in the product. Missing jurisdictions remain missing—not inferred from US records.

### 12.3 FDA and openFDA

| Source | Use | Cadence / caution |
|---|---|---|
| Drugs@FDA files and approval packages/reviews | Approved applications, products, submissions, actions, and available review documents | Weekday refresh; this is an approved-product corpus, not a complete source for pending applications, INDs, holds, or failed programs |
| Orange Book | Small-molecule approvals, patents, use codes, exclusivity | Release-based |
| Purple Book | Biologics, biosimilars, interchangeability, exclusivity | Monthly archive |
| FDA Advisory Committee Calendar | Scheduled official meetings | Poll at least hourly |
| Federal Register | Meeting notices, rules, regulatory events | Incremental |
| PDUFA goals | Review-clock mechanics | Not an asset-level calendar |
| openFDA labels | Label sections and changes | Weekly; current-label limitations |
| openFDA FAERS | Adverse-event reports | Quarterly; lagged; no causal/incidence inference |
| openFDA shortages | Shortage and availability changes | Daily |
| Complete Response Letters | Public redacted CRLs | Infrequent additions |
| Safety communications | Unstructured authoritative safety notices | Monitor and parse |
| Safety-related labeling changes | Label safety changes | Monitor and version |
| Postmarketing requirements/commitments | PMR/PMC status and milestones | Release-based; link to approval/application |
| Inspection classifications and FDA Data Dashboard | Facility/inspection and compliance context | Coverage and publication lag must be explicit |
| Warning letters, import alerts, and recalls | Manufacturing/compliance and supply risk | Event-driven monitoring |
| Form FDA 483 and FOIA-released records | Inspection observations and otherwise unavailable regulatory evidence | Partial, delayed, and document-specific; never imply comprehensive coverage |

There is no official complete forward PDUFA calendar. Asset-level PDUFA dates must be extracted from issuer 8-Ks, 10-Qs, releases, presentations, regulator notices, and later corrections, with exact wording and confidence.

There is also no single universal regulator-evidence hierarchy. The engine uses an event-specific evidence matrix:

| Event | Preferred evidence | Necessary fallback / caution |
|---|---|---|
| Approval, label, PMR/PMC | FDA action/approval package and current label | Issuer disclosure may establish timing first; reconcile when regulator evidence appears |
| Pending PDUFA/review clock | Issuer filing or release quoting FDA correspondence | FDA generally does not publish a complete pending calendar; preserve the issuer's exact claim and later revisions |
| Clinical hold / IND status | Public FDA communication when available | Usually issuer filing/release; distinguish company-reported status from regulator-published fact |
| AdCom | FDA calendar, Federal Register, briefing documents, vote/minutes | Issuer disclosure may precede calendar publication |
| CRL / non-approval | Public CRL or FDA review material when released | Issuer filing/release may be the only timely evidence; do not infer undisclosed deficiencies |
| CMC / facility risk | Inspection classification, warning letter, import alert, review package, FDA Data Dashboard, released 483/FOIA record | Each source has different coverage and lag; company claims remain separate evidence |
| Safety signal | FDA communication, label change, regulator review | FAERS and trial reports are signal-generating evidence, not causal proof |

Every regulatory card identifies whether the underlying fact is regulator-published, company-reported, source-derived, or inferred.

### 12.4 SEC and corporate evidence

SEC sources:

- submissions JSON;
- filing archives and indexes;
- companyfacts;
- companyconcept;
- frames;
- RSS/current filing feeds;
- inline XBRL;
- primary filing documents; and
- exhibits.

Relevant forms and exhibits:

- 8-K;
- 10-Q and 10-K;
- 20-F and 6-K;
- S-1 and S-3;
- 424B prospectuses;
- ATM and offering documents;
- DEF 14A;
- Forms 3, 4, and 5;
- material contracts;
- collaboration and licensing agreements;
- trial and regulatory disclosures; and
- earnings releases and presentations.

BioCatalyst does not own the generic document plane. It consumes the shared Corporate Intelligence Spine and extracts domain-specific:

- asset;
- trial;
- endpoint;
- catalyst;
- regulator;
- partnership;
- manufacturing;
- safety;
- competition; and
- management-guidance claims.

### 12.5 Literature, grants, and science

| Source | Use |
|---|---|
| PubMed / NCBI E-utilities | Publications, metadata, links, abstracts where available |
| PubTator3 | Biomedical entity and relation annotations |
| Crossref | DOI, author, journal, funder, license, and citation metadata |
| NIH RePORTER / ExPORTER | Grants, projects, publications, investigators, organizations |
| Conference sites | Abstracts, presentation schedules, posters, slide releases |
| Preprint servers | Early scientific evidence with explicit publication state |

The evidence graph must preserve abstract/full-text rights. Literature snippets and embeddings cannot silently become a redistribution product.

Outcome evidence additionally requires a versioned publication-linkage lane covering:

- registry results and history;
- protocols, statistical analysis plans, amendments, and results documents;
- regulator approval/review packages and briefing documents;
- journal article versions, corrections, expressions of concern, and retractions;
- conference abstract, poster, presentation, and later-full-publication versions;
- preprint-to-publication relationships;
- duplicate/subgroup/pooled analyses; and
- discordance between registered endpoints, sponsor disclosure, publication, and regulator interpretation.

The linker records “same study,” “subset,” “pooled,” “follow-up,” and “uncertain” separately. It never counts multiple publications of one trial as independent outcomes, and it never overwrites a discordant result with the most convenient version.

### 12.6 Patents and exclusivity

Sources:

- Orange Book;
- Purple Book;
- USPTO Open Data Portal and Patent File Wrapper;
- EPO Open Patent Services;
- patent documents and assignments;
- FDA exclusivity codes;
- litigation and settlement disclosures; and
- issuer filings.

Patent-to-program matching is probabilistic. True expiry and freedom-to-operate depend on patent term adjustment, patent term extension, pediatric extension, disclaimers, continuations, regional rights, litigation, settlement, and ownership. Product surfaces must distinguish:

- listed expiry;
- calculated expiry;
- extension assumption;
- legal event;
- disputed expiry;
- mapping confidence; and
- analyst/legal review.

### 12.7 Market, estimates, options, and commercial datasets

Licensed or negotiated sources are likely required for:

- exchange-authorized real-time and historical price/volume;
- OPRA options;
- consensus estimates and analyst history;
- robust sales or prescription data;
- commercial competitive intelligence;
- contact and verified email data;
- global private-company funding;
- some conference content; and
- deep historical catalyst curation.

Potential vendors should be evaluated through a rights and quality bakeoff, not selected because a page looks complete.

### 12.8 Licensable-data bakeoff

For each candidate vendor:

1. select a stratified 100-company and 500-asset set;
2. define canonical source truth and adjudication rules;
3. measure identity accuracy, date precision, revision capture, historical depth, and correction lag;
4. inspect rights for storage, derived features, display, API, model training, redistribution, and termination;
5. compare latency and analyst workload;
6. measure unique incremental fields;
7. score dependency and exit cost;
8. run a thirty-day live delta comparison; and
9. license only the families that materially beat the public-source stack.

### 12.9 Update cadences and SLOs

These are launch targets, not current capabilities. They require the O1 persistent operations substrate; GitHub Actions, a render build, or a best-effort nightly cannot satisfy them. W0 freezes a machine-readable source-SLO manifest defining launch-critical class, opportunity/denominator semantics, freshness threshold, completeness-drift tolerance, maximum consecutive misses, severity weight, and pass/fail aggregation for every source. Every row is then measured against that manifest and upstream timestamps—not only “job exited zero.”

| Source family | Collection target | Product SLO |
|---|---|---|
| SEC material filings | Streaming/polling | 5 minutes p95 |
| Monitored issuer IR/RSS | Frequent polling | 15 minutes p95 |
| FDA, AdCom, Federal Register | Frequent polling | 60 minutes p95 |
| ClinicalTrials.gov | Upstream timestamp driven | 2 hours p95 |
| Drugs@FDA | Every source release | 4 hours |
| Shortages | Daily | Same day |
| Labels and recalls | Weekly/source release | 24 hours |
| FAERS | Quarterly | 24 hours after release |
| Orange/Purple Books | Every release | 24 hours |
| PubMed and grants | Daily/bulk | 24 hours |
| Patents/legal events | Daily or source allowance | 24 hours |
| Market data | Licensed realtime or delayed | Entitlement-specific |

---

## 13. Domain engines

### 13.1 Trial versioning and change detection

Every study version actually captured under the trial's evidence-coverage class becomes a full immutable snapshot. “Complete history” is valid only prospectively after the service begins capture, or for a bounded historical interval whose versions were independently evidenced. The change engine has two layers:

1. exact structural diffs over source paths; and
2. semantic alignment for objects whose order, label, or wording changed.

Endpoint matching:

1. preserve verbatim endpoint objects and create a raw identity hash over source fields;
2. parse role, measure, timeframe, population/estimand, threshold, units, and description into separately versioned components;
3. use whitespace/punctuation/unit/synonym normalization only to generate match candidates—not to define equality;
4. exact-match unchanged raw objects first;
5. align remaining old/new objects with a weighted similarity matrix whose null-match penalty permits genuine additions/removals;
6. run one-to-many and many-to-one checks for endpoint splits, merges, and decompositions before final assignment;
7. retain unmatched and low-margin matches for review;
8. classify component-level changes; and
9. emit the raw source diff, parsed-component diff, match confidence/margin, coverage class, and interpretation.

A normalized semantic hash must never erase a meaningful threshold, estimand, analysis-population, role, or timeframe change. Matching is probabilistic record linkage; source equality is exact.

Change classes:

- endpoint added or removed;
- primary-to-secondary or secondary-to-primary switch;
- outcome measure changed;
- timeframe changed;
- threshold or responder definition changed;
- estimand or analysis population changed;
- description-only rewrite;
- ordering-only change;
- enrollment target change;
- arm or comparator change;
- eligibility change;
- masking or allocation change;
- study design change; and
- result-posting change.

Product language must say “registry endpoint change” unless a protocol, statistical analysis plan, filing, or issuer statement establishes that the trial protocol itself changed.

Acceptance:

- 300 adjudicated version pairs is an initial coverage checkpoint, not statistical sufficiency;
- the pre-sized per-change-family lower-confidence-bound gates in section 20.3 clear, nominally at least 95% endpoint-change precision and 90% recall;
- the lower confidence bound for exact source-level date/site-diff accuracy is at least 99%;
- no silent endpoint merges;
- low-confidence matches enter review; and
- every alert preserves old and new evidence.

Acceptance is reported separately by evidence-coverage class and includes split/merge cases. Historical recall is never quoted outside an interval whose source versions are known to be observable.

### 13.2 Enrollment and site intelligence

Public data rarely exposes actual enrollment velocity directly. The engine should estimate, not pretend to observe.

Inputs:

- target and actual enrollment;
- recruitment status;
- start, primary completion, and completion guidance;
- first and last site activation;
- active site count;
- geographic mix;
- investigator and contact changes;
- inclusion/exclusion changes;
- trial pauses or holds;
- issuer statements;
- comparable site productivity;
- disease prevalence and recruitment difficulty; and
- results or disposition counts when available.

Outputs:

- disclosed target;
- site count and expansion/contraction;
- inferred activation velocity;
- estimated enrollment-completion distribution;
- delay probability;
- evidence and assumptions;
- prior forecast; and
- confidence.

Each input and output carries an observation class:

| Observation class | Meaning |
|---|---|
| Registry-observed | A location, enrollment value, status, or date appeared in a dated registry version |
| Sponsor-reported | Company or investigator disclosed activation, enrollment, pause, or completion |
| Results-retrospective | Actual enrollment/disposition became visible only when results or a publication appeared |
| Independently documented | Regulator, site, protocol, or other dated primary document supports the claim |
| Model-inferred | Latent activation, recruitment velocity, completion, or delay estimated from observed inputs |
| Unknown | The public record cannot establish the state |

A registry location's appearance is not proof that the site activated, screened, or enrolled a patient. “Actual enrollment” is often a retrospective total, not a live counter. Site growth is not automatically enrollment growth; site contraction is not automatically failure. Models must learn conditional relationships by indication, geography, phase, design, and recruitment status while preserving the observation class in every feature and explanation.

### 13.3 Catalyst date engine

Never coerce “second half of 2027” into December 31.

Maintain two distinct objects:

1. the **disclosed interval claim**—a faithful encoding of what the source said; and
2. the **predictive occurrence distribution**—a model of when the event will happen, including explicit delay, cancellation, dependency-failure, and still-unresolved mass.

Represent each disclosure plus exact original wording:

| Disclosure | Representation |
|---|---|
| Exact date | Point claim plus timezone/source; predictive object still retains delay/cancellation mass |
| October 2026 | Calendar-month interval constraint only |
| Q4 2026 | Calendar-quarter interval constraint only |
| H2 2026 | Calendar-half interval constraint only |
| Late 2026 | Fuzzy-language class plus source wording; no invented within-range density |
| By year-end | Upper-bound claim only |
| In coming weeks | Relative interval constraint anchored to disclosure time |
| No longer guided | Withdrawn guidance claim, never a fake future date or generic censoring label |

No disclosure representation supplies a uniform or learned within-interval density. That density, if modeled, belongs only to the separately versioned predictive occurrence distribution.

The engine should combine:

- issuer language;
- trial registry dates;
- FDA clocks;
- conference schedules;
- management history;
- enrollment estimates;
- comparable development timing; and
- known dependencies.

Use survival, multi-state, or accelerated-failure-time models for timing. An event can remain active, occur, be delayed/revised, be cancelled, or become unresolvable; those states are not interchangeable. Output interval coverage and proper-scoring metrics, not a single guessed date.

### 13.4 Outcome taxonomy

Clinical records cannot be labeled only success/failure, but unlike concepts must not be forced into one “competing outcome” list. Use four orthogonal layers:

1. **Lifecycle transition graph** — phase/state entered, filing, acceptance, review, approval, restriction, withdrawal, or discontinuation.
2. **Evidence/result classification** — positive efficacy, negative efficacy, mixed/partial, safety concern, inconclusive, not disclosed, or not evaluable, with endpoint-level support.
3. **Discontinuation/cause classification** — efficacy, safety, CMC/manufacturing, regulatory, enrollment/operations, financing/sponsor failure, strategic reprioritization, partnership return, or unknown; multiple causes may coexist with confidence.
4. **Observation status** — resolved, right-censored at cutoff, interval-censored, lost/unknown, acquired before target resolution, or source coverage insufficient.

Every statistical target then defines its own mutually exclusive and exhaustive first-event state space. Examples:

| Model target | Valid first-event states |
|---|---|
| Phase transition within 24 months | advance; discontinue before advance; remain active at horizon; observation lost/coverage insufficient |
| Primary-endpoint readout | positive; negative; mixed/inconclusive; readout cancelled; unresolved at horizon; unobservable |
| Filing review | approve; approve with material restriction; CRL/non-approval; application withdrawn; unresolved at horizon; unobservable |
| Program lifecycle | advance; approve; discontinue with cause sidecar; acquired/rights-transferred before resolution; active at horizon; unknown |

“Delayed” is a timing state, not a scientific outcome. “Acquired” is an ownership/observation event unless the model target explicitly treats acquisition as a competing first event. Censoring describes what can be observed at the cutoff; it is not a failure cause.

Outcome policies must define:

- evidence hierarchy;
- resolution time;
- how silent programs are treated;
- how indication-specific outcomes are separated;
- how combination trials are handled;
- when a phase transition counts;
- how post-hoc endpoint changes are treated; and
- how later corrections revise labels without rewriting history.

Outcome adjudication joins registry results, protocol/SAP/results documents, sponsor disclosures, regulator reviews, publications, conference versions, and correction/retraction state. Discordant evidence remains visible and versioned.

### 13.5 Probability of progression and approval

#### Baseline

Start with a leakage-safe version of BPC's understandable baseline:

    transition rate by phase × therapeutic area
    with count, interval, cohort dates, censoring, and outcome definitions

#### Challenger

Use a hierarchical competing-risks model with partial pooling across:

- therapeutic area;
- indication;
- phase;
- modality;
- target class;
- biomarker strategy;
- orphan/rare disease;
- trial design;
- randomized/blinded/control structure;
- endpoint type and objectivity;
- sample size and power proxies;
- sponsor experience;
- regulator designation;
- prior asset evidence;
- safety history;
- competitive density;
- calendar era; and
- data completeness.

Possible implementation:

- discrete-time hazard or multi-state survival model;
- hierarchical Bayesian model for honest sparse-cell uncertainty;
- calibrated gradient-boosted challenger for nonlinear interactions;
- monotonic constraints where defensible;
- isotonic or beta calibration on rolling-origin validation;
- competing-risk cumulative incidence;
- ensemble only if it beats the best component out of sample.

Required outputs:

- probability of each outcome;
- probability of progression;
- probability of approval by an explicit horizon;
- optional lifetime approval probability only when the extrapolation horizon, assumptions, and tail uncertainty are printed;
- time distribution;
- credible/confidence interval;
- baseline comparison;
- top evidence contributions;
- analogous cohorts;
- missingness;
- model and calibration version; and
- authority tier.

### 13.6 Comparable-trial engine

Comparable retrieval is a hybrid:

1. hard structured filters for phase, indication, mechanism, modality, population, endpoint role, and study design;
2. lexical BM25 over titles, summaries, outcome text, and eligibility;
3. biomedical embeddings;
4. graph proximity;
5. temporal availability filter;
6. diversity constraints; and
7. human override with recorded reason.

Each comparable must show:

- inclusion reason;
- exclusion reason when manually rejected;
- similarity dimensions;
- evidence availability;
- outcome;
- date;
- sponsor;
- market context;
- sample size; and
- whether it was available at the forecast cutoff.

Comparable outcome synthesis can use random-effects meta-analysis where endpoints are compatible. It must not pool incomparable measures because their labels share a keyword.

### 13.7 Competitive-position engine

Competitive position is multidimensional:

- mechanism and target differentiation;
- modality;
- efficacy and safety evidence;
- endpoint strength;
- population breadth and unmet need;
- trial timing;
- recruitment competition;
- regulatory status;
- manufacturing complexity;
- dosing and convenience;
- label breadth;
- patent/exclusivity;
- commercial infrastructure;
- partnership strength;
- competing program discontinuations;
- market saturation; and
- expected time to launch.

Output axes, not one unexplained rank:

- evidence strength;
- differentiation;
- time lead/lag;
- regulatory advantage;
- trial-execution advantage;
- commercial position;
- durability;
- crowding; and
- uncertainty.

A compact competitive-position feature may later feed a model, but the product should preserve the axes and graph.

### 13.8 Regulatory engine

Track:

- IND and clinical hold events;
- NDA, BLA, sNDA, and sBLA disclosures;
- filing acceptance;
- standard/priority review;
- PDUFA disclosures and revisions;
- major amendment/extensions where disclosed;
- advisory committee notices, briefing documents, votes, and minutes;
- accelerated approval and confirmatory obligations;
- orphan, breakthrough, fast track, RMAT, priority-review, and other designations;
- complete response letters;
- approval, label, and postmarketing requirements;
- REMS;
- manufacturing inspection/CMC disclosures;
- recalls and shortages;
- foreign regulator decisions; and
- safety communications.

Regulatory claims use the event-specific evidence matrix in section 12.3, not one generic priority list. A regulator publication is strongest for some resolved actions; a timely issuer filing may be the only public source for a pending PDUFA date, clinical hold, or CRL detail. The system holds multiple claims, classifies each as regulator-published/company-reported/source-derived/inferred, and shows contradictions. It never collapses them to the most recent string without lineage.

### 13.9 Safety and label engine

The safety layer joins:

- labels and label versions;
- FDA safety communications;
- safety-related labeling changes;
- recalls;
- shortages;
- trial adverse events and discontinuations;
- published literature;
- regulator meeting documents;
- issuer disclosures; and
- FAERS as a hypothesis-generating reporting system.

FAERS reports do not establish causality or incidence. The engine may detect reporting disproportionality and change, but every product surface must preserve:

- stimulated reporting;
- duplicates;
- missing exposure denominator;
- confounding;
- indication bias;
- reporting lag; and
- the difference between signal detection and causal inference.

### 13.10 Patent and exclusivity engine

Outputs:

- patent families;
- listed patents;
- patent/use codes;
- Orange/Purple Book status;
- calculated and asserted expiry;
- patent-term adjustment/extension evidence;
- pediatric or regulator exclusivity;
- biosimilar/interchangeability context;
- legal events;
- litigation and settlement;
- ownership;
- asset mapping confidence;
- loss-of-exclusivity distribution; and
- review status.

No single “patent expiry” date should appear without its assumption class.

### 13.11 Partnership and licensing economics

Extract:

- licensor/licensee;
- asset, indication, and territory;
- option structure;
- upfront;
- equity investment;
- development milestones;
- regulatory milestones;
- commercial milestones;
- royalties;
- cost/profit share;
- opt-in/opt-out;
- rights reversion;
- termination;
- change of control;
- funding obligations; and
- disclosed accounting receipts.

Values become ranges when terms are aggregate or undisclosed. The engine links potential milestone timing to catalysts and capital-structure scenarios without assuming receipt.

### 13.12 Financing survival and dilution

BioCatalyst consumes the shared Capital Structure plane:

- reported cash;
- normalized burn;
- debt and covenants;
- shares and float;
- shelf capacity;
- ATM state and usage;
- warrants and converts;
- ELOC and other facilities;
- offerings;
- contractual milestones;
- financing ability;
- financing need;
- financing activation; and
- forward financing scenarios.

Domain-specific targets are joint, not “financing hazard through one fixed catalyst date.” Let `C` be catalyst occurrence time, `F1, F2, ...` recurrent financing-event times, and `D` catalyst cancellation/discontinuation. The decision quantities include:

    P(C < F1), P(F1 < C and F1 < D),
    P(reach C without a financing that breaches a dilution threshold),
    and the joint distribution of C, financing path, and shares outstanding.

An exact conditional decomposition is:

    P(C < F1 and C < D | X)
      = integral P(F1 > t and D > t | C = t, X)
                 × f_C(t | X) dt

Here `f_C` is the finite catalyst-occurrence subdensity; any `C = infinity`/never-occurs mass remains outside the event. The conditional term preserves dependence among catalyst timing, first financing, and cancellation. Because those events, market price, and management choice share covariates and affect one another, production should estimate a joint multi-state/competing-event or simulation model, include recurrent financings and cancellation, and validate dependence assumptions.

Hazard inputs can include:

- cash runway;
- catalyst timing;
- shelf/ATM availability;
- warrant exercise economics;
- listing requirements;
- debt maturity;
- market capitalization and liquidity;
- stock performance;
- volatility;
- prior financing behavior;
- expected milestone receipts;
- trial cost step-ups;
- deal optionality; and
- broader biotech capital-market regime.

The company dossier should show:

- runway distribution;
- catalyst-date distribution;
- probability of reaching the catalyst;
- financing paths;
- share-count distribution;
- dilution before and after the event; and
- assumptions.

### 13.13 Expected-value distribution

Do not replace BPC's simplistic fields with a more impressive-looking bull/base/bear guess.

The correct object is a scenario mixture. Define mutually exclusive and exhaustive **joint** scenarios `s` across clinical/regulatory outcome, timing, financing path, competitive response, and market state. Then:

    F_R(r) = Σ_s π_s F_{R|s}(r)
    E[R]   = Σ_s π_s E[R|s]

The scenario probabilities must sum to one, expose residual/unknown mass, and avoid multiplying marginal probabilities that share evidence.

Fundamental branches can use:

- risk-adjusted net present value;
- indication population;
- treatment share;
- price and duration;
- probability and timing;
- development and launch cost;
- royalties and partnership economics;
- patent/exclusivity;
- tax and capital structure; and
- competitor response.

Use either (a) conditional cash-flow/NPV inside already probability-weighted scenario branches or (b) a standalone risk-adjusted NPV construction. Never probability-adjust the same clinical/regulatory risk in both places.

Market-response branches can use:

- historical abnormal returns by event family;
- company and asset comparables;
- pre-event run-up;
- enterprise value at risk;
- implied option movement;
- short interest and liquidity;
- broad biotech regime;
- surprise magnitude; and
- financing overhang.

Outputs:

- probability of positive abnormal return;
- expected return;
- median;
- quantiles;
- value at risk and conditional value at risk;
- scenario attribution;
- model uncertainty;
- market-implied versus model distribution; and
- sensitivity to key assumptions.

A “market-implied probability” is not identified by price alone. It requires declared scenario values, discount/risk premium, financing/share count, liquidity/positioning, and often option-volatility assumptions. Show an assumption-conditioned implied range, not a uniquely observed probability.

### 13.14 Market reaction and option structure

Build event studies with:

- split/dividend/corporate-action-adjusted prices;
- market and biotech-beta adjustment;
- pre-event and post-event windows;
- filing/publication timestamps;
- after-hours versus regular-session alignment;
- liquidity filters;
- delisted and acquired companies;
- option-implied movement;
- volatility crush;
- skew;
- open interest and spread quality;
- event-window gap and follow-through; and
- costs.

The research design must additionally specify:

- benchmark model and pre-event estimation window;
- intraday/publication timestamp uncertainty and executable-session mapping;
- confounding issuer disclosures in the event window;
- overlapping events and repeated events per issuer/asset;
- clustered inference by issuer, asset, event date, and correlated indication where appropriate;
- serial dependence and heteroskedasticity-robust uncertainty;
- matched-control and calendar-time portfolio sensitivity checks;
- delisting returns and acquisition treatment;
- multiple-hypothesis families and corrected discovery thresholds; and
- options availability/selection bias, stale quotes, spread/size filters, and correction for choosing strikes/expiries after seeing outcomes.

The market layer does not change a clinical probability. It changes the mapping from outcome to expected market payoff and tradeability.

### 13.15 Earnings, filings, transcripts, and alternative data

The shared Corporate Intelligence Spine should supply:

- source documents and spans;
- earnings events;
- transcripts;
- slides;
- filings;
- metric deltas;
- management claims;
- topic evidence;
- company-event digests; and
- correction state.

BioCatalyst adds domain extraction:

- catalyst guidance introduced, narrowed, delayed, or removed;
- asset prioritization;
- enrollment and site commentary;
- endpoint interpretation;
- FDA meeting or regulatory language;
- manufacturing/CMC risk;
- competitive read-through;
- partnership and milestone economics;
- program discontinuation;
- commercial launch evidence;
- burn guidance tied to trials; and
- contradiction with registry, prior call, prior filing, or regulator evidence.

Alternative data can include:

- trial-site hiring and investigator activity;
- conference schedule and abstract changes;
- patent events;
- grant and procurement awards;
- manufacturing and shortage evidence;
- web and search interest;
- prescription or claims data when licensed;
- job postings when legally and operationally reliable;
- import/export and shipping evidence in the future Shipping & Trade pack; and
- supplier/customer changes.

Every alternative source must earn its place through incremental timeliness or accuracy, not novelty.

### 13.16 Company memory and management track record

For each company, track:

- original catalyst guidance versus actual timing;
- frequency and size of date revisions;
- endpoint and trial-design revisions;
- enrollment commentary accuracy;
- cash guidance and financing timing;
- dilution behavior;
- partnership claims versus realized economics;
- regulatory language;
- disclosure corrections;
- program cancellations;
- post-event framing changes; and
- management continuity.

This becomes context, not a moral score. It can improve timing priors, confidence, and contradiction review when tested point in time.

### 13.17 Materiality and alert ranking

Alert ranking should be a learned or rule-governed attention policy over:

- exposure;
- event proximity;
- object importance;
- semantic change class;
- magnitude;
- novelty;
- contradiction;
- source quality;
- model sensitivity;
- forecast delta;
- downside asymmetry; and
- urgency.

It is not a security ranking. A severe data-quality failure can outrank a favorable catalyst because it invalidates downstream confidence.

Article 2 still treats attention ordering as authority. The facts-first product therefore launches with chronological/user-authored ordering only. Any system attention policy above runs as a graded shadow queue with a falsifiable “this mattered” outcome; it cannot reorder cards, raise alert priority, or create an offscreen-urgent marker until its exact consumer earns A2 under Article 3. User-created filters, watchlists, and explicit sort choices are not covert system promotion.

### 13.18 Analyst operations

A credible product needs an internal operations console:

- entity-link review;
- trial and endpoint alignment review;
- catalyst-date conflict resolution;
- outcome adjudication;
- source/parser health;
- stale-source queue;
- patent mapping review;
- deal-economics review;
- forecast exceptions;
- customer correction intake;
- change approval;
- audit log; and
- SLA dashboard.

Initial steady-state **hypothesis**, not a staffing commitment:

- 0.6–1.0 biopharma analyst FTE;
- 0.2 data engineering/SRE;
- 0.1 ML/quant;
- fractional finance and IP review.

The analyst is not there to manually recreate every row. W0 must measure daily change volume, ambiguity and escalation rates, minutes per review, reviewer agreement, queue p50/p95/p99 age, correction sensitivity, and bilingual-QA load. Staffing is recomputed from the measured arrival/service process and target queue tail; the system routes high-value ambiguity and reports when automation merely hides an unserved queue.

---

## 14. Prophet architecture

### 14.1 The proposed five-factor concept

The user's conceptual score is directionally right:

    technical setup
      × catalyst probability
      × expected payoff
      × financing survivability
      × competitive position

It forces the system to avoid the classic biotech mistake: treating a scientifically interesting catalyst as a complete investment thesis.

Literal multiplication of raw values is still the wrong production model because:

- the terms have different units;
- some are conditional on others;
- expected payoff can be negative or unbounded;
- financing and competition influence both probability and payoff;
- technical setup has a different horizon;
- a near-zero input can annihilate the product;
- correlated components double-count evidence; and
- a product of uncalibrated scores is not a probability or expected return.

### 14.2 Recommended model

Maintain distinct causal layers:

1. biological/regulatory outcome distribution;
2. event timing distribution;
3. fundamental value distribution by outcome;
4. financing and share-count distribution;
5. market-response distribution;
6. competitive-position features; and
7. existing Prophet technical and market-structure context.

The target outputs are:

- calibrated probability of positive return over the event horizon;
- expected abnormal return;
- full return distribution;
- downside tail;
- scenario attribution; and
- abstention/data-quality state.

### 14.3 Explainability index

If the product needs a five-part visual score, use it as an explainability index, not the model itself.

Normalize every axis to a calibrated zero-to-one scale and compute:

    BioCatalyst Research Index
      = 100 × exp(
          sum of each weight
          × log(maximum of a small floor and the calibrated axis))

Display the five axes and the weakest-link penalty. Then calibrate the index against outcomes. Never label the index “probability” unless it is separately calibrated as one.

The Research Index is hard-fenced `display_only`. It is excluded from default sorting, screening, alerts, ranking, portfolio sizing, Prophet candidate selection, and every scored-path input. A user may open it as an explainer or explicitly choose it as a display column. Any broader use requires its own registered target, forward ledger, Article-3 evidence, and tier promotion; attractive factor geometry is not authority.

### 14.4 Integration ladder

| Stage | BioCatalyst use | Authority |
|---|---|---|
| P0 | Dossier and product only | None |
| P1a | Attach official facts after Prophet selection | Display/context; cannot change IDs/order/gates/size |
| P1b | Attach stored forecasts after Prophet selection | Shadow; domain-ledger receipt required; cannot change IDs/order/gates/size |
| P2 | Neural Web explanation plus graded shadow attention queue | A1 explain; A2 attend only after Article-3 earn-in |
| P3 | Staleness, contradiction, imminent financing hazard | Candidate A3 de-escalate only |
| P4 | Artifact seeks CONFIRMER or SCORED tier under Article 3 | A5 governor records promotion/demotion; it is not itself a probability engine |
| P5 | New selection or sizing logic | Separate future program; not implied here |

The repository's current Prophet bridge selects before contextual attachment. Preserve that boundary for the initial integration.

### 14.5 Time-safe feature projection

Prophet receives a compact frozen projection:

- company/security ID;
- asset-indication IDs;
- next material catalyst and date distribution;
- event horizon;
- evidence cutoff;
- outcome probabilities and uncertainty;
- payoff distribution;
- financing-survival distribution;
- competitive axes;
- contradiction and staleness flags;
- model and calibration versions;
- input receipt IDs;
- authority tier; and
- packet hash.

It does not query the live BioCatalyst database during a backtest.

### 14.6 Promotion gate

Six months and 100 resolved events are an **eligibility checkpoint**, not an authority gate. They never override the Neural Web constitution, Article 3, the target's statistical power needs, or incomplete outcome horizons.

Per registered model family × target × horizon, a promotion review requires:

- a pre-registered outcome, decision surface, baseline, error budget, family/FDR assignment, and lapse rule;
- a power-calculated effective sample size with minimum positive/negative or competing-event counts, accounting for clustering and repeated issuer/asset observations;
- a horizon-complete evaluation window, even when it requires substantially longer than six months;
- at least two non-overlapping rolling-origin evaluation periods;
- calibration intercept and slope with confidence bounds, reliability curves, Brier/log-loss skill, and interval coverage where applicable;
- confidence bounds for incremental net utility after costs and for every behavioral lift claim;
- subgroup and regime stability with explicit abstention where support is weak;
- Article-3 Wilson lower-bound or appropriate pre-registered confidence-bound gates, evaluated within the declared multiple-testing family;
- no material leakage, survivorship, timestamp, or selection defect;
- a promotion manifest naming consumers, permitted surfaces, expiry, kill switch, and rollback artifact;
- an A5 governance-ledger record for promotion/demotion; and
- automatic lapse or demotion on silence, stale evidence, calibration decay, or a failed re-evaluation.

Sparse model families remain shadow. A high-quality product does not need false authority.

---

## 15. Neural Web and Mastermind AI

### 15.1 Sector packet

BioCatalyst should emit one compact versioned packet:

    sector_intelligence_packet.v1
      sector
      entity_refs
      security_refs
      portfolio_exposure
      knowledge_cutoff
      current_facts
      material_changes
      upcoming_events
      contradictions
      freshness
      quality
      feature_snapshot_refs
      prediction_refs
      evidence_refs
      authority_caps
      packet_hash

The packet is the integration seam for BioCatalyst, HigherGov, Shipping, Mining, Energy, and Agriculture.

### 15.2 Neural Web responsibilities

Neural Web may:

- read typed facts and events;
- connect cross-sector evidence;
- detect contradictions and stale context;
- raise attention;
- explain a Prophet result;
- attach portfolio exposure;
- request deeper research;
- de-escalate when a promoted hazard policy permits;
- record lobe health and source freshness; and
- preserve the evidence path.

It may not:

- invent a clinical outcome;
- convert an LLM opinion into a probability;
- rank a stock up from prose;
- bypass Prophet's selection order;
- size a position;
- turn community sentiment into authority; or
- hide missing data behind a fluent narrative.

### 15.3 Mastermind tools

Proposed permission-scoped tools:

- search_biopharma_entities;
- get_company_dossier;
- get_asset_dossier;
- get_trial;
- get_trial_changes;
- get_catalyst;
- get_catalyst_timeline;
- get_regulatory_history;
- get_competitive_landscape;
- get_comparables;
- get_capital_survival;
- get_probability_forecast;
- get_ev_distribution;
- get_evidence;
- compare_companies;
- compare_trials;
- what_changed;
- portfolio_catalyst_exposure;
- create_scenario;
- explain_forecast;
- save_cohort; and
- generate_research_packet.

Every answer must carry:

- as-of time;
- source citations;
- fact/estimate/scenario labels;
- uncertainty;
- conflicts;
- freshness; and
- the relevant authority boundary.

### 15.4 Example Mastermind investigations

User:

> Which holdings have a clinical readout before they probably need financing?

Mastermind:

- resolves holdings;
- joins BioCatalyst event distributions to Capital Structure projections;
- ranks attention by overlap probability;
- explains the highest-risk collisions;
- cites filings and catalyst evidence;
- offers scenario changes;
- does not create a buy/sell signal.

User:

> What changed in this Phase 3 since the last earnings call?

Mastermind:

- compares the prior call cutoff to current state;
- aligns trial versions;
- retrieves endpoint, enrollment, site, timing, and management claims;
- highlights contradictions;
- shows probability changes from a stored model run;
- distinguishes registry changes from confirmed protocol changes.

User:

> Which defense-procurement awards could matter to our biotech universe?

Mastermind:

- queries the Government/Procurement pack;
- follows company, grant, contract, program, and supplier edges;
- retrieves BioCatalyst assets and financing context;
- returns a sourced cross-sector evidence path.

### 15.5 Retrieval before generation

Mastermind answers from:

- canonical objects;
- source spans;
- stored changes;
- model outputs;
- comparable sets;
- user scenarios; and
- versioned sector packets.

The LLM may synthesize or request a bounded deterministic calculation. It does not estimate probabilities from an unstructured prompt on demand.

---

## 16. Current repository substrate

This audit began from fresh origin/main at commit f84613090e4aa3787379b1565a0b9f94a5cef221 and rebased onto commit 2ae565326771b7da5460a77374c431ab37e40d3b after the Capital Structure docket merged.

### 16.1 Existing biopharma-related assets

| Existing capability | Current value | Limitation / action |
|---|---|---|
| collectors/clinicaltrials_themes.py | Scheduled ClinicalTrials.gov theme collection | Only broad phase/sponsor/first-post/enrollment context |
| engine/theme_clinical.py | Theme-level clinical context | Display/context, not asset-indication intelligence |
| Existing clinical cache | About 2,471 studies across three themes at audit | Narrow thematic slice |
| collectors/clinicaltrials.py | Per-ticker Phase 3 start/halt support | Limited mapping and deduplication |
| collectors/openfda.py | Approval and label-expansion history | Retrospective display, not a full regulatory graph |
| collectors/fda_shortages.py | Active shortage collection | Weak drug/company resolution |
| collectors/beneficial_ownership.py and engine/beneficial_ownership.py | 13D/13G ownership context | Consume; do not duplicate |
| collectors/edgar_dilution.py | Financing/dilution event substrate | Consume through Capital Structure contract; runtime availability remains gated by `NEXTL-U4` until the first successful nightly materialization |
| collectors/edgar_earnings_8k.py | Large historical earnings observation set | Not a canonical transcript/document spine |
| collectors/finnhub_transcripts.py | Transcript metadata/source option | Plan and body limitations |
| scripts/backtest_event_priors.py | Clinical/openFDA event-prior research | Existing constructions did not clear BH-FDR; timing alignment weak |
| engine/event_landmine.py | Event-risk context | Explicitly omits forward PDUFA because no credible source existed |
| engine/prophet_bridge.py | Prophet origination and plan construction | Despite the filename, it is not a generic sector-context bridge and must not become BioCatalyst's integration shortcut |

The right move is consolidation around a domain-owned evidence graph, not another narrow collector beside these.

### 16.2 Current authority

Current repository law and wiring already support the safe rollout:

- clinical information is display/context;
- Neural Web confluence does not originate rankings;
- Prophet selection occurs before contextual attachment;
- management/context layers do not change pick IDs or order;
- LLM-originated scoring is forbidden; and
- the validation gauntlet applies to authority promotion, not to building display/context infrastructure.

BioCatalyst should ship useful facts, changes, dossiers, search, alerts, and machine context immediately while predictive families accrue in shadow.

The current stage-tilt and options-context attachments are useful **precedents** for bounded, traceable integration, not an available generic bridge. BioCatalyst must build a new post-selection adapter. No BioCatalyst import may enter Prophet candidate generation, ordering, gating, or sizing unless that exact consumer and model family later clear the governed promotion path.

---

## 17. Ownership and collision map

Fresh GitHub inspection at the audit cutoff found no open Macro Dashboard PR whose title/branch claimed BioCatalyst, clinical/pharma, Corporate Intelligence/earnings-document, capital/dilution, or Neural Web implementation ownership. The user's concurrent sessions are coordination signals, not executable dependencies until their contracts merge. Repository build maps are useful hints but can lag GitHub; W0 repeats this census before assigning any path.

### 17.1 Corporate Intelligence Spine

An active earnings/document effort is proposing the generic company evidence plane:

- company identity;
- company event;
- source document;
- source span;
- transcript;
- slide page and family;
- metric delta;
- mention/topic evidence;
- company-event digest; and
- health state.

At the audit cutoff, parts of this work remained unmerged and contract names overlapped across its own dockets. BioCatalyst must participate in the shared Wave-0 contract freeze rather than assume unstable names.

This is a hard dependency, not an invitation to duplicate it. Until an executable Corporate Intelligence contract lands, SEC/issuer-backed BioCatalyst features remain blocked or visibly degraded behind an adapter; BioCatalyst may use bounded fixtures for interface development but may not create a second generic document collector, span store, or retrieval index.

Corporate Intelligence owns:

- generic filings;
- transcript and slide acquisition;
- document storage;
- source spans;
- generic company events;
- document retrieval;
- correction mechanics; and
- general metric deltas.

BioCatalyst owns domain extraction from those objects.

### 17.2 Capital Structure Intelligence

[PR 4175](https://github.com/chriswong6031-creator/macro/pull/4175) merged the [Capital Structure Intelligence docket](CAPITAL_STRUCTURE_INTELLIGENCE_COMPETITIVE_TEARDOWN_AND_BUILD_DOCKET_2026-08-01.md) during this investigation. It is a planning reference, not an implemented data plane. Wave 0 still needs to freeze and implement executable schemas, producers, stores, cadences, and one-writer registrations before BioCatalyst can consume live capital projections.

That plane owns:

- shares and float reconciliation;
- shelves, ATMs, ELOCs, offerings, and registration state;
- warrants and converts;
- debt and contractual overhang;
- cash and normalized burn;
- runway;
- financing ability, need, and activation;
- dilution scenarios;
- financing-probability research; and
- its forward ledger.

BioCatalyst consumes a compact point-in-time capital-structure context/projection and adds catalyst timing and domain scenarios. It does not create a second generic cash or dilution engine.

### 17.3 Government and Procurement Intelligence

The HigherGov/defense/procurement session should own:

- agencies;
- budget programs;
- solicitations;
- awards and modifications;
- vendors and subcontractors;
- contract vehicles;
- procurement competition;
- spending forecasts;
- protests and cancellations;
- government-customer exposure; and
- procurement-domain models and UI lenses.

Shared with BioCatalyst:

- registered company-identity read contract;
- Sector Interface Kit source/evidence contracts;
- sector-event grammar;
- product-shell-owned saved cohorts, alerts, and user state;
- shared product shell;
- Neural-Web-owned cross-sector read graph;
- versioned API/MCP conventions;
- Mastermind tools;
- Neural-Web-owned authority vocabulary/governor contract; and
- visual interaction system.

BioCatalyst may link BARDA, NIH, DoD, HHS, VA, or other awards to companies/assets, but it must consume procurement truth from that pack once the contract lands.

### 17.4 Shipping and Trade Intelligence

The future pack should own:

- vessels and operators;
- ports and terminals;
- routes and lanes;
- manifests and customs events;
- commodity flows;
- freight and congestion;
- sanctions and trade controls;
- importer/exporter and supplier edges; and
- shipping/trade-specific models.

BioCatalyst consumes relevant cold-chain, API, raw-material, manufacturing, and distribution evidence through cross-sector edges.

### 17.5 One-writer rule

| Object / write lane | Canonical owner |
|---|---|
| Generic company identity | Corporate Intelligence identity service; B2 is blocked until its executable contract lands or B0 issues a joint replacement ruling |
| Security identity and corporate actions | Market Data/security-master service registered in B0 |
| SEC/issuer raw acquisition, generic source document/span, transcript, and generic company event | Corporate Intelligence |
| ClinicalTrials.gov/AACT and FDA-family raw acquisition | BioCatalyst |
| Capital instrument, financing state, cash/burn, and runway projection | Capital Structure |
| Government solicitation/award | Government & Procurement |
| Vessel/port/manifest/customs event | Shipping & Trade |
| Asset/drug/target/indication and temporal biopharma ownership | BioCatalyst |
| Trial/endpoint/site snapshot and regulatory application/catalyst | BioCatalyst |
| Clinical forecast, comparable set, outcome label, and BioCatalyst forward ledger | BioCatalyst |
| QI qledger rows | QI |
| Cross-sector read-side federation and contradiction/context projection | Neural Web |
| Tier constitution, promotion/demotion, and authority ledger | Neural Web A5 governor under Article 3 |
| Final technical selection | Prophet |
| Narrative synthesis/explanation over registered APIs | Mastermind |
| Auth, entitlements, saved queries/cohorts, watchlists, and other user state | Mastermind Terminal/Supabase product plane |
| Schedulers, queues, migrations, secrets, watermarks, retention, and incident controls | Macro FastAPI/VPS BioCatalyst Operations service; B0 assigns its named on-call owner |

No team creates a second writer because an upstream contract is temporarily inconvenient.

W0 must turn every row above into an executable producer map: producer module/service, canonical artifact or database, storage class, schema/version, cadence, retry/replay policy, consumer contract, and named operational owner. “Shared” without those fields is not an owner.

B0 cannot close with any of the three pending registrations unresolved: Corporate company identity, the Market Data security master, and the BioCatalyst Operations on-call owner. B2 waits for the first two; O1 waits for the operations registration; Terminal user-state work remains owned by the Terminal/Supabase plane throughout.

---

## 18. W0–W8 delivery program

### 18.1 Delivery assumption

An aggressive eight-week **facts-first** closed-beta hypothesis assumes:

- two backend/data engineers;
- one ML/quant engineer focused on labels, baselines, and forward-ledger scaffolding—not production PoS/EV authority;
- one full-stack product engineer;
- fractional SRE;
- one biopharma analyst;
- part-time finance and IP support; and
- a high-judgment product designer before frontend implementation.

A two-engineer team should budget roughly sixteen to twenty-four weeks for the same bounded beta. A credible full system—historical cohort reconstruction, literature/patent depth, PoS, EV, financing simulation, global regulators, and enterprise data products—is a multi-quarter program.

W0 must measure the workload before committing the calendar: daily source-change volume, identity ambiguity rate, endpoint/catalyst ambiguity, minutes per adjudication, bilingual-QA burden, queue p50/p95/p99 age, error sensitivity by object family, and source/parser failure rates. Staffing and the eight-week date are re-estimated from those observations; the numbers above are not capacity evidence.

The numbered gates below overlap. They are acceptance stages, not nine sequential full weeks.

### 18.2 Gate table

| Gate | Build and dependencies | Required artifacts | Acceptance | Initial authority | Human burden |
|---|---|---|---|---|---|
| W0 — Contract/workload freeze | Interface-kit boundary, executable one-writer map, ontology/vocabularies, rights, outcome targets, evidence coverage, UI home, workload measurement | Core schemas, producer/store/cadence map, source/vocabulary registries, outcome policies, golden-set specs, queue/workload report, source-SLO manifest | Every feature maps source → producer → artifact → transform → consumer; SLO manifest freezes launch-critical classes, denominators/opportunities, freshness thresholds, completeness-drift limits, consecutive-miss limits, severity weights, and aggregation; schema CI passes; beta scope/date re-estimated | Internal | Measured, not assumed |
| O1 — Persistent operations substrate | VPS/service scheduler, queues, migrations, credentials, object store/database, watermarks, BioCatalyst domain-ledger storage, replay and incident ownership | Deployment/service manifests, secret map, migrations, append-only ledger tables/interfaces, queue policy, SLO instrumentation, runbooks | Restart/replay/idempotency/append tests pass; no canonical heavy data in git; source-SLO manifest is machine-evaluable and opportunity accounting visible | Internal | SRE-owned infrastructure; BioCatalyst owns domain rows |
| W1 — Official evidence substrate | Ingest ClinicalTrials.gov/AACT and FDA-family sources only | Connectors, receipts, watermarks, raw manifests, bitemporal migrations, replay command | Idempotent reruns; deterministic prospective replay; supported as-of bounds enforced; all raw objects hashed; future records rejected | Internal | Measured weekly |
| W2 — Identity graph | Resolve issuer, security, organization, asset, target, indication, trial, application, temporal owner | Entity tables, entity links, alias registry, review queue, contradiction store | 1,000 adjudicated links is a coverage checkpoint only; pre-sized per-entity-family lower-confidence-bound gates in section 20.3 clear; ambiguous records never silently merge | Internal / search preview | Measured initially |
| W3 — Change engines | Exact trial diffs, endpoint alignment, registry-observed enrollment/site/date changes, FDA/regulatory event lifecycle | Trial diff, endpoint change, observation-class signals, date-claim objects, review queue | Endpoint precision/recall gates with confidence bounds; exact path changes ≥99%; no overwrite; coverage class visible | Exact facts/diffs display; inference shadow |
| W4 — Facts product | Event Explorer, Company/Trial/Catalyst Dossiers, Evidence Thread, Change Tape, saved queries/watchlists, alerts | Bounded read APIs, product contracts, authenticated responsive surfaces | Every fact has evidence/history/coverage; filters/watchlists work; API/search/LCP budgets pass | Official facts display |
| W5 — Shared-plane adapters | Consume Corporate and Capital contracts only if implemented; otherwise ship explicit blocked/degraded states and contract fixtures | Adapters, dependency health, domain extraction fixtures, optional cash-through-catalyst display | No duplicate SEC/document/cash engine; unavailable dependencies cannot masquerade as zero or current | Landed facts display; forecasts shadow |
| W6 — Context packets and minimal Bio forecast record | Facts-only sector packet, Mastermind evidence tools, post-selection facts adapter, optional stored-baseline forecast adapter, label/forecast scaffolding | Packet, lobe run, reader, adapters, contribution trace, persistent minimal Bio-owned forecast/outcome ledger; this does not reopen the deferred Neural Web dashboard/promotion work in `BRIDGE-U19` | Deterministic packets; facts are display/context; every forecast is stored shadow; no selection/order/gate/size mutation; unauthorized fields rejected | A1 explain for facts; A2 only if separately earned; forecasts shadow |
| W7 — Analyst/customer operations | Source health, review/adjudication, corrections, customer triage, bilingual QA, second-pack interface-kit test | Quality console, queue metrics, correction propagation, state-atlas results | Queue tail and reviewer agreement inside measured bounds; correction/source drills pass | Display/context |
| W8 — Soak and closed beta | Production operations, reconciliation, beta QA, rights and rollback | Per-source opportunity/freshness/completeness dashboard, license ledger, rollback runbook, beta pack | Fourteen-day severity-weighted soak; zero untraceable cards; no unresolved Sev-1/2; consecutive-miss, stale, rollback, and parser-drift drills pass | Facts-first display/context launch |

### 18.3 Critical path

    W0 → O1 → W1 → W2 → W3 → W4
                         └────→ W5 ─┐
                              W6 ───┴→ W7 → W8

Design starts during W0 from production-shaped fixtures and proceeds in parallel with W1–W2. Frontend implementation starts only after content and interaction contracts are stable enough to avoid designing fantasy data.

### 18.4 W0 decisions that cannot be deferred

1. Executable registrations for Corporate company identity, Market Data security master, Terminal/Supabase user state, BioCatalyst Operations/on-call, documents, capital structure, and sector objects; B2/O1/D1 remain blocked where an owner is unresolved.
2. Macro Dashboard versus Terminal frontend responsibility.
3. Stable identifier policy.
4. Bitemporal and source-evidence contract.
5. Outcome taxonomy.
6. License classes and redistribution policy.
7. Authority ladder.
8. W0 universe.
9. Analyst review workflow.
10. Product navigation and cross-sector shell.
11. Baseline market-data entitlement.
12. Reference mockups and visual acceptance suite.
13. Persistent operations owner, canonical storage, queues, migrations, and secrets.
14. Measured analyst/reviewer workload and a calendar re-estimate.

### 18.5 Recommended beta universes

Do not begin with every global biotech.

Maintain two explicitly separate universes.

**Prospective live product universe:**

- all active US-listed biotech/pharma securities above a minimum liquidity floor;
- their active clinical-stage assets and indications;
- all associated interventional trials;
- issuers with a disclosed FDA/PDUFA/AdCom event;
- current portfolio/watchlist companies regardless of liquidity;
- relevant direct competitors; and
- private companies when they enter a tracked competitive landscape.

**Historical model/adjudication cohort:**

- securities and issuers discovered from a historical security master, not today's listings;
- delisted, bankrupt, acquired, reverse-merged, and renamed issuers;
- abandoned, returned, failed, and silently discontinued programs;
- trials and applications found from historical registry/regulator cohorts independently of current company survival; and
- explicit observation/coverage classes for records that cannot be fully reconstructed.

The live universe drives product workload. The historical cohort drives model validity. Neither is used as a shortcut for the other.

Expand only after identity, source, and analyst-queue SLOs remain healthy.

### 18.6 Facts-first beta product wedge

The fastest product that already beats BPC:

1. universal event and catalyst explorer;
2. company, catalyst, and trial dossiers;
3. primary-source evidence;
4. prospectively complete trial-version differences plus honestly bounded historical versions;
5. honest date ranges and revisions;
6. cash-through-catalyst only when the shared Capital Structure plane is implemented and healthy;
7. saved cohorts and alerts;
8. Change Tape;
9. bounded product read API and export; and
10. Mastermind evidence retrieval.

The eight-week product does **not** promise calibrated PoS, EV, patent/literature depth, global coverage, enterprise bulk/API/MCP, or a new Prophet selection signal. Those remain later research/product waves while this facts-first product is already commercially useful.

### 18.7 Post-beta moat program

The next moat layer:

- point-in-time historical reconstruction;
- outcome adjudication;
- calibrated transition and approval probability;
- comparable-trial engine;
- competitive asset-indication graph;
- foreign regulatory read-through;
- label, safety, patent, and exclusivity history;
- deal economics;
- financing and dilution distributions;
- management track record;
- market-response and options integration;
- earnings/transcript contradiction engine;
- personalized generated briefs;
- webhooks, bulk data, and MCP;
- Prophet forward shadow; and
- cross-sector links.

“Historical reconstruction” means quantified coverage-class backfill plus exact service-launch-forward history—not invented daily replay.

### 18.8 Later

Defer:

- production PoS/approval and EV authority until forward evidence clears the promotion gates;
- broad literature/publication graph and patent/exclusivity engine;
- enterprise bulk, webhooks, and MCP;
- non-US regulator/trial comprehensiveness;
- full medical-device vertical;
- community scoring;
- editorial personalities and partner watchlists;
- podcasts and media;
- broad analyst-rating coverage;
- expensive commercial prescription data;
- global patent legal opinion;
- real-time microstructure;
- contact database;
- education/gamification; and
- full institutional redistribution until rights and support are mature.

---

## 19. Frontend and cross-repo build architecture

### 19.1 Recommended home

The richest authenticated BioCatalyst surfaces should live in the one responsive Mastermind Terminal application, which is currently Next.js 16.2.9, React 19.2.4, and Tailwind 4 in the connected charting-app repository.

Fresh `origin/master` inspection on 2026-08-01 found the authenticated route group at `terminal/app/(shell)`, with existing `AppShell`, `AppNav`, and `SearchModal` primitives. BioCatalyst extends those seams; it does not create a parallel shell, navigation rail, search system, session model, or global stylesheet.

Macro Dashboard should own:

- BioCatalyst-owned source and domain ingestion plus its persistent-service definitions;
- canonical contracts;
- backend APIs;
- Neural Web;
- Mastermind brain integration;
- Prophet bridge;
- compact product artifacts;
- public marketing/preview surfaces; and
- shared data health.

Mastermind Terminal should own:

- authenticated BioCatalyst Cockpit;
- Explorers;
- Company/Asset/Trial/Catalyst Dossiers;
- Change Tape;
- Research Workbench;
- graph and scenario interactions;
- responsive product shell; and
- cross-sector desk switching.

This is a recommended W0 architecture, not permission to fork auth, billing, data contracts, or business logic between repositories.

The current Terminal primary rail is a compact fixed set—Chart, Analyst, Screener, Scripts, Portfolio, Alerts, Options, and Heatmap. Do not append one icon for every sector until the rail becomes another BPC-style menu. The suite needs one high-level workspace switcher:

    Markets
    Sector Intelligence
      BioCatalyst
      Government & Procurement
      Shipping & Trade
      Mining
      Energy
      Agriculture

Inside a sector workspace, local navigation uses the shared Cockpit / Explore / Changes / Research / Data grammar. The global rail remains stable. Deep links, back behavior, command search, current portfolio, and open Mastermind context must survive a workspace switch.

### 19.2 Provisional Macro Dashboard paths

Paths should be frozen during W0, but a coherent target is:

    contracts/sector_intelligence/
      source_record.v1.schema.json
      evidence_claim.v1.schema.json
      sector_event.v1.schema.json
      feature_snapshot.v1.schema.json
      prediction.v1.schema.json
      outcome_label.v1.schema.json
      sector_intelligence_packet.v1.schema.json
      authority_manifest.v1.schema.json

    contracts/biocatalyst/
      ontology.v1.schema.json
      trial_snapshot.v1.schema.json
      trial_version_diff.v1.schema.json
      endpoint_change.v1.schema.json
      catalyst.v1.schema.json
      probability_forecast.v1.schema.json
      catalyst_ev_distribution.v1.schema.json
      biocatalyst_context.v1.schema.json

    collectors/biocatalyst/
      clinicaltrials_v2.py
      aact_snapshots.py
      drugs_at_fda.py
      openfda_regulatory.py
      fda_calendar.py
      literature.py
      patents.py

    app/biocatalyst.py                       # FastAPI /api/biocatalyst/v1 router

    services/biocatalyst/
      worker.py
      scheduler.py
      queues.py
      storage.py
      watermarks.py

    scripts/deploy/
      biocatalyst_migrate.py
      biocatalyst_0001_core.sql
      biocatalyst_0002_domain_ledger.sql

    app/deploy/
      macro-biocatalyst-worker.service
      macro-biocatalyst-scheduler.service

    config/biocatalyst_sources.yml
    docs/biocatalyst_operations_runbook.md

    engine/sector_intelligence/
      contracts.py
      connector_sdk.py
      temporal_types.py
      evidence_types.py
      query_adapters.py
      packet_interfaces.py
      health_interfaces.py

    engine/biocatalyst/
      identity.py
      trials.py
      trial_diff.py
      endpoints.py
      enrollment.py
      catalysts.py
      regulatory.py
      comparables.py
      competition.py
      probability.py
      timing.py
      safety.py
      patents.py
      partnerships.py
      financing_adapter.py
      ev.py
      market_response.py
      context.py

    data/biocatalyst/
      manifests/
      fixtures/
      model_cards/
      compact_current_packet.json

Heavy raw and historical artifacts belong in canonical object storage/database/columnar infrastructure, with manifests, schemas, bounded fixtures, model cards, and an optional size-capped current packet in git. Full trial versions, entity tables, graphs, raw documents, and domain forward ledgers do **not** live in the repository. The BioCatalyst forward ledger is domain-owned persistent storage exposed through a versioned adapter.

B0 freezes these provisional operations/API paths, process topology, database/object-store names, migration order, and deployment owner before O1 coding. An ad hoc render job or unregistered VPS script is not an acceptable substitute.

### 19.3 Provisional Terminal paths

Exact leaf paths require a fresh Terminal worktree during D0, but the current shell contract is:

    terminal/app/(shell)/biocatalyst/
      page
      companies
      catalysts
      trials
      changes
      research
      data

    terminal/app/api/biocatalyst/[...path]/route.ts

    terminal/components/chrome/AppShell.tsx        # extend existing
    terminal/components/AppNav.tsx                 # extend existing
    terminal/components/SearchModal.tsx            # extend existing

    terminal/components/sector-intelligence/
      SectorSwitcher
      CommandBar
      DecisionSentence
      TemporalBraid
      EvidenceThread
      ImpactTrace
      ScenarioLattice        # typed dimensions/edges/branches only
      QueryLens
      ResearchTray
      AsOfControl
      DossierShell
      Explorer

    terminal/components/biocatalyst/
      CatalystRibbon
      EvidenceSpine
      ChangePulse
      ClinicalScenarioLattice # clinical/timing/financing/value/market bands
      CompanyDossier
      AssetDossier
      TrialDossier
      CatalystDossier
      CompetitiveLandscape

Shared components remain domain-neutral where their props are domain-neutral. A “TrialCard” does not enter the sector kernel.

The Terminal proxy must enforce the existing session, entitlement, CORS/origin, path-allowlist, request-size, timeout, cache, and error-normalization rules. It forwards only approved BioCatalyst routes to the Macro FastAPI service; no browser receives service credentials or object-store locations.

At the audit cutoff, Terminal [PR 164](https://github.com/chriswong6031-creator/mastermind-terminal/pull/164) was open and conflicting while changing sidebar information architecture, and [PR 170](https://github.com/chriswong6031-creator/mastermind-terminal/pull/170) was open and mergeable while changing the portfolio surface. Both touch likely BioCatalyst integration seams, and `origin/master` had newer shell/nav/proxy work than the local dirty checkout. D0/D1 must start from a fresh `origin/master` after those PRs are resolved or explicitly sequenced; they must not patch around stale paths. The repository's Active Build Map is advisory and may lag live GitHub state.

### 19.4 API shape

Canonical internal route semantics use `/v1/...`; the production Macro FastAPI prefix is `/api/biocatalyst/v1/...`, reached by Terminal through `/api/biocatalyst/[...path]`.

Facts-first beta allowlist:

- GET /v1/search;
- GET /v1/companies/{id};
- GET /v1/assets/{id};
- GET /v1/trials/{id};
- GET /v1/trials/{id}/changes;
- GET /v1/catalysts;
- GET /v1/catalysts/{id};
- GET /v1/events;
- GET /v1/evidence/{id};
- GET /v1/changes;
- GET /v1/health;
- POST /v1/query as a read-only complex Explorer query; and
- POST /v1/exports for bounded, entitlement-checked beta exports.

Saved queries, watchlists, assignments, and other user state use the existing product-shell APIs, not a new BioCatalyst writer. The beta proxy denies every unlisted BioCatalyst route.

Beta query semantics:

- as_of;
- knowledge_cutoff;
- cursor;
- limit;
- fields;
- include;
- evidence_level;
- license_scope.

Later product/enterprise endpoints add `/v1/sectors`, list/search synchronization for companies/assets, landscapes, forecast retrieval, saved-cohort execution, scenarios, bulk/incremental `updated_since` sync, service accounts, webhooks, Parquet, and MCP. They are not part of the eight-week beta allowlist.

### 19.5 API product rules

These govern the complete API; the beta implements the applicable subset and cannot advertise deferred service-account/webhook capabilities.

- credentials only in Authorization headers;
- least-privilege scopes;
- tenant boundaries;
- signed webhook delivery;
- deterministic cursor behavior;
- explicit nullable fields;
- no hidden blur/entitlement behavior in machine responses;
- source and evidence IDs on every fact;
- model and feature timestamps on every forecast;
- pagination;
- rate-limit headers;
- idempotency for writes;
- versioned schemas;
- deprecation windows;
- changelog;
- service health and source freshness; and
- audit logs.

---

## 20. Verification and model evaluation

### 20.1 Point-in-time discipline

Every historical study must:

- use source publication/acceptance time, not only effective period;
- use the object owner known at the time;
- preserve delisted, acquired, bankrupt, and abandoned programs;
- include corrections only after their publication;
- freeze feature snapshots;
- freeze comparable sets;
- align after-hours events to executable sessions;
- apply corporate actions;
- separate training, calibration, and test periods;
- group split by asset, target, sponsor, and related mechanism where leakage is possible;
- use rolling-origin evaluation; and
- record code, data, and manifest hashes.

Exact version-level replay is guaranteed only from service launch forward or inside a separately evidenced full-version interval. Backfill reports coverage by source, date, and trial; coarse AACT month-end states and claim-specific historical documents are never relabeled as daily truth.

### 20.2 Baselines

Required champions:

- phase × therapeutic-area transition table for PoS;
- historical median phase duration for timing;
- source's latest disclosed date constraint as the naïve interval-timing baseline;
- simple cash/burn extrapolation for runway comparison;
- historical event-family return distribution for market response;
- option-implied move for event volatility;
- structured-filter-only comparables; and
- no-change/no-alert baseline for change materiality.

A sophisticated model that cannot beat the simple baseline remains a research artifact.

### 20.3 Model gates

Point estimates do not pass a model gate. Every threshold is pre-registered by model family × target × horizon, evaluated on a locked point-in-time set, and accompanied by effective sample size, positive/negative or competing-event counts, cluster-aware confidence bounds, and the relevant multiple-search/FDR adjustment. Challenger-versus-baseline comparisons use paired block/cluster bootstrap or another declared paired procedure. These are research eligibility gates; authority still follows Article 3 and A5 governance.

Probability:

- lower confidence bound on Brier skill at least 10% over the phase × therapeutic-area baseline;
- upper confidence bound on expected calibration error no more than 0.05;
- calibration intercept and slope with the full declared confidence interval inside pre-registered equivalence bounds, initially slope 0.8–1.2;
- log loss and reliability diagram;
- subgroup stability;
- interval coverage; and
- no materially worse performance on rare-disease or sparse modalities without disclosure.

Timing and EV:

- lower confidence bound on paired CRPS or weighted-interval-score improvement at least 10% over naïve baselines;
- interval coverage by disclosure precision;
- error by event type and horizon;
- tail-loss review; and
- scenario attribution stability.

Comparables:

- lower confidence bound for nDCG at 10 at least 0.80 on a pre-sized adjudicated query set;
- diversity and time-availability checks;
- no post-outcome documents before cutoff; and
- explicit reason for every selected comparable;
- query count, assessor count, and inter-adjudicator agreement with disagreement adjudication.

Entity resolution:

- lower confidence bound for auto-merge precision at least 99.5%;
- lower confidence bound for recall at least 95% on the adjudicated set;
- separate metrics for company, asset, indication, trial, and temporal ownership;
- no silent merge below the threshold; and
- analyst queue size and aging.

Extraction:

- lower confidence bound for reported filing-amount accuracy at least 99% on reviewed fields, with absolute/relative numeric error tolerances declared by field;
- lower confidence bound for instrument and deal extraction precision at least 95%;
- lower confidence bounds for endpoint-change precision at least 95% and recall at least 90%;
- lower confidence bound for exact registry-diff accuracy at least 99%;
- source-span coverage 100% for displayed claims; and
- reviewed record/query counts, adjudicator agreement, error taxonomy, and review burden measured by family.

### 20.4 Market utility

Do not evaluate only clinical classification.

Measure:

- abnormal return distribution;
- probability of positive abnormal return;
- top-cohort lift;
- drawdown;
- conditional tail loss;
- cost and liquidity;
- calibration of expected versus realized movement;
- option-implied benchmark;
- pre-event drift;
- financing-event interaction;
- regime and market-cap subgroups;
- portfolio concentration;
- alert timeliness; and
- decision utility of de-escalation/abstention.

Every utility result is paired with the event-study design receipt: benchmark and estimation window, public-time uncertainty, executable-session mapping, confound exclusions, overlap policy, clustered/serial-dependence correction, matched-control sensitivity, delisting returns, options-selection correction, transaction-cost model, and multiple-testing family. Results that materially change under reasonable design choices remain exploratory.

### 20.5 Forward ledger

Every forecast record includes:

- forecast ID;
- target and horizon;
- entity and event IDs;
- knowledge cutoff;
- feature snapshot ID/hash;
- outcome policy;
- scenario probabilities;
- return/value distribution;
- model and calibration;
- authority;
- publication state;
- resolution state;
- outcome and evidence;
- later correction;
- grade; and
- promotion/retirement decision.

The canonical BioCatalyst ledger lives in persistent domain storage, not git. Nightly remains the only advancer of **governed maturity/resolution state** under current repository law. Persistent intraday source services may append single-writer observations, facts, and source receipts to their own domain streams; they do not rewrite grades, maturity, or promotion state.

### 20.6 Model cards

Each model card states:

- intended use;
- forbidden use;
- target;
- unit of observation;
- training/calibration/test periods;
- data sources and rights;
- missingness;
- label policy;
- baseline;
- performance and calibration;
- subgroup performance;
- uncertainty;
- drift checks;
- authority;
- rollback model;
- owner; and
- next review date.

### 20.7 Product tests

Frontend:

- desktop 1440×900;
- tablet 820×1180;
- mobile 390×844;
- dark and light;
- English and Chinese;
- keyboard-only;
- reduced motion;
- screen-reader labels;
- long company/drug/indication names;
- empty and stale states;
- partial permissions;
- conflicting evidence;
- large result sets;
- slow networks; and
- data refresh during interaction;
- historical-mode navigation and safe reset;
- scenario cloning from a historical state;
- customer alert triage;
- analyst correction propagation;
- Research Tray continuity across sections/entities; and
- workspace switching with search, portfolio, as-of, and Mastermind context intact.

Performance:

- API p95 under 500ms for primary reads;
- search p95 under 1.2s;
- LCP p75 under 2.5s;
- no layout shift from late entitlement checks;
- virtualized large tables;
- progressive graph loading;
- bounded evidence payloads;
- cached but truthfully stamped summaries; and
- no client bundle carrying full datasets.

### 20.8 Adversarial checks

- future filing injected into a historical run must be rejected;
- ownership transfer after cutoff must not alter the past owner;
- endpoint reorder without semantic change must not alert materially;
- primary/secondary switch must alert;
- quarter/half-year guidance must not collapse to a point;
- stale FDA source must show stale;
- positive operating cash flow must not emit nonsensical finite runway;
- missing option liquidity must not imply a reliable expected move;
- FAERS spike must not be worded as causal;
- LLM narrative must not change a stored probability;
- unauthorized packet fields must be rejected;
- shared company/capital objects must have one writer; and
- synthetic Mining pack must pass the kernel contract without biopharma fields.

---

## 21. Product, business model, and moat

### 21.1 Positioning

BPC sells access to a broad event database. BiopharmIQ sells biopharma discovery and lead generation. BioCatalyst should sell decision-grade temporal intelligence:

> Every material biopharma change, connected to its evidence, probability, financing path, competitive context, market implication, and portfolio exposure.

### 21.2 Initial customer segments

| Segment | Primary job | Product emphasis |
|---|---|---|
| Sophisticated retail investor | Avoid surprises and research upcoming events | Cockpit, dossiers, alerts, scenarios |
| Independent analyst / small fund | Build and monitor point-in-time theses | Workbench, API, exports, history |
| Biotech specialist fund | Integrate evidence, models, and portfolio exposure | Full graph, bulk/API, collaboration |
| Biotech BD / vendor | Find companies, technologies, trials, funding, and contacts | Discovery/cohorts; optional licensed contacts |
| Pharma strategy | Competitive landscape and trial/regulatory change | Landscape, comparables, alerts, research packets |
| Data customer | Feed normalized, temporal objects into internal systems | API, bulk, webhook, MCP |

### 21.3 Packaging hypothesis

Do not anchor the premium product to BPC's $25–$75 retail range. That price reflects a calendar/database product.

Test:

- a free or low-cost delayed catalyst explorer as acquisition;
- BioCatalyst Pro for active investors;
- MastermindX bundle for integrated Prophet/Neural Web/market intelligence;
- Team/Research workspace for collaboration and history;
- Enterprise Data for API, bulk, webhooks, service accounts, rights, and support;
- optional BD/contact add-on; and
- cross-sector Intelligence Suite bundle.

Exact price should follow willingness-to-pay tests and data-license economics. The core hypothesis is that evidence history, financing survival, calibrated scenarios, and machine access support materially higher value than a calendar subscription.

### 21.4 Moat ladder

Month 0–3:

- superior UX;
- unified queries;
- source lineage;
- trial changes;
- cash-through-catalyst;
- Mastermind retrieval.

Month 3–9:

- adjudicated entity and outcome history;
- date-revision history;
- competitive graph;
- comparable retrieval;
- management track record;
- alerts and customer workflow.

Month 9–24:

- forward-calibrated models;
- market-response and financing interaction;
- customer scenarios and collaborative evidence;
- API ecosystem;
- cross-sector evidence paths;
- correction reputation; and
- accumulated analyst operations.

The long-term moat is not “we also download ClinicalTrials.gov.” It is an auditable temporal memory of the sector.

### 21.5 Why the sector platform matters

The product economics improve with every pack:

- shared ingestion runtime;
- shared evidence and identity infrastructure;
- shared product shell;
- shared Mastermind and API;
- shared billing and permissions;
- shared alert delivery;
- shared graph/search;
- cross-sell;
- cross-sector evidence;
- reusable analyst operations; and
- lower marginal cost for the next niche.

The important architectural constraint is that each pack remains rigorous and domain-native. Reuse infrastructure, not generic understanding.

---

## 22. Risk register

| Risk | Failure mode | Mitigation |
|---|---|---|
| Historical selection bias | Only visible successful assets enter cohorts | Capture discontinuations, silent failures, delisted sponsors, censoring |
| Point-in-time leakage | Revised registry/filing data appears in the past | Immutable snapshots, publication time, cutoff tests |
| Entity error | Drug, indication, owner, or trial silently mislinked | Confidence, review queue, temporal ownership, precision gate |
| False precision | Q4 or uncertain patent date shown as exact | Date distributions, original wording, assumption class |
| Model theater | Five-factor score looks scientific but is uncalibrated | Distinct layers, baselines, forward ledger, authority caps |
| Duplicate infrastructure | BioCatalyst rebuilds documents/cash/SEC | One-writer contracts and shared adapters |
| UI sprawl | Feature parity recreates competitor navigation | Explorer lenses and dossier grammar |
| Generic vertical template | Every sector looks the same but understands little | Domain card specs and pack-owned ontology/models |
| Source outage | Old data silently presented as current | Watermarks, stale state, health console, automatic de-escalation |
| Parser drift | Source schema change creates plausible wrong facts | Contract fixtures, source hashes, failure alarms, review |
| Patent overclaim | Calculated expiry treated as legal truth | Assumption classes, confidence, legal review |
| FAERS misuse | Report counts described as causality/incidence | Explicit inference policy and language guards |
| Market-data rights | Options/quotes redistributed without rights | Entitlements and license ledger |
| Competitor dependency | BPC becomes production source | Primary/licensed ingestion only |
| Human queue explosion | Long-tail ambiguity overwhelms analyst | Confidence routing, bounded universe, burden metrics |
| Cross-sector coupling | One pack's schema infects the kernel | Synthetic second-pack tests |
| LLM overreach | Fluent text changes scores or hides nulls | Retrieval-first tools, immutable forecasts, authority validation |
| Design dilution | Builders ship generic tables before signature system | Mockups/reference crops and visual gates before code |
| Mobile afterthought | Desktop tables collapse on phones | One responsive product and required viewport tests |

---

## 23. Implementation PR map

This is a handoff sequence, not authorization to merge conflicting contracts without coordination.

### PR B0 — Contract and ownership freeze

- source/evidence/event/feature/prediction/outcome/authority schemas;
- biopharma ontology;
- one-writer matrix;
- source rights registry;
- outcome policies;
- compact fixtures;
- synthetic second-sector pack.

### PR O1 — Persistent operations substrate

- VPS/service scheduler and supervised workers;
- queues, retries, dead-letter handling, and replay;
- database/object-store migrations and retention;
- credentials and entitlement-safe service configuration;
- source watermarks and per-opportunity SLO accounting;
- persistent append-only BioCatalyst forecast/outcome ledger migrations and interfaces, with BioCatalyst as row owner;
- named operations owner and incident runbooks;
- no heavy canonical corpus or forward ledger in git.

### PR B1 — ClinicalTrials.gov evidence substrate

- API v2 and bulk adapters;
- immutable raw manifests;
- trial snapshots;
- overlap and full-reconcile logic;
- source watermarks;
- replay tests.

### PR B2 — Identity and temporal ownership

- company/security bridge;
- asset, target, indication, sponsor, trial, application IDs;
- alias and temporal-owner records;
- review queue;
- adjudicated golden set.

### PR B3 — Trial changes

- exact path diffs;
- endpoint alignment;
- enrollment/site/timing changes;
- alert contract;
- change fixtures;
- precision/recall report.

### PR B4 — FDA and regulatory graph

- Drugs@FDA/openFDA/Orange/Purple/AdCom/Federal Register;
- regulator-published labels, safety, public CRLs/review material, and shortages;
- source priority and contradiction handling.

Issuer-disclosed PDUFA dates, holds, CRL details, and other issuer-only regulatory claims do not enter through B4. They remain visibly unavailable until B5 can consume the landed Corporate document/span contract.

### PR B5 — Corporate and capital adapters

- consume shared company documents/events/spans;
- consume shared capital-structure projection;
- extract issuer-disclosed PDUFA/hold/CRL, catalyst/asset/trial/partnership/CMC claims;
- no duplicate generic collector or cash calculation.

### PR D0 — Sector-suite visual system

In the Terminal repository:

- fresh `origin/master` worktree after PR 164/170 are resolved or explicitly sequenced;
- extension of the existing `(shell)` route group, `AppShell`, `AppNav`, and `SearchModal`;
- exact product IA;
- production-shaped content fixtures;
- suite-wide Decision Sentence / Temporal Braid / Evidence Thread / Impact Trace / Scenario Lattice / Query Lens / Research Tray contracts;
- BioCatalyst Catalyst Ribbon and clinical lattice;
- Government Program Cascade;
- Shipping Flow Field as the deep physical-flow fixture;
- one production-shaped critical workflow plus complete trust/state-atlas pass for Mining, Energy, and Agriculture;
- cross-sector switcher;
- token matrix and state-atlas harness;
- customer-triage and analyst-adjudication state machines;
- historical-mode contract;
- EN/ZH terminology and content contract;
- dark/light/Chinese/desktop/tablet/mobile reference images;
- accessibility and motion specification;
- performance budgets.

### PR D1 — Explorer and dossier shell

- universal command search;
- Explorer query state;
- Dossier shell;
- Decision Sentence;
- Evidence Thread and Research Tray;
- As-of control and historical-mode chrome;
- failure/trust state atlas;
- watch/cohort/export actions;
- responsive and accessibility tests.

### PR D2 — BioCatalyst flagship surfaces

- Cockpit;
- Event Explorer;
- Company Dossier;
- Trial Dossier;
- Catalyst Dossier;
- Change Tape;
- production-shaped visual verification.

### PR M0 — Baselines and ledgers

Later research wave, outside the facts-first eight-week commitment:

- transition baseline;
- timing baseline;
- comparable baseline;
- feature snapshot;
- evaluation/adjudication extensions over the minimal O1/W6 forecast/outcome ledger;
- model-card and evaluation harness.

### PR M1 — Challenger models

Later research wave, outside the facts-first eight-week commitment:

- comparable retrieval;
- competing-risk PoS;
- timing;
- financing-survival join;
- EV and market response;
- shadow outputs only.

### PR N0 — Neural Web and Mastermind

- sector packet;
- lobe run;
- one explicit reader;
- Mastermind tools;
- evidence citations;
- stale/contradiction behavior;
- authority contract tests.

### PR P0 — Prophet shadow

- post-selection facts adapter (display/context);
- optional forecast adapter only for predictions already written to the BioCatalyst domain ledger (shadow);
- frozen snapshot join;
- no-order/no-gate/no-size invariants;
- contribution trace;
- forward evaluation.

### PR O2 — Operations and beta

- per-source opportunity, freshness, completeness-drift, and consecutive-miss status;
- analyst queue;
- correction workflow;
- SLOs;
- incident/rollback drills;
- alert-quality dashboard;
- closed-beta instrumentation.

---

## 24. Source register

All current product observations are dated 2026-08-01.

### 24.1 BioPharmCatalyst

- [Homepage](https://www.biopharmcatalyst.com/)
- [Current pricing and plan comparison](https://www.biopharmcatalyst.com/sign-up)
- [Getting Started](https://www.biopharmcatalyst.com/getting-started)
- [FAQ](https://www.biopharmcatalyst.com/resources/faq)
- [About](https://www.biopharmcatalyst.com/info/about-us)
- [Terms of Use](https://www.biopharmcatalyst.com/terms-of-use)
- [Privacy Policy](https://www.biopharmcatalyst.com/privacy-policy)
- [FDA Calendar](https://www.biopharmcatalyst.com/calendars/fda-calendar)
- [Drug Pipeline Database](https://www.biopharmcatalyst.com/companies/drug-pipeline-database)
- [Cash Database](https://www.biopharmcatalyst.com/analysis/cash-database)
- [Historical Probability of Success](https://www.biopharmcatalyst.com/analysis/probability-of-success)
- [PDUFA Calendar](https://www.biopharmcatalyst.com/calendars/pdufa-calendar)
- [Catalyst Impact](https://www.biopharmcatalyst.com/calendars/catalyst-impact)
- [Conference Calendar](https://www.biopharmcatalyst.com/calendars/conferences)
- [Earnings Calendar](https://www.biopharmcatalyst.com/calendars/earnings-calendar)
- [IPO Calendar](https://www.biopharmcatalyst.com/calendars/ipo-calendar)
- [Company page example](https://www.biopharmcatalyst.com/company/BBIO)
- [Portfolio Tools](https://www.biopharmcatalyst.com/portfolio-tools)
- [Developer API documentation](https://www.biopharmcatalyst.com/v1-docs/api#/)
- [FDA API operation](https://www.biopharmcatalyst.com/v1-docs/api#/operations/fdaCalendar.index)
- [Historical Catalyst API operation](https://www.biopharmcatalyst.com/v1-docs/api#/operations/historicalCatalysts.index)
- [PDUFA API operation](https://www.biopharmcatalyst.com/v1-docs/api#/operations/pdufa.index)
- [Institutional API landing page](https://www.biopharmcatalyst.com/api-landing-page)

### 24.2 BiopharmIQ

- [Homepage and current pricing/list-service FAQ](https://www.biopharmiq.com/)
- [About](https://www.biopharmiq.com/about-us)
- [Why Us](https://www.biopharmiq.com/why-us)
- [Clinical-stage filtering guide](https://www.biopharmiq.com/post/how-to-filter-companies-by-clinical-stage-in-biopharmiq-a-fast-guide-for-partnership-strategy)
- [Company screener public view](https://app.biopharmiq.com/companies-free?state=33&technology=66)
- [Company profile example](https://app.biopharmiq.com/companies/3502)
- [Contact search and export guide](https://www.biopharmiq.com/post/how-to-find-and-export-contacts-in-biopharmiq-a-step-by-step-guide-for-sales-marketing-teams)
- [Clinical-trial workflow guide](https://www.biopharmiq.com/post/how-to-explore-clinical-stage-antibody-companies-from-company-screener-search-to-clinical-trial-dat)
- [Clinical-trial alert builder](https://app.biopharmiq.com/clinicaltrial-notification-create)
- [Funding workflow](https://www.biopharmiq.com/post/how-to-track-immuno-oncology-companies-funding-activities-in-the-past-6-months)
- [PDUFA workflow example](https://www.biopharmiq.com/post/november-pdufa-update-4-approvals-and-1-adcomm)
- [AI technology landscape method](https://www.biopharmiq.com/post/ai-in-bio-pharma-technology-development)
- [Official platform FAQ](https://docs.google.com/document/d/e/2PACX-1vTSv9KYRlFjE1sWvV3w8tIz4-VYJhXc8aOutjT-3MDmul0rR3jTKFk1yQSIJOoEB2j1lFFmhaRwKWnE/pub)

### 24.3 Clinical trials

- [ClinicalTrials.gov API v2](https://clinicaltrials.gov/data-api/api)
- [API migration guide](https://clinicaltrials.gov/data-api/about-api/api-migration)
- [Study data structure](https://clinicaltrials.gov/data-api/about-api/study-data-structure)
- [How to read a study record and Record History](https://clinicaltrials.gov/study-basics/how-to-read-study-record)
- [ClinicalTrials.gov terms](https://clinicaltrials.gov/about-site/terms-conditions)
- [AACT snapshots](https://aact.ctti-clinicaltrials.org/downloads/snapshots?type=pgdump)
- [WHO ICTRP primary-registry network](https://www.who.int/tools/clinical-trials-registry-platform/network/primary-registries)
- [EMA Clinical Trials Information System](https://www.ema.europa.eu/en/human-regulatory-overview/research-development/clinical-trials-human-medicines/clinical-trials-information-system)

### 24.4 FDA and openFDA

- [Drugs@FDA data files](https://www.fda.gov/drugs/drug-approvals-and-databases/drugsfda-data-files)
- [Orange Book data files](https://www.fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files)
- [FDA Purple Book source page](https://www.fda.gov/drugs/therapeutic-biologics-applications-bla/purple-book-lists-licensed-biological-products-reference-product-exclusivity-and-biosimilarity-or)
- [FDA guide to navigating the Purple Book](https://www.fda.gov/media/182175/download)
- [FDA Advisory Committee Calendar](https://www.fda.gov/advisory-committees/advisory-committee-calendar)
- [PDUFA VII goals letter](https://www.fda.gov/media/151712/download)
- [openFDA authentication and limits](https://open.fda.gov/apis/authentication/)
- [openFDA query parameters](https://open.fda.gov/apis/query-parameters/)
- [openFDA licensing](https://open.fda.gov/license/)
- [Drug label endpoint](https://open.fda.gov/apis/drug/label/)
- [FAERS adverse-event endpoint](https://open.fda.gov/apis/drug/event/)
- [Drug shortage endpoint](https://open.fda.gov/apis/drug/drugshortages/)
- [Drug shortage fields](https://open.fda.gov/apis/drug/drugshortages/searchable-fields/)
- [Complete Response Letter endpoint](https://open.fda.gov/apis/transparency/completeresponseletters/)
- [FDA Drug Safety Communications](https://www.fda.gov/drugs/drug-safety-and-availability/drug-safety-communications)
- [FDA safety-related labeling changes](https://www.fda.gov/safety/medical-product-safety-information/drug-safety-related-labeling-changes)
- [FDA postmarketing requirements and commitments](https://www.fda.gov/drugs/guidance-compliance-regulatory-information/postmarket-requirements-and-commitments)
- [FDA inspection classification database](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/inspection-classification-database)
- [FDA Data Dashboard](https://www.fda.gov/about-fda/performance-data/fda-data-dashboard)
- [FDA pharmaceutical warning letters](https://www.fda.gov/drugs/enforcement-activities-fda/warning-letters-and-notice-violation-letters-pharmaceutical-companies)
- [FDA import-alert search](https://www.fda.gov/industry/import-alerts/search-import-alerts)
- [FDA inspection observations and Form 483 context](https://www.fda.gov/inspections-compliance-enforcement-and-criminal-investigations/inspection-references/inspection-observations)
- [FDA OII FOIA Electronic Reading Room](https://www.fda.gov/about-fda/office-inspections-and-investigations/oii-foia-electronic-reading-room)

### 24.5 SEC

- [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC Developer Resources](https://www.sec.gov/about/developer-resources)

### 24.6 Literature and grants

- [NCBI E-utilities manual](https://www.ncbi.nlm.nih.gov/books/NBK25497/)
- [PubMed data download](https://pubmed.ncbi.nlm.nih.gov/help/#download-pubmed-data)
- [PubTator3 API](https://www.ncbi.nlm.nih.gov/research/pubtator3/api)
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)
- [Crossref rate-limit implementation](https://community.crossref.org/t/updates-to-rest-api-rate-limits/14872)
- [NIH RePORTER API v2](https://api.reporter.nih.gov/?urls.primaryName=V2.0)
- [NIH RePORTER ExPORTER](https://reporter.nih.gov/exporter/)

### 24.7 Patents

- [USPTO Open Data Portal APIs](https://data.uspto.gov/apis)
- [USPTO Patent File Wrapper API](https://data.uspto.gov/apis/patent-file-wrapper/application-data)
- [USPTO registration notice](https://www.uspto.gov/about-us/news-updates/uspto-open-data-portal-require-registration-access-beginning-june-18-2026)
- [EPO Open Patent Services](https://www.epo.org/en/searching-for-patents/data/web-services/ops)
- [EPO OPS terms](https://www.epo.org/en/service-support/ordering/terms-and-conditions/ops-terms-and-conditions)

### 24.8 Controlled vocabularies

- [RxNorm](https://www.nlm.nih.gov/research/umls/rxnorm/)
- [FDA Substance Registration System / UNII](https://precision.fda.gov/uniisearch)
- [NCI Enterprise Vocabulary Services and NCI Thesaurus](https://www.cancer.gov/about-nci/organization/cbiit/vocabulary)
- [UMLS](https://www.nlm.nih.gov/research/umls/)
- [MeSH](https://www.nlm.nih.gov/mesh/meshhome.html)
- [WHO ICD](https://www.who.int/standards/classifications/classification-of-diseases)
- [Orphanet nomenclature](https://www.orphadata.com/orphanet-nomenclature-for-coding/)
- [MedDRA](https://www.meddra.org/)
- [CDISC controlled terminology](https://www.cdisc.org/standards/terminology/controlled-terminology)

---

## 25. Final assessment

### 25.1 BioPharmCatalyst

| Dimension | Assessment |
|---|---|
| Product breadth | High |
| UI quality | Low-to-medium and dated |
| Mathematical sophistication visible from product | Low |
| Curation/history value | Medium-high |
| Current-state cloneability | 8/10 |
| Historical cloneability | 5/10 |
| Data moat | Medium |
| Algorithmic moat | Low |

### 25.2 BiopharmIQ

| Dimension | Assessment |
|---|---|
| Company/BD discovery | Strong |
| Investor prediction | Weak |
| UI quality | Operational but generic |
| Private-company/contact value | Medium-high |
| Public-data cloneability | 8.5/10 |
| Contact/private-company cloneability | 4–6/10 |
| Data moat | Medium |
| Algorithmic moat | Low |

### 25.3 MastermindX opportunity

| Dimension | Assessment |
|---|---|
| Ability to reach feature parity | High |
| Ability to exceed UI/UX | Very high |
| Ability to exceed visible engines | Very high |
| Hardest requirement | Temporal identity, historical outcomes, calibration, analyst operations |
| Near-term product payoff | Very high |
| Long-term cross-sector payoff | Exceptional |

### 25.4 Final decision

Proceed.

Build the shared kernel and BioCatalyst pack around primary evidence, bitemporal memory, and one-writer contracts. Ship the beautiful evidence-first product before waiting for an authoritative predictive model. Accrue every forecast from day one. Let BioCatalyst earn progressively deeper Prophet authority only through point-in-time evidence.

The winning product is not “BPC with prettier tables.”

It is a sector operating system that can say:

> Here is what changed.
> Here is the original evidence.
> Here is what it changes in the trial, timeline, financing, competition, and value distribution.
> Here is what the market already implies.
> Here is what remains uncertain.
> Here is how it connects to the rest of the world.

BioCatalyst is the first high-payoff proving ground. HigherGov/defense procurement, Shipping and Trade, Mining, Energy, and Agriculture turn the same architecture into a family of connected intelligence businesses—and give Neural Web a far richer world model than any standalone market dashboard can produce.
