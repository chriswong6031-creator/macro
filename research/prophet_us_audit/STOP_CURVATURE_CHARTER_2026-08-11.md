# Stop-curvature context charter — pre-registration (2026-08-11)

**Program home:** `research/PROPHET_US_EYES_OPEN_MASTERPLAN_BY_FABLE.md` §6.8(a).
**Parent artifact:** `research/prophet_us_audit/EARLY_ADMISSION_BAKEOFF_2026-08-11.md`
(§R4/R4b strict-form kill, §R9 controls, §RT red-team record).
**Status:** CHARTER — registered before any outcome look at the curvature family. No
measurement has run. Charter edits after the first outcome read constitute a NEW charter.

## §0 What this charters, and what it does not

R4b killed the §6.8(a) conditioning hypothesis **as pinned** — "MACD histogram already
rising (2-step) at stop confirm" — on three legs: the cohort is rare (110/12,786 = 0.9%),
it marks local lows LESS than base (23.6% vs 35.0%; month-cluster CI −11.4pp [−19.2,−2.8]),
and its forward tape is weaker. That kill closes the strict-rising construction only. The
operator's described form — "arching up **off the histogram low**" — is a
curvature/above-trailing-min construction the strict lens does not express: the motivating
STLD May-19 receipt itself reads `hist_rising=False, 3D-bull=True` at confirm, so the
killed lens cannot even see the chart the hypothesis came from. The bake-off deliberately
refused to audition curvature forms on its data ("no outcome-audition"); this charter is
that audition's pre-registration.

Load-bearing fact this family targets (R9f): **34.9% of the 12,940 replayed stop confirms
land within ±2 sessions of the ±10-session local low, vs 15.7% random-session null on the
same frame (2.2×, stable 1.7–2.7× across ±5/±10/±15)**. A third of stops are bottom
prints. The product question is which stops those are, knowably, at the confirm close.

Scope of consequence: this study licenses (or refuses) PROMOTION only — a mechanical
effect on stop handling (disarm, demote-to-flush-watch, re-entry arming with rank/size
consequence). The display-tier "flush watch → re-entry watch" surface is context, ships
under §6.6 word budgets regardless of the verdict, and carries the honest null if the
family nulls. No falsifier language front-facing, ever (operator 2026-07-27).

## §1 Motivating receipts and the exemplar-coverage bar

STLD 2026 (all three from the R1 read-out, outcomes already public in the parent doc —
disclosed as known):

| stop confirm | low gap | forward | reading |
|---|---|---|---|
| May-19 @ 222.86 | argmin ON confirm session (0) | +23.2% fwd10 | bottom print; `hist_rising=False, 3D-bull=True` |
| Jan-07 | 1 session off local low | +20.6% fwd21 | bottom print |
| Jun-18 | — | −8.9% fwd10 | the stop that worked |

**Exemplar-coverage gate (definition validity, not statistics):** a candidate lens must
classify May-19 AND Jan-07 curvature-TRUE at their confirm-bar closes using only
information available then. A lens that misses either does not formalize the operator's
visual form and is disqualified **ex ante** — before its outcome row is read
(discovered-rule law: the rule must cover its motivating exemplars). Jun-18 is narrative
illustration only; no lens is tuned to reject it — discrimination is what §3's outcomes
measure. Because these exemplars' outcomes are already published, the primary tables print
a sensitivity row excluding STLD entirely (3 events in a 12,940-confirm frame; the row is
disclosure, not protection).

## §2 Construction family (enumerated now; nothing else gets a read)

All inputs computed strictly at-or-before the stop-confirm bar close on the same
extraction the R4 replay used. `hist` = 1D MACD histogram; `tmin_w` = trailing minimum of
`hist` over the prior `w` sessions (excluding the confirm bar itself from the minimum, so
"off the low" is knowable). Primary parameter cell is pre-declared per form; the
remaining grid is sensitivity only — **no best-cell promotion**.

- **K1 — off-the-trailing-min:** `hist > tmin_w` AND `hist < 0` AND `tmin_w < 0`.
  Arching up off a below-zero low without requiring monotonic rise (May-19's signature
  failure mode in the strict lens). Primary `w=15`; sensitivity `w ∈ {10, 21}`.
- **K2 — curvature proper:** mean second difference of `hist` over the last `m` bars ≥ 0
  with at most one negative first-difference bar (arch, not staircase). Primary `m=3`;
  sensitivity `m=5`.
- **K3 — normalized recovery:** `(hist − tmin_w)/|tmin_w| ≥ θ` with `tmin_w < 0`.
  Primary `θ=0.30, w=15`; sensitivity `θ=0.15`.
- **K4 — multi-timeframe carry:** 3D-bull state true at confirm (the literal remaining
  half of the May-19 receipt: the 3D lens carries the turn the 1D histogram misses).
  DEPENDENCY: 3D grids currently inherit the confluence_v2 first-timestamp phase defect
  (parent §R4.hl_phase; handed to charting-app, chip task_d619e0c8). K4 is measured on
  session-anchored recomputation macro-side (`engine/session_anchor.py` pattern), with a
  parity row on the phased grids for reconciliation. If session-anchored recomputation is
  not available at execution time, K4 is DEFERRED, not approximated.
