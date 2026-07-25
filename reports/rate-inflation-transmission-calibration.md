# Rate & inflation transmission — calibration report

As-of **2026-07-24**. Forward horizon **63 days**; split-half boundary **2015-01-01**. Transmission = signed Spearman IC(driver_t, asset forward 63d return); display-only coefficients. Scored gate = driver as STRESS vs forward 63d S&P drawdown (calibrate_bonds discipline) + purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West return-forecast bar. No look-ahead.

Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = weak/unstable; **INVERTED** = predicts the wrong way.

## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?

Each driver, expressed as STRESS (higher = more risk-off), vs the forward 63-day S&P drawdown — the same discriminative bar the bond-health legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it predicts the LEVEL of returns; a leg can flag RISK without forecasting return.

| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |
|---|---|---|:--:|--:|---|--:|--:|:--:|
| real10y_chg63 (Real-rate SPEED (63d rise) — 'speed breaks equities') | **DIRECTIONAL** | 0.136/0.052/0.218 | True | 7.1pp | [0.105, 0.197, 0.3] | -0.96 | -0.10259 | — |
| real10y (Real-rate LEVEL (high real yields)) | **CONTEXT** | 0.041/0.053/-0.01 | False | -0.9pp | [0.036, 0.115, 0.218] | -0.825 | -0.16775 | — |
| corepce_gap (Core-PCE-vs-target gap (sticky inflation)) | **DIRECTIONAL** | 0.072/0.058/0.12 | False | 0.6pp | [0.077, 0.122, 0.173] | 1.712 | -0.3084 | — |
| infl_accel (Inflation re-acceleration (3m>12m)) | **DIRECTIONAL** | 0.065/0.066/0.063 | False | 4.3pp | [0.107, 0.16, 0.215] | -1.081 | -0.12612 | — |
| exp_wedge (Expectations unanchoring (market>model)) | **INVERTED** | -0.044/-0.05/-0.086 | False | -6.1pp | [0.016, 0.066, 0.137] | 2.295 | -0.09583 | — |
| curve_tp_adj (TP-adjusted curve inversion (flip: low=stress)) | **CONTEXT** | 0.005/0.01/0.042 | False | -0.7pp | [0.062, 0.11, 0.167] | -0.991 | -0.2576 | — |
| nom10y_chg63 (Nominal-rate SPEED (63d rise)) | **DIRECTIONAL** | 0.116/0.097/0.203 | False | -0.1pp | [0.077, 0.118, 0.165] | 0.713 | -0.11352 | — |
| ntfs (Near-term forward spread inversion (flip: low=stress; Engstrom-Sharpe beats 2s10s)) | **CONTEXT** | -0.02/0.048/-0.21 | False | -1.4pp | [0.057, 0.103, 0.16] | -0.711 | -0.2672 | — |
| curvature (Curve curvature (2s5s10s butterfly — humped = late-cycle)) | **CONTEXT** | 0.035/-0.013/0.183 | False | -0.2pp | [0.063, 0.115, 0.177] | -1.335 | -0.30729 | — |
| real_speed_abs (Real-rate move VIOLENCE (|63d speed|, either direction)) | **DIRECTIONAL** | 0.117/0.161/0.068 | False | 3.0pp | [0.08, 0.159, 0.249] | -1.085 | -0.11021 | — |
| slope_chg63 (Curve flattening impulse (flip: − = flattening = stress; INVERTED if post-inversion steepening is the tell)) | **CONTEXT** | -0.033/-0.085/0.16 | False | -2.1pp | [0.053, 0.096, 0.146] | 0.733 | -0.12276 | — |
| trend_spread (3m10y TREND inversion (flip: low trend = stress) — Faria-Verona OOS equity-premium claim, tested on the return-forecast bar) | **CONTEXT** | 0.14/0.195/-0.041 | False | 6.7pp | [0.127, 0.183, 0.244] | 3.639 | -0.27016 | — |

**Scored-eligible legs: NONE — every rate/inflation leg here is display-only context.** Eligible legs are PROPOSED for a config-gated MRS/drawdown leg, adopted only if they hold on the next refresh (the bonds restraint).

## Transmission matrix — per-asset forward pass-through

Signed Spearman IC of each rate/inflation driver vs each asset's forward 63-day return. Positive = tailwind, negative = headwind. These are the DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells are sign-stable across both halves.

