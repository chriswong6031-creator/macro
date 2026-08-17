# D0R required runtime lineages (A2)

**Cut:** git `HEAD` artifacts `as_of=2026-08-13`, graph `defense19-v1` digest `0733a966c4442a4fc5bb883d1670320218ecc3b6754131f7ee84965d3036f758`, workspace bundle `grw2-dd9d7af893a7f3c773909351`, candidate queue `grcq1-d93ebaf6878402e3be09e490`.  
**Production entitled proof:** 2026-08-17T04:39–04:46Z, `site_full`, cookie workspace **500**, bearer candidates **22**.  
**Law:** every hop is an observed artifact, API, or typed failure. No fabricated source, graph, or NW/Prophet packet.

The required six families:

| # | Family | Terminal | Packet |
|---|---|---|---|
| 1 | Positive award/action | Browser Change Tape | `D0R_GOLDEN_AWARD_CHANGE_LINEAGE.md` (HC101319C0006 **P00032** / IRDM) |
| 2 | Negative / deobligation / correction | Workspace event; **no ticker on the deobligation row** | L2 below |
| 3 | Opportunity / recompete | Typed `unavailable` | L3 below |
| 4 | Budget / program | Typed `PROJECTION_MISSING` / JS `unavailable` | L4 below |
| 5 | Issuer-mapping ambiguity | Mapping backlog **21**; GE/BWXT `mapping_needed` | L5 below |
| 6 | Company financial / transcript join | Candidate `earnings_transmission` stops at null denominator; Earnings/SEC owner not forked | L6 below |

---

## L1. Positive award/action (closed)

See `D0R_GOLDEN_AWARD_CHANGE_LINEAGE.md`.

```
USAspending POST /api/v2/transactions/
  CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0
  action_type C FUNDING ONLY; federal_action_obligation 18416666.66; action_date 2026-05-12
        ↓
receipt usaspending:usaspending-3be22546a4a9a6b9a46a7469:actions:1d52f66cfa31a196:2a07ba19681a3c9d
        ↓
award_action_versions.parquet event_eligible true; known_at 2026-08-12T23:50:04Z; is_late_discovery true
        ↓
workspace event govws-a6c70850a9cbdce9fa3e7f3b
        ↓
defense19-v1 UEI S77SW52LCR57 → Iridium Government Services LLC → parent → central:IRDM
        ↓
candidate grc1-025ab7cfdb7f9735f0e1e575 (API 22)
        ↓
cookie workspace.json 500 AND compact teaser row
        ↓
browser Changes tab (entitled) — official source link
        ↓
NW/Prophet: not observed this session (typed unverified, not fabricated)
```

Not GAAP revenue. Not an August catalyst.

---

## L2. Negative / deobligation / correction

**Observed object:** HEAD `data/government_revenue/workspace.json` contains **35** `award_change.event_type=deobligation` rows among 500. Largest magnitude with a retained official amount:

| Field | Value |
|---|---|
| event_id | `govws-aa6f1867ab7cae18de92e16c` |
| title | Deobligation observed — N0002415C2114 |
| PIID | `N0002415C2114` |
| action_id | `CONT_TX_9700_-NONE-_N0002415C2114_AZ0010_-NONE-_0` |
| amount | `federal_action_obligation` **−5,937,624.00** USD |
| effective_at | 2018-03-22 |
| known_at | 2026-08-08T03:58:07.559480Z |
| is_late_discovery | true |
| listed_company_impacts | **[]** |
| primary_ticker | **null** |

Sibling on the **same PIID** that *does* carry HII: `govws-b19836e22bc86b6144fd410a` (`award_discovered_late`, title “Award discovered after effective date — N0002415C2114”).

```
official USAspending transaction (negative obligation)
  CONT_TX_…_N0002415C2114_AZ0010_…
        ↓
receipt-bound action version (same collector family as P00032; known_at 2026-08-08)
        ↓
normalized event govws-aa6f1867ab7cae18de92e16c
  kind award_change / event_type deobligation
  amount semantic official / value negative
        ↓
graph join
  TYPED GAP: listed_company_impacts empty on this deobligation
  same PIID late-discovery sibling carries HII
        ↓
financial join
  not asserted (no ticker)
        ↓
candidate/display
  this event is NOT in the 22-row candidate queue (queue is award_obligation_change / award_ceiling_change on reviewed issuers)
        ↓
API
  present inside entitled workspace.json 500; not a standalone /events total (filtered events API total=31)
        ↓
browser
  entitled Change Tape includes deobligation titles in the 500; inspector must keep the minus sign
        ↓
NW/Prophet
  not observed; must not be inferred from the HII sibling
```

