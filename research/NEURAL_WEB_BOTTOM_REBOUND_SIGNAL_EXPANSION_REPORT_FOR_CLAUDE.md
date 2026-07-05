# Neural Web Bottom and Rebound Signal Expansion

**Status:** Draft research and suggestion report for Claude/Fable review.
**Requested by:** Operator, 2026-07-05.
**Prepared by:** Codex.
**Intended reader:** Claude/Fable, Entry Intelligence, Setup Species, Oracle, Neural Web.

---

## 0. Plain-English Thesis

The next high-return opportunity for Neural Web is not "add more indicators." It is to teach Neural Web where each sensor sits in the bottoming sequence:

1. **Exhaustion:** sellers have been forced out.
2. **Stabilization:** the stock stops making easy new lows.
3. **Trigger:** short-cycle momentum turns before the broad crowd sees the rebound.
4. **Repair:** the stock starts improving versus its own peer group.
5. **Sponsorship:** sector, subsector, theme, or flow engines confirm capital is rotating into the area.
6. **Anti-chase and veto:** avoid buying after the easy rebound is already spent, or just before an event that turns timing into a coin flip.

The operator's intuition is right: 3D MACD / RSI-MACD plus 3D StochRSI and 2W StochRSI washout can front-run weekly-cycle bottoms. But the repo's prior work says those oscillators should remain the **entry spine**, not the whole decision. Durable bottom entries improve when the oscillator turn is surrounded by capitulation context, relative-strength repair, cohort washout, flow/rotation sponsorship, and anti-chase controls.

Neural Web should therefore build a **bottom/rebound sensor stack** rather than a hand-weighted master score. Each candidate should emit as a separate spine engine or kernel feature, accrue outcomes, and earn promotion by regime and horizon.

---

## 1. Why This Matters for Returns

The operator's return thesis is explicitly bottom/rebound capture:

- find names near the end of a short-to-medium cycle;
- enter before the obvious breakout;
- reduce the cases where a fresh buy becomes dead money or immediately drops;
- favor names that mean-revert upward soon after entry;
- let winners transition from "bottom entry" to "hold/launch" rather than repeatedly re-buying stale signals.

This is exactly the domain where a normal indicator stack fails if every indicator is treated as an equal vote. Oversold indicators fire early and often. Trend indicators confirm late. Volume indicators can look bullish after the move is already obvious. Sector rotation can help or hurt depending on whether it is used as a hard gate or a priority modifier.

The correct Neural Web task is: **learn which sensor has incremental value at which stage of the bottoming process, under which regime, at which horizon.**

That matches the Neural Web kernel design already described in `research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md`: engines emit claims, claims are graded, and regime/horizon cells decide which engines deserve trust. It also matches `research/ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`, which says every surviving trigger/hygiene sensor should emit `SpinePrediction` rows and accrue display-first.

---

## 2. Current Evidence Base to Respect

This report should be read as a synthesis, not a replacement for the existing programs.

### 2.1 Existing spine: MACD-RSI x StochRSI confluence

The live entry gate already centers on a MACD-RSI x StochRSI cascade:

- T1/T2: just-crossed confirmed buy zones.
- T3: 3D StochRSI crossed and 2D MACD-RSI is about to cross.
- T4: earliest/weakest tier; useful as forming context, not an entry-now fire.

The prior MTF MACD/StochRSI study found that **single legs are weak**, while the confluence has a small front-loaded lift. This matters: Neural Web should not separately upweight daily MACD, 3D StochRSI, weekly bottoming, and volume as if they were independent. The confluence is the object.

### 2.2 COILED is the strongest shipped bottom context

The durable-bottom program's load-bearing finding was cohort washout:

- COILED = washout context plus a large share of GICS-sector peers in weekly StochRSI washout.
- COILED improved clean-liftoff and stop-out measures in US and China.
- HK failed, which is a critical warning that bottom mechanisms are market-structure-specific.

This is first-principles coherent. A single stock being oversold may be a knife. A cohort being washed out while a name begins to turn is a cleaner forced-seller exhaustion process.

### 2.3 RS repair is promising, but only in the right frame

The Codex bottom-backtest triage and S7 re-run found a sharp distinction:

- RS repair versus SPY was not reliable and was even worse in holdout.
- RS repair versus the stock's own cohort/sector peer group was the real signal.
- The "triple lock" of capitulation + RS repair + near-low location did not survive as a hard conjunction. COILED carried the load-bearing effect.

This suggests Neural Web should not ask "is the stock outperforming the index?" during bottom fishing. It should ask "is the stock repairing its place inside the cohort that was just washed out?"

### 2.4 Anti-chase matters, but can fight durability

The prior bottom backtest suggested that being within roughly 15-20% of the 60D low helped entry asymmetry. But anti-chase/location filters can also worsen longer 60D durability if used as a hard conjunction. This implies:

- anti-chase is primarily an **entry-zone quality** feature;
- it should penalize extended entries;
- it should not automatically block names that have already launched and are now in a hold/continuation state.

### 2.5 Volume as a generic confirmer is suspect

Existing docs already warn that OBV, up/down volume, capitulation spike, and dry-up filters had bad or noisy signs as positive entry filters. That does not mean volume is useless. It means volume should be used only in tightly defined event mechanics:

- release from squeeze with direction;
- reclaim day sponsorship;
- liquidity/tradability hygiene;
- not as a broad "more volume = better buy" vote.

### 2.6 Neural Web should consume, not overrule, until earned

Neural Web law is the important integration constraint:

- no LLM-originated signals;
- no hand-weighted master score;
- display-first until earned;
- quarterly/kernel FDR gates before consumption;
- cross-artifact double-counting guard;
- rare signals must justify whether they can reach event budgets.

That means the output of this report should be a queue of sensors and studies, not immediate production weights.

---

## 3. First-Principles Model of a Durable Bottom

A durable bottom is not just "oversold." It is a supply/demand transition.

### 3.1 First-order effects

These are direct, mechanical observations:

- forced selling pushes price below recent ranges;
- momentum decelerates as sellers lose force;
- oscillators turn up because the rate of decline slows;
- buyers reclaim broken levels when supply has been absorbed;
- relative strength repairs when the name stops being the funding source inside its group.

### 3.2 Second-order effects

These decide whether the bounce is tradable:

- if the whole cohort is washed out, sellers may be exhausted across the theme;
- if the sector is rotating up, the name gets external sponsorship;
- if the stock is too far above the low, entry risk shifts from bottom capture to chase;
- if earnings are imminent, the technical edge may be dominated by event variance;
- if the name is illiquid, realized entry/exit quality worsens even if the chart works.

### 3.3 Third-order effects

These matter for Neural Web:

- the same oscillator fire has different meaning in a risk-on market, a bear rally, a sector unwind, or a liquidity squeeze;
- some sensors are early but noisy; some are late but cleaner;
- hard gates shrink recall and can destroy the board if used too aggressively;
- the best architecture is staged interpretation, not a single scalar score.

---

## 4. Proposed Neural Web Bottom/Rebound Sensor Taxonomy

Neural Web should track each signal family as a separate sensor with a declared job.

### 4.1 Exhaustion Sensors

**Purpose:** identify forced-seller context. These do not buy by themselves.

Candidate indicators:

- 2W StochRSI washout and reclaim.
- 1W StochRSI K/D cross from deep zone.
- Weekly StochRSI D below 20/30.
- Multi-timeframe StochRSI washout breadth across 1D, 3D, 1W, 2W.
- Drawdown from 60D, 126D, and 252D highs.
- Distance from 60D and 126D lows.
- ATR-normalized drawdown.
- Percent of sector/cohort peers in weekly StochRSI washout.
- New-low breadth in the cohort.
- Gap-down exhaustion followed by close recovery, where open data exists.

Recommended Neural Web fields:

- `exhaustion_tf_2w_stoch`
- `exhaustion_w_stoch`
- `exhaustion_cohort_washout_frac`
- `exhaustion_drawdown_atr`
- `exhaustion_near_low_score`
- `exhaustion_new_low_breadth`

Build priority:

1. Use existing COILED fields as the load-bearing exhaustion context.
2. Add 2W washout-reclaim as a context chip, not a standalone entry.
3. Add deep-tier cohort washout tiers as regime cells for Neural Web, especially bear-regime robustness.

