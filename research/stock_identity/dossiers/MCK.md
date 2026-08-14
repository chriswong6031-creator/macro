# MCK — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | operator core |
| price plane | `stocks_tr_v1` |
| first print | 1994-11-10 |
| last print | 2026-08-13 |
| sessions | 7991 |
| `open` available | False |
| sector stratum | Health Care |
| cap stratum | adv3 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol1 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 1994-11-10 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.1582 | 63.0 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0670 | 44.5 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0763 | 58.8 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.3078 | 38.0 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.1316 | 20.3 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.5159 | 37.8 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.7817 | 64.1 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0992 | 80.7 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.1230 | 97.1 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0212 | 25.7 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.0698 | 11.8 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 0.3333 | 26.3 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 6.0000 | 55.4 | yes |  |
| `f2_ulcer_126` | F2 | 17.1370 | 49.3 | yes |  |
| `f2_ulcer_252` | F2 | 12.7131 | 27.4 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 4.4505 | 54.0 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 24.0000 | 51.6 | yes |  |
| `f4_ar1_daily_252` | F4 | -0.0448 | 42.7 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.1437 | 9.9 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 0.9322 | 41.2 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8459 | 44.5 | yes |  |
| `f4_mr_half_life_252` | F4 | 21.1256 | 22.0 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 2.8182 | 38.6 | yes |  |
| `f5_realized_vol_21` | F5 | 39.6371 | 40.3 | yes |  |
| `f5_realized_vol_63` | F5 | 30.6298 | 23.8 | yes |  |
| `f5_realized_vol_252` | F5 | 30.2575 | 23.3 | yes |  |
| `f5_vol_of_vol_252` | F5 | 11.1484 | 40.8 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.0762 | 51.5 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 0.4740 | 13.4 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.3295 | 60.6 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 0.5360 | 52.8 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 3.0448 | 68.9 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0833 | 65.9 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0238 | 44.2 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 11.8182 | 34.3 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 49.2500 | 66.0 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.7692 | 95.6 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.2846 | 61.5 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 399.0000 | 70.6 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.3311 | 57.3 | yes |  |
| `f8_swing_period_median_756` | F8 | 138.5000 | 95.4 | yes |  |
| `f8_swing_period_median_1260` | F8 | 200.5000 | 99.6 | yes |  |
| `f9_beta_univ_ew_252` | F9 | -0.1536 | 1.0 | yes |  |
| `f9_beta_univ_ew_756` | F9 | -0.0820 | 0.1 | yes |  |
| `f9_idio_share_252` | F9 | 0.9917 | 94.3 | yes |  |
| `f9_idio_share_756` | F9 | 0.9958 | 99.3 | yes |  |
| `f10_dollar_adv_63` | F10 | 8.569e+08 | 95.4 | yes |  |
| `f10_dollar_adv_252` | F10 | 6.225e+08 | 94.2 | yes |  |
| `f10_turnover_proxy_252` | F10 | 1.1887 | 70.4 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 3.7 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0051 | 7.7 | yes |  |

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
| `d_close_jump_freq_252` | 0.0278 | 51.1 | yes |
| `d_close_jump_drift5_252` | 0.7782 | 84.8 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 1996-01-25 | 1996-01-25 | 1996-01-26 | 1.1 | 0.71 | 1 | recovered | no |
| reset_decline | 2 | 1996-03-11 | 1996-05-09 | 1996-05-09 | 20.7 | 12.90 | 42 | durable_low | no |
| failed_breakdown | 3 | 1996-04-26 | 1996-04-26 | 1996-05-01 | 0.8 | 0.44 | 3 | recovered | no |
| failed_breakdown | 3 | 1996-07-16 | 1996-07-16 | 1996-07-19 | 1.7 | 1.08 | 3 | recovered | no |
| failed_breakdown | 3 | 1996-07-24 | 1996-07-26 | 1996-07-30 | 4.6 | 2.36 | 4 | recovered | no |
| reset_decline | 3 | 1997-12-03 | 1998-01-30 | 1998-01-30 | 15.2 | 7.43 | 39 | durable_low | no |
| failed_breakdown | 3 | 1997-12-18 | 1997-12-18 | 1997-12-19 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 1998-01-29 | 1998-01-30 | 1998-02-02 | 3.0 | 1.11 | 2 | recovered | no |
| reset_decline | 1 | 1998-07-07 | 1999-10-22 | 1999-10-22 | 78.1 | 31.11 | 328 | durable_low | no |
| failed_breakdown | 3 | 1998-08-31 | 1998-08-31 | 1998-09-01 | 1.2 | 0.34 | 1 | recovered | no |
| failed_breakdown | 3 | 1998-09-10 | 1998-09-10 | 1998-09-11 | 0.8 | 0.19 | 1 | recovered | no |
| failed_breakdown | 3 | 1998-10-22 | 1998-10-22 | 1998-10-28 | 5.4 | 0.87 | 4 | recovered | no |
| failed_breakdown | 3 | 1998-11-11 | 1998-11-11 | 1998-11-12 | 1.6 | 0.40 | 1 | recovered | no |
| failed_breakdown | 3 | 1998-11-16 | 1998-11-16 | 1998-11-17 | 0.5 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 1998-12-04 | 1998-12-07 | 1998-12-08 | 2.3 | 0.59 | 2 | recovered | no |
| failed_breakdown | 3 | 1999-02-04 | 1999-02-05 | 1999-02-09 | 5.2 | 1.17 | 3 | recovered | no |
| failed_breakdown | 3 | 1999-03-05 | 1999-03-11 | 1999-03-16 | 11.0 | 2.58 | 7 | recovered | no |
| reclaim | 1 | 1999-03-09 | 2000-07-05 | 2000-10-03 | 39.9 | 12.55 | 335 | held | no |
| failed_breakdown | 3 | 1999-07-20 | 1999-07-20 | 1999-07-21 | 0.6 | 0.14 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-03-07 | 2000-03-08 | 2000-03-09 | 0.4 | 0.08 | 2 | recovered | no |
| failed_breakdown | 3 | 2000-03-14 | 2000-03-14 | 2000-03-15 | 1.4 | 0.31 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-04-26 | 2000-04-27 | 2000-05-01 | 7.2 | 1.42 | 3 | recovered | no |
| reset_decline | 3 | 2000-10-05 | 2000-10-24 | 2000-10-24 | 23.4 | 7.35 | 13 | durable_low | no |
| reset_decline | 2 | 2000-12-29 | 2001-03-22 | 2001-03-22 | 33.1 | 10.69 | 56 | durable_low | no |
| reset_decline | 3 | 2001-07-31 | 2001-09-21 | 2001-09-21 | 17.6 | 8.00 | 33 | durable_low | no |
| failed_breakdown | 3 | 2001-09-20 | 2001-09-21 | 2001-09-26 | 5.1 | 1.54 | 4 | recovered | no |
| failed_breakdown | 3 | 2002-02-25 | 2002-02-25 | 2002-02-28 | 2.4 | 0.97 | 3 | recovered | no |
| failed_breakdown | 3 | 2002-03-01 | 2002-03-05 | 2002-03-11 | 9.1 | 3.20 | 6 | recovered | no |
| reset_decline | 2 | 2002-04-26 | 2002-07-23 | 2002-07-23 | 32.5 | 11.17 | 60 | durable_low | no |
| failed_breakdown | 3 | 2002-07-11 | 2002-07-11 | 2002-07-12 | 0.2 | 0.05 | 1 | recovered | no |
| failed_breakdown | 3 | 2002-07-19 | 2002-07-23 | 2002-07-24 | 4.7 | 0.88 | 3 | recovered | no |
| failed_breakdown | 3 | 2002-10-01 | 2002-10-07 | 2002-10-11 | 10.2 | 2.68 | 8 | recovered | no |
| reclaim | 1 | 2002-10-04 | 2003-05-02 | 2003-08-01 | 39.4 | 15.60 | 144 | held | no |
| failed_breakdown | 3 | 2003-02-13 | 2003-02-13 | 2003-02-14 | 2.5 | 0.84 | 1 | recovered | no |
| failed_breakdown | 3 | 2003-03-10 | 2003-03-14 | 2003-03-21 | 8.7 | 2.80 | 9 | recovered | no |
| reset_decline | 3 | 2003-06-17 | 2003-08-06 | 2003-08-06 | 12.8 | 5.17 | 35 | durable_low | no |
| failed_breakdown | 3 | 2003-11-21 | 2003-11-21 | 2003-11-24 | 1.0 | 0.35 | 1 | recovered | no |
| failed_breakdown | 3 | 2004-02-20 | 2004-02-27 | 2004-03-05 | 2.9 | 1.43 | 10 | recovered | no |
| reset_decline | 1 | 2004-06-17 | 2004-10-21 | 2004-10-21 | 35.7 | 20.04 | 88 | durable_low | no |
| failed_breakdown | 3 | 2004-07-09 | 2004-07-12 | 2004-07-15 | 1.5 | 0.57 | 4 | recovered | no |
| failed_breakdown | 3 | 2004-08-13 | 2004-08-13 | 2004-08-16 | 1.2 | 0.60 | 1 | recovered | no |
| failed_breakdown | 3 | 2004-10-14 | 2004-10-15 | 2004-10-18 | 0.4 | 0.15 | 2 | recovered | no |
| failed_breakdown | 3 | 2004-10-19 | 2004-10-21 | 2004-10-22 | 5.6 | 2.21 | 3 | recovered | no |
| reclaim | 3 | 2004-10-21 | 2004-12-01 | 2005-01-19 | 35.7 | 20.68 | 28 | failed | no |
| failed_breakdown | 3 | 2005-10-12 | 2005-10-13 | 2005-10-14 | 1.2 | 0.69 | 2 | recovered | no |
| reset_decline | 3 | 2006-03-01 | 2006-06-13 | 2006-06-13 | 17.7 | 12.19 | 72 | durable_low | no |
| failed_breakdown | 3 | 2006-11-01 | 2006-11-03 | 2006-11-07 | 2.7 | 1.35 | 4 | recovered | no |
| failed_breakdown | 3 | 2006-11-21 | 2006-11-21 | 2006-11-22 | 1.1 | 0.46 | 1 | recovered | no |
| reset_decline | 3 | 2007-06-01 | 2007-09-17 | 2007-09-17 | 15.6 | 12.08 | 74 | durable_low | no |
| failed_breakdown | 3 | 2007-07-10 | 2007-07-10 | 2007-07-11 | 0.1 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2007-07-26 | 2007-07-27 | 2007-08-01 | 3.6 | 2.02 | 4 | recovered | no |
| failed_breakdown | 3 | 2007-09-06 | 2007-09-17 | 2007-09-18 | 4.0 | 1.45 | 8 | recovered | no |
| reset_decline | 2 | 2008-01-16 | 2008-03-28 | 2008-03-28 | 23.9 | 10.71 | 49 | durable_low | no |
| failed_breakdown | 3 | 2008-03-25 | 2008-03-25 | 2008-03-26 | 0.4 | 0.14 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-03-28 | 2008-03-28 | 2008-03-31 | 0.3 | 0.12 | 1 | recovered | no |
| reset_decline | 2 | 2008-08-28 | 2008-11-20 | 2008-11-20 | 51.4 | 22.23 | 59 | durable_low | no |
| failed_breakdown | 3 | 2008-09-29 | 2008-09-29 | 2008-09-30 | 2.2 | 0.54 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-10-27 | 2008-10-27 | 2008-10-28 | 5.5 | 0.70 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-10-29 | 2008-10-29 | 2008-11-04 | 3.4 | 0.41 | 4 | recovered | no |
| failed_breakdown | 3 | 2008-11-12 | 2008-11-12 | 2008-11-13 | 4.4 | 0.64 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-11-17 | 2008-11-20 | 2008-11-26 | 16.0 | 2.24 | 7 | recovered | no |
| failed_breakdown | 3 | 2009-03-11 | 2009-03-11 | 2009-03-13 | 2.3 | 0.46 | 2 | recovered | no |
| failed_breakdown | 3 | 2009-04-01 | 2009-04-01 | 2009-04-02 | 0.2 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2009-04-03 | 2009-04-07 | 2009-04-09 | 2.4 | 0.55 | 4 | recovered | no |
| reclaim | 2 | 2009-04-03 | 2009-06-05 | 2009-09-03 | 42.0 | 15.97 | 43 | held | no |
| failed_breakdown | 3 | 2010-01-29 | 2010-01-29 | 2010-02-01 | 1.0 | 0.42 | 1 | recovered | no |
| failed_breakdown | 3 | 2010-02-04 | 2010-02-05 | 2010-02-11 | 0.9 | 0.39 | 5 | recovered | no |
| reset_decline | 3 | 2010-06-17 | 2010-08-31 | 2010-08-31 | 18.1 | 8.12 | 52 | durable_low | no |
| reset_decline | 3 | 2011-05-18 | 2011-10-04 | 2011-10-04 | 19.8 | 13.17 | 96 | durable_low | no |
| failed_breakdown | 3 | 2011-10-03 | 2011-10-04 | 2011-10-10 | 1.9 | 0.61 | 5 | recovered | no |
| failed_breakdown | 3 | 2012-08-17 | 2012-08-17 | 2012-08-20 | 0.0 | 0.02 | 1 | recovered | no |
| failed_breakdown | 3 | 2012-08-22 | 2012-08-22 | 2012-08-23 | 0.2 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2012-09-19 | 2012-09-19 | 2012-09-20 | 0.7 | 0.48 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-04-11 | 2014-04-11 | 2014-04-14 | 1.4 | 0.62 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-15 | 2014-10-15 | 2014-10-17 | 0.7 | 0.36 | 2 | recovered | no |
| reset_decline | 2 | 2015-05-18 | 2015-10-30 | 2015-10-30 | 26.2 | 16.54 | 116 | durable_low | no |
| failed_breakdown | 3 | 2015-07-30 | 2015-07-30 | 2015-08-03 | 2.3 | 1.52 | 2 | recovered | no |
| failed_breakdown | 3 | 2015-09-28 | 2015-09-28 | 2015-10-05 | 2.1 | 0.70 | 5 | recovered | no |
| failed_breakdown | 3 | 2015-10-06 | 2015-10-06 | 2015-10-07 | 0.1 | 0.05 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-10-22 | 2015-10-22 | 2015-10-23 | 1.4 | 0.54 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-10-30 | 2015-10-30 | 2015-11-03 | 1.5 | 0.40 | 2 | recovered | no |
| reclaim | 2 | 2016-02-23 | 2016-05-24 | 2016-06-27 | 36.3 | 18.01 | 64 | failed | no |
| reset_decline | 1 | 2016-07-20 | 2016-10-28 | 2016-10-28 | 37.4 | 21.77 | 71 | durable_low | no |
| failed_breakdown | 3 | 2016-09-29 | 2016-09-29 | 2016-09-30 | 0.2 | 0.12 | 1 | recovered | no |
| reclaim | 2 | 2016-11-08 | 2017-05-19 | 2017-08-16 | 34.6 | 12.11 | 132 | failed | no |
| failed_breakdown | 3 | 2017-04-19 | 2017-04-19 | 2017-04-20 | 0.3 | 0.15 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-04-21 | 2017-04-21 | 2017-04-24 | 0.1 | 0.06 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-04-25 | 2017-04-25 | 2017-04-26 | 0.7 | 0.36 | 1 | recovered | no |
| reset_decline | 3 | 2017-07-17 | 2017-08-18 | 2017-08-18 | 13.2 | 8.00 | 24 | durable_low | no |
| reset_decline | 2 | 2018-01-26 | 2018-03-27 | 2018-03-27 | 21.3 | 9.79 | 41 | durable_low | no |
| failed_breakdown | 3 | 2018-08-09 | 2018-08-10 | 2018-08-13 | 0.6 | 0.25 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-10-24 | 2018-10-26 | 2018-10-30 | 3.6 | 1.33 | 4 | recovered | no |
| reset_decline | 3 | 2020-02-21 | 2020-03-23 | 2020-03-23 | 32.1 | 12.77 | 21 | durable_low | no |
| failed_breakdown | 3 | 2020-03-09 | 2020-03-09 | 2020-03-10 | 2.4 | 0.50 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-03-12 | 2020-03-12 | 2020-03-13 | 6.0 | 1.06 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-03-16 | 2020-03-16 | 2020-03-17 | 2.2 | 0.34 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-03-23 | 2020-03-23 | 2020-03-24 | 4.6 | 0.51 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-10-28 | 2020-10-29 | 2020-10-30 | 1.7 | 0.65 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-02-26 | 2021-02-26 | 2021-03-01 | 0.3 | 0.11 | 1 | recovered | no |
| reset_decline | 3 | 2022-11-03 | 2022-11-15 | 2022-11-15 | 11.0 | 4.97 | 8 | durable_low | no |
| failed_breakdown | 3 | 2023-03-15 | 2023-03-15 | 2023-03-16 | 0.0 | 0.01 | 1 | recovered | no |
| reset_decline | 2 | 2024-08-02 | 2024-09-26 | 2024-09-26 | 23.9 | 15.82 | 38 | durable_low | no |
| failed_breakdown | 3 | 2024-08-08 | 2024-08-09 | 2024-08-12 | 1.4 | 0.65 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-08-07 | 2025-08-12 | 2025-08-20 | 3.3 | 1.63 | 9 | recovered | no |
| reset_decline | 2 | 2026-03-03 | 2026-05-11 | 2026-05-11 | 27.2 | 11.72 | 48 | durable_low | no |

