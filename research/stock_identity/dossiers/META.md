# META — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | stressor — known epoch-changer |
| price plane | `stocks_tr_v1` |
| first print | 2012-05-18 |
| last print | 2026-08-13 |
| sessions | 3579 |
| `open` available | False |
| sector stratum | Communication Services |
| cap stratum | adv3 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol2 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 2012-05-18 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0277 | 13.3 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0498 | 34.9 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0726 | 56.5 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.1312 | 22.1 | yes | **unstable** |
| `f1_logprice_r2_252` | F1 | 0.5702 | 55.3 | yes | **unstable** |
| `f1_share_above_50dma_252` | F1 | 0.3849 | 15.9 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.2738 | 18.1 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0000 | 10.9 | yes | **unstable** |
| `f1_new_high_cadence_756` | F1 | 0.0847 | 87.7 | yes | **unstable** |
| `f2_drawdown_median_756` | F2 | 0.0192 | 21.2 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.1022 | 23.8 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.0000 | 66.8 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.3333 | 64.1 | yes |  |
| `f2_time_under_water_median_756` | F2 | 4.0000 | 21.5 | yes |  |
| `f2_ulcer_126` | F2 | 18.1186 | 51.8 | yes |  |
| `f2_ulcer_252` | F2 | 18.8657 | 45.0 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 7.1748 | 92.0 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 18.5000 | 30.0 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.0273 | 78.3 | yes |  |
| `f4_ar1_weekly_756` | F4 | 0.0323 | 75.7 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 0.9004 | 28.5 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8068 | 35.2 | yes |  |
| `f4_mr_half_life_252` | F4 | 15.8837 | 11.9 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 4.7500 | 81.1 | yes |  |
| `f5_realized_vol_21` | F5 | 44.2241 | 47.8 | yes |  |
| `f5_realized_vol_63` | F5 | 46.2271 | 48.9 | yes |  |
| `f5_realized_vol_252` | F5 | 38.4259 | 37.9 | yes |  |
| `f5_vol_of_vol_252` | F5 | 11.9634 | 44.6 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.0679 | 47.1 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 0.8736 | 41.4 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | -0.3331 | 9.8 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | -0.6502 | 16.6 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | -0.6555 | 30.2 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.1151 | 91.3 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0357 | 60.1 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 6.4667 | 5.6 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 13.8000 | 21.5 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.5909 | 67.8 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.2214 | 40.0 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.4058 | 61.8 | yes |  |
| `f8_swing_period_median_756` | F8 | 40.0000 | 54.0 | yes |  |
| `f8_swing_period_median_1260` | F8 | 33.5000 | 47.1 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 0.6776 | 32.0 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 0.6980 | 26.2 | yes |  |
| `f9_idio_share_252` | F9 | 0.8994 | 60.2 | yes |  |
| `f9_idio_share_756` | F9 | 0.8501 | 56.8 | yes |  |
| `f10_dollar_adv_63` | F10 | 9.916e+09 | 99.6 | yes |  |
| `f10_dollar_adv_252` | F10 | 8.931e+09 | 99.7 | yes |  |
| `f10_turnover_proxy_252` | F10 | 1.0035 | 48.4 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 0.3 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0054 | 10.9 | yes |  |

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
| `d_close_jump_drift5_252` | 0.7664 | 84.5 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2012-08-31 | 2012-09-04 | 2012-09-11 | 6.9 | 1.37 | 6 | recovered | no |
| reset_decline | 2 | 2013-01-28 | 2013-06-05 | 2013-06-05 | 29.5 | 9.16 | 89 | durable_low | no |
| failed_breakdown | 3 | 2013-03-20 | 2013-03-25 | 2013-03-27 | 3.0 | 0.90 | 5 | recovered | no |
| reset_decline | 3 | 2013-10-18 | 2013-11-25 | 2013-11-25 | 17.3 | 5.58 | 26 | durable_low | no |
| reset_decline | 3 | 2014-03-10 | 2014-04-28 | 2014-04-28 | 22.1 | 7.58 | 34 | durable_low | no |
| failed_breakdown | 3 | 2014-04-28 | 2014-04-28 | 2014-04-29 | 1.1 | 0.22 | 1 | recovered | no |
| reset_decline | 3 | 2015-07-21 | 2015-08-24 | 2015-08-24 | 16.6 | 8.03 | 24 | durable_low | no |
| failed_breakdown | 3 | 2016-01-13 | 2016-01-13 | 2016-01-14 | 1.6 | 0.60 | 1 | recovered | no |
| failed_breakdown | 3 | 2016-01-15 | 2016-01-21 | 2016-01-22 | 1.3 | 0.42 | 4 | recovered | no |
| failed_breakdown | 3 | 2016-11-03 | 2016-11-03 | 2016-11-08 | 2.7 | 1.67 | 3 | recovered | no |
| failed_breakdown | 3 | 2016-11-11 | 2016-11-14 | 2016-11-21 | 4.1 | 1.64 | 6 | recovered | no |
| failed_breakdown | 3 | 2016-12-30 | 2016-12-30 | 2017-01-03 | 0.0 | 0.01 | 1 | recovered | no |
| reset_decline | 2 | 2018-02-01 | 2018-03-27 | 2018-03-27 | 21.2 | 11.14 | 37 | durable_low | no |
| reset_decline | 1 | 2018-07-25 | 2018-12-24 | 2018-12-24 | 43.0 | 24.81 | 105 | durable_low | no |
| failed_breakdown | 3 | 2018-07-30 | 2018-07-30 | 2018-08-02 | 1.7 | 0.44 | 3 | recovered | no |
| failed_breakdown | 3 | 2018-10-02 | 2018-10-02 | 2018-10-03 | 0.6 | 0.23 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-10-04 | 2018-10-10 | 2018-10-17 | 5.0 | 1.86 | 9 | recovered | no |
| failed_breakdown | 3 | 2018-10-24 | 2018-10-29 | 2018-10-31 | 6.1 | 2.12 | 5 | recovered | no |
| failed_breakdown | 3 | 2018-11-12 | 2018-11-12 | 2018-11-13 | 0.4 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 2018-12-21 | 2018-12-24 | 2018-12-26 | 5.7 | 1.40 | 2 | recovered | no |
| reclaim | 2 | 2018-12-21 | 2019-03-04 | 2019-03-18 | 43.0 | 17.51 | 47 | failed | no |
| reset_decline | 3 | 2019-05-03 | 2019-06-03 | 2019-06-03 | 16.0 | 7.60 | 20 | durable_low | no |
| failed_breakdown | 3 | 2019-09-27 | 2019-09-27 | 2019-09-30 | 0.4 | 0.15 | 1 | recovered | no |
| failed_breakdown | 3 | 2019-10-01 | 2019-10-02 | 2019-10-03 | 1.4 | 0.60 | 2 | recovered | no |
| reset_decline | 3 | 2020-01-29 | 2020-03-16 | 2020-03-16 | 34.6 | 21.72 | 32 | durable_low | no |
| failed_breakdown | 3 | 2020-02-27 | 2020-02-27 | 2020-03-02 | 2.2 | 0.83 | 2 | recovered | no |
| failed_breakdown | 3 | 2020-03-03 | 2020-03-03 | 2020-03-04 | 2.0 | 0.65 | 1 | recovered | no |
| reclaim | 3 | 2020-03-23 | 2020-04-29 | 2020-07-29 | 33.7 | 6.88 | 26 | held | no |
| reset_decline | 3 | 2020-08-26 | 2020-09-21 | 2020-09-21 | 18.3 | 6.75 | 17 | durable_low | no |
| failed_breakdown | 3 | 2021-01-11 | 2021-01-14 | 2021-01-20 | 6.0 | 2.08 | 6 | recovered | no |
| reset_decline | 1 | 2021-09-07 | 2022-06-22 | 2022-06-22 | 59.2 | 32.93 | 199 | durable_low | no |
| failed_breakdown | 3 | 2021-10-26 | 2021-10-27 | 2021-11-01 | 3.6 | 1.34 | 4 | recovered | no |
| failed_breakdown | 3 | 2021-12-01 | 2021-12-03 | 2021-12-06 | 1.7 | 0.55 | 3 | recovered | no |
| failed_breakdown | 3 | 2022-01-21 | 2022-01-21 | 2022-01-24 | 1.2 | 0.35 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-01-25 | 2022-01-26 | 2022-01-31 | 2.8 | 0.75 | 4 | recovered | no |
| failed_breakdown | 3 | 2022-02-18 | 2022-02-23 | 2022-02-25 | 4.5 | 0.71 | 4 | recovered | no |
| failed_breakdown | 3 | 2022-03-07 | 2022-03-07 | 2022-03-09 | 5.5 | 1.03 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-03-14 | 2022-03-14 | 2022-03-15 | 0.4 | 0.08 | 1 | recovered | no |
| reclaim | 1 | 2022-04-18 | 2023-02-01 | 2023-05-03 | 44.9 | 23.06 | 199 | held | no |
| failed_breakdown | 3 | 2022-04-22 | 2022-04-22 | 2022-04-25 | 1.4 | 0.28 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-04-26 | 2022-04-27 | 2022-04-28 | 5.0 | 1.06 | 2 | recovered | no |
| reset_decline | 3 | 2024-04-05 | 2024-04-30 | 2024-04-30 | 18.4 | 7.21 | 17 | durable_low | no |
| failed_breakdown | 3 | 2024-04-30 | 2024-04-30 | 2024-05-01 | 0.6 | 0.12 | 1 | recovered | no |
| reset_decline | 3 | 2024-07-05 | 2024-07-25 | 2024-07-25 | 16.0 | 7.71 | 14 | durable_low | no |
| reset_decline | 2 | 2025-02-14 | 2025-04-21 | 2025-04-21 | 34.2 | 14.31 | 44 | durable_low | no |
| failed_breakdown | 3 | 2025-03-18 | 2025-03-18 | 2025-03-20 | 0.4 | 0.10 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-03-28 | 2025-03-31 | 2025-04-01 | 1.0 | 0.26 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-04-03 | 2025-04-04 | 2025-04-09 | 12.4 | 3.14 | 4 | recovered | no |
| failed_breakdown | 3 | 2025-04-16 | 2025-04-21 | 2025-04-23 | 4.0 | 0.62 | 4 | recovered | no |
| reset_decline | 2 | 2025-08-12 | 2025-11-20 | 2025-11-20 | 25.4 | 10.83 | 71 | durable_low | no |
| failed_breakdown | 3 | 2025-11-17 | 2025-11-20 | 2025-11-24 | 3.3 | 1.00 | 5 | recovered | no |
| failed_breakdown | 3 | 2026-03-20 | 2026-03-20 | 2026-03-23 | 1.6 | 0.55 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-03-24 | 2026-03-24 | 2026-03-25 | 0.1 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-03-26 | 2026-03-27 | 2026-04-08 | 11.3 | 3.91 | 8 | recovered | no |
| failed_breakdown | 3 | 2026-07-30 | 2026-07-30 | 2026-07-31 | 0.7 | 0.17 | 1 | recovered | no |

