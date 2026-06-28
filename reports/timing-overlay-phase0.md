# Breadth/liquidity net-exposure timing overlay — does it earn its keep?

**Verdict: GO.** Ship it as a net-exposure / drawdown overlay (a RISK lever, like vol-managed sizing — it trades a little CAGR for far shallower drawdowns), orthogonal to the dispersion (selection) gate. It IS worth having as a net-exposure / drawdown overlay: lifts Sharpe 0.42→0.582 and cuts maxDD -86.2%→-52.0% net of cost. Leg attribution (same-span): breadth is REDUNDANT with trend (deep 1962+); net-liquidity ADDS over breadth+trend (2014+).


Span 1927-12-30..2026-06-12 · daily · net of 3.0bps per unit exposure change · legs: trend, breadth, netliq.

| strategy | Sharpe | CAGR % | maxDD % | vol % | days |
|---|--:|--:|--:|--:|--:|
| buy_hold | 0.42 | 6.35 | -86.2 | 18.9 | 24728 |
| overlay_combined | 0.582 | 6.6 | -52.0 | 12.3 | 24728 |
| leg_trend | 0.586 | 6.58 | -52.0 | 12.1 | 24728 |
| leg_breadth | 0.59 | 6.79 | -54.6 | 12.5 | 16020 |
| leg_netliq | 0.627 | 8.09 | -33.9 | 14.0 | 2704 |
| overlay_breadth_trend_deep | 0.581 | 6.63 | -52.0 | 12.4 | 24728 |
| overlay_2014_breadth_trend | 0.821 | 9.66 | -21.0 | 12.1 | 2704 |
| overlay_2014_plus_netliq | 0.856 | 9.35 | -24.5 | 11.2 | 2704 |

**Combined overlay − buy&hold:** -0.81%/yr.

> Net-exposure (TIME-SERIES) timer — orthogonal to the dispersion gate (CROSS-SECTIONAL selection gross): a book uses both. Cash earns 0 (conservative). Trend/breadth legs are deep (1962-2026); net-liq is 2014+, so its marginal value is judged on the 2014-block rows. Timing typically trades return for drawdown — judge on Sharpe + maxDD, not CAGR.