# Intraday Flow Opportunity OS — product, intelligence, and lifecycle ruling

**Date:** 2026-09-05  
**Operation:** `intraday-flow-opportunity-lifecycle-p0-20260905-sol-001`  
**Authority:** Chairman-directed Sol product/intelligence architecture  
**Repository/base inspected:** `mastermindx-market-intelligence/macro@443fe9a6f7d98484710452dc98f1aed58011c823`  
**Protected Sol procedure inspected:** `mastermindx-market-intelligence/Mastermind@a3440f21a0d6df7666bd9ed9f3b02385dac23588` (`mastermind.sol_skillpack.v1`, v1.0.1, bootstrap major 1)  
**Status:** architecture frozen for the bounded P0 lifecycle correction; later waves remain dependency- and evidence-gated  
**Authority ceiling:** descriptive/display and research-candidate intelligence only. Nothing in this ruling authorizes trade origination, order execution, position sizing, Prophet ranking authority, or promotion of options-derived signals.

---

## 1. Executive ruling

The current Intraday Flow board is a useful **market radar**, but it is not yet a trustworthy end-to-end opportunity system.

Its existing foundation is materially stronger than a generic unusual-options-flow page:

- a curated 116-name leader universe rather than an indiscriminate tape;
- explicit washout/reclaim, time-of-day RVOL, VWAP, volume durability, higher-low, multi-timeframe, trap, and leader-quality context;
- per-root intraday options flow, event badges, DTE/strike context, dealer levels, expected move, skew, IV rank, and OPEX context;
- source clocks, degraded states, null-aware handling, bilingual explanations, risk/invalidation fields, and a forward-return ledger;
- a current recovery lane that already repaired quote/pulse wiring and source-health semantics, although natural regular-session production proof is still owed.

The board’s decisive weakness is **temporal semantics**. It recomputes a memoryless snapshot and then presents that snapshot as an opportunity stage. It does not preserve a setup epoch, trigger event, trigger time, trigger price, maximum favorable/adverse excursion, reset condition, or expiry. Consequently, a name can move from “Almost ready” to actionable and later fall back to “Almost ready” while the old washout bit is still inside its lookback window. The ASTS card observed by the Chairman is a real product defect class, not a cosmetic wording issue.

The immediate correction is therefore not “add more options metrics.” It is:

> **Make timing state monotonic within a setup episode, block pre-trigger language after activation/extension/failure, and show an explicit anti-chase state.**

The 10/10 end-state is an **Intraday Opportunity OS** that answers, for each candidate:

1. **Why this name?** Structural quality, theme, catalyst, liquidity, and setup context.
2. **Why now?** A point-in-time setup transition with exact evidence and freshness.
3. **Has it already moved?** Trigger identity, entry window, current distance, MFE/MAE, and anti-chase boundary.
4. **What does options activity actually add?** Execution-location quality, concentration, persistence, volatility/dealer context, and evidence grade—not an unlabeled “whale” narrative.
5. **What is the best expression?** Underlying versus defined-risk option structure, liquidity/slippage, Greeks, event exposure, scenario P&L, invalidation, and maximum loss.
6. **How reliable has this exact pattern been?** Point-in-time, regime- and horizon-conditioned calibration with transaction costs and no look-ahead.

The system must become better at **selectivity and timing**, not merely denser.

---

## 2. Evidence and uncertainty boundary

The public HTML endpoint and current live JSON could not be retrieved from the inspection environment during this investigation; repeated direct reads timed out or were inaccessible. Therefore this ruling does **not** claim to possess the exact live ASTS payload that produced the Chairman’s card.

The defect is nevertheless proven at the implementation-contract level:

- the Python and browser stance ladders can emit `get_ready` / “Almost ready” from recent washout plus upturn/squeeze plus no current reclaim;
- neither ladder accepts a prior trigger or setup-episode identity;
- the browser’s washout fallback treats any `entry_signal.status` containing the substring `buy` as washout evidence, so `buy_now` and `buy_soon` can manufacture L1 when direct washout evidence is absent;
- the `get_ready` branch ignores the canonical `entry_signal` timing vocabulary (`buy_now`, `partial`, `hold`, `extended`, `topping`, `exit`, `blocked`, and others);
- the in-favour branch excludes names whose recent-washout bit remains true, which prevents a normal washout setup from progressing cleanly into continuation while L1 persists;
- the off-hours branch can say “Base in place — waiting for the open” from nightly structure after the opportunity has already triggered or run;
- the page’s market-hours helper uses only Eastern clock minutes and no weekday/holiday calendar, so weekend/holiday freshness semantics can be wrong even though that is not required to explain the Chairman’s late-Friday observation.

