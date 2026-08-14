# BABA — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | operator core |
| price plane | `stock_identity_ohlcv_v1` |
| first print | 2014-09-19 |
| last print | 2026-08-13 |
| sessions | 2992 |
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

**First-print sanity:** `PREDATES_CALENDAR` — first print 2014-09-19 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.1518 | 61.0 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.1321 | 76.7 | yes | **unstable** |
| `f1_kaufman_er_252` | F1 | 0.0012 | 0.8 | yes | **unstable** |
| `f1_logprice_r2_126` | F1 | 0.4135 | 47.7 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.4353 | 44.1 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.4484 | 25.2 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.5397 | 38.4 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0357 | 47.2 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0317 | 40.0 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0216 | 26.4 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.3128 | 82.7 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.0000 | 66.8 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 1.0000 | 94.1 | yes |  |
| `f2_time_under_water_median_756` | F2 | 3.0000 | 7.3 | yes |  |
| `f2_ulcer_126` | F2 | 30.4277 | 75.3 | yes |  |
| `f2_ulcer_252` | F2 | 25.7576 | 58.9 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 4.6214 | 57.5 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 17.5000 | 25.8 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0141 | 73.1 | yes |  |
| `f4_ar1_weekly_756` | F4 | 0.1378 | 96.4 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0011 | 70.8 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 1.2377 | 96.9 | yes |  |
| `f4_mr_half_life_252` | F4 | 44.0752 | 54.8 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 5.7500 | 90.3 | yes |  |
| `f5_realized_vol_21` | F5 | 38.4400 | 38.6 | yes |  |
| `f5_realized_vol_63` | F5 | 42.2759 | 42.9 | yes |  |
| `f5_realized_vol_252` | F5 | 44.5623 | 46.9 | yes |  |
| `f5_vol_of_vol_252` | F5 | 9.7592 | 34.8 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | -0.0049 | 16.1 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 0.4862 | 14.2 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.0269 | 31.5 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | -0.2068 | 27.2 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 0.3515 | 38.5 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0635 | 39.8 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0040 | 13.3 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 12.5556 | 38.7 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 136.0000 | 88.2 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.2632 | 9.3 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.3806 | 83.4 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.8280 | 84.8 | yes |  |
| `f8_swing_period_median_1260` | F8 | 30.0000 | 42.1 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 0.7448 | 38.1 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 0.6342 | 21.3 | yes |  |
| `f9_idio_share_252` | F9 | 0.9096 | 64.0 | yes |  |
| `f9_idio_share_756` | F9 | 0.9034 | 76.1 | yes |  |
| `f10_dollar_adv_63` | F10 | 1.244e+09 | 96.9 | yes |  |
| `f10_dollar_adv_252` | F10 | 1.567e+09 | 98.3 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.6987 | 11.1 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 2.0 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0035 | 0.6 | yes |  |

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
| `d_f6_gap_share_252` | 0.7997 | 99.6 | yes |
| `d_f6_event_gap_contrib_252` | 0.0693 | 59.3 | yes |
| `d_f6_gap_fill_rate_252` | 0.1267 | 0.2 | yes |
| `d_close_jump_freq_252` | 0.0357 | 81.5 | yes |
| `d_close_jump_drift5_252` | 0.5995 | 78.1 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2015-02-23 | 2015-02-24 | 2015-02-25 | 1.2 | 0.40 | 2 | recovered | no |
| failed_breakdown | 3 | 2015-03-02 | 2015-03-03 | 2015-03-04 | 3.7 | 1.36 | 2 | recovered | no |
| failed_breakdown | 3 | 2015-04-30 | 2015-05-05 | 2015-05-07 | 2.5 | 1.07 | 5 | recovered | no |
| failed_breakdown | 3 | 2015-07-08 | 2015-07-08 | 2015-07-10 | 2.0 | 0.87 | 2 | recovered | no |
| failed_breakdown | 3 | 2015-09-01 | 2015-09-01 | 2015-09-03 | 1.5 | 0.33 | 2 | recovered | no |
| failed_breakdown | 3 | 2015-09-04 | 2015-09-08 | 2015-09-15 | 6.0 | 1.45 | 6 | recovered | no |
| reclaim | 3 | 2015-09-17 | 2015-10-28 | 2015-11-11 | 44.8 | 17.85 | 29 | failed | no |
| failed_breakdown | 3 | 2015-09-23 | 2015-09-28 | 2015-10-02 | 5.8 | 1.24 | 7 | recovered | no |
| failed_breakdown | 3 | 2016-01-20 | 2016-01-20 | 2016-01-21 | 1.3 | 0.30 | 1 | recovered | no |
| failed_breakdown | 3 | 2016-06-27 | 2016-06-27 | 2016-06-28 | 1.6 | 0.64 | 1 | recovered | no |
| reset_decline | 2 | 2016-09-22 | 2016-12-23 | 2016-12-23 | 20.6 | 8.97 | 65 | durable_low | no |
| failed_breakdown | 3 | 2016-11-11 | 2016-11-14 | 2016-11-17 | 4.4 | 1.45 | 4 | recovered | no |
| failed_breakdown | 3 | 2016-12-15 | 2016-12-16 | 2016-12-20 | 1.2 | 0.49 | 3 | recovered | no |
| failed_breakdown | 3 | 2016-12-22 | 2016-12-23 | 2017-01-04 | 2.1 | 0.92 | 7 | recovered | no |
| reset_decline | 3 | 2018-01-26 | 2018-04-06 | 2018-04-06 | 18.4 | 7.95 | 48 | durable_low | no |
| failed_breakdown | 3 | 2018-04-04 | 2018-04-06 | 2018-04-10 | 3.6 | 0.93 | 4 | recovered | no |
| reset_decline | 1 | 2018-06-14 | 2019-01-03 | 2019-01-03 | 38.1 | 17.64 | 139 | durable_low | no |
| failed_breakdown | 3 | 2018-10-29 | 2018-10-29 | 2018-10-31 | 3.6 | 0.83 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-12-21 | 2018-12-24 | 2018-12-26 | 1.1 | 0.26 | 2 | recovered | no |
| failed_breakdown | 3 | 2019-01-03 | 2019-01-03 | 2019-01-04 | 1.0 | 0.23 | 1 | recovered | no |
| reclaim | 3 | 2019-01-03 | 2019-02-19 | 2019-05-20 | 38.1 | 14.27 | 31 | failed | no |
| reset_decline | 3 | 2019-05-03 | 2019-05-31 | 2019-05-31 | 23.5 | 11.57 | 19 | durable_low | no |
| reset_decline | 2 | 2020-01-13 | 2020-03-23 | 2020-03-23 | 23.5 | 14.08 | 48 | durable_low | no |
| failed_breakdown | 3 | 2020-03-09 | 2020-03-09 | 2020-03-10 | 1.4 | 0.40 | 1 | recovered | no |
| reset_decline | 2 | 2020-10-27 | 2020-12-24 | 2020-12-24 | 30.0 | 11.72 | 41 | durable_low | no |
| failed_breakdown | 3 | 2020-11-16 | 2020-11-18 | 2020-11-20 | 1.9 | 0.43 | 4 | recovered | no |
| failed_breakdown | 3 | 2020-12-15 | 2020-12-15 | 2020-12-16 | 0.3 | 0.10 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-07-08 | 2021-07-08 | 2021-07-13 | 3.0 | 1.27 | 3 | recovered | no |
| failed_breakdown | 3 | 2021-07-26 | 2021-07-27 | 2021-08-02 | 6.9 | 2.41 | 5 | recovered | no |
| reclaim | 1 | 2021-07-27 | 2023-01-03 | 2023-02-24 | 41.3 | 20.42 | 362 | failed | no |
| failed_breakdown | 3 | 2021-09-15 | 2021-09-16 | 2021-09-17 | 1.1 | 0.27 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-01-27 | 2022-01-27 | 2022-01-28 | 0.2 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-03-10 | 2022-03-15 | 2022-03-16 | 21.3 | 3.78 | 4 | recovered | no |
| failed_breakdown | 3 | 2022-09-06 | 2022-09-06 | 2022-09-07 | 1.0 | 0.20 | 1 | recovered | no |
| reset_decline | 2 | 2023-01-26 | 2023-03-20 | 2023-03-20 | 32.8 | 9.64 | 36 | durable_low | no |
| failed_breakdown | 3 | 2023-03-09 | 2023-03-20 | 2023-03-23 | 5.4 | 1.30 | 10 | recovered | no |
| failed_breakdown | 3 | 2023-05-25 | 2023-05-30 | 2023-06-01 | 2.9 | 0.76 | 4 | recovered | no |
| failed_breakdown | 3 | 2023-10-04 | 2023-10-05 | 2023-10-06 | 0.5 | 0.20 | 2 | recovered | no |
| failed_breakdown | 3 | 2023-12-04 | 2023-12-11 | 2023-12-15 | 3.5 | 1.19 | 9 | recovered | no |
| failed_breakdown | 3 | 2024-01-16 | 2024-01-18 | 2024-01-23 | 3.4 | 1.30 | 5 | recovered | no |
| reset_decline | 3 | 2024-05-17 | 2024-06-28 | 2024-06-28 | 16.9 | 5.73 | 28 | durable_low | no |
| reset_decline | 2 | 2024-10-07 | 2025-01-10 | 2025-01-10 | 31.5 | 10.07 | 65 | durable_low | no |
| failed_breakdown | 3 | 2024-12-20 | 2024-12-20 | 2024-12-23 | 1.0 | 0.35 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-01-10 | 2025-01-10 | 2025-01-15 | 2.1 | 0.89 | 3 | recovered | no |
| reset_decline | 3 | 2025-03-17 | 2025-04-08 | 2025-04-08 | 32.7 | 7.55 | 16 | durable_low | no |
| reset_decline | 1 | 2025-10-02 | 2026-04-07 | 2026-04-07 | 36.8 | 11.78 | 127 | durable_low | no |
| failed_breakdown | 3 | 2025-12-31 | 2025-12-31 | 2026-01-02 | 0.3 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-04-07 | 2026-04-07 | 2026-04-08 | 1.9 | 0.54 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-25 | 2026-06-26 | 2026-07-08 | 5.0 | 1.35 | 8 | recovered | no |

