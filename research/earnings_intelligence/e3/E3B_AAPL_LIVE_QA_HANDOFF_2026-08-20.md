# E3-B — AAPL live Q&A handoff

**Wave:** E3-B · **Date:** 2026-08-20 · **Amended:** 2026-08-21 · **Authority:** `E3_EVENT_INTELLIGENCE_COMPILER_FREEZE_2026-08-20.md`  
**Depends on:** E3-A hard safety gates green **and** the frozen (or Sol-granted) usefulness gate.  
**Do not start from E3-0.** Do not start if E3-A returned to Sol without a usefulness grant.

Not done unless production AAPL Intelligence consumes a **non-empty** accepted `qa_exchanges[]` for `evt_cik0000320193_2026q3_results` in the real Terminal workflow without regressing the E2 event to CI v1.

---

## Mission

Promote validator-accepted `qa_exchange.v1` objects into the existing `event_workspace.v1` `qa_exchanges` list for the live AAPL FY2026 Q3 event. Terminal and the Macro dossier must read those objects. The AAPL source gold contains **seven real exchanges**; completion cannot be an empty list.

## Visible user add

- Terminal Intelligence / Results: structured Q&A (ordered question/answer, questioner plus ordered `respondents[]` when source-supported, closed topic labels with taxonomy version). Stop treating overlay `14` or `facts.questions_count` unstructured absence as the live Q&A once accepted exchanges exist.
- Public glance: analyst questions may move off "unstructured" to an honest count of accepted exchanges. Still no receipts, hashes, beat/miss, or score overlay.

Still forbidden on the surface: evasiveness, answer quality scores, contradictions, peer topics, commitments lifecycle, read-through, sentiment, trading implications.

## Contract to implement

Freeze §7 (`qa_exchange.v1`) and §3 (`event_source_clock.v1` enough that provenance is not `generated_at`). Parent schema stays `event_workspace.v1`. Do **not** add top-level `WORKSPACE_KEYS`. If a top-level key appears necessary, stop and escalate.

Required item shape (do not invent a parallel store):

- revision-scoped `exchange_id` = `qx_{event_id}_{document_sha256[:12]}_{ordinal:02d}`
- ordered `respondents[]` tied to `answer_spans` via `span_indexes`
- questioner name/affiliation independently available; whole-identity absence = `speaker_unresolvable`
- `taxonomy_version` + `taxonomy_hash`
- provenance = extractor/provider/model/prompt/validator/run + clocks + rights. **No** `candidate_id`

Terminal `normalizeSource` currently **strips** unknown nested keys. E3-B must teach Terminal to **read** `clocks: event_source_clock.v1` and to **normalize** `qa_exchanges` items instead of storing `unknown[]`. Extra unknown nested keys must still not hard-fail the workspace.

Macro `validate_event_workspace` must close `qa_exchange.v1` item keys (exact keys, not an open bag). Same for nested `clocks` when present.

Public glance projector stays bounded: no R2 URLs, hashes, or byte locators.

## Cutover law (unchanged)

v2 200 owns the current event. Proven v2 not-covered (`code=event_workspace_not_covered`) → legacy v1. All other v2 failures → unavailable, never stale v1. A model failure must not make AAPL disappear.

## Correction

Same `event_id` + new transcript/release SHA → invalidate affected exchanges → rerun Q&A family only → new `generation_id` with new revision-scoped `exchange_id`s. Do not fork a second AAPL event. Do not pretend ordinal-only IDs survive an inserted/removed exchange.

## Candidate store

Do **not** create a durable candidate database or R2 plane. Accepted production objects must be independently auditable from source spans plus extractor/provider/model/prompt/validator/run provenance. Rejected candidates, if retained, stay in bounded diagnostic/run artifacts.

## Telemetry

Every model rung, including local Qwen and any named fallback, through `lib.ai_costs.record_usage` lane `earnings_event_compiler`. No silent paid fallback.

## Owned files (expected)

- `engine/company_intelligence/event_workspace.py` (validate accepted `qa_exchanges` items)
- `engine/company_intelligence/event_workspace_build.py` (stop hardcoding `[]` once accepted objects exist)
- Compiler/validator module beside them
- Macro glance projector only if questions-state copy must change
- Terminal `terminal/lib/eventWorkspace.ts` + presenter + Intelligence/Results UI
- Tests on both repos pinning AAPL SHAs and LMND remaining v1 fallback

Do not reopen E2-T1 CSS ownership (`#420`). Do not mutate `GET /api/company-intelligence/{ticker}`. Do not edit FIF.

## Stop conditions

**Complete** only if:

- Live AAPL workspace generation advances with a **non-empty** accepted `qa_exchanges[]` that passed the E3-A/Sol usefulness gate.
- Authenticated Terminal AAPL Intelligence at 1440 EN / 820 EN / 390 ZH **renders** those exchanges in the real workflow without overflow or CI console errors.
- Public AAPL dossier does not request `/api/company-intelligence/AAPL`; questions state may show an honest accepted count.
- LMND still falls through on canonical 404.
- Beat/miss still absent. Prophet flags still false. `authority=context_only`.
- Native or explicit-unknown clocks on accepted exchanges; no `generated_at` used as `source_available_at`. Transcript availability is not conference time.

**Honest failure, not completion:** `qa_exchanges=[]`, validator admits nothing, or Terminal does not render accepted Q&A. Empty is representable. It does not close E3-B.

## Out of scope

Second issuer, natural-cycle event, slides, consensus, reaction join, deflection scoring, earnings_qual score schema, FIF-7, durable candidate store.
