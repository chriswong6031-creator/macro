# China low-volatility / low-beta — Phase 0

*`scripts/china_lowvol_phase0.py`. Tests the low-RISK anomaly on the deep A-share panel (no external data). Each month sort the universe into 5 factor quintiles, long each EW for 21d; the anomaly = the LOW-risk quintile (Q1) earns a higher risk-adjusted return (Sharpe) than the HIGH-risk quintile (Q5) and the market, even if raw returns are similar. low−high = the long-short spread (Q1 minus Q5). Panel 790 names, 413 monthly rebalances, 1990-12-19→2026-06-12.*

**Market baseline (EW universe):** ann 27.6% · Sharpe **0.88** · maxDD -65.8%.

## low VOL (trailing 252d σ) · cross-sectional

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 lowest | 27.2% | 0.96 | -55.4% | 0.612 | 369 |
| Q2 | 24.6% | 0.83 | -68.5% | 0.604 | 369 |
| Q3 | 27.9% | 0.87 | -68.3% | 0.618 | 369 |
| Q4 | 29.3% | 0.81 | -69.6% | 0.585 | 369 |
| Q5 highest | 29.4% | 0.76 | -70.7% | 0.591 | 369 |

**low−high spread (Q1−Q5):** Sharpe **-0.08** · ann -2.2% · maxDD -96.7% · hit 0.518.

## low VOL (trailing 252d σ) · sector-neutral

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 lowest | 27.1% | 0.98 | -57.5% | 0.618 | 369 |
| Q2 | 25.8% | 0.84 | -67.0% | 0.623 | 369 |
| Q3 | 28.5% | 0.87 | -65.0% | 0.621 | 369 |
| Q4 | 28.2% | 0.83 | -70.3% | 0.596 | 369 |
| Q5 highest | 28.9% | 0.76 | -70.4% | 0.588 | 369 |

**low−high spread (Q1−Q5):** Sharpe **-0.08** · ann -1.8% · maxDD -91.2% · hit 0.518.

## low BETA (causal 252d) · cross-sectional

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 lowest | 24.3% | 0.93 | -60.6% | 0.621 | 340 |
| Q2 | 25.0% | 0.87 | -64.5% | 0.641 | 340 |
| Q3 | 25.2% | 0.83 | -67.4% | 0.609 | 340 |
| Q4 | 28.2% | 0.85 | -65.9% | 0.609 | 340 |
| Q5 highest | 24.5% | 0.67 | -72.5% | 0.571 | 340 |

**low−high spread (Q1−Q5):** Sharpe **-0.01** · ann -0.2% · maxDD -90.8% · hit 0.553.

## low BETA (causal 252d) · sector-neutral

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 lowest | 24.9% | 0.94 | -61.0% | 0.629 | 340 |
| Q2 | 23.6% | 0.82 | -64.8% | 0.641 | 340 |
| Q3 | 27.8% | 0.91 | -67.3% | 0.635 | 340 |
| Q4 | 26.0% | 0.81 | -64.6% | 0.615 | 340 |
| Q5 highest | 25.1% | 0.71 | -72.8% | 0.562 | 340 |

**low−high spread (Q1−Q5):** Sharpe **-0.02** · ann -0.3% · maxDD -81.6% · hit 0.562.

---

**How to read.** A clean low-vol anomaly shows a MONOTONE Sharpe decline Q1→Q5 (lowest-risk wins risk-adjusted) and a positive low−high spread Sharpe. If Q1 also beats the market Sharpe, low-vol is a defensible A-share factor (a tilt / defensive sleeve, framed as risk-adjusted not higher-raw-return). Excess/returns here are gross, pre-cost; low-vol is low-turnover so costs bite less than reversal.
