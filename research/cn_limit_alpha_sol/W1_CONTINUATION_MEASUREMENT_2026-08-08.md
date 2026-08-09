# CN limit-up continuation — SOL Wave-1 deterministic receipt

**Receipt date:** 2026-08-08
**Authority:** `none_research_display_only`
**Model/definition:** `sol_w1_era_aware_traded_ipo_canonical_vendor_2026-08-08`

> Curated-slice warning: this receipt does not describe the full 打板 universe. The vendor pool has 1,607 distinct tickers, but only 580 (36.09%) overlap the local nominal OHLCV slice.

## Frozen contract

- `C0`: tolerant board close on D to the common CN calendar successor. A missing/halted ticker bar stays in the primary denominator as no board; observed-bar-only results are a named sensitivity.
- `C-AUCTION`: features stop at D close. The candidate fill is D+1 official open; an open within the tolerant upper-limit cushion is an unfilled queue. The realised D+1 gap is not a selection filter.
- `C-POSTGAP`: realised auction gap conditions next-board probability only. There is deliberately no daily-OHLCV return claim because 09:30/first-five-minute execution is absent.
- T+1 exits begin no earlier than D+2 for a D+1-open entry. Every exit resolves on exact market sessions; a missing bar is unresolved, and lower-limit carry advances one market session at a time.
- Positive finite ticker volume is mandatory for signal, next-session tradability, fill, every fixed exit, every seal-state check, and every lower-limit carry step. Zero volume is halt/no-trade, never fill.
- The IPO clock counts positive-volume observations on exact market sessions, not raw rows. Main listings from 2023-04-10, ChiNext listings from 2020-08-24, and STAR from inception quarantine five traded sessions; earlier main/ChiNext listings quarantine listing day only. Start/end filtering retains full listing context.
- Vendor identity is canonicalized before coverage and joining: uppercase `.SH` aliases map to the repo's `.SS` suffix.
- Main board is primary; ChiNext band eras are separate secondary cohorts; STAR is descriptive; BSE/ST are untested.

## Data and event inventory

- Raw files: 1,842 scanned for clock/volume support; 1,841 measured; 0 errors; 1 current-ST intersections excluded from measurement.
- Measured raw rows: 6,760,225; all-file support rows: 6,767,465; sessions 1990-12-19 to 2026-08-07.
- Common clock: 3,786 sessions; >=50-name raw consensus 3,786; set-identical=True; 2014-12-24 successor=2014-12-25.
- 2014-12-25 raw support: 983 names, 894 with positive volume. The clock anchor has 3,780 positive-volume sessions and 6 nonpositive placeholders; its index, not volume, defines the clock.
- Zero/missing-volume census: 277,152 raw rows total, 133,854 in-window; 133,107 otherwise price-eligible rows and 1 tolerant board-price rows were reclassified.
- Zero-volume downstream states: 456 next sessions; exact-exit unresolved counts {"seal_state_next_open": 342, "tplus1_legal_close": 268, "tplus1_legal_open": 265, "tplus2_close": 370, "tplus4_close": 524}. Off-calendar positive-volume otherwise-eligible rows: 0.
- Registration-era main IPO quarantine: 41 files and 204 in-window positive-volume no-limit observations; boundary 2023-04-10.
- IPO traded-session regimes (files): {"chinext_pre_reform_listing_day_only": 233, "chinext_registration_first_five": 120, "main_historical_listing_day_only": 1204, "main_registration_first_five": 41, "star_from_inception_first_five": 243}; raw rows before the first positive-volume session: 450,434.
- Tolerant boards: 55,631; strict boards: 29,351; marginal tolerance rows: 26,280.
- Measured after boundary purge: 55,140 signals, 3,699 date clusters, 44,177 board-run clusters.
- `china_zt_pool` vendor strata use valid observed sessions only: 0 clone dates are excluded, missing sessions are not imputed, and retrospective rows are explicitly stamped non-PIT.
- Vendor alias reconciliation: 1,770 literal names become 1,607 canonical names; 580 overlap raw OHLCV, and 1,187/3,102 valid rows have local prices.
- Content-addressed input/config fingerprint: `cb36dad39587ebdd230481da3c5932f22c08642f227a69c63fbc24e6da835d51`. The hash covers the exact worktree file consumed; the physically repaired zt-pool artifact contains no off-calendar clone rows.

