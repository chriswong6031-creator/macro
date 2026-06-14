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
| bfi | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| mvrv_z | **EXTREMES — low <0: +40.5%/90d 71.9% hit (n=356) [BOTTOM]; high >3.5: +27.1%/90d 57.8% hit (n=277) [weak]** | 0 | 0 | 0 | -1 |
| nupl | **EXTREMES — low <0: +28.0%/90d 66.5% hit (n=603) [weak]; high >.65: +25.8%/90d 58.5% hit (n=265) [weak]** | 0 | 0 | -1 | -1 |
| mayer | **EXTREMES — low <0.8: +12.0%/90d 49.9% hit (n=625) [weak]; high >2.4: -13.9%/90d 33.9% hit (n=62) [TOP]** | 1 | 1 | 0 | -1 |
| puell | **EXTREMES — low <0.5: +15.8%/90d 59.5% hit (n=153) [weak]** | 1 | 1 | 0 | -1 |
| sth_cb_ratio | **EXTREMES — low <-10%: -0.6%/90d 35.3% hit (n=304) [weak]** | 0 | 0 | 0 | 1 |
| hash_ribbon_capit | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| dvol | **EXTREMES — low <40: +8.4%/90d 46.8% hit (n=220) [weak]; high >90: +15.8%/90d 71.4% hit (n=168) [weak]** | 0 | 0 | 0 | -1 |
| vrp | **EXTREMES — low <-5: +17.2%/90d 77.8% hit (n=203) [weak]; high >15: +7.2%/90d 53.9% hit (n=484) [TOP]** | -1 | 0 | -1 | -1 |
| leverage_stress | **EXTREMES — low 0-25: +12.7%/90d 62.0% hit (n=639) [weak]** | 0 | 0 | 0 | -1 |
| funding_z | **EXTREMES — low <-1: +18.5%/90d 70.3% hit (n=151) [weak]** | 0 | 0 | 0 | -1 |
| oi_price_divergence | **EXTREMES — low <-10%: +14.8%/90d 70.4% hit (n=159) [weak]** | -1 | 0 | -1 | -1 |
| net_liq_roc | **DIRECTIONAL (one half weak)** | 1 | 1 | 0 | 1 |
| macro_score | **CONFIRMED** | 1 | 1 | 1 | 1 |
| coinbase_premium_ema | **EXTREMES — low <-.3: +16.5%/90d 64.8% hit (n=295) [weak]; high >1.5: -5.9%/90d 35.5% hit (n=421) [TOP]** | -1 | 0 | -1 | 1 |
| ssr_oscillator | **CONTEXT-ONLY** | 0 | 0 | 0 | 1 |
| mpi | **INVERTED** | 1 | 0 | 1 | -1 |
| reserve_risk | **EXTREMES — low <.0015: +18.6%/90d 68.6% hit (n=974) [weak]; high >.02: -42.5%/90d 4.2% hit (n=48) [TOP]** | 1 | 0 | -1 | -1 |
| impulse | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |
| cycle_pct | **DIRECTIONAL (one half weak)** | -1 | -1 | 0 | -1 |
| cot_z | **EXTREMES — low <-1.5: +13.2%/90d 47.8% hit (n=224) [weak]; high >1.5: -5.8%/90d 35.3% hit (n=593) [TOP]** | -1 | 0 | -1 | -1 |
| corr_spx | **CONFIRMED** | -1 | -1 | -1 | -1 |
| vdd_multiple | **EXTREMES — low <.5: +8.0%/90d 43.6% hit (n=774) [weak]; high >2.9: +35.2%/90d 59.1% hit (n=154) [weak]** | 1 | 1 | 0 | -1 |
| global_m2_yoy | **DIRECTIONAL (full only)** | 1 | 0 | -1 | 1 |
| rv_cone_pctile | **EXTREMES — low 0-25: +24.8%/90d 70.6% hit (n=1206) [weak]; high 75-100: +30.3%/90d 64.0% hit (n=831) [weak]** | 0 | 0 | 0 | -1 |
| vov_pctile | **EXTREMES — low 0-25: +12.5%/90d 53.0% hit (n=1159) [weak]; high 75-100: +37.7%/90d 75.5% hit (n=826) [weak]** | 1 | 1 | 0 | -1 |
| stbl_growth_z | **DIRECTIONAL (one half weak)** | 1 | 0 | 1 | 1 |

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

