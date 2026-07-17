# Options Confluence Intelligence Engine

## Codex audit and build handoff for Fable

Date: 2026-07-16  
Status: research and architecture brief; no directional-alpha claim  
Adjudicated 2026-07-16 by Fable — see OPTIONS_CONFLUENCE_PROGRAM_BY_FABLE.md (program of record; §2 adjudication table) and FLOW_ORIGINATION_SANDBOX_BY_FABLE.md (operator-ratified origination experiment).
Scope: Mastermind Terminal, Macro Dashboard options infrastructure, and an eventual multi-horizon stock-opportunity engine

---

## 1. Purpose

This document converts the MSFT / QuantData case study into an actionable research and engineering program.

The objective is not to reproduce another vendor dashboard. The objective is to build a point-in-time, replayable system that can determine whether options information adds incremental value to:

- intraday and very-short-term stock forecasts;
- swing and medium-term stock selection;
- volatility, strike-touch, breakout, pin, and path forecasts;
- trade-expression selection after spreads, IV, liquidity, and risk;
- an explicit abstain decision when evidence is weak or contradictory.

The immediate conclusion is:

> Mastermind already owns enough observable data to reproduce most of the QuantData-style MSFT analysis. The missing moat is durable point-in-time persistence, horizon alignment, outcome calibration, and disciplined evidence handling.

No new broad options-data dashboard is required for version 1.

---

## 2. Executive audit verdict

### What we can already reproduce

Using the existing deep options store, Codex independently reconstructed:

- MSFT constant-maturity 30-day IV of approximately 45.75% on 2026-07-14;
- a 252-session IV Rank of approximately 99.6 to 100, depending on the exact interpolation and ranking convention;
- the 2026-07-17 $400 strike as the dominant positive conventional-GEX concentration;
- approximately 35,979 contracts of combined call and put open interest at that strike in the replicated chain;
- a separate current live-flow observation of approximately $2.63M in MSFT 2026-07-17 $400 calls with volume above prior open interest.

For one explicit unit convention, the reconstructed $400 exposure was approximately:

- $11.62M of option-induced dollar-delta change per $1 underlying move;
- $44.73M per 1% MSFT move.

Other internal and vendor outputs report different dollar magnitudes because their unit, spot timestamp, contract population, Greek source, and scaling conventions differ. The dominant-strike result agrees. This discrepancy is itself evidence that a versioned measurement contract is mandatory.

### What this proves

It proves measurement capability.

### What it does not prove

It does not prove that:

- the call flow was opening;
- the trade was an outright bullish bet;
- dealers were the counterparty;
- the $400 GEX concentration caused price to rise;
- IV Rank 100 was bullish;
- the combined setup has repeatable after-cost predictive value.

The system is presently a strong analytics foundation, not a validated stock-picking engine.

---

## 3. What QuantData appears to have calculated

### 3.1 Net Drift

The documented method is cumulative signed option premium:

    trade premium = option price × contracts × contract multiplier

Each print is classified from its location relative to the prevailing bid and ask:

- at or above ask: inferred buyer-initiated;
- at or below bid: inferred seller-initiated;
- inside the spread or near midpoint: uncertain;
- complex trades can be filtered because a visible leg may not be directional.

Calls inferred bought add to bullish call drift. Calls inferred sold subtract. Put signs require explicit convention; a put inferred sold is normally bullish evidence while a put inferred bought is bearish evidence.

This is a useful observation layer. It is not direct knowledge of trade intent.

### 3.2 IV Rank

QuantData documents:

    IV Rank = 100 × (current IV - trailing minimum IV)
                    / (trailing maximum IV - trailing minimum IV)

A nominal 30-day maturity request uses a broad maturity band around 30 days. Therefore it should not be treated as a perfectly constant 30-day series unless we independently construct one by interpolating total variance across adjacent expiries.

IV Rank measures the location of current IV inside its historical range. It does not measure:

- direction;
- expected percentage return;
- whether a stock will rise;
- whether long options are attractive;
- whether the absolute implied move is unusually large.

Expected move should be estimated from the ATM straddle and/or a constant-maturity IV calculation.

### 3.3 GEX, DEX, Vanna, and Charm

