# Deepvue Competitive Teardown and Mastermind Build Docket

**Canonical deliverable:** this file

**Research snapshot:** 2026-08-01, America/Vancouver

**Scope:** authenticated Deepvue product walkthrough, official documentation, public frontend assets and network behavior, AI benchmark, clean-room engine reconstruction, Macro Dashboard gap audit, Neural Web and Prophet integration, and a sequenced implementation program

**Decision:** reproduce Deepvue's useful workflow contracts from independent data and Mastermind-native code; do not copy its source, visual identity, assets, wording, prompts, hidden formulas, or customer data

**First shipped lane from this docket:** Stage Industry Intelligence repair, restoring the existing industry-rank and industry-flow substrate from the current live Stage frame

**Publication boundary:** private research and implementation handoff. Do not publish through `reports.html` without a separate operator decision.

---

## Executive verdict

Deepvue is the closest horizontal product competitor to Macro Dashboard, but not because it has a hidden superintelligence engine.

Its real achievement is product coherence:

1. one shared market-data vocabulary appears in charts, screens, watchlists, alerts, ratings, tables, dashboards, and AI;
2. one selected symbol can retune several linked widgets;
3. historical snapshots, live deltas, alerts, files, and AI are served by separated paths;
4. conventional growth-trader calculations are packaged as ubiquitous, legible ratings;
5. natural language can become a deterministic screen or interface action; and
6. the application hides latency with ready context, bounded routes, caching, and polished progress states.

Deepvue is therefore a serious product threat and a useful architecture benchmark. It is not evidence that Mastermind lacks intelligence. The opposite is closer to the truth: Mastermind already owns the richer thematic, Stage, evidence, Neural Web, and Prophet substrate, but exposes that power through fragmented pages and contracts. Deepvue has productized weaker intelligence more coherently.

The winning move is not a pixel clone. It is:

> Deepvue's coherence and deterministic workflow actions
> + Mastermind's temporal evidence, theme depth, Stage intelligence, Neural Web, and Prophet
> + explicit provenance, point-in-time safety, and visible authority boundaries.

### Blunt scorecard

| Dimension | Deepvue | Mastermind today | Strategic read |
|---|---:|---:|---|
| Workflow cohesion | 9/10 | 5/10 | Deepvue's largest lead |
| Chart/screener packaging | 9/10 | 7/10 | Deepvue is more unified; Terminal is broader than the public site suggests |
| Ratings accessibility | 9/10 | 5/10 | We have components, not one ubiquitous rating passport |
| Theme intelligence | 5/10 | 9/10 | Their tracker is curated price performance, not demonstrated capital flow |
| AI speed, simple route | 8/10 | 4/10 | Routing and transport problem, not an MCP problem |
| AI depth and action surface | 7/10 | 8/10 potential | Deepvue packages actions better; Mastermind has a much richer tool graph |
| Provenance and temporal evidence | 5/10 | 8/10 | Mastermind can make this a moat |
| Neural context and forecasting | 3/10 observed | 9/10 potential | No public Deepvue analogue to Neural Web or Prophet was found |
| UI hierarchy | 6/10 | 7/10 | Their density is useful but visually noisy; do not import the lavender shell |
| Competitive threat | 8/10 | — | They can win users while we are still explaining our stronger internals |

### Three corrections that change the build plan

1. **Theme Tracker is not disclosed institutional-flow data.** Deepvue documents it as real-time percentage performance for manually curated themes over Today, Week, Month, and YTD, with constituent drill-down. Price leadership may imply attention; it does not prove capital flow.
2. **Its ratings are reproducible concepts, not exposed secret science.** Relative momentum, earnings/sales growth, price-volume accumulation, liquidity, volatility, and composites are standard cross-sectional calculations. Exact weights remain unknown and should not be imitated.
3. **Its AI is not literally instant and there is no MCP evidence.** A broad novel prompt took 27.33 seconds server-side. A native-metric prompt took 9.81 seconds. A one-line price question took 2.14 seconds but returned a source timestamp four days behind the August 1 session. The public client sends one structured REST request and receives a complete response before animating it.

---

## Evidence boundary

This docket uses four evidence labels:

- **OBSERVED:** directly visible during the authenticated walkthrough, supplied screenshots, network responses, public frontend assets, or the current Mastermind repository.
- **DISCLOSED:** stated in official Deepvue marketing, documentation, application listings, or terms.
- **INFERENCE:** the most likely implementation from observed contracts and payload fingerprints, but not a vendor disclosure.
- **PROPOSED:** an independent Mastermind design or formula.

### What was inspected

- all seven supplied screenshots at original resolution;
- the authenticated Deepvue dashboard and onboarding flow;
- every currently visible dashboard app, including a scratch layout populated with 18 instantiated widgets;
- the Add Apps catalogue, preset dashboards, chart controls, Data Panel, screening surfaces, Theme Tracker, Stage Analysis, Market Brief, analyst actions, and AI Terminal;
- official product pages and the public knowledge base;
- publicly delivered production JavaScript/CSS assets and source-map references;
- browser-visible API hosts, request shapes, response shapes, timing, and dashboard/screener serialization; and
- current `origin/main` across the relevant Macro Dashboard, Stage, theme, Terminal, Neural Web, Prophet, and Mastermind AI surfaces.

### What remains unknown

- Deepvue's backend languages and deployment topology;
- market, fundamental, estimate, news, analyst-action, and earnings data vendors;
- exact rating weights and eligibility rules;
- server-side prompts, routing thresholds, cache policy, and retrieval implementation;
- the exact AI model or provider; and
- whether any private server component uses MCP.

