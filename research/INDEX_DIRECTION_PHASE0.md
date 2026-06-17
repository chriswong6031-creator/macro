# Index Direction — Phase-0 results

Walk-forward OOS (expanding, sign-restricted, monthly, embargo=42td) vs the recursive historical mean. A leg/combination is GO only if OOS-R² > 0 AND Clark-West nested test significant (BH-adjusted p<0.10) AND positive in BOTH date-halves; the combination also needs DSR≥0.90 (n_trials=200), Brier skill>0, and must beat its best single leg. Benchmark = 'always predict the mean' (Goyal-Welch random walk).

## SPY — medium (42td), 279 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `vrp` | -0.00378 | 0.4411 | — | **NEUTRAL** |
| `tsmom` | -0.02665 | 0.5953 | — | **NEUTRAL** |
| `netliq` | -0.04003 | 0.9843 | — | **NEUTRAL** |
| `credit` | -0.01977 | 0.5274 | — | **NEUTRAL** |

**Combination:** OOS-R² -0.00678, Clark-West p 0.5459, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 8.1%/0.6/-48.2% vs buy&hold 10.8%/0.65/-55.2% · exposure 0.69 · DSR 0.7557.
**Calibration:** Brier skill -0.07 (base up-rate 0.717), Platt a 0.055, mean P(up) 0.662.
**Verdict:** display-only (combination did not clear the OOS bar).

## QQQ — medium (42td), 205 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `vrp` | -0.11372 | 0.9698 | — | **NEUTRAL** |
| `real_rate` | 0.02714 | 0.0034 | ✓ | **GO** |
| `tsmom` | -0.04363 | 0.7216 | — | **NEUTRAL** |
| `netliq` | 0.0693 | 0.0024 | — | **NEUTRAL** |

**Combination:** OOS-R² 0.02714, Clark-West p 0.0034, beats-best-leg True, both-halves True.
**Timing backtest** (long when forecast>0, costed): strat 10.7%/0.72/-42.1% vs buy&hold 10.9%/0.52/-83.0% · exposure 0.58 · DSR 0.8367.
**Calibration:** Brier skill -0.041 (base up-rate 0.712), Platt a 0.457, mean P(up) 0.644.
**Verdict:** SCORED — directional lean is live.

## IWM — medium (42td), 190 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `credit` | -0.03532 | 0.7153 | — | **NEUTRAL** |
| `credit_vel` | -0.00509 | 0.676 | — | **NEUTRAL** |
| `anfci` | -0.04098 | 0.6658 | — | **NEUTRAL** |
| `vrp` | -0.02416 | 0.8552 | — | **NEUTRAL** |

**Combination:** OOS-R² -0.01475, Clark-West p 0.7565, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 6.4%/0.46/-31.9% vs buy&hold 8.8%/0.47/-58.6% · exposure 0.61 · DSR 0.3391.
**Calibration:** Brier skill -0.082 (base up-rate 0.674), Platt a -0.331, mean P(up) 0.615.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLK — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `real_rate` | 0.07334 | 0.0 | ✓ | **GO** |
| `vrp` | -0.10957 | 0.898 | — | **NEUTRAL** |
| `tsmom` | -0.01447 | 0.4877 | — | **NEUTRAL** |

**Combination:** OOS-R² 0.07334, Clark-West p 0.0, beats-best-leg True, both-halves True.
**Timing backtest** (long when forecast>0, costed): strat 11.1%/0.72/-31.5% vs buy&hold 10.5%/0.52/-82.0% · exposure 0.57 · DSR 0.8344.
**Calibration:** Brier skill -0.104 (base up-rate 0.716), Platt a 0.142, mean P(up) 0.616.
**Verdict:** SCORED — directional lean is live.

## XLF — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `credit` | -0.03668 | 0.7193 | — | **NEUTRAL** |
| `credit_vel` | -0.00526 | 0.9221 | — | **NEUTRAL** |
| `tsmom` | -0.02564 | 0.8525 | — | **NEUTRAL** |
| `vrp` | -0.04475 | 0.7166 | — | **NEUTRAL** |

