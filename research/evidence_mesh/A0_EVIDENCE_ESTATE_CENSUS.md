# A0 — Evidence / provenance estate census

**Commission:** MASTERMIND GROK-A0 (2026-08-18)  
**Checkout:** `origin/main` `3d12412e561e`  
**Scope:** read-only. No implementation. No new store. No invented ownership.  
**Status of this file:** CODE VERIFIED against contracts and engine modules this session, plus five bounded explore-lane reports whose load-bearing claims were re-opened on the primary artifact. Live HTTP / R2 / VPS state is PRIMARY SOURCE VERIFIED only where a prior handoff already recorded it; this session did not re-fetch.

There is **no** existing Evidence Mesh (`research/EVIDENCE_MESH*.md`, `engine/neuralweb/evidence_mesh.py`, `engine/neuralweb/evidence.py` — search bound: those names, 0 hits). The estate is many owner-local planes. The Mesh, if built, must join them.

---

## How to read this census

Each row is one **object**, not one program. Programs often own several objects with different clocks and PIT quality. Authority listed is what the contract already declares — this census does not grant or move any.

Claim tags: **CODE VERIFIED** · **PRODUCTION VERIFIED** (committed artifact on this checkout) · **PRIMARY SOURCE VERIFIED** (prior recorded live check, not re-run) · **INFERRED** · **UNKNOWN**.

---

## 1. FIF / Filing Forensics / financial intelligence packets

Owner workstreams: `WS:FINANCIAL-INTELLIGENCE-FABRIC` (FIF-1 in progress, FIF-2 stopped), `WS:FUNDAMENTAL-FORENSICS`, `WS:CALCBENCH-FILING-FORENSICS-PARITY`.

| Object | Contract / schema | Grain | Subject key | Clocks | Correction | Evidence IDs | Quality | Freshness | Authority | Readers | PIT | Siblings |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `financial_intelligence_packet.v1` | `contracts/financial_intelligence_packet.schema.json` | One query answer for one entity × metrics × periods | `entity.entity_id` **must equal** 10-digit `cik`; `packet_id` `fip_`+24 hex | Query: `source_event_cutoff` + `system_recorded_cutoff`. Cell: `source_event_time` / `system_recorded_time`. `built_at` is assembly. No `observed_at`. | `revisions[]` hops; cells not mutated | `source_occurrence_ids`, accession, `source_digest`, rule digests, `receipts.*_sha256` | `quality_state`, `coverage_state`, `non_value_state` | Cutoffs are explicit; not a live store | `context_only`, `display_only=true` | `scripts/build_financial_intelligence_packet.py`, tests. FIF-2 API todo | Derived view, not a store | Same facts as raw ledger / query kernel | CODE VERIFIED |
| `fundamental_forensics.raw_ledger/v1` | `engine/fundamental_forensics/raw_ledger.py` (no JSON Schema under `contracts/`) | One `RawFactOccurrence` | `occurrence_id` = hash of source+concept+context+unit+value+clocks+event_type+`revision_of` | `accepted_at` (source event); required `recorded_at`; optional `mapping_available_at` / `computed_at` / `published_at` | Append-only new occurrence; `revision_of` required for revision types; `FILED` cannot carry `revision_of` | `SourceIdentity` (source, entity_id, accession, document_id, body_sha256) | `AvailabilityStatus`; withdrawn via event type | Query applies both clocks before vintage | kernel, not product | `query.py`, packet assembler | Immutable events | Company Facts conversion can emit these; FIF-1 must not use CF as core query ledger | CODE VERIFIED |
| Filing package / attestation / query snapshot / attested v2 | `engine/fundamental_forensics/{filing_package,filing_attestation,query_snapshots,attested_query_snapshots}.py` + FF contracts | One accession inventory / sealed query / CF-correspondence overlay | `ffpkg_` / `ffatt_` / `ffqs_` / `ffqsv2_` + cik+accession | `assembled_at` / `retrieved_at` / `published_at`; `available_at`/`filed_at` on metadata | New content-addressed object; pointer last; v2 overlays v1 and never upgrades it | member `content_sha256`, conversion receipts | Inventory states; `xbrl_semantic_attested=false` unless elsewhere | Source freshness SLA 4d on composed FF | context / inventory | attested-history API (`app/forensics.py`) | Immutable + latest pointer | Distinct from FIF synthetic fixture | CODE VERIFIED. Production issuer **not admitted** (writer-key gate) |
| `fundamental_forensics.companyfacts_ledger/v2` | `engine/fundamental_forensics/companyfacts_ledger.py` | One CF unit-array entry → occurrence + companion | `cffledger_` + occurrence_id + CIK | `accepted_at` from Submissions join (**null if unjoined**, fail-closed); `recorded_at` = max of CF/capture/submissions/revision clocks | `revision_of` only if caller supplies auditable revision evidence. CF itself has no amendment lineage | capture/manifest/accession/entry digest | `dimensions_known=false` always (`DSC:COMPANYFACTS-CANNOT-FEED-CORE-METRIC-QUERY`) | CF is a **current observed snapshot**, never as-of poll start | witness / inventory | attested snapshots; FIF **witness hash only**; CS sibling | Deterministic conversion; SEC endpoint overwrites | Same SEC CF bytes as CS share-count | CODE VERIFIED |
| `fundamental_forensics_state.v1` | `engine/fundamental_forensics/private_state.py` | Current workbench blob | Company map | `generated_at` must not be relabeled source freshness | **Overwrite** latest | Private object | Product current-state | Health clocks in `fundamental_forensics.health.v1` | premium product current | `app/forensics.py` | Snapshot-only | Separate plane from attested-history | CODE VERIFIED |
| FIF-1 hermetic fixture | `tests/fixtures/fundamental_forensics/*` | Synthetic issuer ledger | CIK `0000999999` / `FIP1` | Fixture clocks | Fixture includes restatement hops | Occurrence IDs + accession | Hermetic test only | Golden cutoffs in tests | context_only | Packet builder tests | Snapshot fixture | Must not be minted from Company Facts | CODE VERIFIED |

