# Credit Carry — Phase-0 calibration & GATE

*High-yield credit (TR) 19.2yr (to 2026-06-15), cost 3.0bps one-way, de-risked sleeve at 5y Treasury (DGS5). Split-half boundary 2016-11-07. Baseline Sharpe to beat = 0.83 (max of buy&hold 0.5 / 200dma 0.83).*

> HONEST FRAME: this is a DRAWDOWN / risk-adjusted-return engine, NOT a CAGR-beater — sitting in the cash leg through stress gives up some carry, so CAGR ~matches or trails buy & hold. The thesis is timing the LEFT TAIL that destroys the yield (the recession / credit / rate shock), not the yield.

> SAMPLE CAVEAT: the benchmark is the dividend/coupon-adjusted ETF close (High-yield credit (TR)); the small number of INDEPENDENT bears in this window — not the day count — bounds confidence. The authoritative ICE BofA total-return index (deeper history) lands via CI (config.yml fred.series.credit) and enables a deeper-history re-run; until then treat a PASS as provisional.

## Baselines

| strategy | CAGR | Sharpe | MaxDD | turn/yr |
|---|--:|--:|--:|--:|
| buy & hold | 4.95 | 0.5 | -34.2 | 0.05 |
| 200dma | 4.61 | 0.83 | -9.2 | 6.93 |

## Candidates (PRIMARY = shipped `glide (cd5)`)

| candidate | CAGR | CAGR(noC) | Sharpe | MaxDD | %inMkt | turn | DSR |
|---|--:|--:|--:|--:|--:|--:|--:|
| glide (cd5) — shipped | 4.3 | 3.49 | 0.75 | -14.7 | 99.3 | 2.55 | 0.9633 |
| glide (cd3) | 4.48 | 3.67 | 0.79 | -12.4 | 99.0 | 3.9 | 0.9751 |
| glide (cd10) | 4.27 | 3.45 | 0.66 | -22.0 | 99.4 | 1.23 | 0.9214 |
| glide binary | 4.86 | 4.49 | 0.67 | -21.4 | 85.7 | 3.28 | 0.9262 |

## GATE — primary `glide (cd5) — shipped`

- split-half Sharpe: pre 0.73 (B&H 0.46), post 0.82 (B&H 0.6)
- leave-one-crisis-out (Sharpe edge vs B&H): GFC 2008 +0.11, euro 2011 +0.28, energy/EM 2015-16 +0.28, COVID 2020 +0.27, rate/credit 2022 +0.29
- drawdown-reduction bootstrap (pp, B&H−strat): CI [5.9, 15.5, 30.7] P(>0)=1.0
- DSR 0.9633 at n_trials=8

- PASS (a) cut MaxDD vs B&H (>10pp shallower)
- FAIL (b) beat baseline Sharpe
- PASS (c) dd-reduction CI excludes 0
- PASS (d) survive leave-one-crisis-out
- PASS (e) turnover < 4/yr (tax-tolerable)
- PASS (f) both split-halves beat B&H
- PASS (g) DSR > 0.90

### Verdict: DISPLAY-ONLY — the drawdown-control edge is robust (6/7 gates), but it does not clear every bar (see FAILs); keep it experimental / display-first, not a scored signal
