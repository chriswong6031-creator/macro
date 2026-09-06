# BioCatalyst R1B — owner-composed read model and bounded asset references

Date: 2026-09-06. Status: R0 interface candidate; NOT_BUILT until the named future implementations and consumers are verified.
Source operation: `biocatalyst-v3-r0-source-repair-20260906-sol-001`, existing Macro PR 6712.
Governing procedure: protected Mastermind `4fe4d6bc93d9543f77320f68342a10c5af4d4f49`, Skillpack 1.0.1/bootstrap 1.
Inspected owner source: Macro `a68fdb5bee7648ba734c8562c6f98233c3a80076`; candidate pickup `75a994307998dd8d25ff45dc53193d5c4dc5267c`.

## 0. Acceptance and capability boundary

The investor must move from a broad, honestly scoped catalyst queue to the evidence and the correct stock research page. A machine must receive the same event, timing, relationship and missingness objects without mistaking a sponsor string for economic ownership or a past schedule for an occurrence.

This document makes the previously unmade interface choices in R1B sections 5/8/11 explicit. It does not supersede company authority, source activation, historical soak policy, the accepted Trial Milestones contract, or any withheld amendment. Section 16 of the R1B packet and review 5126025473 remain the selected research-triage semantics. This document cannot accept itself or the whole R0.

Acceptance of this architecture requires an independent reader to implement the contracts below without choosing another identity authority, publication pointer, clock, route, or fiscal-event workaround. The accompanying normative cases are synthetic contract examples, not production data or a passing runtime test. Later R1B acceptance additionally requires the real owner-composed path, entitled browser journey and broad coverage proof.

Three alternatives were considered: a new global drug/security master (rejected as duplicate authority); indefinite waiting for a fully populated global asset graph (rejected as a circular build prerequisite); and existing owners plus explicit source-scoped asset references (selected). The provisional path preserves useful source context but grants no global drug equivalence or ownership inference.

## 1. Binding owner matrix

`EXISTING` below means the source surface was read, not that this new workflow is live. `PLANNED` means a bounded implementation under that owner is owed. No new service or state store is selected.

| Port | Owner and exact surface | Selected consumer / boundary |
|---|---|---|
| Registry source facts | EXISTING `engine/biocatalyst/trials.py::validate_trial_snapshot`, `build_trial_snapshot`; `trial_snapshot.v1` | Read the generation's validated trial projections, not raw contact/patient payloads. |
| Registry milestone identity | EXISTING `engine/biocatalyst/catalyst_events.py::project_trial_milestones` | Preserve its source event identity. New timing/occurrence projection must not copy its calendar-aged `occurred` label as corroboration. |
| Disclosure facts and non-fiscal event identity | EXISTING `engine/company_intelligence/documents.py`, `events.py`, `event_id_adapter.py`; PLANNED `company_catalyst_event.v1` read port, section 2 | Company Intelligence publishes the admitted port; BioCatalyst never starts a second SEC/IR collector or calls a fiscal workspace a catalyst producer. |
| Current issuer/security/CIK | EXISTING `lib/dataos/identity.py::IssuerMaster`; `scripts/build_security_master.py` remains allocator | PLANNED `IssuerMaster.issuers_for_cik` extends this same reader, section 3. No Bio CIK table or allocator. |
| Current symbol/listing | EXISTING `VendorAliasTable.resolve` / `vendor_symbol_for`, vendor `store` | Symbols are display/navigation aliases only. Canonical securities must already be active members of the same accepted master cut. |
| Therapeutic occurrence and relationship projection | EXISTING Bio domain ontology and validated trial/document evidence; PLANNED `engine/biocatalyst/asset_relationships.py` pure adapter | Source-scoped references and evidenced edges only; no persistent asset master, fuzzy auto-admission, or security minting. |
| What Matters Next composition | PLANNED `engine/biocatalyst/what_matters_next.py::build_what_matters_next` | Pure composition of the admitted bundle, declared query/cutoff and accepted triage policy; no collection or disk I/O. |
| Generation assembly and publication | EXISTING `engine/biocatalyst/publication.py`; PLANNED compatible manifest/artifact extension and `scripts/biocatalyst_worker.py` integration | One validated immutable generation; existing `current.json` moves last. Source/identity/disclosure input references are pinned together; no second current pointer. |
| API | EXISTING `app/biocatalyst.py`, `_read_bundle`, `_response`, `_PRIVATE_HEADERS`, `require_site_full_user`; PLANNED handlers below | New route reads the existing bundle once. Existing `/v1/catalyst-radar` behavior is untouched. |
| UI and research action | EXISTING `templates/biocatalyst.html.j2`, `templates/biocatalyst.js`, `scripts/build_biocatalyst.py`; existing `templates/stock.html.j2` query/hash route | Same Bio product surface plus an admitted current-security link; no new navigation, watchlist, or Terminal service. |

