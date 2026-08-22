# DEFENSE D5R — Program / Mission / Capability / Product Graph Architecture Freeze

**Status:** SOL AUTHORIZED — RESEARCH / ARCHITECTURE ONLY. D5 implementation NOT authorized. D6+ NOT authorized.
**Frozen against:** `origin/main` `33d70f5ce4b36329e8acfb285557f4c9d3c72589` (2026-08-22T02:28Z).
**Program:** Defense Procurement & Industrial Base Intelligence OS V3 (`WS:DEFENSE-PROCUREMENT-V3`).
**Companion:** `DEFENSE_D5_PROGRAM_GRAPH_IMPLEMENTATION_HANDOFF.md` (acceptance gates §0 there govern the D5 build).
**Decision records:** `DEC:D5-OWNER-IS-GOVREV-ONTOLOGY-PLUS-COMPOSED-DOSSIER`, `DEC:D5-PILOT-IS-VIRGINIA-CLASS-SSN`.

The D5 user job this architecture must serve, end to end, point-in-time, evidence-bound:

```
mission requirement → capability → program → platform/product
→ budget/acquisition evidence → prime(s) → reviewed supplier/product roles
→ public issuer(s) → next official milestones
```

Every hop is deterministic-join or human-reviewed; every absence is a typed state, never a blank.

---

## 1. Current-estate census (what exists; all claims cited)

| Plane | Contract / module | State on frozen main | D5-relevant fact |
|---|---|---|---|
| Recipient identity | `contracts/government_revenue/government_recipient_entity_graph.v1.schema.json` | live, defense21-v1 | **Closed by design**: 13 top-level keys, `additionalProperties: false` on every def, `schema_version` const-pinned, reviewState closed at `confirmed\|reviewed\|analyst_approved`. Self-describes as "Reviewed, evidence-bound, point-in-time recipient attribution graph." No program/capability/platform def exists. |
| Award/action events | `engine/government_revenue/point_in_time.py:148` `canonical_award_identity` | live | Stable event identity = `generated:<id>` preferred, `award_key`, `piid:` last resort. Program-adjacent fields on awards are **free-text source strings only**: `major_program`, `dod_acquisition_program`, `dod_claimant_program`, `program_acronym`, derived `program` (`collectors/usaspending_awards.py:1271-1289`). No PE codes, no treasury/federal account fields. |
| Budget/PE | `contracts/government_revenue/government_budget_program_graph.v1.schema.json`, `engine/government_revenue/budget_program.py`, `collectors/dod_budget.py` | contract + producer exist; **artifact never produced**; `DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED = False` (`collectors/dod_budget.py:37`); publication hard-raises (`scripts/build_government_revenue.py:713-715`) | Budget-native program nodes exist in schema: `program_key` `^dod-program:...`, `kind ∈ {procurement_line_item, rdte_program_element}`. `government_budget_edge.v1` separates automatic `source_native_identifier` edges (`review_state: official`) from manual `reviewed_documentary` program→award edges requiring **dual evidence** (≥1 budget doc + ≥1 award doc) and `review_state ∈ {reviewed, confirmed}`. `config/government_revenue/budget_program_reviewed_edges.v1.json` exists with `edges: []`. Live product state = `projection_missing` (`workspace.py:451-457`). |
| Identity atlas (D2) | `government_revenue_identity_atlas.v1` | live | Issuer path via reviewed graph walk only; states `verified_live \| listing_terminated \| not_in_si_universe` and `reviewed \| not_asserted`; gap code `no_reviewed_exact_path` (`identity_atlas.py:62`). "Never carries an event or award reference." |
| Temporal (D3) | `DEFENSE_D3_TEMPORAL_CONTRACT_AND_CHANGE_TAPE_SPEC.md`; `workspace.py:389-457` | live | Typed rail `failure_state ∈ {null, source_unavailable, projection_missing}`; `source_published_at` MUST NOT be invented (named null); dual clocks + late-discovery first-class. |
| Company bridge (D4) | shipped #6123/#6173/#6192 | live, Sol accepted 2026-08-21 | Government fact bytes immutable in company context; receipt links fail closed on sha mismatch. |
| GMI Theme Graph | `contracts/theme_graph/nodes.v1.schema.json:26`, `edges.v1.schema.json` | live spine (W1b: `MEMBER_OF`/`EXPRESSES`/`TRACKS` only) | Node kind `policy_program` is **declared, never emitted** (zero rows). Economic edges `SUPPLIES/ENABLES/BOTTLENECK_OF/BENEFITS_FROM/CATALYST_OF` are **reserved-null**, owner `gmi-theme-graph` (W4 planned, blocked on a merge-order ruling). `context_only`, all six authority flags false. |
| Ownership census | `research/economic_propagation/D0_OWNERSHIP_AND_GRAPH_CENSUS.md` | standing ruling (2026-08-18) | §2.5 assigns "program/mission/capability/product (D5)" to `government-revenue-foresight`. §1 row: customer/supplier economic object is **MISSING — "do not mint under Defense D1 or Bio P0."** Recommendations: "Do **not** create a new graph store"; GMI W4 + GR3b + **Defense D5/D10 are the three existing build ramps**; `D0_THREE_GRAPH_SEPARATION_MAP.md` §6: Graph-1 store = "GMI edge types … not a parallel parquet." |
| Stock Identity | `universe_snapshot_v1`; atlas `central:<TICKER>` | live | Identity owner. Issuer join for the defense estate is the reviewed-graph walk to `central:<TICKER>` (D0R F2). D5 never mints tickers or a security master. |
| Review machinery | `scripts/propose_government_revenue_recipient_graph.py` / `curate_…` / `_REVIEWED_GRAPH_STATES` (7 gate sites in `entity_resolution.py`) | live | Discovery writes a candidate file only (`guard_output_path` refuses the canonical path); a human-reviewed worksheet is admitted atomically by the curate script. Producers may only emit `proposed` (`issuer_graph_expansion.py:74`, `ProposalAuthorityError`). |

