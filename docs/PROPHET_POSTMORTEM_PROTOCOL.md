# Prophet postmortem protocol

Status: STANDING · Program: `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` (gate G6)
· Engine: `engine/postmortem.py` · CLI: `scripts/prophet_postmortem.py`

The board loses money on some picks. This document is how those losses become knowledge
instead of anecdotes — who runs what, on what cadence, what they are allowed to conclude,
and where the conclusion is written down.

The one-line version: **the artifact classifies, a session adjudicates, and nothing
changes a live weight without its own pre-registration.**

---

## 1. When it runs

| Trigger | Cadence | Who |
|---|---|---|
| Routine review | Weekly, after the week's last nightly render | a Fable session |
| Loser cluster | Within 24h of any board night producing **≥ 3 episodes at ≤ −8%** | a Fable session |
| Operator request | On demand | whoever is asked |
| Definition change | Immediately after any board-definition change ships | the shipping session |

Re-running is free and idempotent: identical inputs produce an identical artifact
(everything iterated is sorted; the bootstrap is seeded upstream in
`engine/track_scoring.py`). Run it as often as you like — the discipline is in the
adjudication, not in the frequency.

```bash
python -m scripts.prophet_postmortem              # writes both artifacts
python -m scripts.prophet_postmortem --dry-run    # headline only, writes nothing
```

---

## 2. What the artifact gives you

| Path | What it is |
|---|---|
| `data/prophet_postmortem/summary.json` | machine-readable: aggregations + every episode row with its trigger values |
| `reports/prophet_postmortem_<as_of>.md` | the same content rendered for a reader — start here |

Inside, in the order you should read them:

1. **Coverage** — how many episodes, how many matured, how many had no price path, how
   many revisions of the theme artifact were reconstructable. Read this first: every
   number below is conditioned on it.
2. **Failure taxonomy, both tails** — seven labels, each a deterministic
   feature-threshold rule (no LLM anywhere), each carrying the values that fired it.
   Shares are over the episodes where the label could be **decided**, never over the
   whole sample.
3. **What a veto would have cost — both sides** — for every TRIGGER the loop could be
   built on: losses avoided **and winners forfeited**, with the net. This table is the
   reason the loop exists. A rule that removes six losers and eight winners is a losing
   rule, and this is where that shows up before anything ships.

   A row is a trigger, not a label, and each carries an `evidence` column with one of two
   values. **`buildable`** means the trigger was readable on the night of the pick.
   **`hindsight upper bound`** means it needs a number that did not exist yet, so the row
   is a CEILING on what the pattern could be worth if a buildable trigger is ever found —
   never the value of a rule, and never a candidate for pre-registration as written.

   `re_admission` is the worked example, and the reason the column exists. It is costed
   on two lines. The **+79.08pp** on the 2026-07-31 artifact is the **hindsight upper
   bound**: it sits entirely on the `prior_episode_loss` leg, which needs the earlier
   episode's RESOLVED outcome — a number that does not exist on the night the board
   re-admits the name (IPGP was +3.04% GREEN when it came back). The only buildable leg,
   `open_drawdown_at_readmit` (the earlier position already ≥ 8% under water at the
   re-admission), fires **0 times** on that window; the row is printed with its zero
   rather than dropped. So the buildable trigger has **no sample yet**: it needs its own
   accrual — enough fires to measure, both tails costed — before there is anything to
   pre-register, and the hindsight number may not stand in for that accrual. Read the
   +79.08pp as "this pattern is worth looking for a buildable trigger for", nothing more.
4. **Systemic or anomalous** — label share across distinct entry DATES, not rows.
   Episodes surfaced on the same night are one bet.
5. **Entry-state splits**, **repeat offenders**, **every loser with its triggers**,
   **in-flight rows**, **caveats**.

### The seven labels

| Label | Fires on | Visible at entry? |
|---|---|---|
| `sector_headwind` | theme / sector-basket reco in {avoid, trim}, or spotlight `out_of_play` / stage `lagging` | yes |
| `bought_extended` | overextended alignment, `Extended — wait` tier, `extended` entry status, an `ext` risk component, or a fill above the board's own chase level | yes |
| `thesis_break` | a later board night stamped `hold.state = broken`, else a close crossed the entry row's published stop | no |
| `gap_event` | a single-session close-to-close move ≤ −8% against the position | no |
| `market_beta` | benchmark-excess loss under 40% of the absolute loss | no |
| `re_admission` | same ticker re-admitted ≤ 10 sessions after a prior episode that was already ≥ 8% under water (`open_drawdown_at_readmit`) or that RESOLVED to a ≥ 8% loss (`prior_episode_loss`) | **no** — see below |
| `idiosyncratic` | nothing else fired | — |

Labels are multi-label; the shares do not sum to 100%.

**`re_admission` is not a visible-at-entry label**, and the reason is item 3 above: its
two legs have opposite epistemic status, and on today's data 100% of its fires are the
hindsight one. The individual ROW still says which leg fired it, and a row carrying the
open-drawdown leg is flagged visible-at-entry on that row — but the label as a whole
makes the weaker, safer claim, and that is the one the report, `summary.json` and the
admin panel read.

---

## 3. Reading rules (these are where postmortems usually go wrong)

**A null is not a negative.** An episode whose entry state was never recorded is not
evidence that the label did not apply. Those rows are excluded from that label's
denominator and counted in `nulls`. If a label's `n_evaluated` is small, its share is
about a small sample — say so out loud.

**A share is not a cause.** "60% of losers had a headwind at entry" means nothing until
you have read the winners' column on the same line. If the two are close, the feature
separates nothing.

