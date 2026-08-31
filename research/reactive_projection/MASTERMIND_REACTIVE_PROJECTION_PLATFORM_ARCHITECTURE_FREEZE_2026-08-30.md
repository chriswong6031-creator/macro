# Mastermind Reactive Projection Platform — Architecture Freeze

**Date:** 2026-08-31  
**Parent operation:** `modernize-mastermind-architecture-20260830-sol-001`  
**Repository:** `mastermindx-market-intelligence/macro`  
**Sole R0 carrier:** `sol/reactive-projection-platform-r0-20260830`  
**Original pickup base:** `20748fccbb9777f7e43c39acf19499bac4d011be`  
**Latest protected Sol procedure used for R0 correction:** `mastermindx-market-intelligence/Mastermind@dcce6f7ab6efad360f4854d748ad0d65dc9e0f7c`  
**Status:** **PROPOSED ARCHITECTURE FREEZE / RECORDS_ONLY / PRODUCTION_INERT**

This document resolves the architecture question created by the Chairman's directive that Mastermind-X stop behaving like a once-per-night static publication and become a responsive market-intelligence product. It does **not** install a service, arm a scheduler, change a quote feed, alter ranking, publish a browser bundle, create an Executive Job, or make any live-capability claim.

The architecture is deliberately evolutionary. Mastermind already has valuable canonical systems: nightly engines and ledgers, a Terminal Quote Plane, Macro's API serving tier, static-page progressive enhancement, Prophet-Live, close-pass publication, freshness sentinels, and governed Agent/Executive operating systems. The correct move is to make those systems cooperate through a small projection contract—not to replace them with a second realtime stack.

---

## 1. Executive ruling

Mastermind's responsive product architecture has exactly three semantic layers:

1. **Durable baseline** — the nightly/close-pass generated artifact remains the complete, auditable and correction-safe baseline.
2. **Deterministic live projection** — bounded current observations patch only fields explicitly owned by a live producer, with source time, projection time, feed freshness, market session, coverage and content-revision semantics.
3. **Material intelligence delta** — slower intelligence is recomputed only when a governed materiality rule says the underlying evidence changed enough to matter. No model reruns merely because a quote tick arrived.

The first implementation slice is **R1A — Intelligence Hub Market Pulse**:

> For the names the nightly Intelligence Hub already selected, display current regular-session price and move from the canonical Terminal Quote Plane, update the whole visible pulse atomically, and state feed freshness, market session and coverage honestly—without changing selection, order, score, stage, Prophet state, intelligence conclusion or trading authority.

R1A is a stateless snapshot projection. Ordered deltas/SSE are a later independently reviewable wave. This is intentional: first prove one useful current-data vertical end to end, then generalize transport only from measured need.

---

## 2. Outcome and 10/10 end-state

### Primary user job

A user opens a Mastermind page during or after the trading session and can immediately distinguish:

- what the durable intelligence system concluded;
- what the market is doing now;
- whether the feed is genuinely live, delayed or stale;
- whether coverage is complete or partial;
- whether the market is open or the displayed observation is a settled close;
- whether the durable conclusion has been recomputed or is still the last settled baseline.

The user must never mistake a recently fetched stale print for a live market observation, a partial response for full coverage, a settled close for an open market, or a current quote for a newly recomputed intelligence verdict.

### Machine/intelligence job

The system must ingest current observations through the existing canonical owner, project only governed fields, preserve source and projection clocks, reject out-of-order responses, expose coverage and degradation as separate axes, and leave all authoritative engines/ledgers untouched until their own cadence or promotion rules run.

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
| Intelligence Hub page-complete Market Pulse | `DARK_OR_DISCONNECTED` | no bounded page contract, orthogonal freshness/coverage state or production acceptance |
| Breathing Platform / Prophet same-session machinery | `PARTIAL` | useful live systems exist; current workstream still has separate causal acceptance gaps |
| Shared ordered-delta/SSE projection transport | `NOT_BUILT` | deliberately deferred to R1B |
| Materiality-gated intelligence recomputation | `PARTIAL` | domain-specific precedents exist; no universal authority |
| This R0 architecture freeze | `BUILT_NOT_PROVEN` while the draft PR is held | records exist; independent review and merge remain open |
| R1A implementation | `NOT_BUILT` | architecture and implementation remain separate |