These are chain positions multiplied by Greeks and aggregated by strike or expiry under a position-sign convention.

The conventional call-positive / put-negative GEX proxy is useful for describing option-position topology. It is not measured all-market dealer inventory.

Required interpretation:

- if dealers are truly long gamma, hedging generally sells rallies and buys dips;
- this can damp volatility, create mean reversion, or encourage pinning;
- if dealers are truly short gamma, hedging can amplify a rising or falling move;
- a static DEX level describes an estimated position and hedge inventory, not necessarily future stock demand;
- Vanna and Charm require an IV path and time path before they imply hedge changes.

Therefore:

> Positive GEX at $400 does not mean that GEX pushes MSFT upward to $400.

The strike could act as a pin, magnet, resistance, volatility damper, or irrelevant level depending on dealer sign, distance, time to expiry, stock liquidity, implied volatility, and catalysts.

### 3.4 Price confirmation

The final component was ordinary stock confirmation:

- rising price;
- relative strength versus peers;
- volume;
- proximity to the highlighted strike;
- subsequent breakout.

The critical research question is whether options evidence led the residual stock move or merely chased a move already underway.

---

## 4. Forensic problems in the MSFT example

The screenshots do not demonstrate one perfectly aligned confluence.

- Net Drift appears to include multiple or all expiries.
- The GEX / DEX / Vanna panels are explicitly filtered to 2026-07-17.
- The IV Rank panel uses a roughly 30-day maturity population.
- MSFT earnings were scheduled for 2026-07-29, after the July 17 contracts expired.
- The IV Rank screenshot appears to have been captured at a later MSFT price than the initial flow and exposure screenshots.

Consequences:

- the displayed call premium is not proven to be concentrated in the July 17 $400 calls;
- the July 17 exposure did not include the earnings event;
- IV Rank may partly reflect an earnings-containing maturity population that is different from the GEX population;
- later evidence must not be permitted to leak into the timestamp of the initial alert;
- several panels may be related transformations of the same underlying option activity and cannot be counted as independent confirmations.

The correct research object is a pre-timestamped candidate setup, not a successful chart selected after the outcome.

---

## 5. Current Mastermind capability map

| Capability | Audit status | Notes |
|---|---|---|
| Historical contract OHLCV | Strong | Deep ThetaData store, roughly 380 roots, history beginning in 2012 |
| Historical open interest | Strong | Point-in-time timing law exists |
| Historical IV and Greeks | Strong | Delta, gamma, vanna, charm, vomma and higher orders are available |
| Live option trades plus prevailing NBBO | Available | ThetaData trade_quote endpoint |
| Live signed premium and contract events | Implemented | Direction is correctly labelled soft |
| GEX / DEX / Vanna / Charm maps | Implemented | Strike and expiry maps, walls and gamma flip |
| IV term, smile, IV30 and IV rank | Implemented in newer hub paths | Older entry-state path still structurally nulls IV Rank |
| Sweep, repeat, vol-above-OI heuristics | Implemented | True parent-order and multi-leg reconstruction is absent |
| Cross-sectional scanner | Display-stage | No validated buy ranking |
| Flow-led confluence board | Present but weakly populated | Missing price/context legs and baseline history |
| Signal harvesting and outcome grading | Scaffolded | No durable populated ledger and grade history found |
| Durable historical per-trade replay | Major gap | Current tape process aggregates then discards raw rows |
| Actual dealer/customer inventory | Unavailable | Not observable from consolidated OPRA |

### Key source locations

- collectors/thetadata.py
  - measured EOD, OI, EOD-Greeks, and trade_quote endpoints;
  - full Greek and trade-plus-quote schemas;
  - OI publication timing;
  - measured history beginning 2012-06-01.

- engine/thetadata_store.py
  - point-in-time chain construction and OI joins.

- engine/tape_flow.py
  - quote-signed daily flow;
  - aggregate-then-discard behavior;
  - same-day OI lookahead prohibition;
  - DTE, moneyness, delta-notional, and trailing-baseline features.

- engine/live_flow.py
  - live soft-side classification;
  - contract event aggregation;
  - current tide and ticker views;
  - moneyness currently approximated from prior-session close.

