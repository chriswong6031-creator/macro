# Options Data as Entry Intelligence for Neural Web

_Prepared for Fable, 2026-07-05._

## Executive Verdict

Options data can help us find unusually good stock entries, but the edge is not "GEX says buy" or
"large call sweep equals bullish." The credible edge is more specific:

1. **Informed demand:** option traders sometimes express information before it shows up in the
   stock. The strongest literature-backed families are buyer-initiated/opening option volume,
   matched call-put IV spreads, OTM-put skew/smirk, and abnormal short-dated OI/volume.
2. **Entry quality:** options state can tell us whether a price signal is likely to get clean
   follow-through or get chopped/stop-run. This is where it fits our existing durable-bottom
   work best.
3. **Pressure map:** GEX, walls, max-pain/pinning, and gamma flips are better as volatility,
   barrier, and stop-placement context than as directional alpha.
4. **Neural Web integration:** options signals should enter as bus artifacts, stamped context,
   confluence/contradiction edges, and graded hypotheses. Neural Web should not let options
   originate buys until the options entry harness earns authority under the existing constitution.

The build target is an **Options Entry Intelligence layer**: a ticker/day state vector that says
"this existing long setup has cleaner bottom/liftoff odds," "this existing long setup is fragile,"
or "this extended name has topping pressure." It should feed Neural Web as a confirmer, cautioner,
reflex trigger, and hypothesis source before it ever becomes a ranking weight.

## Local Context Already in Place

The repo already contains most primitives:

- `engine/options_flow.py` and `scripts/build_options_flow.py` create measured flow context:
  premium, put/call, 0DTE share, dealer gamma flow, delta flow, vol>OI fresh positioning, and
  day-over-day OI positioning.
- `engine/options_stamp.py` stamps US board fires with PIT options state:
  `opt_gamma_regime`, `opt_dist_to_flip_pct`, `opt_wall_up`, `opt_wall_down`, `opt_iv30`,
  `opt_iv_rank_252`, `opt_doi_slope_5d`, `opt_voi_flag`.
- `scripts/validate_options_entry.py` is the right machine: it asks whether options context
  reduces stop-outs/dead money and improves clean liftoffs on entries the price thesis already
  likes.
- `engine/options_ivspread.py` implements the Cremers-Weinbaum matched call-put IV spread.
- `engine/options_skew.py` implements the Xing-Zhang-Zhao IV smirk/skew.
- `scripts/build_gex_board.py`, `engine/gex_model.py`, and `engine/gex_engine.py` already create
  GEX heatmaps, walls, flip, max pain, IV30, put/call OI, and related structure.
- `config/synapse.yml` already registers `options-flow-index` and `polygon-gex-summaries`.
- `config/dag.yml` already has `build_options_flow`, `build_options_skew`,
  `build_options_ivspread`, `stamp_options_state`, and `validate_options_entry`.

Important existing doctrine:

- Raw GEX is display/context only. Prior repo research found raw multi-year GEX score integration
  did not clear the bar. Do not resurrect it as a directional stock signal.
- Flow direction has historically been soft unless calibrated to trade+NBBO. Magnitude, OI change,
  walls, IV, and vol>OI are more reliable than signed tape labels.
- Neural Web's Article 1 forbids LLM-originated signals. Options must become registered artifacts
  and graded claims, not ad hoc cortex intuition.

## External Evidence, Compressed

### 1. Option volume can lead stock returns when it is opening/buyer initiated

Pan and Poteshman find that put-call ratios built from buyer-initiated opening volume predict
future stock returns: low put-call ratios outperform high put-call ratios by more than 40 bps next
day and more than 1% over the next week. The economic read is informed traders using options
before equity prices fully reflect the information.

Build implication: generic volume is noisy; **opening, buyer-initiated, short-horizon, leveraged
contracts matter most**. If we do not have true open/close and buyer/seller tags, use softer proxies:
vol>prior-OI, day-over-day call/put OI changes, premium z-scores, OTM/short-dated contract emphasis,
and calibrated NBBO signing when available.

### 2. Call-put IV spread is one of the cleanest directional options features

Cremers and Weinbaum show that deviations from put-call parity measured by matched call-put IV
differences contain return information: stocks with relatively expensive calls outperform stocks
with relatively expensive puts by about 50 bps per week. This maps directly to our
`engine/options_ivspread.py`.

Build implication: this is a **cross-sectional relative signal**, not an absolute level. It should
confirm long entries when the stock's existing price/setup thesis is already constructive and
caution long entries when matched puts are rich.

