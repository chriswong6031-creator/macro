# WPM — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | miner neighborhood probe |
| price plane | `stock_identity_ohlcv_v1` |
| first print | 2005-07-06 |
| last print | 2026-08-13 |
| sessions | 5310 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | adv3 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol2 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 2005-07-06 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0542 | 25.9 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0402 | 28.2 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0506 | 40.3 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.5453 | 59.5 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.2292 | 27.2 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.5714 | 50.1 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.8452 | 70.6 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.1310 | 89.5 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.1217 | 96.9 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0264 | 36.9 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.1393 | 41.1 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.3333 | 80.7 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 5.0000 | 40.0 | yes |  |
| `f2_ulcer_126` | F2 | 23.5043 | 64.1 | yes |  |
| `f2_ulcer_252` | F2 | 17.3896 | 40.7 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 6.2874 | 85.2 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 13.0000 | 10.0 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0110 | 71.9 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.1559 | 7.4 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0866 | 91.3 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.7499 | 22.8 | yes |  |
| `f4_mr_half_life_252` | F4 | 25.2110 | 28.8 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 3.0000 | 44.9 | yes |  |
| `f5_realized_vol_21` | F5 | 47.2061 | 51.8 | yes |  |
| `f5_realized_vol_63` | F5 | 50.7006 | 55.1 | yes |  |
| `f5_realized_vol_252` | F5 | 48.3603 | 52.3 | yes |  |
| `f5_vol_of_vol_252` | F5 | 13.8320 | 52.0 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.0253 | 27.4 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.4274 | 68.9 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.3795 | 65.9 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 0.7293 | 60.6 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 4.1542 | 80.5 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0476 | 19.3 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0159 | 31.6 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 20.5714 | 75.8 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 71.0000 | 75.1 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.6316 | 77.0 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.2870 | 62.0 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.4434 | 64.3 | yes |  |
| `f8_swing_period_median_756` | F8 | 20.0000 | 25.6 | yes |  |
| `f8_swing_period_median_1260` | F8 | 25.0000 | 34.5 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.0796 | 61.9 | yes | **unstable** |
| `f9_beta_univ_ew_756` | F9 | 0.5634 | 16.6 | yes | **unstable** |
| `f9_idio_share_252` | F9 | 0.8388 | 37.4 | yes | **unstable** |
| `f9_idio_share_756` | F9 | 0.9075 | 77.6 | yes | **unstable** |
| `f10_dollar_adv_63` | F10 | 2.108e+08 | 82.3 | yes |  |
| `f10_dollar_adv_252` | F10 | 2.353e+08 | 84.4 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.8683 | 29.3 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 18.5 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0069 | 29.3 | yes |  |

### Diagnostic block

Census and baseline use only — never a distance input, never a map input.

