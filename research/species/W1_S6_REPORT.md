# W1 S6 Phase-0 Report — Failed-Fire Fuel (OOS basket panel)

*2026-07-04 · prereg: research/species/W1_S6_PREREG.md (committed before the run)
· harness: research/entry_timing/wave2.py --panel baskets (UNMODIFIED; regenerated
run reproduced the audited panel exactly: 102,433 fires, COILED n=6,842 — the §8
G2 numbers) · analysis: research/species/w1_s6_analysis.py · raw:
research/species/_s6_phase0_out.json · trial family `s6_failed_fire_fuel` (m=2).*

## Verdict

**S6 PASSES phase-0 — the failed-fire inversion is REAL out-of-sample, in both
registered variants — but at an effect size BELOW the ≥5pp promotion floor.**
Per the pre-registered outcome paths: S6 advances to **display-chip candidacy
only** (ladder §1.3 bottom rung) with ledger accrual; nothing ranks, sizes, or
gates off it, and promotion past display requires the full §1.2 battery
(which the current +3.8/+4.3pp spreads do not meet).

The graveyard's "cried-wolf veto" stays dead in both directions confirmed: the
veto was inverted in-sample, and the inversion now holds OOS — **serial failure
inside cohort washout is fuel, not poison.**

## Primary — failed2 × COILED interaction (clean8_21, rotational primary)

| variant | failed2=T | failed2=F | spread | p (episode boot) | BH q (W1 family, m=4) | halves | per-name majority |
|---|---|---|---|---|---|---|---|
| m2d_s3d | 37.15% (n=3,160) | 32.86% (n=3,682) | **+4.29pp** | 0.008 | **0.032 ✓** | +3.93 / +4.45 ✓ | 52.7% of 459 ✓ |
| base3d | 36.52% (n=1,224) | 32.73% (n=3,804) | **+3.79pp** | 0.040 | **0.080 ✓** | +5.58 / +1.54 ✓ | 52.0% of 319 ✓ |

All five registered requirements met in both variants (spread>0, q≤0.10,
n≥300/side, both halves positive, per-name majority >50%).

**The safety axes agree** (the constitution's real test): within COILED, the
failed2 side STOPS OUT LESS — m2d_s3d 35.66% vs 40.58% (−4.9pp), base3d 37.09%
vs 38.70% — and the positional grid (clean15_126 context) points the same way
(41.01 vs 36.72; 39.13 vs 36.25). This is not liftoff bought with stop-outs.

## Secondary — standalone failed2 on ALL fires (context, cannot promote)

Spreads +4.14pp / +3.71pp, BUT with WORSE stop-outs on the failed2 side
(45.97 vs 43.52; 45.76 vs 44.15). **Standalone, the inversion buys liftoff by
eating stop-outs — it is only inside cohort washout that serial failure is
safety-positive.** The interaction is the species; the standalone form stays
context, exactly as registered.

## Honesty / caveats

- **Effect size below the promotion bar:** +3.8/+4.3pp < the §1.2 ≥5pp floor.
  Display-chip rung only; the forward ledger (near-miss capture now stamps
  every failed fire with reasons) accrues the honest forward read.
- **Per-name majorities are thin** (52.0%/52.7% — barely above coin on 319/459
  names). The edge is broad-but-shallow, cohort-carried rather than name-carried.
- **OOS came in STRONGER than in-sample** (wave-1: +1.8/+3.2pp; OOS baskets:
  +3.79/+4.29pp) — the same direction of surprise as COILED's G2 replication.
- base3d's bootstrap spread CI touches zero ([−0.47, +7.68]); m2d_s3d's does
  not ([+0.87, +7.41]). The registered criterion (BH q) passes for both; the CI
  is printed for the owner's eyes.
- Survivorship: the basket panel carries current-membership bias (printed in
  prereg; unchanged). Sector cohorts per the wave-2 audited construction.
- Leak audit: unmodified harness (its wave-2 leak audit stands); rotational
  clean8_21 recomputed per fire through engine.grading.terminal_state (shared
  constants, next-bar fill); failed2 verbatim wave-1 (≥2 own-trigger stops in
  trailing 180cd — trailing window, no forward information).

## Registry / gating updates shipped with this report

- S6 `validation_status` stays `phase0`; gating.maturation records the pass +
  the sub-5pp constraint; `come_back_on` → 2026-08-01 (monthly review decides
  the display-chip wiring; the ledger accrues meanwhile).

## In plain English

We asked: when a stock's buy signal has already failed twice recently, is the
third one poison or fuel? Out of sample, on 100k+ signals across ten years of
basket names: **fuel — but only when the whole sector is washed out too.** In
that setting the twice-burned names lifted off cleanly 4 points more often AND
got stopped out 5 points less. Alone, without the sector-washout context, the
extra liftoffs come with extra stop-outs — no free lunch. The effect is real
but modest (below our bar for letting it influence rankings), so it earns a
badge on cards and a place in the forward ledger — and nothing more yet.
