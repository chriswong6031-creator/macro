# DEFENSE D5R — Program / Mission / Capability / Product Graph Architecture Freeze

**Status:** SOL AUTHORIZED — RESEARCH / ARCHITECTURE ONLY. D5 implementation NOT authorized. D6+ NOT authorized.
**Frozen against:** `origin/main` `33d70f5ce4b36329e8acfb285557f4c9d3c72589` (2026-08-22T02:28Z).
**Program:** Defense Procurement & Industrial Base Intelligence OS V3 (`WS:DEFENSE-PROCUREMENT-V3`).
**Companion:** `DEFENSE_D5_PROGRAM_GRAPH_IMPLEMENTATION_HANDOFF.md` (acceptance gates §0 there govern the D5 build).
**Precedence (total order, on any conflict):** this freeze document > the implementation handoff > the DEC records (decision narrative) > the reference composition. A conflict discovered anywhere in that chain is a defect to report and repair, never a choice to make silently.
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
| Budget/PE | `contracts/government_revenue/government_budget_program_graph.v1.schema.json`, `engine/government_revenue/budget_program.py`, `collectors/dod_budget.py` | contract + producer exist; **artifact never produced**; `DOD_BUDGET_PRODUCTION_ACTIVATION_ENABLED = False` (`collectors/dod_budget.py:37`); publication hard-raises (`scripts/build_government_revenue.py:715-718`) | Budget-native program nodes exist in schema: `program_key` `^dod-program:...`, `kind ∈ {procurement_line_item, rdte_program_element}`. `government_budget_edge.v1` separates automatic `source_native_identifier` edges (`review_state: official`) from manual `reviewed_documentary` program→award edges requiring **dual evidence** (≥1 budget doc + ≥1 award doc) and `review_state ∈ {reviewed, confirmed}`. `config/government_revenue/budget_program_reviewed_edges.v1.json` exists with `edges: []`. Live product state = `projection_missing` (`workspace.py:451-457`). |
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
The ownership census already assigns this truth category to `government-revenue-foresight` (§2.5), and its recommendations run through exactly three sanctioned build ramps (GMI W4, GR3b, Defense D5/D10) with "do not create a new graph store" as rec-1 — an independent store would be a fourth spine in exactly the sense the census's honesty-layer ruling rejects. Program/capability/platform truth is procurement-domain truth — the same program that owns awards, recipients, and budget references. An "independent" graph would be duplicate graph infrastructure with a second review pipeline, exactly what the commission presumptively disallows; no evidence surfaced that it is a genuinely different canonical truth category.

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
**Producer discipline:** `scripts/propose_government_program_ontology.py` (discovery → candidate file only, `proposed` rows, output-path guard) and `scripts/curate_government_program_ontology.py` (atomic admission of a human-reviewed worksheet) — the recipient-graph propose/curate **script pattern**, with D5's own evidence gates per §3.1a (the recipient graph's closed evidence classes/hosts do NOT transfer — they would reject every D5 source). Engine reader: `engine/government_revenue/program_ontology.py`.
**Contract discipline (inherited, mandatory):** closed top-level key set; `additionalProperties: false` on every def; const-pinned `schema_version`; the verbatim all-false display-tier `AUTHORITY` block (`tier: display`, `context_only: true`, `can_rank/size/gate/originate_signal/add_candidates/escalate: false`); an `evidence` table whose rows carry receipt id + sha256 + source URL + retrieved_at; top-level `conflicts` and `overrides` collections with the recipient-graph override action semantics.

### 3.1 Object model (the minimum D5 vertical — deliberately reduced)

The V3 masterplan's broad vocabulary (threat, conflict, operation, munition, sensor, payload, software, component, material, fleet, readiness…) is **not** frozen into D5. D5 freezes five record kinds and three intra-ontology edge kinds. Everything else is display prose or a later wave.

| Record | ID grammar | Required fields (beyond the temporal quadruple of §5) | Notes |
|---|---|---|---|
| `program` | `acq-program:<slug>` | `name`, `aliases[]` (reviewed), `source_identities[]`, `phase` (closed: `development \| production \| sustainment \| restructured \| terminated`), `sponsor_agency` (verbatim official string) | The slug is minted once at first review and never re-derived from the name; renames/restructures append a successor record (§5). `source_identities[]` rows: `{system ∈ {p1_line_item, rdte_pe, sar_msar, official_program_page, contract_announcement}, native_identifier, evidence_ref}` — identity evidence, never budget figures. |
| `capability` | `acq-capability:<slug>` (prefixed — GMI already owns an unrelated `capability.v1` row class in the plane D5 records must stay consumable by) | `name`, `need_statement` (evidence-bound prose from an official source), `source_identities[]` | D5 carries ONE capability layer. Mission/threat/conflict cascade is explicitly out (D6+). The user-job "mission requirement" hop is answered by the capability record's evidence-bound `need_statement`. |
| `platform` | `platform:<slug>` | `name`, `program_id`, optional `variant_of` (another `platform:` id), `source_identities[]` | Blocks/variants (Block V, Block VI) are `platform` records with `variant_of`; succession appends, never edits. |
| `role_assertion` | `prog-role:<sha12>` (content-derived from the normalized tuple `program_id \| platform_id-or-"-" \| entity_id \| role \| role_scope \| valid_from \| revision` — `role_scope` and the platform slot are IN the preimage so two assertions differing only in scope or block can never collide; `revision` is an integer starting at 1 that increments ONLY on a `superseded_evidence` succession, so an evidence-superseding successor mints a distinct id while an identical resubmission stays idempotent) | `program_id` (**REQUIRED**), `platform_id` (**OPTIONAL**; when present the loader enforces: the referenced platform exists, `platform.program_id == role_assertion.program_id`, and the platform's and assertion's temporal intervals are compatible — **platform-only role assertions are invalid in v1**), `entity_id` (a defense21 legal-entity id — never a raw name, never a ticker), `role` (closed: `prime_contractor \| teaming_partner \| subcontractor \| supplier` — teaming co-production is NOT subcontracting; D0R F2 keeps JV/consortium distinct and the enum must not fuse them), `role_scope` (evidence-bound prose quoting the source's own words, e.g. "naval nuclear reactor components"), `shared_scope: bool` (true when the evidence sentence covers multiple programs), `single_document_dual_scope: bool`, `economic_weight` (**REQUIRED, `const: null`** — it names the absence of an earned economic share; do not derive, estimate, populate, rank, or otherwise make it non-null — no ratio or exposure share exists in D5), `evidence_refs[]` (`minItems: 1`; loader-enforced coverage rule: the union of the refs' `claim_scopes` must cover BOTH `program_identity` AND `role`; when ONE document covers both, `single_document_dual_scope: true` is required and the review worksheet must quote the exact source-native sentence) | This is the supplier law's carrier, mirroring `government_budget_edge.v1 reviewed_documentary` discipline with the coverage rule made loader-checkable. **Entity attachment rule:** the role attaches to the legal entity the evidence document names as performing the work; a parent-issued release naming a subsidiary's work attaches to the subsidiary. |
| `milestone` | `prog-milestone:<sha12>` | `program_id`, `kind` (closed: `budget_event \| contract_event \| delivery_event \| review_event`), `title`, `date` or `window {from,to}`, `evidence_refs[]` | **FORWARD-ONLY.** Official forward-looking statements only; the dossier's "next" rail reads these, and no milestone exists without an official document. An already-realized procurement event (e.g. the 2026-07-29 Block VI award) is GovRev/D3 truth — it renders under "what changed" and is NEVER duplicated as a milestone. A milestone whose date/window has passed is closed out (`valid_to`), not re-shown as "next". |

Both content-addressed kinds (`role_assertion`, `milestone`) additionally REQUIRE a stored **`revision`** field (integer, starts at 1) — the same value that enters their id preimages, so the loader can recompute and verify `<sha12>` and curate can mint `revision+1` on a `superseded_evidence` succession; declared here at record level exactly as `predecessor_id`/`succession_reason` are in §5.

Intra-ontology edges (closed): `implements_capability` (program→capability), `part_of_program` (platform→program, carried as `program_id`), `variant_of` (platform→platform). No other edge kind exists in v1; adding one is a contract version bump with its own review.

### 3.1a Evidence admissibility (frozen — the recipient graph's closed sets do not transfer)

The recipient graph's evidence gates (`_GRAPH_EVIDENCE_CLASSES` = official_filing/official_award/issuer_disclosure; publisher hosts closed at SEC/USAspending; `entity_resolution.py:116-127,400-433`) would reject every D5 pilot source. D5 freezes its own closed sets — same enforcement pattern, D5 vocabulary:

- **`evidence_class` enum:** `official_budget_exhibit | official_acquisition_report | official_contract_announcement | official_program_page | congressional_research | issuer_disclosure`. Nothing else admits.
- **Publisher host allowlist** (loader-enforced, extend only by contract version bump): `comptroller.defense.gov`, `comptroller.war.gov`, `www.defense.gov`, `www.war.gov`, `www.secnav.navy.mil`, `www.navy.mil`, `www.esd.whs.mil`, `www.gao.gov`, `www.congress.gov`, `crsreports.congress.gov`, `api.usaspending.gov`, `www.usaspending.gov`, `www.sec.gov`, plus the asserting issuer's own IR host for `issuer_disclosure` rows only, per the issuer-host authority block below.
- **Issuer-disclosure host authority (frozen after a bounded census, D5R.1):** **no canonical issuer→IR-host owner exists in the estate** — `reference.issuer_master` carries no website field (`scripts/build_security_master.py:188-197`), the earnings plane ingests no first-party releases/filings (`config/earnings_story_promotion.yml:11-16` `not_ingested`), and `config/biocatalyst_sources.yml` is per-dataset, not per-issuer. D5 therefore does **NOT** mint a company-source registry, and the implementation may not invent one. The issuer→host binding is split exactly as follows: **schema-enforced** — every `issuer_disclosure` evidence row REQUIRES `source_url`, `retrieved_from_url`, `pinned_issuer_host`, and `pinned_issuer_host_basis` (a short prose sentence copied from the worksheet into the artifact at curate time; shape/presence only — the schema asserts no host truth); **curator/human-reviewed** — the review worksheet pins `pinned_issuer_host` per row, with the reviewer recording the basis for "this host is the asserting issuer's official IR/corporate host" (e.g. the host named in the issuer's own SEC filings or site identification), and the curate script copies both pin and basis into the artifact row; **loader-enforced** — the loader (which reads only the artifact, never the worksheet) refuses any `issuer_disclosure` row whose `source_url` host does not equal that row's `pinned_issuer_host`, or whose `pinned_issuer_host` / `pinned_issuer_host_basis` is missing or empty. There is no global issuer→host table to consult; per-row worksheet pins are the ONLY authority. If a canonical issuer→IR-host owner later exists (e.g. the security master grows a website field), D5 rejoins it read-only via a contract version bump — never by minting its own.
- **Mirror rule:** every evidence row carries `source_url` (the host of record for the document — must be on the allowlist) AND `retrieved_from_url` (the host actually fetched, which MAY be a mirror, e.g. a globalsecurity.org-hosted Navy exhibit or an EveryCRSReport CRS copy). The receipt sha256 binds the retrieved bytes; the citation is always the host of record; a mirror-only row whose document cannot be tied to a host-of-record identity does not admit.
- **`claim_scopes` enum** on every evidence row: `program_identity | capability_need | role | milestone | ownership_context`. Per-kind required coverage (loader-enforced, this table is exhaustive): `program` → `program_identity`; `capability` → `capability_need`; `platform` → `program_identity` (a variant's identity is program-native); `role_assertion` → `program_identity` AND `role` (§3.1); `milestone` → `milestone`. `ownership_context` is never required — it may only annotate.
- **`<sha12>` definition** (applies to every content-derived id): the first 12 lowercase hex characters of SHA-256 over the UTF-8 preimage fields joined with `|`, each field NFC-normalized, lowercased, whitespace-collapsed, with an absent optional field encoded as `-`. Preimages: `prog-role:` per §3.1 (including its `revision` slot); `prog-milestone:` = `program_id | kind | title | date-or-window-from | revision` (two milestones on one program with different titles or dates never collide; an identical resubmission at the same revision is idempotent; a `superseded_evidence` succession increments `revision`, giving the successor a distinct id while §5's predecessor byte-identity holds).

### 3.2 Review states and authority tiers

Three tiers, matched to the estate (this is stricter than "deterministic + human"):

1. **`official` (automatic)** — does NOT exist inside D5 v1. Automatic source-native rows remain the budget plane's tier. Every D5 record and edge is human-admitted.
2. **`proposed`** — the only state the discovery script may emit; structurally inadmissible to the canonical artifact (curate refuses candidates as canonical; loader refuses `proposed` rows).
3. **`confirmed | reviewed | analyst_approved`** — the recipient graph's closed review-state enum, reused verbatim as the admission states. **The D5 artifact FIELD name is `verification_state`** (the estate's actual snake_case row field — `government_recipient_entity_graph.v1.schema.json:115,119`; "reviewState" is only that schema's `$defs` alias and is never a D5 key).

LLM boundary (A7-consistent): a model may draft alias candidates or summarize evidence **into the candidate file only**, tagged with its provenance; the loader/curator rejects any row carrying `FORBIDDEN_INPUT_KEYS`/`FORBIDDEN_ASSOCIATION_METHODS` provenance (`llm_assertion`, `search_snippet`, `similarity`, …, per `issuer_graph_expansion.py:87-114`). A model may never originate program IDs, budget IDs, supplier relationships, validity dates, or economic exposure, and no numeric confidence field exists anywhere in the contract.

### 3.3 What D5 does NOT own (binding no-rebuild recap)

- **No tickers / security master** — issuers only via defense21 → identity atlas → `central:<TICKER>`.
- **No recipient identity** — `entity_id` values must exist in the reviewed recipient graph; unknown entity ⇒ the role stays in the candidate file as `proposed` with a rejection-ledger row.
- **No award forks** — awards referenced by `canonical_award_identity` strings and workspace event ids only.
- **No budget truth** — no P-1/R-1 parsing, no figures. The frozen join point to `dod-program:*` keys is `budget_program_keys: {"type": "array", "const": []}` **on the `program` record** in v1 — named and documented but **structurally unfillable** (the estate's reserved-null idiom is a typed const, not an empty writable array); populating it is a contract version bump with its own referential-integrity rule, gated on the budget artifact existing AND a reviewed link. Until then the dossier budget rail is `projection_missing`.
- **No economic edges** — no `defense_supplier_graph.json`, no firm→firm edge of any kind. The `supplier` role value is an entity→**program** participation fact (no counterparty node, `economic_weight` typed null), not the census's missing customer/supplier economic object; the two §4 participants-rail limitation strings plus T12 keep the render from implying otherwise. GMI W4 may later consume D5 records as an input ramp, in GMI's vocabulary, under GMI's ownership.
- **No company facts** — Earnings/SEC owner; D4 bridge is the join.
- **No facility/BOM/capacity** — D8/D10.

---

## 4. Composed read model — `government_program_dossier.v1`

**Contract:** `contracts/government_revenue/government_program_dossier.v1.schema.json`. **Artifact:** `data/government_revenue/program_dossier.json` + site twin `site/government-revenue-data/program-dossier.json`. **Composer:** `engine/government_revenue/program_dossier.py`, invoked from `scripts/build_government_revenue.py` beside the workspace build. Read-only composition; owns zero truth; every section carries its owner's ids so the UI can deep-link.

Per-program rails, each with a typed state (vocabulary in §6):

Empty-rail honesty (D0R law: never coerce 0+unavailable into empty-valid): every review-gated rail distinguishes **`not_reviewed`** (no review pass has covered this subject — carries no timestamp claim) from **`reviewed_none`** (a review worksheet covered it and admitted nothing — carries the pass's `known_at`). Both render the plain-word "unresolved / not asserted" umbrella copy with the sub-state in the inspector tier.

| Rail | Composes from | Typed states |
|---|---|---|
| `program_identity` | D5 ontology | `reviewed` / `not_reviewed` / `reviewed_none` / `conflicted` |
| `capability` | D5 ontology | `reviewed` / `not_reviewed` / `reviewed_none` / `conflicted` |
| `awards` | award plane via role-assertion/milestone evidence references (D5 v1: a general program→award edge set is the budget owner's `reviewed_documentary` shape, not duplicated here) | `current` / `partial` / `stale` (USAspending latency is days–weeks per the D0R registry) / `source_unavailable` |
| `budget` | budget owner | `projection_missing` (today) / `source_unavailable` |
| `participants` | D5 role assertions × defense21 × atlas | per-row `reviewed` + issuer state, ATLAS vocabulary only (`verified_live` / `listing_terminated` / `not_in_si_universe`, or issuer-path `not_asserted` when no reviewed path exists — the machine token `not_asserted` is shared with the economic_relationships rail, but copy keys are RAIL-SCOPED per gate 6, so the rendered strings never collide); rail-level `not_reviewed` / `reviewed_none` / `conflicted`. **Two frozen limitation strings, both required, verbatim:** `participation_limitation` = "Companies on this rail participate in the same program; no commercial relationship between them is asserted." and `allocation_limitation` = "Reviewed participation is not a share of revenue. Nothing here allocates award value to a ticker." |
| `economic_relationships` | GMI (reserved-null today) | `not_asserted` (GMI's own absence — rendered as "no reviewed economic-relationship data", never fabricated) |
| `milestones` | D5 ontology | `reviewed` / `not_reviewed` / `reviewed_none` / `conflicted` |

The IRDM P00032 award view keeps its D1–D4 rails untouched and gains exactly one D5 field: `program_link: {state: not_reviewed | reviewed_none, reason_code: no_reviewed_program_link}` — the honest null (§8, test T1). `no_reviewed_program_link` is a **new, program-rail-scoped reason code**: reusing the atlas's `no_reviewed_exact_path` would render its bound bilingual recipient-identity copy ("No reviewed exact recipient → legal entity path…") on a program gap — the #6188 shared-rank-shared-copy trap. A test must assert the program rail and the atlas rail never share a copy string.

---

## 5. Temporal and correction law (binding; estate field names)

Every D5 record and edge carries the graph-plane temporal quadruple, exact names non-negotiable (`entity_resolution.py:65`): **`known_at`, `valid_from`, `valid_to` (nullable), `evidence_refs`** — RFC3339 with explicit UTC offset (`_strict_datetime` discipline). The artifact header carries `graph_known_at` / `graph_effective_at`; the loader must refuse certification on future leakage exactly as `entity_resolution.py` does (`future_known_claim` / `future_effective_claim` / `future_*_at_analysis_asof` at :341-353, `evidence_known_after_claim` at :369, `evidence_retrieved_after_known_at` at :433 inside `_validate_graph_evidence_receipt`).

- **Never backdate knowledge.** Evidence dated 2025 learned in August 2026 ⇒ `valid_from` may be 2025 (if the evidence establishes it), `known_at` = the 2026 collection time. A replay at any `analysis_as_of` before `known_at` returns the record as absent. "A mapping learned later cannot appear in an earlier replay."
- **`source_published_at` MUST NOT exist as a key** (D3 law — named null).
- **The knowledge clock is never presented as official** (D0R F3's `known_at.semantic ≠ "official"` law, restated for the graph plane): D5's `known_at` is a plain RFC3339 scalar with no nested `semantic` key; no D5 field, copy string, or doc may label `known_at` as a source/official clock — the official clocks are the evidence documents' own dates, carried in evidence rows.
- **Renames / restructures / variant changes append, never rewrite.** The predecessor record's id, `known_at`, `valid_from`, and `evidence_refs` stay byte-identical; a successor record is appended with its own clocks and evidence and a **`predecessor_id`** field (new mint for the graph plane, sibling of the event plane's `prior_source_identity`) plus `succession_reason` (closed: `renamed \| restructured \| variant_added \| superseded_evidence`). Names are attributes on time-boxed rows; identity is the minted id.
- **Source corrections** append (successor row + predecessor close-out row); receipts are never overwritten (D0R F2).
- **Reviewer reversal** is an appended `override` row (recipient-graph action vocabulary: `retire_edge`, `block`, …) that changes resolution only for `analysis_as_of ≥` the override's `known_at`. Reversal-by-mutation is forbidden and untestable under T2's byte-identity assertion.
- **Conflicts fail closed.** Two admissible incompatible claims ⇒ `resolution_state: conflicted`, attribution withheld, BOTH sides' evidence kept, a `conflicts[]` row appended; the underlying records stay visible. `unknown != false`; `missing != zero`.

---

## 6. Failure-state vocabulary (reuse-first; commission code → frozen form)

Machine enums are lowercase snake_case in artifacts; bilingual display copy lives in the template keyed by the enum (D3 law). The commission's uppercase codes freeze as:

| Commission code | Frozen artifact form | Provenance |
|---|---|---|
| `PROGRAM_REVIEWED` | record present with `verification_state` ∈ `confirmed\|reviewed\|analyst_approved` | recipient graph enum, reused (field name per §3.2) |
| `PROGRAM_UNRESOLVED` | `program_link.state: not_reviewed \| reviewed_none` + `reason_code: no_reviewed_program_link` | new program-rail-scoped code (see §4 — reusing the atlas code would render recipient-identity copy on a program gap) |
| `CAPABILITY_UNRESOLVED` | capability rail `not_reviewed` / `reviewed_none` | §4 empty-rail law |
| `BUDGET_PROJECTION_MISSING` | `projection_missing` | existing shipped state (`workspace.py:417`); do not mint a `budget_` prefix variant |
| `SUPPLIER_ROLE_UNRESOLVED` | participants rail / row `not_reviewed` / `reviewed_none` | §4 empty-rail law |
| `RIGHTS_BLOCKED` | `rights_blocked` — attached at the entitlement boundary (anonymous/locked view of the dossier; any future rights-limited source row), not to pilot sources (all public-domain) | D0R E product typed-state list, reused |
| `SOURCE_UNAVAILABLE` | `source_unavailable` | existing shipped state, reused |
| `HISTORICAL_ONLY` | role assertion with `valid_to` in the past + issuer state `listing_terminated` (SPR pattern); rail chip "historical only" | atlas + G1b, composed — no new enum |
| `CONFLICTING_EVIDENCE` | `conflicted` + `conflicts[]` row | `entity_resolution.py` states, reused; the string `conflicting_evidence` exists nowhere in the estate and is not minted |

**Complete new-mint inventory** (anything not listed here or defined in §3.1/§3.1a is NOT minted — this list and those sections are the same closed set stated twice): failure/state vocabulary — `no_reviewed_program_link`, the `not_reviewed`/`reviewed_none` empty-rail split, `unverified_supplier_language` (extends the closed `_action_text_annotations` family), `OntologyInputError`; field/enum mints defined in §3.1/§3.1a — the `role` enum, `succession_reason` + `predecessor_id`, `economic_weight` (const null), `shared_scope`, `single_document_dual_scope`, the `phase` enum, the milestone `kind` enum, `budget_program_keys` (const `[]`, on the `program` record), `evidence_class`, `claim_scopes`, `pinned_issuer_host` + `pinned_issuer_host_basis`, `source_url`/`retrieved_from_url`; the `program_link` field on the workspace award view (defined in §4; genuinely new — no `program_link` exists in the estate) with its `revision` sibling on content-addressed kinds (§3.1/§3.1a); and the id grammars `acq-program:` / `acq-capability:` / `platform:` / `prog-role:` / `prog-milestone:`.

---

## 7. Pilot freeze

### 7.1 Positive pilot: **Virginia-class SSN / undersea warfare** (`DEC:D5-PILOT-IS-VIRGINIA-CLASS-SSN`)

Compared against Patriot/GEM-T on the commission's six criteria (full source census with per-claim verification levels in the implementation handoff §3; summary):

- **Exact source-native identity:** VERIFIED — Navy P-1 pattern (Appropriation 1611N Shipbuilding & Conversion Navy, BA-02, Line "Virginia Class Submarine" + Advance Procurement sibling; FY2011 exhibit direct-extracted) plus DoD acquisition-report identity "SSN 774 Virginia Class Submarine" (MSAR). Current-FY SCN book confirmed to exist at its official URL; its PDF-portfolio format defeated this session's parsers — recorded as a D6/tooling dependency, not assumed.
- **Prime structure:** one prime (GD Electric Boat — CRS RL32418, direct-read: "the program's prime contractor") with one documented teaming yard (HII/NNS, ~50-50 construction split on the same hulls; the CRS evidence supports **teaming**, not subcontracting — HII's expected role is `teaming_partner`, and an HII first-party statement is NOT LOCATED, so the final label is whatever the re-fetched documents support). The comparison candidate decomposed under census into **two programs with two different primes** (PAC-3 MSE → Lockheed; GEM-T → RTX/Raytheon) plus a four-company supplier lattice and a German production JV — and GEM-T has **no located official budget-line identity at all** (FMS/DCS-heavy). "Patriot/GEM-T" therefore fails the bounded-complexity and exact-identity criteria as a single pilot.
- **Pilot entity ids (frozen against defense21-v1 committed bytes):** GD/EB prime → `legal:gd:electric-boat-corp` (exists ✓). HII → `legal:hii:huntington-ingalls-inc` — **Newport News Shipbuilding is a division, not a legal entity in the graph**; "NNS" is carried in `role_scope` prose, never as an entity id. BWXT → per the §3.1 entity-attachment rule, whichever entity the re-fetched document names as performing the work: `legal:bwxt:bwx-technologies-inc` (parent, the release's issuer) or `legal:bwxt:bwxt-nuclear-operations-group-inc` (the operating subsidiary) — the worksheet records the sentence that decides. A needed-but-absent entity is a worksheet handed to the recipient-graph lane, never a D5 edit.
- **Supplier rail:** BWXT first-party IR release ties naval nuclear reactor component contracts to "Virginia-class and Columbia-class submarines … as well as … Ford-class" — first-party, sentence-level, **shared-scope** (three programs in one sentence), which is exactly the nuance `role_assertion.shared_scope` exists to represent honestly. Decisive tie-breaker: BWXT's issuer identity already has reviewed chains in defense21-v1 (D2), so the full ontology→identity→issuer chain is executable in the current estate with zero new identity work.
- **Prose-vs-role discriminator (frozen; resolves the apparent T4↔pilot tension):** prose may establish a role ONLY when (a) the publisher is the asserting party itself (first-party `issuer_disclosure`) or a government source of record on the §3.1a allowlist, AND (b) the program is named via a reviewed alias tracing to an official `source_identities[]` document. Third-party award-description prose (USAspending descriptions, press aggregators) NEVER creates a role — it can at most earn the `unverified_supplier_language` annotation. The BWXT admission satisfies (a)+(b); "supplied by ACME" in an award description satisfies neither.
- **Change event + forward milestone (separated by law, §3.1):** the Block VI construction award, 2026-07-29 ($42.1B, SSN 814-822 + material for a tenth boat; official contracts page + GD first-party release) is the **GovRev/D3 "what changed" event — never a D5 milestone**. The forward-milestone candidate is the **AUKUS Pillar-1 window** (sale of up to three in-service boats to Australia, early 2030s); source candidate = CRS RL32418 (congress.gov CRS product, 2025-03-28 update) — document access VERIFIED in D5R, but the AUKUS sentence itself is held at SOURCE CLAIM (paraphrase, not verbatim-quoted), so admission requires re-fetch + receipt + human review like every other role/milestone. If no source survives review, `milestones.state = not_reviewed \| reviewed_none` is a **valid D5 production outcome** — never backfilled from model knowledge or a generic web claim.
- **Rights:** all government sources are public-domain US works; corporate materials quotable with attribution; no paywall, no licensed-ontology dependence.
- **Complexity bound:** rich enough to exercise every hop (capability → program → block variants → two yards → two issuers → supplier → milestone) without the F-35 universe.

PAC-3 MSE is recorded as the runner-up (it produced this census's single cleanest verified current identifier — Army MYP-1 exhibit, direct-extracted) and is a natural second vertical **after** D5 closes; not authorized here.

**Verification honesty (binding on D5):** several pilot sources were located at search-synthesis confidence only (official .mil article pages 403'd this session). The architecture freeze does not depend on their verbatim text; the **admission** of any role assertion or milestone at implementation time requires the actual document fetched, receipted (sha256 + URL + retrieved_at), and reviewed — search synthesis is not admissible evidence, per §3.2.

### 7.2 Negative control: **IRDM / P00032** (mandatory)

The award `HC101319C0006` mod `P00032` (DoD/DISA, $18,416,666.66, effective 2026-05-12, known 2026-08-12, late discovery) remains program-null. `DISA + SATCOM + contract description → program X` is a forbidden inference. A successful D5 renders "Program relationship: unresolved / not asserted" on the live IRDM rails while every D1–D4 rail is byte-unchanged. This is test T1 and the standing golden-example law (D0R F: "if a proposed field cannot be filled on this case, it is not minimum").

---

## 8. Adversarial acceptance tests (frozen; implement as stated)

Object roles: PR = program record, RA = role assertion, DRM = dossier read model, RG = reviewed recipient graph, EV = event row. All fixtures are committed test fixtures (D4 CI-wiring law: law gates ride `gate: code` with frozen fixtures, never nightly-rewritten artifacts).

1. **T1 — IRDM stays program-null.** Given the frozen P00032 EV and zero RAs citing that award: the WORKSPACE award view (the artifact that owns the single `program_link` field per §4; the DRM surfaces it unchanged) emits `program_link {state: not_reviewed, reason_code: no_reviewed_program_link}` (and, with a pilot worksheet row that covered P00032 and admitted nothing, `state: reviewed_none` — both render the "unresolved / not asserted" plain copy); no program name token renders; government fact bytes unchanged; no `source_published_at` key anywhere; the program rail's rendered copy string is asserted UNEQUAL to the atlas's `no_reviewed_exact_path` copy.
2. **T2 — rename does not rewrite.** Given PR "Alpha" and a later restructure to "Beta" (observed `K2`): predecessor PR is byte-identical post-rebuild; successor carries `predecessor_id` + own clocks; replay at `analysis_as_of < K2` renders "Alpha" and never "Beta"; historical awards render under the name valid at their `effective_at`.
3. **T3 — prime role does not smear to siblings.** Given RA(prime) on `legal:X:parent` and two RG subsidiaries with no RA: exposed set = parent only; `economic_weight` is present and typed null on every RA (named null, never a number); the frozen `allocation_limitation` string (§4) renders verbatim.
4. **T4 — prose supplier mention is not an edge.** Given an EV description containing "supplied by ACME": zero RAs created (fails BOTH halves of the §7.1 prose-vs-role discriminator — third-party prose, no reviewed alias); at most an `unverified_supplier_language` annotation; rejection ledger row recorded; forbidden-provenance keys refused at the door.
5. **T5 — request ≠ appropriation ≠ obligation (label law).** A render/template test, not an artifact-field test: no numeric node ever sums or compares a budget-request figure with an obligation; EN **and** ZH assert that no request amount is labeled obligation / appropriation / revenue / backlog. (The four-stage `source_coverage` object belongs to the budget owner's artifact — `government_budget_program_graph.v1`, unproduced until D6 — and is NOT asserted on the D5 rail; the shipped rail shape is T9's.)
6. **T6 — no identity from ticker.** Input rows carrying `discovery_query_ticker` etc. are rejected (`forbidden_provenance_key_present`); no ticker string appears in any minted id.
7. **T7 — multiple primes, different roles.** Three RAs (two `prime_contractor`, one other role) on one PR return as a set, each with own window + evidence; role multiplicity is NOT `conflicted` — while identity-axis multiplicity still fails closed (`multiple_active_ownership_paths` contrast pin). The ownership walker is not reused for roles.
8. **T8 — one issuer, multiple legal entities.** Both IRDM entities' participation paths render separately (own entity, own evidence), never deduped or summed; issuer reached only via the reviewed ownership walk.
9. **T9 — missing budget rail.** No budget artifact ⇒ `freshness.budget {status: unavailable, failure_state: projection_missing, observed_at: null, records_visible: 0, reason_code: no_request_graph_artifact}` exactly (the shipped five-key shape, `workspace.py:449-455`); deleted rail block ⇒ unavailable, never valid-empty; `loading` is never a settled state.
10. **T10 — ownership cannot backdate exposure.** Acquisition edge `valid_from` 2025-12-08, award `effective_at` 2025-06-01 ⇒ `unresolved / ownership_path_missing` at the event clock; also invisible before its `known_at`; a post-acquisition award resolves — pinning the clock, not a blanket refusal.
11. **T11 — dual-scope evidence coverage.** An RA whose refs' `claim_scopes` cover `role` but not `program_identity` (or vice versa) is refused at load with a named coverage error; a single-ref RA admitting both scopes REQUIRES `single_document_dual_scope: true` and a worksheet `scope_statement` quoting the source-native sentence — absent either, refused.
12. **T12 — co-participation is not a counterparty edge.** Given the full pilot dossier (prime + teaming partner + supplier on one program): the emitted payload contains zero firm→firm edges or adjacency structures of any kind, and BOTH §4 participants-rail limitation strings (`participation_limitation` and `allocation_limitation`) render verbatim (EN and ZH); additionally, the participants rail's rendered copy for the `not_asserted` token is asserted UNEQUAL to the economic_relationships rail's copy (rail-scoped copy keys, gate 6).
13. **T13 — evidence publisher/host refusal (asserts only authority that exists).** (a) An evidence row whose `source_url` host is off the §3.1a government/official allowlist (e.g. a press aggregator) is refused at load with the host named. (b) An `issuer_disclosure` row whose `source_url` host ≠ that row's worksheet-pinned `pinned_issuer_host` is refused — the comparison is against the PER-ROW PIN, never against any global issuer→host table (none exists in the estate). (c) An `issuer_disclosure` row missing or carrying an empty `pinned_issuer_host` or `pinned_issuer_host_basis` (both artifact fields per §3.1a — the loader never reads the worksheet) is refused. (d) A mirror-fetched row missing its host-of-record `source_url` is refused.
14. **T14 — role-id collision resistance + platform referential integrity.** (a) Two admissible RAs identical except `role_scope` (or except `platform_id` Block V vs Block VI) mint DISTINCT `prog-role:` ids from the frozen preimage `program_id | platform_id-or-"-" | entity_id | role | role_scope | valid_from | revision`; a rebuild with both present leaves each byte-identical; a `superseded_evidence` successor (revision+1) likewise mints a distinct id with the predecessor byte-identical. (b) An RA carrying a `platform_id` whose platform does not exist, or whose `platform.program_id != role_assertion.program_id`, or whose temporal interval is incompatible with the platform's, is refused at load with a named error; an RA carrying `platform_id` with no `program_id` is refused (platform-only assertions invalid in v1).

---

## 9. Experience architecture (Program / Platform Dossier)

Reference composition: `research/defense_intelligence/evidence/compositions/d5-program-dossier-virginia.html` (real pilot data, 1440/820/390 via CSS, shared `d0r-target.css`, sibling of the frozen D1/D2 targets). D0R H composition #5 law applies with two **recorded deviations** (deliberate, D6-bounded — not silent substitutions): (1) D0R's glance element "last GAO/DOT&E" requires GAO/DOT&E sources that are D6 scope; until then the glance carries phase + contract type + latest official program state (sources for each defined at the end of this paragraph), and the GAO/DOT&E element renders as a named gap. (2) D0R's why-rail "EAC / quantity": quantity is composed READ-ONLY from the GovRev/D3 changed-event evidence already on the tape (e.g. the Block VI award = nine boats, official announcement — rendered under "what changed", NEVER admitted as a D5 milestone per §3.1); EAC and all cost figures are D6 (SAR/budget) — the why rail renders that changed-event quantity + the capability need statement and names the economics gap. The glance's "contract type" element is likewise composed read-only from the award plane's existing `award_type` field (USAspending `contract_award_type` vocabulary, `collectors/usaspending_awards.py:1268`), rendered verbatim as the estate carries it (e.g. "definitive contract") — never a D5 field and never synthesized prose. The glance's "latest official program state" element is sourced from the reviewed PLATFORM/variant record (e.g. "Latest block in the reviewed record: Block VI"), not from milestones (which are forward-only, §3.1). The GAO/DOT&E element renders as a named gap keyed off `source_unavailable` (sense: no GAO/DOT&E assessment on file, source not yet collected; exact bilingual copy is template-owned). Changed = award events (budget events once the budget plane lives); evidence = exact official sources; next = next FORWARD official milestone only.

D0R H2's fourteen required states, mapped (every composition must specify all; N/A must say why):

| D0R state | D5 dossier form |
|---|---|
| complete/current | all rails reviewed/current with cut clock in chrome |
| partial coverage | `partial` on awards rail; per-rail mixed states |
| stale source / fresh transport | awards rail `stale` (source latency days–weeks) with fresh `generated_at` shown |
| stale transport | artifact `generated_at` older than the nightly cadence ⇒ rail-level stale banner (workspace freshness idiom) |
| identity unresolved | participant row whose issuer path is not reviewed — exactly §4's per-row enum (atlas issuer-path `not_asserted`, or `public_security` state `not_in_si_universe` — the row FIELD, not the schema's `publicSecurity` $defs alias); resolution-plane states (`unresolved`/`candidate_review`) never render on this rail — row shows the identity-state chip, no issuer link |
| conflicting graph | `conflicted` + conflicts row (§5) — attribution withheld, both evidences visible |
| corrected event | successor line from `predecessor_id` + "read being updated" chip (D3 idiom); predecessor stays visible, never re-titled as new |
| rights blocked | `rights_blocked` at the entitlement boundary (anonymous/locked view) |
| provider down | `source_unavailable` on the affected rail |
| valid empty | `reviewed_none` ONLY (a review pass covered it and admitted nothing — never coerced from absence) |
| model unavailable | N/A — no model output exists anywhere on this surface (LLM boundary §3.2) |
| shadow-only | N/A — D5 has no scored/shadow tier; display only |
| warning/adverse | N/A until D6 (GAO/DOT&E/IG adverse packets are D6 sources); adverse-shaped prose never synthesized |
| high uncertainty | plain-word watch stance ("windows, not certainties"); no numeric confidence exists to display |

First screen answers, in order: What is this? Why does government need it? What changed? Which listed companies have reviewed access? What remains unresolved? What happens next? — with the unresolved column carrying the typed states of §6 in plain words ("Budget request rail unavailable", "No reviewed economic-relationship data", "Supplier scope shared across three programs"). Technical IDs (`acq-program:*`, UEI, `prog-role:*`) live in the inspector tier. EN/ZH parity; no translated `title=` attributes; no third header; no frontend-computed order; **no graph visualization as the primary UX** — the graph answers investor questions; it is never rendered as nodes for their own sake.

---

## 10. What D5R deliberately leaves open (nothing a cold builder must decide)

- Whether the dossier ships as a new mode of `government_revenue.html` or a sibling page — frozen in the handoff (§0 gate 5: new `mode=programs` view inside the existing page family; no new header).
- FY2026 SCN exhibit parsing (PDF portfolio) — a D6 dependency; D5 renders the identity from already-verified historical exhibits + MSAR identity and states the current-FY gap.
- GMI W4 consumption of D5 role assertions — GMI's wave, GMI's vocabulary, not started here.

Anything not listed here is frozen above or in the handoff; if a builder finds a decision this document does not answer, that is a D5R defect to report, not a choice to make silently.
