# Rotation Time Machine Extended Pattern Gauntlet

Generated from local Time Machine, sector ETF, m-tier, FRED, and Yahoo-cache artifacts. Latest sector Time Machine date in this run: `2026-07-01`.

## Bottom Line

The deeper run strengthens one core conclusion and prunes several tempting but weak ideas:

1. **Keep early episode onsets.** Sector `in` onsets remain the cleanest tradable timing pattern after next-session entry. The signal decays by confirmed dates, so confirmation is evidence, not an entry trigger.
2. **Use mature leadership as a caution/trim condition.** Old `Leading` states and right-side rollovers are more useful for avoiding stale leadership than for finding new buys.
3. **Use m-tier/direct and family breadth as confluence, not origination.** Direct `us_sector_*` momentum is useful at 21d, but broad family sponsorship levels are not reliable standalone rank signals.
4. **Use inverse pressure as a filter, not a standalone signal.** It helps explain schedules and risk budgets, but empirical inverse filters alone are not robust enough to originate trades.
5. **Reject raw continuous coordinate chasing.** `rs_ratio`, `pos`, and family sponsorship levels have too much aging-leadership mean reversion when used as top-minus-bottom ranks.

## Gauntlet Criteria

- All forward tests use next-session-close entry and sector ETF forward return relative to the equal-weight sector ETF cross-section.
- `KEEP`: 10d n >= 80, mean payoff > 0.25%, HAC t >= 2.0, hit >= 54%, and split-half minimum mean > 0.
- `WATCH`: positive but not fully gated, or useful context with lower support/stability.
- `PRUNE`: weak sign, weak t, low hit rate, bad split stability, too few observations, or economically redundant after a stronger parent pattern.

## Pattern Cards

These cards combine the measured result with a first-principles explanation and the wiring decision.

