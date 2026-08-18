# A0 — Provenance and correction matrix

**Commission:** MASTERMIND GROK-A0  
**Standing law:** `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` — do not hash a per-run clock into the identity of an immutable content-addressed evidence object.

---

## 1. Provenance patterns already in the estate

| Pattern | Where | What a later reader can prove | Tag |
|---|---|---|---|
| Content-addressed bytes + pointer last | FF-1 SEC objects, filing packages, query snapshots, Terminal transcript bodies, narrative/story objects, event_workspace generations, CS CF snapshots | Exact bytes that were sealed; latest pointer is the only mutable object | CODE VERIFIED |
| Hash identity of a receipt | Theme Graph `evidence_id` = sha1(kind\|source_ref\|published_at); CN policy `_hash`; synapse `inputs_hash` | Same receipt observed twice is one row | CODE VERIFIED |
| Dual-clock occurrence | FIF raw ledger `occurrence_id` includes clocks + `revision_of` | Two vintages of the same economic fact are two occurrences | CODE VERIFIED |
| Event id that ignores revision | Earnings `evt_cik…_{period}_{type}` | Amendment does not fork the event | CODE VERIFIED |
| Event id that **includes** known_at | GovRev `govws-…` hashed from award+rail+state+**known_at** | A→B→A is three immutable events | CODE VERIFIED |
| Keep-FIRST append | QLedger claims/grades; Theme Graph nodes/evidence; probation; TXI episode transitions | Re-register is a no-op | CODE VERIFIED |
| SHA-256 of source body | Filings (`body_sha256`, accession members), transcripts (`content_sha256` / `source_sha256`), CF `sec-companyfacts:{cik}:{sha256}` | Shared upstream key across owners | CODE VERIFIED |
| Span receipts | Earnings transcript (segment+offsets); Exhibit 99.1 (char/byte); public wire UTF-8 | Replayable citation, or typed `address_only` / `typed_absence` | CODE VERIFIED |
| Collection receipt bound to event | GovRev `collection_receipts.jsonl`; BioCatalyst page/history receipts | Event fail-closed without a receipt | CODE VERIFIED |
| Envelope stamp | NW `produced_by` / `produced_at` / `inputs_hash` / `tier` | Builder identity, not source identity | CODE VERIFIED |

---

## 2. Correction / revision matrix

