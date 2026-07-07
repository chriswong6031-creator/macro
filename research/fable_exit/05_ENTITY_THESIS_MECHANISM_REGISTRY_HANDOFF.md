# Entity, Thesis, and Mechanism Registry Handoff

Prepared: 2026-07-07
Author: Codex
Status: research and freeze-spec only; do not build from this doc.
Audience: Fable, Neural Web implementers, Research Factory maintainers.

## Executive Decision

The repo has many strong local ID systems. It does not have a crosswalk that answers:

```text
Is this ticker, thesis, mechanism, claim, species, trial family, governance event,
and PR all the same idea wearing different clothes?
```

This registry is not another lobe and not another score. It is a connective substrate: a typed, inspectable graph that reduces duplicate research, hidden thesis concentration, and Fable token burn.

## What This Doc Does For Fable

This handoff:

- inventories existing ID schemes,
- defines the gap,
- proposes a registry schema,
- gives sample rows,
- sets namespace rules,
- lists non-goals and Fable freeze decisions.

The key choice for Fable: preserve local system IDs and build a crosswalk, rather than forcing a universal primary key.

## Existing Local ID Systems

### Entity Resolution

`engine/entity_resolver.py` already provides layered, context-only entity resolution:

- CN 6-digit exchange-code adjacency,
- curated CN aliases,
- generic-noun guard,
- US ticker token and alias scan,
- CUSIP map.

It is high-precision and leaf-only. It does not claim conceptual lineage.

### Cycle Entities

`engine/cycle_pattern/registry.py` uses IDs like:

```text
<family>:<native_id>
```

That is good local namespace practice. It does not connect to ticker/thesis/mechanism IDs outside cycle pattern.

### Thesis Layer

`engine/thesis_funnel.py` has states such as:

- `not_eligible`,
- `watch_for_thesis`,
- `thesis_candidate_shadow`.

It does not create an `active_thesis` authority path today. `engine/long_hold_clocks.py` adds `entry_clock` and `thesis_clock`, both display-only.

### Claims

`engine/qledger.py` creates deterministic claim IDs, scoped to entity/basket/sector/macro, with horizons and `check_by`. Current claim-accountability output shows:

- 9,069 claims,
- 2,815 grades,
- 146 claims with falsifiers,
- about 1.6% falsifier coverage.

That is a claim accountability layer, not a thesis/mechanism registry.

### Research Factory

`engine/research_factory/schema.py` carries:

- `candidate_id`,
- `mechanism`,
- `spec_ref`,
- `trial_accounting`,
- state transitions.

It owns orchestration, not domain identity.

### Species Registry

`engine/species_registry.py` / `data/species/registry.json` carry species IDs, versions, mechanisms, evidence stacks, deployment status, and rejection rules.

Species are not universal mechanisms. They are program-local hypotheses with lifecycle state.

### Governance

`engine/neuralweb/governance.py` emits `event_id = sha256[:16]` over event type, target, timestamp. This is a governance event ID, not a mechanism or thesis ID.

### Reflexivity / R-ORTH

`engine/reflexivity.py` and `data/reflexivity/n_eff_history.json` answer "same hidden trade?" for current board candidates. `site/factordata/reflexivity_overlay.json` is context-only and includes `same_thesis_groups`.

This catches duplicate exposure on a board. It does not provide cross-program lineage.

## Gap

`docs/SIGNAL_BUS.md` catalogs artifact topology and freshness. It does not catalog conceptual lineage.

Fable still has to manually answer:

- Which ticker aliases refer to the same entity?
- Which entities are the same thesis?
- Which claims and mechanisms are the same research idea?
- Which trial family already spent budget on this concept?
- Which governance ruling already touched this mechanism?
- Which PR implemented or killed a related idea?
- Which system owns the next decision?

## Proposed Artifact Contract

Doc-only freeze target:

```text
config/entity_thesis_mechanism_registry.yml
data/neuralweb/entity_thesis_mechanism_registry.json
docs/ENTITY_THESIS_MECHANISM_REGISTRY.md
engine/neuralweb/entity_thesis_mechanism_registry.py
scripts/build_entity_thesis_mechanism_registry.py
scripts/check_entity_thesis_registry.py
```

Do not build these from this handoff.

## Design Law

V1 should be deterministic, typed, and inspectable.

Do not start with embeddings. Do not let a fuzzy vector decide thesis identity. Use explicit joins and leave unknowns unknown.

## Schema V1

```yaml
schema: neuralweb.entity_thesis_mechanism.v1
registry_id: entity:US:NVDA
registry_type: entity|thesis|mechanism|claim_cluster|species_link
entity_refs:
  ticker: NVDA
  cusip: null
  cycle_entity_id: null
  resolver_source:
    - engine/entity_resolver.py
  market: US
  aliases:
    - NVIDIA
    - Nvidia
thesis_refs:
  thesis_family: ai_infra
  horizon_role: hold_thesis
  thesis_state: thesis_candidate_shadow
  thesis_clock_ref: site/stockdata/NVDA.json::thesis_clock
mechanism_refs:
  mechanism_id: ai_capex_acceleration
  spec_ref: null
  species_id: null
  species_version: null
  candidate_id: null
claim_refs:
  claim_ids: []
  claim_family: null
  horizons: []
  check_by: []
  falsifier_coverage: null
trial_refs:
  trial_family: null
  config_hashes: []
  declared_budget_n: null
  effective_n_policy: null
governance_refs:
  event_ids: []
  ruling_refs: []
  source_prs: []
clock_refs:
  check_by: []
  come_back_on: []
  fdr_batch_due: []
  freshness_sla_hours: null
authority:
  role: display_only
  can_gate: false
  can_rank: false
  can_size: false
source_paths:
  - engine/entity_resolver.py
  - engine/thesis_funnel.py
last_seen_at: "2026-07-07"
notes: "Crosswalk only; local systems remain authoritative."
```

## Namespace Rules

Recommended prefix rules:

| Namespace | Meaning |
|---|---|
| `entity:US:NVDA` | Public market entity. |
| `entity:CN:300750.SZ` | China A-share entity. |
| `cycle:sector:technology` | Cycle registry entity. |
| `thesis:ai_infra` | Human-readable thesis family. |
| `mechanism:A15_WASHOUT_OPP_OUT_2NODE` | Mechanism-level research idea. |
| `species:S1@1.0` | Species registry row/version. |
| `claim:<qledger_id>` | Qledger claim. |
| `rf:<candidate_id>` | Research Factory candidate. |
| `gov:<event_id>` | Governance event. |

Rule: do not rename source IDs. The registry maps them.

## Sample Rows

### `entity:US:NVDA`

```yaml
registry_id: entity:US:NVDA
registry_type: entity
entity_refs:
  ticker: NVDA
  resolver_source:
    - engine/entity_resolver.py
thesis_refs:
  thesis_family: ai_infra
  thesis_state: null_or_shadow_only
mechanism_refs:
  species_id: null
claim_refs:
  claim_ids: []
authority:
  role: display_only
  can_rank: false
note: >
  Link qledger claim refs only when the claim rows explicitly identify NVDA.
  Do not invent species or active thesis links when source rows are null.
```

### `mechanism:A15_WASHOUT_OPP_OUT_2NODE`

```yaml
registry_id: mechanism:A15_WASHOUT_OPP_OUT_2NODE
registry_type: mechanism
mechanism_refs:
  candidate_id: rf-20260706-adopt-a15_washout_opp_out_2node
  mechanism_id: washout_opp_out_2node
trial_refs:
  trial_family: research_factory_or_oracle_source
governance_refs:
  source_prs:
    - 1629
  ruling_refs:
    - RF-5
    - RF-9
authority:
  role: display_only
note: >
  Paper state is a Research Factory / operator decision. Registry does not promote.
```