FIF packet query policies (CODE VERIFIED, schema + `query.py`): `as_reported` · `latest_known_as_of` · `latest_restated`. Evaluation mode is a label; it never bypasses the two cutoffs.

---

## 2. Earnings event workspace / claims / transcript linkage

Owner: `WS:EARNINGS-INTELLIGENCE-OS` (E1P done, E2 todo). Program key `earnings-intelligence`. Evidence spine subprogram: `earnings-evidence-spine`.

| Object | Contract | Grain | Subject key | Clocks | Correction | Evidence IDs | Quality | Authority | Readers | PIT | Siblings |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `company_event.v1` | `engine/company_intelligence/events.py` | One issuer × fiscal period × event_type | `evt_cik{10}_{yyyy}q{n}_results` — **never ticker** | Every transition: `observed_at` ≥ `source_available_at` or refuse | Same `event_id` on `corrected`; `supersedes` is a different event | `source_receipt_ids`, `document_ids` | Coverage states (`blocked_rights`, `source_missing`) ≠ event states | `context_only` | `event_workspace.py` | In-memory immutable record | Aliases `cie_*`, `TICKER/YYYYQn` | CODE VERIFIED |
| `event_workspace.v1` | `engine/company_intelligence/event_workspace.py` (no `contracts/*.schema.json`) | One compact payload per canonical event | `event_id` + aliases | `lifecycle.{observed_at,source_available_at}`; `generated_at` | Event id correction-stable; new `generation_id` for payload change | `sources[]` (transcript, 8-K, wire, typed absences) | `completeness` per rail; v1 `claim_citations_pending` may stay true | `context_only`; Prophet flags false | `read_event_workspace` | Immutable generation + sibling marker | CI v1 context is a **different** object | CODE VERIFIED. Live AAPL nest PRIMARY SOURCE VERIFIED via E1P handoff (HTTP 200, generation `f709a0a6ec514282d5769e7d`). Not re-fetched this session |
| `company_identity.v1` | `engine/company_intelligence/identity.py` | Issuer / security / listing alias | `company_id` = `cik:`+10 digits; `security_id` = `{mic}:{ticker}`; ticker is PIT alias | Alias `valid_from` / exclusive `valid_to` | Mapping registered today must not retro-attribute older events | — | Resolver refuses on ambiguity | `context_only` | events, workspace | PIT ticker resolution | Data OS `ISS:`/`SEC:` is a **designed sibling**, not this module | CODE VERIFIED |
| `source_document.v1` / `source_span.v1` | `engine/company_intelligence/documents.py` | One versioned document or replayable span | `document_id`; filing key `(cik, accession)` | `fetched_at`, `available_at`, `published_at` | `revision` + `supersedes_document_id` | `content_sha256`; span `text_sha256` if `byte_replayed` | `address_only` is unreplayable | `context_only` | workspace build | Revision chain | Transcript vs release receipts use different coordinate spaces | CODE VERIFIED |
| `earnings.fact_pack` / `claim_graph` / `evidence_manifest` | `engine/earnings_narrative/contracts.py` | One transcript event’s facts/claims | `ticker` + `transcript_id` (`YYYYQn`) | `generated_at`; source `index_generated_at` | Manifest `supersedes_source_sha256` | Span receipts (source/segment/text sha + offsets) | Closed warning sets | `context_only` | story_store, public_wire, context_packets | Content-addressed; marker last | Terminal `mastermind.tx/v1` is the body | CODE VERIFIED |
| `earnings.context_packet/v1` | `engine/earnings_narrative/context_packets.py`; synapse `earnings-evidence-context-latest` | One ticker’s public excerpts | `context_id` `earnctx_` | Manifest `knowledge_cutoff`; source `known_at` | Source `correction_status` | article/packet/story ids + `source_sha256` | Completeness forced transcript-only | `context_only` | `earnings_context_reader.py`; BioCatalyst adapter | Latest selected packet only | Not a filing store | CODE VERIFIED |
| Public wire / story / private record | `engine/earnings_narrative/{public_wire,story_store,private_publication}.py` | One call-record page / packet | slug `{ticker}-{transcript_id}-call-record` | Wire lastmod; source `index_generated_at` | Admission `correction_status`; pointer last | Exact UTF-8 span receipts | Transcript-only completeness **forced** | `context_only` | Public archive, Brain, API | Immutable articles + pointer | Can be live while CI latest is older (`DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`) | CODE VERIFIED + PRIMARY SOURCE (E0) |
| `earnings_release.bound_release/v1` | `engine/earnings_release/` | One Exhibit 99.1 bound to a filing | Filing `(cik, accession)`; event `(cik, report_date)` | `acceptance_datetime` (SEC, never processing clock) | 8-K/A = new filing, same event | char/byte span hashes | Receipt replayed before return | `context_only` | `event_workspace_build.py` only exclusive importer | In-process bind | Distinct coordinate space from transcript receipts | CODE VERIFIED |
| `earnings_transcript_span_read.v1` / `biocatalyst_transcript_context_bundle.v1` | `contracts/biocatalyst/earnings_transcript_span_read.v1.schema.json` + bundle | In-process projection of latest context packet | `read_id` / `bundle_id`; query ticker + `as_of` | Document `known_at`; generation `knowledge_cutoff` | Document `correction_status` | `document_id` `earnings_transcript_*` | Mentions are candidates, `asserted=false` | A1_EXPLAIN; `persistence_authorized=false` | BioCatalyst adapter | Ephemeral; `history_scope=latest_selected_context_packet_only` | Must not be used as identity resolver | CODE VERIFIED |
| `data/earnings/earnings.parquet` | `collectors/equity_earnings.py` | One **calendar** row per ticker | ticker | `as_of` sweep stamp | Overwrite / mixed as_of on partial sweep | None SEC | Unofficial Nasdaq dates | none / display countdown | stock_fundamentals, blackout | Replace snapshot | **Not** an earnings event evidence store | CODE VERIFIED |
| `data/edgar/earnings_8k_dates.parquet` | `collectors/edgar_earnings_8k.py` | One Item 2.02 8-K | `(cik, accession)` | `acceptance_datetime`, `filing_date`, `report_date` | New accession; 8-K/A distinct | accession, items | PIT: filing_date conservative | none | workspace collector join | Append-dedup | Join with workspace on `(cik, accession)` only | CODE VERIFIED |

