# Fiscal-derived Research OS architecture delta

**Date:** 2026-08-22  
**Status:** architecture/source-law freeze candidate; records/research only  
**Executive owner:** Sol / Chairman Chris  
**Experience parent:** `WS:MARKET-OS` / existing `terminal-user-services` boundary  
**Semantic owners preserved:** Earnings Intelligence, Financial Intelligence Fabric, Alpha Intelligence, Stock/Data identity, GMI/Theme Graph, specialist event lobes, Eval OS, Conditional Fusion  
**Repositories inspected:** `mastermindx-market-intelligence/macro`, `mastermindx-market-intelligence/mastermind-terminal`, `mastermindx-market-intelligence/Mastermind`  
**Protected Skillpack:** `mastermindx-market-intelligence/Mastermind@db0bac5fe3f72348262d42c8bd26b836bda9f61d` (`mastermind.sol_skillpack.v1`, version `1.0.0`, bootstrap major `1`)  
**Macro pickup base:** `1dde1cc2dd1166c3ecda510a2f05a09ca6452fad`  
**Terminal observed master:** `449439c690e93ba968185499af4041c2f512b659`  
**Fiscal authenticated-recon source:** Mastermind draft PR `#121` head `758741b9b89d9ee641729a81af691ad608de4720`; only structured observations/interaction findings are architectural inputs here. Raw authenticated screenshots are under separate Sol packaging hold and are not reproduced in this document.

---

# 0. Executive ruling

The Fiscal reconnaissance does **not** justify a Fiscal clone, a new Research OS backend, a universal Market-Belief database, a second metric registry, a second search index, or another AI memory plane.

It does expose three cross-product capabilities that Mastermind should freeze explicitly:

1. **Market-Belief / Expectation composition** — a point-in-time view over owner-native expectation and incorporation objects, not a new truth store and not one score.
2. **Portable Research Context** — a bounded bundle of canonical references that lets a user's active investigation survive legitimate surface transitions, not a new memory or evidence warehouse.
3. **Reusable Analytical Lens** — a versioned deterministic expression over canonical owner metrics/facts that can travel across compatible subjects and product surfaces, not a second financial semantic model.

The ownership split is load-bearing:

```text
owner-native truth
  → optional owner/federation expectation semantics
  → optional family-specific incorporation science
  → bounded reference/composition objects
  → Market OS / Terminal experience
```

Never invert it into:

```text
Market OS / Terminal
  → new universal truth store
  → copied source payloads
  → new scoring authority
```

The architecture therefore freezes the following company-level thesis:

> **Reality is owned by the specialist truth planes. Market belief is reconstructed from point-in-time owner-native expectations and observable incorporation. Research context carries references to those truths through the product. Analytical lenses recombine governed inputs without becoming new truth or signal authority.**

This is a product/intelligence convergence ruling. It creates no runtime, database, schema, search index, ranker, signal, Prophet feature, user-state writer, or production claim.

---

# 1. Intent recovery

## 1.1 User job

A serious investor should be able to begin with a concept, company, event, source, chart, portfolio question, or emerging discrepancy and move through Mastermind without repeatedly rebuilding the question in their head.

The end-state journey is:

```text
notice something
→ search / discover
→ open the company or event
→ inspect exact evidence
→ compare with expectations and prior belief
→ inspect what price appears to have incorporated
→ apply or create a useful analytical lens
→ compare peers / a basket / a portfolio when semantically valid
→ ask Mastermind with the same selected evidence and cutoff
→ save or monitor the investigation deliberately
→ return later with corrections and changes visible
```

The user should never have to wonder whether switching from Search to an event, from an event to a chart, or from a chart to Ask Mastermind silently discarded the active concept, source evidence, comparison set, or historical cutoff.

## 1.2 Machine/intelligence job

The machine must keep four things separate:

1. **Reality State** — source-backed facts/events/relationships owned by specialist systems.
2. **Expectation / Belief State** — what a defined actor or observable market channel expected as of a defined clock.
3. **Incorporation State** — how observed market response compares with a family-specific, preregistered response baseline where estimable.
4. **Research Interaction State** — what the user is currently investigating and which canonical objects are selected.

These states may be composed in one experience. They must not be collapsed into one storage authority or one number.

## 1.3 Moat

The moat is not navigation state or formula syntax by itself. Those are reproducible.

The moat is the accumulating combination of:

```text
correction-safe source truth
+ canonical identity
+ point-in-time expectations
+ event/evidence lineage
+ relationship/theme context
+ family-specific incorporation histories
+ reusable analytical definitions
+ exact source receipts
+ prospective outcome learning
```

Portable context makes that intelligence usable. It does not create the intelligence.

## 1.4 10/10 end-state example

The user searches `HBM supply constraint` globally. Results span calls, filings, guidance items, relationships, and issuer events. The user opens one NVDA event, pins two exact management statements, changes the historical cutoff to the event date, opens an HBM supplier comparison set, and applies a saved lens such as `CapEx / Revenue` where the financial semantics are compatible. They then open Ask Mastermind.

Ask Mastermind receives references to the same search concept, event, evidence pins, comparison set, cutoff and lens definitions. It does not receive copied proprietary document bodies from a navigation state object. If one source was corrected after the historical cutoff, the product shows the correction without rewriting what was knowable at the selected cutoff. If a peer lacks a comparable CapEx definition, the lens returns a typed coverage/refusal state rather than zero. If the user later opens Prophet, none of this interaction automatically becomes rank authority.

---

# 2. What the authenticated Fiscal reconnaissance actually taught us

The architectural input is the structured behavior, not Fiscal's text/assets/visual identity.

Observed jobs from Mastermind PR #121 include:

- company sibling surfaces preserved company context well;
- a cross-document query carried company, query text and exact result identity into an event/transcript deep link;
- transcript selection coordinated with audio;
- Query, global Charting, dashboard, fund-letter and investor-profile workspaces retained different local state rather than one shared investigation state;
- estimate selections did not travel into global Charting;
- a company-specific user-created metric survived reload and charted locally, but did not appear in Screener, global Charting or another issuer's custom-metric search;
- a displayed primary-U.S. NVIDIA selection could persist as `BUL:NVD`, demonstrating that a smooth context transfer is dangerous if identity itself is wrong;
- a holder filing could be opened from ownership data, while holder identity did not directly route into the separately available investor profile.

The useful lesson is therefore not “copy Fiscal navigation.” It is:

> **Context continuity, identity integrity, reusable analytical definitions, and source traversal are separate capabilities. A product can be strong at one and weak at another.**

Mastermind should make those boundaries explicit.

---

# 3. Current Mastermind capability ledger

Closed state vocabulary is the company standard.

| Capability | Current state | Canonical owner / evidence | Fiscal-derived delta |
|---|---|---|---|
| Generation-pinned Company Intelligence workspace | `PROVEN_LIVE` for the current bounded Terminal path | Earnings / Terminal `company_intelligence_context.v1` | Preserve; use as local-context precedent |
| Local event/evidence selection | `PROVEN_LIVE` / bounded | Terminal Company Intelligence workspace resets evidence on event change | Generalize semantics, not implementation |
| Global cross-source primary-source search | `SPEC_ONLY` globally / `PARTIAL` ticker-scoped | Earnings E5 plan; current Terminal transcript/source search | Fiscal raises experience priority; no second search index |
| Earnings `consensus_snapshot` / `estimate_revision_state` architecture | `SPEC_ONLY` / source-dependent | Earnings V2 | Feed future expectation composition; do not move ownership |
| Current analyst revision snapshots | `PARTIAL` / `ACCRUING` | current revisions collector; Alpha-E census | Useful only from observation-era birth; not historical consensus truth |
| Deep historical Street-consensus vintages | `NOT_BUILT` at required depth | no licensed historical owner-native plane proven | Strategic data gap; separate source/data program needed |
| Market-incorporation state-vector research | `PARTIAL` research architecture | Alpha-E E0 + MAS-118 | Keep family-specific; no universal gap score |
| Federated `ExpectationBaseline` semantics | `SPEC_ONLY` / MAS-119 backlog | Catalyst Federation candidate | Natural common semantic seam; do not preempt it here |
| Prophet D5 typed evidence transport | `SPEC_ONLY` | MAS-122 / PR #6275 | D5 transports later; it is not user research context |
| Portable cross-workspace research context | `NOT_BUILT` as a canonical cross-surface primitive | local precedents only | Freeze reference semantics here |
| Governed financial facts/formulas/query semantics | `PARTIAL` but canonical architecture frozen | Financial Intelligence Fabric | Analytical lenses must consume, not duplicate |
| User-defined reusable analytical lens | `NOT_BUILT` as cross-subject/product primitive | no canonical implementation found | Freeze definition/evaluation laws here |
| Market OS shared experience | `PARTIAL`, active A1A | `WS:MARKET-OS` | Experience host only; current A1A remains untouched |
| Cross-family rank / authority | `PROVEN_LIVE` under existing owner | Conditional Fusion / Eval OS | Explicitly out of scope |
| Dislocation P0 blind source/manifest experiment | `PARTIAL`, protected | Dislocation owner route | No touch; no outcome-informed adoption |

---

# 4. Canonical ownership matrix

The most important output of this freeze is not a schema. It is the ownership boundary.

| Concern | Canonical owner | This architecture may do | This architecture may not do |
|---|---|---|---|
| Issuer/security/listing identity | Stock/Data identity owners | reference canonical IDs | mint ticker truth or infer primary listing from UI strings |
| Financial statement/metric/formula semantics | Financial Intelligence Fabric | reference/query governed metric IDs and receipts | create a second metric registry/query kernel |
| Earnings event truth | Earnings Intelligence | reference event/source/guidance/Q&A objects | create a second event store |
| Other specialist event truth | domain owners (Bio, Defense, Capital Structure, etc.) | reference native objects | normalize away domain meaning |
| Common catalyst expectation semantics | future MAS-119 / owner federation | consume an accepted `ExpectationBaseline` shape later | preempt it with a Market-OS expectation database |
| Family-specific response/incorporation science | MAS-118 / Alpha-E owner route | display/reference accepted assessment later | create universal `gap_score`, fair value or new event study |
| Prophet evidence transport | MAS-122 / V4 D5 after its own gates | pass accepted references later | make research navigation state a D5 family |
| Cross-family rank/influence | Conditional Fusion | none | rank from lenses/context/history |
| Evaluation/promotion | Eval OS / QLedger | none | infer authority from product usefulness |
| Search corpora/indexes | existing source/search owners, notably Earnings E5 for company-event sources | carry query/result refs between surfaces | build another universal index in Market OS |
| User-state / cross-surface experience | Market OS under `terminal-user-services`, after current owner gates | compose bounded references and deliberate saved state | own source truth or duplicate specialist data |
| Neural/context memory | existing Neural Web / Brain / Research Vault boundaries | resolve explicitly passed refs | turn navigation context into a second durable memory plane |

### 4.1 Ownership ruling for “Market-Belief State”

There is **no new universal Market-Belief truth store**.

The product may render a `Market Belief` lens, panel or view. That view is composition.

A future composition may include separately typed observations such as:

- explicit analyst consensus / dispersion / revisions;
- issuer guidance or other owner-native expectations;
- options-implied distribution or move where the Options owner provides a lawful object;
- observable ownership/positioning context at its native lag;
- attention or narrative breadth at its native clock;
- family-specific `IncorporationAssessment` from MAS-118 where validated;
- typed unknown/unavailable/unlicensed states.

Those are not interchangeable “belief votes.” They retain actor/channel, method, clock, scope, units, coverage and authority.

### 4.2 Reality → belief → response law

For catalyst-like events, the preferred semantic sequence is already converging elsewhere:

```text
EventFact
→ ExpectationBaseline
→ SurpriseAssessment
→ IssuerMaterialityAssessment
→ IncorporationEvidence / IncorporationAssessment
```

This architecture adopts that separation as the interface direction and defers exact common expectation semantics to MAS-119. It adopts MAS-118's family-specific incorporation boundary and does not create a competing calculation lane.

---

# 5. Market-Belief / Expectation composition

## 5.1 Purpose

The user question is not simply “what is consensus?” It is:

> What did relevant observable actors/channels appear to expect at this time, what changed, how certain is that reconstruction, and how much appears reflected in the market under a lawful family-specific method?

That requires a composition of heterogeneous owner-native states.

## 5.2 Conceptual read model, not production schema

A future product-level composition may look conceptually like:

```text
market_belief_view
  subject
    issuer_id
    security_id?
    event_id?
  decision_cutoff
  observations[]
    belief_channel
    owner
    native_object_ref
    method_class
    value_or_state
    unit_or_distribution
    known_at
    source_effective_at?
    captured_at
    corrected_at?
    coverage_state
    rights_state
    authority_tier
  expectation_baseline_ref?
  surprise_assessment_ref?
  incorporation_assessment_ref?
  conflicts[]
  typed_absences[]
```

This object should normally be derived/read-only and reconstructable from owners. Persistence is not justified merely because the view is useful.

## 5.3 Point-in-time law

Every belief observation must distinguish, where applicable:

- what period/event it describes;
- when the source became available;
- when Mastermind observed/captured it;
- what was knowable at the user's selected cutoff;
- whether a later correction/restatement exists;
- whether the shown state is contemporaneous, reconstructed or current-only.

A later corrected value may be visible as a correction. It may not overwrite the historical belief state and then pretend the corrected value was known earlier.

## 5.4 No scalar-belief law

Do not compute:

```text
market_belief_score = analyst + options + 13F + sentiment + price
```

without a separately validated statistical question and authority path.

A slow 13F position, an option-implied distribution, analyst consensus and immediate price response are different clocks and constructs. The user can see them together; the machine may not treat co-location as commensurability.

## 5.5 Historical consensus is a source/data gap, not a UI gap

Current Alpha-E work already found that the in-estate analyst revision history begins in mid-June 2026 and that broad historical Street-consensus vintages are absent at the quality needed for replay.

Therefore:

- do not backfill current consensus backward;
- do not scrape/derive a fake historical consensus from current provider pages;
- do not use final/restated estimates in historical event studies;
- evaluate a rights-safe licensed historical estimate-vintage source separately;
- until then, owner-native expectations such as comparable prior issuer guidance may support narrow families where lawful, as MAS-118 is already researching.

---

# 6. Portable Research Context

## 6.1 Ruling

Portable Research Context is a **reference bundle**, not memory and not truth.

The product must be able to carry a bounded active investigation across compatible surfaces without copying source corpora, manufacturing identity, or granting authority.

The name `ResearchContextRef` is descriptive here, not a frozen production schema name.

## 6.2 Conceptual shape

```text
ResearchContextRef
  context_version
  origin_surface
  active_surface
  subjects[]
    issuer_id
    security_id?
  selected_event_ref?
  active_query?
    query_text
    query_mode
    filter_refs[]
    result_ref?
  pinned_evidence_refs[]
  comparison_set_ref?
  decision_cutoff?
  selected_lens_refs[]
  active_projection?
  created_at_session
  expires_at_session?
```

### It carries

- canonical IDs and object references;
- user's active query text/filter semantics where safe;
- selected/pinned evidence handles;
- comparison-set references;
- an explicit historical/as-of cutoff;
- analytical-lens references;
- presentation selection needed to make the next surface coherent.

### It does not carry

- full transcript/filing/fund-letter bodies;
- duplicated financial facts;
- copied search indexes;
- derived Prophet scores;
- hidden recommendations;
- a second user-memory transcript;
- credentials/entitlements;
- source bodies that the destination user is not entitled to view.

## 6.3 Identity law

Context never uses a ticker string as the authoritative cross-surface identity.

A displayed symbol may travel for presentation. The transfer is bound to canonical issuer/security/listing identity from the owner.

The Fiscal `NVDA` → `BUL:NVD` observation is the canonical failure example: smooth persistence of the wrong listing is worse than a visible refusal.

If identity cannot be resolved unambiguously, transfer fails with `IDENTITY_UNRESOLVED` rather than silently choosing another listing.

## 6.4 Evidence/rights law

Pinned evidence is a reference to an owner-native receipt. The destination surface re-resolves:

- identity;
- availability/correction state;
- user entitlement;
- source display rights.

A context reference never turns a source the user could see on Surface A into a permanent unrestricted copy on Surface B.

## 6.5 Correction law

If pinned evidence is corrected or superseded after selection:

- preserve the original pinned reference and historical cutoff;
- show that a correction exists;
- allow the user to inspect current/corrected truth separately;
- never silently retarget a historical pin to latest truth.

## 6.6 Persistence law

Default implementation should prefer **ephemeral/session/navigation composition** first.

If users later explicitly save a research workspace or lens set, persistence must use/reconcile the existing `terminal-user-services` user-state authority after an owner census. This freeze does **not** authorize a `research_context` database, workspace store, browser-local canonical fallback, or new cloud truth plane.

## 6.7 Boundary with other Mastermind context systems

`ResearchContextRef` is not:

- Prophet D5 — D5 is an episode-scoped decision-time evidence read-model for Prophet;
- Neural Web memory — this is user interaction/navigation context;
- Research Vault — this does not store source/evidence corpora;
- Evidence Mesh — this does not solve cross-source evidence interoperability;
- Market Memory — this does not reconstruct historical market episodes;
- a portfolio/watchlist — attention/ownership membership remains under Market OS canonical state.

## 6.8 Complete user journey

A valid first journey is:

```text
Global source search
→ select issuer + exact event hit
→ event workspace opens at exact evidence
→ pin evidence
→ open company/chart lens without losing issuer/event/query/cutoff
→ open Ask Mastermind
→ Ask receives the same explicit reference set
→ return to event/evidence
```

Failure journeys are first-class:

- source no longer displayable due to rights → reference remains, body refuses;
- source corrected → original + correction state shown;
- target surface cannot consume comparison set → preserves the rest and reports unsupported field;
- context expires → explicit reset, never stale hidden carryover;
- event changes → incompatible evidence selection resets, matching current Terminal precedent;
- identity mismatch → transfer refuses.

---

# 7. Reusable Analytical Lens

## 7.1 Ruling

An Analytical Lens is a **versioned deterministic analytical definition over canonical inputs**.

It is not a new metric truth store, not arbitrary code, not an LLM-generated score, and not a Prophet feature merely because a user saved it.

The name `AnalyticalLens` is descriptive in this freeze, not a production schema commitment.

## 7.2 Product job

A user should be able to define an analytical relationship once and reuse it wherever its inputs are semantically compatible.

Examples:

- `Capital Expenditure / Revenue`;
- `Gross Margin - 3Y median Gross Margin`;
- a named spread between two governed macro series;
- an estimate-revision acceleration view when the owner exposes a comparable series;
- a management-commitment completion ratio only if the owner has a deterministic, comparable definition.

The last two examples are not automatically financial metrics; their owning providers remain responsible for input semantics.

## 7.3 Definition concept

```text
AnalyticalLens
  lens_id
  lens_version
  owner_user_or_system
  title
  description
  scope_capability
    single_subject
    comparable_set
    universe_eligible
  inputs[]
    provider_owner
    object_or_metric_id
    basis
    unit
    period_policy
    dimension_policy
    known_at_policy
  expression_ast
  output
    unit
    sign_semantics
    formatting
  applicability
  coverage_policy
  rights_policy
  authority_tier = display_context
  created_at
  supersedes?
```

This is a conceptual contract. The implementation owner must reuse current user-state and metric/query owners rather than mint these fields blindly.

## 7.4 Closed deterministic expression law

The first grammar should be deliberately boring.

Allowed classes may include typed arithmetic and bounded deterministic transforms such as:

- add/subtract;
- multiply/divide with zero-denominator refusal;
- ratio/margin/spread;
- period-over-period delta/growth where period comparability is proven;
- rolling deterministic aggregation over a named input series where the time basis is explicit.

Do not allow arbitrary Python, SQL, JavaScript, network access, hidden model calls, or user text that executes as code.

LLMs may help a user draft a lens. The resulting expression must compile into the closed deterministic grammar and expose its resolved inputs before execution.

## 7.5 FIF boundary for financial lenses

For financial statement/fundamental inputs:

- resolve through FIF's governed metric/query semantics;
- preserve metric ID, basis, units, period, dimensions, revision policy and receipts;
- do not create a parallel `custom_metrics` financial registry that independently decides what Revenue, CapEx, FCF or a segment means.

FIF remains truth. The lens is a reusable expression over that truth.

## 7.6 Unit/basis/dimension law

A lens cannot silently combine incompatible inputs.

Fail closed on unresolved:

- currency mismatch;
- duration vs instant mismatch;
- fiscal-period mismatch;
- consolidated vs segment mismatch;
- GAAP vs non-GAAP ambiguity;
- restated vs as-reported ambiguity;
- per-share vs absolute values;
- issuer vs security grain;
- unavailable denominator.

Any permitted normalization/conversion must be explicit, governed and reproducible.

## 7.7 Sign semantics law

Never silently “fix” source-native signs.

Fiscal's observed `CapEx / Revenue` user metric produced a negative result because CapEx was represented as a cash outflow. Mastermind should treat that as a semantic issue to expose, not hide.

Default behavior:

- preserve source-native sign;
- label sign semantics;
- if a user wants `capital_spend_magnitude`, require an explicit allowed transform with a visible definition;
- the formula receipt must show the transform.

## 7.8 Missing/null law

Missing input is never zero.

Typed outcomes include at least concepts equivalent to:

- `NOT_APPLICABLE`;
- `NOT_COVERED`;
- `SOURCE_UNAVAILABLE`;
- `STALE`;
- `RIGHTS_BLOCKED`;
- `IDENTITY_UNRESOLVED`;
- `INSUFFICIENT_HISTORY`;
- `UNESTIMABLE`;
- `CONFLICTED`.

Exact vocabulary must reconcile with Data OS / owner contracts at implementation time. This freeze does not create a fifth null vocabulary.

## 7.9 Cross-company comparability law

A company-local formula does not become universe-comparable because its arithmetic succeeds twice.

A lens may project to a comparison set or screener only when every input declares a compatible semantic basis across that target population.

Therefore:

- `single_subject` is the safe default;
- `comparable_set` requires owner-confirmed comparable input semantics;
- `universe_eligible` requires measured coverage and an explicit comparability contract;
- partial coverage is displayed as coverage, never silently filtered into a flattering universe.

## 7.10 Correction / replay law

The lens definition and the source truth are separately versioned.

Historical evaluation must bind:

- lens version;
- owner metric/object versions;
- source availability / known-at cutoff;
- formula grammar/compiler version where relevant.

A later source restatement may create a current-restated lens value. It may not rewrite a prior as-known-at lens result.

## 7.11 Evidence law

Every rendered lens result should be able to disclose:

```text
expression
resolved input IDs
input values / typed absence
units/bases/periods
source receipts
calculation steps
cutoff / vintage
```

This is deterministic provenance, not a model explanation.

## 7.12 Authority law

At birth:

```text
may_rank = false
may_gate = false
may_size = false
may_change_ENTRY_OPEN = false
may_originate_trade = false
```

A useful lens may later become a research candidate feature only through the existing owner + Eval/Fusion promotion path. User popularity, visual appeal or intuitive plausibility is not evidence of alpha.

---

# 8. Search and Ask Mastermind integration

This freeze does not create a new search engine.

The desired experience is a consumer contract over existing/future search owners:

```text
query
→ result set from canonical search owner
→ selected result ref
→ ResearchContextRef
→ event/company/source surface
→ exact evidence
→ Ask Mastermind with explicit bounded refs
```

For Earnings/company-event sources, the current E5 architecture remains the natural owner of global primary-source search across transcripts, releases, filings, slides, guidance, commitments, claims, relationships and Q&A.

Portable context adds continuity. It does not own indexing or relevance.

Ask Mastermind must distinguish:

- source-backed statements;
- deterministic lens calculations;
- owner-native statistical states;
- model-generated inference.

The fact that all four are selected in one context does not merge their epistemic authority.

---

# 9. Experience architecture

## 9.1 Research header / context rail

The eventual experience should expose enough active state that a user can tell what they are carrying between surfaces:

- subject/company/security;
- selected event where relevant;
- active concept/query;
- as-of/cutoff mode;
- pinned evidence count;
- comparison set;
- active lens(es).

Do not turn this into a giant persistent toolbar before the first vertical proves the interaction.

## 9.2 Progressive disclosure

First viewport answers:

1. What am I looking at?
2. What changed?
3. What evidence is selected?
4. What expectation/incorporation context is actually estimable?
5. What comparison/lens is active?
6. What is missing, stale or conflicted?

Detailed receipts, formula traces, corrections and source bodies open on demand.

## 9.3 Local state vs portable state

Not every UI selection should travel.

Portable:

- canonical subject/event;
- query and selected result;
- pinned evidence;
- historical cutoff;
- explicit comparison set;
- explicitly selected analytical lens.

Usually local:

- scroll position;
- open accordion;
- chart zoom;
- temporary sort order;
- audio playback time unless entering/leaving the same event-document workflow;
- cosmetic tab state with no analytical meaning.

This boundary prevents context from becoming an unbounded serialization of the UI.

---

# 10. Failure-state architecture

| Failure | Required behavior |
|---|---|
| Wrong/ambiguous listing identity | refuse transfer; show identity problem; never choose silently |
| Source corrected after pin | preserve original reference and cutoff; flag correction; offer corrected view |
| Destination lacks source rights | preserve reference metadata if lawful; refuse body; do not copy from origin |
| Lens input missing | typed absence; no zero fill |
| Lens units/bases incompatible | compile/evaluation refusal with exact conflict |
| Lens denominator zero | deterministic refusal, not infinity/hidden null |
| Comparison population partly uncovered | disclose coverage and excluded/refused subjects |
| User lens deleted/superseded | context reports unavailable/superseded lens; does not silently substitute latest |
| Context expired | visible reset/expired state |
| Destination does not support one context field | preserve compatible fields and report dropped field explicitly |
| Event changes | reset event-incompatible evidence selection, following existing Terminal precedent |
| Historical belief unavailable | `UNAVAILABLE/NOT_COVERED`, not current consensus projected backward |
| Incorporation method unvalidated/unestimable | descriptive raw response may show; no `UNDER_INCORPORATED` claim |
| Model-generated inference conflicts with source | source truth remains visible; inference marked and never overwrites owner state |

---

# 11. Architecture freeze / no-rebuild boundaries

## 11.1 Do not build

- a `market_belief` truth database;
- a universal `expectation_score`;
- a universal `gap_score`;
- a second consensus/estimate store owned by Market OS;
- a second metric registry beside FIF;
- a second source/search index beside owner search planes;
- a `research_context` evidence warehouse;
- a second Neural Web/Brain/Market Memory memory plane;
- a second user-state authority;
- a custom-metric store that redefines canonical financial semantics;
- a generic context object that embeds full restricted document bodies;
- a route from user-created lenses directly into Prophet/Fusion;
- any current Dislocation P0 change from this work;
- any current Earnings E3 change from this work;
- any Market OS A1A runtime change from this work.

## 11.2 Preserve

- FIF financial semantics/query/revision authority;
- Earnings event/source/search roadmap;
- MAS-118 family-specific incorporation science;
- MAS-119 common catalyst expectation/materiality federation;
- MAS-122 D5 transport boundary;
- Data OS/Stock Identity canonical identity;
- existing Terminal event/evidence selection behavior;
- Market OS separate Portfolio/Watchlist truth;
- Eval OS / Conditional Fusion authority boundaries;
- Dislocation P0 blindness.

---

# 12. Supersession ledger

This freeze deliberately supersedes only loose architectural language from the Fiscal discussion, not accepted owner programs.

### Superseded phrase

> “Market-Belief State should become a new canonical primitive/object.”

### Replacement

> **Market Belief is a cross-product composition over canonical owner-native expectation, surprise, positioning and incorporation objects. Common expectation semantics belong to the owner federation; family-specific incorporation belongs to its research owner. No new Market-Belief truth store is created.**

### Still controlling

- Earnings V2 source/event/search/graph plan;
- Financial Intelligence Fabric semantic/query ownership;
- Alpha-E incorporation state-vector law;
- MAS-118 no-universal-gap/family-first science;
- MAS-119 expectation/materiality federation direction;
- MAS-122 D5 specialist-compute / transport-only separation;
- Market OS current A1A sequencing;
- all current no-rank/no-gate/no-duplicate laws.

---

# 13. Capability/value model

## 13.1 User value

Portable Research Context reduces repeated navigation/reconstruction work and makes deep research feel like one continuous investigation rather than a collection of pages.

Analytical Lens turns one-off arithmetic into reusable research tooling while preserving source trace and comparability.

Market-Belief composition makes expectations/incorporation understandable without hiding uncertainty behind a composite score.

## 13.2 Machine value

- exact context refs allow bounded cited Ask Mastermind queries;
- lens definitions create reproducible deterministic research artifacts;
- expectation/incorporation references preserve point-in-time semantics for later learning;
- explicit coverage/refusals prevent false neutral states;
- context telemetry can later measure which research paths are useful without making user behavior an alpha label.

## 13.3 Commercial value

These capabilities support premium workflow differentiation because they reduce analyst effort, improve auditability and make Mastermind's many specialist lobes behave as one product.

They do not require exposing high-authority proprietary signals. A future institutional product can use the same reference/lens architecture over more privileged owner outputs.

## 13.4 Data-moat value

The valuable accumulating data is not “which tab the user clicked.” It is the correction-safe owner-native evidence and longitudinal expectation/response/outcome history.

User-created lenses may reveal useful research demand, but they do not become signal labels without a separately governed research design.

---

# 14. Implementation entrance gates

No runtime implementation is authorized by this freeze. Future work must satisfy the relevant gates below.

## Gate A — expectation federation

Before a general `Market Belief` product composition claims a common `ExpectationBaseline`, MAS-119 (or its canonical successor) must reconcile domain-specific expectation semantics across at least Earnings plus one non-earnings specialist domain.

Until then, product views may display native owner expectations side by side with explicit labels; they must not imply one universal normalized baseline.

## Gate B — incorporation

No product may display `UNDER_INCORPORATED`, probability of underreaction, or equivalent authority merely from low price response.

MAS-118's family-specific method must first be estimable and independently validated for that family. Raw/descriptive response remains separate.

## Gate C — portable context persistence

Before persistent saved research contexts are built, the implementation wave must census existing `terminal-user-services` / Terminal user-state stores and prove there is an existing canonical place or explicitly return for an ownership ruling.

Ephemeral reference transfer can be designed earlier; no new database is presumed.

## Gate D — Analytical Lens financial semantics

A financial lens implementation must resolve its inputs through the accepted FIF query/metric semantics available on the target environment. Fixture-only FIF capability cannot be marketed as broad production lens coverage.

## Gate E — search

A search-to-context vertical must consume an existing canonical search provider. It may not build an index merely to prove context portability.

## Gate F — identity

Every cross-surface subject transfer must use canonical identity. No ticker-only implementation proof is accepted.

---

# 15. Bounded future verticals

These are sequencing candidates, not authorized runtime work.

## RCTX-1 — first Portable Research Context vertical

**Observable mission:** one real company-event search result can open the existing event workspace, pin exact evidence, open Ask Mastermind, and return with company/event/query/evidence/cutoff references intact; wrong identity, corrected evidence, rights refusal and event change are explicit.

**Why first:** it makes an existing research flow materially better without requiring historical consensus, a new formula engine or predictive authority.

