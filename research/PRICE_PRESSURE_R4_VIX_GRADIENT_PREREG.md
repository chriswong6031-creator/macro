# PRICE PRESSURE — R4 VIX-liquidity gradient pre-registration

Registered: 2026-08-10 (DRL session 2; rev 2 same day — 10 red-team blockers
folded before first merge, see §0.3). Status: **REGISTERED — UNGRADED. Zero
evidence rows exist** (the forward era begins with the 2026-08-11 session).
Program: `research/DISLOCATION_RECOVERY_LOBE_MASTERPLAN_BY_FABLE.md` §8 leg 1;
gate law §7. Kill-scope authority: DNR:KILL-LIQUIDITY-SHOCK-REVERSAL-CLASSIFIER
(whose own text carves out this claim: "needs its own prereg with frozen
breakpoints — it does NOT revive the classifier") and
DNR:KILL-ABSOLUTE-VIX-THRESHOLDS (absolute VIX anchors are non-stationary —
this prereg therefore uses the trailing-percentile transform, with the
level-vs-percentile weakness disclosed in §7).

**One claim gates (R4-A, h=5). Everything else in this document is
descriptive and can never promote anything.** This document is the registry
for the claim; grading results are appended to §8, never rewritten.

## §0 Provenance — every prior look at this data, disclosed

This is **not** a no-peek registration. Three in-sample looks exist and are
disclosed; the forward era (`era=="forward"`, sessions 2026-08-11 onward) is
disjoint from all of them, so grading on forward rows only is a true
out-of-sample confirmation.

**§0.1 The sighting (2026-08-05).** LSR-P0's reopener pass
(`scripts/research_lsr_reopeners.py`, report
`research/LIQUIDITY_SHOCK_REVERSAL_PHASE0.md` §7) computed a VIX-conditioned
cut on the 2021-09→2026-07 panel: the **no-news down arm** ran −0.599%
(calm) → −0.312% → +0.261% (stressed) resid at h=5 across VIX terciles, and
the direct difference test on calm (pct < 0.5) vs stressed (pct ≥ 0.8) gave
calm − stressed = **−0.860% [−1.575, −0.145]** — excluding zero at 1 of 3
horizons (h ∈ {3, 5, 10}; h=21 was NOT tested), with post-hoc breakpoints, on
an arm mean. The stressed bucket's median VIX was **24.5**. The kill row
logged it as "ONE LEAD LOGGED, NOT CLAIMED."

**§0.2 Theory.** Nagel (2012), "Evaporating Liquidity": compensation for
liquidity provision scales with the VIX **level**. Note the tension §7
returns to: the frozen conditioning below is a trailing *percentile*, which
is not the level.

**§0.3 The red-team measurements (2026-08-10).** The pre-freeze adversarial
pass measured, on the backfill ledger in the exact registered cell
(`side=="down"`, `family=="no-filing"`, `edgar_covered`, date-weighted arms):

- h=5: calm −0.380% (478 dates) vs stressed +0.337% (214 dates), Δ =
  **+0.717%, normal-approx CI [+0.039, +1.395]** — consistent with §0.1;
- h=21: Δ = **+0.719%, CI [−0.572, +2.009] — does NOT exclude zero
  in-sample**. This is why R4-B below is registered descriptive-only: a
  claim already weak on ~700 in-sample dates cannot honestly be given a
  forward gate it would need ~decades to power (measured MDE at the §7-law
  minimum floors: 4.9× the effect);
- stressed-arm structure: the 268 stressed sessions of the backfill span
  form only **36 contiguous runs** (longest 30 sessions) — the clustering
  unit §4/§5 must respect;
- `vix_pctile ≥ 0.8` marks **27.1%** of backfill event rows — the arm is
  common, not rare, at every absolute vol level (2017's ≥0.8 bucket had
  median VIX **15.55**).

All three looks are disclosure, never evidence. The registered constructions
below are imported from §0.1 and frozen ex ante for the forward test — not
chosen post hoc a second time.

## §1 Claims

Direction convention: `fwd{h}` is the ledger's stamped h-session forward
residual log-return. For down-side events, continuation is negative;
"continuation weakens" means the stressed-arm mean is HIGHER (less negative).
**Estimand weighting (frozen): every arm mean is the mean over event dates of
the within-date mean** — the house date-weighted unit (`date_block_ci`
docstring: "the unit is the trading date, never the name-day"), which is also
what the sighting's `_arm()` computed.

- **R4-A (GATING — mechanism replication, h=5).** Among eligible down-side
  forward episodes (§2), Δ_A = datemean(fwd5 | STRESSED) −
  datemean(fwd5 | CALM) > 0, with the 95% two-arm bootstrap CI of §4
  excluding zero. An interval excluding zero in the wrong direction grades
  the claim FAILED, not inconclusive. R4-A is the **only** test in this
  registration; there is no multiplicity to control at the gate.
- **R4-B (DESCRIPTIVE ONLY — product horizon, h=21).** Printed at R4-A's
  grading, gates nothing, promotes nothing, ever: Δ_B1 = the same difference
  on `fwd21`; Δ_B2 = share(`terminal_state_21d == "RECOVERED_21D"` |
  STRESSED) − share(… | CALM) (note the ledger suffixes every terminal with
  `_{h}D` except the unsuffixed `DELISTED_OR_HALTED`). h=21 is an unsighted
  extrapolation (§0.1) already weak in-sample (§0.3). For 21d recovery
  language ever to carry a comparative VIX claim, a NEW registration with its
  own power analysis is required.

## §2 Evidence cells (construction imported, not tunable)

- Detector, fence, thresholds, horizons, peer basis: exactly the shipped
  `engine/price_pressure/` detector (z ≥ 3, 2× volume, $5/$5M-ADV, stamped
  `peer_basis` per row). Changing any of these = re-tuning the killed
  construction: forbidden.
- Rows: `era == "forward"` only. `gap`/`backfill` rows are never evidence.
- Side: `side == "down"` only.
- Filing arm: `edgar_covered == True` and `family == "no-filing"` (the
  sighted arm — the reopener's `cov_earn8k ∧ ~news` cell).
  `filing-coverage-unknown` rows are excluded: the no-news property is
  unknowable there.
- Episode unit: `first_in_5 == True` for R4-A; `first_in_21 == True` for
  R4-B (per-horizon honest-N, masterplan §5).
- **Maturity (frozen):** a row enters a statistic only when its window has
  fully elapsed by the grading asof — `fwd5` non-null for R4-A; for R4-B,
  21 sessions elapsed OR `terminal_state_21d == "DELISTED_OR_HALTED"`.
  Harvested-but-unmatured rows are excluded by CALENDAR (not by outcome — no
  resolution-conditioned denominator) and their per-arm count is printed.
  **Floors in §5 count matured rows only.**
- **Dead-tape scoping:** "delistings stay in denominators" binds Δ_B2
  (DELISTED_OR_HALTED is a non-RECOVERED terminal). It CANNOT bind the mean
  statistics — a dead tape leaves `fwd{h}` NaN (`ledger.py` truncation) and
  such rows drop from Δ_A/Δ_B1 mechanically. Grading prints the per-arm
  dead-tape drop count so that survivorship conditioning is disclosed.

## §3 Conditioning variable (frozen)

- **The estimand** is the trailing 252-session percentile of the FRED VIXCLS
  close at t0, computed by the shipped transform
  (`engine/price_pressure/context.py::vix_percentile`): series `.dropna()`,
  de-duplicated index (`keep="last"`), sorted, then
  `rolling(252, min_periods=60).rank(pct=True)` — inclusive of t0. (The
  sighting used `min_periods=120`; the two differ only inside the first 120
  observations of the series, i.e. no date after ~1991 — equivalent here.)
- **At grading**, the value is recomputed deterministically from
  `data/fred/VIXCLS.parquet` as of the grading session and mapped to t0,
  **ffilled at most 3 sessions** (a t0 more than 3 sessions past the last
  VIXCLS observation grades NULL and is excluded, count printed per arm).
- **The ledger's stamped `vix_pctile`** (an identity column, frozen at
  harvest) is the tripwire, not the estimand: FRED publishes with a lag, so
  a forward row harvested on its own night typically stamps NULL there —
  a known limitation, not an error. Wherever the stamped value is non-null,
  the recomputed value must match it; a mismatch rate above 1% of non-null
  rows ABORTS grading for investigation.
- Arms: **CALM = pct < 0.5**; **STRESSED = pct ≥ 0.8** — the sighting's own
  direct-test cells, now frozen. The middle band (0.5 ≤ pct < 0.8) enters no
  test and is printed descriptively.
- PIT: the percentile uses closes through t0 — the same close the shock
  itself is measured on. Recomputing it later from the archival series is
  reconstruction of a t0-known value, not lookahead; VIX closes are not
  materially revised.

## §4 Inference (frozen — the two-arm estimator, written out)

The house `date_block_ci` is one-sample; the sighting combined two of them
with a normal approximation. Neither is registered here. The grading script
implements exactly this:

1. Per arm, reduce to the per-date series: for each event date, the mean of
   `fwd{h}` over that date's eligible episodes (§2).
2. **Calm arm resampling:** circular blocks of **5 consecutive entries** of
   the arm's date-ordered series, drawn with replacement to the observed
   length (the `date_block_ci` mechanic).
3. **Stressed arm resampling:** at the **regime-run level**. Runs = maximal
   groups of stressed event dates where consecutive dates are ≤ **10
   sessions** apart. Resample runs with replacement to the observed run
   count; a replicate's arm mean is the date-weighted mean over the drawn
   runs' dates. (Stress arrives in long runs — §0.3: 268 sessions in 36
   runs — so 5-date blocks under-count the clustering;
   cf. the masterplan §7's own episode→date recursion, one level up.)
4. Per replicate, draw both arms independently and record Δ* = stressedmean*
   − calmmean*. **B = 4000 replicates, seed = 7.** Arms are non-empty in
   every replicate by construction (resample counts equal observed counts).
5. CI = the 2.5th/97.5th percentiles of Δ*. Gate: CI excludes zero in the
   registered direction.

Arms are date-disjoint by construction (a date has one percentile), so
independent per-arm resampling is coherent.

## §5 Floors and discipline

Floors are POWER-BASED, not the §7-law minimum (which is subsumed and would
have engineered a false null — §0.3: at 40 dates/arm the MDE is 2.4× the
sighted effect). All floors count **matured** rows (§2):

- STRESSED arm: ≥ **240** event dates, across ≥ **8 distinct regime runs**
  (§4's run definition), and ≥ 200 episodes.
- CALM arm: ≥ **480** event dates and ≥ 200 episodes.
- Power basis, disclosed: at the in-sample date-level variances (§0.3), 240
  stressed dates gives roughly 80% one-sided power at α=0.05 against the
  sighted +0.86%; against the registered-cell backfill point (+0.72%) power
  is ~65–70% — accepted and stated so a marginal miss is read honestly.
- No interim significance peeking; grading happens once, in the session
  where floors first clear. No re-binning, re-horizoning, re-siding, or
  era-mixing at grading time — any of those is the LSR re-tuning shape and
  voids the registration.
- An opus `reviewer` adversarial pass on the exact claim text and graded
  numbers is required before ANY surface change (masterplan §7 clause 4).
- The grading script is written at grading time to implement this document
  with **no free parameters** — every constant it needs is registered here:
  transform + cutpoints (§3), ffill cap 3 (§3), mismatch-abort 1% (§3), run
  gap 10 / block 5 / B 4000 / seed 7 (§4), floors 240/480/8/200 (§5),
  maturity + drop-count prints (§2), per-arm realized-VIX prints (§7).
- Mandatory prints at grading: per-arm realized median VIX and absolute-VIX
  quartiles (§7's percentile-vs-level check), per-arm dead-tape drops and
  unmatured exclusions (§2), ffill-cap exclusions (§3), middle-band
  descriptives, and both R4-B descriptives.

## §6 Consequence matrix

- **R4-A PASS** → the base-rate artifact may gain the VIX axis, and the band
  may carry ONE plain-word comparative sentence **scoped to the first week**
  (the tested horizon — e.g. "in stressed tape, these steadied sooner that
  first week"; final wording through the design-law lane). Display tier
  still — ranking, sizing, or gating anywhere requires a further full §7
  trip. Nothing at 21d gains comparative language regardless of what R4-B's
  descriptives show.
- **R4-A FAIL** → the null is printed on the Calibration Lab (nulls-printed
  law); the VIX axis ships as context-only with no comparative language
  anywhere. R4-B descriptives are still printed when matured.
- **Lapse clause:** if the floors have not cleared by **2036-12-31**, or the
  upstream detector construction changes, or VIXCLS is discontinued, this
  registration lapses and the claim requires fresh registration. An
  ungraded registration confers nothing while open.

## §7 Clock and the percentile-vs-level weakness (honest)

- The trailing percentile marks ~20% of sessions stressed **by
  construction, at any absolute vol level** — 27.1% of backfill event rows
  sit ≥ 0.8, and 2017's stressed bucket had median VIX 15.55 vs the
  sighting's 24.5 (§0.3). The arm measures *relative* vol position; Nagel's
  mechanism is about the *level*. This is a registered weakness, not a
  surprise to be discovered at grading: the §5 mandatory prints exist so the
  grading reviewer can judge whether the forward stressed arm was
  vol-comparable to the sighting's, and say so in the graded record.
- Accrual, measured on the backfill era: the stressed cell gathered ~167
  episodes across ~44 event dates per year. At that rate the 240-date
  stressed floor clears in ≈ **5.5 years** (~2032); the calm floor sooner.
  The substrate accrues nightly regardless — that is the program's design.
  Check floors each DRL session; never grade early.
- Store state at registration: `data/fred/VIXCLS.parquet` last observation
  **15.15 on 2026-08-06** (the store, not a quote — cite what a grader can
  reproduce).

## §8 Grading log (append-only)

*(empty — no grading has occurred)*
