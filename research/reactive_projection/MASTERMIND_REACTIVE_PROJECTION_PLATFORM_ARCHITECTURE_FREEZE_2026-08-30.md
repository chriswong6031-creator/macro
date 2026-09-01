# Mastermind Reactive Projection Platform — Architecture Freeze

**Date:** 2026-08-31  
**Parent operation:** `modernize-mastermind-architecture-20260830-sol-001`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Sole R0 carrier:** `sol/reactive-projection-platform-r0-20260830` / Macro PR `#6707`  
**Current corrected architecture head before this edit:** `8cd1ac766f544e6615366b7ba21c7d8d0182bda9`  
**Current protected Sol procedure:** `mastermindx-market-intelligence/Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc`  
**Terminal archaeology pin:** `mastermindx-market-intelligence/mastermind-terminal@86a75b68c273a592a41af5e322f95aab242b8297`  
**Status:** **PROPOSED ARCHITECTURE FREEZE / BUILT_NOT_PROVEN / RECORDS_ONLY / PRODUCTION_INERT**

This document freezes the architecture for moving Mastermind-X from a predominantly nightly generated publication to a responsive market-intelligence product. It does not install a service, arm a scheduler, change a quote feed, alter a rank, publish a browser bundle, create an Executive Job, or claim a production capability.

The architecture is evolutionary. Mastermind already owns the hard systems that must remain canonical: nightly evidence and ledgers, the Terminal Quote Plane, Macro's serving tier, static-page progressive enhancement, Prophet-Live, close-pass publication, freshness sentinels, identity, Agent OS and Executive OS. The missing capability is a disciplined projection contract joining those owners—not another realtime stack.

---

## 1. Executive ruling

Mastermind's responsive product architecture has exactly three semantic layers:

1. **Durable baseline** — the nightly or close-pass generated artifact remains complete, auditable, cacheable and correction-safe.
2. **Deterministic live projection** — bounded observations patch only fields explicitly owned by the canonical producer, preserving source time, projection time, feed freshness, market session, coverage and revision semantics.
3. **Material intelligence delta** — slower intelligence is recomputed only when a governed materiality rule proves the underlying evidence changed enough to matter. A quote tick does not itself authorize model work or a new verdict.

The first user capability is **R1A — Intelligence Hub Market Pulse**:

> For the exact names rendered in the nightly Intelligence Hub's Command, Emerging and diversified Discovery views, display current regular-session price and coherent day move from the canonical Terminal Quote Plane, repaint every occurrence atomically, and state freshness, session and coverage honestly—without changing selection, order, score, stage, Prophet state, intelligence conclusion, allocation or trading authority.

R1A is a stateless snapshot projection. Ordered deltas/SSE are a later independently reviewed wave. The first slice proves product truth, rights, source ownership, demand isolation, browser ownership and failure behavior before any transport is generalized.

---

## 2. Outcome and 10/10 end-state

### Primary user job

A user opens a Mastermind page during or after the trading session and can immediately distinguish:

- what the durable intelligence system concluded;
- what the regular market is doing now or where it settled;
- whether the quote feed is live, delayed or stale;
- whether coverage is complete or partial;
- whether the market is open or the value is a settled close;
- whether the durable conclusion has actually been recomputed.

The product must never make a recently fetched stale print look live, a partial response look complete, a settled close look like an open market, an extended-hours print look like a regular-session day move, or a current quote look like a new intelligence verdict.

### Machine and intelligence job

The system must:

- source current observations only through the existing Terminal Quote Plane;
- obtain a regular-session-only view without perturbing Terminal's globally shared extended-hours demand budget;
- project only governed fields;
- preserve source and projection clocks;
- reject out-of-order browser results;
- expose availability, freshness and coverage as orthogonal facts;
- paint one response atomically across every DOM occurrence of a symbol;
- leave authoritative engines and ledgers untouched until their own cadence or promotion law runs.

### Product moat

The moat is not a websocket. It is the combination of exact durable evidence, fast deterministic observation, honest clocks, correction-safe projection, coherent cross-surface interaction, rights-safe provenance, and an instrumented learning loop.

### Completion standard

The program is complete only when it has:

- **Truth:** source-time honest, correction-safe and rights-safe inputs that fail downward.
- **Intelligence:** useful current context without authority laundering.
- **Product:** coherent flagship workflows across normal and degraded states.
- **Learning:** latency, coverage, correction and usage instrumentation that can show whether responsiveness improves research and decisions.

---

## 3. Current capability ledger at R0

| Capability | State | Current truth |
|---|---|---|
| Nightly generated baseline and governed artifacts | `PROVEN_LIVE` | Current Macro pipeline and product |
| Terminal Market Data and Quote Plane | `PROVEN_LIVE` | Canonical current quote owner |
| Macro public debranded dossier quote projection | `PROVEN_LIVE` | Existing one-symbol precedent |
| Generic static-page live-price enhancement | `PARTIAL` | `templates/live.js`; not a page-complete truth contract |
| Intelligence Hub nightly quote markup | `PARTIAL` | Baked `.nb-px` values exist for surfaced rows |
| Intelligence Hub page-complete Market Pulse | `DARK_OR_DISCONNECTED` | No accepted bounded batch contract or production proof |
| Terminal regular-only non-disruptive quote view | `NOT_BUILT` | Existing `/quotes` always demands extended-hours state for US names |
| Breathing Platform / Prophet same-session machinery | `PARTIAL` | Useful systems exist; separate completion program remains active |
| Shared ordered-delta/SSE projection transport | `NOT_BUILT` | Held to R1B |
| Materiality-gated intelligence recomputation | `PARTIAL` | Domain-specific precedents only |
| This R0 freeze on PR #6707 | `BUILT_NOT_PROVEN` | Records exist; foreign-base repair, current-head CI and independent review remain gates |
| R1A implementation and production proof | `NOT_BUILT` | Separate post-R0 child operations required |

No aggregate label such as “the site is live” may erase these distinctions.

---

## 4. Canonical owner map

| Concern | Canonical owner | Required behavior |
|---|---|---|
| Nightly intelligence, ranking, Prophet state and ledgers | Existing Macro engines and registered artifacts | Live observation may display beside them; never silently mutate or recompute them |
| US regular and extended quote observations | Terminal Quote Plane | Extend this owner with a regular-only read mode; create no second source or store |
| Public projection, cache, rate and response policy | Existing Macro FastAPI serving tier | One deliberate public quote-only route under existing middleware |
| Static asset access | `config/site_access.yml` plus matching Caddy boundary | Explicitly expose only the controller required by the public shell |
| Durable organizational state | Agent OS | Decisions, discoveries and handoffs only; never runtime liveness |
| Job/Attempt/Worker/Event lifecycle | Executive OS | R0 creates no lifecycle or dispatch |
| Ticker/chart workspace interaction | Terminal | Existing ticker-to-Terminal route remains sole interaction owner |
| Page baseline | Current Intelligence Hub builder and Jinja template | Complete no-JavaScript fallback |
| Client quote DOM | One R1A route-scoped controller | Generic live controller must not own the same targets |
| Telemetry | Existing first-party observability paths | Emit measurements; create no second analytics store |

The projection platform is a contract and composition pattern, not a new source of market truth.

---

## 5. Current-estate finding: ordinary `/quotes` is not safe for R1A outside RTH

Current Terminal code at `86a75b68...` establishes:

- `hub/hub.js::handleQuotes()` calls `applyDemand()` for every requested US symbol.
- `hub/lib/quotes.js::applyDemand()` demands SnapshotFeed, Polygon, AnchorCache **and** `ExtFeed` for every US symbol when the Polygon leg is healthy.
- `hub/lib/extfeed.js::ExtFeed` is a process-wide singleton with a **30-symbol global LRU** shared by all users.
- Every ordinary `/quotes` request advances each requested US symbol to MRU and evicts the oldest symbol at capacity.
- The Intelligence Hub can render at most 30 Command + 14 Emerging + 14 diversified Discovery slots: at most **58 unique candidates before dedupe**, with many symbols appearing in more than one panel.

A 60-second public page refresh over up to 58 names would therefore repeatedly churn a 30-name extended-hours LRU and could evict symbols demanded by active Terminal users, even though R1A intentionally ignores extended-hours fields. Restricting R1A to 30 names, fetching only once after close, or simply dropping `ext*` fields in Macro would not repair the demand-side effect.

### Ruling

R1A must not call the ordinary full quote view. It requires an owner-native Terminal extension:

```http
GET /quotes?syms=NVDA,AAPL,MSFT&view=regular
```

The default remains `view=full` for every existing caller. `view=regular` changes no source ownership and creates no endpoint family; it is a closed read option on the canonical endpoint.

For `view=regular`, Terminal must:

- demand SnapshotFeed for every eligible US symbol;
- preserve the existing Polygon subscription and AnchorCache warm path;
- **not call `extFeed.demand()`**;
- pass no extended-hours provider into response assembly;
- emit no `extPrice`, `extChg`, `extTs`, `extSession`, `extSource` or `extBasis` field;
- retain the existing flat `{SYM: quote}` response and present-entries-only behavior;
- reject unknown `view` values instead of silently broadening behavior;
- preserve the default `view=full` byte-for-semantic behavior and tests.

Macro's R1A route must call `view=regular` explicitly and must fail closed if deployed Terminal does not prove that contract. No direct vendor call, second snapshot service or Macro-side demand suppressor may substitute for the Terminal owner change.

---

## 6. R1A rendered roster and identity

The projected roster is the ordered unique union of exactly:

```text
hub.command[:30]
hub.emerging[:14]
hub.discovery_shown[:14]
```

where `discovery_shown` is the existing diversified presentation list, not the full Discovery candidate corpus. `exhausted`, catalyst-only names and hidden Discovery candidates are outside R1A.

Rules:

- Maximum unique request cardinality is **58**; API cap is **60** to allow only bounded presentation evolution.
- First occurrence in rendered DOM order establishes request order.
- Coverage denominators count unique symbols, not DOM nodes.
- One symbol may have several rendered targets. The client owns `Map<symbol, HTMLElement[]>`, validates the response once, and paints every target for that symbol inside the same animation-frame transaction.
- A symbol not in the rendered roster cannot be requested merely because the public API accepts a safe symbol.
- The nightly builder remains the source of roster membership and baseline values.

---

## 7. Anti-duplication constitution

This program must not create:

- a second quote connection, credential pool, vendor normalizer, quote database or snapshot daemon;
- a second intelligence ranker, score, stage machine, Prophet board or entry gate;
- a second browser-wide event bus or overlapping DOM owner;
- a second canonical market-state database;
- a second scheduler, retry, liveness or heartbeat authority;
- a second user identity or entitlement plane;
- a second correction ledger;
- a server monotonic sequence counter merely to decorate a stateless snapshot;
- a general Kafka, Redis or Temporal platform before a user vertical proves the need;
- a SPA rewrite merely to obtain fresh data;
- continuous model inference on quote ticks;
- a “fresh” badge derived from fetch time;
- an SSE/WebSocket endpoint that becomes a hidden publisher of market truth;
- Macro-side logic that bypasses or imitates Terminal's demand router.

Any future exception requires a new architecture ruling and evidence that the current owner cannot satisfy the job.

---

## 8. Three-layer contract

### Layer A — durable baseline

The current builder renders:

- selection and order;
- settled scores, stages and verdicts;
- last-known display values;
- bilingual normal and degraded markup;
- durable as-of/build time;
- complete no-JavaScript fallback.

Live failure never empties or invalidates the baseline.

### Layer B — deterministic live projection

The allowlist is limited to:

- regular-session price;
- regular-session absolute move;
- regular-session percentage move;
- market session;
- source timestamp;
- projection timestamp;
- feed freshness;
- coverage counts and state.

It may not update rank, order, score, Prophet state, stage, entry gate, falsifier, stance, recommendation, allocation, sizing or a forward ledger.

### Layer C — material intelligence delta

A material delta requires a named producer and consumer, a versioned input fingerprint, a deterministic materiality predicate, hysteresis/debounce where state can flap, an explicit authority class, replay/correction behavior, and forward evaluation where decisions could change.

R1A contains no Layer-C recomputation.

---

## 9. R1A projection envelope

R1A is stateless pull. There is no server transport sequence, replay cursor or correction ledger.

