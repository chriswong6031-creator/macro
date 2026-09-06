# Rate & inflation transmission — calibration report

As-of **2026-09-04**. Forward horizon **63 days**; split-half boundary **2015-01-01**. Transmission = signed Spearman IC(driver_t, asset forward 63d return); display-only coefficients. Scored gate = driver as STRESS vs forward 63d S&P drawdown (calibrate_bonds discipline) + purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West return-forecast bar. No look-ahead.

Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = weak/unstable; **INVERTED** = predicts the wrong way.

## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?

Each driver, expressed as STRESS (higher = more risk-off), vs the forward 63-day S&P drawdown — the same discriminative bar the bond-health legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it predicts the LEVEL of returns; a leg can flag RISK without forecasting return.

| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |
|---|---|---|:--:|--:|---|--:|--:|:--:|
| real10y_chg63 (Real-rate SPEED (63d rise) — 'speed breaks equities') | **DIRECTIONAL** | 0.135/0.052/0.216 | True | 7.0pp | [0.1, 0.195, 0.305] | -0.951 | -0.1026 | — |
| real10y (Real-rate LEVEL (high real yields)) | **CONTEXT** | 0.039/0.053/-0.014 | False | -1.2pp | [0.035, 0.111, 0.213] | -0.814 | -0.16792 | — |
| corepce_gap (Core-PCE-vs-target gap (sticky inflation)) | **DIRECTIONAL** | 0.072/0.058/0.118 | False | 0.6pp | [0.077, 0.121, 0.172] | 1.716 | -0.30844 | — |
| infl_accel (Inflation re-acceleration (3m>12m)) | **DIRECTIONAL** | 0.064/0.066/0.06 | False | 4.3pp | [0.107, 0.158, 0.215] | -1.071 | -0.1262 | — |
| exp_wedge (Expectations unanchoring (market>model)) | **INVERTED** | -0.041/-0.05/-0.08 | False | -6.1pp | [0.016, 0.066, 0.136] | 2.309 | -0.09619 | — |
| curve_tp_adj (TP-adjusted curve inversion (flip: low=stress)) | **CONTEXT** | 0.005/0.01/0.045 | False | -0.7pp | [0.063, 0.11, 0.165] | -0.988 | -0.25758 | — |
| nom10y_chg63 (Nominal-rate SPEED (63d rise)) | **DIRECTIONAL** | 0.115/0.097/0.199 | False | -0.2pp | [0.075, 0.117, 0.165] | 0.716 | -0.11351 | — |
| ntfs (Near-term forward spread inversion (flip: low=stress; Engstrom-Sharpe beats 2s10s)) | **CONTEXT** | -0.042/0.026/-0.198 | False | -1.6pp | [0.054, 0.103, 0.162] | -0.794 | -0.27967 | — |
| curvature (Curve curvature (2s5s10s butterfly — humped = late-cycle)) | **CONTEXT** | 0.036/-0.013/0.183 | False | -0.2pp | [0.061, 0.115, 0.177] | -1.336 | -0.30731 | — |
| real_speed_abs (Real-rate move VIOLENCE (|63d speed|, either direction)) | **DIRECTIONAL** | 0.118/0.161/0.072 | False | 3.0pp | [0.083, 0.156, 0.25] | -1.074 | -0.11033 | — |
| slope_chg63 (Curve flattening impulse (flip: − = flattening = stress; INVERTED if post-inversion steepening is the tell)) | **CONTEXT** | -0.034/-0.085/0.155 | False | -2.1pp | [0.052, 0.095, 0.145] | 0.73 | -0.12284 | — |
| trend_spread (3m10y TREND inversion (flip: low trend = stress) — Faria-Verona OOS equity-premium claim, tested on the return-forecast bar) | **CONTEXT** | 0.152/0.241/-0.044 | False | 6.5pp | [0.11, 0.179, 0.258] | 3.647 | -0.27035 | — |

**Scored-eligible legs: NONE — every rate/inflation leg here is display-only context.** Eligible legs are PROPOSED for a config-gated MRS/drawdown leg, adopted only if they hold on the next refresh (the bonds restraint).

## Transmission matrix — per-asset forward pass-through

Signed Spearman IC of each rate/inflation driver vs each asset's forward 63-day return. Positive = tailwind, negative = headwind. These are the DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells are sign-stable across both halves.

