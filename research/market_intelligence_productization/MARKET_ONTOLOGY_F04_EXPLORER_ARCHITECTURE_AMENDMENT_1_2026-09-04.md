# Market Ontology F04 Explorer — Architecture Amendment 1

**Date:** 2026-09-04  
**Status:** `BINDING_ARCHITECTURE_AMENDMENT / RECORDS_ONLY / NO PRODUCT EFFECT`  
**Operation:** `marketontology-f04-explorer-architecture-20260904-sol-001`  
**Carrier:** Macro PR #6820 / `sol/market-ontology-f04-explorer-architecture-20260904`  
**Parent preserved:** `marketontology-f04-ontology-transmission-20260826-fable-001`  
**Protected procedure at adjudication:** `Mastermind@22b36b830bd5560942186ada7597508f918696af` / `mastermind.sol_skillpack.v1` 1.0.1 / bootstrap major 1  
**Reviewed predecessor head:** `621613cf79b483afe54eb4c7327a318ccb8a1ad4`  
**Capability delta:** `NONE — this amendment narrows and completes the architecture contract`

> **SUPERSEDED IN PART (2026-09-04).** Amendment 2 controls access/transport. Amendment 3,
> `MARKET_ONTOLOGY_F04_EXPLORER_ARCHITECTURE_AMENDMENT_3_REVIEW_CLOSURE_2026-09-04.md`,
> controls the F00 consumption edge, navigation, request-time freshness, K1 evidence forms,
> sample-denominator honesty, theme art directions, protected paths, and record census.
> Specifically, Amendment 1 §2.1's static publication sentence, §3.1 in full, §3.3 items
> 2/4/5, and every producer-order/DAG test are historical and must not be implemented.

This amendment closes the seven blocking ambiguities recorded in Sol exact-head architecture review `5111169860`. It is part of the same architecture operation and does not create a product route, worker, RuntimeBinding, scenario run, owner model, deployment or authority effect.

The governing thesis remains:

> **Build the explorer; compose the intelligence. Do not rebuild the organs.**

---

## 1. Authority and supersession

This amendment is binding with the existing decision and narrows the earlier architecture, handoff and implementation plan where they are ambiguous.

It supersedes only:

1. the single mixed `ontology_explorer.v1` object that could contain market snapshot, scenario and private user state;
2. any implication that a shared static paid payload may contain `mode`, a user assumption, Portfolio/Watchlist contents or another user's state;
3. any X1 path that permits prior-night TXI state to appear as current without typed visible lag;
4. the phrases `most material chain` and `weakest supported link` where no deterministic non-alpha definition was supplied;
5. any implication that F04 may own the WTI response model developed in X3;
6. any scenario implementation that reimplements TXI test grammar, infers an unspecified path shape, uses the wrong market calendar or feeds hypothetical points into owner history;
7. X1's requirement for a live Brain/page-context consumer, which belongs to X6;
8. the earlier four/five-record release census; PR #6820 ultimately merged eight records
   counted by Git, and Amendment 3 controls the current packet census.

Everything else in these sources remains controlling:

- `DEC:MARKET-ONTOLOGY-F04-EXPLORER-LIVE-TRACE-SCENARIO-BOUNDARY`;
- `MARKET_ONTOLOGY_F04_EXPLORER_ARCHITECTURE_FREEZE_2026-09-04.md`;
- `MARKET-ONTOLOGY-F04-EXPLORER-FABLE-COO-2026-09-04.md`;
- `2026-09-04-market-ontology-f04-explorer-implementation.md`;
- existing canonical owner contracts and later accepted owner-specific rulings.

A later accepted owner ruling wins for that owner. The affected F04 child returns to Sol rather than silently adapting around it.

---

## 2. Four-layer state architecture

The explorer must not solve composition by mixing unrelated state classes into one object. Four objects now have four owners, lifetimes and privacy boundaries.

### 2.1 `ontology_explorer_snapshot.v1` — tenant-neutral market snapshot

This is the tenant-neutral object returned through the authenticated read-only API in X1. It
is not eligible for a shared/public static payload.

