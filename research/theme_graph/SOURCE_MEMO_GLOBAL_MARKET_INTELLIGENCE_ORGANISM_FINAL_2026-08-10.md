# Mastermind Global Market Intelligence Organism

## Final Deep-Research Brainstorming, Strategic Synthesis, and Architecture Handoff

**Status:** Final ideation handoff for Claude/Fable assessment, challenge, planning, and eventual build-out  
**Scope:** United States + China A-shares as one global intelligence project, with market-specific organs rather than false uniformity  
**Nature of this document:** Research notebook / strategic whitepaper / conceptual architecture — **not** a compressed executive summary and **not** a PRD

---

# Handoff Directive to the Next AI Session

This document is deliberately expansive.

Do **not** reduce it immediately into tickets, schemas, microservices, or a conventional implementation roadmap. The point of this handoff is to preserve the conceptual landscape before engineering compression destroys useful ideas.

The next session should first understand the system as a whole:

1. challenge the concepts;
2. identify which ideas reinforce each other;
3. distinguish useful metaphors from measurable constructs;
4. assess which concepts are genuinely differentiated;
5. identify data or validation bottlenecks;
6. only then translate the strongest ideas into architecture and build phases.

The central discovery behind this project is not “we should add more theme baskets” and not “we should clone 同花顺.”

It is much larger:

> **Mastermind can evolve from a collection of powerful market sensors and deterministic engines into a persistent market intelligence organism that models the state of the world, understands the semantic and causal relationships connecting assets, remembers prior market experiences, notices when reality violates expectations, and continuously improves how it interprets new information.**

The 同花顺 study matters because it exposes an unusually rich **market sensorium** for China.

The Dynamic Theme Graph work matters because it exposes the inadequacy of sector taxonomies and suggests a living **economic/narrative/trading ontology**.

The Neural Web matters because it supplies the persistent **world model, memory, attention, and reasoning architecture** capable of making all of those signals mean something together.

Prophet matters because it turns the world model into **probabilistic expectations and opportunity rankings**.

Historical replay matters because it can potentially give this organism something approximating **synthetic lived market experience** rather than forcing it to learn one day at a time.

Everything in this document should be read as part of that single idea.

---

# Executive Synthesis

## 1. The Correct Strategic Decision: Amalgamate the US and China Projects

The US Dynamic Theme Graph and the China 同花顺 intelligence project should become **one project at the level of cognition**, but **not one homogeneous feature set**.

The correct abstraction is:

```text
                 GLOBAL MARKET INTELLIGENCE ORGANISM
                               │
                ┌──────────────┴──────────────┐
                │                             │
        UNIVERSAL COGNITIVE CORE       MARKET-SPECIFIC ORGANS
                │                             │
     themes / narratives / memory      US              China
     state / causality / surprise      │                 │
     dislocations / prediction       options          涨跌停生态
                                     ETFs             龙虎榜
                                     13F              游资
                                     earnings         竞价
                                     analysts         连板
                                     shorting         政策资金
```

The markets are different in their microstructure, participants, regulatory rules, information channels, and dominant behavioral signals.

But the **questions** are remarkably similar:

- What is moving?
- Why is it moving?
- Is the move broad or narrow?
- What capital is driving it?
- What story is spreading?
- Which companies are genuine beneficiaries versus speculative proxies?
- Where is the theme in its lifecycle?
- What changed from yesterday?
- What changed unexpectedly?
- Which historical episodes are structurally similar?
- What is different this time?
- What should happen next if our interpretation is correct?
- Where is price violating the relationships implied by the rest of the system?

That common question set is the cognitive core.

The market-specific modules are the sensory organs.

---

## 2. Why the Project Is Larger Than Theme Classification

The attached US thematic research correctly begins with a classification problem: GICS answers **“what industry does this company primarily belong to?”**, whereas modern investors need to know what economic forces, narratives, technologies, supply chains, and capital flows a company is exposed to.

That is the starting point, not the destination.

Once a theme becomes a persistent Neural Web object, the system can attach:

- business exposure;
- market-perceived exposure;
- realized trading exposure;
- supply-chain position;
- catalysts;
- earnings revisions;
- capital flows;
- attention;
- leadership;
- breadth;
- valuation;
- crowding;
- participant behavior;
- historical analogues;
- lifecycle state;
- causal parents and children;
- expected outcomes;
- surprises;
- learned reliability.

At that point a “theme” is no longer a label.

It has become a **memory-bearing market entity**.

And once themes interact with macro states, commodities, policy, companies, participants, options, flows, and other themes, the Theme Graph becomes the **semantic connective tissue of the Neural Web**.

---

## 3. Why 同花顺 Is Such a Useful Inspiration

The most valuable thing visible in the 同花顺 screenshots is not any single proprietary score.

It is the product's implicit worldview.

The application treats the A-share market as an ecology in which you simultaneously observe:

- index direction;
- advancing and declining stocks;
- turnover;
- prior limit-up cohort behavior;
- limit-ups and limit-downs;
- concept/theme performance;
- theme popularity;
- fund flows;
- ETFs;
- 龙虎榜 participants;
- abnormal large trades;
- valuations;
- macro liquidity;
- FX;
- futures;
- commodities;
- news;
- and sentiment.

That is effectively a **real-time market observability layer**.

同花顺 primarily leaves the synthesis to the human.

Mastermind should ingest the same categories of evidence, normalize them into machine-readable beliefs and states, and ask:

> **What do all of these observations collectively imply?**

That is the jump from market terminal to market cognition.

---

## 4. The Nervous System → Brain Analogy

The cleanest mental model from the original brainstorming remains useful.

### 同花顺-like system: nervous system

```text
price sensor ─────┐
flow sensor ──────┤
news sensor ──────┤
sentiment sensor ─┼──> human trader must synthesize
theme sensor ─────┤
龙虎榜 sensor ────┤
macro sensor ─────┘
```

### Mastermind: nervous system + world model + memory + cortex

```text
SENSORS
   ↓
NORMALIZED BELIEFS
   ↓
PERSISTENT WORLD STATE
   ↓
SALIENCE / ATTENTION
   ↓
MEMORY RETRIEVAL
   ↓
CAUSAL + ANALOGICAL REASONING
   ↓
PROBABILISTIC EXPECTATION
   ↓
REALIZED OUTCOME
   ↓
SURPRISE
   ↓
LEARNING
```

The central cognitive loop from prior Neural Web work should be retained almost verbatim as a governing idea:

```text
SENSE
  → UNDERSTAND
  → REMEMBER
  → NOTICE
  → THINK
  → PREDICT
  → EXPERIENCE
  → LEARN
  → IMPROVE HOW YOU SENSE
```

Mastermind already has unusually strong **SENSE** and meaningful **PREDICT** capability.

The largest architectural frontier is increasingly:

- UNDERSTAND
- REMEMBER
- NOTICE
- EXPERIENCE
- LEARN

This Theme/同花顺 synthesis is powerful precisely because it can fill those missing layers.

---

# PART I — WHY STATIC MARKET TAXONOMIES FAIL

# 5. GICS Is Not Wrong. It Solves the Wrong Problem.

A common mistake would be to argue that GICS, ICB, or exchange industry classifications are obsolete.

They are not.

They are excellent for what they were designed to do:

- index construction;
- portfolio reporting;
- broad exposure control;
- accounting consistency;
- industry comparison;
- benchmark decomposition.

The issue is objective-function mismatch.

An investor trying to understand **AI infrastructure buildout** does not see:

```text
Nvidia               → Semiconductors
Arista                → Communications Equipment
Vertiv                → Electrical Equipment
Eaton                 → Electrical Equipment
Constellation Energy  → Utilities
Quanta Services       → Construction & Engineering
Micron                → Semiconductors
```

The investor sees:

```text
                      AI CAPEX SUPER-CYCLE
                              │
         ┌────────────────────┼──────────────────────┐
         │                    │                      │
      COMPUTE             NETWORKING              POWER
         │                    │                      │
       GPU/HBM            switches/CPO       generation/grid
         │                    │                      │
         └────────────── DATA CENTERS ──────────────┘
                              │
                           COOLING
                              │
                         CONSTRUCTION
```

This is not an industry.

It is an **economic transmission system**.

The same applies to:

- commercial space;
- nuclear renaissance;
- GLP-1;
- missile defense;
- grid modernization;
- copper electrification;
- memory super-cycles;
- critical minerals;
- humanoid robotics;
- sovereign AI;
- data-center power scarcity;
- stablecoins;
- drone warfare.

The securities market continuously creates cross-industry economic groupings faster than formal taxonomies can update.

Therefore Mastermind needs a layer **above** industries rather than a replacement for industries.

---

# 6. Institutional Research Validates the Problem

External research strongly validates the broad direction.

Theia Insights describes its system as a dynamic, one-to-many classification rather than a single-label taxonomy. Its current materials describe 245 major themes and more than 3,200 microthemes across five taxonomy tiers, with business activity inferred not only from revenue but also products/services, R&D and CapEx, target markets, use cases, partnerships, and acquisitions.

Theia's Theme Watch Indices track more than 200 themes across regions and are explicitly positioned for observing market rotations and capital-flow trends.

S&P Dow Jones Indices now collaborates with Theia on a thematic dashboard covering 200+ themes. S&P Kensho separately uses NLP and machine learning on public company documents to build thematic indices around emerging technologies and “new economies.”

MSCI's thematic work similarly uses NLP/LLM techniques and segment-level economic information to estimate company relevance to investment themes. Morningstar uses analyst assessments of future revenue and net-profit impact and also has a market-consensus approach based partly on thematic fund holdings.

These systems prove several things:

1. **Multi-label classification is not a fringe idea.**
2. **Granular thematic exposure has institutional value.**
3. **Text + economic evidence is now a legitimate way to build market taxonomies.**
4. **Thematic indices can be treated as quantitative objects, not merely analyst narratives.**
5. **There is no need for Mastermind to invent the category from zero.**

But they do **not** eliminate the Mastermind opportunity.

They clarify it.

---

# 7. Theia's Objective Function vs Mastermind's Objective Function

The attached US memo arrived at an important distinction:

> Theia is building a universal economic ontology.  
> Mastermind should build a trading intelligence ontology.

That distinction should remain foundational.

Theia wants to answer:

> “Who does what, by how much?”

Mastermind ultimately wants to answer:

> “What does the market currently believe matters, how is capital reacting, how reliable is that relationship, and what opportunity does it imply?”

Those objectives overlap, but they are not identical.

Consider a hypothetical company:

```text
Economic exposure to orbital computing:      12%
Narrative exposure to orbital computing:     82%
Trading beta to orbital-compute basket:      91%
Revenue materiality in next 12 months:         low
Long-run optionality:                         high
Retail attention acceleration:             +3.1σ
Institutional participation:                 low
```

A conventional thematic index provider may correctly assign modest economic weight.

A trading-intelligence system must notice:

> **The stock is currently functioning as a high-beta market proxy for the narrative despite weak near-term economic purity.**

That mismatch is not noise to discard.

It is potentially the most interesting information.

---

# 8. Three Realities Are the Minimum, Not the Maximum

The prior Dynamic Theme Graph memo introduced three independent dimensions:

## 8.1 Business Reality

What does the company economically do?

Examples of evidence:

- revenue segments;
- products and services;
- disclosed contracts;
- CapEx;
- R&D;
- customer exposure;
- acquisitions;
- partnerships;
- capacity additions;
- management guidance.

Call this:

```text
E_business(company, theme, t)
```

## 8.2 Narrative Reality

What does the market currently believe this company represents?

Possible evidence:

- financial news;
- analyst language;
- earnings-call topic emphasis;
- social-media association;
- search behavior;
- theme lists;
- fund holdings;
- investor presentations;
- repeated co-mentions.

Call this:

```text
E_narrative(company, theme, t)
```

## 8.3 Trading Reality

Does the security actually trade like the theme?

Possible evidence:

- return correlation;
- residual return correlation after market/sector controls;
- beta to theme factor;
- synchronized volume;
- options-flow co-movement;
- relative reaction to theme catalysts;
- cross-sectional leadership;
- ETF flow sensitivity.

Call this:

```text
E_market(company, theme, t)
```

These three dimensions are essential.

But the combined project suggests several additional dimensions worth keeping separate.

---

# 9. Add Temporal Reality

A company's theme exposure is not stationary.

Example:

```text
Amazon 1999  → e-commerce
Amazon 2010  → e-commerce + logistics
Amazon 2016  → AWS/cloud
Amazon 2024+ → cloud + AI infrastructure + advertising + logistics
```

The graph therefore must preserve:

```text
ThemeEdge {
    valid_from
    valid_to
    observed_at
    confidence_at_time
    evidence_available_at_time
}
```

This is not merely a database convenience.

It is critical for:

- honest historical backtests;
- reconstructing what investors knew then;
- avoiding today's ontology leaking into yesterday;
- studying how corporate identity changes;
- detecting theme migration early.

A static 2026 label attached retrospectively to 2018 data will create counterfeit predictive power.

---

# 10. Add Catalyst Reality

A company can be economically exposed to a theme without having a current catalyst.

Therefore distinguish:

```text
StructuralExposure
CatalystActivation
```

Example:

Many defense companies have permanent missile-defense exposure.

But a new Golden Dome procurement announcement may suddenly activate that exposure.

Possible Catalyst Activation components:

- recency;
- economic materiality;
- specificity to company;
- surprise;
- probability of monetization;
- time to revenue;
- confirmation from procurement/capex data.

This creates a much more tradeable representation:

> **Exposure tells us who can benefit. Catalyst activation tells us why now.**

---

# 11. Add Supply-Chain Position

Theme membership is insufficient if the graph cannot understand **where** the company sits in the transmission chain.

For every theme/company edge, potentially track roles:

```text
Enabler
Input Supplier
Critical Bottleneck
Manufacturer
Platform
Distributor
Customer
Beneficiary
Substitute
Competitor
Hedge / Loser
```

This enables causal propagation.

Example:

```text
Hyperscaler AI CapEx ↑
      ↓
GPU demand ↑
      ↓
HBM demand ↑
      ↓
advanced packaging demand ↑
      ↓
power density ↑
      ↓
liquid cooling demand ↑
      ↓
data-center electricity demand ↑
      ↓
grid / generation bottlenecks ↑
```

Without supply-chain role, this is a basket.

With supply-chain role, it is a **causal network**.

---

# 12. Add Market-Perceived Role

Within the same theme, securities play very different trading roles.

Mastermind should infer roles such as:

```text
Fundamental Anchor
Narrative Flagship
Momentum Leader
Liquidity Leader
First Mover
Confirmation Stock
Upstream Bottleneck
Secondary Beneficiary
Sympathy Proxy
Late Follower
Laggard
False Association
```

This matters because theme breadth should not be naïvely counted.

If a flagship rises 10% while 40 “members” do nothing, the theme may be fragile.

If the flagship rises 6%, the bottleneck suppliers rise 5%, the median constituent rises 3%, and previously ignored secondaries begin breaking out, the theme is undergoing **diffusion**.

That is a completely different state.

---

# PART II — REVERSE ENGINEERING 同花顺 AS A MARKET SENSORIUM

# 13. What the Screenshots Actually Teach

The screenshots collectively suggest that 同花顺's true strength is **market-state compression**.

A trader can move from:

```text
MARKET
  ↓
SENTIMENT
  ↓
THEME
  ↓
FLOW
  ↓
STOCK
  ↓
PARTICIPANT
  ↓
EVENT
```

without leaving the environment.

The product is effectively asking the human brain to synthesize:

> “What is the market doing, what is hot, where is money going, and who is involved?”

Mastermind should retain the observational richness while changing the final consumer of the data.

The consumer should increasingly be the Neural Web itself.

---

# 14. Build a Persistent A-Share Market State Object

The original brainstorming proposed a `ChinaMarketState`. It should be treated as a persistent world-state node rather than a dashboard snapshot.

Conceptually:

```text
ChinaMarketState {
    index_structure
    breadth
    turnover
    liquidity
    speculation
    limit_up_ecology
    theme_rotation
    attention
    flow
    participant_mix
    valuation
    policy_liquidity
    rates
    FX
    offshore_futures
    cross_market_context
    regime_probabilities
    anomalies
    expectations
}
```

Each field should contain more than a current level.

Persistent state means:

```text
current value
+ trajectory
+ velocity
+ acceleration
+ percentile
+ relationships
+ prior expectation
+ surprise
+ historical reliability
```

So instead of:

> Daily turnover = X

the system stores:

> Turnover has risen for four sessions, is now in the 91st historical percentile, is concentrating into five concept groups, and the increase is being accompanied by lower failed-board rates and stronger median-stock returns.

That is a **belief about the market**, not a number.

---

# 15. Market Direction and Market Quality Must Be Separate

A major extension beyond the screenshots should be a distinction between:

## Direction

Are index prices rising?

## Quality

How internally healthy and durable is the move?

Possible Market Quality components:

- breadth;
- equal-weight vs cap-weight confirmation;
- leader participation;
- median-stock return;
- new highs vs new lows;
- theme breadth;
- turnover distribution;
- failed-board behavior;
- leadership renewal;
- cross-sectional correlation;
- concentration;
- flow confirmation;
- volatility structure.

This allows:

> **CSI 300 +1.3%, but Market Quality fell 11 points because breadth narrowed, prior leaders broke down, and turnover concentrated into a handful of index heavyweights.**

That is far richer than “market up.”

The inverse also matters:

> **Index flat, but Market Quality improved sharply because median returns, speculative breadth, and theme participation broadened.**

That can be an early regime-transition signal.

---

# 16. Breadth Should Be Multi-Scale

Do not reduce breadth to advance/decline.

Potential layers:

```text
Market Breadth
    % advancing
    median return
    % > 20DMA / 50DMA / 200DMA
    new highs / new lows
    return distribution skew

Theme Breadth
    % theme members advancing
    % theme members making new highs
    median theme member return
    leader contribution

Catalyst Breadth
    number of related beneficiaries reacting

Limit-Up Breadth
    number reaching limit
    number sealing
    number resealing
    board-height distribution

Attention Breadth
    number of companies gaining attention
```

A broadening move and a narrowing move should be recognized as different organisms.

---

# 17. Sentiment Temperature Is Not a Toy Gauge

同花顺's 冰点 → 过冷 → 微冷 → 微热 → 过热 → 沸点 presentation looks simple.

The underlying concept is strategically strong.

It compresses a complex speculative ecology into an intuitive state.

Mastermind should rebuild the concept quantitatively rather than reverse-engineer their proprietary formula.

Potential components:

```text
advancing / declining ratio
median stock return
limit-up count
limit-down count
failed-limit rate
reseal rate
highest 连板
prior-limit-up premium
prior-leader premium
% stocks > +5%
% stocks < -5%
turnover percentile
small-cap relative strength
theme breadth
opening-gap follow-through
new-high / new-low ratio
龙虎榜 activity
margin activity
retail attention
```

The important output is **not** only:

```text
Sentiment = 37 / 100
```

It is:

```text
Level:          37
Velocity:       +8.2 / day
Acceleration:   positive
Regime:         冰点 recovery
Days in state:  2
Transition:
    P(微热 within 3 sessions)  41%
    P(relapse)                 27%
```

The derivative can be more predictive than the level.

A market moving:

```text
18 → 25 → 34
```

may be more attractive than:

```text
82 → 77 → 70
```

even though the latter still looks “hot.”

That is a general principle for the entire architecture:

> **State transitions often matter more than state labels.**

---

# 18. Build a Speculation Ecology, Not One Sentiment Number

A-shares have a specific speculative microstructure that deserves its own lobe.

Possible `SpeculationEcologyState`:

```text
limit_up_count
limit_down_count
first_board_count
second_board_count
3+ board_count
maximum_board_height
board_survival_curve
first_touch_time_distribution
seal_strength
seal_break_count
reseal_probability
failed_board_return
previous_day_limit_up_premium
previous_day_high_board_premium
high_attention_smallcap_return
turnover_concentration
```

Why this matters:

A 70-limit-up day where 60 are first boards, most seal late, and prior leaders lose money is different from a 70-limit-up day where yesterday's leaders gap strongly, high boards survive, seals are early and durable, and themes show internal propagation.

The count is the same.

The **ecology is opposite**.

---

# 19. Price-Limit Rules Must Be Board-Aware

One important correction to simplistic A-share statistics: raw return extremes are not comparable across boards.

As of 2026, exchange rules still differ materially. Shanghai Main Board stocks generally use 10% price limits, STAR Market uses 20% after its no-limit initial listing period, and Beijing Stock Exchange uses 30%. Special-treatment securities and IPO/no-limit periods require additional handling. Exchange rules can change, so the rules engine should be versioned through time.

Therefore every event should be normalized to the applicable market structure:

```text
NormalizedMove =
    realized move / applicable daily range
```

and every limit event should know:

```text
board
rule_version
limit_percentage
IPO_status
ST_status
no_limit_status
```

Otherwise a 19% ChiNext move and a 9.8% Main Board move are statistically misinterpreted.

This is especially important for historical training.

---

# 20. Limit-Up Is a Sequence, Not a Boolean

One of the richest extensions from 同花顺 is to stop representing 涨停 as:

```text
limit_up = true
```

Instead represent the intraday path:

```text
09:31   first acceleration
09:46   first touch
09:47   seal
10:13   break
10:17   reseal
14:52   sell pressure
15:00   closed sealed
```

Derived concepts:

- time to first touch;
- velocity into touch;
- order-wall size at touch;
- wall persistence;
- wall-to-free-float ratio;
- number of breaks;
- time spent unsealed;
- reseal latency;
- closing seal;
- post-touch turnover;
- peer behavior before/after touch;
- theme propagation after first leader sealed.

This converts a crude event into a microstructure episode.

It also connects directly to the user's existing interest in:

- closing-auction imbalance;
- 封单 order-wall size;
- first-touch time.

Those fields are not ornamental. They can become training features for:

- next-day premium;
- leader survival;
- theme continuation;
- failed-board risk;
- contagion probability.

---

# 21. “Yesterday's Limit-Up Cohort” Is a Hidden State Variable

同花顺 surfaces prior limit-up cohort performance for a reason.

It answers:

> **Is speculative capital being rewarded for yesterday's risk-taking?**

That is analogous to measuring whether a strategy is currently “paying.”

If yesterday's limit-ups:

- gap up;
- hold;
- generate new boards;
- produce strong median returns;

then momentum participants are receiving reinforcement.

If they:

- gap down;
- fail;
- break boards;
- underperform the market;

speculative capital is being punished.

This can become:

```text
SpeculativeRewardRate
```

Potential dimensions:

```text
T+1 open premium
T+1 close return
T+1 board recurrence
T+2 survival
leader survival
drawdown after entry
```

It is not just sentiment.

It is the **reinforcement schedule of the market**.

That phrase is useful: markets condition behavior by rewarding or punishing recent strategies.

Mastermind should measure which behaviors are currently being reinforced.



# 22. 热点板块 Should Become a Dynamic Theme-State Engine

The 同花顺 hotspot interface is much more than a list of sectors.

It exposes a useful market habit:

> **Observe the same theme through several independent lenses.**

The screenshots show ideas such as:

- today's return;
- largest fund inflow;
- multi-day performance;
- heat / popularity;
- speed;
- volume ratio;
- limit-up count.

That should be interpreted as a prototype of a `ThemeState`, not a set of columns.

For every theme:

```text
ThemeState {
    price
    breadth
    liquidity
    flow
    attention
    leadership
    catalyst
    fundamentals
    valuation
    crowding
    participant_mix
    cross_asset_confirmation
    lifecycle
}
```

And each component should contain multiple horizons and derivatives.

Example:

```text
Commercial Space

Price:
    intraday return             +3.6%
    5D relative strength        92nd pct
    price acceleration          +1.4σ

Breadth:
    advancers                   81%
    > morning high              63%
    new breakouts               7

Flow:
    active-buy imbalance        +2.1σ
    ETF / basket flow           positive
    flow acceleration           rising

Attention:
    heat rank                   72 → 31 → 8
    mention velocity            +2.8σ

Leadership:
    leader dependency           moderate
    secondaries broadening      yes

Catalyst:
    policy / contract           active

Lifecycle:
    Discovery → Expansion

Crowding:
    61 / 100

Historical continuation:
    conditional T+3 favorable
```

This is not merely a better theme dashboard.

It is a standardized **theme belief object** that can feed every other Mastermind system.

---

# 23. Heat Is Valuable; Heat Acceleration Is More Valuable

The screenshot's 热度 concept is behaviorally interesting because attention is a scarce resource.

A stock or theme does not need to be fundamentally changed for its probability distribution to change if it suddenly enters the attention set of millions of traders.

Research on Chinese equities supports taking this seriously. Studies using Baidu search volume find that abnormal attention is associated with contemporaneous price and trading-volume effects, while some of the price effect subsequently reverses. Account-level research also finds meaningful heterogeneity among Chinese retail investors: smaller accounts tend to exhibit momentum, weaker public-news processing, and more gambling-like behavior, while larger retail accounts behave more contrarian and predict returns better.

This does **not** mean:

> “High attention = buy.”

It means attention should be modeled as an independent state dimension.

For a theme, track:

```text
AttentionLevel
AttentionVelocity
AttentionAcceleration
AttentionPersistence
AttentionBreadth
AttentionConcentration
AttentionSourceMix
```

Then create divergences.

### Early-discovery pattern

```text
Price                   +0.8%
Attention               +2.7σ
Attention breadth       expanding
Flow                    beginning to turn positive
```

Potential interpretation:

> Narrative discovery may be occurring before broad repricing.

### Late-euphoria pattern

```text
Price                   +18% over 5D
Attention               extreme
Attention velocity      decelerating
Breadth                 narrowing
Flow                    flattening
```

Potential interpretation:

> The market may be consuming the last incremental attention rather than attracting new participants.

### Hidden accumulation pattern

```text
Price                   flat
Attention               moderate
Institutional flow      strong
Retail heat             low
```

Potential interpretation:

> Potential stealth accumulation rather than a narrative chase.

The system should care about the **shape of attention**.

---

# 24. Narrative Breadth and Price Breadth Should Be Separate

This distinction can produce an early-warning system for thematic diffusion.

## Price Breadth

How many stocks are already moving?

## Narrative Breadth

How many stocks are increasingly being *identified* as beneficiaries?

Narrative breadth can lead price breadth.

Example:

```text
Day 0:
    Government announces satellite initiative.

Day 1:
    media focuses on launch companies.

Day 2:
    analysts identify satellite manufacturers.

Day 3:
    research expands to power systems, solar, optics and materials.

Day 4:
    social attention broadens.

Day 5:
    previously ignored suppliers begin moving.
```

Mastermind should track:

```text
NewThemeAssociations_t
```

and distinguish:

```text
SemanticDiffusion
vs
PriceDiffusion
```

A widening gap in which semantic diffusion leads price diffusion may be a discovery signal.

The reverse can also be useful.

If price breadth explodes but no durable economic/narrative explanation emerges, the move may be:

- pure liquidity;
- speculative contagion;
- short covering;
- index mechanics.

That should lower confidence in persistence.

---

# 25. The 异动 Feed Should Become an Event Nervous System

The 同花顺 unusual-move feed is one of the most important ideas in the screenshots.

Instead of forcing the Cortex to scan millions of continuously changing observations, deterministic detectors should convert abnormal behavior into **events**.

Potential event vocabulary:

```text
LARGE_ACTIVE_BUY
LARGE_ACTIVE_SELL
VOLUME_SPIKE
TURNOVER_SPIKE
PRICE_ACCELERATION
PRICE_REVERSAL
VOLATILITY_EXPANSION
NEW_INTRADAY_HIGH
BREAKOUT
FAILED_BREAKOUT

LIMIT_UP_FIRST_TOUCH
LIMIT_UP_SEAL
LIMIT_UP_BREAK
LIMIT_UP_RESEAL
LIMIT_DOWN_TOUCH

AUCTION_IMBALANCE
CLOSING_AUCTION_SHIFT
ORDERBOOK_IMBALANCE
LIQUIDITY_VACUUM

THEME_BREADTH_EXPANSION
THEME_SYNCHRONIZATION
THEME_LEADER_BREAKOUT
THEME_LEADER_FAILURE
THEME_CONTAGION

FLOW_REVERSAL
ETF_CREATION_SPIKE
MARGIN_ACCELERATION

PEER_DIVERGENCE
INDEX_DIVERGENCE
CROSS_ASSET_DIVERGENCE
EXPECTED_RELATIONSHIP_BREAK
```

Each event should contain:

```text
Event {
    entity
    timestamp
    event_type
    magnitude
    z_score
    historical_percentile
    persistence
    market_context
    theme_context
    participant_context
    causal_candidates
    related_events
    confidence
    provenance
}
```

The Neural Web's cortex should not be asked to “watch everything.”

It should be **woken up by meaningful state changes**.

This is directly compatible with prior Neural Web architecture, where the deliberative Cortex should activate because something happened:

- NFP;
- CPI;
- a 2σ yield move;
- sector breadth explosion;
- strong lobe disagreement;
- correlation break;
- abnormal peer behavior;
- a regime shift;
- or a major news event.

Eventization makes that architecture tractable.

---

# 26. Event Clusters Are More Interesting Than Single Events

A single large buy may be meaningless.

Seven related events within 90 seconds may be structurally important.

Create event clustering:

```text
10:14:07   SPACE_LEADER_BREAKOUT
10:14:18   THEME_BREADTH +12 pts
10:14:29   LARGE_ACTIVE_BUY supplier A
10:14:41   LARGE_ACTIVE_BUY supplier B
10:14:53   options / warrants activity rises
10:15:11   theme turnover acceleration +2σ
```

This should compress into a higher-order event:

```text
THEME_IGNITION_CLUSTER
Theme: Commercial Space
Confidence: High
```

This is analogous to a nervous system recognizing that several sensory inputs represent **one underlying event**, rather than independently reporting each twitch.

---

# 27. 龙虎榜 Should Become a Participant Intelligence Graph

同花顺 already surfaces and labels participant categories such as:

- 一线游资;
- 敢死队;
- institutions.

The natural Mastermind extension is to treat participants as persistent entities.

Conceptually:

```text
ParticipantNode {
    identity / seat
    inferred participant type
    historical transactions
    preferred themes
    preferred market caps
    entry timing
    average holding horizon
    follow-through profile
    success distribution
    risk appetite
    catalyst preference
    momentum / reversal bias
    crowding sensitivity
}
```

This enables questions such as:

> Which participants are repeatedly early to themes?

> Which seats are excellent at first-wave momentum but poor at late-stage continuation?

> Which institutions tend to accumulate before earnings revision cycles?