---

## 3. Defense / government-revenue evidence

Owner: `WS:DEFENSE-PROCUREMENT-V3` / program `government-revenue-foresight`. Live projector is **v2 only**.

| Object | Contract | Grain | Subject key | Clocks | Correction | Authority | PIT | Notes |
|---|---|---|---|---|---|---|---|---|
| Award snapshot / action / action version | collector tables + `government_procurement_event.v2` | First-seen award state per UTC day; official transaction; later revision of same native action | `award_key` / `generated_unique_award_id`; event `record_id=award:{award_key}` | Dual clock required: `known_at`/`first_seen_at` + `effective_at`/`action_date`. Fail-closed if missing | New immutable event; event_id includes `known_at` so A→B→A = 3 events | context / display | PRODUCTION VERIFIED: 210 snapshot rows, 35,257 action versions | Snapshot $ and action $ must not be summed | CODE + PRODUCTION |
| `government_procurement_event.v2` | `contracts/government_revenue/government_procurement_event.v2.schema.json` | One display card (`opportunity` / `recompete` / `award_change`) | `event_id` `govws-`/`govopp-`/`govawd-` | `change.{effective_at,known_at,first_seen_at,last_seen_at}`; receipts add `retrieved_at` | Same-id contradictory payloads **dropped**, not last-write-wins | declared on event | Workspace 2026-08-18 `bundle_id=grw2-df3a9860110d76a89dd9cc6b` | Dual-rail observation is intentional | CODE + PRODUCTION |
| `government_procurement_workspace.v2` | workspace.v2 | UI bundle, max 500 events | `bundle_id` `grw2-…` + `as_of` date | `as_of`, `known_at`, `generated_at` | Projection overwrite | display | Opportunity visible=0 this checkout | Not a second fact store | CODE + PRODUCTION |
| Candidates + ledger | `government_revenue_candidate.v1` + queue | Research hypothesis per issuer × official event | `candidate_id` `grc1-…`; durable join = `source_event.{event_id,record_id,source_rail,source_content_id}` (`observation_id` rotates) | `effective_at`, `known_at`, `analysis_as_of`, `generated_at` | Ledger append-only; queue rebuilt | context | as_of 2026-08-18 | Do not join on `observation_id` as durable | CODE + PRODUCTION |
| Issuance corrections / historical suppressions | two v1 config manifests | Quarantine exact issued row / do-not-backfill tombstone | candidate_id + source identity + issued row sha256; suppressions **omit** `observation_id` | `reviewed_at`, incident clocks | Never delete the ledger line | reviewed policy | PRODUCTION files in `config/government_revenue/` | Two policies on one identity, not two events | CODE + PRODUCTION |
| Dossiers / IDV / subaward / recipient graph | matching v1 schemas | Latest bounded read models + reviewed UEI→issuer path | `award_key`; `recipient_entity_id`; issuer `company_id`+ticker | ownership `event_effective_at` vs `record_known_at` | Graph overrides/conflicts/blocks; no fuzzy name | reviewed relation only | files present | Ticker is collection scope, not issuer attribution | CODE + PRODUCTION |
| `company_government_revenue.v1` (`latest.json`) | live payload (not under contracts/ as that name) | Company-scoped workbench | ticker / company | `as_of`, `known_at`, `generated_at` | overwrite | context | 2026-08-18 | Embeds workspace freshness | PRODUCTION VERIFIED |
| SAM opportunities | `government_opportunity.v1` | Latest visible SAM revision under PIT cutoff | `notice_id` + `revision_id` | `known_at`, `effective_at`, `posted_at` | current-state under 90-min SLA | context | **`opportunities.parquet` ABSENT** this checkout | Workspace opportunity.visible=0 | CODE VERIFIED; disk UNKNOWN |