No vendor source, asset, prompt, customer record, or paid data payload is included in this repository. Deepvue's current [Terms of Use](https://deepvue.com/terms-of-use/) reserve its code, databases, functionality, and design, and prohibit copying/adapting software, systematic extraction, reverse engineering, and competitive reuse. This docket therefore specifies behavior contracts and independent implementations only.

---

## 1. Product suite: what Deepvue actually ships

Deepvue's product is one growth-trader operating surface rather than a set of loosely linked pages.

### 1.1 Published breadth

| Surface | Published capability | What matters |
|---|---|---|
| Charts | 12 marketed chart families, 85+ drawings, 60+ indicators, 35 layouts, 1–8 synchronized charts, replay, pre/post-market | A curated trader workflow on top of a commodity renderer |
| Screener | 1,152 active datapoints, 1,490 filterable fields, 568 streamed fields, 150+ presets, nested Boolean groups | Shared data registry and deterministic filter execution |
| Watchlists | 33 presets, up to 1,500 symbols, 500+ visible metrics, sections, Combo Lists, table/mini-chart views | Same state and actions across modes |
| Alerts | Price, trendline, technical, and conditional alerts with up to five additional conditions | General rule grammar, not isolated alert scripts |
| Dashboard | 36-column grid, up to 20 apps, unlimited layouts, nine link colors | A typed context bus masquerading as colored UI chrome |
| AI Terminal | 50+ marketed templates, current-symbol awareness, contextual references, cited research, executable screens | Context compiler plus bounded action contracts |
| Mobile | Synced lists, settings, chats, and selected research views | Distribution after the shared contracts exist |
| Browser extension | Cashtag hover cards and cashtag-to-watchlist import | Lightweight capture loop |

The live product is currently marketed at $49 per month. Pricing is strategically relevant because Deepvue is executing the same clean-room-undercut playbook against MarketSurge that Mastermind can execute against Deepvue.

### 1.2 Dashboard app inventory

The live Add Apps drawer exposed 19 entries. The scratch dashboard successfully instantiated 18; Position Size Calculator did not appear after two add attempts, which is either a product defect or a practical 18-widget/layout constraint. Deepvue's marketing says 20 apps, while a removed Relative Rotation Graph type still appears in public client strings. Treat the count as documentation drift, not a stable contract.

| Family | App | Authenticated behavior observed | Mastermind status |
|---|---|---|---|
| Core | Chart | Multi-type chart, drawings, indicators, layouts, symbol/timeframe sync | Strong in Terminal/charting stack; fragmented from public pages |
| Core | Screener | Live table, presets, filter groups, sort, selected-symbol propagation | Strong screeners; no one canonical query grammar across all surfaces |
| Core | Watchlist | Table/list context and linked symbol selection | Strong local/cloud lists and portfolio integration |
| Core | Alerts | Active/triggered views and condition creation | Strong internal alerts; arbitrary user rule builder is a gap |
| Visualization | Performance Chart | Select symbols and a datapoint for comparative ranking | Existing factor/performance surfaces |
| Visualization | Heat Map | Template plus x/y datapoints | Stronger existing stock/theme/sector heatmaps |
| Visualization | Bubble Chart | x/y/z datapoints and zoom | Real generic widget gap |
| Visualization | Mini Chart | Symbol, timeframe, previous-close comparison | Sparklines exist; reusable widget packaging is missing |
| Research | Data Panel | Custom categories and hundreds of company/price/rating/fundamental fields | Data exists; canonical modular panel is missing |
| Research | Market Breadth | highs/lows, A/D, up/down volume, ±4%, Stage distribution | Strong underlying collectors and regional surfaces |
| Research | Theme Tracker | Curated theme performance over several horizons | Mastermind's engine is materially richer; compact packaging lags |
| Research | Reports | Saved-screen result counts monitored together | Partial equivalent through registries/briefs |
| Research | Deepvue Terminal | Chat, prompts, context, citations, ticker actions | Broader Mastermind tool graph; slower and less polished routing |
| Research | Industry Ranks | Sector rows with 1/3/6/12-month rank and change | Designed but current Stage industry artifacts are empty |
| Research | Market Brief | Sentiment, timestamp, concise prose | Multiple stronger briefs; not a dockable compact contract |
| Research | Stage Analysis | Weinstein Stage 1–4 distribution and health by sector | Strong classifier and dedicated six-tab page |
| Research | Upgrades/Downgrades | Date/action filters, summary, firm/rating/target table | Partial revision breadth; event-level analyst tape gap |
| Tools | Stats Table | Periodic earnings/sales/statistics table | Fundamentals and Stage tables exist |
| Tools | Position Size Calculator | Catalogue entry; widget failed to instantiate in this walkthrough | Mastermind has a stronger bilingual calculator suite |

### 1.3 Dashboard mechanics

**OBSERVED / public-client evidence**

- 36×36 logical grid;
- maximum 20 widgets;
- 6px inter-widget gutter;
- minimum 3×3 widget size;
- all-edge and corner resizing;
- responsive cell dimensions driven by container size;
- collision resolution that can swap, displace, or shrink neighbors;
- Escape cancellation and valid/invalid placement previews;
- autosaved layout revisions;
- widget payloads shaped around `type`, `points {h,w,x,y}`, symbol, color group, constraints, and app configuration; and
- up to nine color groups that propagate a selected symbol/context among subscribed widgets.

The useful concept is not colored dots. It is a typed context bus:

```text
selection event
  -> link_group
  -> normalized entity/timeframe/filter context
  -> subscribed widgets
  -> local validation and refresh
```

Mastermind should expose semantic link names such as `primary_symbol`, `peer_compare`, `theme_focus`, and `event_focus`, while optionally rendering colors as a quick visual cue.

