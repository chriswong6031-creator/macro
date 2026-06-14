# Commodity Vector — calibration report

Split-half boundary: 2013-01-01. Forward horizons: [21, 63, 126] days.

House rule: a relationship is trusted (labeled a *signal* in the UI) only if its forward-return rank-trend holds in the expected direction in the full sample AND survives both halves. The Risk Index is judged on forward DRAWDOWN (its real job). **shock_z** (the residual exogenous-bid detector) is judged directionally: CONFIRMED = bids persist (momentum), INVERTED = bids fade (mean-reversion) — both honest. Anything failing is context-only.


## GOLD — 2001-01-02..2026-06-12 (6386 days)

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
| <-0.5   | 1305 |      61.2 |       1.04 |      62.7 |       2.37 |       68.8 |        4.98 |
| -0.5..0 | 1104 |      59.5 |       1.34 |      66.1 |       2.85 |       70.4 |        6.07 |
| 0..0.5  | 1168 |      55.1 |       0.89 |      68.9 |       4.39 |       74.2 |        7.53 |
| >0.5    | 2809 |      56   |       1.01 |      63.5 |       3.2  |       72.9 |        7.13 |

### gold · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down |  474 |      56.1 |       0.7  |      56.8 |       1.45 |       45.4 |        1.13 |
| down        | 1083 |      53.8 |       0.78 |      60.3 |       1.78 |       66.9 |        4.21 |
| up          | 1258 |      54.1 |       0.72 |      59.5 |       2.62 |       71.4 |        5.59 |
| strong-up   | 3403 |      60   |       1.31 |      68.7 |       4.14 |       76.5 |        8.61 |

### gold · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1676 |      60.6 |       1.31 |      63   |       2.46 |       69.6 |        5.53 |
| neutral      | 1966 |      55.1 |       0.77 |      67.8 |       3.78 |       71.6 |        6.83 |
| constructive | 2744 |      57.3 |       1.09 |      63.7 |       3.21 |       73.4 |        7.04 |

### gold · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1229 |      55   |       0.88 |      57.8 |       2.46 |       72.7 |        5.38 |
| 20-40  |  850 |      51.8 |       0.41 |      55.6 |       2.08 |       61.8 |        5.67 |
| 40-60  |  807 |      59.1 |       1.33 |      65.7 |       3.58 |       65.1 |        4.86 |
| 60-80  |  997 |      55.1 |       0.77 |      67.9 |       3.54 |       79.8 |        8.9  |
| 80-100 | 2399 |      61.4 |       1.41 |      69.4 |       3.72 |       73.4 |        7.16 |

### gold · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1652 |      62.1 |       1.46 |      74.2 |       4.76 |       80.1 |        8.93 |
| neutral  | 2692 |      55.5 |       0.79 |      62.9 |       2.35 |       68.3 |        5.49 |
| tailwind | 2042 |      56.5 |       1.06 |      59.6 |       3.03 |       69.8 |        6.12 |

### gold · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +3.4% 67.9%hit (n=334) [flat]; high >1.5: +8.0% 72.3%hit (n=581) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  334 |      65.9 |       1.9  |      52.2 |       1.09 |       67.9 |        3.36 |
| -1.5..-.5 | 1266 |      58.3 |       1.04 |      66.9 |       3.58 |       69.5 |        6.5  |
| -.5..5    | 2041 |      57.7 |       1.28 |      65.7 |       3.72 |       71   |        6.99 |
| .5..1.5   | 1083 |      54   |       0.83 |      59.9 |       2.93 |       66.3 |        6.45 |
| >1.5      |  581 |      52.8 |       0.32 |      62.8 |       2.53 |       72.3 |        7.98 |

### gold · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  958 |      63.2 |       1.43 |      68.8 |       3.19 |       69.1 |        5.3  |
| 15-50  | 1802 |      56.2 |       0.67 |      59.1 |       2.1  |       71.7 |        6.28 |
| 50-85  | 2141 |      55.5 |       1.14 |      66.7 |       3.88 |       71.2 |        6.9  |
| 85-100 | 1378 |      58.7 |       1.18 |      65.6 |       3.65 |       73.9 |        7.52 |

### gold · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      58.4 |       1.11 |      62   |       2.9  |       68.8 |        6.17 |
| Stagflation     | 1605 |      53.3 |       0.98 |      62.4 |       3.3  |       74   |        7.35 |
| Goldilocks      | 1508 |      61.9 |       1.29 |      68.2 |       2.95 |       71.2 |        6.38 |
| Deflation-scare | 1712 |      56.8 |       0.85 |      66.6 |       3.56 |       73.3 |        6.42 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    5.2 |          6   |            0.8 |        11.4 |     0.61 |           0.7 |      0.48 |           0.92 |   -14.8 |        -44.4 |             35.1 |               8.9 |            0.23 |
| moderate     |    5   |          5.8 |            0.9 |        11.4 |     0.49 |           0.7 |      0.48 |           0.92 |   -33.2 |        -44.4 |             58.7 |              10.1 |            0.22 |
| aggressive   |    5.8 |          6.7 |            0.8 |        11.4 |     0.49 |           0.7 |      0.53 |           0.92 |   -32.2 |        -44.4 |             68.6 |               9.9 |            0.27 |
| optimal      |    4.9 |          5.8 |            0.8 |        11.4 |     0.48 |           0.7 |      0.49 |           0.92 |   -33.6 |        -44.4 |             61.3 |               9.8 |            0.22 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.5771**; observed SR 0.48 ann vs haircut SR0 0.44 ann (N=40 trials, T=6386d, skew=-0.895, kurt=20.643).

## SILVER — 2001-01-02..2026-06-12 (6388 days)

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| momentum | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| ts_momentum | **DIRECTIONAL (one half weak)** | 1 | -1 | 1 | 1 |
| structure | **INVERTED** | -1 | -1 | 1 | 1 |
| gsr_pctile | **CONFIRMED** | 1 | 1 | 1 | 1 |
| driver_score | **CONTEXT-ONLY** | 0 | -1 | 0 | 1 |
| shock_z | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| pos_pctile | **CONTEXT-ONLY** | 0 | -1 | 1 | -1 |
| risk_index (drawdown) | **CONFIRMED near-term risk gauge** | -1 | -1 | -1 | -1 |

### silver · momentum — forward returns by band (full)

| band    |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:--------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-0.5   | 1809 |      56.4 |       1.29 |      64.3 |       3.65 |       63.1 |        6.98 |
| -0.5..0 | 1149 |      57.8 |       2.31 |      61.6 |       4.96 |       62   |        6.91 |
| 0..0.5  | 1029 |      53.5 |       1.34 |      57.2 |       4.38 |       59.2 |        9.57 |
| >0.5    | 2401 |      49.6 |       0.88 |      50.1 |       3.7  |       56.8 |        9.62 |

### silver · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1552 |      52.4 |       1.35 |      60.8 |       3.48 |       59.6 |        5.83 |
| down        |  786 |      47.8 |      -0.04 |      52   |       1.16 |       58.4 |        4.75 |
| up          |  791 |      51.3 |       1.22 |      58.5 |       4.82 |       58.2 |        7.72 |
| strong-up   | 3091 |      57.2 |       1.8  |      58.4 |       5.15 |       62   |       11.39 |

### silver · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1966 |      56.5 |       1.45 |      64   |       3.6  |       65.2 |        6.61 |
| neutral      | 1980 |      54.7 |       1.22 |      60.1 |       3.69 |       55.9 |        7.23 |
| constructive | 2442 |      50.4 |       1.31 |      49.8 |       4.61 |       58.9 |       10.72 |

### silver · gsr_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-20   | 1230 |      52.5 |       1.17 |      49.8 |       2.16 |       50.4 |        2.93 |
| 20-40  |  850 |      47.3 |       0.57 |      51.8 |       2.44 |       53.1 |        7.12 |
| 40-60  |  807 |      57   |       1.63 |      56.1 |       5.19 |       55.4 |        5.08 |
| 60-80  |  997 |      47.6 |       0.45 |      59.1 |       3.67 |       66.4 |       12.23 |
| 80-100 | 2400 |      58.3 |       2.05 |      64.5 |       5.56 |       67.3 |       11.39 |

### silver · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1541 |      55.3 |       1.58 |      62.3 |       4.34 |       69.5 |        9.68 |
| neutral  | 2754 |      50.2 |       0.72 |      56.1 |       3.2  |       56.3 |        6.59 |
| tailwind | 2093 |      56.9 |       1.93 |      55.3 |       4.85 |       57.6 |        9.72 |

### silver · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +13.9% 65.4%hit (n=361) [STRONG]; high >1.5: +8.7% 56.8%hit (n=482) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  361 |      63.6 |       2.36 |      65.3 |       5.44 |       65.4 |       13.91 |
| -1.5..-.5 | 1364 |      55.8 |       1.35 |      63.2 |       4.43 |       62.3 |        7.47 |
| -.5..5    | 1961 |      50.1 |       1.06 |      56.1 |       3.3  |       56.1 |        7.2  |
| .5..1.5   | 1138 |      52   |       1.22 |      50   |       4.46 |       57.7 |       11.34 |
| >1.5      |  482 |      51.2 |       2.29 |      50.2 |       5.46 |       56.8 |        8.67 |

