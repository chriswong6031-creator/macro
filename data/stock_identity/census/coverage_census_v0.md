# Identity Atlas v0 — coverage census (W1 / PR-1)

Descriptive coverage only. Zero authority: nothing here ranks, sizes, gates, originates a signal, or escalates. No expert data exists in W1 by law (masterplan §16.9), so fires-per-name-year and attribution-rate columns are absent rather than empty — they are PR-2/PR-3 additions.

## Scope

- **asof**: 2026-08-13
- **Universe (evaluated)**: 2781 names
- **Excluded as blind evaluation arm**: 229 names — the blind arm is excluded entirely from this census until PR-3; its members appear nowhere below, not even as counts by stratum.
- **Excluded by ticker-identity hygiene**: 1 names (ABX)
- **Census population**: 2527 names
- **Survivor-only cohort**: the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Every cohort-level statement below is therefore a statement about survivors, and cannot name who is missing.
- **Episodes catalogued**: 134207
- **Censored share**: 0.007 — censored episodes are kept, never dropped (a decline that never prints a durable low is exactly the case that would otherwise turn recall into a survivorship filter).
- **Constants**: a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a
- **fingerprint_spec_hash**: dc36a6052ec57fd928f4279778f9890f125744947df30ab09a6a05ffde7fb7a8

Cluster rule (frozen v0): anchor dates pooled across names, single-linkage components at a 126-session gap, global cluster ids. The P90-episode-duration linkage refinement is a named PR-3 candidate.

## Episodes by type and tier

| episode_type | tier | names | episodes | censored | censored share |
|---|---:|---:|---:|---:|---:|
| failed_breakdown | 3 | 2525 | 103262 | 152 | 0.001 |
| reclaim | 1 | 1881 | 3707 | 49 | 0.013 |
| reclaim | 2 | 1182 | 1785 | 38 | 0.021 |
| reclaim | 3 | 853 | 1130 | 23 | 0.020 |
| reset_decline | 1 | 1893 | 4452 | 160 | 0.036 |
| reset_decline | 2 | 2256 | 8522 | 277 | 0.033 |
| reset_decline | 3 | 2272 | 11349 | 207 | 0.018 |

## Calendar clusters — frozen v0 rule (all anchors pooled)

Total distinct clusters: **1**

**This column carries no information at universe scale, and that is a result about the rule, not about the market.** The frozen v0 rule pools anchor dates across every name AND every episode type; with thousands of names catalogued, the pooled anchors cover essentially every session, so no 126-session gap ever occurs and single linkage returns one component. The rule is applied as frozen and reported as frozen. The stratified view below is a NAMED diagnostic, not a substitution — swapping the rule silently is precisely what the registration forbids.

| cluster_id | start | end | anchor dates |
|---:|---|---|---:|
| 0 | 1962-04-05 | 2026-08-12 | 9390 |

## Calendar clusters — diagnostic, stratified by (type, tier)

Anchors pooled within one (episode_type, tier) stratum, same 126-session single linkage. This is the object masterplan §8.1 describes when it says post-2010 tier-1 episodes concentrate in a single-digit number of market clusters, and it is the count to read when judging whether a cell's episodes are one market event wearing many tickers.

| episode_type | tier | clusters | first | last |
|---|---:|---:|---|---|
| failed_breakdown | 3.0 | 1 | 1962-04-05 | 2026-08-12 |
| reclaim | 1.0 | 26 | 1967-01-12 | 2026-08-07 |
| reclaim | 2.0 | 33 | 1967-04-17 | 2026-08-06 |
| reclaim | 3.0 | 29 | 1966-11-17 | 2026-08-07 |
| reset_decline | 1.0 | 25 | 1968-03-25 | 2026-06-12 |
| reset_decline | 2.0 | 10 | 1963-03-08 | 2026-06-12 |
| reset_decline | 3.0 | 4 | 1963-03-06 | 2026-06-10 |

## Distinct-cluster distribution per cell

| episode_type | tier | cells | median clusters/cell (diagnostic) | cells with <=1 cluster |
|---|---:|---:|---:|---:|
| failed_breakdown | 3 | 2525 | 1.0 | 2525 |
| reclaim | 1 | 1881 | 1.0 | 1740 |
| reclaim | 2 | 1182 | 1.0 | 1089 |
| reclaim | 3 | 853 | 1.0 | 801 |
| reset_decline | 1 | 1893 | 1.0 | 1772 |
| reset_decline | 2 | 2256 | 1.0 | 2213 |
| reset_decline | 3 | 2272 | 1.0 | 2250 |

A cell whose episodes sit in one cluster has an honest N of one market event regardless of its raw episode count.

## Feature availability by price plane

