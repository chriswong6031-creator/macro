# PRICE PRESSURE — R4 VIX-liquidity gradient pre-registration

Registered: 2026-08-10 (DRL session 2). Status: **REGISTERED — UNGRADED. Zero
evidence rows exist** (evidence eligibility begins with the 2026-08-11
session — §10.6).
Program: `research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md` §8 leg 1;
gate law §7. Kill-scope authority: DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER
(whose own text carves out this claim: "needs its own prereg with frozen
breakpoints — it does NOT revive the classifier") and
DNR:KILL-ABSOLUTE-VIX-THRESHOLDS (absolute VIX anchors are non-stationary —
this prereg therefore uses the trailing-percentile transform, not levels).

This document is the registry for the claim. Grading results are appended
here, never rewritten. A pre-merge, pre-evidence audit amendment is recorded
in §9; it fixed an enum typo and closed PIT, inference, and maturity degrees of
freedom before the first eligible forward session. A second pre-evidence
amendment (§10, hours later, same no-outcome window) folded an independent
red-team pass's **measured** repairs: the VIXCLS stamp-lag completion rule,
the stressed-arm clustering unit, power-based floors, R4-B's demotion to
descriptive-only, and the explicit evidence-eligibility boundary.

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
evidence set (`era=="forward"` rows with event date ≥ 2026-08-11, the
registered eligibility boundary — §10.6) is
disjoint from every date the sighting touched, so grading on evidence rows only
is a true out-of-sample confirmation. It is not an exact replication sample:
the forward ledger additionally applies the program's per-horizon episode
deduplication (`first_in_h`). The breakpoints below are **imported from the
sighting and frozen ex ante for the forward test** — they are not chosen post
hoc a second time.

**Second disclosure (2026-08-11, the §10 red-team pass).** Before the §10
amendment froze, an adversarial pass measured, on the backfill/gap ledger in
the exact registered cell (down side, `no-filing`, `edgar_covered`,
date-weighted arms):

- h=5: calm −0.380% (478 dates) vs stressed +0.337% (214 dates), Δ =
  **+0.717%, normal-approx CI [+0.039, +1.395]** — consistent with §0's
  sighting;
- h=21: Δ = **+0.719%, CI [−0.572, +2.009] — does NOT exclude zero
  in-sample** on ~700 dates (and h=21 was never in the sighting's direct
  test, which ran h ∈ {3, 5, 10});
- stressed-arm structure: the backfill span's 268 stressed sessions form only
  **36 contiguous runs** (longest 30);
- `vix_pctile ≥ 0.8` marks **27.1%** of backfill event rows — the arm is
  common at every absolute vol level (2017's ≥0.8 bucket: median VIX 15.55;
  the sighting's stressed bucket: 24.5);
- the VIXCLS store trails the tape by one session at the nightly harvest.

All of it is disclosure, never evidence; every number is backfill-era. These
measurements motivated the §10 repairs and are the reason R4-B cannot
honestly gate (§10.3).

## §1 Frozen claims

Direction convention: `fwd{h}` is the ledger's stamped h-session forward
residual log-return. For down-side events, continuation is negative;
"continuation weakens" means the stressed-arm mean is HIGHER (less negative).

- **R4-A (prospective mechanism confirmation, h=5 — THE gating test).** Among
  eligible down-side
  forward episodes (§2), the mean of the date-level `fwd5` means in the
  STRESSED arm exceeds the corresponding CALM mean: Δ_A = mean_date(fwd5 |
  stressed) − mean_date(fwd5 | calm) > 0, with the 95% bootstrap-difference
  CI of §4 excluding zero. R4-A is the **only** test in this registration
  that can change anything (§10.3); there is no multiplicity at the gate.
- **R4-B (product horizon, h=21 — DESCRIPTIVE ONLY, never gates).** Printed
  at R4-A's grading with the same machinery, promotes nothing, ever:
  Δ_B1 = mean_date(fwd21 | stressed) − mean_date(fwd21 | calm) and Δ_B2 =
  mean_date(share(`terminal_state_21d == "RECOVERED_21D"`)) difference on the
  same cells. h=21 was never in the sighting's direct test (§0: h ∈ {3, 5,
  10}) and measured weak in-sample (§0 second disclosure) — no floors this
  registration could realistically power would detect it (§10.3). For 21d
  recovery language ever to carry a comparative VIX claim, a NEW registration
  with its own power analysis is required.

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
- Arm assignment uses the §3 conditioning value: the non-null ledger stamp,
  else the §3 lag-completion. Rows with neither are excluded and printed.
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
  `data/fred/VIXCLS.parquet` (FRED VIXCLS). A **non-null** stamp decides the
  arm forever: grading must not revise, forward-fill, or re-map it. A
  recompute of the same transform serves only as the consistency tripwire —
  mismatch against more than 1% of non-null stamps aborts grading for
  investigation (§10.1).
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
  measured on — and non-null stamps are immutable. **Lag completion (§10.1):**
  the VIXCLS store trails the tape by one session at the nightly harvest
  (measured — §0 second disclosure), so a forward row typically stamps NULL
  through no property of its own; under §9's exclusion rule both evidence
  arms would have starved to zero forever. A null-at-harvest stamp is
  therefore completed ONCE — null → **t0's own close percentile** under the
  §3 transform on the archival series (an exact late-arriving value, not a
  forward-fill) — only by the first subsequent nightly producer run on which
  t0 appears and only before that row's `fwd5` endpoint matures. That producer
  appends an immutable completion receipt binding the row identity, completed
  percentile, `observed_at`, and exact VIXCLS source-artifact SHA-256. Grading may
  consume that frozen receipt but may never fill or recompute a null stamp at
  grading time. If no receipt exists before `fwd5` maturity, the row is
  excluded forever from both arms and printed as missing. Completed counts are
  printed per arm. Completion never revises a non-null stamp.