> Which participants co-occur?

> Which participants repeatedly sell into retail attention peaks?

The graph becomes:

```text
PARTICIPANT
    │ buys
    ↓
  STOCK
    │ belongs to
    ↓
  THEME
    │ driven by
    ↓
 CATALYST
```

And:

```text
Participant A ↔ Participant B
```

can carry edges based on:

- repeated co-occurrence;
- synchronized entries;
- apparent leader/follower behavior;
- theme similarity;
- opposite-side behavior.

---

# 28. Participant Identity Should Be Probabilistic

Do not overstate what 龙虎榜 or brokerage-seat data reveals.

A brokerage seat is not always one human.

An institutional label can aggregate heterogeneous capital.

Therefore use:

```text
ObservedEntity
InferredActorType
Confidence
```

rather than:

```text
Seat X = Trader Y
```

The point is behavioral fingerprinting, not storytelling.

This also generalizes to the US.

A 13F holder, ETF complex, insider, options cohort, or systematic flow does not reveal a perfect causal actor.

It reveals **evidence about participant classes**.

---

# 29. Capital Should Be Modeled as Species, Not One “Main Flow” Number

One of the weakest concepts in many retail platforms is the idea of generic `主力资金`.

Money is heterogeneous.

Potential capital species:

```text
Retail Attention Capital
High-Net-Worth Retail
Momentum / 游资
Long-Only Institutional
Mutual Fund
ETF / Passive
Hedge Fund
Systematic / Quant
Options-Dealer-Related
Margin / Leveraged
Foreign / Cross-Border
Corporate / Insider
Government / Stabilization
Unknown
```

Every species has different:

- horizon;
- information set;
- constraints;
- objective function;
- persistence;
- response to volatility;
- tolerance for drawdown;
- execution pattern.

A +10% rally driven by:

```text
long-only accumulation + earnings revisions
```

should have a different continuation prior than:

```text
retail attention + short-horizon momentum + collapsing seal quality
```

even if the return and volume are identical.

---

# 30. Build Capital Confluence

For every stock/theme:

```text
CapitalConfluence {
    institutional
    retail
    ETF
    leverage
    foreign
    momentum
    derivatives
    policy
}
```

Then classify:

### Convergent accumulation

Several independent capital species are buying.

### Retail-led ignition

Attention and short-horizon capital lead; institutions not yet involved.

### Institutional accumulation

Slow persistent buying with low narrative heat.

### Mechanical passive move

ETF/index flows dominate.

### Distribution

Retail participation rises while sophisticated or long-horizon capital exits.

This can become much more informative than raw flow.

---

# 31. ETF Flow Intelligence Deserves Its Own Plane

The screenshots include estimated ETF subscription/redemption behavior.

This should be a first-class intelligence object in both markets.

For each ETF:

```text
ETFState {
    shares_outstanding
    estimated_creation_redemption
    AUM_change
    price_change
    flow_ex_price
    turnover
    premium_discount
    constituent_exposure
    theme_exposure
    concentration
}
```

Then propagate ETF flow upward:

```text
Semiconductor Equipment ETF inflow
        ↓
Semiconductor Equipment Theme
        ↓
Constituent demand pressure
```

And downward:

```text
Broad-market ETF redemption
        ↓
mechanical constituent selling
        ↓
possible stock-level dislocation
```

This is particularly useful for distinguishing:

> “Investors suddenly hate this company”

from:

> “The company is being sold because a basket is being redeemed.”

That distinction is exactly the kind of contextual intelligence Mastermind should surface.

---

# 32. “National Team” Should Be an Inference, Not a Label

同花顺 and Chinese market commentary often interpret large broad-ETF activity through the lens of 国家队 / stabilization capital.

Mastermind should never simply echo that interpretation as fact.

Instead maintain:

```text
P(StabilizationActivity | observations)
```

Possible evidence:

- synchronized broad-index ETF creation;
- timing after sharp index weakness;
- concentration in large liquid index vehicles;
- unusual relative support in index constituents;
- state-linked fund disclosures where available;
- historical intervention-pattern similarity;
- divergence between broad-index support and speculative breadth.

This becomes a probabilistic **Policy Capital Lobe**.

The more useful question is not:

> “Did the national team buy?”

It is:

> “How much of today's tape is consistent with stabilization-style capital, and what historically happens when this signature appears?”

---

# 33. Northbound Flow Must Respect Current Data Reality

A practical correction is necessary.

Historically, many China dashboards relied heavily on real-time Northbound buy/sell flow.

HKEX and the Mainland exchanges changed Stock Connect dissemination beginning in 2024. Real-time Northbound buy/sell and total turnover stopped being published in the prior form; historical total turnover, trade counts, ETF turnover, and selected activity remain available, while shareholding disclosure also became less granular/frequent.

Therefore do not design the China engine around a fantasy feed that no longer exists.

Instead:

- use what is legitimately disclosed;
- estimate cross-border behavior only when defensible;
- distinguish direct observations from inferred flows;
- maintain confidence/provenance.

This is a perfect example of why the Neural Web needs provenance.

```text
NorthboundState:
    observed_total_activity
    observed_selected_security_activity
    inferred_direction
    confidence
    disclosure_regime
```

---

# 34. Macro Liquidity Is Part of Speculative Context

The 同花顺 screens include:

- reverse repos / liquidity;
- RMB;
- bonds;
- A50 futures.

These are not decorative macro cards.

They describe the **environment in which the local ecology operates**.

Potential `ChinaLiquidityState`:

```text
OMO injections
OMO maturities
net liquidity
DR007 / repo conditions
SHIBOR
government-bond yields
curve slope
CNY
CNH
CNY-CNH spread
credit impulse proxies
margin financing
```

Then ask conditional questions:

> Do speculative growth themes have better persistence when domestic liquidity is easing and RMB is stable?

> Do high-board momentum cycles fail more often during liquidity withdrawal?

> Does a stronger CNH change the persistence of foreign-sensitive large-cap themes?

This is the kind of empirical question historical replay can answer.

---

# 35. A50 and Overnight Markets Should Form a Pre-Open Prior

China does not wake up into a vacuum.

Before the A-share open, Mastermind can form priors from:

```text
A50 futures
CNH
Hong Kong
China ADRs
US thematic baskets
Nasdaq / SOX
US defense / space baskets
gold
silver
copper
oil
Treasuries
DXY
relevant global news
```

But the relationship should be theme-specific.

Example:

```text
Overnight:
Silver +5%
US silver miners +8%
DXY -1%
real yields lower
```

should update:

```text
P(China silver-theme strength at open)
```

more than:

```text
P(China banks strong at open)
```

Likewise:

```text
US space basket +10%
major procurement catalyst
SpaceX-related news
```

should update the prior for:

- 商业航天;
- satellite components;
- aerospace materials;
- selected power/solar exposure;

but with weights based on **actual Chinese company relevance**, not headline association alone.

---

# 36. Commodity-to-Equity Transmission Should Be a Graph

同花顺's commodity context hints at something bigger.

For commodities:

```text
Commodity Move
   ↓
Producer economics
   ↓
Input-cost effects
   ↓
Downstream margins
   ↓
Inventory value
   ↓
Substitution
   ↓
Narrative
```

Example:

Silver spike:

```text
Silver ↑
  ├── silver miners: direct positive
  ├── streamers: positive
  ├── solar manufacturers: input cost pressure
  ├── electronics: possible marginal cost effect
  ├── recycling economics: improve
  └── strategic-supply narrative: strengthens
```

The same commodity move can be bullish for one theme and bearish for another.

A plain commodity dashboard cannot express this.

A causal graph can.

---

# 37. Valuation Is a Conditioning Variable, Not a Timing Oracle

同花顺 surfaces market valuations.

Mastermind should keep them, but not overfit short-horizon decisions to PE.

Useful representation:

```text
valuation percentile
relative valuation
valuation vs own history
valuation vs growth
valuation vs rates
valuation vs narrative maturity
valuation vs crowding
```

The actionable context is more like:

> Theme at 96th valuation percentile + attention at extreme + breadth decelerating + leader failures + tighter liquidity.

That is a distribution-risk state.

Conversely:

> Expensive theme + accelerating revisions + broadening participation + falling discount rates

may remain strong.

Valuation becomes useful when embedded in state.

---

# 38. Progressive Disclosure Is a Product Lesson Worth Keeping

同花顺 makes navigation intuitive because information unfolds in levels.

Mastermind should preserve this logic:

```text
GLOBAL / MACRO
      ↓
MARKET STATE
      ↓
THEMES
      ↓
SUBTHEMES
      ↓
COMPANIES
      ↓
PARTICIPANTS
      ↓
EVENTS
```

But each level should answer:

> **Why is this node in this state?**

For example:

```text
Commercial Space
State: Expansion
```

Clicking should reveal:

- catalyst;
- leaders;
- breadth;
- attention;
- flow;
- cross-market confirmation;
- lifecycle history;
- failure conditions.

The user should not need to reverse-engineer a score.

Explainability is part of the product.

---

# 39. Do Not Copy 同花顺's UI; Copy Its Information Density

The strategic mistake would be to recreate:

- identical heatmaps;
- identical gauges;
- identical cards;
- identical terminology.

The value is the **data ontology underneath the interface**.

Mastermind's advantage should come from:

```text
same observable world
+
better persistence
+
better cross-linking
+
better historical memory
+
better probabilistic interpretation
```

The result should feel less like:

> “Here are 30 widgets.”

and more like:

> “Here is the current state of the Chinese market, the three transitions that matter most, and the evidence supporting them.”



# PART III — THE US SIDE: BUILDING THE RETAIL THEMATIC INTELLIGENCE SYSTEM THAT DOES NOT CURRENTLY EXIST

# 40. The US Opportunity Is Not “Create More Baskets”

The US side is where the combined project becomes strategically interesting.

China already has retail products that expose unusually granular market ecology.

The US retail ecosystem is fragmented.

A user can find:

- charts in TradingView;
- broad sectors in Finviz;
- ETF holdings in fund pages;
- institutional ownership in filings or data terminals;
- options flow in specialist services;
- alternative data in Quiver-like products;
- analyst research from brokers;
- macro data elsewhere;
- thematic ETFs with opaque constituent logic.

What is largely missing for retail use is a **single system that continuously maps emerging economic themes, explains their supply chains, measures their trading state, and connects them to the rest of the market intelligence graph**.

This creates an important product opportunity:

> Bring institutional-quality thematic ontology and state intelligence into a retail-accessible environment — and then go beyond institutional taxonomy products by connecting the taxonomy to real-time trading intelligence and machine memory.

---

# 41. Existing Institutional Systems Validate Pieces of the US Architecture

The point of studying institutional products is not to imitate their UI.

It is to see which problem categories sophisticated users are already paying to solve.

### Theia Insights

Current Theia material describes:

- dynamic, multidimensional industry classification;
- 200+ thematic and style factors;
- Concept2Universe;
- 200+ Theme Watch Indices;
- portfolio attribution by theme;
- dynamic ontology;
- emerging-player identification.

This validates:

```text
theme ontology
+
theme factor model
+
theme indices
+
dynamic classification
```

### S&P Kensho

S&P explicitly describes using NLP and machine learning over regulatory filings and other public information to detect companies connected to emerging technologies and structural trends.

One especially important design lesson from S&P's own explanation is that text-based classification can identify companies at the **first clear signs of commercial involvement**, before a traditional revenue-threshold screen would necessarily capture them.

This maps directly to Mastermind's distinction:

```text
Business Exposure
vs
Catalyst Activation
vs
Narrative Exposure
```

### MSCI

MSCI now markets tools that map company business segments to themes using an LLM-driven workflow and describes thematic exposure across roughly 40,000 global securities.

The implication:

> Semantic theme mapping is becoming infrastructure, not a novelty.

### Morningstar

Morningstar uses more conservative fundamental relevance frameworks, including analyst judgments about expected future revenue and profit impact. Its “consensus” approach also uses holdings across thematic funds as a market-derived relevance signal.

This is useful because it shows that different methods capture **different realities**:

```text
fundamental analyst relevance
semantic textual relevance
fund-holdings consensus
trading relevance
```

Mastermind should not choose one and declare it truth.

It should explicitly model the disagreement.

---

# 42. Theme Consensus Disagreement Can Be a Signal

Suppose:

```text
Company X

Filings-based theme score:          22
Analyst fundamental theme score:    18
Thematic ETF consensus score:       74
News narrative score:               89
Trading beta score:                 93
```

This tells us something fascinating:

The company is **not yet fundamentally pure**, but the market is rapidly turning it into a theme proxy.

Possible interpretations:

1. investors are correctly pricing future optionality before financial statements show it;
2. theme ETFs are mechanically creating exposure;
3. narrative speculation has outrun economics;
4. management is strategically repositioning;
5. a second-order supply-chain link matters more than current revenue.

Instead of forcing consensus, Mastermind should maintain:

```text
ThemeExposureDisagreement
```

and ask:

> When this disagreement historically appears, what happens next?

That creates a new research surface.

---

# 43. Theme Purity and Theme Optionality Should Be Different Scores

An important improvement over common thematic methodologies:

### Theme Purity

How much current business depends on the theme?

### Theme Optionality

How much future upside could plausibly depend on the theme if adoption succeeds?

Example:

```text
Company A
Current theme revenue: 65%
Theme optionality:      80%

Company B
Current theme revenue:  4%
Theme optionality:      90%
```

Company B may be a terrible pure-play index constituent but a fantastic **emerging exposure candidate**.

The system should preserve both.

Potential theme edge attributes:

```text
current_revenue_exposure
future_revenue_optionality
profit_sensitivity
capex_sensitivity
contract_pipeline
management_commitment
market_narrative_exposure
trading_beta
```

This allows more nuanced baskets:

- Pure Exposure Basket
- Emerging Exposure Basket
- High Optionality Basket
- Trading Proxy Basket
- Supply-Chain Bottleneck Basket

The user can stop arguing over “which is the real basket.”

There can be several, each answering a different question.

---

# 44. Theme Baskets Should Be Multiple Views of the Same Theme

A powerful extension:

For every theme, automatically maintain several basket constructions.

## 44.1 Economic-Purity Basket

Highest direct fundamental exposure.

Useful for:

- long-horizon investment;
- thematic attribution;
- clean economic beta.

## 44.2 Market-Behavior Basket

Stocks currently trading most like the theme.

Useful for:

- short-horizon rotation;
- momentum;
- hedging.

## 44.3 Emerging-Beneficiary Basket

Companies whose theme relevance is rapidly increasing.

Useful for:

- discovery;
- early-cycle identification.

## 44.4 Narrative-Proxy Basket

Stocks receiving disproportionate attention around the theme.

Useful for:

- sentiment;
- speculation;
- crowding analysis.

## 44.5 Bottleneck Basket

Companies whose products constrain growth of the theme.

Useful for:

- second-order alpha;
- margin power;
- capex transmission.

## 44.6 Laggard / Catch-Up Basket

Economically connected names not yet repriced.

Useful for:

- dislocation hunting.

This converts “one thematic index” into a family of **theme views**.

---

# 45. Theme Factor Models Should Explain the Market

The attached US work proposed Mastermind Theme Factors.

This deserves major expansion.

For each theme, build factor returns such as:

```text
equal_weight_return
exposure_weighted_return
market_neutral_return
sector_neutral_return
high_purity_return
high_optionality_return
leader_return
laggard_return
```

Then calculate:

```text
breadth
dispersion
realized volatility
cross-sectional correlation
beta to market
beta to rates
beta to commodity
beta to theme parents
beta to neighboring themes
```

This lets Mastermind ask:

> **What themes explain today's market?**

Instead of:

```text
NASDAQ +1.2%
Industrials +0.5%
```

the system might infer:

```text
AI Power Infrastructure     +0.74% contribution
Defense Modernization       +0.31%
Space Economy               +0.22%
Memory Cycle                -0.18%
GLP-1                       -0.11%
```

That is a far more intuitive decomposition of how investors actually experience markets.

---

# 46. Theme Residual Returns Can Expose Hidden Rotation

Suppose AI Infrastructure rises +2%.

But the market rises +1.7% and semiconductors rise +2.1%.

The raw theme gain is not very informative.

Calculate:

```text
ThemeResidual =
ThemeReturn
- market beta
- sector beta
- factor exposures
```

If residual theme return is strongly positive, the narrative itself is likely contributing.

This helps distinguish:

> “AI stocks rose because all tech rose”

from:

> “AI infrastructure received a theme-specific bid.”

This is crucial for a Dynamic Theme Graph.

---

# 47. Build Theme-to-Theme Relative Value

A theme graph naturally creates relative trades.

Examples:

```text
AI Compute vs AI Power
Gold Miners vs Gold
Space Launch vs Satellite Components
Defense Prime Contractors vs Defense Electronics
Copper Miners vs Copper
GLP-1 Producers vs GLP-1 Suppliers
```

The system can learn:

- lead-lag;
- beta;
- normal spread;
- valuation relationship;
- flow relationship;
- catalyst sensitivity.

Then detect:

```text
SpreadDislocation(theme_A, theme_B)
```

This converts theme intelligence into relative-value intelligence.

---

# 48. Themes Should Form Higher-Order Economic Systems

Some “themes” are better understood as connected subgraphs.

Example:

```text
AI CAPEX COMPLEX
    │
    ├── COMPUTE
    │      ├── GPU
    │      ├── custom silicon
    │      └── HBM
    │
    ├── NETWORKING
    │      ├── switches
    │      ├── optics
    │      └── CPO
    │
    ├── PHYSICAL INFRASTRUCTURE
    │      ├── cooling
    │      ├── electrical equipment
    │      └── construction
    │
    ├── ENERGY
    │      ├── grid
    │      ├── gas
    │      ├── nuclear
    │      └── renewables
    │
    └── APPLICATIONS
           ├── enterprise AI
           ├── agents
           └── robotics
```

The system should reason at each level.

If GPU leadership weakens but power infrastructure accelerates, the AI theme may not be dying.

It may be **migrating downstream**.

That is a key distinction.

---

# 49. Theme Migration Is Different From Theme Death

This is a major new insight.

A theme can appear to weaken because capital is leaving its original leaders.

But capital may actually be rotating into the next monetization layer.

Example:

```text
Phase 1: GPU
Phase 2: networking
Phase 3: power / cooling
Phase 4: software monetization
```

A naïve theme engine sees leadership decay.

An intelligent theme engine asks:

> Is the theme dying, or is value migrating through the causal graph?

Create:

```text
ThemeCapitalMigrationMap
```

Potential outputs:

```text
AI Infrastructure:
    Compute share of theme turnover      61% → 43%
    Power / Cooling                      14% → 29%
    Software Applications                 9% → 18%

Interpretation:
    Theme remains healthy; leadership is migrating downstream.
```

This could be extremely useful.

---

# 50. Theme Mutation: Narratives Change Their Meaning

Themes are living semantic objects.

“AI” in 2023 is not identical to “AI” in 2026.

A theme can mutate because:

- new technologies appear;
- economics change;
- policy changes;
- bottlenecks shift;
- investor interpretation shifts.

Therefore each theme should preserve:

```text
ThemeDefinition_t
ConstituentSet_t
SubthemeWeights_t
NarrativeKeywords_t
CausalGraph_t
```

The system should be able to say:

> “The AI theme has shifted from compute scarcity toward power and deployment economics.”

That is a deeper form of persistent state.

---

# 51. Autonomous Theme Discovery Should Look for Convergence, Not Just Text Clusters

The prior US memo proposed:

```text
documents
→ embeddings
→ semantic clustering
→ candidate theme
→ LLM validation
```

That is useful but incomplete.

Text alone can hallucinate economically meaningless groupings.

A stronger discovery engine requires **cross-modal confirmation**.

Potential candidate theme creation:

```text
Semantic co-emergence
        +
Market co-movement
        +
Shared catalyst
        +
Supply-chain relationship
        +
Attention acceleration
        ↓
Candidate Theme
```

Example:

The system observes:

- several companies mention in-orbit compute;
- news begins discussing orbital data centers;
- a subset of satellite/semiconductor names co-move;
- venture/private-market activity rises;
- government documents mention edge processing in orbit.

Then:

```text
Candidate Theme:
Orbital Computing

Confidence:
0.81

Status:
Emerging / unconfirmed
```

This is far more robust than an LLM inventing a clever label.

---

# 52. Theme Birth Should Be a First-Class Event

A system that only tracks known themes will always be late to genuinely new ones.

Create a `THEME_BIRTH_CANDIDATE` event when:

```text
new semantic cluster
+
new correlated behavior
+
new catalyst graph
+
minimum number of credible companies
```

The system then asks:

- Is this actually new?
- Is it just a subtheme?
- Is there enough economic coherence?
- Is there enough market coherence?
- What existing themes are parents?
- What would falsify the theme?

A theme should graduate through:

```text
Candidate
→ Emerging
→ Confirmed
→ Tracked
→ Mature
→ Dormant / Archived
```

This keeps ontology growth controlled.

---

# 53. Avoid “Theme Spam”

One danger of AI-generated ontologies is producing thousands of clever but useless microthemes.

Do not optimize for theme count.

Optimize for:

```text
economic coherence
market coherence
distinctiveness
predictive usefulness
interpretability
minimum constituent support
historical persistence
```

A useful hierarchy might contain:

```text
Level 0: Global Forces
Level 1: Macro Megathemes
Level 2: Economic Systems
Level 3: Tradable Themes
Level 4: Subthemes
Level 5: Event-specific temporary narratives
```

Temporary narratives should be allowed to expire.

Otherwise the graph becomes a landfill.

---

# 54. Theme Entropy: How Coherent Is a Theme?

Another potentially useful proprietary concept:

## Theme Entropy

A healthy coherent theme should exhibit some combination of:

- common catalysts;
- correlated residual returns;
- shared narrative;
- related economic exposure;
- synchronized flows.

A theme with random members and no shared behavior has high entropy.

Conceptually:

```text
Low Theme Entropy:
    coherent
    tight relationship
    clear leadership
    common drivers

High Theme Entropy:
    scattered
    weak causal relationship
    mixed drivers
    inconsistent market behavior
```

Entropy may increase during:

- theme decay;
- arbitrary narrative expansion;
- late-stage theme washing;
- broad market risk-on where everything rises.

This can help reject bad baskets.

---

# 55. Theme Gravity: How Strongly Does the Theme Pull Members?

Another brainstorming metric:

## Theme Gravity

How much of constituent behavior is currently being explained by the theme?

Possible components:

- residual correlation;
- synchronized intraday moves;
- common reaction to catalysts;
- theme factor R²;
- co-volume spikes;
- options co-movement.

High Theme Gravity:

> Constituents are trading as one organism.

Low Theme Gravity:

> Theme is semantically real but not currently controlling price.

This distinguishes:

```text
Economic theme
vs
Active trading regime
```

A theme may exist permanently but only sometimes become a dominant market force.

---

# 56. Theme Leadership Concentration

Track how dependent the theme is on a few names.

Possible:

```text
LeaderDependency =
top_3 contribution / total positive contribution
```

Interpretation:

### Low concentration + rising breadth

Healthy diffusion.

### High concentration + stable secondaries

Flagship-led but potentially healthy.

### Rising concentration + falling breadth

Fragility.

### Leader failure + no replacement

Possible lifecycle deterioration.

A theme's durability partly depends on whether new leaders can emerge.

---

# 57. Leadership Renewal Is a Powerful Health Signal

In long thematic cycles, leadership often changes.

A durable secular theme can survive the exhaustion of individual leaders if new leaders appear.

Therefore track:

```text
LeadershipRenewalRate
```

Questions:

- Are new stocks entering the top decile of relative strength?
- Are leaders coming from new subthemes?
- Are previous laggards becoming leaders?
- Is leadership broadening or narrowing?

Theme death and leader rotation are not synonymous.

This may be one of the most important safeguards against premature shorting.

---

# 58. Build a Theme Lifecycle as a State-Transition Network

The simple linear ladder:

```text
Dormant
→ Catalyst
→ Discovery
→ Expansion
→ Consensus
→ Crowding
→ Distribution
→ Collapse
```

is useful for intuition.

But the model should not assume a straight line.

A better state network:

```text
                    ┌──── Failed Ignition
Dormant → Catalyst ─┤
                    └──── Discovery
                           │
                           ├──── Consolidation
                           │        │
                           │        └── Re-Acceleration
                           │
                           └──── Expansion
                                  │
                                  ├── Consensus
                                  │      │
                                  │      ├── Mania
                                  │      └── Healthy Maturity
                                  │
                                  └── Premature Exhaustion

Mania
  ├── Blow-Off
  ├── High-Level Consolidation
  └── Distribution

Distribution
  ├── Second Wave
  └── Collapse
```

The key predictive task is:

```text
P(next_state | current_state, world_state)
```

not merely classification.

---

# 59. Theme Lifecycle Must Be Conditioned on the Macro World State

The same theme state has different implications in different macro regimes.

Example:

```text
Theme = Discovery
```

Under:

```text
falling real rates
expanding liquidity
positive earnings revisions
broad risk appetite
```

the probability of Expansion may be high.

Under:

```text
liquidity shock
credit stress
rising real rates
risk-off breadth
```

the same local theme ignition may fail.

So:

```text
P(Expansion)
=
f(
    ThemeState,
    MarketState,
    MacroState,
    LiquidityState,
    CatalystState
)
```

This is where the Theme Graph integrates naturally with the Neural Web world model.

---

# 60. Narrative Reproduction Number (Rₙ) — Make the Metaphor Operational

The original brainstorming used a viral analogy.

Keep it, but make clear that it is not literal epidemiology.

The useful intuition:

> A narrative grows when it continually recruits new attention, new securities, new subthemes, new capital, and new explanatory stories.

Possible inputs:

```text
Δ number of active constituents
Δ number of subthemes
Δ unique news sources
Δ analyst coverage
Δ social/search attention
Δ thematic ETF exposure
Δ new catalysts
Δ cross-market propagation
```

Then a normalized score:

```text
NarrativePropagationScore
```

can be branded as a narrative reproduction number if useful.

The important derivative:

```text
PropagationAcceleration
```

A theme whose price is rising but propagation is collapsing may be late-cycle.

A theme whose propagation is exploding while price remains contained may be early.

---

# 61. Narrative Exhaustion

A theme can run out of incremental story.

Potential signs:

- headline count remains high but unique information falls;
- the same catalyst is repeated;
- attention level high but new-attention growth slows;
- new constituent discovery stops;
- analyst coverage becomes unanimous;
- retail narrative saturation rises;
- leadership narrows;
- price requires increasingly large news to advance.

Create:

```text
NarrativeExhaustionScore
```

This is conceptually similar to diminishing marginal buyer capacity.

A theme does not top because “everyone has heard of it.”

It becomes vulnerable when **incremental information no longer creates incremental demand**.

That distinction matters.

---

# 62. Information Novelty vs Information Volume

Do not count articles.

Measure whether information is new.

Ten thousand articles repeating:

> “AI demand is strong”

may add little.

One filing revealing:

> “hyperscaler increased 2027 power commitment by 40%”

may matter enormously.

Every narrative event should carry:

```text
Novelty
Specificity
Credibility
EconomicMateriality
Surprise
TimeHorizon
```

This connects directly to salience.

The Cortex should attend to **novel information**, not merely loud information.

---

# 63. Narrative Half-Life

Different narratives decay at different speeds.

Examples:

- rumor: hours;
- earnings surprise: days to weeks;
- policy program: months;
- technological transition: years.

Estimate:

```text
NarrativeHalfLife
```

This helps prevent a system from overweighting stale catalysts.

A theme node should know:

```text
CurrentCatalystSet
CatalystAge
ExpectedHalfLife
ResidualImpact
```

This also improves event aggregation.

---

# 64. Narrative Competition

Investor attention is finite.

Themes compete.

When AI, gold, defense, crypto, and biotech all compete for incremental capital, one theme can weaken because another becomes more compelling.

Create:

```text
AttentionShare(theme)
TurnoverShare(theme)
FlowShare(theme)
```

The useful question becomes:

> Is a theme weakening absolutely, or simply losing the competition for scarce attention?

This is especially relevant to A-share rotation, but it exists in the US as well.

---

# 65. Theme Market Share

Treat total speculative/capital attention like an economy.

For theme `i`:

```text
ThemeTurnoverShare_i
ThemeAttentionShare_i
ThemeLimitUpShare_i        # China
ThemeOptionsShare_i        # US
ThemeNewsShare_i
```

Then study:

- share gains;
- share losses;
- concentration;
- leadership rotation.

A theme can be positive in price but losing market share to faster narratives.

That may precede relative underperformance.

---

# 66. Cross-Market Theme Identity

The same economic theme should have a global node with local expressions.

Example:

```text
GLOBAL SPACE ECONOMY
      │
      ├── US expression
      │      ├── launch
      │      ├── satellite comms
      │      └── defense contractors
      │
      ├── China expression
      │      ├── 商业航天
      │      ├── satellite manufacturing
      │      └── components/materials
      │
      └── Europe / others
```

This enables:

```text
GlobalThemeState
RegionalThemeState
CrossRegionalLeadership
```

If US space equities ignite Friday and China opens Monday, the Chinese branch of the same global node inherits a **prior**, not a guaranteed prediction.

This allows intelligent cross-market transmission.

---

# 67. Theme Translation Is Not Literal

A US theme does not necessarily map one-for-one to China.

Example:

US “AI data center power” may express through:

- utilities;
- gas turbines;
- nuclear;
- electrical equipment.

China may express through a different mix because of:

- industry structure;
- policy;
- listing universe;
- local narrative conventions;
- supply-chain geography;
- investor behavior.

Therefore the global graph should have:

```text
GlobalTheme
  ├── US_LocalExpression
  ├── CN_LocalExpression
  ├── HK_LocalExpression
  └── CommodityExpression
```

This prevents a misleading universal basket.

---

# 68. Build a Theme Translation Matrix

For each cross-market theme:

```text
Global Theme        US Expression        CN Expression
------------------------------------------------------------
AI Power            VRT/ETN/etc.         grid/equipment names
Space               launch/satcom        商业航天 components
Gold                miners/royalties     黄金股 / jewelry / miners
Memory              MU/etc.              storage/controller/supply chain
Defense             primes/electronics   军工 / aerospace / electronics
```

The matrix should be dynamic.

When a US catalyst occurs, the system can estimate which Chinese subthemes historically respond and with what lag.

That can become a unique cross-market feature.

---

# 69. Cross-Market Lead-Lag Is a Research Problem, Not a Fixed Rule

Do not encode:

> “US theme up → China theme up.”

Instead backtest:

```text
P(CN theme response | US theme shock, catalyst type, CN state)
```

Condition on:

- magnitude;
- timing;
- whether the catalyst is globally relevant;
- A50 overnight state;
- CNH;
- Chinese market sentiment;
- local policy;
- previous theme saturation.

Sometimes the US is the leader.

Sometimes China is the leader.

Sometimes commodities lead both.

The graph should discover directionality empirically.



# PART IV — DISLOCATION INTELLIGENCE: TURN THE GRAPH INTO AN ALPHA ENGINE

# 70. A Relationship Graph Naturally Creates a Dislocation Engine

One of the most important consequences of building a Theme Graph is that Mastermind gains an explicit model of **what normally relates to what**.

That means it can recognize when expected relationships break.

This connects directly to prior Mastermind dislocation work.

A dislocation is not simply:

> “Stock fell a lot.”

A dislocation is:

> **Observed price behavior is inconsistent with a relationship that the system has reason to believe should currently matter.**

Examples:

```text
Fundamentals strong
but
Price collapses

Theme strong
but
Economically exposed stock lags

Commodity surges
but
Producer fails to respond

Institutional flow strong
but
Price flat

Narrative expands
but
valuation has not repriced

Peers stable
but
one security crashes on non-recurring accounting noise
```

The graph gives Mastermind something explicit to compare price against.

---

# 71. Build a General Dislocation Taxonomy

## 71.1 Price vs Fundamental State

```text
ΔPrice << ΔFundamentalExpectation
```

Potential causes:

- forced selling;
- headline misunderstanding;
- accounting noise;
- non-recurring expense;
- technical liquidation;
- passive basket flow;
- temporary uncertainty.

Potential opportunity:

- long dislocation;
- relative-value trade;
- catalyst watch.

The CDE/HL-style mining example is a perfect archetype:

```text
One company reports noisy earnings
        ↓
stock falls sharply
        ↓
peer is dragged down sympathetically
        ↓
commodity thesis remains intact
        ↓
other peers do not confirm deterioration
```

A sophisticated system should flag the peer contagion as a possible **relationship overreaction**.

---

## 71.2 Price vs Theme

```text
Theme factor        +8%
Stock               +0.5%
Economic exposure   high
Catalyst relevance  high
```

Possible:

- laggard;
- hidden beneficiary;
- company-specific concern;
- delayed reaction.

The engine should not instantly label this a buy.

It asks:

> Is there a valid company-specific reason for the divergence?

That is where Fundamental Forensics, news, filings, and company state enter.

---

## 71.3 Price vs Commodity

```text
Copper +12%
high-beta copper miners +18%
Company X +1%
```

Possible:

- hedge book;
- operational issue;
- jurisdiction risk;
- production miss;
- opportunity.

The causal graph tells the Cortex what explanations to investigate.

---

## 71.4 Flow vs Price

```text
Persistent active buying
+
flat price
```

Possible interpretations:

- absorption by a large seller;
- stealth accumulation;
- poor-quality flow;
- mechanical execution;
- impending breakout.

The signal becomes stronger if:

- seller pressure fades;
- theme breadth improves;
- no negative catalyst exists.

---

## 71.5 Attention vs Price

```text
Narrative attention +3σ
price unchanged
```

Possible early discovery.

But:

```text
attention +3σ
price +70%
breadth falling
```

may instead mean saturation.

The same attention level has different meaning conditioned on lifecycle.

---

## 71.6 Price vs Peer Graph

A static peer list is insufficient.

The Theme Graph supplies **contextual peers**.

For a semiconductor company, its relevant peers today might be:

- HBM suppliers;
- AI memory names;
- data-center components;

rather than its official industry classification.

So peer-dislocation detection should be state-dependent.

---

## 71.7 Expected Relationship Break

This is broader and potentially more important.

Suppose Mastermind expects:

```text
real yields ↓
USD neutral/down
labor weak
→ gold positive
```

but gold falls.

That is not just a price move.

It is a **model surprise**.

This should wake the Cortex.

Possible explanations:

- crowded positioning;
- inflation breakevens collapsed;
- forced liquidation;
- China demand weakened;
- geopolitical premium reversed;
- relationship regime changed.

This makes dislocation detection a core learning mechanism.

---

# 72. Dislocations Need a Falsification Layer

Retail traders frequently call every loss an “overreaction.”

Mastermind must not.

Every dislocation candidate should have:

```text
ExpectedRelationship
ObservedDeviation
AlternativeExplanations
KnownNegativeEvidence
HistoricalMeanReversionRate
HistoricalFailureRate
Confidence
```

The question is:

> **What would make the current move rational rather than dislocated?**

This is essential.

Example:

```text
Theme strong
stock -10%
```

could be cheap.

Or the company may have:

- lost a major customer;
- issued equity;
- guided down;
- faced regulatory action.

The system must actively search for invalidating information.

---

# 73. Dislocation Quality Should Be Scored by Relationship Strength

Not all divergences matter equally.

Possible:

```text
DislocationStrength
=
ExpectedRelationshipStrength
× DeviationMagnitude
× ContextValidity
× CatalystPersistence
× AbsenceOfIdiosyncraticExplanation
```

A stock lagging a weak semantic theme is uninteresting.

A historically high-beta, economically pure, catalyst-relevant beneficiary lagging a powerful theme move with no new negative information is much more interesting.

---

# 74. Relative-Value Dislocations Are Safer Research Targets Than Naked Forecasts

The graph creates pairs and baskets where the question is not:

> “Will the stock rise?”

but:

> “Why has this historically stable relationship moved outside its normal state-conditioned range?”

Examples:

- miner vs metal;
- supplier vs customer;
- US theme vs China local expression;
- leader vs secondary;
- ETF vs NAV constituents;
- economic-purity basket vs narrative-proxy basket.

These relationships are highly compatible with:

- z-scores;
- residual models;
- cointegration where appropriate;
- historical event studies;
- causal reasoning.

This can become an institutional-style opportunity layer.

---

# PART V — TOP RECOGNITION, THEME FRAGILITY, AND DISTRIBUTION

# 75. Merge the Top-Recognition Project Into the Theme Lifecycle

The existing Mastermind top-recognition research should not remain a separate island.

Its deepest insight was:

> **Extension is not proof of a top. The useful problem is distinguishing EXTENDED + CONTINUES from EXTENDED + TOPS.**

That logic applies directly to themes.

A theme in Mania is not automatically a short.

A theme can remain extended for months.

Therefore the Theme Lifecycle Engine and Top Recognition Lobe should share a common concept:

```text
FragilityState
```

The question becomes:

> Has the theme moved from strong-but-extended into a state where incremental demand is failing and internal structure is deteriorating?

---

# 76. Theme Fragility Should Be Multi-Dimensional

Possible fragility inputs:

```text
price extension
price acceleration
volatility expansion
turnover explosion
breadth deterioration
leader concentration
leader failure
attention saturation
narrative exhaustion
valuation extremity
issuance / insider selling
options speculation
flow divergence
new-entrant quality
late-follower behavior
cross-asset non-confirmation
```

Research on historical industry bubbles supports this framing: large run-ups alone do not reliably imply low future returns, but the characteristics of the run-up — including volatility, turnover, issuance, and the price path — can help distinguish crash-prone episodes.

That is precisely why Mastermind should model **anatomy**, not just extension.

---

# 77. Theme Fragility State Machine

Conceptually:

```text
Healthy Trend
    ↓
Extended
    ↓
Accelerating
    ↓
Saturated
    ↓
Fragile
    ↓
Distributing
    ↓
Failed Continuation
    ↓
Breakdown
```

But transitions are not deterministic.

A theme can move:

```text
Extended → Consolidation → Re-Acceleration
```

instead.

Therefore output probabilities:

```text
P(continuation)
P(consolidation)
P(distribution)
P(material drawdown)
```

across:

- 5D;
- 20D;
- 60D;
- 120D.

---

# 78. Breadth Divergence Can Signal Internal Deterioration

Classic late-cycle pattern:

```text
Theme index makes new high
but
fewer members make new highs
```

Add:

- leaders account for more return;
- median member weakens;
- failed breakouts rise;
- volatility broadens;
- high-attention names dominate turnover.

This can be summarized as:

```text
ThemeInternalsDeterioration
```

China has additional variants:

- high-board leaders still rise;
- first-board participation declines;
- failed seals increase;
- prior-day premium weakens.

The US has:

- index/mega-cap concentration;
- options frenzy;
- deteriorating equal-weight behavior;
- insiders/issuance;
- lower-quality speculative follower participation.

Different sensors, same cognitive concept.

---

# 79. Late Followers Can Be a Mania Signature

In mature themes, increasingly weak companies may begin rallying merely because they can be narratively associated with the story.

Create:

```text
ConstituentQualityGradient
```

Track whether incremental outperformers have:

- lower economic exposure;
- weaker fundamentals;
- higher narrative-only exposure;
- lower liquidity;
- higher short interest;
- more promotional language.

A shift from:

```text
high-purity leaders
→ quality suppliers
→ secondaries
→ tenuous proxies
```

may mark narrative saturation.

This is analogous to speculative “infection” reaching marginal hosts.

---

# 80. Theme Washing Is a Detectable Risk

Morningstar explicitly notes the possibility of “theme washing,” where companies emphasize fashionable themes to gain thematic association.

Mastermind can turn this into a feature.

Possible:

```text
ThemeWashingRisk
=
NarrativeExposure
-
EconomicEvidence
```

Adjust for:

- management mention frequency;
- lack of measurable revenue;
- vague future language;
- absence of contracts;
- lack of capex/R&D evidence;
- weak trading confirmation.

A rising ThemeWashingRisk across new entrants may be late-cycle evidence.

---

# 81. Narrative vs Fundamental Divergence Can Be Bullish Early and Bearish Late

This deserves nuance.

High:

```text
NarrativeExposure - BusinessExposure
```

does **not** automatically mean overvaluation.

Early in a real technological transition, narrative can correctly lead reported financials.

The sign depends on:

- catalyst credibility;
- future optionality;
- evidence accumulation;
- theme lifecycle;
- valuation;
- market state.

### Early cycle

Narrative leads → fundamentals later catch up.

### Late cycle

Narrative leads → evidence stops improving → valuation remains extreme.

Same divergence.

Different meaning.

This is exactly why state-conditioning is essential.

---

# 82. Incremental Buyer Exhaustion

Tops occur when marginal demand becomes insufficient.

We cannot directly observe “all future buyers,” but can approximate exhaustion via:

- attention saturation;
- turnover extremity;
- ownership concentration;
- options speculation;
- retail participation;
- diminishing price response to positive news;
- repeated failed breakouts;
- rising sell response to weak news.

One especially powerful variable:

```text
CatalystResponseElasticity
```

Measure:

```text
price response / catalyst surprise
```

If bullish catalysts keep arriving but generate progressively smaller gains, the theme may be exhausting.

Conversely, if minor positive catalysts generate outsized moves, demand remains highly reflexive.

---

# 83. Bad-News Sensitivity vs Good-News Sensitivity

A healthy bull phase may show:

```text
good news → large upside
bad news → shallow dip
```

Distribution may transition toward:

```text
good news → little upside
bad news → large downside
```

Create:

```text
AsymmetricNewsElasticity
```

This can be measured at:

- stock level;
- theme level;
- market level.

The concept is especially useful because it directly observes how the market is **processing information**, not merely what information exists.

---

# 84. Failed Continuation Is More Important Than “Overbought”

An extended move becomes dangerous when it repeatedly fails to convert conditions that historically should have produced continuation.

Examples:

- strong commodity, weak miners;
- good earnings, stock cannot hold gap;
- theme catalyst, breadth fails;
- leader breaks out, secondaries do not follow;
- large active buying, no advance;
- market risk-on, theme underperforms.

This is **negative surprise**.

That surprise should update:

```text
P(distribution)
```

far more than an RSI threshold.

---

# PART VI — MARKET STATE, WORLD MODEL, AND CONTEXTUAL INTUITION

# 85. Theme Intelligence Must Live Inside a World Model

A theme cannot be understood without context.

The Neural Web architecture already provides the correct abstraction.

A persistent world state might include:

```text
State_t = {
    Growth,
    Inflation,
    Liquidity,
    Rates,
    Credit,
    FX,
    Policy,
    Commodities,
    Volatility,
    Breadth,
    Momentum,
    Positioning,
    Earnings,
    Narratives,
    US_market_ecology,
    China_market_ecology,
    Global_theme_states,
    ...
}
```

This state should eventually contain hundreds or thousands of dimensions.

The goal is not to reduce reality prematurely to:

```text
Risk-On
Risk-Off
```

Those labels are useful summaries, not sufficient representations.

---

# 86. The Market State Tensor

The earlier brainstorming proposed a `Market State Tensor`.

That concept should be retained.

Each observation exists across:

## Entity

```text
Global
Country
Exchange
Index
Factor
Industry
Theme
Subtheme
Company
ETF
Commodity
Participant
Event
```

## Horizon

```text
tick
minute
session
daily
weekly
monthly
cycle
```

## Dimension

```text
price
volume
flow
attention
narrative
sentiment
fundamental
valuation
positioning
microstructure
macro
```

This prevents the system from confusing a five-minute event with a six-month structural trend.

A theme can simultaneously be:

```text
5-minute:   overbought
5-day:      accelerating
3-month:    early expansion
3-year:     secular adoption
```

All can be true.

---

# 87. Horizon Separation Is Non-Negotiable

Many market systems fail because they collapse signals with different horizons.

Example:

```text
Long-term:
    AI capex secular thesis strong

Medium-term:
    earnings revisions positive

Short-term:
    theme extremely crowded

Intraday:
    failed breakout
```

This does not produce one “bullish” or “bearish” score.

It produces a conditional action surface.

Mastermind should preserve horizon:

```text
Signal {
    direction
    magnitude
    horizon
    confidence
}
```

Then Prophet can reason separately for:

- trade;
- swing;
- medium-term;
- strategic position.

---

# 88. Every Lobe Should Emit Beliefs, Not Just Data

The Neural Web research proposed a standardized belief object.

This Theme project should adopt it.

A mature lobe should emit:

```text
Observation
Derived State
Direction
Magnitude
Horizon
Confidence
Historical Reliability
Regime Compatibility
Causal Interpretation
Contradicting Evidence
Novelty
Provenance
Expected Consequences
```

Example:

```text
Lobe: China Speculation Ecology

Observation:
Failed-board rate fell from 31% to 14%.

Derived State:
Speculative follow-through improving.

Direction:
Risk-on.

Horizon:
1–5 sessions.

Confidence:
0.78.

Historical Reliability:
Strongest after sentiment-ice regimes.

Contradiction:
Turnover remains below 60D median.

Expected Consequence:
Yesterday's limit-up cohort should outperform the median stock tomorrow.
```

That last line is crucial.

It creates a falsifiable expectation.

---

# 89. Expectations Are the Bridge From Observation to Intelligence

A system does not truly understand a state until it can say:

> **If my interpretation is correct, what should happen next?**

Every important belief should generate expectations.

Example:

```text
Hypothesis:
Commercial Space is transitioning Discovery → Expansion.

Expected:
1. breadth should continue increasing;
2. secondaries should begin outperforming;
3. leader dependency should decline;
4. turnover should remain elevated;
5. negative idiosyncratic news should not collapse the whole basket.
```

If these fail, confidence should decline.

This creates self-correcting intelligence.

---

# 90. Surprise Is the Foundation of Machine Intuition

Prior Neural Web work defined:

```text
Surprise = Observed Outcome - Expected Outcome
```

This should become one of the organizing principles of the Theme Graph.

Examples:

### Positive surprise

```text
Theme expected to consolidate
but
breadth accelerates and new leaders emerge.
```

Update:

```text
P(re-acceleration) ↑
```

### Negative surprise

```text
Commodity +5%
miners expected strong
but
miners sell off.
```

Wake Cortex.

### Structural surprise

```text
US theme historically leads China by one session
but
relationship stops working for several episodes.
```

Research Cortex investigates regime change.

Machine intuition comes from repeatedly experiencing:

```text
expectation
→ outcome
→ error
→ explanation
```

---

# 91. Build a Surprise Graph

Surprise itself can propagate.

Example:

```text
NFP downside surprise
      ↓
yield surprise
      ↓
gold response surprise
      ↓
miner response surprise
```

If gold behaves as expected but miners do not, the anomaly localizes to the equity layer.

If yields themselves do not respond, the anomaly is macro pricing.

This helps the system diagnose **where in the causal chain the model broke**.

That is much more useful than a flat anomaly score.

---

# 92. Salience: What Deserves the Cortex's Expensive Attention?

The Cortex should not reason continuously about every ticker.

That would be computationally wasteful and likely noisy.

Create a salience function:

```text
Salience =
f(
    Surprise,
    Magnitude,
    Novelty,
    RelationshipBreak,
    RegimeTransition,
    PredictiveImportance,
    PortfolioRelevance,
    CrossLobeDisagreement
)
```

Events above threshold trigger deeper reasoning.

This makes the architecture scalable.

---

# 93. Novelty Should Control Confidence

Historical analogs are powerful but dangerous.

Define:

```text
Novelty(State_t)
=
1 - max historical similarity
```

### Familiar state

Use:

- empirical analogs;
- calibrated conditional probabilities;
- learned factor weights.

### Novel state

Use more:

- causal reasoning;
- scenario analysis;
- conservative confidence;
- explicit uncertainty.

This prevents the system from forcing every new event into a familiar template.

---

# 94. Historical Analog Retrieval Must Ask “How Is Now Different?”

If current markets look partly like 2021 AI/speculation, that does not mean:

> “2021 again.”

The Cortex should retrieve:

```text
Similarities
Differences
Causal relevance of differences
```

A strong analog output:

```text
Closest structural analogs:
A, B, C.

Similar:
- liquidity improving
- theme breadth broadening
- retail attention accelerating

Different:
- rates level higher
- valuation lower
- institutional participation stronger
- current theme has actual earnings revisions

Implication:
Use historical continuation prior, but reduce expected volatility and extend horizon.
```

That is **analogical reasoning**, not pattern matching.

---

# 95. Contextual Weighting Solves the “Which Signal Matters?” Problem

Current systems often use fixed weights:

```text
Score = Σ w_i * signal_i
```

But the useful architecture is:

```text
Score_t = Σ w_i(State_t) * signal_i,t
```

Example:

Gold:

During:

```text
early easing + sticky inflation
```

real-yield signals may receive high weight.

During:

```text
liquidity crisis
```

forced-liquidation and USD funding signals may dominate.

China high-beta theme:

During:

```text
冰点 recovery + rising turnover
```

limit-up ecology may be highly predictive.

During:

```text
policy-driven large-cap stabilization
```

the same speculative signals may matter less.

This is what “context-sensitive intuition” means in engineering terms.

---

# 96. Mixture-of-Experts Can Become a Practical Approximation

Possible experts:

```text
Early Easing Expert
Inflationary Expansion Expert
Growth Scare Expert
Liquidity Crisis Expert
Commodity Shock Expert
Speculative Momentum Expert
AI CapEx Expert
China Stimulus Expert
China Sentiment Recovery Expert
Late-Cycle Bubble Expert
```

The world-state model estimates:

```text
P(regime_k)
```

and gates their influence.

The LLM does not need to invent numeric weights.

Historical validation should calibrate them.

---

# 97. The LLM Is the Scientist, Not the Calculator

Retain this architectural principle.

LLM strengths:

- interpretation;
- contradiction detection;
- causal hypothesis generation;
- semantic mapping;
- analogy;
- synthesis;
- identifying missing information.

Deterministic/statistical strengths:

- correlations;
- factor estimation;
- scoring;
- calibration;
- optimization;
- execution;
- validation.

The goal is hybrid intelligence.

Do not replace robust mathematics with eloquent language generation.

---

# PART VII — HISTORICAL MEMORY AND SYNTHETIC MARKET EXPERIENCE

# 98. The Theme Graph Becomes Much More Powerful When It Remembers

Static theme data answers:

> “What is Commercial Space today?”

Persistent theme memory answers:

> “How did Commercial Space get here?”

Store:

- birth catalyst;
- initial members;
- leadership transitions;
- expansions;
- failed waves;
- valuation extremes;
- attention peaks;
- important earnings;
- policy changes;
- distribution events;
- previous analogs.

Themes become **experienced entities**.

---

# 99. Three Kinds of Memory

The Neural Web architecture's memory taxonomy should be explicitly inherited.

## Episodic Memory

Specific historical experiences.

Example:

```text
202X Commercial Space breakout:
    initial catalyst
    state at ignition
    leaders
    breadth path
    failed signals
    ultimate outcome
```

## Semantic Memory

Generalized beliefs extracted from episodes.

Example:

> “Commercial-space breakouts have historically persisted longer when defense procurement and private launch demand accelerate simultaneously.”

## Procedural Memory

Behavioral changes in models.

Example:

```text
When:
China sentiment recovering
+ theme breadth > threshold
+ prior-limit-up premium positive

increase theme continuation factor weight.
```

The third type is critical.

Learning should eventually change behavior, not just add notes.

---

# 100. Historical Replay Is a Domain Apprenticeship

A human analyst experiences:

```text
1 market day / day
```

Mastermind can potentially process thousands of historical states per day.

For each replay date, enforce strict point-in-time information.

At time `t`, the system only sees information available at `t`.

Then produce:

```text
World State
Important Variables
Theme States
Hypotheses
Analogues
Contradictions
1D forecast
5D forecast
20D forecast
60D forecast
Confidence
```

Advance time.

Reveal outcomes.

Ask:

```text
What happened?
What did we predict?
What surprised us?
What did we misunderstand?
What should we remember?
```

That creates synthetic experience.

---

# 101. Theme Replay Can Train Lifecycle Recognition

Historical replay is especially powerful for themes.

Take historical episodes such as:

- dot-com infrastructure;
- shale;
- solar;
- EVs;
- cannabis;
- SPACs;
- COVID beneficiaries;
- cloud;
- semiconductors;
- AI;
- uranium;
- precious metals;
- Chinese property;
- China EV;
- A-share AI;
- A-share brokerage rallies.

At each date:

```text
ThemeState_t
```

Then label later outcomes:

```text
Expansion
Failed Ignition
Consolidation
Mania
Distribution
Collapse
Second Wave
```

The system can learn transition probabilities.

---

# 102. Hindsight Is Allowed for Labels, Not Features

The top-recognition research correctly makes this distinction.

We are allowed to know:

> March 15 was the ultimate top

when constructing the historical target.

But a March 10 training state may only contain information available by March 10.

This transforms hindsight into supervised labels rather than leakage.

Every historical dataset should track:

```text
event_time
knowledge_time
release_time
revision_time
```

Point-in-time integrity is non-negotiable.

---

# 103. The Ontology Itself Must Be Point-in-Time

This is harder than price data.

Suppose in 2026 we know:

> Company X became a major AI-power beneficiary.

A 2022 backtest must not assume investors already classified it that way unless evidence existed then.

Therefore theme membership needs:

```text
evidence_time
belief_time
valid_time
```

Potential solution:

reconstruct historical theme edges using only documents available then.

This is expensive.

But it may be one of the most valuable forms of data integrity in the whole system.

---

# 104. Replay the Same History After the System Improves

A profound consequence:

Mastermind can relive 2008, 2020, or 2021 multiple times.

Model version N:

```text
historical life
→ errors
→ lessons
→ improved representation
```

Model N+1 replays the same eras with:

- better lobes;
- better theme ontology;
- better attention metrics;
- better state representations.

This approximates repeated apprenticeship.

That may be one of the shortest paths toward domain-specific machine intuition.



# PART VIII — HOW THIS PLUGS INTO THE EXISTING MASTERMIND NEURAL WEB

# 105. The Theme Graph Is Not Another Lobe

This distinction is important.

Do not architect the Theme Graph as:

```text
Macro Lobe
Options Lobe
Fundamentals Lobe
Theme Lobe
```

That would undersell it.

The Dynamic Theme Graph is better understood as a **semantic relationship layer** through which many lobes communicate.

For example:

```text
                    AI POWER THEME
                          │
      ┌───────────────────┼───────────────────┐
      │                   │                   │
 FUNDAMENTALS           OPTIONS            MACRO
      │                   │                   │
 earnings revisions   call demand       real rates
 margins              skew              capex
      │                   │                   │
      └───────────────────┼───────────────────┘
                          │
                       THEME STATE
```

The theme node gathers evidence from multiple lobes and then feeds its state back into them.

This makes the Neural Web actually **web-like** rather than a stack of independent dashboards.

---

# 106. The Dynamic Theme Graph Can Become the Missing Semantic Bus

Current market systems often suffer from representation fragmentation.

Macro knows:

> real yields fell.

Commodity system knows:

> gold rose.

Equity system knows:

> NEM outperformed.

Theme system knows:

> precious metals breadth expanded.

News system knows:

> Fed easing expectations increased.

Without a shared semantic layer, those are separate observations.

The Theme Graph can connect:

```text
Fed Policy
   ↓
Real Yields
   ↓
Gold
   ↓
Precious Metals Theme
   ↓
Senior Miners
   ↓
Junior Miners
```

The graph is therefore not simply a classification service.

It is a **meaning transport layer**.

---

# 107. Existing Mastermind Systems Gain New Context

## Prophet

Receives:

- market state;
- theme lifecycle;
- theme factor returns;
- constituent roles;
- crowding;
- historical analogs.

## Risk Radar

Receives:

- theme concentration;
- correlated-theme contagion;
- cross-theme dependence;
- crowding;
- fragility.

## Rotation Engine

Receives:

- theme market share;
- attention share;
- flow share;
- migration;
- leadership renewal.

## Short / Top Recognition

Receives:

- lifecycle;
- narrative exhaustion;
- breadth deterioration;
- theme washing;
- catalyst response elasticity.

## Fundamental Forensics

Receives:

- theme-specific expectations;
- peer context;
- economic exposure;
- dislocation candidates.

## Alternative Data Network

Receives:

- a semantic target to map every alternative data event onto.

This last point is particularly important.

---

# 108. Alternative Data Becomes More Valuable When It Has a Theme Destination

Raw alternative data easily becomes a museum.

Examples:

- government contract;
- patent filing;
- lobbying disclosure;
- congressional trade;
- satellite activity;
- import/export;
- procurement;
- hiring;
- web traffic.

Without semantic context:

> interesting data point.

With the Theme Graph:

```text
Government Contract
      ↓
Company
      ↓
Missile Defense Subtheme
      ↓
Defense Modernization Theme
      ↓
Theme Catalyst Strength
      ↓
Peer / supplier expectation
```

This converts alternative data from isolated novelty into **causal evidence**.

---

# 109. Alternative Data Should Update Beliefs, Not Merely Trigger Alerts

Imagine a defense supplier receives a material contract.

A simple system:

> Alert: contract awarded.

Mastermind:

```text
Company Economic Exposure:
    Missile Defense 0.44 → 0.52

Catalyst Activation:
    +0.23

Theme Fundamental Confirmation:
    stronger

Supply-Chain Confidence:
    increased

Revenue Expectation:
    update horizon 12–36M

Theme State:
    Discovery confidence +4 pts

Related Companies:
    identify upstream/downstream beneficiaries
```

The event changes the graph.

That is how information becomes state.

---

# 110. The White House / Policy Plane Can Feed Themes Directly

Policy is one of the strongest cross-market theme creators.

Potential architecture:

```text
Executive Order / Budget / Procurement / Regulation
                    ↓
             Policy Event Node
                    ↓
      affected technologies / industries
                    ↓
             Theme Graph
                    ↓
          Company Exposure Graph
```

Examples:

- defense procurement;
- semiconductor restrictions;
- tariffs;
- energy subsidies;
- medical reimbursement;
- AI regulation;
- export controls;
- mineral policy.

The system should distinguish:

```text
Announcement
Authorization
Appropriation
Contract Award
Actual Spending
```

because markets frequently confuse these stages.

A policy headline with no funding should not equal cash-flow reality.

---

# 111. Foresight Can Become Catalyst Probability

If Mastermind already has a forward-looking Foresight layer, theme nodes can consume:

```text
P(policy event)
P(regulatory decision)
P(earnings catalyst)
P(product launch)
P(contract)
P(macro event)
```

Then the Theme Graph becomes forward-looking.

Instead of only:

> theme strong because catalyst happened

it can reason:

> theme has a credible upcoming catalyst tree.

---

# 112. Fundamental Forensics Can Validate Theme Purity

When narrative exposure surges, Fundamental Forensics should answer:

> Is there economic evidence?

Potential checks:

- revenue share;
- backlog;
- orders;
- capex;
- margin;
- management language;
- unit economics;
- customer concentration.

Output:

```text
Narrative / Fundamental Alignment:
    Strong
    Moderate
    Weak
    Speculative
```

This is especially useful for late-cycle theme washing.

---

# 113. Risk Radar Should Think in Theme Contagion Graphs

Risk does not propagate by sector labels only.

Example:

```text
Memory pricing collapse
    ↓
Memory producers
    ↓
semicap suppliers
    ↓
AI server BOM assumptions
    ↓
broader AI hardware basket
```

Or:

```text
Silver collapse
    ↓
silver miners
    ↓
precious-metal risk appetite
    ↓
junior miners
    ↓
leveraged mining ETFs
```

Risk Radar can use graph centrality to identify:

- high-propagation nodes;
- bottlenecks;
- shared factors;
- concentration.

---

# 114. Graph Centrality Can Identify Hidden Market Importance

A company may be small by market cap but highly central to a theme graph.

Possible centrality concepts:

```text
Economic Centrality
Narrative Centrality
Trading Centrality
Supply-Chain Centrality
Catalyst Centrality
```

Example:

A niche component supplier may sit at a bottleneck connecting multiple themes.

Its price behavior may provide information about a larger ecosystem.

This creates a potential **market sensor discovery** process:

> Which securities consistently lead economically connected groups?

---

# 115. Leading Indicator Nodes

The graph can empirically learn that certain nodes lead others.

Examples:

```text
Commodity → miners
Hyperscaler capex → power equipment
Memory spot pricing → memory equities
A50 futures → China open
US ADR basket → local A-share sentiment
```

But leadership can change by regime.

Store:

```text
LeadLagEdge {
    source
    target
    horizon
    regime
    historical_strength
    current_strength
}
```

Now causal and statistical relationships coexist.

---

# 116. The Neural Web Should Distinguish Causal Edges From Statistical Edges

This is essential.

Graph edges can represent:

```text
CAUSES / TRANSMITS
SUPPLIES
BUYS_FROM
COMPETES_WITH
SUBSTITUTES_FOR
CORRELATES_WITH
LEADS
CO-MOVES_WITH
NARRATIVELY_ASSOCIATED_WITH
OWNED_BY
MEMBER_OF
```

