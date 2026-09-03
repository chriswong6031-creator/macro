# Policy Transmission & Pre-Turn Command — Architecture Design

Date: 2026-09-03  
Status: **DESIGN ACCEPTED / ARCHITECTURE FROZEN / RECORDS-ONLY UNTIL IMPLEMENTATION WAVES PROVE OTHERWISE**  
Chairman intent: anticipate macro turns before retrospective regime labels, monitor Fed/Treasury/administration reaction windows, and explain apparently contradictory cross-asset moves well enough to improve real portfolio and end-user decisions.  
Canonical implementation carrier for the first vertical: GitHub issue #6787  
Protected Sol procedure at freeze: `mastermindx-market-intelligence/Mastermind@793e75639911f21dae9c90a77c3a5dbf4b37cbb0`, `mastermind.sol_skillpack.v1` 1.0.1, bootstrap major 1 compatible.  
Macro architecture base: `931870b1feccb91b5122d92b07995e9749566aae`.

## 1. Outcome

The product job is not to report that yields rose, a speech occurred, or volatility expanded. It is to identify the **transition sequence** early enough for a user to change posture before the market has fully repriced it:

```text
pressure accumulates
→ a market or policy threshold is approached
→ one or more actors acquire incentive and available tools to respond
→ cross-assets begin pricing the response before the response is fully visible
→ support is confirmed, contradicted or withdrawn
→ leadership and portfolio posture change
```

The primary user must be able to answer:

1. What pressure is building now?
2. Which scheduled event or market threshold could cause the next turn?
3. Which actor can respond, what tool is available, and what constrains its use?
4. Is the market still pricing the shock, or already pricing the response to the shock?
5. Which assets confirm the proposed turn and which contradict it?
6. What would invalidate the read before it becomes expensive?
7. Which portfolio exposures are structurally robust, conditionally attractive, or vulnerable to a reversal?

The machine job is to preserve point-in-time evidence, compose canonical market and policy owners, publish deterministic transition states with explicit unknowns, and prospectively grade whether the warning preceded a real turn.

Completion is not a new dashboard card. Completion requires official-source truth, useful causal intelligence, a coherent product journey, a real machine consumer, and evidence that the system improves lead time without laundering narrative into trade authority.

## 2. Product thesis

Mastermind wins by combining four capabilities that are usually fragmented:

- **public-policy microstructure:** exact schedules, speeches, liquidity operations, source revisions and actor availability;
- **market microstructure:** OPEX inventory, futures rolls, auctions, rebalancing, funding and dealer constraints;
- **cross-asset causal reconciliation:** nominal yields, real yields, dollar, oil, metals, credit, volatility and equity breadth read together rather than as isolated indicators;
- **reaction-function intelligence:** actor interests and constraints represented as conditional response windows, not secret-intent certainty.

The moat is the accumulated point-in-time evidence graph and its prospective track record. Provenance is necessary but insufficient: the product must turn receipts into a useful explanation of **what changes next and how the user knows**.

## 3. Current capability ledger at freeze

| Capability | State | Freeze implication |
|---|---|---|
| Unified U.S. scheduled-event calendar | `BUILT_NOT_PROVEN` for this new use | Extend/consume `engine/event_calendar.py`; do not create another calendar. |
| OPEX calendar and phase | `BUILT_NOT_PROVEN` for this new use | `engine/opex.py` remains the only expiration-date owner. |
| Dealer-surface/OPEX holdability | `PARTIAL` | Existing options surface and `engine/opex_risk.py` provide useful context but carry OI-timing and dealer-sign uncertainty. |
| Rebalance calendar and observed pulse | `PARTIAL` | Existing RLT organs describe calendar and mechanical volume; they are not bottom callers. |
| TGA and net-liquidity plumbing | `PARTIAL` | `engine/treasury_watch.py` owns TGA episodes; buyback/auction/settlement detail is incomplete. |
| Static Fed/administration policy intelligence | `PARTIAL` | Rich but stale for fast event monitoring; cannot be treated as a live clock. |
| RIC F3 yield momentum | `BUILT_NOT_PROVEN / RELEASE_BLOCKED` | PR #6721 is the sole carrier; no duplicate implementation. |
| Official actor schedule/location clock | `NOT_BUILT` | First-wave source truth. |
| Futures-roll clock with live progress | `NOT_BUILT` | Build as a helper consumed by the canonical event view, never as a second event system. |
| Cross-asset contradiction resolver | `NOT_BUILT` | Later wave after source/event and yield foundations are accepted. |
| Conditional actor response windows | `NOT_BUILT` | Later research/shadow wave. |
| Pre-turn posture vector | `NOT_BUILT` | Later descriptive/calibrated layer; Prophet authority unchanged. |
| Secret coordination, private-location or discretionary-timing oracle | `REJECTED_BY_DESIGN` | Never build. |

