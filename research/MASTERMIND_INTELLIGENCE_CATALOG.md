# Mastermind Intelligence Catalog

**Authored** 2026-08-12 · **Method** repository reconnaissance, every number recomputed from
`HEAD` this session · **Scope** what intelligence Mastermind produces, how it is graded today,
and where the evaluation is missing or misleading.

> Reading note. This catalog deliberately reports *measurements*, not documentation. Where a
> docstring and the artifact disagreed, the artifact won and the discrepancy is recorded. Every
> figure below is reproducible with the command in §7.

---

## 0. The headline, before the inventory

Mastermind does not have an evaluation problem of the usual kind. The usual kind is "nobody
measured anything." Here the opposite is true: the repository contains a **prereg culture, a
kill registry, a matched-control grading substrate, a placebo tape, a champion-vs-challenger
shadow harness, and 16 freshness/health monitors under `scripts/`.** By the standards of most quant shops this is
already upper-decile infrastructure.

The problem is three-fold and specific:

1. **The graded record is younger and thinner than the machinery suggests.** The Universal
   Scoreboard holds 45,203 claims — and **not one claim family has produced a single verdict at
   its own declared horizon.** Every verdict in the store is off-horizon.
2. **The flagship's live record cannot yet distinguish itself from noise.** Prophet US: 28
   closed plans, mean +0.51%, **t = +0.178**. And its *plan* ledger has no benchmark field, so
   that headline is a raw return with no alpha behind it — while Prophet's *board* is graded
   correctly against SPY and sector ETF. The un-benchmarked surface is the one carrying the
   public narrative (§5, Finding C-5).
3. **Three ways to read the store produce impressive numbers that mean nothing**, and one of
   them is already emitted by a shipped script (§4.3). These are now caught by a gate
   (`scripts/check_qledger_metric_validity.py`, added with this catalog).

None of this says the intelligence is bad. It says **we cannot currently prove it is good**, and
the distance between those two statements is the whole subject of this program.

---

## 1. The registries that already exist

Four registries exist. None of them is an *engine* registry, which is the gap (§6).

| Registry | Location | Unit | Count | What it governs |
|---|---|---|---|---|
| Signal bus / synapse | `config/synapse.yml` | cross-engine artifact | **642** | producer, consumers, freshness SLA, storage, qualification tier, horizon role |
| Setup species | `data/species/registry.json` | tradeable setup archetype | **27** | validation + deployment lifecycle, mechanism, rejection rules |
| Kill / law / hold | `research/DO_NOT_REBUILD.md` | forbidden construction | 181 lines | what may not be rebuilt, with the evidence that killed it |
| Universal Scoreboard | `data/qledger/{claims,grades}.jsonl` | dated claim + its grades | **45,203 / 55,287** | the claim→outcome substrate |

### 1.1 Signal bus (`config/synapse.yml`)

642 artifacts across **99** distinct `owner_program` values. Field coverage is genuinely high:

- `tier` — 642/642 · `horizon_role` — 642/642 · `storage`/`format`/`owner_program` — 642/642
- `freshness_sla_hours` — **635/642**
- `consumers` — 527/642 (115 artifacts declare no consumer)

Tier distribution:

| tier | n | meaning |
|---|---|---|
| `display` | 374 | may be shown; carries no authority over another engine |
| `infrastructure` | 162 | plumbing, not a signal |
| `shadow` | 101 | accruing toward promotion; read by nothing that ranks |
| `scored` | **5** | may inform rank/size/gate |
| `confirmer` | **0** | vocabulary exists, never used |

The registry describes itself as **passive**: *"This file is PASSIVE in W0 — it names what
exists; it does not yet enforce read-gating or stamp envelopes."* That is accurate.
`scripts/check_synapse_registry.py` is a hard gate on registry *integrity* (fields, enums,
producer existence). `scripts/check_synapse_reads.py` — which catches undeclared readers, i.e.
the actual leak class — is **WARN-tier and exits 0**.

**The five `scored` artifacts**, the only artifacts permitted to influence rank/size/gate:

| id | path | producer | qual_ladder_ref |
|---|---|---|---|
| `vector-calibration` | `data/vector/calibration.json` | `scripts/calibrate_vector.py` | **none** |
| `hazard-model` | `data/hazard/model_price_c4414dcb.json` | `scripts/fit_cycle_hazard.py` | **none** |
| `vol-regime-gate` | `data/vol_regime/gate.json` | `scripts/validate_vol_regime.py` | **none** |
| `vol-regime-basket-overlay-gate` | `data/vol_regime/basket_overlay_gate.json` | `scripts/backtest_vol_overlay.py` | **none** |
| `site-basket-washout-state` | `site/factordata/basket_washout_state.json` | `scripts/build_basket_washout_state.py` | `RECLAIM_VETO_CONDITIONAL_PREREG.md` |

**Finding C-1 (integrity).** Four of the five artifacts holding rank/size/gate authority carry
no pointer to the pre-registration that earned them that authority. The authority tier is the
one place a `qual_ladder_ref` is not optional.

**Finding C-2 (semantics).** `tier` does **not** mean "carries authority with the user." The
Prophet graded board — `site-us-standouts` (`site/factordata/us_standouts.json`) — is
`tier: display`, as is `prophet-index`. Those surfaces order what a paying user sees. The tier
vocabulary conflates *authority over another engine* with *authority over a human*, and only the
first is governed. This is the single most consequential registry defect, because every
"only 5 things are scored" reassurance is measuring the wrong thing.

### 1.2 Setup species (`data/species/registry.json`)

27 species with a genuine, code-enforced lifecycle — this is the best-governed surface in the
repository:

- `validation_status` ∈ {`phase0`, `accruing`, `validated`, `falsified`, `retired`};
  **`falsified` and `retired` are terminal**.
- `deployment_status` ∈ {`unshipped`, `chip`, `ledger_fields`, `graded_bonus`, `gate_weight`} —
  an explicit escalation ladder from "shown" to "sizes a position."
- Transitions only via `engine.species_registry.transition_validation_status()`; horizon-class
  changes force `bump_version()`.

The registry already carries `adjacent_falsified`, `rejection_rules`, and `evidence_stack` per
entry. **This is the model the engine registry in §6 should copy**, not replace.

### 1.3 Kill registry (`research/DO_NOT_REBUILD.md`)

An institutional memory of what has already been disproven, with the measurement that
disproved it — e.g. `DNR:KILL-PRIMED-DIRECTIONAL-GATE` records a three-leg pre-registered
NO-GO (75,722 events, 233 names, CI entirely negative) and `DNR:KILL-FRESH-TICKS-WINDOW`
records a third-look null with date-blocked CIs. Rows are cited by stable key, compiled to
blocklists, and CI-enforced.

Most organisations cannot name one idea they killed. This one has a registry with receipts.
**It is the strongest single piece of evidence that Mastermind's research process is honest**,
and §8 argues it is the most under-used asset in the company.

---

## 2. Output-class taxonomy, applied

The handoff's classes, mapped onto what actually exists. The right evaluation method follows
from the class — this is why "win rate" cannot be the universal metric.

| Class | Representative engines here | Correct primary metric | Wrong metric to avoid |
|---|---|---|---|
| **Predictive** (directional, dated) | Prophet US/CN plans, `radar`, `whitehouse`, `policy`, altdata picks | hit rate + excess vs matched control **at the declared horizon**; calibration curve | raw return; any pooled signed excess (§4.3) |
| **Ranking** | `us_standouts` board ordering, `composite_rank`, sector rotation, basket scores | rank-IC / decile monotonicity / top-vs-bottom spread | hit rate of rank 1 |
| **Classification (state)** | regime vector, risk radar state, `quad_hard_label`, vol regime | transition-lag, stability, state-conditional forward distributions | accuracy vs a label the engine itself defines |
| **Detection (event)** | dislocation, ignition radar, catalyst/event lanes, contagion | precision/recall vs a curated event list; false-positive burden per unit time | hit rate without a denominator of missed events |
| **Descriptive** | GEX, concentration, exposure, breadth, correlation | reconciliation against source; reproducibility; freshness | any forward-return metric at all |
| **Salience / importance** | `us_importance_v0`, `cn_importance_v0`, `china_news`, `narrative` | rank-IC against realised |move|; attention-vs-outcome coverage | **hit rate — undefined here (§4.2)** |
| **Generative** | Brain gateway `/api/brain/*`, CIO/daily brief, analyst doctrine | mechanical checks → rubric judge → frozen benchmark regression | LLM-judge score as sole evaluator |

The **salience** row is the one the handoff's taxonomy does not name and this repository needs
most: 71% of all registered claims are salience claims (§4.2).

---

## 3. Engine families and their evaluation status

Grouped by owner program (synapse `owner_program`, 99 values; the largest shown). "Graded"
means outcomes are attached to dated predictions in a ledger, not that a study once ran.

| Family | Artifacts | Tiers | Ledger / grader | Evaluation status |
|---|---|---|---|---|
| neural-web | 64 | 29 display / 28 infra / 7 shadow | `qledger`, `contradictions.py`, `response_eval.py` | Partly graded; generative side has a rubric but one benchmark case |
| government-revenue-foresight | 42 | 31 infra / 11 display | `grade_policy_calendar.py` | Candidate ledger exists; no promotion-grade record |
| long-hold | 36 | 35 display / 1 infra | — | **Display-only, ungraded** |
| oracle | 29 | 18 display / 6 shadow / 5 infra | `oracle_gauntlet_p3/p8/compound`, `oracle_reversion_forward_ledger` | **Best-gauntleted family in the repo** |
| china-alpha | 25 | 12 shadow / 10 display / 3 infra | `cn_*` ledgers, `grade_qledger` | Accruing; W1–W3 under a standing STOP-SHIP (`DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`) |
| qualitative-intelligence | 23 | 12 shadow / 10 display / 1 infra | `qledger` (owner) | Substrate owner; see §4 |
| capital-structure-intelligence | 20 | 18 infra / 2 display | — | Descriptive; correctly ungraded on returns |
| options-intelligence-program | 19 | 7 infra / 6 display / 6 shadow | `OPTIONS_HISTORY_GAUNTLET_E1` | Two families killed by gauntlet (`DNR:KILL-DOI-FAMILY`, `KILL-SKEW-DECELERATION`) |
| macro-release-intel | 17 | 9 shadow / 4 infra / 4 display | `grade_news_events.py` | Accruing |
| macro-context-rail | 17 | 16 display / 1 infra | — | **Display-only, ungraded** |
| cycle-intelligence | 14 | 9 infra / 2 shadow / 2 display / **1 scored** | `fit_cycle_hazard.py` | One scored artifact, no `qual_ladder_ref` |
| prophet | 3 (+ ~25 modules) | 3 display | `data/prophet/ledger.jsonl`, `us_board_ledger`, `prophet_arena` | See §5 — richest, and thinnest |

**Measured:** of the **99** distinct `owner_program` values in the registry, **48 own at least one
grader-shaped artifact and 51 own none** — where "grader-shaped" is a name match on
`grade|ledger|calibrat|backtest|track|audit|gauntlet|forward_log|scoreboard|fitness` across each
artifact's id, path and producer.

That heuristic **undercounts graded programs and 51 is therefore an upper bound**, not a count.
`blocked-entry-override` lands in the "none" bucket while actually owning a `scored`-tier artifact
whose `qual_ladder_ref` points at a real pre-registration — its grading simply is not visible in
a filename. Read the figure as *"about half the programs have no visible grading surface"* and no
further.

Nor is an ungraded program automatically wrong: descriptive analytics (GEX, concentration,
exposure) *should not* carry a forward-return grade, and forcing one would be exactly the
"evaluate everything by win rate" error the handoff warns against. The registry gap in §6 is what
makes the distinction unauditable today — nothing records whether a program is ungraded *by
design* or *by neglect*, which is why `graded_by_design` is a required field of the engine
registry and why this paragraph needs a heuristic at all.

---

## 4. The Universal Scoreboard, measured