## Construction verdicts

### C0_TRUE_NEXT_SESSION

- Verdict: **MEASURED_BASE_RATE_NO_PROMOTION**
- Headline: n=7,637; mean=17.98%; date-cluster 95% CI=[15.28%, 20.67%]
- Kill scope: none
- Measured: tolerant close-to-close board continuation on the common CN calendar successor; missing/halted bars retained as failures, with observed-bar-only sensitivity
- Not measured: see ore ledger below

### C_AUCTION

- Verdict: **NEGATIVE_EVENT_LEVEL_N1_N2_EXPECTANCY_SPECIFIC_ONLY**
- Headline: n=8,994; mean=-0.75%; date-cluster 95% CI=[-1.10%, -0.39%]
- Kill scope: Only the N=1/2 main-board event-level candidate-row expectancy with nonfills cash=0, seal-state-next-open exit at 60bp in historical replay is negative; it is not a portfolio-return verdict.
- Measured: N=1/2 primary event-level candidate-row expectancy after a D-close decision, plus separately labelled all-N reference and N>=3 exploratory books
- Not measured: realised gap as a selection feature

### C_AUCTION_PRIMARY_N1_N2_PORTFOLIO

- Verdict: **NEGATIVE_SELF_FINANCING_PROXY_SPECIFIC_ONLY**
- Headline: n=590; mean=-0.20%; date-cluster 95% CI=[-0.28%, -0.12%]
- Kill scope: Only the frozen N=1/2 main-board equal-available-cash, no-duplicate-ticker, realised-exit-cost-basis paper book with seal-state exit at 60bp in historical replay.
- Measured: self-financing equal-available-cash paper book with same-ticker dedupe, exact cash reservation, all five exits, four costs, and daily realised-exit metrics
- Not measured: daily mark-to-market NAV, theme/sector constraints, auction capacity, or partial fills

### C_AUCTION_N

- Verdict: **NEGATIVE_ALL_PRIMARY_ENDPOINT_STRATA_SPECIFIC_ONLY**
- Headline: n/a
- Kill scope: At locked-replay seal-state/60bp only, negative cells: 1, 2. Other exits/costs and unlisted cells are not killed.
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

## Main N=1/2 historical-replay fill funnel

| Signals | Exact tradable next bar | Halt/missing bar | Zero-volume no-trade | Upper-limit queue | Candidate fills | Fill / all signals |
|---:|---:|---:|---:|---:|---:|---:|
| 9,006 | 8,996 | 0 | 10 | 998 | 7,998 | 88.81% |

The event-level candidate-row expectancy keeps mature nonfills at cash=0 and explicitly equals P(fill) × E(net | resolved fill). It is not a portfolio return. Filled-conditional distributions remain diagnostics. The separately printed self-financing proxy reserves cash until exact exits.

## N=1/2 overlap and cash-accounting replay — 60bp

The no-duplicate row/date-equal columns are sequential-trade/cohort expectancy only. The cash-accounted columns invest available cash equally on each entry date and reserve it through exact exits. They remain a cost-basis, no-theme/no-capacity proxy—not a capital/theme-complete portfolio.

