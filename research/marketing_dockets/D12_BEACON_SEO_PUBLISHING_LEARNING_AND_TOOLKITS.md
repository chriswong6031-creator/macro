# MKT-D12 — Beacon SEO Publishing, Learning, and Public Toolkits

**Department:** Beacon (Organic Search & Public Pages)

**Supporting departments:** Workshop, Studio, Radar, Funnel, Lab, Sentinel

**Priority:** P1 program; MKT-SEO-00 and MKT-SEO-01 are P0 foundations

**Status:** W0 READY FOR A SPECIALIST CLAUDE SESSION — docket only; no D12 product code has shipped

**Operator request:** Launch a native blog, a TrendSpider-University-style Learning Center, free calculators, recurring market toolkits such as new 52-week highs and recent insider transactions, and the additional SEO systems worth building now.

**Canonical relationship:** This docket is an additive execution program beneath `research/NEURAL_WEB_AUTONOMOUS_MARKETING_LOBE_GRANDMASTER_PLAN_FOR_FABLE.md`, `research/TRENDSPIDER_GROWTH_SEO_AND_GUERRILLA_MARKETING_INTELLIGENCE_FOR_FABLE.md`, and `research/MARKETING_DEMAND_CAPTURE_AND_GROWTH_ACCELERATION_DOCKET_FOR_FABLE.md`. It does not replace the Growth OS, the first-1,000-leads distribution strategy, or existing Marketing dockets.

**Index coordination:** At drafting time, open PR #3092 is already editing `research/marketing_dockets/INDEX.md`. This docket intentionally avoids that collision. Register D12 in the index after #3092 merges or closes; the direct path in this header is the handoff authority until then.

---

## 0. Copy-ready launch directive for the SEO specialist

> Read `CLAUDE.md`, `docs/ACTIVE_BUILD_MAP.md`, `research/DO_NOT_REBUILD.md`, `research/marketing_dockets/INDEX.md`, this docket, `research/TRENDSPIDER_GROWTH_SEO_AND_GUERRILLA_MARKETING_INTELLIGENCE_FOR_FABLE.md`, `research/MARKETING_DEMAND_CAPTURE_AND_GROWTH_ACCELERATION_DOCKET_FOR_FABLE.md`, and D10 before changing code. If PR #3092 has merged, also read `research/MARKETING_FASTEST_PATH_TO_FIRST_1000_QUALIFIED_LEADS_FOR_FABLE.md`; otherwise inspect #3092 as an active collision and do not depend on its unmerged files. Work from fresh `origin/main`; inspect open Marketing PRs and do not collide with them. Treat the shipped ticker dossiers, report renderer, confluence screener, movers page, UTM link builder, and Congress page as reusable infrastructure, not greenfield work. First execute MKT-SEO-00, then build the MKT-SEO-01 vertical slice: one native blog article, one Learning Center lesson, one calculator, and one living toolkit through a shared publication contract, complete metadata, sitemap, internal links, analytics, and tests. Do not scale article count until that slice renders, is crawlable, passes the indexation governor, and records a useful continuation event. After the substrate passes, execute MKT-SEO-02 through MKT-SEO-05 in dependency order. Sonnet builders receive explicit NO GIT instructions; Opus reviews search architecture, claims, and public data boundaries; user-facing surfaces receive the required design review. Finish each bounded wave by commit, PR, same-day squash merge, docket status update, and artifact verification.

The first specialist session should not attempt to write thirty articles and six applications at once. Its job is to establish the canonical publishing machine, prove one complete object from each page family, and leave the next content wave mechanical and safe.

---

## 1. Executive ruling

### 1.1 What to build now

Build one connected organic-acquisition estate with five public surfaces:

1. **Mastermind Blog:** current market explainers, original data stories, methodology articles, and product intelligence in a native, indexable publication system.
2. **Mastermind Learning Center:** structured learning tracks with evergreen lessons, interactive examples, common traps, and direct links into live tools.
3. **Calculator Lab:** free, fast, genuinely useful calculators whose results are available before signup.
4. **Living Market Toolkits:** stable URLs for recurring, data-backed jobs such as new 52-week highs, recent Form 4 activity, earnings-week risk, and market breadth.
5. **Beacon control plane:** Search Console feedback, page-family analytics, sitemap and canonical governance, internal-linking rules, structured data, freshness/noindex state, crawl monitoring, and retirement decisions.

The estate must work as a loop:

```text
query or AI answer
  -> useful article, lesson, calculator, toolkit, or ticker dossier
  -> inspect evidence or perform a real task
  -> continue to a related live object
  -> monitor a ticker, save a result, request a deep dive, or return later
  -> search-demand and activation data flow back to Beacon
  -> refresh, expand, merge, or retire the page family
```

### 1.2 What not to build

Do not answer TrendSpider's 2,500-plus article estate with an indiscriminate AI article factory. Google explicitly warns that large quantities of pages made primarily to manipulate rankings or AI answers can constitute scaled-content abuse. The advantage here is not article volume. It is proprietary evidence, live market objects, historical receipts, and useful calculations that generic publishers cannot reproduce cheaply.

Do not rebuild:

- the approximately 1,460 shipped ticker dossiers;
- their canonical URLs, Article JSON-LD, stale-page noindex state, sitemap merger, or share cards;
- the public confluence screener;
- `/movers.html`;
- the existing Research Reports renderer and templates;
- `/congress_trades.html`;
- D07 UTM and attribution infrastructure;
- D10 Workshop W1;
- MKT-ACC's Ticker Guardian, dossier-intent, and conversion work.

### 1.3 The first 30-day target

After the foundational vertical slice passes, the initial public estate should contain:

- one native Blog hub and **eight** strong launch articles;
- one Learning Center hub, six learning tracks, and **twelve** cornerstone lessons;
- one Tools hub and **three** calculators;
- **three** living market toolkits;
- one About/author entity, one public methodology page, one corrections page, and one automation/process explanation;
- one blog RSS or Atom feed and one living-tool update feed;
- a sitemap index split by page family;
- page-family Search Console and acquisition reporting;
- internal links connecting every new page to a live ticker, tool, lesson, report, or monitoring continuation.

This is a launch target, not an instruction to index every page automatically. The indexation governor makes the final call per URL.

---

## 2. Current repository reality

### 2.1 What is already built

The current `origin/main` audit found:

| Capability | Current state | Canonical evidence |
|---|---|---|
| Ticker SEO estate | Approximately 1,460 stock dossier URLs in a 1,472-URL sitemap | `scripts/build_ticker_pages.py`, `templates/ticker.html.j2`, `site/stocks/`, `tests/test_ticker_pages.py` |
| Ticker metadata | Unique titles/descriptions, canonical URL, Open Graph, share card, Article JSON-LD, freshness, stale noindex | `templates/ticker.html.j2`, `scripts/build_ticker_pages.py` |
| Sitemap | Existing stock-aware merger preserving non-stock URLs | `scripts/build_ticker_pages.py::build_sitemap`, `site/sitemap.xml` |
| Public reports | Six registered long-form report templates and searchable report index | `scripts/build_reports.py`, `templates/article_base.html.j2`, `templates/reports.html.j2` |
| Existing education | One standalone interactive Gamma Weather field manual, not a multi-topic Learning Center | `site/learn.html` |
| Free tools | Confluence screener and movers page with tagged CTAs and share cards | D10, `scripts/build_confluence_screener.py`, `scripts/build_movers_page.py` |
| Congress transactions | Existing public Congress page | `templates/congress_trades.html.j2`, `site/congress_trades.html` |
| 52-week-high calculations | Existing reusable facts and indicator functions | `engine/marketing/chart_facts.py`, `engine/momentum_context_signals.py` |
| Insider data | SEC Form 4 collector/panel plus fresher licensed Quiver lane and event wire | `collectors/sec_insider.py`, `engine/ownership_event_wire.py`, `data/sec_insider/` |
| Marketing attribution | Canonical tagged links and short-link infrastructure | `engine/marketing/links.py` |
| Beacon charter | Dossier, sitemap, schema, freshness, canonical, internal-link, receipt-page, demand-feedback, crawl, and speed engines are named | `engine/marketing/departments.py` |

### 2.2 What is actually missing

- There is no native `/blog/` publication estate.
- The current `learn.html` is one excellent specialist field manual, not a hub, curriculum, lesson registry, or reusable lesson renderer.
- There is no canonical calculators directory, calculator contract, or tools catalog.
- There is no stable public new-highs toolkit or recent-insider toolkit.
- The sitemap is dominated by stock pages and is not separated by page family.
- The report renderer is hand-registered and useful for a small number of polished reports, but is not a scalable editorial CMS.
- There is no unified content frontmatter contract for author, evidence, search intent, freshness, source packet, related tools, and index state.
- Search Console query/page data is not yet a closed feedback loop into Beacon.
- Internal linking is mostly page-local and navigation-driven rather than a measured topic/entity graph.
- Structured data is strong on ticker dossiers but is not consistently designed for articles, lessons, breadcrumbs, public datasets, videos, and tools.
- There is no page-family refresh queue or merge/retire ledger.

### 2.3 The active-build collision

The first-1,000-qualified-leads program is an active Marketing lane. Its ruling is that distribution, not content supply, is the immediate bottleneck. D12 does not dispute that. SEO is a compounding background channel and a destination estate for partners, X, YouTube, communities, and AI assistants.

The relationship is:

- the first-1,000 program chooses offers, distributors, and launch objects;
- D12 makes those objects searchable, durable, internally linked, and measurable;
- MKT-ACC turns visits into remembered intent and a second value event;
- D07 and the Growth Event Spine determine whether search traffic becomes retained value.

Do not delay the first partner pilots until the full Learning Center exists. Do not scale SEO pages without a useful continuation.

---

## 3. Organic-search strategy

### 3.1 The three content systems

#### A. Evergreen education

Answers durable questions and builds topical authority:

- what a concept is;
- how a calculation works;
- how to interpret a public filing or market statistic;
- common mistakes;
- when the concept is useful and when it is not;
- a live example from Mastermind.

Home: Learning Center and selected Blog explainers.

#### B. Current editorial

Captures fresh intent and distributes original research:

- what changed;
- why an asset or theme is moving;
- what a release revealed;
- a market myth examined with current data;
- a public outcome review;
- a data story derived from a toolkit.

Home: Blog. Stable current-event pages should be updated at one canonical URL when the user job persists; disposable daily observations remain social/feed objects or noindex pages.

#### C. Living utility

Lets the visitor do something repeatedly:

- calculate;
- screen;
- compare;
- inspect current filings;
- see new highs/lows;
- follow an event or ticker;
- download a rights-cleared public dataset.

Home: Tools and Markets. These are the best backlink and return-visit candidates.

### 3.2 Page-family contract

| Family | Primary search intent | Unique value requirement | Update mode | Exact continuation |
|---|---|---|---|---|
| Blog article | understand a current issue or original analysis | original chart, dataset, receipt, or expert synthesis | event-driven or editorial update | related toolkit, ticker, lesson, or monitor |
| Learning lesson | learn a durable concept | interactive example, Mastermind evidence, common trap | review clock | practice tool, next lesson, or live page |
| Calculator | solve one bounded numeric problem | correct formula, immediate result, explainable assumptions | formula/version update | save/share, related lesson, or live data |
| Living toolkit | inspect a changing public market state | fresh data, filters, provenance, timestamp, change history | nightly/event | follow object, open ticker, subscribe to changes |
| Ticker dossier | research one security | existing rich multi-engine state | nightly | monitor ticker, compare, request deep dive |
| Dataset page | inspect or download a public derivative | rights-cleared data, methodology, version history | scheduled | feed/API, related article, monitoring |
| Comparison | choose between instruments/products/concepts | substantive normalized table and dated methodology | review clock | open dossiers or relevant product |

### 3.3 The index-worthiness test

A page may become `index_candidate` only when all of the following are true:

1. **Intent:** there is a coherent user question or recurring job.
2. **Originality:** the page contains a proprietary calculation, original research, interactive utility, or unusually complete synthesis.
3. **Completeness:** a visitor can finish the promised job without returning to Google for the missing answer.
4. **Evidence:** sources, methodology, `as_of`, and limitations are visible where relevant.
5. **Freshness:** the owner and update/expiry rule are known.
6. **Difference:** the page is not a near-duplicate of a ticker dossier, report, lesson, or another URL.
7. **Continuation:** one exact next value action is available.
8. **Performance:** core content is present in static HTML and the page meets the new-page performance budget.
9. **Rights:** public use of data, images, and quotes is permitted.
10. **Trust:** title, description, visible content, and structured data make the same promise.

If any item is missing, publish as `noindex` or keep the object private until repaired. A null does not block building the capability; it blocks promoting the URL into the index.

---

## 4. Information architecture

### 4.1 Initial public routes

Use the current static-host conventions until hosting rules are explicitly confirmed. Do not assume invisible URL rewrites.

```text
site/
  blog/
    index.html
    <slug>.html
  learn/
    index.html
    technical-analysis/
    options-market-structure/
    fundamentals-valuation/
    ownership-filings/
    macro-cross-asset/
    mastermind-methodology/
  tools/
    index.html
    calculators/
      drawdown-recovery.html
      earnings-implied-move.html
      portfolio-concentration.html
    market-data/
      new-52-week-highs.html
      recent-insider-transactions.html
      earnings-this-week.html
  methodology/
    index.html
    <tool-or-dataset>.html
  authors/
    mastermind-research.html
  corrections.html
  llms.txt
  brand-facts.json
```

Before moving the current `site/learn.html`, confirm Cloudflare/static-host redirect support and external references. Preferred migration:

1. move the Gamma Weather lesson to `/learn/options-market-structure/gamma-positioning.html`;
2. create `/learn/index.html` as the Learning Center hub;
3. issue a real permanent redirect from `/learn.html` to the new lesson or retain a compact legacy router with one canonical;
4. never serve two indexable copies of the same lesson.

### 4.2 Source and builder layout

Recommended canonical source boundary:

```text
content/
  seo/
    blog/
      <slug>.md
    learn/
      <track>/<slug>.md
    calculators.yml
    toolkits.yml
    authors.yml
    tracks.yml
config/
  seo.yml
engine/marketing/seo/
  contracts.py
  indexation.py
  internal_links.py
  search_demand.py
  schema.py
scripts/
  build_seo_publications.py
  build_seo_tools.py
  build_sitemap_index.py
  collect_search_console.py
templates/
  seo_base.html.j2
  blog_index.html.j2
  learning_index.html.j2
  learning_lesson.html.j2
  tools_index.html.j2
  calculator_base.html.j2
  toolkit_base.html.j2
tests/
  test_seo_contracts.py
  test_seo_render.py
  test_seo_indexation.py
  test_seo_links.py
  test_seo_sitemaps.py
```

This is a suggested boundary, not permission to fork shared components. Reuse `_navlinks.html.j2`, `theme.css`, the report article styles where appropriate, `engine.marketing.links`, share-card infrastructure, and existing ticker page context.

### 4.3 Publication frontmatter contract

Every Blog or Learning source declares:

```yaml
id: seo_<stable_id>
family: blog | lesson
slug: stable-kebab-slug
title_en: ...
title_zh: ...
description_en: ...
description_zh: ...
cluster: ownership_filings
search_intent: informational
primary_question: How should investors interpret insider buying?
author_id: mastermind_research
published_at: 2026-07-20T00:00:00-07:00
updated_at: 2026-07-20T00:00:00-07:00
as_of: 2026-07-20
source_packet:
  - source_id_or_url
evidence_artifacts:
  - site_or_data_artifact
index_request: candidate | noindex
refresh_policy: event | 30d | 90d | annual
expires_at: null
related_tickers: []
related_lessons: []
related_tools: []
cta_id: monitor_ticker | open_tool | next_lesson | request_deep_dive
hero_image: ...
image_rights: owned | generated | licensed | none
automation_method: assisted | deterministic | none
```

The source requests indexation. `engine/marketing/seo/indexation.py` decides the rendered state and records the reason.

---

## 5. Native Blog program

### 5.1 Blog mandate

The Blog is a native publishing surface, not a renamed reports page and not an X-post archive. It should publish four editorial lanes:

1. **What Changed:** a material state change with evidence, mechanism, contradiction, and next condition.
2. **Data Stories:** original findings from toolkits, public datasets, receipts, and market history.
3. **How the Market Works:** durable explainers connected to live Mastermind objects.
4. **Outcome Reviews:** what happened after a prior claim, including misses and corrections.

Research Reports remain the home for large, polished recommendation-blog-style pieces. The Blog handles smaller, faster, internally linked objects. Do not duplicate a report into a blog post; write a short doorway with a distinct question and canonical link to the report if needed.

### 5.2 Launch article set

The first eight should be built around assets already in the repository:

| Working title | Unique Mastermind asset | Destination loop |
|---|---|---|
| What a New 52-Week High Actually Tells You | `chart_facts` and momentum context; live high toolkit | lesson → new-high toolkit → ticker dossier |
| Insider Buying: Transaction Date, Filing Date, and the Two-Day Gap | SEC Form 4 panel and event wire | recent-insider toolkit → ticker dossier |
| Why Congress Trades Are Not Real-Time Signals | existing Congress page and documented filing lag | Congress page → ownership lesson |
| VWAP vs. Anchored VWAP: Same Average, Different Question | shipped indicator work and chart examples | technical lesson → confluence screener |
| Volume Profile and Point of Control Without the Mystique | shipped volume-profile infrastructure | lesson → screener → ticker example |
| Implied Earnings Move vs. Realized Move | options/earnings data and calculator | calculator → earnings toolkit |
| How to Read Market Breadth Without Counting Headlines | breadth engines and current market context | breadth lesson → movers/toolkit |
| Gamma Exposure: Positioning, Not Prophecy | existing Gamma Weather field manual | updated lesson → live board |

After the launch set, let Search Console queries, partner questions, on-site requests, and Radar events determine the next queue. Do not precommit to a hundred-post calendar.

### 5.3 Blog article anatomy

Every post includes:

- one-sentence direct answer;
- why the question matters;
- original chart, calculation, table, or receipt;
- explanation in plain language;
- the strongest common misreading;
- methodology and sources;
- `published_at`, `updated_at`, and meaningful `as_of`;
- author identity and creation/process note where readers would reasonably ask;
- related lesson, tool, and live object;
- one exact continuation;
- correction history when changed materially.

### 5.4 Publication cadence

Start with at most two strong posts per week after the launch set. Event-driven posts may exceed that only when each contains original evidence and a persistent useful object. Cadence is subordinate to index-worthiness and distribution inventory.

---

## 6. Learning Center / Mastermind University

### 6.1 Product ruling

Build the Learning Center as an educational product, not a keyword glossary. A strong lesson should leave a reader able to interpret a real Mastermind surface more competently.

Each lesson contains:

1. learning objective;
2. direct definition;
3. visual or interactive example;
4. calculation or mechanism;
5. common trap;
6. “when this breaks” section;
7. live Mastermind example;
8. three-question self-check;
9. next lesson and relevant tool;
10. sources, author, update date, and method.

### 6.2 Initial tracks

#### Track A — Technical analysis and price structure

- 52-week highs and lows;
- trend versus momentum;
- RSI and MACD without indicator worship;
- VWAP and anchored VWAP;
- volume profile and point of control;
- breadth, participation, and divergence;
- support/resistance as evidence, not certainty;
- confluence and overfitting.

#### Track B — Options and market structure

- option basics and payoff geometry;
- implied versus realized volatility;
- implied earnings move;
- gamma exposure and its assumptions;
- open interest versus traded volume;
- skew and term structure;
- why dealer-position estimates are not observable truth.

#### Track C — Fundamentals and valuation

- income statement, balance sheet, and cash flow linkage;
- revenue growth versus operating leverage;
- valuation multiples and their hidden assumptions;
- reverse valuation / what the price implies;
- margins, revisions, and earnings quality;
- peer comparison without sector mistakes.

#### Track D — Ownership, filings, and alternative data

- Form 4 transaction types and filing dates;
- open-market purchases versus grants and exercises;
- insider clusters and their limitations;
- 13F holdings and the reporting lag;
- Congress transaction/disclosure lag;
- ownership concentration and crowding;
- source rights and public-data provenance.

#### Track E — Macro and cross-asset context

- growth, inflation, liquidity, and rates;
- yield curves and term premium;
- dollar, commodities, and cross-asset transmission;
- sector leadership and breadth;
- event impact and second-order exposure;
- regime descriptions versus forecasts.