### 4.2 Turn-Trigger Sensors

**Purpose:** detect the moment selling pressure flips into upward momentum.

Candidate indicators:

- 2D RSI-MACD bullish cross.
- 3D RSI-MACD bullish cross.
- 3D StochRSI bullish cross from below 20.
- 2D MACD-RSI approaching cross with projected bars-to-cross.
- MACD histogram slope turning positive before cross.
- MACD histogram second derivative / curl.
- 1D MACD-RSI fire inside COILED context.
- Daily trigger as early ripple; 3D trigger as wave; weekly as tide.

Recommended Neural Web fields:

- `trigger_tier`
- `trigger_take_date`
- `trigger_age_ticks`
- `trigger_macd_bars_to_cross`
- `trigger_hist_slope`
- `trigger_hist_accel`
- `trigger_stoch_zone_at_cross`
- `trigger_freshness_state`

Build priority:

1. Keep existing confluence tiers as the official trigger spine.
2. Add histogram slope/acceleration as an early-warning context feature.
3. Ensure every trigger row carries freshness and signal-age metadata into Neural Web.

### 4.3 Stabilization and Reclaim Sensors

**Purpose:** prove the stock stopped falling and buyers absorbed supply.

Candidate indicators:

- Undercut-and-rally / spring reclaim.
- Close back above prior 21D or 63D low after undercut.
- Higher low after washout.
- Failed breakdown reversal.
- Close back above 8/21 EMA after washout.
- Donchian low reclaim.
- Retest hold: price revisits trigger zone but does not break trough.
- Invalidation line: trough x 0.97 or ATR-scaled equivalent.

Recommended Neural Web fields:

- `reclaim_spring`
- `reclaim_lookback_n`
- `reclaim_depth_atr`
- `reclaim_days_to_reclaim`
- `stabilization_higher_low`
- `stabilization_retest_hold`
- `invalidation_close_line`

Build priority:

1. Promote S-UR/spring reclaim to the top new species candidate.
2. Test S-UR inside COILED and near gate fires.
3. Keep same-bar fill banned: the reclaim must be knowable before entry.

### 4.4 Relative-Strength Repair Sensors

**Purpose:** avoid buying stocks still bleeding relative to their own opportunity set.

Candidate indicators:

- 20D slope of stock rank inside its sector/cohort.
- RS higher-low versus sector while price retests low.
- RS z-score inflection from bottom quartile to middle quartiles.
- Stock/sector RS slope, with same-computable-subset baselines.
- Sector-neutral residual momentum repair.
- Avoid using plain stock/SPY repair as a bottom signal unless re-tested in a narrow context.

Recommended Neural Web fields:

- `rs_cohort_rank_slope20`
- `rs_cohort_rank_delta`
- `rs_sector_slope20`
- `rs_higher_low`
- `rs_inflection_zone`
- `rs_repair_state`: `repairing | neutral | deteriorating | extended`

Build priority:

1. Carry S7 as phase0 and reread after the W0.4 within-cohort RS-rank series exists.
2. Treat RS-vs-SPY repair as adjacent-falsified for bottom entries.
3. Let Neural Web learn whether RS repair matters more at 21D, 63D, or 126D horizons.

### 4.5 Anti-Chase and Entry-Zone Sensors

**Purpose:** reduce dead money and immediate post-buy drawdown caused by entering after the move is already spent.

Candidate indicators:

- Extension from 20D/60D low.
- ATR distance from trigger price.
- Distance above 8/21/50 EMA after trigger.
- 3D StochRSI overbought state after signal.
- RSI above 70 soon after signal.
- Bollinger %B / Keltner channel position.
- Days since trigger plus launch/hold state.
- Vol-scaled entry zone: expected noise band, not fixed 5% for every name.

Recommended Neural Web fields:

- `entry_ext_z`
- `entry_dist_from_low_60d`
- `entry_atr_from_trigger`
- `entry_stoch_ob`
- `entry_signal_age`
- `entry_launch_state`
- `entry_zone_low_40d`
- `entry_vol_scaled_stop_band`

Build priority:

1. Re-test extension/anti-chase on production-trigger fires only.
2. Distinguish "fresh buy" from "hold/launch." Do not punish a successful launch as if it were a bad entry.
3. Pre-register vol-scaled races as a co-primary outcome for high-vol bottom names.

### 4.6 Volatility Compression and Release Sensors

**Purpose:** find the transition from quiet base to active rebound without re-creating the falsified calm-base arm.

Candidate indicators:

- Bollinger BandWidth percentile / BBWP.
- Historical volatility percentile / HVP.
- TTM squeeze.
- Keltner/Bollinger squeeze release.
- NR7 / narrow-range cluster followed by range expansion.
- ATR percentile rising from a low base.
- Directional release bar.

Recommended Neural Web fields:

- `vol_compression_pctile`
- `vol_squeeze_state`
- `vol_release_up`
- `vol_release_age`
- `range_expansion_state`
- `atr_pctile_turn`

Build priority:

1. Implement `vol_squeeze.assess_series()` fidelity-pinned to existing scalar `assess()`.
2. Test release-bar-only, not quiet-base arming.
3. If it survives, ship as a `RELEASE` chip and spine engine; never as a hard gate.

### 4.7 Flow and Sponsorship Sensors

**Purpose:** identify whether capital is rotating into the stock's sector/theme after the bottom signal.

Candidate indicators:

- Sector rotation velocity.
- Subsector/theme velocity and acceleration.
- Flow velocity into names and sectors.
- Southbound/Northbound flow where live and reliable.
- ETF flow residuals after stripping price effect.
- Options flow / IV demand after sufficient accrual.
- Relative volume on reclaim/release day only.
- CMF / Accumulation-Distribution only as sponsorship context, not generic gate.

Recommended Neural Web fields:

- `sponsor_sector_velocity`
- `sponsor_subsector_velocity`
- `sponsor_theme_accel`
- `sponsor_flow_velocity`
- `sponsor_etf_flow_residual`
- `sponsor_reclaim_rvol`
- `sponsor_cmf_state`

Build priority:

1. Feed Oracle rotation state and velocity into Neural Web as a priority modifier, not a hard gate.
2. Test whether bottom fires inside accelerating subsectors have lower stop-out/dead-money.
3. Use China/HK flow velocity only where the data is live and freshness-stamped.

### 4.8 Regime and Donor-Leadership Sensors

**Purpose:** determine whether the market backdrop favors mean reversion, continuation, or risk control.

Candidate indicators:

- SPY/QQQ/IWM 3D and weekly MACD state.
- Market above/below 200D and 200D slope.
- Breadth thrust and new-high/new-low repair.
- VIX level and VIX trend.
- Credit/liquidity stress context.
- Donor-unwind: former leading sector cracking, allowing capital to rotate.
- Risk-on/risk-off Neural Web world state.

Recommended Neural Web fields:

- `regime_market_trend`
- `regime_mtf_index_state`
- `regime_breadth_thrust`
- `regime_vol_state`
- `regime_credit_liquidity`
- `regime_donor_state`
- `regime_world_state_bucket`

Build priority:

1. Keep donor-unwind US-only unless separately tested elsewhere.
2. Use regime as a reliability-cell bucket for Neural Web rather than a universal block.
3. Require separate market-specific studies for HK/China/Canada.

### 4.9 Quality and Holdability Sensors

**Purpose:** improve medium-term holding quality after a good entry.

Candidate indicators:

- Piotroski F-score.
- Altman Z-score.
- Sloan accruals.
- Profitability and balance-sheet stress.
- Earnings revisions if a live feed exists.
- Upcoming earnings blackout.
- Liquidity/spread deterioration.
- ADV floor and tradability screens.

Recommended Neural Web fields:

- `quality_piotroski`
- `quality_altman`
- `quality_sloan`
- `quality_balance_sheet_stress`
- `event_earnings_blackout`
- `liquidity_amihud_band`
- `liquidity_spread_proxy`

Build priority:

1. Earnings blackout is the cleanest hygiene candidate.
2. Quality should affect 63D/126D holdability, not initial entry timing.
3. Liquidity is a cost/MAE screen, not alpha.

---

## 5. Proposed Neural Web Decision Model