- engine/gex_engine.py
  - explicit declaration that GEX is a volatility-regime and levels map, not alpha;
  - dealer-sign assumption and display-only passport.

- engine/options_hub.py
  - IV Rank, term/smile, IV30, and options-hub Greek topology.

- engine/options_entry_state.py
  - older structurally-null IV Rank path requiring integration repair.

- engine/flow_enrich.py
  - current heuristic flow quality score and event enrichment.

- engine/options_matrix.py
  - strike-by-expiry exposure matrix and heat-seeker logic.

- engine/flow_leaders.py
  - existing confluence legs and fire rules.

- collectors/flow_signals.py
  - intended signal-ledger harvester.

- engine/flow_signals_grade.py
  - intended forward outcome grader.

- scripts/research/options_history_gauntlet.py
  - existing historical validation discipline.

- research/OPTIONS_OPEX_VANNA_CHARM_FINDINGS.md
  - evidence that Greek state is more reliable for volatility and path shape than standalone direction.

- /Users/chriswong/Documents/Cluade/charting-app/ingest/collect_options.py
  - lightweight daily ATM IV, term, and smile collector.

- /Users/chriswong/Documents/Cluade/charting-app/terminal/app/api/flow/route.ts
  - terminal consumer/router with backend and R2 fallback.

### Architectural boundary

The charting app should remain primarily a client and presentation surface.

The canonical analytics, point-in-time feature store, replay engine, models, and alert ledger should live in Macro Dashboard or a dedicated shared analytics service. Reimplementing core logic in the frontend would create irreconcilable formula and timestamp drift.

---

## 6. Critical operational and research gaps

### 6.1 Live ingestion is not yet truly incremental

The live poller targets a short cycle but has been observed taking much longer because it repeatedly requests the full trading day and falls back to expiry-level requests.

Required:

- sequence-aware incremental polling;
- cursor or last-sequence persistence;
- duplicate suppression;
- cancellation and correction handling;
- latency and missing-event telemetry;
- immutable batch identifiers.

### 6.2 Historical live tape is not durably replayable

engine/tape_flow.py explicitly aggregates and discards raw trade rows.

Recommended tiered retention:

- permanent daily contract aggregates for the full universe;
- permanent minute-by-contract aggregates for the research universe;
- permanent exact signal snapshots and all contributing records;
- a rolling hot raw-tape window;
- permanent raw windows around alerts, market shocks, earnings, and sampled controls.

This controls storage cost without sacrificing falsifiability.

### 6.3 Trade direction remains probabilistic

Quote signing should always carry:

- inferred side;
- side confidence;
- source;
- prevailing quote age;
- spread width;
- condition-code quality;
- whether the trade is at ask, above ask, midpoint, bid, or below bid;
- possible multi-leg or stock-tied status.

User-facing language must remain approximately buy / approximately sell until stronger ground truth exists.

### 6.4 Opening versus closing is unknown in real time

Do not treat volume above OI as proof of opening demand.

Estimate an opening probability from:

- volume relative to prior OI;
- contract age;
- repeated same-side flow;
- trade conditions;
- spread reconstruction;
- next-day change in OI;
- historical behavior of similar contracts.

Next-day OI should confirm or falsify the earlier inference. It cannot be used at the earlier timestamp.

### 6.5 Dealer positioning is scenario-dependent

Maintain three distinct representations:

1. Legacy OI-based conventional exposure.
2. Intraday flow-implied incremental dealer inventory.
3. Lower, central, and upper scenario bands under alternative sign and opening assumptions.

Never collapse these into one authoritative dealer-position number.

### 6.6 Store and builder resolution is fragmented

Some builders find the deep operations store automatically; others require THETADATA_STORE and can silently operate against an empty local path.

Required:

- one canonical store resolver;
- one data catalog;
- explicit failure when required history is absent;
- no silent fallback to structurally-null output;
- source lineage on every published artifact.

### 6.7 No closed learning loop

The repository contains ledger and grader scaffolding, but no durable populated alert-and-outcome history was found.

Without that ledger, the system cannot answer the central question:

> Historically, did extreme call flow plus this volatility state plus this strike topology predict residual stock returns, strike touches, realized volatility, or executable option profits?

---

## 7. Target system: multiple forecasts, not one confluence score

