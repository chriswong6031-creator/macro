# NW Core-Cognition Docket — Adjudication & Build Charter (by Fable)

Date: 2026-07-06
Adjudicator: Fable (main loop)
Input: `research/NW_FABLE_EXIT_ACTUAL_TOP3_CORE_BUILDS_BY_CODEX.md` (Codex, 2026-07-07 stamp)
Evidence: 5-lane repo census (4 Sonnet lanes + 1 Haiku prior-art grep) against origin/main @ #1786,
then a two-critic Opus red-team of the draft ruling (steelman-Codex vs skeptic). Red-team dispositions
are recorded in §7 — several materially amended this final ruling.

## In plain English

Codex proposed three "deep cognition" builds for the Neural Web: (1) a learned market-state embedding
(R6), (2) a counterfactual "what if" engine (R7), and (3) a compiler that turns scattered
driver/transmission fragments into a persistent "why did the tape move today" artifact. We fact-checked
every load-bearing claim against the repo and red-teamed the draft verdicts from both directions.
Final: **one thin accept, one library-sized salvage, one park with a cheap preservation step.** The
pathway compiler is real but must be a thin reader over artifacts we already emit — not a second
computation of them. The counterfactual engine's ambitious half has no computational backend (it would
emit stories dressed as experiments); its boring half — "if this artifact goes stale, what downstream
surfaces are compromised" — ships as a library inside existing surfaces, not as new nightly plumbing.
The latent-state model stays parked because its decisive evaluation ruler doesn't exist yet, but its
feature manifest (the leakage/PIT census) is cheap, un-blocked, and ships now as a one-shot artifact.

## Executive verdicts

| # | Codex proposal | Verdict | What ships now |
|---|---|---|---|
| 1 | R6 Latent State Foundation Rail | **PARK** encoder (laws frozen; re-open clock) — **ACCEPT** R6.1-lite manifest as one-shot | §3 laws + `panel_manifest` / coverage audit (no nightly step, no model) |
| 2 | R7 Causal Intervention / Counterfactual Rail | **KILL** signed counterfactuals; **SALVAGE** blast-radius as a library | `support_map.py` library embedded in health.json + admin (no new registered artifact) |
| 3 | Mechanism Pathway Compiler | **ACCEPT — thin** | `mechanism_pathways.py` reading emitted artifacts only + consumer citations |

Codex's "One-Day Fable Ask" (ratify all three as build authority) is granted **in modified form**: this
document is the ratification; MPC gets thin-build authority, R7 gets library-salvage authority, R6 gets
frozen laws plus manifest-only authority.

Docket quality: better than the typical Codex docket — exclusion boundary honest, evidence snapshot
accurate (verified: spine 288,666 rows; kernel 22 cells; confluence 148 nodes / 749 edges; PR #1635
OPEN). The operator's instinct that it is "not that useful" is right about the headline framing (two of
three items as specified would be over-builds or unevaluable) and wrong about the salvageable core.

## 1. Mechanism Pathway Compiler — ACCEPT, thin (chartered)

### Why accepted, and why thin

The census found the mechanism-chain content largely pre-assembled and nightly: `market_drivers.py`
computes 9 named drivers (fed_repricing, real_rate_shock, usd_shock, credit_stress, liquidity_impulse,
china_stimulus, oil_shock, ai_semis, crypto_liquidity) with signed leg z-scores,
verdict/strength/dominance/evidence_legs/invalidation/runner_up, emitted to
`latest.json["market_drivers"]`; `rate_inflation_transmission.py` emits 4 ordered first/second/third-
order chains with EN/ZH text to `data/transmission/latest.json`. The skeptic critic is right that a
naive MPC would be a re-formatting layer. What is genuinely missing — and is the product — is:
(a) a unified episode-trigger union across market_drivers / risk_radar / regime_snap / factor-rotation;
(b) per-leg present/**stale**/conflicted/missing status against freshness SLAs;
(c) honest `no_pathway` nulls, printed with reasons;
(d) a persistent, citable history ledger so daily_brief/Ask Brain/cortex/committee stop improvising
    explanations (census: daily_brief does zero "why" narration today);
(e) transmission chains attached as ordered mechanism edges to the day's driver verdict.

