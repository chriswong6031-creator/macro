# D0R Workstream B — Golden award-change lineage

**Case:** USAspending funding-only action `P00032` on PIID `HC101319C0006`  
**Browser row:** “New obligation observed — HC101319C0006” / IRDM  
**Governed event:** `govws-a6c70850a9cbdce9fa3e7f3b`  
**Why this case (not the easiest):** official action identity, reviewed issuer path, visible in the current compact product, nontrivial incremental obligation, and a 92-day gap between `action_date` and first observation. A May funding action discovered in August is not an August catalyst.

HEAD workspace also contains a second IRDM event on the same award (`govws-70d45adde3342d5eca8f8014`, `reported_obligation_balance_changed`). That sibling is **not** in the compact two-row teaser. This lineage follows the row the browser actually showed.

## 1. Chain (no unexplained hop)

```
official USAspending transaction
  id CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0
        ↓
raw retained source evidence
  GET https://api.usaspending.gov/api/v2/transactions/
  run usaspending-3be22546a4a9a6b9a46a7469
        ↓
receipt / immutable source identity
  usaspending:usaspending-3be22546a4a9a6b9a46a7469:actions:1d52f66cfa31a196:2a07ba19681a3c9d
  response_sha256 2a07ba19681a3c9d07f69b3316850b4646db48a8075d2ea8375755e112d02bab
        ↓
award/action version
  data/government_revenue/award_action_versions.parquet
  action_id = source_action_id = CONT_TX_…_P00032_…_0
  event_state_sha256 997bc21615ab6b9418cd107a587340a5bb3ca67862a4fc4df8430854f0df92ac
  event_eligible true
        ↓
normalized canonical procurement event
  government_procurement_event.v2
  event_id govws-a6c70850a9cbdce9fa3e7f3b
  kind award_change / change.type obligation
        ↓
first-observed / known-at
  known_at = first_seen_at = last_seen_at = 2026-08-12T23:50:04.442107+00:00
        ↓
recipient identity
  IRIDIUM GOVERNMENT SERVICES LLC
  UEI S77SW52LCR57
        ↓
legal-entity / ownership graph (defense19-v1)
  identifier:irdm:s77sw52lcr57
  → legal:irdm:iridium-government-services-llc
  → wholly_owned (1.0) legal:irdm:iridium-communications-inc
  → issuer_legal_entity central:IRDM
        ↓
public issuer
  IRDM / Iridium Communications
        ↓
Government Revenue workspace/projection
  bundle grw2-dd9d7af893a7f3c773909351
  compact HTML #gov-data events[0] AND HEAD workspace.json events (500)
        ↓
API / read model
  unentitled: compact embed only; /api/government-revenue/event/{id} 401
        ↓
browser list row
  Changes tab, Official USAspending change, Reviewed issuer link, IRDM
        ↓
browser detail / evidence
  revision diff + official source ↗ CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-
```

A reviewer can start from the compact row and walk backward: PIID on the title → `award_change.action_id` in `#gov-data` → USAspending `/api/v2/transactions/` result with the same id → receipt id on the event → parquet action version → reviewed UEI edge → IRDM.

## 2. Identifiers

| Field | Value |
|---|---|
| source | USAspending.gov |
| source rail | `usaspending_award_action` |
| award ID (generated unique) | `CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-` |
| PIID | `HC101319C0006` |
| action ID | `CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0` |
| modification number | `P00032` |
| USAspending award numeric id | `306425727` |
| event ID | `govws-a6c70850a9cbdce9fa3e7f3b` |
| record ID | `award:generated:CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-` |
| recipient name | IRIDIUM GOVERNMENT SERVICES LLC |
| UEI | `S77SW52LCR57` |
| CAGE | **absent** |
| legal entity | `legal:irdm:iridium-government-services-llc` |
| subsidiary relation | `wholly_owned` of `legal:irdm:iridium-communications-inc` |
| public parent | `central:IRDM` / Iridium Communications Inc. |
| ticker | IRDM |
| program | **absent** as a named DoD program; NAICS 517410 SATELLITE TELECOMMUNICATIONS; PSC D399; description AIRTIME SERVICES; `major_program` null |
| awarding agency | Department of Defense / DISA (97AK) — present on official award and award_snapshots; **empty `agency: {}` on the compact event** |
| funding agency | Department of Defense / Department of the Air Force (5700) |
| vehicle / IDV | none (`parent_award` null; type D DEFINITIVE CONTRACT) |
| graph ID | `recipient-graph:reviewed:2026-08-08:defense19-v1` |
| graph evidence IDs | `evidence:irdm-usaspending-s77sw52lcr57`; `evidence:irdm-sec-ex21`; `evidence:irdm-sec-10k` |
| solicitation | `HC101318R0008` (award-level, not shown on the compact change row) |

