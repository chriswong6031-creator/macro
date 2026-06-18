# Index Direction — Phase-0 results (multi-horizon)

Walk-forward OOS (expanding, sign-restricted, monthly, embargo=horizon) vs the recursive historical mean, at MEDIUM (42td) and LONG (189td). A cell is SCORED only if the GO-leg composite has OOS-R²>0 AND Clark-West nested test BH-significant ACROSS ASSETS (q<0.05) AND positive in BOTH date-halves AND beats its best single leg AND the timing overlay is not Sharpe-worse than buy&hold AND P(up) is calibrated (recal Brier ≥ −0.01). DSR + bootstrap CI are reported as economic context. Benchmark = 'always predict the mean' (Goyal-Welch).

## Scored cells (validated directional lean)

| asset | horizon | GO legs | OOS-R² | Clark-West p | BH-q |
|---|---|---|---|---|---|
| **QQQ** | medium | real_rate | 0.02714 | 0.0034 | 0.0034 |
| **SMH** | long | real_rate | 0.09305 | 0.0006 | 0.0018 |
| **XLI** | long | copper_gold | 0.05701 | 0.0069 | 0.0069 |
| **XLK** | medium | real_rate | 0.07334 | 0.0 | 0.0 |
| **XLP** | long | real_rate | 0.1545 | 0.0052 | 0.0069 |

## All cells

### GDX — long (189td), 112 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 5.1%/0.41/-36.3% vs hold 5.0%/0.33/-80.6% · DSR 0.1038 · recal-Brier None → **display-only**

### GDX — medium (42td), 119 OOS rebalances
- GO legs: —; composite OOS-R² -0.01618, Clark-West p 0.9586, BH-q None, both-halves False.
- timing: strat 4.2%/0.29/-59.7% vs hold 5.0%/0.33/-80.6% · DSR 0.0386 · recal-Brier -0.008 → **display-only**

### GDXJ — long (189td), 70 OOS rebalances
- GO legs: —; composite OOS-R² -0.03375, Clark-West p 0.8077, BH-q None, both-halves False.
- timing: strat 1.7%/0.18/-51.4% vs hold 2.6%/0.29/-88.7% · DSR 0.0101 · recal-Brier 0.045 → **display-only**

### GDXJ — medium (42td), 77 OOS rebalances
- GO legs: —; composite OOS-R² -0.02472, Clark-West p 0.9116, BH-q None, both-halves False.
- timing: strat 0.8%/0.15/-56.9% vs hold 2.6%/0.29/-88.7% · DSR 0.0069 · recal-Brier -0.002 → **display-only**

### IBB — long (189td), 175 OOS rebalances
- GO legs: —; composite OOS-R² -0.01065, Clark-West p 0.5498, BH-q None, both-halves False.
- timing: strat 6.5%/0.43/-39.8% vs hold 6.8%/0.38/-62.8% · DSR 0.1841 · recal-Brier 0.018 → **display-only**

### IBB — medium (42td), 182 OOS rebalances
- GO legs: —; composite OOS-R² -0.01598, Clark-West p 0.6993, BH-q None, both-halves False.
- timing: strat 6.2%/0.42/-39.8% vs hold 6.8%/0.38/-62.8% · DSR 0.1673 · recal-Brier -0.005 → **display-only**

### IGV — long (189td), 170 OOS rebalances
- GO legs: —; composite OOS-R² -0.00482, Clark-West p 0.4556, BH-q None, both-halves False.
- timing: strat 8.4%/0.52/-45.9% vs hold 9.3%/0.47/-62.2% · DSR 0.3113 · recal-Brier -0.003 → **display-only**

### IGV — medium (42td), 177 OOS rebalances
- GO legs: —; composite OOS-R² 0.00722, Clark-West p 0.1416, BH-q None, both-halves False.
- timing: strat 7.8%/0.5/-36.7% vs hold 9.3%/0.47/-62.2% · DSR 0.2843 · recal-Brier 0.009 → **display-only**

### ITB — long (189td), 112 OOS rebalances
- GO legs: —; composite OOS-R² -0.00209, Clark-West p 0.3349, BH-q None, both-halves False.
- timing: strat 6.2%/0.39/-52.1% vs hold 4.0%/0.29/-86.5% · DSR 0.0962 · recal-Brier 0.024 → **display-only**

### ITB — medium (42td), 119 OOS rebalances
- GO legs: —; composite OOS-R² 0.01254, Clark-West p 0.1995, BH-q None, both-halves False.
- timing: strat 6.4%/0.41/-52.1% vs hold 4.0%/0.29/-86.5% · DSR 0.1102 · recal-Brier -0.004 → **display-only**

