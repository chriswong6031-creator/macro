# Rate & inflation transmission — calibration report

As-of **2026-08-07**. Forward horizon **63 days**; split-half boundary **2015-01-01**. Transmission = signed Spearman IC(driver_t, asset forward 63d return); display-only coefficients. Scored gate = driver as STRESS vs forward 63d S&P drawdown (calibrate_bonds discipline) + purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West return-forecast bar. No look-ahead.

Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = weak/unstable; **INVERTED** = predicts the wrong way.

## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?

Each driver, expressed as STRESS (higher = more risk-off), vs the forward 63-day S&P drawdown — the same discriminative bar the bond-health legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it predicts the LEVEL of returns; a leg can flag RISK without forecasting return.

| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |
|---|---|---|:--:|--:|---|--:|--:|:--:|
| real10y_chg63 (Real-rate SPEED (63d rise) — 'speed breaks equities') | **DIRECTIONAL** | 0.136/0.052/0.217 | True | 7.2pp | [0.105, 0.198, 0.301] | -0.954 | -0.1026 | — |
| real10y (Real-rate LEVEL (high real yields)) | **CONTEXT** | 0.039/0.053/-0.014 | False | -1.0pp | [0.035, 0.114, 0.216] | -0.82 | -0.16776 | — |
| corepce_gap (Core-PCE-vs-target gap (sticky inflation)) | **DIRECTIONAL** | 0.072/0.058/0.117 | False | 0.6pp | [0.077, 0.122, 0.172] | 1.714 | -0.3084 | — |
| infl_accel (Inflation re-acceleration (3m>12m)) | **DIRECTIONAL** | 0.065/0.066/0.061 | False | 4.3pp | [0.107, 0.16, 0.215] | -1.076 | -0.12612 | — |
| exp_wedge (Expectations unanchoring (market>model)) | **INVERTED** | -0.042/-0.05/-0.08 | False | -6.1pp | [0.015, 0.065, 0.136] | 2.302 | -0.09589 | — |
| curve_tp_adj (TP-adjusted curve inversion (flip: low=stress)) | **CONTEXT** | 0.005/0.01/0.045 | False | -0.7pp | [0.062, 0.11, 0.166] | -0.99 | -0.25757 | — |
| nom10y_chg63 (Nominal-rate SPEED (63d rise)) | **DIRECTIONAL** | 0.116/0.097/0.2 | False | -0.1pp | [0.077, 0.117, 0.165] | 0.716 | -0.11351 | — |
| ntfs (Near-term forward spread inversion (flip: low=stress; Engstrom-Sharpe beats 2s10s)) | **CONTEXT** | -0.042/0.026/-0.198 | False | -1.6pp | [0.054, 0.103, 0.163] | -0.787 | -0.27864 | — |
| curvature (Curve curvature (2s5s10s butterfly — humped = late-cycle)) | **CONTEXT** | 0.036/-0.013/0.184 | False | -0.2pp | [0.063, 0.115, 0.176] | -1.335 | -0.30726 | — |
| real_speed_abs (Real-rate move VIOLENCE (|63d speed|, either direction)) | **DIRECTIONAL** | 0.119/0.161/0.072 | True | 3.1pp | [0.081, 0.158, 0.249] | -1.08 | -0.1102 | — |
| slope_chg63 (Curve flattening impulse (flip: − = flattening = stress; INVERTED if post-inversion steepening is the tell)) | **CONTEXT** | -0.034/-0.085/0.156 | False | -2.1pp | [0.053, 0.096, 0.146] | 0.73 | -0.12284 | — |
| trend_spread (3m10y TREND inversion (flip: low trend = stress) — Faria-Verona OOS equity-premium claim, tested on the return-forecast bar) | **CONTEXT** | 0.152/0.241/-0.044 | False | 6.6pp | [0.112, 0.181, 0.26] | 3.643 | -0.27019 | — |

**Scored-eligible legs: NONE — every rate/inflation leg here is display-only context.** Eligible legs are PROPOSED for a config-gated MRS/drawdown leg, adopted only if they hold on the next refresh (the bonds restraint).

## Transmission matrix — per-asset forward pass-through

Signed Spearman IC of each rate/inflation driver vs each asset's forward 63-day return. Positive = tailwind, negative = headwind. These are the DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells are sign-stable across both halves.

