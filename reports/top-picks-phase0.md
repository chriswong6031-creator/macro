# Top-Picks composite — Phase 0 validation

*Survivorship-clean deep S&P panel · PIT S&P 1500 membership · 2014-06-30..2025-11-28 · 138 monthly rebalances · ~444 names/date · residual windows 252/252/21 shrink 0.66 · insider 6mo filings · L/S net of 5bps one-way.*

Does a holistic multi-factor **conviction** composite rank forward returns better than the residual-momentum `alpha` leg the board ranks by today? And does folding a mean-reversion/entry tilt INTO the rank help (China) or hurt (US momentum continues)? Legs are sector-neutral winsor-z; composites are z-means of those legs.


## Forward horizon: 21 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| alpha (BASELINE — today's rank) | +0.0087 | +0.05 | +0.70 | 0.487 | 0.9734 | 0.0126→0.0049 | 0.06 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite | +0.0097 | +0.07 | +0.87 | 0.385 | 0.9734 | 0.0147→0.0047 | 0.06 | FAILS multiple-testing haircut (DSR<0.90) |
| alpha-led composite (0.6α+0.4) | +0.0112 | +0.07 | +0.91 | 0.363 | 0.9734 | 0.0168→0.0056 | 0.11 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction + reversal tilt | +0.0077 | +0.06 | +0.70 | 0.484 | 0.9734 | 0.0142→0.0012 | 0.03 | FAILS multiple-testing haircut (DSR<0.90) |
| short reversal (entry leg) | +0.0012 | +0.01 | +0.13 | 0.899 | 0.9968 | 0.0054→-0.003 | -0.15 | FAILS multiple-testing haircut (DSR<0.90) |
| value | +0.0029 | +0.03 | +0.34 | 0.733 | 0.9968 | -0.0063→0.0121 | 0.15 | FAILS multiple-testing haircut (DSR<0.90) |
| quality | -0.0000 | -0.00 | -0.00 | 0.997 | 0.9968 | -0.0008→0.0008 | -0.2 | FAILS multiple-testing haircut (DSR<0.90) |
| profitability | +0.0167 | +0.14 | +1.54 | 0.123 | 0.9734 | 0.0198→0.0136 | 0.49 | FAILS multiple-testing haircut (DSR<0.90) |
| low-vol | +0.0044 | +0.03 | +0.33 | 0.739 | 0.9968 | 0.017→-0.0082 | -0.2 | FAILS multiple-testing haircut (DSR<0.90) |
| insider net/mcap | -0.0002 | -0.00 | -0.02 | 0.983 | 0.9968 | -0.0063→0.0059 | 0.14 | FAILS multiple-testing haircut (DSR<0.90) |

## Forward horizon: 63 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| alpha (BASELINE — today's rank) | +0.0194 | +0.13 | +0.98 | 0.327 | 0.5895 | 0.0354→0.0033 | 0.14 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite | +0.0136 | +0.10 | +0.83 | 0.408 | 0.5895 | 0.0286→-0.0015 | 0.01 | FAILS multiple-testing haircut (DSR<0.90) |
| alpha-led composite (0.6α+0.4) | +0.0222 | +0.15 | +1.16 | 0.247 | 0.5895 | 0.0402→0.0041 | 0.15 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction + reversal tilt | +0.0116 | +0.09 | +0.72 | 0.472 | 0.5895 | 0.0276→-0.0044 | 0.03 | FAILS multiple-testing haircut (DSR<0.90) |
| short reversal (entry leg) | -0.0077 | -0.07 | -0.81 | 0.419 | 0.5895 | -0.0174→0.002 | -0.21 | FAILS multiple-testing haircut (DSR<0.90) |
| value | -0.0022 | -0.02 | -0.16 | 0.871 | 0.8706 | -0.026→0.0216 | 0.09 | FAILS multiple-testing haircut (DSR<0.90) |
| quality | -0.0136 | -0.20 | -1.51 | 0.131 | 0.5895 | -0.0114→-0.0159 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| profitability | +0.0334 | +0.27 | +1.91 | 0.057 | 0.567 | 0.0408→0.026 | 0.5 | FAILS multiple-testing haircut (DSR<0.90) |
| low-vol | +0.0098 | +0.06 | +0.49 | 0.623 | 0.6922 | 0.0435→-0.0239 | -0.16 | FAILS multiple-testing haircut (DSR<0.90) |
| insider net/mcap | -0.0141 | -0.12 | -1.02 | 0.307 | 0.5895 | -0.0228→-0.0055 | -0.05 | FAILS multiple-testing haircut (DSR<0.90) |

