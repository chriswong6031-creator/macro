# Moderna-Style Sponsorship Breakaway Research

Date: 2026-07-07
Status: research design / brainstorming / not a live trading signal
Question: how do we identify stocks that behave like Moderna in 2026: very large alpha versus their own sector, repeated institutional-looking buying, and a narrative that forces investors to re-underwrite the company?

This is not investment advice. The goal is a research blueprint for detecting sponsorship breakaways, then validating them honestly before any score is trusted.

## 1. Bottom Line

The main answer is: do not try to find a magic "institutional inflow" feed. For US single stocks, the most useful sponsorship signal is a latent state inferred from many imperfect surfaces:

1. Sector-relative price is the primary footprint.
2. Dollar-volume expansion tells us whether the move has real capital behind it.
3. Options open-interest and volatility structure show whether investors are paying for convexity or building forward exposure.
4. Catalyst quality tells us whether the move can become a re-rating instead of a squeeze.
5. Ownership and short-interest data tell us how much forced buying or supply exhaustion may exist, but with meaningful reporting lag.
6. Buy-side research itself is not legally or practically observable, so we need public proxies: analyst revision velocity, target dispersion, conference chatter, transcript Q&A, clinical/regulatory calendars, and expert-free public-source evidence.

The practical detector should therefore be a "sponsorship breakaway" model, not an "inflow" model. The detector should ask:

> Is this stock being re-underwritten by large pools of capital faster than its sector, with repeated evidence that buyers are absorbing supply after each catalyst?

For Moderna, the local evidence says yes, at least as a descriptive state. Using repo price files ending 2026-07-02, MRNA was:

| Window ending 2026-07-02 | MRNA | XBI | XLV | MRNA excess vs XBI | MRNA excess vs XLV |
|---|---:|---:|---:|---:|---:|
| 5 trading days | 33.49% | 5.85% | 5.21% | 27.64 pp | 28.28 pp |
| 21 trading days | 74.76% | 25.59% | 11.84% | 49.16 pp | 62.91 pp |
| 126 trading days | 162.28% | 31.88% | 5.18% | 130.40 pp | 157.10 pp |
| YTD from 2026-01-02 | 158.46% | 32.04% | 5.29% | 126.42 pp | 153.17 pp |

Computed locally from:

- `data/massive_stock_day/MRNA.parquet`
- `data/massive_stock_day/XBI.parquet`
- `data/massive_stock_day/IBB.parquet`
- `data/massive_stock_day/XLV.parquet`
- `data/massive_stock_day/SPY.parquet`
- `data/massive_stock_day/QQQ.parquet`

The current live-ish quote context was similar: StockAnalysis showed MRNA at 81.80 at the July 6, 2026 close, with a 52-week range of 22.28 to 85.60 and an analyst consensus still at Hold with a 45.85 average target, which is important because it says the tape had outrun the average published model.

Source: https://stockanalysis.com/stocks/mrna/

## 2. Why Moderna Moved: The Mosaic, Not One Catalyst

Moderna's recent run looks like a cluster of re-rating triggers rather than a single news item.

### 2.1 Oncology Platform Validation

On January 20, 2026, Moderna and Merck announced five-year follow-up data for intismeran autogene, also known as mRNA-4157/V940, with Keytruda in high-risk melanoma. The key investor point was durability: a 49% reduction in risk of recurrence or death at median five-year follow-up in the Phase 2b KEYNOTE-942/mRNA-4157-P201 study, with eight Phase 2 and Phase 3 trials underway across tumor types.

Source: https://www.merck.com/news/moderna-merck-announce-5-year-data-for-intismeran-autogene-in-combination-with-keytruda-pembrolizumab-demonstrated-sustained-improvement-in-the-primary-endpoint-of-recurrence-free-survival-i/

This matters because it changes the question from "can Moderna replace COVID revenue?" to "is Moderna a repeatable mRNA oncology and immunology platform?"

### 2.2 Regulatory De-Risking For The Flu Franchise

