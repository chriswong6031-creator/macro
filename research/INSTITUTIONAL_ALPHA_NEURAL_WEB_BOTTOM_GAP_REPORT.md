# Institutional Alpha Lessons for Neural Web Durable-Bottom Selection

**Status:** Research report and implementation gap map.  
**Prepared:** 2026-07-05.  
**Scope:** What institutional investors and systematic firms do to create alpha that is **not already covered** by the current Macro Dashboard / Neural Web / durable-bottom research stack, and how to translate those lessons into a better stock-selection system for durable bottoms.

---

## 0. Do Not Re-Write What We Already Have

This report intentionally avoids re-proposing the existing system:

- Neural Web registry, world state, spine federation, reliability kernel, confluence graph, constitution, cortex, and admin/committee surfaces are already built or documented in `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`.
- Existing bottom/rebound sensor taxonomy already covers exhaustion, trigger, repair, sponsorship, anti-chase, COILED, RS-repair, confluence tiers, and same-bar-fill discipline in `research/NEURAL_WEB_BOTTOM_REBOUND_SIGNAL_EXPANSION_REPORT_FOR_CLAUDE.md`.
- The current US board problem map already covers fixed-width fill pressure, score/timing inversion, variable-width lanes, edge-vs-entry separation, and board ledger needs in `research/US_STOCKS_ENGINE_PROBLEMS_FOR_FABLE.md` and `research/ENGINE_FIX_MASTERPLAN.md`.
- The broad institutional roadmap already covers survivorship, PIT fundamentals, trial ledgers, incremental IC, cost/capacity, and free-data factor expansion in `research/INSTITUTIONAL_ROADMAP.md` and `research/QUANT_FACTOR_EXPANSION.md`.
- The S7 RS-repair study already refuted plain stock/SPY repair as a hard bottom signal and kept cohort-relative repair in phase-0 in `research/species/s7_rs_repair_phase0/`.

So the target here is narrower and more useful: **what institutional desks would add on top of our current machinery to decide which bottom setups deserve capital, which deserve a watchlist slot only, and which are traps.**

In plain English: the missing layer is not "more indicators." It is **who is forced to sell, who is beginning to sponsor the name, what event can blow up the setup, what crowding/borrow/options pressure says about the path, and how the trade should be sized and managed after entry.**

---

## 1. How Institutions Create Alpha: The Useful Translation

Institutional alpha is rarely one magic signal. It usually comes from a repeatable stack:

1. **A structural reason for mispricing.**
   Forced sellers, slow information diffusion, mandate constraints, benchmark pressure, leverage constraints, liquidity shocks, investor underreaction, crowded positioning, or an accounting/fundamental fact that the market prices too slowly.

2. **A measurement advantage.**
   Better data, cleaner point-in-time reconstruction, faster parsing, superior entity mapping, or a way to see the same public information with less delay and less noise.

3. **A portfolio implementation advantage.**
   Market neutrality, factor neutrality, risk budgeting, position sizing, execution cost control, borrow awareness, capacity control, and concentration management.

4. **A learning loop.**
   Every signal is logged, attributed, compared to a baseline, and either promoted, demoted, retired, or restricted to specific regimes.

This is consistent with the institutional literature. AQR's style framework emphasizes that many returns marketed as alpha are really robust styles such as value, momentum, carry, and defensive, and that implementation needs hedging, cost control, leverage/shorting discipline, and risk management rather than simple long-only picks ([AQR, Investing With Style](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/JOIM-Investing-With-Style.pdf)). BlackRock describes systematic equity as combining traditional accounting signals with alternative data and technology to evaluate thousands of securities ([BlackRock systematic investing](https://www.blackrock.com/us/individual/investment-ideas/systematic-investing)). Two Sigma describes its edge as scientific, technology- and data-science-driven discovery in a data-rich market ([Two Sigma Investment Management](https://www.twosigma.com/businesses/investment-management/)).

The practical lesson for us:

> Neural Web should not ask, "What one signal finds bottoms?" It should ask, "Which economic mispricing mechanism is this bottom candidate expressing, and has that mechanism earned trust in this regime?"

---

## 2. Institutional Mental Model for Durable Bottoms

An institutional desk would not define a durable bottom as "oversold plus oscillator cross." It would define it as a **temporary transfer of shares from forced or exhausted sellers to better-capitalized buyers, followed by evidence that price no longer needs forced-selling discounts to clear.**