Do not flatten these into one `related_to`.

A causal edge has different interpretive value than a correlation edge.

Example:

```text
Copper price ↑ → copper miner cash flow
```

has economic mechanism.

```text
Stock A ↔ Stock B correlation 0.8
```

may be temporary.

The Cortex should know the difference.

---

# 117. Causal Confidence Should Be Separate From Predictive Strength

A relationship can be:

### Strong causal, weak short-horizon predictive

Example:

commodity price affects long-term producer economics but daily equity price is noisy.

### Weak causal, strong predictive

Example:

one liquid ETF consistently leads a basket by minutes due to market mechanics.

Track:

```text
CausalConfidence
PredictiveStrength
Stability
Horizon
```

This prevents philosophical purity from discarding useful empirical relationships.

---

# 118. Build Causal Chains, Not Just Pairwise Edges

The most interesting reasoning occurs through paths.

Example:

```text
NFP weak
   ↓
Fed path reprices
   ↓
nominal yields fall
   ↓
real yields fall
   ↓
gold strengthens
   ↓
senior miners improve
   ↓
junior miners catch up
```

If the chain breaks at:

```text
gold strengthens
but miners fail
```

the system knows the anomaly occurs between commodity and equity expression.

That is far more diagnostic than “miner weakness.”

---

# 119. Propagation Delay Should Be Learned

Each causal path has a characteristic time distribution.

Example:

```text
Macro release → Treasury:
seconds

Treasury → gold:
seconds/minutes

Gold → senior miners:
minutes

Senior miners → junior miners:
hours/days

Policy program → supplier revenue:
quarters/years
```

A causal graph without horizon is misleading.

Every transmission edge should learn:

```text
lag_distribution
half_life
regime_dependence
```

This helps the Cortex avoid asking for immediate confirmation from long-horizon relationships.

---

# 120. Build a Counterfactual Layer

A mature system should be able to ask:

> If catalyst X had not occurred, how much of the move would we expect anyway?

This helps estimate theme-specific impact.

Possible statistical approaches:

- market/sector residuals;
- matched controls;
- synthetic baskets;
- event studies;
- factor models.

The Cortex can then interpret:

```text
Observed move       +8.0%
Expected ex-event   +2.4%
Residual            +5.6%
```

This gives a cleaner measure of catalyst importance.

---

# PART IX — A MASTER MARKET-STATE ENGINE ACROSS US AND CHINA

# 121. One Global World Model, Multiple Local Market States

Architecture:

```text
GLOBAL WORLD STATE
    │
    ├── US Market State
    │       ├── equity breadth
    │       ├── options
    │       ├── ETF flows
    │       ├── credit
    │       └── theme states
    │
    ├── China Market State
    │       ├── breadth
    │       ├── limit-up ecology
    │       ├── auction
    │       ├── policy liquidity
    │       └── theme states
    │
    ├── HK Market State
    │
    ├── Commodity State
    │
    └── Macro State
```

This creates cross-market context without pretending the markets are identical.

---

# 122. Local Market “Weather Reports”

Each market should generate a machine-readable weather report.

Example — China:

```text
China Market Weather

Direction:             Mixed
Market Quality:        Improving
Speculation:           Recovering
Liquidity:             Supportive
Theme Concentration:   Moderate
Breadth:               Broadening
High-board survival:   Improving
Prior limit-up reward: Positive
Policy capital:        Possible
Crowding:              Low/Moderate
```

Example — US:

```text
US Market Weather

Direction:             Positive
Market Quality:        Narrow
Mega-cap concentration: High
Equal-weight breadth:  Weak
Options speculation:   Elevated
Credit:                Benign
Real yields:           Falling
Theme leadership:      AI / Space / Metals
Crowding:              High in AI compute
```

The same global macro event can have different local expressions.

---

# 123. Market Quality Should Have Its Own Historical Distribution

Do not invent 0–100 scores purely by intuition.

If a user-facing score exists, map it to empirically meaningful distributions.

Example:

```text
Market Quality 82
=
state historically in top 18% of internal confirmation
```

And record conditional outcomes.

This turns a pretty gauge into a calibrated state variable.

---

# 124. Market Concentration Has Several Meanings

Track separately:

```text
Return Concentration
Turnover Concentration
Attention Concentration
Theme Concentration
Leadership Concentration
Ownership Concentration
```

A market can be broad in price but concentrated in narrative.

Or narrow in index leadership but broad in speculative themes.

The details matter.

---

# 125. Market Synchronization

Measure cross-sectional correlation.

### High synchronization

Market macro/factor dominates.

Individual theme signals may be less independent.

### Low synchronization

Idiosyncratic/theme selection matters more.

This should influence Prophet's expected value of stock-picking signals.

Conceptually:

```text
StockSelectionWeight ↑
when
cross-sectional differentiation ↑
```

---

# 126. Regime Compatibility Should Be Attached to Every Signal

A signal learned in one environment may fail elsewhere.

For every signal:

```text
SignalReliabilityByState
```

Example:

```text
China first-board continuation signal

Strong:
    sentiment recovery
    rising turnover

Weak:
    沸点
    declining prior-board premium
```

US:

```text
small-cap breakout signal

Strong:
    falling real yields
    broad risk-on
    improving credit

Weak:
    rising funding stress
```

This is a practical route toward context-sensitive intuition.

---

# PART X — US-SPECIFIC INTELLIGENCE ORGANS

# 127. US ETF Ecosystem as a Capital-Flow Map

ETFs are unusually important in the US because they provide visible, structured baskets.

Use them as:

- ownership signals;
- theme consensus;
- flow vehicles;
- mechanical demand/supply sources;
- ontology seed data.

Potential graph:

```text
ETF
  ├── holds → Company
  ├── represents → Theme
  ├── overlaps → ETF
  └── receives → Flow
```

Then derive:

```text
ThemeETFFlow
ThemeConsensusHoldings
CrowdedETFOverlap
PassiveFlowSensitivity
```

---

# 128. ETF Consensus Can Reveal Market-Perceived Theme Membership

Morningstar's consensus approach illustrates a clever idea:

If many independently constructed thematic funds repeatedly own the same stock, that is evidence the market views the stock as relevant.

Mastermind can generalize:

```text
ThemeConsensusScore =
function(number of relevant ETFs,
         weights,
         manager diversity,
         theme purity,
         time persistence)
```

Then compare with fundamental exposure.

Again:

```text
Consensus vs Economics
```

becomes information.

---

# 129. ETF Ownership Can Create Mechanical Dislocations

If several crowded thematic ETFs own the same small/mid-cap names:

- inflows can amplify;
- outflows can create forced selling;
- rebalance dates can matter.

Track:

```text
ETFOwnershipPressure
ETFOverlap
FlowSensitivity
```

The Theme Graph then understands reflexivity:

```text
Theme narrative ↑
→ ETF inflow
→ constituent buying
→ theme return ↑
→ more attention
```

This is a feedback loop.

---

# 130. US Options Should Be a Theme-Level Sensor, Not Only a Ticker Tool

Aggregate options state upward.

For each theme:

```text
call_volume
put_volume
open_interest
skew
implied_volatility
term_structure
dealer-sensitive positioning where obtainable
options_attention
```

Then ask:

> Is speculation concentrated in the leader, or broadening across constituents?

### Early phase

Options activity may rise in a small set of informed/early leaders.

### Mania

Call activity can spread into low-quality proxies.

This can complement lifecycle detection.

---

# 131. Options Market Data Has Public Baselines but Commercial Depth Matters

OCC publicly exposes various volume and open-interest reports, including account-type and exchange views and historical windows.

That gives useful baseline market structure.

But richer intraday flow, quote history, Greeks, trade classification, and long backfills may require licensed feeds/vendors.

The system should retain provenance:

```text
Raw exchange/OCC observable
Vendor-derived classification
Mastermind inference
```

Do not present inferred “smart money” labels as direct facts.

---

# 132. SEC Filings Are a Foundational US Semantic Data Source

SEC EDGAR APIs provide real-time company submission histories and XBRL data, while bulk archives support large-scale ingestion.

This is extremely compatible with the Dynamic Theme Graph.

Potential extraction targets:

- new product language;
- revenue-segment changes;
- capex;
- customer concentration;
- risk factors;
- acquisitions;
- partnerships;
- geographic exposure;
- contract references.

The advantage of primary filings:

> They create an auditable evidence layer for company-theme edges.

---

# 133. 13F Is Useful but Lagged

Form 13F is valuable for understanding larger institutional portfolios, but the system must respect what it is.

Institutional managers meeting the statutory threshold report covered securities holdings, generally at quarter end.

This means:

```text
13F ≠ live institutional flow
```

Use it for:

- persistent ownership;
- manager-theme fingerprints;
- ownership concentration;
- quarter-over-quarter change;
- consensus.

Do not call a 13F change “today's smart-money buying.”

---

# 134. Institutional Manager Theme Fingerprints

The Participant Graph creates a new use for 13F.

For every manager:

```text
ManagerThemeExposure
ThemeChangeOverTime
Concentration
TypicalHoldingPeriod
PositionInitiationPattern
```

Then:

> Which managers are increasing AI Power exposure?

> Which managers repeatedly enter commodity themes before public narrative peaks?

This can become a slow-moving capital-intelligence layer.

---

# 135. Analyst Revision State

The US theme system should aggregate:

```text
earnings revision breadth
revenue revision breadth
price-target changes
rating changes
estimate dispersion
```

at theme level.

This allows:

```text
Price strong + revisions strong
```

vs:

```text
Price strong + revisions deteriorating
```

The latter may imply narrative outrunning fundamentals.

---

# 136. Short-Side Data Must Be Interpreted Carefully

FINRA provides:

- short interest;
- off-exchange short-sale volume;
- more detailed monthly short-sale transaction files.

But short-sale volume is **not** short interest and does not represent a direct bearish-position measure.

This distinction should be hard-coded into the intelligence ontology.

Potential features:

```text
ShortInterestState
BorrowCost where licensed
Utilization where licensed
ShortSaleVolumeContext
ShortCoveringRisk
CrowdedShortPotential
```

But provenance and semantics matter.

A false “short pressure” label would poison the graph.

---

# PART XI — CHINA-SPECIFIC INTELLIGENCE ORGANS

# 137. China Is Where Market Ecology Can Become a Product Moat

The China system should not be treated as a translated US terminal.

A-shares have their own behavioral grammar.

Unique concepts include:

```text
涨停
跌停
连板
炸板
封单
竞价
游资
龙虎榜
情绪周期
板块接力
昨日涨停溢价
```

These are not merely Chinese labels for universal indicators.

They represent market structures that should be modeled natively.

---

# 138. Build a “Strategy Reinforcement Map”

Earlier we described yesterday's limit-up cohort as the market's reinforcement schedule.

Generalize it.

Track recent strategy cohorts:

```text
Yesterday Limit-Ups
Yesterday High Boards
Recent Breakouts
Recent IPOs
High-Turnover Leaders
Low-Price Speculative Names
Theme Laggards
```

Measure:

```text
next-session reward
drawdown
survival
follow-through
```

This tells Mastermind:

> Which kinds of risk-taking are currently being rewarded?

That is a powerful market-state signal.

---

# 139. Board-Height Survival Curve

Rather than only maximum 连板:

```text
P(survive to n+1 board | currently n boards)
```

conditional on:

- sentiment;
- theme breadth;
- turnover;
- first-touch time;
- seal quality;
- participant profile.

This creates a probabilistic model of speculative ladder health.

---

# 140. Auction Intelligence Is a First-Class Signal

Opening call auction can reveal:

- overnight narrative repricing;
- demand imbalance;
- theme synchronization;
- leader/follower hierarchy.

Potential fields:

```text
indicative price
matched volume
unmatched volume
imbalance direction
auction turnover
relative gap
revision during auction
final seconds acceleration
theme peer synchronization
```

Closing auction can reveal:

- index/passive flow;
- institutional execution;
- rebalance pressure;
- late information;
- positioning into next day.

These should be stored as events.

---

# 141. Auction Surprise

Compare auction state with the overnight prior.

Example:

```text
Overnight prior:
Commercial Space expected strong.

Auction:
leaders gap +6%
secondaries flat
breadth poor
```

Interpretation:

> Catalyst is recognized, but market breadth is not confirming.

Or:

```text
Overnight prior modest
Auction breadth unexpectedly huge
```

Positive surprise.

This is where pre-open world state becomes immediately falsifiable.

---

# 142. “封单” Should Be Normalized

Raw order-wall size is misleading across securities.

Potential normalizations:

```text
wall / free float
wall / ADV
wall / intraday traded value
wall / top-of-book depth
wall persistence
wall cancellation rate
```

Also track:

```text
wall trajectory
```

A wall falling from:

```text
¥500m → ¥120m
```

while price remains sealed is different from a strengthening wall.

Again: derivative > level.

---

# 143. Failed-Board Anatomy

A failed limit-up should be treated as its own episode.

Possible features:

- first touch time;
- number of breaks;
- time sealed;
- largest wall;
- wall decay;
- volume after break;
- theme behavior;
- leader behavior;
- market sentiment;
- closing location.

Then classify:

```text
Healthy shakeout
Weak seal
Distribution
Theme-wide failure
Idiosyncratic failure
```

This can feed both continuation and short-risk systems.

---

# 144. 龙虎榜 + Theme Lifecycle

Participant behavior becomes more useful when interpreted by theme state.

Example:

### Discovery

Early repeat 游资 participation may confirm ignition.

### Mania

The same seats entering late, low-purity followers may indicate speculation.

### Distribution

Institution selling + retail heat + failing seals is different again.

Do not assign static “good/bad” labels to participants.

Context matters.

---

# 145. China Retail Attention Is Empirically Worth Modeling

Academic research using Baidu search data has found meaningful relationships between attention and Chinese stock behavior, including contemporaneous abnormal returns, trading behavior, idiosyncratic risk, and forms of mispricing.

But the literature does not support a simplistic:

```text
attention ↑ → future return ↑
```

Some effects reverse; some vary by investor type; attention can increase volatility or price pressure.

Therefore the system's correct stance is:

> **Attention is a causal/behavioral state variable whose meaning depends on lifecycle, participant composition, and current price response.**

That is more defensible and more useful.

---

# 146. China “Theme Heat” Should Be Decomposed by Source

One aggregate heat score hides whether attention comes from:

- search;
- news;
- app clicks;
- social media;
- broker research;
- 龙虎榜;
- price movement itself.

These may have different information content.

Create:

```text
AttentionSourceMix
```

Then study which source tends to lead.

For example:

```text
analyst/research attention leading
```

may imply discovery.

```text
retail search attention after +80% move
```

may imply saturation.

This should be empirical, not assumed.



# PART XII — NEW PROPRIETARY CONCEPTS THAT EMERGE FROM THE SYNTHESIS

# 147. Theme State Vector

Every theme should have a common state representation.

Conceptually:

```text
ThemeState_t = {
    EconomicExposureQuality,
    CatalystActivation,
    PriceMomentum,
    RelativeStrength,
    Breadth,
    Leadership,
    LeadershipRenewal,
    Liquidity,
    Flow,
    Attention,
    NarrativePropagation,
    FundamentalRevisions,
    Valuation,
    Crowding,
    ParticipantMix,
    OptionsState,
    ETFState,
    CrossMarketConfirmation,
    MacroCompatibility,
    Fragility,
    Lifecycle,
    Novelty
}
```

The value is not the exact variable list.

The value is standardization.

Once every theme emits comparable state, the system can learn across:

- AI;
- defense;
- gold;
- biotech;
- commercial space;
- China AI;
- China solar;
- US uranium.

This is how experience can transfer from one thematic organism to another without pretending they are economically identical.

---

# 148. Theme Intelligence Should Have Two Parallel Scores: Strength and Health

A theme can be:

```text
very strong
but unhealthy
```

or:

```text
moderately strong
but improving
```

Therefore separate:

## Theme Strength

Current market force.

Potential inputs:

- return;
- relative strength;
- flow;
- attention;
- breadth.

## Theme Health

Durability / internal quality.

Potential inputs:

- leadership diversity;
- fundamental confirmation;
- narrative freshness;
- breadth trend;
- catalyst quality;
- crowding;
- response symmetry.

Example:

```text
AI Compute
Strength: 93
Health:   54
```

Interpretation:

> Still powerful, but increasingly fragile.

China:

```text
商业航天
Strength: 62
Health:   81
```

Interpretation:

> Not yet extreme, but internally improving.

This is much more useful than a single ranking.

---

# 149. Theme Pressure

Another concept:

```text
ThemePressure =
unrealized drivers
-
priced-in saturation
```

Positive pressure can come from:

- improving revisions;
- new catalysts;
- expanding attention;
- low crowding;
- lagging price.

Negative pressure:

- exhausted catalysts;
- extreme crowding;
- weak revisions;
- excessive valuation;
- failing breadth.

This attempts to measure:

> How much unresolved force remains behind the theme?

It may be difficult to quantify perfectly, but the mental model is valuable.

---

# 150. Theme Potential Energy vs Realized Motion

Borrow a useful analogy.

A theme can have **potential energy**:

- powerful catalyst;
- low attention;
- low ownership;
- strong economic exposure;
- little price reaction.

Or mostly **realized motion**:

- price already vertical;
- everyone watching;
- high ownership;
- narrative saturated.

This yields four states:

```text
High Potential / Low Motion
    early opportunity

High Potential / High Motion
    powerful expansion

Low Potential / High Motion
    momentum / possible late cycle

Low Potential / Low Motion
    dormant / irrelevant
```

This conceptual matrix is useful for discovery even if the eventual implementation uses different terminology.

---

# 151. Narrative-to-Capital Conversion Rate

Some themes receive enormous attention but little capital.

Others convert attention into buying immediately.

Define:

```text
NarrativeCapitalConversion =
Δ flow / Δ attention
```

Possible interpretations:

### High attention + high conversion

Narrative is monetizing into demand.

### High attention + low conversion

Spectators, skepticism, or saturation.

### Low attention + high flow

Institutional / stealth accumulation.

This could become surprisingly useful.

---

# 152. Capital-to-Price Conversion Rate

Similarly:

```text
CapitalPriceConversion =
Δ price / Δ flow
```

Low conversion:

- absorption;
- hidden supply;
- mechanical flow;
- weak demand elasticity.

High conversion:

- thin supply;
- squeezed positioning;
- reflexive momentum.

A change in conversion can signal regime transition.

---

# 153. Information-to-Price Elasticity

For each theme/catalyst class:

```text
InfoPriceElasticity =
abnormal return / information surprise
```

Track how it changes through lifecycle.

This provides a quantitative expression of:

> “Good news no longer works.”

That can be a distribution signal.

---

# 154. Theme Reflexivity Score

Some themes become self-reinforcing.

Loop:

```text
Price rises
    ↓
Attention rises
    ↓
ETF / retail flows rise
    ↓
Price rises further
    ↓
Media coverage expands
    ↓
New companies associated
```

Create a reflexivity estimate from:

- price → attention sensitivity;
- attention → flow sensitivity;
- flow → price sensitivity.

High reflexivity can produce powerful continuation.

It can also produce violent reversals.

Therefore:

```text
ReflexivityStrength
+
ReflexivityDirection
```

matter.

---

# 155. Theme Fragility Surface, Not One Score

Fragility should vary by shock type.

A theme may be vulnerable to:

- rates;
- commodity;
- policy;
- earnings;
- liquidity;
- geopolitical;
- valuation.

Build:

```text
FragilityToRates
FragilityToLiquidity
FragilityToPolicy
FragilityToEarnings
FragilityToCommodity
FragilityToLeaderFailure
```

This allows scenario analysis.

Example:

> AI Power is crowded but currently more fragile to capex disappointment than to rates.

That is much more actionable.

---

# 156. Theme Confidence Must Be Evidence-Aware

A theme state should expose:

```text
DataCoverage
EvidenceQuality
ModelAgreement
HistoricalSampleSize
CurrentNovelty
```

Confidence should drop when:

- ontology is new;
- data sparse;
- cross-signals disagree;
- current state is historically novel.

This prevents false precision.

---

# 157. Theme Uncertainty Is Itself Information

If the system cannot agree whether a theme is:

```text
Consolidation
or
Distribution
```

that uncertainty may matter.

Track:

```text
StateEntropy
```

Low entropy:

> clear state.

High entropy:

> transition / ambiguity.

Transitions often create both the best opportunities and greatest risk.

---

# 158. Theme Attention Efficiency

Possible:

```text
AttentionEfficiency =
fundamental information generated / total attention
```

A theme flooded with low-value repetitive discussion has low efficiency.

A theme with modest attention but high-value filings, contracts, and revisions has high efficiency.

This concept may help distinguish:

- research-driven discovery;
- pure social speculation.

---

# 159. Theme Evidence Velocity

Track whether hard economic evidence is catching up to the story.

Inputs:

- contracts;
- revenue;
- orders;
- capex;
- guidance;
- customer adoption;
- margins.

```text
EvidenceVelocity
```

This becomes critical after narrative ignition.

### Healthy secular theme

Narrative leads → evidence accelerates.

### Fragile theme

Narrative leads → evidence stalls.

---

# 160. Theme Legitimacy Curve

Combine:

```text
Narrative
EconomicEvidence
MarketBehavior
```

through time.

Possible states:

```text
Speculative Emergence
Narrative-Led Validation
Fundamentally Confirmed
Mature Economic Theme
Narrative Decay
```

This avoids treating every early narrative as fraudulent or every mature theme as permanent.

---

# 161. Cross-Theme Contagion Matrix

Themes can activate one another.

Example:

```text
AI Compute
   ↓
AI Power
   ↓
Nuclear
   ↓
Uranium
```

Or:

```text
Gold
   ↓
Gold miners
   ↓
Silver
   ↓
Silver miners
```

Learn:

```text
P(theme_B activation | theme_A shock)
```

conditional on state.

This can detect second-order opportunities before conventional sector rotation.

---

# 162. Theme Causal Distance

Not all beneficiaries are equally close to the catalyst.

Assign graph distance:

```text
Direct
1-hop
2-hop
3-hop
```

Early-cycle:

capital may focus on direct beneficiaries.

Later:

capital searches farther down the graph.

A rising average causal distance of outperformers could indicate:

- healthy diffusion;
- or late-stage speculative stretching.

The distinction depends on economic evidence and lifecycle.

---

# 163. Theme Frontier

Define the **frontier** as the set of newly activated nodes at the edge of narrative expansion.

Example:

```text
AI core already known:
GPU / networking

Theme frontier:
power transformers
cooling
gas turbines
nuclear fuel
```

Tracking the frontier may become one of the most useful discovery features.

It answers:

> Where is the market extending the theme next?

---

# 164. Hidden Beneficiary Engine

Use causal graph + economic exposure to find:

```text
high exposure
low narrative recognition
low trading recognition
```

Potential score:

```text
HiddenBeneficiary =
EconomicExposure
× CatalystActivation
× EvidenceQuality
× (1 - NarrativeExposure)
× (1 - MarketRepricing)
```

This is very close to Mastermind's “find it before they chase it” product philosophy.

---

# 165. Narrative Excess Engine

The opposite:

```text
high narrative
high market repricing
low economic evidence
```

Potential conceptual score:

```text
NarrativeExcess =
NarrativeExposure
+ TradingExposure
- EconomicEvidence
```

But lifecycle-condition it.

Early-stage optionality can justify high narrative excess.

Late-stage evidence failure is more concerning.

---

# 166. Theme Opportunity Matrix

A simple product-level representation:

```text
                    FUNDAMENTAL / CATALYST QUALITY
                        LOW                 HIGH
                ┌──────────────────┬──────────────────┐
LOW ATTENTION   │ Dormant / Avoid  │ Hidden Discovery │
                ├──────────────────┼──────────────────┤
HIGH ATTENTION  │ Speculative      │ Confirmed Trend  │
                │ / Fragile        │ / Crowded        │
                └──────────────────┴──────────────────┘
```

Then add price extension as a third axis.

This gives a very intuitive way to explain opportunities.

---

# PART XIII — FULL EXAMPLES: HOW THE ORGANISM WOULD THINK

# 167. Example A — AI Infrastructure

Suppose the world state:

```text
Macro:
    real yields falling modestly
    growth stable
    credit benign

Corporate:
    hyperscaler capex revisions rising

Theme:
    GPU leaders already extended
    networking strong
    power equipment accelerating
    cooling breadth widening

Attention:
    core AI high
    power/cooling attention accelerating from low base

Flow:
    ETFs positive
    options activity spreading downstream
```

A conventional platform shows:

> VRT +5%, ETN +3%, NVDA +1%.

Mastermind reasons:

### Theme interpretation

```text
AI Infrastructure:
    Expansion remains intact.

Internal migration:
    Compute → Physical Infrastructure.

Narrative propagation:
    Still positive.

Leadership:
    Renewing rather than collapsing.

Crowding:
    High in GPU;
    moderate in power/cooling.

Fundamental evidence:
    improving.

Theme death probability:
    low.
```

### Opportunity implication

The best opportunity may no longer be the original leader.

The frontier is migrating toward:

- power;
- cooling;
- grid;
- construction;
- selected generation.

### Risk implication

A top-recognition system that watches only NVDA extension could incorrectly declare:

> “AI topping.”

The Theme Graph sees:

> “Leadership migration inside a still-expanding economic system.”

This is exactly why the projects should be integrated.

---

# 168. Example B — Commercial Space Across US and China

Catalyst:

```text
major launch / infrastructure / procurement announcement
```

US response:

```text
launch leader +12%
satcom +9%
components +4%
```

Global Theme node updates:

```text
Space Economy CatalystActivation ↑
NarrativePropagation ↑
US Theme Strength ↑
```

China pre-open engine asks:

- Is the catalyst economically relevant to Chinese suppliers?
- Is it a generic “space is exciting” story or actual supply-chain transmission?
- What happened historically after large US space-theme shocks?
- What is A-share sentiment state?
- Is 商业航天 already crowded?
- Which Chinese companies have genuine economic exposure vs narrative-only exposure?

Auction:

```text
leader gaps +7%
secondaries +1%
theme breadth weak
```

Interpretation:

> Recognition concentrated; not yet broad expansion.

Later:

```text
component names accelerate
breadth 35% → 71%
turnover broadens
two limit-ups seal early
```

State updates:

```text
CN Space:
Catalyst → Discovery → Expansion probability rises
```

Mastermind did not merely translate a US basket.

It translated a **global catalyst through a local market ecology**.

---

# 169. Example C — Silver Miner Dislocation

World:

```text
Silver:
bullish regime

Silver price:
temporarily weak on day

Company CDE:
earnings headline miss
but
core cash generation strong
non-recurring transaction cost

CDE:
-10%

HL:
-4%

Other peers:
mostly resilient

Gold:
stable
NEM:
positive
```

Graph:

```text
CDE idiosyncratic event
    ↓
sympathy pressure on HL
```

Dislocation engine asks:

> Did the information alter silver macro thesis?

No.

> Did it alter HL fundamentals?

No meaningful direct evidence.

> Are peers confirming industry deterioration?

No.

> Is commodity trend broken?

No.

Candidate:

```text
Peer Contagion Dislocation
```

If silver subsequently strengthens overnight, the expected relationship becomes even more favorable.

This is what it means for the Theme Graph to become an alpha engine.

---

# 170. Example D — China Sentiment Ice Recovery

State:

```text
Sentiment:
18 → 24 → 33

Turnover:
bottoming

Limit-ups:
rising

Failed boards:
falling

Prior-limit-up premium:
turns positive

Highest board:
still low

Broad index:
flat
```

A conventional market view:

> CSI 300 unchanged.

Mastermind:

```text
Speculative Ecology:
Early recovery.

Reinforcement:
Improving.

Theme ignition probability:
Rising.

Best environment:
First-wave emerging themes,
not late high-board chasing.
```

The system could favor:

- low-base theme discovery;
- early leaders;
- improving breadth.

This is a different market from one where the index is also flat but sentiment is:

```text
82 → 74 → 65
```

---

# 171. Example E — Theme Mania vs Healthy Expansion

Theme A:

```text
5D return             +28%
Attention             extreme
Narrative growth      slowing
Breadth               81% → 52%
Leader dependency     rising
Good-news response    weakening
Options calls         extreme
New entrants          low-purity
```

Theme B:

```text
5D return             +11%
Attention             moderate
Narrative growth      accelerating
Breadth               42% → 76%
Leadership renewal    strong
Revisions             positive
Institutional flow    rising
```

A momentum screen may rank A first.

A market-intelligence organism may prefer B.

That is precisely the kind of differentiated retail insight the project can create.

---

# 172. Example F — Narrative Leads Fundamentals Correctly

A new technology appears.

Company:

```text
current revenue exposure    4%
narrative exposure         75%
trading exposure           82%
contracts                   rising
capex                       rising
management emphasis         rising
```

A naïve theme-washing model says:

> Overhyped.

Mastermind says:

```text
Narrative leads current revenue,
but evidence velocity is strongly positive.
Theme optionality high.
```

Interpretation:

> Emerging legitimate exposure.

The system should learn how often narrative-first cases later become fundamental.

---

# 173. Example G — Narrative Fails to Become Economics

Another company:

```text
current revenue exposure    2%
narrative exposure         88%
trading exposure           91%
contracts                   none
capex                       unchanged
R&D                         unchanged
management language         promotional
evidence velocity           flat
price                       +140%
```

Now:

```text
Narrative Excess extreme
Theme Washing Risk high
Fragility rising
```

The same economic/narrative gap means something different because evidence failed to catch up.

---

# 174. Example H — US Theme-to-China Transmission Failure

US:

```text
solar names +10%
```

China next session:

```text
solar auction weak
local policy negative
turnover rotating elsewhere
```

A simple cross-market strategy fails.

Mastermind:

```text
Global Theme shock positive
but
CN Local Expression incompatible with local state.
```

This becomes a learned episode.

Next time:

```text
US shock
+
CN local confirmation required
```

receives more weight.

---

# PART XIV — USER EXPERIENCE: HOW TO MAKE THE INTELLIGENCE LEGIBLE

# 175. The User Should See Conclusions With Expandable Evidence

A key product principle:

Do not expose the whole Neural Web by default.

Surface:

```text
Commercial Space

STATE
Expansion

STRENGTH
78

HEALTH
84

ATTENTION
Accelerating

FLOW
Positive

CROWDING
Moderate

WHY NOW
Procurement + global space catalyst

WHAT CHANGED TODAY
Breadth +19 pts
Secondaries activating
Leader dependency falling

RISK
Auction gap concentrated
Valuation elevated

NEXT EXPECTED
Continuation requires breadth to remain >70%
```

