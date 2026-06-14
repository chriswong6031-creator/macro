# Factor IC scorecard (leak-free, point-in-time)

Span 2023-06-30..2025-12-31 · 11 quarterly rebalances · forward 63d · ~1323 names · point-in-time (no look-ahead).

IC = cross-sectional rank correlation of each factor's z-score vs the forward return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. Judge survivors against ~0 — post point-in-time fix the spreads are honestly weaker.

| factor | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| payout | 0.0232 | 0.409 | 0.817 | 1.604 | 0.1087 | 0.3229 | 0.636 | 11 |
| short_interest | 0.0326 | 0.402 | 0.805 | 1.731 | 0.0834 | 0.3229 | 0.636 | 11 |
| value | 0.0285 | 0.319 | 0.638 | 1.162 | 0.2452 | 0.5394 | 0.727 | 11 |
| composite | 0.0126 | 0.134 | 0.268 | 0.501 | 0.6166 | 0.8478 | 0.545 | 11 |
| low_vol | 0.0079 | 0.037 | 0.074 | 0.151 | 0.88 | 0.9286 | 0.556 | 9 |
| composite_orth | -0.0021 | -0.017 | -0.035 | -0.09 | 0.9286 | 0.9286 | 0.545 | 11 |
| investment | -0.0051 | -0.11 | -0.219 | -0.304 | 0.7609 | 0.9286 | 0.455 | 11 |
| low_beta | -0.0358 | -0.14 | -0.28 | -0.646 | 0.5182 | 0.8143 | 0.455 | 11 |
| quality | -0.0213 | -0.318 | -0.635 | -1.566 | 0.1174 | 0.3229 | 0.455 | 11 |
| profitability | -0.0339 | -0.319 | -0.639 | -1.014 | 0.3105 | 0.5692 | 0.364 | 11 |
| accruals | -0.0171 | -0.371 | -0.743 | -1.681 | 0.0928 | 0.3229 | 0.455 | 11 |

**Survive BH-FDR(10%):** NONE

## Factor overlap (latest cross-section)

`composite_orth` above is the Löwdin-decorrelated composite. Mean |factor corr| **0.126** raw → **0.054** orthogonalized (the redundancy removed). VIF>5 = redundant. Most-correlated pairs:
- low_vol ↔ low_beta: |corr| 0.73
- quality ↔ accruals: |corr| 0.72

> Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0.