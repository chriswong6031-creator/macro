# Market Ontology Final Preservation Audit

**Operation:** `marketontology-final-preservation-census-20260828-terra-001`
**Date:** 2026-08-28
**Parent:** `WS:MARKET-OS` / Market Ontology complete-parity F00
**Scope:** archive-first evidence preservation and adversarial current-public reconciliation only. This is not a build, adoption, authority, or access-expansion decision.

## 1. Formal result

```text
SAFE_TO_LOSE_MARKETONTOLOGY_ACCESS: NO
RESULT_CLASS: HISTORICAL_ARCHIVE_STILL_DARK + CURRENT_PUBLIC_FINDINGS_NOT_ZERO
HISTORICAL_ARCHIVE_STATUS: OPEN_IMPORT_GATE
CURRENT_PUBLIC_CENSUS_STATUS: COMPLETED_WITH_MATERIAL_FINDINGS
AUTHENTICATED_COVERAGE_STATUS: NOT_PROVEN (no existing authenticated session was available)
IMPLEMENTATION_AUTHORITY: NONE GRANTED
```

This is intentionally a **failure to close**, not a negative judgment about the
earlier team. The historical public-P1 corpus remains absent from the accessible
repository/archive surfaces, and a second discovery method found meaningful
current-public state that top-level navigation alone does not preserve. A claim that
the 88/88 advertised paid rows make the corpus complete would therefore be false.

The prior authenticated research is sufficient for the architectural decisions it
was already used to make. It is not a substitute for the retained evidence reserve
needed to reproduce route-level states, exports, and screenshots if access ends.

## 2. Non-negotiable archive receipt

The earlier retained record `DSC:MARKET-ONTOLOGY-PUBLIC-P1-CORPUS-RETAINED-OUTSIDE-GITHUB`
identifies the artifact that must be recovered intact:

| Artifact | Required identity | Result of this operation |
|---|---|---|
| `MARKET_ONTOLOGY_P1_CAPABILITY_LEDGER_V5.csv` | 495,184 bytes; SHA-256 `1b5d1137710d6bae504e94bbcf4155a3bd5491863e0d8e84078b0d009564a827` | **NOT FOUND** |
| JSON twin | 957,866 bytes; SHA-256 `785f83ca2e92e070d41174b2a6e28834019517d6c845351771eb261fde766d59` | **NOT FOUND** |
| P1 master artifact index and Turn-1 through Turn-6 reports | required supporting historical evidence | **NOT FOUND AS AN EXACT IMPORT SET** |

### 2.1 Checks performed before any current-site crawl

1. Searched the fresh `origin/main` tree and all locally reachable refs for the
   exact V5 names and historical public-P1 archive paths.
2. Checked the named local Market Ontology archive and the related Downloads packet.
   Those surfaces contain a Desk-authenticated packet, not the public V5 bytes.
3. Checked the earlier named Market Ontology P1 worktree for the exact artifact.
4. Queried the local exact-filename index for the CSV, JSON twin, and master index.

No check returned the required bytes. This is a bounded accessible-surface receipt,
not a claim that every personal volume or backup was exhaustively searched. No
replacement was fabricated; no Desk packet was relabelled as public P1; no import
was made.

### 2.2 Closure condition for the archive gate

F00 may close this gate only after the original bytes are placed in the bounded
historical archive, a manifest records the source/receipt and import date, and the
CSV and JSON hashes above match exactly. Historical owner/state suggestions then
require current-law reconciliation; importing the archive never grants product,
source, or execution authority.

## 3. What was reconciled

The operation compared three separate inventories without collapsing their meanings:

| Inventory | Count/status | Role in this audit |
|---|---:|---|
| Historical public P1 | 1,556 capability rows plus 460 quality findings; bytes absent | completeness reserve; still the import blocker |
| Authenticated paid baseline | 88 rows in `MARKET_ONTOLOGY_COMPLETE_PARITY_ADOPTION_LEDGER_2026-08-26.csv` | advertised-capability baseline |
| Earlier current-public delta | 42 rows in `MARKET_ONTOLOGY_CURRENT_PUBLIC_DELTA_LEDGER_2026-08-26.csv` | current name/depth reconciliation input |
| This final preservation pass | 15 recorded observations; 6 material preservation candidates | adversarial delta and evidence receipt |

The new records are additive evidence. They do **not** rewrite the 88-row ledger,
the 42-row delta ledger, the F00/F01-F13 manifest, or any existing disposition.

