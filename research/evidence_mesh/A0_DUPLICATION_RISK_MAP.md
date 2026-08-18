# A0 — Duplication risk map

**Commission:** MASTERMIND GROK-A0  
**Rule:** multiple lawful observations of one real-world event are not a bug. A Mesh that “dedupes” them into one payload creates false independence or destroys a clock.

---

## 1. Shared upstreams that create false independence

If two lobes read the same vendor bytes and emit two artifacts, they are **not** independent evidence.

| Upstream | Lawful consumers already in-repo | False-independence trap |
|---|---|---|
| SEC Submissions + archive + iXBRL | FF-1 exact bytes, filing package, attested-history seed, earnings 8-K collector, Exhibit 99.1 binder | Counting “FF says 10-K” and “earnings 8-K collector says 8-K” as two sources for the same accession |
| SEC Company Facts JSON | FF `companyfacts_ledger`, FIF packet **witness hash only**, CS share-count / snapshots | Treating CS observation_id and FIF occurrence_id as independent facts about the same CF entry. Join on `sec-companyfacts:{cik}:{sha256}` / body digest |
| Terminal `mastermind.tx/v1` transcripts | intake, fact_pack/claim_graph, public wire, context packet, CI sources, event_workspace, BioCatalyst span_read | Treating Wire, CI, workspace, and BioCatalyst bundle as four transcript sources. They are four **projections** of one body |
| ClinicalTrials.gov v2 | `engine/biocatalyst` current-only plane **and** `collectors/clinicaltrials.py` theme parquet | NCT + ticker from the theme collector is **not** a BioCatalyst identity (packet forbids sponsor/ticker inference) |
| ClinicalTrials.gov Record History (`/api/int/…`) | BioCatalyst history plane only | Collapsing `ctgov_snapshot_*` with `ctgov_history_snapshot_*` |
| USAspending.gov | GovRev award/action/IDV/subaward **and** theme `data/usaspending/obligations.parquet` | Ticker-monthly theme series ≠ UEI/award graph. Same vendor, different identity |
| SAM.gov | GovRev opportunities **and** theme_activity presolicitation | Title/date fuzzy match is not `notice_id`+`revision_id` |
| Drugs@FDA ZIP | BioCatalyst FDA plane (dark) **and** `collectors/openfda.py` / `data/fda/shortages.parquet` | “Approval” narrative across three FDA-adjacent stores |
| Nasdaq unofficial calendar | `data/earnings/earnings.parquet` | Joining calendar `next_date` to SEC `report_date` or workspace event_id |
| Price / membership stores | QLedger grades, TXI hops, Theme Graph co-movement kinds, boards | Shared tape is not independent confirmation of a thesis |
| `config/theme_crosswalk.yml` | TIL + Theme Graph | Same `theme_id` string, different grain (composed legs vs membership graph). **No code join** |
| BioPharmCatalyst.com scrape (`scraped_*.json`) | **not** in `engine/biocatalyst` / `collectors/biocatalyst` | Must not be typed as a BioCatalyst fact |

---

## 2. Same real-world event, multiple lawful objects

### A. One 10-K / 10-Q accession

| Object | Native key | Owner |
|---|---|---|
| FF-1 exact bytes | SHA-256 of SEC bytes | FF |
| Filing package inventory | `ffpkg_` + cik+accession | FF |
| Raw-ledger occurrences | `occurrence_id` | FIF kernel |
| Query snapshot / attested v2 | `ffqs_` / `ffqsv2_` | Calcbench |
| Private workbench state | company map | FF product |
| FIF packet cell | `accession` + `source_occurrence_ids` | FIF (derived) |
| CS share-count observation | `observation_id` / `issuer:{cik}` | Capital Structure |

**Join:** `(cik, accession)` + `body_sha256`. Never ticker+date.

### B. One Company Facts snapshot

| Object | Native key |
|---|---|
| FF companyfacts_ledger | `cffledger_` + occurrence |
| FIF receipts.companyfacts_witness_sha256 | witness only |
| CS `sec-companyfacts:{cik}:{sha256}` | snapshot |
| CS share-count observation | `companyfacts-receipt:cs:` / bridge |

**Join:** payload SHA-256. Not occurrence_id schemes.

### C. One issuer-quarter earnings print (AAPL FY2026 Q3 is the golden case)

| Object | Native key |
|---|---|
| Canonical event | `evt_cik0000320193_2026q3_results` |
| CI v1 | `cie_98e318c37ec1a2a1f83c45e1` |
| Narrative / intake | `AAPL/2026Q3` |
| Public wire | `aapl-2026q3-call-record` |
| 8-K accession (workspace constant) | `0000320193-26-000018` |
| Terminal body | `AAPL/2026Q3` + body sha |
| Nasdaq calendar | ticker `AAPL` |

`event_id_adapter` already records aliases. v1 CI still listing-keys (GOOG/GOOGL fork). **Do not mint a fifth id.**

Transcript vs Exhibit 99.1 span receipts share grammar and **must not** replay against each other.

### D. One USAspending award

| Object | Native key |
|---|---|
| Snapshot event | `govawd-` / `record_id=award:{award_key}` |
| N action events / versions | action id + version |
| Dossiers award + actions | `award_key` |
| IDV child / subaward prime | PIID family |
| Candidate | `source_event.event_id` + `source_content_id` |
| `latest.json` company card | ticker scope |
| Theme obligations parquet | ticker × month |

**Join:** `generated_unique_award_id` / `award_key`. Event: (`source_rail`, `content_sha256`, `known_at`).  
**Unsafe:** ticker, recipient name, PIID alone, summing snapshot δ + action $.

