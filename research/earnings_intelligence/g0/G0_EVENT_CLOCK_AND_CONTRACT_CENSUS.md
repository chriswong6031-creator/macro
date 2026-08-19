# G0 Event Clock and Contract Census

**Commission:** MASTERMIND GROK-G0 — Post-Event Reinterpretation Research Census  
**Owner:** existing `earnings-intelligence` program (`DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`).  
**Not a new store.** No Prophet change. No trading signal.  
**Tree:** `origin/main` @ `12f60066e324` (session worktree `grok/g0-post-event-census`).  
**Live object checked this session:** public `event_workspace.v1` generation `f709a0a6ec514282d5769e7d`.

Tag vocabulary: `CODE VERIFIED` · `PRODUCTION VERIFIED` · `PRIMARY SOURCE VERIFIED` · `INFERRED` · `UNKNOWN`.

---

## 0. Ownership and collision map

| Question | Answer | Tag |
|---|---|---|
| Who owns event / document / claim / earnings product truth? | `earnings-intelligence`. Product name: Mastermind Earnings Intelligence OS. | CODE VERIFIED — `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`; freeze `research/earnings_intelligence/E0_E1_E2_CONTRACT_FREEZE.md` §0 |
| Who owns filings → reversible financial facts / disclosure changes / packets? | FIF / `fundamental-forensics`. Packet still `context_only` / `display_only: true`. FIF-7 (earnings / non-GAAP / KPI / guidance convergence) is **todo**. | CODE VERIFIED — `WS:FINANCIAL-INTELLIGENCE-FABRIC`; `contracts/financial_intelligence_packet.schema.json` `authority` |
| Who owns group read-through / sympathy? | `group-reads`. Do not rebuild inside Earnings. | CODE VERIFIED — freeze §0; `DNR` spirit of `DEC:EARNINGS-INTELLIGENCE-IS-A-CENTRAL-LOBE` |
| Who already mapped clocks across the estate? | Grok-A0 temporal matrix. **Do not rename foreign clocks** to `observed_at`. | CODE VERIFIED — `research/evidence_mesh/A0_TEMPORAL_SEMANTICS_MATRIX.md` |
| Who already cased market incorporation? | Opportunity-evidence E0 incorporation casebook over `research/winners/cases/*.md`. G0 **consumes** those receipts; it does not take that owner. | CODE VERIFIED — `research/opportunity_evidence/E0_MARKET_INCORPORATION_CASEBOOK.md` |
| May this census mint a second program / packet / workspace? | No. Extension stays under Earnings event_workspace + existing FIF packet. | STATED by commission |

No canonical-owner conflict blocks the census. The collision risk is **duplicate clocks / duplicate reaction objects**, not a missing owner.

---

## 1. The two clocks that already exist (do not invent a third pair)

Earnings already has a point-in-time firewall. FIF already has a two-cutoff query. They are **not** the G0 legal-information frontier. They are the substrate that frontier must bind to.

### 1.1 Earnings `company_event.v1`

Every lifecycle transition carries `observed_at` and `source_available_at`. A transition with `observed_at < source_available_at` is refused.

- CODE VERIFIED — `engine/company_intelligence/events.py` module docstring L16–20; `EventTransition.__post_init__` L249–253.
- Event states (not G0 frontier states): `discovered`, `scheduled`, `rescheduled`, `started`, `completed_partial`, `complete`, `corrected`, `superseded`, `derived_ready`, `distributed`, `cancelled`. CODE VERIFIED — `EVENT_STATES` L43–55.
- Coverage states (`blocked_rights`, `source_missing`) are **not** event states. CODE VERIFIED — L71–74.
- `point_in_time: bool = True` on `CompanyEvent`. CODE VERIFIED — L288.
- Document clocks: `fetched_at`, `published_at`, `available_at`. CODE VERIFIED — `engine/company_intelligence/documents.py` L162–164, L195, L223–225.

### 1.2 Compact payload `event_workspace.v1`

Required keys include `lifecycle`, `completeness`, `facts`, `deltas`, `guidance`, `claims`, `sources`, `qa_exchanges`, `authority`, `prophet_flags`. CODE VERIFIED — `engine/company_intelligence/event_workspace.py` `WORKSPACE_KEYS` L46–66.

`lifecycle` projection is only `{state, observed_at, source_available_at}`. CODE VERIFIED — `_lifecycle_payload` L234–241.

