# Bitcoin Vector — calibration report

Span: 2015-01-01..2026-07-01 (4200 days). Split-half boundary: 2021-01-01.

House rule: a signal is trusted (labeled a *signal* in the UI) only if its forward outcome relationship trends in the expected direction in the full sample AND survives both halves (rank-trend |rho|>0.6, tolerant of one small-sample band). Return-predicting signals (momentum, structure, BFI) are judged on forward RETURN; the Risk Index is judged on forward DRAWDOWN (its actual job) because at long horizons extreme risk marks capitulation and forward *return* is U-shaped — the documented contrarian behavior, not a defect. Anything failing is context-only; anything inverted is flagged.

## Signal verdicts

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| risk_index | **CONFIRMED** | -1 | -1 | -1 | -1 |
| momentum | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| structure | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| risk_oscillator | **CONTEXT-ONLY** | 0 | 0 | -1 | -1 |
| bfi | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| mvrv_z | **EXTREMES — low <0: +40.5%/90d 71.9% hit (n=356) [BOTTOM]; high >3.5: +27.1%/90d 57.8% hit (n=277) [weak]** | 0 | 0 | 0 | -1 |
| nupl | **EXTREMES — low <0: +28.0%/90d 66.5% hit (n=603) [BOTTOM]; high >.65: +25.8%/90d 58.5% hit (n=265) [weak]** | 0 | 0 | -1 | -1 |
| mayer | **EXTREMES — low <0.8: +11.4%/90d 48.5% hit (n=633) [weak]; high >2.4: -13.9%/90d 33.9% hit (n=62) [TOP]** | 1 | 1 | 0 | -1 |
| puell | **EXTREMES — low <0.5: +15.8%/90d 59.5% hit (n=153) [weak]** | 1 | 1 | 0 | -1 |
| sth_cb_ratio | **EXTREMES — low <-10%: -1.1%/90d 33.1% hit (n=320) [weak]** | 0 | 0 | 0 | 1 |
| hash_ribbon_capit | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| dvol | **EXTREMES — low <40: +8.4%/90d 46.8% hit (n=224) [weak]; high >90: +15.8%/90d 71.4% hit (n=168) [weak]** | 0 | 0 | 0 | -1 |
| vrp | **EXTREMES — low <-5: +17.2%/90d 77.8% hit (n=203) [weak]; high >15: +7.2%/90d 53.9% hit (n=484) [TOP]** | -1 | 0 | -1 | -1 |
| leverage_stress | **EXTREMES — low 0-25: +12.3%/90d 61.1% hit (n=639) [weak]** | 0 | 0 | 0 | -1 |
| funding_z | **EXTREMES — low <-1: +17.4%/90d 67.7% hit (n=152) [weak]** | 0 | 0 | 0 | -1 |
| oi_price_divergence | **EXTREMES — low <-10%: +14.8%/90d 70.4% hit (n=159) [weak]** | -1 | 0 | -1 | -1 |
| net_liq_roc | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| macro_score | **CONFIRMED** | 1 | 1 | 1 | 1 |
| coinbase_premium_ema | **EXTREMES — low <-.3: +34.5%/90d 57.1% hit (n=184) [BOTTOM]** | -1 | 0 | 0 | 1 |
| ssr_oscillator | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| mpi | **INVERTED** | 1 | 0 | 1 | -1 |
| etf_flow_z | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| reserve_risk | **EXTREMES — low <.0015: +18.0%/90d 67.2% hit (n=979) [weak]; high >.02: -42.5%/90d 4.2% hit (n=48) [TOP]** | 1 | 0 | -1 | -1 |
| impulse | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| cycle_pct | **DIRECTIONAL (one half weak)** | -1 | -1 | 0 | -1 |
| cot_z | **EXTREMES — low <-1.5: +13.2%/90d 47.8% hit (n=224) [weak]; high >1.5: -5.9%/90d 34.1% hit (n=611) [TOP]** | -1 | 0 | -1 | -1 |
| corr_spx | **CONFIRMED** | -1 | -1 | -1 | -1 |
| vdd_multiple | **EXTREMES — low <.5: +7.5%/90d 42.5% hit (n=779) [weak]; high >2.9: +35.2%/90d 59.1% hit (n=154) [weak]** | 1 | 1 | 0 | -1 |
| global_m2_yoy | **DIRECTIONAL (full only)** | 1 | 0 | -1 | 1 |
| rv_cone_pctile | **EXTREMES — low 0-25: +24.8%/90d 70.6% hit (n=1206) [weak]; high 75-100: +30.1%/90d 63.8% hit (n=831) [weak]** | 0 | 0 | 0 | -1 |
| vov_pctile | **EXTREMES — low 0-25: +12.5%/90d 53.0% hit (n=1160) [weak]; high 75-100: +36.6%/90d 73.8% hit (n=826) [weak]** | 1 | 1 | 0 | -1 |
| stbl_growth_z | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |

## Risk Index as a drawdown gauge

**CONFIRMED near-term risk gauge (7d drawdown)** — rank-trend {'full': -1, 'pre': -1, 'post': -1, 'want': -1, 'horizon': 7}.

| band   |    n |   avgDD_7d |   p05DD_7d |   avgDD_30d |   p05DD_30d |   avgDD_90d |   p05DD_90d |
|:-------|-----:|-----------:|-----------:|------------:|------------:|------------:|------------:|
| 0-25   | 2125 |      -2.97 |     -13.97 |       -8.25 |      -26.04 |      -14.11 |      -46.54 |
| 25-50  | 1285 |      -4.17 |     -16.58 |      -10.07 |      -30.84 |      -17.72 |      -50.39 |
| 50-75  |  692 |      -4.64 |     -20.78 |       -9.83 |      -37.07 |      -14.72 |      -41.92 |
| 75-100 |   98 |      -4.4  |     -16.25 |       -9.04 |      -27.8  |      -12.49 |      -32.79 |

### risk_index — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 2125 |     56.1 |      1.93 |      56.6 |       7.64 |      66   |      28.14 |
| 25-50  | 1285 |     52.7 |      0.64 |      57.3 |       5.21 |      52.8 |      17.61 |
| 50-75  |  692 |     53.8 |      0.7  |      58.9 |       4.6  |      55.9 |      13.96 |
| 75-100 |   98 |     49   |      1.89 |      56.7 |       4.16 |      58.8 |      15.46 |

### momentum — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-0.5   | 1042 |     52.7 |      0.17 |      56.8 |       1.99 |      51.5 |       6.63 |
| -0.5..0 |  675 |     51.4 |      0.69 |      56.6 |       3.92 |      57.7 |      19.03 |
| 0..0.5  |  785 |     51.6 |      0.68 |      53.6 |       5.56 |      55   |      23.4  |
| >0.5    | 1698 |     58.3 |      2.6  |      59.2 |      10.22 |      68.5 |      32.35 |

### structure — forward returns by band (full sample)

| band         |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| broken       | 1158 |     52.5 |      0.42 |      59.8 |       3.27 |      57.3 |      12.2  |
| neutral      | 1236 |     53.6 |      0.93 |      55.6 |       6.16 |      56.7 |      22.46 |
| constructive | 1806 |     56.5 |      2.19 |      56.6 |       8.34 |      64.2 |      28.58 |

### risk_oscillator — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| falling | 1664 |     55.4 |      1.9  |      58.6 |       6.19 |      58.7 |      22.34 |
| neutral | 1265 |     54.9 |      1.34 |      58   |       6.99 |      63.1 |      24.44 |
| rising  | 1271 |     53.1 |      0.59 |      54.5 |       5.82 |      59   |      20.08 |

### bfi — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <40    | 1585 |     50.6 |      0.48 |      52.4 |       3.53 |      49.8 |      13.49 |
| 40-60  | 1063 |     55   |      0.72 |      57.6 |       6.96 |      62.9 |      23.1  |
| >60    | 1477 |     58.4 |      2.75 |      62.1 |       9.04 |      69.9 |      32.19 |

### mvrv_z — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     |  356 |     58.7 |      1.86 |      68   |       9.71 |      71.9 |      40.55 |
| 0-1    | 1213 |     53.2 |      0.93 |      56.2 |       3.84 |      50.2 |       5    |
| 1-2    | 1148 |     52.4 |      0.72 |      55.6 |       3.95 |      67.7 |      23.48 |
| 2-3.5  |  948 |     56.5 |      1.84 |      56.9 |      10.2  |      59.8 |      36.62 |
| >3.5   |  277 |     59.9 |      4.67 |      58.1 |      14.54 |      57.8 |      27.15 |

### nupl — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     |  603 |     56.7 |      1.07 |      63.2 |       6.29 |      66.5 |      28.01 |
| 0-.25  |  635 |     57   |      1.79 |      67.6 |       7.16 |      56.7 |      10.14 |
| .25-.5 | 1670 |     52.9 |      0.73 |      52.9 |       2.59 |      60.6 |      17.04 |
| .5-.65 | 1027 |     53.7 |      1.44 |      54.1 |      10.19 |      58   |      33.38 |
| >.65   |  265 |     57.4 |      4.19 |      58.5 |      13.03 |      58.5 |      25.77 |