### silver · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1152 |      59.8 |       1.93 |      68.8 |       5.92 |       64.1 |        7.74 |
| 15-50  | 1958 |      54.9 |       1.94 |      54.6 |       3.39 |       64.1 |        6.77 |
| 50-85  | 2066 |      51.3 |       1.01 |      56.1 |       4.6  |       57   |       10.97 |
| 85-100 | 1105 |      50.6 |       0.48 |      56.5 |       2.75 |       58.1 |        8.11 |

### silver · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1562 |      56.9 |       2.09 |      62.4 |       4.7  |       67.6 |       10.12 |
| Stagflation     | 1606 |      53.9 |       1.5  |      54.7 |       3.93 |       54.4 |        8.05 |
| Goldilocks      | 1508 |      50.2 |       0.59 |      53.7 |       1.32 |       54.2 |        5.33 |
| Deflation-scare | 1712 |      53.3 |       1.1  |      58.2 |       5.83 |       62.9 |        9.72 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    0.8 |          1.5 |            0.7 |        11.2 |     0.13 |          0.49 |      0.08 |            0.6 |   -49.4 |        -75.8 |             28.1 |               8.5 |            0.08 |
| moderate     |    1.4 |          2.2 |            0.8 |        11.2 |     0.17 |          0.49 |      0.14 |            0.6 |   -62   |        -75.8 |             47.8 |              10   |            0.1  |
| aggressive   |    2.8 |          3.6 |            0.8 |        11.2 |     0.24 |          0.49 |      0.22 |            0.6 |   -71.9 |        -75.8 |             59.3 |              10.1 |            0.13 |
| optimal      |    0.6 |          1.5 |            0.8 |        11.2 |     0.14 |          0.49 |      0.11 |            0.6 |   -66.2 |        -75.8 |             51.3 |              10.1 |            0.08 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0651**; observed SR 0.14 ann vs haircut SR0 0.44 ann (N=40 trials, T=6388d, skew=-2.778, kurt=75.231).

## COPPER — 2001-01-02..2026-06-12 (6391 days)

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| momentum | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| ts_momentum | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| structure | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| driver_score | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| shock_z | **CONTEXT-ONLY** | 0 | 1 | 0 | 1 |
| pos_pctile | **CONTEXT-ONLY** | 0 | -1 | 1 | -1 |
| risk_index (drawdown) | **DIRECTIONAL** | -1 | -1 | 1 | -1 |

### copper · momentum — forward returns by band (full)

| band    |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:--------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-0.5   | 1707 |      54.1 |      -0.17 |      56   |       1.08 |       58.7 |        4.45 |
| -0.5..0 | 1073 |      55.6 |       1.41 |      61.1 |       3.39 |       57.8 |        5.08 |
| 0..0.5  | 1178 |      57.6 |       1.68 |      56.8 |       3.94 |       55.3 |        6.06 |
| >0.5    | 2433 |      54.3 |       1.22 |      58   |       3.86 |       59.6 |        8.57 |

### copper · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1597 |      59   |       1.14 |      63.1 |       4.45 |       58.6 |        8.44 |
| down        | 1030 |      45.4 |      -0.38 |      42.7 |      -1.13 |       39.1 |       -0.48 |
| up          |  760 |      50.9 |       0.06 |      55.2 |      -0.53 |       65.6 |        2.55 |
| strong-up   | 2836 |      59.8 |       1.84 |      64   |       5.44 |       65.5 |        9.89 |

### copper · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1882 |      53.7 |      -0.12 |      54.8 |       1.32 |       59.4 |        4.48 |
| neutral      | 1907 |      55.3 |       1.05 |      57.9 |       2.28 |       54.1 |        3.21 |
| constructive | 2602 |      55.8 |       1.69 |      59.7 |       4.87 |       60.5 |       10.22 |

### copper · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1339 |      53.3 |       0.05 |      57.5 |       0.98 |       63.1 |        5.32 |
| neutral  | 2780 |      53.7 |       1.15 |      52.9 |       2.2  |       53.4 |        4.2  |
| tailwind | 2272 |      57.8 |       1.28 |      63.8 |       5.32 |       61.4 |        9.82 |