### real10y — Real 10y yield (level)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.344 | 0.374 | 0.309 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.268 | -0.31 | -0.171 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | 0.174 | 0.266 | 0.079 | tailwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.169 | 0.122 | 0.191 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.152 | -0.271 | -0.058 | headwind | CONFIRMED |
| HG=F (Copper) | 0.132 | 0.19 | -0.034 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.125 | -0.18 | -0.044 | headwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.124 | 0.13 | 0.09 | tailwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.06 | None | -0.075 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.059 | -0.159 | -0.004 | headwind | DIRECTIONAL |
| SPY (S&P 500) | -0.053 | -0.139 | 0.057 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.048 | 0.119 | -0.287 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.029 | None | 0.029 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.026 | 0.058 | -0.079 | neutral | CONTEXT |
| XLK (Technology) | -0.021 | -0.039 | 0.074 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.012 | -0.069 | 0.074 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.01 | 0.075 | -0.136 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.006 | -0.1 | 0.053 | neutral | CONTEXT |

### real10y_chg63 — Real 10y — 63d change (speed)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.311 | None | -0.301 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.214 | -0.198 | -0.218 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.195 | -0.197 | -0.198 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.191 | -0.167 | -0.218 | headwind | CONFIRMED |
| XLK (Technology) | -0.19 | -0.209 | -0.19 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.187 | -0.17 | -0.186 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.169 | -0.131 | -0.208 | headwind | CONFIRMED |
| HG=F (Copper) | -0.165 | -0.162 | -0.14 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.152 | -0.109 | -0.206 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.143 | 0.225 | 0.077 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.128 | -0.116 | -0.125 | headwind | CONFIRMED |
| XLE (Energy (inflation beneficiary)) | -0.111 | -0.142 | -0.057 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.082 | 0.018 | -0.174 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.032 | -0.0 | -0.06 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.027 | 0.004 | -0.045 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.027 | None | 0.027 | neutral | CONTEXT |
| GC=F (Gold) | -0.007 | 0.052 | -0.064 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.007 | 0.005 | 0.0 | neutral | CONTEXT |

### nom10y_chg63 — Nominal 10y — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.245 | None | -0.275 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.14 | -0.086 | -0.226 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.121 | -0.092 | -0.186 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.103 | -0.052 | -0.198 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.101 | 0.047 | -0.224 | headwind | CONTEXT |
| XLK (Technology) | -0.096 | -0.053 | -0.191 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.082 | 0.004 | -0.199 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.072 | 0.137 | 0.037 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.066 | -0.04 | -0.106 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.047 | 0.052 | -0.189 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.044 | -0.004 | -0.099 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.04 | None | 0.04 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.036 | -0.041 | 0.017 | neutral | CONTEXT |
| HG=F (Copper) | -0.031 | 0.014 | -0.115 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.03 | 0.054 | -0.171 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.027 | 0.049 | -0.009 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.026 | 0.029 | -0.107 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.02 | 0.064 | -0.032 | neutral | CONTEXT |

### be10y — 10y breakeven (inflation comp.)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.32 | None | -0.347 | headwind | CONTEXT |
| XLK (Technology) | -0.277 | -0.37 | -0.137 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.276 | -0.38 | -0.162 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.225 | -0.281 | -0.26 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.217 | -0.281 | -0.143 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.215 | -0.243 | -0.231 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.187 | -0.174 | -0.184 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.165 | -0.1 | -0.271 | headwind | CONFIRMED |
| HG=F (Copper) | -0.119 | -0.176 | -0.11 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.109 | -0.193 | -0.102 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.104 | 0.143 | 0.169 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.096 | -0.177 | -0.051 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.088 | None | -0.088 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.074 | -0.027 | -0.182 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.062 | -0.165 | 0.037 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.06 | -0.045 | 0.08 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.048 | 0.152 | -0.121 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.036 | 0.048 | -0.014 | neutral | CONTEXT |

