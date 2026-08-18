# A0 — Temporal semantics matrix

**Commission:** MASTERMIND GROK-A0  
**Rule:** never rename a foreign clock to `observed_at` just because the word is familiar. The same English word already means three different things in this repo.

Every cell is CODE VERIFIED against the named contract or module unless tagged otherwise.

---

## 1. The clocks that actually exist

| Clock name (as written) | Meaning in its home | Typical field | Must not be read as |
|---|---|---|---|
| World / valid time | When the underlying fact was true | `valid_from`/`valid_to`, `effective_at`, `action_date`, fiscal `period.end`, `report_date` | When we learned it |
| Source publication / acceptance | When the source published or SEC accepted | `published_at`, `accepted_at`, `source_event_time`, `acceptance_datetime`, `source_submitted_at`, `source_last_update_posted_at` | When we retrieved it |
| First knowable / available | When this system could lawfully have known | `source_available_at`, `known_at`, `first_seen_at`, `available_at`, `knowledge_cutoff` | When the world changed |
| Observation / retrieve | When this run looked | `observed_at`, `retrieved_at`, `response.received_at` | Source publication |
| System recorded / ingested | When our ledger wrote the row | `recorded_at`, `system_recorded_time`, `materialized_at`, `transaction_from` | Source event |
| Belief / compose | When this system came to believe a composed view | `belief_time`, TIL `as_of`, envelope `produced_at`, `built_at`, `generated_at`, `computed_at` | Observation of the world |
| Review / maturity | When a claim or clock is due | `check_by`, `due_at` | Evidence time |
| Reconstruction flag | This date is a convention or a backfill | Theme Graph `era=reconstruction`, `date_provenance=seed_constant` | An observation |

---

## 2. Matrix by estate