| Exit | Accepted resolved | Same-ticker overlap cash | Row-weighted event | Date-equal cohort | Capital unavailable | Final NAV | Cumulative realised | Daily realised mean | Mean invested |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| tplus1_legal_open | 7,127 | 863 | -0.62% | -0.78% | 579 | 0.0311 | -96.89% | -0.57% | 50.40% |
| tplus1_legal_close | 7,127 | 863 | -0.37% | -0.51% | 85 | 0.2821 | -71.79% | -0.21% | 80.59% |
| tplus2_close | 6,911 | 1,082 | -0.32% | -0.46% | 597 | 0.5259 | -47.41% | -0.10% | 85.49% |
| tplus4_close | 6,380 | 1,609 | -0.18% | -0.37% | 301 | 0.3561 | -64.39% | -0.16% | 80.85% |
| seal_state_next_open | 7,079 | 909 | -0.65% | -0.86% | 22 | 0.2975 | -70.25% | -0.20% | 88.95% |

## Fixed pre-auction rider books — locked replay primary comparison, seal-state exit, 60bp

These are separate one-dimensional predeclared strata. The JSON includes every fixed exit and 0/30/60/100bp; this compact table is the seal-state/60bp primary comparison only. No crossed combination or best-cell tuning was run.

| Construction | Population | Fixed stratum | Candidates | Mature book | Fill / mature | Event-level cash-zero mean | Date-cluster 95% CI | Cell verdict |
|---|---|---|---:|---:|---:|---:|---:|---|
| C_AUCTION_N | primary_n1_n2 | 1 | 7,637 | 7,627 | 90.14% | -0.66% | [-1.02%, -0.30%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_N | primary_n1_n2 | 2 | 1,369 | 1,367 | 81.27% | -1.26% | [-2.08%, -0.44%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_N | exploratory_n3plus | 3 | 406 | 405 | 68.64% | -1.26% | [-2.33%, -0.18%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_N | exploratory_n3plus | 4 | 182 | 181 | 72.93% | -0.86% | [-2.51%, 0.79%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_N | exploratory_n3plus | 5_plus | 168 | 168 | 64.88% | -2.95% | [-4.76%, -1.14%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ONE_PRICE_D_CLOSE | primary_n1_n2_population | no | 8,585 | 8,573 | 90.96% | -0.75% | [-1.12%, -0.39%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ONE_PRICE_D_CLOSE | primary_n1_n2_population | yes | 421 | 421 | 44.66% | -0.64% | [-1.37%, 0.10%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | primary_n1_n2_population | 0_10_to_0_35 | 285 | 285 | 85.96% | -0.78% | [-1.61%, 0.06%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | primary_n1_n2_population | 0_35_to_0_70 | 1,505 | 1,504 | 78.59% | -0.80% | [-1.41%, -0.18%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | primary_n1_n2_population | gt_0_70 | 6,763 | 6,752 | 93.99% | -0.75% | [-1.16%, -0.35%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_INTRADAY_RANGE_D_CLOSE | primary_n1_n2_population | le_0_10 | 453 | 453 | 47.02% | -0.54% | [-1.24%, 0.15%] | INCONCLUSIVE_DATE_CLUSTER_CI |
| C_AUCTION_ECOLOGY_D_CLOSE | primary_n1_n2_population | cold | 2,299 | 2,299 | 93.52% | -0.64% | [-1.03%, -0.25%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ECOLOGY_D_CLOSE | primary_n1_n2_population | hot | 2,767 | 2,763 | 79.15% | -0.82% | [-1.59%, -0.05%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |
| C_AUCTION_ECOLOGY_D_CLOSE | primary_n1_n2_population | neutral | 3,940 | 3,932 | 92.80% | -0.76% | [-1.32%, -0.20%] | NEGATIVE_DATE_CLUSTER_CI_SPECIFIC_CELL |

## Frozen crowd clock

| Split | Population | Board | Friday | Holiday gap | Signals | Mature book | Inclusive continuation | Fill / all | Event-level seal-state 60bp |
|---|---|---:|---|---|---:|---:|---:|---:|---:|
| calibration_2020_2023 | primary_n1_n2 | 1 | friday | holiday_gap_ge_4_calendar_days | 220 | 220 | 25.45% | 95.00% | 0.46% |
| calibration_2020_2023 | primary_n1_n2 | 1 | friday | not_holiday_gap | 1,968 | 1,968 | 18.39% | 94.31% | -0.65% |
| calibration_2020_2023 | primary_n1_n2 | 1 | not_friday | holiday_gap_ge_4_calendar_days | 125 | 125 | 16.80% | 93.60% | -0.65% |
| calibration_2020_2023 | primary_n1_n2 | 1 | not_friday | not_holiday_gap | 9,503 | 9,498 | 12.68% | 96.22% | -0.83% |
| calibration_2020_2023 | primary_n1_n2 | 2 | friday | holiday_gap_ge_4_calendar_days | 17 | 17 | 23.53% | 82.35% | -3.38% |
| calibration_2020_2023 | primary_n1_n2 | 2 | friday | not_holiday_gap | 262 | 262 | 37.79% | 79.77% | -1.49% |
| calibration_2020_2023 | primary_n1_n2 | 2 | not_friday | holiday_gap_ge_4_calendar_days | 20 | 20 | 45.00% | 60.00% | -0.16% |
| calibration_2020_2023 | primary_n1_n2 | 2 | not_friday | not_holiday_gap | 1,347 | 1,344 | 27.39% | 86.71% | -1.23% |
| calibration_2020_2023 | exploratory_n3plus | 3 | friday | holiday_gap_ge_4_calendar_days | 5 | 5 | 20.00% | 80.00% | -1.45% |
| calibration_2020_2023 | exploratory_n3plus | 3 | friday | not_holiday_gap | 85 | 84 | 38.82% | 78.82% | -2.07% |
| calibration_2020_2023 | exploratory_n3plus | 3 | not_friday | holiday_gap_ge_4_calendar_days | 4 | 4 | 75.00% | 50.00% | 0.42% |
| calibration_2020_2023 | exploratory_n3plus | 3 | not_friday | not_holiday_gap | 387 | 386 | 41.09% | 78.04% | -1.46% |
| calibration_2020_2023 | exploratory_n3plus | 4 | friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 50.00% | 100.00% | 12.99% |
| calibration_2020_2023 | exploratory_n3plus | 4 | friday | not_holiday_gap | 31 | 30 | 58.06% | 70.97% | -0.20% |
| calibration_2020_2023 | exploratory_n3plus | 4 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 100.00% | 0.00% | 0.00% |
| calibration_2020_2023 | exploratory_n3plus | 4 | not_friday | not_holiday_gap | 162 | 162 | 48.77% | 69.75% | -0.65% |
| calibration_2020_2023 | exploratory_n3plus | 5_plus | friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 50.00% | 100.00% | -14.11% |
| calibration_2020_2023 | exploratory_n3plus | 5_plus | friday | not_holiday_gap | 44 | 43 | 47.73% | 63.64% | -3.35% |
| calibration_2020_2023 | exploratory_n3plus | 5_plus | not_friday | not_holiday_gap | 159 | 157 | 52.83% | 69.81% | -2.16% |
| historical_replay_after_common_prior | primary_n1_n2 | 1 | friday | holiday_gap_ge_4_calendar_days | 25 | 25 | 20.00% | 96.00% | 1.31% |
| historical_replay_after_common_prior | primary_n1_n2 | 1 | friday | not_holiday_gap | 1,346 | 1,346 | 21.69% | 93.02% | -0.71% |
| historical_replay_after_common_prior | primary_n1_n2 | 1 | not_friday | holiday_gap_ge_4_calendar_days | 505 | 505 | 36.44% | 31.49% | -0.29% |
| historical_replay_after_common_prior | primary_n1_n2 | 1 | not_friday | not_holiday_gap | 5,761 | 5,751 | 15.48% | 94.60% | -0.69% |
| historical_replay_after_common_prior | primary_n1_n2 | 2 | friday | holiday_gap_ge_4_calendar_days | 5 | 5 | 60.00% | 80.00% | 0.96% |
| historical_replay_after_common_prior | primary_n1_n2 | 2 | friday | not_holiday_gap | 214 | 214 | 37.38% | 77.10% | -1.33% |
| historical_replay_after_common_prior | primary_n1_n2 | 2 | not_friday | holiday_gap_ge_4_calendar_days | 53 | 53 | 60.38% | 30.19% | -0.82% |
| historical_replay_after_common_prior | primary_n1_n2 | 2 | not_friday | not_holiday_gap | 1,097 | 1,095 | 26.53% | 84.59% | -1.27% |
| historical_replay_after_common_prior | exploratory_n3plus | 3 | friday | holiday_gap_ge_4_calendar_days | 3 | 3 | 66.67% | 66.67% | 2.23% |
| historical_replay_after_common_prior | exploratory_n3plus | 3 | friday | not_holiday_gap | 63 | 63 | 46.03% | 65.08% | 0.06% |
| historical_replay_after_common_prior | exploratory_n3plus | 3 | not_friday | holiday_gap_ge_4_calendar_days | 31 | 31 | 32.26% | 35.48% | -0.58% |
| historical_replay_after_common_prior | exploratory_n3plus | 3 | not_friday | not_holiday_gap | 309 | 308 | 45.31% | 72.82% | -1.63% |
| historical_replay_after_common_prior | exploratory_n3plus | 4 | friday | not_holiday_gap | 33 | 33 | 57.58% | 63.64% | -0.11% |
| historical_replay_after_common_prior | exploratory_n3plus | 4 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 0.00% | 100.00% | -1.63% |
| historical_replay_after_common_prior | exploratory_n3plus | 4 | not_friday | not_holiday_gap | 148 | 147 | 41.22% | 75.00% | -1.02% |
| historical_replay_after_common_prior | exploratory_n3plus | 5_plus | friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 0.00% | 100.00% | -13.49% |
| historical_replay_after_common_prior | exploratory_n3plus | 5_plus | friday | not_holiday_gap | 33 | 33 | 39.39% | 63.64% | -3.60% |
| historical_replay_after_common_prior | exploratory_n3plus | 5_plus | not_friday | holiday_gap_ge_4_calendar_days | 4 | 4 | 75.00% | 25.00% | -2.16% |
| historical_replay_after_common_prior | exploratory_n3plus | 5_plus | not_friday | not_holiday_gap | 130 | 130 | 55.38% | 66.15% | -2.73% |
| train_2011_2019 | primary_n1_n2 | 1 | friday | holiday_gap_ge_4_calendar_days | 152 | 151 | 11.18% | 91.45% | -0.28% |
| train_2011_2019 | primary_n1_n2 | 1 | friday | not_holiday_gap | 2,761 | 2,734 | 17.28% | 91.81% | -0.76% |
| train_2011_2019 | primary_n1_n2 | 1 | not_friday | holiday_gap_ge_4_calendar_days | 155 | 155 | 20.00% | 83.23% | -1.08% |
| train_2011_2019 | primary_n1_n2 | 1 | not_friday | not_holiday_gap | 13,855 | 13,696 | 15.82% | 92.32% | -0.99% |
| train_2011_2019 | primary_n1_n2 | 2 | friday | holiday_gap_ge_4_calendar_days | 18 | 17 | 50.00% | 72.22% | 1.90% |
| train_2011_2019 | primary_n1_n2 | 2 | friday | not_holiday_gap | 804 | 796 | 59.70% | 77.86% | -0.84% |
| train_2011_2019 | primary_n1_n2 | 2 | not_friday | holiday_gap_ge_4_calendar_days | 19 | 19 | 31.58% | 57.89% | -0.16% |
| train_2011_2019 | primary_n1_n2 | 2 | not_friday | not_holiday_gap | 1,874 | 1,838 | 29.72% | 75.13% | -1.62% |
| train_2011_2019 | exploratory_n3plus | 3 | friday | holiday_gap_ge_4_calendar_days | 9 | 9 | 33.33% | 55.56% | 2.07% |
| train_2011_2019 | exploratory_n3plus | 3 | friday | not_holiday_gap | 115 | 113 | 43.48% | 71.30% | -2.44% |
| train_2011_2019 | exploratory_n3plus | 3 | not_friday | holiday_gap_ge_4_calendar_days | 11 | 11 | 45.45% | 45.45% | 0.37% |
| train_2011_2019 | exploratory_n3plus | 3 | not_friday | not_holiday_gap | 916 | 911 | 35.81% | 73.69% | -2.65% |
| train_2011_2019 | exploratory_n3plus | 4 | friday | holiday_gap_ge_4_calendar_days | 6 | 6 | 50.00% | 50.00% | -0.53% |
| train_2011_2019 | exploratory_n3plus | 4 | friday | not_holiday_gap | 60 | 59 | 56.67% | 51.67% | -1.10% |
| train_2011_2019 | exploratory_n3plus | 4 | not_friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 100.00% | 0.00% | 0.00% |
| train_2011_2019 | exploratory_n3plus | 4 | not_friday | not_holiday_gap | 316 | 308 | 40.82% | 69.30% | -3.47% |
| train_2011_2019 | exploratory_n3plus | 5_plus | friday | holiday_gap_ge_4_calendar_days | 2 | 2 | 100.00% | 0.00% | 0.00% |
| train_2011_2019 | exploratory_n3plus | 5_plus | friday | not_holiday_gap | 97 | 95 | 61.86% | 41.24% | 0.53% |
| train_2011_2019 | exploratory_n3plus | 5_plus | not_friday | holiday_gap_ge_4_calendar_days | 7 | 7 | 71.43% | 14.29% | -2.24% |
| train_2011_2019 | exploratory_n3plus | 5_plus | not_friday | not_holiday_gap | 349 | 344 | 63.32% | 35.53% | -0.44% |
| vendor_tail_audit | primary_n1_n2 | 1 | friday | not_holiday_gap | 140 | 114 | 14.04% | 76.43% | -1.66% |
| vendor_tail_audit | primary_n1_n2 | 1 | not_friday | holiday_gap_ge_4_calendar_days | 26 | 26 | 19.23% | 96.15% | -0.98% |
| vendor_tail_audit | primary_n1_n2 | 1 | not_friday | not_holiday_gap | 797 | 772 | 15.06% | 97.74% | -0.84% |
| vendor_tail_audit | primary_n1_n2 | 2 | friday | not_holiday_gap | 16 | 12 | 8.33% | 75.00% | -1.25% |
| vendor_tail_audit | primary_n1_n2 | 2 | not_friday | holiday_gap_ge_4_calendar_days | 3 | 3 | 33.33% | 100.00% | 0.16% |
| vendor_tail_audit | primary_n1_n2 | 2 | not_friday | not_holiday_gap | 126 | 118 | 23.81% | 92.86% | 0.27% |
| vendor_tail_audit | exploratory_n3plus | 3 | friday | not_holiday_gap | 3 | 2 | 50.00% | 33.33% | -1.75% |
| vendor_tail_audit | exploratory_n3plus | 3 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 100.00% | 100.00% | 16.01% |
| vendor_tail_audit | exploratory_n3plus | 3 | not_friday | not_holiday_gap | 30 | 25 | 33.33% | 96.67% | 0.73% |
| vendor_tail_audit | exploratory_n3plus | 4 | friday | not_holiday_gap | 4 | 1 | 0.00% | 25.00% | -4.12% |
| vendor_tail_audit | exploratory_n3plus | 4 | not_friday | holiday_gap_ge_4_calendar_days | 1 | 1 | 100.00% | 0.00% | 0.00% |
| vendor_tail_audit | exploratory_n3plus | 4 | not_friday | not_holiday_gap | 7 | 7 | 57.14% | 42.86% | -1.20% |
| vendor_tail_audit | exploratory_n3plus | 5_plus | friday | not_holiday_gap | 1 | 1 | 100.00% | 100.00% | -11.64% |
| vendor_tail_audit | exploratory_n3plus | 5_plus | not_friday | not_holiday_gap | 6 | 6 | 16.67% | 83.33% | 0.69% |

## Predeclared 2015 standalone stress era

This table is printed separately so the pooled 2011–2019 train average cannot hide crisis behaviour.

| Population | Board | Signals | Inclusive continuation | Observed-bar sensitivity | Fill / all | Event-level state 0bp | Event-level state 60bp |
|---|---:|---:|---:|---:|---:|---:|---:|
| primary_n1_n2 | 1 | 6,127 | 23.23% | 23.56% | 90.09% | 0.16% | -0.38% |
| primary_n1_n2 | 2 | 1,426 | 47.05% | 47.76% | 74.96% | -1.05% | -1.50% |
| exploratory_n3plus | 3 | 671 | 32.49% | 32.93% | 76.45% | -2.77% | -3.23% |
| exploratory_n3plus | 4 | 217 | 36.87% | 37.04% | 68.66% | -3.69% | -4.10% |
| exploratory_n3plus | 5_plus | 263 | 69.96% | 71.60% | 33.08% | 0.60% | 0.40% |

## Vendor descriptive stratum

- Valid observed-session rows: 3,102; excluded clone rows: 0 across 0 dates.
- Retrospectively fetched/not-proven-PIT rows: 1,205; joined curated event rows: 1,156.
- Ticker canonicalization recovered 223 joins beyond the literal-suffix sensitivity (933 literal joins).
- Absolute seal fund is unnormalised; all vendor-field verdicts remain descriptive.

## ORE coverage ledger

| Required construction family | Status | Exact scope |
|---|---|---|
| Five-axis continuation | UNTESTED_NOT_SILENTLY_KILLED | vol_z20, runup_5, gap_pct, dist_52w_low, consec_up_days |
| Strict board definition | MEASURED_SEALED_CLOSE_SENSITIVITY | true-next-session probability and event-level cash-zero book |
| Ecology extensions | UNTESTED_NOT_SILENTLY_KILLED | active ceiling, 3-session acceleration, leader-failure shock |
| N>=3 riders | EXPLORATORY_ONLY_NO_PRIMARY_VERDICT | board-count cells remain visible but cannot drive Packet B |
| Portfolio constraints | UNTESTED_BEYOND_FROZEN_CASH_RESERVATION_PROXY | mark-to-market, theme/sector caps, capacity, partial fills |

## Honesty notes

- `historical_replay_after_common_prior` is labelled replay, never unseen test.
- `EVENT_LEVEL_CANDIDATE_ROW_EXPECTANCY_NOT_A_PORTFOLIO_RETURN` is the exact label for cash-zero signal rows; the no-duplicate date-equal series is cohort expectancy, and only the separate cash-reservation proxy is self-financing.
- The self-financing proxy values open positions at cost until realised exits; interim drawdown, theme concentration, capacity, and mark-to-market risk remain unmeasured.
- IPO listing dates are inferred from first positive-volume common-session raw observations; no complete official listing-master claim is made. Vendor identity normalization is limited to the explicit `.SH`/`.SS` alias.
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
- complete five-axis continuation strata: vol_z20, runup_5, gap_pct, dist_52w_low, and consec_up_days
- strict first-touch and intraday seal-path sensitivity beyond the measured strict sealed-close sensitivity
- active-ceiling, 3-session acceleration, and leader-failure-shock ecology constructions
- N>=3 continuation riders beyond explicitly exploratory descriptive cells
- capital/theme/capacity-complete portfolio simulation beyond the frozen self-financing cash-reservation proxy
- complete official listing-date master beyond first positive-volume common-session inference
- vendor security-master identity beyond the explicit .SH to .SS suffix canonicalization