```json
{
  "schema": "intelligence_hub.market_pulse.v1",
  "projection": "intelligence_hub.market_pulse",
  "snapshot_id": "opaque-response-identity",
  "generated_at": "2026-08-31T14:31:10.214Z",
  "source_owner": "terminal-market-data",
  "source_view": "regular",
  "state": {
    "availability": "available",
    "freshness": "live",
    "coverage": "partial"
  },
  "coverage": {
    "requested": 30,
    "resolved": 29,
    "live": 27,
    "delayed": 2,
    "stale": 0,
    "missing": 1
  },
  "items": [],
  "errors": []
}
```

Required laws:

- `schema`, `projection` and `source_view` are exact closed identities.
- `snapshot_id` grants no ordering, lifecycle or retry authority.
- `generated_at` is projection time, not source time.
- `state.availability=available` only when at least one trustworthy item exists.
- freshness is the conservative worst resolved item: `live`, `delayed` or `stale`.
- coverage is independent: `complete` or `partial`.
- `resolved + missing == requested`.
- `live + delayed + stale == resolved`.
- Missing/error symbols remain in the denominator.
- Errors are opaque allowlisted codes.
- A majority of live rows cannot hide one delayed/stale row.

Item:

```json
{
  "symbol": "NVDA",
  "price": 227.98,
  "change_abs": 18.32,
  "change_pct": 8.7379566918,
  "currency": "USD",
  "session": "regular",
  "freshness": "live",
  "observed_at": "2026-08-28T19:55:58Z",
  "received_at": null,
  "published_at": "2026-08-28T19:56:01Z",
  "revision": "sha256-of-source-identity-time-and-values",
  "regular_session_date": "2026-08-28"
}
```

- `change_abs = price - regular_session_reference`.
- `change_pct` is percent, never dollars.
- “Live” UI requires `freshness=live` and `session=regular`.
- A non-stale `session=closed` row is a settled close.
- `observed_at` is source time and may stop after close.
- `received_at` remains null unless the canonical owner provides a trustworthy receive clock.
- `published_at` is Macro projection time.
- `revision` is deterministic equality fingerprint, not a counter.
- Extended fields cannot substitute into the regular tuple.
- Missing reference means null moves, not zero.
- Unknown basis/session/freshness fails downward.

---

## 10. Server axes and client product states

API axes:

| Axis | Values | Meaning |
|---|---|---|
| Availability | `available` or HTTP `503` | whether any trustworthy item exists |
| Feed freshness | `live`, `delayed`, `stale` | what the source proves |
| Coverage | `complete`, `partial` | whether every unique requested symbol resolved |

Browser states combine those axes with market session and local lifecycle:

| State | Behavior |
|---|---|
| `baked` | complete durable baseline before activation or when live prices are disabled |
| `loading` | baseline stays visible during one bounded request |
| `live-complete` | atomically paint every target; live indicator only in regular session |
| `live-partial` | paint resolved symbols, retain baked missing targets, print coverage |
| `delayed-complete` / `delayed-partial` | show delayed language and source time; no live animation |
| `stale-complete` / `stale-partial` | unmistakable stale language; last-good only inside hard client bound |
| `settled-complete` / `settled-partial` | closed session with non-stale regular close; never call market live |
| `unavailable` | baseline remains with concise unavailable state |

No state is inferred from HTTP 200 alone.

---

## 11. Time, ordering and correction

Keep separate:

- market/source time;
- canonical receive time only when supplied;
- Macro projection time;
- browser paint time;
- baseline build time.

A controller accepts a response only when it belongs to the newest local request generation, passes full envelope/coverage validation, and contains exact requested identities. For each symbol:

- newer source time: accept;
- older source time: suppress and recompute truthful coverage;
- equal source time + equal revision: idempotent;
- equal source time + changed revision on a later request: accept as source correction and emit telemetry.

Every occurrence of every accepted symbol is committed in one animation frame. `snapshot_id` is never an ordering key.

R1B alone may add contiguous stream sequence, heartbeat and gap resync.

---

## 12. Browser ownership law

For R1A:

- the template owns baked baseline markup;
- the R1A controller owns the Market Pulse quote/move/status targets after activation;
- `theme.js` owns ticker-to-Terminal interaction;
- generic `live.js` must not mutate R1A targets.

The controller may reuse pure formatters but cannot subscribe the same node to two asynchronous writers. It maps one symbol to all rendered targets and paints the accepted response atomically. It creates no runtime stylesheet, second token palette or hidden design system.