Do not build one master "buy score." Build a staged bottom/rebound profile.

### 5.1 Six Subscores

Each buy candidate should have six interpretable subscores:

1. **Exhaustion Score**
   - Is this a real washout, or a shallow dip?
   - Inputs: 2W/1W StochRSI washout, drawdown, cohort washout, near-low state.

2. **Trigger Score**
   - Did the entry spine fire recently?
   - Inputs: T1/T2/T3 tier, 2D/3D MACD-RSI cross, 3D StochRSI cross, histogram slope.

3. **Repair Score**
   - Is the stock improving versus its own peer group?
   - Inputs: cohort RS rank slope, RS higher-low, sector-relative repair.

4. **Sponsorship Score**
   - Is capital rotating into the relevant group?
   - Inputs: sector/subsector velocity, flow velocity, donor-unwind, breadth repair.

5. **Entry-Zone Score**
   - Are we early enough to be paid for the risk?
   - Inputs: extension, ATR distance, StochRSI overbought, signal age, launch state.

6. **Holdability Score**
   - If we are right on entry, is this worth holding?
   - Inputs: quality, liquidity, earnings blackout, volatility zone, balance-sheet stress.

### 5.2 Suggested Classification Output

Neural Web should output state labels, not just points:

| State | Meaning | Likely action |
|---|---|---|
| `A_DURABLE_BOTTOM` | Exhaustion + trigger + repair + sponsorship + not extended | Highest priority bottom/rebound candidate |
| `TACTICAL_BOUNCE` | Exhaustion + trigger, but weak sponsorship or weak quality | Shorter hold, tighter expectation |
| `EARLY_WATCH` | Exhaustion and histogram curl, but no trigger/reclaim yet | Watchlist / alert |
| `REPAIR_PENDING` | Trigger fired, but RS repair not yet visible | Lower priority; wait for repair |
| `DEAD_MONEY_RISK` | Trigger fired, but no repair/sponsorship and stale/flat | Deprioritize |
| `CHASE_RISK` | Strong chart, but too extended from low/trigger | Avoid fresh buy; maybe hold only |
| `KNIFE_RISK` | Oversold but still deteriorating, no reclaim | Block fresh entry |
| `EVENT_BLACKOUT` | Fresh technical fire inside earnings/event window | Hygiene veto or warning |
| `HOLD_LAUNCHED` | Earlier buy worked; now manage via hold/invalidation | Do not relabel as new bottom |

### 5.3 Why This Helps Decision Making

This structure helps Neural Web avoid three common errors:

1. **Oversold knife:** StochRSI washout fires, but price and RS keep deteriorating.
   - Fix: require repair/reclaim before upgrading from watch to buy.

2. **Dead-money base:** Trigger fired, but the name never launches and has no sector sponsorship.
   - Fix: mark `DEAD_MONEY_RISK`, keep in watch/hold tracker, avoid fresh ranking boost.

3. **Chase after bounce:** MACD/StochRSI signal already worked, but the stock is now extended.
   - Fix: transition to `HOLD_LAUNCHED`, not fresh buy.

It also gives the cortex/Claude a clean explanation surface: "This name is buyable because exhaustion and trigger are present, RS is repairing, and the subsector is accelerating; this other name is only tactical because the trigger fired but quality/flow are weak."

---

## 6. Build Suggestions for Claude

### 6.1 Immediate Build Lane A: Bottom Sensor Envelope

Create a common bottom-sensor payload emitted by existing entry engines.

Suggested module:

- `engine/neuralweb/bottom_sensors.py`

Suggested output:

- `data/neuralweb/bottom_sensors.parquet`
- `site/neuralwebdata/bottom_sensors.json` for display/debug only.

Minimum schema:

```text
symbol
as_of
region
trigger_tier
trigger_age_ticks
exhaustion_score_raw
repair_score_raw
sponsorship_score_raw
entry_zone_score_raw
holdability_score_raw
bottom_state
sensor_versions
source_artifacts
is_display_only
```

The first version can be purely descriptive and compute only from fields already in library rows: confluence tier, COILED, coiled_fire, donor_state, extension, hold_state, RS fields if available, sector/subsector context if already emitted.