**105 episodes**, 0 censored; by type {'failed_breakdown': 76, 'reset_decline': 23, 'reclaim': 6}; by tier {3: 88, 2: 12, 1: 5}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `close_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1994 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 1995 | 10% | 0% | 0% | 0% | 0% | 14% | 0% | 76% |
| 1996 | 12% | 0% | 0% | 0% | 12% | 34% | 0% | 42% |
| 1997 | 16% | 0% | 0% | 0% | 10% | 74% | 0% | 0% |
| 1998 | 14% | 0% | 0% | 0% | 38% | 38% | 0% | 10% |
| 1999 | 6% | 67% | 2% | 0% | 6% | 0% | 2% | 18% |
| 2000 | 12% | 36% | 0% | 38% | 3% | 5% | 2% | 4% |
| 2001 | 6% | 0% | 0% | 0% | 45% | 35% | 6% | 8% |
| 2002 | 0% | 0% | 2% | 0% | 19% | 6% | 21% | 53% |
| 2003 | 4% | 0% | 0% | 0% | 36% | 15% | 3% | 42% |
| 2004 | 16% | 0% | 0% | 7% | 17% | 7% | 33% | 21% |
| 2005 | 6% | 0% | 0% | 25% | 9% | 59% | 0% | 2% |
| 2006 | 4% | 0% | 0% | 0% | 22% | 39% | 2% | 33% |
| 2007 | 5% | 0% | 0% | 0% | 23% | 64% | 0% | 8% |
| 2008 | 4% | 12% | 8% | 0% | 5% | 5% | 16% | 50% |
| 2009 | 6% | 0% | 2% | 33% | 0% | 23% | 0% | 35% |
| 2010 | 8% | 0% | 0% | 0% | 15% | 53% | 3% | 20% |
| 2011 | 7% | 0% | 0% | 0% | 10% | 57% | 4% | 22% |
| 2012 | 4% | 0% | 0% | 0% | 24% | 64% | 0% | 7% |
| 2013 | 6% | 0% | 0% | 0% | 2% | 92% | 0% | 0% |
| 2014 | 2% | 0% | 0% | 0% | 12% | 86% | 0% | 0% |
| 2015 | 2% | 0% | 0% | 0% | 5% | 52% | 9% | 32% |
| 2016 | 11% | 0% | 6% | 26% | 2% | 0% | 25% | 29% |
| 2017 | 6% | 0% | 0% | 0% | 35% | 4% | 18% | 37% |
| 2018 | 8% | 0% | 0% | 0% | 7% | 8% | 9% | 69% |
| 2019 | 4% | 0% | 0% | 0% | 35% | 31% | 6% | 24% |
| 2020 | 6% | 0% | 0% | 0% | 47% | 25% | 0% | 22% |
| 2021 | 4% | 0% | 0% | 0% | 9% | 87% | 0% | 0% |
| 2022 | 2% | 0% | 0% | 0% | 18% | 80% | 0% | 0% |
| 2023 | 6% | 0% | 0% | 0% | 16% | 66% | 0% | 12% |
| 2024 | 10% | 0% | 0% | 0% | 12% | 65% | 3% | 12% |
| 2025 | 6% | 0% | 0% | 0% | 17% | 77% | 0% | 0% |
| 2026 | 10% | 0% | 0% | 0% | 44% | 15% | 10% | 21% |

## Episode map

![MCK episode map](MCK.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
