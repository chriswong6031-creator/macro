# YELP — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | operator core |
| price plane | `baskets_ohlcv_v1` |
| first print | 2014-01-02 |
| last print | 2026-08-13 |
| sessions | 3172 |
| `open` available | True |
| sector stratum | Communication Services |
| cap stratum | adv2 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol2 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 2014-01-02 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0384 | 17.9 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0162 | 11.7 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0520 | 41.2 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.0740 | 16.5 | yes | **unstable** |
| `f1_logprice_r2_252` | F1 | 0.5382 | 52.6 | yes | **unstable** |
| `f1_share_above_50dma_252` | F1 | 0.3452 | 11.7 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.0198 | 2.7 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0000 | 10.9 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0079 | 11.6 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0621 | 77.1 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.0896 | 19.1 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 0.0000 | 7.7 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 15.0000 | 89.6 | yes |  |
| `f2_ulcer_126` | F2 | 23.9633 | 65.1 | yes |  |
| `f2_ulcer_252` | F2 | 31.8931 | 70.0 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 3.1867 | 27.4 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 14.0000 | 13.2 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0060 | 69.4 | yes |  |
| `f4_ar1_weekly_756` | F4 | 0.0648 | 85.6 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 0.9893 | 66.1 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8680 | 49.9 | yes |  |
| `f4_mr_half_life_252` | F4 | 30.6893 | 37.7 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 7.2500 | 95.7 | yes |  |
| `f5_realized_vol_21` | F5 | 48.2731 | 53.3 | yes |  |
| `f5_realized_vol_63` | F5 | 49.8115 | 54.0 | yes |  |
| `f5_realized_vol_252` | F5 | 42.5750 | 44.2 | yes |  |
| `f5_vol_of_vol_252` | F5 | 13.6447 | 51.2 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.0689 | 47.7 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.7813 | 78.8 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | -0.2193 | 15.2 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | -0.8365 | 13.1 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | -4.5965 | 9.6 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0714 | 50.3 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0317 | 55.0 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 9.6667 | 21.7 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 1.2500 | 2.2 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.2500 | 8.4 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.2598 | 54.4 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 3.0585 | 91.7 | yes |  |
| `f8_swing_period_median_1260` | F8 | 37.5000 | 52.6 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 0.6691 | 31.3 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 0.7251 | 28.0 | yes |  |
| `f9_idio_share_252` | F9 | 0.9201 | 67.9 | yes |  |
| `f9_idio_share_756` | F9 | 0.8190 | 46.6 | yes |  |
| `f10_dollar_adv_63` | F10 | 2.652e+07 | 53.3 | yes |  |
| `f10_dollar_adv_252` | F10 | 2.781e+07 | 57.3 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.9191 | 36.7 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 40.6 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0067 | 27.0 | yes |  |

### Diagnostic block

Census and baseline use only — never a distance input, never a map input.

