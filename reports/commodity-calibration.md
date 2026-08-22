# Commodity Vector — calibration report

Split-half boundary: 2013-01-01. Forward horizons: [21, 63, 126] days.

House rule: a relationship is trusted (labeled a *signal* in the UI) only if its forward-return rank-trend holds in the expected direction in the full sample AND survives both halves. The Risk Index is judged on forward DRAWDOWN (its real job). **shock_z** (the residual exogenous-bid detector) is judged directionally: CONFIRMED = bids persist (momentum), INVERTED = bids fade (mean-reversion) — both honest. Anything failing is context-only.


## GOLD — 2001-01-02..2026-08-21 (6441 days)

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| momentum | **CONTEXT-ONLY** | 0 | -1 | 1 | 1 |
| ts_momentum | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| structure | **CONTEXT-ONLY** | 0 | -1 | 1 | 1 |
| gsr_pctile | **CONFIRMED** | 1 | 1 | 1 | 1 |
| driver_score | **INVERTED** | -1 | -1 | -1 | 1 |
| shock_z | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| pos_pctile | **INVERTED** | 1 | 0 | 1 | -1 |
| risk_index (drawdown) | **CONFIRMED near-term risk gauge** | -1 | -1 | -1 | -1 |

### gold · momentum — forward returns by band (full)

| band    |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:--------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-0.5   | 1337 |      60.3 |       0.94 |      61.9 |       2.23 |       68.8 |        4.98 |
| -0.5..0 | 1114 |      59.4 |       1.35 |      64.8 |       2.59 |       70.4 |        6.07 |
| 0..0.5  | 1175 |      55.1 |       0.89 |      68.2 |       4.19 |       74.2 |        7.53 |
| >0.5    | 2815 |      56   |       1.01 |      63.5 |       3.2  |       71.6 |        6.76 |

### gold · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down |  474 |      56.1 |       0.7  |      56.8 |       1.45 |       45.4 |        1.13 |
| down        | 1083 |      53.8 |       0.78 |      60.3 |       1.78 |       66.9 |        4.21 |
| up          | 1258 |      54.1 |       0.72 |      59.5 |       2.62 |       71.4 |        5.59 |
| strong-up   | 3458 |      59.6 |       1.27 |      67.7 |       3.92 |       75.4 |        8.28 |

### gold · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1717 |      60.1 |       1.27 |      61.9 |       2.23 |       69.6 |        5.53 |
| neutral      | 1970 |      54.9 |       0.74 |      66.9 |       3.61 |       71.7 |        6.82 |
| constructive | 2754 |      57.3 |       1.09 |      63.7 |       3.21 |       72   |        6.67 |

### gold · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1272 |      54   |       0.75 |      55.4 |       1.91 |       69.6 |        4.57 |
| 20-40  |  862 |      52.1 |       0.48 |      55.6 |       2.08 |       61.8 |        5.67 |
| 40-60  |  807 |      59.1 |       1.33 |      65.7 |       3.58 |       65.1 |        4.86 |
| 60-80  |  997 |      55.1 |       0.77 |      67.9 |       3.54 |       79.8 |        8.9  |
| 80-100 | 2399 |      61.4 |       1.41 |      69.4 |       3.72 |       73.4 |        7.16 |

### gold · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1696 |      61.9 |       1.47 |      73.4 |       4.58 |       79.8 |        8.84 |
| neutral  | 2703 |      55.3 |       0.76 |      62.2 |       2.2  |       67.7 |        5.3  |
| tailwind | 2042 |      56.3 |       1.02 |      59.5 |       3.02 |       69.2 |        5.94 |

### gold · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +3.4% 67.9%hit (n=336) [flat]; high >1.5: +7.0% 69.3%hit (n=582) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  336 |      65.8 |       1.88 |      50.2 |       0.66 |       67.9 |        3.36 |
| -1.5..-.5 | 1290 |      57.6 |       0.99 |      65.9 |       3.37 |       69.4 |        6.48 |
| -.5..5    | 2058 |      57.6 |       1.26 |      65.2 |       3.61 |       70.8 |        6.9  |
| .5..1.5   | 1094 |      54.1 |       0.83 |      59.6 |       2.86 |       65.2 |        6.18 |
| >1.5      |  582 |      52.8 |       0.32 |      62.8 |       2.53 |       69.3 |        7.01 |

### gold · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  951 |      63.1 |       1.34 |      67.3 |       3    |       69   |        5.22 |
| 15-50  | 1813 |      54.7 |       0.57 |      58.1 |       1.85 |       70.6 |        5.91 |
| 50-85  | 2158 |      56.5 |       1.21 |      65.8 |       3.73 |       70.3 |        6.67 |
| 85-100 | 1407 |      58.4 |       1.2  |      66.9 |       3.84 |       74.1 |        7.64 |

