# Cross-Asset TSMOM — Phase-0 honesty gate

*Leverage-free time-series momentum (avg sign of trailing 3/6/12m return, skip 1w) over 10 keyless cross-asset legs, equal-weight, 2007-01-01→, 8.0bps one-way. AQR's gross ~1.8 Sharpe is contested — this is the AFTER-COST number.*

## Headline — diversified equal-weight TSMOM vs equal-weight buy&hold

| | TSMOM | Buy&Hold |
|---|---|---|
| Sharpe (net) | **0.54** | 0.56 |
| CAGR % | 9.4 | 11.2 |
| MaxDD % | -40.8 | -68.3 |

- **Block-bootstrap Sharpe 95% CI:** [0.17, 0.54, 0.9] (P(Sharpe>0)=0.998)
- **MaxDD 95% CI:** [-66.1, -42.8, -27.6]%
- **AQR permutation null:** real Sharpe 0.54 vs null p95 0.42 → skill p = **0.008** (B=1500)
- **Deflated Sharpe:** 0.795 at n_trials=24 (SR0_annual 0.38)

### Verdict: DOES NOT CLEAR the gate — present as a CONTESTED-factor / regime read, not a strategy

## Per-asset after-cost Sharpe (TSMOM)

| asset | TSMOM Sharpe |
|---|---|
| crypto | 0.83 |
| equity_us | 0.31 |
| oil | 0.22 |
| gold | 0.18 |
| copper | 0.1 |
| credit_hy | 0.08 |
| equity_sm | -0.05 |
| bond_10y | -0.07 |
| silver | -0.13 |
| dollar | -0.31 |

## Honesty notes

- Net of an 8bps one-way cost on |Δposition|; leverage-free (alloc∈[-1,1]); no vol-targeting leverage.
- The bond leg is a duration-return proxy (−7·Δyield); the dollar leg trends the DXY level.
- DSR n_trials=24 is a conservative upper bound on the horizon/skip/blend variants tried.
- This validates TREND only. Carry & intermarket ratios are current-state context, not backtested.
- Permutation null shuffles each leg's timing independently (circular blocks of 42d), preserving each marginal.

*Run: `python -m scripts.cross_asset_phase0`*