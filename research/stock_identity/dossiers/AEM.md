# AEM — Identity Atlas v0 dossier

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
| `f1_kaufman_er_63` | F1 | 0.0598 | 28.6 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0633 | 42.3 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0464 | 36.9 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.7541 | 81.7 | yes | **unstable** |
| `f1_logprice_r2_252` | F1 | 0.0405 | 11.3 | yes | **unstable** |
| `f1_share_above_50dma_252` | F1 | 0.5992 | 56.3 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.7659 | 62.6 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.1508 | 93.7 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.1481 | 99.3 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0179 | 19.1 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.0933 | 20.4 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.3333 | 80.7 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 4.0000 | 21.5 | yes |  |
| `f2_ulcer_126` | F2 | 28.7424 | 72.8 | yes |  |
| `f2_ulcer_252` | F2 | 20.9761 | 49.7 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 4.7193 | 59.8 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 19.0000 | 32.0 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0016 | 67.0 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.1182 | 15.1 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0835 | 90.9 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8192 | 37.6 | yes |  |
| `f4_mr_half_life_252` | F4 | 25.1352 | 28.6 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 4.5455 | 78.4 | yes |  |
| `f5_realized_vol_21` | F5 | 49.1557 | 54.6 | yes |  |
| `f5_realized_vol_63` | F5 | 49.1772 | 53.3 | yes |  |
| `f5_realized_vol_252` | F5 | 46.3424 | 49.1 | yes |  |
| `f5_vol_of_vol_252` | F5 | 11.5868 | 42.7 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | -0.0540 | 4.6 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.1401 | 57.1 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.4101 | 68.6 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 0.8196 | 63.9 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 4.4817 | 83.7 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0476 | 19.3 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0198 | 38.2 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 21.5714 | 78.6 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 64.3333 | 73.1 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.7500 | 93.7 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.4464 | 92.9 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.4272 | 63.3 | yes |  |
| `f8_swing_period_median_756` | F8 | 20.5000 | 27.0 | yes |  |
| `f8_swing_period_median_1260` | F8 | 32.0000 | 45.2 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 0.9783 | 56.6 | yes | **unstable** |
| `f9_beta_univ_ew_756` | F9 | 0.5061 | 13.8 | yes | **unstable** |
| `f9_idio_share_252` | F9 | 0.8558 | 43.3 | yes | **unstable** |
| `f9_idio_share_756` | F9 | 0.9233 | 82.7 | yes | **unstable** |
| `f10_dollar_adv_63` | F10 | 4.132e+08 | 90.2 | yes |  |
| `f10_dollar_adv_252` | F10 | 4.430e+08 | 91.7 | yes |  |
| `f10_turnover_proxy_252` | F10 | 1.0803 | 58.6 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 11.8 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0068 | 28.0 | yes |  |

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
| `d_f6_gap_share_252` | 0.6837 | 98.4 | yes |
| `d_f6_event_gap_contrib_252` | 0.0636 | 50.6 | yes |
| `d_f6_gap_fill_rate_252` | 0.3759 | 7.8 | yes |
| `d_close_jump_freq_252` | 0.0317 | 68.3 | yes |
| `d_close_jump_drift5_252` | 1.1007 | 92.2 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2014-04-16 | 2014-04-21 | 2014-04-25 | 4.3 | 1.16 | 6 | recovered | no |
| reset_decline | 1 | 2014-07-28 | 2014-12-16 | 2014-12-16 | 48.1 | 17.67 | 99 | durable_low | no |
| failed_breakdown | 3 | 2014-10-03 | 2014-10-07 | 2014-10-08 | 3.7 | 0.98 | 3 | recovered | no |
| failed_breakdown | 3 | 2014-12-15 | 2014-12-16 | 2014-12-17 | 1.8 | 0.30 | 2 | recovered | no |
| reclaim | 3 | 2014-12-22 | 2015-01-16 | 2015-02-06 | 45.3 | 13.61 | 17 | failed | no |
| failed_breakdown | 3 | 2015-06-30 | 2015-07-01 | 2015-07-06 | 3.7 | 1.19 | 3 | recovered | no |
| failed_breakdown | 3 | 2015-07-30 | 2015-08-05 | 2015-08-10 | 5.7 | 1.07 | 7 | recovered | no |
| reclaim | 1 | 2015-09-09 | 2016-01-05 | 2016-01-19 | 37.5 | 9.94 | 81 | failed | no |
| reset_decline | 1 | 2016-08-04 | 2016-12-15 | 2016-12-15 | 38.8 | 13.11 | 93 | durable_low | no |
| reset_decline | 3 | 2017-09-05 | 2017-12-06 | 2017-12-06 | 19.3 | 8.64 | 65 | durable_low | no |
| failed_breakdown | 3 | 2017-10-20 | 2017-10-20 | 2017-10-23 | 0.2 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-10-24 | 2017-10-25 | 2017-10-26 | 0.9 | 0.46 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-09-04 | 2018-09-05 | 2018-09-18 | 5.4 | 1.77 | 10 | recovered | no |
| reclaim | 1 | 2018-09-05 | 2018-12-24 | 2019-01-08 | 35.9 | 17.06 | 76 | failed | no |
| failed_breakdown | 3 | 2019-04-23 | 2019-04-23 | 2019-04-24 | 0.1 | 0.04 | 1 | recovered | no |
| reset_decline | 3 | 2019-09-04 | 2019-10-15 | 2019-10-15 | 19.2 | 7.45 | 29 | durable_low | no |
| failed_breakdown | 3 | 2019-10-15 | 2019-10-15 | 2019-10-16 | 0.6 | 0.17 | 1 | recovered | no |
| reclaim | 3 | 2020-04-01 | 2020-04-22 | 2020-07-22 | 34.7 | 5.57 | 14 | held | no |
| reset_decline | 2 | 2020-09-14 | 2020-11-24 | 2020-11-24 | 26.9 | 7.20 | 51 | durable_low | no |
| failed_breakdown | 3 | 2021-07-22 | 2021-07-23 | 2021-07-26 | 0.8 | 0.32 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-09-10 | 2021-09-10 | 2021-09-14 | 0.8 | 0.29 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-12-01 | 2021-12-02 | 2021-12-07 | 3.1 | 1.01 | 4 | recovered | no |
| failed_breakdown | 3 | 2021-12-10 | 2021-12-10 | 2021-12-13 | 0.3 | 0.10 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-01-27 | 2022-01-28 | 2022-01-31 | 3.0 | 0.78 | 2 | recovered | no |
| reset_decline | 1 | 2022-04-14 | 2022-07-25 | 2022-07-25 | 41.1 | 12.92 | 68 | durable_low | no |
| failed_breakdown | 3 | 2022-06-14 | 2022-06-14 | 2022-06-16 | 3.3 | 0.78 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-06-23 | 2022-06-23 | 2022-06-24 | 0.7 | 0.17 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-07-15 | 2022-07-25 | 2022-07-29 | 10.6 | 2.12 | 10 | recovered | no |
| failed_breakdown | 3 | 2022-09-26 | 2022-09-26 | 2022-09-28 | 1.4 | 0.32 | 2 | recovered | no |
| reclaim | 2 | 2022-09-26 | 2022-11-29 | 2023-02-17 | 42.0 | 16.04 | 45 | failed | no |
| reset_decline | 3 | 2023-01-25 | 2023-03-08 | 2023-03-08 | 22.0 | 8.79 | 29 | durable_low | no |
| failed_breakdown | 3 | 2023-02-17 | 2023-02-23 | 2023-03-01 | 3.4 | 1.04 | 7 | recovered | no |
| failed_breakdown | 3 | 2023-03-08 | 2023-03-08 | 2023-03-10 | 0.5 | 0.16 | 2 | recovered | no |
| reset_decline | 2 | 2023-05-04 | 2023-10-04 | 2023-10-04 | 27.0 | 10.59 | 105 | durable_low | no |
| failed_breakdown | 3 | 2023-06-20 | 2023-06-28 | 2023-06-30 | 2.8 | 1.05 | 8 | recovered | no |
| failed_breakdown | 3 | 2023-07-06 | 2023-07-06 | 2023-07-10 | 0.6 | 0.22 | 2 | recovered | no |
| failed_breakdown | 3 | 2023-08-08 | 2023-08-08 | 2023-08-09 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2023-08-14 | 2023-08-16 | 2023-08-28 | 4.7 | 1.97 | 10 | recovered | no |
| failed_breakdown | 3 | 2023-09-27 | 2023-09-27 | 2023-09-28 | 0.8 | 0.34 | 1 | recovered | no |
| failed_breakdown | 3 | 2023-10-02 | 2023-10-04 | 2023-10-09 | 4.0 | 1.52 | 5 | recovered | no |
| reset_decline | 3 | 2023-12-27 | 2024-02-13 | 2024-02-13 | 19.7 | 8.00 | 32 | durable_low | no |
| failed_breakdown | 3 | 2024-02-13 | 2024-02-13 | 2024-02-15 | 3.5 | 1.28 | 2 | recovered | no |
| failed_breakdown | 3 | 2024-11-13 | 2024-11-13 | 2024-11-14 | 1.2 | 0.37 | 1 | recovered | no |
| reset_decline | 3 | 2025-10-16 | 2025-10-27 | 2025-10-27 | 16.4 | 6.11 | 7 | durable_low | no |
| reset_decline | 1 | 2026-03-02 | — | 2026-08-13 | 45.8 | 12.37 | 114 | censored | yes |
| failed_breakdown | 3 | 2026-05-05 | 2026-05-05 | 2026-05-06 | 0.6 | 0.13 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-05-19 | 2026-05-19 | 2026-05-20 | 2.7 | 0.63 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-03 | 2026-06-03 | 2026-06-04 | 0.8 | 0.19 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-05 | 2026-06-10 | 2026-06-15 | 11.2 | 2.70 | 6 | recovered | no |

