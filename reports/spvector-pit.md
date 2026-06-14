# S&P / Macro Vector — ALFRED point-in-time validation

*Swapped to INITIAL-RELEASE (publication-timed) values: recession_prob, term_premium_10y/curve_tp_adj. Sahm already real-time. NFCI + EBP have no ALFRED path -> keep the publication-lag approximation. Same per-leg lags on both sides, so this isolates the revised-vs-PIT DATA effect.*

| | revised+lag (shipped) | genuine PIT |
|---|--:|--:|
| CAGR | 13.01 | 12.55 |
| Sharpe | 0.92 | 0.9 |
| MaxDD | -33.2 | -32.5 |
| DSR | 0.9994 | 0.999 |

leave-one-crisis-out (Sharpe edge vs B&H):
- revised+lag: dotcom +0.28, GFC +0.15, COVID +0.3, 2022 +0.29
- genuine PIT: dotcom +0.24, GFC +0.15, COVID +0.28, 2022 +0.27

## Verdict
CONFIRMED — the edge holds on genuinely point-in-time data; the publication-lag approximation was sound (Sharpe/MaxDD/leave-one-crisis-out essentially unchanged). The revised-data look-ahead was NOT driving the result.

_Residual: NFCI + EBP still revised (no ALFRED vintages). They feed the drawdown gauge but are not the load-bearing leg; the publication-lag buffer remains for them._