Fleet/lane check at freeze time: no open PR or worktree touches `research/defense_intelligence/`, the recipient graph, the budget-program plane, or GMI theme-graph contracts (PR list read 2026-08-22T02:29Z).

---

## 2. Owner adjudication — where reviewed program truth lives

**Question:** where does reviewed program / mission / capability / product truth canonically live, and how are economic/supplier relationships composed with it without creating a parallel graph?

### Option A — extend `government_recipient_entity_graph.v1`. REJECTED.
The contract rejects it by construction, not by preference: closed 13-key top level, `additionalProperties: false` on every def, const-pinned `schema_version`, and a producer docstring that names the closure as a deliberate anti-drift device ("a candidate cannot carry an extra status field and still load"). Its self-description is identity-scoped. Adding domain ontology would break the exact discipline that makes defense21-v1 trustworthy, and D2's own law ("never carries an event or award reference") shows the estate already refuses scope creep on identity artifacts.

### Option B — put D5 objects into GMI Theme Graph. REJECTED.
`policy_program` exists only as an unused enum literal; nothing defense-shaped has ever been emitted. GMI is `context_only`, thematic, and its own `does_not_own` plus the ownership census bound it away from acquisition identity. Its node grammar has no program/platform/variant identity, and its TRANSMISSION wave is blocked on an unrelated merge-order ruling — parking defense truth there would couple procurement truth to a blocked thematic lane. Decisively: `D0_THREE_GRAPH_SEPARATION_MAP.md` §6 routes GovRev **into** GMI as an input ramp for future economic edges; making GMI the owner would invert the estate's own separation ruling. What survives from B: D5 records must stay consumable by GMI W4 (stable IDs + evidence refs), so the composition happens later in GMI's vocabulary, owned by GMI.

### Option C — independent Defense Program Graph. REJECTED.
The ownership census already assigns this truth category to `government-revenue-foresight` (§2.5) and forbids a fourth spine. Program/capability/platform truth is procurement-domain truth — the same program that owns awards, recipients, and budget references. An "independent" graph would be duplicate graph infrastructure with a second review pipeline, exactly what the commission presumptively disallows; no evidence surfaced that it is a genuinely different canonical truth category.

### Option E (surfaced by census) — extend `government_budget_program_graph.v1`. REJECTED.
The budget graph's `program` nodes are **budget-exhibit-native** (`dod-program:{kind}:{component}:{appropriation}:{native_identifier}`, kind closed at P-1 line item / R-1 PE): identity IS the exhibit code, per-document, per-FY. An acquisition program (Virginia-class SSN) spans multiple exhibit lines, appropriations, and decades, and must exist and be reviewable **now**, while the budget artifact is hard-disabled and its acquisition is D6 scope. Tenanting acquisition identity inside the budget graph would (a) invert the dependency — D5's core object could not exist until D6 ships; (b) conflate two truth categories the estate itself separates (request ≠ appropriation ≠ obligation; exhibit-line identity ≠ acquisition-program identity). The budget graph remains the budget owner and a future join **target**.

### Option D — canonical domain-ontology records + composed read model. **SELECTED.**
D5 owns exactly one new canonical truth category — reviewed acquisition-domain ontology and source-bound role assertions — as a closed contract in the GovRev plane, and the user-facing Program Dossier is a **composed read model** that joins, at read time, with no new global supergraph:

```
D5 program ontology (new, reviewed)
+ defense21 recipient identity        (reference — never fork)
+ GovRev award/action events          (reference by canonical_award_identity — never fork)
+ budget owner                        (reference; projection_missing until that plane produces)
+ Stock Identity via identity atlas   (reference — never mint)
+ GMI economic relationships          (absent today: reserved-null; shown as not_asserted, never fabricated)
```

This is the same two-artifact shape the estate has already ratified twice (recipient graph + identity atlas; budget graph + workspace rails), and it is the only option that satisfies both "no parallel graph" and "program truth must exist before D6."

---

## 3. The D5 canonical contract (frozen names; no code in D5R)

**Contract:** `government_program_ontology.v1` at `contracts/government_revenue/government_program_ontology.v1.schema.json`.
**Canonical artifact:** `data/government_revenue/program_ontology.json`.
**Producer discipline:** `scripts/propose_government_program_ontology.py` (discovery → candidate file only, `proposed` rows, output-path guard) and `scripts/curate_government_program_ontology.py` (atomic admission of a human-reviewed worksheet) — byte-for-byte the recipient-graph propose/curate pattern. Engine reader: `engine/government_revenue/program_ontology.py`.
**Contract discipline (inherited, mandatory):** closed top-level key set; `additionalProperties: false` on every def; const-pinned `schema_version`; the verbatim all-false display-tier `AUTHORITY` block (`tier: display`, `context_only: true`, `can_rank/size/gate/originate_signal/add_candidates/escalate: false`); an `evidence` table whose rows carry receipt id + sha256 + source URL + retrieved_at; top-level `conflicts` and `overrides` collections with the recipient-graph override action semantics.

### 3.1 Object model (the minimum D5 vertical — deliberately reduced)

The V3 masterplan's broad vocabulary (threat, conflict, operation, munition, sensor, payload, software, component, material, fleet, readiness…) is **not** frozen into D5. D5 freezes five record kinds and three intra-ontology edge kinds. Everything else is display prose or a later wave.

| Record | ID grammar | Required fields (beyond the temporal quadruple of §5) | Notes |
|---|---|---|---|
| `program` | `acq-program:<slug>` | `name`, `aliases[]` (reviewed), `source_identities[]`, `phase` (closed: `development \| production \| sustainment \| restructured \| terminated`), `sponsor_agency` (verbatim official string) | The slug is minted once at first review and never re-derived from the name; renames/restructures append a successor record (§5). `source_identities[]` rows: `{system ∈ {p1_line_item, rdte_pe, sar_msar, official_program_page, contract_announcement}, native_identifier, evidence_ref}` — identity evidence, never budget figures. |
| `capability` | `capability:<slug>` | `name`, `need_statement` (evidence-bound prose from an official source), `source_identities[]` | D5 carries ONE capability layer. Mission/threat/conflict cascade is explicitly out (D6+). The user-job "mission requirement" hop is answered by the capability record's evidence-bound `need_statement`. |
| `platform` | `platform:<slug>` | `name`, `program_id`, optional `variant_of` (another `platform:` id), `source_identities[]` | Blocks/variants (Block V, Block VI) are `platform` records with `variant_of`; succession appends, never edits. |
| `role_assertion` | `prog-role:<sha12>` (content-derived from `program_id \| entity_id \| role \| valid_from`) | `program_id` (or `platform_id`), `entity_id` (a defense21 legal-entity id — never a raw name, never a ticker), `role` (closed: `prime_contractor \| teammate_subcontractor \| supplier`), `role_scope` (evidence-bound prose, e.g. "naval nuclear reactor components"), `shared_scope: bool` (true when the evidence sentence covers multiple programs), `evidence_refs[]` (**dual evidence**: ≥1 document establishing the role + ≥1 establishing the program identity in that document; one document may satisfy both only when it names program and role in the same source-native statement) | This is the supplier law's carrier. Mirrors `government_budget_edge.v1 reviewed_documentary` discipline. `economic_weight` does not exist as a field — role ≠ exposure share. |
| `milestone` | `prog-milestone:<sha12>` | `program_id`, `kind` (closed: `budget_event \| contract_event \| delivery_event \| review_event`), `title`, `date` or `window {from,to}`, `evidence_refs[]` | Official forward-looking statements only. The dossier's "next" rail reads these; no milestone exists without an official document. |

Intra-ontology edges (closed): `implements_capability` (program→capability), `part_of_program` (platform→program, carried as `program_id`), `variant_of` (platform→platform). No other edge kind exists in v1; adding one is a contract version bump with its own review.

### 3.2 Review states and authority tiers

Three tiers, matched to the estate (this is stricter than "deterministic + human"):

1. **`official` (automatic)** — does NOT exist inside D5 v1. Automatic source-native rows remain the budget plane's tier. Every D5 record and edge is human-admitted.
2. **`proposed`** — the only state the discovery script may emit; structurally inadmissible to the canonical artifact (curate refuses candidates as canonical; loader refuses `proposed` rows).
3. **`confirmed | reviewed | analyst_approved`** — the recipient graph's closed reviewState enum, reused verbatim as the admission states.

LLM boundary (A7-consistent): a model may draft alias candidates or summarize evidence **into the candidate file only**, tagged with its provenance; the loader/curator rejects any row carrying `FORBIDDEN_INPUT_KEYS`/`FORBIDDEN_ASSOCIATION_METHODS` provenance (`llm_assertion`, `search_snippet`, `similarity`, …, per `issuer_graph_expansion.py:87-114`). A model may never originate program IDs, budget IDs, supplier relationships, validity dates, or economic exposure, and no numeric confidence field exists anywhere in the contract.

### 3.3 What D5 does NOT own (binding no-rebuild recap)

- **No tickers / security master** — issuers only via defense21 → identity atlas → `central:<TICKER>`.
- **No recipient identity** — `entity_id` values must exist in the reviewed recipient graph; unknown entity ⇒ the role stays in the candidate file as `proposed` with a rejection-ledger row.
- **No award forks** — awards referenced by `canonical_award_identity` strings and workspace event ids only.
- **No budget truth** — no P-1/R-1 parsing, no figures. A reserved, empty-until-D6 `budget_program_keys[]` field on `program` is the frozen join point to `dod-program:*` keys; populating it requires the budget artifact to exist AND a reviewed link. Until then the dossier budget rail is `projection_missing`.
- **No economic edges** — no `defense_supplier_graph.json`, no `SUPPLIES`-shaped vocabulary. D5 role assertions are program-participation facts (procurement domain); GMI W4 may later consume them as an input ramp, in GMI's vocabulary, under GMI's ownership.
- **No company facts** — Earnings/SEC owner; D4 bridge is the join.
- **No facility/BOM/capacity** — D8/D10.

---

## 4. Composed read model — `government_program_dossier.v1`

**Contract:** `contracts/government_revenue/government_program_dossier.v1.schema.json`. **Artifact:** `data/government_revenue/program_dossier.json` + site twin `site/government-revenue-data/program-dossier.json`. **Composer:** `engine/government_revenue/program_dossier.py`, invoked from `scripts/build_government_revenue.py` beside the workspace build. Read-only composition; owns zero truth; every section carries its owner's ids so the UI can deep-link.

Per-program rails, each with a typed state (vocabulary in §6):