Workspace 2026-08-18: 665 award_change after exact-id dedupe; snapshot rail 44 / action rail 621. That is **intentional dual-rail observation**.

### E. One NCT

| Object | Native key | Coverage |
|---|---|---|
| Page receipt → current snapshot → observation → `trial_snapshot` | `src:ctgov:NCT:sha256:` | current_only |
| History snapshot → exact diff → change fact → tape | `src:ctgov-history:NCT:version:N:sha256:` | record_history_complete |
| Operating packet fact | same current src: | packet is current_only |
| Theme `data/clinicaltrials/trials.parquet` | NCT + status | informal |
| BioCatalyst theme_rollup_pit | NCT + clinical `theme_id` | PIT optional |
| TIL `theme_clinical` | clinical `theme_id` | **not** `theme:*` |

**Unsafe:** NCT + ticker; collapsing current vs history namespaces.

### F. One FDA application / submission

Application snapshot + submission observation + regulatory event + (future) packet regulatory family. Join: `application_number` + submission number + `release_id`. Sponsor-name text is not a key. `event_date_source_text` is null.

### G. One canonical theme

| Object | Grain |
|---|---|
| Theme Graph node `theme:*` | vocabulary |
| Theme Graph `EXPRESSES` / `MEMBER_OF` edges | dated membership/expression |
| TIL `theme_state` | current composed legs |
| TIL thesis / pathways / asymmetry | current / versioned composition |
| Local themes `ltheme:finviz:*` / `ltheme:ths:*` | source-local; not canonical |
| Clinical `theme_id` | modality vocabulary |

No derived company→theme edge in Theme Graph (refused). Composing membership with expression is the **consumer’s** join.

### H. One transmission chain

`chain_state.json` (current) + `chain_episodes.jsonl` (transitions) + `latest.json` (macro-context-rail sibling) + China `policy_transmission.json` (different owner). Not one object.

---

## 3. Name collisions (same word, different world)

| Name | World A | World B | Join? |
|---|---|---|---|
| `claim_id` | QLedger 16-hex | Marketing ClaimPassport | **No** |
| `contradiction` | NW 9-pair detector | Chat eval `contra_verdict` | **No** |
| `dt_contra_state` | DannyTrades chip | not a contradiction ledger | **No** |
| China `contradictions_count` | CN-SYS compose | not W4 | **No** |
| `evidence_clock` | Global NW aggregator | QLedger family write-once start files | **No** |
| `health.json` | NW lobe health | CS ingestion health | **No** |
| `canon` | `engine/canon.py` formulas | imagined identifier canon | **No** |
| `event_id` | earnings `evt_cik…` | GovRev `govws-…` | **No** (type prefix already distinguishes) |
| `observation_id` | BioCatalyst `ctgov_observation_…` | GovRev candidate `gro1-…` (rotates) | **No**; GovRev durable join is `source_event` |
| `theme_id` | crosswalk `theme:*` | clinical modality slug | **No** |

---

## 4. Site mirrors (byte twins, not siblings)

These are projections, not second sources:

- `data/neuralweb/theme_state.json` ↔ `site/neuralwebdata/theme_state.json`
- TIL thesis / pathways / asymmetry site twins
- TXI site subset **lags one nightly** (synapse `lag_note`)
- CI public wire HTML vs private record

A Mesh that counts a data/ file and its site/ copy as two observations is wrong.

---

## 5. Dual-class / rename / ticker traps

| Trap | Who already encoded the refusal |
|---|---|
| GOOG/GOOGL as two issuers | Earnings freeze; `company_identity.v1` |
| Ticker as durable event key | Earnings `evt_cik…`; CI v1 still listing-keys (live contradiction recorded, not silently preferred) |
| MMC→MRSH re-key of historical files | `lib/dataos/identity.py`, `lib/ticker_aliases.py`, qledger retired-symbol disclosures |
| Present mapping applied to past events | Earnings alias `valid_from`/`valid_to`; Data OS time-scoped aliases (designed) |
| Listing snapshot bound to CIK map | `listing_sec_identity_binding_eligible=false` |

A Mesh that joins on bare ticker will re-introduce every one of these.

---

## 6. What must not be collapsed

1. Current-only CT.gov vs Record History.
2. GovRev snapshot rail vs action rail.
3. FIF raw occurrence vs CS share-count observation vs CF snapshot.
4. Earnings canonical event vs CI v1 vs calendar parquet.
5. Theme Graph evidence vs TIL composed state.
6. TXI chain_state vs `transmission/latest.json` vs China policy unifier.
7. QLedger claim vs marketing claim vs earnings `event_claim.v1`.
8. NW display contradiction vs qledger falsifier vs board contradiction vs GovRev issuance correction.
9. Repo-root BioPharmCatalyst scrapes vs BioCatalyst contracts.

---

## 7. Multi-lobe observation (special question 3)

Yes, already:

| Real-world event | Lobes / planes that can see it |
|---|---|
| SEC filing | FF source plane, FIF kernel, CS, earnings 8-K/release, Theme Graph `kind=filing` (when minted) |
| Earnings call | Earnings OS (event/workspace/wire/claims), Terminal archive, BioCatalyst span_read, Chronicle scores, Nasdaq calendar |
| USAspending award | GovRev snapshot + action + dossiers + candidates + Prophet annotation + NW ticker context + theme obligations |
| NCT change | BioCatalyst current-only + history + operating packet + theme clinical collector + TIL W10 |
| Policy shock | policy-shock ledgers, TXI chains, China policy unifier, White House desk, TIL (conceptual consume) |
| Theme membership | Theme Graph edges, TIL state (via baskets/radar, not the graph), Group Reads participation (not this census’s owner) |

A Mesh should **record the join**, not pick a winner.
