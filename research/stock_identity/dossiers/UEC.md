# UEC — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | disagreement set |
| price plane | `baskets_ohlcv_v1` |
| first print | 2014-01-02 |
| last print | 2026-08-13 |
| sessions | 3172 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | adv3 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol3 |
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
| `f1_kaufman_er_63` | F1 | 0.1508 | 60.8 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0787 | 51.4 | yes | **unstable** |
| `f1_kaufman_er_252` | F1 | 0.0066 | 5.8 | yes | **unstable** |
| `f1_logprice_r2_126` | F1 | 0.6508 | 69.6 | yes | **unstable** |
| `f1_logprice_r2_252` | F1 | 0.0283 | 9.2 | yes | **unstable** |
| `f1_share_above_50dma_252` | F1 | 0.5040 | 35.4 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.7659 | 62.6 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0873 | 75.3 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0794 | 85.0 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0475 | 66.7 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.1774 | 55.9 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.3333 | 80.7 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 1.0000 | 94.1 | yes |  |
| `f2_time_under_water_median_756` | F2 | 4.5000 | 31.1 | yes |  |
| `f2_ulcer_126` | F2 | 36.7145 | 83.7 | yes |  |
| `f2_ulcer_252` | F2 | 29.1775 | 65.7 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 4.3154 | 50.9 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 13.0000 | 10.0 | yes |  |
| `f4_ar1_daily_252` | F4 | -0.0661 | 33.2 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.0657 | 31.7 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 0.9260 | 38.5 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8390 | 42.6 | yes |  |
| `f4_mr_half_life_252` | F4 | 14.7199 | 9.7 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 2.1000 | 17.8 | yes |  |
| `f5_realized_vol_21` | F5 | 56.6456 | 63.7 | yes |  |
| `f5_realized_vol_63` | F5 | 83.1360 | 85.6 | yes |  |
| `f5_realized_vol_252` | F5 | 78.6544 | 83.1 | yes |  |
| `f5_vol_of_vol_252` | F5 | 16.1737 | 61.0 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.1077 | 65.9 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 2.0353 | 84.2 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.1626 | 43.5 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 0.3035 | 44.5 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 2.3475 | 60.5 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0714 | 50.3 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0198 | 38.2 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 12.7000 | 39.6 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 64.3333 | 73.1 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.3158 | 14.3 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.3629 | 80.0 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 483.0000 | 73.7 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.1938 | 50.0 | yes |  |
| `f8_swing_period_median_756` | F8 | 13.5000 | 11.2 | yes |  |
| `f8_swing_period_median_1260` | F8 | 17.5000 | 19.4 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.9447 | 91.5 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 1.2170 | 74.0 | yes |  |
| `f9_idio_share_252` | F9 | 0.8022 | 25.8 | yes |  |
| `f9_idio_share_756` | F9 | 0.8643 | 61.7 | yes |  |
| `f10_dollar_adv_63` | F10 | 9.418e+07 | 73.0 | yes |  |
| `f10_dollar_adv_252` | F10 | 1.315e+08 | 77.9 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.7140 | 12.2 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 27.8 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0143 | 78.8 | yes |  |

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
| `d_f6_gap_share_252` | 0.5071 | 84.5 | yes |
| `d_f6_event_gap_contrib_252` | 0.0484 | 23.0 | yes |
| `d_f6_gap_fill_rate_252` | 0.5732 | 55.3 | yes |
| `d_close_jump_freq_252` | 0.0198 | 17.3 | yes |
| `d_close_jump_drift5_252` | -0.7497 | 8.4 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2014-03-31 | 2014-03-31 | 2014-04-01 | 0.8 | 0.09 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-05-05 | 2014-05-07 | 2014-05-12 | 3.9 | 0.47 | 5 | recovered | no |
| failed_breakdown | 3 | 2014-09-19 | 2014-09-19 | 2014-09-22 | 0.8 | 0.14 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-09-26 | 2014-09-26 | 2014-09-29 | 0.8 | 0.12 | 1 | recovered | no |
| reset_decline | 2 | 2014-11-20 | 2015-01-21 | 2015-01-21 | 42.8 | 5.79 | 40 | durable_low | no |
| reclaim | 2 | 2015-01-23 | 2015-03-30 | 2015-04-07 | 43.2 | 8.24 | 45 | failed | no |
| reset_decline | 2 | 2015-05-29 | 2015-08-26 | 2015-08-26 | 68.2 | 11.63 | 62 | durable_low | no |
| failed_breakdown | 3 | 2015-07-02 | 2015-07-08 | 2015-07-14 | 17.5 | 1.11 | 7 | recovered | no |
| failed_breakdown | 3 | 2015-08-19 | 2015-08-26 | 2015-08-31 | 19.5 | 2.91 | 8 | recovered | no |
| failed_breakdown | 3 | 2015-12-17 | 2015-12-17 | 2015-12-22 | 2.0 | 0.36 | 3 | recovered | no |
| reset_decline | 3 | 2016-06-06 | 2016-06-28 | 2016-06-28 | 26.8 | 5.59 | 16 | durable_low | no |
| reset_decline | 2 | 2016-08-11 | 2016-11-29 | 2016-11-29 | 31.7 | 6.83 | 76 | durable_low | no |
| failed_breakdown | 3 | 2016-10-18 | 2016-10-18 | 2016-10-19 | 1.1 | 0.24 | 1 | recovered | no |
| failed_breakdown | 3 | 2016-10-26 | 2016-10-26 | 2016-10-31 | 3.4 | 0.67 | 3 | recovered | no |
| failed_breakdown | 3 | 2016-11-02 | 2016-11-02 | 2016-11-03 | 1.2 | 0.22 | 1 | recovered | no |
| failed_breakdown | 3 | 2016-11-29 | 2016-11-29 | 2016-11-30 | 3.5 | 0.63 | 1 | recovered | no |
| reset_decline | 2 | 2017-02-14 | 2017-05-04 | 2017-05-04 | 39.7 | 6.08 | 55 | durable_low | no |
| failed_breakdown | 3 | 2017-04-28 | 2017-05-04 | 2017-05-09 | 14.0 | 2.25 | 7 | recovered | no |
| failed_breakdown | 3 | 2017-10-26 | 2017-11-03 | 2017-11-09 | 10.3 | 2.02 | 10 | recovered | no |
| reclaim | 3 | 2017-11-07 | 2017-11-16 | 2017-11-27 | 41.8 | 11.05 | 7 | failed | no |
| reset_decline | 2 | 2018-01-05 | 2018-03-27 | 2018-03-27 | 36.4 | 6.25 | 55 | durable_low | no |
| failed_breakdown | 3 | 2018-02-12 | 2018-02-12 | 2018-02-13 | 2.3 | 0.30 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-03-27 | 2018-03-27 | 2018-03-29 | 0.8 | 0.14 | 2 | recovered | no |
| reset_decline | 1 | 2018-08-06 | 2018-12-20 | 2018-12-20 | 37.2 | 7.04 | 95 | durable_low | no |
| failed_breakdown | 3 | 2018-10-26 | 2018-10-26 | 2018-10-30 | 5.5 | 0.91 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-12-17 | 2018-12-20 | 2018-12-26 | 5.0 | 0.85 | 6 | recovered | no |
| reclaim | 1 | 2018-12-19 | 2019-04-01 | 2019-04-11 | 41.9 | 11.75 | 69 | failed | no |
| reset_decline | 1 | 2019-04-10 | 2019-08-07 | 2019-08-07 | 44.2 | 10.68 | 82 | durable_low | no |
| failed_breakdown | 3 | 2019-08-06 | 2019-08-07 | 2019-08-08 | 5.4 | 0.71 | 2 | recovered | no |
| failed_breakdown | 3 | 2019-11-25 | 2019-12-03 | 2019-12-05 | 10.8 | 2.40 | 7 | recovered | no |
| reclaim | 1 | 2019-11-26 | 2020-04-22 | 2020-06-26 | 44.2 | 14.40 | 100 | failed | no |
| failed_breakdown | 3 | 2020-01-27 | 2020-01-28 | 2020-01-31 | 6.0 | 1.55 | 4 | recovered | no |
| failed_breakdown | 3 | 2020-03-11 | 2020-03-12 | 2020-03-17 | 29.6 | 2.36 | 4 | recovered | no |
| reset_decline | 3 | 2020-09-18 | 2020-10-28 | 2020-10-28 | 36.4 | 7.12 | 28 | durable_low | no |
| reset_decline | 3 | 2021-04-05 | 2021-04-20 | 2021-04-20 | 27.0 | 3.52 | 11 | durable_low | no |
| failed_breakdown | 3 | 2021-06-29 | 2021-06-29 | 2021-06-30 | 3.1 | 0.36 | 1 | recovered | no |
| reset_decline | 2 | 2021-11-11 | 2022-01-27 | 2022-01-27 | 55.9 | 8.70 | 52 | durable_low | no |
| reset_decline | 2 | 2022-04-13 | 2022-07-06 | 2022-07-06 | 53.7 | 7.85 | 56 | durable_low | no |
| failed_breakdown | 3 | 2022-07-06 | 2022-07-06 | 2022-07-07 | 1.6 | 0.15 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-12-16 | 2022-12-16 | 2022-12-20 | 2.5 | 0.37 | 2 | recovered | no |
| failed_breakdown | 3 | 2023-04-06 | 2023-04-06 | 2023-04-10 | 0.4 | 0.05 | 1 | recovered | no |
| reclaim | 2 | 2023-05-31 | 2023-07-31 | 2023-10-27 | 43.3 | 14.54 | 41 | held | no |
| reset_decline | 3 | 2024-02-01 | 2024-03-15 | 2024-03-15 | 23.4 | 5.01 | 30 | durable_low | no |
| failed_breakdown | 3 | 2024-06-07 | 2024-06-11 | 2024-06-20 | 11.3 | 2.08 | 8 | recovered | no |
| failed_breakdown | 3 | 2024-07-25 | 2024-07-25 | 2024-07-26 | 1.4 | 0.28 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-09-06 | 2024-09-06 | 2024-09-09 | 2.7 | 0.39 | 1 | recovered | no |
| reclaim | 3 | 2024-09-10 | 2024-10-01 | 2024-12-31 | 43.8 | 11.46 | 15 | held | no |
| reset_decline | 1 | 2024-11-19 | 2025-04-08 | 2025-04-08 | 53.5 | 8.72 | 94 | durable_low | no |
| failed_breakdown | 3 | 2025-03-10 | 2025-03-10 | 2025-03-11 | 3.0 | 0.38 | 1 | recovered | no |
| reclaim | 2 | 2025-04-21 | 2025-06-16 | 2025-07-08 | 44.7 | 10.40 | 39 | failed | no |
| reset_decline | 3 | 2025-10-15 | 2025-11-21 | 2025-11-21 | 34.9 | 5.21 | 27 | durable_low | no |
| reset_decline | 1 | 2026-01-28 | — | 2026-08-13 | 55.1 | 9.10 | 136 | censored | yes |
| failed_breakdown | 3 | 2026-05-19 | 2026-05-19 | 2026-05-20 | 1.5 | 0.16 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-09 | 2026-06-10 | 2026-06-18 | 20.9 | 2.30 | 7 | recovered | no |
| failed_breakdown | 3 | 2026-07-16 | 2026-07-17 | 2026-07-21 | 1.5 | 0.19 | 3 | recovered | no |
| failed_breakdown | 3 | 2026-07-29 | 2026-07-29 | 2026-07-30 | 2.6 | 0.37 | 1 | recovered | no |