### real10y — Real 10y yield (level)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.351 | 0.374 | 0.327 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.27 | -0.31 | -0.175 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | 0.176 | 0.266 | 0.083 | tailwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.173 | 0.122 | 0.197 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.165 | -0.271 | -0.087 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.133 | -0.18 | -0.063 | headwind | CONFIRMED |
| HG=F (Copper) | 0.132 | 0.19 | -0.039 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.13 | 0.13 | 0.103 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.059 | -0.159 | -0.005 | headwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | -0.054 | None | -0.069 | headwind | CONTEXT |
| SPY (S&P 500) | -0.053 | -0.139 | 0.061 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.042 | 0.119 | -0.277 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.026 | None | 0.026 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.026 | 0.058 | -0.084 | neutral | CONTEXT |
| XLK (Technology) | -0.02 | -0.039 | 0.08 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.008 | -0.069 | 0.087 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.008 | -0.1 | 0.048 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.008 | 0.075 | -0.144 | neutral | CONTEXT |

### real10y_chg63 — Real 10y — 63d change (speed)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.311 | None | -0.3 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.215 | -0.198 | -0.222 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.192 | -0.197 | -0.191 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.191 | -0.167 | -0.218 | headwind | CONFIRMED |
| XLK (Technology) | -0.189 | -0.209 | -0.187 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.183 | -0.17 | -0.179 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.171 | -0.131 | -0.213 | headwind | CONFIRMED |
| HG=F (Copper) | -0.166 | -0.162 | -0.144 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.159 | -0.109 | -0.222 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.146 | 0.225 | 0.08 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.127 | -0.116 | -0.126 | headwind | CONFIRMED |
| XLE (Energy (inflation beneficiary)) | -0.114 | -0.142 | -0.063 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.081 | 0.018 | -0.175 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.04 | -0.0 | -0.076 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.027 | None | 0.027 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.023 | 0.004 | -0.037 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.007 | 0.005 | 0.001 | neutral | CONTEXT |
| GC=F (Gold) | -0.004 | 0.052 | -0.06 | neutral | CONTEXT |

### nom10y_chg63 — Nominal 10y — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.242 | None | -0.272 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.141 | -0.086 | -0.231 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.121 | -0.092 | -0.186 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.101 | -0.052 | -0.191 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.101 | 0.047 | -0.226 | headwind | CONTEXT |
| XLK (Technology) | -0.096 | -0.053 | -0.189 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.084 | 0.004 | -0.205 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.075 | 0.137 | 0.041 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.063 | -0.04 | -0.101 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.044 | -0.004 | -0.1 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.042 | 0.052 | -0.181 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.039 | None | 0.039 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.036 | 0.054 | -0.189 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.036 | -0.041 | 0.016 | neutral | CONTEXT |
| HG=F (Copper) | -0.033 | 0.014 | -0.119 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.03 | 0.049 | -0.0 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.028 | 0.029 | -0.113 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.013 | 0.064 | -0.05 | neutral | CONTEXT |

### be10y — 10y breakeven (inflation comp.)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.315 | None | -0.341 | headwind | CONTEXT |
| XLK (Technology) | -0.278 | -0.37 | -0.134 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.274 | -0.38 | -0.151 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.226 | -0.281 | -0.264 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.218 | -0.243 | -0.238 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.217 | -0.281 | -0.141 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.195 | -0.174 | -0.203 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.163 | -0.1 | -0.271 | headwind | CONFIRMED |
| HG=F (Copper) | -0.121 | -0.176 | -0.115 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.109 | -0.193 | -0.103 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.107 | -0.177 | -0.077 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.102 | 0.143 | 0.166 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.091 | None | -0.091 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.069 | -0.027 | -0.17 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.058 | -0.045 | 0.074 | tailwind | CONTEXT |
| GC=F (Gold) | -0.056 | -0.165 | 0.053 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.052 | 0.152 | -0.117 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.041 | 0.048 | -0.003 | tailwind | CONTEXT |

