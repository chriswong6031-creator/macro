# Capital Structure Intelligence — competitive teardown and Mastermind build docket

Date: 2026-08-01
Status: assessment and program of record; no runtime feature is built by this docket
Canonical deliverable: this file
Targets examined: DilutionTracker.com and Dilutracker.com
Product destination: Macro Dashboard front-facing Capital Structure Intelligence desk plus a context-first Neural Web lobe and a compact Mastermind projection

## 0. Decision

Build this.

The opportunity is real, but the phrase “clone it in a few hours” describes only the screenshot. A convincing dark dashboard, instrument cards, a risk badge, and a ticker search are a one-to-two-day exercise. A trustworthy capital-structure product is a temporal accounting system: it must join filings, amendments, effectiveness notices, pricing documents, later usage disclosures, cash statements, corporate actions, and market data without confusing authorization with issuance. That reconciliation corpus is the product.

The strongest strategic move is therefore not a pixel clone. It is an evidence-first Capital Structure Intelligence system that covers the documented workflows visible across both competitors and removes their weakest shared property: opaque, difficult-to-audit conclusions.

The recommended product has four layers:

1. A canonical, point-in-time filing and instrument ledger in Macro Dashboard.
2. A front-facing discovery desk and per-ticker dossier built from that same ledger.
3. A context-only Capital Structure lobe in Neural Web and Mastermind.
4. A later, separately validated financing-probability and Prophet de-escalation layer.

The revised feasibility verdict is:

| Object | Cloneability | Mastermind payoff | Honest assessment |
|---|---:|---:|---|
| Visual shell and ticker dossier | 9.5/10 | High | Easy |
| Filing feeds, search, filters, guides, watchlists | 9/10 | High | Straightforward |
| Deterministic shelf / ATM / offering math | 8/10 | Very high | Achievable with careful rules |
| Full warrant / convertible / ELOC lifecycle | 7/10 | Extremely high | Document parsing and reconciliation are the work |
| Reliable float and fully diluted supply | 6/10 | Extremely high | Definitions, holder status, and corporate actions create ambiguity |
| High-trust historical corpus | 5.5/10 | Extremely high | Backfill and correction labor dominate |
| Calibrated 7 / 30 / 90-day offering probability | 4/10 immediately; 8/10 after accrual | Extremely high | Cannot be honestly manufactured from retrospective labels |
| Better total product than either competitor | 8.5/10 | Extremely high | Feasible as a staged program, not a cosmetic sprint |

Recommendation: authorize Waves 0–1 after review. Wave 2 begins only after the shared-contract, compatibility, pipeline-placement, and authority exit gates in this docket pass. Ship the public dossier only after its underlying ledger passes the source-reconciliation gates. Keep every Neural Web and Mastermind use context-only until its own promotion test passes. Do not copy either competitor’s opaque overall score or proprietary copy.

## 1. Scope, evidence, and access boundary

This assessment used:

- user-authorized member access to DilutionTracker.com;
- its public landing, pricing, knowledge-base, and education surfaces;
- live Open Access ticker records and authenticated member navigation;
- public pages, public API documentation, public ticker structure, and public client assets from Dilutracker.com;
- the user-provided RUBI screenshot;
- official SEC documentation;
- the current Macro Dashboard repository and adjacent company-intelligence work;
- no private source repository, private prompt, server database, or proprietary model weights.

The Dilutracker.com account reached its subscription checkout and had no paid entitlement. The audit therefore treated that product as public-only. No CSS blur was removed, no paywall or subscription control was bypassed, and no restricted record content is used in this docket. Publicly delivered client assets were useful for identifying routes, component families, and product architecture; they did not expose the backend extraction or reconciliation engine.

This distinction matters commercially. Product ideas, SEC form taxonomies, standard financial calculations, information architecture, and generic interaction patterns are reproducible. Proprietary copy, brand assets, hidden data, and source code should not be copied. Mastermind has no need to do so: its stronger product can be implemented independently from public primary data and its existing infrastructure.

Observations are labeled as:

- Observed: visible in an audited surface.
- Documented: stated in official product documentation.
- Inferred: a likely mechanism, not a verified internal implementation.
- Proposed: Mastermind design, not a competitor fact.

Pricing, coverage, and feature availability are a 2026-08-01 snapshot and can change.

## 2. The category in one sentence

Both products turn scattered SEC disclosure into the answer a small-cap trader actually wants:

> Can this issuer raise stock now, does it need to, what supply can hit, and what document or price move activates it?

DilutionTracker.com answers through a manually curated research terminal. Dilutracker.com packages a narrower version as an AI-forward report, screener, and API. The first publicly emphasizes historical reconciliation and education. The second publicly emphasizes contemporary packaging, API clarity, and self-serve discovery. A comparative accuracy benchmark was not available.

Neither public product makes the full source-to-conclusion proof chain the center of the interface. That is Mastermind’s opening.

## 3. Competitor A — DilutionTracker.com

### 3.1 Product thesis and apparent operating model

DilutionTracker is a ticker-first capital-structure research terminal focused on smaller US-listed issuers. Its landing copy says its team reads relevant filings, calculates dilution, and cross-checks the result with traders. Its knowledge base repeatedly describes manual adjustments, which is consistent with the product’s dense, curated instrument records.

The important moat is not the layout. It is a hand-reconciled issuer state built over time:

- what was registered;
- when it became effective;
- what was priced;
- what remains;
- which securities are registered for resale;
- who holds them;
- what clauses change their share equivalent;
- what a subsequent 10-Q, 10-K, 8-K, or prospectus says was actually used;
- how splits change every historical amount.

That is a modest data moat, not a proprietary-data moat. The inputs are public. The labor, taxonomy, correction history, and issuer-specific exceptions are cumulative.

The site’s advertised covered universe has varied across public copy and member UI, roughly around 2,300–2,500 small-cap issuers, with a subset having actionable dilution records. Mastermind should not repeat a vague number. It should publish explicit eligibility, coverage, freshness, and reviewed/unreviewed counts.

### 3.2 Information architecture observed

The authenticated product includes these principal workflows:

| Surface | Primary job |
|---|---|
| Ticker search / ticker report | Reconstruct one issuer’s current capital structure |
| New Filings | Discover recent dilution-related documents |
| Completed Offerings | Review priced transactions and terms |
| Pending S-1s | Track registration-to-pricing pipeline |
| Reverse Split | Track proposed, approved, and effective splits |
| Real-Time Notifications | Configure form and event alerts |
| Learn | Teach the filing and instrument taxonomy |
| Account / watchlists | Persist user focus and delivery preferences |

This is a strong workflow split. It supports both “I own this ticker” and “show me what changed today.” A Mastermind implementation that ships only a ticker lookup would miss half the product.

### 3.3 Ticker dossier

The audited ticker report is organized around:

1. Identity and market context
   - symbol and company name;
   - quote and extended-hours context;
   - market capitalization and enterprise value;
   - sector, industry, country, and exchange;
   - company description;
   - links to external market pages.

2. Supply and ownership facts
   - latest shares outstanding;
   - estimated float;
   - institutional ownership;
   - short interest;
   - estimated net cash per share.

3. Dilution-risk lanes
   - Overall Risk;
   - Offering Ability;
   - Overhead Supply;
   - Historical Dilution;
   - Cash Need.

4. Historical and potential supply
   - split-adjusted O/S history;
   - potential ATM shares;
   - potential pending S-1 shares;
   - registered warrants;
   - equity-line capacity;
   - convertible share equivalents.

5. Cash condition
   - cash or liquid resources;
   - operating cash use;
   - estimated runway.

6. Instrument and transaction records
   - warrants;
   - convertible notes and preferred stock;
   - ATMs;
   - equity lines;
   - shelf registrations and I.B.6 capacity;
   - pending S-1 offerings;
   - completed offerings.

7. Context tabs
   - News;
   - Holders;
   - Filings;
   - Financials.

The report’s main virtue is compression. A user can see ability, need, and overhang before opening a filing. Its main weakness is auditability: the result is often easier to consume than to reproduce.

### 3.4 Instrument ontology and fields

The following field inventory was visible in the authenticated product and its guides.

#### Warrants

- registered status;
- remaining and original quantity;
- exercise price;
- issue, exercisable, expiry, and update dates;
- known holders or owners;
- placement agent or investment bank;
- price-protection type;
- clause text or summary;
- source filing.

#### Convertible notes and preferred shares

- remaining and original principal;
- remaining and original share equivalent;
- conversion price;
- fixed or variable mechanism;
- floor, reset, or protection clause;
- holder and placement agent;
- issue, conversion, maturity, and update dates;
- source filing.

#### ATM programs

- total capacity;
- estimated remaining capacity;
- sales agent;
- start and update dates;
- source registration / prospectus chain.

#### Equity lines, ELOCs, and related purchase agreements

- total and remaining capacity;
- commencement and termination dates;
- purchase limits;
- registered share cap;
- exchange-rule constraint where disclosed;
- discount or formula;
- counterparty;
- update date.

#### Shelf registrations

- original registered amount;
- estimated amount raised;
- remaining registered capacity;
- currently raisable amount;
- I.B.6 / baby-shelf status;
- trailing 12-month amount sold under the instruction;
- non-affiliate public float inputs;
- highest qualifying recent close;
- effective and expiry dates;
- banker / sales agent;
- latest update.

#### Pending S-1 offerings

- initial filing and amendment dates;
- anticipated deal size;
- anticipated warrant coverage;
- underwriters;
- status;
- expected or actual pricing date;
- final price, shares, warrant coverage, and exercise price.

#### Completed offerings

- offering type;
- sale method;
- share equivalent;
- offer price;
- warrant coverage;
- gross amount;
- bank / placement agent;
- disclosed investors;
- pricing date.

#### Reverse splits

- proposed or approved ratio;
- vote status;
- effective date;
- current float;
- source proxy, vote result, 8-K, 6-K, or press release.

This ontology is broad enough to become Mastermind’s starting dictionary. It is not broad enough to become its data model without adding status transitions, source spans, amendment lineage, calculation versions, uncertainty, and corrections.

### 3.5 How the calculations work

The public documentation exposes several methods.

#### Potential O/S

The O/S chart uses split-adjusted reported shares as its base. It stacks potential share supply from instruments on the most recent bar. Documented approximations include:

- ATM potential shares = remaining dollar capacity divided by current price;
- pending S-1 potential shares = anticipated deal size, including expected warrant coverage, divided by current price;
- equity-line potential shares = remaining capacity divided by current price, subject to disclosed registered-share and exchange constraints;
- warrants = registered warrants outstanding, in and out of the money;
- converts = current share equivalent under the stated conversion terms.