---

## 13. Transport progression

### R1A-T — Terminal owner extension

One child operation and one Terminal carrier implement and production-prove `view=regular`:

```text
canonical /quotes endpoint
+ closed view parser
+ demand isolation
+ regular-only response assembly
+ exact tests
+ deployed loopback canary
```

It does not create a new endpoint, source, service or public product surface. Its machine capability is a non-disruptive regular-session quote read for bounded internal projections.

### R1A-M — Macro consumer and Intelligence Hub product

Only after R1A-T is merged, deployed and proven does a separate Macro child operation consume `view=regular` and implement:

```text
shared public quote semantics
+ deliberately public bounded batch projection
+ durable markup
+ public controller asset
+ atomic multi-target paint
+ browser/production proof
```

R1A-T and R1A-M are two modifying operations with two repository carriers under one user-capability program. Neither inherits the other's START. The product is not `PROVEN_LIVE` until R1A-M passes production proof.

### R1B — ordered delta transport

Only after R1A acceptance and measured need may a new operation add shared SSE with snapshot bootstrap, monotonically increasing stream sequence, heartbeat, gap detection, bounded snapshot resync, backpressure and last-good degradation. WebSocket requires an independently proven bidirectional job.

A successful R1A may remain snapshot-based.

---

## 14. Rights, access, privacy and security

R1A's Macro quote route is deliberately public because the HTML shell is public, the response is allowlisted market observation only, the executed enterprise redistribution addendum permits external display/API redistribution, and the dossier projection establishes the pattern.

Required controls:

- Terminal owns credentials and vendor normalization.
- Macro reads loopback only and returns a debranded allowlist.
- Macro calls `view=regular` and refuses an unproven/fallback full view.
- Provider, basis and anchor-source names remain server-side.
- No key, internal host, path, raw body or exception crosses the route.
- Redirects are refused.
- Unique safe symbols are capped at 60.
- Each unique symbol consumes one unit in bounded client and peer rolling budgets.
- Response and upstream read sizes are bounded.
- Existing no-store policy applies.
- The new controller path is opened in both `config/site_access.yml` and the matching Caddy list; no signal JSON prefix is opened.
- R1A uses no personal Portfolio/Watchlist state.

---

## 15. Observability and SLOs

Measure:

- request and unique-symbol units;
- upstream and total projection latency;
- source view requested and proven;
- availability/freshness/coverage axes;
- requested/resolved/live/delayed/stale/missing counts;
- same-time revision changes;
- out-of-order suppression;
- first paint and refresh success/failure;
- fallback reason;
- ticker-to-Terminal continuity;
- Terminal regular-view demand counts;
- proof that regular-view requests changed neither ExtFeed LRU size nor membership.

Initial acceptance budgets:

- route p95 below 2.5 seconds;
- one Macro upstream request per browser refresh;
- at most 60 unique symbols;
- zero regular-view ext-demand calls;
- zero false-live rows;
- 100% unique-roster accounting;
- no rank/order/score/stage mutation;
- no mixed-response paint;
- zero console errors and horizontal overflow at required breakpoints.

Telemetry reports behavior; it grants no health or authority.

---

## 16. Failure behavior

| Failure | Required result |
|---|---|
| Terminal regular view unavailable or unsupported | one bounded failure; baseline + unavailable; never fall back to full view |
| Upstream returns extended fields under regular view | reject contract as malformed; retain baseline |
| Regular-view request changes ExtFeed demand state | R1A-T acceptance fails |
| Partial symbols | coverage partial, denominator preserved, missing targets remain baked |
| Unknown basis/session/clock | never live |
| Missing source timestamp | stale/unavailable, never fresh by request time |
| Late local generation | suppress response |
| Older item source time | suppress item and recompute coverage |
| Equal time + changed revision | accept as correction and record telemetry |
| Future clock | refuse live classification |
| Hidden browser | pause; resume with one snapshot |
| JavaScript disabled | complete honestly dated baseline |
| Live setting disabled | no request |
| Controller asset gated/missing | serving-boundary test fails |
| Malformed schema/arithmetic | reject entire response |
| Duplicate symbol in response | reject entire response |
| Symbol rendered in several panels | every occurrence updates together |
| Terminal click target | remains operative before and after paint |

---

## 17. Program waves

### R0 — records-only architecture freeze

Exactly five records on Macro PR #6707. No runtime capability.

### R1A-T — regular-only Terminal owner contract

One Terminal PR, owner-native tests and deployed loopback proof. No Macro/browser change.

### R1A-M — Intelligence Hub Market Pulse

One Macro PR with producer adapter, real page consumer, UI, tests and production/browser proof.

### R1B — shared ordered-delta transport

Separate commission after R1A acceptance and measurement.

### R2 — shared projection components

Converge proven status/clock/coverage patterns across additional flagship surfaces without a rewrite.

### R3 — materiality-gated intelligence deltas

Add domain-specific recomputation contracts, replay and calibration. No universal rerun-everything loop.

### R4 — resilient publication and orchestration

Reduce the nightly critical path through existing DAG/workflow/host owners, not another scheduler.

### R5 — learning and portfolio relevance

Measure product outcomes and add personalized projections only through existing identity and Portfolio/Watchlist authorities.

---

## 18. R1A frozen boundary

Included:

- ordered unique roster from Command, Emerging and diversified Discovery presentation lists;
- at most 58 current rendered names, API cap 60;
- regular-session price and coherent absolute/percentage move;
- Terminal `view=regular` owner extension with zero ext-demand effect;
- one page-level freshness/session/coverage instrument;
- one symbol to many DOM targets;
- deliberate public quote-only Macro route and controller asset;
- dark/light, EN/ZH, desktop/narrow presentation;
- ticker-to-Terminal continuity;
- live, delayed, partial, stale, settled, unavailable and baked states;
- rights, access, abuse, telemetry, canary and rollback proof.

Excluded:

- full Discovery corpus, exhausted and catalyst-only rows;
- selection, ordering, ranking or score changes;
- Prophet/entry state changes;
- options, news, policy or model recomputation;
- personalized holdings/watchlists;
- extended-hours primary-price redesign;
- streaming/SSE/WebSocket;
- service worker/offline cache;
- new database/event bus;
- broad site migration;
- vendor/entitlement changes.

---

## 19. Production proof

R1A-T must prove on the actual Terminal host:

- default `/quotes` behavior remains unchanged;
- `view=regular` returns the regular flat response;
- no extended field is emitted;
- 58-name regular-view demand changes neither ExtFeed subscription map nor LRU order;
- SnapshotFeed/Polygon/AnchorCache regular paths still receive demand;
- invalid view fails closed;
- deployment identity matches reviewed merge.

R1A-M must prove on the real site:

- visible values came from Terminal `view=regular` through Macro's canonical projection;
- price, absolute move and percent form one coherent regular tuple;
- freshness, session and coverage match item truth;
- the unique roster is exactly the rendered Command/Emerging/Discovery union;
- every duplicate DOM occurrence updates in the same paint;
- anonymous shell loads the controller and quote route;
- symbol-weighted limits block amplification while normal cadence succeeds;
- nightly order, scores and stages are invariant;
- one refresh makes one batch route call;
- outage/partial/malformed regular-view states leave the baseline usable;
- old responses cannot roll the page backward;
- equal-time correction can land without a server ledger;
- ticker-to-Terminal still works;
- dark/light × EN/ZH × 1440/390 evidence is reviewed.

---

## 20. R0 acceptance gates

R0 may be accepted only when:

- the sole branch and draft PR are exact and collision-clean;
- changed paths remain exactly these five records;
- Agent OS validates on the full current base;
- current protected procedure, Macro base and Terminal archaeology pin are recorded;
- an independent reviewer confirms no duplicate authority, source, state, transport or demand plane;
- the regular-only owner extension and two-child carrier order eliminate ExtFeed LRU contention;
- the exact rendered roster and one-symbol-to-many-target law are executable;
- time, correction, rights, access and failure rules are testable;
- the stateless snapshot carries no fake sequence or correction authority;
- freshness, session and coverage remain orthogonal;
- the PR remains records-only and production inert;
- every reviewer/worker dialogue is explicitly closed.

After R0 merge, R1A-T and R1A-M still require fresh operation identities, lawful placement, ACK, separate START, exact PRs, review, deployment proof and terminal closeout. R0 merge is architecture completion only.