| feature | raw | universe pct | covered |
|---|---:|---:|:--:|
| `d_sector` | — | — | no |
| `d_industry` | UNKNOWN | — | yes |
| `d_cap_bucket` | — | — | no |
| `d_market_cap_b` | — | — | no |
| `d_price_plane_id` | baskets_ohlcv_v1 | — | yes |
| `d_listing_venue_class` | — | — | no |
| `d_f6_gap_share_252` | 0.3998 | 37.1 | yes |
| `d_f6_event_gap_contrib_252` | 0.0659 | 53.9 | yes |
| `d_f6_gap_fill_rate_252` | 0.4677 | 23.4 | yes |
| `d_close_jump_freq_252` | 0.0397 | 89.9 | yes |
| `d_close_jump_drift5_252` | -0.0442 | 39.2 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2014-04-25 | 2014-04-28 | 2014-05-01 | 10.0 | 1.38 | 4 | recovered | no |
| failed_breakdown | 3 | 2014-05-06 | 2014-05-06 | 2014-05-12 | 6.2 | 0.71 | 4 | recovered | no |
| failed_breakdown | 3 | 2014-10-10 | 2014-10-13 | 2014-10-15 | 6.3 | 1.54 | 3 | recovered | no |
| failed_breakdown | 3 | 2014-11-19 | 2014-11-19 | 2014-11-20 | 1.6 | 0.31 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-12-16 | 2014-12-16 | 2014-12-17 | 2.9 | 0.68 | 1 | recovered | no |
| reclaim | 1 | 2015-04-09 | 2016-05-06 | 2016-08-05 | 44.7 | 23.16 | 272 | held | no |
| failed_breakdown | 3 | 2015-04-30 | 2015-05-06 | 2015-05-07 | 9.4 | 2.68 | 5 | recovered | no |
| failed_breakdown | 3 | 2015-07-20 | 2015-07-20 | 2015-07-21 | 0.5 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-07-22 | 2015-07-22 | 2015-07-23 | 0.3 | 0.07 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-08-13 | 2015-08-13 | 2015-08-14 | 2.1 | 0.32 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-09-24 | 2015-10-01 | 2015-10-07 | 8.3 | 1.73 | 9 | recovered | no |
| reset_decline | 3 | 2016-10-05 | 2016-10-28 | 2016-10-28 | 23.4 | 7.44 | 17 | durable_low | no |
| reset_decline | 1 | 2017-02-01 | 2017-05-17 | 2017-05-17 | 36.2 | 15.18 | 73 | durable_low | no |
| failed_breakdown | 3 | 2017-03-23 | 2017-03-28 | 2017-04-06 | 4.7 | 1.61 | 10 | recovered | no |
| reclaim | 2 | 2017-05-26 | 2017-08-04 | 2017-11-02 | 35.5 | 14.91 | 48 | held | no |
| reset_decline | 3 | 2017-11-24 | 2018-02-09 | 2018-02-09 | 19.5 | 7.53 | 52 | durable_low | no |
| failed_breakdown | 3 | 2017-12-07 | 2017-12-08 | 2017-12-13 | 3.0 | 0.92 | 4 | recovered | no |
| failed_breakdown | 3 | 2018-02-08 | 2018-02-09 | 2018-02-14 | 5.4 | 1.55 | 4 | recovered | no |
| reset_decline | 2 | 2018-05-09 | 2018-07-31 | 2018-07-31 | 23.0 | 9.37 | 57 | durable_low | no |
| failed_breakdown | 3 | 2018-07-23 | 2018-07-24 | 2018-07-25 | 1.8 | 0.61 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-07-30 | 2018-07-31 | 2018-08-06 | 2.9 | 0.79 | 5 | recovered | no |
| reset_decline | 2 | 2018-09-20 | 2018-11-21 | 2018-11-21 | 41.1 | 12.60 | 44 | durable_low | no |
| reclaim | 1 | 2018-12-21 | 2019-04-25 | 2019-05-10 | 38.4 | 11.75 | 84 | failed | no |
| failed_breakdown | 3 | 2019-05-28 | 2019-06-03 | 2019-06-04 | 3.8 | 1.04 | 5 | recovered | no |
| failed_breakdown | 3 | 2019-11-07 | 2019-11-07 | 2019-11-08 | 5.2 | 1.68 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-02-24 | 2020-02-24 | 2020-02-25 | 0.6 | 0.16 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-03-16 | 2020-03-18 | 2020-03-26 | 32.6 | 3.32 | 8 | recovered | no |
| reclaim | 1 | 2020-07-01 | 2020-11-06 | 2021-02-09 | 41.7 | 10.96 | 90 | held | no |
| reset_decline | 3 | 2020-11-27 | 2020-12-21 | 2020-12-21 | 21.7 | 5.44 | 16 | durable_low | no |
| reset_decline | 3 | 2021-03-17 | 2021-05-12 | 2021-05-12 | 14.5 | 3.40 | 39 | durable_low | no |
| failed_breakdown | 3 | 2021-07-16 | 2021-07-19 | 2021-07-20 | 3.9 | 1.15 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-11-26 | 2021-11-26 | 2021-11-29 | 0.8 | 0.22 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-11-30 | 2021-12-01 | 2021-12-07 | 4.7 | 1.27 | 5 | recovered | no |
| failed_breakdown | 3 | 2022-01-21 | 2022-01-27 | 2022-01-31 | 4.6 | 1.21 | 6 | recovered | no |
| failed_breakdown | 3 | 2022-03-07 | 2022-03-07 | 2022-03-10 | 5.0 | 1.19 | 3 | recovered | no |
| failed_breakdown | 3 | 2022-05-24 | 2022-05-24 | 2022-05-26 | 5.6 | 1.17 | 2 | recovered | no |
| reclaim | 2 | 2022-05-24 | 2022-08-05 | 2022-09-22 | 36.8 | 11.35 | 50 | failed | no |
| reset_decline | 2 | 2022-10-28 | 2022-12-20 | 2022-12-20 | 34.0 | 11.59 | 36 | durable_low | no |
| failed_breakdown | 3 | 2023-05-03 | 2023-05-04 | 2023-05-10 | 3.8 | 1.58 | 5 | recovered | no |
| failed_breakdown | 3 | 2023-10-26 | 2023-10-26 | 2023-10-27 | 2.1 | 0.81 | 1 | recovered | no |
| reset_decline | 2 | 2023-12-22 | 2024-02-23 | 2024-02-23 | 25.7 | 10.28 | 41 | durable_low | no |
| failed_breakdown | 3 | 2024-02-13 | 2024-02-13 | 2024-02-14 | 0.4 | 0.19 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-05-22 | 2024-05-28 | 2024-05-31 | 1.3 | 0.45 | 6 | recovered | no |
| failed_breakdown | 3 | 2024-06-04 | 2024-06-04 | 2024-06-07 | 1.4 | 0.60 | 3 | recovered | no |
| failed_breakdown | 3 | 2024-06-18 | 2024-06-18 | 2024-06-20 | 0.4 | 0.20 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-07-10 | 2024-07-10 | 2024-07-11 | 1.3 | 0.72 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-09-10 | 2024-09-10 | 2024-09-11 | 0.5 | 0.19 | 1 | recovered | no |
| reset_decline | 2 | 2025-01-28 | 2025-04-21 | 2025-04-21 | 21.1 | 8.13 | 57 | durable_low | no |
| failed_breakdown | 3 | 2025-04-07 | 2025-04-08 | 2025-04-09 | 2.3 | 0.71 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-04-21 | 2025-04-21 | 2025-04-22 | 0.9 | 0.22 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-08-01 | 2025-08-01 | 2025-08-04 | 1.9 | 0.96 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-10-10 | 2025-10-10 | 2025-10-13 | 0.7 | 0.28 | 1 | recovered | no |

