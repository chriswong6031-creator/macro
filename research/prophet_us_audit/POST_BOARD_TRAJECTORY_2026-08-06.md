# Post-board trajectory — what Prophet US names do after they leave the board

**Date:** 2026-08-06 · **Instrument:** `research/prophet_us_audit/post_board_trajectory.py`
· **Frozen results:** `post_board_trajectory_results.json` (REPRO_ASOF `2026-07-31`)
· **Tests:** `test_post_board_trajectory.py` (27, synthetic sequences only)

---

## §0 Status

**RESEARCH TIER. This changes nothing.** No gate, lane, ranker, cap, surface, config or
engine file is touched by this work — the diff is three files under
`research/prophet_us_audit/`. Nothing below is a promotion, and no number here licenses
one. The measurement is descriptive: it grades a population the board had already
chosen, from the date the board stopped showing it.

Kills-check, matched by rule text and cited by stable key:

| Row | Why this construction is not it |
|---|---|
| `DNR:KILL-PROPHET-POP-MERGE` | Fences the graded-board **population**. This instrument reads published boards and writes nothing into them. The population is untouched. |
| `DNR:KILL-OUTCOME-AUDITION` | Forbids per-name selection of a timing tool **by outcome**. Every cell here is a cohort defined by a label the board itself stamped at departure. No per-name gate, rank, size or tool is chosen from any outcome. |
| Killed **leader-pullback-reset** family (`RESULTS_2026-08-03.md`, −1.50% pooled / −2.12% per-name-first on 938 fires; cited as "the §2.5 leader-family null" inside `DNR:KILL-FRESH-TICKS-WINDOW`) | That family **entered leaders on dips** — a new admission rule on the full universe. This study **never enters anything**. Its population is names the board had *already admitted*, its anchor is the date they *left*, and no cell contains a name that was not on the board. The two constructions share no fire. |
| `DNR:KILL-FRESH-TICKS-WINDOW` | Forbids widening the admission window (2→3/4). Nothing here proposes an admission change; `freshness_edge` is a descriptive departure class, and §4 explains why its positive number is **not** evidence for widening. |
| `DNR:KILL-OFFHORIZON-VERDICTS` | Verdicts only at registered horizons. The grid is the board's own registered ladder (`scripts/grade_us_board.HORIZONS = [5, 10, 21, 63]`); H=42 is reported as absent, never as a verdict. |

---

## §1 The question, and the three facts that raised it

Names leave the US board constantly and silently, and nobody had ever graded what they
did next. Three measured facts converged:

1. **The one stable positive in the program is the stage-ran cohort.** BUY-lane rows
   whose `entry_status` buckets to STAGE_RAN graded **14.5% loser vs 27.6%** for the rest
   of the buy lane (n=55, no half-split flip) — #4547,
   `label_grading_battery_results.json` §`section_3_ran_lane`. Names that already ran
   keep working *while on the board*.
2. **Departures were invisible until #4554.** The VALE forensic found a marginal
   admission dropped on a single bad bar while its gate state stayed eligible, and
   departed names had no track-record row at all until the row-persistence law was built
   (`BOARD_CONTINUITY_FORENSIC_2026-08-05.md`).
