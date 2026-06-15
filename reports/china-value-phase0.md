# China VALUE factor (earnings yield) — Phase 0

*`scripts/china_value_phase0.py` (akshare PE-TTM fallback — Tushare account had no access). Tests the value premium: each month sort into 5 earnings-yield (1/PE) quintiles, long each EW 21d. Q1 = cheapest (highest E/P), Q5 = priciest. The premium = Q1 out-returns/out-Sharpes Q5 + the market; value−growth = the Q1−Q5 spread. 790 names with PE, 119 monthly rebalances, 2016-06-30→2026-04-30. Loss-makers (PE<=0) dropped.*

**Market baseline (EW):** ann 22.1% · Sharpe **1.05** · maxDD -26.3%.

## earnings yield (1/PE) · cross-sectional

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 value (cheapest) | 15.6% | 0.94 | -29.4% | 0.622 | 119 |
| Q2 | 17.0% | 0.91 | -28.6% | 0.597 | 119 |
| Q3 | 24.8% | 1.08 | -32.8% | 0.639 | 119 |
| Q4 | 23.7% | 0.89 | -38.5% | 0.622 | 119 |
| Q5 growth (priciest) | 29.2% | 0.94 | -39.8% | 0.58 | 119 |

**value−growth spread (Q1−Q5):** Sharpe **-0.46** · ann -13.6% · maxDD -89.2% · hit 0.487.

## earnings yield (1/PE) · sector-neutral

| quintile | ann return | Sharpe | max drawdown | hit | n |
|---|--:|--:|--:|--:|--:|
| Q1 value (cheapest) | 17.8% | 1.06 | -29.6% | 0.63 | 119 |
| Q2 | 23.3% | 1.13 | -26.0% | 0.697 | 119 |
| Q3 | 24.4% | 1.02 | -33.4% | 0.613 | 119 |
| Q4 | 28.1% | 1.08 | -36.4% | 0.588 | 119 |
| Q5 growth (priciest) | 16.7% | 0.67 | -40.0% | 0.538 | 119 |

**value−growth spread (Q1−Q5):** Sharpe **0.06** · ann 1.1% · maxDD -48.3% · hit 0.504.

---

**How to read.** A value premium shows Q1 (cheapest) out-returning Q5 (priciest) with a positive value−growth spread Sharpe; a MONOTONE return decline Q1→Q5 is the clean signature. A-share value is regime-dependent (weak pre-2017), so the era in the panel matters. PE-TTM is point-in-time-ish (Baidu daily); akshare per-stock coverage is partial — treat a thin panel cautiously. If it validates, the clean rebuild is Tushare daily_basic (bulk PE/PB/ROE by date) once the account has points.