#### Track F — Mastermind method

- what “What Changed” means;
- evidence status and `as_of`;
- falsifiers and contradictions;
- receipts and outcome reopens;
- why display context is not a trading signal;
- how corrections propagate.

### 6.3 Twelve-lesson launch

Launch two cornerstone lessons from each track. Migrate Gamma Weather into Track B as one of the twelve. Use the remaining planned lessons as the visible curriculum, marked “planned” only on the hub; do not create empty indexable placeholder pages.

### 6.4 Structured-data reality

Google removed Course Info and Learning Video as supported search-result structured-data types. Do not spend W1 building a “Course rich result” system. Use accurate Article/BlogPosting markup where applicable, BreadcrumbList, visible curriculum navigation, video metadata when a real video exists, and generic schema.org semantics only when they truthfully describe visible content. Do not promise a ranking or rich-result benefit.

---

## 7. Calculator Lab

### 7.1 Calculator product law

Every calculator must:

- return a useful result without signup;
- state the formula and assumptions;
- accept bounded inputs with validation;
- work with keyboard and mobile;
- keep the core explanation in static HTML;
- avoid hidden data collection;
- offer a privacy-safe share or copy-result action;
- link to a lesson explaining the concept;
- link to a live data/tool continuation where available;
- carry version, methodology, and test fixtures;
- never claim precision the inputs cannot support.

### 7.2 Build now: three calculators

#### Calculator 1 — Drawdown Recovery and CAGR

Inputs:

- starting value;
- current value or drawdown percentage;
- elapsed years;
- optional target date.

Outputs:

- drawdown;
- gain required to recover;
- annualized return to recover by target date;
- simple benchmark comparison example;
- shareable result string.

Why now: broad evergreen intent, trivial compute, easy testing, useful prerequisite for outcome receipts.

#### Calculator 2 — Earnings Implied Move

Inputs:

- stock price;
- at-the-money call premium;
- at-the-money put premium;
- optional expiration/date and historical realized move.

Outputs:

- straddle-implied dollar and percentage move;
- upper/lower reference range;
- realized-versus-implied comparison when supplied;
- explicit note that this is a market-price estimate, not a forecast.

Why now: connects to earnings-week content, options education, ticker dossiers, and the first-1,000 Earnings Week Risk Scan.

#### Calculator 3 — Portfolio Concentration / HHI

Inputs:

- tickers or labels and weights;
- optional sector labels;
- equal-weight shortcut.

Outputs:

- normalized weights;
- Herfindahl-Hirschman concentration;
- effective number of equally weighted positions;
- top-position and top-three concentration;
- descriptive warnings about duplicated exposure, not a recommended allocation.

Why now: creates a natural bridge to Portfolio X-Ray while remaining useful without account creation.

### 7.3 Build next, only after the first three produce use

- reverse-valuation / growth-implied-price bridge;
- total-return and benchmark calculator;
- bond price/yield-duration sensitivity;
- option breakeven and payoff explorer;
- average-cost and tax-lot organizer, only after jurisdiction and privacy boundaries are explicit;
- position-risk calculator, only if wording remains descriptive and does not become personalized sizing instruction.

### 7.4 Structured-data warning

Do not fabricate ratings or reviews to satisfy SoftwareApplication rich-result properties. W1 may use truthful WebPage and Breadcrumb markup. Generic `WebApplication` semantics may be added later if they accurately describe visible functionality, but no rich-result claim belongs in acceptance tests.

---

## 8. Living Market Toolkits

### 8.1 Toolkit contract

A toolkit is a stable, nightly or event-updated page with:

- clear user job;
- current `as_of` and data-through time;
- methodology and source;
- filterable or sortable useful results;
- healthy, stale, degraded, or unavailable state;
- visible limitations;
- change history or recent snapshots where useful;
- links to underlying ticker dossiers;
- share card and canonical URL;
- optional RSS/Atom or JSON update feed;
- one continuation such as follow, monitor, compare, or inspect a lesson;
- public-data/redistribution entitlement recorded.

### 8.2 Build now: new 52-week highs

Canonical job:

> Which covered U.S. stocks made a new 52-week closing or intraday high recently, and is participation broad or concentrated?

Minimum output:

- today, last five sessions, and last twenty sessions;
- ticker, company, sector/industry, price, high date, previous high date, distance from high, and volume context;
- sector counts and breadth trend;
- closing-high versus intraday-high distinction;
- filters for sector, market-cap band where available, and date window;
- links to ticker dossiers;
- companion new-lows tab, but one canonical page unless demand later supports separation;
- current methodology and universe definition.

Reuse:

- `engine/marketing/chart_facts.py::_fact_52w_high_low`;
- `engine/momentum_context_signals.py`;
- existing stock membership, sector, OHLC, share-card, and canonical-link infrastructure.

Do not recompute a second definition that can disagree silently. Extract or promote one canonical helper and test equality against existing facts.

### 8.3 Build now: recent insider transactions

Canonical job:

> Which corporate insiders recently filed meaningful open-market purchases or sales, what actually happened, and how stale is the information?

Minimum output:

- transaction date and filing date as separate columns;
- reporting owner, role, transaction code, buy/sell, shares, price, approximate value, and source filing;
- open-market purchases/sales separated from grants, exercises, gifts, and other transaction codes;
- distinct-insider cluster view;
- latest source and freshness note;
- exact Form 4 link when available;
- ticker-dossier links;
- method explaining two-business-day statutory timing and real-world edge cases;
- no “act now,” “smart money says buy,” or ungraded directional ranking.

Source priority:

1. direct SEC Form 4 public data from `collectors/sec_insider.py` where the current-quarter pipeline supports the required fields;
2. licensed Quiver lane only when public redistribution terms permit the rendered fields;
3. quarterly SEC aggregate only when the page clearly labels the slower grain.

The rights checker must decide public fields before production. A data-rights uncertainty may keep the licensed lane out of the public page; it does not block the direct-SEC build.

### 8.4 Build now: earnings this week / earnings risk

Canonical job:

> Which covered companies report this week, what move is priced, and which related names or themes may be exposed?

Minimum output:

- date/session, ticker, company, sector;
- implied-move input and timestamp where entitlements permit;
- recent realized earnings moves;
- related ticker/theme links based only on existing deterministic or cited relationships;
- countdown and ICS feed;
- pre-event, live, and post-event state at stable URLs;
- outcome reopen after the event.

This toolkit is the SEO destination for the first-1,000-leads Earnings Week Risk Scan. It must share contracts rather than create a second scan implementation.

### 8.5 Build next

- market-breadth dashboard and new-high/new-low participation history;
- recent 13F changes, with quarter/reporting lag made prominent;
- biggest post-earnings gaps and follow-through;
- sector and theme leadership pages where the current basket engine provides unique data;
- public exposure indices and rights-cleared dataset downloads;
- substantive hand-curated pair comparisons such as QQQ versus QQQM, SPY versus VOO, or NVDA versus AMD.

