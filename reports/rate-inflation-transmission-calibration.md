# Rate & inflation transmission — calibration report

As-of **2026-07-17**. Forward horizon **63 days**; split-half boundary **2015-01-01**. Transmission = signed Spearman IC(driver_t, asset forward 63d return); display-only coefficients. Scored gate = driver as STRESS vs forward 63d S&P drawdown (calibrate_bonds discipline) + purged-CV sign robustness + bootstrap-CI tercile edge + Clark-West return-forecast bar. No look-ahead.

Verdicts (cells & legs): **CONFIRMED** = sign-stable in full + both purged halves with |IC|≥0.10 (scored legs also need the high-stress tercile drawdown edge with a bootstrap-CI lower bound above the base rate, and purged-CV sign robustness); **DIRECTIONAL** = full + both halves but weaker; **CONTEXT** = weak/unstable; **INVERTED** = predicts the wrong way.

## Scored-leg gate — does any rate/inflation leg earn a SCORED tier?

Each driver, expressed as STRESS (higher = more risk-off), vs the forward 63-day S&P drawdown — the same discriminative bar the bond-health legs pass. The return-forecast columns (Clark-West t, OOS-R²) test whether it predicts the LEVEL of returns; a leg can flag RISK without forecasting return.

| leg | verdict | IC dd (full/pre/post) | CV robust | hi-tercile edge | boot CI | CW t | OOS-R² | scored? |
|---|---|---|:--:|--:|---|--:|--:|:--:|
| real10y_chg63 (Real-rate SPEED (63d rise) — 'speed breaks equities') | **DIRECTIONAL** | 0.137/0.052/0.218 | True | 7.1pp | [0.105, 0.198, 0.3] | -0.967 | -0.10263 | — |
| real10y (Real-rate LEVEL (high real yields)) | **CONTEXT** | 0.042/0.053/-0.007 | False | -0.9pp | [0.036, 0.115, 0.218] | -0.83 | -0.1678 | — |
| corepce_gap (Core-PCE-vs-target gap (sticky inflation)) | **DIRECTIONAL** | 0.073/0.058/0.122 | False | 0.6pp | [0.077, 0.121, 0.173] | 1.71 | -0.30843 | — |
| infl_accel (Inflation re-acceleration (3m>12m)) | **DIRECTIONAL** | 0.065/0.066/0.064 | False | 4.3pp | [0.107, 0.159, 0.215] | -1.085 | -0.12615 | — |
| exp_wedge (Expectations unanchoring (market>model)) | **INVERTED** | -0.046/-0.05/-0.09 | False | -6.1pp | [0.015, 0.065, 0.136] | 2.289 | -0.09586 | — |
| curve_tp_adj (TP-adjusted curve inversion (flip: low=stress)) | **CONTEXT** | 0.005/0.01/0.04 | False | -0.7pp | [0.062, 0.11, 0.167] | -0.993 | -0.25763 | — |
| nom10y_chg63 (Nominal-rate SPEED (63d rise)) | **DIRECTIONAL** | 0.116/0.097/0.203 | False | -0.1pp | [0.077, 0.117, 0.165] | 0.71 | -0.11355 | — |
| ntfs (Near-term forward spread inversion (flip: low=stress; Engstrom-Sharpe beats 2s10s)) | **CONTEXT** | -0.02/0.048/-0.21 | False | -1.4pp | [0.058, 0.103, 0.16] | -0.707 | -0.26699 | — |
| curvature (Curve curvature (2s5s10s butterfly — humped = late-cycle)) | **CONTEXT** | 0.035/-0.013/0.181 | False | -0.2pp | [0.063, 0.115, 0.177] | -1.336 | -0.30732 | — |
| real_speed_abs (Real-rate move VIOLENCE (|63d speed|, either direction)) | **DIRECTIONAL** | 0.116/0.161/0.065 | False | 3.0pp | [0.08, 0.159, 0.249] | -1.09 | -0.11026 | — |
| slope_chg63 (Curve flattening impulse (flip: − = flattening = stress; INVERTED if post-inversion steepening is the tell)) | **CONTEXT** | -0.033/-0.085/0.161 | False | -2.0pp | [0.053, 0.096, 0.148] | 0.734 | -0.12274 | — |
| trend_spread (3m10y TREND inversion (flip: low trend = stress) — Faria-Verona OOS equity-premium claim, tested on the return-forecast bar) | **CONTEXT** | 0.14/0.195/-0.039 | False | 6.7pp | [0.128, 0.184, 0.245] | 3.636 | -0.27018 | — |

