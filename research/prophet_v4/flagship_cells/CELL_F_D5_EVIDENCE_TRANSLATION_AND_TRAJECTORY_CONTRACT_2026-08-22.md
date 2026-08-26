# Cell F — D5 Evidence Translation & Trajectory Contract

**Status:** ARCHITECTURE FROZEN; runtime vertical BLOCKED on canonical V4 candidate episode B1  
**Linear:** MAS-122, child of MAS-116  
**Chairman authorization:** 2026-08-22 Cell F directive  
**Skillpack:** `mastermind.sol_skillpack.v1` at protected `mastermindx-market-intelligence/Mastermind@e1101eb2c1f17d801d480ded497b3fc1bb0ef18b`  
**Macro archaeology pin:** `9f373fd9553603192f495260b2100c16c177023b` (only change after the deeper census pin `f6a16bc24b62b3655d2662dba2018d6e83ee2e18` was a marketing-outbox append)  
**Canonical D5 schema name:** `prophet.intelligence_vector/v1`  
**Authority:** evidence/context only; all rank/gate/size/origination/ENTRY_OPEN flags false

---

## 0. Executive ruling

The preliminary architecture survives, with two material amendments.

1. **Context Vector survives intact as the zero-authority, append-only, point-in-time full-universe historical/research substrate.** D5 v1 does **not** widen or repurpose `engine/us_context_vector.py`. It may point to an exact Context Vector observation when one exists, but it does not migrate the wide nightly row into an episode envelope.
2. **D5 is an episode-scoped typed decision-time evidence read-model, not a warehouse.** It carries small typed observations, explicit clocks/state/rights/lineage, and references to specialist-owned source objects. It does not copy documents, transcripts, full workspaces, option chains, Market Memory feature receipts, or raw specialist payloads.
3. **Specialist owners remain source truth.** D5 may mechanically adapt a source-owned field into the common envelope. It may not originate domain facts, statistical measures, novelty metrics, decay models, source corrections, source identity, or domain authority.
4. **Semantic heads are grouping only.** They answer “what research/product question does this evidence illuminate?” They do not aggregate, weight, vote, rank, or imply independence.
5. **Fusion members remain separately registered rank inputs.** D5 evidence-family identity is not a Fusion family and does not imply a Fusion member. Existing F1–F8 are rank-budget / anti-double-count groupings owned by Conditional Fusion. Any D5-to-Fusion binding is an explicit reference to an already registered member/version; default is none.
6. **Evidence-root identity and economic dependence are different.** Two different first-party documents may be two evidence roots and still express one economic shock. D5 never calls distinct roots “independent” by default.
7. **Missing never becomes zero, false, neutral, or no-signal.** Measured neutral requires positive evidence that the owner actually measured the applicable, covered object under a named neutral definition.
8. **Corrections append; decision-time belief does not rewrite.** Later corrections are linked beside the original decision snapshot. They may explain what is now known but may not alter what D5 says the episode knew at the decision cut.
9. **Trajectory is family-native and sparse.** `level/delta/acceleration/novelty/persistence/decay` exist only where a specialist contract gives them a real economic meaning and comparable cadence. D5 does not manufacture six generic columns for every family.
10. **D5 never directly changes deterministic `ENTRY_OPEN`.** It also carries no overall score, family score, confidence blend, evidence count, or “number of agreeing families” proxy.

The old D1/D5 readiness suggestion to “extend `us_context_vector.py`” is therefore **superseded as an implementation tactic**, not as a rejection of Context Vector. The Context Vector is reused more strongly by preserving its current contract and referencing it.

---

## 1. Why Context Vector must remain a separate substrate

Current code proves that Context Vector is already a durable shared machine contract:

- it appends one nightly row for the full analyzed universe, including ineligible names;
- it keeps first on `(stamp_date, ticker, board_definition)` and never retroactively backfills;
- schema union adds future columns as null on earlier rows;
- null means unmeasured, never false;
- it is explicitly zero-authority and contains no forward outcome labels;
- its broad row is consumed by Prophet grading/races, candidate-lane machinery, board/rank code, Neural Web/context paths, and Government Revenue;
- Government Revenue reads a **narrow projection** of the Context Vector at a procurement event’s `known_at` to reconstruct what Prophet’s market context looked like then, and gives missing/stale/abstained states rather than zeros;
- generic Context Snapshot flattening already produced a real containment incident: entitlement-gated forensics bodies reached the committed parquet until `STAMP_FORBIDDEN_COLUMNS` and non-scalar classification were added.

Those facts make “add all D5 semantics to the same wide parquet” the wrong abstraction. Episode lineage, economic dependence, correction views, rights policies, variable-cardinality source references, and family-native trajectory structures would turn the existing fixed nightly feature tape into a second evidence warehouse while making every current reader inherit semantics it does not need.

**Ruling:** Context Vector is **REUSE_AS_PIT_HISTORY_SUBSTRATE**. D5 v1 adds **zero columns** to it.

---

## 2. Capability ledger at freeze

| Capability | Status | Cell F ruling |
|---|---|---|
| US Context Vector PIT full-universe history | `PROVEN_LIVE` | Reuse unchanged; reference exact observations only |
| Conditional Fusion C1 cross-family ranker | `PROVEN_LIVE` | Separate authority plane; no D5 weight/rank changes |
| `prophet.candidate_episode/v1` frozen semantic contract | `SPEC_ONLY` | Mandatory D5 parent identity; implementation not found on current main |
| `prophet.intelligence_vector/v1` | `SPEC_ONLY` before this freeze | Contract frozen here; no runtime object yet |
| Earnings `event_workspace.v1` | `PROVEN_LIVE` source owner | Preferred first adapter after B1 exists |
| Capital Structure `capital_structure.event.v1` + immutable lineage | `PROVEN_LIVE` source spine; richer issuer twin partial | Adapt existing event facts only; no invented runway/capacity |
| GMI canonical ThemeState | `NOT_BUILT` / sequencing active | Do not substitute legacy Context Vector theme fields |
| Options EOD intelligence | `BUILT_NOT_PROVEN` globally | Current daily-current coverage about 39/375; covered names may be measured, others `NOT_COVERED` |
| Market Memory `market_memory.as_known_at.v1` | `PARTIAL` / prospective activation | Reference immutable context; do not copy its 18 feature receipts |
| Dislocation source-integrity research repair | `PARTIAL`, held in #6258 | No production D5 dislocation claim; no prices/outcomes/rank imported |
| Defense D3 temporal change truth | `PROVEN_LIVE` | Strong dual-/multi-clock and correction reference family |
| Bio Trial Milestone projection | `BUILT_NOT_PROVEN` | Source facts exist; P1-1 product acceptance still blocked by desktop clipping |

