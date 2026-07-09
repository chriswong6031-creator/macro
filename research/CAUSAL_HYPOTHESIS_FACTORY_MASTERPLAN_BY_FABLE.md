# Causal Hypothesis Factory — adjudicated masterplan (CHF-R1..R17)

Status: ADJUDICATED — W0 ruling document, red-teamed (3-lens Opus panel, findings
recorded in §8; every blocker and major accepted and incorporated). Build waves
W1–W6 chartered below.
Author: Fable (main-loop adjudication), 2026-07-09.
Source intake: `research/CAUSAL_DISCOVERY_NEURAL_WEB_PRODUCTION_PLAN.md` (Codex handoff,
2026-07-09, adapted from an X article by `@RitOnchain` on causal discovery for factor
research; Harvey/Liu/Zhu factor-zoo + Lopez de Prado causality-and-factor-investing lineage).
Census basis: 8-lane repo census 2026-07-09 (metabolism, research factory, data substrate,
pipeline mechanics, R-ORTH/confluence, UI, doctrine, Oracle/Signal-Lab consumption).

---

## 0. Verdict on the Codex plan

ADOPT the direction, ADOPT most of the architecture, AMEND the placement and the
registration path, and UPGRADE the loop so it closes without an operator hypothesizing
— behind an explicit, operator-flipped autonomy gate (CHF-R8/CHF-R17).

What Codex got right (retained verbatim in spirit):

- Epistemic organ, not an alpha lobe. It produces candidate experiments, audits,
  and nulls — never buys, never escalates.
- LLM roles limited to propose / critique / compile / explain. Code grades.
- Ensemble skepticism: an edge is a candidate explanation, not a signal;
  `causal_support` + `causal_concerns` + `test_plan`, never "causal truth".
- Null library as a first-class output. Invariance across declared environments
  as the main financial reality check.
- Reuse of the existing hypothesis metabolism rather than a parallel promotion path.

What the census and the red-team forced us to change:

| Codex proposal | Repo fact | CHF ruling |
|---|---|---|
| "First-class Neural Web lobe" | Two-lobe cap FULLY CONSUMED (NWC-U2); docket taxonomy makes anything with own objective + own FDR family + own falsifiers a LOBE | CHF is a **PROGRAM** (Research-Factory / NW-Context-Intelligence mold), not a lobe and not a "rail" (CHF-R1) |
| New machine registration family + `registered_by: causal_lobe` through metabolism | metabolism hard-wires the cortex family; QS-U2 sole-chokepoint; RF-16 bans budget games | v1 uses the **three-exit pattern** (R-CI6 shape) for deterministic candidates; LLM cards ride the cortex's already-adjudicated proposal lane (CHF-R2) |
| Build stop-out/MAE targets | `replay_boarded.parquet` already has `state_8_21`/`state_15_126` (STOPPED = stop-out), `fwd_mdd_{h}`, `fwd_mfe_{h}` — but it is a gitignored runner-local store | reuse with env-override resolution + honest data-absent degradation (CHF-R6); no new fire ledger (RUL-ORTH-4) |
| Write a Granger scout from scratch | `engine/cross_asset.py` has HAC + BH primitives — but they are single-series / market-index tools with NO cross-sectional control | reuse for index frames only; ticker panels get within-period cross-ticker permutation + date fixed-effects by law (CHF-R5) |
| Confluence-independence auditor | R-ORTH covariance spine owns undirected independence (RUL-ORTH-1..12) | CHF adds only the **directed** annotations; zero recomputation (CHF-R10) |
| Weekly full-DAG refresh | graph churn risk; render budget law; Mac Studio RAM incidents | split cadence: nightly drift-only, weekly bounded battery, quarterly review; no full-graph learner in v1 (CHF-R8/R11/R14) |
| Operator pastes packs to an LLM | the only automated LLM lane is the cortex job (`engine/llm_auth.py` waterfall), currently ops-dead on a corrupted token; no automated brainstorm loop exists anywhere | weekly runner is NET-NEW machinery built on the cortex/llm_auth pattern, default operator-triggered, auto-loop behind a Phase-A gate + service-key identity (CHF-R8, §6 ops) |

The one-line charter:

```text
CHF is the Neural Web's idea immune system: a deterministic causal-edge scout,
an LLM mechanism-card factory behind a schema firewall, a null/frontier memory,
and an anti-mirage auditor — all display-tier, feeding the existing metabolism,
factory, and domain gauntlets. It never originates authority. It makes everyone
else's experiments better-chosen and cheaper.
```

