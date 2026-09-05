# Mastermind Single-Name Intelligence OS — Program Architecture Design

**Date:** 2026-08-28  
**Status:** Chairman-approved in-chat design direction; written architecture for review; no implementation, runtime, product, source procurement, model promotion, or trading authority is created by this document.  
**Operation:** `sni-architecture-freeze-20260828-sol-001`  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@bdcb00132692b7e2dc40d35a2d2e226f81efe2f4`, `mastermind.sol_skillpack.v1` v1.0.1, bootstrap-major 1 compatible.  
**Macro architecture pin:** `bca7221a2d0020d15d220ffa814b753d1a7a6561`.  
**Terminal architecture pin:** `b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`.  
**Initial reference organisms:** Alibaba Group issuer; 9988.HK and BABA as linked but distinct instruments; Tencent 0700.HK; U.S. stress set NVDA, MSFT, TSLA; later complete Mag 7.  

---

## 0. Executive ruling

Mastermind should build a **Single-Name Intelligence OS**, not a larger generic stock dossier and not a fleet of hand-coded ticker bots.

The product is a continuously updated **issuer + instrument digital twin, research workspace, forecasting laboratory, and learning system** for a deliberately small set of strategically important securities first. It should eventually scale to the Nasdaq 100, Dow 30, S&P 500, and beyond, but broad coverage is explicitly subordinate to making the first names extraordinary.

The ambition is not to be a better stock page. It is:

> For a covered name, Mastermind should know the company's operating truth, capital state, relationships, event memory, market-path behavior, listing-specific microstructure, positioning, expectations, historical response functions, current deviations from normal, and the complete record of what Mastermind previously believed — well enough that a serious investor can understand what changed, what is unusual, what is already incorporated, what could happen next, why, and what observable evidence would change the read.

The target bar is deliberately extreme:

> A serious investor should be able to spend twenty minutes inside the Alibaba, Tencent, Nvidia, Microsoft, or Tesla intelligence workspace and conclude that no other single product gives them a more coherent, source-grounded, continuously learning model of that individual security.

This does **not** mean the system is allowed to claim alpha, certainty, or trade authority because the product is comprehensive. Every predictive or decision-bearing claim remains subject to the existing prospective evaluation and promotion laws.

---

## 1. Why this is a new product surface but not a new truth plane

Today's stock dossier is intentionally compact. `engine/stock_dossier.py` composes already-computed action, why-now, why-not, staleness, authority, and deterministic no-buy reasons. The broad ticker-page builder similarly aggregates many existing organs into a public dossier. Those are useful glance projections and should remain so.

The Single-Name Intelligence OS is the deep workspace behind that glance.

It owns:

1. **single-name composition** — joining canonical issuer and instrument intelligence into one user journey;
2. **coverage profiles** — declaring which canonical sources and company-specific KPI/event families matter for each reference organism;
3. **new single-name research** that has no canonical owner today, especially residual/abnormal behavior, state-conditioned response surfaces, incorporation analysis, and forecast calibration;
4. **experience architecture** — the premium single-name command surface in Terminal and compact projections back to dossier surfaces;
5. **learning orchestration** — registering forecasts and research questions into existing qledger/Evaluation OS rather than creating a second grader.

It does **not** own a replacement identity graph, earnings corpus, filing store, news corpus, options store, market-data plane, event store, capital ledger, relationship graph, forecast grader, queue, agent lifecycle, or trading authority.

The architecture is therefore a **compiler and research layer over existing owners**, with new data acquisition only where an existing owner cannot lawfully supply a required observation.

---

## 2. Current capability ledger at the architecture pin

The current estate is unusually favorable for this program because many hard organs already exist.

| Capability | State | Current canonical interpretation for this program |
|---|---|---|
| Compact Stock Dossier / ticker-page composition | `BUILT_NOT_PROVEN` | Source pipeline is present and broad; this session did not separately production-browser-prove the live public surface. Keep it compact and use it as a projection, not the new semantic owner. |
| Stock Identity W0 archaeology / research contract | `PROVEN_LIVE` | Landed and governs per-instrument behavioral research. |
| Stock Identity W1 Atlas + W1-A1 identity correction | `PROVEN_LIVE` | Fingerprints, bars-only state, path episodes, dossiers, sealed partitions, and GOLD/Barrick repair exist. |
| Stock Identity W2 expert replay/provenance | `PROVEN_LIVE` | 31,119 era-pinned events / 34,491 attribution rows across 22 pilot names in the current recovery record; authority false. |
| Stock Identity executable ruler / real identity epochs / SIF / integrated consumer | `NOT_BUILT` | W3+ remains unbuilt. Single-Name OS must render these as unavailable or provisional until the owner earns them; it must not recreate them. |
| Earnings Intelligence E0–E2 first arc | `PROVEN_LIVE` | Canonical event-workspace slice for AAPL is live through existing Terminal + dossier projections. E3+ remains separately unstarted. |
| Company Intelligence v2 full receipt/search/peer/slides vision | `SPEC_ONLY` / `PARTIAL` | Strong experience and evidence grammar exists; many deeper lenses are not yet production implementations. |
| Capital Structure issuer identity/publication W1 | `PROVEN_LIVE` | Canonical issuer capital-twin program exists. |
| Capital Structure W2A/W2B | `PROVEN_LIVE` | Capacity/horizon path proven. |
| Capital Structure W2C/W2D | `BUILT_NOT_PROVEN` | Merged and awaiting the owner's required natural proof. W3+ issuer capital UX/state remains held. |
| China Intelligence Hub | `PROVEN_LIVE` program substrate / mixed per-lane freshness | Existing official-policy corpora, China news, A/H, southbound, per-name margin, special-situation, and narrative-divergence organs must be reused rather than rebuilt. |
| HK per-stock southbound holdings, A/H and venue-divergence substrate | `BUILT_NOT_PROVEN` for SNI-specific use | Existing China/HK collectors and hub logic contain relevant inputs; Single-Name OS has not consumed them yet. |
| ThetaData canonical options source / broad T1 cadence | `PROVEN_LIVE` | Existing options architecture records this source plane as canonical and production-proven. |
| EOD options intelligence | `BUILT_NOT_PROVEN` end-to-end | Producer exists; downstream acceptance is incomplete. |
| Intraday options/live-flow product dependency | `PARTIAL` | Useful source and campaign evidence exists, but Options Alpha itself is being recovered and must remain its own owner. |
| qledger / claim accountability / prospective grading apparatus | `PROVEN_LIVE` house apparatus | Reuse for single-name forecasts and registered research; no SNI-specific evaluation database. |
| Single-name issuer+instrument twin view | `NOT_BUILT` | No canonical composite object or premium workspace currently fuses all of the above. |
| Single-name state-conditioned response model | `NOT_BUILT` | New research frontier. |
| Single-name multi-horizon calibrated forecast book | `NOT_BUILT` | New research frontier; must reuse qledger/Evaluation OS for evidence. |
| Single-name product authority to rank/size/gate/trade | `REJECTED_BY_DESIGN` for the initial program | The first arcs are research/display/context only. Any future authority is a separately preregistered promotion. |

### 2.1 Material disagreements and open adjacent carriers

- Stock Identity has an open draft W3→final recovery carrier (#6529). This program must not absorb its W3 ruler, W4 epoch, W5 fit, W6 SIF, or W7 prospective responsibilities.
- Live Entry Radar has its own completion program and owns prospective entry-expert event truth. SNI may consume accepted outputs; it does not build a second event feed.
- Options Alpha has a current architecture/recovery program. SNI may consume options observations, candidates, calibrated signals, and explicit abstentions according to their authority; it does not manufacture browser-side alpha semantics.
- Capital Structure W2 is not fully closed despite merged repairs. SNI must preserve owner state such as `BUILT_NOT_PROVEN` rather than painting the combined page green.
- Company Intelligence E2 is real, while much of the later v2 experience is still spec/partial. SNI should reuse what is live and show typed absence for what is not.

---

## 3. Core model: issuer twin + instrument twin + belief state

A public company and a traded security are related but not identical objects. The product therefore has two primary twins and a separately governed belief layer.

```text
                           SINGLE-NAME INTELLIGENCE OS
                                      │
               ┌──────────────────────┴──────────────────────┐
               │                                             │
          ISSUER TWIN                                  INSTRUMENT TWIN
       economic/company truth                          traded-security truth
               │                                             │
 business model / segments                         listing / venue / currency
 KPIs / financial history                          price-path fingerprint
 earnings / guidance                               identity epochs
 management / commitments                          intraday microstructure
 capital allocation                                options / volatility
 products / customers / suppliers                  liquidity / positioning
 regulation / policy                               factor sensitivities
 relationships / themes                            event reaction history
               │                                             │
               └──────────────────────┬──────────────────────┘
                                      │
                            CURRENT BELIEF STATE
                                      │
          facts → state → expectations → scenarios → forecast records
                                      │
                             qledger / Evaluation OS
                                      │
                         calibration / learning / abstain