## 2. Company Intelligence disclosure port

Selected wire identifier: `company_catalyst_event.v1`, `schema_version: 1.0.0`. The future schema belongs at `contracts/company_intelligence/company_catalyst_event.v1.schema.json`, registered through the existing Company Intelligence contract validator. The producer is a bounded extension of that owner's existing event/document build; a pure `project_catalyst_event` function in `engine/company_intelligence/events.py` supplies this port. It is NOT an independently persisted Bio event bus.

Required closed fields: `contract_id`, `schema_version`, `event_id`, `company_id`, `issuer_cik`, `event_family`, `native_identity`, `revision_ref`, `revision_is_current`, `occurrence`, `timing`, `source_available_at`, `observed_at`, `document_refs`, `public_evidence`, `asset_mentions`, `relationship_claims`, `authority`. Object fields reject unrecognized keys. Optional information is represented by explicitly nullable fields, not omitted obligations.

Families for this first port: `issuer_readout_guidance`, `regulatory_target_disclosed`, `advisory_meeting_disclosed`, `result_announced`, `regulatory_action`. They describe the claim actually evidenced. Advisory advice, scheduled action dates, and final regulatory actions are not interchangeable. Unsupported families are listed by coverage and produce no invented event rows.

The current `CompanyEvent` requires `FiscalPeriod`; it cannot represent these families unchanged. The selected extension is a source-anchored variant in the SAME `events.py` owner, with the existing lifecycle/publication/evidence owners retained. Existing `evt_cik..._{year}{q|fy}_...` IDs and parsing remain valid and unchanged. A separately versioned non-fiscal variant, not `fy_action`, carries the new port. The existing `event_id_adapter.py` must recognize the two variants explicitly; no catch-all acceptance of arbitrary strings.

For the new variant, `canonical_source_event_id(company_id, source_namespace, native_event_key, event_family)` uses the full SHA256 of canonical JSON of exactly those four fields, prefixed `evt_source_`. It is an extension of the canonical Company event allocator, never a Bio-side hash. Schedule dates, document hashes, retrieval times, model outputs, and ticker spellings are excluded. The allocator rejects missing fields and unknown source namespaces/families.

A source-native stable event identifier is preferred. Where a disclosure has no such identifier, `native_event_key` is the FIRST admitted immutable Company Intelligence document ID plus its typed claim occurrence locator. That is a source-anchored occurrence, not a global assertion of equivalence. Later guidance attaches to it only with the Company's evidenced `revises` relation; a new accession alone cannot establish equivalence. Ambiguous restatements remain separate unresolved claims with `timing_state: conflicted` until owner reconciliation. The first anchor remains stable across corrected guidance. A false-positive merge is corrected by existing owner supersession, never by deleting history.

`document_refs` identify existing immutable Company Intelligence documents and their revisions. `public_evidence` is that owner's rights-checked projection, not raw licensed text or private storage locators. Each relationship claim binds a document/evidence ref, the subject asset mention, counterparty organization/CIK if explicitly evidenced, relationship kind, territory and effective interval. Missing CIK, territory, economics or effective time remains null with a reason. Models may propose extractions to that owner's existing review/admission path but cannot self-admit an economic relationship.

All knowledge clocks are UTC instants with explicit offsets normalized by the owner; the port rejects guessed timezone normalization. A future schedule is legal; a future `observed_at` or `source_available_at` at the consuming generation cutoff is not. Occurrence is family-specific evidence, not the event-envelope lifecycle's `complete` state or the passage of a scheduled date.