| feature | raw | universe pct | covered |
|---|---:|---:|:--:|
| `d_sector` | — | — | no |
| `d_industry` | UNKNOWN | — | yes |
| `d_cap_bucket` | — | — | no |
| `d_market_cap_b` | — | — | no |
| `d_price_plane_id` | stock_identity_ohlcv_v1 | — | yes |
| `d_listing_venue_class` | — | — | no |
| `d_f6_gap_share_252` | 0.6850 | 98.5 | yes |
| `d_f6_event_gap_contrib_252` | 0.0670 | 55.6 | yes |
| `d_f6_gap_fill_rate_252` | 0.3732 | 7.3 | yes |
| `d_close_jump_freq_252` | 0.0198 | 17.3 | yes |
| `d_close_jump_drift5_252` | -0.2635 | 25.9 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| reset_decline | 2 | 2006-04-19 | 2006-06-13 | 2006-06-13 | 41.6 | 9.70 | 38 | durable_low | no |
| failed_breakdown | 3 | 2006-06-06 | 2006-06-13 | 2006-06-15 | 13.5 | 1.77 | 7 | recovered | no |
| reset_decline | 3 | 2006-09-06 | 2006-10-03 | 2006-10-03 | 28.8 | 7.53 | 19 | durable_low | no |
| failed_breakdown | 3 | 2007-03-13 | 2007-03-13 | 2007-03-14 | 0.1 | 0.02 | 1 | recovered | no |
| reset_decline | 3 | 2007-07-19 | 2007-08-28 | 2007-08-28 | 28.2 | 8.84 | 28 | durable_low | no |
| failed_breakdown | 3 | 2007-08-28 | 2007-08-28 | 2007-08-29 | 1.3 | 0.21 | 1 | recovered | no |
| reset_decline | 3 | 2007-11-06 | 2007-12-17 | 2007-12-17 | 22.1 | 5.69 | 28 | durable_low | no |
| reset_decline | 3 | 2008-01-02 | 2008-02-05 | 2008-02-05 | 24.4 | 5.68 | 23 | durable_low | no |
| reset_decline | 3 | 2008-03-14 | 2008-04-29 | 2008-04-29 | 34.2 | 8.44 | 31 | durable_low | no |
| reclaim | 1 | 2008-09-02 | 2009-03-20 | 2009-03-30 | 44.6 | 12.84 | 138 | failed | no |
| failed_breakdown | 3 | 2008-10-22 | 2008-10-27 | 2008-11-04 | 41.8 | 2.04 | 9 | recovered | no |
| failed_breakdown | 3 | 2008-11-20 | 2008-11-20 | 2008-11-21 | 0.8 | 0.03 | 1 | recovered | no |
| reset_decline | 3 | 2009-06-04 | 2009-07-09 | 2009-07-09 | 32.1 | 6.62 | 24 | durable_low | no |
| reset_decline | 3 | 2010-01-11 | 2010-02-04 | 2010-02-04 | 22.2 | 6.25 | 17 | durable_low | no |
| failed_breakdown | 3 | 2010-02-04 | 2010-02-04 | 2010-02-05 | 1.4 | 0.26 | 1 | recovered | no |
| reset_decline | 3 | 2010-12-06 | 2011-01-25 | 2011-01-25 | 28.4 | 7.91 | 34 | durable_low | no |
| reset_decline | 2 | 2011-04-08 | 2011-06-17 | 2011-06-17 | 35.6 | 9.09 | 48 | durable_low | no |
| failed_breakdown | 3 | 2011-05-11 | 2011-05-16 | 2011-05-24 | 4.0 | 0.71 | 9 | recovered | no |
| failed_breakdown | 3 | 2011-09-23 | 2011-09-26 | 2011-09-27 | 0.4 | 0.06 | 2 | recovered | no |
| failed_breakdown | 3 | 2011-09-28 | 2011-10-04 | 2011-10-12 | 14.9 | 2.28 | 10 | recovered | no |
| reclaim | 1 | 2011-10-04 | 2012-01-27 | 2012-03-14 | 41.4 | 9.36 | 79 | failed | no |
| failed_breakdown | 3 | 2012-04-11 | 2012-04-11 | 2012-04-12 | 0.0 | 0.01 | 1 | recovered | no |
| reclaim | 1 | 2012-05-14 | 2012-08-15 | 2012-11-15 | 42.9 | 15.26 | 65 | held | no |
| reset_decline | 1 | 2012-11-01 | 2013-06-26 | 2013-06-26 | 56.3 | 19.59 | 162 | durable_low | no |
| failed_breakdown | 3 | 2012-12-05 | 2012-12-06 | 2012-12-07 | 0.7 | 0.23 | 2 | recovered | no |
| failed_breakdown | 3 | 2012-12-20 | 2012-12-21 | 2012-12-31 | 1.7 | 0.57 | 6 | recovered | no |
| failed_breakdown | 3 | 2013-01-25 | 2013-01-28 | 2013-01-29 | 1.3 | 0.48 | 2 | recovered | no |
| failed_breakdown | 3 | 2013-03-11 | 2013-03-11 | 2013-03-12 | 0.1 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2013-03-20 | 2013-03-20 | 2013-03-21 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2013-04-17 | 2013-04-17 | 2013-04-24 | 7.0 | 1.29 | 5 | recovered | no |
| failed_breakdown | 3 | 2013-05-17 | 2013-05-17 | 2013-05-20 | 1.2 | 0.24 | 1 | recovered | no |
| reclaim | 1 | 2013-07-31 | 2014-02-07 | 2014-03-26 | 43.5 | 19.58 | 132 | failed | no |
| failed_breakdown | 3 | 2013-11-01 | 2013-11-01 | 2013-11-04 | 0.1 | 0.02 | 1 | recovered | no |
| failed_breakdown | 3 | 2013-11-07 | 2013-11-12 | 2013-11-14 | 3.6 | 0.93 | 5 | recovered | no |
| failed_breakdown | 3 | 2014-05-07 | 2014-05-07 | 2014-05-08 | 0.6 | 0.24 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-05-16 | 2014-05-16 | 2014-05-19 | 1.0 | 0.41 | 1 | recovered | no |
| reset_decline | 1 | 2014-07-11 | 2014-11-05 | 2014-11-05 | 37.3 | 15.10 | 82 | durable_low | no |
| failed_breakdown | 3 | 2014-09-29 | 2014-10-07 | 2014-10-08 | 7.1 | 2.53 | 7 | recovered | no |
| failed_breakdown | 3 | 2014-10-30 | 2014-11-05 | 2014-11-13 | 10.5 | 2.72 | 10 | recovered | no |
| reclaim | 2 | 2014-11-04 | 2015-01-12 | 2015-01-29 | 37.3 | 12.52 | 46 | failed | no |
| failed_breakdown | 3 | 2015-03-06 | 2015-03-10 | 2015-03-18 | 3.6 | 0.97 | 8 | recovered | no |
| failed_breakdown | 3 | 2015-06-12 | 2015-06-12 | 2015-06-15 | 0.4 | 0.17 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-07-23 | 2015-07-23 | 2015-07-24 | 1.3 | 0.27 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-08-05 | 2015-08-05 | 2015-08-06 | 1.2 | 0.27 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-08-25 | 2015-08-26 | 2015-08-28 | 5.6 | 1.10 | 3 | recovered | no |
| failed_breakdown | 3 | 2015-09-04 | 2015-09-04 | 2015-09-08 | 1.1 | 0.19 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-09-14 | 2015-09-14 | 2015-09-15 | 2.2 | 0.40 | 1 | recovered | no |
| reclaim | 1 | 2015-10-05 | 2016-02-11 | 2016-05-12 | 42.9 | 15.49 | 89 | held | no |
| reset_decline | 1 | 2016-08-16 | 2016-12-15 | 2016-12-15 | 44.5 | 16.08 | 85 | durable_low | no |
| failed_breakdown | 3 | 2016-12-15 | 2016-12-15 | 2016-12-27 | 4.6 | 0.93 | 7 | recovered | no |
| failed_breakdown | 3 | 2017-08-14 | 2017-08-15 | 2017-08-21 | 3.3 | 1.23 | 5 | recovered | no |
| reset_decline | 2 | 2018-07-06 | 2018-09-11 | 2018-09-11 | 31.8 | 20.78 | 46 | durable_low | no |
| failed_breakdown | 3 | 2018-07-30 | 2018-07-30 | 2018-07-31 | 1.0 | 0.59 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-08-07 | 2018-08-07 | 2018-08-08 | 0.3 | 0.21 | 1 | recovered | no |
| reclaim | 2 | 2018-09-13 | 2018-12-27 | 2019-01-15 | 30.0 | 12.60 | 72 | failed | no |
| failed_breakdown | 3 | 2018-11-27 | 2018-11-27 | 2018-11-28 | 0.4 | 0.10 | 1 | recovered | no |
| reset_decline | 2 | 2019-03-27 | 2019-05-22 | 2019-05-22 | 20.8 | 9.26 | 39 | durable_low | no |
| failed_breakdown | 3 | 2019-05-02 | 2019-05-02 | 2019-05-03 | 0.6 | 0.22 | 1 | recovered | no |
| reset_decline | 3 | 2019-09-04 | 2019-10-15 | 2019-10-15 | 18.2 | 6.41 | 29 | durable_low | no |
| failed_breakdown | 3 | 2019-10-15 | 2019-10-15 | 2019-10-18 | 3.3 | 1.10 | 3 | recovered | no |
| reset_decline | 3 | 2020-02-24 | 2020-03-19 | 2020-03-19 | 28.7 | 12.78 | 18 | durable_low | no |
| failed_breakdown | 3 | 2020-03-12 | 2020-03-19 | 2020-03-24 | 12.7 | 2.68 | 8 | recovered | no |
| reset_decline | 3 | 2020-05-19 | 2020-06-05 | 2020-06-05 | 19.0 | 5.07 | 12 | durable_low | no |
| reset_decline | 1 | 2020-08-05 | 2021-03-04 | 2021-03-04 | 36.3 | 9.44 | 145 | durable_low | no |
| failed_breakdown | 3 | 2020-10-28 | 2020-10-29 | 2020-11-05 | 6.5 | 2.10 | 6 | recovered | no |
| failed_breakdown | 3 | 2021-01-27 | 2021-01-27 | 2021-01-28 | 3.0 | 0.82 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-02-26 | 2021-03-04 | 2021-03-09 | 4.5 | 1.00 | 7 | recovered | no |
| reset_decline | 2 | 2021-06-10 | 2021-10-01 | 2021-10-01 | 24.2 | 10.08 | 79 | durable_low | no |
| failed_breakdown | 3 | 2021-08-09 | 2021-08-10 | 2021-08-11 | 1.0 | 0.40 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-08-19 | 2021-08-19 | 2021-08-20 | 0.3 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-10-01 | 2021-10-01 | 2021-10-06 | 1.6 | 0.55 | 3 | recovered | no |
| failed_breakdown | 3 | 2022-01-07 | 2022-01-07 | 2022-01-10 | 0.2 | 0.07 | 1 | recovered | no |
| reset_decline | 1 | 2022-04-20 | 2022-09-26 | 2022-09-26 | 43.3 | 16.61 | 109 | durable_low | no |
| failed_breakdown | 3 | 2022-05-10 | 2022-05-18 | 2022-05-20 | 5.8 | 1.55 | 8 | recovered | no |
| failed_breakdown | 3 | 2022-06-14 | 2022-06-17 | 2022-06-21 | 1.9 | 0.50 | 4 | recovered | no |
| failed_breakdown | 3 | 2022-06-22 | 2022-06-23 | 2022-06-27 | 3.2 | 0.83 | 3 | recovered | no |
| failed_breakdown | 3 | 2022-07-20 | 2022-07-25 | 2022-07-29 | 5.9 | 1.48 | 7 | recovered | no |
| failed_breakdown | 3 | 2022-08-26 | 2022-09-01 | 2022-09-07 | 6.0 | 1.77 | 7 | recovered | no |
| reclaim | 2 | 2022-09-23 | 2022-11-30 | 2023-03-03 | 43.3 | 19.69 | 47 | held | no |
| failed_breakdown | 3 | 2022-09-26 | 2022-09-26 | 2022-09-28 | 2.3 | 0.57 | 2 | recovered | no |
| reset_decline | 3 | 2023-01-25 | 2023-03-08 | 2023-03-08 | 16.7 | 5.93 | 29 | durable_low | no |
| reset_decline | 2 | 2023-04-13 | 2023-10-04 | 2023-10-04 | 25.2 | 10.14 | 120 | durable_low | no |
| failed_breakdown | 3 | 2023-07-06 | 2023-07-06 | 2023-07-12 | 2.6 | 0.98 | 4 | recovered | no |
| failed_breakdown | 3 | 2023-08-17 | 2023-08-18 | 2023-08-22 | 1.0 | 0.36 | 3 | recovered | no |
| failed_breakdown | 3 | 2023-09-27 | 2023-10-04 | 2023-10-11 | 5.0 | 1.90 | 10 | recovered | no |
| reset_decline | 2 | 2023-12-27 | 2024-02-26 | 2024-02-26 | 22.3 | 9.12 | 40 | durable_low | no |
| reset_decline | 3 | 2024-10-22 | 2025-01-13 | 2025-01-13 | 18.4 | 8.24 | 55 | durable_low | no |
| failed_breakdown | 3 | 2025-01-13 | 2025-01-13 | 2025-01-14 | 0.6 | 0.21 | 1 | recovered | no |
| reset_decline | 3 | 2025-10-16 | 2025-11-04 | 2025-11-04 | 16.9 | 6.02 | 13 | durable_low | no |
| reset_decline | 3 | 2026-03-02 | 2026-03-20 | 2026-03-20 | 30.8 | 8.09 | 14 | durable_low | no |
| failed_breakdown | 3 | 2026-03-20 | 2026-03-20 | 2026-03-23 | 2.4 | 0.37 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-09 | 2026-06-10 | 2026-06-12 | 5.9 | 1.16 | 3 | recovered | no |
| failed_breakdown | 3 | 2026-07-16 | 2026-07-20 | 2026-07-21 | 3.8 | 0.85 | 3 | recovered | no |

**93 episodes**, 0 censored; by type {'failed_breakdown': 58, 'reset_decline': 27, 'reclaim': 8}; by tier {3: 73, 2: 10, 1: 10}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2005 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 2006 | 0% | 0% | 0% | 0% | 41% | 7% | 0% | 53% |
| 2007 | 0% | 0% | 0% | 0% | 53% | 29% | 0% | 18% |
| 2008 | 0% | 36% | 4% | 0% | 28% | 3% | 1% | 29% |
| 2009 | 0% | 39% | 0% | 61% | 0% | 0% | 0% | 0% |
| 2010 | 0% | 0% | 0% | 3% | 48% | 49% | 0% | 0% |
| 2011 | 0% | 0% | 0% | 0% | 49% | 12% | 10% | 28% |
| 2012 | 0% | 0% | 2% | 39% | 11% | 0% | 2% | 46% |
| 2013 | 0% | 19% | 17% | 0% | 13% | 0% | 10% | 41% |
| 2014 | 0% | 0% | 1% | 21% | 11% | 9% | 12% | 47% |
| 2015 | 0% | 33% | 3% | 8% | 0% | 0% | 2% | 54% |
| 2016 | 0% | 8% | 0% | 48% | 22% | 6% | 5% | 11% |
| 2017 | 0% | 0% | 0% | 0% | 20% | 6% | 7% | 67% |
| 2018 | 2% | 0% | 1% | 2% | 9% | 36% | 6% | 44% |
| 2019 | 0% | 0% | 0% | 19% | 50% | 29% | 1% | 1% |
| 2020 | 3% | 0% | 0% | 0% | 48% | 37% | 0% | 12% |
| 2021 | 2% | 0% | 0% | 0% | 42% | 0% | 3% | 52% |
| 2022 | 0% | 0% | 4% | 10% | 9% | 14% | 9% | 55% |
| 2023 | 2% | 0% | 0% | 22% | 32% | 19% | 4% | 21% |
| 2024 | 0% | 0% | 0% | 0% | 44% | 46% | 6% | 4% |
| 2025 | 0% | 0% | 0% | 0% | 23% | 73% | 1% | 3% |
| 2026 | 0% | 0% | 0% | 0% | 57% | 18% | 0% | 25% |

## Episode map

![WPM episode map](WPM.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