3. **The cascade is a FRESH-cross detector** (`FRESH_TICKS = 2`), so a name whose cross
   ages out is structurally un-readmittable — and widening that window was measured and
   KILLED three times (`DNR:KILL-FRESH-TICKS-WINDOW`, #4546/#4548).

The untested hypothesis that leaves: **the board may be dropping its own winners
mid-run.** If it is, the lawful response is a *retention/continuation surface*, never a
gate loosening. This document answers whether it is.

---

## §2 Method, taxonomy, and the frame that actually exists

### 2.1 Four deltas from the commissioning brief — census first

**(a) The membership frame is nearly twice as wide as the brief assumed.** The brief
pointed at `snapshots.jsonl` + `snapshots_v2.jsonl` (17 and 12 dates). The production
grader does not read those alone: `scripts/grade_us_board.collect_boards` unions them
with the **git history of the published board artifact**. Doing the same is the only way
to see the board before 2026-06-30 at all.

| Family | as_of from snapshots | as_of from git history | total | range |
|---|---|---|---|---|
| v1 (`us_standouts.json`) | 17 | 15 | **32** | 2026-06-15 → 2026-07-31 |
| v2 (`us_standouts_v2.json`) | 12 | 10 | **22** | 2026-06-30 → 2026-07-31 |

**(b) The frame still ends 2026-07-31, and that end is a censoring boundary, not a mass
departure.** Board-artifact commits exist through 2026-08-05, but every one of them
carries `as_of` 2026-07-31 — the collect outage, which `BOARD_CONTINUITY_FORENSIC` §0
records was never backfilled. The 152 episodes still on the 07-31 board are therefore
**right-censored** and are reported in their own bucket. Reading them as departures would
have invented 152 exits out of an outage.

**(c) H=42 and H=63 are structurally unmeasurable here — n=0, by arithmetic.** The widest
forward budget on this frame is **32 sessions** (2026-06-15 → 2026-07-31); the earliest
*detectable* departure is 2026-06-16, at 31. The brief's central ask — "what did holding
through H=63 earn versus dropping at departure" — **cannot be answered on any frame that
exists today**, and no amount of care would change that. It is printed as absent with the
arithmetic receipt (`frame_budget.per_board_date`) rather than approximated.

| Horizon | Latest drop date that matures | Buy-lane departures matured |
|---|---|---|
| H=5 | 2026-07-24 | 852 |
| H=10 | 2026-07-17 | 754 |
| H=21 | 2026-07-01 | 577 |
| H=42 | — | **0** |
| H=63 | — | **0** |

**(d) `entry_status` is far better populated than the brief's 43.9% warning, but the gate
state is far worse.** On buy-lane board rows: `entry_status` is null on 19.6% (all of it
the first three dates), but `eligible` / `ticks` are null on **47.6%** — the whole first
era — and `tier_cascade` on 65.8%. Any taxonomy leaning on the gate block is blind for
half the frame, and says so.

### 2.2 The board changed construction five times in 32 dates

This is the largest single finding about the frame, and it is detected from the boards
themselves (`detect_era_breaks`), not hand-listed:

| Date | What changed (buy lane) |
|---|---|
| 2026-06-23 | `rank_by` conviction → bottoming-alignment |
| 2026-06-25 | lane size level 120 → 32 (step 120 → 33 on the day) |
| 2026-06-26 | the gate-state block appears (readable share 0.00 → 1.00) |
| 2026-07-17 | `rank_by` bottoming-alignment → confluence, **and** eligible-share 0.20 → 1.00 |
| 2026-07-28 | lane size level 43 → 78 (step 44 → 80 on the day) |

A departure whose drop date is one of these is a **construction change, not a signal
event**, and is classed `roster_break`. The detector is a level-shift test de-smeared to
the day the step landed, with a drift guard (a cap change is a *step*; a board emptying
over a week is *drift*) and an absolute floor (an 18→10 lane is churn, not a re-cap).
Both guards are mutation-verified, and the one known limitation — two cap steps inside
three boards collapse to the first — is pinned by a named test rather than left to be
rediscovered.

The consequence for reading §3: **the H=10-gradeable window is dominated by
constructions that no longer exist.** The current gate (era from 2026-07-17) contributes
essentially one gradeable drop date at H=10. Every number below describes boards the
desk has already replaced.

### 2.3 Departure detection

Episodes are contiguous runs over **each lane's own board-date sequence** — the dates on
which that lane's key existed in the artifact. A calendar gap therefore cannot
manufacture a departure, and a lane being born (`leaders`, 2026-07-28) or retired cannot
either. A departure is an episode whose last board date is followed by a board where the
name is absent; the **drop date is that next board**, because that is the first day a
holder could have acted on the disappearance.

Independent corroboration: the detector reproduces the two VALE episodes the #4554
forensic identified by hand — `2026-07-24 → 2026-07-28` (departed 07-29) and
`2026-07-30 → 2026-07-31` (censored) — with no VALE-specific code.

Census: **3,272 board rows · 872 tickers · 1,648 episodes · 1,496 departures · 152
censored · 536 re-entries** (median **3 board dates** out before readmission). Roughly a
third of all episodes are re-entries of a name that had already left — the board churns
its own roster far more than a "dropped forever" framing implies.

### 2.4 The taxonomy, and why it is reported two ways

Nine exclusive classes, priority-ordered, every one with a fire count so an empty class
is visible: `roster_break` → `lane_move` → `ran_advanced` → `veto_blocked` →
`freshness_edge` → `gate_ineligible` → `weak_tier` → `still_eligible_absent` →
`gate_state_absent`.

Two deliberate choices: `ran_advanced` outranks the gate classes because it is the
hypothesis under test and reads a field that is ~100% populated from 2026-06-18; and
`gate_ineligible` is kept **distinct from** `veto_blocked` because before 2026-07-17
`eligible = False` was the *modal* state of the buy lane — calling it a veto there would
be a misassignment, and a misassigned class is worse than an honest unknown. Every row
also carries every non-exclusive flag it satisfies, so overlap is visible rather than
hidden by the priority order.

### 2.5 Prices — coverage, and one basis defect found by hand-check

100% of the 872 board tickers resolve (0 unresolved), on a 2,946-name panel:

| Source | Board tickers resolved |
|---|---|
| `data/baskets/ohlcv` | 695 |
| `data/yahoo` | 20 |
| `data/stocks` | 1 |
| breadth closes caches (**unadjusted** — see below) | 156 |

**The ladder is adjusted-first, and it had to be.** Hand-checking six departures against
raw parquet initially produced four exact matches and two misses of ≈0.68pp each — a
systematic gap, not noise. Cause: **the breadth closes caches are forward-accruing** —
each session's close is written as-of and never retro-adjusted — while `baskets/ohlcv`
and `yahoo` carry back-adjusted history. Measured at 2026-06-22, CFG reads 67.9900 in the
cache vs 67.5514 in baskets and ALLY 45.5700 vs 45.2556, while both agree to the cent at
2026-07-07 (after the ex-div) and every name with no ex-div in the window agrees exactly
across all four sources — including the payers JPM and KO. A cache-priced name therefore
**books its own dividend as a loss**, and SPY is only available adjusted, so a
cache-primary panel puts a dividend-shaped bias into every excess-vs-SPY number in this
file. Expected size at H=10 is ~0.06pp — small, but the same order as the deltas being
reported. After re-laddering to adjusted-first, all six hand-checks match to 1e-4. 156
board tickers still fall back to the unadjusted cache; that count is printed in the
results, not hidden.

**Price pin.** REPRO_ASOF `2026-07-31` pins the board frame *and* every price series.
Prices exist to 08-04 for a minority of names, but extending the pin buys 2 sessions
while only **20 / 872** board tickers print past 07-31 — so it manufactures *truncation*
(41 extra truncated rows at H=10) rather than maturity, and moves the headline from
+0.01pp to −0.16pp. Reported as a labelled sensitivity; the pin stays at the common
ceiling.

**Survivorship convention (stated).** A name whose series stops before the horizon is
**kept**, liquidated at its last print, and counted in `n_truncated` (3 / 6 / 9 rows at
H=5/10/21); every headline is reprinted excluding them. A name with no resolvable price
is counted `unpriced` and named — there are none. Dropping either silently is exactly how
a post-departure study deletes its own losers.

**Loser threshold:** excess vs SPY < **−3pp** at the horizon, stated, with medians printed
beside every rate so no verdict hangs on it.

---

## §3 Results

### 3.1 The headline: dropped vs KEPT on the same board date

SPY and the universe median answer "did departed names beat the market". Neither answers
"did the board drop its *better* names" — both denominators contain thousands of names
the board never considered. The matched contrast holds the board's own population and its
own decision date fixed: on board date *d*, **KEPT** = names present on both *d−1* and
*d*; **DROPPED** = names on *d−1* and not on *d*; both anchored at *d*.

**Primary read — excluding construction seams** (buy lane, excess vs SPY, pp):

| H | dropped n | dropped med | dropped per-name | kept n | kept med | kept per-name | **Δ med** | **Δ per-name** | Δ loser rate |
|---|---|---|---|---|---|---|---|---|---|
| 5 | 581 | +1.45 | +1.34 | 560 | +1.90 | +2.27 | **−0.45** | **−0.93** | +1.5pp |
| 10 | 483 | +1.33 | +1.09 | 439 | +1.66 | +2.00 | **−0.33** | **−0.91** | −1.2pp |
| 21 | 333 | +2.26 | +1.99 | 364 | +2.53 | +2.13 | **−0.27** | **−0.14** | +0.1pp |

Negative Δ = the board kept the better names. The deltas are **a fraction of a
percentage point at every horizon**, the loser-rate gap flips sign across horizons, and
the effect shrinks as the horizon lengthens. On the daily decision, dropping and keeping
are close to indistinguishable in outcome.

**Including construction seams** — the same table, showing where the apparent effect
lives:

| H | dropped n | dropped med | kept n | kept med | **Δ med** | **Δ per-name** | Δ loser rate |
|---|---|---|---|---|---|---|---|
| 5 | 852 | +0.91 | 590 | +1.82 | −0.91 | −1.24 | +5.6pp |
| 10 | 754 | +0.01 | 469 | +1.57 | −1.56 | −1.80 | +6.2pp |
| 21 | 577 | +1.09 | 393 | +2.50 | −1.41 | −1.19 | +2.6pp |

The delta is **3–5× larger** once the roster cuts are included. The only place the drop
decision looked like it mattered is where a configuration change re-cut the roster — and
that cohort's raw number is largely a date effect (4 drop dates; raw −2.32pp but
date-demeaned **+0.21pp**).