---

## 3. Namespace separation — three concepts, three identifiers

### 3.1 Evidence family

`evidence_family_id` names a **source-owner/native-method family**, for example:

- `earnings.event`
- `capital_structure.event`
- `options.eod_positioning`
- `market_memory.analogue_context`
- `theme.theme_state`
- `dislocation.incorporation_state`
- `defense.procurement_change`
- `biocatalyst.trial_milestone`

It answers: **which specialist owns the fact and native method?**

The generic field name `family_id` is forbidden in D5 because Conditional Fusion already uses “family” for a different job.

### 3.2 Semantic head

`semantic_head_ids[]` is a controlled grouping projection such as `event_expectation`, `capital_supply`, `positioning_volatility`, `theme_transmission`, `historical_analogue`, `incorporation_gap`, `mission_contract`, or `clinical_timing`.

A semantic head:

- can group multiple evidence families;
- may be used for product sections and research slicing;
- contains no score or aggregate value;
- cannot establish economic independence;
- cannot map to a Fusion family by naming convention.

### 3.3 Fusion binding

A `fusion_binding` is valid only when it names an **already registered** Conditional Fusion member and registry/version. It carries the existing `fusion_family_id` (`F1`–`F8` domain) and member ID exactly as Fusion owns them.

D5 never creates, registers, weights, promotes, or infers a Fusion member. Empty `fusion_bindings[]` is the default and is the correct state for the first adapter vertical.

---

## 4. Identity grain

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A9.** `episode_ref` MUST additionally pin the B1
> `generation_id` (`peg:<64 hex>`) that was HEAD at adaptation time. `episode_id` alone cannot
> pin an immutable parent.

D5’s grain is exactly:

> **one canonical V4 candidate episode × one decision cut × one adapter-set version**.

D5 does not mint candidate episodes.

Required parent reference:

```text
episode_ref:
  schema: prophet.candidate_episode/v1
  episode_id: <owner-issued>
  identity_ref: <episode-owned canonical Data OS identity reference>
```

D5 may echo a minimal stable identity join key only when the episode contract itself supplies it. It must not create a ticker/CIK/security crosswalk.

### 4.1 Entry Radar live episodes are not a substitute

Current main contains `mastermind.live_entry_episode.v1` in `engine/entry_radar/live_ledger.py`. Its identity is a live-detector lifecycle address over `(ticker, detector_id, variant, first_armed_at)`, its state is operational/re-derivable, and its durable evidence is owned elsewhere. It is useful source/context for its own Radar program but is **not** silently reclassified as the frozen V4 candidate-episode contract.

### 4.2 Context Vector reference

An optional `context_vector_ref` may point to the pre-existing nightly row:

```text
context_vector_ref:
  stamp_date
  ticker
  board_definition
  tier                 # descriptive; not part of Context Vector dedupe identity
  selection_era
```

The authoritative Context Vector key remains `(stamp_date, ticker, board_definition)`. A missing same-cut row stays null; D5 never backfills one.

---

## 5. Top-level `prophet.intelligence_vector/v1` contract

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A8.** REQUIRED `decision_cut` is bound to clocks B1
> already owns (`opened_at`, `opened_session`, the `known_at`-bearing event stream). D5 mints
> no clock. A builder may NOT synthesise a cut from any other source.

The v1 semantic payload is closed to these concepts. A future implementation may choose JSON/typed Python internally, but serialization may not change their meaning.

| Field | Required | Meaning |
|---|---:|---|
| `schema` | yes | constant `prophet.intelligence_vector/v1` |
| `projection_id` | yes | content-addressed ID over the semantic payload, excluding transport-only assembly metadata; no lifecycle registry |
| `episode_ref` | yes | canonical V4 candidate episode reference; never D5-minted |
| `decision_cut` | yes | episode-owned decision/session/tradability references used to establish PIT admissibility |
| `adapter_set_version` | yes | exact set/version of adapters used |
| `context_vector_ref` | no | exact existing Context Vector observation if one lawfully exists |
| `evidence_families[]` | yes | zero or more typed family envelopes; absence of families is legal |
| `economic_dependence_groups[]` | yes | known/common economic-information dependence; never an independence score |
| `semantic_heads[]` | yes | grouping-only projection over family/evidence IDs |
| `fusion_bindings[]` | yes | explicit existing Fusion registrations only; default `[]` |
| `authority` | yes | all-false D5 authority block |

**Forbidden top-level fields:** `score`, `opportunity_score`, `confidence`, `conviction`, `family_score`, `head_score`, `evidence_count_score`, `rank`, `weight`, `entry_open_delta`, `size`, or any synonym that combines evidence strength.

`projection_id` is a receipt alias, not a second source identity. It is deterministic from the canonical D5 semantic payload and has no mutable registry, correction lifecycle, or owner semantics of its own.

---

## 6. Family envelope

Each member of `evidence_families[]` is closed to this conceptual shape:

```text
family_projection_id
evidence_family_id
family_contract_version
owner_ref
subject_binding
semantic_head_ids[]
method_version
point_in_time
applicability
coverage
freshness
rights
identity_state
quality
source_refs[]
evidence_roots[]
observations[]
trajectory
correction
calibration
fusion_bindings[]
authority
```

### 6.1 Owner and method

`owner_ref` names the specialist workstream/contract/schema that is authoritative. `method_version` names the source-owner method when the observation is derived.

Allowed observation method classes:

- `OWNER_OBSERVED_FACT`
- `OWNER_DETERMINISTIC_DERIVATION`
- `OWNER_STATISTICAL_ESTIMATE`
- `OWNER_MODEL_OUTPUT`
- `ADAPTER_MECHANICAL_PROJECTION`