No row should be averaged into “the site is live.” Different capabilities have different truth.

---

## 4. Canonical owner map

| Concern | Canonical owner | Projection behavior |
|---|---|---|
| Nightly intelligence, rankings, Prophet state, ledgers | Existing Macro engines and registered artifacts | Live layer may display beside them, never mutate or silently recompute them |
| Current US quote observations | Terminal Quote Plane | Macro reads a bounded debranded projection; no second feed/store |
| Public serving, auth, cache and rate policy | Existing Macro FastAPI serving tier | Add one deliberately public, bounded quote-only route under existing middleware and deploy ownership |
| Static asset access boundary | `config/site_access.yml` + matching Caddy boundary | New controller is explicitly public presentation code or it does not load on the anonymous-public shell |
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
- a server-side monotonic sequence counter merely to decorate a stateless snapshot;
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

A live projection may update only allowlisted observational fields:

- regular-session price;
- regular-session absolute move;
- regular-session percentage move;
- market session;
- observation/source timestamp;
- projection timestamp;
- feed freshness;
- coverage counts/state.

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

## 7. R1A projection envelope

R1A is a stateless pull. Its response intentionally has **no server transport sequence**. Request ordering belongs to the browser's local generation counter; content ordering belongs to source time plus a deterministic content revision. A stream sequence appears only in R1B.

