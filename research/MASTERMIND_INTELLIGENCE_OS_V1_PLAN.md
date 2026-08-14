# Mastermind Intelligence OS — V1 Implementation Plan

**Authored** 2026-08-12 · **Companions** `MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md`,
`MASTERMIND_INTELLIGENCE_CATALOG.md`, `MASTERMIND_EVALUATION_STANDARDS.md`,
`MASTERMIND_PROPHET_EVAL_SPEC.md`

---

## §0 Acceptance gates — the whole program

A task is **not done** unless all of these hold. They are stated first, inline, because a
criterion living in a document a spawned session was not handed arrives as nothing
(CLAUDE.md §Spawn-handoff law).

1. **Nothing in §1.1 of the architecture is rebuilt.** Every task extends a named existing
   component or explains in its PR body why extension was impossible.
2. **No new hand-maintained registry.** Derived and rebuildable, or it violates
   `DNR:KILL-PARALLEL-KNOWLEDGE-BASE`.
3. **No new gate reds the fleet on first wiring.** New gates ship WARN-tier with a dated
   promotion plan (standards §8.2).
4. **No engine retuning rides along with an evaluation change.** Evaluation PRs change how we
   measure, never what we predict. A tuning change is a separate PR with its own prereg.
5. **Every published number obeys the metric contracts** (standards §4). `--strict` on the
   metric-validity gate must pass for any number the task causes to be published.
6. **Nulls printed.** Any task producing a surface renders what it cannot claim as prominently
   as what it can.
7. **Live-verified**, not merely merged: the artifact exists and is non-empty after one real
   nightly run.

---

## §1 Sequencing

```
T0 metric-validity gate ── SHIPPED (this PR)
     │
     ├──► T1 engine registry ──┬──► T7 per-engine scorecard ──► T8 CEO view
     │      (keystone)         └──► T12 Agent OS tier interface
     │
     ├──► T2 Prophet plan benchmark  ──► T5 failure taxonomy ──► T5b clustering
     ├──► T3 fix invalid emitters
     ├──► T4 output health contract
     ├──► T6 golden case library
     ├──► T9 qledger adoption wave
     ├──► T10 contradiction classification
     └──► T11 deterministic numeric verification
```

**Critical path is T1 → T7 → T8.** Everything else parallelises. T2, T3, T6 and T9 should start
immediately and concurrently: T9 in particular is **calendar-bound** — the accrual clock starts
when registration does, and no later effort recovers a day not recorded.

---

## §2 Tasks

### T0 — Metric-validity gate · **SHIPPED**

| | |
|---|---|
| **Objective** | Make the three self-deception readings machine-detectable |
| **Dependencies** | none |
| **Files** | `engine/qledger_validity.py`, `scripts/check_qledger_metric_validity.py`, `tests/test_qledger_validity.py` |
| **Output** | 18 findings across 11 families on the live corpus |
| **Validation** | `--selftest` 7/7 with negative controls; `pytest` 14/14 |
| **Status** | done, WARN-tier by design (promotion gated on T3) |

---

### T1 — Engine registry (the keystone)

| | |
|---|---|
| **Objective** | One derived row per intelligence engine: output class, authority, ledger, declared horizon, validation state, evidence, and `graded_by_design` |
| **Dependencies** | none |
| **Files** | new `engine/intelligence_registry.py` (pure derivation), `scripts/build_intelligence_registry.py`, `scripts/check_intelligence_registry.py` (gate), `config/intelligence_registry_overlay.yml` (curated fields only), generated `docs/MASTERMIND_INTELLIGENCE_REGISTRY.md` + `data/intelligence_registry.json`; reads `config/synapse.yml`, `data/species/registry.json`, `data/qledger/claims.jsonl`, `research/DO_NOT_REBUILD.md` |
| **Output** | Registry regenerated ON THE PR THAT CHANGES ITS INPUTS — **not nightly**; drift gate like `check_blocklist_drift.py` |
| **Agent** | `builder` (opus) — build; `Explore` (**sonnet**) for the output-class census sweep |
| **Validation** | Regeneration is idempotent; **every `synapse` ARTIFACT maps to exactly one engine** (total, disjoint partition of all 642), and every producer maps to **one or more** engines or carries an explicit `not_an_engine` exclusion with a reason |
| **Acceptance** | Not done unless: spine is **derived** (overlay holds only fields absent from canonical sources); every engine above `display` authority has a non-null `evidence_ref` **or appears in the generator's machine-readable missing-evidence report**; `graded_by_design` is set for 100% of rows so "ungraded by design" is distinguishable from "ungraded by neglect"; `authority` distinguishes `user_ranking` from `engine_input` (catalog Finding C-2) |

**Why this is the keystone.** Without a unit of account there is no scorecard (T7), no CEO view
(T8) and no tier routing (T12). It is also the fix for Finding C-1: four of the five
authority-tier artifacts carry no pointer to the prereg that earned them authority.

#### T1 as shipped (2026-08-12) — two amendments to the criteria above

**The producer-level validation criterion was wrong and is corrected above.** The unit of
account is the **`(producer, owner_program)` pair** — 642 artifacts partition into **385
cells (378 engines + 7 excluded)**. 15 producers span more than one `owner_program`, so
"every producer maps to exactly one engine" is provably false under the shipped code. The
correct and stronger invariant is *artifact*-level: the partition is total and disjoint
over all 642, which is what `scripts/check_intelligence_registry.py` enforces. Leaving the
old wording would have handed a future reviewer a criterion the code cannot satisfy.

**`evidence_ref` is reported, not backfilled.** The C-1 backlog (21 engines above `display`
authority with a null `evidence_ref` on the 2026-08-12 corpus) is surfaced by the
generator's missing-evidence report and by the warn-tier law
`epistemics.engine_authority_evidence`, each naming its concrete heal: add
`qual_ladder_ref` to `config/synapse.yml`. T1 deliberately did **not** invent those
citations — a prereg pointer that does not exist is worse than a null one. Draining the
backlog and promoting that law to `hard --strict` is **T7's** work.

Two further properties worth carrying forward: `authority` and `evidence_ref` are
**derived, not curated** (a hand-typed `authority:` key in `synapse.yml` would be
unenforced free text, since `_REQUIRED_ARTIFACT_KEYS` is a required-key set, not an
exact-key set — reproducing the C-1/C-2 defect class one field later); and **there is no
drift law at all** — the registry is a derived on-demand view, nothing generated is
committed, and there is no `--check` equality mode, because `data/qledger/claims.jsonl` is
append-only and `config/synapse.yml` took **69 commits in the 14 days to 2026-08-14**
(measured on full history after the clone was unshallowed; the 26 cited earlier was a
shallow-clone artifact), so every candidate pin was a scheduled fleet-wide red.

#### T1a / T1b / T1c — the 2026-08-14 fix wave

**T1a — the ledger waterfall now earns what it publishes.** Rule 4 adopted any
grader-shaped consumer's ledger, "even cross-program". Measured 2026-08-14: 7 engines
resolved by rule 4 and **6 of the 7 hops crossed a program boundary and were wrong or
unearned** — `engine/run.py::engine-fix`, the nightly orchestrator, was "graded by"
hk-canada's `data/board_ledger/ca_board.parquet`, and
`scripts/build_stock_library.py::us-stocks-prebreakout` resolved through
`scripts/grade_us_board.py`, a producer owning two cells with different ledgers, so the
hop index made an arbitrary pick. Rule 4 is now same-program only, keyed by
`(producer, owner_program)`: rule-4 count 7 → 1, `graded_by_design: yes` 106 → 100, content
findings 222 → 212, **engine count unchanged at 378** — this deletes unearned semantics,
never a row. Separately, the `weak_filename_heuristic` label was measurably wrong: 5 of the
35 rule-1 matches carry `ledger` only in a **directory** component and all five are real
grading stores, so basename-tightening was measured and **rejected** and the value is now
`weak_path_heuristic`.

**T1b — fail-closed, keyed on the plane that went blind (M4 ruling 2026-08-14, amended the
same day).** An incomplete read of **PR-plane** input — `synapse.yml`, the overlay,
`qual_ladder.yml`, `species/registry.json`, the Article-2 table, producer source, all
config and code moved only by a pull request — is a RUN-level defect the guard failed at,
so it exits non-zero on **every** run in both plain and `--json` mode. The first form of
the ruling gated on *any* incomplete read, which handed the nightly the power to red every
PR in flight: one truncated line of 46,696 in `data/qledger/claims.jsonl` — the **one**
input an automated lane advances — reddened the whole job. Data-plane blindness is now
REPRESENTED in full (summary names the plane and the count, `COULD NOT LOOK` annotation,
`--json unreadable_by_plane`) and gated only under `--strict`. **Deferred, with an owner:**
no lane passes `--strict` yet, so claim-store corruption alerts everywhere and gates
nowhere until T7 wires the nightly-side strict run in the wave that drains C-1.
"Incomplete" includes **partial**: a store that opens but whose lines do not all parse is
named with its count while the rows that did parse stay in the view. Every live-corpus and
live-non-emptiness assertion moved onto fixture roots — asserting the C-1 backlog is
non-empty would have reddened this lane the day T7 drained it, and asserting the live claim
store parses would have reddened it the night the nightly truncated a line.

**T1c — the guard runs in its OWN legacy job, `intelligence-registry` (CEO ruling
2026-08-14).** This supersedes the earlier front-of-`neural-web` placement. `run_ci_pack.py`
returns on the first non-zero step, so inside a shared job there is no safe position: first
masks the nine sibling suites behind it, last goes dark behind any of them (#4779 — an
absence of red is not a pass), and a step-level `if: always()` is unavailable because
`ALLOWED_STEP_KEYS` is `{name, run, uses, with}`. 188 jobs were measured for consolidation
first; zero exact-duplicate signatures and no safe merge existed, so the one-off pack
rebalance is the cheaper cost. The job passes no `--strict`: with ~200 pre-existing content
findings that would be a scheduled red on arrival.

---

### T2 — Prophet plan-ledger benchmark, MFE/MAE

| | |
|---|---|
| **Objective** | Make Prophet's headline record express alpha, not raw return |
| **Dependencies** | none |
| **Files** | `data/prophet/ledger.jsonl` (schema + backfill), `scripts/reconcile_prophet_live.py`, `research/PROPHET_LEDGER_SCHEMA.md`; reuse the price/benchmark logic in `scripts/grade_us_board.py` |
| **Output** | `bench_ret_pct`, `sector_ret_pct`, `excess_vs_bench_pct`, `excess_vs_sector_pct`, `mfe_pct`, `mae_pct` on all 28 closed plans and every future closure |
| **Agent** | `builder` (opus) |
| **Validation** | Backfilled excess for a sampled plan reproduced by hand from the price parquet; ledger-advance receipt unchanged in row count |
| **Acceptance** | Not done unless: excess is **direction-signed at write time** (a short plan that falls beats a rising benchmark) with the convention documented in the file's `#` schema header; all 28 closed plans non-null; §2 of the Prophet spec recomputed with a CI beside the raw figure; G0.2 ledger law intact (intraday lane still writes nothing under `data/`) |

**Highest value-per-hour task in the plan.** Days of work; without it, six further months of
accrual still yield no alpha number.

---

### T3 — Retire the invalid emitters

| | |
|---|---|
| **Objective** | Stop publishing readings the metric contracts forbid, then promote T0 to `--strict` |
| **Dependencies** | T0 |
| **Files** | `scripts/grade_qledger.py` (per-family `excess_mean`), `engine/qledger_ui.py`, any scorecard consumer |
| **Output** | Mixed-direction families emit hit rate and `mean_abs_excess`, or per-direction splits; salience families emit no hit rate; off-horizon aggregates labelled `ACCRUING` |
| **Agent** | `builder` (opus); `reviewer` (opus) for the metric-semantics review |
| **Validation** | `check_qledger_metric_validity.py --strict` exits 0 |
| **Acceptance** | Not done unless: `--strict` is green **and** the CI wiring flips the gate's default to strict in the same PR, with the WARN-tier rationale removed from the module docstring |

---

### T4 — Output-level health contract

| | |
|---|---|
| **Objective** | Resolve `healthy` / `degraded` / `stale` / `unavailable` per engine **output**, not per feed |
| **Dependencies** | T1 (input sets) |
| **Files** | new `engine/output_health.py`; reads `config/synapse.yml` `freshness_sla_hours` (635/642 populated) + the consumer graph; extends `engine/provider_health.py`, `foresight_health.py`, `freshness_sentinel.py` |
| **Output** | A health state per engine output, consumed by T7 |
| **Agent** | `builder` (opus) |
| **Validation** | Synthetic stale/missing input flips the state; a healthy input set resolves `healthy` (both directions pinned) |
| **Acceptance** | Not done unless: state is computed from the **reader's** view, not the producer's (a green producer with stale consumers must not resolve `healthy`); `unavailable` is rendered as "could not look", never as a neutral reading (standards §9.2); `degraded` measurably lowers displayed confidence |

---

### T5 — Failure taxonomy · T5b — clustering

| | |
|---|---|
| **Objective** | Turn per-pick autopsies into a closed vocabulary, then into research tasks |
| **Dependencies** | T2 (MFE/MAE needed by `false_breakout`) |
| **Files** | `engine/metabolism/standout_auditor.py`, `scripts/run_prophet_pick_autopsies.py`, new taxonomy module |
| **Output** | A tag per closed plan; T5b groups tags into candidate research issues |
| **Agent** | `builder` (opus) |
| **Validation** | Tag assignment is deterministic and reproducible on the 28 closed plans |
| **Acceptance** | Not done unless: an honest `unclassified` bucket exists and is populated (forcing every loser into a category manufactures a pattern); `stale_feature` and `data_issue` are evaluated **first**, since they alone mean the model was never given a fair chance |

---

### T6 — Golden Case Library

| | |
|---|---|
| **Objective** | 20 curated historical cases: what was knowable, the PIT slice, the expected reading, the known failure modes |
| **Dependencies** | none |
| **Files** | new `data/golden_cases/<case_id>/`, extends `engine/neuralweb/eval/` (which holds exactly one benchmark case today) |
| **Output** | A regression suite any engine change can be run against |
| **Agent** | `Explore` (**sonnet**) to harvest candidate cases from the postmortem corpus; **main loop / `orchestrator`** for the expected-reading adjudication — that judgement is the deliverable and must not be delegated to a mechanical tier |
| **Validation** | Each case replays deterministically from its PIT slice |
| **Acceptance** | Not done unless: ≥15 cases seed from **already-adjudicated** material (`DO_NOT_REBUILD.md` rows, `POSTMORTEM_*`, the gold real-rate case study) so each arrives with its adjudication attached; every case states what was knowable *at the time*, with no post-hoc information |

**Cheapest high-leverage build in the program** — the firm has already done the adjudication work;
this only harvests it.

---

### T7 — Per-engine scorecard

| | |
|---|---|
| **Objective** | One page per engine, metrics selected by output class |
| **Dependencies** | T1, T4 |
| **Files** | new builder + template; extends `templates/measurement.html.j2` (the Calibration Lab) |
| **Agent** | `builder` (opus) for data; `designer` (opus) for the surface — design is judgment work and never routes to sonnet |
| **Validation** | Rendered for Prophet, sector rotation, Risk Radar, a descriptive engine, and a generative engine — five different output classes, five different metric sets |
| **Acceptance** | Not done unless: a **descriptive** engine's scorecard shows *no* forward-return metric (standards §4.3); an engine below the 50-episode floor shows accrual status only (§4.7); "what this engine cannot yet claim" renders at the same visual weight as its numbers; internal rubric scores never reach a public surface |

---

### T8 — CEO view

| | |
|---|---|
| **Objective** | One page ranked by **evidence strength**, not impressiveness |
| **Dependencies** | T7 |
| **Output** | Five lists: Validated · Accruing (with the date each becomes decidable) · Ungraded by design · Degraded · Disproven |
| **Agent** | `designer` (opus) |
| **Acceptance** | Not done unless: the **Disproven** list is rendered as an asset, sourced from `DO_NOT_REBUILD.md`; today's honest render shows a nearly empty Validated list and a full Accruing list, and ships that way rather than being padded |

---

### T9 — qledger adoption wave · **start immediately**

| | |
|---|---|
| **Objective** | Every directional engine registers claims before outcomes exist |
| **Dependencies** | none (T1 informs prioritisation but must not block it) |
| **Files** | per-engine adapters onto `engine/qledger.register()`; 26 files reference it today against 99 programs |
| **Agent** | `builder` (opus), one engine per PR |
| **Validation** | Claims appear with correct `direction`, `horizon_d`, `bench`, `control`, and `timestamp_quality` |
| **Acceptance** | Not done unless: `direction` is set correctly (`0` **only** for genuine salience claims — the salience/directional split is what makes any later hit rate legal); `horizon_d` is the horizon the engine actually claims, not a convenient short one; the engine also registers a `*_pit` twin or documents why no lookahead control is needed |