### 8.6 Existing pages to improve, not duplicate

- Link the Congress lesson into `/congress_trades.html` and add its methodology/lag explanation there.
- Link the confluence lessons and relevant calculator/tool pages into the shipped confluence screener.
- Link new-high articles and lessons into `/movers.html` and eligible ticker dossiers.
- Add toolkit discovery to the Tools hub; do not create a second movers, Congress, or confluence route.

---

## 9. Topic clusters and internal-link graph

### 9.1 Initial clusters

| Cluster | Hub | Supporting pages | Live objects |
|---|---|---|---|
| Momentum and 52-week highs | learning track/hub | high/low lesson, breadth lesson, launch article | new-high toolkit, movers, ticker dossiers |
| Insider and ownership | ownership track | Form 4 lesson, 13F lesson, Congress-lag article | insider toolkit, Congress page, ticker ownership sections |
| Earnings and volatility | options track | implied-move lesson, earnings article | calculator, earnings toolkit, ticker options/earnings sections |
| Technical confluence | technical track | VWAP, volume profile, RSI/MACD, overfitting lessons | confluence screener, ticker technicals |
| Dealer positioning | options track | Gamma Weather, OI/volume, skew | live boards and ticker options sections |
| Macro transmission | macro track | rates, dollar, liquidity, sector leadership | macro, sector, event pages |
| Accountability method | Mastermind-method track | evidence, falsifier, receipt, correction lessons | public receipts, corrections, dossiers |

### 9.2 Link rules

- Every indexed article or lesson links to at least one parent hub, one sibling, and one live object.
- Every calculator links to its method lesson and at least one relevant toolkit.
- Every toolkit row links to a canonical ticker dossier when one exists.
- Ticker dossiers receive no more than a small, contextually selected set of related lessons/tools; do not inject a giant footer link farm.
- Links use crawlable `<a href>` elements in initial HTML.
- Anchor text describes the destination job; avoid repeated exact-match keyword stuffing.
- The internal-link engine must cap links, deduplicate them, and never create a link to a stale/noindex destination as a primary continuation.
- Orphan-page and link-depth checks run in CI.

### 9.3 Demand-backed content expansion

Beacon should score candidate work using:

- Search Console impressions and unresolved queries;
- on-site search and “request deeper investigation” demand;
- creator/community questions;
- current event half-life;
- proprietary data readiness;
- uniqueness versus current pages;
- refresh cost;
- downstream activation fit.

This score ranks a content backlog only. It does not become a market signal or product recommendation.

---

## 10. Technical SEO and machine readability

### 10.1 Static-first rendering

The core answer, headings, table labels, links, metadata, and sources must be in initial static HTML. JavaScript may power filters, calculators, charts, and progressive disclosure. Do not make a crawler execute the full application to discover the promised content.

### 10.2 Canonical and URL law

- one self-referential canonical per indexable URL;
- the same canonical in HTML, sitemap, share metadata, JSON-LD, feeds, and analytics;
- no query-string variants in sitemaps;
- filter/sort states remain noncanonical unless a new page has independent user value;
- no separate URL for minor date snapshots;
- migrations require redirect, canonical, sitemap, and internal-link updates together;
- no canonical pointing to a URL that is noindex, missing, or materially different.

### 10.3 Sitemap architecture

Move from one stock-dominated sitemap to an index:

```text
/sitemap.xml                 sitemap index
/sitemaps/core.xml
/sitemaps/stocks.xml
/sitemaps/blog.xml
/sitemaps/learn.xml
/sitemaps/tools.xml
/sitemaps/datasets.xml       only when public datasets ship
/sitemaps/video.xml          only when owned/embedded watch pages qualify
```

Rules:

- include only canonical URLs intended for search;
- `<lastmod>` changes only when visible main content, structured data, or meaningful links change;
- rebuilding a footer timestamp does not refresh `<lastmod>`;
- stale/noindex pages leave the sitemap;
- sitemap generation is deterministic and tested;
- maintain the existing stock-page preservation behavior during migration.

### 10.4 Structured-data map

| Page family | W1 markup | Notes |
|---|---|---|
| Blog | Article or BlogPosting + BreadcrumbList | accurate author, `datePublished`, `dateModified`, image, canonical |
| Learning lesson | Article + BreadcrumbList | no Course rich-result project; lesson content must be visible |
| Hub | CollectionPage/WebPage + BreadcrumbList where useful | do not mark invisible child content |
| Calculator | WebPage + BreadcrumbList | no fabricated ratings; WebApplication semantics only if honest and maintainable |
| Toolkit | WebPage + BreadcrumbList | Dataset only when a real rights-cleared dataset/download exists |
| Dataset landing page | Dataset + BreadcrumbList | methodology, license, provenance, canonical, version |
| Video lesson/watch page | VideoObject where requirements are met | stable thumbnail, embed, transcript/summary, video sitemap if justified |
| Ticker dossier | preserve existing Article JSON-LD | extend only through a separately tested change |

Do not prioritize FAQ structured data. Google ended FAQ rich results in May 2026. Visible FAQs may still help users, but markup is not a W1 acquisition project.

### 10.5 Authorship and trust entity

Create a real `/authors/mastermind-research.html` or equivalent organization page with:

- what Mastermind is;
- editorial/research process;
- how deterministic data, AI assistance, and review are used;
- corrections policy;
- source and rights policy;
- coverage boundaries;
- links to methodology and contact route.

Article bylines link to that page. Do not invent fictional human authors.

### 10.6 AI-assistant discovery

Ship only machine-readable facts that can stay current:

- `/llms.txt`;
- `/brand-facts.json`;
- `/offers.json` only after MKT-ACC-00 commercial truth exists;
- methodology and corrections URLs;
- stable sitemap/feed discovery;
- concise answer-first summaries and structured tables;
- source, `as_of`, and canonical on every living object.

Each machine fact needs `effective_at`, `expires_at` where applicable, owner, and source URL. `llms.txt` is not a substitute for crawlable content, Search Console, or real authority.

### 10.7 Image and video SEO

- unique owned or rights-cleared images;
- descriptive filenames and alt text describing the evidence, not stuffing keywords;
- width/height set to prevent layout shift;
- 1200×630 share asset where appropriate;
- stable thumbnail URLs;
- meaningful captions near data charts;
- text alternative/table for chart conclusions;
- video watch pages with unique title, description, visible embed, thumbnail, and transcript/summary;
- video sitemap only after real watch pages exist.

### 10.8 Performance budget

At the 75th percentile, target Google's current “good” Core Web Vitals:

- LCP at or below 2.5 seconds;
- INP below 200 milliseconds;
- CLS below 0.1.

New Blog/Learn/Calculator/Toolkit pages also target:

- no blocking third-party application shell;
- core content without JavaScript;
- compressed responsive images;
- fingerprinted/cacheable assets;
- no large chart library for a page that needs one simple SVG;
- calculator interactions that do not trigger layout shifts;
- automated Lighthouse or equivalent sampling in CI/preview, with field data taking precedence once available.

### 10.9 Chinese-language strategy

The site-wide bilingual UI law remains. Do not create hundreds of separate Chinese URLs merely to double page count. In W0, decide whether:

- one bilingual URL remains the canonical user experience; or
- durable Chinese articles/lessons receive distinct `/zh/` URLs with equivalent visible content, self-canonicals, and reciprocal `hreflang`.

Do not publish machine-translated thin duplicates. Separate locale URLs require a real translation/update owner and parity checks.

---

## 11. Search measurement and feedback

### 11.1 Search Console ingestion

Build a read-only Search Console adapter, gated on operator property verification and credentials, that collects:

- page;
- query;
- date/week;
- country;
- device;
- search type;
- clicks;
- impressions;
- CTR;
- average position;
- incomplete-data metadata.

The Search Analytics API can return top rows rather than every hidden query. Store that limitation in the artifact. Never treat missing rows as zero demand.

Suggested artifact:

```text
data/marketing/seo/search_console_daily.parquet
data/marketing/seo/page_family_scorecard.json
data/marketing/seo/query_gaps.json
```

Credentials remain runner secrets; derived non-sensitive aggregates may be committed only if existing data policy allows.

### 11.2 Page-family events

Every page records through the Growth Event Spine:

- impression/landing where available;
- page family and object ID;
- source and query class when available;
- scroll/read completion proxy;
- calculator completion;
- filter use;
- file/feed/embed use;
- ticker/tool/lesson continuation click;
- monitor/save/request intent;
- second session;
- paid activation and retained value when joinable;
- correction or stale state.

### 11.3 Beacon scorecard

Primary outcome:

> Qualified non-brand organic visitors who complete a useful public job and return or preserve an object.

Diagnostics:

| Layer | Metrics |
|---|---|
| Discovery | valid indexed URLs, non-brand impressions, query coverage, citations, earned links |
| Click | CTR by query/page family, title test, device, country |
| Use | lesson completion, calculator completion, toolkit interaction, source inspection |
| Continue | dossier/tool/lesson click, monitor intent, request, feed subscription |
| Return | second session, update-open, repeat calculator/tool use |
| Commercial | trial/paid/retained contribution by landing family |
| Trust | stale pages, corrections, rights issues, structured-data errors, crawl errors |
| Cost | build time, refresh time, inference cost, data cost, editorial/review cost |

Never use page count, indexed-page count, or raw organic sessions as the north star.

### 11.4 Decision clocks

- **Launch:** technical/index-worthiness review.
- **14 days:** crawl and rendering check; do not judge ranking.
- **30 days:** indexation, initial impressions, query mismatch, broken continuations.
- **60 days:** page-family CTR, use, internal-link behavior, early return.
- **90 days:** qualified organic acquisition, second value, links/citations, cost, retained contribution where mature.
- **Quarterly:** refresh, merge, expand, noindex, or retire.

A page with zero impressions is not automatically bad until crawl/index state and query demand are understood. A page with traffic but no useful completion may be a worse asset than a low-volume, high-intent page.

---

## 12. Indexation, refresh, and retirement governor

### 12.1 State machine

```text
draft
  -> published_noindex
  -> index_candidate
  -> indexed_active
  -> refresh_due
  -> indexed_active | merge_candidate | noindex_stale | retire_410
```

Each transition records:

- URL and page family;
- reason;
- owner;
- evidence completeness;
- source/data freshness;
- duplication check;
- last significant update;
- Search Console state where available;
- next review date;
- replacement/canonical if merged.

### 12.2 Freshness classes

| Class | Examples | Policy |
|---|---|---|
| Live/nightly | highs, insider filings, earnings calendar | stale badge immediately; noindex/remove from sitemap after declared data limit |
| Event lifecycle | earnings war room, policy event | pre/live/post states at one URL; postmortem remains if useful |
| Periodic | comparison, methodology, calculator | scheduled quarterly or annual review |
| Evergreen | durable lesson | review on source/product change; do not fake date freshness |
| Historical receipt | outcome review | immutable original claim plus append-only correction/outcome |

### 12.3 Retirement actions

- update when the user job persists and evidence changed;
- merge when two URLs answer the same question;
- redirect when a better canonical exists;
- noindex when a useful page temporarily lacks fresh evidence;
- 410 only when the object is permanently removed with no successor;
- keep historical receipts when their age is the point.

---

## 13. Build packets

## MKT-SEO-00 — Baseline, contracts, and collision audit

**Owners:** Beacon + Lab + Engine Room

**Priority:** P0

**Dependencies:** none

**Operator block:** Search Console/Bing property access for live data; code and fixtures are buildable without it

Deliver:

- current URL census by page family, indexability, canonical, status, title, description, schema, lastmod, byte weight, and link depth;
- exact inventory of existing Blog/Learn/Tools/Reports/Dossiers routes;
- collision review against open Marketing PRs and D10/MKT-ACC;
- `seo_page.v1`, `seo_source.v1`, `seo_index_decision.v1`, and `seo_event.v1` contracts;
- baseline sitemap/canonical/structured-data audit;
- Search Console adapter interface and fixtures;
- one written ruling confirming the route and source layout before scaling.

Acceptance:

- census is reproducible from a clean checkout;
- existing 1,460 dossier URLs are not accidentally rewritten;
- duplicate titles/canonicals and orphan pages are printed;
- missing credentials produce an explicit unavailable artifact, not a healthy zero;
- no secrets or raw personal query data enter git;
- the docket receives any current-state corrections discovered during the audit.

## MKT-SEO-01 — Shared publishing substrate and vertical slice

**Owners:** Beacon + Studio + Workshop + Funnel

**Priority:** P0

**Depends on:** MKT-SEO-00

Deliver:

- content/frontmatter parser and validation;
- shared SEO base template and hub templates;
- Blog/Learn/Tools route builders;
- schema, canonical, author, freshness, internal-link, and analytics adapters;
- sitemap-index builder preserving current stock URLs;
- RSS/Atom feed builder;
- one blog article, one learning lesson, one calculator, and new-highs toolkit end to end;
- share assets and tagged continuations;
- deterministic build and tests.

Acceptance:

- all four objects render from canonical sources in a clean checkout;
- core content and links exist in initial HTML;
- no duplicate titles, descriptions, canonicals, or slugs;
- stale/noindex decisions change sitemap membership correctly;
- Article/Breadcrumb markup passes local/schema checks;
- calculator fixtures cover boundaries and malformed inputs;
- toolkit reuses the canonical 52-week-high definition;
- every object emits page-family and continuation events;
- screenshot review passes desktop and mobile;
- render-time delta is measured and remains within the repo budget.

## MKT-SEO-02 — Native Blog launch

**Owners:** Studio + Beacon + Radar + Sentinel

**Priority:** P1

