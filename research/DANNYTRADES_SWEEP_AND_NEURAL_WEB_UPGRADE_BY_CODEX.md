# DannyTrades Sweep and Neural Web Upgrade Review

Prepared by Codex, 2026-07-06.

Status: external-method sweep, first-principles review, and Neural Web build
translation. Additive research artifact only. No scoring, sizing, trading, or live
authority is granted here.

## 0. Boundary and Ruling

This memo is intentionally additive to the existing in-repo DannyTrades phase-0:

- `research/DANNYTRADES_PHASE0.md` already reconstructs Danny Cheng's public
  indicator stack, implements causal proxy indicators in `engine/dannytrades.py`,
  runs phase-0 and whale-specific backtests, and concludes that the reconstructed
  buy-confirmation use does not clear the gate. Its gate-passing use is the inversion:
  high composite / hot whale readings are extension and no-chase warnings.
- This memo does not re-run that harness. It uses it as the repo's quantitative
  anchor, then adds the broader public-source sweep: his stated methodology,
  stock-selection philosophy, holdings, mindset, wealth mechanism, first-principles
  critique, and Neural Web upgrade plan.
- Public sources include DannyTrades/Danny Cheng Patreon pages and public X-indexed
  posts. I did not access or reconstruct paywalled posts beyond snippets publicly
  exposed by Patreon/X/search. Claimed portfolio balances, hit rates, and screenshots
  are treated as unverified self-reports unless independently auditable.

Executive ruling:

1. DannyTrades is best understood as a concentrated, long-horizon secular-growth
   investor using technical indicators for entry/accumulation/trim timing. He is
   not primarily a high-turnover day trader.
2. His real edge, if the public claims are directionally true, is probably the
   combination of stock selection, concentration, patience, and trend discipline,
   not the literal proprietary indicators.
3. The in-repo causal reconstruction found no shippable buy-confirmation edge. The
   strongest measured translation is contrarian: hot composite, hot/rising whale,
   and fully confirmed trend states are often too mature to chase.
4. Neural Web should not copy the indicator names. It should extract the useful
   operating ideas: big-leader right-tail admission, sponsorship-versus-retail
   ownership state, volatility-compression breakout boxes, no-chase clocks,
   support-ladder accumulation, and monthly trim/exhaustion detection.

## 1. Public Evidence Sweep

### 1.1 Identity and service shape

DannyTrades refers here to Danny Cheng, public X handle `@dannycheng2022`, whose
Patreon tagline is "Trade and invest for life." Patreon showed 15,480 posts and a
membership starting at $5/month when accessed on 2026-07-06. His public service
description says he posts daily, weekly, and monthly charts on selected stocks and
that a typical day involves roughly 20-40 chart posts. His May 2026 subscriber note
says he tracks about 60-65 names regularly, spends 10-12 hours per day on analysis
and charting, and cannot answer every individual message because of message volume.

### 1.2 Chart-panel suite

His public "how to read my charts" material lays out a five-panel chart grammar:

| Panel | Public meaning | Neural Web interpretation |
|---|---|---|
| Panel 1 | Candle/ribbon state. Red candle = short-term bullish; yellow = short-term bearish; dark blue = uptrend persists; light blue = downtrend persists; red ribbon = mid-term uptrend; blue ribbon = mid-term downtrend. | Multi-horizon trend-state classifier with explicit trend start, trend continuation, and trend decay states. |
| Panel 2 | "Technical expert" mimic of Panel 1. Green bars denote downtrend, red bars uptrend; purple/green lines represent uptrend/downtrend lines. | Redundant confirmation panel; useful only if it improves calibration versus Panel 1. |
| Panel 3 | Whale accumulation/distribution versus retail accumulation. He uses red bars for whales, green bars for retail, yellow bars for short-term daily traders. His public thresholds are roughly >35% for momentum, >50% for a stock to run, and >75% for a surge. | Sponsorship-pressure state. Must be measured as an observed proxy, not as literal knowledge of investor identity. |
| Panel 4 | MACD. Below zero = bearish momentum, above zero = bullish; golden-cross curl up/down is bullish/bearish. | Standard momentum confirmation, likely lagging. |
| Panel 5 | RSI. He watches oversold/overbought areas and compares three RSI sets versus prior lows. | Mean-reversion/overextension context; best as entry-zone and no-chase context, not a standalone signal. |