### real10y — Real 10y yield (level)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.347 | 0.374 | 0.317 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.269 | -0.31 | -0.171 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | 0.175 | 0.266 | 0.081 | tailwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.172 | 0.122 | 0.196 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.161 | -0.271 | -0.077 | headwind | CONFIRMED |
| HG=F (Copper) | 0.133 | 0.19 | -0.036 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.131 | -0.18 | -0.058 | headwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.129 | 0.13 | 0.1 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.059 | -0.159 | -0.005 | headwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | -0.058 | None | -0.073 | headwind | CONTEXT |
| SPY (S&P 500) | -0.053 | -0.139 | 0.06 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.045 | 0.119 | -0.281 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.026 | None | 0.026 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.025 | 0.058 | -0.086 | neutral | CONTEXT |
| XLK (Technology) | -0.019 | -0.039 | 0.081 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.009 | -0.069 | 0.084 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.007 | -0.1 | 0.05 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.007 | 0.075 | -0.145 | neutral | CONTEXT |

### real10y_chg63 — Real 10y — 63d change (speed)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.312 | None | -0.3 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.215 | -0.198 | -0.222 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.193 | -0.197 | -0.192 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.191 | -0.167 | -0.218 | headwind | CONFIRMED |
| XLK (Technology) | -0.189 | -0.209 | -0.187 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.184 | -0.17 | -0.18 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.171 | -0.131 | -0.212 | headwind | CONFIRMED |
| HG=F (Copper) | -0.166 | -0.162 | -0.144 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.158 | -0.109 | -0.22 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.146 | 0.225 | 0.08 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.128 | -0.116 | -0.126 | headwind | CONFIRMED |
| XLE (Energy (inflation beneficiary)) | -0.114 | -0.142 | -0.063 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.082 | 0.018 | -0.175 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.039 | -0.0 | -0.074 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.027 | None | 0.027 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.024 | 0.004 | -0.038 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.008 | 0.005 | 0.002 | neutral | CONTEXT |
| GC=F (Gold) | -0.005 | 0.052 | -0.061 | neutral | CONTEXT |

### nom10y_chg63 — Nominal 10y — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.244 | None | -0.274 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.141 | -0.086 | -0.231 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.121 | -0.092 | -0.186 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.101 | -0.052 | -0.192 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.101 | 0.047 | -0.226 | headwind | CONTEXT |
| XLK (Technology) | -0.095 | -0.053 | -0.188 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.084 | 0.004 | -0.204 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.075 | 0.137 | 0.04 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.064 | -0.04 | -0.103 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.044 | -0.004 | -0.1 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.043 | 0.052 | -0.183 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.039 | None | 0.039 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.036 | -0.041 | 0.018 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.035 | 0.054 | -0.185 | neutral | CONTEXT |
| HG=F (Copper) | -0.032 | 0.014 | -0.118 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.03 | 0.049 | -0.002 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.028 | 0.029 | -0.113 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.015 | 0.064 | -0.046 | neutral | CONTEXT |

### be10y — 10y breakeven (inflation comp.)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.319 | None | -0.346 | headwind | CONTEXT |
| XLK (Technology) | -0.276 | -0.37 | -0.133 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.275 | -0.38 | -0.155 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.227 | -0.281 | -0.265 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.217 | -0.281 | -0.141 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.217 | -0.243 | -0.235 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.192 | -0.174 | -0.197 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.164 | -0.1 | -0.272 | headwind | CONFIRMED |
| HG=F (Copper) | -0.119 | -0.176 | -0.112 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.109 | -0.193 | -0.103 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.104 | 0.143 | 0.17 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.103 | -0.177 | -0.067 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.091 | None | -0.091 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.071 | -0.027 | -0.175 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.06 | -0.165 | 0.043 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.058 | -0.045 | 0.073 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.051 | 0.152 | -0.118 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.039 | 0.048 | -0.007 | neutral | CONTEXT |

### be10y_chg63 — 10y breakeven — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.121 | -0.156 | -0.087 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.121 | -0.075 | -0.145 | headwind | CONFIRMED |
| HG=F (Copper) | 0.098 | 0.189 | -0.054 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.084 | 0.228 | -0.076 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | 0.069 | 0.151 | -0.018 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.069 | 0.121 | 0.034 | tailwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | 0.058 | 0.082 | 0.029 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.047 | -0.028 | -0.069 | headwind | DIRECTIONAL |
| XLB (Materials (inflation beneficiary)) | -0.045 | 0.036 | -0.145 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.042 | 0.113 | -0.081 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.038 | -0.062 | 0.036 | neutral | CONTEXT |
| XLK (Technology) | -0.037 | -0.012 | -0.073 | neutral | CONTEXT |
| SPY (S&P 500) | 0.029 | 0.107 | -0.054 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.026 | None | 0.026 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.02 | 0.075 | -0.166 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.012 | None | -0.061 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.006 | 0.092 | -0.099 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | -0.002 | -0.014 | 0.028 | neutral | CONTEXT |