**49 episodes**, 1 censored; by type {'failed_breakdown': 33, 'reset_decline': 11, 'reclaim': 5}; by tier {3: 40, 1: 6, 2: 3}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 0% | 0% | 6% | 0% | 0% | 0% | 0% | 94% |
| 2015 | 0% | 3% | 1% | 31% | 0% | 0% | 0% | 65% |
| 2016 | 0% | 0% | 0% | 17% | 28% | 40% | 0% | 16% |
| 2017 | 0% | 0% | 0% | 0% | 39% | 0% | 4% | 57% |
| 2018 | 0% | 0% | 1% | 4% | 25% | 1% | 1% | 69% |
| 2019 | 0% | 0% | 0% | 15% | 47% | 34% | 1% | 3% |
| 2020 | 2% | 0% | 0% | 45% | 25% | 10% | 0% | 17% |
| 2021 | 0% | 0% | 0% | 0% | 14% | 0% | 9% | 77% |
| 2022 | 0% | 0% | 2% | 10% | 20% | 0% | 9% | 59% |
| 2023 | 0% | 0% | 0% | 20% | 32% | 7% | 10% | 31% |
| 2024 | 0% | 0% | 0% | 0% | 26% | 63% | 5% | 7% |
| 2025 | 0% | 0% | 0% | 0% | 27% | 73% | 0% | 0% |
| 2026 | 0% | 2% | 0% | 1% | 40% | 21% | 1% | 35% |

## Episode map

![AEM episode map](AEM.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