Then allow drill-down.

This makes deep intelligence usable.

---

# 176. Every Score Should Answer “Why?”

If user clicks:

```text
Health = 84
```

show:

```text
+ strong breadth
+ leadership renewal
+ positive revisions
+ low failed-breakout rate
- rising valuation
- moderate crowding
```

Never build black-box mystique.

Trust compounds through explainability.

---

# 177. “What Changed?” Should Be a Primary Product Surface

Humans struggle to detect slow state transitions.

A daily/real-time Mastermind surface should answer:

## Market

What changed?

## Themes

What entered or left important states?

## Relationships

What broke?

## Attention

What accelerated?

## Capital

Who changed behavior?

## Expectations

What should happen next?

This is arguably more useful than another dashboard homepage.

---

# 178. “Why Is This Moving?” Becomes a Native Query

User:

> Why is Commercial Space moving?

Mastermind retrieves:

```text
Catalyst
Theme propagation
US/CN cross-market link
leaders
breadth
flow
participants
historical analogs
```

Then answers:

```text
Primary driver:
new procurement narrative

Confirmation:
5 of 7 high-exposure names accelerating

Secondary driver:
US space basket overnight strength

Capital:
游资 participation rising

Lifecycle:
Discovery → Expansion

Risk:
leader gap extended; broad continuation still unconfirmed
```

The answer is grounded in the graph.

---

# 179. “What Is Moving Before Price?” Becomes a Discovery Surface

A distinctive Mastermind page could rank:

```text
Attention ↑, Price flat
Flow ↑, Price flat
Revisions ↑, Price flat
Catalyst ↑, Attention low
Narrative breadth ↑, Price breadth flat
Economic evidence ↑, Narrative low
```

This is exactly where the Dynamic Theme Graph becomes a discovery engine rather than a prettier market map.

---

# 180. “What Is Breaking?” Becomes the Inverse Surface

Rank:

```text
Price high, Breadth falling
Attention high, Propagation falling
Good news, Weak price response
Flow positive, Price falling
Leader new high, secondaries weak
Narrative high, evidence flat
```

This serves:

- risk management;
- top recognition;
- short research.

---

# 181. A Theme Timeline Could Be More Powerful Than a Static Chart

For each theme:

```text
Jan 12   Catalyst detected
Jan 15   Theme born
Jan 21   Attention acceleration
Jan 25   Breadth expansion
Feb 03   Institutional participation
Feb 18   Leadership migration
Mar 02   Mania warning
Mar 07   Breadth divergence
Mar 10   Distribution state
```

This is a narrative of the market's evolution.

Humans understand timelines intuitively.

It also provides explainable historical memory.

---

# 182. Historical Analog Cards

For current theme state:

```text
Closest analogs

1. 2024 episode A       similarity 84%
2. 2021 episode B       similarity 77%
3. 2019 episode C       similarity 69%
```

But always include:

```text
Important differences
```

This prevents naïve pattern matching.

---

# 183. Confidence Needs a Human-Readable Decomposition

Instead of:

```text
Confidence: 73%
```

show why:

```text
Evidence coverage       strong
Historical sample       moderate
Model agreement         strong
Current novelty         moderate
Data freshness          strong
```

A precise number without epistemic context is fake certainty.

---

# 184. User-Facing Terminology Can Be Simpler Than Internal Ontology

Internally:

```text
NarrativePropagationAcceleration
```

User-facing:

> Story spreading faster.

Internally:

```text
CatalystResponseElasticity
```

User-facing:

> Good news is producing less upside.

The intelligence can be sophisticated without making the product unreadable.

---

# PART XV — VALIDATION: HOW TO KEEP THE SYSTEM FROM BECOMING A BEAUTIFUL HALLUCINATION

# 185. Every Clever Metric Must Earn Its Place

Metrics such as:

- Theme Gravity;
- Theme Entropy;
- Narrative R0;
- Theme Pressure;
- Hidden Beneficiary;
- Theme Health;

are **research hypotheses**, not truths.

The next session should resist fetishizing names.

Each must be tested for:

```text
stability
incremental predictive value
interpretability
cross-era robustness
cross-market robustness
leakage
redundancy
```

If `Theme Gravity` adds nothing beyond residual correlation and breadth, discard the branding.

The creative phase should be expansive.

The validation phase should be ruthless.

---

# 186. Avoid Composite-Score Soup

A common failure mode:

```text
ThemeScore =
0.1 momentum
+ 0.1 flow
+ 0.1 attention
+ ...
```

with arbitrary weights.

This produces visually satisfying nonsense.

Better:

1. preserve raw interpretable dimensions;
2. learn conditional relationships;
3. calibrate with history;
4. expose uncertainty.

Composite scores can be user-facing summaries after validation.

They should not substitute for understanding.

---

# 187. Do Not Ask the LLM to Invent Historical Weights

The Neural Web research already solved this conceptually.

The LLM should propose hypotheses.

History should calibrate weights.

Example:

LLM:

> “Failed-board rate may matter more during sentiment recovery.”

Research engine:

- backfill;
- segment regimes;
- test;
- walk forward;
- estimate stability.

Only then does the weight change.

---

# 188. Theme Discovery Creates Severe Look-Ahead Risk

This deserves emphasis.

If the system discovers “AI power” in 2026 and retroactively applies today's constituents to 2023, it can manufacture impossible historical performance.

Therefore maintain:

```text
KnowledgeTime
```

for:

- theme existence;
- constituent membership;
- evidence;
- catalyst;
- analyst coverage.

Historical research should reconstruct what the system could reasonably have known then.

---

# 189. Survivorship Bias Is Not Just a Stock-Universe Problem

Themes die.

Companies disappear.

Names change.

Narratives fail.

A historical theme study that only retains successful modern themes will exaggerate alpha.

Store:

- failed themes;
- obsolete themes;
- delisted constituents;
- bankrupt companies;
- temporary narratives.

Mastermind's memory should include failures.

---

# 190. Avoid Semantic Leakage

A frontier model trained on later history may know that:

> Company X eventually became an AI winner.

When reconstructing a 2022 theme state, the system must not use that latent knowledge as admissible evidence.

Possible safeguards:

- retrieve only point-in-time source documents;
- require cited evidence;
- separate model general knowledge from admissible historical evidence;
- validate historical edges deterministically.

This is one of the hardest problems in AI-assisted historical research.

---

# 191. Causal Stories Must Be Tested Against Counterfactuals

LLMs are extremely good at constructing plausible narratives.

That is dangerous.

If Mastermind says:

> “Gold rose because real yields fell,”

test:

- did comparable days support that relation?
- did DXY matter?
- did China demand contribute?
- did positioning dominate?
- what did gold do when yields fell in similar regimes?

Narrative should trigger research, not substitute for it.

---

# 192. Cross-Market Correlation Is Not Automatically Transmission

If US space and China space move together, possible causes include:

- shared catalyst;
- global risk-on;
- coincidence;
- commodity/input link;
- direct narrative transmission.

The graph should distinguish:

```text
co-movement
from
causal transmission
```

This is why causal-confidence and predictive-strength fields are separate.

---

# 193. Validate Lifecycle States Against Outcomes

For each predicted state:

```text
Discovery
Expansion
Mania
Distribution
```

measure:

- forward return distribution;
- drawdown;
- volatility;
- breadth transition;
- probability of next state.

If “Distribution” does not predict materially different outcomes, the label is decorative.

---

# 194. Calibration Matters More Than Classification Accuracy

A state model saying:

```text
P(Expansion) = 70%
```

should produce expansion roughly 70% of the time in comparable validated samples.

This is more valuable than merely being “right” often.

Probability calibration allows:

- position sizing;
- risk budgeting;
- expectation management.

---

# 195. Maintain an Outcome Evaluator

Every important output should eventually be evaluated.

Record:

```text
Prediction
Horizon
Confidence
Reasoning
State
Outcome
Error
```

Then ask:

> Which kinds of reasoning fail?

This feeds the Research Cortex.



# PART XVI — RESEARCH CORTEX: HOW THE SYSTEM CAN DISCOVER ITS OWN MISSING ORGANS

# 196. The Research Cortex Is Potentially the Long-Term Moat

The most ambitious Neural Web concept is not a giant LLM deciding trades.

It is a system that learns where its own information architecture is incomplete.

Example:

```text
Repeated failure:
Gold-miner predictions wrong when Chinese demand diverges.

Hypothesis:
Missing China physical/ETF demand.

Action:
Propose new China gold-demand lobe.
```

Another:

```text
Repeated failure:
Biotech theme forecasts break around FDA events.

Hypothesis:
Catalyst calendar incomplete.

Action:
Propose FDA-event lobe.
```

Another:

```text
Repeated failure:
Semiconductor supplier forecasts fail when hyperscaler capex expectations shift.

Hypothesis:
Missing direct capex-transmission state.

Action:
Build hyperscaler capex lobe.
```

This is qualitatively different from humans deciding upfront which data matters.

The system begins asking:

> **What information would have allowed me to predict the things I repeatedly get wrong?**

That is a research question, not a trading signal.

---

# 197. Separate Operating Cortex From Research Cortex

This architectural separation is essential.

## Operating Cortex

Responsibilities:

- interpret current world state;
- retrieve memory;
- detect contradictions;
- form hypotheses;
- issue forecasts;
- explain current conditions.

It should **not** freely rewrite production systems.

## Research Cortex

Responsibilities:

- inspect systematic errors;
- identify missing representations;
- propose candidate features/lobes;
- design experiments;
- assess alternative explanations;
- prioritize research.

This prevents a charismatic model from continuously changing the live system based on one anecdote.

---

# 198. Research Cortex Loop

Conceptually:

```text
Prediction Failure
      ↓
Error Clustering
      ↓
Hypothesis
      ↓
Possible Missing Variable / Representation
      ↓
Acquire or Construct Data
      ↓
Historical Backfill
      ↓
Replay
      ↓
Walk-Forward Validation
      ↓
Stability / Leakage / Redundancy Check
      ↓
Candidate Improvement
      ↓
Human / Governance Review
      ↓
Production
```

This is how Mastermind can become a **scientific system** rather than merely an AI-enabled dashboard.

---

# 199. Error Clustering May Be More Valuable Than Raw Accuracy

Suppose Prophet has 67% accuracy.

The interesting research question is not only:

> How do we get 68%?

It is:

> What kinds of states produce the remaining failures?

Cluster misses by:

```text
regime
theme
catalyst
market
horizon
capital mix
novelty
surprise pattern
```

Possible discovery:

```text
Most false-positive AI continuation calls occur when:
    breadth is high
    but
    revision breadth has already rolled over
    and
    options speculation is extreme.
```

That becomes a new semantic belief.

---

# 200. The Research Cortex Can Discover Better Representations, Not Only More Data

A failure does not always mean:

> We need another feed.

It may mean the existing data is represented incorrectly.

Example:

Raw input:

```text
sentiment = 38
```

Repeated failures suggest:

> Level is weak; velocity matters.

New representation:

```text
sentiment_level
sentiment_velocity
sentiment_acceleration
```

Another:

```text
theme return
```

becomes:

```text
theme residual return
theme breadth
leader dependency
```

This is **representation learning at the architecture level**.

That may be more valuable than adding thousands of feeds.

---

# 201. Data Density → Relationship Density → Experience Density

Retain one of the strongest Neural Web conclusions:

```text
Data Density
    ↓
Relationship Density
    ↓
Experience Density
    ↓
Intelligence
```

Mastermind is already becoming rich in raw data.

The next frontier is not “how many more dashboards can we ingest?”

It is:

- how many useful relationships can we represent;
- how many expectations can we form;
- how many historical experiences can we accumulate;
- how effectively can those experiences alter future behavior?

Twenty deeply stateful expert lobes may produce more intelligence than two thousand passive planes.

---

# PART XVII — DATA AND EVIDENCE ARCHITECTURE

# 202. Every Observation Needs Provenance

A market cognition system becomes dangerous if it cannot distinguish:

```text
direct fact
vendor transformation
Mastermind estimate
LLM inference
```

Every datum/belief should carry:

```text
source
observation_time
knowledge_time
method
confidence
licensing_class
revision_status
```

Example:

```text
Northbound direction:
    type: inferred
    source: public aggregate activity + internal model
    confidence: 0.61
```

versus:

```text
SSE turnover:
    type: observed
    source: exchange
    confidence: 1.0
```

This helps both model reasoning and user trust.

---

# 203. Evidence Objects Should Be First-Class Nodes

Instead of storing:

```text
Company X → AI Power = 0.83
```

store the evidence underneath:

```text
ThemeEdge
    ├── filing paragraph
    ├── earnings-call statement
    ├── contract
    ├── capex data
    ├── analyst consensus
    ├── trading beta
    └── news association
```

Then:

```text
Score = aggregation(evidence)
```

This makes theme relationships auditable.

It also allows a future model to reinterpret old evidence using better reasoning.

---

# 204. Evidence Can Contradict

Do not design evidence as only additive.

Example:

```text
Positive:
management says AI demand accelerating.

Negative:
segment revenue unchanged.

Negative:
capex flat.

Positive:
options and trading beta high.
```

The correct output may be:

```text
Narrative Exposure: high
Economic Confirmation: low
Market Exposure: high
```

Contradiction is intelligence.

---

# 205. Source Reliability Should Be Learned by Domain

Different source types have different historical reliability.

Examples:

- SEC filing;
- exchange announcement;
- management interview;
- sell-side note;
- financial press;
- anonymous social post.

But do not hard-code a permanent global hierarchy.

A niche specialist may predict a semiconductor supply issue earlier than a formal filing.

Track:

```text
SourceReliabilityByDomain
```

and learn from outcomes.

---

# 206. Temporal Semantics Are Critical

There are several “times”:

```text
Event Time:
    when the real-world thing happened

Publication Time:
    when source released it

Ingestion Time:
    when Mastermind received it

Knowledge Time:
    when system could legitimately know it

Effective Time:
    when it begins affecting fundamentals
```

Example:

A contract signed June 1, announced June 5, ingested June 5, revenue begins next year.

All four matter.

Historical replay requires `Knowledge Time`.

Causal modeling may care about `Effective Time`.

---

# 207. Version Every Market Rule

The China price-limit example illustrates this.

Store:

```text
MarketRule {
    jurisdiction
    venue
    security_type
    effective_from
    effective_to
}
```

Rules include:

- price limits;
- IPO exceptions;
- ST regimes;
- auction mechanics;
- disclosure policies;
- Stock Connect dissemination rules.

Historical features must be computed under the rule that existed then.

---

# 208. Corporate Identity Resolution Is Part of Intelligence Infrastructure

For US filings and ownership:

- tickers change;
- CUSIPs change;
- companies merge;
- ADRs differ;
- share classes exist.

For China:

- stock names change;
- ST designations change;
- restructurings occur;
- corporate groups have listed affiliates.

The graph needs canonical entities.

Otherwise historical theme membership and participant behavior become corrupted.

---

# 209. Public US Data Gives a Strong Baseline

Several primary sources are particularly valuable.

## SEC EDGAR

Official SEC APIs expose company submission history and extracted XBRL facts; Form 13F datasets are also published in structured form.

Potential use:

- corporate semantic evidence;
- ownership;
- insider filings;
- event history.

## FINRA

FINRA publishes short interest and off-exchange short-sale volume/transactions.

Crucial semantic distinction:

> Short-sale volume is **not** short interest.

The system should encode that explicitly rather than repeat common retail misconceptions.

## OCC

OCC publishes options volume and open-interest reports, including queries by account type and exchange over available historical windows.

This supplies useful public baseline derivatives state, even if richer trade-level classification requires commercial data.

---

# 210. China Exchange Data Should Be the Ground Truth for Rules

For market-structure rules, prioritize:

- Shanghai Stock Exchange;
- Shenzhen Stock Exchange;
- Beijing Stock Exchange;
- HKEX / Stock Connect official notices.

Examples currently relevant:

- STAR stocks generally move under a 20% daily range after the first five IPO trading days, which have no regular price limit;
- ChiNext similarly uses a 20% daily range after its first five IPO trading days;
- BSE stocks use a 30% daily price limit under current rules;
- Stock Connect real-time Northbound buy/sell/total turnover dissemination was changed in 2024, so old-style live Northbound flow assumptions should not be silently carried forward.

The exact implementation should always use versioned official rules.

---

# 211. Research Data Licensing Must Be Treated as Architecture

A system can legally analyze data internally yet be unable to redistribute raw fields to paying users.

Therefore tag datasets:

```text
InternalAnalysisAllowed
DerivedAnalyticsAllowed
DisplayAllowed
RedistributionAllowed
RetentionLimits
AttributionRequired
```

This affects product architecture.

The moat should increasingly be **derived intelligence** rather than dependence on redistributing vendor raw data.

---

# PART XVIII — WHAT SHOULD BE UNIVERSAL VS MARKET-SPECIFIC

# 212. Universal Cognitive Primitives

The following should be common across markets:

```text
Entity
Relationship
State
Trajectory
Event
Catalyst
Theme
Narrative
Attention
Capital
Participant
Expectation
Surprise
Dislocation
Memory
Analogue
Confidence
Novelty
Outcome
```

These are the vocabulary of market cognition.

---

# 213. Universal Theme Primitives

Every market can support:

```text
Economic Exposure
Narrative Exposure
Trading Exposure
Catalyst Activation
Breadth
Leadership
Flow
Attention
Lifecycle
Fragility
Historical Analog
```

Data availability will differ.

The conceptual schema should remain common.

---

# 214. China-Specific Primitives

Native China concepts should remain explicit:

```text
涨停
跌停
连板
炸板
封单
竞价
龙虎榜
游资
昨日涨停溢价
情绪周期
政策资金
```

Do not force these into awkward US analogies.

---

# 215. US-Specific Primitives

Native US concepts include:

```text
Options surface
ETF flow mechanics
13F ownership
short interest
borrow / utilization when licensed
earnings revisions
analyst dispersion
insider activity
activism
```

Again: common cognition, different sensors.

---

# 216. Global Nodes Bridge the Two

Global nodes include:

```text
commodities
rates
FX
geopolitics
technologies
global supply chains
multinational capex
policy conflicts
```

These connect local markets.

Example:

```text
Silver
    ├── US miner theme
    ├── China precious-metals theme
    ├── solar input-cost theme
    └── strategic minerals narrative
```

One global economic node, several local market expressions.

---

# PART XIX — STRATEGIC PRODUCT MOAT

# 217. The Classification Is Not the Moat

This conclusion from the prior US theme memo is correct.

Anyone with a frontier model can generate:

> “Here are 300 themes.”

That has almost no durable value.

The moat comes from compounding layers:

```text
Dynamic Theme Graph
+
Point-in-Time Evidence
+
Historical Theme States
+
Market Behavior
+
Alternative Data
+
Participant Intelligence
+
Cross-Market Relationships
+
Outcome Memory
+
AI Reasoning
```

The longer the system runs and replays history, the richer its learned state becomes.

---

# 218. Theme History Is More Defensible Than Theme Labels

Competitor can copy label:

```text
AI Power
```

Harder to copy:

```text
AI Power:
    4 years of point-in-time constituent evolution
    catalyst history
    breadth history
    flow history
    attention history
    analog library
    state transitions
    learned outcome distributions
```

The moat is accumulated experience.

---

# 219. Relationship History Is Even More Defensible

Harder still:

```text
When US AI Power enters state X
under macro state Y
and China sentiment is Z,
which A-share electrical-equipment subtheme usually responds,
with what lag,
and when does the transmission fail?
```

That requires:

- ontology;
- historical data;
- local-market understanding;
- state-conditioned backtests.

This is not easy to clone from a screenshot.

---

# 220. Product Moat Could Be “Intelligence Compression”

Bloomberg's moat is partly information access and workflow.

Mastermind's potential moat:

> **Compress an enormous market state into the few changes that matter, while retaining drill-down evidence.**

A user with ten minutes should understand:

- what changed;
- what is emerging;
- what is breaking;
- what deserves research.

That is valuable even without automated trading.

---

# 221. Retail UX + Institutional Depth Is the Wedge

Institutional thematic systems can be powerful but expensive and workflow-heavy.

Retail systems can be intuitive but shallow.

The product wedge is:

```text
institutional depth
+
retail legibility
+
AI explanation
```

同花顺 demonstrates how much ecology retail users can actually consume when it is presented intuitively.

Mastermind can apply that lesson globally.

---

# 222. Cross-Market Theme Intelligence Is Especially Differentiated

A user should eventually be able to ask:

> “US space ripped Friday. Which China names are genuine Monday beneficiaries, which are narrative proxies, and what does historical transmission say?”

This combines:

- global theme graph;
- local market ontology;
- overnight state;
- causal exposure;
- historical lead-lag;
- China auction/limit-up ecology.

That is a distinctive capability.

---

# PART XX — WHAT NOT TO BUILD

# 223. Do Not Build a Giant Static Ontology Before Testing Usefulness

A temptation:

> “Classify every listed company into 3,200 microthemes first.”

That could consume enormous effort before proving alpha.

Better:

- seed useful major themes;
- validate edge semantics;
- build point-in-time evidence;
- create theme states;
- test predictive questions;
- expand where the graph demonstrates value.

Theia's scale proves feasibility, not that Mastermind needs identical scale on day one.

---

# 224. Do Not Build 2,000 Scores

Keep raw state interpretable.

A screen with:

```text
Narrative Score
Flow Score
Heat Score
Gravity Score
Entropy Score
Pressure Score
Health Score
Potential Score
...
```

will recreate dashboard overload.

Internally maintain rich dimensions.

Externally surface the few that matter for the decision.

---

# 225. Do Not Turn Every Correlation Into a Causal Story

Graph edges need types and confidence.

Use:

```text
correlated_with
```

when that is all we know.

Upgrade to causal only with evidence.

---

# 226. Do Not Turn Every Theme Into an Investable Basket

Some themes are useful as **explanatory states** even if not suitable for portfolio construction.

Examples:

- “AI Power Scarcity”
- “Defense Procurement Acceleration”
- “China Sentiment Recovery”

The theme ontology can serve reasoning without becoming a tradable index.

---

# 227. Do Not Force China and US Into the Same Feature Set

The unified architecture is conceptual, not cosmetic.

A US stock does not need a fake “连板 equivalent.”

A Chinese stock does not need every US options concept if data is unavailable.

Unification happens at:

```text
state
event
relationship
expectation
memory
```

not at superficial feature parity.

---

# 228. Do Not Make the Cortex Omniscient

The system should be allowed to say:

```text
We have insufficient data.
The state is novel.
Two interpretations remain plausible.
```

Epistemic humility is a feature.

---

# 229. Do Not Confuse AI Fluency With Evidence

A fluent explanation can be wrong.

Every important claim should resolve to:

- evidence;
- model;
- historical statistic;
- inference.

The system should distinguish them visibly.

---

# 230. Do Not Optimize for “Looks Institutional”

Fancy dashboards are easy.

The difficult part is:

- correct semantics;
- point-in-time integrity;
- historical memory;
- calibrated expectations.

If the intelligence is real, the UI can become elegant later.



# PART XXI — RESEARCH PROGRAM: HOW TO TURN THE IDEAS INTO KNOWLEDGE BEFORE TURNING THEM INTO SOFTWARE

# 231. The Next Step Is Not “Build Everything”

This document intentionally contains more ideas than should be implemented.

The correct next phase is **research compression**.

Ask of every major concept:

1. Can it be observed?
2. Can it be reconstructed historically?
3. Does it describe something economically meaningful?
4. Does it improve prediction, risk detection, or explanation?
5. Is it redundant with simpler variables?
6. Is it stable across eras?
7. Is it useful in both US and China or only locally?
8. Can it be made point-in-time?
9. Is the required data legally usable?
10. Does the insight justify engineering complexity?

This is how a creative brainstorming project becomes disciplined research.

---

# 232. Research Track A — Reconstruct Theme State Historically

Start with a manageable set of historically important themes.

US candidates:

```text
AI Infrastructure
Cloud
Semiconductor Cycle
Space Economy
Defense Modernization
Gold / Precious Metals
Uranium / Nuclear
EVs
Solar
GLP-1
Crypto Infrastructure
Robotics
```

China candidates:

```text
AI / 算力
商业航天
机器人
创新药
券商
黄金
有色金属
光伏
新能源车
半导体
低空经济
军工
```

For each episode reconstruct:

```text
constituents as known then
economic exposure
narrative exposure
trading exposure
price
breadth
attention where available
flows
catalysts
macro state
local market state
```

Then label:

```text
Discovery
Expansion
Consolidation
Re-Acceleration
Mania
Distribution
Collapse
```

The objective is not immediately to maximize Sharpe.

The first objective is:

> Can humans and models reliably distinguish these states with point-in-time data?

---

# 233. Research Track B — Test Whether Themes Add Information Beyond Sectors

This is a fundamental empirical question.

For every theme factor:

1. regress out broad market;
2. regress out official sector/industry;
3. regress out common style factors;
4. measure remaining structure.

Questions:

- Does theme residual return explain constituent behavior?
- Does theme breadth forecast stock-level returns?
- Does theme lifecycle explain drawdown risk?
- Do theme factors improve Prophet after sector factors already exist?

If the answer is no, the ontology is pretty but economically weak.

If yes, it validates the project at a fundamental level.

---

# 234. Research Track C — Economic vs Narrative vs Trading Exposure

Construct all three for a sample set.

Then study disagreement states.

Examples:

```text
Economic high / Narrative low / Trading low
Economic low / Narrative high / Trading high
Economic high / Narrative high / Trading low
Economic high / Narrative high / Trading high
```

Questions:

- Which state produces best future returns?
- Which transitions matter?
- When does narrative lead fundamentals correctly?
- When does narrative excess revert?
- Does trading exposure usually follow narrative exposure or vice versa?

This one experiment could generate an entire family of proprietary insights.

---

# 235. Research Track D — Theme Breadth and Leadership

Test:

```text
breadth level
breadth velocity
leader concentration
leadership renewal
leader failure
```

against:

- continuation;
- volatility;
- drawdown;
- transition to distribution.

Specifically compare:

```text
Strong index + broad breadth
Strong index + narrowing breadth
Strong index + leadership renewal
Strong index + no replacement leader
```

The goal is to learn the anatomy of theme health.

---

# 236. Research Track E — Attention

Because attention is behaviorally meaningful but ambiguous, test it carefully.

China:

- Baidu search where accessible;
- app heat/popularity data where licensed/obtainable;
- social/forum activity;
- news count;
- 龙虎榜 mentions;
- price-derived attention.

US:

- Google Trends where feasible;
- news;
- social;
- options activity;
- ETF flows;
- media prominence.

Research:

```text
AttentionLevel
AttentionVelocity
AttentionAcceleration
AttentionBreadth
AttentionSource
```

Condition on:

- price extension;
- lifecycle;
- market state.

The key question is not:

> Does attention predict returns?

It is:

> **When is attention discovery, when is it confirmation, and when is it saturation?**

---

# 237. Research Track F — Narrative Propagation

Operationalize the Rₙ idea.

Possible observable proxies:

```text
new companies semantically associated
new subthemes
new analyst coverage
new unique catalysts
new media sources
new social participants
new ETF representation
```

Test whether:

```text
PropagationAcceleration
```

leads:

- price breadth;
- turnover breadth;
- new leaders;
- forward returns.

If not, discard the metric.

If yes, it could become a core Mastermind primitive.

---

# 238. Research Track G — Catalyst Response Elasticity

For earnings/news/policy events estimate:

```text
AbnormalPriceResponse
/
CatalystSurprise
```

Study through lifecycle.

Hypothesis:

### Early/healthy theme

Positive information has high upside elasticity.

### Mature/crowded theme

Positive information has declining upside elasticity.

### Distribution

Bad-news downside elasticity increases.

This could be a powerful top-recognition feature.

---

# 239. Research Track H — China Speculation Ecology

Build event-level data for:

```text
first touch
seal
break
reseal
closing status
board height
prior-day premium
auction
```

Then test:

- next-day continuation;
- leader survival;
- theme survival;
- risk of failed boards.

The output may create an empirical sentiment state far richer than a generic gauge.

---

# 240. Research Track I — Cross-Market Theme Transmission

For global themes, estimate:

```text
US → CN
CN → US
Commodity → US
Commodity → CN
HK → CN
ADR → A-share
```

conditional on:

- catalyst class;
- local sentiment;
- macro;
- crowding;
- time zone.

This is a natural proprietary research program because Mastermind operates across markets.

---

# 241. Research Track J — Dislocation Resolution

For each detected divergence, label outcome:

```text
mean reversion
fundamental catch-up
theme catch-up
continued divergence
relationship regime break
```

The system should learn:

> Which dislocations actually resolve?

This protects against assuming every spread closes.

---

# 242. Research Track K — Theme Lifecycle vs Top Recognition

Combine historical theme episodes with extended-move research.

Questions:

- Which mania states continue?
- Which mania states distribute?
- Does breadth deterioration add value after extension?
- Does narrative exhaustion add value?
- Does low-quality follower participation add value?
- Does good-news response deterioration add value?

This directly bridges long-side theme discovery and short-side fragility detection.

---

# 243. Research Track L — Market Reinforcement

China:

```text
yesterday's limit-ups → T+1 reward
```

US equivalents can be constructed:

```text
yesterday's high-momentum breakouts
earnings gaps
theme leaders
high-call-volume names
```

Ask:

> What behaviors is the market currently rewarding?

This may become a universal concept.

---

# PART XXII — CONCEPTUAL OBJECT MODEL FOR THE NEXT SESSION

The following is **not** a final engineering schema.

It is a way to make the ideas concrete enough that the next AI can reason about interfaces.

# 244. Theme Node

```text
ThemeNode {
    theme_id
    canonical_name
    aliases
    description

    taxonomy_level
    parent_themes[]
    child_themes[]
    adjacent_themes[]

    economic_system
    global_or_local

    lifecycle_state
    lifecycle_probabilities

    strength
    health
    fragility
    crowding
    narrative_state
    attention_state
    flow_state
    fundamental_state

    historical_memory_refs[]
    current_catalysts[]
    active_expectations[]

    evidence_quality
    novelty
    confidence
}
```

---

# 245. Company ↔ Theme Edge

```text
CompanyThemeEdge {
    company_id
    theme_id

    business_exposure
    narrative_exposure
    trading_exposure
    catalyst_activation

    theme_purity
    theme_optionality

    supply_chain_role
    market_role
    causal_distance

    evidence_refs[]
    confidence

    valid_from
    valid_to
    knowledge_time
}
```