### `species:S1@1.0`

```yaml
registry_id: species:S1@1.0
registry_type: species_link
mechanism_refs:
  species_id: S1
  species_version: "1.0"
source_paths:
  - data/species/registry.json
authority:
  role: display_only
note: >
  Carries evidence stack and rejection rules from species registry.
  Deployment status is copied as context, never converted into a new authority path.
```

### `thesis:ai_infra`

```yaml
registry_id: thesis:ai_infra
registry_type: thesis
entity_refs:
  tickers:
    - NVDA
    - AVGO
    - VRT
thesis_refs:
  thesis_family: ai_infra
  source: reflexivity same_thesis_groups + baskets + operator labels
authority:
  role: display_only
note: >
  V1 can say "these names express a shared thesis"; it cannot say the thesis is good,
  rank the names, or size the book.
```

## Build Inputs

V1 should read:

- `engine/entity_resolver.py` maps,
- `data/species/registry.json`,
- `data/experiments/registry_seed.json`,
- `data/trial_ledger.jsonl`,
- `data/neuralweb/governance.jsonl`,
- `data/governance/claim_accountability.json`,
- `site/factordata/reflexivity_overlay.json`,
- `data/reflexivity/n_eff_history.json`,
- `data/research/thesis_funnel_states_manifest.json`,
- `config/synapse.yml`,
- Research Factory candidates/transitions when present.

## What The Registry Unlocks

### For Case Law

Ruling graph can ask: "does this proposal touch an existing mechanism?"

### For Research Factory

Challenger packets can include:

- duplicate mechanism candidates,
- prior trial family,
- related species,
- existing claim IDs,
- unresolved clocks.

### For Mastermind Feedback

Private held-book feedback can attach `thesis_id` and `mechanism_id` without exposing public position details.

### For R-ORTH / Reflexivity

Board duplicate exposure can graduate from pairwise current-board similarity to a historical thesis graph, still display-only.

### For Evidence Clock

Clock rows can group by mechanism/thesis, not only by artifact path.

## Non-Goals

- No embeddings in v1.
- No new score.
- No ranking.
- No sizing.
- No lobe charter.
- No new thesis authority.
- No qledger semantic changes.
- No replacement of Signal Bus.
- No forced universal primary key.
- No invented links when source IDs are absent.

## Fable Freeze Decisions

Fable should decide:

1. Should V1 be a crosswalk only, with local IDs preserved? Recommended: yes.
2. What are legal `registry_type` values?
3. Can human-curated `thesis_family` rows exist in V1?
4. What evidence is required before two mechanisms are declared the same?
5. Can private Mastermind `thesis_id` values be referenced in public summaries? Recommended: no, unless anonymized.
6. Which source wins when two systems disagree on entity identity?
7. Should registry rows enter Signal Bus as `infrastructure` or stay doc/internal initially?
8. What fields are allowed in public `site/` copies?

## Likely Objections And Answers

### "This duplicates Signal Bus."

Signal Bus maps artifact topology. This maps conceptual lineage.

### "This duplicates R-ORTH."

R-ORTH measures independence/overlap. This gives IDs and source links so R-ORTH, Research Factory, and case law can talk about the same mechanism.

### "IDs are messy."

Preserve the mess locally. Build aliases and provenance instead of forcing a brittle canonical ID.

### "This could become subjective."

Start deterministic. Human-curated thesis labels should carry source refs and confidence/state, not authority.

## V1 Success Test

A future proposal says:

```text
Test washout-outside-opportunity as a new Oracle reversion compound and entry-stack setup.
```

The registry should answer:

```text
Mechanism match: A15_WASHOUT_OPP_OUT_2NODE.
Prior RF status: paper.
Related PR: #1629.
Related trial family: existing Oracle/RF source.
Allowed next step: inspect paper clock or scoped follow-up.
Forbidden: treat as net-new family without citing prior mechanism.
```

That is the registry paying rent.
