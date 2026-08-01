# Quartr Pro Teardown and Mastermind Build Docket

**Canonical deliverable:** this file

**Research snapshot:** 2026-08-01

**Scope:** Quartr Pro, Quartr API, Quartr MCP, public company and event pages, public frontend implementation, supplied product media, commercial model, and Mastermind recreation strategy

**Companion:** research/JODIE_STRUCT_ENGINE_TEARDOWN_AND_MASTERMIND_INTEGRATION_DOCKET_2026-07-31.md

**Decision:** build the Mastermind-native evidence and narrative engine; do not clone Quartr wholesale and do not use a Quartr Pro subscription as an ingestion source

---

## Executive verdict

Quartr is not primarily an AI summarizer with a polished interface. It is a continuously maintained primary-source operating system:

1. a global company and security identity graph;
2. a company-event calendar and lifecycle model;
3. a versioned corpus of calls, transcripts, filings, reports, presentations, and audio;
4. page-, paragraph-, and timestamp-level source addressing;
5. search, entity extraction, slide classification, and historical matching;
6. source-grounded AI workflows over that corpus; and
7. multiple monetization surfaces built on the same data spine: Pro, API, MCP, free mobile, public company pages, public event summaries, and editorial content.

The attractive screens are the final ten percent. The difficult ninety percent is reliable ingestion, normalization, permissions, correction handling, citations, entity resolution, search relevance, event completeness, and operational freshness across 15,000-plus companies and 65-plus markets.

For Mastermind, the right move is neither a cosmetic clone nor a global Quartr replacement. It is a narrower, more opinionated system:

- start with the companies and events Mastermind actually analyzes;
- build an immutable company-event-document-source-span spine;
- turn every filing, earnings call, deck, and investor event into one cited event digest;
- derive ticker dossiers, narrative-change views, peer Topics, Mentioned By edges, X fact packets, and SEO pages from that one digest;
- keep all LLM output downstream of deterministic evidence and out of signal authority;
- expand from 100 to 300 to roughly 2,000 companies only after measured retrieval, citation, correction, and user-value gates pass.

That system would not match Quartr's global coverage or live-call SLA. It could, however, surpass Quartr for Mastermind's use case by joining primary-source narrative changes to the existing market, sector, theme, technical, research, distribution, and per-ticker context graph.

### Build, buy, or skip

| Layer | Recommendation | Reason |
|---|---|---|
| Quartr Pro seat | Buy only as a human benchmark if useful | Excellent analyst workflow reference; prohibited as a scraping or competing-product data source |
| Quartr API | Negotiate only for a clearly approved Mastermind use case | Fastest route to licensed normalized content, but default terms are restrictive and pricing is private |
| Company-event identity spine | Build | Foundational, reusable, and already partly present in Mastermind |
| U.S./Canada filing and issuer-document ingestion | Build | Public first-party sources, high strategic leverage |
| Full global, real-time, 65-market ingestion | Skip for now | Large rights, staffing, reliability, and data-operations burden |
| Search and cited event summaries | Build now | High value and tractable once evidence contracts exist |
| Timeline, Mentioned By, peer Topics | Build in phase two | Differentiating context layer with manageable complexity |
| Slide Search, Key Slides, History Mode | Build after the evidence spine | Valuable but materially harder than text search |
| Consensus analyst estimates | Buy or partner | Licensing and normalization dominate engineering |
| Five-second live transcription | Partner or defer | Operationally expensive and not necessary for first product value |
| Quartr interface clone | Do not clone | Mastermind already has better distribution surfaces; integrate into its existing Dashboard, Terminal, Brain, and X systems |

### Difficulty in plain English

- Recreating the visible calendar, filters, search shell, event page, and ticker page: straightforward.
- Recreating useful search and cited summaries for a controlled U.S. universe: moderate.
- Recreating reliable peer-topic clustering, external mentions, slide tagging, and narrative history: hard but feasible.
- Recreating Quartr's total geographic coverage, live-event latency, content completeness, corrections, and institutional reliability: a multi-year company, not a side feature.

### Commercial ruling

The user's reported quote of roughly $500 per month, billed for one year, is plausible as a private institutional quote but is not publicly verifiable. Quartr currently publishes contact-sales pricing, not a numeric Pro price. Its standard 2026 Pro terms do confirm a default twelve-month initial subscription period, automatic renewal unless the Order says otherwise, and a generally non-cancellable subscription.

More importantly, the standard Pro terms explicitly prohibit systematic extraction, scraping, bulk downloading, database population, competing-product construction, and model training or evaluation with Quartr data. A Pro seat is therefore a benchmark and analyst tool, not a lawful Mastermind ingestion method.

The API is the proper product-integration route, but even the standard API terms bind use to an approved use case and contain restrictive default language. Any Mastermind deal would need the Order to state, in writing, the permitted storage, transformation, retrieval, derivative display, public publishing, AI-processing, model-evaluation, and end-user use cases.

---

## Evidence labels

This memo uses four labels:

- **OBSERVED:** directly visible in Quartr pages, supplied media, public API or MCP documentation, public frontend assets, or the Mastermind repositories.
- **DISCLOSED:** stated by Quartr in official marketing, documentation, terms, or newsroom material.
- **INFERENCE:** the most likely implementation based on observed behavior; not claimed as Quartr's disclosed backend design.
- **PROPOSED:** a Mastermind design decision. Any formula under this label is ours, not Quartr's.

This distinction matters. Public source maps reveal client architecture and API call patterns, but not Quartr's private ingestion code, search weights, embeddings, model prompts, source contracts, or ranking models.

### Scope boundary and already-covered work

The companion Jodie and Struct memo already covers:

- the broader Company Event Spine and canonical-story compiler;
- article and X-content fan-out;
- Struct-style publication economics;
- the existing Earnings Calls lobe in greater file-level detail;
- model-specific token-price examples.

This docket does not re-litigate that work. It adds the Quartr-specific layers the companion does not fully specify:

- company-event-content lifecycle semantics;
- primary-source and source-span contracts;
- transcript correction structure;
- Master Search;
- Timeline;
- peer Q&A Topics;
- Mentioned By;
- slide page extraction, Key Slides, and History Mode;
- Quartr's API, MCP, frontend, source-map, pricing, and contractual evidence;
- the exact Mastermind build-versus-buy boundary.

The proposed Corporate Intelligence Spine extends the existing earnings and research systems. It does not replace Research Vault, Signal Bus, the Terminal, Brain, or X Growth.

---

## 1. What Quartr actually sells

### 1.1 Product stack

**DISCLOSED**

Quartr presents four connected surfaces:

1. **Quartr Pro:** the institutional research workspace.
2. **Quartr API:** licensed company-event content for other products and internal systems.
3. **Quartr MCP:** subscriber-scoped tool access for AI clients, bounded by rate limits and Pro permissions.
4. **Free mobile and public web:** discovery, calls, transcripts, company pages, event summaries, and acquisition.

The current Pro page describes:

- more than 15,000 companies;
- more than 65 markets;
- more than 800 clients;
- live calls and real-time transcripts;
- filings, reports, and slide decks;
- company, transcript, filing, slide, and global search;
- AI Chat and event summaries;
- calendar and calendar sync;
- keyword alerts;
- watchlists;
- transcript highlighting;
- daily and weekly recaps;
- slide history comparison;
- custom dataset export;
- workspaces and collaboration.

The API page describes more than 50 million first-party documents alongside live and historical audio, transcripts, filings, reports, slides, summaries, and enterprise service levels.

### 1.2 Positioning

**OBSERVED**

The strongest current positioning is not “we have the numbers.” It is:

> Numbers are easy. Understanding is hard.

Quartr repeatedly frames the value as detecting what management:

- said;
- did not say;
- changed;
- stopped saying;
- moved between prepared remarks and Q&A;
- repeated across quarters;
- disclosed only in a call or presentation;
- mentioned about another company;
- committed to previously and must now be held accountable for.

This is a narrative-continuity product wrapped around primary sources.

### 1.3 Customer segments

**DISCLOSED**

Quartr markets Pro to:

- hedge funds;
- asset managers;
- sell-side analysts and investment banks;
- investor-relations and corporate-strategy teams.

It markets the API to:

- market-data products;
- AI research products;
- brokerage and investing platforms;
- news and financial-information platforms;
- internal enterprise research systems.

Named API or ecosystem relationships shown by Quartr include MarketBeat, RavenPack, Yahoo, Manus, Fortune, Perplexity, TradingView, Rogo, and Avanza. Customer stories span buy-side firms, IR teams, and data-product builders.

### 1.4 Company scale is evidence about the hidden workload

**DISCLOSED**

Quartr says it was founded in 2020 and now has more than 140 team members across Stockholm, New York, and Dublin. In July 2026 it announced a $15 million financing led by Altos Ventures with SEB participation, triple-digit growth, and approximately 120% net revenue retention. A May 2025 release said annual recurring revenue had grown roughly 300% year over year and that four of the five largest hedge funds used Pro.

These figures should calibrate the recreation question. A working demo of Quartr features is not equivalent to Quartr's maintained service. A 140-plus-person vendor is evidence that coverage, customer operations, rights, integrations, sales, and data quality are major parts of the product.

---

## 2. Pricing, contract, and data-rights assessment

### 2.1 What is publicly verified

**OBSERVED**

The current pricing page does not publish a dollar price:

- Pro uses scalable multi-seat pricing and enterprise deal options.
- API uses enterprise or bundle arrangements.
- Both direct the buyer to contact sales.

Third-party directories are inconsistent. Some show contact-sales annual licensing; one lists an $80 monthly starting point while also saying pricing is available on request. Those are not sufficient evidence for current institutional pricing.

### 2.2 The user's approximately $500-per-month quote

**ASSESSMENT**

Treat the quote as a private sales quote, not a public list price:

- approximately $6,000 annual contract value for one seat;
- likely subject to seat count, buyer type, data access, and negotiated terms;
- potentially different from API licensing by an order of magnitude or more.

