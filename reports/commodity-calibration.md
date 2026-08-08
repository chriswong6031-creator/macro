# Commodity Vector — calibration report

Split-half boundary: 2013-01-01. Forward horizons: [21, 63, 126] days.

House rule: a relationship is trusted (labeled a *signal* in the UI) only if its forward-return rank-trend holds in the expected direction in the full sample AND survives both halves. The Risk Index is judged on forward DRAWDOWN (its real job). **shock_z** (the residual exogenous-bid detector) is judged directionally: CONFIRMED = bids persist (momentum), INVERTED = bids fade (mean-reversion) — both honest. Anything failing is context-only.


## GOLD — 2001-01-02..2026-08-07 (6430 days)

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
| <-0.5   | 1337 |      60.1 |       0.9  |      62.2 |       2.26 |       68.8 |        4.98 |
| -0.5..0 | 1114 |      59.2 |       1.31 |      64.8 |       2.59 |       70.4 |        6.07 |
| 0..0.5  | 1170 |      55.1 |       0.89 |      68.2 |       4.19 |       74.2 |        7.53 |
| >0.5    | 2809 |      56   |       1.01 |      63.5 |       3.2  |       71.9 |        6.84 |

### gold · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down |  474 |      56.1 |       0.7  |      56.8 |       1.45 |       45.4 |        1.13 |
| down        | 1083 |      53.8 |       0.78 |      60.3 |       1.78 |       66.9 |        4.21 |
| up          | 1258 |      54.1 |       0.72 |      59.5 |       2.62 |       71.4 |        5.59 |
| strong-up   | 3447 |      59.5 |       1.25 |      67.8 |       3.94 |       75.6 |        8.35 |

### gold · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1717 |      59.8 |       1.21 |      62   |       2.24 |       69.6 |        5.53 |
| neutral      | 1969 |      54.9 |       0.74 |      67.1 |       3.63 |       71.7 |        6.82 |
| constructive | 2744 |      57.3 |       1.09 |      63.7 |       3.21 |       72.3 |        6.76 |

### gold · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1261 |      53.8 |       0.72 |      55.7 |       1.94 |       70.3 |        4.75 |
| 20-40  |  862 |      51.8 |       0.41 |      55.6 |       2.08 |       61.8 |        5.67 |
| 40-60  |  807 |      59.1 |       1.33 |      65.7 |       3.58 |       65.1 |        4.86 |
| 60-80  |  997 |      55.1 |       0.77 |      67.9 |       3.54 |       79.8 |        8.9  |
| 80-100 | 2399 |      61.4 |       1.41 |      69.4 |       3.72 |       73.4 |        7.16 |

### gold · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1696 |      61.6 |       1.42 |      73.4 |       4.58 |       79.8 |        8.84 |
| neutral  | 2692 |      55.3 |       0.76 |      62.3 |       2.21 |       67.7 |        5.3  |
| tailwind | 2042 |      56.3 |       1.02 |      59.6 |       3.03 |       69.6 |        6.04 |

### gold · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +3.4% 67.9%hit (n=336) [flat]; high >1.5: +7.0% 69.4%hit (n=581) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  336 |      65.8 |       1.88 |      50.2 |       0.66 |       67.9 |        3.36 |
| -1.5..-.5 | 1290 |      57.4 |       0.95 |      66.2 |       3.4  |       69.5 |        6.5  |
| -.5..5    | 2057 |      57.5 |       1.24 |      65.2 |       3.62 |       71   |        6.97 |
| .5..1.5   | 1085 |      54   |       0.83 |      59.6 |       2.86 |       65.4 |        6.23 |
| >1.5      |  581 |      52.8 |       0.32 |      62.8 |       2.53 |       69.4 |        7.04 |

### gold · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  951 |      63.1 |       1.34 |      67.3 |       3    |       69   |        5.22 |
| 15-50  | 1813 |      54.7 |       0.57 |      58.3 |       1.86 |       71.1 |        6.03 |
| 50-85  | 2158 |      56.3 |       1.17 |      65.9 |       3.74 |       70.3 |        6.67 |
| 85-100 | 1396 |      58.4 |       1.2  |      66.9 |       3.84 |       74.1 |        7.64 |