**Combination:** OOS-R² -0.02225, Clark-West p 0.7689, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 7.2%/0.53/-33.7% vs buy&hold 5.9%/0.35/-82.7% · exposure 0.59 · DSR 0.4895.
**Calibration:** Brier skill -0.03 (base up-rate 0.654), Platt a 0.567, mean P(up) 0.589.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLE — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `dollar` | -0.05561 | 0.8385 | — | **NEUTRAL** |
| `tsmom` | -0.0096 | 0.8598 | — | **NEUTRAL** |
| `vrp` | 0.00167 | 0.2666 | — | **NEUTRAL** |

**Combination:** OOS-R² -0.02872, Clark-West p 0.9166, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 3.6%/0.28/-75.2% vs buy&hold 8.6%/0.43/-71.3% · exposure 0.61 · DSR 0.0912.
**Calibration:** Brier skill -0.032 (base up-rate 0.587), Platt a 0.115, mean P(up) 0.588.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLU — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|

**Combination:** OOS-R² None, Clark-West p None, beats-best-leg False, both-halves None.
**Timing backtest** (long when forecast>0, costed): strat 6.6%/0.52/-36.1% vs buy&hold 7.7%/0.48/-52.3% · exposure 0.64 · DSR 0.4885.
**Calibration:** Brier skill None (base up-rate None), Platt a None, mean P(up) 0.654.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLB — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `dollar` | -0.14807 | 0.9232 | — | **NEUTRAL** |
| `oil_mom` | -0.00583 | 0.7203 | — | **NEUTRAL** |

**Combination:** OOS-R² -0.07339, Clark-West p 0.9246, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 4.2%/0.34/-37.3% vs buy&hold 8.4%/0.46/-59.8% · exposure 0.57 · DSR 0.1613.
**Calibration:** Brier skill -0.094 (base up-rate 0.663), Platt a -0.255, mean P(up) 0.596.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLI — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `tsmom` | -0.02335 | 0.8016 | — | **NEUTRAL** |
| `oil_mom` | -0.01264 | 0.8599 | — | **NEUTRAL** |
| `credit` | -0.04324 | 0.778 | — | **NEUTRAL** |

**Combination:** OOS-R² -0.02191, Clark-West p 0.857, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 8.3%/0.6/-42.3% vs buy&hold 9.6%/0.54/-62.3% · exposure 0.61 · DSR 0.6326.
**Calibration:** Brier skill -0.088 (base up-rate 0.697), Platt a -0.149, mean P(up) 0.623.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLY — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `credit` | -0.03318 | 0.7785 | — | **NEUTRAL** |
| `real_rate` | 0.0006 | 0.1545 | — | **NEUTRAL** |
| `vrp` | -0.01366 | 0.4327 | — | **NEUTRAL** |

**Combination:** OOS-R² 0.00073, Clark-West p 0.3253, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 8.0%/0.57/-36.5% vs buy&hold 9.7%/0.52/-59.0% · exposure 0.61 · DSR 0.573.
**Calibration:** Brier skill -0.078 (base up-rate 0.697), Platt a -0.045, mean P(up) 0.628.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLP — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|
| `real_rate` | 0.00595 | 0.1017 | — | **NEUTRAL** |
| `tsmom` | -0.01523 | 0.9254 | — | **NEUTRAL** |

**Combination:** OOS-R² 0.00107, Clark-West p 0.1978, beats-best-leg True, both-halves False.
**Timing backtest** (long when forecast>0, costed): strat 6.3%/0.61/-24.5% vs buy&hold 6.8%/0.51/-35.9% · exposure 0.63 · DSR 0.65.
**Calibration:** Brier skill -0.059 (base up-rate 0.683), Platt a -0.059, mean P(up) 0.641.
**Verdict:** display-only (combination did not clear the OOS bar).

## XLV — medium (42td), 208 OOS rebalances

| leg | OOS-R² | Clark-West p | both halves | gate |
|---|---|---|---|---|

**Combination:** OOS-R² None, Clark-West p None, beats-best-leg False, both-halves None.
**Timing backtest** (long when forecast>0, costed): strat -0.6%/-0.33/-20.0% vs buy&hold 8.4%/0.54/-39.2% · exposure 0.0 · DSR 0.0.
**Calibration:** Brier skill None (base up-rate None), Platt a None, mean P(up) 0.501.
**Verdict:** display-only (combination did not clear the OOS bar).

_Generated by scripts/index_direction_phase0.py. Short horizon stays a coin-flip; long horizon pending a valuation (Shiller) collector. Re-run after data updates._