This edge is one of the most important objects in the entire architecture.

---

# 246. Theme Market State

```text
ThemeMarketState {
    theme_id
    timestamp

    price_return
    residual_return
    relative_strength

    breadth
    breadth_velocity
    leadership_concentration
    leadership_renewal

    turnover
    liquidity

    capital_confluence
    ETF_state
    options_state

    attention_level
    attention_velocity
    narrative_propagation

    revisions
    valuation

    market_compatibility
    cross_market_confirmation

    expected_next_states
}
```

---

# 247. Market State Object

```text
MarketState {
    market
    timestamp

    direction
    quality
    breadth
    dispersion
    correlation
    liquidity
    volatility

    speculation
    attention
    capital_mix
    concentration

    macro_compatibility
    local_policy_state

    leading_themes[]
    weakening_themes[]
    important_transitions[]
    anomalies[]
}
```

---

# 248. China Speculation State

```text
ChinaSpeculationState {
    timestamp

    limit_up_count
    limit_down_count
    first_board_count
    high_board_count

    max_board_height
    board_survival_curve

    failed_board_rate
    reseal_rate
    seal_quality

    prior_limit_up_reward
    prior_high_board_reward

    auction_state
    retail_attention
    youzi_activity

    sentiment_level
    sentiment_velocity
    sentiment_acceleration
}
```

---

# 249. Participant Node

```text
ParticipantNode {
    participant_id
    observed_identity
    inferred_type

    preferred_themes
    preferred_market_caps
    preferred_catalysts

    holding_horizon
    entry_profile
    exit_profile

    historical_episode_refs
    conditional_success
    confidence
}
```

---

# 250. Event Object

```text
MarketEvent {
    event_id
    entity_id
    timestamp

    type
    magnitude
    percentile
    z_score

    source
    evidence
    confidence

    market_context
    theme_context
    participant_context

    candidate_causes[]
    expected_consequences[]
}
```

---

# 251. Belief Object

```text
Belief {
    subject
    proposition

    direction
    magnitude
    horizon
    confidence

    historical_reliability
    regime_compatibility
    causal_interpretation

    supporting_evidence[]
    contradicting_evidence[]

    novelty
    provenance

    expected_consequences[]
}
```

The belief object is the interface between deterministic lobes and the Cortex.

---

# 252. Expectation Object

```text
Expectation {
    belief_id
    target
    horizon

    expected_range
    probability

    conditions
    invalidation_conditions

    created_at
    expires_at
}
```

This creates a clean path to surprise.

---

# 253. Surprise Object

```text
Surprise {
    expectation_id

    expected
    observed
    deviation

    magnitude
    importance

    suspected_explanations[]
    affected_beliefs[]
    research_priority
}
```

---

# 254. Experience Record

```text
Experience {
    timestamp
    world_state_ref

    observations
    salient_variables

    hypotheses
    predictions
    confidence

    outcomes
    surprises

    error_analysis
    lesson

    semantic_memory_candidates[]
    procedural_memory_candidates[]
}
```

This is the unit of synthetic lived experience.

---

# 255. Relationship Edge

```text
Relationship {
    source
    target

    relation_type

    causal_confidence
    predictive_strength

    horizon
    lag_distribution
    regime_conditions

    valid_from
    valid_to

    historical_evidence
}
```

Possible relation types:

```text
CAUSES
SUPPLIES
BUYS_FROM
COMPETES_WITH
SUBSTITUTES_FOR
LEADS
CORRELATES_WITH
NARRATIVELY_ASSOCIATED_WITH
MEMBER_OF
OWNED_BY
EXPOSED_TO
```

---

# 256. Dislocation Object

```text
Dislocation {
    source_relationship
    expected_state
    observed_state

    deviation
    duration

    alternative_explanations
    invalidating_evidence

    historical_resolution_rate
    confidence

    candidate_trade_expression
}
```

Again, the conceptual point matters more than exact schema.

---

# PART XXIII — THE KEY DIFFERENCE BETWEEN A DASHBOARD AND A COGNITIVE SYSTEM

# 257. A Dashboard Has Values; a Cognitive System Has Beliefs

Dashboard:

```text
Real yield = 1.6%
Gold = +2%
Miners = +3%
```

Cognitive system:

> Real yields have declined for 38 days; the decline recently accelerated following labor weakness. Gold initially underreacted, then broke out; miners have now begun outperforming. This resembles prior early-easing precious-metal episodes, although current fiscal policy is more expansionary. The system therefore expects miner breadth to remain positive unless the dollar reverses sharply.

That sentence contains:

- trajectory;
- causality;
- historical memory;
- difference from analog;
- expectation;
- invalidation.

This is the destination.

---

# 258. A Dashboard Resets; a Cognitive System Remembers

Dashboard tomorrow:

> Gold +1%.

Cognitive system tomorrow:

> The expected continuation occurred, increasing confidence in the current precious-metal interpretation. However, juniors still lag, so breadth expansion remains incomplete.

This is persistent state.

---

# 259. A Dashboard Reports; a Cognitive System Is Surprised

Dashboard:

> Gold -3%.

Cognitive system:

> Gold fell despite the combination that had historically supported it. This is a negative surprise; investigate positioning, real-vs-nominal yield divergence, USD funding, China demand, and forced liquidation.

This is attention.

---

# 260. A Dashboard Has History; a Cognitive System Has Experience

Historical chart:

> March 2020.

Experience:

> In March 2020, falling yields did not immediately support gold because dollar funding stress and forced liquidation dominated. The system initially misclassified the move as a standard easing regime. The important lesson is to condition gold's real-yield relationship on liquidity stress.

That changes behavior.

---

# 261. A Dashboard Has Correlations; a Cognitive System Has Relationship Semantics

Dashboard:

> Correlation = 0.72.

Cognitive system:

> Copper and this miner are strongly related because commodity price affects expected cash flow, but the relationship weakens around operational disruptions and hedge-book changes.

Again: meaning.

---

# PART XXIV — HOW A DAILY MASTERBRAIN SESSION COULD WORK

# 262. Pre-Open Global Synthesis

Before each market opens:

```text
1. update macro state;
2. update overseas markets;
3. detect global theme shocks;
4. update commodities;
5. update relevant news/catalysts;
6. calculate local priors;
7. identify expected local expressions.
```

China example:

```text
US space +8%
silver +5%
CNH stable
A50 +0.4%
```

The system creates priors for:

- 商业航天;
- precious metals;
- risk appetite.

Not predictions yet.

Priors.

---

# 263. Auction as First Falsification

China call auction reveals whether overnight priors are accepted.

Compare:

```text
expected local response
vs
auction response
```

Update immediately.

This is the first surprise checkpoint.

---

# 264. Intraday Event-Driven Cortex

During session:

Deterministic sensors detect:

- breadth explosion;
- first limit-up;
- theme synchronization;
- large flow;
- leader failure;
- cross-market divergence.

Only important events trigger deeper Cortex reasoning.

This keeps computation focused.

---

# 265. End-of-Day Synthesis

At close:

```text
What changed?
Which expectations succeeded?
Which failed?
Which themes changed lifecycle?
Which dislocations opened or closed?
Which market strategies were rewarded?
What should we expect tomorrow?
```

This becomes an Experience Record.

---

# 266. Weekly Deep Review

Weekly:

- update semantic memory;
- review theme transitions;
- identify repeated errors;
- assess regime probabilities;
- nominate Research Cortex investigations.

This mimics a professional investment team's weekly process.

---

# PART XXV — A PHASED CONCEPTUAL ROADMAP WITHOUT COLLAPSING INTO A PRD

# 267. Phase 0 — Preserve the Research Questions

Before engineering:

- formalize hypotheses;
- decide what success means;
- identify point-in-time data constraints;
- decide which themes/episodes form research set.

This prevents architecture from becoming feature-driven.

---

# 268. Phase 1 — Universal Theme Graph Seed

Start with:

```text
200–300 useful tradable major themes
```

not thousands of microthemes.

For each:

- definition;
- hierarchy;
- core constituents;
- evidence;
- exposure weights.

US and China should share global parents where appropriate.

---

# 269. Phase 2 — Build Point-in-Time Theme Factors

For each seed theme:

- price;
- equal-weight;
- exposure-weighted;
- residual;
- breadth;
- leadership;
- volatility;
- dispersion.

This creates historical quantitative objects.

---

# 270. Phase 3 — Add Narrative + Attention + Catalyst

Then introduce:

- news;
- search;
- analyst/research;
- catalysts;
- semantic membership changes.

This begins to turn indices into living themes.

---

# 271. Phase 4 — Add Market-Specific Ecology

China:

- limit-up;
- auction;
- 龙虎榜;
- sentiment.

US:

- ETF;
- options;
- revisions;
- ownership.

Keep the universal interface but local sensors.

---

# 272. Phase 5 — Historical Replay and Lifecycle Models

Only after state reconstruction becomes credible:

- train transition models;
- backtest hidden-beneficiary ideas;
- test fragility;
- test dislocations.

---

# 273. Phase 6 — Cortex Integration

Feed standardized beliefs into Neural Web.

Cortex asks:

- what changed?
- what matters?
- what contradicts?
- what should happen next?

Do not let the LLM replace quantitative engines.

---

# 274. Phase 7 — Research Cortex

Only after a meaningful production history exists:

- cluster errors;
- propose missing variables;
- run research loops.

This is an advanced layer, not day-one scope.

---

# PART XXVI — THE MOST IMPORTANT RESEARCH QUESTIONS FOR CLAUDE / FABLE TO CHALLENGE

# 275. Ontology Questions

- How granular should themes be before they become unstable?
- How should temporary event narratives coexist with structural themes?
- How should theme merges/splits be represented?
- How should edge weights decay?
- How should conflicting evidence be aggregated?
- Can a company have different local-market narrative identities?

---

# 276. Quant Questions

- Do residual theme factors have predictive value beyond industry factors?
- Does theme breadth forecast continuation?
- Does attention acceleration lead price breadth?
- Does leadership renewal distinguish healthy extension from distribution?
- Can good-news elasticity identify tops?
- Does theme propagation provide incremental information?

---

# 277. China Questions

- Can limit-up ecology be reconstructed historically with enough fidelity?
- Which auction fields are legally/licensably obtainable?
- How predictive are seal quality and first-touch time?
- Can 龙虎榜 participant fingerprints generalize?
- What is the best replacement for now-limited Northbound real-time flow visibility?

---

# 278. US Questions

- How should ETF holdings contribute to narrative consensus?
- Can options state be meaningfully aggregated to theme level?
- How much does 13F lag reduce its usefulness?
- Which analyst-revision measures are truly incremental?
- Can supply-chain mapping identify lagging beneficiaries before price?

---

# 279. Cognitive Questions

- What belongs in persistent world state?
- What should trigger Cortex activation?
- What should be deterministic vs LLM-driven?
- How should novelty be estimated?
- How should memories be retrieved?
- How do we prevent analogue overreach?
- How do learned lessons actually alter future weights?

---

# 280. Product Questions

- Which 3–5 outputs make the deepest intelligence immediately useful?
- How much complexity should remain hidden?
- How should uncertainty be communicated?
- How can “why” explanations remain concise but auditable?
- Which features are sufficiently unique to become marketing wedges?



# PART XXVII — PRIORITIZATION: WHICH IDEAS ARE CORE, WHICH ARE EXPERIMENTAL, WHICH SHOULD WAIT

# 281. Tier A — Foundational Architecture

These ideas are not optional if the project is pursued seriously.

## A1. Dynamic multi-label Theme Graph

Without this, everything falls back into sectors and hand-curated baskets.

## A2. Point-in-time Company ↔ Theme edges

Without point-in-time membership, historical research becomes unreliable.

## A3. Three core exposure realities

```text
Economic
Narrative
Trading
```

These should remain separate.

## A4. Persistent Theme State

At minimum:

```text
price
breadth
leadership
flow
attention
fundamentals
catalyst
crowding
```

## A5. Universal world-state interface

Themes must be conditioned on macro and local market state.

## A6. Historical theme factors

Without history there is no learning.

## A7. Eventization

Important state changes should become events that can wake the Cortex.

## A8. Expectation → Surprise → Outcome

Without expectations, the system cannot learn from violations of its worldview.

These constitute the core intellectual architecture.

---

# 282. Tier B — High-Potential Alpha Research

These deserve serious testing once the foundation exists:

```text
Theme lifecycle transition probabilities
Leadership renewal
Theme breadth acceleration
Hidden Beneficiary Engine
Narrative / economic disagreement
Catalyst response elasticity
Attention acceleration
Theme market share
Cross-market theme transmission
Dislocation resolution
Theme fragility
```

Each is conceptually strong and connected to measurable outcomes.

---

# 283. Tier C — Powerful but More Experimental

These are creative constructs that should not be prematurely institutionalized:

```text
Narrative Reproduction Number
Theme Gravity
Theme Entropy
Theme Pressure
Potential Energy
Attention Efficiency
Narrative-Capital Conversion
Capital-Price Conversion
Theme Frontier
```

They are useful as research metaphors.

Some may become excellent proprietary metrics.

Others may disappear after empirical testing.

That is fine.

The point of brainstorming is to generate hypotheses.

---

# 284. Tier D — Later-Stage Intelligence

These require significant infrastructure and should wait:

```text
fully autonomous theme discovery
Research Cortex self-expansion
large-scale causal graph learning
participant behavioral inference across all actors
continuous counterfactual simulation
```

Do not let futuristic capability block useful near-term research.

---

# PART XXVIII — PRODUCT SURFACES THAT COULD EMERGE FROM THE INTELLIGENCE GRAPH

These are not UI specifications. They are examples of how deep internal intelligence could become legible to users.

# 285. Global Theme Map

A real-time map showing themes by:

```text
Emerging
Accelerating
Mature
Crowded
Distributing
Dormant
```

Do not sort solely by today's return.

A theme that is only +1% but moving:

```text
Dormant → Discovery
```

may be more important than one already +35% in Mania.

This surface should therefore privilege **change in state**.

---

# 286. Theme Radar

Potential axes:

```text
Strength
Health
Attention Velocity
Fundamental Confirmation
Crowding
```

A user can immediately distinguish:

- early healthy themes;
- powerful mature themes;
- speculative themes;
- deteriorating themes.

A radar-like display is only worthwhile if the dimensions have empirical meaning.

---

# 287. Theme Frontier

A dedicated discovery surface:

> Which companies/subthemes are newly entering an existing narrative?

Example:

```text
AI Infrastructure Frontier

Newly activating:
- gas turbines
- transformer components
- data-center construction
- nuclear fuel
```

Show:

- causal path from parent theme;
- economic evidence;
- attention change;
- repricing status.

This can become one of the most differentiated Mastermind experiences.

---

# 288. Hidden Beneficiaries

Rank companies where:

```text
economic exposure high
catalyst active
evidence improving
narrative awareness low
price response low
```

Possible interface:

```text
Why hidden?
Why relevant?
What has not yet repriced?
What could invalidate?
```

This aligns directly with Mastermind's discovery mission.

---

# 289. Narrative Excess

Inverse surface:

```text
market narrative high
price extension high
hard evidence low
attention saturated
```

Useful for:

- risk reduction;
- short research;
- avoiding late chases.

But never call these automatic shorts.

---

# 290. Theme Migration

Show capital moving inside a larger economic system.

Example:

```text
AI
Compute           ↓
Networking        →
Power             ↑↑
Cooling           ↑
Applications      ↑
```

This is much more informative than “AI sector -0.4%.”

It can prevent users from mistaking internal rotation for theme death.

---

# 291. What Changed Today?

Possible cards:

```text
Theme entered Expansion
Theme health deteriorated sharply
Narrative propagation accelerated
Institutional participation appeared
Leader failed to confirm
Cross-market relationship broke
```

This should be a **delta-first** product.

Users generally know current values.

They need help seeing **important changes**.

---

# 292. Relationship Breaks

A live screen:

```text
Gold ↑ / Miners ↓
Commodity ↑ / China producers flat
AI Power ↑ / supplier X ↓
ETF inflow ↑ / constituent basket weak
Good earnings / stock reaction negative
```

Then rank by historical abnormality and possible dislocation quality.

This could be both a research and alpha product.

---

# 293. Market Reinforcement Dashboard

China:

```text
Strategy                  T+1 Reward
First boards               ↑
High boards                ↓
Yesterday limit-ups        ↑
Late-day seals             ↓
```

US:

```text
Strategy                  Next-session Reward
Earnings gaps              ↑
Breakouts                  ↑
High-call-volume chases    ↓
Theme laggards             ↑
```

This tells the trader which behaviors are currently being rewarded.

That is an unusually intuitive way to express regime.

---

# 294. Theme Autopsy

After a theme collapses:

```text
What happened?
When did health peak?
When did attention saturate?
When did breadth diverge?
Which leaders failed first?
Which evidence stopped improving?
Which signals actually mattered?
```

This becomes both education and machine learning.

---

# 295. Historical Replay Mode

A genuinely differentiated research experience:

Put the user — and the model — at a historical date with only then-available information.

Example:

```text
March 5, 2020
```

Ask:

> What state do you infer?

Then advance.

This could become an internal training tool first and eventually a premium research product.

---

# PART XXIX — WHY THIS COULD BE A UNIQUE RETAIL PRODUCT IN THE US

# 296. US Retail Market Intelligence Is Highly Fragmented

A sophisticated US retail investor often assembles a patchwork:

```text
TradingView
Finviz
Unusual Whales
Fintel
Quiver
Koyfin
broker research
ETF sites
SEC
social media
```

Each answers a subset.

The under-served question is:

> **What do all of these observations collectively mean about the current market structure?**

The user currently acts as the Cortex.

Mastermind's opportunity is to automate part of that synthesis.

---

# 297. Institutional Theme Intelligence Is Mostly Hidden From Retail

Institutional systems can provide:

- dynamic classifications;
- thematic factor models;
- bespoke baskets;
- portfolio attribution.

But such products are often:

- enterprise-priced;
- data-oriented;
- designed for professional workflows;
- not built as a live retail market-intelligence experience.

This creates whitespace.

Mastermind does not need to be “better than Theia at Theia.”

It can use the same problem insight but optimize for:

```text
trading relevance
real-time state
explainability
cross-market context
retail usability
AI interaction
```

---

# 298. The Retail USP Is Not “We Have 3,000 Themes”

A giant number is a weak marketing message.

The stronger story:

> **Mastermind knows which themes are waking up, which are spreading, which are becoming crowded, and which companies the market has not noticed yet.**

That communicates intelligence, not database size.

---

# 299. China Intelligence Can Differentiate the Global Product Too

A US investor interested in:

- commodities;
- semiconductors;
- EVs;
- solar;
- China ADRs;
- global manufacturing;

benefits from understanding A-share theme behavior.

Example:

A Chinese semiconductor-equipment theme could signal local supply-chain optimism before it becomes obvious in US-listed suppliers.

Likewise US overnight themes can shape A-share opening priors.

The cross-market graph creates a two-way informational advantage.

---

# 300. The Product Can Teach Users to Think Structurally

A side effect:

Users stop thinking:

> “Stock X is up.”

and begin thinking:

> “Theme is expanding; breadth is broadening; capital is migrating downstream; this stock is a secondary beneficiary.”

This is valuable even when no direct prediction is made.

The product can effectively teach institutional market reasoning.

---

# PART XXX — SYSTEM FAILURE MODES AND ADVERSARIAL QUESTIONS

# 301. What If Themes Are Mostly Retrospective Stories?

Challenge:

Humans are excellent at inventing narratives after prices move.

Possible failure:

```text
price rises
→ media invents theme
→ model sees theme
→ claims theme predicted price
```

Countermeasure:

- point-in-time semantic evidence;
- causal chronology;
- residual returns;
- delayed validation;
- explicit counterfactuals.

The system must prove that theme state adds information rather than narrating hindsight.

---

# 302. What If Narrative Attention Is Mostly Endogenous to Price?

This is likely partially true.

Price drives searches.

Searches can also drive demand.

Therefore use:

- lag structures;
- instrumental research where possible;
- source decomposition;
- event timing;
- attention changes not explained by price.

The goal is not to prove pure causality for every feature.

It is to identify when attention contains **incremental state information**.

---

# 303. What If “Smart Money” Labels Become Folk Mythology?

This is a real risk.

A seat that succeeded five times may not have persistent skill.

A 13F holder may be hedged elsewhere.

Options flow may be dealer hedging.

Therefore:

```text
ParticipantInference != GroundTruthIntent
```

Always maintain probabilistic interpretation.

---

# 304. What If Theme Graphs Become Too Dense?

A fully connected graph becomes useless.

Use:

- edge thresholds;
- relevance;
- temporal decay;
- hierarchical organization;
- purpose-specific views.

The system does not need to show all relationships simultaneously.

---

# 305. What If Cross-Market Signals Disappear After Discovery?

Some lead-lag relationships will arbitrage away.

Therefore every relationship needs:

```text
current reliability
decay
last validation
```

The graph is living.

Do not canonize yesterday's alpha.

---

# 306. What If the LLM Over-Interprets Sparse Data?

Require:

- minimum evidence;
- confidence;
- novelty;
- explicit missing data.

The best answer can be:

> “The apparent theme ignition is not yet sufficiently confirmed.”

---

# 307. What If the System Learns the Wrong Lesson From One Episode?

Semantic memory should not update from one anecdote without validation.

Episode:

```text
Observation
```

does not automatically become:

```text
Rule
```

Require repeated evidence or research validation.

---

# 308. What If a Beautiful Composite Score Masks Regime Failure?

Keep raw components.

Always permit:

```text
Why did score fall?
```

and backtest score components by regime.

---

# PART XXXI — COMPETITIVE POSITIONING

# 309. Bloomberg

Strength:

- enormous professional data/workflow ecosystem.

Mastermind opportunity:

- more explicit semantic theme state;
- AI-native reasoning;
- retail accessibility;
- persistent cross-lobe world model.

Do not try to replicate Bloomberg's entire information monopoly.

---

# 310. 同花顺

Strength:

- exceptional A-share market ecology;
- local investor behavior;
- retail workflow;
- breadth of market views.

Mastermind opportunity:

- turn observations into persistent machine-readable state;
- add historical experience;
- add causal and cross-market reasoning;
- unify with US/global themes.

---

# 311. Theia

Strength:

- institutional dynamic ontology;
- multi-label exposure;
- thematic factor model;
- global coverage;
- historical taxonomy.

Mastermind opportunity:

- optimize ontology for trading intelligence;
- integrate attention, participants, catalysts and market state;
- create lifecycle/dislocation layers;
- expose intelligence directly to retail users.

---

# 312. S&P Kensho / MSCI / Morningstar

These validate:

- NLP-based thematic classification;
- business-segment mapping;
- forward-looking theme relevance;
- holdings-consensus methods;
- systematic index construction.

Mastermind can combine their distinct philosophies as **separate evidence channels** rather than selecting one.

---

# 313. Finviz-Style Theme Pages

Useful for:

- simple theme discovery;
- visual grouping;
- relative performance.

But a theme list without:

- point-in-time exposure;
- evidence;
- lifecycle;
- capital;
- memory;
- causality;

remains mostly a classification/screening surface.

Mastermind's target is an intelligence layer above it.

---

# 314. Alternative-Data Products

Products such as Quiver expose:

- government contracts;
- congressional trading;
- lobbying;
- insiders;
- institutional holdings;
- patents.

Mastermind's differentiation is not necessarily possessing more isolated datasets.

It is mapping each event into:

```text
Company
→ Theme
→ Causal Graph
→ Current State
→ Expected Consequence
```

Alternative data becomes context.

---

# PART XXXII — DEEPER IDEATION: WHAT THE SYSTEM MAY EVENTUALLY BECOME

# 315. A Market “Consciousness” Is a Useful Metaphor, If Used Carefully

Do not anthropomorphize the system literally.

But the metaphor captures something valuable:

At any moment the market has:

- current focus;
- recent memories;
- prevailing expectations;
- unresolved contradictions;
- emotional state;
- dominant narratives.

Mastermind's world state can approximate a machine-readable representation of this collective state.

Call it:

```text
Market Consciousness State
```

internally if useful.

It is simply:

> **the collection of beliefs and expectations currently necessary to interpret market behavior.**

---

# 316. Market Attention Is the Allocation of Collective Computation

Investors cannot process everything.

Attention determines which information gets converted into prices fastest.

Thus attention is analogous to:

```text
where the market is spending its cognitive bandwidth
```

This gives a deeper interpretation of:

- search heat;
- media focus;
- options activity;
- turnover concentration;
- theme popularity.

A theme can become mispriced partly because the market has not allocated enough attention to it yet.

---

# 317. Narrative Is a Compression Algorithm

A narrative compresses complicated economics into a tradable mental model.

Example:

```text
“AI power shortage”
```

compresses:

- data-center load;
- grid bottlenecks;
- transformer lead times;
- generation;
- cooling;
- capex.

Narratives matter because capital allocation requires simplified mental models.

Mastermind should therefore not dismiss narratives as irrational.

It should model:

- whether the compression is economically valid;
- whether it is spreading;
- whether price has outrun the underlying reality.

---

# 318. Themes Are Interfaces Between Reality and Capital

This may be the deepest synthesis.

Economic reality is enormous and complicated.

Capital needs a tradable representation.

Themes are the **interfaces** through which investors map reality into securities.

Therefore:

```text
Reality
   ↓
Narrative Compression
   ↓
Theme
   ↓
Capital Allocation
   ↓
Price
```

And price feeds back:

```text
Price
   ↓
Attention
   ↓
Narrative
   ↓
Capital
```

This is a reflexive system.

The Dynamic Theme Graph is therefore not merely classification.

It is a model of **how economic reality is translated into market behavior**.

---

# 319. The System Can Measure Where That Translation Is Failing

This creates three broad alpha families.

## Reality ahead of narrative

Potential hidden beneficiary.

## Narrative ahead of reality

Potential optionality or eventual excess.

## Capital/pricing inconsistent with both

Potential dislocation.

This three-way framework can organize much of Mastermind research.

---

# 320. The Theme Graph Can Become a Causal Search Engine

User asks:

> “If silver remains in deficit, where does that propagate?”

Graph explores:

```text
silver price
→ miners
→ solar input costs
→ recycling
→ electronics
→ substitution
→ policy
```

User asks:

> “If hyperscaler capex rises 20%, who benefits two hops downstream?”

The graph returns:

- direct compute;
- networking;
- cooling;
- power;
- construction.

This is a very different product from a stock screener.

---

# 321. The System Can Become a Hypothesis Generator

Rather than only answering known questions:

```text
Observation:
US space theme strengthening.
China commercial-space attention rising before price.

Hypothesis:
Cross-market narrative transmission may be starting.

Test:
Historical US-space shocks vs China theme response under similar local sentiment.
```

That becomes machine-assisted research.

---

# 322. Eventually the System Can Discover “Unknown Unknowns”

The Research Cortex can notice:

```text
These stocks keep moving together
but
our graph has no explanation.
```

It then investigates:

- shared customer?
- hidden supply chain?
- common commodity?
- policy?
- thematic relationship?

This is a compelling long-term form of autonomous theme discovery.

---

# 323. Persistent Experience Can Create a “Feel” for the Tape Without Mysticism

Human traders often say:

> “The tape feels weak.”

Usually this intuition compresses many observations:

- failed breakouts;
- poor reaction to news;
- shrinking breadth;
- heavy supply;
- weak leaders.

Mastermind can decompose and measure those observations.

What humans call “feel” may often be:

```text
high-dimensional pattern recognition
```

Historical replay gives the system examples.

The goal is not mystical intuition.

It is **compressed learned state recognition**.

---

# 324. Machine Intuition Should Remain Auditable

Even if the system develops strong learned representations:

```text
z_t = f(State_t)
```

it should still retrieve supporting interpretable evidence.

Output:

> State embedding resembles episodes X/Y/Z.

Then:

- show major matching dimensions;
- show important differences;
- show uncertainty.

That preserves trust.



# PART XXXIII — WHAT THE EXTERNAL RESEARCH CHANGES OR STRENGTHENS

The external research pass largely **strengthens** the conceptual direction rather than invalidating it.

It does, however, sharpen several assumptions.

# 325. Theia Shows That the Ontology Problem Is Already Much More Mature Than a Casual Clone Would Suggest

Theia currently describes a one-to-many classification spanning:

- 10 sectors;
- 23 industries;
- 80 sub-industries;
- 245 major themes;
- 3,200+ microthemes;
- 50,000+ public companies;
- 13+ years of history.

It also states that company activities are assessed through more than revenue, including:

- products/services;
- R&D and CapEx;
- target markets/use cases;
- partnerships;
- acquisitions.

The important implication is not:

> “We should reproduce 3,200 microthemes.”

It is:

> **A credible dynamic ontology requires substantially more evidence, history, and maintenance than a one-pass LLM classification.**

This should make Mastermind **more selective**, not less ambitious.

The first milestone should be a smaller set of deeply useful trading themes whose states can be validated.

---

# 326. Theia Also Confirms That Theme Factor Models Are Not Speculative Architecture

Theia explicitly offers:

```text
200+ thematic factors
+
style factors
```

and markets them for:

- thematic alpha;
- risk;
- rotation;
- hedging;
- portfolio decomposition.

This is important validation of the idea:

```text
theme classification
→ quantitative theme factor
→ stock return explanation
```

Mastermind can build on this rather than wondering whether the concept is institutionally legitimate.

The differentiation should therefore move **one layer up**:

```text
theme factor
+
theme state
+
narrative
+
participants
+
memory
+
expectation
+
surprise
```

---

# 327. S&P Kensho Confirms That Filings Can Detect Emerging Economic Participation

S&P Kensho describes using machine learning and NLP on regulatory filings and other public information to identify companies connected to emerging economic themes.

This supports an important Mastermind research principle:

> Do not require a theme to already dominate reported revenue before considering it economically meaningful.

A company can become relevant because:

- it begins investing;
- management commits resources;
- it signs contracts;
- it enters a market;
- it changes product strategy.

This is exactly what `Theme Optionality` and `Catalyst Activation` are designed to preserve.

---

# 328. MSCI Confirms That Natural-Language Investment Ideas Can Map Directly Into Business Segments

MSCI's current Strategy Explorer uses an LLM-driven workflow to connect plain-language investment ideas to company business segments and thematic exposures.

This suggests an eventual Mastermind capability:

User:

> “Build me the companies exposed to orbital compute but exclude generic satellite exposure.”

The ontology could dynamically resolve:

- concept definition;
- relevant nodes;
- evidence;
- exposure.

But Mastermind's job should not end with basket generation.

