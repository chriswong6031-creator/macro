# B — Identity Atlas v0 dossier

Descriptive behavioral read. **Zero authority**: nothing on this page ranks, sizes, gates, originates a signal, or escalates. No expert content exists in W1 by law. Episode *resolutions* use future data by design — they are a research-time labeling instrument, never a live surface.

**Pilot addendum (W2).** Barrick Mining, NYSE `B` — added by the 2026-08-14 operator ruling as the intended miner pilot after NYSE `GOLD` was resolved to a different issuer. `B` never entered the W1 universe snapshot, so it is in neither the blind evaluation arm nor the sealed calibration partition, and no sealed object was touched to add it. Its percentiles rank against the FROZEN W1 asof cross-section.

## Identity

| field | value |
|---|---|
| pilot role | miner neighborhood probe (Barrick Mining — the intended miner pilot) |
| price plane | `stock_identity_ohlcv_v1` |
| first print | 1985-02-13 |
| last print | 2026-08-13 |
| sessions | 10454 |
| `open` available | True |
| sector stratum | UNKNOWN |
| cap stratum | UNKNOWN (dollar-ADV tercile **proxy** — no per-name cap store is tracked) |
| vol stratum | UNKNOWN |
| epoch key | `epoch_0` (listing-to-date; epoch detector: none/provisional) |
| tape ended | False |
| terminated reason | right_censored_at_asof (tape active through asof) |

**Survivor-only cohort:** the allowed price planes retain no ceased tapes; no dead name could be included (registration §2). Any cohort comparison this name appears in is a comparison among survivors and cannot name who is missing.

### Ticker-identity hygiene (§9.6)

| flag | resolution |
|---|---|
| `symbol_lineage_note` | ABX -> GOLD (2019-01-02 rename) -> B (2025-05-09 rename): ONE continuous NYSE listing for Barrick through two symbol changes, not a splice of three instruments. The tape collected here is that listing under its current symbol. Barrick's retired symbols are separately occupied today — data/baskets/ohlcv/ABX.parquet (2020-09 onward) and data/baskets/ohlcv/GOLD.parquet (2014-03-17 onward) are DIFFERENT instruments on reused symbols. operator/CEO W1-return ruling 3, 2026-08-14 (#5613 ticker-identity forensics). |

**First-print sanity:** `PREDATES_CALENDAR` — first print 1985-02-13 predates the deal calendar's earliest priced date (2024-12-03)

## Behavioral fingerprint v0 (snapshot at asof)

Percentiles are PIT ranks against the contemporaneous evaluated universe. `—` is a coverage mask (the value is unavailable, which is not a low rank). `unstable` marks an adjacent-window quartile jump: the windows disagree, so the number is reported flagged rather than averaged into a clean-looking one.

### Metric block

The only block any future distance or map may read. Label-free by construction: no sector, industry, cap bucket, plane, or basket member here, and no gap-family member (the gap family is structurally unavailable on the open-less curated plane, so the plane law excludes it from this block universe-wide).