### 6.2 Immediate Build Lane B: SPRING / S-UR Study

This is the most mechanism-clean new sensor.

Study object:

- undercut prior 21D/63D low;
- reclaim within 2/3/5 bars;
- test standalone, inside COILED, and near gate fires;
- compare to incumbent gate fires using stop-out, dead-money, cushion, clean-liftoff;
- no same-bar fill;
- include delisted close-only arm for close-based version.

Suggested output:

- `research/entry_stack/S_UR_REPORT.md`
- `engine/species_registry.py` entry if it proceeds.
- Spine engine `spring_reclaim` only if it earns live accrual.

### 6.3 Immediate Build Lane C: Production-Trigger Trio Ablation

There is already `research/entry_intel/P1_3_TRIO_ABLATION_PREREG.md`. Claude should decide whether to expand it to this report's staged model.

Trio factors:

- cohort washout proximity;
- RS inflection / cohort-rank repair;
- anti-chase / extension.

Suggestion:

- Do not only test hard gates.
- Test hard gate, rank-weight, and state-label effects.
- Mandatory fire-rate impact table: a factor that improves quality but kills recall may still be a bad board rule.

### 6.4 Immediate Build Lane D: Neural Web Bottom Classification

After lanes A-C, add a non-authoritative classification layer:

- `A_DURABLE_BOTTOM`
- `TACTICAL_BOUNCE`
- `EARLY_WATCH`
- `DEAD_MONEY_RISK`
- `CHASE_RISK`
- `KNIFE_RISK`
- `HOLD_LAUNCHED`

This should be display-only and logged before it ranks anything.

### 6.5 Immediate Build Lane E: Earnings Blackout Hygiene

This is likely the fastest safety improvement.

Build:

- event blackout emitter;
- next earnings date freshness semantics;
- stale rows fail open with warning;
- T-3 through T+0 fresh-entry suppression tested first.

Important:

- This is not alpha. It is variance hygiene.
- It should not hide the signal; it should explain that the technical setup exists but fresh entry is event-contaminated.

### 6.6 Immediate Build Lane F: Sector/Theme Sponsorship Connector

Neural Web should ingest Oracle/subsector rotation and flow velocity into bottom decisions.

Build:

- map stock to sector/subsector/theme exposures;
- attach current velocity and acceleration;
- attach flow velocity where available;
- classify sponsorship as `tailwind | neutral | headwind | stale | unavailable`.

Critical constraint:

- Sponsorship should prioritize and contextualize.
- It should not hard-block bottom entries unless a separate gauntlet proves that gate.

### 6.7 Medium-Term Build Lane G: Vol-Scaled Entry Zone

The fixed -5% stop is too crude for volatile bottom names. Prior S7 zone addendum suggests the typical washout zone may trade 6-8% below fill before working.

Build:

- per-fire sigma20 x sqrt(20) band;
- clamp to 5-15%;
- report whether the zone held;
- use as board stop-guidance context and research metric.

This helps Neural Web distinguish:

- a real failure;
- normal washout noise;
- a too-early but still valid zone.

### 6.8 Medium-Term Build Lane H: Quality/Holdability Overlay

For 63D/126D holds:

- Piotroski;
- Altman;
- Sloan;
- balance-sheet stress;
- profitability stability;
- liquidity/spread proxies.

This should create `HOLDABILITY` chips, not initial buy gates. A good bottom in a bad balance sheet is a tactical bounce; a good bottom in a strong business can be a positional hold.

### 6.9 Deferred Lane I: Options/Order Flow

Per existing plan, per-name options surface is too young. Do not force it.

Accrue:

- skew/IV spread;
- call/put premium imbalance;
- sweep concentration;
- GEX if available;
- IV crush risk around earnings.

Revisit when event floors are available.

---

## 7. Recommended Sensor Priority Ranking

### Highest priority

1. **S-UR / spring reclaim**
   - Most direct absorption evidence.
   - Mechanically different from MACD/StochRSI.
   - Likely to catch early durable turns.

2. **Within-cohort RS repair**
   - Better framed than vs-SPY repair.
   - Helps avoid names still bleeding inside their own group.

