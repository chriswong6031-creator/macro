# D0R Workstream C — Capability and authority ledger

Completed after unentitled A, P00032 lineage, and entitled `site_full` recapture 2026-08-17T04:41Z.  
`PROVEN_LIVE` requires a production observation this wave. Entitled cookie JSON and bearer `/api/government-revenue/*` 200 are now `PROVEN_LIVE`. Candidate Radar **UI** is not.

**Global authority at D0R (any new V3 capability, and the current GovRev fence):**

| Flag | Value |
|---|---|
| `can_display` | true for compact page + HEAD artifacts |
| `can_publish_context` | true for federation selectors (`reviewed_award_change_context`) — live Prophet/Neural Web *output* not re-proven this session |
| `can_generate_research_hypothesis` | false (no V3 hypothesis engine) |
| `can_shadow_score` | false (shadow module has no fused score by design; not live) |
| `can_rank` | **false** |
| `can_add_candidates` | **false** |
| `can_gate` | **false** |
| `can_size` | **false** |
| `can_set_entry` | **false** |
| `can_execute` | **false** |

Prophet remains pick/ranking authority. `#5424` defense20-v1 is still open and is **not** the live graph.

Legend for Current state: `PROVEN_LIVE` | `BUILT_NOT_PROVEN` | `PARTIAL` | `DARK_OR_DISCONNECTED` | `BROKEN` | `SPEC_ONLY` | `NOT_BUILT` | `BLOCKED_BY_DATA` | `BLOCKED_BY_EVIDENCE` | `BLOCKED_BY_IDENTITY` | `BLOCKED_BY_RIGHTS` | `REJECTED_BY_DESIGN`.

---

## Evidence and ingestion