He also uses a proprietary "volatility hole" / "volatility black hole" concept:
a boxed volatility structure whose upper boundary can become a buy/accumulation
trigger when closed above, and whose lower boundary can signal downside if broken.
Public posts describe it as useful in bottoming formations, trend resumptions, and
temporary top recognition. His public strategy post claims near-99% accuracy as
tested by him and collaborators, but this is not independently verified and should
be treated as a hypothesis, not evidence.

Momentum bars are another core tool. His public strategy post describes them as
blue horizontal levels in Panel 1 representing significant whale transactions. The
levels act as support/resistance; a breakout above a bar can become an accumulation
signal and later support, while failed breakouts remain resistance.

He also refers to points of control in the volume shelf, strongest whale
accumulation points from a proprietary chip system, Fibonacci levels, Dr. Cat's
Ichimoku Cloud work, Bollinger Band exhaustion checks, and Matt's Gann levels.
That makes the real stack a confluence desk, not a one-indicator system.

### 1.3 Buy, accumulation, and exit rules

His public buy/sell strategy post is very explicit:

- He focuses more on weekly and monthly red candles than daily noise.
- He uses DCA after a red candle if price pulls back into identified support zones.
- On daily charts he says the first two days after a red candle are often the more
  sensible accumulation window.
- He warns against chasing after the red candle has already persisted for more than
  several days or after price reaches resistance.
- For each red candle he marks an upper continuation/acceleration level and a lower
  invalidation level.
- He encourages buying support, not resistance, unless resistance flips into support
  and is accompanied by higher whale accumulation plus lower retail accumulation.
- His trim/exit framework is monthly, not daily: monthly yellow candles plus a
  gradual decline in whale accumulation, corroborated by volatility-hole logic and
  trend-exhaustion tools.
- He says he avoids options and does not care much about short-term yellow candles
  because frequent trading in a bull cycle can miss long-term rallies.

This is a lifecycle method:

```text
secular leader candidate
  -> public chart watchlist
  -> volatility hole / red candle / whale support confluence
  -> DCA support ladder
  -> hold through noise if thesis and trend remain valid
  -> monthly yellow + sponsorship decay = trim/exit review
```

### 1.4 Stock-selection and long-term thesis

The public thesis is strongly biased toward big, liquid, high-quality leaders and
major secular themes. In his May 2026 Patreon note, he says the core of a balanced
portfolio should be dominated by big leaders, including the Big 7, semiconductors,
and major trending stocks. He explicitly describes most small caps as lottery
tickets because of volatility.

Public X search snippets as of early July 2026 show him saying his top four
holdings were `PLTR`, `AMD`, `NVDA`, and `HOOD`, accounting for over 93% of his
portfolio. Other public snippets from 2025-2026 identify `PLTR`, `NVDA`, and `AMD`
as top/core holdings; earlier public snippets mention `MSTR`, `FUTU`, Xiaomi,
`HIMS`, `OSCR`, and `SMH`/semiconductors as important names or themes. A public
July 2025 snippet listed top FUTU-account positions with average costs around
`NVDA` 15.20, `PLTR` 8.80, `MSTR` 28.80, `HOOD` 9.90, and Xiaomi 9.20. Treat these
as public claims, not audited account records.

Why those names fit his thesis:

- `NVDA`, `AMD`, `SMH`, `TSMC`, `AVGO`: AI compute, semiconductor buildout, and
  leadership in a bull-market theme.
- `PLTR`: AI/data platform leader, institutional ownership narrative, and a major
  trend since his claimed low-cost entry.
- `HOOD` and `FUTU`: brokerage/fintech/platform exposure that benefits from retail
  participation, crypto/equity activity, and asset-market wealth effects.
- `MSTR`, `COIN`, crypto-adjacent names: high-beta participation in crypto cycles,
  though his 2026 public comments were dismissive of some miners as lottery tickets.
- `HIMS`, `OSCR`, `RKLB`, `RDDT`, `EOSE`, `BB`, `NBIS`, etc.: selected thematic or
  turnaround/trend names, apparently sized below the core mega-conviction book.

### 1.5 Mindset and personality, limited to public behavior

Publicly observable style:

- Direct, confident, and promotional.
- Strongly conviction-oriented: he repeatedly stresses holding, position sizing,
  and avoiding churn.