It should then answer:

> **Which of these exposures are active in the market now?**

That second layer remains central.

---

# 329. Morningstar Confirms That “Theme Relevance” Has Multiple Legitimate Definitions

Morningstar's thematic framework uses analyst assessments of future revenue and net-profit importance, while its separate consensus indexes infer thematic relevance from how widely stocks are owned across thematic funds.

These are different epistemologies.

That directly validates the Mastermind decision **not** to collapse theme exposure into one score.

It is reasonable to maintain:

```text
Analyst Fundamental Exposure
Fund-Holdings Consensus
Semantic Exposure
Market Exposure
```

and let disagreement itself become a signal.

---

# 330. Official Exchange Rules Confirm That China Needs Native Market-Structure Modeling

Current official exchange materials show meaningful differences:

- STAR Market uses a 20% daily price range after the first five IPO trading days, which have no regular price limit.
- ChiNext similarly uses 20% after the first five IPO trading days.
- Beijing Stock Exchange's current trading rules use a 30% daily limit, with specified no-limit cases.
- Main-board regimes differ and special-treatment rules need their own treatment.

This confirms that one naïve “extreme daily return” feature is unusable across A-shares.

The market rule itself is part of the state.

---

# 331. The BSE Rules Also Confirm Why Auction Data Can Be Rich

The BSE rulebook explicitly describes auction reference prices, matched volume, and unmatched volume in call-auction dissemination.

This supports the larger idea that:

```text
matched demand
unmatched demand
price evolution
```

are not merely screen decorations.

They are microstructure observations that can be normalized into state.

The exact fields available across Shanghai/Shenzhen/BSE and commercial feeds will differ, but the research direction is legitimate.

---

# 332. Stock Connect Disclosure Changes Are an Important Warning Against Frozen Architectures

HKEX/SSE/SZSE announced in 2024 that real-time Northbound buy, sell, and total turnover would no longer be disseminated in the prior form, while selected historical aggregate statistics remained available and shareholding disclosure frequency changed.

This matters beyond Northbound flow.

It teaches:

> **Data availability is itself regime-dependent.**

A production system must know:

```text
what was observable
when
under which dissemination policy
```

Otherwise historical and live states silently diverge.

The data model should therefore version **information regimes**, not just market rules.

---

# 333. FINRA Provides a Perfect Example of Semantic Data Errors We Must Prevent

FINRA explicitly warns that daily short-sale volume is not equivalent to reported short interest.

Retail platforms frequently blur these concepts.

Mastermind should treat semantic correctness as part of its moat.

If a field is:

```text
off-exchange short-sale transaction volume
```

call it that.

Do not convert it into:

```text
bearish short positioning
```

without further inference and evidence.

This seems mundane but is foundational.

A graph full of mislabeled relationships becomes confidently wrong.

---

# 334. OCC Confirms That Useful Public Options Baselines Exist

OCC currently provides public reports covering:

- volume;
- open interest;
- exchange volume;
- volume by account type;
- calls vs puts;
- underlying/symbol queries.

This does not replace a full institutional options feed.

But it means Mastermind can build some **public-baseline options state** and reserve expensive vendor data for richer layers such as:

- high-frequency flow;
- Greeks;
- trade direction inference;
- quote history;
- dealer-position estimates.

That suggests a sensible data architecture:

```text
official baseline
+
licensed enrichment
+
Mastermind inference
```

---

# 335. SEC APIs Make Evidence-Backed US Semantic Classification Very Feasible

The SEC's official data APIs provide:

- submissions history;
- company metadata;
- XBRL facts;
- bulk archives;
- near-real-time update behavior.

The SEC also publishes structured Form 13F datasets.

Therefore a meaningful portion of the US economic-evidence layer can be built directly on official primary data.

The difficult problem is not download access.

The difficult problem is:

- entity resolution;
- semantic extraction;
- temporal evidence;
- segment normalization;
- corporate-history handling.

That is an engineering moat in its own right.

---

# 336. Investor-Attention Research Supports Modeling Attention as a State — But Warns Against Simplistic Directionality

Empirical China research using Baidu search measures has found:

- contemporaneous relationships between attention and abnormal returns;
- short-term price-pressure/reversal patterns in some samples;
- attention factors that improve explanation of return anomalies;
- links between co-attention and return co-movement;
- investor-type heterogeneity;
- links between attention and idiosyncratic risk.

The conclusion should **not** be:

> High search interest predicts higher future returns.

The stronger conclusion is:

> **Attention is a real behavioral dimension of Chinese market state, and its effect depends on level, change, investor composition, prior returns, and context.**

That is exactly why we proposed:

```text
AttentionLevel
AttentionVelocity
AttentionAcceleration
AttentionSourceMix
AttentionBreadth
```

rather than one popularity number.

---

# 337. Bubble Research Strongly Supports the Fragility Framing

Greenwood, Shleifer, and You find that sharp industry price run-ups do not, by themselves, imply unusually poor future returns, although they increase crash risk; characteristics such as volatility, turnover, issuance, and the path of the run-up help distinguish more crash-prone episodes.

This is almost a direct empirical endorsement of the Mastermind top-recognition framing:

```text
EXTENDED
!=
TOP
```

The real research problem is:

```text
EXTENDED + CONTINUES
vs
EXTENDED + FRAGILITY / DISTRIBUTION
```

Theme state adds potentially useful dimensions that their original industry work did not attempt to represent:

- narrative saturation;
- attention;
- breadth;
- leadership renewal;
- economic evidence;
- participant mix.

That suggests a rich research program.

---

# PART XXXIV — THE SINGLE UNIFIED ARCHITECTURE

# 338. The Full Stack

The entire synthesis can be represented as:

```text
┌───────────────────────────────────────────────────────────────┐
│                       GLOBAL SENSORIUM                        │
│                                                               │
│ Price | Volume | Options | ETFs | Filings | News | Macro      │
│ China Microstructure | Commodities | Policy | Alt Data        │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                  NORMALIZATION / EVIDENCE                     │
│                                                               │
│ entity resolution | timestamps | provenance | confidence      │
│ rule versions | evidence objects | feature derivation         │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                     DYNAMIC THEME GRAPH                       │
│                                                               │
│ Companies ↔ Themes ↔ Catalysts ↔ Supply Chains ↔ Commodities  │
│ Participants ↔ Flows ↔ ETFs ↔ Policies ↔ Markets             │
│                                                               │
│ Economic | Narrative | Trading | Catalyst | Temporal Reality  │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                      PERSISTENT WORLD MODEL                   │
│                                                               │
│ Global State | US State | China State | Theme States          │
│ trajectories | transitions | expectations | anomalies         │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                    SALIENCE / EVENT SYSTEM                    │
│                                                               │
│ surprise | novelty | regime shifts | relationship breaks      │
│ theme ignition | distribution | abnormal flows                │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                  MEMORY + EXPERIENCE RETRIEVAL                │
│                                                               │
│ episodic | semantic | procedural | historical analogues       │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                    DELIBERATION CORTEX                        │
│                                                               │
│ interpret | reconcile | hypothesize | compare | falsify       │
│ ask “how is now different?” | identify missing information    │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                     PROPHET / OUTPUT ORGANS                   │
│                                                               │
│ probabilities | theme rankings | stock rankings | risk        │
│ dislocations | transitions | expected returns | horizons      │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                     OUTCOME EVALUATOR                         │
│                                                               │
│ expected vs observed | surprise | error taxonomy              │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                       LEARNING SYSTEM                         │
│                                                               │
│ reliability | weights | memories | regimes | procedures       │
└──────────────────────────────┬────────────────────────────────┘
                               │
                               ▼
┌───────────────────────────────────────────────────────────────┐
│                       RESEARCH CORTEX                         │
│                                                               │
│ recurring failures → hypotheses → missing capability          │
│ → backfill → replay → validate → proposed improvement         │
└───────────────────────────────────────────────────────────────┘
```

This is the architecture that the 同花顺 and US thematic studies converge toward.

---

# 339. The Dynamic Theme Graph Sits in the Middle for a Reason

The Theme Graph is unusually valuable because it connects:

```text
macro
to
companies

stories
to
economic reality

capital
to
assets

global events
to
local markets

history
to
current state
```

It provides semantic topology.

Without it, the Neural Web has many sensors but fewer structured relationships.

With it, signals can propagate through explicit paths.

---

# 340. Prophet Should Become an Output Organ, Not the Whole Brain

This is a crucial conceptual reframe.

Prophet may remain the system that ultimately ranks:

- stocks;
- themes;
- entries;
- expected returns;
- risks.

But Neural Web becomes the broader organism.

```text
Neural Web
    understands the world.

Prophet
    expresses expectations from that understanding.
```

This separation prevents every new idea from being shoved into one giant stock-picking formula.

---

# 341. The Theme Graph Also Gives Prophet Hierarchical Predictions

Instead of only:

```text
P(stock up)
```

predict:

```text
P(global theme strengthens)
P(local theme strengthens)
P(theme transitions to Expansion)
P(company outperforms theme)
P(company catches up)
P(theme enters fragility)
```

These probabilities form a hierarchy.

A stock prediction can inherit context from each level.

---

# 342. Hierarchical Error Attribution

If stock forecast fails:

```text
Was global theme wrong?
Was local theme wrong?
Was stock exposure wrong?
Was catalyst wrong?
Was timing wrong?
Was market regime wrong?
```

This makes errors diagnosable.

A flat model only says:

> prediction failed.

A hierarchical cognitive system says:

> thesis correct at theme level; company-specific expression failed because economic exposure was overstated.

That is learnable.

---

# 343. The Ultimate Closed Loop

The complete organism:

```text
SENSE
    market observations

UNDERSTAND
    normalize into state and relationships

REMEMBER
    retrieve relevant experiences

NOTICE
    detect surprise, novelty, transitions

THINK
    reconcile evidence and form hypotheses

PREDICT
    generate probabilistic expectations

EXPERIENCE
    compare expectation to reality

LEARN
    update reliability and memory

DISCOVER
    identify missing variables and new themes

IMPROVE SENSING
    expand or refine the architecture

REPEAT
```

This is much closer to a market apprenticeship than a screen of indicators.

---

# PART XXXV — FINAL STRATEGIC RECOMMENDATION

# 344. Amalgamate the Projects — But Preserve Market Identity

The answer to the original strategic question is **yes**:

> The US Dynamic Theme Graph project and the China 同花顺-derived market intelligence project should be amalgamated into one Mastermind Global Market Intelligence project.

But this must not mean:

> “Build the same dashboard twice.”

It means:

```text
one ontology of market cognition
+
two highly native market sensoriums
+
global cross-market bridges
```

The Universal Core should understand:

- entities;
- themes;
- narratives;
- catalysts;
- attention;
- capital;
- states;
- transitions;
- expectations;
- surprises;
- dislocations;
- memories.

The US module should specialize in:

- filings;
- economic evidence;
- ETF structures;
- options;
- institutional holdings;
- revisions;
- supply chains.

The China module should specialize in:

- concept ecology;
- sentiment;
- 涨跌停;
- 连板;
- auction;
- 龙虎榜;
- 游资;
- local policy liquidity.

The global layer should connect:

- commodities;
- macro;
- geopolitical catalysts;
- technology;
- cross-market narrative transmission.

---

# 345. Why One Project Is Better Than Two

If separate:

```text
US Theme Engine
China Theme Engine
```

the systems will independently reinvent:

- state;
- lifecycle;
- exposure;
- evidence;
- memory;
- transition;
- surprise.

That produces duplicated architecture and weak cross-market reasoning.

If unified:

```text
ThemeState
```

is universal while:

```text
ThemeState.US
ThemeState.CN
```

can consume different sensors.

That enables transfer learning while respecting local structure.

---

# 346. The Long-Term Product Identity

The most compelling formulation remains:

> **Mastermind is not trying to become a better database of financial facts. It is trying to become a persistent model of what the market currently means.**

That requires:

```text
what exists
what changed
why it changed
who is acting
what is spreading
what is breaking
what history resembles it
what is different
what should happen next
```

No current retail product needs to solve all of those perfectly for the architecture to be valuable.

Even partially solving them creates differentiation.

---

# 347. The Immediate Product Wedge

The entire cognitive organism is a long vision.

The near-term wedge can be narrower:

## Global Theme Intelligence

For each important theme:

```text
WHAT IT IS
WHO IS EXPOSED
WHAT CHANGED
WHY IT IS MOVING
HOW BROAD IT IS
WHERE CAPITAL IS GOING
WHERE IT IS IN ITS LIFECYCLE
WHAT HISTORICALLY HAPPENED NEXT
```

China gets additional local ecology.

US gets institutional-style thematic depth.

This alone could be a major product.

Everything else compounds around it.

---

# 348. The Deepest Moat Is Compounded Experience

The most important long-run thought in this entire project:

A competitor can copy:

- a feature;
- a theme label;
- a screen;
- a composite score.

It is much harder to copy:

```text
years of point-in-time world states
+
millions of expectation/outcome episodes
+
learned conditional reliability
+
historical theme evolution
+
cross-market relationship history
+
validated semantic memory
```

That is why historical replay is not an accessory.

It may be the mechanism that converts a clever architecture into an experienced one.

---

# 349. The Product Does Not Need “Market AGI” to Be Extraordinary

Avoid making success contingent on science fiction.

The architecture can create value incrementally.

Even without autonomous learning:

- dynamic themes improve classification;
- theme factors improve explanation;
- attention improves state;
- China ecology improves timing;
- dislocations improve research;
- eventization improves monitoring;
- historical analogs improve context.

The organism metaphor describes direction.

Each organ can still be useful independently.

---

# 350. The Most Important Near-Term Shift in Mindset

Mastermind should gradually stop asking:

> **What new data plane should we add?**

and increasingly ask:

> **What relationship, state, expectation, or memory are we currently unable to represent?**

This is the transition from data accumulation to intelligence architecture.

---

# PART XXXVI — DIRECT HANDOFF TO CLAUDE / FABLE

# 351. How to Read This Document

Do not treat every coined term as a required product feature.

The document deliberately contains three categories:

### Architectural principles

These are strong recommendations.

Examples:

- one global cognitive core;
- market-specific sensors;
- point-in-time ontology;
- economic/narrative/trading separation;
- persistent state;
- expectation/surprise;
- historical replay.

### Research hypotheses

These deserve empirical testing.

Examples:

- leadership renewal;
- attention acceleration;
- theme breadth;
- dislocation resolution;
- lifecycle transitions.

### Creative hypotheses / metaphors

These are designed to stimulate further thought.

Examples:

- Narrative Rₙ;
- Theme Gravity;
- Theme Pressure;
- Potential Energy;
- Theme Entropy.

Do not accidentally promote the third category into production because the name sounds cool.

---

# 352. What the Next Session Should Do First

Before planning implementation, critique the architecture.

Specifically ask:

1. Which ideas are genuinely distinct?
2. Which are redundant representations of the same latent state?
3. Which are measurable with current data?
4. Which require licensing?
5. Which are vulnerable to look-ahead?
6. Which should be universal schemas?
7. Which should remain market-specific?
8. Which hypotheses have known academic support?
9. Which should be tested on a small pilot theme universe?
10. Which outputs create the strongest product differentiation?

Then propose a staged research/build architecture.

---

# 353. Do Not Lose the Original Spirit During Engineering

The danger is that the next phase converts this into:

```text
Table: themes
Table: constituents
API: /themes
Page: theme dashboard
```

and declares victory.

That would miss the point.

The actual concept is:

> **A theme should know its history, current state, evidence, relationships, catalysts, expectations, and surprises.**

A table of constituents is only the skeleton.

---

# 354. Preserve the “Why Now?” Question

For every system feature, ask:

```text
Why does this matter now?
```

Theme exposure without catalyst:

> structural context.

Theme exposure + catalyst:

> activated opportunity.

Catalyst + market confirmation:

> current regime.

Catalyst + market rejection:

> surprise.

That sequence is cognition.

---

# 355. Preserve the “What Should Happen Next?” Question

This is perhaps the single most important instruction.

Do not allow the architecture to become purely descriptive.

Every meaningful state should eventually emit:

```text
expected consequences
```

Even if the expectation is low-confidence.

Otherwise the system cannot learn from outcomes.

---

# 356. Preserve Contradiction

Do not force all lobes to agree.

Example:

```text
Fundamental:
bullish

Narrative:
bullish

Flow:
bullish

Price:
weak
```

The contradiction may be the signal.

The Cortex should ask:

> Why is price refusing to confirm?

A system that averages all four into `+0.5` destroys the interesting part.

---

# 357. Preserve Provenance

The next architecture should make it impossible to forget whether an idea came from:

- official data;
- licensed vendor;
- deterministic transformation;
- LLM inference;
- historical model.

This is both a trust feature and a debugging feature.

---

# 358. Preserve Point-in-Time Integrity

Do not accept a beautiful backtest built on today's semantic knowledge.

This may be the hardest engineering problem in the theme project.

It is also one of the most important.

---

# 359. Preserve Market Specificity

Do not erase:

```text
涨停
连板
龙虎榜
游资
```

by converting everything into generic global factors.

China's local grammar is information.

Likewise do not underuse:

```text
ETF mechanics
options
13F
earnings revisions
```

in the US merely for symmetry.

---

# 360. Preserve the Human-Understandable Narrative

The internal architecture can be complex.

The output should remain understandable.

The user should receive:

> “Commercial Space is moving from Discovery to Expansion because breadth, capital and narrative propagation are broadening. The move is not yet heavily crowded. The primary risk is that the overnight catalyst has not translated into fundamental evidence.”

That is the product.

Not:

```text
ThemeComposite = 0.7127
```

---

# 361. Final Challenge to the Next Session

The next session should not ask only:

> “How do we build this?”

It should also ask:

> **“What would make this idea substantially smarter than what is written here?”**

Look for:

- missing states;
- missing relationships;
- better statistical formulations;
- more defensible proprietary data;
- ways to simplify;
- ways to falsify;
- unexpected cross-market applications.

This document is not intended to close the design.

It is intended to elevate the starting point of the next design session.



# PART XXXVII — THE TEN MOST IMPORTANT CREATIVE INTEGRATIONS

This section exists because a long architecture can obscure its own highest-value ideas.

If the next session remembers only ten things, retain these.

# 362. Theme Graph as Semantic Bus

The Theme Graph is not another content page.

It is the **semantic bus** connecting:

```text
macro
companies
supply chains
participants
catalysts
alternative data
commodities
local markets
```

It lets independent lobes talk about the same underlying economic object.

---

# 363. Economic Reality × Narrative Reality × Trading Reality

Do not collapse these.

The disagreement between them is often exactly where the opportunity lies.

```text
Reality ahead of narrative   → hidden beneficiary
Narrative ahead of reality   → optionality or excess
Trading ahead of both        → reflexive proxy / speculation
All three aligned            → confirmed thematic exposure
```

This may become the most reusable conceptual framework in the project.

---

# 364. Market State Is a Trajectory, Not a Snapshot

Persistent intelligence means:

```text
current value
+
trajectory
+
velocity
+
history
+
relationships
+
expectations
+
surprise
```

This applies to:

- rates;
- sentiment;
- theme breadth;
- attention;
- flows;
- valuation.

A dashboard reports level.

A brain understands how the level got there.

---

# 365. Theme Lifecycle + Top Recognition Should Be One System

Long-side discovery and short-side fragility are not separate universes.

They are opposite regions of the same lifecycle.

```text
Discovery
→ Expansion
→ Maturity
→ Crowding
→ Distribution
```

This unifies:

- rotation;
- breakout selection;
- risk;
- bubble detection;
- short timing.

---

# 366. Narrative Propagation Is Different From Price Momentum

A theme can spread before it reprices.

Measure:

- new companies;
- new subthemes;
- attention;
- analyst coverage;
- new economic evidence.

This creates the possibility of detecting **semantic expansion before price diffusion**.

---

# 367. Capital Has Species

Do not ask only:

> How much money?

Ask:

> What kind of money?

Different capital has different horizons and meanings.

This transforms raw flow into behavior.

---

# 368. Dislocations Are Relationship Violations

Once Mastermind models relationships, it can hunt:

```text
price vs theme
price vs fundamentals
price vs commodity
flow vs price
attention vs price
expected relation vs realized relation
```

This turns the graph into an alpha engine.

---

# 369. Expectation and Surprise Create Machine Experience

A system that never says what it expected cannot learn that it was wrong.

The loop:

```text
state
→ expectation
→ outcome
→ surprise
→ explanation
→ memory
```

is the bridge from data processing to experience.

---

# 370. US + China Should Share Cognition, Not Microstructure

This phrase captures the amalgamation strategy.

Shared:

```text
state
theme
evidence
event
relationship
expectation
memory
```

Different:

```text
China: limit-up / auction / 龙虎榜 / sentiment
US: ETF / options / filings / 13F / revisions
```

One mind, different senses.

---

# 371. Historical Replay Can Compress Decades of Apprenticeship

This is the long-term force multiplier.

If every historical state becomes:

```text
what was known
what was expected
what happened
what was learned
```

Mastermind can acquire an experience library no human analyst can manually accumulate.

That may eventually become the deepest moat in the entire system.

---

# PART XXXVIII — RESEARCH GROUNDING AND REFERENCE MAP

This project contains substantial original synthesis, but several external sources materially validate its components. These should be treated as grounding references, not authorities that dictate the architecture.

## 372. Internal Source Material

### Mastermind Dynamic Theme Graph — Institutional Brainstorming & Strategic Ideation Memo

Key ideas inherited:

- GICS is insufficient for modern thematic intelligence;
- companies should be multi-label weighted nodes;
- separate business, narrative, and market exposure;
- build hierarchical themes;
- make themes persistent Neural Web objects;
- create theme factors and historical indices;
- discover themes dynamically;
- use themes in Prophet, rotation, short systems, and Risk Radar.

### Mastermind Cognitive Architecture v1

Key ideas inherited:

- deterministic nervous system + persistent world model + AI Cortex;
- lobe maturity ladder;
- event-driven Cortex;
- surprise as machine intuition;
- episodic / semantic / procedural memory;
- historical replay;
- state-conditioned weighting;
- novelty;
- Research Cortex;
- SENSE → UNDERSTAND → REMEMBER → NOTICE → THINK → PREDICT → EXPERIENCE → LEARN.

These two internal bodies of work should remain linked.

The current document effectively joins them.

---

# 373. Theia Insights

Relevant official materials:

- Dynamic industry classification:
  https://www.theiainsights.com/solutions/industry-classification/

- Theme Watch Indices:
  https://www.theiainsights.com/solutions/theme-watch-indices/

- Thematic Factor Risk Model:
  https://www.theiainsights.com/solutions/factor-model

- Hedge & Quant Funds use cases:
  https://www.theiainsights.com/clients/hedge-quant-funds/

Important lessons:

- dynamic one-to-many classification is institutionally viable;
- 245 major themes / 3,200+ microthemes demonstrate possible granularity;
- point-in-time thematic history has value;
- theme factors can be used for alpha, risk, rotation, and hedging;
- theme indices can serve as real-time maps of market rotation.

Mastermind should not attempt to reproduce Theia's economic-ontology objective exactly.

The opportunity is to **connect ontology to market behavior and cognition**.

---

# 374. S&P Kensho

Official material:

- S&P Kensho New Economies:
  https://www.spglobal.com/spdji/en/index-family/equity/kensho-new-economies/

- Investment Themes / New Economies methodology overview:
  https://www.spglobal.com/spdji/en/landing/investment-themes/new-economies/

Relevant lesson:

NLP and machine learning applied to filings and public data can detect emerging business activity and create systematic thematic universes.

This supports:

- filing-driven theme discovery;
- economic evidence extraction;
- dynamic company-theme mapping.

---

# 375. MSCI Strategy Explorer

Official material:

https://www.msci.com/data-and-analytics/index-data/strategy-explorer

Relevant lesson:

Plain-language investment themes can be mapped to company business segments through an LLM-driven workflow.

This validates eventual natural-language concept → theme universe capabilities.

Mastermind should then add:

```text
market state
+
history
+
catalyst
+
alpha
```

rather than stopping at exposure mapping.

---

# 376. Morningstar Thematic Indexes

Official material:

- Thematic Indexes:
  https://indexes.morningstar.com/thematic/

- Thematic Consensus Indexes:
  https://indexes.morningstar.com/insights/analysis/blt80f6ca3f09147608/morningstar-thematic-consensus-indexes

Relevant lessons:

- future revenue/profit impact can be used to estimate thematic relevance;
- holdings consensus across thematic funds can provide a separate market-derived relevance measure;
- theme relevance is inherently multi-method.

This reinforces Mastermind's decision to keep multiple exposure realities.

---

# 377. 同花顺 Official Public Surfaces

Relevant official/public pages:

- Data Center:
  https://data.10jqka.com.cn/

- Concept sectors:
  https://q.10jqka.com.cn/gn/

- i问财:
  https://search.10jqka.com.cn/stockpick/index

These publicly visible surfaces reinforce the screenshot observations:

- 龙虎榜;
- financing/margin data;
- concept flows;
- industry flows;
- big-order tracking;
- new highs/lows;
- technical selection;
- concept timelines;
- driver events;
- leading stocks.

The product's value lies in how many market-ecology dimensions are integrated into the retail workflow.

---

# 378. China Market Structure — Official Exchange Sources

## Shanghai / STAR Market

Shanghai Stock Exchange:

https://star.sse.com.cn/en/gettingstarted/features/investors/

https://english.sse.com.cn/start/trading/mechanism/

Current official explanations describe:

- no regular price limit for the first five STAR IPO trading days;
- 20% daily limit thereafter.

## ChiNext

Shenzhen Stock Exchange investor education:

https://investor.szse.cn/knowledge/stock/chinext/t20200729_580056.html

Official explanation:

- first five IPO trading days have no price limit;
- thereafter 20%.

## Beijing Stock Exchange

Current trading rules:

https://www.bse.cn/jygl_list/200028217.html

Current BSE rules effective in 2026 retain:

- 30% daily limit under ordinary price-limited trading;
- defined no-limit cases;
- auction dissemination including reference price, matched and unmatched volume.

The implication is architectural:

> Market-rule metadata belongs in the feature layer.

---

# 379. Stock Connect Dissemination

HKEX official announcement:

https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en

Relevant change:

- old real-time Northbound buy/sell/total turnover dissemination was removed;
- selected historical aggregate turnover/trade/ETF/top-security information remained;
- Northbound shareholding disclosure became less frequent.

This should be encoded as an information-regime change.

Never assume an old data field remains currently observable.

---

# 380. SEC EDGAR

Official API documentation:

https://www.sec.gov/search-filings/edgar-application-programming-interfaces

Form 13F datasets:

https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets

Relevant capabilities:

- real-time-ish submissions metadata;
- filing histories;
- XBRL company facts;
- bulk archives;
- structured 13F data.

This provides a strong primary-source foundation for US evidence.

---

# 381. FINRA Short-Sale / Short-Interest Data

Official:

https://www.finra.org/finra-data/browse-catalog/short-sale-volume

FINRA's explanatory warning:

https://www.finra.org/investors/insights/short-interest

Key semantic lesson:

```text
short-sale volume != short interest
```

This distinction should be encoded into Mastermind's ontology.

---

# 382. OCC Options Data

Official OCC:

- Volume Query:
  https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/volume-query

- Volume by Account Type:
  https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/volume-by-account-type

- Open Interest:
  https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/open-interest

These establish useful public baseline derivatives data.

Commercial feeds can enrich them.

---

# 383. Investor Attention Research

Useful research examples:

### Limited attention and ChiNext stock performance

Zhang / Wang line of research using Baidu Index as a direct attention proxy.

ScienceDirect:
https://www.sciencedirect.com/science/article/pii/S026499931500156X

Key finding direction:

- attention relates to contemporaneous abnormal returns;
- price-pressure effects can reverse.

### Investor attention factors and Chinese stock returns

https://www.sciencedirect.com/science/article/pii/S1042443121002031

Key idea:

- both level and changes in attention can matter;
- attention-augmented factor models explain return anomalies better than baseline models in that study.

### Investor co-attention and return co-movement

https://www.sciencedirect.com/science/article/pii/S1062940821001583

Key idea:

- co-attention can help explain co-movement beyond fundamentals/firm characteristics.

This supports the `Attention Plane`, but not a simplistic directional signal.

---

# 384. Bubble / Top-Recognition Research

Greenwood, Shleifer & You:

NBER:
https://www.nber.org/papers/w23191

The key lessons:

- large run-ups alone do not imply poor forward returns;
- they do increase crash probability;
- turnover, volatility, issuance, and price-path characteristics help distinguish crash-prone episodes.

This strongly supports:

```text
extension != top
```

and the need to model **fragility transitions**.

A 2026 NBER extension of long-run US bubble/crash evidence also re-examines the Greenwood-Shleifer-You framework over a much longer history:

https://www.nber.org/papers/w34903

---

# PART XXXIX — FINAL MASTERBRAIN CONCEPT

# 385. The Destination in One Sentence

> **Mastermind should become a persistent market intelligence organism that continuously maps economic and narrative reality into a dynamic graph, observes how capital is interacting with that graph across markets, remembers comparable historical states, forms expectations, notices when reality violates them, and learns which relationships matter under which conditions.**

That is the complete synthesis.

---

# 386. The Product Thesis in One Sentence

> **Show investors not merely what moved, but what is changing beneath the move, where capital and narratives are propagating next, and whether the market's current behavior is historically healthy, fragile, or dislocated.**

---

# 387. The China Thesis in One Sentence

> **Turn the unusually rich A-share retail ecology exposed by 同花顺 — themes, heat, limit-up dynamics, auctions, 龙虎榜, flows, and local liquidity — into machine-readable persistent state rather than leaving synthesis entirely to the trader.**

---

# 388. The US Thesis in One Sentence

> **Bring institutional-grade dynamic thematic intelligence into a retail-accessible system, then exceed static ontology providers by attaching live market state, catalysts, capital behavior, historical memory, and reasoning.**

---

# 389. The Neural Web Thesis in One Sentence

> **The Neural Web should not merely contain more data planes; it should know how the planes relate, what changed, what it expected, what surprised it, and what prior experience says matters now.**

---

# 390. The Historical Replay Thesis in One Sentence

> **Use point-in-time historical replay to convert decades of market history into structured synthetic lived experience, allowing Mastermind to learn not just correlations but which interpretations repeatedly succeeded or failed.**

---

# 391. The Strategic Moat in One Sentence

> **The moat is not the taxonomy; it is the compounding combination of point-in-time semantic relationships, historical state, alternative evidence, cross-market behavior, calibrated expectations, and accumulated experience.**

