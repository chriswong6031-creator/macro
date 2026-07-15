# Intraday Large-Cap Tech Leader: Phase-0 Results

- **As of:** 2026-07-14
- **Historical data through:** 2026-07-10
- **Status:** private research; shortlist evidence only; no live rank, alert, sizing, or authority
- **Canonical deliverable:** this memo
- **Preregistration:** [`INTRADAY_LARGE_CAP_TECH_LEADER_PREREG.md`](INTRADAY_LARGE_CAP_TECH_LEADER_PREREG.md)
- **Reproducible tables:** [`intraday_large_cap_tech_leader_phase0/`](intraday_large_cap_tech_leader_phase0/)

## Bottom line

There is no supported way to **consistently know the single future winner** before or just after the open. The useful result is narrower:

1. By 09:45, first-15-minute relative strength is useful for recognizing the stock that is **already the full-day tape leader**: in the untouched holdout it named the eventual prior-close-to-close winner 32.1% of the time and placed it in the top three 52.4% of the time.
2. It was much weaker at predicting the stock that would do best **from 09:45 onward**: 14.3% exact and 22.6% top-three. Its mean beta-adjusted continuation was +0.42%, but the confidence interval crossed zero, the median was only +0.009%, and just 51.2% of selections had positive residual continuation.
3. The most repeatable winner attributes were abnormal opening participation and range: first-15-minute RVOL, first-15-minute range expansion, a large premarket range, and prior 5-/20-session relative strength. These are probabilistic shortlist attributes, not a deterministic recipe.
4. Last-available daily options magnitude, conservatively lagged to T-2, did not add robust holdout information. The historical field is a gross attention proxy, not institutional buying or directional premium flow.
5. The correct operating design is therefore **shortlist -> opening confirmation -> dominance gate -> possibly no clear leader**. MACD, VWAP, and pullback structure should time an entry only after identity is established; they should not be used to decide the leader.

The study conclusion is **useful shortlist/confirmation evidence, insufficient for a consistent single-winner detector**.

## The two questions that must not be mixed

“NVDA is up 4% and obviously owns today's tape” is a **current/full-day leader classification** question. Much of that move may already be in the overnight gap, premarket, or first 15 minutes.

“Which stock should I buy at 09:45 because it will outperform for the rest of today?” is a **remaining-session forecast**. This is harder and is the preregistered primary test.

The distinction explains the apparent contradiction in the results:

| Holdout question | 09:45 first-15 beta-RS result |
|---|---:|
| Exact eventual full-day winner | 32.1% |
| Eventual full-day winner in top three | 52.4% |
| Exact 09:45-close beta-residual winner | 14.3% |
| 09:45-close beta-residual winner in top three | 22.6% |

Premarket beta-RS and gap beta-RS found the full-day winner 29.8% of the time, but their selected names had almost no average residual continuation after 09:45. They often recognized a move that had already happened.

## Study contract

- **Universe:** `AAPL MSFT NVDA AMZN META GOOGL TSLA AVGO AMD MU QCOM AMAT LRCX KLAC MRVL ORCL CRM ADBE PLTR NOW PANW ANET IBM`; benchmark `QQQ`.
- **Price data:** five-minute bars. Rolling features use an uncompressed 278-session QQQ exchange calendar, including scheduled half-days. Outcome dates require exact 78-bar regular-session coverage for every ticker.
- **Admitted price sample:** 209 sessions from 2025-07-31 through 2026-07-10.
- **Development / holdout:** first 125 sessions through 2026-03-10; final 84 sessions from 2026-03-11 through 2026-07-10.
- **Primary winner:** highest QQQ-beta-adjusted return from the 09:45 bar open through the 15:55 close.
- **Clear leader:** raw continuation at least +0.50%, residual continuation at least +0.50%, and residual margin over number two at least 0.35%.
- **Execution accounting:** selected raw return is also shown after a fixed 0.10% round-trip cost. This is not a fill/slippage model.
- **Options cohort:** 106 complete sessions; holdout 43. Provider publication latency forces the daily aggregate to normally T-2 at a 09:30/09:45 decision.
- **Signed sensitivity:** 100 complete sessions across only eight names; holdout 40; diagnostic because its direction-quality gate fails.
- **Inference:** chronological holdout, week-block confidence intervals, within-date permutation, and BH correction. The final interpretation is more conservative than the formal q-values because ticker winner rates are not uniform.