### mayer — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.8    |  633 |     54.2 |      0.96 |      61.5 |       4.08 |      48.5 |      11.38 |
| 0.8-1   |  958 |     51   |     -0.05 |      53   |       1.93 |      53.3 |      11.5  |
| 1-1.5   | 1888 |     55.7 |      1.46 |      57.9 |       6.15 |      68.3 |      24.11 |
| 1.5-2.4 |  566 |     58.7 |      3.82 |      60.6 |      18.69 |      62.5 |      53.36 |
| >2.4    |   62 |     43.5 |      2.27 |      43.5 |      -1.92 |      33.9 |     -13.95 |

### puell — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.5   |  153 |     54.9 |      1.22 |      64.7 |       4.09 |      59.5 |      15.76 |
| 0.5-1  | 1699 |     53.7 |      0.61 |      58.6 |       4.17 |      62.1 |      20.99 |
| 1-2    | 1855 |     55.1 |      1.7  |      55.6 |       6.87 |      60.1 |      20.23 |
| 2-4    |  397 |     54.7 |      2.41 |      57.4 |      14.94 |      58.7 |      47.89 |
| >4     |   23 |     56.5 |     10.54 |      34.8 |      -3.22 |      17.4 |     -33.4  |

### sth_cb_ratio — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-10%  | 320 |     52.7 |      0.48 |      58.9 |       1.81 |      33.1 |      -1.15 |
| -10-0% | 343 |     51   |     -0.05 |      56.6 |       2.28 |      74   |      25.59 |
| 0-20%  | 621 |     53.1 |      1.17 |      52.5 |       4.5  |      58.8 |       9.29 |
| 20-50% | 196 |     52   |      0.97 |      55.6 |       3.69 |      68.9 |      13.76 |
| >50%   |   0 |    nan   |    nan    |     nan   |     nan    |     nan   |     nan    |

### hash_ribbon_capit — forward returns by band (full sample)

| band         |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| normal       | 3445 |     55   |      1.57 |      58.3 |       7.19 |      60   |      23.31 |
| capitulation |  755 |     52.3 |      0.25 |      52   |       2.24 |      60.8 |      17.19 |

### dvol — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <40    | 224 |     47.3 |     -0.74 |      40.9 |      -1.08 |      46.8 |       8.4  |
| 40-55  | 654 |     51.5 |      0.91 |      58.9 |       4.49 |      63.4 |      12.31 |
| 55-70  | 479 |     54.1 |      0.47 |      53.9 |       2.88 |      62.6 |      10.65 |
| 70-90  | 401 |     48.9 |      0.01 |      38.4 |      -3.8  |      18.7 |     -12.64 |
| >90    | 168 |     47   |     -0.28 |      47   |       2.06 |      71.4 |      15.84 |

### vrp — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-5    | 203 |     57.6 |      1.05 |      61.6 |       3.81 |      77.8 |      17.23 |
| -5-0   | 170 |     57.6 |      1.64 |      63.7 |       5.58 |      50   |       8.81 |
| 0-5    | 357 |     48.6 |      0.07 |      53.6 |       2.37 |      36.8 |       2.14 |
| 5-15   | 712 |     46.6 |     -0.47 |      45.9 |      -0.59 |      51.6 |       3.85 |
| >15    | 484 |     52.9 |      0.88 |      44.6 |       1.45 |      53.9 |       7.2  |

### leverage_stress — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 639 |     53.5 |      1.28 |      57.9 |       4.23 |      61.1 |      12.32 |
| 25-50  | 690 |     51.2 |      0.23 |      51.9 |       2.19 |      58.9 |      12.24 |
| 50-75  | 129 |     52.7 |      0.65 |      54.3 |       4.42 |      43.6 |       3.18 |
| 75-100 |   8 |     75   |      2.65 |     100   |       6.79 |      62.5 |       2.66 |

### funding_z — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    | 152 |     60.5 |      1.22 |      64.2 |       3.15 |      67.7 |      17.38 |
| -1-0   | 399 |     52.4 |      0.4  |      55.7 |       1.73 |      59.8 |       9.23 |
| 0-1    | 334 |     53.2 |      1.18 |      59.3 |       6.97 |      53.7 |      13.1  |
| 1-2    | 106 |     49   |     -0.43 |      44.1 |       1.45 |      42.2 |       4.49 |
| >2     |  39 |     71.8 |      2.69 |      59   |       3.1  |      79.5 |      24.32 |

