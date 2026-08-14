# NVDA — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | operator core |
| price plane | `stocks_tr_v1` |
| first print | 1999-01-22 |
| last print | 2026-08-13 |
| sessions | 6932 |
| `open` available | False |
| sector stratum | Information Technology |
| cap stratum | adv3 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol2 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 1999-01-22 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0010 | 0.6 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0719 | 47.4 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0481 | 38.0 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.4268 | 49.0 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.4834 | 48.0 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.6111 | 59.1 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.9484 | 82.5 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0556 | 58.8 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.1138 | 95.8 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0260 | 35.8 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.1780 | 56.2 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.6667 | 88.4 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.3333 | 64.1 | yes |  |
| `f2_time_under_water_median_756` | F2 | 3.0000 | 7.3 | yes |  |
| `f2_ulcer_126` | F2 | 11.2775 | 33.0 | yes |  |
| `f2_ulcer_252` | F2 | 10.0029 | 19.6 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 6.4028 | 86.4 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 18.5000 | 30.0 | yes |  |
| `f4_ar1_daily_252` | F4 | -0.0346 | 48.5 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.1140 | 16.2 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 0.8845 | 22.1 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.7362 | 20.3 | yes |  |
| `f4_mr_half_life_252` | F4 | 17.0009 | 13.8 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 2.0000 | 15.2 | yes |  |
| `f5_realized_vol_21` | F5 | 38.7383 | 39.1 | yes |  |
| `f5_realized_vol_63` | F5 | 41.0437 | 41.3 | yes |  |
| `f5_realized_vol_252` | F5 | 36.6491 | 35.2 | yes |  |
| `f5_vol_of_vol_252` | F5 | 6.3068 | 17.8 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.0283 | 28.7 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 0.6496 | 27.2 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.2597 | 53.4 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 0.6477 | 57.1 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 3.9757 | 78.8 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.1349 | 97.6 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0159 | 31.6 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 8.5556 | 15.1 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 79.6667 | 77.9 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.5200 | 51.7 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.1867 | 29.5 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 1.6134 | 16.6 | yes |  |
| `f8_swing_period_median_756` | F8 | 31.5000 | 44.0 | yes |  |
| `f8_swing_period_median_1260` | F8 | 31.5000 | 44.5 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 0.7246 | 36.5 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 0.8918 | 43.6 | yes |  |
| `f9_idio_share_252` | F9 | 0.8735 | 49.9 | yes |  |
| `f9_idio_share_756` | F9 | 0.8474 | 55.9 | yes |  |
| `f10_dollar_adv_63` | F10 | 2.919e+10 | 100.0 | yes |  |
| `f10_dollar_adv_252` | F10 | 3.078e+10 | 100.0 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.7242 | 13.2 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 0.0 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0065 | 24.7 | yes |  |

### Diagnostic block

Census and baseline use only — never a distance input, never a map input.