On June 18, 2026, Moderna announced that FDA's VRBPAC voted 9-0 in favor of the benefit-risk profile of mRNA-1010, its investigational seasonal flu vaccine, with the PDUFA goal date remaining August 5, 2026.

Source: https://www.pressrelease.com/news/moderna-announces-fda-advisory-committee-votes-unanimously-in-favor-of-the

This was not the whole move, but it helped repair the near-term commercial narrative.

### 2.3 Science Day Reframed The Long-Duration Optionality

On June 25, 2026, Moderna highlighted T-cell engagers, mRNA-2808, mRNA-2151, in vivo CAR-T with mRNA-6007, and its "Scientific Intelligence Engine" combining data, AI, machine learning, automation, and robotics.

Sources:

- https://www.modernatx.com/science-day
- https://www.newswire.com/view/content/moderna-science-day-highlights-expanding-potential-of-mrna-platform

This is where the "AI and cancer vaccines" intuition is directionally right, but too compressed. AI is not the whole thesis. It is part of a platform-learning thesis: if mRNA design, delivery, manufacturing, clinical data, and automation create a faster learning loop, investors may assign platform value beyond a single product.

### 2.4 Cancer Prevention Optionality

Moderna also disclosed UK MHRA authorization for a Phase 1/2 study of mRNA-4194 in people with Lynch syndrome, an inherited condition associated with higher cancer risk.

Source: https://www.modernatx.com/media-center/all-media/blogs/potential-mRNA-cancer-prevention

This is early, but it widens the imagination frontier: treatment after diagnosis -> prevention before cancer develops.

### 2.5 Options/GEX Context In The Local Dashboard

The local `site/gex/MRNA.json` snapshot as of 2026-07-04 showed:

- Spot: 79.76
- Regime: long
- IV30: 96.73
- Put/call open-interest ratio: 0.26
- Put/call volume ratio: 0.22
- Call wall: 80.0 with very strong wall strength
- Put wall: 76.0
- Largest OI: 80.0
- Vol-hole state: `COILED_UP`

This says the option market had a strong upside/convexity structure around the 80 strike, but the repo's own options research is clear: without trade-level NBBO, signed direction is soft. The reliable parts are magnitude, open interest, walls, implied volatility, and positioning shape.

Relevant repo doctrine: `research/OPTIONS_FLOW_DATA.md` and `research/OPTIONS_ALPHA_MASTERPLAN.md`.

## 3. The General Pattern: Sponsorship Breakaway Anatomy

A Moderna-like move has five stages.

### Stage A: Compressed Prior

The best alpha breakaways usually start from a hated, forgotten, or de-risked base. This is not the same as "cheap." It means the marginal model is stale.

Useful signs:

- Stock is far below old highs or has a long negative narrative.
- Sell-side average target and consensus rating are stale or below spot.
- Revenue/earnings headline is bad, but investors begin focusing on a new asset or platform.
- Ownership is high in passive holders but active growth sponsorship has thinned.
- Short interest or put demand is elevated enough to create future fuel.
- Sector sentiment is improving, but the stock is beating the sector by far more than beta explains.

For Moderna: COVID-revenue decay and losses kept the prior compressed, while oncology/flu/science-day milestones created a new underwriting path.

### Stage B: Catalyst Ladder

One catalyst makes a pop. A ladder makes sponsorship.

The important thing is not "news is good." The important thing is a sequence of events that lets large investors keep increasing position size with new evidence.

For biotech, a strong ladder might be:

- Durable Phase 2 data.
- Fully enrolled Phase 3 trial.
- Upcoming Phase 3 readout with clear timing.
- Regulatory panel or PDUFA date.
- Partner validation from a major pharma.
- Multiple indications using the same platform.
- Analyst day showing the platform can create repeatable programs.
- Balance-sheet/cost-cut path that extends runway.

For software, the analogous ladder might be:

- Product usage acceleration.
- Net retention stabilization.
- Margins inflecting.
- AI product monetization.
- Enterprise reference customers.
- Estimate revisions.

For industrials/defense:

- Budget authorization.
- Backlog conversion.
- Production-rate increases.
- Margin recapture.
- Strategic contract wins.

### Stage C: Relative Price Breakaway

This is the cleanest institutional footprint. Institutions can hide intent, but they cannot hide executed buying if it persistently reprices the stock relative to peers.

Core signal:

```text
excess_ret_21d = stock_return_21d - sector_or_theme_return_21d
excess_ret_42d = stock_return_42d - sector_or_theme_return_42d
```

Breakaway criteria:

- 21d excess return > +20 percentage points versus sector/theme.
- 42d excess return > +25 percentage points.
- New 63d or 126d relative high.
- Price is above the last failed rally high.
- Pullbacks are shallow relative to prior volatility.
- Up days have higher dollar volume than down days.
- The stock closes near the upper part of its daily range on repeated high-volume sessions.

For Moderna, the local 21d excess return versus XBI was +49.16 pp and versus XLV was +62.91 pp as of 2026-07-02.

### Stage D: Liquidity Confirmation

Institutional accumulation is not just price up. It is price up with enough dollar liquidity to support real capital.

Useful fields:

- `dollar_volume = close * volume`
- `dollar_volume_z_21`
- `volume_z_21`
- `transactions_z_21`
- `up_dollar_volume / down_dollar_volume`
- `close_location_value = (close - low) / (high - low)`
- `gap_hold_rate`: did a gap hold for 3, 5, 10 trading days?

For Moderna, local data showed:

- 2026-06-18: 24.1 million shares, about 1.54 billion dollars of turnover.
- 2026-07-02: 14.1 million shares, about 1.13 billion dollars of turnover.
- 2026-07-02 was a new multi-window close breakout, about 10.0% above the prior 252-trading-day closing high.

That is not retail-only liquidity. It does not prove "institutional buying," but it proves institutional-capacity trading.

### Stage E: Options Convexity Sponsorship

Options can help detect stocks like Moderna, but only if we use the right parts.

Reliable or mostly reliable without trade-level NBBO:

- Total option premium traded.
- Option volume relative to 20d/60d baseline.
- Volume/open-interest ratio.
- New open interest after high-volume sessions.
- Call open-interest concentration near upside strikes.
- Put open-interest floor or put-wall support.
- Implied volatility rank/percentile.
- Call/put IV spread.
- Risk reversal or skew.
- Term structure.
- GEX wall and magnet levels.
- Changes in OI by strike and expiry.

Soft or dangerous without trade-level NBBO:

- Signed premium.
- "Sweeps are bullish."
- "Large call buyer" claims.
- Dealer gamma-flow sign from bar data.
- Retail/institution attribution from order size alone.

Academic support exists for options information, but the details matter:

- Pan and Poteshman found that buyer-initiated opening option volume, especially put-call ratios, contained information about future stock returns. Source: https://www.nber.org/papers/w10925
- Cremers and Weinbaum found that put-call parity deviations, proxied through call-put implied-vol differences, had return-predictive information. Source: https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/deviations-from-putcall-parity-and-stock-return-predictability/D9BA8F97580328AAFD7988B092FE5D50
- Xing, Zhang, and Zhao found that individual option volatility smirk shape predicted future equity returns and was related to future earnings shocks. Source: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1107464

The dashboard should not copy these studies naively. It should translate them into measurable, forward-ledger features.

## 4. What Data Can And Cannot Tell Us

### 4.1 Institutional Ownership / 13F

13F is good for slow sponsorship breadth, not real-time detection.

The SEC states that 13F filings are due within 45 days after quarter-end, with 2026 deadlines including May 15 for 1Q and August 14 for 2Q.

Source: https://www.sec.gov/rules-regulations/staff-guidance/division-investment-management-frequently-asked-questions/frequently-asked-questions-about-form-13f

