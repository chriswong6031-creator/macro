# Cross-Asset Confirmation — Phase-0 honesty gate

*Does cross-asset NON-CONFIRMATION (dispersion/dissent across the 7 signed RORO legs) predict forward EQUITY DRAWDOWN — incrementally, beyond the RORO level and VIX? Legs: vix, hy_oas, skew, vix_term, nfci, copper_gold, dxy. n~5133, 1971-01-04→2026-06-12. PIT-causal signal; HAC(lag=H) t-stats; the forward windows overlap.*

### Verdict: DISPLAY-ONLY — does not show INCREMENTAL drawdown-prediction skill beyond the RORO level / VIX; keep it as a legibility read, never scored

## 1. Decisive test — PARTIAL IC vs forward-63d max-loss
*(controlling for RORO level, |RORO|, VIX z. If the partial collapses toward zero, the feature is just a stress proxy.)*

| feature | univariate IC | PARTIAL IC (given roro,|roro|,vix) |
|---|---|---|
| disp | -0.086 (t=-2.006, p=0.0448) | **-0.036 (t=-0.858, p=0.3908)** |
| rng | -0.103 (t=-2.343, p=0.0191) | **-0.062 (t=-1.443, p=0.1491)** |
| frac_opp | -0.036 (t=-0.96, p=0.3368) | **-0.030 (t=-1.057, p=0.2904)** |
| worst | -0.154 (t=-3.176, p=0.0015) | **-0.033 (t=-0.797, p=0.4253)** |

_Baselines' own univariate skill on the same target (the bar):_ roro +0.178 (t=3.336, p=0.0008) · absroro -0.013 (t=-0.288, p=0.773) · vix_z -0.086 (t=-1.778, p=0.0754)

## 2. Full IC screen + Benjamini-Hochberg FDR (α=0.10)

6/24 feature×outcome tests survive FDR.

| feature\|outcome | IC | t (HAC) | p | q (BH) | reject |
|---|---|---|---|---|---|
| disp|maxloss_21 | -0.0657 | -2.081 | 0.0375 | 0.1191 | — |
| disp|ret_21 | -0.0285 | -0.823 | 0.4105 | 0.4691 | — |
| disp|maxloss_63 | -0.0856 | -2.006 | 0.0448 | 0.1195 | — |
| disp|ret_63 | -0.0753 | -1.472 | 0.1411 | 0.2117 | — |
| disp|maxloss_126 | -0.09 | -1.713 | 0.0866 | 0.1734 | — |
| disp|ret_126 | -0.0869 | -1.336 | 0.1815 | 0.2562 | — |
| rng|maxloss_21 | -0.0744 | -2.364 | 0.0181 | 0.088 | ✅ |
| rng|ret_21 | -0.0269 | -0.783 | 0.4336 | 0.473 | — |
| rng|maxloss_63 | -0.1029 | -2.343 | 0.0191 | 0.088 | ✅ |
| rng|ret_63 | -0.0785 | -1.543 | 0.1228 | 0.2013 | — |
| rng|maxloss_126 | -0.1112 | -2.057 | 0.0397 | 0.1191 | — |
| rng|ret_126 | -0.1011 | -1.595 | 0.1107 | 0.2013 | — |
| frac_opp|maxloss_21 | -0.0075 | -0.262 | 0.7931 | 0.8276 | — |
| frac_opp|ret_21 | -0.0497 | -1.713 | 0.0867 | 0.1734 | — |
| frac_opp|maxloss_63 | -0.0365 | -0.96 | 0.3368 | 0.4254 | — |
| frac_opp|ret_63 | -0.0676 | -1.825 | 0.0681 | 0.1634 | — |
| frac_opp|maxloss_126 | -0.067 | -1.531 | 0.1258 | 0.2013 | — |
| frac_opp|ret_126 | -0.0976 | -2.291 | 0.022 | 0.088 | ✅ |
| worst|maxloss_21 | -0.128 | -3.875 | 0.0001 | 0.0024 | ✅ |
| worst|ret_21 | -0.0053 | -0.149 | 0.8815 | 0.8815 | — |
| worst|maxloss_63 | -0.1541 | -3.176 | 0.0015 | 0.018 | ✅ |
| worst|ret_63 | -0.0489 | -0.905 | 0.3655 | 0.4386 | — |
| worst|maxloss_126 | -0.1771 | -3.035 | 0.0024 | 0.0192 | ✅ |
| worst|ret_126 | -0.0887 | -1.292 | 0.1965 | 0.262 | — |

## 3. Split-half sign stability (disp → maxloss_63)

- 1st half IC: -0.083 (t=-1.303, p=0.1925)
- 2nd half IC: -0.078 (t=-1.369, p=0.1709)
- same sign: YES

## 4. Tradable horse-race — de-risk overlay (cash when trigger z>1), 2bps

| trigger | Sharpe | B&H Sharpe | MaxDD% | B&H MaxDD% | days in cash |
|---|---|---|---|---|---|
| **dispersion** | 0.4 | 0.49 | -57.2 | -55.2 | 17.4% |
| VIX | 0.44 | 0.49 | -56.5 | -55.2 | 46.3% |
| \|RORO\| | 0.52 | 0.49 | -49.3 | -55.2 | 17.0% |

- dispersion-derisk **beats VIX-derisk** (lower MaxDD & ≥ Sharpe): NO
- Deflated Sharpe (dispersion overlay): 0.8589 at n_trials=24 → FAILS multiple-testing haircut (DSR<0.90)

## Honesty notes

- The signal is PIT-causal (rolling-z legs); association ICs are full-sample rank correlations — standard for screening, not a tradable claim.
- The de-risk overlay IS causal (trigger shifted 1d) and after 2bps.
- Dispersion co-moves with stress, so a univariate hit is EXPECTED and not evidence of a new edge — only the PARTIAL IC and the VIX horse-race are.

*Run: `python -m scripts.cross_asset_confirmation_phase0`*