The exact runner, input hashes, runtime versions, cutoff rules, and artifact inventory are recorded in [`manifest.json`](intraday_large_cap_tech_leader_phase0/manifest.json).

## Holdout selector results

The development-modal baseline is `MU`, selected only because it was the most frequent development-period winner and then frozen before holdout. It is a fairer baseline than “always NVDA” or a uniform 1-in-23 draw because the outcome favors higher-volatility names.

| Selector | Exact | Top three | Mean residual | 95% block CI | Median residual | Positive residual | Mean MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| Random expectation | 4.35% | 13.04% | — | — | — | — | — |
| Always NVDA | 3.57% | 3.57% | -0.05% | -0.33% to +0.28% | -0.03% | 48.8% | -1.38% |
| Development modal (`MU`) | 8.33% | 8.33% | +0.16% | -0.30% to +0.62% | +0.03% | 51.2% | -2.84% |
| Prior 5-session beta-RS | 13.10% | 29.76% | +0.54% | -0.18% to +1.19% | +0.19% | 53.6% | -2.40% |
| First-15 beta-RS | **14.29%** | 22.62% | +0.42% | -0.14% to +0.97% | **+0.009%** | 51.2% | -2.05% |
| First-15 RVOL | 13.10% | 26.19% | +0.34% | -0.12% to +0.78% | +0.17% | 54.8% | -2.04% |
| Preregistered price/volume confirmation | 11.90% | 19.05% | +0.28% | -0.31% to +0.83% | +0.009% | 51.2% | -2.08% |

No selector has a positive residual-return confidence interval wholly above zero. First-15 beta-RS also hit only 12.9% of the 62 holdout sessions that eventually met the clear-leader definition.

The average is right-tail driven. It should not be translated into “I can enter badly and the stock will probably rescue me.” The first-15 beta-RS selection suffered a mean -2.05% adverse excursion, had essentially zero median residual return, and produced a positive residual only about half the time.

## Attributes of a historical winner

On the 84-session holdout, the eventual residual winner tended to rank above its peers on these fields:

| Attribute at 09:45 or earlier | Winner mean percentile | Winner in top six | Null top-six rate | Enrichment | BH q |
|---|---:|---:|---:|---:|---:|
| First-15 time-of-day RVOL | 63.9 | 45.2% | 26.1% | 1.73x | 0.004 |
| Prior 5-session beta-RS | 63.6 | 39.3% | 26.1% | 1.51x | 0.006 |
| Premarket range / prior close | 62.7 | 39.3% | 26.1% | 1.51x | 0.004 |
| First-15 range expansion | 61.5 | 38.1% | 26.1% | 1.46x | 0.010 |
| Prior 20-session beta-RS | 60.8 | 40.5% | 26.1% | 1.55x | 0.010 |
| Beta-adjusted opening gap | 59.5 | 36.9% | 26.1% | 1.41x | 0.023 |

Interpretation:

- **Participation matters:** abnormal opening volume and range expansion are the clearest repeatable fingerprints.
- **Sponsorship matters:** multi-session relative strength is more useful than simply copying yesterday's winner.
- **Catalyst-like premarket activity matters:** a large premarket range is informative even without a news feed, although the study cannot tell whether earnings, an analyst event, or sector news caused it.
- **The first move alone is insufficient:** the eventual winner's mean first-15 beta-RS percentile was only 53.0 and was not significant after correction. The name with the strongest first 15 minutes can identify the visible full-day leader, but does not generally order the rest of the day's continuation.
- **These q-values are descriptive:** the permutation null assumes interchangeable ticker identities, while volatile names win more often. RVOL and range expansion are already normalized to each ticker's own trailing history and are more credible than unnormalized premarket range or raw multi-day RS. A follow-up must use ticker-preserving inference and own-history volatility normalization.

## Past instances: what a true easy leader looked like

These are holdout days when first-15 beta-RS selected the eventual residual winner:

| Date | Winner | 09:45-close raw | Residual | MAE | VWAP hold | 15m RVOL | Read |
|---|---:|---:|---:|---:|---:|---:|---|
| 2026-04-13 | ORCL | +9.32% | +7.53% | -0.46% | 100.0% | 1.57x | Clean participation and almost uninterrupted VWAP control |
| 2026-05-22 | QCOM | +6.61% | +7.03% | 0.00% | 100.0% | 1.42x | Ideal momentum-leader path |
| 2026-06-02 | MRVL | +5.56% | +4.47% | -3.58% | 100.0% | 5.82x | Correct winner, but far less forgiving than the close implies |
| 2026-06-26 | NOW | +3.66% | +3.72% | -0.71% | 100.0% | 1.07x | Strong control without extreme early RVOL |
| 2026-07-10 | NVDA | +3.09% | +2.45% | -0.13% | 97.3% | 0.91x | The intuitive NVDA experience: shallow dip and persistent demand |

The misses matter just as much. On 2026-04-27, NVDA became a clear remaining-session winner (+3.26% raw, +2.95% residual), but first-15 beta-RS chose MU because NVDA had not yet separated by 09:45. A leader can emerge later; a one-time opening call cannot cover that path.

The full 209-session census was also not “mostly NVDA”: `MU` won 23 times, `AMD` 18, `TSLA` and `ORCL` 16 each, `MRVL` and `ANET` 14 each, while `NVDA` won seven and `MSFT` zero. This reflects the fixed-current universe and a residual-return label that structurally favors more volatile names; it is not a recommendation to trade MU every day.

## Why options flow did not solve it

The aggregate history is mostly built from daily per-contract bars. `premium_mn` is approximately option closing price times full-day contract volume times 100, summed across contracts. It is therefore a **gross options-attention proxy**:

- it does not reveal whether customers bought or sold;
- it does not distinguish opening from closing trades;
- it is not actual institutional premium paid;
- raw call share can represent call buying, call selling, hedging, closing, or spreads;
- the provider's next-day 11:00 ET update means yesterday's aggregate is not yet safely available at today's 09:45 cutoff, so the backtest uses normally T-2.

In the 43-session holdout, the strongest aggregate option attribute was last-available volume versus its trailing median: winner mean percentile 58.7, q=0.37. Gross premium ratio had percentile 54.0, q=0.50. Neither survived correction. Requiring option attention reduced coverage to 79.1% and produced 11.8% exact hits, worse than first-15 beta-RS alone.

The eight-name quote-signed sensitivity also failed to establish a directional edge. Its best q-value was 0.53 on only 40 holdout dates. It cannot support a detector.

