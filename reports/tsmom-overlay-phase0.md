# Cross-asset TSMOM as a 60/40 diversifying overlay — Phase-0 verdict

**VERDICT: CONFIRMER (validated diversifying overlay).** Standalone diversified trend
stays DISPLAY (it ≈ buy&hold, the existing `cross-asset-phase0.md` finding); but blended
as a ~30% overlay on a 60/40 book it is a robust, multiple-testing-survived **drawdown
reducer** — the same drawdown-shaped payoff the S&P/Macro Vector is scored on. Not yet
wired into a live allocation, so it ships as a confirmer; the promotion path to SCORED is
a `masterminds.html` GTAA sleeve.

Harness: `scripts/tsmom_phase0.py` (READ-ONLY). 12-1 (12-month, skip-1) time-series
momentum, vol-targeted 10%/leg (3x cap), **monthly** rebalance, **2bps** one-way cost,
long/short, equal-risk aggregate. No look-ahead: signal/vol use data through t,
`backtest_core` acts next bar. Analysis 2003-01-01 → 2026 (all four asset classes live;
spans the 4 independent SPY bears).

Universe (4 classes): SPY (equity) · TLT (bond) · GC=F/CL=F/HG=F (commodity) · DX-Y.NYB (FX).

## Standalone sleeve — weak (confirms the existing display verdict)

| Lookback | CAGR | Sharpe | MaxDD |
|---|--:|--:|--:|
| TSMOM 12-1m | +2.57% | +0.50 | −13.4% |
| SPY buy&hold | +11.33% | +0.67 | −55.2% |
| 60/40 (SPY/TLT) | +9.13% | +0.85 | −29.9% |

Standalone Sharpe 0.50 < 60/40's 0.85 → **not** a standalone strategy. Split-half Sharpe
+0.44 / +0.54 (same-sign). DSR 0.9167 standalone (marginal).

## As a 60/40 overlay — the win

| Book | CAGR | Sharpe | MaxDD |
|---|--:|--:|--:|
| 60/40 alone | +9.13% | 0.85 | −29.9% |
| 60/40 + 10% TSMOM | +8.52% | 0.87 | −26.9% |
| 60/40 + 15% TSMOM | +8.21% | 0.88 | −25.3% |
| 60/40 + 20% TSMOM | +7.90% | 0.89 | −23.8% |
| **60/40 + 30% TSMOM** | +7.27% | **0.91** | **−20.8%** |

- **DSR = 0.9952** (n_trials=16 = lookback×weight grid) → SURVIVES multiple testing.
- Sharpe rises monotonically across **every** blend weight (not a single lucky point).
- Sharpe 95% CI [0.51, 0.91, 1.34].

## Robustness (the harden battery)

- **Purged 5-fold CV (embargo 63d):** all five folds positive — Sharpe +0.82 / +0.16 /
  +0.89 / +0.68 / +0.18. No fold flips negative.
- **Leave-one-crisis-out:** the 60/40+30% improvement holds dropping *each* crisis —
  ΔSharpe +0.04…+0.07, ΔMaxDD +8.7…+9.1pp for all of {2008, 2018Q4, 2020, 2022}. The
  benefit is broad-based, not one-episode-driven — the direct answer to the honest-N≈4
  constraint that sinks most de-risk signals here.
- **Crisis convexity (futures sleeve, cumulative through window):**

  | window | TSMOM | 60/40 | SPY |
  |---|--:|--:|--:|
  | 2008 GFC | −0.6% | −17.0% | −36.9% |
  | 2018Q4 | −6.7% | −6.5% | −13.5% |
  | 2020 COVID | +3.5% | −8.4% | −23.0% |
  | 2022 bear | +4.4% | −24.0% | −17.7% |

## Executable-today variant (ETF-only, no commodities/FX, no roll caveat)

SPY/TLT/IEF/LQD/HYG sleeve (equity + duration + credit), the liquid ETFs on disk:

- Standalone Sharpe 0.42, MaxDD −19.4%.
- **60/40 + 30% ETF-TSMOM: Sharpe 0.85→0.87, MaxDD −29.9%→−19.8%** (−10pp).
- Crisis convexity: 2008 +3.6%, 2022 +6.4% (still pays the big two); 2018Q4 −7.9%,
  2020 −6.7% (weaker in the fast crashes — no commodity/gold leg to rally).

**This ETF-only result is the honest headline for scoring** (executable with on-hand
instruments, no front-month-futures roll assumption).

## Caveats / honest framing

- **CAGR give-up ~2pp** (9.1%→7.3%) — the premium paid for the protection, banked when
  the cycle breaks. Frame on Sharpe + drawdown, never CAGR (the SP-Vector posture).
- The fuller futures sleeve's commodity/FX legs use **front-month closes (roll not
  modeled)** → productionize with tradeable proxies (DBC / UUP / GLD) before citing the
  futures numbers; the ETF-only numbers need no such caveat.
- Effective-N ≈ 4 independent crises remains the binding constraint; the leave-one-
  crisis-out test is the strongest available mitigation (the edge is not single-episode).
- Sharpe gain is modest (+0.02 ETF-only); the real win is the ~10pp MaxDD cut.

## Recommendation

Ship as a **confirmer** on `signal_lab.html` now (validated drawdown overlay). Promote to
**scored** by wiring the trend sleeve into the `masterminds.html` GTAA models (a vol-target
+ trend overlay sleeve), and by collecting DBC/UUP/GLD so the fuller-diversification version
is executable.