`engine/qledger.py` (1,279 LOC) is the closest thing Mastermind has to the handoff's PART VII
live prediction ledger — and it is genuinely well built. It already implements, unprompted,
most of what PART VII asks for: PIT entry levels, an engine-derived falsifier, `check_by` dates,
matched-control excess, a `timestamp_quality` embargo, honest `n_dates` via independent date
clusters, Wilson CI lower bounds, and an `is_placebo` slot for a synthetic control tape.

**Corpus at `HEAD` (2026-08-12):**

| Measure | Value |
|---|---|
| Claims | 45,203 (37.1 MB) |
| Grades | 55,287 rows over 39,360 distinct claims (**87% of claims have ≥1 grade**) |
| Desks / families | 13 / 17 |
| Date span | 2026-06-15 → 2026-08-12 (**59 distinct as-of dates**) |
| Placebo claims | 940 (1,299 graded rows) |
| Claim status | 45,202 `open`, 1 `rejected` |

### 4.1 The placebo tape works

Placebo excess: n=1,299, mean **+0.0022**, t=**+0.94** — indistinguishable from zero, exactly as
a synthetic control should be. Real claims: n=53,988, mean −0.0065, t=−17.92. The gap between
those two lines is *not* evidence of skill (see §4.3) but the placebo arm behaving correctly is
real evidence that the grading plumbing is not systematically biased. **This is the single most
credible artifact in the evaluation stack** and it should be in every scorecard.

### 4.2 71% of the corpus is salience, not prediction

| direction | claims | share |
|---|---|---|
| `0` (salience/importance) | **32,123** | **71.1%** |
| `±1` (directional) | 13,080 | 28.9% |

Salience families: `us_importance_v0` (12,946), `us_importance_v0_pit` (12,946),
`cn_importance_v0` (2,338), `cn_importance_v0_pit` (2,338), `china_news` (812),
`narrative` (331), `china_special_sits` (70), `placebo` (342).

For these, `hit` is undefined by construction and stored null — which is why 38,075 of 55,287
grade rows carry `hit: null`. **That is correct behaviour, not a bug.** The hazard is
presentational: "45,203 claims registered" invites a reader to believe the directional evidence
base is 3.5× larger than it is. The directional corpus is ~13,080 claims across five families.

The `*_pit` twins (`us_importance_v0_pit`, `cn_importance_v0_pit`) are a **point-in-time control
arm** — an exact-size shadow of each importance desk. This is a lookahead control most shops
never build, and it is the right pattern.

### 4.3 Three readings that produce meaningless numbers

These are now enforced by `engine/qledger_validity.py` + `scripts/check_qledger_metric_validity.py`.

**V1 — signed excess pooled across directions.** `grades.excess` is **raw** subject-minus-control
return; it is *not* signed by the claim's direction. `hit` is what carries direction. Proof, from
the cross-tab of (direction, hit, sign(excess)) over the live corpus:

```
(-1, True,  excess<=0)  4594      (1, True,  excess>0)  4046
(-1, False, excess>0)   4140      (1, False, excess<=0) 4432
```

A **correct bearish call contributes a negative excess.** Therefore the pooled −0.0065 (t=−17.92)
measures the drift of the subject universe, not skill. `scripts/grade_qledger.py` emits a
per-family `excess_mean`; for `radar` (3,681 bullish + 5,626 bearish) that figure is
uninterpretable. The same script's placebo duel correctly uses `mean_abs_excess`, so the design
is *partly* aware of the distinction — it simply is not enforced.

**V2 — hit rate on a salience family.** A ratio over an empty verdict set (§4.2).

**V3 — off-horizon verdicts.** Grading emits each in-scope horizon as it matures, so a 63-day
claim accrues 5d and 21d rows months before its own ruler resolves. Live corpus grade horizons:

| horizon_d | 1 | 3 | 4 | 5 | 21 | 63 | 126 |
|---|---|---|---|---|---|---|---|
| grade rows | 2 | 16 | 14 | 39,328 | 15,927 | **0** | **0** |

Declared horizons that have produced **zero** verdicts at their own ruler: `radar` (63),
`altdata`/`altdata_mid`/`altdata_slow` (63), `policy` (126), `narrative_source_call` (28),
`whitehouse` (7 — graded only at 1/3/4/5).

