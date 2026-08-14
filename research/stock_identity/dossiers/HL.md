# HL — Identity Atlas v0 dossier

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
| sector stratum | Materials |
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
| `f1_kaufman_er_63` | F1 | 0.0964 | 43.2 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0787 | 51.4 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0651 | 51.0 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.6998 | 74.9 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.2241 | 26.7 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.5794 | 51.9 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.7897 | 65.1 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.1627 | 95.6 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0701 | 79.4 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0425 | 61.4 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.2469 | 72.8 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 2.3333 | 96.2 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.6667 | 85.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 3.5000 | 12.6 | yes |  |
| `f2_ulcer_126` | F2 | 43.0706 | 89.9 | yes |  |
| `f2_ulcer_252` | F2 | 32.2041 | 70.5 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 2.9778 | 24.5 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 24.0000 | 51.6 | yes |  |
| `f4_ar1_daily_252` | F4 | -0.0315 | 49.9 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.1359 | 11.1 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0393 | 82.8 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8212 | 38.2 | yes |  |
| `f4_mr_half_life_252` | F4 | 27.8972 | 33.3 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 4.2500 | 73.4 | yes |  |
| `f5_realized_vol_21` | F5 | 65.3896 | 72.1 | yes |  |
| `f5_realized_vol_63` | F5 | 68.2838 | 74.4 | yes |  |
| `f5_realized_vol_252` | F5 | 72.2316 | 78.4 | yes |  |
| `f5_vol_of_vol_252` | F5 | 14.6876 | 55.5 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | -0.0213 | 10.4 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.4220 | 68.7 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.7241 | 92.9 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 1.4639 | 86.2 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 4.6569 | 85.3 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0317 | 5.5 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0278 | 49.7 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 29.2000 | 90.7 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 49.7500 | 66.4 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.4737 | 40.2 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.2480 | 50.1 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.5693 | 72.9 | yes |  |
| `f8_swing_period_median_756` | F8 | 16.0000 | 17.0 | yes |  |
| `f8_swing_period_median_1260` | F8 | 21.5000 | 27.9 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.6068 | 84.9 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 1.1970 | 72.4 | yes |  |
| `f9_idio_share_252` | F9 | 0.8399 | 37.7 | yes |  |
| `f9_idio_share_756` | F9 | 0.8454 | 55.2 | yes |  |
| `f10_dollar_adv_63` | F10 | 4.250e+08 | 90.4 | yes |  |
| `f10_dollar_adv_252` | F10 | 3.284e+08 | 88.3 | yes |  |
| `f10_turnover_proxy_252` | F10 | 1.7695 | 92.7 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 20.4 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0105 | 60.1 | yes |  |

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
| `d_f6_gap_share_252` | 0.6908 | 98.6 | yes |
| `d_f6_event_gap_contrib_252` | 0.0682 | 58.1 | yes |
| `d_f6_gap_fill_rate_252` | 0.4286 | 15.4 | yes |
| `d_close_jump_freq_252` | 0.0357 | 81.5 | yes |
| `d_close_jump_drift5_252` | 0.6746 | 81.9 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2014-04-21 | 2014-04-21 | 2014-04-22 | 0.9 | 0.21 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-09-19 | 2014-09-22 | 2014-09-23 | 4.0 | 1.28 | 2 | recovered | no |
| failed_breakdown | 3 | 2014-10-22 | 2014-10-22 | 2014-10-23 | 0.4 | 0.07 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-27 | 2014-10-27 | 2014-10-28 | 0.4 | 0.07 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-30 | 2014-10-31 | 2014-11-03 | 4.8 | 0.80 | 2 | recovered | no |
| failed_breakdown | 3 | 2014-11-04 | 2014-11-05 | 2014-11-07 | 6.4 | 1.01 | 3 | recovered | no |
| reset_decline | 3 | 2015-01-22 | 2015-03-10 | 2015-03-10 | 22.1 | 4.46 | 32 | durable_low | no |
| failed_breakdown | 3 | 2015-06-16 | 2015-06-16 | 2015-06-17 | 1.0 | 0.32 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-08-03 | 2015-08-07 | 2015-08-10 | 10.2 | 1.49 | 5 | recovered | no |
| failed_breakdown | 3 | 2015-08-26 | 2015-08-26 | 2015-08-27 | 2.0 | 0.22 | 1 | recovered | no |
| reclaim | 2 | 2015-12-14 | 2016-02-17 | 2016-05-17 | 44.8 | 14.50 | 43 | held | no |
| reset_decline | 2 | 2016-08-10 | 2016-10-11 | 2016-10-11 | 28.3 | 6.69 | 43 | durable_low | no |
| failed_breakdown | 3 | 2016-10-04 | 2016-10-11 | 2016-10-17 | 4.3 | 0.74 | 9 | recovered | no |
| reset_decline | 3 | 2016-11-09 | 2016-12-22 | 2016-12-22 | 29.1 | 6.18 | 30 | durable_low | no |
| failed_breakdown | 3 | 2017-06-15 | 2017-06-15 | 2017-06-16 | 0.1 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-07-03 | 2017-07-03 | 2017-07-10 | 2.8 | 0.72 | 4 | recovered | no |
| failed_breakdown | 3 | 2017-08-07 | 2017-08-08 | 2017-08-09 | 1.4 | 0.33 | 2 | recovered | no |
| failed_breakdown | 3 | 2017-08-15 | 2017-08-15 | 2017-08-16 | 2.3 | 0.58 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-11-29 | 2017-12-07 | 2017-12-13 | 7.7 | 1.81 | 10 | recovered | no |
| failed_breakdown | 3 | 2018-03-19 | 2018-03-20 | 2018-03-21 | 6.2 | 1.39 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-06-27 | 2018-06-28 | 2018-07-05 | 3.6 | 1.14 | 5 | recovered | no |
| failed_breakdown | 3 | 2018-07-11 | 2018-07-11 | 2018-07-12 | 0.6 | 0.18 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-07-17 | 2018-07-17 | 2018-07-18 | 1.8 | 0.54 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-07-19 | 2018-07-20 | 2018-07-23 | 4.2 | 1.16 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-08-14 | 2018-08-16 | 2018-08-24 | 8.4 | 1.58 | 8 | recovered | no |
| failed_breakdown | 3 | 2018-11-12 | 2018-11-13 | 2018-11-15 | 7.5 | 1.11 | 3 | recovered | no |
| reclaim | 1 | 2018-11-23 | 2019-10-24 | 2020-01-27 | 43.0 | 11.62 | 230 | held | no |
| failed_breakdown | 3 | 2019-03-01 | 2019-03-01 | 2019-03-04 | 0.4 | 0.07 | 1 | recovered | no |
| failed_breakdown | 3 | 2019-03-06 | 2019-03-06 | 2019-03-08 | 2.5 | 0.39 | 2 | recovered | no |
| failed_breakdown | 3 | 2019-05-28 | 2019-05-28 | 2019-06-03 | 8.7 | 1.12 | 4 | recovered | no |
| reset_decline | 3 | 2020-02-07 | 2020-03-18 | 2020-03-18 | 53.0 | 10.86 | 27 | durable_low | no |
| reset_decline | 2 | 2020-08-06 | 2020-10-30 | 2020-10-30 | 31.1 | 5.90 | 60 | durable_low | no |
| failed_breakdown | 3 | 2020-10-28 | 2020-10-30 | 2020-11-02 | 3.0 | 0.60 | 3 | recovered | no |
| reset_decline | 3 | 2021-01-06 | 2021-01-27 | 2021-01-27 | 31.1 | 6.23 | 14 | durable_low | no |
| reset_decline | 1 | 2021-06-02 | 2022-01-27 | 2022-01-27 | 49.5 | 10.59 | 166 | durable_low | no |
| failed_breakdown | 3 | 2021-08-19 | 2021-08-19 | 2021-08-23 | 2.5 | 0.45 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-09-20 | 2021-09-23 | 2021-09-27 | 1.6 | 0.33 | 5 | recovered | no |
| failed_breakdown | 3 | 2021-10-05 | 2021-10-05 | 2021-10-07 | 0.9 | 0.21 | 2 | recovered | no |
| failed_breakdown | 3 | 2021-10-12 | 2021-10-12 | 2021-10-13 | 4.7 | 1.05 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-12-10 | 2021-12-15 | 2021-12-21 | 7.0 | 1.30 | 7 | recovered | no |
| failed_breakdown | 3 | 2022-01-27 | 2022-01-27 | 2022-01-31 | 1.3 | 0.22 | 2 | recovered | no |
| reset_decline | 2 | 2022-04-13 | 2022-07-11 | 2022-07-11 | 51.0 | 9.99 | 59 | durable_low | no |
| failed_breakdown | 3 | 2022-06-23 | 2022-06-23 | 2022-06-24 | 1.8 | 0.26 | 1 | recovered | no |
| reclaim | 2 | 2022-08-22 | 2022-11-10 | 2022-11-17 | 44.0 | 13.22 | 57 | failed | no |
| failed_breakdown | 3 | 2022-09-26 | 2022-09-27 | 2022-09-28 | 2.1 | 0.30 | 2 | recovered | no |
| reset_decline | 3 | 2023-01-25 | 2023-02-24 | 2023-02-24 | 22.9 | 5.15 | 21 | durable_low | no |
| reset_decline | 1 | 2023-04-13 | 2023-10-05 | 2023-10-05 | 47.7 | 14.05 | 121 | durable_low | no |
| failed_breakdown | 3 | 2023-06-20 | 2023-06-23 | 2023-07-03 | 3.9 | 1.06 | 9 | recovered | no |
| failed_breakdown | 3 | 2023-09-07 | 2023-09-13 | 2023-09-14 | 2.8 | 0.54 | 5 | recovered | no |
| reclaim | 1 | 2023-11-09 | 2024-03-27 | 2024-06-27 | 43.5 | 14.59 | 94 | held | no |
| reset_decline | 2 | 2024-05-20 | 2024-08-05 | 2024-08-05 | 23.8 | 5.22 | 52 | durable_low | no |
| failed_breakdown | 3 | 2024-08-05 | 2024-08-05 | 2024-08-06 | 0.6 | 0.11 | 1 | recovered | no |
| reset_decline | 2 | 2024-10-22 | 2024-12-30 | 2024-12-30 | 35.3 | 9.06 | 47 | durable_low | no |
| failed_breakdown | 3 | 2024-12-02 | 2024-12-02 | 2024-12-03 | 0.1 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-04-04 | 2025-04-08 | 2025-04-09 | 7.0 | 1.22 | 3 | recovered | no |
| failed_breakdown | 3 | 2025-05-02 | 2025-05-02 | 2025-05-05 | 3.6 | 0.56 | 1 | recovered | no |
| reset_decline | 1 | 2026-01-23 | 2026-06-10 | 2026-06-10 | 55.8 | 10.47 | 95 | durable_low | no |
| failed_breakdown | 3 | 2026-03-18 | 2026-03-26 | 2026-04-01 | 8.9 | 1.03 | 10 | recovered | no |
| failed_breakdown | 3 | 2026-05-05 | 2026-05-05 | 2026-05-06 | 0.8 | 0.14 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-05-19 | 2026-05-19 | 2026-05-20 | 4.0 | 0.53 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-05 | 2026-06-10 | 2026-06-15 | 14.1 | 2.23 | 6 | recovered | no |

