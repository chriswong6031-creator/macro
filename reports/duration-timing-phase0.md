# Duration / Treasury Timing — Phase-0 calibration & GATE

*Long Treasuries (TR) 23.9yr (to 2026-06-15), cost 3.0bps one-way, de-risked sleeve at T-bills (DTB3). Split-half boundary 2014-07-07. Baseline Sharpe to beat = 0.33 (max of buy&hold 0.33 / 200dma 0.12).*

> HONEST FRAME: this is a DRAWDOWN / risk-adjusted-return engine, NOT a CAGR-beater — sitting in the cash leg through stress gives up some carry, so CAGR ~matches or trails buy & hold. The thesis is timing the LEFT TAIL that destroys the yield (the recession / credit / rate shock), not the yield.

> SAMPLE CAVEAT: the benchmark is the dividend/coupon-adjusted ETF close (Long Treasuries (TR)); the small number of INDEPENDENT bears in this window — not the day count — bounds confidence. The authoritative ICE BofA total-return index (deeper history) lands via CI (config.yml fred.series.credit) and enables a deeper-history re-run; until then treat a PASS as provisional.

## Baselines

| strategy | CAGR | Sharpe | MaxDD | turn/yr |
|---|--:|--:|--:|--:|
| buy & hold | 3.7 | 0.33 | -48.4 | 0.04 |
| 200dma | 0.76 | 0.12 | -40.3 | 10.89 |

## Candidates (PRIMARY = shipped `glide (cd5)`)

| candidate | CAGR | CAGR(noC) | Sharpe | MaxDD | %inMkt | turn | DSR |
|---|--:|--:|--:|--:|--:|--:|--:|
| glide (cd5) — shipped | 3.59 | 2.89 | 0.49 | -18.1 | 95.2 | 1.81 | 0.828 |
| glide (cd3) | 3.12 | 2.41 | 0.43 | -17.3 | 95.0 | 2.93 | 0.7423 |
| glide (cd10) | 3.27 | 2.57 | 0.44 | -20.9 | 95.7 | 1.03 | 0.7557 |
| glide binary | 3.95 | 3.4 | 0.46 | -21.5 | 54.4 | 2.97 | 0.7816 |

## GATE — primary `glide (cd5) — shipped`

- split-half Sharpe: pre 0.66 (B&H 0.56), post 0.3 (B&H 0.12)
- leave-one-crisis-out (Sharpe edge vs B&H): taper 2013 +0.14, hikes 2016-18 +0.16, rate shock 2020-23 +0.04
- drawdown-reduction bootstrap (pp, B&H−strat): CI [7.4, 18.0, 34.2] P(>0)=1.0
- DSR 0.828 at n_trials=8

- PASS (a) cut MaxDD vs B&H (>10pp shallower)
- PASS (b) beat baseline Sharpe
- PASS (c) dd-reduction CI excludes 0
- PASS (d) survive leave-one-crisis-out
- PASS (e) turnover < 4/yr (tax-tolerable)
- PASS (f) both split-halves beat B&H
- FAIL (g) DSR > 0.90

### Verdict: DISPLAY-ONLY — the drawdown-control edge is robust (6/7 gates), but it does not clear every bar (see FAILs); keep it experimental / display-first, not a scored signal