Why causal-first beats mine-and-test: every hypothesis arrives with a mechanism,
declared confounders, a pre-registered environment map where it should and should
NOT work, and falsifiers — so the expensive post-registration slots (3/week
metabolism, domain gauntlet shots) are spent on candidates with priors, and kills
are classified correctly at birth (mechanism-false vs construct-unidentifiable vs
estimator-broken, per the measurement-lens reassessment law).

---

## 1. Rulings

**CHF-R1 (taxonomy — PROGRAM, not lobe, not rail).** CHF is chartered as a Neural
Web epistemic PROGRAM in the mold of the Research Factory and NW Context
Intelligence — both of which own scanners and FDR families without lobe charters.
It is NOT chartered as a lobe (no attention earn-in, no board/brief salience of its
own, no domain signals — NW-U15 scope fence) and it does NOT claim the RAIL label:
under the Future Lobes Docket taxonomy, CHF's own objective + own FDR family + own
falsifier vocabulary are lobe traits, so calling it a rail would be a cap dodge a
future adjudicator should strike. The NWC-U2 two-lobe cap is not consumed and not
evaded: the cap governs NW organ charters with authority ambitions; CHF's NW-side
organs are infrastructure artifacts + display copies at authority ceiling A1
EXPLAIN (precedent: RUL-ORTH-1's A1_EXPLAIN ceiling), `scored_path_surfaces: []`,
`horizon_role: context`, all authority booleans False, A7 refused unconditionally.
If CHF ever seeks attention-raising or authority above A1, that is a NEW,
cap-subject charter question and requires a fresh Fable/operator ruling.

**CHF-R2 (candidate exits — reuse adjudicated lanes only).** Two candidate streams,
each riding an existing legal lane:
1. **Deterministic scout candidates** (edges from registered screen batteries —
   no LLM anywhere in their production) follow the context-scanner three-exit
   shape (R-CI6): (a) the cortex may stake a candidate through
   `metabolism.register_hypothesis()` (cortex family, 3/week budget intact,
   QS-U2 preserved) after reading the candidate queue through a read-only tool;
   (b) Fable/operator charters a pre-registered domain study routed to the OWNING
   program's harness and frozen ruler (Oracle grammar for rotation, entry-intel
   P-runs for entry quality, signal-lab for families); (c) decay to the null
   library (dead-stays-dead: decayed candidates remain in the dedup corpus).
2. **LLM mechanism cards** are drafts for the SAME already-adjudicated proposal
   lane the cortex uses today (NW-U11: "the cortex proposes FROM history";
   `a6_llm_proposed` governance events; server-side registration). Cards are
   inert proposal material until a human or the cortex's own staking chokepoint
   acts (CHF-R17). CHF itself NEVER writes `machine_registry.jsonl`, never calls
   `register_hypothesis`, never touches the 3/week budget.
Factory tracking of skeptic-passed cards uses `source='external_report'` +
`candidate_type='external_idea'` through the deterministic factory ingest script
(RF-13) — `external_idea` is a candidate_type, not a source, and no new enum
values are minted without an RF amendment in the same PR that needs them. A
dedicated CHF machine-registration family is DEFERRED to the Phase-2 come-back
(§7) and requires ≥8 matured causal candidates through exits (a)/(b) plus a fresh
Fable ruling.

**CHF-R3 (multiplicity accounting — cumulative, launder-proof).** The scout's
statistics form the new FDR family `causal_scan` (registered in
`config/ruling_graph.yml` `meta.known_fdr_families` in THIS PR so no later doc or
code PR trips the H1 conflict guard). Accounting law, superseding any per-family
max() reading of RUL-U3a for this program:
- every edge×lag×environment cell evaluated by any battery is logged as a
  DISTINCT TrialLedger config, so the family's literal_n ACCUMULATES across all
  batches — many small batches can never launder into one under-counted search;
- the cumulative family literal_n is printed on every lab-state surface and on
  every edge record (`search_width_at_scan` — Oracle promotion-scan pattern);
- any edge exiting to a promotion path (exit (a)/(b)) carries the full cumulative
  family width into that path's discipline; the RUL-U3a descriptive-only
  tolerance explicitly does NOT extend to exited edges;
- BH runs once per batch per family; DSR calls (if any) use the `ledger=` kwarg
  only — the literal `n_trials` kwarg stays forbidden per the trial-budgets CI law;
- a test asserts the family's effective width ≥ its cumulative logged cells.

**CHF-R4 (causal constitution).** Structural priors are a committed, CI-validated
config `config/causal_priors.yml`, not code-buried assumptions:
- tier ordering (edges may only point down or across cadence tiers:
  macro_plumbing → asset_class → sector/complex → stock → fire_outcome);
- per-feature minimum lags derived from cadence + publication latency
  (no same-day edges from weekly-published sources — H.4.1 pattern);
- forbidden causes: downstream composites (`board_rank`, `final_verdict`,
  `top_setups`, any Article-2 surface), forward-outcome echoes
  (`outcome_excess`, `fwd_*`, `terminal_state_*` — encoder-exclusion law),
  kernel estimates (NW-U16/R-CI8 fence until the 2026-10-01 batch),
  positioning keys barred by the positioning-fusion ruling;
- a **kill mask** in two sections: (i) CURATED — hand-appended rows mirroring
  `research/DO_NOT_REBUILD.md` per adjudication (the registry itself stays
  curated per its standing no-extractor ruling); (ii) COMPILED — regenerated on
  every nightly inventory build from `causal_nulls.jsonl`, with a CI sync test
  (SIGNAL_BUS doc-gate pattern) asserting the committed compiled section matches
  regeneration, so newly-killed edges cannot silently become proposable again.
The scout hard-refuses any edge the mask forbids and prints the refusal.

**CHF-R5 (estimator law — by construction).** Battery elements per published edge:
- declared-lag effect estimate with inference matched to the TARGET TYPE:
  - **ticker-panel targets** (entry quality, per-name outcomes): collapse to
    per-date cross-sections with within-date demeaning / date fixed-effects
    BEFORE any time-series inference, and use within-period CROSS-TICKER
    permutation as the null for level-threshold causes; effective N is reported
    in calendar periods, never fire counts (ticker-cluster time-confound law);
  - **market/macro-series targets**: Newey-West HAC on the time dimension
    (reusing `engine/cross_asset.py` primitives, which are single-series /
    market-index tools and may NOT be applied verbatim to ticker panels);
- **negative-lag placebo** (target leading cause ⇒ suspicious);
- **time-shift placebo** (DT-R14 time-preserving null law) for event/change causes;
- circular block bootstrap on TIME blocks (never ticker clusters), ≥200 draws,
  with within-window null percentiles printed (RUL-ORTH-8 extended);
- overlap correction for overlapping-horizon outcomes, specified as one of:
  non-overlapping subsampling, or explicit overlap variance inflation
  (Hansen-Hodrick/NW with lag ≥ horizon) — a plain HAC-on-mean under-correction
  is a protocol violation;
- **era split** (DT-R16: the 2010 break plus feature-availability eras). When the
  target's verdict-grade span does not straddle the required break, the leg
  returns the honest verdict `insufficient_era_span` — never a within-regime
  split dressed as an era test;
- **environment invariance** ONLY over splits pre-registered per card/edge at
  mint time (CHF-R7); any additional split computed is charged to the
  `causal_scan` ledger and printed as splits_tested vs splits_declared.
Edge verdict vocabulary: `screened_candidate | era_specific | unstable |
insufficient_era_span | insufficient_power | null | forbidden`. Support fields are
`causal_support: {weak|medium|strong}` per lens with `causal_concerns[]`; output
NEVER claims causality (RUL-CC-5 language law: the banned words are enforced by a
sanitizer at write time on all generated text).

**CHF-R6 (targets v1 — reuse, don't rebuild; honest about eras and stores).**
1. **regime/risk transmission** (the CI-safe v1 anchor) — regime transitions and
   risk escalations from `data/regime/regime_history.parquet` (1971→) and spine
   engine-family outcome aggregates via the existing `engine/neuralweb/query`
   API (no new fire ledger). Substrate is git-tracked; runs anywhere.
2. **entry_quality** — `data/replay/replay_boarded.parquet`: `good_21d`
   (state_8_21 ∈ {CUSHIONED, CLEAN_LIFTOFF}), STOPPED rate, `fwd_mdd_21`,
   `fwd_ret_21/63` on the verdict-grade subset (49,939 of 57,640 fires).
   Constraints, all binding: the store is GITIGNORED and runner-local
   (untracked-store law) — the causal job resolves it via a `REPLAY_BOARDED_PATH`
   env override pointing at the runner-local store (THETADATA_STORE pattern) and
   prints an honest `data_absent` null when unresolved; the EFFECTIVE
   verdict-grade window is ≈2022-06-30 → present (P0 memo §6 v1.1 — the nominal
   2021-07-06 window does not exist in the ledger), so every entry_quality edge
   is auto-stamped `era_specific`/RECENT_ONLY by construction and the era-split
   leg returns `insufficient_era_span`; `insufficient_power` is an expected,
   first-class terminal verdict here (P0 memo §2.4.6).
Rotation-episode and de-escalation target panels are W5+ follow-ups (they need an
episodes→outcome join builder adjudicated with the Oracle constitution's owner).
Candidate-cause panel v1: `regime_v2_pit` columns (1971→), `breadth.parquet`
(1962→, survivorship caveat pre-2002 printed), `data/macro/fed_net_liquidity.parquet`
(2002→), liquidity-quality labels (`data/regime/latest.json` lineage), GEX history
(2017→, era-flagged), credit/rates/FX context series already on the bus. 2021+-only
columns (options entry state, cohesion family) are admitted but auto-stamped
`era_specific`-only (Oracle RECENT_ONLY pattern).

**CHF-R7 (mechanism cards).** New artifact `data/neuralweb/causal_mechanisms.jsonl`
(schema `neuralweb.causal_mechanism_card.v1`). A card = mechanism story (EN/ZH
display strings), causal graph fragment (cause/target/mediators/confounders/
colliders-to-avoid), **frozen environment map** (should-hold / should-break split
set, hashed at mint time BEFORE any invariance test runs — a card whose invariance
verdict rests on splits outside its frozen map is a protocol violation),
falsifiers (≥2 mandatory), test spec (metabolism claim_shape where the exit is
(a); domain-harness spec where the exit is (b)), lineage, and status. Authority
block copied verbatim from the MPC pattern (`may_rank/gate/size/escalate: false`,
`not_a_signal: true`, forbidden_uses list). Card verdicts use the trichotomy of
the measurement-lens law: `supported_in_env | mechanism_refuted |
construct_unidentifiable | estimator_broken | accruing | insufficient_n`.
ETM cross-links: ONLY cards holding a metabolism-issued id (exit a) or a
registered domain-study id (exit b) mint `mechanism:` ETM IDs from that spec_ref
(ETM-R2/R4 identity law); inbox and decayed cards stay out of ETM entirely.

**CHF-R8 (the loop — autonomous machinery, gated autonomy).** Cadences:
- **Nightly (causal job, off the render path): drift monitoring only.** Refresh
  feature inventory stamps; refresh target panels; cheap drift checks on
  already-published candidates; refresh frontier ledger, surprise queue, lab
  state + site copy. Deterministic, no LLM, no bootstrap batteries.
- **Weekly (same job, weekday-gated): the bounded battery + brainstorm.**
  Full CHF-R5 batteries over the frontier's top-K cells (K ≤ 40 edge-cells/week,
  printed); then the brainstorm step. The prompt pack is REBUILT FRESH every run
  (never persisted-pack reuse) from: feature inventory, current edges, frontier
  cells, surprise tickets, null library, registered hypotheses, and the kill
  mask. The LLM chain (generator → skeptic → compiler → deduper; skeptic output
  categorical only, no numeric confidence — RF-7 pattern) runs ONLY when
  (i) an operator triggers it (workflow_dispatch / manual invocation), or
  (ii) `config/causal_llm.yml` has `auto_loop: true` — which ships FALSE and may
  be flipped only by the operator after Phase-A (below). Scheduled auto-loop
  runs use SERVICE-KEY identity (`ANTHROPIC_API_KEY` repo secret), never
  user-OAuth, per the W-AUTO line in the Research Factory charter. Without
  auth or with `auto_loop: false` and no trigger, the step degrades to
  pack-generation-only (operator-paste mode — the pack pattern is Oracle's;
  the AUTOMATION precedent is the cortex job, and this runner is net-new
  machinery, not a copy of an existing loop). Card filing into the inbox is
  idempotent per ISO week (a filing-budget row mirroring the
  `--defer-on-budget` pattern), so a mid-week token fix can never double-file.
- **Quarterly:** FDR/null review over matured causal-tagged hypotheses,
  null-basin retirement into the kill mask, frontier re-scoring, and a
  come-back packet on the evidence clock.
**Phase-A gate (autonomy earn-in):** ≥1 full operator-triggered cycle with ≥5
schema-valid cards filed, ≥1 candidate through exit (a) or (b), and zero guard
violations → the operator may flip `auto_loop: true` in a one-line PR. This
masterplan is the risk-acceptance ruling that the flip requires nothing further.
Agenda-setting is machine-owned regardless of the LLM gate: the **frontier
ledger** (coverage map over cause-family × target-family × environment cells with
states unexplored/accruing/screened/null_basin/killed and a printed deterministic
value heuristic) and the **surprise queue** (unexplained-variance tickets from MPC
`no_attributable_driver` nulls, MRI release-forecast misses, and Oracle episode
failures — each ticket stamped with its source artifact's asof and marked stale
when the source is; `winner_episodes` lineage is on-demand and treated as such)
decide what gets tested and brainstormed next. The operator ratifies promotions;
the operator does not have to hypothesize.

**CHF-R9 (natural-experiment instrument library — classed, not vibes).**
`config/causal_instruments.yml` registers event tapes with a MANDATORY
`exogeneity_class` schema field, CI-validated:
- `timing_only` — the scheduled CALENDAR is exogenous (OPEX dates, pre-announced
  FOMC meeting dates, scheduled release timestamps, index-rebalance dates);
  usable as event-window clocks;
- `surprise_component` — the realization is usable ONLY with a mandatory
  anticipated-vs-surprise decomposition (futures-implied or consensus-survey
  surprise) — CPI/NFP prints, FOMC decisions;
- `endogenous_reaction` — policy reaction functions (China RRR/LPR); admissible
  only as conditioning context with a printed reaction-function confound note,
  never as an identification lens.
Every entry carries a `required_confounds` list; the scout refuses to run an
instrument whose class requirements are unmet. Event studies obey the same
placebo/era law (CHF-R5).

**CHF-R10 (anti-mirage auditor — compose with R-ORTH).** The auditor emits
`data/neuralweb/causal_confluence_audit.json` with DIRECTED annotations only:
`duplicate_exposure` (price-derived siblings sharing a parent process, from
inventory role tags), `shared_parent_suspect` (co-firing concentrated in one
environment/driver state), `collider_risk` (conditioning-on-downstream warnings
for named composites). The confluence builder consumes it to tag `confirms`
edges; committee/admin display extends the existing independence block. Hard
limits: no recomputation of R-ORTH statistics (RUL-ORTH-9), spine remains the
sole fire substrate (RUL-ORTH-4), annotations are deterministic rules
(RUL-ORTH-11 — the LLM may explain them, never originate them), display-only
until replay evidence earns more (RUL-ORTH-5 analog).

**CHF-R11 (pipeline placement — costed and enumerated).** CHF runs as its own
`causal` job in daily.yml (`needs: engine`, `if: always()`, `timeout-minutes: 45`,
runs-on [self-hosted, macstudio]) with the narrow commit block pre-written:

```bash
git add data/neuralweb/causal_feature_inventory.json
git add data/neuralweb/causal_edges.jsonl data/neuralweb/causal_nulls.jsonl
git add data/neuralweb/causal_mechanisms.jsonl
git add data/neuralweb/causal_frontier.json data/neuralweb/causal_surprise_queue.jsonl
git add data/neuralweb/causal_confluence_audit.json
git add data/neuralweb/causal_lab_state.json site/neuralwebdata/causal_lab_state.json
git add data/trial_ledger.jsonl
```

None of these paths collide with the cortex job's adds (asserted at W3 review,
not assumed). The job never writes asia-owned paths, never touches Article-2
surfaces, never reads kernel cells (until the fence lifts), and keeps the engine
job's render budget untouched. Nightly work is drift-only (cheap); the ≥200-draw
batteries are weekly and bounded (CHF-R8) so the 45m timeout holds on the shared
Mac Studio (RAM-frugal by design: macro panels are small; the ticker-panel path
loads only the needed columns). All steps registered in `config/dag.yml`
(dag-conformance is a hard gate). `data/trial_ledger.jsonl` is also written by
the cortex job — the causal job runs its ledger append AFTER a fresh pull and
keeps the append idempotent (keep-first), mirroring existing multi-writer
discipline.