The counterfactual, stated as the identity it is: dropping at departure earns **zero**
excess from the drop date onward, so the drop-anchored distribution *is* the
hold-minus-drop delta. It is not a second measurement.

### 3.2 By departure class, H=10, buy lane

Read the demeaned and universe-median columns, not the raw one: several classes are
concentrated on few drop dates, where the raw number carries that day's market move.

| Class | n / names | loser % | med | **demeaned** | **vs univ. median** | per-name | dates | vs rest | half-split flip | max sector |
|---|---|---|---|---|---|---|---|---|---|---|
| `roster_break` | 271 / 254 | 44.3 | −2.32 | **+0.21** | −0.81 | −2.24 | 4 | −3.33 | no | 18.5% |
| `lane_move` (all → watch) | 28 / 23 | 28.6 | +3.81 | **+2.78** | +1.08 | +3.31 | 6 | +3.63 | no | 21.4% |
| `ran_advanced` | 145 / 135 | 29.7 | −0.15 | **−0.16** | +0.25 | −0.27 | 13 | −0.01 | **YES** | 33.1% |
| `veto_blocked` | 15 / 15 | 26.7 | +1.04 | +1.68 | −3.16 | +1.04 | **2** | +1.36 | no | 46.7% |
| `freshness_edge` | 115 / 102 | 20.0 | +2.12 | **+0.48** | +1.81 | +2.31 | 12 | +3.04 | no | 18.3% |
| `gate_ineligible` | 12 / 12 | 8.3 | +1.16 | −1.57 | −0.14 | +1.16 | 7 | +1.42 | **YES** | 25.0% |
| `weak_tier` | 3 / 3 | 33.3 | +2.53 | +0.12 | +0.99 | +2.53 | 3 | +2.79 | — | 33.3% |
| `still_eligible_absent` (VALE class) | 19 / 18 | 21.1 | +1.48 | −1.02 | +0.51 | +1.51 | 12 | +1.85 | no | 15.8% |
| `gate_state_absent` | 146 / 138 | 28.8 | +2.00 | **+0.56** | −0.42 | +1.67 | 5 | +2.37 | no | 30.1% |

