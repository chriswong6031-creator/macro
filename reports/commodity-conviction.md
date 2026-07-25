# Commodity conviction — calibration

Measured forward-return predictive strength per factor (Spearman, 63d & 126d), split-half @ 2013-01-01. Weight = polarity x |corr| x stability, normalized to 0.8 panel mass (+ live cycle/mtf/alerts). Thresholds = score quantiles; buckets verified monotone in forward 126d return.


## Gold

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| carry | +0.185 | 0.179 | 0.122 | 0.277 | ✓ |
| liquidity | +0.160 | 0.158 | 0.084 | 0.194 | ✓ |
| inflation | -0.121 | -0.124 | -0.179 | -0.102 | ✓ |
| value | -0.103 | -0.099 | -0.101 | -0.183 | ✓ |
| cycle | +0.100 | — | — | — | · |
| trend | +0.071 | 0.178 | -0.25 | 0.292 | · |
| dollar | -0.061 | -0.051 | -0.063 | -0.035 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| positioning | -0.040 | -0.087 | 0.062 | -0.143 | · |
| real_rates | +0.030 | 0.066 | -0.184 | 0.211 | · |
| growth | -0.030 | -0.059 | 0.053 | -0.186 | · |

Cycle (amp 0.18, 14 legs): bull median 1012d (n=7, 95.2%); bear median 177d (n=7, 21.9%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 12 | +2.15 | 100.0 |
| SELL | 1310 | +2.57 | 63.6 |
| HOLD | 2789 | +5.32 | 66.0 |
| BUY | 1639 | +9.78 | 79.5 |
| STRONG BUY | 481 | +13.17 | 95.4 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Silver

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| value | +0.198 | 0.164 | 0.184 | 0.26 | ✓ |
| inflation | -0.131 | -0.101 | -0.095 | -0.117 | ✓ |
| carry | +0.119 | 0.088 | 0.037 | 0.209 | ✓ |
| cycle | +0.100 | — | — | — | · |
| growth | -0.088 | -0.072 | -0.006 | -0.2 | ✓ |
| risk | -0.084 | -0.055 | -0.004 | -0.09 | ✓ |
| mtf | +0.060 | — | — | — | · |
| shock | -0.055 | -0.036 | -0.01 | -0.077 | ✓ |
| real_rates | +0.050 | 0.092 | -0.122 | 0.227 | · |
| liquidity | +0.048 | 0.087 | -0.029 | 0.16 | · |
| alerts | +0.040 | — | — | — | · |
| riskoff | -0.026 | -0.052 | 0.0 | -0.168 | · |

Cycle (amp 0.35, 14 legs): bull median 631d (n=7, 150.5%); bear median 453d (n=7, 43.2%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 505 | +0.70 | 43.0 |
| SELL | 1770 | +6.75 | 52.5 |
| HOLD | 1927 | +8.31 | 58.4 |
| BUY | 1642 | +8.40 | 67.4 |
| STRONG BUY | 452 | +21.20 | 83.6 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✓ YES

## Copper

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| risk | -0.183 | -0.153 | -0.125 | -0.203 | ✓ |
| riskoff | +0.153 | 0.137 | 0.13 | 0.144 | ✓ |
| growth | +0.146 | 0.115 | 0.042 | 0.143 | ✓ |
| real_rates | +0.107 | 0.085 | 0.055 | 0.079 | ✓ |
| structure | +0.105 | 0.086 | 0.136 | 0.01 | ✓ |
| cycle | +0.100 | — | — | — | · |
| mtf | +0.060 | — | — | — | · |
| liquidity | +0.042 | 0.094 | -0.031 | 0.222 | · |
| alerts | +0.040 | — | — | — | · |
| dollar | +0.035 | 0.06 | -0.051 | 0.168 | · |
| carry | -0.029 | -0.046 | -0.188 | 0.171 | · |

Cycle (amp 0.28, 14 legs): bull median 711d (n=7, 69.8%); bear median 258d (n=7, 35.6%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 842 | -5.46 | 39.1 |
| SELL | 1715 | +2.86 | 49.7 |
| HOLD | 2708 | +10.47 | 64.1 |
| BUY | 1074 | +9.92 | 69.6 |
| STRONG BUY | 43 | +1.33 | 39.5 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context

## Oil

| factor | weight | corr126 | pre | post | stable |
|---|---:|---:|---:|---:|:--:|
| trend | -0.138 | -0.181 | -0.39 | -0.128 | ✓ |
| growth | +0.123 | 0.158 | 0.189 | 0.098 | ✓ |
| real_rates | +0.112 | 0.156 | 0.346 | 0.029 | ✓ |
| cycle | +0.100 | — | — | — | · |
| dollar | +0.094 | 0.143 | 0.073 | 0.218 | ✓ |
| shock | -0.091 | -0.136 | -0.159 | -0.126 | ✓ |
| risk | -0.089 | -0.092 | -0.153 | -0.067 | ✓ |
| value | +0.072 | 0.082 | 0.222 | 0.015 | ✓ |
| mtf | +0.060 | — | — | — | · |
| alerts | +0.040 | — | — | — | · |
| structure | -0.034 | -0.035 | -0.051 | -0.039 | ✓ |
| liquidity | +0.029 | 0.103 | -0.03 | 0.218 | · |
| riskoff | +0.018 | 0.068 | -0.001 | 0.091 | · |

Cycle (amp 0.4, 18 legs): bull median 194d (n=9, 55.9%); bear median 342d (n=9, 57.3%).

Score buckets (forward 126d):
| action | n | avg fwd126% | hit% |
|---|---:|---:|---:|
| STRONG SELL | 873 | -7.80 | 40.2 |
| SELL | 1681 | +0.39 | 45.0 |
| HOLD | 2468 | +7.24 | 62.2 |
| BUY | 1213 | +19.18 | 77.2 |
| STRONG BUY | 151 | +1.64 | 42.4 |

Score reliable (monotone Strong Sell → Strong Buy, spread ≥6%): ✗ NO — weak for this asset, present as context
