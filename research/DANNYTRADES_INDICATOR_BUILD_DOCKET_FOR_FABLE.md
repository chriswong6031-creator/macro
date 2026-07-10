# DannyTrades Indicator Build Docket for Fable

Prepared by Codex, 2026-07-09.

Audience: Fable, Claude, and Macro Dashboard builders.

Status: research and build docket only. This does not authorize a new
directional DannyTrades signal, score, buy gate, trim gate, sizing rule, stop
rule, or portfolio construction rule.

## 0. Executive Ruling

DannyTrades is best understood as a multi-panel discretionary charting grammar:
trend state, duplicate trend confirmation, sponsorship/accumulation proxy,
MACD, RSI, volatility boxes, volume-shelf price memory, support/resistance
geometry, and slow exit review. His public method is a confluence desk, not a
single magic indicator.

For this repo, the buildable value is not "copy Danny's indicators." The
standing DannyTrades rulings already retired all directional reads. The useful
work is to inventory each public indicator, identify the data it would require,
write causal proxies where the formula is public or inferable, and route each
piece into the correct governed home:

- Descriptive DannyTrades chip: already live through `engine/dannytrades_chip.py`.
- Basket-level descriptive tape: already live through `engine/basket_tape.py`.
- Momentum bars / volume shelf / POC / chip-system cost basis: route to Entry
  Intelligence price-memory work, not a DannyTrades signal.
- Volatility hole / black hole variants: route to S-SQ / volatility-compression
  work, not a new DannyTrades family.
- Ichimoku, Bollinger, MACD, RSI, Fibonacci, Gann-style rails: route through the
  technical-lab / indicator-event bus. Avoid colliding with open PR #1840.
- Monthly yellow-candle plus sponsorship-decay trims: future Exit & Trim charter
  only. No live trim authority here.
- Big-leader and concentration logic: Mastermind / Long-Hold context only. No
  fused admission gate inside Macro Dashboard.

The short version for Fable:

1. Do not revive DannyTrades directional chips.
2. Do not blend DannyTrades composite values into any momentum ranker.
3. Keep the public indicator inventory as a source-backed design map.
4. Build missing primitives under existing programs with their own evidence
   rulers, not under the DannyTrades brand.

## 1. Evidence Boundary

Public sources inspected:

- DannyTrades Patreon intro and panel guide, Feb. 13, 2024:
  https://www.patreon.com/DannyTrades/posts/hi-everyone-from-98378381
- DannyTrades strategy post, updated Oct. 5, 2025:
  https://www.patreon.com/DannyTrades/posts/sharing-of-my-on-134759106
- Duplicate public strategy URL surfaced by Patreon search:
  https://www.patreon.com/DannyTrades/posts/sharing-of-my-on-140544204
- DannyTrades black-hole explainer, Nov. 10, 2024:
  https://www.patreon.com/DannyTrades/posts/how-to-interpret-115707443
- DannyTrades proprietary-buy-signal summary, Dec. 10, 2025:
  https://www.patreon.com/DannyTrades/posts/how-to-use-my-10-145491526
- DannyTrades get-started note, Oct. 28, 2025:
  https://www.patreon.com/DannyTrades/posts/how-to-get-with-142214974
- DannyTrades subscriber note, May 2, 2026:
  https://www.patreon.com/DannyTrades/posts/must-read-to-all-157131507
- DannyTrades public X snippets found by search, including:
  https://x.com/dannycheng2022/status/1927596950632689934
  https://x.com/dannycheng2022/status/1998383139337773456
  https://x.com/dannycheng2022/status/2061659717970301314
  https://x.com/dannycheng2022/status/2072162205232136280
  https://x.com/dannycheng2022/status/1971075567110979750
  https://twitter.com/dannycheng2022/status/1940438783750771191

Local repo evidence inspected:

- `research/DANNYTRADES_PHASE0.md`
- `research/DANNYTRADES_SWEEP_AND_NEURAL_WEB_UPGRADE_BY_CODEX.md`
- `research/DANNYTRADES_NW_ADJUDICATION_AND_MASTERPLAN_BY_FABLE.md`
- `research/DO_NOT_REBUILD.md`
- `docs/ACTIVE_BUILD_MAP.md`
- `engine/dannytrades.py`
- `engine/dannytrades_chip.py`
- `engine/basket_tape.py`

Important limitations:

- Danny's proprietary formulas and paywalled videos/posts were not accessed.
- Search snippets from X/Patreon are evidence only for the visible text.
- The word "whale" is public vocabulary, not an observed investor identity.
  With OHLCV, we can infer accumulation-like behavior, not whether institutions
  or retail actually traded.
- Self-reported accuracy, account balance, and hit-rate claims are not audited
  evidence.

## 2. Existing Repo Rulings That Bind This Docket

### 2.1 DannyTrades family status

The in-repo reconstruction already exists:

- `engine/dannytrades.py` implements a causal OHLCV proxy stack.
- `scripts/dannytrades_phase0.py` and related sweeps tested it.
- `engine/dannytrades_chip.py` is now display-only and descriptive.
- `engine/basket_tape.py` emits basket-level descriptive Danny fields and caveats.

The current standing state is stricter than the original phase-0 header:

- All DannyTrades directional chip reads are retired.
- `dt_contra` state is descriptive only.
- The chip's state is permanently neutral for schema stability.
- Extension percentile and accumulation values describe location only.
- Whale motion no longer resolves fade/bounce states.
- The 2021+ survivorship-honest, time-controlled replication was all-null.
- The 64-year panel had one pooled whale-surge fade survivor, but it was
  pre-2010 only, null in the modern era, and survivor-flattered.

### 2.2 Do-not-rebuild constraints

`research/DO_NOT_REBUILD.md` explicitly lists:

- DannyTrades directional chip reads: retired, descriptive only.
- Ticker-cluster bootstrap without time control: forbidden estimator.
- Era-pooled inference across the 2010 break without era split: forbidden.
- Positioning fusion into signal scores: illegal.
- LLM-originated signals, scores, or escalations: forbidden.

Any future DannyTrades-family study must include:

- Calendar-time primary inference.
- Modern-era row for any multi-decade result.
- Survivorship and coverage stamps.
- Explicit non-authority if it is display/context.

### 2.3 Active build collisions

As of the active build map read on 2026-07-09:

- PR #1840 is an open technical-indicator machine / lab PR.
- PR #1891 also touches technical-lab robustness and conflicts with #1840.

Therefore, Fable should not start a parallel generic technical-indicator engine
from this docket. Use this docket as source grammar and routing. Build after
that lane settles or explicitly merge the scope into that lane.

## 3. Full Public Indicator Inventory

### 3.1 Panel 1: candle colors and trend ribbon

Public meaning:

- Red candle: short-term bullish state.
- Yellow candle: short-term bearish state.
- Dark blue candle: uptrend persists.
- Light blue candle: downtrend persists.
- Red ribbon: mid-term uptrend.
- Blue ribbon: mid-term downtrend.

Likely technical substrate:

- Close, high, low, and optionally open.
- Fast and slow moving averages or a ribbon of several averages.
- Slope and price-location filters.
- Momentum confirmation from MACD/RSI.
- Multi-timeframe bars: daily, weekly, monthly.

Current repo proxy:

- `engine.dannytrades.ribbon_trend(close)` uses EMA fast/slow, slow-EMA slope,
  and price above/below the slow EMA.
- `engine.dannytrades.momentum_ok(close)` combines MACD histogram and RSI
  rollover logic.

Better build if Fable wants fuller fidelity:

- Add a descriptive `dt_trend_color_state` helper that outputs:
  `short_color`, `trend_persist_color`, `ribbon_color`, `ribbon_age`,
  `range_high`, `range_low`, and `breached_downside`.
- Compute per timeframe: `D`, `W`, `M`.
- Red/yellow should be event states with age, not buy/sell commands.
- Dark/light blue should be persistence states, not fresh events.
- The lower red-candle range breach should be printed as "range breached",
  not "stop loss".

Implementation sketch:

```text
fast = EMA(close, 20)
slow = EMA(close, 50)
slow_slope = slow - slow.shift(10)
ribbon = up if fast > slow and slow_slope > 0 and close > slow
       = down if fast < slow and slow_slope < 0 and close < slow
       = flat otherwise

red_event = short_momentum_turns_up and ribbon != down
yellow_event = short_momentum_turns_down or close < fast
dark_blue = ribbon == up and no fresh red_event
light_blue = ribbon == down and no fresh yellow_event
```

Required data:

- Minimum: adjusted OHLCV daily bars.
- Better: open/high/low/close to identify true candle ranges.
- Optional: intraday bars for cleaner event dating.

Authority:

- Display/context only.
- Can de-escalate FOMO when red-event age is stale.
- Cannot originate buys, sells, stops, or score bumps.

### 3.2 Panel 2: "technical expert" duplicate panel

Public meaning:

- It mimics Panel 1.
- Green bar means downtrend.
- Red bar means uptrend.
- Purple line is an uptrend line.
- Green line is a downtrend line.

Likely technical substrate:

- Trend-line extraction.
- Moving-average or Supertrend-style directional bars.
- Linear regression channel or pivot-connected trend lines.

Current repo status:

- No separate dedicated Panel 2 proxy is needed.
- Panel 2 is redundant unless it improves calibration versus Panel 1.

Build recommendation:

- Do not build a separate DannyTrades Panel 2 engine now.
- If technical-lab PR #1840 lands an indicator-event bus, represent this as
  `trendline_confirmation_state`, not as a new Danny module.
- Only keep it if it is independently useful for display: "trendline support
  intact", "trendline break", "lower-high line active", etc.

Implementation sketch:

```text
confirmed_pivots = causal pivot highs/lows with delay
uptrend_line = last two higher lows
downtrend_line = last two lower highs
trendline_state = above_uptrend_line / below_downtrend_line / broken / none
```

Required data:

- OHLC.
- A causal pivot detector.
- ATR-scaled tolerance to avoid false breaks.

Authority:

- Display/context only.
- No independent score or gate without its own pre-registration.

### 3.3 Panel 3: whale accumulation/distribution versus retail accumulation

Public meaning:

- Red bars are "whales."
- Green bars are retail accumulation.
- Yellow bars are short-term daily traders and usually ignored.
- Public thresholds: around 35% for momentum, 50% for a stock to rise, 75% for
  a surge.
- Retail green bars disappearing is described as constructive.
- Falling retail accumulation is described as a bottoming clue.

What the data can and cannot know:

- OHLCV can estimate accumulation-like pressure.
- It cannot identify whether buyers were institutions, insiders, funds, or
  retail.
- The correct repo label is `sponsorship_proxy` or `accumulation_proxy`, not
  "whale truth."

Current repo proxy:

- `engine.dannytrades.whale_accumulation()`:
  smoothed Chaikin Money Flow rescaled by trailing percentile.
- `engine.dannytrades.whale_buy_fraction()`:
  rolling share of volume allocated to buying pressure based on close-in-range.
- `engine.dannytrades_chip.assess()` prints accumulation level and motion as
  descriptive values only.
- `engine.basket_tape._whale()` computes basket-level descriptive accumulation.

Better build if Fable wants source-faithful descriptive output:

- Split Panel 3 into separate descriptive fields:
  `accumulation_level`, `accumulation_chg`, `distribution_level`,
  `retail_chase_proxy`, `trader_noise_proxy`, `coverage`.
- Do not fuse these into one sponsorship score.
- Do not use the 35/50/75 thresholds as buy thresholds. They can be printed as
  "Danny public threshold bands" only.

Implementation sketch:

```text
mfm = ((close - low) - (high - close)) / (high - low)
buy_share = clip((mfm + 1) / 2, 0, 1)
accumulation_level = rolling_sum(buy_share * dollar_volume, win) /
                     rolling_sum(dollar_volume, win)
distribution_level = 1 - accumulation_level
accumulation_chg = accumulation_level - accumulation_level.shift(win)
retail_chase_proxy = high volume + large positive return + close far above AVWAP
trader_noise_proxy = high turnover + intraday range expansion + no trend follow
```

Required data:

- Minimum: OHLCV with long enough history.
- Better: dollar volume, float shares, split-adjusted volume, intraday volume
  profile.
- Best: signed trade tape or broker-classified flow, if legally licensed.
- Store law: use `data/massive_stock_day/` for DannyTrades-family studies.

Authority:

- Descriptive only.
- Directional whale reads are closed unless Fable explicitly authorizes a new
  modern-era, survivorship-honest, time-controlled restoration attempt.

### 3.4 Panel 4: MACD

Public meaning:

- MACD below zero is bearish momentum.
- MACD above zero is bullish momentum.
- Fast/slow-line cross curling up is bullish.
- Fast/slow-line cross curling down is bearish.

Technical substrate:

- Adjusted close.
- Standard MACD, usually EMA(12), EMA(26), signal EMA(9).
- Histogram and line slopes.

Current repo proxy:

- `engine.technicals.macd_hist()` is used in `engine.dannytrades.momentum_ok()`.

Build recommendation:

- Keep MACD as an indicator-event family, not as Danny-specific edge.
- Emit event age and timeframe:
  `macd_above_zero`, `macd_cross_up`, `macd_cross_down`, `histogram_curl_up`,
  `histogram_curl_down`.
- Use as context for trend maturity or repair; do not score by itself.

Implementation sketch:

```text
macd = EMA(close, 12) - EMA(close, 26)
signal = EMA(macd, 9)
hist = macd - signal
cross_up = macd > signal and macd.shift(1) <= signal.shift(1)
curl_up = hist.diff() > 0
above_zero = macd > 0
```

Required data:

- Adjusted close.
- Daily, weekly, monthly resamples.

Authority:

- Display/context.
- Can be a confirming feature only inside an existing pre-registered family.

### 3.5 Panel 5: RSI with three sets

Public meaning:

- RSI around 20-30 is oversold and may be a buy indicator.
- RSI above 80-95 is usually a sell signal.
- Danny compares three RSI sets and prior lows.
- Three RSI sets curling up is bullish; curling down is bearish.

Unknown:

- The exact three RSI periods are not public in the sources inspected.

Reasonable proxy:

- Use `RSI(7)`, `RSI(14)`, `RSI(21)` for short/intermediate confirmation, or
  `RSI(14)`, `RSI(21)`, `RSI(50)` for slower weekly/monthly investor context.
- Fable should choose one set and freeze it before any measurement.

Build recommendation:

- Emit a descriptive RSI stack:
  `rsi_fast`, `rsi_mid`, `rsi_slow`, `all_curling_up`, `all_curling_down`,
  `prior_low_divergence`, `overbought_band`, `oversold_band`.
- Regime-condition it. In a strong uptrend, RSI overbought can persist. In a
  downtrend, RSI oversold can also persist.

Implementation sketch:

```text
rsi_fast = RSI(close, 7)
rsi_mid = RSI(close, 14)
rsi_slow = RSI(close, 21)
all_curl_up = rsi_fast.diff() > 0 and rsi_mid.diff() > 0 and rsi_slow.diff() > 0
oversold_stack = count(rsi <= 30)
overbought_stack = count(rsi >= 80)
positive_divergence = price makes lower low while RSI_mid makes higher low
```

Required data:

- Adjusted close.
- Causal swing-low detection for divergence.

Authority:

- Context only unless a specific RSI event is tested in a registered family.

### 3.6 Volatility hole / black hole

Public meaning:

- The black hole is presented publicly as a neutral volatility and trend
  direction structure.
- It has many levels; the most important are upper resistance and lower final
  support.
- A subsequent close above the upper level implies emerging or ongoing uptrend.
- A subsequent close below the lower level implies ongoing or emerging downtrend.
- Candle colors are used to refine the interpretation.
- Public strategy posts treat a close above the upper boundary as a possible
  buy/accumulation signal, and the lower break as the bearish mirror.

Current repo proxy:

- `engine.dannytrades.volatility_hole()`:
  Bollinger-bandwidth squeeze, sticky range, close-beyond-edge breakout.
- `engine.basket_tape._volhole()`:
  basket-level compression and expansion state.

Better build:

- Move future work to S-SQ / volatility-compression, not DannyTrades.
- Represent a box as a state object:
  `box_upper`, `box_lower`, `box_mid`, `box_width_pct`, `compression_age`,
  `close_position`, `breakout_up`, `breakdown`, `retest_state`,
  `false_break_state`, `time_since_resolution`.
- Keep unresolved boxes non-directional.
- If Fable wants multiple definitions, pre-register the family and FDR budget.

Implementation sketch:

```text
bb_width = (upper_band - lower_band) / mid_band
bb_width_pctile = rolling_percentile(bb_width, 126)
squeeze = bb_width_pctile <= 0.25
box_upper = rolling_max(high where squeeze, 20).ffill()
box_lower = rolling_min(low where squeeze, 20).ffill()
breakout_up = close > box_upper and prior_close <= prior_box_upper
breakdown = close < box_lower and prior_close >= prior_box_lower
```

Required data:

- OHLC.
- Realized volatility for a second compression definition.
- Optional intraday bars for precise retest / false-break timing.

Authority:

- Compression state: display only.
- Expansion direction: can be descriptive event content, but no buy/sell
  authority without an independent S-SQ study.

### 3.7 Momentum bars

Public meaning:

- Blue horizontal bars in Panel 1.
- Represent significant "whale transactions."
- Longer bars matter more.
- Once price breaks above a bar, it can become accumulation/support.
- Failed breaks remain temporary resistance.

Likely technical substrate:

- Volume-at-price, high-volume nodes, or anchored volume shelves.
- Longer bars likely mean more traded volume at that price zone.
- "Whale transaction" is probably a charting label for large volume/cost-basis
  areas, not observable identity.

Current repo proxy:

- `engine.dannytrades.poc_proxy()` uses rolling VWAP as a crude POC proxy.
- `engine.basket_tape` uses the single-name proxy on basket candles.

Better build:

- Route to Entry Intelligence price-memory bundle.
- Build a volume-shelf engine:
  `high_volume_nodes`, `node_strength`, `node_age`, `above_node`,
  `reclaim_node`, `failed_node_break`, `distance_to_nearest_node`,
  `overhead_supply`.
- Use bars as descriptive support/resistance memory, not DCA policy.

Implementation sketch:

```text
window = last 126 trading days
bins = price bins scaled by ATR or log-price width
volume_by_price[bin] = sum(dollar_volume for bars whose typical price in bin)
positive_flow_by_price[bin] = sum(dollar_volume * buy_share)
poc = bin with max(volume_by_price)
whale_node = bin with max(positive_flow_by_price)
node_strength = node_volume / total_window_volume
reclaim = close > node_upper and close.shift(1) <= node_upper.shift(1)
failed_break = high > node_upper and close < node_upper
```

Required data:

- Minimum: daily OHLCV.
- Better: intraday OHLCV or true volume profile.
- Best: signed trade/auction data.

Authority:

- Descriptive location and price-memory context only.
- Explicit DCA / max-add / invalidation policy objects are killed by DT-R7.

### 3.8 Points of control and dynamic volume shelf

Public meaning:

- Danny uses points of control in the volume shelf for support/resistance.
- Public X snippets also list POC on a dynamic volume shelf as one of his most
  reliable tools.

Build relation:

- This is the same family as momentum bars, but with a clearer standard name.
- POC = price level with maximum traded volume in a window or anchor segment.

Better build:

- Add multiple anchors:
  rolling 63d/126d/252d POC, post-earnings POC, post-gap POC, post-breakout
  POC, and swing-low anchored VWAP.
- Each level needs age, touch count, break/reclaim status, and crowding warning.

Implementation sketch:

```text
rolling_poc = max volume-by-price node in rolling window
anchored_vwap(anchor_date) = cumulative(price * volume) / cumulative(volume)
distance_to_poc = close / rolling_poc - 1
overhead_supply = share of trailing volume transacted above current price
```

Required data:

- Long OHLCV history.
- Intraday volume profile strongly preferred.

Authority:

- Entry Intelligence descriptive / research family.
- No DannyTrades directional authority.

### 3.9 Proprietary chip system / strongest whale accumulation point

Public meaning:

- Danny references a proprietary chip system that identifies strongest whale
  accumulation points.
- "Chip" likely means cost-basis distribution / volume-at-price / ownership
  pressure in charting vocabulary.

What can be built:

- A reproducible "chip shelf" proxy from volume-by-price and positive
  money-flow weighting.
- A "sponsorship cost-basis shelf" that finds where accumulation-like volume
  concentrated.

Implementation sketch:

```text
buy_share = close-in-range buy pressure
positive_flow = buy_share * dollar_volume
chip_by_price = volume_by_price weighted by positive_flow
strongest_chip = max chip_by_price node
chip_support = close above strongest_chip and node not broken on retest
chip_overhead = close below strongest_chip and node above current price
```

Required data:

- At least OHLCV.
- Much better with intraday volume profile.
- Optional float/turnover to express shelf as percent of float.

Authority:

- Same as price-memory: descriptive only until the Entry Intelligence bundle is
  tested.

### 3.10 Red-candle buy signal lifecycle

Public meaning:

- Danny focuses more on weekly/monthly red candles than daily noise.
- Daily red candles are used for earlier entry windows.
- He warns not to chase after the red candle has been active for more than
  roughly five days or after price reaches resistance.
- For each red candle, he marks an upper continuation/acceleration level and a
  lower invalidation level.
- The Dec. 2025 public summary says red bullish candles are valid only while
  their price range is not breached to the downside.

Build recommendation:

- Build as a descriptive lifecycle state, not a buy signal.
- This could improve the existing no-chase / action-board copy by showing event
  age and range status.

Implementation sketch:

```text
red_event_date = first bar where short trend flips bullish
red_age = bars since red_event_date
red_range_high = high at event bar or event cluster high
red_range_low = low at event bar or event cluster low
upper_continuation = red_range_high or nearest volume node above
lower_range_breach = close < red_range_low
stale_red = red_age > 5 daily bars or price near resistance
```

Required data:

- OHLC daily/weekly/monthly.
- Price-memory levels for resistance.

Authority:

- Display/no-chase context only.
- "Invalidation" wording should be "range breached" in UI, not a stop command.

### 3.11 Blue-to-red ribbon trend reversal

Public meaning:

- The proprietary-buy-signal summary says daily charts often provide first
  entry opportunity when trend reverses from blue ribbon to red ribbon; weekly
  can be the second chance.

Build recommendation:

- Already approximated by `ribbon_trend`.
- If expanded, make it a multi-timeframe trend-transition event:
  `D_blue_to_red`, `W_blue_to_red`, `M_blue_to_red`, `transition_age`,
  `transition_confirmed`, `transition_failed`.

Implementation sketch:

```text
ribbon_state_tf = ribbon_trend(resampled_close)
blue_to_red = ribbon_state_tf == up and ribbon_state_tf.shift(1) <= flat_or_down
transition_failed = close < transition_low or ribbon_state returns down
```

Required data:

- Daily adjusted close; weekly/monthly resample.
- OHLC for transition range.

Authority:

- Context only. Trend transition is late by design and must not become a
  standalone buy chip.

### 3.12 Support/resistance confluence: Fibonacci

Public meaning:

- Danny uses Fibonacci analysis to identify support and resistance levels.

Technical substrate:

- Swing highs/lows.
- Standard retracements: 23.6%, 38.2%, 50%, 61.8%, 78.6%.
- Extensions: 127.2%, 161.8%, 261.8%.

Build recommendation:

- Use only as level context inside price-memory / technical-lab.
- Do not add Fibonacci confluence points to scores without a study.

Implementation sketch:

```text
last_major_swing = causal pivot high/low pair
fib_levels = low + ratio * (high - low) for retracement
level_cluster = fib level within ATR tolerance of POC / AVWAP / volume node
```

Required data:

- OHLC.
- Causal pivot detector.

Authority:

- Display only.

### 3.13 Dr. Cat's Ichimoku Cloud theory

Public meaning:

- Danny says exit/trim analysis is corroborated with Cat's Ichimoku Cloud
  theory, especially for trend exhaustion.
- Public onboarding also routes new members to Dr. Cat videos for panel reading.

Technical substrate:

- Standard Ichimoku formulas:
  Tenkan-sen, Kijun-sen, Senkou Span A, Senkou Span B, and Chikou span.
- High/low history, not volume.

Build recommendation:

- Technical-lab event family, not Danny-specific.
- Useful descriptive states:
  `above_cloud`, `inside_cloud`, `below_cloud`, `cloud_twist`,
  `tenkan_kijun_cross`, `kijun_distance`, `cloud_support_break`.

Implementation sketch:

```text
tenkan = (rolling_high_9 + rolling_low_9) / 2
kijun = (rolling_high_26 + rolling_low_26) / 2
span_a = (tenkan + kijun) / 2 shifted forward 26
span_b = (rolling_high_52 + rolling_low_52) / 2 shifted forward 26
state = close above max(span_a, span_b), inside, or below
```

Required data:

- OHLC.
- Careful handling of forward-shifted cloud for causal display; no future data
  can enter historical features.

Authority:

- Display/context only until tested under technical-lab rules.

### 3.14 Bollinger Band exhaustion

Public meaning:

- Danny says exit/trim analysis is corroborated with Bollinger Band analysis
  for bullish trend exhaustion.
- Volatility hole itself is also Bollinger-like in our current proxy.

Technical substrate:

- Close, moving average, rolling standard deviation.
- Bandwidth and close position relative to bands.

Build recommendation:

- This belongs to S-SQ / technical-lab.
- Useful events:
  `band_walk`, `upper_band_rejection`, `lower_band_reclaim`,
  `bandwidth_compression`, `bandwidth_expansion`, `outside_band_reentry`.

Implementation sketch:

```text
mid = SMA(close, 20)
sd = rolling_std(close, 20)
upper = mid + 2 * sd
lower = mid - 2 * sd
bandwidth = (upper - lower) / mid
upper_rejection = high > upper and close < upper
exhaustion = repeated upper-band tags + RSI rollover + monthly yellow state
```

Required data:

- Adjusted close and OHLC.

Authority:

- Display/context; trim-review candidate only inside Exit & Trim.

### 3.15 Matt's Gann theory / long-term resistance

Public meaning:

- Danny cites Matt's Gann theory for long-term resistance levels.

Unknown:

- The exact Gann method used by Matt is not public in the sources inspected.
- Gann can mean angles, fans, square-of-nine style levels, time cycles, or a
  looser resistance framework.

Build recommendation:

- Do not build a named "Gann" module without a formula from the operator or
  source.
- If Fable wants a legal proxy, build generic long-term resistance rails:
  pivot channels, log trend channels, measured-move extensions, and volume
  overhead nodes.

Implementation sketch:

```text
major_pivots = monthly causal pivots
log_channel = regression channel over major uptrend
resistance_rail = upper channel or measured-move extension
touch_count = count within ATR tolerance
```

Required data:

- Long OHLC history.
- Monthly bars.

Authority:

- Display only. No sell/trim command.

### 3.16 Monthly yellow candle plus whale-decay exit review

Public meaning:

- Danny does not emphasize daily/weekly yellow candles because he is not an
  active trader.
- Monthly yellow candles plus gradual whale-accumulation decline trigger
  potential reversal / downtrend / exit-or-trim review.
- He corroborates with volatility hole, Ichimoku, Bollinger exhaustion, and
  Gann resistance.

Current repo status:

- Exit/trim work already has TRIM/EXIT grids and L2 charter constraints.
- Danny monthly sponsorship-decay trim input was deferred to the future L2
  Exit & Trim charter and contingent on replication in the earlier adjudication;
  later settlement retired directional Danny claims.

Build recommendation:

- Keep as a future candidate input, not an active build.
- If revived, it must be framed as trim-review context, not a sell rule.

Implementation sketch:

```text
monthly_yellow = monthly short-trend flips bearish
accumulation_decay = accumulation_level falls for 2-3 monthly bars
exhaustion_confluence = RSI overbought rollover + Bollinger rejection +
                        resistance rail proximity + volatility-box breakdown risk
trim_review_context = monthly_yellow and accumulation_decay and exhaustion_confluence
```

Required data:

- Monthly OHLCV.
- Accumulation proxy from sanctioned volume substrate.
- Long history for resistance/exhaustion levels.

Authority:

- Deferred. Future L2 Exit & Trim only.

### 3.17 Big-leader universe and watchlist discipline

Public meaning:

- Danny publicly prefers large, high-quality leaders.
- He says 60-65 names are enough to participate in the bull trend.
- He views most small caps as lottery tickets.
- He posts daily, weekly, and monthly charts for selected names.

Build recommendation:

- This is not an indicator. It is a universe and behavior filter.
- Do not create `big_leader_core_eligible` as a fused admission gate; that was
  rejected by DT-R6 / long-hold constraints.
- If useful, print descriptive universe tags:
  `liquidity_tier`, `leader_theme`, `mega_cap`, `small_cap_lottery_risk`,
  `coverage_quality`.

