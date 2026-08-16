#### 1. Catalyst Radar

The default landing surface.

- upcoming catalysts by date;
- date confidence and source state;
- asset, indication, phase, event class;
- materiality to issuer;
- proximity;
- historical revisions;
- event-window implied move;
- price/volume/relative-strength context;
- watch, alert, export.

#### 2. Market Pulse

- premarket, session, and after-hours biotech movers;
- XBI/IBB/XLV and subsector regime;
- gainers/losers;
- unusual volume;
- residual returns;
- options and dark-pool anticipation;
- catalyst-linked moves;
- heatmap and scatter views.

#### 3. Explorer

- companies;
- assets;
- indications;
- trials;
- regulatory events;
- medical devices;
- cash/runway;
- ownership;
- screens and saved cohorts.

#### 4. Dossiers

Separate but linked pages for:

- company/security;
- asset;
- asset × indication;
- trial;
- regulatory submission/event;
- financing;
- catalyst.

Each dossier should carry an Evidence Thread and point-in-time selector.

#### 5. Change and First-Seen Intelligence

Preserve the strongest current differentiator:

- exact registry changes;
- first-seen facts;
- correction lineage;
- temporal braid;
- source receipts;
- alert rules;
- impact triage.

#### 6. Research and Models

- PoS;
- timing;
- market-response;
- financing survival;
- options-implied vs historical move;
- matched-cohort studies;
- score decomposition;
- forward track records;
- killed and rejected models.

#### 7. Watches, Alerts, Portfolio, and API

- saved companies/assets/trials;
- event alerts;
- change alerts;
- unusual flow;
- financing and ownership alerts;
- portfolio exposure;
- exports;
- API keys and documentation.

### 9.2 Operator-only surface

Do not force data review and source incidents into customer pages.

Create an operator console for:

- source health;
- generation health;
- unresolved identities;
- date conflicts;
- duplicate assets;
- sponsor mappings;
- correction queues;
- model clock status;
- rights and redistribution states;
- data-coverage denominators.

---

## 10. Canonical data architecture

The BioCatalyst lobe should be one domain graph with multiple read models, not a collection of page-specific JSON files.

### 10.1 Preserve the existing temporal and provenance substrate

Keep:

- source registry;
- raw immutable objects;
- current projection;
- historical versions;
- correction lineage;
- first-seen ledger;
- transaction and source clocks;
- generation pointer;
- content hashes;
- R2 receipts;
- fail-closed contract validation;
- forward outcome store.

### 10.2 Build the missing temporal knowledge graph

#### Core nodes

- issuer;
- security;
- company;
- sponsor;
- subsidiary;
- asset/drug/device;
- target/mechanism;
- modality;
- indication;
- trial;
- endpoint;
- trial site;
- regulatory application;
- regulator event;
- label;
- safety event;
- patent/exclusivity;
- licensing/partnership event;
- financing instrument;
- financing event;
- ownership position;
- analyst estimate;
- catalyst;
- market observation;
- options snapshot;
- flow observation;
- research forecast;
- realized outcome.

#### Every fact or edge carries

- effective time;
- known-at time;
- retrieved-at time;
- source ID;
- source record ID;
- exact locator;
- original value;
- normalized value;
- correction lineage;
- review state;
- identity confidence;
- coverage state;
- rights/redistribution disposition;
- authority tier.

### 10.3 Entity resolution must become a first-class service

The current reviewed sponsor map is a useful seed, not a complete solution.

Use a layered resolver:

1. exact source-native IDs;
2. exact reviewed aliases;
3. corporate parent/subsidiary records;
4. SEC identifiers and security-master links;
5. asset ownership and licensing timeline;
6. model-generated candidates;
7. human review for ambiguous or high-impact joins.

A model may propose. It may not silently promote an ambiguous relationship.

Historical ownership matters. An asset can change owners, a company can merge, and a sponsor can be a subsidiary. Every relationship needs a valid-time interval.

### 10.4 One source adapter per authority

Do not create duplicate collectors for data already owned elsewhere.

- ClinicalTrials.gov and record history: BioCatalyst-owned.
- FDA/openFDA/Drugs@FDA: one regulatory adapter and rights disposition.
- SEC filings and capital structure: read the Capital Structure/SEC owner’s PIT contracts.
- prices, quotes, and historical bars: read canonical Massive/Polygon/Macro stores.
- intraday options flow and dark pool: read Terminal-owned contracts and R2 archives.
- EOD options/GEX: read the existing options estate.
- analyst estimates: licensed source only, with vintage support.
- news/transcripts: read existing corporate-document and transcript owners.
- ownership/insider/13F: read the existing ownership plane when its temporal contract is complete.

---

## 11. The BioCatalyst alpha lobe

The lobe should answer a narrower and more useful question than “is this biotech good?”

> **Among investable names already eligible for consideration, where is the combination of information, catalyst, payoff, financing survival, positioning, and price action most asymmetric relative to what appears priced?**

It should not collapse this into one opaque score at the beginning.

### 11.1 Four layers

#### Layer A: Evidence eligibility

Before scoring anything, decide whether the observation is lawful and usable.

Inputs:

- identity confidence;
- source authority;
- point-in-time availability;
- freshness;
- completeness;
- date precision;
- contradiction state;
- correction state;
- rights state;
- coverage denominator.

Outputs:

- eligible;
- partial;
- abstain;
- reject;
- reason codes.

Missing is not zero. Ambiguous identity is not weak evidence. It is no ticker-level evidence.

#### Layer B: Catalyst intelligence

Estimate the event, not the stock.