### gold · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      58.4 |       1.11 |      62   |       2.9  |       68.6 |        6.11 |
| Stagflation     | 1605 |      53.3 |       0.98 |      62.4 |       3.3  |       72.8 |        6.98 |
| Goldilocks      | 1563 |      61   |       1.2  |      67.1 |       2.78 |       70.9 |        6.29 |
| Deflation-scare | 1712 |      56.8 |       0.85 |      65.5 |       3.29 |       72.7 |        6.3  |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    5.5 |          6.2 |            0.7 |        11.8 |     0.64 |          0.71 |      0.5  |           0.95 |   -14.3 |        -44.4 |             35.2 |               8.8 |            0.23 |
| moderate     |    4.9 |          5.8 |            0.9 |        11.8 |     0.49 |          0.71 |      0.48 |           0.95 |   -33.3 |        -44.4 |             58.3 |              10.1 |            0.2  |
| aggressive   |    5.7 |          6.6 |            0.9 |        11.8 |     0.49 |          0.71 |      0.52 |           0.95 |   -32.2 |        -44.4 |             68.1 |              10.1 |            0.24 |
| optimal      |    5.3 |          6.2 |            0.8 |        11.8 |     0.52 |          0.71 |      0.52 |           0.95 |   -33.7 |        -44.4 |             60.8 |               9.8 |            0.22 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.6447**; observed SR 0.52 ann vs haircut SR0 0.44 ann (N=40 trials, T=6441d, skew=-0.914, kurt=20.599).

## SILVER — 2001-01-02..2026-08-21 (6443 days)

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| momentum | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| ts_momentum | **DIRECTIONAL (one half weak)** | 1 | -1 | 1 | 1 |
| structure | **CONTEXT-ONLY** | 0 | -1 | 1 | 1 |
| gsr_pctile | **CONFIRMED** | 1 | 1 | 1 | 1 |
| driver_score | **CONTEXT-ONLY** | 0 | -1 | 0 | 1 |
| shock_z | **CONTEXT-ONLY** | 0 | 0 | -1 | 1 |
| pos_pctile | **CONTEXT-ONLY** | 0 | -1 | 1 | -1 |
| risk_index (drawdown) | **CONFIRMED near-term risk gauge** | -1 | -1 | -1 | -1 |

### silver · momentum — forward returns by band (full)

| band    |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:--------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-0.5   | 1845 |      56.1 |       1.23 |      64.1 |       3.59 |       63.1 |        6.98 |
| -0.5..0 | 1156 |      57.4 |       2.15 |      60.2 |       4.5  |       61.6 |        6.78 |
| 0..0.5  | 1040 |      53.3 |       1.3  |      56.3 |       3.98 |       58.5 |        9.14 |
| >0.5    | 2402 |      49.5 |       0.86 |      50   |       3.61 |       56.2 |        9.14 |

### silver · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1552 |      52.4 |       1.35 |      60.8 |       3.48 |       59.6 |        5.83 |
| down        |  786 |      47.8 |      -0.04 |      52   |       1.16 |       58.4 |        4.75 |
| up          |  791 |      51.3 |       1.22 |      58.5 |       4.82 |       58.2 |        7.72 |
| strong-up   | 3146 |      56.7 |       1.68 |      57.3 |       4.73 |       61   |       10.77 |

### silver · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 2007 |      56.4 |       1.41 |      63.3 |       3.42 |       65.2 |        6.61 |
| neutral      | 1986 |      54.2 |       1.09 |      59.2 |       3.35 |       55.5 |        7.04 |
| constructive | 2450 |      50.3 |       1.3  |      49.6 |       4.53 |       58.1 |       10.15 |

### silver · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1273 |      51.4 |       0.84 |      47.5 |       1.23 |       48.5 |        1.74 |
| 20-40  |  862 |      47.7 |       0.67 |      51.8 |       2.44 |       53.1 |        7.12 |
| 40-60  |  807 |      57   |       1.63 |      56.1 |       5.19 |       55.4 |        5.08 |
| 60-80  |  997 |      47.6 |       0.45 |      59.1 |       3.67 |       66.4 |       12.23 |
| 80-100 | 2400 |      58.3 |       2.05 |      64.5 |       5.56 |       67.3 |       11.39 |

### silver · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1584 |      55   |       1.53 |      61.5 |       4.05 |       69.5 |        9.68 |
| neutral  | 2766 |      49.9 |       0.64 |      55.4 |       2.93 |       55.8 |        6.23 |
| tailwind | 2093 |      56.8 |       1.9  |      55.2 |       4.82 |       57   |        9.4  |