**Scored-eligible legs: NONE — every rate/inflation leg here is display-only context.** Eligible legs are PROPOSED for a config-gated MRS/drawdown leg, adopted only if they hold on the next refresh (the bonds restraint).

## Transmission matrix — per-asset forward pass-through

Signed Spearman IC of each rate/inflation driver vs each asset's forward 63-day return. Positive = tailwind, negative = headwind. These are the DISPLAY-ONLY coefficients the transmission engine reads; **CONFIRMED** cells are sign-stable across both halves.

### real10y — Real 10y yield (level)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.353 | 0.374 | 0.331 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.271 | -0.31 | -0.177 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | 0.177 | 0.266 | 0.084 | tailwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.173 | 0.122 | 0.199 | tailwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.166 | -0.271 | -0.091 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.134 | -0.18 | -0.065 | headwind | CONFIRMED |
| HG=F (Copper) | 0.132 | 0.19 | -0.04 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.131 | 0.13 | 0.104 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.059 | -0.159 | -0.005 | headwind | DIRECTIONAL |
| SPY (S&P 500) | -0.053 | -0.139 | 0.06 | headwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.053 | None | -0.067 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.042 | 0.119 | -0.275 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.026 | 0.058 | -0.083 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.025 | None | 0.025 | neutral | CONTEXT |
| XLK (Technology) | -0.021 | -0.039 | 0.078 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.008 | -0.069 | 0.087 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.008 | -0.1 | 0.047 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.008 | 0.075 | -0.145 | neutral | CONTEXT |

### real10y_chg63 — Real 10y — 63d change (speed)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.312 | None | -0.3 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.215 | -0.198 | -0.223 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.192 | -0.197 | -0.192 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.191 | -0.167 | -0.218 | headwind | CONFIRMED |
| XLK (Technology) | -0.19 | -0.209 | -0.187 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.183 | -0.17 | -0.179 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.171 | -0.131 | -0.213 | headwind | CONFIRMED |
| HG=F (Copper) | -0.166 | -0.162 | -0.144 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.159 | -0.109 | -0.222 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.146 | 0.225 | 0.08 | tailwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.127 | -0.116 | -0.126 | headwind | CONFIRMED |
| XLE (Energy (inflation beneficiary)) | -0.114 | -0.142 | -0.063 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.081 | 0.018 | -0.175 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.04 | -0.0 | -0.076 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.027 | None | 0.027 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.023 | 0.004 | -0.037 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.007 | 0.005 | 0.0 | neutral | CONTEXT |
| GC=F (Gold) | -0.004 | 0.052 | -0.06 | neutral | CONTEXT |

### nom10y_chg63 — Nominal 10y — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.241 | None | -0.272 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.141 | -0.086 | -0.23 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.121 | -0.092 | -0.186 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.101 | -0.052 | -0.192 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.1 | 0.047 | -0.226 | headwind | CONTEXT |
| XLK (Technology) | -0.096 | -0.053 | -0.19 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.084 | 0.004 | -0.205 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.076 | 0.137 | 0.041 | tailwind | DIRECTIONAL |
| GC=F (Gold) | -0.062 | -0.04 | -0.1 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.044 | -0.004 | -0.1 | headwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | -0.042 | 0.052 | -0.181 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.039 | None | 0.039 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.036 | 0.054 | -0.189 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.036 | -0.041 | 0.015 | neutral | CONTEXT |
| HG=F (Copper) | -0.033 | 0.014 | -0.12 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.031 | 0.049 | 0.0 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.028 | 0.029 | -0.113 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.013 | 0.064 | -0.051 | neutral | CONTEXT |

### be10y — 10y breakeven (inflation comp.)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.313 | None | -0.34 | headwind | CONTEXT |
| XLK (Technology) | -0.279 | -0.37 | -0.137 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.274 | -0.38 | -0.152 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.225 | -0.281 | -0.262 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.218 | -0.243 | -0.239 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.217 | -0.281 | -0.141 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.196 | -0.174 | -0.206 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.163 | -0.1 | -0.27 | headwind | CONFIRMED |
| HG=F (Copper) | -0.121 | -0.176 | -0.116 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.109 | -0.193 | -0.103 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | -0.109 | -0.177 | -0.08 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.101 | 0.143 | 0.164 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.091 | None | -0.091 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.068 | -0.027 | -0.168 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.058 | -0.045 | 0.074 | tailwind | CONTEXT |
| GC=F (Gold) | -0.055 | -0.165 | 0.057 | headwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.052 | 0.152 | -0.115 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.042 | 0.048 | -0.001 | tailwind | CONTEXT |

### be10y_chg63 — 10y breakeven — 63d change

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.12 | -0.075 | -0.144 | headwind | CONFIRMED |
| GC=F (Gold) | -0.119 | -0.156 | -0.081 | headwind | CONFIRMED |
| HG=F (Copper) | 0.097 | 0.189 | -0.057 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.082 | 0.228 | -0.081 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | 0.069 | 0.151 | -0.018 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.066 | 0.121 | 0.028 | tailwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | 0.059 | 0.082 | 0.032 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.047 | -0.028 | -0.068 | headwind | DIRECTIONAL |
| XLB (Materials (inflation beneficiary)) | -0.044 | 0.036 | -0.144 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.044 | 0.113 | -0.078 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.04 | -0.062 | 0.033 | neutral | CONTEXT |
| XLK (Technology) | -0.038 | -0.012 | -0.075 | neutral | CONTEXT |
| SPY (S&P 500) | 0.029 | 0.107 | -0.054 | neutral | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.025 | None | 0.025 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.02 | 0.075 | -0.167 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.008 | None | -0.057 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.007 | 0.092 | -0.101 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | -0.001 | -0.014 | 0.03 | neutral | CONTEXT |

### be5y5y — 5y5y forward breakeven (anchor)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.307 | None | -0.287 | headwind | CONTEXT |
| XLK (Technology) | -0.264 | -0.272 | -0.143 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.217 | -0.272 | -0.134 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.205 | 0.261 | -0.042 | tailwind | CONTEXT |
| HG=F (Copper) | -0.199 | -0.409 | -0.189 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.169 | -0.167 | -0.132 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.162 | -0.302 | -0.278 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.152 | -0.085 | -0.179 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.138 | -0.195 | -0.205 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.125 | -0.165 | -0.253 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.106 | -0.306 | -0.175 | headwind | CONFIRMED |
| GC=F (Gold) | -0.071 | -0.243 | 0.077 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.071 | 0.205 | 0.131 | tailwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.067 | None | -0.067 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.055 | 0.045 | -0.016 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.022 | -0.073 | -0.121 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.008 | -0.13 | -0.036 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.006 | 0.017 | -0.083 | neutral | CONTEXT |

### curve_tp_adj — TP-adjusted 2s10s curve

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.239 | 0.246 | 0.162 | tailwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | 0.162 | None | 0.162 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.146 | -0.08 | -0.169 | headwind | CONFIRMED |
| XLK (Technology) | -0.117 | 0.009 | -0.11 | headwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.102 | None | -0.048 | headwind | CONTEXT |
| SPY (S&P 500) | -0.098 | -0.067 | -0.133 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.081 | -0.266 | -0.071 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.063 | 0.036 | -0.121 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.056 | -0.065 | 0.024 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.043 | -0.046 | -0.087 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | 0.043 | 0.049 | 0.028 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.035 | -0.086 | -0.017 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.031 | 0.048 | 0.022 | neutral | CONTEXT |
| XLP (Staples (defensive)) | -0.023 | -0.023 | 0.009 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | 0.033 | -0.08 | neutral | CONTEXT |
| GC=F (Gold) | -0.017 | 0.112 | -0.117 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.015 | -0.041 | 0.116 | neutral | CONTEXT |
| HG=F (Copper) | 0.002 | 0.07 | -0.066 | neutral | CONTEXT |

### policy_gap — us2y − funds (cut/hike pricing)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.192 | None | -0.17 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.176 | -0.171 | -0.179 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.166 | -0.059 | -0.347 | headwind | CONFIRMED |
| XLK (Technology) | -0.165 | -0.028 | -0.304 | headwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.154 | -0.016 | -0.321 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.14 | -0.031 | -0.292 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.097 | -0.0 | -0.238 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.097 | -0.085 | -0.156 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | 0.072 | 0.189 | -0.044 | tailwind | CONTEXT |
| XLP (Staples (defensive)) | -0.071 | -0.087 | -0.054 | headwind | DIRECTIONAL |
| GC=F (Gold) | -0.071 | 0.125 | -0.299 | headwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.061 | None | -0.061 | headwind | CONTEXT |
| HG=F (Copper) | 0.058 | 0.224 | -0.155 | tailwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.032 | -0.014 | -0.053 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.028 | 0.111 | -0.035 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.021 | -0.005 | -0.062 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.02 | -0.05 | 0.098 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.015 | -0.004 | -0.041 | neutral | CONTEXT |

### corepce_gap — Core PCE YoY − 2% target

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| BTC-USD (Bitcoin (long-duration)) | -0.257 | None | -0.31 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.185 | -0.272 | -0.099 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.18 | -0.229 | -0.176 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.16 | -0.307 | -0.077 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.152 | None | -0.152 | headwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.144 | -0.13 | -0.173 | headwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.135 | 0.024 | -0.227 | headwind | CONTEXT |
| XLK (Technology) | -0.13 | -0.287 | -0.063 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.112 | -0.184 | -0.128 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.103 | -0.172 | -0.079 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | -0.094 | -0.097 | -0.089 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | -0.089 | -0.091 | -0.11 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.086 | -0.14 | -0.061 | headwind | DIRECTIONAL |
| TLT (Long Treasuries (20y+)) | -0.061 | 0.125 | -0.199 | headwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.041 | 0.034 | 0.243 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.039 | -0.065 | 0.173 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.027 | 0.049 | -0.049 | neutral | CONTEXT |
| GC=F (Gold) | 0.027 | -0.044 | 0.03 | neutral | CONTEXT |

### infl_accel — Inflation re-acceleration (3m−12m)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| FXI (China large-cap (EM proxy)) | -0.198 | -0.191 | -0.189 | headwind | CONFIRMED |
| CL=F (Oil (WTI)) | 0.12 | 0.056 | 0.151 | tailwind | CONFIRMED |
| XLU (Utilities (bond proxy)) | 0.097 | 0.081 | 0.121 | tailwind | DIRECTIONAL |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.09 | -0.136 | -0.036 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | 0.08 | -0.027 | 0.159 | tailwind | CONTEXT |
| GC=F (Gold) | -0.075 | -0.009 | -0.152 | headwind | DIRECTIONAL |
| XLF (Financials (rate beneficiary)) | -0.074 | -0.095 | -0.047 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.072 | -0.136 | -0.002 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.07 | None | 0.07 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | -0.067 | -0.09 | -0.048 | headwind | DIRECTIONAL |
| XLK (Technology) | -0.066 | -0.101 | -0.036 | headwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.034 | -0.069 | 0.147 | neutral | CONTEXT |
| HG=F (Copper) | 0.024 | 0.044 | -0.024 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.024 | 0.079 | -0.01 | neutral | CONTEXT |
| SPY (S&P 500) | -0.018 | -0.019 | -0.023 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.014 | 0.064 | -0.046 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.011 | 0.09 | -0.077 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.005 | None | -0.031 | neutral | CONTEXT |