**Calendar-bound.** The ledger's value is linear in time and quadratic in adoption. Every week
of delay is a week of evidence that cannot be recovered later.

---

### T10 — Contradiction classification

| | |
|---|---|
| **Objective** | Classify detected disagreements as healthy / tension / impossible |
| **Dependencies** | T1 (`horizon_role`), T4 (staleness) |
| **Files** | `engine/neuralweb/contradictions.py` (1,142 LOC, 7 typed pairs today) |
| **Agent** | `builder` (opus) |
| **Acceptance** | Not done unless: the display-only hard law is preserved — no gate, no ranking effect, no `critical` severity (`DNR:KILL-REGIME-SCORECARD`); "impossible contradiction" routes to the **health** lane as a data-integrity incident, never to a market surface; corroboration is computed only over **input-disjoint** engines using the synapse consumer graph, since two engines sharing an input do not corroborate each other |

---

### T11 — Deterministic numeric verification for generative output

| | |
|---|---|
| **Objective** | Check every number in generated prose against its source artifact |
| **Dependencies** | none |
| **Files** | `engine/neuralweb/response_eval.py` (mechanical tier), `engine/neuralweb/market_packet.py` (aggregation-only grounding source) |
| **Agent** | `builder` (opus) |
| **Acceptance** | Not done unless: it runs in the **mechanical** tier (free, deterministic, pre-judge); a wrong figure fails regardless of how well the answer reads; scores stay internal QA telemetry and never reach `site/` |

**Catches the highest-severity generative failure — a confidently wrong number — far more
reliably than any rubric axis.**

---

### T12 — Agent OS tier interface

| | |
|---|---|
| **Objective** | Two narrow contracts between Evaluation OS and Agent OS |
| **Dependencies** | T1 |
| **Output** | (a) structured research issue emitted from a finding; (b) `required_tier(diff) -> T0..T4` derived from the registry's `authority` field |
| **Agent** | `builder` (opus) |
| **Acceptance** | Not done unless: Evaluation OS **states findings and never routes or prioritises**; tier routing derives from registry `authority` (a `gate_size` engine ⇒ T3; a `display` engine ⇒ T1) rather than from a hand-maintained path list |

---

## §3 What V1 deliberately excludes

- **Transaction-cost modelling.** Premature: no engine yet has a record long enough for slippage
  assumptions to change a conclusion. Revisit when an engine clears the 50-episode floor.
- **Vendor economics (PART XVII).** The mechanism is specified (architecture §6) but a
  leave-one-feed-out challenger needs the same accrual time as any signal. The honest V1 answer
  for most feeds is *"we cannot yet say"*, and publishing that beats a fabricated attribution.
- **Cross-engine ensemble scoring.** Would create a new un-gauntleted composite signal — exactly
  what `DNR:KILL-REGIME-SCORECARD` killed.
- **Any performance-based hard gate.** Noise-driven vetoes on records this short (standards §8.1).

---

## §4 Definition of done for V1

- [ ] T1 registry regenerated on every PR that moves one of its (PR-only) inputs — **not
      nightly, deliberately**: it carries nothing derived from the append-only claim
      corpus, so there is nothing an automated lane could move, and a nightly rewrite of a
      ~800 KB tracked JSON would be a push storm for zero information. Every engine has
      `output_class`, `authority`, `graded_by_design`, and — above `display` —
      `evidence_ref`
- [ ] T2 Prophet plans carry direction-signed benchmark excess and MFE/MAE
- [ ] T3 `check_qledger_metric_validity.py --strict` green in CI
- [ ] T4 every engine output resolves a health state from the reader's view
- [ ] T7 scorecards render for five different output classes with five different metric sets
- [ ] T8 CEO view renders honestly, including a nearly empty Validated list
- [ ] T9 every directional engine registering, with correct `direction` and `horizon_d`
- [ ] T6 ≥15 golden cases seeded from already-adjudicated material
- [ ] The six-month claim in architecture §9 is supportable: a pre-registered,
      placebo-controlled, PIT-shadowed forward record at declared horizons, published beside
      every disproven idea
