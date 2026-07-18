# Bitcoin Vector — calibration report

Span: 2015-01-01..2026-07-17 (4216 days). Split-half boundary: 2021-01-01.

House rule: a signal is trusted (labeled a *signal* in the UI) only if its forward outcome relationship trends in the expected direction in the full sample AND survives both halves (rank-trend |rho|>0.6, tolerant of one small-sample band). Return-predicting signals (momentum, structure, BFI) are judged on forward RETURN; the Risk Index is judged on forward DRAWDOWN (its actual job) because at long horizons extreme risk marks capitulation and forward *return* is U-shaped — the documented contrarian behavior, not a defect. Anything failing is context-only; anything inverted is flagged.

## Signal verdicts

| Signal | Verdict | full | pre | post | want |
|---|---|--:|--:|--:|--:|
| risk_index | **DIRECTIONAL (one half weak)** | -1 | -1 | 0 | -1 |
| momentum | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| structure | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| risk_oscillator | **CONTEXT-ONLY** | 0 | 0 | -1 | -1 |
| bfi | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| mvrv_z | **EXTREMES — low <0: +40.5%/90d 71.9% hit (n=356) [BOTTOM]; high >3.5: +27.1%/90d 57.8% hit (n=277) [weak]** | 0 | 0 | 0 | -1 |
| nupl | **EXTREMES — low <0: +28.0%/90d 66.5% hit (n=603) [BOTTOM]; high >.65: +25.8%/90d 58.5% hit (n=265) [weak]** | 0 | 0 | -1 | -1 |
| mayer | **EXTREMES — low <0.8: +11.3%/90d 48.1% hit (n=633) [weak]; high >2.4: -13.9%/90d 33.9% hit (n=62) [TOP]** | 1 | 1 | 0 | -1 |
| puell | **EXTREMES — low <0.5: +15.8%/90d 59.5% hit (n=153) [weak]** | 1 | 1 | 0 | -1 |
| sth_cb_ratio | **EXTREMES — low <-10%: -1.3%/90d 32.5% hit (n=321) [weak]** | 0 | 0 | 0 | 1 |
| hash_ribbon_capit | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| dvol | **EXTREMES — low <40: +8.4%/90d 46.8% hit (n=239) [weak]; high >90: +15.8%/90d 71.4% hit (n=168) [weak]** | 0 | 0 | 0 | -1 |
| vrp | **EXTREMES — low <-5: +17.2%/90d 77.8% hit (n=203) [weak]; high >15: +7.2%/90d 53.9% hit (n=484) [TOP]** | -1 | 0 | -1 | -1 |
| leverage_stress | **EXTREMES — low 0-25: +13.5%/90d 62.4% hit (n=690) [weak]** | -1 | 0 | -1 | -1 |
| funding_z | **EXTREMES — tails too thin to judge** | 0 | 0 | 0 | -1 |
| oi_price_divergence | **EXTREMES — low <-10%: +14.8%/90d 70.4% hit (n=159) [weak]** | -1 | 0 | -1 | -1 |
| net_liq_roc | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| macro_score | **CONFIRMED** | 1 | 1 | 1 | 1 |
| coinbase_premium_ema | **EXTREMES — low <-.3: +34.5%/90d 57.1% hit (n=184) [BOTTOM]** | -1 | 0 | 0 | 1 |
| ssr_oscillator | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| mpi | **INVERTED** | 1 | 0 | 1 | -1 |
| etf_flow_z | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| reserve_risk | **EXTREMES — low <.0015: +17.5%/90d 66.0% hit (n=979) [weak]; high >.02: -42.5%/90d 4.2% hit (n=48) [TOP]** | 1 | 0 | -1 | -1 |
| impulse | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| cycle_pct | **DIRECTIONAL (one half weak)** | -1 | -1 | 0 | -1 |
| cot_z | **EXTREMES — low <-1.5: +13.2%/90d 47.8% hit (n=224) [weak]; high >1.5: -6.1%/90d 33.1% hit (n=627) [TOP]** | -1 | 0 | -1 | -1 |
| corr_spx | **CONFIRMED** | -1 | -1 | -1 | -1 |
| vdd_multiple | **EXTREMES — low <.5: +7.1%/90d 41.5% hit (n=779) [weak]; high >2.9: +35.2%/90d 59.1% hit (n=154) [weak]** | 1 | 1 | 0 | -1 |
| global_m2_yoy | **DIRECTIONAL (full only)** | 1 | 0 | -1 | 1 |
| rv_cone_pctile | **EXTREMES — low 0-25: +24.8%/90d 70.6% hit (n=1219) [weak]; high 75-100: +30.1%/90d 63.8% hit (n=831) [weak]** | 0 | 0 | 0 | -1 |
| vov_pctile | **EXTREMES — low 0-25: +12.5%/90d 53.0% hit (n=1167) [weak]; high 75-100: +36.6%/90d 73.7% hit (n=826) [weak]** | 1 | 1 | 0 | -1 |
| stbl_growth_z | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |

## Risk Index as a drawdown gauge

**CONFIRMED near-term risk gauge (7d drawdown)** — rank-trend {'full': -1, 'pre': -1, 'post': -1, 'want': -1, 'horizon': 7}.

| band   |    n |   avgDD_7d |   p05DD_7d |   avgDD_30d |   p05DD_30d |   avgDD_90d |   p05DD_90d |
|:-------|-----:|-----------:|-----------:|------------:|------------:|------------:|------------:|
| 0-25   | 2057 |      -2.99 |     -14.23 |       -8.3  |      -26.09 |      -14.01 |      -46.94 |
| 25-50  | 1347 |      -4.04 |     -16.24 |       -9.87 |      -30.33 |      -17.66 |      -50.33 |
| 50-75  |  708 |      -4.64 |     -20.76 |       -9.74 |      -36.88 |      -14.56 |      -41.63 |
| 75-100 |  104 |      -4.29 |     -15.96 |       -8.85 |      -27.33 |      -12.1  |      -32.43 |

### risk_index — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 2057 |     56.2 |      1.97 |      56.2 |       7.77 |      66.7 |      28.89 |
| 25-50  | 1347 |     53.1 |      0.67 |      57.6 |       5.18 |      51.2 |      16.46 |
| 50-75  |  708 |     54   |      0.71 |      59.1 |       4.48 |      56.3 |      14.35 |
| 75-100 |  104 |     49   |      1.83 |      55.8 |       4.01 |      60.4 |      15.57 |

### momentum — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-0.5   | 1054 |     53.2 |      0.21 |      56.6 |       1.95 |      51.3 |       6.58 |
| -0.5..0 |  679 |     51.4 |      0.69 |      56.6 |       3.92 |      57.5 |      18.94 |
| 0..0.5  |  785 |     51.6 |      0.68 |      53.6 |       5.56 |      54.3 |      22.91 |
| >0.5    | 1698 |     58.3 |      2.6  |      59.2 |      10.22 |      68.5 |      32.35 |

### structure — forward returns by band (full sample)

| band         |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| broken       | 1170 |     53   |      0.46 |      59.6 |       3.22 |      57.3 |      12.2  |
| neutral      | 1240 |     53.6 |      0.93 |      55.6 |       6.16 |      56.1 |      22.11 |
| constructive | 1806 |     56.5 |      2.19 |      56.6 |       8.34 |      64.1 |      28.5  |

### risk_oscillator — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| falling | 1686 |     55.9 |      1.94 |      58.6 |       6.21 |      58.5 |      22.04 |
| neutral | 1252 |     54.8 |      1.31 |      58.2 |       7.06 |      63.1 |      24.54 |
| rising  | 1278 |     52.9 |      0.58 |      54.1 |       5.67 |      58.5 |      19.97 |

### bfi — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <40    | 1601 |     51   |      0.51 |      52.3 |       3.49 |      49.3 |      13.22 |
| 40-60  | 1063 |     55   |      0.72 |      57.6 |       6.96 |      62.9 |      23.1  |
| >60    | 1477 |     58.4 |      2.75 |      62.1 |       9.04 |      69.9 |      32.19 |

### mvrv_z — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     |  356 |     58.7 |      1.86 |      68   |       9.71 |      71.9 |      40.55 |
| 0-1    | 1229 |     53.7 |      0.96 |      56   |       3.79 |      49.5 |       4.76 |
| 1-2    | 1148 |     52.4 |      0.72 |      55.6 |       3.95 |      67.7 |      23.48 |
| 2-3.5  |  948 |     56.5 |      1.84 |      56.9 |      10.2  |      59.8 |      36.62 |
| >3.5   |  277 |     59.9 |      4.67 |      58.1 |      14.54 |      57.8 |      27.15 |