**49 episodes**, 0 censored; by type {'failed_breakdown': 35, 'reset_decline': 11, 'reclaim': 3}; by tier {3: 41, 2: 5, 1: 3}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 2015 | 8% | 5% | 6% | 15% | 0% | 0% | 0% | 67% |
| 2016 | 2% | 0% | 0% | 6% | 42% | 27% | 0% | 23% |
| 2017 | 4% | 0% | 0% | 0% | 22% | 75% | 0% | 0% |
| 2018 | 2% | 0% | 2% | 0% | 25% | 25% | 1% | 44% |
| 2019 | 2% | 0% | 0% | 29% | 26% | 14% | 6% | 22% |
| 2020 | 6% | 0% | 0% | 0% | 46% | 43% | 0% | 4% |
| 2021 | 2% | 30% | 0% | 0% | 9% | 0% | 16% | 42% |
| 2022 | 0% | 86% | 0% | 1% | 0% | 0% | 0% | 13% |
| 2023 | 4% | 0% | 0% | 19% | 15% | 0% | 11% | 51% |
| 2024 | 7% | 0% | 0% | 0% | 48% | 5% | 14% | 26% |
| 2025 | 6% | 0% | 0% | 0% | 75% | 15% | 1% | 3% |
| 2026 | 6% | 6% | 1% | 0% | 25% | 0% | 30% | 31% |

## Episode map

![BABA episode map](BABA.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
