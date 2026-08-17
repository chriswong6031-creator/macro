# E0 → E1/E2 Contract Freeze

**Wave:** E0 · **Frozen:** 2026-08-16 · **Feature implementation:** none  
This freeze is the construction drawing for E1 and E2 only. Later graph seams are named, not specified.

Supersedes nothing in `research/EARNINGS_WAVE1_CONTRACT_FREEZE_2026-08-06.md`. If a line below conflicts with that file, **Wave 1 freeze wins** unless this document cites a live contradiction.

Live contradiction recorded, not silently preferred: production still listing-keys events (`cie_…`, `TICKER/transcript_id`) while Wave 1 freeze already requires issuer keys. E1 implements the freeze; it does not reopen Q1–Q5.

---

## 0. Program ownership (E0-C)

| Decision | Frozen answer |
|---|---|
| Canonical program **key** | Keep existing `earnings-intelligence` in `config/mastermind_programs.yml`. Do **not** mint a second key this PR. |
| Canonical product **name** | Mastermind Earnings Intelligence OS (Company Event Intelligence). |
| Owns | Event / document / claim / earnings product truth; public Wire as evidence/acquisition; Event Workspace projection; compact Neural Web packet. |
| Does not own | Theme lifecycle (`thematic-intelligence`); basket participation and group read-through (`group-reads`); Prophet rank/size/gate; Filing Forensics / Calcbench; Terminal shell; Stage as live authority. |
| Terminal workspace | Earnings OS owns the **payload**. Terminal owns chrome, routing, and the existing CI v1 lenses being extended. |
| Public acquisition | Earnings OS owns Wire / weekly. Do not replace with uncited analysis. |
| Follow-up (not E0) | Expand `owns` / `does_not_own` in `mastermind_programs.yml` and regenerate maps in a dedicated PR. Generated-map work is out of E0. |

Preferred architecture confirmed, not disproved:

```
earnings-intelligence
  owns event/document/claim/earnings product truth
  contains no duplicate theme or co-movement engine
  consumes Group Reads and TIL
  feeds Neural Web and research
  feeds Prophet only through governed context/shadow contracts
```

See `DEC:EARNINGS-INTELLIGENCE-PROGRAM-OWNERSHIP`.

---

## 1. Identifiers

| Object | Frozen id | Notes |
|---|---|---|
| Issuer | `company_id` = `cik:` + 10-digit EDGAR CIK | Real CIKs only. Corpus `cik_synthetic` is fixture-only. |
| Security | `security_id` | Dual class = one issuer, many securities. |
| Listing alias | ticker + MIC + `valid_from`/`valid_to` | Ticker is never a durable key. |
| Event | `canonical_event_id` = `evt_{cik}{pad}_{yyyy}q{n}_results` | Example: `evt_cik0000320193_2026q3_results`. No ticker, no call_date, no hash. |
| Alias (keep) | `cie_` + sha256(`TICKER\|YEAR\|Qn`)[:24] | Bidirectional via `event_id_adapter`. Do not rewrite history. |
| Alias (keep) | narrative `TICKER/transcript_id` | Same adapter. |
| Public slug | `{ticker.lower()}-{transcript_id.lower()}-call-record` | Compiler-owned (`public_wire.py:121-127`). |
| Document revision | `source_document.v1` + `source_sha256` | `supersedes_source_sha256` on amendment. |
| Filing key | `(cik, accession)` | Freeze Q2. No `(cik, filing_date)` tolerance join. |
| Source span | `source_span.v1` | `text_span` (UTF-8 bytes) now; `table_cell` / `slide_region` declared, empty until E1 table / E10. |
| Citation token (Macro + Terminal) | `{event_id, document_revision, locator, receipt_state}` | `receipt_state` ∈ `byte_replayed \| address_only \| typed_absence`. Shared JSON field names. |

---

## 2. Objects E1 must emit (minimum)

Schemas live in code E1 will add under `engine/company_intelligence/` as frozen dicts, not a new parallel tree. Names:

| Object | Schema name | Required fields |
|---|---|---|
| Event | `company_event.v1` | `event_id`, `company_id`, `security_ids`, `fiscal_period`, `event_type=earnings_results`, `lifecycle.state`, `observed_at`, `source_available_at`, `authority=context_only` |
| Fact | `event_fact.v1` | `fact_id`, `event_id`, `metric`, `value`, `unit`, `period`, `basis` (`gaap\|adjusted\|unknown`), `source_span` or `typed_absence` |
| Metric delta | `metric_delta.v1` | `metric`, `current`, `prior`, `consensus` (or typed absence), `basis_match: bool`. If `basis_match` is false, **no beat/miss**. |
| Guidance item | `guidance_item.v1` | `metric`, `low`, `high`, `unit`, `horizon`, `status` (`introduced\|reiterated\|raised\|cut\|withdrawn\|absent`) |
| Event claim | `event_claim.v1` | `claim_id`, `text`, `speaker?`, `evidence_spans[]` or `typed_absence`, `kind` (`quote\|numeric\|guidance\|other`) |
| Compact payload | `event_workspace.v1` | See §4 |

Q&A exchange, management commitment, narrative change, market reaction: **declared for E2 display**.

| Object | E1 | E2 |
|---|---|---|
| `qa_exchange.v1` | optional empty list | may render count + “open transcript”; no fake exchanges |
| `management_commitment.v1` | omit | empty honest state |
| `narrative_change.v1` | omit | empty honest state |
| `market_reaction.v1` | omit or `not_joined` | E2 may join PIT windows **display-only** if cheap; otherwise `not_joined` chip |

---

## 3. Citation, correction, clocks, authority

- **Per-claim receipts.** Event-level `claim_citations_pending` becomes **derived** on v2 (`any(claim has no receipt)`). v1 contexts must still store `true` (corpus invariant). Do not silently upgrade document-level lineage to span-level (typed absence is the compliant answer).
- **Correction.** New `source_sha256` → document revision → event `corrected` → compact payload `generation_id` changes → Wire, dossier, Terminal, Brain that consume v2 **must** rebuild or show corrected. Identity unchanged.
- **Clocks.** Every transition carries `observed_at` and `source_available_at`. A transition observed before its source was available is refused.
- **Health enum (Q5):** `ready \| degraded \| stale \| partial \| blocked_rights \| empty`. `blocked_rights` remains non-mintable until a rights registry exists.
- **Authority:** `context_only`. Compact payload must include `may_rank=false`, `may_size=false`, `may_gate=false`, `prophet_authority=false`.

---

## 4. Compact event workspace payload (`event_workspace.v1`)

One JSON object E1 writes and E2 reads. No second interpretation on the Terminal.

```
event_id                  canonical
aliases                   [cie_…, TICKER/YYYYQn, slug]
issuer                    {company_id, display_name, listings[]}
fiscal_period
lifecycle                 {state, observed_at, source_available_at}
completeness              {release, filing, transcript, slides, consensus, reaction}
facts[]                   event_fact.v1
deltas[]                  metric_delta.v1
guidance[]                guidance_item.v1 or []
claims[]                  event_claim.v1
sources[]                 documents + receipt_state
warnings[]                closed vocabulary
generation_id
generated_at
authority                 context_only
prophet_flags             all false
```

E2 may not fetch CI v1 overlay as the glance once this payload exists for the event.

### 4.1 Frozen production publication / read contract

This is a binding of the **existing** Company Intelligence publication chain, not a new store.

**Why the payload is a sibling object, not a v1 context field.** `company_intelligence_context.v1` is a closed public wire (`engine/company_intelligence/contracts.py`). `validate_context` refuses unknown keys; `validate_manifest` accepts only `companies/{TICKER}.json` and requires `len(files) == company_count`. Stuffing `event_workspace.v1` into that object would either break the teaser contract or silently invent a parallel schema. Additive evolution stays in a new object with a new reader, as that module already requires.

**Writer (existing discipline, nested under the same product prefix).**

| Piece | Frozen value |
|---|---|
| Product prefix | R2 / local root `company_intelligence/` — same prefix `write_generation` already publishes |
| Workspace nest | `company_intelligence/event_workspaces/` |
| Marker (last) | `event_workspaces/manifest.json` |
| Immutable generation | `event_workspaces/generations/{generation_id}/manifest.json` |
| Object | `event_workspaces/generations/{generation_id}/workspaces/{canonical_event_id}.json` |
| Writer | `engine.company_intelligence.event_workspace.write_workspace_generation` — marker last, content-addressed `generation_id`, refuse in-place mutation of an immutable generation |
| Not the writer | `views.write_generation` (v1 teaser only). Do not reopen that closed files map. |

**Reader (the real E1 consumer; a golden JSON fixture is not one).**

