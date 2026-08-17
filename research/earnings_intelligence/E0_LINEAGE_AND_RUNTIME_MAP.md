# E0 Lineage and Runtime Map

**Wave:** E0 · **Verified:** 2026-08-16 · **Production mutation:** none

Three real events were traced. Identifiers are **not** shared across planes today. That mismatch is assigned to E1 (`Gate 3`).

```
source discovery
 -> raw storage
 -> normalization
 -> evidence generation
 -> extraction / score
 -> company context
 -> public wire
 -> dossier
 -> Terminal
 -> Neural Web / Brain
 -> Stage / Prophet
```

---

## 1. Identity schemes in force (do not collapse in prose)

| Plane | Identifier | Shape | Keyed on | Live? |
|---|---|---|---|---|
| Company Intelligence v1 | `stable_event_id` | `cie_` + sha256(`TICKER\|YEAR\|Qn`)[:24] | listing | Yes |
| Earnings narrative | `event_key` | `TICKER/transcript_id` e.g. `IEX/2026Q2` | listing + transcript | Yes |
| Public Wire slug | `wire_slug` | `{ticker}-{transcript_id}-call-record` | listing + transcript | Yes |
| Canonical spine (library) | `canonical_event_id` | `evt_cik0000320193_2026q3_results` | issuer + fiscal period | Built, not the live mint |
| Alias adapter | `event_id_adapter` | maps `cie_` and `TICKER/YYYYQn` → canonical | both | Built, not driving publication |

`call_date` is accepted and **not hashed** (`contracts.py:202-206`). Correction of the calendar date does not fork `cie_`. Dual class still forks because the ticker is in the hash.

---

## 2. Event A — healthy Wire record, stale CI (LMND)

**Job:** recent healthy transcript event that actually published.

| Field | Value | Source |
|---|---|---|
| Issuer | Lemonade Inc | Live Wire 2026-08-16 |
| Listing | `LMND` | Wire + CI |
| Wire period | Q2 FY2026, call 2026-07-29 | `https://www.mastermind-x.com/stocks/earnings/` card + `lmnd-2026q2-call-record.html` |
| CI `latest_event` | Q1 FY2026, call 2026-04-29, `cie_cc4a20429454459f3b390d4f` | `GET /api/company-intelligence/LMND` 2026-08-16T06:55:37Z |
| Citation on Wire | Exact UTF-8 spans | Public: claim `claim_6af24d284313b106ae256948f8a47f62` segment 8 bytes 241–370; 29 numeric receipts, 41 bound spans |
| Citation on CI | `claim_citations_pending: true`; transcript `citation_precision: "document"` | Same API |
| Release / 8-K / slides / consensus / reaction | Disclosed absent on Wire | Rail: “No release, filing, slides, consensus, or price-reaction join is implied here.” |

### Edge trace

| Edge | Identifier | Freshness | Citation | Authority | Failure / state | Consumer |
|---|---|---|---|---|---|---|
| Discovery → raw | Terminal `LMND/2026Q2` body | Index generated_at on packet | Body SHA-256 | context_only | — | Evidence catalog |
| Raw → evidence | narrative `event_key` | Packet generation | Span receipts | context_only | Transcript-only completeness **forced** | `public_wire.py:396-400` |
| Evidence → Wire | slug `lmnd-2026q2-call-record` | Live page 2026-08-16 | Exact | context_only | Member gate after 2 public excerpts | Public archive |
| Evidence → CI | `cie_cc4a20429454459f3b390d4f` | CI generated_at 2026-08-16 but **latest is Q1** | Metadata / document | context_only | CI did not advance to the Q2 Wire event | Dossier / Terminal / API |
| CI → dossier | ticker `LMND` | Same | Pending | context_only | Summary from `score_overlay` | Stock page |
| CI → Terminal | BFF `/api/company-intelligence/LMND` | Same | Pending | context_only | Brief cannot open a span | Analysis intelligence |
| Evidence → Brain | compact excerpts | Private R2 | URL + sha | context_only | Not the Q2 Wire claim set unless the packet caught up | Brain |
| → Stage / Prophet | Stage scores / post-select context | Stage health latest call 2026-08-07 | Scores, not spans | context_only; Prophet flags false | Split-brain residual: `earnings_call_sent` | Stage; Prophet annotation |

**Verdict:** the healthiest live path is Wire-only. Company Intelligence, dossier, and Terminal Brief are a **different, older event** for the same ticker on the same day.

---

## 3. Event B — flagship mega-cap, CI present, Wire missing (AAPL Q3 FY2026)

**Job:** the E1 golden event. Partial sources, high product value.

| Field | Value | Source |
|---|---|---|
| Issuer | Apple Inc | Live CI |
| Listing | `AAPL` | `GET /api/company-intelligence/AAPL` |
| CI event | `cie_98e318c37ec1a2a1f83c45e1` · FY2026 Q3 · call 2026-07-30 | Same, `generated_at` 2026-08-16T06:55:37Z |
| Canonical target | `evt_cik0000320193_2026q3_results` | `events.py:187` example is this exact shape |
| Status | `partial` | API |
| Summary (score_overlay, not span-cited) | “The root cause is a demand forecast issue, where the iPhone and Mac are doing remarkably better than we thought they would do.” | API `field_lineage.summary: score_overlay` |
| Glance facts in CI (history, not 8-K bound) | June-quarter revenue $109.4B (+16% YoY); iPhone +22%; Mac +29%; Services $30.7B (+12%); Q4 supply constraints “increase significantly sequentially”; memory costs “100-year flood”; FX −2.5 ppt sequential growth headwind | `positive_highlights` / `negative_highlights` |
| Metrics | `revenue_growth_pct` 16, `eps_growth_pct` 29, `gross_margin_pct` 50.1, `questions_count` 14 | `earnings_history` |
| Sources | history `metadata_only`; score_overlay `metadata_only`; transcript `present` / `document` | API `sources[]` |
| Public Wire | **404** `aapl-2026q3-call-record.html` | Fetched 2026-08-16 |
| `claim_citations_pending` | `true` | API |

### Edge trace

| Edge | Identifier | Freshness | Citation | Authority | Failure / state | Consumer |
|---|---|---|---|---|---|---|
| Discovery | Calendar + 8-K Item 2.02 (marketing lane, not CEI) | Calendar coverage degraded (17.9% SLA) | Accession on 8-K collector; CI has no accession | context_only | CEI filing `not_ingested` | Marketing wire ≠ dossier |
| Raw transcript | Terminal `AAPL/2026Q3` implied by CI `transcript: present` | CI sees document | Document, not span | context_only | Not admitted to public Wire (404) | Terminal reader likely; Wire no |
| Score overlay | Qualitative / EquityDesk-style history | Overlay generation | Metadata | context_only | This is what the dossier *says* | Dossier glance |
| CI context | `cie_98e318c37ec1a2a1f83c45e1` | 2026-08-16 | Pending | context_only | `untrusted_source_data: true` | API, dossier, Terminal |
| Public Wire | slug would be `aapl-2026q3-call-record` | Missing | — | — | Admission/evidence-policy hold or unpublished | Public archive |
| Dossier | ticker `AAPL` | Same CI | Pending; UI can show “Wording not yet checked” | context_only | Glance is overlay prose | Stock page |
| Terminal | Brief + Sources | Same | Metadata / document | context_only | Exact open only via transcript search, not Brief | Analysis |
| Brain | Compact packet if generated | Private | Excerpt receipts if admitted | context_only | Not a structured AAPL event packet | Brain |
| Stage / Prophet | Season scores; post-select context | Stage ready | Scores | context_only | Must not rank/size/gate | Stage; Prophet |

**Verdict:** AAPL is the right E1 event because the user-visible story already exists and is **not** source-bound. E1’s job is to bind issuer + 8-K/Exhibit 99.1 + transcript + exact claims into `evt_cik0000320193_2026q3_results` and one compact payload. The Wire 404 is a consumer gap, not a reason to pick a less important name.

---

## 4. Event C — identity / dual-class (GOOGL Q2 FY2026)

**Job:** difficult identity. Dual-class must not mint two issuer events.

