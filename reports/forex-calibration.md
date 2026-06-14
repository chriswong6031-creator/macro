# Forex Vector — calibration report

Split-half boundary: **2015-01-01**. Forward horizons: [21, 63, 126] days.

IC = Spearman rank corr of naive-bullish factor vs forward base-vs-USD return; peg windows excised.

House rule: a factor's weight is its MEASURED forward-return strength (mean Spearman IC), signed. CONFIRMED = same sign in full + both halves; INVERTED = robustly negative (the engine flips it); DIRECTIONAL = full only (half weight); CONTEXT = weak/unstable (no weight). Peg & intervention windows are excised. FX history is short and crash-dominated, so most factors land DIRECTIONAL/CONTEXT — the verdicts are honest, not flattering.


## EURUSD — 2004-01-01..2026-06-12 (5823 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.069 | -0.073 | -0.056 | -0.306 |
| structure | **CONTEXT** | +0.030 | 0.048 | -0.008 | +0.034 |
| carry | **DIRECTIONAL** | -0.121 | -0.217 | 0.01 | -0.128 |
| rates | **CONTEXT** | +0.035 | 0.066 | -0.007 | +0.047 |
| value | **CONFIRMED** | +0.099 | 0.141 | 0.055 | +0.136 |
| riskoff | **DIRECTIONAL** | +0.052 | 0.032 | 0.086 | +0.128 |
| positioning | **UNMEASURED** | n/a | None | None | +0.153 |
| risk | **CONTEXT** | -0.014 | 0.01 | -0.067 | +0.038 |
| shock | **CONTEXT** | -0.000 | -0.031 | 0.016 | +0.030 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.4%** net (gross 0.5%, drag 0.1pp; passive-long hold -0.4%), Sharpe 0.15 (hold 0.02), MaxDD -9.7%, turnover 4.3x/yr, avg exposure 17.6%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0005**; observed SR 0.15 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5823d, skew=3.077, kurt=142.524).

## USDJPY — 2004-01-01..2026-06-13 (5824 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONFIRMED** | +0.156 | 0.217 | 0.048 | +0.305 |
| structure | **CONTEXT** | -0.004 | 0.003 | -0.018 | +0.034 |
| carry | **CONTEXT** | -0.017 | -0.104 | 0.035 | +0.064 |
| rates | **CONTEXT** | -0.024 | -0.032 | -0.014 | +0.047 |
| value | **INVERTED** | -0.166 | -0.125 | -0.189 | -0.136 |
| riskoff | **DIRECTIONAL** | +0.049 | 0.077 | 0.019 | +0.127 |
| positioning | **UNMEASURED** | n/a | None | None | +0.152 |
| risk | **DIRECTIONAL** | -0.049 | -0.147 | 0.069 | -0.076 |
| shock | **DIRECTIONAL** | +0.042 | 0.095 | 0.0 | +0.059 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.9%** net (gross 1.0%, drag 0.1pp; passive-long hold -1.8%), Sharpe 0.21 (hold -0.09), MaxDD -13.7%, turnover 5.6x/yr, avg exposure 25.1%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0018**; observed SR 0.21 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5824d, skew=-0.952, kurt=505.454).

## AUDUSD — 2006-05-16..2026-06-13 (5223 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONTEXT** | +0.017 | 0.045 | -0.029 | +0.101 |
| structure | **CONTEXT** | -0.007 | 0.036 | -0.083 | +0.045 |
| carry | **CONTEXT** | +0.004 | -0.249 | 0.021 | +0.084 |
| rates | **CONTEXT** | +0.040 | 0.069 | 0.03 | +0.062 |
| value | **CONFIRMED** | +0.100 | 0.06 | 0.167 | +0.180 |
| riskoff | **CONTEXT** | -0.027 | -0.011 | -0.026 | +0.084 |
| positioning | **UNMEASURED** | n/a | None | None | +0.202 |
| risk | **INVERTED** | -0.091 | -0.152 | -0.06 | -0.202 |
| shock | **CONTEXT** | +0.003 | 0.1 | -0.069 | +0.039 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **-0.2%** net (gross -0.1%, drag 0.1pp; passive-long hold -0.4%), Sharpe -0.08 (hold 0.03), MaxDD -10.0%, turnover 5.7x/yr, avg exposure 15.6%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0**; observed SR -0.08 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5223d, skew=-0.402, kurt=15.431).

## GBPUSD — 2004-01-01..2026-06-12 (5835 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.088 | -0.115 | -0.068 | -0.235 |
| structure | **CONTEXT** | -0.022 | 0.01 | -0.054 | +0.026 |
| carry | **INVERTED** | -0.161 | -0.307 | -0.109 | -0.196 |
| rates | **CONTEXT** | +0.002 | -0.028 | 0.034 | +0.036 |
| value | **DIRECTIONAL** | +0.044 | -0.063 | 0.142 | +0.052 |
| riskoff | **CONFIRMED** | +0.109 | 0.131 | 0.089 | +0.196 |
| positioning | **UNMEASURED** | n/a | None | None | +0.118 |
| risk | **INVERTED** | -0.067 | -0.015 | -0.122 | -0.118 |
| shock | **CONTEXT** | -0.035 | -0.015 | -0.048 | +0.023 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.5%** net (gross 0.6%, drag 0.1pp; passive-long hold -1.3%), Sharpe 0.31 (hold -0.09), MaxDD -6.7%, turnover 4.5x/yr, avg exposure 15.6%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0064**; observed SR 0.31 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5835d, skew=-0.096, kurt=12.92).