| Rail | Composes from | Typed states |
|---|---|---|
| `program_identity` | D5 ontology | `reviewed` / `not_asserted` / `conflicted` |
| `capability` | D5 ontology | `reviewed` / `not_asserted` |
| `awards` | award plane via reviewed award↔program links (D5 v1: award references admitted as evidence on role assertions and milestones; a general program→award edge set is the budget owner's `reviewed_documentary` shape, not duplicated here) | `current` / `partial` / `source_unavailable` |
| `budget` | budget owner | `projection_missing` (today) / `source_unavailable` |
| `participants` | D5 role assertions × defense21 × atlas | per-row `reviewed` + issuer state (`verified_live` / `listing_terminated` / `not_in_si_universe`); rail-level `not_asserted` when empty |
| `economic_relationships` | GMI (reserved-null today) | `not_asserted` — rendered as "no reviewed economic-relationship data", never fabricated |
| `milestones` | D5 ontology | `reviewed` / `not_asserted` |

The IRDM P00032 award view keeps its D1–D4 rails untouched and gains exactly one D5 field: `program_link: {state: not_asserted, reason_code: no_reviewed_exact_path}` — the honest null (§8, test T1).

---

## 5. Temporal and correction law (binding; estate field names)

Every D5 record and edge carries the graph-plane temporal quadruple, exact names non-negotiable (`entity_resolution.py:65`): **`known_at`, `valid_from`, `valid_to` (nullable), `evidence_refs`** — RFC3339 with explicit UTC offset (`_strict_datetime` discipline). The artifact header carries `graph_known_at` / `graph_effective_at`; the loader must refuse certification on future leakage exactly as `entity_resolution.py:345-353` does (`future_known_claim`, `future_effective_claim`, `future_*_at_analysis_asof`, `evidence_known_after_claim`, `evidence_retrieved_after_known_at`).

- **Never backdate knowledge.** Evidence dated 2025 learned in August 2026 ⇒ `valid_from` may be 2025 (if the evidence establishes it), `known_at` = the 2026 collection time. A replay at any `analysis_as_of` before `known_at` returns the record as absent. "A mapping learned later cannot appear in an earlier replay."
- **`source_published_at` MUST NOT exist as a key** (D3 law — named null).
- **`known_at.semantic` must never be `"official"`** (D0R F3).
- **Renames / restructures / variant changes append, never rewrite.** The predecessor record's id, `known_at`, `valid_from`, and `evidence_refs` stay byte-identical; a successor record is appended with its own clocks and evidence and a **`predecessor_id`** field (new mint for the graph plane, sibling of the event plane's `prior_source_identity`) plus `succession_reason` (closed: `renamed \| restructured \| variant_added \| superseded_evidence`). Names are attributes on time-boxed rows; identity is the minted id.
- **Source corrections** append (successor row + predecessor close-out row); receipts are never overwritten (D0R F2).
- **Reviewer reversal** is an appended `override` row (recipient-graph action vocabulary: `retire_edge`, `block`, …) that changes resolution only for `analysis_as_of ≥` the override's `known_at`. Reversal-by-mutation is forbidden and untestable under T2's byte-identity assertion.
- **Conflicts fail closed.** Two admissible incompatible claims ⇒ `resolution_state: conflicted`, attribution withheld, BOTH sides' evidence kept, a `conflicts[]` row appended; the underlying records stay visible. `unknown != false`; `missing != zero`.

---

## 6. Failure-state vocabulary (reuse-first; commission code → frozen form)

Machine enums are lowercase snake_case in artifacts; bilingual display copy lives in the template keyed by the enum (D3 law). The commission's uppercase codes freeze as:

| Commission code | Frozen artifact form | Provenance |
|---|---|---|
| `PROGRAM_REVIEWED` | record present with reviewState ∈ `confirmed\|reviewed\|analyst_approved` | recipient graph enum, reused |
| `PROGRAM_UNRESOLVED` | `program_link.state: not_asserted` + `reason_code: no_reviewed_exact_path` | atlas vocabulary, reused |
| `CAPABILITY_UNRESOLVED` | capability rail `not_asserted` | atlas vocabulary, reused |
| `BUDGET_PROJECTION_MISSING` | `projection_missing` | existing shipped state (`workspace.py:417`); do not mint a `budget_` prefix variant |
| `SUPPLIER_ROLE_UNRESOLVED` | participants rail / row `not_asserted` | atlas vocabulary, reused |
| `RIGHTS_BLOCKED` | `rights_blocked` | D0R E product typed-state list, reused |
| `SOURCE_UNAVAILABLE` | `source_unavailable` | existing shipped state, reused |
| `HISTORICAL_ONLY` | role assertion with `valid_to` in the past + issuer state `listing_terminated` (SPR pattern); rail chip "historical only" | atlas + G1b, composed — no new enum |
| `CONFLICTING_EVIDENCE` | `conflicted` + `conflicts[]` row | `entity_resolution.py` states, reused; the string `conflicting_evidence` exists nowhere in the estate and is not minted |