For every ticker, timestamp, and horizon, the engine should produce:

- D: calibrated directional return distribution;
- M: probability of a move large enough to matter or clear a specified breakeven;
- V: realized-volatility and IV-change forecasts;
- P: path, breakout, strike-touch, and pin probabilities;
- Q: data-quality, classification, and regime confidence;
- U: after-cost expected utility for each permitted trade expression.

The permitted final action is:

- stock;
- call or put;
- debit spread;
- defined-risk volatility structure;
- no trade.

The stock forecast must be generated before the instrument is selected.

Example:

- bullish stock forecast plus extremely expensive IV may favor shares or a call spread;
- bullish stock forecast plus underpriced convexity may favor calls;
- large-move forecast with weak direction may favor a volatility structure;
- high pin probability plus overpriced IV may support only defined-risk short-volatility research;
- low confidence or disagreement should produce abstention.

---

## 8. Point-in-time architecture

    Options trades + prevailing NBBO ─┐
    OI + Greeks + IV surface ─────────┤
    Stock + sector + market data ─────┼─> point-in-time event store
    Events + fundamentals ────────────┘
                                           |
                                           v
                               independent evidence families
                                           |
                  ┌────────────────────────┼────────────────────────┐
                  v                        v                        v
          intraday model             swing model          medium/long model
                  └────────────────────────┼────────────────────────┘
                                           v
                                  D / M / V / P / Q
                                           |
                                           v
                            trade-expression optimizer
                                           |
                                           v
                             immutable alert and outcome ledger

Every output must carry:

- event timestamp;
- information cutoff;
- source and source timestamp;
- formula version;
- model version;
- latency;
- quality flags;
- feature snapshot identifier;
- horizon;
- event context;
- expected signal half-life.

---

## 9. Evidence families

### 9.1 Observed option flow

Core features:

- quote-confidence-weighted signed premium;
- signed contract volume;
- signed share-equivalent delta flow;
- dollar-delta flow;
- gamma-, vega-, and theta-weighted flow;
- call/put and bullish/bearish decomposition;
- DTE and moneyness buckets;
- repeated prints;
- sweep and exchange-dispersion heuristics;
- block size;
- burst, persistence, acceleration, reversal, and change-point features;
- volume relative to prior OI;
- premium and delta flow relative to option ADV;
- flow relative to underlying dollar volume;
- spread width and quote age;
- condition-code and complex-trade quality;
- event-containing versus non-event expiry.

A preferred directional feature is confidence-weighted option-induced stock flow:

    OIS shares =
        sum(
            expected aggressor sign
            × probability trade is opening
            × contracts
            × multiplier
            × option delta
        )

Normalize it within:

- ticker;
- time of day;
- liquidity bucket;
- expiry bucket;
- moneyness bucket;
- market regime.

Raw premium must not be the principal feature because a rising stock mechanically increases the dollar value of later call transactions.

### 9.2 Flow lead-versus-chase

Create a lead/chase score.

Questions:

- Did option flow arrive before residual stock momentum?
- Did the stock move first and calls follow?
- Was there common news that moved both?
- Did flow appear while the stock remained flat or down?
- Did the stock subsequently confirm?

Use strictly lagged flow in prediction tests and control for:

- prior stock return;
- underlying volume;
- sector and market return;
- volatility;
- news timestamp;
- time of day.

### 9.3 Positioning and hedging topology

Features:

- GEX, DEX, Vanna, and Charm by strike and expiry;
- gamma flip or zero-gamma estimate;
- call wall and put wall;
- concentration at each strike;
- asymmetry above versus below spot;
- exposure gradient near spot;
- expiry concentration;
- front-week versus later-expiry disagreement;
- state-revaluation versus inferred new-inventory decomposition;
- hedge-demand scenario for spot, IV, and time shocks;
- hedge demand relative to expected underlying liquidity.

Strike distance must be normalized:

    strike distance in implied sigma =
        (strike - spot) / (spot × IV × square-root(time))

Do not call a strike a target merely because its GEX bar is large.

### 9.4 Volatility surface and event state

Features:

- constant-maturity ATM IV;
- IV Rank;
- IV percentile;
- term slope and curvature;
- skew;
- risk reversals and butterflies;
- volatility-of-volatility;
- ATM straddle-implied move;
- model-free implied variance where practical;
- realized-minus-implied variance;
- event variance from expiries bracketing earnings;
- risk-neutral finish-above-strike and touch-related features;
- surface staleness and static-arbitrage checks.

IV Rank and IV percentile must remain separate.

High IV is primarily:

- a magnitude or uncertainty state;
- an option-cost input;
- a trade-expression constraint.

It is not directional evidence.

### 9.5 Underlying and cross-sectional confirmation

Features:

- residual return versus SPY / QQQ;
- sector-relative and peer-relative strength;
- MAG-7 relative strength where relevant;
- VWAP state;
- opening-range state;
- gap;
- relative volume;
- realized volatility;
- stock-order imbalance if available;
- market and sector breadth;
- correlation regime;
- option and stock liquidity;
- distance to technical and option-derived levels;
- news and catalyst timestamps.

### 9.6 Events and regimes

Required point-in-time contexts:

- known earnings date;
- expiration and monthly OPEX;
- CPI and FOMC;
- index rebalance;
- ex-dividend;
- major company events;
- high/low volatility regime;
- positive/negative gamma scenario;
- breadth regime;
- liquidity regime;
- correlation regime.

---

## 10. Evidence dependency and contradiction engine

Net Drift, GEX, DEX, Vanna, Charm, and volume-above-OI can be correlated transformations of the same option chain or tape.

Create an evidence dependency graph:

- flow family;
- legacy OI / topology family;
- volatility-surface family;
- underlying-price family;
- event and fundamental family.

Rules:

- cap each family contribution;
- require independent families for high-conviction alerts;
- use grouped feature ablations;
- do not allow five OI transformations to appear as five confirmations;
- expose contradictions to users;
- reduce confidence when horizons do not align.

Examples of contradictions:

- bullish inferred flow but highly expensive IV;
- call flow across all expiries but GEX evidence from one expiry;
- positive conventional GEX while a momentum thesis assumes short-gamma amplification;
- highlighted expiry before a key catalyst;
- large premium after the stock has already completed most of its move;
- wall beyond a plausible remaining implied move;
- strong call premium but next-day OI declines;
- bullish single-name flow while peer and sector breadth deteriorate.

---

## 11. Horizon-specific engines

| Horizon | Primary options features | Required outputs |
|---|---|---|
| 5 to 60 minutes | flow burst, acceleration, relative delta flow, live stock momentum, local gamma state, liquidity | residual return, touch probability, realized volatility |
| Intraday to 2 days | persistent flow, lead/chase, expiry topology, VWAP, relative strength, event context | close / next-day return, barrier touch, MFE and MAE |
| 2 to 20 trading days | next-day OI confirmation, repeated accumulation, skew/term changes, event variance, sector breadth | 5/10/20-day residual return, IV change, executable strategy P&L |
| 1 to 3 months | 30-to-180-DTE flow, longer-dated skew, event expectations, factor and revision context | 20/60-day residual return and realized-versus-implied edge |
| 3 to 12 months | fundamentals, revisions, quality, valuation, macro, credit, borrow, persistent LEAPS information | monthly and quarterly residual returns and valuation scenarios |

Near-expiry GEX should receive almost no weight in long-horizon stock selection.

---

## 12. Candidate scanner archetypes

### A. Momentum accelerator

Candidate evidence:

- confidence-weighted bullish option-induced stock flow;
- meaningful probability that flow is opening;
- estimated incremental dealer short-gamma state;
- stock and sector confirmation;
- relevant strike within a plausible implied move;
- hedge demand large relative to underlying liquidity.

### B. Flow-divergence reversal

Candidate evidence:

- strong bullish delta flow;
- stock initially flat or down;
- no prior price chase;
- later residual-price confirmation;
- supportive sector and breadth.

This may be more informative than call buying after a stock has already rallied.

### C. Long-gamma pin or reversion

Candidate evidence:

- spot already close to a concentrated monthly strike;
- positive-gamma scenario;
- meaningful hedge flow relative to liquidity;
- no imminent catalyst;
- declining realized volatility;
- empirical pin probability above baseline.