## §4 Inference (frozen)

For each endpoint, sort event dates ascending and collapse eligible rows to one
observation per event date:
the date's mean residual return for A/B1 and the date's `RECOVERED_21D` share
for B2. The point estimate is the STRESSED date-series mean minus the CALM
date-series mean. Dates, not name-days, are the inference units; the two arms
are date-disjoint because a date has one VIX stamp.

The 95% CI is a percentile CI of the **difference itself**, frozen as 4,000
replicates with a fresh `numpy.random.default_rng(7)` for each endpoint.
Within each replicate, draw the CALM arm first and the STRESSED arm second
from the same RNG stream:

- **CALM arm:** the LSR circular date-block bootstrap — blocks of 5
  consecutive entries of the date-ordered series, truncated to the original
  arm-date count.
- **STRESSED arm:** resampled at the **regime-run** level (§10.2). Runs =
  maximal groups of stressed event dates whose consecutive gaps are ≤ 10
  sessions; draw runs with replacement to the observed run count, each drawn
  run contributing all of its dates. (Measured: the backfill span's 268
  stressed sessions form only 36 runs — 5-date blocks under-count that
  clustering and narrow the CI exactly where a false PASS would promote.)

Subtract the two resampled date-series means and report the 2.5th/97.5th
percentiles. This is not the source reopener's approximate subtraction of two
arm CIs; the direct bootstrap-difference is prospectively frozen here before
forward evidence.

R4-A's stated direction is one-sided, but its passage deliberately requires
the more conservative two-sided 95% interval to sit wholly above zero. For
R4-A only, an interval wholly below zero grades R4-A FAILED; an interval
spanning zero grades it INCONCLUSIVE. R4-B's endpoints are estimated with the
same bootstrap machinery and printed only alongside R4-A's one grading, but no
R4-B interval maps to PASS, FAIL, or INCONCLUSIVE; they gate nothing (§1,
§10.3).

## §5 Floors and discipline (per masterplan §7)

