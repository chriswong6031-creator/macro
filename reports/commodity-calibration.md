# Commodity Vector — calibration report

Split-half boundary: 2013-01-01. Forward horizons: [21, 63, 126] days.

House rule: a relationship is trusted (labeled a *signal* in the UI) only if its forward-return rank-trend holds in the expected direction in the full sample AND survives both halves. The Risk Index is judged on forward DRAWDOWN (its real job). **shock_z** (the residual exogenous-bid detector) is judged directionally: CONFIRMED = bids persist (momentum), INVERTED = bids fade (mean-reversion) — both honest. Anything failing is context-only.


## GOLD — 2001-01-02..2026-07-17 (6413 days)

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
| <-0.5   | 1330 |      60.2 |       0.9  |      62.5 |       2.31 |       68.8 |        4.98 |
| -0.5..0 | 1106 |      59.3 |       1.32 |      65.4 |       2.7  |       70.4 |        6.07 |
| 0..0.5  | 1168 |      55.1 |       0.89 |      68.3 |       4.24 |       74.2 |        7.53 |
| >0.5    | 2809 |      56   |       1.01 |      63.5 |       3.2  |       72.3 |        6.99 |

### gold · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down |  474 |      56.1 |       0.7  |      56.8 |       1.45 |       45.4 |        1.13 |
| down        | 1083 |      53.8 |       0.78 |      60.3 |       1.78 |       66.9 |        4.21 |
| up          | 1258 |      54.1 |       0.72 |      59.5 |       2.62 |       71.4 |        5.59 |
| strong-up   | 3430 |      59.5 |       1.25 |      68.2 |       4.02 |       76   |        8.48 |

### gold · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1703 |      59.9 |       1.23 |      62.1 |       2.25 |       69.6 |        5.53 |
| neutral      | 1966 |      54.9 |       0.74 |      67.7 |       3.75 |       71.7 |        6.82 |
| constructive | 2744 |      57.3 |       1.09 |      63.7 |       3.21 |       72.8 |        6.91 |

### gold · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1253 |      53.9 |       0.73 |      56.5 |       2.14 |       71.3 |        5.08 |
| 20-40  |  853 |      51.8 |       0.41 |      55.6 |       2.08 |       61.8 |        5.67 |
| 40-60  |  807 |      59.1 |       1.33 |      65.7 |       3.58 |       65.1 |        4.86 |
| 60-80  |  997 |      55.1 |       0.77 |      67.9 |       3.54 |       79.8 |        8.9  |
| 80-100 | 2399 |      61.4 |       1.41 |      69.4 |       3.72 |       73.4 |        7.16 |

### gold · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1679 |      61.8 |       1.43 |      73.4 |       4.58 |       79.8 |        8.84 |
| neutral  | 2692 |      55.3 |       0.76 |      62.7 |       2.3  |       67.9 |        5.39 |
| tailwind | 2042 |      56.3 |       1.02 |      59.6 |       3.03 |       69.8 |        6.12 |

### gold · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +3.4% 67.9%hit (n=336) [flat]; high >1.5: +7.6% 70.9%hit (n=581) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  336 |      65.6 |       1.87 |      50.2 |       0.66 |       67.9 |        3.36 |
| -1.5..-.5 | 1287 |      57.5 |       0.96 |      66.5 |       3.47 |       69.5 |        6.5  |
| -.5..5    | 2045 |      57.5 |       1.24 |      65.5 |       3.69 |       71   |        6.97 |
| .5..1.5   | 1083 |      54   |       0.83 |      59.8 |       2.89 |       65.7 |        6.32 |
| >1.5      |  581 |      52.8 |       0.32 |      62.8 |       2.53 |       70.9 |        7.6  |

### gold · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  951 |      63.1 |       1.34 |      67.3 |       3    |       69   |        5.22 |
| 15-50  | 1813 |      54.7 |       0.57 |      58.6 |       1.94 |       71.5 |        6.17 |
| 50-85  | 2142 |      56.3 |       1.17 |      66.1 |       3.79 |       70.5 |        6.75 |
| 85-100 | 1395 |      58.5 |       1.21 |      66.9 |       3.84 |       74.1 |        7.64 |