Completeness axes on the **workspace** (E1): `release`, `filing`, `transcript`, `slides`, `consensus`, `reaction`. CODE VERIFIED — `event_workspace_build.py` L399–420.

Hard rules already frozen:

| Rule | Receipt |
|---|---|
| Authority `context_only`; Prophet flags all false | `event_workspace.py` L39–44, L251–255 |
| `basis_match` true is **not minted in E1** without licensed consensus | `validate_event_workspace` L275–276 |
| Beat/miss keys forbidden unless `basis_match` is true | L277–278 |
| Warning vocab includes `reaction_not_joined`, `consensus_unlicensed`, `slides_absent`, `questions_count_unstructured` | `WORKSPACE_WARNINGS` L80–87 |

### 1.3 FIF `financial_intelligence_packet.v1`

Query requires **both** `source_event_cutoff` and `system_recorded_cutoff`. Policies: `as_reported` / `latest_known_as_of` / `latest_restated`. Modes: `historical_replay` / `retrospective_research`. Authority `class: context_only`, `display_only: true`. CODE VERIFIED — `contracts/financial_intelligence_packet.schema.json` L97–127, L62–70.

Underlying forensics clocks: `KnowledgeClock.SOURCE_EVENT` vs `RECORDED`; occurrence `source_event_at` / `recorded_at`; Company Facts `pit_eligible` iff `accepted_at is not None`. CODE VERIFIED — `engine/fundamental_forensics/models.py` L21–23, L161–162; `companyfacts_ledger.py` L434–435.

FIF-1 is still in Sol review; FIF-2 must not start; FIF-7 (earnings/guidance convergence) has **not** been built. CODE VERIFIED — `WS:FINANCIAL-INTELLIGENCE-FABRIC` waves.

---

## 2. Live production object (AAPL FY2026 Q3)

**PRODUCTION VERIFIED** this session (`curl` 200):

- Marker: `https://pub-f7ffb4441c5f4ad983ca56ec7c651c61.r2.dev/company_intelligence/event_workspaces/manifest.json`
  - `schema=event_workspace_manifest.v1`
  - `generation_id=f709a0a6ec514282d5769e7d`
  - `generated_at=2026-07-30T20:30:28Z`
  - `event_count=1`
  - `authority=context_only`
- Workspace: `…/generations/f709a0a6ec514282d5769e7d/workspaces/evt_cik0000320193_2026q3_results.json`

| Field | Live value | Implication for G0 |
|---|---|---|
| `lifecycle.state` | `complete` | Event lifecycle ≠ information-frontier state |
| `lifecycle.observed_at` | `2026-07-30T20:30:28Z` | Same instant as `source_available_at` |
| `lifecycle.source_available_at` | `2026-07-30T20:30:28Z` | **Two-clock firewall is present in schema and collapsed in this generation** |
| `completeness.release` | `present` | Exhibit 99.1 bound |
| `completeness.filing` | `bound` accession `0000320193-26-000018` | Filing key exists; 10-Q/10-K reconcile is not a completeness axis |
| `completeness.transcript` | `present` `tx:AAPL/2026Q3` | Body exists; chapters not split on the workspace |
| `completeness.slides` | `absent` typed absence | Honest |
| `completeness.consensus` | `unlicensed` typed absence | No legal beat/miss |
| `completeness.reaction` | `not_joined` | No price/options join |
| `qa_exchanges` | `[]` | Empty list, not structured Q&A |
| `deltas[0].basis_match` | `false` | Beat/miss correctly withheld |
| `sources[*]` | no `available_at` / `published_at` / `observed_at` | Per-source clocks are **not on the published object** |
| `warnings` | `collector_filing_unjoinable`, `consensus_unlicensed`, `questions_count_unstructured`, `reaction_not_joined`, `slides_absent`, `wire_record_not_found` | Public Wire still 404 for the flagship |
| `prophet_flags` | all false | Must stay false |

The generation timestamp equals both lifecycle clocks. That is a **collapsed PIT proof**, not evidence that the legal headline, full 8-K, prepared remarks, and Q&A arrived at one instant. INFERRED from the equality; the builder stamps `generated_at` from the same `clock` used for lifecycle (`event_workspace_build.py` L449).

---

## 3. Native-source census against the G0 frontier

