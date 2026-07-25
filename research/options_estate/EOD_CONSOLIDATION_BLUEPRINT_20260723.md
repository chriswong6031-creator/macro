# Macro Dashboard Options: EOD Consolidation and Upgrade Blueprint

**Date:** 2026-07-23  
**Audience:** Product owner and Claude implementation agent  
**Macro Dashboard repository:** `/Users/chriswong/Documents/Cluade/Macro Dashboard`  
**Local checkout audited:** detached `5c90bf15229`  
**Current remote source audited:** `origin/main@d16a5cf669b`  
**Related handoff:** [Terminal Options competitive upgrade review](./OPTIONS_TERMINAL_UPGRADE_REVIEW_2026-07-23.md)  
**Decision:** keep Macro Dashboard as the settled EOD/next-session options research product, consolidate its pages into one coherent workspace, and move live/intraday jobs to Terminal.

> The local Macro checkout is behind `origin/main` and has a heavily dirty worktree. It was not modified. The local generated `site/` contained only `gex.html`, `options_screener.html`, `flow_desk.html`, and `darkpool.html`; the current `origin/main` contains the newer builders/templates for all eight URLs supplied for review. Source findings below use `origin/main` where stated, while visual observations of those four pages use the local generated artifacts. The public domain was not a reliable audit target from this environment, so do not assume deployed HTML matches either checkout. Reconcile production, deployed routes, and generated artifacts before adding redirects.

## Executive verdict

Macro Dashboard’s options work is not primitive. The GEX page in particular contains a large amount of serious analysis:

- gamma regime and flip;
- call/put walls, magnet, structural band, and expected move;
- strike/expiry exposure;
- term structure, smile, skew, and risk reversal;
- GEX/DEX/VEX/charm-derived context;
- daily flow summaries and 0DTE share;
- stated model assumptions and limitations.

The product feels messy because eight pages mix different markets, cadences, and jobs:

- EOD options positioning;
- EOD options flow;
- ordinary equity movers;
- an hourly equity reclaim scanner;
- delayed off-exchange equity statistics;
- index-level gamma/systematic/volatility regime models.

They appear together under “Options & Flow” even though several are not options products at all. Coverage, freshness, model language, and interaction patterns differ on every page. The user cannot perform a continuous:

`review close → find change → inspect ticker → save watchlist → set next-session alert → review outcome`

workflow.

The correct answer is not to copy Terminal into Macro or copy all Macro pages into Terminal. Use cadence as the product boundary:

> **Terminal explains what is changing now. Macro explains what settled at the close, what changed from prior sessions, and what deserves research for tomorrow.**

Macro should become **Options & Positioning — After Close**, with four task-oriented modes:

1. Daily Brief
2. Scanner
3. Positioning & Volatility
4. Leaders & History

Daily Movers, Market Structure, and Off-Exchange Activity remain Macro products but leave the Options navigation. Intraday Flow moves to Terminal.

## Immediate decisions

### Keep and strengthen

- Flow Desk’s EOD market/sector hierarchy;
- GEX’s index-first positioning and volatility research;
- Options Screener’s cross-sectional dataset;
- Flow Leaders’ recurrence, DTE breadth, caution tags, and OI-confirmation concepts—after fixing its logic;
- explicit `EOD`, `delayed`, `direction approximate`, and dealer-sign caveats;
- static generation for after-close research, provided publication is atomic and fresh.

### Consolidate

- Flow Desk + corrected Flow Leaders → **Daily Brief** and **Leaders & History**;
- Options Screener + GEX universe selector → **Scanner**;
- GEX page research sections → **Positioning & Volatility** ticker workbench;
- duplicated ticker flow summaries → one shared ticker detail.

### Move

- Intraday Flow live board → Terminal;
- live-relevant SPX gamma/level subset → Terminal 0DTE & Index, using a properly labeled live model;
- alert execution and live monitoring → Terminal.

### Remove from Options navigation

- Daily Movers;
- Dark Pool;
- Market Structure;
- Intraday Flow.

### Rename

- `Dark Pool Desk` → **Off-Exchange Activity**;
- `Flow Desk` in Macro → **Options Daily Brief**;
- `Options Screener` → **EOD Options Scanner**;
- `Market Structure` → **Market Regime**;
- `Fresh Positioning` based only on vol>OI → **Volume Exceeds Prior OI**;
- immature `IV Rank` → **IV Percentile — N Sessions**.

## Current route inventory and disposition

The supplied URLs are:

- `gex.html`
- `options_screener.html`
- `movers.html`
- `flow_desk.html`
- `intraday_flow.html`
- `flow_leaders.html`
- `darkpool.html`
- `market_structure.html`

### Route map

