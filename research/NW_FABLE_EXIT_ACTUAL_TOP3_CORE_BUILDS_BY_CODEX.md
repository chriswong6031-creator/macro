# Neural Web Fable Exit: Actual Top 3 Core Builds

Prepared: 2026-07-07
Author: Codex
Status: Replacement analysis after operator rejection of the prior precaution-heavy list.

## Executive Ruling

The prior answer was not good enough because it drifted toward precautions, governance, and adjacency work. The operator's actual question is narrower and harder:

> What should be built now because it is core to making Neural Web stronger, novel versus prior chats, and too conceptually difficult to define cleanly after Fable is gone?

After re-checking prior Neural Web memos, live PRs, core code, signal-bus artifacts, and three delegated repo sweeps, the top 3 are:

1. **R6 Latent State Foundation Rail**
   - Give Neural Web a learned, PIT-safe representation of market state across every lobe and rail.
   - This is the missing "shared latent language" beneath world_state, spine, kernel, confluence, and cortex.

2. **R7 Causal Intervention / Counterfactual World-Model Rail**
   - Give Neural Web an imagination layer: "if this state/lobe/artifact/driver changes, what else changes?"
   - This must sit above active R5 macro-context work and R1 policy replay; it should not duplicate either.

3. **Mechanism Pathway Compiler**
   - Give Neural Web a durable "why is this happening?" artifact that compiles time-ordered mechanism chains across macro, rates, credit, liquidity, flows, factors, news, sectors, and names.
   - This turns scattered explanatory fragments into a persistent reasoning object the cortex and Ask Brain can cite.

These are not new score lobes. They are core brain faculties:

```text
R6 learns the state space.
R7 imagines interventions inside that state space.
Mechanism Pathways explain the live causal story in human-readable form.
```

## Hard Exclusion Boundary

The following are excluded because they are already built, discussed, active, or directly adjacent to an active lane:

- Options entry state, GEX/OPEX/vanna/charm, signed options tape, options analogue library.
- Bottom/durable-bottom primitives, sponsorship/solvency/event-hazard, entry-stack expansions.
- Long-term thesis layer, expectation drift, thesis ledger, moat falsifiers.
- Mastermind bridge and context-only Neural Web export.
- Agentic Research Factory, claim reliability, narrative truth, paper monitor, challenger packets.
- Final-3 lobe upgrades: Exit/Trim, Dispersion/Selection-Regime, Liquidity/Execution, Cash/Patience follow-on.
- R-ORTH independence/covariance, disagreement mining, analogue retrieval, breadth budgeting.
- Macro/policy transmission L6 and portfolio/thesis independence L8.
- Short-side/options/operator next-3 upgrades.
- Public/private data boundary, governance-only precautions, access controls, and generic guardrails.
- Active PR #1635: R5 macro context intake and memory rail. That PR already owns macro world_state lobes, macro snapshot registry, macro transitions, spine macro stamps, macro weather page, confluence macro edges, and ask-brain macro routing.

The replacement top 3 below are intentionally above or orthogonal to those lanes.

## Evidence Snapshot

Current Neural Web already has a strong symbolic nervous system:

- `engine/neuralweb/world_state.py` composes the current blackboard: verdict, regime, vol, breadth, rotation, liquidity, alerts, factor/options context, contradictions.
- `data/neuralweb/world_state.json` is today's composed state, not a learned model or simulator.
- `engine/neuralweb/query.py` builds `spine_index.parquet`, a federated ledger of claims, outcomes, horizons, regimes, and role flags.
- Local `data/neuralweb/spine_index.parquet` has about 288,666 rows and 38 canonical columns.
- `engine/neuralweb/kernel.py` estimates `(engine, regime, horizon)` reliability cells; local kernel estimates are still sparse at 22 rows.
- `engine/neuralweb/confluence.py` builds a display-only graph; local `confluence_graph.json` has 148 nodes and 749 edges, mostly structural feed edges.
- `engine/neuralweb/cortex.py` is a bounded read/write tool loop under shadow probation.
- `engine/neuralweb/daily_brief.py` gives deterministic daily "what changed" output, but not a general world-state transition model.
- `engine/rule_replay.py` and `research/rule_replay/R1_CHARTER.md` own fire-tape x policy-grid replay, not whole-brain intervention.
- Open PR #1635 owns R5 macro context intake/memory: macro snapshots, macro transitions, macro world_state lobes, macro weather page, and macro ask-brain routing.

