# S&P / Macro Vector — Phase 1 (de-risk core) calibration & GATE

*SPY 33.4yr, cost 3.0bps one-way, flat sleeve at DTB3. Baseline Sharpe to beat = 0.77 (max of 200dma 0.77 / 200dma+netliq 0.68).*

> HONEST CLAIM (adversarially verified, spvector-phase1-verify): this is a DRAWDOWN / SHARPE engine, NOT a CAGR-beater. The headline CAGR-beat is entirely the T-bill carry on the de-risked sleeve — the `CAGR(noC)` column (carry stripped) ~matches or slightly trails buy & hold. The robust, defensible edge is Sharpe ~0.9 vs 0.65 and MaxDD ~-34% vs -55%, at carry-financed-flat CAGR.

> ⚠️ LOOK-AHEAD: macro legs (NFCI/recession-prob/Sahm/EBP) are REVISED FRED series, now PIT-lagged per-leg (LEG_LAGS) by their real publication delay. The remaining fix is ALFRED point-in-time vintages (Phase 3). Edge confirmed robust to band/weight/window perturbation; drawdown_risk is the load-bearing leg.

## Baselines

| strategy | CAGR | Sharpe | MaxDD | turn/yr |
|---|--:|--:|--:|--:|
| buy & hold | 10.8 | 0.65 | -55.2 | 0.03 |
| 200dma | 8.81 | 0.77 | -23.4 | 6.44 |
| 200dma+netliq | 11.16 | 0.68 | -50.8 | 3.33 |

## Candidates

| candidate | CAGR | CAGR(noC) | Sharpe | MaxDD | %inMkt | turn | whip% | DSR |
|---|--:|--:|--:|--:|--:|--:|--:|--:|
| RISK-glide (cd5) | 11.15 | 10.56 | 0.91 | -34.1 | 98.7 | 1.4 | 40.1 | 0.9998 |
| RISK-glide (cd3) | 10.89 | 10.31 | 0.89 | -34.6 | 98.7 | 1.74 | 49.7 | 0.9997 |
| RISK-glide (cd10) | 10.56 | 9.99 | 0.85 | -33.2 | 98.8 | 0.83 | 18.5 | 0.9993 |
| RISK-glide binary | 10.76 | 10.52 | 0.73 | -53.7 | 89.8 | 1.53 | 31.4 | 0.9937 |
| RISK+voltarget (cd5) | 9.17 | 8.29 | 0.97 | -24.9 | 98.7 | 3.35 | 95.6 | 0.9999 |

## Release-lag sensitivity (PIT honesty — extra trading-day lag on the macro score)

| extra lag | CAGR | Sharpe | MaxDD |
|---|--:|--:|--:|
| 0d | 11.15 | 0.91 | -34.1 |
| 5d | 10.55 | 0.86 | -33.2 |
| 10d | 10.3 | 0.83 | -35.3 |
| 21d | 10.78 | 0.87 | -32.7 |
| 42d | 10.04 | 0.78 | -33.7 |

_The drawdown reduction is stable across all lags; the CAGR edge shrinks to match-or-slightly-lag B&H at realistic lags (the honest reframe). Default score lag = 5d._

## GATE — primary candidate `RISK-glide (cd5)`

- split-half Sharpe: pre 0.86 (B&H 0.47), post 0.97 (B&H 0.86)
- leave-one-crisis-out (Sharpe edge vs B&H): dotcom 2000-02 +0.28, GFC 2008 +0.14, COVID 2020 +0.3, bear 2022 +0.28
- drawdown-reduction bootstrap (pp, B&H−strat): CI [6.7, 14.9, 32.3] P(>0)=1.0
- DSR 0.9998 at n_trials=12, whipsaw 40.1%

- PASS (a) cut MaxDD vs B&H
- PASS (b) beat baseline Sharpe
- PASS (c) dd-reduction CI excludes 0
- PASS (d) survive leave-one-crisis-out
- PASS (e) turnover < 3/yr (tax-tolerable)
- PASS (f) both split-halves beat B&H
- PASS (g) DSR > 0.90

### Verdict: PASS — advance to Phase 2