3. **Sector/subsector rotation velocity**
   - Gives sponsorship and priority.
   - Should help Neural Web find which bottoms deserve attention first.

4. **Anti-chase / entry-zone score**
   - Prevents buying the same successful signal too late.
   - Should reduce immediate post-buy drawdown and dead-money perception.

5. **Earnings blackout**
   - Clean hygiene improvement.
   - Reduces uncontrolled event variance.

### Second priority

6. **Vol-scaled entry zone**
   - Improves measurement and stop guidance.
   - Important for high-vol bottom names.

7. **Squeeze release**
   - Useful if defined as release-bar-only.
   - Must avoid repeating calm-base arming failures.

8. **Quality overlay**
   - Especially useful for medium-term holds.
   - Should stratify holdability, not entry.

9. **Liquidity/spread deterioration**
   - Cost/MAE hygiene.
   - Useful for tradability, not return prediction.

10. **Flow velocity**
   - Valuable in China/HK and where data is live.
   - Needs freshness and market-specific treatment.

### Lower priority / caution

11. Generic OBV/CMF/RVOL confirmation.
12. ADX/trend alignment as a positive filter.
13. KST/multi-ROC oscillator stacking.
14. Fibonacci/Elliott/candlestick taxonomy.
15. Per-name options surface before sample depth exists.

---

## 8. Suggested Neural Web Integration Contract

Each surviving sensor should feed Neural Web like this:

```text
engine_name: bottom_<sensor>
signal_id: {engine}:{as_of}:{symbol}:{horizon}:{version}
symbol: ticker
as_of: completed-bar known date
horizon: 21d | 63d | 126d
direction: +1 for favorable bottom/rebound context; 0 for hygiene/context only
strength: bounded numeric if measured; null if display-only
size_binding: false
is_display_only: true until promotion
meta:
  bottom_stage: exhaustion | trigger | repair | sponsorship | anti_chase | holdability | hygiene
  trigger_tier: optional
  source_artifacts: list
  freshness_days: int
  regime_bucket: market/sector/world-state bucket
  version: frozen definition version
```

### 8.1 Kernel cells

Recommended initial cells:

- `(confluence_gate, world_state_bucket, 21d)`
- `(coiled, world_state_bucket, 21d)`
- `(coiled_fire, world_state_bucket, 21d)`
- `(spring_reclaim, world_state_bucket, 21d)`
- `(rs_cohort_repair, world_state_bucket, 21d)`
- `(anti_chase_clear, world_state_bucket, 21d)`
- `(sector_velocity_tailwind, world_state_bucket, 21d)`
- `(quality_holdable, world_state_bucket, 63d)`
- `(event_blackout, all, hygiene)`

### 8.2 Confluence graph edges

Display-only edges to track:

- `confluence_gate x COILED`
- `confluence_gate x S-UR`
- `COILED x S-UR`
- `COILED x RS repair`
- `RS repair x sector velocity`
- `trigger fresh x anti-chase clear`
- `event blackout x fresh trigger`
- `sector velocity tailwind x flow velocity`

### 8.3 State machine integration

Every candidate should map into the state machine:

```text
WATCH -> ARMED -> FIRE -> BASE/RETEST -> LAUNCHED -> HOLD -> INVALIDATED
```

Proposed mapping:

- Exhaustion without trigger = `WATCH`.
- Exhaustion + early histogram curl = `ARMED`.
- Trigger + not extended = `FIRE`.
- Trigger stale but unbroken = `BASE/RETEST`.
- Max-up > threshold or OB-persist = `LAUNCHED`.
- Launched and above invalidation = `HOLD`.
- Close below invalidation = `INVALIDATED`.

This avoids the operator's known pain point: a valid signal fires, bases, falls off the board, then the system goes silent while the trade is still alive.

---

## 9. Validation Protocol Claude Should Enforce

### 9.1 Required metrics

For every new sensor:

- stop-out rate;
- dead-money rate;
- clean-liftoff rate;
- cushion incidence;
- MFE/MAE;
- days-to-10%;
- recall versus durable bottoms;
- fire-rate impact;
- per-name majority;
- era split;
- regime split;
- same-computable-subset baseline.

### 9.2 Required controls