**Owner:** F04 derived-composition producer.  
**Publication (superseded):** do not publish `/premiumdata/ontology_explorer.json` or another
public/static twin. Amendment 2's authenticated Macro API and Amendment 3's request-time
source-manifest/deployed-checkout contract control.
**Lifetime:** immutable generation.  
**Inputs:** canonical owner outputs only.  
**Private/user content:** forbidden.  
**Scenario content:** forbidden.  
**Authority:** all rank/gate/size/trade axes false.

```text
ontology_explorer_snapshot.v1
  meta
    snapshot_id
    schema
    generated_at
    effective_as_of
    knowledge_cutoff
    source_manifest_hash
    producer_build_ref
    owner_generations[]
    freshness_summary
    authority
  catalog
    default_path_id
    path_order_rule
    node_order_rule
    available_path_ids[]
  nodes[]
    node_ref
    owner_ref
    native_ref
    owner_generation_ref
    source_generation_ref?
    kind
    label
    observed_value?
    unit?
    effective_at?
    first_known_at?
    generated_at?
    freshness
    correction_state
    rights_state
    evidence_refs[]
    degradations[]
  edges[]
    edge_ref
    from
    to
    owner_ref
    native_ref
    owner_generation_ref
    source_generation_ref?
    graph_class
    method_class
    state
    input_unit?
    output_unit?
    horizon?
    effective_at?
    first_known_at?
    generated_at?
    lag_window?
    estimate?
    interval?
    n?
    span?
    regime?
    evidence_refs[]
    invalidator_refs[]
    degradations[]
  paths[]
    path_id
    owner_ref
    owner_generation_ref
    edge_refs[]
    state
    current_hop?
    first_blocking_leg?
    coverage
    combined_estimate?
    no_combined_estimate_reason?
    alternatives[]
  evidence_index[]
  invalidation_index[]
  degradations[]
```

`owner_generations[]` is an index, not a substitute for binding every material node, edge and path to the exact owner generation that emitted it.

### 2.2 `ontology_scenario_assumption.v1` — explicit user assumption

**Owner:** active user/session.  
**Lifetime:** ephemeral until the user explicitly saves a view in X7.  
**Storage in X1/X2:** memory/session state only.  
**Private:** yes.  
**Market truth:** no.  
**Owner mutations:** forbidden.

```text
ontology_scenario_assumption.v1
  assumption_id
  snapshot_id
  node_ref
  shock_definition
  magnitude
  unit
  horizon
  path_shape
  origin_class
  baseline_effective_at
  baseline_knowledge_cutoff
  created_at
```

`assumption_id` is deterministic over the normalized assumption plus `snapshot_id`. It is not a market-event ID and never enters TXI or another owner ledger.

### 2.3 `ontology_scenario_eval.v1` — pure evaluation result

**Owner:** F04 scenario composition over explicit owner adapters.  
**Lifetime:** ephemeral and recomputable from assumption + immutable snapshot + method versions.  
**Storage:** not persisted in X2. X7 saves references and assumption, not copied output.  
**Authority:** all action axes false.

```text
ontology_scenario_eval.v1
  scenario_eval_id
  assumption_id
  snapshot_id
  evaluated_at
  method_versions[]
  root_evaluation
  hop_evaluations[]
  combined_estimate?
  no_combined_estimate_reason?
  degradations[]
  side_effect_receipt
    owner_writes: 0
    episode_writes: 0
    calibration_writes: 0
    portfolio_writes: 0
    alert_writes: 0
```

A scenario evaluation may contain threshold state, historical context, an owner-model output, same-window empirical sensitivity or typed unavailability. It cannot relabel any field as observed.

### 2.4 `ontology_session_view.v1` — interaction and private overlay

**Owner:** authenticated/session UI layer.  
**Lifetime:** browser/session; later save through Terminal/Supabase User Plane in X7.  
**Shared static payload:** forbidden.  
**Telemetry:** closed, non-sensitive event metadata only.

```text
ontology_session_view.v1
  session_view_id
  snapshot_id
  mode                 # LIVE_TRACE | SCENARIO
  selected_path_id
  selected_node_ref?
  selected_edge_ref?
  filters
  layout
  assumption_id?
  portfolio_generation_ref?
  watchlist_generation_ref?
  overlay_summary?
```

Private overlay data is fetched and joined through then-current authenticated Portfolio/Watchlist contracts. It never enters public HTML, shared static JSON, committed browser evidence or analytics payloads.

### 2.5 Future saved-view contract

X7 persists user-owned saved-view identity/revisions, `snapshot_id`, owner references, session-view state, normalized assumption and correction/supersession comparison metadata.

X7 does not persist copied market values, evidence bodies, a private duplicate graph, cached evaluation claimed as enduring truth, or raw Portfolio/Watchlist content in a share object.

---

## 3. Historical freshness proposal — superseded for request-time X1

> **SECTION SUPERSEDED.** Amendment 3 §4 replaces §3.1 and §3.3 items 2, 4, and 5.
> X1 composes at request time from exact bytes in the deployed checkout. Freshness is proven
> by owner generations, `source_manifest_hash`, owner clocks, and typed
> `DEPLOYED_CHECKOUT_LAG`/`DEPLOY_PULL_LAG`; it is not proven by nightly job order.

The current TXI web-publication adapter documents a one-night lag because `build_site` runs before `run_transmission_chains`. The explorer cannot inherit that lag while claiming current Live Trace.

### 3.1 Historical producer-order proposal — do not implement for request-time X1

```text
required TXI/rate owner producers complete
-> exact immutable owner generation identities exist
-> build ontology_explorer_snapshot.v1
-> validate source manifest and clocks
-> publish gated snapshot
-> build/serve /ontology.html shell and client
```

The ontology snapshot producer runs after every owner whose current values it includes. A later owner step cannot silently make the newly published snapshot stale at birth.

### 3.2 Permitted degradation

If current owner freshness cannot be established, return only with, per affected owner/edge:

- owner generation used;
- newest owner generation available to the producer;
- measured lag duration/cycles;
- typed `SOURCE_STALE` or owner-specific degradation;
- visible user disclosure.

A page-level as-of without owner-generation identity is insufficient.

### 3.3 X1 production proof

X1 must show:

1. exact owner artifacts and hashes/generation IDs read;
2. exact deployed checkout/build identity and its relationship to current source;
3. snapshot `source_manifest_hash` resolving to exact inputs;
4. request-time composer build/method identity;
5. no newer owner generation exists in current source but is absent from deployment, or typed deployed-checkout/pull lag accurately discloses it;
6. browser values matching snapshot and owner receipts.

This does not authorize changing `/transmission.html` in X1. Its existing lag is a separately owned defect.

### 3.4 Partial owner failure

If owner A advances and owner B fails, accept A only if independent owner generations are supported; retain B last-good only under B's law and mark stale; never assign one false unified freshness status; preserve correction links; do not withhold unaffected paths.

---

## 4. Deterministic non-alpha ordering and first-blocking-leg semantics

### 4.1 X1 default

X1 defaults to `oil_inflation_duration_derate` as an explicitly frozen product/reference path. It is not a machine judgment that WTI is the most important or highest-conviction path.

The X1 UI may say `Reference path`, `WTI transmission trace` or `Selected path`. It must not call WTI the `most material chain`.

### 4.2 General path ordering

Until a later accepted product-ranking owner exists, path rails use deterministic non-alpha ordering:

1. closed state order, e.g. `propagating`, `arming`, `expressed`, `dormant`, `halted`, `expired`, `unavailable`;
2. current hop/depth within compatible state class;
3. most recent owner transition timestamp;
4. canonical `path_id` tie-break.

An explicitly editorial pinned order is also lawful when labeled and versioned. Neither form may use expected return, historical follow-through, model confidence or user exposure to imply recommendation.

### 4.3 First blocking leg

For X1, `first_blocking_leg` is the first declared hop whose required source node is false, unknown, stale beyond owner law, rights-restricted, invalidated, expired or unresolved. It is null only when all required hops are satisfied.

A later `least_authoritative_leg` may use a closed method ceiling only:

```text
OBSERVED_STATE / DETERMINISTIC_IDENTITY / accepted OWNER_MODEL
> EMPIRICAL_SAME_WINDOW_BETA
> HISTORICAL_TRANSITION_RATE / HISTORICAL_OUTCOME_DISTRIBUTION
> THRESHOLD_STATE_ONLY
> HYPOTHESIS_MECHANISM
> UNAVAILABLE
```

This is not a probability or economic-strength score. Classes are never averaged.

### 4.4 Historical transition-rate language

Preferred rendering:

> Followed in 49 of 71 eligible historical windows (69%), 2002–2026. Growth-accelerating: 21 of 28; steady/slowing: 28 of 43.

The integer numerator must be emitted or deterministically derived without changing denominator semantics.

When no valid null/unconditional comparator exists, emit `baseline_comparison: unavailable` and render `Historical follow-through only; no baseline lift established.`

Never call it confidence, reliability, probability of the current path, causal effect or expected return.

### 4.5 Structured coverage

```text
coverage
  denominator_definition
  total
  covered
  unavailable
  stale
  rights_restricted
  unresolved_identity
  method_unsupported
  effective_as_of
  knowledge_cutoff
```

A percentage may be derived for display, but denominator and buckets remain inspectable and the percentage is never relabeled confidence.

---

## 5. X3 owner boundary

F04 is the consumer/composition product. It does not own oil-to-inflation/rates response estimation.

X3 begins as a bounded dependency request under the existing Rate & Inflation Transmission / Rates-Inflation Command owner. TXI supplies chain definitions, root/next-hop constructs, lag windows, episode context, mechanisms and falsifiers. The rates/inflation owner supplies or rejects shock definition, source/origin identification, response estimation, units/horizons, clocks/vintages, method version, uncertainty, evaluation and publication contract. F04 consumes an accepted output by immutable reference.

Do not create owner models under:

- `engine/ontology_explorer/wti_response.py`;
- `engine/ontology_explorer/oil_causal_model.py`;
- `data/ontology_explorer/wti_coefficients.*`.

If current owner law does not clearly permit adoption, X3 returns `DECISION_REQUEST / OWNER_BOUNDARY_UNRESOLVED`. No numerical WTI propagation is built until Sol resolves the owner.

The owner may validly conclude `NOT_ESTIMABLE`, `INSUFFICIENT_IDENTIFICATION`, `UNSTABLE_ACROSS_ERAS`, `RIGHTS_OR_VINTAGE_INADEQUATE` or `REJECTED_BY_DESIGN`. F04 productizes that rejection honestly.

---

## 6. Scenario path-overlay contract

### 6.1 Baseline

A scenario starts from one immutable snapshot, owner-native values knowable at `baseline_knowledge_cutoff`, and owner-native effective dates and calendars. Current data may not be substituted into a historical cutoff.

### 6.2 Closed path-shape vocabulary

- `terminal_only` — terminal observation only;
- `linear_sessions` — equally spaced owner-session path between baseline and terminal;
- `step_at_start` — full change at first eligible owner session;
- `custom_points` — explicit dated owner-session points, only after a later security/validation review.

A missing path shape is invalid. `terminal_only` cannot satisfy a slope, persistence, rolling-window path or volatility requirement.

### 6.3 Calendar and unit law

Securities/futures use the series owner's trading sessions; release series use the release owner's calendar; basis points, percentage points, percentages and index points remain distinct; horizon labels resolve to exact owner windows; calendar days are never silently substituted for sessions.

### 6.4 TXI grammar reuse

F04 does not copy the TXI threshold parser or evaluator. It calls a reviewed pure interface over the existing grammar. If that interface cannot accept an ephemeral series overlay without owner writes, X2 returns an owner-interface request rather than forking the grammar.

### 6.5 Ephemeral algorithm