```

### 3.1 Issuer twin

The issuer twin answers **what the business is and how it is changing**.

Required domains:

- legal issuer identity and corporate lineage;
- business segments, products, geographies, customer types, and economic drivers;
- financial statements and company-specific KPI histories;
- earnings, guidance, management narrative, analyst challenge, and management commitments;
- capital structure, issuance capacity, buybacks, dividends, SBC, debt, convertibles, and disclosed financing needs;
- customers, suppliers, partners, competitors, themes, and reporting-wave relationships;
- regulatory, litigation, policy, and jurisdiction-specific events;
- consensus/expectation snapshots where licensed and basis-safe;
- valuation drivers and scenario assumptions;
- evidence provenance, corrections, rights, staleness, and typed absence.

### 3.2 Instrument twin

The instrument twin answers **how this exact traded security behaves**.

Required domains:

- listing, venue, currency, share class, ADR ratio or conversion mechanics, and corporate-action handling;
- total-return-adjusted historical path and current price state;
- Stock Identity fingerprint and identity-drift/epoch output when available;
- drawdown grammar, recovery velocity, trend persistence, mean reversion, cyclicality, gap behavior, volatility clustering, liquidity, and factor dependence;
- intraday session grammar, including open/auction, morning, midday, afternoon/close behavior where lawful high-resolution history exists;
- current microstructure: spread, depth, order/trade imbalance and liquidity state only to the semantic precision the source supports;
- options term structure, skew, IV, OI, Greeks/exposure, campaign/live-flow context and later settled-OI updates according to the existing options owners;
- short activity and ownership/positioning inputs with their native clocks and semantics;
- listing-specific event-response history;
- dynamic factor exposures and residual/idiosyncratic move decomposition.

### 3.3 Belief state

The belief layer is not one score. It is a versioned set of separately testable views:

1. `business_trajectory` — improving / stable / weakening only when grounded in specific facts and deterministic or separately governed methodology;
2. `fundamental_expectation_gap` — evidence versus known expectations, with basis and source clocks;
3. `market_incorporation_state` — whether observed pricing appears low/normal/high relative to a frozen expected-response model, never a causal certainty claim;
4. `technical_path_state` — current measured path condition and Stock Identity context;
5. `positioning_fragility_state` — options/ownership/short/liquidity context without laundering them into directional intent;
6. `valuation_state` — scenario distributions and historical/peer context, not a single fair-value oracle;
7. `forecast_book` — separately registered probability/distribution outputs by target and horizon;
8. `unknowns_and_abstentions` — missing source, inadequate N, unstable regime, unresolved identity, stale input, unlicensed data, or uncalibrated model.

No single scalar is allowed to flatten these into `BABA = 83/100` or equivalent.

---

## 4. The full Stock DNA model

"DNA" is used here as a product metaphor for persistent and slowly changing measured structure. It must not become a hand-authored personality label.

### 4.1 Business DNA

Track:

- segment revenue, margins, profit pools and capital intensity;
- KPI trees specific to the issuer;
- geography/customer/product mix;
- unit economics where reported;
- recurring versus cyclical revenue components;
- capex, R&D, sales/marketing, headcount and efficiency where relevant;
- cash conversion, FCF, ROIC and reinvestment;
- balance-sheet resilience and financing dependencies;
- capital allocation behavior;
- management targets and commitment history;
- estimate dispersion and estimate revisions where licensed;
- historical sensitivity of price and valuation to each major business driver.

### 4.2 Earnings DNA

Track every legitimate event as a longitudinal object:

- reported facts versus prior period, prior guide and decision-time consensus on matched basis;
- surprise by KPI, not only EPS/revenue;
- guidance changes and assumptions;
- narrative additions, removals and reframing;
- analyst questions, repeated pressure, follow-ups, and unanswered areas as the canonical Earnings owner matures them;
- management commitments and later resolution;
- implied move versus realized move;
- opening gap, intraday reaction, day 1/5/21/63 path;
- post-event drift and reversal conditional on surprise, positioning, path state and market regime;
- cross-company read-through and reporting-wave effects when the canonical graph supports them.

### 4.3 Market-path DNA

Consume and extend Stock Identity lawfully:

- trend grammar;
- drawdown distribution and time-under-water;
- recovery/rebound geometry;
- mean-reversion half-life and oscillator-extreme dwell;
- realized-vol and vol-of-vol structure;
- gap/event response;
- moving-average relationships;
- cyclicality/swing-period behavior;
- factor/idio share;
- liquidity and size;
- real identity epochs and drift when W4 lands.

SNI may add new descriptive coordinates only when they are genuinely not owned by Stock Identity, and any predictive use must be separately registered. It may never pick indicators for a ticker by outcome audition.

### 4.4 Intraday DNA

For Tier-A reference names, learn the session process rather than merely drawing 1-minute charts:

- opening auction/opening gap behavior;
- first 5/15/30/60-minute range and volume realization;
- VWAP relation and recapture/failure behavior;
- session volume curve and abnormal participation;
- realized intraday variance by session segment;
- high/low formation time distribution;
- gap fill / gap continuation conditional on event and overnight information;
- liquidity/spread/depth state by time of day;
- close/auction behavior;
- venue-specific overnight information transfer, e.g. BABA U.S. close → 9988 Hong Kong open.

These measurements are descriptive until an OOS/prospective experiment earns predictive use.

### 4.5 Positioning and fragility DNA

Keep native semantics separate:

- options IV level, skew, term structure, expected move, OI and Greeks/exposure;
- intraday options campaign/live-flow observations, including measured NBBO aggression only when covered;
- settled OI confirmation after the fact;
- short interest, short-sale turnover/volume and securities-borrow observations only at their native clocks;
- 13F/ownership/CCASS/southbound holdings as position snapshots, not live flow unless the source actually measures flow;
- insider transactions, buybacks, issuance, SBC and other supply/demand changes;
- liquidity depth and crowding proxies.

No open interest, short volume, 13F, CCASS or southbound series is allowed to claim bullish/bearish investor intent merely because it changed.

### 4.6 Narrative and information DNA

The system tracks what the information environment is doing to the company-specific research state:

- first appearance / acceleration / fading / disappearance of key topics;
- management versus analyst versus media versus regulatory narratives kept separate;
- onshore Chinese versus offshore English narrative divergence for China names where existing source owners support it;
- primary-source facts versus inference versus outside commentary;
- source novelty, duplication and correction state;
- how similar categories of information historically affected this security in comparable states.

Sentiment is a descriptor, not a forecast authority.

### 4.7 Relationship DNA

Consume canonical graph/ontology owners for:

- customers and suppliers;
- products and end markets;
- partners and competitors;
- themes/subthemes;
- index/ETF membership and peer groups;
- reporting waves;
- capital/ownership relationships;
- country, policy and commodity exposures.

Relationships must preserve evidence type, strength/precision, first-known/last-known clocks, and corrections. SNI creates no second relationship graph.

---

## 5. New intelligence frontier A — normal versus abnormal behavior

A core capability should answer:

> Is today's move normal for this instrument given the market, factors, volatility, known event state and its own historical behavior — or is there a meaningful idiosyncratic residual?

The initial research architecture is:

```text
observed return / volatility / volume response
        -
expected response from a frozen PIT conditional factor model
        =
residual / abnormal instrument response
```

### 5.1 Candidate method families

The research program should compare, not assume, at least:

1. transparent rolling factor regression baseline;
2. characteristic-conditioned factor-loadings model in the IPCA family;
3. nonlinear conditional factor challenger with capacity constraints and name-disjoint/time-disjoint evaluation;
4. simple sector/index/market benchmarks.

Academic work such as Kelly-Pruitt-Su IPCA and later semiparametric conditional factor models supports the idea that observable characteristics can condition time-varying factor loadings, while Gu-Kelly-Xiu supports testing nonlinear interactions under rigorous OOS discipline. These are methodological inspirations, not evidence that any candidate works for Mastermind's targets.

### 5.2 Output

The product may surface:

- expected move from common exposures;
- observed move;
- residual move;
- residual percentile versus the instrument's own PIT history;
- which factor contributions dominated;
- current model coverage/uncertainty;
- `ABSTAIN` when the factor model is unstable, inputs are stale, or the current identity epoch is not estimable.

It may not label the residual "smart money", "information edge", or company-news impact without additional evidence.

---

## 6. New intelligence frontier B — stock-specific response surfaces

The deepest version of "know the stock" is to learn how its response changes conditional on state and stimulus.

Example questions for Alibaba:

- What happens to 9988 when CNH weakens sharply?
- How does it behave after a strong BABA U.S. session before the Hong Kong open?
- How has it reacted to China internet policy events across identity eras?
- How does cloud-growth evidence transmit into price when commerce margins are weakening versus improving?
- How does a large equity issuance affect path, valuation and volatility conditional on stated use of proceeds?
- How does an earnings beat behave when guidance, positioning and pre-event extension disagree?

### 6.1 Method law

A response surface may not become a hidden ticker-specific outcome optimizer.

Use a hierarchy:

```text
global event/mechanism prior
    → behavioral/economic neighborhood prior
        → issuer/instrument structural conditioning
            → bounded per-name residual shrinkage
                → current identity epoch / market state
                    → conditional outcome distribution
```

The own-name term is shrinkage with printed N/effective N, never best-of-grid selection.

### 6.2 Event families

Each event family has its own target and clock. Initial families include:

- earnings/result events;
- guidance/estimate revisions;
- capital issuance/buyback events;
- material regulatory/policy events;
- major product/capex announcements;
- supply-chain/customer read-through events;
- listing/index/corporate-action events;
- major technical/path dislocations;
- options-positioning transitions where the options owner has a lawful event definition.

The system does not pool them into one "news reaction" class.

### 6.3 Required controls

Every response study must declare:

- event identity and first-known timestamp;
- instrument/listing target;
- identity epoch and market regime knowable at decision time;
- outcome horizon before observation;
- common-factor benchmark / matched control;
- overlap and calendar-cluster treatment;
- sample size and effective sample size;
- source/right/correction state;
- pre-registered primary question and sensitivity budget;
- prospective shadow requirement before any product authority.

---

## 7. New intelligence frontier C — evidence versus incorporation

A company's fundamentals and its stock price are different layers.

The product should explicitly model:

```text
new evidence
→ economic/fundamental change
→ expectation/surprise change
→ expected response distribution
→ observed market response
→ residual incorporation state
```

This enables answers such as:

- "The business evidence improved, but the stock already moved more than comparable historical responses."
- "The earnings surprise was ordinary, but the residual reaction was highly unusual."
- "The company issued equity, but the observed selloff was smaller than the historical response distribution after accounting for market and capital raised."
- "The price has not yet moved much despite a material expectation change; this is a research gap, not automatically a buy signal."

### 7.1 Incorporation state is descriptive first

Initial labels may be `less_than_expected`, `within_expected`, `more_than_expected`, or `unestimable` only when derived from a frozen response distribution with explicit uncertainty. No front-end phrase may imply mispricing or alpha until separately promoted.

### 7.2 Attention and delayed processing are research variables

Academic evidence around post-earnings announcement drift and investor attention supports testing delayed incorporation as a real hypothesis, not assuming it. SNI should therefore preserve macro-news days, reporting-time context, retail/positioning context and information density as possible conditioning variables under preregistration.

---

## 8. New intelligence frontier D — multi-horizon probabilistic forecasting

SNI must not pretend a single target price is the forecasting problem.

Maintain separate forecast families:

### 8.1 Trading/path targets

Examples:

- 1-session, 3-session, 5-session and 21-session return distribution;
- expected range / realized volatility distribution;
- drawdown/MFE/MAE distribution;
- probability of touching explicitly predeclared levels;
- probability of path-state transition;
- gap continuation versus fill when relevant.

### 8.2 Catalyst/event targets

Examples:

- event reaction relative to implied move;
- post-event drift/reversal distribution;
- KPI or guidance surprise where a lawful expectation baseline exists;
- cross-listing response sequence;
- read-through response for linked names.

### 8.3 Investment/fundamental targets

Examples:

- segment/KPI distributions over 1–4 quarters;
- margin / FCF / capex scenarios;
- business-thesis state transitions;
- valuation distributions conditional on fundamental scenarios;
- 3/6/12-month return distributions as a separate family from short-term path forecasts.

### 8.4 Calibration and uncertainty

Every forecast stores through the existing prospective apparatus:

- target definition;
- horizon;
- known-at timestamp;
- feature/source generation refs;
- model/spec hash;
- probability distribution or interval;
- baseline/challenger identity;
- authority block;
- maturity/outcome state;
- later grade.

The research program should evaluate adaptive uncertainty methods, including time-series-aware conformal challengers, because standard exchangeable conformal assumptions are not valid for dependent, nonstationary market time series. A conformal method may be used only after empirical coverage is prospectively measured by horizon/regime; no unconditional "95% guaranteed" marketing language.

### 8.5 Forecast hierarchy

Never use the same model merely because it can output every horizon. Candidate architecture is a mixture of horizon-specific experts with explicit fallback to simpler baselines. Complexity must earn narrower calibrated errors or better proper-scoring-rule performance out of sample.

---

## 9. Forecast memory: Mastermind remembers what it thought

A world-class single-name system must preserve intellectual accountability.

The product should offer a **Time Machine / Forecast Ledger** view that reconstructs exactly what Mastermind knew and believed at a past timestamp.

It must show:

- the published facts and missing data at that time;
- the then-current issuer/instrument state;
- the then-current model/spec version;
- every active forecast, probability distribution and scenario;
- conditions that would have changed the read;
- later observations and corrections separately;
- outcome grades after the horizon matured;
- calibration by target, horizon, name, identity epoch and broader cohort;
- where the system systematically over/underpredicted and what later model revision addressed it.

No forecast may be silently recomputed under today's model and presented as yesterday's belief.

This uses qledger/Evaluation OS/claim-accountability owners. SNI may add a projection and registration family; it does not create a second forecast ledger.

---

## 10. Reference organism 1 — Alibaba issuer + 9988.HK + BABA

Alibaba is intentionally difficult and therefore a superior first reference organism.

### 10.1 Identity requirements

The issuer twin must represent Alibaba Group once while preserving each instrument separately.

Official Alibaba investor materials establish:

- NYSE `BABA` ADSs;
- each ADS represents eight ordinary shares;
- HK `9988` HKD counter and `89988` RMB counter;
- U.S. ADSs and Hong Kong ordinary shares are fungible in both directions;
- Hong Kong became a dual-primary listing on 2024-08-28.

SNI must therefore distinguish:

```text
Alibaba Group issuer
  ├─ 9988.HK ordinary share / HKD counter
  ├─ 89988.HK ordinary share / RMB counter
  └─ BABA NYSE ADS / 8 ordinary shares per ADS
```

The issuer's fundamentals belong to Alibaba Group. Price path, microstructure, options, session clock and some corporate-action mechanics belong to the specific instrument.

### 10.2 Cross-listing state

The product should compute a clearly labeled diagnostic such as:

```text
BABA-implied ordinary-share HKD price
  = BABA_USD × USDHKD / 8

9988 cross-listing basis
  = 9988_HKD / implied_ordinary_share_HKD - 1
```

This is a diagnostic after respecting timestamps, market hours, fees, conversion frictions and stale-market state. It is not an automatic arbitrage signal.

### 10.3 Alibaba source profile

Priority source families:

1. Alibaba IR / HKEX issuer announcements / NYSE-SEC where applicable;
2. canonical earnings/company-event owner;
3. canonical China official-policy and filing/news owners;
4. HKEX and house HK market data;
5. BABA U.S. consolidated/house market data;
6. house options source for BABA and HK stock-options source if/when licensed/qualified for 9988;
7. southbound holdings / CCASS / short activity where source rights and clocks qualify;
8. canonical capital-structure owner;
9. canonical relationship/theme graph;
10. licensed consensus, channel checks and specialist research only as separate source families with rights manifests.

### 10.4 Capital events

The system must be able to ingest an event such as Alibaba's 2026-08-26 HK$80B placement, update the issuer capital state through the canonical capital owner, preserve the use-of-proceeds evidence, recompute relevant share-count/valuation denominators only when their canonical owner publishes them, and then study each instrument's response without interpreting dilution or AI-capex investment as direction by fiat.

---

## 11. Reference organism 2 — Tencent 0700.HK

Tencent provides a complementary Hong Kong mega-cap organism with different beta, business mix, capital behavior and listing structure.

Required company-specific ontology includes, where reported and source-safe:

- gaming revenue and geography/platform splits;
- advertising/marketing-services drivers;
- fintech/business services and cloud exposure;
- gross/operating margin progression;
- AI-related capex/compute/product developments;
- major investee/portfolio and ecosystem changes where material and source-grounded;
- buybacks, awards/options, debt issuance and capital allocation;
- China regulation/policy and platform-economy exposure;
- relationships and read-through into gaming, advertising, cloud/AI and China internet groups.

Tencent's official investor page currently shows 2026 Q2 results dated 2026-08-12 and repeated August next-day disclosure returns for share changes/share buybacks. That makes capital allocation a first-class live state rather than an annual footnote.

Alibaba and Tencent should also be paired in a **HK Mega-Cap Pair View** that measures, never assumes:

- rolling beta and residual correlation;
- lead/lag by session and event type;
- relative strength and residual divergence;
- factor contribution differences;
- HSI/HS Tech contribution and sensitivity;
- southbound/ownership-context differences;
- capital-allocation divergence;
- policy/news co-exposure versus issuer-specific residuals.

The pair is a diagnostic sensor for Hong Kong/China risk appetite only to the degree empirical measurement supports it.

---

## 12. Hong Kong Tier-A data architecture

Hong Kong should be a first-class market, not a U.S. template with renamed tickers.

### 12.1 Existing house substrate to reuse

The China Intelligence estate already contains or documents:

- A/H pair data;
- southbound Connect data;
- per-stock southbound holdings;
- PIT per-name margin detail;
- A/H premium and broader China-flow context;
- official policy corpora from State Council/PBoC/NDRC/CSRC/People's Daily;
- China news and onshore-Chinese versus offshore-English narrative divergence;
- special situations and filing-related surfaces;
- qledger registration/promotion discipline.

SNI consumes these; it does not create `china_single_name_event.v1` or a second China bus.

### 12.2 High-fidelity HKEX upgrade path

HKEX's current source offerings make a much deeper tier technically possible:

- OMD-C securities real-time market data;
- historical full-book securities tick-by-tick orders/trades through HKEX Data Marketplace;
- CCASS shareholding data through HKEX Data Marketplace;
- OMD-D derivatives feeds including market-by-order FullTick;
- historical full-book stock-options data;
- designated-short-selling security lists and short-selling statistics;
- issuer information feeds and announcements;
- Stock Connect market data.

The program should create a **source/rights/economics qualification docket** before procurement. It should compare existing house coverage against HKEX L2/FullTick, historical full book, CCASS and derivatives products, estimate storage/compute/rights requirements, and identify the minimum package that materially improves Alibaba/Tencent intelligence.

No purchase or legal/rights decision is authorized by this design.

### 12.3 Hong Kong session grammar

The instrument twin must model Hong Kong-specific time structure, including applicable auction/session boundaries and lunch break, rather than resampling U.S. intraday assumptions.

Cross-venue features must tag whether the other venue was open, closed, stale, or post-event at the comparison timestamp.

---

## 13. U.S. stress set — NVDA, MSFT, TSLA

After Alibaba/Tencent define the architecture, the first U.S. stress set deliberately spans radically different operating and trading grammars.

### 13.1 NVDA

Company-specific monitoring should emphasize:

- data-center segment demand;
- hyperscaler/customer capex and ordering signals;
- product/platform transitions;
- supply and packaging constraints;
- gross margin and mix;
- competitive accelerators and ecosystem adoption;
- export controls/geopolitical restrictions;
- semiconductor supply-chain relationships;
- unusually important options/volatility/event-response state.

### 13.2 MSFT

Emphasize:

- Azure/cloud growth and AI contribution;
- bookings/RPO and enterprise demand;
- capex and data-center capacity;
- Copilot/AI monetization;
- Office/Dynamics/Windows/gaming mix as relevant;
- margin/capex/FCF trade-offs;
- hyperscaler reporting-wave read-through;
- steadier market-path grammar as a counterexample to NVDA/TSLA.

### 13.3 TSLA

Emphasize:

- deliveries, production and pricing;
- automotive gross margin and incentives;
- energy/storage economics;
- autonomy/robotaxi milestones with fact-versus-claim separation;
- regulatory and litigation state;
- capex and product roadmap;
- high retail/news sensitivity;
- options reflexivity and volatility;
- unusually strong event/narrative regime dependence.

The goal is not to encode three handcrafted strategies. It is to prove the shared twin/compiler can support radically different source/KPI/event packs while keeping the market-behavior model empirical.

---

## 14. Mag 7 extension packs

After the stress set, extend to AAPL, AMZN, META and Alphabet with company-specific KPI/event packs.

Examples of differentiated driver families:

- AAPL: hardware unit/mix where source-safe, services, installed base/proxy metrics, China exposure, product cycle, gross margin, supplier relations;
- AMZN: AWS, retail sales/margins, advertising, fulfillment/capex, logistics, Prime and consumer demand;
- META: ad pricing/impressions, engagement, Reels/AI monetization, capex, Reality Labs, regulation;
- Alphabet: Search/YouTube advertising, Cloud, AI capex/monetization, TAC, traffic/product shifts, regulatory/antitrust.

Every pack is an ontology/source configuration, not a private ticker model key.

---

## 15. Product experience architecture

The deep product should live primarily in Terminal, with a concise public/private dossier projection in Macro.

### 15.1 Five-second first viewport

A reference layout:

```text
ALIBABA · 9988.HK                     SINGLE-NAME INTELLIGENCE
Issuer: Alibaba Group                 Linked instruments: BABA · 89988

WHAT CHANGED SINCE THE LAST MEANINGFUL STATE
[material facts / source-backed deltas]

CURRENT STATE
Business        …
Expectations    …
Market path     …
Positioning     …
Capital         …
Valuation       …
Evidence health …

NORMAL VS ABNORMAL
common-factor expected move | observed | residual | model coverage

WHAT MAY HAPPEN NEXT
1 session   distribution / range / abstain
1 week      distribution / catalysts / abstain
1 month     distribution / state transitions / abstain
3–12 months fundamental + valuation scenarios / abstain

WHAT WOULD CHANGE THE READ
[observable, predeclared conditions]

NEXT IMPORTANT EVENTS
[event clock + source confidence]
```

No panel renders a directional number when its owner is missing, stale, unlicensed or uncalibrated. The missing state itself is a finished product state.

### 15.2 Deep lenses

1. **Overview** — current state, what changed, forecasts, evidence health.
2. **DNA** — persistent path/business characteristics, identity epochs, historical distributions.
3. **Live Tape** — intraday state, normal session curve, abnormal volume/volatility/liquidity, event markers.
4. **Options & Positioning** — options structure, live campaigns, settled updates, short/ownership context with native clocks.
5. **Business** — KPI tree, segments, drivers, operating trends.
6. **Earnings** — event workspace, guidance, narrative, Q&A, commitments, reaction history.
7. **Capital** — issuance capacity, buybacks, debt, SBC, share-count/capital events.
8. **Events & News** — source-grounded event timeline, Chinese/English source lenses where applicable.
9. **Relationships** — customers, suppliers, competitors, themes, reporting waves, read-through.
10. **Valuation & Expectations** — consensus/estimates where licensed, scenario distributions, expectation changes.
11. **Response Lab** — state-conditioned historical response surfaces, sample/effective N, controls, abstentions.
12. **Forecast Lab** — active forecasts, baselines/challengers, calibration and proper scores.
13. **Time Machine / Sources** — exact past belief reconstruction, corrections, receipts, typed absences.

### 15.3 Pair/cluster modes

The same workspace may render a pair/cluster composition without creating another semantic owner:

- Alibaba 9988 vs BABA cross-listing;
- Alibaba vs Tencent HK mega-cap pair;
- Mag 7 comparison;
- company vs economic/behavioral neighbors.

Pair mode compares canonical views; it does not merge identities.

---

## 16. Evidence and failure-state law

Borrow the strongest Company Intelligence grammar: every material displayed claim must resolve to either a source/derived evidence path or a named absence.

Required failure states include:

- source missing;
- source not licensed;
- source rights block;
- stale source/view;
- corrected/superseded source;
- listing/issuer identity conflict;
- unsupported currency/unit/basis conversion;
- cross-listing stale-market mismatch;
- insufficient history;
- insufficient distinct events/calendar clusters;
- identity epoch unstable or not available;
- model underpowered;
- model uncalibrated;
- forecast horizon pending;
- source owner `BUILT_NOT_PROVEN`;
- source owner unavailable;
- conflicting canonical sources;
- structurally not applicable.

Missing is never zero. Stale is never current. Context is never signal. Uncalibrated is never 50/50 by default.

---

## 17. Authority architecture

SNI introduces no new trading authority.

### 17.1 Stage ladder

```text
observation
→ descriptive context
→ registered research hypothesis
→ calibrated forecast/context
→ separately promoted signal family
→ existing Prophet / Issue Desk / portfolio authority if independently licensed
```

Each artifact carries explicit authority axes.

### 17.2 Prohibited shortcuts

- no ticker-specific outcome argmax;
- no per-name best-indicator menu;
- no hidden sector/archetype routing key;
- no LLM-originated probability, rank, target or score;
- no options-flow semantic laundering;
- no "smart money" claims from holdings/flow proxies without direct evidence;
- no historical forecast reconstruction after outcomes;
- no same-sample feature selection and grading;
- no result-driven rewrite of event families, horizons or response definitions;
- no broad product-completeness claim from green CI.

---

## 18. Statistical/research architecture

### 18.1 Training/evaluation partitions

Different research families require distinct partitions, but all obey:

- point-in-time features and source availability;
- name-disjoint evaluation where the question is cross-sectional generalization;
- time-disjoint/forward evaluation where the question is future performance;
- identity-epoch known-at treatment;
- calendar/event overlap controls;
- dead/delisted/inactive instrument controls where applicable;
- explicit trial/look budget;
- frozen baselines;
- proper scoring rules for probability/distribution forecasts;
- calibration plots and coverage, not accuracy alone.

### 18.2 Hierarchical partial pooling

Small-N per-name data is a central constraint. The preferred family of methods borrows strength in a declared hierarchy and exposes the borrow weights/effective N.

No single-name model is allowed to use hundreds of ticker-specific degrees of freedom because the ticker has a long chart.

### 18.3 Baseline ladder

Every advanced model competes against simpler baselines such as:

- unconditional name history;
- market/sector factor baseline;
- simple rolling linear model;
- global cross-sectional model;
- existing canonical signal/state when applicable;
- implied options expectation where appropriate.

A complex model that does not beat the relevant simple baseline at the registered metric remains research-only or is killed.

### 18.4 Forecast metrics

Depending on target:

- log score / negative log likelihood;
- Brier score for binary event outcomes;
- CRPS or equivalent for distributions;
- interval coverage and width;
- calibration slope/intercept / reliability bins;
- MAE/RMSE only where a point statistic is meaningful;
- realized utility only as a later, separately governed question.

Trading P&L is not the only nor the default research ruler.

---

## 19. Data/source architecture and moat ladder

Coverage should be tiered by economic importance and by what the source can actually support.

### Tier A — Reference organisms

Alibaba/Tencent + Mag 7 eventually receive the deepest lawful stack:

- primary issuer documents;
- high-quality structured company/event corpus;
- full canonical market data available to the house;
- detailed options/microstructure where licensed;
- complete company-specific KPI ontology;
- relationship/theme graph;
- capital/ownership state;
- region-specific data (HK/China where relevant);
- richer alternative data only after rights/source/validation review;
- continuous forecast/response evaluation.

### Tier B — Strategic large caps / Nasdaq 100 / Dow

Same compiler and schemas, fewer expensive sources initially. Escalate high-value names/events dynamically.

### Tier C — S&P 500

Broad canonical truth, business/event intelligence, Stock Identity, core options where covered, and standard forecasting. Expensive microstructure/alternative-data tiers can be selective until economics prove value.

### 19.1 Licensed research upgrades

Competitive research shows useful potential complements:

- Quartr: structured first-party events, transcripts, filings/reports and slides across global markets;
- S&P Capital IQ Pro / Visible Alpha: deep consensus line items and point-in-time estimates;
- AlphaSense/Tegus: broker research, expert transcripts, channel checks and AI research workflows;
- LSEG / FactSet class products: deep estimates, ownership, value-chain and market/derivatives data;
- HKEX Data Marketplace: first-party full-book and CCASS data.

These are **source candidates**, not automatic procurement instructions. Each enters a rights/economics/coverage/uniqueness evaluation against existing Mastermind data before spend.

---

## 20. Competitive benchmark and the intended leap

No single benchmark should define the product. The design intentionally combines jobs currently split across institutional systems.

### 20.1 Benchmark primitives worth meeting or exceeding for the controlled universe

**Primary-source research:** Quartr / AlphaSense class event, transcript, filing, slide and evidence workflow.

**Financial/KPI/consensus depth:** Capital IQ / Visible Alpha / LSEG / FactSet class structured financial and estimate analysis.

**Relationship intelligence:** FactSet Revere / Bloomberg Supply Chain / Capital IQ class customer-supplier-peer exposure, but with Mastermind's own lawful graph and evidence.

**Market workstation:** Bloomberg/LSEG/Terminal class live quote, chart, correlation, derivatives and monitoring workflow.

**Options intelligence:** institutional options surface + Mastermind's own canonical ThetaData/live-flow/campaign/evaluation estate.

**AI research:** AlphaSense-style multi-step cited research and monitoring, but grounded on Mastermind's canonical object graph and forecast memory rather than a one-off narrative answer.

### 20.2 The intended Mastermind differentiation

The leap is the **intersection**:

```text
primary-source company truth
+ complete longitudinal event memory
+ issuer capital twin
+ relationship/theme graph
+ instrument-specific behavioral identity
+ venue/session microstructure
+ options/positioning state
+ dynamic factor / residual decomposition
+ state-conditioned response surfaces
+ evidence-versus-incorporation analysis
+ multi-horizon calibrated forecasts
+ immutable forecast memory
+ prospective self-grading
+ one premium single-name experience
```

The defensible moat is the accumulation of correction-safe, point-in-time **belief and response history per security**, not a static library of indicators or summaries.

---

## 21. Program decomposition

This architecture is too broad for one implementation plan or one worker. It decomposes into independently reviewable subprograms/waves.

### SNI-0 — Program architecture and owner map

**Mission:** this document plus current capability/source/ownership freeze.  
**Output:** reviewed architecture only.  
**No code.**

### SNI-1 — Reference Twin Contract + Alibaba/Tencent Source Qualification

**Mission:** define the smallest canonical read model that composes issuer + instrument state without duplicating owners, and complete an exact source/rights/clock/coverage matrix for Alibaba/9988/BABA and Tencent/0700.

Must include:

- issuer/security/listing identity contract;
- unit/currency/ADR conversion law;
- company-specific KPI source packs;
- HK/China source map;
- canonical owner field map;
- rights/licensing gaps;
- freshness/correction/null semantics;
- exact typed-absence behavior;
- no predictive model yet.

### SNI-2 — Reference Experience Composition

**Mission:** design and build the premium Alibaba/Tencent workspace using only accepted/available owner outputs, with missing advanced intelligence shown honestly.

The user must be able to understand current company state, instrument state, what changed, event timeline, capital, options/positioning context and evidence health before advanced forecasting exists.

### SNI-3 — Residual / Normal-vs-Abnormal Research

**Mission:** preregister and evaluate the conditional factor/residual architecture.  
**No product alpha claim until prospective/OOS gates pass.**

### SNI-4 — Response Surface Lab

**Mission:** build event/state-conditioned hierarchical response research with honest N, controls, shrinkage and abstention.

### SNI-5 — Forecast Book + Evaluation Bridge

**Mission:** register multi-horizon forecast families through qledger/Evaluation OS, create Time Machine projections, baseline/challenger grading, calibration and pending/matured states.

### SNI-6 — U.S. Stress Set

**Mission:** prove NVDA/MSFT/TSLA can use the same compiler with different KPI/source packs and no per-ticker strategy hard-coding.

### SNI-7 — Complete Mag 7

**Mission:** AAPL/AMZN/META/Alphabet extension packs and pair/group compositions.

### SNI-8 — Scale Compiler

**Mission:** prove that adding a new security is mostly identity + source profile + KPI/event ontology + coverage tier, not new application code.

Expansion beyond the reference cohort is held until the reference organisms meet the product/research acceptance gates.

---

## 22. High-effort / Pro research dockets

The architecture requires several research questions where deeper reasoning and external primary-source work are more valuable than immediate coding. These should be treated as dedicated high-effort/Pro research passes before the relevant implementation wave.

### PRO-A — Statistical Superstructure

Decide and preregister:

- conditional factor/residual baseline family;
- hierarchical response-surface estimators;
- event overlap/effective-N law;
- state/epoch conditioning;
- uncertainty and adaptive-conformal challengers;
- distribution forecast metrics;
- leakage and model-capacity controls;
- forecast revision/versioning law.

Deliver a method docket with explicit baselines, kill criteria and prospective gates — not code first.

### PRO-B — HK/China Institutional Data & Rights

Produce an exact matrix for:

- HKEX OMD-C L1/L2/FullTick;
- historical full-book securities data;
- OMD-D stock options and historical full book;
- CCASS shareholding;
- short-selling data;
- Stock Connect and house southbound holdings;
- issuer-information feeds;
- Alibaba/Tencent IR/HKEX source rights;
- China official/news/filing sources already in-house;
- storage, delivery, latency, licensing and redistribution constraints.

The output must identify what we already have, what materially improves the product, what is redundant, and what requires Chairman procurement/legal approval.

### PRO-C — Alibaba/Tencent Economic Ontology

Build a source-grounded KPI/driver/relationship/event map detailed enough to support a professional analyst's model:

- business segments and KPI definitions;
- historical definition changes;
- management targets;
- key economic sensitivities;
- material regulatory/policy families;
- capital-allocation state;
- relevant peers/customers/suppliers/themes;
- event categories and expected research questions;
- listing-specific mechanics.

No stock-direction predictions in this pass.

### PRO-D — Mag 7 Economic Ontology

Same standard for NVDA, MSFT, TSLA, then AAPL/AMZN/META/Alphabet. The goal is to discover the reusable compiler vocabulary and the genuinely company-specific extensions.

### PRO-E — Institutional Product Benchmark

Maintain a capability ledger against Bloomberg, LSEG, Capital IQ/Visible Alpha, FactSet-class systems, AlphaSense/Tegus, Quartr, institutional options products and relevant modern AI research tools.

Benchmark **jobs and interactions**, not branding. For each capability classify:

- competitor job;
- Mastermind current state;
- copy/upgrade/reject ruling;
- source/rights implication;
- product value;
- machine/research value;
- whether it belongs in SNI or an existing owner.

This is a living research input, not a permanent feature checklist.

---

## 23. Prototype acceptance gates

The first Alibaba/Tencent reference release is not accepted because many cards exist.

### 23.1 Truth

- correct issuer versus instrument identity;
- correct currency/unit/share-class/ADS handling;
- source receipts or typed absence for material facts;
- correction-safe event lineage;
- explicit source freshness and rights state;
- no unsupported cross-listing arithmetic across stale/asynchronous timestamps.

### 23.2 Intelligence

- company-specific business/KPI model is useful, not generic fundamentals;
- Stock Identity context is consumed without violating owner/DNR law;
- event memory joins business, capital and market reaction;
- normal-vs-abnormal decomposition has a registered baseline and OOS evidence before being promoted beyond research;
- response surfaces print honest N/effective N and abstain when unestimable;
- forecasts are versioned distributions with baseline/challenger identity and no unearned authority.

### 23.3 Product

A user can answer, without leaving the workspace:

1. What changed materially?
2. What is the current business state?
3. What is the current instrument/path state?
4. What is unusual versus this stock's normal behavior?
5. What do options/positioning/capital data say — at their actual semantic precision?
6. What are the next major events?
7. What are the plausible forward distributions/scenarios, or why are they unavailable?
8. What observable evidence would change the read?
9. What did Mastermind believe previously and how did it grade?
10. Where did each material statement come from?

### 23.4 Learning

- forecast/research registration uses existing qledger/Evaluation OS;
- prospective clock is real and immutable;
- at least simple baselines are accrued beside challengers;
- pending horizons stay visible;
- no backfill is used to manufacture a successful forward record;
- calibration and failure modes are visible to researchers.

### 23.5 Production proof

User-facing implementation requires real Alibaba/Tencent data through the real production path and browser proof at relevant desktop/tablet/mobile breakpoints, EN/ZH where the product promise requires it. Green CI alone is insufficient.

---

## 24. Scale acceptance before S&P 500 rollout

Do not broadly roll out merely because the compiler can loop over 500 symbols.

Before SNI-8 expansion, prove:

1. adding a new company mostly requires declarative identity/source/KPI/event configuration rather than new core code;
2. the system distinguishes unavailable/not-applicable/stale/unlicensed without per-name exceptions scattered through UI code;
3. compute/storage/source economics are measured by coverage tier;
4. forecasts remain centrally registered and do not spawn 500 independent model lifecycles;
5. owner services can meet freshness SLAs without duplicating their pipelines;
6. company-specific packs improve research usefulness enough to justify their maintenance burden;
7. monitoring tells us which fields/sources/models are failing per name;
8. reference-name user engagement/research utility supports expansion.

---

## 25. Explicit non-goals

The first program does not:

- promise to predict every next-day move;
- guarantee alpha;
- create autonomous trading;
- replace Prophet;
- replace Stock Identity;
- replace Earnings Intelligence or Company Intelligence;
- replace Capital Structure;
- replace China Intelligence Hub;
- replace Options Alpha or live-flow owners;
- create a new universal entity/relationship graph;
- create a new qledger/evaluation system;
- purchase enterprise datasets automatically;
- make an LLM a stock-direction oracle;
- hand-optimize one strategy per ticker;
- roll the full S&P 500 before reference organisms are excellent.

---

## 26. Open research questions that do not block the architecture

These are explicit future research dockets, not unspecified requirements:

1. Which conditional factor estimator best separates common versus idiosyncratic movement under PIT/OOS evaluation?
2. Which hierarchical estimator provides the best bias/variance tradeoff for low-N name-specific response surfaces?
3. Which uncertainty method maintains useful empirical coverage under market nonstationarity at each horizon?
4. Which HKEX paid data products add enough unique predictive/research value beyond existing house data to justify cost/rights complexity?
5. How much incremental value do company-specific ontology packs add versus a high-quality global financial ontology?
6. Which response families have sufficient independent event N to be estimable for a single name, and which must remain cohort-level?
7. Which forecast outputs improve analyst decision quality even if they never earn trade authority?
8. How should a user's own thesis/position eventually interact with SNI without contaminating the canonical market research state?

Each question receives its own preregistration or architecture decision before it can change production semantics.

---

## 27. Architecture freeze / no-rebuild boundaries

The following boundaries are frozen for the program unless a later Sol/Chairman decision explicitly supersedes them:

1. **One issuer, many instruments.** Economic truth is issuer-level; traded behavior is instrument-level.
2. **No duplicate truth planes.** Existing identity, event, earnings, capital, options, China, graph, forecast/evaluation and publication owners remain canonical.
3. **No single magic score.** Preserve separable business, market, positioning, valuation and forecast beliefs.
4. **No outcome-audition personalization.** Stock-specific intelligence comes from source/ontology customization plus measured structure/hierarchical learning, not choosing what won on the ticker's own backtest.
5. **Forecasts are immutable beliefs.** Past beliefs are reconstructed from historical records, never today's recomputation.
6. **Uncertainty is visible.** Distribution, calibration, effective N and abstention are product objects.
7. **Context does not self-promote.** Predictive or trading authority is earned separately.
8. **Reference organisms before mass rollout.** Alibaba/Tencent first, U.S. stress set next, then full Mag 7, then broader indices.
9. **Premium product in Terminal; concise projection in dossier/Macro.** Do not turn the existing dossier into a monolith.
10. **High-cost data must earn its keep.** Rights/economics/uniqueness qualification precedes procurement.

---

## 28. Exact next action after written-spec approval

Do **not** write one giant implementation plan.

The next design/plan unit is **SNI-1 — Reference Twin Contract + Alibaba/Tencent Source Qualification**.

That subproject begins with current-state revalidation at its action-time pins, then produces:

1. the canonical field/owner map for the reference read model;
2. exact Alibaba/9988/BABA and Tencent/0700 identity/source/clock matrix;
3. company-specific KPI/event ontology v0;
4. HK paid-data qualification and rights/economics docket;
5. a typed-absence/freshness/correction contract;
6. an initial real-data reference payload for product composition;
7. zero new forecasting or trading authority.

Only after SNI-1 is separately designed and approved should a bounded implementation plan be written for that subproject.

---

## 29. External research anchors used in this design

These are method/product references, not authority or proof that Mastermind already owns/licences the data.

- AlphaSense Generative Search / Company Profiles / Workflow Agents: integrated structured financials, filings, broker research, expert transcripts and cited multi-agent research; 2026 product updates add company-level workflows and monitoring.  
  https://www.alpha-sense.com/platform/generative-search/  
  https://help.alpha-sense.com/hc/en-us/articles/49460548624915-AlphaSense-Product-Updates-February-2026  
  https://help.alpha-sense.com/hc/en-us/articles/52207495181203-AlphaSense-Product-Updates-May-2026
- Quartr API: structured first-party IR events, live/historical transcripts, filings/reports and slide presentations across global markets.  
  https://quartr.com/docs/introduction
- S&P Capital IQ Pro / Visible Alpha: public-company financials and deep consensus/line-item estimate coverage.  
  https://www.spglobal.com/market-intelligence/en/solutions/products/sp-capital-iq-pro  
  https://www.spglobal.com/market-intelligence/en/solutions/products/estimates
- LSEG Workspace for equities: company overview, estimates/fundamentals/news, order-book analytics and options volatility/Greek surfaces.  
  https://www.lseg.com/en/data-analytics/products/workspace/equities
- HKEX Data Marketplace: first-party CCASS, historical full-book securities and stock-options data.  
  https://www.hkex.com.hk/Services/Market-Data-Services/Historical-Data-Services/HKEX-Data-Marketplace?sc_lang=en
- HKEX OMD-D: derivatives market-by-price and market-by-order/FullTick datafeeds.  
  https://www.hkex.com.hk/OMDD?sc_lang=en
- Alibaba investor information: BABA/9988/89988 listing and 8:1 ADS/share conversion mechanics.  
  https://www.alibabagroup.com/en-US/faqs-investor-information
- Tencent investor relations / announcements: current result and share-change/buyback disclosure flow.  
  https://www.tencent.com/investors/  
  https://www.tencent.com/investors/announcements/
- Gu, Kelly & Xiu, "Empirical Asset Pricing via Machine Learning," Review of Financial Studies 2020.  
  https://doi.org/10.1093/rfs/hhaa009
- Kelly, Pruitt & Su, "Characteristics Are Covariances," Journal of Financial Economics / NBER.  
  https://www.nber.org/papers/w24540
- Chen, Roussanov & Wang, "Semiparametric Conditional Factor Models," NBER 2023.  
  https://www.nber.org/papers/w31817
- Time-series conformal methods are a research challenger only; recent literature emphasizes dependence/nonstationarity and horizon-specific coverage rather than naïve exchangeability assumptions.  
  https://arxiv.org/abs/2601.18509  
  https://arxiv.org/abs/2410.13115

---

## 30. Self-review checklist

- No implementation is claimed by this architecture.
- No new truth/event/identity/graph/evaluation plane is introduced.
- Stock Identity's `DNR:KILL-OUTCOME-AUDITION` boundary is preserved.
- Issuer and instrument identity are separated.
- HK/US clocks, currency and listing semantics are explicit.
- Forecasts are distributions/registered beliefs, not LLM scores.
- Missing/stale/unlicensed/unproven states are first-class.
- Paid-data research is a qualification gate, not an implicit purchase.
- The program is decomposed before implementation planning.
- The next bounded design unit is SNI-1, not an all-program mega-build.
