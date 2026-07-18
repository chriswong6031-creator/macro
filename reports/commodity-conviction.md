# Commodity conviction — calibration

Measured forward-return predictive strength per factor (Spearman, 63d & 126d), split-half @ 2013-01-01. Weight = polarity x |corr| x stability, normalized to 0.8 panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; buckets verified monotone in forward 126d return.


## Gold

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| carry | +0.185 | 0.18 | 0.122 | 0.28 | ✓ |
| liquidity | +0.161 | 0.159 | 0.084 | 0.197 | ✓ |
| inflation | -0.120 | -0.123 | -0.179 | -0.101 | ✓ |
| value | -0.101 | -0.097 | -0.101 | -0.178 | ✓ |
| cycle | +0.100 | — | — | — | · |
| trend | +0.072 | 0.182 | -0.25 | 0.299 | · |
| dollar | -0.060 | -0.05 | -0.063 | -0.033 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| positioning | -0.040 | -0.087 | 0.062 | -0.144 | · |
| growth | -0.030 | -0.061 | 0.053 | -0.191 | · |
| real_rates | +0.029 | 0.064 | -0.184 | 0.209 | · |

Cycle (amp 0.18, 14 legs): bull median 1012d (n=7, 95.2%); bear median 177d (n=7, 21.9%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 12 | +2.15 | 100.0 |
| SELL | 1320 | +2.58 | 63.6 |
| HOLD | 2781 | +5.35 | 66.0 |
| BUY | 1632 | +9.86 | 79.8 |
| STRONG BUY | 480 | +13.17 | 95.2 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Silver

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| value | +0.197 | 0.161 | 0.184 | 0.256 | ✓ |
| inflation | -0.130 | -0.101 | -0.095 | -0.116 | ✓ |
| carry | +0.121 | 0.09 | 0.037 | 0.212 | ✓ |
| cycle | +0.100 | — | — | — | · |
| growth | -0.090 | -0.074 | -0.006 | -0.205 | ✓ |
| risk | -0.086 | -0.055 | -0.004 | -0.09 | ✓ |
| mtf | +0.060 | — | — | — | · |
| shock | -0.053 | -0.032 | -0.01 | -0.072 | ✓ |
| real_rates | +0.049 | 0.091 | -0.122 | 0.225 | · |
| liquidity | +0.049 | 0.088 | -0.029 | 0.162 | · |
| alerts | +0.040 | — | — | — | · |
| riskoff | -0.026 | -0.05 | 0.0 | -0.164 | · |

Cycle (amp 0.35, 14 legs): bull median 631d (n=7, 150.5%); bear median 453d (n=7, 43.2%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 500 | +0.71 | 43.2 |
| SELL | 1778 | +7.02 | 52.6 |
| HOLD | 1927 | +8.29 | 58.6 |
| BUY | 1644 | +8.39 | 67.4 |
| STRONG BUY | 441 | +21.27 | 83.9 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Copper

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| risk | -0.183 | -0.153 | -0.125 | -0.202 | ✓ |
| riskoff | +0.153 | 0.137 | 0.13 | 0.143 | ✓ |
| growth | +0.146 | 0.115 | 0.042 | 0.145 | ✓ |
| real_rates | +0.108 | 0.085 | 0.055 | 0.08 | ✓ |
| structure | +0.105 | 0.085 | 0.136 | 0.009 | ✓ |
| cycle | +0.100 | — | — | — | · |
| mtf | +0.060 | — | — | — | · |
| liquidity | +0.042 | 0.094 | -0.031 | 0.222 | · |
| alerts | +0.040 | — | — | — | · |
| dollar | +0.035 | 0.06 | -0.051 | 0.167 | · |
| carry | -0.029 | -0.046 | -0.188 | 0.17 | · |

Cycle (amp 0.28, 14 legs): bull median 711d (n=7, 69.8%); bear median 258d (n=7, 35.6%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 843 | -5.46 | 39.0 |
| SELL | 1702 | +2.84 | 49.8 |
| HOLD | 2715 | +10.46 | 64.0 |
| BUY | 1073 | +9.92 | 69.5 |
| STRONG BUY | 43 | +1.33 | 39.5 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context

## Oil

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| trend | -0.137 | -0.179 | -0.39 | -0.126 | ✓ |
| growth | +0.124 | 0.16 | 0.189 | 0.101 | ✓ |
| real_rates | +0.112 | 0.158 | 0.346 | 0.031 | ✓ |
| cycle | +0.100 | — | — | — | · |
| dollar | +0.093 | 0.143 | 0.073 | 0.217 | ✓ |
| shock | -0.092 | -0.137 | -0.159 | -0.127 | ✓ |
| risk | -0.089 | -0.093 | -0.153 | -0.068 | ✓ |
| value | +0.071 | 0.08 | 0.222 | 0.011 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| structure | -0.034 | -0.037 | -0.051 | -0.042 | ✓ |
| liquidity | +0.029 | 0.102 | -0.03 | 0.217 | · |
| riskoff | +0.018 | 0.066 | -0.001 | 0.088 | · |

Cycle (amp 0.4, 18 legs): bull median 194d (n=9, 55.9%); bear median 342d (n=9, 57.3%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 871 | -7.71 | 40.3 |
| SELL | 1685 | +0.28 | 44.9 |
| HOLD | 2460 | +7.22 | 62.3 |
| BUY | 1213 | +19.14 | 77.2 |
| STRONG BUY | 151 | +1.64 | 42.4 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context