**CHF-R12 (synthetic gauntlet before live edges).** The scout may not publish a
live edge until the hermetic synthetic suite passes in CI. Minimum planted set:
- planted-DAG recovery under autocorrelation + nonstationarity + hidden confounder;
- planted mirages that must be REJECTED: collider conditioning, sibling
  duplication (two children of one parent read as confirmation), reverse
  causation (negative-lag placebo must fire), lagged-echo (time-shift placebo
  must fire), **cross-sectional dependence mirage** (co-firing tickers sharing
  one date factor must not inflate N), and **regime-persistence mirage** (an
  "invariance" split that is really one slow state must not pass invariance).
We test the ruler before it measures the market.

**CHF-R13 (operator surface).** Admin "Causal Lab" card (panel module + route +
RENDER entry, Context-Lobe pattern): heartbeat, frontier map summary, newest
candidate edges with concerns, surprise queue, null count, cumulative
`causal_scan` width, LLM-lane status (ok / degraded / awaiting-Phase-A), and the
three-exit funnel counts. Committee page: CHF engine node rides the existing
graph builder into the `meta` lobe in v1 (no template anchor churn);
measurement-hub rows appear only when the first matured verdicts exist
(BACKTEST/LIVE never blended, Ruling A6). All copy bilingual; no CJK in `title=`;
`theme.js` law respected. The word "validated" never appears. CHF display
artifacts are intentionally NOT registered in the external contract manifest
(no external bot/terminal consumer) — do not add them and re-arm the drift gate.

