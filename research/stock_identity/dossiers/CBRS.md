# CBRS — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

## Identity

| field | value |
|---|---|
| pilot role | stressor — recent IPO (rule-chosen at PR-1) |
| price plane | `baskets_ohlcv_v1` |
| first print | 2026-05-14 |
| last print | 2026-08-13 |
| sessions | 63 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | UNKNOWN (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | UNKNOWN |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

No reused-ticker, rename, fixup, or delisting flag on this symbol.

**First-print sanity:** `OK` — first print within 0d of priced date 2026-05-14

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | — | — | no |  |
| `f1_kaufman_er_126` | F1 | — | — | no |  |
| `f1_kaufman_er_252` | F1 | — | — | no |  |
| `f1_logprice_r2_126` | F1 | — | — | no |  |
| `f1_logprice_r2_252` | F1 | — | — | no |  |
| `f1_share_above_50dma_252` | F1 | — | — | no |  |
| `f1_share_above_200dma_252` | F1 | — | — | no |  |
| `f1_new_high_cadence_252` | F1 | — | — | no |  |
| `f1_new_high_cadence_756` | F1 | — | — | no |  |
| `f2_drawdown_median_756` | F2 | — | — | no |  |
| `f2_drawdown_p90_756` | F2 | — | — | no |  |
| `f2_resets_per_year_15pct` | F2 | — | — | no |  |
| `f2_resets_per_year_30pct` | F2 | — | — | no |  |
| `f2_time_under_water_median_756` | F2 | — | — | no |  |
| `f2_ulcer_126` | F2 | — | — | no |  |
| `f2_ulcer_252` | F2 | — | — | no |  |
| `f3_post_trough_63d_atr_median` | F3 | — | — | no |  |
| `f3_time_to_50pct_retrace_median` | F3 | — | — | no |  |
| `f4_ar1_daily_252` | F4 | — | — | no |  |
| `f4_ar1_weekly_756` | F4 | — | — | no |  |
| `f4_variance_ratio_k5_756` | F4 | — | — | no |  |
| `f4_variance_ratio_k20_756` | F4 | — | — | no |  |
| `f4_mr_half_life_252` | F4 | — | — | no |  |
| `f4_oscillator_dwell_extreme_252` | F4 | — | — | no |  |
| `f5_realized_vol_21` | F5 | — | — | no |  |
| `f5_realized_vol_63` | F5 | — | — | no |  |
| `f5_realized_vol_252` | F5 | — | — | no |  |
| `f5_vol_of_vol_252` | F5 | — | — | no |  |
| `f5_acf_abs_ret_1_252` | F5 | — | — | no |  |
| `f5_natr_regime_spread_252` | F5 | — | — | no |  |
| `f7_atr_dist_20dma_252` | F7 | — | — | no |  |
| `f7_atr_dist_50dma_252` | F7 | — | — | no |  |
| `f7_atr_dist_200dma_252` | F7 | — | — | no |  |
| `f7_cross_freq_50dma_252` | F7 | — | — | no |  |
| `f7_cross_freq_200dma_252` | F7 | — | — | no |  |
| `f7_dwell_run_above_50dma_252` | F7 | — | — | no |  |
| `f7_dwell_run_above_200dma_252` | F7 | — | — | no |  |
| `f7_bounce_rate_50dma_756` | F7 | — | — | no |  |
| `f8_detrended_acf_peak_1260` | F8 | — | — | no |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | — | — | no |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | — | — | no |  |
| `f8_swing_period_median_1260` | F8 | — | — | no |  |
| `f9_beta_univ_ew_252` | F9 | — | — | no |  |
| `f9_beta_univ_ew_756` | F9 | — | — | no |  |
| `f9_idio_share_252` | F9 | — | — | no |  |
| `f9_idio_share_756` | F9 | — | — | no |  |
| `f10_dollar_adv_63` | F10 | — | — | no |  |
| `f10_dollar_adv_252` | F10 | — | — | no |  |
| `f10_turnover_proxy_252` | F10 | — | — | no |  |
| `f10_amihud_252` | F10 | — | — | no |  |
| `f10_cs_spread_252` | F10 | — | — | no |  |

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
| `d_f6_gap_share_252` | — | — | no |
| `d_f6_event_gap_contrib_252` | — | — | no |
| `d_f6_gap_fill_rate_252` | — | — | no |
| `d_close_jump_freq_252` | — | — | no |
| `d_close_jump_drift5_252` | — | — | no |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

_no episodes catalogued for this name_

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |

## Episode map

![CBRS episode map](CBRS.svg)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
