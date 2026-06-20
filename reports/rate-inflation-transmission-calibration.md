# Rate & inflation transmission — calibration report

As-of **2026-06-18**. Forward horizon **63 days**; split-half boundary **2015-01-01**. Transmission = signed Spearman IC(driver_t, asset forward 63d return); display-only coefficients. Scored gate = driver as STRESS vs forward 63d S&P drawdown (calibrate_bonds discipline) + purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West return-forecast bar. No look-ahead.

Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = weak/unstable; **INVERTED** = predicts the wrong way.

## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?

Each driver, expressed as STRESS (higher = more risk-off), vs the forward 63-day S&P drawdown — the same discriminative bar the bond-health legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it predicts the LEVEL of returns; a leg can flag RISK without forecasting return.

| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |
|---|---|---|:--:|--:|---|--:|--:|:--:|
| real10y_chg63 (Real-rate SPEED (63d rise) — 'speed breaks equities') | **DIRECTIONAL** | 0.139/0.052/0.222 | False | 7.2pp | [0.106, 0.198, 0.304] | -1.106 | -0.10517 | — |
| real10y (Real-rate LEVEL (high real yields)) | **DIRECTIONAL** | 0.047/0.053/0.004 | False | -1.0pp | [0.036, 0.115, 0.218] | -0.932 | -0.17087 | — |
| corepce_gap (Core-PCE-vs-target gap (sticky inflation)) | **DIRECTIONAL** | 0.042/0.009/0.13 | False | 0.2pp | [0.074, 0.123, 0.179] | 1.67 | -0.31096 | — |
| infl_accel (Inflation re-acceleration (3m>12m)) | **DIRECTIONAL** | 0.053/0.049/0.073 | False | 4.0pp | [0.104, 0.163, 0.227] | -1.192 | -0.1281 | — |
| exp_wedge (Expectations unanchoring (market>model)) | **INVERTED** | -0.054/-0.05/-0.106 | False | -6.2pp | [0.016, 0.065, 0.137] | 2.151 | -0.099 | — |
| curve_tp_adj (TP-adjusted curve inversion (flip: low=stress)) | **CONTEXT** | 0.005/0.01/0.031 | False | -0.7pp | [0.062, 0.11, 0.167] | -1.026 | -0.25953 | — |
| nom10y_chg63 (Nominal-rate SPEED (63d rise)) | **DIRECTIONAL** | 0.095/0.068/0.208 | False | -0.4pp | [0.073, 0.118, 0.174] | 0.642 | -0.11508 | — |
| ntfs (Near-term forward spread inversion (flip: low=stress; Engstrom-Sharpe beats 2s10s)) | **CONTEXT** | -0.018/0.048/-0.213 | False | -1.2pp | [0.058, 0.103, 0.161] | -0.629 | -0.26525 | — |
| curvature (Curve curvature (2s5s10s butterfly — humped = late-cycle)) | **CONTEXT** | 0.032/-0.013/0.177 | False | -0.1pp | [0.063, 0.115, 0.176] | -1.347 | -0.30873 | — |
| real_speed_abs (Real-rate move VIOLENCE (|63d speed|, either direction)) | **DIRECTIONAL** | 0.112/0.161/0.057 | False | 3.0pp | [0.081, 0.159, 0.249] | -1.203 | -0.11284 | — |
| slope_chg63 (Curve flattening impulse (flip: − = flattening = stress; INVERTED if post-inversion steepening is the tell)) | **CONTEXT** | -0.032/-0.085/0.169 | False | -2.1pp | [0.054, 0.096, 0.148] | 0.755 | -0.12276 | — |
| trend_spread (3m10y TREND inversion (flip: low trend = stress) — Faria-Verona OOS equity-premium claim, tested on the return-forecast bar) | **CONTEXT** | 0.163/0.234/-0.031 | False | 6.4pp | [0.124, 0.187, 0.255] | 3.567 | -0.27277 | — |

**Scored-eligible legs: NONE — every rate/inflation leg here is display-only context.** Eligible legs are PROPOSED for a config-gated MRS/drawdown leg, adopted only if they hold on the next refresh (the bonds restraint).

## Transmission matrix — per-asset forward pass-through

Signed Spearman IC of each rate/inflation driver vs each asset's forward 63-day return. Positive = tailwind, negative = headwind. These are the DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells are sign-stable across both halves.

