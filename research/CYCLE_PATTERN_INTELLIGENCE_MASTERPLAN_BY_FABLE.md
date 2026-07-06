# Cycle Pattern Intelligence — MASTERPLAN (by Fable)

**Date:** 2026-07-06
**Supersedes/extends:** `research/CYCLE_PATTERN_INTELLIGENCE_FOR_FABLE.md` (Codex report, both drafts — the
`measurement.html`-inclusive draft is canonical; the earlier draft is a strict subset and is fully absorbed here).
**Binds to:** `research/cycle_masterplan/PREREGISTRATION.md` (frozen gates), `FABLE_CORE.md` (doctrine),
`W04_KEYSTONE_VERDICT.md`, `W42_HAZARD_VERDICT.md`, `W46_BINDING_CALIBRATION_VERDICT.md`, `W51_LEADLAG_VERDICT.md`,
Research Factory state machine (`engine/research_factory/state.py`), Signal Bus (`config/synapse.yml`).
**Scope pages:** `measurement.html`, `cycle.html`, `sector_cycles.html`, `country_cycles.html`, `markets.html`,
`sector_central.html`, `sector_central_china.html`.

---

## 0 · Executive ruling

**Build Cycle Pattern Intelligence (CPI), on the Codex skeleton, with one decisive re-weighting: the binding
constraint on cycle-prediction accuracy is not pattern-search machinery — it is information content and sample
accrual.** The Codex report designs an excellent court system (feature lake → candidate registry → trials → truth
artifacts → governed consumers). It under-designs the two things that determine whether the court ever convicts:

1. **New orthogonal evidence.** Every predictive gate run so far on the *price-derived cycle state itself* has
   returned null or near-null: position→return NO-EDGE (KG-1), ladder inversion inconclusive (KG-3), risk-sizing
   0/48 cells (BC-1), lead-lag NO-GO (LL-B), turn-projection precision 0.075–0.230 vs a 0.5 bar (CC-3), directional
   labels negative Brier skill (CC-2). The one live edge — 4/6 hazard cells beating the KM prior — is carried by
   age/oscillator/momentum structure. Mining the same columns harder with fancier machinery will mostly rediscover
   these nulls. A human grandmaster does not call turns from the oscillator; they triangulate breadth, credit,
   liquidity, policy, positioning, and cross-market confirmation. The repo *already holds* most of that data,
   unjoined: breadth to 1962, a FRED vintage store, an Oracle episode archive to 1999, net liquidity, China policy
   rate history. **CPI's discovery program must be, first, a covariate-expansion program** — preregistered trials
   asking "does joining X lift out-of-sample Brier on the turn/risk targets?" — and only second a lattice-mining
   program.

2. **Accrual.** Live forward logs have 2–5 unique dates; the China log has stamped NaN hazard since W4.3 shipped;
   the sync gauge is static; `market_state`, vol-regime, and fear-greed have no PIT history; `build_measurement.py`
   is wired into **no** workflow. Every un-stamped day is training data lost forever. **Phase 0 of this plan is
   accrual hardening, and it ships before any discovery code.**

Ownership as Codex ruled, confirmed: **Cycle-owned; Research Factory owns candidate lifecycle; Neural Web consumes
a compact lobe; Oracle is downstream context-only.** LLMs compress, tag, and adjudicate packets; statistics is the
court; the preregistration ledger stays frozen.

---

## 1 · Verdict on `measurement.html` (the direct question)

**The measurement process is right. It is also incomplete, and it is operationally fragile. Keep it, harden it,
and promote it from courthouse to courthouse-plus-operations-console.**

What it gets right (do not touch):
- Two-cohort discipline (BACKTEST never blends with LIVE), frozen preregistered criteria, BH-FDR within families,
  family-stratified KM baselines, month-block bootstrap, the honest display of falsified promises. This is why we
  can trust the nulls above. The temptation to "fix" measurement because the grades are bad must be refused — the
  grades are the finding.

What is wrong or missing (fix, in priority order):
1. **It is not wired into any nightly lane** (verified: no workflow invokes `scripts/build_measurement.py`).
   Doctrine #10 — a page that requires a human to stay honest will eventually be dishonest. → Phase 0.