### gold · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      58.4 |       1.11 |      62   |       2.9  |       68.6 |        6.11 |
| Stagflation     | 1605 |      53.3 |       0.98 |      62.4 |       3.3  |       73.3 |        7.12 |
| Goldilocks      | 1552 |      60.7 |       1.15 |      67.5 |       2.81 |       70.9 |        6.29 |
| Deflation-scare | 1712 |      56.8 |       0.85 |      65.5 |       3.29 |       72.7 |        6.3  |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    5.5 |          6.2 |            0.7 |        11.5 |     0.65 |           0.7 |      0.51 |           0.93 |   -14.3 |        -44.4 |             35.3 |               8.8 |            0.24 |
| moderate     |    4.8 |          5.7 |            0.9 |        11.5 |     0.47 |           0.7 |      0.47 |           0.93 |   -33.3 |        -44.4 |             58.2 |              10.1 |            0.21 |
| aggressive   |    5.5 |          6.3 |            0.9 |        11.5 |     0.47 |           0.7 |      0.5  |           0.93 |   -32.2 |        -44.4 |             68   |              10.1 |            0.24 |
| optimal      |    5.2 |          6   |            0.8 |        11.5 |     0.5  |           0.7 |      0.5  |           0.93 |   -33.7 |        -44.4 |             60.8 |               9.8 |            0.23 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.6229**; observed SR 0.5 ann vs haircut SR0 0.44 ann (N=40 trials, T=6430d, skew=-0.917, kurt=20.631).

## SILVER — 2001-01-02..2026-08-07 (6432 days)

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
| <-0.5   | 1845 |      55.9 |       1.18 |      64.1 |       3.59 |       63.1 |        6.98 |
| -0.5..0 | 1156 |      57.3 |       2.12 |      60.5 |       4.6  |       61.9 |        6.86 |
| 0..0.5  | 1030 |      53.3 |       1.3  |      56.5 |       4.05 |       58.7 |        9.28 |
| >0.5    | 2401 |      49.5 |       0.86 |      50   |       3.61 |       56.2 |        9.18 |

### silver · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1552 |      52.4 |       1.35 |      60.8 |       3.48 |       59.6 |        5.83 |
| down        |  786 |      47.8 |      -0.04 |      52   |       1.16 |       58.4 |        4.75 |
| up          |  791 |      51.3 |       1.22 |      58.5 |       4.82 |       58.2 |        7.72 |
| strong-up   | 3135 |      56.6 |       1.63 |      57.5 |       4.8  |       61.2 |       10.89 |

### silver · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 2007 |      56.1 |       1.35 |      63.3 |       3.42 |       65.2 |        6.61 |
| neutral      | 1983 |      54.2 |       1.09 |      59.5 |       3.44 |       55.8 |        7.2  |
| constructive | 2442 |      50.3 |       1.3  |      49.7 |       4.53 |       58.1 |       10.15 |

### silver · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1262 |      51.2 |       0.79 |      48   |       1.36 |       49   |        1.96 |
| 20-40  |  862 |      47.3 |       0.57 |      51.8 |       2.44 |       53.1 |        7.12 |
| 40-60  |  807 |      57   |       1.63 |      56.1 |       5.19 |       55.4 |        5.08 |
| 60-80  |  997 |      47.6 |       0.45 |      59.1 |       3.67 |       66.4 |       12.23 |
| 80-100 | 2400 |      58.3 |       2.05 |      64.5 |       5.56 |       67.3 |       11.39 |

### silver · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1584 |      54.7 |       1.44 |      61.5 |       4.05 |       69.5 |        9.68 |
| neutral  | 2751 |      50   |       0.68 |      55.6 |       2.98 |       55.8 |        6.23 |
| tailwind | 2097 |      56.7 |       1.86 |      55.3 |       4.85 |       57.3 |        9.56 |