The provider latency is documented in [Massive's day-aggregate documentation](https://massive.com/docs/flat-files/options/day-aggregates). The distinction between volume and open interest, and the fact that open interest is established after end-of-day clearing, is summarized in the [Options Industry Council FAQ](https://www.optionseducation.org/referencelibrary/faq/general-information).

If options are revisited, the needed data are point-in-time trade-level fields with explicit source timestamps and quality flags: buyer/seller-initiated premium, net delta proxy, volume relative to prior open interest, IV change, skew/term-structure change, repeat activity, and exclusion rate. Even then, options should remain a confirming witness until a prospective test proves otherwise.

## Proposed shadow protocol: leader or no leader

This is the concrete formulation for the next phase. It is deliberately a state machine, not a weighted score. Its thresholds are a **prospective preregistration seed**, not validated results from this study.

### 1. Build the pre-open sponsorship set

At 09:25, mark each ticker on three independent witnesses:

- prior 5-session beta-adjusted RS in the cross-sectional top quartile;
- prior 20-session beta-adjusted RS in the cross-sectional top quartile;
- premarket range, normalized to that ticker's own prior-20 distribution, in the top quartile.

A ticker enters the sponsorship set only if at least two witnesses are present. Add an explicit catalyst tag for earnings, guidance, analyst action, product news, or sector shock, but keep it separate from the price/volume state.

### 2. Require opening leadership at 09:45

A candidate must satisfy all mandatory conditions:

- top three first-15-minute beta-adjusted RS;
- positive first-15 raw and beta-adjusted return;
- above session VWAP at 09:40;
- first-15 residual lead over the number-two ticker of at least 0.20 percentage point.

It must also have at least two participation witnesses:

- first-15 time-of-day RVOL in the top quartile;
- first-15 range expansion in the top quartile;
- opening dollar-volume share in the top quartile;
- opening-range close location at least 0.70.

Finally it must have either pre-open sponsorship or a verified fresh catalyst.

### 3. Preserve a real abstain state

- Exactly one ticker passes: `LEADER_CANDIDATE`.
- Zero pass: `NO_CLEAR_LEADER`.
- More than one passes or the dominance margin disappears: `CONTESTED`, which is also a no-trade leader state.

The original 3-of-4 confirmation rule is rejected for this purpose because it called 98.4% of development days and 100% of holdout days. It did not avoid chop.

The old “forgiving” path label is also too broad: 1,063 of 4,807 ticker-sessions passed, averaging 5.1 names per day. The next label must require both path quality **and unique cross-sectional dominance**.

### 4. Keep options subordinate

Display one of `OPTIONS_CONFIRMS`, `OPTIONS_NEUTRAL`, or `OPTIONS_UNAVAILABLE`. The badge cannot create a candidate, eliminate one, or change the price/volume ordering. Daily T-2 magnitude should be treated as stale attention context. T-1 signed data may be used only when its direction-quality and timestamp gates pass.

### 5. Use momentum indicators for execution, not identity

Once a candidate exists, a low-timeframe MACD reset, first higher low, VWAP retest, or opening-range retest can time entry. The leader state invalidates if the stock loses VWAP, drops out of the relative-strength top three, or its dominance margin collapses. Re-evaluate the state every five minutes because late leaders exist.

Do not assume a bad entry will be rescued. That belief is precisely what the holdout median, MAE, and 51% positive-residual rate fail to support.

## Required next test before any live rank

1. Record immutable 09:45 and latency-safe 09:50 shadow predictions before outcomes for at least 60-100 new sessions; extend historical coverage toward at least 250 clean sessions.
2. Keep three labels separate: full-day/current leader, remaining-session raw/residual winner, and unique tradeable leader with path-quality plus dominance gates.
3. Compare against uniform random, development-modal ticker, prior-5 RS, first-15 RVOL, and first-15 beta-RS.
4. Normalize structural fields to each ticker's own point-in-time history and use ticker-preserving/fixed-effect inference.
5. Report median after-cost return, adverse excursion, calibration, abstention coverage, and four chronological blocks. A positive mean driven by one recent regime is insufficient.
6. Add point-in-time earnings/news/catalyst data. Its absence is likely a major omitted variable for the very days this detector is meant to find.
7. Do not promote unless exact/top-three performance beats the non-uniform baseline, the median economics are positive, the result is stable across blocks, and `NO_CLEAR_LEADER` demonstrably removes bad sessions.

Day trading remains highly risky; the study is a research protocol, not assurance that losses will recover. See [Investor.gov's day-trading risk summary](https://www.investor.gov/introduction-investing/investing-basics/glossary/day-trading).

## Artifact map

- [`selector_metrics.csv`](intraday_large_cap_tech_leader_phase0/selector_metrics.csv): exact, top-three, economics, path quality, confidence intervals.
- [`feature_atlas.csv`](intraday_large_cap_tech_leader_phase0/feature_atlas.csv): winner-attribute percentiles and descriptive inference.
- [`session_events.csv`](intraday_large_cap_tech_leader_phase0/session_events.csv): every historical winner and opening pick.
- [`winner_census.csv`](intraday_large_cap_tech_leader_phase0/winner_census.csv): ticker win frequencies and winner path properties.
- [`chronological_blocks.csv`](intraday_large_cap_tech_leader_phase0/chronological_blocks.csv): regime stability; the final block drove most positive economics.
- [`leave_one_out.csv`](intraday_large_cap_tech_leader_phase0/leave_one_out.csv): universe sensitivity.
- [`exploratory_full_day_atlas.csv`](intraday_large_cap_tech_leader_phase0/exploratory_full_day_atlas.csv): explicitly post-registered current/full-day leader classification.
- [`manifest.json`](intraday_large_cap_tech_leader_phase0/manifest.json): hashes, coverage, point-in-time correction, runtime, and authority boundaries.
