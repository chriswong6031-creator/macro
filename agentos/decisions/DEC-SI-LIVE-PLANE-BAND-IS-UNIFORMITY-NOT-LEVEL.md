---
key: SI-LIVE-PLANE-BAND-IS-UNIFORMITY-NOT-LEVEL
question: >
  DEC:SI-REGISTERED-B-PREFIX-IS-A-FROZEN-SNAPSHOT froze the registered B prefix off the
  live plane and kept a revision tripwire on it, specified as "price moves within 1e-5
  relative, volume within 1e-2". What may that tripwire actually assert? A relative band
  on the price LEVEL is the obvious reading, and it is the one that shipped.
answer: >
  Band the UNIFORMITY of the vendor's rescale, not its level, and split the volume rule by
  whether the session had settled. Concretely: (1) per-row O/H/L/C factor coherence at
  1e-6; (2) per-row factor residual against the WINDOW MEDIAN factor at 1e-5 — this is the
  clause that replaces the level band; (3) settled-session volume must match EXACTLY, with
  the 1e-2 band retained for the ASOF bar alone; (4) a gross-rescale sanity bound
  [0.2, 5.0], checked AFTER volume so a real corporate action is diagnosed as one.
  This amends the tripwire clause of DEC:SI-REGISTERED-B-PREFIX-IS-A-FROZEN-SNAPSHOT and
  leaves every other part of it — the freeze, the unchanged digest, the falsification of
  quantize-then-hash — standing.
rationale: >
  A level band cannot survive an ordinary dividend, so it is a fleet red with a due date.
  `auto_adjust=True` re-scales the whole ELAPSED history on every FUTURE ex-date, so a
  routine ~$0.10 Barrick quarterly on a ~$41 tape moves every historical row by ~2.4e-03 —
  240x a 1e-5 band. The shipped comment justifies 1e-5 against "the smallest economically
  real price revision, one cent at the plane's minimum price of 4.81 = 2.08e-03, a ~2400x
  separation"; that reasoning is sound about REVISIONS but the dividend re-adjustment lands
  in the same 1e-3 neighbourhood while being no revision at all. It is also the wrong
  quantity to measure: a uniform rescale leaves every return, drawdown and percentage gap
  identical, so it cannot move a W1-A1 conclusion. Only a change in RELATIVE prices can,
  which is exactly what a residual against the window median sees. Corporate actions are
  not thereby ignored — split adjustment rescales share counts too, so requiring settled
  volume to match exactly catches them on a channel that a price band cannot fake. That
  same split also repairs a blind spot: a blanket 1e-2 volume tolerance let a settled
  session's volume be restated by up to 1% unseen, and only the ASOF bar is genuinely
  provisional.
alternatives:
  - option: Keep the per-column level band at 1e-5 (what shipped in PR #5865)
    why_not: "Fires on any future dividend — measured against that code: $0.10 -> 2.40e-03, $0.02 -> 4.90e-04, $0.005 -> 1.22e-04, all red — so the fleet re-reds on the next ex-date. Also measures a quantity no conclusion depends on."
  - option: Widen the level band above dividend scale (e.g. 1e-2)
    why_not: Would swallow the real revisions the tripwire exists to catch — a one-cent restatement at this plane's minimum price is 2.08e-03, inside such a band. Widening trades a scheduled false positive for a permanent false negative.
  - option: Drop the live-plane check now that the build reads the snapshot
    why_not: Forfeits the only detector of a genuine historical revision to the sealed evidence window; the snapshot would silently diverge from the curated plane with nothing watching.
  - option: Set the coherence band at the observed 4.4e-16
    why_not: That sits ~5 orders BELOW the float32 grid of the underlying raw prints (~6e-8). One raw print re-quantizing by a single ULP, or a yfinance bump deriving O/H/L differently, would report vendor noise as a print revision. 1e-6 sits ~16x above the grid and still catches anything meaningful ($0.00004 on a $41 tape).
evidence: >
  Simulated against the frozen snapshot using PR #5865's own shipped check
  (_validate_live_b_plane_tracks_registration, B_LIVE_PRICE_REL_TOL = 1e-5): a 0.9976
  rescale fires at 2.40e-03, 0.99951 at 4.90e-04, 0.999878 at 1.22e-04; a settled-session
  volume restatement of +0.5% does NOT fire. Measured seed->live over the 3,172-row
  prefix: O/H/L/C share one per-row float64 factor coherent to 4.4e-16; residual against
  the window median <= 8.63e-07 and non-accumulating over the observed 4-day, no-dividend
  window; settled volume byte-identical on all 3,171 rows, only the ASOF bar moving
  (10,621,100 -> 10,625,700, 4.33e-04). tests/test_stock_identity_atlas.py encodes both
  directions and all ten new cases FAIL against main's pre-change builder
  (`git checkout origin/main -- scripts/stock_identity_build_w1a1.py` then
  `pytest -k b_tripwire` -> 10 failed; 10 passed after restoring).
affects:
  - WS:STOCK-IDENTITY
  - scripts/stock_identity_build_w1a1.py
  - research/stock_identity/W1_IDENTITY_ATLAS_V0_REGISTRATION.md
discoveries:
  - DSC:SEALED-PIN-ON-A-NIGHTLY-OWNED-PATH
  - DSC:BASKET-OHLCV-REWRITES-HISTORY-NIGHTLY
confidence: high
reversibility: easy
decided_by: coo-fable
decided_at: 2026-08-18
review_by: 2026-11-18
---

## The generalizable part

When you replace an equality check with a tolerance, ask what **routine future event**
moves the quantity — not merely what noise moves it. A band calibrated only against the
noise you happened to measure is a red with a due date, and it will look correct for
exactly as long as the routine event stays outside your observation window. Here the
noise window was four days and contained no dividend, so the dividend never appeared in
the data the band was fitted to.

The deeper move is to band the **invariant the conclusion depends on** rather than the
raw quantity. W1-A1's conclusions are functions of returns, drawdowns and percentage
gaps, every one of which is invariant to a uniform rescale of the whole window. So a
uniform rescale — of any size — is not a revision, and the tripwire should be blind to it
by construction rather than by choosing a large enough number. What remains after
quotienting out that invariance is precisely the thing that can hurt: relative price
change, and share counts.