| Current route | What it actually is | Cadence/domain | Disposition |
|---|---|---|---|
| `gex.html` | Large EOD options positioning and volatility workbench with embedded flow | EOD options | Keep; split into Daily Brief summary + Positioning & Volatility detail |
| `options_screener.html` | Cross-sectional IV/GEX/walls/max-pain/flow table | EOD options | Keep as Scanner; add freshness, liquidity, saved views, and ticker drilldown |
| `movers.html` | Equity price gainers/losers and themes | EOD stocks | Move to general Markets/Stocks |
| `flow_desk.html` | EOD market tide, sector premium, top names, and ETF proxy | EOD options | Make the default Daily Brief |
| `intraday_flow.html` | Mostly equity-price/volume reclaim and continuation scanner with one soft options leg | Hourly/intraday equities | Move live product to Terminal; retain an EOD next-session candidate receipt |
| `flow_leaders.html` | Multi-day options-flow recurrence and washout-turn research | EOD options | Correct logic; merge into Leaders & History |
| `darkpool.html` | FINRA off-exchange short-volume and delayed ATS transparency data | EOD/weekly equities | Rename and move to Macro Market Structure; remove directional claims |
| `market_structure.html` | SPX gamma plus modeled CTA/vol-control, correlation, and vol-curve context | EOD macro/index | Keep as top-level Market Regime, not Options |

The current navigation source on `origin/main`, `templates/_navlinks.html.j2:78-93`, places these unrelated products together. That is the first consolidation target.

## Why the split between Terminal and Macro is justified

The current separation feels arbitrary because both apps show options numbers. It becomes useful if the distinction is based on when a fact can be known.

| Data/job | Terminal | Macro Dashboard |
|---|---|---|
| Option trade and NBBO | Live | Daily archive/summary |
| Approximate aggressor side | Live inference with confidence | Session aggregate and methodology |
| Current volume | Live | Settled daily total |
| Open interest | Prior-night vintage | Confirmed next-session change and history |
| Static OI GEX | Reference layer | Canonical EOD research |
| Intraday volume-estimated GEX/pressure | Live modeled layer | Archived/researched after close |
| 0DTE index management | Primary product | Close recap and next-session context |
| Signal detection/management | Live | Outcome, confirmation, research |
| Scanner | Live alerts/presets | Broad EOD cross-section |
| Replay | Intraday synchronized replay | Multi-session study and backtest |
| Long reports/methodology | Link only | Primary home |

The apps still need one conceptual Options navigation, shared symbol/watchlist state, and deep links. The user should perceive one product with two horizons, not two unrelated sites.

## Page-by-page assessment

### 1. GEX / Options Desk

#### Current strengths

The GEX page is the most technically mature Macro options surface. The underlying model implements or presents:

- gamma exposure by strike and expiry;
- net gamma profile and flip;
- call/put walls and level strength;
- max pain;
- expected move;
- IV term structure and smile;
- 25-delta skew/risk reversal;
- expiry ladder;
- delta/vanna/charm context;
- index-versus-single-name assumption caveats.

Relevant source areas on `origin/main`:

- `engine/gex_model.py:1-26,113-244,290-360,719-805`
- `scripts/build_gex_board.py:1-20,222-231`

The generated page correctly says it uses daily delayed chains, is not live intraday flow, and relies on an unobservable dealer-sign assumption (`site/gex.html:580`). This honesty is worth preserving.

#### Current problems

1. **It is several products on one extremely long page.**  
   A beginner verdict, ticker lookup, market weather, daily flow, wall cards, structural band, directional tilt, strike charts, gamma profile, strike×expiry matrix, skew, term, expiry ladder, and methodology all compete in one scroll.

2. **Index and single-name confidence are not visually separated enough.**  
   The page acknowledges that the sign assumption is more robust for indices and fragile for individual names, but a polished single-name “tilt” can still feel equally authoritative.

3. **The page embeds flow that belongs to a shared ticker detail.**  
   This duplicates Flow Desk/Scanner concepts and encourages inconsistent definitions.

4. **Cadence copy is internally confusing.**  
   The bottom notes that daily delayed OI analysis misses 0DTE (`site/gex.html:657`), while an earlier “Today’s measured flow” block reports 0DTE share from a separate flow dataset. Both can be true, but the page does not make the dataset boundary obvious.

5. **Static levels are at risk of being read as targets.**  
   Max pain, walls, magnet, and “volatility hole” require persistent model/assumption badges and historical-change context.

#### Recommended design

Default to SPX, SPY, QQQ, and IWM. Use four subviews:

1. **Overview**
   - spot;
   - expected move;
   - net gamma/regime;
   - flip;
   - call/put walls;
   - change from yesterday;
   - quality and sign-assumption badge.