2. **It grades old promises but has no view of the learning loop.** No candidate counts, no truth inventory, no
   null library, no coverage/adoption matrix (e.g. hazard probabilities exist in artifacts and forward logs but
   render on zero pages today — an adoption gap the page should indict). → Measurement Hub v2 (Phase 2).
3. **No accrual clock.** "Accruing" cohorts should display *dates*: at the current stamping cadence, when does each
   experiment reach its n-floor / comeback verdict? Converting maturity into a date is what makes waiting a plan
   rather than a hope.
4. **Live-cohort visual authority** must stay subordinated until n_eff ≥ 40 per the house floor (Codex is right).
5. **The embedded gate-ledger fallback should be a real artifact** (`data/cycle_ontology/gate_ledger.json` does not
   exist on disk; the builder silently falls back to a hard-coded list).

Should the measurement be *different*? One genuine methodological addition: the page grades promises the pages
*make*; it should also grade the **system-level nowcast** — a rolling live Brier/coverage ledger per family for
every probability the platform ships (hazard cells, future transition models), with a CUSUM-style decay alarm that
auto-downgrades a truth artifact's status when live skill drifts below its backtest envelope. Decay must be
detected by machinery, not by quarterly vibes.

---

## 2 · Review of the Codex report — adopted / amended / rejected

**Adopted as-is:**
- Feature-lake-first sequencing; no model before the lake (§ Canonical Feature Lake).
- Ownership split (Cycle owns; Research Factory governs lifecycle; NW consumes; Oracle downstream).
- Truth artifacts = permanent memory with revocable authority; nulls are first-class; falsifiers mandatory.
- Anti-mining law (trial budgets, printed candidate counts, null baselines, date-blocked holdouts, era splits,
  sample floors, duplicate collapse, dead-stays-dead).
- Risk/event targets over raw-return targets; "broad forward return from position" stays excluded.
- Measurement Hub v2 section list (Prediction Layer, Pattern Memory, Coverage Matrix, Adoption Gaps, Live
  Maturity, Null Library).
- Basket and China caveats; LLM role limits; page-consumer permission staging.

**Amended:**
- **Discovery engine priority order.** Codex: lattice → motif → supervised → association → LLM digest. Fable:
  **covariate-expansion trials (FT-families, §4) → lattice-with-shrinkage → supervised risk models → motif/analogue
  (display-class) → association rules last.** Reason: the lattice over existing columns re-walks scorched earth;
  new columns move the frontier.
- **Lattice statistics.** Cell-independent scans + BH-FDR will reproduce the BC-1 outcome (0/48 survivors)
  forever. The default estimator for any cell family is **partial pooling** (James-Stein toward the phase/family
  pooled mean, exactly the D5 §2.2 machinery, n_eff on month-blocks) with FDR applied only at **promotion**, not
  at exploration. Weak evidence accumulates in shrunken posteriors; authority still requires the frozen gates.
- **Candidate/truth schema.** Codex proposed a parallel lifecycle. The Research Factory 15-state machine is
  already the law (`proposed → registered → screened → challenged → human_review → paper/… → retired`), with
  `IllegalTransition` enforcement, trial-ledger gates (RF-6), dedup, challenge packets, and a paper monitor.
  **CPI candidates register as domain `cycle_pattern` in the factory; the CPI "promotion ladder" maps onto factory
  states; `truths.jsonl` is a *separate, downstream* artifact layer** — the adjudicated output memory, written only
  from human_review/paper decisions and existing verdict docs, never a competing pipeline.
- **`promoted_null` semantics** live in the truth layer (factory has no durable-null state; `numeric_rejected` /
  `rejected` are candidate outcomes, not memory). A null truth blocks future duplicate candidates via the factory's
  dedup context.
- **Oracle rotation state as context**: Codex said "only where point-in-time" — recon shows it is *reconstructable*
  point-in-time from the episode archive (6,402 episodes, 1999→, onset/confirmed/exhausted dates). Promote from
  "maybe someday" to a Phase-1 context column with `pit_class=reconstructed`.

**Rejected / re-scoped:**
- **"Central fuser disagreement outcome" as a near-term model family** — the central call ledgers have 5 unique
  dates. It stays a *target definition* in the outcomes spine and becomes trainable when the ledger matures
  (accrual clock says when). Building it now is theater.
