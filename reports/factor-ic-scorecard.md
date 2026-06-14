# Factor IC scorecard (leak-free, point-in-time)

Span 2023-06-30..2025-12-31 · 11 quarterly rebalances · forward 63d · ~537 names · point-in-time (no look-ahead).

IC = cross-sectional rank correlation of each factor's z-score vs the forward return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. Judge survivors against ~0 — post point-in-time fix the spreads are honestly weaker.

| factor | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| sue | 0.0354 | 0.456 | 0.911 | 2.342 | 0.0192 | 0.0768 | 0.636 | 11 |
| value | 0.0446 | 0.344 | 0.688 | 1.14 | 0.2544 | 0.6106 | 0.636 | 11 |
| payout | 0.0089 | 0.189 | 0.378 | 0.644 | 0.5193 | 0.9281 | 0.636 | 11 |
| composite | 0.0022 | 0.032 | 0.064 | 0.122 | 0.9031 | 0.9549 | 0.545 | 11 |
| low_vol | 0.0021 | 0.014 | 0.028 | 0.057 | 0.9549 | 0.9549 | 0.444 | 9 |
| composite_orth | -0.0015 | -0.021 | -0.043 | -0.122 | 0.9025 | 0.9549 | 0.545 | 11 |
| short_interest | -0.0024 | -0.033 | -0.065 | -0.119 | 0.9055 | 0.9549 | 0.273 | 11 |
| investment | -0.006 | -0.095 | -0.191 | -0.366 | 0.7143 | 0.9549 | 0.455 | 11 |
| low_beta | -0.0313 | -0.142 | -0.284 | -0.611 | 0.5414 | 0.9281 | 0.455 | 11 |
| profitability | -0.0442 | -0.432 | -0.864 | -1.486 | 0.1374 | 0.4122 | 0.455 | 11 |
| accruals | -0.0296 | -0.694 | -1.387 | -2.456 | 0.014 | 0.0768 | 0.182 | 11 |
| quality | -0.0432 | -0.721 | -1.443 | -2.905 | 0.0037 | 0.0444 | 0.182 | 11 |

**Survive BH-FDR(10%):** quality, accruals, sue

## Factor overlap (latest cross-section)

`composite_orth` above is the Löwdin-decorrelated composite. Mean |factor corr| **0.12** raw → **0.059** orthogonalized (the redundancy removed). VIF>5 = redundant. Most-correlated pairs:
- quality ↔ accruals: |corr| 0.73
- low_vol ↔ low_beta: |corr| 0.71

> Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0.