### be10y_chg63 — 10y breakeven — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.122 | -0.156 | -0.09 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.121 | -0.075 | -0.145 | headwind | CONFIRMED |
| HG=F (Copper) | 0.098 | 0.189 | -0.053 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.087 | 0.228 | -0.068 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.072 | 0.121 | 0.041 | tailwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.068 | 0.151 | -0.018 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.056 | 0.082 | 0.026 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.049 | -0.028 | -0.072 | headwind | DIRECTIONAL |
| XLB (Materials (inflation beneficiary)) | -0.044 | 0.036 | -0.141 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.04 | 0.113 | -0.085 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.038 | -0.062 | 0.036 | neutral | CONTEXT |
| XLK (Technology) | -0.037 | -0.012 | -0.074 | neutral | CONTEXT |
| SPY (S&P 500) | 0.029 | 0.107 | -0.053 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.028 | None | 0.028 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.019 | 0.075 | -0.162 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.015 | None | -0.064 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.005 | 0.092 | -0.096 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | -0.003 | -0.014 | 0.026 | neutral | CONTEXT |

### be5y5y — 5y5y forward breakeven (anchor)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.31 | None | -0.291 | headwind | CONTEXT |
| XLK (Technology) | -0.264 | -0.272 | -0.141 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.216 | -0.272 | -0.139 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.206 | 0.261 | -0.045 | tailwind | CONTEXT |
| HG=F (Copper) | -0.199 | -0.409 | -0.183 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.169 | -0.167 | -0.132 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.162 | -0.302 | -0.275 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.153 | -0.085 | -0.164 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.138 | -0.195 | -0.198 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.123 | -0.165 | -0.261 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.105 | -0.306 | -0.175 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.07 | 0.205 | 0.132 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.069 | -0.243 | 0.067 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.067 | None | -0.067 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.056 | 0.045 | -0.025 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.022 | -0.073 | -0.121 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.009 | -0.13 | -0.033 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.003 | 0.017 | -0.063 | neutral | CONTEXT |

### curve_tp_adj — TP-adjusted 2s10s curve

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.238 | 0.246 | 0.158 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | 0.164 | None | 0.164 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.146 | -0.08 | -0.153 | headwind | CONFIRMED |
| XLK (Technology) | -0.117 | 0.009 | -0.11 | headwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.108 | None | -0.056 | headwind | CONTEXT |
| SPY (S&P 500) | -0.098 | -0.067 | -0.135 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.082 | -0.266 | -0.074 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.063 | 0.036 | -0.127 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.056 | -0.065 | 0.028 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.043 | -0.046 | -0.086 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | 0.042 | 0.049 | 0.05 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.035 | -0.086 | -0.013 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.031 | 0.048 | 0.006 | neutral | CONTEXT |
| XLP (Staples (defensive)) | -0.023 | -0.023 | 0.009 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | 0.033 | -0.077 | neutral | CONTEXT |
| GC=F (Gold) | -0.018 | 0.112 | -0.129 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | 0.105 | neutral | CONTEXT |
| HG=F (Copper) | 0.002 | 0.07 | -0.063 | neutral | CONTEXT |

### policy_gap — us2y − funds (cut/hike pricing)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.194 | None | -0.173 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.175 | -0.171 | -0.179 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.166 | -0.059 | -0.348 | headwind | CONFIRMED |
| XLK (Technology) | -0.166 | -0.028 | -0.306 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.155 | -0.016 | -0.325 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.139 | -0.031 | -0.283 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.097 | -0.085 | -0.155 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.096 | -0.0 | -0.236 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.072 | -0.087 | -0.055 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.071 | 0.189 | -0.046 | tailwind | CONTEXT |
| GC=F (Gold) | -0.07 | 0.125 | -0.299 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.062 | None | -0.062 | headwind | CONTEXT |
| HG=F (Copper) | 0.058 | 0.224 | -0.154 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.033 | -0.014 | -0.057 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.026 | 0.111 | -0.042 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.02 | -0.005 | -0.054 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.02 | -0.05 | 0.099 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.014 | -0.004 | -0.038 | neutral | CONTEXT |

### corepce_gap — Core PCE YoY − 2% target

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.26 | None | -0.313 | headwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.176 | -0.229 | -0.173 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.171 | -0.272 | -0.078 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.162 | -0.307 | -0.086 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.149 | None | -0.149 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.144 | -0.13 | -0.172 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.138 | 0.024 | -0.231 | headwind | CONTEXT |
| XLK (Technology) | -0.128 | -0.287 | -0.064 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.103 | -0.172 | -0.081 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.103 | -0.184 | -0.115 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.1 | -0.097 | -0.098 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.088 | -0.091 | -0.11 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.084 | -0.14 | -0.059 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | -0.066 | 0.125 | -0.203 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.042 | -0.065 | 0.177 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.041 | 0.034 | 0.245 | tailwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | 0.021 | 0.049 | -0.061 | neutral | CONTEXT |
| GC=F (Gold) | 0.019 | -0.044 | 0.016 | neutral | CONTEXT |

