# Bitcoin Vector — calibration report

Span: 2015-01-01..2026-06-13 (4182 days). Split-half boundary: 2021-01-01.

House rule: a signal is trusted (labeled a *signal* in the UI) only if its forward outcome relationship trends in the expected direction in the full sample AND survives both halves (rank-trend |rho|>0.6, tolerant of one small-sample band). Return-predicting signals (momentum, structure, BFI) are judged on forward RETURN; the Risk Index is judged on forward DRAWDOWN (its actual job) because at long horizons extreme risk marks capitulation and forward *return* is U-shaped — the documented contrarian behavior, not a defect. Anything failing is context-only; anything inverted is flagged.

## Signal verdicts

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| risk_index | **CONFIRMED** | -1 | -1 | -1 | -1 |
| momentum | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| structure | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| risk_oscillator | **CONTEXT-ONLY** | 0 | 0 | -1 | -1 |
| bfi | **CONFIRMED** | 1 | 1 | 1 | 1 |

## Risk Index as a drawdown gauge

**CONFIRMED near-term risk gauge (7d drawdown)** — rank-trend {'full': -1, 'pre': -1, 'post': -1, 'want': -1, 'horizon': 7}.

| band   |    n |   avgDD_7d |   p05DD_7d |   avgDD_30d |   p05DD_30d |   avgDD_90d |   p05DD_90d |
|:-------|-----:|-----------:|-----------:|------------:|------------:|------------:|------------:|
| 0-25   | 2125 |      -2.97 |     -13.97 |       -8.25 |      -26.04 |      -14.05 |      -46.54 |
| 25-50  | 1268 |      -4.17 |     -16.61 |      -10.1  |      -30.9  |      -17.81 |      -50.5  |
| 50-75  |  691 |      -4.65 |     -20.78 |       -9.77 |      -37.07 |      -14.66 |      -41.94 |
| 75-100 |   98 |      -4.4  |     -16.25 |       -9    |      -27.8  |      -12.45 |      -32.79 |

### risk_index — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 2125 |     56.1 |      1.93 |      56.7 |       7.71 |      66   |      28.18 |
| 25-50  | 1268 |     53.2 |      0.69 |      57.8 |       5.44 |      53.3 |      17.88 |
| 50-75  |  691 |     53.6 |      0.68 |      58.9 |       4.6  |      56.2 |      14.1  |
| 75-100 |   98 |     49   |      1.89 |      56.7 |       4.16 |      58.8 |      15.46 |

### momentum — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-0.5   | 1024 |     53.2 |      0.21 |      57.3 |       2.15 |      52.1 |       6.84 |
| -0.5..0 |  675 |     51.4 |      0.69 |      57.2 |       4.15 |      58.2 |      19.28 |
| 0..0.5  |  785 |     51.6 |      0.68 |      53.8 |       5.64 |      55   |      23.4  |
| >0.5    | 1698 |     58.3 |      2.6  |      59.2 |      10.22 |      68.5 |      32.35 |

### structure — forward returns by band (full sample)

| band         |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| broken       | 1140 |     53   |      0.46 |      60.1 |       3.37 |      57.3 |      12.2  |
| neutral      | 1236 |     53.6 |      0.93 |      55.9 |       6.28 |      57.2 |      22.73 |
| constructive | 1806 |     56.5 |      2.19 |      56.8 |       8.44 |      64.5 |      28.75 |

### risk_oscillator — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| falling | 1655 |     55.8 |      1.94 |      58.6 |       6.19 |      58.9 |      22.46 |
| neutral | 1261 |     55   |      1.35 |      58.2 |       7.12 |      63.4 |      24.58 |
| rising  | 1266 |     53   |      0.57 |      55.1 |       6.05 |      59.3 |      20.25 |

### bfi — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <40    | 1567 |     51   |      0.51 |      52.7 |       3.65 |      50   |      13.58 |
| 40-60  | 1063 |     55   |      0.72 |      58.1 |       7.19 |      63.6 |      23.49 |
| >60    | 1477 |     58.4 |      2.75 |      62.1 |       9.04 |      69.9 |      32.19 |

## Allocation backtest vs HODL

|              |   cagr |   hodl_cagr |   sharpe |   hodl_sharpe |   sortino |   hodl_sortino |   maxdd |   hodl_maxdd |   time_in_market |   final_vs_hodl |
|:-------------|-------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|----------------:|
| conservative |   47.7 |          59 |     1.33 |          1.03 |      1.14 |           1.37 |   -27.4 |        -83.8 |             34.9 |            0.43 |
| moderate     |   66.2 |          59 |     1.44 |          1.03 |      1.55 |           1.37 |   -38.2 |        -83.8 |             56.4 |            1.66 |
| aggressive   |   61.9 |          59 |     1.25 |          1.03 |      1.4  |           1.37 |   -57.2 |        -83.8 |             64.1 |            1.23 |
| optimal      |   65.2 |          59 |     1.42 |          1.03 |      1.56 |           1.37 |   -42   |        -83.8 |             58.6 |            1.55 |

## Whipsaw

|                  |   changes |   whipsaws |   pct |
|:-----------------|----------:|-----------:|------:|
| momentum_state   |       180 |         36 |  20   |
| risk_regime      |       126 |         25 |  19.8 |
| structure_state  |       178 |         36 |  20.2 |
| market_mode      |        86 |         14 |  16.3 |
| alt_cycle_leader |        94 |         16 |  17   |