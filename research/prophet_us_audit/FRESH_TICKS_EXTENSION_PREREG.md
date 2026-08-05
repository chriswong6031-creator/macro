# W5.2 — FRESH_TICKS extension: pre-registration and ratification memo

**Rung:** `PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §3, queue position 1.
**Instruments:** `research/prophet_us_audit/fresh_ticks_extension_replay.py` +
`fresh_ticks_extension_replay_results.json` (frozen), `tests/test_fresh_ticks_extension_replay.py`.
**Parent evidence:** §5 S-B (`superintelligence_standins.py`). **Date:** 2026-08-04.

---

## §0 STATUS — read this before anything else

**PRE-REGISTERED, NOT RUN FORWARD. This document changes NO gate. `FRESH_TICKS` is
untouched by the PR that carries it.** The scored change it describes is W5-class and is
sequenced behind BOTH G0.2 (five green W0 nightlies) AND explicit operator ratification.
Forward races confirm, they never block (fast-track doctrine, roadmap §0.3).

**And the finding this packet must lead with: the frozen-frame replay does NOT support the
extension.** The proposed decision bars below are therefore written for a question whose
retro evidence currently points the other way. That is the honest state, and it is what
makes the bars worth pre-registering rather than quietly dropping — a bar written after
seeing a null is worth less than one written before the forward data arrives.

---

## §1 The question

`engine/confluence_tiers.FRESH_TICKS = 2` expires a cross's buyability after two ticks on
the signal's own timeframe. S-B measured, WITHIN actual board admissions on the frozen
`retro_grades` buy/H=10 frame, that outcomes improve with cross age right up to that
boundary:

| cross age | n | loser rate | median excess | date-demeaned median |
|---|---|---|---|---|
| ticks 0 | 53 | 20.8% | +1.54pp | +0.10pp |
| ticks 1 | 30 | 10.0% | +2.77pp | +0.92pp |
| ticks 2 | 26 | 11.5% | +5.06pp | +3.04pp |

The W5.2 question: does that gradient **extend** to ticks 3–4 — the cohort the freshness
gate currently excludes — or does it **peak at the boundary**?

This is gate-boundary measurement of an existing, already-shipped signal. It makes no
pre-onset claim about what a winner looks like before it moves (DNR rows 114–115), forces
no leadership call (row 117), and changes no graded population (row 49): the curated
universe is untouched either way, and only the admission *window* is at issue.

---

## §2 What the frozen-frame replay measured

**Construction.** `tier_stream` already exposes `fresh_ticks` as a documented knob-sweep
override, so the counterfactual required no re-derivation: the same production function was
called twice over the same full-universe panel (1,540 names × 777 sessions from the three
breadth closes caches, pinned at **2026-07-31**), once at the shipped gate and once with the
freshness clock — and only the freshness clock — extended. Every other leg (the not-topped
veto, `long_bias`, `recent3`/`confirm3`, `rsi_ok`, the T3 persistence hardening) is
re-evaluated per day by the engine itself under both settings. Primary unit = one row per
(cross episode, tick level); outcomes on a next-bar fill matching `engine.grading`.

**Receipts, all passing.**

| check | result |
|---|---|
| S-B `by_cross_age_ticks` reproduced from current stores | **PASS — exact**, cell for cell (53/30/26 · 20.8/10.0/11.5 · +0.10/+0.92/+3.04) |
| leg reconstruction vs `tier_stream`'s own output | **0 mismatches / 939,611 name-days / 1,493 names** (`not_topped` every day; `ticks` every admitted day) |
| extension knob is a pure widening (never drops an admitted session) | pinned in tests |
| ticks ≤ 2 states already on the board (construction invariant) | **0 violations** |
| all 11 admission/veto legs fire (dead-leg check) | 11/11 fire |

### 2.1 The tick walk is flat — the gradient does not extend, and it is not there to extend

Episode-tick unit, marginal states only. Eval window 2023-06→2026-06, 755 sessions.

| cross age | n | names | loser rate | median excess vs SPY | date-demeaned | vs universe median | per-name median | H=21 median | gate status |
|---|---|---|---|---|---|---|---|---|---|
| 0 | 9,003 | 1,485 | 31.2% | −0.25pp | −0.25pp | +0.01pp | −0.13pp | −1.14pp | admitted |
| 1 | 8,600 | 1,458 | 31.3% | −0.34 | −0.24 | −0.00 | −0.35 | −1.29 | admitted |
| 2 | 5,008 | 1,405 | 32.5% | −0.59 | −0.28 | −0.03 | −0.41 | −1.33 | admitted |
| **3** | **2,875** | **1,289** | **32.6%** | **−0.71** | **−0.18** | **−0.01** | **−0.48** | **−1.18** | **EXCLUDED — the question** |
| **4** | **1,809** | **1,113** | **32.2%** | **−0.70** | **−0.29** | **−0.23** | **−0.56** | **−0.93** | **EXCLUDED — the question** |
| 5 | 1,353 | 947 | 34.7% | −0.88 | −0.12 | −0.02 | −0.77 | −1.08 | decay context |
| 6 | 1,000 | 761 | 32.4% | −0.44 | +0.08 | +0.12 | −0.38 | −0.95 | decay context |

### 2.2 The headline contrast is a TIGHT null, not an underpowered one

ticks-3/4 marginal (n=4,684, 1,315 names) vs ticks-0/2 admitted (n=22,611, 1,486 names):

| measure | delta (ext − admitted) | 95% interval |
|---|---|---|
| date-demeaned median excess | **+0.04pp** | **[−0.18, +0.24]** (date-blocked bootstrap, 449 day-blocks, 1,000 draws) |
| loser rate | **+0.9pp** | **[−1.9, +3.6]** |
| per-name median | −0.17pp | — |
| H=21 median | +0.16pp | — |
| loser rate, Wilson (over-tight — see note) | 32.4% [31.1, 33.8] vs 31.5% [30.9, 32.2] | overlapping |

The bootstrap interval straddles zero **and is narrow**: the effect, if one exists, is
smaller than ±0.25pp of demeaned median. This is not "we could not tell" — it is "there is
nothing here at a size worth a gate change". Half-split robustness agrees and flips sign:
+0.13pp first half, −0.10pp second.

*(The Wilson intervals are printed because a reader expects them, and labelled: rows inside
one tick bucket are the same cross on consecutive days, so Wilson reads tighter than the
data earns. The date-blocked bootstrap is the honest interval — one trading day is one bet.)*

### 2.3 The mechanism block says waiting COSTS

Same cross, entered at tick 0 vs at tick 3/4 (paired, so cross quality cancels):

| pair | crosses | median at tick 0 | median late | paired delta | % where late is better |
|---|---|---|---|---|---|
| tick 0 → 3 | 2,645 | −0.03pp | −0.74pp | **−0.53pp** | 46.5% |
| tick 0 → 4 | 1,688 | −0.22pp | −0.68pp | **−0.38pp** | 47.5% |

So the marginal-admission contrast is flat *because* two effects cancel: crosses that
survive to tick 3–4 are modestly better crosses, and entering them late is modestly worse.
Neither is large. Nothing in this pair of readings argues for widening the window.

### 2.4 S-B's gradient is board selection, not cross age

Era-matched to S-B's own month (2026-06-16..07-16), the same tick levels on the state
population vs S-B's measured admissions:

| cross age | synthetic n | synthetic loser | S-B n | S-B loser | **selection delta** |
|---|---|---|---|---|---|
| 0 | 233 | 33.5% | 53 | 20.8% | **12.7pp** |
| 1 | 244 | 28.3% | 30 | 10.0% | **18.3pp** |
| 2 | 180 | 27.8% | 26 | 11.5% | **16.3pp** |

The board's own selection layer — the §7 master marker, the ranking, the cap — is worth
**12–18pp of loser rate**, an order of magnitude more than anything cross age does. And on
the demeaned median the state population runs the *opposite* way to S-B in the same month
(+0.92 / +0.51 / +0.23, declining) while S-B rises (+0.10 / +0.92 / +3.04). S-B's monotone
gradient is a property of *which names the board admitted*, not of how old their cross was.

That reading is the packet's most durable output, and it generalises past this rung: a
within-admissions gradient measured on a ranked, capped board is a statement about the
ranker until someone removes the ranker and re-measures.

### 2.5 What actually excludes aged crosses is the veto, not the clock

Leg mix of blocked T1-clock sessions (first failing leg, engine evaluation order):

| clock | blocked sessions | stoch_ob | stoch_bear | macd_bear (cross broke) |
|---|---|---|---|---|
| 2 | 19,093 | 69% | 27% | 4% |
| **3** | **22,996** | **59%** | **40%** | **0.5%** |
| **4** | **24,104** | **57%** | **41%** | **3%** |
| 6 | 22,552 | 52% | 39% | 9% |

At ticks 3–4 the cross itself has almost never broken (`macd_bear` 0.5–3%). The population
is culled by *overbought* and *rolled-over* stochastics. The freshness clock and the
not-topped veto are therefore **not redundant**: there is a real, veto-cleared population
that only the clock excludes — 4,684 episode-tick entries, **+16.5% board widening**
(+17.8 eligible sessions per night). The extension would genuinely add names. They just
are not better ones.

### 2.6 Bindings, caveats, coverage debts

- **Frozen replay, pinned at 2026-07-31.** Re-running against a later snapshot is a
  different measurement and needs its own pin (the CN #4522 precedent).
- **Synthetic eligibility, not admissions.** Cohorts are per-name PIT states — no ranking,
  no cap, no lane, no operator, and `tier_stream`'s T1 is the raw-3D-cross fallback, a
  superset of the production §7 master. §2.4 measures how far that is from S-B's frame.
- **THE IRREDUCIBLE DEBT.** Whether the gradient survives *inside the ranked subset* cannot
  be answered from any frozen frame, because the board has never admitted a ticks-3/4 name
  — the gate excluded them. A rank×age interaction is exactly what a forward shadow would
  resolve, and it is the one live reason to keep this rung open rather than close it.
- **Survivorship is the cohort, not a bug.** A ticks-3 state is a cross that survived three
  ticks un-topped; the conditioning is observable on the firing evening, so no lookahead is
  involved. §2.3 separates it from the timing question anyway.
- **Era.** The panel spans the pre- and post-cascade-gate eras; S-B's frame is the pre-gate
  month only. §2.4 is era-matched; the rest is not.
- **T3/T4 excluded** from the tick comparison (their `ticks` is 0 by construction — a
  projection has no cross to age); counted separately, never pooled into the tick-0 cell.

---

## §3 This knob has been measured before — and agreed

`scripts/validate_provisional_replay.py` swept exactly this grid on 2026-07-02, registered
in the Trial Ledger (`data/trial_ledger.jsonl`, family `provisional_fresh_ticks_us`,
declared budget 4, `info_cutoff` 2026-07-01), on a different frame (117 held-out names) with
different outcomes (stop-out / expectancy / win rate on the walk-forward harness):

| FRESH_TICKS | OOS stop-out | OOS win rate | OOS expectancy |
|---|---|---|---|
| 1 | 61.468% | 32.289% | 4.404 |
| **2 (incumbent)** | 61.619% | 32.164% | 4.346 |
| 3 | 61.725% | 32.104% | 4.324 |
| 4 | 61.785% | 32.024% | 4.308 |

Verdict on file: `ship: false`, "no-improvement-found", margin 0.151pp — and monotone in the
direction of *wider is worse* on all three measures.

Two independent constructions, different frames, different outcome definitions, same answer.
Related standing kill for context (not this construction): DNR "FRESH BUY as a buy edge on
the Act-Now board — REFUTED, worst state on the board" (#1513).

**Multiple-testing discipline.** This packet is the **third** look at this knob. Any further
look needs its own Trial Ledger registration and should carry a stricter bar than the first,
not a looser one. The bars in §5 are written with that in mind.

---

## §4 What saying yes would actually cost (the change is not one constant)

`FRESH_TICKS` has consumers that would *not* move with it, and one that would move in a way
its own prereg forbids:

| site | what it does | effect of 2 → 4 |
|---|---|---|
| `engine/confluence_tiers.py:44` | the constant | the intended change |
| `engine/us_board_rank.py:84` `FEATURED_MAX_TICKS = 2` | featured freshness window, a **mirrored copy**, not an import | silently forks — featured stays at 2 while admission widens |
| `scripts/check_board_contradictions.py:49` `FRESH_TICKS = 2` | **hardcoded literal** in the CI contradiction guard | guard keeps enforcing the old boundary; every new ticks-3/4 FRESH-BUY row reads as a contradiction |
| `scripts/build_stock_library.py:4513` | stale-cross arbiter at `ticks > FRESH_TICKS + 1` | boundary drags 3 → 5; a second, undebated behaviour change |
| `engine/prophet_doors.py:94` `REARM_TICKS_MIN = 3` | **Door R fires on ticks ∈ [3,15] with a `not eligible` leg** | the door's whole premise collapses — its cohort becomes board-eligible. Door constants are **prereg-frozen**: "changing any of these changes the door, which is a prereg amendment, not a refactor" |

So the honest cost of "yes" is: one constant, two forked copies to reconcile, one arbiter
boundary to re-adjudicate, and a Door R prereg amendment. That is a W5-class change with a
real blast radius, which is the correct frame for the bars below.

---

## §5 PROPOSED decision bars — **PROPOSED, the commissioner adjudicates**

Every number below is a proposal for review, not a ratified bar.

**Primary read.** Demeaned median excess **and** loser rate of a ticks-3/4 **shadow** cohort
versus the ticks-0/2 **admitted** cohort, both taken from inside the ranked pipeline (not the
raw state population — §2.4 is the reason this qualifier is load-bearing).

**Horizons.** H=21 primary (the doors' horizon, and the horizon the operator's own swing
window matches); H=10 supporting (the record/S-B basis). Both printed always.

**Minimum evidence before any read is taken:**

| gate | proposed floor | why |
|---|---|---|
| matured shadow entries | **n ≥ 120** | the retro effect ceiling is ±0.25pp demeaned; below ~120 the forward read cannot see anything smaller than the retro noise band |
| distinct fire-dates | **≥ 40** | one board night is one bet; §2.2's interval is date-blocked and the forward read must be too |
| distinct names | ≥ 60 | keeps one repeat ticker from carrying the cohort |
| calendar | ≥ 2 quarters spanned | a one-regime read is not a read (one-window symmetry) |

**Promotion bar (all must hold, on the date-blocked interval, not the pooled one):**

1. Demeaned median excess of ticks-3/4 ≥ ticks-0/2, with the **date-blocked 95% CI on the
   delta excluding zero on the favourable side**. A straddle is a null, not a pass.
2. Loser rate of ticks-3/4 **not worse by more than 2pp**, with its own CI.
3. The delta holds the same sign on **both calendar halves** (the retro half-split flipped;
   a forward read that also flips is noise).
4. The paired within-cross delta (§2.3) is **not negative** on forward data — i.e. the
   forward evidence must contradict the retro mechanism finding, explicitly, rather than
   being silent about it.
5. Bars 1–4 are met at H=21 **and** not contradicted at H=10.

**Anything short of all five = the rung closes as measured-null** and the roadmap queue
re-ranks. A partial pass is a null with extra steps.

**Displaced-definition tripwire** (the theme_timing precedent's shape — W0 stratifies
nightly, a rolling comparison, alarm + revert proposal, never a silent drift):

> W0's nightly artifact (`data/prophet_miss_audit/`) stratifies matured shadow entries by
> tick bucket. If the ticks-3/4 stratum's rolling loser rate exceeds the ticks-0/2 stratum's
> **by ≥ 5pp over ≥ 60 matured entries**, the tripwire alarms and files a revert proposal.
> If the change ever ships live, the displaced FRESH_TICKS=2 definition keeps grading nightly
> as a labelled shadow so the race runs in both directions.

Tripwire subject, from §2.5: the leg that carries the exclusion is the leg that carries the
risk. Watch the **stoch_ob share** of the shadow cohort — a widening window admits mostly
overbought-adjacent names, and an extended-entry drawdown problem will show up there first.

**Pre-registered null disclosure.** If the bars fail, the result is printed — the roadmap
gets a measured-null row and the queue re-ranks. Nulls are printed, not hidden.

---

## §6 Implementation sketch for the shadow — NOT built in this PR

**Recommendation: do not build a new shadow. Read Door R.**

`engine/prophet_doors.py` Door R already fires on exactly this cohort — `ticks ∈ [3, 15]`,
explicitly commented "the master cross is STALE (past the FRESH_TICKS=2 window)" — with a
`not eligible` leg, `above200`, `weekly_bull`, and a re-arm confluence leg. It emits nightly
to `data/prophet_doors/flags.jsonl` (`scripts/emit_prophet_doors.py`, zero authority, writes
only to `data/prophet_doors/`) and is graded by `scripts/grade_prophet_doors.py`. It has been
accruing since the doors merged.

| option | what it costs | what it answers |
|---|---|---|
| **A — Door R stratification (recommended)** | one **recorded feature** (tick-age bucket) on the existing flag payload + a stratification in the grader. **No fire-condition change** — Door R's definitions stay frozen per `PROPHET_DOORS_PREREG.md` §7; a recorded-features addendum is the same lawful move §4.1 used for Door T. | the ticks-3/4 stratum of an already-accruing, already-graded, already-ranked prospective ledger |
| B — cascade shadow column | a new store, a new nightly writer, a new grader, a new synapse registration, and a fresh maturity clock starting at zero | the same question, later |

Option A's honest limitation, stated so the operator is not surprised: Door R's extra legs
(`above200`, `weekly_bull`, re-arm confluence) make its cohort a **subset** of the replay's
ticks-3/4 population. It answers a *narrower and better-conditioned* question — "do aged
crosses that re-arm inside an intact trend pay?" — not "should the window simply widen".
That is arguably the better question, and it is the one a bounded-authority rung would want
anyway; but the substitution must be named at ratification, not discovered later.

If the operator wants the unconditioned question instead, Option B is the honest route and
its cost is the one listed.

---

## §7 Two ship paths — laid out, neither advocated

The choice is the operator's. Both are presented with what they cost and what they risk.

### Path 1 — DEFAULT: wait for G0.2, shadow first

Ratify nothing now. Land the Door R stratification (recorded feature, zero authority), let
the shadow accrue, read it against §5's bars after G0.2's five green W0 nightlies.

- **Costs:** time. The bars in §5 need n ≥ 120 matured over ≥ 40 fire-dates; at Door R's
  observed flag cadence that is a multi-month clock, and the rung sits in the queue meanwhile.
- **Risks:** none to the live board. The pure cost is opportunity — if a rank×age interaction
  does exist (§2.6's irreducible debt), it stays unexploited for that period.

### Path 2 — the CN G0.8 pattern: ratify and flip live, graded

The CN desk's shipping pattern (`CN_TO_US_PROPHET_HANDOFF_2026-08-04.md` §4): measured
inversion + coherent mechanism ⇒ operator ratification ⇒ ship the flip live with (a) the
displaced rule still grading nightly as a labelled shadow, (b) a named tripwire (their shape:
≥5pp win-rate trail over 60 matured → alarm + revert proposal), (c) a single-commit revert
path. Implementation template: `engine/cn_v3_tripwires.py` + the shadow-append idiom in
`build_china_library.py`.

- **Costs:** the §4 blast radius, up front — two forked constants reconciled, the
  `build_stock_library` arbiter boundary re-adjudicated, and a Door R prereg amendment
  (widening the gate to 4 collapses Door R's `not eligible` leg, so the door must be
  re-scoped in the same change or it silently stops firing).
- **Risks:** a +16.5% wider board (§2.5) whose added names measure flat-to-marginally-worse,
  entered a median 0.4–0.5pp later on the same cross (§2.3).
- **The precondition, stated as fact not as advice:** G0.8's trigger is *measured inversion*.
  Here the measurement is a tight null in the retro and monotone-adverse in the prior
  registered sweep (§3). Path 2 would therefore be shipping **ahead of** the evidence rather
  than on it. That is a legitimate operator call — the operator may weigh the §2.6 rank×age
  debt, or a prior about the tape, above two retro constructions — but it is not the same
  epistemic move the CN flip was, and the memo should not let the two be conflated.

---

## §8 In plain words, for the operator

**What we asked.** Our board drops a name once its buy signal is more than two "ticks" old.
S-B suggested older signals were doing *better*, right up to that cutoff — so we asked
whether we are throwing away the best ones.

**What we found.** No. Rebuilding the comparison over every name in the universe — extending
only the staleness clock and leaving every other safety check exactly as it is — the
three-and-four-tick names come out **the same** as what we already buy: better by 0.04pp,
with a confidence range of −0.18 to +0.24pp. Practically zero, and measured precisely enough
that we can say zero rather than "unclear". Following the *same* signal, entering three ticks
later is about half a point worse. And a separate study run a month ago, on a different set of
names with different measures, found the same thing in the same direction.

**Why S-B looked different.** S-B could only see names the board had already picked. Once you
strip out the picking, the pattern disappears — the improvement was our selection working,
not the signal ageing well. That is genuinely good news about the board, just not about this
knob.

**Expected effect if we changed it anyway.** About 17 more names per night on the board
(+16.5%), performing the same as today's names or a touch worse. Not free: five other places
in the code assume the current two-tick boundary, two of them by copied literal, and one of
our prospective ledgers (Door R) exists specifically to watch aged crosses and would stop
working as designed.

**What we watch.** If a shadow does get built, the alarm is: aged names losing more often than
fresh ones by 5 points over 60 matured picks → alarm and propose reverting. The specific thing
to watch is the *overbought* share, because that is what actually kills aged crosses today —
not the signal breaking down.

**How it rolls back.** Nothing has changed, so nothing needs rolling back. If a future
version does ship, it is one constant plus the five reconciliations in §4, revertible in a
single commit, with the old rule still being graded alongside so the comparison keeps running.

---

## §9 What would change this verdict

1. **A rank×age interaction in the forward shadow.** The one thing no frozen frame can see
   (§2.6). This is the live reason to keep the rung open.
2. **A regime split.** The panel is one long US trend regime. A dispersion- or
   correlation-conditioned re-read is a different question and would need its own prereg.
3. **A narrower, better-conditioned cohort** — Door R's re-arm construction (§6 option A) is
   exactly that, and its stratum could separate where the raw window does not.

None of these is a reason to widen the window today. All three are reasons not to close the
file.

*Related: `PROPHET_US_SUPERINTELLIGENCE_ROADMAP_BY_FABLE.md` §3/§5 (parent),
`PROPHET_DOORS_PREREG.md` (§6 option A would amend its recorded-features list, not its fire
conditions), `CN_TO_US_PROPHET_HANDOFF_2026-08-04.md` §2/§4 (method + shipping pattern),
`superintelligence_standins.py` (S-B), `US_BOARD_MEASUREMENT` (measurement canon).*