**55 episodes**, 0 censored; by type {'failed_breakdown': 38, 'reset_decline': 14, 'reclaim': 3}; by tier {3: 47, 2: 5, 1: 3}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `close_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2012 | 6% | 0% | 0% | 0% | 0% | 0% | 0% | 94% |
| 2013 | 4% | 0% | 0% | 0% | 19% | 26% | 0% | 50% |
| 2014 | 4% | 0% | 0% | 0% | 43% | 53% | 0% | 0% |
| 2015 | 2% | 0% | 0% | 0% | 23% | 75% | 0% | 0% |
| 2016 | 10% | 0% | 0% | 0% | 19% | 62% | 6% | 4% |
| 2017 | 10% | 0% | 0% | 0% | 2% | 88% | 1% | 0% |
| 2018 | 10% | 0% | 2% | 0% | 8% | 33% | 6% | 41% |
| 2019 | 6% | 0% | 0% | 27% | 34% | 17% | 0% | 15% |
| 2020 | 10% | 0% | 0% | 34% | 28% | 13% | 1% | 13% |
| 2021 | 8% | 0% | 0% | 0% | 44% | 42% | 0% | 7% |
| 2022 | 10% | 70% | 11% | 0% | 1% | 0% | 0% | 8% |
| 2023 | 4% | 8% | 0% | 46% | 18% | 23% | 0% | 0% |
| 2024 | 6% | 0% | 0% | 0% | 23% | 71% | 0% | 0% |
| 2025 | 8% | 0% | 0% | 0% | 32% | 42% | 12% | 7% |
| 2026 | 13% | 0% | 0% | 0% | 6% | 0% | 30% | 51% |

## Episode map

![META episode map](META.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
