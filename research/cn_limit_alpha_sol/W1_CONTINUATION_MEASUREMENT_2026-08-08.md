# CN limit-up continuation — SOL Wave-1 deterministic receipt

**Receipt date:** 2026-08-08
**Authority:** `none_research_display_only`
**Model/definition:** `sol_w1_daily_tolerant_common_calendar_fixed_strata_2026-08-08`

> Curated-slice warning: this receipt does not describe the full 打板 universe. The vendor pool has 1,770 distinct tickers, but only 514 (29.04%) overlap the local nominal OHLCV slice.

## Frozen contract

- `C0`: tolerant board close on D to the common CN calendar successor. A missing/halted ticker bar stays in the primary denominator as no board; observed-bar-only results are a named sensitivity.
- `C-AUCTION`: features stop at D close. The candidate fill is D+1 official open; an open within the tolerant upper-limit cushion is an unfilled queue. The realised D+1 gap is not a selection filter.
- `C-POSTGAP`: realised auction gap conditions next-board probability only. There is deliberately no daily-OHLCV return claim because 09:30/first-five-minute execution is absent.
- T+1 exits begin no earlier than D+2 for a D+1-open entry. Every exit resolves on exact market sessions; a missing bar is unresolved, and lower-limit carry advances one market session at a time.
- Main board is primary; ChiNext band eras are separate secondary cohorts; STAR is descriptive; BSE/ST are untested.

## Data and event inventory

- Raw files: 1,841 read / 1,842 discovered; 0 errors; 1 current-ST intersections excluded.
- Raw rows: 6,760,225; sessions 1990-12-19 to 2026-08-07.
- Tolerant boards: 55,603; strict boards: 29,333; marginal tolerance rows: 26,270.
- Measured after boundary purge: 55,112 signals, 3,698 date clusters, 44,158 board-run clusters.
- `china_zt_pool` vendor strata use valid observed sessions only: 11 clone dates are excluded, missing sessions are not imputed, and retrospective rows are explicitly stamped non-PIT.

## Construction verdicts

### C0_TRUE_NEXT_SESSION

- Verdict: **MEASURED_BASE_RATE_NO_PROMOTION**
- Headline: n=7,637; mean=17.98%; date-cluster 95% CI=[15.28%, 20.67%]
- Kill scope: none
- Measured: tolerant close-to-close board continuation on the common CN calendar successor; missing/halted bars retained as failures, with observed-bar-only sensitivity
- Not measured: see ore ledger below

### C_AUCTION

- Verdict: **NEGATIVE_SPECIFIC_CONSTRUCTION**
- Headline: n=9,762; mean=-0.81%; date-cluster 95% CI=[-1.16%, -0.46%]
- Kill scope: Only the unconditioned curated-main candidate book (all signals; nonfills cash=0), tolerant-board D-close decision / D+1 official-open rider with seal-state-next-open exit at 60bp in historical replay is killed.
- Measured: official-open candidate fill after a D-close decision, upper-limit queue rejected, T+1-valid exits, 0/30/60/100bp, and all-signal cash-book expectancy
- Not measured: realised gap as a selection feature

### C_AUCTION_N

- Verdict: **MIXED_OR_INCONCLUSIVE_PRIMARY_ENDPOINT_STRATA_NO_GLOBAL_KILL**
- Headline: n/a
- Kill scope: At locked-replay seal-state/60bp only, negative cells: 1, 2, 3, 5_plus. Other exits/costs and unlisted cells are not killed.
- Measured: main-board all-signal candidate books by fixed board-count bucket, all five exits and four costs
- Not measured: crossed board-count/geometry/ecology search or post-auction gap selection

### C_AUCTION_ONE_PRICE_D_CLOSE