Defense V3 D3 (“Temporal event v3 and Change Tape”) is **todo**. Do not treat the current event.v2 card as that tape.

---

## 4. BioCatalyst event / fact stores

Program `biocatalyst` (building). **No `WS-*` in `agentos/workstreams/`** (25 files listed). Production objects designed for R2 + `/var/lib/macro-biocatalyst/state/operational`. This checkout’s `data/biocatalyst/` is **fixtures only**.

| Object | Contract | Grain | Subject key | Clocks | Coverage | Correction | Authority |
|---|---|---|---|---|---|---|---|
| `source_page_receipt.v1` | contracts/biocatalyst | One sanitized CT.gov v2 page | `ctgov_receipt_…` | `response.received_at`, `source_dataset_timestamp_raw`, `transaction_from/to` | current fetch | put_if_absent | source receipt | CODE VERIFIED |
| `trial_source_snapshot.v1` | same | Canonical study JSON at one retrieve | `ctgov_snapshot_…`; `src:ctgov:NCT…:sha256:…` | `retrieved_at`, `first_seen_at`, source published/effective/last_update, `valid_from/to` | **`coverage_class=current_only`** | new snapshot; close prior | source | CODE VERIFIED |
| `trial_snapshot_observation.v1` | same | One fetch vs prior | `ctgov_observation_…` | `observed_interval.{after,at_or_before}`, `retrieved_at`, `first_seen_at` | current_only | immutable observation | observation | CODE VERIFIED |
| `trial_history_source_snapshot.v1` + `trial_history_exact_diff.v1` | history.py | One Record History version / adjacent pair | `ctgov_history_snapshot_…`; `src:ctgov-history:NCT:version:N:sha256:…` | `source_submitted_at`, `retrieved_at` | **`record_history_complete`**, `current_only=false` | new version objects | source history | CODE VERIFIED |
| `trial_registry_change_fact.v1` | same | One semantic field-family fact | `trial_registry_change_…` + NCT + `diff_ref` | `transaction_from/to` | `source_fact=true`; does **not** assert protocol change or materiality | derived from exact diff | `classification=source_fact`; decision_authority false | CODE VERIFIED |
| FDA application / submission / regulatory event | drugs_at_fda + regulatory.py | One ZIP-release row | `fda_application_…` / `fda_submission_…` / `fda_submission_action_…` | `source_evidence.observed_at`; **`event_date_source_text` const null** | **`source_release_snapshot_only`** | new ZIP = new release id (archive SHA) | dark-by-default | CODE VERIFIED |
| `biocatalyst_operating_packet.v1` | packet_producer.py | Facts-only carrier | `biocatalyst_operating_packet:{24hex}` | `generated_at`, `knowledge_cutoff`; facts carry `observed_at` | **`coverage.class=current_only`** even if history exists elsewhere | packet is not the history store | max A1_EXPLAIN; identity/regulatory families declared unavailable | CODE VERIFIED |
| `biocatalyst_outcome_record.v1` / operational envelope | operational_store.py | One outcome / one store record | `outcome_id`; `subject_ref=nct:NCT…`; `bcop_{32hex}` | **`effective_at ≤ known_at ≤ observed_at`**; `recorded_at` | forward ledger | corrigible kinds append + `revision_of` / `corrects_record_id`; immutable kinds cannot be corrected | operational | CODE VERIFIED. Production root not in repo — UNKNOWN on this checkout |
| Theme collector `data/clinicaltrials/trials.parquet` | `collectors/clinicaltrials.py` — **not** `engine/biocatalyst` | Phase-3 start/halt | NCT + status | first-post / last-update | informal | overwrite-ish collector | **Same CT.gov v2 API, different product plane** | CODE + PRODUCTION |
| Repo-root `scraped_*.json` | **not** claimed by BioCatalyst | BioPharmCatalyst.com scrape rows | ticker / drug / date | scrape `catalyst_date` only | none | **Not a BioCatalyst contract object** | PRODUCTION files exist; not in official chain |