**CHF-R14 (kills and deferrals registered now).**
- Full-graph learners (NOTEARS/DAG-GNN/LoRAM/CMIN-style) in v1: KILLED for v1;
  small-universe NOTEARS-with-priors is a Phase-3 candidate behind the §7 clock,
  admissible only after the scout + null library have operated for a quarter.
- Causal-DAG → portfolio construction: FORBIDDEN (Codex concurs; Article 1/2).
- Weekly full-DAG re-estimation: REJECTED (churn); drift monitors are nightly,
  structure re-estimation is quarterly at most.
- LLM numeric confidence anywhere in CHF: FORBIDDEN (RF-16 extension).
- New fire/outcome ledger: FORBIDDEN (RUL-ORTH-4).
- These rows are appended to `research/DO_NOT_REBUILD.md` in this PR.

**CHF-R15 (evidence clocks).** Registry-seed entries (RF-9: no bespoke timers):
first-edge-batch review clock (~35d after W3 lands), Phase-2 dedicated-family
come-back (2026-10-15, conditional on ≥8 matured exit-(a)/(b) candidates), and
the Phase-3 structure-learner come-back (2027-01-15). Grace 7d.

**CHF-R16 (truth-in-labeling).** Every CHF surface states its epistemic status
inline: "causal-candidate — screened, not gauntleted", concerns list, environment
map, and which consumer (if any) is allowed to act on it (v1 answer: none). The
gauntlet remains a PROMOTION gate, not a build gate: nulls never block accrual,
and a standalone-null edge is retained as confluence context, not deleted.

**CHF-R17 (LLM actor law).** LLM-generated mechanism cards are inert proposal
material with ZERO authority until a human (operator/Fable) or the cortex's own
server-budgeted staking chokepoint acts on them — mirroring RF-7's advisory-only
+ human-authored-transition law and the cortex's adjudicated proposal lane
(NW-U11, `a6_llm_proposed`). No card status may transition to any
registered/queued/chartered state via an LLM actor; transitions are script or
human actors only (RF-5 actor-allowlist analog), and a CI-tested validator
enforces it. The LLM chain never selects exits, never ranks the frontier, never
edits the kill mask, never touches calibrated keys except to de-escalate.

---

## 2. Architecture (what gets built where)