Port absence does not block the registry lane. It returns `unsupported_family: owner_port_not_built` for these disclosure families, not zero upcoming regulatory events. A production board that has only registry milestones must say so and cannot claim R1B's complete multi-family milestone. The missing port is a bounded Company Intelligence predecessor slice in the R1B build plan, not a reason to duplicate ingestion.

## 3. Current issuer/security join — no new identity plane

`IssuerMaster.issuers_for_cik(cik) -> tuple[str, ...]` is the only new Data OS reader method selected here. It uses the already stored `issuer_cik`, the same strict CIK normalization and active-security filtering as `cik_of_issuer`/`securities_of_issuer`. It returns sorted distinct existing issuer IDs. Zero matches is unresolved; multiple issuer IDs is ambiguous and must not be resolved by market size, first-row order or sponsor spelling. Conflicting CIK observations within one issuer retain the existing `IdentityError`. No IDs are allocated by this read method.

Input is an already validated, immutable security-master cut with unique security IDs and its accepted current-observation receipt, plus the matching vendor-alias cut. The source allocator remains `scripts/build_security_master.py`; `engine/intelligence_workspace/entity.py::_security_sources` is an existing example of duplicate/missing-ID refusal, not a new Bio-owned identity authority. The Bio adapter rejects incomplete or unbound input cuts instead of silently reopening arbitrary parquet files per row.

Given an evidenced Company Intelligence `issuer_cik`, resolve issuer(s), then active securities with `securities_of_issuer`. A security must actually occur in `IssuerMaster.rows`; `security_state_of(unknown) is None` does NOT establish that it exists. Reject a superseded/retired security for current stock navigation and retain its owner-supplied successor as evidence, never follow an unverified alias. Resolve display symbols through `VendorAliasTable.vendor_symbol_for('store', security_id, identity_cut_date)`.

All these joins are labelled `current_only`, with the identity-cut observation timestamp retained. The request cutoff cannot predate that observation. They are not usable for a historical issuer join merely because a source event is old. A past-event view may show today's stock relation explicitly as current context; R2 historical admission must independently prove the historical relationship and identity. A security-master filename, Git date, current listing or corrected ticker cannot manufacture that proof.

For multiple admitted securities of one issuer, the board keeps ONE issuer-event row and a sorted list of stock choices. It does not choose a preferred share class. Multiple evidenced issuers produce distinct issuer-event rows without duplicating the underlying source event. The derived row key is the structured tuple `(event_fact_ref, issuer_id)`; the unresolved row uses null issuer. This is a projection key, not another event or security allocator. Event, issuer-event and security counts are separate.

## 4. Bounded therapeutic references and economic claims

The selected owner is the existing BioCatalyst clinical-domain projection, not Data OS security identity and not Company Intelligence's corporate identity. The ontology schema's `asset_indication_temporal_owner` unit and asset/indication concepts are reusable design evidence; `data/biocatalyst/fixtures/ontology.v1.valid.json` is explicitly a fixture, not an admitted global asset registry or rights grant.

`engine/biocatalyst/asset_relationships.py::project_asset_relationships` is a PLANNED pure adapter over validated trial snapshots and admitted Company Intelligence claim/evidence objects. Its returned object is embedded in the existing generation's What Matters Next input artifact; it creates no independent database, append-only log, publication selector, identifier allocator or correction ledger.

An `asset_ref` is either an admitted canonical domain reference supplied by an existing owner, or this closed provisional shape: `{state: 'source_scoped', canonical_asset_id: null, source_system, source_object_ref, occurrence_path, observed_name}`. Allowed source systems are `clinicaltrials_gov_v2` and `company_intelligence`. `source_object_ref` identifies the exact accepted snapshot/document, and `occurrence_path` is its existing JSON-pointer or typed claim-occurrence locator. `observed_name` is display text, never a key. Missing or unresolved pointers make the reference invalid, not an invitation to fuzzy-match.

A source-scoped reference denotes only THAT source occurrence. Array movement or a corrected snapshot may change the reference; it never changes the parent source event identity. An existing owner alias/correction relation may connect occurrences, but string equality cannot. Two trials with the same drug name, a combination intervention, placebo, regional brand or acquisition do not acquire a shared canonical asset automatically. Multiple intervention occurrences remain a list, not a made-up merged drug.

An economic edge has closed fields `claim_ref`, `asset_ref`, `organization_ref`, `issuer_cik`, `kind`, `territory`, `valid_from`, `valid_to`, `observed_at`, `evidence_refs`, `admission_state`. Kinds are `sponsor`, `owner`, `licensee`, `licensor`, `co_developer`, `royalty_beneficiary`. Territorial rights and validity are source claims at native precision; unknown boundaries are null with a reason and cannot imply perpetual/global rights. The existing claim owner supplies correction/supersession. `admission_state` is `evidenced`, `unresolved` or `conflicted`; a missing claim reference or evidence cannot be evidenced.

Wholly owned, licensed, subsidiary and multi-party relationships require their respective evidence. Registry lead-sponsor status supports only `sponsor`; it is not proof of ownership, royalty economics, a parent corporation, or a listed issuer. A sponsor-name/ticker annotation may remain visible as unadmitted context but cannot populate an admitted issuer ID or stock link. CIK corroboration and corporate-parent edges come from the existing corporate owner.

For the RP adapter, `identity_state: resolved` means the row's stated relationship kind has an evidenced organization-to-current-issuer join and a valid source-scoped or admitted asset occurrence. It does NOT mean a source-scoped asset became canonical. An evidenced sponsor-only relationship may therefore support research triage and an explicitly labelled sponsor-stock link, while `economic_exposure_state` remains `unresolved` and materiality remains NOT_ESTIMABLE. If the organization/issuer join or occurrence is unverified, RP identity is unresolved. A missing global asset ID alone is disclosed, not hidden or mislabelled as a canonical identity.

Accepted economic claims produce `economic_exposure_state: evidenced`; contradictory or missing claims produce `conflicted` or `unresolved`. Never infer an exposure percentage from relationship kind or divide 100% among partners. Conflicts remain visible and the aggregate materiality slot stays NOT_ESTIMABLE. The default queue never suppresses a row merely because its asset is provisional or its economics are unknown.

## 5. Selected wire contract and generation transaction

The new READ PROJECTION is `biocatalyst_what_matters_next.v1`, `schema_version: 1.0.0`; future schema path `contracts/biocatalyst/biocatalyst_what_matters_next.v1.schema.json`. Register it through the existing `engine.sector_intelligence` contract registry. It does not replace `trial_snapshot.v1`, source EventFacts, company events or historical artifacts. `build_what_matters_next(bundle, query, evaluation_cutoff)` returns the validated read model, never source state.

The generation assembler extends `engine/biocatalyst/publication.py` with ONE optional, content-hashed artifact `what_matters_next_inputs.json` in its existing manifest. Its internal contract is `biocatalyst_wmn_inputs.v1`: `contract_id`, `schema_version`, `input_cut`, `events`, `relationships`, `identity_projection`, `coverage`, `authority`. No request-relative priority is persisted in this artifact. It contains public-safe owner projections only. Existing generations lacking it remain readable by Trial Intelligence; the new endpoint returns `owner_projection_missing`, not fabricated empty rows.

`input_cut` binds each contributing owner artifact's contract, immutable generation/ref, full content hash, observed/accepted timestamps and availability state. Required cut members are the validated Bio trial source-manifest/snapshot cut and current Data OS master/alias cuts. When trial snapshots are assembled in the same publication transaction, bind their pre-existing source-manifest and staged snapshot hashes, NOT the future enclosing generation ID; a reused prior public generation may instead be referenced by its already committed ID. Company Intelligence and optional model/history owners are present with a verified cut or explicit `not_built`, `unavailable` or `not_admitted`; a missing optional port never becomes a zero-valued fact. Raw locators and credentials never enter this projection. The assembler obtains owner-approved projections through existing worker/input paths; it does not read an unpinned current file in the request handler.

The publication owner validates all configured artifact hashes, authority/rights, cross-references and clock bounds; writes the complete candidate privately/staged through its existing transaction; verifies readback; and advances the ONE existing pointer last. A failure preserves last-known-good. No global atomic snapshot across unrelated systems is claimed: the manifest attests a consistent SELECTED composite cut with each member's own as-of. Cross-owner skew is disclosed and governed by their accepted health policies, never a new guessed freshness threshold.