## 3. Clocks (absent means absent)

| Clock | Value | Notes |
|---|---|---|
| `source_effective_at` | `2026-05-12` (date only) | USAspending `action_date`; compact event stores `2026-05-12T00:00:00+00:00` — **date, not a proven timestamp** |
| `source_published_at` | **absent** | award `last_modified_date=2026-05-12` is a date, not a publication timestamp |
| `first_observed_at` / `known_at` | `2026-08-12T23:50:04.442107+00:00` | first time this projector saw P00032 (actions page grew 32 → 33) |
| `retrieved_at` | `2026-08-12T23:50:04.442107+00:00` | receipt `observed_at` / event receipt `retrieved_at` |
| `normalized_at` | **absent** as a named field | nearest: action version row written with that known_at |
| `generated_at` | `2026-08-13T09:24:42.811885+00:00` | workspace / latest.json assembly |
| `published_at` | **absent** | |
| `browser_capture_at` | `2026-08-17T01:54:09.346Z` | Cursor CDP; UI said “4d ago” relative to known_at |
| `as_of` | `2026-08-13` | **not** known_at |

Do not treat `as_of` as `known_at`. Do not treat 2026-05-12T00:00:00Z as an observed instant — the source only gave a date.

Later collection receipts (2026-08-13T07:06:54Z and 2026-08-14T00:15:20Z) re-fetched the same award’s transactions with a **different** `response_sha256` (`a4bbab62…`). The event the browser shows is pinned to the 2026-08-12 receipt `2a07ba19681a3c9d…`. The live HTML `Last-Modified` is 2026-08-14 but `#gov-data` clocks remain 2026-08-13.

## 4. Correction / novelty semantics

| Question | Finding |
|---|---|
| Event class | **modification / funding-only action**, not first issue of the award |
| USAspending `action_type` | `C` = FUNDING ONLY ACTION |
| Predecessor on the award | `P00031` same description/amount on 2026-03-11; award itself signed 2019-09-13 |
| Predecessor in this projector | **no `before` values** on changed_fields — first *visible version of this action* in the lobe, not first modification of the contract |
| `is_correction` | `false` (event); action-version correction columns all **null** |
| `is_late_discovery` | **true** |
| Late-discovery meaning | effective 2026-05-12, first observed 2026-08-12 (~92 days). **Not an August catalyst.** |
| Changed fields (after only) | `federal_action_obligation=18416666.66`; `action_date=2026-05-12`; `action_type=C`; `description=YEAR 7 INCREMENTAL FUNDING` |
| Signed changes | compact event does not carry a separate signed-delta object; the obligation figure is the action’s own `federal_action_obligation` |
| Supersession / cancellation / deobligation | no |
| Genuinely new to the market at `known_at` | **unknown / not claimed.** USAspending had the action dated May 12; this system first ingested it August 12. Public FPDS/USAspending lag is not measured here. |

Award-detail snapshots in `award_event_snapshots.parquet` for this PIID are a **different, older cut** (`last_modified_date=2026-03-11`, `total_obligation=701666666.65`, `event_eligible=false`, `known_at=2026-08-07`). The Change Tape row is the **action** observation, not that award-detail snapshot. Live USAspending award total obligation is now `720083333.31`, matching the later `award_snapshots.parquet` row.

## 5. Economic semantics (what the number is / is not)

The browser primary amount is **`$18,416,666.66` `federal_action_obligation`**.

