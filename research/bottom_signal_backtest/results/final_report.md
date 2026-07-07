# Bottom/Bounce Signal Backtest

> **⚠️ NO INFERENCE / TEST-LEAKED — DO NOT CITE AS EVIDENCE (banner added 2026-07-07).**
> Every number in this report is a point estimate selected by combo-max over hundreds of
> candidates with **no CIs, no p-values, no multiplicity correction, and no calendar-time
> control**; the base outcome swings ~5.2pp across calendar years and 16% of fires land in
> 2022 alone. `research/species/s7_rs_repair_phase0/SPEC.md` rules the tuned outputs
> test-leaked and forbids citing them; the load-bearing verdicts (PR #1207) were
> re-adjudicated by the time-controlled S7 re-run. See
> `research/TIME_CONFOUND_EXPOSURE_AUDIT.md` §3.6.

## Executive summary

Ran the requested completed-candle base trigger on `data/baskets/ohlcv`: weekly price MACD bullish crossover aligned within 10 trading days of a completed 2W StochRSI bullish crossover from oversold, with a 20D per-ticker cooldown.

Baseline sample: **14544** signals. Median forward returns were 5D 0.3%, 10D 0.5%, 20D 0.8%, and 30D 0.8%. The 20D entry-stop failure rate was 56.0%; 60D durable-bottom rate was 60.6%.

Best scored candidate with at least 50 fires: **candidate_1_cohort_rs_antichase** (315 signals), median 20D 2.2%, 20D MFE/MAE 1.79, stopout 32.1%, durable 60D 64.1%.

## Baseline signal results

|   sample_size |   median_5D |   median_10D |   median_20D |   median_30D |   win_rate_20D |   median_MFE_20D |   median_MAE_20D |   MFE_MAE_ratio_20D |   stopout_rate_5pct |   new_low_rate_60D |   durable_bottom_60D |   median_distance_from_60D_low |
|--------------:|------------:|-------------:|-------------:|-------------:|---------------:|-----------------:|-----------------:|--------------------:|--------------------:|-------------------:|---------------------:|-------------------------------:|
|         14544 |   0.0029308 |   0.00511191 |   0.00781598 |   0.00777607 |       0.533003 |          0.06779 |       -0.0585658 |              1.1575 |            0.559543 |            0.52984 |             0.606298 |                       0.176908 |

## Best individual filters

| signal_name          |   sample_size |   median_10D |   median_20D |   MFE_MAE_ratio_20D |   stopout_rate_5pct |   new_low_rate_60D |   durable_bottom_60D |   bounce_quality_score |
|:---------------------|--------------:|-------------:|-------------:|--------------------:|--------------------:|-------------------:|---------------------:|-----------------------:|
| cohort_sector_50     |          1203 |   0.0158924  |   0.0185345  |             1.64745 |            0.365752 |           0.472153 |             0.66916  |                76.8763 |
| rs_sector_higher_low |          1743 |   0.0116089  |   0.0207303  |             1.58406 |            0.380952 |           0.475043 |             0.698221 |                74.3936 |
| cohort_sector_25     |          2480 |   0.012841   |   0.0195136  |             1.58709 |            0.372177 |           0.478629 |             0.667742 |                73.5537 |
| cohort_sector_40     |          1652 |   0.0127815  |   0.0174072  |             1.55121 |            0.381356 |           0.485472 |             0.651332 |                71.1254 |
| cohort_industry_40   |          1643 |   0.0123667  |   0.0170389  |             1.53902 |            0.371272 |           0.491783 |             0.664638 |                70.4828 |
| rs_sector_20d_pos    |          2466 |   0.0105238  |   0.0183305  |             1.46256 |            0.391322 |           0.47283  |             0.695053 |                69.2156 |
| near_rising_200w     |          1406 |   0.00752284 |   0.0135675  |             1.31708 |            0.48862  |           0.532006 |             0.651494 |                55.3587 |
| rs_spy_50d_pos       |          7541 |   0.00758968 |   0.0118167  |             1.22976 |            0.532158 |           0.435884 |             0.687044 |                52.5728 |
| monthly_hist_rising  |          3494 |   0.00834251 |   0.00758347 |             1.23026 |            0.552089 |           0.511734 |             0.623641 |                46.2724 |
| near_60d_low_15      |          5652 |   0.00620743 |   0.00876531 |             1.25608 |            0.455237 |           0.631458 |             0.567056 |                46.0496 |

## Best combinations

| signal_name                     |   sample_size |   median_10D |   median_20D |   MFE_MAE_ratio_20D |   stopout_rate_5pct |   new_low_rate_60D |   durable_bottom_60D |   bounce_quality_score |
|:--------------------------------|--------------:|-------------:|-------------:|--------------------:|--------------------:|-------------------:|---------------------:|-----------------------:|
| candidate_1_cohort_rs_antichase |           315 |   0.0166705  |   0.0221964  |             1.79479 |            0.320635 |           0.590476 |             0.64127  |                82.1071 |
| cohort+anti_chase               |           470 |   0.0146586  |   0.0165285  |             1.7121  |            0.334043 |           0.619149 |             0.606383 |                72.4473 |
| cohort+rs                       |          1425 |   0.0126327  |   0.0175066  |             1.54872 |            0.384561 |           0.461053 |             0.670175 |                71.4235 |
| production_score_65_proxy       |           929 |   0.0108242  |   0.0163057  |             1.56047 |            0.337998 |           0.538213 |             0.667384 |                69.4845 |
| candidate_3_monthly_cohort      |           148 |   0.0112185  |   0.00713137 |             1.69327 |            0.344595 |           0.594595 |             0.608108 |                64.7091 |
| strict_quality_stack            |            74 |   0.0191734  |   0.00569829 |             1.37014 |            0.378378 |           0.567568 |             0.648649 |                61.2515 |
| candidate_5_clean_compounder    |            60 |   0.0107422  |   0.0141719  |             1.28442 |            0.483333 |           0.566667 |             0.583333 |                58.453  |
| candidate_4_volume_reclaim      |            46 |  -0.00451073 |   0.021143   |             1.1961  |            0.695652 |           0.391304 |             0.695652 |                46.6348 |
| rs+anti_chase                   |          2491 |   0.00446842 |   0.00813702 |             1.21212 |            0.426335 |           0.635086 |             0.586511 |                44.7077 |
| failed_reclaim+rs               |           602 |   0.00148354 |   0.0167754  |             1.09719 |            0.666113 |           0.456811 |             0.66113  |                41.7542 |

## Why the winners work

The highest-ranked filters generally improved the signal by enforcing one of three things: entry proximity to the washout low, evidence that relative strength had stopped deteriorating, or broader cohort/market confirmation. The important read is the tradeoff between better MFE/MAE and smaller sample size; tiny ultra-strict stacks are not treated as production winners.

## Filters that failed validation

Filters that only reduced signal count without improving stop-out, new-low, or MFE/MAE were left below the top table. Sector/cohort and sector-RS filters also lose breadth because only mapped tickers can use them; those rows need PIT sector validation before production.

## Robustness

Static split, rolling 3Y/1Y/1Y, yearly, sector, and regime-style SPY 200D fields are written to CSV. The available price panel begins in 2014, so the requested 2010-2017 train window is implemented as 2014-2017.

## Recommended production signal design

Base trigger required:
- completed 1W price MACD bullish crossover
- completed 2W StochRSI bullish crossover with recent sub-20 oversold state

Score the surviving base fires as:
- Sector/cohort washout: 25 points
- Relative strength inflection: 20 points
- Anti-chase/asymmetric entry: 20 points
- Structure/divergence/reclaim: 15 points
- Volume capitulation/accumulation: 10 points
- Monthly freshness/context: 10 points

Hard veto candidates:
- signal more than 15% above the 60D low
- monthly StochRSI oversold dwell >= 6 bars
- stock/SPY and stock/sector relative strength both still falling
- sector ETF still making fresh 60D lows
- fundamental deterioration once PIT fundamentals are available

Classify: 80-100 A+ bottom/bounce signal; 65-79 high-quality bounce candidate; 50-64 early turn, wait for retest; below 50 bounce risk / avoid.

## Data and bias controls

- Completed weekly/2W candles are mapped to the first tradable day after the known close.
- Same-ticker repeat signals are suppressed for 20 trading days.
- Forward return/MFE/MAE/stop metrics are calculated only after the entry date.
- Current/static sector maps are not point-in-time; production should replace them with PIT classifications.
- Survivorship bias remains possible in the active OHLCV panel; delisted coverage should be added before treating absolute rates as final.

## Missing data hooks

- Point-in-time fundamentals were not available in this repo slice, so fundamental survivability vetoes were not scored.
- Options/GEX history was not available as a broad point-in-time panel, so options confirmation was not scored.
- Sector classifications are current/static where available, not point-in-time; sector/cohort filters are therefore evidence, not production-ready PIT proof.

## Output files

- `base_signal.csv`
- `single_factor_results.csv`
- `combo_results.csv`
- `top_5_combinations.csv`
- `all_signal_results.csv`
- `all_base_events.csv` and `all_variant_events.csv`
- `static_split_results.csv`, `rolling_split_results.csv`, `year_stability.csv`, `sector_stability.csv`
- charts in `../charts/`

Dropped/skipped tickers: 100.