Cell F adapters may originate only `ADAPTER_MECHANICAL_PROJECTION`: naming, unit-preserving shape conversion, allowlisted field selection, and exact reference wiring. Domain calculations stay with the source owner.

### 6.2 Subject binding

A family may naturally bind to issuer/security, event, theme, program/contract, trial, market/session, or other source-native subjects. D5 records how that subject maps to the candidate episode; it does not force every source into a ticker row.

Binding states:

- `RESOLVED`
- `AMBIGUOUS`
- `UNRESOLVED`
- `NOT_APPLICABLE`

No guessed binding is permitted.

---

## 7. Clock contract

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A7 and A8.** The abstract clock names below bind to
> owner-native field names via the normative binding table in A7; do not guess the mapping.
> `tradable_at` is `NOT_ASSERTED` until V4-B4 exists.

Six specialist clocks remain distinct, plus the episode decision/tradability clocks. No clock may substitute for another.

| Clock | Meaning | Named-null law |
|---|---|---|
| `source_effective_at` | when the fact/action/state takes effect in the source/economy | may be date/instant/interval or explicitly not asserted |
| `source_published_at` | when the source published that version | never substitute filing date, collector time, effective time, or `known_at` |
| `known_at` | earliest instant the **source owner** can assert this exact version was knowable under its contract | not automatically equal to source publication |
| `captured_at` | when Mastermind actually acquired/verified this version | required for a claim about what the live system itself knew |
| `computed_at` | when the specialist computed its derived state | not source publication and not decision time |
| `corrected_at` | when a later correction/revision became known/captured | never rewrites the earlier decision version |
| `decision_at` | candidate-episode decision cut | episode-owned |
| `tradable_at` | first tradable instant/availability after decision semantics | episode/availability-owned |

A clock is a typed assertion, not an unqualified timestamp:

```text
state: ASSERTED | NOT_ASSERTED | NOT_APPLICABLE | UNKNOWN
value: <instant/date> | null
interval: {start, end} | null
precision: INSTANT | DAY | MONTH | QUARTER | YEAR | INTERVAL | UNKNOWN
basis: <owner-native reason/method>
source_ref_ids[]
```

This admits Bio’s month/year intervals without inventing point dates and Defense’s deliberately named-null `source_published_at` without substituting `known_at`.

### 7.1 PIT basis and decision admissibility

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A7 (BLOCKING repair).** Labels are not an access rule.
> For the Earnings family, decision-time observations may be read ONLY through
> `read_event_source_revisions` / `read_all_event_source_revisions`, filtered
> `source_available_at <= decision_cut`, latest-lawful-wins, re-sorted by `source_available_at`.
> `read_event_workspace` is FORBIDDEN in any decision-time path — it resolves the CURRENT
> generation and will pass this section's stated test while shipping post-cut corrected values.

`point_in_time.basis` reuses the proven Market Memory distinctions where applicable:

- `LIVE_CAPTURED`
- `SOURCE_VINTAGE`
- `PUBLIC_RECONSTRUCTED`
- `RECOMPUTED_HISTORY`
- `CURRENT_SNAPSHOT_BACKFILL`
- `UNKNOWN`

For **production decision-time D5**, an observation is system-known only if the owner can prove the version was actually captured/available to the running system by the decision cut. Public reconstruction or current-snapshot backfill may be valid research context, but it is labeled `RESEARCH_ONLY_RECONSTRUCTION` and never masquerades as live knowledge.

`decision_admissibility`:

- `ADMISSIBLE`
- `RESEARCH_ONLY_RECONSTRUCTION`
- `AFTER_DECISION_CUT`
- `UNVERIFIABLE`

---

## 8. Applicability, coverage, freshness, rights and missingness

These are orthogonal. D5 must not flatten them into one overloaded nullable value.

### 8.1 Family axes

`applicability.state`:

- `APPLICABLE`
- `NOT_APPLICABLE`
- `UNKNOWN`

`coverage.state`:

- `COVERED`
- `PARTIAL`
- `NOT_COVERED`
- `UNKNOWN`

Coverage may carry owner-native numerator/denominator and basis when that is honest. It never fabricates a denominator.

`freshness.state`:

- `CURRENT`
- `STALE`
- `EXPIRED`
- `UNKNOWN`

Freshness carries owner-native source watermark/SLA references, not a D5-wide hard-coded age.

`rights.state`:

- `ALLOWED`
- `DERIVED_ONLY`
- `BLOCKED`
- `UNKNOWN`

`rights.profile_ref` must point to the source owner’s rights policy/profile when one exists. D5 does not infer legal permission. Raw/source text is denied unless the owner explicitly exposes it as display-safe.

`identity_state`:

- `RESOLVED`
- `AMBIGUOUS`
- `UNRESOLVED`
- `NOT_APPLICABLE`

### 8.2 Observation value state

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A10.** This vocabulary is a superset ACROSS families,
> not a per-family menu. A10 classifies all fifteen for Earnings v1: three owner-backed, one
> partial, six D5-originated states about D5's own access or join, and five not mintable at
> all. `absence_reasons[]` carries only §8.2 members — `AFTER_DECISION_CUT` is a
> `decision_admissibility` value, `MEASURED_NEUTRAL` is a `value_state`, and owner warning
> strings pass through a separate field.

Every `observations[]` row declares:

- `value_state = PRESENT | MEASURED_NEUTRAL | ABSENT`
- `absence_reasons[]` when absent
- `neutral_definition_ref` when measured neutral

Allowed typed absence reasons:

- `NOT_APPLICABLE`
- `NOT_COVERED`
- `SOURCE_UNAVAILABLE`
- `STALE`
- `RIGHTS_BLOCKED`
- `IDENTITY_UNRESOLVED`
- `INSUFFICIENT_HISTORY`
- `UNESTIMABLE`
- `ACCRUING`
- `PRODUCER_DEGRADED`
- `CONFLICTED`
- `CORRECTION_PENDING`
- `NOT_CAPTURED_AT_DECISION`
- `NOT_COMPUTED`
- `UNKNOWN`

Multiple reasons may be true. There is no precedence that hides a second material failure state.

### 8.3 Measured-neutral law

