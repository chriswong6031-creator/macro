# GOLD — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | miner neighborhood probe |
| price plane | `baskets_ohlcv_v1` |
| first print | 2014-03-17 |
| last print | 2026-08-13 |
| sessions | 3122 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | adv2 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol2 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

| flag | resolution |
|---|---|
| `symbol_history_note` | continuous Barrick history under the CURRENT symbol — the pre-2018 rows are the ABX era restated, i.e. instrument-level continuity via rename, not a splice. The separate data/baskets/ohlcv/ABX.parquet (2020-09 onward) is a DIFFERENT instrument on Barrick's retired symbol and is excluded from this program; that reuse is unacknowledged in config (reused_ticker_acks / ticker_key_migrations / breadth.ticker_fixups all silent on both symbols) |

**First-print sanity:** `PREDATES_CALENDAR` — first print 2014-03-17 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0467 | 22.0 | yes | **unstable** |
| `f1_kaufman_er_126` | F1 | 0.1398 | 79.4 | yes | **unstable** |
| `f1_kaufman_er_252` | F1 | 0.0905 | 66.6 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.4829 | 53.6 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.5424 | 53.1 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.5952 | 55.2 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.8889 | 75.8 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0873 | 75.3 | yes | **unstable** |
| `f1_new_high_cadence_756` | F1 | 0.0397 | 49.5 | yes | **unstable** |
| `f2_drawdown_median_756` | F2 | 0.0917 | 87.9 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.3818 | 88.5 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.0000 | 66.8 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.6667 | 85.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 11.0000 | 83.3 | yes |  |
| `f2_ulcer_126` | F2 | 31.1546 | 76.2 | yes |  |
| `f2_ulcer_252` | F2 | 29.9603 | 66.6 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 3.7748 | 39.1 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 41.0000 | 83.5 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0076 | 70.3 | yes |  |
| `f4_ar1_weekly_756` | F4 | 0.1121 | 94.0 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 0.9787 | 62.2 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 1.2242 | 96.6 | yes |  |
| `f4_mr_half_life_252` | F4 | 61.3050 | 68.4 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 5.6250 | 89.2 | yes |  |
| `f5_realized_vol_21` | F5 | 40.0804 | 41.2 | yes |  |
| `f5_realized_vol_63` | F5 | 43.5415 | 45.2 | yes |  |
| `f5_realized_vol_252` | F5 | 51.1527 | 55.5 | yes |  |
| `f5_vol_of_vol_252` | F5 | 13.8631 | 52.2 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.1197 | 70.7 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.1635 | 58.4 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.5861 | 84.8 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 1.1327 | 75.3 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 3.4605 | 73.6 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0397 | 11.4 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0357 | 60.1 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 25.0000 | 85.9 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 44.8000 | 62.8 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.3846 | 22.9 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.1471 | 17.7 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 350.0000 | 68.1 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 1.2879 | 2.3 | yes |  |
| `f8_swing_period_median_756` | F8 | 41.0000 | 55.7 | yes |  |
| `f8_swing_period_median_1260` | F8 | 39.5000 | 55.6 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.3222 | 75.2 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 0.9706 | 52.1 | yes |  |
| `f9_idio_share_252` | F9 | 0.7839 | 21.8 | yes |  |
| `f9_idio_share_756` | F9 | 0.8210 | 47.2 | yes |  |
| `f10_dollar_adv_63` | F10 | 1.634e+07 | 43.8 | yes |  |
| `f10_dollar_adv_252` | F10 | 1.794e+07 | 49.2 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.7212 | 12.8 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 57.5 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0091 | 50.6 | yes |  |

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
| `d_f6_gap_share_252` | 0.5193 | 87.3 | yes |
| `d_f6_event_gap_contrib_252` | 0.0538 | 33.5 | yes |
| `d_f6_gap_fill_rate_252` | 0.4649 | 22.8 | yes |
| `d_close_jump_freq_252` | 0.0317 | 68.3 | yes |
| `d_close_jump_drift5_252` | 0.0862 | 48.7 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2014-06-20 | 2014-06-20 | 2014-06-23 | 1.2 | 0.33 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-28 | 2014-10-28 | 2014-10-30 | 1.6 | 0.45 | 2 | recovered | no |
| failed_breakdown | 3 | 2014-11-05 | 2014-11-05 | 2014-11-06 | 0.1 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-11-07 | 2014-11-07 | 2014-11-10 | 0.1 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-11-12 | 2014-11-12 | 2014-11-14 | 1.5 | 0.56 | 2 | recovered | no |
| failed_breakdown | 3 | 2014-12-10 | 2014-12-10 | 2014-12-11 | 0.6 | 0.18 | 1 | recovered | no |
| failed_breakdown | 3 | 2015-08-28 | 2015-08-28 | 2015-08-31 | 0.3 | 0.15 | 1 | recovered | no |
| reset_decline | 2 | 2016-04-26 | 2016-06-22 | 2016-06-22 | 35.5 | 11.20 | 40 | durable_low | no |
| failed_breakdown | 3 | 2016-06-01 | 2016-06-02 | 2016-06-03 | 3.6 | 0.65 | 2 | recovered | no |
| failed_breakdown | 3 | 2016-10-03 | 2016-10-11 | 2016-10-13 | 4.2 | 1.33 | 8 | recovered | no |
| failed_breakdown | 3 | 2016-10-28 | 2016-10-28 | 2016-10-31 | 0.8 | 0.27 | 1 | recovered | no |
| reset_decline | 2 | 2017-02-13 | 2017-05-10 | 2017-05-10 | 29.5 | 10.44 | 60 | durable_low | no |
| failed_breakdown | 3 | 2017-04-21 | 2017-04-21 | 2017-04-24 | 0.3 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-05-08 | 2017-05-10 | 2017-05-19 | 11.0 | 3.39 | 9 | recovered | no |
| failed_breakdown | 3 | 2017-07-12 | 2017-07-12 | 2017-07-13 | 0.6 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-07-14 | 2017-07-14 | 2017-07-17 | 1.1 | 0.21 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-07-19 | 2017-07-19 | 2017-07-20 | 0.3 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-07-25 | 2017-07-25 | 2017-07-26 | 0.1 | 0.02 | 1 | recovered | no |
| reset_decline | 1 | 2017-09-12 | 2018-02-20 | 2018-02-20 | 41.7 | 14.71 | 110 | durable_low | no |
| failed_breakdown | 3 | 2017-10-30 | 2017-10-30 | 2017-10-31 | 0.3 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-11-01 | 2017-11-01 | 2017-11-02 | 2.1 | 0.72 | 1 | recovered | no |
| reclaim | 1 | 2018-03-21 | 2018-08-02 | 2018-08-16 | 39.6 | 16.12 | 93 | failed | no |
| failed_breakdown | 3 | 2018-07-13 | 2018-07-24 | 2018-07-27 | 4.8 | 1.54 | 10 | recovered | no |
| failed_breakdown | 3 | 2018-09-21 | 2018-09-21 | 2018-09-24 | 1.6 | 0.43 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-11-26 | 2018-11-26 | 2018-11-28 | 1.4 | 0.41 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-12-19 | 2018-12-21 | 2019-01-02 | 7.5 | 2.05 | 8 | recovered | no |
| failed_breakdown | 3 | 2019-04-17 | 2019-04-17 | 2019-04-18 | 0.9 | 0.24 | 1 | recovered | no |
| reset_decline | 1 | 2019-08-13 | 2020-01-28 | 2020-01-28 | 45.7 | 13.01 | 115 | durable_low | no |
| failed_breakdown | 3 | 2019-09-18 | 2019-09-19 | 2019-09-20 | 3.4 | 0.75 | 2 | recovered | no |
| failed_breakdown | 3 | 2020-01-28 | 2020-01-28 | 2020-01-29 | 1.9 | 0.44 | 1 | recovered | no |
| reclaim | 3 | 2020-03-20 | 2020-03-26 | 2020-06-25 | 44.3 | 9.87 | 4 | held | no |
| reset_decline | 2 | 2020-10-15 | 2020-12-29 | 2020-12-29 | 29.5 | 6.45 | 51 | durable_low | no |
| failed_breakdown | 3 | 2020-12-29 | 2020-12-29 | 2020-12-30 | 1.7 | 0.26 | 1 | recovered | no |
| reset_decline | 2 | 2021-11-03 | 2022-01-07 | 2022-01-07 | 28.7 | 7.71 | 45 | durable_low | no |
| failed_breakdown | 3 | 2022-01-05 | 2022-01-07 | 2022-01-11 | 2.9 | 0.57 | 4 | recovered | no |
| reset_decline | 2 | 2022-04-20 | 2022-07-06 | 2022-07-06 | 38.4 | 9.70 | 52 | durable_low | no |
| failed_breakdown | 3 | 2022-05-09 | 2022-05-12 | 2022-05-23 | 7.5 | 1.16 | 10 | recovered | no |
| failed_breakdown | 3 | 2022-06-13 | 2022-06-13 | 2022-06-14 | 1.1 | 0.16 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-07-05 | 2022-07-06 | 2022-07-19 | 10.5 | 1.81 | 10 | recovered | no |
| failed_breakdown | 3 | 2022-09-16 | 2022-09-20 | 2022-09-23 | 8.4 | 1.35 | 5 | recovered | no |
| reclaim | 2 | 2022-09-20 | 2022-11-10 | 2022-11-17 | 43.6 | 11.35 | 37 | failed | no |
| reset_decline | 3 | 2023-02-01 | 2023-03-13 | 2023-03-13 | 30.2 | 9.27 | 27 | durable_low | no |
| failed_breakdown | 3 | 2023-02-08 | 2023-02-13 | 2023-02-15 | 8.1 | 1.39 | 5 | recovered | no |
| failed_breakdown | 3 | 2023-03-02 | 2023-03-02 | 2023-03-03 | 0.4 | 0.09 | 1 | recovered | no |
| failed_breakdown | 3 | 2023-03-06 | 2023-03-13 | 2023-03-16 | 4.8 | 1.09 | 8 | recovered | no |
| reset_decline | 1 | 2023-07-26 | 2023-11-09 | 2023-11-09 | 39.9 | 16.64 | 75 | durable_low | no |
| failed_breakdown | 3 | 2023-08-24 | 2023-08-24 | 2023-08-28 | 0.2 | 0.09 | 2 | recovered | no |
| failed_breakdown | 3 | 2023-10-02 | 2023-10-03 | 2023-10-06 | 3.3 | 0.73 | 4 | recovered | no |
| failed_breakdown | 3 | 2024-02-16 | 2024-02-22 | 2024-03-01 | 5.8 | 1.39 | 9 | recovered | no |
| reset_decline | 2 | 2024-05-02 | 2024-07-02 | 2024-07-02 | 21.9 | 5.40 | 41 | durable_low | no |
| failed_breakdown | 3 | 2024-07-02 | 2024-07-02 | 2024-07-03 | 0.2 | 0.05 | 1 | recovered | no |
| reset_decline | 1 | 2024-09-13 | 2024-12-23 | 2024-12-23 | 45.7 | 13.17 | 70 | durable_low | no |
| failed_breakdown | 3 | 2024-12-23 | 2024-12-23 | 2024-12-24 | 1.7 | 0.37 | 1 | recovered | no |
| reclaim | 1 | 2025-03-03 | 2025-09-11 | 2025-12-10 | 43.5 | 19.83 | 133 | held | no |
| failed_breakdown | 3 | 2025-05-21 | 2025-05-22 | 2025-05-27 | 4.3 | 0.83 | 3 | recovered | no |
| failed_breakdown | 3 | 2025-05-29 | 2025-05-30 | 2025-06-02 | 0.5 | 0.09 | 2 | recovered | no |
| reset_decline | 3 | 2026-02-09 | 2026-03-30 | 2026-03-30 | 40.6 | 8.31 | 34 | durable_low | no |
| failed_breakdown | 3 | 2026-07-13 | 2026-07-13 | 2026-07-14 | 1.3 | 0.27 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-07-20 | 2026-07-20 | 2026-07-21 | 1.2 | 0.28 | 1 | recovered | no |