---

# 392. The Final Warning

The greatest risk is not that this vision is too ambitious.

The greatest risk is that implementation makes it ordinary.

If this is reduced to:

```text
Theme table
Theme page
Heat score
AI summary
```

then the project has failed intellectually even if the software works.

The architecture should preserve:

```text
STATE
RELATIONSHIPS
MEMORY
EXPECTATIONS
SURPRISE
LEARNING
```

Those are the pieces that turn a terminal into an intelligence system.

---

# 393. Final Instruction to Claude / Fable

Treat this memo as a **high-energy research prior**, not a fixed specification.

Your job in the next session is to:

1. understand the complete conceptual system;
2. criticize weak assumptions;
3. identify redundant concepts;
4. preserve genuinely novel integrations;
5. research the hardest empirical questions;
6. formalize the universal vs market-specific interfaces;
7. propose the smallest architecture that preserves the intelligence vision;
8. design validation before scale;
9. explicitly protect point-in-time integrity;
10. ensure every advanced inference remains grounded in evidence and uncertainty.

Most importantly:

> **Do not build a prettier collection of dashboards. Build the substrate that allows Mastermind to understand why the dashboards matter.**

---


# PART XL — THEME INDEX AND BASKET CONSTRUCTION AS A RESEARCH INSTRUMENT

This section intentionally returns to the original US thematic-basket problem in much greater detail. The basket itself is not the final product, but constructing several honest, point-in-time baskets is how Mastermind can turn a semantic theme into a quantitative object that can be studied, compared, replayed, and eventually reasoned about.

# 394. There Should Not Be One “True” Theme Index

A recurring mistake in thematic products is to argue over a single correct constituent list.

That is usually asking one basket to answer several incompatible questions.

For Mastermind, a theme should be the durable intelligence object; **indices are lenses on the object**.

For a single theme, maintain several basket views:

```text
Economic Purity Index
Trading Proxy Index
High Optionality Index
Emerging Beneficiary Index
Narrative Proxy Index
Supply-Chain Bottleneck Index
Leader Index
Secondary / Catch-Up Index
```

Each has a different objective function.

This also solves a conceptual fight that otherwise becomes endless:

> Is Company X “really” an AI company?

Mastermind can answer:

```text
Economically:       weak/moderate
Narratively:        strong
Trading behavior:   very strong
Future optionality: high
```

There is no need to force a binary verdict.

---

# 395. Economic-Purity Basket

Purpose:

> Measure the securities whose current and near-term economics are most directly dependent on the theme.

Possible evidence:

- segment revenue;
- segment operating profit;
- backlog;
- customer concentration;
- disclosed contracts;
- direct CapEx;
- production capacity;
- management guidance.

Possible weighting logic:

```text
Economic Weight
=
Exposure
× Confidence
× Materiality
× Liquidity Adjustment
```

Useful for:

- structural theme performance;
- long-horizon portfolio exposure;
- fundamental attribution;
- clean economic comparisons.

Weakness:

It will often be late to genuine emerging optionality because accounting disclosures lag reality.

That weakness is not a reason to alter the basket.

It is a reason to maintain a separate optionality basket.

---

# 396. High-Optionality Basket

Purpose:

> Identify companies where the theme could become economically important even if it is not yet a major reported business.

Evidence:

- R&D;
- new products;
- announced capacity;
- strategic partnerships;
- capex;
- early customer wins;
- management commitment;
- regulatory approvals;
- supply-chain positioning.

Potential attributes:

```text
CurrentExposure
FutureExposureRange
ProbabilityOfMaterialization
TimeToMateriality
EvidenceVelocity
```

This is particularly useful for technological transitions.

An emerging winner often looks economically “impure” before it becomes obvious.

---

# 397. Trading-Proxy Basket

Purpose:

> Identify the securities the market is currently using to express the narrative.

Inputs:

- residual theme beta;
- event-day co-movement;
- intraday synchronization;
- options co-movement;
- relative turnover;
- attention;
- repeated reaction to theme catalysts.

This basket may change quickly.

That is appropriate.

It is measuring market behavior, not corporate identity.

Example:

A company can enter the Trading Proxy basket for three months during a speculative cycle and later leave without its business changing.

---

# 398. Narrative-Proxy Basket

Purpose:

> Identify the companies most strongly associated with the theme in the current information environment.

Possible evidence:

- news co-mentions;
- analyst note language;
- earnings-call theme mentions;
- search associations;
- social discourse;
- thematic ETF ownership;
- broker baskets.

This can be especially useful for measuring:

- attention;
- speculative breadth;
- narrative infection;
- theme washing.

It should not be confused with economic purity.

---

# 399. Bottleneck Basket

Purpose:

> Identify companies controlling scarce inputs or capabilities that constrain theme expansion.

This is potentially one of the most valuable second-order baskets.

Examples:

AI:

```text
GPU availability
HBM
advanced packaging
power transformers
grid interconnection
cooling
```

Space:

```text
launch capacity
radiation-hardened components
satellite buses
propulsion
specialty materials
```

Defense:

```text
rocket motors
energetics
radars
rare materials
shipyard capacity
```

A bottleneck can experience disproportionate pricing power.

The bottleneck basket therefore asks:

> Where does the economic system break if demand accelerates faster than supply?

That is a more interesting question than “which stocks mention AI?”

---

# 400. Leader Basket

The current leaders should be tracked separately from the whole theme.

Possible leader definitions:

```text
Price Leader
Liquidity Leader
Narrative Leader
Fundamental Leader
Institutional Leader
```

Do not assume they are the same security.

A theme can have:

```text
Fundamental anchor:   NVDA
Trading leader:       another high-beta name
Power bottleneck:     VRT-like company
Attention leader:     speculative proxy
```

This internal differentiation gives the Cortex a richer picture.

---

# 401. Secondary / Catch-Up Basket

This basket explicitly supports dislocation research.

Candidate characteristics:

```text
economic relevance high
theme beta historically high
current residual return low
no obvious negative catalyst
```

Then ask:

> Do these laggards historically catch up during healthy Expansion states?

This is more rigorous than scanning for “cheap-looking” related stocks.

---

# 402. Basket Weighting Should Match the Question

Possible weighting methods:

```text
Equal Weight
Market Cap Weight
Float Weight
Economic Exposure Weight
Narrative Exposure Weight
Trading Beta Weight
Risk-Parity Weight
Liquidity-Capped Weight
```

Do not debate which is universally best.

Store several.

The factor model may use one weighting while a user-facing investable basket uses another.

---

# 403. Concentration Caps Are Not Just Portfolio Rules

Concentration can distort inference.

If one mega-cap explains 70% of a theme index:

```text
Theme return
≈
single-stock return
```

That is bad for measuring theme state.

Therefore maintain:

```text
Raw Economic Basket
and
Analytical De-Concentrated Basket
```

The latter is useful for:

- breadth;
- residual factor;
- theme-specific behavior.

---

# 404. Theme Factor vs Investable Index

These should not be synonymous.

## Investable Index

Needs:

- liquidity;
- turnover controls;
- concentration limits;
- rebalance rules.

## Research Theme Factor

Can prioritize:

- signal purity;
- exposure neutrality;
- sector neutrality;
- market neutrality.

The Research Cortex may care more about the second.

The product may expose both.

---

# 405. Point-in-Time Reconstitution

Each rebalance should only use evidence available by that date.

For every membership decision:

```text
candidate
evidence
evidence_time
score
decision_time
```

This makes historical basket returns auditable.

A theme index with today's membership backfilled through history is not historical intelligence.

It is a hindsight chart.

---

# 406. Theme Entry and Exit Should Have Hysteresis

If membership threshold is:

```text
score > 0.60
```

a company fluctuating:

```text
0.59 → 0.61 → 0.59
```

should not repeatedly enter and leave.

Use:

```text
entry threshold
exit threshold
minimum persistence
```

This reduces semantic churn.

Temporary Trading Proxy baskets can be more dynamic than Economic Purity baskets.

Different basket types should have different hysteresis.

---

# 407. Membership Confidence and Portfolio Weight Are Different

A company can have:

```text
confidence = 95%
exposure = 20%
```

or:

```text
confidence = 60%
exposure = 80%
```

Do not multiply these blindly without preserving both.

Confidence says:

> How sure are we about the estimate?

Exposure says:

> How large is the relationship?

Those are different dimensions.

---

# 408. The Basket Should Expose Its Reasoning

For each member:

```text
Why included?
What evidence?
Which role?
What exposure?
What changed?
```

Example:

```text
Company X

Theme:
AI Power Infrastructure

Economic exposure:
42%

Role:
Power-distribution bottleneck

Evidence:
3 contracts
capex expansion
revenue segment
management guidance

Narrative exposure:
31%

Trading exposure:
57%

Confidence:
High
```

This is how Mastermind becomes transparent.

---

# 409. Theme Basket Drift Can Be Intelligence

Changes in constituents are not merely maintenance.

They can show how the economic story is evolving.

Example:

```text
AI Infrastructure 2024:
GPU / HBM dominant

AI Infrastructure 2026:
power / cooling / generation weights rise
```

The index composition itself contains information:

```text
ThemeSemanticDrift
```

That should feed historical memory.

---

# 410. Theme “Pure Play” Is Context-Dependent

A company may be a pure economic exposure but a poor trading proxy due to:

- conglomerate effects;
- hedging;
- regulation;
- capital structure;
- foreign listing;
- illiquidity.

Likewise a narrative proxy may be economically impure.

Do not allow marketing concepts like “pure play” to collapse these distinctions.

---

# PART XLI — A MORE FORMAL THEME DISCOVERY PIPELINE

# 411. Theme Discovery Has Two Problems

There are two different tasks:

## Known-Theme Maintenance

We know:

> Commercial Space exists.

Question:

> Which companies belong and how are exposures changing?

## Unknown-Theme Discovery

We do not yet know the correct concept name.

Question:

> Why are these companies, documents, and catalysts suddenly clustering?

The second is much harder.

Treat them separately.

---

# 412. Known-Theme Maintenance Pipeline

Conceptually:

```text
Source documents
    ↓
Entity + segment extraction
    ↓
Evidence claims
    ↓
Theme relevance inference
    ↓
Economic / Narrative / Trading scores
    ↓
Temporal comparison
    ↓
Edge update candidate
    ↓
Validation
```

The system should explain:

> Why did exposure change?

---

# 413. Unknown-Theme Discovery Pipeline

A richer pipeline:

```text
1. Detect semantic novelty
2. Detect unusual co-mentions
3. Detect new market co-movement
4. Detect common catalysts
5. Detect supply-chain coherence
6. Detect attention diffusion
7. Cluster candidate entities
8. Generate possible concept descriptions
9. Search for prior/existing theme overlap
10. Validate economic coherence
11. Create temporary candidate node
12. Observe whether the candidate persists
```

Do not create permanent nodes immediately.

---

# 414. Candidate Theme Incubation

Candidate themes should have a probation period.

```text
Candidate Theme:
Orbital Computing

Evidence:
5 companies
3 credible source clusters
2 related contracts
cross-sectional co-movement
growing narrative attention

Age:
12 days

Confidence:
0.72

Status:
Incubating
```

Graduation requires:

- persistence;
- economic coherence;
- distinctiveness;
- enough securities;
- market or research relevance.

This prevents the ontology from exploding.

---

# 415. Theme Merge and Split

Themes evolve.

Two candidate themes may prove identical.

One mature theme may split.

Examples:

```text
AI Infrastructure
→ AI Compute
→ AI Power
```

or:

```text
Space Communications
+
Direct-to-Device
```

may merge temporarily depending on market behavior.

The ontology needs:

```text
MERGED_INTO
SPLIT_FROM
RENAMED_FROM
```

with historical validity.

---

# 416. Semantic Neighbors Are Different From Parent/Child

Example:

```text
AI Power
```

Parent:

```text
AI Infrastructure
```

Neighbors:

```text
Grid Modernization
Nuclear Renaissance
Gas Turbines
```

They are related but not children.

This distinction matters for contagion.

---

# 417. Temporary Event Themes Should Be Allowed

Some tradable narratives are transient:

```text
bank rescue
specific tariff
earthquake reconstruction
Olympics
election trade
```

They may deserve nodes for weeks/months.

Use:

```text
ThemeType = Structural | Cyclical | Event
```

with different decay and archival behavior.

---

# 418. Theme Naming Should Follow Market Language Without Becoming Captive to It

A useful theme name should be:

- recognizable;
- semantically precise;
- stable enough for history.

Store aliases:

```text
AI Power
Data Center Power
AI Electricity Demand
```

This lets the graph understand changing terminology without constantly creating new themes.

---

# 419. Multilingual Ontology Is a Major Cross-Market Requirement

China and US market language differ.

Examples:

```text
商业航天
Commercial Space

算力
Compute / Computing Power

低空经济
Low-Altitude Economy

人形机器人
Humanoid Robotics
```

Direct translation can lose local meaning.

The ontology should store:

```text
canonical global concept
local-language label
local market definition
market-specific subthemes
```

This enables semantic bridges without forcing English concepts onto China.

---

# 420. Local Narratives Can Be Economically Distinct Even When Translation Looks Similar

“AI” in the US and `人工智能` in A-shares may activate different company sets.

The reasons include:

- domestic supply chains;
- policy;
- listing universe;
- investor conventions;
- national technology priorities.

Therefore:

```text
GlobalConcept
≠
IdenticalLocalBasket
```

This is a core rule.



# PART XLII — RESEARCH VERIFICATION, CURRENT MARKET-STRUCTURE CORRECTIONS, AND SOURCE-OF-TRUTH NOTES

The conceptual architecture above is intentionally broader than any one vendor or paper. Before finalizing this handoff, several externally verifiable assumptions were checked against current primary/official sources. This section records the most important conclusions so the next session does not accidentally build on stale market rules or overstate what commercial products actually provide.

# 421. Theia Is Strong Validation of the Underlying Ontology Problem

Current official Theia materials describe its Industry Classification as:

- one-to-many rather than one-company/one-industry;
- dynamically updated;
- global;
- backed by 13+ years of historical data;
- covering 50,000+ public companies;
- spanning 245 major themes and 3,200+ microthemes.

Its public documentation also says exposures incorporate much more than current revenue, including:

- products and services;
- R&D and CapEx;
- target markets and use cases;
- partnerships;
- acquisitions.

Official source:

https://www.theiainsights.com/solutions/industry-classification/

This materially strengthens the decision to treat company-theme membership as:

```text
multi-dimensional
evidence-backed
time-varying
point-in-time
```

rather than as a keyword tag.

It also raises the bar.

A one-pass LLM classification of several thousand equities is not a credible substitute for the full concept.

The sensible Mastermind strategy is to begin narrower and make the **trading intelligence around each theme deeper**.

---

# 422. Theia's Theme Watch Indices Validate the “Theme Market State” Idea

Theia currently describes its Theme Watch Indices as daily-updated performance across 200+ existing and emerging themes and regions, used for:

- thematic momentum and rotation;
- leaders/laggards;
- benchmarking;
- attribution;
- risk and hedging;
- thematic product research.

Official source:

https://www.theiainsights.com/solutions/theme-watch-indices/

This validates a core layer of the Mastermind plan:

```text
theme
→ persistent quantitative time series
→ relative strength
→ rotation
→ historical state
```

But it also clarifies the differentiation.

A Theme Watch Index is still largely:

> What is the theme doing?

Mastermind's ambition is:

```text
What is the theme doing?
Why?
Who is driving it?
How healthy is it?
Where is it in its lifecycle?
What should happen next?
What would falsify the interpretation?
```

---

# 423. Theia's Thematic Factor Model Confirms That Theme Factors Can Sit Beside Traditional Factors

Current Theia materials describe a factor model with 200+ thematic factors plus market/style drivers, daily updates, and uses in:

- signal generation;
- portfolio intelligence;
- risk;
- thematic rotation and timing.

Official source:

https://www.theiainsights.com/solutions/factor-model/

This substantially de-risks the intellectual leap from:

```text
theme classification
```

to:

```text
theme factor
```

The key Mastermind research challenge is therefore not whether thematic factors can exist.

It is whether Mastermind can extract additional alpha or explanatory power from:

```text
theme state
theme lifecycle
theme attention
theme evidence
theme participants
theme surprise
```

on top of the factor itself.

---

# 424. S&P Kensho Validates Public-Document-Driven Emerging-Economy Classification

S&P Dow Jones Indices states that its Kensho New Economy family uses a systematic methodology with machine learning and NLP over regulatory filings and other public information to identify companies involved in emerging economic themes. It explicitly emphasizes that standard industry schemes do not capture the interconnectedness and fluidity of new economic systems.

Official source:

https://www.spglobal.com/spdji/en/landing/investment-themes/new-economies/

This is especially relevant to Mastermind because it supports:

```text
filing semantics
+
company strategy
+
economic-system classification
```

rather than requiring current revenue to be the sole criterion.

---

# 425. S&P Kensho Also Surfaces an Important Backtest Warning

S&P's index pages explicitly warn that pre-launch performance is hypothetical back-tested performance and can reflect hindsight/survivor effects.

That warning should be treated as an architecture lesson.

Official source example:

https://www.spglobal.com/spdji/en/index-family/equity/kensho-new-economies/

Mastermind should be stricter:

```text
today's ontology
must not
silently rewrite yesterday's investable universe
```

If a theme is discovered in 2026, historical research must reconstruct:

> What evidence existed at the historical date?

This is one of the most important safeguards in the entire project.

---

# 426. MSCI Validates Natural-Language Theme → Business-Segment Mapping

MSCI's current Strategy Explorer allows investment ideas expressed in plain language to be mapped to company business segments through an LLM-driven workflow. MSCI states that its Strategy Exposure methodology measures the share of company revenue from business segments matched to the strategy.

Official source:

https://www.msci.com/data-and-analytics/index-data/strategy-explorer

This reinforces two ideas simultaneously:

1. natural-language concept-to-universe construction is becoming institutional infrastructure;
2. Mastermind should retain a separate **trading/narrative reality**, because a revenue-based strategy exposure answers only the economic side of the problem.

---

# 427. Morningstar Validates Both Fundamental and Market-Consensus Theme Relevance

Morningstar's thematic indexes use forward-looking analyst assessments of how a theme may affect future revenue and net profit.

Official source:

https://indexes.morningstar.com/thematic/

Morningstar separately maintains Thematic Consensus indexes that use public thematic-fund holdings to infer the securities most commonly associated with a theme.

Official source:

https://indexes.morningstar.com/morningstar-thematic-consensus-indexes

That is almost a real-world validation of the Mastermind idea:

```text
there is no single correct theme exposure
```

because:

```text
fundamental analyst relevance
≠
market-holdings consensus
≠
semantic relevance
≠
trading beta
```

The disagreements themselves deserve research.

---

# 428. 同花顺's Public Surfaces Confirm That Its Theme/Data Ecology Is Broader Than the Screenshots Alone

The publicly accessible 同花顺 Data Center currently surfaces categories including:

- 龙虎榜;
- 融资融券;
- 大宗交易;
- capital-flow and market information.

Official/public surface:

https://data.10jqka.com.cn/

Its concept pages expose dynamic concept baskets and fields such as fund-flow information:

https://q.10jqka.com.cn/gn/

i问财 currently exposes an AI/search-oriented natural-language investment query workflow:

https://search.10jqka.com.cn/stockpick/index

This supports the original interpretation:

> 同花顺 is not merely a quote terminal. It encodes a broad Chinese market ontology and a natural-language layer around local market behavior.

Mastermind's opportunity is not to reproduce the same screens.

It is to make these categories part of persistent machine cognition.

---

# 429. Current Shanghai / STAR Market Rules Reinforce Board-Aware Normalization

The Shanghai Stock Exchange currently states that STAR Market stocks use a 20% daily price limit and that the regular price limit does not apply during the first five trading days following an IPO.

Official source:

https://english.sse.com.cn/start/trading/mechanism/

SSE materials also distinguish the Main Board and STAR Market price-limit mechanisms.

Therefore:

```text
raw daily return
```

must never be interpreted without:

```text
venue
board
security status
rule regime
```

The `MarketRule` object proposed earlier is not optional for serious A-share backtesting.

---

# 430. Current Shenzhen Rules Also Require Time-Versioned Treatment

Shenzhen's official investor materials state that ChiNext IPOs have no price limit during their first five trading days and use a 20% daily price limit thereafter.

Official source:

https://www.szse.cn/www/investor/index/update/t20200729_580056.html

SZSE's registration-system materials also state that newly listed Main Board stocks have no regular price limit for the first five trading days, followed by the Main Board's normal 10% limit.

Official source:

https://www.szse.cn/www/investor/knowledge/t20230306_599093.html

This is a useful correction to older market folklore built around the prior first-day 44% IPO convention.

Historical research must know **which rules applied at each date**.

---

# 431. Current BSE Rules Confirm Both the 30% Regime and the Richness of Auction State

The Beijing Stock Exchange published revised trading rules in April 2026, effective July 6, 2026.

Official current rule:

https://www.bse.cn/jygl_list/200028217.html

The rulebook defines auction information including:

```text
reference price
matched volume
unmatched volume
```

and BSE's ordinary equity framework continues to include its distinct wider price-limit regime.

This reinforces the idea that:

```text
auction state
```

is a real observable market object.

It should not merely be screenshot decoration.

---

# 432. Stock Connect Data Availability Changed — Do Not Rebuild a Dead “Live Northbound Flow” Assumption

HKEX, SSE and SZSE announced changes to Stock Connect information dissemination in 2024.

For Northbound trading, the former real-time:

```text
buy turnover
sell turnover
total turnover
```

would no longer be available in the same way.

Historical aggregates such as daily/monthly total turnover, trade counts, ETF turnover, and top active-stock turnover remain part of the disclosed information set, while Northbound shareholding search frequency also changed.

Official HKEX announcement:

https://www.hkex.com.hk/News/Market-Communications/2024/2404122news?sc_lang=en

This is important enough to repeat:

> **Do not architect the live China system around obsolete real-time Northbound flow fields.**

If Mastermind estimates direction from other data, call it an inference and attach confidence.

---

# 433. SEC Data Gives the US Theme Graph a Strong Primary-Source Backbone

The SEC's official EDGAR APIs currently provide:

- filer submission histories;
- XBRL company facts;
- metadata;
- bulk JSON archives.

The SEC states that submissions and XBRL APIs update throughout the day, with bulk archives refreshed on a scheduled basis.

Official source:

https://www.sec.gov/search-filings/edgar-application-programming-interfaces

Structured Form 13F datasets are also published by the SEC:

https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets

This makes a primary-source evidence layer highly feasible.

The hard part is not “can we get filings?”

The hard part is:

```text
entity normalization
semantic extraction
point-in-time evidence
theme mapping
corporate-history tracking
```

---

# 434. FINRA's Warning Should Become a General Semantic-Integrity Rule

FINRA explicitly explains that its short-sale volume data:

- reflects publicly disseminated off-exchange short-sale transactions in the covered facilities;
- is not consolidated with all exchange trading in the simple daily file;
- is **not equivalent to reported short-interest positions**.

Official source:

https://www.finra.org/finra-data/browse-catalog/short-sale-volume

This is an excellent example of a broader Mastermind principle:

> **Never allow a convenient retail label to replace the actual semantics of the source field.**

If the source says:

```text
off-exchange short-sale volume
```

store exactly that.

Any interpretation of bearish positioning must be a separate inferred belief.

---

# 435. OCC Offers Useful Public Options Baselines, but Do Not Pretend They Equal Full Flow Intelligence

OCC's current public reports include:

- daily volume;
- open interest;
- volume query by underlying/symbol;
- calls vs puts;
- volume by account type;
- exchange-level reports.

Official sources:

https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/volume-query

https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/open-interest

https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/volume-by-account-type

These can support a public baseline.

More granular intraday trade classification, quote history, Greeks, dealer-position inference, or long-depth history may still require licensed data and Mastermind modeling.

Again:

```text
official observable
+
licensed enrichment
+
internal inference
```

is the correct architecture.

---

# 436. Attention Research Supports the Attention Plane but Also Warns Against “Heat = Bullish”

Research on Chinese listed firms using abnormal Baidu search volume reports a positive association with contemporaneous returns and trading volume, with subsequent reversal in the return effect in the cited sample.

One accessible citation:

Yang, Ma, Wang & Wang, *Does Investor Attention Affect Stock Trading and Returns? Evidence from Publicly Listed Firms in China*, Journal of Behavioral Finance.

Reference:

https://www.tandfonline.com/doi/abs/10.1080/15427560.2020.1785469

Other research has also studied Baidu search volume as a China investor-attention proxy and found time-varying relationships.

The architectural lesson:

```text
attention is real
but
its sign is conditional
```

That directly supports the choice to model:

```text
level
velocity
acceleration
source
breadth
price context
lifecycle
```

instead of treating popularity as a buy signal.

---

# 437. Bubble Research Strongly Supports the Fragility-State Approach

Greenwood, Shleifer and You's *Bubbles for Fama* studies large industry run-ups and reports:

- large run-ups do not, on average, mechanically imply unusually low future returns;
- large run-ups are associated with greater crash probability;
- features including volatility, turnover, issuance, and the price path can help distinguish more crash-prone episodes.

NBER:

https://www.nber.org/papers/w23191

This should remain a foundational principle for Mastermind:

```text
Extension
≠
Top
```

Therefore the Short / Top Recognition system should not fight strong themes merely because they are extended.

The research problem is the transition:

```text
Extended + Healthy
        ↓
Extended + Fragile
        ↓
Distribution
```

That integrates naturally with the Theme Lifecycle Engine.

---

# PART XLIII — FINAL SYSTEM MAP FOR FABLE

# 438. The Most Important Inputs

Think in categories, not vendor names.

```text
MARKET
price, volume, breadth, volatility, liquidity

FUNDAMENTALS
filings, earnings, estimates, segment economics

THEMES
ontology, constituents, factors, lifecycle

NARRATIVE
news, research, search, social, semantic diffusion

CAPITAL
ETF, institutional, retail, leverage, participants

MICROSTRUCTURE
auction, limit-up, order-book, options, short data

MACRO
rates, FX, credit, commodities, policy

ALTERNATIVE
contracts, patents, trade, procurement, hiring, etc.
```

---

# 439. The Most Important Transformations

```text
Raw Observation
    ↓
Normalized Evidence
    ↓
State
    ↓
Trajectory
    ↓
Relationship
    ↓
Expected Consequence
    ↓
Surprise
    ↓
Experience
```

If Fable retains this chain, much of the architecture will remain coherent.

---

# 440. The Most Important Outputs

Do not think first in terms of pages.

Think in decisions:

```text
What changed?
What matters?
What is emerging?
What is spreading?
What is healthy?
What is fragile?
What is mispriced?
Who is acting?
What historically resembles this?
What is different?
What should happen next?
What invalidates the thesis?
```

A page should exist only if it helps answer one of these.

---

# 441. The Minimum Viable “Intelligence” Threshold

A feature deserves to be called intelligent only if it does more than expose a number.

For example:

### Not enough

```text
Theme return: +4.8%
```

### Better

```text
Theme return: +4.8%
Breadth: 81%
```

### Stateful

```text
Theme has moved from narrow leadership to broad participation over three sessions.
```

### Contextual

```text
The broadening occurred while liquidity improved and earnings revisions remained positive.
```

### Experienced

```text
Comparable states historically continued more often than they reversed.
```

### Self-aware

```text
Current state is unusually novel because valuation and macro conditions differ materially from the historical sample, so confidence is reduced.
```

That maturity ladder should guide product decisions.

---

# 442. The Minimum Viable “Theme Intelligence” Product

If the full organism feels too large, preserve these eight components:

```text
1. Point-in-time Theme Graph
2. Economic / Narrative / Trading exposure
3. Theme factor + residual return
4. Breadth + leadership
5. Attention + catalyst state
6. Lifecycle / fragility
7. Historical analogs
8. Why / what-next explanation
```

Then add market-specific sensors.

That already creates something meaningfully different from a normal screener.

---

# 443. The Minimum Viable China Intelligence Add-On

```text
1. Market sentiment state
2. Limit-up ecology
3. Yesterday-strategy reinforcement
4. Auction state
5. Theme flows
6. 龙虎榜 / participant state
7. Local policy/liquidity
8. Cross-market pre-open prior
```

This is the part most directly inspired by 同花顺.

But it should be represented as state, not copied as interface cards.

---

# 444. The Minimum Viable US Intelligence Add-On

```text
1. Filing-driven economic evidence
2. ETF theme consensus + flow
3. Options theme state
4. Earnings/revision breadth
5. Institutional ownership state
6. short/borrow context where legitimately available
7. supply-chain causal mapping
8. global thematic transmission
```

This fills a meaningful gap in US retail tools.

---

# 445. The “North Star” Test for Every Future Addition

Whenever someone proposes another feature, ask:

> Does this improve Mastermind's ability to **understand state, relationships, expectations, or learning**?

If yes:

consider it.

If it merely adds another isolated chart:

be skeptical.

---

# PART XLIV — COMPLETION NOTE

This memo now intentionally captures both the **broad vision** and the **reasoning substrate** behind it.

It incorporates:

- the original 同花顺 screenshot reverse engineering;
- the US Dynamic Theme Graph work;
- institutional thematic-intelligence research;
- the Neural Web cognitive architecture;
- market-state and persistent-memory concepts;
- narrative propagation;
- capital species;
- participant intelligence;
- A-share-specific microstructure;
- US-specific thematic and institutional data;
- dislocation hunting;
- top recognition / fragility;
- cross-market theme transmission;
- historical replay;
- expectation/surprise learning;
- Research Cortex;
- experimental proprietary metrics;
- validation warnings;
- strategic moat;
- practical research sequencing.

The document is intentionally larger than an implementation prompt.

That is the point.

The next Claude/Fable session should be able to understand **why** the architecture exists, not merely see a list of modules.

## Final synthesis

The project began with a deceptively simple observation:

> 同花顺 shows a lot of useful market information in one place.

The deeper conclusion is:

> **Those panels are fragments of a latent market state.**

The US thematic project then added:

> **Traditional taxonomies cannot represent the narratives and economic systems through which modern capital actually moves.**

The Neural Web adds:

> **State only becomes intelligence when it persists, relates to other state, produces expectations, remembers outcomes, and learns.**

Together:

```text
同花顺-style sensorium
        +
Dynamic Theme Graph
        +
Global / local world state
        +
Persistent memory
        +
Historical replay
        +
Deliberative Cortex
        +
Prophet
        +
Outcome learning
        =
Mastermind Market Intelligence Organism
```

That is the final conceptual handoff.

# END