`MEASURED_NEUTRAL` is a positive epistemic claim. It requires all of:

1. applicable subject;
2. covered source/object;
3. lawful and sufficiently fresh input;
4. owner method actually executed;
5. explicit owner-native neutral definition.

Examples:

- a complete eligible Options symbol that the owner classified `NO_SIGNAL` may be measured neutral;
- `theme_membership_count = 0` is measured only when the membership source loaded; if the file/artifact was absent, it is not zero and not neutral;
- a missing GEX row, unlicensed consensus, or unjoined company identity is never neutral.

---

## 9. Source references: what D5 references versus copies

### 9.1 `source_refs[]`

A source reference is an allowlisted pointer, not an opaque payload:

```text
source_ref_id
owner_namespace
object_schema
object_id
version_or_generation
receipt_id?          # only if owner exposes it
content_hash?        # only if owner exposes it to this consumer
field_paths[]?       # exact fields adapted
render_policy        # INTERNAL_ONLY | DERIVED_ONLY | DISPLAY_SAFE
```

D5 cannot require a source owner to reveal a private path, object key, secret receipt, or non-public hash merely to fit the envelope.

### 9.2 Copy rule

D5 may copy only:

- small source-owned scalar/enum/range/interval observations;
- units and native method/version IDs;
- typed absence/quality/reason codes;
- source-owned clocks;
- minimal structured explanation facts already derivable from those same allowed values.

D5 references rather than copies:

- filings, transcripts, press releases, trial records and source text;
- full `event_workspace.v1` packets and claim arrays;
- Capital Structure manifests/event histories/large lineages;
- option chains, surfaces and raw flow tables;
- Market Memory’s full 18-feature context/receipt set;
- Defense full workspaces/change tapes;
- Bio full registry payload/history;
- GMI graph bodies;
- Dislocation source packets/K-packets;
- any paid/restricted body.

D5 rejects entirely:

- generic owner composite scores used as a shortcut for evidence;
- owner rank/priority/conviction fields unless an explicit future product need references them **outside** evidence semantics;
- generated prose summaries as facts;
- arbitrary dict/list spreading from a source owner into the envelope.

---

## 10. Evidence roots versus economic dependence

### 10.1 Evidence root

An `evidence_root_id` is a deterministic **D5 alias of an owner source-version reference**, not a new source-of-truth registry. It answers:

> Which exact source object/version(s) ultimately support this observation?

The alias is content-addressed from the canonical `source_ref` identity. If the owner already exposes a stable receipt/object ID, D5 retains it inside the root reference rather than replacing it.

Root types may include `DOCUMENT_VERSION`, `EVENT_VERSION`, `OWNER_PACKET`, `SOURCE_SNAPSHOT`, `MARKET_SESSION`, `REGISTRY_RECORD`, and `OTHER`.

A derived observation may have multiple evidence roots.

### 10.2 Economic dependence group

`economic_dependence_groups[]` answers a different question:

> Which observations may be manifestations of the same underlying economic information/shock/mechanism and therefore must not be counted as independent corroboration merely because their files/providers differ?

Each group has:

```text
dependence_group_id
relation: SAME_ECONOMIC_DRIVER | COMMON_INFORMATION_ORIGIN | MECHANICALLY_DERIVED | UNKNOWN_OVERLAP
member_observation_refs[]
basis: OWNER_ASSERTED | CONTRACT_RULE | EVAL_ASSERTED | UNKNOWN
basis_refs[]
```

Rules:

- two evidence roots may belong to one dependence group;
- one evidence root may support multiple derived observations in one dependence group;
- distinct providers do not prove distinct economics;
- absence of a common group does **not** prove independence;
- D5 does not mint an `independent=true` flag. Explicit independence, if later needed for rank calibration, belongs to Eval/Fusion and must be earned.

Reference example: an earnings press release and an 8-K covering the same quarterly result are distinct source roots but normally one economic-information group. A Defense award record and an issuer filing describing that same award are likewise not two independent shocks.

---

## 11. Observation and explanation-fact contract

An observation is a small source-native fact:

```text
observation_id
native_metric_id
value_state
value                 # scalar/enum/range/interval only; null when absent
units
method_class
method_version
source_ref_ids[]
evidence_root_ids[]
economic_dependence_group_ids[]
clock_overrides?      # only when observation differs from family default
quality_flags[]
absence_reasons[]
neutral_definition_ref?
```

`explanation_facts[]` are deterministic, source-bound render facts pointing back to observation/source/root IDs. They can say things such as “effective 2026-05-12; first captured/known 2026-08-12; source publication time not asserted.” They cannot be free-running LLM summaries.

A future model-generated narrative can consume D5, but its output remains a separate model artifact with prompt/model/source citations and never becomes a D5 fact merely by being useful prose.

---

## 12. Quality and calibration

D5 carries quality evidence without manufacturing one confidence scalar.

`quality` may carry source-owner flags such as degraded provider, partial coverage, identity gap, late arrival, imputation, stale source, or conflict. It does not combine them numerically.

`calibration.state`:

- `NOT_APPLICABLE` — deterministic source fact where predictive calibration is the wrong concept;
- `UNREGISTERED` — statistical/model observation has no accepted calibration record;
- `ACCRUING` — prospective evaluation is accumulating;
- `REGISTERED` — an external Eval/Q registration exists.

`calibration.registration_ref` points to the evaluator/registry. D5 does not convert registration into rank authority.

Every family and top-level envelope repeats an all-false authority block:

```text
can_rank: false
can_gate: false
can_size: false
can_originate_signal: false
can_change_entry_open: false
can_change_execution: false
```

A separately registered `fusion_binding` may tell a consumer that **another plane** has earned bounded rank authority for a particular member. It does not mutate the D5 authority block.

---

## 13. Correction contract: contemporaneous belief and final truth coexist

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A7 clause 4 and A10 clause 3.** The `UNESTIMABLE` /
> `CORRECTION_PENDING` escape is reachable ONLY via the revision-chain reader; under
> `read_event_workspace` a builder cannot discover that a correction exists, so this section
> is dead law without A7.

Each family carries:

```text
correction:
  state_at_decision: NONE | PENDING | CONFLICTED
  decision_version_ref_ids[]
  later_correction_ref_ids[]
  current_state: CURRENT | CORRECTED | RETRACTED | CONFLICTED | UNKNOWN
```

Rules:

1. `decision_version_ref_ids[]` are the versions actually admissible at the decision cut.
2. `later_correction_ref_ids[]` may be discovered later and are audit/context links only.
3. Rebuilding D5 after a correction may add the later-correction link, but it must not replace the decision observations with the corrected values.
4. A research resolver may explicitly request a **final-corrected view** by traversing owner corrections; that is a research view over the immutable decision envelope, not a rewrite of the envelope.
5. If the owner cannot reconstruct version history safely, historical values become `UNESTIMABLE` / `CORRECTION_PENDING` rather than silently using today’s corrected snapshot.

This mirrors the estate’s strongest existing law: Defense successors append and preserve predecessor clocks/receipts/event IDs; Capital Structure versions/edges are immutable; Bio keeps revision lineage.

---

## 14. Trajectory contract — sparse, native, comparable

`trajectory` is optional per family and has no fixed six-column row. It contains only dimensions the source owner can define honestly:

```text
trajectory:
  state: AVAILABLE | PARTIAL | NOT_APPLICABLE | INSUFFICIENT_HISTORY | UNESTIMABLE | ACCRUING
  dimensions[]:
    dimension: LEVEL | DELTA | ACCELERATION | NOVELTY | PERSISTENCE | DECAY
    state: MEASURED | MEASURED_NEUTRAL | NOT_APPLICABLE | INSUFFICIENT_HISTORY | UNESTIMABLE | ACCRUING
    native_metric_id
    value
    units
    window
    cadence
    method_version
    reference_observation_ids[]
    source_ref_ids[]
```

### 14.1 Hard method law

D5 v1 **transports** source-owner trajectory semantics. It does not invent a universal formula for acceleration, novelty, persistence, or decay.

A dimension is lawful only when:

- the underlying quantity is semantically comparable across the referenced observations;
- cadence/window is explicit;
- units/basis are stable or conversion is deterministic and declared;
- missing observations do not become zero;
- corrections and late arrivals are handled by the source owner’s version law;
- the dimension itself has no hidden rank/weight semantics.

### 14.2 Family-specific meaning

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A12.** The Earnings row overstates current capability:
> `metric_delta.v1` ships `basis_match: False` (refused outright in code) and the guidance
> status enum is documented but unenforced, with only `"introduced"` ever minted.

| Family | Level | Delta | Acceleration | Novelty | Persistence | Decay |
|---|---|---|---|---|---|---|
| Theme | meaningful only after canonical GMI ThemeState has stable cadence | possible owner-native state change | possible only with fixed comparable cadence | possible owner-native emergence/rarity | meaningful for sustained theme state | meaningful only if owner defines state cooling/expiry | 
| Earnings | guidance/estimate/event facts as owner exposes | revision/surprise/change when basis-matched | usually N/A for one event; estimate-revision velocity only if owner defines | possible claim/event novelty if owner defines | post-event revisions/claim persistence if owner defines | event freshness/expectation decay if owner defines | 
| Capital Structure | current filing/event/capacity state when source owner has it | amendment/issuance/share-count change | usually N/A until owner defines financing cadence | new instrument/action if owner defines | active shelf/ATM/instrument life | expiry/effectiveness only where source defines | 
| Options | IV/skew/OI/surface state on covered comparable session | lawful cross-session change | only fixed-cadence comparable series | owner-defined unusual surface/positioning | multi-session persistence | expiry/freshness-aware owner state | 
| Market Memory | analogue/support state | generally N/A | N/A | owner-defined out-of-support distance may qualify | case-support persistence if owner defines | generally N/A | 
| Dislocation | owner-computed incorporation/residual state | owner-computed change | only owner-defined | event/incorporation novelty if owner defines | unresolved-gap persistence | closure/incorporation decay if owner defines | 
| Defense | award/program/change state | receipt-bound `changed_fields` delta | N/A by default | new/successor event state if owner defines | program/contract continuity if owner defines | only source-defined expiry/window | 
| Bio | milestone interval/status | registry revision before→after | N/A by default | new milestone/revision if owner defines | schedule/status persistence | only source-defined staleness/expiry | 

No family is defective because a dimension is `NOT_APPLICABLE`.

---

## 15. Context Vector field-by-field disposition matrix

Disposition vocabulary:

- `REUSE_REF` — D5 may reference the exact historical row/key; field stays owned by Context Vector/producer.
- `HISTORY_ONLY` — useful research context but not current specialist D5 evidence by existence alone.
- `SUPERSEDE_CURRENT_D5` — retain forever in Context Vector, but current D5 must use the named specialist owner instead.
- `REJECT_D5_EVIDENCE` — never treat as D5 evidence/family observation.
- `EXTEND_CONTEXT_VECTOR` — **no current fields**; D5 v1 adds none.