Avoid circular hashes: the input artifact contains upstream cut refs, not its future output generation ID. The enclosing existing manifest binds the artifact's hash; the API response obtains its generation ID from that committed manifest. No artifact is required to hash a manifest that hashes the artifact itself. An owner input change, relationship correction or changed admission yields a successor generation; changing the request's relative date does not publish a new source generation.

### 5.1 Closed response envelope

Required keys: `contract_id`, `schema_version`, `generation_id`, `state`, `reason_codes`, `input_cut`, `query`, `evaluation_cutoff`, `anchor_date`, `method_id`, `authority`, `coverage`, `rows`, `pagination`. `generation_id` is the existing committed public generation ID. `method_id` is exactly `biocatalyst.research_triage.v1` in V1. No arbitrary nested extension maps are accepted; each subobject below is closed.

`state` is `ready`, `partial`, `stale` or `empty`. `ready` means the DECLARED supported slice is complete under its accepted owner policies, not that every biotech event family exists. `partial` outranks `stale` if coverage is incomplete; `stale` applies when selected retained source health is stale; `empty` means a valid complete selected view has zero rows. Optional model NOT_ESTIMABLE does not itself make source coverage partial. Integrity loss/no valid generation is a typed non-200 failure, not `ready` with an empty array.

`query` has `view`, `horizon_days`, `q`, `event_family`, `lane`, `limit`. Views: `upcoming`, `reconcile`, `history`; default `upcoming`. Horizons: 7/30/90/180/365, default 90; other views carry null horizon. Filters are exact closed enums or null; q is trimmed/casefolded for matching (maximum 100 Unicode characters), original display text separately retained by the UI. Unknown or contradictory selection is HTTP 400. Limits use the existing `_query_limit`, default 50; no new independent limit policy.

`authority` is closed: `classification: research_priority_only`, `trade_origination: false`, `changes_availability: false`, `position_sizing: false`, `prophet_admission: false`. Source facts inside rows keep their OWN stricter source-fact authority; wrapper research ordering does not upgrade a nested fact or an unrelated downstream consumer.

`coverage` separately carries `declared_universe_ref`, `source_event_count`, `issuer_event_count`, `security_count`, `unresolved_event_count`, `rejected_count`, `superseded_count`, `lane_counts`, `selected_row_count`, `family_states`, `missing_owner_ports`. Global counts are computed before view/page selection; selected count is after filtering but before pagination. Event counts deduplicate event_fact_ref, not dates, stock choices or relationship count. A missing upstream denominator is null with an explicit reason, never inferred from output length. Family states contain declared scope, observed count or null, and `supported`, `not_built`, `unavailable`, `not_admitted` or `partial`.

### 5.2 Closed row and missingness objects

Each row has exactly `row_key`, `event_fact_ref`, `event_family`, `event_revision_ref`, `revision_is_current`, `occurrence`, `timing`, `issuer`, `assets`, `relationships`, `economic_exposure_state`, `evidence`, `revision_summary`, `research_priority`, `probability`, `materiality`, `historical_response`, `incorporation`, `missingness`, `links`.

`row_key` is `{event_fact_ref, issuer_id}`; `issuer_id` is null for an unjoined event. `issuer` is `{state, issuer_id, company_id, relationship_role, identity_scope, identity_observed_at, securities}`. State is `resolved`, `unresolved` or `ambiguous`; `identity_scope` is `current_only` or `unavailable` in this first version. Each security is `{security_id, listing_key, display_symbol, symbol_observed_on, state}` and must pass section 3. Display symbols may be null; an absent symbol does not erase a canonical security. A source CIK/company_id is not silently equated with an ISS:* issuer ID.

`assets` is a list of section 4 references; `relationships` is a list of that section's admitted or unresolved claims. For RP's optional exposure tie-break use the lexicographically first stable, owner-supplied relationship claim_ref for this issuer-event row, or null; do not mint an exposure ID or use a correction's document hash. All claims remain inspectable. Selection of this tie-break ref never chooses a preferred economic beneficiary or share class.