Thin cells, flagged as such and directional only: `veto_blocked` (n=15, **2 drop dates**,
46.7% one sector — the demean is degenerate there and the instrument says so),
`gate_ineligible` (n=12), `weak_tier` (n=3), `still_eligible_absent` (n=19). Base for
comparison: all buy-lane departures at H=10 are n=754, loser 32.6%, median +0.01pp.

### 3.3 The receipt that governs the whole taxonomy: no stamped field predicts departure

For each classification flag, its rate among names that **left** vs names that **stayed**,
on the *same* (lane, board-date) pairs — 1,496 departed vs 1,623 stayed:

| Flag | departed | stayed | **lift** |
|---|---|---|---|
| ran status (`extended`/`hold`/`topping`) | 28.9% | 29.6% | **−0.7pp** |
| `cycle_blocked` | 13.6% | 23.5% | **−9.9pp** |
| `eligible = False` | 28.3% | 40.4% | **−12.1pp** |
| `ticks ≥ FRESH_TICKS` | 39.8% | 49.7% | **−9.9pp** |
| `tier_cascade` ∈ {T3, T4} | 1.5% | 1.0% | +0.5pp |
| **bottom quartile of its lane** | **28.7%** | **20.1%** | **+8.6pp** |

Every stamped *state* field has zero or **negative** lift — a blocked, ineligible or
aged-out name is *less* likely to leave than a clean one. The only positive is **rank
position**. Departure from this board is **rank displacement**, not a state event. That
reframes the taxonomy honestly: it is a well-defined partition of the departing
population, but it is **not an explanation of why names leave**, and no class outcome
below should be read as "the reason X causes outcome Y".