### gold · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      58.4 |       1.11 |      62   |       2.9  |       68.6 |        6.11 |
| Stagflation     | 1605 |      53.3 |       0.98 |      62.4 |       3.3  |       74   |        7.35 |
| Goldilocks      | 1535 |      60.8 |       1.16 |      68.2 |       2.95 |       71   |        6.32 |
| Deflation-scare | 1712 |      56.8 |       0.85 |      65.6 |       3.32 |       72.7 |        6.3  |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    5.5 |          6.3 |            0.7 |        11.2 |     0.65 |          0.68 |      0.51 |           0.91 |   -14.3 |        -44.4 |             35.4 |               8.8 |            0.26 |
| moderate     |    4.8 |          5.7 |            0.9 |        11.2 |     0.48 |          0.68 |      0.47 |           0.91 |   -33.3 |        -44.4 |             58.4 |              10.1 |            0.22 |
| aggressive   |    5.4 |          6.3 |            0.9 |        11.2 |     0.47 |          0.68 |      0.49 |           0.91 |   -32.2 |        -44.4 |             68.2 |              10.1 |            0.26 |
| optimal      |    5.2 |          6   |            0.8 |        11.2 |     0.5  |          0.68 |      0.51 |           0.91 |   -33.7 |        -44.4 |             60.9 |               9.8 |            0.24 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.6229**; observed SR 0.5 ann vs haircut SR0 0.44 ann (N=40 trials, T=6413d, skew=-0.916, kurt=20.577).

## SILVER — 2001-01-02..2026-07-17 (6415 days)

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
| <-0.5   | 1835 |      56.1 |       1.21 |      64.1 |       3.59 |       63.1 |        6.98 |
| -0.5..0 | 1150 |      57.3 |       2.12 |      60.9 |       4.76 |       62   |        6.91 |
| 0..0.5  | 1029 |      53.3 |       1.3  |      56.8 |       4.2  |       59.2 |        9.57 |
| >0.5    | 2401 |      49.5 |       0.86 |      50.1 |       3.67 |       56.4 |        9.33 |

### silver · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1552 |      52.4 |       1.35 |      60.8 |       3.48 |       59.6 |        5.83 |
| down        |  786 |      47.8 |      -0.04 |      52   |       1.16 |       58.4 |        4.75 |
| up          |  791 |      51.3 |       1.22 |      58.5 |       4.82 |       58.2 |        7.72 |
| strong-up   | 3118 |      56.7 |       1.66 |      57.8 |       4.96 |       61.6 |       11.14 |

### silver · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1993 |      56.3 |       1.38 |      63.3 |       3.42 |       65.2 |        6.61 |
| neutral      | 1980 |      54.2 |       1.09 |      59.9 |       3.58 |       55.9 |        7.23 |
| constructive | 2442 |      50.3 |       1.3  |      49.8 |       4.61 |       58.5 |       10.43 |

### silver · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1254 |      51.4 |       0.83 |      48.7 |       1.73 |       49.7 |        2.48 |
| 20-40  |  853 |      47.3 |       0.57 |      51.8 |       2.44 |       53.1 |        7.12 |
| 40-60  |  807 |      57   |       1.63 |      56.1 |       5.19 |       55.4 |        5.08 |
| 60-80  |  997 |      47.6 |       0.45 |      59.1 |       3.67 |       66.4 |       12.23 |
| 80-100 | 2400 |      58.3 |       2.05 |      64.5 |       5.56 |       67.3 |       11.39 |

### silver · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1567 |      54.9 |       1.48 |      61.5 |       4.05 |       69.5 |        9.68 |
| neutral  | 2751 |      50   |       0.68 |      55.9 |       3.15 |       56   |        6.4  |
| tailwind | 2097 |      56.7 |       1.86 |      55.3 |       4.85 |       57.5 |        9.68 |