| feature | family | raw | universe pct | covered | unstable |
|---|---|---:|---:|:--:|:--:|
| `f1_kaufman_er_63` | F1 | 0.0618 | 29.2 | yes |  |
| `f1_kaufman_er_126` | F1 | 0.0489 | 34.3 | yes |  |
| `f1_kaufman_er_252` | F1 | 0.0797 | 60.4 | yes |  |
| `f1_logprice_r2_126` | F1 | 0.4550 | 51.0 | yes |  |
| `f1_logprice_r2_252` | F1 | 0.2613 | 29.8 | yes |  |
| `f1_share_above_50dma_252` | F1 | 0.6270 | 62.6 | yes |  |
| `f1_share_above_200dma_252` | F1 | 0.8373 | 69.7 | yes |  |
| `f1_new_high_cadence_252` | F1 | 0.1825 | 97.6 | yes |  |
| `f1_new_high_cadence_756` | F1 | 0.0886 | 89.3 | yes |  |
| `f2_drawdown_median_756` | F2 | 0.0294 | 42.4 | yes |  |
| `f2_drawdown_p90_756` | F2 | 0.1247 | 34.3 | yes |  |
| `f2_resets_per_year_15pct` | F2 | 1.0000 | 66.8 | yes |  |
| `f2_resets_per_year_30pct` | F2 | 0.0000 | 24.4 | yes |  |
| `f2_time_under_water_median_756` | F2 | 5.0000 | 40.0 | yes |  |
| `f2_ulcer_126` | F2 | 22.6139 | 62.4 | yes |  |
| `f2_ulcer_252` | F2 | 16.5638 | 38.5 | yes |  |
| `f3_post_trough_63d_atr_median` | F3 | 4.4950 | 55.0 | yes |  |
| `f3_time_to_50pct_retrace_median` | F3 | 26.5000 | 59.4 | yes |  |
| `f4_ar1_daily_252` | F4 | -0.0014 | 65.6 | yes |  |
| `f4_ar1_weekly_756` | F4 | -0.1300 | 12.3 | yes |  |
| `f4_variance_ratio_k5_756` | F4 | 1.0214 | 77.8 | yes |  |
| `f4_variance_ratio_k20_756` | F4 | 0.8710 | 50.5 | yes |  |
| `f4_mr_half_life_252` | F4 | 22.7052 | 24.9 | yes |  |
| `f4_oscillator_dwell_extreme_252` | F4 | 4.9091 | 82.8 | yes |  |
| `f5_realized_vol_21` | F5 | 48.7739 | 54.0 | yes |  |
| `f5_realized_vol_63` | F5 | 48.9557 | 53.1 | yes |  |
| `f5_realized_vol_252` | F5 | 47.9210 | 51.7 | yes |  |
| `f5_vol_of_vol_252` | F5 | 10.4824 | 37.8 | yes |  |
| `f5_acf_abs_ret_1_252` | F5 | 0.0089 | 20.6 | yes |  |
| `f5_natr_regime_spread_252` | F5 | 1.0684 | 53.2 | yes |  |
| `f7_atr_dist_20dma_252` | F7 | 0.7862 | 95.0 | yes |  |
| `f7_atr_dist_50dma_252` | F7 | 1.7147 | 92.0 | yes |  |
| `f7_atr_dist_200dma_252` | F7 | 6.2559 | 95.0 | yes |  |
| `f7_cross_freq_50dma_252` | F7 | 0.0556 | 28.5 | yes |  |
| `f7_cross_freq_200dma_252` | F7 | 0.0198 | 38.2 | yes |  |
| `f7_dwell_run_above_50dma_252` | F7 | 19.7500 | 73.2 | yes |  |
| `f7_dwell_run_above_200dma_252` | F7 | 70.3333 | 74.9 | yes |  |
| `f7_bounce_rate_50dma_756` | F7 | 0.5676 | 62.9 | yes |  |
| `f8_detrended_acf_peak_1260` | F8 | 0.3481 | 77.1 | yes |  |
| `f8_detrended_acf_peak_lag_1260` | F8 | 126.0000 | 30.9 | yes |  |
| `f8_detrended_acf_peak_sharpness_1260` | F8 | 3.1114 | 92.5 | yes |  |
| `f8_swing_period_median_756` | F8 | 33.0000 | 45.8 | yes |  |
| `f8_swing_period_median_1260` | F8 | 37.0000 | 51.8 | yes |  |
| `f9_beta_univ_ew_252` | F9 | 1.0890 | 62.5 | yes | **unstable** |
| `f9_beta_univ_ew_756` | F9 | 0.6260 | 20.7 | yes | **unstable** |
| `f9_idio_share_252` | F9 | 0.8329 | 35.7 | yes |  |
| `f9_idio_share_756` | F9 | 0.8893 | 71.0 | yes |  |
| `f10_dollar_adv_63` | F10 | 4.278e+08 | 90.5 | yes |  |
| `f10_dollar_adv_252` | F10 | 5.373e+08 | 93.2 | yes |  |
| `f10_turnover_proxy_252` | F10 | 0.6594 | 8.7 | yes |  |
| `f10_amihud_252` | F10 | 0.0000 | 10.7 | yes |  |
| `f10_cs_spread_252` | F10 | 0.0062 | 21.8 | yes |  |

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
| `d_f6_gap_share_252` | 0.6731 | 98.1 | yes |
| `d_f6_event_gap_contrib_252` | 0.0681 | 57.7 | yes |
| `d_f6_gap_fill_rate_252` | 0.3286 | 4.0 | yes |
| `d_close_jump_freq_252` | 0.0437 | 94.8 | yes |
| `d_close_jump_drift5_252` | -0.1878 | 30.8 | yes |

## Identity-episode catalog

Built with no expert event anywhere in its construction. Censored episodes are kept: a decline that never prints a durable low is the case that would otherwise silently disappear from every downstream count.

