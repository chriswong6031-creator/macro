# Rate & inflation transmission — calibration report

As-of **2026-06-16**. Forward horizon **63 days**; split-half boundary **2015-01-01**. Transmission = signed Spearman IC(driver_t, asset forward 63d return); display-only coefficients. Scored gate = driver as STRESS vs forward 63d S&P drawdown (calibrate_bonds discipline) + purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West return-forecast bar. No look-ahead.

Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = weak/unstable; **INVERTED** = predicts the wrong way.

## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?

Each driver, expressed as STRESS (higher = more risk-off), vs the forward 63-day S&P drawdown — the same discriminative bar the bond-health legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it predicts the LEVEL of returns; a leg can flag RISK without forecasting return.

| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |
|---|---|---|:--:|--:|---|--:|--:|:--:|
| real10y_chg63 (Real-rate SPEED (63d rise) — 'speed breaks equities') | **DIRECTIONAL** | 0.139/0.052/0.222 | False | 7.2pp | [0.106, 0.198, 0.304] | -1.118 | -0.10539 | — |
| real10y (Real-rate LEVEL (high real yields)) | **DIRECTIONAL** | 0.047/0.053/0.004 | False | -1.0pp | [0.036, 0.115, 0.218] | -0.942 | -0.17117 | — |
| corepce_gap (Core-PCE-vs-target gap (sticky inflation)) | **DIRECTIONAL** | 0.042/0.009/0.13 | False | 0.2pp | [0.074, 0.123, 0.179] | 1.666 | -0.3112 | — |
| infl_accel (Inflation re-acceleration (3m>12m)) | **DIRECTIONAL** | 0.053/0.049/0.073 | False | 4.0pp | [0.105, 0.162, 0.226] | -1.203 | -0.12829 | — |
| exp_wedge (Expectations unanchoring (market>model)) | **INVERTED** | -0.054/-0.05/-0.106 | False | -6.2pp | [0.016, 0.065, 0.137] | 2.14 | -0.09926 | — |
| curve_tp_adj (TP-adjusted curve inversion (flip: low=stress)) | **CONTEXT** | 0.005/0.01/0.031 | False | -0.7pp | [0.061, 0.11, 0.166] | -1.03 | -0.25973 | — |
| nom10y_chg63 (Nominal-rate SPEED (63d rise)) | **DIRECTIONAL** | 0.095/0.068/0.208 | False | -0.4pp | [0.073, 0.118, 0.174] | 0.636 | -0.1152 | — |

**Scored-eligible legs: NONE — every rate/inflation leg here is display-only context.** Eligible legs are PROPOSED for a config-gated MRS/drawdown leg, adopted only if they hold on the next refresh (the bonds restraint).

## Transmission matrix — per-asset forward pass-through

Signed Spearman IC of each rate/inflation driver vs each asset's forward 63-day return. Positive = tailwind, negative = headwind. These are the DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells are sign-stable across both halves.

### real10y — Real 10y yield (level)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.362 | 0.374 | 0.354 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.274 | -0.31 | -0.185 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | 0.183 | 0.266 | 0.096 | tailwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.175 | 0.122 | 0.2 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.171 | -0.271 | -0.104 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.139 | -0.18 | -0.077 | headwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.135 | 0.13 | 0.114 | tailwind | CONFIRMED |
| HG=F (Copper) | 0.129 | 0.19 | -0.049 | tailwind | CONTEXT |
| SPY (S&P 500) | -0.059 | -0.139 | 0.046 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.059 | -0.159 | -0.007 | headwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | -0.046 | None | -0.06 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.036 | 0.119 | -0.265 | neutral | CONTEXT |
| XLK (Technology) | -0.028 | -0.039 | 0.061 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.027 | 0.058 | -0.082 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.017 | None | 0.017 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.014 | -0.069 | 0.072 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.014 | -0.1 | 0.033 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.012 | 0.075 | -0.137 | neutral | CONTEXT |

### real10y_chg63 — Real 10y — 63d change (speed)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.311 | None | -0.3 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.215 | -0.198 | -0.224 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.196 | -0.197 | -0.197 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.195 | -0.167 | -0.224 | headwind | CONFIRMED |
| XLK (Technology) | -0.193 | -0.209 | -0.193 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.181 | -0.17 | -0.178 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.174 | -0.131 | -0.218 | headwind | CONFIRMED |
| HG=F (Copper) | -0.168 | -0.162 | -0.146 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.161 | -0.109 | -0.225 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.146 | 0.225 | 0.079 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.127 | -0.116 | -0.127 | headwind | CONFIRMED |
| XLE (Energy (inflation beneficiary)) | -0.112 | -0.142 | -0.06 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.079 | 0.018 | -0.173 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.042 | -0.0 | -0.079 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.023 | None | 0.023 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.022 | 0.004 | -0.036 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.006 | 0.005 | -0.002 | neutral | CONTEXT |
| GC=F (Gold) | -0.001 | 0.052 | -0.058 | neutral | CONTEXT |