### infl_accel — Inflation re-acceleration (3m−12m)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.199 | -0.191 | -0.191 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | 0.116 | 0.056 | 0.142 | tailwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.096 | 0.081 | 0.117 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.09 | -0.136 | -0.036 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.08 | -0.027 | 0.161 | tailwind | CONTEXT |
| GC=F (Gold) | -0.079 | -0.009 | -0.16 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.076 | None | 0.076 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.071 | -0.095 | -0.039 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.07 | -0.136 | 0.002 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.067 | -0.09 | -0.048 | headwind | DIRECTIONAL |
| XLK (Technology) | -0.064 | -0.101 | -0.032 | headwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.033 | -0.069 | 0.151 | neutral | CONTEXT |
| HG=F (Copper) | 0.025 | 0.044 | -0.019 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.022 | 0.079 | -0.012 | neutral | CONTEXT |
| SPY (S&P 500) | -0.018 | -0.019 | -0.021 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.016 | 0.09 | -0.065 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.013 | 0.064 | -0.046 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.011 | None | -0.038 | neutral | CONTEXT |

### exp_wedge — Expectations wedge (mkt − model)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.257 | -0.302 | -0.257 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | 0.19 | 0.282 | 0.061 | tailwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.162 | -0.297 | -0.133 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.139 | 0.17 | 0.129 | tailwind | CONFIRMED |
| HG=F (Copper) | -0.138 | -0.249 | -0.043 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | 0.129 | 0.165 | 0.026 | tailwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | 0.126 | None | 0.179 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.081 | None | 0.081 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.069 | -0.102 | 0.265 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.064 | 0.166 | 0.01 | tailwind | DIRECTIONAL |
| XLK (Technology) | -0.049 | 0.014 | -0.07 | headwind | CONTEXT |
| SPY (S&P 500) | 0.043 | 0.138 | -0.042 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.027 | -0.005 | -0.081 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.009 | -0.041 | -0.031 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.006 | 0.038 | -0.049 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.006 | 0.08 | -0.124 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.005 | -0.046 | 0.019 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.003 | -0.059 | 0.02 | neutral | CONTEXT |

### curvature — 2s5s10s curvature (butterfly)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| SPY (S&P 500) | -0.232 | -0.131 | -0.385 | headwind | CONFIRMED |
| XLK (Technology) | -0.221 | -0.121 | -0.327 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.221 | None | -0.175 | headwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.207 | -0.098 | -0.31 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.203 | -0.109 | -0.325 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.194 | -0.116 | -0.31 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.176 | -0.156 | -0.232 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.167 | 0.305 | -0.017 | tailwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.103 | -0.136 | -0.073 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.099 | None | -0.099 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.08 | -0.072 | -0.085 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.075 | -0.085 | -0.046 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.054 | 0.068 | -0.212 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.039 | -0.045 | 0.005 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.028 | -0.033 | -0.028 | neutral | CONTEXT |
| GC=F (Gold) | -0.024 | 0.129 | -0.251 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.022 | 0.014 | -0.122 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.0 | -0.028 | 0.111 | neutral | CONTEXT |

### slope_chg63 — 2s10s 63d change (steepening)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLRE (Real Estate (rate-sensitive)) | 0.318 | None | 0.318 | tailwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.166 | None | 0.144 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.113 | 0.028 | 0.217 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.099 | -0.121 | -0.102 | headwind | DIRECTIONAL |
| GC=F (Gold) | 0.096 | 0.014 | 0.206 | tailwind | DIRECTIONAL |
| HG=F (Copper) | -0.073 | -0.199 | 0.107 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.061 | -0.068 | 0.294 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.059 | 0.009 | 0.149 | tailwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.054 | -0.029 | -0.124 | headwind | DIRECTIONAL |
| SPY (S&P 500) | 0.047 | -0.083 | 0.318 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.041 | -0.061 | 0.206 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.033 | -0.045 | -0.051 | neutral | CONTEXT |
| XLK (Technology) | 0.026 | -0.105 | 0.259 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.014 | -0.099 | 0.204 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.014 | -0.036 | 0.031 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.008 | -0.078 | 0.151 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.008 | -0.009 | 0.049 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.006 | -0.139 | 0.218 | neutral | CONTEXT |