That means every candidate bottom has four institutional questions:

1. **Was the decline caused by forced supply or permanent impairment?**
   A fund-flow liquidation, index/ETF unwind, sector panic, options hedging shock, or tax-loss/mandate pressure is potentially reversible. A broken balance sheet, dilution, guidance collapse, fraud, or refinancing wall is not.

2. **Has supply been absorbed?**
   The stock stops making easy lows, reclaims a prior breakdown, holds a retest, improves relative to its own cohort, and trades with acceptable liquidity.

3. **Is there new sponsorship?**
   New holders, rising ownership breadth, sector/theme rotation, insider open-market buying, buyback support, positive revisions, post-earnings drift, or options/borrow pressure showing shorts are no longer in control.

4. **Is the setup tradeable?**
   Entry is close enough to invalidation, the event calendar is not hostile, liquidity supports the intended size, borrow/options conditions are not pathologically crowded, and the position does not duplicate the rest of the book.

This reframes durable-bottom selection into five output scores, not one:

- **Rebound timing:** probability of a 10- to 21-day bounce.
- **Durability:** probability the low holds over 40- to 63-day windows.
- **Sponsorship:** evidence that real capital is accumulating or at least no longer liquidating.
- **Fragility/veto:** event, balance-sheet, borrow, dilution, or liquidity hazards.
- **Tradeability:** expected slippage, capacity, stop distance, and correlation with current book.

The current system has strong timing and exhaustion bones. The institutional gap is mostly **sponsorship, forced-flow diagnosis, fragility, and trade design.**

---

## 3. What Institutions Would Add That We Mostly Do Not Have

### 3.1 Ownership-Pressure Map

**Institutional behavior:** Long/short equity and pod shops study who owns a stock, which holders are under pressure, and whether the shareholder base is broadening or narrowing. This matters because durable bottoms often form when forced sellers finish and patient buyers step in.