- **K5 — the single pre-declared composite:** K1 OR K4. No other unions, intersections,
  or parameter cells get an outcome read under this charter; any new form is a new charter.

## §3 Frame and outcomes (frozen)

Frame: the R4 replay frame — 12,940 stop confirms, extraction parity-identical to the
Terminal machinery, store window ~2014+ with the parent doc's substrate bounds restated
(18,137 C0 / 7,202 C2 pre-store events dropped, never relocated; exposure 2,658.7
name-years; breadth features are NOT used here, so the post-2023 basket bound does not
bind). This frame has been outcome-read by R4/R8/R9 for OTHER lenses; the curvature family
has never been auditioned on it. Disclosed accordingly: this is one pre-registered pass on
already-frozen tape; the confirmatory tier is forward accrual (§6).

Per form K, against base 34.9% and null 15.7%:

- **Primary:** low-marking rate — share of curvature-TRUE confirms within ±2 sessions of
  the ±10-session local low; month-cluster CIs (R4b style); window-grid sensitivity
  ±5/±10/±15 (R9f style); per-name-first aggregation beside pooled (R2 style);
  both-time-halves sign stability (R2g style).
- **Secondary (economics, R8b framing):** forward tape of curvature-TRUE vs
  curvature-FALSE confirms (median/IQR @10/@21) — measured as MOVE captured, never as
  "safety"; and re-entry-watch economics: watch-armed → next structure re-confirm entry,
  graded under the fire's own risk contract, vs the do-nothing baseline. R8b already
  proved waiting changes stop-out rates by ZERO under the fire's own contract — any claim
  here must be in move terms.
- **Coverage:** curvature-TRUE share of all confirms, per form (the R4b 0.9% failure is a
  named trap; see G1).

## §4 Trap controls (each named from the §RT record)

1. **PIT audit (R9c class):** every feature input ≤ confirm-bar close; an explicit leak
   test in the study script (the repeat-fire retraction was a label window resolving past
   T — the same audit runs here before any table freezes).
2. **Stop-width arithmetic (R9d class — the verdict lives here):** full risk-equalization
   battery — fixed −8% stops, 2ATR stops, entry-distance quintiles. A curvature lift that
   dies under risk-equalization is stop-width arithmetic and is printed as such (the
   parent §RT recorded three artifact classes of this trap on this very frame).
3. **Thin-cohort floor:** promotion requires coverage ≥5% of confirms (R4b failed at
   0.9%). Below floor → "rare-lens" disclosure tier only, whatever the point estimate.
4. **Multiplicity:** 5 forms × pre-declared primary cells = 5 primary reads; grids are
   sensitivity-only and printed in full. Promotion is judged on the pre-declared primary
   cell, never a scanned max.
5. **Survivorship/substrate:** parent N4–N6 bounds restated in the artifact; no silent
   re-windowing.
6. **Phase defect (R4.hl_phase):** K4's dependency stated in §2; a phased-grid parity row
   reconciles, and a material divergence between phased and session-anchored K4 rows is
   itself a finding to print.

## §5 Promotion gates (pre-registered)

Per form, ALL must clear on the pre-declared primary cell:

- **G1 coverage:** ≥5% of confirms.
- **G2 low-marking lift:** ≥ +8pp over the 34.9% base, month-cluster CI lower bound
  > +2pp. (Magnitude anchor: the killed strict form's deficit was −11.4pp [−19.2,−2.8]; a
  promotable positive form should be of comparable magnitude with a CI that excludes
  noise, not merely a positive point estimate.)
- **G3 survives risk-equalization:** sign-stable under all three R9d lenses with ≥ half
  the raw lift retained.
- **G4 forward-tape consistency:** curvature-TRUE cohort median fwd10 ≥ +2% (bottom
  prints run; the exemplar ran +23.2%).
- **G5 exemplar coverage:** §1 bar (May-19 + Jan-07 TRUE) — checked before outcomes are
  read.

FAIL → the form's row lands in the ore ledger, the construction closes, the family stays
open ("not found yet" ≠ "does not exist"); the display-tier watch surface keeps shipping
with plain-word null disclosure. PASS → eligible for the promotion gauntlet only: the
mechanical effect (stop demote-to-flush-watch + re-entry arming) enters the forward accrual
tier below before any rank/size consequence.

## §6 Confirmatory tier (forward, nightly)

The nightly stop-confirm stream accrues curvature-form stamps from the first bake after
the study script lands (display/data tier — accrual is never blocked by a null, per the
epistemics law). Confirmatory read at ≥120 stamped confirms or 2026-11-01, whichever is
later; same gates, no re-tuning. The frozen-frame pass (§3) licenses nothing on its own if
the forward tier contradicts it — forward outranks frozen.

## §7 Execution notes

Study script lands beside the parent's in `research/prophet_us_audit/` with frozen `RC.*`
tables; red-team pass (Opus reviewer lane) is mandatory before the results doc lands — the
parent's adjudication coverage gate applies unchanged. Routing per house law: script build
= Opus builder; adjudication of the verdict = main loop. Execution is a successor-session
work item; this charter is the registration act.