### copper · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +4.8% 56.9%hit (n=364) [flat]; high >1.5: +6.2% 51.4%hit (n=285) [flat]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  364 |      58.5 |       0.21 |      60.7 |       2.08 |       56.9 |        4.82 |
| -1.5..-.5 |  931 |      53.7 |      -0.08 |      52.8 |       0.87 |       50.4 |        2.28 |
| -.5..5    | 1992 |      58.9 |       1.41 |      56.9 |       2.47 |       55.9 |        4.38 |
| .5..1.5   |  989 |      45.9 |      -0.15 |      48.8 |       0.51 |       46.7 |        2.61 |
| >1.5      |  285 |      47.2 |      -1.11 |      54.9 |       1.96 |       51.4 |        6.25 |

### copper · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   | 1284 |      58   |       1.67 |      62.4 |       6.11 |       61.1 |       11.72 |
| 15-50  | 1879 |      53.1 |       0.43 |      58   |       2.52 |       56.5 |        6.4  |
| 50-85  | 1754 |      55.5 |       1.17 |      54.1 |       1.05 |       57.2 |        2.07 |
| 85-100 | 1367 |      57.5 |       1.07 |      62.4 |       4.46 |       64.2 |        8.84 |

### copper · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.5 |       1.97 |      63.2 |       5.36 |       59.7 |        6.65 |
| Stagflation     | 1608 |      50.6 |       0.77 |      55.4 |       3.98 |       61.8 |        6.71 |
| Goldilocks      | 1509 |      50.7 |       0.07 |      49.4 |      -0.29 |       47.2 |        4.41 |
| Deflation-scare | 1713 |      57.2 |       1    |      62.3 |       2.94 |       63.3 |        7.63 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    4.3 |          5   |            0.7 |         8.4 |     0.41 |          0.43 |      0.32 |            0.6 |   -39.8 |        -69.4 |             30.9 |               8.1 |            0.37 |
| moderate     |    3.9 |          4.7 |            0.8 |         8.4 |     0.32 |          0.43 |      0.31 |            0.6 |   -60.2 |        -69.4 |             52.5 |              10.1 |            0.34 |
| aggressive   |    4.2 |          5   |            0.9 |         8.4 |     0.31 |          0.43 |      0.34 |            0.6 |   -61.7 |        -69.4 |             63.7 |              10.4 |            0.36 |
| optimal      |    4.5 |          5.3 |            0.8 |         8.4 |     0.35 |          0.43 |      0.35 |            0.6 |   -56.6 |        -69.4 |             55.5 |               9.7 |            0.39 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.323**; observed SR 0.35 ann vs haircut SR0 0.44 ann (N=40 trials, T=6391d, skew=-1.272, kurt=47.995).

## OIL — 2001-01-02..2026-06-12 (6390 days)

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
| <-0.5   | 1708 |      52.2 |      -0.23 |      57.2 |       4.09 |       60.4 |        7.35 |
| -0.5..0 | 1102 |      57.6 |       2.04 |      63.9 |       5.24 |       58.9 |        6.89 |
| 0..0.5  | 1140 |      58.2 |       1.72 |      55.1 |       3.36 |       59.2 |        6.7  |
| >0.5    | 2440 |      52.8 |       1.03 |      56.7 |       1.85 |       54.1 |        3.41 |

### oil · ts_momentum — forward returns by band (full)

| band        |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| strong-down | 1926 |      55.9 |       1.73 |      63.9 |       8.84 |       65.8 |       13.08 |
| down        |  755 |      55.5 |       1.08 |      56.7 |       2.06 |       62.2 |        6.62 |
| up          |  752 |      55.3 |       0.77 |      59.4 |       1.86 |       58.8 |        5.4  |
| strong-up   | 2794 |      53.4 |       0.64 |      55.8 |       0.82 |       53.4 |        1.82 |

### oil · structure — forward returns by band (full)

| band         |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| broken       | 1910 |      53   |      -0.01 |      57.5 |       4.11 |       62.4 |        7.66 |
| neutral      | 1821 |      60.1 |       2.3  |      62.8 |       5.42 |       57.8 |        7.09 |
| constructive | 2659 |      51.6 |       0.82 |      54.5 |       1.29 |       53.9 |        3.21 |

### oil · bw_change — forward returns by band (full)

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     | 1194 |      46.9 |      -1.97 |      53.3 |      -1.67 |       46   |       -2.03 |
| -1.5..-.3 |  908 |      49.1 |      -0.25 |      49.6 |       1.66 |       44.9 |        0.36 |
| -.3..3    |  519 |      56.4 |       1.14 |      61.7 |       4.98 |       56.2 |        6.51 |
| .3..1.5   |  836 |      59.4 |       2.61 |      56.5 |       4.67 |       56.1 |        5.95 |
| >1.5      | 1232 |      55.2 |       2.36 |      56.8 |       4.64 |       59.1 |        8.44 |

### oil · driver_score — forward returns by band (full)

| band     |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:---------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| headwind | 1980 |      44.3 |      -1.8  |      48.1 |      -0.75 |       45.6 |       -0.34 |
| neutral  | 1905 |      60.4 |       2.43 |      62.5 |       5.12 |       59.5 |        7.01 |
| tailwind | 2505 |      58   |       2.11 |      61.9 |       5.16 |       65.8 |        9.5  |

### oil · shock_z — forward returns by band (full)  
_EXTREMES — low <-1.5: +12.7% 61.5%hit (n=371) [STRONG]; high >1.5: -4.4% 34.3%hit (n=354) [FADE]_

| band      |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| <-1.5     |  371 |      43.7 |      -1.28 |      58.5 |       6.8  |       61.5 |       12.7  |
| -1.5..-.5 | 1030 |      52.5 |       0.02 |      54.8 |       3.26 |       53.2 |        2.99 |
| -.5..5    | 1814 |      54   |       0.75 |      55.1 |       1.42 |       55.3 |        5.42 |
| .5..1.5   |  989 |      51.7 |       1.27 |      49.6 |      -0.08 |       44.2 |       -2.32 |
| >1.5      |  354 |      54.4 |       1.44 |      52.8 |       3.13 |       34.3 |       -4.43 |

### oil · pos_pctile — forward returns by band (full)

| band   |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:-------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| 0-15   |  778 |      47.3 |       0.4  |      51.4 |       2.91 |       47.2 |        4.53 |
| 15-50  | 2204 |      56   |       0.85 |      60.5 |       4.64 |       62.5 |        6.37 |
| 50-85  | 1895 |      56   |       1.23 |      55.6 |       1.44 |       58.6 |        7.15 |
| 85-100 | 1410 |      54.3 |       1.34 |      62.1 |       4.41 |       57.4 |        4.59 |

### oil · forward returns by complex regime

| band            |    n |   hit_21d |   mean_21d |   hit_63d |   mean_63d |   hit_126d |   mean_126d |
|:----------------|-----:|----------:|-----------:|----------:|-----------:|-----------:|------------:|
| Reflation       | 1561 |      61.2 |       2.52 |      67.6 |       5.44 |       70.5 |       11.35 |
| Stagflation     | 1606 |      52.7 |       0.74 |      53.9 |       2.87 |       61.1 |        6.41 |
| Goldilocks      | 1510 |      52.5 |       0.44 |      54.1 |       0.91 |       48.9 |        0.79 |
| Deflation-scare | 1713 |      51.5 |       0.3  |      55.6 |       3.85 |       49.8 |        3.94 |
| Neutral         |    0 |     nan   |     nan    |     nan   |     nan    |      nan   |      nan    |

### allocation vs buy-and-hold (NET of 8.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hold_cagr |   sharpe |   hold_sharpe |   sortino |   hold_sortino |   maxdd |   hold_maxdd |   time_in_market |   turnover_annual |   final_vs_hold |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |    0.5 |          1.3 |            0.8 |         4.6 |     0.11 |         -0.02 |      0.09 |          -0.02 |   -67.8 |       -125.9 |             33.9 |               9.7 |            0.36 |
| moderate     |    1.1 |          1.9 |            0.8 |         4.6 |     0.16 |         -0.02 |      0.15 |          -0.02 |   -63.3 |       -125.9 |             52.7 |              10.3 |            0.42 |
| aggressive   |    3.2 |          4   |            0.8 |         4.6 |     0.25 |         -0.02 |      0.27 |          -0.02 |   -52.1 |       -125.9 |             62.2 |               9.6 |            0.71 |
| optimal      |    2.1 |          2.9 |            0.8 |         4.6 |     0.2  |         -0.02 |      0.21 |          -0.02 |   -63.6 |       -125.9 |             54.6 |              10.2 |            0.54 |

**Deflated Sharpe (multiple-testing haircut)** — shipped variant `optimal`: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.1225**; observed SR 0.2 ann vs haircut SR0 0.44 ann (N=40 trials, T=6390d, skew=-0.516, kurt=17.23).

## Trial log

As-of 2026-06-12: **40** declared independent trials per asset (upper-bound); 8 signal families screened across 4 assets; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 8.0bps one-way.