- Floors are **POWER-BASED** (§10.3), counted on **endpoint-complete**
  evidence rows (finite `fwd5` for A): STRESSED arm ≥ **320** distinct event
  dates across ≥ **8** distinct regime runs (§4's run definition) and ≥ 200
  episodes; CALM arm ≥ **640** distinct event dates and ≥ 200 episodes.
  Power basis, disclosed: passage requires the two-sided 95% interval in §4
  to sit wholly above zero, so the power calculation uses its corresponding
  one-sided α=0.025 boundary — not α=0.05. At the in-sample date-level
  variances (§0 second disclosure), 320 stressed / 640 calm dates gives
  roughly 82% power against the sighted +0.86%; against the registered-cell
  backfill point (+0.72%) power is ~67% — accepted and stated so a marginal
  miss is read honestly. (The masterplan-§7 minimum of 200 episodes / 40
  dates is subsumed; grading at that minimum would have been a scheduled
  INCONCLUSIVE at an MDE 2.4× the sighted effect.) R4-B's descriptives print
  whenever R4-A grades, on whatever endpoint-complete rows exist then; they
  carry no floors of their own because they gate nothing.
- No interim outcome or significance peeking. Only eligibility/maturity counts
  may be checked while accruing. R4-A is graded once, in the first session
  after its complete floors clear, and its result is then appended. R4-B is
  merely computed and printed at that same grading; it receives no verdict and
  is never graded separately.
- No re-binning, re-horizoning, re-siding, or era-mixing at grading time —
  any of those is the LSR re-tuning shape and voids the registration.
- An opus `reviewer` adversarial pass on the exact claim text and the graded
  numbers is required before ANY surface change (masterplan §7 clause 4).
- The grading script is written at grading time to implement THIS document
  literally, with no free parameters, and is committed alongside the results.
  It must print eligible, endpoint-complete, null-VIX, lag-completed
  (§10.1), dead/truncated, distinct-date, and distinct-run counts by arm,
  plus per-arm realized **median VIX and VIX quartiles** (§10.4's
  percentile-vs-level check), middle-band descriptives, and both R4-B
  descriptives, before printing any claim verdict.

## §6 Consequence matrix (what grading changes)

- **R4-A PASS** → the base-rate artifact may gain the VIX axis, and the band
  may carry ONE plain-word comparative sentence **scoped to the tested first
  week** (e.g. "in stressed tape, these steadied sooner that first week";
  final wording through the design-law lane). Display tier still — ranking,
  sizing, or gating is not authorized by this registration. Nothing at 21d
  gains comparative language regardless of what R4-B's descriptives show
  (§10.3); a fresh registration is the only path to that sentence.
- **R4-A FAILED or INCONCLUSIVE** → the completed result is printed on the
  Calibration Lab (nulls-printed law); the VIX axis ships as context-only,
  no comparative language anywhere. R4-B's descriptives print alongside,
  labeled descriptive.
- **Lapse:** if R4-A's floors have not cleared by **2036-12-31**, or the
  upstream detector construction changes, or FRED VIXCLS is discontinued,
  this registration lapses; the claim then requires fresh registration. An
  open ungraded registration confers nothing.

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

The STRESSED arm accrues on evidence dates stamped (or §10.1-completed) at
percentile ≥ 0.8 — which the trailing transform marks on ~20% of sessions
**at any absolute vol level** (§10.4): it is a relative-position arm, not a
vol-level arm, and 2017's ≥0.8 bucket had median VIX 15.55 vs the sighting's
24.5. That weakness is registered here, not discovered at grading — the §5
realized-VIX prints exist so the mandatory reviewer pass can judge whether
the forward stressed arm was vol-comparable to the sighting's, and say so in
the graded record. Accrual measured on the backfill era: ~167 stressed
episodes across ~44 stressed event dates per year, so the 320-date stressed
floor clears in ≈ **7.3 years (~2034)** at those rates; the calm floor
sooner. Check maturity floors each DRL session without reading outcomes
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

## §10 Second audit amendment (2026-08-11, pre-evidence — measured repairs)

A second, independent adversarial pass (opus, commissioned by the registering
session; it raced §9's audit and merged second) measured the registered
construction against the backfill ledger and the VIXCLS store — its numbers
are §0's second disclosure. It endorsed §9's repairs 1, 3 and 4, and found
three defects that survived §9 (one introduced by it), plus two gaps. The
repairs, folded into §§0–7 above:

1. **Stamp-lag completion (§2, §3).** §9's repair 2 bound arms to the
   harvest-night stamp and excluded null stamps forever — but the VIXCLS
   store trails the tape by one session at the 22:30Z harvest (measured:
   store last observation 2026-08-06 while 2026-08-07 had already traded),
   so forward rows typically stamp NULL and **both evidence arms would have
   starved to zero permanently** — an ungradeable registration by
   construction. Non-null stamps stay immutable and decide the arm; a
   null-at-harvest stamp is completed once (null → t0's own close
   percentile, an exact late-arriving value, never a forward-fill, never a
   revision of a non-null) by the first subsequent nightly on which t0 is
   available and before `fwd5` maturity. The producer appends an immutable
   row/value/`observed_at`/source-artifact-SHA-256 receipt; grading consumes that
   receipt and is forbidden to complete stamps itself. A row without a timely
   receipt is missing forever. The recompute doubles as §3's 1% consistency
   tripwire on non-null stamps.
2. **Stressed-arm clustering unit (§4).** The backfill span's 268 stressed
   sessions form 36 contiguous regime runs; 5-date circular blocks
   under-count that dependence and narrow the CI exactly where a false PASS
   would promote a sentence. The stressed arm now resamples whole regime
   runs (gap ≤ 10 sessions); the calm arm keeps §9's 5-date blocks; B=4,000
   and `default_rng(7)` unchanged.
3. **Power floors; R4-B demoted to descriptive (§1, §5, §6).** At the prior
   200-episode/40-date floors the MDE is 2.4× (h=5) and 4.9× (h=21) the
   sighted effect — under §5's grade-once rule, a scheduled INCONCLUSIVE
   that would have closed the claim unread. Because passage requires a
   two-sided 95% CI wholly above zero, floors are now 320 stressed dates
   across ≥ 8 runs / 640 calm dates (~82% power at the corresponding
   one-sided α=0.025 boundary vs the sighted +0.86%). R4-B measured weak
   in-sample (Δ_B1 +0.719%, CI [−0.572,
   +2.009] on ~700 dates) at a horizon the sighting never tested; no
   registerable floor powers it, so it is estimated and printed without a
   PASS/FAIL verdict and can never gate; the A-pass surface sentence is scoped
   to the tested first week.
4. **Percentile-vs-level weakness registered (§7).** The ≥ 0.8 arm marks
   ~20% of sessions at ANY absolute vol level (27.1% of backfill event
   rows; 2017 median VIX 15.55 in that bucket vs the sighting's 24.5), and
   accrues ~44 stressed event dates/yr — §9's §7 text ("waits years for a
   regime") had the mechanism backwards. Grading prints per-arm realized
   VIX so the mandatory reviewer pass can judge vol-comparability.
5. **Lapse clause (§6).** 2036-12-31, construction change, or VIXCLS
   discontinuation lapses the registration.
6. **Evidence-eligibility boundary (§0, header).** `ledger.py` stamps
   `era="forward"` for rows dated the harvest's own asof session; the first
   post-merge nightly (in flight as this amendment froze) has asof
   **2026-08-10**, so the era's first rows are dated 2026-08-10 — not
   2026-08-11 as §0/§9 assumed. The registered boundary stands as written:
   **evidence = `era=="forward"` AND event date ≥ 2026-08-11**; any
   2026-08-10 forward rows are excluded and printed. Disjointness from the
   sighting's panel (ends 2026-07-02) is unaffected.

Like §9: no forward outcome was read — none exists; the first `fwd5` of any
evidence row cannot exist before ~2026-08-18. Hypothesis, arm breakpoints,
side, filing family, direction, and R4-A's horizon are unchanged. Changed
with measurement: the null-stamp rule, the stressed clustering unit, the
floors, R4-B's role, and the eligibility boundary — each before the first
eligible session's rows existed. Base receipt: amended from main
`7795827d348` (§9's merged text), zero forward rows on main at freeze.