### mvrv_z — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     |  356 |     58.7 |      1.86 |      68   |       9.71 |      71.9 |      40.55 |
| 0-1    | 1195 |     53.7 |      0.97 |      57.1 |       4.18 |      51   |       5.25 |
| 1-2    | 1148 |     52.4 |      0.72 |      55.6 |       3.95 |      67.7 |      23.48 |
| 2-3.5  |  948 |     56.5 |      1.84 |      56.9 |      10.2  |      59.8 |      36.62 |
| >3.5   |  277 |     59.9 |      4.67 |      58.1 |      14.54 |      57.8 |      27.15 |

### nupl — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     |  603 |     56.7 |      1.07 |      63.2 |       6.29 |      66.5 |      28.01 |
| 0-.25  |  617 |     58   |      1.9  |      67.7 |       7.2  |      58.3 |      10.69 |
| .25-.5 | 1670 |     52.9 |      0.73 |      53.4 |       2.8  |      60.7 |      17.07 |
| .5-.65 | 1027 |     53.7 |      1.44 |      54.1 |      10.19 |      58   |      33.38 |
| >.65   |  265 |     57.4 |      4.19 |      58.5 |      13.03 |      58.5 |      25.77 |

### mayer — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.8    |  625 |     54.1 |      0.95 |      61.5 |       4.08 |      49.9 |      12.03 |
| 0.8-1   |  948 |     51.6 |      0    |      54   |       2.32 |      53.3 |      11.5  |
| 1-1.5   | 1888 |     55.7 |      1.46 |      57.9 |       6.15 |      68.3 |      24.11 |
| 1.5-2.4 |  566 |     58.7 |      3.82 |      60.6 |      18.69 |      62.5 |      53.36 |
| >2.4    |   62 |     43.5 |      2.27 |      43.5 |      -1.92 |      33.9 |     -13.95 |

### puell — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.5   |  153 |     54.9 |      1.22 |      64.7 |       4.09 |      59.5 |      15.76 |
| 0.5-1  | 1681 |     54.1 |      0.64 |      59.2 |       4.41 |      62.8 |      21.35 |
| 1-2    | 1855 |     55.1 |      1.7  |      55.6 |       6.87 |      60.1 |      20.23 |
| 2-4    |  397 |     54.7 |      2.41 |      57.4 |      14.94 |      58.7 |      47.89 |
| >4     |   23 |     56.5 |     10.54 |      34.8 |      -3.22 |      17.4 |     -33.4  |

### sth_cb_ratio — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-10%  | 304 |     54.2 |      0.6  |      58.9 |       1.81 |      35.3 |      -0.55 |
| -10-0% | 341 |     51.3 |     -0.02 |      59.6 |       3.34 |      74   |      25.59 |
| 0-20%  | 621 |     53.1 |      1.17 |      52.6 |       4.53 |      58.8 |       9.29 |
| 20-50% | 196 |     52   |      0.97 |      55.6 |       3.69 |      68.9 |      13.76 |
| >50%   |   0 |    nan   |    nan    |     nan   |     nan    |     nan   |     nan    |

### hash_ribbon_capit — forward returns by band (full sample)

| band         |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| normal       | 3445 |     55   |      1.57 |      58.4 |       7.27 |      60.2 |      23.42 |
| capitulation |  737 |     53.1 |      0.31 |      52.6 |       2.45 |      61.4 |      17.48 |