The amount is not independently confirmed. The one-year commitment is supported by Quartr's default standard terms.

### 2.3 Standard Pro terms: the load-bearing restrictions

**DISCLOSED**

The official 2026 U.S. Pro standard subscription terms specify a default twelve-month initial subscription period and automatic renewal unless the applicable Order changes it. They also make subscriptions generally non-cancellable and non-refundable.

The license is for subscribers' internal research and analysis. Transformative work may be shared within bounded quotation rules, but the terms prohibit, among other things:

- scraping or crawling;
- bulk downloading;
- systematic caching, indexing, or extraction;
- using Quartr data to populate a database;
- building a competing product or feature;
- training or evaluating machine-learning or large-language models on Quartr data.

MCP does not convert the Pro seat into a feed entitlement.

### 2.4 API terms are not an automatic escape hatch

**DISCLOSED**

The standard API internal-use terms tie the license to the Approved Use-case or Permitted Purpose in the Order. Their default language also limits public redistribution, storage, model use, and competing-product construction unless authorized.

### 2.5 Mastermind contracting requirements

**PROPOSED**

If Mastermind considers Quartr API, the Order must explicitly authorize:

1. long-term storage of raw and normalized data;
2. derived event records and embeddings;
3. internal retrieval-augmented generation;
4. model evaluation and quality testing;
5. end-user display inside Mastermind Terminal and Dashboard;
6. derived summaries, narrative deltas, and peer analyses;
7. public SEO pages and X content where intended;
8. citation excerpts and deep links;
9. caching and correction retention;
10. use by automation, Brain tools, and downstream agents;
11. permitted user counts and account types;
12. termination behavior and data deletion or retention;
13. audit, rate-limit, and service-level terms;
14. whether Mastermind can combine Quartr content with its own market and signal data;
15. whether a derived-data right survives contract termination.

Without those clauses, do not architect the core product around Quartr.

### 2.6 Practical decision

A Pro seat at the reported price can still be worth buying for:

- analyst productivity;
- benchmark testing;
- feature and interaction reference;
- side-by-side quality evaluations;
- understanding what institutional users expect.

It cannot be the hidden supply chain for a Mastermind replica.

---

## 3. Feature teardown

### 3.1 Compact feature matrix

| Feature | What is directly observed | Likely hidden engine | Mastermind value | Recreation difficulty |
|---|---|---|---|---|
| Master Search | Search across transcripts, slides, and reports with company, industry, and time filters; transcript hits connect to audio | Inverted index plus field filters; possibly semantic reranking, not publicly proven | Very high | Moderate after corpus exists |
| Slide Search | Every deck page detached and searchable; millions of slides; page tags and filters | PDF split, text extraction, OCR, layout parsing, classifier, index | High | Hard |
| Key Slides | Controlled slide labels; ranking system plus trained AI model disclosed | Multi-label page classifier plus ranking and curated priors | High | Hard |
| History Mode | Related slides linked across quarters; viewer shows chronological family | Within-company slide-family matching using text, layout, and image similarity | Very high | Hard |
| Timeline | Mention counts, share of transcripts, containing transcripts, time buckets, four-year window | Deterministic lexical aggregation | Medium-high | Easy to moderate |
| Topics | Cross-company Q&A themes and debated points with timestamped evidence | Q&A segmentation, retrieval, clustering, ranking, cited synthesis | Very high | Hard |
| Mentioned By | External company mentions in chronological order, issuer's own content excluded | Alias/entity graph plus self-source exclusion and source-span index | High | Moderate |
| Event summaries | AI summary evolves as documents arrive; source tags supported in API | Event packet, structured extraction, synthesis, citation validation | Very high | Moderate-hard |
| Live calls and transcripts | Near-real-time audio and transcript with later corrections | Event scheduling, streaming, ASR, incremental correction protocol | Useful but non-core initially | Very hard operationally |
| Calendar | Day/week/month, saved filters, watchlists, event and report type, geography, industry, market cap, Google/Outlook sync | Event lifecycle store plus user preferences and calendar integrations | High | Easy-moderate |
| Financial segments | Company segment series derived from first-party reports | XBRL/table normalization and company-specific mapping | High | Hard across companies |
| Consensus estimates | Forecasts, multiples, and analyst consensus | Licensed external data and normalization | High | Buy, do not build from scratch |
| Workspaces | Saved slides, snippets, reports, folders, sharing, source links | User content graph and permissions | Medium | Moderate |
| AI Chat | Chats and asynchronous AI workflow runs visible in frontend | Retrieval orchestration, tool calls, run state, source citation | High | Moderate after corpus |

---

## 4. How each engine most likely works

### 4.1 Master Search

**OBSERVED**

Quartr says Master Search covers presentations, transcripts, and reports. The interface supports keyword, company, industry, and time filters. Transcript hits can take the user from text to the corresponding audio moment.

Use cases shown in official material include:

- finding a margin disclosure made only on the call;
- reviewing acquisition promises;
- finding mentions of an external source such as Gartner;
- seeing which companies discuss a particular dependency;
- finding slides containing an exact term.

**INFERENCE**

The minimum architecture is:

1. normalize every document into source-addressable chunks;
2. place exact text and metadata in an inverted index;
3. add company, event, document type, industry, date, fiscal period, and page or timestamp filters;
4. preserve transcript time offsets and slide page IDs;
5. return highlighted snippets with deterministic deep links.

Public material does not prove that the default search uses vector similarity. Excellent financial-document search can be built with BM25, aliases, stemming, phrase search, proximity, fields, and filters. Quartr may add semantic retrieval or reranking, but its exact search weights and models are not public.

**PROPOSED FOR MASTERMIND**

Start lexical and measurable:

- title field weight: 4.0;
- company and alias exact-match weight: 3.0;
- headings and slide title weight: 2.5;
- speaker or section labels: 1.5;
- body: 1.0;
- exact phrase bonus;
- adjacent-term bonus;
- source-quality and freshness tie-breakers.

Add embeddings only for:

- vague natural-language queries;
- related-concept discovery;
- Q&A clustering;
- slide-family matching;
- narrative comparisons.

A proposed hybrid result rank, after score normalization:

    score =
        0.45 * lexical_relevance
      + 0.25 * semantic_relevance
      + 0.15 * exact_entity_or_topic_match
      + 0.10 * recency
      + 0.05 * source_quality

This formula is a Mastermind starting point, not an assertion about Quartr.

### 4.2 Timeline

**OBSERVED**

Quartr's Timeline feature exposes:

- percentage of transcripts containing a term;
- total mentions;
- number of transcripts containing the term;
- time grouping by year, quarter, or month;
- a maximum lookback of four years;
- company, industry, and event-type filters.

**ASSESSMENT**

This is much simpler than the marketing language can imply. The disclosed measures are lexical frequency statistics, not a proprietary model of theme heat.

**PROPOSED FOR MASTERMIND**

Do not collapse different phenomena into one magic line. Publish:

1. raw mention count;
2. documents containing the term;
3. document prevalence;
4. token-normalized mentions per 10,000 words;
5. company breadth;
6. new-company breadth;
7. quarter-over-quarter acceleration;
8. semantic-cluster breadth as a separate series.

For a universe U and period t:

    document_prevalence(t) =
        documents_with_term(t) / eligible_documents(t)

    company_breadth(t) =
        companies_with_term(t) / eligible_companies(t)

    normalized_frequency(t) =
        mentions(t) / total_tokens(t) * 10,000

    breadth_acceleration(t) =
        company_breadth(t) - company_breadth(t - 1)

Counts are deterministic. Any semantic expansion must list the aliases or cluster and retain all source spans.

### 4.3 Topics

**OBSERVED**

Quartr describes Topics as advanced AI that analyzes Q&A across a selected company or industry set, identifies relevant or debated talking points, and creates comparative views. Each point links to a timestamped transcript excerpt.

**INFERENCE**

A likely pipeline is:

1. identify transcript Q&A boundaries;
2. separate analyst questions from management answers;
3. split into coherent question-answer exchanges;
4. embed or otherwise represent each exchange;
5. cluster similar questions or claims across companies and periods;
6. rank clusters by company breadth, recurrence, follow-up intensity, novelty, and recency;
7. have a language model label and summarize the cluster;
8. attach the best source spans to every generated statement.

“Debated” may reflect repeated analyst questions, follow-ups, management pushback, disagreement across companies, or simply relevance ranking. Quartr does not disclose the formula.

**PROPOSED FOR MASTERMIND**

Build a transparent topic record with separate factors:

    topic_rank =
        0.30 * company_breadth
      + 0.20 * question_recurrence
      + 0.15 * analyst_follow_up_intensity
      + 0.15 * novelty_vs_prior_periods
      + 0.10 * cross_company_disagreement
      + 0.10 * recency

The output must expose the components. The model may write the label and synopsis, but it may not manufacture the rank or omit contradictory source spans.

### 4.4 Mentioned By

**OBSERVED**

Mentioned By finds references to a company in other public companies' transcripts, slides, and reports, orders them chronologically, excludes the target company's own materials, and deep-links to the original evidence.

**INFERENCE**

The likely engine combines:

- canonical company identities;
- name, brand, subsidiary, product, ticker, and historical-name aliases;
- entity recognition over chunks;
- contextual disambiguation;
- target-company versus source-company comparison;
- optional relationship classification such as customer, supplier, competitor, partner, or benchmark;
- chronological indexing.

**PROPOSED FOR MASTERMIND**

Start with high precision:

- exact canonical name;
- unambiguous brand or subsidiary alias;
- ticker only when syntax strongly indicates a security;
- ambiguous short names require contextual entity scoring;
- every edge stores the exact matched span;
- issuer self-mentions are excluded by company ID, not name;
- relationship labels remain “hint” until validated.

This should produce a graph:

    source_company
        -> event
        -> source_span
        -> mentioned_company
        -> optional_relation_hint

Once joined to Mastermind themes and market data, Mentioned By becomes more valuable than the Quartr version: it can show whether narrative breadth precedes relative-strength, estimate, options, or capital-flow changes without pretending that correlation establishes causality.

