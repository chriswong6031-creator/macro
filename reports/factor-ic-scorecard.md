# Factor IC scorecard (leak-free, point-in-time)

Span 2023-06-30..2025-12-31 · 11 quarterly rebalances · forward 63d · ~886 names · point-in-time (no look-ahead).

IC = cross-sectional rank correlation of each factor's z-score vs the forward return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. Judge survivors against ~0 — post point-in-time fix the spreads are honestly weaker.

| factor | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| sue | 0.0386 | 0.614 | 1.227 | 3.162 | 0.0016 | 0.0192 | 0.818 | 11 |
| value | 0.0307 | 0.307 | 0.615 | 1.034 | 0.3011 | 0.5162 | 0.636 | 11 |
| composite | 0.015 | 0.255 | 0.511 | 1.034 | 0.301 | 0.5162 | 0.727 | 11 |
| short_interest | 0.0193 | 0.24 | 0.479 | 0.929 | 0.353 | 0.5295 | 0.636 | 11 |
| payout | 0.013 | 0.234 | 0.468 | 1.062 | 0.2882 | 0.5162 | 0.545 | 11 |
| composite_orth | 0.0141 | 0.145 | 0.29 | 0.835 | 0.4038 | 0.5384 | 0.545 | 11 |
| low_vol | 0.0197 | 0.114 | 0.229 | 0.464 | 0.6425 | 0.771 | 0.556 | 9 |
| investment | 0.0 | 0.001 | 0.002 | 0.002 | 0.9981 | 0.9981 | 0.636 | 11 |
| low_beta | -0.0182 | -0.08 | -0.16 | -0.348 | 0.7278 | 0.794 | 0.455 | 11 |
| quality | -0.0226 | -0.375 | -0.75 | -1.8 | 0.0718 | 0.2872 | 0.364 | 11 |
| profitability | -0.0403 | -0.382 | -0.764 | -1.213 | 0.2252 | 0.5162 | 0.455 | 11 |
| accruals | -0.0209 | -0.503 | -1.005 | -2.016 | 0.0437 | 0.2622 | 0.364 | 11 |

**Survive BH-FDR(10%):** sue

## Factor overlap (latest cross-section)

`composite_orth` above is the Löwdin-decorrelated composite. Mean |factor corr| **0.112** raw → **0.05** orthogonalized (the redundancy removed). VIF>5 = redundant. Most-correlated pairs:
- low_vol ↔ low_beta: |corr| 0.72
- quality ↔ accruals: |corr| 0.71

> Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0.