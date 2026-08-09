# Neural Web edge-outcome ledger — first retro

*Quant wave-2b (`research/ADVANCED_QUANT_METHODS_ADJUDICATION_BY_FABLE.md` §4-2b).
Run 2026-08-05 against the committed `data/neuralweb` store.
Module: `engine/neuralweb/edge_outcomes.py` · runner: `scripts/build_edge_outcomes.py`
· ledger: `data/neuralweb/edge_outcomes_retro.jsonl` · machine payload:
`research/edge_outcome_retro_results.json`.*

## §0 What this is, and what it is not

The Neural Web has typed edges but has never had a ledger grading **"edge fired
→ did the target actually move, which way, with what lag"**. The spine grades
signal-fires; nothing graded edges. This is that ledger: deterministic,
display-tier, zero fitted weights, AUTHORITY_BLOCK on every row.

It is **not** a new fire substrate. CHF-R14 forbids one ("New fire/outcome
ledger: FORBIDDEN (RUL-ORTH-4)"), and the module complies by construction: it
never originates a fire and never grades an outcome. Every fire is read off
`spine_index.parquet`; every outcome number is an `outcome_excess` the spine
already graded. It is a *join*, and its unit of record — the edge — is the
object CHF-R15's Phase-3 clock (2027-01-15) will be asked to judge.

**The headline is a coverage result, not a finding.** Exactly one edge of 58
clears the floor, at H=21 on its 16 settled fires, and it lands
**indistinguishable from its own base rate** (0.312 against 0.318, lift
−0.006, on 2 independent blocks). H=63 accrues everywhere. Nothing here
supports or refutes any linkage.

**This document has been corrected three times under adversarial review**, and
the headline moved each time — worth stating plainly, because every correction
ran against the result:

| | lift | what changed |
|---|---|---|
| first cut | **+0.078** | control used the wrong estimator over the wrong span |
| matched control | **−0.002** | same estimator, same window, fires' own span |
| settled H=21 (current) | **−0.006** | dropped 2 verdicts whose windows were still open |

Six structural defects were fixed across those rounds: the prospective lane
could never reach a graded row; it then froze each verdict on a partial window;
settlement was gated on the longest horizon rather than each horizon's own;
the unsigned-outcome guard covered one of four affected ledgers; the base rate
was unmatched and latched; and the prospective fire count inflated 13× by
re-counting its own summaries. Details in §3, §4 and §8.

## §1 Inventory

| Source | Edge type | Count | In scope |
|---|---|---|---|
| `confluence_graph.json` (asof 2026-08-05) | `feeds` | 1,667 | **no** — static wiring |
| | `confirms` | 15 | yes |
| | `contradicts` | 6 | yes |
| | `headwind` | 2 | yes |
| `causal_edges.jsonl` | `leads` (scout candidates) | 35 | yes |
| **Measured inventory** | | **58** | |

`feeds` is 98.6% of the graph and is skipped deliberately: it is
producer→artifact→consumer plumbing read out of `config/synapse.yml`. It
asserts that data flows along a pipe, not that a market subject moves when
another one does. Grading it would produce a number with no claim behind it.
The skip is printed as a gap on every run, never silent.

Substrate: `spine_index.parquet`, 349,299 rows, `as_of` 1962-11-29 → 2026-08-05.

## §2 Coverage — the honest headline

**11 of 58 edges (19.0%) are gradeable.** 47 are not, and each names one
reason code:

| Reason | Edges | Why |
|---|---|---|
| `chf_panel_subject_graded_elsewhere` | 35 | Both endpoints are CHF cause-feature / target-panel ids (`fed_net_liquidity → regime_worsening_5d`), not spine subjects. The causal battery grades these itself; re-grading here would duplicate an existing measurement. |
| `src_unresolved` | 7 | 4 are artifact paths (`data/regime/latest.json:regime_vector`, `site/intelligence/briefing.json`) — files, not market subjects. 3 are options *conditions* (`options.skew_rising`), which name a state inside the options engine, not the engine. Mapping a condition to its whole engine would silently grade a different object, so the resolver refuses to guess. |
| `dst_outcome_unsigned_mfe_proxy` | 3 | Target is `engine:track_record` — see §3. |
| `dst_unresolved` | 2 | `regime:Q2` is a regime quad; the spine carries quads as row *stamps*, not as subjects. |

Separately, **13,145 fires** were bounded away as `no_overlapping_outcome_window`
— the target had no graded row inside the link window. **13,042** of those
belong to one edge (`track_record → us_board`), whose src emits on 12,979
sessions back to 1962 while its target is graded over a handful of 2026
sessions; that edge fired 13,074 times in total, 32 of which did land a window.
The remaining 103 bounded-away fires (13,145 − 13,042) are spread across the
other ten gradeable edges. Those fires are **counted, not dropped**: each edge
carries a summary row with the exact tally, so coverage arithmetic is unchanged
while the ledger stays readable at 273 rows instead of 13,407.

## §3 The unsigned-outcome trap (why 3 edges were refused)

`engine/neuralweb/query.py` assigns `row["outcome_excess"] = _safe_float(r.get(mfe_col))`
at **three sites covering four ledgers** — `track_record` (line 573),
`board_hk`/`board_ca` (657), `board_cn` (742). For all of them `outcome_excess`
**is** `fwd_mfe_H`, a max favorable excursion, unsigned by construction.
Measured on the store: 288,884 graded `track_record` rows with
`outcome_excess == fwd_mfe_H` for 100.0% of them; `board_hk` 509 rows and
`board_ca` 330 rows, all three with minimum 0.0000 and **zero** negative
values. `direction` is also pinned to 1 on those ledgers.

Any direction-agreement computed against them would have read ~100% agreement
at every horizon and meant nothing. Three `confirms` edges targeting
`engine:track_record` are refused with `dst_outcome_unsigned_mfe_proxy` rather
than shipped as near-perfect confirmations; the board ledgers are refused on
the same grounds whenever an edge targets them.

**The two checks are not equals, and the earlier draft of this document
overstated them as "fail-closed and doubled".** Only the structural check —
ledger membership in `UNSIGNED_OUTCOME_LEDGERS` — is fail-closed. The empirical
probe (a cohort of ≥8 graded outcomes with no negative value) is a *backstop*
that fails **open** on a single negative: one signed row anywhere in an
otherwise-unsigned cohort and the edge grades normally at a meaningless ~100%.
Because the structural list is the real lock, it is pinned to its upstream by a
test that re-scans `query.py` and fails when a fourth assignment site appears,
naming the ledger to add. `tests/test_edge_outcomes.py::TestUnsignedLedgerPinnedToQuery`.

## §4 Per-edge scoreboard

**Above the MIN_N=10 floor at H=21: 1 edge**, on its 16 settled fires. Every
other edge accrues, and H=63 accrues everywhere.

| Edge | fires | H=21 settled | H=21 unsettled | agreement | matched base | lift | CI95 | blocks |
|---|---|---|---|---|---|---|---|---|
| `confirms  engine:altdata → engine:radar` | 35 | **16** | 2 | 0.312 (5/16) | 0.318 (22 sessions) | **−0.006** | [0.142, 0.556] | **2** |

Per-horizon for that edge — the settle clock runs separately for each:

| Horizon | settles at | verdicts | settled | rate | state |
|---|---|---|---|---|---|
| H=5 | `t + 10` | 30 | 27 | — | accruing |
| **H=21** | `t + 26` | 18 | **16** | **0.312** | **measured** |
| H=63 | `t + 68` | 0 | 0 | — | accruing |

**Only H=21 prints a rate, and the dashes are not missing data.** The matched
base rate is computed at the primary horizon alone, so a rate at H=5 or H=63
would be an *uncontrolled* one — the exact shape §4b exists to refuse. H=5 has
27 settled verdicts and no control to read them against, so the ledger reports
the counts and stamps
`rate_suppressed_reason: "no_matched_control_at_this_horizon"`. For the same
reason `n_distinct_dst_sessions` is **null** off-primary rather than 0: those
sessions are not collected there, and a 0 would read as "rests on no sessions"
when the truth is "not measured here". `n_independent_blocks` is reported at
every horizon but always strides by 21 sessions, which
`n_independent_blocks_stride_sessions` states inline.

### §4a Settlement is per-horizon

A fire at session `t` draws its outcome from dst rows in `[t, t+5]`, and each
of those rows is itself graded forward. So a horizon-`H` verdict is final only
once `t + 5 + H` sessions have elapsed — **per horizon**, because no row
arriving after `t + 26` can move an H=21 median. H=21 settles at `t + 26`,
H=63 at `t + 68`, and gating the H=21 rate on the H=63 window would have
delayed it 42 sessions for zero correctness gain.

This was not a cosmetic gap. Grading a fire the moment its first dst row
settled meant taking a median over **one** row where the settled answer takes a
median over **six**. Measured over a 90-night simulation: 69 fires graded
prospectively, and **34 of them (49%) carried the opposite verdict** from a
retro over the identical settled store — agreement 0.507 against 1.000. The
row-level ladder is `stub → partial → graded_partial → graded_settled`
(terminal rung = all horizons closed, kept monotone and simple), and
per-horizon settlement rides alongside it as fields rather than extra rungs. A
fire's H=21 answer therefore supersedes its own premature version as soon as
`t + 26` passes, without waiting on H=63.

### §4b The base rate, and the three readings it went through

The H=21 read on the settled 16: agreement **0.312** (5 of 16) against a
matched base of **0.318**, a lift of **−0.006**. The control is recomputed over
the convex hull of *those 16 fires'* evaluation points — the control follows
the settled numerator, not the full fire set.

That number moved three times under review, each time against the result:

| | agreement | base | lift | why it changed |
|---|---|---|---|---|
| first cut | 0.278 (18) | 0.200 | **+0.078** | control used the wrong estimator over the wrong span |
| matched control | 0.278 (18) | 0.280 | **−0.002** | same estimator, same window, fires' own span |
| **settled 16 at H=21** | **0.312 (16)** | **0.318** | **−0.006** | 2 verdicts dropped — their H=21 windows were still open |

Two naive readings are both wrong, in opposite directions. The first: 5
agreements in 16 fires looks like a 69% disagreement, evidence *against* the
confirms edge. It is not — radar's own rate of moving the claimed way over the
same stretch is essentially identical. The second was ours, the **+0.078** in
the first cut: a base computed as a per-session median (no link window) across
the dst's entire history (no span match), while the numerator is a pooled
median over `[t, t+5]` at fire dates. A base rate that does not match its
numerator is not a control; it is a second uncontrolled statistic.

**The corrected reading: this edge is indistinguishable from its base rate.**
Not confirmation, not refutation. And at 16 verdicts in **2 independent
blocks**, that is what the evidence can currently support.

**The control overlaps the fires by construction** — 16 of its 22 evaluation
sessions *are* fire sessions (73%). That is deliberate: a control drawn from a
different stretch of calendar would import a different market regime and stop
being a control. But it means base and numerator are not independent samples,
so the comparison measures "did these fires beat their own window", not "did
this edge beat an unrelated baseline".
`dst_base_rate_sessions_overlapping_fires` carries the intersection.

Three further honesty notes, all stamped in the artifact:

- **Effective n is 2, not 18.** The 18 H=21-graded fires span 2026-06-19 →
  2026-07-13 (2026-07-29 is the last fire overall, but it carries no H=21
  verdict) and share a 21-session forward window; `n_independent_blocks = 2`.
  The Wilson CI assumes independent trials, so any interval printed here would
  be a nominal floor on width, not a calibrated one. Every row carries
  `ci_basis: nominal_wilson_assumes_independent_fires`, and `overlap_warning`
  is set whenever a rate does clear the floor on fewer blocks than the floor.
- **The src direction is structurally constant.** `altdata` emits `direction=1`
  only (18 up-claims, 0 down-claims), so "confirms" collapses to "did radar's
  median 21d excess go up". `src_direction_degenerate: true` is stamped on each
  fire. Where an edge's fires *do* carry mixed signs, the base is the
  fire-weighted null `(n₊·up + n₋·(1−up))/n`, not the majority sign — three
  live edges already have mixed signs and will clear the floor by accrual.
- **The numerator rests on 20 distinct dst sessions**, which is the one thin-ness
  check this edge passes. Others do not — see below.

**The other 57 edges accrue.** The eight below the floor with any H=21 verdict:

| Edge | fires | H=21 settled | H=21 open | distinct dst sessions |
|---|---|---|---|---|
| `confirms  engine:radar → engine:us_board` | 37 | 6 | 0 | **1** |
| `headwind  macro:rates_transmission → sector:xlb` | 24 | 4 | 3 | 6 |
| `headwind  macro:rates_transmission → sector:xlk` | 24 | 4 | 3 | 6 |
| `confirms  engine:altdata → engine:intel_hub` | 35 | 4 | 2 | 4 |
| `confirms  engine:altdata → engine:us_board` | 35 | 4 | 0 | **1** |
| `confirms  engine:track_record → engine:us_board` | 13,074 | 4 | 0 | **1** |
| `confirms  engine:policy → engine:radar` | 7 | 4 | 0 | 19 |
| `confirms  engine:intel_hub → engine:radar` | 27 | 1 | 3 | 3 |

**The bolded rows are thinner than their `n_graded` suggests.** `us_board` has
exactly **one** session graded at H=21, so all six of `radar → us_board`'s
"graded fires" read that same single dst session through overlapping link
windows. `n_graded = 6` there is really n = 1. That is a different failure from
the block-overlap one above — overlapping *fires* versus a single *observation*
read repeatedly — so the scoreboard carries both counters:
`n_independent_blocks` and `n_distinct_dst_sessions`, with
`thin_numerator_warning` set when the latter is ≤ 2. No rate is drawn from any
of these rows regardless; the floor already suppresses them.

## §5 Realized lag — null, and why

Every lag came back null, under two reasons: `no_horizon_crossed_1sigma` and
`no_trailing_history_before_fire`. With targets graded over weeks rather than
years, the trailing dispersion floor (MIN_N_LAG=10 observations before the
fire) is rarely met, and where it is met the move does not clear 1σ.

**The trailing window is not strictly point-in-time, and the code no longer
claims it is.** σ_H is built from dst rows whose `as_of` precedes the fire, but
each of those rows carries a *forward* outcome that resolves after its own
as_of — so for rows dated a few sessions before the fire, the outcome window
overlaps the fire itself. That is trailing-by-selection, not a clean "no
peeking" guarantee. It is tolerable only because the lag is report-only: it
feeds no rate, no rank, and no gate. A promotion-tier use would need a
`graded_at`-based cutoff instead, and this paragraph is the reason that would
not be a small change.

**Disclosed deviation from the charter phrasing.** The charter asks for "first
*session* in (t, t+21] where |dst cumulative excess| crosses 1σ". A
session-resolution cumulative-excess path per subject is not derivable from the
graded artifacts — the spine stores forward outcomes per signal row, not a daily
path per subject — and building one would mean opening a new price pipeline,
which RUL-ORTH-4 forbids this module from doing. The lag is therefore reported
on the horizon grid {5, 21, 63}, and every row carries
`lag_basis: "horizon_grid"` so the coarser resolution is never mistaken for
session resolution.

## §6 Fire-definition variant

The pre-registered primary definition is `spine_asof` (src has ≥1 spine row at
`t`). The disclosed variant `tape_transition` (tape state `new`/`strengthening`)
is implemented and selectable, and grades **zero** fires against today's
inventory for a structural reason: the confluence tape is keyed by **ticker**
(170 distinct symbols over 544 rows), while every measured edge is keyed by
`engine:`/`sector:`/`macro:`. The two subject spaces are disjoint. That is a
coverage fact, not a defect — the variant becomes live when ticker-level edges
enter the inventory. Bridging tape subjects to engine ids would be an amendment
to the pre-registration, not a refactor.

**The variant is `--retro` only.** The RUL-ORTH-4 compliance argument in §0 is
that this ledger is a spine-*derived* join. A nightly path deciding what fired
from the confluence tape would be reading a second substrate, which that
argument does not cover, so `--nightly --fire-def tape_transition` is refused
outright rather than left available.

## §7 What would make the next read informative

Named plainly, in the order they bind:

1. **Independent windows, not just fires.** The one measured read rests on 16
   verdicts sitting in **2 independent blocks** — that is the binding
   constraint, not the raw count. A rate worth trusting needs ~10
   non-overlapping 21-session windows, roughly a year of accrual at current
   fire density.
2. **H=63 has nothing at all yet**, and will not until `t + 68` passes on fires
   that have not happened. The long horizon is the one most likely to carry a
   propagation lag, so it is the one worth waiting for.
3. **H=21 grading breadth on the targets.** `us_board` and `intel_hub` have 1
   and 4 sessions graded at H=21. Until targets are graded at the primary
   horizon across more sessions, both the numerators and the base rates rest on
   a handful of observations read repeatedly.
4. **A signed outcome column for the four MFE ledgers** (`track_record`,
   `board_hk`, `board_ca`, `board_cn`), or an explicit decision that edges
   targeting them stay permanently ungradeable by direction. As built, the
   guard refuses them rather than printing a fake ~100%.
5. **Nightly accrual actually running.** The prospective lane is what turns
   every item above from a limitation into a countdown, and it is not yet wired
   (see §8). Until the follow-up PR lands the dag node, nothing accrues.

## §8 Status and constraints

- Display-tier, `not_a_signal`, `may_rank/gate/size/escalate` all false, on
  every row and on the scoreboard payload. This ledger evidences; it never
  scores.
- Deterministic. No LLM, no fitted weights, no learned structure (A7 /
  Article 1; CHF-R14's full-graph-learner kill is untouched by this PR).
- No promotion-tier claim language is used anywhere in these artifacts, and no
  rate is printed below the n=10 floor.
- **Not wired.** This PR adds no `config/dag.yml` node, no
  `.github/workflows` step, and no `config/synapse.yml` entry — four open lanes
  collide on those files. The wiring rides a follow-up PR; until then the runner
  is invoked by hand and `--nightly` is inert outside the nightly lane.
- Retro and prospective ledgers never mix: `--retro` writes only
  `edge_outcomes_retro.jsonl`, `--nightly` writes only `edge_outcomes.jsonl` and
  refuses unless `COLLECT_LANE=nightly`. The forward ledger is nightly-only from
  day one, and `--fire-def tape_transition` is refused on that lane (§6).
- **The two lanes have different write semantics, deliberately.** `--retro`
  rewrites its file whole and atomically — it is a replay artifact, so this
  run's output *is* the file. Appending instead double-counted: summary rows
  are keyed by the fire span they cover, so an advanced store minted a second
  summary for the same edge and both were counted. `--nightly` appends, with
  monotonic supersede: a settled grading replaces the stub written for the same
  `(edge_id, fire_date)` before its outcomes existed, and a stub can never
  replace a grading, so a degraded night cannot un-grade history. Readers go
  through `resolve_ledger`, which collapses each key to its settled row.
- **The nightly lane sweeps a 68-session lookback, not just the newest
  session.** A fire cannot be graded on the day it fires — its outcomes live in
  `[t, t+5]` and its longest horizon settles 63 sessions later. A latest-only
  lane wrote an ungraded stub every night and keep-first dedup then blocked the
  only run that could ever grade it: 0 graded rows over a 60-night simulation,
  against 39 for a retro over the same store.
- **A verdict is only final once its own horizon's window closes** — `t + 5 + H`,
  per horizon. The row ladder (`stub → partial → graded_partial →
  graded_settled`, upward only) records the all-horizon terminal state, and
  per-horizon settlement rides alongside as fields, so each horizon's rate
  admits only fires settled at that horizon. Supersede compares
  `(ladder rung, horizons settled)`, both monotone: without the second
  component an H=21 upgrade sits at the same rung as the premature row it
  should replace and gets skipped — the freeze re-appearing one level down.
  Pinned by `TestNightlyAccrual`, whose equality test compares the nightly
  ledger to the retro fire-for-fire on a fixture where partial and full windows
  give *opposite* verdicts (red on the old two-rung shape, 3/3 fires
  disagreeing), plus a per-horizon test asserting H=21 prints while H=63 is
  still open.
- **Summary rows carry a stable per-edge key.** Span-keying them let the
  nightly lookback re-mint one every night, and the aggregator summed them all:
  the prospective fire count read 351 against a truth of 27 in simulation. One
  summary per edge now survives resolution, latest wins.
- Re-running is idempotent in both lanes: a repeated retro produces a
  byte-equivalent replay, and a repeated nightly appends nothing new.

*Reproduce: `python -m scripts.build_edge_outcomes --retro --results-json research/edge_outcome_retro_results.json`*