`timing` is `{state, source_class, lower_date, upper_date, precision, source_timezone, source_wording, evidence_refs}`. State is `consistent`, `conflicted` or `missing`; source class is `registry_schedule`, `issuer_guided`, `regulator_disclosed`, `rule_derived` or `unresolved`. Bounds are closed source-calendar dates, not invented instants. Precision is `day`, `month`, `quarter`, `year`, `window` or `unknown`; source timezone may be null. All conflicting source claims are retained in evidence; they are not averaged. When the owner has not adjudicated a preferred claim, conflicting bounds are null in this summary and each original interval remains in evidence; the composer does not select the earliest or widest interval as a fact. `rule_derived` is withheld until its separately accepted method/coverage can be supplied; no V1 heuristic readout date is added here.

Each estimate slot is `{state, value, reason_code, method_ref, as_of, evidence_refs}`. State is `NOT_ESTIMABLE` or `available`; NOT_ESTIMABLE requires null value plus a nonempty reason and never a neutral numeric fallback. Available values are the separately accepted owner object's validated public projection with its own schema/method/coverage, not an arbitrary JSON blob. Until that owner's schema is explicitly admitted in the read-contract registry, the slot remains NOT_ESTIMABLE. This keeps the first slice executable without silently inventing R2-R4 schemas. Available owner components may be shown in evidence while an unsupported aggregate remains NOT_ESTIMABLE.

`research_priority` contains method_id, lane, primary_reason, ordered gap reasons, comparison_date and authority, all from the accepted section 16 adapter. `missingness` retains separate source, identity, asset, economic and estimate reasons. An output claiming `identity_state: resolved` must be accompanied by its exact relationship role and current-only scope; unresolved economics cannot disappear under a generic high-confidence badge.

`evidence` contains only existing public source URLs, owner-approved snippets and source-date/precision/correction facts. All private storage, host, credential, raw-contact and unauthorised licensed-text fields fail the public projection recursively. `revision_summary` records actual owner correction refs and material-change clocks; it never infers a changed protocol or realized outcome from a fetch timestamp. `links` contains only selected internal routes or validated public source URLs, never caller-supplied filesystem/object locations.

## 6. Request, inspector and research-action bindings

New list route: `GET /api/biocatalyst/v1/what-matters-next`. New inspector route: `GET /api/biocatalyst/v1/what-matters-next/detail`, with required `generation_id` and `event_fact_ref`, optional `issuer_id`. Both live in the existing `app/biocatalyst.py` router and use `Depends(require_site_full_user)`, `_PRIVATE_HEADERS` and `_response`. Authentication/entitlement denial occurs before generation or identity reads. Existing source routes and their recursive authority checks remain unchanged.

The handler resolves the current committed bundle once, validates its input cut, establishes the server evaluation cutoff and UTC anchor on page one, then invokes the pure composer. The composer projects current rows, applies RP classification, records global counts, filters, sorts the whole selected set and returns one page. Evidence/identity reads do not happen inside a row loop. There is no LLM or network request in this path.

Extend the existing HMAC cursor mechanism with a separate `what_matters_next.v1` purpose/version; retain the existing secret/configuration source and old-route compatibility. Its signed fields are purpose, generation_id, normalized query, method_id, evaluation_cutoff, anchor_date and last complete stable ordering key. A cursor valid for Trial Milestones must not be accepted here. No unsigned caller cutoff or row offset may override these bindings. Section 16's correction/day/query reload semantics remain controlling.

The inspector resolves an event ONLY from the selected current generation's catalog. A changed generation returns 409 `RELOAD_REQUIRED`, not a new inspector paired with an old row. A valid but unknown event/issuer combination returns 404 `EVENT_NOT_IN_GENERATION`. Generation and event parameters are logical IDs, never paths to open; reject traversal, raw object keys and arbitrary URLs. Existing retention remains the retention owner: this new endpoint does not create an archival-access service.

The first stock research route is the existing `stock.html?ticker=<URL-encoded-current-store-symbol>`, whose `templates/stock.html.j2` query boot normalizes to the existing hash route. A PLANNED pure `stock_research_link` in `what_matters_next.py` emits it only after section 3 admission, and records the relationship role (for example Registry sponsor, not Asset owner). Multiple share classes present a chooser; unknown/superseded securities or missing aliases yield no guessed link. Terminal-specific routing and watchlist mutation are not needed to invent this first action.