Shelf capacity is intentionally excluded from that chart because a large authorization is not a likely single-deal share count. This is a good product decision and an important conceptual fence.

Source: https://knowledge.dilutiontracker.com/en/articles/6820942-how-do-i-interpret-the-o-s-chart

#### Float

DilutionTracker documents float as latest O/S less shares held by officers, directors, affiliates, and holders above its ownership threshold.

Source: https://knowledge.dilutiontracker.com/en/articles/5602376-how-is-your-float-calculated

Mastermind should improve this by showing the exact holder set, report date, source, and inclusion reason. “Float” is an estimate, not an SEC-standard live field.

#### Cash and runway

DilutionTracker says it can include marketable securities and investments in liquid resources, uses operating cash flow as the cash-burn basis, and can manually adjust one-time items.

Source: https://knowledge.dilutiontracker.com/en/articles/5602396-why-does-the-cash-and-cash-burn-not-match-10k-10q-on-bamsec-finviz

This explains why its result may differ from a mechanical statement reader. It also exposes a replication challenge: the adjustment ledger matters as much as the formula.

#### Offering ability

The public guide treats an effective registered shelf or a pending S-1 as the main public-offering pathways, while noting that a private placement can occur without them.

Source: https://knowledge.dilutiontracker.com/en/articles/5602359-how-do-i-know-if-the-company-can-offer

The product’s investment-bank study says its offering-ability rating uses available shelf capacity and pending S-1 registrations, while cash need and historical dilution inform likelihood.

Source: https://knowledge.dilutiontracker.com/en/articles/5722415-offerings-investment-bank-tiers-and-why-it-matters-for-small-cap-stocks

The exact overall-risk weights are not published. Any claim to have reverse-engineered the score would be speculation. Mastermind should use the visible component taxonomy, not attempt to mimic unknown weights.

#### I.B.6 / baby-shelf capacity

The competitor’s education explains the core one-third-float restriction and the importance of the highest qualifying closing price. Mastermind’s implementation must follow the current official S-3 instruction rather than relying on a simplified article.

Official source: https://www.sec.gov/files/forms-3.pdf

The required state is not merely “float below $75 million.” The engine must preserve the issuer’s eligibility determination, non-affiliate float, qualifying price and date, aggregate primary sales in the applicable prior 12-month window, amendments, and any transition conditions in the current rule.

### 3.6 Event feeds and discovery

The authenticated tables reveal the operational taxonomy:

- New Filings: ticker, company, type, name, date.
- Completed Offerings: ticker, type, method, share equivalent, price, warrants, amount, bank, investors, date.
- Pending S-1s: ticker, company, industry, first filing, expected or actual pricing date, anticipated size, estimated warrant coverage, underwriters, float, status, pricing, shares, final coverage, exercise price.
- Reverse Splits: ticker, effective date, ratio, current float, status.

This is more valuable than an undifferentiated EDGAR stream because it converts documents into state transitions. Mastermind should go further: every row should say what changed since the previous version and which issuer-state object was affected.

### 3.7 Alerts

The audited notification manager supports email and, for selected event families, SMS. Audience scopes include all relevant US issuers, the product’s covered universe, and custom ticker lists. Categories include:

- offering press releases;
- private placements;
- IPO and uplist releases;
- reverse splits;
- dilution and prospectus filings, including 424B, EFFECT, F-series, S-series, Reg A, and withdrawal forms;
- financial filings;
- material-disclosure filings;
- merger documents;
- ownership filings;
- proxies.

This is an expansive form router, but a filing alert is not enough. Mastermind should alert on semantic transitions: EFFECT received, ATM activated, capacity changed, convert reset triggered, shareholder approval obtained, O/S restated, or an earlier parse corrected.

### 3.8 Holders, filings, news, and financials

The product includes:

- a 13F holder table with institution, percent, shares, change, form, effective date, and filing date;
- filing categories for chronological, financial, prospectus, other, disclosure, ownership, and proxy records;
- company press releases;
- annual and quarterly statement grids;
- spreadsheet export.

These are useful context surfaces, not part of the core dilution engine. Mastermind should reuse existing company and market data where possible rather than rebuild a parallel filings or financial-statements stack.

13F must remain delayed ownership context. Repository law already rejects it as a positive signal. It can identify concentration, potential resale context, or crowding; it cannot prove current accumulation.

### 3.9 Education and research

The Learn surface is not decoration. It is a conversion and retention engine organized from novice to advanced:

- a short core course on dilution and supply/demand;
- SEC filing cheat sheet;
- ATM, PIPE, shelf, warrant, S-1, equity-line, and convertible explainers;
- FAQs and definitions;
- original research on large squeezes and offering behavior;
- advanced lessons on price protection, variable converts, I.B.6, registered shares, and cashless warrant mechanics.

The best Mastermind translation is contextual education: “Why this matters” attached to the actual instrument, formula, source clause, and scenario. Do not copy their prose or charts. Rebuild the curriculum in Mastermind’s language from SEC primary material and our own research.

### 3.10 Product and UX strengths

- Excellent ticker-first compression.
- Strong dual workflow: search one name or scan events.
- Broad instrument taxonomy.
- Dense but practical field selection.
- Education mirrors the product’s actual concepts.
- Completed-offering and banker history create useful priors.
- Manual reconciliation handles exceptions that naive extraction misses.

### 3.11 Product and UX weaknesses

- Opaque overall and component scoring.
- Source lineage is present but not always the organizing principle.
- Manual adjustments are hard for a subscriber to reproduce.
- Potential-supply bars can be mistaken for forecast issuance.
- Current price as a share-conversion denominator creates unstable, circular-looking estimates.
- Float is an estimate whose holder and date assumptions need greater visibility.
- Daily/manual processing is slower and harder to scale than event-driven extraction.
- Dense tables and legacy visual hierarchy are less approachable than the newer competitor.
- A single “updated” stamp can hide different clocks for filing discovery, extraction, review, and quote.
- Corporate-action normalization can produce visually extreme historical values on serial reverse-split issuers; every transformed number needs an as-filed counterpart and invariant tests.

## 4. Competitor B — Dilutracker.com

### 4.1 Product thesis

The newer product presents itself as an automated SEC-to-dilution-risk platform. Its public “How it works” page describes a five-step path from EDGAR monitoring through AI extraction, normalization/reconciliation, risk analysis, and a report. It packages the result as:

- a modern ticker report;
- a dilution screener;
- watchlists and alerts;
- a REST API;
- bulk export and webhooks at higher tiers;
- 13F and filing tools;
- institutional and data-licensing offers.

Source: https://www.dilutracker.com/how-it-works

The product’s design is more contemporary than DilutionTracker’s, but the public material does not establish that its historical reconciliation is deeper.

### 4.2 Observed information architecture

The public and user-supplied surfaces show:

- a dark left rail;
- ticker search;
- watchlist;
- popular names with risk labels;
- compact header with quote and market capitalization;
- generated summary;
- overall dilution-risk band;
- key-stat cards;
- active-instrument cards;
- chart explorer;
- report modules for holders, filings, and financials.

The user’s RUBI screenshot is a strong reference for density and scan order:

1. company and quote;
2. short explanation;
3. risk band;
4. O/S, float, runway, ownership;
5. instrument grid;
6. price chart.

This layout should inform, not dictate, Mastermind’s design. Its best idea is the concise “instrument inventory” grid. Its weakness is that a risk band can look definitive without showing the state transition and calculation receipts underneath.

### 4.3 Feature inventory

Public material advertises:

- ticker reports with narrative, O/S, float, runway, active instruments, holders, filings, and financials;
- risk bands for Overall, Offering Ability, Cash Need, and Float Risk;
- warrants, convertibles, ATM, ELOC / SEPA, shelves, S-1 pipeline, equity plans, options, and preferred shares;
- detection of variable conversion, floorless or death-spiral terms, full-ratchet protection, original issue discount, and cashless warrant features;
- screener filters for ticker/company, overall risk, offering ability, float, and runway;
- filing monitoring across 10-K/Q, 8-K, S-1/S-3, DEF 14A, 424B, 13F, and foreign-issuer forms;
- email alerts;
- watchlists;
- CSV and PDF export;
- API access, refresh, bulk exports, and webhooks depending on plan;
- a 13F tracker and SEC filing utilities.

Its public API describes full-report and modular resources for:

- report;
- summary;
- dilution;
- float;
- runway;
- quote;
- filings;
- holders;
- financials;
- refresh.

Source: https://www.dilutracker.com/dilution-tracker-api

The API is a strategically important clue. It suggests a report composed from normalized modules rather than a monolithic page. Mastermind should do the same, but the UI, alerts, exports, and API must all read one canonical issuer ledger so their answers cannot drift.

### 4.4 Claimed analytical pipeline

The public five-step description can be translated as:

1. Watch EDGAR for relevant company documents.
2. Extract financing terms and risk factors.
3. Deduplicate and reconcile the terms into structured instruments.
4. compute risk components.
5. render the ticker report and derivative products.

The public score descriptions associate:

- Offering Ability with shelves, ATM, ELOC, and authorized capacity;
- Cash Need with cash runway, burn, and obligations;
- Float Risk with warrants, converts, resale supply, and related overhang;
- Overall Risk with a roll-up of those conditions.

Exact formulas, weights, label thresholds, extraction prompts, and reconciliation rules are not public. They should be treated as unknown.

### 4.5 Technology and code exposure assessment

Public client assets indicate a contemporary Next.js-style web application, PWA behavior, analytics instrumentation, and a modular report/API architecture. Public bundles can reveal:

- route names;
- component hierarchy;
- presentation strings;
- public request shapes;
- state and entitlement wiring.

They do not reveal:

- the normalized historical corpus;
- document extraction services;
- amendment and supersession logic;
- review workflow;
- score training or weights;
- correction history;
- private database;
- reliability under difficult issuer cases.

There is no exposed codebase that collapses the hard work into a few hours. Reusing served application code would also be a poor engineering choice: it would import another product’s coupling, branding, entitlement assumptions, and technical debt. The useful asset is the product map, not their JavaScript.

### 4.6 Commercial packaging

At the assessment date, the public site showed Starter, Pro, and Business tiers around $59, $119, and $299 per month, with annual discounts and progressively larger watchlist, alert, export, API, refresh, history, and webhook allowances. API redistribution is separately licensed.

The clearer packaging is worth borrowing conceptually:

- individual research tier;
- active trader tier;
- developer / business tier;
- institutional redistribution contract.

