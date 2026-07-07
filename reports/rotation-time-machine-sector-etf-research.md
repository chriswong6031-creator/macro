# Rotation Time Machine Sector ETF Research

Generated from `site/oracledata/tm_manifest.json` built at `2026-07-05T10:58:17.943386Z`.
Live `site/marketdata/subsector_rotation.json` as-of `2026-07-05`; ETF parquets latest close `2026-07-02`.

## Executive Findings

1. The continuous sector-coordinate ranks are not a standalone alpha. Across the full ETF history, raw `rs_ratio`, `rs_mom`, and composite position are mostly flat to mildly mean-reverting once tested as next-session tradable forward returns.
2. The useful measured signal is episodic: Time Machine `in` episode onsets show strong positive forward sector-ETF excess returns, while `out` onsets show negative forward excess. By confirmed dates the effect largely decays, so the timing value is early detection, not late confirmation.
3. Quadrants behave like a schedule map: mature `Leading` often fades by 21-63 sessions, while `Improving`/`Lagging` are where the next rotation candidate forms. The practical read is to monitor Lagging -> Improving -> Leading, then demand price/flow confirmation before entry.
4. Sector ETFs cluster into three repeatedly rotating complexes: growth/innovation (XLK/XLC/XLY), cyclical/commodity/rates (XLE/XLB/XLI/XLF), and defensive/rate-sensitive (XLV/XLU/XLP/XLRE). The inverse relationships are strongest across those complex borders, not usually within them.
5. The m-tier `us_sector_*` nodes add modest 21-session confirmation; broad theme/subsector family sponsorship is more useful as context than as a direct rank signal until a point-in-time ledger matures.

## Data Contract

- Sector tier: 11 sector ETF nodes, daily, 1998-12-22 through 2026-07-01 in Time Machine chunks.
- M tier: 38 themes plus 316 subsector/basket-like nodes, daily, 2021-08-02 through 2026-07-02.
- Tradable reference: XLB, XLC, XLE, XLF, XLI, XLK, XLP, XLRE, XLU, XLV, XLY from `data/yahoo`, with SPY for excess-return context.
- Forward tests use next-session-close entry, then ETF forward returns relative to the equal-weight sector ETF cross-section (`fwd_xs`) over 5, 10, 21, and 63 trading days. Entry lag = 1 trading session.

## Sector ETF Signal Tests

Rank IC: Time Machine signal today vs next-session tradable future cross-sectional sector ETF excess return. The continuous coordinates are better treated as state/context than as direct rank alpha.

|   horizon | signal        |   n_days |   mean_ic |   median_ic |   t_hac | hit_rate   |
|----------:|:--------------|---------:|----------:|------------:|--------:|:-----------|
|         5 | rs_mom_chg5   |     6890 |    -0.006 |       0     |  -0.865 | 48.9%      |
|         5 | rs_ratio      |     6895 |    -0.007 |       0     |  -0.783 | 49.6%      |
|         5 | rs_ratio_chg5 |     6890 |    -0.008 |      -0.009 |  -1.118 | 48.6%      |
|         5 | rs_mom        |     6895 |    -0.009 |      -0.017 |  -1.056 | 48.5%      |
|         5 | pos_chg5      |     6890 |    -0.009 |      -0.017 |  -1.321 | 48.1%      |
|         5 | pos           |     6895 |    -0.016 |      -0.017 |  -1.818 | 48.1%      |
|        10 | rs_mom        |     6890 |    -0.002 |       0     |  -0.138 | 49.4%      |
|        10 | rs_mom_chg5   |     6885 |    -0.004 |       0     |  -0.5   | 48.9%      |
|        10 | rs_ratio_chg5 |     6885 |    -0.007 |      -0.017 |  -0.807 | 48.4%      |
|        10 | pos_chg5      |     6885 |    -0.008 |      -0.008 |  -1.161 | 48.6%      |
|        10 | rs_ratio      |     6890 |    -0.011 |      -0.003 |  -0.906 | 49.0%      |
|        10 | pos           |     6890 |    -0.011 |      -0.017 |  -0.994 | 47.9%      |
|        21 | rs_mom        |     6879 |     0.001 |       0.009 |   0.046 | 50.2%      |
|        21 | rs_mom_chg5   |     6874 |    -0.002 |      -0.006 |  -0.226 | 48.6%      |
|        21 | rs_ratio_chg5 |     6874 |    -0.002 |       0     |  -0.19  | 49.1%      |
|        21 | pos_chg5      |     6874 |    -0.003 |       0     |  -0.432 | 48.8%      |