Nasdaq's institutional-holdings page says major institutional holdings are based on Form 13F, limited to equity securities and filed within 45 days after calendar quarter-end.

Source: https://www.nasdaq.com/market-activity/stocks/mrna/institutional-holdings

How to use 13F:

- Sponsorship breadth: number of funds adding, new, reducing, closing.
- Quality of sponsor: long-term growth fund, biotech specialist, quant, passive, event-driven, generalist.
- Concentration: top 10 active holders as % of float.
- Underweight pressure: benchmark weight vs active fund exposure.
- Whale validation: first-time positions by domain specialists.
- Crowding risk: too many hot-money funds at once.

How not to use 13F:

- Do not use it to explain a current six-day rally.
- Do not infer current ownership from prior-quarter holdings.
- Do not treat passive Vanguard/BlackRock changes as conviction.
- Do not ignore short, option, or derivative exposures not captured in long-only 13F.

For a Moderna-style detector, 13F should be a slow context feature:

```text
ownership_pressure =
  active_holder_count_change_z
  + specialist_holder_count_change_z
  + new_quality_sponsor_count
  - hot_money_churn_count
  - passive_only_penalty
```

Everything must be timestamped on filing date plus one trading day, not quarter-end.

### 4.2 Form N-PORT / Fund Holdings

Form N-PORT can reveal fund holdings, but it is also delayed. The SEC Form N-PORT instructions say funds file monthly portfolio reports, but reports for each month in a fiscal quarter are filed no later than 60 days after the end of the fiscal quarter, and only some information becomes public.

Source: https://www.sec.gov/files/formn-port.pdf

Use case:

- Better fund-level holdings than 13F for registered funds.
- Useful for "which active growth/healthcare funds are involved?"
- Useful for sponsor quality and style alignment.

Limit:

- Too stale for entry.
- Must be joined only when public.

### 4.3 Short Interest And Short Volume

Short interest can show squeeze fuel, but it is delayed and sparse. FINRA says member firms report short positions twice a month and data is published on the seventh business day after the reporting settlement date.

Source: https://www.finra.org/finra-data/browse-catalog/equity-short-interest

Daily short volume is not the same thing as short interest. FINRA explicitly warns that short-sale files are not intended to equate to bi-monthly reported short-interest positions.

Source: https://www.finra.org/finra-data/browse-catalog/short-sale-volume

Use case:

- Short interest / float.
- Days to cover.
- Borrow cost if available from a vendor.
- Short-interest change around catalyst windows.
- "Crowded short + high-quality catalyst + price breakaway" as a special mode.

Do not mistake daily short-volume ratios for "shorts are attacking" or "shorts are covering."

### 4.4 Options Flow

This is the best near-real-time sponsorship-adjacent layer, but only if we refuse fake precision.

Build these:

- `opt_premium_z_20`: total premium vs baseline.
- `opt_volume_z_20`: total contracts vs baseline.
- `call_oi_delta_5d`: call OI change.
- `put_oi_delta_5d`: put OI change.
- `net_doi_call_share`: call share of new OI.
- `vol_over_oi_burst`: high volume compared with prior OI.
- `upside_call_wall_growth`: call wall moves higher or strengthens.
- `put_wall_floor_growth`: put wall rises under price.
- `rr25_change`: risk-reversal changes toward call demand.
- `iv_rank_change`: IV repricing from low/normal to high.
- `term_slope_change`: front vol demand vs back vol.
- `gex_coiled_up`: spot near upper call wall with defined lower put wall.

For Moderna, local GEX on 2026-07-04 had a very strong 80 call wall, put/call OI ratio 0.26, put/call volume ratio 0.22, IV30 near 97, and a coiled-up state. That is a classic "convexity sponsorship or chase" profile. It needs follow-through evidence to distinguish durable sponsorship from near-term blow-off.

### 4.5 Buy-Side Research

We cannot observe private buy-side research directly, and we should not try to acquire MNPI. The repo's qualitative-intelligence compliance boundary explicitly excludes expert networks and non-public sources.