**Correction family (related, not a restatement overwrite):** 12 workspace rows are `reported_obligation_balance_changed`, including IRDM sibling `govws-70d45adde3342d5eca8f8014` on HC101319C0006. Those are observation-kind updates, not silent overwrites of P00032.

**D1/D3 implication:** late-discovery UI must use existing `is_late_discovery`, never a frontend `action_date << known_at` heuristic. Deobligation without ticker must remain a Change Tape row, not a Radar candidate.

---

## L3. Opportunity / recompete → typed failure

HEAD `data/government_revenue/latest.json` → `opportunity_intelligence`:

- `opportunities`: **[]**
- `events`: **[]**
- `freshness.opportunities.status`: **`unavailable`**
- `records_visible`: 0
- `observed_at`: null
- `freshness_sla_minutes`: 90

Entitled browser: Opportunities **0**, Recompete **0**, SAM copy **SOURCE_UNAVAILABLE**.

```
SAM.gov opportunity notices
        ↓
GovRev opportunity collector / current-state rail
  TYPED FAILURE: freshness.opportunities.status = unavailable
  no raw notice corpus in this cut
        ↓
parse / event
  empty arrays (not a valid-empty “no bids this week” — clocks are null)
        ↓
graph
  no opportunity nodes asserted
        ↓
candidate/display
  Opportunities/Recompete tabs render 0
        ↓
API
  opportunity current-state not entitled-proven as a 200 corpus
        ↓
browser
  SOURCE_UNAVAILABLE (do not coerce to empty-valid)
        ↓
NW/Prophet
  no opportunity packet
```

**Not D1:** do not build a SAM collector in the rescue. D1 may only print the typed failure honestly and stop the compact-loading banner from implying the rail is still hydrating.

---

## L4. Budget / program → typed failure

HEAD: no `government_budget_program_graph.v1` artifact under `data/government_revenue/` or `site/government-revenue-data/` (budget keys absent from `latest.json`).

Live entitled Budget tab: **“Budget request rail unavailable”** (JS `budgetStatus='unavailable'` after `/api/government-revenue/budget-programs` fails). Product census labeled this **PROJECTION_MISSING**.

Official source **does** exist and was re-verified 2026-08-17: https://comptroller.defense.gov/Budget-Materials/ currently lists FY2027 P-1 and R-1 PDFs. Absence is our graph, not the government’s books.

```
DoD Comptroller P-1 / R-1 PDFs (official, public)
  verified_at 2026-08-17: Budget-Materials page lists Procurement Programs (P-1)
  and RDT&E Programs (R-1) for FY2027
        ↓
GovRev budget_program collector / graph bake
  TYPED FAILURE: artifact absent on HEAD; API budget-programs not a live graph
        ↓
templates/government-revenue-dossiers.js createGovernmentRevenueBudget
  fetch /api/government-revenue/budget-programs → catch → status unavailable
        ↓
browser Budget tab 0 + “Budget request rail unavailable”
        ↓
financial join / Radar / NW
  not reached
```

**D1:** typed failure state only (`PROJECTION_MISSING` or equivalent already used in A). **Not D1:** parse P-1/R-1 into a graph. That is a separately scoped P-1/R-1 collection wave if it exceeds the rescue.

---

## L5. Issuer-mapping ambiguity

Entitled mapping-backlog API **total=21**, same `content_id` as the candidate queue. HEAD `candidate_queue.json` `mapping_backlog` length 21.

Two **hard** `mapping_needed` / `exact_identifier_mapping_required` rows (issuer_attribution `not_asserted`):

| ticker | company_name | backlog_id | why |
|---|---|---|---|
| **GE** | GE Aerospace | `grmb1-5b348ffef833172dda7e5643` | exact identifier + time-valid reviewed ownership path required |
| **BWXT** | BWX Technologies | `grmb1-b6aea55c4513e34edcd39b0f` | same |

The other 19 are `partial_identifier_coverage` (including **IRDM** `grmb1-1033a2ab1abbedf27dfb23a1` and **AVAV**). Partial coverage means at least one exact recipient path is reviewed, but discovery scope is incomplete — **not** ticker proof for unmatched names.