### exp_wedge — Expectations wedge (mkt − model)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | -0.27 | -0.302 | -0.285 | headwind | CONFIRMED |
| XLV (Health Care (defensive)) | 0.21 | 0.282 | 0.099 | tailwind | CONFIRMED |
| FXI (China large-cap (EM proxy)) | -0.168 | -0.297 | -0.14 | headwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | 0.144 | 0.17 | 0.138 | tailwind | CONFIRMED |
| HG=F (Copper) | -0.137 | -0.249 | -0.036 | headwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.129 | 0.165 | 0.026 | tailwind | DIRECTIONAL |
| BTC-USD (Bitcoin (long-duration)) | 0.118 | None | 0.171 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | 0.087 | None | 0.087 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.077 | 0.166 | 0.034 | tailwind | DIRECTIONAL |
| CL=F (Oil (WTI)) | 0.059 | -0.102 | 0.251 | tailwind | CONTEXT |
| XLK (Technology) | -0.049 | 0.014 | -0.073 | headwind | CONTEXT |
| SPY (S&P 500) | 0.043 | 0.138 | -0.047 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.021 | -0.005 | -0.09 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.018 | -0.041 | -0.049 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.013 | 0.038 | -0.065 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.009 | 0.08 | -0.118 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.008 | -0.046 | 0.028 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.002 | -0.059 | 0.021 | neutral | CONTEXT |

### curvature — 2s5s10s curvature (butterfly)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| SPY (S&P 500) | -0.232 | -0.131 | -0.386 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.227 | None | -0.18 | headwind | CONTEXT |
| XLK (Technology) | -0.221 | -0.121 | -0.328 | headwind | CONFIRMED |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.205 | -0.109 | -0.329 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.203 | -0.098 | -0.308 | headwind | CONFIRMED |
| IWM (Russell 2000 (small caps)) | -0.193 | -0.116 | -0.309 | headwind | CONFIRMED |
| XLB (Materials (inflation beneficiary)) | -0.177 | -0.156 | -0.234 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.165 | 0.305 | -0.022 | tailwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.102 | -0.136 | -0.072 | headwind | CONFIRMED |
| XLRE (Real Estate (rate-sensitive)) | -0.097 | None | -0.097 | headwind | CONTEXT |
| XLP (Staples (defensive)) | -0.075 | -0.085 | -0.045 | headwind | DIRECTIONAL |
| XLV (Health Care (defensive)) | -0.074 | -0.072 | -0.078 | headwind | DIRECTIONAL |
| HG=F (Copper) | -0.053 | 0.068 | -0.211 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.043 | -0.045 | 0.001 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.031 | -0.033 | -0.031 | neutral | CONTEXT |
| GC=F (Gold) | -0.028 | 0.129 | -0.261 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.024 | 0.014 | -0.126 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | 0.001 | -0.028 | 0.114 | neutral | CONTEXT |

### slope_chg63 — 2s10s 63d change (steepening)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLRE (Real Estate (rate-sensitive)) | 0.323 | None | 0.323 | tailwind | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.162 | None | 0.139 | tailwind | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.111 | 0.028 | 0.213 | tailwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.098 | -0.121 | -0.099 | headwind | DIRECTIONAL |
| GC=F (Gold) | 0.092 | 0.014 | 0.199 | tailwind | DIRECTIONAL |
| HG=F (Copper) | -0.072 | -0.199 | 0.111 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.059 | -0.068 | 0.291 | tailwind | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.059 | 0.009 | 0.149 | tailwind | DIRECTIONAL |
| DX-Y.NYB (US Dollar (DXY)) | -0.054 | -0.029 | -0.121 | headwind | DIRECTIONAL |
| SPY (S&P 500) | 0.047 | -0.083 | 0.318 | tailwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.042 | -0.061 | 0.209 | tailwind | CONTEXT |
| CL=F (Oil (WTI)) | -0.037 | -0.045 | -0.06 | neutral | CONTEXT |
| XLK (Technology) | 0.026 | -0.105 | 0.26 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.016 | -0.036 | 0.028 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | 0.014 | -0.009 | 0.064 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.011 | -0.099 | 0.197 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.008 | -0.078 | 0.152 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.002 | -0.139 | 0.23 | neutral | CONTEXT |

