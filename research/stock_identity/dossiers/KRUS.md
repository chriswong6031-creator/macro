# KRUS — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | operator core |
| price plane | `baskets_ohlcv_v1` |
| first print | 2019-08-01 |
| last print | 2026-08-13 |
| sessions | 1768 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | adv2 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol3 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 2019-08-01 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0356 | 16.8 | yes | **unstable** |
| `f1_kaufman_er_126` | F1 | 0.0941 | 59.8 | yes | **unstable** |
| `f1_kaufman_er_252` | F1 | 0.0596 | 47.0 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.6607 | 70.6 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.2996 | 33.0 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.2738 | 5.2 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.2500 | 16.2 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0000 | 10.9 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0053 | 8.8 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0737 | 82.2 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.2967 | 80.3 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 0.3333 | 26.3 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.3333 | 64.1 | yes |  |
| `f2_time_under_water_median_756` | F2 | 9.5000 | 79.6 | yes |  |
| `f2_ulcer_126` | F2 | 31.2242 | 76.4 | yes |  |
| `f2_ulcer_252` | F2 | 41.0228 | 81.6 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 7.1243 | 91.7 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 37.5000 | 80.8 | yes |  |
| `f4_ar1_daily_252` | F4 | 0.1349 | 98.0 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.0682 | 30.7 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0434 | 83.7 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.9740 | 72.8 | yes |  |
| `f4_mr_half_life_252` | F4 | 22.5920 | 24.6 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 5.0000 | 83.9 | yes |  |
| `f5_realized_vol_21` | F5 | 42.4568 | 45.1 | yes |  |
| `f5_realized_vol_63` | F5 | 59.2422 | 65.7 | yes |  |
| `f5_realized_vol_252` | F5 | 62.1192 | 68.5 | yes |  |
| `f5_vol_of_vol_252` | F5 | 15.3396 | 58.0 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.1534 | 81.7 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.4758 | 70.5 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | -0.3179 | 10.5 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | -0.9166 | 12.0 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | -2.0945 | 20.2 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0595 | 33.9 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0516 | 77.5 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 8.6250 | 15.6 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 9.0000 | 12.0 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.2000 | 5.5 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.5274 | 98.8 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 168.0000 | 64.1 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 2.7921 | 83.6 | yes |  |
| `f8_swing_period_median_1260` | F8 | 18.0000 | 20.5 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.2939 | 73.9 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 1.5266 | 87.8 | yes |  |
| `f9_idio_share_252` | F9 | 0.8596 | 45.0 | yes |  |
| `f9_idio_share_756` | F9 | 0.7751 | 34.6 | yes |  |
| `f10_dollar_adv_63` | F10 | 1.484e+07 | 42.4 | yes |  |
| `f10_dollar_adv_252` | F10 | 1.640e+07 | 47.8 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.6345 | 7.4 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 56.1 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0140 | 78.0 | yes |  |

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
| `d_f6_gap_share_252` | 0.2840 | 2.8 | yes |
| `d_f6_event_gap_contrib_252` | 0.0377 | 6.2 | yes |
| `d_f6_gap_fill_rate_252` | 0.7206 | 90.0 | yes |
| `d_close_jump_freq_252` | 0.0198 | 17.3 | yes |
| `d_close_jump_drift5_252` | 0.5311 | 74.8 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2020-02-14 | 2020-02-14 | 2020-02-18 | 0.6 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-03-12 | 2020-03-18 | 2020-03-26 | 61.8 | 6.42 | 10 | recovered | no |
| reclaim | 1 | 2020-07-07 | 2020-11-06 | 2021-02-09 | 65.0 | 14.87 | 87 | held | no |
| failed_breakdown | 3 | 2020-07-23 | 2020-07-28 | 2020-07-29 | 9.4 | 0.98 | 4 | recovered | no |
| failed_breakdown | 3 | 2021-10-26 | 2021-10-26 | 2021-11-01 | 3.7 | 0.63 | 4 | recovered | no |
| reset_decline | 2 | 2021-11-17 | 2022-01-27 | 2022-01-27 | 49.8 | 9.28 | 48 | durable_low | no |
| failed_breakdown | 3 | 2022-01-26 | 2022-01-27 | 2022-01-28 | 5.8 | 0.48 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-05-18 | 2022-05-20 | 2022-05-26 | 5.7 | 0.58 | 6 | recovered | no |
| reset_decline | 1 | 2022-08-15 | 2023-01-06 | 2023-01-06 | 58.3 | 13.25 | 100 | durable_low | no |
| failed_breakdown | 3 | 2022-11-09 | 2022-11-09 | 2022-11-10 | 1.6 | 0.20 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-11-17 | 2022-11-18 | 2022-11-21 | 0.8 | 0.09 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-12-07 | 2022-12-07 | 2022-12-08 | 0.1 | 0.02 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-12-09 | 2022-12-09 | 2022-12-13 | 1.2 | 0.20 | 2 | recovered | no |
| failed_breakdown | 3 | 2023-01-06 | 2023-01-06 | 2023-01-10 | 15.1 | 2.18 | 2 | recovered | no |
| reset_decline | 1 | 2023-07-13 | 2023-11-10 | 2023-11-10 | 52.0 | 11.80 | 85 | durable_low | no |
| failed_breakdown | 3 | 2023-10-13 | 2023-10-13 | 2023-10-17 | 4.1 | 0.76 | 2 | recovered | no |
| failed_breakdown | 3 | 2023-10-30 | 2023-11-01 | 2023-11-03 | 7.7 | 1.47 | 4 | recovered | no |
| failed_breakdown | 3 | 2023-11-09 | 2023-11-10 | 2023-11-14 | 7.8 | 1.20 | 3 | recovered | no |
| reset_decline | 1 | 2024-03-27 | 2024-08-05 | 2024-08-05 | 59.3 | 13.62 | 89 | durable_low | no |
| failed_breakdown | 3 | 2024-08-05 | 2024-08-05 | 2024-08-06 | 0.6 | 0.07 | 1 | recovered | no |
| reset_decline | 1 | 2024-11-29 | 2025-04-08 | 2025-04-08 | 61.2 | 12.48 | 87 | durable_low | no |
| failed_breakdown | 3 | 2025-02-06 | 2025-02-06 | 2025-02-10 | 1.9 | 0.29 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-03-11 | 2025-03-13 | 2025-03-24 | 11.1 | 1.33 | 9 | recovered | no |
| failed_breakdown | 3 | 2025-04-03 | 2025-04-08 | 2025-04-09 | 17.0 | 2.20 | 4 | recovered | no |
| reset_decline | 1 | 2025-07-23 | 2025-11-20 | 2025-11-20 | 55.5 | 11.52 | 85 | durable_low | no |
| failed_breakdown | 3 | 2025-10-08 | 2025-10-08 | 2025-10-09 | 0.6 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-10-10 | 2025-10-10 | 2025-10-14 | 3.9 | 0.72 | 2 | recovered | no |
| failed_breakdown | 3 | 2025-10-30 | 2025-10-30 | 2025-10-31 | 1.6 | 0.24 | 1 | recovered | no |
| failed_breakdown | 3 | 2025-11-03 | 2025-11-03 | 2025-11-04 | 1.4 | 0.22 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-04-10 | 2026-04-10 | 2026-04-14 | 1.2 | 0.14 | 2 | recovered | no |
| failed_breakdown | 3 | 2026-04-28 | 2026-04-28 | 2026-05-01 | 3.1 | 0.39 | 3 | recovered | no |
| failed_breakdown | 3 | 2026-05-12 | 2026-05-14 | 2026-05-20 | 10.1 | 1.51 | 6 | recovered | no |
| failed_breakdown | 3 | 2026-06-02 | 2026-06-03 | 2026-06-12 | 8.3 | 1.17 | 8 | recovered | no |

**33 episodes**, 0 censored; by type {'failed_breakdown': 26, 'reset_decline': 6, 'reclaim': 1}; by tier {3: 26, 1: 6, 2: 1}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 2020 | 0% | 30% | 9% | 13% | 0% | 0% | 0% | 49% |
| 2021 | 0% | 0% | 0% | 39% | 49% | 12% | 0% | 0% |
| 2022 | 0% | 19% | 0% | 60% | 4% | 1% | 2% | 14% |
| 2023 | 2% | 5% | 0% | 22% | 18% | 2% | 30% | 21% |
| 2024 | 2% | 16% | 0% | 57% | 7% | 0% | 3% | 14% |
| 2025 | 0% | 40% | 0% | 29% | 0% | 0% | 12% | 19% |
| 2026 | 0% | 27% | 0% | 25% | 0% | 0% | 24% | 24% |

## Episode map

![KRUS episode map](KRUS.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