**Why it matters for bottoms:** A chart can show exhaustion, but ownership data can explain whether the exhaustion is mechanical. Coval and Stafford show that mutual-fund outflows can force sales in overlapping holdings, causing price pressure; liquidity providers to distressed funds can earn abnormal returns, and some forced trades are predictable ([NBER asset fire sales](https://www.nber.org/system/files/working_papers/w11357/w11357.pdf)).

**What we should build:**

- `ownership_breadth_delta_q`: quarter-over-quarter change in number of 13F holders.
- `ownership_entropy_delta_q`: change in holder concentration, using Herfindahl/entropy.
- `top_holder_flow_pressure`: estimated pressure from top holders whose public fund vehicles saw outflows or underperformance.
- `holder_overlap_fire_sale`: overlap with funds/ETFs/themes under recent drawdown/outflow pressure.
- `sponsor_quality_delta`: change in ownership by long-horizon managers versus high-turnover/crowded holders.

**Free data path:**

- SEC 13F data sets are quarterly, extracted from XML filings and flattened for public use ([SEC 13F data sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)).
- 13F is lagged and incomplete, so this is not a timing trigger. It is a **sponsorship and vulnerability context**.

**Neural Web role:** display/shadow first. It should never hard-gate entry until it proves incremental IC versus existing COILED/RS/confluence signals.

**Institutional read:**

- Good bottom: ownership breadth stopped falling, concentration is not getting worse, and pressured holders are likely finished.
- Bad bottom: ownership keeps narrowing, top holders overlap with distressed strategies, and the bounce is mostly retail/short-covering noise.

### 3.2 Fund-Flow and ETF-Flow Pressure

**Institutional behavior:** A desk asks, "Who has to sell tomorrow even if they do not want to?" This is different from normal price momentum.

**Bottom-specific thesis:** Durable bottoms are more likely when the forced-flow impulse has already peaked. The system should distinguish a stock down because fundamental expectations are collapsing from a stock down because the holder base was forced to reduce exposure.

**Metrics:**

- `etf_flow_pressure_5d`: sum over ETFs: estimated flow dollars x stock weight / stock ADV.
- `theme_flow_pressure_20d`: same, but across thematic baskets/sector ETFs.
- `fund_distress_overlap_q`: lagged 13F holder overlap with funds experiencing performance/outflow stress.
- `forced_seller_exhaustion`: pressure was high, then decelerated, while price reclaimed a breakdown.
- `liquidity_provider_setup`: high prior pressure + improving absorption + near-low entry.

**Data reality:**

- Full mutual fund flows and holdings are cleaner with paid CRSP/EPFR/Lipper data.
- Free approximations are still useful: ETF holdings and ETF flow proxies, 13F lagged holdings, public fund returns, and ADV.

**Implementation note:** This should be a **mechanism classifier**, not a score weight. Label the candidate:

- `mechanism=forced_flow_reversal`
- `mechanism=information_repricing`
- `mechanism=short_covering`
- `mechanism=unknown`

Then let Neural Web learn which mechanisms work in which regimes.

### 3.3 Ownership Breadth as Sponsorship, Not Just Institutional Percent Held

**Institutional behavior:** Institutions care about the composition and breadth of holders, not just "institutional ownership is high." High institutional ownership can mean sponsorship, but it can also mean crowding.

The Chen, Hong, and Stein breadth-of-ownership work is directly relevant because it frames ownership breadth as information about demand constraints and future returns ([Jeremy Stein publication page](https://stein.scholars.harvard.edu/publications/breadth-ownership-and-stock-returns)).

**Metrics:**

- `breadth_level`: number of distinct institutional holders normalized by float/market cap.
- `breadth_delta`: change in distinct holders.
- `breadth_reversal`: prior breadth collapse followed by stabilization.
- `concentration_hhi`: holder concentration.
- `crowding_top10_pct`: percent of institutional shares held by top 10 holders.
- `sponsorship_turn`: breadth delta positive while price is still near the low.

**Durable-bottom use:**

- Positive: breadth has stopped declining before price fully recovers.
- Negative: price bounces but breadth continues to contract.

**Caveat:** 13F is quarterly and delayed. Treat it as **durability context**, not entry timing.

### 3.4 Short-Interest and Borrow Pressure, Interpreted Correctly

**Institutional behavior:** A high short interest ratio is not automatically bullish. It can mean overvaluation, structural fraud concerns, broken financing, or a possible squeeze. Institutions separate **informed shorts** from **crowded shorts vulnerable to covering**.

The academic evidence is mixed. Asquith, Pathak, and Ritter caution that many short-interest return patterns are not robust across weighting schemes and periods ([SSRN short interest study](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=532993)). FINRA does provide short-interest reporting twice monthly ([FINRA short interest reporting](https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest)).

**Metrics:**

- `si_pct_float`: short interest as percent of float.
- `si_delta_2prints`: two-report change.
- `days_to_cover`: short interest / average volume.
- `short_covering_risk`: high SI + improving RS + reclaim + rising volume.
- `informed_short_warning`: high SI + deteriorating fundamentals + negative revisions + failed reclaim.
- `borrow_fee_z` and `utilization_z` if paid borrow data becomes available.

**Bottom use:**

- Bullish only when high short interest is paired with **absorption and repair**.
- Bearish when high short interest is paired with **fundamental deterioration or dilution risk**.

**Neural Web role:** split into two labels:

- `short_squeeze_fuel`
- `informed_short_fragility`

Do not average them together.

### 3.5 Options-Surface Panic and Dealer Positioning

**Institutional behavior:** Options desks look at skew, term structure, put demand, open interest, dealer gamma, strike concentration, and vol risk premium. They ask whether hedging flows are amplifying downside or whether the panic premium has peaked.

OCC publishes market data categories including daily volume, open interest, stock-loan volume, and volume by account type ([OCC market data](https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/daily-volume)). Our repo already has some options/GEX/IV-spread machinery, but it is not yet a dependable scored bottom selector.

**Metrics to add or formalize around bottom candidates:**

- `put_volume_z`: put volume versus trailing history.
- `put_call_oi_z`: OI-based put/call imbalance.
- `skew_percentile`: downside-vol premium percentile.
- `iv_rv_spread_z`: implied versus realized vol gap.
- `downside_oi_wall`: put OI concentrated below spot.
- `gamma_flip_distance`: distance to estimated dealer gamma flip.
- `vol_panic_peak`: skew/put demand high but no longer rising.
- `post_panic_vol_crush_risk`: IV too high; equity bounce may happen but options expression is poor.

**Bottom use:**

- Positive: panic premium peaked, price reclaimed, shorts/options hedgers may need to cover.
- Negative: downside OI/gamma remains a mechanical pressure source and price is below dealer-sensitive strikes.

**Important:** options flow should be a **path and sizing input**, not a claim that a stock is fundamentally better.

### 3.6 Event-Risk Calendar and Dilution Hazard

**Institutional behavior:** A bottom setup is not just a price pattern; it is a trade exposed to events. Institutions check earnings, guidance, lockups, offerings, credit events, index changes, litigation, FDA dates, convertible maturities, and buyback windows.

**Metrics:**

- `days_to_earnings`
- `earnings_blackout_state`
- `recent_guidance_cut`
- `shelf_registration_active`
- `atm_or_secondary_risk`
- `convertible_maturity_12m`
- `debt_refi_wall_24m`
- `index_rebalance_flow_risk`
- `litigation_or_regulatory_flag`
- `event_variance_veto`: event variance dominates technical edge.

**Bottom use:**

- A technically attractive bottom ahead of earnings should not be ranked the same as the same setup after the event clears.
- For distressed names, dilution/refinancing risk is often the reason the "cheap bottom" stays cheap or gaps lower.

**Free data path:**

- SEC 8-K/S-3/424B/10-Q/10-K parsing.
- Earnings date feeds may be imperfect free-data wise, but even stale/approximate event flags are useful if clearly stamped.

**Neural Web role:** downgrade-only until validated. This is mostly a veto/fragility layer.

### 3.7 Bottom-Specific Quality Survival Filter

**Institutional behavior:** Quality is not the same at a bottom as in a normal factor model. At a bottom, the question is not "is this a high-quality compounder?" It is "can this company survive the stress without issuing equity, breaching debt, or seeing earnings expectations collapse further?"

**Metrics:**

- `cash_to_debt`
- `net_debt_to_ebitda`
- `interest_coverage`
- `fcf_margin_ttm`
- `gross_margin_trend`
- `revenue_revision_3m`
- `eps_revision_breadth`
- `altman_or_distress_proxy`
- `equity_issuance_risk`
- `needs_capital_12m`

**Bottom use:**

- If the stock is in a forced-flow technical bottom but the balance sheet is fragile, size smaller or treat as tactical bounce only.
- If the stock has decent quality survival and the decline looks flow-driven, upgrade durability.

**Avoid duplication:** this is not a general QMJ/value factor. It is a **bottom survival pass** that answers "can the name bridge the drawdown?"

### 3.8 Earnings Underreaction and Post-Event Accumulation

**Institutional behavior:** Many systematic equity desks exploit slow information diffusion after earnings, revisions, and guidance changes. For durable bottoms, this matters most when a stock bottoms after bad news is absorbed or when good news arrives while price is still near the low.

**Metrics:**

- `post_event_drift_elig`: earnings event cleared, surprise direction positive, price not extended.
- `revision_breadth_30d`: upgrades minus downgrades.
- `estimate_dispersion_delta`: uncertainty narrowing or widening.
- `guidance_tone_delta`: if qualitative pipeline supports it.
- `event_absorption`: gap down or selloff after event, then reclaim.
- `bad_news_no_new_low`: negative event but price refuses to break prior low.

**Bottom use:**

- Positive: bad news fails to make a new low, or positive surprise emerges before the chart fully recovers.
- Negative: earnings/revisions continue to deteriorate while technicals merely bounce.

**Important:** the existing SUE/revision legs have known PIT/as-of issues in the US-stock audit. The improvement is not "add SUE." It is **real event-date availability plus bottom-specific absorption labels.**

### 3.9 Analyst and Estimate Dispersion as Uncertainty Compression

**Institutional behavior:** Analysts do not just provide a directional revision signal. Dispersion tells a desk how uncertain the market is. A bottom can become durable when uncertainty compresses after an event.

**Metrics:**

- `eps_dispersion_z`
- `sales_dispersion_z`
- `dispersion_delta_30d`
- `revision_disagreement`: upgrades and downgrades both high.
- `uncertainty_compression_after_event`: dispersion falls after price holds low.

**Data reality:** high-quality estimates are paid (IBES/FactSet/Zacks). Free proxies are limited. If we cannot get a clean PIT feed, keep this as a paid-data candidate or use only robust event-derived proxies.

### 3.10 Liquidity, Capacity, and Slippage at the Name Level

**Institutional behavior:** A signal that works on paper but cannot be sized, entered, or exited is not alpha. Institutions translate signal quality into feasible position size.

**Metrics:**

- `adv_dollar_20d`
- `spread_proxy`
- `atr_pct`
- `expected_slippage_bps`
- `participation_to_enter_1pct_book`
- `stop_distance_atr`
- `position_size_cap`
- `liquidity_regime`: normal / impaired / event-thin.

**Bottom use:**

- A deep bottom in a thin name may have attractive forward return but poor executable edge.
- A high-ADV name with clean invalidation can receive larger sizing even with equal signal score.

**Neural Web role:** tradeability and sizing, not selection score.

### 3.11 Crowding and Effective-Bet Control

**Institutional behavior:** A long book can look diversified by ticker count while being one factor, sector, or macro bet. Institutions monitor factor exposure, sector exposure, pairwise correlation, shared holder overlap, and crowding.

**Metrics:**

- `effective_bets`: inverse concentration/correlation measure.
- `sector_weight_share`
- `theme_weight_share`
- `factor_beta_vector`: market, size, value, momentum, quality, low-vol, rates beta.
- `holder_overlap_book`: same crowded holders across candidates.
- `co_bottom_cluster_id`: candidates belong to same drawdown cluster.

**Bottom use:**

- If 12 candidates are all the same Utilities/rates bottom, the board should display one cluster with representative names, not 12 independent "buys."
- Size should be cluster-aware.

### 3.12 Trade Design and Lifecycle State

**Institutional behavior:** Selection and trade management are separate. A desk defines entry, invalidation, add rules, time stop, and when a bounce trade becomes a hold.

**Metrics and states:**

- `entry_zone`: distance to trigger and low.
- `invalidation_line`: ATR- or swing-low-based.
- `first_retest_due`: expected retest window.
- `retest_hold`: price revisits trigger zone and holds.
- `time_stop_days`: no progress after N days.
- `bounce_to_hold_transition`: RS and fundamentals confirm after initial move.
- `stop_to_reentry_rule`: whether failed bottom can re-qualify.

**Bottom use:**

- A tactical bounce and a durable bottom should not use the same exit/hold logic.
- Neural Web should classify a candidate after entry:
  - `failed_immediately`
  - `dead_money`
  - `clean_liftoff`
  - `retest_hold`
  - `launch_continuation`

This is the bridge from "pick better names" to "manage the setup like an institution."

---

## 4. How an Institutional Desk Would Build the System

### 4.1 Separate Mechanism, Timing, and Portfolio Decisions

Institutional design would split the system:

1. **Mechanism detector:** why is this stock dislocated?
   Forced flow, short squeeze, post-event underreaction, balance-sheet stress, sector panic, broad market beta, or unknown.

2. **Timing detector:** is now a good entry window?
   Existing confluence tiers, exhaustion, reclaim, RS repair, anti-chase.

3. **Durability detector:** is this likely to hold the low?
   Sponsorship, ownership breadth, quality survival, event clearance, retest hold.

4. **Risk and tradeability detector:** how much can we express?
   Liquidity, stop distance, options/borrow path, correlation cluster, event variance.

5. **Portfolio allocator:** do we already own this bet?
   Effective bets, sector/theme/factor exposure, candidate correlation.

This avoids the common failure mode: a stock gets one high "buy score" because timing is good while sponsorship and fragility are terrible.

### 4.2 Use Shallow ML for Interactions, Not Signal Origination

Modern asset-pricing research finds that nonlinear methods can help because predictors interact. Gu, Kelly, and Xiu find that trees and neural networks can perform well when relationships are nonlinear and interactive, not merely additive ([RFS, Empirical Asset Pricing via Machine Learning](https://academic.oup.com/rfs/article/33/5/2223/5758276)). Lopez de Prado's ML-for-asset-managers framing is also useful: start from theories and use ML to test/discover structure, not to mine random trading rules ([SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3558728)).

For this repo, the right version is conservative:

- No universal black-box "P(bounce)" model.
- No LLM-originated signal.
- No hand-weighted master score.
- Use shallow models only to learn **interaction gates** among already-defined sensors.

Candidate models:

- monotonic gradient-boosted trees;
- logistic hazard model for stop-out vs liftoff;
- survival model for days-to-retest-fail;
- hierarchical partial-pooling model by sector/regime;
- isotonic calibration per lane.

Feature examples:

- confluence tier x ownership-pressure exhaustion;
- COILED x RS-cohort repair x event cleared;
- high short interest x reclaim x positive revision;
- options panic x gamma flip distance x near-low location;
- quality survival x forced-flow mechanism.

Validation:

- purged/embargoed walk-forward;
- registered trial family;
- compare to equal-weight and rule-based baselines;
- report incremental IC after neutralizing existing confluence/COILED/RS features;
- promote only per regime/horizon cell where Wilson/CI and FDR gates pass.

### 4.3 Use Labels Institutions Would Actually Care About

Forward return alone is too blunt. Durable-bottom selection should grade multiple outcomes:

- `fwd_excess_10d`, `fwd_excess_21d`, `fwd_excess_42d`, `fwd_excess_63d`
- `max_adverse_excursion_21d`
- `low_held_21d`, `low_held_63d`
- `clean_liftoff`: reaches +X ATR before -Y ATR
- `stop_out`: breaks invalidation before target
- `dead_money`: neither target nor stop after N days
- `retest_hold`: retest zone holds after first bounce
- `bounce_then_fail`: first target hits but 63d low fails
- `launch_continuation`: transition from bottom trade to relative leader

Institutions would care because the trade is not just "did it go up?" A +6% bounce that immediately gives back the low is not the same product as a durable bottom that can become a 3-month hold.

---

## 5. Concrete Neural Web Implementation Spec

### 5.1 New Sensor Families

Add these as separate Neural Web producers, not one fused model.

| Family | Purpose | First artifact |
|---|---|---|
| Ownership pressure | forced seller / sponsor map | `data/neuralweb/ownership_pressure.parquet` |
| Flow vulnerability | ETF/fund flow pressure proxy | `data/neuralweb/flow_pressure.parquet` |
| Short/borrow context | squeeze fuel vs informed short warning | `data/neuralweb/short_pressure.parquet` |
| Options panic path | vol/skew/OI/gamma path context | `data/neuralweb/options_panic.parquet` |
| Event fragility | earnings/dilution/refi/calendar vetoes | `data/neuralweb/event_fragility.parquet` |
| Bottom survival quality | can the company survive the drawdown? | `data/neuralweb/bottom_quality.parquet` |
| Tradeability | capacity, slippage, invalidation | `data/neuralweb/tradeability.parquet` |
| Lifecycle grader | post-entry state machine | `data/neuralweb/bottom_lifecycle.parquet` |

Each row should include:

- `as_of`
- `ticker`
- `sensor_family`
- `feature_name`
- `value`
- `coverage_state`
- `known_lag`
- `data_source`
- `mechanism_label`
- `is_display_only`
- `spine_claim_id` when emitted as a claim

### 5.2 Candidate Composite Display

Do not create a single master score. Render a five-column card/table:

| Column | Meaning |
|---|---|
| Timing | existing confluence/tier/freshness/near-low state |
| Durability | low-hold odds from sponsorship, quality, retest, event-cleared |
| Sponsorship | ownership breadth, flow pressure, sector/theme sponsor |
| Fragility | dilution, event, informed-short, liquidity, options pressure |
| Tradeability | stop distance, capacity, correlation cluster, position cap |

This fits the user's real question: "Which bottoms are durable?" The answer is multi-dimensional.

### 5.3 Mechanism Labels

Every bottom candidate should get one or more mechanism labels:

- `forced_flow_reversal`
- `sector_panic_repair`
- `post_event_absorption`
- `short_covering_reversal`
- `quality_compounder_pullback`
- `distress_bounce_only`
- `unknown_technical_only`

These labels are not alpha by themselves. They make the learning loop intelligible.

### 5.4 Promotion Rules

Initial state:

- All new sensor families ship `display_only=true`.
- No new sensor changes rank, size, or alert priority.

Promotion to confirmer:

- Must show incremental lift versus existing bottom stack.
- Must be measured on same-computable subset.
- Must pass minimum event count per mechanism label.
- Must show stable sign in at least two market regimes or be explicitly regime-scoped.

Promotion to scoring:

- Must beat the existing rule-based baseline after costs.
- Must survive FDR within its declared family.
- Must have live-forward evidence, not just historical backtest.
- Must have capacity/tradeability stamped.

Hard-gate authority:

- Only for fragility/veto classes where the claim is "this setup is not comparable because event variance/dilution/liquidity dominates."
- Even there, start downgrade-only.

---

## 6. Specific Studies to Run

### Study A: Forced-Flow Reversal Prototype

**Hypothesis:** Bottom setups following high estimated flow pressure and subsequent pressure deceleration have better low-hold and rebound outcomes than technical-only setups.

**Features:**

- ETF flow pressure proxy.
- 13F holder overlap with pressured funds/themes.
- ADV-scaled estimated sell pressure.
- Price reclaim after pressure peak.

**Labels:**

- 21d clean liftoff.
- 63d low held.
- 21d max adverse excursion.

**Expected result:** sparse but economically interpretable. Even if return lift is small, this may improve fragility labels by identifying "technical-only unknown" versus "forced-flow exhaustion."

### Study B: Ownership Breadth Stabilization

**Hypothesis:** Bottom setups where ownership breadth stabilizes or improves after a prior decline have better 63d durability than setups where breadth keeps contracting.

**Features:**

- holder count delta;
- concentration delta;
- top-holder churn;
- sponsor quality delta.

**Caveat:** quarterly lag means this is not a fresh-entry signal. Grade as durability context.

### Study C: Short-Interest Split

**Hypothesis:** High short interest helps only when paired with absorption/repair; otherwise it is a fragility marker.

**Cells:**

- high SI + reclaim + positive RS repair;
- high SI + no reclaim;
- high SI + negative revisions / weak quality;
- low SI technical bottom baseline.

**Labels:**

- 10d/21d rebound;
- stop-out;
- low held.

### Study D: Post-Event Absorption

**Hypothesis:** A stock that absorbs bad news without making a new low, or prints positive event/revision evidence while still near the low, has higher durability than a pure oscillator turn.

**Features:**

- event cleared;
- bad-news-no-new-low;
- event gap reclaim;
- revision direction after event;
- days since earnings.

**Labels:**

- bounce-then-fail versus durable low hold.

### Study E: Bottom Survival Quality

**Hypothesis:** Bottom setups in financially resilient companies have lower stop-out/dead-money rates than fragile balance-sheet names, even if short-term bounce returns are similar.

**Features:**

- leverage;
- interest coverage;
- FCF margin;
- issuance risk;
- debt maturity proxy;
- gross margin/revenue trend.

**Labels:**

- stop-out;
- dead-money;
- low held;
- 63d excess.

### Study F: Trade Design A/B

**Hypothesis:** Same selector, better lifecycle rules improve realized outcome more than another marginal entry indicator.

**Variants:**

- enter at trigger close plus next open;
- enter only on retest hold;
- partial entry at trigger, add on retest;
- time stop after 10/15/21 trading days;
- ATR invalidation versus swing-low invalidation.

**Labels:**

- realized return net of stop logic;
- max adverse excursion;
- opportunity cost from missed winners.

---

## 7. Paid-Data Watchlist

Free data can build much of the architecture, but some institutional edges are hard to replicate without vendor feeds.

Highest-value paid candidates:

1. **Borrow/stock loan:** borrow fee, utilization, lendable supply.
   Use for informed-short warning versus squeeze fuel.

2. **Institutional flows:** EPFR/Lipper/CRSP mutual fund flows.
   Use for true forced-flow pressure instead of ETF/13F proxies.

3. **Estimates/revisions:** IBES/FactSet/Zacks point-in-time estimates.
   Use for real revision breadth, estimate dispersion, and PEAD quality.

4. **Options surface history:** OptionMetrics/ThetaData/ORATS/LiveVol.
   Use for stock-level skew, risk reversals, gamma/OI history, and vol panic.

5. **News/NLP:** RavenPack/AlphaSense/CapIQ transcripts.
   Use only if event-date and text rights are clean.

6. **Ownership and holdings:** FactSet Ownership / 13F normalized feed.
   Use to avoid painful entity mapping and manager classification.

Paid data should be justified by a study that says exactly which missing variable would change a Neural Web decision. Do not buy broad data because institutions use it. Buy only where the current system has a measured blind spot.

---

## 8. What Institutions Would Not Do

They would not:

- turn every indicator into a vote;
- average sponsorship, timing, quality, and fragility into a hand-weighted 0-100 score;
- rank 30-plus "buys" when the edge only supports three;
- let a bottoming/timing indicator select the top slot by itself;
- call high short interest bullish without separating squeeze fuel from informed shorting;
- call high volume bullish without a specific absorption/reclaim event;
- use 13F as a timing signal despite quarterly lag;
- ignore event calendars;
- size every bottom setup the same;
- evaluate the selector only by forward return while ignoring stop-out, dead money, and low-hold outcomes;
- let an LLM originate, escalate, or reweight a signal without measured authority.

---

## 9. Recommended Build Order

### Phase 1: Free, high-signal context with low risk

1. **Event fragility layer**
   Earnings window, recent 8-K/S-3/424B, shelf/secondary/refi/dilution flags. Downgrade-only.

2. **Tradeability layer**
   ADV, ATR, stop distance, participation, capacity, expected slippage, cluster exposure.

3. **Short-interest split**
   FINRA short interest, days-to-cover, high-SI plus reclaim versus high-SI plus deterioration.

4. **Bottom survival quality**
   Leverage, FCF, coverage, issuance risk, margin trend. Use as durability/fragility, not general factor score.

### Phase 2: Sponsorship and flow proxies

5. **13F ownership breadth and concentration**
   Quarterly durability context, not entry timing.

6. **ETF/theme flow pressure**
   ADV-scaled flow proxy by stock. Mechanism label: forced-flow reversal.

7. **Post-event absorption**
   Earnings/filing event cleared plus price refuses new low or reclaims.

### Phase 3: Interaction learning

8. **Mechanism-conditioned shallow model**
   Learn interactions among existing bottom stack plus new context, with purged walk-forward and FDR.

9. **Lifecycle state machine**
   Convert picks into managed trades: entry, retest, time stop, invalidation, transition to hold.

### Phase 4: Paid-data decision

10. **Paid-data trial only after free proxies prove the mechanism**
    Borrow, estimates, options surface, and institutional flows are valuable only if the free proxy study shows that the mechanism matters.

---

## 10. Final Thesis

The current system is strongest at **technical timing discipline and validation discipline**. Institutions would improve it by adding the missing economic context around the bottom:

- who was forced to sell;
- whether forced selling is ending;
- whether sponsorship is returning;
- whether shorts/options pressure is fuel or warning;
- whether the company can survive the drawdown;
- whether an event can invalidate the setup;
- whether the trade can be sized and managed;
- whether the candidate adds a new bet or duplicates the existing book.

The most institutional version of Neural Web is not a bigger score. It is a **mechanism-aware bottom desk**:

> "This is a COILED/confluence technical bottom, caused by likely forced-flow pressure, with improving cohort sponsorship, event risk cleared, acceptable liquidity, high short-covering fuel but no balance-sheet fragility. Entry is fresh but not chased; invalidation is 1.4 ATR away; size cap is 60 bps because the book already owns the same sector cluster."

That is the level of interpretation investment firms try to reach. The current system already has the nervous system to host it. The next alpha work is to feed Neural Web the missing institutional variables and force each one to earn its place.

---

## Sources Consulted

- AQR: [Investing With Style](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/JOIM-Investing-With-Style.pdf)
- BlackRock: [Systematic Investing](https://www.blackrock.com/us/individual/investment-ideas/systematic-investing)
- Two Sigma: [Investment Management](https://www.twosigma.com/businesses/investment-management/)
- Gu, Kelly, Xiu: [Empirical Asset Pricing via Machine Learning](https://academic.oup.com/rfs/article/33/5/2223/5758276)
- Lopez de Prado: [Machine Learning for Asset Managers, Chapter 1](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3558728)
- SEC: [Form 13F Data Sets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)
- SEC: [Insider Transactions Data Sets](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets)
- FINRA: [Short Interest Reporting](https://www.finra.org/filing-reporting/regulatory-filing-systems/short-interest)
- OCC: [Market Data, Volume and Open Interest](https://www.theocc.com/market-data/market-data-reports/volume-and-open-interest/daily-volume)
- Coval and Stafford: [Asset Fire Sales and Purchases in Equity Markets](https://www.nber.org/system/files/working_papers/w11357/w11357.pdf)
- Chen, Hong, Stein: [Breadth of Ownership and Stock Returns](https://stein.scholars.harvard.edu/publications/breadth-ownership-and-stock-returns)
- Asquith, Pathak, Ritter: [Short Interest and Stock Returns](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=532993)