| decision   | pattern                       | family   | intent   |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d | first_principles                                                                                                               | action                                   |
|:-----------|:------------------------------|:---------|:---------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|:-------------------------------------------------------------------------------------------------------------------------------|:-----------------------------------------|
| KEEP       | onset_in_plus_same_complex    | combo    | long     |     186 | 0.59%      |   3.418 | 59.1%     | 0.57%           | 0.46%      |   2.268 | Sector rotations with complex-level support should persist better than isolated single-sector pops.                            | Use as shadow signal / alert component   |
| KEEP       | episode_onset_in_peak_ge_1_5  | episode  | long     |     342 | 0.54%      |   3.378 | 59.1%     | 0.43%           | 0.43%      |   2.417 | Higher episode acceleration should mark more urgent institutional repricing.                                                   | Use as shadow signal / alert component   |
| KEEP       | episode_onset_in              | episode  | long     |     356 | 0.53%      |   3.467 | 58.7%     | 0.43%           | 0.44%      |   2.658 | Fresh in-episode means a sector is beginning to attract relative sponsorship before the move is fully crowded.                 | Use as shadow signal / alert component   |
| WATCH      | cyclical_onset_hy_tightening  | macro    | long     |      72 | 1.03%      |   2.435 | 68.1%     | 0.51%           | 0.88%      |   1.907 | Cyclical/rates/commodity sectors should prefer easing credit spreads.                                                          | Keep context-only; accrue forward ledger |
| WATCH      | episode_onset_out             | episode  | short    |     390 | 0.24%      |   1.948 | 56.2%     | 0.21%           | 0.04%      |   0.215 | Out episodes should mark capital leaving a sector before full underperformance is visible.                                     | Keep context-only; accrue forward ledger |
| WATCH      | direct_us_sector_mom_pos      | m_tier   | long     |    5185 | 0.09%      |   1.044 | 49.9%     | 0.07%           | 0.18%      |   1.005 | The m-tier sector proxy should confirm ETF-level sponsorship when it points in the same direction.                             | Keep context-only; accrue forward ledger |
| WATCH      | mom_cross_down_right          | quadrant | short    |    2103 | 0.04%      |   0.673 | 51.5%     | -0.01%          | 0.15%      |   1.559 | A momentum cross-down while still right of center is an early exit warning.                                                    | Keep context-only; accrue forward ledger |
| PRUNE      | energy_onset_oil_up           | macro    | long     |      27 | 1.70%      |   3.919 | 63.0%     | 1.68%           | 1.44%      |   4.718 | Energy ETF rotations should be more durable when crude itself is confirming.                                                   | Do not wire; display or ignore only      |
| PRUNE      | old_leading_fade              | quadrant | short    |       6 | 0.90%      |         | 100.0%    | 0.86%           | 1.20%      |         | Very old leadership should be even more vulnerable to mean reversion and profit taking.                                        | Do not wire; display or ignore only      |
| PRUNE      | utilities_re_onset_rates_down | macro    | long     |      35 | 0.86%      |   5.897 | 74.3%     | 0.56%           | 0.61%      |   3.937 | Rate-sensitive sectors should prefer falling yields.                                                                           | Do not wire; display or ignore only      |
| PRUNE      | financials_onset_rates_up     | macro    | long     |      22 | 0.66%      |   3.772 | 72.7%     | 0.66%           | 0.27%      |         | Financials often reprice with rising long yields and/or reflation expectations.                                                | Do not wire; display or ignore only      |
| PRUNE      | onset_in_plus_inverse_out     | combo    | long     |      30 | 0.58%      |   1.812 | 70.0%     | 0.10%           | -0.08%     |  -0.521 | The highest-quality rotations should have both a source of funds and a destination.                                            | Do not wire; display or ignore only      |
| PRUNE      | episode_onset_in_fast_confirm | episode  | long     |      45 | 0.48%      |   1.197 | 55.6%     | 0.24%           | 0.91%      |   1.539 | Fast confirmation implies broad enough follow-through that the onset was not a one-day artifact.                               | Do not wire; display or ignore only      |
| PRUNE      | defensive_onset_vix_pressure  | macro    | long     |      61 | 0.38%      |   0.953 | 59.0%     | -0.56%          | 0.16%      |   0.478 | Defensive sectors should benefit when volatility is high or rising.                                                            | Do not wire; display or ignore only      |
| PRUNE      | onset_in_plus_family_chg      | combo    | long     |      68 | 0.26%      |   0.843 | 51.5%     | 0.06%           | -0.14%     |  -0.183 | ETF onset with rising theme-family breadth should reduce false starts.                                                         | Do not wire; display or ignore only      |
| PRUNE      | onset_in_plus_direct_mom      | combo    | long     |      32 | 0.20%      |   0.684 | 53.1%     | 0.17%           | -0.11%     |  -0.208 | ETF onset is more believable when the m-tier sector proxy agrees.                                                              | Do not wire; display or ignore only      |
| PRUNE      | growth_onset_low_vix          | macro    | long     |      41 | 0.15%      |   0.469 | 48.8%     | -0.42%          | 0.04%      |   0.094 | Growth rotations usually prefer easier volatility conditions and abundant risk appetite.                                       | Do not wire; display or ignore only      |
| PRUNE      | episode_confirmed_in          | episode  | long     |     356 | 0.14%      |   1.037 | 51.7%     | 0.08%           | -0.01%     |  -0.097 | Late confirmation may still work if the rotation has persistence; this tests whether paying up is worth it.                    | Do not wire; display or ignore only      |
| PRUNE      | inverse_partner_mom_negative  | inverse  | long     |   32852 | 0.03%      |   0.979 | 50.3%     | 0.02%           | 0.03%      |   0.387 | Rotation is relative; a candidate has more room if its empirical inverse partners are losing momentum.                         | Do not wire; display or ignore only      |
| PRUNE      | fresh_improving_plus_inverse  | combo    | long     |    5563 | 0.02%      |   0.358 | 50.3%     | -0.04%          | 0.03%      |   0.276 | An improving laggard is cleaner when its opposite complex is weakening.                                                        | Do not wire; display or ignore only      |
| PRUNE      | right_rollover                | quadrant | short    |   16889 | 0.01%      |   0.358 | 51.3%     | 0.00%           | 0.06%      |   0.833 | Positive relative strength with falling momentum is the classic weakening quadrant setup.                                      | Do not wire; display or ignore only      |
| PRUNE      | family_sponsor_level          | m_tier   | long     |    6402 | 0.01%      |   0.133 | 48.5%     | -0.09%          | -0.04%     |  -0.23  | High family sponsorship might identify the sector with the broadest underlying theme support.                                  | Do not wire; display or ignore only      |
| PRUNE      | family_hot_breadth_rising     | m_tier   | long     |    5680 | -0.00%     |  -0.005 | 49.6%     | -0.07%          | -0.02%     |  -0.143 | A sector move is healthier when many mapped themes/subsectors are heating together.                                            | Do not wire; display or ignore only      |
| PRUNE      | left_thrust                   | quadrant | long     |   11319 | -0.01%     |  -0.154 | 49.8%     | -0.05%          | 0.06%      |   0.589 | A sector still left of center but with rising momentum can be early enough to matter.                                          | Do not wire; display or ignore only      |
| PRUNE      | mom_cross_up_left             | quadrant | long     |    2209 | -0.03%     |  -0.401 | 50.7%     | -0.12%          | -0.07%     |  -0.629 | Crossing positive momentum while relative strength is still negative should catch turn candidates before consensus leadership. | Do not wire; display or ignore only      |
| PRUNE      | left_thrust_plus_family_chg   | combo    | long     |    1633 | -0.03%     |  -0.294 | 48.7%     | -0.10%          | 0.16%      |   0.745 | Early ETF thrust should be more reliable when mapped subsectors are also broadening.                                           | Do not wire; display or ignore only      |
| PRUNE      | fresh_improving               | quadrant | long     |    9056 | -0.04%     |  -0.665 | 49.5%     | -0.04%          | -0.03%     |  -0.355 | A fresh move into Improving is the first RRG-style evidence that a laggard is being sponsored again.                           | Do not wire; display or ignore only      |
| PRUNE      | fresh_leading                 | quadrant | long     |    9593 | -0.04%     |  -0.825 | 49.4%     | -0.04%          | -0.14%     |  -1.743 | Fresh leadership may still have continuation before it becomes crowded.                                                        | Do not wire; display or ignore only      |
| PRUNE      | episode_confirmed_out         | episode  | short    |     390 | -0.08%     |  -0.461 | 52.6%     | -0.33%          | -0.11%     |  -0.636 | Confirmed exits are cleaner but may arrive after most relative damage has happened.                                            | Do not wire; display or ignore only      |
| PRUNE      | inverse_out_recent            | inverse  | long     |    7986 | -0.09%     |  -1.176 | 48.7%     | -0.14%          | 0.01%      |   0.108 | Actual out episodes in inverse partners should free relative capital for the target sector.                                    | Do not wire; display or ignore only      |
| PRUNE      | mature_leading_fade           | quadrant | short    |     516 | -0.11%     |  -0.531 | 50.4%     | -0.63%          | -0.16%     |  -0.434 | Old leadership gets crowded; the next flow dollar often searches for fresher rotation candidates.                              | Do not wire; display or ignore only      |

## Surviving Patterns

| pattern                      | family   | intent   |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:-----------------------------|:---------|:---------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| onset_in_plus_same_complex   | combo    | long     |     186 | 0.59%      |   3.418 | 59.1%     | 0.57%           | 0.46%      |   2.268 |
| episode_onset_in_peak_ge_1_5 | episode  | long     |     342 | 0.54%      |   3.378 | 59.1%     | 0.43%           | 0.43%      |   2.417 |
| episode_onset_in             | episode  | long     |     356 | 0.53%      |   3.467 | 58.7%     | 0.43%           | 0.44%      |   2.658 |

## Current Sector Snapshot

This is a schedule lens, not a trade ticket. `alert` means a recent in-episode has same-complex support; `watch` means a recent in-episode without that support; `trim_watch` means recent out-pressure or stale-leadership risk.