```text
config/causal_priors.yml            CHF-R4 constitution (tiers, lags, forbidden, kill mask)
config/causal_instruments.yml       CHF-R9 instrument library (exogeneity_class schema)
config/causal_llm.yml               CHF-R8 autonomy gate (auto_loop: false at birth)
engine/neuralweb/causal_inventory.py    feature inventory builder (roles, eras, pit_basis, lags)
engine/neuralweb/causal_discovery.py    edge scout: battery per CHF-R5, target panels per CHF-R6
engine/neuralweb/causal_schema.py       mechanism-card schema + validators + language sanitizer
engine/neuralweb/causal_frontier.py     frontier ledger + surprise queue + lab state assembly
engine/neuralweb/causal_audit.py        anti-mirage annotations (CHF-R10)
scripts/build_causal_inventory.py       nightly step
scripts/build_causal_edges.py           weekly scout batch (TrialLedger per-cell logging)
scripts/build_causal_frontier.py        nightly frontier + surprise + lab state + site copy
scripts/causal_brainstorm_pack.py       pack generator (stdout; generated, never hand-kept)
scripts/run_causal_brainstorm.py        LLM chain w/ operator trigger + auto_loop gate + degradation
scripts/causal_ingest_brainstorm.py     schema firewall + dedup + skeptic routing + ISO-week filing lock
scripts/build_causal_confluence_audit.py  auditor step
admin/causal_lab.py + route + RENDER    operator card
tests/test_causal_*.py                  incl. the CHF-R12 synthetic gauntlet + CHF-R17 actor law
```

Artifacts (synapse-registered; count-pin bumps handled per §4 discipline):

| artifact | path | tier | notes |
|---|---|---|---|
| causal-feature-inventory | `data/neuralweb/causal_feature_inventory.json` | infrastructure | roles/eras/lags/forbidden |
| causal-edges | `data/neuralweb/causal_edges.jsonl` | shadow | append-only candidate edges w/ full battery |
| causal-nulls | `data/neuralweb/causal_nulls.jsonl` | infrastructure | null library, feeds kill mask + packs |
| causal-mechanisms | `data/neuralweb/causal_mechanisms.jsonl` | shadow | mechanism cards |
| causal-frontier | `data/neuralweb/causal_frontier.json` | shadow | coverage map + value scores + cumulative width |
| causal-surprise-queue | `data/neuralweb/causal_surprise_queue.jsonl` | infrastructure | unexplained-variance tickets (per-source asof stamps) |
| causal-confluence-audit | `data/neuralweb/causal_confluence_audit.json` | shadow | directed annotations |
| causal-lab-state | `data/neuralweb/causal_lab_state.json` | shadow | heartbeat + funnel counts + width |
| site-causal-lab-state | `site/neuralwebdata/causal_lab_state.json` | display | operator/committee copy |

## 3. The loop, end to end

```text
nightly:  inventory → target panels → drift check → frontier → surprise → lab state
weekly:   bounded battery (top-K frontier cells, per-cell ledger logging)
          → pack(frontier + surprise + nulls + kill mask)   [always]
          → LLM chain (operator-triggered, or auto_loop after Phase-A, service-key)
          → schema firewall → dedup → inbox (ISO-week idempotent)
          → exits: (a) cortex may stake (3/wk, unchanged) | (b) Fable charters domain study | (c) decay
maturity: evaluator grades post-registration only → verdicts append null library
          → kill mask + frontier update → next week's pack is smarter
quarterly: FDR review, null-basin retirement, frontier re-score, come-back packet
```

## 4. Build waves (PR plan)

| Wave | PR content | Depends |
|---|---|---|
| W0 | this masterplan + Codex source doc (token-break edits noted) + DO_NOT_REBUILD rows + clocks + `causal_scan` in known_fdr_families | — |
| W1 | causal constitution + feature inventory (engine, builder, tests, synapse, dag) | W0 |
| W2 | scout core + synthetic gauntlet (no live batch); TrialLedger per-cell logging | W1 |
| W3 | live scout (regime/risk anchor family + entry_quality behind env-override) + nulls + frontier + surprise + causal job in daily.yml | W2 |
| W4 | mechanism-card schema + pack generator + ingest firewall + instrument library + causal_llm gate config | W2 |
| W5 | LLM runner (trigger + gate + degradation + ISO-week lock) + cortex read-tool + factory ingest routing + governance | W3, W4 |
| W6 | anti-mirage auditor + confluence tagging + admin Causal Lab card + descriptions + brief line | W3 |

Build discipline: each PR branches off fresh origin/main; Sonnet builds, Opus
reviews, Fable merges same-day (squash). Count-pin bumps: rebase + regen
SIGNAL_BUS.md immediately before each merge (registry-drift recipe); CHF merges
are serialized by the orchestrator.

## 5. What "stronger than the Codex plan" concretely means

1. **Closed loop with a lawful autonomy gate** — frontier ledger + surprise queue
   give the machine its own agenda; the LLM chain is fully built and one
   operator config-flip (after Phase-A) makes the whole loop hands-free.
