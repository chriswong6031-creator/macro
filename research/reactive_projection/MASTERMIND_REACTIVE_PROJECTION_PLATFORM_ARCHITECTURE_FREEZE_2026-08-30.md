# Mastermind Reactive Projection Platform — Architecture Freeze

**Date:** 2026-08-31  
**Parent operation:** `modernize-mastermind-architecture-20260830-sol-001`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Sole R0 carrier:** `sol/reactive-projection-platform-r0-20260830`  
**Pickup base:** `20748fccbb9777f7e43c39acf19499bac4d011be`  
**Protected Sol Skillpack:** `mastermindx-market-intelligence/Mastermind@eccf0a3fae8b8597c2ad0bc4f830e31b220415d2`  
**Status:** **PROPOSED ARCHITECTURE FREEZE / RECORDS_ONLY / PRODUCTION_INERT**

This document resolves the architecture question created by the Chairman's directive that Mastermind-X stop behaving like a once-per-night static publication and become a responsive market-intelligence product. It does **not** install a service, arm a scheduler, change a quote feed, alter ranking, publish a browser bundle, create an Executive Job, or make any live-capability claim.

The architecture is deliberately evolutionary. Mastermind already has valuable canonical systems: nightly engines and ledgers, a Terminal Quote Plane, Macro's API serving tier, static-page progressive enhancement, Prophet-Live, close-pass publication, freshness sentinels, and a governed Agent/Executive operating system. The correct move is to make those systems cooperate through a small projection contract—not to replace them with a second realtime stack.

---

## 1. Executive ruling

Mastermind's responsive product architecture has exactly three semantic layers:

1. **Durable baseline** — the nightly/close-pass generated artifact remains the complete, auditable and correction-safe baseline.
2. **Deterministic live projection** — bounded current observations patch only fields explicitly owned by a live producer, with source time, receipt time, freshness, coverage, revision and correction semantics.
3. **Material intelligence delta** — slower intelligence is recomputed only when a governed materiality rule says the underlying evidence changed enough to matter. No model reruns merely because a quote tick arrived.

The first implementation slice is **R1A — Intelligence Hub Market Pulse**:

> For the names the nightly Intelligence Hub already selected, display current regular-session price and move from the canonical Terminal Quote Plane, update the whole visible pulse atomically, and state freshness/coverage honestly—without changing selection, order, score, stage, Prophet state, intelligence conclusion or trading authority.

R1A is a snapshot projection. Ordered deltas/SSE are a later independently reviewable wave. This is intentional: first prove one useful current-data vertical end to end, then generalize transport only from measured need.

---

## 2. Outcome and 10/10 end-state

### Primary user job

A user opens a Mastermind page during or after the trading session and can immediately distinguish:

- what the durable intelligence system concluded;
- what the market is doing now;
- whether the current layer is genuinely current, delayed, partial, stale or unavailable;
- whether the durable conclusion has been recomputed or is still the last settled baseline.

The user must never mistake a recently fetched stale print for a current market observation, or a current quote for a newly recomputed intelligence verdict.

### Machine/intelligence job

The system must ingest current observations through the existing canonical owner, project only governed fields, preserve source and correction clocks, suppress out-of-order revisions, expose coverage and degradation, and leave all authoritative engines/ledgers untouched until their own cadence or promotion rules run.

### Product moat

The moat is not “websockets.” It is the combination of:

- exact durable evidence and corrections;
- fast deterministic observation;
- explicit distinction between observation and intelligence;
- coherent cross-surface interaction;
- provenance and freshness that are useful rather than ornamental;
- a learning loop that measures whether timely projection improves research and decisions.

### Completion standard

The program is complete only when:

- **Truth:** live observations are source-time honest, correction-safe, rights-safe and fail downward.
- **Intelligence:** current observations and settled conclusions coexist without authority laundering.
- **Product:** flagship surfaces behave coherently across normal and degraded states.
- **Learning:** latency, coverage, correction and user-use instrumentation can show whether the change helps.

---

## 3. Current capability ledger at R0