This operation does not upgrade any row merely by documenting it.

## 4. Canonical ownership and no-rebuild law

Policy Transmission & Pre-Turn Command is a composition capability inside the existing Rates & Inflation Command and Global Markets/Regimes estate. It does not create a new workstream, application, event database, options plane, market-state classifier, queue, scheduler, lifecycle, model router, forecast authority or trade system.

Canonical owners:

| Question | Owner |
|---|---|
| Scheduled U.S. macro events | `engine/event_calendar.py` |
| Historical event-window behavior | `engine/event_window.py` |
| Release truth/forecast/corrections | existing Macro Release Intelligence owners |
| Monthly options-expiration phase | `engine/opex.py` |
| Options surface and OPEX holdability | ThetaData plane, `engine/options_surface.py`, `engine/opex_risk.py` |
| Rebalance dates and observed pulse | `engine/rebalance_calendar.py`, `engine/rebalance_pulse.py` |
| TGA episode and net-liquidity mechanics | `engine/treasury_watch.py`, existing canonical liquidity artifacts |
| Yield momentum | RIC F3 PR #6721 until reconciled/accepted |
| Shock/repricing context | existing `market_drivers` and Policy-Shock Regime owners |
| Trade ranking, entry, sizing and capital | existing Prophet/portfolio authorities |
| Runtime jobs, attempts and workers | Executive OS |
| Organizational decisions and handoffs | Agent OS |

The accepted `DEC:RIC-CANONICAL-COMPOSITION-BOUNDARIES` remains binding. An implementation that creates a convenient duplicate is a design failure even if its output is correct.

## 5. Evidence architecture

### 5.1 Event and actor evidence

Every official event observation uses a revision-safe record with:

- stable source identity;
- actor identity and role as of the event;
- organization and source publisher;
- event kind, title, topics and audience;
- `scheduled_start`, `scheduled_end`, timezone and status;
- location label plus precision (`venue`, `city`, `country`, `unknown`);
- source URL, source publication time, observation time, available-at time and content digest;
- revision/cancellation lineage;
- evidence class (`FACT`, `INFERENCE`, `PRIOR`, `THEORY`);
- rights/source class and parser version.

A later correction appends a new vintage; it never overwrites the original point-in-time record. The current projection selects the latest valid vintage while retaining the full lineage.

`current_location` is permitted only while an official event window or official statement supports it. Outside that window, the product shows `last_verified_location` and `current_location_status=unknown`. It never infers travel from photographs, prior city, press silence or a likely itinerary.

### 5.2 Treasury liquidity evidence

Treasury records separate:

- announcement maximum;
- submitted/offered amount;
- accepted amount;
- instrument and tenor scope;
- operation type (`auction`, `buyback`, `cash_management`, `tga_release`, `tga_build`, `settlement`);
- operation window, auction time, settlement date and maturity date;
- mechanical reserve/liquidity direction;
- market-function objective stated by the source;
- inferred policy intent, if any, as a separately labeled hypothesis.

A TGA decline is mechanically liquidity-supportive all else equal. It is not evidence that Treasury deliberately rescued equities. A buyback can support market liquidity without being QE or yield-curve control.

### 5.3 Market and flow evidence

Each market observation retains `observed_at`, `available_at`, source owner, unit, session, timezone, revision policy and freshness budget. Null, zero, false and not-applicable remain distinct.

Options consumers must carry the canonical OI timing and dealer-sign passports. Sign-robust magnitude fields are preferred where available. Futures-roll state must distinguish a scheduled quarterly window from observed migration in volume/open interest.

## 6. Intelligence architecture

### 6.1 Yield-cause decomposition

A later bounded wave will decompose material yield moves into separately evidenced contributors:

- expected Fed path;
- real-growth expectations;
- inflation breakevens;
- term premium and fiscal supply;
- auction absorption and dealer balance sheet;
- AI capital demand and corporate issuance;
- Japan/global-duration spillovers;
- oil/geopolitical inflation;
- funding, repo, swap and basis stress;
- positioning/technical liquidation;
- policy-response anticipation.

The output is a mixture with confidence and disagreement, not one asserted cause.

### 6.2 Cross-asset contradiction resolver

The resolver must explain combinations such as:

- yields and gold rising together;
- yields rising while cyclicals outperform;
- yields falling while equities and credit deteriorate;
- gold rising while silver lags;
- metals, small caps and equities rising after a yield spike.