### nupl — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     |  603 |     56.7 |      1.07 |      63.2 |       6.29 |      66.5 |      28.01 |
| 0-.25  |  651 |     57.8 |      1.83 |      67   |       6.97 |      56   |       9.88 |
| .25-.5 | 1670 |     52.9 |      0.73 |      52.9 |       2.59 |      60.3 |      16.88 |
| .5-.65 | 1027 |     53.7 |      1.44 |      54.1 |      10.19 |      58   |      33.38 |
| >.65   |  265 |     57.4 |      4.19 |      58.5 |      13.03 |      58.5 |      25.77 |

### mayer — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.8    |  633 |     54.7 |      1.01 |      61.8 |       4.08 |      48.1 |      11.26 |
| 0.8-1   |  974 |     51.3 |     -0.03 |      52.6 |       1.89 |      52.6 |      11.16 |
| 1-1.5   | 1888 |     55.7 |      1.46 |      57.9 |       6.15 |      68.3 |      24.11 |
| 1.5-2.4 |  566 |     58.7 |      3.82 |      60.6 |      18.69 |      62.5 |      53.36 |
| >2.4    |   62 |     43.5 |      2.27 |      43.5 |      -1.92 |      33.9 |     -13.95 |

### puell — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.5   |  153 |     54.9 |      1.22 |      64.7 |       4.09 |      59.5 |      15.76 |
| 0.5-1  | 1715 |     54   |      0.64 |      58.5 |       4.13 |      61.5 |      20.67 |
| 1-2    | 1855 |     55.1 |      1.7  |      55.6 |       6.87 |      60.1 |      20.23 |
| 2-4    |  397 |     54.7 |      2.41 |      57.4 |      14.94 |      58.7 |      47.89 |
| >4     |   23 |     56.5 |     10.54 |      34.8 |      -3.22 |      17.4 |     -33.4  |

### sth_cb_ratio — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-10%  | 321 |     53.9 |      0.6  |      58.5 |       1.73 |      32.5 |      -1.27 |
| -10-0% | 358 |     51.6 |     -0.02 |      56.3 |       2.25 |      71.4 |      24.2  |
| 0-20%  | 621 |     53.1 |      1.17 |      52.5 |       4.5  |      58.8 |       9.29 |
| 20-50% | 196 |     52   |      0.97 |      55.6 |       3.69 |      68.9 |      13.76 |
| >50%   |   0 |    nan   |    nan    |     nan   |     nan    |     nan   |     nan    |

### hash_ribbon_capit — forward returns by band (full sample)

| band         |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| normal       | 3445 |       55 |      1.57 |      58.3 |       7.18 |      60   |      23.31 |
| capitulation |  771 |       53 |      0.31 |      51.8 |       2.21 |      59.4 |      16.52 |

### dvol — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <40    | 239 |     48.3 |     -0.68 |      40.4 |      -1.08 |      46.8 |       8.4  |
| 40-55  | 655 |     52.1 |      0.96 |      58.8 |       4.4  |      61.7 |      11.67 |
| 55-70  | 479 |     54.1 |      0.47 |      53.9 |       2.88 |      62.6 |      10.65 |
| 70-90  | 401 |     48.9 |      0.01 |      38.4 |      -3.8  |      18.7 |     -12.64 |
| >90    | 168 |     47   |     -0.28 |      47   |       2.06 |      71.4 |      15.84 |

### vrp — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-5    | 203 |     57.6 |      1.05 |      61.6 |       3.81 |      77.8 |      17.23 |
| -5-0   | 170 |     57.6 |      1.65 |      62.6 |       5.44 |      50   |       8.81 |
| 0-5    | 371 |     50.3 |      0.2  |      53.4 |       2.34 |      35.6 |       1.64 |
| 5-15   | 714 |     46.6 |     -0.47 |      46.1 |      -0.57 |      51.2 |       3.74 |
| >15    | 484 |     52.9 |      0.88 |      44.6 |       1.45 |      53.9 |       7.2  |

### leverage_stress — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 690 |     54.2 |      1.31 |      58.7 |       4.03 |      62.4 |      13.51 |
| 25-50  | 440 |     52   |      0.19 |      52.8 |       2.55 |      61.3 |      14.09 |
| 50-75  | 335 |     51.4 |      0.36 |      49.1 |       2.5  |      45.1 |       3.27 |
| 75-100 |  17 |     52.9 |      1.51 |      64.7 |       5.27 |      47.1 |       2.58 |