## 4. Method — deliberately different second pass

### Pass A: direct product-state sampling

Direct public pages and the read-only public preview were used to understand the
event-to-decision workflow, option-expression lifecycle, capital-markets workspace,
event-to-holdings workspace, API contract, and visible entitlement boundaries. The
focus was functional depth: field sets, state transitions, saved/monitoring behavior,
and the next surface opened from a decision—not feature labels or marketing prose.

### Pass B: indexed-route and dynamic-family challenge

This was intentionally not another navigation crawl. The operator supplied the
public robots policy and sitemap index. Its allowed public route families were used
while respecting the listed exclusions (including settings, portfolio, entity,
workspaces, app, team, checkout, activation, and reset paths). Sitemap child
inventories were read as public route indexes, not mass-crawled:

| Sitemap family | Indexed public URLs observed | Why it matters |
|---|---:|---|
| static | 292 | feature landers and workflow/orphan pages |
| owned | 7 | additional product-positioning landers |
| geonews | 11 | recurring geopolitical-news family |
| map-the-world | 10 | event-to-portfolio family |
| public | 25 | public console/drill-down family |
| equities | 3,087 | dynamic entity and per-ticker impact-ledger family |
| events | 2,088 | dynamic event-record family |
| news | 55 | current event subset |

Representative samples were selected from the large indexed dynamic families. This
finds route shapes and object contracts; it does not claim a full content crawl of
more than five thousand dynamic pages. The in-app browser itself blocked direct
sitemap navigation, so the public index was retrieved read-only using the supplied
policy boundary. No account was created, no sign-in was attempted, and no access
control was bypassed.

## 5. Material preservation findings

The complete detailed matrix is
`MARKET_ONTOLOGY_FINAL_PRESERVATION_OBSERVATION_MATRIX_2026-08-28.csv`.

### P-001 — Ticker Impact Ledger is an object contract, not just a Ticker Workspace

The indexed entity family contains a public ticker page that leads to a distinct
per-ticker impact ledger. The ledger presents two linked histories:

- an assumption-change history with **date, field, direction, magnitude, and
  confidence**; and
- an event-impact history with **date, event/channel, direction, horizon, and
  impact**.

This is related to `MO-PAID-021` (Ticker Workspace), `MO-PAID-022` (Valuation
Finder), and event mapping, but the current ledgers do not preserve the explicit
entity-level bridge from an event to a typed assumption change and then to a durable
per-ticker log. It is a high-priority F06/F07 reconciliation candidate, not a new
financial-truth store.

### P-002 — Ticker Options “Current Read” is a composed research state

The public ticker-options route composes a live chain and a synthesis layer in one
security state. The visible components are chain quotes/volume/open interest/implied
volatility/Greeks; open-interest concentration; dealer gamma and delta positioning;
a strike/expiry volatility surface; notable flow; and a synthesized current read.

The baseline already names chain, OI, dealer positioning, vol, flow, and scenario
components (`MO-PAID-012` through `MO-PAID-015`, `MO-PAID-071` through
`MO-PAID-077`). The preservation gap is the **composition law**: those primitives
are interpreted together in a ticker-specific, continuously refreshed current state.
The record belongs with F03 and must remain research/decision-support context until
its own source, timing, and evaluation law is accepted.

### P-003 — Catalyst-to-options presents a state-machine contract

The public surface presents this sequence, rather than merely a page named
“catalyst-to-options”:

```text
catalyst -> exposed assets -> options structures -> saved thesis -> change monitor
```

The public description says a thesis binds catalyst, asset, structure, rationale,
invalidation, and alert, and that related catalysts and asset moves can change the
monitored state. No thesis was created, reloaded, or monitored in this operation.
Accordingly, persistence is **unproven**; the preserved finding is a state-machine
*contract presented by the public surface*. It confirms the depth behind
`MO-DELTA-033` and `MO-PAID-070` rather than creating a separate workflow authority.
F03/F11/F08 must preserve the candidate handoffs and test persistence separately.

### P-004 — Research Terminal is a continuation graph

A live catalyst is visibly ranked using direction, horizon, confidence, dislocation,
and pricedness, with calls to continue into a ticker workspace, valuation inputs,
policy pipeline, capital-markets analysis, or scenario/portfolio response. The current
page displays source/evidence, mechanism, affected assets, risks, invalidation, and
monitoring fields associated with that graph. The calls were not activated and no
saved research object was created, so destination behavior and persistence are
unproven.

