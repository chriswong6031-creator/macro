# Commodity term-structure (roll yield / basis) — Phase-0 verdict

**VERDICT: DISPLAY-ONLY (no robust edge)**

Storage theory / Keynesian normal backwardation: positive roll yield (backwardation) should positively predict forward returns. Tested deep on WTI (EIA spot + futures 1-4, keyless, 1985-2024); metals are the shallow Yahoo collector (~18mo, underpowered).

Conservative: strategy P&L = SPOT move only; the mechanical roll carry is excluded and only reported as context.

## Oil (WTI) — the real test

- 63d IC overlap=-0.1599 (t_HAC=-4.585, p=0.0), halves -0.1064/-0.2363 sign-consistent=True
- net Sharpe=-0.21 vs B&H 0.296; DSR=0.0015; perm-null skill p=0.768

### Predictive IC (basis_1m → forward spot return)

| Horizon | IC (overlap) | t_HAC | p | IC (indep) | half-1 | half-2 | sign-consistent |
|--:|--:|--:|--:|--:|--:|--:|:--:|
| 21d | -0.0831 | -3.749 | 0.0002 | -0.0895 (n=456) | -0.0622 | -0.1223 | ✓ |
| 63d | -0.1599 | -4.585 | 0.0 | -0.2035 (n=152) | -0.1064 | -0.2363 | ✓ |
| 126d | -0.214 | -4.486 | 0.0 | -0.2725 (n=76) | -0.1441 | -0.3144 | ✓ |

### Timing backtest (long/short spot vs expanding-median basis, net of 8bps)

- 38.3y, n=9584, long 40% of the time
- **net Sharpe -0.21** vs buy&hold 0.296; CAGR -16.84% vs 3.29%; MaxDD -99.9% vs -93.9%
- DSR {'dsr': 0.0015, 'sr_daily': -0.013235, 'sr_annual': -0.21, 'sr0_daily': 0.016907, 'sr0_annual': 0.27, 'n_trials': 12, 'T': 9584, 'skew': -1.054, 'kurt': 52.436}
- perm-null {'real_sharpe': -0.21, 'null_sharpe_p95': 0.156, 'skill_p': 0.768, 'B': 2000}
- bootstrap {'sharpe_ci': [-0.57, -0.25, 0.08], 'maxdd_ci_pct': [-100.0, -100.0, -96.9], 'sharpe_gt0_prob': 0.06, 'block': 63, 'B': 3000, 'n': 9584}

### Is it just price mean-reversion? (incremental value over momentum)

- corr(basis→fwd) -0.1563 vs corr(momentum→fwd) -0.059; basis–momentum corr 0.2508
- **partial corr(basis, fwd | momentum) = -0.1465** (vs momentum's own partial -0.0207) — basis is NON-redundant; it largely SUBSUMES price momentum as the mean-reversion signal
- **TOTAL-return view (spot + realized carry): IC 0.1536** — crediting the carry you earn in backwardation roughly CANCELS the spot mean-reversion. This is why cross-sectional carry harvesting works but single-asset directional timing sees the spot reversal.

### Roll-carry context (the mechanical piece we EXCLUDED)

- backwardated 44% of days; mean 1m basis -0.00028
- forward-21d spot when backwardated: 0.379% vs contango 1.322% (n 4223/5261)

## Metals (Yahoo carry, SHALLOW ~18mo — underpowered, forward-accumulating)

- **gold** (2025-02-07..2026-06-12, n=351): 63d IC 0.0423 (half -0.2203/0.4831) — too short to conclude
- **silver** (2025-02-07..2026-06-12, n=351): 63d IC -0.3611 (half -0.7268/0.0157) — too short to conclude
- **copper** (2024-12-02..2026-06-12, n=400): 63d IC -0.111 (half 0.3865/-0.3635) — too short to conclude
