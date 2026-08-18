# A0 — Minimal Evidence Mesh recommendation

**Commission:** MASTERMIND GROK-A0, special question 8  
**Verdict:** build a **typed pointer join layer**. Do not build a universal observation store, a second identity registry, a second contradiction engine, or a payload warehouse.

Wrong costs: a new truth store that silently forks FIF / Theme Graph / BioCatalyst / GovRev / earnings.  
Checking costs: this census.

---

## 1. Why this is the smallest lawful thing

The estate already has observation-grade planes:

| Plane | What it already is |
|---|---|
| Theme Graph `evidence.parquet` + bitemporal edges | Dated receipts; contradictions coexist |
| FIF raw ledger + packet | Bitemporal filing facts + revision hops |
| Earnings `company_event` + workspace generations | Issuer-keyed event + span receipts |
| BioCatalyst snapshots / observations / history facts | Current-only vs complete history, typed |
| GovRev events + action versions + correction manifests | Dual-clock award/opportunity facts |
| Market Memory | Full `as_known_at` / `available_at` / `observed_at` contract (narrow subjects) |
| QLedger | Forward claims — **adjacent**, not a fact plane |

Synapse already catalogs artifact paths, producers, `asof_field` names, and SLAs. Evidence clock already aggregates **review** clocks. Confluence already draws a display DAG over artifacts.

A sixth store that copies cells would violate the commission (“do not create a new truth store when an owner already exists”), `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` (if it restamped ids), and several `do_not_redo` lines on FIF / earnings / Theme Graph / GovRev.

---

## 2. What the Mesh is

One append-only **observation log of pointers**. Each row says: *this owner-native object is about this typed subject at this named clock.*

It does not store the fact. It does not score. It does not pick a winner. It does not advance any source ledger.

Schema sketch (names are recommendations, not a minted contract):

```
mesh_ref.v1
  mesh_ref_id            # content-hash of the pointer fields, no run clock
  owner_store            # closed enum, see §4
  native_id              # unchanged owner id
  schema                 # contract id the owner already publishes
  subject_key_type       # closed enum, see §5
  subject_key            # native string in that type’s grammar
  secondary_keys[]       # optional typed aliases already minted by the owner
  clock_class            # world_valid | source_published | knowable | observed | system_recorded | belief_or_build | review_due
  clock_field            # native field name (do not rename)
  clock_value
  clock_grain            # date | datetime
  native_digest          # sha256 of the owner object if it has one; else null
  coverage_class         # copy owner’s coverage_class when present (current_only, record_history_complete, source_release_snapshot_only, …)
  authority_class        # copy owner’s declared authority; Mesh may only lower, never raise
  join_recorded_at       # THIS log’s write clock (not a fact clock)
```

That is the construction `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` already prescribed: an explicit observation log binding artifact id + digest + observation clock — not a restamped artifact.

---

## 3. What the Mesh is not

- Not a new `evidence.parquet` that re-hosts Theme Graph, FIF cells, or trial facts.
- Not a security master. Data OS `ISS:`/`SEC:` and earnings `cik:` both exist; Mesh v0 **points at both types** and does not unify them.
- Not a contradiction graph. See `A0_EXISTING_CONTRADICTION_CAPABILITIES.md`.
- Not a freshness SoT. Evidence clock + T4 + owner health packets stay owners.
- Not a synapse replacement. Synapse remains the artifact catalog; Mesh rows point at objects, not at YAML keys (unless the object *is* the artifact).
- Not a promotion path. Default `authority_class` is the owner’s; Mesh cannot grant rank/size/gate.
- Not a home for `scraped_*.json`, marketing corrections, chat contra_verdicts, or Nasdaq calendar rows — unless a later decision types them as a downgraded sibling.

---

## 4. Closed `owner_store` enum (v0)

Only stores that already have a native id + a documented clock. Additive later.

| owner_store | native_id | default subject_key_type | default clock_class |
|---|---|---|---|
| `theme_graph.evidence` | `evidence_id` | `theme_node` or `source_ref` | `source_published` |
| `theme_graph.edge_belief` | `(edge_id, belief_time)` | `theme_node` (src/dst) | `world_valid` + `belief_or_build` |
| `fif.raw_occurrence` | `occurrence_id` | `cik` | `source_published` + `system_recorded` |
| `fif.packet` | `packet_id` | `cik` | `belief_or_build` (derived) |
| `earnings.company_event` | `evt_cik…` | `cik` | `knowable` (`source_available_at`) |
| `earnings.workspace_generation` | `generation_id` + `event_id` | `cik` | `belief_or_build` |
| `earnings.context_packet` | `context_id` | `ticker_store_key` (honest: listing-keyed) | `knowable` (`known_at`) |
| `govrev.event.v2` | `event_id` | `award_key` or `notice_id` | `knowable` + `world_valid` |
| `govrev.candidate` | `candidate_id` via `source_event` | `cik` / ticker **as declared by reviewed graph only** | `knowable` |
| `biocatalyst.ctgov_current` | `src:ctgov:NCT:sha256:` | `nct` | `observed` |
| `biocatalyst.ctgov_history` | `src:ctgov-history:NCT:version:N:sha256:` | `nct` | `source_published` |
| `biocatalyst.change_fact` | `change_fact_id` | `nct` | `system_recorded` |
| `biocatalyst.outcome` | `outcome_id` | `nct` | `world_valid` + `knowable` + `observed` |
| `txi.episode` | `{slug}@r{rev}:{asof}` | `chain_id` | `belief_or_build` |
| `qledger.claim` | `claim_id` | `ticker_store_key` or `basket` | `belief_or_build` (`asof`) |
| `market_memory.observation` | `mmidobs_` / receipt_id | `mm_subject` | `knowable` |

Derived heads (TIL theme_state, TXI chain_state, workspace marker, GovRev queue, evidence clock) are **not** v0 owner_stores. Point at the immutable object underneath.

---

## 5. Closed `subject_key_type` enum (v0)

Do not add a “universal entity id.”

| Type | Grammar | Owner of the grammar |
|---|---|---|
| `cik` | `cik:0000320193` or 10-digit | earnings identity / FIF entity_id |
| `award_key` | GovRev award_key / `generated_unique_award_id` | GovRev |
| `notice_id` | SAM `notice_id` + `revision_id` | GovRev |
| `nct` | `NCT########` | BioCatalyst |
| `theme_node` | `theme:*` / `ltheme:*` / company node_id | Theme Graph |
| `chain_id` | TXI slug + rev | Transmission |
| `ticker_store_key` | membership ticker (`MMC` not `MRSH`) | membership + Data OS store_key |
| `claim_id` | qledger 16-hex | QLedger |
| `accession` | `##########-##-######` | SEC / FF / earnings release |
| `mm_subject` | Market Memory subject_id | Market Memory (canary) |

**v0 join rules:**

- Same `subject_key_type` + same `subject_key` ⇒ joinable.
- `cik` ↔ `award_key` only through GovRev **reviewed** recipient resolution (`relation_semantic=reviewed`).
- `cik` ↔ `ticker_store_key` only through earnings `company_identity.v1` PIT alias **or** a dated symbol-directory + cik_map pair that does **not** claim listing-SEC binding.
- `theme_node` (`theme:*`) ↔ clinical `theme_id` is **not** a v0 join.
- `nct` ↔ `ticker_store_key` is **not** a v0 join (BioCatalyst forbids sponsor inference).
- Data OS `ISS:`/`SEC:` is recorded as a **future** type when that master is populated; do not mint Mesh rows in that grammar until the stored master is the authority.

---

## 6. Answers to the eight special questions

1. **Which stores already behave like immutable observations?**  
   See `A0_PROVENANCE_AND_CORRECTION_MATRIX.md` §3 first list. Theme Graph evidence, FIF occurrences, FF content-addressed objects, earnings generations/documents, GovRev events, BioCatalyst receipts/observations/facts, CS observations, qledger claims, TXI episodes, Market Memory rows.

2. **Which preserve corrections vs overwrite current state?**  
   Preserve: anything with `revision_of` / new generation / new event_id / coexist-rows / config quarantine. Overwrite: TIL/TXI/CN heads, FF private state, calendar parquet, latest markers, evidence clock, track_record.

