# Commodity conviction — calibration

Measured forward-return predictive strength per factor (Spearman, 63d & 126d), split-half @ 2013-01-01. Weight = polarity x |corr| x stability, normalized to 0.8 panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; buckets verified monotone in forward 126d return.


## Gold

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| carry | +0.187 | 0.186 | 0.122 | 0.29 | ✓ |
| liquidity | +0.168 | 0.163 | 0.084 | 0.202 | ✓ |
| inflation | -0.120 | -0.127 | -0.179 | -0.106 | ✓ |
| cycle | +0.100 | — | — | — | · |
| value | -0.092 | -0.088 | -0.101 | -0.165 | ✓ |
| trend | +0.078 | 0.194 | -0.25 | 0.323 | · |
| dollar | -0.061 | -0.051 | -0.063 | -0.034 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| positioning | -0.036 | -0.081 | 0.078 | -0.147 | · |
| growth | -0.032 | -0.066 | 0.053 | -0.2 | · |
| real_rates | +0.027 | 0.059 | -0.184 | 0.204 | · |

Cycle (amp 0.18, 14 legs): bull median 1012d (n=7, 95.2%); bear median 177d (n=7, 21.9%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 925 | +3.15 | 67.4 |
| SELL | 1552 | +3.66 | 62.0 |
| HOLD | 1237 | +5.89 | 66.1 |
| BUY | 1554 | +8.40 | 77.0 |
| STRONG BUY | 930 | +12.88 | 90.6 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Silver

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| value | +0.196 | 0.155 | 0.184 | 0.246 | ✓ |
| inflation | -0.136 | -0.103 | -0.095 | -0.119 | ✓ |
| carry | +0.127 | 0.094 | 0.037 | 0.22 | ✓ |
| cycle | +0.100 | — | — | — | · |
| growth | -0.098 | -0.079 | -0.006 | -0.215 | ✓ |
| risk | -0.092 | -0.054 | -0.0 | -0.091 | ✓ |
| mtf | +0.060 | — | — | — | · |
| liquidity | +0.054 | 0.091 | -0.029 | 0.167 | · |
| real_rates | +0.050 | 0.087 | -0.122 | 0.222 | · |
| shock | -0.049 | -0.023 | -0.01 | -0.059 | ✓ |
| alerts | +0.040 | — | — | — | · |

Cycle (amp 0.35, 14 legs): bull median 631d (n=7, 150.5%); bear median 453d (n=7, 43.2%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 939 | +3.62 | 45.0 |
| SELL | 1562 | +7.01 | 53.7 |
| HOLD | 1250 | +8.70 | 58.0 |
| BUY | 1566 | +8.49 | 68.3 |
| STRONG BUY | 940 | +14.82 | 74.0 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Copper

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| risk | -0.196 | -0.154 | -0.123 | -0.205 | ✓ |
| riskoff | +0.165 | 0.136 | 0.13 | 0.138 | ✓ |
| growth | +0.158 | 0.117 | 0.042 | 0.148 | ✓ |
| real_rates | +0.118 | 0.087 | 0.055 | 0.085 | ✓ |
| cycle | +0.100 | — | — | — | · |
| mtf | +0.060 | — | — | — | · |
| structure | +0.050 | 0.083 | 0.136 | -0.001 | · |
| liquidity | +0.044 | 0.094 | -0.031 | 0.221 | · |
| alerts | +0.040 | — | — | — | · |
| dollar | +0.038 | 0.061 | -0.051 | 0.17 | · |
| carry | -0.031 | -0.049 | -0.188 | 0.166 | · |

Cycle (amp 0.28, 14 legs): bull median 711d (n=7, 69.8%); bear median 258d (n=7, 35.6%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 950 | -7.31 | 36.2 |
| SELL | 1582 | +5.66 | 50.7 |
| HOLD | 1283 | +7.54 | 58.1 |
| BUY | 1583 | +11.86 | 71.1 |
| STRONG BUY | 951 | +9.03 | 66.4 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context

## Oil

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| trend | -0.132 | -0.175 | -0.39 | -0.117 | ✓ |
| growth | +0.128 | 0.164 | 0.189 | 0.108 | ✓ |
| real_rates | +0.114 | 0.163 | 0.346 | 0.04 | ✓ |
| cycle | +0.100 | — | — | — | · |
| dollar | +0.093 | 0.144 | 0.073 | 0.221 | ✓ |
| risk | -0.092 | -0.094 | -0.156 | -0.07 | ✓ |
| shock | -0.088 | -0.135 | -0.159 | -0.124 | ✓ |
| value | +0.071 | 0.078 | 0.222 | 0.005 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| structure | -0.031 | -0.034 | -0.051 | -0.037 | ✓ |
| liquidity | +0.030 | 0.101 | -0.03 | 0.217 | · |
| positioning | +0.019 | 0.021 | 0.127 | 0.012 | ✓ |

Cycle (amp 0.35, 18 legs): bull median 194d (n=9, 55.9%); bear median 342d (n=9, 57.3%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 960 | -7.28 | 40.1 |
| SELL | 1585 | -0.02 | 45.3 |
| HOLD | 1264 | +4.19 | 57.4 |
| BUY | 1590 | +11.32 | 67.9 |
| STRONG BUY | 954 | +18.85 | 73.7 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES
