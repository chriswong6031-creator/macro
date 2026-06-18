# Forex Vector — calibration report

Split-half boundary: **2015-01-01**. Forward horizons: [21, 63, 126] days.

IC = Spearman rank corr of naive-bullish factor vs forward base-vs-USD return; peg windows excised.

House rule: a factor's weight is its MEASURED forward-return strength (mean Spearman IC), signed. CONFIRMED = same sign in full + both halves; INVERTED = robustly negative (the engine flips it); DIRECTIONAL = full only (half weight); CONTEXT = weak/unstable (no weight). Peg & intervention windows are excised. FX history is short and crash-dominated, so most factors land DIRECTIONAL/CONTEXT — the verdicts are honest, not flattering.


## EURUSD — 2004-01-01..2026-06-18 (5828 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.069 | -0.073 | -0.056 | -0.275 |
| structure | **CONTEXT** | +0.030 | 0.048 | -0.008 | +0.030 |
| carry | **DIRECTIONAL** | -0.121 | -0.217 | 0.011 | -0.115 |
| rates | **CONTEXT** | +0.035 | 0.066 | -0.007 | +0.042 |
| value | **CONFIRMED** | +0.099 | 0.141 | 0.055 | +0.122 |
| riskoff | **DIRECTIONAL** | +0.051 | 0.032 | 0.086 | +0.115 |
| positioning | **INVERTED** | -0.135 | -0.194 | -0.067 | -0.137 |
| risk | **INVERTED** | -0.062 | -0.029 | -0.114 | -0.137 |
| shock | **CONTEXT** | -0.000 | -0.031 | 0.016 | +0.027 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.8%** net (gross 0.9%, drag 0.1pp; passive-long hold -0.4%), Sharpe 0.31 (hold 0.02), MaxDD -5.4%, turnover 4.8x/yr, avg exposure 15.2%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0033**; observed SR 0.31 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5828d, skew=5.795, kurt=307.052).

## USDJPY — 2004-01-01..2026-06-18 (5829 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONFIRMED** | +0.156 | 0.217 | 0.048 | +0.330 |
| structure | **CONTEXT** | -0.004 | 0.003 | -0.018 | +0.037 |
| carry | **CONTEXT** | -0.017 | -0.104 | 0.035 | +0.069 |
| rates | **CONTEXT** | -0.024 | -0.032 | -0.014 | +0.051 |
| value | **INVERTED** | -0.166 | -0.125 | -0.189 | -0.147 |
| riskoff | **DIRECTIONAL** | +0.049 | 0.077 | 0.019 | +0.138 |
| positioning | **DIRECTIONAL** | -0.055 | -0.094 | -0.046 | -0.083 |
| risk | **DIRECTIONAL** | -0.063 | -0.159 | 0.046 | -0.083 |
| shock | **DIRECTIONAL** | +0.042 | 0.095 | 0.0 | +0.064 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.9%** net (gross 1.0%, drag 0.1pp; passive-long hold -1.8%), Sharpe 0.19 (hold -0.09), MaxDD -13.5%, turnover 5.5x/yr, avg exposure 26.2%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0008**; observed SR 0.19 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5829d, skew=-0.531, kurt=512.043).

## AUDUSD — 2006-05-16..2026-06-18 (5228 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONTEXT** | +0.017 | 0.045 | -0.029 | +0.119 |
| structure | **CONTEXT** | -0.007 | 0.036 | -0.083 | +0.053 |
| carry | **CONTEXT** | +0.004 | -0.249 | 0.021 | +0.099 |
| rates | **CONTEXT** | +0.040 | 0.069 | 0.03 | +0.073 |
| value | **CONFIRMED** | +0.100 | 0.06 | 0.167 | +0.212 |
| riskoff | **CONTEXT** | -0.027 | -0.011 | -0.026 | +0.099 |
| positioning | **CONTEXT** | +0.019 | 0.062 | -0.026 | +0.060 |
| risk | **INVERTED** | -0.080 | -0.151 | -0.049 | -0.238 |
| shock | **CONTEXT** | +0.003 | 0.1 | -0.069 | +0.046 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **-0.3%** net (gross -0.2%, drag 0.1pp; passive-long hold -0.4%), Sharpe -0.15 (hold 0.03), MaxDD -11.1%, turnover 5.1x/yr, avg exposure 15.0%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0**; observed SR -0.15 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5228d, skew=-0.371, kurt=14.524).

