# DeepVue W1-C `ai_context_envelope.v1` contract freeze

Status: implementation contract for the bounded W1-C carrier (visible context
compiler + effective-context receipt). This document does not authorize W2,
workspace schema, semantic link groups, screener, ratings, alerts, Prophet or
Fusion work, a persistent context store, or any latency change to the quote
owner waterfall.

## Pinned boundary

- Commission: Sol → Fable COO, W1-C only, `WS:DEEPVUE-INTELLIGENCE-WORKSPACE`.
- Protected Sol Skillpack: `51f9942733b86e550bb9169d2a43462bd28e774f`.
- Macro pickup: `origin/main` `2c20168df5d9e711825f7fca5983b4bbab69711d`.
- Terminal pickup: `origin/master` `04f872629db73bb6eae76acba47ced8df53103db`.
- W1-A registry digest (must not drift):
  `7dff09b790f9f789dfeed80781a7fb62bc138ad4bf801d81664d471c4508d4cf`.
- Binding fences: `DNR:KILL-LLM-ORIGINATION`, `DNR:KILL-PUBLIC-INTERNALS`,
  the W1-A architecture freeze (no second registry/resolver/identity/owner/
  rights plane/Brain service/result store/fact cache/retry plane), and the
  W1-B receipt's residual boundary (no cache, no alternate quote owner).
- The compiler is a deterministic, pure resolution layer. The LLM consumes the
  resolved envelope and has zero authority over precedence, identity, facts,
  conflicts, or authority fields.

## Frozen precedence law

```
explicit request  >  pinned context  >  active selection  >  ambient widget context
```

- Effective context = the highest non-empty level after validation. Levels do
  not merge. Lower-level entities not contained in the effective set are
  recorded in `dropped` with reasons, never silently discarded.
- `explicit` entities come only from the user's message text via the existing
  W1-B lexer (`_symbol_candidates` in `engine/neuralweb/native_facts.py`).
  W1-C reuses that lexer; it does not fork a second grammar.
- Multi-explicit is legal in the envelope (effective = all explicit entities).
  The native lane's single-entity law is a lane constraint and is unchanged:
  it engages only when the effective set has exactly one entity.
- Lexer uppercase-ambiguity keeps its W1-B behavior (native lane refuses;
  deep route). The envelope records `context_flags.ambiguous_explicit: true`
  and resolves effective context from the remaining levels for visibility.
- Empty everything → `effective_context.source: "none"`,
  `reason: "no_context"`. This is a distinct state, not an error and not a
  fabricated context.

## Client context block — `ai_context_client.v1`

Carried inside the existing `BrainChatRequest.context` dict under key
`ai_context` (no new top-level request field, no second transport channel;
the async `POST /api/brain/chart/state` mirror is out of scope and carries no
per-request authority):

```json
{
  "schema": "ai_context_client.v1",
  "origin_id": "opaque string ≤64 chars, unique per widget mount",
  "context_revision": 7,
  "captured_at": "RFC3339",
  "pinned": [{"type": "security", "id": "NVDA"}],
  "active": {"type": "security", "id": "AAOI"},
  "ambient": {"symbol": "AAOI", "timeframe": "1D", "page": "terminal", "panel": null}
}
```

- `pinned` is bounded at 3 entries. Entity type `security` only in v1; any
  other type is recorded `unsupported_entity_type` and never coerced.
- Symbol validation reuses the exact existing `_context_symbol` admission law
  from W1-B; a non-conforming id is recorded `invalid_symbol` in
  `unsupported`, never guessed.
- Legacy mapping (no `ai_context` key — old dashboard/Terminal clients):
  `active` ← legacy `context.symbol`, `ambient` ← `{page, panel}`,
  `pinned` = [], `origin` = `{legacy: true, context_revision: 0}`. This
  preserves today's explicit-over-ambient behavior byte-for-byte in meaning.
- Privileged fields (`effective_context`, `authority`, `field_requests`,
  `datapoints`, `latency_lane`, or any `_server`-prefixed key) appearing
  inside `ai_context` are stripped and recorded in
  `context_flags.rejected_fields`. Unknown non-privileged keys are ignored
  and recorded in `context_flags.ignored_fields`. The two classes stay
  distinct.
- A malformed block (wrong types, negative/non-int revision, oversized
  origin_id, non-list pinned, >3 pins) rejects the whole `ai_context` block:
  `context_flags.malformed: true` with a reason code, and compilation
  proceeds from the legacy fields. Never a 500, never a silent success.
