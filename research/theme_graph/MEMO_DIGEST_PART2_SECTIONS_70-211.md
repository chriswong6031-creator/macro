# Memo Digest — Part 2 of 3 (lines 3177–8195)

Source: `/Users/chriswong/Downloads/Mastermind_Global_Market_Intelligence_Organism_Final.md`
Covers: PART IV–XVII (§70–211). Research notebook by a ChatGPT session with NO codebase access — every claim about "existing Mastermind systems" is unverified by construction and must be checked against actual code before being treated as fact.

---

## PART IV — Dislocation Intelligence (§70–74)

**Concrete proposals:**
- §70 A relationship/Theme Graph mechanically creates a dislocation detector: dislocation redefined as "observed price behavior inconsistent with a relationship the system has reason to believe should currently matter" — not just "stock fell." Needs: an explicit expected-relationship model (peer, commodity-link, flow-link, factor-link) to diff price against. Universal (US+CN examples both given).
- §71 General dislocation taxonomy, six categories: **Price vs Fundamental** (CDE/HL mining example — one noisy print drags a sympathetic peer down while the commodity thesis is intact → "relationship overreaction"), **Price vs Theme** (laggard/hidden-beneficiary/company-specific triage, routes to Fundamental Forensics), **Price vs Commodity** (copper +12%, miners +18%, one name +1% → hedge-book/operational/jurisdiction hypotheses), **Flow vs Price** (persistent buying + flat price → absorption/stealth-accumulation/breakout-pending), **Attention vs Price** (state-dependent: +3σ attention + flat price = early discovery; +3σ attention + +70% price + falling breadth = saturation — same metric, opposite meaning by lifecycle), **Price vs Peer Graph** (peers must be *contextual* — a semi's live peer set is HBM suppliers/AI-memory names, not its GICS industry), **Expected Relationship Break** (real yields↓+USD flat+labor weak "should" mean gold up; if gold falls instead, that's a **model surprise** — wakes the Cortex).
- §72 Dislocation Falsification Layer — every dislocation candidate must carry: `ExpectedRelationship, ObservedDeviation, AlternativeExplanations, KnownNegativeEvidence, HistoricalMeanReversionRate, HistoricalFailureRate, Confidence`. Core question the system must actively search to answer: "What would make the current move rational rather than dislocated?" (lost customer, equity issuance, guide-down, regulatory action, etc.) — explicit anti-"every loss is an overreaction" guard.
- §73 `DislocationStrength = ExpectedRelationshipStrength × DeviationMagnitude × ContextValidity × CatalystPersistence × AbsenceOfIdiosyncraticExplanation` — a multiplicative composite score (flag: this is exactly the "composite-score soup" pattern PART XV later warns against — needs the same validation gauntlet before promotion).
- §74 Relative-value dislocation framing ("why has this stable relationship left its state-conditioned range?") positioned as safer research target than naked directional forecasts. Named pair types: miner vs metal, supplier vs customer, US theme vs China local expression, leader vs secondary, ETF vs NAV constituents, purity basket vs narrative-proxy basket. Statistically compatible with z-scores/residual models/cointegration/event studies.

