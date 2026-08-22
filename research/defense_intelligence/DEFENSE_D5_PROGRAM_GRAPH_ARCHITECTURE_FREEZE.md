# DEFENSE D5R — Program / Mission / Capability / Product Graph Architecture Freeze

**Status:** SOL AUTHORIZED — RESEARCH / ARCHITECTURE ONLY. D5 implementation NOT authorized. D6+ NOT authorized.
**Frozen against:** `origin/main` `33d70f5ce4b36329e8acfb285557f4c9d3c72589` (2026-08-22T02:28Z).
**Program:** Defense Procurement & Industrial Base Intelligence OS V3 (`WS:DEFENSE-PROCUREMENT-V3`).
**Companion:** `DEFENSE_D5_PROGRAM_GRAPH_IMPLEMENTATION_HANDOFF.md` (acceptance gates §0 there govern the D5 build).
**Precedence (total order, on any conflict):** this freeze document > the implementation handoff > the DEC records (decision narrative) > the reference composition and the fixtures file (`evidence/fixtures/d5-representability-fixtures.json`) — the two reference artifacts rank last and equal. A conflict discovered anywhere in that chain is a defect to report and repair, never a choice to make silently.
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
| Review machinery | `scripts/propose_government_revenue_recipient_graph.py` / `curate_…` / `_REVIEWED_GRAPH_STATES` (7 gate sites in `entity_resolution.py`) | live | Discovery writes a candidate file only (`guard_output_path` refuses the canonical path); a human-reviewed worksheet is admitted atomically by the curate script. Producers may only emit `proposed` (`issuer_graph_expansion.py:66,172` — `PROPOSED_STATE`, `ProposalAuthorityError`). |

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
**Canonical artifact:** `data/government_revenue/program_ontology.json` + site twin `site/government-revenue-data/program-ontology.json` (the estate's `site/government-revenue-data/*.json` publication pattern — the dossier UI dereferences `ev:` receipts, `source_identities`, and row ids against this published twin; dossier rails carry ids only).
**Producer discipline:** `scripts/propose_government_program_ontology.py` (discovery → candidate file only, `proposed` rows, output-path guard) and `scripts/curate_government_program_ontology.py` (atomic admission of a human-reviewed worksheet) — the recipient-graph propose/curate **script pattern**, with D5's own evidence gates per §3.1a (the recipient graph's closed evidence classes/hosts do NOT transfer — they would reject every D5 source). Engine reader: `engine/government_revenue/program_ontology.py`.
**Contract discipline (inherited, mandatory):** closed top-level key set (enumerated in §3.0); `additionalProperties: false` on every def; const-pinned `schema_version`; the verbatim all-false display-tier `AUTHORITY` block (`tier: display`, `context_only: true`, `can_rank/size/gate/originate_signal/add_candidates/escalate: false` — exact key names per `dossiers.py:47-56`); an `evidence` table whose row shape is frozen in §3.1a; top-level `conflicts` and `overrides` collections with D5-scoped rows following the recipient-graph structural pattern (§5).

### 3.0 Top-level contract skeleton (frozen — D5R.2 representability seal)

The top-level key set is CLOSED and enumerated. `government_program_ontology.v1` has exactly these **seventeen** top-level keys, in this order, and **no additional top-level collection is allowed in D5 v1** — adding one returns to Sol before any change:

`contract` · `schema_version` · `graph_id` · `graph_known_at` · `graph_effective_at` · `authority` · `evidence` · `programs` · `capabilities` · `platforms` · `program_capability_links` · `role_assertions` · `milestones` · `program_event_links` · `review_coverage` · `conflicts` · `overrides`

- **`contract`**: const `"government_program_ontology.v1"`. **`schema_version`**: const `"1.0.0"` (semver string, const-pinned — the recipient graph pins `"1.1.0"` the same way, `entity_resolution.py:40`).
- **`graph_id` grammar (frozen):** `program-ontology:<status>:<YYYY-MM-DD>:<batch-slug>` with `status ∈ {candidate, reviewed}` — the recipient graph's exact grammar shape (committed value `recipient-graph:reviewed:2026-08-19:defense21-v1`; the propose script mints `candidate`, the curate script re-mints `reviewed` on admission, per the `propose_government_revenue_recipient_graph.py:1469-1480` precedent). Example: `program-ontology:reviewed:2026-08-22:defense-d5-v1`.
- **Graph clocks:** `graph_known_at` / `graph_effective_at`, strict RFC3339 with explicit UTC offset (§5) — graph-style clocks because this is reviewed PIT truth, not a transient workspace projection; the `as_of`/`generated_at` idiom belongs to read models (§4) and is not used here. Header receipt: the recipient graph's required header is exactly `contract, schema_version, graph_id, graph_known_at, graph_effective_at` (`entity_resolution.py:51-55`).

**Reference object (documentation only — the production schema file is a D5 deliverable and is NOT created in D5R):** every content-addressed id below recomputes under §3.1a's sha12 law, and the identical values appear in `evidence/fixtures/d5-representability-fixtures.json` so a cold builder can verify them. Evidence `sha256` values are placeholders (each is sha256 of the named `d5r2-reference-placeholder:*` string, not of a real document), and the `program_event_links` row is a SYNTHETIC shape example — the 2026-08-22 census found NO real Virginia Block VI `government_procurement_event.v2` row on `origin/main` `7e00f874` (§3.1b).

```json
{
 "contract": "government_program_ontology.v1",
 "schema_version": "1.0.0",
 "graph_id": "program-ontology:reviewed:2026-08-22:defense-d5-v1",
 "graph_known_at": "2026-08-22T08:00:00+00:00",
 "graph_effective_at": "2026-08-22T08:00:00+00:00",
 "authority": {
  "tier": "display",
  "context_only": true,
  "can_rank": false,
  "can_size": false,
  "can_gate": false,
  "can_originate_signal": false,
  "can_add_candidates": false,
  "can_escalate": false
 },
 "evidence": [
  {
   "evidence_id": "ev:7e57bb71753d",
   "evidence_class": "official_budget_exhibit",
   "sha256": "7e57bb71753d1da0e289734b1c1b8b5cca7260be990d416d21542d00d99ea8c1",
   "source_url": "https://www.secnav.navy.mil/fmc/fmb/Documents/11pres/SCN_BA2_BOOK.pdf",
   "retrieved_from_url": "https://www.globalsecurity.org/military/library/budget/fy2011/navy-peds/scn_ba2_book.pdf",
   "retrieved_at": "2026-08-22T08:00:00+00:00",
   "known_at": "2026-08-22T08:00:00+00:00",
   "claim_scopes": [
    "program_identity"
   ]
  },
  {
   "evidence_id": "ev:4f8d159388a7",
   "evidence_class": "congressional_research",
   "sha256": "4f8d159388a732c82699f11b2be27768d6f1e2dc1b561ecb3e688e21185c43ad",
   "source_url": "https://crsreports.congress.gov/product/pdf/RL/RL32418",
   "retrieved_from_url": "https://www.everycrsreport.com/reports/RL32418.html",
   "retrieved_at": "2026-08-22T08:00:00+00:00",
   "known_at": "2026-08-22T08:00:00+00:00",
   "claim_scopes": [
    "capability_need",
    "milestone",
    "program_capability_link",
    "program_identity",
    "role"
   ]
  },
  {
   "evidence_id": "ev:2f718fd13f51",
   "evidence_class": "official_contract_announcement",
   "sha256": "2f718fd13f51c621268a01f0cc1cff186281231acd0466f5a71af4d9385d77cd",
   "source_url": "https://www.war.gov/News/Contracts/Contract/Article/example-2026-07-29/",
   "retrieved_from_url": "https://www.war.gov/News/Contracts/Contract/Article/example-2026-07-29/",
   "retrieved_at": "2026-08-22T08:00:00+00:00",
   "known_at": "2026-08-22T08:00:00+00:00",
   "claim_scopes": [
    "program_event_link",
    "program_identity",
    "role"
   ]
  },
  {
   "evidence_id": "ev:31e47b3a83dd",
   "evidence_class": "issuer_disclosure",
   "sha256": "31e47b3a83dd03ded474b20a3d7640b997534efe6ff9622cd1630af24affc34e",
   "source_url": "https://investors.bwxt.com/news/example-2025-02-19",
   "retrieved_from_url": "https://investors.bwxt.com/news/example-2025-02-19",
   "retrieved_at": "2026-08-22T08:00:00+00:00",
   "known_at": "2026-08-22T08:00:00+00:00",
   "claim_scopes": [
    "program_identity",
    "role"
   ],
   "pinned_issuer_host": "investors.bwxt.com",
   "pinned_issuer_host_basis": "Host identified as BWX Technologies' investor-relations site in the issuer's own SEC filings."
  }
 ],
 "programs": [
  {
   "id": "acq-program:virginia-class-ssn",
   "revision": 1,
   "name": "Virginia-class SSN",
   "aliases": [
    "SSN 774 class"
   ],
   "source_identities": [
    {
     "system": "p1_line_item",
     "native_identifier": "1611N BA-02 Virginia Class Submarine",
     "evidence_ref": "ev:7e57bb71753d"
    }
   ],
   "phase": "production",
   "sponsor_agency": "Department of the Navy",
   "budget_program_keys": [],
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2010-01-26T00:00:00+00:00",
   "evidence_refs": [
    "ev:7e57bb71753d"
   ]
  }
 ],
 "capabilities": [
  {
   "id": "acq-capability:undersea-warfare",
   "revision": 1,
   "name": "Undersea warfare",
   "need_statement": "Attack-submarine force level below the Navy's stated force-structure goal.",
   "source_identities": [
    {
     "system": "congressional_research",
     "native_identifier": "CRS RL32418",
     "evidence_ref": "ev:4f8d159388a7"
    }
   ],
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2025-03-28T00:00:00+00:00",
   "evidence_refs": [
    "ev:4f8d159388a7"
   ]
  }
 ],
 "platforms": [
  {
   "id": "platform:virginia-block-v",
   "revision": 1,
   "name": "Virginia Block V",
   "program_id": "acq-program:virginia-class-ssn",
   "variant_of": null,
   "source_identities": [
    {
     "system": "congressional_research",
     "native_identifier": "CRS RL32418 (Block V)",
     "evidence_ref": "ev:4f8d159388a7"
    }
   ],
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2019-12-02T00:00:00+00:00",
   "evidence_refs": [
    "ev:4f8d159388a7"
   ]
  },
  {
   "id": "platform:virginia-block-vi",
   "revision": 1,
   "name": "Virginia Block VI",
   "program_id": "acq-program:virginia-class-ssn",
   "variant_of": "platform:virginia-block-v",
   "source_identities": [
    {
     "system": "contract_announcement",
     "native_identifier": "Block VI construction award, 2026-07-29",
     "evidence_ref": "ev:2f718fd13f51"
    }
   ],
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2026-07-29T00:00:00+00:00",
   "evidence_refs": [
    "ev:2f718fd13f51"
   ]
  }
 ],
 "program_capability_links": [
  {
   "link_id": "prog-cap:6c61262a44f6",
   "revision": 1,
   "program_id": "acq-program:virginia-class-ssn",
   "capability_id": "acq-capability:undersea-warfare",
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2010-01-26T00:00:00+00:00",
   "evidence_refs": [
    "ev:4f8d159388a7"
   ]
  }
 ],
 "role_assertions": [
  {
   "id": "prog-role:21c01a4ec620",
   "revision": 1,
   "program_id": "acq-program:virginia-class-ssn",
   "platform_id": null,
   "entity_id": "legal:gd:electric-boat-corp",
   "role": "prime_contractor",
   "role_scope": "the program's prime contractor",
   "shared_scope": false,
   "single_document_dual_scope": false,
   "economic_weight": null,
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2025-03-28T00:00:00+00:00",
   "evidence_refs": [
    "ev:4f8d159388a7",
    "ev:7e57bb71753d"
   ]
  },
  {
   "id": "prog-role:4db1f7c7bfba",
   "revision": 1,
   "program_id": "acq-program:virginia-class-ssn",
   "platform_id": null,
   "entity_id": "legal:hii:huntington-ingalls-inc",
   "role": "teaming_partner",
   "role_scope": "joint construction of Virginia-class boats (~50-50 split)",
   "shared_scope": false,
   "single_document_dual_scope": true,
   "economic_weight": null,
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2025-03-28T00:00:00+00:00",
   "evidence_refs": [
    "ev:4f8d159388a7"
   ]
  },
  {
   "id": "prog-role:1cc0b3429f99",
   "revision": 1,
   "program_id": "acq-program:virginia-class-ssn",
   "platform_id": null,
   "entity_id": "legal:bwxt:bwx-technologies-inc",
   "role": "supplier",
   "role_scope": "naval nuclear reactor components",
   "shared_scope": true,
   "single_document_dual_scope": true,
   "economic_weight": null,
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2025-02-19T00:00:00+00:00",
   "evidence_refs": [
    "ev:31e47b3a83dd"
   ]
  }
 ],
 "milestones": [
  {
   "id": "prog-milestone:cd326e9ef033",
   "revision": 1,
   "program_id": "acq-program:virginia-class-ssn",
   "kind": "delivery_event",
   "title": "AUKUS Pillar 1 initial transfer window",
   "temporal_kind": "window",
   "window": {
    "from": "2030-01-01",
    "to": "2032-12-31"
   },
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2025-03-28T00:00:00+00:00",
   "evidence_refs": [
    "ev:4f8d159388a7"
   ]
  }
 ],
 "program_event_links": [
  {
   "link_id": "prog-event:1b5c5cc8b33d",
   "revision": 1,
   "program_id": "acq-program:virginia-class-ssn",
   "event_contract": "government_procurement_event.v2",
   "event_id": "govws-0000000000000000example",
   "event_source_identity_id": "action:EXAMPLE_SYNTHETIC_0",
   "event_source_identity_content_sha256": "a15b4df2ff5653b980308567a2ec051bf57db7793106eb64629f4197c54fd3ac",
   "canonical_award_identity": "generated:EXAMPLE_SYNTHETIC_AWARD",
   "verification_state": "reviewed",
   "known_at": "2026-08-22T08:00:00+00:00",
   "valid_to": null,
   "valid_from": "2026-07-29T00:00:00+00:00",
   "evidence_refs": [
    "ev:2f718fd13f51"
   ]
  }
 ],
 "review_coverage": [
  {
   "coverage_id": "rev-cov:8a2db413615f",
   "scope": "program_identity",
   "subject_type": "program",
   "subject_id": "acq-program:virginia-class-ssn",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json",
   "worksheet_sha256": "283987ebaab45ea45aab5ad37ea07f1d9fc7b83364f7e9eebd0a04a0cf5adbd0",
   "admitted_count": 3
  },
  {
   "coverage_id": "rev-cov:dd73e4e23d1f",
   "scope": "capability",
   "subject_type": "program",
   "subject_id": "acq-program:virginia-class-ssn",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json",
   "worksheet_sha256": "283987ebaab45ea45aab5ad37ea07f1d9fc7b83364f7e9eebd0a04a0cf5adbd0",
   "admitted_count": 1
  },
  {
   "coverage_id": "rev-cov:c2e7744ed876",
   "scope": "participants",
   "subject_type": "program",
   "subject_id": "acq-program:virginia-class-ssn",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json",
   "worksheet_sha256": "283987ebaab45ea45aab5ad37ea07f1d9fc7b83364f7e9eebd0a04a0cf5adbd0",
   "admitted_count": 3
  },
  {
   "coverage_id": "rev-cov:a798a82c83b6",
   "scope": "milestones",
   "subject_type": "program",
   "subject_id": "acq-program:virginia-class-ssn",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json",
   "worksheet_sha256": "283987ebaab45ea45aab5ad37ea07f1d9fc7b83364f7e9eebd0a04a0cf5adbd0",
   "admitted_count": 1
  },
  {
   "coverage_id": "rev-cov:61894f1b4417",
   "scope": "program_event_link",
   "subject_type": "program",
   "subject_id": "acq-program:virginia-class-ssn",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json",
   "worksheet_sha256": "283987ebaab45ea45aab5ad37ea07f1d9fc7b83364f7e9eebd0a04a0cf5adbd0",
   "admitted_count": 1
  },
  {
   "coverage_id": "rev-cov:1570e40418bb",
   "scope": "program_event_link",
   "subject_type": "award_event",
   "subject_id": "govws-0000000000000000example",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-example.json",
   "worksheet_sha256": "283987ebaab45ea45aab5ad37ea07f1d9fc7b83364f7e9eebd0a04a0cf5adbd0",
   "admitted_count": 1
  },
  {
   "coverage_id": "rev-cov:1f312c8cddad",
   "scope": "program_event_link",
   "subject_type": "award_event",
   "subject_id": "govws-a6c70850a9cbdce9fa3e7f3b",
   "known_at": "2026-08-22T08:00:00+00:00",
   "worksheet_ref": "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_2026-08-22-irdm-example.json",
   "worksheet_sha256": "a4d0c6cbb8b75de2bfa92ba4ac86f16a615320a71e9e5e509cc6e062a08b764c",
   "admitted_count": 0
  }
 ],
 "conflicts": [],
 "overrides": []
}
```