### 4.5 Key Slides

**DISCLOSED**

Quartr says Key Slides uses a carefully designed ranking system complemented by a trained AI model. Its controlled tags include:

- Equity story;
- Snapshot;
- Business model;
- Financial targets;
- Outlook;
- Market overview;
- Products and solutions;
- Market share;
- Capital allocation;
- Unit economics;
- Segment split;
- Management;
- Mission and vision;
- Trading update;
- Footprint.

Quartr also says some results or labels are carefully handpicked for a better experience.

**INFERENCE**

Likely page-level signals include:

- extracted slide title;
- page text;
- layout;
- numeric and table density;
- chart and image presence;
- company and event context;
- phrase and taxonomy anchors;
- model probability for each tag;
- human-curated overrides or priors.

**PROPOSED FOR MASTERMIND**

For an initial tag-specific rank:

    key_slide_rank =
        0.35 * tag_probability
      + 0.25 * exact_anchor_or_title_score
      + 0.15 * numeric_or_table_density
      + 0.15 * recurrence_across_decks
      + 0.10 * recency

Build a labeled golden set before model selection. A rules-plus-small-classifier baseline is likely sufficient for the first 1,000 to 5,000 decks.

### 4.6 Slide Search

**OBSERVED**

Quartr detaches each presentation page from its original PDF and indexes it independently. The official example searches for Outlook within the luxury industry, returning 1,167 slides before a six-month filter reduces the set to 126.

**INFERENCE**

The production pipeline likely includes:

1. fetch and hash the original deck;
2. split into pages;
3. retain page-level PDF and image renditions;
4. extract embedded text;
5. run OCR only where text coverage is poor;
6. detect title, body, charts, tables, and regions;
7. classify slide tags;
8. index text and metadata;
9. generate stable page citations;
10. create thumbnails and viewer assets.

### 4.7 History Mode

**OBSERVED FROM SUPPLIED MEDIA**

The supplied History Mode video shows a primary slide, a page-thumbnail rail, and a bottom history rail labeled “23 slides in history.” The user can switch among related pages from Q2 2026, Q1 2026, Q4 2025, Q3 2025, and earlier quarters. The example is a financial-position slide whose layout and underlying numbers change.

The interaction appears to swap members of a precomputed slide family. It does not visibly present a pixel-difference overlay.

**INFERENCE**

Likely matching stages:

1. restrict candidates to the same company;
2. prefer compatible slide tags;
3. compare normalized titles and anchor text;
4. compare full-page semantic representations;
5. compare layout and image similarity;
6. require chronological plausibility;
7. group sufficiently similar pages into a family;
8. allow correction or manual overrides for ambiguous matches.

**PROPOSED FOR MASTERMIND**

Candidate matching:

    family_match =
        0.40 * visual_embedding_similarity
      + 0.35 * semantic_text_similarity
      + 0.15 * normalized_title_similarity
      + 0.10 * layout_or_perceptual_hash_similarity

Require:

- same company;
- compatible event or deck type;
- compatible slide tag, unless manually overridden;
- minimum threshold;
- ambiguity gap between best and second-best candidate;
- review queue for high-value uncertain matches.

Do not call an image change a business fact. Extract and compare:

- numeric labels and values;
- guidance ranges;
- segment names;
- KPI presence or absence;
- chart series labels;
- text claims;
- footnotes.

The viewer can show the visual history; the narrative engine should report only validated text or numeric changes with citations.

### 4.8 Event summaries

**DISCLOSED**

Quartr API documentation says summaries may be attached to events or documents, are sold as a separate content family, can draw from slides, transcripts, and reports, and are continuously updated as new source documents arrive. API summaries can contain document-source tags and a structured source array containing document, page, timestamp, and source-type information.

**OBSERVED**

Public Quartr event pages publish AI-generated summaries with a warning that AI can make mistakes and important information should be verified.

**INFERENCE**

This strongly suggests an event-packet workflow rather than one raw giant prompt:

- event is created;
- sources arrive independently;
- each source is parsed and added to availability state;
- structured facts and claims are extracted;
- summary is generated or amended;
- citations are bound to source spans;
- later edited transcripts or reports can supersede earlier versions;
- derived surfaces reuse the event summary.

### 4.9 Calendar

**OBSERVED FROM SUPPLIED MEDIA**

The newer Pro video shows:

- left navigation for Home, Calendar, Search, Chat, Topics, Saved, Workspaces, and Watchlists;
- a week calendar with event cards;
- 19 events before filtering;
- saved and ad hoc filters for watchlists, event type, companies, countries, report type, industries, market cap, and time;
- an industry filter for semiconductors;
- a resulting 21-event board including Qualcomm, STMicroelectronics, Arm, Micron, TSMC, Intel, onsemi, Broadcom, NXP, Marvell, Texas Instruments, KLA, Lam Research, Samsung, Applied Materials, NVIDIA, and Analog Devices.

The supplied stills also show:

- day and week views;
- followed-company event inclusion;
- audio, transcript, slide, and financial-document actions;
- Google and Outlook calendar synchronization.

**ASSESSMENT**

The frontend is uncomplicated. The hard part is maintaining authoritative event time, timezone, type, fiscal-period, estimated-versus-confirmed status, rescheduling, cancellation, and source availability.

### 4.10 Live transcripts

**DISCLOSED**

Quartr's API documentation advertises:

- 90% of live events streamed and transcribed within five seconds of event start;
- 95% of post-event transcripts within 45 minutes after conclusion;
- 90% of event audio within 20 minutes;
- 90% of reports and filings within 15 minutes of release;
- edited transcripts within a couple of hours;
- 90% of slide decks within 30 minutes of release.

The live transcript protocol supports JSON Lines words, timestamps, speakers, phrase confidence, and later refinement instructions including word update, insertion, deletion, and paragraph insertion.

**ASSESSMENT**

This is not merely an ASR model. It is event scheduling, audio acquisition, streaming, incremental transcript state, correction semantics, monitoring, retries, and customer-facing latency. It is the least attractive layer for Mastermind to reproduce first.

---

## 5. Public API and MCP reveal the real data model

### 5.1 Three-level object model

**DISCLOSED**

Quartr's public API centers on:

    company -> event -> content

Content families have independent availability and lifecycles:

- documents;
- audio;
- live audio and live transcripts;
- raw and edited transcripts;
- chapters;
- summaries;
- slide pages.

This is a crucial design clue. An earnings call is not one blob. It is an event whose content arrives, changes, and becomes complete in stages.

### 5.2 Identity

Quartr company records support:

- internal company IDs;
- exchange and ticker pairs;
- ISINs;
- CIKs;
- OpenFIGI identifiers;
- geography, industry, status, and other metadata.

The API deliberately avoids treating a company name as the primary identifier.

### 5.3 Documents

Parsed documents may be delivered as Markdown that preserves headings and tables. Parsed-document access is separately permissioned and requires the relevant base content package. Document files are delivered through CDN links.

Slide decks have per-page endpoints with page PDF and image URLs. This is the contract needed for page-level search, citations, Key Slides, and History Mode.

### 5.4 Transcripts

The transcript hierarchy can preserve:

    transcript
      -> paragraph
        -> sentence
          -> word

Words carry time and confidence. Paragraphs map to speakers. Quartr distinguishes raw, edited, and live transcript types, and chapters can identify prepared remarks, Q&A, and nested topics.

### 5.5 Summary citations

Structured summary sources can include:

- source ID;
- document ID;
- page or timestamp;
- source type.

This is the right pattern for Mastermind: citations are data, not decorative links added after generation.

### 5.6 Delivery modes

The public API supports:

- REST retrieval;
- webhooks;
- daily Snowflake sharing;
- modular content packages.

The “fetch only and pay only for what you use” positioning implies content-family entitlements and enterprise packaging rather than a simple all-you-can-eat seat.

### 5.7 MCP

**DISCLOSED**

The Quartr MCP endpoint uses OAuth 2.0 with PKCE and subscriber-scoped bearer tokens. Documented limits include:

- individual tool limits of roughly 20 to 100 requests per minute;
- 100 aggregate requests per minute;
- 2,250 requests per hour;
- 8,500 requests per day.

Documented tool families include:

- current user;
- company search and profiles;
- company lists and related companies;
- events and event types;
- documents and page-by-page reading;
- transcript selection and Q&A-only reading;
- document search with highlighted snippets;
- conferences;
- financial statements;
- event and document AI summaries;
- watchlists;
- keyword alerts;
- folders;
- workspaces;
- saved search filters;
- GICS hierarchy.

Quartr explicitly directs product integrations to the Public API, not MCP.

### 5.8 Mastermind implication

Do not expose dozens of low-level Quartr-shaped Brain tools. Keep the storage model granular but the agent interface compact:

1. search_company_sources;
2. get_company_event;
3. compare_company_narrative;
4. get_peer_topic_pulse.

Everything else should be composed behind those contracts.

---

## 6. Frontend and codebase inspection

### 6.1 Boundaries

The inspection was limited to:

- public HTML;
- public JavaScript bundles;
- publicly served source maps;
- public API and MCP documentation;
- unauthenticated public company and event pages;
- supplied product images and videos.

No authenticated private surface was scraped, no access control was bypassed, and no proprietary backend code was obtained.

### 6.2 Marketing and public pages

**OBSERVED**

The main Quartr site is a Next.js Pages Router application deployed on Vercel and backed by Storyblok content. Public page hydration contains structured company and event-summary content.

Public company pages are indexable and canonicalized. One example uses an SEO title in the form:

    Apple (AAPL) Investor Relations, Earnings Summary & Outlook

The hydrated company page contains:

- the latest AI summary;
- a next-event card;
- suggested AI questions;
- historical event-summary cards;
- cursor-paginated event data.

Public event pages expose detailed AI summaries combining source materials and include an AI-error disclaimer.

### 6.3 Pro web application

**OBSERVED**

