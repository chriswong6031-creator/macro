# Score iteration v3.1 — adjudication record (2026-08-05)

**Adjudicator:** main-loop Fable, CN Prophet program. **Baseline to beat:**
capture@6 = 0.111 / oracle regret 13.46pp (rank-effectiveness calibration on the
V1 era, PR #4570). **Evidence reviewed:** rank_feature_battery (#4571),
flow_exante_battery (#4520), both gate audits (#4576, #4582), the era-retro
(#4521), the rank-effectiveness ledger's multi-metric calibration (#4570), and
the v3 leg structure as shipped (#4509). All merged; all numbers cited from
their frozen artifacts.

## Decisions

**D1 — NO score reweighting in this iteration.** The forward per-leg
attribution only became gradeable today (#4658 persists `prophet_theme_timing`;
the audit now reads a same-night spine). Reweighting v3's legs on the *legacy*
frame's feature ICs would tune the new instrument on the old instrument's
cohort. The battery independently VALIDATED v3's two structural calls — the
`setup` removal (it orders the pool backwards, −0.157 date-demeaned, both
halves) and the theme_timing ladder's shape (`in_basket` +0.196, the only
stable non-price axis; the Trough+/Trough− split 0.707 vs 0.429 matches the
1.0-vs-0.6 rungs) — so the score stands as shipped until its own forward
attribution (now live) accrues ≥60 matured v3 episodes per leg.

**D2 — Crowding (turnover percentile) enters as display + strata, NOT a leg.**
Its admission-level separation is the strongest single number in the program
(17.7% → 42.5% loser rate, monotone, full coverage — #4520), but its
*within-pool ordering* IC did not reach the battery's stable top tier. Path:
context-vector column + card chip (display, free) + a turnover-bucket stratum
in the W0 telemetry; a score leg or featured shortfall requires its own prereg
once the strata accrue. This is the flow battery's own recommendation kept
intact.

**D3 — Thrust cap goes to prereg, in ordering form.** trail_21 is the
strongest continuous anti-ordering axis (−0.212, stable). The filter form was
already costed and is too blunt at any single threshold (trail21≥25% removed
only 5 era episodes). PREREG (to run as an era-retro extension before any
ratification): a bounded ordering penalty `−k × within-date trail_21
percentile` applied to the v3 score, k chosen so the leg is worth ≤10 points;
promotion bar: capture@6 and regret improve on the era frame AND the
winners-forfeited table satisfies G0.7; tripwire mirrors the theme_timing
pattern.

**D4 — Closed, with receipts:** compression leg (sign reversed on CN, S-COIL
port NO-GO — #4571), `vs_ma200` (ρ0.83 with the killed depth axis — fence
ruling recorded), winners-only magnitude ranker (ICs ≤0.11 — nothing ranks
which winner runs farthest; ordering value is loser-avoidance + theme
positioning), naive gate removals (both audits: keep), blanket chase veto
(right-tail amputation), naive sector caps / board shrinking (winner-negative).

**D5 — The HOLD-leg prereg is the one open door question** (from #4582: the
continuation cell's binding leg, which HK deliberately kept; reclaim narrowly
earns, hold fails both horizons). It is a POPULATION question, not an ordering
question, and belongs to its own prereg with the continuation-watch ledger
(accruing since last night) as its evidence stream.

## What grades this iteration

The rank-effectiveness block now prints nightly, per definition: the IC ladder
across every outcome dimension, capture@6/regret, risk-by-tercile, per-leg
attribution, and the wrong-sign tripwire. v3.1's success criterion is not a
promise: it is capture@6 rising off 0.111 on the v3 cohort as it matures, with
no tripwire firing. The next adjudication reads those numbers, not this file.