### be5y5y — 5y5y forward breakeven (anchor)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.31 | None | -0.291 | headwind | CONTEXT |
| XLK (Technology) | -0.264 | -0.272 | -0.14 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.216 | -0.272 | -0.135 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.205 | 0.261 | -0.044 | tailwind | CONTEXT |
| HG=F (Copper) | -0.199 | -0.409 | -0.185 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.169 | -0.167 | -0.132 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.162 | -0.302 | -0.279 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.152 | -0.085 | -0.173 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.139 | -0.195 | -0.202 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.124 | -0.165 | -0.257 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.105 | -0.306 | -0.176 | headwind | CONFIRMED |
| GC=F (Gold) | -0.07 | -0.243 | 0.07 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.07 | 0.205 | 0.134 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.067 | None | -0.067 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.055 | 0.045 | -0.02 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.022 | -0.073 | -0.121 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.008 | -0.13 | -0.036 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.004 | 0.017 | -0.074 | neutral | CONTEXT |

### curve_tp_adj — TP-adjusted 2s10s curve

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.239 | 0.246 | 0.16 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | 0.162 | None | 0.162 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.146 | -0.08 | -0.163 | headwind | CONFIRMED |
| XLK (Technology) | -0.117 | 0.009 | -0.107 | headwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.107 | None | -0.054 | headwind | CONTEXT |
| SPY (S&P 500) | -0.098 | -0.067 | -0.133 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.082 | -0.266 | -0.073 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.063 | 0.036 | -0.122 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.056 | -0.065 | 0.029 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.043 | -0.046 | -0.09 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | 0.043 | 0.049 | 0.038 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.035 | -0.086 | -0.018 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.031 | 0.048 | 0.014 | neutral | CONTEXT |
| XLP (Staples (defensive)) | -0.023 | -0.023 | 0.009 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | 0.033 | -0.078 | neutral | CONTEXT |
| GC=F (Gold) | -0.017 | 0.112 | -0.125 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | 0.112 | neutral | CONTEXT |
| HG=F (Copper) | 0.002 | 0.07 | -0.064 | neutral | CONTEXT |

### policy_gap — us2y − funds (cut/hike pricing)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.192 | None | -0.171 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.175 | -0.171 | -0.18 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.166 | -0.059 | -0.347 | headwind | CONFIRMED |
| XLK (Technology) | -0.165 | -0.028 | -0.304 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.154 | -0.016 | -0.321 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.14 | -0.031 | -0.29 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.097 | -0.0 | -0.237 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.097 | -0.085 | -0.156 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.072 | 0.189 | -0.045 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.071 | -0.087 | -0.054 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.07 | 0.125 | -0.299 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.061 | None | -0.061 | headwind | CONTEXT |
| HG=F (Copper) | 0.058 | 0.224 | -0.154 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.032 | -0.014 | -0.055 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.028 | 0.111 | -0.038 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.021 | -0.005 | -0.061 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.02 | -0.05 | 0.1 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.015 | -0.004 | -0.041 | neutral | CONTEXT |

### corepce_gap — Core PCE YoY − 2% target

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.26 | None | -0.313 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.179 | -0.272 | -0.089 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.178 | -0.229 | -0.175 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.16 | -0.307 | -0.079 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.151 | None | -0.151 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.145 | -0.13 | -0.176 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.137 | 0.024 | -0.23 | headwind | CONTEXT |
| XLK (Technology) | -0.127 | -0.287 | -0.06 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.108 | -0.184 | -0.123 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.103 | -0.172 | -0.079 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.097 | -0.097 | -0.093 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.089 | -0.091 | -0.11 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.085 | -0.14 | -0.059 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | -0.063 | 0.125 | -0.201 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.041 | 0.034 | 0.247 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.038 | -0.065 | 0.172 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.025 | 0.049 | -0.054 | neutral | CONTEXT |
| GC=F (Gold) | 0.022 | -0.044 | 0.021 | neutral | CONTEXT |