### nom10y_chg63 — Nominal 10y — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.24 | None | -0.27 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.141 | -0.086 | -0.232 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.124 | -0.092 | -0.193 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.104 | -0.052 | -0.199 | headwind | CONFIRMED |
| XLK (Technology) | -0.099 | -0.053 | -0.197 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.099 | 0.047 | -0.223 | headwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.087 | 0.004 | -0.212 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.076 | 0.137 | 0.041 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.06 | -0.04 | -0.097 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.044 | -0.004 | -0.1 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.04 | 0.052 | -0.178 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.038 | 0.054 | -0.195 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.038 | -0.042 | 0.012 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.035 | None | 0.035 | neutral | CONTEXT |
| HG=F (Copper) | -0.035 | 0.014 | -0.123 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.032 | 0.049 | 0.003 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.026 | 0.029 | -0.11 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.012 | 0.064 | -0.054 | neutral | CONTEXT |

### be10y — 10y breakeven (inflation comp.)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.308 | None | -0.334 | headwind | CONTEXT |
| XLK (Technology) | -0.286 | -0.37 | -0.153 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.28 | -0.38 | -0.165 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.225 | -0.281 | -0.261 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.223 | -0.243 | -0.252 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.222 | -0.281 | -0.152 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.199 | -0.174 | -0.214 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.16 | -0.1 | -0.263 | headwind | CONFIRMED |
| HG=F (Copper) | -0.123 | -0.176 | -0.123 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.112 | -0.177 | -0.09 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.109 | -0.193 | -0.104 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.1 | 0.143 | 0.159 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.096 | None | -0.096 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.065 | -0.027 | -0.16 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.061 | -0.045 | 0.082 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.054 | 0.152 | -0.114 | tailwind | CONTEXT |
| GC=F (Gold) | -0.05 | -0.165 | 0.072 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.045 | 0.048 | 0.006 | tailwind | DIRECTIONAL |

### be10y_chg63 — 10y breakeven — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.119 | -0.075 | -0.143 | headwind | CONFIRMED |
| GC=F (Gold) | -0.118 | -0.156 | -0.077 | headwind | CONFIRMED |
| HG=F (Copper) | 0.096 | 0.189 | -0.061 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.081 | 0.228 | -0.085 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | 0.069 | 0.151 | -0.019 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.066 | 0.121 | 0.025 | tailwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | 0.06 | 0.082 | 0.034 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.049 | -0.028 | -0.073 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | 0.046 | 0.113 | -0.075 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.044 | 0.036 | -0.145 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.041 | -0.062 | 0.031 | headwind | CONTEXT |
| XLK (Technology) | -0.04 | -0.012 | -0.081 | neutral | CONTEXT |
| SPY (S&P 500) | 0.028 | 0.107 | -0.058 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.023 | None | 0.023 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.018 | 0.075 | -0.164 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.009 | 0.092 | -0.107 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.005 | None | -0.054 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | -0.001 | -0.014 | 0.031 | neutral | CONTEXT |

### be5y5y — 5y5y forward breakeven (anchor)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.307 | None | -0.287 | headwind | CONTEXT |
| XLK (Technology) | -0.261 | -0.272 | -0.143 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.213 | -0.272 | -0.134 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.205 | 0.261 | -0.041 | tailwind | CONTEXT |
| HG=F (Copper) | -0.198 | -0.409 | -0.189 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.166 | -0.167 | -0.132 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.163 | -0.302 | -0.278 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.149 | -0.085 | -0.178 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.135 | -0.195 | -0.205 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.13 | -0.165 | -0.258 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.11 | -0.306 | -0.176 | headwind | CONFIRMED |
| GC=F (Gold) | -0.076 | -0.243 | 0.077 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.072 | 0.205 | 0.131 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.066 | None | -0.066 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.053 | 0.045 | -0.016 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.022 | -0.073 | -0.121 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.012 | -0.13 | -0.038 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.009 | 0.017 | -0.083 | neutral | CONTEXT |

### curve_tp_adj — TP-adjusted 2s10s curve

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.238 | 0.246 | 0.162 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | 0.157 | None | 0.157 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.145 | -0.08 | -0.177 | headwind | CONFIRMED |
| XLK (Technology) | -0.117 | 0.009 | -0.126 | headwind | CONTEXT |
| SPY (S&P 500) | -0.097 | -0.067 | -0.145 | headwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | -0.096 | None | -0.041 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.08 | -0.266 | -0.061 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.063 | 0.036 | -0.135 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.056 | -0.065 | 0.018 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.043 | -0.046 | -0.086 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | 0.043 | 0.049 | 0.02 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.035 | -0.086 | -0.007 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.031 | 0.048 | 0.035 | neutral | CONTEXT |
| XLP (Staples (defensive)) | -0.023 | -0.023 | 0.008 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | 0.033 | -0.091 | neutral | CONTEXT |
| GC=F (Gold) | -0.017 | 0.112 | -0.104 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | 0.124 | neutral | CONTEXT |
| HG=F (Copper) | 0.003 | 0.07 | -0.072 | neutral | CONTEXT |