**61 episodes**, 0 censored; by type {'failed_breakdown': 44, 'reset_decline': 13, 'reclaim': 4}; by tier {3: 49, 2: 7, 1: 5}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 2015 | 0% | 7% | 22% | 0% | 40% | 4% | 0% | 27% |
| 2016 | 0% | 8% | 0% | 47% | 35% | 6% | 0% | 4% |
| 2017 | 0% | 3% | 7% | 0% | 20% | 0% | 0% | 70% |
| 2018 | 0% | 32% | 4% | 0% | 0% | 0% | 12% | 52% |
| 2019 | 0% | 31% | 0% | 19% | 0% | 0% | 7% | 43% |
| 2020 | 0% | 6% | 0% | 63% | 25% | 2% | 0% | 4% |
| 2021 | 2% | 4% | 0% | 0% | 42% | 14% | 0% | 38% |
| 2022 | 0% | 28% | 2% | 28% | 0% | 0% | 6% | 35% |
| 2023 | 0% | 3% | 9% | 27% | 24% | 0% | 8% | 28% |
| 2024 | 0% | 8% | 0% | 43% | 19% | 7% | 1% | 22% |
| 2025 | 2% | 0% | 0% | 0% | 42% | 28% | 12% | 17% |
| 2026 | 0% | 37% | 0% | 26% | 25% | 10% | 0% | 3% |

## Episode map

![HL episode map](HL.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