- **DTW / shapelets in the first analogue release** — nearest-neighbor over standardized episode vectors ships
  first; DTW/shapelets only if NN analogues demonstrate consumption (a display-class feature nobody opens is not
  worth a fancier metric).
- **Hazard columns retro-scored into the monthly backfill in v0** — retro-scoring the fitted model over 2010–2026
  stamps is a *preregistered* exercise (it back-propagates a 2026-fit model into history and must be labeled
  in-sample-contaminated for any pre-2024 row); it is not lake plumbing.

---

## 3 · The system, named honestly

The user's ask — "a system that, like an experienced human, has seen every cycle so often that it recognizes what
comes next" — decomposes into five capabilities, each with a different maturity today:

| capability | today | CPI target |
|---|---|---|
| **C1 Remember** — every episode, every verdict, every null, queryable | scattered in 30 verdict docs + parquets | truth registry + episode library + lake (P1–P2) |
| **C2 Recognize** — "current state resembles these N precedents; here's what followed" | nothing | analogue engine, display-class (P5) |
| **C3 Predict turns** — calibrated P(turn) beating an age prior | hazard model, 4/6 cells, no UI, China live-stamps broken | fix accrual (P0), covariate expansion (P3), UI adoption (P6) |
| **C4 Predict what-comes-next** — next-phase distribution, false-repair risk, path shape | nothing (phase wheel is descriptive) | transition + false-repair models (P4) |
| **C5 Predict the market cycle itself** — index-level turn risk from constituent structure | nothing (markets.html US row is *curated opinion*) | cross-entity aggregates → index hazard trial (P4) |

The grandmaster claim is earned only when C3–C5 carry MEASURED badges with live Brier ledgers, C2 carries honest
n/era caveats, and C1 makes it structurally impossible to re-believe a buried null.

---

## 4 · The information program (the part Codex under-weighted)

Preregistered **feature-trial families (FT-x)**, each = "join covariate family X into the lake, refit the hazard
model (and later the transition model) with X, walk-forward per the frozen W4.2 harness, gate on paired ΔBrier
month-block CI + BH-FDR within family `cycle_pattern_ft` (q=0.10)." Baseline is always the *current shipped
model*, not KM — X must add information to what we already have.

| id | covariate family | source (verified in repo) | pit_class | prior |
|---|---|---|---|---|
| FT-1 | **Breadth structure** — family pct>200d, pct>50d, own-vs-family divergence, breadth thrust | `data/breadth/breadth.parquet` (16,184 rows, 1962→) | pit_pure | W4.2 dropped breadth *for absence*; capitulation/thrust literature; cheapest first trial |
| FT-2 | **Credit & curve** — HY OAS level/Δ/percentile, 10y–3m slope/Δ | FRED market series (quad inputs already pull them) | pit_pure (market-priced) | credit leads equity cycle turns; orthogonal to price momentum |
| FT-3 | **Liquidity** — net-liquidity level/Δ (2013→ full; WALCL-only before), liq_expanding refinement | `data/regime/regime_history.parquet` cols | mixed | liquidity regime dominated 2019–2025 turn timing |
| FT-4 | **Cross-entity cycle structure** — family sync (extend W5.1 gauge), phase-breadth (% members late/downturn), defensive-vs-cyclical RS spread, dispersion | computable from the lake itself | pit_pure | the one W5.1 survivor idea; aggregates pool noise that killed pairwise lead-lag |
| FT-5 | **Rotation context** — Oracle episode density/direction active at t (reconstructed) | `data/oracle/tm_episodes` archive (6,402 eps, 1999→) | reconstructed | institutional rotation intensity near tops/bottoms |
| FT-6 | **China policy stance** — LPR/RRR change recency, easing/tightening state | `data/china_macro/lpr_rate.parquet` + policy events | pit_pure (announcement-dated) | CN sector cycles are policy-dominated (house doctrine) |
| FT-7 | **Vintage-true macro** — re-run FT-gated regime features under ALFRED vintages where covered | `data/fred_vintage/vintages.parquet` (26 series, 1997→) | pit_pure | converts revision_optimistic cells into gradeable ones |