**RUL-CC-11 (drift law, from red-team):** MPC **must read emitted artifacts only** —
`latest.json["market_drivers"]` (freshness governed by the registered regime-latest SLA) and
`data/transmission/latest.json`. It may **never recompute** the classifiers, re-run leg math, or select
its own as-of. One computation, one truth: hk.html/china.html/transmission.html and MPC must be
incapable of disagreeing about the primary driver.

**Module:** `engine/neuralweb/mechanism_pathways.py` (small, thin); builder
`scripts/build_mechanism_pathways.py`.
**Artifacts:** `data/neuralweb/mechanism_pathways.json` (schema `neuralweb.mechanism_pathways.v1`),
`data/neuralweb/mechanism_pathways_history.jsonl` (append-only; nightly is the sole advancer),
`site/neuralwebdata/mechanism_pathways.json` (direct write by builder).

**Birth authority (printed in artifact):**

```yaml
tier: display
horizon_role: context
weights: none
scored_path_surfaces: []
may_rank: false
may_gate: false
may_size: false
may_escalate: false
display_only: true
not_a_signal: true
forbidden_uses: [ranking, sizing, alert_escalation, claim_validation, board_ordering, mastermind_arming]
```

**v1 families (10):** the 9 market_drivers families verbatim + `factor_rotation`. Deferred to v2:
china_sector_pathway (asia-close.yml cross-workflow freshness), demand_chain (name-level mapping
collides with the no-ticker-details brief law).

**Family/leg definitions (RUL-CC-2):** required legs and expected signs are the leg sets and canonical
signs **already defined in `market_drivers.py`, read from its emitted evidence — reused verbatim**; no
new thresholds, weights, or leg lists at birth. Rates/inflation families additionally attach the
relevant transmission CHAIN as ordered edges (first-order → `same_day`, second → `days_1_5`, third →
`weeks_1_4`). Optional context legs (never required): factor weather state, vol regime, matching
news_vector events by topic slice.

**Triggers and primary-selection precedence (RUL-CC-12, frozen — red-team fix):**
1. `market_drivers` verdict == `clear` → primary = that driver's family; `runner_up` seeds alternate 1.
2. else `risk_radar` dominant_scare escalation → primary via the frozen scare→family map:
   credit→credit_stress, rates→real_rate_shock, bubble→ai_semis, global→usd_shock;
   vol/growth scares have no clean family → `no_pathway(reason=scare_unattributed)`.
3. else factor-rotation persistent flip → primary = factor_rotation family.
4. no attributable trigger (incl. regime-snap-only days) → `no_pathway(reason=no_attributable_driver)`;
   broad flips are recorded as trigger context, never narrated into a family they cannot support.
   *Build-time amendment (ratified 2026-07-06):* the snap boolean lives in `data/regime/regime_snap.json`,
   a site-builder product outside the RUL-CC-11 read-set, so v1 cannot key on `snap==True`; the branch-4
   null is therefore labeled `no_attributable_driver` rather than `snap_unattributed`.
Ties resolve by this fixed order. The market_drivers ranked `scores` list seeds alternates (≤2) in all
cases. At most 1 primary + 2 alternates per day.

**Stale-trigger guard (RUL-CC-13, red-team fix):** if the trigger's source artifact is stale per its
registered freshness SLA, MPC emits `no_pathway(reason=trigger_stale)`. A mechanism story may not be
narrated off a stale driver read — this closes the narrative-laundering re-entry the docket itself
warned about.

**Node schema:** `node_id, as_of, domain, source_artifact, entity, observation, direction, value,
z_or_percentile, source_tier, lag_class, pathway_role, evidence_refs`.
**Edge schema:** `src_node, dst_node, mechanism_type, expected_lag ∈ {same_day, days_1_5, weeks_1_4},
expected_sign, observed_sign, status ∈ {measured, theory_prior, context_only, conflicted, missing,
stale}, evidence_refs`.

**Scores (RUL-CC-3, amended per red-team):**
- `coverage_score` (float 0–1) = required legs present with readable, fresh values / required legs.
  Stale legs count as not-present and are listed under `stale_legs`.
- `coherence` is **categorical only**: `supported | partial | conflicted` (from the emitted agreement
  bands). No float is ever emitted. Reason, printed in the artifact: leg agreement is near-tautological
  for the trigger-selected primary (`market_drivers.py` documents this and deliberately declines to
  score it); a float would read as conviction. Coherence exists to compare *alternates*, not to grade
  the primary.