Mastermind should not design entitlements until the data product is stable, but it should version the API and lineage from day one so a future data tier is possible.

### 4.7 Product and UX strengths

- Modern, lower-friction visual hierarchy.
- Immediate summary and instrument inventory.
- Strong public product demonstration.
- Useful self-serve screener.
- Clear modular API story.
- Commercial packaging maps to actual limits.
- Automation is positioned as scalable.

### 4.8 Product and UX weaknesses

- Public claims mix “real-time monitoring” with processing within roughly a day; those are different service levels.
- AI extraction is not itself evidence of correct reconciliation.
- Risk bands remain opaque.
- A polished summary can mask missing or stale source state.
- Coverage claims vary across public pages.
- Paywall-first product design limits proof for prospective users.
- Public pages do not foreground correction history, source-span evidence, or calculation version.
- A modern shell is easy for competitors to reproduce.

## 5. Side-by-side verdict

| Dimension | DilutionTracker.com | Dilutracker.com | Mastermind target |
|---|---|---|---|
| Core advantage | Curated historical issuer state | Modern automation and distribution | Evidence-grade temporal ledger plus automation |
| Data source | SEC filings and official PRs | SEC EDGAR and related public material | SEC-first, issuer PR second, market/corporate-action context |
| Extraction | Human-heavy, manually adjusted | AI-forward, details undisclosed | Deterministic first, model-assisted with cited spans, reviewed by exception |
| Reconciliation | Appears strong and cumulative | Claimed normalization/deduplication | Explicit event and instrument state machines |
| Risk model | Four components plus overall, weights opaque | Four components plus overall, weights opaque | Separate measurable lanes; probability only after calibration |
| Ticker UX | Dense and mature | Cleaner and more contemporary | Three-question glance tier plus evidence drilldown |
| Discovery | Strong event feeds | Strong screener | Both, built from state transitions |
| Alerts | Broad form and PR taxonomy | Simpler plan-gated alerts | Semantic state changes, not form spam |
| Education | Excellent course and research | Marketing explainers | Embedded Learn system tied to live evidence |
| API | Institutional / less public | First-class public API | Same canonical versioned ledger as UI |
| Trust surface | Manual-team reputation | Automation claim | Receipts, confidence, corrections, freshness clocks |
| Defensibility | Corpus and analyst workflow | Distribution and packaging | Corpus, temporal graph, outcome ledger, Prophet integration |

The best synthesis is clear: take Competitor A’s ontology, historical discipline, feeds, and curriculum; take Competitor B’s shell, screener, API modularity, and packaging; add Mastermind’s point-in-time governance, scenario analysis, cross-engine context, and forward validation.

## 6. Data acquisition: how Mastermind can reproduce the category

### 6.1 Primary public sources

#### SEC EDGAR discovery and metadata

Use:

- submissions JSON for issuer filing history;
- daily and quarterly index files for exhaustive form discovery;
- filing index and primary HTML documents;
- XBRL companyfacts and filing facts;
- structured datasets where available;
- accession, acceptance timestamp, filing date, form, CIK, and document hash as immutable identity.

The SEC documents that submissions data is generally updated in under a second and XBRL APIs in under a minute, while bulk submissions and companyfacts archives are republished nightly.

Source: https://www.sec.gov/search-filings/edgar-application-programming-interfaces

Respect the SEC’s fair-access guidance, identify the client, cache documents, and stay at or below its published request ceiling.

Source: https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits

#### Filing text and exhibits

Parse:

- primary registration and prospectus documents;
- exhibit 10 financing agreements;
- exhibit 99 press releases;
- incorporated-by-reference documents;
- fee tables and cover pages;
- XBRL facts and inline XBRL;
- later financial-statement footnotes that disclose actual usage.

#### Issuer press releases

Use official IR releases or SEC-filed exhibits as the preferred PR source. Third-party syndication can help discovery but must not be the canonical evidence when an issuer or SEC version exists.

#### Market and corporate-action data

Reuse repository quote, OHLCV, split, market-cap, and issuer mapping infrastructure. Required inputs include:

- current and historical price;
- 60-calendar-day close window where applicable;
- split and reverse-split factors;
- pre-offering close;
- offer-date and aftermarket returns;
- volume and liquidity;
- exchange and listing status.

Market-data redistribution rights are separate from the public SEC data.

#### Ownership

Use:

- proxy and annual-report ownership tables;
- Forms 3, 4, and 5 for insiders;
- Schedules 13D and 13G for large holders;
- 13F only as delayed institutional context.

Official structured-filing specifications are available for ownership forms and other XML submissions.

Source: https://www.sec.gov/submit-filings/technical-specifications

#### Issuer authorization and listing constraints

Authorized common/preferred share limits and shareholder approvals can appear in:

- charter amendments;
- proxy and information statements;
- 8-K / 6-K vote results;
- 10-Q / 10-K cover and equity notes;
- exchange notices and issuer announcements.

Relevant 8-K items include material agreements, new obligations, trigger or acceleration events, unregistered equity sales, charter amendments, and votes.

Source: https://www.sec.gov/files/form8-k.pdf

### 6.2 Filing and event coverage matrix

| Form / source | Capital-structure purpose | Typical state transition |
|---|---|---|
| S-1 / F-1 and amendments | New registered issuance or resale | proposed → amended → effective / withdrawn |
| S-3 / F-3 / F-10 and amendments | Shelf registration | filed → eligible review → effective → available / expired |
| S-3ASR | Automatic shelf for eligible issuer | filed/effective → available |
| EFFECT | Registration effectiveness | pending → effective |
| 424B1–B5 | Terms, pricing, takedown, resale prospectus | available → priced / updated / resale registered |
| POS AM / post-effective amendments | Change or maintain registration | amended / superseded |
| RW / AW | Withdrawal | pending or effective object → withdrawn |
| 8-K / 6-K | Financing agreement, pricing, closing, use, default, vote, split | semantic state transition |
| 10-Q / 10-K / 20-F / 40-F | O/S, cash, burn, debt, actual proceeds/use, going concern | reconcile ledger to reported state |
| DEF 14A / PRE 14A / 14C | authorization, issuance approval, split vote, incentive plans | proposed → approved / rejected |
| Reg A filings | Alternative offering path | qualified / active / completed |
| Forms 3/4/5 | Insider ownership and transactions | holder-state update |
| 13D/G | Large-holder and affiliate context | holder-state update |
| 13F | Delayed institutional context | contextual holder snapshot |
| Official PR / exhibit 99 | announcement, pricing, closing, termination | discover and explain transition |

The engine must route by both form and content. A 424B5 can represent a plain shelf takedown, an ATM update, a complex structured deal, or another prospectus event. The existing Special Situations classifier already refuses to guess ambiguous 424B5 filings without text; Capital Structure must preserve that standard.

## 7. What exists in Macro Dashboard already

This program is an expansion of a live precursor.

### 7.1 Existing dilution event collector

collectors/edgar_dilution.py already:

- sweeps SEC daily-index files for S-3, S-3ASR, S-3/A, and 424B1–B5;
- emits append-only data/edgar/dilution_events.parquet;
- deduplicates by accession;
- stores filing date and first-seen timestamp;
- maps CIK to ticker where possible;
- runs on the nightly collection lane;
- explicitly declares itself display-only.

Evidence: collectors/edgar_dilution.py:1–22, 41–66, 143–229.

This is a discovery spine, not a capital-structure engine. It does not fetch or parse terms, link amendments, track effectiveness, reconstruct instruments, or reconcile usage.

### 7.2 Existing Neural Web projection

engine/neuralweb/bottom_sensors.py reduces the collector to:

- days_since_shelf;
- days_since_takedown;
- dilution_events_365d.

Missing data degrades to null, never zero.

Evidence: engine/neuralweb/bottom_sensors.py:202–288 and 996–1003.

engine/neuralweb/mastermind_context.py passes the same sparse dilution block into candidate context. Every authority boolean remains false.

Evidence: engine/neuralweb/mastermind_context.py:1–14, 2192–2197, 2500–2513.

config/synapse.yml registers this as projection-only display context and documents the three fields.

Evidence: config/synapse.yml:8262–8301.

### 7.3 Adjacent reusable systems

- engine/special_situations.py provides a precedent for a display-only SEC event desk and refuses ambiguous 424B5 classification without document text.
- engine/capital_allocation.py and engine/stock_fundamentals.py already calculate historical shares, repurchases, SBC, and capital-allocation context. They are not issuance ledgers.
- existing EDGAR collectors provide CIK mapping, XBRL, submissions, 8-K, 13F, beneficial ownership, and other form-specific machinery.
- the current ticker builder and stockdata payload provide the natural per-name distribution surface.
- the shared navigation inventory owns product entry points.
- the Neural Web → Mastermind bridge already supports a compact context artifact.

### 7.4 Adjacent company-intelligence architecture

The in-progress Jodie / Struct research proposes—but has not yet landed as a repository contract—a shared Macro truth plane with:

- immutable raw source documents;
- company_event.v1;
- company_fact_delta.v1;
- a company evidence graph;
- compact downstream context.

Capital Structure should become the first rigorous financing family under that umbrella. Wave 0 must either land company_event.v1 as a versioned contract with a registered Synapse artifact owner or use capital_structure.event.v1 as an explicit adapter pending that decision. It must not create a second document store, entity resolver, or generic company-event graph.

### 7.5 Collision and sequencing constraints

At the audit snapshot, the Active Build Map showed an open Ticker workbench depth PR touching the per-ticker surface. Do not begin the ticker-panel UI wave until that lane merges or file ownership is coordinated. The research docket itself has no file collision.

Any runtime build must first:

1. refresh docs/ACTIVE_BUILD_MAP.md;
2. re-read research/DO_NOT_REBUILD.md;
3. register raw and derived artifact ownership in config/synapse.yml;
4. amend docs/SIGNAL_BUS.md before adding consumers;
5. define one writer per artifact;
6. preserve existing three-field dilution context during migration.

## 8. Already covered and explicitly excluded

### 8.1 Already covered — do not rebuild

- Generic SEC download, pacing, user-agent, retry, and CIK mapping utilities.
- Thin shelf / prospectus event discovery.
- XBRL statements and fundamental panels.
- Existing quote, split, price-history, and market-cap plumbing.
- Existing filings, financials, ticker dossier, and shared navigation foundations.
- Existing 13F, insider, and beneficial-ownership collectors.
- Existing Special Situations desk mechanics.
- Existing Neural Web context compiler and authority envelope.
- Existing capital-allocation analytics.
- The proposed, not-yet-landed company_event.v1 and company_fact_delta.v1 umbrella; Wave 0 must resolve its contract status before implementation.