Filmstrip extras vs graph: GE/BWXT appear as discovery names; they must not mint Radar candidates.

```
discovery name / curated_fuzzy_name association
        ↓
mapping_backlog row (issuer_attribution = not_asserted)
        ↓
graph
  GE/BWXT: no reviewed UEI→legal→central:* path in defense19-v1 sufficient to emit a candidate
        ↓
candidate queue
  STOP — not in the 22 exact-linked candidates
        ↓
API /api/government-revenue/mapping-backlog 200 total=21
        ↓
browser filmstrip
  tickerRailState → mapping (“Link pending”) when backlog ticker list is hydrated;
  today the list is not hydrated because Radar load 401s to locked → “Members only”
        ↓
NW/Prophet
  must not treat filmstrip extras as reviewed issuer evidence
```

**D2** owns closing GE/BWXT (and the 19 partials) without letting backlog rows become ticker evidence.

---

## L6. Company financial / transcript join (consume Earnings/SEC; do not fork)

IRDM candidate `grc1-025ab7cfdb7f9735f0e1e575` already carries a **research-context** transmission object:

- `earnings_transmission.statement_status` = `research_context_not_trade_signal`
- `possible_earnings_channels` = backlog, revenue, margin, cash, guidance, narrative (possible, not observed)
- `materiality.issuer_attributed_denominator` = **null**
- `materiality.materiality_ratio` = **null**
- `reason_code` = `exact_issuer_attributed_denominator_not_available`
- `crosscheck_state` = `not_evaluated`
- `is_neuralweb_trade_candidate` = **false**
- mechanism evidence_refs include `evidence:irdm-sec-10k` and `evidence:irdm-sec-ex21` (graph review receipts, not a GovRev 10-K store)

```
procurement event govws-a6c70850a9cbdce9fa3e7f3b / $18.4M official obligation
        ↓
candidate materiality block (GovRev)
  attributable_amount 18416666.66; denominator null
        ↓
company financial packet
  OWNER: Earnings / SEC planes (EDGAR accession, transcript, guidance)
  GovRev must not parse a second 10-K
        ↓
join key
  ticker IRDM + Stock Identity central:IRDM (universe snapshot: tape_ended=false, compute_eligible=true, last_date 2026-08-13)
        ↓
observed this session
  tests/fixtures/govrev_issuer_evidence/sec_10k_irdm.htm is a graph-review fixture
  (registrant Iridium Communications Inc., FY ended 2025-12-31, symbol IRDM)
  — not a live earnings print join
        ↓
display
  Radar inspector already says “No issuer-attributed denominator… no materiality ratio”
  Change Tape already says Watch — do not chase
        ↓
API
  candidate 200 includes the null denominator (do not invent a ratio in JS)
        ↓
browser
  Radar UI currently locked, so the entitled user never sees this honest null
        ↓
NW/Prophet
  is_neuralweb_trade_candidate false; do not originate a signal from the $18.4M
```

**D4** is the first wave allowed to consume Earnings/SEC packets for one golden dossier. D1 must not compute a frontend materiality ratio.

---

## Lineage coverage vs A2

| Hop | L1 | L2 | L3 | L4 | L5 | L6 |
|---|---|---|---|---|---|---|
| source | USAspending tx | USAspending tx | SAM (unavail) | Comptroller PDFs (unparsed) | discovery name | SEC/Earnings owner |
| raw | receipt sha | same family | none | none | backlog row | 10-K fixture ref |
| parse | action version | action version | fail | fail | mapping_state | existing SEC parser |
| event | govws-a6c7… | govws-aa6f… | empty | none | none | candidate points at govws |
| graph | IRDM reviewed | ticker **null** | none | none | GE/BWXT needed | central:IRDM SI live |
| financial join | null denom | n/a | n/a | n/a | forbidden | null denom honest |
| candidate/display | grc1-025a | not a candidate | 0 | 0 | backlog 21 | awaiting_crosscheck |
| API | 200 | inside 500 | unavail | unavail | 200/21 | 200/22 |
| browser | Changes 500 | deobligation row | SAM down | Budget missing | Members only bug | Radar lock hides it |
| NW/Prophet | unverified | unverified | none | none | none | false flag |

A2 is **closed as research**. None of these lineages authorize D1 collectors.
