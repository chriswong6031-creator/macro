# US → CN handoff — score memory, full-population grading, and the horizon ladder

**From:** the US Prophet trend-intelligence program
(`research/PROPHET_US_TREND_INTELLIGENCE_MASTERPLAN_BY_FABLE.md` §W7; shipped PR #4555).
**To:** the CN Prophet program
(`research/CHINA_PROPHET_LOSER_INTELLIGENCE_MASTERPLAN_BY_FABLE.md`).
**Why now:** operator order, 2026-08-05 — *"we should be remembering the score that we
give picks, so that it can be logged into the ledger and so that we can later assess how
robust and correct our scoring system is. Because it would be a disaster if say the stocks
we score very high end up underperforming … (this applies to both US and China sides, so
communicate this back to China side to implement as well, **after you finish
implementing**)."* The US side is now merged, so the trigger condition is met.

This is the reciprocal of `CN_TO_US_PROPHET_HANDOFF_2026-08-04.md`. Same discipline: the
**method** transfers, the **coefficients and the horizon map do not**.

---

## 1. The order, in one sentence

A score that is displayed but never graded is an untested claim on the user's attention.
The fix is not a better score — it is a **record**: stamp every score, grade every stamped
row on a fixed ruler, and publish the scorecard nightly so a mis-calibrated ranker is
visible in days rather than discovered by a customer.

## 2. What the US shipped (the parts that port)

**(a) Full-population forward grader.** `engine/us_prophet_grades.py` +
`scripts/grade_us_prophet_candidates.py`, declared in `config/dag.yml` and wired into the
nightly between `build_site` and the miss-audit. It grades **every stamped candidate row**
(~1,579 curated, ~2,252 more once the scan tier stamps) rather than the ~12 that reach the
plan lane. Nightly-lane-gated (`ledger_lane.nightly_advance_enabled()` as the **first**
statement), idempotent (a second run the same night writes zero rows), policy-free, zero
authority.

**(b) The ruler is reused, never forked.** Forward marks come from
`engine.grading.forward_metrics`, pinned mark-for-mark against the door grader in a test.
Two graders that quietly disagree put two sets of numbers in the repo under one name.

**(c) `priority_score_scorecard`, published in the nightly miss-audit artifact.** Rank-IC
by date, P@k at k=1/5/10/25, decile lift, loser-rate by score decile. Structure is
**cohort → horizon → class with no pooled top-level figure** — deliberately, so no reader
can quote a number that averages across populations that were never comparable.

**(d) Storage shape.** Month-grouped **daily** parts. Parquet cannot append in place, so a
monthly file rewritten nightly cost a measured **6.30 GB/yr** of git history versus **0.57
GB/yr** for day parts. Reader helper globs the parts; no consumer knows they exist.

## 3. The horizon ladder — port the METHOD, adjudicate your own MAP

The US added `HORIZONS = (10, 21, 42, 63)` and a `signal_class` derived from labels the
board **already stamps** (`engine/cycles.py::STATE_DISPLAY` — nothing new was stamped),
then pre-registered `CHARTERED_HORIZON` (basing → H=63 primary, momentum → H=10) **inside
the nightly artifact, before any long-horizon row could mature**.

Origin: the operator observed that basing-class admissions (VALE, NEM — bought while still
building a base) were being judged on a 10-session ruler built for swing entries. A class
mismatch between the signal and its measurement is not a scoring problem; it is a
**measurement** problem, and it makes a good pick look like a bad one.

**Do not copy the US map.** Your tape mean-reverts; ours pays continuation. Your own exit
horse race (#4507) found **0 of 11 challengers beat H=10** on your record basis — that is
CN evidence that H=10 is your incumbent, and it must stay the headline until CN evidence
says otherwise. What ports is the *discipline*:

1. Grade every class at every horizon in the ladder — nothing hidden.
2. Fix the class → **headline** horizon map **before** the long-horizon data exists.
3. The existing record continues untouched as its own labeled cohort; any redefinition of
   the headline is a separate, dated operator adjudication.

Step 2 is the whole point: choosing each class's horizon *after* seeing which one flatters
it is the most inviting form of self-deception available to a desk that grades itself.

**The CN question this raises, for your data to answer:** your RAN_LATE continuation cohort
(83% win, excluded from featured) and your bounce_wait patience cohort are plausibly
different *classes* with different natural horizons. If they are, your class map has more
than one honest row in it.

## 4. Four traps we hit, so you do not

- **NaN takes down the whole document.** A zero-variance cross-section makes Spearman
  undefined; the resulting `NaN` reached the artifact, and `json.dumps` emits a bare `NaN`
  — invalid JSON that would have killed the entire nightly document over one degenerate
  night. Drop, count, state the reason, and pin with an `allow_nan=False` round-trip.
- **Resolve a column by name, then validate it by value.** Both conditioning columns
  (cohort, class) resolve from a candidate-name list and then confirm the values intersect
  the expected vocabulary. A name match alone is not the column you think it is; when it is
  absent, the block reads null with a printed `::warning` and says `unsplit` — it never
  silently defaults to a cohort.
- **Coverage is a finding, not a footnote.** Our priority score turned out to exist on only
  **3.2%** of stamped rows (it is computed for the buy lane alone). A single ranked column
  would have been 97% empty; filling it is a *scored* change, because the edge leg is a
  within-pool percentile and widening the pool moves every existing score. Filed as its own
  wave rather than smuggled in. **Check your own score's row coverage before you rank on
  it.**
- **Grade rows carry the cohort discriminator.** Ours is `universe_tier` (curated vs the
  wider scan set). Cohorts that were never selected the same way must never be pooled — the
  same law that keeps your v2/v3 eras apart.

## 5. What is NOT being suggested

The US class map, the US horizon ladder's headline choices, our scan-tier population, and
our score legs are all US adjudications on US evidence. **Five of five** CN findings have
now failed naive transport to the US tape (turnover monotone→bimodal, confirmation
negative→positive, membership quality→crowding, relay early→null, and — measured this week
— the patience/waiting extension: on the US tape, waiting **costs** 0.4–0.5pp on the same
cross, and our freshness-window widening was killed on a tight null). The fence in your own
§5 is now empirically strong in both directions: **shared spine, never shared
coefficients.**

## 6. The shared future, restated

Your memo's §6 stands and this program agrees: **one entry family cannot serve two
regimes**. Whoever builds regime-conditional entry-family weights first should build it
**market-agnostic** so the second desk consumes rather than re-implements. Add to it the
lesson of this handoff: whoever builds **class-conditional grading** should likewise build
the class→horizon machinery market-agnostic — the map is per-market, the mechanism is not.

*Cross-reference: `CN_TO_US_PROPHET_HANDOFF_2026-08-04.md` (the reciprocal),
`research/US_ALL_PICKS_SURFACE_CONTRACT.md` (the frozen surface contract for the ranked
all-picks view), `research/CONTEXT_VECTOR_SCHEMA_CONTRACT.md` §3.1 (the `stamp_date` family
key, now done on both sides).*
