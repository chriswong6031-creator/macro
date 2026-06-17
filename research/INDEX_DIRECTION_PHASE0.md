# Index Direction — Phase-0 results (multi-horizon)

Walk-forward OOS (expanding, sign-restricted, monthly, embargo=horizon) vs the recursive historical mean, at MEDIUM (42td) and LONG (189td). A cell is SCORED only if the GO-leg composite has OOS-R²>0 AND Clark-West nested test BH-significant ACROSS ASSETS (q<0.05) AND positive in BOTH date-halves AND beats its best single leg AND the timing overlay is not Sharpe-worse than buy&hold AND P(up) is calibrated (recal Brier ≥ −0.01). DSR + bootstrap CI are reported as economic context. Benchmark = 'always predict the mean' (Goyal-Welch).

## Scored cells (validated directional lean)

| asset | horizon | GO legs | OOS-R² | Clark-West p | BH-q |
|---|---|---|---|---|---|
| **QQQ** | medium | real_rate | 0.02714 | 0.0034 | 0.0034 |
| **XLK** | medium | real_rate | 0.07334 | 0.0 | 0.0 |
| **XLP** | long | real_rate | 0.1545 | 0.0052 | 0.0052 |

## All cells

### IWM — long (189td), 184 OOS rebalances
- GO legs: —; composite OOS-R² -0.05058, Clark-West p 0.8111, BH-q None, both-halves False.
- timing: strat 7.0%/0.5/-31.9% vs hold 8.7%/0.47/-58.6% · DSR 0.4019 · recal-Brier 0.015 → **display-only**

### IWM — medium (42td), 191 OOS rebalances
- GO legs: —; composite OOS-R² -0.01468, Clark-West p 0.7554, BH-q None, both-halves False.
- timing: strat 6.4%/0.46/-31.9% vs hold 8.7%/0.47/-58.6% · DSR 0.3358 · recal-Brier 0.013 → **display-only**

### QQQ — long (189td), 198 OOS rebalances
- GO legs: —; composite OOS-R² -0.10929, Clark-West p 0.9885, BH-q None, both-halves False.
- timing: strat 11.7%/0.79/-35.1% vs hold 10.9%/0.52/-83.0% · DSR 0.9045 · recal-Brier 0.0 → **display-only**

### QQQ — medium (42td), 205 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.02714, Clark-West p 0.0034, BH-q 0.0034, both-halves True.
- timing: strat 10.6%/0.72/-42.1% vs hold 10.9%/0.52/-83.0% · DSR 0.8336 · recal-Brier 0.006 → **SCORED**

### SPY — long (189td), 272 OOS rebalances
- GO legs: —; composite OOS-R² -0.02348, Clark-West p 0.5625, BH-q None, both-halves False.
- timing: strat 8.1%/0.58/-55.2% vs hold 10.8%/0.65/-55.2% · DSR 0.7143 · recal-Brier 0.004 → **display-only**

### SPY — medium (42td), 279 OOS rebalances
- GO legs: —; composite OOS-R² -0.00678, Clark-West p 0.5459, BH-q None, both-halves False.
- timing: strat 8.0%/0.6/-48.2% vs hold 10.8%/0.65/-55.2% · DSR 0.751 · recal-Brier -0.001 → **display-only**

### XLB — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 2.3%/0.25/-39.0% vs hold 8.4%/0.46/-59.8% · DSR 0.0701 · recal-Brier 0.092 → **display-only**

### XLB — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.07339, Clark-West p 0.9246, BH-q None, both-halves False.
- timing: strat 4.1%/0.34/-37.3% vs hold 8.4%/0.46/-59.8% · DSR 0.1574 · recal-Brier 0.007 → **display-only**

### XLE — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.06041, Clark-West p 0.7317, BH-q None, both-halves False.
- timing: strat 4.2%/0.3/-71.3% vs hold 8.5%/0.43/-71.3% · DSR 0.1156 · recal-Brier 0.018 → **display-only**

