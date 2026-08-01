# Jodie + Struct Engine Teardown and Mastermind Integration Docket

**Canonical deliverable:** this file

**Research snapshot:** 2026-07-31 America/Vancouver / 2026-08-01 UTC

**Decision:** integrate the useful intelligence primitives into the shared Macro Dashboard and Mastermind data plane; do not clone Jodie or Struct as a second product stack.

## Executive verdict

The opportunity is real, but it is different from the first impression.

Jodie is best understood as a **market-attention and relationship engine**, not a proven capital-allocation engine. Its public methodology says the detected structures survived validation as descriptions of unusual coordination, while the forward trading edge did not. Jodie is explicit that it does not predict direction, is not faster than news, and should not be read as a buy or sell signal. That sharply limits the value of reproducing its score as an alpha engine. It does not limit the value of reproducing its ability to answer:

- Which securities are beginning to move together after stripping out the common market?
- Is a group established, strengthening, weakening, or newly forming?
- Which companies are connected by customer, supplier, competitor, or similar filing language?
- Where does a fresh market anomaly cross a known business relationship?
- What changed in a filing, which peers may receive a read-through, and what should be investigated next?

Struct is the distribution layer built on top of those assets. It is a newly launched, high-throughput automated publication rather than an established newsroom. Its observable article factory turns structured fact packets into indexable articles, evidence cards, ticker links, social-ready images, and calls to action back to Jodie. The prose is almost certainly LLM-generated. Text tokens are cheap enough that they are not the limiting cost. Data normalization, source rights, relationship extraction, quality control, corrections, and trust are the expensive parts.

The recommendation is therefore:

| Decision | Score | Verdict |
|---|---:|---|
| Make company-and-theme intelligence a core Mastermind capability | 8.5/10 | Yes |
| Clone the entire Jodie product and opaque scoring system | 3/10 | No |
| Clone Struct's visual frontend | 4/10 | Unnecessary; Mastermind already has stronger surfaces |
| Rebuild the four useful analytical primitives independently | 9/10 | Yes |
| Publish a long article for every filing | 4/10 | No; use event tiers |
| Use the corpus to drive dossiers, SEO, and differentiated X accounts | 9/10 | Yes |
| Treat 13-F activity as a positive alpha signal | 1/10 | No; context and crowding only |

The four primitives worth bringing over are:

1. **Residual theme discovery:** detect organic groups after removing common market motion.
2. **Theme lifecycle and lineage:** distinguish newly forming, watching, confirmed, expanding, weakening, and dissolved groups over time.
3. **Filing relationship graph with receipts:** map customer, supplier, competitor, product, and language similarity with exact source spans.
4. **One canonical evidence packet, many products:** update the ticker dossier once, then derive a research article, X thread, short posts, alerts, and Mastermind context from the same versioned facts.

This is not a greenfield build. The current Macro Dashboard and Mastermind estate already contains roughly 70–80% of the useful substrate: EDGAR facts and filing dates, 13-F context, theme scoring, residual correlations, theme discovery, ticker dossiers, an extensive marketing system, SEO primitives, and freshness-gated Mastermind bridges. The missing 20–30% is the difficult and defensible vertical: complete source documents, reliable transcripts and consensus, event-to-theme evidence, claim-level provenance, a living article object, and persistent correction operations.

The existing EquityDesk-derived Earnings Calls lobe strengthens that reuse case but is currently broken operationally: a 50,053-row raw historical archive exists locally and a 3,431-row latest-call seed is committed, while the dedicated builder reads an absent full-history parquet and the live R2 score object does not exist. “Warming up” is a silent data-contract failure, not a job that merely needs another night.

## The most important correction to the product thesis

The attractive interpretation is:

> Jodie detects themes heating up, proves their structural importance from filings, and supplies early signals for capital deployment.

The evidence supports a narrower claim:

> Jodie detects unusual residual co-movement, tracks group state, connects that activity to filing-derived relationships, and compresses the result into an investigation surface.

