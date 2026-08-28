# Commodity conviction — calibration

Measured forward-return predictive strength per factor (Spearman, 63d & 126d), split-half @ 2013-01-01. Weight = polarity x |corr| x stability, normalized to 0.8 panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; buckets verified monotone in forward 126d return.


## Gold

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| carry | +0.183 | 0.176 | 0.122 | 0.273 | ✓ |
| liquidity | +0.153 | 0.153 | 0.086 | 0.183 | ✓ |
| inflation | -0.123 | -0.125 | -0.179 | -0.105 | ✓ |
| value | -0.110 | -0.107 | -0.101 | -0.198 | ✓ |
| cycle | +0.100 | — | — | — | · |
| trend | +0.066 | 0.167 | -0.25 | 0.268 | · |
| dollar | -0.063 | -0.057 | -0.063 | -0.045 | ✓ |
| mtf | +0.060 | — | — | — | · |
| positioning | -0.041 | -0.089 | 0.062 | -0.145 | · |
| alerts | +0.040 | — | — | — | · |
| real_rates | +0.030 | 0.066 | -0.184 | 0.21 | · |
| growth | -0.030 | -0.058 | 0.053 | -0.185 | · |

Cycle (amp 0.18, 14 legs): bull median 1012d (n=7, 95.2%); bear median 177d (n=7, 21.9%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 13 | +2.34 | 100.0 |
| SELL | 1318 | +2.66 | 64.3 |
| HOLD | 2785 | +5.11 | 65.0 |
| BUY | 1647 | +9.77 | 79.6 |
| STRONG BUY | 490 | +13.08 | 95.3 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Silver

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| value | +0.208 | 0.171 | 0.184 | 0.273 | ✓ |
| inflation | -0.135 | -0.103 | -0.095 | -0.119 | ✓ |
| carry | +0.120 | 0.086 | 0.037 | 0.205 | ✓ |
| cycle | +0.100 | — | — | — | · |
| growth | -0.090 | -0.071 | -0.006 | -0.199 | ✓ |
| risk | -0.073 | -0.046 | -0.004 | -0.072 | ✓ |
| mtf | +0.060 | — | — | — | · |
| shock | -0.052 | -0.031 | -0.01 | -0.07 | ✓ |
| real_rates | +0.051 | 0.092 | -0.122 | 0.225 | · |
| liquidity | +0.044 | 0.081 | -0.029 | 0.148 | · |
| alerts | +0.040 | — | — | — | · |
| riskoff | -0.027 | -0.053 | 0.0 | -0.17 | · |

Cycle (amp 0.35, 14 legs): bull median 631d (n=7, 150.5%); bear median 453d (n=7, 43.2%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 527 | +0.54 | 42.9 |
| SELL | 1726 | +6.57 | 52.7 |
| HOLD | 1827 | +8.05 | 56.2 |
| BUY | 1716 | +8.42 | 67.4 |
| STRONG BUY | 522 | +19.95 | 83.9 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Copper

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| risk | -0.184 | -0.155 | -0.125 | -0.207 | ✓ |
| riskoff | +0.153 | 0.138 | 0.13 | 0.145 | ✓ |
| growth | +0.145 | 0.115 | 0.042 | 0.143 | ✓ |
| real_rates | +0.107 | 0.085 | 0.055 | 0.079 | ✓ |
| structure | +0.105 | 0.086 | 0.136 | 0.014 | ✓ |
| cycle | +0.100 | — | — | — | · |
| mtf | +0.060 | — | — | — | · |
| liquidity | +0.041 | 0.093 | -0.038 | 0.228 | · |
| alerts | +0.040 | — | — | — | · |
| dollar | +0.035 | 0.062 | -0.051 | 0.173 | · |
| carry | -0.029 | -0.046 | -0.188 | 0.17 | · |

Cycle (amp 0.28, 14 legs): bull median 711d (n=7, 69.8%); bear median 258d (n=7, 35.6%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 844 | -5.45 | 39.0 |
| SELL | 1725 | +2.83 | 49.7 |
| HOLD | 2711 | +10.51 | 64.4 |
| BUY | 1081 | +9.99 | 69.9 |
| STRONG BUY | 43 | +1.33 | 39.5 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context

## Oil

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| trend | -0.141 | -0.183 | -0.39 | -0.13 | ✓ |
| growth | +0.121 | 0.158 | 0.189 | 0.099 | ✓ |
| real_rates | +0.113 | 0.155 | 0.346 | 0.028 | ✓ |
| cycle | +0.100 | — | — | — | · |
| dollar | +0.097 | 0.146 | 0.073 | 0.223 | ✓ |
| shock | -0.089 | -0.131 | -0.159 | -0.119 | ✓ |
| risk | -0.088 | -0.092 | -0.153 | -0.064 | ✓ |
| value | +0.074 | 0.089 | 0.222 | 0.025 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| structure | -0.031 | -0.031 | -0.051 | -0.03 | ✓ |
| liquidity | +0.029 | 0.103 | -0.038 | 0.225 | · |
| riskoff | +0.018 | 0.068 | -0.001 | 0.093 | · |

Cycle (amp 0.4, 18 legs): bull median 194d (n=9, 55.9%); bear median 342d (n=9, 57.3%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 870 | -7.53 | 41.3 |
| SELL | 1690 | +0.53 | 44.9 |
| HOLD | 2476 | +6.94 | 62.0 |
| BUY | 1220 | +19.62 | 77.7 |
| STRONG BUY | 152 | +2.08 | 42.8 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context