| Estate | World / valid | Source published / accepted | Knowable / available | Observed / retrieved | System recorded | Belief / build | Honesty flags |
|---|---|---|---|---|---|---|---|
| **FIF packet** | Period `start`/`end` | `source_event_time` / query `source_event_cutoff` | (cutoff is the knowable bound) | n/a | `system_recorded_time` / `system_recorded_cutoff` | `built_at` | Policies `as_reported` / `latest_known_as_of` / `latest_restated`. Mode never bypasses cutoffs |
| **FIF raw ledger** | `FactContext` period | `accepted_at` (`source_event_at`) | optional `mapping_available_at` | n/a | required `recorded_at` | `computed_at` / `published_at` | CF `accepted_at is None` ⇒ unavailable for source-event replay |
| **FF-1 / filing package** | n/a | `sec_accepted_at`, `filed_on` | per-member `retrieved_at` | poll `*_retrieved_at` | `recorded_at` **must not default to poll_started_at** | `assembled_at` | `generated_at` on composed FF is EDGAR clock, not builder |
| **Company Facts (FF + CS)** | `period_end` / fy/fp | Submissions join `accepted_at` | `source_retrieved_at` | capture | `recorded_at` = max of several | snapshot pointer | CF endpoint is a **current snapshot**. No implicit amendment lineage |
| **Earnings `company_event`** | fiscal period | `source_available_at` | same field is the knowable bound | `observed_at` (must be ≥ available) | processor version on transition | workspace `generated_at` | Transition with `observed_at < source_available_at` is **refused** |
| **Event workspace** | `calendar_end` | `lifecycle.source_available_at` | same | `lifecycle.observed_at` | generation id | `generated_at` | `generated_at today` ≠ latest event (`DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`) |
| **Earnings context packet** | event date | source `known_at` | manifest `knowledge_cutoff` | n/a | wire derivative | `generated_at` | Latest selected packet only |
| **8-K dates / release bind** | `report_date` | `acceptance_datetime` (SEC) | n/a | collector fetch | n/a | n/a | `JOIN_DATE_TOLERANCE_DAYS = 0`. Never join on filing_date±N |
| **Nasdaq calendar parquet** | `next_date` | n/a | n/a | n/a | `as_of` sweep stamp | n/a | Unofficial. Mixed as_of on partial sweep |
| **GovRev award event** | `effective_at` / `action_date` | n/a | `known_at` / `first_seen_at` | receipt `retrieved_at` | `generated_at` | workspace `as_of` (date, end-of-UTC-day) | Fail-closed if dual clock missing. Do **not** coalesce `base_obligation_date` as effective |
| **GovRev late discovery** | effective | n/a | known_at | n/a | n/a | n/a | `known_at − effective_at > 45d` → late-discovery flag |
| **GovRev SAM opportunity** | `effective_at` / `posted_at` | posted | `known_at` | `observation_horizon_at` | n/a | n/a | Current-state only if observed inside 90-min SLA |
| **BioCatalyst current-only** | `source_effective_at` / valid interval | `source_published_at` / `source_last_update_posted_at` | `first_seen_at` | `retrieved_at` + `observed_interval` | `transaction_from`/`to` | packet `generated_at` / `knowledge_cutoff` | `coverage_class=current_only`. Interval-censored (“changed after X and at-or-before Y”) |
| **BioCatalyst Record History** | n/a | `source_submitted_at` (source time) | n/a | `retrieved_at` | `transaction_*` | n/a | `coverage_class=record_history_complete`. Do not collapse with current-only ids |
| **BioCatalyst outcome** | `effective_at` | n/a | `known_at` | `observed_at` | `recorded_at` | n/a | Invariant **`effective_at ≤ known_at ≤ observed_at`** |
| **FDA Drugs@FDA** | **none native** (`event_date_source_text` const null) | n/a | n/a | `source_evidence.observed_at` | release archive SHA | n/a | `source_release_snapshot_only` |
| **Theme Graph evidence** | optional `effective_at` | **required** `published_at` | **no column** | n/a | n/a | `computed_at` | Undatable receipt is not evidence (contract refuses) |
| **Theme Graph edges** | `valid_from`/`valid_to` | `evidence_time` | **no column** | n/a | n/a | `belief_time` + `era` | `seed_constant` is a **convention**. Reconstruction era is never promotion evidence (G0.2) |
| **TIL theme_state** | none | source asofs | stale if source asof >5 calendar days | n/a | n/a | compose `as_of` = today; `generated_at` | Overwrite snapshot |
| **TXI chain_state** | hop windows in YAML | receipts’ series windows | `substrate.substrate_asof` | n/a | n/a | episode `asof`; `built` | Instrument windows, not market time |
| **TXI episodes jsonl** | n/a | n/a | n/a | n/a | n/a | `asof` | Append-only transition tape |
| **QLedger claim** | n/a | n/a | n/a | n/a | `timestamp` (registration) | `asof` (claim date); `check_by` (maturity) | `asof` is **not** known_at. Event/snapshot/corrupted `timestamp_quality` not gradeable |
| **Market Memory** | `event_time` / `effective_at` | n/a | `available_at` / `as_known_at` cutoff | `observed_at` | n/a | n/a | TemporalContractError if observed/available follow cutoff |
| **Evidence clock** | n/a | n/a | n/a | n/a | n/a | `generated_utc`; row `due_at` | Review attention, not fact time |
| **Synapse registry** | n/a | n/a | n/a | n/a | n/a | declares `asof_field` name only | Catalog of clock **names**, not values |
| **NW envelope** | n/a | n/a | n/a | n/a | n/a | `produced_at` = **build** time | Must not be treated as data as-of |
| **CS ingestion health** | `latest_source_filing_date` | `latest_source_retrieved_at` | n/a | n/a | `generated_at` | n/a | Compiler as_of is generation time |
| **Symbol directory snapshot** | listing that day | n/a | n/a | receipt `observation_date` | `collector_{started,completed}_at` | n/a | Prospective only; no inferred historical continuity |
| **Polygon / live-flow** | bar time | n/a | **`source_available_at`** | n/a | receipt write | n/a | Vendor delay is first-class |

---

## 3. Dual-clock / bitemporal stores (replay-capable)

These can support a lawful as-known-at read **if** the reader uses both axes:

| Store | Valid / source axis | Transaction / knowledge axis | Replay rule |
|---|---|---|---|
| FIF raw ledger + packet | `accepted_at` / `source_event_cutoff` | `recorded_at` / `system_recorded_cutoff` | Both cutoffs required |
| Theme Graph edges | `valid_from`/`valid_to` + `evidence_time` | `belief_time` + `era` | PIT membership at D = valid interval ∩ `belief_time <= D`. Latest-belief view is a different question |
| Earnings event transitions | `source_available_at` | `observed_at` | Refuse observed-before-available |
| GovRev events | `effective_at` | `known_at` / `first_seen_at` | Fail-closed if either missing |
| BioCatalyst current-only | source published/effective + valid interval | `retrieved_at` / `first_seen_at` / `transaction_*` | Interval-censored; `current_only` |
| BioCatalyst history | `source_submitted_at` + version N | `retrieved_at` / `transaction_*` | Complete version chain when validated |
| BioCatalyst outcomes | `effective_at` | `known_at` ≤ `observed_at` | Ordered triple |
| Market Memory | `event_time` / `effective_at` | `available_at` / `as_known_at` / `observed_at` | Cutoff contract |
| CS share-count observation | `period_end` + `accepted_at` | `source_retrieved_at` / `system_available_at` | Immutable observation + current pointer |

