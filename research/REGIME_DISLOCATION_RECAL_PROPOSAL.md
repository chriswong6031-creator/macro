# Regime + Dislocation recalibration proposal (PRE-REGISTERED)

**Status: PROPOSED — nothing in this document is implemented.**
Author lane: regime/dislocation honesty pass, 2026-07-29.
Companion to `research/DISLOCATION_VALIDATION.md`, `research/PREREGISTRATION.md` §4,
`docs/DESIGN_DOCTRINE.md`, and the promotion-gauntlet law in `CLAUDE.md`.

---

## §0 What this document is, and what it is not

Two adversarial audits (regime package, dislocation package) produced two kinds of
finding. The **honesty and bug** findings shipped immediately — a null never blocks
building, and a false sentence is a defect, not a research question. The findings below
are the other kind: they would move a **gate value, threshold, weight, hysteresis
parameter, or promotion tier**, and under the house gauntlet law those may not be
changed on the strength of an audit narrative. They need a pre-registered replay with
its acceptance gate fixed **before** the replay is run.

So this file states, for each item: the defect, where the evidence is, the proposed
change, the acceptance gate **written down in advance**, and the replay plan.

**Rules this document binds itself to.**

1. **No gate moves on this document alone.** Each item ships only after its own replay
   clears its own pre-registered gate. A null result closes that construction and gets
   a row in `research/DO_NOT_REBUILD.md`.
2. **Gates are stated before the replay runs.** Any gate edited after seeing a result
   invalidates that item and it restarts as a new pre-registration.
3. **Nulls are printed, not hidden.** Every item's outcome — pass or fail — is recorded
   in this file and in the experiments registry.
4. **Display tier is free; authority tier is gated.** Several items below are satisfied
   by a *disclosure* change (publish the seam, print the null) rather than a
   recalibration. Where that is the honest answer it is named as the primary option.
5. **Not a re-proposal of any killed topic.** Checked against
   `research/DO_NOT_REBUILD.md` and `docs/ACTIVE_BUILD_MAP.md` on 2026-07-29. §13 in
   particular is NOT a re-proposal of "election / midterm cycle as standalone signal"
   (REFUTED, `DO_NOT_REBUILD.md` line 84) — it is a coherence question about an
   already-display-only modulator's interaction with the band ladder.

**Verified-today numbers used below** (so a later reader can tell measurement from
assertion). From `data/regime/regime_history.parquet` (25,718 rows, tail 2026-07-28):
`raw_quad != quad` on **25.8%** of all rows with both non-null, **44.0%** since 2000,
**40.9%** since 2010, **44.6%** since 2020, and **49.4%** over the trailing ~2 years
(542 sessions). The audit's figure of 48.5% is consistent with the trailing-2y slice.
Live 2026-07-29 `data/regime/latest.json`: `quad` Q1, `growth_score` −0.133,
`inflation_score` +0.400 (raw Q3), `transition_state` TRANSITIONING, `flip_margin` 0.0.

---

## §1 Hysteresis counter is keyed on candidate IDENTITY, so an alternating candidate stalls it forever

**Defect.** `engine/regime.apply_hysteresis` advances its confirmation counter only
while the raw quad *keeps naming the same candidate*: `cand, cand_n = rq, 1` whenever
`rq != cand`. When one axis holds a flipped sign indefinitely while the other
oscillates across zero, the raw quad alternates between two candidates, each arrival
resets the counter to 1, and the confirmed label can **never** reach
`hysteresis_days` — it holds indefinitely against an axis that contradicts it on every
single session. The label is not "sticky" in this state; it is *unreachable*.

**Evidence pointer.**
* Mechanism pinned in `tests/test_engine.py::test_alternating_candidate_stalls_hysteresis_known_defect`
  (40 contradicted sessions, `pending_days` never exceeds 1; a single-candidate control
  of the same length DOES confirm, which isolates the identity reset as the cause).
* Live instance 2026-07-29: label Q1 with **both** clauses false (growth −0.133,
  inflation +0.400).
* Historical instance, `regime_history.parquet` 2026-01-01..2026-01-15: `quad` pinned
  Q4 while `raw_quad` alternated Q2/Q1; the counter reached 6 and was reset to 1 on
  2026-01-07 by a single Q1 session. The label eventually moved on 2026-01-16 only via
  the **shock override** (inflation_score exactly 1.00), not via the countdown.
* Base rate: `raw_quad != quad` 44.0% since 2000 (above).

**Proposed change (one of, decided by the replay — not by preference).**
* **A. Per-axis-sign counter.** Count consecutive sessions each axis has *disagreed
  with the confirmed label's expected sign* (`_quad_signs`), and flip when either
  axis's disagreement run reaches `hysteresis_days`. The new label is the raw quad on
  the confirming session. This is the variant the defect argues for: it counts
  *contradiction of the current label*, which is the thing hysteresis is meant to be
  robust about, instead of *agreement between successive candidates*.
* **B. Any-non-current-quad counter.** Count consecutive sessions where `raw_quad !=
  quad` regardless of which alternative it names; flip to the raw quad on the
  confirming session. Simpler, but flips to whichever quad happens to be on the
  confirming day, which is arbitrary under a genuine oscillation.
* **C. Do nothing, disclose only.** Publish the stall (already shipped: `raw_quad`,
  `pending_quad`, `pending_days`, `pending_need` in `latest.json`; `flip_condition.
  label_unsupported`; the honest `playbook.quad_meaning`) and accept the stickiness.

**`hysteresis_days` MUST NOT be lowered as part of this.** The 7-session requirement is
the whipsaw control and is not what is broken; lowering it would trade this defect for
the fakeout defect `test_hysteresis_blocks_fakeout` guards. Any replay that reports
improvement while also moving `hysteresis_days` is inadmissible.

**Pre-registered acceptance gate** (A or B ships only if ALL hold):
1. **Fewer contradicted sessions.** Share of sessions with `raw_quad != quad` falls by
   ≥ 5 percentage points on 2000+ (from 44.0%) **and** on the 2012-2025 half
   independently.
