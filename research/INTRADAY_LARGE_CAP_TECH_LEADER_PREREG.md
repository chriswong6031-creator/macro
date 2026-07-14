# Intraday Large-Cap Tech Leader Study — Phase-0 Preregistration

**Registered:** 2026-07-14, before outcome computation  
**Owner:** Intraday Flow Tracker (IFT) research lane  
**Status:** research/display only; `may_rank=false`, `may_alert=false`, `may_size=false`  
**Question:** can information available before the open, then through 09:45 ET, identify the large-cap tech stock that will lead the rest of the regular session?

This is not a new leader engine. It is an IFT-owned historical study. Flow Leaders remains the owner of prior-session options-flow description, Mag7 Command remains the owner of Mag7 cohort leadership, and Day Trade Suite remains the execution/charting surface. No result from this study enters a live rank, alert, buy strip, sizing rule, or Mastermind/Neural Web authority path.

## 1. Fixed universe and data cohorts

### Price/volume cohort

The fixed stock universe is:

`AAPL MSFT NVDA AMZN META GOOGL TSLA AVGO AMD MU QCOM AMAT LRCX KLAC MRVL ORCL CRM ADBE PLTR NOW PANW ANET IBM`

`QQQ` is the benchmark and is never eligible to win. The universe was selected before outcome computation from liquid current large-cap US technology/platform/semiconductor names for which the Terminal archive has 5-minute bars. This is a current-universe study and therefore carries survivorship/composition risk; no claim will be extended to a historical point-in-time Nasdaq-100 universe.

Source: Terminal's Polygon/Massive adjusted 5-minute archive, including extended hours. Expected coverage is roughly 2025-06-02 through 2026-07-10. Bar timestamps are ET wall-clock values encoded as epoch seconds. Only full regular sessions with all 78 bars from 09:30 through 15:55 for QQQ and every eligible stock are admitted. Half-days and incomplete sessions are excluded.

### Historical options-magnitude overlay

Source: `data/options_flow/summary_<TICKER>.parquet`, expected 2026-01-02 through 2026-07-10. Only fields valid from daily contract aggregates are admitted:

- gross contract volume;
- gross premium;
- put/call volume ratio;
- 0DTE volume share.

Signed premium, signed put/call, gamma-flow sign, delta-flow sign, DOI, and other sparsely populated directional fields are excluded from the primary study. Day `t-1` data may be used for a day `t` decision only if its production availability is confirmed before 09:30 ET; otherwise a live implementation must mark the witness unavailable.

### Signed-flow sensitivity cohort

`data/options_tape_signed/<TICKER>.parquet` will be examined separately for `AAPL MSFT NVDA AMZN META GOOGL TSLA AMD`. It is never pooled with aggregate-magnitude history. Its direction gate currently fails, and exclusions are material, so this cohort is diagnostic only and cannot support the recommended detector.

## 2. Decision times and point-in-time boundary

Two decisions are tested and never conflated:

1. **09:30 nomination:** a pre-open top-three watchlist using only data through the completed 09:25–09:29 premarket bar plus prior-session data.
2. **09:45 confirmation (primary):** a selection after the 09:30, 09:35, and 09:40 bars are complete. The executable entry anchor is the 09:45 bar open. No value from the 09:45 bar or later may enter a feature.

Beta, ATR, volume baselines, option baselines, and momentum features use sessions ending at `t-1` or earlier. Any rolling statistic is shifted before joining to day `t`.

## 3. Outcomes fixed before testing

For stock `i` on session `t`:

- `after_return`: 15:55 close / 09:45 open - 1.
- `beta_60`: covariance of the stock and QQQ close-to-close returns divided by QQQ variance over the prior 60 full sessions, minimum 40, ending at `t-1`, clipped to `[0.50, 2.50]`.
- `after_residual`: `after_return - beta_60 * QQQ_after_return`.
- **Relative-return winner:** eligible stock with the highest `after_residual`.
- **Economic tie set:** every eligible stock within 0.20% of the maximum `after_residual`.
- **Raw-return winner:** eligible stock with the highest `after_return`, reported as a sensitivity label.
- **Clear-leader session:** the relative winner has raw `after_return >= 0.50%`, `after_residual >= 0.50%`, and leads second place by at least `0.35%`. Other sessions are legitimate **NO CLEAR LEADER** days.

Tradeability outcomes are measured separately from winner identity:

- `MAE`: minimum post-entry low / 09:45 entry - 1;
- `MFE`: maximum post-entry high / 09:45 entry - 1;
- `VWAP-hold`: fraction of post-entry closes above expanding regular-session VWAP;
- `VWAP-crosses`: sign changes of close minus expanding VWAP after entry;
- `trend-efficiency`: `(15:55 close - entry) / sum(abs(5-minute close changes after entry))`;
- `close-location`: final close location within the post-entry high-low range.
- `rescue-fraction`: across hypothetical 5-minute closing-price entries from 09:45 through 14:00, the fraction for which a later close by 15:55 reaches the hypothetical entry plus 0.05%.