### silver · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +13.9% 65.4%hit (n=361) [STRONG]; high >1.5: +7.3% 54.8%hit (n=482) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  361 |      63.4 |       2.33 |      65.3 |       5.44 |       65.4 |       13.91 |
| -1.5..-.5 | 1387 |      55.4 |       1.27 |      62.5 |       4.22 |       62.3 |        7.47 |
| -.5..5    | 1965 |      49.6 |       0.91 |      55.9 |       3.2  |       56.1 |        7.2  |
| .5..1.5   | 1138 |      52   |       1.22 |      49.9 |       4.38 |       57.7 |       11.34 |
| >1.5      |  482 |      51.2 |       2.29 |      50.2 |       5.46 |       54.8 |        7.27 |

### silver · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1146 |      60.2 |       2.13 |      68.7 |       5.98 |       63.7 |        7.47 |
| 15-50  | 1992 |      53.2 |       1.44 |      52.3 |       2.84 |       63   |        6.35 |
| 50-85  | 2040 |      51.2 |       1.12 |      57   |       4.82 |       57   |       10.91 |
| 85-100 | 1125 |      52   |       0.58 |      57.6 |       2.77 |       59   |        8.66 |

### silver · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1562 |      56.9 |       2.09 |      62.4 |       4.7  |       67.4 |       10    |
| Stagflation     | 1606 |      53.9 |       1.5  |      54.7 |       3.93 |       54.4 |        8.05 |
| Goldilocks      | 1535 |      49.3 |       0.32 |      53.7 |       1.32 |       54.1 |        5.21 |
| Deflation-scare | 1712 |      53.3 |       1.1  |      57.3 |       5.47 |       62.6 |        9.54 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    1.3 |          2   |            0.7 |        10.4 |     0.16 |          0.47 |      0.11 |           0.57 |   -50.5 |        -75.8 |             28.5 |               8.6 |            0.11 |
| moderate     |    1.6 |          2.4 |            0.8 |        10.4 |     0.18 |          0.47 |      0.15 |           0.57 |   -59.4 |        -75.8 |             47.4 |               9.9 |            0.12 |
| aggressive   |    2.5 |          3.3 |            0.8 |        10.4 |     0.22 |          0.47 |      0.21 |           0.57 |   -73   |        -75.8 |             59   |              10.1 |            0.15 |
| optimal      |    1.4 |          2.3 |            0.8 |        10.4 |     0.18 |          0.47 |      0.15 |           0.57 |   -61.7 |        -75.8 |             51.1 |              10   |            0.12 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0934**; observed SR 0.18 ann vs haircut SR0 0.44 ann (N=40 trials, T=6415d, skew=-2.739, kurt=74.347).

## COPPER — 2001-01-02..2026-07-17 (6418 days)

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
| -0.5..0 | 1085 |      55.6 |       1.41 |      61.3 |       3.46 |       57.8 |        5.08 |
| 0..0.5  | 1189 |      57.3 |       1.66 |      57   |       3.97 |       55.3 |        6.06 |
| >0.5    | 2437 |      54   |       1.19 |      58.1 |       3.86 |       60   |        8.6  |

### copper · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1597 |      59   |       1.14 |      63.1 |       4.45 |       58.6 |        8.44 |
| down        | 1030 |      45.4 |      -0.38 |      42.7 |      -1.13 |       39.1 |       -0.48 |
| up          |  761 |      50.9 |       0.06 |      55.7 |      -0.37 |       65.6 |        2.55 |
| strong-up   | 2862 |      59.5 |       1.8  |      64.2 |       5.45 |       65.9 |        9.9  |

### copper · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1893 |      53.7 |      -0.12 |      55.2 |       1.43 |       59.4 |        4.48 |
| neutral      | 1915 |      55.3 |       1.05 |      58.1 |       2.29 |       54.1 |        3.21 |
| constructive | 2610 |      55.5 |       1.65 |      59.8 |       4.87 |       60.9 |       10.22 |

### copper · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1337 |      53.3 |       0.05 |      57.7 |       1.02 |       63.1 |        5.32 |
| neutral  | 2808 |      53.5 |       1.13 |      53.3 |       2.25 |       53.4 |        4.2  |
| tailwind | 2273 |      57.6 |       1.26 |      63.8 |       5.32 |       61.9 |        9.83 |