```text
read owner series <= knowledge cutoff
-> clone in memory
-> append/replace only explicit future assumed points under path_shape
-> evaluate existing node test against clone
-> discard clone
-> emit threshold result + receipts + zero-side-effect receipt
```

The output states which inputs are observed and which are assumed.

### 6.6 Typed refusals

Return unknown/unavailable when baseline history is too short, horizon does not cover the test window, path shape does not determine a required feature, a point is on an invalid session, units cannot be converted without a model, required origin class is unspecified, or the snapshot is stale beyond method law.

### 6.7 History isolation

Scenario points/results may not append to `chain_episodes.jsonl`, modify `chain_state.json`, enter calibration/estimator samples, change historical N/span/regime, become evidence for an observed episode or publish as a market alert. Mutation tests prove owner artifacts are byte-identical before/after evaluation.

---

## 7. X1 and X6 boundary

X1 complete path:

```text
canonical owner outputs
-> ontology_explorer_snapshot.v1 producer
-> authenticated private/no-store API response
-> /ontology.html client
-> WTI path rail/canvas/inspector/inverse/invalidator/history
-> candidate and production browser proof
```

X1 may include stable IDs and schema/contract compatibility tests. It includes no live Brain request, page-context wiring, selected-path answer behavior or AI citation resolution. Those remain X6. This is sequencing discipline, not a reduction of the final product.

---

## 8. Binding real-data reference compositions

These freeze information hierarchy and interaction behavior using current canonical WTI receipts. They are not a pixel copy and use no competitor assets, copy, code or brand identity. Values are archaeology/reference values, not runtime constants.

### 8.1 Desktop paid — WTI Live Trace, current path dormant

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│ ONTOLOGY                 Search node or path…         LIVE TRACE | Scenario  │
│ Reference path · WTI transmission trace  Owner as-of 2026-08-31 · built 2026-09-01 05:51 UTC │
├──────────────────────────────────────────────────────────────────────────────┤
│ TRACE NARRATIVE                                                               │
│ Downstream real-yield and duration conditions are present, but the declared  │
│ WTI shock and breakeven hop are not. This path remains dormant; another      │
│ mechanism may explain the downstream state.                                  │
│ First blocking leg: WTI shock → breakevens                                   │
├──────────────────┬───────────────────────────────────────┬───────────────────┤
│ PATH              │ DIRECTED TRACE                        │ INSPECTOR         │
│ WTI reference     │ [WTI +13.9% /60s] ─ ─> [BE +4bp/22s] │ Oil → breakeven  │
│ State: Dormant    │   root false             false        │ Lag: 5–60d       │
│ Current hop: 0/3  │          │                            │ Followed: 49/71  │
│ Inverse oil path  │          └──── contextual only ───┐  │ Baseline lift: — │
│ Credit path       │                                  ▼  │ Method: history  │
│ Dollar path       │ [Real 10Y +31bp/63s] ───> [QQQ −4.8pp vs SPY /63s]      │
│                  │             true                   true │ Invalidator…     │
├──────────────────┴───────────────────────────────────────┴───────────────────┤
│ Evidence: Observed ✓  Historical ○  Hypothesis ◇  Unavailable —             │
│ Relationship: Economic only   Invalidators   My portfolio (later)            │
└──────────────────────────────────────────────────────────────────────────────┘
```

Required semantics:

- dormant styling stays legible and cannot become active because downstream nodes are true;
- observed truth and historical context use different treatments;
- `49/71` is derived exactly; no hard-coded rounded numerator;
- terminal-cohort outcome study is a separate inspector section, never corroborating confidence;
- inverse path is separate;
- inspector includes owner generation, clocks, correction, rights and evidence.
- the historical reference is explicitly labeled `PR #6820 archaeology snapshot`; runtime
  values are never copied from it;
- calibration evidence separately shows owner as-of `2026-08-21` and built
  `2026-08-22 16:34 UTC`.

### 8.2 Active/partial pattern

```text
ROOT OBSERVED -> confirmed hop(s) -> FIRST WAITING/UNKNOWN HOP -> downstream context
```

