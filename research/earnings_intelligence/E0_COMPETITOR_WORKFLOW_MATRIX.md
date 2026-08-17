# E0 Competitor Workflow Matrix

**Wave:** E0 · **Verified:** 2026-08-16  
**Direct inspection this session:** Mastermind live Wire, CI API, dossier contract.  
**Competitor jobs:** current teardown dockets (2026-07-31 / 2026-08-01) remain the last OBSERVED competitor walkthroughs. Quartr Pro / EarningsCall.ai / Jodie / Struct paywalled product was not re-authenticated this session. Where a teardown is the only source, the row is labelled `TEARDOWN`. A job is never marked done because “we have search/AI/themes.”

Verdict vocabulary: `COPY_JOB` · `ADAPT` · `DEFER` · `REJECT`.

Mastermind current state uses the E0 ledger states.

---

## 1. Quartr — institutional primary-source workflow

| Job | Entry | User task | Sequence | Data required | Output shape | Evidence behavior | Persist / alerts | Likely engine | Mastermind now | Mastermind upgrade | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Event summary | Company → event | Understand the print in minutes | Event page enriches as documents arrive | Release, transcript, slides, estimates | Structured summary + source tabs | Page/paragraph citations | Watchlist | Event + document graph | Wire is source excerpts, not a summary; CI summary is overlay prose with `claim_citations_pending` | E1 facts + E2 Results/Guidance/Narrative from the same event | COPY_JOB |
| Global search | App chrome | Find a phrase anywhere | One box, provider-health chips | Transcripts, filings, slides | Ranked hits → exact open | Span/page | Saved searches | Corpus index | Terminal ticker-scoped transcript search only; Macro none | E5 | COPY_JOB |
| Transcript search | Event or global | Speaker / Q&A filtered retrieval | Filter → hit → reader | Revisioned bodies | Segment + span | Exact | Highlights | Full-text + speaker tags | PARTIAL: in-call filters live; cross-call is event-only | E5 deepen | ADAPT |
| Slide search / history | Event → Slides | Find a chart; compare decks | Search → page → family history | Page images + OCR + family ids | Page + region | Page-region receipt | Key Slide tags | OCR + family matcher | SPEC_ONLY | E10 | DEFER (after E1/E2/E5) |
| Topics | Event / company | What analysts pressed | Topic row → exchanges | Structured Q&A | Topic cluster | Span-backed | — | Clustering over exchanges | CI Topics = tag timeline, not Q&A | E6 | COPY_JOB |
| Mentioned By | Company | Who named us | Inbound mention list | Entity graph | Event + span | Exact | — | Entity resolution | Forced empty `issuer_mentions` | E7 | COPY_JOB |
| AI chat with sources | Split view | Ask, land on source | Question → cited turns | Claim ledger | Answer + locator chips | Same grammar as Brief | Workspace | Retrieval over claims | Ask Mastermind opens Brain; no locator chips | E2 then E13 | ADAPT |
| Calendar / watchlists / alerts | Chrome | What prints this week for my names | Calendar + keyword alerts | Event lifecycle + rights | Calendar + notifications | Correction-aware | Yes | Event store + notifier | Watchlist “next earnings”; no CI calendar; no keyword alerts | E5 | COPY_JOB |
| Split-view research | Event workspace | Doc + chat / two docs | Persistent rail | Documents + claims | Dual pane | Citations stay on screen | Workspace | UI over one event | Desktop evidence **rail** yes; dual-doc split no | E2 | ADAPT |
| Exports | Event | Take evidence | Export with ids | Claims + rights | PDF/CSV/clip | Retain event/source/claim ids | — | Projection | Private record API; no CI export | E12 | ADAPT |

---

## 2. EarningsCall.ai — analysis and corpus reuse