**Non-goals:** no persistent workspace store, no global UI rewrite, no new search index, no portfolio, no Prophet.

## LENS-1 — first Analytical Lens vertical

**Observable mission:** one deterministic two-input financial ratio over a production-proven FIF-supported issuer can be defined, rendered with full formula/input receipts, then applied to a predeclared comparison set only where semantic comparability is proven.

**Non-goals:** no screener-wide launch, no arbitrary code, no LLM formula execution, no rank/score, no new financial metric registry.

## BELIEF-1 — first Market-Belief composition vertical

**Observable mission:** one event shows owner-native expectation state plus a separately labeled price-response/incorporation state, with clocks/coverage/conflicts visible and no scalar.

**Gate:** MAS-119/MAS-118 inputs must exist at the authority level claimed. Otherwise the UI remains a typed partial.

One independently useful capability per PR remains the law. These three verticals should not be bundled.

---

# 16. Required operator handoff for the first implementation wave

When a future Chairman instruction authorizes `RCTX-1`, the operator packet must include:

- **Mission:** exact search → event → evidence → Ask → return journey above.
- **Why:** prove Mastermind behaves like one research product without duplicating truth.
- **Authority precedence:** this freeze; current Market OS workstream; current Earnings/search owner; current Terminal Company Intelligence contract; current identity owner; Data OS time/null law.
- **Current state:** fresh default-branch SHAs and any open PRs touching Terminal navigation, Company Intelligence, Brain/Ask, user-state, search or identity.
- **Scope:** existing surfaces and a reference/view-model seam only.
- **Non-goals:** persistence, lenses, belief scoring, E3, P0, Prophet, Portfolio A1A.
- **Journey:** success + identity/correction/rights/expiry/event-change failures.
- **Contracts:** references only, canonical identity, explicit cutoff, typed missing, entitlement re-resolution.
- **Method:** deterministic reference composition; zero statistical/model authority.
- **Acceptance:** browser proof at 1440/820/390 plus exact evidence/identity/correction tests.
- **Stop:** after one production-proven flow; do not absorb LENS-1 or BELIEF-1.
- **Return:** head SHA, changed files, CI, browser receipts, current owner-state delta, unresolveds and exact next gate.

---

# 17. Research/data continuation: historical expectations

Historical Street-consensus truth is strategically valuable enough to deserve a separate source/data investigation, but it is **not** coupled to RCTX-1.

A future data-source commission should answer:

1. Which licensed providers expose point-in-time analyst estimate vintages, individual/aggregate revisions, dispersion and coverage with lawful retention/replay rights?
2. What history depth, issuer coverage and adjustment/restatement semantics exist?
3. Which clocks represent estimate creation, publication/vendor availability, correction and Mastermind capture?
4. Can the data support Earnings surprise research and MAS-118 incorporation experiments without survivor/look-ahead bias?
5. What are redistribution/public-display/API restrictions?
6. What cost is justified relative to the intelligence unlocked?

Until that work is completed, absence remains absence.

---

# 18. Acceptance standard for this architecture wave

This records-only wave is accepted only if:

- no runtime/schema/data/product path changes;
- no new workstream/program/control plane is minted;
- Market Belief is explicitly composition, not truth store or scalar;
- MAS-118 / MAS-119 / MAS-122 boundaries are preserved;
- FIF remains financial semantic authority;
- identity is canonical-reference only;
- Research Context is references-only and default-ephemeral;
- Analytical Lens is deterministic, typed, source-reversible and zero-authority;
- E3 and Dislocation P0 remain untouched;
- Market OS A1A remains untouched;
- the exact next implementation vertical is bounded and gated.

No production proof is owed because no production capability is built. The correct capability state of these new primitives remains `SPEC_ONLY` after this freeze.

---

# 19. Exact next action

After this records PR receives Sol adversarial review and lands, **do not start a broad Research OS build**.

Primary continuation:

> When the Chairman explicitly authorizes the first implementation wave and current Market OS A1A / Terminal / Earnings-search / identity ownership gates are rechecked, commission `RCTX-1` only: portable reference continuity for one real search → event → evidence → Ask Mastermind → return journey, with no persistence and no new store.

Independent work may continue in parallel under its own owners:

- MAS-118 Evidence–Price Gap research;
- MAS-119 Catalyst Federation when separately launched;
- MAS-122/V4 D5 gating sequence;
- Earnings E3 under its current handoff;
- Dislocation P0 under its blinded program;
- FIF under its current wave;
- Market OS A1A completion.

None of those programs is advanced, blocked or redefined by this records-only architecture freeze.
