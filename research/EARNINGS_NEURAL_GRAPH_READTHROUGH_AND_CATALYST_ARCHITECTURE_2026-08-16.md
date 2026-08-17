# Earnings Neural Graph, Read-Through and Catalyst Architecture

**Companion to:** `EARNINGS_INTELLIGENCE_OS_V2_SUPERINTELLIGENCE_MASTERPLAN_2026-08-16.md`  
**Status:** architecture candidate for E0 validation  
**Authority:** research and product architecture; no trading promotion  
**Purpose:** make the Chairman's peer-rerating / catch-up insight concrete enough for a frontier operator to build without collapsing it into a naive peer score

---

# 0. Core idea

An earnings event changes more than the announcing company's record.

It may reveal:

- end-market demand;
- customer budgets;
- supplier volumes;
- input costs;
- pricing power;
- inventory/channel state;
- competitive share;
- regulatory effects;
- capex cycles;
- financing and capital allocation;
- a new or fading theme.

Those facts can matter to other companies before those companies report.

The system should turn the event into a set of **mechanism-specific, evidence-backed read-through hypotheses**, join those hypotheses to the company/relationship/theme/market graph, measure whether the targets have already incorporated the information, and then grade what happens.

The intelligence loop is:

```text
source event
   -> exact facts and management claims
   -> mechanism classification
   -> economic exposure paths
   -> target peer universe
   -> market-incorporation state
   -> read-through hypotheses and falsifiers
   -> user research surface
   -> point-in-time forecast/shadow ledger
   -> target event and market outcomes
   -> learned transmission priors
```

---

# 1. Three distinct graphs must remain distinct

## 1.1 Economic relationship graph

Represents disclosed or strongly evidenced business relationships:

- customer;
- supplier;
- partner;
- competitor;
- distributor;
- licensor/licensee;
- common customer;
- common supplier;
- product/end-market exposure;
- geography;
- regulation.

This graph explains **why** information might transfer.

## 1.2 Narrative and fundamental similarity graph

Represents similarities in what companies are exposed to or discussing:

- shared products;
- shared KPIs;
- shared Q&A topics;
- shared guidance drivers;
- similar segment mix;
- similar demand/cost mechanisms;
- narrative co-acceleration;
- commitments and risks.

This graph explains **what operating information is comparable**.

## 1.3 Residual market-behavior graph

Represents current beyond-market co-movement and group lifecycle:

- residual correlations;
- newly forming groups;
- established groups;
- breadth/participation;
- strengthening/weakening;
- leader/centrality;
- price incorporation.

This graph explains **how the market is currently treating the names**.

The three graphs may join through a read-through object. They must not be flattened into one opaque edge or magic score.

---

# 2. Canonical graph objects

## 2.1 `earnings_event_fact/v2`

Required fields:

- event and company identity;
- fact concept;
- value/range/unit/currency/period/basis;
- actual/prior/consensus/prior-guidance dimensions;
- deterministic calculation receipt;
- source spans;
- available/observed/effective timestamps;
- correction state;
- validation state.

## 2.2 `earnings_mechanism_observation/v1`

One event may produce many mechanism observations.

```json
{
  "schema": "earnings_mechanism_observation/v1",
  "observation_id": "emo_...",
  "event_id": "evt_...",
  "company_id": "cik:...",
  "mechanism": "end_market_demand",
  "submechanism": "hyperscaler_ai_capex",
  "direction": "accelerating",
  "magnitude": "material",
  "time_horizon": "next_2_to_4_quarters",
  "affected_entities": [],
  "evidence_claim_ids": [],
  "management_vs_analyst_origin": "management",
  "company_specificity": 0.25,
  "industry_transferability": 0.85,
  "uncertainty": [],
  "known_at": "...",
  "authority": "context_only"
}
```

The numerical fields are transparent descriptive components or model confidence about classification—not return probabilities.

## 2.3 `relationship_edge/v2`

Required:

- source and target company/entity;
- directed relationship type;
- source span(s);
- explicit vs inferred;
- effective interval;
- magnitude when disclosed;
- certainty;
- validation state;
- expiry and supersession;
- source availability time;
- rights state.

## 2.4 `peer_exposure/v1`

A target company's exposure to one mechanism:

```json
{
  "company_id": "...",
  "mechanism": "hyperscaler_ai_capex",
  "exposure_paths": [
    {
      "path": ["target", "product", "end_market"],
      "type": "shared_end_market",
      "evidence": [],
      "directionality": "positive_if_demand_broadens",
      "specificity": 0.72
    }
  ],
  "segment_weight": null,
  "revenue_share": null,
  "basis": "relationship_and_narrative_evidence",
  "known_at": "..."
}
```