---

## 5. TIL / Theme Graph evidence planes

Two programs. Do not collapse.

| Object | Owner | Contract | Grain | Subject key | Clocks | Correction | Authority | PIT | Notes |
|---|---|---|---|---|---|---|---|---|---|
| `data/theme_graph/evidence.parquet` | `gmi-theme-graph` / `WS:GMI-THEME-GRAPH` | `contracts/theme_graph/evidence.v1.schema.json` | One dated receipt | `evidence_id` = `ev:`+sha1(kind\|source_ref\|published_at)[:16] | **required** `published_at`; optional `effective_at`; `computed_at` | Nothing superseded in place; contradictory receipts coexist | display; licensing_* are mint-time snapshots; live rights = `config/theme_sources.yml` | Append-only | PRODUCTION VERIFIED: **11** evidence rows on 2026-08-18 `_meta.json` | CODE + PRODUCTION |
| `data/theme_graph/edges.parquet` | same | `edges.v1` | One **belief** about one interval | `(edge_id, belief_time)`; `edge_id` = `<type>:<src>-><dst>@<valid_from>` | `valid_from`/`valid_to` (world); `evidence_time`; `belief_time`; `era` reconstruction\|observed | Later belief = new row; close by appending `valid_to` | display; all six authority booleans false | Bitemporal latest-belief view | 8292 latest-belief edges; no extra historical beliefs yet | CODE + PRODUCTION |
| `data/theme_graph/nodes.parquet` | same | `nodes.v1` | One node | `node_id` keep-first | `birth_date`/`retire_date`; `computed_at` | Identity break → new `node_id` | display | Full set retained; labels mint-time | 3878 nodes | CODE + PRODUCTION |
| capability / _meta / probation | same | capability.v1 + implicit | sidecar classification / run snapshot / proposal | node_id / whole-store / `prop:`+sha1 | `computed_at` / `created` | capability can upgrade **or** demote; _meta overwrite; probation keep-first | capability internal | mixed | Zero registered synapse consumers on all four theme-graph artifacts | CODE + PRODUCTION |
| `data/neuralweb/theme_state.json` | `thematic-intelligence` (TIL) | `neuralweb.theme_state.v1` (module const; no JSON Schema under `contracts/`) | One **current** block per canonical theme | `theme_id` from `config/theme_crosswalk.yml` | compose `as_of`; per-leg source asofs; stale if source asof >5d | **Overwrite snapshot** | `AUTHORITY_BLOCK` all promotion flags false | current-state only | Site byte-mirror. **No Theme Graph join in code** | CODE VERIFIED |
| TIL jsonl ledgers (phase history, thesis, placebo, falsifier evals) | TIL W0/W1/W6 | synapse-named | One row per (theme, as_of) or thesis version | theme_id / content-hash / claim_id | `as_of` | append-only; first-eval-wins on falsifiers | display / shadow | PIT of **composed state**, not graph receipts | First promotion-eligible read 2026-10-15 (synapse note) | CODE VERIFIED |
| `theme_clinical` / BioCatalyst `theme_rollup_pit` | `til-w10-clinical` / BioCatalyst | `theme_clinical.v1` + `biocatalyst_theme_rollup_pit.v1` | Theme × modality rollup | `theme_id` is clinical-modality vocabulary, **not** `theme:*` | `knowledge_cutoff` optional; `study_first_post_date` | overwrite rollup; exclude `superseded_by_later_knowable_version` | context; `fused_obs_z` fenced | current rollup | **No** `theme_graph` import in `engine/biocatalyst/` | CODE VERIFIED |