Top-minus-bottom: long top 3 sectors by signal, short bottom 3, using next-session tradable forward cross-sectional excess return.

|   horizon | signal        |   n_days | long_minus_short   | median   |   t_hac | hit_rate   |
|----------:|:--------------|---------:|:-------------------|:---------|--------:|:-----------|
|         5 | rs_mom        |     6895 | -0.00%             | -0.02%   |  -0.055 | 49.6%      |
|         5 | rs_ratio_chg5 |     6890 | -0.06%             | -0.04%   |  -1.712 | 48.9%      |
|         5 | rs_mom_chg5   |     6890 | -0.06%             | -0.03%   |  -1.715 | 49.4%      |
|         5 | rs_ratio      |     6895 | -0.07%             | -0.03%   |  -1.529 | 49.2%      |
|         5 | pos           |     6895 | -0.08%             | -0.09%   |  -1.825 | 47.9%      |
|         5 | pos_chg5      |     6890 | -0.08%             | -0.06%   |  -2.268 | 48.4%      |
|        10 | rs_mom        |     6890 | 0.01%              | 0.03%    |   0.12  | 50.5%      |
|        10 | rs_mom_chg5   |     6885 | -0.06%             | -0.01%   |  -1.281 | 49.9%      |
|        10 | rs_ratio_chg5 |     6885 | -0.06%             | -0.01%   |  -1.155 | 49.8%      |
|        10 | pos           |     6890 | -0.08%             | -0.06%   |  -1.171 | 48.8%      |
|        10 | rs_ratio      |     6890 | -0.09%             | 0.01%    |  -1.175 | 50.1%      |
|        10 | pos_chg5      |     6885 | -0.10%             | -0.02%   |  -1.978 | 49.6%      |
|        21 | rs_mom        |     6879 | 0.00%              | 0.04%    |   0.03  | 50.4%      |
|        21 | rs_ratio_chg5 |     6874 | -0.03%             | 0.04%    |  -0.32  | 50.7%      |
|        21 | pos_chg5      |     6874 | -0.05%             | -0.05%   |  -0.794 | 49.2%      |
|        21 | rs_mom_chg5   |     6874 | -0.06%             | -0.03%   |  -0.916 | 49.4%      |

Quadrant behavior: mean sector-ETF forward excess return by Time Machine quadrant.

|   horizon | quadrant   |     n | mean_fwd_xs   | median   |   t_hac | hit_rate   |
|----------:|:-----------|------:|:--------------|:---------|--------:|:-----------|
|         5 | lagging    | 15592 | 0.04%         | 0.02%    |   1.57  | 50.4%      |
|         5 | improving  | 18082 | 0.01%         | -0.02%   |   0.588 | 49.5%      |
|         5 | weakening  | 17712 | -0.02%        | -0.01%   |  -1.035 | 49.8%      |
|         5 | leading    | 15331 | -0.03%        | -0.02%   |  -1.094 | 49.3%      |
|        10 | lagging    | 15576 | 0.06%         | 0.03%    |   1.504 | 50.5%      |
|        10 | improving  | 18070 | 0.02%         | 0.01%    |   0.429 | 50.1%      |
|        10 | leading    | 15312 | -0.02%        | -0.03%   |  -0.46  | 49.5%      |
|        10 | weakening  | 17704 | -0.06%        | -0.06%   |  -1.3   | 48.6%      |
|        21 | improving  | 18033 | 0.10%         | 0.05%    |   1.04  | 50.8%      |
|        21 | lagging    | 15540 | 0.06%         | -0.02%   |   0.74  | 49.6%      |
|        21 | weakening  | 17687 | -0.05%        | -0.08%   |  -0.543 | 48.9%      |
|        21 | leading    | 15281 | -0.11%        | -0.14%   |  -1.393 | 48.0%      |
|        63 | lagging    | 15434 | 0.20%         | 0.06%    |   0.91  | 50.6%      |
|        63 | improving  | 17842 | 0.16%         | 0.02%    |   0.669 | 50.2%      |
|        63 | weakening  | 17602 | 0.14%         | 0.06%    |   0.571 | 50.5%      |
|        63 | leading    | 15201 | -0.54%        | -0.44%   |  -2.669 | 46.4%      |