### dvol — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <40    | 220 |     48.2 |     -0.67 |      44.1 |       0.27 |      46.8 |       8.4  |
| 40-55  | 640 |     52   |      0.96 |      59.1 |       4.55 |      65   |      12.89 |
| 55-70  | 479 |     54.1 |      0.47 |      53.9 |       2.88 |      63   |      10.77 |
| 70-90  | 401 |     48.9 |      0.01 |      38.4 |      -3.8  |      18.7 |     -12.64 |
| >90    | 168 |     47   |     -0.28 |      47   |       2.06 |      71.4 |      15.84 |

### vrp — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-5    | 203 |     57.6 |      1.05 |      61.6 |       3.81 |      77.8 |      17.23 |
| -5-0   | 160 |     61.3 |      2.06 |      63.7 |       5.58 |      50.6 |       9.07 |
| 0-5    | 349 |     49   |      0.09 |      53.6 |       2.37 |      38.8 |       2.78 |
| 5-15   | 712 |     46.4 |     -0.5  |      47.1 |      -0.13 |      51.6 |       3.85 |
| >15    | 484 |     52.9 |      0.88 |      44.6 |       1.45 |      53.9 |       7.2  |

### leverage_stress — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 639 |     53.6 |      1.29 |      58   |       4.27 |      62   |      12.65 |
| 25-50  | 672 |     51.9 |      0.3  |      53.1 |       2.65 |      59.7 |      12.53 |
| 50-75  | 129 |     52.7 |      0.65 |      55.2 |       4.78 |      44   |       3.29 |
| 75-100 |   8 |     75   |      2.65 |     100   |       6.79 |      62.5 |       2.66 |

### funding_z — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    | 151 |     60.9 |      1.25 |      64.2 |       3.15 |      70.3 |      18.46 |
| -1-0   | 393 |     53.2 |      0.45 |      55.8 |       1.77 |      61.5 |       9.77 |
| 0-1    | 325 |     53.7 |      1.25 |      60.6 |       7.53 |      54.3 |      13.33 |
| 1-2    | 104 |     49   |     -0.43 |      48.9 |       3.55 |      42.2 |       4.49 |
| >2     |  39 |     71.8 |      2.69 |      59   |       3.1  |      79.5 |      24.32 |

### oi_price_divergence — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-10%  | 159 |     58.5 |      1.04 |      58.5 |       0.82 |      70.4 |      14.78 |
| -10-0% | 511 |     53.8 |      1.31 |      60.3 |       5.26 |      65   |      14.15 |
| 0-10%  | 621 |     51.9 |      0.56 |      52.3 |       3.67 |      54.9 |      10.13 |
| 10-25% | 151 |     49   |     -0.23 |      53.4 |       0.93 |      47.9 |       7.34 |
| >25%   |   6 |     16.7 |     -3.5  |       0   |      -5.7  |      33.3 |      -4.16 |

### net_liq_roc — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-2%   | 1160 |     53.6 |      0.84 |      54.7 |       2.58 |      52.2 |      11.09 |
| -2-0%  |  836 |     54.2 |      1.6  |      57.3 |       7.99 |      63   |      19.38 |
| 0-2%   |  770 |     52.9 |      1.24 |      58.5 |       6.44 |      67.4 |      26.84 |
| 2-5%   |  641 |     61.9 |      2.56 |      63.6 |      10.97 |      77.4 |      45.26 |
| >5%    |  469 |     58.8 |      2.43 |      69.1 |      16.02 |      72.3 |      47.71 |

### macro_score — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.3   | 604 |     51.5 |     -0.02 |      52.3 |      -0.12 |      40.6 |       1.4  |
| -.3-.1 | 817 |     53.9 |      1.22 |      59.5 |       5.16 |      60   |      17.52 |
| -.1-.1 | 942 |     57.2 |      1.82 |      57.2 |       7.94 |      57   |      20.67 |
| .1-.3  | 938 |     54.1 |      1.66 |      58.4 |       7.23 |      62.2 |      17.77 |
| >.3    | 881 |     55.5 |      1.57 |      58.2 |       9.7  |      76.4 |      48.78 |