**Depends on:** MKT-SEO-01

Deliver:

- Blog hub with search/filter by cluster and date;
- remaining seven launch articles;
- author/process/methodology/corrections pages;
- article share cards and feeds;
- editorial opportunity queue fed by Radar and Search Console;
- update/correction workflow;
- related-object links and one exact continuation per article.

Acceptance:

- every article contains original evidence or a live Mastermind object;
- source packet, author, dates, and method are present;
- no report is copied into the Blog;
- Article metadata matches visible content;
- content lint catches unsupported numeric claims and missing sources;
- no article is indexed solely because a file exists;
- feeds contain canonical URLs and meaningful update timestamps.

## MKT-SEO-03 — Learning Center launch

**Owners:** Beacon + Studio + Workshop

**Priority:** P1

**Depends on:** MKT-SEO-01

Deliver:

- Learning Center hub and six track pages;
- twelve cornerstone lessons;
- Gamma Weather migration without duplicate indexable content;
- lesson navigation, progress stored locally where possible, self-checks, and related tools;
- glossary terms embedded in lessons and a compact glossary index only when each term has substantive content;
- lesson review clocks.

Acceptance:

- every lesson has objective, example, common trap, failure condition, self-check, and live continuation;
- planned lessons do not create empty URLs;
- mobile and keyboard use pass;
- no Course/FAQ rich-result dependency;
- migration preserves or redirects the legacy Learn URL;
- hidden Chinese/English content and canonical policy are consistent with the W0 language ruling.

## MKT-SEO-04 — Calculator Lab W1

**Owners:** Workshop + Beacon + Funnel

**Priority:** P1

**Depends on:** MKT-SEO-01

Deliver:

- Tools/Calculators hub;
- drawdown recovery/CAGR calculator;
- earnings implied-move calculator;
- portfolio-concentration/HHI calculator;
- formulas, assumptions, examples, boundary tests, share/copy output, analytics, and lesson links;
- optional live-data prefill only when entitlements and freshness are clear.

Acceptance:

- useful result before signup;
- no server persistence of holdings or other inputs by default;
- formulas match independent test fixtures;
- malformed and extreme inputs fail legibly;
- calculator works without network calls unless live prefill is selected;
- static explanations remain indexable;
- no fabricated reviews or fake functionality;
- completion-to-continuation events are joinable.

## MKT-SEO-05 — Living Toolkits W1

**Owners:** Workshop + Beacon + Radar + Sentinel

**Priority:** P1

**Depends on:** MKT-SEO-01; earnings toolkit also coordinates with first-1,000 service

Deliver:

- new 52-week highs/lows toolkit;
- recent insider transactions toolkit;
- earnings-this-week/risk toolkit;
- stable URLs, feeds, methodology, freshness states, share cards, and ticker links;
- data-rights manifest per field;
- healthy/degraded/unavailable fixtures;
- outcome reopen for earnings events.

Acceptance:

- dates and data-through times are visible;
- broken data is never rendered as an empty quiet market;
- SEC/Quiver source and lag are accurate;
- transaction codes are not collapsed into misleading “buy/sell” labels;
- no licensed field publishes without explicit rights state;
- new-high definition matches the existing engine helper;
- toolkit filters do not generate indexable query variants;
- each toolkit produces a second-value route.

## MKT-SEO-06 — Internal link graph, schema, and crawl control

**Owners:** Beacon + Engine Room

**Priority:** P1

**Depends on:** MKT-SEO-02 through MKT-SEO-05

Deliver:

- topic/entity link graph;
- contextual links into eligible ticker dossiers and tools;
- BreadcrumbList across new page families;
- sitemap index and family sitemaps;
- orphan, depth, broken-link, canonical, metadata, and schema checks;
- meaningful-lastmod contract;
- IndexNow adapter for genuinely added/updated/deleted URLs;
- crawl-error and soft-404 artifact.

Acceptance:

- zero orphan launch pages;
- all primary links are crawlable HTML anchors;
- no stale/noindex URL is submitted;
- no canonical conflict between HTML, sitemap, feed, or JSON-LD;
- IndexNow cannot bulk-submit unchanged inventory;
- structured data describes visible content only.

## MKT-SEO-07 — Search demand and refresh loop

**Owners:** Beacon + Lab + Radar

**Priority:** P2

**Depends on:** MKT-SEO-00 and live traffic

Deliver:

- scheduled Search Console ingestion;
- page/query family scorecards;
- query-gap opportunity feed;
- content refresh queue;
- merge/noindex/retire ledger;
- title/description testing without changing page purpose;
- 30/60/90-day decision reports with denominators.

Acceptance:

- missing/partial Search Console data is labeled;
- branded and non-brand traffic are separable;
- page family joins through useful completion and second value;
- no URL is declared successful from rank or clicks alone;
- losing/low-demand cells remain visible;
- automatic actions remain inside earned Beacon authority.

## MKT-SEO-08 — AI-answer and portable discovery layer

**Owners:** Beacon + Engine Room + Sentinel

**Priority:** P2

**Depends on:** MKT-SEO-01 and MKT-ACC-00 for offer facts

Deliver:

- maintained `llms.txt`;
- timestamped `brand-facts.json`;
- `offers.json` only from commercial truth;
- public methodology and corrections discovery;
- canonical JSON summaries for eligible tools/datasets;
- AI-referral source classification where detectable;
- expiry and owner checks.

Acceptance:

- no price, offer, or product claim can outlive its effective window;
- machine facts point to public canonical evidence;
- removing a fact withdraws it from every generated surface;
- AI answer files never expose private repo research or internal-only context;
- machine-readable text does not differ materially from visible claims.

## MKT-SEO-09 — Expansion candidates

**Owners:** Beacon + Workshop + Allies

**Priority:** P3 / demand-gated

**Depends on:** mature W1 measurement and product truth

Candidates:

- rights-cleared public datasets and exposure indices;
- reporter/creator embeds;
- substantive ticker/instrument comparisons;
- product/competitor comparisons after offer and entitlement truth;
- video watch pages and video sitemap;
- dedicated Chinese-language estate with real translation ownership;
- demand-backed deep-dive factory;
- additional calculators/toolkits that clear W1 use and return thresholds.

No candidate becomes a program merely because a keyword tool reports volume.

---

## 14. Four-week launch sequence

### Week 1 — foundation and one proof slice

- execute MKT-SEO-00;
- ratify route/source/frontmatter contracts;
- build one blog, lesson, calculator, and new-high toolkit;
- create sitemap-index compatibility layer;
- establish author/method/process pages;
- run mobile, schema, crawl, accessibility, and analytics checks.

### Week 2 — Blog and Learning Center

- launch Blog and Learn hubs;
- publish four additional Blog articles;
- publish six additional lessons;
- migrate Gamma Weather safely;
- ship feeds, breadcrumbs, related-object links, and share assets.

### Week 3 — calculators and toolkits