### real10y — Real 10y yield (level)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.361 | 0.374 | 0.353 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.274 | -0.31 | -0.184 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | 0.183 | 0.266 | 0.095 | tailwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.175 | 0.122 | 0.201 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.171 | -0.271 | -0.104 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.138 | -0.18 | -0.076 | headwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.135 | 0.13 | 0.114 | tailwind | CONFIRMED |
| HG=F (Copper) | 0.13 | 0.19 | -0.048 | tailwind | CONTEXT |
| SPY (S&P 500) | -0.059 | -0.139 | 0.048 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.059 | -0.159 | -0.006 | headwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | -0.046 | None | -0.06 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.037 | 0.119 | -0.266 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.028 | 0.058 | -0.081 | neutral | CONTEXT |
| XLK (Technology) | -0.027 | -0.039 | 0.063 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.018 | None | 0.018 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.014 | -0.069 | 0.073 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.013 | -0.1 | 0.034 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.011 | 0.075 | -0.138 | neutral | CONTEXT |

### real10y_chg63 — Real 10y — 63d change (speed)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.311 | None | -0.3 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.215 | -0.198 | -0.224 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.196 | -0.197 | -0.197 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.194 | -0.167 | -0.223 | headwind | CONFIRMED |
| XLK (Technology) | -0.193 | -0.209 | -0.193 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.181 | -0.17 | -0.178 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.174 | -0.131 | -0.218 | headwind | CONFIRMED |
| HG=F (Copper) | -0.168 | -0.162 | -0.146 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.161 | -0.109 | -0.225 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.146 | 0.225 | 0.079 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.127 | -0.116 | -0.127 | headwind | CONFIRMED |
| XLE (Energy (inflation beneficiary)) | -0.112 | -0.142 | -0.061 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.08 | 0.018 | -0.173 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.042 | -0.0 | -0.079 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.024 | None | 0.024 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.022 | 0.004 | -0.036 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.006 | 0.005 | -0.002 | neutral | CONTEXT |
| GC=F (Gold) | -0.002 | 0.052 | -0.058 | neutral | CONTEXT |

### nom10y_chg63 — Nominal 10y — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.24 | None | -0.27 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.141 | -0.086 | -0.231 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.123 | -0.092 | -0.192 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.103 | -0.052 | -0.198 | headwind | CONFIRMED |
| XLK (Technology) | -0.099 | -0.053 | -0.196 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.099 | 0.047 | -0.224 | headwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.087 | 0.004 | -0.211 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.076 | 0.137 | 0.041 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.06 | -0.04 | -0.097 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.044 | -0.004 | -0.1 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.04 | 0.052 | -0.179 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.038 | 0.054 | -0.194 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.038 | -0.042 | 0.013 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.036 | None | 0.036 | neutral | CONTEXT |
| HG=F (Copper) | -0.034 | 0.014 | -0.123 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.032 | 0.049 | 0.002 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.027 | 0.029 | -0.111 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.012 | 0.064 | -0.054 | neutral | CONTEXT |

### be10y — 10y breakeven (inflation comp.)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.308 | None | -0.334 | headwind | CONTEXT |
| XLK (Technology) | -0.285 | -0.37 | -0.151 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.279 | -0.38 | -0.164 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.225 | -0.281 | -0.26 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.222 | -0.243 | -0.251 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.221 | -0.281 | -0.151 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.199 | -0.174 | -0.213 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.16 | -0.1 | -0.264 | headwind | CONFIRMED |
| HG=F (Copper) | -0.123 | -0.176 | -0.122 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.112 | -0.177 | -0.09 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.109 | -0.193 | -0.104 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.1 | 0.143 | 0.159 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.095 | None | -0.095 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.065 | -0.027 | -0.16 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.061 | -0.045 | 0.081 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.054 | 0.152 | -0.114 | tailwind | CONTEXT |
| GC=F (Gold) | -0.051 | -0.165 | 0.071 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.045 | 0.048 | 0.006 | tailwind | DIRECTIONAL |

### be10y_chg63 — 10y breakeven — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.119 | -0.075 | -0.143 | headwind | CONFIRMED |
| GC=F (Gold) | -0.118 | -0.156 | -0.078 | headwind | CONFIRMED |
| HG=F (Copper) | 0.096 | 0.189 | -0.06 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.081 | 0.228 | -0.084 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | 0.069 | 0.151 | -0.018 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.066 | 0.121 | 0.026 | tailwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | 0.06 | 0.082 | 0.034 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.049 | -0.028 | -0.073 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | 0.045 | 0.113 | -0.075 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.044 | 0.036 | -0.144 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.041 | -0.062 | 0.031 | headwind | CONTEXT |
| XLK (Technology) | -0.04 | -0.012 | -0.08 | neutral | CONTEXT |
| SPY (S&P 500) | 0.028 | 0.107 | -0.058 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.024 | None | 0.024 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.018 | 0.075 | -0.165 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.008 | 0.092 | -0.106 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.006 | None | -0.055 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | -0.001 | -0.014 | 0.031 | neutral | CONTEXT |