| type | tier | start | anchor | end | depth % | depth ATR | sessions | resolution | censored |
|---|---:|---|---|---|---:|---:|---:|---|:--:|
| failed_breakdown | 3 | 1985-12-09 | 1985-12-09 | 1985-12-10 | 10.0 | 2.02 | 1 | recovered | no |
| reset_decline | 3 | 1986-10-13 | 1986-11-21 | 1986-11-21 | 19.4 | 6.60 | 29 | durable_low | no |
| reset_decline | 3 | 1987-05-15 | 1987-06-22 | 1987-06-22 | 28.4 | 8.58 | 25 | durable_low | no |
| reset_decline | 2 | 1987-09-18 | 1987-11-10 | 1987-11-10 | 51.9 | 14.38 | 37 | durable_low | no |
| failed_breakdown | 3 | 1987-11-10 | 1987-11-10 | 1987-11-12 | 5.7 | 0.52 | 2 | recovered | no |
| failed_breakdown | 3 | 1988-09-19 | 1988-09-19 | 1988-09-20 | 1.6 | 0.59 | 1 | recovered | no |
| failed_breakdown | 3 | 1988-12-28 | 1988-12-28 | 1988-12-29 | 0.8 | 0.40 | 1 | recovered | no |
| reset_decline | 3 | 1989-03-14 | 1989-05-08 | 1989-05-08 | 15.3 | 6.90 | 38 | durable_low | no |
| failed_breakdown | 3 | 1989-05-08 | 1989-05-08 | 1989-05-10 | 1.9 | 0.93 | 2 | recovered | no |
| reset_decline | 3 | 1989-07-24 | 1989-09-13 | 1989-09-13 | 20.0 | 8.67 | 36 | durable_low | no |
| failed_breakdown | 3 | 1989-09-11 | 1989-09-13 | 1989-09-19 | 3.4 | 1.27 | 6 | recovered | no |
| reset_decline | 3 | 1990-03-15 | 1990-04-30 | 1990-04-30 | 21.0 | 7.67 | 31 | durable_low | no |
| failed_breakdown | 3 | 1990-04-24 | 1990-04-30 | 1990-05-07 | 5.9 | 1.61 | 9 | recovered | no |
| reset_decline | 2 | 1990-08-20 | 1990-10-16 | 1990-10-16 | 28.0 | 7.54 | 40 | durable_low | no |
| failed_breakdown | 3 | 1991-05-03 | 1991-05-03 | 1991-05-13 | 1.3 | 0.63 | 6 | recovered | no |
| failed_breakdown | 3 | 1991-09-12 | 1991-09-12 | 1991-09-17 | 1.2 | 0.43 | 3 | recovered | no |
| reset_decline | 2 | 1992-01-21 | 1992-04-27 | 1992-04-27 | 24.1 | 10.84 | 67 | durable_low | no |
| failed_breakdown | 3 | 1992-04-07 | 1992-04-08 | 1992-04-09 | 4.1 | 2.47 | 2 | recovered | no |
| failed_breakdown | 3 | 1992-04-15 | 1992-04-20 | 1992-04-21 | 2.1 | 1.06 | 3 | recovered | no |
| failed_breakdown | 3 | 1992-04-27 | 1992-04-27 | 1992-05-01 | 2.2 | 0.93 | 4 | recovered | no |
| reset_decline | 3 | 1992-09-16 | 1992-11-24 | 1992-11-24 | 17.0 | 8.24 | 49 | durable_low | no |
| failed_breakdown | 3 | 1992-11-17 | 1992-11-24 | 1992-11-30 | 3.3 | 1.58 | 8 | recovered | no |
| reset_decline | 3 | 1993-08-02 | 1993-09-13 | 1993-09-13 | 26.8 | 10.58 | 29 | durable_low | no |
| failed_breakdown | 3 | 1993-09-10 | 1993-09-13 | 1993-09-15 | 5.1 | 1.35 | 3 | recovered | no |
| reset_decline | 2 | 1994-01-18 | 1994-04-19 | 1994-04-19 | 31.3 | 14.09 | 63 | durable_low | no |
| failed_breakdown | 3 | 1994-02-07 | 1994-02-08 | 1994-02-09 | 1.4 | 0.44 | 2 | recovered | no |
| failed_breakdown | 3 | 1994-02-15 | 1994-02-15 | 1994-02-16 | 1.0 | 0.30 | 1 | recovered | no |
| failed_breakdown | 3 | 1994-02-18 | 1994-02-23 | 1994-02-28 | 5.0 | 1.55 | 5 | recovered | no |
| failed_breakdown | 3 | 1994-03-07 | 1994-03-08 | 1994-03-09 | 2.1 | 0.66 | 2 | recovered | no |
| failed_breakdown | 3 | 1994-08-02 | 1994-08-02 | 1994-08-04 | 0.6 | 0.22 | 2 | recovered | no |
| failed_breakdown | 3 | 1994-08-10 | 1994-08-17 | 1994-08-18 | 1.7 | 0.72 | 6 | recovered | no |
| failed_breakdown | 3 | 1994-08-24 | 1994-08-25 | 1994-08-29 | 1.7 | 0.81 | 3 | recovered | no |
| reset_decline | 2 | 1994-09-27 | 1995-01-31 | 1995-01-31 | 27.2 | 11.65 | 87 | durable_low | no |
| failed_breakdown | 3 | 1995-01-06 | 1995-01-06 | 1995-01-09 | 1.2 | 0.40 | 1 | recovered | no |
| failed_breakdown | 3 | 1995-01-31 | 1995-01-31 | 1995-02-02 | 1.9 | 0.67 | 2 | recovered | no |
| reset_decline | 3 | 1995-07-12 | 1995-07-31 | 1995-07-31 | 9.1 | 4.45 | 13 | durable_low | no |
| reset_decline | 3 | 1996-02-06 | 1996-03-12 | 1996-03-12 | 11.3 | 4.67 | 24 | durable_low | no |
| failed_breakdown | 3 | 1996-06-12 | 1996-06-12 | 1996-06-13 | 0.7 | 0.28 | 1 | recovered | no |
| failed_breakdown | 3 | 1996-06-20 | 1996-06-21 | 1996-07-05 | 4.0 | 1.86 | 10 | recovered | no |
| failed_breakdown | 3 | 1996-07-16 | 1996-07-17 | 1996-07-19 | 4.6 | 1.83 | 3 | recovered | no |
| failed_breakdown | 3 | 1996-09-26 | 1996-09-30 | 1996-10-01 | 2.9 | 1.41 | 3 | recovered | no |
| reset_decline | 3 | 1996-12-10 | 1997-01-15 | 1997-01-15 | 14.4 | 4.93 | 24 | durable_low | no |
| failed_breakdown | 3 | 1997-04-07 | 1997-04-09 | 1997-04-10 | 1.6 | 0.54 | 3 | recovered | no |
| failed_breakdown | 3 | 1997-04-14 | 1997-04-15 | 1997-04-17 | 2.7 | 0.92 | 3 | recovered | no |
| failed_breakdown | 3 | 1997-04-24 | 1997-04-24 | 1997-05-01 | 2.8 | 0.91 | 5 | recovered | no |
| failed_breakdown | 3 | 1997-06-24 | 1997-06-24 | 1997-06-25 | 0.5 | 0.18 | 1 | recovered | no |
| failed_breakdown | 3 | 1997-07-07 | 1997-07-07 | 1997-07-10 | 7.2 | 2.42 | 3 | recovered | no |
| failed_breakdown | 3 | 1997-10-27 | 1997-10-29 | 1997-10-30 | 5.9 | 1.64 | 3 | recovered | no |
| reclaim | 2 | 1998-01-08 | 1998-03-26 | 1998-05-26 | 43.8 | 16.03 | 53 | failed | no |
| failed_breakdown | 3 | 1998-01-12 | 1998-01-12 | 1998-01-13 | 0.4 | 0.08 | 1 | recovered | no |
| reset_decline | 1 | 1998-04-23 | 1998-08-31 | 1998-08-31 | 44.7 | 14.53 | 90 | durable_low | no |
| failed_breakdown | 3 | 1998-06-01 | 1998-06-01 | 1998-06-02 | 2.2 | 0.59 | 1 | recovered | no |
| failed_breakdown | 3 | 1998-08-26 | 1998-08-31 | 1998-09-04 | 16.5 | 4.93 | 7 | recovered | no |
| reclaim | 3 | 1998-09-02 | 1998-09-23 | 1998-12-03 | 43.9 | 16.08 | 14 | failed | no |
| reset_decline | 2 | 1998-11-05 | 1999-04-08 | 1999-04-08 | 29.4 | 7.13 | 104 | durable_low | no |
| failed_breakdown | 3 | 1998-12-22 | 1998-12-22 | 1998-12-23 | 0.7 | 0.15 | 1 | recovered | no |
| failed_breakdown | 3 | 1999-01-27 | 1999-01-27 | 1999-01-28 | 0.3 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 1999-02-18 | 1999-02-18 | 1999-02-19 | 0.3 | 0.09 | 1 | recovered | no |
| failed_breakdown | 3 | 1999-02-22 | 1999-03-02 | 1999-03-08 | 3.8 | 0.94 | 10 | recovered | no |
| reset_decline | 3 | 1999-05-06 | 1999-05-25 | 1999-05-25 | 27.4 | 6.96 | 13 | durable_low | no |
| reset_decline | 3 | 1999-09-27 | 1999-11-05 | 1999-11-05 | 28.8 | 10.77 | 29 | durable_low | no |
| failed_breakdown | 3 | 1999-11-01 | 1999-11-01 | 1999-11-02 | 1.7 | 0.33 | 1 | recovered | no |
| failed_breakdown | 3 | 1999-11-04 | 1999-11-05 | 1999-11-09 | 3.5 | 0.70 | 3 | recovered | no |
| failed_breakdown | 3 | 2000-01-14 | 2000-01-14 | 2000-01-18 | 0.9 | 0.30 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-01-24 | 2000-01-26 | 2000-01-27 | 4.1 | 1.43 | 3 | recovered | no |
| failed_breakdown | 3 | 2000-02-01 | 2000-02-01 | 2000-02-02 | 0.4 | 0.12 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-03-06 | 2000-03-06 | 2000-03-07 | 0.4 | 0.09 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-03-29 | 2000-03-31 | 2000-04-04 | 2.7 | 0.75 | 4 | recovered | no |
| reset_decline | 1 | 2000-06-06 | 2000-10-24 | 2000-10-24 | 35.4 | 10.12 | 98 | durable_low | no |
| failed_breakdown | 3 | 2000-10-03 | 2000-10-03 | 2000-10-04 | 0.8 | 0.27 | 1 | recovered | no |
| failed_breakdown | 3 | 2000-10-24 | 2000-10-24 | 2000-10-26 | 3.3 | 0.80 | 2 | recovered | no |
| reclaim | 2 | 2000-10-24 | 2000-12-19 | 2001-01-04 | 35.4 | 12.64 | 39 | failed | no |
| reset_decline | 3 | 2001-03-08 | 2001-04-02 | 2001-04-02 | 20.2 | 6.39 | 17 | durable_low | no |
| failed_breakdown | 3 | 2001-04-02 | 2001-04-02 | 2001-04-03 | 0.5 | 0.13 | 1 | recovered | no |
| reset_decline | 3 | 2001-05-18 | 2001-07-02 | 2001-07-02 | 24.3 | 8.05 | 30 | durable_low | no |
| failed_breakdown | 3 | 2001-07-02 | 2001-07-02 | 2001-07-11 | 4.7 | 1.40 | 6 | recovered | no |
| failed_breakdown | 3 | 2001-11-08 | 2001-11-08 | 2001-11-09 | 0.6 | 0.19 | 1 | recovered | no |
| reset_decline | 2 | 2002-05-28 | 2002-07-26 | 2002-07-26 | 40.0 | 11.96 | 42 | durable_low | no |
| failed_breakdown | 3 | 2003-03-10 | 2003-03-11 | 2003-03-18 | 2.0 | 0.59 | 6 | recovered | no |
| reset_decline | 3 | 2004-01-05 | 2004-01-29 | 2004-01-29 | 17.4 | 7.17 | 17 | durable_low | no |
| reset_decline | 3 | 2004-04-02 | 2004-05-07 | 2004-05-07 | 23.7 | 10.18 | 24 | durable_low | no |
| failed_breakdown | 3 | 2004-04-28 | 2004-04-28 | 2004-05-04 | 3.3 | 1.04 | 4 | recovered | no |
| failed_breakdown | 3 | 2004-05-07 | 2004-05-07 | 2004-05-11 | 3.4 | 0.96 | 2 | recovered | no |
| failed_breakdown | 3 | 2004-08-11 | 2004-08-12 | 2004-08-13 | 2.1 | 0.81 | 2 | recovered | no |
| reset_decline | 3 | 2004-11-29 | 2005-02-07 | 2005-02-07 | 15.3 | 6.46 | 48 | durable_low | no |
| failed_breakdown | 3 | 2005-02-01 | 2005-02-01 | 2005-02-02 | 0.5 | 0.25 | 1 | recovered | no |
| failed_breakdown | 3 | 2005-02-07 | 2005-02-07 | 2005-02-09 | 1.1 | 0.52 | 2 | recovered | no |
| reset_decline | 3 | 2005-03-08 | 2005-05-16 | 2005-05-16 | 17.8 | 8.42 | 48 | durable_low | no |
| failed_breakdown | 3 | 2005-05-12 | 2005-05-16 | 2005-05-18 | 2.0 | 0.94 | 4 | recovered | no |
| failed_breakdown | 3 | 2005-10-31 | 2005-11-04 | 2005-11-09 | 2.0 | 0.59 | 7 | recovered | no |
| reset_decline | 3 | 2006-01-31 | 2006-03-09 | 2006-03-09 | 18.5 | 7.60 | 26 | durable_low | no |
| reset_decline | 3 | 2006-05-10 | 2006-06-13 | 2006-06-13 | 23.4 | 7.81 | 23 | durable_low | no |
| failed_breakdown | 3 | 2006-11-20 | 2006-11-20 | 2006-11-21 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2007-03-05 | 2007-03-05 | 2007-03-06 | 1.7 | 0.57 | 1 | recovered | no |
| failed_breakdown | 3 | 2007-03-13 | 2007-03-13 | 2007-03-15 | 1.6 | 0.60 | 2 | recovered | no |
| reset_decline | 3 | 2007-11-06 | 2007-12-17 | 2007-12-17 | 20.1 | 5.87 | 28 | durable_low | no |
| failed_breakdown | 3 | 2007-12-13 | 2007-12-17 | 2007-12-21 | 3.0 | 0.72 | 6 | recovered | no |
| reset_decline | 2 | 2008-01-28 | 2008-05-01 | 2008-05-01 | 30.3 | 6.59 | 66 | durable_low | no |
| failed_breakdown | 3 | 2008-04-01 | 2008-04-01 | 2008-04-02 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2008-09-03 | 2008-09-09 | 2008-09-17 | 17.3 | 3.01 | 10 | recovered | no |
| reclaim | 1 | 2008-10-14 | 2009-01-21 | 2009-02-24 | 44.1 | 6.73 | 67 | failed | no |
| failed_breakdown | 3 | 2009-03-10 | 2009-03-10 | 2009-03-12 | 6.1 | 0.80 | 2 | recovered | no |
| reset_decline | 2 | 2009-12-02 | 2010-02-04 | 2010-02-04 | 29.1 | 8.05 | 43 | durable_low | no |
| failed_breakdown | 3 | 2010-01-27 | 2010-01-27 | 2010-01-28 | 0.1 | 0.02 | 1 | recovered | no |
| failed_breakdown | 3 | 2010-01-29 | 2010-01-29 | 2010-02-01 | 2.6 | 0.69 | 1 | recovered | no |
| failed_breakdown | 3 | 2010-02-04 | 2010-02-04 | 2010-02-05 | 2.4 | 0.62 | 1 | recovered | no |
| failed_breakdown | 3 | 2010-07-27 | 2010-07-27 | 2010-07-30 | 1.9 | 0.61 | 3 | recovered | no |
| reset_decline | 3 | 2010-12-06 | 2011-01-25 | 2011-01-25 | 15.9 | 6.53 | 34 | durable_low | no |
| failed_breakdown | 3 | 2011-01-25 | 2011-01-25 | 2011-01-26 | 0.5 | 0.18 | 1 | recovered | no |
| reset_decline | 2 | 2011-04-21 | 2011-06-24 | 2011-06-24 | 22.4 | 9.35 | 44 | durable_low | no |
| failed_breakdown | 3 | 2011-05-05 | 2011-05-05 | 2011-05-09 | 1.2 | 0.36 | 2 | recovered | no |
| failed_breakdown | 3 | 2011-05-11 | 2011-05-13 | 2011-05-25 | 3.9 | 1.26 | 10 | recovered | no |
| failed_breakdown | 3 | 2011-06-24 | 2011-06-24 | 2011-06-27 | 0.1 | 0.03 | 1 | recovered | no |
| failed_breakdown | 3 | 2011-10-04 | 2011-10-04 | 2011-10-05 | 2.5 | 0.57 | 1 | recovered | no |
| failed_breakdown | 3 | 2011-10-20 | 2011-10-20 | 2011-10-24 | 0.6 | 0.15 | 2 | recovered | no |
| failed_breakdown | 3 | 2011-12-15 | 2011-12-15 | 2011-12-16 | 0.0 | 0.00 | 1 | recovered | no |
| failed_breakdown | 3 | 2012-03-14 | 2012-03-22 | 2012-03-26 | 2.2 | 0.84 | 8 | recovered | no |
| failed_breakdown | 3 | 2012-05-08 | 2012-05-15 | 2012-05-21 | 7.7 | 2.76 | 9 | recovered | no |
| failed_breakdown | 3 | 2012-07-12 | 2012-07-12 | 2012-07-13 | 0.7 | 0.20 | 1 | recovered | no |
| failed_breakdown | 3 | 2012-07-18 | 2012-07-18 | 2012-07-19 | 0.7 | 0.21 | 1 | recovered | no |
| reclaim | 3 | 2012-07-26 | 2012-09-13 | 2012-09-25 | 41.1 | 19.85 | 34 | failed | no |
| failed_breakdown | 3 | 2012-11-14 | 2012-11-15 | 2012-11-23 | 5.2 | 1.66 | 6 | recovered | no |
| failed_breakdown | 3 | 2013-02-13 | 2013-02-13 | 2013-02-14 | 1.0 | 0.49 | 1 | recovered | no |
| reclaim | 1 | 2013-04-10 | 2014-01-17 | 2014-03-26 | 42.2 | 21.73 | 196 | failed | no |
| failed_breakdown | 3 | 2013-04-17 | 2013-04-23 | 2013-04-24 | 6.7 | 1.04 | 5 | recovered | no |
| failed_breakdown | 3 | 2013-12-06 | 2013-12-06 | 2013-12-09 | 0.2 | 0.05 | 1 | recovered | no |
| reset_decline | 2 | 2014-02-24 | 2014-05-28 | 2014-05-28 | 25.7 | 7.94 | 65 | durable_low | no |
| failed_breakdown | 3 | 2014-04-21 | 2014-04-21 | 2014-04-25 | 3.1 | 0.99 | 4 | recovered | no |
| failed_breakdown | 3 | 2014-05-01 | 2014-05-01 | 2014-05-02 | 1.0 | 0.32 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-17 | 2014-10-17 | 2014-10-20 | 0.3 | 0.08 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-22 | 2014-10-22 | 2014-10-23 | 0.1 | 0.04 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-10-27 | 2014-10-27 | 2014-10-28 | 0.7 | 0.20 | 1 | recovered | no |
| failed_breakdown | 3 | 2014-12-15 | 2014-12-16 | 2014-12-18 | 5.6 | 1.03 | 3 | recovered | no |
| failed_breakdown | 3 | 2014-12-23 | 2014-12-23 | 2014-12-26 | 1.5 | 0.26 | 2 | recovered | no |
| reset_decline | 1 | 2015-04-29 | 2015-09-23 | 2015-09-23 | 55.7 | 15.32 | 102 | durable_low | no |
| failed_breakdown | 3 | 2015-08-03 | 2015-08-05 | 2015-08-07 | 5.1 | 0.82 | 4 | recovered | no |
| failed_breakdown | 3 | 2015-09-03 | 2015-09-10 | 2015-09-16 | 4.8 | 0.66 | 8 | recovered | no |
| failed_breakdown | 3 | 2015-09-22 | 2015-09-23 | 2015-09-24 | 4.3 | 0.69 | 2 | recovered | no |
| reclaim | 2 | 2015-11-24 | 2016-01-25 | 2016-04-25 | 45.0 | 15.57 | 40 | held | no |
| reset_decline | 1 | 2016-07-06 | 2016-12-15 | 2016-12-15 | 39.4 | 10.23 | 114 | durable_low | no |
| failed_breakdown | 3 | 2016-08-30 | 2016-08-31 | 2016-09-02 | 6.3 | 1.49 | 3 | recovered | no |
| failed_breakdown | 3 | 2016-11-11 | 2016-11-14 | 2016-11-15 | 5.2 | 0.92 | 2 | recovered | no |
| failed_breakdown | 3 | 2016-11-23 | 2016-11-23 | 2016-11-25 | 0.1 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2016-12-15 | 2016-12-15 | 2016-12-27 | 4.2 | 0.85 | 7 | recovered | no |
| failed_breakdown | 3 | 2017-06-14 | 2017-06-20 | 2017-06-22 | 2.4 | 0.97 | 6 | recovered | no |
| failed_breakdown | 3 | 2017-07-07 | 2017-07-07 | 2017-07-10 | 1.5 | 0.60 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-10-20 | 2017-10-20 | 2017-10-23 | 0.4 | 0.21 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-11-10 | 2017-11-13 | 2017-11-14 | 0.3 | 0.13 | 2 | recovered | no |
| failed_breakdown | 3 | 2017-11-16 | 2017-11-16 | 2017-11-17 | 0.2 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-11-20 | 2017-11-20 | 2017-11-21 | 0.1 | 0.07 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-11-30 | 2017-11-30 | 2017-12-01 | 0.7 | 0.36 | 1 | recovered | no |
| failed_breakdown | 3 | 2017-12-05 | 2017-12-06 | 2017-12-13 | 1.7 | 0.78 | 6 | recovered | no |
| failed_breakdown | 3 | 2018-02-06 | 2018-02-09 | 2018-02-14 | 3.6 | 1.22 | 6 | recovered | no |
| failed_breakdown | 3 | 2018-08-01 | 2018-08-02 | 2018-08-03 | 1.4 | 0.52 | 2 | recovered | no |
| failed_breakdown | 3 | 2018-09-10 | 2018-09-10 | 2018-09-12 | 0.7 | 0.24 | 2 | recovered | no |
| reclaim | 3 | 2018-09-10 | 2018-10-11 | 2019-01-14 | 44.7 | 26.45 | 23 | held | no |
| reset_decline | 3 | 2018-12-13 | 2019-01-23 | 2019-01-23 | 16.2 | 5.47 | 26 | durable_low | no |
| failed_breakdown | 3 | 2019-01-14 | 2019-01-23 | 2019-01-28 | 4.6 | 1.19 | 9 | recovered | no |
| reset_decline | 3 | 2019-03-26 | 2019-05-28 | 2019-05-28 | 19.0 | 6.90 | 43 | durable_low | no |
| failed_breakdown | 3 | 2019-05-10 | 2019-05-10 | 2019-05-13 | 2.5 | 0.93 | 1 | recovered | no |
| failed_breakdown | 3 | 2019-05-22 | 2019-05-28 | 2019-05-31 | 2.2 | 0.81 | 6 | recovered | no |
| reset_decline | 3 | 2019-08-28 | 2019-11-07 | 2019-11-07 | 17.8 | 6.64 | 50 | durable_low | no |
| failed_breakdown | 3 | 2019-11-05 | 2019-11-05 | 2019-11-06 | 0.2 | 0.06 | 1 | recovered | no |
| failed_breakdown | 3 | 2019-11-07 | 2019-11-07 | 2019-11-13 | 1.1 | 0.35 | 4 | recovered | no |
| reset_decline | 3 | 2020-02-24 | 2020-03-13 | 2020-03-13 | 28.6 | 11.37 | 14 | durable_low | no |
| failed_breakdown | 3 | 2020-03-12 | 2020-03-13 | 2020-03-17 | 9.6 | 1.72 | 3 | recovered | no |
| reset_decline | 1 | 2020-09-09 | 2021-02-26 | 2021-02-26 | 38.2 | 9.59 | 117 | durable_low | no |
| failed_breakdown | 3 | 2020-10-28 | 2020-10-28 | 2020-10-29 | 0.7 | 0.26 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-11-27 | 2020-11-27 | 2020-11-30 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2020-12-14 | 2020-12-14 | 2020-12-15 | 1.1 | 0.36 | 1 | recovered | no |
| failed_breakdown | 3 | 2021-01-27 | 2021-01-27 | 2021-02-01 | 2.0 | 0.74 | 3 | recovered | no |
| reclaim | 2 | 2021-03-03 | 2021-05-17 | 2021-05-27 | 35.4 | 15.77 | 52 | failed | no |
| reset_decline | 1 | 2022-04-13 | 2022-11-03 | 2022-11-03 | 47.6 | 17.11 | 141 | durable_low | no |
| failed_breakdown | 3 | 2022-05-12 | 2022-05-18 | 2022-05-19 | 4.1 | 1.11 | 5 | recovered | no |
| failed_breakdown | 3 | 2022-06-14 | 2022-06-14 | 2022-06-16 | 0.5 | 0.14 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-07-25 | 2022-07-25 | 2022-07-27 | 2.7 | 0.66 | 2 | recovered | no |
| failed_breakdown | 3 | 2022-09-01 | 2022-09-01 | 2022-09-02 | 0.9 | 0.26 | 1 | recovered | no |
| failed_breakdown | 3 | 2022-09-23 | 2022-09-27 | 2022-09-28 | 3.4 | 0.96 | 3 | recovered | no |
| failed_breakdown | 3 | 2022-11-03 | 2022-11-03 | 2022-11-04 | 7.1 | 1.90 | 1 | recovered | no |
| reclaim | 2 | 2022-11-04 | 2023-01-03 | 2023-02-16 | 43.2 | 18.51 | 39 | failed | no |
| reset_decline | 3 | 2023-02-01 | 2023-03-09 | 2023-03-09 | 21.5 | 8.14 | 25 | durable_low | no |
| failed_breakdown | 3 | 2023-03-07 | 2023-03-09 | 2023-03-10 | 2.1 | 0.75 | 3 | recovered | no |
| reset_decline | 2 | 2023-05-04 | 2023-10-03 | 2023-10-03 | 29.7 | 12.41 | 104 | durable_low | no |
| failed_breakdown | 3 | 2023-06-15 | 2023-06-20 | 2023-06-30 | 4.4 | 1.86 | 10 | recovered | no |
| failed_breakdown | 3 | 2023-08-15 | 2023-08-18 | 2023-08-23 | 2.7 | 1.20 | 6 | recovered | no |
| reset_decline | 3 | 2023-12-27 | 2024-02-14 | 2024-02-14 | 23.9 | 10.23 | 33 | durable_low | no |
| reset_decline | 2 | 2024-10-22 | 2024-12-19 | 2024-12-19 | 27.7 | 11.04 | 41 | durable_low | no |
| reset_decline | 2 | 2026-01-28 | 2026-03-20 | 2026-03-20 | 29.3 | 9.43 | 36 | durable_low | no |
| failed_breakdown | 3 | 2026-03-13 | 2026-03-13 | 2026-03-16 | 0.5 | 0.11 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-06-24 | 2026-06-24 | 2026-06-26 | 2.0 | 0.40 | 2 | recovered | no |
| failed_breakdown | 3 | 2026-07-01 | 2026-07-01 | 2026-07-02 | 0.0 | 0.01 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-07-08 | 2026-07-08 | 2026-07-09 | 1.9 | 0.43 | 1 | recovered | no |
| failed_breakdown | 3 | 2026-07-16 | 2026-07-16 | 2026-07-21 | 2.5 | 0.59 | 3 | recovered | no |

