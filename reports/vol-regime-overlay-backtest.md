# Vol-regime sizing-overlay backtest

_generated 2026-06-21 · subtract-only gross overlay (engine/vol_regime), judged on drawdown/tail not CAGR · L0 unscaled / L1 +vol-target / L2 +regime-caution (LIVE) / L3 +scored (gate-open)_


## Book: SPY (1993-01-29..2026-06-18, 8404 days)

| rung | ann% | vol% | Sharpe | Sortino | Calmar | maxDD% | CVaR5% | avgGross | turnover |
|---|---|---|---|---|---|---|---|---|---|
| L0_unscaled | 10.83 | 18.58 | 0.65 | 0.83 | 0.2 | -55.2 | -2.79 | 1.0 | 0.0 |
| L1_voltarget | 7.86 | 10.76 | 0.76 | 1.02 | 0.24 | -32.8 | -1.58 | 0.702 | 187.4 |
| L2_regime_live | 7.57 | 10.11 | 0.77 | 1.06 | 0.25 | -30.0 | -1.47 | 0.687 | 238.6 |
| L3_scored_open | 7.56 | 10.07 | 0.77 | 1.06 | 0.25 | -29.9 | -1.47 | 0.685 | 243.6 |

**Paired difference CIs** (resampled on the same blocks; 'helps' iff CI excludes 0):
- **L1_vs_L0**: dd-reduction [10.0, 17.1, 26.5] pp (favorable=True); Δsharpe [0.038, 0.108, 0.181]; Δcalmar [-0.006, 0.063, 0.158]
- **L2_vs_L1**: dd-reduction [-0.7, 1.9, 4.9] pp (favorable=False); Δsharpe [-0.02, 0.014, 0.051]; Δcalmar [-0.038, 0.013, 0.071]
- **L2_vs_L0**: dd-reduction [10.3, 18.9, 30.5] pp (favorable=True); Δsharpe [0.03, 0.122, 0.216]; Δcalmar [-0.018, 0.075, 0.199]
- **L3_vs_L2**: dd-reduction [-0.2, 0.1, 0.6] pp (favorable=False); Δsharpe [-0.004, 0.002, 0.008]; Δcalmar [-0.006, 0.001, 0.011]

- beats 200d-brake: False · break-even cost: 20bps · split-half robust: True {'pre2013': 25.2, 'post2013': 17.8}
- leave-one-crisis-out dd-reduction(pp): {'gfc_2008': 19.6, 'covid_2020': 25.2, 'bear_2022': 25.2} (robust=True)
- DSR (ledger-deflated): 0.9943 (SURVIVES multiple-testing (DSR≥0.95))

**Verdict (SPY):** live overlay (L2) helps = **False** (dd-reduction lower-bound 10.3pp). Regime caution adds value beyond plain vol-targeting (L2−L1) = **False**. Scored leg marginal (L3−L2) = False.

## Book: baskets (2023-05-09..2026-06-18, 781 days)

| rung | ann% | vol% | Sharpe | Sortino | Calmar | maxDD% | CVaR5% | avgGross | turnover |
|---|---|---|---|---|---|---|---|---|---|
| L0_unscaled | 58.35 | 24.71 | 1.98 | 2.88 | 2.17 | -26.9 | -3.42 | 1.0 | 0.0 |
| L1_voltarget | 38.33 | 16.55 | 2.04 | 3.02 | 2.19 | -17.5 | -2.26 | 0.731 | 24.1 |
| L2_regime_live | 37.33 | 15.94 | 2.07 | 3.08 | 2.36 | -15.8 | -2.17 | 0.719 | 29.4 |
| L3_scored_open | 37.26 | 15.93 | 2.07 | 3.08 | 2.35 | -15.8 | -2.16 | 0.718 | 29.6 |

**Paired difference CIs** (resampled on the same blocks; 'helps' iff CI excludes 0):
- **L1_vs_L0**: dd-reduction [2.9, 6.7, 11.9] pp (favorable=True); Δsharpe [-0.175, 0.041, 0.274]; Δcalmar [-1.216, -0.103, 0.695]
- **L2_vs_L1**: dd-reduction [-0.5, 0.3, 2.1] pp (favorable=False); Δsharpe [-0.055, 0.018, 0.128]; Δcalmar [-0.275, -0.013, 0.697]
- **L2_vs_L0**: dd-reduction [2.8, 7.0, 13.8] pp (favorable=True); Δsharpe [-0.214, 0.059, 0.378]; Δcalmar [-1.397, -0.104, 1.252]
- **L3_vs_L2**: dd-reduction [-0.1, 0.0, 0.1] pp (favorable=False); Δsharpe [-0.007, -0.002, 0.004]; Δcalmar [-0.028, -0.004, 0.022]

- beats 200d-brake: True · break-even cost: 20bps · split-half robust: False {'post2013': 11.2}
- DSR (ledger-deflated): 0.9502 (SURVIVES multiple-testing (DSR≥0.95))

**Verdict (baskets):** live overlay (L2) helps = **False** (dd-reduction lower-bound 2.8pp). Regime caution adds value beyond plain vol-targeting (L2−L1) = **False**. Scored leg marginal (L3−L2) = False.

## Gate

- **live_overlay_helps = False** → keep the chip as honest-caution display or hold; do not claim improvement.
- regime caution beyond vol-targeting: False; scored leg (gate-open): False → keep gate closed.

_Honest framing: the overlay is subtract-only (gross ≤ 1.0) — it trades upside for smaller drawdowns; a flat/slightly-lower CAGR with materially lower maxDD is a PASS. The basket book is survivorship-caveated (relative sizing test, not OOS selection)._