### be5y5y — 5y5y forward breakeven (anchor)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.307 | None | -0.288 | headwind | CONTEXT |
| XLK (Technology) | -0.261 | -0.272 | -0.143 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.213 | -0.272 | -0.134 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.205 | 0.261 | -0.041 | tailwind | CONTEXT |
| HG=F (Copper) | -0.198 | -0.409 | -0.189 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.166 | -0.167 | -0.132 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.164 | -0.302 | -0.277 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.149 | -0.085 | -0.178 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.135 | -0.195 | -0.205 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.13 | -0.165 | -0.257 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.109 | -0.306 | -0.176 | headwind | CONFIRMED |
| GC=F (Gold) | -0.076 | -0.243 | 0.077 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.072 | 0.205 | 0.131 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.066 | None | -0.066 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.053 | 0.045 | -0.016 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.022 | -0.073 | -0.121 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.011 | -0.13 | -0.038 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.008 | 0.017 | -0.083 | neutral | CONTEXT |

### curve_tp_adj — TP-adjusted 2s10s curve

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.238 | 0.246 | 0.163 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | 0.158 | None | 0.158 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.145 | -0.08 | -0.176 | headwind | CONFIRMED |
| XLK (Technology) | -0.117 | 0.009 | -0.124 | headwind | CONTEXT |
| SPY (S&P 500) | -0.097 | -0.067 | -0.144 | headwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | -0.096 | None | -0.042 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.08 | -0.266 | -0.062 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.063 | 0.036 | -0.134 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.056 | -0.065 | 0.019 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.043 | -0.046 | -0.085 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | 0.043 | 0.049 | 0.021 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.035 | -0.086 | -0.008 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.031 | 0.048 | 0.034 | neutral | CONTEXT |
| XLP (Staples (defensive)) | -0.023 | -0.023 | 0.009 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | 0.033 | -0.089 | neutral | CONTEXT |
| GC=F (Gold) | -0.017 | 0.112 | -0.105 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | 0.123 | neutral | CONTEXT |
| HG=F (Copper) | 0.003 | 0.07 | -0.071 | neutral | CONTEXT |

### policy_gap — us2y − funds (cut/hike pricing)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.192 | None | -0.171 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.177 | -0.171 | -0.18 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.165 | -0.059 | -0.351 | headwind | CONFIRMED |
| XLK (Technology) | -0.165 | -0.028 | -0.308 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.153 | -0.016 | -0.324 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.14 | -0.031 | -0.294 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.099 | -0.085 | -0.157 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.096 | -0.0 | -0.241 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.073 | 0.125 | -0.302 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.071 | -0.087 | -0.054 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.071 | 0.189 | -0.045 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.062 | None | -0.062 | headwind | CONTEXT |
| HG=F (Copper) | 0.058 | 0.224 | -0.156 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.032 | -0.014 | -0.053 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.027 | 0.111 | -0.035 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.02 | -0.005 | -0.063 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.02 | -0.05 | 0.097 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.016 | -0.004 | -0.041 | neutral | CONTEXT |

### corepce_gap — Core PCE YoY − 2% target

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.254 | None | -0.307 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.19 | -0.272 | -0.107 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.186 | -0.229 | -0.186 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.167 | -0.307 | -0.087 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.156 | None | -0.156 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.143 | -0.13 | -0.171 | headwind | CONFIRMED |
| XLK (Technology) | -0.138 | -0.287 | -0.075 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.129 | 0.024 | -0.22 | headwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.116 | -0.184 | -0.135 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.108 | -0.172 | -0.087 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.089 | -0.091 | -0.111 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.089 | -0.14 | -0.064 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.088 | -0.097 | -0.081 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | -0.058 | 0.125 | -0.198 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.043 | -0.065 | 0.181 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.04 | 0.034 | 0.239 | tailwind | DIRECTIONAL |
| GC=F (Gold) | 0.035 | -0.044 | 0.044 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.031 | 0.049 | -0.042 | neutral | CONTEXT |