Unknown exposure weights stay null. Do not convert “named in a filing” into a fake revenue share.

## 2.5 `earnings_wave/v1`

Required:

- wave identity and ontology version;
- theme/mechanism;
- eligible company universe;
- reporting sequence;
- source event set;
- not-yet-reporting set;
- evidence accumulator;
- confirmations, contradictions and divergences;
- market incorporation state;
- lifecycle;
- current next event/falsifier;
- point-in-time timestamps.

## 2.6 `earnings_readthrough_hypothesis/v1`

Required:

- source event;
- target company/event;
- mechanism;
- predicted operating direction, not necessarily stock direction;
- evidence facts;
- relationship paths;
- narrative similarity;
- historical analogs;
- target expectations;
- market incorporation;
- target report timing;
- confidence in mechanism and evidence;
- alternative explanations;
- falsifiers;
- expiry;
- authority and promotion state.

## 2.7 `earnings_market_incorporation/v1`

Required dimensions:

- source-event return;
- target immediate abnormal return;
- target residual return versus peer/wave basket;
- target options-implied repricing;
- estimate revisions;
- volume/attention;
- news references;
- historical expected transfer interval;
- current gap versus expected transfer;
- basis and data coverage.

“Not incorporated” must be an evidence-backed state, not the absence of a price increase.

---

# 3. Mechanism ontology

The first production ontology should be small, explicit and expandable.

## 3.1 Demand

- end-market acceleration;
- end-market slowdown;
- customer budget increase/decrease;
- bookings/backlog;
- unit/volume;
- utilization;
- geographic demand;
- product adoption.

## 3.2 Pricing and margin

- pricing power;
- promotions/discounting;
- mix;
- input costs;
- freight/logistics;
- labor;
- currency;
- warranty/claims;
- supply constraints;
- productivity/cost savings.

## 3.3 Competitive structure

- share gain/loss;
- competitor exit/entry;
- product superiority/shortfall;
- customer wins/losses;
- capacity expansion;
- consolidation.

## 3.4 Capital and financing

- capex increase/decrease;
- buyback/dividend;
- debt/refinancing;
- liquidity;
- dilution;
- M&A;
- strategic investment.

## 3.5 Regulatory and policy

- tariffs;
- reimbursement;
- procurement;
- export controls;
- tax;
- environmental rules;
- approval/licensing.

## 3.6 Company-specific/nontransferable

- one-off accounting;
- litigation settlement;
- restructuring;
- isolated execution failure;
- tax item;
- company-specific acquisition integration;
- idiosyncratic outage.

Classification into a company-specific mechanism should sharply reduce peer-transfer priority.

---

# 4. Read-through candidate generation

## 4.1 Step 1 — Event materiality

Admit only source facts or claims that clear materiality rules:

- meaningful actual/consensus/prior-guide delta;
- explicit guidance change;
- material segment/KPI change;
- repeated analyst pressure;
- major commitment change;
- explicit relationship or customer statement;
- new theme/topic evidence;
- significant market reaction.

## 4.2 Step 2 — Mechanism extraction

For each admitted fact, identify:

- operating driver;
- company-specific versus transferable share;
- direction;
- duration;
- affected product/end market/geography/entity;
- management certainty;
- source and exact evidence.

## 4.3 Step 3 — Target universe

Generate targets from the union of:

- same subindustry;
- curated peer set;
- customer/supplier/partner/competitor graph;
- common customer or supplier;
- product/end-market exposure;
- narrative/topic similarity;
- current residual co-movement group;
- Mastermind theme/subtheme membership;
- historical event transmission neighbors.

Record which generator admitted each target. Do not let semantic similarity alone assert an economic relationship.

## 4.4 Step 4 — Directional mechanism logic

Examples:

### Broad demand acceleration

- same end-market producers: positive operating read-through;
- suppliers: positive only if product/category exposure is relevant;
- customers: ambiguous; strong downstream demand may imply healthy volumes or higher input prices;
- competitors: positive industry transfer unless source event states share capture.

### Share gain

- announcer: positive;
- directly named losing competitor: negative candidate;
- suppliers to announcer: potentially positive;
- broad industry: weak/ambiguous.

### Input cost increase

- upstream providers: potentially positive;
- downstream users: negative margin read-through, conditioned on pricing power;
- peers with hedges or different sourcing: weak.

### Inventory correction

- suppliers: negative near-term;
- customers downstream: could be positive if destocking ends;
- competitors: depends on channel and share.

### Capex acceleration