### 8.2 Excluded from this program

- Copying competitor source code, proprietary copy, brand assets, hidden records, prompts, or score weights.
- Defeating subscriptions or ingesting data obtained by access-control bypass.
- Rebuilding a generic financial-statement terminal.
- Treating shelf registration as actual issuance.
- Treating registered resale shares as newly issued shares.
- Treating 13F as current ownership or positive alpha.
- A fused 0–100 “dilution score” at launch.
- Automatic trade execution, position sizing, short recommendations, or user-book construction.
- Non-US primary coverage in v1, except foreign private issuers that file the relevant SEC forms and can be normalized safely.
- Marketing automation, public claims, and institutional licensing implementation in the first engine waves.
- Prophet rank, size, or entry authority before separate promotion evidence.

## 9. Target system — Capital Structure Intelligence

### 9.1 Three questions at the glance tier

Every ticker report should answer, in this order:

1. Ability — can the issuer issue or sell securities now?
2. Need — how urgently does the issuer appear to need capital?
3. Supply — what instruments or registered resale blocks can create pressure, under what conditions?

The fourth question belongs one click deeper:

4. Activation — what filing, vote, price, maturity, covenant, or runway threshold changes the state?

This is more useful than a single severity label.

### 9.2 Source-to-product architecture

    SEC indexes / submissions / filing documents / XBRL / issuer PR / market data
                                      |
                                      v
                         immutable source manifest
                                      |
                                      v
        company_event.v1 or capital_structure.event.v1 adapter
                                      |
                         +------------+-------------+
                         |                          |
                         v                          v
              instrument lifecycle ledger   company fact deltas
                         |                          |
                         +------------+-------------+
                                      v
                     capital_structure.context.v1
                       issuer state + calculations
                                      |
                 +--------------------+--------------------+
                 |                    |                    |
                 v                    v                    v
        public dashboard       ticker dossier      Neural Web projection
                 |                                         |
                 v                                         v
        alerts / API / Learn                   Mastermind compact context
                                                             |
                                                             v
                                      future validated de-escalation overlay

Macro Dashboard owns the truth plane. Mastermind consumes a bounded point-in-time projection. No collector should be duplicated in the Mastermind service. The public dossier and API read the canonical capital-structure plane directly; Bottom Sensors remains only a narrow compatibility leaf for current consumers.

### 9.3 Core contracts

#### Source manifest

Raw filings belong in content-addressed object / R2 storage, not git. Commit thin manifests and derived artifacts only. Every source record requires:

- accession or canonical source-system ID;
- canonical URL;
- retrieval timestamp;
- SHA-256 content hash;
- document version and media type;
- stable span locator, such as page/table coordinates or a DOM selector plus text hash;
- storage object key;
- rights / redistribution classification;
- parser eligibility and corruption state.

#### company_event.v1 financing family or capital_structure.event.v1 adapter

Required fields:

- event_id;
- source_system and source_id;
- accession, CIK, ticker, issuer identity, and aliases;
- form, filing date, acceptance timestamp, first-seen timestamp;
- primary document URL, exhibit URLs, content hashes;
- event family and subtype;
- amendment_of, supersedes, superseded_by;
- effective, withdrawn, priced, closed, expired, or unknown state;
- affected instrument candidate IDs;
- extraction candidates with stable source locators;
- parser version, extraction method, and review status;
- reconciliation state and contradictions;
- correction version;
- point-in-time availability.

Events are immutable filing and event observations. They do not own the authoritative normalized instrument term. Corrections create a new version and supersession edge; they do not erase what the system knew at the time.

#### capital_structure.instrument_term_observation.v1

This is the one authoritative home for normalized financing terms. Required fields:

- observation_id, issuer_id, instrument_id, and event_id;
- term name, normalized value, unit, currency, and scale;
- as-filed value;
- effective_from and observed_at;
- source-manifest ID and stable span locator;
- extraction method, parser version, confidence, and review state;
- amends, supersedes, and contradiction links;
- correction version and point-in-time availability.

No normalized term may be edited inside an event or issuer context. A correction creates a superseding observation.

#### capital_structure.instrument.v1

Required fields:

- instrument_id and issuer_id;
- security_class_id and source_security_id;
- share_class;
- family: shelf, ATM, follow-on, RDO, PIPE, ELOC, SEPA, warrant, option, RSU, convertible note, convertible preferred, resale registration, rights offering, Reg A, or other;
- supply_role: issued_outstanding, registered_primary_capacity, registered_resale, authorized_unissued, contractual_exercise, contingent_conversion, incentive_equity, or other;
- dedupe_group;
- included_in_reported_os;
- issuer_proceeds_flag;
- status and status history;
- authorization, registration, effectiveness, pricing, issuance, closing, resale, and expiry dates where relevant;
- original and remaining dollars, units, and share equivalents;
- currency and unit scale;
- fixed price, formula, floor, cap, reset, ratchet, discount, OID, and interest terms;
- cashless and alternate-cashless mechanics;
- exercise, conversion, maturity, and termination terms;
- registration and shareholder-approval dependencies;
- holder, buyer, banker, placement agent, and counterparty IDs;
- source events and exact evidence spans;
- authoritative instrument-term observation IDs;
- derived values, assumptions, calculation version, valuation_as_of, and timestamp;
- confidence and review state.

Every issuer aggregate must declare the non-overlapping supply roles and dedupe groups it includes. This is the primary defense against counting the same security as O/S, registered resale supply, and potential exercise supply at once.

#### capital_structure.context.v1

Required issuer-level blocks:

- reported_shares;
- estimated_float;
- authorized_headroom;
- registered_resale_supply;
- incentive_equity_supply;
- active_primary_financing_capacity;
- active_instrument_overhang;
- near_price_overhang;
- cash_resources;
- normalized_cash_use;
- runway;
- debt and convertible maturity calendar;
- shelf / I.B.6 state;
- pending and live offerings;
- historical offering behavior;
- banker / buyer history;
- corporate-action state;
- coverage, freshness, contradictions, and calculation receipts.

The materialized context is keyed by issuer_id, as_of, and calculation_version. It is rebuildable, references all source event and term-observation IDs, and may contain no independently editable facts.

#### capital_structure.projection.v1

The compact Neural Web / Mastermind projection should include only:

- ability_state;
- need_state;
- overhang_state;
- activation_state;
- confirmed live financing flag;
- runway band and as-of date;
- nearest material maturity;
- near-price warrant / convert overhang;
- latest material event and age;
- uncertainty and stale flags;
- source artifact IDs.

It must preserve:

- is_context_only = true;
- all authority booleans false;
- null for unknown;
- source and freshness lineage.

#### capital_structure.forward_ledger.v1

Required before any financing-probability claim:

- issuer and observation timestamp;
- frozen eligible universe;
- frozen feature snapshot;
- model and threshold version;
- 7 / 30 / 90-day probability outputs;
- predicted event definition;
- realized first qualifying event;
- censoring, delisting, and corporate-action status;
- calibration bucket;
- no-edit hash;
- evaluation timestamp.

One nightly writer advances this ledger. The idempotency key is issuer_id, observation_ts, feature_version, and calculation_version. Keep-first semantics apply; corrections are superseding records, and no render or rebuild path may rewrite historical forecasts.

### 9.4 State machines

#### Registration and offering

    draft/disclosed
      → filed
      → amended
      → effective
      → available
      → launched
      → priced
      → closed
      → partially used / fully used
      → expired / withdrawn / terminated

Not every path uses every state. The engine must distinguish a primary issuance registration from a resale registration.

#### ATM

    agreement disclosed
      → prospectus effective
      → active
      → sales disclosed
      → remaining capacity revised
      → exhausted / terminated / expired

#### Warrant

    issued
      → exercisable
      → amended / reset
      → exercised partly
      → cashless or alternate-cashless event
      → expired / redeemed / fully exercised

#### Convertible

    issued
      → accrues
      → conversion terms amended or reset
      → partially converted
      → repaid / exchanged / matured / defaulted

#### Reverse split

    proposed
      → shareholder authorization
      → board ratio selected
      → effective
      → every historical share and price field normalized

The ledger must retain both as-filed and split-adjusted values. Never overwrite the original disclosure.

## 10. Analytical engines

### 10.1 Reported O/S and share reconciliation

Build an O/S observation series from:

- filing cover pages;
- balance-sheet equity notes;
- prospectus capitalization;
- 8-K / 6-K disclosures;
- proxy ownership tables;
- transfer-agent or issuer disclosures when available;
- split events.

Each observation carries:

- as-of date;
- filing date;
- first-seen date;
- as-filed value;
- split-adjusted value;
- source span;
- confidence;
- whether it includes a recent disclosed transaction.

When two sources disagree, preserve both and publish the reconciliation reason. Unknown is not zero.

### 10.2 Float engine

Do not publish one unqualified float number. Publish:

- reported O/S;
- estimated affiliate-restricted shares;
- estimated strategic / control holdings;
- registered resale shares;
- other restricted shares where disclosed;
- estimated tradeable float;
- definition version and holder snapshot date.

Proposed equation:

    estimated tradeable float
      = latest reconciled O/S
      - shares classified as affiliate or control holdings
      - other non-tradeable restricted shares
      + confirmed non-affiliate, unrestricted newly issued shares
        where legal tradability is established

Every subtraction and addition must be inspectable and date-stamped. Registration for resale does not itself create new float, and 13F alone cannot define float.

### 10.3 Fully diluted and scenario supply engine

Publish multiple constructs instead of one misleading fully diluted count:

- reported O/S;
- issued but restricted supply;
- currently exercisable / convertible supply;
- near-price supply at spot;
- gross contractual share equivalent;
- stress share equivalent under reset / floor scenarios;
- possible future primary issuance capacity.

These categories must never be stacked as if all are equally probable or simultaneously issuable.

For each instrument, calculate scenario share equivalents at a named valuation_as_of market timestamp:

- current price;
- 10%, 25%, and 50% lower price where variable terms matter;
- contractual floor;
- next known reset;
- split-adjusted basis.

### 10.4 Shelf and offering-ability engine

Deterministic inputs:

- registration amount and security types;
- effective date and expiry;
- amount already sold;
- remaining capacity;
- eligible primary-versus-resale amount;
- I.B.6 applicability and current headroom;
- authorized-share headroom;
- exchange / shareholder-approval constraints;
- active ATM, ELOC, or purchase agreement;
- pending S-1 / F-1;
- withdrawal, suspension, or lapse.

