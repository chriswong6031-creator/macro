# China QUALITY factor (ROE) — Phase 0

*`scripts/china_quality_phase0.py` (akshare weighted-ROE, FY, point-in-time +4mo lag). Each month sort into 5 ROE quintiles, long each EW 21d. Q1 = highest ROE (quality), Q5 = lowest (junk). The premium = Q1 out-returns/out-Sharpes Q5 + the market; quality−junk = the Q1−Q5 spread. 203 names with ROE, 120 monthly rebalances, 2016-05-31→2026-04-30.*

**Market baseline (EW):** ann 23.9% · Sharpe **1.3** · maxDD -25.2%.

## ROE (weighted, FY) · cross-sectional

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 quality (highest ROE) | 21.7% | 0.96 | -36.6% | 0.642 | 120 |
| Q2 | 22.3% | 1.13 | -26.4% | 0.642 | 120 |
| Q3 | 22.4% | 1.39 | -22.5% | 0.675 | 120 |
| Q4 | 21.0% | 1.11 | -23.3% | 0.592 | 120 |
| Q5 junk (lowest ROE) | 32.0% | 1.4 | -26.4% | 0.658 | 120 |

**quality−junk spread (Q1−Q5):** Sharpe **-0.58** · ann -10.3% · maxDD -80.7% · hit 0.458.

## ROE (weighted, FY) · sector-neutral

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 quality (highest ROE) | 22.5% | 1.0 | -30.5% | 0.65 | 120 |
| Q2 | 20.1% | 1.12 | -24.7% | 0.625 | 120 |
| Q3 | 22.3% | 1.33 | -29.1% | 0.7 | 120 |
| Q4 | 22.8% | 1.14 | -25.9% | 0.6 | 120 |
| Q5 junk (lowest ROE) | 31.9% | 1.5 | -24.3% | 0.658 | 120 |

**quality−junk spread (Q1−Q5):** Sharpe **-0.71** · ann -9.4% · maxDD -68.6% · hit 0.408.

---

**How to read.** A quality premium shows Q1 (high ROE) out-returning Q5 (low ROE) with a positive quality−junk spread Sharpe and a monotone Q1→Q5 decline. Quality is a different mechanism from value (which failed here): it can work in growth-favouring markets. FY ROE is lagged +4mo for PIT; akshare coverage is partial. If quality validates, Tushare daily_basic + fina_indicator (bulk, by date) is the clean production source — worth the points.