| Job | Entry | User task | Sequence | Data required | Output shape | Evidence | Persist | Likely engine | Mastermind now | Upgrade | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Analysis views | Event tabs | Highlights, guidance, strategy, Q&A, risk | One extraction → many views | Transcript (+ release) | Tabbed analysis | Often uncited aggregate | — | One-prompt-per-tab (do **not** copy) | Wire excerpts; CI overlay summary | One extraction contract, many evidence-grounded views (E3) | ADAPT |
| Historical / peer analysis | Company / peer set | This print vs history / peers | Compare table | Multi-event claims | Table + charts | Should be cited | — | Compare projection | Stage QoQ scores; no IR peers | E2 history; E8 peers | ADAPT |
| Chat | Company / cross-company | Ask the corpus | Chat | Same store | Prose | Often weak citations | — | RAG | Brain compact context | Cited chat over claim ledger | ADAPT |
| Weekly intelligence | Public / email | Week’s pattern | Compile | Event catalog | Brief | Source-first weekly is live | RSS | Catalog aggregate | PROVEN_LIVE transcript weekly | Keep; add non-transcript later | ADAPT |
| Topic tracker | Theme / keyword | Follow a debate | Monitor | Topics + alerts | Tracker | — | Alerts | Topic index | NOT_BUILT | E5 + E6 | COPY_JOB |
| Alerts | Keyword | Ping on phrase | Subscribe | Index | Notification | Correction-aware | Yes | Notifier | NOT_BUILT | E5 | COPY_JOB |
| Programmatic event pages | SEO | Public event URL | Publish | Admitted packet | Article | Wire is live, source-first | Sitemap | Public compiler | PROVEN_LIVE 3361 records | Keep as evidence/acquisition; do not turn into uncited analysis | ADAPT |

**Reject:** one-prompt-per-tab architecture and uncited aggregate prose (`masterplan §2.2`).

---

## 3. Jodie / Struct — groups, relationships, compiler

| Job | Product | User task | Mastermind now | Upgrade | Verdict |
|---|---|---|---|---|---|
| Market-neutral groups | Jodie | Residual co-movement after beta | Crowding / residual exists; **not** earnings-joined | E9 join only | ADAPT |
| Lifecycle / lineage | Jodie | Theme birth → fade | TIL owns theme lifecycle | Consume TIL; do not rebuild | REJECT (duplicate TIL) |
| Group participation | Jodie | Breadth / spread / weakening | Group Reads PROVEN_LIVE | Consume | REJECT (duplicate Group Reads) |
| Relationship map | Jodie | Customer/supplier/competitor | `group_linked_outsiders` dark (0 edges); digest empty | E7 | COPY_JOB |
| “What changes next” monitor | Jodie | Next condition, not a score | Group Reads next-condition copy exists in doctrine | E8 falsifiers on the wave object | ADAPT |
| Moving Together | Struct | Who is moving with whom | Group Reads sympathy | Consume; do not clone the page | ADAPT |
| Filing Read | Struct | Filing → structured cards | Filing Forensics / Calcbench program (separate) | Consume; do not rebuild inside Earnings | REJECT (wrong program) |
| Supply Chain | Struct | Customer/supplier cards | Empty relationship_updates | E7 | COPY_JOB |
| Daily Radar | Struct | Today’s structured packet | No earnings radar | Command Center is E11; Live Entry Radar is a different organ | DEFER |
| Story → live product route | Struct | Public story continues in product | Wire → dossier / Terminal deep links **live** | Keep; bind to canonical event | ADAPT |

**Reject:** a second theme engine, a second basket engine, a second Filing Forensics, a standalone EarningsCall.ai app.

---

## 4. EquityDesk — already in-house as Stage

| Job | Mastermind now | Verdict |
|---|---|---|
| Per-call table with scores / tags | Stage PROVEN_LIVE | ADAPT (calibration/migration only; not live CEI authority) |
| QoQ / season raiser-decliner | Stage PROVEN_LIVE | Consume |
| Industry heatmap | Stage PROVEN_LIVE | Consume |
| Live dependency on Stage scores for CI glance | CI `score_overlay` summaries | **Do not** keep as the E2 glance once E1 claims exist |

---

## 5. Jobs Mastermind already wins and must not rebuild

| Job | Evidence |
|---|---|
| Receipt-bound public transcript archive | Live Wire 3361 records, 0 model calls, byte tables |
| Entitlement-gated full record | Member gate; private `/api/earnings/v1/records/{slug}` |
| Stage season analytics | Health `ready`, 50,982 rows |
| Group Reads earnings pulse | `group_earnings.py` + basket UI |
| Terminal transcript reader | Revisioned bodies, in-call filters |
| Context-only authority fence | Every CI payload `authority: context_only`; Prophet flags false |

---

## 6. Fidelity gate (Gate 5)

“We already have search / AI / themes” is **not** accepted for:

- global search (ticker-scoped ≠ global)
- Topics (tag chips ≠ Q&A topics)
- Mentioned By (empty list)
- cited chat (Brain without locator chips)
- event summary (overlay prose ≠ source-bound Results/Guidance)