| Current Context Vector field(s) | Disposition | Reason / D5 route |
|---|---|---|
| `stamp_date`, `ticker`, `board_definition`, `tier`, `selection_era`, `anchor_era` | `REUSE_REF` | exact historical observation reference only; episode identity still comes from B1/Data OS |
| `name`, `sector` | `HISTORY_ONLY` | descriptive snapshot; current identity/issuer semantics come from canonical identity owner |
| `eligible`, `buyable`, `lane`, `tier_cascade`, `tier_sub`, `ticks`, `bars_to_cross`, `fresh_bars`, `gate_weight`, `gate_state`, `gate_reason`, `gate_provisional`, `htf_s1`, `htf_s2`, `near_miss_reason`, `signal_asof` | `REJECT_D5_EVIDENCE` | candidate/admission/gate state belongs to candidate episode / deterministic lane, not evidence family |
| `young_history`, `history_bars` | `HISTORY_ONLY` | useful data-readiness context; a specialist may separately expose `INSUFFICIENT_HISTORY` without copying these as evidence |
| `stage`, `alpha`, `alpha_percentile`, `prophet_score`, `score_rank`, `display_rank`, `featured` | `REJECT_D5_EVIDENCE` | board/rank outputs would create self-feedback and a second rank plane |
| `prophet_{signal,entry,edge,runway,quality}` and `*_points` | `REJECT_D5_EVIDENCE` | existing/current or historical ranker legs, not specialist source truth |
| `prophet_shadow_definition`, `prophet_shadow_score`, `prophet_shadow_score_rank`, `prophet_shadow_{signal,entry,edge,runway,quality}`, `*_points` | `REJECT_D5_EVIDENCE` | W3/ranker-race historical substrate only; never D5 evidence |
| `pool_definition`, `pool_lane`, `pool_lane_reasons`, `pool_headline_reason`, `pool_rank`, `pool_display_rank`, `pool_in_buy_lane`, `pool_admission_class`, `pool_open_plan` | `REJECT_D5_EVIDENCE` | display/candidate-pool lifecycle; episode/availability owns current state |
| `theme_membership_count`, `theme_membership_ids`, `theme_primary_id`, `theme_primary_name`, `theme_heat_rank`, `theme_label`, `theme_reco`, `theme_score`, `theme_bull_days`, `theme_clean_entry`, `relay_count_3d`, `relay_position`, `relay_members_covered`, `relay_basket_id`, `foresight_stage` | `SUPERSEDE_CURRENT_D5` | preserve legacy PIT research; canonical current D5 Theme waits for GMI ThemeState. Never use legacy `theme_score` as substitute |
| `days_to_report`, `reports_within_7`, `post_earnings_move_pct`, `post_earnings_sessions_since`, `earnings_stale`, `in_blackout`, `eightk_recent_days` | `SUPERSEDE_CURRENT_D5` | preserve history; current earnings family adapts EIOS/company-intelligence owner, not the legacy flattened event helper |
| `turnover_pctile_20d`, `turnover_window_20d`, `turnover_pctile_60d`, `mdv20_usd` | `HISTORY_ONLY` | descriptive market/liquidity context; no generic D5 flow family is created from their presence |
| `regime_dispersion_state`, `regime_gate_go`, `regime_market_quad`, `regime_quad_name`, `regime_vol_regime` | `HISTORY_ONLY` | may be referenced for studies; a future current D5 macro family requires its actual specialist owner contract |
| `ext_z`, `antichase_shadow_blocked` | `HISTORY_ONLY` | descriptive/risk snapshot; no automatic family promotion |
| `sue_z`, `flow_attention_z`, `short_vol_ratio` | `HISTORY_ONLY` | producer telemetry; future D5 use requires explicit owner adapter |
| `gex_confirm_verdict` | `HISTORY_ONLY` in D5 | current rank influence, if any, stays under its existing explicit Fusion/Prophet registration; D5 does not become the transport route retroactively |
| `stoch_ob`, `stoch_bear`, `macd_bear` and each `*_null` | `HISTORY_ONLY` | valuable for historical null semantics; not source-family evidence |
| `hub_edge_remaining`, `hub_lifecycle`, `hub_leading_gap`, `hub_isolated`, `hub_governor_trust`, `hub_contradictions` | `HISTORY_ONLY` | decomposed hub telemetry; hub composite scores deliberately excluded already; no D5 auto-ingest |
| all flattened `personality__*`, `archetype__*`, `regime__*`, `sector__*`, `factor__*`, `attention__*`, `insider__*`, `short_int__*`, `options__*`, `spine__*`, `forensics__*` plus `context_dims` | `HISTORY_ONLY`; **bulk copy REJECTED** | source-specific allowlisted adapters only. Generic flattening previously leaked paid forensics bodies; D5 must not repeat that failure |
| `forensics__findings`, `forensics__disclosure_changes` | `REJECT_D5_EVIDENCE` / already stamp-forbidden | entitlement-gated bodies, not telemetry |
| `spine__records`, `options__skew`, `options__gex` | `HISTORY_ONLY`; bulk copy rejected | reviewed non-scalars in Context Vector do not become D5 payloads; use source-owner refs/adapters |

**Net result:** Context Vector disposition is **REUSE**, not replace; D5-specific extension count is zero.

---

## 16. Real reference-family compositions

### 16.1 Theme — honest absence until GMI ThemeState exists

Current Context Vector legacy theme fields remain useful historical telemetry. They are not the canonical GMI ThemeState promised by the flagship architecture.

D5 state today:

```text
evidence_family_id: theme.theme_state
coverage/state: ACCRUING / NOT_COMPUTED
observations: []
source_refs: [] or only an explicit owner readiness ref
fusion_bindings: []
```

Do **not** promote `theme_score`, `theme_heat_rank`, or `foresight_stage` to current canonical D5 truth to make the card look populated.

### 16.2 Earnings — preferred first vertical after B1

Source owner: `event_workspace.v1`, e.g. real AAPL event `evt_cik0000320193_2026q3_results`.

D5 copies small allowed facts (event/fiscal identity, source-owned deltas/guidance where present and basis-safe, typed warnings) and references the full workspace/source objects. It does not copy claims/transcript bodies.

The current EIOS contract explicitly keeps context-only authority and all Prophet flags false. Consensus is unlicensed in current production; therefore a beat/miss observation whose basis cannot be lawfully matched is **ABSENT**, with rights/coverage reason, not zero, neutral, or inferred from headline numbers.

### 16.3 Capital Structure — lineage strong; forward issuer twin incomplete

Source owner: `capital_structure.event.v1` and immutable event versions/edges.

D5 may transport existing event/action/filing facts, owner-native clocks, and source refs. It must not mint the proposed generic `company_event.v1`, choose a “current” share denominator, or manufacture fully diluted supply/runway/remaining-capacity fields that W4–W6 have not yet established.

Trajectory today is mostly discrete event `LEVEL` / owner-native `DELTA`; acceleration and financing-pressure decay are `NOT_APPLICABLE` or `ACCRUING` unless the source owner later defines them.

### 16.4 Options — covered neutral is different from uncovered

Current owner: ThetaData-backed Advanced Data Options plane. Current workstream evidence reports only about **39/375** daily-current names at the relevant acceptance checkpoint; global AD-1 is `BUILT_NOT_PROVEN` on coverage.