## GBPUSD — 2004-01-01..2026-06-18 (5840 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.088 | -0.115 | -0.068 | -0.267 |
| structure | **CONTEXT** | -0.022 | 0.01 | -0.054 | +0.030 |
| carry | **INVERTED** | -0.161 | -0.307 | -0.109 | -0.222 |
| rates | **CONTEXT** | +0.002 | -0.028 | 0.034 | +0.041 |
| value | **DIRECTIONAL** | +0.044 | -0.063 | 0.142 | +0.059 |
| riskoff | **CONFIRMED** | +0.109 | 0.131 | 0.089 | +0.222 |
| positioning | **DIRECTIONAL** | +0.052 | 0.046 | 0.052 | +0.067 |
| risk | **DIRECTIONAL** | -0.049 | -0.005 | -0.092 | -0.067 |
| shock | **CONTEXT** | -0.036 | -0.015 | -0.048 | +0.026 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.5%** net (gross 0.5%, drag 0.1pp; passive-long hold -1.3%), Sharpe 0.27 (hold -0.09), MaxDD -7.3%, turnover 3.7x/yr, avg exposure 15.1%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0025**; observed SR 0.27 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5840d, skew=-0.302, kurt=15.653).

## USDCAD — 2004-01-01..2026-06-18 (5844 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONTEXT** | +0.036 | 0.15 | -0.185 | +0.083 |
| structure | **DIRECTIONAL** | -0.046 | 0.036 | -0.167 | -0.073 |
| carry | **INVERTED** | -0.201 | -0.345 | -0.146 | -0.275 |
| rates | **CONTEXT** | -0.009 | -0.015 | 0.0 | +0.051 |
| value | **DIRECTIONAL** | +0.044 | 0.065 | 0.059 | +0.073 |
| riskoff | **CONTEXT** | +0.013 | 0.054 | -0.029 | +0.069 |
| positioning | **CONFIRMED** | +0.112 | 0.01 | 0.235 | +0.165 |
| risk | **DIRECTIONAL** | -0.053 | -0.043 | -0.057 | -0.083 |
| shock | **INVERTED** | -0.114 | -0.122 | -0.118 | -0.128 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **1.5%** net (gross 1.6%, drag 0.2pp; passive-long hold -0.4%), Sharpe 1.07 (hold -0.0), MaxDD -4.4%, turnover 7.6x/yr, avg exposure 13.9%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.8607**; observed SR 1.07 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5844d, skew=0.832, kurt=16.252).

## USDCHF — 2004-01-01..2026-06-18 (5842 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.156 | -0.169 | -0.139 | -0.255 |
| structure | **INVERTED** | -0.121 | -0.077 | -0.176 | -0.114 |
| carry | **INVERTED** | -0.073 | -0.045 | -0.149 | -0.213 |
| rates | **DIRECTIONAL** | +0.059 | 0.087 | 0.033 | +0.078 |
| value | **CONTEXT** | -0.035 | 0.001 | -0.09 | +0.028 |
| riskoff | **CONTEXT** | -0.034 | -0.02 | -0.058 | +0.053 |
| positioning | **CONTEXT** | +0.031 | -0.03 | 0.097 | +0.032 |
| risk | **INVERTED** | -0.082 | -0.063 | -0.113 | -0.128 |
| shock | **INVERTED** | -0.140 | -0.057 | -0.204 | -0.099 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **1.8%** net (gross 2.0%, drag 0.2pp; passive-long hold 2.0%), Sharpe 0.57 (hold 0.23), MaxDD -15.1%, turnover 9.0x/yr, avg exposure 18.6%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0479**; observed SR 0.57 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5842d, skew=15.588, kurt=676.176).