So the gap is not "wire the brain." That exists.

The gap is:

```text
Neural Web can compose, remember, grade, display, and answer.
It cannot yet learn a unified latent state space,
cannot yet intervene on that state space,
and cannot yet persist a time-ordered mechanism explanation of the live tape.
```

## Scoring

| Rank | Candidate | Direct NW strength | Fable-needed complexity | Novelty after exclusions | Build urgency |
|---|---:|---:|---:|---:|
| 1. R6 Latent State Foundation Rail | 5/5 | 5/5 | 5/5 | 5/5 |
| 2. R7 Causal Intervention Rail | 5/5 | 5/5 | 4/5 | 5/5 |
| 3. Mechanism Pathway Compiler | 5/5 | 4/5 | 5/5 | 4/5 |

Ranking logic:

- R6 is first because it changes what Neural Web *is*: a typed artifact graph becomes a learned market-state representation.
- R7 is second because it gives the brain a real "what if" faculty, but it should consume R5 macro transitions and R6 embeddings rather than front-running them.
- Mechanism Pathways are third because they are the fastest useful visible product and deeply improve Ask Brain/Cortex, but their ontology is slightly less mathematically fragile than R6/R7.

## 1. R6 Latent State Foundation Rail

### Killer Question

What is the market state, in a representation Neural Web can learn from, compare, compress, and monitor across all lobes?

Today Neural Web has many typed state descriptions:

- regime labels;
- world_state blocks;
- kernel cells;
- confluence graph nodes and edges;
- cycle-pattern states;
- factor weather;
- options weather;
- bottom sensors;
- stock personality;
- macro snapshots from active PR #1635 if it merges.

But these remain symbolic surfaces. Neural Web does not have a learned market-state embedding that can say:

- this state is close to those past states in a multi-lobe sense;
- this state's representation is drifting away from prior regimes;
- this combination of lobes is anomalous even if no single lobe is screaming;
- raw regime labels miss a latent transition the full system sees;
- kernel calibration improves when conditioned on this latent cluster versus simple quad labels.

### Why Fable Is Needed Now

This is exactly the kind of thing that becomes dangerous if built casually after Fable:

- The feature panel can leak future information unless Fable freezes the PIT rules.
- The embedding can become a hidden score unless Fable freezes authority boundaries.
- The model objective can accidentally train on forward outcomes and become an unregistered alpha model.
- The cluster names can become fake narratives unless Fable freezes naming discipline.
- The feature manifest must distinguish live PIT, recomputed history, current-snapshot backfill, and display-only context.

The important thing to preserve before losing Fable is not the full model implementation. It is the **charter, feature ontology, leakage law, model-card schema, and promotion boundary**.

### What It Is

R6 is an infrastructure/context rail:

```text
data/neuralweb/latent_state/
  panel_manifest.json
  state_daily.parquet
  model_card.json
  eval.json
  feature_coverage.parquet
```

It builds a PIT-safe feature panel and learns compact vectors over market-state days or state episodes.

Birth authority:

```yaml
tier: infrastructure
horizon_role: context
weights: none
scored_path_surfaces: []
may_rank: false
may_gate: false
may_size: false
may_escalate: false
```

### What It Is Not

- Not an alpha model.
- Not analogue retrieval.
- Not disagreement mining.
- Not a replacement for explicit confluence/contradiction records.
- Not a replacement for R-ORTH.
- Not a macro context rail; active PR #1635 owns that input layer.
- Not a hidden gate for boards, alerts, or Mastermind.

### Feature Panel Design

Fable should freeze the first manifest around feature families, not a large list of raw columns.

Recommended families:

1. **Regime and macro context**
   - Source: `data/regime/regime_v2_pit.parquet`, `data/regime/latest.json`, and PR #1635 macro snapshots if merged.
   - PIT class required on every feature: `pit_live`, `recomputed_history`, `vintage`, `current_snapshot_backfill`, or `display_only`.

2. **Spine claim density**
   - Source: `data/neuralweb/spine_index.parquet`.
   - Features: claim counts by engine/family/horizon/direction/role, not forward outcomes.
   - Forward outcomes are evaluation labels only, never encoder inputs.

