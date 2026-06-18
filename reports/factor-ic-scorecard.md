# Factor IC scorecard (leak-free, point-in-time)

Span 2011-03-31..2025-12-31 · 60 quarterly rebalances · forward 63d · ~1154 names · price panel **deep ~2011-2026, survivorship-biased** · point-in-time (no look-ahead).

IC = cross-sectional rank correlation of each factor's z-score vs the forward return, per rebalance. `t_HAC` is Newey-West (overlapping windows autocorrelate the IC series); `q_FDR` is Benjamini-Hochberg across the factor panel. Judge survivors against ~0 — post point-in-time fix the spreads are honestly weaker.

| factor | mean IC | IC-IR | IC-IR ann | t_HAC | p | q_FDR | hit | n |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| payout | 0.0247 | 0.298 | 0.596 | 2.723 | 0.0065 | 0.0715 | 0.583 | 60 |
| value | 0.0184 | 0.223 | 0.446 | 2.006 | 0.0449 | 0.247 | 0.55 | 60 |
| profitability | 0.0141 | 0.12 | 0.24 | 0.82 | 0.4125 | 0.9309 | 0.55 | 60 |
| accruals | 0.007 | 0.099 | 0.198 | 0.729 | 0.4663 | 0.9309 | 0.55 | 60 |
| quality | 0.0042 | 0.073 | 0.146 | 0.564 | 0.5731 | 0.9309 | 0.533 | 60 |
| composite_orth | 0.0024 | 0.015 | 0.031 | 0.124 | 0.9011 | 0.9482 | 0.483 | 60 |
| sue | 0.0006 | 0.009 | 0.017 | 0.065 | 0.9482 | 0.9482 | 0.517 | 60 |
| investment | -0.0029 | -0.036 | -0.072 | -0.288 | 0.7737 | 0.9456 | 0.5 | 60 |
| composite | -0.0072 | -0.049 | -0.097 | -0.396 | 0.6924 | 0.9456 | 0.45 | 60 |
| low_beta | -0.0151 | -0.063 | -0.127 | -0.535 | 0.5924 | 0.9309 | 0.533 | 60 |
| low_vol | -0.0209 | -0.093 | -0.186 | -0.742 | 0.4583 | 0.9309 | 0.467 | 60 |

**Survive BH-FDR(10%):** payout

## Factor overlap (latest cross-section)

`composite_orth` above is the Löwdin-decorrelated composite. Mean |factor corr| **0.137** raw → **0.055** orthogonalized (the redundancy removed). VIF>5 = redundant. Most-correlated pairs:
- low_vol ↔ low_beta: |corr| 0.74
- quality ↔ accruals: |corr| 0.71

> Deep ~2011-2026 re-test on a SURVIVORSHIP-BIASED price panel: delisted names are absent (yahoo serves only currently-listed), so this is an OPTIMISTIC bound — a clean test needs delisting-recovered prices. FINRA short-interest is omitted (no point-in-time history). Fundamentals stay point-in-time from the EDGAR panel. Compare to the shallow 2023-2025 read: factors that survived on ~2.5y (notably SUE) weaken on deep history. Point-in-time (EDGAR panel + prices truncated to asof); IC = quarterly cross-sectional rank corr of factor z vs forward return; t_hac = Newey-West; q_fdr = Benjamini-Hochberg across the factor panel. Survivors judged vs ~0.