2. **No whipsaw regression.** Count of confirmed-label changes per year rises by
   ≤ 25% vs the current rule on 2000+, and the median confirmed-quad segment length
   falls by ≤ 25%. (This is the price cap: fixing the stall must not turn the label
   into the raw rule.)
3. **The fakeout control still holds.** `test_hysteresis_blocks_fakeout` and
   `test_shock_override_flips_fast` pass unchanged.
4. **Split-half sign consistency.** Whatever downstream metric is chosen in the replay
   plan below must move in the SAME direction in 1997-2011 and 2012-2025. A gain in one
   half only is a null.
5. **No downstream authority claim.** The quad is an input to sector/factor tilts; this
   item claims only label *coherence*, never a return improvement. If the replay shows
   a return improvement it is reported as an observation and does NOT become the
   justification — that would be a separate promotion with its own gauntlet.

**Replay plan.** Re-run `apply_hysteresis` variants A, B and current over the stored
`regime_history.parquet` axis series (`growth_score`, `inflation_score`) — the axes are
inputs to the state machine and are unchanged by it, so this is a pure re-derivation
with no refit and no lookahead. Report: contradicted-session share (full / 2000+ /
per split-half), flips per year, segment-length distribution, and the count of stall
episodes (defined: ≥ `hysteresis_days` consecutive sessions with `raw_quad != quad` and
`pending_days` never reaching `pending_need`). Freeze `SOURCE_COMMIT` and pin the input
grid before running — a DATA-advance between runs re-rounds the axis history and can
flip labels at the 0.0 boundary (see memory `frozen-replay-audit-needs-pinned-input-grid`).

---

## §2 `shock_override_z` 0.85 is unreachable on the inflation lattice with any dissent

**Defect.** Axis components score −1/0/+1 and the axis score is a weighted mean over
*available* components (`engine/axes.score_axis`). The inflation axis has 7 components
with weights `{1, 1, 1, 1, 1, 0.75, 0.5}` summing to 6.25. Enumerating the lattice
against `shock_override_z = 0.85`:

| inflation-axis state | score | ≥ 0.85? |
|---|---|---|
| all 7 agree | 6.25/6.25 = **1.00** | yes |
| sticky_cpi neutral (0), rest agree | 5.75/6.25 = **0.92** | yes |
| tips neutral (0), rest agree | 5.50/6.25 = **0.88** | yes |
| sticky_cpi **dissents** (−1), rest agree | 5.25/6.25 = **0.84** | **no** |
| tips + sticky both neutral | 5.25/6.25 = **0.84** | **no** |
| tips dissents (−1), rest agree | 4.75/6.25 = **0.76** | no |

So the inflation shock override requires **zero dissenting legs**: a single dissent —
even the smallest-weight leg, sticky-CPI at 0.5 — caps the axis at 0.84 and disarms the
override entirely. This is a *lattice* property, not a tuning choice, and it was almost
certainly not intended: 0.85 sits in a gap with no attainable value between 0.84 and
0.88.

The growth axis differs (weights `{1,1,0.5,1,1,1,0.5,0.5,0.5,0.5}`, sum 7.5): one
0.5-weight dissent gives 6.5/7.5 = **0.867** ≥ 0.85, so growth CAN shock through a
single small dissent while inflation cannot. The two axes are therefore governed by
different effective rules despite sharing one parameter.

> **Refinement vs the audit brief.** The brief stated the threshold is "unattainable
> (max 0.84 with sticky-CPI dissent)". Verified precisely: it is unattainable *with any
> dissent*, and attainable at 0.88/0.92/1.00 with neutral-or-unanimous legs. The
> 2026-01-16 live flip fired at exactly 1.00 (unanimous), which is consistent.

**Evidence pointer.** `config.yml` `engine.quad.shock_override_z: 0.85`;
`engine.inflation_axis.components` / `engine.growth_axis.components` weights;
`engine/axes.py:79` (weighted mean over available weight);
`regime_history.parquet` 2026-01-16 (`inflation_score` 1.00 → override flip).

**Proposed change.** No threshold move is proposed here — the primary deliverable is a
**lattice-attainability unit test** that makes this class of defect impossible to ship
silently: for each axis, enumerate the attainable score lattice from the configured
weights and assert (a) `shock_override_z` is attainable, and (b) it is attainable with
at least one dissenting leg, i.e. the override is not secretly a unanimity rule.
Failing that assertion is a config error, not a test error.

Only if the test fails and the operator judges unanimity-only to be *not* the intent
does a threshold change enter, and then as its own pre-registration.

**Pre-registered acceptance gate.**
1. The test enumerates the lattice from `config.yml` (never a hardcoded list) so a
   weight change re-derives it.
2. It is currently expected to **FAIL** for the inflation axis and PASS for growth. It
   ships as an `xfail`-with-reason (or a named skip) pinned to this section, so the
   defect is *visible* rather than red-blocking, exactly as the display-tier rule
   allows. Flipping it to a hard assert requires the threshold decision above.
3. No gate value moves in the same change as the test.

**Replay plan.** None needed — this is a closed-form enumeration over the configured
weight lattice, not a statistical claim. Report the attainable-value table for both axes
in the PR body.

---

## §3 Transition ladder has no inflation-side persistence flag and no `contradiction_floor` leg

**Defect.** The transition warning flags (`engine/transition.compute_flags`, surfaced as
`latest.transition_flags`) cover breadth/price, credit/equity, ratio inflection,
inflation-basket, confidence decay and GEX. Two gaps:
* **No inflation-side persistence flag.** `flag_inflation_basket` reads a *basket
  rotation*, i.e. a market proxy. There is no flag for the inflation axis's own
  persistence legs (`sticky_cpi_direction`, the breakeven direction legs) turning
  against the label — so an inflation-led transition is only visible through a price
  proxy of itself.
* **No `contradiction_floor` leg.** The ladder has no flag that fires on the *structural*
  condition "the confirmed label's own axes contradict it" — which is now a published
  state (`flip_condition.label_unsupported`, `latest.raw_quad != latest.quad`) and was
  true on 44.0% of post-2000 sessions. Today a fully-contradicted label can read STABLE.