A stock is a **forgiving continuation** only when all of the following preregistered conditions hold:

- `after_residual >= 0.50%`;
- `MAE >= -0.50 * ATR20_pct`, where `ATR20_pct` is known at `t-1`;
- `VWAP-hold >= 70%`;
- `rescue-fraction >= 75%`.

This boolean is not a weighted score. There may be zero, one, or several forgiving continuations in a session.

## 4. Candidate attributes

### Known at 09:30

- prior 1-, 5-, and 20-session beta-adjusted relative strength;
- 5-vs-20-session relative-strength acceleration;
- prior-day close location;
- premarket return and beta-adjusted premarket return versus QQQ;
- premarket dollar volume;
- premarket volume divided by the stock's prior-20-session median for the same window;
- premarket range divided by prior close;
- prior-day options gross-premium ratio to its trailing-20 median, shifted;
- prior-day options volume ratio to its trailing-20 median, shifted;
- prior-day put/call volume ratio and 0DTE share;
- option-attention recurrence: count in the last three sessions with gross-premium ratio >= 1.25.

### Added at 09:45

- first-15-minute raw return;
- first-15-minute `beta_60`-adjusted return versus QQQ;
- gap and beta-adjusted gap;
- first-15-minute time-of-day RVOL versus the prior-20 same-window median;
- opening dollar-volume share of the eligible universe;
- distance from session VWAP and above-VWAP boolean;
- opening-range close location;
- first-15-minute trend efficiency;
- first-15-minute range expansion versus its prior-20 median.

No news/catalyst or earnings calendar is silently inferred. Results will explicitly disclose this omitted-variable limitation.

## 5. Fixed baselines and rules

Every single-feature selector chooses the highest value, with top-three recall also reported. Baselines are:

- random selection (`1/N` exact-hit expectation and `3/N` top-three expectation);
- always `NVDA`;
- prior-day residual-return leader;
- prior 5-session relative-strength leader;
- premarket beta-adjusted-return leader;
- prior-day options gross-premium-anomaly leader;
- first-15-minute raw-return leader;
- first-15-minute beta-adjusted-RS leader;
- first-15-minute RVOL leader;
- beta-adjusted gap leader.

The only multi-leg rule is a transparent IFT K-of-N confirmation, not a weighted score:

- L1: first-15-minute beta-adjusted RS is in the cross-sectional top three;
- L2: first-15-minute RVOL is at least 1.20;
- L3: 09:40 close is above session VWAP and opening-range close location is at least 0.70;
- L4: first-15-minute trend efficiency is at least 0.35.

`PV_CONFIRM_RS` requires at least 3 of 4 legs and selects the qualifier with the highest first-15-minute beta-adjusted RS. `PV_CONFIRM_RVOL` uses the same qualifiers and selects the highest-RVOL qualifier. If no stock qualifies, the rule abstains.

Options are tested only as a separate witness/ablation:

- `OPT_ATTN`: prior-day gross-premium ratio to trailing-20 median is at least 1.25;
- `OPT_RECUR`: at least two of the last three sessions meet `OPT_ATTN`.

`PV_CONFIRM_RS + OPT_ATTN` means the price/volume qualifier must also carry the options-attention witness. If none does, it abstains. Options values are not added to price/volume values and do not change the price/volume sort key.

## 6. Evaluation and anti-overfit rules

The primary inference set is the final 40% of admitted sessions in chronological order. The first 60% is labeled development/descriptive. Thresholds above are frozen and will not be changed after looking at either segment.

For every selector, report:

- coverage / abstention rate;
- exact relative-winner hit rate;
- economic-tie hit rate;
- top-three recall where applicable;
- clear-leader hit rate;
- mean and median selected `after_residual`;
- mean selected raw return after a fixed 0.10% round-trip cost;
- selected positive-residual rate;
- mean oracle regret;
- mean MAE, MFE, VWAP-hold, trend-efficiency, and forgiving-continuation rate.

Univariate winner attributes will be assessed by the winner's cross-sectional percentile, top-quartile enrichment, top-one hit rate, and top-three recall. Date is the independent unit. Confidence intervals use week-block resampling. Feature-atlas empirical p-values use within-date label permutation and Benjamini-Hochberg false-discovery control. Ticker-cluster bootstrap and random row splits are prohibited.

Price-only history, options-magnitude overlay, and signed-flow sensitivity remain separate cohorts. A shorter options cohort cannot overwrite the longer price/volume conclusion. Results will be reported by development/holdout segment and by clear-leader versus all sessions.

Robustness checks are frozen as: leave-NVDA-out, leave-one-ticker-out for the primary first-15-minute RS selector, and four chronological blocks. These are robustness disclosures, not alternative primary specifications.

## 7. Promotion boundary

Phase 0 may conclude only one of:

- **useful shortlist/confirmation evidence**;
- **insufficient / unstable evidence**;
- **negative evidence**.

It may not conclude that a winner can be known with certainty. Any later live shadow must preserve an abstain state, stamp feature availability, accrue predictions before outcomes, and pass a separately registered promotion gauntlet before ranking authority is considered.