- Verdict: **MIXED_OR_INCONCLUSIVE_PRIMARY_ENDPOINT_STRATA_NO_GLOBAL_KILL**
- Headline: n/a
- Kill scope: At locked-replay seal-state/60bp only, negative cells: no. Other exits/costs and unlisted cells are not killed.
- Measured: main-board all-signal candidate books by D-close-known one-price yes/no, all five exits and four costs
- Not measured: intraday queue duration, seal path, and crossed feature combinations

### C_AUCTION_INTRADAY_RANGE_D_CLOSE

- Verdict: **MIXED_OR_INCONCLUSIVE_PRIMARY_ENDPOINT_STRATA_NO_GLOBAL_KILL**
- Headline: n/a
- Kill scope: At locked-replay seal-state/60bp only, negative cells: 0_35_to_0_70, gt_0_70. Other exits/costs and unlisted cells are not killed.
- Measured: main-board all-signal candidate books by fixed D-close intraday-range buckets, all five exits and four costs
- Not measured: fitted range cut points and crossed feature combinations

### C_AUCTION_ECOLOGY_D_CLOSE

- Verdict: **NEGATIVE_ALL_PRIMARY_ENDPOINT_STRATA_SPECIFIC_ONLY**
- Headline: n/a
- Kill scope: At locked-replay seal-state/60bp only, negative cells: cold, hot, neutral. Other exits/costs and unlisted cells are not killed.
- Measured: main-board all-signal candidate books by causal D-close ecology state, all five exits and four costs
- Not measured: PIT theme topology and crossed ecology/geometry optimisation

### C_POSTGAP

- Verdict: **PROBABILITY_ONLY_NO_RETURN_VERDICT**
- Headline: n/a
- Kill scope: none; no daily-OHLCV post-auction return construction was claimed or tested
- Measured: realised official-auction gap bucket versus next-close board probability
- Not measured: 09:30 or first-five-minute executable return

### BOARD_GEOMETRY_CHALLENGERS

- Verdict: **DESCRIPTIVE_FIXED_BUCKETS_NO_PROMOTION**
- Headline: n/a
- Kill scope: none
- Measured: one-price, board-day gap, intraday range, close location, and volume-z fixed buckets
- Not measured: intraday seal path and fitted nonlinear geometry model

### PIT_SHRUNK_ECOLOGY_CHALLENGER

- Verdict: **SOFT_DESCRIPTIVE_CHALLENGER_NO_PROMOTION**
- Headline: n/a
- Kill scope: none
- Measured: causal 20/60-session shrunk continuation/breadth/failure state
- Not measured: PIT sector concentration, theme topology, or exposure sizing

### FROZEN_CROWD_CLOCK

- Verdict: **DESCRIPTIVE_FIXED_BINS_NO_PROMOTION**
- Headline: n/a
- Kill scope: none
- Measured: Friday and >=4-day holiday-gap cross by board count, continuation, fill, and joint cash book
- Not measured: fitted calendar-seasonality interactions or intraday crowding

### PREDECLARED_2015_STRESS

- Verdict: **STANDALONE_STRESS_TABLE_NO_PROMOTION**
- Headline: n/a
- Kill scope: none
- Measured: 2015 main-board continuation, fill, and joint cash book by board count
- Not measured: portfolio liquidity/capacity and intraday queue behavior during the 2015 crash

### VENDOR_DESCRIPTIVE_STRATUM

- Verdict: **DESCRIPTIVE_VALID_SESSIONS_ONLY_NO_PROMOTION**
- Headline: n/a
- Kill scope: none
- Measured: seal_fund_yi, failed_seals, and turnover probability strata on valid observed vendor sessions
- Not measured: pre-coverage zeros; clone dates; executable returns; normalized seal-fund intensity

## Main historical-replay fill funnel

| Signals | Exact next bar | Halt/missing | Upper-limit queue | Candidate fills | Fill / all signals |
|---:|---:|---:|---:|---:|---:|
| 9,762 | 9,762 | 0 | 1,233 | 8,529 | 87.37% |