### be10y_chg63 — 10y breakeven — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.12 | -0.156 | -0.083 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.12 | -0.075 | -0.145 | headwind | CONFIRMED |
| HG=F (Copper) | 0.097 | 0.189 | -0.056 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.082 | 0.228 | -0.08 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | 0.069 | 0.151 | -0.018 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.067 | 0.121 | 0.029 | tailwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | 0.059 | 0.082 | 0.031 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.047 | -0.028 | -0.068 | headwind | DIRECTIONAL |
| XLB (Materials (inflation beneficiary)) | -0.045 | 0.036 | -0.145 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.044 | 0.113 | -0.078 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.039 | -0.062 | 0.033 | neutral | CONTEXT |
| XLK (Technology) | -0.037 | -0.012 | -0.074 | neutral | CONTEXT |
| SPY (S&P 500) | 0.029 | 0.107 | -0.054 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.026 | None | 0.026 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.02 | 0.075 | -0.167 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.009 | None | -0.058 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.006 | 0.092 | -0.1 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | -0.001 | -0.014 | 0.03 | neutral | CONTEXT |

### be5y5y — 5y5y forward breakeven (anchor)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.308 | None | -0.288 | headwind | CONTEXT |
| XLK (Technology) | -0.264 | -0.272 | -0.141 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.217 | -0.272 | -0.134 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.206 | 0.261 | -0.042 | tailwind | CONTEXT |
| HG=F (Copper) | -0.199 | -0.409 | -0.188 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.169 | -0.167 | -0.132 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.162 | -0.302 | -0.278 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.152 | -0.085 | -0.178 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.139 | -0.195 | -0.204 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.125 | -0.165 | -0.254 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.106 | -0.306 | -0.175 | headwind | CONFIRMED |
| GC=F (Gold) | -0.071 | -0.243 | 0.075 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.07 | 0.205 | 0.132 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.067 | None | -0.067 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.056 | 0.045 | -0.016 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.022 | -0.073 | -0.121 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.008 | -0.13 | -0.036 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.005 | 0.017 | -0.081 | neutral | CONTEXT |

### curve_tp_adj — TP-adjusted 2s10s curve

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.239 | 0.246 | 0.161 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | 0.163 | None | 0.163 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.146 | -0.08 | -0.168 | headwind | CONFIRMED |
| XLK (Technology) | -0.117 | 0.009 | -0.108 | headwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.103 | None | -0.05 | headwind | CONTEXT |
| SPY (S&P 500) | -0.098 | -0.067 | -0.133 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.081 | -0.266 | -0.072 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.063 | 0.036 | -0.12 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.056 | -0.065 | 0.026 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.043 | -0.046 | -0.089 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | 0.043 | 0.049 | 0.031 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.035 | -0.086 | -0.017 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.031 | 0.048 | 0.02 | neutral | CONTEXT |
| XLP (Staples (defensive)) | -0.023 | -0.023 | 0.009 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | 0.033 | -0.079 | neutral | CONTEXT |
| GC=F (Gold) | -0.017 | 0.112 | -0.119 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | 0.115 | neutral | CONTEXT |
| HG=F (Copper) | 0.002 | 0.07 | -0.066 | neutral | CONTEXT |

### policy_gap — us2y − funds (cut/hike pricing)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.192 | None | -0.17 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.175 | -0.171 | -0.179 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.166 | -0.059 | -0.347 | headwind | CONFIRMED |
| XLK (Technology) | -0.165 | -0.028 | -0.304 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.154 | -0.016 | -0.32 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.14 | -0.031 | -0.291 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.097 | -0.0 | -0.238 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.097 | -0.085 | -0.156 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.072 | 0.189 | -0.044 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.071 | -0.087 | -0.054 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.07 | 0.125 | -0.299 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.061 | None | -0.061 | headwind | CONTEXT |
| HG=F (Copper) | 0.058 | 0.224 | -0.155 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.031 | -0.014 | -0.054 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.028 | 0.111 | -0.036 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.021 | -0.005 | -0.062 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.02 | -0.05 | 0.099 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.015 | -0.004 | -0.041 | neutral | CONTEXT |

### corepce_gap — Core PCE YoY − 2% target

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.258 | None | -0.311 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.184 | -0.272 | -0.096 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.179 | -0.229 | -0.176 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.159 | -0.307 | -0.076 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.151 | None | -0.151 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.145 | -0.13 | -0.174 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.136 | 0.024 | -0.228 | headwind | CONTEXT |
| XLK (Technology) | -0.128 | -0.287 | -0.061 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.111 | -0.184 | -0.127 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.103 | -0.172 | -0.079 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.094 | -0.097 | -0.09 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.089 | -0.091 | -0.11 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.086 | -0.14 | -0.06 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | -0.062 | 0.125 | -0.2 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.041 | 0.034 | 0.245 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.039 | -0.065 | 0.173 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.026 | 0.049 | -0.051 | neutral | CONTEXT |
| GC=F (Gold) | 0.025 | -0.044 | 0.027 | neutral | CONTEXT |