### copper · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +4.8% 56.9%hit (n=364) [flat]; high >1.5: +6.2% 51.4%hit (n=285) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  364 |      58.5 |       0.21 |      60.7 |       2.08 |       56.9 |        4.82 |
| -1.5..-.5 |  932 |      53.7 |      -0.08 |      52.8 |       0.88 |       50.4 |        2.28 |
| -.5..5    | 2019 |      58.7 |       1.4  |      57.4 |       2.56 |       56.1 |        4.43 |
| .5..1.5   |  988 |      45.5 |      -0.18 |      49.1 |       0.54 |       47.8 |        2.74 |
| >1.5      |  285 |      47   |      -1.13 |      54.9 |       1.96 |       51.4 |        6.25 |

### copper · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1276 |      58.9 |       1.91 |      62   |       6.34 |       60.7 |       11.89 |
| 15-50  | 1886 |      52   |       0.26 |      58.2 |       2.41 |       56.8 |        6.27 |
| 50-85  | 1747 |      55.5 |       1.1  |      53.7 |       0.83 |       57.1 |        2.01 |
| 85-100 | 1397 |      57.4 |       1.14 |      63.7 |       4.81 |       64.9 |        8.99 |

### copper · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.5 |       1.97 |      63.2 |       5.36 |       59.8 |        6.64 |
| Stagflation     | 1608 |      50.6 |       0.77 |      55.4 |       3.98 |       61.8 |        6.71 |
| Goldilocks      | 1536 |      50.2 |       0.04 |      49.4 |      -0.29 |       47.3 |        4.42 |
| Deflation-scare | 1713 |      57.2 |       1    |      62.9 |       3.04 |       63.7 |        7.69 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    4.6 |          5.3 |            0.7 |         8.3 |     0.42 |          0.43 |      0.33 |            0.6 |   -40.4 |        -69.4 |             30.9 |               8.1 |            0.41 |
| moderate     |    3.9 |          4.8 |            0.9 |         8.3 |     0.32 |          0.43 |      0.3  |            0.6 |   -59.9 |        -69.4 |             52.4 |              10.2 |            0.35 |
| aggressive   |    3.7 |          4.6 |            0.9 |         8.3 |     0.29 |          0.43 |      0.31 |            0.6 |   -61.8 |        -69.4 |             63.6 |              10.5 |            0.33 |
| optimal      |    4.3 |          5.1 |            0.8 |         8.3 |     0.34 |          0.43 |      0.33 |            0.6 |   -57   |        -69.4 |             55.5 |               9.8 |            0.38 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.3013**; observed SR 0.34 ann vs haircut SR0 0.44 ann (N=40 trials, T=6418d, skew=-1.272, kurt=47.887).

## OIL — 2001-01-02..2026-07-17 (6417 days)

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
| <-0.5   | 1730 |      52.2 |      -0.23 |      57.2 |       4.09 |       60.9 |        7.57 |
| -0.5..0 | 1103 |      57   |       1.77 |      63.9 |       5.23 |       59   |        6.92 |
| 0..0.5  | 1144 |      58.1 |       1.68 |      54.8 |       3.26 |       59.5 |        6.83 |
| >0.5    | 2440 |      52.7 |       0.97 |      56.2 |       1.63 |       54.1 |        3.41 |

### oil · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1926 |      55.9 |       1.73 |      63.9 |       8.84 |       66.3 |       13.28 |
| down        |  755 |      55.5 |       1.08 |      56.7 |       2.06 |       62.2 |        6.62 |
| up          |  767 |      55.5 |       0.78 |      59.4 |       1.86 |       58.8 |        5.4  |
| strong-up   | 2806 |      53   |       0.46 |      55.3 |       0.59 |       53.4 |        1.82 |

### oil · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1936 |      53.1 |      -0    |      57.5 |       4.11 |       62.8 |        7.85 |
| neutral      | 1822 |      59.3 |       2.01 |      62.7 |       5.38 |       57.9 |        7.14 |
| constructive | 2659 |      51.6 |       0.82 |      54.1 |       1.06 |       53.9 |        3.26 |

