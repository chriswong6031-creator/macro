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

**The headline is a coverage result, not a finding.** One edge of 58 cleared
the n=10 floor, and its effective evidence is two independent windows. Nothing
here supports or refutes any linkage. The deliverable is that the record now
exists and its gaps are named.

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
— the target had no graded row inside the link window. 13,074 of those belong
to one edge (`track_record → us_board`), whose src emits on 12,979 sessions back
to 1962 while its target is graded over a handful of 2026 sessions. Those fires
are **counted, not dropped**: each edge carries a summary row with the exact
tally, so coverage arithmetic is unchanged while the ledger stays readable at
273 rows instead of 13,407.

## §3 The unsigned-outcome trap (why 3 edges were refused)

`engine/neuralweb/query.py` builds the `track_record` ledger with
`row["outcome_excess"] = _safe_float(r.get(mfe_col))` — for that ledger,
`outcome_excess` **is** `fwd_mfe_H`, a max favorable excursion, which is
unsigned by construction. Measured on the store: 276,279 graded `track_record`
rows, `outcome_excess == fwd_mfe_H` for 100.0% of them, minimum 0.0000,
fraction negative 0.000. `direction` is also pinned to 1 on that ledger.

Any direction-agreement computed against it would have read ~100% agreement at
every horizon and meant nothing. Three `confirms` edges targeting
`engine:track_record` are therefore refused with
`dst_outcome_unsigned_mfe_proxy` rather than shipped as near-perfect
confirmations. The guard is fail-closed and doubled: a structural ledger list
plus an empirical probe that flags any cohort of ≥8 graded outcomes containing
no negative value, so a future ledger acquiring the same defect is caught
without an edit.

## §4 Per-edge scoreboard

**Above the MIN_N=10 floor: 1 edge.**

| Edge | n_graded | indep. blocks | agreement (H=21) | base rate | lift | Wilson CI95 | median lag |
|---|---|---|---|---|---|---|---|
| `confirms  engine:altdata → engine:radar` | 18 | **2** | 0.278 | 0.200 (n=20 sessions) | **+0.078** | [0.125, 0.509] | null |

**Read this row carefully — the naive read is wrong.** 5 agreements in 18 fires
looks like a 72% disagreement, i.e. evidence *against* the confirms edge. It is
not. Radar's **unconditional** up-rate at H=21 over the same window was 4 of 20
sessions = 0.200. Conditioning on an altdata fire gives 0.278. The edge sits
slightly *above* its own base rate; the apparent disagreement was the market
window, not the linkage. This is why the ledger carries
`dst_base_rate_matched` in the artifact rather than in a footnote — an
agreement rate shipped without its base rate is not interpretable.

Two further honesty notes on that single row, both stamped in the artifact:

- **Effective n is 2, not 18.** The 18 fires span 2026-06-19 → 2026-07-29 and
  share a 21-session forward window; `n_independent_blocks = 2`. The Wilson CI
  assumes independent trials, so `[0.125, 0.509]` is a nominal floor on width,
  not a calibrated interval. Every row carries
  `ci_basis: nominal_wilson_assumes_independent_fires` and `overlap_warning: true`.
- **The src direction is structurally constant.** `altdata` emits `direction=1`
  only, so "confirms" collapses to "did radar's median 21d excess go up".
  `src_direction_degenerate: true` is stamped on each fire.

**Accruing (below floor — count shown, rate suppressed):** 57 edges. The eight
with any graded data:

| Edge | fires | n_graded | base-rate n |
|---|---|---|---|
| `headwind  macro:rates_transmission → sector:xlb` | 24 | 7 | 12 |
| `headwind  macro:rates_transmission → sector:xlk` | 24 | 7 | 20 |
| `confirms  engine:radar → engine:us_board` | 37 | 6 | **1** |
| `confirms  engine:altdata → engine:intel_hub` | 35 | 6 | 4 |
| `confirms  engine:altdata → engine:us_board` | 35 | 4 | **1** |
| `confirms  engine:track_record → engine:us_board` | 13,074 | 4 | **1** |
| `confirms  engine:intel_hub → engine:radar` | 27 | 4 | 20 |
| `confirms  engine:policy → engine:radar` | 7 | 4 | 20 |

The bolded base-rate denominators are the second thin-denominator warning in
this table: `us_board` has exactly **one** session graded at H=21, so its base
rate of 0.000 is an artifact of that single session, not a property of the
engine. The denominator is printed next to every base rate for exactly this
reason. No rate is drawn from these rows.

## §5 Realized lag — null, and why

Every lag came back null, under two reasons: `no_horizon_crossed_1sigma` and
`no_trailing_history_before_fire`. With targets graded over weeks rather than
years, the trailing dispersion floor (MIN_N_LAG=10 observations before the
fire) is rarely met, and where it is met the move does not clear 1σ.

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

## §7 What would make the next read informative

Named plainly, in the order they bind:

1. **Time.** Eight edges sit at n_graded 4–7 against a floor of 10. They clear
   it by accruing sessions, which is what the prospective nightly ledger is for.
2. **Independent windows, not just fires.** Even the one above-floor edge has 2
   independent blocks. A rate worth reading needs ~10 non-overlapping 21-session
   windows — roughly a year of accrual at current fire density.
3. **H=21 grading breadth on the targets.** `us_board` and `intel_hub` have 1
   and 4 sessions graded at H=21. Until targets are graded at the primary
   horizon across more sessions, base rates stay uninterpretable.
4. **A signed outcome column for `track_record`**, or an explicit decision that
   the three edges targeting it stay permanently ungradeable by direction. As
   built, the guard refuses them rather than printing a fake ~100%.

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
  day one.
- Re-running is idempotent: the second retro run appended 0 rows, all 273
  skipped by content hash.

*Reproduce: `python -m scripts.build_edge_outcomes --retro --results-json research/edge_outcome_retro_results.json`*
