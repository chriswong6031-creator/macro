# Commodity conviction — calibration

Measured forward-return predictive strength per factor (Spearman, 63d & 126d), split-half @ 2013-01-01. Weight = polarity x |corr| x stability, normalized to 0.8 panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; buckets verified monotone in forward 126d return.


## Gold

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| carry | +0.184 | 0.177 | 0.122 | 0.275 | ✓ |
| liquidity | +0.151 | 0.149 | 0.086 | 0.175 | ✓ |
| inflation | -0.125 | -0.128 | -0.179 | -0.109 | ✓ |
| value | -0.112 | -0.111 | -0.101 | -0.204 | ✓ |
| cycle | +0.100 | — | — | — | · |
| trend | +0.064 | 0.161 | -0.25 | 0.256 | · |
| dollar | -0.063 | -0.056 | -0.063 | -0.045 | ✓ |
| mtf | +0.060 | — | — | — | · |
| positioning | -0.041 | -0.09 | 0.062 | -0.146 | · |
| alerts | +0.040 | — | — | — | · |
| growth | -0.030 | -0.057 | 0.053 | -0.184 | · |
| real_rates | +0.030 | 0.065 | -0.184 | 0.207 | · |

Cycle (amp 0.18, 14 legs): bull median 1012d (n=7, 95.2%); bear median 177d (n=7, 21.9%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 14 | +2.48 | 100.0 |
| SELL | 1322 | +2.69 | 64.4 |
| HOLD | 2785 | +5.06 | 64.7 |
| BUY | 1654 | +9.72 | 79.5 |
| STRONG BUY | 490 | +13.02 | 95.1 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Silver

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| value | +0.211 | 0.174 | 0.184 | 0.279 | ✓ |
| inflation | -0.136 | -0.105 | -0.095 | -0.123 | ✓ |
| carry | +0.122 | 0.088 | 0.037 | 0.209 | ✓ |
| cycle | +0.100 | — | — | — | · |
| growth | -0.090 | -0.07 | -0.006 | -0.198 | ✓ |
| risk | -0.069 | -0.042 | -0.004 | -0.064 | ✓ |
| mtf | +0.060 | — | — | — | · |
| shock | -0.053 | -0.033 | -0.01 | -0.073 | ✓ |
| real_rates | +0.051 | 0.091 | -0.122 | 0.223 | · |
| liquidity | +0.043 | 0.077 | -0.029 | 0.14 | · |
| alerts | +0.040 | — | — | — | · |
| riskoff | -0.026 | -0.05 | 0.0 | -0.166 | · |

Cycle (amp 0.35, 14 legs): bull median 631d (n=7, 150.5%); bear median 453d (n=7, 43.2%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 535 | +0.63 | 43.4 |
| SELL | 1709 | +6.35 | 52.1 |
| HOLD | 1812 | +8.07 | 56.0 |
| BUY | 1729 | +8.36 | 67.3 |
| STRONG BUY | 545 | +19.65 | 83.9 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Copper

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| risk | -0.186 | -0.157 | -0.125 | -0.211 | ✓ |
| riskoff | +0.152 | 0.136 | 0.13 | 0.142 | ✓ |
| growth | +0.145 | 0.114 | 0.042 | 0.142 | ✓ |
| real_rates | +0.107 | 0.085 | 0.055 | 0.079 | ✓ |
| structure | +0.104 | 0.085 | 0.136 | 0.01 | ✓ |
| cycle | +0.100 | — | — | — | · |
| mtf | +0.060 | — | — | — | · |
| liquidity | +0.041 | 0.095 | -0.038 | 0.232 | · |
| alerts | +0.040 | — | — | — | · |
| dollar | +0.035 | 0.062 | -0.051 | 0.172 | · |
| carry | -0.029 | -0.047 | -0.188 | 0.166 | · |

Cycle (amp 0.28, 14 legs): bull median 711d (n=7, 69.8%); bear median 258d (n=7, 35.6%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 844 | -5.51 | 39.1 |
| SELL | 1715 | +2.84 | 49.6 |
| HOLD | 2755 | +10.46 | 64.4 |
| BUY | 1061 | +10.09 | 70.2 |
| STRONG BUY | 41 | +1.31 | 39.0 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context

## Oil

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| trend | -0.141 | -0.183 | -0.39 | -0.131 | ✓ |
| growth | +0.121 | 0.159 | 0.189 | 0.1 | ✓ |
| real_rates | +0.112 | 0.155 | 0.346 | 0.028 | ✓ |
| cycle | +0.100 | — | — | — | · |
| dollar | +0.097 | 0.146 | 0.073 | 0.223 | ✓ |
| shock | -0.089 | -0.132 | -0.159 | -0.12 | ✓ |
| risk | -0.088 | -0.092 | -0.153 | -0.064 | ✓ |
| value | +0.074 | 0.088 | 0.222 | 0.024 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| structure | -0.032 | -0.032 | -0.051 | -0.031 | ✓ |
| liquidity | +0.028 | 0.101 | -0.038 | 0.221 | · |
| riskoff | +0.018 | 0.069 | -0.001 | 0.094 | · |

Cycle (amp 0.4, 18 legs): bull median 194d (n=9, 55.9%); bear median 342d (n=9, 57.3%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 872 | -7.62 | 40.9 |
| SELL | 1695 | +0.52 | 44.9 |
| HOLD | 2472 | +7.13 | 62.1 |
| BUY | 1229 | +19.18 | 77.5 |
| STRONG BUY | 152 | +2.08 | 42.8 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context