| Store | Mechanism | Identity on correction | Old row | New row | Tag |
|---|---|---|---|---|---|
| FIF raw ledger | `revision_of` + `FactEventType` (amendment / comparative_recast / restatement / source_correction / withdrawn) | New `occurrence_id` | stays | append | CODE VERIFIED |
| FIF packet | `revisions[]` hop list with `lineage_occurrence_ids` | Packet id is content-hash of the query answer | derived view rebuilt | new packet | CODE VERIFIED |
| Company Facts → ledger | `revision_of` **only** with explicit revision evidence | CF has no native amendment lineage | n/a | manufacturing `revision_of` on CF rows is a FIF landmine | CODE VERIFIED |
| FF snapshots / packages / attested v2 | New content-addressed object; pointer last | New `ffqs_` / `ffqsv2_` | immutable | overlay, never in-place upgrade | CODE VERIFIED |
| Earnings `company_event` | state → `corrected`; same `event_id` | **stable** | transition recorded | new document + workspace generation | CODE VERIFIED |
| Earnings `SourceDocument` | `revision` 1..n + `supersedes_document_id` | new document_id | stays | append | CODE VERIFIED |
| Earnings release | 8-K/A = new **filing**, same **event** `(cik, report_date)` | event stable; filing new | listed original→current | new accession | CODE VERIFIED |
| Event workspace | new `generation_id`; marker advances | `event_id` stable | old generation immutable | new object | CODE VERIFIED |
| Transcript intake | `(ticker, YYYYQn)@body_sha256` | new hash re-queues | body immutable | new body | CODE VERIFIED |
| Narrative / context | `supersedes_source_sha256`; `correction_status` current\|corrected | latest packet | old objects stay | marker last | CODE VERIFIED |
| Chronicle call events | same `source_record_id`; healthy correction replaces hash | stable | healthy row replaced; degraded cannot clobber healthy | replace-by-id | CODE VERIFIED |
| Theme Graph evidence | extra row; nothing nets | new `evidence_id` if kind/source/date differ | stays | append | CODE VERIFIED |
| Theme Graph edges | new `(edge_id, belief_time)` | edge_id stable across beliefs | open row stays forever | append `valid_to` or new belief | CODE VERIFIED |
| Theme Graph capability | new `(node_id, computed_at)` | node_id stable | stays | can upgrade **or** demote | CODE VERIFIED |
| TIL snapshots | overwrite | theme_id | previous bytes gone from head | current | CODE VERIFIED |
| TIL jsonl | append / hash-dedup | (theme, as_of) or content-hash | stays | append | CODE VERIFIED |
| TXI chain_state | overwrite current | chain+rev | previous head gone | current | CODE VERIFIED |
| TXI episodes | append; YAML `rev` bump on edit | `(chain, rev, asof, transition)` | stays | append | CODE VERIFIED |
| GovRev events | new event_id (includes known_at); `action_revised` / `action_corrected` / `action_retracted` | new event | stays | append | CODE VERIFIED |
| GovRev workspace | exact-id collapse; contradictory same-id **dropped** | bundle rebuilt | not a fact store | projection | CODE VERIFIED |
| GovRev candidate ledger | append-only | `candidate_id` | stays | append | CODE VERIFIED |
| GovRev issuance corrections | quarantine exact `issued_row_sha256` | candidate + source identity | ledger line **not** deleted | config manifest | CODE + PRODUCTION |
| GovRev historical suppressions | `do_not_backfill` tombstone | source identity **without** `observation_id` | not re-emitted | config manifest | CODE + PRODUCTION |
| Recipient graph | `overrides` / `conflicts` / `blocks`; interval-valid edges | `record_key` | past `known_at` not silently remapped | new edge/override | CODE VERIFIED |
| BioCatalyst raw objects | `put_if_absent` / If-None-Match | content-addressed | no overwrite API | new object | CODE VERIFIED |
| BioCatalyst current-only | close prior `transaction_to` / `valid_to` | new snapshot/observation | prior closed | append | CODE VERIFIED |
| BioCatalyst change tape | `correction_lineage` names earlier **recorded value** | row ids | stays | `correction_assessed=false` (assess_correction forbidden) | CODE VERIFIED |
| BioCatalyst operational | immutable kinds cannot be corrected; corrigible kinds append | `bcop_…`; `revision_of` == `corrects_record_id` | predecessor never rewritten | append | CODE VERIFIED |
| BioCatalyst outcome | new record via `revision_of` | new `outcome_id` | stays | append | CODE VERIFIED |
| FDA release | new ZIP = new `release_id` (archive SHA) | new release | old release stays if retained | no historical correction tape | CODE VERIFIED |
| QLedger claims | keep-FIRST; no `revision_of` | `claim_id` | first row wins forever | re-register returns existing | CODE VERIFIED |
| QLedger falsifiers | parallel eval file | `claim_id` | claims never mutated | first eval wins | CODE VERIFIED |
| QLedger grades | append; new clock/fill = new stamp on **new** rows | `(claim_id, horizon)` + clock basis | legacy rows never rewritten | append | CODE VERIFIED |
| Market Memory outcomes | `revision_of` + `revision_number` | new `mmoutcome_*` | stays | append | CODE VERIFIED |
| Data OS identity | append alias row; never re-mint | `ISS:`/`SEC:`/`US-XNYS-MMC` | inception id stable | alias | CODE VERIFIED |
| Ticker vendor aliases | current map edit | `store_key` stays | historical files stay on store key | fetch under vendor | CODE VERIFIED |
| Marketing correction | `marketing_correction.v1` | marketing `claim_id` (≠ qledger) | editorial | **not market evidence** | CODE VERIFIED |
| Evidence clock reviews | append snooze line | `clock_id` | source ledgers untouched | ack only | CODE + DOC |
| NW contradictions | recompute | no id | previous build gone | display annotation | CODE VERIFIED |

---

## 3. Immutable observations vs current-state heads

### Behave like immutable observations (join these)