| sector_etf   | node   | schedule_hint   | quadrant   |   q_age |   rs_ratio |   rs_mom |   schedule_score |   fade_risk_score |   direct_rs_mom |   same_complex_mom |   inverse_partner_mom |   sponsor_score_chg5 |   hot_breadth_chg5 | price_rel21   | episode_onset_in_5d   | episode_onset_out_5d   |
|:-------------|:-------|:----------------|:-----------|--------:|-----------:|---------:|-----------------:|------------------:|----------------:|-------------------:|----------------------:|---------------------:|-------------------:|:--------------|:----------------------|:-----------------------|
| XLV          | XLV    | watch           | leading    |       8 |       0.77 |     1.74 |            2.975 |            -0.365 |            0.66 |             -0.133 |                -0.51  |                0.292 |              0.056 | 7.00%         | True                  | False                  |
| XLK          | XLK    | trim_watch      | weakening  |      19 |       0.65 |    -2.78 |           -0.961 |             0.6   |           -0.47 |              0.915 |                -0.593 |                0.034 |              0.181 | -6.46%        | False                 | True                   |
| XLP          | XLP    | neutral         | lagging    |       2 |      -0.12 |    -0.21 |            1.09  |            -0.049 |            0.29 |              0.517 |                -1.04  |               -0.12  |             -0.053 | 0.86%         | False                 | False                  |
| XLY          | XLY    | neutral         | improving  |       3 |      -0.07 |     0.81 |            0.791 |            -0.057 |            0.3  |             -0.88  |                -0.505 |                0.009 |              0.043 | -1.28%        | False                 | False                  |
| XLF          | XLF    | neutral         | leading    |      18 |       0.71 |     1.13 |            0.745 |            -0.228 |            0.5  |             -0.51  |                -0.133 |                0.542 |             -0.056 | 5.50%         | False                 | False                  |
| XLC          | XLC    | neutral         | improving  |       1 |      -0.93 |     1.02 |            0.648 |            -0.151 |            0.41 |             -0.985 |                -0.1   |                0.376 |              0.05  | -6.22%        | False                 | False                  |
| XLI          | XLI    | neutral         | leading    |       2 |       0.78 |     0.04 |            0.203 |             0.217 |            0.33 |             -0.147 |                 0.57  |                0.27  |              0.163 | 5.23%         | False                 | False                  |
| XLRE         | XLRE   | neutral         | weakening  |       2 |       0.21 |    -0.37 |            0.168 |             0.096 |            0.12 |              0.57  |                -0.007 |               -0.184 |             -0.125 | 1.61%         | False                 | False                  |
| XLE          | XLE    | neutral         | lagging    |      14 |      -1.67 |    -1.19 |           -0.036 |             0.13  |            0.08 |              0.263 |                -0.78  |               -0.478 |             -0.385 | -8.56%        | False                 | False                  |
| XLB          | XLB    | neutral         | lagging    |       4 |      -0.27 |    -0.38 |           -0.858 |             0.43  |            0.08 |             -0.007 |                 0.98  |               -0.14  |             -0.036 | -0.82%        | False                 | False                  |
| XLU          | XLU    | neutral         | improving  |       2 |      -0.05 |     0.18 |           -1.616 |            -0.023 |            0.26 |              0.387 |                 0.66  |               -1.065 |             -1     | 3.15%         | False                 | False                  |

## Watch-Only Patterns

| pattern                      | family   | intent   |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:-----------------------------|:---------|:---------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| cyclical_onset_hy_tightening | macro    | long     |      72 | 1.03%      |   2.435 | 68.1%     | 0.51%           | 0.88%      |   1.907 |
| episode_onset_out            | episode  | short    |     390 | 0.24%      |   1.948 | 56.2%     | 0.21%           | 0.04%      |   0.215 |
| direct_us_sector_mom_pos     | m_tier   | long     |    5185 | 0.09%      |   1.044 | 49.9%     | 0.07%           | 0.18%      |   1.005 |
| mom_cross_down_right         | quadrant | short    |    2103 | 0.04%      |   0.673 | 51.5%     | -0.01%          | 0.15%      |   1.559 |

## Pruned Patterns

| pattern                       | family   | intent   |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:------------------------------|:---------|:---------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| energy_onset_oil_up           | macro    | long     |      27 | 1.70%      |   3.919 | 63.0%     | 1.68%           | 1.44%      |   4.718 |
| old_leading_fade              | quadrant | short    |       6 | 0.90%      |         | 100.0%    | 0.86%           | 1.20%      |         |
| utilities_re_onset_rates_down | macro    | long     |      35 | 0.86%      |   5.897 | 74.3%     | 0.56%           | 0.61%      |   3.937 |
| financials_onset_rates_up     | macro    | long     |      22 | 0.66%      |   3.772 | 72.7%     | 0.66%           | 0.27%      |         |
| onset_in_plus_inverse_out     | combo    | long     |      30 | 0.58%      |   1.812 | 70.0%     | 0.10%           | -0.08%     |  -0.521 |
| episode_onset_in_fast_confirm | episode  | long     |      45 | 0.48%      |   1.197 | 55.6%     | 0.24%           | 0.91%      |   1.539 |
| defensive_onset_vix_pressure  | macro    | long     |      61 | 0.38%      |   0.953 | 59.0%     | -0.56%          | 0.16%      |   0.478 |
| onset_in_plus_family_chg      | combo    | long     |      68 | 0.26%      |   0.843 | 51.5%     | 0.06%           | -0.14%     |  -0.183 |
| onset_in_plus_direct_mom      | combo    | long     |      32 | 0.20%      |   0.684 | 53.1%     | 0.17%           | -0.11%     |  -0.208 |
| growth_onset_low_vix          | macro    | long     |      41 | 0.15%      |   0.469 | 48.8%     | -0.42%          | 0.04%      |   0.094 |
| episode_confirmed_in          | episode  | long     |     356 | 0.14%      |   1.037 | 51.7%     | 0.08%           | -0.01%     |  -0.097 |
| inverse_partner_mom_negative  | inverse  | long     |   32852 | 0.03%      |   0.979 | 50.3%     | 0.02%           | 0.03%      |   0.387 |
| fresh_improving_plus_inverse  | combo    | long     |    5563 | 0.02%      |   0.358 | 50.3%     | -0.04%          | 0.03%      |   0.276 |
| right_rollover                | quadrant | short    |   16889 | 0.01%      |   0.358 | 51.3%     | 0.00%           | 0.06%      |   0.833 |
| family_sponsor_level          | m_tier   | long     |    6402 | 0.01%      |   0.133 | 48.5%     | -0.09%          | -0.04%     |  -0.23  |
| family_hot_breadth_rising     | m_tier   | long     |    5680 | -0.00%     |  -0.005 | 49.6%     | -0.07%          | -0.02%     |  -0.143 |
| left_thrust                   | quadrant | long     |   11319 | -0.01%     |  -0.154 | 49.8%     | -0.05%          | 0.06%      |   0.589 |
| mom_cross_up_left             | quadrant | long     |    2209 | -0.03%     |  -0.401 | 50.7%     | -0.12%          | -0.07%     |  -0.629 |
| left_thrust_plus_family_chg   | combo    | long     |    1633 | -0.03%     |  -0.294 | 48.7%     | -0.10%          | 0.16%      |   0.745 |
| fresh_improving               | quadrant | long     |    9056 | -0.04%     |  -0.665 | 49.5%     | -0.04%          | -0.03%     |  -0.355 |
| fresh_leading                 | quadrant | long     |    9593 | -0.04%     |  -0.825 | 49.4%     | -0.04%          | -0.14%     |  -1.743 |
| episode_confirmed_out         | episode  | short    |     390 | -0.08%     |  -0.461 | 52.6%     | -0.33%          | -0.11%     |  -0.636 |
| inverse_out_recent            | inverse  | long     |    7986 | -0.09%     |  -1.176 | 48.7%     | -0.14%          | 0.01%      |   0.108 |
| mature_leading_fade           | quadrant | short    |     516 | -0.11%     |  -0.531 | 50.4%     | -0.63%          | -0.16%     |  -0.434 |