---

## §4 What this does and does not support

**It does not support "the board is dropping its winners."** On the primary read the
dropped and kept cohorts are within a fraction of a point of each other at every
measurable horizon, with the sign of the loser-rate gap unstable. There is no measurable
cost to the daily drop decision on this frame.

**The stage-ran result does not extend past departure.** `ran_advanced` at H=10 is
median −0.15pp, demeaned −0.16pp, per-name-first −0.27pp, **−0.01pp against the rest of
the departures**, and its half-split **flips sign**. At H=5 it is +0.46 raw / +0.14
demeaned (−0.62 vs rest). At H=21 the raw +1.52 inverts to **−0.99 demeaned** on 5 drop
dates with 40.5% of the cohort in one sector. And the ran label has **−0.7pp lift** — a
name that ran is no more likely to leave than one that did not. Once a stage-ran name
leaves the board, it does nothing in particular.

**So the lawful next step is neither branch of the brief as written.** The brief offered:
if the ran class holds up → a retention/continuation *surface* question; if not → "the
stage-ran result was a small-n artifact, close the thread." The measurement supports
**closing the continuation thread** but **not** the artifact claim, and the distinction
matters:

- **What closes:** the *continuation* hypothesis — that a ran name keeps working after
  it leaves, and therefore deserves a retention surface that keeps it visible with its
  own horizon. There is no measured support for that on this frame. A retention surface
  built on this evidence would be showing users a cohort with no measured edge.
- **What does NOT close:** #4547's admission-anchored finding. That measured a different
  anchor (board admission) over a different window on a different population (n=55
  matured ledger rows vs n=145 ran departures here). **This study cannot adjudicate it in
  either direction**, and calling it a small-n artifact on this evidence would be exactly
  the "comparing across measures" error the house has already paid for once. It stands or
  falls on its own accrual.