The Pro application at web.quartr.com is a Vercel-hosted client with a public Sentry release marker of v6.7.83. Its HTML preconnects to:

- assets.quartr.com;
- features.quartr.com;
- web.api.quartr.com;
- api2.amplitude.com;
- Vercel Insights;
- private.quartr.com.

Public source maps expose original TypeScript module paths and dependency versions. The inspected release includes:

- React 19.2.7;
- TanStack React Start 1.168.26;
- TanStack Router around 1.170;
- TanStack Query 5.101.0;
- Vite 8.1.0 with Rolldown;
- Elysia Eden 1.4.10;
- Elysia 1.4.28;
- TypeBox 0.34.41;
- Zod 4.4.3;
- oidc-spa 10.2.1;
- Sentry;
- Amplitude browser 2.21.1;
- Vercel Insights.

### 6.4 Client-backend behavior visible in source maps

**OBSERVED**

The client:

- calls web.api.quartr.com through a typed Elysia client;
- identifies itself with a web/app client name and release version;
- uses bearer authentication through an OIDC or Keycloak-style flow;
- calls event, user, watchlist, chat, AI-workflow, and asset-folder routes;
- cursor-paginates AI chats;
- represents AI workflow runs as pending or running;
- polls active workflows at roughly two- to three-second intervals;
- caps active automations at ten;
- uses a roughly 30-second stale window for watchlist query caching;
- includes desktop-wrapper authentication and update code;
- sends analytics and web-vitals telemetry;
- supports feature flags and disabled-feature headers.

### 6.5 Service topology inference

**INFERENCE**

Quartr appears to have at least two web-service generations:

- public API v3 responses expose an Express lineage behind Caddy or Envoy;
- the current Pro web backend uses a typed Elysia or Bun-oriented client contract.

This suggests a mature system with multiple services rather than a single application. The public frontend code confirms client state and request shape, but not private search, ingestion, ranking, or model implementation.

### 6.6 What the source maps do not tell us

They do not disclose:

- source-vendor agreements;
- event collection operations;
- search indices or weights;
- embedding models;
- Key Slide training data;
- slide-family thresholds;
- Topics cluster scores;
- prompts;
- model routing;
- fact-verification rules;
- human quality-control queues;
- correction policies;
- internal cost.

Any claim about those layers must remain an inference.

---

## 7. AI synthesis: why the writing is good and what it probably costs

### 7.1 Is it AI-written?

**ASSESSMENT**

The public event summaries are explicitly labeled as AI-generated. The feature and investor-relations articles are not all labeled the same way and should not automatically be called fully AI-written.

Their consistency suggests a hybrid editorial system:

- structured source packet;
- reusable outlines;
- company and event metadata;
- model-assisted draft or section drafting;
- house-style prompt and examples;
- automated link insertion and metadata;
- human editorial review for high-value pages;
- direct product screenshots and use cases;
- deterministic publication templates.

The high quality is not evidence of a giant token burn. It is more likely evidence of excellent upstream structure and editorial control.

### 7.2 The efficient architecture

An efficient event pipeline does not ask a model to rediscover the whole event for every output. It creates one canonical evidence object:

    source documents
        -> parsed spans
        -> structured facts and claims
        -> cited event digest
        -> event summary
        -> ticker page
        -> peer topic view
        -> alert
        -> SEO page
        -> X posts
        -> short-form variants

The expensive extraction happens once. Distribution is cheap.

### 7.3 Recommended Mastermind model workflow

**PROPOSED**

1. **Deterministic parsing**
   - XBRL facts;
   - filing metadata;
   - tables;
   - fiscal periods;
   - source identity;
   - transcript speakers and times;
   - slide page IDs.

2. **Structured extraction**
   - revenue and margin claims;
   - guidance;
   - segment performance;
   - customer or supplier references;
   - stated risks;
   - management confidence and uncertainty language;
   - analyst questions;
   - commitments and changed wording.

3. **Claim reconciliation**
   - prefer newer edited source over raw source where appropriate;
   - preserve conflicts;
   - rank source authority;
   - never silently overwrite earlier source versions.

4. **Canonical event digest**
   - machine-readable facts;
   - narrative deltas;
   - citations;
   - uncertainty;
   - source completeness state.

5. **Writer**
   - long-form summary or article from the digest;
   - no raw-corpus access unless the packet is insufficient;
   - voice and channel style separated from evidence.

6. **Verifier**
   - number and unit checks;
   - entity checks;
   - citation coverage;
   - unsupported-claim rejection;
   - stale-source checks;
   - regeneration or block on failure.

7. **Fan-out**
   - Terminal dossier;
   - Dashboard event card;
   - Brain answer context;
   - X fact packet;
   - SEO page;
   - email or watchlist alert.

### 7.4 Token budget per event

**PROPOSED PLANNING RANGE**

A naive implementation might stuff:

- a 10-Q or 10-K;
- earnings release;
- transcript;
- presentation;
- prior-quarter material

into one or several long prompts. That can consume roughly 50,000 to 150,000 input tokens per event before retries, with 1,000 to 3,000 output tokens.

An efficient standard earnings-event pipeline can target:

- extraction and retrieval: 12,000 to 24,000 input tokens;
- digest, writing, and validation: 12,000 to 25,000 input tokens;
- total input: roughly 24,000 to 49,000 tokens;
- total output: roughly 3,000 to 6,000 tokens.

A large 10-K, analyst day, or sprawling multinational event may require two to four times that amount.

Once the digest exists, all SEO and X derivatives together should add only:

- 2,000 to 8,000 input tokens;
- fewer than 1,500 output tokens.

They should not reread the raw documents for each channel.

### 7.5 Annual token volume

For 2,000 core companies with four standard result events:

    8,000 events per year
    192 million to 392 million input tokens
    24 million to 48 million output tokens

Average monthly volume:

    16 million to 33 million input tokens
    2 million to 4 million output tokens

The operational problem is peak earnings-day concurrency, not average annual tokens.

For a global 15,000-company universe with roughly 30,000 to 50,000 modeled events:

    720 million to 2.45 billion input tokens
    90 million to 300 million output tokens

Those figures are substantial, but data licensing, transcript rights, ingestion operations, support, and quality control are likely more expensive than the model calls.

### 7.6 Backfill

Eight quarters for 2,000 companies equals 16,000 events:

    384 million to 784 million input tokens
    48 million to 96 million output tokens

Cut this sharply by:

- deterministic numeric extraction;
- document hashes;
- prompt caching;
- reusing source parses;
- storing embeddings once;
- summarizing only higher-priority names;
- generating long prose on demand;
- using a low-cost extraction model and a stronger writer only for Tier A;
- avoiding a model for lexical counts, calendar state, and arithmetic.

### 7.7 Quality is more sensitive to packet design than model size

The strongest cost lever is a compact, source-grounded event packet. A better prompt cannot rescue:

- duplicate or wrong-quarter sources;
- missing edited transcripts;
- broken fiscal-period mapping;
- stale guidance;
- unresolved units;
- uncited claims;
- a slide matched to the wrong historical family.

---

## 8. Marketing, SEO, and monetization

### 8.1 Public content estate

**OBSERVED**

Quartr's sitemap estate currently contains approximately:

- 15,949 company routes;
- 690 Insights routes;
- 60 Newsroom routes;
- roughly 16,845 URLs across the sitemap family in total.

The company pages are a programmatic SEO surface. They use ticker, company, investor-relations, earnings-summary, and outlook language and link into event history.

Public event pages provide indexable, detailed AI summaries. Insights pages target:

- investor-relations workflows;
- product use cases;
- feature education;
- company and market concepts;
- search-intent queries;
- customer case studies.

### 8.2 Funnel

**ASSESSMENT**

The likely funnel is:

    search or social discovery
        -> public company page, event summary, or Insights article
        -> trust through primary-source depth
        -> free app, newsletter, or recurring use
        -> Pro demo or sales contact
        -> multi-seat expansion

The API creates a second funnel:

    enterprise developer or product team
        -> API documentation and named integrations
        -> paid data package
        -> broader content families and usage

### 8.3 Why the content strategy works

One evidence spine creates several compounding assets:

- evergreen company landing pages;
- event-driven pages that capture earnings intent;
- feature pages that educate institutional buyers;
- customer cases that de-risk the purchase;
- newsletter inventory;
- social content;
- internal links among companies, events, and themes;
- fresh pages every quarter;
- demonstrations of product quality using the product's own data.

The content is product marketing and product output at the same time.

### 8.4 Revenue model

**DISCLOSED AND INFERRED**

Verified revenue surfaces:

- annual Pro subscriptions;
- scalable multi-seat and enterprise arrangements;
- API content packages and enterprise agreements.

Likely expansion levers:

- more seats;
- more teams;
- more content families;
- additional API volume;
- additional markets or datasets;
- workflow dependence through watchlists, workspaces, and integrations.

The approximately 120% disclosed net revenue retention supports a land-and-expand interpretation.

### 8.5 What Quartr does with user data

The standard terms allow Quartr to collect and use usage data for operations, analytics, product improvement, and business purposes. The frontend also uses Amplitude and web-vitals tooling.

There is no public evidence in the reviewed material that Quartr monetizes behavioral data by selling it as an external dataset. Do not assert that it does.

### 8.6 Mastermind distribution advantage

Mastermind has a potentially stronger loop because it already owns:

- ticker dossiers;
- market and sector context;
- Neural Web;
- Mastermind Brain;
- the Terminal;
- Research Vault;
- X Growth infrastructure;
- multiple account personas;
- deterministic hard gates and an outbox;
- programmatic report pages.

The missing piece is a canonical primary-source event packet. Once built, Mastermind can produce differentiated outputs:

- “what changed” rather than generic summaries;
- peer contradiction maps;
- theme breadth against price and flow;
- supplier and customer mentions;
- narrative changes against sector rotation;
- evidence-backed posts routed to distinct X personas;
- ticker dossiers with source history;
- public event pages that lead to Terminal conversion.

---

## 9. Mastermind current-state audit

### 9.1 Existing strengths

**OBSERVED IN REPOSITORY**

Mastermind already has:

- an Earnings Calls lobe and qualitative earnings scorer;
- EDGAR earnings 8-K metadata collection;
- an R2-backed earnings history path;
- explicit earnings-intelligence health and provenance work in flight;
- Research Vault ingestion, full-text search, private/public separation, and per-report SEO pages;
- Mastermind Brain and Terminal tool access;
- X fact-packet, writer, hard-gate, outbox, publisher, and metrics infrastructure;
- Signal Bus registration and a cross-system artifact graph;
- per-ticker fundamental and transcript contracts in the Terminal;
- a static transcript dataset bootstrap path;
- stage, season, sector, theme, and market-context systems.

### 9.2 Earnings intelligence

The current earnings qualitative engine is provider-agnostic and can score either:

- a transcript; or
- an EDGAR 8-K Item 2.02 earnings-release fallback.

It produces:

- sentiment;
- zero-to-ten performance;
- tone;
- positive and negative highlights;
- controlled tags;
- a summary;
- a source hash.

The recent in-flight spine work improves:

- R2 canonical history;
- fallback stores;
- provenance;
- source tier;
- latest observation;
- ready, degraded, stale, and empty health states;
- publication of the earnings history artifact.

This is useful groundwork, but it is not yet a Quartr-like corpus:

- no immutable multi-document event record;
- no stable source spans;
- no page-level filing or deck corpus;
- no word-level transcript timing;
- no source version and supersession model;
- no slide families;
- no peer Topics;
- no Mentioned By graph.

### 9.3 Terminal transcript system

**OBSERVED IN CONNECTED TERMINAL REPOSITORY**

The Terminal already has:

- a per-ticker mastermind.fund/v1 fundamentals contract;
- a mastermind.tx/v1 transcript contract;
- a transcript document strip;
- a Transcript Drawer;
- earnings, revenue, forecast, statements, and other tabs.

The current transcript schema contains:

- ticker;
- ID;
- period;
- date;
- title;
- speaker, role, and text segments.

It lacks:

- sentence and word timestamps;
- confidence;
- source versions;
- Q&A chapters;
- page or audio citations;
- full-corpus search;
- slide pages;
- event summaries;
- narrative history.

The bootstrap collector downloads a large DefeatBeta or Hugging Face transcript parquet, filters it locally, and emits up to eight quarters per symbol. It is useful for research prototyping, but commercial and public redistribution rights must be verified before it becomes a product corpus.

### 9.4 EDGAR and issuer sources

The current EDGAR collector captures Item 2.02 event metadata and filing timing. It does not yet preserve a complete, immutable document corpus with:

- original file hashes;
- amendments;
- exhibits;
- parsed pages and tables;
- source spans;
- rights and provenance class;
- parser version.

### 9.5 Research Vault

Research Vault already demonstrates:

- private R2 document storage;
- FTS5 search;
- weighted title, summary, and body fields;
- public catalog generation;
- per-report SEO pages;
- Brain retrieval;
- gated full-report access.

Reuse its corpus and search lessons, but do not put first-party company events into the same logical catalog as private third-party research. Their rights, semantics, freshness, correction model, and user expectations differ.

### 9.6 X Growth

The existing pipeline already has the right shape:

    fact packet -> writer -> hard gates -> outbox -> publisher -> metrics

The weak point is the event evidence source, not the publishing loop. The research lane can deterministically turn a report into posts or an article, but the research account or channel is currently dark and the free earnings-provider seam is weak.

### 9.7 Existing governance fence

The repository's standing research rulings matter:

- qualitative earnings and stage context remain display or confluence;
- Stage-2 plus earnings-call data is not a validated win-rate gate;
- language models do not originate signal scores, signal authority, or escalations;
- new topic, mention, and narrative artifacts must enter Signal Bus as context until separately tested.

The Quartr-inspired system must respect that fence.

---

## 10. Target architecture: Mastermind Corporate Intelligence Spine

### 10.1 Architectural principle

Every downstream surface must be a view of the same evidence graph:

    company identity
        -> event
        -> source document
        -> source span
        -> extracted fact or claim
        -> event digest
        -> derived views

No X writer, SEO writer, Terminal widget, or Brain answer should independently reinterpret raw filings when a canonical event digest exists.

### 10.2 Storage layers

**PROPOSED**

1. **Immutable source blobs**
   - R2;
   - original HTML, PDF, audio, transcript payload, and metadata;
   - content hash;
   - acquisition time;
   - license or rights class.

2. **Normalized metadata**
   - Postgres or compact Parquet initially;
   - company, event, document, availability, source version, parser state.

3. **Search**
   - FTS5 for MVP and controlled corpora;
   - Tantivy, OpenSearch, or another production inverted index as page volume and latency demand;
   - pgvector or a dedicated vector index only for semantic workloads.

4. **Derived artifacts**
   - versioned JSON or Parquet;
   - health record;
   - source-span citations;
   - event digest;
   - topic and mention artifacts;
   - Terminal compact payload.

5. **Presentation**
   - Macro Dashboard;
   - Mastermind Terminal;
   - Brain;
   - X Growth;
   - public event and ticker pages.

---

## 11. Canonical contracts

The following contracts are the center of the build. Field names may be adjusted to repo conventions, but their semantics should not be weakened.

### 11.1 company_identity.v1

    {
      "schema": "company_identity.v1",
      "company_id": "mm_company_00001234",
      "legal_name": "Example Corporation",
      "display_name": "Example",
      "status": "active",
      "listings": [
        {
          "exchange": "NASDAQ",
          "ticker": "EXM",
          "primary": true,
          "valid_from": "2021-01-01",
          "valid_to": null
        }
      ],
      "identifiers": {
        "cik": "0000000000",
        "isin": ["US0000000000"],
        "openfigi": ["BBG000000000"]
      },
      "classification": {
        "gics_sector": "Information Technology",
        "gics_industry": "Software"
      },
      "aliases": [
        {
          "value": "Example Cloud",
          "kind": "brand",
          "ambiguity": "low"
        }
      ],
      "provenance": [
        {
          "source": "sec",
          "retrieved_at": "2026-08-01T00:00:00Z"
        }
      ]
    }

### 11.2 company_event.v1

    {
      "schema": "company_event.v1",
      "event_id": "evt_exm_2026_q2_results",
      "company_id": "mm_company_00001234",
      "event_type": "earnings_results",
      "title": "Q2 2026 Results",
      "scheduled_at": "2026-08-04T20:30:00Z",
      "started_at": null,
      "ended_at": null,
      "status": "confirmed",
      "date_confidence": "issuer_confirmed",
      "fiscal": {
        "year": 2026,
        "period": "Q2"
      },
      "language": "en",
      "content_availability": {
        "press_release": "available",
        "filing": "available",
        "slides": "pending",
        "raw_transcript": "pending",
        "edited_transcript": "pending",
        "audio": "pending",
        "summary": "pending"
      },
      "source_refs": [],
      "supersedes_event_id": null,
      "content_hash": "sha256:..."
    }

### 11.3 source_document.v1

    {
      "schema": "source_document.v1",
      "document_id": "doc_exm_q2_2026_release",
      "company_id": "mm_company_00001234",
      "event_id": "evt_exm_2026_q2_results",
      "document_type": "earnings_release",
      "source_url": "https://...",
      "source_publisher": "issuer",
      "rights_class": "public_first_party",
      "retrieved_at": "2026-08-04T20:01:05Z",
      "published_at": "2026-08-04T20:00:00Z",
      "blob_uri": "r2://...",
      "blob_hash": "sha256:...",
      "mime_type": "application/pdf",
      "pages": 18,
      "parser_version": "corpdoc_parser_1.0.0",
      "text_layer_quality": 0.97,
      "ocr_applied_pages": [],
      "language": "en",
      "version": 1,
      "supersedes_document_id": null
    }

### 11.4 source_span.v1

    {
      "schema": "source_span.v1",
      "span_id": "span_doc_exm_q2_2026_release_p4_b17",
      "document_id": "doc_exm_q2_2026_release",
      "event_id": "evt_exm_2026_q2_results",
      "company_id": "mm_company_00001234",
      "locator": {
        "page": 4,
        "block": 17,
        "paragraph": null,
        "speaker": null,
        "start_ms": null,
        "end_ms": null,
        "coordinates": [72, 134, 518, 292]
      },
      "text": "Revenue increased ...",
      "text_hash": "sha256:...",
      "citation_label": "Q2 2026 earnings release, p. 4"
    }

### 11.5 transcript.v2

    {
      "schema": "transcript.v2",
      "transcript_id": "tx_exm_2026_q2_edited",
      "event_id": "evt_exm_2026_q2_results",
      "company_id": "mm_company_00001234",
      "transcript_type": "edited",
      "language": "en",
      "source_document_id": "doc_exm_q2_2026_tx",
      "version": 2,
      "supersedes_transcript_id": "tx_exm_2026_q2_raw",
      "speakers": [
        {
          "speaker_id": "spk_1",
          "name": "Jane Doe",
          "role": "Chief Executive Officer",
          "company_id": "mm_company_00001234"
        }
      ],
      "chapters": [
        {
          "chapter_id": "ch_prepared",
          "kind": "prepared_remarks",
          "title": "Prepared remarks",
          "start_ms": 0,
          "end_ms": 1740000
        },
        {
          "chapter_id": "ch_qa",
          "kind": "qa",
          "title": "Questions and answers",
          "start_ms": 1740000,
          "end_ms": 3540000
        }
      ],
      "paragraphs": [
        {
          "paragraph_id": "p_0001",
          "speaker_id": "spk_1",
          "chapter_id": "ch_prepared",
          "start_ms": 15400,
          "end_ms": 29800,
          "sentences": [
            {
              "sentence_id": "s_0001",
              "text": "We raised our full-year outlook.",
              "start_ms": 15400,
              "end_ms": 18450,
              "confidence": 0.98,
              "span_id": "span_tx_exm_q2_p1_s1"
            }
          ]
        }
      ]
    }