The trial action retains the existing Bio trial-detail flow; the new inspector uses the selected generation before delegating to that flow. The first release must verify the existing trial selector/router in `templates/biocatalyst.js`, not hard-code a different URL syntax. For an unjoined event, evidence inspection and a copyable research question remain available even without a stock link. Evidence is useful, but an all-unjoined board cannot claim the stock-research R1B milestone.

Failure contract: existing auth errors retain their established 401/403 behavior; invalid filter, malformed identity or cursor is 400 `INVALID_REQUEST`; valid expired/query-changed/day-changed generation binding is 409 `RELOAD_REQUIRED`; valid absent inspector row is 404; absent/corrupt required generation/input cut is 503 `OWNER_INPUT_UNAVAILABLE`. All responses remain private/no-store through existing headers. Errors contain bounded public reason codes, not exception strings or private paths. Optional owner absence produces coverage/missingness in a valid response, not a blanket 503.

Before implementation release, freeze the existing `_query_limit` bounds and actual auth/error transport in conformance tests against the action-time owner head. This is compatibility verification of existing behavior, not permission to choose new limits or an alternative authentication mechanism.

## 7. Ordered bounded implementation and proof

1. R0 independently accepts this interface and the remaining experience package. This records-only PR does not start any source collector or implement these modules.
2. R1A establishes its accepted broad source generation under the existing publication and source-policy gates. Its ended-soak NOT_RECOMPUTED result is not changed here; any prospective source transition requires its original owner's decision.
3. Implement the current-issuer CIK lookup inside Data OS with duplicate/ambiguous/current-only tests and its real Bio consumer, not a second resolver. Extend Company Intelligence's non-fiscal event/document port in a bounded owner-reviewed slice with a real consumer and correction proof. Owner source changes require fresh collision checks; never edit another active worktree.
4. Implement the pure Bio relationship/input/read projections, contract registration and existing-generation publication extension together with the actual router consumer. Preserve old source routes and pointer behavior. New artifact absence must be exercised against an old generation.
5. Implement the accepted RP policy through this composer, including the existing normative RP cases. Freeze input cut, method and day-bound cursor as one request context; exercise real pagination and inspector handlers.
6. Implement the independently frozen Bio page compositions in its current UI owner, with paired plain-copy assets where applicable. Test signed-out/locked, ready, partial, stale, unresolved, empty and correction/reload journeys in both languages/themes and desktop/mobile.
7. Production acceptance binds deployed commit, generation and owner cut IDs, truthful source/event/issuer/security counts, disclosure-family readiness, actual correct stock navigation, evidence resolution and no private leakage. A nonzero page, a four-NCT demo, a schema, or this document is not that proof.

Owner unavailability changes which slice can execute, not the truth of the milestone. Registry-only or all-unresolved output remains a correctly labelled partial capability until the advertised stock and disclosure journeys work. Models/history/incorporation may remain NOT_ESTIMABLE without blocking the first research workflow. No later intelligence infrastructure outruns that workflow.

## 8. Discriminating acceptance cases and evidence limits

`BIOCATALYST_R1B_OWNER_INTERFACE_CASES_2026-09-06.json` names the exact expected outcome for sponsor-only versus owner claims, current/historical joins, dual share classes, multi-issuer counts, provisional occurrence changes, missing disclosure ports, future clocks, generation/cursor/inspector coherence, old-generation fallback and failure-before-I/O. Synthetic source/issuer names are deliberate; none is a production assertion.

The actual later producer/handler must execute those cases, not just compare fixture text. In particular: wrong CIK mapping, sponsor-as-owner, asset-name dedupe, current-to-historical promotion, snapshot-clock reclassification, arbitrary inspector paths, mixed-generation pages, self-referential generation hashing and auth-after-I/O each must produce a failing test when the guard is removed.

This architecture selects source-scoped asset identity and explicitly typed relationship claims. It does not pronounce any real company/drug relationship, grant proprietary data rights, assert a new live schema, or waive the existing source/publication acceptance. Real broad coverage, browser proof, and the remaining whole-R0 findings retain their own acceptance boundaries.

### 8.1 Exact compatibility decisions from the inspected handlers