**`freshness_edge` is the most positive class, and it is NOT evidence for widening
`FRESH_TICKS`.** Its +2.12pp raw collapses to **+0.48pp demeaned**, so most of the raw
number is a date effect. More decisively, `DNR:KILL-FRESH-TICKS-WINDOW` already measured
this exact shape and named it: the within-admission cross-age gradient re-reads as
**board selection**, not confirmation pricing (era-matched delta 12.7–18.3pp, with the
state-population gradient running the *opposite* way), and paired same-cross entry at
tick 3/4 **costs** −0.53/−0.38pp. My cohort is board-selected by construction — every
name in it was already admitted — so it is the selected subset that row describes, not
independent evidence against it. The kill stands untouched.

**The `lane_move` class is the one genuinely interesting positive**, and it survives
demeaning: 28 buy-lane names that moved to `watch` earned +3.81pp raw / **+2.78pp
demeaned** / +3.31pp per-name at H=10, having already earned +2.22pp while on the buy
lane. n=28 across 6 dates is thin and the destination is 100% one lane, so this is a
**lead, not a finding**. It is also the cohort that *did not actually leave the board* —
which, if it survives accrual, is an argument about lane semantics, not about retention.

**Everything here describes superseded boards.** Four of the five construction seams
predate the current gate, and the H=10-gradeable window contributes roughly one drop date
from the era running today. Any read that assumes the current board behaves like this one
is unsupported.

---

## §5 The honest nulls

1. **H=42 and H=63: n=0.** Not thin — arithmetically impossible. The brief's central
   counterfactual ("what did holding through H=63 earn") is unanswerable on any frame
   that exists today. It becomes answerable ~63 sessions after the board resumes
   accruing, i.e. not before **early November 2026**, and only if the collect outage
   past 2026-07-31 is repaired so the frame extends at all.
2. **The kept-vs-dropped delta is reported without a confidence interval.** The kept
   cohort re-observes a name on every board date it survived, so its rows are heavily
   overlapping and its n is not an independent sample size. A date-blocked bootstrap
   over 21 drop dates would be the right apparatus and is not run here; the deltas are
   reported as point estimates with their overlap disclosed, and nothing is claimed to
   exclude zero.
3. **The taxonomy explains the population, not the departures.** Every stamped state
   field has zero or negative lift against survivors (§3.3). The classes are a valid
   partition and a poor causal story, and no class outcome should be read causally.
4. **The current gate is essentially ungraded.** The era from 2026-07-17 contributes ~1
   gradeable drop date at H=10. Everything measurable describes constructions the desk
   has replaced.
5. **`veto_blocked`, `gate_ineligible`, `weak_tier`, `still_eligible_absent` are all
   thin** (n=15/12/3/19 at H=10) and two of them sit on ≤2 drop dates, where the
   date-demeaned column is a within-cohort deviation rather than a control. Directional
   only. The VALE class specifically — the one that motivated the forensic — has n=19 and
   cannot carry a verdict either way.
6. **156 of 872 board tickers are still priced on the unadjusted forward-accruing cache**
   (§2.5), so their measured returns understate total return by any dividend paid inside
   the window. The bias is symmetric between the dropped and kept cohorts, so the Δ
   columns are essentially clean; the absolute excess-vs-SPY levels are not.
7. **Sector concentration is disclosed and is high in the thin cells** — 46.7% single
   sector in `veto_blocked`, 40.5% in `ran_advanced` at H=21, 33.1% at H=10. The
   aggregate is better behaved (max 22.0% Financials).
8. **Two board families were measured; only v1 carries usable weight.** v2
   (`entry_open` / `setting_up`) contributes 184 rows over 22 dates with the gate block
   **100% null**, so its departures land almost entirely in `gate_state_absent`. It is
   censused, not interpreted.
9. **Re-entry is not graded.** 536 episodes (a third of all episodes) are re-entries with
   a median of 3 board dates out. Whether a re-entered name performs differently from a
   first admission is a separate, answerable question this instrument sets up but does
   not measure.
10. **One detector limitation is known and pinned, not fixed:** two cap steps within
    three board dates collapse to the first. Inert on this frame; it would need a
    per-step changepoint pass, not a threshold tweak.