## USDCAD — 2004-01-01..2026-06-13 (5839 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONTEXT** | +0.037 | 0.15 | -0.184 | +0.076 |
| structure | **DIRECTIONAL** | -0.046 | 0.036 | -0.166 | -0.068 |
| carry | **INVERTED** | -0.203 | -0.345 | -0.148 | -0.254 |
| rates | **CONTEXT** | -0.010 | -0.015 | -0.001 | +0.047 |
| value | **DIRECTIONAL** | +0.045 | 0.065 | 0.06 | +0.068 |
| riskoff | **CONTEXT** | +0.013 | 0.054 | -0.029 | +0.064 |
| positioning | **UNMEASURED** | n/a | None | None | +0.152 |
| risk | **INVERTED** | -0.069 | -0.039 | -0.104 | -0.152 |
| shock | **INVERTED** | -0.114 | -0.122 | -0.118 | -0.119 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **1.5%** net (gross 1.7%, drag 0.2pp; passive-long hold -0.3%), Sharpe 1.02 (hold 0.0), MaxDD -6.3%, turnover 9.0x/yr, avg exposure 13.8%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.831**; observed SR 1.02 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5839d, skew=0.975, kurt=20.757).

## USDCHF — 2004-01-01..2026-06-13 (5837 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.156 | -0.169 | -0.139 | -0.233 |
| structure | **INVERTED** | -0.121 | -0.077 | -0.177 | -0.104 |
| carry | **INVERTED** | -0.073 | -0.045 | -0.15 | -0.194 |
| rates | **DIRECTIONAL** | +0.059 | 0.087 | 0.033 | +0.071 |
| value | **CONTEXT** | -0.035 | 0.001 | -0.091 | +0.026 |
| riskoff | **CONTEXT** | -0.034 | -0.02 | -0.058 | +0.049 |
| positioning | **UNMEASURED** | n/a | None | None | +0.117 |
| risk | **INVERTED** | -0.073 | -0.053 | -0.108 | -0.117 |
| shock | **INVERTED** | -0.140 | -0.057 | -0.204 | -0.091 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **1.9%** net (gross 2.1%, drag 0.2pp; passive-long hold 2.0%), Sharpe 0.58 (hold 0.23), MaxDD -15.0%, turnover 9.5x/yr, avg exposure 19.1%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0736**; observed SR 0.58 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5837d, skew=15.553, kurt=674.839).

## USDMXN — 2004-01-01..2026-06-13 (5845 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.081 | -0.178 | -0.053 | -0.258 |
| structure | **INVERTED** | -0.096 | -0.146 | -0.062 | -0.115 |
| rates | **UNMEASURED** | n/a | None | None | +0.158 |
| value | **DIRECTIONAL** | +0.079 | 0.328 | -0.059 | +0.057 |
| riskoff | **CONTEXT** | -0.019 | 0.007 | -0.051 | +0.054 |
| positioning | **UNMEASURED** | n/a | None | None | +0.129 |
| risk | **INVERTED** | -0.107 | -0.127 | -0.097 | -0.129 |
| shock | **INVERTED** | -0.086 | -0.104 | -0.079 | -0.100 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **2.0%** net (gross 2.2%, drag 0.3pp; passive-long hold -1.9%), Sharpe 0.41 (hold -0.09), MaxDD -14.1%, turnover 13.3x/yr, avg exposure 31.0%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0232**; observed SR 0.41 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5845d, skew=0.146, kurt=28.284).

## USDBRL — 2004-01-01..2026-06-13 (5406 days) · context-only (prior weights, confidence dampened)

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **DIRECTIONAL** | +0.064 | 0.145 | -0.01 | +0.182 |
| structure | **CONTEXT** | +0.028 | 0.032 | 0.018 | +0.040 |
| rates | **UNMEASURED** | n/a | None | None | +0.222 |
| value | **DIRECTIONAL** | +0.045 | 0.039 | 0.069 | +0.081 |
| riskoff | **CONTEXT** | -0.036 | -0.074 | 0.003 | +0.076 |
| positioning | **UNMEASURED** | n/a | None | None | +0.182 |
| risk | **INVERTED** | -0.093 | -0.076 | -0.119 | -0.182 |
| shock | **CONTEXT** | -0.002 | -0.007 | 0.001 | +0.035 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **-0.1%** net (gross -0.0%, drag 0.1pp; passive-long hold -2.5%), Sharpe 0.01 (hold -0.04), MaxDD -28.5%, turnover 7.1x/yr, avg exposure 19.9%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0001**; observed SR 0.01 ann vs haircut SR0 0.82 ann (N=60 factor×pair trials, T=5406d, skew=-22.818, kurt=1134.72).

## USDCNH — 2013-02-11..2026-06-12 (3284 days) · context-only (prior weights, confidence dampened)

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **UNMEASURED** | n/a | None | None | +0.212 |
| structure | **UNMEASURED** | n/a | None | None | +0.094 |
| rates | **UNMEASURED** | n/a | None | None | +0.129 |
| value | **UNMEASURED** | n/a | None | None | +0.094 |
| riskoff | **UNMEASURED** | n/a | None | None | +0.176 |
| positioning | **UNMEASURED** | n/a | None | None | +0.106 |
| risk | **UNMEASURED** | n/a | None | None | +0.106 |
| shock | **UNMEASURED** | n/a | None | None | +0.082 |

## Trial log

As-of 2026-06-13: **60** declared factor×pair trials (upper-bound); 9 factor families screened across 9 pairs; spread cost 2.0bps one-way.