Output named states:

- unavailable;
- registration pending;
- constrained;
- available;
- live;
- unknown.

Do not infer desire to issue from ability alone.

### 10.5 Cash, burn, and runway engine

Resources:

- cash and cash equivalents;
- marketable securities split by liquidity and restriction;
- restricted cash excluded unless usable;
- disclosed post-balance-sheet financing proceeds;
- debt repayment and transaction costs;
- known milestone, trial, or capital commitments when reliably structured.

Cash use:

- trailing operating cash use;
- quarterly and annualized variants;
- optional adjusted cash use with every adjustment itemized;
- capex separated;
- financing cash flows excluded from burn;
- positive cash generation represented as “not burning” rather than infinite runway.

Outputs:

- raw runway;
- adjusted runway;
- runway range;
- next balance-sheet report date;
- nearest material maturity;
- assumptions and stale state.

### 10.6 Instrument clause engine

Deterministic parsers should handle:

- fixed exercise and conversion prices;
- maturity and expiry;
- quantity and principal;
- standard discounts;
- floor and cap;
- reset formula;
- full-ratchet and weighted-average anti-dilution;
- original issue discount;
- interest and make-whole;
- cashless exercise;
- alternate cashless multipliers;
- forced exercise / redemption;
- beneficial-ownership blockers;
- exchange-cap and shareholder-approval dependencies;
- registration-rights deadlines and penalties.

A model-assisted extractor may propose fields only when it returns:

- the exact source span;
- document and accession;
- normalized value and unit;
- confidence;
- ambiguity reason;
- parser version.

Code validates arithmetic and cross-field invariants. Low-confidence or contradictory records enter review. An LLM never invents a missing term and never originates a trade signal.

### 10.7 Offering history and outcome engine

For every priced transaction:

- issuer;
- financing type;
- pricing timestamp;
- offer price;
- prior close and relevant VWAP;
- gross and estimated net proceeds;
- shares and share equivalents;
- warrant coverage and terms;
- discount;
- deal size / market cap and deal size / float;
- bank, syndicate, buyers where disclosed;
- one-day, five-day, twenty-day, and sixty-day split-adjusted returns;
- volume and liquidity context;
- market / sector residual outcome;
- subsequent financing;
- post-financing runway extension.

This creates two useful products:

1. descriptive league tables for banks, buyers, structures, and issuer behavior;
2. the labeled outcome corpus required for later prediction.

Never import a competitor’s subjective “bank tier.” Estimate conditional distributions from Mastermind’s own point-in-time data, with sample counts and regime splits.

### 10.8 Reverse-split likelihood

At launch, publish a deterministic risk checklist:

- listing-price deficiency;
- bid-price notice;
- shareholder authorization;
- remaining board authority;
- recent split history;
- authorized-share ratio after a proposed split;
- price and compliance deadline.

Do not publish a probability until a point-in-time cohort study exists. A confirmed vote and board authorization are facts; “likely split” is a forecast.

### 10.9 Financing probability — later research species

The proposed 7 / 30 / 90-day outcome should mean:

> Probability that the issuer announces or prices a qualifying primary financing event within the horizon, conditional on information first available at the observation timestamp.

Candidate feature families:

- ability: active shelf, I.B.6 headroom, ATM/ELOC, pending registration, authorized headroom;
- need: runway, cash use, debt / trial / commitment calendar, going-concern language;
- activation: recent EFFECT, amendments, banker engagement, shareholder approval, price spike, liquidity;
- behavior: issuer financing cadence, structure, prior discounts;
- supply: active convert / warrant / resale state;
- market: realized volatility, volume expansion, price relative to registration assumptions;
- issuer class: industry, market cap, exchange, foreign filer, development stage.

Hard rules:

- freeze features point in time;
- prevent filing leakage;
- split issuer groups, not rows, across train and test where appropriate;
- evaluate calibration, not only rank;
- report horizon-specific base rates;
- keep market regimes and issuer size visible;
- no retroactive editing of forecasts;
- null model and simple logistic baseline first;
- no model output enters Prophet during shadow.

Required metrics:

- Brier score;
- calibration intercept and slope;
- reliability diagram;
- precision / recall at pre-registered thresholds;
- PR-AUC against the horizon base rate;
- false-negative review for financings;
- decision utility under a fixed de-escalation cost;
- stability by market cap, industry, form eligibility, and regime.

## 11. Risk presentation: beat both products without a fake dial

### 11.1 Launch lanes

Show four independent lanes:

| Lane | Question | Examples of printed inputs |
|---|---|---|
| Ability | Can securities be issued or sold now? | effective capacity, pending registration, I.B.6, approvals |
| Need | How tight is the funding clock? | runway range, burn, maturity, going-concern disclosure |
| Overhang | What supply can become tradeable? | near-price warrants, variable converts, resale blocks, equity plans |
| Activation | What changed or can activate next? | EFFECT, pricing, vote, reset, maturity, price threshold |

Add Historical Behavior as a separate record, not a blended score.

### 11.2 Named posture

A top-level narrative may summarize the combination:

- Capacity available, need low.
- Capacity constrained, need urgent.
- Live financing, supply terms known.
- High contractual overhang, no immediate funding need.
- Evidence incomplete.

The narrative must cite the fields that produced it. It is a deterministic rendering of lanes, not a hidden weighted score.

### 11.3 When a composite might be allowed

A composite severity or probability is optional and later. It may ship only if:

- its construct is explicitly defined;
- inputs and weights are versioned;
- a forward ledger exists;
- calibration gates pass;
- it improves a named decision over the component lanes;
- the UI still exposes the lanes and receipts.

Until then, the product is better without it.

## 12. Front-facing product specification

### 12.0 Design ruling — reproduce the intelligence, not the mess

DilutionTracker’s accumulated intelligence is valuable, but its member product reflects an older generation of SaaS information architecture: related work is split across many routes, tables repeat concepts in different shapes, instrument history is separated from the filing chain that changed it, and a user often has to mentally join risk, cash, supply, offerings, and education.

Mastermind should not preserve that fragmentation for the sake of feature parity. AI lowers the cost of building the interface, but its more important advantage is semantic composition: one canonical issuer state can be rendered differently for discovery, rapid decision context, deep research, alerts, and conversation without creating five competing answers.

The design target is one beautiful command system with three user modes:

1. Scan — what changed across the universe, and what needs attention?
2. Understand — what is this issuer’s current capital structure, and why?
3. Monitor — what transition should wake me up?

Product laws:

- One issuer state, many views.
- One timeline joins filing, instrument, calculation, and correction.
- Progressive disclosure: plain-language posture first, terms second, source clause third.
- Delta before inventory: lead with what changed since the prior state.
- Cards summarize; tables compare; the evidence drawer proves.
- No duplicate “overall risk” widgets across routes.
- Search, screener, watchlist, ticker dossier, and Mastermind conversation share the same filters and field vocabulary.
- Desktop density should feel like a professional terminal; mobile should preserve the three-question glance tier without horizontal table dependence.
- Motion communicates state change, lineage, and scenario transitions; it is not decoration.
- The AI is a first-class navigation and explanation surface, not a chat bubble pasted onto the dashboard.

The benchmark is not “all competitor pages reproduced.” It is “every competitor workflow is reachable with fewer context switches and every conclusion is more inspectable.”

### 12.1 Product map

Capital Structure Intelligence should have three homes:

1. Capital Structure desk — discovery and screening.
2. Per-ticker Capital Structure dossier — deep issuer analysis.
3. Learn — tutorial and reference tied to live examples.

### 12.2 Capital Structure desk

Internal desk tab rail, rendered below the shared site navigation:

- Overview;
- New Events;
- Pending;
- Live Financings;
- Completed;
- Instruments;
- Reverse Splits;
- Screener;
- Learn.

The product entry itself must use the shared navlinks inventory. Do not create a second global header, and coordinate final placement with the active Ticker workbench lane.

Overview modules:

- What changed since last close;
- Newly effective registrations;
- Live or newly priced offerings;
- Runway tightening;
- Near-price warrant / convert clusters;
- unresolved high-impact parses;
- coverage and freshness health;
- watchlist changes.

Saved screener filters:

- ticker / company;
- exchange, country, industry, market cap;
- ability state;
- runway range;
- active instrument family;
- near-price overhang;
- variable or toxic clause;
- shelf / I.B.6 state;
- pending / effective / live / used / expired;
- authorized headroom;
- historical offering cadence;
- banker / buyer;
- reverse-split state;
- filing recency;
- confidence and review state.

The default sort should be material state change, not an opaque risk score.

### 12.3 Per-ticker dossier

#### Glance tier

- company, quote, market cap, filing freshness;
- one-sentence posture;
- Ability, Need, Overhang, Activation lanes;
- reported O/S, estimated float, liquid resources, runway range;
- “what changed” delta.

#### Evidence timeline

A vertical, filterable chain:

- registration filed;
- amendment;
- EFFECT;
- ATM / purchase agreement;
- pricing;
- closing;
- O/S observation;
- actual proceeds or usage;
- reset or amendment;
- expiry / termination.

Each item expands to:

- source link;
- exact clause;
- affected fields;
- previous value → new value;
- extraction and review status.

#### Supply waterfall

Display:

- reported O/S;
- restricted and registered resale blocks;
- exercisable / convertible supply at spot;
- near-price supply;
- incentive-plan supply;
- scenario supply under price declines;
- possible future primary capacity separately.

Use toggles for as-filed / split-adjusted and spot / stress scenarios. Never merge capacity into actual O/S.

#### Instrument ledger

Use the newer competitor’s clean card density, but each card must include:

- lifecycle state;
- most important terms;
- remaining quantity / dollars;
- next activation condition;
- latest source and age;
- confidence;
- open evidence drawer;
- complete history.

#### Funding clock

- liquid resources;
- raw and adjusted cash use;
- runway range;
- next financial report;
- maturity / commitment calendar;
- recent and pending proceeds;
- scenario after a proposed financing.

#### Financing history

- offering terms;
- discounts;
- warrant coverage;
- bank and buyer;
- market reaction and residual performance;
- runway extension;
- time to next financing.

#### Holders, filings, financials

Reuse existing product infrastructure. Add capital-structure semantic filters and links back to affected instruments.

### 12.4 Source drawer — the differentiator

Every derived number opens a compact receipt:

- value;
- formula;
- inputs;
- unit and currency;
- source document and span;
- filing / acceptance / first-seen timestamps;
- as-filed and adjusted value;
- parser and calculation version;
- confidence;
- contradictions;
- correction history.

