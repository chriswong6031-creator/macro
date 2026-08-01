# EarningsCall.ai Teardown and Mastermind Integration Docket

**Canonical deliverable:** this file

**Research snapshot:** 2026-08-01, America/Vancouver

**Decision:** rebuild the useful product primitives inside the Company Event Spine; do not clone EarningsCall.ai as a separate stack, do not ingest or republish its corpus, and do not reproduce its analysis architecture one prompt at a time.

## Executive verdict

EarningsCall.ai is much easier to reproduce than its polished surface suggests.

It is a compact, apparently solo-operated application with a sensible serverless transcript pipeline, a conventional Next.js product, a surprisingly large programmatic-SEO corpus, and a series of LLM prompts wrapped around each transcript. Its core is not a secret quantitative engine. There is no public evidence of proprietary weighting formulas, trained financial models, or a durable scoring moat. The verified stack is:

1. Poll transcript and earnings-data vendors.
2. Normalize a call into one Postgres row and archive the vendor JSON.
3. Full-text index the transcript.
4. Ask an LLM for one of several narrative analysis types.
5. Persist or cache the answer and stream it on first generation.
6. Reuse calls for chat, cross-quarter analysis, peer comparison, keyword alerts, weekly recaps, and a tariff-topic view.
7. Expose transcript and analysis URLs at large scale to acquire organic search traffic.
8. Convert researchers into a seven-day trial and one paid plan.

That composition is commercially clever. It is not technically exotic.

The important distinction is between a thin clone and a trustworthy Mastermind-grade system:

| Build target | Difficulty | Credible effort | Verdict |
|---|---:|---:|---|
| Visual and interaction parity | Easy | 1–3 frontend engineer-weeks | Do not build separately |
| Transcript ingestion, search and call pages | Moderate | 3–6 engineer-weeks after source rights are settled | Build into Event Spine |
| Narrative analysis parity | Easy to moderate | 2–4 engineer-weeks | Build as views over one extraction |
| Historical and peer chat | Moderate | 2–4 engineer-weeks | Build with cited retrieval |
| Weekly and tariff surfaces | Easy to imitate, hard to trust | 2–4 weeks plus validation | Build a stronger version |
| Complete, timely, rights-safe US coverage | Hard | data contract plus 6–12 weeks of hardening | Mandatory foundation |
| Source-cited, correction-safe intelligence for Neural Web and public content | Hard and valuable | 3–5 months for a robust release | Core feature |

The system should be absorbed, not cloned:

    one governed earnings event
      -> ticker dossier
      -> Stage Analysis
      -> Terminal transcript and comparison
      -> theme and relationship evidence
      -> Neural Web context
      -> canonical research story
      -> differentiated X and short-form derivatives

The valuable upgrade is not prettier prose. It is claim-level receipts, deterministic numbers, point-in-time state, source rights, correction replay, and a single structured event object that every Mastermind surface can consume.

### Scorecard

| Question | Assessment |
|---|---:|
| Is the product useful? | 8/10 |
| Is its observable engine difficult to reproduce? | 4/10 |
| Is its frontend difficult to reproduce? | 2/10 |
| Is its transcript corpus difficult to operate legally and reliably? | 8/10 |
| Is its LLM prose expensive? | 2/10 |
| Is its current output trustworthy enough for decision authority? | 4/10 |
| Is the SEO and conversion architecture worth adopting? | 8/10 |
| Should it become a separate Mastermind clone? | No |
| Should its primitives become a core Company Event Spine branch? | Yes |

## Evidence boundary

This teardown used:

- public server-rendered pages;
- public Next.js chunks and React Server Component payloads;
- public same-origin API responses and response headers;
- EarningsCall.ai's own engineering article, FAQ, pricing, terms and privacy policy;
- its sitemap, robots policy, transcript, analysis, comparison, weekly and tariff surfaces;
- public company and founder profiles;
- primary Apple SEC filings for a representative fact check.

The backend repository is private. Exact prompts, current model identifier, model parameters, database schema, vendor agreements, queue topology and production logs were not exposed. Those are not presented as verified.

An already-authenticated EarningsCall.ai browser session was not available in this environment. No paid access was bypassed and no credentials from another service were reused. Public pages and APIs nevertheless exposed enough behavior to reconstruct the product contract in considerable detail.

The labels used below are:

- **Verified:** directly stated by EarningsCall.ai, visible in shipped code, returned by its API, or reproduced from a primary source.
- **Strong inference:** the observed client and response behavior largely determines the backend shape, but the private implementation was not seen.
- **Unknown:** no reliable public evidence.

## What the product actually sells

EarningsCall.ai sells time compression, not an investment oracle.

The current product promise is:

- avoid reading long transcripts;
- receive a new call in less than roughly one hour;
- generate highlights, summaries, guidance, strategic updates, risks and Q&A;
- ask questions of one call;
- compare several companies;
- analyze several quarters;
- search and monitor keywords across the market;
- receive watchlist and keyword alerts;
- inspect weekly and topic-level market intelligence.