## USDMXN — 2004-01-01..2026-06-18 (5850 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.079 | -0.178 | -0.051 | -0.276 |
| structure | **INVERTED** | -0.096 | -0.146 | -0.061 | -0.123 |
| rates | **UNMEASURED** | n/a | None | None | +0.169 |
| value | **DIRECTIONAL** | +0.079 | 0.328 | -0.059 | +0.061 |
| riskoff | **CONTEXT** | -0.019 | 0.007 | -0.051 | +0.058 |
| positioning | **DIRECTIONAL** | +0.050 | 0.066 | 0.044 | +0.069 |
| risk | **INVERTED** | -0.099 | -0.131 | -0.082 | -0.138 |
| shock | **INVERTED** | -0.087 | -0.104 | -0.08 | -0.107 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **1.9%** net (gross 2.1%, drag 0.2pp; passive-long hold -1.9%), Sharpe 0.42 (hold -0.09), MaxDD -13.3%, turnover 12.1x/yr, avg exposure 29.7%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0176**; observed SR 0.42 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5850d, skew=0.213, kurt=26.009).

## USDBRL — 2004-01-01..2026-06-18 (5411 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **DIRECTIONAL** | +0.065 | 0.145 | -0.009 | +0.182 |
| structure | **CONTEXT** | +0.028 | 0.032 | 0.017 | +0.040 |
| rates | **UNMEASURED** | n/a | None | None | +0.222 |
| value | **DIRECTIONAL** | +0.045 | 0.039 | 0.069 | +0.081 |
| riskoff | **CONTEXT** | -0.036 | -0.074 | 0.003 | +0.076 |
| positioning | **INVERTED** | -0.178 | -0.141 | -0.194 | -0.182 |
| risk | **INVERTED** | -0.114 | -0.093 | -0.133 | -0.182 |
| shock | **CONTEXT** | -0.002 | -0.007 | -0.0 | +0.035 |

**Conviction long/short backtest (NET of 2.0bps one-way cost)** — IN-SAMPLE (weights fit on full history): CAGR **0.4%** net (gross 0.5%, drag 0.1pp; passive-long hold -2.5%), Sharpe 0.09 (hold -0.04), MaxDD -28.5%, turnover 6.8x/yr, avg exposure 22.0%.

**Deflated Sharpe (multiple-testing haircut)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR (P true Sharpe>0) = **0.0004**; observed SR 0.09 ann vs haircut SR0 0.85 ann (N=60 factor×pair trials, T=5411d, skew=-18.859, kurt=872.476).

## USDCNH — 2013-02-11..2026-06-18 (3289 days) · context-only (prior weights, confidence dampened)

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

## DOLLAR INDEX — value (REER) vs forward broad USD (DTWEXBGS)

2006-01-02..2026-06-12 (5126 days). The dollar's own naive-bullish REER-value factor (cheap = bullish USD) vs forward broad-USD returns, split at 2015-01-01.

| Factor | Verdict | IC full | IC pre | IC post | promotable |
|---|---|--:|--:|--:|:--|
| value (REER) | **CONFIRMED** | +0.065 | 0.077 | 0.06 | False |

**Deflated Sharpe (REER-only dollar long/short, N+1 trials)**: **FAILS multiple-testing haircut (DSR<0.90)**. DSR = **0.0056**; SR -0.04 ann vs SR0 0.52 ann (N=61, T=5126d).

**DISPLAY-ONLY.** This grades the dollar's REER-value lean honestly; it is NOT wired into any score. Promotion to a scored leg requires CONFIRMED in both halves AND DSR≥0.90 — unlikely for FX, which is the honest expected outcome.

## Trial log

As-of 2026-06-18: **60** declared factor×pair trials (upper-bound); 9 factor families screened across 9 pairs; spread cost 2.0bps one-way.