### coinbase_premium_ema — forward returns by band (full sample)

| band   |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.3   | 295 |     46.1 |      0.1  |      60   |       4.81 |      64.8 |      16.52 |
| -.3-0  | 223 |     47.9 |     -0.45 |      50.7 |       3.1  |      62.1 |      16.81 |
| 0-.5   | 260 |     57.1 |      1.71 |      55.4 |       5.39 |      70.5 |      19.12 |
| .5-1.5 | 263 |     60.1 |      1.98 |      65.4 |       7.09 |      70.7 |      18.39 |
| >1.5   | 421 |     52.7 |      0.45 |      49.8 |      -0.32 |      35.5 |      -5.88 |

### ssr_oscillator — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |  484 |     52.3 |      1.11 |      50.4 |       4.16 |      55.6 |       9.9  |
| -1-.3  |  316 |     52.8 |      0.94 |      70.6 |       8.91 |      73.7 |      17.39 |
| -.3-.5 |  516 |     55.2 |      1.31 |      47.9 |       0.8  |      47.3 |       3.5  |
| .5-1.5 | 1372 |     52.1 |      0.64 |      51.8 |       3.83 |      54.4 |      22.51 |
| >1.5   |  342 |     48.5 |      0.08 |      56.8 |       4.09 |      43   |       3.69 |

### mpi — forward returns by band (full sample)

| band    |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0.7    | 323 |     49.7 |      0.07 |      56.7 |       1.59 |      58.8 |       8.84 |
| 0.7-1   | 255 |     55.7 |      0.48 |      56.1 |       3.2  |      67.1 |      15.14 |
| 1-1.5   | 370 |     51.6 |      0.78 |      55.7 |       3.83 |      63.5 |      13.56 |
| 1.5-2.5 | 255 |     58.8 |      1.95 |      64.3 |       8.59 |      69.4 |      19.37 |
| >2.5    | 140 |     52.9 |      1.35 |      46.4 |       2.13 |      60   |      11    |

### reserve_risk — forward returns by band (full sample)

| band        |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:------------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <.0015      |  974 |     56   |      1.49 |      63.2 |       6.23 |      68.6 |      18.62 |
| .0015-.0025 | 1685 |     56.9 |      1.18 |      63   |       6.11 |      69.8 |      25.51 |
| .0025-.005  |  940 |     51.4 |      1.39 |      47.7 |       5.99 |      46   |      17.52 |
| .005-.02    |  535 |     52.9 |      1.76 |      51   |      11.12 |      47.7 |      33.53 |
| >.02        |   48 |     33.3 |     -1.14 |      10.4 |     -22.01 |       4.2 |     -42.55 |

### impulse — forward returns by band (full sample)

| band     |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-.5     |  372 |     55.7 |      1.5  |      53.2 |       5.15 |      61.1 |      23.43 |
| -.5--.15 |  602 |     51.6 |      0.46 |      55.7 |       7.2  |      59.1 |      19.99 |
| -.15-.15 | 2038 |     52.7 |      0.62 |      55.4 |       4.57 |      58.6 |      18.63 |
| .15-.5   |  576 |     59.2 |      2.36 |      62.3 |       8.85 |      61.5 |      27.11 |
| >.5      |  594 |     59.8 |      3.68 |      63.8 |      10.44 |      66.2 |      32.64 |

### cycle_pct — forward returns by band (full sample)

| band     |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| accum    |  963 |     61.1 |      2.76 |      70.4 |      13.26 |      80.6 |      47.86 |
| markup   |  876 |     52.6 |      1.48 |      48.6 |       6.58 |      53.7 |      22.24 |
| markdown | 1245 |     48.6 |     -0.54 |      48.6 |      -0.72 |      42.7 |       5.09 |
| recovery | 1098 |     57.6 |      2.13 |      62.8 |       8.23 |      66.7 |      18.54 |
| late     |    0 |    nan   |    nan    |     nan   |     nan    |     nan   |     nan    |

### cot_z — forward returns by band (full sample)