## Continuous Feature Audit

Rank IC audit. Positive rows mean higher feature values ranked into better future sector-relative returns. Most continuous coordinates fail here, which is why they should not originate a trade alone.

|   horizon | signal               |   n_days |   mean_ic |   median_ic |   t_hac | hit_rate   |
|----------:|:---------------------|---------:|----------:|------------:|--------:|:-----------|
|         5 | direct_rs_mom        |      761 |     0.024 |       0.055 |   0.999 | 55.1%      |
|         5 | direct_pos           |      761 |     0.009 |      -0.005 |   0.427 | 48.8%      |
|         5 | same_complex_mom     |     6895 |     0.009 |       0.017 |   1.041 | 51.2%      |
|         5 | schedule_score       |     6895 |     0.007 |       0.009 |   0.778 | 50.2%      |
|         5 | hot_breadth_chg5     |     1220 |     0.006 |       0.018 |   0.42  | 52.0%      |
|         5 | early_rotation_score |     6895 |     0.002 |       0     |   0.2   | 49.1%      |
|         5 | sponsor_score_chg5   |     1220 |    -0.001 |       0.009 |  -0.095 | 50.6%      |
|         5 | inverse_partner_mom  |     6895 |    -0.004 |       0     |  -0.498 | 49.5%      |
|         5 | price_rel63          |     6854 |    -0.006 |      -0.017 |  -0.653 | 48.5%      |
|         5 | rs_mom_chg5          |     6890 |    -0.006 |       0     |  -0.865 | 48.9%      |
|         5 | rs_ratio             |     6895 |    -0.007 |       0     |  -0.783 | 49.6%      |
|         5 | price_rel21          |     6895 |    -0.009 |      -0.009 |  -0.961 | 48.8%      |
|         5 | rs_mom               |     6895 |    -0.009 |      -0.017 |  -1.056 | 48.5%      |
|         5 | pos_chg5             |     6890 |    -0.009 |      -0.017 |  -1.321 | 48.1%      |
|         5 | pos                  |     6895 |    -0.016 |      -0.017 |  -1.818 | 48.1%      |
|         5 | fade_risk_score      |     3954 |    -0.018 |       0     |  -2.168 | 44.8%      |
|         5 | sponsor_score        |     1225 |    -0.019 |      -0.027 |  -1.028 | 47.3%      |
|        10 | direct_rs_mom        |      756 |     0.038 |       0.016 |   1.3   | 51.7%      |
|        10 | direct_pos           |      756 |     0.025 |       0.009 |   0.866 | 50.1%      |
|        10 | same_complex_mom     |     6890 |     0.023 |       0.033 |   2.152 | 52.6%      |
|        10 | schedule_score       |     6890 |     0.022 |       0.033 |   2.067 | 51.9%      |
|        10 | sponsor_score_chg5   |     1215 |     0.017 |       0.027 |   1.07  | 51.9%      |
|        10 | early_rotation_score |     6890 |     0.009 |       0.009 |   0.885 | 50.2%      |
|        10 | hot_breadth_chg5     |     1215 |     0.008 |       0.027 |   0.555 | 52.5%      |
|        10 | rs_mom               |     6890 |    -0.002 |       0     |  -0.138 | 49.4%      |
|        10 | rs_mom_chg5          |     6885 |    -0.004 |       0     |  -0.5   | 48.9%      |
|        10 | pos_chg5             |     6885 |    -0.008 |      -0.008 |  -1.161 | 48.6%      |
|        10 | price_rel21          |     6890 |    -0.009 |      -0.009 |  -0.713 | 48.8%      |
|        10 | rs_ratio             |     6890 |    -0.011 |      -0.003 |  -0.906 | 49.0%      |
|        10 | pos                  |     6890 |    -0.011 |      -0.017 |  -0.994 | 47.9%      |
|        10 | inverse_partner_mom  |     6890 |    -0.013 |      -0.017 |  -1.267 | 48.1%      |
|        10 | price_rel63          |     6849 |    -0.015 |      -0.017 |  -1.192 | 48.5%      |
|        10 | sponsor_score        |     1220 |    -0.017 |      -0.018 |  -0.734 | 48.3%      |
|        10 | fade_risk_score      |     3949 |    -0.023 |       0     |  -2.231 | 45.3%      |
|        21 | direct_rs_mom        |      745 |     0.076 |       0.091 |   2.09  | 58.0%      |
|        21 | direct_pos           |      745 |     0.053 |       0.027 |   1.574 | 52.5%      |
|        21 | same_complex_mom     |     6879 |     0.021 |       0.027 |   1.412 | 51.5%      |
|        21 | schedule_score       |     6879 |     0.011 |       0.017 |   0.783 | 50.4%      |
|        21 | sponsor_score_chg5   |     1204 |     0.01  |       0.009 |   0.607 | 50.7%      |
|        21 | rs_mom               |     6879 |     0.001 |       0.009 |   0.046 | 50.2%      |

Top-minus-bottom audit. Long top 3 sectors by feature, short bottom 3.