### funding_z — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |   0 |      nan |       nan |       nan |        nan |       nan |        nan |
| -1-0   |   0 |      nan |       nan |       nan |        nan |       nan |        nan |
| 0-1    |   0 |      nan |       nan |       nan |        nan |       nan |        nan |
| 1-2    |   0 |      nan |       nan |       nan |        nan |       nan |        nan |
| >2     |   0 |      nan |       nan |       nan |        nan |       nan |        nan |

### oi_price_divergence — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-10%  | 159 |     58.5 |      1.04 |      58.5 |       0.82 |      70.4 |      14.78 |
| -10-0% | 528 |     53.2 |      1.24 |      59   |       4.8  |      63.4 |      13.54 |
| 0-10%  | 638 |     52.4 |      0.59 |      51.7 |       3.34 |      53.4 |       9.55 |
| 10-25% | 151 |     49   |     -0.23 |      52.3 |       0.73 |      45.9 |       6.61 |
| >25%   |   6 |     16.7 |     -3.5  |       0   |      -5.7  |      33.3 |      -4.16 |

### net_liq_roc — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-2%   | 1251 |     52   |      0.51 |      53.4 |       1.58 |      48.8 |       8.69 |
| -2-0%  |  857 |     53.9 |      1.52 |      56.3 |       7.47 |      61.7 |      18.12 |
| 0-2%   |  861 |     52.5 |      1.13 |      56.1 |       5.34 |      61.4 |      22.08 |
| 2-5%   |  716 |     59.7 |      2.11 |      60   |       8.85 |      69.1 |      37.21 |
| >5%    |  508 |     58.5 |      2.23 |      65   |      14.01 |      67.3 |      41.68 |

### macro_score — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.3   | 571 |     52   |     -0.04 |      51.3 |      -0.38 |      42.6 |       3.03 |
| -.3-.1 | 812 |     53.2 |      1.22 |      60.6 |       5.53 |      59.5 |      17.91 |
| -.1-.1 | 965 |     58   |      1.91 |      58.4 |       8.08 |      56.4 |      19.65 |
| .1-.3  | 941 |     54.4 |      1.66 |      58.7 |       7.55 |      62   |      18.02 |
| >.3    | 927 |     54.5 |      1.37 |      54.7 |       8.03 |      72.7 |      44.87 |

### coinbase_premium_ema — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.3   |  184 |     52.2 |      1.33 |      60.3 |       4.32 |      57.1 |      34.46 |
| -.3-0  |  979 |     51   |      0.19 |      50.8 |       1.82 |      44.2 |       5.42 |
| 0-.5   | 1882 |     52.6 |      0.98 |      52.8 |       4.18 |      55.8 |      13.57 |
| .5-1.5 |   61 |     55.7 |      1.7  |      59   |      13.3  |      93.4 |      85.36 |
| >1.5   |    4 |     25   |     -2.57 |       0   |      -8.47 |       0   |     -28.98 |

### ssr_oscillator — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |  484 |     52.3 |      1.11 |      50.4 |       4.16 |      55.6 |       9.9  |
| -1-.3  |  316 |     52.8 |      0.94 |      70.6 |       8.91 |      73.7 |      17.39 |
| -.3-.5 |  516 |     55.2 |      1.31 |      47.9 |       0.8  |      47.3 |       3.5  |
| .5-1.5 | 1406 |     52.1 |      0.63 |      50.9 |       3.49 |      54   |      22.29 |
| >1.5   |  342 |     48.5 |      0.08 |      57   |       4.09 |      39.7 |       2.65 |

### mpi — forward returns by band (full sample)

| band    |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.7    | 357 |     50   |      0.11 |      52.9 |       0.42 |      51.3 |       6.32 |
| 0.7-1   | 255 |     55.7 |      0.48 |      56.1 |       3.2  |      67.1 |      15.14 |
| 1-1.5   | 370 |     51.6 |      0.78 |      55.7 |       3.83 |      63.5 |      13.56 |
| 1.5-2.5 | 255 |     58.8 |      1.95 |      64.3 |       8.59 |      69.4 |      19.37 |
| >2.5    | 140 |     52.9 |      1.35 |      46.4 |       2.13 |      60   |      11    |

### etf_flow_z — forward returns by band (full sample)

| band      |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:----------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.75     | 214 |     47.2 |     -0.37 |      37.7 |      -3.63 |      41.8 |       0.85 |
| -.75--.25 | 143 |     51   |      0.02 |      53.6 |       0.1  |      42.1 |       0.35 |
| -.25-.25  | 159 |     47.5 |      0.14 |      56.1 |       2.23 |      43.6 |       3.17 |
| .25-.75   | 110 |     61.5 |      1.49 |      62.4 |       4.91 |      59.4 |       9.88 |
| >.75      | 157 |     57.3 |      1.13 |      57.3 |       4.02 |      61.4 |       7.13 |

### reserve_risk — forward returns by band (full sample)

| band        |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <.0015      |  979 |     55.8 |      1.47 |      61.8 |       5.68 |      66   |      17.52 |
| .0015-.0025 | 1685 |     56.9 |      1.18 |      63   |       6.11 |      69.8 |      25.51 |
| .0025-.005  |  940 |     51.4 |      1.39 |      47.7 |       5.99 |      46   |      17.52 |
| .005-.02    |  535 |     52.9 |      1.76 |      51   |      11.12 |      47.7 |      33.53 |
| >.02        |   48 |     33.3 |     -1.14 |      10.4 |     -22.01 |       4.2 |     -42.55 |

### impulse — forward returns by band (full sample)

| band     |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.5     |  376 |     55.9 |      1.52 |      51.3 |       4.42 |      60.7 |      23.52 |
| -.5--.15 |  609 |     52.4 |      0.57 |      56.4 |       6.87 |      59.7 |      19.88 |
| -.15-.15 | 2042 |     52.3 |      0.59 |      54.8 |       4.52 |      57.6 |      18.18 |
| .15-.5   |  578 |     58.9 |      2.23 |      63.6 |       9.02 |      61.9 |      27.58 |
| >.5      |  611 |     60.2 |      3.66 |      63.1 |      10.27 |      65.1 |      31.65 |

### cycle_pct — forward returns by band (full sample)

| band     |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| accum    |  963 |     61.1 |      2.76 |      70.4 |      13.26 |      80.6 |      47.86 |
| markup   |  876 |     52.6 |      1.48 |      48.6 |       6.58 |      53.7 |      22.24 |
| markdown | 1279 |     48.7 |     -0.51 |      47.8 |      -0.96 |      41.5 |       4.63 |
| recovery | 1098 |     57.6 |      2.13 |      62.8 |       8.23 |      66.7 |      18.54 |
| late     |    0 |    nan   |    nan    |     nan   |     nan    |     nan   |     nan    |

### cot_z — forward returns by band (full sample)

| band     |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1.5    | 224 |     50   |      0.23 |      51.3 |       5.29 |      47.8 |      13.25 |
| -1.5--.5 | 655 |     60.9 |      3.36 |      71.5 |      14.14 |      77.9 |      41.72 |
| -.5-.5   | 742 |     56.3 |      1.34 |      53.9 |       3.98 |      61.6 |      18.82 |
| .5-1.5   | 592 |     47.3 |      0.12 |      48.8 |       1.5  |      54.2 |       9.73 |
| >1.5     | 627 |     45.3 |     -1.01 |      43.9 |      -3.44 |      33.1 |      -6.09 |

### corr_spx — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     | 1034 |     56.1 |      1.78 |      57   |       7.01 |      61.4 |      29.23 |
| 0-.2   | 1208 |     57.4 |      2.18 |      64.5 |      12.1  |      69.2 |      32.64 |
| .2-.4  | 1031 |     53.6 |      0.65 |      49.1 |       1.98 |      56.2 |      10.94 |
| >.4    |  943 |     50.8 |      0.53 |      56.4 |       2.68 |      49.5 |      12.25 |

### vdd_multiple — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <.5     |  779 |     55.2 |      0.5  |      53.7 |       2.75 |      41.5 |       7.07 |
| .5-.87  | 1142 |     50.5 |      0.62 |      63.9 |       5.87 |      65.4 |      18.36 |
| .87-1.4 | 1200 |     56.1 |      1.3  |      48.6 |       1.99 |      64.7 |      18.77 |
| 1.4-2.9 |  912 |     57.8 |      2.77 |      65.6 |      15.92 |      61.3 |      41.06 |
| >2.9    |  154 |     51.9 |      2.86 |      40.3 |       4.02 |      59.1 |      35.2  |