### ntfs — Near-term forward spread

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| XLB (Materials (inflation beneficiary)) | -0.223 | -0.251 | -0.197 | headwind | CONFIRMED |
| XLK (Technology) | -0.215 | -0.066 | -0.332 | headwind | CONFIRMED |
| SPY (S&P 500) | -0.2 | -0.1 | -0.361 | headwind | CONFIRMED |
| XLF (Financials (rate beneficiary)) | -0.197 | -0.097 | -0.291 | headwind | CONFIRMED |
| BTC-USD (Bitcoin (long-duration)) | -0.19 | None | -0.155 | headwind | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.179 | -0.039 | -0.339 | headwind | DIRECTIONAL |
| IWM (Russell 2000 (small caps)) | -0.135 | -0.053 | -0.251 | headwind | CONFIRMED |
| XLP (Staples (defensive)) | -0.113 | -0.169 | -0.037 | headwind | DIRECTIONAL |
| FXI (China large-cap (EM proxy)) | -0.109 | -0.161 | -0.15 | headwind | CONFIRMED |
| TLT (Long Treasuries (20y+)) | 0.108 | 0.205 | -0.035 | tailwind | CONTEXT |
| GC=F (Gold) | -0.087 | 0.109 | -0.313 | headwind | CONTEXT |
| XLV (Health Care (defensive)) | -0.06 | -0.078 | -0.047 | headwind | DIRECTIONAL |
| XLE (Energy (inflation beneficiary)) | -0.056 | -0.086 | -0.045 | headwind | DIRECTIONAL |
| XLU (Utilities (bond proxy)) | -0.053 | -0.087 | -0.009 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | -0.048 | None | -0.048 | headwind | CONTEXT |
| CL=F (Oil (WTI)) | 0.025 | 0.086 | -0.015 | neutral | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.015 | -0.042 | 0.138 | neutral | CONTEXT |
| HG=F (Copper) | -0.01 | 0.143 | -0.18 | neutral | CONTEXT |

### real_speed_abs — |Real 10y 63d speed| (violence)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| GC=F (Gold) | 0.117 | 0.067 | 0.165 | tailwind | CONFIRMED |
| DX-Y.NYB (US Dollar (DXY)) | -0.096 | -0.156 | -0.002 | headwind | DIRECTIONAL |
| XLRE (Real Estate (rate-sensitive)) | 0.055 | None | 0.055 | tailwind | CONTEXT |
| XLF (Financials (rate beneficiary)) | -0.048 | -0.111 | 0.023 | headwind | CONTEXT |
| FXI (China large-cap (EM proxy)) | 0.032 | -0.008 | 0.077 | neutral | CONTEXT |
| TLT (Long Treasuries (20y+)) | 0.027 | -0.006 | 0.057 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.024 | -0.0 | 0.046 | neutral | CONTEXT |
| SPY (S&P 500) | -0.022 | -0.05 | 0.01 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | -0.021 | None | -0.035 | neutral | CONTEXT |
| IWM (Russell 2000 (small caps)) | -0.018 | -0.028 | -0.003 | neutral | CONTEXT |
| XLK (Technology) | -0.012 | -0.022 | 0.006 | neutral | CONTEXT |
| XLP (Staples (defensive)) | 0.011 | -0.037 | 0.054 | neutral | CONTEXT |
| XLV (Health Care (defensive)) | -0.011 | -0.051 | 0.039 | neutral | CONTEXT |
| HG=F (Copper) | 0.009 | 0.003 | -0.009 | neutral | CONTEXT |
| XLU (Utilities (bond proxy)) | -0.005 | -0.091 | 0.08 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | -0.005 | 0.073 | -0.094 | neutral | CONTEXT |
| XLE (Energy (inflation beneficiary)) | -0.002 | 0.021 | -0.041 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | 0.001 | 0.001 | 0.008 | neutral | CONTEXT |