**Evidence pointer.** `engine/transition.py` flag set;
`latest.json` 2026-07-29 (`transition_state` TRANSITIONING with `flip_margin` 0.0 —
the state did fire here, but via the ratio/confidence legs, not from the contradiction
itself); §1's Jan-2026 stall, where the contradiction persisted for 15 sessions.

**Proposed change.** Add two flags at **display tier only**, i.e. they appear in
`transition_flags` and in the trigger lines but do NOT enter `n_flags` for the
state-machine ladder until gauntleted:
* `flag_inflation_persistence` — the inflation axis's persistence legs (sticky-CPI
  direction, breakeven direction) sign against the confirmed label's expected inflation
  sign.
* `flag_contradiction_floor` — `raw_quad != quad` for ≥ N consecutive sessions
  (N pre-registered at `hysteresis_days`, so it fires exactly when the countdown
  *should* have resolved and did not).

**Pre-registered acceptance gate** (to enter `n_flags` and thus the ladder — the
display-tier addition needs no gate):
1. Precision floor: conditional on the flag firing, the confirmed label changes within
   63 sessions at a rate ≥ 1.3× the unconditional base rate of a label change in 63
   sessions, with a 95% episode-block-bootstrap CI excluding 1.0.
2. Sign holds in BOTH split-halves (1997-2011, 2012-2025).
3. Does not merely restate an existing flag: max pairwise co-firing rate with any
   current flag ≤ 0.7, else it is a duplicate observation of the same tape and is
   retained as confluence only (per the house same-tape rule).
4. Adding it must not raise the count of NEW_REGIME caps by > 20% on 2000+ (the ladder
   caps market state at MIXED, so a chatty flag has a real cost).

**Replay plan.** Derive both flags over `regime_history.parquet` + the axis component
columns (`c_inflation_*`), join forward label changes, and report per-flag hit rate vs
base, the CI, the split-half table, and the co-firing matrix against all six current
flags. Display-tier shipping does not wait on this.

---

## §4 `dislocation_active` is a single-trigger knife-edge with no hysteresis or minimum duration

**Defect.** `dislocation_active` is a bare OR of four readings
(`engine/dislocation.snapshot`): a single trigger crossing its threshold by any margin
flips the whole panel on, and a single reading crossing back flips it off. There is no
hysteresis, no minimum duration, and no margin requirement. On 2026-07-29 the state was
carried by **one** trigger (`VRP extreme`) whose unrounded reading was 0.9027 against a
0.90 cutoff — a 0.0027 margin. The same knife-edge is what made the rounding defect
(now fixed) visible: the fired/not-fired distinction was inside the display precision.

**Evidence pointer.** `engine/dislocation.py` trigger OR; `latest.json` 2026-07-29
`inputs.vrp_pctile_raw` 0.9027 with `triggers: ["VRP extreme"]`;
`data/dislocation/state_log.parquet` (the forward PIT accrual) for the realized
flip-flop frequency.

**Proposed change.** A minimum-duration / hysteresis wrapper on `dislocation_active`
only — **not** on any trigger threshold: require a trigger to hold for `min_duration_d`
consecutive sessions to turn the state ON, and require all triggers to be clear for
`min_clear_d` sessions to turn it OFF. Both pre-registered before the replay.
A cheaper display-tier alternative that needs no gate: publish the *margin* of each
firing trigger (distance from its own cutoff) so a 0.0027-margin firing reads as
marginal on the page. That is the honest disclosure and is recommended regardless.

**Pre-registered acceptance gate.**
1. State changes per year fall by ≥ 30% vs the current rule on 1997-2026.
2. The gate's own measured effect does not degrade: the put-present-minus-put-absent
   **median forward-63d worst-close-vs-entry** difference stays ≥ +3.0pp with a 95%
   episode-block-bootstrap CI still excluding zero (current: +3.9pp, CI [+0.3, +6.3]).
   A wrapper that improves stability while breaking the one robust effect is a null.
3. No episode that the current rule refused (put-absent) becomes buyable under the
   wrapper — the delay must not smuggle the verdict across.
4. Sign holds in both split-halves.

**Replay plan.** Re-run `scripts/research_dislocation.py` with the wrapper inserted at
the `dislocation_active` step, on the frozen input grid, reporting the full existing
table set plus state-changes-per-year. Requires §5's OR-set correction first, otherwise
the replay measures the wrapper against a composite the engine does not use.

---

## §5 Re-run the dislocation bootstrap on the engine's ACTUAL OR-set

**Defect.** The published CI is measured on a composite the engine does not fire on.
`scripts/research_dislocation.py:103` measures
`STRESS (composite) = vix>30 | spy < 0.88*roll_max | vrp_pctile>0.90`
— i.e. a **−12%** drawdown and **no backwardation leg**. The engine fires on
`vix>30 | dd ≤ −10% | vrp>0.90 | vix_ratio ≥ 1.0` — a **−10%** dip **plus**
backwardation. So the [+0.3, +6.3] CI is evidence about a *narrower* event set than the
one that lights the panel. Backwardation was measured separately and showed essentially
**no** put-present/absent separation (63d: medDD −2.6% vs −3.0%, hit 69.0% vs 66.7%).

**Evidence pointer.** `scripts/research_dislocation.py:96-103` vs
`engine/dislocation.snapshot` trigger construction;
`research/DISLOCATION_VALIDATION.md` `[VIX backwardation]` block.
Interim honesty fix already shipped: `engine/dislocation.evidence_scope` scopes the CI
per firing and states plainly that a backwardation-only firing is **not covered**.

**Proposed change.** Re-run the bootstrap on the engine's exact OR-set and publish that
CI as the panel's evidence, replacing the borrowed composite CI.

**Pre-registered acceptance gate.** This is a *measurement correction*, so the gate is
on what the copy may then claim, not on whether to run it:
1. If the engine-OR-set 63d median-worst-close difference CI **excludes zero**, the
   panel may cite that CI for any firing and `evidence_scope` collapses to one note.
2. If it **includes zero**, the panel must stop citing a CI for the general firing and
   fall back to per-leg scoping — with the backwardation leg explicitly carrying no
   measured separation. `evidence_scope` already implements this shape.
3. Either way the −10% vs −12% difference is reported as its own row, and the copy may
   not present a −12%-measured number as evidence for a −10% firing.
4. No threshold moves on the strength of this replay. If −10% turns out to be
   unsupported, *that* becomes a separate pre-registration.

**Replay plan.** Add the engine OR-set as a named composite in
`scripts/research_dislocation.py`, alongside (not replacing) the research composite so
the two are directly comparable, and regenerate `research/DISLOCATION_VALIDATION.md`.
Report both CIs side by side plus the per-leg blocks. Note the generator also needs the
metric relabel flagged at the top of that file (`medDD`/`dd63` are *worst subsequent
close vs entry*, which can be positive).

---

## §6 Behaviour at the 2.5% breakeven threshold: both 2022 prints were within 0.02pp

**Defect.** The `fedput_off` leg is a hard cut at a 21-day-smoothed 10y breakeven of
2.5%. In 2022 — the canonical put-absent year — the gate printed **buyable_washout**
twice (2022-01-21, 2022-07-12) with the smoothed breakeven within **0.02pp** of the
cutoff, both followed by negative forward-63d outcomes. The verdict on those days was
decided by two hundredths of a percentage point on a smoothed macro series that is
itself revised and vendor-dependent. A binary cut with zero margin treatment is not
robust at that resolution, and the panel presented those verdicts with the same
confidence as a comfortably-clear reading.

**Evidence pointer.** Declustered replay (audit artifact) 2022-01-21 and 2022-07-12;
`research/DISLOCATION_VALIDATION.md` named-episode ledger row `2022 bear` (entry
2022-03-07, `be` 2.8, PUT-ABSENT, fwd63 −0.2%, fwd252 −3.4%) — the ledger's single
max-VIX entry *does* land put-absent, which is why the near-threshold prints were
invisible until the declustered replay looked at every firing.
Interim honesty fix already shipped: the `buyable_washout` headline now names the known
misses, and `EVIDENCE["caveat"]` states them.

**Proposed change (one of).**
* **A. Margin band, display tier.** Publish the distance from the cutoff and, inside a
  pre-registered band (proposal: ±0.10pp), label the verdict `marginal` — the verdict
  enum is unchanged, the panel says the call is knife-edge. No gate moves; ships freely
  under the display-tier rule.
* **B. Verdict-level uncertainty band, authority tier.** Inside the band, degrade the
  verdict to `unknown` the way the staleness guard now does. This DOES move behaviour
  and needs the gate below.

**Pre-registered acceptance gate** (for B only; A needs none):
1. Applying the band over 1997-2026 must not reduce the put-present-vs-absent median
   worst-close difference below +3.0pp with a CI still excluding zero.
2. It must reclassify BOTH 2022 near-threshold prints out of `buyable_washout`.
3. It must not reclassify more than 15% of all firings into `unknown` — a band that
   nulls the panel most of the time is a null result, not a fix.
4. The band half-width is fixed at 0.10pp **before** the replay and may not be tuned to
   satisfy (2) and (3) simultaneously. If no single pre-registered width satisfies both,
   the item fails and option A is the answer.

**Replay plan.** Re-derive the master switch with the band over the frozen grid; report
the verdict-transition matrix (current → banded), the affected-episode ledger, the
reclassification rate, and the re-bootstrapped CI. Run after §5 so the CI being defended
is the engine's own.

---

## §7 `put_state` gates US sector-board OSB eligibility — a live authority-tier use

**Defect.** `engine/sector_signals.py:283` reads
`osb_eligible = (ticker in _OVERSOLD_BOUNCE_COHORT) and not put_absent`, and
`scripts/build_site.py:2195` supplies `put_absent = disl.get("put_state") ==
"put-absent"`. So the dislocation gate is **not** display-only: it gates which names are
eligible for the oversold-bounce carve-out on the US sector board. That is an
authority-tier use of an artifact whose only CI-clearing effect is a median-drawdown
difference measured on ~10 put-absent crises — and whose hit-rate and median-return
separations are indistinguishable from the unconditional base.

Two consequences:
1. **Tier review needed.** An authority-tier use requires the promotion gauntlet for
   *that use*, which was never run. The drawdown-filter framing is defensible for a
   *de-risking* gate; OSB eligibility is closer to an entry permission.