### global_m2_yoy — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <5.5   |  519 |     53.4 |      1.24 |      60.7 |       6.05 |      72.6 |      23.39 |
| 5.5-7  | 1216 |     53   |      0.9  |      52.9 |       3.21 |      47.7 |       6.99 |
| 7-8.5  |  776 |     54.2 |      1.99 |      54.7 |      10.35 |      60.2 |      39.75 |
| 8.5-11 | 1310 |     54   |      0.54 |      56.5 |       3.53 |      59.7 |      15.75 |
| >11    |  395 |     64.6 |      4.23 |      72.2 |      17.65 |      80.8 |      57.97 |

### rv_cone_pctile — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 1219 |     55   |      1.2  |      59   |       5.52 |      70.6 |      24.84 |
| 25-50  | 1073 |     52.9 |      0.72 |      49.5 |       2.28 |      50.5 |      15.86 |
| 50-75  |  897 |     56.5 |      1.45 |      57.5 |       8.14 |      55.1 |      23.16 |
| 75-100 |  831 |     54.3 |      2.48 |      63.4 |      11.39 |      63.8 |      30.11 |

### vov_pctile — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 1167 |     55.4 |      1.32 |      51.9 |       3.48 |      53   |      12.54 |
| 25-50  | 1005 |     52.9 |      0.89 |      56   |       6.42 |      55.8 |      20.27 |
| 50-75  |  993 |     54.5 |      1.56 |      59.8 |       6.58 |      62.4 |      27.7  |
| 75-100 |  826 |     56.8 |      2.04 |      64.4 |      11.4  |      73.7 |      36.6  |

### stbl_growth_z — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |  407 |     44   |     -1.1  |      39.5 |      -2.97 |      41.8 |       0.7  |
| -1-0   | 1557 |     53.3 |      0.95 |      53.9 |       4.23 |      54.3 |      16.68 |
| 0-1    |  620 |     49.5 |      0.84 |      51.1 |       4.01 |      55.8 |      16.26 |
| 1-2    |  228 |     72.8 |      4.22 |      78.1 |      14.14 |      75.9 |      23.38 |
| >2     |  162 |     51.2 |      0.65 |      60.5 |       5.47 |      62.3 |      19.55 |

## Allocation backtest vs HODL — GATED series (NET of 10.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it. **GATED** = final live behavior (midterm blackout active).

|              |   cagr |   cagr_gross |   cost_drag_pp |   hodl_cagr |   sharpe |   hodl_sharpe |   sortino |   hodl_sortino |   maxdd |   hodl_maxdd |   time_in_market |   turnover_annual |   final_vs_hodl |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |   55.3 |         57.6 |            2.3 |        58.5 |     1.5  |          1.02 |      1.51 |           1.37 |   -27   |        -83.8 |             53.2 |              14.4 |            0.79 |
| moderate     |   71.5 |         73.8 |            2.3 |        58.5 |     1.6  |          1.02 |      1.81 |           1.37 |   -32.3 |        -83.8 |             68.6 |              13.2 |            2.48 |
| aggressive   |   75   |         77.2 |            2.2 |        58.5 |     1.53 |          1.02 |      1.75 |           1.37 |   -36.4 |        -83.8 |             71.9 |              12.4 |            3.14 |
| optimal      |   71   |         73.2 |            2.3 |        58.5 |     1.59 |          1.02 |      1.81 |           1.37 |   -32.3 |        -83.8 |             69.5 |              13.1 |            2.39 |

## Allocation backtest vs HODL — RAW (ungated) series

Pure engine without midterm-blackout override. Pre-gate figures retired as of 2026-07; fresh dual-track compute (W1 N7).

|              |   cagr |   cagr_gross |   cost_drag_pp |   hodl_cagr |   sharpe |   hodl_sharpe |   sortino |   hodl_sortino |   maxdd |   hodl_maxdd |   time_in_market |   turnover_annual |   final_vs_hodl |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |   50.9 |         53.4 |            2.5 |        58.5 |     1.39 |          1.02 |      1.51 |           1.37 |   -33.6 |        -83.8 |             63.1 |              16.7 |            0.57 |
| moderate     |   63.8 |         66.4 |            2.7 |        58.5 |     1.45 |          1.02 |      1.78 |           1.37 |   -37.1 |        -83.8 |             80.7 |              16.2 |            1.46 |
| aggressive   |   62.9 |         65.5 |            2.6 |        58.5 |     1.33 |          1.02 |      1.66 |           1.37 |   -45.2 |        -83.8 |             85.5 |              15.7 |            1.37 |
| optimal      |   62.3 |         65   |            2.6 |        58.5 |     1.42 |          1.02 |      1.76 |           1.37 |   -41.2 |        -83.8 |             81.9 |              16.2 |            1.32 |

