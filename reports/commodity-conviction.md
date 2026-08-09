# Commodity conviction — calibration

Measured forward-return predictive strength per factor (Spearman, 63d & 126d), split-half @ 2013-01-01. Weight = polarity x |corr| x stability, normalized to 0.8 panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; buckets verified monotone in forward 126d return.


## Gold

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| carry | +0.184 | 0.176 | 0.122 | 0.273 | ✓ |
| liquidity | +0.157 | 0.157 | 0.086 | 0.191 | ✓ |
| inflation | -0.122 | -0.125 | -0.179 | -0.104 | ✓ |
| value | -0.107 | -0.104 | -0.101 | -0.19 | ✓ |
| cycle | +0.100 | — | — | — | · |
| trend | +0.068 | 0.172 | -0.25 | 0.28 | · |
| dollar | -0.062 | -0.054 | -0.063 | -0.041 | ✓ |
| mtf | +0.060 | — | — | — | · |
| positioning | -0.040 | -0.087 | 0.062 | -0.143 | · |
| alerts | +0.040 | — | — | — | · |
| real_rates | +0.030 | 0.067 | -0.184 | 0.212 | · |
| growth | -0.030 | -0.058 | 0.053 | -0.185 | · |

Cycle (amp 0.18, 14 legs): bull median 1012d (n=7, 95.2%); bear median 177d (n=7, 21.9%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 13 | +2.34 | 100.0 |
| SELL | 1325 | +2.54 | 63.6 |
| HOLD | 2773 | +5.24 | 65.6 |
| BUY | 1647 | +9.79 | 79.7 |
| STRONG BUY | 484 | +13.15 | 95.2 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Silver

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| value | +0.203 | 0.167 | 0.184 | 0.267 | ✓ |
| inflation | -0.133 | -0.102 | -0.095 | -0.118 | ✓ |
| carry | +0.119 | 0.086 | 0.037 | 0.205 | ✓ |
| cycle | +0.100 | — | — | — | · |
| growth | -0.089 | -0.071 | -0.006 | -0.2 | ✓ |
| risk | -0.078 | -0.05 | -0.004 | -0.08 | ✓ |
| mtf | +0.060 | — | — | — | · |
| shock | -0.055 | -0.035 | -0.01 | -0.077 | ✓ |
| real_rates | +0.050 | 0.093 | -0.122 | 0.227 | · |
| liquidity | +0.046 | 0.085 | -0.029 | 0.156 | · |
| alerts | +0.040 | — | — | — | · |
| riskoff | -0.027 | -0.053 | 0.0 | -0.17 | · |

Cycle (amp 0.35, 14 legs): bull median 631d (n=7, 150.5%); bear median 453d (n=7, 43.2%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 516 | +0.64 | 42.6 |
| SELL | 1749 | +6.81 | 53.0 |
| HOLD | 1858 | +8.02 | 57.2 |
| BUY | 1694 | +8.43 | 67.1 |
| STRONG BUY | 490 | +20.45 | 84.1 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Copper

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| risk | -0.184 | -0.154 | -0.125 | -0.205 | ✓ |
| riskoff | +0.154 | 0.138 | 0.13 | 0.145 | ✓ |
| growth | +0.146 | 0.115 | 0.042 | 0.143 | ✓ |
| real_rates | +0.107 | 0.084 | 0.055 | 0.078 | ✓ |
| structure | +0.105 | 0.086 | 0.136 | 0.012 | ✓ |
| cycle | +0.100 | — | — | — | · |
| mtf | +0.060 | — | — | — | · |
| liquidity | +0.040 | 0.092 | -0.038 | 0.226 | · |
| alerts | +0.040 | — | — | — | · |
| dollar | +0.035 | 0.061 | -0.051 | 0.171 | · |
| carry | -0.029 | -0.046 | -0.188 | 0.171 | · |

Cycle (amp 0.28, 14 legs): bull median 711d (n=7, 69.8%); bear median 258d (n=7, 35.6%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 845 | -5.40 | 39.1 |
| SELL | 1719 | +2.86 | 49.7 |
| HOLD | 2704 | +10.48 | 64.2 |
| BUY | 1082 | +9.93 | 69.7 |
| STRONG BUY | 43 | +1.33 | 39.5 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context

## Oil

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| trend | -0.140 | -0.182 | -0.39 | -0.129 | ✓ |
| growth | +0.122 | 0.158 | 0.189 | 0.098 | ✓ |
| real_rates | +0.112 | 0.155 | 0.346 | 0.028 | ✓ |
| cycle | +0.100 | — | — | — | · |
| dollar | +0.096 | 0.145 | 0.073 | 0.221 | ✓ |
| shock | -0.090 | -0.134 | -0.159 | -0.123 | ✓ |
| risk | -0.089 | -0.092 | -0.153 | -0.066 | ✓ |
| value | +0.073 | 0.085 | 0.222 | 0.02 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| structure | -0.033 | -0.033 | -0.051 | -0.034 | ✓ |
| liquidity | +0.028 | 0.102 | -0.038 | 0.222 | · |
| riskoff | +0.018 | 0.068 | -0.001 | 0.093 | · |

Cycle (amp 0.4, 18 legs): bull median 194d (n=9, 55.9%); bear median 342d (n=9, 57.3%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 878 | -7.62 | 40.8 |
| SELL | 1680 | +0.54 | 45.2 |
| HOLD | 2467 | +7.11 | 62.0 |
| BUY | 1221 | +19.26 | 77.4 |
| STRONG BUY | 151 | +1.57 | 42.4 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context