- Ambient string fields (`symbol`, `timeframe`, `page`, `panel`) are
  validated: strings ≤32 chars; non-conforming values (wrong type, oversized,
  or matching the subscriber leak law) are nulled and the condition recorded
  in `context_flags.echo_sanitized` (review amendment). Echoed
  `unsupported[].entity` strings are length-capped (≤64 chars) and leak-
  screened the same way; a non-conforming value there is replaced by a safe
  placeholder rather than nulled, because an `unsupported` row exists
  specifically to name what was rejected.

## Canonical envelope — `ai_context_envelope.v1` (server-compiled only)

```json
{
  "schema": "ai_context_envelope.v1",
  "request_id": "uuid",
  "origin": {"origin_id": "…", "context_revision": 7, "captured_at": "…", "legacy": false},
  "explicit_entities": [{"type": "security", "id": "INOD"}],
  "pinned_context": [],
  "active_selection": [{"type": "security", "id": "AAOI"}],
  "ambient_widget_context": {"symbol": "AAOI", "timeframe": "1D", "page": "terminal", "panel": null},
  "effective_context": {
    "entities": [{"type": "security", "id": "INOD"}],
    "source": "explicit",
    "reason": "explicit_request",
    "precedence": "explicit_over_active"
  },
  "dropped": [{"entity": {"type": "security", "id": "AAOI"}, "level": "active", "reason": "outranked_by_explicit"}],
  "unsupported": [],
  "context_flags": {"stale": false, "malformed": false, "malformed_reason": null,
                     "ambiguous_explicit": false, "rejected_fields": [], "ignored_fields": [],
                     "echo_sanitized": false},
  "field_requests": [],
  "latency_lane": "instant_fact",
  "provenance_requirement": "field_level",
  "authority": {"may_execute": false, "may_originate_signal": false}
}
```

- Frozen `effective_context.source` vocabulary: `explicit | pinned | active |
  ambient | none`.
- Frozen `reason` vocabulary: `explicit_request`, `explicit_entity_wins`
  (explicit beat a differing lower level — preserves the exact W1-B string),
  `pinned_context`, `active_selection`, `ambient_context` (preserves the
  W1-B string), `no_context`.
- Frozen `dropped[].reason` vocabulary (review amendment): `outranked_by_explicit`,
  `outranked_by_pinned`, `outranked_by_active`. `invalid_symbol` and
  `unsupported_entity_type` never appear here — those are `unsupported[]`
  reasons (below); a `dropped` row exists only for a VALID lower-level entity
  that a higher level outranked.
- Frozen `unsupported[].reason` vocabulary (review amendment): `invalid_symbol`,
  `unsupported_entity_type`, `invalid_entity_shape` (the raw client value was
  not even a `{type, id}` mapping).
- Frozen `effective_context.precedence` vocabulary (review amendment, NB-3):
  `explicit_over_pinned`, `explicit_over_active`, `explicit_over_ambient`,
  `pinned_over_active`, `pinned_over_ambient`, `active_over_ambient`,
  `explicit_only`, `pinned_only`, `active_only`, `ambient_only`, `none`.
  Names the HIGHEST lower level that actually lost an entity in this compile
  (e.g. two pins where only the second was outranked by an explicit request
  still reads `explicit_over_pinned`, never a blanket `explicit_over_active`
  regardless of what was really dropped); `<source>_only` when the winning
  source had nothing beneath it to outrank.
- `authority` is constant and server-set. A client can never raise it.
- The compiler performs no I/O, no identity admission, no owner reads.
  Identity admission (symbol → `SEC:*`) remains exclusively W1-A's
  normalizer via the existing native-facts path; the envelope carries edge
  symbols, and canonical identity appears only in the native-fact receipt
  where it already lives today.

## Stale law

- `context_stale_budget_seconds = 900`, a compiler constant.
- A `captured_at` older than the budget at compile time marks
  `context_flags.stale: true`. Precedence is unchanged — a selection does not
  rot — but staleness is mandatorily visible in the receipt and UI.
- Fact-level staleness is unchanged W1-A owner-clock law and stays in the
  native-fact receipt (`earnings.next_date` stale states, etc.). The
  inspector must display fact `status`/`as_of` from that receipt.
- Transport/materialization time never freshens anything: a replayed or
  resumed receipt keeps its original `captured_at`, `context_revision`, and
  fact clocks verbatim.

## Revision and origin law (loop prevention)

- `origin_id`: opaque, ≤64 chars, minted once per widget mount.
- `context_revision`: non-negative integer, monotonic per `origin_id`,
  incremented exactly once per logical context transition (user action or
  bus-driven context change), not per request. Consecutive sends with
  unchanged context reuse the current revision.