On its [Method page](https://jodie.ai/method), Jodie describes two measurements and one join:

1. A live map removes broad-market movement and separates established groups from groups that may be forming.
2. A structural map reads filings for customer, supplier, competitor, and similar annual-report language, retaining the excerpt.
3. An alert becomes more meaningful when a live group crosses a structural relationship to a followed company.

Its published validation statistics are useful but modest:

- Confirmed-group persistence: 52%.
- Forming-group persistence: about 40%.
- Annual-report text peers: 42.9% versus a 30% base rate, p = .0015.
- Filing-linked read-through: +0.046, confidence interval [.017, .075], sector controlled.

Those results indicate that the maps preserve some real structure. They do not establish directional returns. The same page says direction is a coin flip, the product is not faster than the news, and the system de-emphasizes readings for roughly a week after volatility or credit stress. The more detailed [Methodology page](https://jodie.ai/methodology) says the detection system survived its test while the predictive trading edge did not.

That honesty is important. Jodie can improve what Mastermind notices and explains. It should not be permitted to originate a conviction score, trade ranking, size, or execution gate without a separate point-in-time validation gauntlet. This is also consistent with the repository's binding rule that LLM-originated signals are forbidden and that 13-F data remains context-only.

## What the two products actually are

### Jodie

Jodie is a subscription research interface centered on:

- live and recently active market themes;
- per-ticker profiles and watchlists;
- theme membership, breadth, pressure, propagation, and lifecycle state;
- filing-derived company relationships;
- market-weather context;
- alerts and a public TradingView companion;
- ticker-specific previews, exposures, filing assessments, and read-throughs.

The public sitemap exposed approximately 3,851 URLs at inspection time, including 3,787 ticker routes, 51 briefs, four theme routes, and nine other pages. That is a large programmatic landing-page estate, not evidence that 3,787 full research articles are continuously rewritten.

The [Use Cases page](https://jodie.ai/use-cases) emphasizes hidden portfolio exposure, cross-sector rotations, and morning compression. It also describes future or desk-oriented delivery through Slack or Discord webhooks, CSV lineage history, and a read API. These are workflow products, not just charts.

### Struct

Struct is Jodie's free, indexable publication and acquisition surface. It publishes short research briefs across five visible types:

| Article family | Observed count | Mean body length |
|---|---:|---:|
| Filing Read | 125 | 473 words |
| Moving Together | 7 | 408 words |
| Filing Trend | 2 | 580 words |
| Supply Chain | 7 | 717 words |
| Daily Radar | 2 | 261 words |
| **Total** | **143** | **481 words** |

The corpus was exceptionally new and bursty:

- one article on July 2;
- one on July 13;
- 35 on July 30;
- 105 on July 31;
- one just after midnight UTC on August 1.

The [Struct sitemap](https://struct.news/sitemap.xml) exposed 108 briefs plus six non-article pages, while the live homepage contained 35 newer articles absent from that cached sitemap. Its [RSS feed](https://struct.news/feed.xml) exposed the latest 50 items. This is a launch-stage system, not a mature, proven SEO property.

Struct's apparent job is:

    filing or market anomaly
        -> free, crawlable article
        -> ticker evidence and context
        -> jodie.ai/t/{ticker}?from=struct&brief={slug}
        -> Jodie paywall
        -> subscription

There are no visible ads, sponsorships, affiliate links, newsletter capture, or meaningful standalone paid product. Every article routes the reader toward Jodie. The attribution parameters make article-level and ticker-level conversion measurement straightforward.

## Jodie engine reconstruction

The backend source code is private. The following reconstruction separates published methodology, exact public companion code, observations from the live public API, and inference. It would be dishonest to claim that the full backend or every weight can be recovered from the frontend.

### 1. Universe and market-neutral residuals

Jodie's detailed methodology says it processes approximately 1,900 US equities nightly. The essential first step is to remove the common market component so that a broad risk-on day does not masquerade as a new theme.

A reasonable representation of the published method is:

    stock return(i,t) = alpha(i) + beta(i) * equal-weight market return(t) + residual(i,t)

The beta is rolling and shrunk, rather than trusting a noisy per-stock estimate. The residual is the portion of each security's move not explained by the common equal-weight universe proxy.

Why this matters:

- Raw correlations are dominated by market beta and sector beta.
- Residual correlations expose coordination not explained by the broad tape.
- The equal-weight proxy reduces the dominance of a handful of mega-cap names.
- Shrinkage helps stabilize short or sparse histories.

This is a sensible discovery layer. It is not unique by itself; the defensibility comes from stable identity, lineage, event linkage, and longitudinal evaluation.

### 2. Nightly established-group discovery

Jodie describes a nightly pipeline using:

- a residual correlation matrix;
- Ledoit-Wolf covariance shrinkage;
- Marchenko-Pastur denoising;
- Louvain community detection;
- lineage matching across runs.

The likely flow is:

    residual return panel
        -> stabilized covariance/correlation
        -> remove eigenstructure consistent with noise
        -> graph of meaningful relationships
        -> Louvain communities
        -> match today's communities to yesterday's identities

Ledoit-Wolf shrinkage reduces estimation error. Marchenko-Pastur filtering attempts to distinguish correlation eigenvalues that exceed a random-matrix noise band. Louvain then finds densely connected communities. A lineage layer is necessary because raw community IDs are arbitrary between runs; without it, a theme cannot meaningfully be called expanding, weakening, split, merged, or dissolved.

The published site does not reveal:

- the lookback length for the nightly matrix;
- the exact shrinkage target;
- the graph edge threshold;
- how negative correlations are handled;
- Louvain resolution and random seed policy;
- minimum and maximum group size;
- how splits and merges are assigned;
- corporate-action, IPO, delisting, and missing-data rules.

Those parameters materially affect results. They must be independently calibrated rather than guessed.

### 3. Emerging-group detection

For pairs not already explained by an established group, Jodie compares short exponentially weighted residual correlations with each pair's own history. It uses Fisher's z transform and an effective sample-size adjustment. Dense subgraphs with unusually high evidence form candidate groups.

Conceptually:

    z(pair,t) = atanh(short residual correlation)
    surprise(pair,t) = [z(pair,t) - historical pair mean] / adjusted standard error

Pairs with strong surprises become edges. A high-evidence seed clique expands into a candidate community when enough members and edges agree.

Jodie says null simulations are calibrated to produce roughly one false formation every two trading weeks across approximately 1.8 million candidate pairs. That is a useful system-level false-discovery target. It also explains why a formation score is not merely a simple correlation threshold.

Important implementation requirements for Mastermind:

- perform null calibration at the universe level, not one pair at a time;
- correct effective sample size for exponentially weighted and autocorrelated observations;
- use point-in-time membership and liquidity filters;
- prevent duplicate share classes from inflating breadth;
- record every group split, merge, rename, and dissolution;
- test performance in stress and quiet regimes separately.

### 4. Intraday group state

Jodie says it refreshes the live layer every 15 minutes. It compares current readings with each name's own trailing 30-day baseline and measures:

- residual breadth;
- volume;
- flow;
- dispersion;
- shock;
- impulse;
- propagation or shared participation.

The public API exposes related fields including breadth, pressure and pressure components, promotion status and score, agreement, probability, quorum, support count, shock, impulse, propagation, flow, cross-asset context, user-interface state, and validation metadata.

The methodology also mentions winsorization, extreme-value caps, and a drop-the-largest-shared-day robustness check. That last check is valuable: a supposed group should not exist only because every member had one extraordinary day.

The live theme endpoint at inspection time was:

[Jodie US equity themes API](https://jodie.ai/api/themes?mode=equities&region=us&limit=500&include_weak=true)

The API's provenance fields distinguish observed from modeled values, and its exposed validation label was rules_v1. These are useful design cues: every field in a Mastermind contract should say whether it was observed, deterministically derived, statistically modeled, or LLM-extracted.

### 5. Public Activity Radar heat score

Jodie published an open TradingView Activity Radar companion. Unlike the private backend, its Pine implementation exposes useful benchmark math.

- [Jodie Activity Radar — Heat Score](https://www.tradingview.com/script/Aj6DokrJ-Jodie-Activity-Radar-Heat-Score/)
- [Raw public Pine source payload](https://pine-facade.tradingview.com/pine-facade/get/PUB;15223bab4d1541c4afb718c04e803fc0/last)

The companion estimates rolling beta to SPY over 60 bars and creates a residual return. It then computes:

    shock = current residual / rolling residual standard deviation

    impulse = five-bar average residual * square root of 5
              / rolling residual standard deviation

With a peer basket available:

    raw heat = 0.45 * absolute shock
             + 0.35 * absolute impulse
             + 0.20 * propagation

Without a basket, the remaining weights are renormalized:

    raw heat = 0.5625 * absolute shock
             + 0.4375 * absolute impulse

The propagation proxy is an average of peer-member raw heat. Theme heat takes the mean of up to the top eight members and multiplies it by breadth. A member becomes active at raw heat of at least 0.85.

The raw-to-display-score mapping is piecewise linear through these anchors:

| Raw heat | Display score |
|---:|---:|
| 0.00 | 0 |
| 0.63 | 20 |
| 0.85 | 40 |
| 1.11 | 60 |
| 1.55 | 80 |
| 2.68 | 95 |
| 6.00 | 99 |
| 44.00 | 100 |

The visible state bands are:

| Raw heat | State | Display lift |
|---:|---|---:|
| below 0.85 | Calm | 0.8 |
| 0.85 to below 1.11 | Normal | 1.0 |
| 1.11 to below 2.68 | Hot | 1.3 |
| 2.68 and above | Extreme | 1.25 |

The lower lift for Extreme than Hot is unusual but is what the public code showed. Alerts fire on display-score crossings of 60 and 95. The Pro webhook posts ticker, exchange, interval, price, band, heat, and time to Jodie's API for onward Slack or HTTP delivery.

The script comments referred to an internal heat-score module, a heat-score specification, calibration label resid_3m_2026, and an AUC of 0.561. AUC 0.561 is modest, not evidence of a powerful directional forecaster. The public description says hot names are approximately 1.3 times more likely to have an outsized move in either direction over the following few days. Nondirectional volatility anticipation can coexist with Jodie's statement that directional prediction is a coin flip.

TradingView also surfaced consistency warnings around correlation, standard deviation, moving-average, and cross functions being called conditionally. Those warnings are not proof the output is wrong, but they are another reason to treat the script as a benchmark, not production source code.

### 6. Theme pressure: a recoverable public formula

Across a snapshot of 97 current US themes, the public pressure score was reproducible from its component fields:

    pressure = round(100 * (
        0.24 * cluster impulse
      + 0.22 * breadth expansion
      + 0.20 * correlation tightening
      + 0.14 * leader micro impulses
      + 0.10 * volume anomaly
      + 0.10 * propagation build
    ))

This matched all 97 observations in the live US snapshot exactly after rounding. This formula is an independent reconstruction from a live API snapshot, not a published specification.

It also revealed a likely defect. In every observed row where the two fields were nonzero:

    volume anomaly approximately equals 0.75 * correlation tightening

The cross-sectional correlation between the two columns was 1.00. If the fields are aliases or deterministic transforms, the pressure formula double-counts one underlying signal under two labels. That does not prove the private historical engine always behaves this way, but it materially weakens the current public score's credibility.

We could not recover the exact formulas for theme probability, promotion score, agreement, quorum, or stability. They should be treated as opaque. One inspected theme had a promotion score of 0.9181 but remained on hold, theme probability 0.3552, no active members, and a user-interface activity score of 86/hot while the same payload labeled signal strength weak, stability newly forming, and last update roughly ten hours old. The product's multiple score families are not a single coherent probability scale.

### 7. Filing relationship graph

The structural graph is the older and arguably more defensible part of Jodie.

In a 2020 first-person engineering article, founder Justin Davies described using spaCy named-entity recognition over EDGAR 10-K and 10-Q risk-factor text, parsing EDGAR monthly archives and Item 1A, storing filing text in Elasticsearch, storing adjudications and entity rules in MongoDB, and labeling training chunks with doccano. [Training spaCy NER Models with doccano](https://medium.com/@justindavies/training-spacy-ner-models-with-doccano-8d8203e29bfa)

That historical account supports the following architecture:

    SEC filing archive
        -> section extraction
        -> entity recognition
        -> company-name normalization
        -> relationship classification
        -> evidence span
        -> company-to-company graph

The current Method page says the graph looks for customers, suppliers, competitors, and similar annual-report language and stores the excerpt. The site does not prove that the 2020 storage or model stack remains unchanged, so the historical details should not be confused with current backend confirmation.

A production Mastermind equivalent needs more than named entities:

- point-in-time ticker, CIK, LEI, company-name, subsidiary, and former-name resolution;
- relation ontology with direction: supplier-to, customer-of, competitor-of, acquired-from, partner-of, investor-in, and merely-mentioned;
- explicit versus inferred evidence;
- source form, accession, item, document, page or paragraph, and accepted timestamp;
- negation and hypothetical-language detection;
- amendment supersession;
- confidence calibrated by relation type;
- a contradiction and expiration lifecycle.

The relationship should be deterministic once accepted. An LLM may propose a typed relation and quote span, but a validator must verify that the company, wording, form, and source span exist.

### 8. Filing assessment and ticker dossier

The public ticker contract shows that Jodie is doing more than adding relationships to a chart:

- [NVDA compact ticker payload](https://jodie.ai/api/ticker/NVDA?compact=1&region=us)
- [NVDA exposures](https://jodie.ai/api/ticker/NVDA/exposures)
- [NVDA filing assessment](https://jodie.ai/api/ticker/NVDA/filing-assessment)
- [Filing briefs API](https://jodie.ai/api/briefs/filings?limit=6&off_hours=1)

At inspection time, the NVDA exposure response identified MU and TSM as suppliers with confidence and filing support, and AMD as a filing-text peer with similarity and z-score fields. The filing assessment identified its engine and public schema as filing-assessment-v9 and filing-assessment-public-v1.

The visible assessment pattern was:

1. select the current filing and prior comparable filing of the same form;
2. normalize SEC facts and comparable periods;
3. compute revenue, margin, net-income, liquidity, and trailing-valuation changes;
4. assign deterministic dimension points;
5. select sentence-level receipts;
6. produce an operating posture and validation summary.

For NVDA, the live payload reported revenue +85.2%, operating margin +16.5 percentage points, net income +210.6%, operating score +4, posture Constructive, and a 100-point internal validation result. Its valuation was explicitly trailing, based on filing-date price and annual SEC facts—not analyst consensus or a forward estimate.

This is useful product behavior but not independently validated economics. The exact point schedule and reconciliation rules remain private. A “100-point validation” inside the same producer is not equivalent to an external accuracy audit.

The market-flow field is simpler than its branding. The public basis described signed five-minute dollar turnover, using the sign of close divided by the prior close, falling back to the open. That is a directionally signed turnover proxy, not order-book or broker-classified institutional flow.

No current public Jodie or Struct route, article source field, API payload, or sitemap surface inspected in this run substantiated a live 13-F engine or earnings-call transcript engine. The verified current filing substrate is 10-K, 10-Q, 8-K and exhibits, SEC/XBRL facts, filing-derived relationships, and filing-text similarity. Those other sources may exist privately, but they should not be included in a parity estimate without evidence.

### 9. The join

Jodie's most useful product idea is not any single score. It is the join:

    unusual residual market group
        x
    filing-derived business relationship
        x
    user's watched ticker or portfolio
        =
    high-value investigative alert

This can surface, for example:

- a watched company whose named supplier cluster is suddenly coordinating;
- a theme moving across conventional sector boundaries;
- a company with calm own-price action but unusual motion in linked peers;
- a filing claim that gains or loses credibility as the relevant market basket responds.

For Mastermind, this join should produce a context object with evidence and uncertainty. It should not directly increase conviction, position size, or execution permission.

## Public API and frontend teardown

### Jodie stack and exposed contracts

Jodie's shipped bundles and headers showed Next.js 16.2.6, a React 19.3 canary build, Turbopack/App Router, and nginx 1.24.0 on the public host. Its frontend communicates with same-origin API routes and stores bearer authentication in local storage under Jodie-specific token and user keys.

The exposed bundle revealed route families including:

| Route family | Apparent purpose |
|---|---|
| /themes | theme list and filters |
| /themes/{id} | detailed theme |
| /themes/{id}/readthrough | linked-company implications |
| /identity/radar | identity or portfolio radar |
| /briefs/filings | filing brief feed |
| /feed | combined activity feed |
| /market/weather | broad environment |
| /ticker/{symbol} | ticker dossier |
| /ticker/{symbol}/preview | free preview |
| /ticker/{symbol}/fundamental-readthrough | filing/fundamental implications |
| /ticker/{symbol}/exposures | theme and relationship exposures |
| /ticker/{symbol}/filing-assessment | filing-derived assessment |
| /search and /tickers/detail | discovery and metadata |
| /me, watchlists, alert rules | account state |
| Stripe checkout and portal | web billing |
| TradingView webhook | alert relay |

This is enough to understand the product's domain model. It is not enough to recover backend feature engineering, training data, thresholds, graph construction, database layout, or production orchestration.

Observed cache horizons were roughly 30 seconds for theme and ticker payloads, 120 seconds for filing briefs, 300 seconds for market weather, and one hour for filing assessments and exposures. No WebSocket or EventSource route appeared in the shipped client. “Real time” therefore appears to mean frequent request-time refresh rather than a server-pushed stream.

The public Pine comments pointed Pro alerts to https://api.jodie.ai/api/tradingview/hook, but api.jodie.ai had no DNS answer at inspection time. The Methodology footer's Status control was also a null link. The Use Cases page describes Slack or Discord webhooks, CSV, and a read API, but those do not appear on the retail pricing surface. They should be treated as roadmap or desk positioning until demonstrated.

### Struct stack

Struct is a Next.js React Server Components application hosted on Vercel. Pages are server-rendered or prerendered. An observed article delivered roughly 47 KB of HTML and about 718 KB of raw framework assets, fonts, CSS, and JavaScript; only about 21 KB was custom client logic.

Its public client bundle defaults the API base to https://jodie.ai/api, the product URL to https://jodie.ai, and ticker logos to Jodie's host. The custom chunk was visible at:

[Struct custom frontend bundle](https://struct.news/_next/static/chunks/27p9zk-cmfaio.js)

No public repository matching the distinctive bundle or copy was found. The browser session did not observe a client-side article API call or common third-party analytics libraries. That does not prove there is no measurement: server logs, Vercel analytics, referral parameters, or code on unvisited routes could still provide it.

### Frontend reconstruction difficulty

A visually similar Struct publication is several engineer-days to two weeks. A Jodie-like watchlist, theme table, and ticker profile is perhaps three to six frontend engineer-weeks if built from scratch. In this repository, much of that surface already exists, so a useful integrated frontend is closer to one to three weeks after the data contracts stabilize.

The frontends are not the moat. Reproducing their appearance without the evidence system would create an attractive shell with weak research underneath.

## What Struct's article factory is doing

### Observable content compiler

Rendered Struct pages expose structured embed objects. Observed modules included:

| Embed family | Count |
|---|---:|
| metric_strip | 106 |
| valuation_snapshot | 15 |
| co_movement | 7 |
| relationship_map | 6 |
| mini_trend | 2 |
| breadth_comparison | 2 |

Internal identifiers included:

- fundamentals.revenue.latest;
- fundamentals.revenue_yoy.latest;
- fundamentals.operating_margin.latest;
- valuation.market_cap;
- valuation.enterprise_value_to_sales;
- valuation.price_to_earnings;
- market.last_close;
- market.one_day_move;
- recent, usual, and above-normal correlation metrics.

The [Amazon brief](https://struct.news/briefs/amazon-jumps-15-the-numbers-are-huge-the-payoff-still-depends-on-the-multiple) embedded an SEC accession, exact values and periods, source types, deterministic metrics, and an after-paragraph insertion position. This strongly indicates that prose and evidence widgets are compiled from a structured story packet.

The highest-confidence reconstruction is:

    SEC filings and XBRL + market data + Jodie analytics
        -> normalized company facts
        -> candidate anomaly and story detectors
        -> ranked fact and quote packet
        -> LLM draft with a prescribed story shape
        -> deterministic evidence-card insertion
        -> factual and formatting checks
        -> SEO metadata, JSON-LD, image, RSS, sitemap
        -> Struct article
        -> ticker CTA and social derivatives

This is efficient because the writer is not asked to rediscover every fact from a full filing. Filing parsing and calculations happen once. Compact, cited facts are reused by the ticker page, alert engine, article, search metadata, and social content.

### Is the prose AI-generated?

Confidence is greater than 99% that an LLM drafts the body:

- 23 articles were published within one hour.
- The fastest observed gaps were 41–49 seconds.
- A newer 35-story batch had a median interval of 119 seconds.
- All 143 pages had the same published and modified timestamp, with no visible editorial revision.
- Every piece used generic author and publisher name Struct.
- Twelve of 143 articles, or 8.4%, leaked generation directives such as parenthetical or bracketed instructions to insert metric, revenue-trend, co-movement, or relationship-map embeds.
- Two filing reads stopped abruptly after 56 and 57 words.
- Six 40-name co-movement articles appeared in rapid batches with nearly interchangeable framing.

The articles are well written because the problem has been constrained. The model receives a selected thesis, a small set of facts, named relationships, a template, a desired length, and positions for visual evidence. Good financial prose becomes much easier when discovery, arithmetic, and story selection are performed upstream.

The system looks more impressive than its token bill because **information architecture, not raw model intelligence, is doing most of the work**.

### What Struct is not currently using

The examined Struct corpus did not substantiate the user's initial assumption that it routinely synthesizes 13-F filings and earnings-call transcripts:

- zero 13-F mentions across the 143 observed articles;
- zero transcript or earnings-call sources;
- zero direct SEC hyperlinks;
- visible source families limited to SEC filing, Jodie calculation, market data, and Jodie evidence;
- repeated wording that filed results had no analyst estimates.

Of the 125 Filing Reads, 85 were labeled from July 31 10-Qs. The SEC's [July 31 daily master index](https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/master.20260731.idx) contained 179 10-Qs and 239 8-Ks. Struct therefore covered at most 47.5% of that day's 10-Q universe and likely much less of the complete earnings-release universe. It is not yet publishing on every earnings event.

### Quality failures matter

Struct's speed has already produced trust-breaking errors.

1. **Period alignment and arithmetic:** A [Chemed article](https://struct.news/briefs/chemed-is-being-priced-off-a-twoyear-growth-burst-even-though-revenue-slowed-to-41-last-year) described 2023 revenue growth as 88.5%. [SEC company facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000019584.json) show 2022 revenue of $2.134963 billion and 2023 revenue of $2.264417 billion, approximately 6.1% growth.

2. **Form classification and relationship ontology:** A [Synchrony relationship article](https://struct.news/briefs/who-synchrony-syf-is-actually-tied-to-walmart-paypal-amazon-and-a-fiserv-printing-shop) labeled three filings as 10-Ks although [SEC submissions](https://data.sec.gov/submissions/CIK0001601712.json) identify them as 10-Qs. It also leaked a relationship-map instruction, contained a truncated quote, and described an acquired business with a questionable investee label.

3. **Attribution:** The Amazon brief called Jodie-created bull, base, and bear CAGR and exit-P/E scenarios “the company's own scenario drivers.” Amazon's underlying [10-Q](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000026/amzn-20260630.htm) contains no such scenario. This collapses company-authored facts and publisher-created modeling into one voice.

4. **Timezone conversion:** The same article rendered a 22:11 UTC SEC acceptance time as 2:11 PM Eastern rather than 6:11 PM Eastern.

5. **Freshness:** Nine July 31 articles cited market evidence dated July 14, a 17-day lag, without clearly framing it as stale.

6. **Source receipts:** Despite the evidence branding, none of the 143 pages linked directly to sec.gov. Textual references are weaker than accession-level source links.

Jodie's live product also showed taxonomy and data-quality concerns:

- a group labeled Argentinian Regional Banks contained defense-oriented names;
- a Staffing Services group included names from unrelated software categories;
- a filing brief resolved the ordinary word “frontier” in an IOVA sentence to ticker FRO and called it a disclosed partner;
- GOOG and GOOGL could both appear and inflate breadth;
- an AMZN payload showed a normal volume multiple near 3.4 while generated driver prose described volume more than 607,000 times expected;
- theme display state, probability, strength, and activity fields could disagree materially.

Global operations were also uneven in the same snapshot: US and Asia theme timestamps were current to July 31, while Europe was dated June 18 and crypto June 3. A global selector is not useful unless every region carries an explicit freshness contract.

These are not cosmetic edge cases. They illustrate why Mastermind's advantage should be stricter evidence and correction machinery, not a higher publishing count.

## Business model, pricing, and marketing strategy

### Pricing correction

At inspection time, the [Pricing page](https://jodie.ai/pricing) offered:

- Free: delayed feed, three watchlist names, an exposure preview, and limited Confirmed or Watching context.
- Pro monthly: $29 per month, shown against a $39 list price, with a founding-rate lock.
- Pro annual: $290 per year, described as two months free.

The user's statement that $29 per month was billed annually is therefore not current page wording. The effective annual monthly equivalent is about $24.17.

Illustrative subscription economics, not an estimate of actual customers:

| Annual subscribers at $290 | Gross ARR |
|---:|---:|
| 1,000 | $290,000 |
| 5,000 | $1,450,000 |
| 10,000 | $2,900,000 |
| 25,000 | $7,250,000 |

At this price, a self-serve research product does not need institutional-scale accounts to support a small engineering and data operation. The hard question is conversion and retention, not text-generation cost.

### Acquisition system

Jodie and Struct appear to use three reinforcing acquisition loops:

1. **Programmatic ticker SEO**

   Thousands of ticker routes capture company-specific searches and create a permanent destination for every article CTA.

2. **Event-driven editorial SEO**

   Struct converts fresh filings, price moves, co-movements, and relationships into long-tail natural-language URLs with canonical tags, NewsArticle, Dataset, BreadcrumbList, and Organization structured data, Open Graph and X cards, images, RSS, and image sitemap entries.

3. **Product-led conversion**

   The article gives enough free evidence to establish interest, then moves the reader to the live ticker or theme in Jodie. Referral query parameters make conversion attribution possible.

The intended flywheel is:

    new source event
        -> new structured facts
        -> ticker dossier gets fresher
        -> free article captures search and social demand
        -> article sends reader to live Jodie context
        -> subscription funds broader coverage
        -> larger corpus creates more entry points

This is a good architecture. Its demonstrated execution is not yet mature. Struct was registered on July 30, 2026, according to its [RDAP record](https://rdap.identitydigital.services/rdap/domain/struct.news), and the public launch was approximately one day old at inspection. There is no credible public evidence yet of search rankings, traffic, conversion, retention, or payback.

### What data they collect

The current [Privacy Policy](https://jodie.ai/privacy) says Jodie may hold account email and display name, watchlists, alert settings, plan state, and request, device, and log information. Web billing uses Stripe; mobile billing uses RevenueCat. The policy says personal data is not sold or used to make investment recommendations.

The commercially valuable non-personal data is more likely to be:

- which tickers and themes users follow;
- which anomaly or filing pages drive clicks;
- which alerts produce return visits;
- free-to-paid conversion by article, ticker, and theme;
- watchlist overlap and latent demand;
- content formats that generate search or social acquisition.

That behavioral data can improve prioritization and product packaging even if it never becomes a trading feature.

Jodie's [Data License](https://jodie.ai/data-license) forbids bulk downloading, scraping, redistribution, resale, and model training from the public data. The recommendation in this memo is therefore an independent implementation from primary SEC and licensed market or transcript sources. We should learn from public product behavior and published methodology, not ingest their database or copy their source.

### Company maturity and ownership clues

Historical attribution is stronger than current corporate disclosure.

[Companies House officer records](https://find-and-update.company-information.service.gov.uk/company/12483828/officers) list Justin Francis Davies as director of JODIE THE AI LTD, appointed February 26, 2020. The [company record](https://find-and-update.company-information.service.gov.uk/company/12483828) says that entity was dissolved on August 9, 2022. Davies' 2020 engineering post explicitly says he used spaCy for Jodie.

The revived 2026 product, domain, and filing concept make founder continuity plausible, but current ownership and team size are not publicly established:

- the current legal pages do not name an operating entity;
- Jodie exposes no current team page or company address;
- Struct uses the generic author and publisher name Struct;
- Struct exposes no About, contact, corrections, or methodology page;
- the old UK company is dissolved.

The product itself shows launch-stage traits: a founding discount, a two-day article burst, dual Method and Methodology generations, stale global modes, a dead public webhook hostname at inspection, and schema contradictions. It may be a very small team with a highly automated stack; that is an inference, not a verified headcount.

## Mastermind and Macro Dashboard overlap

This repository already owns much of the necessary machinery:

| Needed capability | Current asset | Estimated useful overlap |
|---|---|---:|
| SEC XBRL cross-sections | collectors/edgar.py | 75–90% |
| Multi-year company facts | collectors/edgar_facts.py | 75–90% |
| Earnings filing anchors | collectors/edgar_earnings_8k.py | about 80% |
| Curated 13-F snapshots and diffs | collectors/edgar_13f.py | 70–80% |
| Qualitative earnings scorer | engine/earnings_qual.py | 45–60% |
| Transcript supply | collectors/finnhub_transcripts.py | 10–25% |
| Multi-horizon theme state | engine/theme_scoring.py | 80–90% |
| Subsector rotation | engine/subsector_rotation.py | 80–90% |
| Organic theme discovery | engine/theme_discovery.py | 75–90% |
| Residual-correlation breaks | engine/rotation_corr.py | 75–90% |
| Theme crowding | engine/theme_crowding.py | 75–90% |
| Ticker dossiers and UI | scripts/build_ticker_pages.py and ticker template | 70–85% |
| Marketing fact packets, writers, critics, validators | engine/marketing | 60–75% in code, lower operational maturity |
| Static SEO, canonical, and RSS platform | content/seo | 50–65% platform, 15–25% article factory |
| Freshness-gated Mastermind intake | existing brain bridges | 75–85% architectural |

The current local estate contained:

- 98,975 earnings 8-K date rows across 1,314 tickers;
- 22,458 fundamental-panel rows across 1,552 tickers;
- 8,784 company-year statement rows across 1,506 tickers;
- 3,431 qualitative earnings seed rows;
- 1,676 generated ticker pages;
- 505 research HTML pages;
- 104 Python modules under engine/marketing.

The conclusion is not “we need Jodie.” It is “Jodie reveals how to compose several things we already have into a better company-intelligence product.”

## Existing EquityDesk-derived Earnings Calls lobe: operational audit

### Verdict

The Earnings Calls lobe shown inside stage_analysis.html is substantial software, not a placeholder design. It was built from a logged-in EquityDesk teardown and partial/full data extraction during July 19–20. Its frontend, scoring harness, imports, comparison logic, season analysis, industry heatmap, transcript-reader drawer, tests, R2 transport seam, and local-worker design all exist.

It is nevertheless **not operational as an earnings-call product today**.

The “Warming up” state is caused by an integration break, not merely an engine waiting for its first nightly run:

1. The historical source data was captured locally.
2. Only part of it was converted into committed runtime seeds.
3. The dedicated Earnings Calls page reads a different parquet filename that is absent.
4. The nightly task treats an empty-but-valid artifact as success.
5. The separate live-worker object is also absent from R2.

The right action is to repair and subsume this lobe into the new company-intelligence spine. Building another transcript scorer beside it would duplicate useful code and preserve the broken data seam.

### What was actually acquired

The local archive at /Users/chriswong/Documents/Cluade/equitydesk_backfill occupied approximately 938 MB at inspection time. It included:

- full/earnings_call_data.json: approximately 595 MB and 50,053 rows;
- full/earnings_call_gics_industry_weekly.json: approximately 13 MB;
- full/company_generated_info.json: approximately 119 MB;
- full/news_history.json: approximately 15 MB;
- a broad set of stage, industry, price, alternative-data, company, theme, and ticker-mapping exports;
- _local_archive/backfill_analysis.parquet: 3,431 analyzed calls;
- _local_archive/scores.parquet: 3,431 normalized score rows.

The repository contains two committed seeds:

| Seed | Rows | Coverage |
|---|---:|---|
| data/stage_analysis/backfill/equitydesk_overview.parquet | 6,536 | 6,536 names across USA, Europe, and Asia |
| data/stage_analysis/backfill/earnings_seed.parquet | 3,431 | 3,430 tickers; calls from 2025-02-24 through 2026-07-17 |

The 3,431-row seed is the latest analyzed call per covered company, not the complete historical corpus. The full 50,053-row JSON was downloaded and an importer exists, but the complete call-history parquet is not present in the repository runtime.

So the answer to “did we import and backfill everything?” is:

- **Source capture:** largely yes; the full raw pull exists locally.
- **Partial normalized seed:** yes; 3,431 latest-call records were committed.
- **Full historical runtime import:** no.
- **Live ongoing ingestion:** no evidence it has ever produced or published a current score object.
- **Public Earnings Calls surface:** currently empty.

### Exact wiring failure

Two different data paths coexist.

The Stage Analysis context join in engine/stage_analysis.py reads:

    data/stage_analysis/backfill/earnings_seed.parquet
        plus
    data/earnings_calls/scores.parquet

It reduces those stores to the latest card per ticker. This path can add tone context to a Stage Analysis row.

The dedicated Earnings Calls surfaces in engine/earnings_qual.py instead read:

    data/stage_analysis/backfill/earnings_calls.parquet

That file is absent. The complete importer in scripts/import_equitydesk_full.py knows how to create it from the 50,053-row source archive, but it was not committed or made available to the nightly runner. The builder does not fall back to earnings_seed.parquet or data/earnings_calls/scores.parquet.

The result is deterministic:

- data/stage_analysis/earnings_table.json: zero rows;
- data/stage_analysis/earnings_season.json: zero quarters;
- data/stage_analysis/earnings_compare.json: zero rows;
- data/stage_analysis/ec_industry.json: zero rows;
- data/stage_analysis/ec_industry_heatmap.json: zero regions.

Those files were freshly regenerated at 2026-08-01T02:18:36Z. The browser sees an artifact, successfully parses it, finds no rows, and renders “Warming up.”

### Nightly operational evidence

The July 31 daily workflow log stated:

- earnings_calls/scores.parquet was not in R2;
- earnings_calls/manifest.json was also absent;
- zero files were fetched;
- the Prophet-stage fusion warned that the full earnings_calls.parquet was absent and degraded its earnings arm to zero;
- the Stage Analysis build nevertheless reported that four Earnings-Calls surfaces were built;
- the page builder copied the empty artifacts.

This is a fail-open observability bug. “Built” means the functions returned valid JSON envelopes, not that they contained any data. The workflow's final cancellation was unrelated to the local root cause: the Earnings Calls step itself completed successfully while producing empty output.

The focused implementation suites also passed 71 tests with two skips during this audit. They validate functions against fixtures and temporary seeds, but they do not assert that the production source exists or that a nightly build preserves a nonzero healthy row floor. This is a deployment-contract gap, not a lack of unit tests.

The UI copy “generated tonight” is therefore misleading. Repeated nightlies cannot populate a source file that no job creates or transports.

### What the existing lobe does well

The lobe is worth preserving:

- provider-agnostic transcript or 8-K scorer;
- local OpenAI-compatible Qwen path, with DeepSeek and Anthropic fallback;
- strict JSON output, one retry, then explicit degradation;
- source hashing and per-ticker upsert;
- normalized sentiment, performance, confidence, tone, evidence highlights, and pinned tags;
- display-only and context-only authority;
- deterministic scrubbing of trade language;
- per-call table, season risers/decliners, quarter-over-quarter comparison, and industry heatmap;
- transcript-reader drawer for summary, highlights, guidance, tags, and key quote;
- R2 publish/fetch seam and manifest design;
- a forward ledger and preregistered promotion discipline.

It also contains a decoded EquityDesk score:

    EC sentiment =
        call positivity
      + management confidence
      + future outlook
      - analyst criticism

This identity matched all 3,431 first-pass records. EquityDesk's combined value is sentiment plus performance. These are useful calibration targets, not decision-authorized scores.

### What remains incomplete

- No full call-history parquet reaches the nightly runner.
- No live scores or manifest exist in the configured R2 prefix.
- The Windows Qwen worker is documented but there is no evidence that it is scheduled, healthy, or publishing.
- The current transcript vendor remains undecided.
- The free fallback is an 8-K earnings release, not an earnings-call transcript.
- The scorer truncates source text at 24,000 characters, which may omit late-call analyst questions and risk language.
- The dedicated surfaces and per-stage ticker cards use different schemas and score scales.
- Full-text source spans and rights metadata are not part of the public artifact.
- Empty artifacts pass the nightly lane without a minimum-row or freshness assertion.
- The correction bus and source-version lifecycle are not persistent end to end.

### Repair plan

#### Immediate recovery: one to three engineer-days

1. Run the existing full importer against the already captured 50,053-row archive in a controlled staging directory.
2. Validate row counts, duplicates, dates, ticker identity, and generated file size.
3. Build the five Earnings Calls JSON surfaces from that history.
4. Publish the compact display artifacts; retain the large history in R2 or another governed data store rather than forcing raw text into git.
5. Change the UI from “generated tonight” to a truthful unavailable or stale message carrying the missing source and last successful row count.
6. Fail the earnings sub-lane, without breaking the entire daily build, when row count unexpectedly falls below its prior healthy floor.

This would unblank the historical product. It would not create a live transcript operation.

#### Operational forward lane: two to four engineer-weeks plus data decision

1. Replace the two competing schemas with company_event.v1 and a versioned earnings_call_analysis.v1.
2. Make one loader serve the ticker card, call table, season comparison, industry rollup, canonical article, X derivatives, and Mastermind context.
3. Choose a dependable transcript source and redistribution posture; preserve 8-K exhibits as an explicit fallback.
4. Schedule the producer, publish a heartbeat and manifest, monitor coverage lag, and alert on zero-new or stale runs.
5. Store full source text privately with source spans; distribute derived facts and short licensed excerpts only as rights permit.
6. Replay historical calls through the current validator and preserve source/model/prompt versions.
7. Add claim-level arithmetic, quote, period, and attribution checks before the call can feed an article.

### Should we reacquire EquityDesk?

Not for the current unblanking problem. The local archive already contains the full 50,053-row call export and the adjacent tables needed by the existing importer. Reopening a trial could be useful for a narrow delta check after July 17 or for confirming changed schemas, but it should not become a production dependency.

The durable system should compute from primary SEC sources and a properly licensed transcript/consensus source. EquityDesk data is most useful as a historical calibration and regression corpus, subject to its applicable terms—not as the live database behind Mastermind.

### Effect on the Jodie/Struct build estimate

This discovery reduces the article/transcript implementation burden but adds a mandatory repair gate:

- we can reuse the scorer, provider waterfall, UI, comparison logic, R2 seam, tests, and historical corpus;
- we must fix the source path, unify the contracts, activate a forward producer, and add provenance;
- the historical lobe can be visible within days;
- a trustworthy current call engine still requires two to four weeks plus a transcript-source decision;
- it should become the earnings-call branch of the same Company Event Spine, not remain a separate EquityDesk clone.

## The hard missing layer

### 1. Complete raw-document substrate

The current EDGAR collectors are strongest on structured XBRL facts and filing dates. The new system needs an immutable raw document store for:

- 10-K, 10-Q, and material 8-K documents and exhibits;
- Item 2.02 earnings releases;
- amendments and supersession chains;
- section boundaries and HTML tables;
- accession, filing, acceptance, and fiscal-period metadata;
- precise source spans and stable source URLs.

The SEC's [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) provide keyless submissions and XBRL endpoints, update throughout the day, and offer nightly bulk archives. These should be the primary source of record, with respectful rate limiting and an explicit user agent.

### 2. Transcript and consensus supply

The current Finnhub integration stores transcript metadata but not a reliable corpus of transcript bodies. Full transcript coverage and analyst consensus are the largest likely external-data expense and the main rights question if generated analysis is redistributed publicly.

A free-only system can still cover filings well. It cannot honestly claim complete, timely call analysis or consensus surprise without dependable sources. This choice must be made before promising “every earnings.”

### 3. Event-to-theme evidence graph

Current theme engines understand price and participation. They do not yet persist a source-cited relationship from a new statement such as:

- capex acceleration;
- backlog or remaining-performance-obligation change;
- pricing pressure;
- customer concentration;
- channel inventory;
- a supplier constraint;
- geographic demand;
- headcount or hiring;
- segment margin change;
- guidance raised, narrowed, or withdrawn;

into the company and theme graph.

This graph is where filings, transcripts, fundamentals, and market behavior become one system.

### 4. Canonical living story

The existing marketing system has a good packet-to-writer-to-validator-to-critic shape, but its schema is oriented toward social claims. The new article object needs:

- stable story ID and version history;
- event and accession IDs;
- exact claim objects rather than unstructured claim strings;
- direct source spans;
- numeric calculations and units;
- company-authored versus Mastermind-authored attribution;
- related tickers and themes;
- duplicate and update relationships;
- correction state and public correction note;
- derivative IDs for ticker update, article, X thread, and short posts.

### 5. Persistent operations

The current correction bus is in memory. This feature needs durable queues, idempotency, replay, audit logs, source-version pinning, and the ability to retract every derivative when an upstream fact changes.

## Recommended architecture

The source and truth plane should live in Macro Dashboard. Mastermind should consume a compact, point-in-time contract rather than duplicating collectors.

    SEC + transcript/consensus source + market data
                         |
                         v
              immutable raw source store
                         |
                         v
        company_event.v1 + company_fact_delta.v1
                         |
                         v
              company/theme evidence graph
                         |
             +-----------+------------+
             |                        |
             v                        v
    deterministic theme engines   canonical_story.v1
             |                        |
             +------------+-----------+
                          v
              company_intelligence.v1
                          |
        +---------+-------+-------+----------+
        |         |               |          |
        v         v               v          v
      ticker   Mastermind       article    X/content
      dossier   context          and SEO     accounts

### Core contracts

#### company_event.v1

- event ID and source-system ID;
- ticker, CIK, company identity, and aliases;
- event type, filing form, fiscal period;
- filed and accepted timestamps;
- amendment and supersession chain;
- source documents, content hashes, rights, and freshness;
- processing version and point-in-time availability.

#### company_fact_delta.v1

- metric name and canonical taxonomy;
- current actual, prior actual, consensus, and guidance;
- units, scale, period, segment, and currency;
- absolute and percentage changes calculated by code;
- source span and source classification;
- reconciliation and anomaly status.

#### company_theme_exposure.v1

- company and theme IDs;
- relationship type and direction;
- explicit filing or transcript evidence;
- first-seen and last-confirmed timestamps;
- confidence and validator;
- contradictions, expirations, and amendments;
- market confirmation as a separate field, never blended invisibly into source confidence.

#### company_intelligence.v1

- current dossier summary;
- recent event timeline;
- confirmed facts and unresolved conflicts;
- theme memberships and lifecycle;
- linked-company read-throughs;
- market response relative to sector and established residual group;
- data freshness, provenance, and rights;
- context-only fields explicitly separated from decision-authorized fields.

#### canonical_story.v1

- headline, dek, body blocks, and evidence cards;
- claim IDs and source spans;
- model, prompt, validator, and packet versions;
- published, updated, corrected, and withdrawn timestamps;
- related tickers and themes;
- SEO entities and canonical URL;
- derivative asset IDs and distribution receipts.

### Authority rule

The LLM may:

- extract candidate facts and quotes;
- classify a passage into a controlled ontology;
- propose a thesis from an approved fact packet;
- explain deterministic calculations;
- generate channel-specific prose.

The LLM may not:

- perform authoritative arithmetic;
- invent a metric or relation;
- create a conviction score;
- rank or size a trade;
- override freshness or rights;
- silently merge company facts with Mastermind scenarios;
- publish when a required source span or validator is missing.

Deterministic code owns reconciliation, calculation, ranking, promotion gates, and publication validation.

## Content and X strategy

The correct content unit is one canonical story, not one prompt per channel.

    source event
        -> one reconciled evidence packet
        -> one canonical thesis and story
        -> channel transformations

The transformations should include:

- ticker timeline entry;
- ticker dossier refresh;
- full research article when warranted;
- compact earnings brief;
- one evidence-dense X thread;
- several short posts with different hooks;
- chart or relationship-map card;
- alerts to relevant watchlists;
- Mastermind context object.

### Event tiers

Publishing a full article for every filing optimizes page count rather than value. Use three tiers:

| Tier | Trigger | Outputs |
|---|---|---|
| A | large surprise, material guidance change, active theme, major relationship read-through, or high-demand ticker | 800–1,500 word article, ticker update, X thread, chart cards, short posts, Mastermind context |
| B | ordinary but relevant earnings or filing | 250–600 word brief, ticker update, one or two short posts, Mastermind context |
| C | low-information or duplicative event | structured facts and timeline only; no indexable article |

Every Tier A story should answer:

1. What changed from the prior comparable period?
2. Which numbers actually mattered?
3. What changed in guidance, balance-sheet posture, or operating language?
4. Which theme does the event confirm or contradict?
5. Which peers, suppliers, customers, or competitors receive a read-through?
6. How did the security react relative to sector, market, and its established residual group?
7. What evidence would invalidate the interpretation?

### Multiple X accounts

The account network should not repeat the same generated post. Give each account an information role:

- fast earnings tape;
- deep filing receipts;
- sector and theme rotation;
- supply-chain read-through;
- valuation and scenario framing;
- charts and visual explainers;
- company-specific specialist feeds.

Every derivative references the same story ID and fact version. Hooks, length, and vocabulary can differ; facts cannot. Account-level experiments should optimize click-through, saves, qualified follows, ticker-page depth, and subscription conversion—not raw posting volume.

This creates a compounding loop:

    event coverage
      -> more useful ticker dossiers
      -> more indexable entry pages
      -> more X source material
      -> more watchlists and subscriptions
      -> better demand prioritization
      -> better event coverage

## Validation gates Struct currently lacks

Before public release, every story should pass:

1. **Accession gate:** form, filing date, accepted time, amendment state, and document URL match SEC metadata.
2. **Period gate:** instant versus duration facts, fiscal calendar, segment, unit, scale, and comparative period are reconciled.
3. **Arithmetic gate:** every percentage and multiple is recomputed by deterministic code.
4. **Freshness gate:** market data age is explicit and within the story family's service level.
5. **Quote gate:** every quote is an exact source substring with accession and location.
6. **Attribution gate:** company statement, analyst consensus, market observation, and Mastermind scenario have different source classes.
7. **Relation gate:** relationship type, direction, entity identity, negation, and evidence are validated.
8. **Embed gate:** only declared structured cards can render; prompt instructions or placeholders cause rejection.
9. **Completeness gate:** minimum length, required sections, balanced truncation, and terminal punctuation.
10. **Deduplication gate:** semantic similarity and event identity prevent near-identical stories.
11. **Promotion gate:** a detected relationship or co-movement stays context-only until its own validation permits greater authority.
12. **Correction gate:** changing an upstream fact invalidates the article, ticker, X, and Mastermind derivatives together.

The product promise should be **fewer false receipts**, not merely faster prose.

## Token and generation economics

### Likely Struct launch-run cost

The 143 observed bodies contained 68,728 words, approximately 91,000 output tokens. Titles, deks, structured metadata, and discarded drafts likely keep final-output generation near 100,000 tokens.

Because pages expose compact structured facts and excerpts, a plausible launch-run envelope is:

- 0.3–1.0 million input tokens;
- approximately 0.1 million output tokens;
- additional image generation for 143 fixed-format editorial images.

If the full raw filing were sent to the writer for every article, the input could be many times larger. The evidence packet design strongly suggests that Jodie amortizes extraction and sends the writer only selected facts.

Using current standard OpenAI API prices from the [official pricing page](https://developers.openai.com/api/docs/pricing):

| Model | Input per million | Output per million | Estimated 143-story text run |
|---|---:|---:|---:|
| GPT-5.4 mini | $0.75 | $4.50 | about $0.68–$1.20 |
| GPT-5.6 terra | $2.00 | $12.00 | about $1.80–$3.20 |
| GPT-5.6 sol | $5.00 | $30.00 | about $4.50–$8.00 |

This is an estimate, not knowledge of their vendor, model, retries, or prompts. Image cost may exceed prose cost. Either way, tokens do not explain or constrain the business.

### Mastermind quality budget

A high-quality two-stage event flow should budget:

- extraction and reconciliation proposal: 6,000–10,000 input plus about 1,000 output tokens;
- canonical article and critic: 15,000–25,000 input plus 2,000–4,000 output;
- total: 21,000–35,000 input plus 3,000–5,000 output per event.

Approximate per-event standard API cost:

| Model | Low packet | High packet |
|---|---:|---:|
| GPT-5.4 mini | $0.029 | $0.049 |
| GPT-5.6 terra | $0.078 | $0.130 |
| GPT-5.6 sol | $0.195 | $0.325 |
| Claude Sonnet 5 introductory price | $0.072 | $0.120 |

The [official Anthropic pricing page](https://platform.claude.com/docs/en/about-claude/pricing) listed Sonnet 5 at an introductory $2 per million input and $10 per million output through August 31, 2026, moving to $3 and $15 afterward. Batch processing and prompt caching can lower applicable costs materially.

At 10,800 events per year, approximately 2,700 tickers times four:

| Model | Base annual text cost |
|---|---:|
| GPT-5.4 mini | $316–$527 |
| GPT-5.6 terra | $842–$1,404 |
| GPT-5.6 sol | $2,106–$3,510 |
| Sonnet 5 introductory | $778–$1,296 |
| Sonnet 5 regular | $1,166–$1,944 |

Add roughly 25–75% for retries, evaluations, exceptional long documents, and failed validators. X derivatives should add less than 10% if generated from the canonical story rather than from raw documents.

Even at a peak of 100 events in one day, estimated high-quality text cost is only:

- GPT-5.4 mini: about $2.93–$4.88;
- GPT-5.6 terra: about $7.80–$13.00;
- GPT-5.6 sol: about $19.50–$32.50.

The real cost centers are:

1. transcript and consensus rights;
2. data normalization and point-in-time storage;
3. exception and correction handling;
4. peak earnings-season orchestration;
5. source-linked visual generation;
6. engineering and research QA.

## Build difficulty, staffing, and operating cost

### Difficulty by component

| Component | Difficulty | Why |
|---|---|---|
| Struct-like publication frontend | Easy | standard Next.js/static content and structured data |
| Jodie-like theme/ticker UI | Easy to moderate | UI is conventional; current Terminal already overlaps |
| SEC raw archive and parser | Moderate to hard | forms, exhibits, custom XBRL, periods, amendments |
| Residual correlation and community discovery | Moderate | well-known methods; point-in-time calibration and lineage are harder |
| Filing relationship graph | Hard | entity resolution, relation direction, evidence, expiry, amendments |
| Full transcript and consensus coverage | Hard commercially | licensing and rights, not only code |
| Story compiler | Moderate | easy to draft; hard to validate, deduplicate, correct, and attribute |
| SEO and X fan-out | Moderate | infrastructure exists; governance and differentiation matter |
| Production reliability | Hard | idempotency, replay, freshness, corrections, monitoring |

### Delivery estimate

With a dependable transcript or estimates provider:

- contract and rights decisions plus a golden corpus: 1–2 weeks;
- S&P 500 raw-document ingestion and fact extraction: 3–5 weeks;
- event-to-theme graph and Mastermind bridge: 3–4 weeks;
- article compiler, validation, SEO, RSS, and X derivatives: 3–5 weeks;
- scale and harden for S&P 1500 or broader: 4–8 weeks.

For a greenfield company trying to reproduce the whole observable Jodie and Struct suite, including identity, billing, watchlists, international operations, community lineage, relationship graph, publication, and alerts, the credible range is three to five strong engineers or quant/data specialists for four to eight months, followed by additional hardening toward month nine to twelve and one to two ongoing FTE. That is the answer to literal parity.

Mastermind should not pay that greenfield cost. Reusing its existing collectors, theme engines, dossiers, content infrastructure, and EquityDesk-derived lobe produces the narrower totals below.

Practical totals:

- useful top-500 MVP: **8–12 engineer-weeks**;
- free-source-only MVP: **12–20 engineer-weeks**, with weaker transcript, consensus, and latency coverage;
- production-grade broad suite: **6–10 engineer-months total**, roughly two senior engineers over three to five calendar months;
- integrated frontend: **one to three weeks** after contracts stabilize;
- early maintenance: **0.5–1.0 FTE**;
- steady-state maintenance: **0.25–0.5 FTE**.

### Planning budget

These are planning ranges, not vendor quotes:

| Cost family | MVP / early scale | Broad production |
|---|---:|---:|
| Build labor, fully loaded | $150,000–$350,000 total | depends on team and whether internal |
| Incremental compute, storage, queues, search | $300–$2,000/month | $1,000–$5,000/month |
| LLM text generation | $25–$200/month | $50–$500/month |
| New data rights | $2,000–$10,000+/month | $5,000–$25,000+/month; institutional redistribution may be much higher |
| Ongoing engineering/research operations | 0.5–1 FTE initially | 0.25–0.5 FTE after stabilization |

The range for external data is deliberately wide. SEC filings are free, but reliable transcript bodies, analyst consensus, real-time redistribution, and broad commercial use can dominate the entire infrastructure bill.

## Recommended phased build

### Phase -1 — Recover the existing Earnings Calls surface

Duration: one to three engineer-days.

- Materialize and validate the already captured EquityDesk history.
- Restore non-empty call, season, comparison, and industry artifacts.
- Add row-count, freshness, and missing-source alarms.
- Keep the restored output historical, display-only, and clearly dated.
- Do not wait for a new Jodie-style engine before fixing the existing broken contract.

Exit test: the public Earnings Calls tab shows real dated rows and every nightly refuses to call a zero-row regression healthy.

### Phase 0 — Truth benchmark

Duration: one to two weeks.

- Select 100 companies and 200 historically difficult events.
- Include non-calendar fiscal years, banks, insurers, REITs, ADRs, split share classes, amendments, custom XBRL, missing consensus, and long exhibits.
- Define the five core contracts.
- Select transcript and consensus rights posture.
- Establish point-in-time expected outputs and correction tests.

Exit test: deterministic recomputation and source spans pass on the golden corpus; no model-authored score can enter a decision surface.

### Phase 1 — Company Event Spine

Duration: three to five weeks.

- Store immutable SEC documents and metadata.
- Parse sections, exhibits, tables, and accession chains.
- Generate company_event.v1 and company_fact_delta.v1.
- Reconcile periods, units, taxonomies, and amendments.
- Add direct SEC source links to every accepted fact.
- Update ticker timelines without generating public articles yet.

Exit test: at least 98% of required filing events arrive within the service level; all published numeric deltas reproduce from source values.

### Phase 2 — Relationship and Theme Join

Duration: three to four weeks.

- Build entity and relation candidates from filings.
- Validate source spans and relation direction.
- Connect events to the existing theme discovery, rotation, correlation, and crowding systems.
- Add group lineage, share-class normalization, and null-calibrated formation alerts.
- Export company_intelligence.v1 through a new Mastermind single-reader bridge.

Exit test: no alert can lose its source lineage; live group labels pass human review on a held-out set; context is visibly separate from conviction.

### Phase 3 — Governed Research Compiler

Duration: three to five weeks.

- Create canonical_story.v1 and a persistent correction graph.
- Implement Tier A, B, and C selection.
- Generate article, dossier update, evidence cards, and X derivatives from one packet.
- Enforce all twelve validation gates.
- Publish to existing SEO and ticker surfaces.
- Add story and derivative receipts.

Exit test: zero arithmetic, attribution, accession, placeholder, or source-link defects across a shadow run of at least 500 stories.

### Phase 4 — Scale and optimize

Duration: four to eight weeks.

- Expand universe by liquidity and product demand.
- Add transcript and consensus if rights allow.
- Tune selection for subscriber conversion and retention.
- Add correction replay, provider failover, and incident dashboards.
- Run controlled comparisons of article quality, acquisition, and downstream decision usefulness.

Exit test: stable coverage through an earnings peak, measurable dossier engagement and qualified acquisition, and no evidence that context promotion degrades out-of-sample decisions.

## What not to rebuild

Do not copy:

- Jodie's opaque probability and promotion scales;
- the current public pressure score as an authority;
- a second authentication, billing, watchlist, or ticker-profile stack;
- Struct's generic page flood;
- AI-generated numeric calculations;
- unsourced filing quotes;
- an article for every event;
- 13-F buying as a positive alpha factor;
- theme detections directly into rank, conviction, position size, or execution;
- Jodie's public data or source in violation of its license.

Do not spend the first quarter perfecting the frontend. The existing dossier and Terminal are adequate places to prove the intelligence.

## Go / no-go conditions

Proceed if:

- the feature is framed as company, theme, and attention intelligence;
- primary-source provenance is non-negotiable;
- Macro Dashboard remains the source-and-truth owner;
- Mastermind consumes one governed contract;
- content fan-out shares one canonical fact version;
- a transcript and consensus decision is made explicitly;
- success is measured in research usefulness, qualified acquisition, and retention—not page count.

Pause or narrow the build if:

- the business case requires proven Jodie-style directional alpha;
- redistribution rights make transcript or consensus economics unacceptable;
- the team cannot own corrections and source integrity;
- the project is reduced to a frontend clone;
- publishing speed is prioritized over evidence accuracy.

## Final assessment

Jodie and Struct validate a powerful product composition:

    machine-readable filings
      + residual market structure
      + business relationships
      + compact LLM synthesis
      + permanent ticker and article pages
      + social distribution
      = a low-marginal-cost intelligence and acquisition loop

But their public evidence does not validate a powerful trading oracle. Jodie's own methods reject that interpretation, and the current public data exposes enough inconsistency to make blind score replication a mistake.

Mastermind should build the stronger version:

- use existing theme engines rather than importing opaque weights;
- add a reliable company-event and relationship spine;
- make every important sentence traceable to a source;
- update the dossier before deciding whether an article deserves to exist;
- generate every channel from one canonical story;
- use X and SEO as distribution for research, not as a volume game;
- keep descriptive context separate from decision authority;
- make corrections and point-in-time truth part of the product.

The frontend is easy. The prose is cheap. The valuable system is the evidence graph and its operational memory.

## Source ledger

Primary product and methodology:

- [Jodie Method](https://jodie.ai/method)
- [Jodie Methodology](https://jodie.ai/methodology)
- [Jodie Use Cases](https://jodie.ai/use-cases)
- [Jodie Pricing](https://jodie.ai/pricing)
- [Jodie Privacy](https://jodie.ai/privacy)
- [Jodie Terms](https://jodie.ai/terms)
- [Jodie Data License](https://jodie.ai/data-license)
- [Jodie public US themes API](https://jodie.ai/api/themes?mode=equities&region=us&limit=500&include_weak=true)
- [Jodie NVDA ticker API](https://jodie.ai/api/ticker/NVDA?compact=1&region=us)
- [Jodie NVDA exposures](https://jodie.ai/api/ticker/NVDA/exposures)
- [Jodie NVDA filing assessment](https://jodie.ai/api/ticker/NVDA/filing-assessment)
- [Jodie Activity Radar](https://www.tradingview.com/script/Aj6DokrJ-Jodie-Activity-Radar-Heat-Score/)
- [Raw public Pine source](https://pine-facade.tradingview.com/pine-facade/get/PUB;15223bab4d1541c4afb718c04e803fc0/last)

Struct surfaces and code:

- [Struct homepage](https://struct.news/)
- [Struct sitemap](https://struct.news/sitemap.xml)
- [Struct RSS](https://struct.news/feed.xml)
- [Struct robots.txt](https://struct.news/robots.txt)
- [Struct custom frontend bundle](https://struct.news/_next/static/chunks/27p9zk-cmfaio.js)
- [Struct RDAP record](https://rdap.identitydigital.services/rdap/domain/struct.news)

Verification examples:

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [SEC July 31, 2026 master index](https://www.sec.gov/Archives/edgar/daily-index/2026/QTR3/master.20260731.idx)
- [Amazon 2026 Q2 10-Q](https://www.sec.gov/Archives/edgar/data/1018724/000101872426000026/amzn-20260630.htm)
- [Amazon submissions](https://data.sec.gov/submissions/CIK0001018724.json)
- [Chemed company facts](https://data.sec.gov/api/xbrl/companyfacts/CIK0000019584.json)
- [Synchrony submissions](https://data.sec.gov/submissions/CIK0001601712.json)
- [Historical Jodie NER engineering article](https://medium.com/@justindavies/training-spacy-ner-models-with-doccano-8d8203e29bfa)
- [Historical Jodie company record](https://find-and-update.company-information.service.gov.uk/company/12483828)
- [Historical Jodie officer record](https://find-and-update.company-information.service.gov.uk/company/12483828/officers)

Model pricing:

- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing)
- [Anthropic API pricing](https://platform.claude.com/docs/en/about-claude/pricing)

Evidence caveat: all public-site and API observations are a point-in-time snapshot. Inferred formulas and architecture are labeled as inferences. No private Jodie or Struct code, database, model prompt, customer count, conversion data, or vendor contract was accessed.