### infl_accel — Inflation re-acceleration (3m−12m)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.198 | -0.191 | -0.191 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | 0.118 | 0.056 | 0.147 | tailwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.097 | 0.081 | 0.12 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.09 | -0.136 | -0.036 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.079 | -0.027 | 0.159 | tailwind | CONTEXT |
| GC=F (Gold) | -0.077 | -0.009 | -0.157 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.072 | -0.095 | -0.043 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.071 | -0.136 | -0.001 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.071 | None | 0.071 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.068 | -0.09 | -0.049 | headwind | DIRECTIONAL |
| XLK (Technology) | -0.065 | -0.101 | -0.034 | headwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.034 | -0.069 | 0.149 | neutral | CONTEXT |
| HG=F (Copper) | 0.025 | 0.044 | -0.021 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.023 | 0.079 | -0.011 | neutral | CONTEXT |
| SPY (S&P 500) | -0.018 | -0.019 | -0.022 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.014 | 0.064 | -0.046 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.014 | 0.09 | -0.07 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.008 | None | -0.034 | neutral | CONTEXT |

### exp_wedge — Expectations wedge (mkt − model)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.262 | -0.302 | -0.266 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | 0.201 | 0.282 | 0.082 | tailwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.164 | -0.297 | -0.135 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.14 | 0.17 | 0.129 | tailwind | CONFIRMED |
| HG=F (Copper) | -0.138 | -0.249 | -0.041 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | 0.129 | 0.165 | 0.026 | tailwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | 0.125 | None | 0.178 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.086 | None | 0.086 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.072 | 0.166 | 0.025 | tailwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | 0.064 | -0.102 | 0.259 | tailwind | CONTEXT |
| XLK (Technology) | -0.052 | 0.014 | -0.077 | headwind | CONTEXT |
| SPY (S&P 500) | 0.042 | 0.138 | -0.046 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.023 | -0.005 | -0.086 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | -0.042 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.011 | 0.038 | -0.06 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.009 | -0.046 | 0.028 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.007 | 0.08 | -0.121 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.005 | -0.059 | 0.026 | neutral | CONTEXT |

### curvature — 2s5s10s curvature (butterfly)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| SPY (S&P 500) | -0.232 | -0.131 | -0.385 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.222 | None | -0.176 | headwind | CONTEXT |
| XLK (Technology) | -0.221 | -0.121 | -0.328 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.205 | -0.098 | -0.31 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.204 | -0.109 | -0.327 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.194 | -0.116 | -0.31 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.175 | -0.156 | -0.231 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.166 | 0.305 | -0.019 | tailwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.101 | -0.136 | -0.073 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.097 | None | -0.097 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.078 | -0.072 | -0.084 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.075 | -0.085 | -0.045 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.054 | 0.068 | -0.213 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.04 | -0.045 | 0.004 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.03 | -0.033 | -0.029 | neutral | CONTEXT |
| GC=F (Gold) | -0.025 | 0.129 | -0.253 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.023 | 0.014 | -0.123 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.0 | -0.028 | 0.111 | neutral | CONTEXT |

### slope_chg63 — 2s10s 63d change (steepening)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLRE (Real Estate (rate-sensitive)) | 0.321 | None | 0.321 | tailwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.166 | None | 0.144 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.112 | 0.028 | 0.215 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.098 | -0.121 | -0.098 | headwind | DIRECTIONAL |
| GC=F (Gold) | 0.095 | 0.014 | 0.204 | tailwind | DIRECTIONAL |
| HG=F (Copper) | -0.073 | -0.199 | 0.108 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.06 | -0.068 | 0.292 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.06 | 0.009 | 0.151 | tailwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.054 | -0.029 | -0.126 | headwind | DIRECTIONAL |
| SPY (S&P 500) | 0.046 | -0.083 | 0.318 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.042 | -0.061 | 0.207 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.035 | -0.045 | -0.054 | neutral | CONTEXT |
| XLK (Technology) | 0.025 | -0.105 | 0.257 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.014 | -0.036 | 0.03 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.012 | -0.099 | 0.201 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.011 | -0.009 | 0.056 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.008 | -0.078 | 0.152 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.004 | -0.139 | 0.224 | neutral | CONTEXT |