### 3.1 Object model (the minimum D5 vertical — deliberately reduced)

The V3 masterplan's broad vocabulary (threat, conflict, operation, munition, sensor, payload, software, component, material, fleet, readiness…) is **not** frozen into D5. D5 freezes five record kinds and three intra-ontology edge kinds. Everything else is display prose or a later wave.

| Record | ID grammar | Required fields (beyond the temporal quadruple of §5) | Notes |
|---|---|---|---|
| `program` | `acq-program:<slug>` | `name`, `aliases[]` (reviewed), `source_identities[]`, `phase` (closed: `development \| production \| sustainment \| restructured \| terminated`), `sponsor_agency` (verbatim official string) | The slug is minted once at first review and never re-derived from the name; renames/restructures append a successor record (§5). `source_identities[]` rows: `{system ∈ {p1_line_item, rdte_pe, sar_msar, official_program_page, contract_announcement, congressional_research}, native_identifier, evidence_ref}` — identity evidence, never budget figures (`congressional_research` added D5R.2 so a capability's CRS-sourced identity is representable without abusing another system value). |
| `capability` | `acq-capability:<slug>` (prefixed — GMI already owns an unrelated `capability.v1` row class in the plane D5 records must stay consumable by) | `name`, `need_statement` (evidence-bound prose from an official source), `source_identities[]` | D5 carries ONE capability layer. Mission/threat/conflict cascade is explicitly out (D6+). The user-job "mission requirement" hop is answered by the capability record's evidence-bound `need_statement`. |
| `platform` | `platform:<slug>` | `name`, `program_id`, optional `variant_of` (another `platform:` id), `source_identities[]` | Blocks/variants (Block V, Block VI) are `platform` records with `variant_of`; succession appends, never edits. |
| `role_assertion` | `prog-role:<sha12>` (content-derived from the normalized tuple `program_id \| platform_id-or-"-" \| entity_id \| role \| role_scope \| valid_from \| revision` — `role_scope` and the platform slot are IN the preimage so two assertions differing only in scope or block can never collide; `revision` is an integer starting at 1 that increments ONLY on a succession — `superseded_evidence` or `attribute_revision`, §5 — so a successor mints a distinct id while an identical resubmission stays idempotent) | `program_id` (**REQUIRED**), `platform_id` (**OPTIONAL**; when present the loader enforces: the referenced platform exists, `platform.program_id == role_assertion.program_id`, and the platform's and assertion's temporal intervals are compatible — **platform-only role assertions are invalid in v1**), `entity_id` (a defense21 legal-entity id — never a raw name, never a ticker), `role` (closed: `prime_contractor \| teaming_partner \| subcontractor \| supplier` — teaming co-production is NOT subcontracting; D0R F2 keeps JV/consortium distinct and the enum must not fuse them), `role_scope` (evidence-bound prose quoting the source's own words, e.g. "naval nuclear reactor components"), `shared_scope: bool` (true when the evidence sentence covers multiple programs), `single_document_dual_scope: bool`, `economic_weight` (**REQUIRED, `const: null`** — it names the absence of an earned economic share; do not derive, estimate, populate, rank, or otherwise make it non-null — no ratio or exposure share exists in D5), `evidence_refs[]` (`minItems: 1`; loader-enforced coverage rule: the union of the refs' `claim_scopes` must cover BOTH `program_identity` AND `role`; the stored `single_document_dual_scope` must EQUAL the predicate computed BY CURATE AT ADMISSION over the refs' then-current `claim_scopes` — `true` iff NO pair of DISTINCT refs `(a, b)` exists where `a`'s scopes cover `program_identity` and `b`'s cover `role`, i.e. the dual coverage is achievable only through a single document (within one curate act, evidence-row updates — new rows and widenings — apply FIRST and row admissions are then predicated on the post-update scopes, so "then-current" is deterministic; a candidate whose stored value differs from the computed one is refused AT CURATE with `dual_scope_predicate_mismatch`; the loader checks shape only and NEVER recomputes this predicate — a later §3.1a widening of a document's scopes must not retroactively refuse a byte-frozen row; the flag is an admission-time record, and a materially changed evidence situation is handled like any evidence change, by a succession at the next review pass); when `true`, the review worksheet must quote the exact source-native sentence (`scope_statement`, §3.1c)) | This is the supplier law's carrier, mirroring `government_budget_edge.v1 reviewed_documentary` discipline with the coverage rule made loader-checkable. **Entity attachment rule:** the role attaches to the legal entity the evidence document names as performing the work; a parent-issued release naming a subsidiary's work attaches to the subsidiary. |
| `milestone` | `prog-milestone:<sha12>` (preimage per §3.1a — BOTH window endpoints are in it) | `program_id`, `kind` (closed: `budget_event \| contract_event \| delivery_event \| review_event`), `title`, `temporal_kind` (closed: `date \| window`), then an exact XOR: `temporal_kind: date` ⇒ `date` (RFC3339 full-date) REQUIRED and `window` FORBIDDEN; `temporal_kind: window` ⇒ `window {from, to}` (both RFC3339 full-dates, `from <= to`) REQUIRED and `date` FORBIDDEN — a row carrying both, neither, or a `temporal_kind` that does not match the populated field is refused at load; `evidence_refs[]` | **FORWARD-ONLY.** Official forward-looking statements only; the dossier's "next" rail reads these, and no milestone exists without an official document. An already-realized procurement event (e.g. the 2026-07-29 Block VI award) is GovRev/D3 truth — it renders under "what changed" and is NEVER duplicated as a milestone. A milestone whose date/window has passed is closed out (`valid_to`), not re-shown as "next". |

**Optionality regimes (frozen, D5R.2 — deterministic bytes for idempotent resubmission):** an OPTIONAL field (`platform_id`, `variant_of`, `valid_to`, the two `latest_platform_*` rail keys) is a REQUIRED key with a `null` value when unset — exactly the §3.0 reference-object form; a CONDITIONAL field (`predecessor_id`/`succession_reason`, `pinned_issuer_host`/`pinned_issuer_host_basis`, the milestone `date`/`window` XOR pair, override target fields) is ABSENT unless its condition holds. A submission mixing the regimes is a byte difference and refuses `duplicate_identity_conflict` rather than deduping — the regimes are law, not style.

**Universal `revision` and `verification_state` law (D5R.2):** EVERY canonical row kind — `program`, `capability`, `platform`, `role_assertion`, `milestone`, `program_capability_link`, `program_event_link` — carries a REQUIRED stored **`revision`** field (integer, starts at 1) AND a REQUIRED **`verification_state`** (§3.2 enum; the §3.1 table omits both columns only for brevity — the §3.0 reference JSON is the shape authority). On the two content-addressed record kinds and the two link collections, `revision` also enters the id preimage (as its decimal string), so the loader can recompute and verify every `<sha12>` and a `superseded_evidence` succession mints a distinct id (`revision+1`) while an identical resubmission stays idempotent. On the three **logical** kinds (`program`, `capability`, `platform`) the id is a minted slug, not content-derived, and `revision` versions the SAME logical identity per §5's logical-id law (rename / corrected evidence / attribute revision ⇒ same id, `revision+1`; identity break ⇒ new id at revision 1 with `predecessor_id`).

**Relationship representation law (D5R.2 — one representation per relation; nothing inferred from names):**

- **program → capability** is represented ONLY by `program_capability_links[]` rows (the `implements_capability` semantic). Row shape (all REQUIRED unless marked): `link_id` = `prog-cap:<sha12>` (preimage `program_id | capability_id | valid_from | revision`), `program_id`, `capability_id`, `revision`, `verification_state`, `known_at`, `valid_from`, `valid_to` (nullable), `evidence_refs[]` (`minItems: 1`). The loader enforces: both endpoints exist in this artifact; the link's `[valid_from, valid_to)` interval is temporally compatible with both endpoints'; and the refs' `claim_scopes` union includes **`program_capability_link`** — the RELATION's own scope. Evidence proving the program and the capability separately exist (`program_identity` + `capability_need`) does NOT establish the relation; **no capability relationship may ever be inferred from names, slugs, or prose similarity.** **Curate invariant (v1 single-capability attribution):** at most ONE current link per program (D5 v1 carries one capability layer); admitting a second requires, in the same act, superseding/retiring the first or recording a `conflicts[]` row (`reason_code: incompatible_claims`, scope `capability`, subject the program) — so the capability rail derivation is total (a CURRENT conflicts row ⇒ `conflicted`; ELSE one current link ⇒ `reviewed`; ELSE ⇒ per §3.1c); multi-capability attribution is a contract version bump. The loader mirrors the invariant fail-closed on BOTH link axes: an artifact carrying ≥2 current links on one subject (per program here; per `event_id` in §3.1b) with no current conflicts row refuses certification (`link_multiplicity_invalid`) — a hand-edited artifact cannot smuggle the state past the curate-only invariant. **Orphan rule (curate-time):** a worksheet may not admit a capability record without ≥1 citing link in the same act — refused `orphan_capability` at curate. At LOAD time a capability with zero CURRENT links (e.g. after a lawful `retire_row` on its only link) is NOT a certification error: it simply supports nothing — the capability rail derives from current links per §3.1c, and the record stays as replayable history.
- **platform → program** is the platform record's `program_id` field; **platform → platform variant** is the platform record's `variant_of` field (nullable; when present the referenced platform must exist and belong to the same `program_id`). Neither has an edge collection.
- **program → GovRev event** (cross-plane) is represented ONLY by `program_event_links[]` rows, frozen in §3.1b.

No other relationship representation exists in v1; adding one is a contract version bump with its own review.

### 3.1a Evidence admissibility (frozen — the recipient graph's closed sets do not transfer)

The recipient graph's evidence gates (`_GRAPH_EVIDENCE_CLASSES` = official_filing/official_award/issuer_disclosure; a closed publisher-host allowlist — SEC/USAspending plus one legacy per-issuer entry — an in-graph evidence gate, not a canonical issuer→IR-host owner; `entity_resolution.py:116-127,400-433`) would reject every D5 pilot source. D5 freezes its own closed sets — same enforcement pattern, D5 vocabulary:

- **Evidence row shape (frozen, D5R.2):** every row in the top-level `evidence` table carries exactly `evidence_id` (`ev:<sha12>` — here the twelve hex characters are the first 12 of the row's own document `sha256`, no preimage join), `evidence_class`, `sha256` (the retrieved bytes' receipt), `source_url`, `retrieved_from_url`, `retrieved_at` (strict RFC3339), `known_at` (strict RFC3339 — the receipt's knowledge clock; it is what makes the §5-mandated `evidence_known_after_claim` and `evidence_retrieved_after_known_at` refusals implementable exactly as `entity_resolution.py:369,:433` implements them against its own evidence rows' `known_at`), `claim_scopes[]`, plus — on `issuer_disclosure` rows ONLY — `pinned_issuer_host` and `pinned_issuer_host_basis` (the issuer-host authority block below). `evidence_refs[]` on records and links reference rows by `evidence_id`. Evidence rows are append-only and keyed by `evidence_id` — ONE row per document: a later pass citing the same document for new scopes WIDENS that row's `claim_scopes` (set-union, widening-only; scopes are never removed) — the widened row keeps every ORIGINAL field including `retrieved_at`/`known_at` (first receipt wins: a later fetch of identical bytes adds no receipt information), and a widening submission is one whose candidate evidence row matches the stored row in every field EXCEPT `claim_scopes`; a submission differing in any other field is refused (`evidence_receipt_mismatch`), and a re-fetch yielding different bytes is a different `sha256` and therefore a new row. Widening never retroactively refuses an admitted row: the only per-row check that reads `claim_scopes` at LOAD time is the §3.1a coverage rule (a union that widening can only help); the `single_document_dual_scope` predicate is curate-time only (§3.1).
- **`evidence_class` enum:** `official_budget_exhibit | official_acquisition_report | official_contract_announcement | official_program_page | congressional_research | issuer_disclosure`. Nothing else admits.
- **Publisher host allowlist** (loader-enforced, extend only by contract version bump): `comptroller.defense.gov`, `comptroller.war.gov`, `www.defense.gov`, `www.war.gov`, `www.secnav.navy.mil`, `www.navy.mil`, `www.esd.whs.mil`, `www.gao.gov`, `www.congress.gov`, `crsreports.congress.gov`, `api.usaspending.gov`, `www.usaspending.gov`, `www.sec.gov`, plus the asserting issuer's own IR host for `issuer_disclosure` rows only, per the issuer-host authority block below.
- **Issuer-disclosure host authority (frozen after a bounded census, D5R.1):** **no canonical issuer→IR-host owner exists in the estate** — `reference.issuer_master` carries no website field (`scripts/build_security_master.py:188-197`), the earnings plane ingests no first-party releases/filings (`config/earnings_story_promotion.yml:11-16` `not_ingested`), and `config/biocatalyst_sources.yml` is per-dataset, not per-issuer. D5 therefore does **NOT** mint a company-source registry, and the implementation may not invent one. The issuer→host binding is split exactly as follows: **schema-enforced** — every `issuer_disclosure` evidence row REQUIRES `source_url`, `retrieved_from_url`, `pinned_issuer_host`, and `pinned_issuer_host_basis` (a short prose sentence copied from the worksheet into the artifact at curate time; shape/presence only — the schema asserts no host truth); **curator/human-reviewed** — the review worksheet pins `pinned_issuer_host` per row, with the reviewer recording the basis for "this host is the asserting issuer's official IR/corporate host" (e.g. the host named in the issuer's own SEC filings or site identification), and the curate script copies both pin and basis into the artifact row; **loader-enforced** — the loader (which reads only the artifact, never the worksheet) refuses any `issuer_disclosure` row whose `source_url` host does not equal that row's `pinned_issuer_host`, or whose `pinned_issuer_host` / `pinned_issuer_host_basis` is missing or empty. There is no global issuer→host table to consult; per-row worksheet pins are the ONLY authority. If a canonical issuer→IR-host owner later exists (e.g. the security master grows a website field), D5 rejoins it read-only via a contract version bump — never by minting its own.
- **Mirror rule:** every evidence row carries `source_url` (the host of record for the document — must be on the allowlist) AND `retrieved_from_url` (the host actually fetched, which MAY be a mirror, e.g. a globalsecurity.org-hosted Navy exhibit or an EveryCRSReport CRS copy). The receipt sha256 binds the retrieved bytes; the citation is always the host of record; a mirror-only row whose document cannot be tied to a host-of-record identity does not admit.
- **`claim_scopes` enum** on every evidence row (D5R.2 adds the two relation scopes): `program_identity | capability_need | role | milestone | program_capability_link | program_event_link | ownership_context`. Per-kind required coverage (loader-enforced, this table is exhaustive): `program` → `program_identity`; `capability` → `capability_need`; `platform` → `program_identity` (a variant's identity is program-native); `role_assertion` → `program_identity` AND `role` (§3.1); `milestone` → `milestone`; `program_capability_link` → `program_capability_link` (§3.1 — the relation's own scope, never satisfied by the endpoint scopes); `program_event_link` → `program_event_link` (§3.1b). `ownership_context` is never required — it may only annotate.
- **`<sha12>` definition** (applies to every content-derived id): the first 12 lowercase hex characters of SHA-256 over the UTF-8 preimage fields joined with `|`, each field NFC-normalized, lowercased, whitespace-collapsed, with an absent optional field encoded as `-`, integers as decimal strings, and **every timestamp slot first canonicalized to UTC and serialized exactly `YYYY-MM-DDTHH:MM:SS+00:00`** — no fractional seconds, no `Z`, no non-zero offset — before the normalization steps (so two legal spellings of one instant can never mint two ids; this is what keeps "an identical resubmission is idempotent" true on the timestamp axis, the same guarantee the §4 array-order law gives arrays). Preimage registry (exhaustive, D5R.2):
  - `prog-role:` = `program_id | platform_id-or-"-" | entity_id | role | role_scope | valid_from | revision` (§3.1);
  - `prog-milestone:` = `program_id | kind | title | temporal_kind | date-or-window-from | window-to-or-"-" | revision` — the COMPLETE temporal identity is in the preimage: `temporal_kind: date` rows put the date in slot 5 and `-` in slot 6; `temporal_kind: window` rows put `window.from` in slot 5 and `window.to` in slot 6, so **two windows sharing a start but differing in end mint DISTINCT ids** (the D5R.1 preimage omitted `window.to` and could collide there — repaired here; nothing was ever produced under the old preimage). `valid_from` is DELIBERATELY not a milestone preimage slot: a row with the same program/kind/title/temporal identity but a different `valid_from` is a succession of the SAME milestone, never a sibling — whereas `prog-role:`/`prog-cap:` include `valid_from` because the same parties can hold the same role/relation over disjoint service windows, which are distinct assertions;
  - `prog-cap:` = `program_id | capability_id | valid_from | revision` (§3.1);
  - `prog-event:` = `program_id | event_contract | event_id | valid_from | revision` (§3.1b);
  - `rev-cov:` = `scope | subject_type | subject_id | worksheet_sha256 | known_at` (§3.1c — `known_at` is BOUND to the worksheet's `reviewed_at`, so a distinct pass is a distinct worksheet (new `reviewed_at`, and normally new bytes) and mints distinct coverage rows, while resubmitting the byte-identical worksheet reproduces byte-identical coverage rows that dedupe idempotently; coverage rows are immutable audit facts with no `revision` field and no succession);
  - `conf:` = `scope | subject_type | subject_id | sorted-candidate_row_ids-comma-joined (ascending lexicographic byte order of the id strings) | known_at` and `ovr:` = `action | target_row_id-or-"-" | subject_type-or-"-" | subject_id-or-"-" | known_at` (§5 — the candidate set is a preimage slot, so two distinct conflicts on one scope+subject in one act never collide; conflict and override rows are immutable audit facts with no `revision` field and no succession).
  Across all of them: two rows differing in any preimage slot never collide; an identical resubmission at the same revision is idempotent; a succession (`superseded_evidence` | `attribute_revision`, §5) increments `revision`, giving the successor a distinct id while §5's predecessor byte-identity holds; and every semantic change to a row that does NOT touch a preimage slot (a `shared_scope` correction, a `verification_state` escalation) is representable ONLY as an `attribute_revision` succession — never as an in-place variant, which the §5 duplicate-identity law refuses.

### 3.1b Program → GovRev event linkage — `program_event_links[]` (frozen, D5R.2)

D5 answers "What changed?" through ONE bounded cross-plane relation: a reviewed **pointer/assertion** at an existing `government_procurement_event.v2` row. It copies **no event truth** — no amount, date, agency, recipient name, or description ever lives inside D5.

**Row shape (all REQUIRED unless marked):** `link_id` = `prog-event:<sha12>` (preimage `program_id | event_contract | event_id | valid_from | revision`), `revision`, `program_id`, `event_contract` (const `"government_procurement_event.v2"` in v1), `event_id` (the event's top-level `event_id`, `award_events.py:1907`), `event_source_identity_id` and `event_source_identity_content_sha256` (verbatim copies, recorded at review time, of the target event's `award_change.source_identity.id` and `.content_sha256` — the nested block built at `award_events.py:1844-1848`), `canonical_award_identity` (REQUIRED in v1 — every v2 event is award/action truth; grammar per `point_in_time.py:148`: `generated:<id>` preferred, raw `award_key`, `piid:<id>` last resort), `verification_state`, `known_at`, `valid_from`, `valid_to` (nullable), `evidence_refs[]` (`minItems: 1`; coverage scope `program_event_link` per §3.1a).

**Verification (fail-closed, D5R.2-timed):** the event store is the WORKSPACE artifact `data/government_revenue/workspace.json` — its collection of `government_procurement_event.v2` rows (the same surface fixture D's receipt reads). AT CURATE TIME the referenced `event_id` must EXIST there, and the live event's `award_change.source_identity.id` / `.content_sha256` plus the canonical-identity comparand must EQUAL the link's recorded values — any mismatch or missing event refuses the candidate row. The workspace collection is a DOCUMENTED capped window (its `coverage` block records `event_cap`/`events_truncated`): when the event is absent there AND the cap is engaged (`events_truncated > 0`), curate falls back to the event plane's parquet stores (`data/government_revenue/award_event_snapshots.parquet`, `award_actions.parquet`) with the same identity/hash agreement — the cap is not evidence of nonexistence; a mismatch anywhere still refuses. The comparand is DERIVED from the live event's `award_change` by the `point_in_time.py:148` precedence over its own fields: `"generated:" + award_change.generated_award_id.removeprefix("generated:")` when present (the removeprefix mirrors `point_in_time.py:163-165` exactly — idempotent if the stored value is already prefixed), else `award_change.award_key`, else `"piid:" + award_change.piid` (`award_events.py:1849-1865` carries all three; no `canonical_award_identity` key exists on the event itself). AT LOAD TIME the loader re-verifies hash agreement for every linked event still PRESENT in the current workspace artifact; an event absent from the current (windowed) workspace collection is NOT a refusal — the event plane is append-only truth, the link's recorded identity copies stand as the reviewed receipt, and aging out of a capped cache is not evidence of nonexistence. **No name matching. No description matching. No ticker matching. No fuzzy program matching** — the join is exact-identity-plus-hash or nothing.

**Derivation:** the workspace award view's `program_link` field (§4) is DERIVED from this reviewed relation plus §3.1c coverage — never asserted independently. **Curate invariant (frozen):** at most ONE current admitted link per `event_id`; admitting a second requires, in the same act, either superseding the first or recording a `conflicts[]` row (`reason_code: multi_program_event_attribution`, subject the event). The `program_link` derivation is therefore total: a CURRENT conflicts row (visible and not retired, §5) for the event ⇒ `conflicted`; else exactly one current link ⇒ `reviewed`; else ⇒ `not_reviewed`/`reviewed_none` per §3.1c. A genuinely multi-program award is a RECORDED v1 limitation of the scalar `program_link` — the curator either picks the primary attribution or records the conflict; a richer multi-attribution shape is D6+ scope.

**Census honesty (binding on the pilot):** as of `origin/main` `7e00f874` (2026-08-22 census, receipts in the fixtures file), **no `government_procurement_event.v2` row for the 2026-07-29 Virginia Block VI award exists** — the tape's 13 Electric Boat awards are all pre-2026, and the corpus's newest `known_at` is 2026-08-21T23:22:35Z. Therefore, at D5 implementation start: re-locate an exact existing Virginia event on FRESH main; if one exists and survives review, it may populate this relation; if none exists, the linkage stays honestly `not_reviewed` / `reviewed_none`, the source-rail gap is recorded for D6, and **D5 does NOT implement a DoD announcements collector, does not fabricate "tape current", and does not call the July-29 announcement a GovRev event**. The July-29 official document may still serve as admissible D5 ontology evidence where §3.1a permits (e.g. `official_contract_announcement` behind a platform identity or role) — that does not turn it into an existing GovRev event.

### 3.1c Review coverage — `review_coverage[]` (frozen, D5R.2 — makes `reviewed_none` real)

Production never reads research prose to decide that somebody reviewed something. The ontology artifact itself carries the audit rows of every human-review act; **no second review/lifecycle database exists**, and a coverage row **records the review act — it manufactures no source truth**. No estate precedent exists (census: no artifact carries `worksheet_ref`/`worksheet_sha256`/`admitted_count` as a review-coverage record; the Prophet plane's `admitted_count` is an unrelated pick-intake receipt field) — this is a clean D5 mint.

**Row shape (all REQUIRED):** `coverage_id` = `rev-cov:<sha12>` (preimage `scope | subject_type | subject_id | worksheet_sha256 | known_at`), `scope` (closed v1: `program_identity | capability | participants | milestones | program_event_link`), `subject_type` (closed v1: `program | award_event`), `subject_id` (an `acq-program:*` id, or the target event's `event_id` for `award_event`), `known_at` (BOUND: equal to the worksheet's `reviewed_at` — never a wall clock), `worksheet_ref` (the review worksheet's repo path), `worksheet_sha256` (receipt of the worksheet bytes as reviewed), `admitted_count` (integer ≥ 0 — the number of `action: admit` rows for that scope+subject that curate ACCEPTED in that act: byte-identical already-present rows count (admitted-and-deduped), row-REFUSED admit rows do not; re-running the identical worksheet against the same artifact state reproduces the identical count). Scope↔subject pairing: the four ontology scopes take `subject_type: program`; `program_event_link` coverage takes BOTH forms — `subject_type: award_event` ("this event was reviewed for program attribution"; drives the workspace `program_link` derivation) AND `subject_type: program` ("a pass searched the tape for events belonging to this program"; drives the dossier awards rail's `link_state`) — a worksheet records whichever subjects it actually covered. The curate script appends a coverage row for every scope×subject a worksheet covered — **including scopes where it admitted nothing** — atomically with the admissions themselves.

**Scope → collection map (frozen; `admitted_count` counts the accepted admit rows landing in the mapped collections for that scope+subject in that pass — same definition as the row shape above, stated once per §6's closed-set discipline):** `program_identity` → `programs` + `platforms` (variant identity is program-native, §3.1a); `capability` → `program_capability_links` ONLY (capability RECORDS carry no program attribution — they are admitted alongside their first citing link in the same act, the §3.1 orphan rule refuses a link-less capability, and their review act is recorded through the link's coverage; a capability shared by N programs counts once per program-subject link); `participants` → `role_assertions`; `milestones` → `milestones`; `program_event_link` → `program_event_links`. Every rail-deriving collection is inside the map; `capabilities` participates through its links (above), and `evidence` (receipts) plus the audit collections (`review_coverage`, `conflicts`, `overrides`) are not review subjects.

**Derivation law (frozen; PIT — coverage rows with `known_at` after `analysis_as_of` are invisible like every row). `analysis_as_of` binding (frozen):** for both the workspace `program_link` derivation and the dossier composition, `analysis_as_of` = the read model's `as_of` (a bare UTC civil date, the shipped dossier idiom) coerced END-OF-DAY — the estate's exact rule (`entity_resolution.py:777`, `_timestamp(as_of, end_of_day=True)`); never the artifact's own `known_at`/`generated_at`. (Fixture D's coverage row at 08:00Z on the `as_of` day is therefore visible and derives `reviewed_none`.)

1. admitted current canonical row(s) for the scope+subject exist and no CURRENT `conflicts[]` row (visible and not retired, §5 — a lawfully cleared conflict is visible-but-retired and never blocks this rule) targets that scope+subject ⇒ **`reviewed`**;
2. a CURRENT `conflicts[]` row (visible and not retired, §5) targets the scope+subject ⇒ **`conflicted`** — **conflict is DECLARED by review** (the curate act records the row when two admissible incompatible claims are found), never computed by the composer; the loader's only automatic identity check is `duplicate_identity_conflict` (§5), and role/row multiplicity alone is never conflict (T7);
3. no admitted CURRENT rows, but a visible coverage row covers the scope+subject ⇒ **`reviewed_none`** (rendering the LATEST visible such coverage row's `known_at` when several passes have covered it);
4. no admitted CURRENT rows and no applicable coverage row ⇒ **`not_reviewed`** (no timestamp claim).

**Review worksheet contract (frozen minimally — curate's INPUT, never read by the loader):** `government_program_ontology_review_worksheet.v1`, keys: `contract` (const), `schema_version` (const `"1.0.0"`), `reviewed_at` (strict RFC3339), `reviewer` (free string), `coverage[]` rows `{scope, subject_type, subject_id}` (everything the pass covered — §3.1c coverage rows are minted 1:1 from these), and `rows[]` each `{action ∈ admit | reject, target_kind, candidate_row (the COMPLETE canonical row exactly as admitted), scope_statement (REQUIRED when the row is a role assertion with `single_document_dual_scope: true` — the quoted source-native sentence, T11), rejection_reason (REQUIRED when action is reject), identity_disposition (REQUIRED on logical-kind admit rows, closed: `new_identity | same_object_revision | identity_break`)}`. `pinned_issuer_host`/`pinned_issuer_host_basis` ride inside the candidate evidence rows per §3.1a. Curate hashes the worksheet bytes into `worksheet_sha256`, enforces the worksheet-side halves of T11 and §3.1a, refuses a worksheet whose admitted rows disagree with its own coverage declaration (`worksheet_inconsistent`), and enforces the identity dispositions: a `same_object_revision` row whose candidate id is absent from the artifact is refused (`rename_as_new_identity`), a `new_identity` row whose candidate id already exists is refused (`worksheet_inconsistent`), and an `identity_break` row must carry `predecessor_id` + `succession_reason: restructured` in its candidate.

### 3.2 Review states and authority tiers

Three tiers, matched to the estate (this is stricter than "deterministic + human"):

1. **`official` (automatic)** — does NOT exist inside D5 v1. Automatic source-native rows remain the budget plane's tier. Every D5 record and edge is human-admitted.
2. **`proposed`** — the only state the discovery script may emit; structurally inadmissible to the canonical artifact (curate refuses candidates as canonical; the "loader refuses `proposed`" property is the closed admission-state enum itself doing its job — `proposed` is not in the artifact vocabulary, so a hand-edited row carrying it fails schema validation like any unknown value).
3. **`confirmed | reviewed | analyst_approved`** — the recipient graph's closed review-state enum, reused verbatim as the admission states. **The D5 artifact FIELD name is `verification_state`** (the estate's actual snake_case row field — `government_recipient_entity_graph.v1.schema.json:115,119`; "reviewState" is only that schema's `$defs` alias and is never a D5 key).

**Refusal semantics (frozen, D5R.2 — two tiers, the estate's own split):** at ADMISSION time, the curate script refuses an offending candidate ROW — it stays proposed/rejected with a rejection-ledger row and the canonical artifact never gains it. At LOAD time, the engine reader validates the canonical artifact with the estate's accumulate-then-refuse pattern (`entity_resolution.py:335-372`): ANY named-error hit refuses certification of the WHOLE artifact by raising `OntologyInputError` naming every offending row and error — a canonical artifact with one bad row is corrupt state, not a degraded rail. Every §8 "refused at load" assertion tests BOTH tiers: curate refuses the candidate row; a hand-corrupted canonical fixture makes the loader raise.

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

**Bundle contract (frozen, D5R.2 — one shape, not builder choice).** Exactly these top-level keys: `contract` (const `"government_program_dossier.v1"`), `schema_version` (const `"1.0.0"`), `content_id`, `generated_at`, `as_of`, `ontology_graph_id` (the composing ontology artifact's `graph_id`, §3.0 — nullable ONLY in the bundle-level unavailable form below), `authority` (verbatim all-false block), `dossiers[]`, `limitations[]`. `content_id` = `"gpd1-"` + the first 24 hex characters of SHA-256 over the canonical JSON of the payload with `content_id` and `generated_at` excluded — the exact `dossier_content_id` construction (`dossiers.py:210-230`: canonicalization `ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False`, then prefix + 24-hex truncation; the shipped `government_revenue_dossiers.v1` uses prefix `grd1-`, and D5 mints `gpd1-` — the committed top-level keys of that precedent were census-verified 2026-08-22). A canonicalization failure is a compose-time ERROR (raise — the shipped helper's `None` return is not adopted; a D5 bundle never ships a null `content_id`). `dossiers[]` carries ONE entry per CURRENT program identity (§5 currency and revision resolution — the latest known revision whose validity covers `as_of`, not retired) in the certified ontology artifact — EVERY current program regardless of rail states (the rails carry the typed states) — ordered ascending by `program_id` in lexicographic byte order (determinism). Each entry carries `program_id` plus exactly the seven rails below — no additional rail in v1.

Per-program rails, each with a typed state (vocabulary in §6):

Empty-rail honesty (D0R law: never coerce 0+unavailable into empty-valid): every review-gated rail distinguishes **`not_reviewed`** (no review pass has covered this subject — carries no timestamp claim) from **`reviewed_none`** (a review worksheet covered it and admitted nothing — carries the pass's `known_at`). Both render the plain-word "unresolved / not asserted" umbrella copy with the sub-state in the inspector tier.

| Rail | Composes from | Typed states |
|---|---|---|
| `program_identity` | D5 ontology | `reviewed` / `not_reviewed` / `reviewed_none` / `conflicted` (ontology absence is BUNDLE-level: `dossiers: []` + `ontology_graph_id: null`, below) |
| `capability` | D5 ontology | `reviewed` / `not_reviewed` / `reviewed_none` / `conflicted` |
| `awards` | award plane via the reviewed `program_event_links[]` relation (§3.1b — pointer only; a general program→award edge set remains the budget owner's `reviewed_documentary` shape, not duplicated here) | **TWO independent axes (D5R.2)**: `source_state ∈ current \| partial \| stale \| source_unavailable` (the award PLANE's health — USAspending latency is days–weeks per the D0R registry) × `link_state ∈ reviewed \| not_reviewed \| reviewed_none \| conflicted` (whether a human reviewed any event against THIS program, §3.1c). "Source is healthy but nobody reviewed this event against this program" is `source_state: current` + `link_state: not_reviewed` — representing it as `source_unavailable` is a defect. |
| `budget` | budget owner | `projection_missing` (today) / `source_unavailable` |
| `participants` | D5 role assertions × defense21 × atlas | per-row `reviewed` + issuer state, ATLAS vocabulary only (`verified_live` / `listing_terminated` / `not_in_si_universe`, or issuer-path `not_asserted` when no reviewed path exists — the machine token `not_asserted` is shared with the economic_relationships rail, but copy keys are RAIL-SCOPED per gate 6, so the rendered strings never collide); rail-level `not_reviewed` / `reviewed_none` / `conflicted`. **Two frozen limitation strings, both required, verbatim:** `participation_limitation` = "Companies on this rail participate in the same program; no commercial relationship between them is asserted." and `allocation_limitation` = "Reviewed participation is not a share of revenue. Nothing here allocates award value to a ticker." |
| `economic_relationships` | GMI (reserved-null today) | `not_asserted` (GMI's own absence — rendered as "no reviewed economic-relationship data", never fabricated) |
| `milestones` | D5 ontology | `reviewed` / `not_reviewed` / `reviewed_none` / `conflicted` |

**Rail payload shapes (frozen, D5R.2 — every key enumerated; `additionalProperties: false`; nothing here is builder choice):** every rail object except `awards` carries **`state`** as its state key; `awards` carries the two axes instead. Exact shapes:

- `program_identity`: `{state, program_id, program_revision, name, phase, sponsor_agency, latest_platform_id (nullable), latest_platform_name (nullable), evidence_refs[]}` — name/phase/sponsor AND `evidence_refs[]` copied from the resolved D5 program revision (the selected platform contributes only its id/name; its own refs stay on the platform record, inspectable via the ontology twin; D5-owned truth; the ids let the UI deep-link, dereferenced against the published ontology twin, §3).
- `capability`: `{state, capability_id, capability_revision, name, need_statement, program_capability_link_id, evidence_refs[]}` — `evidence_refs[]` is the byte-order-sorted UNION of the resolved capability revision's refs and the current `program_capability_link`'s refs (need + relation, both inspectable). Revision resolution: the latest visible revision whose validity covers `as_of`; if NONE resolves while the link is current (every revision closed out — a curator-reachable edge), the payload falls back to the LATEST VISIBLE revision (identity attributes outlive validity close-out; the rail state still derives per §3.1c).
- `awards`: `{source_state, link_state, program_event_link_ids[], event_ids[]}` — pointers ONLY; zero copied event truth (amounts/dates/agencies stay in the event plane, fetched by the UI from that plane's own artifacts). `source_state` is COPIED from the award plane's own D3 workspace freshness verdict — specifically `workspace.json`'s `freshness.award_events` block (never `recompetes` or any sibling block); the composer computes no freshness itself. Mapping over the estate's REAL status vocabulary (`workspace.py:52-54` `_DEGRADED_FRESHNESS_STATES`, `freshness.py:14-22` `_STATUS_RANK` — the healthy value is `ok`, there is no `current` status in the estate): `ok`→`current`, `partial`→`partial`, `stale`→`stale`, anything else (`unavailable`/`blocked`/`failed`/`unknown`) or a missing block→`source_unavailable` (fail closed). `link_state` additionally derives `conflicted` when a CURRENT `conflicts[]` row (visible and not retired, §5) either targets the `event_id` cited by any of the rail's current links or names any of this program's link rows in its `candidate_row_ids[]` (the artifact-visible form of "retired by that conflict"). While a conflict row stands, the workspace answers `conflicted` for the event and this rail answers `conflicted` for any program whose links (current or conflict-retired) cite it; a conflict clears ONLY by the reviewed `retire_row` on the conflicts row itself (§5), after which both surfaces re-derive from links and coverage.
- `budget`: `{state}` (`projection_missing` | `source_unavailable`). Derivation (frozen): `state` is COPIED from `workspace.json`'s `freshness.budget.failure_state` verbatim when non-null (its committed domain is exactly these two values; the block's `status: "unavailable"` is NOT the source — the freshness `status` axis belongs to T9's workspace shape, not this rail); a `null` `failure_state` or a missing block maps to `source_unavailable` (fail closed — unreachable in practice before the D6 version bump, since budget production is hard-disabled, `collectors/dod_budget.py:37`). The five-key freshness shape of T9 belongs to the WORKSPACE artifact, not this rail.
- `participants`: `{state, rows[], participation_limitation, allocation_limitation}` (both strings verbatim, below); each row = `{role_assertion_id, entity_id, role, role_scope, shared_scope, historical (bool — true iff the assertion's `valid_to` is in the past at `as_of`; the rail does NOT validity-filter, §5: a historical row renders with the "historical only" chip per §6), issuer_path_state (reviewed | not_asserted), public_security (verified_live | listing_terminated | not_in_si_universe | null), central_id (nullable), evidence_refs[]}` — `public_security` here carries the atlas row's `public_security.state` VALUE as a scalar (the atlas field itself is an object `{state, first_date, last_date, asof}`, `identity_atlas.py:425-448` — never copy the object); the issuer join is the atlas reverse-membership lookup — the row's `entity_id` matched against atlas rows' `entities[].entity_id` (`identity_atlas.py:233-235`) — and `central_id` = `"central:" + ticker` (committed-artifact receipt: `recipient_entity_graph.json` `companies[].company_id`, e.g. `central:AVAV`; the `identity_atlas.py:16` docstring states the same convention); an `entity_id` reverse-matching ≥2 atlas ticker rows fails closed — the row renders `issuer_path_state: not_asserted` with `public_security`/`central_id` null (identity-axis multiplicity, T7's contrast pin).
- `economic_relationships`: `{state}` (const `not_asserted` in v1).
- `milestones`: `{state, rows[]}`; each row = `{milestone_id, kind, title, temporal_kind, date or window, evidence_refs[]}` (D5-owned truth, copied verbatim from the resolved milestone revision). **Forward filter (compose-time):** `rows[]` carries only CURRENT milestone rows whose `valid_to` is null-or-future at `as_of` AND whose `date` (or `window.to`) has not passed at `as_of` — both operands are civil dates, and "passed" is STRICT: a milestone whose `date`/`window.to` equals `as_of` is still "next" (inclusive boundary; the §3.1c end-of-day coercion applies to timestamp comparisons, not to this date-vs-date filter) — a closed-out or passed milestone leaves the "next" rail (it stays replayable in the artifact) and is never re-shown as next (§3.1).

**Array-order law (determinism — `content_id` canonicalization sorts keys, never arrays):** every id array in the bundle (`program_event_link_ids[]`, `event_ids[]`, `evidence_refs[]`) is sorted ascending lexicographic byte order; `participants.rows[]` is ordered by `role_assertion_id` and `milestones.rows[]` by milestone id (same order); in the ontology artifact, `claim_scopes[]` (including after a widening union; `minItems: 1` — an empty scope list never admits, mirroring `entity_resolution.py:410`), `evidence_refs[]`, `aliases[]`, and `conflicts[].candidate_row_ids[]` are likewise byte-order sorted, and `source_identities[]` is sorted by `(system, native_identifier)` — a re-ordered resubmission is therefore byte-identical, never a spurious `duplicate_identity_conflict`.

**Non-reviewed payload law:** on every rail whose review-gated state is not `reviewed` — for `awards` that state is `link_state` alone (`source_state` is a health axis and never takes the value `reviewed`) — every payload key other than the state key(s) and the two participants limitation strings is `null` (arrays: empty) — the typed state IS the content.

**Latest-block selection (frozen, resolves §9's "latest official program state"):** among the subject program's CURRENT platform records (§5) whose validity covers `as_of`, pick the maximum `valid_from`; ties break on the lexicographically greatest `id`; the selection is published as the `program_identity` rail's `latest_platform_id`/`latest_platform_name` (both null when no platform qualifies).

**`workspace.program_link` — exact frozen shapes (D5R.2).** The workspace award view gains exactly one D5 field, DERIVED from `program_event_links[]` + `review_coverage[]` (§3.1b/§3.1c), with exactly these three shapes and five keys — no program name is ever copied into `program_link`:

Reviewed positive:

```json
{"state": "reviewed", "reason_code": null,
 "program_id": "<acq-program:*>", "program_event_link_id": "<prog-event:*>",
 "ontology_graph_id": "<the composing artifact's graph_id>"}
```

Honest unresolved (IRDM P00032 today — §8, test T1):

```json
{"state": "not_reviewed | reviewed_none", "reason_code": "no_reviewed_program_link",
 "program_id": null, "program_event_link_id": null,
 "ontology_graph_id": "<current graph_id>"}
```

Conflict: `state: conflicted`, attribution withheld (`program_id`/`program_event_link_id` null, `reason_code: null`), the `conflicts[]` evidence remains inspectable via the ontology artifact.

Ontology unavailable (fourth shape — the ontology artifact is ABSENT, or the loader refused certification per §3.2):

```json
{"state": "source_unavailable", "reason_code": "ontology_unavailable",
 "program_id": null, "program_event_link_id": null, "ontology_graph_id": null}
```

`ontology_graph_id` is nullable ONLY in this shape. The refusal semantics of §3.2 are unchanged — the loader still raises `OntologyInputError` — but its CONSUMERS (workspace build, dossier composer) catch that refusal (or the artifact's absence): the workspace emits the fourth `program_link` shape above, and the dossier composer still emits the bundle — with `ontology_graph_id: null` and `dossiers: []` (the ONLY case `ontology_graph_id` is null; `dossiers` may also be `[]` under a certified ontology with zero current programs — the page state keys on the PAIR, never on either alone); the page-level unavailable state derives from exactly that pair (template-owned copy), and per-program rails never carry ontology unavailability because no entry exists to carry it. This exactly mirrors the estate's own ruling that an absent or invalid graph produces unresolved annotations rather than stopping the award/event rail (`entity_resolution.py:44-47`). Every absence is a typed state, never a crash and never a blank.

`no_reviewed_program_link` is a **new, program-rail-scoped reason code**: reusing the atlas's `no_reviewed_exact_path` would render its bound bilingual recipient-identity copy ("No reviewed exact recipient → legal entity path…") on a program gap — the #6188 shared-rank-shared-copy trap. A test must assert the program rail and the atlas rail never share a copy string.

---

## 5. Temporal and correction law (binding; estate field names)

Every D5 record and edge carries the graph-plane temporal quadruple, exact names non-negotiable (`entity_resolution.py:65`): **`known_at`, `valid_from`, `valid_to` (nullable), `evidence_refs`** — RFC3339, and in D5 artifacts pinned by schema `pattern` to exactly `YYYY-MM-DDTHH:MM:SS+00:00` (no fractional seconds, no `Z`, no non-zero offset — STRICTER than the estate's `_strict_datetime` regex, `entity_resolution.py:209-210`, which admits `Z` and fractional seconds; the pin is what makes the §3.1a preimage timestamp canonicalization a no-op on conforming rows, and a non-conforming spelling is refused at the schema door). The artifact header carries `graph_known_at` / `graph_effective_at`; the loader must refuse certification on future leakage per each collection's ACTUAL clock inventory — `future_known_claim` applies to every row kind (all carry `known_at`); `future_effective_claim` only to kinds carrying `valid_from`; these are CERTIFICATION checks against the artifact's own `graph_known_at`/`graph_effective_at` (a row may not postdate its own graph header — refuse), and are DISTINCT from a consumer's `analysis_as_of` filter, which makes later-known rows INVISIBLE (§3.1c, T2, T17) and never refuses; the estate's missing-evidence-`valid_from` error (`invalid_evidence_clock`) has NO D5 analogue because D5 evidence rows deliberately carry no validity clocks (§3.1a) — exactly as `entity_resolution.py` does (`future_known_claim` / `future_effective_claim` / `future_*_at_analysis_asof` at :341-353, `evidence_known_after_claim` at :369, `evidence_retrieved_after_known_at` at :433 inside `_validate_graph_evidence_receipt`).

- **Never backdate knowledge.** Evidence dated 2025 learned in August 2026 ⇒ `valid_from` may be 2025 (if the evidence establishes it), `known_at` = the 2026 collection time. A replay at any `analysis_as_of` before `known_at` returns the record as absent. "A mapping learned later cannot appear in an earlier replay."
- **`source_published_at` MUST NOT exist as a key** (D3 law — named null).
- **The knowledge clock is never presented as official** (D0R F3's `known_at.semantic ≠ "official"` law, restated for the graph plane): D5's `known_at` is a plain RFC3339 scalar with no nested `semantic` key; no D5 field, copy string, or doc may label `known_at` as a source/official clock — the official clocks are the evidence documents' own dates, carried in evidence rows.
- **Logical-id vs immutable-revision law (D5R.2 — supersedes the D5R succession wording; nothing was ever produced under it).** `program`, `capability`, and `platform` are **logical identities**: rows are keyed `(id, revision)`, `revision` starts at 1, and every append leaves every prior row byte-identical.
  - **Same real-world object** (a rename, corrected evidence, or an attribute/metadata revision): append a row with the **SAME logical id**, `revision + 1`, its own `known_at`, and `valid_from` reflecting when the new fact became true. The successor row carries `succession_reason` ∈ `renamed | attribute_revision | superseded_evidence` (REQUIRED on every logical-kind row with `revision ≥ 2`; FORBIDDEN on an ordinary revision-1 row). **A pure rename MUST NOT mint a second acquisition-program identity.**
  - **Resolution:** at `analysis_as_of`, revisions with `known_at` after the cut are invisible; at an effective/event time, choose the latest known revision whose `[valid_from, valid_to)` validity covers that time.
  - **True identity break** (a restructure the reviewed evidence says is a DIFFERENT acquisition identity): mint a **new logical id** at `revision: 1` carrying **`predecessor_id`** (the old logical id — the ONLY case `predecessor_id` is legal on a logical kind) and `succession_reason: restructured`; in the same admission, close out the predecessor with a same-old-id `revision + 1` row whose `valid_to` is set and whose `succession_reason` is likewise `restructured`. The old identity remains historical and replayable.
  - **Platform variants are not renames:** a new block/variant is a NEW logical `platform` record (revision 1) with `variant_of` — never a succession; the D5R enum value `variant_added` is REMOVED.
  - **Content-addressed kinds** (`role_assertion`, `milestone`, and the two link collections) succeed by `superseded_evidence` (new or changed evidence) or `attribute_revision` (a non-preimage attribute correction, including a `verification_state` escalation): `revision + 1` in the preimage mints a distinct id, the successor carries `predecessor_id` (the superseded row's content-addressed id) + the matching `succession_reason`, and the predecessor stays byte-identical. **Every content-addressed and link row shape admits the conditional pair `predecessor_id` + `succession_reason`** (both FORBIDDEN except on a successor row) — the enumerated §3.1/§3.1b row shapes are the revision-1 form plus this conditional pair; a content-addressed row with `revision ≥ 2` missing the pair, or `revision: 1` carrying it, is refused `succession_shape_invalid` (the same named error as the logical-kind cases, T2c).
  - Closed enum, all uses: `succession_reason ∈ renamed | attribute_revision | superseded_evidence | restructured`, where `restructured` is valid ONLY on the identity-break pair above; on content-addressed kinds only `attribute_revision`/`superseded_evidence` apply. Names are attributes on time-boxed rows; identity is the minted id.
- **Referential closure (loader law, D5R.2).** The loader refuses, with the named error `dangling_reference`: any `platform`, `role_assertion`, `milestone`, `program_capability_link`, or `program_event_link` whose `program_id` (or `capability_id`) names no row in this artifact; any `evidence_refs[]` entry naming no `evidence` row; any `conflicts[].candidate_row_ids[]` entry or `overrides[].target_row_id` naming no existing row. Nothing composes against a reference that does not resolve.
- **Uniqueness and duplicates (loader law, D5R.2).** Within the artifact, content-addressed kinds are unique on `id`, logical kinds on `(id, revision)`, the audit collections (`review_coverage`, `conflicts`, `overrides`) on their own ids, and `evidence` on `evidence_id`. A byte-identical duplicate row dedupes idempotently; two rows sharing a key with DIFFERING bytes refuse certification with `duplicate_identity_conflict` — with exactly one exception: an `evidence` row differing ONLY in `claim_scopes` resolves by the §3.1a widening union. Every semantic change to an existing row therefore has exactly one legal representation — the appropriate succession — and never an in-place variant of the same id.
- **Temporal compatibility (frozen definition).** Wherever this document requires two rows' intervals to be "temporally compatible", the predicate is OVERLAP: `a.valid_from < (b.valid_to or +∞) AND b.valid_from < (a.valid_to or +∞)`.
- **Currency (frozen definition, D5R.2).** A row is CURRENT at `analysis_as_of` iff it is visible (`known_at ≤ analysis_as_of`), NO visible row names it in `predecessor_id`, and no visible `retire_row` override targets it. VALIDITY is a separate, per-use rule: for logical-kind revision resolution it applies per the logical-id law; for RAIL DISPLAY it is rail-specific and frozen in §4 (the milestones rail forward-filters on date/window and `valid_to`; the participants rail does NOT validity-filter — a past-validity row renders with the "historical only" chip, §6 `HISTORICAL_ONLY`, never silently dropped). Every derivation rule and every rendered rail operates on CURRENT rows only — T14(a)'s byte-identity assertion is about STORAGE: superseded rows persist byte-identical and replayable at historical `analysis_as_of`, but they are not current and never double-render. A change to a row's preimage-identity fields (e.g. re-attributing an event link to a different `program_id`) is NOT a `revision+1` succession — it is an override `retire_row` on the old row plus a fresh admission, with a `conflicts[]` row when the claims are contested.
- **Source corrections** append (successor row + predecessor close-out row); receipts are never overwritten (D0R F2).
- **Reviewer reversal** is an appended `override` row that changes resolution only for `analysis_as_of ≥` the override's `known_at`. Reversal-by-mutation is forbidden and untestable under T2's byte-identity assertion. **D5 override row shape (frozen, D5R.2 — the recipient graph's rows are identity-domain-specific and do not transfer; D5 follows the same structural pattern with its own vocabulary):** `override_id` = `ovr:<sha12>` (preimage §3.1a), `action` (closed v1: `retire_row` — reviewer reversal, requires `target_row_id`: for a content-addressed CANONICAL row (`role_assertion`/`milestone`/either link kind) this is its content-addressed id — `evidence` and `review_coverage`/`overrides` rows are NEVER retirable (append-only receipts and audit facts); a `conflicts` row IS retirable — retiring it is the reviewed act of RESOLVING the conflict (the override's `evidence_refs` carry the resolution basis), and it is the only way a conflict clears in v1; the clearing act must RESTORE the invariant the conflict suspended — for the event axis and the capability axis, at most ONE current link may remain on the subject after the act (the same act retires or supersedes the losers), else curate refuses the clearing with `conflict_resolution_incomplete` — so the post-clearing state is always inside the frozen enumerations (one current link ⇒ `reviewed`; §3.1b and §3.1c agree); for a LOGICAL kind it is the logical id and the override retires the IDENTITY — every revision of it is non-current from the override's `known_at`, and curate REFUSES such an override (`retirement_cascade_incomplete`) unless the same act also retires or supersedes every current row REFERENCING that identity — as `program_id`, `capability_id`, `platform_id`, or `variant_of` (no orphaned dependents — the retirement cascades or is refused); `block` — refuse future admission at CURATE of any candidate row matching the subject: `subject_type: program` blocks the logical id itself and every canonical row carrying it as `program_id`; `subject_type: award_event` blocks any `program_event_link` citing that `event_id`; requires `subject_type` + `subject_id`), `target_row_id` (conditional), `subject_type`/`subject_id` (conditional), `verification_state`, `known_at`, `valid_from` (= `known_at` at mint), `valid_to` (always null at mint), `evidence_refs[]` — on override AND conflict rows the validity pair exists ONLY for the uniform temporal-quadruple shape: NEITHER field participates in currency, clearing, or any derivation (clearing is retire-only, above).
- **Conflicts fail closed.** Two admissible incompatible claims ⇒ `resolution_state: conflicted`, attribution withheld, BOTH sides' evidence kept, a `conflicts[]` row appended; the underlying records stay visible. `unknown != false`; `missing != zero`. **D5 conflict row shape (frozen, D5R.2):** `conflict_id` = `conf:<sha12>` (preimage §3.1a), `scope` (the same closed five as §3.1c coverage scopes), `subject_type`/`subject_id` (§3.1c vocabulary), `candidate_row_ids[]` (`minItems: 2` — the incompatible admitted rows), `reason_code` (closed v1: `incompatible_claims | multi_program_event_attribution`), `verification_state`, `known_at`, `valid_from`, `valid_to` (nullable), `evidence_refs[]`.

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
| `HISTORICAL_ONLY` | role assertion with `valid_to` in the past ⇒ rail chip "historical only" (the §4 `historical` flag — VALIDITY ALONE decides this chip); the issuer state (`listing_terminated`, the SPR pattern) composes independently on the issuer chip and is NOT a precondition | atlas + G1b, composed — no new enum |
| `CONFLICTING_EVIDENCE` | `conflicted` + `conflicts[]` row | `entity_resolution.py` states, reused; the string `conflicting_evidence` exists nowhere in the estate and is not minted |

**Complete new-mint inventory** (anything not listed here or defined in §3.0–§3.1c is NOT minted — this list and those sections are the same closed set stated twice): failure/state vocabulary — `no_reviewed_program_link`, the `not_reviewed`/`reviewed_none` empty-rail split, `unverified_supplier_language` (extends the closed `_action_text_annotations` family), `OntologyInputError`, and the awards-rail axis pair `source_state`/`link_state` (§4); field/enum mints defined in §3.1/§3.1a/§5 — the `role` enum, `succession_reason` (closed `renamed | attribute_revision | superseded_evidence | restructured`, D5R.2 — `variant_added` removed) + `predecessor_id` (§5; the conditional pair is admitted on every content-addressed and link row shape), `economic_weight` (const null), `shared_scope`, `single_document_dual_scope`, the `phase` enum, the milestone `kind` enum + `temporal_kind` + the date/window XOR, `budget_program_keys` (const `[]`, on the `program` record), `evidence_class`, `claim_scopes` (including the two D5R.2 relation scopes `program_capability_link`/`program_event_link`), `pinned_issuer_host` + `pinned_issuer_host_basis`, `source_url`/`retrieved_from_url`, the universal `revision` field, and the evidence-row `evidence_id` shape; collection/row mints defined in §3.0–§3.1c — the seventeen-key top-level skeleton with `graph_id` grammar `program-ontology:<status>:<YYYY-MM-DD>:<batch-slug>`, `program_capability_links[]`, `program_event_links[]` (with `event_contract`, `event_id`, `event_source_identity_id`, `event_source_identity_content_sha256`; `canonical_award_identity` REUSES the event plane's existing grammar, not a mint), `review_coverage[]` (`coverage_id`, `scope`, `subject_type`, `subject_id`, `worksheet_ref`, `worksheet_sha256`, `admitted_count` — D5-plane mints; the Prophet receipt field of the same `admitted_count` name is unrelated), and the D5-scoped `conflicts[]`/`overrides[]` row shapes (§5); the `program_link` field on the workspace award view with its five-key frozen shapes (§4; genuinely new — no `program_link` exists in the estate); dossier-bundle keys `ontology_graph_id` + `dossiers[]` (§4; the rest reuse the shipped dossier idiom); the id grammars `acq-program:` / `acq-capability:` / `platform:` / `prog-role:` / `prog-milestone:` / `prog-cap:` / `prog-event:` / `rev-cov:` / `conf:` / `ovr:` / `ev:`; and the D5R.2 representability additions — `known_at` on evidence rows with the widening-only claim-scope merge and `evidence_receipt_mismatch`, `duplicate_identity_conflict`, the conflict `reason_code` enum (`incompatible_claims | multi_program_event_attribution`), the frozen dossier rail-shape keys (§4: `state`, `program_revision`, `capability_revision`, `program_capability_link_id`, `program_event_link_ids`, `event_ids`, `issuer_path_state`), the `gpd1-` content-id prefix, `government_program_ontology_review_worksheet.v1` with its `identity_disposition` enum (§3.1c), the refusal codes `orphan_capability` and `rename_as_new_identity`, the `ontology_unavailable` reason code with the fourth `program_link` shape and the bundle-level unavailable form (`dossiers: []` + `ontology_graph_id: null`, §4), the `dangling_reference` referential-closure error (§5), the refusal names `claim_scope_coverage_missing` / `publisher_host_refused` / `issuer_host_pin_refused` / `platform_reference_invalid` / `milestone_temporal_shape_invalid` / `temporal_incompatible` / `succession_shape_invalid` / `event_not_found` / `event_identity_mismatch` / `dual_scope_predicate_mismatch` / `worksheet_inconsistent` / `retirement_cascade_incomplete` / `conflict_resolution_incomplete` / `link_multiplicity_invalid` (§3.1/§3.1c/§5/§8 — this closes the named-error vocabulary), the participants-row `historical` flag (§4), and the `latest_platform_id`/`latest_platform_name` rail keys (§4).

---

## 7. Pilot freeze

### 7.1 Positive pilot: **Virginia-class SSN / undersea warfare** (`DEC:D5-PILOT-IS-VIRGINIA-CLASS-SSN`)

Compared against Patriot/GEM-T on the commission's six criteria (full source census with per-claim verification levels in the implementation handoff §3; summary):

- **Exact source-native identity:** VERIFIED — Navy P-1 pattern (Appropriation 1611N Shipbuilding & Conversion Navy, BA-02, Line "Virginia Class Submarine" + Advance Procurement sibling; FY2011 exhibit direct-extracted) plus DoD acquisition-report identity "SSN 774 Virginia Class Submarine" (MSAR). Current-FY SCN book confirmed to exist at its official URL; its PDF-portfolio format defeated this session's parsers — recorded as a D6/tooling dependency, not assumed.
- **Prime structure:** one prime (GD Electric Boat — CRS RL32418, direct-read: "the program's prime contractor") with one documented teaming yard (HII/NNS, ~50-50 construction split on the same hulls; the CRS evidence supports **teaming**, not subcontracting — HII's expected role is `teaming_partner`, and an HII first-party statement is NOT LOCATED, so the final label is whatever the re-fetched documents support). The comparison candidate decomposed under census into **two programs with two different primes** (PAC-3 MSE → Lockheed; GEM-T → RTX/Raytheon) plus a four-company supplier lattice and a German production JV — and GEM-T has **no located official budget-line identity at all** (FMS/DCS-heavy). "Patriot/GEM-T" therefore fails the bounded-complexity and exact-identity criteria as a single pilot.
- **Pilot entity ids (frozen against defense21-v1 committed bytes):** GD/EB prime → `legal:gd:electric-boat-corp` (exists ✓). HII → `legal:hii:huntington-ingalls-inc` — **Newport News Shipbuilding is a division, not a legal entity in the graph**; "NNS" is carried in `role_scope` prose, never as an entity id. BWXT → per the §3.1 entity-attachment rule, whichever entity the re-fetched document names as performing the work: `legal:bwxt:bwx-technologies-inc` (parent, the release's issuer) or `legal:bwxt:bwxt-nuclear-operations-group-inc` (the operating subsidiary) — the worksheet records the sentence that decides. A needed-but-absent entity is a worksheet handed to the recipient-graph lane, never a D5 edit.
- **Supplier rail:** BWXT first-party IR release ties naval nuclear reactor component contracts to "Virginia-class and Columbia-class submarines … as well as … Ford-class" — first-party, sentence-level, **shared-scope** (three programs in one sentence), which is exactly the nuance `role_assertion.shared_scope` exists to represent honestly. Decisive tie-breaker: BWXT's issuer identity already has reviewed chains in defense21-v1 (D2), so the full ontology→identity→issuer chain is executable in the current estate with zero new identity work.
- **Prose-vs-role discriminator (frozen; resolves the apparent T4↔pilot tension):** prose may establish a role ONLY when (a) the publisher is the asserting party itself (first-party `issuer_disclosure`) or a government source of record on the §3.1a allowlist, AND (b) the program is named via a reviewed alias tracing to an official `source_identities[]` document. Third-party award-description prose (USAspending descriptions, press aggregators) NEVER creates a role — it can at most earn the `unverified_supplier_language` annotation. The BWXT admission satisfies (a)+(b); "supplied by ACME" in an award description satisfies neither.
- **Change event + forward milestone (separated by law, §3.1):** the Block VI construction award, 2026-07-29 ($42.1B, SSN 814-822 + material for a tenth boat; official contracts page + GD first-party release) belongs to the **GovRev/D3 changed-event plane — never a D5 milestone**. Census honesty (D5R.2, §3.1b): **no `government_procurement_event.v2` row for it exists on `origin/main` as of `7e00f874`** — until one exists and survives review, the program-event linkage stays `not_reviewed`/`reviewed_none`, the dossier renders `source_state: current` + `link_state: not_reviewed`, and the official announcement document serves only as admissible ontology evidence, never as tape truth. The forward-milestone candidate is the **AUKUS Pillar-1 window** (sale of up to three in-service boats to Australia, early 2030s); source candidate = CRS RL32418 (congress.gov CRS product, 2025-03-28 update) — document access VERIFIED in D5R, but the AUKUS sentence itself is held at SOURCE CLAIM (paraphrase, not verbatim-quoted), so admission requires re-fetch + receipt + human review like every other role/milestone. If no source survives review, `milestones.state = not_reviewed \| reviewed_none` is a **valid D5 production outcome** — never backfilled from model knowledge or a generic web claim.
- **Rights:** all government sources are public-domain US works; corporate materials quotable with attribution; no paywall, no licensed-ontology dependence.
- **Complexity bound:** rich enough to exercise every hop (capability → program → block variants → two yards → two issuers → supplier → milestone) without the F-35 universe.

PAC-3 MSE is recorded as the runner-up (it produced this census's single cleanest verified current identifier — Army MYP-1 exhibit, direct-extracted) and is a natural second vertical **after** D5 closes; not authorized here.

**Verification honesty (binding on D5):** several pilot sources were located at search-synthesis confidence only (official .mil article pages 403'd this session). The architecture freeze does not depend on their verbatim text; the **admission** of any role assertion or milestone at implementation time requires the actual document fetched, receipted (sha256 + URL + retrieved_at), and reviewed — search synthesis is not admissible evidence, per §3.2.

### 7.2 Negative control: **IRDM / P00032** (mandatory)

The award `HC101319C0006` mod `P00032` (DoD/DISA, $18,416,666.66, effective 2026-05-12, known 2026-08-12, late discovery) remains program-null. `DISA + SATCOM + contract description → program X` is a forbidden inference. A successful D5 renders "Program relationship: unresolved / not asserted" on the live IRDM rails while every D1–D4 rail is byte-unchanged. This is test T1 and the standing golden-example law (D0R F: "if a proposed field cannot be filled on this case, it is not minimum").

---

## 8. Adversarial acceptance tests (frozen; implement as stated)

Object roles: PR = program record, RA = role assertion, DRM = dossier read model, RG = reviewed recipient graph, EV = event row. All fixtures are committed test fixtures (D4 CI-wiring law: law gates ride `gate: code` with frozen fixtures, never nightly-rewritten artifacts).

1. **T1 — IRDM stays program-null.** Given the frozen P00032 EV, zero `program_event_links` citing its `event_id`, and no §3.1c coverage row for it: the WORKSPACE award view (the artifact that owns the single `program_link` field per §4; the DRM surfaces it unchanged) emits the exact §4 honest-unresolved shape `{state: not_reviewed, reason_code: no_reviewed_program_link, program_id: null, program_event_link_id: null, ontology_graph_id: <current graph_id>}`; adding ONLY a coverage row (`scope: program_event_link`, `subject_type: award_event`, `subject_id` = the P00032 `event_id`, `admitted_count: 0`) flips `state` to `reviewed_none` with every other key unchanged — both render the "unresolved / not asserted" plain copy; no program name token renders anywhere in `program_link`; government fact bytes unchanged; no `source_published_at` key anywhere; the program rail's rendered copy string is asserted UNEQUAL to the atlas's `no_reviewed_exact_path` copy.
2. **T2 — revision does not rewrite; identity survives a rename and breaks only on a reviewed restructure.** (a) Rename: given `acq-program:x` revision 1 named "Alpha" (`known_at K1`) and an admitted revision 2 named "Beta" (`succession_reason: renamed`, `known_at K2 > K1`, `valid_from V2`): the revision-1 row is byte-identical post-rebuild; NO new logical id exists (the programs collection carries exactly one `acq-program:x` identity); replay at `analysis_as_of < K2` renders "Alpha" and never "Beta"; at `analysis_as_of ≥ K2`, an award with `effective_at < V2` renders "Alpha" (latest known revision whose validity covers that time) and one with `effective_at ≥ V2` renders "Beta". (b) Identity break: given a reviewed restructure admitting `acq-program:y` (revision 1, `predecessor_id: acq-program:x`, `succession_reason: restructured`) plus the predecessor close-out (`acq-program:x` revision +1 with `valid_to` set, `succession_reason: restructured`): replay before the break's `known_at` shows only `acq-program:x`; after it, `acq-program:x` remains historical and replayable with its revision-1 row byte-identical. (c) Refusals: a revision-1 row carrying `succession_reason` (outside the identity-break successor case), a `revision ≥ 2` row missing it, and `predecessor_id` with any `succession_reason` other than `restructured` on a logical kind — each refused `succession_shape_invalid`; a worksheet row marked `identity_disposition: same_object_revision` whose candidate carries a logical id absent from the artifact (a rename smuggled in as a new identity) — refused `rename_as_new_identity` at curate.
3. **T3 — prime role does not smear to siblings.** Given RA(prime) on `legal:X:parent` and two RG subsidiaries with no RA: exposed set = parent only; `economic_weight` is present and typed null on every RA (named null, never a number); the frozen `allocation_limitation` string (§4) renders verbatim.
4. **T4 — prose supplier mention is not an edge.** Given an EV description containing "supplied by ACME": zero RAs created (fails BOTH halves of the §7.1 prose-vs-role discriminator — third-party prose, no reviewed alias); at most an `unverified_supplier_language` annotation; rejection ledger row recorded; forbidden-provenance keys refused at the door.
5. **T5 — request ≠ appropriation ≠ obligation (label law).** A render/template test, not an artifact-field test: no numeric node ever sums or compares a budget-request figure with an obligation; EN **and** ZH assert that no request amount is labeled obligation / appropriation / revenue / backlog. (The four-stage `source_coverage` object belongs to the budget owner's artifact — `government_budget_program_graph.v1`, unproduced until D6 — and is NOT asserted on the D5 rail; the shipped rail shape is T9's.)
6. **T6 — no identity from ticker.** Input rows carrying `discovery_query_ticker` etc. are rejected (`forbidden_provenance_key_present`); no ticker string appears in any minted id.
7. **T7 — multiple primes, different roles.** Three RAs (two `prime_contractor`, one other role) on one PR return as a set, each with own window + evidence; role multiplicity is NOT `conflicted` — while identity-axis multiplicity still fails closed (`multiple_active_ownership_paths` contrast pin). The ownership walker is not reused for roles.
8. **T8 — one issuer, multiple legal entities.** Both IRDM entities' participation paths render separately (own entity, own evidence), never deduped or summed; issuer reached only via the reviewed ownership walk.
9. **T9 — missing budget rail.** No budget artifact ⇒ `freshness.budget {status: unavailable, failure_state: projection_missing, observed_at: null, records_visible: 0, reason_code: no_request_graph_artifact}` exactly (the shipped five-key shape, `workspace.py:451-457`); deleted rail block ⇒ unavailable, never valid-empty; `loading` is never a settled state.
10. **T10 — ownership cannot backdate exposure.** Acquisition edge `valid_from` 2025-12-08, award `effective_at` 2025-06-01 ⇒ `unresolved / ownership_path_missing` at the event clock; also invisible before its `known_at`; a post-acquisition award resolves — pinning the clock, not a blanket refusal.
11. **T11 — dual-scope evidence coverage.** An RA whose refs' `claim_scopes` cover `role` but not `program_identity` (or vice versa) is refused at load with `claim_scope_coverage_missing`; a single-ref RA admitting both scopes REQUIRES `single_document_dual_scope: true` and a worksheet `scope_statement` quoting the source-native sentence — absent either, refused; a two-ref RA where distinct refs independently supply the two scopes COMPUTES `false` (a stored `true` there is refused AT CURATE as a predicate mismatch — the §3.1 admission-time predicate; the loader never recomputes it, and a later evidence-scope widening does not retroactively refuse the row).
12. **T12 — co-participation is not a counterparty edge.** Given the full pilot dossier (prime + teaming partner + supplier on one program): the emitted payload contains zero firm→firm edges or adjacency structures of any kind, and BOTH §4 participants-rail limitation strings (`participation_limitation` and `allocation_limitation`) render verbatim (EN and ZH); additionally, the participants rail's rendered copy for the `not_asserted` token is asserted UNEQUAL to the economic_relationships rail's copy (rail-scoped copy keys, gate 6).
13. **T13 — evidence publisher/host refusal (asserts only authority that exists).** (a) An evidence row whose `source_url` host is off the §3.1a government/official allowlist (e.g. a press aggregator) is refused at load with `publisher_host_refused` naming the host. (b) An `issuer_disclosure` row whose `source_url` host ≠ that row's worksheet-pinned `pinned_issuer_host` is refused with `issuer_host_pin_refused` — the comparison is against the PER-ROW PIN, never against any global issuer→host table (none exists in the estate). (c) An `issuer_disclosure` row missing or carrying an empty `pinned_issuer_host` or `pinned_issuer_host_basis` (both artifact fields per §3.1a — the loader never reads the worksheet) is refused with the same `issuer_host_pin_refused`. (d) A mirror-fetched row missing its host-of-record `source_url` is refused with `publisher_host_refused`.
14. **T14 — content-id collision resistance + platform referential integrity.** (a) Two admissible RAs identical except `role_scope` (or except `platform_id` Block V vs Block VI) mint DISTINCT `prog-role:` ids from the frozen preimage `program_id | platform_id-or-"-" | entity_id | role | role_scope | valid_from | revision`; a rebuild with both present leaves each byte-identical; a `superseded_evidence` successor (revision+1) likewise mints a distinct id with the predecessor byte-identical. (b) An RA carrying a `platform_id` whose platform does not exist, or whose `platform.program_id != role_assertion.program_id`, or whose temporal interval is incompatible with the platform's, is refused at load with `platform_reference_invalid`; an RA carrying `platform_id` with no `program_id` is refused the same way (platform-only assertions invalid in v1). (c) **Milestone window collision (D5R.2):** two milestone rows identical except `window.to` mint DISTINCT `prog-milestone:` ids (both endpoints are preimage slots — fixture G carries the computed pair); a milestone carrying both `date` and `window`, neither, or a `temporal_kind` mismatching the populated field is refused at load with `milestone_temporal_shape_invalid`. (d) **Duplicate identity (D5R.2):** two rows sharing an id with differing bytes refuse certification (`duplicate_identity_conflict`); a `shared_scope` or `verification_state` change submitted as an in-place variant of the same id is refused the same way, while its legal form — an `attribute_revision` succession (revision+1, distinct id, `predecessor_id`) — is accepted.
15. **T15 — event link is exact-identity or nothing (D5R.2).** (a) A candidate `program_event_link` whose `event_id` does not exist in the workspace event store (nor, under the documented cap, in the parquet fallback, §3.1b) is refused AT CURATE with `event_not_found`. (b) A link whose recorded `event_source_identity_id` or `event_source_identity_content_sha256` does not equal the live event's `award_change.source_identity.id`/`.content_sha256`, or whose recorded `canonical_award_identity` does not equal the comparand derived per §3.1b's precedence, is refused `event_identity_mismatch` (curate always; loader whenever the event is present in the current workspace window — an event aged out of the window is NOT a refusal, §3.1b) — hash agreement is mandatory, not advisory. (c) No fallback path exists: the loader has no name, description, ticker, or fuzzy matching input to consult (structural — those fields do not exist on the link row), and a candidate row carrying any such association provenance is rejected at the door (T6 vocabulary). (d) The link row carries zero copied event truth: no amount, date, agency, or recipient-name key exists on it. (e) A link whose refs' `claim_scopes` union lacks `program_event_link` is refused with `claim_scope_coverage_missing` (§3.1a per-kind coverage — the reference object's own link row carries the scope on `ev:2f718fd13f51`).
16. **T16 — capability relation requires relation evidence (D5R.2).** A `program_capability_link` whose refs' `claim_scopes` union covers `program_identity` and `capability_need` but NOT `program_capability_link` is refused at load with `claim_scope_coverage_missing`; a link naming a nonexistent program or capability is refused with `dangling_reference`, and one temporally incompatible with either endpoint with `temporal_incompatible`; no `implements_capability` relationship exists anywhere except as a `program_capability_links[]` row (grep-level assertion on the artifact: the relation cannot be smuggled in prose fields or inferred from slugs).
17. **T17 — review coverage derivation is artifact-only (D5R.2).** From the artifact alone (no worksheet, no research doc): a scope+subject with admitted rows derives `reviewed`; with a coverage row and zero admitted rows derives `reviewed_none` carrying the pass's `known_at`; with neither derives `not_reviewed`; with incompatible admitted rows derives `conflicted` plus a `conflicts[]` row. Deleting the coverage row from the reviewed_none fixture flips the derivation to `not_reviewed` (proving the state is derived, never stored free-floating); a coverage row with `known_at` after `analysis_as_of` is invisible to the derivation; the ONLY producer of coverage rows is the curate script (the propose script emitting one is refused). The dossier awards rail's `link_state` derives identically from `subject_type: program` coverage rows (§3.1c pairing): a program-subject `program_event_link` coverage row with zero admitted links ⇒ rail `link_state: reviewed_none`; no such row and no links ⇒ `not_reviewed`.

---

## 9. Experience architecture (Program / Platform Dossier)

Reference composition: `research/defense_intelligence/evidence/compositions/d5-program-dossier-virginia.html` (real pilot data, 1440/820/390 via CSS, shared `d0r-target.css`, sibling of the frozen D1/D2 targets). D0R H composition #5 law applies with two **recorded deviations** (deliberate, D6-bounded — not silent substitutions): (1) D0R's glance element "last GAO/DOT&E" requires GAO/DOT&E sources that are D6 scope; until then the glance carries phase + contract type + latest official program state (sources for each defined at the end of this paragraph), and the GAO/DOT&E element renders as a named gap. (2) D0R's why-rail "EAC / quantity": QUANTITY IS NOT REPRESENTABLE FROM THE TAPE IN v1 — the committed event rows carry no quantity field of any kind (their `amounts` ids are award-money ids only — `federal_action_obligation`, `current_award_amount`/`potential_award_amount`/`total_obligated_amount` and their `delta_*` siblings — with zero quantity/units keys; census receipt against `workspace.json` events), so the why rail renders the capability need statement and NAMES the quantity gap alongside the economics gap ALWAYS in v1, reviewed link or not; quantity becomes representable only with D6's SAR/budget sources, and nothing is parsed out of announcement prose. EAC and all cost figures are D6 (SAR/budget). The glance's "contract type" element is composed read-only from the award plane's dossier artifact — `data/government_revenue/dossiers.json` `awards[].classifications.award_type` (USAspending `contract_award_type` vocabulary, `collectors/usaspending_awards.py:1268`), joined by `awards[].award_key == program_event_link.canonical_award_identity` — rendered verbatim as the estate carries it (committed casing, e.g. "DEFINITIVE CONTRACT") — never a D5 field, never synthesized prose, and with no reviewed link (or no matching award row in the capped dossier window) it renders as a named gap keyed off `link_state: not_reviewed` (or the plane's own gap state), never a fabricated value. The glance's "latest official program state" element is sourced from the reviewed PLATFORM/variant record (e.g. "Latest block in the reviewed record: Block VI"), not from milestones (which are forward-only, §3.1). The GAO/DOT&E element renders as a named gap keyed off `source_unavailable` (sense: no GAO/DOT&E assessment on file, source not yet collected; exact bilingual copy is template-owned). Changed = award events reached ONLY via reviewed `program_event_links` (§3.1b; honest `link_state` gap otherwise — budget events once the budget plane lives); evidence = exact official sources; next = next FORWARD official milestone only.

D0R H2's fourteen required states, mapped (every composition must specify all; N/A must say why):

| D0R state | D5 dossier form |
|---|---|
| complete/current | all rails reviewed/current with cut clock in chrome |
| partial coverage | `source_state: partial` on the awards rail; per-rail mixed states |
| stale source / fresh transport | awards rail `source_state: stale` (source latency days–weeks) with fresh `generated_at` shown |
| stale transport | artifact `generated_at` older than the nightly cadence ⇒ rail-level stale banner (workspace freshness idiom) |
| identity unresolved | participant row whose issuer path is not reviewed — exactly §4's per-row enum (atlas issuer-path `not_asserted`, or `public_security` state `not_in_si_universe` — the row FIELD, not the schema's `publicSecurity` $defs alias); resolution-plane states (`unresolved`/`candidate_review`) never render on this rail — row shows the identity-state chip, no issuer link |
| conflicting graph | `conflicted` + conflicts row (§5) — attribution withheld, both evidences visible |
| corrected event | successor line from `predecessor_id` + "read being updated" chip (D3 idiom); predecessor stays visible, never re-titled as new |
| rights blocked | `rights_blocked` at the entitlement boundary (anonymous/locked view) |
| provider down | `source_unavailable` on the affected per-rail axis (awards `source_state`, budget); an ontology-plane failure is the bundle-level unavailable form (§4) + the `program_link` fourth shape |
| valid empty | `reviewed_none` ONLY (a review pass covered it and admitted nothing — never coerced from absence); the milestones rail may ALSO render `reviewed` with `rows: []` when every reviewed milestone has passed the §4 forward filter — template-owned copy distinguishes "reviewed, none upcoming" from "reviewed, none admitted" |
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
- The exact `unverified_supplier_language` trigger regex — a display-tier annotation (never law: T4 caps its effect at "at most an annotation"), chosen at implementation inside the `_action_text_annotations` two-regex family pattern (`award_events.py:869-878`); no correctness property depends on the choice.

Anything not listed here is frozen above or in the handoff; if a builder finds a decision this document does not answer, that is a D5R defect to report, not a choice to make silently.
