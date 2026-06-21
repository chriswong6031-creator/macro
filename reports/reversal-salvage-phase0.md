# Reversal salvage — does residual + turnover-conditioned reversal survive net of cost?

**Verdict: NO-GO.** CLOSE THE BOOK on reversal as selection alpha — it is a net-of-cost mirage.

- tradeable (liquid) residual reversal is net-NEGATIVE after 10bps (-1.34%/yr) — the mirage: gross edge is eaten by turnover cost
- liquid residual reversal IC not significant (HAC-t 0.351)

Span 1962-06-29..2026-04-30 · 767 monthly rebalances · formation 21d → forward 21d · ~72 names · leak-free, point-in-time.

| signal | mean IC | IC-IR | t_HAC | gross Sharpe | net@10 Sharpe | net@10 t_HAC | net@10 %/yr | net@10 DSR |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| reversal_raw | 0.018 | 0.097 | 2.497 | 0.454 | 0.312 | 2.41 | 4.22 | 0.7906 |
| reversal_resid | 0.0193 | 0.103 | 2.755 | 0.453 | 0.312 | 2.349 | 4.19 | 0.7882 |
| reversal_resid_liquid | 0.0027 | 0.013 | 0.351 | 0.032 | -0.069 | -0.464 | -1.34 | 0.0244 |

`reversal_resid_liquid` = beta-residual reversal in the TOP dollar-volume tercile (the only tradeable slice) — the form the literature claims survives. The gross→net columns show where turnover cost lands.

> No non-survivor price panel locally → run on the SURVIVORSHIP-BIASED large-cap panel (~114 names), which is GENEROUS to reversal (omits delisted blow-ups). A net-of-cost failure here is therefore CONCLUSIVE; a pass would need a non-survivor confirm before any tilt. Costs: 10/20 bps per side on realized turnover.