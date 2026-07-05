# Oracle Reversion-Capture Gate (PRE-REGISTRATION)

**Date frozen:** 2026-07-05 · **Status:** pre-registered BEFORE screening any
compound on the reversion metric. Thresholds FROZEN; changing them after seeing
results is p-hacking.

## Why this replaces the 63-day gate

The 63-day point-to-point excess gate is a FACTOR metric — it measures "hold a
quarter, beat SPY." It structurally SELECTS AGAINST the actual strategy: enter
at a basing low, ride the reversion, exit near the momentum top (2D StochRSI
roll-over), avg hold ~20-30 sessions. A signal that bounces +7% in 3 weeks then
mean-reverts scores ~0 at 63d — the ruler discards exactly what we trade
(demonstrated: A15 = +1.30%/63d endpoint but +7.2% MFE / +3.0% at 21d / 73% WR).

Two further corrections (operator, 2026-07-05):
- **Do NOT benchmark vs SPY.** SPY is ~50% mega-cap tech; "excess vs SPY" hides
  the defensive-rotation win (defensives holding a falling tape). Use ABSOLUTE
  return + regime split, not SPY-excess.
- **Drawdown avoidance > gains.** Rotation's value is escaping the −20%, not
  only catching the +10%. Safety (MFE/MAE asymmetry) is a first-class criterion.

## Metric (harness: `scripts/oracle_reversion_screen.py`, W=25, E=21)

Per entry, ABSOLUTE (no SPY benchmark): MFE (25-session max up-excursion),
MAE (25-session max drawdown = safety), ret_exit (21-session time-exit return;
proxy for the 2D-StochRSI momentum-top exit — v2 will use the exact oscillator
exit). Regime at entry: risk_off if `spy_above_200d==0 OR vix_pctile>=0.70`.

Aggregates: n, mean ret_exit, **WR = frac(ret_exit>0)**, mean MFE, mean MAE,
**asym = mean_MFE/|mean_MAE|**, each also split risk_on / risk_off.

## Frozen PASS thresholds

A compound PASSES the reversion gate only if ALL hold:
1. **n >= 100.**
2. **WR >= 0.62** (win-rate primary — the strategy is high-WR; base washout is
   0.64, A15 is 0.74, so 0.62 demands the signal at least matches the raw base).
3. **Safety: asym (MFE/|MAE|) >= 1.5** — upside excursion at least 1.5x the
   drawdown sat through (A15=1.83 passes; bare washout=1.28 fails → the filter
   must add safety, not just return).
4. **ret_exit >= +1.0%** absolute AND ret_exit > 0 in BOTH risk_on and risk_off
   (not regime-fragile; a signal that only works in rebounds is a beta timer).
5. **OOS holdout** (split 2019-12-31, tier-s; for tier-m use the modern split
   2023-12-31 per the Tier-M prereg): holdout WR >= 0.58 AND holdout ret_exit
   same sign as dev AND holdout n >= 100.
6. **Timing placebo:** real mean ret_exit > 95th pctile of 500 random-timing
   draws (per-node, count-matched), one-sided p < 0.05.

PASS = 1^2^3^4^5^6. (Gauntlet-reversion harness to be built adds legs 5-6; the
screener supplies 1-4.)

## Standing notes

- ABSOLUTE returns include market beta by design (operator's call: the P&L of a
  long-only rotator is absolute; SPY-excess mis-frames it). Regime robustness
  (leg 4) + the placebo (leg 6) are the guards against "it's only beta."
- Short-horizon high-WR is the easiest thing to overfit and where costs bite; a
  PASS is display-only and a promotion CANDIDATE, not a validated edge. A
  transaction-cost haircut must be applied before any live claim.
- v2: replace the 21-session time-exit with the exact 2D-StochRSI-top exit once
  a 2-day-bar StochRSI is computed; re-freeze if thresholds change materially.