G0 asked, for every native source: `source_available_at`, `system_recorded_at`, after-hours / premarket / open timing, historically PIT.

| Native source | Estate home | `source_available_at` (legal / source) | `system_recorded_at` (our write) | AH / PM / open timing | Historically PIT? | State |
|---|---|---|---|---|---|---|
| Earnings calendar | `collectors/equity_earnings.py` → `data/earnings/earnings.parquet` | UNKNOWN as a legal print time. Calendar `next_date` is unofficial. | Sweep `as_of` | Not a session clock | No. Freshness audit 17.9% within 2-td SLA (E0 ledger, as_of 2026-08-13) | PARTIAL — CODE VERIFIED via E0 ledger |
| Headline / newswire | **No CEI headline object** | — | — | — | — | NOT_BUILT |
| 8-K Item 2.02 / Exhibit 99.1 | Marketing EDGAR + E1 bind; CEI digest still forces `release: not_ingested` on **Wire** | SEC `acceptanceDateTime` exists on submissions; **not copied onto live workspace sources** | Collector fetch / workspace `generated_at` | SEC acceptance is UTC; **not mapped to US session phase** | Filing acceptance is PIT **if** joined on accession, not `filing_date±N` (`JOIN_DATE_TOLERANCE_DAYS = 0`, A0 matrix) | PARTIAL — live AAPL release `present`; Wire still transcript-only |
| 10-Q / 10-K | FIF / EDGAR statements; CEI filing completeness is 8-K bind only | `accepted_at` / packet `source_event_cutoff` | `recorded_at` / `system_recorded_cutoff` | Same as SEC acceptance | Only when `accepted_at` is present (`pit_eligible`) | PARTIAL on FIF fixture; NOT_JOINED to event_workspace |
| Prepared remarks | Transcript chapter heuristic in digest | Transcript `published_at` / `available_at` **fields exist on `SourceDocument`**, not on live sources[] | Story / workspace generation | UNKNOWN | Transcript revision SHA is PIT for **body identity**, not for call-clock vs Q&A-clock | PARTIAL — digest chapters `prepared` vs `q_and_a`; workspace does not split |
| Q&A | Digest lexical markers; Terminal display filters | Same transcript clock | Same | UNKNOWN | No exchange object; no per-answer clock | PARTIAL / NOT_BUILT as `qa_exchange.v1` |
| Slides | Completeness enum only | — | — | — | — | SPEC_ONLY / absent |
| Consensus / estimates | Unlicensed typed absence on CEI; Yahoo snapshot archive accruing from 2026-06-16 (E0 incorporation) | Vendor as-of **if** licensed | Snapshot write | n/a | Pre-June 2026: unlicensed_absent. Live CEI: unlicensed | PARTIAL / ACCRUING |
| Analyst revisions | `engine/analyst_revisions.py`; Finnhub recommendation parquet; `collectors/equity_revisions.py` | UNKNOWN as a decision-time vintage for most history | Snapshot / accruing parquet | n/a | E0 incorporation: Yahoo revisions ACCRUING from 2026-06-16 only. Intelligence-hub note: yfinance snapshot is lookahead-contaminated until vintages accrue | PARTIAL / ACCRUING |
| Price reaction | Digest **forced** `{status: not_joined}`; workspace `reaction: not_joined`; `promotion.py` forbids `market_reaction` as an input | — | — | Stock PEAD copy on `stock.html` is **not** a CEI field (E0 ledger) | Winner-case daily bars exist; **not joined to event_workspace** | SPEC_ONLY on CEI; PARTIAL elsewhere |
| Options reaction | `engine/event_window.py` implied-move helper; GEX snapshots from 2026-06 | Vendor session | Snapshot | Implied move is an **ex-ante** read, not a post-event join | Options history starts ~2026-06; earlier = unavailable, not zero (E0 incorporation law) | PARTIAL / ACCRUING; not joined to CEI |
| Guidance language (thematic, not CEI) | `collectors/edgar_guidance.py` 8-K phrase hits | EDGAR `file_date` | `fetched` column | file_date is a date, not a session phase | Phrase match; no negation; not a CEI `guidance_item.v1` series | DARK relative to Earnings OS — CODE VERIFIED collector exists |
| Disclosure / accounting change | FIF `disclosure_changes[]` | source-event cutoff | system-recorded cutoff | n/a | Only inside FIF packet replay | SPEC / fixture — FIF-1 not frozen |