- `confidence_ceiling` = `context_only` always in v1. These grade explanation support, never forecast
  value; they may never enter any scored path.
- Emission floor: coverage < 0.5 → `no_pathway(reason=insufficient_coverage)` (RUL-CC-4).

**Language law (RUL-CC-5):** pathway narratives may say "consistent with / supported / unsupported /
conflicted / missing". Banned in pathway text: "caused", "proved", "proof", "validated". Bilingual
EN/ZH; no CJK in `title=` attributes (CI-guarded).

**Consumers (v1):** daily_brief new section citing the top pathway (or the printed null);
ask_brain read-only `read_mechanism_pathways`; committee.html compact "Why the tape moved" block;
admin QA section (stale/missing legs, emission-rate). Forbidden: board ordering, alert priority,
Mastermind arming, candidate scoring, source-reliability grading.
**RUL-CC-10:** citations stay at driver/asset-class/ETF level (extends the candidate_watch law).

## 2. R7 — KILL signed counterfactuals; SALVAGE blast radius as a library

### Killed (RUL-CC-6)

`shock_driver` and any signed-propagation intervention are **killed**: synapse/confluence edges carry
no sign or transfer coefficient (verified — edge schema has no `expected_sign`), so a signed shock over
a structural graph can only emit theory-priors wearing an experiment's costume. The historical
matched-context estimator (PR-R7.3) is an unregistered-study generator — anything of that shape arrives
as a pre-registered study through the gauntlet, not as a rail feature. Policy counterfactuals are owned
by R1; macro-state "what if" belongs to R5 transitions once PR #1635 merges.

