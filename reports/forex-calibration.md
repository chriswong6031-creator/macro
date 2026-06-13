# Forex Vector — calibration report

Split-half boundary: **2015-01-01**. Forward horizons: [21, 63, 126] days.

IC = Spearman rank corr of naive-bullish factor vs forward base-vs-USD return; peg windows excised.

House rule: a factor's weight is its MEASURED forward-return strength (mean Spearman IC), signed. CONFIRMED = same sign in full + both halves; INVERTED = robustly negative (the engine flips it); DIRECTIONAL = full only (half weight); CONTEXT = weak/unstable (no weight). Peg & intervention windows are excised. FX history is short and crash-dominated, so most factors land DIRECTIONAL/CONTEXT — the verdicts are honest, not flattering.


## EURUSD — 2004-01-01..2026-06-12 (5823 days) · context-only (prior weights, confidence dampened)

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.069 | -0.073 | -0.056 | -0.376 |
| structure | **CONTEXT** | +0.030 | 0.048 | -0.008 | +0.043 |
| carry | **DIRECTIONAL** | -0.121 | -0.217 | 0.01 | -0.171 |
| riskoff | **DIRECTIONAL** | +0.052 | 0.032 | 0.086 | +0.154 |
| positioning | **UNMEASURED** | n/a | None | None | +0.171 |
| risk | **CONTEXT** | -0.014 | 0.01 | -0.067 | +0.051 |
| shock | **CONTEXT** | -0.000 | -0.031 | 0.016 | +0.034 |

## USDJPY — 2004-01-01..2026-06-13 (5824 days) · context-only (prior weights, confidence dampened)

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONFIRMED** | +0.156 | 0.217 | 0.048 | +0.376 |
| structure | **CONTEXT** | -0.004 | 0.003 | -0.018 | +0.043 |
| carry | **CONTEXT** | -0.017 | -0.104 | 0.035 | +0.086 |
| riskoff | **DIRECTIONAL** | +0.049 | 0.077 | 0.019 | +0.154 |
| positioning | **UNMEASURED** | n/a | None | None | +0.171 |
| risk | **DIRECTIONAL** | -0.049 | -0.147 | 0.069 | -0.103 |
| shock | **DIRECTIONAL** | +0.042 | 0.095 | 0.0 | +0.068 |

## AUDUSD — 2006-05-16..2026-06-13 (5223 days) · context-only (prior weights, confidence dampened)

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONTEXT** | +0.017 | 0.045 | -0.029 | +0.133 |
| structure | **CONTEXT** | -0.007 | 0.036 | -0.083 | +0.060 |
| carry | **CONTEXT** | +0.004 | -0.249 | 0.021 | +0.120 |
| riskoff | **CONTEXT** | -0.027 | -0.011 | -0.026 | +0.108 |
| positioning | **UNMEASURED** | n/a | None | None | +0.241 |
| risk | **INVERTED** | -0.091 | -0.152 | -0.06 | -0.289 |
| shock | **CONTEXT** | +0.003 | 0.1 | -0.069 | +0.048 |

## GBPUSD — 2004-01-01..2026-06-12 (5835 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.088 | -0.115 | -0.068 | -0.254 |
| structure | **CONTEXT** | -0.022 | 0.01 | -0.054 | +0.029 |
| carry | **INVERTED** | -0.161 | -0.307 | -0.109 | -0.231 |
| riskoff | **CONFIRMED** | +0.109 | 0.131 | 0.089 | +0.208 |
| positioning | **UNMEASURED** | n/a | None | None | +0.116 |
| risk | **INVERTED** | -0.067 | -0.015 | -0.122 | -0.139 |
| shock | **CONTEXT** | -0.035 | -0.015 | -0.048 | +0.023 |

## USDCAD — 2004-01-01..2026-06-13 (5839 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **CONTEXT** | +0.037 | 0.15 | -0.184 | +0.085 |
| structure | **DIRECTIONAL** | -0.046 | 0.036 | -0.166 | -0.077 |
| carry | **INVERTED** | -0.203 | -0.345 | -0.148 | -0.308 |
| riskoff | **CONTEXT** | +0.013 | 0.054 | -0.029 | +0.069 |
| positioning | **UNMEASURED** | n/a | None | None | +0.154 |
| risk | **INVERTED** | -0.069 | -0.039 | -0.104 | -0.185 |
| shock | **INVERTED** | -0.114 | -0.122 | -0.118 | -0.123 |

## USDCHF — 2004-01-01..2026-06-13 (5837 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.156 | -0.169 | -0.139 | -0.254 |
| structure | **INVERTED** | -0.121 | -0.077 | -0.177 | -0.116 |
| carry | **INVERTED** | -0.073 | -0.045 | -0.15 | -0.231 |
| riskoff | **CONTEXT** | -0.034 | -0.02 | -0.058 | +0.052 |
| positioning | **UNMEASURED** | n/a | None | None | +0.116 |
| risk | **INVERTED** | -0.073 | -0.053 | -0.108 | -0.139 |
| shock | **INVERTED** | -0.140 | -0.057 | -0.204 | -0.092 |

## USDMXN — 2004-01-01..2026-06-13 (5845 days) · score_reliable ✓

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **INVERTED** | -0.081 | -0.178 | -0.053 | -0.331 |
| structure | **INVERTED** | -0.096 | -0.146 | -0.062 | -0.150 |
| riskoff | **CONTEXT** | -0.019 | 0.007 | -0.051 | +0.068 |
| positioning | **UNMEASURED** | n/a | None | None | +0.150 |
| risk | **INVERTED** | -0.107 | -0.127 | -0.097 | -0.180 |
| shock | **INVERTED** | -0.086 | -0.104 | -0.079 | -0.120 |

## USDBRL — 2004-01-01..2026-06-13 (5406 days) · context-only (prior weights, confidence dampened)

| Factor | Verdict | IC full | IC pre | IC post | weight |
|---|---|--:|--:|--:|--:|
| trend | **DIRECTIONAL** | +0.064 | 0.145 | -0.01 | +0.262 |
| structure | **CONTEXT** | +0.028 | 0.032 | 0.018 | +0.059 |
| riskoff | **CONTEXT** | -0.036 | -0.074 | 0.003 | +0.107 |
| positioning | **UNMEASURED** | n/a | None | None | +0.238 |
| risk | **INVERTED** | -0.093 | -0.076 | -0.119 | -0.286 |
| shock | **CONTEXT** | -0.002 | -0.007 | 0.001 | +0.048 |