**Finding C-3.** *No claim family in the Universal Scoreboard has produced a single verdict at
its own declared horizon.* The corpus began 2026-06-15; 63 trading days had not elapsed by
2026-08-12. This is an **accrual fact, not a defect** — but it means every hit rate currently
computable from this store is off-horizon, and reading one as a family's record is precisely
what `DNR:KILL-OFFHORIZON-VERDICTS` forbids.

### 4.4 What the directional record actually says, read legally

Hit rates below are at 5d/21d — **off-horizon for every family listed**, and therefore *not*
verdicts. They are reported here as accrual telemetry, with CIs, because pretending we have no
information at all would be its own dishonesty.

| desk | graded rows | hit rate | 95% CI | read |
|---|---|---|---|---|
| `radar` | 13,651 | **48.9%** | [48.06%, 49.74%] | tight, and **below 50%** |
| `intel_hub` | 1,949 | **56.1%** | [53.90%, 58.30%] | the only desk clearly above coin-flip |
| `altdata` | 731 | 51.6% | ±3.6pp | indistinguishable from 50% |
| `whitehouse` | 55 | 40.0% | ±12.9pp | n far too small |

`radar`'s CI excludes 50% on the wrong side. That is worth knowing and worth *not* over-reading:
it is an off-horizon measurement of a 63-day signal at 5 and 21 days, which is exactly the
regime in which a slow signal should look worst.

---

## 5. Prophet, measured

Prophet has the deepest apparatus of any engine: `engine/prophet_bridge.py`, `prophet_doors.py`,
`prophet_integrity.py`, `prophet_arena.py`, `prophet_stage_{fusion,inputs,shadow}.py`,
`prophet_miss_audit.py`, `us_prophet_grades.py`, the `engine/prophet_live/` package, and
`scripts/{build_prophet, prophet_live_evaluator, prophet_postmortem, grade_us_board,
run_prophet_pick_autopsies, reconcile_prophet_live}.py`.

**Live forward record — `data/prophet/ledger.jsonl` @HEAD, recomputed this session:**

| Measure | Value |
|---|---|
| Closed plans | **28** (2026-03-18 → 2026-07-31) |
| Distinct signal dates / assets | 24 / 26 |
| Win rate | **32.1%** (9/28) |
| Mean / median result | **+0.514%** / −4.60% |
| sd / se / **t-stat** | 15.26 / 2.88 / **+0.178** |
| 95% CI on mean | **[−5.14%, +6.17%]** |
| Winners / losers | 9 @ +19.73% / 19 @ −8.59% |
| Payoff ratio | 2.30× → breakeven hit rate **30.3%** vs actual 32.1% |
| Mean holding period | 26.1 days |

| outcome | n | mean result |
|---|---|---|
| `T1_HIT` | 7 | +22.60% |
| `T2_HIT` | 1 | +13.03% |
| `EXPIRED` | 9 | −4.44% |
| `INVALIDATED` | 11 | −10.62% |

**Finding C-4.** The record is a *low-hit-rate, positive-skew* profile running **1.8 percentage
points above its own breakeven**. With t = +0.178 it is statistically indistinguishable from
zero. This is not a criticism of Prophet — 28 observations cannot establish anything either way.
It is a statement that **the flagship currently has no defensible performance claim**, and any
marketing that implies otherwise is unsupported.

**Finding C-5 (the most fixable defect in this document).** Prophet has **two** evaluation
surfaces and only one of them is benchmark-graded.

- **The board (ranking layer) is graded correctly.** `scripts/grade_us_board.py` reconstructs
  every past board from git history (~90 committed revisions of
  `site/factordata/us_standouts.json` back to 2026-06-16) and grades every row, per lane
  (buy / watch / leaders / laggard), at 5d/10d/21d/63d **versus SPY and versus the name's own
  sector ETF**, emitting `retro_grades.parquet` plus a track file with hit-rate, precision@k and
  Wilson CIs. This is a properly benchmarked ranking evaluation and should be the template.