| feature | raw | universe pct | covered |
|---|---:|---:|:--:|
| `d_sector` | — | — | no |
| `d_industry` | UNKNOWN | — | yes |
| `d_cap_bucket` | — | — | no |
| `d_market_cap_b` | — | — | no |
| `d_price_plane_id` | stocks_tr_v1 | — | yes |
| `d_listing_venue_class` | — | — | no |
| `d_f6_gap_share_252` | — | — | no |
| `d_f6_event_gap_contrib_252` | — | — | no |
| `d_f6_gap_fill_rate_252` | — | — | no |
| `d_close_jump_freq_252` | 0.0317 | 68.3 | yes |
| `d_close_jump_drift5_252` | -0.4255 | 18.2 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 1999-04-23 | 1999-04-26 | 1999-04-27 | 8.4 | 1.23 | 2 | recovered | no |
| reset_decline | 3 | 1999-08-31 | 1999-09-24 | 1999-09-24 | 35.6 | 6.52 | 17 | durable_low | no |
| reset_decline | 3 | 2000-03-13 | 2000-04-14 | 2000-04-14 | 53.9 | 8.13 | 24 | durable_low | no |
| reset_decline | 3 | 2000-06-21 | 2000-07-27 | 2000-07-27 | 39.0 | 5.93 | 25 | durable_low | no |
| failed_breakdown | 3 | 2000-10-30 | 2000-10-30 | 2000-10-31 | 1.9 | 0.18 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-11-22 | 2000-11-22 | 2000-11-24 | 4.5 | 0.37 | 1 | recovered | no |
| reset_decline | 1 | 2001-06-07 | 2001-10-02 | 2001-10-02 | 51.9 | 9.39 | 77 | durable_low | no |
| failed_breakdown | 3 | 2001-07-23 | 2001-07-23 | 2001-07-26 | 8.1 | 1.21 | 3 | recovered | no |
| reset_decline | 1 | 2002-01-03 | 2002-10-09 | 2002-10-09 | 89.7 | 22.26 | 193 | durable_low | no |
| failed_breakdown | 3 | 2002-02-22 | 2002-02-22 | 2002-02-25 | 2.8 | 0.40 | 1 | recovered | no |
| failed_breakdown | 3 | 2002-04-05 | 2002-04-05 | 2002-04-08 | 0.9 | 0.13 | 1 | recovered | no |
| failed_breakdown | 3 | 2002-04-24 | 2002-04-26 | 2002-05-08 | 14.7 | 1.96 | 10 | recovered | no |
| failed_breakdown | 3 | 2002-07-23 | 2002-07-23 | 2002-07-24 | 0.4 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2002-07-25 | 2002-07-26 | 2002-07-30 | 8.1 | 0.66 | 3 | recovered | no |
| failed_breakdown | 3 | 2002-09-27 | 2002-09-27 | 2002-10-01 | 0.5 | 0.05 | 2 | recovered | no |
| failed_breakdown | 3 | 2002-10-04 | 2002-10-09 | 2002-10-11 | 13.9 | 1.54 | 5 | recovered | no |
| failed_breakdown | 3 | 2003-01-24 | 2003-01-27 | 2003-01-29 | 4.4 | 0.59 | 3 | recovered | no |
| failed_breakdown | 3 | 2003-02-07 | 2003-02-11 | 2003-02-14 | 3.2 | 0.44 | 5 | recovered | no |
| reset_decline | 2 | 2003-06-05 | 2003-08-08 | 2003-08-08 | 41.7 | 8.42 | 45 | durable_low | no |
| reset_decline | 1 | 2004-01-12 | 2004-08-06 | 2004-08-06 | 63.4 | 18.52 | 143 | durable_low | no |
| failed_breakdown | 3 | 2004-04-30 | 2004-05-03 | 2004-05-04 | 2.4 | 0.51 | 2 | recovered | no |
| failed_breakdown | 3 | 2004-06-14 | 2004-06-14 | 2004-06-15 | 0.5 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2004-06-16 | 2004-06-21 | 2004-06-23 | 3.7 | 0.86 | 5 | recovered | no |
| failed_breakdown | 3 | 2004-07-21 | 2004-07-26 | 2004-07-29 | 6.4 | 1.27 | 6 | recovered | no |
| reclaim | 3 | 2004-10-05 | 2004-11-17 | 2005-02-17 | 44.2 | 17.54 | 31 | held | no |
| reset_decline | 3 | 2005-02-28 | 2005-04-18 | 2005-04-18 | 26.9 | 7.09 | 34 | durable_low | no |
| reset_decline | 2 | 2006-05-05 | 2006-07-14 | 2006-07-14 | 43.5 | 12.16 | 48 | durable_low | no |
| failed_breakdown | 3 | 2006-05-30 | 2006-05-30 | 2006-06-01 | 3.1 | 0.61 | 2 | recovered | no |
| failed_breakdown | 3 | 2006-06-27 | 2006-06-27 | 2006-06-28 | 1.9 | 0.38 | 1 | recovered | no |
| failed_breakdown | 3 | 2006-07-07 | 2006-07-14 | 2006-07-19 | 9.3 | 1.74 | 8 | recovered | no |
| reset_decline | 2 | 2006-12-19 | 2007-03-16 | 2007-03-16 | 26.7 | 8.94 | 58 | durable_low | no |
| failed_breakdown | 3 | 2007-01-26 | 2007-01-29 | 2007-02-02 | 4.8 | 1.10 | 5 | recovered | no |
| failed_breakdown | 3 | 2007-03-02 | 2007-03-05 | 2007-03-06 | 4.7 | 1.27 | 2 | recovered | no |
| failed_breakdown | 3 | 2007-03-15 | 2007-03-16 | 2007-03-21 | 1.4 | 0.35 | 4 | recovered | no |
| reset_decline | 1 | 2007-10-17 | 2008-03-19 | 2008-03-19 | 55.3 | 16.98 | 105 | durable_low | no |
| failed_breakdown | 3 | 2007-11-21 | 2007-11-21 | 2007-11-23 | 1.1 | 0.16 | 1 | recovered | no |
| failed_breakdown | 3 | 2007-11-26 | 2007-11-26 | 2007-11-27 | 0.6 | 0.10 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-03-19 | 2008-03-19 | 2008-03-20 | 1.1 | 0.16 | 1 | recovered | no |
| reclaim | 1 | 2008-05-12 | 2009-04-01 | 2009-05-08 | 44.6 | 17.87 | 224 | failed | no |
| failed_breakdown | 3 | 2008-07-24 | 2008-07-24 | 2008-07-25 | 1.0 | 0.13 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-08-01 | 2008-08-04 | 2008-08-05 | 4.1 | 0.60 | 2 | recovered | no |
| failed_breakdown | 3 | 2008-09-11 | 2008-09-15 | 2008-09-18 | 12.1 | 2.02 | 5 | recovered | no |
| failed_breakdown | 3 | 2008-10-23 | 2008-10-23 | 2008-10-27 | 4.0 | 0.33 | 2 | recovered | no |
| failed_breakdown | 3 | 2008-11-19 | 2008-11-20 | 2008-11-24 | 9.8 | 0.82 | 3 | recovered | no |
| reset_decline | 3 | 2009-05-04 | 2009-05-13 | 2009-05-13 | 31.7 | 5.95 | 7 | durable_low | no |
| reset_decline | 2 | 2009-09-10 | 2009-10-30 | 2009-10-30 | 27.4 | 8.00 | 36 | durable_low | no |
| failed_breakdown | 3 | 2009-10-27 | 2009-10-30 | 2009-11-06 | 7.0 | 1.71 | 8 | recovered | no |
| reset_decline | 3 | 2010-01-06 | 2010-01-29 | 2010-01-29 | 18.5 | 6.21 | 16 | durable_low | no |
| failed_breakdown | 3 | 2010-05-18 | 2010-05-24 | 2010-05-27 | 4.6 | 0.78 | 7 | recovered | no |
| failed_breakdown | 3 | 2010-06-29 | 2010-07-06 | 2010-07-13 | 7.1 | 1.39 | 9 | recovered | no |
| failed_breakdown | 3 | 2010-07-16 | 2010-07-16 | 2010-07-19 | 0.9 | 0.18 | 1 | recovered | no |
| reclaim | 2 | 2010-09-13 | 2010-11-18 | 2011-02-18 | 44.2 | 20.54 | 48 | held | no |
| reset_decline | 1 | 2011-02-17 | 2011-08-19 | 2011-08-19 | 54.3 | 12.24 | 127 | durable_low | no |
| failed_breakdown | 3 | 2011-04-11 | 2011-04-11 | 2011-04-13 | 0.7 | 0.15 | 2 | recovered | no |
| failed_breakdown | 3 | 2011-06-27 | 2011-06-27 | 2011-06-29 | 1.3 | 0.31 | 2 | recovered | no |
| failed_breakdown | 3 | 2011-08-19 | 2011-08-19 | 2011-08-22 | 1.7 | 0.24 | 1 | recovered | no |
| reset_decline | 2 | 2012-02-16 | 2012-06-04 | 2012-06-04 | 28.7 | 9.27 | 74 | durable_low | no |
| failed_breakdown | 3 | 2012-05-03 | 2012-05-04 | 2012-05-11 | 4.4 | 1.37 | 6 | recovered | no |
| failed_breakdown | 3 | 2012-05-18 | 2012-05-18 | 2012-05-21 | 1.5 | 0.39 | 1 | recovered | no |
| failed_breakdown | 3 | 2012-06-01 | 2012-06-04 | 2012-06-06 | 2.9 | 0.78 | 3 | recovered | no |
| failed_breakdown | 3 | 2012-10-12 | 2012-10-12 | 2012-10-15 | 0.3 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 2012-10-19 | 2012-10-22 | 2012-11-05 | 5.2 | 1.92 | 9 | recovered | no |
| failed_breakdown | 3 | 2012-11-12 | 2012-11-16 | 2012-11-23 | 4.9 | 1.41 | 8 | recovered | no |
| failed_breakdown | 3 | 2013-11-07 | 2013-11-07 | 2013-11-08 | 1.4 | 0.72 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-07-25 | 2014-07-28 | 2014-07-30 | 0.9 | 0.42 | 3 | recovered | no |
| failed_breakdown | 3 | 2014-07-31 | 2014-08-07 | 2014-08-08 | 1.5 | 0.70 | 6 | recovered | no |
| reset_decline | 3 | 2014-09-04 | 2014-10-13 | 2014-10-13 | 16.2 | 9.35 | 27 | durable_low | no |
| failed_breakdown | 3 | 2014-10-10 | 2014-10-13 | 2014-10-15 | 3.4 | 1.48 | 3 | recovered | no |
| reset_decline | 3 | 2015-03-20 | 2015-07-27 | 2015-07-27 | 17.3 | 8.33 | 88 | durable_low | no |
| failed_breakdown | 3 | 2015-05-11 | 2015-05-11 | 2015-05-12 | 1.0 | 0.32 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-07-27 | 2015-07-27 | 2015-07-28 | 0.5 | 0.20 | 1 | recovered | no |
| reset_decline | 2 | 2015-12-04 | 2016-02-08 | 2016-02-08 | 25.3 | 11.36 | 43 | durable_low | no |
| failed_breakdown | 3 | 2016-01-15 | 2016-01-15 | 2016-01-19 | 0.7 | 0.21 | 1 | recovered | no |
| failed_breakdown | 3 | 2016-02-05 | 2016-02-08 | 2016-02-17 | 7.0 | 1.91 | 7 | recovered | no |
| reset_decline | 3 | 2017-02-07 | 2017-04-13 | 2017-04-13 | 19.7 | 6.68 | 46 | durable_low | no |
| failed_breakdown | 3 | 2017-04-12 | 2017-04-13 | 2017-04-17 | 2.2 | 0.72 | 2 | recovered | no |
| reset_decline | 2 | 2018-10-01 | 2018-12-24 | 2018-12-24 | 56.0 | 23.72 | 58 | durable_low | no |
| failed_breakdown | 3 | 2018-10-11 | 2018-10-11 | 2018-10-12 | 3.6 | 1.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-12-17 | 2018-12-17 | 2018-12-18 | 0.7 | 0.09 | 1 | recovered | no |
| reclaim | 1 | 2019-03-11 | 2019-07-22 | 2019-08-01 | 44.2 | 23.23 | 92 | failed | no |
| reset_decline | 3 | 2020-02-19 | 2020-03-16 | 2020-03-16 | 37.6 | 14.49 | 18 | durable_low | no |
| failed_breakdown | 3 | 2020-03-12 | 2020-03-12 | 2020-03-13 | 3.4 | 0.48 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-03-16 | 2020-03-16 | 2020-03-17 | 9.2 | 1.14 | 1 | recovered | no |
| reset_decline | 3 | 2020-09-02 | 2020-09-08 | 2020-09-08 | 17.0 | 5.89 | 3 | durable_low | no |
| reset_decline | 3 | 2021-02-16 | 2021-03-08 | 2021-03-08 | 24.4 | 8.26 | 14 | durable_low | no |
| failed_breakdown | 3 | 2021-03-04 | 2021-03-08 | 2021-03-11 | 8.1 | 1.81 | 5 | recovered | no |
| reset_decline | 1 | 2021-11-29 | 2022-07-01 | 2022-07-01 | 56.5 | 12.51 | 148 | durable_low | no |
| failed_breakdown | 3 | 2022-01-21 | 2022-01-27 | 2022-01-31 | 9.1 | 1.52 | 6 | recovered | no |
| failed_breakdown | 3 | 2022-03-07 | 2022-03-07 | 2022-03-09 | 2.7 | 0.41 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-03-14 | 2022-03-14 | 2022-03-15 | 0.1 | 0.02 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-04-14 | 2022-04-14 | 2022-04-18 | 0.3 | 0.05 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-05-24 | 2022-05-24 | 2022-05-25 | 0.1 | 0.02 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-06-13 | 2022-06-13 | 2022-06-15 | 3.1 | 0.45 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-06-16 | 2022-06-16 | 2022-06-17 | 0.3 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-06-29 | 2022-07-01 | 2022-07-07 | 6.9 | 1.07 | 5 | recovered | no |
| failed_breakdown | 3 | 2022-09-22 | 2022-09-30 | 2022-10-04 | 6.1 | 1.11 | 8 | recovered | no |
| failed_breakdown | 3 | 2022-10-07 | 2022-10-14 | 2022-10-20 | 7.5 | 1.41 | 9 | recovered | no |
| failed_breakdown | 3 | 2023-10-26 | 2023-10-26 | 2023-10-30 | 1.3 | 0.32 | 2 | recovered | no |
| reset_decline | 3 | 2024-06-18 | 2024-08-07 | 2024-08-07 | 27.0 | 7.87 | 34 | durable_low | no |
| reset_decline | 2 | 2025-01-06 | 2025-04-04 | 2025-04-04 | 36.9 | 10.71 | 61 | durable_low | no |
| failed_breakdown | 3 | 2025-01-27 | 2025-01-27 | 2025-01-28 | 8.1 | 1.82 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-02-03 | 2025-02-03 | 2025-02-04 | 1.5 | 0.23 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-03-03 | 2025-03-03 | 2025-03-05 | 2.2 | 0.37 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-03-06 | 2025-03-10 | 2025-03-12 | 6.2 | 0.98 | 4 | recovered | no |
| failed_breakdown | 3 | 2025-04-03 | 2025-04-04 | 2025-04-09 | 11.8 | 2.28 | 4 | recovered | no |
| reclaim | 3 | 2025-04-21 | 2025-05-13 | 2025-08-13 | 35.1 | 6.90 | 16 | held | no |
| reset_decline | 3 | 2025-10-29 | 2025-12-17 | 2025-12-17 | 17.4 | 6.14 | 34 | durable_low | no |
| failed_breakdown | 3 | 2025-12-12 | 2025-12-12 | 2025-12-15 | 0.7 | 0.19 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-12-17 | 2025-12-17 | 2025-12-19 | 2.3 | 0.67 | 2 | recovered | no |
| failed_breakdown | 3 | 2026-03-26 | 2026-03-30 | 2026-03-31 | 3.9 | 1.21 | 3 | recovered | no |
| reset_decline | 3 | 2026-05-14 | — | 2026-08-13 | 19.3 | 6.58 | 62 | censored | yes |
| failed_breakdown | 3 | 2026-07-29 | 2026-07-29 | 2026-07-30 | 1.3 | 0.33 | 1 | recovered | no |