This is the product’s trust moat.

### 12.5 Watchlists and alerts

Allow:

- all eligible names;
- preset universe;
- user watchlists;
- saved screen;
- single ticker.

Channels:

- in-app feed;
- email;
- push;
- webhook;
- SMS only if commercially justified.

Alert events:

- new relevant filing;
- EFFECT;
- offering launch, pricing, closing, or withdrawal;
- ATM / ELOC activation or use;
- material remaining-capacity change;
- warrant or convert reset;
- shareholder approval;
- reverse split;
- O/S change;
- runway-band change;
- new maturity inside threshold;
- corrected or contradicted record;
- later, probability threshold crossing.

Alerts must deduplicate document spam and group amendments into one evolving event.

At context stage, these are deterministic product-event or state notifications only. They are never trade alerts, rankings, sizing instructions, BUY/SELL messages, or WAIT labels. Probability-threshold alerts remain operator-only in shadow until separately promoted.

### 12.6 API and exports

Proposed resources:

- GET /capital-structure/v1/tickers/{ticker}
- GET /capital-structure/v1/tickers/{ticker}/events
- GET /capital-structure/v1/tickers/{ticker}/instruments
- GET /capital-structure/v1/tickers/{ticker}/scenarios
- GET /capital-structure/v1/screener
- GET /capital-structure/v1/events
- GET /capital-structure/v1/offerings
- GET /capital-structure/v1/coverage
- webhook state-change events

All responses include:

- schema version;
- as-of and generated timestamps;
- source IDs;
- freshness;
- confidence;
- entitlement and redistribution metadata where applicable.

Exports should be generated from the same canonical response objects, not from scraped UI tables.

The ledger API is read-only in v1. Watchlist state belongs in the existing Supabase-backed user-state plane. Any write API, auth/RLS change, or schema migration is a separately owned program, not an incidental endpoint in this engine.

### 12.7 Learn system

Build original modules:

1. Dilution versus authorization versus resale.
2. Reading O/S and float.
3. Shelf registrations and effectiveness.
4. S-1 / F-1 pipeline.
5. ATM.
6. Registered direct and underwritten offerings.
7. PIPE and resale registration.
8. ELOC / SEPA.
9. Warrants.
10. Convertible notes and preferred shares.
11. Variable price, reset, ratchet, OID, and floor mechanics.
12. Cashless and alternate-cashless exercise.
13. Cash burn and runway.
14. I.B.6.
15. Exchange caps and shareholder approval.
16. Reverse splits and corporate-action normalization.
17. Offering history, discounts, banks, and buyers.
18. How to read Mastermind’s evidence receipts and uncertainty.

Each module links to public SEC primary sources and a live, openly available example. Educational heuristics are visibly separated from measured facts.

## 13. Neural Web and Prophet integration

### 13.1 Lobe placement

Capital Structure is a fundamental / event-risk lobe. It is not:

- a Special Situations category;
- an ownership lobe;
- a new positive-alpha source;
- a standalone trading system.

Its initial horizon role is context. The rich lobe should replace the thin three-field projection only after compatibility tests, while preserving those fields for current consumers.

### 13.2 Context-first projection

Mastermind should be able to say:

- “An effective shelf and active ATM create issuance capacity.”
- “Runway is tightening, but the latest cash figure is one quarter old.”
- “Eight million warrants cluster near spot; the calculation uses the current split basis.”
- “The S-1 became effective today; no pricing is yet disclosed.”
- “A priced offering extended estimated runway; the overhang changed from uncertain to known.”

It should not say:

- “This will dilute next week” without a calibrated probability;
- “Avoid” or “buy” from an LLM judgment;
- “institutional accumulation confirms” from 13F;
- “zero overhang” when coverage is missing.

### 13.2A Mastermind-native data tools

Capital Structure must be a typed data source for Mastermind AI, not a page that the model scrapes. Add read-only tools over the canonical ledger:

- capital_structure.get_ticker(ticker, as_of): current or historical issuer posture, instruments, calculations, and receipts;
- capital_structure.get_events(ticker, since, family): semantic state-change timeline;
- capital_structure.get_instrument(instrument_id, as_of): complete term and amendment history;
- capital_structure.compare(tickers, fields, as_of): same-definition comparison across names;
- capital_structure.screen(filters, sort, as_of): universe discovery using the desk’s saved-filter vocabulary;
- capital_structure.explain(receipt_id): formula, inputs, source span, versions, and contradiction state;
- capital_structure.what_changed(ticker, from_as_of, to_as_of): field and lifecycle deltas;
- capital_structure.scenario(ticker, price, financing_assumption, as_of): deterministic, assumption-stamped supply and runway scenarios.

Tool responses are structured objects, not prewritten narrative. Every response carries:

- schema and calculation version;
- as_of, generated_at, and source first-seen clocks;
- authority and context-only envelope;
- coverage and stale state;
- source event, term-observation, and receipt IDs;
- as-filed versus adjusted values;
- assumptions and scenario labels;
- contradictions and review status.

Mastermind then composes answers under strict rules:

1. Lead with Ability, Need, Overhang, and Activation.
2. Cite accession-backed evidence for material facts.
3. Distinguish reported, derived, scenario, and inferred values in language.
4. Never silently substitute stale or lower-confidence data.
5. Ask the explain tool for receipts rather than rereading raw filings opportunistically.
6. Keep source facts separate from Prophet’s market signal.
7. Apply no rank, sizing, BUY/SELL, or WAIT behavior unless the consuming rule has explicit authority.

This lets a user ask:

- “Why did RUBI’s overhang change today?”
- “Compare the next financing window for these five biotech names.”
- “Which watchlist names have an effective shelf, under nine months of runway, and near-price warrants?”
- “Show the clause that makes this convert variable.”
- “What did Mastermind know before the offering?”
- “How would a 25% lower share price change the contractual share equivalent?”

The AI answer, dashboard card, alert, and Prophet context all resolve to the same IDs and calculation version. That shared semantic contract—not the presence of a chatbot—is what makes this a deeper product.

### 13.2B Prophet feature join

Prophet should never ingest dashboard prose or a competitor-style overall severity label. Its join consumes a small, point-in-time feature projection keyed by issuer and observation timestamp:

- confirmed primary-financing lifecycle state;
- capacity availability and constraints;
- need / runway band;
- near-price contractual supply;
- latest material transition and age;
- coverage, freshness, and contradiction flags;
- later, a separately versioned and calibrated financing probability.

The full document graph remains outside Prophet. Each feature retains a receipt ID so a signal explanation can open the underlying capital-structure evidence without bloating the scoring path.

### 13.3 Promotion ladder

#### Stage C0 — display and explanation

- facts, instrument states, calculations, and sources;
- deterministic product-event and state notifications are allowed;
- no rank, gate, size, trade alert, BUY/SELL, or WAIT escalation.

#### Stage C1 — de-escalation context

- named hazard states may lower a predeclared confidence key only when that key has explicit calibration and provenance;
- otherwise an LLM may describe facts and uncertainty but may not modify confidence;
- still cannot alter Prophet ranking or size;
- LLM may only explain or de-escalate, never originate.

#### Stage C2 — shadow overlay

- frozen rule or probability output attached to candidates;
- no user-facing behavioral change;
- forward ledger accrues.

#### Stage C3 — bounded shrink-only authority

After pre-registered validation and review:

- may lower edge grade;
- may reduce size ceiling;
- may turn an entry state into WAIT only when a separate review explicitly sets may_gate = true;
- cannot add candidates, increase size, or force a buy.

#### Stage C4 — deterministic live-event gate

A separately adjudicated rule may block an entry during a confirmed live offering or another objectively defined financing state. “Confirmed live offering” must mean an accession-backed, issuer-primary financing state with a predeclared activation, clear, and expiry condition. A shelf registration or generic 424B5 alone does not activate it. This is not the same as a model-predicted probability.

### 13.4 User-requested Prophet examples, adjudicated

| Proposed behavior | Launch ruling |
|---|---|
| Prophet Buy + elevated offering probability = WAIT — FINANCING RISK | Shadow first; only promoted after horizon calibration and decision-utility gate |
| Technical breakout + warrants clustered just above price = lower edge grade | Context initially; shrink-only candidate after near-price overhang study |
| Post-offering washout + extended cash runway = potential positive catalyst | Display as a scenario and research cohort; never assume positive edge |
| Biotech catalyst + fewer than nine months cash = dilution-adjusted expected value | Build as explanatory scenario; expected-value effect requires catalyst-specific validation |

The architecture supports all four. Governance decides when each earns authority.

## 14. Why Mastermind can be materially better

### 14.1 Evidence, not mystique

Competitors compress complexity into scores. Mastermind can make every conclusion reversible:

source → extracted term → instrument state → issuer calculation → displayed posture.

### 14.2 Time travel

A user should be able to ask:

- What did the system know before the spike?
- When did the shelf become effective?
- When did actual use become knowable?
- Which amendment changed the floor?
- Did a later filing correct O/S?

Point-in-time state turns the product from a reference page into research infrastructure.

### 14.3 Delta-first UI

“What changed?” is more valuable than another full report. Show:

- remaining ATM down by $12 million;
- floor reset from $1.50 to $0.85;
- 3.2 million shares newly registered for resale;
- runway extended from four to eleven months;
- EFFECT received;
- shareholder approval removed the exchange cap.

### 14.4 Scenario engine

Most competitor numbers are single-point estimates. Mastermind can show supply under:

- spot;
- lower prices;
- contractual floor;
- cashless exercise;
- reverse split;
- financing proceeds and burn repair.

### 14.5 Honest uncertainty

Every state displays:

- confirmed;
- derived;
- proposed by extractor;
- contradicted;
- stale;
- awaiting filing;
- not covered.

This turns missing data into visible system state instead of false precision.

### 14.6 Cross-product intelligence

The lobe can later interact with:

- Prophet;
- catalyst and earnings calendars;
- options and borrow context;
- price / volume regime;
- Special Situations;
- long-hold thesis and solvency context;
- watchlist and portfolio review;
- Mastermind explanations.

The truth plane remains singular; downstream products receive projections.

### 14.7 Self-improving correction loop

When a record is corrected:

- preserve the old version;
- record why;
- update the issuer ledger;
- retract or amend dependent alerts;
- grade the extractor;
- add the case to the golden corpus.

That creates a compounding moat from public data.

## 15. Feasibility by feature