### infl_accel — Inflation re-acceleration (3m−12m)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.194 | -0.191 | -0.182 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | 0.126 | 0.056 | 0.164 | tailwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.1 | 0.081 | 0.129 | tailwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.095 | -0.136 | -0.047 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.084 | -0.027 | 0.169 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.078 | -0.095 | -0.055 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.077 | -0.136 | -0.013 | headwind | DIRECTIONAL |
| XLK (Technology) | -0.073 | -0.101 | -0.05 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.07 | -0.009 | -0.141 | headwind | DIRECTIONAL |
| XLB (Materials (inflation beneficiary)) | -0.066 | -0.09 | -0.046 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.065 | None | 0.065 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.035 | -0.069 | 0.143 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.026 | 0.079 | -0.008 | neutral | CONTEXT |
| SPY (S&P 500) | -0.022 | -0.019 | -0.033 | neutral | CONTEXT |
| HG=F (Copper) | 0.021 | 0.044 | -0.031 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.014 | 0.064 | -0.047 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.008 | 0.09 | -0.085 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.002 | None | -0.024 | neutral | CONTEXT |

### exp_wedge — Expectations wedge (mkt − model)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.282 | -0.302 | -0.31 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | 0.218 | 0.282 | 0.114 | tailwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.176 | -0.297 | -0.155 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.149 | 0.17 | 0.148 | tailwind | CONFIRMED |
| HG=F (Copper) | -0.134 | -0.249 | -0.029 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.129 | 0.165 | 0.028 | tailwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | 0.111 | None | 0.164 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.095 | None | 0.095 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.083 | 0.166 | 0.045 | tailwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | 0.052 | -0.102 | 0.239 | tailwind | CONTEXT |
| SPY (S&P 500) | 0.05 | 0.138 | -0.033 | tailwind | CONTEXT |
| XLK (Technology) | -0.04 | 0.014 | -0.056 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.024 | -0.041 | -0.061 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.019 | -0.005 | -0.094 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.016 | 0.08 | -0.105 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.004 | 0.038 | -0.049 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.003 | -0.046 | 0.019 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.001 | -0.059 | 0.017 | neutral | CONTEXT |

### curvature — 2s5s10s curvature (butterfly)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.231 | None | -0.185 | headwind | CONTEXT |
| SPY (S&P 500) | -0.229 | -0.131 | -0.384 | headwind | CONFIRMED |
| XLK (Technology) | -0.217 | -0.121 | -0.324 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.202 | -0.109 | -0.326 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.2 | -0.098 | -0.305 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.19 | -0.116 | -0.305 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.179 | -0.156 | -0.237 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.164 | 0.305 | -0.025 | tailwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.105 | -0.136 | -0.076 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.096 | None | -0.096 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.075 | -0.085 | -0.045 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | -0.072 | -0.072 | -0.073 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.051 | 0.068 | -0.209 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.047 | -0.045 | -0.006 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.034 | 0.129 | -0.273 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.033 | -0.033 | -0.036 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.028 | 0.014 | -0.131 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.002 | -0.028 | 0.117 | neutral | CONTEXT |

### slope_chg63 — 2s10s 63d change (steepening)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLRE (Real Estate (rate-sensitive)) | 0.328 | None | 0.328 | tailwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.159 | None | 0.136 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.11 | 0.028 | 0.212 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.1 | -0.121 | -0.104 | headwind | CONFIRMED |
| GC=F (Gold) | 0.089 | 0.014 | 0.192 | tailwind | DIRECTIONAL |
| HG=F (Copper) | -0.07 | -0.199 | 0.115 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.062 | -0.068 | 0.301 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.058 | 0.009 | 0.148 | tailwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.053 | -0.029 | -0.117 | headwind | DIRECTIONAL |
| SPY (S&P 500) | 0.049 | -0.083 | 0.328 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.045 | -0.061 | 0.217 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.04 | -0.045 | -0.067 | headwind | DIRECTIONAL |
| XLK (Technology) | 0.03 | -0.105 | 0.271 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.018 | -0.036 | 0.022 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.016 | -0.009 | 0.07 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.009 | -0.099 | 0.193 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.008 | -0.078 | 0.153 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.0 | -0.139 | 0.236 | neutral | CONTEXT |