- event class;
- phase and endpoint;
- event certainty;
- date distribution;
- probability of delay;
- probability of positive clinical/regulatory outcome;
- asset and indication importance;
- competitive context;
- unmet need;
- regulatory precedent;
- trial design quality;
- enrollment and site trajectory;
- endpoint changes;
- revision direction;
- sponsor behavior;
- source contradiction.

#### Layer C: Economic asymmetry and mispricing

Estimate what the event means to the security.

- asset contribution to enterprise value;
- addressable market and economics;
- ownership percentage;
- royalties/milestones;
- cash runway through catalyst;
- financing need;
- ATM/shelf/convert/warrant overhang;
- expected dilution;
- downside survival;
- upside and downside scenario returns;
- historical matched-event response;
- options-implied move;
- cross-sectional market-implied expectations;
- borrow/short/ownership crowding;
- liquidity and expected slippage.

#### Layer D: Timing and entry state

Estimate whether now is an attractive entry.

- days to catalyst distribution;
- washout depth;
- residual price dislocation;
- curvature and acceleration;
- reclaim/turn confirmation;
- volume and liquidity;
- subsector breadth;
- idiosyncratic versus sector return;
- options-flow persistence;
- dark-pool accumulation;
- IV term structure;
- extension and chase risk;
- post-event or pre-event regime.

---

## 12. A scenario engine, not a magical composite

For each candidate, produce a distribution and decomposition.

### 12.1 Core scenario variables

- `P(event occurs in window)`
- `P(positive outcome | event)`
- `P(delay or cancellation)`
- `return_positive`
- `return_negative`
- `return_delay`
- `financing/dilution drag`
- `liquidity/slippage drag`
- `model uncertainty`
- `source uncertainty`

A basic research object can compute:

\[
EV = p_{positive}R_{positive} + p_{negative}R_{negative} + p_{delay}R_{delay}
     - D_{financing} - C_{liquidity}
\]

This should not be published as a precise expected return until calibration earns that interpretation. Early outputs should be:

- scenario table;
- expected-utility rank;
- uncertainty interval;
- evidence quality;
- family-level contributions;
- abstention reasons.

### 12.2 Separate opportunity from confidence

A stock can have:

- enormous opportunity with weak evidence;
- modest opportunity with strong evidence;
- strong catalyst but fatal financing risk;
- attractive event odds already fully priced;
- terrible recent price action caused entirely by sector beta;
- apparent bullish options flow that is actually hedging.

Publish at least:

- opportunity magnitude;
- evidence confidence;
- timing readiness;
- downside survivability;
- crowding;
- freshness.

Do not let a high opportunity estimate conceal low confidence.

### 12.3 Define dislocation explicitly

Use several independent dislocation measures:

1. **price residual dislocation**  
   Ticker return minus market, sector, subsector, and style expectation.

2. **event-implied dislocation**  
   Model or matched-cohort event distribution versus options-implied move and skew.

3. **fundamental-value dislocation**  
   Scenario asset value versus enterprise value, after financing and ownership.

4. **information dislocation**  
   Newly observed or revised facts whose expected market relevance is not reflected in price/volume/IV response.

5. **positioning dislocation**  
   Accumulation, shorting, options, or ownership state inconsistent with public narrative and price.

6. **time dislocation**  
   Catalyst proximity is increasing while attention or implied volatility remains unusually low, or a washout is recovering before the event window.

Each should have its own evidence and failure state.

---

## 13. Price, sector, and subsector decomposition

The user’s sector-beta concern is correct. XLV alone is too broad.

### 13.1 Regime hierarchy

Use:

- broad market;
- healthcare;
- biotech;
- large-cap biotech;
- small/mid-cap biotech;
- medtech;
- life-science tools;
- managed care;
- pharma;
- thematic baskets such as oncology, immunology, rare disease, obesity/metabolic, neurology, gene therapy, cell therapy, RNA, vaccines, diagnostics.

### 13.2 Residual return model

For each ticker and horizon, estimate the expected move from:

- market beta;
- healthcare beta;
- biotech beta;
- subsector/theme beta;
- size and liquidity;
- volatility regime.

The residual is the first measure of idiosyncratic movement.

This allows the lobe to distinguish:

- “everything in XBI is rising”;
- “this theme is rerating”;
- “this ticker is moving before peers”;
- “this ticker is lagging despite a bullish sector”;
- “the stock washed out idiosyncratically and is beginning to mean-revert.”

### 13.3 Washout and turn model

A useful pre-catalyst setup should require more than a low price.

Candidate features:

- residual drawdown percentile;
- distance from peak and event-adjusted prior;
- selling-volume exhaustion;
- realized-volatility compression after capitulation;
- slope change;
- second derivative/curvature;
- reclaim of short and medium reference levels;
- relative-strength turn versus subsector;
- breadth improvement;
- gap/failure recovery;
- liquidity and spread normalization.

The model should separate:

- falling knife;
- dead bounce;
- sector beta rebound;
- idiosyncratic rerating;
- catalyst anticipation.

---

## 14. Options, dark pool, and intraday flow integration

The options estate already exists. BioCatalyst should consume it through contracts, not rebuild it.

### 14.1 EOD options features

For every catalyst-bearing ticker:

- options availability and liquidity;
- nearest liquid expiries before and after the event;
- implied move;
- event-window term-structure kink;
- front/back IV spread;
- call/put skew;
- downside skew;
- IV percentile;
- open-interest concentration;
- gamma concentration;
- dealer regime;
- expected IV crush;
- realized versus implied event-move history;
- spread and execution quality.

### 14.2 Intraday anticipation features

From Terminal:

