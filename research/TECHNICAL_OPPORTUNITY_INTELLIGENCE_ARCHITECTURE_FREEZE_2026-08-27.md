# Technical Opportunity Intelligence — Architecture Freeze and Evidence Contract

**Date:** 2026-08-27  
**Authority:** Chairman-approved Sol architecture session; records-only W0  
**Canonical parent:** `market-timing-intelligence`  
**Repositories in scope:** `macro`, `mastermind-terminal`  
**Skillpack pin:** `mastermindx-market-intelligence/Mastermind@af43f356f4f7f34cb3514d1d1099b50444af8487`  
**Macro archaeology pin:** `mastermindx-market-intelligence/macro@463bb3b4b708a4748fc65a04250366ca94205186`  
**Terminal archaeology pin:** `mastermindx-market-intelligence/mastermind-terminal@b1b21a17f843d23e6e77d2abf0cc7e3dfd28ccea`  
**Status:** **FROZEN FOR W1 EVIDENCE CENSUS AND W2-0 DATA/CLOCK ARCHAEOLOGY**  
**Runtime status:** no signal, score, rank, gate, trade, alert, data-plane mutation, or production feature is authorized by this document.

---

## 0. Executive ruling

Mastermind will not solve technical analysis by adding hundreds of indicators to a vote.

It will build a **Technical Opportunity Intelligence** system that continuously determines, for a security and eventually for an index, sector, industry, or point-in-time basket:

1. which technical market process is occurring;
2. which causal phase of that process has been reached;
3. what exact trigger and invalidation define the next transition;
4. how much uncertainty and path risk remain;
5. how much of the historically comparable opportunity may already have been consumed;
6. what happened retrospectively and prospectively from comparable point-in-time states.

The product carries **two simultaneous queues**:

- **Forming / Armed** — anticipation before the move, with lower certainty and potentially more remaining opportunity;
- **Triggered / Confirmed** — actionability after evidence arrives, with confirmation cost and chase explicitly charged.

The queues remain separate. They may share a species and occurrence object, but they may not be averaged into a universal technical score.

The first proving vertical is:

> **U.S. single-stock Compression → Upside Release and Compression → Downside Release across completed Weekly, Daily, and registered 4H bars.**

True 5-minute tactical entry production remains owned by Live Entry Radar. Prophet, Golden Confluence, ranking, sizing, and trade authority remain unchanged.

---

## 1. Outcome before code

### 1.1 Primary user job

A serious investor or researcher monitoring a large equity universe needs to discover:

- securities whose setup is developing before the move becomes obvious;
- securities that have just crossed an actionable trigger;
- securities whose move is already too extended to chase;
- securities whose apparent breakout or reversal is failing;
- the precise evidence, contradiction, trigger, invalidation, and historical uncertainty behind each state.

The user should not have to translate a list of RSI, MACD, squeeze, triangle, or moving-average readings into a coherent market process.

### 1.2 Machine and intelligence job

For every covered subject and registered technical species, the machine must:

- compute only causal, source-receipted observations;
- separate setup, trigger, participation, context, and path-risk evidence;
- de-duplicate correlated evidence through the canonical dependency-family grammar;
- derive one current occurrence phase;
- preserve contradictions instead of averaging them away;
- estimate distinct activation, success, failure, path, and remaining-opportunity heads;
- abstain when data, coverage, effective sample size, or point-in-time integrity is inadequate;
- enroll only registered trigger events into the existing prospective evidence system.

### 1.3 Moat

The moat is not formula secrecy. Most standard technical formulas are public.

The moat is the integrated system of:

- normalized public-method archaeology;
- exact causal implementations and clock receipts;
- dependency-aware evidence rather than indicator counting;
- species-specific lifecycle and outcome rulers;
- retained nulls, failures, and rejected constructions;
- whole-universe monitoring;
- forward evidence clocks;
- chart-native product explanation;
- later conditioning by sector, theme, macro, flow, options, earnings, and issuer intelligence without giving any one context source premature authority.

### 1.4 Ten-out-of-ten end state

The intended end state is a technical perception layer where Mastermind can truthfully say, for example:

> **Daily bottom-reversal:** Triggered.  
> **4H momentum:** Confirming.  
> **Weekly structure:** Still damaged.  
> **Upside structural breakout:** Not Armed.  
> **Current extension:** Low.  
> **Strongest contradiction:** short-term reversal versus unresolved weekly downtrend.  
> **Remaining opportunity:** potentially substantial, wide uncertainty, conditional on weekly repair.

That is materially more useful than “87 bullish confluence.”

### 1.5 Completion proof

The program is not complete when code exists or a screener page renders. Completion requires:

- **Truth:** causal, correction-safe, rights-safe, point-in-time price and universe inputs with explicit clocks;
- **Intelligence:** registered species, lifecycle states, contradictions, calibrated path distributions, uncertainty, and retained failures;
- **Product:** two coherent queues, security detail, trigger/invalidation geometry, and Terminal integration across real states;
- **Learning:** prospective occurrence grading that shows whether the system improves discovery lead, entry quality, false-break avoidance, dead-money avoidance, or decision speed.

---

## 2. Current estate and capability ledger

| Capability | State at the archaeology pin | Ruling |
|---|---|---|
| Deterministic technical primitive catalog | `PARTIAL`, already broad | Extend `engine/tech_catalog.py`; no second indicator registry. |
| Dependency-family and evidence-role metadata | `BUILT_NOT_PROVEN` as complete ontology | Reuse and audit; do not count synonymous or correlated indicators as independent votes. |
| Current D/W confluence miner and public screener | `PROVEN_LIVE` as display-tier research/product | Preserve as incumbent benchmark, not as timing or trade authority. |
| Role-aware/dependency-aware Combo v2 | `NOT_BUILT` | Current miner still gates to legacy families. A future role-aware benchmark may be built, but it is not the final opportunity architecture. |
| Setup Species scientific registry | `BUILT` | Remains canonical for species identity, scientific lifecycle, deployment status, trials, and ledger binding. |
| General per-security technical occurrence lifecycle | `NOT_BUILT` | Build as a deterministic derived occurrence read over canonical species; do not create another species registry. |
| Durable-bottom and setup-species measurement law | `PARTIAL`, unusually mature | Generalize timing-native recall, lateness, false-bottom, dead-money, MFE/MAE, and wait-cost law. |
| Signal Foundry | `BUILT`, autonomous lane `DARK_OR_DISCONNECTED` by design | Reuse for declarative candidate proposals and frozen research batteries; no second automated research factory. |
| Deep, whole-universe, correction-safe daily U.S. panel | `PARTIAL` | Re-prove current coverage, split/correction behavior, universe history, and rights before research claims. |
| Deep causal whole-universe 4H research panel | `NOT_BUILT` or at least `BUILT_NOT_PROVEN` | W2-0 must establish current truth. Entitlement and a short collector are not proof of a research-ready panel. |
| Live Entry Radar tactical event plane | `PROVEN_LIVE` owner-side | Retains 5-minute RTH tactical events, live evaluation, and entry-event ownership. |
| Terminal chart and premium technical primitives | `BUILT` | Use as renderer and local geometry substrate; Macro owns canonical opportunity semantics. |
| Point-in-time theme/basket technical opportunity objects | `NOT_BUILT` | Later wave after single-security species and clocks are proven. |
| Prophet / Golden Confluence consumption | `REJECTED_BY_DESIGN` at birth | No consumption until a named species clears prospective promotion law and receives a separate ruling. |

### 2.1 Why the existing confluence product can feel statistically impressive but operationally mediocre

`engine/tech_catalog.py` already carries newer Technical Lab modules and metadata including `dependency_family`, `role`, `challenger_only`, provenance, and actionable lag.

`engine/tech_confluence.py` still contains a deliberate **Combo v1** gate:

- only `LEGACY_COMBO_FAMILIES` are enumerated;
- `challenger_only` signals are excluded;
- newer Technical Lab families are excluded;
- the file states that a later Combo v2 would lift the gate with a role-grammar search.

That later role-grammar implementation is not present at the archaeology pin.

The current screener therefore has two structural limitations:

1. it does not use the whole deterministic technical estate;
2. it ranks combinations that are active, rather than understanding whether a setup is forming, approaching a trigger, just triggered, confirmed, extended, exhausted, invalidated, or failed.

The current miner remains useful as a benchmark. It is not the architecture for the desired end state.

---

## 3. Canonical ownership and no-duplicate map

| Concern | Canonical owner | Technical Opportunity relationship |
|---|---|---|
| Deterministic technical primitives | `engine/tech_catalog.py` and source modules | Consume and extend; never fork. |
| Species identity, version, mechanism, horizon, scientific status | `engine/species_registry.py` + `data/species/registry.json` | Register new species/versions there. |
| Trials and preregistration | Existing trial/experiment infrastructure | Reuse exact families and budgets. |
| Candidate proposal/test automation | Signal Foundry / Research Factory | Reuse for simple declarative candidates; human promotion remains required. |
| Outcome maturation and promotion legality | Existing grading ledgers + Evaluation OS | Enroll registered events; no second evidence clock. |
| Tactical 5-minute entry events | Live Entry Radar | Read or hand off at the boundary; never duplicate. |
| Per-security current W/D/4H occurrence semantics | **Technical Opportunity Intelligence** | New owner-native capability. |
| Interactive chart rendering and indicator visuals | Terminal Charting / IndicatorCanvas | Render canonical occurrence payloads; do not mint conflicting semantic verdicts. |
| Prophet selection, plan geometry, rank, gate, size | Prophet | Unchanged. Technical Opportunity starts with zero authority. |
| Cross-owner evidence view | Opportunity Evidence Vector / later Market OS | May read promoted technical owner outputs; does not own or store them. |
| Identity | Existing issuer/security/listing identity owners | Ticker is a projection, not the canonical subject key. |
| Market-data ingest / WebSocket connection | Existing Massive/tick-plane owners | W2-0 audits and reuses; no new feed plane. |

### 3.1 One canonical scientific registry

The Setup Species Registry already enforces:

- one record per species-version;
- one frozen horizon class;
- explicit `phase0 → accruing → validated / falsified / retired` transitions;
- terminal falsification and retirement;
- version bumps when the research identity changes;
- trial counts;
- deployment status;
- ledger binding;
- maturation and promotion criteria;
- an experiments mirror.

No new “Technical Opportunity Species Registry” will be created.

### 3.2 One new owner-native object

The genuinely missing object is:

> **One current occurrence of one registered technical species on one subject at one causal observation time.**

That occurrence is derived from current source observations and species rules. It is not a second scientific registry, not a trade, and not a universal evidence store.

---

## 4. Two lifecycles that must never be blurred

### 4.1 Scientific lifecycle

Already canonical:

`PHASE0 → ACCRUING → VALIDATED / FALSIFIED / RETIRED`

Question answered:

> Does this species deserve to exist, what exactly did it claim, and what authority has it earned?

### 4.2 Per-security occurrence lifecycle

New:

`FORMING → ARMED → TRIGGERED → CONFIRMED → EXTENDED → EXHAUSTED`

with branches:

- `INVALIDATED` before a trigger;
- `FAILED` or `FAKEOUT` after a trigger.

Question answered:

> What is this subject doing now under this species definition?

| Phase | Machine meaning | Product treatment |
|---|---|---|
| `FORMING` | The mechanism is materially developing, but the trigger geometry or proximity is not yet actionable. | Early-discovery queue with lower certainty and potentially high remaining opportunity. |
| `ARMED` | Setup prerequisites remain intact; an exact trigger and invalidation are defined; price is within a registered activation distance. | Highest-priority watch state. |
| `TRIGGERED` | A completed registered bar crossed the frozen causal trigger for the first time. | Actionability queue; prospective evidence clock begins. |
| `CONFIRMED` | The move met the species-specific hold, follow-through, participation, or relative-strength condition. | Stronger path evidence, with confirmation cost printed. |
| `EXTENDED` | Too much of the comparable success path has been consumed, or the chase budget is breached. | Working move, no longer a fresh-entry recommendation. |
| `EXHAUSTED` | A mature move is losing marginal momentum, participation, or structure. | Position-health or opposite-direction watch context, not an automatic reversal trade. |
| `INVALIDATED` | Setup geometry failed before triggering. | Removed from live queues; retained through the existing rejection/near-miss owner when that binding is reconciled. |
| `FAILED` / `FAKEOUT` | Trigger occurred, then the registered failure condition arrived before successful path realization. | Explicitly graded failed occurrence. |

`DORMANT` is represented by the absence of a material occurrence, not by millions of empty durable rows.

### 4.3 No new lifecycle database in the first vertical

For the first vertical:

- `FORMING` and `ARMED` are recomputed deterministic current states;
- a current snapshot is published through an existing lawful artifact plane selected during W4;
- only a registered `TRIGGERED` transition opens an existing forward evidence episode;
- outcome maturation remains in existing ledgers;
- pre-trigger invalidations use the existing rejection/near-miss owner only after an explicit owner and contract reconciliation.

A durable occurrence-history database is not authorized by this W0.

---

## 5. Two-queue product law

### 5.1 Queue A — Forming / Armed

This queue answers:

> Which technically coherent setups are developing before the move, and what exactly must happen next?

Eligibility precedes ordering:

- registered species/version;
- current final data;
- minimum evidence and coverage;
- setup not invalidated;
- trigger geometry defined for `ARMED`;
- no rights, identity, clock, or integrity refusal;
- all authority flags false.

Ordering is lexicographic or Pareto-based, not one opaque score:

1. uncertainty-adjusted activation probability;
2. estimated remaining opportunity;
3. trigger proximity;
4. invalidation asymmetry;
5. independent evidence-family coverage;
6. setup freshness and decay;
7. effective sample size and prospective evidence state;
8. contradiction severity.

### 5.2 Queue B — Triggered / Confirmed

This queue answers:

> Which moves have actually begun, how much evidence has arrived, and is the move still worth acting on rather than chasing?

Ordering considers:

1. conditional path-success probability after trigger;
2. false-break probability;
3. expected MFE-to-MAE asymmetry;
4. estimated remaining opportunity after confirmation;
5. participation and relative-strength follow-through;
6. time and ATR distance since trigger;
7. confirmation wait cost;
8. extension and chase state;
9. evidence coverage, effective N, and uncertainty.

### 5.3 Confirmation is not free

Every confirmation rule must print:

- bars elapsed;
- price and ATR paid while waiting;
- MFE already consumed;
- false positives avoided;
- recall lost;
- MAE change;
- whether the rule merely selected survivors after the move had already begun.

A later signal may be more accurate and still be less useful.

---

## 6. Technical species are mechanisms, not indicator names

Initial mechanism families:

1. **Compression → Release**  
   Contracting range, volatility, or path efficiency before directional expansion.

2. **Structural Breakout / Breakdown**  
   Price leaves a behaviorally meaningful causal range, swing, base, support/resistance, or anchored level.

3. **Exhaustion → Reversal**  
   A mature directional move loses marginal pressure and begins turning.

4. **Trend Continuation / Pullback Reclaim**  
   An established trend corrects, retains structural identity, and resumes.

5. **Range Mean-Reversion Snap**  
   Price stretches from a stable range or consensus level and reverts.

6. **Failure / Fakeout**  
   A breakout or breakdown cannot retain its new range and reverses through the trigger structure.

7. **Mature-Move Exhaustion**  
   A working move loses path quality; primarily position-health and do-not-chase intelligence.

Bullish and bearish directions may share a mechanism family, but they require separate registered versions and separate outcome tables unless evidence proves symmetry.

### 6.1 Named-pattern disposition

A triangle, wedge, flag, cup, double bottom, head-and-shoulders, NR7, inside-bar coil, or squeeze receives one of four dispositions:

- first-class species;
- subtype;
- evidence configuration;
- duplicate/rejected.

It becomes a first-class species only if it demonstrates a distinct mechanism and incremental value beyond simpler parents.

A triangle, falling ATR, narrowing Bollinger bands, and reduced range may all describe one compression state. They are not four independent votes.

---

## 7. Canonical occurrence semantics

The exact wire schema and publication path remain W4 decisions. The semantic contract is frozen now.

```text
subject
  canonical security / listing identity
  ticker only as a projection

species
  species_id
  version
  direction
  horizon_class
  scientific validation_status
  deployment_status

observation
  as_of
  known_at
  source_available_at
  price_basis
  timestamp_basis
  timeframe_definition
  provisional_or_final
  evidence refs / digests

lifecycle
  phase
  phase_started_at
  prior_phase
  transition_reason
  setup_age_bars
  trigger_age_bars

geometry
  trigger_rule and level if applicable
  invalidation_rule and level if applicable
  structural range
  distance_to_trigger
  distance_to_invalidation
  distance_from_trigger
  ATR-normalized extension

evidence
  independent dependency families
  supporting observations
  contradictions
  missing or unavailable observations
  coverage denominator
  parent/duplicate receipt

outlook
  activation probability
  conditional path-success probability
  invalidation / fakeout probability
  expected MFE / MAE
  time-to-trigger / time-to-resolution distribution
  dead-money probability
  estimated opportunity consumed / remaining
  interval and effective N

authority
  can_rank = false
  can_size = false
  can_gate = false
  can_trade = false
  can_open_entry = false
```

### 7.1 Separate prediction heads are mandatory

The system may not collapse these into one “confidence” number:

1. `P(trigger within k bars | FORMING or ARMED)`;
2. `P(success path | TRIGGERED)`;
3. `P(invalidation or fakeout | current phase)`;
4. expected MFE, MAE, and time-to-resolution;
5. estimated path consumed and remaining.

A setup can trigger frequently and fail after trigger. Another can trigger rarely and work well when it does. One win rate hides the difference.

### 7.2 Contradictions are first-class

Examples:

- Daily trigger bullish; Weekly structure falling.
- Compression mature; participation absent.
- Price breakout; relative strength not confirming.
- 4H confirmation strong; Daily move already extended.
- Bullish reversal; nearby overhead supply dominates expected path.

Contradictions remain visible. They are not forced to zero through averaging.

---

## 8. Remaining-opportunity and chase law

Before trigger, report:

- distance to trigger;
- setup age and decay;
- distance to invalidation;
- probability and distribution of time-to-trigger;
- conditional remaining path if activation occurs.

After trigger, report:

- current excursion from trigger;
- historical conditional MFE and MAE;
- fakeout and invalidation risk;
- percentage or interval of comparable successful path already consumed;
- time elapsed relative to typical resolution;
- distance to opposing structure;
- volatility-adjusted remaining path.

Outputs must be distributions or bands, not false precision.

A lawful example:

> Estimated move consumed: 18–34% of comparable successful paths.  
> Confirmation cost: 0.8 ATR and two completed bars.  
> Fakeout risk: declining but unresolved.  
> Remaining path: favorable, wide uncertainty.

A lawful null:

> Comparable causal history is too sparse to estimate remaining opportunity.

---

## 9. Time, bar, and point-in-time law

### 9.1 Completed bars for authoritative transitions

- Weekly state uses the most recent completed exchange week.
- Daily state uses a completed market session.
- 4H state uses a completed registered bar.
- A forming bar may be displayed as `PROVISIONAL`, but it cannot produce an authoritative lifecycle transition or enter confirmatory research.

### 9.2 The U.S. 4H boundary problem

The NYSE core session is 9:30 a.m.–4:00 p.m. ET, or 390 minutes. It does not divide evenly into four-hour bars.

A naïve `resample("4h")` can:

- create unequal final bars;
- cross session boundaries;
- mix pre-market, regular, and after-hours prints;
- shift with timezone anchoring;
- disagree with Terminal or vendor charts.

W2-0 must audit and preregister at least two distinct constructions:

#### `4H-CLOCK`

- Exchange-time anchored four-hour buckets.
- Exact regular/extended-session policy.
- Exact treatment of the partial final session bar.
- Product-parity target named.
- Never pooled with a different construction.

#### `195M-RTH`

- Two equal 195-minute bars across the 390-minute regular session.
- No extended-hours contamination.
- Separate species/trial construction.
- Challenger used to detect bar-boundary artifacts.

Extended-hours variants remain separate.

### 9.3 Data entitlement is not a research panel

Massive documents custom historical aggregate bars in Eastern Time and minute/second WebSocket aggregates spanning pre-market, regular, and after-hours sessions. The repo also contains entitlement evidence and an intraday collector.

That proves technical feasibility, not current research readiness.

W3 is blocked until W2 proves:

- history depth;
- point-in-time availability;
- exact session and bar definition;
- split/dividend/corporate-action basis;
- late correction and revision behavior;
- delisted/reused-ticker handling;
- universe membership and survivorship treatment;
- source receipts and rights;
- per-date coverage;
- reproducible current and historical clocks.

Daily bars may not be used to fabricate historical 4H states.

---

## 10. Public evidence posture

The literature does not support either extreme claim that “technicals never matter” or that named patterns are universally predictive.

Published evidence includes:

- historical information in moving-average and trading-range-break rules;
- algorithmic definitions of chart patterns that altered conditional return distributions;
- persistent cross-sectional and time-series momentum in multiple samples;
- incremental information in nearness to a 52-week high;
- a role for volume in momentum magnitude and persistence.

The same literature documents severe hazards:

- data snooping across large rule universes;
- ex-post rule and parameter selection;
- weak transaction-cost and risk treatment;
- selection bias;
- backtest overfitting;
- regime and out-of-sample decay.

Mastermind therefore uses this law:

> Public research and lawful public formulas provide priors and candidates.  
> Local causal replication decides whether they work for the exact Mastermind job.  
> Prospective evidence decides whether a named species earns any authority.

---

## 11. Technical Evidence Census contract

W1 precedes heavy compute.

Every candidate receives a passport:

```text
canonical_id
aliases
source citations and rights
mechanism_family
exact causal formula
parameters and parameter domain
required data
known_at / actionable_lag
repaint or confirmation behavior
timeframe role
economic or behavioral mechanism
dependency family
parent, duplicate, and algebraic-equivalence relationships
expected failure modes
local implementation owner
baseline to beat
registered target/ruler
trial family and search budget
parameter-plateau requirement
universe/regime hypotheses
current local status
forward evidence state
```

Source hierarchy:

1. original papers and authors;
2. official exchange, vendor, and library documentation;
3. public books or educational formula references where lawful;
4. open implementations for parity and edge-case inspection only;
5. practitioner names as hypothesis leads;
6. proprietary/opaque methods blocked unless mechanics and rights are lawfully public.

The census normalizes synonyms before testing. Indicator breadth is not evidence.

---

## 12. Research and backtesting law

### Stage 0 — preregister

Before outcomes are opened:

- species/version;
- direction;
- horizon class;
- feature definitions;
- occurrence transitions;
- primary and secondary endpoints;
- comparators;
- universe;
- trial budget;
- parameter grid;
- costs;
- promotion and kill criteria.

### Stage 1 — formula and causal parity

Mandatory tests:

- truncation-prefix invariance;
- no future-bar leakage;
- known-time mapping;
- completed higher-timeframe bars;
- split and corporate-action behavior;
- session boundaries;
- missing intervals;
- repaint confirmation delay;
- parameter edges;
- independent fixture parity.

### Stage 2 — small-panel falsification

Use clear successes, clear failures, gaps, volatile names, low-volume names, long histories, recent listings, and delisted/reused-ticker cases where available.

This stage cannot support a performance claim.

### Stage 3 — broad retrospective event panel

Report:

- distinct occurrences;
- distinct tickers;
- sectors;
- calendar clusters;
- effective N;
- concentration;
- universe coverage;
- survivor bias;
- regime concentration.

Overlapping bars are not independent observations.

### Stage 4 — nested walk-forward

Model selection occurs inside training folds. Use:

- rolling or anchored walk-forward;
- embargo around overlapping outcomes;
- name, sector, and calendar holdouts;
- leave-crisis-out;
- leave-sector-out;
- early/late era splits.

### Stage 5 — family tournament and incremental lift

Each candidate competes against:

- its simplest parent;
- another representative from its dependency family;
- matched random entries;
- a simple price-only construction;
- current Combo v1;
- the same model with the candidate family ablated.

### Stage 6 — model-selection controls

Use the tool appropriate to the claim:

- BH-FDR or stronger familywise control for declared families;
- White Reality Check or Hansen SPA for searched strategy sets;
- CSCV / Probability of Backtest Overfitting for selection risk;
- Deflated Sharpe only for legitimate return-series claims;
- episode-clustered bootstrap for proportions and path outcomes;
- permutation tests for selected regime cells and interactions.

No single statistic is a universal proof stamp.

### Stage 7 — prospective shadow accrual

Retrospective survivors remain challengers.

Only events observed after registration may support promotion.

LLMs may propose, normalize, explain, or challenge. They may not originate a signal, numeric confidence, rank, size, gate, or trade.

---

## 13. First proving vertical — Compression → Release

Separate registered species:

- `compression_release_up`;
- `compression_release_down`.

The exact IDs and versions are assigned in W3 after W1/W2.

### 13.1 Setup evidence families

- Bollinger bandwidth percentile;
- Keltner/Bollinger squeeze;
- normalized ATR;
- realized-volatility percentile;
- high-low range contraction;
- inside/nested-bar structure;
- trend-efficiency decline;
- directional-movement compression;
- volume contraction;
- tightening dispersion.

Correlated variants are treated as one family or dependency-adjusted evidence.

### 13.2 Structure

- prior causal range;
- confirmed swing high/low;
- prior-bar Donchian boundary;
- triangle/wedge boundary;
- support/resistance cluster;
- base duration and touch count.

### 13.3 Trigger

- first completed close outside the frozen registered range;
- optional gap-through variant as a separate construction;
- provisional intrabar state display-only;
- no post-breakout trigger rewriting.

### 13.4 Participation

- relative volume;
- volume expansion versus setup;
- OBV/CMF direction;
- peer breadth;
- gap quality;
- close location.

### 13.5 Relative strength

- versus market;
- versus sector;
- RS line breakout or stabilization;
- leader/laggard classification.

### 13.6 Path risk

- ATR distance from trigger;
- gap extension;
- opposing structure;
- setup age;
- trigger-bar overextension;
- prior failed attempts;
- liquidity and slippage.

### 13.7 Phase definitions

`FORMING`:

- registered compression evidence;
- causal structure exists or is becoming definable;
- no trigger;
- setup age within bounds;
- minimum independent-family coverage.

`ARMED`:

- forming state remains valid;
- exact trigger and invalidation;
- price within registered ATR distance;
- no extension/integrity veto;
- final current data.

`TRIGGERED`:

- first completed registered-timeframe close through the frozen trigger;
- event address includes species/version, subject, trigger basis, and observation clocks.

`CONFIRMED`:

- one preregistered hold, follow-through, participation, or RS rule;
- every variant carries a wait-cost receipt.

`EXTENDED`:

- registered ATR or conditional path-consumption ceiling breached.

`FAILED` / `FAKEOUT`:

- close through the failure boundary or invalidation before successful path realization.

### 13.8 Prediction and grading heads

Before trigger:

- activation probability;
- time to trigger;
- pre-trigger invalidation;
- activation precision/recall;
- silence rate;
- trigger premium from ARMED.

After trigger:

- fakeout at 1/3/5/10 bars;
- MFE/MAE;
- +1 ATR before −1 ATR;
- +2 ATR before registered invalidation;
- time to favorable excursion;
- dead-money;
- path persistence;
- capture fraction;
- confirmation wait cost;
- remaining opportunity.

### 13.9 Mandatory baselines

- prior-range / Donchian breakout;
- volatility/liquidity-matched breakout;
- random near-range-high/low;
- current Combo v1 leaders;
- compression without participation;
- structure without compression;
- Daily-only;
- Weekly+Daily;
- Weekly+Daily+4H;
- `4H-CLOCK` versus `195M-RTH`.

Success requires an independently useful improvement, such as earlier discovery at comparable fakeout risk, lower fakeout at comparable lead, better MFE/MAE, less chase, more remaining-path capture, or more useful abstention.

A higher 21-day positive-return rate alone is insufficient.

---

## 14. Product experience

### 14.1 Technical Opportunity Radar

#### Forming / Armed row

- ticker/company;
- species and phase;
- trigger, distance, invalidation;
- setup age;
- W/D/4H map;
- activation probability;
- remaining-opportunity band;
- independent evidence;
- strongest contradiction;
- effective N and uncertainty;
- freshness.

#### Triggered / Confirmed row

- trigger and confirmation time/price;
- confirmation cost;
- current trigger distance;
- fakeout risk;
- expected MFE/MAE;
- move consumed / remaining;
- extension state;
- invalidation;
- prospective evidence state.

### 14.2 Security detail

- lifecycle strip;
- annotated chart;
- evidence matrix;
- contradiction panel;
- causal historical analogs;
- path distributions;
- research passport;
- source/freshness/coverage receipts.

### 14.3 Terminal

Terminal renders:

- setup geometry;
- trigger and invalidation;
- occurrence phase;
- provisional/final status;
- evidence-family overlays;
- contradiction chips;
- historical occurrence markers;
- path-consumption band.

Macro owns the canonical occurrence semantics. Terminal may compute local visual primitives, but parity tests must prevent a conflicting verdict.

### 14.4 Baskets and themes — later

The same species may later be evaluated on:

- cap-weighted synthetic price;
- equal-weight synthetic price;
- member breadth;
- member lifecycle distribution;
- leadership concentration;
- dispersion;
- point-in-time constituent coverage.

A basket is not the average of member technical scores. Cap-weighted and equal-weighted objects remain separate.

---

## 15. Authority envelope

At birth, every Technical Opportunity output has:

```text
can_rank = false
can_size = false
can_gate = false
can_trade = false
can_open_entry = false
can_suppress_radar = false
can_modify_prophet = false
```

Possible ladder:

1. research result;
2. display occurrence;
3. prospective ordering inside the technical surface;
4. graded technical bonus;
5. governed contribution to a cross-owner evidence view;
6. separate Prophet/Golden Confluence adjudication;
7. trade or sizing authority only under a stronger future program.

No automatic promotion.

Downside breakdowns are research/display opportunities at birth, not automatic directional short authority.

---

## 16. Binding DNR and no-rebuild boundaries

This program must cite and respect at minimum:

- `DNR:KILL-OUTCOME-AUDITION` — no per-name in-sample best-tool audition;
- `DNR:KILL-OFFHORIZON-VERDICTS` — only preregistered horizon rulers;
- `DNR:KILL-LLM-ORIGINATION`;
- `DNR:KILL-LLM-CONFIDENCE`;
- `DNR:KILL-FUSED-COMPOSITE`;
- `DNR:KILL-PROPHET-POP-MERGE`;
- `DNR:KILL-DIRECTIONAL-SHORTING`;
- `DNR:KILL-ROTATION-CYCLE-CONFLUENCE`;
- `DNR:KILL-PSS-F1-DOWNVOL`;
- `DNR:KILL-PSS-F2-OVERNIGHT`;
- `DNR:KILL-PSS-F3-RESIDUAL`;
- `DNR:KILL-PSS-F4-SEMIVAR`;
- `DNR:KILL-PSS-F4-REPAIR`;
- `DNR:KILL-PSS-SR1-ELASTICITY`;
- `DNR:KILL-PSS-SR2-PEER-DIFFUSION`;
- `DNR:KILL-PSS-SR3-PARTICIPATION`;
- `DNR:KILL-WASHOUT-TURN`.

Construction-scoped kills remain construction-scoped. A retained descriptor may enter a genuinely new preregistered family tournament, but a killed timer or hard gate may not be renamed and retried.

No new:

- indicator registry;
- species registry;
- experiment registry;
- trial ledger;
- evidence clock;
- market-data/WebSocket plane;
- tactical entry radar;
- identity system;
- chart renderer;
- generic evidence warehouse;
- universal technical score;
- Prophet ranker;
- memory or Agent OS database.

---

## 17. Program waves

### W0 — Architecture and durable records

This carrier:

- freezes outcome, ownership, two queues, lifecycles, clock law, research law, product end state, and no-rebuild boundaries;
- creates the canonical Agent OS workstream, decision, discoveries, and continuation handoff;
- commissions no runtime work.

### W1 — Technical Evidence Census

Normalize the public technical universe, current local coverage, aliases, formulas, dependencies, sources, rights, failures, and research priority.

### W2-0 — Data and Clock Archaeology

Prove or fail the current Daily/Weekly/4H data substrate. Freeze bar, session, adjustment, correction, universe, rights, and coverage law. No signal performance runs.

### W2 — Data substrate implementation, only if W2-0 authorizes it

Extend the existing owner plane. No second feed or store by convenience.

### W3 — Compression Release phase zero

Preregister bullish and bearish species, run formula parity and family tournaments, and return retrospective evidence and kill/promote recommendations. No production authority.

### W4 — Current occurrence engine

Produce current two-queue snapshots, trigger/invalidation geometry, evidence, contradictions, and forward-event enrollment without a new lifecycle database.

### W5 — Product and Terminal vertical

Ship Technical Opportunity Radar, security detail, chart overlays, responsive and bilingual states, and real-data browser proof.

### W6 — Prospective production proof

Prove fresh coverage, exact clocks, real occurrences, forward enrollment, degraded states, latency, and no duplicate events on the production path.

### W7 — Sol adjudication

Kill, version, continue accrual, retain display-only, or authorize a bounded consumer per species.

### W8 — Reversal vertical

Generalize the Durable Bottom and Setup Species laws to bottom/top reversal without reopening killed constructions.

Later:

- continuation/pullback;
- fakeout;
- mature-move exhaustion;
- range mean reversion;
- point-in-time sector/theme baskets;
- governed conditioning by GMI, earnings, fundamentals, options, flow, and issuer intelligence.

---

## 18. W0 acceptance gates

W0 passes only when:

- protected Skillpack SHA is recorded;
- current Macro and Terminal SHAs are recorded;
- no exact current carrier/workstream collision exists;
- `market-timing-intelligence` is the canonical parent;
- Live Entry Radar and Stock Identity boundaries are named;
- Setup Species remains canonical;
- two queues and no-universal-score law are durable;
- W1 and W2-0 handoffs are cold-stranger complete;
- Agent OS validation and CI are green;
- the PR remains records-only;
- no runtime, data, score, rank, gate, or trade path changes.

W0 merge does not mean W1/W2 research succeeded, data is ready, the occurrence engine exists, or the product is live.

---

## 19. Primary public-source spine for W1

Academic and statistical priors:

1. Brock, Lakonishok & LeBaron, “Simple Technical Trading Rules and the Stochastic Properties of Stock Returns,” DOI `10.1111/j.1540-6261.1992.tb04681.x`.
2. Lo, Mamaysky & Wang, “Foundations of Technical Analysis,” DOI `10.1111/0022-1082.00265`; NBER `10.3386/w7613`.
3. Sullivan, Timmermann & White, “Data-Snooping, Technical Trading Rule Performance, and the Bootstrap,” DOI `10.1111/0022-1082.00163`.
4. Park & Irwin, “What Do We Know About the Profitability of Technical Analysis?”, DOI `10.1111/j.1467-6419.2007.00519.x`.
5. Jegadeesh & Titman, “Returns to Buying Winners and Selling Losers,” DOI `10.1111/j.1540-6261.1993.tb04702.x`.
6. George & Hwang, “The 52-Week High and Momentum Investing,” DOI `10.1111/j.1540-6261.2004.00695.x`.
7. Lee & Swaminathan, “Price Momentum and Trading Volume,” DOI `10.1111/0022-1082.00280`.
8. Moskowitz, Ooi & Pedersen, “Time Series Momentum,” DOI `10.1016/j.jfineco.2011.11.003`.
9. Hansen, “A Test for Superior Predictive Ability,” DOI `10.1198/073500105000000063`.
10. Bailey, Borwein, López de Prado & Zhu, “The Probability of Backtest Overfitting,” DOI `10.21314/JCF.2016.322`.
11. Bailey & López de Prado, “The Deflated Sharpe Ratio,” DOI `10.3905/jpm.2014.40.5.094`.
12. Gao, Han, Li & Zhou, “Market Intraday Momentum,” DOI `10.1016/j.jfineco.2018.05.009`.
13. Rosa, “Understanding Intraday Momentum Strategies,” DOI `10.1002/fut.22375`.
14. Lim, Zohren & Roberts, “Enhancing Time Series Momentum Strategies Using Deep Neural Networks,” arXiv `1904.04912`.
15. Lim, Arik, Loeff & Pfister, “Temporal Fusion Transformers for Interpretable Multi-horizon Time Series Forecasting,” DOI `10.1016/j.ijforecast.2021.03.012`.

Official method and clock sources:

- TA-Lib official function catalog: `https://ta-lib.org/functions/`
- TradingView Technical Ratings: `https://www.tradingview.com/support/solutions/43000614331-technical-ratings/`
- NYSE trading hours: `https://www.nyse.com/trade/trading-information`
- Massive custom bars: `https://massive.com/docs/rest/stocks/aggregates/custom-bars`
- Massive minute aggregates: `https://massive.com/docs/websocket/stocks/aggregates-per-minute`
- Massive second aggregates: `https://massive.com/docs/websocket/stocks/aggregates-per-second`

These sources seed W1. They do not pre-authorize any formula, parameter, product claim, or authority.

---

## 20. Exact next action after W0 acceptance

Run two disjoint bounded research carriers:

1. **W1 Evidence Census** — public evidence, formula, alias, dependency, local coverage, and rights normalization;
2. **W2-0 Data/Clock Archaeology** — current source, bar, session, correction, adjustment, universe, and coverage proof.

No Compression Release outcome testing begins until both return and Sol freezes the W3 preregistration.
