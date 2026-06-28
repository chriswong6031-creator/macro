# Reversal on a true non-survivor panel — is the edge just survivorship bias?

**Verdict: NO-GO.** CLOSE THE BOOK — residual reversal is net-NEGATIVE after cost on BOTH the survivor (-2.45%/yr) and the non-survivor (-2.68%/yr) S&P 500 universe, both insignificant; survivorship makes it worse (drag 0.23%/yr) and that is only a LOWER bound — the worst losers are unrecoverable. No tradeable edge: do not give reversal an entry tilt.

Span 1996-01-31..2026-04-30 · 364 monthly rebalances · S&P 500 point-in-time membership · 829 names (753 survivors + 76 recovered delisted/removed).

| panel | median breadth | mean IC | IC t_HAC | gross Sharpe | net@10 Sharpe | net@10 t_HAC | net@10 %/yr |
|---|--:|--:|--:|--:|--:|--:|--:|
| survivor-biased | 325 | 0.0035 | 0.44 | -0.077 | -0.181 | -1.026 | -2.45 |
| **non-survivor** | 335 | 0.0026 | 0.338 | -0.095 | -0.2 | -1.143 | -2.68 |

**Survivorship drag on net reversal: 0.23 %/yr** (survivor -2.45 → non-survivor -2.68). Reversal goes long recent losers; the removed names are disproportionately recent losers, so including them is what erodes the edge.

> Yahoo close prices, $5 price floor + ±50% monthly-return clip (robust to the noisy free-source delisted data). Only 76 genuinely-delisted names recovered vs 373 unrecoverable — and Yahoo retains the BENIGN exits (acquisitions/demotions) while dropping the MALIGNANT ones (bankruptcies, true ~-100% blow-ups). So the non-survivor panel still omits the worst losers: the measured drag is a LOWER bound and the clip flatters reversal — a NO-GO here is only stronger. A definitive deep test needs CRSP delisting returns. Universe = S&P 500 PIT.