### 11.6 slide_page.v1

    {
      "schema": "slide_page.v1",
      "slide_page_id": "slide_exm_q2_2026_p12",
      "document_id": "doc_exm_q2_2026_deck",
      "event_id": "evt_exm_2026_q2_results",
      "company_id": "mm_company_00001234",
      "page": 12,
      "title": "Full-year outlook raised",
      "text": "...",
      "image_uri": "r2://...",
      "page_pdf_uri": "r2://...",
      "layout_features": {
        "table_count": 1,
        "chart_count": 0,
        "numeric_density": 0.21
      },
      "tags": [
        {
          "tag": "outlook",
          "probability": 0.96,
          "source": "model"
        }
      ],
      "perceptual_hash": "...",
      "embedding_ref": "emb_slide_exm_q2_2026_p12",
      "span_ids": ["span_slide_exm_q2_2026_p12_b1"]
    }

### 11.7 slide_family.v1

    {
      "schema": "slide_family.v1",
      "family_id": "sf_exm_full_year_outlook",
      "company_id": "mm_company_00001234",
      "label": "Full-year outlook",
      "primary_tag": "outlook",
      "members": [
        {
          "event_id": "evt_exm_2026_q2_results",
          "slide_page_id": "slide_exm_q2_2026_p12",
          "event_date": "2026-08-04"
        },
        {
          "event_id": "evt_exm_2026_q1_results",
          "slide_page_id": "slide_exm_q1_2026_p10",
          "event_date": "2026-05-05"
        }
      ],
      "match_evidence": {
        "visual_similarity": 0.91,
        "semantic_similarity": 0.94,
        "title_similarity": 0.88,
        "layout_similarity": 0.84
      },
      "review_state": "accepted",
      "change_facts": [
        {
          "field": "revenue_growth_outlook",
          "from": "8% to 10%",
          "to": "10% to 12%",
          "source_span_ids": ["...", "..."]
        }
      ]
    }

### 11.8 mention_edge.v1

    {
      "schema": "mention_edge.v1",
      "edge_id": "mention_src_to_target_...",
      "source_company_id": "mm_company_source",
      "mentioned_company_id": "mm_company_target",
      "event_id": "evt_source_2026_q2",
      "span_id": "span_...",
      "matched_alias": "Target Cloud",
      "entity_confidence": 0.97,
      "self_mention_excluded": false,
      "relation_hint": {
        "label": "supplier",
        "confidence": 0.71,
        "validated": false
      },
      "observed_at": "2026-07-29T13:44:00Z"
    }

### 11.9 topic_pulse.v1

    {
      "schema": "topic_pulse.v1",
      "topic_id": "topic_ai_capex_2026_q2",
      "label": "AI infrastructure capital spending",
      "universe": {
        "kind": "company_set",
        "company_ids": ["...", "..."]
      },
      "period": "2026-Q2",
      "measures": {
        "eligible_documents": 42,
        "documents_with_topic": 31,
        "raw_mentions": 214,
        "document_prevalence": 0.738,
        "token_normalized_frequency": 7.2,
        "company_breadth": 0.69,
        "new_company_breadth": 0.11,
        "semantic_cluster_size": 57,
        "novelty_vs_prior_period": 0.34
      },
      "rank_components": {
        "company_breadth": 0.69,
        "question_recurrence": 0.81,
        "follow_up_intensity": 0.58,
        "novelty": 0.34,
        "cross_company_disagreement": 0.46,
        "recency": 1.0
      },
      "source_span_ids": ["...", "..."],
      "authority": "context_only"
    }

### 11.10 company_event_digest.v1

    {
      "schema": "company_event_digest.v1",
      "digest_id": "digest_exm_2026_q2_v3",
      "event_id": "evt_exm_2026_q2_results",
      "company_id": "mm_company_00001234",
      "source_state": {
        "complete": true,
        "documents": [
          "earnings_release",
          "filing",
          "slides",
          "edited_transcript"
        ]
      },
      "facts": [],
      "guidance": [],
      "segment_changes": [],
      "management_claims": [],
      "analyst_questions": [],
      "narrative_deltas": [],
      "external_mentions": [],
      "summary": {
        "headline": "...",
        "bullets": [],
        "long_form": "...",
        "source_span_ids": []
      },
      "quality": {
        "citation_coverage": 1.0,
        "numeric_validation": "pass",
        "entity_validation": "pass",
        "contradiction_state": "none",
        "human_review": "not_required"
      },
      "versions": {
        "extractor": "corp_extract_1.0.0",
        "model": "...",
        "prompt": "event_digest_1.2.0",
        "validator": "digest_validator_1.0.0"
      },
      "correction_state": "current"
    }

### 11.11 corporate_intelligence_health.v1

    {
      "schema": "corporate_intelligence_health.v1",
      "generated_at": "2026-08-04T22:00:00Z",
      "state": "ready",
      "universe": {
        "companies": 300,
        "active_events_30d": 412
      },
      "freshness": {
        "median_event_lag_minutes": 17,
        "p95_event_lag_minutes": 63
      },
      "coverage": {
        "filings": 0.99,
        "releases": 0.97,
        "slides": 0.74,
        "transcripts": 0.68,
        "citation_complete_digests": 0.94
      },
      "failures": {
        "fetch": 3,
        "parse": 5,
        "identity": 1,
        "citation": 2
      },
      "alerts": []
    }

---

## 12. Ingestion and processing pipeline

### 12.1 Source priority

**PROPOSED**

1. SEC EDGAR and equivalent official regulators;
2. issuer investor-relations pages and feeds;
3. issuer-hosted presentations, releases, and reports;
4. licensed transcript or event providers;
5. permissibly licensed public datasets for research bootstrap only;
6. third-party mirrors only as explicit fallback with provenance.

### 12.2 Event lifecycle

    estimated
        -> issuer_confirmed
        -> in_progress
        -> completed
        -> content_partial
        -> content_complete
        -> corrected_or_superseded

Every transition must retain:

- timestamp;
- source;
- old and new value;
- actor or process;
- reason.

### 12.3 Document parsing

For HTML:

- preserve headings, paragraphs, tables, links, and exhibit boundaries;
- remove navigation and boilerplate deterministically;
- retain the original HTML and hash.

For PDF:

- use embedded text first;
- preserve page boundaries;
- preserve tables and layout boxes;
- calculate text-layer coverage and density;
- run OCR only on pages below a quality threshold;
- store OCR confidence and parser version;
- never replace the original file.

For slides:

- split every page;
- render stable images and page PDFs;
- extract title and body regions;
- detect tables and charts;
- calculate numeric density;
- classify tags;
- generate search text;
- create source spans with coordinates.

For transcripts:

- retain raw, live, and edited versions;
- map speakers to identities;
- preserve Q&A structure;
- store word or sentence timestamps where licensed and available;
- allow corrected versions to supersede, not erase, prior versions.

### 12.4 OCR gating

OCR should run when:

- embedded text is absent;
- visible-text coverage is materially below expected density;
- extraction produces high invalid-character rates;
- table or chart labels are otherwise unavailable.

OCR should not be the universal first step. It raises cost and introduces errors.

### 12.5 Search indexing

Index at multiple granularities:

- document;
- section;
- paragraph;
- Q&A exchange;
- slide page;
- transcript sentence;
- extracted table row where useful.

Each indexed unit carries:

- company ID;
- event ID;
- document ID;
- source-span ID;
- date and fiscal period;
- source type;
- speaker and role;
- industry;
- tags;
- language;
- rights class;
- correction state.

### 12.6 Embeddings

Do not embed everything by reflex. Embed:

- coherent transcript exchanges;
- filing sections;
- slide pages;
- normalized management claims;
- topic candidates.

Avoid embedding:

- duplicate boilerplate;
- navigation;
- repeated legal text unless specifically useful;
- every word-level span;
- obsolete duplicate versions except for controlled history.

Use content hashes so a source or chunk is never re-embedded without a parser or model change.

### 12.7 Corrections

Corrections are a first-class requirement:

- raw transcript replaced by edited transcript;
- revised earnings release;
- amended filing;
- restated financial;
- rescheduled event;
- corrected speaker;
- wrong company identity;
- incorrect slide-family match.

Downstream digests must record which source versions they used and be invalidated when a load-bearing source changes.

---

## 13. Mastermind product integration

### 13.1 Macro Dashboard

**PROPOSED**

Upgrade the existing Earnings Calls and Stage Analysis surfaces with:

- cited event summary;
- guidance change;
- segment changes;
- top analyst questions;
- prepared-versus-Q&A tone and claim differences;
- peer-topic breadth;
- source completeness and freshness;
- direct links to filings, slides, transcript, and source spans.

Keep it display and context. Do not turn qualitative output into an unvalidated trade gate.

Add a **Primary Source Search** surface as a sibling to Research Vault, not as a mixed corpus:

- same search interaction lessons;
- separate storage, rights, freshness, and permissions;
- company, industry, event, document, fiscal-period, and source filters;
- exact source citations;
- saved searches and alerts later.

Publish an additive, compact corporate-intelligence reference in per-ticker data:

    site/stockdata/<TICKER>.json

or a separate payload if size becomes material. Register all canonical artifacts and consumers in config/synapse.yml.

### 13.2 Mastermind Terminal

Do not duplicate ingestion in the Terminal. Macro Dashboard remains the source of truth.

Recommended additive contract:

    /data/<SYMBOL>.corp.json
    schema: mastermind.corp/v1

It should contain:

- recent event summaries;
- source availability;
- guidance deltas;
- key segment changes;
- peer topic references;
- Mentioned By edges;
- key slide and history references;
- transcript and filing search endpoints or compact indexes.

Terminal surface changes:

1. **Earnings tab**
   - event digest;
   - guidance delta;
   - segment table;
   - top questions;
   - source completeness.

2. **Statements**
   - direct filing and relevant slide links;
   - period and amendment state.