Required data:

- Market cap, dollar volume, sector/theme membership, index membership,
  borrow/volatility where available.

Authority:

- Descriptive only in Macro Dashboard.
- Portfolio concentration and held-book logic belongs in Mastermind.

## 4. Data Requirements by Indicator Family

| Family | Minimum data | Better data | Best data | Current repo substrate |
|---|---|---|---|---|
| Candle/ribbon trend | Adjusted close | OHLC | Intraday OHLC | `data/stocks`, massive day store |
| MACD/RSI | Adjusted close | Multi-timeframe OHLC | Intraday for timing | existing technical helpers |
| Whale/retail proxy | OHLCV | dollar volume, float, turnover | signed tape / broker class flow | `data/massive_stock_day/` for studies |
| Volatility hole | OHLC | realized vol, BBWP, ATR | intraday break/retest | `engine.dannytrades`, `engine/basket_tape`, vol squeeze lanes |
| Momentum bars/POC | OHLCV | volume-by-price | intraday volume profile | crude `poc_proxy`; EI price-memory pending |
| Chip shelf | OHLCV | volume-by-price + positive flow | signed volume-at-price | not first-class yet |
| Fibonacci | OHLC | causal pivot taxonomy | intraday swing validation | technical-lab candidate |
| Ichimoku | OHLC | multi-timeframe OHLC | none needed | technical-lab candidate |
| Bollinger exhaustion | OHLC | BBWP + trend context | intraday rejection | vol/technical-lab candidate |
| Gann-style rails | long OHLC | monthly pivots, log channels | operator formula | no named Gann build |
| Monthly trim review | monthly OHLCV | accumulation decay + exhaustion set | signed flow + ownership | future L2 only |

## 5. Indicator Passports for Fable

### Passport A: `dt_public_panel_state`

Purpose:

- A descriptive inventory of Danny's five public chart panels for one symbol.

Fields:

- `asof`
- `symbol`
- `timeframes`: `D`, `W`, `M`
- `panel1`: candle color proxy, ribbon color, event age, red range high/low
- `panel2`: trendline confirmation state, if implemented
- `panel3`: accumulation level, accumulation motion, distribution proxy,
  retail-chase proxy, threshold band label
- `panel4`: MACD zero/cross/curl states
- `panel5`: RSI stack, oversold/overbought/curl/divergence states
- `source_confidence`: high/medium/low per field
- `caveat`: single-source caveat from `engine.dannytrades_chip.py`

Authority:

- Display only.
- Useful for education and context.
- No signal state beyond neutral.

Build status:

- Recommended as doc/schema only for now.
- Code build should wait for PR #1840 or be merged into it.

### Passport B: `price_memory_levels`

Purpose:

- Build the momentum-bar / POC / volume-shelf concept in a repo-native way.

Fields:

- `rolling_poc_63d`, `rolling_poc_126d`, `rolling_poc_252d`
- `nearest_high_volume_node`
- `node_strength`
- `node_age`
- `distance_to_node`
- `above_node`
- `reclaim_node`
- `failed_node_break`
- `overhead_supply`
- `anchored_vwap_levels`
- `coverage`

Authority:

- Entry Intelligence research family.
- Descriptive until pre-registered measurement.

Build status:

- Highest practical value from Danny's suite.
- Already routed by DT-R7 to Entry Intelligence; do not place under Danny.

### Passport C: `volatility_box_state`

Purpose:

- Build the black-hole concept as a general volatility-compression box.

Fields:

- `box_upper`, `box_lower`, `box_mid`
- `box_width_pct`
- `bandwidth_pctile`
- `realized_vol_pctile`
- `compression_age`
- `position_in_box`
- `breakout_up`, `breakdown`
- `retest_state`
- `false_break_state`
- `time_since_resolution`

Authority:

- S-SQ / volatility-compression program.
- Display or research only until that program measures it.

Build status:

- Partly exists in `engine.dannytrades.volatility_hole` and `basket_tape`.
- Future variants should not be chartered as DannyTrades work.

### Passport D: `monthly_exhaustion_review`

Purpose:

- Translate Danny's slow trim idea into a non-command review context.

Fields:

- `monthly_yellow_proxy`
- `yellow_age`
- `accumulation_decay_months`
- `box_breakdown_risk`
- `bollinger_exhaustion`
- `ichimoku_trend_decay`
- `long_resistance_rail_distance`
- `review_reason`

Authority:

- Future Exit & Trim charter only.
- Cannot issue sell, trim, or reduce commands.

Build status:

- Deferred.

### Passport E: `source_confidence_ledger`

Purpose:

- Make clear which parts of the DannyTrades suite are public-source supported,
  which are inferred, and which are unknown.

Fields:

- `indicator`
- `source_urls`
- `public_confidence`: high/medium/low
- `formula_confidence`: high/medium/low
- `proxy_confidence`: high/medium/low
- `missing_evidence`
- `legal_route`