- FIF raw-ledger occurrences
- FF-1 content-addressed SEC bytes, filing packages, query snapshots, attested overlays
- Theme Graph evidence rows and edge **belief rows**
- Earnings event transitions, source documents/spans, workspace **generations**, Terminal transcript bodies, narrative/story/wire objects
- GovRev events, action versions, collection receipts, candidate ledger lines, correction/suppression manifests
- BioCatalyst receipts, snapshots, observations, history versions, change facts, operational records
- CS share-count observations + CF snapshots
- QLedger claims / grades / falsifier evals (keep-FIRST)
- TXI `chain_episodes.jsonl`
- Market Memory content-addressed identity/outcome rows
- Symbol-directory **dated** parquets + completion receipts
- Polygon receipt+parquet pairs

### Current-state heads (do not treat as the Mesh fact)

- TIL `theme_state.json` and most TIL/TXI/CN site JSON
- TXI `chain_state.json`
- FF private workbench state
- Nasdaq earnings calendar parquet
- CI v1 latest / workspace marker / context `latest.json`
- GovRev workspace / queue / dossiers / `latest.json`
- Evidence clock JSON, NW health.json, track_record, accountability md
- Eval OS T1/T4 (never committed)
- `_meta.json` beside Theme Graph

A Mesh that copies a head will drift the next nightly. A Mesh that points at a generation/object id will not.

---

## 4. Provenance ID grammar (native — reuse, do not restamp)

| Kind | Native id | Hash inputs include run clock? |
|---|---|---|
| Theme evidence | `ev:`+sha1(kind\|source_ref\|published_at)[:16] | **No** | CODE VERIFIED |
| FIF packet | `fip_`+24 hex of content minus id/hash/`built_at` | `built_at` excluded — lawful | CODE VERIFIED |
| FIF occurrence | hash including clocks + `revision_of` | clocks are **source/system**, not a poll stamp | CODE VERIFIED |
| Earnings event | `evt_cik…` | **No** (ignores call date, hash, revision) | CODE VERIFIED |
| Workspace generation | content-addressed `generation_id` | builder digest, not a poll stamp | CODE VERIFIED |
| GovRev event | hash includes `known_at` | **Yes, knowledge time** — deliberate so A→B→A is three facts | CODE VERIFIED |
| CT.gov current | `src:ctgov:NCT:sha256:` | content hash | CODE VERIFIED |
| CT.gov history | `src:ctgov-history:NCT:version:N:sha256:` | content + version | CODE VERIFIED |
| QLedger claim | sha1(desk\|asof\|scope\|horizon\|direction\|salt) | **No** run clock | CODE VERIFIED |
| Data OS | inception listing key | **Forbidden** by `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` | CODE VERIFIED |
| NW governance | sha256(type+target+ts)[:16] | includes ts — this is an event log, not a content artifact | CODE VERIFIED |

GovRev’s inclusion of `known_at` in `event_id` is a **knowledge-time identity**, not a run-clock identity. It is lawful because the fact being identified is “what we could know at T,” not “the award bytes.” Do not copy that pattern onto content-addressed filing packages.

---

## 5. What “correction” is not

- Re-running a builder and advancing `generated_at` (`DNR` + CS/FF health traps).
- Overwriting a latest pointer and calling the old generation gone — the generation must remain.
- Re-keying qledger claims after a ticker rename (retired-symbol disclosures exist specifically to forbid this).
- Binding a later CIK map onto an earlier listing snapshot.
- Theme Graph “superseding” a contradictory evidence row in place (contract: coexist).
- BioCatalyst `assess_correction` on the change tape (forbidden; `correction_assessed=false`).
- Treating marketing `correction_id` as a market-tape correction.

---

## 6. Smallest provenance record a Mesh may add

If a joining layer needs its own row, the lawful minimum is an **observation log** (the construction `DNR:LAW-RUN-CLOCK-IN-CONTENT-IDENTITY` already prescribes):

```
mesh_ref_id          # not a new fact id
owner_store          # e.g. theme_graph.evidence, fif.raw_ledger, govrev.event.v2
native_id            # unchanged
schema               # contract id
subject_key_type     # cik | nct | award_key | theme_node | claim_id | …
subject_key
clock_class          # from A0_TEMPORAL_SEMANTICS_MATRIX §6
clock_field          # native name
clock_value
observed_digest      # sha256 of the native object, if any
join_as_of           # when THIS mesh row was written (log clock, not fact clock)
```

That row is a **pointer**. It must not copy payload cells, scores, or prose.