- Comfortable with extreme concentration and very large drawdowns; he publicly says
  his own horizon is 5-10 years and that this lets him withstand 70-80% drawdowns.
- Community-focused but bandwidth-constrained: he posts huge chart volume and
  frames Patreon as a way to protect followers from scam accounts and organize
  access.
- Blunt about laggards and small-cap lottery behavior.
- Not one-size-fits-all: his public Patreon note says users should not blindly copy
  his portfolio because style, time horizon, conviction, and risk tolerance differ.

The psychological pattern is important: his method is partly an anti-behavioral
system. He is trying to keep followers from selling core winners during volatility
and from chasing weak/speculative names because they look cheap.

## 2. How Wealth Could Be Amassed Through This Method

Danny publicly claimed that a FUTU account grew from about HKD 1 million in late
2022 / early 2023 to much larger figures by 2024-2025, including a public X-indexed
post titled around a journey from $1M to $47M. I cannot verify those balances. The
mechanism, if directionally accurate, is still straightforward:

1. Extreme concentration: if four positions are over 90% of a portfolio, each major
   winner moves total wealth materially.
2. Right-tail participation: long-term stock wealth is highly skewed. Academic work
   by Bessembinder finds that a small share of stocks account for the net wealth
   creation of the broad market. Concentrated investors who actually select and hold
   those right-tail names can compound dramatically.
3. Secular theme alignment: 2023-2026 heavily rewarded AI semiconductors, AI
   software, crypto/fintech, and high-beta growth rebounds. His public core list
   maps directly onto those winners.
4. Low-churn behavior: avoiding constant trading preserves exposure to parabolic
   moves. This is consistent with his repeated "hold conviction stocks" message.
5. Opportunistic DCA: adding at support during volatility can increase share count
   if the underlying trend and thesis remain intact.
6. Monetization sidecar: Patreon/community income may add to wealth, but public
   data do not disclose paid-member count or net income, so it should not be used
   as an explanatory fact.

The same mechanism can destroy wealth when the selected leaders are wrong. A
70-80% drawdown tolerance is not a normal investor constraint; it requires unusual
liquidity, psychology, and willingness to be wrong for years.

## 3. First-Principles Review of the Techniques

### 3.1 What makes sense

Trend following and momentum are real phenomena.

Jegadeesh and Titman documented that buying past winners and selling past losers
generated positive returns over 3-12 month horizons, with some reversal later.
Moskowitz, Ooi, and Pedersen documented time-series momentum across futures, and
AQR/Hurst/Ooi/Pedersen extended trend-following evidence over long historical
samples. Brock, Lakonishok, and LeBaron found evidence that moving-average and
trading-range rules on a long Dow sample generated behavior inconsistent with
simple null models.

Translation: his "trend is your friend", ribbon, red-candle continuation, and
resistance-breakout language is not nonsense. The market often underreacts, flows
chase winners, and trend persistence exists.

Volume/flow confirmation is plausible.

Academic work on volume and momentum finds that trading volume can predict both
the magnitude and persistence of price momentum, and high-volume shocks can carry
information through attention and demand. His "whale accumulation" and momentum-bar
concepts are a retail charting vocabulary for a real institutional question:

```text
Is price moving because marginal buyers with size are absorbing supply,
or because late retail is chasing after the move?
```

Support/resistance and volume shelves are plausible.

High-volume price areas can become memory zones because many holders have cost
basis there. Breakouts above heavily traded resistance can force underweight
buyers to chase and can flip prior resistance into support. His momentum bars and
POC/chip-system language map to this microstructure idea.

The no-chase rule is excellent.

His warning not to chase red candles after the signal is already mature is the
most repo-compatible insight. The existing phase-0 found the reconstructed
composite was contrarian when hot. That means the public discretionary rule
"do not chase late confirmations" is more valuable than the public promotional
rule "buy the hot confluence."

Monthly exits reduce churn.

Using monthly yellow candles plus sponsorship decay for trims is coherent for a
5-10 year holder. It avoids death by daily noise and pushes exit authority to a
slower, more consequential horizon.

### 3.2 What is fragile or dangerous

The "whale" label may not be literal.

Without broker-level order flow or investor identity data, public OHLCV cannot
know whether whales or retail are buying. It can estimate accumulation-like price
and volume behavior. Neural Web must call this `sponsorship_proxy`, not "whale
truth."