Rules: each FT family is ONE trial-ledger entry with a declared candidate count; features enter the shipped model
only on gate pass; failures are recorded as truth artifacts (`effect_class: null`, scoped to the family). FT-1 and
FT-4 run first (cheapest, purest). The up-3m/up-6m PRIOR cells are the stated bounty: the covariate that unlocks
multi-month peak hazard is worth more than any lattice cell.

**The regime-vintage spine (P-D5-1) is scheduled, not lamented:** market-price-only regime axes are PIT-pure by
construction; the 26-series vintage store covers the macro legs of the business-cycle model; a `regime_v2_pit`
series re-keys the 39 revision-optimistic conditional cells (W4.4) into honest candidates. This is the single
highest-value unlock for everything regime-conditional, and it is a Phase-4 long pole started early.

---

## 5 · Prediction-target doctrine (what this system predicts, and against what bar)

Every target is discrete or bounded, gradeable by Brier/coverage, and carries a *named naive baseline* it must
beat. No target may be "forward absolute return from cycle state alone" (standing null).

| target | definition | baseline | status |
|---|---|---|---|
| Turn hazard (1/3/6m, up/dn) | existing | family-stratified age-only KM | 4/6 PASS — extend via FT trials |
| **Next-phase distribution** | P(phase at t+1m .. t+3m = X) — multinomial over the 5-wheel | unconditional empirical transition matrix per family | NEW (P4) — literally answers "what comes next" |
| **False-repair risk** | P(Repair/Recovery leg fails back below prior trough within 6m) | family base rate by age bucket | NEW (P4) |
| Provisional-turn survival | P(current provisional pivot confirms without lower low) | base rate | NF-provturn gate already registered — revive (P4) |
| Drawdown tail | P(fwd 63d maxDD worse than family p10) conditioned on state cells | phase-pooled shrunken mean | lattice family (P3), shrinkage-first |
| **Index turn hazard** | market-level (SPY/country index) turn hazard with constituent-structure covariates (FT-4) | index's own age-only KM | NEW (P4) — the C5 capability; markets.html US finally engine-backed |
| Phase persistence | P(current phase survives 3m) | per-family phase duration prior | lattice family (P3) |
| Cone miss | P(realized turn outside recalibrated cone) | nominal | after CC-1 recal accrues |

Central-call grading targets activate automatically when ledgers hit n_eff ≥ 40 (accrual clock displays the date).

---

## 6 · Architecture (final)

```
data/cycle_pattern/
  entities.parquet            # stable id map, family/tier/pit flags        [P1 ✅ built]
  state_monthly.parquet       # unified PIT monthly panel (12,519 rows v0)  [P1 ✅ built]
  state_monthly_meta.json     # column-level pit_class metadata             [P1 ✅ built]
  state_daily_live.parquet    # nightly union of forward logs (adapter)     [P2]
  context_monthly.parquet     # FT covariate families, column-tagged        [P3]
  outcomes.parquet            # fwd ret/excess/DD/turn/phase-change spine   [P1 ✅ built]
  episodes.parquet            # one row per confirmed leg + context + tags  [P5]
  truths.jsonl                # market-truth memory (append-only versions)  [P1 ✅ seeded ×15]
  reviews.jsonl               # decay/kill review log                       [P2]
config/cycle_pattern/
  candidate_grammar.yml       # lattice dimensions × targets × budgets      [P2]
  consumer_matrix.yml         # allowed/forbidden consumers per class       [P2]
data/neuralweb/cycle_pattern_state.json                                     [P6]
```

Governance wiring (all verified against current code):
- Factory: add `cycle_pattern` to `DOMAINS`; `adapter_cycle_pattern.py::route_all()`; declare `rf.cycle_pattern.*`
  in `data/trial_ledger.jsonl` **before** first screened candidate (RF-6 hard gate); candidate types map to
  factory schema; falsifier grading gets a cycle-path in the paper monitor.
- Signal Bus: register every artifact in `config/synapse.yml` (owner_program `cycle-intelligence`, tier `display`
  /`infrastructure`), regenerate `docs/SIGNAL_BUS.md`, bump the count pin in `tests/test_signal_bus_doc.py`.
- Enforcement: `scripts/check_cycle_pattern_authority.py` (modeled on the research-factory authority gate) — greps
  for reads of `data/cycle_pattern/` outside the allowed-consumer list; forbidden consumers (board rank, oracle
  escalation, central direction score, position sizing) become a CI failure, not a doc sentence.