### silver · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +13.9% 65.4%hit (n=361) [STRONG]; high >1.5: +6.6% 54.1%hit (n=482) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  361 |      63.4 |       2.33 |      65.3 |       5.44 |       65.4 |       13.91 |
| -1.5..-.5 | 1390 |      55.2 |       1.23 |      62.5 |       4.22 |       62.2 |        7.41 |
| -.5..5    | 1979 |      49.6 |       0.9  |      55.5 |       3.01 |       56   |        7.11 |
| .5..1.5   | 1138 |      52   |       1.22 |      49.7 |       4.28 |       57.5 |       11.23 |
| >1.5      |  482 |      51.2 |       2.29 |      50.2 |       5.46 |       54.1 |        6.61 |

### silver · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1146 |      60.2 |       2.13 |      68.7 |       5.98 |       63.4 |        7.32 |
| 15-50  | 2009 |      53   |       1.41 |      51.8 |       2.61 |       62.6 |        6.09 |
| 50-85  | 2040 |      51.2 |       1.12 |      57   |       4.82 |       57   |       10.91 |
| 85-100 | 1125 |      52   |       0.58 |      57.6 |       2.77 |       59   |        8.66 |

### silver · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1562 |      56.9 |       2.09 |      62.4 |       4.7  |       67.4 |       10    |
| Stagflation     | 1606 |      53.9 |       1.5  |      54.7 |       3.93 |       53.9 |        7.68 |
| Goldilocks      | 1552 |      49.2 |       0.29 |      53.2 |       1.07 |       54   |        5.14 |
| Deflation-scare | 1712 |      53.3 |       1.1  |      57.2 |       5.43 |       62.6 |        9.54 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    1.3 |          2   |            0.7 |        10.8 |     0.16 |          0.48 |      0.11 |           0.59 |   -50.5 |        -75.8 |             28.4 |               8.6 |            0.1  |
| moderate     |    1.6 |          2.4 |            0.8 |        10.8 |     0.18 |          0.48 |      0.15 |           0.59 |   -59.4 |        -75.8 |             47.3 |               9.9 |            0.11 |
| aggressive   |    2.5 |          3.3 |            0.8 |        10.8 |     0.22 |          0.48 |      0.21 |           0.59 |   -73   |        -75.8 |             58.8 |              10   |            0.13 |
| optimal      |    1.4 |          2.3 |            0.8 |        10.8 |     0.17 |          0.48 |      0.15 |           0.59 |   -61.7 |        -75.8 |             51   |              10   |            0.1  |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0934**; observed SR 0.17 ann vs haircut SR0 0.44 ann (N=40 trials, T=6432d, skew=-2.742, kurt=74.543).

## COPPER — 2001-01-02..2026-08-07 (6435 days)

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
| -0.5..0 | 1085 |      56.1 |       1.45 |      61.3 |       3.46 |       57.8 |        5.08 |
| 0..0.5  | 1190 |      57.3 |       1.67 |      57.1 |       3.97 |       55.6 |        6.1  |
| >0.5    | 2453 |      54   |       1.19 |      58.4 |       3.86 |       60.2 |        8.59 |

### copper · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1597 |      59   |       1.14 |      63.1 |       4.45 |       58.6 |        8.44 |
| down        | 1030 |      45.4 |      -0.38 |      42.7 |      -1.13 |       39.1 |       -0.48 |
| up          |  764 |      51   |       0.07 |      55.7 |      -0.37 |       65.6 |        2.55 |
| strong-up   | 2876 |      59.6 |       1.81 |      64.4 |       5.45 |       66.1 |        9.9  |

### copper · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1893 |      54   |      -0.09 |      55.2 |       1.43 |       59.4 |        4.48 |
| neutral      | 1928 |      55.4 |       1.06 |      58.1 |       2.29 |       54.1 |        3.21 |
| constructive | 2614 |      55.4 |       1.65 |      60   |       4.87 |       61.2 |       10.22 |

### copper · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1343 |      53.3 |       0.05 |      57.7 |       1.02 |       63.1 |        5.32 |
| neutral  | 2819 |      53.7 |       1.15 |      53.4 |       2.26 |       53.4 |        4.2  |
| tailwind | 2273 |      57.6 |       1.26 |      63.9 |       5.31 |       62.2 |        9.83 |