### infl_accel — Inflation re-acceleration (3m−12m)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.198 | -0.191 | -0.19 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | 0.119 | 0.056 | 0.15 | tailwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.097 | 0.081 | 0.12 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.089 | -0.136 | -0.035 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.08 | -0.027 | 0.159 | tailwind | CONTEXT |
| GC=F (Gold) | -0.076 | -0.009 | -0.154 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.073 | -0.095 | -0.046 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.072 | -0.136 | -0.001 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.071 | None | 0.071 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.067 | -0.09 | -0.049 | headwind | DIRECTIONAL |
| XLK (Technology) | -0.065 | -0.101 | -0.034 | headwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.034 | -0.069 | 0.148 | neutral | CONTEXT |
| HG=F (Copper) | 0.024 | 0.044 | -0.023 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.023 | 0.079 | -0.011 | neutral | CONTEXT |
| SPY (S&P 500) | -0.018 | -0.019 | -0.022 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.014 | 0.064 | -0.046 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.012 | 0.09 | -0.074 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.006 | None | -0.032 | neutral | CONTEXT |

### exp_wedge — Expectations wedge (mkt − model)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.267 | -0.302 | -0.279 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | 0.208 | 0.282 | 0.094 | tailwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.166 | -0.297 | -0.138 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.142 | 0.17 | 0.134 | tailwind | CONFIRMED |
| HG=F (Copper) | -0.137 | -0.249 | -0.037 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.129 | 0.165 | 0.026 | tailwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | 0.12 | None | 0.173 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.086 | None | 0.086 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.076 | 0.166 | 0.031 | tailwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | 0.06 | -0.102 | 0.253 | tailwind | CONTEXT |
| XLK (Technology) | -0.051 | 0.014 | -0.076 | headwind | CONTEXT |
| SPY (S&P 500) | 0.042 | 0.138 | -0.047 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.022 | -0.005 | -0.088 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.017 | -0.041 | -0.047 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.013 | 0.038 | -0.065 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.008 | 0.08 | -0.119 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.008 | -0.046 | 0.027 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.003 | -0.059 | 0.023 | neutral | CONTEXT |

### curvature — 2s5s10s curvature (butterfly)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| SPY (S&P 500) | -0.232 | -0.131 | -0.386 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.225 | None | -0.179 | headwind | CONTEXT |
| XLK (Technology) | -0.221 | -0.121 | -0.328 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.205 | -0.109 | -0.329 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.204 | -0.098 | -0.309 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.193 | -0.116 | -0.309 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.176 | -0.156 | -0.232 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.166 | 0.305 | -0.02 | tailwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.102 | -0.136 | -0.073 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.097 | None | -0.097 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.075 | -0.085 | -0.045 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | -0.075 | -0.072 | -0.08 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.053 | 0.068 | -0.212 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.042 | -0.045 | 0.002 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.03 | -0.033 | -0.03 | neutral | CONTEXT |
| GC=F (Gold) | -0.027 | 0.129 | -0.258 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.024 | 0.014 | -0.125 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.001 | -0.028 | 0.113 | neutral | CONTEXT |

### slope_chg63 — 2s10s 63d change (steepening)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLRE (Real Estate (rate-sensitive)) | 0.322 | None | 0.322 | tailwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.163 | None | 0.141 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.111 | 0.028 | 0.214 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.098 | -0.121 | -0.099 | headwind | DIRECTIONAL |
| GC=F (Gold) | 0.093 | 0.014 | 0.2 | tailwind | DIRECTIONAL |
| HG=F (Copper) | -0.072 | -0.199 | 0.11 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.059 | -0.068 | 0.291 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.059 | 0.009 | 0.15 | tailwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.054 | -0.029 | -0.123 | headwind | DIRECTIONAL |
| SPY (S&P 500) | 0.046 | -0.083 | 0.318 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.042 | -0.061 | 0.209 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.037 | -0.045 | -0.059 | neutral | CONTEXT |
| XLK (Technology) | 0.026 | -0.105 | 0.258 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.015 | -0.036 | 0.029 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.014 | -0.009 | 0.062 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.011 | -0.099 | 0.198 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.008 | -0.078 | 0.152 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.003 | -0.139 | 0.229 | neutral | CONTEXT |