2. **Exposure**
   - strike × expiry matrix;
   - gamma/DEX/VEX/charm lenses;
   - expiry ladder;
   - call/put separation.

3. **Volatility**
   - IV level/history;
   - term structure;
   - skew/risk reversal;
   - event comparison;
   - expected versus realized move.

4. **History & Assumptions**
   - wall/flip migration;
   - OI change;
   - model version;
   - sign convention;
   - source/vintage;
   - comparable outcome studies.

Move the 650-name selector into Scanner. A scanner result deep-links into this workbench.

### 2. Options Screener

#### Current strengths

The current dataset covers hundreds of names and combines:

- IV30;
- IV percentile/rank;
- implied move;
- put/call OI;
- option volume;
- gross premium;
- max pain;
- GEX regime/tier;
- approximate net-premium tone.

The generated page is explicit that current IV history is young and that net direction is soft (`site/options_screener.html:396`).

#### Correctness and product problems

On `origin/main`, `scripts/build_options_screener.py` and its template reveal:

1. `median_depth_days` is based on observation-row counts, not elapsed calendar days (`build_options_screener.py:390-394,520-527`).
2. “Sector” can be the first thematic basket label; unmatched names fall back to “ETF / Index” (`:73-105`).
3. `pain_dist_pct` uses max pain as the denominator rather than spot, unlike the wall-distance calculations (`:413-416`).
4. The payload can mix stale rows with current rows and includes string `"nan"` gamma regimes.
5. Per-row `asof` exists but the table omits an As-of column (`templates/options_screener.html.j2:460-564`).
6. “Max pain” copy describes gravitational pull too confidently for a debated heuristic.
7. There is no ticker drilldown, watchlist, saved scan, alert, catalyst, or contract-liquidity workflow.
8. While every name has immature history, “High IV Rank” cannot mean a mature annual percentile.

The local generated page also displayed broken filter/template markup visibly in the UI. Even if this has changed on `origin/main`, generated HTML needs a render/interaction QA gate.

#### Required changes

- hard freshness gate and per-row age;
- true GICS sector plus separate theme/basket field;
- `IV Percentile — 26 sessions`, not annual IV Rank, until enough history exists;
- disable misleading mature-history presets;
- fix max-pain distance denominator;
- normalize null/NaN values at schema boundary;
- make every ticker a deep link;
- add earnings/event date;
- add underlying liquidity, contract count, total OI/volume, median spread, and quote-quality coverage;
- filters for DTE, moneyness, liquidity, event window, exposure regime, flow change, and OI confirmation;
- saved screens, watchlists, exports, and next-session alerts.

The scanner should support comparison against the ticker’s own history and a stable same-name cohort, not just sort absolute dollars.

### 3. Flow Desk / Group Flow Heatmap

#### Current strengths

This is the best foundation for Macro’s landing page. It presents:

- market gross premium and soft net tone;
- 0DTE share;
- sector/theme rollups;
- top net-impact names;
- index/ETF context;
- extensive methodology and direction caveats.

The generated page states that gross premium magnitude is more reliable than minute-tick-rule direction (`site/flow_desk.html:378-391`). That is a good product-truth pattern.

#### Main correctness issue: unlike histories

The headline summarizes the whole universe, but the 30-session sparkline and day-over-day comparison are based only on SPY, QQQ, IWM, and DIA:

- `scripts/build_flow_desk.py:184-266,673-680`
- `templates/flow_desk.html.j2:397-403,446-451`

The current headline can therefore show roughly the premium of hundreds of names while the nearby trend compares four ETFs. The visual relationship implies a common basis that does not exist.

#### Other problems

- Despite the name, the local page is primarily cards and ranked lists, not an interactive heatmap.
- It has no drillthrough into a unified ticker history.
- There is no “what changed from yesterday?” receipt with stable cohorts.
- Many repeated cards lengthen the page without advancing the workflow.
- ETF creation/redemption estimates are correctly called proxies, but they sit close enough to options flow to be mistaken for the same domain.

#### Recommended role

Rename this **Options Daily Brief** and make it the default Macro Options mode.

Required sections:

1. **Close receipt**
   - dataset/session;
   - coverage;
   - all-universe gross premium versus same-universe history;
   - 0DTE share;
   - data quality.

2. **What changed**
   - largest standardized changes in Greek flow, IV, skew, GEX regime, walls, and OI;
   - separate observed, inferred, and modeled groups.

3. **Index close**
   - SPX/SPY/QQQ/IWM regime;
   - expected move;
   - wall/flip changes;
   - 0DTE recap.

4. **Sector/theme concentration**
   - stable-universe normalized measures;
   - gross activity first;
   - approximate direction as a secondary lens.