3. **Kernel reliability context**
   - Source: `data/neuralweb/kernel_estimates.parquet`, `kernel_families.json`.
   - Features: n_eff, reliability, armed flag, date_last, but no behavior change.

4. **Confluence and contradiction topology**
   - Source: `data/neuralweb/confluence_graph.json`.
   - Features: edge counts by type, contradiction counts, lobe/node degree, display-only topology summaries.

5. **Cycle and hazard context**
   - Source: `data/neuralweb/cycle_pattern_state.json`, `data/cycle_pattern/state_daily_live.parquet`.
   - Features: phase distribution, hazard summaries, truth coverage, not raw future labels.

6. **Options/factor/bottom sensors**
   - Source: existing Neural Web display artifacts.
   - Important: context-only features; no options-lane duplication.

7. **Stock personality and board context**
   - Source: stock personality artifacts and candidate-board summaries where PIT-safe.
   - Features aggregate by day or cohort, not forward-looking labels.

### Baseline Model

Do not start with an opaque fancy model. Start auditable:

1. Feature normalization with explicit missingness masks.
2. PCA or autoencoder baseline for dimensionality reduction.
3. Masked-field reconstruction task:
   - hide feature families;
   - predict them from the rest;
   - score reconstruction by family.
4. Next-state classification task:
   - predict next coarse state transition from today's features;
   - state transitions are from current labels only, not future returns.
5. Drift/anomaly score:
   - high reconstruction error;
   - large vector distance versus trailing history;
   - cluster transition not seen often in prior history.

### Evaluation

Evaluation should answer:

```text
Does the latent state condition existing Neural Web calibration better than raw regime labels?
```

Allowed evaluation:

- Does latent cluster explain variation in existing kernel accuracy, out-of-time?
- Does latent state improve calibration slices for already-logged claims?
- Does reconstruction error precede data-quality or contradiction spikes?
- Does latent state detect transitions not captured by quad labels?

Forbidden evaluation at birth:

- no "does cluster predict returns" headline;
- no board score improvement;
- no sizing utility;
- no hidden composite score;
- no "validated alpha" language.

### First PR Sequence

**PR-R6.0 - Fable charter**

- File: `research/neuralweb/R6_LATENT_STATE_FOUNDATION_RAIL_BY_FABLE.md`
- Freeze authority, feature classes, PIT basis vocabulary, model objectives, output schemas, and non-goals.

**PR-R6.1 - Feature manifest and panel audit**

- Build only `panel_manifest.json` and `feature_coverage.parquet`.
- No model yet.
- Every feature has `source_artifact`, `first_available_date`, `pit_basis`, `revision_basis`, `leakage_risk`, `null_policy`.

**PR-R6.2 - Baseline encoder**

- Off-render training.
- Emit `state_daily.parquet`, `model_card.json`, `eval.json`.
- Display-only.

**PR-R6.3 - Read-only integration**

- `world_state.latent_state` compact summary.
- Ask Brain read-only tool.
- Committee/admin context surface.
- No board/alert consumers.

### Fable Must Freeze

- PIT feature taxonomy.
- Which source artifacts are eligible in v1.
- The rule that forward outcomes cannot be inputs.
- The rule that latent clusters are unnamed until stable, and even named clusters remain display-only.
- The model-card schema.
- The evaluation bar for "useful context" without alpha claims.

## 2. R7 Causal Intervention / Counterfactual World-Model Rail

### Killer Question

If Neural Web changes one part of its world model, what else changes?

Examples:

- If credit stress is treated as the primary driver, which contradictions disappear and which appear?
- If an input artifact is delayed or stale, which lobe conclusions become unsupported?
- If a macro driver flips from headwind to tailwind, which pathways and context summaries change?
- If a lobe is suppressed, which candidate explanations still survive?
- If a signal family is removed, which confluence claims are still supported by independent evidence?

This is not R1 rule replay. R1 answers:

```text
Given the production fire tape, what would policy rule X have done?
```

R7 answers:

```text
Given Neural Web's current state graph, what changes under intervention X?
```

### Collision Boundary

Do not duplicate these:

- R1 fire-tape x policy-grid replay.
- Active PR #1635 R5 macro snapshots and macro transition ledger.
- R-ORTH covariance/independence.
- Research Factory challenge packets.
- Confluence display graph.
- Daily brief "what changed" surface.