### 1.4 Preset workflow design

The authenticated API returned 21 preset dashboards. Representative compositions included:

- Chart + Theme Tracker + Market Brief + index ETF watchlist;
- Chart + AI Terminal + Stats Table;
- Theme Tracker + Bubble Chart + Chart + Watchlist;
- pre-market monitor with Screener + Chart + Bubble + News + Breadth;
- earnings workflow with AI + Chart + two Screeners;
- weekend routine with Chart + six Screeners;
- Industry Ranks + Chart; and
- Stage Analysis, Character Change, Intraday Strength, Up on Volume, and several heatmap presets.

The meta-lesson is sequencing: presets teach the workflow and sell the product before the user builds a custom workspace.

---

## 2. UI and frontend architecture

### 2.1 Supplied-screen measurements

| Screenshot | Resolution | High-signal observation |
|---|---:|---|
| Main onboarding | 1603×1106 | ~56px global rail, ~190px list, central chart, ~264px Data Panel, bottom Stats Table; modal ~700px wide |
| Chart types | 870×535 | 14 visible representations in four columns |
| Indicators | 870×703 | search plus Deepvue/Trend/Momentum/Volatility/Volume/Reference chips |
| Custom dashboard | 1607×1105 | large chart with three stacked research widgets and ~6–8px gutters |
| Add Apps | 300×1098 crop | ~260px drawer and 19 visible apps |
| Drawing palette | 367×750 crop | ~43px dock, ~230px overflow with capture/share/layout actions |
| AI Terminal | 840×1093 crop | response actions, follow-ups, prompt library, Add Context, voice, current-symbol placeholder |

The four-step chart onboarding is:

1. pin timeframes;
2. choose chart types;
3. bookmark drawing tools; and
4. add indicators.

The chart-type UI exposes Candlestick, CandleVolume, Hollow Candles, OHLC, HLC, Classic HLC, Line, Area, Heikin-Ashi, Baseline, Renko, Line Break, Kagi, and Point & Figure. Marketing counts 12 because it treats some candle styles as one family.

### 2.2 Public client stack

**OBSERVED**

- Vite-built React single-page application;
- React Router, Redux Toolkit, TanStack Query-style caching, Axios, and dnd-kit constructs;
- Tailwind CSS, Sentry, Amplitude/Pendo/Gleap-style product instrumentation;
- TradingView Lightweight Charts 5.1.0 as the chart substrate;
- a lazy QuickJS/Emscripten runtime, plausibly for sandboxed custom indicator execution;
- route-level lazy chunks; and
- separate hosts for core API, alerts, historical/static data, files/images, and live/pubsub traffic.

The production application is not exceptionally small: the observed main JavaScript asset was roughly 9.06 MB raw, the dashboard chunk roughly 710 KB raw, and CSS roughly 1 MB raw. Its warm speed comes from architecture and interaction discipline, not a tiny bundle.

Public `sourceMappingURL` references were present, but the map paths returned the application shell rather than source maps. No private source was obtained.

### 2.3 Backend shape inferred from the browser

Observed host separation:

```text
app.deepvue.com          SPA and static assets
api.deepvue.com          core objects, dashboards, screeners, AI
historical.deepvue.com   static historical snapshots
lightserver.deepvue.com  definitions/statistics paths
alerts.deepvue.com       alert service
files.deepvue.com        descriptions, logos, generated descriptions
live/pubsub hosts        incremental market updates
```

**INFERENCE:** Deepvue likely serves immutable or cacheable historical snapshots separately, then applies incremental latest-bar/cell updates through real-time channels. Ratings are recomputed on independent cadences. This is why the chart/screener shell can remain responsive without rebuilding full state on each interaction.

That separation is the architectural lesson to import:

```text
history snapshot service
       + realtime delta service
       + metric/rating registry
       + rule/alert evaluator
       + context compiler
       + bounded AI routes
```

---

## 3. Screener and data registry

Deepvue's biggest conventional moat is its shared datapoint registry.

The live product uses compact numeric identifiers for datapoints, comparator codes, values, nested filter groups, visible columns, and sorts. Presets such as CANSLIM, accelerating earnings/sales, Weinstein stages, high volume, and other trader workflows are serialized filter programs rather than hard-coded pages.

### 3.1 Clean-room screener contract

```json
{
  "schema": "screener_query.v1",
  "universe_id": "us_equities_liquid.v3",
  "as_of": "2026-08-01T20:00:00Z",
  "where": {
    "op": "all",
    "children": [
      {"field": "rs_12m", "cmp": "gte", "value": 90},
      {"field": "eps_rating", "cmp": "gte", "value": 80},
      {"field": "avg_dollar_volume_50d", "cmp": "gte", "value": 20000000},
      {
        "op": "all",
        "children": [
          {"field": "close", "cmp": "gt_field", "value": "sma_50d"},
          {"field": "close", "cmp": "gt_field", "value": "sma_200d"}
        ]
      }
    ]
  },
  "sort": [{"field": "rs_12m", "direction": "desc"}]
}
```

Natural-language screening must compile through this path:

```text
user request
  -> field/entity resolver
  -> candidate typed AST
  -> validation + cost + freshness check
  -> plain-English diff/preview
  -> deterministic execution
  -> per-row why-matched trace
```

The LLM may propose the AST. It must never invent the result set.

### 3.2 What Mastermind should add beyond Deepvue

- point-in-time snapshots and historical screen replay;
- field freshness and provenance badges;
- cohort and missingness counts;
- per-row contribution/why-match explanations;
- a visible query AST and AI-generated diff;
- query cost and streaming-health indicators; and
- Prophet/Neural Web fields as explicit context columns, never invisible ranking manipulation.