### Wire vs workspace split (load-bearing)

Public Wire **must** disclose transcript-only completeness:

```
release: not_ingested
filing: not_ingested
transcript: present
slides: not_ingested
consensus: unlicensed_absent
```

CODE VERIFIED — `engine/earnings_narrative/public_wire.py` L394–400; `digest.py` L252–260; `promotion.py` `_REQUIRED_COMPLETENESS` L45–51.

Digest `market_reaction` **must** be `{status: not_joined, as_of: None, security_ids: []}`. CODE VERIFIED — `digest.py` L397–400, L618.

So: the workspace can bind an 8-K for AAPL, and the Wire is still legally a transcript excerpt archive. G0 must not treat Wire completeness as the event clock.

---

## 4. G0 frontier vs existing state machines

The commissioned frontier is a **legal information frontier**, not the docket §4.3 lifecycle.

| G0 state | Closest existing object | Gap |
|---|---|---|
| `PRE_EVENT` | `scheduled` / calendar row | Calendar is unofficial; no embargo / consensus vintage on the event |
| `HEADLINE_AVAILABLE` | none | No headline document kind; first legal text is usually the 8-K / Exhibit 99.1 |
| `FULL_RELEASE` | completeness `release=present` | No session-phase; no distinction between alert and full exhibit |
| `PREPARED_REMARKS` | digest chapter `prepared` | Not on workspace; no clock separate from the transcript file |
| `QA_AVAILABLE` | digest chapter `q_and_a`; `qa_exchanges: []` | Marker only; no exchange records |
| `FILING_RECONCILED` | completeness `filing=bound` (8-K key) + FIF packet | 10-Q/10-K reconcile is FIF-7, not CEI |
| `FIRST_SESSION_CLOSE` | none on CEI | Would require PIT prices + `security_id` + session calendar |
| `ANALYST_REVISION_STATE` | accruing revision snapshots | Not event-joined; not PIT before mid-2026 |

Do **not** overload `complete` to mean “all G0 states reached”. Live AAPL is `complete` with reaction not joined, Q&A empty, consensus unlicensed, and both clocks collapsed.

---

## 5. What G0 may add later (census only — not built here)

A later wave, still under Earnings, may add an **orthogonal** `information_frontier` projection on `event_workspace.v1`:

- per-source `{kind, source_available_at, system_recorded_at, session_phase, pit_class}`
- derived `frontier_state` with explicit UNKNOWN / ACCRUING / BLOCKED
- still `authority=context_only`, still no beat/miss without `basis_match`
- FIF remains the filing-fact owner; G0 reads packets, does not fork them

That is a contract extension of the **existing** workspace, not a second nest. E2 is still the next *product* wave (`WS:EARNINGS-INTELLIGENCE-OS` `next_action`). G0 must not jump the E2 queue.

---

## 6. Rights and Prophet fences

- `blocked_rights` is named and **non-mintable** until a rights registry exists. CODE VERIFIED — `events.py` L76–84.
- Transcript rights profile on flagship spans: `rp_public_primary_v1` in the builder. CODE VERIFIED — `event_workspace.py` `_span_payload_from_transcript` L229.
- Golden corpus bodies are **synthetic**. CODE VERIFIED — `research/company_intelligence/GOLDEN_CORPUS_MANIFEST.json` `note`.
- `promotion.py` `_FORBIDDEN_INPUTS` includes `consensus`, `market_data`, `market_reaction`. CODE VERIFIED — L52.
- LLM origination of a reinterpretation verdict is `DNR:KILL-LLM-ORIGINATION`.

---

## 7. What I could not verify

| Claim | Why |
|---|---|
| After-hours vs premarket vs open for any live CEI source | No session-phase field on workspace sources or digest |
| Historical PIT for Wire print times | Wire is excerpt archive; `generated_at` is not source time (`DSC:EARNINGS-WIRE-AND-CI-DIVERGE-ON-THE-SAME-ISSUER`) |
| Whether FIF-1R2 PR merged after this SHA | FIF-1 still `in_progress` on the workstream record at session start; not re-adjudicated here |
| Licensed consensus anywhere in production CEI | Live typed absence only |
| Options implied-move joined to any `evt_cik…` | `event_window.py` exists; CEI reaction remains `not_joined` |