New mints (only these, all flagged as gaps by the estate census): the `role` enum (`prime_contractor \| teammate_subcontractor \| supplier`), the `succession_reason` enum + `predecessor_id` field, one `unverified_supplier_language` text-annotation code (extends the closed `_action_text_annotations` family for prose supplier mentions), and a typed `OntologyInputError` for the producer.

---

## 7. Pilot freeze

### 7.1 Positive pilot: **Virginia-class SSN / undersea warfare** (`DEC:D5-PILOT-IS-VIRGINIA-CLASS-SSN`)

Compared against Patriot/GEM-T on the commission's six criteria (full source census with per-claim verification levels in the implementation handoff §3; summary):

- **Exact source-native identity:** VERIFIED — Navy P-1 pattern (Appropriation 1611N Shipbuilding & Conversion Navy, BA-02, Line "Virginia Class Submarine" + Advance Procurement sibling; FY2011 exhibit direct-extracted) plus DoD acquisition-report identity "SSN 774 Virginia Class Submarine" (MSAR). Current-FY SCN book confirmed to exist at its official URL; its PDF-portfolio format defeated this session's parsers — recorded as a D6/tooling dependency, not assumed.
- **Prime structure:** one prime (GD Electric Boat — CRS RL32418, direct-read: "the program's prime contractor") with one documented teaming yard (HII/NNS, ~50-50 construction split on the same hulls). The comparison candidate decomposed under census into **two programs with two different primes** (PAC-3 MSE → Lockheed; GEM-T → RTX/Raytheon) plus a four-company supplier lattice and a German production JV — and GEM-T has **no located official budget-line identity at all** (FMS/DCS-heavy). "Patriot/GEM-T" therefore fails the bounded-complexity and exact-identity criteria as a single pilot.
- **Supplier rail:** BWXT first-party IR release ties naval nuclear reactor component contracts to "Virginia-class and Columbia-class submarines … as well as … Ford-class" — first-party, sentence-level, **shared-scope** (three programs in one sentence), which is exactly the nuance `role_assertion.shared_scope` exists to represent honestly. Decisive tie-breaker: BWXT's issuer identity already has reviewed chains in defense21-v1 (D2), so the full ontology→identity→issuer chain is executable in the current estate with zero new identity work.
- **Milestone:** Block VI construction award, 2026-07-29 (official contracts page + GD first-party release, $42.1B, SSN 814-822 + material for a tenth boat) and AUKUS Pillar-1 timeline — citable, forward, official.
- **Rights:** all government sources are public-domain US works; corporate materials quotable with attribution; no paywall, no licensed-ontology dependence.
- **Complexity bound:** rich enough to exercise every hop (capability → program → block variants → two yards → two issuers → supplier → milestone) without the F-35 universe.

