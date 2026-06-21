# Capacity / market-impact scorecard

_2026-06-21T14:53:25+00:00_ · 40 names · √-impact η=0.1, linear 3.0bps · demo signal: 12-1 momentum long/flat (no alpha claimed — turnover vehicle)

Model: `net = gross - (cost_bps + eta*sigma*sqrt(traded$/ADV$))*turnover`. participation = traded$/ADV$, traded$ = AUM·|Δpos|. Capacity = largest AUM whose NET Sharpe still beats buy & hold.

| ticker | ADV $M | gross SR | buy&hold SR | capacity |
|---|--:|--:|--:|--:|
| BA | 31 | 0.574 | 0.492 | $1M |
| DUK | 32 | 0.684 | 0.626 | $1M |
| AMT | 118 | 0.588 | 0.432 | $100M |
| EQIX | 103 | 0.602 | 0.373 | $100M |
| AMZN | 905 | 0.853 | 0.76 | $500M |
| CCI | 62 | 0.594 | 0.42 | $500M |
| CTVA | 154 | 0.809 | 0.62 | $500M |
| AAPL | 215 | 0.517 | 0.625 | no edge |
| ABBV | 483 | 0.549 | 0.799 | no edge |
| ABT | 91 | 0.566 | 0.655 | no edge |
| AEP | 2 | 0.467 | 0.476 | no edge |
| AMAT | 208 | 0.54 | 0.649 | no edge |
| AMD | 64 | 0.295 | 0.484 | no edge |
| AMGN | 270 | 0.595 | 0.639 | no edge |
| APD | 25 | 0.348 | 0.544 | no edge |
| AVGO | 470 | 0.895 | 1.107 | no edge |
| AXP | 110 | 0.38 | 0.473 | no edge |
| BAC | 132 | 0.372 | 0.368 | no edge |
| BKNG | 513 | 0.436 | 0.435 | no edge |
| BKR | 72 | 0.234 | 0.349 | no edge |
| BRK-B | 334 | 0.56 | 0.568 | no edge |
| C | 307 | 0.288 | 0.354 | no edge |
| CAT | 16 | 0.424 | 0.55 | no edge |
| CEG | 431 | 0.703 | 1.125 | no edge |
| CL | 43 | 0.496 | 0.523 | no edge |

**Binding capacity:** ~$1M (the lowest-capacity name with a gross edge caps a single-sleeve deployment). 'no edge' = the demo signal doesn't beat buy & hold even costless (not a capacity limit); '≥grid max' = capacity exceeds the grid. Higher-ADV names hold orders of magnitude more — the discrimination a flat bps can't make. NOT an alpha claim.