### silver · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +13.7% 65.0%hit (n=361) [STRONG]; high >1.5: +6.6% 54.1%hit (n=482) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  361 |      63.4 |       2.33 |      65.3 |       5.44 |       65   |       13.72 |
| -1.5..-.5 | 1390 |      55.4 |       1.29 |      62.5 |       4.22 |       61.8 |        7.23 |
| -.5..5    | 1982 |      49.7 |       0.93 |      55.2 |       2.92 |       55.9 |        7.1  |
| .5..1.5   | 1146 |      52   |       1.22 |      49.7 |       4.28 |       57.5 |       11.23 |
| >1.5      |  482 |      51.2 |       2.29 |      50.2 |       5.46 |       54.1 |        6.61 |

### silver · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1146 |      60.2 |       2.13 |      68.7 |       5.98 |       63.4 |        7.32 |
| 15-50  | 2020 |      53.3 |       1.48 |      51.6 |       2.52 |       62.2 |        5.93 |
| 50-85  | 2040 |      51.2 |       1.12 |      57   |       4.82 |       57   |       10.91 |
| 85-100 | 1125 |      52   |       0.58 |      57.6 |       2.77 |       59   |        8.66 |

### silver · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1562 |      56.9 |       2.09 |      62.4 |       4.7  |       67.4 |       10    |
| Stagflation     | 1606 |      53.9 |       1.5  |      54.7 |       3.93 |       53.5 |        7.48 |
| Goldilocks      | 1563 |      49.5 |       0.38 |      52.8 |       0.96 |       54   |        5.14 |
| Deflation-scare | 1712 |      53.3 |       1.1  |      57.2 |       5.43 |       62.6 |        9.54 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    1.3 |          2   |            0.7 |        11.2 |     0.16 |          0.49 |      0.11 |            0.6 |   -50.5 |        -75.8 |             28.4 |               8.6 |            0.09 |
| moderate     |    1.6 |          2.4 |            0.8 |        11.2 |     0.18 |          0.49 |      0.15 |            0.6 |   -59.4 |        -75.8 |             47.2 |               9.9 |            0.1  |
| aggressive   |    2.6 |          3.5 |            0.8 |        11.2 |     0.23 |          0.49 |      0.21 |            0.6 |   -73   |        -75.8 |             58.9 |              10.1 |            0.13 |
| optimal      |    1.6 |          2.4 |            0.8 |        11.2 |     0.18 |          0.49 |      0.15 |            0.6 |   -61.7 |        -75.8 |             51   |              10   |            0.1  |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0997**; observed SR 0.18 ann vs haircut SR0 0.44 ann (N=40 trials, T=6443d, skew=-2.741, kurt=74.526).

## COPPER — 2001-01-02..2026-08-21 (6446 days)

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| momentum | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| ts_momentum | **CONTEXT-ONLY** | 0 | 0 | 1 | 1 |
| structure | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| driver_score | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| shock_z | **CONTEXT-ONLY** | 0 | 1 | 0 | 1 |
| pos_pctile | **CONTEXT-ONLY** | 0 | -1 | 1 | -1 |
| risk_index (drawdown) | **DIRECTIONAL** | -1 | -1 | 1 | -1 |

### copper · momentum — forward returns by band (full)

| band    |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:--------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-0.5   | 1707 |      54.1 |      -0.17 |      56.2 |       1.13 |       58.7 |        4.45 |
| -0.5..0 | 1085 |      56.1 |       1.45 |      61.3 |       3.46 |       57.8 |        5.09 |
| 0..0.5  | 1190 |      57.5 |       1.68 |      57.1 |       3.97 |       55.9 |        6.15 |
| >0.5    | 2464 |      54.2 |       1.19 |      58.5 |       3.86 |       60.2 |        8.59 |

### copper · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1597 |      59   |       1.14 |      63.1 |       4.45 |       58.6 |        8.44 |
| down        | 1030 |      45.4 |      -0.38 |      42.7 |      -1.13 |       39.1 |       -0.48 |
| up          |  764 |      51.2 |       0.09 |      55.7 |      -0.37 |       65.6 |        2.55 |
| strong-up   | 2887 |      59.7 |       1.82 |      64.5 |       5.44 |       66.2 |        9.9  |

### copper · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1893 |      54   |      -0.09 |      55.2 |       1.43 |       59.4 |        4.48 |
| neutral      | 1928 |      55.7 |       1.08 |      58.1 |       2.29 |       54.3 |        3.25 |
| constructive | 2625 |      55.4 |       1.65 |      60.1 |       4.87 |       61.2 |       10.22 |