---

## 4. Ratings engine reconstruction

Deepvue's official rating documentation exposes the component concepts but not the exact weights.

| Rating family | Disclosed basis | Cadence |
|---|---|---|
| Relative Strength | price momentum relative to the S&P 500, percentile 1–99, 1/3/6/12-month horizons, recent periods heavier in longer windows | Daily |
| Absolute Strength | raw percentage price performance converted to a percentile | Daily |
| EPS | GAAP quarterly/annual EPS growth, estimates/stability in newer descriptions, recent results heavier | Daily; docs drift |
| Sales | historical and forward sales growth | Daily |
| Fundamental | EPS/sales history, surprises, and forward estimates; −100 to +100 plus letter grade | Hourly |
| Accumulation/Distribution | 13 weeks of volume, close location within the daily range, and volume relative to 50-day average | Daily |
| Liquidity | float and 20/50-day average volume | Daily |
| Composite | RS, absolute strength, fundamentals, and A/D | Daily |
| Timeliness | EPS, RS, beta, current ratio, and market cap | Daily |
| RMV | high-low volatility over 5/10/15/20 days, ranked 0 tightest to 100 most volatile | Every minute |
| Sector/group rank | weighted constituent Absolute Strength after liquidity/price eligibility rules | Hourly |

### 4.1 Do not counterfeit confidence

Mastermind's current factor composite is not ready to be renamed a Deepvue/IBD-style Composite Rating. Its own scorecard does not grant it trade authority. The first release should be a display-only `equity_rating.v1` passport with transparent components.

```json
{
  "schema": "equity_rating.v1",
  "symbol": "AAPL",
  "universe_id": "us_equities_liquid.v3",
  "as_of": "2026-08-01T20:00:00Z",
  "source_as_of": "2026-08-01T20:00:00Z",
  "formula_version": "rating_fabric.1.0.0",
  "cohort_size": 4127,
  "components": {
    "rs_1m": {"raw": 0.041, "percentile": 78, "coverage": 1.0},
    "rs_3m": {"raw": 0.137, "percentile": 91, "coverage": 1.0},
    "rs_12m": {"raw": 0.284, "percentile": 94, "coverage": 1.0},
    "eps": {"raw": null, "percentile": null, "missingness": "not_available"},
    "accumulation": {"raw": 0.62, "percentile": 73, "coverage": 0.98}
  },
  "composite_display": null,
  "authority": {"display": true, "context": true, "rank": false, "gate": false, "size": false}
}
```

### 4.2 A stronger clean-room formula program

**PROPOSED**

1. Freeze the eligible universe, corporate-action adjustments, horizon convention, missingness policy, and benchmark at each as-of date.
2. Compute raw components independently.
3. Winsorize only under a versioned policy.
4. Convert raw values to deterministic cross-sectional percentiles with cohort count retained.
5. Publish every contribution and the full weight version.
6. Store daily vintages so historical values never use future fundamentals or revised membership.
7. Evaluate each component alone before evaluating a composite.
8. Condition diagnostics by regime, liquidity tier, sector, market cap, and data completeness.
9. Keep the display composite out of Prophet until a predeclared out-of-sample gate passes.

Deepvue's opacity is an opportunity. We can make the rating more trustworthy and more useful to Neural Web by exposing what drove it, what is stale, and how stable the percentile is.

---

## 5. Theme Tracker: what it is and how to beat it

Deepvue's [Theme Tracker documentation](https://docs.deepvue.com/articles/theme-tracker-app) says the list is manually curated and separate from GICS, updates during market hours, ranks Today/Week/Month/YTD performance, and opens the leading constituents. Users cannot define their own themes in the documented product.

There is no disclosed ETF-flow, ownership-change, dark-pool, options-flow, or institutional transaction engine behind that widget.

### 5.1 Existing Mastermind advantage

The current thematic substrate already contains:

- 269 subsectors across 41 themes;
- 1D, 1W, 1M, MTD, 3M, 6M, 1Y, and YTD horizons;
- relative-strength ratio and momentum;
- acceleration and normalized acceleration;
- quadrant, emergence, breadth, and turn state;
- drawdown/trough history;
- crowding, options, revisions, attention, hiring, and flow witnesses; and
- historical episodes and forward track record.

Deepvue has the better compact widget. Mastermind has the better intelligence engine.

### 5.2 Theme Tracker++ contract

```json
{
  "schema": "theme_state.v1",
  "theme_id": "ai_infrastructure",
  "membership_version": "2026-07-29.2",
  "as_of": "2026-08-01T20:00:00Z",
  "returns": {"1d_ew": 0.012, "1w_ew": 0.031, "1m_ew": 0.087, "1m_capw": 0.102},
  "relative": {"market_residual_1m": 0.055, "sector_residual_1m": 0.037},
  "breadth": {"above_20d": 0.71, "positive_1m": 0.78, "new_high_20d": 0.24},
  "structure": {"dispersion": 0.18, "top5_contribution": 0.43, "leader_concentration": 0.36},
  "dynamics": {"rank": 4, "rank_velocity": 7, "persistence": 0.82, "acceleration_z": 1.4},
  "witnesses": {
    "etf_flow_proxy": {"value": 0.63, "label": "proxy"},
    "options_attention": {"value": 0.71, "label": "proxy"},
    "revision_breadth": {"value": 0.58, "label": "observed"}
  },
  "authority": {"display": true, "context": true, "prophet": false}
}
```

Every flow-like value must say whether it is an observed signed flow, a delayed ownership change, or an inferred proxy. Price participation is not institutional flow.

### 5.3 Product surface