Per the steelman critic: a *structural-only* `set_state` (support-set deltas — "which confluence claims
are conditioned on regime==X") degenerates to the same reachability operation as suppress/delay. It is
therefore **subsumed by the Support Map substrate** and may ship later as a v1.1 query without new
authority or vocabulary — it is not killed as a question, only as a rail class. A standalone
intervention registry is rejected: TrialLedger/gauntlet already owns pre-registration discipline.

### Salvaged: Support Map as a library (amended per red-team — no new nightly artifact)

Census: no module performs multi-hop traversal over the artifact DAG (synapse.py exposes only 1-hop
lookups; health.py scores artifacts independently; admin shows 1-hop consumers; what_is_stale is a flat
list). The skeptic critic showed the demonstration BFS was lossy: synapse `consumers` are module paths,
35 producer modules emit >1 artifact, so naive inversion bleeds unrelated artifacts into the radius,
and real reachability extends to 5 hops. Both findings are incorporated:

**Charter:** `engine/neuralweb/support_map.py` — a **pure-function library** over `config/synapse.yml`.
No standalone registered artifact, no new nightly step, no new synapse/dag entries.
- Traversal is artifact-level, to **fixpoint** (no hop cap), with by-hop annotation.
- The result is explicitly labeled **`bound: upper`** — shared-producer inversion over-attributes, and
  the artifact notes say so. For ops ("what *might* be compromised"), an honestly-labeled upper bound
  is the right conservatism.
- **RUL-CC-7:** `config/synapse.yml` is the authoritative adjacency source; `confluence_graph.json` is
  a derived view (currently drifting: 9 registered artifacts missing from it). The library computes a
  `synapse_vs_confluence_coverage` warning as part of its output.
- Language: "downstream surfaces that read this artifact (directly or transitively)". The words
  "would have", "caused", and all counterfactual phrasing are banned.

**Embedding (v1):** (a) `health.py` build embeds, for each stale/missing/degraded artifact, its direct
consumers and upper-bound transitive downstream inside the existing `health.json` (already registered —
no new surface); (b) `admin/neural_web.py` lobe pages compute upstream/downstream views on demand from
the library; (c) daily_brief `what_is_stale` enrichment (W3) reads the health.json embedding — one line
per stale lobe naming what it degrades.

## 3. R6 — PARK the encoder; laws frozen; manifest ships as one-shot

### Why the encoder stays parked (RUL-CC-8, amended per red-team)

The draft ruling overstated one claim, and the steelman critic caught it: Codex lists **four** allowed
evaluations, not one. Corrected reasoning:

1. The **decisive** evaluation — does the latent state condition kernel calibration better than quad
   labels — cannot run today, and it is the only one that would justify the rail's existence as
   calibration infrastructure. The kernel has 22 cells and zero real quad-regime buckets. Materially:
   this is a **stamping-plumbing gap, not a data gap** — `regime_v2_pit.parquet` holds a 55-year quad
   series (1971→) joinable to ~95% of track_record's as_of dates as `recomputed_history` conditioning
   strata. Whether the kernel adopts backfilled quad stamping is a kernel-program decision (its first
   decision batch is due 2026-10-01), not this docket's to order.
2. The two self-contained evaluations (reconstruction error precedes contradiction spikes; latent
   detects transitions quad labels miss) are runnable but weak falsifiers: the contradiction-spike
   series is short and itself derived, and "transitions quad misses" has no ground truth without the
   kernel ruler — it cannot fail. Weak falsifiers alone do not justify an encoder build.
3. Era confound: with feature-family coverage starting in different epochs (spine 1962→, options/
   breadth 2021→), latent axes would encode data-availability eras (DT-R16 era-split law binds).

### R6.1-lite ships now (steelman accepted)

The feature manifest is un-blocked by every park reason, cheap, and is precisely the perishable
"freeze the ontology while Fable is here" asset. **Ships as a one-shot research artifact** — no nightly
step, no synapse/dag registration, no model: `research/neuralweb/latent_state/panel_manifest.json`
(every candidate feature: `source_artifact, first_available_date, pit_basis, revision_basis,
leakage_risk, null_policy`) + `feature_coverage.md` audit (per-family coverage windows, era table).
This makes the frozen laws machine-checkable instead of prose-only.

### Frozen laws (binding on any future R6 build)

1. PIT basis vocabulary per feature: `pit_live | recomputed_history | vintage |
   current_snapshot_backfill | display_only`.
2. Forward outcomes may never be encoder inputs; evaluation labels only.
3. Latent clusters remain unnamed until stable across two consecutive quarterly refits, where stable
   means cluster-membership Jaccard ≥ 0.8 on the overlapping window (red-team fix: enforceable
   predicate). Named or not, clusters are display-only and may never gate, rank, size, or escalate.
4. Era-composition disclosure: any cluster whose membership is >80% one coverage era is reported as an
   era detector, not a state — printed in the model card.
5. Model card + eval.json mandatory at first emit; no return-prediction headline at birth.

### Re-open conditions and clock (amended)

Re-open the encoder when **either** (a) the kernel has real quad-conditioned cells for ≥3 engines with
n_eff ≥ 30 each via forward accrual, **or** (a') the kernel program adopts recomputed_history quad
backfill (printed caveat) giving the conditioning baseline; **and in both cases** (b) at least one
kernel decision batch has run (first due 2026-10-01). **Come-back clock: 2027-01-06.**

## 4. Rulings

1. **RUL-CC-1** — MPC chartered: deterministic, display-only, no LLM in the compile loop, thin-build
   authority per §1.
2. **RUL-CC-2** — MPC family/leg/sign definitions reuse market_drivers emissions + transmission CHAINS
   verbatim; no new thresholds at birth.
3. **RUL-CC-3** — coverage_score float; **coherence categorical only** (supported/partial/conflicted),
   never a float; both grade explanation support, never forecast value; never enter a scored path.
4. **RUL-CC-4** — Emission discipline: ≤1 primary + ≤2 alternates/day; coverage < 0.5 →
   `no_pathway(reason=insufficient_coverage)`; all nulls printed with reasons.
5. **RUL-CC-5** — Language law: "consistent with / supported / unsupported / conflicted / missing";
   banned: "caused / proved / validated".
6. **RUL-CC-6** — `shock_driver` + matched-context estimation killed; structural `set_state` subsumed
   by the Support Map substrate (v1.1 query, no new authority); intervention registry rejected
   (gauntlet owns pre-registration).
7. **RUL-CC-7** — synapse.yml is the authoritative adjacency source; confluence_graph is a derived
   view; the library surfaces the drift between them.
8. **RUL-CC-8** — R6 encoder parked per §3; laws frozen; re-open per amended conditions; come-back
   2027-01-06. R6.1-lite manifest ships now as a one-shot research artifact.
9. **RUL-CC-9** — Nothing chartered here may read PR #1635 (R5 macro) artifacts until that PR merges.
10. **RUL-CC-10** — No ticker-level details in daily_brief/committee pathway citations.
11. **RUL-CC-11** — MPC reads emitted artifacts only (`latest.json["market_drivers"]`,
    `data/transmission/latest.json`); recomputation of classifiers is forbidden (drift law).
12. **RUL-CC-12** — Trigger precedence + scare→family map frozen per §1; unattributable triggers emit
    printed nulls, never a borrowed narrative.
13. **RUL-CC-13** — Stale trigger → `no_pathway(reason=trigger_stale)`; no mechanism story off a stale
    driver read.
14. **RUL-CC-14** — Support Map is a library embedded in existing surfaces (health.json, admin); it is
    an upper bound and must print `bound: upper`; no standalone registered artifact in v1.

## 5. Build waves

| Wave | Branch | Content | Builder | Reviewer |
|---|---|---|---|---|
| W0 | `docs/nw-core-cognition-adjudication` | this ruling + Codex source copy | Fable (main loop) | 2× Opus red-team (done) |
| W1 | `feat/nw-mechanism-pathways` | MPC engine + artifacts + synapse/dag/daily.yml + tests | Sonnet | Opus |
| W2 | `feat/nw-support-map-lib` | support_map library + health.json embed + admin views + tests | Sonnet | Opus |
| W3 | `feat/nw-pathway-consumers` | daily_brief + ask_brain + committee.html + admin QA for MPC; brief stale-enrichment from health embed | Sonnet | Opus + Haiku i18n sweep |
| W4 | `feat/nw-r6-manifest` | R6.1-lite one-shot manifest + coverage audit (research-tier) | Sonnet | Opus |

W1 ∥ W2 ∥ W4 may run in parallel (disjoint files after the W2 library amendment: only W1 touches
synapse.yml/dag.yml/daily.yml). W3 runs after W1+W2 merge (consumes both). Nightly wiring per census:
the MPC step runs in the engine job after `build_world_state`, before `build_neuralweb_health`,
non-fatal wrapper, committed by the engine job's "commit engine outputs" step (cross-job artifact
visibility law). MPC registers data + site-mirror entries in synapse.yml and the step in dag.yml
(dag-conformance is a hard gate).

## 6. Come-back clocks

- **2026-07-20** — MPC first-emissions QA: `mechanism_pathways_history.jsonl` emission mix (expect
  pathways *and* printed nulls; all-null or all-fire both smell); stale-leg rates in admin QA;
  support-map embed sanity in health.json.
- **2026-10-01** — kernel first decision batch (existing clock; feeds R6 re-open condition (b)).
- **2027-01-06** — R6 park re-check per §3.

## 7. Red-team record (Opus critics, 2026-07-06)

**Steelman-Codex critic:** 7 objections. Accepted: #1 (draft misstated "only evaluation" — four exist;
§3 rewritten), #2/#3 (quad-cell blocker is stamping plumbing, not data absence; re-open conditions
amended with the backfill path), #4 (R6.1-lite manifest un-blocked and perishable — now W4), #7
(stability law needed an enforceable predicate — Jaccard ≥ 0.8). Partially accepted: #5 (structural
set_state subsumed by Support Map substrate as v1.1 query, not a revived rail). Rejected: #6
(intervention registry — gauntlet owns pre-registration; duplicate governance).

**Skeptic critic:** 10 objections. Accepted: #3 (read-not-recompute drift law → RUL-CC-11), #4/#6
(coherence near-tautological for the primary — categorical only → RUL-CC-3 amended), #5 (trigger
precedence undefined → RUL-CC-12), #7 (BFS over-attribution + hop-cap wrong → fixpoint + `bound:
upper` → RUL-CC-14), #8 (standalone Support Map artifact over-build → library embedded in existing
surfaces), #9 (stale-trigger narrative laundering → RUL-CC-13). Partially accepted: #1/#2 (re-format
critique valid → "thin" scope; the delta (episode union, staleness, printed nulls, citable history)
is the product and survives). Noted: #10 (in-job ordering verified sound; drift binding made explicit).

Both critics independently endorsed: the R7 signed-counterfactual kill, the R1/R5 ownership boundary,
and the MPC/Support-Map gap being real. Neither found a blocking defect in the final shape.