R7 should consume those surfaces and add one missing object: **a typed intervention registry and perturbation runner over the Neural Web state graph**.

### Why Fable Is Needed Now

This rail needs Fable because bad counterfactual engines are worse than none:

- A freeform "what if" tool becomes p-hacking instantly.
- Intervention vocabulary must be frozen or every result is post-hoc.
- It must know when to call R1, when to call spine/kernel, and when to refuse.
- It must separate structural propagation from empirical outcome estimation.
- It must never imply causal proof from confluence or co-firing edges.

### Required Type System

Fable should freeze edge and node semantics before implementation.

Node types:

```text
artifact
world_state_block
lobe_state
macro_context
signal_family
claim_family
confluence_edge
contradiction_record
consumer_surface
```

Edge types:

```text
structural_feed       # producer/consumer relationship from synapse
empirical_association # measured co-firing or kernel relation
historical_leadlag    # measured lead/lag, still not causal proof
mechanism_prior       # domain theory, explicitly unmeasured
causal_hypothesis     # registered hypothesis, no authority
forbidden             # edge may not be interpreted as causal or behavioral
```

Intervention classes:

```text
set_state             # set a world_state or macro_context field to a counterfactual value
suppress_artifact     # remove one artifact from available evidence
delay_artifact        # mark artifact stale or delayed
suppress_lobe         # remove lobe contribution from confluence/pathway explanation
shock_driver          # apply signed shock to a driver family, e.g. USD/rates/credit
substitute_policy     # delegate to R1 only when the intervention is actually policy replay
```

### Output Schema

Recommended artifacts:

```text
data/neuralweb/interventions/registry.jsonl
data/neuralweb/interventions/results/<intervention_id>_summary.json
data/neuralweb/interventions/results/<intervention_id>_graph_delta.json
```

Summary fields:

```json
{
  "schema": "neuralweb.intervention_summary.v1",
  "intervention_id": "...",
  "registered_at": "...",
  "intervention_class": "suppress_lobe",
  "target": "factor_weather",
  "question": "...",
  "allowed_backend": "graph_perturbation",
  "changed_nodes": [],
  "changed_edges": [],
  "changed_contradictions": [],
  "unsupported_claims": [],
  "unchanged_claims": [],
  "delegated_to": null,
  "outcome_estimation": "none",
  "display_only": true,
  "authority": "context",
  "forbidden_uses": ["ranking", "sizing", "alert_escalation", "claim_validation"]
}
```

### Build Sequence

**PR-R7.0 - Fable charter**

- Freeze intervention vocabulary.
- Freeze the difference between structural graph deltas and outcome estimation.
- Freeze delegation rules to R1, spine/kernel, macro snapshots, and mechanism pathways.

**PR-R7.1 - Whole-brain state graph adapter**

- Build a typed graph from:
  - `config/synapse.yml`;
  - `data/neuralweb/world_state.json`;
  - `data/neuralweb/confluence_graph.json`;
  - `data/neuralweb/spine_index.parquet`;
  - `data/neuralweb/kernel_estimates.parquet`;
  - R5 macro snapshots/transitions if #1635 merges.
- No interventions yet; just graph materialization and type validation.

**PR-R7.2 - Intervention registry and graph perturbation**

- Register interventions before running.
- Apply perturbation to copied graph/state only.
- Emit changed/unchanged support summaries.
- No outcome claims.

**PR-R7.3 - Historical matched-context estimator**

- Optional and later.
- Only for registered interventions where historical matching is valid.
- Must print matched n, leakage class, and null/placebo result.

**PR-R7.4 - Ask Brain read-only tool**

- `read_intervention_summary(intervention_id)`.
- No write tool for new interventions from the public endpoint.

### Fable Must Freeze

- Intervention classes and legal targets.
- Which classes require TrialLedger budget.
- When a run must delegate to R1.
- Which outputs are contaminated surfaces for future preregs.
- The language ban: no "caused", "proved", "validated"; use "under this intervention, support changed as follows."

## 3. Mechanism Pathway Compiler

### Killer Question

Why is this move happening, in a way the system can persist, cite, and falsify later?

Current repo has pieces:

- `engine/market_drivers.py` identifies dominant cross-asset drivers.
- `engine/rate_inflation_transmission.py` has first/second/third-order rate and inflation chains.
- `engine/china_sector_pathway.py` has China sector pathway logic.
- `engine/demand_chain.py` has customer-demand chain logic.
- `engine/news_vector.py`, `engine/news_event_ledger.py`, and `engine/news_flow.py` provide perception atoms.
- `engine/neuralweb/confluence.py` records structural confirms/contradictions.
- `engine/neuralweb/ask_brain.py` can answer request-scoped "why" questions.

But no persistent Neural Web artifact compiles those into:

```text
trigger -> mechanism -> ordered evidence nodes -> transmission edges -> contradictions -> alternate pathways -> missing evidence
```

This is the missing "why today?" faculty.

### Why Fable Is Needed Now

Mechanism compilation needs Fable because it sits between data and narrative:

- Too loose, and it becomes vibes.
- Too strict, and it never emits.
- Too score-like, and it becomes an unregistered signal.
- Too LLM-driven, and explanations become non-replayable.
- Too path-dependent, and current news writes the story backward.

Fable needs to freeze the mechanism ontology, lag windows, evidence tiers, and confidence ceiling now.

### Core Artifact

Recommended module:

```text
engine/neuralweb/mechanism_pathways.py
```

Recommended artifacts:

```text
data/neuralweb/mechanism_pathways.json
data/neuralweb/mechanism_pathways_history.jsonl
site/neuralwebdata/mechanism_pathways.json
```

### Schema

```json
{
  "schema": "neuralweb.mechanism_pathways.v1",
  "as_of": "YYYY-MM-DD",
  "display_only": true,
  "not_a_signal": true,
  "pathways": [
    {
      "pathway_id": "...",
      "trigger": {...},
      "mechanism_family": "rates_shock",
      "ordered_nodes": [],
      "edges": [],
      "evidence_summary": {...},
      "contradictions": [],
      "alternate_pathways": [],
      "missing_evidence": [],
      "coverage_score": 0.0,
      "coherence_score": 0.0,
      "confidence_ceiling": "context_only",
      "forbidden_uses": ["ranking", "sizing", "alert_escalation"]
    }
  ]
}
```

Important: coverage/coherence scores are not alpha scores. They only say whether the explanation is well-supported by observed mechanism legs.

### Event Node

Each node should include:

```text
node_id
as_of
domain
source_artifact
scope_type
entity
observation
direction
value
z_or_percentile
source_tier
lag_class
pathway_role
evidence_refs
```

### Mechanism Edge

Each edge should include:

```text
src_node
dst_node
mechanism_type
expected_lag
observed_lag
expected_sign
observed_sign
status: measured | theory_prior | context_only | conflicted | missing
evidence_refs
```

### First Mechanism Families

Start with deterministic templates where the repo already has primitives:

1. **Rates shock**
   - real yields, nominal yields, curve, duration equity, gold, dollar.
2. **Fed repricing**
   - front-end rates, fed funds futures, growth/value, dollar.
3. **Credit stress**
   - HY OAS, IG OAS, HYG/LQD, VIX, risk radar.
4. **Liquidity impulse**
   - net liquidity, high-beta/low-vol, small/large, crypto.
5. **USD shock**
   - DXY, copper, oil, EM/China, gold.
6. **Inflation/oil shock**
   - oil, breakevens, energy RS, defensives.
7. **AI/semis leadership or unwind**
   - semis RS, growth/value, cap/equal weight, tech/utilities, news.
8. **China stimulus/risk-off**
   - China equity, HK, copper, policy/news, sector pathway.
9. **Demand-chain confirmation/divergence**
   - hyperscaler capex or homebuilder demand versus beneficiary consensus.
10. **Factor rotation**
   - factor weather, style leadership, concentration/dispersion context.

### Compiler Flow

1. Detect candidate move episodes from:
   - market_driver changes;
   - regime/risk radar flips;
   - factor weather shocks;
   - options/factor/breadth/vol changes;
   - high-novelty news events;
   - large sector or index moves.

2. Generate candidate pathway templates.

3. Attach evidence in strict PIT windows.

4. Mark every required leg:
   - present;
   - missing;
   - conflicted;
   - stale;
   - theory-only.

