# PAAS — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | miner neighborhood probe |
| price plane | `baskets_ohlcv_v1` |
| first print | 2014-01-02 |
| last print | 2026-08-13 |
| sessions | 3172 |
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

**First-print sanity:** `PREDATES_CALENDAR` — first print 2014-01-02 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.1860 | 70.6 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0650 | 43.4 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0470 | 37.4 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.5845 | 63.1 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.3252 | 34.9 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.6071 | 58.2 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.8373 | 69.8 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.1587 | 95.0 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0886 | 89.3 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0347 | 51.2 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.2085 | 65.4 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 2.6667 | 97.9 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 4.5000 | 31.1 | yes |  |
| `f2_ulcer_126` | F2 | 24.9358 | 66.6 | yes |  |
| `f2_ulcer_252` | F2 | 18.4765 | 43.6 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 4.1125 | 46.2 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 15.0000 | 16.6 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0384 | 81.8 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.2187 | 1.9 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0039 | 71.8 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.7194 | 17.4 | yes |  |
| `f4_mr_half_life_252` | F4 | 29.0791 | 35.5 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 3.0000 | 44.9 | yes |  |
| `f5_realized_vol_21` | F5 | 57.8950 | 65.1 | yes |  |
| `f5_realized_vol_63` | F5 | 57.1215 | 63.3 | yes |  |
| `f5_realized_vol_252` | F5 | 57.4716 | 63.4 | yes |  |
| `f5_vol_of_vol_252` | F5 | 14.8021 | 55.8 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | -0.0158 | 12.4 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.2713 | 63.5 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.5345 | 80.1 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 1.0663 | 72.9 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 4.6889 | 85.6 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0873 | 70.5 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0198 | 38.2 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 12.7500 | 39.7 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 70.3333 | 74.9 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.5263 | 53.3 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.4633 | 94.8 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.5621 | 72.4 | yes |  |
| `f8_swing_period_median_1260` | F8 | 24.0000 | 32.5 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.2518 | 71.5 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 0.8973 | 44.2 | yes |  |
| `f9_idio_share_252` | F9 | 0.8465 | 40.5 | yes |  |
| `f9_idio_share_756` | F9 | 0.8693 | 63.4 | yes |  |
| `f10_dollar_adv_63` | F10 | 1.996e+08 | 81.6 | yes |  |
| `f10_dollar_adv_252` | F10 | 2.650e+08 | 86.0 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.6444 | 7.8 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 19.4 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0070 | 30.7 | yes |  |

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
| `d_f6_gap_share_252` | 0.7643 | 99.4 | yes |
| `d_f6_event_gap_contrib_252` | 0.0789 | 71.1 | yes |
| `d_f6_gap_fill_rate_252` | 0.3620 | 6.1 | yes |
| `d_close_jump_freq_252` | 0.0357 | 81.5 | yes |
| `d_close_jump_drift5_252` | 0.1492 | 53.1 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2014-05-07 | 2014-05-08 | 2014-05-09 | 1.6 | 0.47 | 2 | recovered | no |
| failed_breakdown | 3 | 2014-05-28 | 2014-05-28 | 2014-05-30 | 1.6 | 0.50 | 2 | recovered | no |
| reset_decline | 1 | 2014-07-09 | 2014-11-05 | 2014-11-05 | 43.2 | 15.06 | 84 | durable_low | no |
| failed_breakdown | 3 | 2014-10-30 | 2014-11-05 | 2014-11-07 | 11.7 | 2.52 | 6 | recovered | no |
| failed_breakdown | 3 | 2015-07-30 | 2015-07-30 | 2015-07-31 | 0.5 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-08-03 | 2015-08-05 | 2015-08-10 | 4.5 | 0.79 | 5 | recovered | no |
| reclaim | 1 | 2015-09-24 | 2016-02-04 | 2016-05-05 | 43.6 | 13.23 | 91 | held | no |
| failed_breakdown | 3 | 2016-01-12 | 2016-01-19 | 2016-01-26 | 9.8 | 1.88 | 9 | recovered | no |
| reset_decline | 2 | 2016-08-18 | 2016-12-22 | 2016-12-22 | 34.0 | 10.53 | 88 | durable_low | no |
| failed_breakdown | 3 | 2016-11-11 | 2016-11-11 | 2016-11-15 | 5.1 | 1.01 | 2 | recovered | no |
| failed_breakdown | 3 | 2016-12-22 | 2016-12-22 | 2016-12-27 | 1.9 | 0.33 | 2 | recovered | no |
| failed_breakdown | 3 | 2017-05-04 | 2017-05-04 | 2017-05-05 | 0.9 | 0.26 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-07-07 | 2017-07-07 | 2017-07-10 | 1.3 | 0.42 | 1 | recovered | no |
| reset_decline | 2 | 2017-09-05 | 2017-12-07 | 2017-12-07 | 25.7 | 10.26 | 66 | durable_low | no |
| failed_breakdown | 3 | 2017-11-03 | 2017-11-03 | 2017-11-06 | 0.2 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-12-06 | 2017-12-07 | 2017-12-13 | 2.6 | 0.95 | 5 | recovered | no |
| reset_decline | 2 | 2018-05-24 | 2018-11-27 | 2018-11-27 | 32.1 | 12.86 | 129 | durable_low | no |
| failed_breakdown | 3 | 2018-08-06 | 2018-08-08 | 2018-08-09 | 2.1 | 1.04 | 3 | recovered | no |
| failed_breakdown | 3 | 2018-08-15 | 2018-08-16 | 2018-08-20 | 3.6 | 1.30 | 3 | recovered | no |
| failed_breakdown | 3 | 2018-08-23 | 2018-08-23 | 2018-08-24 | 0.9 | 0.32 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-09-27 | 2018-09-27 | 2018-09-28 | 0.1 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-11-07 | 2018-11-07 | 2018-11-09 | 2.4 | 0.67 | 2 | recovered | no |
| failed_breakdown | 3 | 2019-03-01 | 2019-03-06 | 2019-03-08 | 2.9 | 0.82 | 5 | recovered | no |
| failed_breakdown | 3 | 2019-04-22 | 2019-04-23 | 2019-04-24 | 1.1 | 0.42 | 2 | recovered | no |
| failed_breakdown | 3 | 2019-05-20 | 2019-05-29 | 2019-05-31 | 4.7 | 1.37 | 8 | recovered | no |
| reclaim | 2 | 2019-05-20 | 2019-07-16 | 2019-10-14 | 43.9 | 21.88 | 39 | held | no |
| reset_decline | 3 | 2020-02-24 | 2020-03-20 | 2020-03-20 | 53.4 | 17.28 | 19 | durable_low | no |
| reset_decline | 2 | 2020-08-05 | 2021-01-27 | 2021-01-27 | 27.9 | 5.70 | 120 | durable_low | no |
| failed_breakdown | 3 | 2020-10-28 | 2020-10-28 | 2020-10-29 | 0.2 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-11-23 | 2020-11-24 | 2020-12-01 | 4.9 | 1.03 | 5 | recovered | no |
| failed_breakdown | 3 | 2021-01-27 | 2021-01-27 | 2021-01-28 | 2.3 | 0.44 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-07-08 | 2021-07-08 | 2021-07-09 | 2.1 | 0.58 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-07-16 | 2021-07-19 | 2021-07-28 | 5.0 | 1.44 | 8 | recovered | no |
| failed_breakdown | 3 | 2021-08-09 | 2021-08-10 | 2021-08-11 | 3.7 | 1.09 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-08-18 | 2021-08-20 | 2021-08-23 | 4.8 | 1.29 | 3 | recovered | no |
| reclaim | 1 | 2021-10-05 | 2022-03-04 | 2022-04-26 | 39.4 | 18.70 | 104 | failed | no |
| failed_breakdown | 3 | 2021-12-14 | 2021-12-15 | 2021-12-16 | 3.4 | 0.89 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-01-27 | 2022-01-28 | 2022-02-01 | 4.3 | 0.95 | 3 | recovered | no |
| reset_decline | 1 | 2022-04-13 | 2022-09-01 | 2022-09-01 | 51.0 | 14.55 | 97 | durable_low | no |
| failed_breakdown | 3 | 2022-05-09 | 2022-05-12 | 2022-05-19 | 6.1 | 1.23 | 8 | recovered | no |
| failed_breakdown | 3 | 2022-06-14 | 2022-06-14 | 2022-06-15 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-06-23 | 2022-06-23 | 2022-06-24 | 1.7 | 0.33 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-07-20 | 2022-07-20 | 2022-07-21 | 1.1 | 0.21 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-08-11 | 2022-08-11 | 2022-08-12 | 1.2 | 0.26 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-08-30 | 2022-09-01 | 2022-09-09 | 7.3 | 1.47 | 7 | recovered | no |
| reclaim | 1 | 2022-10-07 | 2023-01-20 | 2023-01-30 | 44.7 | 17.74 | 71 | failed | no |
| failed_breakdown | 3 | 2022-11-09 | 2022-11-09 | 2022-11-10 | 5.9 | 1.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2023-02-24 | 2023-02-27 | 2023-03-01 | 1.8 | 0.44 | 3 | recovered | no |
| reset_decline | 2 | 2023-04-13 | 2023-07-06 | 2023-07-06 | 27.9 | 7.87 | 57 | durable_low | no |
| failed_breakdown | 3 | 2023-05-25 | 2023-05-26 | 2023-05-31 | 0.5 | 0.13 | 3 | recovered | no |
| failed_breakdown | 3 | 2023-07-06 | 2023-07-06 | 2023-07-07 | 0.6 | 0.19 | 1 | recovered | no |
| failed_breakdown | 3 | 2023-10-02 | 2023-10-02 | 2023-10-09 | 3.2 | 0.91 | 5 | recovered | no |
| failed_breakdown | 3 | 2023-11-08 | 2023-11-08 | 2023-11-09 | 0.6 | 0.14 | 1 | recovered | no |
| failed_breakdown | 3 | 2023-11-10 | 2023-11-13 | 2023-11-14 | 3.5 | 0.77 | 2 | recovered | no |
| reset_decline | 2 | 2023-12-27 | 2024-02-28 | 2024-02-28 | 27.8 | 8.45 | 42 | durable_low | no |
| failed_breakdown | 3 | 2024-02-09 | 2024-02-09 | 2024-02-12 | 0.3 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-02-13 | 2024-02-13 | 2024-02-16 | 5.8 | 1.68 | 3 | recovered | no |
| failed_breakdown | 3 | 2024-02-28 | 2024-02-28 | 2024-02-29 | 0.4 | 0.11 | 1 | recovered | no |
| reset_decline | 3 | 2024-07-16 | 2024-08-08 | 2024-08-08 | 23.2 | 7.10 | 17 | durable_low | no |
| failed_breakdown | 3 | 2024-08-07 | 2024-08-08 | 2024-08-12 | 5.3 | 0.95 | 3 | recovered | no |
| reset_decline | 2 | 2024-10-22 | 2024-12-30 | 2024-12-30 | 22.5 | 6.32 | 47 | durable_low | no |
| failed_breakdown | 3 | 2024-12-18 | 2024-12-19 | 2024-12-26 | 1.5 | 0.34 | 5 | recovered | no |
| failed_breakdown | 3 | 2024-12-30 | 2024-12-30 | 2025-01-02 | 2.6 | 0.70 | 2 | recovered | no |
| reset_decline | 3 | 2025-10-16 | 2025-11-04 | 2025-11-04 | 21.0 | 5.87 | 13 | durable_low | no |
| reset_decline | 3 | 2026-02-27 | 2026-03-20 | 2026-03-20 | 31.9 | 6.14 | 15 | durable_low | no |
| failed_breakdown | 3 | 2026-03-19 | 2026-03-20 | 2026-03-25 | 8.3 | 1.17 | 4 | recovered | no |
| failed_breakdown | 3 | 2026-06-09 | 2026-06-10 | 2026-06-11 | 5.0 | 0.84 | 2 | recovered | no |
| failed_breakdown | 3 | 2026-07-07 | 2026-07-17 | 2026-07-21 | 5.4 | 0.98 | 10 | recovered | no |