3. **Transcript Drawer v2**
   - search;
   - prepared remarks and Q&A chapters;
   - speaker filters;
   - timestamps;
   - source citations;
   - jump to audio if licensed.

4. **Corporate Intelligence or History subpanel**
   - narrative-change timeline;
   - Key Slides;
   - slide families;
   - commitments and status;
   - external mentions.

### 13.3 Mastermind Brain

Add four curated tools:

    search_company_sources(query, companies, document_types, date_range)

    get_company_event(company_id, event_id, include_sources)

    compare_company_narrative(company_id, from_event, to_event, dimensions)

    get_peer_topic_pulse(topic_or_query, universe, period)

Requirements:

- citations in every answer;
- rights-aware excerpts;
- no uncited numeric claim;
- clear distinction between source fact, extracted claim, and model synthesis;
- quota and latency budgets;
- no signal creation.

### 13.4 X Growth

Use company_event_digest.v1 as a fact-packet source for the existing publishing system.

One event can generate:

- immediate factual result card;
- management-change post;
- guidance-change post;
- peer-readthrough post;
- customer or supplier mention post;
- theme breadth post;
- short thread;
- weekly sector wrap;
- longer article.

Do not spray identical summaries across accounts. Route different evidence angles to distinct account personas, enforce event time-to-live, deduplicate claims, and preserve source links.

### 13.5 SEO and public pages

Build indexable pages only where the content adds original structured value:

- Tier A: complete event digest, narrative change, peer context, citations;
- Tier B: shorter event summary and primary-source links;
- Tier C: internal data only, no thin indexable page.

Suggested route families:

    /companies/<company-slug>
    /earnings/<company-slug>/<fiscal-period>
    /topics/<topic-slug>/<period>

Each indexed event page should include:

- original summary;
- structured result facts;
- guidance and prior-quarter comparison;
- cited source list;
- related companies or topics;
- publication and correction timestamps;
- canonical URL;
- JSON-LD where appropriate;
- CTA into the Terminal or paid research workflow.

Programmatic pages without unique evidence, comparison, or analysis are an SEO liability. Quartr's scale should not be copied before Mastermind has content quality.

### 13.6 Neural Web and Signal Bus

Publish:

- topic_pulse.v1;
- mention_edge.v1;
- company_event_digest.v1;
- narrative_delta artifacts;
- corporate_intelligence_health.v1.

Authority:

- display;
- context;
- confluence;
- research features for later testing.

They may confirm or explain an existing signal. They may not originate a signal score or escalation before a separate validation docket and gauntlet.

---

## 14. What Mastermind can do better than Quartr

Quartr's primary-source layer is broad and polished. Mastermind's opportunity is not to beat it at being a neutral document terminal. It is to connect narrative evidence to a much richer operating graph.

### 14.1 Narrative-to-market joins

For every topic or claim, Mastermind can join:

- price and relative strength;
- sector and thematic movement;
- breadth;
- flows;
- options;
- dark-pool or positioning context where available;
- earnings revisions;
- cycle and regime context;
- supplier and customer references;
- research evidence;
- X audience response.

### 14.2 Dislocation views

Examples:

- management language accelerates while relative strength lags;
- supplier mentions broaden before consensus estimates move;
- industry Q&A concern rises while the sector remains bid;
- companies stop showing a KPI before the market notices;
- customer references heat up while the named company underperforms;
- guidance improves but options or flow context diverges;
- a theme becomes broad in first-party commentary but narrow in market leadership.

These are hypotheses and context, not automatic trades. The system should expose both sides and invite validation.

### 14.3 Narrative accountability graph

Create a structured commitment record:

    claim
        -> source span
        -> target date or condition
        -> later references
        -> status: repeated, modified, achieved, missed, dropped, unverifiable

This makes History Mode useful beyond slides. It tracks management's promises across calls, filings, and presentations.

### 14.4 Distribution learning loop

Mastermind can measure:

- which evidence angles drive engagement;
- which accounts convert;
- which topics have durable interest;
- which event-page formats lead to Terminal use;
- which summaries are saved or queried in Brain.

Usage should improve routing and presentation, not rewrite source truth.

---

## 15. Build effort and cost

### 15.1 Feature-level engineering estimate

These are calendar-time ranges for focused work after basic repo orientation. They overlap and assume strong engineers with access to the existing Mastermind systems.

| Capability | Initial effort | Notes |
|---|---:|---|
| Calendar filters and sync | 1–2 engineer-weeks | UI is easy; event correctness is ongoing |
| Search over an existing transcript and filing corpus | 2–4 weeks | Corpus and citations must already be normalized |
| Cited event summaries and guidance delta | 3–5 weeks | Includes structured packet and validation |
| Timeline and Mentioned By | 3–5 weeks | High-precision identity and source spans required |
| Peer Topics over Q&A | 4–7 weeks | Requires chapters, clustering, evaluation |
| Slide ingestion, search, and Key Slide tags | 5–8 weeks | PDF edge cases and labeled set matter |
| History Mode families and change facts | 6–10 weeks | Ambiguity and quality review are substantial |
| Reliable 2,000-name ingestion and health | 8–16 weeks, overlapping | Source drift and retries dominate |
| Dashboard and Terminal integration | 3–6 weeks after data | Mostly additive UI and contracts |
| Live five-second audio and transcript | 12–24-plus months at scale | Vendor and operations problem; defer |

### 15.2 Practical delivery envelopes

**Golden MVP: 100 to 300 companies**

- two strong engineering or data people;
- 8 to 12 weeks;
- filings, releases, existing transcripts, citations, search, event digest;
- limited slide corpus;
- Terminal and Brain pilot;
- no global or live-call claim.

**Core production: roughly 2,000 U.S. and Canadian companies**

- three to five people;
- four to six calendar months;
- source monitoring, correction handling, production search, topic and mention layers, slide support;
- 0.75 to 1.5 ongoing full-time equivalents after launch.

**Quartr-scale parity**

- 15,000-plus companies;
- 65-plus markets;
- live events;
- complete audio, transcript, filings, slides, and corrections;
- 18 to 36 months;
- 10 to 20-plus staff plus content and data operations;
- material licenses and vendor relationships.

Even that estimate may understate enterprise sales, support, compliance, and regional source operations. Quartr's own 140-plus team is the strongest benchmark.

### 15.3 Infrastructure planning range

For an MVP or controlled U.S. universe:

- storage, parsing, search, queues, and monitoring: roughly $500 to $3,000 per month;
- model cost depends on event tier but is likely not the dominant line item.

For a broader production system:

- roughly $3,000 to $15,000 per month for infrastructure is a reasonable planning range before real-time audio and premium data;
- peak earnings-season compute and indexing require burst capacity;
- licensed transcripts, consensus estimates, audio rights, and global content can exceed infrastructure costs.

These are planning ranges, not vendor quotes.

### 15.4 Maintenance burden

Persistent work includes:

- issuer IR URL changes;
- SEC and regulator edge cases;
- duplicate and rescheduled events;
- amendments and corrections;
- fiscal calendars;
- timezones;
- PDF parser changes;
- scans and OCR;
- table extraction;
- transcript speaker mapping;
- missing audio;
- entity aliases and corporate actions;
- slide-family false matches;
- search relevance;
- topic drift;
- source rights;
- data retention;
- alert failures;
- public-page corrections.

A U.S.-core product needs roughly one dedicated ongoing engineer or data-operations equivalent. A global multi-market product needs a small permanent team.

---

## 16. Evaluation and quality gates

### 16.1 Golden corpus

Start with:

- 100 companies;
- 200 recent events;
- at least 1,000 slide pages;
- large-cap, small-cap, financial, industrial, technology, healthcare, and nonstandard fiscal-year examples;
- amended filing, restatement, missing deck, poor PDF, and transcript-correction cases.

### 16.2 Retrieval metrics

Measure:

- Recall@10 for exact fact and phrase queries;
- nDCG@10 for analyst-style questions;
- source-type filter correctness;
- company and period filter correctness;
- citation locator correctness;
- time-to-first-result;
- zero-result rate.

### 16.3 Digest metrics

Require:

- numeric accuracy of at least 99.5% on audited fields before public distribution;
- citation coverage of 100% for factual claims;
- source locator accuracy above 99%;
- no silent conflict resolution;
- correction propagation;
- fiscal-period accuracy;
- unit and currency accuracy;
- unsupported-claim rate near zero.

### 16.4 Mentioned By metrics

Track:

- entity precision;
- entity recall;
- self-mention exclusion;
- ambiguous alias false positives;
- relation-hint precision;
- source-link correctness.

Prioritize precision over recall initially.

### 16.5 Topics metrics

Use human-rated sets for:

- cluster coherence;
- cross-company breadth accuracy;
- duplicate-topic rate;
- label quality;
- cited-span representativeness;
- contradiction preservation;
- novelty correctness.

### 16.6 Slide metrics

For Key Slides:

- tag precision and recall;
- top-five relevance by tag;
- title extraction accuracy;
- OCR error rate.

For History Mode:

- pair precision;
- family purity;
- false merge rate;
- false split rate;
- correct chronological order;
- extracted numeric-change accuracy.

### 16.7 Product gates

Expand coverage only if:

- users repeatedly open source citations;
- Terminal or Brain query success improves;
- event summaries are used rather than ignored;
- retrieval quality remains stable;
- maintenance hours per 100 companies remain bounded;
- content derivatives improve X or SEO outcomes without duplication;
- corrections are fast and visible.

---

## 17. Phased build docket

### Phase 0 — Rights, benchmark, and golden corpus

**Duration:** 1–2 weeks

Deliver:

- optional Quartr Pro benchmark seat;
- contract and source-rights matrix;
- 100-company identity set;
- 200-event and 1,000-slide golden corpus;
- current Quartr feature screenshots and expected behaviors;
- frozen schema draft;
- retrieval and summary evaluation set;
- explicit no-scraping fence.

Exit gate:

- rights for each planned source understood;
- event and citation contracts approved;
- Quartr is treated as a benchmark, not a feed.