### ntfs — Near-term forward spread

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLB (Materials (inflation beneficiary)) | -0.213 | -0.237 | -0.189 | headwind | CONFIRMED |
| XLK (Technology) | -0.209 | -0.063 | -0.322 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.201 | -0.106 | -0.351 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.195 | -0.099 | -0.28 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.179 | None | -0.143 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.172 | -0.036 | -0.33 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.128 | -0.046 | -0.241 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.113 | -0.17 | -0.151 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.105 | -0.156 | -0.036 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.105 | 0.203 | -0.042 | tailwind | CONTEXT |
| GC=F (Gold) | -0.093 | 0.103 | -0.323 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.058 | -0.09 | -0.041 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | -0.053 | -0.064 | -0.041 | headwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | -0.051 | -0.083 | -0.009 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.046 | None | -0.046 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.033 | 0.089 | -0.001 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.023 | -0.013 | 0.146 | neutral | CONTEXT |
| HG=F (Copper) | -0.012 | 0.141 | -0.18 | neutral | CONTEXT |

### real_speed_abs — |Real 10y 63d speed| (violence)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.121 | 0.067 | 0.174 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.099 | -0.156 | -0.008 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.054 | None | 0.054 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.051 | -0.111 | 0.016 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | 0.033 | -0.008 | 0.079 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.029 | -0.006 | 0.059 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.026 | -0.0 | 0.05 | neutral | CONTEXT |
| SPY (S&P 500) | -0.022 | -0.05 | 0.011 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.019 | -0.028 | -0.006 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.017 | -0.051 | 0.027 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.015 | None | -0.028 | neutral | CONTEXT |
| XLK (Technology) | -0.014 | -0.022 | 0.002 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.011 | -0.037 | 0.054 | neutral | CONTEXT |
| HG=F (Copper) | 0.008 | 0.003 | -0.013 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.003 | -0.091 | 0.084 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.001 | 0.001 | 0.01 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.001 | 0.021 | -0.04 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | -0.001 | 0.073 | -0.085 | neutral | CONTEXT |

### trend_spread — 3m10y trend (2y smooth, Faria-Verona)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.124 | 0.123 | 0.032 | tailwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.115 | 0.239 | -0.07 | tailwind | CONTEXT |
| GC=F (Gold) | -0.101 | 0.043 | -0.327 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.098 | 0.253 | -0.128 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.09 | 0.174 | -0.053 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.073 | 0.237 | -0.172 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.065 | None | -0.065 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.058 | 0.161 | -0.098 | tailwind | CONTEXT |
| HG=F (Copper) | 0.046 | 0.204 | -0.218 | tailwind | CONTEXT |
| XLK (Technology) | -0.041 | 0.149 | -0.184 | headwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.032 | 0.21 | -0.181 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.032 | -0.051 | 0.079 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.026 | 0.093 | -0.108 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.024 | 0.038 | 0.002 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.021 | -0.152 | -0.091 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.017 | 0.144 | -0.192 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.012 | None | 0.066 | neutral | CONTEXT |
| SPY (S&P 500) | -0.005 | 0.144 | -0.263 | neutral | CONTEXT |

## Collinearity vs already-scored legs

VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in the inflation axis is caught here and NOT double-counted.

| driver | VIF |
|---|--:|
| be5y5y | 16.63 |
| exp_wedge | 15.68 |
| ntfs | 14.3 |
| policy_gap | 11.52 |
| real10y | 10.74 |
| curve_tp_adj | 7.83 |
| trend_spread | 3.76 |
| corepce_gap | 3.61 |
| slope_chg63 | 2.91 |
| curvature | 2.87 |
| infl_accel | 1.97 |
| _scored_be10y_chg | 1.77 |
| _scored_sticky_dir | 1.55 |
| real_speed_abs | 1.36 |
| be10y_chg63 | -26270903491404.36 |
| real10y_chg63 | -40479982565628.38 |
| be10y | -47937341180701.81 |
| _scored_tips_nominal | -47937488211323.02 |
| nom10y_chg63 | -57706691538145.27 |

Top correlated pairs:

- `be10y` ↔ `_scored_tips_nominal`: 1.0
- `policy_gap` ↔ `ntfs`: 0.88
- `be10y` ↔ `be5y5y`: 0.78
- `be5y5y` ↔ `_scored_tips_nominal`: 0.78
- `real10y_chg63` ↔ `nom10y_chg63`: 0.74
- `curvature` ↔ `ntfs`: 0.71
- `ntfs` ↔ `trend_spread`: 0.68
- `curve_tp_adj` ↔ `ntfs`: 0.67
- `curve_tp_adj` ↔ `trend_spread`: 0.64
- `policy_gap` ↔ `trend_spread`: 0.62
- `real10y` ↔ `exp_wedge`: 0.61
- `policy_gap` ↔ `curvature`: 0.6