| band     |   n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:---------|----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1.5    | 224 |     50   |      0.23 |      51.3 |       5.29 |      47.8 |      13.25 |
| -1.5--.5 | 655 |     60.9 |      3.36 |      71.5 |      14.14 |      77.9 |      41.72 |
| -.5-.5   | 742 |     56.3 |      1.34 |      53.9 |       3.98 |      61.6 |      18.82 |
| .5-1.5   | 592 |     47.3 |      0.12 |      49.1 |       1.61 |      54.2 |       9.73 |
| >1.5     | 593 |     44.9 |     -1.09 |      45   |      -3.15 |      35.3 |      -5.77 |

### corr_spx — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <0     | 1034 |     56.1 |      1.78 |      57   |       7.01 |      61.4 |      29.23 |
| 0-.2   | 1208 |     57.4 |      2.18 |      64.5 |      12.1  |      69.2 |      32.64 |
| .2-.4  | 1004 |     53.1 |      0.62 |      49.2 |       2    |      56.2 |      10.94 |
| >.4    |  936 |     51.3 |      0.57 |      57.6 |       3.11 |      51.5 |      13.18 |

### vdd_multiple — forward returns by band (full sample)

| band    |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:--------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <.5     |  774 |     55.5 |      0.51 |      55.2 |       3.31 |      43.6 |       7.97 |
| .5-.87  | 1142 |     50.5 |      0.62 |      63.9 |       5.87 |      65.4 |      18.36 |
| .87-1.4 | 1200 |     56.1 |      1.3  |      48.6 |       1.99 |      64.7 |      18.77 |
| 1.4-2.9 |  912 |     57.8 |      2.77 |      65.6 |      15.92 |      61.3 |      41.06 |
| >2.9    |  154 |     51.9 |      2.86 |      40.3 |       4.02 |      59.1 |      35.2  |

### global_m2_yoy — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <5.5   |  519 |     53.4 |      1.24 |      60.7 |       6.05 |      72.6 |      23.39 |
| 5.5-7  | 1216 |     53   |      0.9  |      52.9 |       3.21 |      48.3 |       7.21 |
| 7-8.5  |  742 |     54.3 |      2.06 |      56.3 |      11.31 |      61.8 |      41.14 |
| 8.5-11 | 1310 |     54   |      0.54 |      56.5 |       3.53 |      59.7 |      15.75 |
| >11    |  395 |     64.6 |      4.23 |      72.2 |      17.65 |      80.8 |      57.97 |

### rv_cone_pctile — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 1206 |     54.9 |      1.2  |      59.9 |       5.89 |      70.6 |      24.84 |
| 25-50  | 1054 |     53.1 |      0.74 |      49.5 |       2.31 |      51.1 |      16.18 |
| 50-75  |  895 |     56.4 |      1.44 |      57.5 |       8.14 |      56.3 |      23.9  |
| 75-100 |  831 |     54.3 |      2.48 |      63.4 |      11.39 |      64   |      30.26 |

### vov_pctile — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| 0-25   | 1159 |     55.1 |      1.31 |      51.9 |       3.48 |      53   |      12.54 |
| 25-50  |  994 |     52.6 |      0.86 |      57.1 |       6.92 |      56.1 |      20.43 |
| 50-75  |  978 |     55.1 |      1.63 |      60   |       6.64 |      63   |      28.12 |
| 75-100 |  826 |     56.8 |      2.04 |      64.4 |      11.4  |      75.5 |      37.7  |

### stbl_growth_z — forward returns by band (full sample)

| band   |    n |   hit_7d |   mean_7d |   hit_30d |   mean_30d |   hit_90d |   mean_90d |
|:-------|-----:|---------:|----------:|----------:|-----------:|----------:|-----------:|
| <-1    |  372 |     43.3 |     -1.23 |      39.7 |      -3    |      41.9 |       0.76 |
| -1-0   | 1558 |     53.3 |      0.95 |      54.4 |       4.45 |      55.5 |      17.27 |
| 0-1    |  620 |     49.5 |      0.84 |      51.1 |       4.01 |      55.9 |      16.3  |
| 1-2    |  228 |     72.8 |      4.22 |      78.1 |      14.14 |      75.9 |      23.38 |
| >2     |  162 |     51.2 |      0.65 |      60.5 |       5.47 |      62.3 |      19.55 |