### trend_spread — 3m10y trend (2y smooth, Faria-Verona)

| asset | IC (full) | pre | post | effect | verdict |
|---|--:|--:|--:|---|---|
| TLT (Long Treasuries (20y+)) | 0.123 | 0.123 | 0.03 | tailwind | DIRECTIONAL |
| XLP (Staples (defensive)) | 0.116 | 0.239 | -0.071 | tailwind | CONTEXT |
| GC=F (Gold) | -0.106 | 0.043 | -0.338 | headwind | CONTEXT |
| XLU (Utilities (bond proxy)) | 0.097 | 0.253 | -0.132 | tailwind | CONTEXT |
| XLV (Health Care (defensive)) | 0.096 | 0.174 | -0.045 | tailwind | CONTEXT |
| DX-Y.NYB (US Dollar (DXY)) | -0.094 | -0.124 | 0.084 | headwind | CONTEXT |
| IWM (Russell 2000 (small caps)) | 0.075 | 0.237 | -0.17 | tailwind | CONTEXT |
| XLRE (Real Estate (rate-sensitive)) | -0.066 | None | -0.066 | headwind | CONTEXT |
| XLE (Energy (inflation beneficiary)) | 0.057 | 0.161 | -0.099 | tailwind | CONTEXT |
| HG=F (Copper) | 0.048 | 0.204 | -0.216 | tailwind | CONTEXT |
| XLK (Technology) | -0.039 | 0.149 | -0.182 | neutral | CONTEXT |
| XLF (Financials (rate beneficiary)) | 0.036 | 0.21 | -0.177 | neutral | CONTEXT |
| XLB (Materials (inflation beneficiary)) | 0.025 | 0.093 | -0.112 | neutral | CONTEXT |
| FXI (China large-cap (EM proxy)) | -0.023 | -0.152 | -0.093 | neutral | CONTEXT |
| CL=F (Oil (WTI)) | 0.02 | 0.038 | -0.005 | neutral | CONTEXT |
| QQQ (Nasdaq 100 (long-duration growth)) | -0.018 | 0.144 | -0.196 | neutral | CONTEXT |
| BTC-USD (Bitcoin (long-duration)) | 0.006 | None | 0.061 | neutral | CONTEXT |
| SPY (S&P 500) | -0.005 | 0.144 | -0.265 | neutral | CONTEXT |

## Collinearity vs already-scored legs

VIF (>5 redundant) and the top correlated pairs — a 'new' leg that merely restates the breakeven-direction / TIPS-nominal / sticky-CPI legs already in the inflation axis is caught here and NOT double-counted.

| driver | VIF |
|---|--:|
| nom10y_chg63 | 41503906610716.22 |
| be10y | 34501448353393.85 |
| _scored_tips_nominal | 34501272616380.25 |
| real10y_chg63 | 29020534616804.94 |
| be10y_chg63 | 18890822682236.19 |
| be5y5y | 16.64 |
| exp_wedge | 15.57 |
| ntfs | 13.91 |
| policy_gap | 11.6 |
| real10y | 10.36 |
| curve_tp_adj | 7.65 |
| trend_spread | 3.79 |
| corepce_gap | 3.55 |
| curvature | 2.9 |
| slope_chg63 | 2.9 |
| infl_accel | 1.97 |
| _scored_be10y_chg | 1.77 |
| _scored_sticky_dir | 1.54 |
| real_speed_abs | 1.36 |

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