2. **Kill mask compiled from case law** — DO_NOT_REBUILD (curated mirror) + null
   library (regenerated nightly, CI-synced) make adjudicated dead edges
   physically unproposable.
3. **Identification upgrades** — instrument classes with mandatory exogeneity
   schema; estimator law with cross-sectional dependence control, overlap
   correction, time-preserving placebos, era honesty (insufficient_era_span /
   insufficient_power are first-class verdicts).
4. **Synthetic gauntlet** — six planted mirage classes must be rejected before
   any live edge publishes.
5. **Launder-proof multiplicity** — per-cell cumulative trial accounting with
   printed family width riding every exit.
6. **Composition, not duplication** — R-ORTH keeps undirected independence; CHF
   adds only directed structure; MPC stays the deterministic narrator and
   becomes a surprise SOURCE (its printed nulls seed the queue).

## 6. Ops dependencies (loud)

1. **`CLAUDE_CODE_OAUTH_TOKEN` is corrupted** (repo secret; "Connection error" at
   turn 0 since 2026-07-04). Until the operator re-sets it, the cortex stakes
   nothing (exit (a) volume is zero and printed as such).
2. **Scheduled CHF auto-loop needs a SERVICE-KEY** (`ANTHROPIC_API_KEY` repo
   secret) per the W-AUTO identity line — do not point the auto-loop at the
   user-OAuth token even after it is fixed.
3. `REPLAY_BOARDED_PATH` (runner-local absolute path) must be set as a repo
   variable for the entry_quality family; absent → honest `data_absent` null.
4. Machine registry is empty today (zero cortex hypotheses ever registered) —
   funnel counts start at zero and that is expected, printed, and honest.

## 7. Come-backs

- ~W3+35d: first-edge-batch review (quality of nulls, width accounting, drift).
- 2026-10-15: Phase-2 dedicated machine family question (needs ≥8 matured
  exit-(a)/(b) candidates + fresh ruling).
- 2027-01-15: Phase-3 small-universe structure learner question (needs one
  quarter of scout + null-library operation).

## 8. Red-team record (2026-07-09, 3-lens Opus panel)

- **law (BLOCK → resolved):** H1 regex guard hard-fail on the raw
  machine-family literal in both docs → token-break edits + `causal_scan`
  registered in known_fdr_families in this PR. RAIL classification struck as a
  cap dodge → rechartered as PROGRAM (CHF-R1 rewritten). LLM-in-loop auto-file
  vs RF "no scheduled autonomous LLM" line → Phase-A gate + operator trigger +
  service-key identity + CHF-R17 actor law. Factory enum misuse
  (source `external_idea`) → corrected to `external_report`/`external_idea`.
  ETM identity for non-metabolism cards → ETM links restricted to exit-(a)/(b)
  cards. A1-ceiling precedent citation corrected to RUL-ORTH-1.
- **stats (APPROVE_WITH_AMENDMENTS → incorporated):** max()-budget laundering →
  CHF-R3 rewritten to cumulative per-cell accounting with printed width and no
  descriptive-only tolerance on exits. Missing cross-sectional dependence
  control → CHF-R5 target-type inference law. entry_quality era claims →
  effective window corrected to ≈2022-06-30+, auto-stamp era_specific,
  insufficient_era_span / insufficient_power verdicts added. Invariance forking
  paths → frozen per-card split maps hashed at mint. Instrument exogeneity →
  CHF-R9 classes with mandatory schema. Synthetic gauntlet extended with
  cross-sectional and regime-persistence mirages. Overlap correction named.
- **ops (APPROVE_WITH_AMENDMENTS → incorporated):** replay_boarded absent from
  CI checkouts → env-override + data_absent degradation; regime/risk family is
  the CI-safe anchor. "Oracle automated loop" precedent claim corrected (cortex
  is the automation precedent; runner is net-new). ISO-week idempotent filing
  lock for the token-flip case. Count-pin merge-race discipline named. Surprise
  sources stamped with per-source asof (winner_episodes staleness). Compute
  costed: nightly drift-only, weekly bounded K ≤ 40, timeout 45m. Kill-mask
  regeneration + CI sync test (curated mirror stays curated per the
  no-extractor ruling). Narrow git-add block pre-written; trial-ledger
  multi-writer discipline noted. Contract-manifest non-registration stated.

## 9. Status log

- 2026-07-09: W0 adjudicated (CHF-R1..R17), red-teamed, amended.