### copper · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +4.8% 56.9%hit (n=364) [flat]; high >1.5: +6.2% 51.4%hit (n=285) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  364 |      58.5 |       0.21 |      60.7 |       2.08 |       56.9 |        4.82 |
| -1.5..-.5 |  932 |      53.8 |      -0.07 |      52.8 |       0.88 |       50.8 |        2.34 |
| -.5..5    | 2031 |      58.9 |       1.42 |      57.6 |       2.57 |       56.3 |        4.44 |
| .5..1.5   |  993 |      45.5 |      -0.18 |      49.5 |       0.56 |       48   |        2.75 |
| >1.5      |  285 |      47   |      -1.13 |      54.9 |       1.96 |       51.4 |        6.25 |

### copper · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1276 |      58.9 |       1.91 |      62   |       6.34 |       60.7 |       11.89 |
| 15-50  | 1886 |      52   |       0.26 |      58.2 |       2.41 |       56.8 |        6.27 |
| 50-85  | 1747 |      55.5 |       1.1  |      53.7 |       0.83 |       57.4 |        2.07 |
| 85-100 | 1414 |      57.8 |       1.18 |      64.2 |       4.81 |       65.1 |        8.98 |

### copper · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.5 |       1.97 |      63.2 |       5.36 |       59.8 |        6.64 |
| Stagflation     | 1608 |      50.6 |       0.77 |      55.4 |       3.98 |       62.1 |        6.73 |
| Goldilocks      | 1553 |      50.6 |       0.09 |      49.9 |      -0.24 |       47.4 |        4.43 |
| Deflation-scare | 1713 |      57.2 |       1    |      62.9 |       3.04 |       63.7 |        7.69 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    4.5 |          5.2 |            0.7 |         8.5 |     0.42 |          0.44 |      0.33 |            0.6 |   -40.4 |        -69.4 |             30.9 |               8.2 |            0.38 |
| moderate     |    4   |          4.8 |            0.9 |         8.5 |     0.32 |          0.44 |      0.31 |            0.6 |   -59.9 |        -69.4 |             52.6 |              10.3 |            0.34 |
| aggressive   |    3.9 |          4.8 |            0.9 |         8.5 |     0.3  |          0.44 |      0.32 |            0.6 |   -61.8 |        -69.4 |             63.7 |              10.5 |            0.33 |
| optimal      |    4.3 |          5.1 |            0.8 |         8.5 |     0.34 |          0.44 |      0.34 |            0.6 |   -57   |        -69.4 |             55.6 |               9.8 |            0.37 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.3076**; observed SR 0.34 ann vs haircut SR0 0.44 ann (N=40 trials, T=6435d, skew=-1.27, kurt=47.768).

## OIL — 2001-01-02..2026-08-07 (6434 days)

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
| <-0.5   | 1732 |      52.7 |      -0.08 |      57.2 |       4.09 |       60.9 |        7.57 |
| -0.5..0 | 1105 |      57   |       1.77 |      63.9 |       5.23 |       59   |        6.92 |
| 0..0.5  | 1148 |      58.1 |       1.68 |      54.3 |       3.09 |       59.5 |        6.86 |
| >0.5    | 2449 |      52.7 |       0.97 |      56.1 |       1.57 |       54.4 |        3.59 |

### oil · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1926 |      55.9 |       1.73 |      63.9 |       8.84 |       66.6 |       13.44 |
| down        |  755 |      55.5 |       1.08 |      56.7 |       2.06 |       62.2 |        6.62 |
| up          |  767 |      56.2 |       1.04 |      59.4 |       1.86 |       58.8 |        5.4  |
| strong-up   | 2823 |      53.1 |       0.48 |      54.9 |       0.48 |       53.4 |        1.82 |

### oil · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1936 |      53.5 |       0.14 |      57.5 |       4.11 |       62.8 |        7.85 |
| neutral      | 1836 |      59.3 |       2.01 |      62.3 |       5.25 |       57.9 |        7.14 |
| constructive | 2662 |      51.6 |       0.82 |      53.9 |       1.02 |       54.2 |        3.44 |