| Capability | State | Evidence / ruling |
|---|---|---|
| Nightly generated baseline and governed artifacts | `PROVEN_LIVE` | Current Macro pipeline and shipped product |
| Terminal Market Data and Quote Plane | `PROVEN_LIVE` | `mastermind-terminal/hub/`; consumed by shipped Terminal and dossier projection |
| Macro public debranded quote projection precedent | `PROVEN_LIVE` | `app/dossier_quote.py` + dossier surface |
| Generic static-page live-price progressive enhancement | `PARTIAL` | `templates/live.js`; mixed-latency and page-specific coverage |
| Intelligence Hub current price markup | `PARTIAL` | nightly prices may render as `.nb-px`; current page-wide truth not proven |
| Intelligence Hub page-complete Market Pulse | `DARK_OR_DISCONNECTED` | no bounded page contract, aggregate freshness/coverage or production acceptance |
| Breathing Platform / Prophet same-session machinery | `PARTIAL` | useful live systems exist; current workstream still has separate causal acceptance gaps |
| Shared ordered-delta/SSE projection transport | `NOT_BUILT` | deliberately deferred to R1B |
| Materiality-gated intelligence recomputation | `PARTIAL` | domain-specific precedents exist; no universal authority |
| This R0 architecture freeze | `NOT_BUILT` before this carrier lands | prior named branch had zero unique commits and no PR |
| R1A implementation | `NOT_BUILT` | architecture and implementation remain separate |

No row should be averaged into “the site is live.” Different capabilities have different truth.

---

## 4. Canonical owner map

| Concern | Canonical owner | Projection behavior |
|---|---|---|
| Nightly intelligence, rankings, Prophet state, ledgers | Existing Macro engines and registered artifacts | Live layer may display beside them, never mutate or silently recompute them |
| Current US quote observations | Terminal Quote Plane | Macro reads a bounded debranded projection; no second feed/store |
| Public serving, auth, cache and rate policy | Existing Macro FastAPI serving tier | Add bounded route under existing middleware and deployment |
| Durable organizational state | Agent OS | Record WS/DEC/DSC/handoff only; never runtime liveness |
| Job/Attempt/Worker/Event lifecycle | Executive OS | R0 creates no lifecycle or dispatch |
| User workspace/chart interaction | Terminal | Existing ticker-to-Terminal route remains sole interaction owner |
| Page baseline | Current static builder/template | New controller hydrates durable markup; never creates a second page truth |
| Client live-state ownership | One route-scoped controller | Existing generic/live controllers cannot concurrently own the same node |
| Telemetry | Existing first-party analytics/observability paths | Emit measurements; do not create a parallel analytics store |

The projection platform is a **contract and composition pattern**, not a new source of market truth.

---

## 5. Anti-duplication constitution

This program must not create:

- a second quote connection, credential pool, vendor normalizer or quote database;
- a second intelligence ranker, score, stage machine, Prophet board or entry gate;
- a second browser-wide event bus or overlapping DOM owner;
- a second canonical market-state database;
- a second scheduler/retry/liveness/heartbeat authority;
- a second user identity or entitlement plane;
- a second correction ledger;
- a general Kafka/Redis/Temporal platform before one user vertical proves the need;
- a SPA rewrite merely to obtain fresh data;
- continuous LLM/model inference on quote ticks;
- a “fresh” badge derived from fetch time alone;
- an SSE/WebSocket endpoint that becomes a hidden new publisher of market truth.

If a future wave needs one of these, it requires a new explicit architecture ruling with evidence that the current canonical owner cannot meet the job.

---

## 6. Three-layer contract

### Layer A — durable baseline

The baseline is generated by the current builder and contains:

- selection and ordering;
- settled scores/stages/verdicts;
- the last known display values;
- complete bilingual/degraded markup;
- a durable as-of/build stamp;
- a no-JavaScript fallback.

The baseline is always renderable by itself. Live failure never empties the page.

### Layer B — deterministic live projection

A live projection may update only allowlisted observational fields, for example:

- regular-session price;
- regular-session absolute move;
- regular-session percentage move;
- market session;
- observation/source timestamp;
- projection receive timestamp;
- aggregate freshness and coverage state.

It may not update:

- ranking/order;
- opportunity or conviction score;
- Prophet state;
- signal stage;
- entry gate;
- falsifier;
- recommendation/stance;
- trade sizing, allocation or authority;
- any forward ledger.

### Layer C — material intelligence delta

A material delta is a separately governed recomputation. It needs:

- a named producer and consumer;
- a versioned input fingerprint;
- a domain-specific materiality predicate;
- debounce/hysteresis where state can flap;
- an explicit authority class;
- replay/correction behavior;
- forward evaluation where it could affect decisions.

A quote tick alone is never evidence that intelligence changed. R1A contains no Layer-C recomputation.

---

## 7. Projection envelope

The platform contract begins with one versioned envelope:

```json
{
  "schema": "reactive_projection.v1",
  "projection": "intelligence_hub.market_pulse",
  "snapshot_id": "opaque-stable-request-id",
  "sequence": 42,
  "generated_at": "2026-08-31T14:31:10.214Z",
  "source_owner": "terminal-market-data",
  "source_revision": "measured upstream revision or null",
  "status": "current",
  "coverage": {
    "requested": 30,
    "resolved": 29,
    "current": 27,
    "delayed": 2,
    "stale": 0,
    "missing": 1
  },
  "items": [],
  "errors": []
}
```

### Required envelope rules

- `schema` and `projection` are exact, versioned identities.
- `snapshot_id` identifies one response—not one durable lifecycle.
- `sequence` is monotonic within one controller session/stream; lower sequences cannot repaint.
- `generated_at` is projection creation time, not market source time.
- `source_owner` names the canonical upstream program, not a vendor brand.
- `status` is the conservative aggregate of item states.
- `coverage.requested` equals the sanitized requested-symbol count.
- missing/error symbols remain accounted for; they cannot disappear from the denominator.
- `errors` uses opaque allowlisted codes; no secret, vendor payload, filesystem path or raw exception.

### Item contract

```json
{
  "symbol": "NVDA",
  "price": 227.98,
  "change_abs": 18.32,
  "change_pct": 8.7379566918,
  "currency": "USD",
  "session": "regular",
  "freshness": "current",
  "observed_at": "2026-08-28T19:55:58Z",
  "received_at": "2026-08-28T19:56:01Z",
  "published_at": "2026-08-28T19:56:01Z",
  "revision": "source-derived-monotonic-token",
  "regular_session_date": "2026-08-28",
  "correction": false
}
```

Rules:

- `change_abs = price - regular_session_reference`.
- `change_pct` is percent, never dollars.
- `observed_at` is the source print/bar clock; it may legitimately stop after close.
- `received_at` and `published_at` are transport/projection clocks.
- freshness is session-aware and fails downward.
- extended-hours data cannot be substituted into regular-session fields.
- a missing reference produces null moves—not a fabricated zero.
- unrecognized basis/session/freshness vocabulary degrades; it never earns “current.”

---

## 8. Aggregate user states

The visible Market Pulse has exactly these product states:

| State | Meaning | Required behavior |
|---|---|---|
| `current` | every resolved row needed for the visible pulse satisfies the current-session rule and coverage clears the accepted floor | update quote cluster atomically; label current/live only under the accepted language |
| `delayed` | valid observations exist but one or more use an explicitly delayed basis, while coverage remains usable | show delayed language and source time; never animate as live |
| `partial` | usable response but not all requested symbols resolved/current | paint only resolved symbols in one atomic commit, keep baked values for missing rows, print coverage |
| `stale` | last-good projection exists but has exceeded the state-specific age budget | retain clearly stale last-good values or return to baked values according to the design; no live animation |
| `unavailable` | no trustworthy projection can be obtained | durable baseline remains; concise unavailable status |
| `baked` | page baseline before any current read or when live enhancement is disabled | print the baseline's own as-of; never call it live |

No state is inferred from HTTP 200 alone.

---

## 9. Time, ordering and correction semantics

### Clocks

Every implementation must keep separate:

- **market/source time** — when the upstream observation occurred;
- **receive time** — when the canonical quote owner received it;
- **projection time** — when Macro built the public response;
- **paint time** — when the browser committed the new visible state;
- **baseline time** — when the durable page was generated.

The UI chooses its language from market/source time plus session and basis, not from fetch/paint time.

### Session-aware freshness

During regular trading, a stalled print is a feed problem and the freshness budget is tight. After the market closes, the final regular-session print is supposed to stop; it remains a settled close rather than becoming stale minutes later. Pre/post/overnight observations are separate fields and states.

### Ordering

A browser controller accepts a response only when:

- the request belongs to the current route/controller generation;
- its local request sequence is not older than the last committed response;
- each item's revision/source time does not move backward without an explicit correction;
- the symbol identity matches the DOM target.

### Corrections

A correction can replace a prior observation only when its identity matches and its revision wins. The controller commits the whole accepted response atomically. A late non-correction response cannot partially roll the page backward.

### Gaps and reconnect

R1A is snapshot-based: a fresh snapshot closes any prior client gap. R1B ordered deltas must add explicit contiguous sequence/gap handling, with a bounded snapshot resync. Never add a hidden durable replay cursor database solely for browser reconnect.

---

## 10. Browser ownership law

Each visible value has exactly one owner.

For R1A:

- the template owns the baked baseline markup;
- the R1A controller owns the Market Pulse quote/move/status nodes after activation;
- shared `theme.js` continues to own ticker-to-Terminal interaction;
- generic `live.js` must not also mutate the same R1A nodes.

The implementation must use distinct selectors/attributes for the route-scoped controller. It may reuse common formatting and pure semantics, but not subscribe the same DOM node to two asynchronous writers. One request paints all accepted rows within one animation-frame commit to avoid mixed vintages.

JavaScript may mount/recompose canonical DOM and toggle state classes. It must not create a multi-kilobyte runtime stylesheet, second token palette or hidden design system.

---

## 11. Transport progression

### R1A — bounded snapshot pull

- one batch request for the visible symbol set;
- one canonical server read-through to the Terminal Quote Plane;
- refresh only while the page is visible;
- no per-card request;
- no client vendor access;
- no server retry on a single page request;
- no background durable queue.

This proves data/rights/time/browser/product semantics.

### R1B — ordered delta transport

Only after R1A production proof may a separate wave add shared SSE for one or more proven high-value projections. It must have:

- snapshot bootstrap;
- monotonically increasing sequence;
- heartbeat;
- gap detection and bounded snapshot resync;
- connection/rate/backpressure limits;
- last-good degradation;
- no source-of-truth claim.

SSE is the default because the first product need is server-to-browser projection. WebSocket requires an independently proven bidirectional job; it is not selected for branding.

### No transport platform theater

Transport adoption is driven by measured user latency and server cost. A successful R1A may remain snapshot-based if it meets the product SLO. The architecture does not force SSE for its own sake.

---

## 12. Materiality and authority

A live observation can be material to the user without being authority-bearing. Therefore:

- R1A updates observation only.
- A price move can trigger a display-only “market changed since baseline” indicator only under an existing governed rule.
- It cannot originate a rank, signal, stage, entry gate, forecast probability or trade action.
- LLM output has zero role in R1A.
- Future intelligence deltas require their own deterministic/statistical/model method declaration and promotion gate.

The browser never decides authority by comparing numbers locally.

---

## 13. Rights, privacy and security

- The Terminal Quote Plane remains credential/vendor owner.
- Macro consumes only loopback/private server output and returns a debranded allowlist.
- Vendor/source/basis/anchor names that are not licensed for public display stay server-side.
- No vendor key, internal host, path, raw upstream body or exception crosses the route.
- The route rejects redirect egress and non-loopback upstream configuration.
- Symbols are normalized by the existing safe-symbol contract, deduplicated and capped.
- Response bodies and upstream reads have hard byte caps.
- Existing API no-store/cache policy and rate limiting apply.
- R1A uses no personal Portfolio/Watchlist state and adds no new privacy class.
- Any future personalized projection must use verified existing identity and owner-scoped state; it cannot reuse this public response as an entitlement shortcut.

---

## 14. Observability and SLOs

R1A must measure:

- request count;
- sanitized symbol count;
- upstream latency;
- total projection latency;
- response state;
- requested/resolved/current/delayed/stale/missing counts;
- correction and out-of-order suppression counts;
- client first-paint and refresh success/failure;
- controller fallback reason;
- browser interaction continuity for ticker-to-Terminal.

Initial acceptance budgets, subject to measurement rather than silent retuning:

- route p95 under 2.5 seconds;
- one upstream batch read per browser refresh;
- no unbounded payload;
- zero false-current rows in adversarial fixtures;
- 100% requested-universe accounting;
- no rank/order/score/stage changes;
- no page-wide mixed-response paint;
- zero console errors and zero horizontal overflow at required breakpoints.