### oi_price_divergence — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-10%  | 159 |     58.5 |      1.04 |      58.5 |       0.82 |      70.4 |      14.78 |
| -10-0% | 520 |     52.9 |      1.22 |      59.4 |       4.9  |      63.9 |      13.76 |
| 0-10%  | 630 |     51.8 |      0.55 |      51.5 |       3.35 |      54.4 |       9.94 |
| 10-25% | 151 |     49   |     -0.23 |      53   |       0.81 |      46.2 |       6.76 |
| >25%   |   6 |     16.7 |     -3.5  |       0   |      -5.7  |      33.3 |      -4.16 |

### net_liq_roc — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-2%   | 1251 |     52   |      0.51 |      53.4 |       1.58 |      48.8 |       8.69 |
| -2-0%  |  856 |     53.8 |      1.51 |      56.3 |       7.48 |      62   |      18.27 |
| 0-2%   |  849 |     52   |      1.1  |      56.3 |       5.44 |      61.7 |      22.27 |
| 2-5%   |  713 |     59.7 |      2.11 |      60   |       8.85 |      69.9 |      37.73 |
| >5%    |  508 |     58.5 |      2.23 |      65   |      14.01 |      67.3 |      41.68 |

### macro_score — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.3   | 571 |     52   |     -0.04 |      51.3 |      -0.38 |      42.6 |       3.03 |
| -.3-.1 | 812 |     53.2 |      1.22 |      60.6 |       5.53 |      59.5 |      17.91 |
| -.1-.1 | 952 |     57.5 |      1.89 |      58.5 |       8.11 |      57   |      19.95 |
| .1-.3  | 938 |     54.4 |      1.66 |      58.8 |       7.63 |      62.4 |      18.26 |
| >.3    | 927 |     54.5 |      1.37 |      54.8 |       8.05 |      72.7 |      44.87 |

### coinbase_premium_ema — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.3   |  184 |     52.2 |      1.33 |      60.3 |       4.32 |      57.1 |      34.46 |
| -.3-0  |  962 |     50.4 |      0.14 |      50.9 |       1.86 |      44.5 |       5.54 |
| 0-.5   | 1883 |     52.6 |      0.98 |      52.8 |       4.18 |      56.1 |      13.7  |
| .5-1.5 |   61 |     55.7 |      1.7  |      59   |      13.3  |      93.4 |      85.36 |
| >1.5   |    4 |     25   |     -2.57 |       0   |      -8.47 |       0   |     -28.98 |

### ssr_oscillator — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |  484 |     52.3 |      1.11 |      50.4 |       4.16 |      55.6 |       9.9  |
| -1-.3  |  316 |     52.8 |      0.94 |      70.6 |       8.91 |      73.7 |      17.39 |
| -.3-.5 |  516 |     55.2 |      1.31 |      47.9 |       0.8  |      47.3 |       3.5  |
| .5-1.5 | 1390 |     51.7 |      0.6  |      51.1 |       3.54 |      54.4 |      22.51 |
| >1.5   |  342 |     48.5 |      0.08 |      56.8 |       4.09 |      40.7 |       2.94 |

### mpi — forward returns by band (full sample)

| band    |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.7    | 341 |     48.2 |     -0.04 |      53.4 |       0.46 |      54.6 |       7.48 |
| 0.7-1   | 255 |     55.7 |      0.48 |      56.1 |       3.2  |      67.1 |      15.14 |
| 1-1.5   | 370 |     51.6 |      0.78 |      55.7 |       3.83 |      63.5 |      13.56 |
| 1.5-2.5 | 255 |     58.8 |      1.95 |      64.3 |       8.59 |      69.4 |      19.37 |
| >2.5    | 140 |     52.9 |      1.35 |      46.4 |       2.13 |      60   |      11    |

### etf_flow_z — forward returns by band (full sample)

| band      |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:----------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.75     | 213 |     45.7 |     -0.56 |      37.3 |      -3.73 |      41.8 |       0.85 |
| -.75--.25 | 140 |     50   |     -0.04 |      52.6 |       0.06 |      42.1 |       0.35 |
| -.25-.25  | 157 |     47.1 |      0.13 |      56.9 |       2.29 |      44.2 |       3.31 |
| .25-.75   | 101 |     61.4 |      1.49 |      63   |       4.99 |      64   |      11.67 |
| >.75      | 157 |     57.3 |      1.13 |      57.3 |       4.02 |      63.1 |       7.72 |

### reserve_risk — forward returns by band (full sample)

| band        |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <.0015      |  979 |     55.8 |      1.47 |      62.1 |       5.78 |      67.2 |      18.04 |
| .0015-.0025 | 1685 |     56.9 |      1.18 |      63   |       6.11 |      69.8 |      25.51 |
| .0025-.005  |  940 |     51.4 |      1.39 |      47.7 |       5.99 |      46   |      17.52 |
| .005-.02    |  535 |     52.9 |      1.76 |      51   |      11.12 |      47.7 |      33.53 |
| >.02        |   48 |     33.3 |     -1.14 |      10.4 |     -22.01 |       4.2 |     -42.55 |

### impulse — forward returns by band (full sample)

| band     |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.5     |  372 |     56.2 |      1.54 |      52.3 |       4.78 |      61.1 |      23.43 |
| -.5--.15 |  603 |     51.5 |      0.45 |      54.6 |       6.69 |      58.8 |      19.83 |
| -.15-.15 | 2048 |     52.4 |      0.6  |      55.4 |       4.57 |      58.2 |      18.45 |
| .15-.5   |  582 |     58.8 |      2.31 |      62.3 |       8.85 |      61.4 |      27.05 |
| >.5      |  595 |     59.7 |      3.66 |      63.8 |      10.44 |      66   |      32.49 |

### cycle_pct — forward returns by band (full sample)

| band     |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| accum    |  963 |     61.1 |      2.76 |      70.4 |      13.26 |      80.6 |      47.86 |
| markup   |  876 |     52.6 |      1.48 |      48.6 |       6.58 |      53.7 |      22.24 |
| markdown | 1263 |     48.2 |     -0.56 |      47.9 |      -0.97 |      42   |       4.86 |
| recovery | 1098 |     57.6 |      2.13 |      62.8 |       8.23 |      66.7 |      18.54 |
| late     |    0 |    nan   |    nan    |     nan   |     nan    |     nan   |     nan    |

### cot_z — forward returns by band (full sample)

| band     |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1.5    | 224 |     50   |      0.23 |      51.3 |       5.29 |      47.8 |      13.25 |
| -1.5--.5 | 655 |     60.9 |      3.36 |      71.5 |      14.14 |      77.9 |      41.72 |
| -.5-.5   | 742 |     56.3 |      1.34 |      53.9 |       3.98 |      61.6 |      18.82 |
| .5-1.5   | 592 |     47.3 |      0.12 |      48.8 |       1.5  |      54.2 |       9.73 |
| >1.5     | 611 |     44.2 |     -1.12 |      43.9 |      -3.53 |      34.1 |      -5.92 |

### corr_spx — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     | 1034 |     56.1 |      1.78 |      57   |       7.01 |      61.4 |      29.23 |
| 0-.2   | 1208 |     57.4 |      2.18 |      64.5 |      12.1  |      69.2 |      32.64 |
| .2-.4  | 1015 |     53.1 |      0.61 |      49.2 |       2    |      56.2 |      10.94 |
| >.4    |  943 |     50.8 |      0.53 |      56.5 |       2.7  |      50.5 |      12.7  |

### vdd_multiple — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <.5     |  779 |     55.2 |      0.5  |      53.9 |       2.81 |      42.5 |       7.5  |
| .5-.87  | 1142 |     50.5 |      0.62 |      63.9 |       5.87 |      65.4 |      18.36 |
| .87-1.4 | 1200 |     56.1 |      1.3  |      48.6 |       1.99 |      64.7 |      18.77 |
| 1.4-2.9 |  912 |     57.8 |      2.77 |      65.6 |      15.92 |      61.3 |      41.06 |
| >2.9    |  154 |     51.9 |      2.86 |      40.3 |       4.02 |      59.1 |      35.2  |

### global_m2_yoy — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <5.5   |  519 |     53.4 |      1.24 |      60.7 |       6.05 |      72.6 |      23.39 |
| 5.5-7  | 1216 |     53   |      0.9  |      52.9 |       3.21 |      47.7 |       6.99 |
| 7-8.5  |  760 |     53.5 |      1.96 |      54.9 |      10.59 |      61.6 |      40.98 |
| 8.5-11 | 1310 |     54   |      0.54 |      56.5 |       3.53 |      59.7 |      15.75 |
| >11    |  395 |     64.6 |      4.23 |      72.2 |      17.65 |      80.8 |      57.97 |

### rv_cone_pctile — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 1206 |     54.9 |      1.2  |      59.1 |       5.53 |      70.6 |      24.84 |
| 25-50  | 1071 |     52.6 |      0.69 |      49.5 |       2.31 |      51.1 |      16.18 |
| 50-75  |  896 |     56.4 |      1.44 |      57.5 |       8.14 |      55.3 |      23.32 |
| 75-100 |  831 |     54.3 |      2.48 |      63.4 |      11.39 |      63.8 |      30.11 |

### vov_pctile — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 1160 |     55.1 |      1.31 |      51.9 |       3.48 |      53   |      12.54 |
| 25-50  |  996 |     52.8 |      0.88 |      56   |       6.47 |      56.1 |      20.43 |
| 50-75  |  993 |     54.3 |      1.55 |      60   |       6.64 |      63   |      28.12 |
| 75-100 |  826 |     56.8 |      2.04 |      64.4 |      11.4  |      73.8 |      36.65 |

### stbl_growth_z — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |  390 |     42.3 |     -1.27 |      39.4 |      -3.09 |      41.9 |       0.76 |
| -1-0   | 1558 |     53.3 |      0.95 |      53.9 |       4.22 |      54.9 |      16.96 |
| 0-1    |  620 |     49.5 |      0.84 |      51.1 |       4.01 |      55.8 |      16.26 |
| 1-2    |  228 |     72.8 |      4.22 |      78.1 |      14.14 |      75.9 |      23.38 |
| >2     |  162 |     51.2 |      0.65 |      60.5 |       5.47 |      62.3 |      19.55 |

## Allocation backtest vs HODL — GATED series (NET of 10.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it. **GATED** = final live behavior (midterm blackout active).

|              |   cagr |   cagr_gross |   cost_drag_pp |   hodl_cagr |   sharpe |   hodl_sharpe |   sortino |   hodl_sortino |   maxdd |   hodl_maxdd |   time_in_market |   turnover_annual |   final_vs_hodl |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |   53.7 |         56   |            2.3 |        57.7 |     1.46 |          1.01 |      1.5  |           1.36 |   -25.3 |        -83.8 |             54.5 |              14.8 |            0.75 |
| moderate     |   70.8 |         73.1 |            2.3 |        57.7 |     1.57 |          1.01 |      1.81 |           1.36 |   -32.3 |        -83.8 |             69.3 |              13.4 |            2.51 |
| aggressive   |   73.9 |         76.1 |            2.2 |        57.7 |     1.51 |          1.01 |      1.74 |           1.36 |   -36.4 |        -83.8 |             72.7 |              12.5 |            3.09 |
| optimal      |   70.3 |         72.6 |            2.3 |        57.7 |     1.56 |          1.01 |      1.8  |           1.36 |   -32.3 |        -83.8 |             70.2 |              13.3 |            2.43 |

## Allocation backtest vs HODL — RAW (ungated) series

Pure engine without midterm-blackout override. Pre-gate figures retired as of 2026-07; fresh dual-track compute (W1 N7).

|              |   cagr |   cagr_gross |   cost_drag_pp |   hodl_cagr |   sharpe |   hodl_sharpe |   sortino |   hodl_sortino |   maxdd |   hodl_maxdd |   time_in_market |   turnover_annual |   final_vs_hodl |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |   50.9 |         53.5 |            2.6 |        57.7 |     1.39 |          1.01 |      1.53 |           1.36 |   -33.6 |        -83.8 |             63.8 |              16.9 |            0.61 |
| moderate     |   64.7 |         67.4 |            2.7 |        57.7 |     1.46 |          1.01 |      1.8  |           1.36 |   -37.1 |        -83.8 |             81   |              16.2 |            1.66 |
| aggressive   |   63.1 |         65.7 |            2.6 |        57.7 |     1.33 |          1.01 |      1.66 |           1.36 |   -45.2 |        -83.8 |             85.8 |              15.7 |            1.48 |
| optimal      |   63.3 |         66   |            2.7 |        57.7 |     1.43 |          1.01 |      1.78 |           1.36 |   -41.2 |        -83.8 |             82.2 |              16.2 |            1.5  |

**Block-bootstrap 95% CI** [optimal, 5000 resamples, 21d blocks]: Sharpe **1.57** [0.95, 2.17] · MaxDD -41.8% [-29.6, -61.6] · P(Sharpe>0) 1.0. Circular block bootstrap (21d blocks) of the NET daily strategy returns → 95% CI [2.5, 50, 97.5]. sharpe_gt0_prob = bootstrap P(Sharpe>0). Pairs with the Deflated-Sharpe haircut: DSR deflates the mean, this bounds the variance.

## Purged walk-forward CV (stability gate)

8/31 signals **robust** under 5 embargoed folds (90d embargo = max horizon). Purged + embargoed walk-forward CV (embargo = max forward horizon) replaces the single split_date's leaky boundary. 'robust' = full-sample sign matches `want`, no fold flips, all-but-one folds agree. Stricter than pre/post; both are reported.

| Signal | full | folds | want | robust |
|---|--:|---|--:|:-:|
| risk_index | -1 | [-1, -1, -1, -1, 0] | -1 | ✅ |
| momentum | +1 | [0, 1, 1, 1, 0] | +1 | ✅ |
| structure | +1 | [-1, 1, 1, 1, 0] | +1 | · |
| risk_oscillator | -1 | [-1, -1, -1, -1, 1] | -1 | · |
| bfi | +1 | [-1, 0, 0, 1, -1] | +1 | · |
| mvrv_z | +0 | [0, 0, 0, -1, 0] | -1 | · |
| nupl | +0 | [1, 0, 0, -1, 0] | -1 | · |
| mayer | +1 | [0, 1, 1, 1, 0] | -1 | · |
| puell | +1 | [0, 1, -1, 0, 0] | -1 | · |
| sth_cb_ratio | +0 | [0, 0, 0, 0, 0] | +1 | · |
| dvol | +0 | [0, 0, 0, -1, 1] | -1 | · |
| vrp | -1 | [0, 0, 0, -1, -1] | -1 | ✅ |
| leverage_stress | +0 | [0, 0, 0, 0, 1] | -1 | · |
| funding_z | +0 | [0, 0, 0, 0, -1] | -1 | · |
| oi_price_divergence | -1 | [0, 0, 0, 0, 0] | -1 | · |
| net_liq_roc | +1 | [1, 1, 0, 0, 0] | +1 | ✅ |
| macro_score | +1 | [1, 1, -1, 1, 1] | +1 | · |
| coinbase_premium_ema | -1 | [0, -1, 0, 0, 0] | +1 | · |
| ssr_oscillator | +0 | [0, 0, 0, 0, 0] | +1 | · |
| mpi | +1 | [0, 0, 0, -1, -1] | -1 | · |
| etf_flow_z | +1 | [0, 0, 0, 0, 1] | +1 | ✅ |
| reserve_risk | +1 | [0, 0, -1, -1, 0] | -1 | · |
| impulse | +1 | [0, 0, 1, 1, 1] | +1 | ✅ |
| cycle_pct | -1 | [0, 0, -1, 0, -1] | -1 | ✅ |
| cot_z | -1 | [0, 0, 0, -1, -1] | -1 | ✅ |
| corr_spx | -1 | [0, -1, 1, -1, 1] | -1 | · |
| vdd_multiple | +1 | [0, 1, 0, 1, -1] | -1 | · |
| global_m2_yoy | +1 | [0, 0, 1, -1, -1] | +1 | · |
| rv_cone_pctile | +0 | [-1, 1, 0, -1, 1] | -1 | · |
| vov_pctile | +1 | [-1, 1, 0, 0, 1] | -1 | · |
| stbl_growth_z | +1 | [0, 0, -1, 1, 0] | +1 | · |

## Probability calibration of the conviction layer (out-of-fold)

OOF 7d direction: **Brier 0.2498** vs base 0.2483 (skill -0.006); Platt a=0.701, b=0.032. Out-of-fold: each day's P(up) is the momentum×risk cell rate fit on the OTHER folds (EB-shrunk, the live mechanism), scored vs realized. brier<base_brier = skill; Platt a≈1/b≈0 = already calibrated. Direction is a near-coin-flip, so calibrated probabilities cluster near the base rate — that is the honest result.

| prob bin | n | predicted | observed |
|---|--:|--:|--:|
| 0.5-0.6 | 3667 | 0.545 | 0.543 |
| 0.6-0.7 | 83 | 0.606 | 0.446 |

## Signal collinearity (orthogonalize before any blend)

20 signals with **VIF≥5** (redundant): risk_index, momentum, structure, bfi, mvrv_z, nupl, mayer, puell, sth_cb_ratio, dvol, vrp, ssr_oscillator, reserve_risk, cycle_pct, cot_z, corr_spx, vdd_multiple, global_m2_yoy, rv_cone_pctile, stbl_growth_z. VIF>5 ≈ redundant (its forward info is already carried by other signals); the high-corr pairs name the cluster. This MEASURES the independent contribution the one-representative-per-axis rule asserts — orthogonalize before any blend.

