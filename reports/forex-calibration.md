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

## USDCNH — 2004-01-02..2026-06-05 (5623 days) · context-only (prior weights, confidence dampened)

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