```json
{
  "schema": "intelligence_hub.market_pulse.v1",
  "projection": "intelligence_hub.market_pulse",
  "snapshot_id": "opaque-response-identity",
  "generated_at": "2026-08-31T14:31:10.214Z",
  "source_owner": "terminal-market-data",
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

### Required envelope rules

- `schema` and `projection` are exact, versioned identities.
- `snapshot_id` identifies one response; it grants no ordering, lifecycle or retry authority.
- `generated_at` is projection creation time, not market source time.
- `source_owner` names the canonical upstream program, not a vendor brand.
- `state.availability` is `available` only when at least one trustworthy item exists.
- `state.freshness` is the conservative worst item freshness: `live`, `delayed`, or `stale`.
- `state.coverage` is orthogonal: `complete` or `partial`. Empty coverage is a `503`, not a plausible `200`.
- `coverage.requested` equals the sanitized requested-symbol count.
- `coverage.resolved + coverage.missing == coverage.requested`.
- `coverage.live + coverage.delayed + coverage.stale == coverage.resolved`.
- Missing/error symbols remain accounted for; they cannot disappear from the denominator.
- `errors` uses opaque allowlisted codes; no secret, vendor payload, filesystem path or raw exception.
- A majority of live rows cannot hide one delayed/stale row; complete coverage cannot hide stale freshness, and live freshness cannot hide partial coverage.

### Item contract

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

Rules:

- `change_abs = price - regular_session_reference`.
- `change_pct` is percent, never dollars.
- `freshness` reuses the proven public projector vocabulary: `live`, `delayed`, `stale`.
- `session` is independent: `regular`, `pre`, `post`, or `closed`.
- “Live” may be displayed only for `freshness=live` **and** `session=regular`; a closed live-basis row is a settled close, not an open market.
- `observed_at` is the source print/bar clock; it may legitimately stop after close.
- `received_at` is nullable because the current upstream contract may not expose a trustworthy receive clock. Never manufacture it from request time.
- `published_at` is Macro projection time.
- `revision` is a deterministic equality fingerprint, not a monotonic counter.
- Extended-hours data cannot be substituted into regular-session fields.
- A missing reference produces null moves—not a fabricated zero.
- Unrecognized basis/session/freshness vocabulary degrades; it never earns `live`.

---

## 8. Server axes and client product states

The API expresses three orthogonal facts:

| Axis | Values | Meaning |
|---|---|---|
| Availability | `available` or HTTP `503` | whether any trustworthy projection exists |
| Feed freshness | `live`, `delayed`, `stale` | what the observation source proves |
| Coverage | `complete`, `partial` | whether every requested symbol resolved |

The browser combines those facts with market session and its own lifecycle:

| Client state | Required behavior |
|---|---|
| `baked` | complete durable baseline before live activation or when live display is disabled |
| `loading` | baseline remains while one bounded request is in flight |
| `live-complete` | atomically paint all rows; page-level live indicator permitted only while session is regular |
| `live-partial` | paint resolved rows atomically, keep missing rows baked, print `resolved/requested` |
| `delayed-complete` / `delayed-partial` | show delayed language and source time; never animate as live |
| `stale-complete` / `stale-partial` | unmistakable stale language; retain last-good only inside the hard client bound |
| `settled-complete` / `settled-partial` | session is closed and source is not stale; say settled close, never live market |
| `unavailable` | baseline remains; concise unavailable status |

These are presentation states, not server lifecycle or market authority. No state is inferred from HTTP `200` alone.

---

## 9. Time, ordering and correction semantics

### Clocks

Every implementation must keep separate:

- **market/source time** — when the upstream observation occurred;
- **receive time** — only when the canonical quote owner actually supplies one;
- **projection time** — when Macro built the public response;
- **paint time** — when the browser committed the new visible state;
- **baseline time** — when the durable page was generated.

The UI chooses its language from market/source time plus session and feed freshness, not from fetch/paint time.

### Session-aware freshness

During regular trading, a stalled print is a feed problem and the freshness budget is tight. After the market closes, the final regular-session print is supposed to stop; it remains a settled close rather than becoming stale minutes later. Pre/post/overnight observations are separate fields and states.

### Snapshot ordering

A browser controller accepts a response only when:

- the request belongs to the newest local controller generation;
- the symbol identity matches an exact requested DOM target;
- the item's source time is not older than the last committed source time for that symbol;
- the response passes full schema and coverage validation before any DOM write.

`snapshot_id` is never compared for ordering. R1A has no server sequence.

### Corrections

R1A remains stateless on the server:

- later local request generation + newer source time: accept;
- later local request generation + older source time: reject that item and record an out-of-order measurement;
- later local request generation + equal source time + equal revision: idempotent;
- later local request generation + equal source time + different revision: treat as a source correction, accept atomically and record `same_timestamp_revision_change` telemetry.

No `correction=true` claim is required from an upstream that does not supply one, and no browser/server correction ledger is created. The deterministic revision is an equality fingerprint only.

### Gaps and reconnect

R1A is snapshot-based: a fresh snapshot closes any prior client gap. R1B ordered deltas must add explicit contiguous stream sequence/gap handling, with a bounded snapshot resync. Never add a hidden durable replay cursor database solely for browser reconnect.

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
- no server sequence/cursor;
- no background durable queue.

This proves data/rights/time/browser/product semantics.

### R1B — ordered delta transport

Only after R1A production proof may a separate wave add shared SSE for one or more proven high-value projections. It must have:

- snapshot bootstrap;
- monotonically increasing **stream** sequence;
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

## 13. Rights, access, privacy and security

### Deliberate public boundary

R1A's quote-only API is deliberately public because:

- the Intelligence Hub HTML shell is anonymously reachable under the current serving law;
- the payload contains only allowlisted market observations, no intelligence rows/scores, user data or private state;
- the executed Massive enterprise redistribution addendum permits external API/display redistribution;
- the proven dossier projection already establishes the public, debranded, loopback-only pattern.

That decision must be explicit in the module docstring and pinned by an anonymous-access test. “No `Depends` happened to be added” is not an access policy.

The controller asset is presentation code required by the public shell. It must be added to `config/site_access.yml` **and** the byte-for-byte matching Caddy public-asset boundary in the same PR, with `tests/test_site_access_boundary.py` proving parity. Otherwise the shell can load while the controller is default-gated and silently inert.

### Data and abuse controls

- The Terminal Quote Plane remains credential/vendor owner.
- Macro consumes only loopback/private server output and returns a debranded allowlist.
- Vendor/source/basis/anchor names stay server-side even though attribution is not contractually required.
- No vendor key, internal host, path, raw upstream body or exception crosses the route.
- The route rejects redirect egress and non-loopback upstream configuration.
- Symbols are normalized by the existing safe-symbol contract, deduplicated and capped at 80.
- Rate limiting is **symbol-weighted**, not request-count-only: each unique requested symbol consumes one unit in bounded client and peer rolling budgets, preventing an 80-symbol batch from costing the same as one dossier read.
- The page's normal 60-second refresh and maximum rendered universe must fit comfortably inside the accepted budget; the exact limits are printed and mutation-tested.
- Response bodies and upstream reads have hard byte caps.
- Existing API no-store/cache policy applies.
- R1A uses no personal Portfolio/Watchlist state and adds no new privacy class.
- Any future personalized projection must use verified existing identity and owner-scoped state; it cannot reuse this public response as an entitlement shortcut.

---

## 14. Observability and SLOs

R1A must measure:

- request count;
- requested symbol-units;
- sanitized symbol count;
- upstream latency;
- total projection latency;
- availability/freshness/coverage axes;
- requested/resolved/live/delayed/stale/missing counts;
- same-timestamp revision changes;
- out-of-order item suppression counts;
- client first-paint and refresh success/failure;
- controller fallback reason;
- browser interaction continuity for ticker-to-Terminal.

Initial acceptance budgets, subject to measurement rather than silent retuning:

- route p95 under 2.5 seconds;
- one upstream batch read per browser refresh;
- no unbounded payload;
- zero false-live rows in adversarial fixtures;
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
| Upstream returns partial symbols | coverage=`partial`, denominator preserved, missing rows stay baked; freshness remains separately truthful |
| Unknown basis/session/clock | degrade item; never `live` |
| Source timestamp absent/unparseable | stale/unavailable according to contract, never assumed fresh |
| Late older request generation | suppress entire response |
| New request contains older item source time | suppress that item and recompute truthful coverage |
| Same source time, changed revision on later request | accept as correction and record telemetry |
| Future clock beyond tolerance | refuse live classification |
| Browser hidden | pause refresh; resume with one fresh snapshot |
| JavaScript disabled | baseline remains complete and honestly dated |
| Live-price user setting disabled | remain baked; no request |
| Controller asset gated/missing | serving-boundary test fails; production proof cannot pass |
| Route returns malformed schema/coverage math | reject entire response; retain last-good/baked |
| Existing Terminal click target | remains operative before and after price repaint |
| Coverage below useful threshold | partial or unavailable; never cosmetically complete/live |

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

One independently useful user vertical: canonical quote plane → bounded public batch projection → public controller asset → atomic Intelligence Hub display → production/browser proof.

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
- Separate page-level feed freshness, market session and coverage state.
- Deliberately public quote-only API and controller asset boundary.
- Bilingual dark/light desktop/narrow presentation.
- Existing ticker-to-Terminal action.
- Live, delayed, partial, stale, settled, unavailable and baked behavior.
- Browser, API, rights, access, abuse and telemetry proof.

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

R1A is not accepted until a real page proves, in normal and degraded states:

- visible values came from the canonical quote projection;
- quote, absolute move and percent are one internally consistent regular-session tuple;
- feed freshness, market session and coverage independently match item truth;
- anonymous shell can load the intended public controller and call the deliberately public route;
- weighted rate limits prevent batch amplification while normal cadence succeeds;
- the nightly order/scores/stages are byte/semantic invariant;
- one refresh produced one batch route call, not N card calls;
- a forced outage leaves the durable baseline usable;
- late/out-of-order responses cannot roll the page backward;
- equal-time changed-content correction can land without a server correction ledger;
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
- failure/time/correction/rights/access/one-DOM-owner rules are testable;
- the stateless snapshot carries no fake server sequence or correction authority;
- freshness, session and coverage are orthogonal rather than collapsed into a false-green status;
- the PR remains records-only and production inert;
- the worker/reviewer dialogue is explicitly closed.

After R0 acceptance and merge, R1A still requires a new child operation, lawful placement, ACK, separate START, code review, merge, deployment and production proof. R0 merge is architecture completion only.