### 3. IV smirk/skew is more useful as crash/top risk than as a bottom trigger

Xing, Zhang, and Zhao find that stocks with steep volatility smirks underperform by about 10.9%
per year on a risk-adjusted basis, and steep smirks are associated with negative future earnings
shocks. This maps to our `engine/options_skew.py`.

Build implication: steep OTM-put skew is primarily a **durable-top / avoid-long / de-risk** input.
For bottoms, the useful signal is often **skew deceleration** or **skew compression after capitulation**,
not "skew is high."

### 4. Gamma changes path quality more than direction

Recent gamma-positioning work finds positive gamma can sustain liquidity in stress and reduce
volatility, while negative gamma can deplete liquidity and make markets more failure-prone.
Expiration research also shows stock prices cluster near option strikes on expiration dates, with
market-maker hedge rebalancing contributing to the effect.

Build implication: GEX/walls should answer:

- Is this tape likely to pin/chop or trend?
- Where is the nearest likely support/resistance/magnet?
- Is a breakout likely to need force to clear a wall?
- Should a stop be tucked beyond an options wall rather than at an obvious price level?

It should not answer "buy this stock."

### 5. OI is slower but more structural than intraday flow

OCC/OIC descriptions matter operationally: volume is session activity; open interest is the number
of contracts still open after opening/closing/exercise/assignment are netted. Cboe's open-close
data explicitly classifies trades by participant, buy/sell, and open/close, including intraday
1-minute or 10-minute products.

Build implication:

- If we have open/close tags, use them as the gold standard.
- If not, day-over-day OI change is still valuable because it tells us what positions actually
  survived the session.
- Intraday flow is faster but should be lower authority unless trade signing and open/close
  inference are measured.

## Signal Taxonomy for Our System

### A. Directional Informed-Demand Signals

These can eventually influence selection, but only after gates pass:

- **CW IV spread:** matched call IV minus matched put IV, near 30D, OI-weighted and
  cross-sectionally relativized.
- **Open-buy put/call ratio:** gold standard if Cboe open-close or equivalent is licensed.
- **Delta-adjusted net opening call/put OI:** day-over-day OI change, near-money and high-gamma
  weighted.
- **Short-dated OTM call/put information factors:** premium- and probability-weighted OI/volume
  in high-leverage contracts.
- **Vol>OI fresh-positioning bursts:** current proxy for "this contract traded more today than
  existed yesterday."

### B. Risk/Crash/Topping Signals

These should mainly de-escalate or veto longs:

- **Steep OTM-put skew:** especially rising 5D/10D skew.
- **Put IV bid rising while stock still rising:** topping divergence.
- **Put OI build below spot with negative gamma:** fragility underneath.
- **0DTE/high short-dated premium concentration after extension:** reflexive squeeze/chop risk.
- **Call wall exhaustion:** spot pinned below a large call wall while call demand fades.

### C. Entry-Quality / Bottom Signals

These should amplify existing bottom/bounce setups:

- **Skew peaked then compressing:** fear was real, but marginal protection demand is fading.
- **IV rank high but falling, not exploding:** panic premium decays after a washout.
- **Positive or improving CW IV spread:** calls begin pricing richer than matched puts.
- **Call OI slope positive near money:** participants are adding upside structures.
- **Vol>OI call burst after price reclaim:** fresh upside positioning after the stock proves life.
- **Spot reclaims gamma flip / moves from short-gamma to long-gamma zone:** path becomes less
  fragile.
- **Put wall below spot with enough distance:** cleaner stop structure; floor is no longer directly
  under attack.

### D. Structure/Pressure Signals

These should change timing, stop placement, or confidence:

- **Gamma regime:** long gamma = mean reversion/pinning; short gamma = trend/fragility.
- **Distance to gamma flip:** close to flip = nonlinear regime-change zone.
- **Call/put walls:** resistance/support or breakout force levels.
- **Max pain / pinning:** useful near expiration, not a standalone thesis.
- **Charm/vanna/charm anchor:** useful mainly for index/ETF context and OPEX weeks.

## Durable Bottom Playbooks

### Bottom Type 1: Panic Washout Turning Into Clean Liftoff

Use when price/macro signals already detect capitulation or bottoming alignment.

Required price context:

- Stock is near a 60D/120D low or had a high-volume washout.
- Relative strength is repairing versus SPY/sector.
- Price has reclaimed a short-term pivot, VWAP, 8/21 EMA, or our existing bottom trigger.