- **The plan ledger (the 28 closed trade plans) is not.** Its schema is
  `[asof, asset, close_date, days_held, direction, id, option_result_pct, outcome,
  plan_adherence, schema, signal_date, stock_result_pct]` — **no benchmark field.**
  `stock_result_pct` is raw return, so the headline live record in the table above carries no
  alpha and cannot satisfy the base-rate requirement.

So the defect is narrower than "Prophet has no benchmark" and more awkward: the surface that
carries the *public* performance narrative is the un-benchmarked one. Fixing it is a schema
addition plus a backfill against price data the board grader already reads.

**Finding C-6 (methodology, in Prophet's favour).** `engine/prophet_arena.py` is a
champion-vs-challenger *prospective* shadow harness: K frozen challenger policies re-slice the
same nightly candidate artifact the live path used, graded by the same closure rules onto
per-policy ledgers. Its docstring is explicit that *"nothing here is a backtest and nothing here
is a backfill."* This is the correct answer to PART XIII (intelligence regression) and it
already exists. It should be the template for every other engine, not rebuilt.

**Finding C-7 (a look-count caution).** The arena docstring records the record at 2026-08-05 as
16 closed plans / 12.5% win rate. At `HEAD` it is 28 closed / 32.1%. The record materially
improved across one week and twelve observations. Both readings are honest; the lesson is that
at n≈20 the headline moves several tens of percent on a handful of closures, so **no decision
should be conditioned on this series yet**, in either direction.

---

## 6. The gap: there is no engine registry

Four registries exist (§1) and none of them answers the CEO question *"which parts of Mastermind
are actually working?"* Concretely, nothing in the repository can currently answer:

- How many intelligence engines are there? (`642` is artifacts; `27` is setup species; 99 is
  programs — none is engines.)
- For engine X: what output class, what ledger, what evaluation method, what validation state,
  what evidence, and **is it ungraded by design or by neglect?**
- Which engines carry authority over a *user-facing* surface, as opposed to over another engine?
  (§1.1 Finding C-2 — the tier field cannot answer this.)

**Design constraint, load-bearing.** `DNR:KILL-PARALLEL-KNOWLEDGE-BASE` forbids a second
hand-maintained store parallel to canonical sources. The engine registry must therefore be
**derived and rebuildable** from `config/synapse.yml`, `data/species/registry.json`, the ledger
inventory, and `research/DO_NOT_REBUILD.md` — with only genuinely new fields (output class,
evaluation method, graded-by-design flag) curated. A hand-authored engine list would be the
killed pattern. This is specified as task T1 in `MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md`.

---

## 7. Reproducing every number in this document

```bash
python3 scripts/check_qledger_metric_validity.py --root . --json
python3 -m pytest tests/test_qledger_validity.py -q
```

Corpus figures (§4) and the Prophet record (§5) are recomputed from `data/qledger/*.jsonl` and
`data/prophet/ledger.jsonl`. In a sparse agent worktree those paths are absent on disk while
tracked in `HEAD`; materialise with `git show HEAD:<path>` before measuring, and never read
absence-on-disk as an empty ledger.

---

## 8. What is under-used

Two assets are stronger than anything a new build would produce in six months, and both are
currently invisible to anyone outside the repository:

1. **`research/DO_NOT_REBUILD.md`** — a registry of disproven ideas with the measurements that
   killed them. Sophisticated investors do not ask "what works?"; they ask "what have you
   disproven, and did you act on it?" This document answers that better than any performance
   table Mastermind can currently produce.
2. **The placebo tape** (§4.1) — a live synthetic control arm scoring t=+0.94. A firm that runs
   placebos against its own signals is a firm whose positive results can be believed.

The evaluation OS should surface both, not just returns.

---

## Cross-references

- Architecture: `research/MASTERMIND_INTELLIGENCE_EVALUATION_ARCHITECTURE.md`
- Methodology policy: `research/MASTERMIND_EVALUATION_STANDARDS.md`
- Prophet spec: `research/MASTERMIND_PROPHET_EVAL_SPEC.md`
- Build sequence: `research/MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md`