Public proxies:

- Analyst target revision velocity.
- Consensus dispersion widening or collapsing.
- First non-consensus upgrade by a credible domain analyst.
- Repeated conference invitations and transcript Q&A depth.
- Key opinion leader comments in public medical conferences, where legally public.
- ClinicalTrials.gov milestones and enrollment/completion changes.
- Regulatory calendar events: advisory committee, PDUFA, CHMP, MHRA, etc.
- Partner validation: Merck/Moderna, large pharma option exercises, milestone payments.
- Press-release novelty score: is this genuinely new, or recycled science?
- Institutional media framing: "highest close since..." and "top S&P performer" are secondary but useful attention markers.

For Moderna, the useful research proxy is not simply "analyst target went up." The useful proxy is "analyst models were stale while events forced them to reopen the long-duration pipeline value." Piper Sandler reportedly raised its target to 77 from 69 after Science Day, but the average target still sat far below spot. That disagreement is a signal of active re-underwriting and high uncertainty.

Sources:

- https://www.investing.com/news/analyst-ratings/piper-sandler-raises-moderna-stock-price-target-on-pipeline-progress-93CH-4763010
- https://stockanalysis.com/stocks/mrna/

## 5. Sponsorship Breakaway Score v0

This should ship as display/shadow only until the forward ledger proves it has value.

### 5.1 Candidate Gate

A stock enters the candidate set only if all are true:

```text
liquid = median_dollar_volume_20d >= 25 million
optionable = has_options_snapshot_or_gex == true
sector_map = stock has sector/theme benchmark
relative_breakaway =
  excess_ret_21d_vs_sector >= 20 pp
  OR excess_ret_42d_vs_sector >= 25 pp
new_high = close >= prior_63d_close_high OR relative_close >= prior_126d_relative_high
volume_confirm = dollar_volume_z_21 >= 1.0 OR 5d_dollar_volume / 60d_avg >= 1.5
catalyst_present = public catalyst in last 30d OR upcoming catalyst in next 90d
```

For early detection, allow a weaker "pre-breakaway watch" candidate:

```text
price_base_compressed = stock below 52w high by >= 30% at start of setup
rs_turn = 21d relative strength crosses above 63d relative strength
volume_confirm = dollar_volume_z_21 >= 1
catalyst_ladder = at least 2 public milestones in next 180d
```

### 5.2 Score Components

Total: 100 points.

| Component | Max | What It Measures |
|---|---:|---|
| Relative price breakaway | 25 | sector/theme excess return, new relative highs, persistence |
| Institutional-capacity tape | 20 | dollar-volume expansion, high-volume closes, pullback absorption |
| Options convexity sponsorship | 20 | OI growth, call-wall migration, put/call OI, skew, IV, vol/OI bursts |
| Catalyst ladder | 20 | quality, sequence, near/far timing, platform relevance, partner/regulatory validation |
| Ownership/supply pressure | 10 | active 13F/N-PORT sponsorship, short interest, passive/active float structure |
| Research echo | 5 | analyst revisions, target dispersion, conference/transcript intensity |

Suggested labels:

- 80-100: Breakaway sponsorship state.
- 65-79: Emerging sponsorship, needs digestion.
- 50-64: Watch, catalyst/tape improving.
- 35-49: One-day or sector-beta move.
- Below 35: Ignore.

### 5.3 Hazard Penalties

Subtract risk points:

- Price > 2.5 ATR above 20d VWAP: -10.
- IV rank > 95 and no OI persistence: -8.
- Call wall directly overhead and repeated rejection: -8.
- One-day gain > 20% with no follow-through after 3 days: -8.
- Catalyst exhausted with no next milestone: -10.
- Consensus target below spot by >30% and no new upward revisions: -5.
- Insider cluster selling into rally: -5 to -10, context-dependent.
- Short-volume-only story with no true short-interest evidence: -5.
- Low float / low liquidity: reject or isolate.