### policy_gap — us2y − funds (cut/hike pricing)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.192 | None | -0.17 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.177 | -0.171 | -0.18 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.165 | -0.059 | -0.351 | headwind | CONFIRMED |
| XLK (Technology) | -0.165 | -0.028 | -0.308 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.153 | -0.016 | -0.325 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.14 | -0.031 | -0.295 | headwind | DIRECTIONAL |
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
| XLE (Energy (inflation beneficiary)) | -0.016 | -0.004 | -0.04 | neutral | CONTEXT |

### corepce_gap — Core PCE YoY − 2% target

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.253 | None | -0.307 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.191 | -0.272 | -0.107 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.187 | -0.229 | -0.187 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.168 | -0.307 | -0.088 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.157 | None | -0.157 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.144 | -0.13 | -0.172 | headwind | CONFIRMED |
| XLK (Technology) | -0.139 | -0.287 | -0.076 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.129 | 0.024 | -0.219 | headwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.117 | -0.184 | -0.135 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.109 | -0.172 | -0.088 | headwind | CONFIRMED |
| HG=F (Copper) | -0.09 | -0.14 | -0.065 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.089 | -0.091 | -0.111 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.088 | -0.097 | -0.08 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | -0.058 | 0.125 | -0.198 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.044 | -0.065 | 0.182 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.04 | 0.034 | 0.239 | tailwind | DIRECTIONAL |
| GC=F (Gold) | 0.035 | -0.044 | 0.045 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.031 | 0.049 | -0.041 | neutral | CONTEXT |

### infl_accel — Inflation re-acceleration (3m−12m)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.193 | -0.191 | -0.181 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | 0.126 | 0.056 | 0.165 | tailwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.101 | 0.081 | 0.129 | tailwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.096 | -0.136 | -0.049 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.084 | -0.027 | 0.171 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.078 | -0.136 | -0.015 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.078 | -0.095 | -0.056 | headwind | DIRECTIONAL |
| XLK (Technology) | -0.073 | -0.101 | -0.051 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.069 | -0.009 | -0.14 | headwind | DIRECTIONAL |
| XLB (Materials (inflation beneficiary)) | -0.067 | -0.09 | -0.048 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.064 | None | 0.064 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.035 | -0.069 | 0.143 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.026 | 0.079 | -0.008 | neutral | CONTEXT |
| SPY (S&P 500) | -0.023 | -0.019 | -0.034 | neutral | CONTEXT |
| HG=F (Copper) | 0.021 | 0.044 | -0.032 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.014 | 0.064 | -0.048 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.008 | 0.09 | -0.086 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.003 | None | -0.023 | neutral | CONTEXT |

### exp_wedge — Expectations wedge (mkt − model)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.282 | -0.302 | -0.311 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | 0.218 | 0.282 | 0.114 | tailwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.177 | -0.297 | -0.156 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.149 | 0.17 | 0.148 | tailwind | CONFIRMED |
| HG=F (Copper) | -0.134 | -0.249 | -0.028 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.129 | 0.165 | 0.028 | tailwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | 0.111 | None | 0.164 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.096 | None | 0.096 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.083 | 0.166 | 0.046 | tailwind | DIRECTIONAL |
| SPY (S&P 500) | 0.051 | 0.138 | -0.032 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.051 | -0.102 | 0.239 | tailwind | CONTEXT |
| XLK (Technology) | -0.04 | 0.014 | -0.055 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.024 | -0.041 | -0.061 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.019 | -0.005 | -0.094 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.017 | 0.08 | -0.105 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.004 | 0.038 | -0.048 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.003 | -0.046 | 0.018 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.001 | -0.059 | 0.017 | neutral | CONTEXT |

## Collinearity vs already-scored legs

VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in the inflation axis is caught here and NOT double-counted.

| driver | VIF |
|---|--:|
| _scored_tips_nominal | 334642.12 |
| be10y | 334636.14 |
| nom10y_chg63 | 240131.3 |
| real10y_chg63 | 167568.05 |
| be10y_chg63 | 109310.56 |
| be5y5y | 16.02 |
| exp_wedge | 12.7 |
| real10y | 8.81 |
| curve_tp_adj | 3.78 |
| corepce_gap | 2.65 |
| policy_gap | 2.22 |
| infl_accel | 1.9 |
| _scored_be10y_chg | 1.72 |
| _scored_sticky_dir | 1.46 |

Top correlated pairs:

- `be10y` ↔ `_scored_tips_nominal`: 1.0
- `be10y` ↔ `be5y5y`: 0.78
- `be5y5y` ↔ `_scored_tips_nominal`: 0.78
- `real10y_chg63` ↔ `nom10y_chg63`: 0.74
- `real10y` ↔ `exp_wedge`: 0.61