| a | b | \|corr\| |
|---|---|--:|
| mvrv_z | nupl | 0.96 |
| mayer | sth_cb_ratio | 0.94 |
| mayer | ssr_oscillator | 0.93 |
| nupl | reserve_risk | 0.91 |
| sth_cb_ratio | ssr_oscillator | 0.91 |
| mvrv_z | reserve_risk | 0.9 |
| mvrv_z | mayer | 0.87 |
| mvrv_z | sth_cb_ratio | 0.87 |
| mvrv_z | ssr_oscillator | 0.86 |
| momentum | sth_cb_ratio | 0.83 |

## Deflated Sharpe Ratio — GATED series (multiple-testing haircut)

**SURVIVES multiple-testing (DSR≥0.95)** — shipped variant `optimal` (GATED / live behavior).

- DSR (gated) — P(true Sharpe > 0): **0.9986**
- Observed Sharpe 1.56 ann (0.081826/day); haircut threshold SR0 0.69 ann
- N=68 trials (upper-bound, incl. override dof_cost) · T=4200d · skew=0.661 · kurt=13.966 · SR-variance: max(cross-variant dispersion, null SR-sampling proxy)
- **Effective-N haircut**: T_eff=2512.7 vs raw T=4200 (rho_sum_K20=0.3358); dsr_effN=0.9622 (dsr_legacy=0.9986). Block-bootstrap refinement: W5.

> DSR = P(true Sharpe>0) after deflating for n_trials independent configs, sample length, skew & kurtosis. n_trials is a manual UPPER-BOUND of the signal/threshold/window variants explored — overestimating is the conservative direction (de Prado). Bump vector.calibration.n_trials as you try more. GATED series (live behavior).

## Deflated Sharpe Ratio — RAW (ungated) series

**SURVIVES multiple-testing (DSR≥0.95)** — variant `optimal` (RAW / pure engine).

> Pre-gate figure (0.9965) retired as of 2026-07. This is the fresh dual-track compute. Raw series excludes midterm-blackout contamination.
- DSR (raw) — P(true Sharpe > 0): **0.9945**
- Observed Sharpe 1.43 ann; SR0 0.69 ann
- N=68 trials · T=4200d · skew=0.607 · kurt=12.983
- **Effective-N haircut**: T_eff=2523.0, dsr_effN=0.9236 (dsr_legacy=0.9945)

> DSR on the RAW (ungated) series — pure engine without override contamination. Pre-gate figure (0.9965) retired; this is the fresh dual-track compute as of 2026-07. n_trials includes override dof_cost. RAW series.

## Trial log (W1 N7 — n_trials breakdown)

As-of 2026-07-01: **n_trials_total=68** = n_trials_base=65 (config upper-bound) + n_trials_overrides=3 (sum of override dof_costs).
  - override `midterm_blackout`: dof_cost=3
32 signal families screened; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 10.0bps one-way.

> Point-in-time trial ledger (overwritten each run). n_trials_total = n_trials_base (config upper-bound) + sum(dof_cost) across registered overrides (W1 N7). Raise n_trials_base as you try more configs; each new override must declare its dof_cost, which is ADDED here.

## Ensemble capstone — does combining beat the heuristic?

**KEEP-HEURISTIC — the hand-tuned composite_state is NOT beaten by the fixed-form ensemble**

Each axis oriented by its calibrated expected-fwd-return band-map (handles the U-shape a linear z can't), de-correlated in a fixed order, equal-weight combined. Promotion needs the ensemble to beat BOTH the best single signal AND the heuristic composite_state on net Sharpe in BOTH halves. Honest non-promotion = keep the simpler winner (the forecast-combination literature: equal-weight/best-single are brutal baselines on ~3 cycles).

| read | net Sharpe full | pre-2021 | post-2021 |
|---|--:|--:|--:|
| ensemble_eqw | 1.25 | 1.48 | 0.54 |
| best_single | 0.96 | 1.19 | 0.39 |
| heuristic | 1.18 | 1.48 | 0.64 |

Ensemble OOF rank-IC vs 90d return: **0.193** (best single axis = `net_liq_roc`). Per-axis IC: risk_index 0.077, net_liq_roc 0.268, vrp nan, cot_z 0.005, mvrv_z 0.061, momentum 0.15.

## Whipsaw

|                  |   changes |   whipsaws |   pct |
|:-----------------|----------:|-----------:|------:|
| momentum_state   |       180 |         36 |  20   |
| risk_regime      |       126 |         25 |  19.8 |
| structure_state  |       178 |         36 |  20.2 |
| market_mode      |        88 |         15 |  17   |
| alt_cycle_leader |       102 |         21 |  20.6 |