For a covered, eligible symbol where the owner produces `NO_SIGNAL`, D5 may emit `MEASURED_NEUTRAL` with the owner’s no-signal definition. For a symbol outside current source coverage, D5 emits no synthetic neutral and marks `NOT_COVERED`.

D5 may carry owner-native surface/positioning observations and persistence only when clock/cadence are comparable. It does not copy `research_priority_score` or create a second options ranker. AD-2 correction/lifecycle work is not yet complete, so D5 must not claim correction-safe historical options replay beyond owner proof.

### 16.5 Market Memory — reference the context, do not clone it

`market_memory.as_known_at.v1` already owns a label-free immutable PIT context with security identity, clocks, source receipts, 18 feature receipts, domain coverage, availability policy and all-false authority.

D5 stores a `source_ref` to the Market Memory context ID and only small owner-approved support/explanation facts needed by the episode. It does **not** copy the 18 features or source receipts into a second envelope.

Generic level/delta/acceleration are normally `NOT_APPLICABLE`. “Novelty” is allowed only if Market Memory itself exposes a defined out-of-support/distance statistic with support/denominator semantics.

### 16.6 Dislocation — research source integrity is not production evidence authority

PR #6258 is a held source-integrity repair. It has deterministic SEC source packets and honest economic episode linkage, but explicitly stops before prices, outcomes, P0-R1 consumption, score, rank, Prophet or Fusion.

Until that source-owner lane lands and publishes a production-safe state, D5 must remain `ACCRUING`/unavailable for production Dislocation evidence. It may not ingest the held K-packet as if a draft research artifact granted runtime authority.

### 16.7 Defense — multi-clock named-null exemplar

Real D3 case: IRDM / P00032 / HC101319C0006.

- effective date: **2026-05-12**;
- first known/captured by Mastermind: **2026-08-12**;
- amount: **18,416,666.66**;
- classification: late discovery;
- `source_published_at`: **NOT_ASSERTED** because USAspending exposes no per-revision publication time.

D5 must preserve those distinctions. It cannot call this a new August award merely because `known_at` is in August.

For successor/balance changes, D5 points to receipt-bound `changed_fields.before/after` and `prior_source_identity`; it never re-derives a delta in the browser/consumer and never rewrites predecessor clocks.

### 16.8 Bio — partial date and identity uncertainty are first-class

Source projection: `engine/biocatalyst/catalyst_events.py`.

The owner explicitly defines Trial Milestone rows as registry schedule facts, not signals, and forbids importance/likelihood/priority/weights. D5 preserves that.

A source date like `2027-02` remains a February interval with month precision; D5 cannot choose February 1 or 28 as “the” catalyst date. Revision lineage becomes a source/correction reference. When only sponsor→ticker mapping exists and canonical company identity is not joined, D5 carries `IDENTITY_UNRESOLVED`/ticker-only binding rather than minting a company ID.

The P1-1 product wave remains in progress because real desktop EN/ZH rows failed the no-clipping production gate; this does not authorize Cell F to repair that product or to call the family globally proven-live.

---

## 17. Product contract

A read-only D5 consumer should let a user or researcher answer, for one candidate episode:

1. **What evidence existed by the decision cut?**
2. **Which source owner says each fact, and what exact version/receipt does it reference?**
3. **Was the family applicable, covered, fresh, rights-allowed and identity-resolved?**
4. **Was an empty-looking state measured neutral or genuinely missing?**
5. **What changed over time, only where the family can define comparable trajectory?**
6. **Which facts are different source roots but potentially one economic driver?**
7. **Was this decision-time fact later corrected, and what did we believe then versus know now?**
8. **Does any piece have a separately registered Fusion member?**

The UI/machine projection groups by semantic head but renders source-owner family identity and typed failure states. It never shows an “evidence score,” “families agreeing 5/7,” or a fake completeness percentage across unlike families.

Product copy must preserve epistemic precision: “not covered,” “not applicable,” “source unavailable,” “stale,” “rights blocked,” “identity unresolved,” “insufficient history,” and “measured neutral” are different visible states.

---

## 18. Adversarial review matrix

| Attack | Required defense |
|---|---|
| New schema feels cleaner, so replace Context Vector | Rejected: preserve PIT tape and consumers; D5 references it |
| Different SEC documents = independent confirmation | Rejected: roots distinct, economic dependence may be shared |
| Missing options row becomes neutral | Rejected: neutral requires applicable+covered+measured owner state |
| Latest corrected filing is backfilled into old episode | Rejected: decision version immutable; later correction is a sibling ref |
| `source_published_at` missing, use collector time | Rejected: named null |
| Theme D3 not built, use `theme_score` | Rejected: historical legacy only; current D5 accrues honestly |
| Copy Market Memory features for convenience | Rejected: reference immutable context ID |
| Copy owner composite priority/confidence | Rejected: no second ranker; transport facts/method state only |
| Six generic trajectory columns on every family | Rejected: sparse family-native dimensions |
| Treat distinct providers as independent | Rejected: no independence claim by default |
| Use Entry Radar `live_entry_episode` as B1 | Rejected: different operational detector lifecycle and identity |
| Build D5 per nightly ticker because B1 absent | Rejected: would create second candidate lifecycle |
| Wire D5 to ENTRY_OPEN as “context only” | Rejected: explicit all-false gate/entry authority |
| Bulk-spread specialist dicts into D5 | Rejected: explicit allowlists; Context Vector paid-body leak is precedent |
| Hide producer outage behind all-null row | Rejected: source/coverage/freshness states must distinguish outage from sparse applicability |
| Count semantic heads as rank votes | Rejected: heads are grouping only |

---

## 19. Recheck of current V4 / Fusion / path gates