Interpretation: the continuous scatter coordinates are a timing map, not a buy list. The strongest lesson is contrarian/aging-leadership risk: if a sector is already far into Leading, the forward cross-sectional edge often deteriorates.

## Episode Backtests

Sector episode rows come from `tm_episodes.json`. The test measures next-session tradable ETF forward excess return after Time Machine `in`/`out` episode dates.

| date_basis   |   horizon | direction   |   n_events | mean_fwd_xs   | median   |   t_hac | hit_rate   |
|:-------------|----------:|:------------|-----------:|:--------------|:---------|--------:|:-----------|
| onset_date   |         5 | in          |        356 | 0.38%         | 0.31%    |   4.764 | 59.6%      |
| onset_date   |         5 | out         |        391 | -0.18%        | -0.02%   |  -1.642 | 48.6%      |
| onset_date   |        10 | in          |        356 | 0.53%         | 0.32%    |   4.393 | 58.7%      |
| onset_date   |        10 | out         |        390 | -0.24%        | -0.40%   |  -1.646 | 43.8%      |
| onset_date   |        21 | in          |        355 | 0.44%         | 0.30%    |   2.174 | 52.7%      |
| onset_date   |        21 | out         |        388 | -0.04%        | -0.10%   |  -0.217 | 49.0%      |
| onset_date   |        63 | in          |        350 | 0.20%         | 0.42%    |   0.914 | 53.4%      |
| onset_date   |        63 | out         |        384 | 0.04%         | 0.24%    |   0.115 | 51.6%      |

Confirmed-date version:

| date_basis     |   horizon | direction   |   n_events | mean_fwd_xs   | median   |   t_hac | hit_rate   |
|:---------------|----------:|:------------|-----------:|:--------------|:---------|--------:|:-----------|
| confirmed_date |         5 | in          |        356 | 0.12%         | 0.01%    |   1.223 | 50.3%      |
| confirmed_date |         5 | out         |        391 | 0.01%         | 0.03%    |   0.11  | 50.4%      |
| confirmed_date |        10 | in          |        356 | 0.14%         | 0.03%    |   1.14  | 51.7%      |
| confirmed_date |        10 | out         |        390 | 0.08%         | -0.15%   |   0.444 | 47.4%      |
| confirmed_date |        21 | in          |        355 | -0.01%        | 0.04%    |  -0.083 | 50.4%      |
| confirmed_date |        21 | out         |        388 | 0.11%         | 0.05%    |   0.641 | 50.8%      |
| confirmed_date |        63 | in          |        350 | -0.31%        | -0.26%   |  -2.001 | 48.6%      |
| confirmed_date |        63 | out         |        384 | 0.22%         | 0.29%    |   0.861 | 52.3%      |

Most common inverse episode pairs, where an `in` episode in one ETF appears within +/-14 calendar days of an `out` episode in another:

| in_node   | out_node   |   n |   median_lag_days |   mean_lag_days |
|:----------|:-----------|----:|------------------:|----------------:|
| XLF       | XLU        |  10 |               8.5 |            4    |
| XLV       | XLY        |   8 |              -4   |           -1.38 |
| XLF       | XLP        |   7 |              11   |            2    |
| XLF       | XLE        |   6 |               4.5 |            3    |
| XLB       | XLP        |   6 |              11.5 |            8.17 |
| XLRE      | XLY        |   5 |              -9   |           -6.8  |
| XLRE      | XLC        |   5 |              -8   |           -1.4  |
| XLK       | XLU        |   5 |              -5   |           -2    |
| XLU       | XLY        |   5 |              10   |            3    |
| XLRE      | XLK        |   4 |              -7.5 |           -5.75 |
| XLRE      | XLE        |   4 |              -7   |           -6.25 |
| XLB       | XLU        |   4 |              -5.5 |           -2.5  |
| XLI       | XLY        |   4 |               0   |            0.75 |
| XLRE      | XLP        |   4 |               0.5 |            0.5  |
| XLU       | XLK        |   4 |               1   |            0.75 |

## Correlation And Inverse Relationships

Strongest negative 21-day relative-return correlations among sector ETFs:

| a   | b    |   corr_21d_rel |
|:----|:-----|---------------:|
| XLE | XLY  |         -0.413 |
| XLE | XLRE |         -0.413 |
| XLF | XLU  |         -0.386 |
| XLU | XLY  |         -0.37  |
| XLI | XLU  |         -0.345 |
| XLK | XLP  |         -0.335 |
| XLC | XLU  |         -0.324 |
| XLI | XLP  |         -0.32  |
| XLB | XLC  |         -0.317 |
| XLI | XLV  |         -0.305 |
| XLE | XLK  |         -0.303 |
| XLB | XLU  |         -0.303 |
| XLF | XLRE |         -0.3   |
| XLE | XLV  |         -0.285 |
| XLB | XLV  |         -0.284 |

Strongest negative cross-leads: sector A `rs_mom` today vs sector B 21-day forward excess return.

| signal_sector   | return_sector   |   spearman |    n |
|:----------------|:----------------|-----------:|-----:|
| XLI             | XLC             |     -0.207 | 1976 |
| XLE             | XLRE            |     -0.127 | 2654 |
| XLF             | XLC             |     -0.11  | 1976 |
| XLF             | XLU             |     -0.104 | 6879 |
| XLC             | XLY             |     -0.093 | 1976 |
| XLC             | XLK             |     -0.08  | 1976 |
| XLP             | XLY             |     -0.077 | 6879 |
| XLY             | XLV             |     -0.074 | 6879 |
| XLU             | XLY             |     -0.074 | 6879 |
| XLU             | XLK             |     -0.065 | 6879 |
| XLP             | XLRE            |     -0.061 | 2654 |
| XLV             | XLI             |     -0.057 | 6879 |
| XLF             | XLP             |     -0.057 | 6879 |
| XLK             | XLC             |     -0.054 | 1976 |
| XLU             | XLE             |     -0.052 | 6879 |

Strongest positive cross-leads:

| signal_sector   | return_sector   |   spearman |    n |
|:----------------|:----------------|-----------:|-----:|
| XLE             | XLC             |      0.191 | 1976 |
| XLK             | XLRE            |      0.129 | 2654 |
| XLC             | XLE             |      0.109 | 1976 |
| XLV             | XLC             |      0.091 | 1976 |
| XLI             | XLRE            |      0.082 | 2654 |
| XLB             | XLRE            |      0.081 | 2654 |
| XLU             | XLP             |      0.078 | 6879 |
| XLU             | XLC             |      0.067 | 1976 |
| XLRE            | XLB             |      0.064 | 2654 |
| XLE             | XLK             |      0.063 | 6879 |
| XLF             | XLK             |      0.063 | 6879 |
| XLE             | XLY             |      0.061 | 6879 |
| XLC             | XLRE            |      0.061 | 1976 |
| XLB             | XLU             |      0.058 | 6879 |
| XLU             | XLV             |      0.052 | 6879 |

Trading read: inverse pairs are best used as confirmation and risk-budget context. A sector entering Improving is stronger when its opposite complex has simultaneous Weakening/Out pressure; it is weaker when its expected inverse stays resilient.

## Rotation Schedule

The schedule below smooths Time Machine composite position with a 21-session mean, then records persistent leader regimes of at least 10 trading days.

Most frequent leader transitions:

| from   | to   |   n |   median_gap_days |
|:-------|:-----|----:|------------------:|
| XLU    | XLE  |  13 |               4   |
| XLE    | XLK  |  12 |               3   |
| XLY    | XLE  |  10 |               5.5 |
| XLE    | XLY  |   9 |               3   |
| XLE    | XLU  |   9 |               6   |
| XLK    | XLU  |   9 |               1   |
| XLK    | XLY  |   8 |               1   |
| XLB    | XLU  |   7 |               3   |
| XLP    | XLE  |   7 |               3   |
| XLE    | XLB  |   7 |               3   |
| XLE    | XLV  |   7 |               3   |
| XLU    | XLB  |   6 |               5   |
| XLU    | XLK  |   6 |               1   |
| XLK    | XLF  |   5 |               6   |
| XLK    | XLE  |   5 |               6   |

Recent persistent leader runs:

| leader   | start      | end        |   n_trading_days |
|:---------|:-----------|:-----------|-----------------:|
| XLK      | 2026-04-17 | 2026-06-23 |               46 |
| XLE      | 2026-03-23 | 2026-04-14 |               16 |
| XLU      | 2026-03-04 | 2026-03-20 |               13 |
| XLE      | 2026-02-10 | 2026-02-26 |               12 |
| XLB      | 2025-12-22 | 2026-02-09 |               33 |
| XLV      | 2025-10-27 | 2025-12-15 |               35 |
| XLU      | 2025-10-13 | 2025-10-24 |               10 |
| XLC      | 2025-09-19 | 2025-10-06 |               12 |
| XLY      | 2025-08-06 | 2025-09-05 |               22 |
| XLK      | 2025-05-06 | 2025-08-05 |               63 |
| XLP      | 2025-03-04 | 2025-03-20 |               13 |
| XLE      | 2025-01-22 | 2025-02-05 |               11 |
| XLY      | 2024-11-26 | 2025-01-03 |               26 |
| XLE      | 2024-10-18 | 2024-11-05 |               13 |
| XLY      | 2024-09-23 | 2024-10-15 |               17 |
| XLRE     | 2024-07-23 | 2024-09-20 |               43 |
| XLK      | 2024-06-10 | 2024-07-09 |               20 |
| XLU      | 2024-05-06 | 2024-06-07 |               24 |

Schedule heuristic to test in production: `opposite-complex out episode` -> `target in/onset or rs_mom > 0 while rs_ratio < 0` -> `family sponsor_score rising 5/21 sessions` -> `ETF price/flow confirmation` -> `Leading state persistence check`. That sequence is more robust than buying the first green dot.

## Theme/Subsector Sponsorship

Direct `us_sector_*` Time Machine nodes vs sector ETF forward returns:

|   horizon | signal        |   n_days |   mean_ic |   median_ic |   t_hac | hit_rate   |
|----------:|:--------------|---------:|----------:|------------:|--------:|:-----------|
|         5 | rs_mom        |      761 |     0.024 |       0.055 |   0.999 | 55.1%      |
|         5 | pos           |      761 |     0.009 |      -0.005 |   0.427 | 48.8%      |
|         5 | rs_ratio      |      761 |     0.009 |       0.009 |   0.382 | 50.9%      |
|         5 | rs_mom_chg5   |      756 |    -0.015 |      -0.018 |  -0.745 | 48.3%      |
|         5 | rs_ratio_chg5 |      756 |    -0.018 |      -0.023 |  -0.842 | 47.9%      |
|         5 | pos_chg5      |      756 |    -0.02  |      -0.027 |  -0.978 | 47.1%      |
|        10 | rs_mom        |      756 |     0.038 |       0.016 |   1.3   | 51.7%      |
|        10 | pos           |      756 |     0.025 |       0.009 |   0.866 | 50.1%      |
|        10 | rs_ratio      |      756 |     0.003 |       0     |   0.117 | 49.6%      |
|        10 | rs_ratio_chg5 |      751 |    -0.005 |      -0.018 |  -0.186 | 47.9%      |
|        10 | pos_chg5      |      751 |    -0.019 |      -0.018 |  -0.915 | 47.3%      |
|        10 | rs_mom_chg5   |      751 |    -0.022 |      -0.036 |  -1.127 | 46.9%      |
|        21 | rs_mom        |      745 |     0.076 |       0.091 |   2.09  | 58.0%      |
|        21 | pos           |      745 |     0.053 |       0.027 |   1.574 | 52.5%      |
|        21 | rs_ratio_chg5 |      740 |     0.02  |       0.007 |   0.752 | 50.1%      |
|        21 | rs_ratio      |      745 |     0.017 |       0     |   0.454 | 49.8%      |

Broad mapped theme/subsector family sponsorship vs sector ETF forward returns. The broad family levels are weak as direct ranks; use them as confluence/context, especially their changes and current breadth.

