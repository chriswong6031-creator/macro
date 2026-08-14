# Mastermind Intelligence Evaluation OS — Architecture

**Authored** 2026-08-12 · **Companion documents** `MASTERMIND_INTELLIGENCE_CATALOG.md` (what
exists, measured), `MASTERMIND_EVALUATION_STANDARDS.md` (methodology policy),
`MASTERMIND_PROPHET_EVAL_SPEC.md` (the first-class case),
`MASTERMIND_INTELLIGENCE_OS_V1_PLAN.md` (build sequence).

---

## 1. The design thesis

**Mastermind does not need an evaluation system built. It needs the six evaluation systems it
already has to be joined, named, and made answerable to one question.**

The reconnaissance (catalog §1–§5) found a control-capable grading substrate (matched controls
supported in code; no live claim carried one until the P0d contract — prospective
matched-control evidence begins only when controlled claims register), a live placebo
tape, a prospective champion-vs-challenger harness, a code-enforced promotion lifecycle, a
kill registry with receipts, a contradiction detector, and 16 freshness/health monitors under scripts/. What it did
not find is anything that can answer *"which parts of Mastermind are working, and how do you
know?"* — because there is no unit of account. The registries count **artifacts** (642),
**setups** (27), and **programs** (99). None counts **engines**, and none records whether an
engine is ungraded by design or by neglect.

So the architecture below is deliberately thin. Every layer either (a) already exists and is
named here so it is not rebuilt, or (b) is a joining layer measured in hundreds of lines, not
thousands. **The failure mode this architecture is designed against is building a seventh
evaluation system.**

### 1.1 What must not be built

| Do not build | Because it exists | Location |
|---|---|---|
| A prediction ledger | Universal Scoreboard: PIT levels, falsifier, matched control, embargo, Wilson CI, placebo slot | `engine/qledger.py` |
| A backtest framework | 37 calibration/backtest harnesses (26 `calibrate_*` + 11 `backtest*`) with pre-registered gates | `scripts/calibrate_*.py`, `backtest_*.py` |
| A version-regression harness | Prospective champion-vs-challenger shadow arena | `engine/prophet_arena.py` |
| A contradiction detector | 7 typed signal pairs, display-only, fail-open | `engine/neuralweb/contradictions.py` |
| A generative-answer rubric | 3-tier: mechanical → LLM judge (8 axes) → frozen benchmark | `engine/neuralweb/response_eval.py` |
| A freshness registry | 635/642 artifacts carry `freshness_sla_hours` | `config/synapse.yml` |
| A promotion lifecycle | 5-state validation × 5-state deployment, terminal states, code-enforced | `engine/species_registry.py` |
| A kill registry | 181 lines of disproven constructions with their evidence | `research/DO_NOT_REBUILD.md` |
| A second knowledge store | forbidden outright | `DNR:KILL-PARALLEL-KNOWLEDGE-BASE` |

---

## 2. The five layers

```
  L4  ANSWER      Intelligence scorecard (per engine) · CEO view (global)
                  ── the only layer a human reads ──
  L3  JUDGE       Promotion gauntlet · quality gates · regression comparison
                  ── decides what may carry authority ──
  L2  MEASURE     Metric contracts per output class · segmentation · base rates
                  ── turns outcomes into legal numbers ──
  L1  RECORD      Universal Scoreboard (claims → grades) · engine-local ledgers
                  ── what we believed, before we knew ──
  L0  DECLARE     Engine registry · artifact registry · health contract
                  ── what exists, what it depends on, what it may claim ──
```

L1, L3 and most of L2 exist. **L0 is missing its engine unit, and L4 does not exist at all.**

### L0 — DECLARE: the engine registry (the missing keystone)

One row per **intelligence engine** — the unit that produces a claim a user or another engine
acts on. Derived, never hand-maintained (`DNR:KILL-PARALLEL-KNOWLEDGE-BASE`): the spine is
generated from `config/synapse.yml` (producer → artifacts → consumers → SLA → tier),
`data/species/registry.json` (lifecycle), the ledger inventory, and `DO_NOT_REBUILD.md`. Only
fields that genuinely do not exist elsewhere are curated.

Per engine:

| Field | Source | Why |
|---|---|---|
| `engine_id`, `producer`, `artifacts`, `consumers` | derived from synapse | identity + blast radius |
| `output_class` | curated (7 classes, catalog §2) | **selects the metric contract** — the whole point |
| `graded_by_design` | curated: `yes` / `no — descriptive` / `no — not yet` | separates "correctly ungraded" from "neglected"; today indistinguishable |
| `ledger` | derived | where its record lives, or `none` |
| `declared_horizon` | derived from `horizon_role` + claim `horizon_d` | the only legal verdict horizon (`DNR:KILL-OFFHORIZON-VERDICTS`) |
| `authority` | curated: `display` / `engine_input` / `user_ranking` / `gate_size` | **fixes catalog Finding C-2** — the synapse `tier` cannot express authority over a *human* |
| `validation_state` | derived from species registry / prereg / gauntlet | phase0 → accruing → validated → falsified → retired |
| `evidence_ref` | curated | prereg or gauntlet doc; **mandatory above `display`** (fixes Finding C-1) |

The `authority` field is the load-bearing addition. Today `site-us-standouts` — the board that
orders what a paying user sees — is `tier: display`, identical to a decorative chip. An
evaluation OS that cannot distinguish those two cannot prioritise anything.

### L1 — RECORD: adopt, don't rebuild

`engine/qledger.py` is the substrate. Its contract already satisfies most of the handoff's
PART VII. The work is **adoption, not construction**: 26 files reference it against 99
programs, and the largest un-adopted producer is Prophet, which keeps its own
`data/prophet/ledger.jsonl` with a schema that has no benchmark field (catalog Finding C-5).

Integrity is achieved without cryptography. The handoff correctly says not to over-engineer it.
Append-only JSONL + deterministic `claim_id` (hash of desk/asof/scope/horizon) + `graded_at`
stamps + a git-tracked store already makes silent rewriting detectable: **git is the tamper
evidence.** The one addition worth making is a nightly **ledger-advance receipt** — row counts
and a content digest per family, appended to its own log — so a rewrite is detectable without
diffing 37 MB. (`scripts/check_ledger_advance.py` already exists; extend it, don't replace it.)

### L2 — MEASURE: metric contracts per output class

The handoff's instruction "do not evaluate everything using win rate" becomes executable here:
**a metric contract per output class**, and a linter that refuses illegal readings.

This layer is **partly shipped with this document**: `engine/qledger_validity.py` +
`scripts/check_qledger_metric_validity.py` enforce the three invariants that were found live
(catalog §4.3) — signed excess may not be pooled across directions; a salience family has no
hit rate; a verdict may only be read at the family's declared ruler. On the live corpus that
gate returns 18 findings across 11 families.

The contracts to add, per class:

- **Predictive** — hit rate at the declared horizon, with matched-control excess where the
  family's control policy requires it and benchmark-relative excess otherwise (P0d contract);
  calibration curve;
  MFE/MAE; honest-N by independent date cluster (already in `qledger`).
- **Ranking** — rank-IC, decile monotonicity, top-minus-bottom spread with date-blocked CIs.
  Never a hit rate.
- **Classification** — transition lag, state stability, forward distribution conditional on
  state. Never accuracy against a self-defined label.
- **Detection** — precision *and* recall against a curated event list (this needs the Golden
  Case Library, §4), plus false positives per unit time.
- **Descriptive** — reconciliation against source, reproducibility, freshness. **No forward
  return metric may be attached**; attaching one is itself a defect.
- **Salience** — rank-IC against realised |move|; coverage of what actually mattered.
- **Generative** — §5.

Every metric carries a **base rate** alongside it (handoff PART XV). A 32% hit rate is
meaningless without the matched-universe base rate; the `qledger` matched-control and the
`*_pit` twin desks are the machinery for this and already exist.

### L3 — JUDGE: gates, gauntlet, regression

The promotion gauntlet exists and is genuinely good (`oracle_gauntlet_*`, the species
lifecycle, 54 `*PREREG*.md` documents). Two things are missing:

**(a) Gate tiering.** Per handoff PART XIX, and calibrated so research does not stop:

| Gate | Blocks release? | Examples |
|---|---|---|
| **Hard** | yes | lookahead/leakage test fails; a `scored`-tier artifact has no `evidence_ref`; a metric-validity `invalid` finding on a published number; freshness contract `unavailable` on a required input |
| **Warning** | no — annotates, requires a written waiver | alpha declines beyond threshold; ranking monotonicity degrades; sector concentration jumps; false-positive rate rises |
| **Informational** | no | coverage change, timing distribution shift, holding-period drift |

The hard list is deliberately short and made entirely of **integrity** properties, not
performance properties. Performance gates on n=28 records would be noise-driven vetoes. This
is the direct lesson of catalog Finding C-7: the Prophet headline moved from 12.5% to 32.1% in
one week on twelve closures.

**(b) Multidimensional regression.** `prophet_arena.py` is the template — prospective, same
candidate artifact, same closure rules, per-policy ledgers. Generalise its *interface* so any
engine can register challengers. The scorecard for a version change must report coverage, alpha,
drawdown, timing, concentration, false positives, crash frequency and monotonicity **together**,
so "better average return" can never mask "4× worse tail."

### L4 — ANSWER: scorecard and CEO view

The layer that does not exist. Two artifacts, both derived, both regenerated nightly.

**Per-engine scorecard** — engine-specific by output class, never a fixed metric list:

```
PROPHET US                                    validation: accruing
  Health          data freshness OK · 0 contradictions · inputs 12/12
  Live record     28 closed · win 32.1% · mean +0.51% · t=+0.18
                  ⚠ NO BENCHMARK IN SCHEMA — alpha not computable
                  ⚠ n below the 50-observation reporting floor
  At its ruler    verdicts at declared horizon: 0
  Regression      arena: 4 challengers accruing · champion unchanged 14d
  Failures        INVALIDATED 11 (−10.6%) · EXPIRED 9 (−4.4%)
  Since v3        coverage +18% · tail unchanged · timing unchanged
```

Every scorecard shows **what it cannot yet claim**, in the same visual weight as what it can.
That is the difference between a scorecard and a brochure.

**CEO view** — one page, three lists, ranked by evidence strength rather than by impressiveness:

1. **Validated** — passed a pre-registered gauntlet, evidence linked, at its own horizon.
2. **Accruing** — recording honestly, insufficient N. Shows *when* it will be decidable.
3. **Ungraded by design** — descriptive analytics; correctly carries no return metric.
4. **Degraded** — a freshness or contradiction state, live.
5. **Disproven** — from `DO_NOT_REBUILD.md`. **This list is an asset, not an embarrassment.**

Today, honestly rendered, list 1 would be nearly empty and list 2 nearly full. That is the
correct picture and rendering it is the point.

---

## 3. Freshness as an intelligence property (PART X)

`config/synapse.yml` already carries `freshness_sla_hours` on 635/642 artifacts. The gap is
enforcement and propagation:

- **Enforcement**: `check_synapse_registry.py` is a hard gate on *registry integrity*;
  `check_synapse_reads.py`, which catches undeclared readers, is WARN-tier and exits 0.
- **Propagation**: an SLA measured on the producer says nothing about what a reader received.
  A producer can be green while every consumer reads a stale copy.

The health contract therefore attaches to the **output**, not the feed. Each engine output
declares its input set and resolves to one state:

| State | Meaning | Consequence |
|---|---|---|
| `healthy` | all required inputs within SLA | normal |
| `degraded` | a non-critical input stale or partially missing | **confidence must degrade**; surface says so in plain words |
| `stale` | a required input beyond SLA | output may be shown with an explicit as-of, may not gate or size |
| `unavailable` | a required input missing | output withheld; **absence stated, never rendered as a neutral reading** |

The last row is the one that matters: *"I could not look"* must never render as *"I looked and
saw nothing."* This is the same law the metric-validity gate applies to an absent store, and
the same law the user-facing doctrine applies to nulls.

---

## 4. Cross-engine consistency (PART IX)

`engine/neuralweb/contradictions.py` (1,142 LOC) already detects seven typed signal pairs, is
**display-only by hard law**, fail-open, and forbidden from using `critical` severity. That law
is correct and must not be relaxed: a contradiction detector wired to a gate becomes a new
un-gauntleted signal, which is exactly what `DNR:KILL-REGIME-SCORECARD` killed.

The architecture adds classification, not authority. Every detected disagreement resolves to
one of three kinds:

- **Healthy disagreement** — different horizons or domains (a 5-day entry signal and a 126-day
  macro read may legitimately oppose). Resolved by comparing `horizon_role`; **no action**.
- **Important tension** — same horizon, same subject, opposed direction, both fresh, both
  validated. **Reduces conviction** and is worth showing the user in plain words.
- **Impossible contradiction** — two engines assert incompatible *facts* (not views). Almost
  always one is stale or broken. **This is an incident**, routed to the health contract, not a
  market signal.

Only the third is actionable automatically, and its action is a data-integrity alert. The
useful derived quantities are `agreement_score` and `independent_corroboration` — with the
caveat that corroboration between two engines sharing an input is not corroboration, so the
measure must be computed over **input-disjoint** engines. The synapse consumer graph already
holds the dependency structure needed to determine disjointness. Anything else is double-counting
one signal and calling it confluence.

---

## 5. Generative intelligence (PART XI)

`engine/neuralweb/response_eval.py` (1,115 LOC) is well-designed and its tiering is right:
mechanical checks first (free, deterministic, catching exactly what an LLM judge is worst at —
a judge reading a leaked doctrine header often scores the answer as well-structured), then an
LLM judge over eight rubric axes with the mechanical findings supplied so it never guesses, then
a frozen benchmark case as the regression tripwire. `PASS_THRESHOLD = 80`. Scores are
**internal QA telemetry only** and may never reach a public surface — a constraint that should
stay.

Two gaps, both in the corpus rather than the machinery:

1. **`engine/neuralweb/eval/` holds exactly one benchmark case** (`bear_steepener`, 2026-07-29).
   A one-case regression suite detects one kind of regression. This is the Golden Case Library
   (PART XII) and it is the highest-leverage cheap build in the whole program — see below.
2. **Deterministic claim verification is not wired.** The strongest possible check on generated
   prose is not a judge: it is verifying every *number* in the answer against the artifact it
   came from. The Live Market State Packet (`engine/neuralweb/market_packet.py`) is
   aggregation-only and already the grounding source, so numeric claims are checkable by
   construction. A regex-extract-and-reconcile pass would catch the highest-severity failure
   class (a confidently wrong figure) far more reliably than any rubric axis.

### The Golden Case Library

A curated set of historical market situations, each preserving **what was knowable at the time**,
the relevant PIT data slice, the expected interpretation, and the common failure modes. The
handoff calls it a board-exam dataset and that is exactly right.

Mastermind is unusually well-positioned to build it cheaply, because **`DO_NOT_REBUILD.md` and
the postmortem corpus are already half of it.** `POSTMORTEM_20260723_MAG7_FORCED_CALL`,
`KILL-PRIMED-DIRECTIONAL-GATE`, `KILL-FRESH-TICKS-WINDOW`, the gold real-rate case study — each
is a documented case with a known correct reading and a documented wrong one. Seeding the library
from cases the firm has already adjudicated costs a fraction of curating from scratch, and every
case arrives with its adjudication attached.

Target: 20 cases covering genuine breakout, failed breakout, bear-market rally, sector rotation,
earnings dislocation, commodity squeeze, macro regime shift, false catalyst, liquidity shock,
speculative bubble, bubble top, rate shock, geopolitical shock.

---

## 6. Attribution and data-source economics (PARTS XVI–XVII)

**Attribution.** Leave-one-plane-out on the prospective arena is the honest form: run a
challenger identical to the champion except that plane X is removed, and let both accrue on the
same nights against the same ruler. This reuses `prophet_arena.py` wholesale and avoids the fake
precision of retrospective decomposition. It answers *"is Neural Web plane X adding value?"* the
only way that survives scrutiny — forward, on the same tape.

**Vendor economics.** The same mechanism, one level up. For each paid feed: which engines consume
it (the synapse consumer graph already answers this), what unique information it adds (does an
input-disjoint engine already carry the signal?), and champion-vs-challenger with the feed
withheld. The measurement is slow — a challenger needs the same accrual time as any signal — so
the practical V1 answer for most feeds will be *"we cannot yet say"*, and saying that is better
than a fabricated attribution. `SIGNAL_COMMONS_W6_PAID_DATA_MEMO.md` is the existing home.

---

## 7. Evaluation tiers and the Agent OS interface (PARTS XVIII, XXIII)

| Tier | Runs on | Cost | Gate |
|---|---|---|---|
| **T0 integrity** | every PR | seconds | hard — schema, nulls, crashes, registry integrity, metric validity |
| **T1 smoke** | every PR touching an engine | ~1 min | hard — known cases produce known-shaped output; freshness contract resolves |
| **T2 historical regression** | engine-module PRs | minutes | warning — golden cases, prior-version comparison |
| **T3 research validation** | promotion only | hours | hard for promotion — walk-forward, holdout, regime split, prereg conformance |
| **T4 live-forward** | continuous | ongoing | the only tier that can move an engine to `validated` |

**The Agent OS interface is two contracts, both narrow:**

- *Evaluation OS → Agent OS*: emits a **structured research issue** — engine, metric, observed
  change, segment, evidence link, suggested tier. It never routes or prioritises; it states a
  finding in a schema Agent OS can act on.
- *Agent OS → Evaluation OS*: asks **"what tier does this diff require?"** and receives an answer
  derived from the engine registry — a PR touching a `gate_size`-authority engine requires T3; a
  PR touching a `display` engine requires T1.

That second contract is the entire integration, and it is only possible because L0 exists. It is
another reason the engine registry is the keystone rather than a nicety.

---

## 8. The research flywheel (PART XXII)

The loop the handoff describes is already three-quarters implemented and unconnected:

```
 prediction ──► qledger.register()                        [EXISTS]
 outcome    ──► grade_qledger.py                          [EXISTS]
 failure    ──► run_prophet_pick_autopsies.py             [EXISTS, Prophet only]
 clustering ──► failure taxonomy across engines           [MISSING]
 hypothesis ──► prereg document                           [EXISTS, manual]
 test       ──► calibrate_*.py / gauntlet                 [EXISTS]
 compare    ──► prophet_arena.py                          [EXISTS, Prophet only]
 kill/ship  ──► DO_NOT_REBUILD.md / species transition    [EXISTS]
 continue   ──► live-forward accrual                      [EXISTS]
```

The missing link is **failure clustering** — turning individual autopsies into a taxonomy where
similar failures aggregate into a research task. Generalising the two Prophet-only steps
(autopsy, arena) to any registered engine closes the loop. That is a generalisation job, not a
new system.

---

## 9. If we had to prove it tomorrow

*The handoff's closing question, answered without protecting anyone's feelings.*

**What we could produce tomorrow — genuinely credible:**

1. **A kill registry with receipts.** `DO_NOT_REBUILD.md` documents constructions the firm
   disproved and abandoned, with the measurements — pre-registered gates, date-blocked CIs,
   split-half stability, placebo comparisons. A sophisticated investor learns more from this
   than from any equity curve, because it is nearly impossible to fake and directly measures
   whether the process overrides its own enthusiasm. It shows the firm killed things it wanted
   to be true.
2. **A live placebo tape.** 1,299 graded synthetic control rows scoring t=+0.94 — indistinguishable
   from zero, as designed. Very few shops run placebos against their own live signals.
3. **A point-in-time control arm.** The `*_pit` twin desks shadow each importance desk at equal
   size — a structural lookahead control, not a claim of not having peeked.
4. **A prospective challenger harness.** `prophet_arena.py` accrues alternatives forward, on the
   same nights, under the same closure rules. It structurally cannot produce a flattering
   backtest.
5. **A code-enforced promotion lifecycle** with terminal falsification states.

**What we could not produce tomorrow — state this plainly:**

1. **No engine has a validated performance record at its own declared horizon.** Not one. The
   qledger corpus began 2026-06-15 and no family's ruler has matured (catalog Finding C-3).
2. **The flagship cannot distinguish itself from noise.** Prophet US: n=28, mean +0.51%,
   **t=+0.178**, CI [−5.14%, +6.17%].
3. **No alpha figure exists for Prophet's trade plans** — the plan ledger has no benchmark field,
   so its every result is a raw return. Prophet's *board* is properly graded versus SPY and
   sector ETF by `grade_us_board.py`; the un-benchmarked surface is the one that carries the
   public performance narrative (Finding C-5).
4. **Three ways of reading the scoreboard produce impressive, meaningless numbers**, one of them
   already emitted by a shipped script (catalog §4.3).
5. **Up to 51 of the 99 registered programs have no visible grading surface** (name-match
   heuristic, catalog §3 — it undercounts, so treat 51 as an upper bound), and nothing records
   which of those are ungraded *correctly*.

**Honest verdict.** Today Mastermind can prove its *process* is trustworthy and cannot prove its
*predictions* are. That is a much better position than the reverse — a firm with a good-looking
equity curve and no process has nothing, while a firm with a good process and a young record has
everything except time. But it must not be described as anything other than what it is, and any
launch claim implying demonstrated predictive edge is, today, unsupported by the repository's own
evidence.

**What must be built so that in six months the answer is indisputable.** Nothing on this list is
exotic; the binding constraint is calendar time, and every day not recording is a day that cannot
be recovered:

1. **Add a benchmark field to the Prophet plan ledger and backfill it** (days) — reusing the
   SPY-and-sector-ETF logic `grade_us_board.py` already implements. Without this, six more
   months of plan accrual still yields no alpha number.
2. **Get every directional engine registering into `qledger`** (weeks). The ledger's value is
   quadratic in adoption and linear in time; the accrual clock only starts when registration does.
3. **Enforce declared-horizon verdicts** (shipped with this document). Prevents the coming
   temptation to declare victory at 5 days on a 63-day signal.
4. **Build the engine registry with an `authority` field** (weeks). Without a unit of account
   there is no scorecard, no CEO view and no Agent OS tier routing.
5. **Seed the Golden Case Library from the existing postmortem corpus** (weeks) — 20 cases.
6. **Let it run.** In six months the June-2026 cohort reaches its 126-day ruler, the arena has
   ~180 nights of challenger accrual, and the placebo comparison has power. **The strongest
   evidence available in six months is evidence that can only be produced by starting to record
   now and not touching it.**

The honest six-month claim is not *"our intelligence is proven."* It is: *"here is a
pre-registered, placebo-controlled, point-in-time-shadowed forward record at declared horizons,
with every disproven idea listed beside it — judge for yourself."* That claim is defensible,
achievable from here, and worth substantially more than a backtest.
