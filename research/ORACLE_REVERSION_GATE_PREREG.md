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

## Amendment 1 — Single-regime path (frozen 2026-07-05, BEFORE running any single-regime candidate)

**Motivation.** Leg 4's dual-regime requirement ("ret>0 in BOTH risk_on and risk_off") cannot be satisfied by a signal STRUCTURALLY confined to one regime — bear-tape signals gated on `spy_above_200d==0` (which IS risk_off by definition), or any signal explicitly gated to risk-off (`spy_above_200d==0 OR vix_pctile>=0.70`). Such a signal has ~0 entries in the opposite regime, so Leg 4 fails *by construction* — not because it's a beta timer, but because the test is category-inapplicable. This blocks the operator's CORE thesis (defensive/risk-off rotation to escape drawdowns). Confirmed on two mechanisms: the bear-tape family, and (once risk-off-gated) credit-relief, whose tier-M pooled WR fails only because risk_on WR ~0.50 drags it down.

**This amendment is STRICTER, not a loophole.** It replaces the inapplicable dual-regime leg with a within-operating-regime test AND replaces the all-history placebo with a REGIME-MATCHED placebo. The current all-history placebo lets a risk-off-only signal claim credit for risk-off *beta* (risk-off periods bounce harder); the regime-matched placebo removes that free pass — the signal must beat random RISK-OFF-timed entries. The single-regime path therefore demands MORE evidence of genuine timing edge, not less.

**Trigger (non-gameable).** A compound takes the single-regime path IFF the minority regime has **n < 30 entries** (structurally confined; cannot be evaluated as dual-regime). A signal with ≥30 entries in BOTH regimes takes the STANDARD dual-regime path unchanged — the single-regime path is NOT available to a signal that merely performs poorly in one regime with meaningful n (that genuinely fails "works in both").

**Amended legs (single-regime path only; all numeric thresholds otherwise UNCHANGED):**
- **Leg 4′:** ret_exit ≥ +1.0% overall AND ret_exit > 0 in the OPERATING regime AND **n_operating ≥ 100**. (The empty regime is exempt.)
- **Leg 6′ — regime-matched placebo:** the per-node placebo pool is restricted to dates where that node was in the OPERATING regime (risk_off ≡ `spy_above_200d==0 OR vix_pctile>=0.70`). Count-matched draws sample only that regime's realizable outcomes. PASS iff real mean ret_exit > 95th pctile of 500 draws (one-sided p<0.05) — the signal's timing must beat random within-regime timing.
- **Legs 1, 2, 3, 5 UNCHANGED** (n≥100, WR≥0.62, asym≥1.5; OOS holdout WR≥0.58 + sign-match + holdout-n≥100), computed on all entries (≈ operating-regime entries since minority<30).

**Standing.** A single-regime PASS means "beats random within-regime timing with drawdown-safe asymmetry" = genuine entry alpha within the operating regime, NOT regime beta. Display-only + transaction-cost haircut still required. Implementation (`scripts/oracle_reversion_screen.py`) to be built to THIS spec and Opus-reviewed for faithfulness; a known dual-regime signal (A15) must be verified UNCHANGED by the code as a positive control.

## Standing notes

- ABSOLUTE returns include market beta by design (operator's call: the P&L of a
  long-only rotator is absolute; SPY-excess mis-frames it). Regime robustness
  (leg 4) + the placebo (leg 6) are the guards against "it's only beta."
- Short-horizon high-WR is the easiest thing to overfit and where costs bite; a
  PASS is display-only and a promotion CANDIDATE, not a validated edge. A
  transaction-cost haircut must be applied before any live claim.
- v2: replace the 21-session time-exit with the exact 2D-StochRSI-top exit once
  a 2-day-bar StochRSI is computed; re-freeze if thresholds change materially.
