# FFAI — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | stressor — secular decliner (rule-chosen at PR-1, damaged cohort) |
| price plane | `baskets_ohlcv_v1` |
| first print | 2020-09-02 |
| last print | 2026-07-21 |
| sessions | 1476 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | adv2 (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | vol3 |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | store tape ends 17 session(s) before asof; stale-vs-ceased unresolved |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `PREDATES_CALENDAR` — first print 2020-09-02 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.1134 | 49.3 | yes | **unstable** |
| `f1_kaufman_er_126` | F1 | 0.2764 | 98.8 | yes | **unstable** |
| `f1_kaufman_er_252` | F1 | 0.1271 | 84.9 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.6486 | 69.2 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.9181 | 97.6 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.2222 | 2.4 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.1905 | 12.2 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.0000 | 10.9 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0000 | 2.4 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.1841 | 96.1 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.1841 | 58.1 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 0.3333 | 26.3 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 10.0000 | 81.2 | yes |  |
| `f2_ulcer_126` | F2 | 77.0640 | 99.9 | yes |  |
| `f2_ulcer_252` | F2 | 77.5814 | 99.3 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | -0.5058 | 0.7 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | — | — | no |  |
| `f4_ar1_daily_252` | F4 | -0.0942 | 22.1 | yes |  |
| `f4_ar1_weekly_756` | F4 | 0.0370 | 77.4 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.3366 | 99.8 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 1.2587 | 97.5 | yes |  |
| `f4_mr_half_life_252` | F4 | 252.0000 | 96.4 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 5.8750 | 90.9 | yes |  |
| `f5_realized_vol_21` | F5 | 114.7977 | 94.1 | yes |  |
| `f5_realized_vol_63` | F5 | 179.0163 | 99.2 | yes |  |
| `f5_realized_vol_252` | F5 | 133.2595 | 98.3 | yes |  |
| `f5_vol_of_vol_252` | F5 | 54.7989 | 97.2 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.2030 | 91.4 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 6.9823 | 99.7 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | -0.7894 | 0.8 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | -2.0038 | 1.6 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | -7.4980 | 4.0 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0595 | 33.9 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0119 | 25.4 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 7.0000 | 7.3 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 24.0000 | 40.1 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | — | — | no |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.2787 | 59.9 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 1.8460 | 29.1 | yes |  |
| `f8_swing_period_median_1260` | F8 | 6.0000 | 0.2 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.9795 | 91.8 | yes |  |
| `f9_beta_univ_ew_756` | F9 | 2.0863 | 97.2 | yes |  |
| `f9_idio_share_252` | F9 | 0.9265 | 70.2 | yes |  |
| `f9_idio_share_756` | F9 | 0.9618 | 92.9 | yes |  |
| `f10_dollar_adv_63` | F10 | 4.511e+06 | 23.7 | yes |  |
| `f10_dollar_adv_252` | F10 | 7.593e+06 | 34.8 | yes |  |
| `f10_turnover_proxy_252` | F10 | 1.6298 | 90.3 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 77.0 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0234 | 97.2 | yes |  |

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
| `d_f6_gap_share_252` | 0.3574 | 19.2 | yes |
| `d_f6_event_gap_contrib_252` | 0.0615 | 47.1 | yes |
| `d_f6_gap_fill_rate_252` | 0.5924 | 61.4 | yes |
| `d_close_jump_freq_252` | 0.0278 | 51.1 | yes |
| `d_close_jump_drift5_252` | -1.2811 | 1.9 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 2021-09-08 | 2021-09-08 | 2021-09-09 | 0.6 | 0.05 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-10-04 | 2021-10-06 | 2021-10-18 | 14.3 | 1.82 | 10 | recovered | no |
| failed_breakdown | 3 | 2021-12-13 | 2021-12-15 | 2021-12-17 | 11.2 | 0.99 | 4 | recovered | no |
| failed_breakdown | 3 | 2022-05-09 | 2022-05-11 | 2022-05-13 | 25.2 | 1.38 | 4 | recovered | no |
| reset_decline | 1 | 2022-07-15 | 2022-12-07 | 2022-12-07 | 96.7 | 9.66 | 101 | durable_low | no |
| failed_breakdown | 3 | 2022-09-07 | 2022-09-08 | 2022-09-09 | 9.6 | 0.32 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-12-05 | 2022-12-07 | 2022-12-12 | 17.8 | 0.80 | 5 | recovered | no |
| failed_breakdown | 3 | 2023-09-07 | 2023-09-11 | 2023-09-13 | 30.3 | 0.69 | 4 | recovered | no |
| failed_breakdown | 3 | 2023-10-12 | 2023-10-13 | 2023-10-17 | 5.4 | 0.09 | 3 | recovered | no |
| failed_breakdown | 3 | 2023-11-06 | 2023-11-06 | 2023-11-07 | 2.4 | 0.09 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-02-28 | 2024-02-28 | 2024-02-29 | 1.6 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2024-03-19 | 2024-03-19 | 2024-03-21 | 5.2 | 0.12 | 2 | recovered | no |
| failed_breakdown | 3 | 2024-04-02 | 2024-04-05 | 2024-04-09 | 15.2 | 0.42 | 5 | recovered | no |
| failed_breakdown | 3 | 2024-05-02 | 2024-05-02 | 2024-05-07 | 4.8 | 0.14 | 3 | recovered | no |
| failed_breakdown | 3 | 2024-09-24 | 2024-09-25 | 2024-09-26 | 8.5 | 0.22 | 2 | recovered | no |
| failed_breakdown | 3 | 2024-10-04 | 2024-10-08 | 2024-10-10 | 15.1 | 0.53 | 4 | recovered | no |
| failed_breakdown | 3 | 2024-11-27 | 2024-12-03 | 2024-12-09 | 15.1 | 0.84 | 7 | recovered | no |
| failed_breakdown | 3 | 2025-04-16 | 2025-04-16 | 2025-04-24 | 13.5 | 1.20 | 5 | recovered | no |
| reset_decline | 1 | 2025-08-14 | 2025-11-14 | 2025-11-14 | 66.3 | 6.46 | 65 | durable_low | no |
| failed_breakdown | 3 | 2025-09-25 | 2025-09-30 | 2025-10-06 | 19.8 | 1.74 | 7 | recovered | no |
| failed_breakdown | 3 | 2026-03-04 | 2026-03-04 | 2026-03-05 | 1.6 | 0.09 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-03-26 | 2026-03-27 | 2026-03-31 | 10.4 | 0.45 | 3 | recovered | no |
| failed_breakdown | 3 | 2026-04-02 | 2026-04-08 | 2026-04-09 | 10.7 | 0.48 | 4 | recovered | no |

**23 episodes**, 0 censored; by type {'failed_breakdown': 21, 'reset_decline': 2}; by tier {3: 21, 1: 2}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | 2% | 0% | 0% | 0% | 0% | 0% | 0% | 98% |
| 2021 | 12% | 32% | 0% | 0% | 0% | 0% | 0% | 56% |
| 2022 | 0% | 100% | 0% | 0% | 0% | 0% | 0% | 0% |
| 2023 | 2% | 98% | 0% | 0% | 0% | 0% | 0% | 0% |
| 2024 | 4% | 96% | 0% | 0% | 0% | 0% | 0% | 0% |
| 2025 | 2% | 98% | 0% | 0% | 0% | 0% | 0% | 0% |
| 2026 | 0% | 100% | 0% | 0% | 0% | 0% | 0% | 0% |

## Episode map

![FFAI episode map](FFAI.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