**Claims about existing systems:** §70 says this "connects directly to prior Mastermind dislocation work" — needs-verification (no system named beyond the memo's own earlier parts).

**Flags:** §71–72 = CORE-CANDIDATE; §73 = ENHANCER pending validation; §74 = CORE-CANDIDATE.

---

## PART V — Top Recognition, Theme Fragility, Distribution (§75–84)

**Concrete proposals:**
- §75 Unify Mastermind's "top-recognition" research with a new Theme Lifecycle Engine via a shared `FragilityState` concept. Core reframed question: "extended + continues" vs "extended + tops" — same distinction, applied to themes not just single stocks.
- §76 Theme Fragility should be multi-dimensional (14 named inputs: price extension/acceleration, volatility expansion, turnover explosion, breadth deterioration, leader concentration/failure, attention saturation, narrative exhaustion, valuation extremity, issuance/insider selling, options speculation, flow divergence, new-entrant quality, cross-asset non-confirmation). Cites unnamed academic research: run-up magnitude alone doesn't predict low future returns, but run-up *characteristics* (volatility, turnover, issuance, price path) separate crash-prone episodes — argues for modeling **anatomy**, not extension alone.
- §77 Theme Fragility State Machine: `Healthy Trend → Extended → Accelerating → Saturated → Fragile → Distributing → Failed Continuation → Breakdown`, non-deterministic (can loop via Consolidation→Re-Acceleration). Output: `P(continuation), P(consolidation), P(distribution), P(material drawdown)` at 5D/20D/60D/120D horizons.
- §78 `ThemeInternalsDeterioration`: index new-high + fewer members at new highs + leaders capturing more return + failed breakouts rising = late-cycle breadth divergence. US variant: mega-cap concentration, options frenzy, weak equal-weight. China variant: high-board leaders still rising but first-board participation declining, failed seals increasing.
- §79 `ConstituentQualityGradient` — track whether new outperformers have progressively lower economic exposure / weaker fundamentals / higher narrative-only exposure / lower liquidity / higher short interest — a shift `high-purity leaders → quality suppliers → secondaries → tenuous proxies` may mark narrative saturation ("infection reaching marginal hosts").
- §80 `ThemeWashingRisk = NarrativeExposure − EconomicEvidence`, adjusted for mention frequency, lack of measurable revenue, vague language, absent contracts, weak capex/R&D evidence. Cites Morningstar's public "theme washing" concept as prior art (external, not Mastermind).
- §81 Narrative-fundamental divergence is **sign-ambiguous by lifecycle** — early-cycle it's bullish (narrative correctly leads financials in real transitions); late-cycle the same divergence is bearish (evidence stalls, valuation stays extreme). Explicit argument for state-conditioning over static thresholds.
- §82 `CatalystResponseElasticity = price response / catalyst surprise` as an incremental-buyer-exhaustion proxy — shrinking response to bullish catalysts signals exhaustion; outsized response to minor catalysts signals reflexive demand still intact.
- §83 `AsymmetricNewsElasticity`: healthy bull = "good news→large upside, bad news→shallow dip"; distribution = "good news→little upside, bad news→large downside." Measurable at stock/theme/market level — framed as observing how the market *processes* information, not just what information exists.
- §84 Failed Continuation (conditions that historically produce continuation repeatedly failing to do so) argued as a stronger negative-surprise signal than "overbought"/RSI-style thresholds; should update `P(distribution)` directly.

**Claims about existing systems:** §75 claims Mastermind already has "top-recognition research" as a going project — needs-verification against actual code/masterplans, not assumed (plausible given this repo's known top-recognition/short lineage).

**Flags:** §77, §81, §82, §83 = CORE-CANDIDATE; §75 = CORE-CANDIDATE contingent on verifying the top-recognition system exists; §76/§78/§79/§80/§84 = ENHANCER (variants of standard breadth-deterioration logic).

---

## PART VI — Market State, World Model, Contextual Intuition (§85–97)

**Concrete proposals:**
- §85–86 `State_t` world-state object (Growth, Inflation, Liquidity, Rates, Credit, FX, Policy, Commodities, Volatility, Breadth, Momentum, Positioning, Earnings, Narratives, US/China ecology, Global theme states...) intended to scale to "hundreds or thousands of dimensions" — explicitly rejects collapsing to Risk-On/Risk-Off labels. `Market State Tensor` = Entity × Horizon × Dimension (Entity: Global/Country/Exchange/Index/Factor/Industry/Theme/Subtheme/Company/ETF/Commodity/Participant/Event; Horizon: tick→cycle; Dimension: price/volume/flow/attention/narrative/sentiment/fundamental/valuation/positioning/microstructure/macro). Purpose: prevent conflating a 5-minute event with a 6-month trend.
- §87 Horizon separation is "non-negotiable" — signals must preserve `{direction, magnitude, horizon, confidence}` rather than collapsing to one bullish/bearish score, so downstream consumers (trade/swing/medium/strategic) can reason independently.
- §88 Standardized **belief object** every lobe should emit: `Observation, Derived State, Direction, Magnitude, Horizon, Confidence, Historical Reliability, Regime Compatibility, Causal Interpretation, Contradicting Evidence, Novelty, Provenance, Expected Consequences`. Worked example given (China Speculation Ecology lobe). The "Expected Consequences" field is called out as the crucial part — it creates a falsifiable expectation.
- §89 Every important belief must generate testable expectations ("if my interpretation is correct, what should happen next?") — failure to materialize should reduce confidence. This is presented as the core self-correction loop.
- §90–91 `Surprise = Observed Outcome − Expected Outcome` as an organizing primitive; surprise **propagates through causal chains** (NFP surprise→yield surprise→gold surprise→miner surprise) so the system can localize *where* a causal chain broke (equity layer vs macro-pricing layer) rather than emit a flat anomaly score.
- §92 `Salience = f(Surprise, Magnitude, Novelty, RelationshipBreak, RegimeTransition, PredictiveImportance, PortfolioRelevance, CrossLobeDisagreement)` — gates which events get expensive Cortex/LLM reasoning, explicitly for compute scalability (not every ticker reasoned about continuously).
- §93 `Novelty(State_t) = 1 − max historical similarity` — controls which reasoning mode is used: familiar states use empirical analogs/calibrated conditional probabilities/learned weights; novel states use causal reasoning/scenario analysis/conservative confidence/explicit uncertainty.
- §94 Historical-analog retrieval must output **Similarities + Differences + Causal relevance of differences**, not just "closest match" — explicit anti-"2021 again" pattern-matching guard, worked example format given.
- §95 State-dependent signal weighting: `Score_t = Σ w_i(State_t) · signal_i,t` instead of fixed weights — gold real-yield weight vs USD-funding weight shifts by regime; China limit-up-ecology weight shifts by 冰点-recovery vs policy-driven-large-cap regime.
- §96 Mixture-of-experts as practical approximation: named experts (Early Easing, Inflationary Expansion, Growth Scare, Liquidity Crisis, Commodity Shock, Speculative Momentum, AI CapEx, China Stimulus, China Sentiment Recovery, Late-Cycle Bubble) gated by `P(regime_k)`, weights calibrated historically not invented by the LLM.
- §97 "LLM is the scientist, not the calculator" — LLM handles interpretation/contradiction-detection/causal-hypothesis/analogy/synthesis; deterministic/statistical layer handles correlation/scoring/calibration/optimization/execution/validation.

**Claims about existing systems:** §85 asserts "the Neural Web architecture already provides the correct abstraction" for world state — needs-verification. §86/§88 attribute the Market State Tensor and belief-object schema to "earlier brainstorming"/"prior Neural Web research" — these are self-references to earlier parts of the *same memo* (outside this reader's range), not confirmed Mastermind code.

**Flags:** §88, §90–95 = CORE-CANDIDATE (conceptual backbone of the memo's epistemics — belief objects, surprise, salience, novelty, contextual weighting are concrete, testable, mutually reinforcing); §97 = LIKELY-ALREADY-EXISTS (near-verbatim match to house law "LLM never originates signals/scores" — convergent doctrine, not a new proposal); §96 = ENHANCER; §85/§86 = VOCABULARY-ONLY ("hundreds or thousands of dimensions" is aspirational) though the Tensor's three axes are a useful organizing schema.

---

## PART VII — Historical Memory and Synthetic Market Experience (§98–104)

**Concrete proposals:**
- §98 Persistent theme memory: birth catalyst, initial members, leadership transitions, expansions, failed waves, valuation extremes, attention peaks, key earnings, policy changes, distribution events, prior analogs — themes become "experienced entities."
- §99 Three memory types (attributed to "the Neural Web architecture's memory taxonomy," i.e. inherited from elsewhere in the memo): **Episodic** (specific historical episodes with full state-at-ignition detail), **Semantic** (generalized beliefs extracted from episodes, e.g. "commercial-space breakouts persist longer when defense procurement + private launch demand accelerate together"), **Procedural** (behavioral rule changes — e.g. raise a continuation-factor weight under a named joint condition). Procedural is flagged as "critical" — learning must change behavior, not just accumulate notes.
- §100 Historical replay as "domain apprenticeship" — strict point-in-time information at each replay date, output full forecast bundle (1D/5D/20D/60D + confidence), then reveal outcomes and ask what surprised the system.
- §101 Theme replay across ~16 named historical episodes (dot-com infra, shale, solar, EVs, cannabis, SPACs, COVID beneficiaries, cloud, semis, AI, uranium, precious metals, Chinese property/EV, A-share AI/brokerage rallies) to learn transition probabilities between labeled outcome states (Expansion/Failed Ignition/Consolidation/Mania/Distribution/Collapse/Second Wave).
- §102 "Hindsight is allowed for labels, not features" — the top-recognition research's rule (claimed prior art) generalized: every historical dataset needs `event_time, knowledge_time, release_time, revision_time`.
- §103 The **ontology itself** must be point-in-time — theme *membership* needs `evidence_time, belief_time, valid_time` so a 2022 backtest can't silently use 2026 knowledge that a company became an AI beneficiary. Proposed solution: reconstruct historical theme edges only from documents available at the time — explicitly flagged as "expensive" but "one of the most valuable forms of data integrity in the whole system."
- §104 Aspirational: replay the same historical eras (2008/2020/2021) repeatedly as the model improves, to approximate "repeated apprenticeship."

**Claims about existing systems:** §99, §102 attribute prior work to "the Neural Web architecture" / "the top-recognition research" — needs-verification against actual repo.

**Flags:** §100, §102, §103 = CORE-CANDIDATE (§103 especially — point-in-time theme ontology is a real, hard, high-value engineering problem directly relevant to this repo's existing point-in-time discipline); §99 = CORE-CANDIDATE as a taxonomy even if the "inherited from Neural Web" claim is unverified; §98, §101 = ENHANCER; §104 = VOCABULARY-ONLY/aspirational.

---

## PART VIII — How This Plugs Into the Existing Mastermind Neural Web (§105–120)

**This entire PART is claims about existing systems — flag ALL as needs-verification. The author never saw code; this is entirely the memo's own mental model of what Mastermind is.**

Map of what the memo *thinks* the Neural Web is:
- §105 Argues the proposed Theme/Dynamic Theme Graph should NOT be "just another lobe" alongside a claimed existing set — **Macro Lobe, Options Lobe, Fundamentals Lobe** (named as if these already exist) — but a **semantic relationship layer** multiple lobes read/write through.
- §106 Calls the Dynamic Theme Graph the "missing semantic bus" — claims current systems suffer representation fragmentation: Macro/Commodity/Equity/Theme/News each hold isolated facts with no shared layer connecting them into one causal chain.
- §107 Names specific existing Mastermind systems and what each should newly receive from the Theme Graph — **needs-verification, item by item**:
  - **Prophet** ← market state, theme lifecycle, theme factor returns, constituent roles, crowding, historical analogs. (Prophet is confirmed real per this repo's "Prophet US" program, but these specific claimed inputs are the memo's proposal, not confirmed fact.)
  - **Risk Radar** ← theme concentration, correlated-theme contagion, cross-theme dependence, crowding, fragility. (Not corroborated elsewhere in provided context — verify existence.)
  - **Rotation Engine** ← theme market share, attention share, flow share, migration, leadership renewal. (Same — verify existence.)
  - **Short / Top Recognition** ← lifecycle, narrative exhaustion, breadth deterioration, theme washing, catalyst response elasticity.
  - **Fundamental Forensics** ← theme-specific expectations, peer context, economic exposure, dislocation candidates (recurs at §112, treated as an established system).
  - **Alternative Data Network** ← a semantic target (the Theme Graph) to map every alt-data event onto.
- §108–109 Alternative data (govt contracts, patents, lobbying, congressional trades, satellite, import/export, procurement, hiring, web traffic) becomes causal evidence rather than "museum" novelty once routed through the Theme Graph; events should **update belief state fields** (`Company Economic Exposure`, `Catalyst Activation`, `Theme Fundamental Confirmation`, `Supply-Chain Confidence`, `Revenue Expectation` horizon, `Theme State` discovery-confidence delta) rather than fire a bare alert.
- §110 Policy plane: `Executive Order/Budget/Procurement/Regulation → Policy Event Node → affected industries → Theme Graph → Company Exposure Graph`. Valuable distinction: track **Announcement / Authorization / Appropriation / Contract Award / Actual Spending** separately — "a policy headline with no funding should not equal cash-flow reality."
- §111 Claims Mastermind "already has a forward-looking Foresight layer" that could feed catalyst probabilities (`P(policy event), P(regulatory decision), P(earnings catalyst), P(product launch), P(contract), P(macro event)`) — needs-verification ("Prophet US" with "25 forward plans" is possibly related, but "Foresight" as a named layer is unconfirmed).
- §112 Fundamental Forensics (claimed existing) should output `Narrative/Fundamental Alignment: Strong/Moderate/Weak/Speculative` from revenue share, backlog, orders, capex, margin, management language, unit economics, customer concentration.
- §113 Risk Radar (claimed existing) should reason over theme-contagion graphs (memory-pricing collapse→producers→semicap suppliers→AI server BOM→AI hardware basket; silver collapse→miners→risk appetite→junior miners→leveraged ETFs), using graph centrality to find propagation nodes/bottlenecks.
- §114 Graph centrality (`Economic/Narrative/Trading/Supply-Chain/Catalyst Centrality`) can surface a small-cap structurally important to a theme graph — a "market sensor discovery" process.
- §115 Empirically-learned **leading indicator nodes** (commodity→miners, hyperscaler capex→power equipment, memory spot→memory equities, A50 futures→China open, US ADR basket→local A-share sentiment), stored as `LeadLagEdge{source, target, horizon, regime, historical_strength, current_strength}` — regime-dependent, not fixed.
- §116 Graph edges must be typed, not flattened to `related_to`: `CAUSES/TRANSMITS, SUPPLIES, BUYS_FROM, COMPETES_WITH, SUBSTITUTES_FOR, CORRELATES_WITH, LEADS, CO-MOVES_WITH, NARRATIVELY_ASSOCIATED_WITH, OWNED_BY, MEMBER_OF`.
- §117 Track `CausalConfidence` separately from `PredictiveStrength` (+`Stability`,`Horizon`) — a relationship can be strong-causal/weak-predictive (commodity→producer economics) or weak-causal/strong-predictive (one liquid ETF mechanically leading a basket by minutes).
- §118–119 Build causal **chains**, not pairwise edges (NFP→Fed repricing→nominal yields→real yields→gold→senior miners→junior miners), so a break localizes to one link; every edge learns `lag_distribution, half_life, regime_dependence` — delay ranges from seconds (release→Treasury) to quarters/years (policy→supplier revenue).
- §120 Counterfactual layer: estimate "expected move ex-event" via market/sector residuals, matched controls, synthetic baskets, event studies, factor models (worked example: observed +8.0%, expected ex-event +2.4%, residual +5.6%).

**Flags:** §107's named-system list = **needs-verification, highest priority in this PART** — confirm which actually exist before treating "new inputs" as gap-filling vs net-new builds. §111's "Foresight layer" = needs-verification. §116–119 (typed edges, causal-vs-predictive separation, multi-hop chains, learned propagation delay) = CORE-CANDIDATE, portable regardless of the lobe roster. §110 (Announcement→Spending funding-stage ladder) = CORE-CANDIDATE, cheap. §120 = ENHANCER. §108–109, §112–115 = ENHANCER, contingent on named systems' real shape.

---

## PART IX — Master Market-State Engine Across US and China (§121–126)

**Concrete proposals:**
- §121 One `GLOBAL WORLD STATE` tree with distinct local branches: US Market State (equity breadth, options, ETF flows, credit, theme states), China Market State (breadth, limit-up ecology, auction, policy liquidity, theme states), HK Market State, Commodity State, Macro State — explicit non-goal of pretending markets are identical.
- §122 Machine-readable "weather report" per market — China fields (Direction, Market Quality, Speculation, Liquidity, Theme Concentration, Breadth, High-board survival, Prior limit-up reward, Policy capital, Crowding) differ from US fields (Direction, Market Quality, Mega-cap concentration, Equal-weight breadth, Options speculation, Credit, Real yields, Theme leadership, Crowding) — same report *type*, market-native fields.
- §123 Explicit epistemics warning: don't invent 0–100 "Market Quality" scores from intuition — map them to empirical historical distributions (e.g., "82 = historically top 18% of internal confirmation") and record conditional outcomes, "turning a pretty gauge into a calibrated state variable."
- §124 Market concentration is multi-typed, must be tracked separately: Return / Turnover / Attention / Theme / Leadership / Ownership Concentration — a market can be broad in price but narrow in narrative, or vice versa.
- §125 Market synchronization (cross-sectional correlation) should modulate `StockSelectionWeight` — high sync → macro/factor dominates, low sync → idiosyncratic/theme selection matters more; proposed as an input to Prophet's expected value of stock-picking signals.
- §126 Every signal needs `SignalReliabilityByState` — worked examples: China first-board continuation signal strong in sentiment-recovery+rising-turnover, weak in 沸点(boiling)/declining-prior-board-premium; US small-cap breakout signal strong in falling-real-yields+broad-risk-on+improving-credit, weak in rising funding stress.

**Claims about existing systems:** None explicit beyond generic "Prophet" reference in §125 (already flagged in PART VIII).

**Flags:** §121, §123, §126 = CORE-CANDIDATE (§123 is a direct instance of this repo's own "validated claims" CI law — reinforcing, not novel); §122, §124, §125 = ENHANCER.

---

## PART X — US-Specific Intelligence Organs (§127–136)

**Concrete proposals:**
- §127 US ETF ecosystem as capital-flow map: graph `ETF —holds→ Company`, `—represents→ Theme`, `—overlaps→ ETF`, `—receives→ Flow`; derive `ThemeETFFlow, ThemeConsensusHoldings, CrowdedETFOverlap, PassiveFlowSensitivity`. Needs ETF holdings + flow data.
- §128 `ThemeConsensusScore = f(# relevant ETFs, weights, manager diversity, theme purity, time persistence)` — generalizes Morningstar's "many independent thematic funds holding the same stock = market-perceived relevance" idea (credited to Morningstar, external methodology).
- §129 Crowded thematic ETF co-ownership of small/mid-caps creates mechanical dislocation risk (inflow amplification, outflow forced-selling, rebalance-date effects); track `ETFOwnershipPressure, ETFOverlap, FlowSensitivity`; reflexivity loop named: narrative↑→ETF inflow→constituent buying→return↑→more attention.
- §130 US options aggregated to **theme level**, not per-ticker: `call_volume, put_volume, open_interest, skew, implied_volatility, term_structure, dealer-sensitive positioning where obtainable, options_attention`. Key question: is speculation concentrated in the leader or broadening (early phase vs mania signature).
- §131 Options data-source split: OCC publicly exposes volume/OI reports (account-type, exchange, historical windows) — usable as public baseline; richer intraday flow, quote history, Greeks, trade classification, long backfills likely require **licensed vendor feeds**. Warning: retain provenance tags (`Raw exchange/OCC observable / Vendor-derived classification / Mastermind inference`) — "do not present inferred 'smart money' labels as direct facts."
- §132 SEC EDGAR (real-time submission histories + XBRL, plus bulk archives) as foundational semantic source for company-theme edges: extraction targets = new product language, revenue-segment changes, capex, customer concentration, risk factors, acquisitions, partnerships, geographic exposure, contract references. Framed as creating an "auditable evidence layer."
- §133 13F warning: quarter-end holdings snapshot, **not live flow** — "13F ≠ today's smart-money buying." Legitimate uses: persistent ownership, manager-theme fingerprints, ownership concentration, QoQ change, consensus.
- §134 `ManagerThemeExposure, ThemeChangeOverTime, Concentration, TypicalHoldingPeriod, PositionInitiationPattern` per institutional manager from 13F, to find managers systematically early to commodity themes ahead of public narrative peaks — "slow-moving capital-intelligence layer."
- §135 Theme-level aggregation of earnings/revenue revision breadth, price-target changes, rating changes, estimate dispersion — to separate "price strong + revisions strong" from "price strong + revisions deteriorating" (narrative outrunning fundamentals).
- §136 FINRA short-side data warning (load-bearing epistemics point): short interest, off-exchange short-sale volume, and monthly short-sale transaction files are all available, but **short-sale volume is explicitly NOT short interest and is not a direct bearish-position measure** — "this distinction should be hard-coded into the intelligence ontology... A false 'short pressure' label would poison the graph."

**Claims about existing systems:** None load-bearing beyond generic Prophet reference.

**Data-source availability claims:** SEC EDGAR (real-time API + bulk, public); FINRA short interest/short-sale-volume (public, semantically dangerous if conflated); OCC options volume/OI (public baseline only, richer flow/Greeks/backfill = commercial/licensed); 13F (public, structured, quarterly-lagged).

**Flags:** §133, §136 = CORE-CANDIDATE (crisp, cheap-to-encode "don't misuse this data" rules); §131 = DATA-BLOCKED (deep options flow needs paid vendor); §132 = CORE-CANDIDATE; §127–130, §134–135 = ENHANCER.

---

## PART XI — China-Specific Intelligence Organs (§137–146)

**Concrete proposals:**
- §137 Argues China system must be modeled natively, not as a "translated US terminal" — lists native market-structure vocabulary as first-class concepts, not just Chinese labels for universal indicators: 涨停 (limit-up), 跌停 (limit-down), 连板 (consecutive boards), 炸板 (failed/broken seal), 封单 (order wall), 竞价 (auction), 游资 (hot money/speculative capital), 龙虎榜 (dragon-tiger list, top-trader disclosure), 情绪周期 (sentiment cycle), 板块接力 (sector relay), 昨日涨停溢价 (yesterday's-limit-up premium).
- §138 `Strategy Reinforcement Map` — generalizes "yesterday's limit-up cohort" into tracked cohorts (Yesterday Limit-Ups, Yesterday High Boards, Recent Breakouts, Recent IPOs, High-Turnover Leaders, Low-Price Speculative Names, Theme Laggards), each measured for next-session reward/drawdown/survival/follow-through — framed as reading "which kinds of risk-taking are currently being rewarded."
- §139 Board-height survival curve: `P(survive to n+1 board | currently n boards)`, conditioned on sentiment, theme breadth, turnover, first-touch time, seal quality, participant profile — probabilistic model of speculative-ladder health.
- §140 Auction intelligence as first-class signal: opening-auction fields (indicative price, matched/unmatched volume, imbalance direction, turnover, relative gap, revision during auction, final-seconds acceleration, theme peer sync); closing-auction fields reveal index/passive flow, institutional execution, rebalance pressure, next-day positioning.
- §141 "Auction Surprise" — compare realized auction state to the overnight prior expectation — "pre-open world state becomes immediately falsifiable."
- §142 封单 (order wall) must be **normalized**, not read as a raw level: `wall/free float, wall/ADV, wall/intraday traded value, wall/top-of-book depth, wall persistence, wall cancellation rate`, plus **wall trajectory** (falling ¥500m→¥120m while sealed differs from a strengthening wall) — "derivative > level."
- §143 Failed-board anatomy as its own episode type (first touch time, # breaks, time sealed, largest wall, wall decay, volume after break, theme/leader behavior, sentiment, closing location), classified into Healthy shakeout / Weak seal / Distribution / Theme-wide / Idiosyncratic failure.
- §144 龙虎榜 participant behavior should be read **conditional on theme lifecycle stage**, not given static good/bad labels — early-repeat 游资 participation confirms ignition in Discovery; late low-purity-follower entry of the same seats signals Mania.
- §145 Cites academic literature (Baidu search data) finding real attention/Chinese-stock-behavior relationships (abnormal returns, trading behavior, idiosyncratic risk, mispricing) — but warns against naive `attention↑→future return↑`; effects reverse by investor type and can raise volatility instead. Recommended framing: "attention is a causal/behavioral state variable whose meaning depends on lifecycle, participant composition, and current price response."
- §146 `AttentionSourceMix` — decompose "theme heat" by source (search, news, app clicks, social media, broker research, 龙虎榜, price-itself) since sources likely have different lead/lag information content (analyst-attention-leading may imply discovery; retail-search-after-+80%-move may imply saturation) — flagged as needing empirical study, not assumption.

**Claims about existing systems:** None load-bearing.

**Data-source availability claims:** Baidu search-attention data — academic literature shows it's usable, but no stated evidence Mastermind has this feed — DATA-BLOCKED pending confirmation. Auction/封单/龙虎榜/board-height fields (imbalance direction, revision-during-auction, wall-cancellation-rate) assume a China market-structure pipeline plausible given this repo's CN-limit-alpha program, but the specific fields are NOT confirmed as currently captured — needs-verification.

**Flags:** §139, §140, §142, §143 = CORE-CANDIDATE (concrete, implementable if raw auction/order-book data exists); §137 = VOCABULARY-ONLY but sets useful scope; §138, §141, §144 = ENHANCER; §145 = DATA-BLOCKED + CORE-CANDIDATE epistemics warning; §146 = ENHANCER.

---

## PART XII — New Proprietary Concepts (§147–166)

A concept-mint; most items are named formulas presented as hypotheses, not verified mechanisms. Per the memo's own PART XV rule, treat every name here as a candidate to be stress-tested, not adopted.

- §147 **Theme State Vector** — one standardized ~21-field schema per theme (EconomicExposureQuality, CatalystActivation, PriceMomentum, Breadth, Leadership, Flow, Attention, FundamentalRevisions, Valuation, Crowding, OptionsState, ETFState, Fragility, Lifecycle, Novelty, etc). Explicit claim: "the value is not the exact variable list. The value is standardization" — lets experience transfer across themes (AI, defense, gold, biotech, space, China AI/solar, US uranium) without assuming economic identity. **CORE-CANDIDATE** — most reusable idea in this PART.
- §148 Two parallel scores: **Theme Strength** (current force: return, relative strength, flow, attention, breadth) vs **Theme Health** (durability: leadership diversity, fundamental confirmation, narrative freshness, crowding, response symmetry) — worked contrast (AI Compute: Strength 93/Health 54 = "powerful but fragile"; 商业航天: Strength 62/Health 81 = "not extreme but improving"). **CORE-CANDIDATE.**
- §149 `ThemePressure = unrealized drivers − priced-in saturation` — self-flagged by the author as "difficult to quantify perfectly." **VOCABULARY-ONLY.**
- §150 Potential-Energy vs Realized-Motion 2×2 (early opportunity / powerful expansion / momentum-late-cycle / dormant). **ENHANCER.**
- §151–153 Three ratio metrics: `NarrativeCapitalConversion=Δflow/Δattention`, `CapitalPriceConversion=Δprice/Δflow`, `InfoPriceElasticity=abnormal return/information surprise` (quantifies "good news no longer works"). **ENHANCER**, mechanically simple, needs empirical validation.
- §154 **Theme Reflexivity Score** — price→attention→flow→price loop; tracks `ReflexivityStrength`+`ReflexivityDirection` since high reflexivity cuts both ways (continuation or violent reversal). **ENHANCER.**
- §155 **Fragility Surface, not one score** — split by shock type: `FragilityToRates, FragilityToLiquidity, FragilityToPolicy, FragilityToEarnings, FragilityToCommodity, FragilityToLeaderFailure` — enables scenario statements like "AI Power is crowded but more fragile to capex disappointment than to rates." **CORE-CANDIDATE.**
- §156 Theme Confidence must expose `DataCoverage, EvidenceQuality, ModelAgreement, HistoricalSampleSize, CurrentNovelty` and drop when ontology is new/data sparse/signals disagree/state is novel — explicit anti-false-precision rule. **CORE-CANDIDATE** (epistemics; directly reusable in this repo's confidence-surfacing UI).
- §157 `StateEntropy` — disagreement about a theme's state (Consolidation vs Distribution) is itself informative (high entropy = transition = both opportunity and risk). **ENHANCER.**
- §158 `AttentionEfficiency = fundamental information generated / total attention` — separates research-driven discovery from pure social speculation. **VOCABULARY-ONLY** (unclear how the numerator gets measured).
- §159 `EvidenceVelocity` — whether hard evidence (contracts/revenue/orders/capex/guidance/adoption/margins) catches up to narrative; healthy theme = accelerates, fragile theme = stalls. **ENHANCER.**
- §160 **Theme Legitimacy Curve** — Narrative/EconomicEvidence/MarketBehavior states over time (Speculative Emergence→Narrative-Led Validation→Fundamentally Confirmed→Mature→Decay). **VOCABULARY-ONLY/ENHANCER.**
- §161 **Cross-Theme Contagion Matrix** — learn `P(theme_B activation | theme_A shock)` by state (AI Compute→AI Power→Nuclear→Uranium; Gold→miners→Silver→miners). **CORE-CANDIDATE** — concrete, learnable, complements PART VIII's causal-chain proposal.
- §162 **Theme Causal Distance** — graph-hop count from catalyst; rising average hop-distance of outperformers may mean healthy diffusion OR late-stage stretching (ambiguous without economic-evidence context). **ENHANCER.**
- §163 **Theme Frontier** — newly-activated nodes at the edge of narrative expansion (AI core = GPU/networking; frontier = power transformers/cooling/gas turbines/nuclear fuel) — called "one of the most useful discovery features": "where is the market extending the theme next?" **CORE-CANDIDATE** — distinctive, matches this repo's "find it before they chase it" positioning.
- §164 **Hidden Beneficiary Engine**: `EconomicExposure × CatalystActivation × EvidenceQuality × (1−NarrativeExposure) × (1−MarketRepricing)` — tied to "Mastermind's 'find it before they chase it' product philosophy" (claim about existing product identity — needs-verification, though plausible). **CORE-CANDIDATE.**
- §165 **Narrative Excess Engine**: `NarrativeExcess = NarrativeExposure + TradingExposure − EconomicEvidence`, lifecycle-conditioned (early optionality can justify high narrative excess; late-stage evidence failure cannot). **ENHANCER.**
- §166 Theme Opportunity Matrix — 2×2 UX (attention × fundamental/catalyst quality, quadrants: Dormant/Avoid, Hidden Discovery, Speculative/Fragile, Confirmed Trend/Crowded), extendable with price-extension as a third axis. **ENHANCER/UX.**

**Warnings embedded in this PART:** none explicit — but PART XV later retroactively disciplines this entire PART ("Theme Gravity, Theme Entropy, Narrative R0, Theme Pressure, Hidden Beneficiary, Theme Health" are named *by the memo itself* in §185 as "research hypotheses, not truths" requiring the full validation gauntlet before being trusted).

---

## PART XIII — Full Examples of Organism Thinking (§167–174)

Eight worked narrative examples, not new mechanisms — illustrate how PART IV–XII concepts combine. Two most load-bearing:
- §167 (AI Infrastructure): a top-recognition system watching only the headline leader (NVDA) could wrongly call "AI topping" during a **leadership migration** (Compute→Physical Infrastructure) that the Theme Graph would correctly read as internal rotation within a still-expanding theme. Directly motivates PART V's fragility/lifecycle-over-single-name argument. CORE-CANDIDATE as a falsifiable test case.
- §174 (US→CN Transmission Failure): US solar +10% but China solar auction weak/local-policy-negative next session — a naive cross-market strategy fails; the system should **learn the episode** and require CN local confirmation before weighting future US shocks the same way — a worked example of §187's "history calibrates, LLM doesn't invent" rule. CORE-CANDIDATE.

Remaining six (§168 space US→CN translation, §169 CDE/HL dislocation end-to-end, §170 China sentiment-ice recovery, §171 mania-vs-healthy comparison, §172–173 narrative-leads vs narrative-fails pair) = **ENHANCER** — useful acceptance-test fixtures, not new proposals.

---

## PART XIV — UX Legibility (§175–184)

- §175 Conclusions-with-expandable-evidence tile (STATE/STRENGTH/HEALTH/ATTENTION/FLOW/CROWDING/WHY NOW/WHAT CHANGED TODAY/RISK/NEXT EXPECTED, drill-down) — "do not expose the whole Neural Web by default." **CORE-CANDIDATE** — resonates with this repo's Tier-2 receipt / glance-tier doctrine.
- §176 Every score must answer "why" on click (explicit +/− decomposition) — "never build black-box mystique." **LIKELY-ALREADY-EXISTS** — near-identical to this repo's plain-word null-disclosure law.
- §177 "What changed?" proposed as a **primary product surface** (Market/Themes/Relationships/Attention/Capital/Expectations changed-today digest) — "arguably more useful than another dashboard homepage." **CORE-CANDIDATE.**
- §178 "Why is this moving?" as a native chat-style query, answer grounded in graph traversal (primary driver, confirmation count, secondary driver, capital/participant read, lifecycle stage, risk caveat). **CORE-CANDIDATE** — relevant to Mastermind chat/brain_gateway.
- §179 "What is moving before price?" discovery surface — ranks attention↑/price-flat, flow↑/price-flat, revisions↑/price-flat, catalyst↑/attention-low, evidence↑/narrative-low. **CORE-CANDIDATE.**
- §180 "What is breaking?" inverse surface (price-high/breadth-falling, attention-high/propagation-falling, good-news/weak-response, leader-new-high/secondaries-weak) for risk/top-recognition/short research. **CORE-CANDIDATE.**
- §181 Theme timeline UX (dated event log: catalyst→born→attention accel→breadth expansion→institutional participation→leadership migration→mania warning→distribution). **ENHANCER.**
- §182 Historical Analog Cards must pair similarity % with explicit "important differences," never bare pattern-match. **CORE-CANDIDATE.**
- §183 Confidence needs human-readable decomposition (Evidence coverage/Historical sample/Model agreement/Novelty/Data freshness) instead of a bare percentage — "a precise number without epistemic context is fake certainty." **CORE-CANDIDATE** — matches banned-raw-stats/plain-word disclosure law closely.
- §184 User-facing terms simpler than internal ontology names (`NarrativePropagationAcceleration`→"Story spreading faster"; `CatalystResponseElasticity`→"Good news is producing less upside"). **LIKELY-ALREADY-EXISTS** (matches "Tiers may be named, never explained").

**Flags summary for PART XIV:** the whole PART largely **restates this repo's existing design doctrine** (Tier-2 receipts, plain-word disclosure, banned raw stats/internal names) — treat as confirmatory, not novel. Exception: §177–180 (four proposed *surfaces* — what-changed, why-moving, moving-before-price, what's-breaking) are concrete new product-surface proposals worth evaluating independently.

---

## PART XV — Validation Against Hallucination (§185–195) — DETAILED (house-law-relevant)

The memo's epistemics core, mapping closely onto this repo's existing display-tier/gauntlet law:

- **§185 Every clever metric must earn its place.** Explicitly names its own PART XII coinages (Theme Gravity, Theme Entropy, Narrative R0, Theme Pressure, Hidden Beneficiary, Theme Health) as "research hypotheses, not truths." Required tests before trust: `stability, incremental predictive value, interpretability, cross-era robustness, cross-market robustness, leakage, redundancy`. "If Theme Gravity adds nothing beyond residual correlation and breadth, discard the branding." — This is the memo's own author explicitly pre-disclaiming its PART XII concept-mint. **CORE-CANDIDATE / self-aware guardrail.**
- **§186 Avoid composite-score soup.** Names the exact anti-pattern several of this memo's own formulas fall into (`ThemeScore = 0.1·momentum + 0.1·flow + 0.1·attention + ...` arbitrary weights = "visually satisfying nonsense"). Prescribed order of operations: (1) preserve raw interpretable dimensions, (2) learn conditional relationships, (3) calibrate with history, (4) expose uncertainty; composite scores allowed only as **post-validation** user-facing summaries, never as a substitute for understanding. **This directly indicts §73 (DislocationStrength) and §149/151-153/165 (several PART XII formulas) as needing this exact gauntlet before promotion.**
- **§187 Do not let the LLM invent historical weights.** LLM's job is to propose hypotheses in natural language ("failed-board rate may matter more during sentiment recovery"); a separate research engine backfills/segments-by-regime/tests/walk-forwards/estimates stability; only then does a weight change. **This is essentially a restatement of this repo's own house law "LLMs may only de-escalate calibrated keys — never originate signals, scores, or escalations."** Flag: LIKELY-ALREADY-EXISTS as law here — the memo reinvents it independently, which is a convergence signal worth noting rather than a new rule to adopt.
- **§188 Theme discovery creates severe look-ahead risk.** If "AI power" is discovered as a theme in 2026 and its current constituent list is retroactively applied to 2023 data, it manufactures impossible historical performance. Requires `KnowledgeTime` tracked for: theme existence, constituent membership, evidence, catalyst, analyst coverage. **CORE-CANDIDATE — sharp, concrete, and a very plausible failure mode for any theme-graph backtest.**
- **§189 Survivorship bias is not just a stock-universe problem — themes die too.** Companies disappear, names change, narratives fail; a historical theme study retaining only successful modern themes will exaggerate alpha. Must store failed themes, obsolete themes, delisted constituents, bankrupt companies, temporary narratives. **CORE-CANDIDATE**, and directly resonates with this repo's known trap family around survivorship (ticker-identity, gap-refusal-survivors-are-dead-entities, incomplete-history track records) — likely an area where this repo already has some defenses; verify theme-level (not just ticker-level) survivorship handling specifically, since that's a new angle.
- **§190 Avoid semantic leakage.** A frontier LLM's *general* training knowledge that "Company X eventually became an AI winner" must not be used as admissible evidence when reconstructing a 2022 theme state. Proposed safeguards: retrieve only point-in-time source documents; require cited evidence; separate model general knowledge from admissible historical evidence; validate historical edges deterministically. Explicitly called "one of the hardest problems in AI-assisted historical research." **CORE-CANDIDATE — this is a distinct and sharper failure mode than ordinary look-ahead bias (§188), specific to LLM-in-the-loop historical reconstruction, and is not obviously covered by this repo's existing point-in-time disciplines (which are mostly data-pipeline-level, not LLM-knowledge-level).**
- **§191 Causal stories must be tested against counterfactuals**, not accepted because they're plausible — LLMs are "extremely good at constructing plausible narratives. That is dangerous." Any "X because Y" claim (e.g., "gold rose because real yields fell") must be checked against comparable historical days, alternative drivers (DXY, China demand, positioning), and regime-matched base rates. **CORE-CANDIDATE.**
- **§192 Cross-market correlation is not automatically transmission** — shared catalyst, global risk-on, coincidence, commodity/input link, and direct narrative transmission are all alternative explanations for US/China co-movement; ties back to §116/§117's causal-vs-statistical edge distinction.
- **§193 Validate lifecycle states against actual outcomes** — if "Distribution" doesn't predict a materially different forward-return/drawdown/volatility/breadth-transition distribution than other states, "the label is decorative." Directly actionable acceptance criterion for PART V's fragility state machine.
- **§194 Calibration matters more than classification accuracy** — `P(Expansion)=70%` must actually resolve true ~70% of the time in comparable validated samples; enables position sizing/risk budgeting/expectation management, framed as more valuable than raw hit-rate.
- **§195 Maintain an outcome evaluator** — every important output logged as `Prediction, Horizon, Confidence, Reasoning, State, Outcome, Error`, mined for "which kinds of reasoning fail" — feeds directly into PART XVI's Research Cortex.

**Overall PART XV assessment:** the single most house-law-relevant PART in this range. §187/§186 restate existing house epistemics (convergence signal, not new rule). §188/§189/§190 are the most novel — they identify look-ahead, survivorship, and LLM-knowledge-leakage failure modes at the *theme* level, where this repo's existing point-in-time discipline was built mainly for tickers/factors.

---

## PART XVI — Research Cortex (§196–201)

- §196 Frames a system that **discovers its own missing information architecture** (not "a giant LLM deciding trades") as the potential long-term moat. Worked failure→hypothesis→action examples: gold-miner predictions wrong when Chinese demand diverges → hypothesis "missing China physical/ETF demand" → propose new China gold-demand lobe; biotech theme forecasts break around FDA events → propose FDA-event lobe; semiconductor supplier forecasts fail on hyperscaler capex shifts → propose hyperscaler capex lobe.
- §197 **Hard architectural separation: Operating Cortex vs Research Cortex.** Operating Cortex: interpret current state, retrieve memory, detect contradictions, form hypotheses, issue forecasts, explain conditions — must **NOT freely rewrite production systems**. Research Cortex: inspect systematic errors, identify missing representations, propose candidate features/lobes, design experiments, prioritize research — "prevents a charismatic model from continuously changing the live system based on one anecdote." Maps closely onto this repo's display-tier-vs-promoted-authority gauntlet (LLM proposes/never originates; promotion needs pre-registered gates).
- §198 Research Cortex Loop: `Prediction Failure → Error Clustering → Hypothesis → Possible Missing Variable/Representation → Acquire/Construct Data → Historical Backfill → Replay → Walk-Forward Validation → Stability/Leakage/Redundancy Check → Candidate Improvement → Human/Governance Review → Production` — a formalized restatement of this repo's own gauntlet/promotion pipeline; worth a direct diff against the actual implementation rather than treating as novel.
- §199 Error clustering (by regime/theme/catalyst/market/horizon/capital-mix/novelty/surprise-pattern) framed as more valuable than chasing raw accuracy — worked example: "most false-positive AI continuation calls occur when breadth is high but revision breadth has already rolled over and options speculation is extreme" becomes a new semantic belief.
- §200 Research Cortex can discover **better representations of existing data**, not only acquire new feeds — `sentiment=38` repeatedly failing suggests splitting into `sentiment_level/velocity/acceleration`; `theme return` splits into `theme residual return/breadth/leader dependency`. "Representation learning at the architecture level" — potentially more valuable than adding thousands of feeds.
- §201 "Data Density → Relationship Density → Experience Density → Intelligence" pipeline, self-attributed to earlier memo parts — closing argument: "twenty deeply stateful expert lobes may produce more intelligence than two thousand passive planes" (depth-over-breadth prioritization stance, worth surfacing to planners).

**Flags:** §197, §198 = CORE-CANDIDATE (governance-relevant, likely partially redundant with existing gauntlet); §196, §199, §200 = CORE-CANDIDATE; §201 = VOCABULARY-ONLY.

---

## PART XVII — Data and Evidence Architecture (§202–211) — DETAILED (house-law-relevant)

- **§202 Every observation needs provenance.** Every datum/belief must carry `source, observation_time, knowledge_time, method, confidence, licensing_class, revision_status`. Worked contrast: inferred Northbound-flow direction (`type: inferred, confidence: 0.61`) vs directly-observed SSE turnover (`type: observed, confidence: 1.0`) — explicit fact-vs-inference tagging at the datum level. **CORE-CANDIDATE — this is close to a direct match for this repo's own display-tier vs authority distinction, applied one level lower (per-datum rather than per-signal); worth checking whether the existing provenance/evidence plumbing already does this at the datum level or only at the signal level.**
- **§203 Evidence objects should be first-class graph nodes**, not collapsed into a bare score — instead of storing `Company X → AI Power = 0.83` directly, store the evidence set underneath (filing paragraph, earnings-call statement, contract, capex data, analyst consensus, trading beta, news association) with `Score = aggregation(evidence)`. Stated benefits: auditability, and the ability for a **future, better model to reinterpret old evidence** without re-collecting it. **CORE-CANDIDATE.**
- **§204 Evidence can contradict — design for it, don't net it out.** Worked example: management says AI demand accelerating (positive) + segment revenue unchanged (negative) + capex flat (negative) + options/trading beta high (positive) → correct output is **three separate readings** (`Narrative Exposure: high, Economic Confirmation: low, Market Exposure: high`), not one blended number. "Contradiction is intelligence." **CORE-CANDIDATE — directly actionable design rule for any "alignment" or "confirmation" score in the theme system.**
- **§205 Source reliability should be learned by domain, not hard-coded as a permanent hierarchy.** SEC filing > management interview > sell-side note > financial press > anonymous social post is a *default*, not a law — "a niche specialist may predict a semiconductor supply issue earlier than a formal filing." Track `SourceReliabilityByDomain`, update from outcomes.
- **§206 Five distinct "times" must be tracked**, not collapsed: `Event Time` (when it really happened), `Publication Time` (when the source released it), `Ingestion Time` (when Mastermind received it), `Knowledge Time` (when the system could legitimately know it), `Effective Time` (when it starts affecting fundamentals). Worked example: contract signed June 1, announced June 5, ingested June 5, revenue begins next year — all four (five) matter differently: historical replay needs Knowledge Time, causal modeling needs Effective Time. **CORE-CANDIDATE — more granular than this repo's existing `event_time/knowledge_time/release_time/revision_time` framing from §102; the addition of a distinct `Effective Time` (when a known fact starts mattering causally, as opposed to when it's merely knowable) looks like a genuinely new axis worth checking against existing point-in-time plumbing.**
- **§207 Version every market rule.** `MarketRule{jurisdiction, venue, security_type, effective_from, effective_to}` — historical features must be computed under the rule that existed at that time, not today's rule. Named rule categories: price limits, IPO exceptions, ST regimes, auction mechanics, disclosure policies, Stock Connect dissemination rules.
- **§208 Corporate identity resolution as core infrastructure**, not a data-cleaning afterthought. US: tickers/CUSIPs change, mergers, ADRs, share classes. China: stock names change, ST designations change, restructurings, corporate groups with multiple listed affiliates. "Otherwise historical theme membership and participant behavior become corrupted."
- **§209 Public US data-source baseline (concrete, cite-checkable claims):**
  - **SEC EDGAR** — official APIs expose company submission history + extracted XBRL facts; Form 13F datasets published in structured form. Use: corporate semantic evidence, ownership, insider filings, event history.
  - **FINRA** — publishes short interest + off-exchange short-sale volume/transactions; reiterates short-sale volume ≠ short interest as a required semantic distinction to hard-code.
  - **OCC** — publishes options volume/open-interest reports (account-type + exchange views, historical windows) as a public baseline; richer trade-level classification needs commercial data.
  - **DATA-BLOCKED flag:** all three are asserted as currently *publicly available* (i.e., gettable), not asserted as *already integrated into Mastermind* — needs-verification on integration status specifically, separate from availability.
- **§210 China exchange data as ground truth for rules, with specific dated claims** (external facts, unverified against a primary source by this reader, but presented as current specifics rather than vague background):
  - STAR Market: 20% daily range after the first five IPO trading days; **no regular price limit during those first five days**.
  - ChiNext: same 20%-after-first-five-days structure.
  - Beijing Stock Exchange (BSE): 30% daily price limit under current rules.
  - Stock Connect Northbound real-time buy/sell/total-turnover **dissemination was changed in 2024** — explicit warning: "old-style live Northbound flow assumptions should not be silently carried forward." **This is a concrete, dated, checkable claim — worth flagging for verification since a 2024 protocol change silently breaking an assumed-live data feed is exactly the kind of thing that causes silent production drift.**
  - Recommends prioritizing SSE/SZSE/BSE/HKEX-Stock-Connect official notices, and always using **versioned** official rules.
- **§211 Research data licensing must be treated as architecture, not an afterthought.** A system can be legally allowed to analyze data internally yet be barred from redistributing raw fields to paying users. Proposed per-dataset tags: `InternalAnalysisAllowed, DerivedAnalyticsAllowed, DisplayAllowed, RedistributionAllowed, RetentionLimits, AttributionRequired`. Closing strategic claim: "the moat should increasingly be **derived intelligence** rather than dependence on redistributing vendor raw data." **CORE-CANDIDATE — this is a compliance/product-architecture point with real legal teeth (licensing violations are a business risk, not just a data-quality one) and is distinct from anything else in the memo.**

**Overall PART XVII assessment:** alongside PART XV, the other house-law-critical PART. §202–206 sketch a full evidence-and-time model, more granular than but largely compatible with this repo's existing point-in-time/display-tier disciplines — the clearest net-new pieces are the explicit `Effective Time` axis (§206) and per-dataset licensing tags (§211). §209–210 are checkable external facts, not proposals — verify against primary sources before relying on them, especially the dated 2024 Stock Connect dissemination change.

---

## Consolidated Coined-Concept Glossary (name → definition → §)

| Concept | Definition | § |
|---|---|---|
| Dislocation (redefined) | Price behavior inconsistent with a relationship the system has reason to believe should currently matter | 70 |
| DislocationStrength | ExpectedRelationshipStrength × DeviationMagnitude × ContextValidity × CatalystPersistence × AbsenceOfIdiosyncraticExplanation | 73 |
| FragilityState | Shared state concept linking Theme Lifecycle Engine and Top Recognition Lobe | 75 |
| Theme Fragility State Machine | Healthy→Extended→Accelerating→Saturated→Fragile→Distributing→Failed Continuation→Breakdown | 77 |
| ThemeInternalsDeterioration | Index new highs with narrowing participant new-highs / rising leader return share | 78 |
| ConstituentQualityGradient | Tracks whether new theme outperformers have progressively lower economic/fundamental quality | 79 |
| ThemeWashingRisk | NarrativeExposure − EconomicEvidence | 80 |
| CatalystResponseElasticity | price response / catalyst surprise | 82 |
| AsymmetricNewsElasticity | Ratio of upside-on-good-news to downside-on-bad-news | 83 |
| Market State Tensor | Entity × Horizon × Dimension observation cube | 86 |
| Belief object | Standardized 13-field lobe output incl. Direction/Magnitude/Horizon/Confidence/Provenance/Expected Consequences | 88 |
| Surprise | Observed Outcome − Expected Outcome | 90 |
| Surprise Graph | Propagation of surprise through a causal chain to localize where a model broke | 91 |
| Salience | f(Surprise, Magnitude, Novelty, RelationshipBreak, RegimeTransition, ...) — gates expensive reasoning | 92 |
| Novelty | 1 − max historical similarity | 93 |
| Episodic / Semantic / Procedural Memory | Specific-experience / generalized-belief / behavior-changing memory tiers | 99 |
| KnowledgeTime / evidence_time / belief_time / valid_time | Point-in-time ontology fields preventing look-ahead in theme membership | 102–103 |
| Semantic Bus | Framing of the Theme Graph as connective tissue between lobes, not a lobe itself | 105–106 |
| LeadLagEdge | {source, target, horizon, regime, historical_strength, current_strength} | 115 |
| CausalConfidence / PredictiveStrength | Separated fields — a relationship can be strong-causal/weak-predictive or the reverse | 117 |
| Market Weather Report | Machine-readable per-market snapshot of named qualitative/quantitative fields | 122 |
| SignalReliabilityByState | Per-signal record of which regimes it works/fails in | 126 |
| ThemeConsensusScore | f(#relevant ETFs, weights, manager diversity, theme purity, time persistence) | 128 |
| ManagerThemeExposure | Per-institutional-manager 13F-derived theme fingerprint | 134 |
| Strategy Reinforcement Map | Tracked cohorts (limit-ups, high boards, breakouts, IPOs...) scored for next-session reward | 138 |
| Board-height survival curve | P(survive to n+1 board \| currently n boards) | 139 |
| Auction Surprise | Realized auction state vs overnight-prior expectation | 141 |
| Theme State Vector | Standardized ~21-field per-theme state schema | 147 |
| Theme Strength vs Theme Health | Current force vs durability/internal quality — two parallel scores | 148 |
| ThemePressure | unrealized drivers − priced-in saturation | 149 |
| Potential Energy vs Realized Motion | 2×2 discovery-stage matrix | 150 |
| NarrativeCapitalConversion | Δflow / Δattention | 151 |
| CapitalPriceConversion | Δprice / Δflow | 152 |
| InfoPriceElasticity | abnormal return / information surprise | 153 |
| Theme Reflexivity Score | Price→attention→flow→price feedback-loop strength + direction | 154 |
| Fragility Surface | Per-shock-type fragility vector (rates/liquidity/policy/earnings/commodity/leader-failure) | 155 |
| StateEntropy | Disagreement/ambiguity about current theme state, treated as itself informative | 157 |
| AttentionEfficiency | fundamental information generated / total attention | 158 |
| EvidenceVelocity | Rate at which hard evidence catches up to narrative | 159 |
| Theme Legitimacy Curve | Speculative Emergence→Narrative-Led Validation→Fundamentally Confirmed→Mature→Decay | 160 |
| Theme Causal Distance | Graph-hop count from catalyst (Direct/1-hop/2-hop/3-hop) | 162 |
| Theme Frontier | Newly-activated nodes at the edge of narrative expansion | 163 |
| Hidden Beneficiary (score) | EconomicExposure × CatalystActivation × EvidenceQuality × (1−NarrativeExposure) × (1−MarketRepricing) | 164 |
| Narrative Excess | NarrativeExposure + TradingExposure − EconomicEvidence | 165 |
| Operating Cortex vs Research Cortex | Interpret-and-forecast (no self-rewrite) vs propose-and-govern-improvements | 197 |
| Research Cortex Loop | Failure→ErrorClustering→Hypothesis→Data→Backfill→Replay→WalkForward→StabilityCheck→Review→Production | 198 |
| Data Density → Relationship Density → Experience Density → Intelligence | Closing prioritization pipeline | 201 |
| Five-way time semantics | Event / Publication / Ingestion / Knowledge / Effective Time | 206 |
| MarketRule | {jurisdiction, venue, security_type, effective_from, effective_to} | 207 |
| Licensing tags | InternalAnalysisAllowed / DerivedAnalyticsAllowed / DisplayAllowed / RedistributionAllowed / RetentionLimits / AttributionRequired | 211 |

---

## Cross-cutting explicit warnings / "do not build" items (all §)

1. §72 — Do not label every price drop an "overreaction"; require active search for invalidating evidence.
2. §85 — Do not collapse world state prematurely to Risk-On/Risk-Off.
3. §97 — Do not replace robust mathematics with eloquent language generation (LLM = scientist, not calculator).
4. §131 — Do not present inferred "smart money" labels as direct facts; retain raw/vendor/inference provenance split.
5. §133 — Do not call a 13F change "today's smart-money buying" (quarterly-lagged, not live).
6. §136 — Do not conflate short-sale volume with short interest; "a false 'short pressure' label would poison the graph."
7. §145 — Do not assume monotonic attention↑→return↑; effects reverse by investor type/lifecycle.
8. §185 — Do not fetishize a metric's branding; every clever name needs stability/predictive-value/interpretability/robustness/leakage/redundancy testing before trust.
9. §186 — Do not build arbitrary-weight composite scores ("visually satisfying nonsense"); preserve raw dimensions, learn conditional relationships, calibrate historically, expose uncertainty.
10. §187 — Do not let the LLM invent historical weights; it proposes, a research engine calibrates from backtested history.
11. §188 — Do not retroactively apply today's theme constituents to historical dates (look-ahead via theme discovery).
12. §189 — Do not build theme-history datasets that only retain surviving/successful themes.
13. §190 — Do not let an LLM's general/future training knowledge leak into point-in-time historical theme reconstruction ("semantic leakage").
14. §191 — Do not accept a causal narrative because it's plausible; LLMs generate convincing stories cheaply — test against counterfactuals.
15. §192 — Do not treat cross-market correlation as proof of transmission.
16. §193 — Do not keep a lifecycle-state label whose forward-outcome distribution doesn't differ from other states ("decorative").
17. §197 — Operating Cortex must NOT freely rewrite production systems from one anecdote; only Research Cortex (with governance review) can propose changes.
18. §210 — Do not silently carry forward old live-Northbound-flow assumptions after the 2024 Stock Connect dissemination change; version all market rules.
19. §211 — Do not redistribute vendor raw data without checking licensing tags; the moat should be derived intelligence, not raw redistribution.