### copper · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1337 |      53.3 |       0.05 |      57.7 |       1.02 |       63.1 |        5.32 |
| neutral  | 2825 |      53.9 |       1.16 |      53.4 |       2.26 |       53.4 |        4.2  |
| tailwind | 2284 |      57.6 |       1.26 |      64   |       5.3  |       62.4 |        9.84 |

### copper · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +4.8% 56.9%hit (n=364) [flat]; high >1.5: +6.2% 51.4%hit (n=285) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  364 |      58.5 |       0.21 |      60.7 |       2.08 |       56.9 |        4.82 |
| -1.5..-.5 |  935 |      53.8 |      -0.07 |      52.8 |       0.88 |       50.9 |        2.37 |
| -.5..5    | 2039 |      59.1 |       1.44 |      57.6 |       2.58 |       56.5 |        4.48 |
| .5..1.5   |  993 |      45.7 |      -0.18 |      49.8 |       0.58 |       48   |        2.75 |
| >1.5      |  285 |      47   |      -1.13 |      54.7 |       1.95 |       51.4 |        6.25 |

### copper · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1276 |      58.9 |       1.91 |      62   |       6.34 |       60.7 |       11.89 |
| 15-50  | 1886 |      52   |       0.26 |      58.2 |       2.41 |       56.8 |        6.27 |
| 50-85  | 1747 |      55.5 |       1.1  |      53.7 |       0.83 |       57.5 |        2.09 |
| 85-100 | 1425 |      58.1 |       1.2  |      64.3 |       4.8  |       65.3 |        8.99 |

### copper · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.5 |       1.97 |      63.2 |       5.36 |       59.8 |        6.64 |
| Stagflation     | 1608 |      50.6 |       0.77 |      55.4 |       3.98 |       62.4 |        6.77 |
| Goldilocks      | 1564 |      50.9 |       0.11 |      50.1 |      -0.21 |       47.4 |        4.43 |
| Deflation-scare | 1713 |      57.2 |       1    |      62.9 |       3.04 |       63.7 |        7.69 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    4.5 |          5.1 |            0.7 |         8.5 |     0.41 |          0.44 |      0.32 |            0.6 |   -40.4 |        -69.4 |             31   |               8.2 |            0.38 |
| moderate     |    4   |          4.8 |            0.9 |         8.5 |     0.32 |          0.44 |      0.31 |            0.6 |   -59.9 |        -69.4 |             52.6 |              10.3 |            0.34 |
| aggressive   |    3.9 |          4.8 |            0.9 |         8.5 |     0.3  |          0.44 |      0.32 |            0.6 |   -61.8 |        -69.4 |             63.8 |              10.5 |            0.33 |
| optimal      |    4.3 |          5.1 |            0.8 |         8.5 |     0.34 |          0.44 |      0.34 |            0.6 |   -57   |        -69.4 |             55.6 |               9.8 |            0.37 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.308**; observed SR 0.34 ann vs haircut SR0 0.44 ann (N=40 trials, T=6446d, skew=-1.27, kurt=47.752).

## OIL — 2001-01-02..2026-08-21 (6445 days)

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| momentum | **CONTEXT-ONLY** | 0 | 0 | 1 | 1 |
| ts_momentum | **INVERTED** | -1 | -1 | -1 | 1 |
| structure | **CONTEXT-ONLY** | 0 | 0 | 1 | 1 |
| bw_change | **CONFIRMED** | 1 | 1 | 1 | 1 |
| driver_score | **CONFIRMED** | 1 | 1 | 1 | 1 |
| shock_z | **INVERTED** | -1 | -1 | -1 | 1 |
| pos_pctile | **CONTEXT-ONLY** | 0 | -1 | 0 | -1 |
| risk_index (drawdown) | **CONFIRMED near-term risk gauge** | -1 | -1 | -1 | -1 |

### oil · momentum — forward returns by band (full)

| band    |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:--------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-0.5   | 1733 |      52.7 |      -0.08 |      57.2 |       4.09 |       60.9 |        7.57 |
| -0.5..0 | 1108 |      57   |       1.77 |      63.6 |       5.18 |       59   |        6.92 |
| 0..0.5  | 1153 |      58.1 |       1.69 |      54.3 |       3.07 |       59.6 |        6.88 |
| >0.5    | 2451 |      52.6 |       0.96 |      55.9 |       1.53 |       54.6 |        3.68 |