---

## 6. Transmission Intelligence

Program `policy-transmission-intelligence`. Synapse owner `transmission-intelligence` matches **one** artifact: `transmission-chains-state`. Implementation root: `engine/transmission_chains.py`. Display-only (`DNR:KILL-CAUSAL-DAG-ALPHA`).

| Object | Grain | Subject key | Clocks | Correction | Authority | PIT |
|---|---|---|---|---|---|---|
| `data/transmission/chain_state.json` (`transmission_chains.v1`) | Current state of every compiled chain | `chain` slug + `rev` | `asof`; `substrate.substrate_asof`; hop confirm `asof`; `built` wall clock | **Overwrite snapshot**. Same-asof eval idempotent | `display_only=True` | Current episode view. PRODUCTION: asof 2026-08-17 | CODE + PRODUCTION |
| `data/transmission/chain_episodes.jsonl` | One state transition | `(chain, rev, asof, transition)` keep-first | `asof` | append-only forward ledger; nightly sole advancer | display | PIT of **episode machine**, not of series | CODE VERIFIED |
| `data/transmission/latest.json` | Macro transmission current snapshot | whole-file | `asof` | overwrite | display | **Sibling owner** `macro-context-rail`, not `transmission-intelligence` | CODE VERIFIED |
| `data/china_policy_transmission/events.jsonl` + site snapshot | One policy event | `_hash` = sha256(ts\|source\|kind\|title)[:16] | `ts`; snapshot `asof`/`built` | append-only hash-dedup | `authority.tier=context_only` | Historical tape + overwrite snapshot | CODE VERIFIED. **Not in synapse.yml** |

A chain `failed`/`expired`/`arm_veto` is an **instrument verdict** (declared windows), never a market verdict. House law (AGENTS.md signal-state interpretation).

---

## 7. Neural Web evidence / contradiction / lineage