- ship remaining two calculators;
- ship recent-insider and earnings toolkits;
- complete data-rights and degraded-state tests;
- wire first-1,000 Earnings Week Risk Scan to the canonical toolkit contract;
- add contextual links from dossiers, movers, confluence, Congress, and reports.

### Week 4 — scale only what works technically

- complete the eight-article/twelve-lesson launch inventory;
- activate family sitemaps, crawl monitoring, Search Console adapter, and IndexNow changed-URL lane;
- verify URL Inspection on a sample from every family;
- fix query/title mismatch and orphan links;
- record the 30-day clocks;
- hand off demand/refresh queue to Beacon.

If Week 1's vertical slice is not solid, do not proceed by increasing content count. Repair the substrate.

---

## 15. Verification matrix

### Build correctness

- deterministic clean-checkout build;
- duplicate slug/title/canonical rejection;
- schema serialization tests;
- sitemap membership tests;
- meaningful-lastmod tests;
- noindex/stale transition tests;
- broken-link and orphan checks;
- feed validity;
- calculator formula and boundary fixtures;
- toolkit healthy/stale/broken source fixtures;
- rights-manifest enforcement;
- bilingual parity/lint where applicable.

### Public artifact checks

- inspect rendered HTML, not only template context;
- inspect one desktop and one mobile screenshot per family;
- keyboard and screen-reader landmarks;
- copy/share result;
- canonical and Open Graph asset;
- Rich Results Test for supported types;
- Schema Markup Validator for generic schema.org semantics;
- URL Inspection after deployment;
- Core Web Vitals/Lighthouse sample;
- source and correction links;
- exact continuation and analytics event.

### Failure-state checks

- source missing;
- stale data;
- malformed source row;
- no eligible toolkit results;
- Search Console credentials absent;
- duplicate article slug;
- invalid date or timezone;
- rights state unknown;
- Chinese translation missing;
- calculator NaN/infinity/extreme input;
- old canonical requested after migration.

Broken must be distinguishable from quiet. Unknown must be distinguishable from zero.

---

## 16. Standing search laws

1. **A useful object comes before a keyword.** Search intent chooses framing; proprietary value earns the page.
2. **No page farm.** Automation may research, structure, draft, test, link, and refresh; it may not turn a keyword matrix into thin inventory.
3. **One canonical job per URL.** Filter states and daily snapshots do not multiply URLs.
4. **Freshness is factual.** Dates move only after a significant visible change.
5. **Static first.** Core content and links exist before JavaScript.
6. **Structured data mirrors the page.** Never mark hidden, gated, absent, or invented content.
7. **Rights are field-level.** A source being available internally does not imply public redistribution permission.
8. **No fake authors, ratings, reviews, or testimonials.** Use the real Mastermind Research organization and real process.
9. **No empty curriculum.** Planned lessons appear on hubs without indexable placeholder URLs.
10. **No fake tools.** A calculator or generator must perform the promised task before asking for signup.
11. **No raw page-count goals.** Optimize useful completions, second value, links, and retained contribution.
12. **No ranking promises.** Sitemap, structured data, IndexNow, and `llms.txt` improve discovery and understanding; none guarantees indexing or placement.
13. **No generic CTA.** Every page offers the next exact job implied by the current one.
14. **Receipts include misses.** Outcome articles and toolkits preserve corrections and failed claims.
15. **Search does not bypass the Growth OS.** Attribution, commercial truth, claims, publication receipts, economics, and retirement stay connected.

---

## 17. Source and policy references

### Repository authorities

- `research/TRENDSPIDER_GROWTH_SEO_AND_GUERRILLA_MARKETING_INTELLIGENCE_FOR_FABLE.md`
- `research/NEURAL_WEB_AUTONOMOUS_MARKETING_LOBE_GRANDMASTER_PLAN_FOR_FABLE.md`
- `research/MARKETING_DEMAND_CAPTURE_AND_GROWTH_ACCELERATION_DOCKET_FOR_FABLE.md`
- Active PR #3092 at drafting: `research/MARKETING_FASTEST_PATH_TO_FIRST_1000_QUALIFIED_LEADS_FOR_FABLE.md`
- `research/marketing_dockets/INDEX.md`
- `research/marketing_dockets/D10_WORKSHOP_PUBLIC_TOOLS_W1.md`
- `engine/marketing/departments.py`
- `scripts/build_ticker_pages.py`
- `templates/ticker.html.j2`
- `scripts/build_reports.py`
- `templates/article_base.html.j2`
- `collectors/sec_insider.py`
- `engine/ownership_event_wire.py`
- `engine/marketing/chart_facts.py`

### Current external primary guidance

- [Google guidance for generative-AI content](https://developers.google.com/search/docs/fundamentals/using-gen-ai-content)
- [Google guide to AI-feature visibility](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide)
- [Google people-first content guidance](https://developers.google.com/search/docs/fundamentals/creating-helpful-content)
- [Google spam policies](https://developers.google.com/search/docs/essentials/spam-policies)
- [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap)
- [Google canonical guidance](https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls)
- [Google JavaScript SEO basics](https://developers.google.com/search/docs/crawling-indexing/javascript/javascript-seo-basics)
- [Google Article structured data](https://developers.google.com/search/docs/appearance/structured-data/article)
- [Google Breadcrumb structured data](https://developers.google.com/search/docs/appearance/structured-data/breadcrumb)
- [Google Dataset structured data](https://developers.google.com/search/docs/appearance/structured-data/dataset)
- [Google structured-data policies](https://developers.google.com/search/docs/appearance/structured-data/sd-policies)
- [Google structured-data update log](https://developers.google.com/search/updates)
- [Google Core Web Vitals guidance](https://developers.google.com/search/docs/appearance/core-web-vitals)
- [Google image SEO guidance](https://developers.google.com/search/docs/appearance/google-images)
- [Google video SEO guidance](https://developers.google.com/search/docs/appearance/video)
- [Google Search Analytics API](https://developers.google.com/webmaster-tools/v1/searchanalytics/query)
- [Bing IndexNow implementation guide](https://www.bing.com/indexnow/IndexNowView/IndexNowGetStartedView)

---

## 18. Final ruling

TrendSpider's SEO moat is not merely a large article count. It is the integration of education, search-demand pages, free tools, live market objects, brand repetition, and a paid continuation. Mastermind already has the hardest raw material: roughly 1,460 rich ticker dossiers, proprietary market context, report infrastructure, confluence and movers tools, a Marketing Growth OS, and an accountability doctrine.

The next move is to turn those isolated assets into a coherent public knowledge-and-utility graph:

> **Teach the concept, let the user calculate or inspect it, show it live on a ticker or market toolkit, and give the user one reason to return when the state changes.**

That is the SEO system to build now. The Blog creates current authority. The Learning Center creates durable understanding. Calculators earn broad intent and links. Living toolkits earn return behavior. Beacon's governor keeps the estate useful rather than bloated. Funnel and the Growth OS reveal whether any of it becomes a business.