### Phase 1 — Evidence spine

**Duration:** 3–5 weeks

Deliver:

- company_identity.v1;
- company_event.v1;
- source_document.v1;
- source_span.v1;
- transcript.v2;
- immutable R2 source blobs;
- EDGAR and issuer-source adapters;
- parser and OCR quality state;
- correction and supersession model;
- corporate_intelligence_health.v1.

Exit gate:

- source spans survive reprocessing;
- duplicate event and amendment tests pass;
- every derived claim can cite a stable span.

### Phase 2 — Search and per-ticker intelligence

**Duration:** 3–5 weeks

Deliver:

- lexical search;
- source and period filters;
- transcript Q&A chapters;
- cited event digest;
- guidance delta;
- Terminal mastermind.corp/v1 pilot;
- Brain search_company_sources and get_company_event;
- Dashboard earnings-card integration.

Exit gate:

- audited retrieval and citation thresholds pass;
- no uncited public output;
- 100-company pilot is useful without manual rescue.

### Phase 3 — Narrative graph

**Duration:** 4–6 weeks

Deliver:

- mention_edge.v1;
- Timeline lexical measures;
- topic_pulse.v1;
- peer Q&A Topics;
- commitment and narrative-change tracking;
- compare_company_narrative and get_peer_topic_pulse Brain tools;
- Signal Bus context registration.

Exit gate:

- entity precision and topic coherence pass;
- context-only authority is enforced;
- narrative changes are evidence-backed.

### Phase 4 — Slides

**Duration:** 5–10 weeks

Deliver:

- slide_page.v1;
- page rendering and OCR;
- Slide Search;
- controlled Key Slide tags;
- slide_family.v1;
- History Mode viewer;
- extracted text and numeric change facts.

Exit gate:

- false-family merge rate acceptable;
- page citations reliable;
- high-value tags reach target precision.

### Phase 5 — Distribution and acquisition

**Duration:** 3–5 weeks

Deliver:

- canonical_story derivatives from event digests;
- X Growth fact-packet adapter;
- persona-specific post variants;
- Tier A and Tier B public event pages;
- ticker-page corporate-intelligence modules;
- alerts, saved filters, and calendar sync;
- conversion and engagement instrumentation.

Exit gate:

- no duplicate-account spray;
- public-page quality and corrections pass;
- conversion can be measured;
- content generation remains digest-first.

### Phase 6 — Scale and controlled bakeoff

Expand:

    100 -> 300 -> 1,000 -> roughly 2,000 companies

At each step compare:

- Mastermind output;
- Quartr benchmark output;
- analyst judgment;
- maintenance cost;
- source coverage;
- retrieval quality;
- user engagement.

Do not expand because the crawler can. Expand because the quality and economics hold.

---

## 18. What not to rebuild

### 18.1 Do not build a Quartr-shaped global data company by accident

Defer:

- 65-market coverage;
- universal live-event audio acquisition;
- five-second ASR SLA;
- every public-company event;
- every document language;
- full consensus-estimate normalization;
- a desktop clone;
- dozens of low-level agent tools;
- generic team collaboration before evidence quality.

### 18.2 Do not use the model as the database

Never ask an LLM to:

- remember the event;
- infer fiscal period from prose when metadata exists;
- calculate mention counts;
- decide the source identity;
- reconcile units without deterministic checks;
- create a signal score;
- fill missing evidence with plausible language.

### 18.3 Do not mix corpora with incompatible rights

Keep separate:

- public first-party corporate documents;
- licensed transcripts;
- private Research Vault reports;
- Quartr benchmark access;
- public SEO derivatives.

The retrieval layer may federate them with permissions. The storage and publication policies must remain explicit.

### 18.4 Do not build thin SEO pages at global scale

Index only pages with:

- original structured evidence;
- meaningful comparison;
- citations;
- correction state;
- user value.

### 18.5 Do not confuse narrative heat with a trade signal

A surge in mentions can be:

- genuine adoption;
- controversy;
- risk disclosure;
- boilerplate;
- a one-time industry event;
- management storytelling after price has already moved.

Narrative evidence is a context organ. Validation decides whether it has predictive value.

---

## 19. Final recommendation

### The strategic answer

Yes, Mastermind should absorb the core idea behind Quartr as a foundational feature—but the feature is not “AI earnings articles.” It is a source-addressable corporate-intelligence spine.

Build:

- stable company and event identity;
- immutable documents and transcripts;
- page and timestamp citations;
- cited event digests;
- cross-period narrative change;
- peer Q&A Topics;
- Mentioned By;
- Timeline;
- slide search and history after the text layer works;
- one-to-many distribution into Terminal, Brain, Dashboard, SEO, and X.

Do not build:

- global live-call parity;
- a cosmetic Quartr clone;
- a content farm;
- a Pro-seat scraper;
- an LLM-driven signal authority.

### Why this belongs in Mastermind

It gives Mastermind a missing form of memory:

- what management promised;
- how the story changed;
- which peers are discussing the same constraint;
- who is mentioning whom;
- which themes are broadening in first-party evidence;
- whether market behavior agrees or diverges;
- the exact source behind every claim.

That strengthens per-ticker dossiers, earnings analysis, sector and theme intelligence, Brain answers, X content, and SEO without creating five independent research systems.

### The narrow first bet

Ship a 100-company, cited-event pilot:

1. evidence spine;
2. filing and transcript search;
3. source-grounded event digest;
4. guidance and narrative delta;
5. Terminal integration;
6. X fact packets;
7. a small set of high-quality public event pages.

Then add Mentioned By and peer Topics. Add slides only after the text and citation machinery has earned trust.

### Quartr subscription decision

If the reported approximately $500 monthly annual quote is acceptable, one Pro seat is a sensible benchmark and analyst-productivity purchase. It is cheap relative to building the wrong workflow.

The seat should be documented internally as:

- human use only;
- no scraping;
- no corpus population;
- no automated model training or evaluation on Quartr data;
- no competing-feature data extraction.

If Quartr API becomes attractive, negotiate a purpose-built Order. Do not rely on standard terms or verbal assurances.

### Bottom line

The frontend is reproducible. The useful AI workflows are reproducible. The durable evidence graph is difficult but worth building. The global real-time data operation is Quartr's moat and is not worth copying now.

Mastermind can win by being narrower, more source-rigorous, more connected to market context, and dramatically better at turning one verified corporate event into many non-duplicative intelligence and distribution products.

---

## 20. Source ledger

### Official Quartr product and company pages

- https://quartr.com/products/quartr-pro
- https://quartr.com/products/quartr-api
- https://quartr.com/pricing
- https://quartr.com/about
- https://quartr.com/customers
- https://quartr.com/newsroom
- https://quartr.com/newsroom/press-release/quartr-raises-15m-to-extend-its-global-leadership-in-first-party-ir-data
- https://quartr.com/newsroom/press-release/quartr-accelerates-global-growth-with-new-offices-in-new-york-and-dublin-strategic-hires-and-4x-arr-growth
- https://quartr.com/companies/apple-inc_4742
- https://quartr.com/events/evolv-technologies-evlv-investor-day-2026_oCLFZf1b

### Official feature articles supplied for review

- https://quartr.com/insights/investor-relations/5-features-that-make-quartr-pro-the-best-software-for-ir
- https://quartr.com/insights/investor-relations/best-new-quartr-pro-features-use-cases
- https://quartr.com/insights/investor-relations/slide-search-scan-specific-mentions-in-presentations
- https://quartr.com/insights/investor-relations/timeline-track-the-frequency-of-mentions-over-time
- https://quartr.com/insights/investor-relations/topics-leveraging-ai-to-streamline-industry-and-company-insights
- https://quartr.com/insights/investor-relations/history-mode-tracing-corporate-narratives
- https://quartr.com/insights/investor-relations/mentioned-by-keep-track-of-company-mentions
- https://quartr.com/insights/investor-relations/from-analyst-forecasts-to-financial-segment-data
- https://quartr.com/insights/investor-relations/master-search-the-capital-markets-in-one-search-engine
- https://quartr.com/insights/investor-relations/key-slides-unlocking-company-narratives
- https://quartr.com/insights/investor-relations/quartr-earnings-calendar-customized-with-seamless-sync

### Official documentation and terms

- https://quartr.com/docs/llms.txt
- https://mcp.quartr.com/docs
- https://a.storyblok.com/f/182663/x/65c8d49237/quartr-pro-standard-subscription-terms-incl-dpa-us-2026_1.pdf
- https://a.storyblok.com/f/182663/x/d7e500b281/quartr-api-standard-subscription-terms-internal-use-us-2026_1.pdf

### Public implementation surfaces

- https://web.quartr.com
- https://web.quartr.com/api/health
- public JavaScript bundles and source maps served by web.quartr.com
- Quartr sitemap index and child sitemaps

### Supplied product media

- /Users/chriswong/Downloads/_pro-earnings-calendar (2).webm
- /Users/chriswong/Downloads/_pro-history_mode2.mp4
- /Users/chriswong/Downloads/filters_quality(85).webp
- /Users/chriswong/Downloads/filters_quality(85) (1).webp

### Mastermind repository evidence

- AGENTS.md
- CLAUDE.md
- docs/ACTIVE_BUILD_MAP.md
- research/DO_NOT_REBUILD.md
- research/JODIE_STRUCT_ENGINE_TEARDOWN_AND_MASTERMIND_INTEGRATION_DOCKET_2026-07-31.md
- engine/earnings_qual.py
- engine/stock_dossier.py
- collectors/edgar_earnings_8k.py
- collectors/finnhub_transcripts.py
- engine/brain_gateway.py
- scripts/build_research_pages.py
- config/synapse.yml
- connected Mastermind Terminal transcript, fundamentals, ingestion, and UI contracts

### Evidence caution

Quartr's public pages and documentation can change. Counts, feature names, release versions, service-level claims, and contract language in this memo reflect the 2026-08-01 research snapshot. Any procurement or production dependency should be reverified against the live Order and current official documentation.