This confirms the relevant existing baseline and delta families but shows that the
preservation unit is the **event-to-next-research-surface transition**, not the six
destination feature names in isolation. F04 is the cross-lane accountant; F05/F06/F07/
F08/F09 retain their existing ownership boundaries.

### P-005 — Capital Markets is an issuer state cycle

The capital-markets page presents: issuer qualification; probable action and timing;
candidate financing routes and gating conditions; comparable terms; a transaction
effect across share count, ownership, debt, interest expense, leverage, liquidity,
WACC, and valuation; and an offered saved-issuer/return-on-change workflow. No issuer
was saved, no transaction was accessed, and no return/monitor transition was observed.

Existing F09 rows name the constituent workbenches. The current preservation delta is
the **presented state cycle** that would make them one returning issuer analysis rather
than independent screens; its actual persistence is an explicit test gap. It is a
depth reconciliation candidate, not approval for a parallel capital-structure truth
plane.

### P-006 — Indexed public route families are themselves preservation evidence

The indexed current public estate exposes a dynamic entity/impact-ledger family and a
dynamic event-record family at significant scale. The sampled event record carries a
timestamp, event type, confidence, verification status, causal/mechanism content, and
exposed assets. This establishes a public record schema and a need to retain route-
family shape; it does not license bulk copying of event prose or data.

## 6. Confirmations that reduce ambiguity but do not close the audit

- The public event-to-holdings page visibly presents the earlier `MO-DELTA-042`
  pattern: one time-stamped event resolves through a mechanism into per-position
  direction, timeframe, confidence, evidence, and invalidation, with monitoring as an
  offered later state. No holdings or monitor were submitted, so the state transition
  is unproven. It is a confirmation, not a new portfolio authority.
- The API page documents the earlier API delta and adds monitor/update, stored-analysis,
  evidence retrieval, and widget-session route shapes. Its stated separation of
  evidence and inference, versioning, idempotency, signed delivery, retry, and
  deduplication remains a contract/reconciliation input only. No API was called, so no
  response, persisted analysis, monitor update, or delivery behavior was verified.
- The public daily brief page shows a brief as a dated state containing regime,
  cross-asset monitor, transmission-chain status, scorecard, and week-ahead schedule.
  This confirms depth behind the existing daily-brief rows; it is not a new signal
  authority.

## 7. Negative and inaccessible evidence

| Subject | Result | Interpretation |
|---|---|---|
| Exact public-P1 corpus | not found on checked accessible surfaces | historical completeness remains blocked |
| Public-console drill-downs | sign-in required | do not infer their absence or their authenticated behavior |
| Authenticated workspace, settings, portfolios, team, and app paths | not tested | excluded by supplied robots policy and no authenticated session was used |
| One indexed workflow URL | page reported workflow not found | a negative route result, not evidence the job does not exist elsewhere |
| Browser direct sitemap navigation | client-side blocked | method limitation; public index was otherwise available through the supplied policy boundary |

## 8. Visual/state preservation rule

No competitor screenshots, visual assets, or source code are imported. Desktop public
layouts were observed only to validate visible state and controls. The matrix now
records semantic visual structure, available action, observed action result/auth
boundary, transition contract, persistence status, and entitlement status separately.
It intentionally stores that semantic visual structure rather than screenshots. Mobile
behavior and authenticated visual states remain unproven.

## 9. Required next action and review challenge

1. **Exact-byte recovery first:** locate the historical public-P1 archive and execute
   the hash-gated import described in section 2. Do not regenerate the 1,556 rows.
2. F00 should classify each `P-*` candidate explicitly as existing, depth expansion,
   alias/projection, new workflow, or rejected-by-design. The candidate matrix is not
   an automatic adoption ledger.
3. A different worker must independently review only this preservation packet and try
   to find an omitted meaningful state using a method different from both direct pages
   and the sitemap route inventory. The review commission is supplied in
   `MARKET_ONTOLOGY_FINAL_PRESERVATION_REVIEW_PACKET_2026-08-28.md`.
4. Do not state the competitor capture can close until the independent reviewer either
   reports zero material omissions with evidence or records the additional findings.

## 10. Authority and safety boundary

All findings are black-box product research. They do not authorize implementation,
data acquisition, authentication changes, source-rights changes, customer contact,
commercial purchase, portfolio access, market action, or a new control/truth plane.
Any future work remains subject to current Mastermind strategic state, the complete
parity adoption decision, source/rights law, and lane-owner reconciliation.