### ntfs — Near-term forward spread

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLB (Materials (inflation beneficiary)) | -0.223 | -0.251 | -0.197 | headwind | CONFIRMED |
| XLK (Technology) | -0.215 | -0.066 | -0.331 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.2 | -0.1 | -0.361 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.197 | -0.097 | -0.29 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.19 | None | -0.155 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.178 | -0.039 | -0.339 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.135 | -0.053 | -0.251 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.113 | -0.169 | -0.038 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.109 | 0.205 | -0.036 | tailwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.109 | -0.161 | -0.15 | headwind | CONFIRMED |
| GC=F (Gold) | -0.086 | 0.109 | -0.313 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.061 | -0.078 | -0.047 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.056 | -0.086 | -0.045 | headwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | -0.053 | -0.087 | -0.01 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.048 | None | -0.048 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.025 | 0.086 | -0.015 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.015 | -0.042 | 0.139 | neutral | CONTEXT |
| HG=F (Copper) | -0.011 | 0.143 | -0.18 | neutral | CONTEXT |

### real_speed_abs — |Real 10y 63d speed| (violence)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.119 | 0.067 | 0.169 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.097 | -0.156 | -0.005 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.054 | None | 0.054 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.049 | -0.111 | 0.02 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | 0.033 | -0.008 | 0.079 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.028 | -0.006 | 0.059 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.025 | -0.0 | 0.048 | neutral | CONTEXT |
| SPY (S&P 500) | -0.022 | -0.05 | 0.01 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.019 | None | -0.032 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | -0.028 | -0.005 | neutral | CONTEXT |
| XLK (Technology) | -0.014 | -0.022 | 0.003 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.013 | -0.051 | 0.035 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.011 | -0.037 | 0.054 | neutral | CONTEXT |
| HG=F (Copper) | 0.009 | 0.003 | -0.01 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.004 | -0.091 | 0.082 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | -0.004 | 0.073 | -0.091 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.002 | 0.021 | -0.041 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.0 | 0.001 | 0.007 | neutral | CONTEXT |

### trend_spread — 3m10y trend (2y smooth, Faria-Verona)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.124 | 0.123 | 0.031 | tailwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.116 | 0.239 | -0.07 | tailwind | CONTEXT |
| GC=F (Gold) | -0.104 | 0.043 | -0.335 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.097 | 0.253 | -0.131 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.095 | 0.174 | -0.047 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.095 | -0.124 | 0.082 | headwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.074 | 0.237 | -0.171 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.066 | None | -0.066 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.057 | 0.161 | -0.099 | tailwind | CONTEXT |
| HG=F (Copper) | 0.047 | 0.204 | -0.216 | tailwind | CONTEXT |
| XLK (Technology) | -0.04 | 0.149 | -0.184 | headwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.035 | 0.21 | -0.178 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.025 | 0.093 | -0.11 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.022 | -0.152 | -0.092 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.021 | 0.038 | -0.003 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.018 | 0.144 | -0.196 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.008 | None | 0.063 | neutral | CONTEXT |
| SPY (S&P 500) | -0.005 | 0.144 | -0.264 | neutral | CONTEXT |

## Collinearity vs already-scored legs

VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in the inflation axis is caught here and NOT double-counted.

| driver | VIF |
|---|--:|
| be5y5y | 16.64 |
| exp_wedge | 15.58 |
| ntfs | 13.9 |
| policy_gap | 11.61 |
| real10y | 10.37 |
| curve_tp_adj | 7.65 |
| trend_spread | 3.79 |
| corepce_gap | 3.55 |
| slope_chg63 | 2.9 |
| curvature | 2.89 |
| infl_accel | 1.96 |
| _scored_be10y_chg | 1.77 |
| _scored_sticky_dir | 1.54 |
| real_speed_abs | 1.36 |
| be10y_chg63 | -28728252214769.51 |
| real10y_chg63 | -44184887804365.52 |
| be10y | -52461976535736.03 |
| _scored_tips_nominal | -52462332194640.76 |
| nom10y_chg63 | -63130712411698.47 |

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
- `policy_gap` ↔ `trend_spread`: 0.62
- `real10y` ↔ `exp_wedge`: 0.61
- `policy_gap` ↔ `curvature`: 0.6