The compact widget should show:

- rank, return, residual return, breadth, persistence, and concentration at a glance;
- rank-velocity animation that communicates genuine state change;
- click-through to leader contribution, laggards, and membership history;
- a timeframe matrix rather than one dropdown at a time;
- an as-of/freshness chip; and
- a visible toggle between price leadership and flow/attention witnesses.

---

## 6. Deepvue AI teardown

### 6.1 Observed client contract

The public client submits one request to a dedicated Terminal endpoint containing fields equivalent to:

```text
message
sessionId
imageUrl
messageType
promptId
symbol
context
commandType
```

The context compiler expands:

- a watchlist mention into symbols;
- a screener mention into current result symbols;
- a Data Panel mention into symbol + metric/value text; and
- ticker tokens into company identity context.

The response can contain citations, ticker chips, follow-ups, and executable actions such as a created screener.

The inspected Terminal path did not stream answer tokens. It remained in progress states such as “Thinking,” “Reviewing your context,” “Checking market data,” and “Formulating a response,” then rendered and locally animated the completed answer. An SSE path in the public bundle belonged to the support product, not Deepvue Terminal.

### 6.2 Strong Perplexity fingerprint

The broad benchmark response body contained:

- `choices[].message.content`;
- `choices[].delta` and `finish_reason`;
- `citations` as a string array; and
- `search_results[]` with `title`, `url`, `date`, `last_updated`, `snippet`, and `source: "web"`.

