# Factor IC scorecard (leak-free, point-in-time)

Span 2023-06-30..2025-12-31 · 11 quarterly rebalances · forward 63d · ~886 names · point-in-time (no look-ahead).

IC = cross-sectional rank correlation of each factor's z-score vs the forward return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. Judge survivors against ~0 — post point-in-time fix the spreads are honestly weaker.

| factor | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| value | 0.0307 | 0.307 | 0.615 | 1.034 | 0.3011 | 0.5538 | 0.636 | 11 |
| composite | 0.015 | 0.254 | 0.509 | 1.032 | 0.3021 | 0.5538 | 0.727 | 11 |
| short_interest | 0.0193 | 0.24 | 0.479 | 0.929 | 0.353 | 0.5547 | 0.636 | 11 |
| payout | 0.013 | 0.234 | 0.468 | 1.062 | 0.2882 | 0.5538 | 0.545 | 11 |
| low_vol | 0.0193 | 0.112 | 0.224 | 0.456 | 0.6482 | 0.8913 | 0.556 | 9 |
| composite_orth | 0.0032 | 0.035 | 0.069 | 0.202 | 0.84 | 0.924 | 0.545 | 11 |
| investment | 0.0 | 0.001 | 0.002 | 0.002 | 0.9981 | 0.9981 | 0.636 | 11 |
| low_beta | -0.018 | -0.079 | -0.158 | -0.344 | 0.7306 | 0.893 | 0.455 | 11 |
| quality | -0.0226 | -0.375 | -0.75 | -1.8 | 0.0718 | 0.3949 | 0.364 | 11 |
| profitability | -0.0403 | -0.382 | -0.764 | -1.213 | 0.2252 | 0.5538 | 0.455 | 11 |
| accruals | -0.0209 | -0.503 | -1.005 | -2.016 | 0.0437 | 0.3949 | 0.364 | 11 |

**Survive BH-FDR(10%):** NONE

## Factor overlap (latest cross-section)

`composite_orth` above is the Löwdin-decorrelated composite. Mean |factor corr| **0.126** raw → **0.054** orthogonalized (the redundancy removed). VIF>5 = redundant. Most-correlated pairs:
- quality ↔ accruals: |corr| 0.72
- low_vol ↔ low_beta: |corr| 0.72

> Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0.