**68 episodes**, 0 censored; by type {'failed_breakdown': 51, 'reset_decline': 13, 'reclaim': 4}; by tier {3: 55, 2: 8, 1: 5}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 0% | 0% | 5% | 0% | 0% | 0% | 0% | 95% |
| 2015 | 0% | 23% | 3% | 0% | 0% | 0% | 0% | 75% |
| 2016 | 0% | 4% | 0% | 48% | 31% | 8% | 0% | 10% |
| 2017 | 0% | 0% | 0% | 0% | 40% | 4% | 2% | 55% |
| 2018 | 4% | 0% | 0% | 0% | 26% | 6% | 10% | 54% |
| 2019 | 0% | 0% | 4% | 38% | 0% | 9% | 9% | 41% |
| 2020 | 0% | 2% | 0% | 45% | 37% | 10% | 1% | 5% |
| 2021 | 2% | 0% | 2% | 0% | 24% | 2% | 15% | 55% |
| 2022 | 0% | 25% | 7% | 9% | 6% | 0% | 7% | 46% |
| 2023 | 0% | 6% | 0% | 21% | 6% | 0% | 8% | 60% |
| 2024 | 2% | 0% | 0% | 0% | 51% | 23% | 0% | 24% |
| 2025 | 2% | 0% | 0% | 0% | 36% | 61% | 0% | 1% |
| 2026 | 3% | 0% | 0% | 0% | 54% | 16% | 8% | 18% |

## Episode map

![PAAS episode map](PAAS.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