For Moderna as of early July 2026, the state would likely be:

- Strong breakaway: yes.
- Strong liquidity: yes.
- Options convexity: yes, but near an 80 call wall.
- Catalyst ladder: yes.
- Entry quality: late/chasing risk elevated.
- Best research action: monitor digestion and OI persistence, not blindly chase the vertical leg.

## 6. Entry Logic: How To Avoid Buying The Top

Finding the right stock is easier than finding the right entry. Sponsorship breakaways often punish late entry.

The entry framework should separate discovery from execution.

### Discovery State

The stock is in a sponsorship breakaway.

Criteria:

- Relative breakaway confirmed.
- Dollar-volume expansion confirmed.
- Catalyst ladder intact.
- Options structure supportive.
- Sector/theme context not hostile.

Action: add to high-priority watchlist, not automatic buy.

### First Digestion Entry

This is the highest-quality swing entry.

Look for:

- 3 to 8 trading days sideways or shallow pullback after impulse.
- Price holds above prior breakout level or anchored VWAP from catalyst day.
- Down-volume contracts.
- Put wall or high-OI strike rises under price.
- Call wall rolls upward rather than acting as rejection.
- IV cools but OI does not collapse.
- No downgrade or negative regulatory update.

### Continuation Entry

Use when the stock does not pull back.

Look for:

- Tight 3-day range after a high-volume move.
- Inside day or narrow-range close near highs.
- Sector up but stock still beats sector.
- Volume not exhausted.
- Options OI migrates to higher strikes.

### Failure / Exit Warning

The move is likely becoming a blow-off or failed squeeze if:

- Price loses catalyst-day VWAP on heavy volume.
- Call wall remains fixed below spot and price repeatedly rejects.
- OI collapses after expiration.
- IV remains high while price stalls.
- Relative strength versus sector rolls over for 5-10 sessions.
- New catalyst is far away and the recent event is exhausted.
- Analyst revisions do not follow the price.

## 7. Implementation Plan For Macro Dashboard

### 7.1 New Engine

Add:

- `engine/sponsorship_breakaway.py`
- `scripts/build_sponsorship_breakaway.py`
- `tests/test_sponsorship_breakaway.py`

Outputs:

- `data/sponsorship_breakaway/candidates.parquet`
- `data/sponsorship_breakaway/ledger.jsonl`
- `site/stockdata/sponsorship_breakaway.json`
- optional compact UI card on `us_stocks.html`, `stock_view`, or a new "Breakaway Desk"

### 7.2 Inputs Already Present Or Adjacent

Use existing repo surfaces:

- Price and volume: `data/massive_stock_day/{SYM}.parquet`
- Sector/theme map: `scripts/grade_us_board.py`, stock library sector fields, ETF maps
- Sector ETFs: `data/massive_stock_day/XBI.parquet`, `XLV`, `SPY`, etc.
- GEX/options context: `site/gex/{SYM}.json`, `data/polygon_gex/summary_{SYM}.parquet`, `site/flow/mastermind.json`
- Options doctrine: `research/OPTIONS_FLOW_DATA.md`, `research/OPTIONS_ALPHA_MASTERPLAN.md`
- 13F: `data/quiver/sec13f.parquet`, `data/quiver/sec13f_changes.parquet`
- Smart-money tracker: `data/smart_money/`, `site/factordata/smartmoney*.json`
- Short volume/short interest: `data/finra_short_volume/`, and future true short-interest pull if available
- News/catalyst surfaces: financial news, GDELT, SEC 8-K, clinical/regulatory calendar if added
- Forward outcome ledger: reuse the board ledger and/or create a dedicated append-only breakaway ledger

### 7.3 Candidate JSON Contract

Example:

```json
{
  "schema": "sponsorship_breakaway.v0",
  "as_of": "2026-07-02",
  "ticker": "MRNA",
  "benchmark": "XBI",
  "sector": "Biotechnology",
  "state": "breakaway_sponsorship",
  "score": 86,
  "display_only": true,
  "local_evidence": {
    "ret_21d": 0.7476,
    "bench_ret_21d": 0.2559,
    "excess_21d_pp": 49.16,
    "ret_126d": 1.6228,
    "dollar_volume_z_21": 1.63,
    "new_252d_close_high": true
  },
  "options_evidence": {
    "iv30": 96.73,
    "put_call_oi_ratio": 0.26,
    "call_wall": 80.0,
    "put_wall": 76.0,
    "vol_hole_state": "COILED_UP",
    "direction_reliable": false
  },
  "catalyst_ladder": [
    {
      "date": "2026-01-20",
      "type": "oncology_data",
      "summary": "5-year intismeran plus Keytruda melanoma data"
    },
    {
      "date": "2026-06-18",
      "type": "regulatory_panel",
      "summary": "FDA VRBPAC 9-0 vote for mRNA-1010 benefit-risk"
    },
    {
      "date": "2026-06-25",
      "type": "investor_day",
      "summary": "Science Day platform expansion, AI/data engine, T-cell engagers, in vivo CAR-T"
    }
  ],
  "entry_read": "watch_for_digestion",
  "hazards": [
    "extended_after_vertical_move",
    "spot_near_80_call_wall",
    "average_analyst_target_below_spot"
  ]
}
```

### 7.4 Forward Validation

Do not score this live until it earns it.

Pre-register outcome tests:

- Forward 5d, 10d, 21d, 63d excess return versus sector ETF.
- Forward MFE/MAE versus sector.
- Clean-hold label: did it avoid a close below catalyst-day VWAP or breakout pivot before making new highs?
- Blow-off label: did it lose >50% of the impulse within 21 trading days?
- Continuation label: did the stock hold above the 10d moving average for 10 sessions after signal?
- Digest-and-go label: did first pullback entry outperform chase entry?

Core comparisons:

- Breakaway score high vs all liquid optionable names.
- Breakaway score high vs high relative-strength names with no catalyst ladder.
- Options-supported breakaways vs price-only breakaways.
- Biotech-specific breakaways vs software/industrial/consumer breakaways.

Honesty constraints:

- All ownership data timestamped by filing/publication date, not position date.
- Options OI snapshots used only after available.
- News used only by publication timestamp.
- No same-day EDGAR close unless the repo's EDGAR rules allow it.
- No expert-network or MNPI-like sources.
- Print nulls and false positives.

## 8. Creative Signal Ideas Worth Testing

### 8.1 Research-Reunderwriting Velocity

Detect when the market is forcing analysts and investors to reopen old models:

```text
research_reunderwriting =
  abs(price / consensus_target - 1)
  + target_revision_count_30d
  + target_dispersion_z
  + article_topic_shift_score
  + transcript_question_depth_score
```

The interesting state is not just upgrades. It is "price has escaped the published model and research has to catch up."

### 8.2 Underweight Trap

Find names where benchmark-aware managers may be forced to add:

```text
underweight_trap =
  benchmark_weight_change
  + active_ownership_low_vs_history
  + relative_strength_breakout
  + upcoming_catalyst_quality
  - passive_only_ownership
```

If a stock becomes a large index/sector contributor while active managers are underweight, buying can persist for weeks.

### 8.3 Convexity Ladder

Track whether options interest rolls upward:

```text
convexity_ladder =
  call_wall_today > call_wall_5d_ago
  + largest_oi_strike_today > largest_oi_strike_5d_ago
  + put_wall_today > put_wall_5d_ago
  + call_oi_delta_5d > percentile_80
  + iv_up_with_price_up
```

This is better than one-day "unusual options."

### 8.4 Catalyst Half-Life

Some catalysts decay in hours. Others create a multi-month re-rating.

Model event half-life:

- Regulatory acceptance: medium.
- AdCom 9-0 vote: medium to high until PDUFA.
- Phase 2 durability with Phase 3 readout pending: high.
- Analyst day with no hard data: low to medium unless followed by revisions.
- Single headline with tiny TAM: low.
- Partnership with economics: high.
- Trial halt/safety issue: negative high.

### 8.5 Base-to-Breakaway Energy

The best runs often come from long compression:

```text
base_energy =
  drawdown_from_3y_high
  + days_below_200dma
  + short_interest_float
  + negative_revision_history
  + cash_runway_improvement
  + first_200dma_reclaim
```

But this must be paired with catalyst quality. Otherwise it just finds broken stocks.

## 9. False Positives And Troubleshooting

### False Positive: Meme Squeeze

Symptoms:

- Huge short interest.
- Call volume explodes.
- No credible catalyst ladder.
- Social attention dominates public evidence.
- Price collapses after OPEX.

Fix:

- Require catalyst quality score.
- Require OI persistence after expiration.
- Require institutional-capacity dollar volume, not just retail option volume.

### False Positive: One-Day Biotech Binary

Symptoms:

- Massive Phase 1/2 headline.
- Tiny float.
- No partner.
- No near-term next milestone.
- IV remains extreme.

Fix:

- Penalize no next milestone.
- Penalize no liquidity.
- Require 3-5 day hold above gap.

### False Positive: Sector Beta

Symptoms:

- Sector ETF is also up strongly.
- Stock's excess return is small.
- Many peers show similar move.

Fix:

- Sector-relative threshold.
- Peer decile rank.
- Residual return after beta to XBI/XLV/SPY.

### False Positive: Options Mirage

Symptoms:

- Huge call volume, but OI does not increase next day.
- IV collapses after event.
- Call wall pins price.

Fix:

- Use volume plus next-day OI.
- Use strike migration.
- Use IV plus price plus OI, not volume alone.

### False Positive: Stale 13F Narrative

Symptoms:

- Filings show institutions bought last quarter.
- Stock is already up 80%.
- The institutions may have sold before filing appeared.

Fix:

- Use 13F as slow sponsorship context only.
- Timestamp by filing date.
- Combine with current tape and options.

## 10. Proposed Dashboard Display

Make this compact. The user should see the state, not a paragraph.

Card fields:

- Ticker and benchmark.
- State: Breakaway / Emerging / Watch / Blow-off risk / Failed.
- 21d excess vs sector.
- Dollar-volume impulse.
- Catalyst ladder count.
- Options convexity state.
- Ownership pressure state.
- Entry read: chase risk / digestion setup / continuation / failed.
- Key hazards.

Example copy:

```text
MRNA - Breakaway Sponsorship
+49 pp vs XBI over 21d. Dollar volume expanded. Catalyst ladder active: flu AdCom, Science Day, intismeran readout path. Options show high IV and strong 80 call wall. Entry read: extended; wait for digestion or OI roll higher.
```

## 11. Research Verdict

The best way to identify stocks like Moderna is to detect the transition from "speculative rebound" to "institutional sponsorship breakaway." The transition is visible when:

1. The stock beats its own sector by a large margin.
2. The move repeats across days/weeks, not just one gap.
3. Dollar volume expands enough for real capital.
4. The catalyst ladder gives investors permission to keep adding.
5. Options positioning shows durable convexity demand or rising support, not just one-day call volume.
6. Ownership data later confirms quality sponsors, but is not used for real-time entry.
7. Analyst/research proxies show the published model is being reopened.

For Moderna, the current descriptive state is strong sponsorship breakaway with elevated chase risk. The research task is not "why did it go up?" in one sentence. The task is building a repeatable detector that sees when a stale institutional prior is being forcibly repriced by a sequence of public catalysts and confirmed by capital-capacity tape.

The build should be shadow/display-only first. If it works, it will show up in the forward ledger as better 21d/63d excess returns and cleaner digestion entries versus simple high-relative-strength chasing. If it does not, the null is still useful: it will tell us that the story was visible only after the alpha was already gone.