**Block-bootstrap 95% CI** [optimal, 5000 resamples, 21d blocks]: Sharpe **1.59** [0.96, 2.2] · MaxDD -41.3% [-29.2, -60.7] · P(Sharpe>0) 1.0. Circular block bootstrap (21d blocks) of the NET daily strategy returns → 95% CI [2.5, 50, 97.5]. sharpe_gt0_prob = bootstrap P(Sharpe>0). Pairs with the Deflated-Sharpe haircut: DSR deflates the mean, this bounds the variance.

## Purged walk-forward CV (stability gate)

9/31 signals **robust** under 5 embargoed folds (90d embargo = max horizon). Purged + embargoed walk-forward CV (embargo = max forward horizon) replaces the single split_date's leaky boundary. 'robust' = full-sample sign matches `want`, no fold flips, all-but-one folds agree. Stricter than pre/post; both are reported.

| Signal | full | folds | want | robust |
|---|--:|---|--:|:-:|
| risk_index | -1 | [-1, -1, -1, -1, 0] | -1 | ✅ |
| momentum | +1 | [0, 1, 1, 1, 0] | +1 | ✅ |
| structure | +1 | [-1, 1, 1, 1, 0] | +1 | · |
| risk_oscillator | -1 | [-1, -1, -1, -1, -1] | -1 | ✅ |
| bfi | +1 | [-1, 0, 0, 1, 0] | +1 | · |
| mvrv_z | +0 | [0, 0, 0, -1, 0] | -1 | · |
| nupl | +0 | [1, 0, 0, -1, 0] | -1 | · |
| mayer | +1 | [0, 1, 1, 1, 0] | -1 | · |
| puell | +1 | [0, 1, -1, 0, 0] | -1 | · |
| sth_cb_ratio | +0 | [0, 0, 0, 0, 0] | +1 | · |
| dvol | +0 | [0, 0, 0, -1, 1] | -1 | · |
| vrp | -1 | [0, 0, 0, -1, -1] | -1 | ✅ |
| leverage_stress | -1 | [0, 0, 0, 0, 0] | -1 | · |
| funding_z | +0 | [0, 0, 0, 0, 0] | -1 | · |
| oi_price_divergence | -1 | [0, 0, 0, 0, 0] | -1 | · |
| net_liq_roc | +1 | [1, 1, 0, 1, 1] | +1 | ✅ |
| macro_score | +1 | [1, 1, -1, 1, 1] | +1 | · |
| coinbase_premium_ema | -1 | [0, -1, 0, 0, 0] | +1 | · |
| ssr_oscillator | +0 | [0, 0, 0, 0, 0] | +1 | · |
| mpi | +1 | [0, 0, 0, -1, 0] | -1 | · |
| etf_flow_z | +1 | [0, 0, 0, 0, 1] | +1 | ✅ |
| reserve_risk | +1 | [0, 0, -1, -1, 0] | -1 | · |
| impulse | +1 | [0, 0, 1, 1, 1] | +1 | ✅ |
| cycle_pct | -1 | [0, 0, -1, 0, -1] | -1 | ✅ |
| cot_z | -1 | [0, 0, 0, -1, -1] | -1 | ✅ |
| corr_spx | -1 | [0, -1, 1, -1, 1] | -1 | · |
| vdd_multiple | +1 | [0, 1, 1, 1, -1] | -1 | · |
| global_m2_yoy | +1 | [0, 0, 1, -1, -1] | +1 | · |
| rv_cone_pctile | +0 | [-1, 1, 0, -1, 1] | -1 | · |
| vov_pctile | +1 | [-1, 1, 0, 0, 1] | -1 | · |
| stbl_growth_z | +1 | [0, 0, -1, 1, 0] | +1 | · |

## Probability calibration of the conviction layer (out-of-fold)

OOF 7d direction: **Brier 0.2492** vs base 0.248 (skill -0.005); Platt a=0.752, b=0.037. Out-of-fold: each day's P(up) is the momentum×risk cell rate fit on the OTHER folds (EB-shrunk, the live mechanism), scored vs realized. brier<base_brier = skill; Platt a≈1/b≈0 = already calibrated. Direction is a near-coin-flip, so calibrated probabilities cluster near the base rate — that is the honest result.

