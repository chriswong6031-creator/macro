# Stationarized HY-OAS 252d-z de-risk timer — Phase-0

Data: 7406 bars, 1996-12-31..2026-06-11 (29.4y of HY-OAS).

## Headline
- forward IC (252d-z -> fwd63 maxDD): **-0.301** (p 0.0000, NW-t -3.291, FDR-survives True)
- split-half IC: candidate **-0.346 / -0.235** (stable=True) vs LEVEL pct-rank -0.616 / -0.181 (stable=True)
- timed allocation: Sharpe 0.65 vs B&H 0.50, MaxDD -50.8% vs -56.8%, CAGR 7.45% vs 8.13%, **DSR 0.978**
- drawdown-reduction CI (overlay-B&H ΔMaxDD): [-0.58, 15.54, 36.53] pp, excludes 0 = False
- leave-one-crisis-out de-risks on all 4: False; de-risks both halves: True
- beats incumbent LEVEL pct-rank: False; beats VIX>median: False

## Overlay scorecard

| overlay | CAGR% | Sharpe | MaxDD% | TiM% |
|---|---|---|---|---|
| buy&hold | 8.13 | 0.50 | -56.8 | 100.0 |
| z252 candidate | 7.45 | 0.65 | -50.8 | 90.1 |
| LEVEL pct-rank (incumbent) | 9.08 | 0.77 | -22.5 | 90.8 |
| VIX>median (redundancy) | 4.89 | 0.48 | -50.4 | 89.4 |

## Verdict

**DISPLAY — reformulation is stable but no incremental de-risk edge**