- The gateway is stateless across requests with respect to revisions: it
  echoes `origin` verbatim into the envelope and receipt. Monotonicity,
  dedupe, and ordering are client duties, test-proven:
  - a receipt is applied to the live strip only when its `origin_id` matches
    the current mount and its `context_revision` ≥ the last applied revision;
    anything else renders as historical (inspector), never as current state;
  - a duplicate of the same `(origin_id, context_revision)` is the same
    logical context event — re-transport must not produce a new UI
    transition;
  - one UI symbol/timeframe/pin event produces exactly one revision increment
    and at most one strip transition; receipts and `chart/state` mirror acks
    must never feed back into the bus as new context events.
- Resume: the run event log persists the receipt; `GET /api/brain/runs/{id}/
  stream` replays it verbatim, so a resumed run keeps its original effective
  context by construction and never recompiles from moved UI state.

## Receipt — `ai_context_receipt.v1`

- New first-class SSE event, emitted for **every routed** Brain run — a run
  that passes message/quota/prescreen admission and reaches lane routing;
  early refusals (empty message, research-mode rejection, quota exhaustion,
  prescreen block) precede context consumption and carry no receipt (review
  amendment) — after `meta` and before any `delta`/`tool` event:
  `{"type": "context_receipt", "schema": "ai_context_receipt.v1", …}` whose
  body is the envelope minus `field_requests` (which stays in the
  native-fact receipt) — context resolution only.
- The non-streaming `chat()` response carries the same object under
  `context_receipt`.
- The event is appended to the run's persisted event list so replay/resume
  return it unchanged.
- Subscriber safety: the receipt contains only edge symbols, entity types,
  reason codes, revisions, timestamps, and lane labels — never repository
  paths, artifact paths, private source locations, credentials, or internals.
  Tests must assert this with the same private-text regex law the W1-A
  subscriber projection uses (`_PRIVATE_SUBSCRIBER_TEXT`).
- Fact-level parity surface: the existing `brain.native_fact_receipt.v1`
  (identity admission, facts with status/as_of/fingerprint) must reach the
  streaming client and resume path alongside the context receipt; its
  `effective_context` block must be derived from the envelope so the two can
  never disagree.

## Five-fact parity set (frozen)

Wave-1 exit parity is proven over exactly these W1-A fields:

1. `market.price.last`
2. `stage.current`
3. `industry.rank.percentile`
4. `security.industry_member.rs_percentile`
5. `earnings.next_date`

They exercise live-owner identity, owner-artifact facts, relationship-bound
industry rank vs. the non-swappable member-RS twin, and visible staleness.
Parity means identical semantic identity, value, status, as-of, and
fingerprint through (a) a direct resolver call, (b) the Brain native lane
receipt, and (c) Terminal inspection of the same receipt fields.

## Placement and integration (Macro)

- Compiler: `engine/intelligence_workspace/context_compiler.py` — pure
  module at the W1-A layer; imports the explicit lexer from
  `engine/neuralweb/native_facts.py` (one grammar, one compiler).
- Gateway: `chat()`/`chat_stream()` compile the envelope once per request at
  the existing context-consumption point, pass the resolution into
  `plan_native_facts` (which keeps its field grammar and lane law), emit the
  receipt event, and leave the deep lane's prompt construction byte-identical
  to today (the deep path still sees the legacy `context` dict it sees now).
- Contract schema: `ai_context_envelope.v1.schema.json` committed as a
  sibling of the existing datapoint contract schemas (same directory the
  deploy restart regex covers; extend `app/deploy/update.sh` alongside).
- Widget: `templates/mm_brain.js` (+ paired `site/mm_brain.js`, byte-equal)
  renders the effective-context strip and inspector, owns the pin control
  (client-held pin state, no server store), sends `ai_context_client.v1`
  built fresh at send time (Terminal supplies it via a new
  `MM_BRAIN_CFG.getAiContext` hook; the dashboard maps its own `ctxSymbol`
  to `active`).
- CI: new tests join the existing `unrun-brain-gateway` job block in
  `.github/ci/legacy-jobs.yml` (no new job).

## Terminal boundary (separate repo, separate PR, lands second)

Terminal adapts the existing Chart Bus only: an ai-context provider derives
`active`/`ambient` from the same state the bus already owns, mints
`origin_id`, increments `context_revision` exactly once per logical change,
and hands the block to the widget through `MM_BRAIN_CFG.getAiContext`. No
rival bus, no new persistence, no change to chart sync, drawings, replay,
saved layouts, MTF rules, or the Brain proxy allowlist.

## Explicit non-capabilities

No W2 workspace schema, no generic widget graph, no link groups beyond this
minimum Chart Bus adaptation, no Theme Tracker++, no screener, no saved
investigations, no ratings, no alert grammar, no Prophet/Fusion coupling, no
new registry/resolver/identity map/Brain service/rights plane, no persistent
fact or context cache, no alternate quote owner, no quote-waterfall change,
no deep-provider recovery, and no absorption of the W1-B latency residual.