### D. Event-volatility dislocation

Candidate evidence:

- event variance inconsistent with historical event-conditioned outcomes;
- unusual skew or term repricing;
- implied move versus modelled distribution;
- direction and volatility handled separately.

### E. Stealth accumulation

Candidate evidence:

- repeated moderate opening-flow probability across sessions;
- longer-dated ATM or slightly OTM contracts;
- next-day OI confirmation;
- limited immediate stock response;
- improving revisions, fundamentals, or peer-relative strength.

This is more appropriate for medium horizons than a near-expiry gamma wall.

---

## 13. Proposed MSFT-like alert contract

Do not hard-code final thresholds from this one example. Pre-register the feature families and learn or calibrate thresholds from history.

An alert candidate should pass:

### Data-quality gate

- quotes are fresh;
- spreads are within a liquidity threshold;
- duplicate and correction handling passed;
- underlying price is synchronized;
- Greeks and OI are point-in-time valid;
- event calendar is known at the timestamp.

### Flow gate

- confidence-weighted delta flow is extreme relative to the same ticker and time of day;
- evidence persists across more than one time bucket;
- the flow is not explained solely by one ambiguous complex print;
- lead/chase score is favorable;
- DTE and moneyness match the forecast horizon.

### Structure gate

- relevant exposure concentration is material;
- target or barrier is expressed in implied-sigma distance;
- strike expiry matches the flow and horizon;
- hedge-demand scenario is meaningful relative to underlying liquidity;
- dealer-sign uncertainty is disclosed.

### Independent confirmation gate

Require at least one non-options family:

- residual momentum;
- VWAP or opening-range confirmation;
- sector or peer breadth;
- catalyst information.

### Contradiction gate

Display and penalize:

- expensive IV;
- horizon mismatch;
- positive-gamma resistance or pin risk;
- post-price-chase flow;
- event outside the selected expiry;
- low classification confidence.

### Output

Each alert should report:

- ticker and exact timestamp;
- forecast horizon;
- direction distribution;
- magnitude distribution;
- realized-volatility and IV forecast;
- strike-touch and pin probabilities;
- quality/confidence score;
- observed evidence;
- inferred evidence;
- contradictory evidence;
- expected move;
- important strikes under each positioning scenario;
- best after-cost trade expressions;
- abstain option;
- invalidation conditions;
- expected signal half-life;
- feature, formula, model, and data versions.

---

## 14. Labels and outcome grading

Do not use a single label such as stock went up.

Required labels:

- benchmark- and sector-adjusted returns at 5, 30, and 60 minutes;
- close return;
- 1, 5, 10, 20, and 60-trading-day residual returns;
- volatility-scaled triple-barrier outcome;
- maximum favorable excursion;
- maximum adverse excursion;
- drawdown;
- realized variance;
- realized-minus-implied variance;
- constant-delta / constant-tenor IV change;
- strike touch;
- finish above strike;
- close near strike;
- expiry pin;
- executable option-strategy P&L using entry ask and exit bid;
- fill probability and capacity.

Every signal candidate, including failures and ignored candidates, must be written to the ledger.

---

## 15. Backtest and model discipline

### Point-in-time rules

- Freeze every input at the signal timestamp.
- Never use OI published the following morning.
- Use realistic processing and entry latency.
- Preserve point-in-time universes and adjusted contracts.
- Use event dates as known at the time.
- Keep derived-state snapshots reproducible.

### Validation design

- purged and embargoed walk-forward validation;
- no random train/test split;
- date- and event-grouped bootstrap;
- matched-control event studies;
- price/volume-only baseline;
- options-flow-only baseline;
- exposure-only baseline;
- volatility-surface-only baseline;
- combined model;
- grouped feature-family ablation;
- shuffled-flow and randomized-timestamp placebos;
- realistic spreads, costs, impact, and capacity;
- multiple-testing controls;
- shadow-live evaluation.

### Metrics

- precision at K;
- information coefficient;
- Brier score and probability calibration;
- residual return after costs;
- executable strategy return;
- turnover;
- drawdown;
- CVaR;
- capacity;
- regime stability;
- signal decay;
- missing-data sensitivity.

### Initial models

Start with:

- regularized linear and logistic models;
- quantile regression;
- LightGBM or CatBoost;
- calibrated probability layers;
- hierarchical shrinkage across tickers;
- regime-gated ensembles.

Later candidates:

- survival models for strike touch;
- online change-point detection;
- Hawkes-style flow clustering;
- constrained IV-surface models;
- mixture-of-experts.

Do not introduce deep learning until transparent baselines demonstrate stable incremental value.

---

## 16. Trade-expression and risk layer

Forecast the stock distribution first. Select the instrument second.

Examples:

- bullish direction plus expensive volatility:
  - shares or a defined-risk call spread may dominate naked calls;

- bullish direction plus underpriced convexity:
  - calls may be appropriate;

- large magnitude plus weak direction:
  - consider a defined-risk volatility structure;

- high pin probability plus overpriced volatility:
  - only defined-risk short-volatility research, with event-tail controls;

- poor liquidity or conflicting models:
  - abstain.

Required controls:

- name, sector, factor, and event limits;
- portfolio delta, gamma, vega, theta, and gap limits;
- liquidity and capacity limits;
- shock scenarios for spot, IV, skew, and correlation;
- maximum defined loss for short options;
- signal-decay exits;
- stale-data and surface-failure kill switches;
- model-drift and calibration monitors.

---

## 17. Implementation program

### Phase 0: measurement contract and data integrity

Target: 1 to 2 weeks.

Deliverables:

- canonical ThetaData store resolver;
- data catalog and coverage report;
- formula / unit / sign / timestamp specification;
- explicit failure on missing history;
- unified IV Rank history wired into all consumers;
- synchronized underlying-price source;
- incremental sequence-aware live ingestion;
- durable signal snapshot schema;
- archive and retention policy;
- repair stale or empty matrix outputs;
- deterministic 2026-07-14 MSFT reconstruction.

Exit gate:

- the same timestamped MSFT state can be reproduced twice from immutable inputs;
- GEX unit differences are explainable from the measurement contract;
- no future OI or later screenshot state leaks into the initial signal.

### Phase 1: deterministic analytics and replay

Target: 2 to 4 additional weeks.

Deliverables:

- replay service;
- constant-maturity and arbitrage-checked IV surface;
- expected-move and event-variance engine;
- legacy versus incremental exposure separation;
- positioning scenario cube;
- multi-leg and roll reconstruction v1;
- next-day OI reconciliation;
- 60- and 252-session same-time-of-day flow baselines;
- lead/chase scoring;
- immutable signal and outcome ledger populated historically.

Exit gate:

- any historical alert can be reconstructed from data available at that timestamp.

### Phase 2: preregistered research

Target: 3 to 6 additional weeks.

Deliverables:

- formal MSFT-like hypothesis document;
- fixed feature families before outcome inspection;
- price-only, flow-only, topology-only, vol-only, and combined baselines;
- matched controls;
- horizon-specific labels;
- walk-forward and placebo results;
- executable option-P&L study;
- failure library.

Exit gate:

- at least one options family adds stable out-of-sample value beyond price, volume, sector, and event baselines;
- result survives costs and reasonable specification changes.

### Phase 3: paper scanner

Deliverables:

- cross-sectional opportunity ranking;
- D / M / V / P / Q outputs;
- evidence dependency caps;
- contradiction engine;
- alert explanations;
- trade-expression optimizer;
- automatic outcome grading;
- live/offline parity monitoring.

Exit gate:

- stable shadow performance across multiple regimes;
- acceptable calibration, data quality, turnover, and capacity.

### Phase 4: governed limited deployment

Proceed only after:

- predetermined risk limits;
- data-quality kill switches;
- model-drift monitoring;
- stable shadow results;
- no unresolved point-in-time leakage;
- documented rollback and disable paths.

---

## 18. Priority engineering docket

Recommended order:

1. Canonical store resolver and lineage.
2. Immutable point-in-time signal ledger.
3. Incremental live trade ingestion.
4. Permanent contract/minute aggregates plus selective raw retention.
5. Unified IV30, IV Rank, IV percentile, expected move, and event variance.
6. Synchronized underlying stock tape.
7. Legacy exposure versus flow-implied exposure separation.
8. Exposure scenario bands and unit contract.
9. Multi-leg reconstruction.
10. Next-day OI confirmation.
11. Lead/chase features.
12. Historical MSFT-like preregistration and gauntlet.
13. Horizon-specific models.
14. Paper scanner and outcome dashboard.

