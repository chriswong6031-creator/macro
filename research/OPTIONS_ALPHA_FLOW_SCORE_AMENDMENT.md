# Options-Alpha Flow-Score Registration Amendment (FS-3 ML-gauntlet prereg)

**Status: DRAFTED by Opus 2026-07-13 (FLOW_SIGNAL_ML_MASTERPLAN wave FS-3) — awaiting Fable
ratification.** Registers, for the FIRST time, the DTE-bucketed flow-score constructions and
their pre-registered ML-gauntlet before any trainer code exists (FS-R8: registration before
computation). Until Fable ratifies this amendment, no FS-4 trainer may run and no score field
may be written to any ledger or surface.

Parent program doc: `research/FLOW_SIGNAL_ML_MASTERPLAN_BY_FABLE.md` (rulings FS-R1…FS-R12).
Registry host (per FS-R8 / RO-12): `research/OPTIONS_ALPHA_MASTERPLAN.md` §4 — this amendment
adds rows and enlarges that program's BH-FDR family. Era-grid precedent:
`research/OPTIONS_ALPHA_ERA_PARTITION_AMENDMENT.md`. Field-guide basis (rulers derive from it):
`research/FLOW_SIGNAL_FIELD_GUIDE.md` (FS-2), cited by table letter throughout.

---

## §0 In plain English

We are about to build a machine that reads each qualifying options-flow event and prints one
honest sentence: *"Of the N historically similar flow events (same DTE band, same detector
construction, same era), X% preceded a move of the size we care about in the underlying stock
within H days — with a confidence interval, and stated relative to the market."* Before writing
one line of that machine, this document freezes exactly what it is allowed to claim, on which
data, scored against which yardsticks, and under what statistical accounting — so that no result
it later produces can be a goalpost moved after the fact.

Three things make this registration honest rather than a rubber stamp:

1. **We only register verdict cells we can actually fill from the right data.** Our long
   historical proxy cohort (`eod_proxy`, 2012→) is training-priors only; it never yields a
   published verdict, because it is reconstructed pseudo-events, not the live serving
   distribution (FS-R4). The only cohorts that can produce a verdict are the ones that look
   like what we serve at inference: the live event feed (`live_feed`, accruing 2026→) and the
   per-trade tape reconstruction (`tape_recon`, today SPY 2022-2023, accruing). So we register
   verdict cells only in the eras those cohorts populate — not a sprawling 2012→ grid that would
   book cells no legal cohort can ever fill.

2. **The score is a filter on events the detector already fired — never an originator.** It can
   down-weight or de-escalate a detected event; it can never invent a signal, a direction, or a
   trade (FS-R7). Pre-gate it touches nothing that ranks, sizes, or gates anything — it is a
   labeled display probability with its conditioning stated (FS-R3).