Its [FAQ](https://www.earningscall.ai/faq) says it collects calls for more than 5,000 NYSE and Nasdaq companies from multiple sources, analyzes them with GPT-4, processes new calls in less than one hour, and provides the past eight quarters in the main product. “GPT-4” is a marketing-level claim, not a verifiable current model version. The [Terms](https://www.earningscall.ai/terms) confirm that OpenAI APIs are used.

### Current pricing

The live server-rendered pricing payload at inspection time contained:

- $25 per month;
- $228 per year, displayed as $19 per month billed yearly;
- a seven-day free trial;
- one Pro plan.

The crawlable text cached by some search surfaces still showed an older $29 monthly price. The live Stripe product payload and rendered site are the stronger current evidence. The same server payload also retained legacy “EarningsDigest Full Access” products at much higher prices, but the current client selects the EarningsCall.ai products.

The annual economics are attractive for a small team:

| Paid users | Annual-plan gross revenue |
|---:|---:|
| 100 | $22,800 |
| 500 | $114,000 |
| 1,000 | $228,000 |
| 5,000 | $1.14 million |

These are simple price multiples, not an estimate of actual customers or revenue. No public evidence found in this run establishes traffic, conversion, paid-user count, retention or revenue.

### The likely funnel

    free transcript and ticker pages
        + earnings calendar
        + blog use-case pages
        + weekly intelligence
        + tariff tracker
        + social distribution
                    |
                    v
             product discovery
                    |
                    v
        free highlights or transcript
                    |
                    v
             seven-day trial
                    |
                    v
          $25 monthly / $228 annual
                    |
                    v
       watchlists, alerts, monitoring and chat

The old EarningsDigest social handles remain embedded across X, LinkedIn, TikTok, Reddit, Instagram, YouTube and Threads. The founder's public launch history reinforces the product-led strategy: Mark Zhong said the first version took about one month to build in May 2023, and a $125 launch-ad experiment produced more than 1,000 users and more than 100 signups. The current [LinkedIn company page](https://www.linkedin.com/company/earningsdigest) describes a New York financial-services company founded in 2023 with one employee.

This is meaningful evidence about build difficulty. A capable solo engineer can make the thin product quickly. It is not evidence that a solo engineer has solved institutional-grade provenance, data rights, corrections or validation.

## Verified transcript and search architecture

EarningsCall.ai disclosed more of its backend than most competitors in its November 2025 article, [How We Built Our Earnings Call Transcript Search Stack](https://www.earningscall.ai/blog/How-We-Built-Our-Earnings-Call-Transcript-Search-Stack).

### Ingestion path

The published flow is:

    earnings calendar and transcript vendors
                    |
                    v
       external Lambda polls for completed calls
                    |
                    v
       authenticated Next.js cron/webhook endpoint
                    |
                    v
       updateTranscriptOfCalendar
                    |
                    v
        transcript fetched through vendor SDK
                    |
          +---------+----------+
          |                    |
          v                    v
    normalized Postgres     raw vendor JSON
     EarningsCall row       in Vercel Blob
          |
          v
       ParadeDB full-text index

Verified implementation details from that article:

- the service layer is under src/lib/services/earnings.ts;
- the listener is an external Lambda;
- a Next.js cron route delegates to updateTranscriptOfCalendar;
- a package described as the earningscall SDK fetches one source;
- helpers named putFMPTranscript and putEarningsCallTranscript mirror raw payloads;
- normalized records live in Neon Postgres through Prisma;
- the raw object key is transcripts/symbol-year-quarter-ec.json;
- the unique database key is symbol, year and quarter;
- ParadeDB provides full-text matching, relevance score and highlighted snippets;
- a typical 8,000–12,000-word call takes about four seconds to ingest and index;
- Neon compute and storage were said to cost less than $50 per month for approximately 15,000 transcripts, with Vercel Blob adding pennies.

The FMP helper name, FMP-shaped market-data responses and fallback company images hosted by Financial Modeling Prep are strong evidence that Financial Modeling Prep is at least one market-data or transcript source. A second source is implied by the generic earningscall SDK. The exact provider, contractual scope, fallback priority and redistribution rights are unknown.

### What is stored

The public transcript endpoint returns:

- internal ID;
- symbol;
- fiscal quarter;
- fiscal year;
- company name;
- call date;
- exchange;
- a plain normalized transcript body.

The public AAPL Q3 2026 transcript contained approximately 49,500 characters and preserved speaker labels and turns. The architecture article says the raw JSON is retained separately so the system can replay normalization without re-fetching the vendor.

This is a good pattern. Mastermind should retain it with stronger provenance:

- immutable raw object;
- normalized paragraph and speaker-turn table;
- content hash;
- vendor and source ID;
- license and display-rights policy;
- revision and correction chain;
- transcript availability time;
- call start and end time;
- fiscal-period resolution;
- exact mapping to the earnings release, 8-K and 10-Q.

### Search

The search endpoint is described as a thin authenticated route over ParadeDB. Search keeps symbol, quarter and exchange metadata beside full text, then returns ranked highlighted excerpts with pagination.

This is a pragmatic design. Hybrid embeddings are not necessary for exact monitoring queries such as “tariff,” “inventory,” “pricing,” or “data center.” The site's own roadmap described embeddings and inline entities as future work. Mastermind should use:

- BM25/full-text search for exact and lexical monitoring;
- entity-normalized tags for product, geography, customer and competitor;
- embeddings only for semantic recall;
- reciprocal-rank or weighted fusion;
- exact paragraph receipts in every result.

## Public API and frontend contract

The shipped client centralizes a same-origin JSON API. Its HTTP client uses credentials and a ten-second timeout for ordinary requests. Long analyses and chats use native streaming fetches.

### Frontend implementation

The public frontend is a conventional Vercel-hosted Next.js App Router application:

- React Server Component payloads are embedded in initial HTML;
- route-specific chunks are emitted for pricing, FAQ, transcript, analysis, comparison, weekly intelligence and the tariff tracker;
- utility CSS handles most layout, with Ant Design components and CSS-in-JS also present;
- Next Image serves logos and company imagery;
- Clerk provides identity;
- Stripe products and prices are passed into the pricing client;
- Hotjar and Google Analytics provide product analytics;
- the application uses server rendering for transcript, weekly and tariff acquisition pages;
- the analysis workspace hydrates on the client and fetches or streams its answer.

The public Clerk payload exposed an older Clerk Next.js SDK version, but a package version is not strategically useful and can change independently of the product. No public source maps or private server implementation were found. EarningsCall.ai's engineering article, rather than the browser bundle, is what exposed the backend file and helper names.

The frontend has little defensible complexity:

- ticker search;
- tab or menu selection;
- loading and streaming states;
- Markdown-like narrative rendering;
- transcript text;
- metric header cards;
- peer selector;
- chat history;
- paywall presentation;
- responsive navigation.

Mastermind already has equivalent or richer primitives. Rebuilding this shell as a separate application would create duplicate authentication, billing, ticker identity, watchlist and dossier systems for no strategic gain.

### Observed endpoint families

Company and analysis:

- /api/company/query
- /api/company/analyze
- /api/company/analyze/history
- /api/company/analyze/compare
- /api/company/chat

Earnings:

- /api/company/earnings/calendar
- /api/company/earnings/calendars
- /api/company/earnings/history
- /api/company/earnings/latest
- /api/company/earnings/detail
- /api/company/earnings/summary
- /api/company/earnings/dates
- /api/company/earnings/redirect

Market context:

- /api/stock/calendar
- /api/stock/historical-price
- /api/stock/key-metrics
- /api/stock/peers
- /api/stock/profile
- /api/stock/quotes

Account and commerce:

- profile, watchlist, note and search-history endpoints;
- user subscription and source endpoints;
- Stripe checkout/session endpoints;
- log, contact and feedback endpoints.

Representative public responses showed:

- ticker query results with symbol, name, currency and exchange;
- earnings history with actual and estimated EPS/revenue, event time, report date, fiscal ending, year and quarter;
- full transcript content;
- an FMP-shaped company profile with CIK, industry, sector, beta, market capitalization and image URL;
- calendar results using the same earnings-metric shape.

The site advertises a JSON dataset at /api/earnings-data in global structured metadata. That URL returned a “Data Not Found” HTML page rather than the advertised dataset.

### Exact analysis types

The shipped client enum contains:

- ConversationFlag
- Highlights
- Summary
- Guidance
- Tweet
- StrategicUpdates
- SentimentAnalysis
- RiskAnalysis
- QASummary
- HistoryEarnings
- EarningsEvolver
- Unconventional
- TariffImpact

The current visible menu presents:

- Highlights and Takeaways;
- Full Summary;
- Guidance and Outlook;
- Strategic Updates;
- Q&A Summary;
- Unconventional Findings;
- Risk Analysis;
- Historical Earnings;
- Earnings Call Trends;
- Tariff Impacts.

Tweet and SentimentAnalysis remain in the client contract but are absent from the visible current menu, suggesting legacy or hidden features. Highlights is marked free in the client; the other visible analyses are marked Pro.

There is no public evidence of a numerical formula behind any of these types. They are best understood as different prompts or renderers over the same transcript, plus market metrics for surprise calculations. “Sentiment Analysis” is an analysis label, not evidence of a calibrated sentiment model.

### What “analysis and weighting” most likely means

The observable product supports the following reconstruction:

| View | Verified inputs | Likely operation | Formula evidence |
|---|---|---|---|
| Highlights | one transcript and event metrics | select material statements and compress | none |
| Full Summary | transcript, actuals and estimates | broad narrative synthesis | none |
| Guidance | transcript | extract forward ranges, assumptions and qualifiers | none |
| Strategic Updates | transcript | classify products, capex, markets and initiatives | none |
| Q&A Summary | transcript Q&A | cluster analyst concerns and management answers | none |
| Risk Analysis | transcript | identify constraints, uncertainty and negative language | none |
| Unconventional | transcript | novelty-oriented prompt looking for non-obvious statements | none |
| Sentiment | transcript | narrative or label classification | no exposed calibration |
| Historical / Evolver | several calls | compare summaries or transcripts across quarters | none |
| Tariff Impact | transcript plus eligibility data | topic relevance, sentiment and impact extraction | none |
| Peer comparison | selected company events | cross-company narrative contrast | none |
| Chat | transcript or retrieved context plus history | question answering | none |

A good prompt could implicitly prioritize:

- size of a reported change;
- deviation from consensus;
- explicit forward guidance;
- novelty versus prior quarters;
- repetition across prepared remarks and Q&A;
- analyst challenge or management evasion;
- specificity and certainty;
- cross-company recurrence.

Those are a plausible editorial rubric, not recovered EarningsCall.ai weights. Nothing in the shipped code or methodology justifies reconstructing a hidden score.

### Single-call analysis workflow

The client sends:

    POST /api/company/analyze

    {
      q: symbol,
      type: analysis type,
      year: fiscal year,
      quarter: fiscal quarter
    }

Observed behavior:

1. A ticker or type change aborts the prior request.
2. A JSON response with success code renders stored content immediately.
3. A special “processing” code shows a waiting state and refreshes after two minutes.
4. Otherwise the browser reads response chunks and appends text while the model is generating.
5. The UI says a new analysis can take up to two minutes.

This is strong evidence of a persisted or cached answer with an on-demand generation fallback. The exact cache table and key were not visible. A likely private key is symbol, year, quarter and analysis type. A safer Mastermind key must also include:

- normalized transcript content hash;
- earnings-metric snapshot hash;
- schema version;
- extraction prompt version;
- model and parameters;
- validator version;
- analysis renderer version.

Without those dimensions, a changed source or prompt can silently serve an obsolete answer.

### Chat

Single-call chat sends:

    POST /api/company/chat

    {
      q: symbol,
      type: analysis type,
      year: fiscal year,
      quarter: fiscal quarter,
      message: user question,
      history: prior turns
    }

The response is a raw text stream. The browser accumulates the assistant message and keeps the visible conversation in local state. Suggested questions ask about guidance, risks, EPS and revenue surprises, and the Q&A section.

The privacy policy says chats and conversations are not retained. That claim could not be independently audited.

No public client evidence showed transcript retrieval, source-span citations, RAG chunk selection or token budgeting. A full transcript may be sent on every turn, or the server may retrieve sections. Exact behavior is unknown.

### Cross-quarter analysis

The client loads up to eight historical events and displays a smaller recent set. Its history analysis request contains:

    {
      q: symbol,
      dates: [{year, quarter}, ...],
      message: question,
      history: prior turns
    }

Suggested questions cover trends over four calls, changes in management focus, dividend policy and financial metrics.

### Peer comparison

The interface permits one base company and up to three peers. It first loads a calendar/metric record for each company, then sends:

    {
      data: [latest company calendar records]
    }

Follow-up questions add message and history. Responses stream in the same way as single-call analysis.

The private server must resolve each symbol/year/quarter in the submitted metric rows back to a transcript. The exact comparison prompt and weighting are unknown. There is no evidence of a quantitative peer score.

## Caching, generation and entitlement assessment

### What is verified

- A representative precomputed analysis returned JSON immediately.
- The response carried public, revalidation-oriented cache headers but was a Vercel cache miss.
- A first-generation path can stream text.
- An in-progress result asks the client to wait two minutes.
- transcript and analysis HTML pages carried private/no-store-style headers and Vercel cache misses during inspection.
- the server-rendered transcript page contained the full transcript;
- the server-rendered analysis page contained mostly a loading shell, with analysis arriving client-side.

### What is inferred

The likely flow is:

    request analysis
        -> look up stored result
        -> return JSON if present
        -> return processing state if another job owns generation
        -> otherwise start model call
        -> stream text
        -> persist final result

This is efficient for a small paid product because expensive views are generated only when first requested. It also explains why all ten analysis types do not need to be precomputed for every transcript.

### Security and cost-control finding

A very small, non-destructive public sample found that at least one client-marked premium analysis and one AI chat response were returned without an authenticated subscription. This indicates that sampled entitlements were either enforced only in the client or absent on those server routes at inspection time.

This is not a feature to copy. It creates:

- paid-content leakage;
- unauthenticated model-cost exposure;
- scraping risk;
- denial-of-wallet risk;
- inconsistent product state.

Mastermind must enforce on the server:

- authentication;
- subscription entitlement;
- per-user and per-IP rate limits;
- concurrent-generation limits;
- idempotency keys;
- maximum history and prompt size;
- queue budgets;
- abuse and anomaly alarms.

## Weekly Earnings Intelligence

The weekly product is more revealing than the individual summaries because it exposes the system's aggregate schema.

A representative week page, [July 20–24, 2026](https://www.earningscall.ai/weekly-earnings-intelligence/2026-07-20), was fully server rendered and had Article structured data. Its initial object contained:

- week start and date range;
- analyzed stock symbols;
- total stock count;
- overview;
- top insights with description, companies and impact;
- trends with direction, evidence, sectors and implications;
- surprises with expectation, reality and market reaction;
- most-mentioned keywords with frequency, context, sentiment and key quotes;
- sector analyses with key players, trends and outlook;
- market sentiment and rationale;
- key numbers with context and significance;
- notable quotes with company, symbol and speaker;
- generation timestamp.

The observed page analyzed 20 symbols and was generated on the Sunday after the week. It included both GOOG and GOOGL, which are two share classes of the same issuer and effectively duplicate one call. This shows that issuer normalization is not applied before aggregation.

### Likely generation path

The most economical explanation is:

    weekly call set
        -> per-call summaries or extracted fact packets
        -> one aggregate structured prompt
        -> stored weekly JSON object
        -> server-rendered page and Article metadata

There is no need to send 20 full transcripts into one expensive context if compact per-call packets already exist. The structured and rounded nature of the output strongly suggests LLM synthesis into a predefined schema.

### Verified quality failures

The weekly page looked polished but failed receipt-level checks:

1. **Synthetic text presented as quotation.** Three “notable quotes” and keyword “key quotes” were searched verbatim in the corresponding stored transcripts. The exact sentences were absent. The page had turned thematic paraphrases into quotation-marked, CEO-attributed statements.
2. **Keyword counts did not reproduce.** The page displayed AI 200, Spectrum 120 and Capacity 180. Counting those exact words across the latest calls of its 20 listed symbols produced AI 272, Spectrum 33 and Capacity 155. Minor tokenization cannot explain the Spectrum gap. The values are at best opaque approximations and at worst model-invented round numbers.
3. **Duplicate issuer.** GOOG and GOOGL caused the same Alphabet event to contribute twice.
4. **Formatting defect.** The stored key-number value for backlog contained a doubled dollar sign.
5. **Mixed identifiers.** Some arrays use ticker symbols, some use company names, and some mix both.
6. **No receipts.** Key numbers, surprises and cross-company trends have no source-call or paragraph references.

This is the clearest reason not to imitate its article factory directly. The prose is good enough to persuade a reader and insufficiently grounded to audit. Mastermind's advantage should be that quotation marks are mechanically impossible unless the exact text matches a versioned source span.

## Tariff Impact Tracker

The [Tariff Impact Tracker](https://www.earningscall.ai/tariff-impact-tracker-earnings-call) is a strong product idea and a useful preview of topic-materialized views.

The page says it tracks NYSE and Nasdaq companies above $10 billion in market capitalization from April 2, 2025. At inspection time it exposed 204 paginated result pages, with ten cards on the first page.

Each card contains:

- company and symbol;
- event date;
- industry;
- region;
- positive, neutral or negative sentiment;
- one italicized transcript excerpt;
- one or more typed impact statements;
- a link to the transcript.

Observed impact types included:

- Revenue Impact;
- Cost Impact;
- Operations;
- Guidance Impact;
- Financial Impact;
- Supply Chain.

The analysis enum contains TariffImpact, and the cards closely match a structured output from that analysis. The likely implementation is:

    new transcript
        -> market-cap eligibility filter
        -> tariff/topic relevance test
        -> structured TariffImpact extraction
        -> stored card
        -> server-side paginated query

No weighting formula is exposed. Sentiment and impact categories appear to be prompt-based labels.

The surface is valuable because it converts one transcript corpus into a persistent thematic feed. It is also noisy:

- some chosen excerpts do not themselves mention tariffs;
- one Brookfield card used data-center transportation demand as trade context without a visible tariff receipt;
- one Rivian excerpt described vehicle-launch complexity while the card's impact text discussed a separate tariff refund;
- the card does not distinguish verbatim excerpt evidence from model-authored causal interpretation.

Mastermind should generalize this pattern into governed topic monitors:

- tariffs and trade;
- AI capex;
- power and grid;
- data-center demand;
- pricing and promotions;
- inventory and channel;
- labor and headcount;
- China exposure;
- defense and government demand;
- supply constraints;
- credit and consumer stress.

Every card should retain inclusion rule, exclusion checks, exact span, source call, model confidence, human or machine validation state, and event-to-theme edge.

## Representative fact check: Apple Q3 2026

The public AAPL full-summary response was checked against Apple's primary filings:

- [Q3 2026 earnings-release exhibit](https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/a8-kex991q3202606272026.htm);
- [Q3 2026 Form 10-Q](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm);
- [April 2026 CEO transition Form 8-K](https://www.sec.gov/Archives/edgar/data/320193/000114036126015711/ef20071035_8k.htm).

### Claims that reproduced

| EarningsCall.ai claim | Primary-source check |
|---|---|
| Revenue $109.42 billion, up 16% | 10-Q and exhibit: $109.417 billion versus $94.036 billion, 16.36% |
| iPhone $54.3 billion, up 22% | $54.252 billion versus $44.582 billion, 21.69% |
| Mac $10.4 billion, up 29% | $10.352 billion versus $8.046 billion, 28.66% |
| Services $30.7 billion, up 12% | $30.739 billion versus $27.423 billion, 12.09% |
| Diluted EPS $2.02 | Exhibit and 10-Q: $2.02 |
| $147 billion cash position | Cash and marketable securities total $146.517 billion, which rounds to $147 billion |
| Tim Cook transition and John Ternus succession | Apple's April 20 Form 8-K confirms the September 1 transition |

The summary's September-quarter 9–11% revenue-growth guidance, 47–48% gross-margin guidance and $33 billion capital return are present in the transcript served by EarningsCall.ai. They are call-content claims, not all reproduced from the earnings-release exhibit.

### Claims not independently verified in this run

- the estimated EPS/revenue consensus and surprise percentage;
- the exact transcript vendor;
- the complete fidelity of speaker attribution;
- call-only guidance not repeated in a primary text source;
- whether “official transcript” means company-authorized, vendor-transcribed, or merely a transcript of an official call.

### Assessment

The representative single-company summary was materially accurate and well written. It did not look like random generic prose. A capable model with the full transcript and earnings metrics can produce this quality cheaply.

The weakness is auditability:

- no inline source citations;
- no paragraph IDs;
- no separation of filing fact, transcript statement and vendor consensus;
- no visible calculation receipt;
- no source or model version;
- no correction history.

The site's global metadata calls the product “SEC-filed transcript processing” and marks its source verification as “sec-filed.” Earnings calls are generally not SEC-filed transcripts. An 8-K earnings-release exhibit and a 10-Q can verify financial facts, but they do not convert a third-party call transcript into an SEC-filed source. Mastermind must preserve that distinction.

## Corpus and programmatic SEO

The sitemap is the real growth engine.

At inspection time it contained:

- 64,552 URLs;
- 32,245 transcript URLs;
- 32,245 paired analysis URLs;
- 6,944 unique ticker strings;
- fiscal years from 2005 through 2027;
- 13 blog URLs;
- approximately 49 calendar, product and other URLs.

The transcript and analysis pair means every call creates two crawlable acquisition surfaces.

This is not the same as writing a fully rendered editorial article for every earnings event. The transcript page contains the source text, while the paired analysis page initially contains a client-loading shell and can fetch a stored or on-demand answer. The cost-efficient strategy is “one permanent URL pair per call, generate expensive analysis when demanded,” not “prewrite every possible Pro analysis for every call.”

### Corpus distribution

Observed sitemap counts by fiscal year:

| Year | Calls |
|---:|---:|
| 2005–2015 combined | 208 |
| 2016 | 102 |
| 2017 | 241 |
| 2018 | 251 |
| 2019 | 323 |
| 2020 | 442 |
| 2021 | 720 |
| 2022 | 1,070 |
| 2023 | 2,005 |
| 2024 | 8,258 |
| 2025 | 13,479 |
| 2026 | 5,068 |
| 2027 | 78 |

The year labels are fiscal-quarter labels, so future fiscal years can legitimately appear before the calendar year. The distribution nevertheless shows that the deep archive is sparse and the practical corpus is concentrated in 2024–2026.

### SEO implementation

Verified:

- robots excludes account and API paths while allowing transcript and analysis pages;
- transcript pages have unique title, description and canonical metadata;
- full transcript text is server rendered;
- analysis pages have unique metadata but mostly a loading shell in server HTML;
- weekly pages are fully server rendered and include Article JSON-LD;
- the tariff tracker is server rendered;
- blog posts target use cases and evergreen earnings-search questions;
- social cards and legacy EarningsDigest social links are present.

Problems:

1. The single sitemap exceeds Google's documented 50,000-URL limit and should be split behind a sitemap index.
2. transcript and analysis pages returned private/no-store caching during inspection, forcing server work for crawlers.
3. analysis pages expose little unique server-rendered body content.
4. global JSON-LD advertises temporal coverage ending in 2025 even though the live corpus extends further.
5. JSON-LD points to a broken data-download URL.
6. metadata claims real-time freshness, high reliability and SEC-filed verification without claim-level support.
7. page pairs risk thin duplication if the analysis shell has no crawlable answer.

Mastermind should copy the acquisition loop, not the defects:

- split sitemaps by page family and date;
- generate stable static or CDN-cached event pages;
- publish original analysis only where rights allow;
- expose filing facts and short cited transcript excerpts, not an unlicensed full transcript;
- make structured data derive from the same canonical event object;
- include correction and modified timestamps;
- avoid creating a second empty “analysis” URL for every call.

## Data provenance and rights

This is the largest non-token cost.

EarningsCall.ai's terms say site content belongs to it or its content suppliers, prohibit reproduction or distribution without permission, allow subscribers to use AI-generated material in their own work with attribution, prohibit separate redistribution or resale, and require a separate license for broader commercial use.

Therefore:

- public accessibility is not permission to bulk ingest;
- a subscription does not authorize Mastermind to clone the transcript corpus;
- its generated analyses should not be used as training data or republished;
- the independent implementation should begin with primary filings and a transcript contract that explicitly permits our intended uses.

The public product does not display per-call:

- source vendor;
- original audio or webcast URL;
- transcript license;
- received time;
- revision history;
- public-display right;
- derivative-work right;
- quote limit;
- content hash.

The architecture article proves raw vendor payload retention, not that the visible site exposes a provenance ledger.

### Required rights fields for Mastermind

Every source document should include:

- provider and provider document ID;
- contract or license-policy ID;
- acquisition method;
- source URL and timestamp;
- private storage permission;
- internal-analysis permission;
- public full-text display permission;
- derived-analysis publication permission;
- quotation or excerpt limits;
- redistribution/API permission;
- training and embedding permission;
- territory and audience restrictions;
- retention and deletion requirements;
- expiry and renewal date;
- supersession and takedown state.

SEC filings can be the free source of record for reported facts, risk factors and filed exhibits. They are not a substitute for analyst Q&A. A dependable transcript provider remains the central commercial decision.

## What the company appears to do with collected data

Verified uses:

- transcript storage and search;
- AI summaries and analysis;
- watchlists and alerts;
- cross-company comparisons;
- historical trend analysis;
- weekly recaps;
- tariff-topic cards;
- account and subscription management;
- product analytics.

The privacy policy says Clerk handles account identity, Stripe handles payment details, cookies and tracking collect device and page-use information, and chats are not retained. Hotjar and Google Analytics were present in the public frontend.

No evidence found in this run indicates:

- sale of customer data;
- sale of an institutional data feed;
- user-chat training;
- brokerage execution;
- portfolio management;
- advertising revenue;
- affiliate revenue.

The observable business is subscription software supported by a free corpus and organic content.

## How much AI is involved?

Almost all polished analysis prose is likely AI-generated.

Evidence:

- the company says it uses GPT-4 and OpenAI APIs;
- the analysis types align cleanly with prompt templates;
- first generation streams like a model response;
- later requests return stored text;
- weekly output is a large predefined JSON schema;
- tariff cards are structured classification plus extraction;
- individual prose has the high coherence and generic connective language typical of strong LLM synthesis;
- aggregate pages contain classic model failures: synthetic quotations, rounded unsupported counts, mixed identifiers and formatting leakage.

What is likely deterministic:

- transcript identity and storage;
- symbol/year/quarter lookup;
- actual and estimated earnings metrics from a data vendor;
- calendar matching;
- search ranking;
- pagination;
- watchlists and alerts;
- subscription state;
- basic ratios if coded correctly.

What is likely model-generated:

- highlights;
- full summary;
- guidance prose;
- strategic updates;
- risks;
- Q&A summary;
- unconventional findings;
- sentiment narrative;
- cross-quarter narrative;
- peer-comparison narrative;
- weekly themes, surprises, market sentiment and quotes;
- tariff sentiment and impact descriptions.

No evidence supports exact quantitative “weights” for these outputs. Any weighting is more likely prompt instructions such as prioritize management guidance, repeated Q&A concerns, numerical changes and forward-looking statements.

### Why the writing looks expensive when it is not

The prose quality comes from a favorable task:

- earnings calls are already structured, repetitive and information dense;
- company names, speakers, periods and metrics constrain the model;
- each visible section has a narrow editorial purpose;
- saved answers can be generated slowly once and reused many times;
- a predefined schema forces complete-looking coverage;
- current long-context models are good at coherent financial summarization.

The likely production recipe is a detailed system instruction, transcript plus event metrics, an analysis-specific rubric, and a requested Markdown or JSON shape. The fluent connective prose is the cheapest layer. The aggregate quote failures show that a better-sounding writer model does not solve evidence integrity.

## Token and system-cost model

### Per-call token shape

EarningsCall.ai says a typical call is 8,000–12,000 words. That is approximately 10,700–16,000 input tokens before system instructions, earnings metrics and prior-quarter context.

The sampled Apple call at about 49,500 characters is consistent with roughly 12,000–14,000 tokens.

Reasonable output budgets:

| Work unit | Input tokens | Output tokens |
|---|---:|---:|
| One full-transcript narrative | 11k–17k | 1k–3k |
| One comprehensive structured extraction | 12k–18k | 2.5k–5k |
| Renderer over fact packet | 2k–5k | 0.5k–1.5k |
| Cited chat turn with retrieval | 2k–8k | 0.3k–1.2k |
| Naive chat with full transcript | 12k–20k | 0.3k–1.2k |
| Weekly synthesis from 20 compact packets | 20k–60k | 3k–7k |

### Why the current product can be cheap

If ten analysis types each resend a 14,000-token transcript, one heavily explored call consumes about 140,000 input tokens before chat. But the client behavior supports on-demand generation and result persistence. Most calls may only receive the free highlights and a small minority will ever generate every Pro view.

At the site's 32,245-call corpus:

- one 16,000-token pass over every call is about 516 million input tokens;
- one 3,000-token structured result per call is about 97 million output tokens;
- ten naive full-transcript analyses would exceed 5.1 billion input tokens.

For approximately 20,000 new US calls per year:

- one-pass extraction is roughly 214–320 million transcript input tokens;
- 2,500–5,000 output tokens per event is roughly 50–100 million output tokens;
- ten naive prompt views are roughly 2.1–3.2 billion input tokens before chat.

### Vendor-neutral cost formula

For 20,000 calls:

    annual extraction cost
      = input-token millions × input price per million
      + output-token millions × output price per million

Illustrative one-pass ranges:

| Hypothetical model tariff | Annual extraction cost |
|---|---:|
| $1/M input and $5/M output | about $464–$820 |
| $2/M input and $10/M output | about $928–$1,640 |
| $5/M input and $20/M output | about $2,070–$3,600 |
| $30/M input and $60/M output, legacy premium economics | about $9,420–$15,600 |

These are arithmetic scenarios, not current vendor quotes. They exclude retries, evaluation, embeddings and chat.

The conclusion is robust across model vendors: **batch prose tokens are not the expensive part.** User chat can become the larger token variable because it scales with engagement and may repeatedly inject the same transcript.

### Efficient Mastermind architecture

Do not recreate one transcript-to-one-prompt per tab.

Use:

    raw transcript + filing metrics + consensus snapshot
                         |
                         v
          one comprehensive structured extraction
                         |
          +--------------+---------------+
          |              |               |
          v              v               v
     deterministic   materialized     retrieval
      validators        views           index
          |              |               |
          +--------------+---------------+
                         |
       +---------+-------+--------+---------+
       |         |                |         |
       v         v                v         v
    dossier    Stage          article/X    cited chat

One structured extraction should capture:

- speaker and section spans;
- reported metrics and periods;
- guidance ranges and qualifiers;
- segment and geographic changes;
- management priorities;
- risks and constraints;
- analyst questions and management answers;
- tone changes;
- products, customers, suppliers and competitors;
- theme evidence;
- exact quote candidates;
- uncertainty and contradiction flags.

Then:

- calculate all numbers in code;
- render Highlights, Guidance, Risk and Q&A as deterministic views or small prompts over that packet;
- compare quarters using packets rather than full transcripts;
- compare peers using normalized facts and only retrieve supporting spans;
- generate weekly intelligence from issuer-deduplicated packets;
- make chat retrieve a few paragraphs and cite them;
- cache by source and processing versions.

This should reduce repeat transcript input by roughly 70–90% for heavily viewed calls.

### Non-token operating costs

Planning ranges:

| Cost family | Early production | Broad production |
|---|---:|---:|
| Postgres, object storage, queue, search and CDN | $200–$1,000/month | $1,000–$5,000/month |
| Batch LLM extraction and rendering | $50–$500/month | $200–$2,000/month |
| Interactive chat | $50–$1,000/month | usage-dependent; potentially several thousand |
| Transcript and consensus rights | $2,000–$10,000+/month | $5,000–$25,000+/month; redistribution may be higher |
| Initial engineering, fully loaded | $175,000–$400,000 | depends on internal team |
| Ongoing engineering/data operations | 0.5–1.5 FTE | 0.5–1 FTE after stabilization |

The data-rights range is deliberately wide and is not a vendor quote. Commercial public display and downstream redistribution can cost far more than internal analysis access.

## The stronger Mastermind design

### 1. Company Event Spine contracts

#### company_source_document.v1

- document ID and company identity;
- source family: transcript, audio, 8-K, exhibit, 10-Q, 10-K or investor presentation;
- source/provider ID and rights policy;
- source URL and retrieval timestamp;
- raw and normalized content hash;
- paragraph, table and speaker-turn structure;
- amendment, revision and supersession chain;
- point-in-time availability;
- public-display and derivative permissions.

#### earnings_event.v1

- event ID;
- ticker, CIK and issuer ID;
- fiscal year and quarter;
- report-release, call-start, transcript-received and SEC-accepted timestamps;
- actual, consensus and guidance snapshot IDs;
- source-document IDs;
- coverage and freshness state;
- processing and correction state.

#### earnings_call_analysis.v1

- management highlights;
- reported metric facts;
- guidance facts;
- strategy changes;
- risks and constraints;
- Q&A concerns;
- sentiment dimensions;
- products, geographies and counterparties;
- theme candidates;
- exact source-span receipts;
- extraction confidence and contradiction flags;
- model, prompt, schema and validator versions.

#### earnings_metric_delta.v1

- canonical metric;
- actual, prior, consensus and guidance values;
- period, currency, units and scale;
- absolute, percentage and basis-point deltas;
- deterministic calculation receipt;
- source classification and source span.

#### theme_evidence_edge.v1

- event and issuer;
- normalized theme;
- evidence type;
- exact source span;
- positive, negative or mixed direction;
- magnitude, novelty and persistence;
- first-seen and last-seen timestamps;
- affected peers and relationship path;
- validation state.

#### company_event_synthesis.v1

- what changed;
- why it matters;
- what remains uncertain;
- bull, base and bear evidence separated from company-authored guidance;
- linked themes and peer read-through;
- every claim mapped to fact or span IDs;
- version and correction graph.

### 2. Terminal and ticker dossier

One ticker page should expose:

- event timeline;
- call transcript with speaker and paragraph anchors;
- highlights;
- reported versus consensus;
- guidance changes;
- risks;
- analyst Q&A;
- cross-quarter evolution;
- peer comparison;
- themes and relationship read-through;
- source and correction receipts;
- cited chat.

Do not create a second EarningsCall.ai-shaped product shell. The Terminal dossier is already the correct home.

### 3. Stage Analysis

The Earnings Calls tab should consume the same event contract and show:

- report and call dates separately;
- source coverage and freshness;
- actual/consensus surprise;
- guidance direction;
- management confidence dimensions;
- analyst challenge level;
- material risks;
- industry aggregation;
- quarter-over-quarter comparison;
- exact source receipts.

No LLM narrative should directly determine stage, conviction, trade rank, position size or execution. Descriptive context can be visible immediately; decision authority requires a prospective bakeoff.

### 4. Neural Web and Prophet

Neural Web should not receive full transcripts by default. It should receive a compact point-in-time export:

- top event facts;
- guidance delta;
- top risks;
- Q&A tension;
- theme edges;
- supplier/customer read-through;
- source IDs and confidence;
- event age and freshness.

The raw transcript remains retrievable when a lobe asks for evidence.

Prophet and other signal lobes may use earnings context only after:

- point-in-time historical replay;
- source-lag simulation;
- ablation testing;
- issuer and sector stratification;
- stress-regime testing;
- proof that the context adds out-of-sample value.

The first deployment should be contextual, not directional.

### 5. Blog, SEO and X

Create one canonical story packet, then compile:

- ticker dossier update;
- public earnings brief;
- filing/call comparison;
- theme brief;
- X thread;
- short posts for distinct accounts;
- chart annotations;
- alert.

The compiler must:

- use deterministic numbers;
- distinguish company statement, analyst question and Mastermind inference;
- reject any quote not matched exactly to a source span;
- deduplicate share classes;
- attach original source links;
- preserve one version graph across all derivatives;
- retract or correct every derivative from one upstream correction.

Different X accounts should receive different evidence-grounded angles, not lightly paraphrased duplicates:

- fundamentals account: results and guidance;
- macro account: demand, inflation, FX and credit;
- sector account: peer and supply-chain read-through;
- AI account: capex, compute, power and adoption;
- risk account: constraints and analyst pushback;
- trader account: surprise, reaction and next catalyst.

### 6. Topic monitors

EarningsCall.ai's tariff tracker should become a generic materialized-view engine:

    source-cited event facts
        -> topic matcher
        -> entity and theme normalization
        -> deterministic filter and deduplication
        -> model interpretation
        -> validator
        -> topic timeline and alert

The topic engine can directly enrich Jodie-like theme detection. A market co-movement becomes more useful when several members independently mention the same demand driver, cost pressure, customer or capital-spending program.

## Build plan

### Phase A — Source and truth lane

**Duration:** 3–5 weeks after the transcript-rights decision.

- choose transcript provider and commercial use;
- ingest earnings calendars, reports, 8-K exhibits, 10-Qs and calls;
- separate announce date, call date, filing date and provider arrival;
- store immutable raw objects;
- normalize speakers and paragraphs;
- create event IDs and source hashes;
- publish coverage/freshness manifest;
- implement provider replay and failover.

Exit: 98% target coverage, no duplicate issuer-quarter, every event traceable to source and rights.

### Phase B — Structured extraction and validators

**Duration:** 3–5 weeks, overlapping Phase A.

- define earnings_call_analysis.v1;
- build one-pass extraction;
- calculate financial deltas in code;
- exact-match quotations;
- reconcile transcript numbers to filings;
- flag conflicts and missing consensus;
- create golden benchmark of difficult companies and fiscal calendars.

Exit: all published numbers reproduce; zero synthetic quotations in held-out evaluation.

### Phase C — Existing product integration

**Duration:** 2–4 weeks.

- feed Stage Analysis from the Event Spine;
- add Terminal transcript, event and comparison views;
- update per-ticker dossiers;
- expose cited single-call chat;
- connect watchlists and alerts;
- remove duplicate loaders and score scales.

Exit: one reader and one contract across the website.

### Phase D — Theme, Neural Web and content fan-out

**Duration:** 3–5 weeks.

- create event-to-theme edges;
- build topic monitors;
- export compact Neural Web context;
- build canonical story and derivative contracts;
- publish selected public briefs and X variants;
- implement persistent correction replay.

Exit: every public and machine-consumed claim resolves to a versioned fact or source span.

### Phase E — Scale and prospective validation

**Duration:** 4–8 weeks.

- run through an earnings peak;
- test provider latency and gaps;
- benchmark chat cost and retrieval;
- split SEO sitemaps and static-cache public pages;
- measure acquisition, dossier engagement and trial conversion;
- evaluate whether earnings context adds signal value out of sample.

Exit: stable season coverage, measurable product use, and no provenance regressions.

### Staffing and maintenance

A thin clone can be built by one strong engineer in four to eight weeks. A Mastermind-grade integrated system is more credibly:

- two backend/data engineers;
- one product/full-stack engineer;
- part-time research/ML evaluation;
- three to five months for a robust first release.

After stabilization:

- 0.5–1 FTE for pipeline, provider, schema and incident ownership;
- 0.25–0.5 FTE for research quality and evaluation;
- periodic frontend/content work.

Maintenance burden will come from:

- ticker and issuer changes;
- non-calendar fiscal quarters;
- amended and delayed filings;
- provider gaps and revisions;
- speaker-name errors;
- consensus mismatches;
- long or malformed calls;
- rights changes;
- model and prompt upgrades;
- corrections;
- earnings-season burst load.

It will not come mainly from the frontend.

## Relationship to the current EquityDesk-derived lobe

The EquityDesk archive is useful as a historical calibration and UI seed. It is not a complete source-of-truth corpus because its derived records do not carry full transcript provenance.

A concurrent authenticated delta capture found:

- 51,156 total derived call records versus the prior 50,053;
- 1,103 additions;
- 802 calls after the previous July 17 cutoff;
- 301 historical backfills;
- no schema changes;
- zero of the 1,103 added records with a populated source file path.

This confirms the correct posture:

- use the archive for recovery, regression and calibration;
- do not make EquityDesk the live production dependency;
- do not infer transcript rights from derived output;
- route future calls through the Company Event Spine;
- make Stage Analysis one consumer of the new spine.

## What to copy and what to reject

### Copy

- serverless event ingestion;
- raw-object replay;
- normalized transcript store;
- full-text search;
- one canonical corpus for all features;
- on-demand generation and persistence;
- single-call, historical and peer workflows;
- keyword watchlists and alerts;
- weekly and topic materialized views;
- programmatic ticker/event acquisition;
- simple paid plan and product-led trial.

### Upgrade

- exact source and rights ledger;
- event-time semantics;
- issuer/share-class normalization;
- one-pass structured extraction;
- deterministic metrics and counts;
- paragraph-level citations;
- hybrid retrieval;
- versioned cache keys;
- persistent corrections;
- server-side entitlement and cost controls;
- source-aware Neural Web exports;
- canonical multi-channel story compiler.

### Reject

- copying or training on its corpus;
- one full-transcript model call per UI tab;
- quote-like paraphrases;
- unsupported keyword counts;
- “SEC-filed transcript” language;
- client-only premium gates;
- no-store SEO pages at corpus scale;
- one sitemap above 50,000 URLs;
- duplicate issuer share classes in aggregate intelligence;
- LLM sentiment or summary as direct trade authority;
- article volume as the main success metric.

## Final recommendation

Proceed, but define the project correctly.

Do not “bring EarningsCall.ai over” as another cloned product. Build the **Earnings and Company Event Spine** that makes its best features native to Mastermind:

1. Restore the current Stage Analysis lobe from the captured historical archive.
2. Settle transcript and consensus rights.
3. Ingest every future event once with immutable provenance.
4. Run one structured, cited extraction.
5. Derive the dossier, Stage view, comparison, theme evidence, Neural Web context, article and X content from that one object.
6. Treat public content as a governed derivative, not free-form model prose.
7. Prove any signal contribution prospectively before Prophet or another lobe receives decision authority.

EarningsCall.ai demonstrates that a high-coverage transcript product and SEO funnel can be operated cheaply by a very small team. Its own engineering disclosure and founder history make that clear. It also demonstrates the danger of letting fluent aggregate prose outrun evidence: the weekly product invents quotation form, opaque counts and duplicated issuer weight while looking highly credible.

Mastermind can build the materially better system because it already has the surfaces and intelligence graph that EarningsCall.ai lacks. The moat is not the summary. The moat is:

    complete event memory
      + point-in-time truth
      + source rights
      + claim receipts
      + issuer and theme graph
      + correction replay
      + one packet feeding every intelligence and distribution surface

That is difficult enough to matter and reusable enough to justify making it a core feature.

## Source ledger

Product and engineering:

- [EarningsCall.ai home](https://www.earningscall.ai/)
- [Pricing](https://www.earningscall.ai/pricing)
- [FAQ](https://www.earningscall.ai/faq)
- [Transcript search architecture](https://www.earningscall.ai/blog/How-We-Built-Our-Earnings-Call-Transcript-Search-Stack)
- [AAPL Q3 2026 transcript](https://www.earningscall.ai/stock/transcript/AAPL-2026-Q3)
- [AAPL Q3 2026 analysis](https://www.earningscall.ai/stock/analyze/AAPL-2026-Q3)
- [Weekly Earnings Intelligence, July 20, 2026](https://www.earningscall.ai/weekly-earnings-intelligence/2026-07-20)
- [Tariff Impact Tracker](https://www.earningscall.ai/tariff-impact-tracker-earnings-call)
- [Blog](https://www.earningscall.ai/blog)
- [Sitemap](https://www.earningscall.ai/sitemap.xml)
- [Robots policy](https://www.earningscall.ai/robots.txt)

Company, marketing and policy:

- [Terms](https://www.earningscall.ai/terms)
- [Privacy](https://www.earningscall.ai/privacy)
- [EarningsCall.ai LinkedIn company page](https://www.linkedin.com/company/earningsdigest)
- [Founder Mark Zhong launch post](https://www.linkedin.com/posts/markzhongnyc_ai-earningsdigest-fintech-activity-7079828308309241857-usT2)
- [Miky Bayankin soft-launch post](https://www.linkedin.com/posts/bayankin_earnings-digest-ai-powered-stock-earnings-activity-7077684160278016001-Ezc8)

Primary verification:

- [Apple Q3 2026 earnings-release exhibit](https://www.sec.gov/Archives/edgar/data/320193/000032019326000018/a8-kex991q3202606272026.htm)
- [Apple Q3 2026 Form 10-Q](https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/aapl-20260627.htm)
- [Apple CEO transition Form 8-K](https://www.sec.gov/Archives/edgar/data/320193/000114036126015711/ef20071035_8k.htm)
- [SEC submissions API](https://data.sec.gov/submissions/CIK0000320193.json)
- [Google sitemap limits](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