The thresholds are not inherently causal.

Public thresholds like 35/50/75 can be useful heuristics, but they need
cross-sectional, era-stable calibration. A fixed threshold may work in one regime,
theme, or volatility environment and fail elsewhere.

Near-99% accuracy is not a research claim.

It may reflect selected examples, visual hindsight, moving definitions, follower
survivorship, or measuring whether a boundary eventually broke rather than whether
the signal improved risk-adjusted forward returns. The repo's reconstruction found
the buy-confirmation case did not clear significance.

Volatility holes are underspecified.

The idea is plausible if it represents volatility compression, supply exhaustion,
or a volume-pocket breakout. But without a frozen formula, any backtest can drift
into p-hacking. Neural Web should build several pre-registered proxy definitions
and let the gauntlet choose or reject them.

Concentration is a skill amplifier and an error amplifier.

The same right-tail math that creates wealth through `NVDA`/`PLTR` type winners
creates catastrophic loss if the chosen "leader" is a regime bubble, accounting
trap, dilution machine, or valuation reset.

DCA can be brilliant or fatal.

Adding at support works when the long-term thesis and sponsorship are intact. It
is dangerous when price is falling because the business model, funding condition,
or market structure is genuinely breaking. The DCA rule must have falsifiers.

### 3.3 Why it works when it works

The successful state is:

```text
large liquid leader
+ secular theme tailwind
+ early or mid-cycle trend repair
+ real sponsorship / institutional demand
+ volatility has reset expectations
+ price reclaims meaningful supply levels
+ operator holds rather than churns
```

That combination captures three premia at once:

- Fundamental/theme drift: the market is revising future revenue, earnings, or TAM.
- Momentum/flow drift: underweight buyers keep adding because the trend proves
  itself.
- Behavioral drift: holders who can tolerate drawdowns keep exposure while others
  panic in and out.

The failed state is:

```text
hot confluence
+ mature move
+ retail crowding
+ valuation stretched
+ whale proxy already saturated
+ no fresh fundamental revision
+ operator keeps adding because the chart still looks strong
```

This is exactly why the in-repo backtest's inversion matters. By the time all
public indicators are screaming "strong," forward edge may already be spent.

## 4. Existing Repo Evidence: DannyTrades Phase-0

The existing phase-0 reconstructed his stack using causal OHLCV proxies:

| Danny public concept | Repo proxy |
|---|---|
| Whale accumulation | Chaikin money-flow accumulation rescaled by trailing percentile; later a more faithful `whale_buy_fraction` on monthly bars. |
| Volatility hole | Bollinger-bandwidth squeeze box with close beyond upper/lower boundary. |
| Momentum bars / POC | Rolling volume-weighted price reclaim as POC proxy. |
| Red/blue ribbons and MACD/RSI | EMA ribbon state plus MACD/RSI momentum filter. |

Important results from `research/DANNYTRADES_PHASE0.md`:

- Standalone cross-sectional rank IC at 63 days was significantly negative.
- Adding the composite to classic 12-1 momentum diluted momentum.
- Pullback-confirmation lift was directionally positive but not statistically
  significant and had worse drawdown tail.
- The whale leg was the only positive-but-not-significant buy contributor and was
  orthogonal to classic momentum.
- A later faithful monthly whale test found whale-change and hot-whale states
  inverted his thesis: "whales entering" and hot whale readings predicted weaker
  next-month returns, while "whales leaving" had the better bounce profile.
- Composite-score and whale-level deciles showed clean monotonic extension:
  forward 63-day returns fell as the signal got hotter.

Current repo ruling:

```text
Do not ship DannyTrades as a buy confirmer.
Investigate it as an extension / no-chase / fade / support-reentry context layer.
```

That ruling is more valuable than a simple rejection. It shows how Neural Web can
learn from a discretionary influencer without swallowing the influencer's stated
directional interpretation.

## 5. Neural Web Translation

### 5.1 Adopt, modify, reject

Adopt:

- Big-leader right-tail admission test.
- No-chase clock after obvious trend confirmation.
- Support-ladder DCA only when thesis and sponsorship remain intact.
- Sponsorship/retail-exhaustion state, but as a proxy with error bars.
- Volatility-compression box as a hypothesis family.
- Monthly trim/exhaustion review for long-horizon holds.
- Operator patience and churn-regret ledger.

Modify:

- Replace "whale accumulation" with `sponsorship_pressure_proxy`.
- Replace "volatility black hole" with pre-registered `volatility_void_box`
  families.
- Replace public thresholds with calibrated, regime-conditional reliability cells.
- Convert DCA from "buy every dip" into a support-ladder policy with invalidation.

Reject:

- Near-99% accuracy claims without a reproducible PIT harness.
- Literal buy authority from hot confluence.
- Blind copying of concentrated holdings.
- Using paywalled/proprietary labels as live system facts.

### 5.2 Lobe mapping

| Neural Web lobe / rail | Danny-derived upgrade | Authority target |
|---|---|---|
| Entry Intelligence | Volatility-void breakout, momentum-bar reclaim, support-ladder DCA, no-chase age. | Display -> shadow only after replay. |
| Long-Hold Thesis Layer | Big-leader admission, 5-10 year hold clock, drawdown tolerance, thesis falsifiers. | Hold-thesis context, not entry ranking. |
| Oracle / Rotation | Big-leader versus small-lottery regime, semiconductor/AI route memory, ETF/member leadership map. | Rotation context. |
| Exit & Trim Intelligence | Monthly yellow proxy + sponsorship decay + volatility-boundary break as trim review. | Phase-0 role classifier input. |
| Dispersion / Selection-Regime | Detect when only mega-leaders carry the tape versus when small/speculative breadth is trustworthy. | Trust conditioner. |
| Liquidity & Execution Realism | DCA ladder, capacity/cost pass, 70-80% drawdown stress, concentration risk passport. | Friction and risk context. |
| Operator Self-Model | Churn-regret, panic-sell, FOMO-chase, and conviction-hold behavior labels. | Behavioral mirror. |

### 5.3 Proposed artifact family

Do not wire this straight into boards. Build a measured research family:

```text
research/dannytrades/DANNYTRADES_NEURAL_WEB_TRANSLATION_PREREG.md
engine/dannytrades_ext.py
scripts/research/dannytrades_neural_proxy_panel.py
data/research/dannytrades_neural_proxy_panel.parquet
data/research/dannytrades_neural_results.json
research/dannytrades/DANNYTRADES_NEURAL_PROXY_RESULTS.md
```

Suggested features:

| Feature | Definition target | Purpose |
|---|---|---|
| `trend_color_state` | EMA/ribbon/multi-timeframe state with start/continue/decay labels. | Replace subjective red/yellow/blue candles. |
| `volatility_void_box_id` | Frozen compression box from pre-registered squeeze variants. | Track support/resistance boxes causally. |
| `vol_void_break_up` / `vol_void_break_down` | Close above/below frozen box boundary. | Test breakout and breakdown effects. |
| `sponsorship_pressure_proxy` | Ensemble of CMF, OBV slope, dollar-volume impulse, close-location value, block/dark-pool if available. | Replace "whale" with measurable sponsorship. |
| `retail_chase_proxy` | High turnover + social/news surge + high short-term return + low institutional confirmation. | Detect late retail heat. |
| `momentum_bar_level` | High-volume node / anchored VWAP / volume shelf POC. | Test support/resistance flips. |
| `support_ladder_distance` | Distance to nearest support node and invalidation. | DCA location quality. |
| `no_chase_age` | Bars since red/ribbon/void breakout confirmation. | Prevent late entries. |
| `monthly_trim_candidate` | Monthly trend decay + sponsorship decay + exhaustion overlay. | Exit & Trim input. |
| `big_leader_core_eligible` | Size/liquidity/theme/quality gate. | Separate core compounder candidates from lotto sleeves. |
| `concentration_passport` | Max drawdown, beta, factor exposure, liquidity/capacity, thesis state. | Make concentration explicit and survivable. |

Labels:

- Tactical: 10d/21d/63d/126d forward return, MFE/MAE, gap risk, support hold,
  false breakout, re-entry regret.
- Long-hold: 6m/12m/24m/36m excess return, thesis improvement/decay, drawdown
  survival, valuation compression, fundamental break.
- Operator: avoided chase, panic-sell regret, DCA helped/hurt, trim helped/hurt.

Validation:

- Point-in-time only; no same-day OI/ownership leakage.
- Matched controls by sector, size, beta, volatility, liquidity, and prior momentum.
- Placebos for box boundaries, support levels, and whale thresholds.
- Era splits, bull/bear splits, high/low dispersion, high/low liquidity.
- BH-FDR by family.
- Net-of-cost and capacity overlays.
- Print nulls and negative inversions.