Authority:

- Documentation only.

Build status:

- Recommended to include in any future implementation PR.

## 6. Build Lanes

### Lane 0: keep this docket as the canonical source inventory

Deliverable:

- This file.

Why:

- It prevents future sessions from confusing Danny's public vocabulary with
  authorized repo build work.

Acceptance:

- Source list included.
- Existing rulings cited.
- Indicator-by-indicator data requirements included.

### Lane 1: no code until PR #1840 settles, unless Fable explicitly merges scope

Deliverable:

- No immediate technical-lab work from this docket.

Why:

- Active build map shows PR #1840 and #1891 conflicts around technical-lab /
  indicator engine code.

Acceptance:

- Future builder checks `docs/ACTIVE_BUILD_MAP.md` again before coding.

### Lane 2: Entry Intelligence price-memory bundle

Deliverable:

- A pre-registered price-memory family covering momentum bars, POC, AVWAP,
  volume shelves, gap maps, overhead supply, and float turnover.

Why:

- This is the most buildable and potentially useful part of Danny's suite.
- It is also already routed by prior adjudication.

Required controls:

- One family, one FDR budget.
- Calendar-time inference.
- PIT membership / survivorship handling.
- Coverage stamps.
- No DCA policy output.

### Lane 3: volatility-box variants under S-SQ

Deliverable:

- If S-SQ proceeds, include a black-hole crosswalk:
  Danny public box -> repo `volatility_box_state`.

Why:

- The current `volatility_hole` proxy is plausible but should not be a
  DannyTrades authority family.

Required controls:

- Family definition before testing.
- Retest/false-break states pre-declared.
- Unresolved boxes remain non-directional.

### Lane 4: descriptive public-panel state after technical-lab settles

Deliverable:

- Optional `dt_public_panel_state` artifact.

Why:

- Helps explain why the current `dt_contra` chip says "descriptive only" and
  gives Fable a source-backed UI/education map.

Required controls:

- Every field has source confidence.
- State is neutral or descriptive.
- Uses the `engine.dannytrades_chip._CAVEAT` text verbatim or imports it.

### Lane 5: future Exit & Trim monthly review

Deliverable:

- Candidate row for the L2 Exit & Trim charter:
  monthly yellow + accumulation decay + exhaustion confluence.

Why:

- Danny's slow exit horizon is behaviorally coherent, but not authorized here.

Required controls:

- No sell/trim commands.
- No portfolio sizing.
- Fable/operator ruling before any code.

### Lane 6: Mastermind routing for concentration and held-book behavior

Deliverable:

- Optional Mastermind note, not Macro Dashboard code.

Why:

- Danny's actual wealth mechanism appears to be concentration, leader selection,
  long holding period, and low churn. That is portfolio behavior, not a public
  indicator edge.

Required controls:

- Do not build held-position or portfolio monitor features in Macro Dashboard.

## 7. What Fable Should Reject Immediately

Reject these if they appear in a future DannyTrades build proposal:

- `danny_buy_score`
- `danny_sell_score`
- `whale_buy_signal`
- `whale_surge_fade_signal`
- Any 35/50/75 whale threshold used as buy or sell authority
- Any merged sponsorship score that blends CMF, OBV, options flow, 13F, ETF flow,
  and price action into rank authority
- Any `max_add`, `invalid_if`, `stop`, `no_chase_above`, or DCA policy object
- Any pooled 60-year result without modern-era split
- Any ticker-cluster-only inference for monthly/level studies
- Any LLM-generated confidence number or escalation
- Any attempt to call the descriptive `dt_contra` state a prediction

## 8. Practical Build Priority

Priority 1:

- Price-memory levels. This converts momentum bars, POC, dynamic volume shelf,
  and chip shelf into one governed Entry Intelligence family.

Priority 2:

- Volatility-box state cleanup. Keep it general and route through S-SQ.

Priority 3:

- Public-panel descriptive passport. Useful for explainability, but wait for the
  active technical-lab PRs to settle.

Priority 4:

- Monthly exhaustion review. Worth keeping as a future Exit & Trim input, but
  currently deferred.

Do not prioritize:

- Re-testing Danny's buy confluence.
- Rebuilding the whale directional line.
- Building a Danny-branded lobe.
- Generic indicator engine work that duplicates PR #1840.

## 9. Final Take

DannyTrades' public indicator suite is coherent as a human charting workflow:
find big leaders, track trend state, watch accumulation-like pressure, identify
volume-memory shelves, wait for volatility boxes to resolve, avoid chasing stale
red candles, and only review exits on slow monthly evidence.

Macro Dashboard should keep the useful nouns but not inherit the authority. The
right Fable move is to decompose the suite into repo-native descriptive organs:
price memory, volatility boxes, technical event passports, and monthly exhaustion
context. The DannyTrades family itself stays settled: descriptive only, no
directional claims, no promotion path without a new explicit ruling.