### ntfs — Near-term forward spread

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLB (Materials (inflation beneficiary)) | -0.224 | -0.251 | -0.198 | headwind | CONFIRMED |
| XLK (Technology) | -0.213 | -0.066 | -0.336 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.198 | -0.1 | -0.364 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.196 | -0.097 | -0.294 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.19 | None | -0.155 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.177 | -0.039 | -0.343 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.134 | -0.053 | -0.254 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.113 | -0.169 | -0.037 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.111 | -0.161 | -0.15 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.108 | 0.205 | -0.035 | tailwind | CONTEXT |
| GC=F (Gold) | -0.09 | 0.109 | -0.315 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.059 | -0.078 | -0.048 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.058 | -0.086 | -0.045 | headwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | -0.054 | -0.087 | -0.009 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.049 | None | -0.049 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.024 | 0.086 | -0.013 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.014 | -0.042 | 0.137 | neutral | CONTEXT |
| HG=F (Copper) | -0.01 | 0.143 | -0.181 | neutral | CONTEXT |

### real_speed_abs — |Real 10y 63d speed| (violence)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.111 | 0.067 | 0.155 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.094 | -0.156 | 0.004 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.057 | None | 0.057 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.045 | -0.111 | 0.029 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | 0.028 | -0.008 | 0.07 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.027 | None | -0.041 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.025 | -0.006 | 0.055 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.022 | -0.0 | 0.042 | neutral | CONTEXT |
| SPY (S&P 500) | -0.018 | -0.05 | 0.019 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.013 | -0.028 | 0.006 | neutral | CONTEXT |
| HG=F (Copper) | 0.011 | 0.003 | -0.005 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.01 | -0.037 | 0.054 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | -0.01 | 0.073 | -0.106 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.009 | -0.091 | 0.074 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.007 | -0.051 | 0.048 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.006 | 0.001 | 0.017 | neutral | CONTEXT |
| XLK (Technology) | -0.006 | -0.022 | 0.017 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.005 | 0.021 | -0.047 | neutral | CONTEXT |

### trend_spread — 3m10y trend (2y smooth, Faria-Verona)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.121 | 0.123 | 0.028 | tailwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.116 | 0.239 | -0.071 | tailwind | CONTEXT |
| GC=F (Gold) | -0.114 | 0.043 | -0.354 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.101 | 0.174 | -0.038 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.097 | -0.131 | 0.089 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.094 | 0.253 | -0.139 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.082 | 0.237 | -0.161 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.064 | None | -0.064 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.053 | 0.161 | -0.106 | tailwind | CONTEXT |
| HG=F (Copper) | 0.051 | 0.204 | -0.212 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.04 | 0.21 | -0.172 | tailwind | CONTEXT |
| XLK (Technology) | -0.032 | 0.149 | -0.173 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.029 | -0.152 | -0.1 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.023 | 0.093 | -0.116 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.014 | 0.038 | -0.016 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.012 | 0.144 | -0.188 | neutral | CONTEXT |
| SPY (S&P 500) | 0.0 | 0.144 | -0.258 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.0 | None | 0.054 | neutral | CONTEXT |

## Collinearity vs already-scored legs

VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in the inflation axis is caught here and NOT double-counted.

| driver | VIF |
|---|--:|
| be5y5y | 16.65 |
| exp_wedge | 15.49 |
| ntfs | 13.92 |
| policy_gap | 11.6 |
| real10y | 10.32 |
| curve_tp_adj | 7.66 |
| trend_spread | 3.8 |
| corepce_gap | 3.54 |
| curvature | 2.91 |
| slope_chg63 | 2.9 |
| infl_accel | 1.97 |
| _scored_be10y_chg | 1.77 |
| _scored_sticky_dir | 1.54 |
| real_speed_abs | 1.37 |
| be10y_chg63 | -27555031480173.53 |
| real10y_chg63 | -42245656143770.22 |
| be10y | -50340055167067.48 |
| _scored_tips_nominal | -50340210489382.44 |
| nom10y_chg63 | -60532940210911.03 |

Top correlated pairs:

- `be10y` ↔ `_scored_tips_nominal`: 1.0
- `policy_gap` ↔ `ntfs`: 0.89
- `be10y` ↔ `be5y5y`: 0.78
- `be5y5y` ↔ `_scored_tips_nominal`: 0.78
- `real10y_chg63` ↔ `nom10y_chg63`: 0.74
- `curvature` ↔ `ntfs`: 0.72
- `curve_tp_adj` ↔ `ntfs`: 0.67
- `ntfs` ↔ `trend_spread`: 0.67
- `curve_tp_adj` ↔ `trend_spread`: 0.64
- `policy_gap` ↔ `trend_spread`: 0.63
- `real10y` ↔ `exp_wedge`: 0.61
- `policy_gap` ↔ `curvature`: 0.6