| It is | It is not |
|---|---|
| A **transaction delta** / incremental **obligation** on modification P00032 | GAAP revenue |
| Year-7 incremental **funding** on a definitive contract | Award ceiling, potential ceiling, or IDV ceiling |
| One funded action inside a contract whose **cumulative** obligation is `$720,083,333.31` | The cumulative award total |
| Distinct from `base_exercised_options` `$738,500,000` (funded capacity / current award amount) | Funded backlog (`ceiling − obligation` residual elsewhere in metrics) |
| Distinct from outlay (award `total_outlay` null/0 in snapshots) | Cash received |
| Display/context only (`can_rank/size/gate=false`) | A Prophet pick, size, or gate |

`engine/government_revenue/amount_semantics.py` classifies `federal_action_obligation` as `transaction_delta`. Adding this $18.4M to the $720.1M cumulative would double-count. The compact UI title “New obligation observed” is obligation language, not revenue language — that part is honest. The empty `agency: {}` on the event is a projection gap, not an economic claim.

## 6. Graph path (reviewed)

Graph `recipient-graph:reviewed:2026-08-08:defense19-v1` (19 companies; compact company strip has 21 names including GE and BWXT, which are **not** in this graph’s `companies` list).

For this award:

1. USAspending recipient UEI `S77SW52LCR57` matches `identifier:irdm:s77sw52lcr57` (`sam_uei`, reviewed).
2. Identifier binds `legal:irdm:iridium-government-services-llc` (reviewed; evidence `evidence:irdm-sec-ex21` + `evidence:irdm-usaspending-s77sw52lcr57`).
3. Ownership edge `ownership:irdm:iridium-government-services-llc`: child LLC, parent `legal:irdm:iridium-communications-inc`, `wholly_owned`, economic_share 1.0, reviewed.
4. Issuer edge `issuer-identity:irdm:iridium-communications-inc`: parent_company_id `central:IRDM`, reviewed, evidence `evidence:irdm-sec-10k` (SEC 10-K `irdm-20251231.htm`).

Confidence on the compact impact is `medium` with `relation_semantic=reviewed` and stance `watch_dont_chase`. That is an issuer-link claim, not a revenue-attribution claim.

Note: graph evidence `evidence:irdm-usaspending-s77sw52lcr57` points at a **different** award (`CONT_AWD_0005_9700_N0017809D3007_9700`) used to bind the UEI, not at HC101319C0006. Identity is reviewed; this specific award is not the graph’s exemplar receipt.

## 7. Browser comparison

| Check | Result |
|---|---|
| Same event | Yes — PIID, action P00032, event_id in compact JSON, selected Changes row |
| Correct issuer | IRDM / Iridium Communications; “Reviewed issuer link” |
| Correct amount / change semantics | Diff shows `federal_action_obligation → 18416666.66`; title “New obligation observed”; not labeled revenue |
| Truthful timestamps | UI “4d ago” tracks `known_at` 2026-08-12 vs capture 2026-08-17. Effective date 2026-05-12 is in the diff. Compact `dates.known_at.semantic` is labeled `"official"` — **that label is wrong**; known_at is this projector’s first-seen clock |
| Correct evidence | Official source ↗ USAspending award id; receipt ref matches parquet `source_receipt_id` |
| No invented claims | Stance “Watch — do not chase”; authority fence false; limitations printed on the event |
| Correction state | `is_correction=false` is consistent; **late discovery is in the JSON (`is_late_discovery=true`) but the compact title does not say “late”** — unlike the sibling HII row which *does* say “Award discovered after effective date” |

HII `N0002415C2114` is the other compact row (late award discovery, current/potential amount `$4,529,389,336.50`). It is a control that the UI *can* surface late-discovery language; this IRDM obligation row does not.

## 8. Workstream B acceptance

Another reviewer can travel from the compact browser row to the official P00032 transaction without an identity break. Remaining honesty gaps (recorded, not unexplained):

- `source_published_at` absent
- compact `agency: {}` despite DISA on the official award
- `known_at` marked `semantic: official` in `dates[]`
- late-discovery flag not in the IRDM row title
- entitled API event endpoint not proven (401 in this session)
- graph UEI evidence is a different award

Those are product/contract defects for D1+, not missing hops in this chain.