5. Select best-supported pathway by coverage/coherence, not forecast value.

6. Emit alternates and missing evidence.

7. Let Daily Brief, Cortex, Ask Brain, and Committee cite the pathway artifact instead of inventing explanations ad hoc.

### Integration

Good first integrations:

- `daily_brief`: cite top pathway in `what_changed`.
- `ask_brain`: add read-only `read_mechanism_pathways`.
- `committee.html`: show top pathway and alternates in a compact "Why the tape moved" block.
- `admin/neural_web.py`: show stale/missing pathway legs for operator QA.

Forbidden integrations:

- no board ordering;
- no alert priority;
- no Mastermind arming;
- no direct candidate scoring;
- no source-reliability grading.

### Fable Must Freeze

- v1 mechanism families.
- Required and optional legs per family.
- Expected lag windows.
- Status vocabulary for edges.
- Coverage/coherence formula.
- Confidence ceiling language.
- Rules for "no pathway emitted" when evidence is too thin.

## Why These Three Are Better Than the Rejected Set

These are not "be careful after Fable" items. They are buildable faculties that make Neural Web materially stronger:

- R6 makes the brain learn its own state space.
- R7 lets the brain run controlled mental experiments over its state.
- Mechanism Pathways make the brain explain the live market in a persistent, evidence-cited form.

They are also hard to define without Fable because their failure modes are subtle:

- latent representations can become hidden scores;
- interventions can become p-hacked counterfactuals;
- pathway explanations can become narrative laundering.

The right move before losing Fable is to get Fable to freeze the ontology and authority boundaries, then let builders implement against that frozen spec.

## Suggested Build Order

If Fable time is extremely limited, do this:

1. **One Fable ratification doc covering all three**
   - Freeze R6/R7/Pathway charters and schemas.
   - No code required.
   - This preserves the hard conceptual work.

2. **Mechanism Pathway Compiler P0**
   - Fastest visible win.
   - Deterministic templates over existing driver/pathway/news/confluence primitives.

3. **R6 feature manifest**
   - Starts the long clock on PIT feature coverage and representation hygiene.
   - No model yet.

4. **R7 graph adapter and intervention registry**
   - Starts the world-model rail without outcome claims.

5. **R6 baseline encoder**
   - Only after the manifest is clean.

6. **R7 perturbation runner**
   - Only after graph typing and intervention vocabulary are stable.

## One-Day Fable Ask

If we only get one more serious Fable session, ask for this:

```text
Please ratify a Neural Web Core-Cognition Program with:

1. R6 Latent State Foundation Rail:
   feature manifest vocabulary, PIT basis classes, model objectives,
   output schemas, and no-authority law.

2. R7 Causal Intervention Rail:
   legal intervention classes, edge semantics, registry schema,
   delegation rules to R1/R5/spine/kernel, and contamination law.

3. Mechanism Pathway Compiler:
   v1 mechanism families, required evidence legs, lag windows,
   node/edge schemas, coverage/coherence scoring, and no-signal ceiling.

Do not implement the rails in this ruling. The ruling should be the build authority.
```

That is the most valuable thing to preserve before Fable leaves.

## Rejected Near-Misses

These were considered and rejected because they repeat prior work or active lanes:

- **Episode/analogue memory:** already discussed in quant-fund/options context; several active surfaces are adjacent.
- **Disagreement/arbitration router:** overlaps prior disagreement mining, R-ORTH, confluence, and claim reliability.
- **Claim reliability/narrative truth:** already adjudicated into waves and QI-owned gates.
- **Macro transmission:** already L6 and active R5 macro context PR territory.
- **Portfolio/thesis independence:** already L8/reflexivity/Mastermind boundary territory.
- **Attention/anomaly thalamus:** parked in the future-lobes docket because fused escalation is dangerous.
- **Generic scenario simulator:** too broad unless grounded in R7 intervention vocabulary.

## Bottom Line

The top 3 core builds are:

1. **R6 Latent State Foundation Rail**
2. **R7 Causal Intervention / Counterfactual World-Model Rail**
3. **Mechanism Pathway Compiler**

These are the missing deep-cognition pieces. They improve Neural Web directly, do not duplicate the active Fable/Claude lanes, and are exactly the sort of high-complexity architecture that should be specified before Fable disappears.