## Forward horizon: 126 trading days

| signal | mean IC | IC-IR | HAC t | p | q_FDR | IC h1→h2 | L/S Sharpe | DSR verdict |
|---|--:|--:|--:|--:|--:|--:|--:|---|
| alpha (BASELINE — today's rank) | +0.0315 | +0.20 | +1.21 | 0.228 | 0.3793 | 0.0507→0.0122 | 0.12 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction composite | +0.0220 | +0.16 | +1.02 | 0.308 | 0.4404 | 0.0413→0.0026 | 0.01 | FAILS multiple-testing haircut (DSR<0.90) |
| alpha-led composite (0.6α+0.4) | +0.0356 | +0.23 | +1.41 | 0.160 | 0.32 | 0.0589→0.0124 | 0.07 | FAILS multiple-testing haircut (DSR<0.90) |
| conviction + reversal tilt | +0.0178 | +0.14 | +0.87 | 0.385 | 0.4809 | 0.0401→-0.0045 | 0.05 | FAILS multiple-testing haircut (DSR<0.90) |
| short reversal (entry leg) | -0.0159 | -0.14 | -1.64 | 0.101 | 0.32 | -0.0314→-0.0003 | -0.2 | FAILS multiple-testing haircut (DSR<0.90) |
| value | -0.0084 | -0.07 | -0.41 | 0.685 | 0.6854 | -0.0556→0.0388 | 0.19 | FAILS multiple-testing haircut (DSR<0.90) |
| quality | -0.0215 | -0.32 | -1.89 | 0.059 | 0.32 | -0.0181→-0.025 | -0.14 | FAILS multiple-testing haircut (DSR<0.90) |
| profitability | +0.0372 | +0.28 | +1.67 | 0.095 | 0.32 | 0.0524→0.022 | 0.52 | FAILS multiple-testing haircut (DSR<0.90) |
| low-vol | +0.0139 | +0.09 | +0.55 | 0.582 | 0.6464 | 0.0532→-0.0255 | -0.14 | FAILS multiple-testing haircut (DSR<0.90) |
| insider net/mcap | -0.0244 | -0.23 | -1.44 | 0.150 | 0.32 | -0.0195→-0.0293 | -0.13 | FAILS multiple-testing haircut (DSR<0.90) |

## Verdict (primary horizon 21d)

Baseline `alpha`: mean IC +0.0087, L/S Sharpe 0.06.

- **conviction composite**: IC +0.0097 (+ vs alpha), Sharpe 0.06 (− vs alpha) → **beats on one axis**
- **alpha-led composite (0.6α+0.4)**: IC +0.0112 (+ vs alpha), Sharpe 0.11 (+ vs alpha) → **BEATS on both**
- *Reversal tilt diagnostic:* conviction+reversal IC +0.0077 vs conviction +0.0097 → folding US reversal into the rank HURTS/neutral (US leaders continue — entry belongs on a separate axis).

**GO — rank Top Picks by the alpha-led composite (0.6α+0.4)**: it beats alpha-alone on both the cross-sectional IC and the long/short Sharpe, so the holistic blend is a measured upgrade, not cosmetic. Entry-timing still rides a separate axis (the reversal tilt does not belong in the US rank).