|   horizon | signal             |   n_days |   mean_ic |   median_ic |   t_hac | hit_rate   |
|----------:|:-------------------|---------:|----------:|------------:|--------:|:-----------|
|         5 | hot_breadth_chg5   |     1220 |     0.006 |       0.018 |   0.42  | 52.0%      |
|         5 | mean_mom_chg5      |     1220 |    -0.001 |       0     |  -0.072 | 49.8%      |
|         5 | sponsor_score_chg5 |     1220 |    -0.001 |       0.009 |  -0.095 | 50.6%      |
|         5 | mean_mom           |     1225 |    -0.006 |      -0.018 |  -0.317 | 48.2%      |
|         5 | improving_breadth  |     1225 |    -0.011 |      -0.018 |  -0.675 | 48.0%      |
|         5 | mean_pos           |     1225 |    -0.016 |      -0.027 |  -0.87  | 46.6%      |
|         5 | hot_breadth        |     1225 |    -0.018 |      -0.027 |  -1.027 | 46.9%      |
|         5 | sponsor_score      |     1225 |    -0.019 |      -0.027 |  -1.028 | 47.3%      |
|        10 | mean_mom_chg5      |     1215 |     0.02  |       0.027 |   1.332 | 51.4%      |
|        10 | sponsor_score_chg5 |     1215 |     0.017 |       0.027 |   1.07  | 51.9%      |
|        10 | hot_breadth_chg5   |     1215 |     0.008 |       0.027 |   0.555 | 52.5%      |
|        10 | mean_mom           |     1220 |    -0.008 |      -0.009 |  -0.326 | 47.9%      |
|        10 | improving_breadth  |     1220 |    -0.009 |      -0.008 |  -0.402 | 48.8%      |
|        10 | mean_pos           |     1220 |    -0.012 |      -0.018 |  -0.531 | 48.2%      |
|        10 | sponsor_score      |     1220 |    -0.017 |      -0.018 |  -0.734 | 48.3%      |
|        10 | hot_breadth        |     1220 |    -0.021 |      -0.03  |  -0.896 | 47.0%      |

Current confluence snapshot:

| node   | sector_name        | tm_sector_quadrant   |   tm_sector_pos | tm_usnode_quadrant   |   tm_usnode_pos |   sponsor_score | hot_breadth   | improving_breadth   | live_quadrant   |   live_emerging_score |
|:-------|:-------------------|:---------------------|----------------:|:---------------------|----------------:|----------------:|:--------------|:--------------------|:----------------|----------------------:|
| XLV    | Health Care        | leading              |            2.51 | leading              |            1    |           1.379 | 94.4%         | 11.1%               | leading         |                 2.584 |
| XLF    | Financials         | leading              |            1.84 | leading              |            0.85 |           1.218 | 83.3%         | 22.2%               | leading         |                 1.864 |
| XLC    | Comm Services      | improving            |            0.09 | improving            |            0.28 |           0.456 | 80.0%         | 40.0%               | improving       |                 2.088 |
| XLY    | Cons Discretionary | improving            |            0.74 | improving            |            0.35 |           0.246 | 76.1%         | 58.7%               | improving       |                 1.416 |
| XLP    | Cons Staples       | lagging              |           -0.33 | improving            |            0.42 |           0.257 | 84.2%         | 73.7%               | leading         |                 0.3   |
| XLI    | Industrials        | leading              |            0.82 | improving            |            0.28 |           0.387 | 65.3%         | 46.9%               | weakening       |                -1.067 |
| XLU    | Utilities          | improving            |            0.13 | improving            |            0.29 |          -1.095 | 0.0%          | 0.0%                | improving       |                -0.034 |
| XLRE   | Real Estate        | weakening            |           -0.16 | improving            |            0.21 |           0.451 | 75.0%         | 0.0%                | weakening       |                -0.581 |
| XLB    | Materials          | lagging              |           -0.65 | leading              |            0.25 |          -0.138 | 64.3%         | 46.4%               | lagging         |                -0.515 |
| XLE    | Energy             | lagging              |           -2.86 | improving            |           -0.49 |          -0.617 | 50.0%         | 50.0%               | lagging         |                -1.584 |
| XLK    | Technology         | weakening            |           -2.13 | lagging              |           -0.84 |          -0.441 | 40.4%         | 31.9%               | weakening       |                -4.471 |

Top current mapped family nodes by sector:

| anchor_etf   | sector             | node                     | node_tier   | theme                        | quadrant   |   rs_ratio |   rs_mom |   pos |
|:-------------|:-------------------|:-------------------------|:------------|:-----------------------------|:-----------|-----------:|---------:|------:|
| XLB          | Materials          | nanotechproducts         | subsector   | Nanotechnology               | leading    |       1.36 |     0.48 |  1.84 |
| XLB          | Materials          | nanotechmaterials        | subsector   | Nanotechnology               | leading    |       1.23 |     0.02 |  1.25 |
| XLB          | Materials          | nanotechmedicine         | subsector   | Nanotechnology               | leading    |       0.3  |     0.81 |  1.11 |
| XLB          | Materials          | environmentalwaste       | subsector   | Environmental Sustainability | leading    |      -0    |     0.97 |  0.97 |
| XLB          | Materials          | environmentalwater       | subsector   | Environmental Sustainability | improving  |      -0.03 |     0.72 |  0.69 |
| XLC          | Comm Services      | socialniche              | subsector   | Social Media                 | leading    |       0.15 |     1.12 |  1.27 |
| XLC          | Comm Services      | socialadvertising        | subsector   | Social Media                 | leading    |       0.11 |     1.03 |  1.14 |
| XLC          | Comm Services      | Social Media             | theme       | Social Media                 | leading    |       0.07 |     0.99 |  1.06 |
| XLC          | Comm Services      | telecomsatcom            | subsector   | Telecommunications           | leading    |       0.26 |     0.68 |  0.94 |
| XLC          | Comm Services      | entertainmentgaming      | subsector   | Digital Entertainment        | leading    |       0.18 |     0.74 |  0.92 |
| XLE          | Energy             | energybaseutilities      | subsector   | Energy Traditional           | improving  |      -0.21 |     0.27 |  0.06 |
| XLE          | Energy             | commenergygaslng         | subsector   | Commodities Energy           | improving  |      -0.39 |     0.41 |  0.02 |
| XLE          | Energy             | energybaseoilrefining    | subsector   | Energy Traditional           | improving  |      -0.22 |     0.19 | -0.03 |
| XLE          | Energy             | commenergybiofuels       | subsector   | Commodities Energy           | improving  |      -0.67 |     0.61 | -0.06 |
| XLE          | Energy             | energycleanutilities     | subsector   | Energy Renewable             | improving  |      -0.33 |     0.25 | -0.08 |
| XLF          | Financials         | fintechneobanks          | subsector   | FinTech                      | leading    |       3.05 |     4.49 |  7.54 |
| XLF          | Financials         | payments_fintech         | subsector   |                              | leading    |       0.94 |     1.98 |  2.92 |
| XLF          | Financials         | FinTech                  | theme       | FinTech                      | leading    |       0.6  |     1.14 |  1.74 |
| XLF          | Financials         | fintechinsurance         | subsector   | FinTech                      | leading    |       0.78 |     0.84 |  1.62 |
| XLF          | Financials         | fintechpayments          | subsector   | FinTech                      | leading    |       0.4  |     1.09 |  1.49 |
| XLI          | Industrials        | roboticsconsumer         | subsector   | Robotics                     | weakening  |      12.36 |    -4.77 |  7.59 |
| XLI          | Industrials        | Robotics                 | theme       | Robotics                     | weakening  |       3.19 |    -1.15 |  2.04 |
| XLI          | Industrials        | spacesatellites          | subsector   | Space Tech                   | leading    |       0.32 |     0.75 |  1.07 |
| XLI          | Industrials        | spacedefense             | subsector   | Space Tech                   | improving  |      -0.3  |     1.15 |  0.85 |
| XLI          | Industrials        | defensecyberdefense      | subsector   | Defense & Aerospace          | improving  |      -0.44 |     1.21 |  0.77 |
| XLK          | Technology         | softwarevsaas            | subsector   | Software                     | improving  |      -0.41 |     1.47 |  1.06 |
| XLK          | Technology         | bigdataproviders         | subsector   | Big Data                     | improving  |      -0.23 |     1.17 |  0.94 |
| XLK          | Technology         | softwaregaming           | subsector   | Software                     | improving  |      -0.03 |     0.93 |  0.9  |
| XLK          | Technology         | aiadssearch              | subsector   | Artificial Intelligence      | leading    |       0.02 |     0.84 |  0.86 |
| XLK          | Technology         | ai_agents                | subsector   |                              | improving  |      -0.28 |     1.03 |  0.75 |
| XLP          | Cons Staples       | nutritionsupplements     | subsector   | Healthy Food & Nutrition     | improving  |      -0.13 |     1.45 |  1.32 |
| XLP          | Cons Staples       | consumersecondhand       | subsector   | Consumer Goods               | leading    |       0.13 |     0.74 |  0.87 |
| XLP          | Cons Staples       | Healthy Food & Nutrition | theme       | Healthy Food & Nutrition     | improving  |      -0.17 |     0.8  |  0.63 |
| XLP          | Cons Staples       | nutritionmealdelivery    | subsector   | Healthy Food & Nutrition     | improving  |      -0.06 |     0.66 |  0.6  |
| XLP          | Cons Staples       | defensives               | subsector   |                              | improving  |      -0.01 |     0.61 |  0.6  |
| XLRE         | Real Estate        | realestateoffice         | subsector   | Real Estate & REITs          | leading    |       0.77 |     0.25 |  1.02 |
| XLRE         | Real Estate        | realestatehealthcare     | subsector   | Real Estate & REITs          | leading    |       0.18 |     0.55 |  0.73 |
| XLRE         | Real Estate        | realestatehousing        | subsector   | Real Estate & REITs          | leading    |       0.07 |     0.5  |  0.57 |
| XLRE         | Real Estate        | realestatewarehousing    | subsector   | Real Estate & REITs          | leading    |       0.06 |     0.39 |  0.45 |
| XLRE         | Real Estate        | Real Estate & REITs      | theme       | Real Estate & REITs          | leading    |       0.1  |     0.21 |  0.31 |
| XLU          | Utilities          | power_grid               | subsector   |                              | lagging    |      -0.33 |    -0.27 | -0.6  |
| XLU          | Utilities          | data_center_power        | subsector   |                              | lagging    |      -0.41 |    -0.68 | -1.09 |
| XLV          | Health Care        | healthcarenextgen        | subsector   | Healthcare & Biotech         | leading    |       0.66 |     1.17 |  1.83 |
| XLV          | Health Care        | healthcaretelemedicine   | subsector   | Healthcare & Biotech         | leading    |       0.81 |     0.67 |  1.48 |
| XLV          | Health Care        | healthcarediagnostics    | subsector   | Healthcare & Biotech         | leading    |       0.65 |     0.79 |  1.44 |
| XLV          | Health Care        | managed_care             | subsector   |                              | weakening  |       1.53 |    -0.11 |  1.42 |
| XLV          | Health Care        | healthcareitdata         | subsector   | Healthcare & Biotech         | leading    |       0.55 |     0.83 |  1.38 |
| XLY          | Cons Discretionary | ecommercesecondhand      | subsector   | E-commerce                   | weakening  |       1.16 |    -0.04 |  1.12 |
| XLY          | Cons Discretionary | varealityapplications    | subsector   | Virtual & Augmented Reality  | improving  |      -0.13 |     1.1  |  0.97 |
| XLY          | Cons Discretionary | ecommerceplatforms       | subsector   | E-commerce                   | improving  |      -0.46 |     1.28 |  0.82 |
| XLY          | Cons Discretionary | varealityenterprise      | subsector   | Virtual & Augmented Reality  | improving  |      -0.15 |     0.91 |  0.76 |
| XLY          | Cons Discretionary | ecommerceadsmedia        | subsector   | E-commerce                   | leading    |       0.27 |     0.49 |  0.76 |