Telemetry reports behavior; it grants no health or authority.

---

## 15. Failure behavior

| Failure | Response |
|---|---|
| Terminal Quote Plane unavailable | one bounded failure, no retry storm; baseline + unavailable state |
| Upstream returns partial symbols | `partial`, denominator preserved, missing rows stay baked |
| Unknown basis/session/clock | degrade item; never current |
| Source timestamp absent/unparseable | stale/unavailable according to contract, never assumed fresh |
| Late older request | suppress |
| Explicit newer correction | atomically replace matching row |
| Future clock beyond tolerance | refuse current classification |
| Browser hidden | pause refresh; resume with one fresh snapshot |
| JavaScript disabled | baseline remains complete and honestly dated |
| Live-price user setting disabled | remain baked; no request |
| Route returns malformed schema | reject entire response; retain last-good/baked |
| Existing Terminal click target | remains operative before and after price repaint |
| Coverage below useful threshold | partial or unavailable; never cosmetically “live” |

---

## 16. Program waves

### R0 — records-only architecture freeze

Five canonical records on one branch/PR:

1. this architecture freeze;
2. route-level design specification;
3. R1A implementation plan;
4. Agent OS decision;
5. Agent OS handoff.

R0 makes no runtime capability live.

### R1A — Intelligence Hub Market Pulse

One independently useful user vertical: canonical quote plane → bounded public batch projection → atomic Intelligence Hub display → production/browser proof.

### R1B — shared ordered-delta transport

Separate commission after R1A acceptance. Generalize only the proven contract and only where continuous push materially improves the product.

### R2 — shared projection component registry

Converge additional flagship surfaces onto canonical status/clock/coverage components without a rewrite.

### R3 — materiality-gated intelligence deltas

Add domain-specific recomputation contracts, replay and calibration. No universal “recompute everything” loop.

### R4 — resilient publication/orchestration

Reduce nightly critical path and make durable baselines update in smaller independently recoverable units, extending existing DAG/workflow/host orchestration rather than creating another scheduler.

### R5 — learning and portfolio relevance

Measure research/discovery/retention outcomes and add personalized projections only through existing identity/Portfolio/Watchlist authorities.

Each wave receives a separate operation identity, exact carrier and proof law.

---

## 17. R1A frozen boundary

### Included

- US symbols already surfaced by the Intelligence Hub baseline.
- Current regular-session price and absolute/percentage move.
- One page-level aggregate freshness/coverage state.
- Bilingual dark/light desktop/narrow presentation.
- Existing ticker-to-Terminal action.
- Current, delayed, partial, stale, unavailable and baked behavior.
- Browser, API, rights and telemetry proof.

### Excluded

- selection/order/ranking/score changes;
- Prophet or entry-state changes;
- options/news/policy/LLM recomputation;
- personalized holdings/watchlists;
- premarket/after-hours primary-price redesign;
- streaming/SSE/WebSocket;
- service worker/offline cache;
- new database/event bus;
- broad site migration;
- quote-vendor or entitlement changes.

### Production proof

R1A is not accepted until a real page proves, in both normal and degraded states:

- visible current values came from the canonical quote projection;
- quote, absolute move and percent are one internally consistent regular-session tuple;
- aggregate state and coverage match item truth;
- the nightly order/scores/stages are byte/semantic invariant;
- one refresh produced one batch route call, not N card calls;
- a forced outage leaves the durable baseline usable;
- late/out-of-order responses cannot roll the page backward;
- ticker-to-Terminal continues to work;
- dark/light × EN/ZH × 1440/390 evidence is reviewed.

---

## 18. Architecture acceptance gates

R0 may be accepted only when:

- the sole branch and draft PR are exact and collision-clean;
- changed paths are exactly the five records named in §16;
- Agent OS records validate;
- current protected procedure and current Macro base are recorded;
- an independent principal reviewer finds no duplicate authority/state/transport plane;
- R1A is executable without architectural invention;
- failure/time/correction/rights/one-DOM-owner rules are testable;
- the PR remains records-only and production inert;
- the worker/reviewer dialogue is explicitly closed.

After R0 acceptance and merge, R1A still requires a new child operation, lawful placement, ACK, separate START, code review, merge, deployment and production proof. R0 merge is architecture completion only.