3. **The score target is deliberately modest about direction.** Today's outcome grader measures
   an *unsigned* underlying move (did the stock move, not did-the-call's-thesis-pay); signed,
   right-conditioned (call vs put) discrimination is a documented deferral in the field guide
   (Table E, §6 accrual list). So the calibrated score estimates the probability of an
   underlying-move outcome as the grader currently defines it — we do not dress it up as a signed
   directional probability we have not earned.

The count that matters, stated up front so the FDR section below is auditable: this amendment
adds **8 registered test cells** to the options-alpha family, taking it from **28 → 36 tests**
under Benjamini-Hochberg FDR at α = 0.10. The enumeration is in §6.

---

## §1 What is registered (and what is deferred)

**Registered here (frozen on Fable ratification):**

- Three flow-score constructions, one per FS-R5 DTE bucket: **S-FLOWML-0_7**, **S-FLOWML-8_90**,
  **S-FLOWML-90P** (§2, §4-registry rows appended to OPTIONS_ALPHA §4).
- The target variable and estimated probability for each bucket (§2), anchored to the FS-R2
  outcome rulers, with the unsigned-outcome basis stated explicitly.
- The training/cohort/population spec: cohort roles (FS-R4), frozen `detector_version`, feature
  legality (FS-R9), and the Table-H index-root prefilter written into the population definition
  (§3).
- The cross-validation geometry: purged K-fold, embargo ≥ label horizon per bucket, group folds
  by underlying AND time block, CPCV for model selection, uniqueness weights (§4-CV).
- The calibration criteria: per-bucket isotonic on a temporal holdout, ECE < 0.05 per bucket,
  Brier-vs-base-rate, reliability monotonicity (§5).
- The enlarged BH-FDR family arithmetic: the 8 added cells enumerated, the new total (36), the
  recompute obligation, and the amend-on-add re-check clause (§6).
- N floors and ERA-SPARSE handling (§7).
- The pre-registered kill criteria (§8).
- The shadow / promotion path and the display-only-until-gate discipline (§9).

**Explicitly deferred — NOT registered here, requires its own future amendment:**

- Signed / right-conditioned (call vs put) directional score (field guide Table E + §6): a
  different target variable; registered only when the right-conditioned grader column exists.
- Moneyness-stratified ("deep-OTM binary move-to-strike") rulers (field guide §2.5, Table G):
  `mny_bucket` is `'unknown'` in both cohorts today; registered when the close-price moneyness
  join lands.
- Repeat-cluster and cross-session accumulation cells (Table F is empty in the current
  tape_recon sweep): registered when tier-3 single-name tape populates them.
- Any promotion of the score to a rank/size/gate lever: that is FS-5, gate-governed, and needs
  the gate to pass first (§9, §10).

---

## §2 Score definition per DTE bucket

### §2.1 The constructions and their target rulers (FS-R5 buckets, FS-R2 rulers)

FS-R5 routes by DTE into three constructions. The middle band is a **single model with a DTE
interaction term**, not two models — the volume-weighted-pragmatism ruling — so it is one
construction, not several. The extremes are separate models.

| Construction | DTE band (FS-R5) | Primary outcome ruler (FS-R2) | Secondary ruler |
|---|---|---|---|
| **S-FLOWML-0_7** | 0–7 DTE (0DTE index excluded, §3.3) | forward **5-day** underlying move | — |
| **S-FLOWML-8_90** | 8–90 DTE, single model + DTE-interaction | forward **21-day** underlying move | — |
| **S-FLOWML-90P** | 90+ DTE | forward **63-day** underlying move (primary) | forward **126-day** (secondary; rides alongside — the long bucket's thesis window can exceed 63d, FS-R2) |

Every ruler is reported in **two forms — absolute AND excess-vs-SPY** (FS-R2). The **decision
ruler is excess-vs-SPY**: the field guide's Table H secondary finding and Table J show the
absolute-return gradient is largely market drift (SPY-excess is flat across premium deciles;
index buckets' higher absolute hit rate reflects benchmark drift, not flag alpha). The absolute
form is reported for transparency alongside; it is **not** a separately counted FDR cell (§6) —
counting both forms of the same underlying label as independent tests would double-count.

### §2.2 What P(·) the calibrated score estimates

For a detected event *e* in bucket *b*, the calibrated score is:

> **s(e) = P̂( the underlying-move outcome fires on bucket *b*'s primary ruler within its horizon H_b | detector-fired event *e*, its features, its era )**

where "the underlying-move outcome fires" is defined by the **FS-0 grader** — it is whatever the
shared `engine/grading.py` triple-barrier primitives return on the stock at horizon H_b, on the
excess-vs-SPY basis (with the absolute basis reported alongside). The score is a **conditional
probability of a graded outcome**, calibrated so that the printed number equals the empirical
rate (§5). It is **not** a return forecast, an expected-value, or a P&L estimate; the option
premium-touch columns (`prem_touch_50/100`) remain display-only, labeled "path max, not P&L,"
never verdict currency (FS-R2), and are not the score target.

### §2.3 Unsigned-outcome caveat (binding — reviewer attack (c))

The FS-0 grader today measures the underlying move **unsigned** with respect to option side:
field guide Table E states plainly that the at-ask/at-bid execution split is "measured in an
UNSIGNED underlying up-move outcome, pooled over calls and puts (the `right` field is not
conditioned on)… NOT signed directional discrimination." Consequently:

- The score estimates **P(underlying-move outcome as the grader defines it)** — it does **not**
  assert a signed P(stock goes the way the option-buyer's thesis needs). No signed directional
  claim is registered here.
- The grader's outcome basis is the score target's basis. If and when a right-conditioned
  (call/put) grader column is added (field guide §6 unlock), a *new* construction with a signed
  target is registered by amendment — it does not silently replace this one.
- Any surface copy for the score therefore states the outcome in the plain-word form the grader
  supports ("similar flow preceded a move of this size in N of M cases"), never a directional
  "bullish/bearish" verdict — consistent with FS-R6 (direction tone stays soft `~`) and
  DESIGN_DOCTRINE.

---

## §3 Training / cohort / population spec

### §3.1 Cohort roles (FS-R4 — no pooling, ever)

A training cohort is keyed by `(detector_version, source)`. The three sources and their roles:

| Cohort | Coverage today (FS-1 status 2026-07-13) | Role |
|---|---|---|
| `eod_proxy` | 2012-06 → 2026-07, 383-root store (380 event-producing), ~5.66M ok-graded events | **Priors / pre-training ONLY.** Reconstructed pseudo-events; NEVER a calibration set, NEVER a published verdict cell (train/serve mismatch, §1.2 of the masterplan). |
| `tape_recon` | SPY 2022-2023, ~696k events / ~118k ok-graded, accruing (tier-2 ETF 2017→ and tier-3 single-name 2022→ not yet harvested) | **Serving-distribution cohort.** Calibration + OOS verdicts legal here. |
| `live_feed` | Accruing 2026-07→ (FS-0 ledger) | **Serving-distribution cohort.** Calibration + OOS verdicts legal here; the true production distribution. |

**Pooling prohibition:** cohorts are never combined in one training set (FS-R4; field-guide §5
confound #6 — the atlas enforces `_assert_single_source`). `eod_proxy` may seed model priors /
pre-training, but every calibration curve and every published OOS number comes only from
`live_feed` / `tape_recon`. This is the structural reason §6 registers **no verdict cell in the
2012-15 or 2016-19 eras**: no serving-distribution cohort exists there, so a verdict cell there
would be unfillable by any legal cohort (reviewer attack (b)).

### §3.2 Frozen detector

The population is defined by the frozen `config/flow_detector.yml` v1 (FS-0b, shipped
2026-07-13). `detector_version` rides every ledger row; changing any threshold = a new version +
full re-label (config-header law). Cohorts of different `detector_version` are different cohorts
(selection effects poison labels when thresholds drift, §3 masterplan). Training reads a single
frozen `detector_version` per model artifact; the version is recorded in the artifact hash.

### §3.3 The Table-H index-root prefilter (binding population rule — reviewer attack (c))

Field guide **Table H** measures `vol_gt_oi_rate = 1.000` for index instruments (SPX/SPXW/NDX
etc.) across both 0DTE and short-DTE buckets — a **structural artifact** (index contracts start
each session at OI≈0, so any volume trivially flags vol>OI), "structurally inapplicable to index
instruments." The population spec therefore encodes a **registered index-root prefilter**:

- **Index-rooted events are excluded from the scored population by default.** The vol>OI-derived
  qualification and its downstream features are not meaningful on index roots (Table H); an
  index-rooted event does not enter any S-FLOWML-* training or scoring population.
- The **only** admissible re-entry for an index root is behind the field-guide-registered
  **pre-existing-OI > 500 prefilter** (Table H key finding; §5 confound #1): an index-rooted
  event may enter the population only if it clears OI > 500 on the prior session (T-1 OI, PIT).
  This prefilter is registered here as part of the population definition, not left to trainer
  discretion.
- 0DTE index intraday-pressure effects are out of scope entirely (field guide §1.6 / §2.6 — GEX
  stack territory); 0DTE index is excluded from S-FLOWML-0_7.

This makes the Table-H exclusion a *population* rule, verifiable in the registered spec, not a
feature the trainer might silently include.

### §3.4 Feature legality (FS-R9)

Model inputs come only from PIT-clean stores with honest coverage windows. Binding inheritances:

- **Crowdedness features** (`signal_count_7d`, `bull_premium_share_14d`-style, 7-session rolling
  per field guide Table K) are legal and adopted into detector v1 (FS-R9). RUL-2 adjacency:
  these count *our own logged events*, mechanistically distinct from the killed sector-level
  ΔOI-persistence construction (DO_NOT_REBUILD §2) — documented so no agent can claim them as a
  variant of the dead construction. Field-guide Table K caveat carried: crowdedness is weak
  as a standalone cross-root feature (high tercile is SPY/SPX/AAPL momentum); it is admitted as
  a within-root-over-time / interaction input, not a standalone ranker.
- **GEXR-family features** carry **mandatory era interaction** and are never fixed-sign (E1
  verdict, FS-R9; the era-partition amendment §5 decision rule); vol-conditioning, not direction.
- **Skew-decel features** carry the **skeptical prior** (FS-R9; the bullish premise is
  unsupported) — admitted as a feature labeled with that prior, never an anchored escalator.
- **DOI features**: the sector-level construction is dead (DO_NOT_REBUILD §2); the single-name
  S-DOI bucket still accrues with **no anchored weight either way** (FS-R9) — admissible as an
  unweighted input, not a prior.
- **Quote-rule execution features** (at-ask/at-bid/sweep aggression) are legal measurement per
  FS-R6(a) (FS-C1 positive, 2026-07-13); tape-**signed** tick-rule direction is **not** a legal
  feature or label (FS-R6, DO_NOT_REBUILD §4 Theta-tape SUSPENDED). Soft direction may enter
  only as a feature labeled with its measured error (field guide Table E provides the first
  discrimination measurement), never as a label.
- **Survivorship discipline** (field guide survivorship notice): the 383-root eod_proxy universe
  is today's optionable set applied backward; pre-2020 base rates are survivorship-inflated.
  Since eod_proxy is priors-only and no pre-2020 verdict cell is registered, this bias cannot
  enter a verdict — but priors drawn from early eras carry the caveat and are not treated as
  unbiased baselines.

---

## §4 Cross-validation geometry (FS-R7)

The CV design is fixed here so it cannot be tuned to a result. It follows the FS-R7 ML statute
(purged + embargoed CV; group folds by underlying AND time; uniqueness weights; era-stratified
OOS; registered trial count + deflated stats).

### §4.1 Purged K-fold + embargo ≥ label horizon per bucket

- **Purged K-fold** (K = 5): training observations whose label window overlaps any validation
  observation's label window are **purged** from the training fold (overlapping-label leakage
  removal).
- **Embargo ≥ label horizon**, set **per bucket** to the primary ruler's horizon: **≥ 5 trading
  days** for S-FLOWML-0_7, **≥ 21** for S-FLOWML-8_90, **≥ 63** for S-FLOWML-90P (the 90P
  embargo covers the 63d primary; the 126d secondary is reported only where a ≥126d embargo is
  also clean, else the 126d cell is `building_history`). The embargo removes post-validation
  training rows within the horizon window on both sides of each validation block.

### §4.2 Group folds by underlying AND time block

Folds are grouped on **both** `underlying` (a name never appears in both train and validation of
the same fold — cross-sectional leakage guard) **and** `time_block` (calendar blocks, so a fold
boundary is a date boundary — temporal leakage guard). This is the ticker-cluster + time-control
law: ticker-cluster CV without time control is anti-conservative (effective N collapses to
months; the field-guide §4 CI-independence caveat and §5 confound #9 make this explicit — millions
of same-day events share one SPY session). Grouping on time as well as underlying is mandatory.

### §4.3 CPCV for model selection

Model / hyperparameter selection uses **Combinatorial Purged Cross-Validation** (CPCV) — multiple
purged train/test splits over combinatorial block assignments — so the selection statistic has a
distribution, not a single point, and the number of selection paths is counted toward the
deflated-stats trial count (§4.5). Final OOS reporting is on a **held-out temporal block** that
took part in **no** selection path (the newest era's out-of-selection tail), never on a CPCV
path used for selection.

### §4.4 Uniqueness sample-weights

Overlapping-label events are down-weighted so concurrent events do not count as independent
evidence (FS-R7). The scheme:

- For each event *i* in bucket *b*, its label spans the horizon window W_i = [t_i, t_i + H_b].
  Let c_t = the number of events in the same bucket whose label window covers day t. The
  **average uniqueness** of event *i* is u_i = mean over t ∈ W_i of (1 / c_t).
- The training sample weight is w_i = u_i, renormalized so Σ w_i = the **effective sample size**
  Σ u_i (not the raw row count) — so n floors (§7) and all reported statistics are quoted in
  *effective* observations, not raw rows.
- **Additional same-session down-weight** for the shared-underlying-move problem (field-guide
  §5 #9): within a (session, underlying) group, events additionally share a common outcome
  shock; the uniqueness weight is applied on the (session, underlying)-collapsed concurrency,
  so a thousand SPY prints on one session do not inflate effective N. This is the operational
  form of the anti-conservative-CI fix the field guide mandates.

### §4.5 Registered trial count for deflated statistics

Deflated statistics (deflated-Sharpe-style multiple-testing correction on any selection metric)
require a pre-committed trial count. The **declared trial budget is fixed here** and is the
cardinality of the registered selection grid, per bucket:

> **N_trials(bucket) = |hyperparameter grid| × |DTE-interaction on/off (8_90 only)| × |CPCV
> selection paths|**, with the hyperparameter grid frozen in the FS-4 trainer config and its
> cardinality printed in the artifact manifest. The trial count used in the deflation is the
> **registered** budget, not the post-hoc number of runs — over-running the grid without
> amending this number is a violation. Any expansion of the grid is an amendment that re-states
> N_trials and re-checks (§6 re-check clause).

The deflation is applied to the model-selection metric; the **verdict** on each registered cell
(§6) is separately subject to the BH-FDR family correction — the two corrections are distinct
and both bind (selection deflation guards the model choice; BH-FDR guards the cell verdicts).

---

## §5 Calibration criteria (FS-R5)

Calibration is the product (§3 masterplan). Per bucket, on the serving-distribution cohorts only:

- **Per-bucket isotonic calibration on a TEMPORAL holdout** (FS-R5): isotonic regression fit on a
  time-separated holdout, never on a random split (a random split leaks the shared-session
  structure). Each bucket calibrates independently — no cross-bucket "a 90 means the same
  everywhere" parity claim until every bucket independently clears its registered OOS n floor
  (FS-R5).
- **ECE < 0.05 per bucket** as the go/no-go (FS-R5). Expected Calibration Error computed on the
  temporal holdout with pre-registered bins (10 equal-mass bins); ECE ≥ 0.05 = the bucket does
  not ship a calibrated score (display stays "building history").
- **Brier score vs base rate:** the bucket's Brier score must beat the no-skill base-rate Brier
  (predict the marginal rate for every event) on the temporal holdout. A Brier that does not
  beat base rate = no skill = no calibrated score.
- **Reliability monotonicity:** the reliability curve (predicted vs empirical, per bin) must be
  monotone non-decreasing within tolerance on the holdout. A non-monotone reliability curve is a
  kill trigger (§8), not a "smooth it and ship" situation.
- All calibration numbers are reported with **n per bin** (tiny-n bucket theater is the exact
  failure red-teamed in §1.2 of the masterplan); bins below the n floor are printed as
  ERA-SPARSE, not smoothed over.

---

## §6 FDR family arithmetic (FS-R8 — the enlargement, explicit)

This is the mandatory FS-R8 statement: the NEW total FDR family arithmetic, enumerated cell by
cell, with no double-counting, and the amend-on-add re-check clause. The family being enlarged is
the options-alpha family, **28 tests as of the OVC amendment** (OPTIONS_ALPHA §4, 2026-07-06;
BH-FDR α = 0.10, threshold for the k-th ranked ascending p-value = (k/N) × 0.10).

### §6.1 Cell definition — what one registered test cell is

A flow-score test cell is exactly **one (construction × era × ruler)** triple, where:

- **construction** ∈ {S-FLOWML-0_7, S-FLOWML-8_90, S-FLOWML-90P} — 3 (FS-R5 buckets).
- **era** ∈ the eras a **legal serving-distribution cohort** populates — see §6.2. This is the
  honesty pivot: eras with no `live_feed`/`tape_recon` coverage register **zero** cells.
- **ruler** = the FS-R2 primary ruler for that bucket (excess-vs-SPY basis), plus for
  S-FLOWML-90P the 126d **secondary** ruler as its own cell. The **absolute-basis** report of
  each ruler is a diagnostic printed alongside, **not** a separate cell (§2.1) — so absolute vs
  excess does not double-count.

A verdict on a cell is: does the calibrated score, on that construction/era, separate outcomes on
that ruler with a time-preserving / clustered CI that excludes 0 (§7 inference)?

### §6.2 Which eras get a verdict cell (reviewer attack (b) — cohort-coverage honesty)

Verdict cohorts are `live_feed` (2026→) and `tape_recon` (SPY 2022-2023 today, accruing). Both
are greeks-era instruments; on the greeks-dependent grid (2017-19 / 2020-22 / 2023→, era-partition
amendment §3.1) they fall in:

| Greeks-grid era | Legal-cohort coverage | Verdict cell? |
|---|---|---|
| 2017-19 | none (tape_recon tier-2 ETF 2017→ **not yet harvested**; live_feed is 2026→) | **NO** — no legal cohort populates it today. Registered as reservable-on-amendment, not booked now. |
| 2020-22 | `tape_recon` SPY **2022 only** (2020-21 not covered) — a **PARTIAL era** | **YES, partial** — booked but flagged 2022-only + ERA-SPARSE-gated until n floor clears (§7). No claim that 2020-21 is covered. |
| 2023→ | `tape_recon` SPY 2023 + `live_feed` 2026→ | **YES** — the primary verdict era. |

And on the OI-only grid (2012-15 / 2016-19 / …): those early eras are populated **only** by
`eod_proxy`, which is priors-only (FS-R4) — so they register **zero** verdict cells. This is the
explicit anti-(b) guarantee: **no era cell claims a pre-2022 OOS verdict from tape**, and no
pre/post-2020 pooling occurs — the 2020-22 and 2023→ cells are separate cells with separate
verdicts, and the pre-2022 window has no verdict cell at all.

**Verdict eras registered = {2020-22 (partial, 2022-only), 2023→} = 2 eras.**

### §6.3 The enumeration (reviewer attack (a) — count equals cells, no double-count)

Ruler-cells per construction per era:

- S-FLOWML-0_7 → {5d excess-vs-SPY} = **1** ruler-cell
- S-FLOWML-8_90 → {21d excess-vs-SPY} = **1** ruler-cell
- S-FLOWML-90P → {63d excess-vs-SPY (primary), 126d excess-vs-SPY (secondary)} = **2** ruler-cells

Ruler-cells per era = 1 + 1 + 2 = **4**.

Cells × the 2 verdict eras:

| Era | 0_7 (5d) | 8_90 (21d) | 90P (63d) | 90P (126d) | Era subtotal |
|---|---|---|---|---|---|
| 2020-22 (partial, 2022-only) | 1 | 1 | 1 | 1 | 4 |
| 2023→ | 1 | 1 | 1 | 1 | 4 |
| **Added cells** | | | | | **8** |

**Cells added = 8.** No cell is counted twice: absolute-basis reports are diagnostics not cells
(§2.1); the 126d secondary is one distinct cell per era (not a re-report of 63d); the 2017-19 era
and all OI-only early eras contribute **zero** cells (§6.2).

### §6.4 New family total and BH-FDR recompute

> **Total family size = 28 + 8 = 36 tests.** Under Benjamini-Hochberg (BH-FDR) at **α = 0.10**,
> the adjusted significance threshold for the k-th ranked p-value (ranked ascending) becomes
> **p_k ≤ (k/36) × 0.10**. The most-significant single-test threshold tightens to 0.10/36 ≈
> **0.0028** (from ≈0.0036 at N=28), relaxing to 0.10 for the 36th. **No flow-score cell verdict
> claims significance without clearing BH-FDR at α = 0.10 over this full 36-test family.**
> Per-era sub-family accounting per the era-amendment §6 clause still applies where a signal is
> reported per era; the family total 36 is the ceiling family over which the global BH-FDR runs.

### §6.5 Amend-on-add re-check clause (currently vacuous, but binding)

Per the W-C / OVC amend-on-add clause carried into FS-R8: when this amendment enlarges the family,
prior registered p-values must be re-checked at the new (tighter) threshold. **Re-check result at
this enlargement: all prior 28 buckets are `building_history` with no claimed p-values (their
fires accrue from 2026→ and none has cleared its n floor), and all 8 new flow-score cells are
likewise `building_history` (tape_recon is accruing, live_feed just started). Therefore no
re-check flips any verdict — the clause is currently VACUOUS.** It is nonetheless binding: the
first time any cell in the 36-family posts a p-value, every other posted p-value is re-ranked
against (k/36)×0.10, and each future enlargement (deferred signed/moneyness/repeat cells, §1)
re-states the total and re-runs the re-check.

---

## §7 N floors and ERA-SPARSE handling (FS-R8)

- **N floor ≥ 30 per condition bucket; ≥ 20 per era cell**, else **ERA-SPARSE** (FS-R8). All n
  are quoted in **effective** observations (uniqueness-weighted, §4.4), not raw rows — this is
  the operative anti-anti-conservative-CI rule (a million SPY prints on shared sessions is not
  n=1,000,000; field guide §5 #9).
- An ERA-SPARSE cell prints its count and its "building history" state; **no verdict, no
  effect-size claim, and it does not enter the BH-FDR ranking** until it clears the floor (it
  remains a registered-but-unfilled cell — a null never blocks accrual, but it also never earns a
  verdict below floor).
- The **2020-22 (2022-only, partial) cells are expected ERA-SPARSE-gated** for some time — the
  tape_recon 2022-2023 sweep is ~17% graded and accruing (field guide Table D/E), and 2022 is a
  slice of that. They are booked (so the family arithmetic is honest and fixed in advance) but
  will sit `building_history` until effective n ≥ floor. This is the honest handling of a partial
  era: register the cell, gate the verdict.
- **Inference is time-preserving / clustered, never raw-Wilson** (field guide §4 CI-independence
  caveat + §5 #9; the ticker-cluster + time-control law): CIs come from a within-period
  block/permutation or an underlying×time clustered method, so effective N reflects the months of
  independent time, not the row count. A cell whose time-preserving CI includes 0 is not a pass.

---

## §8 Pre-registered kill criteria (FS-R8; FS-3 wave kill template)

A construction is **killed** (closes to display/confirmer only, construction-specific per the
kill-scope law — the search space stays open) when, at or above its n floor on the
serving-distribution cohorts:

1. **OOS AUC ≤ 0.55 in the newest era (2023→)** for that bucket — the score does not rank-order
   outcomes better than near-chance where it matters most (the live-serving era). (Chosen as the
   newest-era gate because a signal alive only in an older era is suspect/decayed, era-amendment
   §5 decision rule.)
2. **Calibration monotonicity broken** — the reliability curve is non-monotone beyond tolerance,
   OR ECE ≥ 0.05 persists on the temporal holdout after refit. A miscalibrated score is not
   shippable as a probability (§5).
3. **All ruler-cell CIs include 0** for the bucket — every registered (era × ruler) cell for that
   construction has a time-preserving / clustered CI covering 0 at n ≥ floor (no ruler separates
   outcomes). Kills that specific construction, not the flow-score search space.
4. **Shadow calibration-decay breach** (decay sentinel, FS-R11 / Oracle W-B4 pattern): after a
   quarterly refit, realized-vs-predicted ECE drifts beyond the registered band (ECE crosses 0.05
   and stays there across the monitoring window) — the bucket demotes from any shipped-calibrated
   state back to `building_history` and the decay is logged. This is included because the 0DTE /
   zero-commission regime is young and fast-moving (masterplan §7 era-fragility risk; the 0-7d
   bucket retrains most often and is most decay-prone), so a live decay tripwire is judged
   necessary, not optional.

A kill is recorded construction-by-construction and era-by-era; a bucket may survive in 2023→ and
be ERA-SPARSE (no verdict) in 2020-22 — that is not a kill, it is an unfilled cell.

---

## §9 Shadow / promotion path (FS-R10, FS-R11 — display-only until gate)

- **Display-only until the gate passes (FS-R3, doctrine §2.1).** Pre-gate, the score ships as a
  labeled display probability with its conditioning stated ("based on N similar events, since
  DATE; building history") on the FS-R10 surfaces (primary seam = `intel/v1 tape.flow_score` via
  the Dashboard-owned `pull_macro_intel.py` bridge; secondary = the R2 `tickers_ctx` field behind
  the chartered VPS coordination; site surfaces glance-tier per DESIGN_DOCTRINE, EN/ZH via
  Write/Edit, no `title=` translations, no competitor names). The word "validated" never appears
  in an affirmative claim on any surface — only in negation or backed by a passed-gate artifact
  (`check_validated_claims.py` CI guard; CLAUDE.md law).
- **Shadow is gate-governed, not calendar-governed (FS-R11).** The live shadow = the ledger
  scoring every new event + the nightly realized-vs-predicted calibration monitor (decay sentinel,
  §8 #4) + shadow-stamp columns on the fire ledger written ONLY through the A9 single writer
  `scripts/stamp_options_state.py` (no new writer; FS-R8 / RO-12 ownership). Promotion eligibility
  begins when the registered n floors (§7) clear per bucket per era — not after any fixed number
  of weeks (the competitor's one-week window is refused, §1.2 masterplan).
- **Promotion (FS-5) is a separate gauntlet**, not authorized by this amendment (§10). Survivors
  act only through the existing bounded seams (F8): stock_score entry tilt (±0.5 bounded,
  gate-keyed), evidence-stack vote, NW Article-3 earn-in, Terminal tone upgrade — and start as
  **caution-only / de-escalation** per doctrine §2.1; symmetric escalation only via its own
  registered gate.

---

## §10 What this amendment does NOT authorize

Stated explicitly so scope cannot drift:

1. **No trainer code until this amendment is merged and Fable-ratified** (FS-R8: registration
   before computation). FS-4 is blocked on this.
2. **No coupling of the score to rank / size / gate on ANY surface pre-gate** (FS-R3, RO-2,
   doctrine §2.1). Pre-gate the score is display-only; grep-verifiable that it feeds no ranker,
   sizer, or gate. No fused pre-gate composite lift.
3. **No `eod_proxy` cohort in any calibration set or published verdict** (FS-R4). eod_proxy is
   priors / pre-training only; a verdict or calibration curve drawn from it is a violation.
4. **No signed / tick-rule direction features or labels** (FS-R6; DO_NOT_REBUILD §4 Theta-tape
   SUSPENDED). Quote-rule execution measurement is legal (FS-R6(a)); tape-signed direction is not.
   The registered score target is the **unsigned** grader outcome (§2.3) — no signed directional
   P(·) is registered.
5. **No verdict cell outside the 2 registered verdict eras** (§6.2). No pre-2022 OOS verdict from
   tape; no 2017-19 verdict until tier-2 ETF tape is harvested (which would be a future amendment
   re-stating §6); no OI-only-early-era verdict at all.
6. **No premium-touch (`prem_touch_50/100`) ruler as verdict currency** (FS-R2) — display-only,
   labeled "path max, not P&L."
7. **No new BH-FDR cell without amending §6** — expanding rulers, eras, moneyness strata, signed
   targets, or repeat-cluster cells re-states the family total and re-runs the re-check clause.
8. **No new data spend** (FS-R12); **no sklearn on the nightly render path** (FS-R7 — precompute
   artifact off-path, render reads); **no ledger write except through the A9 single writer**.
9. **No cross-bucket "90 = 90" parity claim** until every bucket independently clears its
   registered OOS n floor (FS-R5).

---

## §11 Ratification

- **Drafted by:** Opus (FS-3 statistics-design lane), 2026-07-13.
- **RATIFIED by:** Fable (main-loop orchestrator), 2026-07-13, after direct review of §2 (score
  definition + unsigned-outcome basis), §3 (population spec incl. the Table H index-root
  prefilter), §6 (cell enumeration — arithmetic independently re-checked: 4 ruler-cells × 2
  verdict eras = 8 added, 28 → 36, BH-FDR α=0.10 top threshold ≈0.0028; the 2020-22
  partial-era booking and zero-cell treatment of priors-only eras are the honest reading of
  FS-R4), §7-§8 (floors + kill criteria). The §2 constructions, §6 family arithmetic, §4 CV
  geometry, §5 calibration criteria, §7 n floors, and §8 kill criteria are hereby FROZEN;
  FS-4 may be dispatched. Changing any frozen element requires a new amendment + re-check.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