| Capability | User/machine job | Current state | Owner | Producer | Runner | Artifact/API | Consumer | Source | Freshness | Identity dep | Production proof | Authority | Blocker | V3 target | Wave | Acceptance test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| USAspending award snapshots | retain award-level observations | `BUILT_NOT_PROVEN` (HEAD rows exist; entitled API 401) | GovRev engine | collectors → `award_snapshots.parquet` | `government-revenue-live.yml` | parquet + `/api/government-revenue/award/{key}` | workspace, dossiers | USAspending awards/detail | HEAD known_at 2026-08-13; live HTML still that cut | recipient query ticker | HEAD 4031 snapshot rows; live award HC101319C0006 matches | display/context | entitled read unproven | PIT award spine | D1/D3 | entitled GET award key 200 equals parquet |
| Action/transaction history | retain action versions | `PARTIAL` | GovRev | `award_action_versions.parquet` | same | parquet; compact event receipts | Change Tape | USAspending `/api/v2/transactions/` | P00032 first seen 2026-08-12; later receipts 08-13/14 have new sha | award_key | lineage closed for P00032 | display | collection truncated by safety cap | complete action spine | D3 | page count + sha match live USAspending |
| SAM opportunities | current notice tape | `SOURCE_UNAVAILABLE` / `BLOCKED_BY_DATA` | GovRev opportunities | `opportunity_intelligence` | live workflow | compact `opportunities=[]` | Opportunities tab | SAM.gov | `freshness.opportunities.status=unavailable` | n/a | live tab 0 + freshness unavailable | display | source not producing | live SAM + revisions | D1 | nonzero official notice with revision clock |
| Opportunity revisions | first-seen vs official amendment | `NOT_BUILT` as official SAM amendment archive | GovRev | limitations text only | n/a | workspace limitations | UI copy | SAM | n/a | n/a | limitation: “not an official complete SAM amendment archive” | display | no SAM rail | revision history | D3 | two versions of one notice |
| IDVs/orders | vehicle ↔ order graph | `BUILT_NOT_PROVEN` | GovRev | `idv_dossiers.json`, `idv_relationship_snapshots.parquet` | live + builder | site `idv-dossiers.json` (locked 401) | award IDV API | USAspending | HEAD files exist | award_key | git inventory; no entitled GET | display | rights + unproven live | IDV drilldown | D3 | entitled IDV relationship 200 |
| Subawards | subaward dossiers | `BUILT_NOT_PROVEN` | GovRev | `subaward_*` | live | site `subaward-dossiers.json` | subaward API | USAspending | HEAD files exist | award_key | git inventory; this golden award `subaward_count=0` | display | unproven live | subaward tape | D3 | entitled subaward 200 on a nonzero award |
| SBIR/STTR | progression payload | `DARK_OR_DISCONNECTED` | GovRev `sbir_progression.py` | tests only | not in `scripts/build_government_revenue.py` | no site artifact | tests | SBIR.gov (intended) | n/a | UEI | module + tests; no producer import from builder | display | not on DAG | theme/program input | D5+ | committed payload consumed by UI or federation |
| DoD budget | P-1/R-1 graph | `NOT_BUILT` in HEAD artifacts | `budget_program.py` | would write `budget_program_graph.json` | render.yml *expects* `budget-program.json` | **file absent on HEAD data/ and site/** | Budget tab, `/budget-programs` | comptroller.defense.gov | UI “verifying” then 0 | program keys | `git cat-file` miss; live tab 0 | display | `PROJECTION_MISSING` | budget graph | D1/D5 | committed graph + entitled 200 |
| Forecasts | SAM/agency forecasts | `NOT_BUILT` | V3 spec | n/a | n/a | n/a | n/a | n/a | n/a | n/a | none | none | not in substrate | forecast rail | D5+ | source record |
| Protests | GAO/COFC | `NOT_BUILT` | V3 spec | n/a | n/a | n/a | n/a | n/a | n/a | n/a | none | none | not in substrate | protest rail | D8+ | official docket id |
| Official contract announcements | DoD contracts | `NOT_BUILT` | V3 spec | n/a | n/a | n/a | n/a | n/a | n/a | n/a | none | none | not in substrate | announcement rail | D3+ | notice ↔ award join |
| Source receipts | immutable collection receipts | `PARTIAL` | GovRev | `collection_receipts.jsonl` | live | jsonl | event `evidence.receipts` | USAspending | P00032 receipt verified | run_id + sha | lineage | display | raw body not in git (sha only) | receipt store | D1 | sha re-fetch match |
| Correction history | correction/retraction flags | `PARTIAL` | award_events | action-version columns | live | parquet columns all null on P00032 | event `is_correction` | USAspending | n/a | action_id | columns exist; unused on this case | display | source fields null | correction lineage | D3 | a real correction with predecessor |
| Source health | SLA / aged status | `PARTIAL` | freshness.py | status JSON + UI | live | `candidate_projection_status.source_health=ok`; UI “Partial or stale coverage” | headline | derived | 4-day SLA vs 2026-08-13 cut captured 08-17 | n/a | dual: status ok vs UI partial | display | client ages clocks | honest aged states | D1 | UI state == computed freshness |

## Identity

| Capability | User/machine job | Current state | Owner | Producer | Runner | Artifact/API | Consumer | Source | Freshness | Identity dep | Production proof | Authority | Blocker | V3 target | Wave | Acceptance test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Recipient identity | name/UEI on award | `PROVEN_LIVE` (compact+official) | GovRev + graph | USAspending + graph | live | award + event | browser | USAspending | 2026-08-12 | UEI | IRIDIUM GOVERNMENT SERVICES LLC / S77SW52LCR57 | display | CAGE absent | Identity Atlas | D2 | UEI on row = official |
| UEI/CAGE | exact identifiers | `PARTIAL` | graph `identifiers` | reviewed manifest | # reviewed graph, not collectors | `recipient_entity_graph.json` | mapping | SAM/USAspending | graph known_at 2026-08-07 | UEI reviewed; CAGE absent | IRDM UEI reviewed | display | CAGE not in graph | UEI+CAGE+DUNS history | D2 | both ids on a case |
| Legal entity | canonical legal name | `BUILT_NOT_PROVEN` live dossier; **proven in graph for this case** | graph | reviewed | defense19-v1 | legal_entities | issuer path | SEC 10-K / Ex.21 | 2025-12-31 valid_from | entity_id | three IRDM legal entities | display | not shown as a named entity on compact row | Atlas | D2 | UI shows legal name |
| Subsidiaries | ownership edges | `BUILT_NOT_PROVEN` as UI; proven in graph | graph | Ex.21 | defense19-v1 | ownership_edges | issuer path | SEC | 2026-08-07 | parent/child | wholly_owned LLC | display | not a UI tree | Atlas | D2 | tree for IRDM |
| Issuer links | ticker on event | `PROVEN_LIVE` compact | graph + workspace | reviewed path | live | `listed_company_impacts` | Changes row | graph | 2026-08-07 | reviewed | IRDM on HC101319C0006 | display/context; not rank | GE/BWXT in company strip but not graph companies[] | exact reviewed only | D2 | no fuzzy ticker |
| Historical ownership | valid_from/to | `PARTIAL` | graph | reviewed | defense19-v1 | valid_from 2025-12-31, valid_to null | PIT | SEC | graph_effective_at 2026-08-07 | PIT | fields exist | display | no pre-2025 history | PIT ownership | D2 | a dated change |
| JVs | joint ventures | `NOT_BUILT` | Atlas | n/a | n/a | n/a | n/a | n/a | n/a | n/a | none | none | no JV model | JV edges | D2 | named JV case |
| Acquisitions/divestitures | corporate events | `NOT_BUILT` | Atlas | n/a | n/a | n/a | n/a | n/a | n/a | n/a | none | none | no event model | M&A PIT | D2 | dated edge |
| Program mapping | award → program | `BLOCKED_BY_IDENTITY` | V3 / D5 | `major_program` null on this award | n/a | n/a | n/a | USAspending program fields | n/a | program id | this case program absent | display | no program graph | golden programs | D5 | mapped program |
| Vehicle mapping | IDV/order | `BUILT_NOT_PROVEN` | idv_bridge | idv snapshots | live | idv artifacts | API | USAspending | HEAD | award_key | this case has no parent IDV | display | unproven live | vehicle map | D5 | IDV case |
| Supplier mapping | supplier graph | `NOT_BUILT` | V3 industrial | n/a | n/a | n/a | n/a | n/a | n/a | n/a | none | none | no supplier plane | industrial graph | D8+ | one supplier edge |

## Product

| Capability | User/machine job | Current state | Owner | Producer | Runner | Artifact/API | Consumer | Source | Freshness | Identity dep | Production proof | Authority | Blocker | V3 target | Wave | Acceptance test |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Candidate Radar | exact-linked research queue | `PARTIAL` — API `PROVEN_LIVE` 22; **UI locked** after site_full | candidates.py | `candidate_queue.json` | live + `build_government_revenue_candidates.py` | `/api/government-revenue/candidates` 200 `grcq1-d93ebaf6878402e3be09e490` | radar JS (bearer only) | workspace + graph | generated 2026-08-13 | exact reviewed path | bearer 200 total=22; overlay still membership | display; cannot add candidates | hydrate-once; does not reread cookie candidates.json | entitled radar UI | D1 | overlay gone; tab count=22 |
| Change Tape | governed award-change queue | `PROVEN_LIVE` entitled 500; compact teaser still 2 | workspace.py | workspace.json | live | compact 2 / full 500 | Changes tab | award_events | 2026-08-13 | reviewed optional | entitled list 500; P00032 + balance sibling | display | anonymous lock; entitled loading banner leftover | keep 500 honest | D1 | banner clears after hydrate |
| Award Tape | award/action tape | `PROVEN_LIVE` entitled 500 | same | same | same | same 500 | Award tab | same | same | same | live count 500 | display | same | entitled tape | D1 | same |
| Opportunities | SAM desk | `BLOCKED_BY_DATA` | opportunities.py | opportunity_intelligence | live | empty array | Opportunities tab | SAM | unavailable | n/a | live 0 + freshness unavailable | display | source | live SAM | D1 | official notice |
| Recompete Watch | derived expiry | `PARTIAL` | workspace recompete events | award end dates | live | compact 0; limitation says derived | Recompete tab | award POP | compact omission | ticker | live 0 under lock | display | lock + derivation-only | honest derived watch | D3 | derived row with source end date |
| Budget & Programs | P-1/R-1 | `BROKEN`/`PROJECTION_MISSING` | budget_program.py | missing artifact | render expects file | no HEAD file | Budget tab | DoD comptroller | loading | program key | live 0 + missing git object | display | artifact never committed | budget desk | D1 | file exists and UI rows |
| Companies | coverage strip + dossiers | `PARTIAL` | metrics + dossiers | latest.json companies | live | 21 companies in compact; dossiers.json locked | Companies tab | USAspending monthly | 2026-08-13 | ticker | 21 names live; link status unavailable | display | candidate API 401 for link state | entitled dossiers | D1 | chip state = mapping |
| Company dossiers | issuer file | `BUILT_NOT_PROVEN` | dossiers.py | `dossiers.json` | live | site dossiers 401 | dossier API / filmstrip click | awards+graph | HEAD | ticker | 401 this session | display | rights | entitled dossier | D1 | 200 dossier |
| Search | notice/agency/ticker filter | `PARTIAL` | page JS | client filter over compact rows | n/a | local | Changes | compact events | n/a | n/a | search box present; not exhaustively tested | display | only 2 rows | full-index search | D1 | filter a 500-row set |
| Filters | truth layer / agency / ticker | `PARTIAL` | page JS | facets | n/a | compact facets (agency facet is raw dict-as-id — degraded) | sidebar | workspace facets | n/a | n/a | All evidence 2 works | display | agency facet serialization bug | clean facets | D1 | agency dropdown shows DISA |
| Evidence drilldown | receipts drawer | `PARTIAL` | page JS | event.evidence | n/a | receipts in JSON | inspector | USAspending | 2026-08-12 | receipt_id | controls + official link live; drawer pixel not fully captured | display | MCP drop | entitled drawer | D1 | drawer lists sha + url |
| Saved state | briefcase views | `DARK_OR_DISCONNECTED` unentitled | briefcase JS | local; disabled until hydrate | n/a | Save/Delete disabled | briefcase | workspace | n/a | n/a | controls disabled | display | hydrate lock | entitled views | D1 | save/restore |
| Alerts | local inbox | `DARK_OR_DISCONNECTED` unentitled | briefcase | local | n/a | Enable local alert disabled | inbox 0 | n/a | n/a | n/a | disabled | display | lock | entitled local alerts | D1 | enable + fire |
| Exports | JSON/CSV | `DARK_OR_DISCONNECTED` unentitled | briefcase | client | n/a | Export disabled | n/a | workspace | n/a | n/a | disabled | display | lock | entitled export | D1 | file equals view |
| API | paid read-model | `PROVEN_LIVE` bearer 200 (cookie-only still 401) | `app/government_revenue.py` | files under `/opt/macro` | VPS FastAPI | latest/candidates/workspace/events/mapping-backlog | page JS | artifacts | 2026-08-13 cut | site_full | bearer 200; cookie 401 missing bearer | display fence in payloads | two auth planes | keep split documented | D1 | session attaches bearer; UI rehydrates |

## Financial transmission

All rows: current authority display/context only; `can_rank/size/gate/execute=false`. V3 target is research/shadow then Prophet evidence, never pick authority in D0R.

| Capability | Current state | Owner | Proof / blocker | Wave |
|---|---|---|---|---|
| Denominators | `PARTIAL` — `metrics.py` publishes TTM obligations / exposure sums on compact `market` (`mapped exposure $206.7B`) | GovRev metrics | headline live; not company-reported | D4 |
| Federal exposure | `PARTIAL` — bounded USAspending sample, not 10-K federal % | metrics | coverage 21 companies | D4 |
| Reported backlog | `NOT_BUILT` as issuer 10-K backlog | company-financials plane (do not duplicate) | none | D4 |
| Funded backlog | `PARTIAL` — `funded_backlog_observed` / `funded_capacity_observed` as ceiling−obligation residual over sample | metrics | `amount_semantics` forbids calling it GAAP | D4 |
| Revenue | `NOT_BUILT` as GAAP | existing financials plane | obligation ≠ revenue (this lineage) | D4 |
| Segment revenue | `NOT_BUILT` | financials/transcripts | none | D4 |
| Margin / FCF / working capital / guidance / estimate revision / valuation | `NOT_BUILT` in GovRev | existing estimate/price planes | do not mint duplicates | D4–D7 |
| Contract quality | `NOT_BUILT` | V3 | none | D6 |
| Backlog conversion | `NOT_BUILT` | V3 D4 | none | D4 |

## Industrial-base intelligence

All `NOT_BUILT` / `SPEC_ONLY` in this substrate: production capacity, facilities, bottlenecks, supplier graph, inventories/consumption, lead times, production-rate changes, supplier distress, qualification risk. Wave D8+ in V3 masterplan. Do not create a parallel store.

## Defense thematic intelligence

Missile defense, munitions, space, autonomy/UAS, shipbuilding, nuclear, C4ISR/EW, NATO/rearmament, FMS, fleet modernization, sustainment: **`SPEC_ONLY`**. No theme engine in GovRev. Existing Macro theme planes must be reused, not copied (`duplicate-plane` hazard). Wave D5/G in the D0R architecture handoff, not this continuation.

This golden case is satellite airtime (NAICS 517410), not a V3 theme roster member.

## Market and asymmetry

Event materiality band `high` on the compact impact is a **display heuristic**, not a residual. All of: expectations gap, price residualization, defense-theme residualization, event market response, dislocation, adverse-event overreaction, washout/turn, options anticipation, dark pool, flow, scenario distribution, expected residual return, uncertainty, Alpha Shadow Board — **`SPEC_ONLY` / `NOT_BUILT`**. `market_context.py` exists and is imported by `shadow_context.py` (tests); **not** imported by the GovRev builder. Do not create a duplicate options/flow store. Wave D6–D12. Authority: no rank/size.

## Neural Web and Prophet

| Capability | Current state | Owner | Producer | Consumer | Proof | Authority | Blocker | Wave |
|---|---|---|---|---|---|---|---|---|
| Current GovRev federation | `BUILT_NOT_PROVEN` live output | `federation.py` | `reviewed_award_change_context` | `engine/prophet_bridge.py`, `engine/neuralweb/mastermind_context.py` | import graph; no live Prophet card captured | `can_publish_context` only; cannot add candidates | unproven in UI | D1 |
| Neural Web procurement context | `BUILT_NOT_PROVEN` | mastermind_context | same selector | chat packet | code path | display | no chat capture | D1 |
| V3 defense neural-state | `SPEC_ONLY` | V3 masterplan | n/a | n/a | none | none | not designed this session | D9+ |
| Causal event packets | `PARTIAL` — `government_procurement_event.v2` is the packet | workspace | projector | UI | this lineage | display | entitled API unproven | D3 |
| Current Prophet annotation | `BUILT_NOT_PROVEN` / possibly inert | `prophet_annotation.py` via `annotate_plans_from_repo` | prophet_bridge post-selection | Prophet plans | wired; fail-open; comment claims radar empty — HEAD queue is 22 | cannot rank/add | live annotation not captured | D1 |
| Shadow contribution | `DARK_OR_DISCONNECTED` | `shadow_context.py` | tests only | tests | no builder/Prophet import of `build_shadow_context` | no fused score by design | not on runtime path | D6 |
| Independent-family research | `SPEC_ONLY` | V3 | n/a | n/a | none | none | D0R later workstreams | D0R-D/E |
| Forward outcome grading | `NOT_BUILT` | V3 | n/a | n/a | none | none | D17 | D17 |
| Promotion evidence | `REJECTED_BY_DESIGN` at D0R | Prophet | n/a | n/a | architecture | no promotion | D20 | D20 |

## Engine module wiring (exists ≠ live)

| Module | Runtime consumer | State |
|---|---|---|
| `amount_semantics.py` | tests + classification law | `BUILT_NOT_PROVEN` as UI copy; law holds on this case |
| `award_events.py` | payload/workspace | `PARTIAL` live via compact events |
| `budget_program.py` | missing artifact | `DARK_OR_DISCONNECTED` |
| `candidate_grader.py` / `candidates.py` | candidate builder | `BUILT_NOT_PROVEN` entitled |
| `dossiers.py` / `idv_*` / `subaward_dossiers.py` | builder + locked JSON | `BUILT_NOT_PROVEN` |
| `entity_resolution.py` | builder + graph load | `PARTIAL` (this lineage) |
| `federation.py` | Prophet + Neural Web | `BUILT_NOT_PROVEN` live |
| `freshness.py` | UI + federation gate | `PARTIAL` |
| `issuer_graph_expansion.py` | tests (`test_group_linked_outsiders`) | `DARK_OR_DISCONNECTED` |
| `market_context.py` | shadow tests | `DARK_OR_DISCONNECTED` |
| `metrics.py` | `build_payload` | `PARTIAL` (headline live) |
| `opportunities.py` | payload | `BLOCKED_BY_DATA` |
| `point_in_time.py` | engine | `BUILT_NOT_PROVEN` as product clock UI |
| `prophet_annotation.py` | prophet_bridge | `BUILT_NOT_PROVEN` |
| `sbir_progression.py` | tests | `DARK_OR_DISCONNECTED` |
| `shadow_context.py` | tests | `DARK_OR_DISCONNECTED` |
| `workspace.py` | builder + HTML | `PARTIAL` (compact live, full locked) |
