# Calcbench Dissection and the MastermindX Fundamental Forensics Engine

## Full product assessment, clean-room engine inference, build-versus-buy decision, and Fable build docket

| Field | Value |
|---|---|
| Status | Canonical private research handoff |
| As of | 2026-08-01 |
| Audience | Fable, MastermindX, Neural Web, Prophet, data engineering, product |
| Decision | HYBRID — build the forensic brain and provenance substrate; rent or benchmark the long-tail normalization library |
| Canonical file | research/CALCBENCH_FUNDAMENTAL_FORENSICS_ENGINE_ASSESSMENT_AND_BUILD_DOCKET_FOR_FABLE.md |
| Publication boundary | Private research artifact. Do not add to reports.html without a separate operator decision. |

---

## 0. Executive decision

### The verdict

Calcbench is worth studying and worth using as a benchmark. It is not worth cloning feature-for-feature.

The best description of Calcbench is not “another fundamental-data terminal.” It is a **traceable financial-data compiler with an analyst workbench attached**. The visible grids, filters, exports, text comparisons, and Excel formulas are straightforward to reproduce. The difficult asset is underneath:

1. a maintained mapping ontology that turns thousands of standard and issuer-specific XBRL concepts into comparable economic metrics;
2. selective normalized breakout schemas across periods, segments, instruments, plans, geographies, and disclosure tables;
3. point-in-time and revision lineage;
4. extraction of earnings-release and other non-XBRL data;
5. visible data-quality controls; and
6. source-level tracing for supported values and calculations.

That distinction changes the cloneability score materially:

| Target | Cloneability | Judgment |
|---|---:|---|
| Calcbench-looking frontend | 8/10 | Mostly ordinary product engineering |
| Raw SEC/XBRL retrieval and statements | 8–9/10 | Public substrate and mature parsers exist |
| Reliable face-statement normalization | 6/10 | Tractable, but mapping and period logic need care |
| Point-in-time fact ledger | 7/10 | Tractable if designed bitemporally from day one |
| Disclosure search and visual diff | 7–8/10 | Search/diff is easy; section alignment and materiality are harder |
| Dimensional footnote normalization | 3/10 | The core semantic and QA moat |
| Non-GAAP and earnings-release normalization | 2–3/10 | Company-specific, non-XBRL, table-structure problem |
| Full Calcbench product parity | **4.5/10** | Multi-year data-vendor program, not a SaaS feature sprint |
| Focused MastermindX Forensics Engine | **7–8/10** | Feasible because it can ignore most long-tail terminal parity |

The previous 7.5/10 “cloneability” estimate was directionally right only for the narrow forensic product, not for Calcbench itself.

### What MastermindX should do

Build a **Fundamental Forensics Engine**, not a Calcbench replica.

Its job is to answer:

> What materially changed in this filing, why might it matter, what is the evidence, and what benign explanation could make the alert harmless?

The user-facing promise can still be provocative — “What changed that management hopes you will not notice?” — but the engine should not claim intent. The defensible product language is **Filing Change Radar** or **Forensic Delta**: “the material changes most likely to be overlooked.”

The recommended commercial and engineering path is:

1. Negotiate an authorized Calcbench API evaluation and derived-data/redistribution terms. The website subscription does not include API rights.
2. Use Calcbench as a temporary comparison benchmark for 10–20 high-value forensic families, not as unquestioned ground truth.
3. Build MastermindX’s own immutable SEC filing store, parser, provenance graph, point-in-time ledger, disclosure sections, and evidence objects immediately.
4. Replace vendor-normalized metric families selectively when economics, latency, coverage, licensing, or strategic control justify it.
5. Do not rebuild Calcbench’s Excel product, full metric catalog, filer portal, compensation suite, or every specialist footnote table.

### Is $12,000 per year worth it?

**Yes as a diligence and validation expense; no as a screenshot-copying expense.**

Calcbench displayed current website pricing of:

- Professional: $12,000 per user per year
- Premium: $6,000 per user per year
- Basic: free
- API: separate commercial agreement

The $12,000 Professional subscription is small beside a six-figure prototype or seven-figure production normalization effort. But Professional access alone is not the decision product. The decisive questions are:

- Can MastermindX use the API programmatically?
- Can derived forensic signals be stored and shown to customers?
- Can source traces be redistributed?
- Are historical point-in-time snapshots included?
- What are the rate limits, latency, corrections policy, and termination rights?

If those rights are unavailable, the subscription is useful only as a benchmark and analyst tool. It is not a backend strategy.

### Economic reality

The following staffing, timing, cost, storage, and cloud figures are **rough-order-of-magnitude internal planning assumptions with roughly ±50% uncertainty**, not Calcbench quotes or measured production requirements. They assume North American loaded annual rates around $250K–$350K for senior technical/accounting specialists, exclude vendor-license cost, and assume a staged backfill and early service level rather than an instant global/full-history SLA.

Directional North American loaded-cost ranges:

| Scope | Team | Time | First-year cost |
|---|---|---:|---:|
| About 50-company prototype, 5–10 core metrics, 4–6 detectors, basic text diff | 2 engineers + 0.5 accounting SME | 8–12 weeks | $150K–$350K |
| Production S&P 500 engine, 10–20 forensic families | 4–6 engineers + 1 XBRL/accounting SME + fractional QA/SRE | 6–9 months | $1.0M–$1.8M |
| Full U.S. universe and Calcbench-like long-tail catalog | 8–15 staff, including 2–4 accounting/data-QA specialists | 18–30 months | $4M–$12M+ |
| Ongoing full-universe maintenance | 5–8 FTE | Continuous | $1.5M–$4M per year |

Infrastructure is unlikely to be the first bottleneck. A planning envelope of hundreds of gigabytes to low single-digit terabytes and roughly $2K–$15K per month may be reasonable for an early bounded universe before heavy end-user traffic or indiscriminate LLM use. It is not an estimate for immutable full-universe accession bundles with every exhibit/image, repeated retrieval versions, parsed graphs, and search indexes. The bakeoff must measure storage, backfill, and live-filing peaks.

---

## 1. Evidence boundary and investigation method

### What was directly examined

The investigation used an authorized Calcbench Premium trial account in the normal product interface. It covered:

- logged-in product navigation;
- Company In Detail;
- Multi-Company;
- Bulk Data / Data Query;
- Interactive Disclosures;
- Recent Filings;
- Analytics;
- Segments;
- the API documentation surface;
- the Excel product and sample-workbook catalog;
- pricing and tier entitlements; and
- source-trace and disclosure-comparison workflows.

The trial exposed Premium features. Professional-only controls were visibly locked, including the Earnings Model and parts of the specialized raw-data suite. Those controls were not bypassed.

The review was read-only. No account settings, alerts, saved portfolios, uploads, or external messages were created.

### What was not done