This shape closely matches the official [Perplexity Sonar API response](https://docs.perplexity.ai/api-reference/sonar-post), including the Perplexity-specific `citations` and `search_results` fields. Deepvue removed model, usage, and provider identifiers before returning the payload.

**INFERENCE:** a Perplexity Sonar-class search response is likely used for at least the broad research route. This is a high-confidence fingerprint, not proof of the exact provider or model. Deepvue could proxy, transform, or emulate the same schema.

### 6.3 Authenticated latency benchmark

| Prompt class | Prompt | Deepvue completion | Observed result |
|---|---|---:|---|
| Broad current research | situational awareness covering regime, themes, breadth, rates/liquidity, catalysts, risks, citations, and timestamps | 27.33s | 10,142-character answer, 80 web results/citations, no true token stream |
| Native metric packet | AAPL RS 1M/3M/12M, industry rank, Stage, earnings date, EPS growth, citations/as-of | 9.81s | Faster bounded route; requested exact native provenance remained the critical quality test |
| Simple current fact | AAPL current price, one sentence, source and exact as-of | 2.14s | Returned Yahoo Finance value timestamped July 28 during the August 1 session |

The broad answer searched 80 web results. The domain mix included YouTube, Yahoo Finance, Investing.com, Indonesian and Indian official/market sites, KASE, media, and retail market sites. Some sources were current, while sampled dates also reached back to 2011. Large retrieval volume did not guarantee better source selection.

### 6.4 Quality findings

- The broad answer was fluent and comprehensive but generic where Deepvue already had live breadth and theme state in adjacent widgets.
- It did not satisfy the explicit request for source timestamps consistently.
- It used stale macro phrasing and vague references to “recent commentary.”
- The one-line price route optimized latency over freshness.
- The UI can confuse explicit and ambient symbol context: the supplied INOD answer was followed by AAOI-oriented suggestions and placeholder text.
- Deepvue's suggested prompts and UI polish make average answers feel more capable than the underlying grounding warrants.

Context precedence should be explicit in Mastermind:

```text
entity named in the request
  > pinned context chips
  > selected widget entity
  > global ambient entity
```

The effective context and its timestamps should be visible before submission.

### 6.5 Why Deepvue can feel fast

Supported explanations:

1. dedicated bounded Terminal service instead of an open-ended agent loop;
2. already-loaded symbol, list, screen, and Data Panel context serialized directly;
3. model/route selection for fast fact, research, filing, and calculation classes;
4. precomputed market packets and separated real-time services;
5. cached templates and warm queries;
6. one retrieval/generation call rather than sequential tool turns; and
7. local answer animation that creates perceived streaming.

There is no evidence that MCP is responsible.

### 6.6 Mastermind's latency cause

The current Mastermind gateway executes blocking tool turns, may dispatch them sequentially, then performs a synthesis pass. It buffers the final answer for advice filtering and leak screening before emitting one full-answer SSE delta. Heartbeats stream; answer tokens do not.

This architecture naturally creates 30–60 second perceived latency even when the underlying tools and model are strong.

### 6.7 Live production A/B

The same prompts were sent to live Mastermind production while `/api/health` reported checkout `5ed0b824a26`, matching the then-current `origin/main`.

| Prompt | Surface | Headers / first SSE | First real answer | Done | Tools / model rounds | Citations |
|---|---|---:|---:|---:|---:|---:|
| Situational awareness | Terminal context | 0.82s | 56.68s | 56.68s | 8 / 3 | 0 |
| Situational awareness | Dashboard context | 0.71s | 77.28s | 77.28s | 5 / 3 | 0 |
| AAPL native metrics | Terminal context | 0.54s | 52.12s | 52.12s | 6 / 4 | 0 |
| Minimal no-tool control | bounded control | 0.54s | 3.74s | 3.75s | 0 / 1 | 0 |

The network and local gateway are not slow. Headers arrive in under one second, and a no-tool model round completes in 3.74 seconds. Roughly 48–73 seconds are added by multi-round DeepSeek/tool orchestration, final synthesis, and whole-answer buffering.

The bakeoff ruling is nuanced:

- Deepvue wins current perceived speed and source-link presentation.
- Deepvue's broad answer uses much more web retrieval than its native product context, and source quantity did not ensure relevance or freshness.
- Mastermind has the stronger internal research graph but failed to surface citations in these tested live answers.
- Both products withhold substantive answer text until the response is effectively complete on the paths tested.
- Mastermind should keep the deep route for real investigations and stop sending bounded native-data questions through it.

Mastermind's situational answer covered the requested categories and produced a useful regime/rotation/rates/risk synthesis with section-level July 31/August 1 timestamps. Its `done.citations` array was empty, however, and model-written `Source:` labels were not verifiable citation objects.

The AAPL answer was a clearer contract failure:

- it did not have the requested 1M/3M/12M RS fields and substituted Mansfield RS;
- it described Mansfield `15.96` as roughly 84th-percentile performance, an invalid semantic conversion;
- it substituted an industry percentile for industry rank;
- the next-earnings date it returned was already past;
- it substituted other earnings statistics for latest reported EPS growth; and
- it incorrectly implied that local Mastermind data was “Deepvue-native.”

This is exactly why the typed field registry is P0. A bounded factual route must return the exact field and timestamp, or an explicit null with a reason. Semantic improvisation is worse than missing data.

### 6.8 Exact Mastermind latency path

The live path is:

1. `templates/mm_brain.js` posts to `/api/brain/stream`.
2. `app/main.py` authenticates/checks quota and starts a durable background run.
3. `app/brain_runs.py` detaches generation from the socket and emits keepalives.
4. `engine/neuralweb/brain_gateway.py` assembles live market and per-symbol grounding.
5. Fast lane invokes DeepSeek V4 Pro with native thinking and a large per-round budget.
6. Terminal context allows a larger tool budget; each tool round is a blocking model call.
7. The complete final response is buffered, citation extraction and leak screening run, then one full-answer `delta` is emitted.
8. `templates/mm_brain.js` animates the already-complete answer locally.

The original buffering rationale is partly fossilized: `_post_filter_advice` in `engine/neuralweb/ask_brain.py` is currently a no-op. Leak screening and suggestion extraction still require a safe streaming design, but the old advice filter no longer justifies withholding the entire answer.

Citation loss is also structural. The current extractor recognizes a narrow `rows[].signal_id` shape, while many market, curve, theme, earnings, and symbol tools return different source/as-of structures. Their provenance is discarded instead of normalized into one evidence envelope.

### 6.9 Proposed Mastermind lanes

| Lane | Budget | Behavior |
|---|---:|---|
| Instant fact | p50 <2s TTFV, p95 <5s completion | deterministic intent route, one current packet, zero/one retrieval, fast model or templated renderer, true token/event streaming |
| Native research | p50 <5s TTFV, p95 <15s completion | parallel bounded retrieval over explicit internal contracts, cited synthesis |
| Filing/event | p50 <8s TTFV, p95 <30s completion | source-span retrieval, longer context, claim-level citations |
| Deep investigation | explicit long-running task | multi-tool orchestration, progress ledger, evidence pack, no fake instant promise |
| Calculation/action | p50 <2s | deterministic calculator/compiler, LLM only parses/explains |

The fast lane must not be a safety bypass. It is a narrower contract with fewer ways to be wrong.

---

## 7. Current Mastermind parity and gaps

### 7.1 Where Mastermind is already ahead

- thematic ontology, breadth, acceleration, crowding, episodes, and track record;
- Stage classifier and research page depth;
- multiple regional breadth and factor surfaces;
- evidence/provenance architecture;
- Research Vault, event intelligence, and deterministic briefs;
- Neural Web world state and contextual lobes;
- Prophet plans, live evaluation, and authority fencing;
- bilingual position-size and calculator suite; and
- a broader tool graph for portfolios, charts, fundamentals, earnings, factors, themes, and memory.

### 7.2 Actual competitive gaps

| Gap | Severity | Why it matters |
|---|---:|---|
| One configurable workspace/context bus | P0 | Users experience pages, not an operating system |
| Canonical 1–99 rating passport | P0 | Strong underlying factors are not legible or ubiquitous |
| Empty Stage industry/flow artifacts | P0 defect | Existing UI and AI context silently lose a high-value layer |
| Mastermind instant factual lane | P0 | Perceived intelligence loses before depth is experienced |
| Shared datapoint/query registry | P0 | Screeners, tables, AI, and ratings cannot compound cleanly without it |
| Natural-language-to-validated-AST | P1 | Deepvue turns chat into executable workflow more cleanly |
| Generic bubble and mini-chart widgets | P1 | Theme/state data lacks lightweight visual composition |
| Arbitrary user alert rule grammar | P1 | Many internal alerts, no unified user-authored contract |
| Analyst upgrade/downgrade tape | P1 | Revision breadth is not event-level sell-side action intelligence |
| Mobile/extension capture | P2 | Distribution lever after the data plane is stable |

### 7.3 Concrete defect found and repaired first

The existing Stage Analysis page already has Screener, Stage Board, Industries, Earnings Calls, Alt-Data, and Research tabs. The live classifier is healthy, but the industry surfaces were empty because the orchestrator built industry ranks and flows before producing the current normalized Stage frame, while the older backfill parquet seed was absent.

This docket's first code lane changes the Stage build so current classifier output becomes the explicit input to industry rank/flow construction, with freshness and non-vacuous coverage checks. The resulting context remains display/context-only and does not alter Prophet selection, rank, gates, or size.

Why this first:

- revives an already-designed product surface;
- closes Industry Ranks and Stage-relative context gaps;
- improves Mastermind grounding without a greenfield scoring engine;
- creates a reusable same-day packet for Terminal, briefs, and Neural Web; and
- has a narrow, testable authority boundary.

---

## 8. Target architecture

### 8.1 Shared datapoint registry

Every field exposed to charts, tables, screens, ratings, AI, Neural Web, or Prophet should have one definition:

```text
field_id
label / unit / type
entity and universe compatibility
raw source and license class
observed_at / effective_at / as_of
update cadence and staleness budget
point-in-time policy
missingness semantics
filter comparators
display renderer
authority permissions
```

### 8.2 Workspace contract

```json
{
  "schema": "workspace_layout.v1",
  "revision": 17,
  "breakpoint": "desktop",
  "link_groups": {
    "primary_symbol": {"entity_type": "security"},
    "theme_focus": {"entity_type": "theme"}
  },
  "widgets": [
    {
      "id": "chart-primary",
      "type": "chart",
      "semantic_lane": "primary",
      "grid": {"x": 0, "y": 0, "w": 24, "h": 24},
      "context_in": ["primary_symbol"],
      "context_out": ["primary_symbol"],
      "config_ref": "chart.default.v4"
    }
  ]
}
```

Use semantic lanes and responsive reflow on small screens rather than shrinking a 36-column desktop canvas until it becomes unusable.

### 8.3 AI context envelope

```json
{
  "schema": "ai_context_envelope.v1",
  "request_id": "...",
  "explicit_entities": ["AAPL"],
  "pinned_context": [],
  "ambient_widget_context": {"symbol": "AAOI"},
  "effective_context": {"symbol": "AAPL", "reason": "explicit_request"},
  "source_timestamps": {},
  "screener_ast": null,
  "datapanel_values": [],
  "latency_lane": "instant_fact",
  "provenance_requirement": "field_level",
  "authority": {"may_execute": false}
}
```

### 8.4 Service separation

```text
event and historical snapshot stores
            |
            +--> realtime delta bus
            +--> typed datapoint registry
            +--> rating fabric + vintages
            +--> screen/query executor
            +--> alert/rule evaluator
            +--> workspace context bus
            +--> AI context compiler/router
            +--> Neural Web context packets
            +--> Prophet shadow features after validation only
```

---

## 9. Neural Web and Prophet integration

Deepvue-style ratings and theme ranks are descriptive context until independently validated. Integration should occur in layers.

### 9.1 Neural Web

Neural Web may consume:

- rating components, cohort, coverage, freshness, and stability;
- industry rank and Stage distribution;
- theme breadth, residual strength, persistence, dispersion, concentration, and witnesses;
- screener membership as a timestamped observation;
- explicit contradictions and missingness; and
- AI evidence packets only when source claims are retained.

Each packet must declare whether it is observed, derived, inferred, or model-generated.

### 9.2 Prophet

No imported Deepvue-like score may change Prophet rank, entry gate, direction, timing, or size merely because it is intuitive.

Promotion path:

1. reconstruct point-in-time historical vintages;
2. freeze feature semantics and universe eligibility;
3. join after selection in shadow mode;
4. measure incremental information beyond existing Prophet features;
5. test by regime and liquidity cohort;
6. predeclare promotion thresholds;
7. require out-of-sample evidence and calibration stability; and
8. preserve an explainable contribution trace.

The safer first use is abstention/context: stale, contradictory, concentrated, or low-coverage states may reduce confidence before any state is allowed to increase it.

---

## 10. Build docket

### Wave 0 — repair the substrate and prove the benchmark

1. **Stage Industry Intelligence repair** — implemented in this lane.
2. Add same-day industry coverage/freshness assertions and fail visibly on vacuous output.
3. Point Mastermind Stage peer context at the current Stage packet rather than a stale overview snapshot.
4. Preserve this three-prompt Deepvue benchmark as the first row in a permanent latency/quality harness.
5. Instrument Mastermind time-to-first-visible-content, total time, tool count, context bytes, and cache status.

Acceptance:

- non-empty industry artifacts when the Stage universe and taxonomy are healthy;
- artifact as-of matches the live Stage build;
- idempotent same-date rebuild;
- no Prophet authority change;
- reproducible AI benchmark with cold/warm labels.

### Wave 1 — workspace and instant intelligence

1. Ship a configurable Terminal workspace around existing Theme, Stage, Industry, Brief, Screen, Heatmap, and Chart contracts.
2. Implement semantic link groups and visible effective context.
3. Add the instant factual AI lane with a precomputed context packet and true incremental output.
4. Compile natural language into a validated screener AST with preview and diff.
5. Package Theme Tracker++ as a compact dockable widget.

Acceptance:

- mobile reflow uses semantic lanes;
- context propagation is deterministic and inspectable;
- p95 instant-fact completion under five seconds on warm production;
- no ticker result can originate directly from LLM prose;
- every Theme field has provenance and an as-of time.

### Wave 2 — rating fabric and rules

1. Ship display-only `equity_rating.v1` across stock, screen, watchlist, chart, and AI surfaces.
2. Store daily vintages and contribution traces.
3. Add generic bubble and mini-chart widgets over the datapoint registry.
4. Build the user-authored alert/rule grammar.
5. Create an event-level analyst upgrade/downgrade tape with licensed/primary evidence.

Acceptance:

- full component/missingness visibility;
- point-in-time replay;
- alert idempotency, deduplication, and replay tests;
- rating authority remains display/context until validation passes.

### Wave 3 — compounding workflows

1. Combo Lists and persistent list sections.
2. Shareable screens, prompts, dashboard templates, and cited investigations.
3. Bar replay and synchronized multi-chart diagnostics where Prophet research benefits.
4. Mobile research views and cashtag capture extension.
5. Education/prompt library that teaches existing proprietary intelligence.

---

## 11. Permanent AI bakeoff

Test both systems with identical timestamped prompts and explicit context packets.

| Class | Example | Required scoring |
|---|---|---|
| Simple fact | price, next earnings, one rating | freshness, numeric accuracy, TTFV, citation |
| Native packet | RS + Stage + industry + earnings | internal-context use, field provenance, missingness honesty |
| Current market | regime + breadth + themes + liquidity | source quality, timestamp coverage, unsupported claims |
| Filing/event | explain a reported quarter from primary sources | claim/source-span correctness |
| Screener | compile multi-condition universe query | AST fidelity and executable result correctness |
| Calculation | position sizing with explicit inputs | deterministic math and units |
| Context collision | explicit INOD while ambient AAOI | context precedence correctness |
| Deep synthesis | Neural Web + Prophet question | tool selection, contradiction handling, authority discipline |

Record:

- cold/warm/cache status;
- p50/p95 time to first visible content and completion;
- prompt and context bytes;
- number and duration of retrieval/tool calls;
- citation precision and source recency;
- factual/numerical correctness;
- explicit-context utilization;
- action success and deterministic reproducibility;
- unsupported-claim rate; and
- useful verified information per second.

Do not compare one cached Deepvue quote with one cold Mastermind investigation and call that architecture.

---

## 12. Product and visual direction

Do not copy Deepvue's pale lavender chrome, tiny typography, repeated micro-controls, icons, onboarding wording, or freeform panel density.

Mastermind should win on:

- a clearer distinction between market state, evidence, interpretation, and action;
- progressive disclosure: glance, inspect, study;
- denser expert mode without low-contrast clutter;
- provenance drawers and visible as-of times;
- semantic workspace lanes that recompose on mobile;
- keyboard-first navigation;
- motion that shows context propagation, rank movement, and temporal revision; and
- honest empty/stale/error states instead of successful-looking blank panels.

Recommended default workspace:

```text
top command/context bar
  ├─ primary chart + evidence markers
  ├─ compact Theme/Industry/Stage state rail
  ├─ watchlist/screener result lane
  └─ Mastermind Terminal with visible context and route

expandable lower drawer
  ├─ rating passport
  ├─ fundamentals / earnings event spine
  ├─ breadth and market structure
  └─ Neural Web / Prophet diagnostic trace
```

---

## 13. Already covered / excluded fence

### Already covered; integrate rather than rebuild

- existing charting-terminal indicators, detections, and command surface;
- Stage classifier and Stage Analysis page;
- Thematic Intelligence Layer and sector-cycle history;
- watchlists, portfolios, positions, and calculators;
- Research Vault and company-event work;
- existing deterministic market briefs;
- Neural Web world state and lobe contracts; and
- Prophet evaluation and authority framework.

### Excluded from literal parity

- Deepvue source code, CSS, assets, icons, copy, prompt text, and proprietary datasets;
- undisclosed rating weights;
- vendor customer data or saved objects;
- representing price performance as institutional flow;
- representing an LLM-generated score as validated alpha;
- a separate Deepvue-looking application beside Mastermind; and
- Prophet authority before point-in-time, out-of-sample validation.

### Deferred until a real data-rights path exists

- licensed real-time exchange data replication;
- consensus estimates and analyst-action coverage at Deepvue breadth;
- a sub-three-minute global earnings/fundamental SLA;
- mobile and extension distribution; and
- a large library of trader-branded proprietary indicator names.

---

## 14. Source registry

Official Deepvue sources:

- [Deepvue homepage](https://deepvue.com/)
- [Charts](https://deepvue.com/charts/)
- [Screener](https://deepvue.com/screener/)
- [Watchlists](https://deepvue.com/watchlist/)
- [Dashboard](https://deepvue.com/dashboard/)
- [AI Terminal](https://deepvue.com/terminal/)
- [Creating a Custom Dashboard](https://docs.deepvue.com/articles/creating-a-custom-dashboard)
- [Technical datapoints](https://docs.deepvue.com/articles/technical)
- [Proprietary ratings](https://docs.deepvue.com/articles/proprietary-ratings)
- [Theme Tracker](https://docs.deepvue.com/articles/theme-tracker-app)
- [RS Rating](https://deepvue.com/ratings/deepvue-rs-rating/)
- [Absolute Strength](https://deepvue.com/ratings/absolute-strength-rating/)
- [EPS Rating](https://deepvue.com/ratings/use-the-eps-rating-to-evaluate-stocks/)
- [Fundamental Rating](https://deepvue.com/ratings/fundamental-rating/)
- [Composite Rating](https://deepvue.com/ratings/composite-rating/)
- [Terms of Use](https://deepvue.com/terms-of-use/)

AI response-shape comparison:

- [Perplexity Sonar API response](https://docs.perplexity.ai/api-reference/sonar-post)
- [Perplexity OpenAI compatibility](https://docs.perplexity.ai/docs/sonar/openai-compatibility)

---

## Final ruling

Deepvue should be watched weekly, but not feared as a superior intelligence engine.

It has done the annoying, valuable work of making ordinary calculations feel like one coherent professional product. Mastermind has already done much of the harder intelligence work and left too much of it scattered, stale, or hidden.

The strategic program is therefore:

1. repair the live data seams;
2. unify the datapoint and context contracts;
3. package existing intelligence into one configurable workspace;
4. add a genuinely fast bounded AI lane;
5. ship transparent rating and theme passports;
6. turn language into deterministic screen/action programs; and
7. let Neural Web and Prophet consume those layers only through provenance and validation gates.

Deepvue's product thesis is correct. Its implementation is beatable. The path to beating it is to productize what Mastermind already knows, not to cosplay its interface.