**56 episodes**, 1 censored; by type {'failed_breakdown': 33, 'reset_decline': 16, 'reclaim': 7}; by tier {3: 40, 2: 10, 1: 6}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 2015 | 0% | 52% | 1% | 25% | 2% | 0% | 0% | 19% |
| 2016 | 0% | 48% | 0% | 39% | 1% | 0% | 0% | 12% |
| 2017 | 2% | 0% | 2% | 10% | 53% | 8% | 4% | 21% |
| 2018 | 0% | 0% | 1% | 20% | 39% | 0% | 2% | 38% |
| 2019 | 0% | 15% | 1% | 5% | 2% | 0% | 12% | 65% |
| 2020 | 2% | 20% | 0% | 45% | 11% | 6% | 8% | 9% |
| 2021 | 0% | 0% | 0% | 39% | 43% | 10% | 0% | 8% |
| 2022 | 0% | 31% | 0% | 51% | 0% | 0% | 0% | 17% |
| 2023 | 0% | 20% | 6% | 43% | 2% | 6% | 0% | 23% |
| 2024 | 0% | 2% | 4% | 26% | 36% | 9% | 2% | 21% |
| 2025 | 2% | 4% | 3% | 47% | 20% | 0% | 7% | 17% |
| 2026 | 0% | 23% | 0% | 0% | 56% | 6% | 5% | 11% |

## Episode map

![UEC episode map](UEC.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