Only owner-confirmed hops receive active propagation treatment. Downstream observations beyond the first unresolved hop may display as context but are not connected by an active edge.

### 8.3 Mobile paid — vertical sequence

```text
ONTOLOGY · LIVE TRACE
WTI transmission trace          Dormant

Downstream conditions are present, but the oil root is not.

1  WTI CRUDE OIL
   +13.9% over 60 sessions
   Needs > +25% and rising MA50
   Root not satisfied

2  10Y BREAKEVEN
   +4bp over 22 sessions
   Needs > +15bp
   Not confirmed
   Historical follow-through: 49 of 71 windows
   [Inspect evidence]

3  REAL 10Y YIELD
   +31bp over 63 sessions · rising
   Condition present — not attributed to WTI

4  LONG-DURATION EQUITIES
   QQQ −4.8pp vs SPY over 63 sessions
   Condition present — not attributed to WTI

[Inverse path] [Invalidators] [Source desk]
```

No horizontal graph is required to complete the task; path order is keyboard/screen-reader order; all qualifiers remain visible without hover; optional canvas is secondary; EN/ZH states and caveats are equivalent.

### 8.4 Anonymous / Free shell

```text
ONTOLOGY
Understand how a market move can travel — and where evidence stops.

Reference composition
WTI → inflation expectations → real yields → duration

Current owner values are available to Essential and Pro members.
[Start trial / Sign in]

Method
• Live Trace uses owner-observed state.
• Scenario begins with an explicit assumption.
• Historical follow-through is not a forecast.
• Unsupported links remain unavailable.
```

The shell may include a non-current instructional diagram and methodology. It may not contain current values/state, evidence receipts, private overlays or the paid payload serialized into HTML/JS. Anonymous and Free direct payload requests fail under existing `site_full` law.

### 8.5 Stale owner

```text
WTI path · Source stale
Last owner generation: <exact ref>
Freshness limit: <owner law>
Affected: root value and dependent path state
Unaffected: separately fresh rate/duration observations
Action: last-good stale context only / current trace unavailable
```

### 8.6 Scenario method unavailable

```text
ASSUMED: WTI +20% over 3 months · terminal only
Root threshold: not satisfied (>25% required)
MA50 slope: unknown — terminal-only does not define interim slope
Numerical oil→CPI response: unavailable — no accepted owner method
Historical mechanism and invalidators remain inspectable
```

### 8.7 PIT unavailable

```text
Replay: 2024-06-30 effective / knowledge cutoff 2024-07-01
WTI owner history: available
Theme membership: PIT unavailable for this cutoff
Result: macro path visible; theme/security expansion withheld
Current membership was not backdated
```

### 8.8 Partial Portfolio coverage

```text
Portfolio overlay
Covered: 7 positions / 61% of supplied market value
Unresolved identity: 1 / 8%
No compatible response model: 3 / 31%

No whole-book P&L estimate available.
```

Raw holdings/weights remain private and never enter shared evidence or telemetry.

---

## 9. Revised X1 acceptance boundary

X1 is accepted only when:

1. snapshot is tenant-neutral and contains no assumption/user overlay;
2. owner-generation references bind every material node/edge/path;
3. request-time `source_manifest_hash`, owner generations, deployed checkout/build identity,
   and typed source/deploy lag prove freshness without a nightly-order claim;
4. WTI is explicit reference/default, not machine-ranked as most material;
5. `first_blocking_leg` is deterministic path-order state, not score;
6. historical rates show episode numerator/denominator/span/regime and baseline-comparison
   availability; terminal cohort bar N is labeled overlapping and missing effective N,
   overlap treatment, interval, span, or concentration is typed unavailable;
7. coverage is structured;
8. public/Free shell and paid boundary are proven;
9. desktop/mobile compositions and stale/unavailable states work with current data;
10. producer + entitled browser consumer are production-proven;
11. Brain, Scenario execution, Portfolio overlay, GMI/K3-D adoption and private save remain out;
12. no canonical owner/ledger is modified by the projection.

---

## 10. Revised child boundaries