2. **The consumer fails OPEN on the new `unknown` state.** `put_state == "put-absent"`
   evaluates False when `put_state` is `"unknown"`, so an unreadable switch grants OSB
   eligibility. The engine now publishes `put_state_reliable` (and `fed_put: null`)
   precisely so a consumer can fail closed; `build_site.py` has not been updated (it is
   outside this change's pathspec). **This is a live fail-open seam.**

**Evidence pointer.** `engine/sector_signals.py:246, 283, 359-390`;
`scripts/build_site.py:2195-2196, 4259-4266`;
`research/DISLOCATION_VALIDATION.md` bootstrap block (hit-rate CI [−5.1, +63.0],
median-return CI [−2.7, +12.3] — both span zero).

**Proposed change.**
1. **Immediate, no gate:** `build_site.py` derives `put_absent` as
   `put_state == "put-absent" or not put_state_reliable` — i.e. an unreadable switch
   withholds the carve-out instead of granting it. This is a fail-closed correction, not
   a recalibration.
2. **Gated:** decide whether OSB eligibility may be gated by this artifact at all, or
   whether the gate should be advisory (a chip on the row) rather than an eligibility
   filter.
3. Register the seam in `research/DISPLAY_VS_SCORING_MANIFEST.md` under scoring seams
   either way — it belongs there today and is missing.

**Pre-registered acceptance gate** (for keeping the eligibility gate):
1. Restricted to the OSB cohort and to OSB entries only, requiring `put-present` must
   improve the cohort's forward-63d median worst-close-vs-entry by ≥ 2.0pp with a
   95% CI excluding zero, on episode-declustered entries.
2. Sign holds in both split-halves.
3. If it fails, the gate is demoted to display tier (a caution chip) and a
   `DO_NOT_REBUILD.md` row records that the put switch does not earn OSB eligibility.

**Replay plan.** Join the OSB cohort's historical entries to the master-switch series
(`engine/dislocation.master_switch_frame` gives the daily put-present/absent series
already), decluster, and measure. Note the OSB cohort is small — report effective N
before the point estimate, and if N is below the pre-registered floor of 20 declustered
entries the honest outcome is "not measurable", which demotes to display tier.

---

## §8 Episode declustering gap (42bd) is shorter than the outcome horizon (63d)

**Defect.** `scripts/research_dislocation.py:56` sets `EPISODE_GAP_BD = 42`, while the
headline outcome horizon is `HEADLINE_H = 63` sessions. Two "independent" episodes
42-62 business days apart therefore have **overlapping forward windows**, so their
outcomes share tape. The episode block bootstrap resamples these as independent blocks,
which understates the variance — the CI is narrower than the data supports. Since the
one robust effect's CI is `[+0.3, +6.3]`, with a lower bound only 0.3pp above zero,
this is not an academic concern: a correctly widened CI could cross zero.

**Evidence pointer.** `scripts/research_dislocation.py:56` (`EPISODE_GAP_BD = 42`) vs
`:53` (`HEADLINE_H = 63`); the bootstrap at `:186`; the 252d horizon rows are worse
affected still (gap 42 vs horizon 252).

**Proposed change.** Set the declustering gap to at least the outcome horizon being
tested (63bd for the headline, and report the 252d rows with an explicit
overlapping-windows caveat or a horizon-matched gap). This is a **variance-estimation
correction**, not a gate change — it cannot make an effect stronger.

**Pre-registered acceptance gate.** The gate here is on what may be *claimed*
afterwards:
1. Re-run with `gap = HEADLINE_H = 63`. If the median-worst-close CI still excludes
   zero, the "ROBUST" label stands and the corrected CI replaces the published one.
2. If it now spans zero, the dislocation gate has **no** effect clearing its CI, every
   surface must drop the CI citation, and the panel falls back to sign-consistency
   language only (LOYO 26/28, both split-halves) with the null printed. The word
   "validated" must then be removed from the allowlist entries added for this panel.
3. Effective N is reported before and after (currently 37 put-present / 10 put-absent
   episodes at gap 42; expect fewer at 63).
4. No threshold or trigger changes in the same replay.

**This item is the highest-risk one in this document** — it can retire the panel's only
statistical claim. It is stated here *before* the replay precisely so the outcome cannot
be re-framed after the fact.

---

## §9 The `fedput_off` leg is structurally dead before 2003 in the validation sample

**Defect.** The validation sample starts `1997-01-01`
(`scripts/research_dislocation.py:54`), but `T10YIE` — the 10y breakeven feeding the
`fedput_off` leg — starts **2003-01-02** (verified: `data/fred/T10YIE.parquet`, first
index 2003-01-02, 5,896 rows). For 1997-2002 the leg cannot fire at all: it is
structurally absent, not measured-and-negative. The named-episode ledger shows this
directly — `be` is `nan` for `1998 LTCM` and for `2000-02 dotcom`.

Consequences:
* In 1997-2002, `put_absent` reduces to the Sahm recession leg alone. The master switch
  is a *different rule* in that stretch.
* The `1997-2011` split-half — one of the two halves the "holds in BOTH split-halves"
  claim rests on — has the full two-leg rule for only 9 of its 15 years.
* The 2000-02 buyable prints flagged in §6/the docstring occurred in exactly the window
  where the inflation leg could not veto.

**Evidence pointer.** `data/fred/T10YIE.parquet` first index 2003-01-02;
`scripts/research_dislocation.py:54` `ANALYSIS_START = "1997-01-01"`;
`research/DISLOCATION_VALIDATION.md` named-episode ledger `be` column (`nan` for the
two pre-2003 episodes).

**Proposed change.** No rule change. Two disclosure/measurement corrections:
1. `research/DISLOCATION_VALIDATION.md` prints per-leg coverage windows and states that
   pre-2003 results reflect a **one-leg** switch.
2. The split-half claim is re-stated on a coverage-matched sample: re-run the split-half
   with `ANALYSIS_START = 2003-01-02` (both legs live throughout) as the primary, with
   the 1997-start version retained and labelled one-leg-early.

**Pre-registered acceptance gate.**
1. If the two-leg-only (2003+) sample still shows the median-worst-close difference with
   a CI excluding zero AND consistent split-half signs (splitting 2003+ in half), the
   robustness claim stands on the coverage-matched sample and that becomes the cited
   result.
2. If it does not, the claim is downgraded to "measured on 2003+ with a CI spanning
   zero; the pre-2003 stretch tested a different (one-leg) rule" and the null is printed
   on the panel.
3. Effective N on 2003+ is reported before the point estimate; below 15 declustered
   put-present + 6 put-absent episodes the honest outcome is "not measurable at this
   sample" rather than a weak pass.
4. Runs jointly with §8 (both are variance/coverage corrections to the same bootstrap)
   and the combined result — gap 63 **and** coverage-matched — is the one that governs
   the panel copy.

---

## §10 The `market_state` amplifier set is non-monotone in stress

**Defect.** Two of the corroborators that amplify the risk read —
`complacency` and `breadth_div` — have *preconditions that a decline removes*:
`complacency` requires a calm surface (VIX percentile below its calm cut, or VIX term in
contango) and `breadth_div` requires the index within ~3% of its 1-year high
(`engine/risk_radar.py:679-716` documents this explicitly, and `engine/market_state.py`
consumes the same conditions gauges). So as stress actually arrives, corroborators
**disarm**, and the amplifier set is non-monotone in stress: it is strongest in the
calm-but-fragile regime it was designed for and weakest in the decline it would be most
wanted for.

This is arguably by design for those two legs (they are *pre*-decline detectors), but
the *composite* inherits the shape without any decline-appropriate replacement, so the
amplification available to the score falls exactly when the tape breaks.

**Evidence pointer.** `engine/risk_radar.py:679-716` (the honest-suppression map already
names both preconditions and why they cannot be met in a decline);
`engine/risk_radar.py:478` `CORROBORATORS`; `engine/market_state.py:262-342` (the
complacency/breadth_div consumption and the −0.06 complacency caveat).

**Proposed change.** Add one or more **decline-appropriate corroborators** so the set is
monotone-or-flat in stress rather than decreasing — candidates: realized-vol expansion
persistence, downside-participation breadth (share of names making new lows), credit
follow-through after the first widening. Display tier first; escalation weight only
after the gate.

**Pre-registered acceptance gate.**
1. Monotonicity check (the actual claim of this item): binning sessions by realized
   drawdown depth, the count of *available* (precondition-satisfied) corroborators must
   be non-decreasing across bins, on 1997-2026. A candidate that does not restore
   monotonicity fails regardless of any accuracy improvement.
2. To carry escalation weight, the new corroborator must lift the conditional
   P(SPY ≥ 5% pullback, 21 sessions) over the state's own base with a 95% CI excluding
   1.0 — and must do so in the **decline** bins specifically, not on the full sample.
3. Same-tape check: max pairwise co-firing with any existing corroborator ≤ 0.7,
   otherwise it is retained as confluence only.
4. Both split-halves same sign.
5. No existing weight moves in the same change.

**Replay plan.** Reconstruct the corroborator availability series over history from the
conditions gauges, bin by drawdown depth, and report the availability-vs-depth table
(the monotonicity evidence) before any accuracy measurement. Accuracy is measured only
for candidates that pass (1).

---

## §11 `risk_radar` `caution` carries an h21 lift below 1.0 yet de-grosses

**Defect.** `_PROB_CAL["h21"]["caution"] = 0.16` against
`_PROB_BASE["h21"] = 0.178` (`engine/risk_radar.py:237, 239`) — a lift of **0.90**, i.e.
the `caution` state is associated with a *lower* 21-session pullback probability than
the unconditional base rate. Yet `caution` carries a gross reduction
(`RISK_STATE_GROSS["caution"]`, `engine/risk_radar.py:243-250`). The file's own comment
at `:259` already concedes this ("'caution' h21 is 0.16 against a 0.178 base rate"), so
the defect is *known and documented but not resolved*: a state that de-grosses on a
sub-1.0 lift is acting on an anti-signal at h21.

Possible readings, which the replay must distinguish: (a) the calibration table is
stale; (b) `caution` is genuinely informative at a horizon other than h21 (h5 lift
0.03/0.036 = 0.83, h10 0.08/0.086 = 0.93 — both also below 1.0, which weakens this
reading); (c) `caution` is a *sequencing* state (it precedes `elevated`) whose value is
not in its own conditional probability.

**Evidence pointer.** `engine/risk_radar.py:233-239` (`_PROB_CAL`, `_PROB_BASE`),
`:243-250` (`RISK_STATE_GROSS`), `:259` (the existing acknowledgement);
`data/risk_radar/calibration.json` for the live override table.

**Proposed change.** Re-examine, then one of: (a) recalibrate `_PROB_CAL` from the
current forward-outcome log; (b) remove the gross reduction from `caution` and let it be
a watch-only state; (c) keep the reduction and justify it on a *sequencing* basis, in
which case the sequencing claim itself needs measuring and the panel must stop implying
a probability lift.

**Pre-registered acceptance gate.**
1. Recalibration from the forward log ships only if it is derived on a leak-free frame
   and reported with per-state Wilson CIs; a state whose CI includes the base rate must
   be labelled "no measured lift" on the surface, not silently kept.
2. Keeping the gross reduction requires the sequencing claim to clear its own bar:
   P(`elevated` or `risk-off` within 21 sessions | `caution`) ≥ 1.3× P(same |
   `watch`), CI excluding 1.0, both split-halves.
3. If neither (1) nor (2) passes, option (b) ships — `caution` stops de-grossing — and a
   `DO_NOT_REBUILD.md` row records that the state carries no measured h21 lift.
4. No band threshold (`watch` 55 / `caution` 68 / `elevated` 78 / `risk_off` 88) moves in
   this item; that would be a separate pre-registration.

---

## §12 The US radar ceiling applies with no earn-in while CN/HK/CA require 30 graded + 8 alerts

**Defect.** The non-US radars must *earn* their ceiling authority (a documented
predicate of 30 graded outcomes + 8 alerts) before the ceiling binds, but the US radar's
ceiling applies immediately with no equivalent earn-in. Same mechanism, two different
authority predicates, and the asymmetry is not registered anywhere — it is not in
`research/DISPLAY_VS_SCORING_MANIFEST.md` (checked 2026-07-29: the manifest has
scoring-seam and display-seam sections, with no row for the radar-ceiling earn-in
asymmetry).

Either the US ceiling is justified by evidence the others lack — in which case the
predicate should say so — or it is an unexamined default, in which case the US surface
is asserting authority the house rule denies its siblings.

**Evidence pointer.** `engine/risk_radar.py` ceiling application and the market-scoped
corroborator/earn-in handling (`:633` notes CN/HK/CA lack the US conditions gauges);
`research/DISPLAY_VS_SCORING_MANIFEST.md` (no such row);
`docs/site_semantics/macro.md` Risk Radar section (states the ceiling without an
earn-in condition).

**Proposed change (either is acceptable; pick one deliberately, do not leave it
implicit).**
* **A. Register the seam.** Add a `DISPLAY_VS_SCORING_MANIFEST.md` scoring-seam row
  stating exactly why US differs — naming the evidence that earns it — and surface the
  difference in the semantics doc. Zero behaviour change; ships freely.
* **B. Give US the same predicate.** Require 30 graded outcomes + 8 alerts before the US
  ceiling binds, matching the siblings. This is a behaviour change and needs the gate.

**Pre-registered acceptance gate** (for B):
1. Applying the predicate retroactively must not increase the count of
   under-warned sessions (sessions where the ceiling would have bound but did not, and
   a ≥5% pullback followed within 21 sessions) by more than 10% vs today.
2. The US radar's graded-outcome count as of the replay date is reported first — if it
   already exceeds 30 graded + 8 alerts, B is a no-op today and A is the whole
   deliverable.
3. No band or ceiling magnitude changes in the same change.

**Recommendation:** run (2) first. It is a one-line count and it very likely makes this
a disclosure item rather than a recalibration.

---

## §13 The election-cycle band modulator lowers only `watch`/`caution`, widening the `caution`→`elevated` gap

**Defect.** `engine/election_cycle.modulation` returns a `band_delta` that
`engine/risk_radar.py:868-873` subtracts from the `watch` and `caution` cuts **only**,
explicitly never touching `elevated`/`risk_off` so the calendar cannot manufacture a
loud banner. Correct as a safety property — but the side effect is that the
`caution`→`elevated` distance **widens** by exactly `band_delta` during the modulated
window. So in the one slice the modulator judges more dangerous (a midterm Apr-Oct
window while the tape is still risk-on), it becomes *easier* to enter `caution` and
*relatively harder* to progress out of it into `elevated` — the states get more
sensitive at the quiet end and the escalation step gets longer at the same time.

Compounding it: `risk_radar.py:1264` notes the conjunction count must use the same
election-nudged `caution` cut, so the nudge also feeds the conjunction logic, and the
context gate (`context_gate_live`) is what decides `risk_on`. When the context gate is
shut the modulator is inactive — which is when the gap is normal — so the widened gap
occurs specifically while the gate is open.

**Not a re-proposal.** `research/DO_NOT_REBUILD.md` line 84 REFUTES the election cycle
as a standalone signal, surviving only as this US-only modulator. This item does not
propose strengthening the calendar signal in any way; it asks whether an
asymmetric band nudge is the right *shape* for a modulator that is already display and
sizing only.

**Evidence pointer.** `engine/election_cycle.py:174-210` (`modulation`, `band_delta`,
`_BAND_NUDGE`, `_GROSS_MULT`); `engine/risk_radar.py:856-877` (application, and the
comment stating elevated/risk_off are deliberately untouched); `:1264` (conjunction uses
the nudged cut); `research/DO_NOT_REBUILD.md` line 84.

**Proposed change (one of).**
* **A. Gap-preserving nudge.** Shift `elevated` by the same `band_delta` so the ladder
  translates rather than stretches — while keeping the *absolute* floor that prevents a
  calendar-only loud banner (i.e. nudge `elevated` but require a non-calendar condition
  for the banner, which is already the case since the banner needs the broad tape).
* **B. Sizing only.** Drop `band_delta` entirely and keep only `gross_mult` — the
  modulator becomes a pure position-sizing prior, which is the use the refutation left
  standing, and the band ladder is untouched.
* **C. Disclose only.** Publish the active `band_delta` and the resulting cuts on the
  surface so the modulated ladder is visible. Ships freely; recommended regardless.

**Pre-registered acceptance gate** (for A or B):
1. Neither variant may increase loud-banner (`elevated`/`risk-off`) firings during the
   modulated window by more than 5% vs today — the refutation's boundary must hold.
2. A must reduce the mean time-in-`caution` during modulated windows by ≥ 15% without
   increasing under-warned sessions (defined as in §12) by more than 5%.
3. B ships if A fails (1) or (2) — removing an unmeasured band nudge needs no positive
   evidence, only the absence of harm under (1).
4. Both split-halves same sign for A; B is exempt (it is a removal).
5. `_BAND_NUDGE` and `_GROSS_MULT` magnitudes do not change in this item.

**Replay plan.** `engine/risk_radar_backtest.py` already applies `band_delta` per date
(`:113, :124, :156`), so all three variants are a config-level A/B over the same
backtest. Report state-occupancy, banner counts, and under-warned sessions per variant
over the modulated windows only, plus the full sample as a control.

---

## §14 Registry, ordering, and outcomes

**Dependency order** (later items measure against corrected baselines):
`§5 (engine OR-set)` → `§8 (declustering gap)` + `§9 (leg coverage)` → `§4 (dislocation
hysteresis)` and `§6 (threshold band)`. §1-§3 are regime-side and independent. §7 and
§10-§13 are independent, and §7's fail-closed correction and §12's count check should be
done first because they are cheap and may close their items outright.

**Ship-free-today (display/disclosure tier, no gate needed):**
§2's attainability test, §3's two display-tier flags, §4's trigger-margin publication,
§6 option A, §7's fail-closed `put_absent` derivation + manifest row, §9's coverage
disclosure, §12 option A, §13 option C.

**Outcome log** — one row per item, filled as each replay concludes. An empty
Outcome column means the replay has not run; it does not mean the item passed.

| § | Item | Tier | Replay run | Outcome |
|---|---|---|---|---|
| 1 | Hysteresis candidate-identity counter | authority | no | — |
| 2 | `shock_override_z` lattice attainability | display (test) | n/a (closed form) | — |
| 3 | Inflation-persistence + contradiction-floor flags | display → authority | no | — |
| 4 | `dislocation_active` min-duration | authority | no | — |
| 5 | Bootstrap on the engine's OR-set | measurement | no | — |
| 6 | 2.5% breakeven margin band | display (A) / authority (B) | no | — |
| 7 | `put_state` gates OSB eligibility | authority | no | — |
| 8 | Declustering gap 42bd < 63d horizon | measurement | no | — |
| 9 | `fedput_off` leg dead pre-2003 | measurement | no | — |
| 10 | Non-monotone amplifier set | display → authority | no | — |
| 11 | `caution` h21 lift 0.90 yet de-grosses | authority | no | — |
| 12 | US radar ceiling earn-in asymmetry | disclosure (A) / authority (B) | no | — |
| 13 | Election band nudge widens the caution gap | display (C) / authority (A,B) | no | — |

**On failure.** A failed gate closes the *specific construction tested*, not the search
space, and gets a `research/DO_NOT_REBUILD.md` row naming the construction, the ruler,
and the effective N. "Not found yet" is not "does not exist"; a factor that is null
standalone is retained as a confluence input.

---

## §14 — `bubble_leadership` goes CALM exactly when the leadership cohort breaks

**Status:** PROPOSED (construction critique — not a same-day bug fix). Added 2026-07-29
from the cohort-dispersion audit commissioned after the operator's "how do we signal to a
user crowded in semis" escalation.

**Defect.** `engine/risk_radar.py:613-615` builds the only cohort-aware leg in the radar as

```python
lead = (smh / smh.shift(63)) / (spy / spy.shift(63)) - 1.0   # leadership concentration froth
out["bubble_leadership"] = pcol(lead)
```

`pcol` is a rising-percentile = rising-risk convention (stated at `:562`), and the term is
not negated. So as SMH collapses against SPY the percentile *falls* and the leg contributes
**calm**. Its sibling `bubble_ext` (`:610`) is SPY's own distance from its 200dma — an
index-level measure that structurally cannot see a cohort bubble deflating underneath a held
index.

**Evidence (2026-07-28/29 stores).** The `bubble` scare scores **23.2 with
`firing_legs: []`** while, on the same vintage: `leadership_crack` state **BROKEN**
(`med_dd` −36.4%, 42/42 members, `index_dd` −2.2% — a 16.5x ratio),
SOXX **−25.0%** off its 252d high at **57.8%** realized vol, SMH **−20.8%**,
`breadth_split.spread_50` **−44.64** (the most negative value in the entire 293-observation
series: AI cohort 34.3% above 200dma vs non-AI 78.9%), index/median-name realized-vol ratio
**0.285 = 7.4th percentile of 3 years**, implied average correlation **0.081** vs a 0.152
median, and CBOE COR1M at the **1.4th percentile of 5,173 observations back to 2006**.

**Why this is NOT filed as a bug and fixed today.** Read literally, the leg measures froth
*accumulation*, and a deflating ratio is a truthful "froth is no longer accumulating"
reading. The complaint is that accumulation is the wrong construction for detecting a cohort
*break* — which is a construction critique, not a sign error. Changing it would move a
scored leg's contribution in the escalating direction on today's tape, i.e. exactly the
shape of an LLM originating an escalation. It therefore goes through the gauntlet.
Compounding reasons for restraint: the leg carries weight 0.15 and is unvalidated
(`lift_2020` 0.38 vs `_VALIDATED_MIN` 1.20), and `research/DO_NOT_REBUILD.md` row 117 KILLED
operator force-add of un-gauntleted directional calls to signal surfaces as a process class
after the 2026-07-11 Mag-7 incident.

**Proposed change (A/B, pre-registered).**
- **A — separate the two states.** Keep `bubble_leadership` as the accumulation read, and add
  a distinct `leadership_break` leg sourced from the existing `leadership_crack` engine
  (state, `med_dd`, and the `med_dd`-vs-`index_dd` ratio) so accumulation and rupture are not
  the same axis with opposite signs.
- **B — dispersion-aware representativeness, not a redder score.** Add an index
  *representativeness* state from the three dispersion estimators that already exist
  (`engine/dispersion.py`, CBOE COR1M in `data/cboe/cor1m.parquet`,
  `engine/rotation_corr.py`), applying the ratified `sector_fragmentation` doctrine
  (RC-R6/RC-R3, "aggregate reads not representative — legs disagree") one level up, at the
  index. This does not move the score; it qualifies it.

**Pre-registered acceptance gates (state BEFORE any replay).**
1. Cohort-break detection: on matched historical cohort ruptures (leadership_crack BROKEN
   with `index_dd` shallower than −5%), variant A must raise the `bubble` scare above its
   `watch` cut in ≥ 60% of episodes, where the current construction fires in 0%.
2. No false-alarm inflation: variant A must not raise `bubble` above `watch` on more than
   10% of all non-rupture sessions in the same sample (the current leg's own FP rate is the
   baseline, not zero).
3. Representativeness (B) is **display-tier by construction and stays display-tier** — it
   may never rank, size, or gate. Promotion to authority requires its own Wilson-CI lift
   ≥ 1.20 at h21 against the unconditional base, matching `_VALIDATED_MIN`.
4. PSS-CD1 (`DO_NOT_REBUILD.md` row 135) already freezes the correlation-one / low-dispersion
   crowding overlay as prospective-only accrual: nothing here may be presented as a validated
   crowding or sell gate, and forward accrual must start dark.

**Replay plan.** Cohort-rupture episodes are identified from
`data/leadership_crack/forward_log.jsonl` plus a reconstruction over the per-ticker panel
(775x1540 loads in 0.13s; full vol-ratio and dispersion series compute in 0.08s — the render
budget is not a constraint here). Declustering gap must be ≥ the outcome horizon per §8.
Report the null loudly if variant A fails gate 1: "cohort rupture is not detectable from
relative-strength percentiles" is a publishable result, and the display-tier
representativeness state (B) is independently valuable and does not depend on it.

**What ships WITHOUT this proposal.** The single highest-value change found by the audit
needs no engine work and no gauntlet at all: the sentence the operator asked for already
exists, correct and bilingual, at `templates/dashboard.html.j2:11585` — *"Leaders broken —
the median AI-hardware leader is 36% off its high while the index still holds"* — rendered
only inside the click-open `#dlg-risk` modal. Promoting that (plus the `breadth_split`
AI-vs-rest line, currently 10px at ~40% opacity, and the `dispersion` chip, currently killed
by a literal `{% if false and ... %}` at `dashboard.html.j2:13889`) to sit beside the
headline score as a *representativeness caveat on the index* is a template placement change
at display tier. The evidence was never missing and was never destroyed at aggregation — it
was rendered at 10 pixels or put behind a click.