The inspected `_query_limit` accepts a one-to-three-digit string and integers 1 through 250 inclusive; default remains 50. V1 adopts those exact bounds. Action-time comparison verifies compatibility, not an unmade threshold. Null q means no search; an explicitly empty/whitespace-only q is rejected by `_query_text`, matching the current route. Registry family tokens are `registry_primary_completion` and `registry_study_completion`; disclosure tokens are exactly section 2's five values. A family filter for an unsupported but recognized family yields its coverage explanation and zero selected rows, not an unknown-filter error.

Company Intelligence's current `contracts.py` uses explicit Python validators rather than the Bio registry. The planned `validate_company_catalyst_event` is added THERE with the versioned schema as its machine-readable mirror; do not invent an existing generic registration API or a second validation authority. Bio's read projection is registered through its existing sector-intelligence registry only.

The existing UI functions `selectTrial` and `showDetail` are the actual Trial Intelligence entry/render seams. `selectTrial` currently fetches the latest `/api/biocatalyst/v1/trials/{nct_id}` without binding the new WMN generation. Therefore the WMN inspector MUST NOT simply invoke it and stitch that latest response onto a retained row. Add `selectWhatMattersNextRow` in the SAME `templates/biocatalyst.js`; it calls the generation-bound new detail route, then reuses `openInspector`, `detailLoading`, `showDetail`/existing evidence components with the validated SAME-generation trial detail. Reuse the existing AbortController and response-token stale-response guards.

The detail wire is `biocatalyst_wmn_detail.v1`, future schema `contracts/biocatalyst/biocatalyst_wmn_detail.v1.schema.json`: closed keys `contract_id`, `schema_version`, `generation_id`, `event`, `trial`, `related_events`, `reason_codes`, `authority`. `event` is the selected row from section 5.2; `trial` is the existing public trial-detail projection from that generation or null with `non_registry_event`; related events must resolve within the same generation. Each related event retains its canonical source owner identity. Detail has no new ranking or lifecycle authority. An optional explicit navigation to the standalone latest Trial workspace leaves the old WMN selection context; it is not presented as same-generation evidence.

For time-safety, every selected knowledge/acceptance timestamp is no later than the immutable composite-cut cutoff and the request evaluation cutoff. Later owner updates do not leak into that retained generation. A disclosure's amended date does not rewrite its first public-known clock; a material revision has its own observed timestamp. Field absence, source null, not built and malformed input remain distinct rejection/missingness states.

## 9. Exact source evidence

All owner blobs below were read at Macro `a68fdb5bee7648ba734c8562c6f98233c3a80076`; they are source evidence, not production receipts. Source movement intersecting these interfaces requires compatibility review, not an ancestry-only source commit.

| Path | Git blob |
|---|---|
| `app/biocatalyst.py` | `18dc16edf61749879a02043b00a1bbae66123d85` |
| `engine/biocatalyst/publication.py` | `72fa2d872cd22f71797a2c7ed58b1c30f9b60291` |
| `engine/biocatalyst/trials.py` | `89dfc595d9156022f5f139cd33bdb28d0ce2af65` |
| `lib/dataos/identity.py` | `16f272df801229ac0bb69dbc70d834097c9afc16` |
| `engine/intelligence_workspace/entity.py` | `5303d211a830bc84650b7934dd906cb2d30005a0` |
| `engine/company_intelligence/events.py` | `9d839a468ba0de2b2ea090bfe7d3ae698d303c44` |
| `engine/company_intelligence/contracts.py` | `750cf16e481e98222e6f078eb6a28ef3e8e45d7f` |
| `contracts/biocatalyst/ontology.v1.schema.json` | `5292540330d313b4aacf624fe4374cce9d95c741` |
| `templates/biocatalyst.js` | `565ab98b440f95895e5e4477df2c60a00f38d110` |
| `templates/stock.html.j2` | `0a23d4e19f27a070bbdefb7dbf04fc50844d2870` |
| `agentos/decisions/DEC-BPC-CATALYST-COMPOSES-WITH-COMPANY-EVENT-NOT-FISCAL-WORKSPACE.md` | `a833a2583ffb78ac80b59ba44c4e2abab2358012` |