It compares levels, velocity, acceleration, intraday rejection and confirmation across nominal/real yields, dollar, breakevens, oil, credit, equity breadth, small caps, gold, silver, copper, yen, JGBs, MOVE and equity volatility.

Its principal question is: **is the market pricing the shock, or the expected response to the shock?**

### 6.3 Reaction-function graph

Each actor node contains:

- stated objective;
- inferred incentive;
- constraints;
- available tools;
- observable activation conditions;
- counterparties;
- current alignment/conflict edges;
- evidence class and confidence;
- last material action and next public decision window.

Shared interests may create aligned behavior; they do not prove secret coordination. Response output is categorical and conditional:

```text
DORMANT
PRESSURE_BUILDING
RESPONSE_WINDOW_OPEN
ACTION_OBSERVED
TRANSMISSION_PENDING
CONFIRMED
INVALIDATED
UNKNOWN
```

It may say that a Treasury response window is opening because auction absorption and long-end liquidity worsened while a scheduled buyback tool exists. It may not say that Bessent will intervene at a specific undisclosed time.

### 6.4 Monthly transition clock

The monthly pattern is modeled as **support formation, support expiry, replacement and catalyst override**, not seasonality.

Required independent axes:

- OPEX phase and front-cycle concentration;
- gamma/pin context;
- vanna/charm holdability, with symmetry caveat;
- replacement-book evidence after expiration;
- quarterly equity/Treasury futures roll schedule and observed progress;
- month-/quarter-end rebalance calendar and pulse;
- bond-index extension context;
- Treasury/TGA/settlement liquidity;
- macro/policy catalyst density;
- cross-asset confirmation;
- source coverage/freshness.

Permitted glance states:

```text
SUPPORT_BUILDING
SUPPORT_STABLE
PINNED
SUPPORT_ROLLOFF_IMMINENT
VOLATILITY_WINDOW_OPEN
MONTH_END_REBALANCE_DOMINANT
CATALYST_DOMINANT
MIXED
UNKNOWN
```

Calendar proximity alone cannot select a directional state. State precedence and evidence minimums are frozen in the first-vertical design.

### 6.5 Posture vector

The command eventually publishes independent descriptive axes, not a single master score:

- duration pressure;
- real-yield/dollar tightening;
- inflation/energy pressure;
- Treasury liquidity/funding;
- growth/AI capital demand;
- geopolitical/haven pressure;
- credit/market-function health;
- monthly support/rolloff.

A later calibrated layer may estimate transition hazards after sufficient prospective evidence. It does not originate trades or silently change Prophet ranking or portfolio size.

## 7. Product experience

The primary Macro/Policy Watch composition has four layers.

### Now

- what changed since the prior observation;
- current monthly/support phase;
- current yield-cause mixture once that wave is accepted;
- cross-assets agreeing and disagreeing;
- freshness and material gaps.

### Next 72 hours / 14 days

- actor, organization, event and exact ET time;
- Treasury operation type, announced/accepted amount and settlement;
- macro releases, auctions, OPEX, month-end and futures-roll windows;
- expected information gain and affected channels;
- cancellation/revision state.

### Why this can turn

- mechanism chain;
- actor response windows and available tools;
- whether markets are pricing shock or response;
- confirmation and invalidation conditions.

### Decision translation

Retail-facing copy compresses the read into plain language. The institutional detail layer preserves raw evidence, calculations, assumptions and receipts. The same machine JSON feeds Terminal or other governed consumers; HTML is never the API.

Required failure states include fresh, partial, stale, source-unavailable, cancelled, contradictory and unknown. The panel must remain visible and honest rather than disappearing when data is missing.

## 8. Monthly-pattern ruling

The Chairman’s observation is real enough to deserve a first-class clock, but unsafe as a universal rule.

Historical research documented strong returns from the last trading day through the first three trading days, yet newer work finds the unconditional effect disappears after 2001 and in-repo modern SPY research withholds a forward edge. Academic work on expiration week finds higher large-cap returns and declining implied volatility/dealer call exposure in some samples, while Mastermind’s own adjudication finds post-OPEX weakness era-sensitive and not robust enough for directional authority. Cboe research also finds aggregate SPX 0DTE dealer gamma small relative to futures liquidity on average, so the product cannot blame every intraday move on 0DTE hedging. New York Fed research documents unusually high Treasury activity at month-end, consistent with passive fixed-income rebalancing, and in-repo study finds month-end duration extension stronger than generic pension-rebalance folklore.

Therefore:

- **OPEX is an inventory transition, not a bearish date.**
- **Post-OPEX is a support-rolloff hazard only when stabilizing inventory actually existed and replacement/confirmation is weak.**
- **Early-month support must be observed through cash, option-book rebuilding, volatility control, breadth or liquidity—not assumed from the calendar.**
- **Quarterly futures rolls are separate from ordinary monthly OPEX.**
- **Month-end bond and equity effects are asset-specific and may oppose one another.**
- **Major releases can dominate every mechanical clock.**

The system predicts the condition under which a turn becomes more likely; it does not emit “buy first day / sell fourth Friday.”

## 9. Method and authority boundaries

| Layer | Method | Authority |
|---|---|---|
| Official schedules, amounts, locations and revisions | deterministic | fact |
| OPEX/month-end/futures calendars | deterministic | context |
| Options, liquidity and rebalance state | deterministic measurements with assumptions | descriptive |
| Historical phase statistics | statistical, era-split | research |
| Cross-asset cause mixture | statistical/structured synthesis | research/shadow until validated |
| Actor-interest narrative | model-assisted only over receipts | context |
| Response-window hazard | calibrated after prospective evidence | research/shadow |
| Rank, gate, size, trade | existing Prophet/portfolio owners | unchanged |

No model output may override a deterministic source fact or silently become a state transition. No calendar construction may enter a risk-sizing path.

## 10. Prospective learning

Every transition call freezes:

- evidence cutoff;
- current state and contributing axes;
- expected mechanism;
- affected markets;
- horizon;
- confirmation;
- invalidation;
- missing evidence;
- confidence and method version.

Evaluation separates:

- warning lead time;
- realized volatility/path;
- mechanism correctness;
- timing correctness;
- false alarms;
- missed transitions;
- correction/freshness failures;
- decision usefulness.

Backtests and live cohorts never share one badge. Promotion requires a predeclared sample floor, era stability, point-in-time replay and forward evidence. A useful display capability may ship before signal authority.

## 11. Wave sequence

### PTC-W1 — Actor, Liquidity & Monthly Transition Clock

Canonical issue: #6787. Build official-source receipts, quarterly futures-roll helper, deterministic monthly transition composer, machine artifact, Policy Watch consumer and prospective receipt. No model dependency and no trade authority.

### PTC-W2 — Source breadth and speech-delta intelligence

Add regional Fed, BOJ/MOF, White House, State, Energy and Iran/sanctions official sources; transcript/speech change detection remains receipt-grounded and context-only.

### PTC-W3 — Yield Cause & Cross-Asset Contradiction Resolver

Begins only after RIC F3 is reconciled/accepted or explicitly redesigned on its existing carrier. Composes current yield, market-driver and cross-asset owners.

### PTC-W4 — Reaction-Function Graph & Response Windows

Build actor pressure/tool/constraint graph and categorical response windows. No private-intent probabilities.

### PTC-W5 — Pre-Turn Posture & Evaluation

Publish the descriptive posture vector, prospective cohort evaluation and any later calibrated hazards that survive promotion gates. Prophet/portfolio integration requires a separate authority ruling.

## 12. Acceptance standard

The program is not complete until it has:

- **Truth:** fresh official sources, exact clocks, revision/cancellation safety and rights-safe receipts;
- **Intelligence:** useful mechanism chains, contradiction resolution, response windows and explicit unknowns;
- **Product:** a premium, plain-language workflow across desktop/mobile, light/dark and English/Chinese;
- **Learning:** prospective evidence that measures lead time, false alarms and decision usefulness.

Green CI, a merged spec, a generated JSON or a rendered card are not final acceptance. Every wave requires real input through the real production path to a visible user and machine consumer.

## 13. References informing the monthly ruling

- McConnell and Xu, “Equity Returns at the Turn of the Month,” Purdue/CFA Institute.
- Han, Han and Tian, “The disappearing turn-of-month effect,” *Finance Research Letters* 71 (2025).
- Stivers and Sun, “Returns and option activity over the option-expiration week for S&P 100 stocks,” *Journal of Banking & Finance* 37 (2013).
- Cboe, “Much Ado About 0DTEs” and subsequent 0DTE market-impact work.
- CME Group, Equity Index Roll Dates, Equity Quarterly Roll Analyzer and Treasury Pace of the Roll.
- Federal Reserve Bank of New York, “End-of-Month Liquidity in the Treasury Market.”
- In-repo `research/OPTIONS_OPEX_VANNA_CHARM_ADJUDICATION.md`, `reports/artifacts/options_opex_vanna_charm_summary.md`, `reports/d2-rates-calendar-flows-phase0.md`, and `research/REBALANCE_LIQUIDITY_TRANSMISSION_MASTERPLAN_BY_FABLE.md`.