### ntfs — Near-term forward spread

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLB (Materials (inflation beneficiary)) | -0.213 | -0.237 | -0.188 | headwind | CONFIRMED |
| XLK (Technology) | -0.208 | -0.063 | -0.323 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.201 | -0.106 | -0.352 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.194 | -0.099 | -0.274 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.181 | None | -0.145 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.172 | -0.036 | -0.332 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.127 | -0.046 | -0.24 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.113 | -0.17 | -0.15 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.105 | -0.156 | -0.036 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.105 | 0.203 | -0.043 | tailwind | CONTEXT |
| GC=F (Gold) | -0.092 | 0.103 | -0.324 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.058 | -0.09 | -0.039 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | -0.052 | -0.064 | -0.035 | headwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | -0.051 | -0.083 | -0.012 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.047 | None | -0.047 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.032 | 0.089 | -0.006 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.024 | -0.013 | 0.146 | neutral | CONTEXT |
| HG=F (Copper) | -0.012 | 0.141 | -0.18 | neutral | CONTEXT |

### real_speed_abs — |Real 10y 63d speed| (violence)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.12 | 0.067 | 0.171 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.099 | -0.156 | -0.009 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.05 | None | 0.05 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.048 | -0.111 | 0.022 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | 0.033 | -0.008 | 0.079 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.027 | -0.006 | 0.056 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.026 | -0.0 | 0.05 | neutral | CONTEXT |
| SPY (S&P 500) | -0.022 | -0.05 | 0.01 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | -0.028 | -0.004 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.016 | None | -0.029 | neutral | CONTEXT |
| XLK (Technology) | -0.015 | -0.022 | -0.0 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.013 | -0.051 | 0.036 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.011 | -0.037 | 0.054 | neutral | CONTEXT |
| HG=F (Copper) | 0.008 | 0.003 | -0.011 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.005 | -0.091 | 0.079 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | -0.003 | 0.073 | -0.088 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.001 | 0.001 | 0.005 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.001 | 0.021 | -0.038 | neutral | CONTEXT |

### trend_spread — 3m10y trend (2y smooth, Faria-Verona)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.127 | 0.123 | 0.035 | tailwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.115 | 0.239 | -0.07 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.101 | 0.253 | -0.122 | tailwind | CONTEXT |
| GC=F (Gold) | -0.099 | 0.043 | -0.323 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.083 | 0.174 | -0.063 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.071 | 0.237 | -0.174 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.067 | None | -0.067 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.054 | 0.161 | -0.103 | tailwind | CONTEXT |
| HG=F (Copper) | 0.045 | 0.204 | -0.218 | tailwind | CONTEXT |
| XLK (Technology) | -0.04 | 0.149 | -0.178 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.032 | -0.051 | 0.079 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.028 | 0.038 | 0.008 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.026 | 0.21 | -0.187 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.025 | 0.093 | -0.11 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.02 | -0.152 | -0.091 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.015 | 0.144 | -0.184 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.014 | None | 0.069 | neutral | CONTEXT |
| SPY (S&P 500) | -0.005 | 0.144 | -0.26 | neutral | CONTEXT |

## Collinearity vs already-scored legs

VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in the inflation axis is caught here and NOT double-counted.

| driver | VIF |
|---|--:|
| be5y5y | 16.63 |
| exp_wedge | 15.76 |
| ntfs | 14.29 |
| policy_gap | 11.49 |
| real10y | 10.8 |
| curve_tp_adj | 7.84 |
| trend_spread | 3.76 |
| corepce_gap | 3.62 |
| be10y | 3.03 |
| _scored_tips_nominal | 3.03 |
| slope_chg63 | 2.9 |
| curvature | 2.85 |
| infl_accel | 1.97 |
| _scored_be10y_chg | 1.77 |
| be10y_chg63 | 1.55 |
| _scored_sticky_dir | 1.55 |
| real_speed_abs | 1.36 |
| real10y_chg63 | 1.11 |
| nom10y_chg63 | 0.87 |

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
- `real10y` ↔ `exp_wedge`: 0.62
- `policy_gap` ↔ `trend_spread`: 0.62
- `policy_gap` ↔ `curvature`: 0.6