### IWM — long (189td), 184 OOS rebalances
- GO legs: —; composite OOS-R² -0.05058, Clark-West p 0.8111, BH-q None, both-halves False.
- timing: strat 7.0%/0.5/-31.9% vs hold 8.7%/0.47/-58.6% · DSR 0.2921 · recal-Brier 0.015 → **display-only**

### IWM — medium (42td), 191 OOS rebalances
- GO legs: —; composite OOS-R² -0.01468, Clark-West p 0.7554, BH-q None, both-halves False.
- timing: strat 6.4%/0.46/-31.9% vs hold 8.7%/0.47/-58.6% · DSR 0.2349 · recal-Brier 0.013 → **display-only**

### KBE — long (189td), 118 OOS rebalances
- GO legs: —; composite OOS-R² -0.0751, Clark-West p 0.9946, BH-q None, both-halves False.
- timing: strat 3.3%/0.26/-53.1% vs hold 3.6%/0.28/-83.2% · DSR 0.0302 · recal-Brier 0.113 → **display-only**

### KBE — medium (42td), 125 OOS rebalances
- GO legs: —; composite OOS-R² -0.02784, Clark-West p 0.953, BH-q None, both-halves False.
- timing: strat 3.5%/0.28/-53.1% vs hold 3.6%/0.28/-83.2% · DSR 0.0346 · recal-Brier 0.005 → **display-only**

### KRE — long (189td), 111 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 3.3%/0.26/-55.0% vs hold 4.5%/0.3/-68.5% · DSR 0.0291 · recal-Brier 0.096 → **display-only**

### KRE — medium (42td), 118 OOS rebalances
- GO legs: —; composite OOS-R² -0.01515, Clark-West p 0.7921, BH-q None, both-halves False.
- timing: strat 5.8%/0.39/-52.7% vs hold 4.5%/0.3/-68.5% · DSR 0.0951 · recal-Brier -0.001 → **display-only**

### OIH — long (189td), 175 OOS rebalances
- GO legs: —; composite OOS-R² 0.0183, Clark-West p 0.2271, BH-q None, both-halves False.
- timing: strat -1.3%/0.03/-68.3% vs hold 0.0%/0.2/-94.4% · DSR 0.0017 · recal-Brier -0.005 → **display-only**

### OIH — medium (42td), 182 OOS rebalances
- GO legs: —; composite OOS-R² -0.01884, Clark-West p 0.8681, BH-q None, both-halves False.
- timing: strat -8.2%/-0.25/-94.6% vs hold 0.0%/0.2/-94.4% · DSR 0.0 · recal-Brier 0.001 → **display-only**

### QQQ — long (189td), 198 OOS rebalances
- GO legs: —; composite OOS-R² -0.10929, Clark-West p 0.9885, BH-q None, both-halves False.
- timing: strat 11.7%/0.79/-35.1% vs hold 10.9%/0.52/-83.0% · DSR 0.8435 · recal-Brier 0.0 → **display-only**

### QQQ — medium (42td), 205 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.02714, Clark-West p 0.0034, BH-q 0.0034, both-halves True.
- timing: strat 10.6%/0.72/-42.1% vs hold 10.9%/0.52/-83.0% · DSR 0.7485 · recal-Brier 0.006 → **SCORED**

### SMH — long (189td), 183 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.09305, Clark-West p 0.0006, BH-q 0.0018, both-halves True.
- timing: strat 16.7%/0.8/-45.3% vs hold 10.9%/0.47/-85.9% · DSR 0.8362 · recal-Brier 0.002 → **SCORED**

### SMH — medium (42td), 190 OOS rebalances
- GO legs: ['real_rate', 'tsmom']; composite OOS-R² 0.03985, Clark-West p 0.0018, BH-q 0.0027, both-halves True.
- timing: strat 13.5%/0.72/-44.1% vs hold 10.9%/0.47/-85.9% · DSR 0.7163 · recal-Brier 0.01 → **display-only**

### SOXX — long (189td), 170 OOS rebalances
- GO legs: —; composite OOS-R² 0.02439, Clark-West p 0.1153, BH-q None, both-halves False.
- timing: strat 9.2%/0.57/-45.8% vs hold 14.6%/0.58/-70.2% · DSR 0.4258 · recal-Brier -0.004 → **display-only**

### SOXX — medium (42td), 177 OOS rebalances
- GO legs: —; composite OOS-R² 0.01017, Clark-West p 0.0442, BH-q None, both-halves False.
- timing: strat 14.7%/0.71/-47.9% vs hold 14.6%/0.58/-70.2% · DSR 0.6807 · recal-Brier -0.005 → **display-only**

### SPY — long (189td), 272 OOS rebalances
- GO legs: —; composite OOS-R² -0.02348, Clark-West p 0.5625, BH-q None, both-halves False.
- timing: strat 8.1%/0.58/-55.2% vs hold 10.8%/0.65/-55.2% · DSR 0.6053 · recal-Brier 0.004 → **display-only**