### oil · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1926 |      55.9 |       1.73 |      63.9 |       8.84 |       66.6 |       13.45 |
| down        |  755 |      55.5 |       1.08 |      56.7 |       2.06 |       62.6 |        6.83 |
| up          |  767 |      56.2 |       1.04 |      59.4 |       1.86 |       58.9 |        5.44 |
| strong-up   | 2834 |      53   |       0.48 |      54.7 |       0.43 |       53.4 |        1.82 |

### oil · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1936 |      53.5 |       0.14 |      57.5 |       4.11 |       62.8 |        7.85 |
| neutral      | 1842 |      59.2 |       1.99 |      61.9 |       5.14 |       57.9 |        7.14 |
| constructive | 2667 |      51.6 |       0.82 |      53.9 |       1.02 |       54.4 |        3.53 |

### oil · bw_change — forward returns by band (full)

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     | 1211 |      46.7 |      -2.11 |      52.7 |      -1.92 |       46   |       -2.03 |
| -1.5..-.3 |  915 |      49   |      -0.33 |      49.3 |       1.52 |       45.3 |        0.58 |
| -.3..3    |  528 |      56.4 |       1.16 |      61.5 |       4.9  |       57.3 |        7.04 |
| .3..1.5   |  844 |      59.1 |       2.51 |      56   |       4.49 |       57.8 |        6.82 |
| >1.5      | 1246 |      55.5 |       2.47 |      55.6 |       4.17 |       59.3 |        8.5  |

### oil · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 2016 |      44.7 |      -1.65 |      47.9 |      -0.87 |       45.6 |       -0.34 |
| neutral  | 1913 |      60.2 |       2.38 |      61.8 |       4.85 |       59.5 |        7.01 |
| tailwind | 2516 |      57.6 |       1.94 |      61.3 |       4.95 |       66.6 |        9.92 |

### oil · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +12.7% 61.5%hit (n=375) [STRONG]; high >1.5: -4.3% 34.7%hit (n=356) [FADE]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  375 |      44   |      -1.21 |      58.5 |       6.8  |       61.5 |       12.7  |
| -1.5..-.5 | 1049 |      52.9 |       0.12 |      54.3 |       3.12 |       54.1 |        3.49 |
| -.5..5    | 1833 |      53.8 |       0.63 |      54.5 |       1.22 |       55.6 |        5.56 |
| .5..1.5   | 1000 |      51.4 |       1.18 |      49.3 |      -0.24 |       45.5 |       -1.61 |
| >1.5      |  356 |      53.9 |       1.32 |      50.3 |       1.77 |       34.7 |       -4.28 |

### oil · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  773 |      48.4 |       0.26 |      48.5 |       1.92 |       47.7 |        4.64 |
| 15-50  | 2242 |      54.8 |       0.62 |      60.5 |       4.52 |       62.4 |        6.57 |
| 50-85  | 1938 |      56.6 |       1.45 |      56   |       1.65 |       58.8 |        7.36 |
| 85-100 | 1385 |      54.4 |       1.31 |      61.2 |       4    |       58.5 |        4.68 |

### oil · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.2 |       2.52 |      67.6 |       5.44 |       70.6 |       11.38 |
| Stagflation     | 1606 |      52.7 |       0.74 |      53.9 |       2.87 |       61.8 |        6.76 |
| Goldilocks      | 1565 |      52.2 |       0.29 |      53.1 |       0.63 |       49.1 |        0.93 |
| Deflation-scare | 1713 |      51.5 |       0.3  |      54.7 |       3.42 |       50.3 |        4.2  |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    0.7 |          1.5 |            0.8 |         4.6 |     0.13 |         -0.02 |      0.1  |          -0.01 |   -64.1 |       -125.9 |             34   |               9.6 |            0.38 |
| moderate     |    0.9 |          1.8 |            0.8 |         4.6 |     0.15 |         -0.02 |      0.14 |          -0.01 |   -64.6 |       -125.9 |             52.1 |              10.1 |            0.4  |
| aggressive   |    2.8 |          3.6 |            0.8 |         4.6 |     0.24 |         -0.02 |      0.25 |          -0.01 |   -52.1 |       -125.9 |             62.1 |               9.6 |            0.64 |
| optimal      |    2.1 |          2.9 |            0.8 |         4.6 |     0.2  |         -0.02 |      0.21 |          -0.01 |   -63.5 |       -125.9 |             54.4 |              10   |            0.54 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.1236**; observed SR 0.2 ann vs haircut SR0 0.43 ann (N=40 trials, T=6445d, skew=-0.509, kurt=17.078).

## Trial log

As-of 2026-08-21: **40** declared independent trials per asset (upper-bound); 8 signal families screened across 4 assets; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 8.0bps one-way.