## Allocation backtest vs HODL (NET of 10.0bps one-way cost)

`cagr` is net of transaction cost (the honest headline); `cagr_gross` and `cost_drag_pp` show the cost bite, `turnover_annual` the one-way turnover/yr driving it.

|              |   cagr |   cagr_gross |   cost_drag_pp |   hodl_cagr |   sharpe |   hodl_sharpe |   sortino |   hodl_sortino |   maxdd |   hodl_maxdd |   time_in_market |   turnover_annual |   final_vs_hodl |
|:-------------|-------:|-------------:|---------------:|------------:|---------:|--------------:|----------:|---------------:|--------:|-------------:|-----------------:|------------------:|----------------:|
| conservative |   49.5 |         51.4 |            1.9 |          59 |     1.35 |          1.03 |      1.33 |           1.37 |   -29.4 |        -83.8 |             48.8 |              12.4 |            0.49 |
| moderate     |   65.5 |         67.4 |            1.9 |          59 |     1.44 |          1.03 |      1.67 |           1.37 |   -39   |        -83.8 |             68.1 |              11.4 |            1.58 |
| aggressive   |   62.7 |         64.4 |            1.7 |          59 |     1.28 |          1.03 |      1.53 |           1.37 |   -48.4 |        -83.8 |             75.2 |              10.3 |            1.3  |
| optimal      |   64.2 |         66.1 |            1.9 |          59 |     1.41 |          1.03 |      1.67 |           1.37 |   -42.8 |        -83.8 |             70.2 |              11.4 |            1.44 |

**Block-bootstrap 95% CI** [optimal, 5000 resamples, 21d blocks]: Sharpe **1.42** [0.79, 2.03] · MaxDD -47.4% [-34.3, -68.5] · P(Sharpe>0) 1.0. Circular block bootstrap (21d blocks) of the NET daily strategy returns → 95% CI [2.5, 50, 97.5]. sharpe_gt0_prob = bootstrap P(Sharpe>0). Pairs with the Deflated-Sharpe haircut: DSR deflates the mean, this bounds the variance.

## Purged walk-forward CV (stability gate)

6/30 signals **robust** under 5 embargoed folds (90d embargo = max horizon). Purged + embargoed walk-forward CV (embargo = max forward horizon) replaces the single split_date's leaky boundary. 'robust' = full-sample sign matches `want`, no fold flips, all-but-one folds agree. Stricter than pre/post; both are reported.

| Signal | full | folds | want | robust |
|---|--:|---|--:|:-:|
| risk_index | -1 | [-1, -1, -1, -1, 0] | -1 | ✅ |
| momentum | +1 | [0, 1, 1, 1, -1] | +1 | · |
| structure | +1 | [-1, 1, 1, 1, 0] | +1 | · |
| risk_oscillator | -1 | [-1, -1, -1, -1, 1] | -1 | · |
| bfi | +1 | [-1, 0, 0, 1, -1] | +1 | · |
| mvrv_z | +0 | [0, 0, 0, -1, 0] | -1 | · |
| nupl | +0 | [1, 0, 0, -1, 0] | -1 | · |
| mayer | +1 | [0, 1, 0, 1, 0] | -1 | · |
| puell | +1 | [0, 1, -1, 0, 0] | -1 | · |
| sth_cb_ratio | +0 | [0, 0, 0, 0, 0] | +1 | · |
| dvol | +0 | [0, 0, 0, -1, 1] | -1 | · |
| vrp | -1 | [0, 0, 0, -1, 0] | -1 | ✅ |
| leverage_stress | +0 | [0, 0, 0, 0, 1] | -1 | · |
| funding_z | +0 | [0, 0, 0, 0, -1] | -1 | · |
| oi_price_divergence | -1 | [0, 0, 0, 0, 0] | -1 | · |
| net_liq_roc | +1 | [1, 1, 0, 1, 0] | +1 | ✅ |
| macro_score | +1 | [1, 1, -1, 1, 1] | +1 | · |
| coinbase_premium_ema | -1 | [0, 0, 0, 0, -1] | +1 | · |
| ssr_oscillator | +0 | [0, 0, 0, 0, 0] | +1 | · |
| mpi | +1 | [0, 0, 0, -1, -1] | -1 | · |
| reserve_risk | +1 | [0, 0, -1, 0, 0] | -1 | · |
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