| Object | What it is | Grain | Clocks | Lineage | Authority | PIT |
|---|---|---|---|---|---|---|
| `neuralweb.evidence_clock.v1` | Display aggregator of **review clocks** | One rollup row per `clock_id` (EC-R1 forbids per-claim rows) | `due_at`; `generated_utc`; source `as_of` copied when present. **No** observed_at / known_at / effective_at | none | `display_only`; cannot promote/mutate | Latest snapshot. PRODUCTION: 2026-08-18, 309 rows | CODE + PRODUCTION + DOC |
| `engine/neuralweb/contradictions.py` | 9 hardcoded bus-pair detectors | One typed pair firing | `as_of` = most recent artifact date | none | `display_only`; severity `note`/`tension` only | Recomputed each build; no ledger | CODE VERIFIED. Docstring still says “seven pairs”; synapse notes still list a–f — **DRIFT** |
| `factor_contradictions.py` | Per-name `borrowed_strength` | `(date, ticker)` | `as_of` = standout board date | none | display; severity clamped `note` | Intended append-only jsonl. **File ABSENT** this checkout | CODE VERIFIED |
| Chat `_CONTRADICTION_DIRECTIVE` | Assistant-behavior eval | response-eval row | n/a | n/a | de-escalate only | **Not market evidence** | CODE + DOC |
| `confluence_graph.v1` | Typed graph over the bus | nodes/edges; `contradicts` / `confirms` | `produced_at` = **build** time | none | display | Closest “evidence DAG”; it is a display graph over artifacts, not a provenance DAG | CODE VERIFIED |
| Envelope | Five sibling keys on the artifact | whole artifact | `produced_at` = build time | `inputs_hash` is content identity, not parent | tier stamp | no parent/revision | CODE VERIFIED |
| Market Memory observations | Bounded PIT observations (SPY canary identity, OI, technical, breadth) | `mmidobs_` / receipt ids | Full set: `event_time`, `available_at`, `observed_at`, `effective_at`, `as_known_at` | outcome `revision_of` | context; identity store is **not** a security master | Strongest PIT packet in `engine/neuralweb/` | CODE VERIFIED |
| `earnings_context_reader` | PIT reader of context packets | one ticker packet | `known_at` vs `as_of` cutoff | `correction_status` flag, not a pointer | `context_only` | Best NW **evidence ID + known_at** packet — transcript-scoped | CODE VERIFIED |
| Governance jsonl | Append-only rulings | `event_id` = sha256[:16](type+target+ts) | `lapses_at` | none | governance | evidence_clock consumes lapses | CODE VERIFIED |

`config/synapse.yml` is a **catalog of artifacts**, not an evidence store. `config/dag.yml` is a **workflow-step inventory**, not an evidence DAG. `docs/MASTERMIND_SYSTEM_MAP.md` is a generated semantic map.

---

## 8. Synapse / DAG / System Map

| Object | Role for a Mesh | Not |
|---|---|---|
| `config/synapse.yml` (~643 artifacts) | Names producer, path, `asof_field`, `freshness_sla_hours`, tier, consumers | A fact store. Does not hold observations |
| `config/dag.yml` | Build order of producers | Subject identity or clocks |
| `docs/MASTERMIND_SYSTEM_MAP.md` / `docs/SIGNAL_BUS.md` | Generated views of programs + artifacts | Writable truth |
| `config/lobe_charters.yml` | Lobe fitness / charter | Evidence ownership |

Synapse `asof_field` is the house’s existing **clock-name registry**. A Mesh should reuse those names, not invent a parallel `observed_at` for every artifact.

---

## 9. QLedger / Evaluation stores

| Object | Grain | Subject key | Clocks | Correction | Authority | PIT |
|---|---|---|---|---|---|---|
| `data/qledger/claims.jsonl` | One directional/salience **claim** (prediction), not a world observation | `claim_id` = sha1(desk\|asof\|scope.key\|horizon_d\|direction\|salt)[:16]. Entity key is membership **ticker** | `asof`, `timestamp`, `check_by`. **No** known_at / source_available_at / effective_at | Append-only keep-FIRST. No `revision_of` | Display until gauntlet | PIT regime stamp at register (`vector_asof`). PRODUCTION: `run_status` 2026-08-18 `n_open=51694` | CODE + PRODUCTION |
| `data/qledger/grades.jsonl` | `(claim_id, horizon_d)` | joins claims | `graded_at`; fill/clock stamps | Append-only; legacy rows never rewritten | feeds track record | Two stamped discontinuities | CODE VERIFIED |
| `data/qledger/falsifier_evaluations.jsonl` | One row per claim_id (first eval wins) | claim_id | `as_of`, `asof_claim`, `check_by`, `evaluated_at` | Parallel artifact; **never** mutates claims | display / TIL honesty | Independent of `grades.hit` | CODE VERIFIED |
| Eval OS T1 registry / T4 output health | `(engine_id, artifact_id)` | `producer::owner_program` | injected `now`; watermark from `asof_field` | **commits nothing** | reports synapse authority | on-demand view | CODE VERIFIED |
| `docs/CLAIM_ACCOUNTABILITY.md` | Desk/family rollup | desk | Generated header 2026-07-06 | overwrite | display | **Stale vs live store** (9,069 vs 51,694) | PRODUCTION (stale doc) |