### XLE — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.02872, Clark-West p 0.9166, BH-q None, both-halves False.
- timing: strat 3.6%/0.27/-75.2% vs hold 8.5%/0.43/-71.3% · DSR 0.0894 · recal-Brier -0.002 → **display-only**

### XLF — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.05807, Clark-West p 0.8587, BH-q None, both-halves False.
- timing: strat 6.8%/0.48/-42.9% vs hold 5.9%/0.34/-82.7% · DSR 0.3875 · recal-Brier 0.002 → **display-only**

### XLF — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.02225, Clark-West p 0.7689, BH-q None, both-halves False.
- timing: strat 7.2%/0.52/-33.7% vs hold 5.9%/0.34/-82.7% · DSR 0.4868 · recal-Brier -0.002 → **display-only**

### XLI — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.05144, Clark-West p 0.6705, BH-q None, both-halves False.
- timing: strat 8.6%/0.62/-42.3% vs hold 9.6%/0.54/-62.3% · DSR 0.6709 · recal-Brier 0.001 → **display-only**

### XLI — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.02191, Clark-West p 0.857, BH-q None, both-halves False.
- timing: strat 8.3%/0.6/-42.3% vs hold 9.6%/0.54/-62.3% · DSR 0.6319 · recal-Brier 0.004 → **display-only**

### XLK — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.05304, Clark-West p 0.8308, BH-q None, both-halves False.
- timing: strat 12.2%/0.79/-33.6% vs hold 10.5%/0.52/-82.0% · DSR 0.9145 · recal-Brier 0.004 → **display-only**

### XLK — medium (42td), 208 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.07334, Clark-West p 0.0, BH-q 0.0, both-halves True.
- timing: strat 11.1%/0.72/-31.5% vs hold 10.5%/0.52/-82.0% · DSR 0.8334 · recal-Brier -0.001 → **SCORED**

### XLP — long (189td), 201 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.1545, Clark-West p 0.0052, BH-q 0.0052, both-halves True.
- timing: strat 5.9%/0.6/-24.5% vs hold 6.7%/0.5/-35.9% · DSR 0.6262 · recal-Brier 0.011 → **SCORED**

### XLP — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² 0.00107, Clark-West p 0.1978, BH-q None, both-halves False.
- timing: strat 6.2%/0.6/-24.5% vs hold 6.7%/0.5/-35.9% · DSR 0.635 · recal-Brier 0.001 → **display-only**

### XLU — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 0.0%/nan/0.0% vs hold 7.7%/0.48/-52.3% · DSR None · recal-Brier None → **display-only**

### XLU — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 6.5%/0.52/-36.1% vs hold 7.7%/0.48/-52.3% · DSR 0.4812 · recal-Brier None → **display-only**

### XLV — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² 0.02924, Clark-West p 0.1357, BH-q None, both-halves False.
- timing: strat 6.0%/0.57/-28.4% vs hold 8.3%/0.54/-39.2% · DSR 0.5709 · recal-Brier 0.052 → **display-only**

### XLV — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat -0.6%/-0.33/-20.0% vs hold 8.3%/0.54/-39.2% · DSR 0.0 · recal-Brier None → **display-only**

### XLY — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.00413, Clark-West p 0.4512, BH-q None, both-halves False.
- timing: strat 10.3%/0.69/-39.7% vs hold 9.6%/0.52/-59.0% · DSR 0.7845 · recal-Brier -0.005 → **display-only**

### XLY — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² 0.00073, Clark-West p 0.3253, BH-q None, both-halves False.
- timing: strat 7.9%/0.56/-36.5% vs hold 9.6%/0.52/-59.0% · DSR 0.5608 · recal-Brier 0.001 → **display-only**

_Generated by scripts/index_direction_phase0.py. Short horizon stays a coin-flip. Re-run after data updates._