Options confirmation:

- IV rank was high but is now falling or flattening.
- OTM-put skew is compressing from an extreme.
- Put/call OI pressure stops worsening.
- Near-money call OI slope turns positive.
- Vol>OI call burst appears after price reclaim, not before.
- Spot is above a put wall or has reclaimed gamma flip.

Neural Web interpretation:

- "Fear premium is decelerating while upside positioning begins to accumulate."
- Amplify bottom confidence; do not originate the buy.
- Strongest when existing bottom signal says bounce and options state says lower stop-out odds.

Failure mode:

- High IV + high skew + negative gamma + no call OI improvement is not a bottom. It is often an
  active crash state.

### Bottom Type 2: Coiled Base Before Breakout

Use when price is basing rather than crashing.

Required price context:

- Tight range / volatility contraction / coiled state.
- Relative strength stable or improving.
- No stale monthly overextension.

Options confirmation:

- IV rank low-to-mid but rising gently, not panic-spiking.
- CW IV spread positive versus peers.
- Call OI slope positive for 3-5 sessions.
- Vol>OI call burst in 8-45D tenor.
- Price is not immediately below a major call wall unless flow is strong enough to challenge it.

Neural Web interpretation:

- "Options market is paying for upside before price expansion."
- Good top-pick amplifier for prebreakout/entry-stack setups.

Failure mode:

- Huge 0DTE call burst into a call wall without durable OI follow-through is often a retail chase
  or expiry pin setup, not a durable entry.

### Bottom Type 3: Squeeze/Reflexive Repricing Candidate

Use sparingly. This is a tactical bounce family, not automatically a durable bottom.

Required price context:

- High short interest/crowding or known squeeze-prone name.
- Stock has stopped making new lows or has reclaimed a trigger.

Options confirmation:

- Short-gamma regime.
- Large OTM call vol>OI burst.
- Call OI concentration above spot.
- IV rising with price, not against it.
- Borrow/short-interest context if available.

Neural Web interpretation:

- Mark as **tactical convexity**, not durable quality.
- Route to a separate bounce-strength output, respecting the prior bottom-backtest doctrine.

Failure mode:

- It can work violently and then fail. Do not let it contaminate durable-bottom scoring.

## Durable Top / Avoid-Long Playbooks

### Top Type 1: Euphoria Into Call Wall

Required price context:

- Stock extended versus trend, high momentum, near upper range.
- Existing lagging/extension detector or stale-trend veto is active.

Options warning:

- Heavy call premium but decelerating call OI.
- Spot sits below or at large call wall / max-pain zone near OPEX.
- Long-gamma pinning prevents clean continuation.
- IV spread stops improving.

Neural Web interpretation:

- Reduce entry confidence and flag "chase risk."
- For existing longs, this is trim/watch context, not a short signal by itself.

### Top Type 2: Hidden Protection Bid

Required price context:

- Stock still rising or sideways, but breadth/RS momentum weakening.

Options warning:

- OTM-put skew steepens.
- Matched puts become richer than calls relative to peers.
- Put OI accumulates below spot.
- Negative gamma increases.

Neural Web interpretation:

- Strong avoid-long / de-escalation signal.
- If existing price signals are bullish, register a contradiction edge.

### Top Type 3: Post-Squeeze Exhaustion

Required price context:

- Sharp recent rally, high turnover, social/retail/0DTE attention.

Options warning:

- IV extreme and rising into price extension.
- 0DTE/weekly call share dominates.
- Call buying is mostly same-day volume, not durable OI.
- Put skew remains elevated underneath.

Neural Web interpretation:

- Tactical bounce may be real, durable quality poor.
- Split the output: high bounce strength, low durable-entry quality.

## Top-Pick Ranking: How Options Should Amplify Picks

For a candidate already surfaced by US stocks, setup species, entry stack, or bottom engine, compute
two separate scores:

### 1. Options Entry Quality

Purpose: rank entries likely to avoid immediate stop-out and produce clean 5-21D follow-through.

Inputs:

- `opt_iv_rank_252` state and 5D change.
- `opt_doi_slope_5d`.
- `opt_voi_flag`.
- `ivspread_rel` and 5D change.
- `skew` and 5D change.
- `dist_to_flip_pct`.
- distance to put wall/call wall.
- gamma regime.
- OPEX days and wall proximity.

Output:

- `options_entry_quality`: -3 to +3, display/shadow until gate.
- `options_entry_reason`: short structured reason list.
- `options_entry_contra`: whether it contradicts price thesis.

### 2. Options Convexity / Bounce Strength

Purpose: find names with tactical squeeze/bounce potential.

Inputs:

- short-gamma regime.
- high vol>OI call burst.
- OTM/short-dated call concentration.
- rising IV with rising price.
- call wall distance / breakout force.
- high realized compression before burst.

Output:

- `options_convexity`: 0 to 100.
- Explicit flag: tactical, not durable.

This separation is essential. It matches the prior bottom research conclusion: tactical bounce edge
and durable-bottom quality are different animals.

## Neural Web Integration Design

### Layer 1: Artifact Registration

Add or tighten Synapse artifacts:

- `options-entry-gate`: `data/options_entry/gate.json`, producer
  `scripts/validate_options_entry.py`, tier `shadow` until passed.
- `options-skew-snapshots`: `data/options_skew/snapshots.parquet`, producer
  `scripts/build_options_skew.py`, tier `confirmer`.
- `options-ivspread-snapshots`: `data/options_ivspread/snapshots.parquet`, producer
  `scripts/build_options_ivspread.py`, tier `confirmer`.
- `live-options-flow-current`: R2/API `live_flow/feed_current.json` or local mirror, tier
  `display` or `shadow`.
- `options-entry-state`: new compact per-ticker/day state described below.

### Layer 2: New Compact State Vector

Build `engine/options_entry_state.py` and `scripts/build_options_entry_state.py`.

Output:

`data/options_entry/state.parquet`

Suggested columns:

- `as_of`, `ticker`
- `iv_rank_252`, `iv_rank_5d_chg`, `iv30`
- `ivspread_rel`, `ivspread_5d_chg`, `ivspread_tone`
- `skew`, `skew_5d_chg`, `skew_tone`
- `doi_call_slope_5d`, `doi_put_slope_5d`, `doi_pc`, `doi_tone`
- `voi_call_flag`, `voi_put_flag`, `fresh_premium_mn`
- `gamma_regime`, `dist_to_flip_pct`, `spot_vs_flip`
- `call_wall_dist_pct`, `put_wall_dist_pct`, `max_pain_dist_pct`
- `opex_days`, `wall_pin_risk`
- `options_entry_quality_shadow`
- `options_convexity_shadow`
- `options_contradiction_flag`
- `evidence_quality`: full / partial / thin / stale
- `scored`: false until gate promotion

This state vector is the missing connective tissue. It lets Neural Web read one stable table
instead of separately understanding GEX, flow, skew, IV spread, and live flow.

### Layer 3: Stamp Every Existing Fire

Extend `options_stamp.py` or a sibling stamp module so every existing US board/entry-stack fire gets:

- current options state vector ID/hash
- the fields currently in `STAMP_COLS`
- IV spread relative rank
- skew relative rank and change
- call/put wall distance
- OPEX/pin risk
- quality flags

This makes the entry-quality harness stronger without creating a new ledger.

### Layer 4: Neural Web Spine Adapter

Add an adapter in `engine/neuralweb/query.py`:

- ledger name: `options_entry`
- claim type: `context_confirmer`
- family: `options.entry_quality`, `options.convexity`, `options.top_risk`
- horizon: 5/10/21/63 as appropriate
- outcome source: existing `retro_grades.parquet`
- graded outcome: clean liftoff, stop breach, MFE, forward return

Rules:

- `options_entry_quality_shadow > 0` can be graded against existing long fires.
- `options_contradiction_flag=True` can be graded as "did it correctly de-escalate bad longs?"
- `options_convexity_shadow` is graded separately on MFE fat-tail, not clean durability.

### Layer 5: Confluence Graph Edges

Add edges:

- `price_bottom_signal CONFIRMED_BY options_entry_quality`
- `price_prebreakout CONFIRMED_BY ivspread_positive + call_doi`
- `price_bottom_signal CONTRADICTED_BY skew_rising + negative_gamma`
- `extension_signal CONFIRMED_BY skew_rising / call_wall_pin`
- `risk_off_world_state AMPLIFIES negative_gamma / put_skew`
- `oracle_rotation_lobe CONFIRMED_BY sector options aggregation`

These are graph edges, not score weights. They give cortex and committee views a way to explain
why a name is cleaner or more fragile.

### Layer 6: Cortex Read Tools

Expose read-only tools:

- `read_options_entry_state(ticker=None, date=None, top_n=...)`
- `explain_options_context(ticker)`
- `query_options_confluence(ticker)`
- `list_options_contradictions()`

The cortex can flag attention or stake hypotheses, but cannot directly rank or buy.

### Layer 7: Promotion Path

Promotion should follow the existing constitution:

1. Display/context.
2. Shadow confirmer: visible to Neural Web and admin, no user-facing score impact.
3. Caution-only: allowed to lower confidence if it reduces stop-outs.
4. Bounded confirmer: allowed to add a small confidence nudge if entry harness passes.
5. Scored component: only after FDR-governed, post-registration evidence.

Never jump directly from a pretty heatmap to score influence.

## Concrete Build Plan

### Phase A: Connect the Dots, No New Alpha Claims

1. Build `options_entry_state.py` to fuse GEX, flow summary, IV spread, skew, and stamped OI
   features into one ticker/day table.
2. Register it in Synapse.
3. Add an admin/Neural Web panel section: "Options Entry State."
4. Add cortex read-only tools.
5. Add confluence graph edges as display/shadow.

Acceptance:

- Every field has `as_of`, source artifact, freshness, and quality flag.
- Missing options data produces nulls, not fake neutral.
- No score/rank/sizing consumer changes.

### Phase B: Make Existing Fires Learn From Options

1. Extend `scripts/stamp_options_state.py` to stamp IV spread, skew, wall distances, OPEX risk.
2. Extend `scripts/validate_options_entry.py` with new pre-registered buckets:
   - `S-IVSPREAD`: positive relative IV spread.
   - `S-SKEW_DECEL`: high skew but falling.
   - `S-TOP_RISK`: rising skew / puts-rich / negative gamma on extended names.
   - `S-PIN_RISK`: near call wall + OPEX + long gamma.
3. Emit `data/options_entry/gate.json` with per-family verdicts.
4. Add spine adapter.

Acceptance:

- No verdict under n < 30 per bucket.
- Metrics remain ledger primitives: stop breach, clean liftoff, MFE, fwd return.
- Tactical convexity and durable quality remain separate.

### Phase C: Live Flow Reflexes

Live flow is most useful as a fast attention/reflex layer:

- "candidate already on watchlist gets fresh call vol>OI after reclaim"
- "existing top pick suddenly receives steep put demand / negative gamma"
- "price reaches a major wall / flip zone"
- "options contradiction appears against a Neural Web high-priority name"

Build:

- `engine/neuralweb/reflexes.py` mirroring lane for `options_flow_attention`.
- R2/API live flow reader with stale guards.
- Single-writer JSONL firings:
  `data/reflexes/options_flow_attention/firings.jsonl`.

Acceptance:

- It only flags attention.
- It never auto-generates a buy.
- It is graded like cortex attention later.

### Phase D: Sector/Theme Aggregation

Build sector options aggregates for Neural Web:

- sector call/put DOI pressure
- sector IV spread median
- sector skew median and change
- sector negative-gamma share
- sector wall pressure relative to ETF

Use cases:

- Confirm Oracle/rotation lobe when sector price leadership is matched by call OI / IV spread.
- De-escalate sector breakouts when protection demand rises.
- Identify sector-wide bottoming when price breadth repairs and options fear decelerates.

### Phase E: True Open/Close Upgrade

If Fable wants the best path to real option-flow edge, the data upgrade is not more GEX. It is
open/close, participant-type, and buy/sell classification.

Target data:

- Cboe Open-Close Volume Summary or equivalent.
- Intraday 1-minute/10-minute open-close if licensing allows.
- ThetaData trade+NBBO to calibrate signing and sweep/block classification.

Why:

- Literature edge is strongest in buyer-initiated opening demand.
- Our current proxies are good enough to accrue and study, but not enough to claim a live
  directional tape edge.

## Signal Recipes

### Recipe 1: Durable Bottom Amplifier

```
price_bottom_candidate
AND rs_repair
AND iv_rank_252 high_or_mid
AND iv_rank_5d_chg <= 0
AND skew_5d_chg < 0
AND (ivspread_rel > 0 OR ivspread_5d_chg > 0)
AND doi_call_slope_5d > 0
AND spot_above_put_wall
AND not pin_risk
```

Expected behavior:

- Fewer immediate post-entry stop breaches.
- More 21D clean liftoffs.
- Not necessarily the highest 5D bounce.

### Recipe 2: Tactical Bounce / Squeeze Candidate