**59 episodes**, 0 censored; by type {'failed_breakdown': 43, 'reset_decline': 12, 'reclaim': 4}; by tier {3: 46, 2: 7, 1: 6}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2014 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 2015 | 0% | 0% | 0% | 0% | 38% | 31% | 0% | 32% |
| 2016 | 0% | 0% | 0% | 0% | 33% | 14% | 0% | 53% |
| 2017 | 4% | 0% | 0% | 0% | 31% | 2% | 22% | 41% |
| 2018 | 0% | 2% | 8% | 12% | 9% | 0% | 17% | 53% |
| 2019 | 2% | 0% | 8% | 0% | 15% | 17% | 19% | 38% |
| 2020 | 8% | 1% | 9% | 45% | 20% | 7% | 2% | 8% |
| 2021 | 4% | 0% | 0% | 0% | 67% | 29% | 0% | 0% |
| 2022 | 0% | 0% | 1% | 13% | 37% | 9% | 12% | 27% |
| 2023 | 2% | 0% | 0% | 12% | 31% | 13% | 22% | 20% |
| 2024 | 4% | 0% | 0% | 0% | 45% | 15% | 12% | 24% |
| 2025 | 2% | 45% | 2% | 30% | 0% | 0% | 2% | 19% |
| 2026 | 0% | 0% | 0% | 31% | 64% | 0% | 0% | 6% |

## Episode map

![GOLD episode map](GOLD.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