**52 episodes**, 0 censored; by type {'failed_breakdown': 37, 'reset_decline': 10, 'reclaim': 5}; by tier {3: 41, 2: 7, 1: 4}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 4% | 0% | 4% | 0% | 0% | 0% | 0% | 92% |
| 2015 | 6% | 75% | 4% | 0% | 0% | 0% | 0% | 15% |
| 2016 | 6% | 40% | 0% | 46% | 8% | 0% | 0% | 0% |
| 2017 | 6% | 0% | 1% | 30% | 10% | 10% | 29% | 15% |
| 2018 | 6% | 0% | 4% | 0% | 35% | 17% | 14% | 23% |
| 2019 | 6% | 0% | 0% | 4% | 7% | 0% | 37% | 46% |
| 2020 | 4% | 24% | 8% | 13% | 9% | 0% | 5% | 36% |
| 2021 | 2% | 0% | 0% | 34% | 42% | 3% | 1% | 18% |
| 2022 | 2% | 0% | 0% | 22% | 0% | 0% | 25% | 50% |
| 2023 | 6% | 0% | 0% | 0% | 31% | 31% | 1% | 31% |
| 2024 | 4% | 0% | 0% | 0% | 21% | 2% | 29% | 45% |
| 2025 | 2% | 0% | 0% | 0% | 23% | 2% | 41% | 32% |
| 2026 | 0% | 8% | 8% | 3% | 0% | 0% | 25% | 56% |

## Episode map

![YELP episode map](YELP.png)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