### 5.4 Most important Neural Web upgrades

#### Upgrade 1: No-Chase / Extension Intelligence

This is the highest-confidence translation because the current phase-0 already
found contrarian extension.

Build:

- `engine/extension_no_chase.py`
- `scripts/build_extension_no_chase_state.py`
- `data/neuralweb/extension_no_chase_state.parquet`
- `site/neuralwebdata/extension_no_chase_state.json`

Inputs:

- Danny composite score and hot-whale proxy.
- Existing anti-chase, RS repair, extension, and bottom-sensor fields.
- Distance from high-volume node / momentum bar.
- Bars since trend confirmation.
- Short-term return and gap count.

Output:

```json
{
  "ticker": "NVDA",
  "asof": "YYYY-MM-DD",
  "state": "late_hot_do_not_chase",
  "extension_score": 0.81,
  "no_chase_age": 7,
  "nearest_support": 180.50,
  "invalid_if_below": 171.20,
  "reason": ["hot sponsorship proxy", "late breakout age", "above support shelf"]
}
```

Authority:

- Display or shadow. It can de-escalate urgency, not create a buy.

#### Upgrade 2: Sponsorship Pressure, Not Whale Mythology

Build a real sponsorship proxy family that can be falsified.

Inputs:

- CMF/OBV/VPT style price-volume signals.
- Dollar-volume impulse.
- Close-location value.
- Dark-pool or block proxies if available.
- 13F/13D/13G deltas where horizon-appropriate.
- ETF/sector flow and options flow context.

Key outputs:

- `sponsorship_pressure_proxy`
- `sponsorship_decay`
- `retail_chase_proxy`
- `sponsorship_uncertainty`

Ruling:

- If sponsorship is rising after a huge move, test it as extension and distribution
  risk, not as a naive buy.
- If sponsorship has bled out but price holds support, test it as washout/re-entry
  context.

#### Upgrade 3: Volatility Void Box Family

Rebuild the volatility-hole idea as a preregistered family:

Definitions to test:

1. Bollinger-bandwidth squeeze box.
2. Keltner/Bollinger squeeze box.
3. ATR compression plus volume shelf box.
4. Realized-volatility collapse after drawdown.
5. Gap/volume-pocket box near prior high-volume nodes.

For each box:

- freeze the upper/lower boundaries when formed,
- record breakout/breakdown dates,
- test support/retest behavior,
- test false-break rates,
- separate bottoming voids from top/exhaustion voids.

Important: the output should not be "buy." It should be:

```text
void_state = inside | break_up | retest_hold | false_break | break_down
void_role  = bottom_repair | continuation | exhaustion | unknown
```

#### Upgrade 4: Big-Leader Core Eligibility

Danny's best public idea is not "small cap lottery hunting"; it is that the core
book should be dominated by major leaders with secular tailwinds.

Build:

- `big_leader_core_eligible`
- `right_tail_theme_membership`
- `leader_liquidity_pass`
- `survivable_drawdown_capacity`

This belongs in the Long-Hold Thesis Layer and Dispersion lobe:

- Long-Hold decides whether a candidate deserves a thesis file.
- Dispersion decides whether selection among leaders is being rewarded or whether
  the whole market is one macro trade.
- Liquidity/Execution decides whether concentrated exposure is realistic.

#### Upgrade 5: Support-Ladder DCA With Invalidation

Convert his support DCA rules into a policy object:

```json
{
  "ticker": "PLTR",
  "entry_role": "core_add",
  "support_ladder": [
    {"level": 182.4, "source": "volume_node", "max_add": 0.25},
    {"level": 171.9, "source": "void_lower", "max_add": 0.25}
  ],
  "no_chase_above": 198.0,
  "invalid_if": [
    "monthly_sponsorship_decay",
    "thesis_falsifier_triggered",
    "support_break_without_reclaim"
  ]
}
```

This is especially useful because it changes the question from "is this bullish?"
to "where can we add without destroying expected value?"

#### Upgrade 6: Monthly Trim and Thesis-Break Desk

For long holds, daily sell signals are noise. The Danny-derived trim logic fits
the repo's Exit & Trim lobe:

- Monthly trend decay.
- Sponsorship decay.
- Failed reclaim of support shelf.
- Fundamental/thesis decay.
- Valuation-implied expectation reset.
- Crowding/exhaustion overlay from options and flows.

It should publish:

```text
hold
partial_trim_review
exit_review
reentry_watch
do_nothing
```

Not:

```text
sell everything now
```

#### Upgrade 7: Conviction-Hold and Churn-Regret Ledger

Danny's most durable behavioral idea is that wealth often comes from holding the
right few names through turbulence. Neural Web already has long-hold work; this
adds an operator-behavior layer:

- When did the operator sell a high-thesis winner?
- Was the sale caused by noise, thesis decay, liquidity need, or valid risk control?
- What happened 21d/63d/126d/12m later?
- Did DCA improve basis or add to a broken name?
- Did waiting improve entry or miss the move?

This can feed Decision-Quality / Operator Self-Model without becoming an LLM-originated
trade signal.

## 6. Practical Build Order

1. Do not ship buy confirmation. Keep the existing `DANNYTRADES_PHASE0` ruling.
2. Promote the contrarian extension result into a formal no-chase prereg, because
   it has the strongest current evidence.
3. Build sponsorship proxy as a measured feature family with uncertainty, not as
   literal "whale" state.
4. Build volatility-void boxes as multiple frozen definitions and test which, if
   any, survives.
5. Add support-ladder and invalidation fields to Entry Intelligence for core
   candidates only.
6. Add monthly trim/exhaustion features to Exit & Trim.
7. Add core-leader eligibility to Long-Hold Thesis Layer and connect it to
   concentration passports.
8. Add operator churn-regret ledger only after the candidate/position state schema
   is stable.

## 7. Final Ruling for Fable / Claude

The DannyTrades system should not be copied. It should be digested.

What is worth keeping:

- He is right that the big money often comes from a few right-tail leaders.
- He is right that churn kills long-term compounding.
- He is right that support/resistance, volatility compression, and sponsorship
  state are useful tactical context.
- He is right that small-lottery speculation should not dominate a serious core
  book.
- He is right that exits for long-term winners should be slower than entries.

What the repo already proved:

- The reconstructed hot-buy confluence did not earn buy authority.
- The best measured version is inverse: hot DannyTrades composite / hot whale is
  an extension warning.

Best Neural Web upgrade:

```text
Turn DannyTrades from a buy-signal influencer framework
into a Neural Web no-chase, sponsorship-decay, support-ladder,
and long-hold conviction-management framework.
```

That is how we use his best ideas without inheriting the fragile parts.

## Source Notes

Primary DannyTrades public sources:

- Patreon profile: `https://www.patreon.com/DannyTrades`
- "Hi everyone from X" / chart-reading post: `https://www.patreon.com/DannyTrades/posts/hi-everyone-from-98378381`
- "A sharing of my buy and sell strategies": `https://www.patreon.com/DannyTrades/posts/sharing-of-my-on-134759106`
- "MUST-READ: To All Subscribers (May 2, 2026)": `https://www.patreon.com/DannyTrades/posts/must-read-to-all-157131507`
- "$MSFT Free Daily Chart Update-New Volatility Hole": `https://www.patreon.com/DannyTrades/posts/msft-free-daily-162472706`
- Public X handle and indexed posts: `https://x.com/dannycheng2022`

Academic / first-principles anchors:

- Jegadeesh and Titman, "Returns to Buying Winners and Selling Losers":
  `https://econpapers.repec.org/article/blajfinan/v_3a48_3ay_3a1993_3ai_3a1_3ap_3a65-91.htm`
- Moskowitz, Ooi, and Pedersen, "Time Series Momentum":
  `https://www.sciencedirect.com/science/article/pii/S0304405X11002613`
- Hurst, Ooi, and Pedersen, "A Century of Evidence on Trend-Following Investing":
  `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2993026`
- Brock, Lakonishok, and LeBaron, "Simple Technical Trading Rules and the Stochastic Properties of Stock Returns":
  `https://scholarworks.brandeis.edu/esploro/outputs/journalArticle/Simple-Technical-Trading-Rules-and-the/9924036588601921`
- Lee and Swaminathan, "Price Momentum and Trading Volume":
  `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=92589`
- Bessembinder, "Do Stocks Outperform Treasury Bills?":
  `https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2900447`
