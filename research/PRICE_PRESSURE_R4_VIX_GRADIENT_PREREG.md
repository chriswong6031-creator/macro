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
here, never rewritten. A pre-merge, pre-evidence audit amendment is recorded
in §9; it fixed an enum typo and closed PIT, inference, and maturity degrees of
freedom before the first eligible forward session.

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
is a true out-of-sample confirmation. It is not an exact replication sample:
the forward ledger additionally applies the program's per-horizon episode
deduplication (`first_in_h`). No VIX-conditioned readout of the DRL ledger
itself has ever been computed (the base-rate artifact carries no VIX axis);
the breakpoints below are **imported from the sighting and frozen ex ante for
the forward test** — they are not chosen post hoc a second time.

## §1 Frozen claims

Direction convention: `fwd{h}` is the ledger's stamped h-session forward
residual log-return. For down-side events, continuation is negative;
"continuation weakens" means the stressed-arm mean is HIGHER (less negative).

- **R4-A (prospective mechanism confirmation, h=5).** Among eligible down-side
  forward episodes (§2), the mean of the date-level `fwd5` means in the
  STRESSED arm exceeds the corresponding CALM mean: Δ_A = mean_date(fwd5 |
  stressed) − mean_date(fwd5 | calm) > 0, with the 95% date-block bootstrap-
  difference CI excluding zero.
- **R4-B (product horizon, h=21, conjunctive).** Same cells at the program's
  decision horizon: Δ_B1 = mean_date(fwd21 | stressed) − mean_date(fwd21 |
  calm) > 0 AND Δ_B2 = mean_date(share(`terminal_state_21d ==
  "RECOVERED_21D"`) | stressed) − the corresponding CALM mean > 0, each with
  its 95% date-block bootstrap-difference CI excluding zero. B is conjunctive
  because the surface sentence it would unlock speaks in outcome shares — a
  means-only pass may not promote a share-worded sentence.

## §2 Evidence cells (construction imported, not tunable)

- Detector, fence, thresholds, horizons, peer basis: exactly the shipped
  `engine/price_pressure/` detector (`abs(resid_z) ≥ 3`, 2× volume,
  $5/$5M-ADV, stamped `peer_basis` per row). Changing any of these = re-tuning
  the killed construction: forbidden.
- Rows: `era == "forward"` only. `gap`/`backfill` rows are never evidence.
- Side: `side == "down"` only.
- Filing arm: `edgar_covered == True` and `family == "no-filing"` (the
  sighted arm). `filing-coverage-unknown` rows are excluded — the no-news
  property is unknowable there.
- Episode unit: `first_in_5 == True` for R4-A; `first_in_21 == True` for
  R4-B (per-horizon honest-N, masterplan §5).
- Arm assignment requires a non-null, ledger-stamped `vix_pctile` (§3).
- Endpoint maturity is literal: A and B1 use finite `fwd5` and `fwd21`,
  respectively; B2 uses non-null `terminal_state_21d`. Calendar-censored rows
  are not silently treated as outcomes and do not count toward the relevant
  floor.
- Delisted/halted terminals stay in the B2 denominator at
  `DELISTED_OR_HALTED` (§12 discipline), which is not `RECOVERED_21D`. A dead
  row with no finite `fwd21` is excluded from B1 only; that missing count and
  rate are printed by arm, with no imputation, while B2 retains the row as a
  non-recovery.

## §3 Conditioning variable (frozen)

- Frozen field: the row's immutable identity-block `vix_pctile`, stamped at t0
  by `engine.price_pressure.context.vix_percentile` from
  `data/fred/VIXCLS.parquet` (FRED VIXCLS). Grading **must not** reread, revise,
  forward-fill, or recompute historical VIX; the stored t0 value decides the
  arm forever.
- Transform provenance: trailing-252-session percentile rank of the t0 close,
  inclusive of t0. The shipped producer permits 60 observations during
  warm-up while the sighting used 120; every eligible forward row begins after
  a full 252-observation history, where those transforms are identical. A
  future producer or history change that breaks this parity requires a new
  registration, not a remap of accrued rows.
- Arms: **CALM = pct < 0.5**; **STRESSED = pct ≥ 0.8**. The middle band
  (0.5 ≤ pct < 0.8) enters no test; it is printed descriptively with the
  grading. These are the sighting's own direct-test cells, now frozen.
- PIT: the stamp uses closes through t0 — the same close the shock itself is
  measured on — and forward/gap rows are immutable. A null stamp excludes the
  row and is printed as missing; later FRED availability cannot backfill it
  into an evidence arm.

## §4 Inference (frozen)

For each endpoint, sort event dates ascending and collapse eligible rows to one
observation per event date:
the date's mean residual return for A/B1 and the date's `RECOVERED_21D` share
for B2. The point estimate is the STRESSED date-series mean minus the CALM
date-series mean. Dates, not name-days, are the inference units; the two arms
are date-disjoint because a date has one VIX stamp.