Avoid prioritizing another UI panel before items 1 through 10 are working.

---

## 19. Data procurement conclusion

Version 1 does not require another broad vendor.

QuantData may be useful temporarily as:

- a black-box comparison oracle;
- a formula and display benchmark;
- a source for discrepancy investigations.

It should not become the canonical research dependency if the same analytics can be generated from owned data.

If supplemental budget is available, the highest-value purchase would be a limited ground-truth sample containing some combination of:

- true buy/sell side;
- opening/closing status;
- participant capacity;
- complex-order linkage;
- execution-time NBBO.

That sample should be used to calibrate inference uncertainty, not assumed to represent all venues or all dealer inventory.

No public consolidated feed provides complete beneficial-owner intent, OTC inventory, internal dealer hedges, or true all-market dealer positioning.

---

## 20. Binding epistemic laws

1. Calls bought means inferred aggressive-side call buying, not known bullish opening demand.
2. Volume above OI does not prove opening activity.
3. Conventional GEX is an exposure proxy under an assumed sign convention.
4. Positive GEX is not automatically upward pressure.
5. Static DEX is not future stock demand.
6. IV Rank is not direction or expected move.
7. Related transformations of one source are not independent confluences.
8. Contract, expiry, event, and forecast horizons must align.
9. Same-day use of next-morning OI is prohibited.
10. Later price confirmation cannot be inserted into an earlier alert.
11. Every signal requires an immutable snapshot and outcome.
12. Greek topology remains display/path/volatility evidence until incremental directional value passes the gauntlet.
13. The system must be allowed to abstain.
14. A successful screenshot is a hypothesis generator, not validation.

---

## 21. Requested Fable response

Fable should:

1. Verify this audit against the current operational branches and stores.
2. Adjudicate which existing options roadmaps this document supersedes, amends, or consolidates.
3. Convert the priority docket into small, dependency-ordered PR work packages.
4. Preserve the binding epistemic laws.
5. Identify the minimum replayable dataset required for the MSFT preregistration.
6. Define the exact acceptance tests for Phase 0.
7. Avoid status inflation: analytics remain display-tier until predictive and tradability gates pass.
8. Make the first deliverable the measurement contract plus point-in-time replay, not a new composite score.

---

## 22. External research references

- QuantData, Mastering Net Drift:
  https://help.quantdata.us/en/articles/9900974-mastering-the-net-drift-tool-leveraging-order-flow-sentiment-for-smarter-options-trading

- QuantData, GEX methodology and dealer-positioning limitations:
  https://help.quantdata.us/en/articles/15807345-gamma-exposure-gex-api-python-quickstart-dealer-positioning-guide

- QuantData, IV Rank endpoint:
  https://quantdata.us/api/docs/endpoints/iv-rank

- QuantData, Interval Map:
  https://quantdata.us/api/docs/endpoints/interval-map

- Databento, OPRA dataset and trade-side limitations:
  https://databento.com/docs/venues-and-datasets/opra-pillar

- Hu, Does Option Trading Convey Stock Price Information?:
  https://www.sciencedirect.com/science/article/pii/S0304405X13003048

- Pan and Poteshman, The Information in Option Volume for Future Stock Prices:
  https://web.mit.edu/junpan/www/volume.pdf

- Gamma Fragility:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454

- Cboe Enhanced Trade-by-Trade:
  https://datashop.cboe.com/enhanced-us-options-trade-by-trade-execution-detail

- OCC / Options Industry Council open-interest mechanics:
  https://www.optionseducation.org/referencelibrary/faq/general-information

---

## 23. Final interpretation of the MSFT case

The defensible point-in-time description is:

> MSFT displayed potentially bullish short-term inferred option flow, historically expensive volatility, an interesting nearby expiry-strike topology, and uncertain dealer-mechanics evidence.

That is a worthwhile candidate alert.

It is not yet an automatic buy-calls signal, and one successful subsequent move is not evidence of a repeatable edge.