### 19.1 Canonical episode gate — **BLOCKING**

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A11.** Superseded in full. B1 MERGED as
> `878930b3b2f9849e120391fa461ed528f32d2e3c` (PR #6405). Status is now MERGED /
> BUILT_NOT_PROVEN: the gate is BLOCKING-because-unproven and clears on natural-production
> acceptance from a scheduled run whose HEAD contains the B1 merge.

Current-main code search finds `prophet.candidate_episode/v1` only in V4 research/freeze documents; no canonical B1 runtime implementation exists. The V4 workstream still places the episode wave before D5.

Therefore the requested real first vertical:

> mature source owner → adapter → D5 envelope on real candidate episode(s) → real read-only consumer

cannot be completed lawfully in Cell F today without inventing a second episode plane.

### 19.2 Fusion gate — clear only for zero-rank work

Conditional Fusion C1 remains the canonical cross-family ranker. D5 implementation must not edit:

- `engine/us_prophet_fusion.py`;
- `research/prophet_fusion/families.yml`;
- existing member weights/registry/authority;
- `engine/us_board_rank.py` score/rank semantics.

The first D5 vertical’s `fusion_bindings[]` should be empty.

### 19.3 Context Vector gate — clear only as read-only reference

No D5 v1 change to `engine/us_context_vector.py`, `data/us_prophet_rank/**`, or its dedupe/schema/null semantics.

### 19.4 Specialist path gate

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A7.** "existing public/load APIs" does NOT license
> `read_event_workspace` for decision-time observations. That reader is the defect this
> clause would otherwise steer a builder onto.

The first vertical must read source owners through existing public/load APIs and must not write their paths. Earnings is preferred because its `event_workspace.v1` is mature, typed, context-only, and already all-false for Prophet authority.

### 19.5 ENTRY_OPEN gate

D5 has no direct or indirect mutation path to deterministic `ENTRY_OPEN`. Any future consumer that asks to gate or change entry from D5 is a new authority operation requiring separate architecture/promotion.

---

## 20. First bounded vertical once B1 is real

> **AMENDED 2026-08-26 — see `CELL_F_D5_CONTRACT_AMENDMENTS_2026-08-26.md` A7, A8, A9, A10.** Required scope item 4
> ("source-ref the full workspace") must be read under A7's access law. The acceptance list
> below is extended by A7's two-generation correction test, which a single-generation fixture
> does not satisfy.

**Mission:** for one or more real canonical candidate episodes, project the already-produced Earnings `event_workspace.v1` through a thin allowlisted adapter into `prophet.intelligence_vector/v1`, and expose it to one existing read-only Prophet Lab episode-detail consumer without any rank/entry change.

### Required scope

1. consume **owner-issued** `prophet.candidate_episode/v1`; no local episode minting;
2. add a closed D5 contract/schema plus pure adapter;
3. adapt only the mature `earnings.event` family;
4. source-ref the full workspace; copy only small typed facts/clocks/warnings permitted by EIOS;
5. preserve `consensus_unlicensed`/basis mismatch as typed absence;
6. emit explicit evidence roots and conservative dependence group(s);
7. make all authority false and `fusion_bindings=[]`;
8. add a real **read-only** Prophet Lab detail projection, not a new product/queue;
9. no universal history migration; D5 begins prospectively from real episodes.

### Acceptance tests

- missing consensus never becomes beat/miss or zero;
- a measured-neutral owner state can be distinguished from missing;
- a source correction after decision cannot rewrite the decision observation;
- rights-blocked fields/source text are absent from display projection;
- two source documents for the same earnings announcement can be two roots but one dependence group;
- no forbidden score/rank/weight/ENTRY_OPEN fields exist;
- no import/write into Fusion rank logic;
- exact episode ID is owner-issued and survives adapter round-trip;
- Context Vector remains byte/schema untouched;
- real episode → real Earnings source → D5 → Prophet Lab read-only response is proven end-to-end.

### Stop condition

Stop after this one family and one consumer are proven. Do not wire Theme/Capital/Options/Market Memory/Dislocation/Defense/Bio in the same PR.

---

## 21. Why implementation stops here today

The blocker is architectural and satisfies the Chairman’s explicit stop condition for a genuine conflict/gate:

- D5 must be episode-scoped;
- the canonical V4 candidate-episode plane is frozen but not implemented on current main;
- the available Entry Radar `mastermind.live_entry_episode.v1` is a different operational detector lifecycle, not a semantic alias;
- using Context Vector nightly rows as episodes would create a second lifecycle/identity plane;
- implementing B1 inside MAS-122 would cross the current V4 wave/owner boundary and widen the cell beyond evidence translation.

**Therefore no runtime D5 code is started in this operation.** The architecture is frozen and implementation is explicitly `BLOCKED_ON_CANONICAL_CANDIDATE_EPISODE_B1`, not deferred because the contract is unclear.

The exact next action for the V4 owner is to implement and prove B1’s canonical `prophet.candidate_episode/v1` on real candidate lifecycle data. Once that object exists, Cell F resumes with the bounded Earnings vertical in §20.

---

## 22. External method grounding

The design is consistent with the external methods already included in the flagship READ FIRST research:

- bitemporal systems separate valid/effective time from record/system time so later corrections do not erase what was believed earlier;
- W3C PROV distinguishes entities/versions, derivation, primary-source lineage and revision relationships rather than flattening provenance into one source string;
- pipeline lineage systems such as OpenLineage separate run/job/dataset identities, reinforcing the value of typed references without pretending pipeline lineage proves economic independence.

These are architecture analogies only. Mastermind’s owner contracts, PIT laws, rights rules, and economic-dependence semantics remain canonical.

---

## 23. Frozen decisions and reopening conditions

### Frozen

- Context Vector = preserve and reference; no D5 v1 widening.
- D5 = episode-scoped typed read-model, not warehouse.
- `evidence_family_id` / semantic heads / Fusion family-member namespaces are separate.
- specialist owners compute; Cell F transports.
- roots != economic dependence.
- no independence assertion by default.
- multi-clock named-null law.
- measured neutral requires positive measurement.
- corrections append; decision belief immutable.
- trajectory sparse and owner-native.
- D5 authority all false; no direct deterministic ENTRY_OPEN path.
- first implementation family = Earnings, after B1.

### Reopen only if

- V4 changes the canonical episode contract/ownership;
- an existing source owner proves a required D5 field cannot be represented without violating its own source/rights semantics;
- an implementation demonstrates that a family-native trajectory concept cannot be transported without D5 computing domain semantics;
- Conditional Fusion changes its family/member ontology in a way that invalidates the namespace fence;
- a real consumer requirement proves a referenced owner payload must be copied for correctness, in which case rights/storage/no-rebuild review is required before widening.