OOF 7d direction: **Brier 0.25** vs base 0.2483 (skill -0.007); Platt a=0.694, b=0.026. Out-of-fold: each day's P(up) is the momentum×risk cell rate fit on the OTHER folds (EB-shrunk, the live mechanism), scored vs realized. brier<base_brier = skill; Platt a≈1/b≈0 = already calibrated. Direction is a near-coin-flip, so calibrated probabilities cluster near the base rate — that is the honest result.

| prob bin | n | predicted | observed |
|---|--:|--:|--:|
| 0.5-0.6 | 3649 | 0.547 | 0.543 |
| 0.6-0.7 | 83 | 0.606 | 0.446 |

## Signal collinearity (orthogonalize before any blend)

19 signals with **VIF≥5** (redundant): risk_index, momentum, structure, bfi, mvrv_z, nupl, mayer, puell, sth_cb_ratio, dvol, vrp, ssr_oscillator, reserve_risk, cycle_pct, cot_z, corr_spx, global_m2_yoy, rv_cone_pctile, stbl_growth_z. VIF>5 ≈ redundant (its forward info is already carried by other signals); the high-corr pairs name the cluster. This MEASURES the independent contribution the one-representative-per-axis rule asserts — orthogonalize before any blend.

| a | b | \|corr\| |
|---|---|--:|
| mvrv_z | nupl | 0.94 |
| mayer | sth_cb_ratio | 0.94 |
| mvrv_z | reserve_risk | 0.92 |
| mayer | ssr_oscillator | 0.9 |
| sth_cb_ratio | ssr_oscillator | 0.9 |
| nupl | reserve_risk | 0.87 |
| momentum | sth_cb_ratio | 0.84 |
| risk_index | momentum | 0.8 |
| ssr_oscillator | stbl_growth_z | 0.8 |
| momentum | structure | 0.78 |

## Deflated Sharpe Ratio (multiple-testing haircut)

**SURVIVES multiple-testing (DSR≥0.95)** — shipped variant `optimal`.

- DSR — P(true Sharpe > 0) after deflation: **0.9947**
- Observed Sharpe 1.41 ann (0.073793/day); haircut threshold SR0 0.66 ann
- N=50 trials (upper-bound) · T=4182d · skew=0.553 · kurt=12.442 · SR-variance: max(cross-variant dispersion, null SR-sampling proxy)

> DSR = P(true Sharpe>0) after deflating for n_trials independent configs, sample length, skew & kurtosis. n_trials is a manual UPPER-BOUND of the signal/threshold/window variants explored — overestimating is the conservative direction (de Prado). Bump vector.calibration.n_trials as you try more.

## Trial log

As-of 2026-06-13: **50** declared independent trials (upper-bound); 31 signal families screened; allocation variants: conservative, moderate, aggressive, optimal; transaction cost 10.0bps one-way.

## Whipsaw

|                  |   changes |   whipsaws |   pct |
|:-----------------|----------:|-----------:|------:|
| momentum_state   |       180 |         36 |  20   |
| risk_regime      |       126 |         25 |  19.8 |
| structure_state  |       178 |         36 |  20.2 |
| market_mode      |        86 |         14 |  16.3 |
| alt_cycle_leader |       102 |         21 |  20.6 |