### SPY — medium (42td), 279 OOS rebalances
- GO legs: —; composite OOS-R² -0.00678, Clark-West p 0.5459, BH-q None, both-halves False.
- timing: strat 8.0%/0.6/-48.2% vs hold 10.8%/0.65/-55.2% · DSR 0.6476 · recal-Brier -0.001 → **display-only**

### TAN — long (189td), 89 OOS rebalances
- GO legs: —; composite OOS-R² -0.00882, Clark-West p 0.9115, BH-q None, both-halves False.
- timing: strat 1.2%/0.18/-78.5% vs hold -6.3%/0.08/-95.3% · DSR 0.0103 · recal-Brier 0.298 → **display-only**

### TAN — medium (42td), 96 OOS rebalances
- GO legs: —; composite OOS-R² 0.0079, Clark-West p 0.2594, BH-q None, both-halves False.
- timing: strat 2.0%/0.2/-72.9% vs hold -6.3%/0.08/-95.3% · DSR 0.0133 · recal-Brier 0.017 → **display-only**

### XBI — long (189td), 115 OOS rebalances
- GO legs: —; composite OOS-R² -0.06604, Clark-West p 0.9446, BH-q None, both-halves False.
- timing: strat 5.7%/0.36/-63.9% vs hold 11.4%/0.51/-63.9% · DSR 0.0715 · recal-Brier 0.017 → **display-only**

### XBI — medium (42td), 122 OOS rebalances
- GO legs: —; composite OOS-R² -0.08591, Clark-West p 0.9283, BH-q None, both-halves False.
- timing: strat 4.9%/0.33/-63.9% vs hold 11.4%/0.51/-63.9% · DSR 0.0558 · recal-Brier 0.063 → **display-only**

### XHB — long (189td), 115 OOS rebalances
- GO legs: —; composite OOS-R² 0.01045, Clark-West p 0.2349, BH-q None, both-halves False.
- timing: strat 7.3%/0.47/-49.6% vs hold 5.4%/0.32/-81.6% · DSR 0.1683 · recal-Brier 0.002 → **display-only**

### XHB — medium (42td), 122 OOS rebalances
- GO legs: —; composite OOS-R² 0.02143, Clark-West p 0.1504, BH-q None, both-halves False.
- timing: strat 6.7%/0.45/-49.6% vs hold 5.4%/0.32/-81.6% · DSR 0.1485 · recal-Brier 0.003 → **display-only**

### XLB — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.53799, Clark-West p 0.8718, BH-q None, both-halves False.
- timing: strat 3.7%/0.35/-37.3% vs hold 8.4%/0.46/-59.8% · DSR 0.1076 · recal-Brier 0.09 → **display-only**

### XLB — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.04974, Clark-West p 0.9174, BH-q None, both-halves False.
- timing: strat 5.0%/0.39/-37.3% vs hold 8.4%/0.46/-59.8% · DSR 0.1471 · recal-Brier 0.005 → **display-only**

### XLE — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.07882, Clark-West p 0.8039, BH-q None, both-halves False.
- timing: strat 4.3%/0.3/-71.3% vs hold 8.5%/0.43/-71.3% · DSR 0.0698 · recal-Brier 0.023 → **display-only**

### XLE — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.03676, Clark-West p 0.8966, BH-q None, both-halves False.
- timing: strat 2.2%/0.21/-76.6% vs hold 8.5%/0.43/-71.3% · DSR 0.0238 · recal-Brier -0.001 → **display-only**

### XLF — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.07367, Clark-West p 0.8776, BH-q None, both-halves False.
- timing: strat 6.7%/0.47/-42.9% vs hold 5.9%/0.34/-82.7% · DSR 0.2631 · recal-Brier 0.012 → **display-only**

### XLF — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.02533, Clark-West p 0.7937, BH-q None, both-halves False.
- timing: strat 7.3%/0.53/-33.7% vs hold 5.9%/0.34/-82.7% · DSR 0.3754 · recal-Brier -0.004 → **display-only**

### XLI — long (189td), 201 OOS rebalances
- GO legs: ['copper_gold']; composite OOS-R² 0.05701, Clark-West p 0.0069, BH-q 0.0069, both-halves True.
- timing: strat 9.1%/0.62/-42.3% vs hold 9.6%/0.54/-62.3% · DSR 0.5575 · recal-Brier 0.0 → **SCORED**

### XLI — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² -0.013, Clark-West p 0.703, BH-q None, both-halves False.
- timing: strat 7.7%/0.57/-42.3% vs hold 9.6%/0.54/-62.3% · DSR 0.4617 · recal-Brier 0.0 → **display-only**