- named equipment/component providers: positive candidate;
- power/cooling/infrastructure ecosystem: mechanism-specific positive candidate;
- cash-flow-sensitive source company: possible negative internal effect;
- competitors: positive demand or negative competitive-spend pressure.

## 4.5 Step 5 — Target expectations

Attach decision-time:

- consensus level and revision momentum;
- prior guidance;
- dispersion;
- recent peer evidence;
- valuation/expectation proxies only where approved;
- report date and time;
- Stage/Prophet state for context;
- options implied move.

The same operating read-through has different stock implications when expectations differ.

## 4.6 Step 6 — Market incorporation

Compare target movement with:

- source event;
- exposure-weighted peer basket;
- historical pair/wave transfer;
- market/sector residual;
- estimate and option changes.

Classify:

- incorporated;
- partially incorporated;
- potentially under-incorporated;
- overreacted;
- divergent for a known reason;
- unknowable/insufficient coverage.

## 4.7 Step 7 — Research-priority ranking

The system may rank research attention using transparent components:

```text
priority =
  evidence_quality
× mechanism_transferability
× target_exposure
× target_expectation_sensitivity
× event_timing_relevance
× incorporation_gap
× historical_support
× freshness
```

Expose every component and the reasons. Label it “research priority,” never “probability of gain.”

---

# 5. Historical transmission learning

## 5.1 Pair-level history

For a source-target pair and mechanism:

- immediate target reaction;
- delayed H1/H5/H10/H21 reaction;
- estimate revisions;
- target event surprise;
- target guidance confirmation;
- direction agreement;
- regime and sector context;
- source/target reporting order;
- source data coverage.

## 5.2 Wave-level history

Measure:

- first-announcer information transfer;
- confirmation premium as more peers report in same direction;
- divergence frequency;
- early versus late reporter effects;
- market incorporation speed;
- performance of “unreported target” cohorts;
- false-positive mechanisms.

## 5.3 Mechanism priors

Learn separately for:

- industry demand;
- customer demand;
- supplier input costs;
- pricing;
- share gain;
- regulation;
- capex;
- inventory;
- company-specific execution.

Do not pool all read-through events.

## 5.4 Point-in-time requirements

Historical replay uses only:

- relationships known then;
- source documents available then;
- consensus vintage then;
- schedule known then;
- market data through the decision timestamp;
- graph version then.

Later relationship discoveries may improve present research but cannot be backfilled into a historical forecast as if known.

---

# 6. Four forecast families

## 6.1 Fundamental surprise model

Inputs:

- decision-time consensus and dispersion;
- revision momentum;
- prior guidance;
- company trend;
- peer-wave facts;
- customer/supplier mechanisms;
- alternative data with clean PIT provenance;
- seasonality and reporting history.

Outputs:

- EPS/revenue/guidance distributions;
- important KPI/segment expectations;
- missing-data state;
- calibrated uncertainty.

## 6.2 Event-reaction model

Inputs:

- fundamental surprise distribution;
- expectations management;
- valuation/positioning where clean;
- implied move/skew;
- pre-event price/volume;
- prior company reaction function;
- market regime;
- source timing.

Outputs:

- direction distribution;
- move-size distribution;
- probability of exceeding implied move;
- tail-risk estimates.

## 6.3 Post-event drift model

Inputs:

- event facts;
- realized first reaction;
- guidance and Q&A;
- estimate revisions;
- price incorporation;
- liquidity/attention;
- peer confirmations;
- setup survival.

Outputs:

- H5/H10/H21 distributions;
- continuation/reversal;
- risk bands.

## 6.4 Peer read-through model

Inputs:

- mechanism observation;
- relationship/exposure paths;
- target expectations;
- current incorporation;
- reporting-wave state;
- historical transfer priors;
- target's later report date.

Outputs:

- operating confirmation probability;
- expected direction of target fundamental revision;
- target event surprise distribution;
- target immediate/delayed market response distributions.

This model must be promoted separately from the source-company Catalyst models.

---

# 7. Product surfaces

## 7.1 Event “Who else does this matter to?” module

For each material event fact, show:

- affected companies;
- relationship/mechanism;
- direction: positive/negative/mixed;
- target report date;
- current incorporation;
- evidence path;
- next falsifier;
- saved-monitor action.

## 7.2 Peer catch-up board

Columns:

- target company;
- source event;
- mechanism;
- exposure evidence;
- report timing;
- price/estimate incorporation;
- confirmation count;
- contradictions;
- research-priority components;
- source links.

No opaque total score in the first viewport.

## 7.3 Earnings wave graph

Visual grammar:

- company nodes ordered by report time;
- source events lit as they occur;
- edges colored by mechanism direction, not stock recommendation;
- evidence count and quality;
- market incorporation ring;
- target outcome after reporting;
- lifecycle state;
- filters by relationship type, theme and confidence.

## 7.4 Theme/group integration

For an active theme:

- constituent report coverage;
- accumulated earnings evidence;
- narrative breadth;
- Q&A breadth;
- relationship-supported members;
- residual market participation;
- leaders/laggards in incorporation;
- next reporting catalysts;
- falsifiers.

Earnings evidence becomes one leg in Thematic Intelligence; it does not replace theme lifecycle authority.

---

# 8. Worked example — data-center power/cooling wave

This example is illustrative and must be replaced by real E0 golden data.

## Source event

An early reporter states:

- hyperscaler demand accelerated;
- orders/backlog rose materially;
- data-center power availability remains a constraint;
- capex and capacity are being raised;
- margins are pressured by a component bottleneck.

## Mechanism observations

1. `hyperscaler_ai_capex`: accelerating, broad, 2–4 quarter horizon.
2. `data_center_power_constraint`: intensifying.
3. `component_supply_constraint`: company and ecosystem effect.
4. `capacity_expansion`: positive demand evidence, negative near-term cash/margin possibility.

## Candidate target sets

- direct disclosed suppliers;
- direct disclosed customers;
- cooling/power peers;
- common hyperscaler-exposure companies;
- active residual data-center infrastructure group;
- companies with repeated data-center Q&A topics;
- companies in a curated AI infrastructure theme.

## Direction logic

- broad demand can support peers;
- share-gain language can hurt direct competitors;
- power constraints can benefit infrastructure providers but limit compute deployment;
- component bottlenecks can hurt firms without alternate supply;
- price increases can help suppliers and hurt unhedged buyers.

## Incorporation

A target that rose in sympathy and received estimate revisions may already be incorporated. A target that did not move but has a strong disclosed relationship and an upcoming report may become a high research-priority case. Another target may not move because its exposure is too small; the system must preserve that alternative.

## Grading

When targets report, grade:

- whether the same mechanism appeared;
- whether fundamentals confirmed;
- whether estimates moved beforehand;
- whether the stock caught up before or at report;
- whether the relationship edge was useful;
- which evidence component contributed.

---

# 9. Validation and promotion

## 9.1 Graph quality

- relationship precision and recall on a reviewed corpus;
- entity-resolution accuracy;
- receipt-open success;
- expired-edge handling;
- correction replay;
- false relation assertions;
- share-class deduplication.

## 9.2 Read-through research quality

- mechanism classification accuracy;
- target-set precision;
- sign agreement for operating outcomes;
- market incorporation classification;
- confirmation/falsification rate;
- performance versus simple industry peers;
- performance versus economic-link-only and narrative-only baselines;
- coverage and abstention.

## 9.3 Forecast quality

- calibration;
- proper scoring rules;
- ranking metrics;
- tail-risk accuracy;
- era/sector stability;
- data-availability cohorts;
- transaction-cost realism;
- pre-registered promotion gates.

## 9.4 User quality

- time to identify affected peers;
- evidence-open success;
- analyst agreement on mechanism;
- saved-monitor use;
- follow-through into target research;
- false-confidence reports.

---

# 10. Build boundaries

Do not build this as one graph database first.

The first vertical slice should use versioned, content-addressed event/relationship/read-through objects and only introduce a dedicated graph serving layer when query patterns and scale justify it.

Do not build this as one LLM prompt.

The model proposes structured mechanisms and entities; deterministic and statistical layers resolve identity, calculations, time, evidence and outcomes.

Do not make read-through a Prophet shortcut.

Product and research value may ship immediately. Directional authority requires the full learning path.

Do not duplicate Jodie.

Consume existing Group Reads, theme and price-pressure systems through explicit adapters. Earnings owns event-derived evidence and read-through hypotheses; Group Reads owns participation; TIL owns theme lifecycle; Prophet owns decisions.

---

# 11. First implementation sequence after E0

1. Freeze mechanism ontology and exact graph contracts for one golden wave.
2. Bind one real source event to deterministic facts and exact claims.
3. Resolve a high-precision target universe from existing identity/relationship/theme data.
4. Materialize read-through hypotheses with explicit alternatives and falsifiers.
5. Display them in the event workspace with no predictive authority.
6. Accrue market incorporation and target event outcomes point in time.
7. Evaluate simple transparent baselines.
8. Only then add learned ranking or forecasts.

This sequence converts the Chairman's idea into a useful product early while preserving the path to a genuine moat.