3. **Where can the same real-world event be observed by multiple lobes?**  
   Filings, earnings prints, USAspending awards, NCTs, policy shocks, theme membership. Map: `A0_DUPLICATION_RISK_MAP.md` §7.

4. **What shared upstreams create false independence?**  
   SEC archive, Company Facts, Terminal transcripts, CT.gov v2, USAspending, SAM, Drugs@FDA, Nasdaq calendar, price/membership stores, theme crosswalk. Map: `A0_DUPLICATION_RISK_MAP.md` §1.

5. **Which existing contradiction system can be reused?**  
   Theme Graph coexistence (receipts), FIF/earnings/GovRev/BioCatalyst lineage (revisions), NW W4 (display signal pairs only), qledger falsifier (forward claims), evidence clock (review attention), TXI falsifiers (instrument windows). Not a new engine. Details: `A0_EXISTING_CONTRADICTION_CAPABILITIES.md`.

6. **Which entity/security/company identifiers are canonical?**  
   **None universally.** Canonical *inside a plane*: `cik:` (earnings/FIF), `evt_cik…` (earnings event), NCT, award_key, theme `node_id`, Data OS inception listing (designed, not yet qledger’s key), membership ticker (qledger/boards). Ticker is never durable. `engine/canon.py` is formula canon. `WS:STOCK-IDENTITY` is behavioral.

7. **Which stores are current-snapshot-only and cannot lawfully support replay?**  
   TIL theme_state and most composed JSON heads; TXI chain_state (use episodes); FF private state; Nasdaq calendar; CI/workspace **markers**; context `latest.json`; GovRev workspace/queue/dossiers heads; FDA release snapshot; CT.gov current-only plane; evidence clock / health / track_record. Matrix: `A0_TEMPORAL_SEMANTICS_MATRIX.md` §4.

8. **Smallest possible Evidence Mesh joining layer?**  
   This file, §2–§5.

---

## 7. First consumers (if built)

v0 is useful only if someone reads pointers without needing a payload copy:

1. Neural Web / Brain: “what owner-native objects exist for this `cik` / `nct` / `award_key` today,” then **call the owner reader**.
2. Earnings E2 / dossier: already has `event_id` aliases; Mesh should not replace `event_id_adapter`.
3. Evidence clock: may grow an adapter that counts Mesh pointer freshness — rollup only (EC-R1).

No Prophet / rank / size / gate consumer in v0.

---

## 8. Boring baseline (the one that must lose a named test)

The boring baseline is **do not build a Mesh at all**: keep writing owner-local joins (`event_id_adapter`, GovRev `source_event`, BioCatalyst `src:ctgov:…`, Theme Graph `evidence_refs`).

That baseline fails one named requirement of this commission: *map the estate so a later Mesh extends existing truth*. The map is this packet. The Mesh itself is optional and must still lose to “call the owner reader” unless a consumer needs a **cross-store pointer index**.

**Flip condition:** a funded consumer that must list, in one query, native objects across ≥3 owner_stores for one `cik` or one `nct` without importing those engines. Until that consumer exists, **stop at this census**.

---

## 9. No-build / do-not-infer warnings

- Do not start FIF-2, BioCatalyst identity families, Defense D3 Change Tape, or Theme Graph TRANSMISSION wave under a Mesh ticket.
- Do not ingest `scraped_*.json` as BioCatalyst facts.
- Do not treat Company Facts as a PIT filing ledger.
- Do not bind `cik_map` to listing snapshots.
- Do not join NCT to ticker.
- Do not join clinical `theme_id` to `theme:*`.
- Do not copy payloads into `data/evidence_mesh/`.
- Do not put a run clock in `mesh_ref_id`.
- Do not let a Mesh row raise authority above its owner.
- Do not infer causality from two pointers sharing a subject_key (`DNR:KILL-CAUSAL-DAG-ALPHA`; house epistemics).
- Do not convert missing clocks to epoch / zero; leave UNKNOWN.
- Do not use LLM prose as a Mesh fact.