```
price_reclaim_or_bottom_trigger
AND gamma_regime == short
AND voi_call_flag
AND fresh_premium_mn high
AND otm_call_concentration high
AND call_wall_dist_pct > breakout_room_min
```

Expected behavior:

- Higher MFE fat tail.
- More failed round trips.
- Must be labeled tactical.

### Recipe 3: Avoid-Long / Topping Risk

```
price_extended
AND (skew_5d_chg > 0 OR ivspread_rel < 0)
AND put_doi_slope_5d > 0
AND (gamma_regime == short OR call_wall_dist_pct <= near_wall)
```

Expected behavior:

- Lower clean-liftoff rate for new long entries.
- Useful as de-escalation and contradiction.

### Recipe 4: OPEX Pin/Chop Warning

```
opex_days <= 5
AND gamma_regime == long
AND min(abs(spot-call_wall), abs(spot-put_wall), abs(spot-max_pain)) <= threshold
AND no strong fresh opening demand
```

Expected behavior:

- Lower breakout follow-through.
- Better wait/avoid timing.

## How to Use Options Data by Timeframe

### Intraday to 2D

Best inputs:

- live premium z-score
- vol>OI bursts
- 0DTE share
- sweep/block-like clusters
- spot versus wall/flip
- gamma regime

Use:

- attention/reflex
- "wait for wall reclaim"
- "do not chase into OPEX pin"

Risk:

- false direction from signing, retail 0DTE noise.

### 3D to 10D

Best inputs:

- day-over-day OI change
- IV spread change
- skew change
- vol>OI that survives into OI
- wall/flip structure

Use:

- entry timing
- top-pick amplification
- tactical bounce filter

### 10D to 63D

Best inputs:

- CW IV spread level/rank
- XZZ skew/smirk level
- IV rank/VRP
- persistent OI accumulation
- sector options aggregation

Use:

- durable-bottom quality
- durable-top/avoid-long risk
- Neural Web kernel conditioning after enough history.

## Guardrails

1. Do not use raw GEX as direction.
2. Do not trust flow direction unless the signing gate says it is reliable.
3. Keep 0DTE separate from durable positioning.
4. Use OI change for structure; use live flow for attention.
5. Use IV spread for directional lean; use skew for crash/top risk.
6. Separate tactical convexity from durable quality.
7. Never let options originate a score before post-registration evidence.
8. Every options-derived field must carry freshness and data-quality flags.
9. Around earnings, single-name GEX/walls should be de-weighted or separately flagged.
10. Sector aggregates must suppress thin-coverage sectors.

## Fable Rulings Requested

1. Adopt `options_entry_state` as the canonical connector between options stack and Neural Web.
2. Keep all options signals shadow/display until the existing entry harness gates clear.
3. Approve two outputs for stock candidates:
   - `options_entry_quality_shadow`
   - `options_convexity_shadow`
4. Add a third de-escalation output:
   - `options_top_risk_shadow`
5. Approve Neural Web graph edges for confirm/contradict before any score integration.
6. Prioritize true open/close flow data over more GEX sophistication if procurement is considered.

## Source Notes

- Pan & Poteshman, "The Information in Option Volume for Future Stock Prices":
  https://ideas.repec.org/p/nbr/nberwo/10925.html
- Cremers & Weinbaum, "Deviations from Put-Call Parity and Stock Return Predictability":
  https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/deviations-from-putcall-parity-and-stock-return-predictability/D9BA8F97580328AAFD7988B092FE5D50
- Xing, Zhang & Zhao, "What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?":
  https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/abs/what-does-the-individual-option-volatility-smirk-tell-us-about-future-equity-returns/ECFD16BA9ACBDC8D577D1BD866FBEA72
- Ni, Pearson & Poteshman, "Stock Price Clustering on Option Expiration Dates":
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=519044
- Buis, Pieterse-Bloem, Verschoor & Zwinkels, "Gamma positioning and market quality":
  https://www.sciencedirect.com/science/article/pii/S0165188924000721
- Muravyev, Pearson & Pollet, "Why does options market information predict stock returns?":
  https://www.sciencedirect.com/science/article/pii/S0304405X25001618
- Cboe Open-Close Volume Summary:
  https://datashop.cboe.com/cboe-options-open-close-volume-summary
- OIC, "Open Interest: Why It Matters":
  https://www.optionseducation.org/news/open-interest-why-it-matters
- Springer/RQFA, "Do short-lived options reveal information asymmetry?":
  https://link.springer.com/article/10.1007/s11156-025-01427-z