| Feature | Primary inputs | Existing overlap | Difficulty | Wave |
|---|---|---:|---:|---:|
| Relevant filing feed | SEC indexes/submissions | High | Low | 1 |
| Source document cache | EDGAR HTML/exhibits | Medium | Low–medium | 1 |
| Form classification | form metadata + text | Medium | Medium | 1 |
| Filing timeline | canonical events | Medium | Medium | 1 |
| Shelf state / expiry | S-3/F-3/EFFECT/424B | Low | Medium | 2 |
| Pending S-1 feed | S-1 amendments/EFFECT | Low | Medium | 2 |
| Completed offering terms | 424B/8-K/PR | Medium | Medium–high | 2 |
| ATM state and usage | prospectus + later disclosures | Low | High | 2–3 |
| Warrants | exhibits/notes/prospectuses | Low | High | 3 |
| Converts / preferred | agreements/notes/prospectuses | Low | Very high | 3 |
| ELOC / SEPA / PIPE | agreements/registration chain | Low | High | 3 |
| O/S history | XBRL/cover/prospectus | Medium–high | Medium | 2 |
| Estimated float | ownership + O/S | Medium | High | 3 |
| Authorized headroom | charter/proxy/8-K | Low | High | 3 |
| I.B.6 | S-3 state + float/price/sales | Low | High | 3 |
| Cash and burn | XBRL + notes | High | Medium | 2 |
| Adjusted runway | post-quarter events/commitments | Medium | High | 3 |
| Reverse-split tracker | proxy/8-K/PR/splits | Medium | Medium | 2 |
| Corporate-action normalization | splits + instrument terms | Medium | High | 2–3 |
| Banker/buyer history | offering documents | Low | Medium | 3 |
| Outcome league tables | terms + market data | Medium | Medium | 4 |
| Ticker dossier | stockdata/ticker UI | High | Medium | 4 |
| Discovery desk / screener | normalized universe | Medium | Medium | 4 |
| Alerts/watchlists | event changes + user state | Medium | Medium | 5 |
| Learn center | original content + live examples | Low | Medium | 4–5 |
| API / exports / webhooks | canonical schemas | Medium | Medium | 5 |
| 7/30/90-day probability | forward corpus | Low initially | Very high | 6 |
| Prophet shrink gate | calibrated output + authority review | Existing bridge | High governance | 7 |

## 16. Build program

### Wave 0 — contracts, ownership, and golden corpus

Goal: make incorrect architecture impossible.

Deliver:

- final instrument and event taxonomy;
- decision and versioned contract for company_event.v1 versus the explicit capital_structure.event.v1 adapter;
- instrument, issuer-context, projection, and forward-ledger schemas;
- source-rights and retention matrix;
- Signal Bus and synapse ownership registrations;
- one-writer rules;
- migration plan for data/edgar/dilution_events.parquet;
- explicit coverage policy;
- 200-event golden corpus across issuer types, forms, amendments, and corporate actions;
- source-span annotation tool or review format;
- baseline data-quality scoreboard.

For every registered artifact, Wave 0 must declare a concrete path, producer, owner program, storage, cadence, freshness SLA, schema, consumers, and external consumers. It must regenerate Signal Bus documentation and pass the repository’s registry contract and undeclared-reader gates.

Pipeline placement is also a Wave 0 decision, not an implementation afterthought:

- SEC downloading remains nightly-only.
- Run the capital-structure compiler after collection and before scripts.build_site so current-night ticker dossier blocks are present in stockdata.
- Run the legacy compatibility projector before Bottom Sensors and Mastermind Context.
- Render workflows consume committed or R2 artifacts and return null/stale when absent; they never fetch SEC data.
- Keep data/edgar/dilution_events.parquet semantics through an adapter until both Bottom Sensors and engine/falsifier_tripwires.py have migrated.

Exit gates:

- no schema duplicates the company-intelligence truth plane;
- all current consumers, including the falsifier tripwire’s 90-day edgar_dilution series, continue receiving their existing semantics;
- every golden record has a primary source and expected state transition;
- unknown and contradiction semantics are fixed.

Estimated effort: 2–4 engineering days plus corpus annotation.

### Wave 1 — event spine and source evidence

Goal: exhaustive, point-in-time discovery and source storage.

Deliver:

- broaden form coverage;
- fetch primary documents and relevant exhibits;
- immutable manifest and hashes;
- amendment / supersession graph;
- EFFECT and withdrawal linkage;
- deterministic form router;
- semantic event classifier with defer state;
- event feed and internal review queue;
- freshness / coverage telemetry.

Exit gates:

- accession completeness against SEC index sample;
- duplicate rate within gate;
- acceptance and first-seen timestamps preserved;
- amendments never delete history;
- ambiguous documents remain deferred, not guessed.

Estimated effort: 4–7 engineering days.

### Wave 2 — core issuer state

Goal: useful product before exotic instruments.

Deliver:

- reported O/S observation series;
- split normalization;
- shelf, pending registration, EFFECT, pricing, closing, and completed-offering states;
- cash, normalized burn, and raw runway;
- reverse-split lifecycle;
- initial I.B.6 calculator;
- per-ticker evidence timeline;
- compatibility projection to current bottom sensors.

Exit gates:

- O/S and split invariants;
- authorization never counted as issuance;
- primary versus resale registration classified;
- cash and burn source periods visible;
- no finite runway from positive cash generation;
- internally frozen legal-test fixtures pass against the current Form S-3 instructions, with counsel-validated interpretation where required.

Estimated effort: 7–12 engineering days.

### Wave 3 — complete instrument engine

Goal: parity on capital-structure depth.

Deliver:

- ATM;
- warrants;
- convertible notes and preferred;
- PIPE and resale chain;
- ELOC / SEPA;
- equity plans, options, and RSUs;
- authorized-share headroom;
- price protection, reset, floor, ratchet, OID, and cashless clauses;
- remaining-capacity reconciliation;
- holder, buyer, and banker graph;
- scenario share equivalents;
- adjusted runway with post-balance-sheet events.

Exit gates:

- field-level precision and recall by instrument;
- arithmetic and unit reconciliation;
- source-span coverage;
- remaining never exceeds original without amendment;
- split transformation preserves economic equivalence;
- contradictions visible;
- review queue bounded and measurable.

Estimated effort: 10–20 engineering days plus backfill.

### Wave 4 — public product

Goal: a better subscriber surface than both competitors.

Deliver:

- Capital Structure desk;
- event feeds and saved screener;
- per-ticker dossier;
- evidence timeline;
- supply waterfall and scenario explorer;
- instrument cards;
- funding clock;
- offering history and outcomes;
- source drawer;
- original Learn modules;
- typed Mastermind read tools and an issuer-question eval set;
- responsive EN/ZH shell;
- open-access sample policy.

Sequencing:

- coordinate with the active Ticker workbench lane;
- reuse shared navigation and current stockdata;
- avoid duplicating filings and financials.

Exit gates:

- source receipt from every derived number;
- light/dark/mobile crops;
- keyboard and screen-reader flow;
- no color-only meaning;
- no hidden internal slugs on glance tier;
- missing and stale states tested;
- dashboard and ticker answers match the canonical API object.
- Mastermind answers resolve to the same receipt IDs and never silently cross as-of versions.

Estimated effort: 7–12 engineering days after Wave 2, partly parallel with Wave 3.

### Wave 5 — alerts, API, and commercial surface

Goal: turn analysis into workflow and distribution.

Deliver:

- watchlists and saved screens;
- semantic state-change alerts;
- email / in-app / webhook delivery;
- dedupe and amendment grouping;
- versioned API;
- production Mastermind tool registration, quotas, and read-path telemetry;
- CSV/PDF export;
- API keys, quotas, and audit logs;
- correction / retraction delivery;
- coverage status endpoint.

Exit gates:

- no duplicate alert storms;
- replay-safe idempotency;
- correction propagates to every derivative;
- API and UI snapshot hashes agree;
- AI tool, API, and UI material fields agree for the same as_of and calculation_version;
- entitlement failures do not leak records.

Estimated effort: 6–10 engineering days.

### Wave 6 — financing probability research

Goal: earn—not assert—the 7 / 30 / 90-day forecasts.

Deliver:

- retrospective point-in-time backfill with leakage audit;
- frozen baseline model;
- forward shadow ledger;
- calibration and reliability reporting;
- outcome slices and model card;
- live shadow UI visible only to operators;
- scheduled review date.

Exit gates:

- pre-registered thresholds;
- calibration beats base-rate baseline;
- useful precision at the proposed intervention threshold;
- stable direction across issuer-size and regime slices;
- no hidden retrospective relabeling;
- adequate forward event count.

Estimated calendar: historical research in 2–4 weeks; honest forward evidence requires elapsed time, likely at least one to two quarters before meaningful authority.

### Wave 7 — Neural Web / Prophet promotion

Goal: bounded risk control.

Deliver only after review:

- compact lobe registration;
- shadow comparison against Prophet outcomes;
- shrink-only intervention rule;
- explanation receipts;
- rollback and kill switch;
- nightly outcome ledger advancement.

Exit gates:

- separate authority review;
- improvement in named decision utility;
- no candidate addition or size increase;
- stale or uncertain data can only weaken the intervention;
- deterministic live-event and model-prediction rules remain separate.

## 17. Timeline and resourcing

Assuming two focused engineering agents or one engineer with strong agent assistance:

| Milestone | Honest calendar |
|---|---:|
| Screenshot-grade demo | hours to 2 days |
| Filing feed + source-linked internal timeline | about 1 week |
| Useful public v0 with shelves, offerings, O/S, cash/runway | 2–4 weeks |
| Credible instrument-complete beta | 6–10 weeks |
| Broad historical parity and operational alerts/API | 8–12 weeks |
| Better-than-competitor high-trust corpus | 3–6 months of backfill and correction |
| Authority-worthy financing forecast | gated by forward accrual, not coding speed |

Parallel work lanes:

- Lane A: EDGAR event spine and source storage.
- Lane B: schemas, reconciliation, and corporate actions.
- Lane C: cash/O/S/instrument parsers.
- Lane D: dashboard, ticker surface, and Learn.
- Lane E: golden corpus, QA, and correction operations.
- Lane F: outcome ledger and later probability research.

Do not put six agents on one schema. Wave 0 must freeze contracts before parallel implementation.

## 18. Cost and operating model

### 18.1 Data

- SEC filing data: public, subject to fair-access and attribution constraints.
- Issuer PRs: generally public; prefer issuer/SEC canonical versions.
- Market data: use existing licensed or permitted sources; redistribution terms require review.
- SMS, email, and webhooks: variable delivery cost.