## Build Recommendations

1. Add a shadow `sector_rotation_schedule` artifact keyed by ETF with fields: `etf_tm_quadrant`, `etf_rs_mom_chg5`, `opposite_complex_pressure`, `family_sponsor_score`, `family_hot_breadth`, `family_sponsor_chg5`, and `schedule_stage`.
2. Treat `Improving + rising family sponsorship + inverse out pressure` as an alert, not an entry. Entry should require existing price/flow gates to confirm.
3. Track three clocks separately: growth clock (XLK/XLC/XLY), cyclical/commodity clock (XLE/XLB/XLI/XLF), defensive/rate clock (XLV/XLU/XLP/XLRE). Most false reads happen when those clocks are mixed into one scalar.
4. Persist daily family-group snapshots point-in-time. The current m-tier has a survivorship watermark, so backtests are research-grade only.
5. Add an error ledger for schedule calls: did an Improving sector become a top-3 ETF by 21/63d, and did its inverse complex actually weaken?

## Artifact Index

- Report: `reports/rotation-time-machine-sector-etf-research.md`
- CSV outputs: `reports/artifacts/rotation_time_machine/`
- Key CSVs: `sector_rank_ic.csv`, `sector_top_bottom.csv`, `quadrant_forward.csv`, `event_onset_returns.csv`, `inverse_episode_pairs.csv`, `family_rank_ic.csv`, `current_confluence.csv`.

## Limits

- Sector ETF tests before XLC/XLRE inception use the Time Machine sector feed but tradable forward-return rows only where ETF prices exist; cross-sectional tests require enough available ETF returns.
- M-tier subsector/theme history begins in 2021 and carries the dashboard caveat: membership as of 2026-06, historical composition approximated.
- These are overlapping forward windows. HAC t-statistics are reported to reduce, not eliminate, overlap distortion.
- This report does not claim a production trading edge; it identifies measurable confluence patterns to convert into shadow signals and ledgers.