### oil · bw_change — forward returns by band (full)

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     | 1208 |      46.5 |      -2.17 |      53   |      -1.88 |       46   |       -2.03 |
| -1.5..-.3 |  910 |      48.9 |      -0.34 |      49.5 |       1.61 |       45.3 |        0.58 |
| -.3..3    |  522 |      56.3 |       1.09 |      61.6 |       4.93 |       57   |        6.89 |
| .3..1.5   |  836 |      59.2 |       2.52 |      56.5 |       4.65 |       56.7 |        6.23 |
| >1.5      | 1240 |      55.2 |       2.34 |      56.1 |       4.35 |       59.1 |        8.44 |

### oil · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 2005 |      44.3 |      -1.8  |      47.9 |      -0.87 |       45.6 |       -0.34 |
| neutral  | 1906 |      60.2 |       2.38 |      61.9 |       4.88 |       59.5 |        7.01 |
| tailwind | 2506 |      57.6 |       1.94 |      61.9 |       5.15 |       66.2 |        9.7  |

### oil · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +12.7% 61.5%hit (n=375) [STRONG]; high >1.5: -4.4% 34.3%hit (n=354) [FADE]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  375 |      43.9 |      -1.26 |      58.5 |       6.8  |       61.5 |       12.7  |
| -1.5..-.5 | 1048 |      52.2 |      -0.13 |      54.6 |       3.2  |       54   |        3.45 |
| -.5..5    | 1819 |      53.7 |       0.62 |      55   |       1.36 |       55.4 |        5.46 |
| .5..1.5   |  989 |      51.6 |       1.19 |      49.5 |      -0.14 |       44.5 |       -2.16 |
| >1.5      |  354 |      54.2 |       1.35 |      50.4 |       1.85 |       34.3 |       -4.43 |

### oil · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  773 |      48.4 |       0.26 |      50.3 |       2.56 |       47.7 |        4.64 |
| 15-50  | 2219 |      54.6 |       0.54 |      60.5 |       4.52 |       62.3 |        6.55 |
| 50-85  | 1933 |      56.6 |       1.42 |      56   |       1.65 |       58.8 |        7.35 |
| 85-100 | 1385 |      54.4 |       1.31 |      61.2 |       4    |       57.8 |        4.25 |

### oil · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.2 |       2.52 |      67.6 |       5.44 |       70.6 |       11.38 |
| Stagflation     | 1606 |      52.7 |       0.74 |      53.9 |       2.87 |       61.1 |        6.41 |
| Goldilocks      | 1537 |      51.8 |       0.12 |      54.1 |       0.91 |       49.1 |        0.87 |
| Deflation-scare | 1713 |      51.5 |       0.3  |      54.8 |       3.43 |       50.3 |        4.2  |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    0.7 |          1.5 |            0.8 |         4.4 |     0.13 |         -0.02 |      0.1  |          -0.02 |   -64.1 |       -125.9 |             34.1 |               9.7 |            0.4  |
| moderate     |    1.2 |          2   |            0.8 |         4.4 |     0.16 |         -0.02 |      0.15 |          -0.02 |   -64.6 |       -125.9 |             52.2 |              10.1 |            0.45 |
| aggressive   |    3.1 |          3.9 |            0.8 |         4.4 |     0.25 |         -0.02 |      0.26 |          -0.02 |   -52.1 |       -125.9 |             62   |               9.6 |            0.72 |
| optimal      |    2.2 |          3   |            0.8 |         4.4 |     0.21 |         -0.02 |      0.21 |          -0.02 |   -63.5 |       -125.9 |             54.4 |              10   |            0.58 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.1283**; observed SR 0.21 ann vs haircut SR0 0.44 ann (N=40 trials, T=6417d, skew=-0.513, kurt=17.167).

## Trial log

As-of 2026-07-17: **40** declared independent trials per asset (upper-bound); 8 signal families screened across 4 assets; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 8.0bps one-way.