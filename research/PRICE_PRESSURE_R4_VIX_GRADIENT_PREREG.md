# PRICE PRESSURE — R4 VIX-liquidity gradient pre-registration

Registered: 2026-08-10 (DRL session 2). Status: **REGISTERED — UNGRADED. Zero
evidence rows exist** (the forward era begins with the 2026-08-11 session).
Program: `research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md` §8 leg 1;
gate law §7. Kill-scope authority: DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER
(whose own text carves out this claim: "needs its own prereg with frozen
breakpoints — it does NOT revive the classifier") and
DNR:KILL-ABSOLUTE-VIX-THRESHOLDS (absolute VIX anchors are non-stationary —
this prereg therefore uses the trailing-percentile transform, not levels).

This document is the registry for the claim. Grading results are appended
here, never rewritten.

## §0 Provenance — the in-sample sighting, disclosed

This is **not** a no-peek registration. LSR-P0's reopener pass
(`scripts/research_lsr_reopeners.py`, report
`research/LIQUIDITY_SHOCK_REVERSAL_PHASE0.md` §7, 2026-08-05) already computed
a VIX-conditioned cut on the 2021-09→2026-07 panel: the **no-news down arm**
ran −0.599% (calm) → −0.312% → +0.261% (stressed) resid at h=5 across VIX
terciles, and the direct difference test on calm (pct < 0.5) vs stressed
(pct ≥ 0.8) gave calm − stressed = **−0.860% [−1.575, −0.145]** — excluding
zero at 1 of 3 horizons, with post-hoc breakpoints, on an arm mean (not a
tradeable spread). The kill row logged it as "ONE LEAD LOGGED, NOT CLAIMED."

Epistemic status therefore: hypothesis = Nagel (2012) ("Evaporating
Liquidity": compensation for liquidity provision scales with VIX) **plus one
in-sample sighting on the span that is now the ledger's backfill era**. The
forward era (rows stamped `era="forward"`, sessions 2026-08-11 onward) is
disjoint from every date the sighting touched, so grading on forward rows only
is a true out-of-sample confirmation. No VIX-conditioned readout of the DRL
ledger itself has ever been computed (the base-rate artifact carries no VIX
axis); the breakpoints below are **imported from the sighting and frozen ex
ante for the forward test** — they are not chosen post hoc a second time.

## §1 Frozen claims

Direction convention: `fwd{h}` is the ledger's stamped h-session forward
residual log-return. For down-side events, continuation is negative;
"continuation weakens" means the stressed-arm mean is HIGHER (less negative).

- **R4-A (mechanism replication, h=5).** Among eligible down-side forward
  episodes (§2), mean `fwd5` in the STRESSED arm exceeds mean `fwd5` in the
  CALM arm: Δ_A = mean(fwd5 | stressed) − mean(fwd5 | calm) > 0, with the 95%
  date-block bootstrap CI excluding zero.
- **R4-B (product horizon, h=21, conjunctive).** Same cells at the program's
  decision horizon: Δ_B1 = mean(fwd21 | stressed) − mean(fwd21 | calm) > 0
  AND Δ_B2 = share(terminal_state_21d == RECOVERED | stressed) −
  share(… | calm) > 0, each with its 95% date-block bootstrap CI excluding
  zero. B is conjunctive because the surface sentence it would unlock speaks
  in outcome shares — a means-only pass may not promote a share-worded
  sentence.

## §2 Evidence cells (construction imported, not tunable)

- Detector, fence, thresholds, horizons, peer basis: exactly the shipped
  `engine/price_pressure/` detector (z ≥ 3, 2× volume, $5/$5M-ADV, stamped
  `peer_basis` per row). Changing any of these = re-tuning the killed
  construction: forbidden.
- Rows: `era == "forward"` only. `gap`/`backfill` rows are never evidence.
- Side: `side == "down"` only.
- Filing arm: `edgar_covered == True` and `family == "no-filing"` (the
  sighted arm). `filing-coverage-unknown` rows are excluded — the no-news
  property is unknowable there.
- Episode unit: `first_in_5 == True` for R4-A; `first_in_21 == True` for
  R4-B (per-horizon honest-N, masterplan §5).
- Delisted/halted terminals stay in denominators at their terminal values
  (§12 discipline); a DELISTED_OR_HALTED terminal is not RECOVERED for Δ_B2.

## §3 Conditioning variable (frozen)

- Source: `data/fred/VIXCLS.parquet` (FRED VIXCLS), first column, ffilled to
  the event date — the same source and mapping the sighting used.
- Transform: `pct = v.rolling(252, min_periods=120).rank(pct=True)` — the
  trailing 252-session percentile of the t0 close, inclusive of t0.
- Arms: **CALM = pct < 0.5**; **STRESSED = pct ≥ 0.8**. The middle band
  (0.5 ≤ pct < 0.8) enters no test; it is printed descriptively with the
  grading. These are the sighting's own direct-test cells, now frozen.
- PIT: the percentile uses closes through t0 — the same close the shock
  itself is measured on; no lookahead. FRED's publication lag is irrelevant
  at grading time (historical series complete).

## §4 Inference (frozen)

Difference of arm means (shares for Δ_B2), stressed − calm, with the same
date-block bootstrap machinery the base-rate artifact uses (blocks = event
dates; arms are date-disjoint by construction since a date has one VIX
percentile), 95% percentile CI at the machinery's default resample count.
One-sided direction as stated in §1; an interval excluding zero in the WRONG
direction grades the claim FAILED, not inconclusive.

## §5 Floors and discipline (per masterplan §7)

- Each arm of a claim: ≥ 200 forward episodes across ≥ 40 distinct event
  dates before that claim may be graded. A-arms and B-arms count separately
  (different `first_in_h`).
- No interim significance peeking. The accrual substrate is the ledger;
  grading happens once per claim, in the session where floors first clear.
- No re-binning, re-horizoning, re-siding, or era-mixing at grading time —
  any of those is the LSR re-tuning shape and voids the registration.
- An opus `reviewer` adversarial pass on the exact claim text and the graded
  numbers is required before ANY surface change (masterplan §7 clause 4).
- The grading script is written at grading time to implement THIS document
  literally, with no free parameters, and is committed alongside the results.

## §6 Consequence matrix (what grading changes)

- **A pass ∧ B pass** → the base-rate artifact gains the VIX axis and the
  band may carry one comparative sentence (plain words, e.g. "in stressed
  tape, more of these came back"). Display tier still — ranking, sizing, or
  gating anywhere requires a further full §7 trip.
- **A pass ∧ B fail** → both printed on the Calibration Lab; no band
  sentence (mechanism exists at 5d but fades by the decision horizon — that
  IS the honest product answer).
- **A fail** → null printed (nulls-printed law); the VIX axis ships as
  context-only, no comparative language anywhere. B is still graded and
  printed when its floors clear, but **B alone never promotes**: a 21d effect
  with no 5d mechanism contradicts the sighting that motivated this prereg
  and reads as noise until re-registered from scratch.

## §7 Clock (honest)

As of registration VIXCLS closed 14.90 (2026-08-07) — deep in the CALM arm.
The STRESSED arm accrues only when the trailing percentile exceeds 0.8, i.e.
during genuine vol regimes; at the current tape its forward count is zero and
stays zero. Earliest plausible grading is therefore unknown — the calm arm
may clear its floors in months while the stressed arm waits years for a
regime. Check floors each DRL session
(`research/DRL_CONTINUATION_HANDOFF_2026-08-10.md` queue); do not grade
early, do not substitute eras.

## §8 Grading log (append-only)

*(empty — no grading has occurred)*