The 95% CI is a percentile CI of the **difference itself**, frozen as 4,000
replicates of the LSR circular date-block bootstrap with block length 5 and
a fresh `numpy.random.default_rng(7)` for each endpoint. Within each replicate,
draw the CALM arm's circular blocks first and the STRESSED arm's blocks second
from the same RNG stream, truncate each resample to its original arm-date
count, and subtract the two resampled means. Report the 2.5th/97.5th
percentiles. This is not the source reopener's approximate subtraction of two
arm CIs; the direct bootstrap-difference is prospectively frozen here before
forward evidence.

The stated direction is one-sided, but passage deliberately requires the
more conservative two-sided 95% interval to sit wholly above zero. An interval
wholly below zero grades the claim FAILED; an interval spanning zero grades it
INCONCLUSIVE. R4-B is an intersection-union gate: **both** B1 and B2 must pass;
there is no best-of-two endpoint selection.

## §5 Floors and discipline (per masterplan §7)

- Each arm of each endpoint: ≥ 200 **endpoint-complete** forward episodes
  across ≥ 40 distinct event dates before that endpoint may be graded. A uses
  finite `fwd5`; B1 uses finite `fwd21`; B2 uses a non-null 21d terminal. The
  A and B floors are separate because their `first_in_h` filters differ; B is
  not graded until both B1 and B2 clear both-arm floors.
- No interim outcome or significance peeking. Only eligibility/maturity counts
  may be checked while accruing. Each claim is graded once, in the first
  session after its complete floors clear, and its result is then appended.
- No re-binning, re-horizoning, re-siding, or era-mixing at grading time —
  any of those is the LSR re-tuning shape and voids the registration.
- An opus `reviewer` adversarial pass on the exact claim text and the graded
  numbers is required before ANY surface change (masterplan §7 clause 4).
- The grading script is written at grading time to implement THIS document
  literally, with no free parameters, and is committed alongside the results.
  It must print eligible, endpoint-complete, null-VIX, dead/truncated, and
  distinct-date counts by arm before printing any claim verdict.

## §6 Consequence matrix (what grading changes)

- **A pass ∧ B pass** → the base-rate artifact gains the VIX axis and the
  band may carry one comparative sentence (plain words, e.g. "in stressed
  tape, more of these came back"). Display tier still — ranking, sizing, or
  gating is not authorized by this registration.
- **A pass ∧ B does not pass** (FAILED, INCONCLUSIVE, or still UNGRADED) →
  completed results are printed on the Calibration Lab; no band sentence. If
  B fails or is inconclusive, say the decision-horizon confirmation did not
  clear; if B is ungraded, print its accrual clock without an outcome claim.
- **A does not pass** (FAILED or INCONCLUSIVE) → null printed
  (nulls-printed law); the VIX axis ships as
  context-only, no comparative language anywhere. B is still graded and
  printed when its floors clear, but **B alone never promotes**: a 21d effect
  with no 5d mechanism contradicts the sighting that motivated this prereg
  and reads as noise until re-registered from scratch.

**Authority invariant, regardless of every outcome:** DRL remains
`display_only=true`; `can_rank`, `can_size`, `can_gate`,
`can_originate_signal`, and `can_escalate` all remain false. This prereg can at
most unlock the one display-tier comparative sentence above. It cannot create
a score, candidate, entry/exit rule, portfolio input, Prophet admission, or
Neural Web authority.

## §7 Clock (honest)

The exact registration parent (`c319e22a149`) carries 35,677 ledger rows, all
`era="backfill"`, with maximum event date 2026-07-02: **zero forward or gap
rows existed when this text froze**. Its committed VIXCLS store ends
2026-08-06 at 15.15, trailing percentile 0.1071 (CALM). These are chronology
receipts, not evidence and not a forecast of the next regime.

The STRESSED arm accrues only on forward event dates whose immutable percentile
stamp is ≥ 0.8. Earliest plausible grading is therefore unknown — the calm arm
may clear its floors in months while the stressed arm waits years for a regime.
Check maturity floors each DRL session without reading outcomes
(`research/DRL_CONTINUATION_HANDOFF_2026-08-10.md` queue); do not grade
early, do not substitute eras.

## §8 Grading log (append-only)

*(empty — no grading has occurred)*

## §9 Registration audit amendment (2026-08-10, pre-merge/pre-evidence)

The branch's initial public commit preceded this audit but never merged and
preceded the first eligible 2026-08-11 session. The audit read no forward
outcomes (none existed) and changed no hypothesis, arm breakpoint, side,
filing family, horizon, direction, numeric floor, or consequence. It made four
execution-critical repairs before registration became canonical:

1. corrected the nonexistent terminal enum `RECOVERED` to the shipped
   `RECOVERED_21D`;
2. bound arm assignment to immutable t0 `vix_pctile` stamps instead of a
   grading-time FRED recomputation;
3. froze the bootstrap-difference algorithm and endpoint-complete floors; and
4. made dead/missing denominators and the permanent no-authority fence
   explicit.