Calcbench’s [license agreement](https://www.calcbench.com/home/eula) prohibits reverse engineering and decompilation. This investigation therefore did **not**:

- decompile proprietary JavaScript or binaries;
- probe private endpoints to bypass entitlements;
- defeat access controls;
- inspect private server code;
- claim access to Calcbench’s internal mapping rules or QA queues; or
- infer that visible product behavior reveals an exact proprietary algorithm.

The backend assessment is a clean-room inference from:

1. normal user-visible behavior;
2. Calcbench’s official knowledge base, public API, and client documentation;
3. SEC and XBRL technical documentation; and
4. the minimum architecture required to produce the observed outputs.

### Evidence classes used below

| Label | Meaning |
|---|---|
| OBSERVED | Seen in the authenticated Premium UI on 2026-08-01 |
| DOCUMENTED | Stated by Calcbench, SEC, XBRL International, or Arelle documentation |
| MEASURED | Counted from a public endpoint or public dataset on 2026-08-01 |
| INFERRED | Clean-room architecture inference; confidence is stated |
| UNKNOWN | Not exposed and should not be presented as fact |

This distinction matters. We can reconstruct the product contract and build an equivalent clean-room capability. We cannot honestly claim to know Calcbench’s exact source code, human review process, internal thresholds, or proprietary mapping tables.

---

## 2. The product suite: what Calcbench actually sells

Calcbench organizes nearly every workflow around the same analyst loop:

> choose companies → choose reporting time → choose metrics or disclosures → inspect a dense grid → trace to the filing → compare/export

That workflow is more important than any individual screen.

### 2.1 Product inventory

| Product / surface | What it does | Availability observed / pricing-page minimum | Strategic value to us |
|---|---|---|---|
| Recent Filings | Filing feed with form, period, filing links, associated documents, Calcbench publication time, and data readiness | Public surface; paid/export boundaries not fully established | High as a latency/provenance reference |
| Company Dashboard | Company-level launch/dashboard surface | Basic; enhanced in paid tiers | Medium as a product-navigation reference |
| Company In Detail | As-reported statements, period controls, source trace, quick reports, revisions, ownership links, exports | Basic; enhanced in Premium/Professional | High as the core single-name workflow reference |
| Multi-Company | Peer groups, standardized metrics, raw tags, periods, aggregates, formula/trace exports | Premium | High for cross-company ontology and analyst UX |
| Bulk Data / Data Query | Point-in-time switches, preliminary releases, large metric catalog, aggregates, Excel orientation | Premium, trial row limits | High as the normalized data-query contract |
| Interactive Disclosures | Filing-section taxonomy, full-text search, table/list modes, exports, previous-period and redline comparison | Premium | Very high for the differentiated forensics product |
| Analytics | Common-size analysis and peer average/median/percentile comparisons | Premium | Medium; easy to reproduce after normalized data |
| Segments | Operating/geographic segments and specialist dimensional tables | Premium | Very high data difficulty; selective product value |
| Excel Add-In | Standardized/as-reported formulas, arrays, raw facts, text blocks, trace and refresh | Premium/Professional features vary | Medium for traditional analysts; low initial priority for MastermindX |
| API | Standardized mapped-data outputs, raw, dimensional, disclosure, filings, raw 13F, and specialist endpoints | Separate agreement | Critical for a buy/hybrid path; 13F maturity/coverage not established |
| Raw XBRL Query | Direct tag and context access | Professional | Useful for audit and research, but SEC can supply the substrate |
| Earnings-release query / model | Preliminary 8-K and non-GAAP data | Professional; model locked in trial | High signal value, very hard to normalize |
| Filer Portal | Issuer/auditor workflow and data inspection | Professional suite; issuers can request free access for their own company | Low relevance to MastermindX |
| Auditor fees / flags | Audit relationships and warning metadata | Professional | Medium for forensics, but can be sourced separately |
| M&A / business combinations | Consideration, PPA, goodwill/intangibles and deal tables | Professional/API | Medium-high value, high dimensional difficulty |
| Executive/director compensation | Compensation data | Professional | Low first-wave value |
| Custom Queries | Vendor-built specialist queries | Professional | Medium only when a needed dataset is otherwise unavailable |
| Ownership | Proxy links and external holder/insider links | Observed tab; not established as a separate priced entitlement | Thin in the observed product; not a moat |

Calcbench’s [product overview](https://www.calcbench.com/home/products_overview), [data-set inventory](https://www.calcbench.com/home/our_data), [disclosure list](https://www.calcbench.com/disclosure_list), [API page](https://www.calcbench.com/api), and [Excel page](https://www.calcbench.com/home/excel) corroborate the observed suite.

The pricing page advertised a two-week Premium trial at the review date. It also showed separate academic arrangements: Premium at $6,000 per school per year, Professional at $12,000, and an API add-on at $6,000. These are dated advertised terms, not a quote for MastermindX’s commercial or redistribution use.

### 2.2 Current catalog size

The public available-metrics endpoint returned **1,460 standardized metrics** on 2026-08-01:

- 152 face-statement metrics;
- 1,277 footnote metrics; and
- 31 ratios, 28 of which expose equation descriptions.

That means roughly **87.5% of the standardized catalog is footnote data**.

This is the strongest numerical clue about the moat. Ordinary statements are the minority. The long tail includes tax, pensions and benefits, guidance, insurance, debt, goodwill and intangibles, commitments, contingencies, equity compensation, leases, segments, fair value, derivatives, business combinations, customer concentration, and more.

Other public endpoints exposed:

- 66 XBRL note categories;
- 24 10-K/10-Q section categories;
- 9 non-XBRL document types;
- 31 8-K items;
- approximately 1,581 block tags; and
- 25 dimensional breakout families.

Source: Calcbench’s public [available metrics](https://www.calcbench.com/api/availablemetrics), [document types](https://www.calcbench.com/api/documentTypes), [block-tag counts](https://www.calcbench.com/api/blockTagCounts), and [available breakouts](https://www.calcbench.com/api/availableBreakouts) endpoints. These counts are a dated snapshot and can change.

### 2.3 Company coverage

Calcbench’s public pages use different coverage numbers, including roughly 12,000 companies and roughly 19,000 entities. The likely explanation is listed/current companies versus historical/legal entities, but the definitions were not reconciled in the examined materials. This is an **UNKNOWN**, not a number MastermindX should repeat without vendor clarification.

Calcbench generally describes filing/data history back to 2009, with some filer/dataset coverage as early as 2008. MastermindX should not assume a deep pre-Inline-XBRL or pre-XBRL history without measuring each dataset.

---

## 3. Authenticated UI and workflow teardown

### 3.1 Navigation and information architecture

The logged-in home page presents launch tiles for:

- Excel Add-In;
- Company Detail;
- Multi-Company;
- Disclosures;
- Filings; and
- Request Demo.

The account product menu expands the real suite:

- Company Detail;
- Multi-Company;
- Interactive Disclosures;
- Recent Filings;
- Bulk Data;
- Segments;
- Analytics;
- Excel Add-In; and
- API.

The information architecture is analyst-first rather than novice-first. It assumes the user already understands filings, fiscal periods, XBRL tags, standardized metrics, and point-in-time semantics.

### 3.2 Company In Detail

The Company Detail screen is Calcbench’s strongest single-name surface.

Observed controls:

- Income Statement, Balance Sheet, Cash Flow, and other presentation statements;
- Annual, Quarterly, Combined, and Cumulative periods;
- fiscal-period selection;
- “As Originally Reported”;
- currency conversion;
- all history;
- previous period;
- guidance and non-GAAP overlays;
- values, formulas, and all-statements exports; and
- source links from period headers and individual facts.

The interface explicitly labels fourth-quarter flow values as calculated. The visible logic is annual value minus nine-month cumulative value. This is an important sign of honesty: Calcbench distinguishes filed facts from engine-derived facts.

#### Source trace

Clicking a quarterly Microsoft revenue value opened a source-trace modal containing:

- the XBRL tag;
- the numeric value;
- fiscal period;
- exact filing;
- SEC link;
- relevant source disclosure excerpt or table; and
- a link into the disclosure viewer.

This is the product’s most important UX primitive. A normalized value is never just a number; it is a claim with a reversible path back to the filing.

#### Quick reports

The Quick Reports area exposes deep reports for:

- tax;
- segments; and
- share-based compensation.

It also exposes disclosure packs for:

- accounting policies;
- business combinations;
- commitments and contingencies;
- stock compensation;
- debt;
- derivatives;
- earnings per share;
- equity;
- fair value;
- goodwill;
- income taxes;
- inventory and property, plant and equipment;
- leases;
- revenue;
- segments; and
- related specialist notes.

#### Revisions and ownership

The Revisions tab supports PDF and Excel export and presents filing date, filing type, and revision count. Microsoft had no visible revision rows in the sampled screen.

The Ownership tab was comparatively thin: external Yahoo holder/insider links and proxy statements. This is not a Calcbench moat.

The Earnings Model control was Professional-only and disabled in the Premium trial.

### 3.3 Recent Filings

The filing-retrieval screen supports:

- whole-universe or group filters;
- company filters;
- date ranges;
- filing types;
- sorting; and
- export.

Columns include:

- company;
- filing date and type;
- period end;
- fiscal year and period;
- disclosure link;
- SEC link;
- associated filings;
- Calcbench Published timestamp; and
- data or Earnings Model status.

In the sampled Microsoft sequence, Calcbench showed separate publication timestamps for an earnings 8-K and the later 10-K. This reveals a filing-event pipeline rather than a nightly-only database and gives users a visible latency receipt.

### 3.4 Multi-Company

Multi-Company is a flexible peer and portfolio workbench.

Company selection can use:

- SIC;
- NAICS;
- geography;
- screening;
- indexes such as the Dow, S&P 500, IFRS SEC, and ESEF;
- pasted ticker lists;
- saved peer groups; and
- portfolios.

The screen also offers filing email alerts.

Time and version controls include:

- fiscal versus calendar;
- as originally reported;
- year, quarter, trailing twelve months, and all history.

Metric selectors include:

- Primary Financials;
- Non-GAAP;
- Ratios;
- Footnotes; and
- raw XBRL tag input.

Exports can include values, formulas, and trace. The grid supports sorting, totals, averages, and previous-period retrieval across all selected companies.

The metadata catalog is unusually revealing. It includes filing and data-quality fields such as:

- creation software;
- tag, fact, and extension counts;
- revision count;
- scale, sign, and DEI error counts;
- filing, earnings, and proxy dates and links;
- currencies and exchange rates;
- shares, price, and public float.

This tells us Calcbench treats filing quality itself as data.

### 3.5 Bulk Data / Data Query

Bulk Data is the product contract in its purest form: a matrix builder over normalized facts.

Observed controls:

- point-in-time mode;
- preliminary earnings / 8-K inclusion;
- annual, quarterly, and combined periods;
- all history, a single period, or a range;
- company filters;
- sum, average, count, and standard deviation;
- periods in rows or columns; and
- Excel export with source trace.

The metric descriptions expose several important behaviors and caveats:

- Calcbench calculates EBITDA rather than merely passing through one universal filed tag.
- Bank revenue is defined as net interest income plus non-interest income minus provision for loan losses.
- Calcbench warns that its market data is not its strongest data product.
- Lower tiers disable some filing-quality error metrics.
- The free trial limits the result to 50 rows.

The point-in-time switch and preliminary-release inclusion demonstrate that “period end” is not enough. The system also models when a value became knowable and whether it came from a preliminary non-XBRL source or a later XBRL filing.

### 3.6 Interactive Disclosures

Interactive Disclosures is the closest existing product to the proposed Fundamental Forensics Engine.

Observed controls:

- fiscal versus calendar;
- year versus all history;
- list versus table view;
- disclosure type;
- full-text search with Lucene syntax;
- Word and PDF export;
- Previous Period; and
- Compare Text.

The taxonomy covers:

- earnings releases;
- guidance and KPIs;
- transcript and slide document types, without implying complete issuer coverage or licensing;
- proxy materials;
- SEC comment letters;
- Risk Factors;
- Cybersecurity;
- MD&A;
- audit and controls sections;
- individual 8-K items;
- accounting policies; and
- most major financial-statement notes.

The List view shows disclosure group, XBRL marking, exact filing/report time, and normalized HTML. The sampled Microsoft Risk Factors comparison produced a three-pane layout:

1. current-period disclosure;
2. redline with deletions and additions; and
3. prior-period disclosure.

The visual hierarchy is dated and dense, but the workflow is excellent.

The Table view treats disclosures as columns and companies as rows. It includes word count, source links, disclosure selection, and a Text Analytics control. In the trial, Text Analytics appeared to be a relatively simple word-count-oriented surface, not a hidden semantic AI engine.

Calcbench documents Lucene syntax and relevance behavior in its [disclosure search guide](https://knowledge.calcbench.com/hc/en-us/articles/223299228-Search-the-notes-to-a-company-s-financial-statements), and its client docs describe [disclosure retrieval](https://calcbench.github.io/python_api_client/html/disclosures.html). The compare view is conventional textual diffing; the hard part is reliably locating comparable sections.

### 3.7 Analytics

Analytics combines common-size and peer benchmarking.

The sampled table included:

- metric value;
- year-over-year change;
- value as a percentage of revenue or assets;
- peer average;
- peer median;
- peer percentile; and
- source trace.

This is valuable product packaging but not a deep engine moat once normalized metrics and peer universes exist.

### 3.8 Segments and dimensional data

The Segments surface is much broader than its name implies. Dataset choices included:

- operating and geographic segments;
- deferred-tax assets and liabilities;
- tax reconciliation;
- fair-value assets;
- pension assets and rollforwards;
- debt;
- derivatives;
- stock compensation;
- discontinued operations;
- intangibles;
- REIT holdings;
- customer and supplier concentration;
- business-combination consideration;
- purchase-price allocation;
- acquired intangibles;
- equity-method investments; and
- pensions.

The sampled Microsoft operating-segment table exposed rows such as product, service, Productivity and Business Processes, Intelligent Cloud, and More Personal Computing, with metrics including revenue, operating income, and goodwill. It supported revised versus as-originally-reported values and formula/trace export.

This surface is visually ordinary and semantically difficult. Every row can be an issuer-defined member on a standard or custom axis. A MastermindX cross-company comparison engine would have to decide whether “Cloud,” “Intelligent Cloud,” a legal entity, a product family, and a geography are comparable across time and issuers. The observed Calcbench grid does not prove that it universally resolves issuer-defined members across companies.

### 3.9 API

The visible Swagger surface included endpoints for:

- available metrics;
- business combinations;
- companies;
- dimensional data;
- disclosure contents;
- face statements;
- XBRL fact metadata;
- filings;
- raw XBRL;
- raw non-XBRL;
- raw 13F;
- tag values;
- standardized mapped-data outputs; and
- footnote search.

The exposed models include:

- standardized metric definitions;
- footnote definitions;
- purchase-price allocation;
- dimensional points;
- mapped data with trace;
- statements, contexts, and facts;
- raw XBRL;
- raw non-XBRL; and
- raw 13F.

The Swagger presence of raw 13F does not establish its coverage, maturity, entitlement, or full product support. The mapped-data endpoints expose standardized outputs and trace, not Calcbench’s proprietary mapping rules.

Calcbench publishes a Python client and notebook examples, including columnar bulk download patterns. See the [client index](https://calcbench.github.io/python_api_client/html/index.html) and [public notebooks](https://github.com/calcbench/notebooks).

### 3.10 Excel

Calcbench’s Excel product supports:

- standardized calendar and fiscal formulas;
- as-originally-reported values;
- arrays;
- raw XBRL facts with optional dimensions;
- disclosure text;
- XBRL text blocks;
- non-XBRL fact IDs;
- right-click source trace; and
- refresh.

The strongest implementation is Windows. Microsoft 365, Mac, and a web spreadsheet are more limited or beta-oriented.

Sample workbooks cover:

- face and footnote data;
- standard statements;
- DuPont analysis;
- property, plant and equipment;
- income tax;
- impairments;
- oil and gas;
- portfolio income statements;
- text blocks;
- growth versus maintenance capital expenditure;
- valuation; and
- dynamic arrays.

This is an effective distribution channel into legacy analyst workflow. It is not a priority for MastermindX’s differentiated product.

---

## 4. Product-design assessment

### What Calcbench gets right

1. **Trace is a first-class interaction.** Numbers lead back to exact facts, tables, filings, and formulas.
2. **Time semantics are visible.** Fiscal/calendar, preliminary/final, original/latest, quarter/cumulative, and point-in-time are explicit.
3. **Power-user density is high.** It exposes the controls accounting analysts actually need.
4. **The same object model appears everywhere.** Company, period, metric/disclosure, value/text, trace, export.
5. **Disclosure comparison is integrated with the source corpus.**
6. **Data-quality metadata is surfaced instead of hidden.**
7. **Excel and API make the data portable.**

### What Calcbench gets wrong or leaves open

1. The UI feels like a database workbench, not an intelligence product.
2. Navigation and selectors assume expert prior knowledge.
3. Visual hierarchy is weak; controls and results compete for attention.
4. The product returns a large fact space but does limited prioritization of what matters.
5. Text comparison shows additions and deletions, but not a strong materiality ranking.
6. Peer and common-size analytics are useful but generic.
7. Mobile and casual-user ergonomics are not the design center.
8. The ownership surface is thin.
9. The product’s greatest strength — provenance — is not converted into a concise decision packet.

### The opening for MastermindX

Calcbench answers:

> Find and compare the facts.

MastermindX should answer:

> Which changes deserve attention now, what do they imply, how strong is the evidence, and what would falsify the concern?

That is not a prettier Calcbench. It is a layer above it.

---

## 5. How the Calcbench engine likely works

### 5.1 High-confidence clean-room architecture

The observed and documented behavior implies this pipeline:

~~~mermaid
flowchart TD
    A["SEC live submissions + nightly bulk + issuer releases"] --> B["Immutable accession/document store"]
    B --> C["XBRL and Inline XBRL parse + validation/data-quality rules"]
    C --> D["Raw fact graph: contexts, units, dimensions, labels, linkbases, source spans"]
    D --> E["Versioned mapping ontology"]
    E --> F["Bitemporal normalized observation ledger"]
    F --> G["Typed derivation and ratio DAG"]
    B --> H["Disclosure sectioning + normalized HTML"]
    H --> I["Search index + prior-period alignment + text diff"]
    G --> J["Company, peer, bulk, Excel, and API products"]
    I --> J
    J --> K["Source trace and correction feedback"]
    K --> E
~~~

This is not a claim about Calcbench’s exact codebase. It is the minimum robust architecture needed to produce the visible contracts.

### 5.2 Observed output to inferred mechanism

| Observed/documented output | Required mechanism | Confidence |
|---|---|---:|
| Standardized metric with raw-fact trace | Versioned metric-to-tag mapping rules and a derivation graph | High |
| Multiple raw trace facts with dimensions and negative weights | Compositional mapping, not one-tag aliases only | High |
| Original versus latest values | Versioned observation history | High |
| Revision number, preliminary flag, report/modified/confirmed dates | Event and processing lineage with more than one clock | High |
| Ratio receives a new point-in-time timestamp after a dependency changes | Dependency-aware recomputation | High |
| Calculated Q4 marker | Explicit interval derivation | High |
| Disclosure search and previous-period redline | Section classifier/index plus structural or textual alignment | High |
| Non-XBRL earnings values | HTML-table extraction and row/column association | Documented |
| Filing error counts | Automated data-quality rule layer | High |
| Exact human-review queue, confidence thresholds, and override rules | Not exposed | Unknown |

Calcbench’s [standardized-metric explanation](https://knowledge.calcbench.com/hc/en-us/articles/230017408-What-is-a-standardized-metric) says multiple tags and issuer extensions can map to a common economic concept and that several facts can be combined. Its [standardized numeric client](https://calcbench.github.io/python_api_client/html/standardized-numeric.html) exposes version, timing, original value, and trace fields.

### 5.3 Standardization engine

A naive normalized database says:

> normalized metric = one canonical XBRL tag

A production database must say:

> normalized metric at time t = a versioned rule applied to one or more facts with compatible periods, units, dimensions, entity scope, signs, and provenance

The rule types likely include:

1. direct standard-tag mapping;
2. approved alternative standard tags;
3. deterministic combinations of multiple facts;
4. issuer-extension mapping;
5. presentation- and calculation-linkbase evidence;
6. prior-period and peer structural evidence;
7. company-specific overrides; and
8. exception and QA rules.

Every output must retain:

- rule version;
- source facts;
- weights/signs;
- unit conversion;
- context and dimensions;
- source filing;
- calculation status; and
- confidence/quality status.

The mapping ontology, not the SQL database, is the long-lived asset.

### 5.4 Period and derived-metric engine

Representative deterministic calculations:

**Discrete fourth quarter**

    Q4 flow = fiscal-year flow − nine-month cumulative flow

This is valid only when:

- both values cover the same entity and dimensions;
- units and scale agree;
- the intervals nest correctly;
- neither input is an incompatible revision;
- the fiscal year is not a changed/stub period; and
- the difference passes reconciliation checks.

**Trailing twelve months**

    TTM flow at known-time t = sum of the latest four compatible discrete quarters knowable at t

This must not silently substitute a later-restated annual number into an earlier point-in-time state.

**Point-in-time ratio**

    reconstructed_source_ready_at =
        max(source_event_at for all dependencies)

    actual_known_from =
        computation_published_at after all dependency observations
        and the exact rule version were recorded

If any dependency is revised, the ratio is a new observation. Calcbench explicitly documents this behavior for [point-in-time ratios](https://www.calcbench.com/blog/post/704992501309849600/point-in-time-financial-ratios).

**Bank revenue**

The Calcbench UI describes a bank-specific construction:

    bank revenue = net interest income + non-interest income − provision for loan loss

This is a reminder that standardized metrics can be sector-specific accounting definitions, not mere taxonomy aliases.

### 5.5 Point-in-time and revision engine

Calcbench exposes fields including:

- revision number;
- preliminary status;
- XBRL status;
- date reported;
- date modified;
- date XBRL confirmed;
- original value;
- accession number; and
- trace facts.

Its [point-in-time fundamentals documentation](https://knowledge.calcbench.com/hc/en-us/articles/13794475152919-Point-In-Time-Fundamentals) distinguishes first-reported and later values. Its API notes that pre-2015 report timestamps can be less precise and that later Calcbench-side processing corrections have their own modified time.

A clean design therefore needs the following distinct temporal coordinates:

| Coordinate | Meaning |
|---|---|
| Economic start/end/instant | Business validity, not a knowledge clock |
| source_event_at | SEC acceptance or wire/publication event; not guaranteed practical availability |
| first_observed_at/retrieved_at | When our collector observed and fetched the source |
| recorded_from/recorded_to | MastermindX transaction-time ledger interval |
| rule_available_at | When the exact mapping/detector version existed |
| computation_published_at | When the derived output became consumable |
| superseded_at | When that system output ceased to be current |

The schema should preserve source event time, actual observation, rule availability, computation publication, and correction separately. Otherwise a historical backfill can falsely claim that MastermindX knew a corrected mapping at the source event time.

### 5.6 Non-XBRL earnings engine

Calcbench says its earnings-release parser attempts to match HTML table rows with prior XBRL statement tables. See its [8-K parsing explanation](https://knowledge.calcbench.com/hc/en-us/articles/360010058714-8-K-Earnings-Press-Release-Parsing), [release sources](https://knowledge.calcbench.com/hc/en-us/articles/4403231777303-Earnings-Press-Release-Sources), and [standardization notes](https://knowledge.calcbench.com/hc/en-us/articles/7576892022295-Earnings-Release-Standardization).

A plausible clean-room flow is:

1. locate earnings-release exhibits or issuer-hosted releases;
2. normalize HTML and table structure;
3. infer headers, units, scale, periods, and row labels;
4. align rows to the company’s previous XBRL statement topology;
5. distinguish GAAP, non-GAAP, guidance, and KPI tables;
6. reconcile values against later filed XBRL;
7. assign confidence and expose source spans; and
8. queue ambiguous cases for review.

Calcbench acknowledges that extraction quantity and quality vary. This is important: the product is not magical. It is a parser and mapping layer with variable extraction quality; its repair cadence and human-review share are unknown.

### 5.7 Disclosure engine

The visible disclosure system appears to have three layers:

1. **document normalization** — standard HTML with filing metadata;
2. **section/topic classification** — risk factors, MD&A, policies, individual notes, 8-K items; and
3. **search and comparison** — Lucene/TF-IDF retrieval plus previous-period textual diff.

Simple red/green diffing is easy. Reliable comparison requires:

- section identity across changed headings;
- removal of page furniture and duplicated Inline XBRL markup;
- table-aware normalization;
- boilerplate suppression;
- matching moved paragraphs;
- distinguishing numeric-only changes from policy changes; and
- materiality ranking.

Calcbench’s public post on [standardized disclosure HTML](https://www.calcbench.com/blog/post/blogger3349734422124773596/Easier-SEC-Disclosure-NLP-with-Standardized-HTML) confirms that normalized document structure is an intentional product layer.

### 5.8 Likely technology fingerprints

Public API and client artifacts contain signs consistent with a .NET/IIS application, and Calcbench’s push-notification client uses Azure Service Bus. This is a low-value implementation detail, not the moat, and it is not proof of the full private stack.

MastermindX should choose technology based on its own operating model. The invariant is the data contract, not the language.

---

## 6. What the SEC gives us for free

The public source substrate is stronger than the earlier “normalization is difficult” framing may suggest.

### 6.1 Live and bulk APIs

The SEC’s [EDGAR API documentation](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) provides unauthenticated:

- submissions history;
- extracted company facts;
- real-time updates; and
- nightly bulk archives.

The submission records include:

- accession number;
- acceptance timestamp;
- report date;
- form;
- primary document; and
- XBRL/Inline XBRL flags.

The acceptance timestamp is an essential event clock, but not sufficient proof of exact public availability. MastermindX should preserve accepted_at alongside first_observed_at and retrieved_at so EDGAR queueing, after-cutoff handling, and collector latency remain visible.

On 2026-08-01, the public bulk files were approximately:

- companyfacts.zip: 1.39 GB compressed;
- submissions.zip: 1.55 GB compressed.

These sizes will change. They demonstrate that infrastructure volume is manageable.

### 6.2 Company Facts is useful but insufficient

SEC Company Facts aggregates non-custom, entity-wide facts. It omits much of what MastermindX needs for:

- issuer extensions;
- product and geographic segments;
- debt instruments;
- plan-specific pension data;
- customer concentration;
- tax-reconciliation dimensions;
- maturity tables; and
- many specialist footnote breakouts.

Company Facts is a convenience view, not the canonical long-form fact store.

### 6.3 Financial Statement and Notes datasets

The SEC’s [Financial Statement and Notes datasets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets) provide quarterly as-filed tables such as:

- SUB — submissions;
- TAG — concepts;
- DIM — dimensions;
- NUM — numeric facts;
- TXT — text facts;
- REN — rendering metadata;
- PRE — presentation relationships; and
- CAL — calculation relationships.

The 2009 through June 2026 archives totaled roughly 25 GB compressed when measured for this assessment. Backfill size is not the problem.

### 6.4 Parsing and validation

The SEC publishes [XBRL validation and rendering resources](https://www.sec.gov/data-research/xbrl-validation-rendering). [Arelle](https://arelle.readthedocs.io/en/2.30.24/index.html) supports:

- XBRL 2.1;
- XBRL Dimensions;
- Inline XBRL;
- Formula;
- SEC EFM validation;
- command-line and Python use; and
- web-service interfaces.

The [SEC-maintained Arelle EDGAR plugin](https://github.com/Arelle/EDGAR) and SEC renderer mean MastermindX should not implement the XBRL specification from scratch.

### 6.5 Footnotes are structured, but not normalized

The SEC’s current [EDGAR XBRL Guide](https://www.sec.gov/file/xbrl-guide) describes layers ranging from full-note text blocks to separately tagged amounts, percentages, and numbers.

That structure makes extraction feasible. It does not solve:

- semantic equivalence;
- custom axes and members;
- company-specific labels;
- cross-period identity;
- missing tags; or
- whether two values should be compared.

The public rails eliminate acquisition scarcity. They do not eliminate accounting interpretation.

---

## 7. Why aggregation and normalization are genuinely complex

### 7.1 The short answer

**Data aggregation is moderate. Reliable normalization is very high difficulty.**

Downloading filings, parsing facts, and storing text is an engineering problem. Deciding that two differently tagged, dimensioned, signed, periodized, and revised facts mean the same economic thing is an accounting-knowledge and operations problem.

### 7.2 Failure-mode inventory

#### A. Taxonomy drift

Taxonomies change annually. Concepts are added, deprecated, renamed, and reorganized. Mapping rules must be version-aware. See the SEC’s [2026 taxonomy update](https://www.sec.gov/newsroom/whats-new/2603-2026-xbrl-taxonomies-update).

#### B. Issuer extensions

Companies create custom concepts when they believe standard taxonomy concepts do not fit. Custom tags reduce comparability and can mask ordinary concepts behind issuer language. The SEC continues to monitor [custom-tag trends](https://www.sec.gov/data-research/structured-data/us-gaap-xbrl-custom-tags-trend).

#### C. Dimensions

The same concept can refer to:

- consolidated total;
- product;
- geography;
- legal entity;
- reportable segment;
- debt instrument;
- pension plan;
- customer class;
- share class; or
- transaction.

Custom axes and members make cross-company and cross-period identity difficult.

#### D. Period interpretation

The engine must distinguish:

- instant versus duration;
- discrete quarter versus year to date;
- annual versus trailing twelve months;
- 52- versus 53-week years;
- changed fiscal year ends;
- stub periods;
- missing Q4;
- amended comparative facts; and
- calendar-aligned peer periods.

Calcbench documents case-specific handling for unusual calendars in its [calendar and TTM guide](https://knowledge.calcbench.com/hc/en-us/articles/223267767-What-are-Calendar-Years-and-Periods-What-is-TTM).

#### E. Signs, scales, and units

Fact sign requires separate treatment of the raw value, Inline XBRL sign, concept balance, preferred-label role, rendered sign, and normalized metric orientation. A displayed Inline XBRL token of 78 with scale 6 evaluates to 78,000,000; ignoring the scale creates a million-fold error. The SEC has published reminders on [negative-value handling](https://www.sec.gov/newsroom/whats-new/osd_announcement07142017-data-quality-reminder-negative-values) and [public-float tagging errors](https://www.sec.gov/data-research/structured-data/2507-dqreminder-public-float-tagging-errors).

#### F. Duplicates and precision

Inline filings can legitimately repeat the same fact. Rounded values are only equal within declared precision. Duplicate arbitration must use context, decimals, unit, source position, filing role, and presentation relationships.

#### G. Calculation linkbases are not a normalization engine

Filer-provided calculation relationships help validate arithmetic. They can be incomplete or wrong and usually do not express:

- Q4 derivation;
- TTM;
- ratios;
- cross-period changes; or
- a vendor’s standardized concepts.

XBRL International’s [Calculation 1.1 guidance](https://www.xbrl.org/guidance/adopting-calc1-1/) improves validation behavior but does not create economic comparability.

#### H. Revisions are not restatements

A later filing can recast a comparative value without a formal restatement. Amendments, recasts, source corrections, vendor mapping corrections, and true accounting restatements must be separate event types. Calcbench explains the [revision/restatement distinction](https://knowledge.calcbench.com/hc/en-us/articles/226003228-Are-restatements-and-revisions-the-same-thing).

#### I. Non-GAAP is outside the clean XBRL path

Non-GAAP releases contain:

- changing row labels;
- nested headers;
- images;
- issuer-defined adjustments;
- inconsistent reconciliation direction;
- “adjusted” measures whose definitions change;
- guidance ranges; and
- company-specific KPIs.

This is why non-GAAP exclusion creep is strategically valuable and among the hardest features.

#### J. EDGAR source corrections

EDGAR can correct or remove accepted filings. Daily indexes do not reflect every historical correction; rebuilt indexes may. The raw store needs checksums, reconciliation, tombstones, and retrieval history. See the SEC’s [EDGAR access guidance](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).

### 7.3 Difficulty by proposed forensic feature

Difficulty assumes the raw filing, fact, and section substrate already exists.

| Feature | Difficulty | Why |
|---|---:|---|
| Receivables growth versus revenue growth | Low | Correct intervals and average balances |
| Inventory divergence | Low | Same, with sector applicability |
| Cash-conversion deterioration | Low | CFO/NI/FCF period alignment and one-offs |
| Recurring restructuring charges | Low–medium | Tag aliases, narrative labels, non-GAAP overlap |
| Risk-factor wording changes | Low–medium | Section alignment and boilerplate suppression |
| Auditor change | Low–medium | Form/section extraction and entity matching |
| Material weakness / controls change | Low–medium | Negation, remediation, and section state |
| Going-concern language | Low–medium | Audit/note extraction and negation |
| Stock-compensation dilution | Medium | Split-adjusted shares and repurchase offset |
| Revenue-recognition policy change | Medium | Standards adoption versus company-specific change |
| Lease-obligation wall | Medium | Maturity buckets, current/noncurrent, dimensions |
| Purchase commitments | Medium | Table identity and bucket alignment |
| Tax-rate anomalies | Medium–high | Jurisdictions, discrete items, valuation allowance |
| Pension assumptions | Medium–high | Multiple plans, currencies, discount/return assumptions |
| Customer/supplier concentration | Medium–high | Issuer-defined members and qualitative disclosure |
| Debt maturity/refinancing wall | High | Instrument identity, dimensions, floating rates, refinancing |
| Debt-covenant headroom | High | Narrative definitions and bespoke covenant math |
| Segment-definition changes | High | Member identity resolution across recasts |
| Previously disclosed KPI disappearance | High | Proving comparable prior disclosure and true omission |
| Non-GAAP exclusion creep | Very high | Non-XBRL extraction plus definition drift |
| Capitalized-expense detection | Very high | Accounting-policy semantics; no universal fact |

### 7.4 The central design implication

Do not make every field pretend to have equal certainty.

Use explicit normalization tiers:

| Tier | Mapping type | Initial use |
|---|---|---|
| A | Direct standard concept with compatible context | Eligible for deterministic display only after context, unit, scale, duplicate, PIT, and coverage gates |
| B | Approved standard-concept alternatives | Eligible for deterministic display only after the same gates |
| C | Deterministic combination of traced facts | Eligible for deterministic display with formula only after the same gates |
| D | Issuer extension mapped by structural evidence | Shadow display until reviewed and graded |
| E | NLP or LLM semantic inference | Context/explanation only |

Mapping tier is not authority. All tiers are context/display at birth. Prophet may display qualified A–C receipts, but mapping tier alone grants no behavioral authority. Tier D can shadow. Tier E must not originate numeric facts or decision authority.

---

## 8. Repo audit: what MastermindX already owns

### 8.1 Already covered — do not rebuild

The repository already contains approximately 30–40% of a narrow forensic product.

#### Existing SEC/fundamental computation

engine/stock_fundamentals.py already:

- loads SEC EDGAR XBRL financials;
- emits build-time per-stock panels into site/stockdata/{TICKER}.json;
- computes accrual and cash-backing context;
- compares inventory and receivables growth with sales;
- evaluates margin and asset-growth trends;
- surfaces share dilution;
- calculates or displays leverage context;
- includes Piotroski and Altman evidence;
- de-duplicates correlated working-capital/accrual warnings;
- emits Accounting Quality;
- emits moat falsifiers;
- emits capital-allocation and expectation-state blocks.

The Accounting Quality producer declares itself display-only, but the current downstream path is not cleanly display-only: engine/stock_score.py can use its verdict to cap quality context and alter cautions/verdicts, and the resulting composite can affect pre-sector-cap ordering in scripts/build_stock_library.py. Treat this as an authority-boundary inconsistency requiring audit. New forensics must not enter that path.

The existing stock-page seam is templates/stock.html.j2 in the collapsed “Fundamentals & financials” group.

#### Existing Brain seam

engine/neuralweb/brain_gateway.py already allowlists get_fundamentals and reads baked per-ticker stockdata. Its current response is thin — mainly the Accounting Quality verdict/headline/count — but the read path exists.

#### Existing Neural Web seam

engine/neuralweb/context_api.py is implemented as an absent-tolerant, point-in-time-aware research/query interface, but it is explicitly absent from daily.yml and has no current nightly production consumer. engine/neuralweb/bottom_sensors.py already joins per-name leverage, valuation, and dilution context without making them signal originators.

The governing pattern in world_state is to keep granular per-name rows in columnar storage and expose only compact aggregate state globally.

#### Existing Prophet seam

engine/prophet_bridge.py deterministically originates display-only plans from the us_standouts buy lane. The hold tilt is post-selection and cannot rank or veto. engine/prophet_management.py encodes the ceiling that any narration or management intelligence may only narrate/de-escalate; that ceiling is not evidence that an LLM currently runs in the Prophet path.

This is the correct insertion pattern for Fundamental Forensics.

### 8.2 Existing data defects prove the hard part

The current repo itself is strong evidence against a casual full-clone estimate:

- collectors/edgar.py uses a synthetic period-end plus 120-day availability proxy because SEC Frames lacks a filed timestamp.
- collectors/edgar_facts.py keeps latest-filed values for an annual period, which collapses original-version lineage.
- collectors/edgar_eps.py needed a separate per-filer overlay to recover earliest real disclosure dates and avoid later comparative retags.
- collectors/edgar_share_quality.py contains repairs for wrong units, placeholders, wrong classes/entities, and pre-IPO artifacts.
- collectors/edgar_flow_quality.py handles thousand- and million-fold flow errors with cross-source and neighboring-period checks.
- collectors/edgar_geo_revenue.py documents that Company Facts/Frames is insufficient for dimensions and parses filing archives for a narrow geography use case.
- collectors/edgar_fts.py documents that SEC search yields useful filing metadata but not a normalized searchable text corpus.
- statements_quarterly has near-empty true Q4 coverage and amendment duplicates. Raw row-adjacent comparisons across fiscal-year boundaries are therefore forbidden; Q4 must be derived and checked through explicit interval logic rather than assumed from row order.

These are not implementation mistakes. They are small examples of the general normalization problem.

### 8.3 Missing capabilities

MastermindX does not yet have:

1. an accession-complete filing manifest and reusable document cache;
2. every as-reported fact version with dimensions and source spans;
3. amendment, recast, revision, and restatement lineage;
4. a versioned normalization ontology;
5. a general derivation DAG with reversible trace;
6. filing-section segmentation and normalized document HTML;
7. comparable-section alignment and wording diff;
8. cross-company disclosure search;
9. deterministic forensic finding objects;
10. a dedicated filing-forensics query workbench;
11. evidence-rich Brain reads; or
12. forward grading of forensic findings.

That is the build.

### 8.4 Binding repo fences

The build must obey the following current rulings:

| Ruling | Consequence |
|---|---|
| GAP-U3 | Do not create a duplicate EDGAR solvency/fragility Neural Web lobe |
| FR-8 | EDGAR crawling and heavy filing parsing must remain off the render path |
| FR-9 | Per-stock fundamental features bind to bottom_sensors.py and stock_fundamentals.py, not the hazard panel |
| ESX-U9 | Existing synthetic period-end plus 120-day availability must remain honestly disclosed until replaced |
| LH-R2 | Do not fuse entry, fundamentals, ownership, and expectations into one opaque admission verdict |
| DO_NOT_REBUILD Prophet rule | Fundamental data may enter presentation/management context, not contaminate the graded-board population |

Therefore this program is a **fundamentals buildout subsystem**, not a new alpha lobe.

---

## 9. The differentiated MastermindX product

### 9.1 Product thesis

The Fundamental Forensics Engine should transform a filing from a document into a ranked set of evidence-bearing changes.

For every company and filing:

1. identify what changed numerically, structurally, and linguistically;
2. compare the change with the company’s history and peers;
3. test accounting relationships and cash conversion;
4. estimate materiality, novelty, persistence, and evidence quality;
5. print plausible benign explanations;
6. attach exact source receipts; and
7. expose a compact state to MastermindX, Neural Web, Prophet, and users.

The engine is not a fraud detector. It is a **review-priority engine**.

### 9.2 Ranking model

Rank individual findings, not companies. First apply a hard detector-specific applicability and evidence gate. Then combine normalized components through a monotone calibrated score, such as a weighted geometric mean with declared floors:

    eligible =
        detector_applicable
        AND evidence_gate_passed
        AND temporal_invariants_passed

    priority =
        detector_calibration(
            weighted_geometric_mean(
                materiality,
                novelty,
                persistence,
                peer_rarity,
                cross_statement_inconsistency,
                evidence_quality
            )
        )

Unknown and inapplicable components remain missing; they do not become zero. Each detector defines which components apply, how they are normalized, and what evidence floor is mandatory. Peer rarity must use a point-in-time universe snapshot.

Do not turn this into one universal “manipulation probability.” Each component, gate, missing value, and calibration should be visible and falsifiable.

### 9.3 Every alert must answer six questions

1. **What changed?**
2. **How large is it?**
3. **Why might it matter?**
4. **Where is the filing evidence?**
5. **What benign explanation could account for it?**
6. **How complete and reliable is the underlying data?**

### 9.4 Recommended user-facing surface

#### Filing Change Radar

Top strip:

- latest filing and accepted time;
- comparison filing;
- coverage state;
- high/medium/low finding counts;
- original versus revised toggle; and
- source-latency receipt.

Primary feed:

- top three overlooked changes;
- topic and severity;
- exact old/new value or text;
- materiality;
- evidence tier;
- benign alternative;
- “why flagged” formula; and
- source trace.

Tabs:

1. Change Feed
2. Statements
3. Footnotes
4. Policies and Risk Factors
5. Segments
6. Peers
7. Revision Timeline

Power-user workbench:

- company/universe selector;
- point-in-time/as-originally-reported controls;
- metric/topic query;
- filing and period filters;
- table/list/redline modes;
- saved screens;
- export; and
- API receipt.

This preserves Calcbench’s powerful object model while replacing its “database grid first” experience with “material change first.”

### 9.5 What not to clone

Do not build in the first program:

- a full Excel add-in;
- all 1,460 metrics;
- filer portal;
- executive/director compensation;
- complete 13F tooling;
- generic market data;
- every acquisition/PPA table;
- all specialist insurance/bank disclosure families;
- a Calcbench-identical UI;
- a black-box fraud score; or
- an LLM that reads raw filings ad hoc and invents numbers.

### 9.6 Qualitative and alternative-data value

The most valuable output is not another copy of revenue and EPS. It is a set of primary-source behavioral and disclosure features that traditional financial feeds usually flatten away.

#### Qualitative evidence

- revenue-recognition and accounting-policy wording;
- management’s definition and presentation of non-GAAP measures;
- risk-factor additions, deletions, and specificity;
- new control weaknesses or remediation language;
- auditor changes and audit emphasis;
- going-concern language;
- covenant definitions and waivers;
- segment redefinitions;
- KPI introductions, substitutions, and disappearances;
- customer/supplier concentration language; and
- changes in pension, tax, lease, and valuation assumptions.

#### Alternative-data-like metadata

These are public primary-source features, not proprietary alternative data, but they can behave like an orthogonal data layer:

- filing-to-Calcbench or filing-to-Mastermind processing latency;
- filing revision and recast velocity;
- custom-extension density;
- scale/sign/unit error counts;
- disclosure word-count and structural change intensity;
- unusual late exhibits or amended documents;
- SEC comment-letter topics;
- changes in filing creation software;
- segment/member churn;
- footnote-table expansion or contraction; and
- reconciliation complexity.

Candidate context features:

| Feature | Interpretation | Initial authority |
|---|---|---|
| disclosure_change_intensity | How much supported filing language changed | Context |
| policy_novelty | New accounting-policy content after boilerplate removal | Context |
| kpi_churn | Introduced, renamed, replaced, or missing company KPIs | Context |
| extension_density | Reliance on issuer-specific XBRL concepts | Data-quality context |
| revision_velocity | Frequency and size of later comparative changes | Context |
| reconciliation_complexity | Number, breadth, and persistence of non-GAAP exclusions | Shadow |
| segment_identity_churn | Instability of reportable segment definitions | Context |
| filing_quality_state | Scale/sign/unit/duplicate/DEI rule outcomes | Data-quality context |

These features become useful to Neural Web when they help it reason about trust, survivability, and contradiction. They should not be promoted merely because they feel exotic.

---

## 10. Canonical data architecture

### 10.1 Raw and normalized artifacts

Register every artifact in config/synapse.yml with its storage backend, freshness contract, producer, and full consumer list.

| Artifact | Purpose | Storage class |
|---|---|---|
| filing_manifest and filing_relationship | Filing/accession events plus typed many-to-many relationships | Warehouse/R2; optional bounded latest index in git |
| document_retrieval | URL/status/headers/body hash and every observation/retrieval event | Warehouse metadata + immutable R2 blobs |
| canonical XBRL object tables | Fact occurrences, contexts, units, concepts, and relationship edges | Warehouse/R2 |
| data/edgar/xbrl_facts_long.parquet | Convenient denormalized query projection, not the canonical source | R2/warehouse |
| data/edgar/disclosure_sections.parquet | Normalized sections, topics, spans, hashes, and prior-section links | R2/warehouse |
| data/fundamental_forensics/findings.parquet | Append-only deterministic finding history | R2/warehouse |
| data/fundamental_forensics/forward_ledger.parquet | Frozen finding vintages, outcome rulers, and grades | R2/warehouse; nightly-only advancement |
| data/fundamental_forensics/state.parquet | Bounded current per-company/as-of projection for consumers | Registered bounded git/R2 artifact |
| site/stockdata/{TICKER}.json embedded block | Small user-facing current summary only | Git-backed site artifact |

Raw accession bundles, long facts, disclosure corpora, and event/finding history do not belong in git or per-ticker site JSON. Only bounded latest-state projections and compact presentation artifacts may be git-backed.

### 10.2 Canonical XBRL object model

One long Parquet table is useful for analysis but insufficient as the canonical store. Preserve separate immutable objects:

| Object | Required identity/content |
|---|---|
| document_retrieval | URL, HTTP status, relevant headers/cache validators, observed time, retrieved time, body hash, blob location |
| fact_occurrence | Document-local fact occurrence, raw/parsed value, source span, context/unit references, Inline XBRL attributes |
| context | Entity identifier scheme/value, economic interval/instant, scenario, explicit and typed dimensions |
| unit | Simple unit or compound numerator/denominator measures |
| taxonomy_concept | QName, namespace/version, type, period type, balance, labels, documentation, standard/extension |
| relationship_edge | Arcrole, linkrole, source/target, order, weight, preferredLabel, targetRole |
| computation_run | Code/container digest, rule hash, rounding policy, run ID, rule-available time, publication time |
| dependency_edge | Exact source fact/computation dependencies and weights for every derived value |

Context IDs are document-local and cannot be treated as global identities.

### 10.3 Filing manifest and relationship contract

Minimum filing fields:

- cik;
- ticker/entity-map version;
- accession;
- form;
- filed date;
- source_event_at/accepted_at;
- first_observed_at;
- report period;
- fiscal year/period;
- primary document;
- all exhibit/document references;
- XBRL and Inline XBRL flags;
- source URL;
- latest retrieval receipt;
- content hashes;
- source status;
- tombstone/correction status; and
- parser/validator version.

Do not model accession supersession as one singular pointer. A later 10-K can revise one comparative value without superseding the earlier filing as a whole. Use a many-to-many filing_relationship edge table with typed, evidenced relations such as:

- amends;
- associated earnings 8-K;
- later comparative;
- withdrawn;
- source-corrected; and
- related exhibit.

Observation-level lineage remains separate.

### 10.4 Fact occurrence and long-query contract

Every fact occurrence preserves:

- accession and immutable source-blob hash;
- filing identity;
- taxonomy namespace/version and concept QName;
- entity identifier scheme and value;
- context reference plus economic start/end/instant;
- explicit and typed dimensions;
- unit reference, including compound units;
- raw token/string and parsed value;
- nil and xml:lang;
- decimals/precision;
- Inline XBRL format/transformation, sign, scale, hidden status, and continuation chain;
- concept balance and preferred-label role;
- rendered sign and normalized-metric orientation as separate derived attributes;
- document ID and byte/DOM/source span;
- table row/column coordinates;
- source URL;
- duplicate data-point group;
- quality flags;
- source_event_at;
- first_observed_at; and
- retrieved_at.

Preserve every occurrence. Group duplicates by the XBRL data point — concept, context, and unit — and collapse only consistent, complete duplicates under declared precision. Inconsistent duplicates are flagged; the engine must not silently pick one by source position or presentation role.

For Inline XBRL, a displayed token of 78 with scale 6 produces a fact value of 78,000,000. Store both the token and transformed value so scale errors remain auditable.

data/edgar/xbrl_facts_long.parquet is a rebuildable projection over these canonical objects.

### 10.5 Normalized observation and computation contract

Minimum normalized fields:

- normalized metric ID/version;
- company and economic start/end/instant;
- value and normalized unit/orientation;
- source fact-occurrence IDs;
- mapping tier A–E;
- mapping rule version/hash;
- computation run ID;
- formula, rounding policy, and dependency-edge IDs;
- source accession;
- source_stage;
- observation_event_type;
- revision_class;
- lineage_parent_id;
- scoped revision_ordinal;
- source_event_at;
- first_observed_at;
- recorded_from/recorded_to;
- rule_available_at;
- computation_published_at;
- superseded_at;
- confidence;
- coverage;
- quality flags; and
- trace receipt.

Preliminary/final and original/latest are not intrinsic booleans on a fact. A preliminary 8-K, later 10-Q/10-K, amendment, comparative recast, formal restatement, source correction, parser correction, mapping correction, and XBRL confirmation are distinct typed events. Preserve provenance events even when the numeric value does not change.

“As originally reported,” “latest,” and similar views are explicit query policies using a named vintage_policy.

### 10.6 Forensic finding contract

Suggested schema: fundamental_forensics.finding/v1

Fields:

- finding_id;
- ticker/cik;
- as_of and replay mode;
- source and comparison accessions;
- topic and detector version;
- state/severity;
- detector applicability;
- evidence-gate state;
- materiality, novelty, persistence, point-in-time peer rarity, and inconsistency;
- evidence quality;
- old/new values or text hashes;
- normalized calculation and computation-run ID;
- evidence fact IDs and source spans;
- benign explanations;
- coverage/freshness;
- mapping-tier distribution;
- universe_snapshot_id and classification_as_of where peers are used;
- user-facing summary;
- authority tier;
- recorded_from/recorded_to; and
- forward-grade state.

### 10.7 Temporal law and replay modes

Never overwrite a fact, mapping result, computation, or finding in place.

Economic start/end/instant describes validity; it is not a knowledge clock. Preserve these distinct events:

| Field/event | Meaning |
|---|---|
| source_event_at | SEC acceptance or wire/publication event reported by the source |
| first_observed_at | First time our collector could observe the source |
| retrieved_at | Time a specific document body was retrieved |
| recorded_from/recorded_to | Transaction-time interval in MastermindX’s ledger |
| rule_available_at | Time the exact mapping/detector rule became available |
| computation_published_at | Time the derived result became consumable |
| superseded_at | Time that result ceased to be the current system view |

Support two explicit replay modes:

1. **Source-vintage replay** reconstructs what the source contained at a historical event time under a pinned rule policy. It is hypothetical and must not claim MastermindX actually knew the result then.
2. **Actual-system replay** uses first-observed, recorded, rule-available, and computation-published times to reconstruct what MastermindX could consume in reality.

A historical backfill performed today cannot manufacture historical system knowledge.

For a derived value, reconstructed source readiness is the maximum source_event_at of its dependencies. Actual known_from is the recorded/published computation time after every dependency and exact rule version was available.

The event ledger is the source of truth. Latest-state files are derived views.

### 10.8 Bitemporal entity, security, universe, and market-data master

Point-in-time facts are not enough. Preserve:

- CIK-to-entity and entity-to-security mappings;
- ticker history;
- mergers, spin-offs, and reorganizations;
- share classes and stock splits;
- historical index and peer membership;
- SIC/NAICS/sector classification version;
- currency and FX vintage; and
- market-data vintage.

Every peer percentile or peer-rarity feature carries universe_snapshot_id and classification_as_of. Every dilution feature carries the relevant security/share-class and split lineage. Otherwise survivorship and identity leakage can survive a perfect filing clock.

---

## 11. Forensic detector design

### 11.1 Deterministic first, LLM second

The fact layer should be deterministic.

Use an LLM to:

- classify ambiguous text topics;
- summarize a verified delta;
- propose benign explanations;
- translate accounting language;
- cluster similar issuer labels; and
- help an analyst inspect unresolved mappings.

Do not use an LLM to:

- originate numeric facts;
- silently choose units or scale;
- overwrite a source value;
- assign untraceable confidence;
- assert fraud or management intent;
- increase Neural Web/Prophet authority; or
- parse raw filings at request time without deterministic receipts.

### 11.2 Wave-one detector families

These are close to data MastermindX already has:

1. receivables versus revenue;
2. inventory versus revenue;
3. accrual and cash-conversion deterioration;
4. share-based compensation and net dilution;
5. recurring restructuring charges;
6. basic debt maturity concentration where tagged;
7. effective-tax-rate anomaly;
8. auditor changes;
9. material weaknesses and controls;
10. going-concern language;
11. risk-factor and accounting-policy diffs;
12. segment-label changes; and
13. prior KPI disappearance candidates.

The early product should be excellent at 10–20 families, not mediocre at 1,277 metrics.

### 11.3 Detector examples

#### Receivables versus revenue

Inputs:

- revenue;
- accounts receivable;
- allowance/credit losses where available;
- contract assets;
- DSO;
- acquisition/FX notes.

Output:

- multi-period growth gap;
- days-sales-outstanding delta;
- peer percentile;
- acquisition/FX adjustment;
- evidence quality; and
- whether cash collection corroborates or contradicts the concern.

#### Recurring restructuring

Inputs:

- restructuring and impairment facts;
- non-GAAP adjustment tables;
- related narrative;
- cash payments and liabilities;
- historical filing labels.

Output:

- years/quarters with a charge;
- charge as a percentage of operating expense/revenue;
- cumulative cash versus noncash;
- whether “one-time” language recurs;
- exclusion from adjusted earnings; and
- source evidence.

#### Stock compensation and dilution

Inputs:

- SBC expense;
- diluted and basic shares;
- repurchases;
- option/RSU grants;
- unrecognized compensation;
- cash-flow add-back.

Output:

- SBC/revenue and SBC/FCF;
- gross grants;
- buyback offset;
- net diluted share change;
- unrecognized compensation runway; and
- peer comparison.

#### Debt refinancing pressure

Inputs:

- instrument-level debt where available;
- current/noncurrent debt;
- maturity buckets;
- interest rates and floating-rate exposure;
- cash;
- FCF;
- revolver availability;
- covenant text.

Output:

- maturities within 12/24/36 months;
- maturity-to-cash/FCF ratios;
- floating-rate share;
- weighted coupon reset risk;
- covenant evidence state;
- refinancing events; and
- coverage limitations.

#### KPI disappearance

Inputs:

- issuer-specific metric registry;
- earnings releases;
- MD&A;
- investor slides/transcripts where licensed;
- prior section/table identity;
- business-model and segment changes.

Output:

- comparable KPI previously disclosed;
- last seen;
- expected location;
- current omission confidence;
- replacement metric;
- acquisition/segment-change explanation; and
- exact prior/current evidence.

### 11.4 Scoring caution

The product may show an Accounting Quality state, Earnings Durability state, Cash Conversion state, Balance-Sheet Surprise state, Accounting Anomaly state, and Refinancing Pressure state.

It should not initially collapse them into one number.

Independent, explainable flags are more useful and comply with the repo’s no-fused-verdict law. A later composite requires a pre-registered forward study proving incremental decision value.

---

## 12. Neural Web integration

### 12.1 Ownership

Fundamental Forensics is not a new Neural Web lobe.

It is a canonical per-company evidence subsystem that Neural Web can read as context. This respects GAP-U3 and avoids duplicating an EDGAR solvency/fragility organ.

### 12.2 Consumer contract

Add an absent-tolerant fundamental_forensics dimension to engine/neuralweb/context_api.py with:

- latest filing accession;
- latest filing accepted time;
- coverage;
- high/medium finding counts;
- active topics;
- cash-conversion state;
- dilution state;
- refinancing state;
- accounting-policy change state;
- evidence-quality floor;
- stale flag; and
- source receipt.

Bind compact fields into bottom_sensors.py:

- forensics_state;
- n_high_severity;
- latest_filing_date;
- latest_accession;
- change_topics;
- coverage;
- evidence_tier_floor; and
- stale.

These are read-only bindings from the canonical fundamental_forensics/state artifact, with source-artifact, absent, and stale semantics. bottom_sensors.py performs no new forensics calculation; its charter’s computed-column allowance is already occupied.

Keep granular per-company history in Parquet. world_state may later receive only aggregate breadth, such as:

- percentage of the universe with deteriorating cash conversion;
- sector breadth of refinancing pressure;
- share of recent filers with new material weaknesses; or
- disclosure-change intensity.

That aggregate remains context until it passes its own forward-grade gate.

### 12.3 Claims and grading

Write deterministic findings and grades with:

- exact point-in-time state;
- source accession;
- provenance receipt;
- detector version;
- coverage; and
- forward outcome definition

to a dedicated registered forward ledger. engine/neuralweb/query.py and spine_index are derived read-side federation, not the finding warehouse. Only after grading and an explicit ruling may query.py gain a read-only adapter that projects eligible rows into spine_index. Never write findings directly to data/neuralweb/spine_index.parquet.

The first Neural Web authority is contextual contradiction and survivability evidence, not alpha origination.

---

## 13. Prophet integration

### 13.1 Correct role

Fundamental Forensics enters Prophet **after selection**.

At birth it may only:

- print display context;
- show named cautions and evidence links; and
- freeze a filing-known-as-of snapshot at plan issuance.

The following are shadow-study candidates only:

- enrich or alter thesis-management language;
- shorten the review clock;
- tighten monitoring;
- recommend smaller size;
- de-escalate management confidence; and
- trigger a live re-evaluation action.

Each candidate requires preregistration, accrued outcomes, and a new promotion ruling before it can change live behavior.

It must not initially:

- add names to the board;
- raise rank;
- boost confidence;
- rescue a weak technical setup;
- veto entry automatically;
- alter the graded population; or
- create a fused “good company + good chart” score.

### 13.2 Proposed Prophet evidence pack

| Field | Initial form | Authority |
|---|---|---|
| accounting_quality | clean/watch/warn plus findings | Display/context |
| earnings_durability | durable/mixed/fragile plus recurring-item evidence | Display/context |
| cash_conversion | improving/stable/deteriorating plus calculation | Display/context |
| balance_sheet_surprise | none/watch/high plus revision/maturity evidence | Display/context |
| accounting_anomaly_flags | named anomaly flags, never fraud probability | Display/context |
| refinancing_pressure | low/watch/high/unknown plus maturity coverage | Display/context |

Each field should link to the exact finding and filing receipt.

### 13.3 Shadow authority path

1. Print the evidence pack on Prophet plans.
2. Freeze the filing-known-as-of state at plan issuance.
3. Advance outcomes only in the nightly ledger.
4. Test whether named findings improve drawdown, thesis-break, or management outcomes after conditioning on the existing selection.
5. Promote only a pre-declared shrink/tighten/de-escalation rule.
6. Never promote a confidence-boost rule from the same evidence without a separate ruling.

One subtle audit item: existing Accounting Quality appears to reach Prophet presentation through conviction cautions, while an earlier composite may indirectly affect a soft sector-cap ordering path in scripts/build_stock_library.py. New forensics must not strengthen that path until it is explicitly audited.

---

## 14. Brain and server integration

### 14.1 Extend the existing read

Expand get_fundamentals so it can return:

- current forensic states;
- top findings;
- evidence receipts;
- latest accession and filing time;
- coverage and stale status; and
- links to the filing workbench.

Do not send full raw filings into every Brain prompt.

### 14.2 Add deterministic read tools

Recommended tools:

1. get_filing_changes(symbol, form, accession?)
2. compare_disclosures(symbols, topic, as_of?)
3. search_filing_facts(query, filters)
4. get_fact_trace(fact_or_finding_id)
5. get_revision_timeline(symbol, metric_or_topic)

The model should query normalized indexes and evidence objects. It should not improvise a filing parser inside a chat request.

### 14.3 Serve-time model

The current FastAPI server reads baked artifacts rather than recomputing full panels at request time. Preserve that operating model:

- heavy filing parsing and indexing off the render/request path;
- compact current state baked for public pages;
- dedicated indexed reads for the authenticated workbench;
- raw documents in object storage;
- no large filing corpus in git.

---

## 15. Build, buy, or hybrid

### 15.1 Option A — buy Calcbench as the backend

**Advantages**

- fastest route to normalized/PIT/footnote data;
- broad long-tail coverage;
- mature trace;
- less accounting QA burden;
- ideal benchmark for signal-value testing.

**Disadvantages**

- API and redistribution rights may be restrictive;
- vendor economics and rate limits;
- external correction timing;
- strategic dependency;
- limited control over ontology/version changes;
- product differentiation still must be built.

**Use when**

The API license permits derived customer-facing findings and the unit economics are attractive.

### 15.2 Option B — build full parity

**Advantages**

- complete control;
- own normalization/IP;
- unrestricted product shape;
- potential standalone data business.

**Disadvantages**

- $3M–$7M and 18–30 months for credible broad parity;
- permanent accounting/data-ops organization;
- opportunity cost;
- large low-value tail;
- risk of silently wrong normalized values.

**Use when**

MastermindX intentionally chooses to become a financial-data vendor, not merely an intelligence product.

### 15.3 Option C — hybrid, recommended

**Advantages**

- rapid product learning;
- owned provenance and event substrate;
- vendor as benchmark rather than single point of truth;
- selective internalization of high-value metric families;
- clean path to strategic independence;
- avoids rebuilding low-ROI terminal features.

**Disadvantages**

- dual-system reconciliation;
- licensing negotiations;
- temporary complexity;
- requires clear source-of-truth rules.

**Use when**

MastermindX’s moat is forensic interpretation and decision context, which is the recommended strategy.

### 15.4 Decision matrix

| Criterion | Buy | Full build | Hybrid |
|---|---:|---:|---:|
| Speed to first product | 5/5 | 1/5 | 4/5 |
| Long-tail coverage | 5/5 | 2/5 initially | 5/5 initially |
| Strategic control | 1/5 | 5/5 | 4/5 |
| Upfront cost | 5/5 | 1/5 | 3/5 |
| Ongoing ontology burden | 5/5 | 1/5 | 3/5 |
| Product differentiation | 3/5 | 5/5 | 5/5 |
| Redistribution certainty | Contract-dependent | 5/5 | Contract-dependent, improves over time |
| Recommended | No | No | **Yes** |

### 15.5 Other supplier option

XBRL US exposes granular as-filed facts, dimensions, extensions, and data-quality assertions. Its free grant is not a commercial redistribution license; commercial use requires an agreement or membership. See the [XBRL US API](https://xbrl.us/home/priorities/use/xbrl-api/) and [database grant terms](https://xbrl.us/home/about/legal/database-grant-of-use/).

It can be part of the benchmark set, but it does not remove the need for MastermindX’s forensic interpretation layer.

---

## 16. Ninety-day dual-track bakeoff

### Objective

Determine whether a narrow Fundamental Forensics Engine materially improves analyst/user review while measuring the real cost of vendor versus internal normalization.

This larger bakeoff is not the two-engineer prototype in the planning table. Budget approximately 3–5 engineers, one accounting/XBRL SME, and fractional product/design, QA, and SRE support for the 100–200 issuer, 10–20 detector scope.

### Universe

Use 100–200 issuers across:

- software;
- semiconductors;
- retail;
- industrials;
- energy;
- healthcare;
- banks;
- insurers; and
- REITs.

Include:

- standard calendars;
- 52/53-week retailers;
- serial acquirers;
- high-SBC companies;
- companies with restatements/recasts;
- segment reorganizations;
- preliminary non-GAAP releases; and
- sparse/custom-tag filers.

### Detector set

Start with 10–20 families:

- receivables/revenue;
- inventory/revenue;
- cash conversion;
- SBC/net dilution;
- recurring restructuring;
- basic debt maturities;
- tax-rate anomalies;
- auditor/control/going-concern events;
- risk-factor and policy diffs;
- segment changes;
- KPI disappearance candidates; and
- a deliberately narrow non-GAAP exclusion test.

### Weeks 0–2

- negotiate Calcbench API trial and rights;
- write the source/derived-data license matrix;
- freeze the issuer/file sample;
- define exact facts/findings and gold labels;
- implement filing manifest schema;
- capture raw accession bundles;
- register source-event, observation, recording, rule-availability, and computation-publication coordinates.

### Weeks 3–6

- Arelle parse and validation;
- canonical XBRL object store plus long-fact query projection;
- section extraction and normalized HTML;
- A–C normalization rules for core metrics;
- vendor/internal fact comparison harness;
- source-trace UI primitive;
- point-in-time leakage tests.

### Weeks 7–10

- implement detector set;
- same-company filing diff;
- current-state artifact;
- Filing Change Radar prototype;
- Brain evidence reads;
- analyst adjudication queue.

### Weeks 11–13

- review 100+ filings;
- measure accuracy, coverage, latency, and usefulness;
- price vendor dependency;
- identify metric families worth internalizing;
- write go/no-go and next-wave ruling.

### Proposed acceptance gates

These are targets for the bakeoff, not current claims. Review-worthiness and severity labels should be assigned independently by at least two accounting-capable reviewers who are blinded to vendor/internal provenance and engine rank. Report raw agreement and Cohen’s kappa before resolving disagreements.

| Test | Target |
|---|---:|
| Eligible filing/accession capture | at least 99.9% by next-day reconciliation |
| Source accession and document trace correctness | at least 99% sampled |
| Tier A/B fact agreement with the source filing within declared precision | at least 99% sampled |
| Point-in-time leakage | zero detected in preregistered tests plus enforced temporal invariants |
| Section identity precision for supported topics | at least 98% sampled |
| Top-three finding judged review-worthy | at least 70% of sampled filings |
| Independent reviewer agreement | Cohen’s kappa at least 0.60, with raw agreement printed |
| High-severity false-positive rate | below 10% after coverage exclusions |
| Every displayed finding has exact source receipt | 100% |
| Missing/ambiguous data printed as unknown | 100% |

### Kill or pivot criteria

Pivot away from vendor dependency if:

- derived-data or redistribution rights are incompatible;
- latency is strategically inadequate;
- ontology changes are not versioned or discoverable;
- coverage fails in the highest-value families;
- trace cannot be retained; or
- unit economics break the product.

Pivot away from internal broad normalization if:

- A–C accuracy remains below target after the bakeoff;
- accounting review grows faster than useful detector coverage;
- analysts do not find the top-ranked changes useful;
- the best findings depend overwhelmingly on vendor-only long-tail mappings; or
- full-universe ambitions distract from the differentiated narrow product.

---

## 17. Implementation docket for Fable

### Lane FFE-0 — authority, license, and measurement contract

**Goal:** Make the experiment legally and scientifically interpretable.

Deliverables:

- Calcbench/API rights matrix;
- data retention and derived-output ruling;
- issuer/form/topic sample;
- gold-label protocol;
- metric/finding definitions;
- coverage and quality rubric;
- point-in-time clocks;
- forward-grade outcomes; and
- explicit excluded scope.

Exit gate:

- every vendor field and internal field has a permitted use;
- every detector has a source, formula, and failure state;
- no “validated” language before forward evidence.

### Lane FFE-1 — immutable EDGAR corpus

**Goal:** One reusable source layer for every future filing feature.

Deliverables:

- filing_manifest.parquet;
- raw accession object store;
- document_retrieval receipts with cache validators;
- checksum/reconciliation job;
- submission and bulk backfill;
- typed filing relationships and observation lineage;
- source correction/tombstone behavior;
- descriptive SEC-compliant User-Agent identification;
- a configurable global request budget at or below the SEC’s currently published 10 requests per second;
- throttling, exponential backoff, caching, and 429 recovery;
- parser receipts;
- freshness/coverage monitor.

Exit gate:

- sample accession completeness and trace target met;
- repeat retrieval is idempotent;
- raw source can reconstruct every downstream object.

### Lane FFE-2 — raw XBRL graph and point-in-time ledger

**Goal:** Preserve every fact before normalization.

Deliverables:

- Arelle parse;
- canonical document-retrieval, fact-occurrence, context, unit, taxonomy-concept, and relationship-edge objects;
- xbrl_facts_long.parquet as a rebuildable query projection;
- occurrence-preserving duplicate grouping and inconsistent-duplicate flags;
- scale/sign/unit quality rules;
- source/observation/recording/rule/publication time;
- typed revision lineage and named vintage-policy views;
- Q4 and TTM derivation contracts.

Exit gate:

- zero detected PIT leakage in preregistered tests plus enforced temporal invariants;
- facts trace to exact source span/context;
- amendments and recasts do not overwrite history.

### Lane FFE-3 — versioned normalization core

**Goal:** High-confidence A–C metric families, not full catalog parity.

Deliverables:

- metric registry;
- mapping-rule DSL;
- rule versioning;
- source-fact weights;
- sector-specific formulas;
- derivation DAG and dependency-edge receipts;
- code/container digest, rule hash, rounding policy, and computation-run ID;
- confidence/coverage;
- vendor comparison harness;
- analyst exception queue.

Exit gate:

- fact agreement and trace targets met on the bakeoff set;
- every derived value exposes dependencies;
- no Tier D/E value silently enters production evidence.

### Lane FFE-4 — disclosure corpus and structural diff

**Goal:** Comparable filing sections with source receipts.

Deliverables:

- normalized document HTML;
- section/topic taxonomy;
- disclosure_sections.parquet;
- table and paragraph spans;
- prior-section alignment;
- boilerplate suppression;
- numeric/text diff;
- search index;
- cross-company topic query.

Exit gate:

- supported-section precision target met;
- redline is reproducible;
- moved text is not misclassified as deletion/addition at unacceptable rates.

### Lane FFE-5 — detector pack

**Goal:** Ten to twenty ranked, evidence-bearing forensic families.

Deliverables:

- detector registry/versioning;
- finding schema;
- detector-specific applicability/evidence gates and calibrated components;
- point-in-time universe snapshots for peer rarity;
- benign explanation templates;
- high-severity review queue;
- coverage/freshness flags;
- dedicated nightly-advanced forward ledger and outcomes.

Exit gate:

- review-worthiness and false-positive targets met;
- every finding prints formula, evidence, and limitations;
- no fraud or intent assertion.

### Lane FFE-6 — Filing Change Radar

**Goal:** Make the system useful to a human before making it authoritative.

Deliverables:

- compact stock-page forensics panel;
- dedicated filing-forensics workbench;
- top-three change feed;
- source-trace drawer;
- period/original/latest/PIT controls;
- peers and revision timeline;
- bilingual copy;
- mobile-safe progressive disclosure.

Exit gate:

- user can reach exact source evidence in two interactions;
- top findings readable without accounting-terminal expertise;
- raw detail remains available without bloating the stock page.

### Lane FFE-7 — Brain, Neural Web, and Prophet shadow wiring

**Goal:** Consume the evidence without laundering it into alpha authority.

Deliverables:

- expanded get_fundamentals;
- filing-change/search/trace tools;
- context_api dimension;
- bottom_sensors fields;
- optional aggregate world-state breadth;
- Prophet evidence pack;
- plan-issuance snapshot;
- nightly forward ledger;
- authority audit.

Exit gate:

- no selection/ranking/boost path;
- absent data degrades honestly;
- every consumer names the canonical artifact;
- promotion requires a new ruling.

---

## 18. Sequenced roadmap

### First 30 days — prove the source spine

- close licensing questions;
- filing manifest;
- immutable documents;
- Arelle parse;
- bitemporal long facts;
- five core A/B metrics;
- risk-factor and controls section extraction;
- source trace.

### Days 31–90 — prove user value

- 50 core metrics;
- 10–20 detectors;
- same-company filing diff;
- top-three finding feed;
- 100–200 issuer bakeoff;
- Calcbench/internal reconciliation;
- analyst review;
- go/no-go ruling.

### Months 4–6 — production S&P 500

- operational correction loop;
- broader sector coverage;
- specialist tax/debt/SBC families;
- workbench and Brain tools;
- point-in-time backfill;
- shadow Neural Web/Prophet packets;
- customer-facing provenance.

### Months 7–12 — selective moat expansion

- segment identity graph;
- debt instruments and maturity wall;
- KPI registry/disappearance;
- revenue-policy changes;
- pensions/taxes/leases;
- narrow non-GAAP normalization;
- selectively replace vendor metric families.

### Beyond year one

Only if economics and demand justify:

- broader U.S. universe;
- more specialist footnote families;
- IFRS/ESEF;
- Excel distribution;
- standalone data API;
- filer-side workflows.

---

## 19. Risks and mitigations

| Risk | Consequence | Mitigation |
|---|---|---|
| Silent normalization errors | False forensic alerts and lost trust | Tiered mappings, exact trace, review queue, vendor comparison |
| PIT leakage | Inflated backtests | Separate source/system clocks; immutable versions; leakage tests |
| LLM fact invention | Unreliable numbers | Deterministic fact layer; LLM only explains verified deltas |
| Scope explosion | Multi-year terminal clone | 10–20 detector target; explicit excluded suite |
| License mismatch | Cannot commercialize vendor-derived outputs | Negotiate rights before product dependency |
| Custom-tag drift | Coverage decay | Versioned ontology, issuer history, structural evidence, coverage flags |
| Dimensional identity errors | Wrong segment/instrument comparisons | Entity/member graph, no forced match, review ambiguous cases |
| Non-GAAP parser false positives | Noisy “exclusion creep” | Narrow issuer cohort, reconciliation, confidence, later phase |
| Intent/fraud overclaim | Misleading product | “Review priority,” benign explanations, source evidence |
| Prophet authority leakage | Corrupt graded population | Post-selection only, shadow ledger, explicit audit |
| Per-ticker JSON bloat | Slow site | Compact summary only; indexed API for detail |
| Render-path expansion | Operational instability | Heavy parsing off render path; object/columnar stores |

---

## 20. Final recommendation

### Decision

**Proceed with the Fundamental Forensics Engine. Do not proceed with a full Calcbench clone.**

Calcbench validates the demand and provides an excellent benchmark. Its visible product is highly reproducible. Its long-tail normalization catalog is not.

The strategically rational division of labor is:

- **Own:** SEC corpus, accession lineage, point-in-time clocks, provenance, disclosure diff, forensic detectors, evidence ranking, UI, Neural Web/Prophet contracts, and forward grading.
- **Rent or benchmark:** long-tail standardized footnote metrics while the product proves value.
- **Selectively replace:** only metric families that become economically or strategically important.
- **Exclude:** terminal parity, broad Excel parity, filer portal, and low-value specialist breadth.

The moat MastermindX can build is not “more XBRL facts.” It is:

> a filing-change intelligence system that knows what changed, knows when it became knowable, knows exactly where the evidence came from, and knows how much authority that evidence has earned.

That is more valuable to MastermindX, Neural Web, and Prophet than owning a second generic fundamentals terminal.

---

## Appendix A — Product and technical sources

### Calcbench

- [Calcbench product overview](https://www.calcbench.com/home/products_overview)
- [Calcbench data sets](https://www.calcbench.com/home/our_data)
- [Calcbench fundamental data](https://www.calcbench.com/fundamentaldata)
- [Calcbench disclosure catalog](https://www.calcbench.com/disclosure_list)
- [Calcbench pricing](https://www.calcbench.com/payment/pricing)
- [Calcbench API](https://www.calcbench.com/api)
- [Calcbench Excel](https://www.calcbench.com/home/excel)
- [Calcbench Raw XBRL Query](https://www.calcbench.com/home/rawxbrlquery)
- [Calcbench earnings-release data](https://www.calcbench.com/home/earnings_release_data)
- [Calcbench Filer Portal](https://www.calcbench.com/filerportal/about)
- [Calcbench license agreement](https://www.calcbench.com/home/eula)
- [Standardized metric definition](https://knowledge.calcbench.com/hc/en-us/articles/230017408-What-is-a-standardized-metric)
- [As-reported versus standardized](https://knowledge.calcbench.com/hc/en-us/articles/224533068-What-is-the-difference-between-As-reported-data-and-Standardized-Metrics)
- [Tracing a mapped metric](https://knowledge.calcbench.com/hc/en-us/articles/223267667-How-do-I-trace-a-mapped-metric-on-Calcbench)
- [Point-in-time fundamentals](https://knowledge.calcbench.com/hc/en-us/articles/13794475152919-Point-In-Time-Fundamentals)
- [Calendar years, periods, and TTM](https://knowledge.calcbench.com/hc/en-us/articles/223267767-What-are-Calendar-Years-and-Periods-What-is-TTM)
- [Foreign-currency conversion](https://knowledge.calcbench.com/hc/en-us/articles/115000652114-Foreign-currency-conversions)
- [Stock splits](https://knowledge.calcbench.com/hc/en-us/articles/4407990838167-Stock-Splits)
- [8-K earnings-release parsing](https://knowledge.calcbench.com/hc/en-us/articles/360010058714-8-K-Earnings-Press-Release-Parsing)
- [Earnings-release sources](https://knowledge.calcbench.com/hc/en-us/articles/4403231777303-Earnings-Press-Release-Sources)
- [Earnings-release standardization](https://knowledge.calcbench.com/hc/en-us/articles/7576892022295-Earnings-Release-Standardization)
- [Disclosure search](https://knowledge.calcbench.com/hc/en-us/articles/223299228-Search-the-notes-to-a-company-s-financial-statements)
- [Disclosure comparison example](https://www.calcbench.com/blog/post/blogger8415112756103396020/Calcbench-Cheat-Code-for-Comparing-Disclosures)
- [Point-in-time ratios](https://www.calcbench.com/blog/post/704992501309849600/point-in-time-financial-ratios)
- [Standardized disclosure HTML](https://www.calcbench.com/blog/post/blogger3349734422124773596/Easier-SEC-Disclosure-NLP-with-Standardized-HTML)
- [Standardized numeric Python client](https://calcbench.github.io/python_api_client/html/standardized-numeric.html)
- [Face statements Python client](https://calcbench.github.io/python_api_client/html/face-statements.html)
- [Disclosure Python client](https://calcbench.github.io/python_api_client/html/disclosures.html)
- [Raw non-XBRL Python client](https://calcbench.github.io/python_api_client/html/raw-numeric-non-XBRL.html)
- [Dimensional Python client](https://calcbench.github.io/python_api_client/html/dimensional.html)
- [Calcbench notebooks](https://github.com/calcbench/notebooks)

### SEC, XBRL, and parsing

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC developer resources and automated-access guidance](https://www.sec.gov/about/developer-resources)
- [SEC Financial Statement and Notes datasets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets)
- [SEC Inline XBRL](https://www.sec.gov/data-research/structured-data/inline-xbrl)
- [SEC XBRL Guide](https://www.sec.gov/file/xbrl-guide)
- [SEC XBRL validation and rendering](https://www.sec.gov/data-research/xbrl-validation-rendering)
- [SEC EDGAR data access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
- [Arelle documentation](https://arelle.readthedocs.io/en/2.30.24/index.html)
- [SEC-maintained Arelle EDGAR plugin](https://github.com/Arelle/EDGAR)
- [XBRL taxonomies](https://www.xbrl.org/the-standard/what/key-concepts-in-xbrl/taxonomies/)
- [XBRL Dimensions specifications](https://specifications.xbrl.org/spec-group-index-group-dimensions.html)
- [XBRL Essentials](https://specifications.xbrl.org/xbrl-essentials.html)
- [XBRL developer introduction](https://www.xbrl.org/the-standard/how/getting-started-for-developers/)
- [XBRL Calculation 1.1 guidance](https://www.xbrl.org/guidance/adopting-calc1-1/)
- [XBRL US API](https://xbrl.us/home/priorities/use/xbrl-api/)
- [XBRL US database grant](https://xbrl.us/home/about/legal/database-grant-of-use/)

---

## Appendix B — Findings that remain unknown

The following were not exposed and should not be represented as discovered:

- Calcbench’s complete proprietary mapping table;
- exact mapping confidence thresholds;
- automated versus human-review percentages;
- analyst exception-queue workflow;
- QA staffing and service-level objectives;
- exact infrastructure topology;
- exact customer/API pricing;
- derived-data and redistribution terms;
- false-positive/error rates;
- full Professional-only Earnings Model behavior;
- every specialized Professional query;
- exact non-GAAP table-matching model;
- exact segment/entity-resolution model; and
- exact correction/backfill policy by product tier.

These are diligence questions for Calcbench, not reverse-engineering targets.

---

## Appendix C — Vendor diligence questions

### Rights

1. May MastermindX store normalized API responses indefinitely?
2. May it create and display derived forensic findings to subscribers?
3. May source traces, excerpts, and formulas be shown?
4. What survives termination?
5. Are model training, evaluation, and internal benchmarking permitted?

### Data

1. Which products include full point-in-time history?
2. How are preliminary 8-K values reconciled with later XBRL?
3. Are every revision and vendor-side correction timestamped?
4. What is the typical and tail filing latency?
5. How are amendments, recasts, and restatements distinguished?
6. What coverage metrics exist by disclosure family and year?
7. Can mapped values expose all source facts, dimensions, and weights?

### Operations

1. Rate limits and bulk-delivery options?
2. Historical backfill format?
3. Change notifications for mapping/formula revisions?
4. Availability and correction SLAs?
5. Sandbox/trial?
6. Support access to accounting/data specialists?

### Economics

1. Pricing by user, company, endpoint, volume, or redistribution?
2. Separate production and development rights?
3. Customer-facing API restrictions?
4. Price protection and renewal terms?
5. Audit and attribution requirements?

The answers determine whether Calcbench is a supplier, benchmark, analyst seat, or no-go.