| prob bin | n | predicted | observed |
|---|--:|--:|--:|
| 0.5-0.6 | 3705 | 0.545 | 0.546 |
| 0.6-0.7 | 61 | 0.602 | 0.459 |

## Deflated Sharpe Ratio — GATED series (multiple-testing haircut)

**SURVIVES multiple-testing (DSR≥0.95)** — shipped variant `optimal` (GATED / live behavior).

- DSR (gated) — P(true Sharpe > 0): **0.9885**
- Observed Sharpe 1.59 ann (0.083045/day); haircut threshold SR0 0.82 ann
- N=71 trials (upper-bound, incl. override dof_cost) · T=4216d · skew=0.672 · kurt=14.442 · SR-variance: max(cross-variant dispersion, null SR-sampling proxy)
- **Effective-N haircut**: T_eff=2490.7 vs raw T=4216 (rho_sum_K20=0.3464); dsr_effN=0.9644 (dsr_legacy=0.9989). Block-bootstrap refinement: W5.

> DSR = P(true Sharpe>0) after deflating for n_trials independent configs, sample length, skew & kurtosis. n_trials is a manual UPPER-BOUND of the signal/threshold/window variants explored — overestimating is the conservative direction (de Prado). Bump vector.calibration.n_trials as you try more. The DSR statistic now uses a block-bootstrap effective sample size (T_eff) instead of raw sqrt(T-1), so autocorrelated daily returns no longer overstate confidence. GATED series (live behavior).

## Deflated Sharpe Ratio — RAW (ungated) series

**SURVIVES multiple-testing (DSR≥0.95)** — variant `optimal` (RAW / pure engine).

> Pre-gate figure (0.9965) retired as of 2026-07. This is the fresh dual-track compute. Raw series excludes midterm-blackout contamination.
- DSR (raw) — P(true Sharpe > 0): **0.9659**
- Observed Sharpe 1.42 ann; SR0 0.81 ann
- N=71 trials · T=4216d · skew=0.604 · kurt=13.142
- **Effective-N haircut**: T_eff=2507.5, dsr_effN=0.9154 (dsr_legacy=0.9938)

> DSR on the RAW (ungated) series — pure engine without override contamination. Pre-gate figure (0.9965) retired; this is the fresh dual-track compute as of 2026-07. n_trials includes override dof_cost. RAW series.

## Trial log (N7 — n_trials breakdown)

As-of 2026-07-17: **n_trials_declared=71** = n_trials_config=65 (config upper-bound) + override dof_cost (registry).
  - override `midterm_blackout`: dof_cost=6
32 signal families screened; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 10.0bps one-way.

> Point-in-time trial ledger (overwritten each run). n_trials_declared = n_trials_config (upper-bound of configs explored) + sum(dof_cost) across registered overrides. Raise n_trials_config as you try more; each new override must declare its dof_cost, which is ADDED here.

## Ensemble capstone — does combining beat the heuristic?

**KEEP-HEURISTIC — the hand-tuned composite_state is NOT beaten by the fixed-form ensemble**

Each axis oriented by its calibrated expected-fwd-return band-map (handles the U-shape a linear z can't), de-correlated in a fixed order, equal-weight combined. Promotion needs the ensemble to beat BOTH the best single signal AND the heuristic composite_state on net Sharpe in BOTH halves. Honest non-promotion = keep the simpler winner (the forecast-combination literature: equal-weight/best-single are brutal baselines on ~3 cycles).

| read | net Sharpe full | pre-2021 | post-2021 |
|---|--:|--:|--:|
| ensemble_eqw | 1.25 | 1.48 | 0.54 |
| best_single | 0.97 | 1.2 | 0.4 |
| heuristic | 1.19 | 1.48 | 0.67 |

Ensemble OOF rank-IC vs 90d return: **0.196** (best single axis = `net_liq_roc`). Per-axis IC: risk_index 0.087, net_liq_roc 0.266, vrp nan, cot_z 0.008, mvrv_z 0.062, momentum 0.147.

## Whipsaw

|                  |   changes |   whipsaws |   pct |
|:-----------------|----------:|-----------:|------:|
| momentum_state   |       180 |         36 |  20   |
| risk_regime      |       114 |         21 |  18.4 |
| structure_state  |       179 |         37 |  20.7 |
| market_mode      |        84 |         14 |  16.7 |
| alt_cycle_leader |       103 |         21 |  20.4 |