- NW lobe: `_compose_cycle_pattern()` in `world_state.py`, `LOBE_SUMMARIZERS['cycle_pattern']` in
  `mastermind_context.py`, `read_cycle_pattern_state` in cortex/ask-brain read tools, envelope-stamped.
- Ops: every builder in `config/dag.yml` + daily/render lanes; heavy fits in the monthly `cycle-calibration.yml`
  lane; ledgers nightly-only.

---

## 7 · The phased program

Each phase = 1–3 same-day PR waves per house rules; executable acceptance on every wave. Tier tags: (O)pus
judgment / (S)onnet implementation / (H)aiku collection.

### P0 — Accrual & honesty hardening  *(built 2026-07-06, this branch)*
- China forward-log hazard investigation: the all-NaN rows are honest pre-W4.3 history (keep-FIRST), but the
  investigation surfaced a real latent defect — `_stamp_hazard`'s else-branch read `proj.period_yrs.median`
  (a FULL-cycle estimate) as a HALF-cycle duration, biasing `log_age_ratio` by −log 2 for **all** US sector/basket
  and China records. Fixed (÷2) + 3 regression tests; fresh stamps produce finite calibrated probabilities (S).
- Wire `build_measurement.py` into daily + render lanes + dag conformance (S).
- `archive_context_snapshots.py`: nightly append-only PIT archive of regime/market_state/vol/fear-greed snapshots
  → `data/signal_archive/context_daily.parquet` (the P-D5-3 fix, forward) (S).
- `append_sync_gauge.py`: sync gauge goes nightly-appending instead of static (S).
- **Acceptance:** next nightly stamps CN hazard non-null; `check_dag_conformance` green; context archive grows by
  one row/day; measurement.html rebuilt nightly.

### P1 — Substrate  *(built 2026-07-06, this branch)*
- `entities.parquet` (~180 entities, basket/amalgam `pit_membership=False` flagged), `state_monthly.parquet`
  (12,519 rows = 1,881 US + 5,738 country + 4,900 CN; hazard-panel features joined; zero outcome columns;
  column-level pit_class sidecar), `outcomes.parquet` (fwd/excess/DD/turn-event spine, grader-convention anchors,
  keystone cross-check) (O).
- Truth registry v0: schema + append-only versioned transitions + **15 seed truths** encoding every adjudicated
  verdict (the system boots knowing what not to believe) (S).
- **Acceptance:** one query returns all engine-backed states for any month; outcomes reproduce keystone rows where
  they overlap; seeds validate with real evidence paths; deterministic rebuild.

### P2 — Governance machinery + Measurement Hub v2 completion
*(Hub v2 v0 shipped 2026-07-06 with P1: Pattern Memory truth ledger, Null Library, Live Maturity & accrual clocks
are live on measurement.html, schema `measurement.v2`. Remaining below.)*
- Factory domain adapter + trial-family declaration + candidate grammar + consumer matrix + authority check gate (S).
- `state_daily_live` adapter over forward logs (S).
- Hub v2 completion: Prediction Layer section (hazard cells + model freshness + **adoption gaps**) and the
  cross-page Coverage Matrix (S).
- **Acceptance:** a synthetic candidate walks proposed→registered→screened only with a declared budget; measurement
  answers "what has Cycle learned and where may it act"; authority gate fails CI on a seeded forbidden read.

### P3 — First discovery batch (two-commit discipline: prereg, then run)
- FT-1 breadth + FT-4 cross-entity structure into the hazard harness; new FDR family `cycle_pattern_ft` (O).
- Lattice v0 with shrinkage-first estimator on risk/event targets (drawdown tail, phase persistence, false-turn),
  budgeted via `candidate_grammar.yml` (O).
- **Acceptance:** rediscovers KG-1 null and the hazard pass/prior split from the lake (harness sanity); ≥1 truth
  artifact written per outcome *including nulls*; candidate counts printed pre-evaluation.