**112 episodes**, 1 censored; by type {'failed_breakdown': 78, 'reset_decline': 29, 'reclaim': 5}; by tier {3: 95, 2: 9, 1: 8}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `close_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1999 | 4% | 0% | 0% | 0% | 0% | 0% | 0% | 96% |
| 2000 | 7% | 12% | 0% | 58% | 12% | 2% | 0% | 9% |
| 2001 | 0% | 10% | 0% | 69% | 2% | 0% | 0% | 19% |
| 2002 | 6% | 66% | 0% | 21% | 0% | 0% | 0% | 7% |
| 2003 | 10% | 33% | 0% | 39% | 12% | 0% | 2% | 5% |
| 2004 | 4% | 23% | 4% | 12% | 35% | 7% | 0% | 15% |
| 2005 | 4% | 0% | 0% | 31% | 20% | 45% | 0% | 0% |
| 2006 | 2% | 0% | 0% | 0% | 25% | 59% | 0% | 13% |
| 2007 | 10% | 0% | 0% | 0% | 54% | 31% | 0% | 5% |
| 2008 | 4% | 72% | 2% | 0% | 1% | 0% | 2% | 20% |
| 2009 | 4% | 46% | 0% | 47% | 0% | 2% | 0% | 0% |
| 2010 | 2% | 16% | 12% | 13% | 28% | 5% | 4% | 21% |
| 2011 | 10% | 21% | 0% | 15% | 22% | 0% | 7% | 25% |
| 2012 | 0% | 2% | 0% | 14% | 8% | 0% | 6% | 70% |
| 2013 | 2% | 0% | 0% | 0% | 13% | 62% | 0% | 23% |
| 2014 | 6% | 0% | 0% | 0% | 15% | 77% | 2% | 0% |
| 2015 | 12% | 0% | 0% | 0% | 20% | 56% | 3% | 9% |
| 2016 | 12% | 0% | 0% | 0% | 16% | 72% | 0% | 0% |
| 2017 | 16% | 0% | 0% | 0% | 40% | 44% | 0% | 0% |
| 2018 | 8% | 8% | 1% | 0% | 24% | 50% | 6% | 2% |
| 2019 | 2% | 31% | 1% | 40% | 0% | 0% | 6% | 19% |
| 2020 | 7% | 0% | 0% | 12% | 40% | 41% | 0% | 0% |
| 2021 | 8% | 0% | 0% | 0% | 40% | 52% | 0% | 0% |
| 2022 | 2% | 55% | 0% | 1% | 22% | 0% | 0% | 19% |
| 2023 | 6% | 2% | 0% | 45% | 24% | 21% | 0% | 1% |
| 2024 | 8% | 0% | 0% | 0% | 42% | 50% | 0% | 0% |
| 2025 | 4% | 0% | 2% | 44% | 25% | 7% | 3% | 15% |
| 2026 | 3% | 0% | 0% | 0% | 70% | 18% | 0% | 8% |

## Episode map

![NVDA episode map](NVDA.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