- **X1:** immutable tenant-neutral WTI Live Trace snapshot and user surface. No Brain/scenario evaluation.
- **X2:** assumption/eval contracts, owner-native path-overlay evaluator and one existing real-rate empirical scenario. No persistence.
- **X3:** Rate & Inflation Transmission / RIC owner researches and publishes or rejects magnitude-sensitive WTI response output; F04 consumes only.
- **X4:** private Portfolio/Watchlist join into session view through authenticated owners; never shared snapshot.
- **X5:** channel-specific adapters without universalizing clocks/methods.
- **X6:** selected-path context and Ask Mastermind through existing Brain gateway.
- **X7:** saved view revisions and assumptions in Terminal/Supabase User Plane; recompute from references.
- **X8/X9:** unchanged except they consume these four-layer contracts and ordering law.

---

## 11. Hostile tests added by this amendment

### X1

- shared snapshot refuses `mode`, `assumption`, `user_overlay`, raw holdings and user IDs;
- every material node/edge/path resolves owner generation;
- deployed-checkout test fails when current source has a newer owner generation than the
  request-time deployment and no typed deploy/pull lag is emitted;
- downstream true nodes cannot activate false root;
- p-confirm ordering or deletion of first-blocking-leg logic turns tests red;
- public HTML/JS contains no current values or paid body;
- mobile vertical path works without canvas JavaScript.

### X2

- terminal-only cannot satisfy slope/persistence;
- calendar/session mismatch refuses;
- owner files remain byte-identical before/after scenario;
- scenario never serializes as observed;
- eval IDs change with snapshot/method version;
- copied TXI grammar is rejected by ownership/contract checks where feasible.

### X3

- model cannot land under F04 namespace;
- owner output carries source/method/clock/version/uncertainty;
- explicit rejection is a completed research outcome;
- F04 refuses unaccepted/unversioned response artifacts.

### X4/X7

- private content never enters shared snapshot, public HTML, committed screenshots or analytics;
- cross-user RLS/share sanitization fail closed;
- saved views persist references/assumptions, not owner values/eval outputs.

---

## 12. Routing and effect receipt

```text
PARENT_OPERATION: marketontology-f04-ontology-transmission-20260826-fable-001
PREFERRED_AVENUE: Fable
RECEIVER_BINDING_MODE: CAPACITY_SELECTABLE
PLACEMENT_STATE: WAITING_CAPACITY / needs_placement
CURRENT PRODUCT EFFECT: NONE
CURRENT WORKER EFFECT: NONE
```

Fable remains justified as sustained principal because the amended program crosses owner, access, private-state, scenario-method and production boundaries. Bounded implementation remains least-scarce-worker labor.

A fixture/read Executive surface is not production-live placement. Concrete eligible receiver and lawful assignment remain required before ACK/START.

---

## 13. Architecture-carrier release gate

PR #6820 remains Draft/Hold until:

1. historical PR #6820 changed-file census is eight records by Git; the current repair adds
   Amendment 3 and minimally amends the eight predecessor records;
2. decision and PR body reference the amendment and supersession;
3. Agent OS/schema/fences and relevant CI are terminal with no candidate-owned red;
4. the two existing review packets are closed by Amendment 3 delta verification; no third
   full review is required for the bounded records repair;
5. current-main compatibility is proven under current review-reuse law;
6. Sol accepts the immutable head.

A merge makes architecture durable only. It does not place Fable, start X1, create `/ontology.html`, run a scenario, accept D2C/K3-D or confer market/trading authority.

---

## 14. Exact next action after architecture acceptance

1. Preserve D2C #6809 on its repair carrier and consume only a real repaired return.
2. Bind one concrete eligible Fable principal to the existing parent when capacity exists; otherwise retain `WAITING_CAPACITY / needs_placement`.
3. Fable performs fresh current-main/open-PR/active-runtime planned-write census.
4. Commission X1 as a new child to the least-scarce capable avenue.
5. X1 stops at the tenant-neutral WTI Live Trace snapshot and production browser proof defined here.

No old parent watcher, D2C runtime or architecture PR may self-originate X1.