- T+1 or next-known-bar entry; no same-bar fill.
- Completed higher-timeframe bars relabeled to last constituent trading day.
- Episode/block bootstrap.
- BH/FDR where families test multiple variants.
- Delisted-inclusive or survivor-stamped where applicable.
- Static/current sector maps must be treated as context unless PIT membership exists.
- Nulls printed.
- Recall printed next to precision.

### 9.3 Promotion rules

- **Display chip:** useful and coherent, but not enough to rank.
- **Rank bonus:** improves safety/quality without destroying recall.
- **Hygiene veto:** only for event/cost physics, not alpha guesses.
- **Hard gate:** rare; only if the gate survives its own gauntlet and does not starve the board.
- **Kernel consumption:** only after event floors and FDR clock.

---

## 10. Claude Review Questions

Claude/Fable should explicitly rule on these:

1. Should this report become an appendix/amendment to `ENTRY_STACK_EXPANSION_MASTERPLAN_BY_FABLE.md`, or should it live as a Neural Web bottom-sensor program?
2. Should `bottom_sensors.parquet` be a new Neural Web artifact, or should these fields be appended to existing spine/index rows?
3. Should S-UR be promoted as the next highest-priority species after W0 foundations?
4. Should the production-trigger trio ablation be expanded to include state labels, not only gate/rank-weight tests?
5. Should sector/subsector velocity be a Neural Web sponsorship sensor, an Oracle-only artifact, or both?
6. What is the correct event budget for rare sensors like S-UR inside regime cells?
7. Should vol-scaled entry-zone outcomes become co-primary for bottom/rebound studies?
8. Should the bottom/rebound state labels be displayed on the Committee View before any ranking authority is granted?
9. How should the system avoid double-counting COILED when COILED is both an exhaustion sensor and a confluence edge participant?
10. Which surfaces should show the final output first: US stock board, Top Setups, Committee View, or stock detail pages?

---

## 11. Suggested First PR Sequence

### PR 1: Descriptive bottom sensor envelope

- Add bottom sensor schema and builder.
- Populate from existing fields only.
- Emit display-only artifact.
- Add tests for determinism and schema.

### PR 2: Committee/QA display

- Add a bottom/rebound profile block to Committee View or a QA page.
- Show the six subscores and state label.
- No ranking changes.

### PR 3: S-UR prereg and primitives

- Add undercut/reclaim primitives.
- Register frozen definitions.
- Add leak tests and no same-bar-fill tests.

### PR 4: Production-trigger trio ablation execution

- Run only after replay/golden/PIT gates are clean.
- Include hard-gate, rank-weight, and state-label impact.

### PR 5: Sponsorship connector

- Attach sector/subsector velocity and flow context.
- Display-only.
- Add Neural Web confluence edges.

### PR 6: Earnings blackout hygiene

- Build event blackout emitter.
- Test T-3/T+0.
- If it earns, ship as hygiene warning/veto.

---

## 12. External Indicator Reference Anchors

These are definition references only, not evidence that an indicator works in this repo:

- StockCharts technical indicators index: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays
- StockCharts MACD Histogram definition: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/macd-histogram
- StockCharts Average True Range: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/average-true-range-atr
- StockCharts Chaikin Money Flow: https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/chaikin-money-flow-cmf
- Fidelity technical indicator guide: https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/overview

---

## 13. Bottom Line

Neural Web should become excellent at bottom/rebound capture by doing what human chart reading does well, but with better memory:

- identify real washout;
- wait for a fresh turn;
- require some evidence of repair;
- prioritize names with sector/theme/flow sponsorship;
- avoid stale or overextended entries;
- separate tactical bounce from durable hold;
- learn which sensors matter by regime and horizon.

The first build should be a display-only bottom/rebound sensor envelope. The highest-value new research should be S-UR spring reclaim, within-cohort RS repair, anti-chase/entry-zone scoring, sector velocity sponsorship, and earnings blackout hygiene. These should feed Neural Web as staged sensors, not as a hand-built master score.

If Claude agrees, this becomes a practical bridge between the operator's 3D MACD/StochRSI timing intuition and the repo's evidence-earned Neural Web architecture.