ASTS itself rose 11.83% on 2026-09-02, with unusually high volume relative to adjacent sessions, before the Chairman observed it still presented as “Almost ready.” That market move is consistent with “already started,” but the exact internal path—late canonical `entry_signal`, absent VWAP/reclaim, off-hours skeleton, or a combination—requires a natural production payload receipt to distinguish.

This distinction is mandatory:

- **Defect class:** proven.
- **Exact ASTS branch inputs at observation time:** not captured by this session.
- **Required closure evidence:** post-fix natural regular-session and off-hours receipt containing the full ASTS card inputs, lifecycle output, and rendered copy.

---

## 3. Current capability ledger

| Capability | State | Ruling |
|---|---|---|
| Curated leader universe and nightly base context | `PROVEN_LIVE` / existing product substrate | Useful focus and identity layer; preserve. |
| Washout/reclaim, RVOL, VWAP, volume durability, higher lows, MTF, quality/trap legs | `BUILT_NOT_PROVEN` as a complete current-session board contract | Individual components exist; live semantic parity and current natural-session proof remain required. |
| Board-scoped live quotes and pulse health repair (#6105) | `BUILT_NOT_PROVEN` | Merged implementation; natural live-session dossier still owed under `WS-INTRADAY-FLOW-P0-RECOVERY`. |
| Per-root live options flow, NCP durability, enriched event badges | `BUILT_NOT_PROVEN` as an opportunity selector | Display works in existing estate, but predictive/decision value is not calibrated and signing remains soft except where direct NBBO fields are available. |
| OA-1T NBBO execution-location microstructure | `BUILT_NOT_PROVEN` | Merged zero-authority measurement contract; natural RTH proof and product consumption remain owed. |
| Dealer/GEX/flip/walls/expected move/skew/IV rank/OPEX context | `BUILT_NOT_PROVEN` / display context | Assumption-signed and useful as context; not an independently validated trade signal. |
| Six deterministic stance lanes | `BROKEN` for setup timing | Present, but memoryless and semantically contradictory after activation. |
| Trigger persistence and setup episode lifecycle | `NOT_BUILT` | Required moat and P0/P1 direction. |
| Explicit “already moving / do not chase” board state | `PARTIAL` elsewhere, `NOT_BUILT` here | Canonical entry gauge already knows it; Intraday Flow discards it. |
| Exact option-trade/strategy expression and executable liquidity model | `NOT_BUILT` on this board | Later wave only after candidate/timing correctness. |
| Point-in-time pattern calibration by regime/horizon | `PARTIAL` | Forward ledger exists, but no accepted setup-episode calibration or promotion gauntlet. |
| Options-derived rank/score/trade authority | `REJECTED_BY_DESIGN` until promotion | Must remain disabled until replay, cost, calibration, and forward gates pass. |

---

## 4. Qualitative effectiveness assessment

These scores are an architecture/product assessment, not measured production KPIs.

| Dimension | Current assessment | Why |
|---|---:|---|
| Universe relevance | 7.5/10 | Focused leaders and thematic names are much better than scanning every noisy contract. |
| Data breadth | 7.5/10 | Price/volume/flow/dealer/volatility context is unusually broad for one page. |
| Data truth and observability | 6/10 | Source clocks and degraded semantics are good, but PR-4 natural proof remains open and live endpoint inspection was unavailable here. |
| Flow interpretation honesty | 6/10 | Soft labels and authority ceilings exist, yet the board still leans heavily on approximate signed premium and badges without full execution-location/persistence treatment. |
| Timing correctness | 3/10 | No setup memory; ASTS-class regression is structurally possible. |
| Opportunity selectivity | 4/10 | Confluence helps, but lane assignment and RVOL-centric ordering do not yet answer “best opportunity now” with calibrated evidence. |
| Executability | 3/10 | No complete option-expression, spread/slippage, scenario, or event-risk workflow. |
| Learning/calibration | 4/10 | A forward ledger exists, but episode outcomes, false-arm/late-call metrics, and point-in-time promotion are not mature. |
| Product clarity | 6/10 | Plain-language lanes and bilingual presentation are valuable, but timing contradictions undermine trust. |

**Overall ruling: approximately 5.5/10 today.** It is a good radar and research surface, not yet a decision-grade opportunity system.

---

## 5. ASTS defect — root cause and immediate semantic law

### 5.1 Current failure shape

A recent washout is sticky for a lookback window. Reclaim is a current-bar/current-session fact. When price pulls back under the reclaim threshold, VWAP is absent, live bars are unavailable, or the page is off-hours, L2 can be false while L1 remains true. The stance ladder then re-enters `get_ready`, even though another canonical owner may already classify the name as `buy_now`, `partial`, `hold`, `extended`, `topping`, or `exit`.

This is a stage-regression bug:

```text
FORMING -> TRIGGERED/ACTIVE -> memoryless snapshot -> FORMING
```

The browser fallback adds a second defect:

```text
entry_signal.status contains "buy" -> infer L1 washout
```

A timing result is being used as evidence that a separate structural precursor occurred. That is circular and can make a “buy now” status help generate “almost ready.”

### 5.2 P0 law

Within the current snapshot-only contract, lifecycle must be adjudicated **before** the six-lane stance ladder.

Canonical status groups for P0:

```text
FORMING
  buy_soon | await_confluence | watch | bounce_wait

ACTIVE_WINDOW
  buy_now | partial

ALREADY_MOVING
  hold | extended | wait_pullback | topping

FAILED_OR_BLOCKED
  exit | avoid | blocked

UNKNOWN
  missing or unrecognized
```

Price above the canonical `chase_above` / don’t-chase line overrides `FORMING` to `ALREADY_MOVING` when current price and boundary are both finite.

Rules:

1. `Almost ready` is eligible only for explicit `FORMING` timing plus direct L1 evidence plus the existing structure/quality conditions.
2. `ACTIVE_WINDOW` may still reach `Buy now` if live confluence satisfies the existing action gate; it may never fall back to `Almost ready`.
3. `ALREADY_MOVING` may never show `Almost ready`; use the existing `watch` lane with explicit anti-chase copy unless the pre-existing take-profit rule has stronger evidence.
4. `FAILED_OR_BLOCKED` may never show `Almost ready`; use `stand_aside` unless a more conservative existing rule applies.
5. `UNKNOWN` cannot grant a positive timing label. Unknown remains disclosed and non-positive.
6. Remove the substring-`buy` and squeeze fallbacks that fabricate washout. Direct washout/reclaim or bounded drawdown/recovery evidence owns L1; otherwise L1 is null.
7. Apply the same logic in Python, browser template, and generated site. No source/render semantic split.
8. Apply the same lifecycle guard during off-hours. “Waiting for the open” is forbidden after activation, extension, failure, or an anti-chase breach.
9. Add weekday-aware session semantics now if it fits the bounded change without creating a market-calendar owner. Full exchange-holiday ownership may be a later canonical calendar integration; weekends must not appear live.
10. Preserve the six existing lanes in P0. The anti-chase state is a `watch` presentation with additive `timing_state`; do not create a seventh incompatible lane merely for wording.

Required English copy:

- Active but live confirmation unavailable: **“Entry window already opened — wait for live confirmation.”**
- Already moving: **“Already moving — wait for a reset; do not chase.”**
- Failed/blocked: **“Setup is no longer actionable.”**
- Timing unknown: **“Timing unavailable — no positive setup claim.”**

Equivalent natural Chinese copy is required, not machine-literal fragments.

### 5.3 P1 lifecycle law

P0 prevents obvious contradictions using the already-owned entry gauge. It does not create durable setup memory. P1 must extend the existing event/ledger plane with an episode contract rather than inventing a second store:

```text
FORMING -> ARMED -> TRIGGERED -> CONFIRMED -> EXTENDED
                  \-> FAILED
TRIGGERED/CONFIRMED/EXTENDED/FAILED -> RESET or EXPIRED
RESET/EXPIRED -> a new setup epoch only after a new qualifying precursor
```

Minimum episode identity:

```text
setup_id
symbol
setup_family/version
setup_epoch_started_at
precursor_event_at
armed_at
triggered_at
trigger_price
confirmed_at
extended_at
failed_at
reset_at
reset_reason
last_state
last_state_at
mfe_pct / mfe_at
mae_pct / mae_at
source_clock_set
correction/version metadata
```

Monotonicity law:

- once `triggered_at` is set, the same `setup_id` can never become `FORMING` or `ARMED` again;
- a reset requires an explicit, versioned reset rule and emits a new state transition;
- a later washout or new precursor creates a new `setup_id`; it never erases the old episode;
- corrections append/revise through the existing correction-safe contract; they do not silently rewrite history;
- no later EOD field may be backfilled into an earlier point-in-time decision row unless it was available at that earlier timestamp.

---

## 6. Options-data research — what is useful, what is dangerous

### 6.1 Options flow is conditionally informative

Research supports the proposition that some option activity contains information, but not the shortcut that any large premium print is predictive.

Historically documented examples include:

- buyer-initiated **opening** put/call volume ratios predicting short-horizon underlying returns in Pan and Poteshman;
- option-to-stock volume relationships and informed-trading models under information asymmetry;
- call-put implied-volatility deviations, individual-stock volatility smirk, volatility demand, and implied-versus-realized volatility spreads carrying cross-sectional information in particular samples;
- evidence that option quotes often adjust to stock information rather than universally leading it.

The product implication is not to choose one paper as universal truth. It is to classify flow by mechanism and validate each mechanism at its own horizon.

### 6.2 Trade execution location is not trader intent

Direct NBBO comparison can truthfully say where a print occurred:

- at/near ask;
- at/near bid;
- inside spread;
- outside a valid spread;
- unclassifiable because quotes were stale, locked/crossed, absent, or future-dated.

It cannot by itself prove:

- customer versus dealer;
- opening versus closing;
- institutional identity;
- economic bullishness/bearishness of a multi-leg package;
- whether stock or another option leg neutralized the apparent exposure.

The existing OA-1T measurement contract correctly keeps these as zero-authority execution-location facts. Intraday Flow should consume their quality/coverage fields, not relabel them as proven “smart money.”

### 6.3 Open interest is delayed state, not an intraday intent oracle

Official open-interest mechanics support only day-over-day inference:

- both sides opening increases OI;
- both sides closing decreases OI;
- one side opening and one closing leaves OI unchanged.

Therefore `volume > OI` is an unusual-activity descriptor, not proof of new opening demand. Next-session OI change may confirm persistence at the exact contract, but only with same-vintage contract identity and explicit timing. No intraday opening/closing claim should be manufactured from current volume alone.

### 6.4 Complex orders and stock-tied trades contaminate naive direction

Options packages may contain many option legs and stock legs and execute for a net package price. Reading each leg as an independent bullish/bearish bet can invert the strategy.

The normalized event layer must preserve exchange condition/package evidence and classify:

```text
SINGLE_LEG_CLEAN
SINGLE_LEG_UNCERTAIN
MULTI_LEG_IDENTIFIED
STOCK_TIED_IDENTIFIED
POSSIBLE_PACKAGE
EXCLUDED_FROM_DIRECTIONAL_READ
```

Unresolved package legs may still contribute to gross activity and liquidity context, but not to directional conviction.

### 6.5 Gamma/dealer maps are useful context, not deterministic forecasts

Dealer gamma estimates are model-dependent because public chain data does not reveal each participant’s complete signed inventory or hedge book. Research and market-practitioner tools support plausible relationships between gamma sign, hedging pressure, liquidity, momentum/reversal, and late-day behavior. Other empirical work cautions that aggregate 0DTE positioning can be balanced and small relative to futures liquidity, especially when offsets across expiries and products are included.

The board may use GEX/flip/walls/magnets to answer:

- Is price near a modeled hedging inflection?
- Is the path likely to encounter a dense call/put wall?
- Is the expected-move budget already consumed?
- Is OPEX/pinning context relevant?

It may not say a wall “will hold” or a gamma regime “will force” direction without calibrated evidence.

### 6.6 Volatility can be the opportunity even when direction is not

Directional flow, realized-volatility opportunity, and option-return opportunity are different jobs.

Useful volatility dimensions include:

- IV level and percentile/rank;
- term structure and event kink;
- skew/smirk and risk-reversal shape;
- implied-versus-realized volatility gap;
- vol-of-vol and surface change;
- expected move consumed versus remaining;
- earnings/catalyst clock and likely IV crush;
- cross-sectional volatility demand and disagreement.

A recent earnings-event study is a useful warning: a surface shape can predict larger absolute price moves while long straddles still lose because the options were already too expensive. The system must model both **move probability** and **price paid for convexity**.

### 6.7 Look-ahead and multiple-testing risk are first-order product risks

Recent options research has shown that spectacular backtests can be created by filters that use information unavailable at trade time. The Intraday Opportunity OS must therefore record field-level availability timestamps and reconstruct the exact information set.

Forbidden research shortcuts:

- using final daily OI before it was published;
- using a revised earnings/corporate-action calendar without vintage control;
- selecting contracts using future liquidity/survival;
- grading a setup using a later finalized bar while pretending it was intraday;
- choosing thresholds on the full sample and reporting the same sample as validation;
- ignoring bid/ask, fees, early assignment, exercise, and fill uncertainty;
- evaluating hundreds of strategy variants without false-discovery controls.

---

## 7. Strategy and opportunity taxonomy

The board should not collapse every opportunity into “calls bullish / puts bearish.” It should identify the economic job first.

### 7.1 Underlying directional continuation/reversal

Examples:

- washed-out leader reclaim with durable underlying demand;
- base breakout/continuation with confirmed volume and clean overhead path;
- failed breakdown/reversal;
- event-driven gap continuation or exhaustion;
- relative-strength leader versus sector/market;
- dealer-level break, pin, or rejection as context.

Options activity is corroboration or contradiction, never the sole source of setup identity at current authority.

### 7.2 Long-volatility opportunities

Examples:

- implied volatility cheap versus forecast realized volatility;
- event uncertainty underpriced after accounting for surface shape;
- convexity demand appearing before underlying confirmation;
- dispersion or correlation dislocation;
- skew normalization or tail-risk demand.

Required output includes expected move, premium at risk, theta, vega, breakevens, and scenario distribution—not only a direction label.

### 7.3 Short-volatility / carry opportunities

Examples:

- implied volatility rich versus point-in-time realized forecast;
- post-event crush;
- range/pin regimes with stable liquidity;
- skew or term-structure mean reversion.

These require strict defined-risk treatment, gap/event exclusions, assignment behavior, and loss-tail analysis. They should not enter the first execution wave.

### 7.4 Relative-value and structure opportunities

Examples:

- calendar/diagonal term-structure dislocation;
- vertical skew relative value;
- risk reversal;
- butterfly/condor around modeled distribution;
- stock-option or option-option relative value;
- sector/index versus single-name dispersion.

These are package-level opportunities; leg-by-leg flow direction is inadequate.

### 7.5 Hedging and portfolio-protection opportunities

The board can later answer:

- where convexity is cheapest for a known portfolio exposure;
- whether a collar, put spread, or index hedge is more efficient;
- expected protection under defined stress scenarios;
- carry cost and roll schedule.

This is distinct from alpha ranking and requires portfolio context/permission boundaries.

---

## 8. Competitive-job synthesis

Current options platforms tend to specialize in four jobs:

1. **Raw tape and alerts:** fast unusual-flow filters, sweeps, blocks, repeated prints, dark-pool/context feeds.
2. **Market-impact and dealer maps:** gamma/delta/charm estimates, walls, flips, real-time hedge-pressure proxies.
3. **Surface/chain analytics:** volatility, skew, Greeks, historical chains, event context, scanners.
4. **Strategy testing/expression:** intraday backtests, historical strategy matching, trade construction and payoff analysis.

Mastermind should not imitate proprietary brands or copy their text/design. Its differentiated moat should be:

> **A correction-safe opportunity lifecycle that fuses first-party/canonical market evidence, explains why the opportunity is early or late, selects an executable expression, and learns point-in-time whether that exact pattern improves decisions.**

Raw alerts are abundant. Trustworthy episode memory, cross-surface semantic consistency, evidence grading, and calibrated “why now / already moved” judgment are rarer and more defensible.

---

## 9. Frozen Intraday Opportunity OS architecture

### 9.1 Plane A — canonical truth and source clocks

Extend current owners only:

- underlying quote/tape clock;
- intraday bar/pulse clock;
- live options trade/quote clock;
- enriched-flow clock;
- EOD chain/OI/dealer clock;
- corporate-event/calendar clock;
- setup-episode clock;
- outcome/calibration clock.

Every displayed fact carries source, as-of, session, freshness, coverage, and correction/version metadata. One fresh clock may not hide another stale clock.

No second collector, quote store, options store, scheduler, event bus, publication plane, or health database.

### 9.2 Plane B — normalized options event intelligence

For each contract/event or package candidate, preserve:

```text
root / OCC identity / expiry / strike / right
trade timestamp / exchange / condition / sequence
price / size / premium
contemporaneous NBBO / quote age / spread / quote validity
execution location and coverage
DTE / moneyness / Greeks and model provenance
underlying spot and clock
volume / prior OI vintage / next OI confirmation when available
single-leg / complex / stock-tied classification
repeat/lattice/sweep/group identity
source and correction metadata
```

Derived facets:

- direct execution-location balance with valid-coverage denominator;
- premium normalized by root, contract, DTE, moneyness, and time-of-day baselines;
- contract concentration and repeated participation;
- delta-, gamma-, and vega-dollar exposure with model provenance;
- DTE and moneyness concentration;
- multi-exchange sequence and duration;
- next-day OI persistence confirmation;
- package uncertainty/exclusion.

All remain descriptive until calibrated.

### 9.3 Plane C — setup lifecycle and episode memory

The lifecycle contract in §5.3 is the timing owner for Intraday Flow. It consumes existing deterministic setup context and writes through the existing event/ledger plane.

It must answer:

- first observed;
- armed;
- trigger condition and exact timestamp;
- confirmation condition;
- current distance from trigger/entry/chase/invalidation;
- MFE/MAE and elapsed time;
- extended/failed/reset/expired;
- whether a fresh epoch exists.

This plane fixes the ASTS problem permanently. P0’s status guard is only the immediate vertical correction.

### 9.4 Plane D — opportunity evidence card, not an opaque score

Before any fused probability is validated, expose seven independent facets:

1. **Setup quality** — deterministic structural evidence.
2. **Timing state** — lifecycle and distance to trigger/chase/invalidation.
3. **Underlying confirmation** — RVOL, durability, VWAP/reclaim, higher lows, relative strength.
4. **Options-flow quality** — NBBO coverage, concentration, persistence, package uncertainty.
5. **Volatility/dealer context** — IV/skew/term structure/expected move/GEX, with assumption labels.
6. **Event and gap risk** — earnings, launches, macro releases, corporate actions, known catalysts.
7. **Executability** — underlying/contract liquidity, spread, depth, slippage, max risk.

Each facet has:

```text
state: positive | mixed | negative | unknown
confidence/evidence grade
reason codes
source clocks
missing-data penalty
human-readable explanation
```

Do not average unknown into neutral. Do not turn seven facets into a universal 0–100 conviction number until a preregistered calibration wave earns it.

### 9.5 Plane E — candidate selection

Candidate admission is deterministic and conservative:

- fresh required truth;
- eligible lifecycle state;
- minimum underlying liquidity;
- explicit invalidation;
- no unresolved hard event/market-data conflict;
- options context optional, not mandatory;
- a flow-only event cannot create the setup at current authority.

The board’s primary views become:

```text
NOW            triggered/confirmed and not above anti-chase boundary
FORMING        armed/near trigger with explicit remaining condition
ALREADY MOVED  triggered/extended or above anti-chase boundary
FAILED/RESET   closed episodes, available for learning but not opportunity ranking
```

### 9.6 Plane F — option-expression engine

Only after a candidate exists, evaluate expressions:

- stock / no option;
- long call/put;
- debit vertical;
- calendar/diagonal;
- defined-risk event structure;
- no-trade.

Inputs:

- target horizon/distribution;
- catalyst timing;
- surface/term/skew;
- live spreads/depth and realistic fill model;
- Greeks and scenario paths;
- max risk, breakevens, assignment/exercise risk;
- user risk constraints.

Output is a comparison table, not an order. No naked short-vol structure in initial waves.

### 9.7 Plane G — premium product experience

Each opportunity card must show, in this order:

1. lifecycle badge and elapsed time;
2. plain-language thesis: why this name, why now;
3. exact trigger/entry zone, current price, anti-chase, invalidation;
4. what changed since the prior state;
5. underlying evidence and contradictions;
6. options-flow quality and exact caveats;
7. volatility/dealer/event path map;
8. expression choices and scenario risk when available;
9. source/freshness strip;
10. episode timeline and outcomes.

Default density should answer the decision in seconds; details expand on demand.

Material UI work must provide distinct dark command-center and light research-workspace treatments, EN/ZH parity, desktop 1440 and mobile 390 evidence, and all degraded/null/stale/conflict states.

### 9.8 Plane H — transition alerts

Alert on **state transitions**, not every large print:

- armed;
- trigger;
- confirmation;
- anti-chase breach;
- invalidation/failure;
- reset/new epoch;
- material flow-quality change;
- event-risk change.

Deduplicate by `setup_id + transition`. A repeated print may enrich evidence but does not create repeated “new opportunity” alerts.

### 9.9 Plane I — point-in-time learning and promotion

Required evaluation cohorts:

- setup family/version;
- lifecycle state at decision;
- market/sector/volatility/gamma regime;
- event versus non-event;
- DTE/moneyness/liquidity bucket;
- flow-quality grade and package certainty;
- horizon: intraday, close, 1d, 5d, 10d, 21d;
- underlying outcome and exact option outcome separately.

Required metrics:

- coverage and abstention rate;
- precision/recall for trigger and continuation definitions;
- false-arm rate;
- late-call/anti-chase violation rate;
- MFE, MAE, time to MFE/MAE;
- expectancy and tail loss after costs;
- probability calibration/Brier/log loss where probabilities exist;
- spread/slippage/fill sensitivity;
- stability across walk-forward folds and regimes;
- incremental value versus underlying-only controls;
- user behavior: opened, dismissed, acted, chased, returned, and whether evidence changed the decision.

Promotion sequence remains:

```text
measurement
-> descriptive display
-> research candidate
-> calibrated family
-> forward shadow
-> promotion proposal
-> separately accepted downstream authority
```

No LLM summary, badge count, premium magnitude, or historical backtest can skip this sequence.

---

## 10. Ordered implementation program

### P0 — lifecycle truth / ASTS-class correction

**Observable capability:** a setup that is active, already moving, failed, blocked, or above its anti-chase line can no longer appear as “Almost ready,” in live or off-hours rendering.

Owned paths:

- `engine/intraday_flow.py`
- `scripts/build_intraday_flow.py`
- `templates/intraday_flow.html.j2`
- generated `site/intraday_flow.html`
- focused tests only

Required proof:

- test-first red for active/late/failed/unknown states;
- Python/JS parity;
- template/site byte-semantic parity;
- ASTS fixture reproducing the defect class;
- weekend time test if included;
- natural regular-session and off-hours browser proof on real data;
- no regression in six lane counts, source clocks, EN/ZH, dark/light, desktop/mobile;
- exact payload receipt showing ASTS or another naturally activated name cannot regress.

### P1 — durable setup episode registry

**Observable capability:** every setup has a stable episode timeline and cannot regress without an explicit reset/new epoch.

Extend the existing event/ledger plane; no new lifecycle store.

### P2 — flow-quality evidence consumption

**Observable capability:** the card distinguishes clean NBBO-covered single-leg activity, uncertain/package flow, baseline-normalized concentration, and next-OI persistence.

Consume OA-1T and current live-flow owners; do not clone them.

### P3 — opportunity board experience

**Observable capability:** `Now`, `Forming`, and `Already moved` views make trigger, anti-chase, invalidation, evidence, contradictions, and freshness visible across all required states and breakpoints.

### P4 — point-in-time evaluation harness

**Observable capability:** replayed episodes and exact options/underlying outcomes produce cost-aware, regime-conditioned calibration and late-call/error metrics.

### P5 — bounded expression engine

**Observable capability:** one validated candidate can compare stock/no-trade versus one or more defined-risk options expressions using live executable inputs and scenario risk.

### P6 — calibrated promotion proposal

Only families that pass preregistered replay, walk-forward, cost, stability, and forward-shadow gates may request greater authority. This is a new Sol/Chairman decision, not an automatic consequence of P0–P5.

---

## 11. No-rebuild and non-goals

This program must not create:

- another options collector, OPRA/ThetaData store, live-flow engine, GEX engine, event bus, scheduler, health store, publication plane, candidate lifecycle store, queue, score, ranker, Prophet bridge, alert bus, or execution system;
- a second `entry_signal` timing owner;
- a generic “institutional flow” claim from at-ask prints, volume/OI, sweeps, or premium size;
- directional interpretation of unresolved complex/stock-tied packages;
- a universal options score before calibration;
- retroactive point-in-time history using future OI, revised events, or finalized bars;
- copied competitor code, proprietary corpus, branding, text, or visual identity;
- automatic trade/order/size authority;
- a broad design migration inside the P0 bugfix.

---

## 12. P0 acceptance and stop condition

P0 is acceptable only when all are true:

1. The exact current source and collision census are refreshed before implementation.
2. Tests prove `Almost ready` is impossible for `ACTIVE_WINDOW`, `ALREADY_MOVING`, `FAILED_OR_BLOCKED`, unknown timing, and price above `chase_above`.
3. Explicit forming states can still reach `Almost ready` when direct precursor evidence exists.
4. `buy_now` may still reach `Buy now` when the live action gate is genuinely satisfied.
5. Browser and Python return the same lifecycle/lane semantics.
6. The page no longer infers washout from the substring `buy` or from squeeze alone.
7. Null timing and stale/missing inputs stay null/non-positive.
8. English and Chinese copy, dark/light, 1440/390, regular-session/off-hours/degraded states are verified.
9. Focused tests and repository binding checks conclude green on the immutable head.
10. A non-author exact-head review confirms no duplicate owner or authority promotion.
11. Real production input passes through the real build/publication path to the visible page.
12. The existing PR-4 natural live-session dossier obligation is preserved; this change does not falsely close it.

**Stop after this one capability.** Do not absorb persistent episode storage, flow-quality UI, scoring, strategy construction, alerts, or promotion into the P0 PR.

---

## 13. Research references

Primary/authoritative references used for this architecture include:

- Pan, J. and Poteshman, A., *The Information in Option Volume for Future Stock Prices*.
- Easley, D., O’Hara, M., and Srinivas, P., *Option Volume and Stock Prices: Evidence on Where Informed Traders Trade*.
- Johnson, T. and So, E., work on option-to-stock volume and future returns.
- Cremers, M. and Weinbaum, D., *Deviations from Put-Call Parity and Stock Return Predictability*.
- Xing, Y., Zhang, X., and Zhao, R., *What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?*
- Ni, S., Pan, J., and Poteshman, A., *Volatility Information Trading in the Option Market*.
- Goyal, A. and Saretto, A., *Cross-section of Option Returns and Volatility*.
- Muravyev, D., Pearson, N., and Broussard, J., work on whether option markets lead stock markets.
- *Too Good to Be True: Look-Ahead Bias in Empirical Options Research*, Review of Financial Studies.
- Options Industry Council educational material on open interest.
- Cboe public research/material on 0DTE market structure, complex orders, and trade conditions.
- ThetaData public documentation for OPRA trades/quotes, NBBO, OI, Greeks, and historical/streaming data.

Commercial-product pages from ORATS, SpotGamma, Unusual Whales, and LiveVol were reviewed only to understand user jobs and product categories. Their proprietary claims are not treated as independent efficacy proof, and this architecture requires original implementation and design.