5. **Names for tomorrow**
   - flow recurrence;
   - new OI confirmation;
   - IV/skew change;
   - event/catalyst;
   - Terminal alert link.

Maintain two honest histories:

- all-universe or stable-cohort market history;
- explicitly named Index ETF tape proxy.

### 4. Flow Leaders

#### What is valuable

The concept—multi-session recurrence, OI confirmation, DTE breadth, caution flags, and possible washout transitions—is appropriate for an EOD research product.

#### Critical logic bug

`engine/flow_leaders.py:393-440` says it detects a positive flip after at least three recent negative sessions, but:

- it counts all negative observations in the preceding history;
- it does not require consecutive negatives immediately before the flip;
- it can select an old positive observation after any accumulated negatives.

The builder then admits any row with non-null `days_since_inflection` (`scripts/build_flow_leaders.py:934-940`). In the current artifact, Board A and Board B both have 129 rows, a strong sign that almost every eligible leader became a supposed washout turn.

#### Fix specification

Detect the newest valid local pattern:

`negative, negative, negative, positive`

Requirements:

- negatives must be consecutive and immediately precede the positive;
- use the most recent transition;
- freshness window, initially 0–5 sessions;
- Board B membership requires actual washout conditions, not only a badge;
- interrupted runs and old historical flips must fail;
- record exact source dates and values;
- add tests for `---+`, `--0+`, `---+---`, old flip, missing sessions, and insufficient history.

After correction, merge it into:

- **Daily Brief → Names for tomorrow**
- **Leaders & History → Recurrence / Transitions / OI-confirmed**

Do not keep it as another top-level page.

### 5. Intraday Flow

#### What it actually does

This is primarily an equity continuation/reclaim model. Its legs include:

- washout;
- price above VWAP/previous close;
- relative volume;
- volume durability;
- a soft net-options-premium leg;
- multi-timeframe price upturn;
- trap filter.

See `engine/intraday_flow.py:368-526` on `origin/main`.

The builder’s fast path uses hourly equity bars and fetches limited options enrichment separately (`scripts/build_intraday_flow.py:1-31,1158-1286`). It is not an intraday options-feed signal engine.

#### Product-language problem

The model/template uses “Buy now,” “Take profits,” and other direct actions despite also calling itself display-tier:

- `engine/intraday_flow.py:627-827`
- `templates/intraday_flow.html.j2:337-428`

#### Disposition

- move the live board to Terminal;
- rename it **Reclaim Monitor** until a true options-originated detector exists;
- replace commands with `developing`, `confirmed`, `weakening`, `failed`, and predeclared evidence;
- connect it to live underlying bars and normalized options events;
- retain only an after-close **Tomorrow Candidates** snapshot in Macro;
- measure its own outcomes separately from options-native signals.

### 6. Daily Movers

`scripts/build_movers_page.py` and `templates/movers.html.j2` show an ordinary stock price/theme movers page. It contains no meaningful options analysis.

Action:

- move to `Markets → Movers`;
- remove from Options navigation;
- allow an optional options-context column only when it deep-links to the shared Options ticker workbench.

### 7. Dark Pool Desk

#### What the data actually is

The generated page correctly says:

- it is not live;
- it is not direct dark-pool print data;
- daily data is FINRA-facility short-sale and total volume;
- weekly per-ATS data can lag two to four weeks.

See `site/darkpool.html:365-375`.

The local artifact was particularly stale:

- data as of 2024-02-07;
- page built 2026-07-13;
- sparse display;
- empty weekly ATS section.

That should trigger a hard stale/unavailable state, not a polished research desk.

#### Unsupported directional claims

`engine/darkpool_context.py` turns elevated off-exchange share and FINRA short-volume changes into phrases such as:

- “Quiet accumulation”
- “Distribution pressure”
- “Big blocks trading in the dark”
- “institutions build a position quietly”

The source does not support those conclusions. Daily FINRA short-sale volume can include temporary short marking used to facilitate customer long sales and does not identify held short positions or directional conviction.

References:

- [FINRA: Understanding short-sale volume data](https://www.finra.org/rules-guidance/notices/information-notice-051019)
- [FINRA daily short-sale volume description](https://www.finra.org/finra-data/daily-short-sale-volume-transaction-data)

#### Required disposition

Rename to **Off-Exchange Activity** and move outside Options.

Keep:

- off-exchange share;
- own-history z-score;
- recent change;
- coverage;
- publication lag;
- ATS venue breakdown.

Replace directional labels with:

- unusually elevated;
- rising;
- fading;
- typical;
- direction unknown.

Remove:

- accumulation/distribution;
- “biggest players”;
- “institutional footprint”;
- live dark-pool implications.

If the data is older than the page’s freshness SLA, show a blocking stale panel and withhold rankings. A true Terminal dark-pool product would require licensed equity prints, TRF/ATS source, price/quote context, block clustering, and live chart levels. This EOD page cannot substitute for it.

### 8. Market Structure

#### Correct home

The page combines:

- SPX gamma;
- modeled CTA/vol-control flow;
- correlation/dispersion;
- volatility-curve context.

It belongs in Macro as **Market Regime**, not under Options. Terminal may consume only its live-relevant index levels/regime through a shared contract.

#### Correctness and false-precision issues

On `origin/main`:

1. `scripts/build_market_structure.py` does not emit `week_map`, but the template renders a full Weekly Range section (`templates/market_structure.html.j2:468-535`). The current output remains “warming up.”
2. The DAG renders the page before the parallel build refreshes its artifact (`config/dag.yml:358-359` versus `449-476`). A run can publish the previous artifact.
3. A tooltip claims a “70/30 SPX/SPY blend reconstruction,” but the builder reads only `data/cboe/gex_SPX.parquet`; no matching blend implementation was found.
4. The vol-control model assumes a fixed $300B pool and 10% target, then presents precise `$X.XB today` values. These are stylized proxies, not observed flow (`engine/systematic_flows.py:45-88`).

#### Required changes

- build data before render;
- implement or remove `week_map`;
- remove the 70/30 claim unless code and tests prove it;
- put `STYLIZED PROXY` beside every CTA/vol-control output;
- prefer state and sensitivity range over a single precise dollar estimate;
- expose assumptions and change scenarios;
- keep it independent from Options navigation.

## Cross-suite product problems

### 1. Coverage has no common contract

Current `origin/main`/generated artifacts illustrate the mismatch:

| Surface | Audit-time generated coverage |
|---|---:|
| GEX universe | about 650 rows |
| Options Screener | 403 names |
| Flow Desk | about 370 names |
| Flow Leaders | about 352 names |
| Off-Exchange/Dark Pool | 273 names; 166 with off-exchange-share data |
| Market Structure | index-level only |

These are snapshot counts, not permanent product requirements. The problem is that the user sees different universes without a common explanation. A user cannot tell whether absence means:

- no signal;
- no options;
- missing chain;
- stale row;
- filter exclusion;
- collector failure;
- unsupported symbol.

Every page needs:

- universe ID/version;
- eligible count;
- processed count;
- fresh count;
- missing/failed count;
- same-name historical cohort;
- row-level as-of.

### 2. Freshness is page-level when it needs to be metric-level

A generated page can combine:

- latest equity close;
- prior-night OI;
- delayed chain;
- soft signed flow;
- multi-week ATS data;
- a model built later.

One page timestamp cannot describe all of them. Every metric carries:

`value · observation as-of · published at · cadence · source class · quality · assumptions`

### 3. Observed, inferred, and modeled data look equivalent

Use consistent truth badges:

- **OBSERVED:** price, volume, trade, OI vintage.
- **INFERRED:** side, recurrence grouping, opening estimate.
- **MODELED:** dealer sign, gamma regime, systematic-flow proxy, expected scenario.

Visual polish must not erase epistemic differences.

### 4. The suite lacks workflow state

There is no shared:

- ticker;
- watchlist;
- saved scan;
- alert;
- note/journal;
- session/date;
- signal;
- outcome.

Clicking a row should open the same ticker object everywhere, not a new bespoke page.

### 5. Explanations overwhelm task flow

The pages often contain lengthy disclaimers, tutorial blocks, and method notes interleaved with data. The caution is valuable, but repeating it makes already long pages harder to use.

Use:

- compact persistent badges;
- a one-sentence local caveat;
- an expandable methodology drawer;
- one canonical metric dictionary;
- consistent wording across pages.

## Target Macro information architecture

Create one workspace:

# Options & Positioning — After Close

### Mode 1: Daily Brief

Answers: “What happened today, what changed, and what matters tomorrow?”

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ Session 2026-07-23 · EOD COMPLETE · OI AS OF 2026-07-22 · coverage 403/420 │
├──────────────────────────────────────────────────────────────────────────────┤
│ Market activity │ 0DTE share │ SPX regime │ IV/skew change │ data quality   │
├───────────────────────────────┬──────────────────────────────────────────────┤
│ What changed since yesterday │ Index close: levels, wall/flip migration     │
├───────────────────────────────┼──────────────────────────────────────────────┤
│ Sector/theme concentration    │ Names for tomorrow                          │
├───────────────────────────────┴──────────────────────────────────────────────┤
│ Confirmed OI changes · Recurrence · Events · Create Terminal watch/alert    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Mode 2: Scanner

Answers: “Which names match my EOD options research criteria?”

- sortable/filterable table;
- real sector and separate themes;
- DTE and event filters;
- IV/skew/term;
- GEX regime/change;
- flow activity;
- confirmed ΔOI;
- liquidity/quote quality;
- row age;
- saved screens;
- watchlist/alert/export;
- ticker deep link.

Starter presets:

- unusual activity versus own history;
- confirmed new OI;
- repeated multi-day campaign;
- IV/skew dislocation;
- gamma-regime change;
- wall migration;
- event premium;
- liquid 0DTE names;
- tomorrow-watch candidates.

Presets are templates, not separate pages.

### Mode 3: Positioning & Volatility

Answers: “What does settled positioning and implied volatility look like for this ticker?”

- overview;
- exposure surface;
- volatility surface/history;
- OI and strike/expiry change;
- walls/flip history;
- model assumptions;
- link to Terminal Ticker Lab.

### Mode 4: Leaders & History

Answers: “Which themes persist, what just turned, and what historically followed?”

- corrected recurrence leaders;
- fresh transitions;
- OI-confirmed campaigns;
- sector/theme history;
- OPEX/expiry studies;
- detector performance;
- session archive;
- replay deep links.

### Separate Macro products

```text
MACRO
├── Market Regime
│   └── SPX gamma · volatility curve · correlations · systematic proxies
├── Options & Positioning — After Close
│   ├── Daily Brief
│   ├── Scanner
│   ├── Positioning & Volatility
│   └── Leaders & History
├── Off-Exchange Activity
└── Markets
    └── Daily Movers
```

## Features Macro is missing

Once page consolidation and correctness are complete, the most valuable EOD additions are:

### 1. Confirmed OI change

- strike × expiry ΔOI;
- call and put kept separate;
- next-day confirmation of intraday campaigns;
- opening/closing estimates clearly distinct from settled fact;
- multi-day cumulative change;
- OI vintage and no-lookahead controls.

### 2. OI-change history map

A strike × date map showing:

- confirmed OI;
- ΔOI;
- underlying close;
- walls/flip;
- expiration removal;
- event annotations.

This complements Terminal’s strike × intraday-time map.

### 3. “What changed” engine

Rank changes rather than absolute values:

- IV and skew residual;
- term inversion;
- gamma regime;
- flip/wall movement;
- OI concentration;
- repeat activity;
- sector breadth;
- 0DTE share;
- data quality/coverage.

Normalize to the ticker’s own history and same-time/cadence cohort.

### 4. OPEX and expiration calendar

- monthly/weekly expiration concentration;
- large exposure removal;
- roll/migration;
- expected change in gamma/charm;
- post-expiry historical behavior;
- event and macro-calendar overlay.

### 5. Volatility history and event studies

- IV versus realized;
- expected versus realized move;
- skew/risk-reversal history;
- term curve percentile;
- earnings/macro-event implied move accuracy;
- regime-conditioned distributions.

### 6. Signal research and validation

For Terminal detectors:

- sample size;
- outcome distribution;
- MFE/MAE;
- time to peak;
- horizon;
- spread/slippage;
- regime/ticker/DTE cohorts;
- calibration;
- detector version;
- historical examples.

Macro is the natural home for this depth.

### 7. Tomorrow watchlist handoff

One click creates:

- shared watchlist item;
- reason/evidence snapshot;
- next-session Terminal alert;
- target/invalidation level if the user defines one;
- link back to the EOD source.

### 8. Stable exports and research API

Advanced users expect:

- CSV/JSON;
- saved query;
- daily snapshot IDs;
- schema version;
- metric dictionary;
- reproducible historical query.

## Shared data and product contracts

The current `engine/options_hub.py` already points toward a common data plane for volatility, GEX, OI movers, hot contracts, cross-root context, and flow z-scores. Evolve this into a versioned shared service rather than letting both front ends invent metrics independently.

### Static research plus dynamic user state

Keep after-close research artifacts static and immutable, but do not try to encode personalized workflow state into generated HTML or another localStorage silo.

Add an authenticated shared user-state service used by Macro and Terminal:

- one identity/SSO session;
- plan and data entitlements;
- watchlists and tags;
- saved Macro scans;
- Terminal alert definitions and delivery preferences;
- notes/journal links;
- last selected symbol/session;
- stable signal/replay references.

Macro renders the immutable research generation, then hydrates a small authorized user overlay. The static artifact must remain cacheable and reproducible; the user overlay must remain private, owner-scoped, revocable, and unavailable to static/CDN caches.

Canonical ownership:

- Terminal owns live detection, lifecycle, delivery, and intraday replay;
- Macro owns full signal research, backtests, calibration, EOD Leaders, and historical outcomes;
- Terminal may show a compact calibration summary and link to Macro;
- Macro may create a next-session alert definition and link to Terminal;
- the existing Terminal Leaders/Leader Radar are migrated into Macro’s **Leaders & History**, not retained as a second independent ranking system.

### Shared identity

- canonical symbol/product ID;
- OCC contract ID;
- multiplier/settlement;
- underlying mapping;
- index/ETF relationship;
- sector and theme as separate taxonomies;
- supported universe and reason.

### Shared provenance object

```json
{
  "metric_id": "net_gamma_oi_model",
  "schema_version": "metric_provenance_v1",
  "observation_asof": "2026-07-22T20:00:00-04:00",
  "published_at": "2026-07-23T06:10:04Z",
  "cadence": "EOD_T_PLUS_1_OI",
  "source_class": "DELAYED_CHAIN",
  "truth_class": "MODELED",
  "universe_id": "us_options_liquid_v7",
  "quality": "COMPLETE",
  "model_id": "gex_oi_sign_assumption_v3",
  "assumptions": ["dealer_call_short_put_long_convention"]
}
```

### Shared deep-link state

At minimum:

- `symbol`
- `contract`
- `session`
- `expiry`
- `signal_id`
- `view`

Example conceptual links:

```text
/terminal/options/ticker?symbol=NVDA&session=2026-07-23&signal_id=...
/macro/options/positioning?symbol=NVDA&session=2026-07-23
```

### Atomic publication

Every nightly run should:

1. collect;
2. validate;
3. build all option artifacts;
4. run correctness/freshness checks;
5. render pages;
6. publish one immutable generation;
7. switch manifest pointer atomically.

Never render a page before its artifact in the same DAG generation. Never combine prior and current generations without an explicit badge.

## Copy and product-truth rules

Use:

- `ask-side/bid-side estimate`;
- `direction approximate`;
- `volume exceeds prior OI`;
- `confirmed ΔOI as of ...`;
- `dealer-sign assumption`;
- `stylized systematic-flow proxy`;
- `level to monitor`;
- `estimated dampening/amplifying regime`;
- `direction unknown`.

Avoid:

- “institutional accumulation” from FINRA short volume;
- “new position” from vol>OI;
- “gravitational pull” for max pain as a fact;
- “Buy now,” “Take profits,” or “What to do now” for display-tier models;
- “live” for an EOD artifact;
- precise modeled dollar flow without assumptions/ranges;
- “bullish” or “bearish” from a soft tick-rule sign alone;
- confidence/probability without calibration.

## Prioritized delivery plan

### P0 — correctness and truth

- fix Flow Leaders inflection logic and tests;
- remove Dark Pool directional/institutional claims;
- fix Market Structure build-before-render order;
- implement/remove `week_map`;
- remove unimplemented 70/30 SPX/SPY claim;
- label systematic-flow estimates as stylized proxies with ranges;
- separate Flow Desk all-universe history from ETF-only history;
- add Scanner row freshness and correct coverage/sector/distance/NaN semantics;
- remove direct trade commands from Intraday Flow;
- fix broken generated search/filter markup;
- add dataset schema validation and generation IDs;
- add freshness and quality gates that can withhold output.

**P0 acceptance:**

- no known logic bug remains in a ranked board;
- no stale row is silently ranked with current rows;
- no modeled input is presented as observed;
- no page renders a prior-generation artifact after a successful current build;
- no metric label disagrees with its calculation;
- generated HTML passes automated render/interaction smoke tests.

### P1 — information architecture consolidation

- add the four-mode Options & Positioning workspace;
- make Daily Brief the default;
- move Scanner and GEX research into shared workspace state;
- merge corrected Leaders into Brief/History;
- remove Movers, Intraday Flow, Dark Pool, and Market Structure from Options navigation;
- create separate Market Regime and Off-Exchange Activity homes;
- preserve legacy URLs with redirects after deployed-route audit;
- standardize cadence, provenance, universe, and ticker drilldown.
- implement shared SSO/entitlement and private user-state APIs; keep generated research artifacts immutable.

**P1 acceptance:**

- a user reaches any EOD options job in at most two navigation decisions;
- the selected ticker persists between Brief, Scanner, and Positioning;
- every legacy URL resolves to the intended new view;
- no live and EOD metric share an unlabeled visual;
- methodology is canonical rather than copied inconsistently.
- watchlists, saved scans, and alert definitions are owner-scoped and never leak into static/CDN output.

### P2 — workflow and research depth

- shared watchlist with Terminal;
- saved scans and exports;
- one-click next-session alerts;
- confirmed OI-change views;
- OI strike × date heatmap;
- “what changed” engine;
- wall/flip/skew history;
- OPEX and event studies;
- signal outcomes and validation;
- session archive and Terminal replay links.

**P2 acceptance:**

- scan → ticker detail → watchlist/alert is continuous;
- OI confirmation never leaks into prior-session signals;
- historical results are reproducible by generation/model version;
- every result shows sample, costs, horizon, and limitations.

### P3 — advanced subscription value

- custom EOD recipes and backtests;
- scenario/sensitivity tools;
- portfolio exposure overlay;
- options research API;
- team/shared workspaces;
- morning and close reports;
- advanced participant-capacity data if licensed;
- AI query/explanation over deterministic, cited metrics.

## Claude implementation sequence

1. **Do not edit the dirty Macro worktree blindly.** Reconcile local checkout, `origin/main`, deployed production, and existing user changes first.
2. **Create route and artifact inventory** for all eight URLs, their builders, templates, inputs, output generation, and deployment.
3. **Write failing tests** for the Flow Leaders transition, Flow Desk history basis, Screener distances/freshness, and Market Structure DAG/order issues.
4. **Fix P0 calculations and publication order.**
5. **Create one metric/provenance dictionary** shared by all Macro options templates.
6. **Normalize page data into versioned view models** rather than letting templates infer semantics.
7. **Build the four-mode workspace shell** with shared symbol/session state.
8. **Migrate Daily Brief**, then Scanner, then GEX detail, then corrected Leaders/History.
9. **Move/redirect non-options routes** only after verifying deployed traffic and bookmarks.
10. **Add shared Terminal links/watchlists/alerts.**
11. **Build confirmed OI/change/history features.**
12. **Add validation/outcome research after signal contracts exist in Terminal.**

Likely Macro touchpoints on `origin/main`:

- `templates/_navlinks.html.j2`
- `templates/gex.html.j2`
- `templates/options_screener.html.j2`
- `templates/flow_desk.html.j2`
- `templates/flow_leaders.html.j2`
- `templates/intraday_flow.html.j2`
- `templates/darkpool.html.j2`
- `templates/market_structure.html.j2`
- `scripts/build_gex_board.py`
- `scripts/build_options_screener.py`
- `scripts/build_flow_desk.py`
- `scripts/build_flow_leaders.py`
- `scripts/build_intraday_flow.py`
- `scripts/build_darkpool_desk.py`
- `scripts/build_market_structure.py`
- `engine/gex_model.py`
- `engine/flow_leaders.py`
- `engine/intraday_flow.py`
- `engine/darkpool_context.py`
- `engine/systematic_flows.py`
- `engine/options_hub.py`
- `config/dag.yml`

## Definition of done

The Macro options product is coherent when a user can:

1. open one after-close Brief and understand session, coverage, data vintage, and market changes;
2. distinguish settled facts, direction inference, and dealer/systematic models at a glance;
3. scan a fresh, stable universe with real sector, event, and liquidity context;
4. open one ticker workbench for exposure, volatility, OI, history, and assumptions;
5. see whether today’s apparent flow was confirmed by next-session OI;
6. find persistent or newly turning campaigns using correct logic;
7. save a candidate and create a next-session Terminal alert;
8. review historical outcomes without lookahead;
9. access Market Regime, Off-Exchange Activity, and Daily Movers in their correct categories;
10. move between Macro and Terminal without relearning metric names or losing context.

## What not to do

- do not merge both repositories solely because both display options;
- do not duplicate Terminal’s live tape inside a static page;
- do not keep eight URLs as eight equal products;
- do not hide stale rows behind a fresh page build timestamp;
- do not infer accumulation/distribution from FINRA daily short-volume files;
- do not label an equity reclaim scanner “intraday options flow”;
- do not preserve action commands from unvalidated models;
- do not treat vol>OI as confirmed opening;
- do not let templates calculate business logic;
- do not publish mixed artifact generations;
- do not add AI summaries before metrics and provenance are consistent;
- do not build another long page of cards as the answer to consolidation.

## Final recommendation

Macro Dashboard should not compete with Terminal for live attention. Its differentiated role is to turn the close into a trustworthy research receipt:

- what settled;
- what changed;
- what was confirmed;
- what persists;
- what tomorrow’s live desk should monitor;
- how comparable signals performed.

Make Flow Desk the concise Daily Brief, GEX the advanced Positioning & Volatility workbench, Screener the cross-sectional discovery tool, and corrected Flow Leaders the history layer. Move everything else to its proper domain.

That produces one understandable EOD options product instead of a menu full of unrelated experiments—and gives Terminal a clean source of confirmed next-session evidence without duplicating the live experience.
