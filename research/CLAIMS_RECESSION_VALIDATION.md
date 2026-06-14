# Phase-0: Folding Jobless Claims into the Recession Composite

**Question.** The `recession_risk` composite (engine/conditions.py) feeds the macro-risk
SCORE (sector heat + per-stock ladder), so house discipline is validate-before-wire.
Does adding an initial-jobless-claims leg improve recession detection vs NBER — and is
the gain INCREMENTAL over the existing legs, especially the Sahm leg (itself
unemployment-derived, so partly redundant with claims)?

**Verdict: WIRE, conservative weight 0.5.** A real, consistent, out-of-sample-stable
improvement — modest because the composite is already strong, but it clears the bar.

## Method
- Monthly panel **1967–2026, 8 NBER recessions** (USREC). Far more events than the
  post-1993 engine frame (3) — claims/Sahm/NY-Fed-prob reach back to 1967, EBP to 1973.
- Replicated the conditions.py 0..1 leg transforms + config weights; composite =
  weighted mean over available legs ×100 (the engine's renormalization rule).
- Claims leg (PRIMARY, pre-registered): YoY of the 4wk-MA level, `/0.40` clipped 0..1
  (+40% y/y ⇒ full). Robustness leg: Sahm-analog (rise off trailing-12m low).
- Targets: NBER concurrent, and NBER within next 6 / 12 months (the lead test).
- Metrics: standalone AUC, claims-vs-Sahm correlation, composite ΔAUC, split-half
  stability, threshold lead/false-alarm. Harness: `scripts/validate_claims_recession.py`.

## Results
**Standalone AUC** (recession discrimination):

| leg | concurrent | within 6m | within 12m |
|---|---|---|---|
| Sahm | 0.884 | 0.775 | 0.699 |
| NY-Fed prob | 0.998 | 0.959 | 0.893 |
| EBP prob | 0.872 | 0.810 | 0.764 |
| curve (tp-adj) | 0.488 | 0.523 | 0.538 |
| EBP level | 0.827 | 0.768 | 0.749 |
| **claims YoY** | **0.953** | **0.873** | **0.810** |

Claims is a **stronger standalone labor signal than the Sahm leg at every horizon**, and
only **0.62-correlated** with it → not redundant.

**Composite ΔAUC** (with-claims minus base, w=0.5): **+0.011 concurrent, +0.013 (6m),
+0.014 (12m)** — positive at every horizon (w=1.0 gives +0.013 / +0.018 / +0.021).

**Split-half (within 6m), both must improve:** early 1967–1996 +0.017 (5 onsets), late
1996–2026 +0.005 (3 onsets). **Both positive.**

**Threshold (high=55):** no new false alarms (0→0); median lead ~unchanged (3.0→2.0 mo,
noisy at 3 qualifying onsets). The AUC, which integrates over thresholds, is the robust read.

## Why modest, and why still WIRE
The composite is already near-ceiling because the NY-Fed-probability leg is essentially a
recession model fit to NBER (concurrent AUC 0.998). Against that ceiling, any orthogonal
leg shows a small ΔAUC. But the claims gain is **consistent across all horizons, positive
in both split-halves, adds zero false alarms, and the leg is independently a better labor
signal than the Sahm leg it sits beside.** Unlike a rejected addition (cf. the GBT
meta-label, ΔSharpe −0.43), this is a genuine, conservative improvement.

Weight **0.5** (the "supporting" tier, matching EBP-level) — not 1.0 — so a single weekly
series can't dominate the score. Config-gated (`weights.claims: 0`) for clean rollback.

## Live behaviour (2026-06)
Claims falling (−9.6% y/y) ⇒ claims leg reads **0** (benign), nudging `recession_risk`
slightly DOWN (a labor "all-clear"). Score 7.81 / low. Correct: the leg adds signal in
both directions and is currently saying "no recession from the labor side."

## Phase-1.5 — point-in-time robustness (DONE)
The Phase-0 numbers used stored (latest-revised) series. Two look-ahead sources could
in principle have manufactured the result: REVISION (latest-revised legs, esp. the
Chauvet-Piger recession prob, "know" recessions better than their real-time prints) and
TIMING (a value stamped on its reference month wasn't published until weeks later).
`scripts/validate_claims_recession_pit.py` re-measures ΔAUC(claims, w=0.5) under both
fixes. Claims barely revise (~3%, mostly 4wk-MA smoothing) and publish within days, so
the PIT-ness is applied to the OTHER legs; claims stays stored.

| mode | recessions | ΔAUC 6m | ΔAUC 12m |
|---|---|---|---|
| revised-full (Phase-0 baseline) | 8 | +0.013 | +0.014 |
| **lagged-full** (stored + publication lags; timing-honest) | 8 | **+0.025** | **+0.023** |
| **ALFRED-PIT** (sahm/prob real-time initial-release, 1997+; revision-honest) | 3 | **+0.019** | **+0.019** |

**The claims leg SURVIVES point-in-time — and gets STRONGER.** Removing timing look-ahead
roughly DOUBLES its incremental value (+0.013 → +0.025 at 6m): the other legs lose ground
when lagged 1–2 months, while claims (weekly, ~0 lag) does not, so claims fills more of
the gap. This is the whole thesis — claims helps *because* it is real-time — confirmed
once the other legs no longer get an unfair as-of-reference-date advantage. It also holds
under revision-honest ALFRED data (low power: only 3 recessions since the archive begins
1997). The conservative w=0.5 stands (the lagged result would justify more; we don't chase
a single-sample number).

CAVEAT: ALFRED claims vintages begin only 2009 (negligible — claims barely revise); EBP
has no ALFRED series (it is the one leg without revision-PIT, lagged-stored in PIT mode —
ΔAUC(claims) is robust to it since base and +claims share the same EBP leg); NBER dates are
final (correct — PIT applies to features, not the target).