---

## 4. Snapshot-only / overwrite stores (cannot lawfully support replay from the head)

A git history of the file is not a PIT API.

| Store | Why replay from the head is unlawful |
|---|---|
| TIL `theme_state.json` (and pathways/asymmetry) | Overwrite current composition |
| TXI `chain_state.json` | Current episode view; use `chain_episodes.jsonl` for transitions |
| `data/transmission/latest.json` | Overwrite macro snapshot |
| FF private `state.json.gz` | Product current-state |
| Nasdaq `data/earnings/earnings.parquet` | Overwrite / mixed as_of |
| CI v1 latest teaser / workspace **marker** | Pointer last; generations are the PIT |
| Earnings context `latest.json` | Latest selected packet only |
| GovRev workspace / candidate **queue** / dossiers / `latest.json` | Latest projections over immutable events |
| FDA Drugs@FDA release | `source_release_snapshot_only`; no event date |
| CT.gov v2 plane | `current_only`; no complete history |
| QLedger `run_status.json` / `track_record.json` / accountability md | Derived views |
| Evidence clock JSON / NW health.json | Aggregators |
| Envelope `produced_at` | Build time |
| Capability.parquet current view | Latest `computed_at` per node (history retained, but it is a measurement) |

---

## 5. Words that collide

| Word | Homes | Collision |
|---|---|---|
| `observed_at` | Earnings transitions; BioCatalyst outcomes; FDA `source_evidence`; Market Memory; symbol-directory receipt | Earnings: “we saw the transition.” BioCatalyst outcome: latest of the triple. FDA: ZIP observed. MM: sampled after receipt boundary. **Do not unify.** |
| `as_of` | TIL compose date; TXI episode date; GovRev workspace date; QLedger claim date; evidence clock row | Four of five are **belief/build** dates. QLedger `asof` is the claim’s event/disclosure date. |
| `known_at` | Earnings context; GovRev; BioCatalyst outcomes; Market Memory | Closest shared “knowable” word. Still not interchangeable: GovRev is collector first-seen; earnings is source packet; MM is a cutoff contract. |
| `source_available_at` | Earnings events; live-flow receipts; MM | Earnings = transition firewall. Live-flow = vendor availability. |
| `effective_at` | Theme Graph evidence; GovRev; BioCatalyst outcomes; MM | Theme Graph: when reality lagged publication. GovRev: action_date. Outcome: when the outcome applied. |
| `generated_at` / `built_at` / `produced_at` / `computed_at` | Almost every snapshot | Builder clocks. Never source freshness (FF health and CS ingestion health already encode this trap). |
| `asof_field` (synapse) | Catalog | Name of a field, not a value. |

---

## 6. Lawful Mesh clock map (do not normalize)

A joining layer may **point at** a clock and name its class. It may not cast every clock into one column.

Recommended Mesh clock classes (labels only):

1. `world_valid`
2. `source_published`
3. `knowable`
4. `observed`
5. `system_recorded`
6. `belief_or_build`
7. `review_due`

Each `mesh_ref` carries `{clock_class, field_name, value, timezone_or_date_grain}`. Date-only vs timestamp is load-bearing (GovRev workspace `as_of` is a date; candidate `known_at` is a timestamp).

---

## 7. PIT risks (standing)

- Reconstruction / `seed_constant` dates treated as observations (Theme Graph G0.2).
- `generated_at today` treated as “latest event current” (earnings Wire vs CI).
- Company Facts current snapshot treated as as-of-poll (FIF landmine).
- CT.gov current-only interval treated as a point event.
- FDA release snapshot treated as a dated regulatory event (`event_date_source_text` is null).
- QLedger `asof` treated as `known_at`.
- Envelope `produced_at` treated as data as-of.
- Binding dated `cik_map` to dated listings (`listing_sec_identity_binding_eligible=false`).
- Present-day ticker applied to historical claims (Data OS / earnings identity both forbid this).