PAC-3 MSE is recorded as the runner-up (it produced this census's single cleanest verified current identifier — Army MYP-1 exhibit, direct-extracted) and is a natural second vertical **after** D5 closes; not authorized here.

**Verification honesty (binding on D5):** several pilot sources were located at search-synthesis confidence only (official .mil article pages 403'd this session). The architecture freeze does not depend on their verbatim text; the **admission** of any role assertion or milestone at implementation time requires the actual document fetched, receipted (sha256 + URL + retrieved_at), and reviewed — search synthesis is not admissible evidence, per §3.2.

### 7.2 Negative control: **IRDM / P00032** (mandatory)

The award `HC101319C0006` mod `P00032` (DoD/DISA, $18,416,666.66, effective 2026-05-12, known 2026-08-12, late discovery) remains program-null. `DISA + SATCOM + contract description → program X` is a forbidden inference. A successful D5 renders "Program relationship: unresolved / not asserted" on the live IRDM rails while every D1–D4 rail is byte-unchanged. This is test T1 and the standing golden-example law (D0R F: "if a proposed field cannot be filled on this case, it is not minimum").

---

## 8. Adversarial acceptance tests (frozen; implement as stated)

Object roles: PR = program record, RA = role assertion, DRM = dossier read model, RG = reviewed recipient graph, EV = event row. All fixtures are committed test fixtures (D4 CI-wiring law: law gates ride `gate: code` with frozen fixtures, never nightly-rewritten artifacts).

1. **T1 — IRDM stays program-null.** Given the frozen P00032 EV and zero RAs citing that award: DRM emits `program_link {state: not_asserted, reason_code: no_reviewed_exact_path}`; no program name token renders; government fact bytes unchanged; no `source_published_at` key anywhere.
2. **T2 — rename does not rewrite.** Given PR "Alpha" and a later restructure to "Beta" (observed `K2`): predecessor PR is byte-identical post-rebuild; successor carries `predecessor_id` + own clocks; replay at `analysis_as_of < K2` renders "Alpha" and never "Beta"; historical awards render under the name valid at their `effective_at`.
3. **T3 — prime role does not smear to siblings.** Given RA(prime) on `legal:X:parent` and two RG subsidiaries with no RA: exposed set = parent only; no `economic_weight` field exists; the "does not allocate … to an issuer" limitation renders.
4. **T4 — prose supplier mention is not an edge.** Given an EV description containing "supplied by ACME": zero RAs created; at most an `unverified_supplier_language` annotation; rejection ledger row recorded; forbidden-provenance keys refused at the door.
5. **T5 — request ≠ appropriation ≠ obligation.** Budget rail carries the four-stage `source_coverage` (`president_budget_request` / `authorization` / `appropriation_enacted` / `execution`); request figures never sum or compare against obligations in one numeric node; EN and ZH label assertions.
6. **T6 — no identity from ticker.** Input rows carrying `discovery_query_ticker` etc. are rejected (`forbidden_provenance_key_present`); no ticker string appears in any minted id.
7. **T7 — multiple primes, different roles.** Three RAs (two `prime_contractor`, one other role) on one PR return as a set, each with own window + evidence; role multiplicity is NOT `conflicted` — while identity-axis multiplicity still fails closed (`multiple_active_ownership_paths` contrast pin). The ownership walker is not reused for roles.
8. **T8 — one issuer, multiple legal entities.** Both IRDM entities' participation paths render separately (own entity, own evidence), never deduped or summed; issuer reached only via the reviewed ownership walk.
9. **T9 — missing budget rail.** No budget artifact ⇒ `freshness.budget {status: unavailable, failure_state: projection_missing, observed_at: null, records_visible: 0}` exactly; deleted rail block ⇒ unavailable, never valid-empty; `loading` is never a settled state.
10. **T10 — ownership cannot backdate exposure.** Acquisition edge `valid_from` 2025-12-08, award `effective_at` 2025-06-01 ⇒ `unresolved / ownership_path_missing` at the event clock; also invisible before its `known_at`; a post-acquisition award resolves — pinning the clock, not a blanket refusal.

---

## 9. Experience architecture (Program / Platform Dossier)

Reference composition: `research/defense_intelligence/evidence/compositions/d5-program-dossier-virginia.html` (real pilot data, 1440/820/390 via CSS, shared `d0r-target.css`, sibling of the frozen D1/D2 targets). D0R H composition #5 law applies: glance = phase + contract type + latest relevant official program state; changed = budget/award/milestone; why = quantity/economics/execution; evidence = exact official sources; next = next official milestone.

First screen answers, in order: What is this? Why does government need it? What changed? Which listed companies have reviewed access? What remains unresolved? What happens next? — with the unresolved column carrying the typed states of §6 in plain words ("Budget request rail unavailable", "No reviewed economic-relationship data", "Supplier scope shared across three programs"). Technical IDs (`acq-program:*`, UEI, `prog-role:*`) live in the inspector tier. EN/ZH parity; no translated `title=` attributes; no third header; no frontend-computed order; **no graph visualization as the primary UX** — the graph answers investor questions; it is never rendered as nodes for their own sake.

---

## 10. What D5R deliberately leaves open (nothing a cold builder must decide)

- Whether the dossier ships as a new mode of `government_revenue.html` or a sibling page — frozen in the handoff (§2: new `mode=programs` view inside the existing page family; no new header).
- FY2026 SCN exhibit parsing (PDF portfolio) — a D6 dependency; D5 renders the identity from already-verified historical exhibits + MSAR identity and states the current-FY gap.
- GMI W4 consumption of D5 role assertions — GMI's wave, GMI's vocabulary, not started here.

Anything not listed here is frozen above or in the handoff; if a builder finds a decision this document does not answer, that is a D5R defect to report, not a choice to make silently.