**In-flight rows carry no rate.** They are marked to the latest close and classified,
because dropping them would delete the most recent evidence — but a mark is
outcome-conditioned, so they enter no win rate and no expectancy. Never quote an
in-flight number as a result.

**One night is one bet.** Before calling anything systemic, check the distinct-dates
column. Nine losses on one night is one bad night.

**`idiosyncratic` is a scoreboard, not a bucket.** A large idiosyncratic share means the
taxonomy is not yet explaining the losses. That is a finding about the taxonomy, and the
fix is a new candidate label with its own rule — not a wider threshold on an existing one.

**A hindsight number is not a rule.** Before quoting any line of the veto table, read its
`evidence` cell. A `hindsight upper bound` row measures a pattern nobody could have acted
on; quoting its net as what a veto "would have saved" silently asserts that the board
could have known something it could not. If the buildable sibling of that trigger fires
zero times, the honest sentence is "the pattern is real and we have no buildable version
of it yet" — and the next step is accrual, not a pre-registration.

**The counterfactual is arithmetic, not a backtest.** `net_pct_if_vetoed` sums equal-weight
percentage points. It ignores sizing, the overlap between episodes on one night, and the
fact that the same capital cannot take every pick. It is a first-order screen for whether
a rule is even worth pre-registering.

---

## 4. What a Fable session does with it

1. **Read the report top to bottom.** Coverage first.
2. **Adjudicate each label: systemic, recurring, anomalous, or unfired.** Use the
   distinct-dates column, not the row count.
3. **For anything that looks systemic, read the veto-cost row.** If the winners-forfeited
   column eats the loss-avoided column, the finding is *interesting* and *not actionable*.
   Say both.
4. **Write the verdict** (§5). A cycle that changes nothing still gets a verdict — "read
   this week's cluster, found nothing beyond one bad night" is a result and prevents the
   same cluster being re-litigated next week.
5. **If a candidate rule survives, pre-register it** — do not implement it. See §6.

### What a session must NOT do

- **Never hot-patch a score weight, gate, or veto from a postmortem.** One week of losers
  is the smallest, most over-fit sample in the building. Every rule born here goes through
  the promotion pipeline like any other candidate.
- **Never widen a threshold to make a label fire more.** If `market_beta` never fires,
  that is a fact about the window (the diagnostics block prints the distribution it was
  thresholded on); moving the threshold to produce a nicer table is fitting the label to
  the story.
- **Never pool eras.** A board-definition change ends a sample. Grade both sides with the
  same scorer and report them separately — the CN `prior_record` block is the worked
  example.
- **Never let an LLM originate a label, score, or escalation** (constitution A7). The
  classifier is threshold rules in `engine/postmortem.py`. A session may de-escalate and
  interpret; it may not invent.
- **Never write "validated"** anywhere this work surfaces. Descriptive verdicts only —
  "the headwind cohort lost more often, and forfeited a comparable weight of winners".

---

## 5. Where verdicts are recorded

| Outcome | Goes to |
|---|---|
| The cycle's read | a dated entry appended to the program masterplan `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` |
| A candidate rule | its own pre-registration (pick-lab book / prereg doc) with gates fixed **before** measurement |
| A killed idea | a row in `research/DO_NOT_REBUILD.md`, inside sections 1–4, with the compiled blocklists regenerated in the same PR |
| A data or coverage defect | a normal issue/PR — coverage holes are bugs, not findings |

A verdict entry states, in this order: the cycle date, what the artifact showed, what was
adjudicated systemic vs anomalous, what (if anything) is being pre-registered, and what
was explicitly NOT changed.

---

## 6. Promotion path for a candidate rule

The postmortem is measurement tier. Nothing it finds reaches a live weight without:

1. a **pre-registration** naming the rule, the exact feature and threshold, the outcome
   metric, the sample it will be tested on, and the pass/fail gates — written down before
   the test runs;
2. an **out-of-sample or date-blocked evaluation** (episodes on one board night are one
   bet — `engine.track_scoring.date_block_ci`);
3. **both sides costed** — a veto's winners-forfeited column is part of its result, not a
   caveat on it;
4. a **verdict recorded** whether it passes or fails, so the same idea is not re-proposed
   from scratch next quarter.

Until all four exist, a finding ships **display tier only**: it may be shown, described
and accrued. It may not rank, size, or gate.

---

## 7. Where to see it

- **The artifact is the product.** `reports/prophet_postmortem_<as_of>.md` is the reader
  surface; `data/prophet_postmortem/summary.json` is the machine surface.
- **Admin.** The Prophet panel (`admin/prophet.py` → `GET /api/prophet`) exposes a
  `learning_loop` block reading `summary.json`: as-of, episode/loser/winner counts, the
  label frequencies with their per-label coverage, and the veto-cost table including the
  winners-forfeited column and each row's `variant` / `visible_at_entry` — a hindsight row
  may not reach a surface without its evidence status attached. It is a read-only pointer
  at the artifact — the panel never recomputes anything.
- **CN continuity.** `site/factordata/cn_track_ledger.json` carries `prior_record`, the
  pre-2026-07-30 board graded under the same core and labelled as the previous
  definition. The current record is unchanged.

---

## 8. Related

- `research/PROPHET_LEARNING_LOOP_MASTERPLAN_BY_FABLE.md` — the program and its gates
- `engine/track_scoring.py` — the three rules that make a track record honest
- `research/US_BOARD_MEASUREMENT.md` — what the US board's numbers mean
- `docs/DESIGN_DOCTRINE.md` — what may be said on a user-facing surface