### 18.2 Compute

The cheapest reliable architecture is:

- cache each SEC document once;
- deterministic parsing and XBRL first;
- run model extraction only on routed, unresolved sections;
- embed or index evidence spans only where search needs it;
- rebuild only issuers affected by new events;
- precompute universe screens;
- static or edge-cached public payloads;
- use a review queue for high-impact ambiguity rather than manually reviewing everything.

Rough pilot infrastructure can remain modest if it rides the existing stack. Production cost will be driven more by model extraction volume, market-data rights, and alert delivery than by SEC storage. Any dollar forecast should be made after Wave 0 measures document counts, token use, and current data contracts.

### 18.3 Human review

The right goal is not “zero humans.” It is:

- deterministic auto-accept for high-confidence structured fields;
- review only high-impact, low-confidence, or contradictory records;
- record every correction as training and parser evidence;
- publish reviewed versus machine-derived status.

Competitor A demonstrates that reconciliation labor matters. Competitor B demonstrates that automation is a marketable wedge. Mastermind should combine them.

## 19. Validation and quality gates

### 19.1 Ingestion

- SEC index completeness by date and form.
- No missing accessions in sampled issuer histories.
- Acceptance timestamp and first-seen timestamp retained.
- Fair-access pacing and cache hit rate.
- Retry and holiday behavior.

### 19.2 Identity

- CIK / ticker / former ticker mapping.
- Multiple share classes.
- foreign private issuers.
- mergers, delistings, and reincorporations.
- symbol reuse.

### 19.3 Document graph

- amendment and supersession correctness.
- EFFECT linkage.
- incorporated-by-reference resolution.
- primary versus resale classification.
- withdrawal and expiry.

### 19.4 Numeric extraction

- unit, scale, currency, and sign.
- dollars versus shares versus share equivalents.
- principal plus accrued interest.
- price, floor, cap, and percentage formulas.
- registered total versus remaining.
- gross versus net proceeds.

### 19.5 Corporate actions

- forward and reverse splits.
- simultaneous ticker change.
- economic-equivalence invariants for exercise price × share count.
- as-filed and adjusted values both preserved.
- no double adjustment.

### 19.6 O/S and float

- source-date ordering.
- later filing versus earlier event reconciliation.
- affiliate classification evidence.
- restricted / registered resale separation.
- missing holder data does not become zero.

### 19.7 Cash and runway

- marketable securities classification.
- restricted cash exclusion.
- one-time adjustment receipt.
- positive operating cash flow.
- post-balance-sheet proceeds and debt payments.
- stale-quarter warning.

### 19.8 Instrument lifecycle

- remaining amount cannot exceed original unless amended.
- partial exercise / conversion and later balance.
- reset and anti-dilution changes.
- expiry, redemption, and termination.
- beneficial-ownership blockers not mistaken for cancellation.
- shareholder-approval and exchange caps.

### 19.9 Product consistency

- API, dashboard, alert, and export agree.
- every derived field opens a receipt.
- changed event updates only dependent issuers.
- corrections retract or amend downstream content.
- EN/ZH meaning parity.
- mobile and accessibility.

### 19.10 Probability

- point-in-time feature audit.
- issuer leakage audit.
- label definition and censoring.
- calibration.
- pre-registered threshold evaluation.
- regime and size stability.
- forward-only ledger.

## 20. Acceptance tests that should be written before build

Golden scenarios:

1. Plain S-3 filed but not effective: ability is pending, not available.
2. Effective shelf with no takedown: capacity is authorization, not issuance.
3. 424B5 shelf takedown: event links to shelf and reduces remaining capacity.
4. Resale prospectus: registered resale supply, not company cash proceeds.
5. ATM with later 10-Q usage: actual sold shares and remaining dollars reconcile.
6. I.B.6 issuer crossing the public-float threshold: state follows official instruction and observation date.
7. Variable convert with floor: spot and floor scenarios diverge correctly.
8. Full-ratchet reset after lower-priced financing: terms and share equivalent update.
9. Cashless warrant amendment: no fictional cash proceeds.
10. Reverse split: as-filed and adjusted histories preserve economic equivalence.
11. Positive operating cash flow: runway prints “not burning,” not an absurd month count.
12. Post-quarter offering: pro-forma cash is separated from reported cash.
13. Authorized-share limit: possible issuance is capped until approval.
14. Foreign issuer using F-3 / 6-K: routed correctly.
15. Conflicting O/S disclosures: both preserved, report marked unresolved.
16. Amendment supersedes terms: old state remains available in time travel.
17. Filing parser low confidence: record defers to review, no risk state fabricated.
18. Stale market price: scenario supply is marked stale.
19. Alert replay: no duplicate notification.
20. Correction: UI, API, export, and webhook all receive the same version.

## 21. Product moat and business case

The raw data moat is low. The operational moat can become meaningful.

Mastermind’s defensibility would come from:

- a point-in-time instrument graph;
- source-span evidence and correction history;
- split-safe historical normalization;
- a growing golden corpus;
- issuer, banker, buyer, and structure outcomes;
- user watchlists and alert workflow;
- developer API and version stability;
- integration with catalysts, market regime, options, and Prophet;
- forward-calibrated financing forecasts.

The category can support a dedicated subscription because it prevents a painful, legible failure mode. Inside Mastermind, however, its larger value is retention and decision context: it makes every small-cap signal more economically aware.

## 22. Final rulings for the build team

1. Build the ledger before the dial.
2. Treat filing discovery as the beginning, not the engine.
3. Land company_event.v1 or use an explicit capital_structure.event.v1 adapter; do not target a fictional contract or create a second company truth plane.
4. Preserve authorization, registration, effectiveness, issuance, and resale as different states.
5. Preserve as-filed and split-adjusted values.
6. Deterministic/XBRL extraction comes before model extraction.
7. A model proposal without a cited source span does not enter the ledger.
8. Unknown is null, never zero.
9. Every adjustment has a receipt.
10. UI, API, alerts, and exports read one canonical object.
11. Ship discovery and ticker workflows; one without the other is incomplete.
12. Rebuild the education suite in original Mastermind language.
13. 13F stays context-only and delayed.
14. Overall risk stays a named posture until a composite earns validation.
15. Financing probability accrues in shadow.
16. Prophet integration is shrink-only after promotion.
17. Confirmed live financing and predicted financing are separate rules.
18. Corrections are first-class events.
19. Coverage and freshness are user-visible product features.
20. The win condition is not “looks like Dilutracker.” It is “the user can reproduce why Mastermind believes every share exists.”

## 23. Recommended first authorization

Approve a Wave 0 + Wave 1 package. Begin the deterministic half of Wave 2 only after the Wave 0 shared-contract, compatibility, pipeline-placement, and authority gates pass:

- schemas and artifact ownership;
- 200-event golden corpus;
- exhaustive filing and source manifest;
- amendment / EFFECT chain;
- O/S, shelf, completed-offering, cash, and raw-runway state;
- internal evidence timeline;
- compatibility output to the existing dilution context.

That slice tests the hard premise—reconciliation quality—before spending time on the public shell. If it passes, the ticker dossier and discovery desk can be built in parallel with exotic instruments.

## 24. Source register

### Official competitor sources

- DilutionTracker home: https://dilutiontracker.com/
- DilutionTracker pricing: https://dilutiontracker.com/pricing
- DilutionTracker Knowledge Base: https://knowledge.dilutiontracker.com/en/
- O/S chart method: https://knowledge.dilutiontracker.com/en/articles/6820942-how-do-i-interpret-the-o-s-chart
- Cash and burn method: https://knowledge.dilutiontracker.com/en/articles/5602396-why-does-the-cash-and-cash-burn-not-match-10k-10q-on-bamsec-finviz
- Float method: https://knowledge.dilutiontracker.com/en/articles/5602376-how-is-your-float-calculated
- Offering ability: https://knowledge.dilutiontracker.com/en/articles/5602359-how-do-i-know-if-the-company-can-offer
- SEC filing cheat sheet: https://knowledge.dilutiontracker.com/en/articles/5870135-sec-filings-cheat-sheet
- ATM guide: https://knowledge.dilutiontracker.com/en/articles/4330335-what-are-at-the-market-agreements-atm
- I.B.6 guide: https://knowledge.dilutiontracker.com/en/articles/4330443-what-is-the-ib6-restriction-or-baby-shelf-rule
- Offering / banker research: https://knowledge.dilutiontracker.com/en/articles/5722415-offerings-investment-bank-tiers-and-why-it-matters-for-small-cap-stocks
- Mega-squeeze research: https://knowledge.dilutiontracker.com/en/articles/5611407-characteristics-of-mega-squeezes-and-how-to-anticipate-them
- Alternate cashless warrants: https://knowledge.dilutiontracker.com/en/articles/10736701-guide-on-alternate-cashless-warrants
- Dilutracker home: https://www.dilutracker.com/
- Dilutracker how it works: https://www.dilutracker.com/how-it-works
- Dilutracker API: https://www.dilutracker.com/dilution-tracker-api
- Dilutracker 13F tracker: https://www.dilutracker.com/13f-tracker
- Dilutracker institutional: https://www.dilutracker.com/institutional

### Official SEC sources

- EDGAR APIs and bulk archives: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Fair-access request limits: https://www.sec.gov/filergroup/announcements-old/new-rate-control-limits
- Form S-3 and General Instruction I.B.6: https://www.sec.gov/files/forms-3.pdf
- Form 8-K items: https://www.sec.gov/files/form8-k.pdf
- Structured filing technical specifications: https://www.sec.gov/submit-filings/technical-specifications
- Securities Act form interpretations: https://www.sec.gov/rules-regulations/staff-guidance/corporation-finance-interpretations/securities-act-forms

### Repository evidence

- collectors/edgar_dilution.py
- engine/neuralweb/bottom_sensors.py
- engine/neuralweb/mastermind_context.py
- config/synapse.yml
- engine/special_situations.py
- engine/capital_allocation.py
- engine/stock_fundamentals.py
- research/DO_NOT_REBUILD.md
- docs/ACTIVE_BUILD_MAP.md
- docs/SIGNAL_BUS.md
- adjacent Jodie / Struct company-intelligence docket

## 25. Bottom line

The SaaS surface has little moat. The trustworthy issuer-state history has more moat than it first appears, but it is still reproducible from public sources.

Mastermind should not build “another dilution score.” It should build the capital-structure truth plane the other scores wish they could prove: a temporal, source-linked ledger that powers a better dashboard today and earns a risk-control role in Neural Web and Prophet later.