| Piece | Frozen value |
|---|---|
| Real production reader | `engine.neuralweb.company_intelligence_reader.read_event_workspace` |
| Chain | public HTTPS origin → marker → immutable generation manifest → hash-verify workspace object → return the full `event_workspace.v1` |
| Origin | same operator-controlled `COMPANY_INTELLIGENCE_R2_BASE_URL` family as the existing reader (`…/company_intelligence`), then the `event_workspaces/` nest |
| Alias resolution | `event_id_adapter` before fetch: `cie_…`, `TICKER/YYYYQn`, and the public slug all resolve to `evt_cik…` |
| Correction proof | same canonical `event_id`; new `generation_id`; reader returns the corrected generation (marker advanced) |
| Not a consumer | `GET /api/company-intelligence/{ticker}` (bounded v1 teaser) |
| Not a consumer | `read_company_intelligence` (teaser projector; `claim_citations_pending` stays `true` on v1 events) |
| Not a consumer | a golden JSON fixture used *as* the observer. Fixtures may pin expected bytes; they do not satisfy E1 done. |

Local tests wire the reader the same way `tests/test_company_intelligence_neural_reader.py` already does: `write_workspace_generation` to a temp tree, monkeypatch `_fetch_bytes` / origin, then call `read_event_workspace`. That is the production adapter under test, not a second architecture.

If E1 discovers that this nest cannot be published without inventing a second product prefix, a second marker-last family, or a mutation of the closed v1 context/manifest — **stop and escalate**. Do not invent a parallel store.

See `DEC:EARNINGS-EVENT-WORKSPACE-PUBLICATION-CONTRACT`.

---

## 5. Flagship event

**AAPL FY2026 Q3** · call 2026-07-30 · live alias `cie_98e318c37ec1a2a1f83c45e1` · canonical `evt_cik0000320193_2026q3_results`.

**E1 success** = this event bound from issuer identity + 8-K Item 2.02 / Exhibit 99.1 + existing transcript through canonical `evt_cik0000320193_2026q3_results` → `event_workspace.v1` on the frozen path in §4.1 → `read_event_workspace` observes the generation and a source-SHA correction (same event id, new `generation_id`, lifecycle `corrected`). No UI.

**E1+E2 arc success** = that payload rendered into **one** Terminal Brief and **one** dossier module, with correction replay through those surfaces. Do not label Brief + dossier as E1 done.

---

## 6. Files E1 may touch

```
engine/company_intelligence/events.py          (use, do not fork)
engine/company_intelligence/identity.py
engine/company_intelligence/event_id_adapter.py
engine/company_intelligence/documents.py
engine/company_intelligence/resolution.py      (derived pending)
engine/company_intelligence/event_workspace.py (new: schema + write_workspace_generation)
engine/neuralweb/company_intelligence_reader.py (add read_event_workspace only; do not widen the v1 teaser)
engine/earnings_narrative/                     (bind release facts; do not replace Wire grammar)
collectors/edgar_earnings_8k.py                (accession already present — join, don't re-scrape)
tests/test_company_intelligence_*.py
tests/fixtures/company_intelligence/           (add AAPL live fixture; do not rewrite synthetic CIKs)
```

E1 may **not** touch: Terminal UI, dossier JS glance copy as the source of truth, Stage, Prophet rank path, Group Reads, TIL, slides OCR, search index, `config/mastermind_programs.yml` (ownership follow-up is a later docs/registry PR), `views.write_generation`, `validate_context` / `validate_manifest` closed v1 maps, `app/company_intelligence.py`.

## 7. Files E2 may touch

```
terminal/ components for Company Intelligence lenses (Brief, Sources, EvidenceRail)
Macro dossier module that *reads* event_workspace.v1
tests / e2e for the six frozen interactions
```

E2 may **not** ship Command Center, Peers, Slides, global search, or cited long-form analysis.

---

## 8. Later graph seams (do not freeze in code now)

- `relationship_edge.v1` → E7
- `earnings_wave.v1` / read-through hypothesis → E8
- residual co-movement join → E9
- `slide_region` receipts → E10
- Neural Web event graph packet → E13
- four-target catalyst ledger → E14

---

## 9. Handoffs

- E1: `research/earnings_intelligence/E1_IMPLEMENTATION_HANDOFF.md`
- E2: `research/earnings_intelligence/E2_IMPLEMENTATION_HANDOFF.md` (blocked on E1)