|   horizon | signal               |   n_days | long_minus_short   | median   |   t_hac | hit_rate   |
|----------:|:---------------------|---------:|:-------------------|:---------|--------:|:-----------|
|         5 | direct_rs_mom        |      761 | 0.13%              | 0.13%    |   1.029 | 53.9%      |
|         5 | same_complex_mom     |     6895 | 0.05%              | 0.05%    |   1.256 | 51.4%      |
|         5 | direct_pos           |      761 | 0.05%              | 0.01%    |   0.413 | 50.2%      |
|         5 | early_rotation_score |     6895 | 0.03%              | -0.02%   |   0.877 | 49.4%      |
|         5 | schedule_score       |     6895 | 0.03%              | 0.00%    |   0.673 | 50.1%      |
|         5 | hot_breadth_chg5     |     1220 | -0.00%             | 0.03%    |  -0.027 | 50.6%      |
|         5 | rs_mom               |     6895 | -0.00%             | -0.02%   |  -0.055 | 49.6%      |
|         5 | sponsor_score_chg5   |     1220 | -0.03%             | 0.04%    |  -0.438 | 51.3%      |
|         5 | inverse_partner_mom  |     6895 | -0.04%             | 0.01%    |  -1.063 | 50.4%      |
|         5 | price_rel21          |     6895 | -0.05%             | -0.03%   |  -1.093 | 49.2%      |
|         5 | fade_risk_score      |     6895 | -0.05%             | -0.04%   |  -1.3   | 48.7%      |
|         5 | rs_mom_chg5          |     6890 | -0.06%             | -0.03%   |  -1.715 | 49.4%      |
|         5 | sponsor_score        |     1225 | -0.06%             | -0.10%   |  -0.671 | 47.8%      |
|         5 | rs_ratio             |     6895 | -0.07%             | -0.03%   |  -1.529 | 49.2%      |
|         5 | pos                  |     6895 | -0.08%             | -0.09%   |  -1.825 | 47.9%      |
|         5 | pos_chg5             |     6890 | -0.08%             | -0.06%   |  -2.268 | 48.4%      |
|         5 | price_rel63          |     6854 | -0.09%             | -0.03%   |  -1.895 | 49.2%      |
|        10 | direct_rs_mom        |      756 | 0.35%              | 0.18%    |   1.713 | 53.6%      |
|        10 | direct_pos           |      756 | 0.27%              | 0.22%    |   1.34  | 54.5%      |
|        10 | sponsor_score_chg5   |     1215 | 0.12%              | 0.14%    |   1.02  | 51.6%      |
|        10 | same_complex_mom     |     6890 | 0.10%              | 0.16%    |   1.367 | 53.1%      |
|        10 | schedule_score       |     6890 | 0.10%              | 0.11%    |   1.366 | 52.4%      |
|        10 | early_rotation_score |     6890 | 0.07%              | 0.01%    |   0.987 | 50.2%      |
|        10 | rs_mom               |     6890 | 0.01%              | 0.03%    |   0.12  | 50.5%      |
|        10 | hot_breadth_chg5     |     1215 | -0.01%             | 0.05%    |  -0.146 | 50.5%      |
|        10 | sponsor_score        |     1220 | -0.02%             | -0.04%   |  -0.117 | 49.4%      |
|        10 | price_rel21          |     6890 | -0.05%             | 0.00%    |  -0.675 | 50.0%      |
|        10 | rs_mom_chg5          |     6885 | -0.06%             | -0.01%   |  -1.281 | 49.9%      |
|        10 | fade_risk_score      |     6890 | -0.08%             | -0.03%   |  -1.114 | 49.5%      |
|        10 | pos                  |     6890 | -0.08%             | -0.06%   |  -1.171 | 48.8%      |
|        10 | rs_ratio             |     6890 | -0.09%             | 0.01%    |  -1.175 | 50.1%      |
|        10 | pos_chg5             |     6885 | -0.10%             | -0.02%   |  -1.978 | 49.6%      |
|        10 | inverse_partner_mom  |     6890 | -0.10%             | -0.06%   |  -1.495 | 48.7%      |
|        10 | price_rel63          |     6849 | -0.12%             | -0.06%   |  -1.429 | 48.9%      |
|        21 | direct_rs_mom        |      745 | 0.87%              | 0.76%    |   2.464 | 59.1%      |
|        21 | direct_pos           |      745 | 0.64%              | 0.63%    |   1.959 | 57.7%      |
|        21 | sponsor_score_chg5   |     1204 | 0.15%              | -0.01%   |   0.821 | 49.9%      |
|        21 | same_complex_mom     |     6879 | 0.14%              | 0.22%    |   1.036 | 52.9%      |
|        21 | schedule_score       |     6879 | 0.11%              | 0.13%    |   0.801 | 51.6%      |
|        21 | early_rotation_score |     6879 | 0.09%              | 0.03%    |   0.616 | 50.3%      |

## Mined Pattern Scan

Exploratory boolean combinations were mined only after anchoring on an interpretable rotation event/state. These are not wiring instructions; they are idea generators that still need pre-registration before promotion.

Second-stage mined filter: n >= 80, 10d mean > 0.25%, HAC t >= 2.0, hit >= 54%, split-half minimum > 0, and positive 21d mean. Rows outside this stricter filter are kept in the raw mined CSVs but should be treated as small-sample or multiple-testing curiosities.

Robust mined long candidates:

| pattern                                                |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:-------------------------------------------------------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| onset_in_5d + price_rel21_pos + hy_tightening_21d      |     589 | 0.67%      |   3.586 | 59.3%     | 0.25%           | 0.80%      |   2.8   |
| onset_in_5d + same_complex_mom_pos + dollar_down_21d   |     459 | 0.71%      |   3.558 | 60.1%     | 0.50%           | 0.87%      |   3.807 |
| onset_in_5d + inverse_mom_neg + dollar_down_21d        |     496 | 0.75%      |   3.139 | 61.7%     | 0.33%           | 0.83%      |   2.346 |
| onset_in_5d + same_complex_mom_pos + hy_tightening_21d |     512 | 0.56%      |   3.006 | 58.0%     | 0.23%           | 0.35%      |   1.224 |
| onset_in_5d + rates_down_21d + hy_tightening_21d       |     335 | 0.57%      |   2.935 | 60.6%     | 0.57%           | 0.62%      |   1.782 |
| onset_in_5d + oil_up_21d + dollar_down_21d             |     495 | 0.66%      |   2.925 | 59.8%     | 0.63%           | 0.74%      |   2.44  |
| onset_in_5d + inverse_mom_neg + hy_tightening_21d      |     594 | 0.57%      |   2.903 | 58.6%     | 0.06%           | 0.23%      |   0.661 |
| direct_mom_pos + inverse_mom_neg + dollar_down_21d     |    1300 | 0.44%      |   2.805 | 54.1%     | 0.29%           | 0.87%      |   2.786 |
| onset_in_5d + inverse_mom_neg + price_rel21_pos        |     842 | 0.48%      |   2.751 | 55.5%     | 0.18%           | 0.42%      |   1.532 |
| onset_in_5d + dollar_down_21d + hy_tightening_21d      |     459 | 0.61%      |   2.742 | 58.8%     | 0.35%           | 0.74%      |   2.023 |
| onset_in_5d + dollar_down_21d                          |     758 | 0.52%      |   2.693 | 58.3%     | 0.45%           | 0.54%      |   1.991 |
| onset_in_5d + price_rel21_pos                          |    1193 | 0.37%      |   2.514 | 55.3%     | 0.24%           | 0.36%      |   1.624 |
| onset_in_5d + hy_tightening_21d                        |     888 | 0.40%      |   2.491 | 56.5%     | 0.20%           | 0.29%      |   1.091 |
| onset_in_5d + rates_up_21d + dollar_down_21d           |     317 | 0.73%      |   2.437 | 59.9%     | 0.58%           | 0.54%      |   1.196 |
| onset_in_5d + price_rel21_pos + rates_up_21d           |     554 | 0.49%      |   2.339 | 57.4%     | 0.30%           | 0.43%      |   1.459 |
| onset_in_5d + family_hot + price_rel21_pos             |     193 | 1.00%      |   2.272 | 61.1%     | 0.76%           | 0.50%      |   0.735 |
| onset_in_5d                                            |    1780 | 0.29%      |   2.27  | 54.0%     | 0.24%           | 0.14%      |   0.75  |
| onset_in_5d + price_rel21_pos + oil_up_21d             |     592 | 0.47%      |   2.247 | 55.7%     | 0.41%           | 0.55%      |   1.874 |
| onset_in_5d + same_complex_mom_pos                     |     956 | 0.35%      |   2.207 | 54.3%     | 0.25%           | 0.15%      |   0.673 |
| onset_in_5d + hot_breadth_rising + hy_tightening_21d   |     149 | 0.71%      |   2.19  | 59.7%     | 0.43%           | 1.00%      |   2.041 |
| onset_in_5d + inverse_mom_neg + vix_high_or_rising     |     692 | 0.43%      |   2.174 | 54.9%     | 0.28%           | 0.37%      |   1.203 |
| onset_in_5d + price_rel21_pos + dollar_down_21d        |     487 | 0.55%      |   2.168 | 56.7%     | 0.04%           | 0.63%      |   1.892 |
| onset_in_5d + price_rel21_pos + vix_high_or_rising     |     655 | 0.45%      |   2.156 | 55.6%     | 0.22%           | 0.65%      |   2.017 |
| onset_in_5d + vix_high_or_rising + dollar_down_21d     |     433 | 0.58%      |   2.129 | 57.7%     | 0.55%           | 0.53%      |   1.53  |
| onset_in_5d + same_complex_mom_pos + rates_down_21d    |     518 | 0.36%      |   2.011 | 54.2%     | 0.31%           | 0.25%      |   0.948 |
| onset_in_5d + hot_breadth_rising + family_hot          |     181 | 0.65%      |   2.009 | 56.9%     | 0.36%           | 0.46%      |   1.058 |

Robust mined short/avoid candidates:

| pattern                                                     |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:------------------------------------------------------------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| onset_out_5d + family_hot + inverse_out_recent              |      90 | 1.21%      |   2.652 | 64.4%     | 0.27%           | 1.22%      |   2.112 |
| onset_out_5d + same_complex_mom_pos + rates_up_21d          |     412 | 0.49%      |   2.197 | 56.3%     | 0.40%           | 0.83%      |   2.412 |
| onset_out_5d + rates_up_21d + dollar_down_21d               |     213 | 0.58%      |   2.166 | 61.5%     | 0.16%           | 0.77%      |   1.977 |
| mom_cross_down_right + vix_high_or_rising + dollar_down_21d |     503 | 0.28%      |   2.148 | 55.7%     | 0.27%           | 0.46%      |   2.189 |
| onset_out_5d + same_complex_mom_pos + dollar_down_21d       |     219 | 0.56%      |   2.141 | 62.1%     | 0.42%           | 0.65%      |   1.664 |
| onset_out_5d + inverse_out_recent + price_rel21_neg         |     521 | 0.54%      |   2.109 | 57.0%     | 0.27%           | 0.48%      |   1.567 |

Top mined long combinations:

| pattern                                                   |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:----------------------------------------------------------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| onset_in_5d + price_rel21_pos + hy_tightening_21d         |     589 | 0.67%      |   3.586 | 59.3%     | 0.25%           | 0.80%      |   2.8   |
| onset_in_5d + same_complex_mom_pos + dollar_down_21d      |     459 | 0.71%      |   3.558 | 60.1%     | 0.50%           | 0.87%      |   3.807 |
| mom_cross_up_left + direct_mom_pos + price_rel21_pos      |      21 | 0.50%      |   3.335 | 61.9%     | -0.23%          | 0.14%      |         |
| onset_in_5d + inverse_mom_neg + dollar_down_21d           |     496 | 0.75%      |   3.139 | 61.7%     | 0.33%           | 0.83%      |   2.346 |
| onset_in_5d + same_complex_mom_pos + hy_tightening_21d    |     512 | 0.56%      |   3.006 | 58.0%     | 0.23%           | 0.35%      |   1.224 |
| onset_in_5d + rates_down_21d + hy_tightening_21d          |     335 | 0.57%      |   2.935 | 60.6%     | 0.57%           | 0.62%      |   1.782 |
| onset_in_5d + oil_up_21d + dollar_down_21d                |     495 | 0.66%      |   2.925 | 59.8%     | 0.63%           | 0.74%      |   2.44  |
| onset_in_5d + inverse_mom_neg + hy_tightening_21d         |     594 | 0.57%      |   2.903 | 58.6%     | 0.06%           | 0.23%      |   0.661 |
| direct_mom_pos + inverse_mom_neg + dollar_down_21d        |    1300 | 0.44%      |   2.805 | 54.1%     | 0.29%           | 0.87%      |   2.786 |
| onset_in_5d + inverse_mom_neg + price_rel21_pos           |     842 | 0.48%      |   2.751 | 55.5%     | 0.18%           | 0.42%      |   1.532 |
| onset_in_5d + dollar_down_21d + hy_tightening_21d         |     459 | 0.61%      |   2.742 | 58.8%     | 0.35%           | 0.74%      |   2.023 |
| onset_in_5d + family_hot + inverse_out_recent             |      35 | 2.02%      |   2.73  | 77.1%     | 1.36%           | 2.09%      |   6.746 |
| onset_in_5d + dollar_down_21d                             |     758 | 0.52%      |   2.693 | 58.3%     | 0.45%           | 0.54%      |   1.991 |
| left_thrust + inverse_mom_neg + dollar_down_21d           |    2956 | 0.28%      |   2.685 | 52.8%     | 0.11%           | 0.35%      |   1.641 |
| direct_mom_pos + same_complex_mom_pos + dollar_down_21d   |    1486 | 0.39%      |   2.647 | 53.0%     | 0.25%           | 0.70%      |   2.457 |
| onset_in_5d + price_rel21_pos                             |    1193 | 0.37%      |   2.514 | 55.3%     | 0.24%           | 0.36%      |   1.624 |
| onset_in_5d + hy_tightening_21d                           |     888 | 0.40%      |   2.491 | 56.5%     | 0.20%           | 0.29%      |   1.091 |
| onset_in_5d + rates_up_21d + dollar_down_21d              |     317 | 0.73%      |   2.437 | 59.9%     | 0.58%           | 0.54%      |   1.196 |
| onset_in_5d + hot_breadth_rising + inverse_out_recent     |      25 | 1.45%      |   2.379 | 80.0%     | 0.37%           | 1.46%      |   3.169 |
| onset_in_5d + price_rel21_pos + rates_up_21d              |     554 | 0.49%      |   2.339 | 57.4%     | 0.30%           | 0.43%      |   1.459 |
| fresh_improving + same_complex_mom_pos + price_rel21_pos  |    1277 | 0.25%      |   2.288 | 50.5%     | 0.16%           | 0.20%      |   1.06  |
| direct_mom_pos + same_complex_mom_pos + hy_tightening_21d |    1637 | 0.30%      |   2.281 | 50.7%     | 0.16%           | 0.62%      |   2.241 |
| onset_in_5d + family_hot + price_rel21_pos                |     193 | 1.00%      |   2.272 | 61.1%     | 0.76%           | 0.50%      |   0.735 |
| onset_in_5d                                               |    1780 | 0.29%      |   2.27  | 54.0%     | 0.24%           | 0.14%      |   0.75  |
| onset_in_5d + price_rel21_pos + oil_up_21d                |     592 | 0.47%      |   2.247 | 55.7%     | 0.41%           | 0.55%      |   1.874 |
| direct_mom_pos + inverse_mom_neg + hy_tightening_21d      |    1452 | 0.35%      |   2.237 | 53.7%     | 0.28%           | 0.84%      |   2.567 |
| onset_in_5d + same_complex_mom_pos                        |     956 | 0.35%      |   2.207 | 54.3%     | 0.25%           | 0.15%      |   0.673 |
| onset_in_5d + hot_breadth_rising + hy_tightening_21d      |     149 | 0.71%      |   2.19  | 59.7%     | 0.43%           | 1.00%      |   2.041 |
| onset_in_5d + inverse_mom_neg + vix_high_or_rising        |     692 | 0.43%      |   2.174 | 54.9%     | 0.28%           | 0.37%      |   1.203 |
| mom_cross_up_left + price_rel21_pos + vix_high_or_rising  |     127 | 0.55%      |   2.172 | 53.5%     | 0.27%           | 0.43%      |   1.869 |

Top mined short/avoid combinations:

| pattern                                                        |   n_10d | mean_10d   |   t_10d | hit_10d   | split_min_10d   | mean_21d   |   t_21d |
|:---------------------------------------------------------------|--------:|:-----------|--------:|:----------|:----------------|:-----------|--------:|
| mature_leading + hot_breadth_rising + rates_down_21d           |      23 | 0.35%      |   4.252 | 69.6%     | 0.31%           | 0.37%      |   1.852 |
| mom_cross_down_right + hot_breadth_rising + dollar_down_21d    |      54 | 0.86%      |   3.85  | 55.6%     | 0.72%           | 1.70%      |   7.983 |
| mom_cross_down_right + sponsor_chg_pos + oil_up_21d            |      59 | 0.82%      |   3.624 | 61.0%     | 0.82%           | 1.83%      |   7.109 |
| mom_cross_down_right + sponsor_chg_pos + rates_down_21d        |      48 | 0.46%      |   3.043 | 58.3%     | 0.19%           | 0.98%      |   2.856 |
| mom_cross_down_right + sponsor_chg_pos + dollar_down_21d       |      59 | 0.79%      |   2.7   | 52.5%     | 0.61%           | 1.95%      |   9.926 |
| onset_out_5d + family_hot + inverse_out_recent                 |      90 | 1.21%      |   2.652 | 64.4%     | 0.27%           | 1.22%      |   2.112 |
| onset_out_5d + direct_mom_pos + price_rel21_pos                |      54 | 0.92%      |   2.381 | 74.1%     | 0.47%           | 1.29%      |   2.731 |
| mom_cross_down_right + hot_breadth_rising + oil_up_21d         |      62 | 0.62%      |   2.359 | 58.1%     | 0.32%           | 1.44%      |   4.944 |
| mature_leading + inverse_out_recent + rates_down_21d           |      33 | 1.26%      |   2.32  | 69.7%     | 0.44%           | 0.54%      |   1.389 |
| mom_cross_down_right + direct_mom_pos + inverse_out_recent     |      33 | 0.69%      |   2.25  | 57.6%     | 0.46%           | 1.13%      |   2.602 |
| onset_out_5d + same_complex_mom_pos + rates_up_21d             |     412 | 0.49%      |   2.197 | 56.3%     | 0.40%           | 0.83%      |   2.412 |
| onset_out_5d + family_hot + price_rel21_pos                    |      76 | 0.70%      |   2.168 | 64.5%     | 0.49%           | 0.90%      |   1.928 |
| onset_out_5d + rates_up_21d + dollar_down_21d                  |     213 | 0.58%      |   2.166 | 61.5%     | 0.16%           | 0.77%      |   1.977 |
| mature_leading + inverse_out_recent + same_complex_mom_pos     |      23 | 1.33%      |   2.151 | 73.9%     | 0.92%           | 0.55%      |         |
| mom_cross_down_right + vix_high_or_rising + dollar_down_21d    |     503 | 0.28%      |   2.148 | 55.7%     | 0.27%           | 0.46%      |   2.189 |
| onset_out_5d + same_complex_mom_pos + dollar_down_21d          |     219 | 0.56%      |   2.141 | 62.1%     | 0.42%           | 0.65%      |   1.664 |
| onset_out_5d + inverse_out_recent + price_rel21_neg            |     521 | 0.54%      |   2.109 | 57.0%     | 0.27%           | 0.48%      |   1.567 |
| mom_cross_down_right + sponsor_chg_pos + price_rel21_pos       |     106 | 0.51%      |   2.076 | 51.9%     | 0.47%           | 1.35%      |   3.657 |
| mom_cross_down_right + family_hot + dollar_down_21d            |      71 | 0.40%      |   2.044 | 53.5%     | 0.38%           | 1.54%      |   5.201 |
| mom_cross_down_right + sponsor_chg_pos + vix_high_or_rising    |      74 | 0.68%      |   2.039 | 56.8%     | 0.27%           | 1.75%      |   5.269 |
| mom_cross_down_right + hot_breadth_rising + vix_high_or_rising |      71 | 0.51%      |   2.031 | 54.9%     | 0.42%           | 1.16%      |   3.591 |
| mom_cross_down_right + rates_up_21d + dollar_down_21d          |     381 | 0.25%      |   2.005 | 52.8%     | 0.14%           | 0.41%      |   1.81  |
| onset_out_5d + dollar_down_21d                                 |     507 | 0.40%      |   1.998 | 59.2%     | 0.22%           | 0.57%      |   2.289 |
| mom_cross_down_right + sponsor_chg_pos + hot_breadth_rising    |      94 | 0.44%      |   1.984 | 52.1%     | 0.35%           | 1.00%      |   3.757 |
| mom_cross_down_right + sponsor_chg_pos                         |     118 | 0.48%      |   1.975 | 53.4%     | 0.39%           | 1.23%      |   3.8   |
| mom_cross_down_right + hot_breadth_rising + price_rel21_pos    |     104 | 0.35%      |   1.959 | 51.0%     | 0.27%           | 0.87%      |   3.189 |
| onset_out_5d + price_rel21_neg + dollar_down_21d               |     381 | 0.45%      |   1.929 | 60.4%     | 0.20%           | 0.63%      |   2.666 |
| onset_out_5d + dollar_down_21d + hy_tightening_21d             |     152 | 0.73%      |   1.924 | 63.2%     | 0.42%           | 1.09%      |   2.553 |
| onset_out_5d + direct_mom_pos + dollar_down_21d                |      53 | 0.90%      |   1.916 | 66.0%     | 0.53%           | 1.06%      |   1.825 |
| onset_out_5d + vix_high_or_rising + dollar_down_21d            |     442 | 0.41%      |   1.853 | 60.0%     | 0.22%           | 0.60%      |   2.2   |

## First-Principles Synthesis

- **Why onsets work:** They mark a change in relative sponsorship before the sector becomes obviously dominant. The market pays for the transition, not the settled label.
- **Why confirmed entries decay:** Confirmation waits for enough persistence to prove the episode. By then, part of the repricing is already visible and crowded.
- **Why mature leadership fades:** Sector allocation is a relative budget. When one sector has absorbed flows long enough, the next marginal dollar often hunts for a fresher laggard with improving momentum.
- **Why inverse pressure matters but cannot stand alone:** Rotation needs a funding source and a destination. Inverse out-pressure identifies funding, but without target-sector sponsorship it can just mean broad risk-off.
- **Why m-tier confirmation is context-only:** Theme/subsector families help explain where sponsorship is broad, but current m-tier history is shorter and survivorship-caveated, so it cannot yet originate or hard-gate sector ETF trades.
- **Why macro filters are fragile:** Rates, oil, VIX, credit, and dollar states explain sector narratives, but the same macro move can mean reflation, recession, policy easing, or stress depending on context. Macro belongs as a conditioner on a rotation pattern, not as a blind sector switch.

## Proposed Shadow Signal

Create a display/shadow artifact keyed by sector ETF:

`sector_rotation_schedule.v1 = onset_state + quadrant_age + direct_m_tier_mom + family_breadth_change + inverse_pressure + macro_conditioner + stale_leadership_penalty`

Suggested fields:

- `episode_onset_in_5d`, `episode_onset_out_5d`
- `quadrant`, `q_age`, `fresh_improving`, `mature_leading`, `right_rollover`
- `direct_rs_mom`, `family_hot_breadth`, `family_sponsor_score_chg5`
- `inverse_partner_mom`, `inverse_out_10d`, `same_complex_mom`
- `vix_high_or_rising`, `rates_up_21d`, `rates_down_21d`, `oil_up_21d`, `hy_tightening_21d`
- `schedule_score`, `fade_risk_score`, `decision_hint = alert/watch/prune`

Do not let this signal size positions or originate final entries until it has its own forward ledger. It should support sector timing, alerting, and de-escalation first.

## Artifact Index

- Report: `reports/rotation-time-machine-extended-patterns.md`
- CSV outputs: `reports/artifacts/rotation_time_machine_extended/`
- Key CSVs: `current_sector_snapshot.csv`, `pattern_decisions.csv`, `pattern_cards.csv`, `rule_eval_all.csv`, `continuous_rank_ic.csv`, `continuous_top_bottom.csv`, `mined_long_patterns.csv`, `mined_short_patterns.csv`, `mined_long_robust.csv`, `mined_short_robust.csv`.

## Limits

- M-tier features begin in 2021 and carry the Time Machine survivorship caveat.
- Boolean mined combinations are exploratory and multiple-testing exposed; use them to design pre-registered tests, not to wire live signals.
- The empirical inverse-partner map uses full-sample correlations and should be replaced by a rolling or pre-fixed map before production use.
- All tests are gross ETF-relative returns; no cost, slippage, or capacity model is included.