QLedger is a **forward-claim ledger**. It is not an observation mesh.

---

## 10. Source-health / freshness / correction infrastructure

There is **no** generic `source_health` packet (search bound: `source_health` hits are ad-hoc fields and specialized packets).

| Packet | Owner | What it measures | Clock honesty |
|---|---|---|---|
| Global Evidence Clock | neural-web | Review due / stale / blocked | Display aggregator of other clocks |
| `data/neuralweb/health.json` | neural-web | Lobe/artifact freshness vs synapse SLA | `_AS_OF_KEYS` fallback is estate-specific (T4: do not generalize) |
| Eval OS T4 `output_health.v1` | Eval OS | Reader vs producer vs self-health | The only generic **normalizer**; commits nothing |
| `capital_structure.ingestion_health/v1` | CS | One ingest/compile run | Compiler `as_of` is **generation time, not source freshness** |
| `fundamental_forensics.health.v1` | FF | Workbench / source clocks | Split clocks; gzip mtime 0 is not a clock |
| `scripts/freshness_sentinel.py` | ops | Live HTTP/disk dead-man | Outside git |
| `engine/provider_health.py` | ops | Vendor attempt log | Attempt history |
| Polygon / live-flow receipt | options | `source_available_at` + parquet sha | Receipt+parquet pair; mismatch → do not consume |
| Board contradictions | publish lane | Rendered-board invariants | Not freshness; not a thesis falsifier |
| Marketing `marketing_correction.v1` | marketing | Copy correction | **Not market evidence** |

---

## Identifier planes (do not collapse)

| Plane | Form | Used as | Bound |
|---|---|---|---|
| Earnings / FIF issuer | `cik:0000320193` / 10-digit cik | Durable issuer in those products | CODE VERIFIED |
| Earnings security | `xnas:AAPL` | Listed security | CODE VERIFIED |
| Ticker | `AAPL`, `MMC` | Alias / membership key / qledger `scope.key` | Never durable |
| Data OS (designed) | `ISS:US-XNYS-MMC`, `SEC:US-XNYS-MMC`, `US-XNYS-MMC` | Inception listing spine | Designed; CN already uses `<CC>-<MIC>-<CODE>`. **Not** qledger keys | CODE VERIFIED (`lib/dataos/identity.py`) |
| CS issuer | `issuer:{cik}` | Share-count observations | CODE VERIFIED |
| Theme node | `theme:*` / `ltheme:finviz:…` / `ltheme:ths:…` | Graph identity | CODE VERIFIED |
| NCT | `NCT########` | Trial identity | CODE VERIFIED |
| GovRev event | `govws-` / `govopp-` / `govawd-` | Display event | CODE VERIFIED |
| Award | `generated_unique_award_id` / `award_key` | Official award | CODE VERIFIED |
| QLedger claim | 16-hex `claim_id` | Forward claim | CODE VERIFIED |
| Market Memory | `mmsecurity_` / `mmidobs_` | SPY canary only; **not** a security master | CODE VERIFIED |
| `engine/canon.py` | RMA/EMA/net-liquidity | **Formula** canon, not identifier canon | CODE VERIFIED |
| `WS:STOCK-IDENTITY` | behavioral fingerprints | Prophet routing research | **Not** ticker/CIK/FIGI canon | CODE VERIFIED |
| Dated `cik_map` | ticker ↔ CIK snapshot | SEC registrant **reference** | `listing_sec_identity_binding_eligible=false` | CODE VERIFIED |

---

## What this census is not

- Not a license to mint a sixth observation store.
- Not a ranking of which plane is “more true.”
- Not production verification of R2 / VPS / CT.gov / USAspending live endpoints (not called this session).