### P4 — Prediction expansion
- Next-phase transition model vs empirical-matrix baseline; false-repair classifier; NF-provturn revival (O).
- **Index turn hazard** from constituent aggregates (C5; engine-backs the markets.html US row) (O).
- Regime-v2 PIT spine (market-price axes + vintage-fed legs); re-key W4.4 cells (S/O).
- FT-2/3/5/6/7 as budget allows (S).
- **Acceptance:** every model carries the frozen gate format (ΔBrier CI + BH within its family + era split); PRIOR
  ships where gates fail, badged.

### P5 — Memory & analogue layer
- `episodes.parquet` (one row per confirmed leg: state at open/mid/close, context, outcome, confirm lag);
  narrative/DNA → frozen tag taxonomy via LLM normalization (versioned vocab, spot-audited, tags are display
  metadata not features until separately gated) (S/H).
- NN analogue retrieval + episode cards: "8 precedents, 5 resolved up, era split, evidence class DISPLAY" (S).
- **Acceptance:** every analogue card shows n/dates/era stability/caveats; no analogue output can touch a score.

### P6 — Lobe & page consumers
- `cycle_pattern_state.json` + NW lobe + cortex read tool + spine-index adapter (S).
- Pages: sector_cycles Pattern-Memory drawer; central truth badges + Truth-Guard reasoning lines; markets
  cross-market sync/late-cluster view; cycle.html truth module; measurement stays the console (S).
- **Acceptance:** every visible claim carries evidence class; forbidden-consumer CI gate covers all new readers;
  progressive disclosure (base pages stay readable).

### Continuous loop (the actual "self-learning")
Monthly: lake append + regrade + discovery batch within standing budget. Quarterly: refits, decay review
(auto-demotion on envelope breach), comeback-date adjudications. Annually: era re-split, taxonomy version review.
The loop's clock lives in dag.yml, not in anyone's memory.

### Deferred (explicitly, with reasons)
- **Single-equity cycles** — sample explosion + noise; revisit only after sector-level C3/C4 hold live for 2+
  quarters. The Terminal's per-stock confluence stack is a different organism.
- **DTW/shapelet analogues** — after NN proves consumed.
- **Central-fuser disagreement models** — when call ledgers mature (clock will say).
- **Any LLM-originated score** — never; constitutional.

---

## 8 · Preregistration amendments required (append-only, before P3 runs)

1. New FDR family `cycle_pattern_ft` (q=0.10) — FT-1..FT-7, one entry per family, candidate counts declared.
2. New FDR family `cycle_pattern_lattice` (q=0.10) — budgeted per `candidate_grammar.yml`; shrinkage exploration
   exempt from FDR, **promotion** subject to it (this distinction written into the ledger text).
3. New gates: TR-1 (next-phase model beats empirical transition matrix, OOS multiclass Brier, CI excludes 0),
   FR-1 (false-repair classifier AUC ≥ 0.60 + calibrated-Brier beats base with CI), IX-1 (index hazard beats index
   KM), each with era-split and embargo [2024-01-01, end] honored.
4. Truth-layer law: a `promoted_null` truth may be reopened only by a new preregistered trial naming the null it
   challenges (dead stays dead otherwise).

---

## 9 · What Fable asks the operator to decide

1. **Ratify the re-weighting**: information program (FT trials) outranks lattice mining in P3 sequencing.
2. **Ratify factory ownership** of CPI candidate lifecycle (no parallel ladder) with truths.jsonl as the separate
   downstream memory layer.
3. **Approve the P0 accrual fixes deploying immediately** (they change nightly behavior: CN hazard stamping,
   measurement in the render lanes, two new nightly appenders).
4. **Approve starting the regime-v2 PIT spine** in P4 (it is the long pole; every week of delay keeps 39
   conditional cells revision-optimistic).
5. Confirm single-equity cycles stay deferred.

---

## 10 · Bottom line

The Codex report correctly refuses the seductive version of this project — "let AI read all the charts" — and
builds a court instead. This masterplan keeps the court and adds what a court cannot supply: **new evidence and
a docket that never stops filling.** Harden the stamping so every day compounds; unify the substrate; seed the
memory with every null already paid for; then spend the discovery budget where the priors are best — breadth,
credit, liquidity, cross-entity structure, policy — under the same frozen gates that made the existing nulls
trustworthy. The system becomes the experienced investor the user described not by pattern-matching harder, but
by remembering everything, watching more of the market than any page currently does, and being forced by
machinery to say "I don't know yet" with a date attached.