| Field | Value | Source |
|---|---|---|
| Issuer | Alphabet Inc | Live CI GOOGL |
| Listing A | `GOOGL` `cie_e7b4b160257b99936851ece0` FY2026 Q2 call 2026-07-22 | `GET /api/company-intelligence/GOOGL` 200 |
| Listing B | `GOOG` | `GET /api/company-intelligence/GOOG` **404** |
| Glance | Cloud +82% to $24.8B; backlog $514B; CapEx $195–205B; FCF −$5.9B | CI highlights |
| Citations | `claim_citations_pending: true` | API |
| Canonical target | One `evt_cik0001652044_2026q2_results` (real Alphabet CIK; corpus CIKs are **synthetic** and must not be used in production) | Freeze Q1 |

### Edge trace

| Edge | What happens | Failure |
|---|---|---|
| Identity | Live mint hashes `GOOGL\|2026\|Q2` | `GOOG` is a different listing and currently has **no CI object at all** |
| Adapter | `aliases_for` can mint one canonical + N `cie_` keys | Not on the live builder |
| Wire | Not traced to a live GOOGL article this session | Do not assume Wire coverage from CI presence (AAPL counterexample) |
| Group Reads / TIL | Must consume this as one issuer | A second GOOG event would inflate breadth — Freeze Q1 forbids it |

**Verdict:** production identity is still listing-keyed and incomplete. E1 must resolve AAPL (single class) first; GOOGL/GOOG is a required golden *acceptance* case for the adapter, not the first vertical slice.

---

## 5. Control — Wire-healthy industrial with structured-looking guidance (IEX)

Not one of the three required traces, but the live control for “exact receipts already work”:

- `https://www.mastermind-x.com/stocks/earnings/iex-2026q2-call-record.html`
- Quote claim `claim_08e3f9dfdc802b94cb7c06618d54069e` segment 18 bytes 0–142: “For the third quarter of 2026, we expect 5%-7% organic growth, adjusted EBITDA margin in the 27%-27.5% range, and adjusted EPS of $2.20-$2.25.”
- 33 numeric receipts, 45 bound spans
- Still transcript-only; guidance is a quote, not `guidance_item.v1`

Use IEX as the **receipt-grammar fixture**. Do not make it the flagship E1 product event.

---

## 6. Runtime clocks (do not mix)

| Clock | Artifact | As-of this session | Honest read |
|---|---|---|---|
| Public Wire catalog | Live index | 3361 admitted; weekly 2026-07-27→08-02 | Transcript-excerpt archive is live |
| CI builder | API `generated_at` | 2026-08-16T06:55:37Z | Builder ran today; **latest_event can still be a prior quarter** |
| Stage / import health | `data/quality/earnings_intelligence_health.json` | `ready`, latest call 2026-08-07, age_days 7 | Score/history plane, not Wire |
| Calendar freshness | `data/quality/earnings_freshness_audit.json` | `ok: false`, 17.9% coverage | Presence-vs-coverage trap; newest stamp looks fresh |
| Golden corpus CIKs | `golden_corpus_issuers.v1.json` | `cik_synthetic: true` | **Unusable as production `company_id`** |

---

## 7. Correction behavior

| Layer | What a new source SHA does today | What E1 must prove |
|---|---|---|
| Narrative story | Supersedes revision; Wire can show “Corrected source revision” | Same |
| `cie_` identity | Unchanged (call_date unhashed) | Preserve |
| CI dossier | Independent rebuild from history/overlay | Must invalidate or rebuild from the canonical event |
| Terminal Brief | Follows CI | Follows CI |
| Public Wire | Separate admission | Same canonical event + correction_status |
| Brain packet | Separate generation | Compact payload generation id must change |

---

## 8. Gate 3 statement

The same golden event **cannot** yet be traced across Macro and Terminal under one id.

- Macro Wire uses `ticker + transcript_id` slugs.
- Macro/Terminal CI uses `cie_` from ticker + fiscal period.
- Canonical `evt_cik…` exists only in the library.

E1 owns the adapter going live for **one** event (AAPL Q3 FY2026). E2 may not invent a second id.