### XLK — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.05304, Clark-West p 0.8308, BH-q None, both-halves False.
- timing: strat 12.2%/0.79/-33.6% vs hold 10.5%/0.52/-82.0% · DSR 0.8577 · recal-Brier 0.004 → **display-only**

### XLK — medium (42td), 208 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.07334, Clark-West p 0.0, BH-q 0.0, both-halves True.
- timing: strat 11.1%/0.72/-31.5% vs hold 10.5%/0.52/-82.0% · DSR 0.7482 · recal-Brier -0.001 → **SCORED**

### XLP — long (189td), 201 OOS rebalances
- GO legs: ['real_rate']; composite OOS-R² 0.1545, Clark-West p 0.0052, BH-q 0.0069, both-halves True.
- timing: strat 5.9%/0.6/-24.5% vs hold 6.7%/0.5/-35.9% · DSR 0.5092 · recal-Brier 0.011 → **SCORED**

### XLP — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² 0.00107, Clark-West p 0.1978, BH-q None, both-halves False.
- timing: strat 6.2%/0.6/-24.5% vs hold 6.7%/0.5/-35.9% · DSR 0.5185 · recal-Brier 0.001 → **display-only**

### XLU — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 0.0%/nan/0.0% vs hold 7.7%/0.48/-52.3% · DSR None · recal-Brier None → **display-only**

### XLU — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat 6.5%/0.52/-36.1% vs hold 7.7%/0.48/-52.3% · DSR 0.3647 · recal-Brier None → **display-only**

### XLV — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² 0.02924, Clark-West p 0.1357, BH-q None, both-halves False.
- timing: strat 6.0%/0.57/-28.4% vs hold 8.3%/0.54/-39.2% · DSR 0.4522 · recal-Brier 0.052 → **display-only**

### XLV — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² None, Clark-West p None, BH-q None, both-halves None.
- timing: strat -0.6%/-0.33/-20.0% vs hold 8.3%/0.54/-39.2% · DSR 0.0 · recal-Brier None → **display-only**

### XLY — long (189td), 201 OOS rebalances
- GO legs: —; composite OOS-R² -0.00413, Clark-West p 0.4512, BH-q None, both-halves False.
- timing: strat 10.3%/0.69/-39.7% vs hold 9.6%/0.52/-59.0% · DSR 0.6875 · recal-Brier -0.005 → **display-only**

### XLY — medium (42td), 208 OOS rebalances
- GO legs: —; composite OOS-R² 0.00073, Clark-West p 0.3253, BH-q None, both-halves False.
- timing: strat 7.9%/0.56/-36.5% vs hold 9.6%/0.52/-59.0% · DSR 0.442 · recal-Brier 0.001 → **display-only**

### XME — long (189td), 111 OOS rebalances
- GO legs: —; composite OOS-R² -0.02017, Clark-West p 0.6016, BH-q None, both-halves False.
- timing: strat 5.4%/0.35/-63.9% vs hold 6.3%/0.35/-85.9% · DSR 0.0667 · recal-Brier 0.01 → **display-only**

### XME — medium (42td), 118 OOS rebalances
- GO legs: —; composite OOS-R² -0.01857, Clark-West p 0.7553, BH-q None, both-halves False.
- timing: strat 8.8%/0.52/-46.0% vs hold 6.3%/0.35/-85.9% · DSR 0.2304 · recal-Brier -0.004 → **display-only**

### XOP — long (189td), 111 OOS rebalances
- GO legs: —; composite OOS-R² -0.00109, Clark-West p 0.4038, BH-q None, both-halves False.
- timing: strat -1.6%/0.03/-68.9% vs hold 2.0%/0.25/-90.3% · DSR 0.0017 · recal-Brier 0.007 → **display-only**

### XOP — medium (42td), 118 OOS rebalances
- GO legs: —; composite OOS-R² -0.01472, Clark-West p 0.906, BH-q None, both-halves False.
- timing: strat 1.2%/0.16/-64.9% vs hold 2.0%/0.25/-90.3% · DSR 0.0097 · recal-Brier -0.005 → **display-only**

### XRT — long (189td), 111 OOS rebalances
- GO legs: —; composite OOS-R² -0.02837, Clark-West p 0.843, BH-q None, both-halves False.
- timing: strat 4.6%/0.33/-47.0% vs hold 9.3%/0.47/-65.8% · DSR 0.0552 · recal-Brier 0.004 → **display-only**

### XRT — medium (42td), 118 OOS rebalances
- GO legs: —; composite OOS-R² -0.02546, Clark-West p 0.8347, BH-q None, both-halves False.
- timing: strat 3.3%/0.27/-47.0% vs hold 9.3%/0.47/-65.8% · DSR 0.0312 · recal-Brier 0.02 → **display-only**

_Generated by scripts/index_direction_phase0.py. Short horizon stays a coin-flip. Re-run after data updates._