### oil · bw_change — forward returns by band (full)

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     | 1211 |      46.7 |      -2.13 |      53   |      -1.88 |       46   |       -2.03 |
| -1.5..-.3 |  913 |      49   |      -0.33 |      49.3 |       1.53 |       45.3 |        0.58 |
| -.3..3    |  526 |      56.5 |       1.17 |      61.6 |       4.93 |       57.3 |        7.04 |
| .3..1.5   |  842 |      59.2 |       2.52 |      56.2 |       4.55 |       57.4 |        6.62 |
| >1.5      | 1241 |      55.5 |       2.47 |      55.6 |       4.19 |       59.2 |        8.46 |

### oil · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 2021 |      44.8 |      -1.65 |      47.9 |      -0.87 |       45.6 |       -0.34 |
| neutral  | 1907 |      60.2 |       2.38 |      61.8 |       4.85 |       59.5 |        7.01 |
| tailwind | 2506 |      57.6 |       1.94 |      61.6 |       5.02 |       66.4 |        9.85 |

### oil · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +12.7% 61.5%hit (n=375) [STRONG]; high >1.5: -4.4% 34.3%hit (n=356) [FADE]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  375 |      44   |      -1.21 |      58.5 |       6.8  |       61.5 |       12.7  |
| -1.5..-.5 | 1048 |      52.9 |       0.12 |      54.4 |       3.14 |       54.1 |        3.49 |
| -.5..5    | 1823 |      53.7 |       0.62 |      54.7 |       1.26 |       55.6 |        5.55 |
| .5..1.5   | 1000 |      51.6 |       1.19 |      49.4 |      -0.22 |       45   |       -1.84 |
| >1.5      |  356 |      54.2 |       1.35 |      50.4 |       1.85 |       34.3 |       -4.43 |

### oil · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  773 |      48.4 |       0.26 |      49.2 |       2.12 |       47.7 |        4.64 |
| 15-50  | 2231 |      54.8 |       0.62 |      60.5 |       4.52 |       62.3 |        6.55 |
| 50-85  | 1938 |      56.7 |       1.46 |      56   |       1.65 |       58.8 |        7.35 |
| 85-100 | 1385 |      54.4 |       1.31 |      61.2 |       4    |       58.3 |        4.58 |

### oil · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.2 |       2.52 |      67.6 |       5.44 |       70.6 |       11.38 |
| Stagflation     | 1606 |      52.7 |       0.74 |      53.9 |       2.87 |       61.5 |        6.63 |
| Goldilocks      | 1554 |      52.3 |       0.3  |      53.5 |       0.72 |       49.1 |        0.93 |
| Deflation-scare | 1713 |      51.5 |       0.3  |      54.7 |       3.42 |       50.3 |        4.2  |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    0.7 |          1.5 |            0.8 |         4.2 |     0.13 |         -0.02 |      0.1  |          -0.02 |   -64.1 |       -125.9 |             34.1 |               9.7 |            0.42 |
| moderate     |    1   |          1.8 |            0.8 |         4.2 |     0.15 |         -0.02 |      0.15 |          -0.02 |   -64.6 |       -125.9 |             52.1 |              10.1 |            0.45 |
| aggressive   |    2.7 |          3.5 |            0.8 |         4.2 |     0.23 |         -0.02 |      0.25 |          -0.02 |   -52.1 |       -125.9 |             62.1 |               9.6 |            0.7  |
| optimal      |    2.1 |          2.9 |            0.8 |         4.2 |     0.2  |         -0.02 |      0.2  |          -0.02 |   -63.5 |       -125.9 |             54.5 |              10   |            0.59 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.1212**; observed SR 0.2 ann vs haircut SR0 0.43 ann (N=40 trials, T=6434d, skew=-0.508, kurt=17.056).

## Trial log

As-of 2026-08-07: **40** declared independent trials per asset (upper-bound); 8 signal families screened across 4 assets; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 8.0bps one-way.