**193 episodes**, 0 censored; by type {'failed_breakdown': 135, 'reset_decline': 48, 'reclaim': 10}; by tier {3: 166, 2: 19, 1: 8}.

## State shares by year

Eight mutually-exclusive bars-only states, first-match-wins precedence. Gap basis on this plane: `open_vs_prev_close` — a close-to-close proxy absorbs the whole session's move, not just the overnight jump, so cross-plane comparisons of the dislocation share carry that caveat.

| year | post event dislocation | deep washout | breakdown | recovery reclaim | controlled pullback | structural uptrend | vol transition | range |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1985 | 0% | 0% | 0% | 0% | 0% | 0% | 0% | 100% |
| 1986 | 0% | 0% | 0% | 0% | 36% | 52% | 0% | 11% |
| 1987 | 2% | 2% | 0% | 11% | 38% | 42% | 0% | 5% |
| 1988 | 0% | 2% | 0% | 13% | 8% | 0% | 2% | 75% |
| 1989 | 0% | 0% | 0% | 17% | 33% | 46% | 1% | 4% |
| 1990 | 4% | 0% | 0% | 0% | 51% | 33% | 4% | 8% |
| 1991 | 0% | 0% | 0% | 0% | 43% | 36% | 0% | 21% |
| 1992 | 0% | 0% | 0% | 0% | 54% | 32% | 7% | 7% |
| 1993 | 0% | 0% | 0% | 0% | 49% | 49% | 0% | 2% |
| 1994 | 0% | 0% | 0% | 0% | 19% | 6% | 8% | 67% |
| 1995 | 0% | 0% | 0% | 0% | 43% | 34% | 3% | 20% |
| 1996 | 0% | 0% | 0% | 0% | 26% | 34% | 13% | 27% |
| 1997 | 2% | 4% | 3% | 0% | 4% | 0% | 20% | 66% |
| 1998 | 0% | 2% | 2% | 38% | 0% | 0% | 5% | 54% |
| 1999 | 4% | 0% | 0% | 8% | 28% | 1% | 11% | 48% |
| 2000 | 0% | 0% | 1% | 4% | 15% | 0% | 33% | 48% |
| 2001 | 2% | 0% | 0% | 11% | 40% | 1% | 9% | 36% |
| 2002 | 0% | 0% | 0% | 0% | 27% | 26% | 14% | 33% |
| 2003 | 0% | 0% | 0% | 0% | 38% | 31% | 9% | 23% |
| 2004 | 0% | 0% | 0% | 0% | 40% | 20% | 12% | 27% |
| 2005 | 0% | 0% | 0% | 0% | 54% | 42% | 0% | 4% |
| 2006 | 0% | 0% | 0% | 0% | 57% | 21% | 10% | 12% |
| 2007 | 0% | 0% | 0% | 0% | 31% | 30% | 25% | 14% |
| 2008 | 0% | 17% | 7% | 1% | 25% | 13% | 0% | 36% |
| 2009 | 0% | 4% | 0% | 45% | 15% | 16% | 0% | 20% |
| 2010 | 0% | 0% | 0% | 0% | 56% | 36% | 4% | 4% |
| 2011 | 0% | 0% | 0% | 0% | 38% | 20% | 7% | 35% |
| 2012 | 2% | 0% | 4% | 7% | 10% | 0% | 24% | 53% |
| 2013 | 0% | 73% | 2% | 0% | 0% | 0% | 5% | 21% |
| 2014 | 0% | 12% | 15% | 29% | 10% | 0% | 1% | 33% |
| 2015 | 0% | 41% | 7% | 0% | 0% | 0% | 0% | 52% |
| 2016 | 0% | 0% | 0% | 41% | 27% | 7% | 0% | 25% |
| 2017 | 0% | 0% | 0% | 0% | 29% | 0% | 1% | 70% |
| 2018 | 0% | 1% | 4% | 22% | 0% | 0% | 1% | 72% |
| 2019 | 0% | 0% | 0% | 17% | 49% | 27% | 0% | 8% |
| 2020 | 2% | 0% | 0% | 0% | 49% | 34% | 11% | 3% |
| 2021 | 0% | 0% | 2% | 4% | 2% | 0% | 18% | 73% |
| 2022 | 0% | 0% | 9% | 0% | 18% | 14% | 7% | 51% |
| 2023 | 0% | 0% | 0% | 29% | 21% | 1% | 5% | 44% |
| 2024 | 2% | 0% | 0% | 0% | 34% | 31% | 10% | 23% |
| 2025 | 0% | 0% | 0% | 0% | 30% | 54% | 4% | 12% |
| 2026 | 3% | 0% | 0% | 0% | 55% | 15% | 0% | 27% |

## Episode map

![B episode map](B.png)

Log price with the 200DMA, episode spans shaded by type, durable lows marked, and the daily state strip beneath. On histories longer than 5,000 sessions the two price LINES are drawn at weekly resolution for legibility and file size; spans, markers and the state strip stay daily.

---

Constants: `77e111c11672524c826948455a8c2ea5b812cdddb3f0d9dac1807b253604e9d0` · fingerprint spec: `0e3457b11f41452e1c3efac3858196f5f42b573d1961b798ea581e1590b33187` · partition: `a546c64983431f0afca01cfd9aacc230ef3bed875520c44898090520cf98164a` · asof 2026-08-13
