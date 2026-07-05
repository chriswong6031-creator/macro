# Non-Technical Durable-Bottom Signal Program for Fable

**Status:** research handoff and build plan.  
**Prepared for:** Fable / Neural Web / Entry Intelligence / Setup Species.  
**Prepared by:** Codex, 2026-07-05.  
**Scope:** weekly-cycle durable bottoms in single stocks and cohorts, explicitly outside pure technical indicators and outside the options workstream.

---

## 0. Executive Ruling

The next-best non-technical frontier is **sponsorship plus solvency repair**, not another market-timing indicator.

The existing strongest trigger remains MACD+StochRSI on 2D/3D. COILED already adds the best proven setup context: cohort washout. Options is a separate active workstream. The non-technical program should therefore answer a different question:

> When the technical trigger says "the selling rhythm is turning," can we prove that the company, cohort, and capital base are no longer broken?

The highest-conviction program is a three-layer **Bottom Sponsorship Stack**:

1. **Real sponsor appeared:** insiders, activists, buybacks, smart 13F adds, government/contracts/grants, or institutional underweight-to-reweighting.
2. **The business stopped deteriorating:** SUE/revision/guidance stabilization, cash runway, margins, balance-sheet risk, or demand/activity reacceleration.
3. **External conditions stopped punishing the bounce:** credit/liquidity stress easing, positioning washed out, fund flows no longer forced-selling the sleeve.

Everything else is supporting context. Sentiment, news, search, social, patents, app reviews, flights, and political/intelligence feeds can be useful, but they should feed the stack only when they can be tied to one of the three economic jobs above.

This program must not create a hand-weighted "bottom score." It should emit separate Neural Web sensors, let the outcome spine grade them, and only promote those that beat the existing confluence trigger plus COILED/S7 baselines on durable-bottom metrics.

---

## 1. What We Must Respect

### Existing durable-bottom law

The current durable-bottom framework defines the target as **washout -> trough -> small perk-up -> liftoff**, not "buy low and hope." Its key metrics are clean-liftoff, stop-out, dead-money, recall, and trap-fire rate. It also warns that durability and return magnitude can compete.

Already established:

- COILED cohort washout is the strongest shipped bottom context in US and China.
- HK failed, so no universal bottom mechanism should be assumed.
- RS repair vs the market is refuted; RS repair inside the stock's own cohort is promising but still phase0.
- Triple-lock hard conjunctions can fail by amputating recall.
- Volume-confirmation, calm-base, trend/location guards, and failed-fire vetoes have bad prior evidence when used as generic buy filters.
- Live Neural Web law: display-first, spine-graded, no LLM-originated signals, no unearned weighting.

### External-source reality check

Official/free and semi-free feeds exist for many non-technical sensors:

- ALFRED/FRED for point-in-time macro vintages and economic/credit series ([ALFRED](https://alfred.stlouisfed.org/), [FRED API](https://fred.stlouisfed.org/docs/api/fred/)).
- OFR FSI for daily financial-stress components ([OFR FSI](https://www.financialresearch.gov/financial-stress-index/)).
- SEC Form 3/4/5 insider data and Form 13F datasets ([SEC insider data](https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets), [SEC 13F datasets](https://www.sec.gov/data-research/sec-markets-data/form-13f-data-sets)).
- SEC EDGAR APIs for XBRL company facts and frames ([SEC data APIs](https://data.sec.gov/), [EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)).
- FINRA short-interest and margin statistics ([FINRA short interest](https://www.finra.org/finra-data/browse-catalog/equity-short-interest/data), [FINRA margin statistics](https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics)).
- ICI weekly fund/ETF flow estimates ([ICI combined flows](https://www.ici.org/research/stats/combined_flows), [ICI ETF flows](https://www.ici.org/research/stats/etf_flows)).
- CFTC COT positioning data ([CFTC COT](https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm)).
- AAII and NAAIM sentiment/exposure gauges ([AAII sentiment](https://www.aaii.com/sentimentsurvey), [NAAIM exposure](https://naaim.org/programs/naaim-exposure-index/)).
- GDELT and EPU for news/narrative intensity ([GDELT data](https://www.gdeltproject.org/data.html), [EPU](https://www.policyuncertainty.com/)).

The key issue is not access. The key issue is **which feeds are causal, point-in-time, non-duplicative, and close enough to the weekly-cycle entry moment to matter**.

---

## 2. First-Principles Model

A durable bottom forms when marginal supply is exhausted and new marginal demand becomes more durable than the prior selling pressure.

### First-order effects

- Forced sellers finish.
- The business is no longer deteriorating faster than price discounted.
- Capital providers stop tightening the valuation multiple.
- A real sponsor has economic reason to buy, hold, or defend the equity.
- Event risk stops dominating the next 1-8 weeks.

### Second-order effects

- Insider/activist/buyback support matters most after a washout, not at all-time highs.
- Positive SUE or guidance stabilization matters more when the name is technically bottoming and still near the trough.
- Retail/institutional pessimism is useful only at extremes and only as a market/cohort context, not as a ticker-level buy.
- News volume can be bearish because bad news is peaking, or bearish because a real impairment is spreading. Tone alone is insufficient.
- Fund flows can mark capitulation, but flows can also chase the bounce after the first move. The slope/turn matters more than the level.

### Third-order effects

- A technical bottom with no sponsor is a bounce candidate.
- A technical bottom with business repair but no market sponsorship is a slow-base candidate.
- A technical bottom with sponsor + business repair + stress easing is the durable-bottom candidate.
- A technical bottom just before earnings, dilution, lockup, litigation, or debt/refi stress is a trap candidate even if the chart looks perfect.

---

## 3. Candidate Signal Families

### Tier 1: Build First

#### F1. Insider and Management Sponsorship

**Mechanism:** open-market insider buying after a drawdown is one of the cleanest non-technical signs that the people closest to the business believe the price is wrong. Clusters beat single buys; opportunistic non-routine buys beat scheduled patterns; CEO/CFO buys beat passive holder buys.

**Existing repo evidence:** insider long-only tilt is positive and orthogonal, but borderline as a standalone sizer. That is perfect for a confirmer, not a stock-picker.

**Signal forms:**

- `insider_cluster_after_washout`: >=2 or >=3 distinct open-market buyers within 45 trading days after a 15-30% drawdown.
- `off_schedule_top_officer_buy`: non-routine CEO/CFO/founder purchase, normalized by market cap.
- `insider_buy_vs_prior_year`: current net buy dollars as percentile of the ticker's own history.
- `insider_cluster_near_confluence`: cluster within -20 to +15 trading days of a MACD+StochRSI fire.

**Expected effectiveness:** high precision, low recall. Should improve trap/dead-money rates and 63/126d durability more than 21d bounce.

**Neural Web role:** `bottom_sponsor.insider`, family `sponsorship`, direction +1, `size_binding=false`, `is_context=true`.

**Kill rule:** if cluster buys do not improve clean-liftoff or dead-money versus same-sector, same-fire-date controls, keep as display-only.

#### F2. Corporate Action Support: Buybacks, Activists, Strategic Owners

**Mechanism:** companies and activists can absorb supply. A buyback authorization, accelerated repurchase, 13D campaign, or strategic holder increase can mark a new marginal buyer with patience.

**Signal forms:**

- `buyback_authorization_after_washout`: new/increased buyback program disclosed by 8-K/10-Q/10-K after a large drawdown.
- `buyback_actual_intensity`: repurchases over trailing quarter / market cap, only if shares outstanding actually decline or cash spent is disclosed.
- `activist_13d_after_washout`: new 13D or activist campaign after drawdown.
- `strategic_holder_add`: known strategic or high-conviction 13F holder initiates/adds after large drawdown.

**Expected effectiveness:** strong for durable bottoms when not funded by balance-sheet deterioration. Activist events may be sparse but should be clean. Buyback authorization alone is weaker than actual repurchase.

**Neural Web role:** `bottom_sponsor.corporate_action`, context plus possible attention escalation. Never a hard buy.

**Veto interaction:** if leverage is high, cash is falling, or debt maturities are near, a buyback should not be treated as support. It may be financial engineering.

#### F3. Fundamental Repair: SUE, Guidance, Revisions, Quality

**Mechanism:** bottoms fail when the business continues to deteriorate underneath the chart. They become durable when the market has already priced bad news and the next fundamental print stops getting worse.

**Existing repo evidence:** SUE has been one of the strongest positive factor candidates, though the current validation window has caveats. Piotroski/Altman/Sloan already exist as slow quality context.

**Signal forms:**

- `sue_positive_near_bottom`: SUE z >= +1 after a washout/confluence fire.
- `sue_less_bad_repair`: SUE improves from bottom decile to above median after serial misses.
- `guidance_delta_positive`: latest guidance range midpoint improves or stops falling.
- `revision_breadth_turn`: analyst revisions turn from negative to neutral/positive, if a reliable feed exists.
- `quality_floor`: Piotroski/Altman/Sloan says "not broken" while price is washed out.

**Expected effectiveness:** likely best at 63/126d durability and dead-money reduction, not immediate 5-21d bounce. Should be separated from tactical bounce outputs.

**Neural Web role:** `bottom_fundamental_repair`, horizon 63/126, not 5/10 unless event reaction is immediate.

**Kill rule:** must beat existing entry-quality bands after controlling for sector, market cap, and fire date. Do not let quality become a generic "good company" preference.

#### F4. Event-Risk Hygiene

**Mechanism:** some bottoms fail because a known binary event overwhelms timing. Earnings, lockups, dilution windows, FDA/regulatory decisions, court rulings, debt maturities, and merger votes can turn a high-quality technical entry into a coin flip.

**Signal forms:**

- `earnings_blackout`: scheduled earnings T-3 through T+0, live row must be fresh and future-dated.
- `dilution_overhang`: ATM/shelf/convertible/equity offering filed recently while cash runway is short.
- `lockup_expiry_overhang`: IPO/SPAC lockup expiry within next 20 trading days.
- `debt_maturity_refi`: near-term maturities plus high spread/weak cash flow.
- `regulatory_binary`: FDA/PDUFA/court date inside stop horizon.

**Expected effectiveness:** high confidence as a veto/hygiene layer. It may not increase returns, but it should reduce ugly stop-outs and post-entry gap risk.

**Neural Web role:** `bottom_event_hygiene`, direction -1, `is_veto=true`, `size_binding=false`.

**Promotion path:** this is the one non-technical family allowed to become a hard gate, but only if vetoed fires are demonstrably worse and veto volume stays small.

### Tier 2: Build After Tier 1 Foundations

#### F5. Macro and Credit Stress Release

**Mechanism:** weekly-cycle bottoms are more durable when broad funding stress stops tightening. Credit spreads, CP/T-bill spreads, OFR FSI components, NFCI, dollar liquidity, and rates volatility tell us whether the market is still de-risking.

**Signal forms:**

- `stress_peak_turn`: OFR FSI or NFCI extreme percentile starts falling.
- `credit_spread_turn`: HY/IG OAS, CP/T-bill, bank/funding spreads stop widening.
- `liquidity_impulse`: FRED/ALFRED liquidity series improve using point-in-time vintages.
- `rates_vol_relief`: MOVE/VIX-rates pressure turns lower.

**Expected effectiveness:** strong for market/cohort permission, weak for ticker selection. It should condition Neural Web's trust in bottom sensors by regime, not produce individual buy calls.

**Neural Web role:** `bottom_macro_release`, universe-level context, regime bucket feature.

**Kill rule:** if it only restates VIX or existing risk regime, keep as context. The incremental test must control for VIX, SPY drawdown, and existing market_state/risk_regime.

#### F6. Positioning and Flow Capitulation

**Mechanism:** durable bottoms often need forced sellers to be done. Positioning washout plus stabilization is more useful than bearish sentiment alone.

**Signal forms:**

- `aaii_bear_extreme_turn`: extreme bearish sentiment begins reverting.
- `naaim_exposure_washout_turn`: active-manager exposure collapses then rises.
- `cot_equity_spec_washout`: CFTC equity-index speculative positioning near low percentile then improving.
- `ici_equity_outflow_exhaustion`: equity fund/ETF outflows peak and moderate.
- `finra_margin_deleveraging`: margin debt drawdown stabilizes after forced deleveraging.
- `short_interest_crowded_repair`: single-name short interest high but no longer rising, paired with sponsor/fundamental repair.

**Expected effectiveness:** good for index and sector bottoms; noisy for individual tickers. Best used as a "market supply exhausted" context cell.

**Neural Web role:** `bottom_positioning_reset`, universe/cohort scope, horizon 21/63.

**Gotcha:** AAII/NAAIM/COT/ICI are weekly or lagged. They cannot be the exact entry trigger. They are weekly-cycle weather.

#### F7. Ownership and Fund-Flow Reweighting

**Mechanism:** a bottom is more durable when the name/cohort is under-owned and sponsorship begins to return. The signal is not "crowded is good"; the signal is "underweight or purged, then re-accumulated."

**Signal forms:**

- `13f_underowned_reaccumulation`: ownership percentile low, then tracked funds initiate/add.
- `vip_holder_count_delta`: high-quality holder count rises after washout.
- `sector_fund_flow_turn`: ETF/fund flow into the sector turns positive after outflows.
- `crowding_relief`: prior crowding unwound enough that new buying can matter.

**Expected effectiveness:** slower but useful for durable bottoms and portfolio construction. 13F lag makes it poor for immediate timing but good for confirming a base.

**Neural Web role:** `bottom_ownership_reweight`, horizon 63/126, low cadence.

**Kill rule:** must be point-in-time filed-date based. Quarter-end holdings dated as if known on quarter-end are illegal.

### Tier 3: Shadow or Exploratory

#### F8. Real-Activity and Product-Demand Repair

**Mechanism:** some stocks bottom before financial statements show it because activity data turns first: app reviews, web traffic, job postings, patents, flights, contract awards, grants, developer activity, or product launches.

**Existing repo state:** many Quiver-derived feeds are already activated into the Signal Intelligence Desk. This program should not duplicate them. It should create **bottom-specific transforms**: "reacceleration after price washout" rather than generic convergence.

**Signal forms:**

- `app_demand_reaccel_after_washout`: review velocity/rating trend improves after drawdown.
- `gov_contract_accel_after_washout`: contracts/grants accelerate off a real dollar floor.
- `patent_cluster_after_washout`: recent patent cluster after large drawdown.
- `hiring_reaccel`: job postings stabilize/reaccelerate after layoffs or slowdown, if a reliable feed exists.
- `developer_activity_repair`: GitHub/HuggingFace momentum for names where this is economically meaningful.

**Expected effectiveness:** high idiosyncratic value, low coverage, long half-life. Better for "durable base" than weekly-cycle timing.

**Neural Web role:** `bottom_real_activity_repair`, context only until many events mature.

#### F9. Narrative Neglect, Panic, and Resolution

**Mechanism:** durable bottoms often occur when the story has gone from ignored -> hated -> no longer getting worse. But text can easily duplicate VIX/price or become a hallucination channel.

**Signal forms:**

- `bad_news_peak_decay`: ticker news volume/tone extremely negative, then volume decays while price stabilizes.
- `narrative_resolution`: litigation/regulation/supply-chain topic shifts from uncertainty to resolved.
- `theme_neglect_reversal`: theme coverage falls to low percentile, then real sponsor/activity appears.
- `social_panic_capitulation`: retail/social panic spikes, then fades without further price break.

**Expected effectiveness:** useful for attention and falsifier generation, weak as a direct signal. Existing narrative-regime work found text uncertainty redundant/worse once VIX is controlled for forward vol, so this family must prove ticker-level incremental value.

**Neural Web role:** `bottom_narrative_repair`, display and contradiction/confluence graph first.

**Hard rule:** LLMs may classify text and extract cited events; they may not originate the signal or raise conviction.

---

## 4. The Proposed Build: Bottom Sponsorship Stack

### 4.1 Stack definition

For every existing technical fire, build a same-date context snapshot with independent non-technical sensors:

```text
Bottom Sponsorship Stack =
  Sponsor present
  + business repair / not-broken floor
  + event-risk clear
  + macro/positioning permission
```

Where:

- Sponsor present = insider cluster OR buyback actual/intended OR activist/strategic owner OR smart 13F add OR government/contracts/grants acceleration.
- Business repair = positive SUE/revision/guidance OR quality floor OR real-activity reacceleration.
- Event-risk clear = no fresh earnings/dilution/lockup/debt/regulatory binary inside the stop horizon.
- Macro/positioning permission = stress/flows/positioning no longer deteriorating.

### 4.2 Why this is the next-best thing

Technical indicators observe price behavior. Options observe derivatives positioning. This stack observes the **economic reasons the bounce should hold**:

- someone with information or mandate is buying;
- the business is not still falling through the floor;
- the next known event is not about to overwhelm the entry;
- the market is not still forcing liquidation.

That is orthogonal enough to deserve Neural Web space.

### 4.3 Do not make it a hard conjunction

Hard conjunctions are dangerous because they gut recall. Instead:

- Each leg emits separately.
- The stack emits a context tier:
  - `NONE`: no non-technical support.
  - `SPONSOR_ONLY`: sponsor present, business/event unknown.
  - `REPAIR_ONLY`: business repair, no sponsor.
  - `SPONSOR_REPAIR`: sponsor + business repair.
  - `FULL_SUPPORT`: sponsor + repair + event clear + macro permission.
  - `VETOED`: event/dilution/debt binary blocks the entry.
- Neural Web grades each tier against the incumbent fire, COILED, S7, and entry-quality bands.

---

## 5. Validation Design

### 5.1 Primary unit of analysis

Do not ask, "does this feed predict returns by itself?"

Ask:

> Conditional on the existing confluence/COILED fire, does this non-technical sensor reduce false bottoms, dead money, or missed durable bottoms?

Use the durable-bottom framework metrics:

- stop-out rate;
- clean-liftoff rate;
- dead-money rate;
- trap-fire rate;
- recall vs durable-bottom labels;
- entry premium above trough;
- 21d, 63d, and 126d horizons split by sensor family.

### 5.2 Baselines

Every candidate must beat or add marginal value beyond:

- existing MACD+StochRSI fire/tier;
- COILED and COILED-FIRE;
- existing entry-quality/proximity/freshness bands;
- S7 within-cohort RS repair when available;
- sector/date fixed effects;
- market regime/risk state.

### 5.3 Statistical bars

Recommended promotion bars:

- **Hygiene veto:** vetoed set is worse by >=2pp stop-out or materially worse MAE, CI excluding 0, and vetoes <=10% of fires.
- **Confirmer chip:** favorable stratum improves clean-liftoff by >=3pp or dead-money by >=3pp, same sign in >=3/4 eras, no more than 2pp worse stop-out.
- **Neural Web kernel lane:** n_eff >= 12 per marginal cell, then quarterly FDR sweep decides whether cells can influence trust language.
- **Board/rank bonus:** no rank/score effect until live ledger matures and shrunken posterior is positive with CI support.

### 5.4 Controls against self-deception

- Known-date only. 13F uses filing date, not quarter-end. EDGAR facts use filed/as-of dates, not period-end.
- Same-computable-subset baselines for sparse feeds.
- Episode-block bootstrap; no pseudo-replication across many names in one crisis.
- Date fixed effects for stratum comparisons.
- No using the same historical fire once in a phase0 report and again as independent Neural Web kernel evidence.
- Nulls are printed. Failed feeds go to the graveyard.

---

## 6. Neural Web Integration Contract

### 6.1 Engines and families

Create separate engines or families, not one blob:

| Engine | Family | Scope | Horizon |
|---|---|---|---|
| `bottom_sponsor` | insider / buyback / activist / 13f / gov | ticker | 21/63/126 |
| `bottom_fundamental_repair` | sue / guidance / quality / activity | ticker | 63/126 |
| `bottom_event_hygiene` | earnings / dilution / lockup / debt / regulatory | ticker | 5/21/63 |
| `bottom_macro_release` | stress / liquidity / credit | market/cohort | 21/63 |
| `bottom_positioning_reset` | AAII / NAAIM / COT / ICI / margin / SI | market/cohort/ticker | 21/63 |
| `bottom_ownership_reweight` | 13F / holders / flow | ticker/cohort | 63/126 |
| `bottom_narrative_repair` | news / social / uncertainty resolution | ticker/cohort | 21/63 |
| `bottom_real_activity_repair` | app / patents / contracts / hiring | ticker | 63/126 |

### 6.2 Spine emission

For each technical fire, emit `SpinePrediction` context rows:

```json
{
  "engine": "bottom_sponsor",
  "family": "insider_cluster",
  "as_of": "YYYY-MM-DD",
  "symbol": "TICKER",
  "horizon": 63,
  "score": 1.0,
  "direction": 1,
  "size_binding": false,
  "event_key": "TICKER:YYYY-MM-DD:bottom_context",
  "meta": {
    "trigger_id": "confluence:T2",
    "sensor_stage": "sponsorship",
    "source_event_date": "YYYY-MM-DD",
    "known_date": "YYYY-MM-DD",
    "definition_version": "v1",
    "pit_basis": "filing_date",
    "support_tier": "SPONSOR_REPAIR"
  }
}
```

For hygiene vetoes, use `direction=-1`, `is_veto=true`, and a falsifier such as "veto should earn positive credit if blocked entries underperform matched non-veto fires."

### 6.3 Display surfaces

Do not crowd the chart. Use progressive disclosure:

- Standout card chip: `Sponsor`, `Repair`, `Event clear`, `Macro relief`, `Veto`.
- Stock page section: exact source events with known dates and citations.
- Committee page: provenance sidecar rows per source.
- Neural Web graph: confluence edges from sponsor/repair to technical fires.
- Ask-the-brain: explain which non-technical sensors were present and which were absent.

### 6.4 AI usage

LLM may:

- extract and classify events from filings/news;
- summarize source evidence with citations;
- write falsifiers and second-order implications;
- de-escalate if evidence is stale or contradictory.

LLM may not:

- create a signal without a deterministic extractor;
- raise a score by narrative judgment;
- treat uncited claims as source events;
- override the spine/kernel promotion ladder.

---

## 7. Wave Plan

### W0: Inventory and collision audit

Read current implementations and avoid duplication:

- `engine/insider_factor.py`
- `engine/altdata_models.py`
- `engine/altdata_signals.py`
- `engine/sue.py`
- `engine/stock_fundamentals.py`
- `engine/neuralweb/*`
- `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`
- `research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md`

Deliverable: `research/nontech_bottom/W0_INVENTORY.md` with source availability, PIT status, expected event counts, and no-go duplicates.

### W1: Build PIT feature panels

Build or adapt:

- insider cluster panel;
- buyback/activist/corporate-action panel from EDGAR 8-K/10-Q/10-K/13D;
- SUE/guidance/quality repair panel;
- event-risk calendar panel;
- macro stress/credit/positioning panel;
- 13F ownership/reweighting panel;
- bottom-specific transforms for existing alt-data channels.

Deliverable: `data/research/nontech_bottom_features.parquet` plus `feature_meta.json`.

### W2: Phase0 studies anchored on technical fires

Run the primary study:

- baseline technical fires;
- baseline + COILED;
- baseline + S7 where available;
- baseline + each non-technical family;
- baseline + Bottom Sponsorship Stack tiers.

Deliverable: `research/nontech_bottom/W2_PHASE0_REPORT.md`.

### W3: Shadow Neural Web wiring

Only for families that clear phase0 or are hygiene-worthy:

- emit display-only spine rows;
- add synapse registry entries;
- add provenance sidecar rows;
- add event-key collapse so co-firing channels do not count as independent observations;
- build dashboard chips only if they improve clarity.

Deliverable: PR with no behavior-changing score effects.

### W4: Live ledger accrual and quarterly kernel batch

Let live events mature. No promotion before the quarterly Neural Web FDR batch.

Deliverables:

- kernel cells by engine/family/horizon/regime;
- confluence graph edges;
- passport states;
- come-back dates for thin cells.

### W5: Promotion or graveyard

Promote only one of:

- hygiene veto;
- confirmer chip;
- rank bonus inside existing tier;
- display-only context;
- retired/falsified.

Anything promoted must include the exact bars, sample, confidence, and failure modes.

---

## 8. Ranked Build Queue

1. **Event-risk hygiene**: easiest to reason about, most likely to prevent avoidable traps, doctrine-legal as a veto if proven.
2. **Insider/management sponsorship**: strongest single-ticker non-technical candidate, sparse but orthogonal.
3. **Fundamental repair/SUE/guidance**: most likely to improve 63/126d durability.
4. **Corporate action support**: buybacks/activists/strategic holders can absorb supply, but requires careful balance-sheet veto.
5. **Macro/credit stress release**: excellent regime conditioner, not a ticker signal.
6. **Positioning/fund-flow reset**: useful weekly-cycle weather, lagged and mostly cohort-level.
7. **Ownership reweighting**: slow but valuable for bases, not exact weekly trigger timing.
8. **Real-activity repair**: promising, sparse, best after existing alt-data plumbing is bottom-specific.
9. **Narrative repair**: high curiosity, high false-positive risk, display/attention first.

If Fable wants the fastest useful build, start with **event hygiene + insider sponsorship + fundamental repair**, then wire the stack shadow-only into Neural Web.

---

## 9. Candidate Graveyard and No-Go Rules

Do not build:

- a master bottom score with hand weights;
- pure sentiment as a buy trigger;
- plain "bad news is high, buy" reversal logic;
- 13F quarter-end ownership treated as known before filing;
- generic volume confirmation outside already-registered technical work;
- generic "quality stock" ranking as if it were bottom timing;
- news/LLM conviction without deterministic cited event extraction;
- macro stress level without the **turn** and without controlling for VIX/market drawdown;
- short interest as a standalone bullish signal.

---

## 10. Fable Prompt

Use this as the build prompt:

> Build the Non-Technical Durable-Bottom Program. Do not add new technical indicators and do not touch the options lane. The goal is to determine which non-technical sensors improve the durability of existing MACD+StochRSI weekly-cycle bottom entries: sponsorship, business repair, event-risk hygiene, macro/credit release, positioning reset, ownership reweighting, real activity, and narrative repair. Start with a W0 inventory against current repo implementations, then build PIT panels and run phase0 studies anchored on existing technical fires. Use durable-bottom metrics, not standalone return alpha. Emit separate Neural Web spine families, display-first, with no hand-weighted master score. Promote only after pre-registered gates; print nulls and graveyard failures.

---

## 11. Bottom Line

The non-technical edge is not "find a different oscillator." It is:

```text
Technical trigger says sellers are losing rhythm.
Non-technical stack asks whether real capital, business facts, and event risk agree.
Neural Web learns which of those confirmations matter, in which regime, at which horizon.
```

The best first target is a **Sponsorship + Fundamental Repair + Event Hygiene** overlay. If it works, it will not replace MACD+StochRSI. It will tell Neural Web which MACD+StochRSI bottoms are worth stepping on because the floor is less likely to cave in.