The strategy-level return is the joint candidate-book mean with nonfills held at cash=0. Filled-conditional distributions remain diagnostics, not expectancy.

## Fixed pre-auction rider books — locked replay primary comparison, seal-state exit, 60bp

These are separate one-dimensional predeclared strata. The JSON includes every fixed exit and 0/30/60/100bp; this compact table is the seal-state/60bp primary comparison only. No crossed combination or best-cell tuning was run.

| Construction | Fixed stratum | Candidates | Mature book | Fill / mature | Joint cash-book mean | Date-cluster 95% CI | Cell verdict |
|---|---|---:|---:|---:|---:|---:|---|
| C_AUCTION_N | 1 | 7,637 | 7,637 | 90.28% | -0.66% | [-1.02%, -0.30%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_N | 2 | 1,369 | 1,369 | 81.30% | -1.25% | [-2.07%, -0.43%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_N | 3 | 406 | 406 | 68.72% | -1.23% | [-2.30%, -0.16%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_N | 4 | 182 | 182 | 73.08% | -0.83% | [-2.47%, 0.81%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_N | 5_plus | 168 | 168 | 64.88% | -2.95% | [-4.76%, -1.14%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ONE_PRICE_D_CLOSE | no | 9,128 | 9,128 | 90.50% | -0.82% | [-1.19%, -0.45%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ONE_PRICE_D_CLOSE | yes | 634 | 634 | 42.27% | -0.63% | [-1.30%, 0.05%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | 0_10_to_0_35 | 343 | 343 | 82.51% | -0.50% | [-1.33%, 0.32%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | 0_35_to_0_70 | 1,692 | 1,692 | 78.37% | -0.93% | [-1.53%, -0.34%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | gt_0_70 | 7,056 | 7,056 | 93.86% | -0.82% | [-1.22%, -0.42%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | le_0_10 | 671 | 671 | 44.26% | -0.53% | [-1.18%, 0.13%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_ECOLOGY_D_CLOSE | cold | 2,465 | 2,465 | 92.17% | -0.69% | [-1.08%, -0.30%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ECOLOGY_D_CLOSE | hot | 3,041 | 3,041 | 78.10% | -1.01% | [-1.80%, -0.23%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ECOLOGY_D_CLOSE | neutral | 4,256 | 4,256 | 91.21% | -0.73% | [-1.27%, -0.20%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |

## Frozen crowd clock

| Split | Board | Friday | Holiday gap | Signals | Mature book | Inclusive continuation | Fill / all | Joint seal-state 60bp |
|---|---:|---|---|---:|---:|---:|---:|---:|
| calibration_2020_2023 | 1 | friday | holiday_gap_ge_4_calendar_days | 220 | 220 | 25.45% | 95.45% | 0.46% |
| calibration_2020_2023 | 1 | friday | not_holiday_gap | 1,968 | 1,968 | 18.39% | 94.41% | -0.65% |
| calibration_2020_2023 | 1 | not_friday | holiday_gap_ge_4_calendar_days | 125 | 125 | 16.80% | 93.60% | -0.65% |
| calibration_2020_2023 | 1 | not_friday | not_holiday_gap | 9,503 | 9,503 | 12.68% | 96.34% | -0.82% |
| calibration_2020_2023 | 2 | friday | holiday_gap_ge_4_calendar_days | 17 | 17 | 23.53% | 82.35% | -3.38% |
| calibration_2020_2023 | 2 | friday | not_holiday_gap | 262 | 262 | 37.79% | 79.77% | -1.49% |
| calibration_2020_2023 | 2 | not_friday | holiday_gap_ge_4_calendar_days | 20 | 20 | 45.00% | 60.00% | -0.16% |
| calibration_2020_2023 | 2 | not_friday | not_holiday_gap | 1,347 | 1,347 | 27.39% | 86.79% | -1.13% |
| calibration_2020_2023 | 3 | friday | holiday_gap_ge_4_calendar_days | 5 | 5 | 20.00% | 80.00% | -1.45% |
| calibration_2020_2023 | 3 | friday | not_holiday_gap | 85 | 85 | 38.82% | 78.82% | -2.03% |
| calibration_2020_2023 | 3 | not_friday | holiday_gap_ge_4_calendar_days | 4 | 4 | 75.00% | 50.00% | 0.42% |
| calibration_2020_2023 | 3 | not_friday | not_holiday_gap | 387 | 387 | 41.09% | 78.29% | -1.26% |
| calibration_2020_2023 | 4 | friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 50.00% | 100.00% | 12.99% |
| calibration_2020_2023 | 4 | friday | not_holiday_gap | 31 | 31 | 58.06% | 70.97% | 1.76% |
| calibration_2020_2023 | 4 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 100.00% | 0.00% | 0.00% |
| calibration_2020_2023 | 4 | not_friday | not_holiday_gap | 162 | 162 | 48.77% | 70.37% | -0.65% |
| calibration_2020_2023 | 5_plus | friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 50.00% | 100.00% | -14.11% |
| calibration_2020_2023 | 5_plus | friday | not_holiday_gap | 44 | 44 | 47.73% | 63.64% | -3.30% |
| calibration_2020_2023 | 5_plus | not_friday | not_holiday_gap | 159 | 159 | 52.83% | 69.81% | -1.87% |
| historical_replay_after_common_prior | 1 | friday | holiday_gap_ge_4_calendar_days | 25 | 25 | 20.00% | 96.00% | 1.31% |
| historical_replay_after_common_prior | 1 | friday | not_holiday_gap | 1,346 | 1,346 | 21.69% | 93.24% | -0.71% |
| historical_replay_after_common_prior | 1 | not_friday | holiday_gap_ge_4_calendar_days | 505 | 505 | 36.44% | 31.49% | -0.29% |
| historical_replay_after_common_prior | 1 | not_friday | not_holiday_gap | 5,761 | 5,761 | 15.48% | 94.72% | -0.69% |
| historical_replay_after_common_prior | 2 | friday | holiday_gap_ge_4_calendar_days | 5 | 5 | 60.00% | 80.00% | 0.96% |
| historical_replay_after_common_prior | 2 | friday | not_holiday_gap | 214 | 214 | 37.38% | 77.10% | -1.33% |
| historical_replay_after_common_prior | 2 | not_friday | holiday_gap_ge_4_calendar_days | 53 | 53 | 60.38% | 30.19% | -0.82% |
| historical_replay_after_common_prior | 2 | not_friday | not_holiday_gap | 1,097 | 1,097 | 26.53% | 84.59% | -1.27% |
| historical_replay_after_common_prior | 3 | friday | holiday_gap_ge_4_calendar_days | 3 | 3 | 66.67% | 66.67% | 2.23% |
| historical_replay_after_common_prior | 3 | friday | not_holiday_gap | 63 | 63 | 46.03% | 65.08% | 0.06% |
| historical_replay_after_common_prior | 3 | not_friday | holiday_gap_ge_4_calendar_days | 31 | 31 | 32.26% | 35.48% | -0.58% |
| historical_replay_after_common_prior | 3 | not_friday | not_holiday_gap | 309 | 309 | 45.31% | 72.82% | -1.59% |
| historical_replay_after_common_prior | 4 | friday | not_holiday_gap | 33 | 33 | 57.58% | 63.64% | -0.11% |
| historical_replay_after_common_prior | 4 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 0.00% | 100.00% | -1.63% |
| historical_replay_after_common_prior | 4 | not_friday | not_holiday_gap | 148 | 148 | 41.22% | 75.00% | -0.98% |
| historical_replay_after_common_prior | 5_plus | friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 0.00% | 100.00% | -13.49% |
| historical_replay_after_common_prior | 5_plus | friday | not_holiday_gap | 33 | 33 | 39.39% | 63.64% | -3.60% |
| historical_replay_after_common_prior | 5_plus | not_friday | holiday_gap_ge_4_calendar_days | 4 | 4 | 75.00% | 25.00% | -2.16% |
| historical_replay_after_common_prior | 5_plus | not_friday | not_holiday_gap | 130 | 130 | 55.38% | 66.15% | -2.73% |
| train_2011_2019 | 1 | friday | holiday_gap_ge_4_calendar_days | 152 | 152 | 11.18% | 96.05% | -0.23% |
| train_2011_2019 | 1 | friday | not_holiday_gap | 2,767 | 2,767 | 17.38% | 94.18% | -0.61% |
| train_2011_2019 | 1 | not_friday | holiday_gap_ge_4_calendar_days | 155 | 155 | 20.00% | 89.68% | -1.08% |
| train_2011_2019 | 1 | not_friday | not_holiday_gap | 13,831 | 13,831 | 15.82% | 93.53% | -0.91% |
| train_2011_2019 | 2 | friday | holiday_gap_ge_4_calendar_days | 18 | 18 | 50.00% | 72.22% | 2.63% |
| train_2011_2019 | 2 | friday | not_holiday_gap | 800 | 800 | 59.75% | 79.88% | -0.81% |
| train_2011_2019 | 2 | not_friday | holiday_gap_ge_4_calendar_days | 19 | 19 | 31.58% | 73.68% | -0.01% |
| train_2011_2019 | 2 | not_friday | not_holiday_gap | 1,878 | 1,878 | 29.71% | 77.48% | -1.46% |
| train_2011_2019 | 3 | friday | holiday_gap_ge_4_calendar_days | 9 | 9 | 33.33% | 77.78% | 3.05% |
| train_2011_2019 | 3 | friday | not_holiday_gap | 115 | 115 | 43.48% | 73.04% | -1.57% |
| train_2011_2019 | 3 | not_friday | holiday_gap_ge_4_calendar_days | 11 | 11 | 45.45% | 72.73% | 2.39% |
| train_2011_2019 | 3 | not_friday | not_holiday_gap | 914 | 914 | 35.67% | 75.71% | -2.63% |
| train_2011_2019 | 4 | friday | holiday_gap_ge_4_calendar_days | 6 | 6 | 50.00% | 50.00% | -0.53% |
| train_2011_2019 | 4 | friday | not_holiday_gap | 59 | 59 | 55.93% | 50.85% | -0.76% |
| train_2011_2019 | 4 | not_friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 100.00% | 0.00% | 0.00% |
| train_2011_2019 | 4 | not_friday | not_holiday_gap | 314 | 314 | 40.76% | 70.70% | -3.16% |
| train_2011_2019 | 5_plus | friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 100.00% | 0.00% | 0.00% |
| train_2011_2019 | 5_plus | friday | not_holiday_gap | 96 | 96 | 61.46% | 46.88% | 0.49% |
| train_2011_2019 | 5_plus | not_friday | holiday_gap_ge_4_calendar_days | 7 | 7 | 71.43% | 14.29% | -2.24% |
| train_2011_2019 | 5_plus | not_friday | not_holiday_gap | 346 | 346 | 63.58% | 41.33% | -0.42% |
| vendor_tail_audit | 1 | friday | not_holiday_gap | 140 | 114 | 14.04% | 77.14% | -1.67% |
| vendor_tail_audit | 1 | not_friday | holiday_gap_ge_4_calendar_days | 26 | 26 | 19.23% | 96.15% | -0.98% |
| vendor_tail_audit | 1 | not_friday | not_holiday_gap | 797 | 773 | 15.06% | 97.74% | -0.83% |
| vendor_tail_audit | 2 | friday | not_holiday_gap | 16 | 12 | 8.33% | 75.00% | -1.25% |
| vendor_tail_audit | 2 | not_friday | holiday_gap_ge_4_calendar_days | 3 | 3 | 33.33% | 100.00% | 0.16% |
| vendor_tail_audit | 2 | not_friday | not_holiday_gap | 126 | 119 | 23.81% | 92.86% | 0.23% |
| vendor_tail_audit | 3 | friday | not_holiday_gap | 3 | 2 | 50.00% | 33.33% | -1.75% |
| vendor_tail_audit | 3 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 100.00% | 100.00% | 16.01% |
| vendor_tail_audit | 3 | not_friday | not_holiday_gap | 30 | 25 | 33.33% | 96.67% | 0.73% |
| vendor_tail_audit | 4 | friday | not_holiday_gap | 4 | 1 | 0.00% | 25.00% | -4.12% |
| vendor_tail_audit | 4 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 100.00% | 0.00% | 0.00% |
| vendor_tail_audit | 4 | not_friday | not_holiday_gap | 7 | 7 | 57.14% | 42.86% | -1.20% |
| vendor_tail_audit | 5_plus | friday | not_holiday_gap | 1 | 1 | 100.00% | 100.00% | -11.64% |
| vendor_tail_audit | 5_plus | not_friday | not_holiday_gap | 6 | 6 | 16.67% | 83.33% | 0.69% |

## Predeclared 2015 standalone stress era

This table is printed separately so the pooled 2011–2019 train average cannot hide crisis behaviour.

| Board | Signals | Inclusive continuation | Observed-bar sensitivity | Fill / all | Joint state 0bp | Joint state 60bp |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 6,128 | 23.22% | 23.22% | 91.53% | 0.21% | -0.34% |
| 2 | 1,426 | 47.05% | 47.05% | 76.44% | -0.98% | -1.44% |
| 3 | 671 | 32.49% | 32.49% | 77.79% | -2.72% | -3.19% |
| 4 | 217 | 36.87% | 36.87% | 69.12% | -3.64% | -4.05% |
| 5_plus | 263 | 69.96% | 69.96% | 35.36% | 0.57% | 0.36% |

## Vendor descriptive stratum

- Valid observed-session rows: 3,102; excluded clone rows: 818 across 11 dates.
- Retrospectively fetched/not-proven-PIT rows: 1,205; joined curated event rows: 933.
- Absolute seal fund is unnormalised; all vendor-field verdicts remain descriptive.

## Honesty notes

- `historical_replay_after_common_prior` is labelled replay, never unseen test.
- The 0/30/60/100 bp grid is a round-trip friction sensitivity, not a live fill model.
- Date- and board-run-cluster intervals accompany pooled means; clustered names on one board-festival date are not treated as independent evidence.
- No construction receives ranking, sizing, gating, or trading authority.

## UNTESTED VARIANTS

- full-market small-cap universe: zt_pool names without local nominal OHLCV are outside this curated slice
- historically correct ST and risk-warning membership; all current-snapshot ST intersections are excluded
- BSE listings and their 30 percent band
- first 60 listed sessions, including registration-era no-limit IPO sessions
- pre-close and same-day near-limit executable entries
- C-POSTGAP returns using a real 09:30 trade or first-five-minute VWAP
- opening-auction matched volume, unmatched imbalance, queue depth, order priority, and partial fills
- first-touch time, cumulative sealed minutes, final seal time, and seal-break or reseal entries
- PIT THS concept membership, sector concentration, and theme leader-follower topology
- PIT seal-wall and LHB participant fields outside their short and currently unreliable vendor windows
- free-float shares, capacity, commissions, stamp duty, and slippage outside the stated cost grid
- delisted-name-complete history and survivorship-free down-limit release reversals
- cross-name portfolio dependence, theme caps, and crowded-factor drawdown
- tree, boosting, hazard, and nested-validation models
- corporate-action truth beyond the inherited nominal-price open-gap suppression heuristic