| feature | baskets_ohlcv_v1 | stock_identity_ohlcv_v1 | stocks_tr_v1 |
|---|---:|---:|---:|
| d_close_jump_drift5_252 | 0.848 | 1.000 | 0.873 |
| d_close_jump_freq_252 | 0.966 | 1.000 | 1.000 |
| d_f6_event_gap_contrib_252 | 0.976 | 1.000 | 0.000 |
| d_f6_gap_fill_rate_252 | 0.976 | 1.000 | 0.000 |
| d_f6_gap_share_252 | 0.976 | 1.000 | 0.000 |
| f10_amihud_252 | 0.964 | 1.000 | 0.995 |
| f10_cs_spread_252 | 0.976 | 1.000 | 1.000 |
| f10_dollar_adv_252 | 0.976 | 1.000 | 1.000 |
| f10_dollar_adv_63 | 0.976 | 1.000 | 1.000 |
| f10_turnover_proxy_252 | 0.976 | 1.000 | 1.000 |
| f1_kaufman_er_126 | 0.976 | 1.000 | 1.000 |
| f1_kaufman_er_252 | 0.976 | 1.000 | 1.000 |
| f1_kaufman_er_63 | 0.976 | 1.000 | 1.000 |
| f1_logprice_r2_126 | 0.976 | 1.000 | 1.000 |
| f1_logprice_r2_252 | 0.976 | 1.000 | 1.000 |
| f1_new_high_cadence_252 | 0.947 | 1.000 | 0.995 |
| f1_new_high_cadence_756 | 0.906 | 1.000 | 0.986 |
| f1_share_above_200dma_252 | 0.955 | 1.000 | 0.995 |
| f1_share_above_50dma_252 | 0.967 | 1.000 | 1.000 |
| f2_drawdown_median_756 | 0.922 | 1.000 | 0.991 |
| f2_drawdown_p90_756 | 0.922 | 1.000 | 0.991 |
| f2_resets_per_year_15pct | 0.922 | 1.000 | 0.991 |
| f2_resets_per_year_30pct | 0.922 | 1.000 | 0.991 |
| f2_time_under_water_median_756 | 0.875 | 1.000 | 0.991 |
| f2_ulcer_126 | 0.976 | 1.000 | 1.000 |
| f2_ulcer_252 | 0.947 | 1.000 | 0.995 |
| f3_post_trough_63d_atr_median | 0.952 | 1.000 | 0.995 |
| f3_time_to_50pct_retrace_median | 0.942 | 1.000 | 0.995 |
| f4_ar1_daily_252 | 0.976 | 1.000 | 1.000 |
| f4_ar1_weekly_756 | 0.922 | 1.000 | 0.991 |
| f4_mr_half_life_252 | 0.976 | 1.000 | 1.000 |
| f4_oscillator_dwell_extreme_252 | 0.973 | 1.000 | 1.000 |
| f4_variance_ratio_k20_756 | 0.922 | 1.000 | 0.991 |
| f4_variance_ratio_k5_756 | 0.922 | 1.000 | 0.991 |
| f5_acf_abs_ret_1_252 | 0.976 | 1.000 | 1.000 |
| f5_natr_regime_spread_252 | 0.973 | 1.000 | 1.000 |
| f5_realized_vol_21 | 0.976 | 1.000 | 1.000 |
| f5_realized_vol_252 | 0.976 | 1.000 | 1.000 |
| f5_realized_vol_63 | 0.976 | 1.000 | 1.000 |
| f5_vol_of_vol_252 | 0.974 | 1.000 | 1.000 |
| f7_atr_dist_200dma_252 | 0.955 | 1.000 | 0.995 |
| f7_atr_dist_20dma_252 | 0.972 | 1.000 | 1.000 |
| f7_atr_dist_50dma_252 | 0.967 | 1.000 | 1.000 |
| f7_bounce_rate_50dma_756 | 0.875 | 1.000 | 0.981 |
| f7_cross_freq_200dma_252 | 0.955 | 1.000 | 0.995 |
| f7_cross_freq_50dma_252 | 0.967 | 1.000 | 1.000 |
| f7_dwell_run_above_200dma_252 | 0.955 | 1.000 | 0.995 |
| f7_dwell_run_above_50dma_252 | 0.967 | 1.000 | 1.000 |
| f8_detrended_acf_peak_1260 | 0.860 | 1.000 | 0.986 |
| f8_detrended_acf_peak_lag_1260 | 0.860 | 1.000 | 0.986 |
| f8_detrended_acf_peak_sharpness_1260 | 0.860 | 1.000 | 0.986 |
| f8_swing_period_median_1260 | 0.860 | 1.000 | 0.986 |
| f9_beta_univ_ew_252 | 0.976 | 1.000 | 1.000 |
| f9_beta_univ_ew_756 | 0.922 | 1.000 | 0.991 |
| f9_idio_share_252 | 0.976 | 1.000 | 1.000 |
| f9_idio_share_756 | 0.922 | 1.000 | 0.991 |

The gap family sits in the diagnostic block precisely because its availability is plane-conditional: the open-less curated plane cannot carry it, so under the plane-availability law it is excluded from the metric block universe-wide rather than masked per name.

