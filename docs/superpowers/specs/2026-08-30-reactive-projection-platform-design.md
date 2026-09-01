# Reactive Projection R1A — Intelligence Hub Market Pulse Design

**Architecture parent:** `research/reactive_projection/MASTERMIND_REACTIVE_PROJECTION_PLATFORM_ARCHITECTURE_FREEZE_2026-08-30.md`  
**Program:** `modernize-mastermind-architecture-20260830-sol-001`  
**Design state:** **FROZEN FOR IMPLEMENTATION AFTER R0 ACCEPTANCE**  
**Implementation state:** `NOT_BUILT`  
**Macro records carrier:** `sol/reactive-projection-platform-r0-20260830` / PR `#6707`  
**Protected procedure:** `mastermindx-market-intelligence/Mastermind@990b5b6c10ca9acb2f5fa42405c688c3b2abe2fc` at freeze; re-pinned `@187490f3d5676adf7a249d69afacedd00b3efcec` at the 2026-09-01 main rejoin  
**Macro archaeology pin for this correction:** R0 head `8cd1ac766f544e6615366b7ba21c7d8d0182bda9`  
**Terminal archaeology pin:** `mastermindx-market-intelligence/mastermind-terminal@86a75b68c273a592a41af5e322f95aab242b8297`

## 1. Observable capability

On `intelligence_hub.html`, the exact US names rendered in Command, Emerging and diversified Discovery views show current regular-session price and coherent day move from the canonical Terminal Quote Plane. One compact page-level instrument separately reports feed freshness, market session and unique-symbol coverage. Every occurrence of a symbol updates atomically. Intelligence rank, order, score, stage, stance, Prophet state, entry state, allocation and trade authority remain unchanged.

## 2. Why this is the first slice

The Intelligence Hub already combines high-value intelligence with ticker-to-Terminal interaction. Its trust gap is that nightly conclusions and current observations are visually conflated. The existing dossier route proves that Macro can safely project a debranded regular-session tuple from Terminal. R1A turns that precedent into one page-complete workflow.

R1A does not begin with a generic bus, streaming platform, SPA rewrite or database. It first proves:

- source ownership;
- non-disruptive quote demand;
- exact rendered population;
- clock, correction and coverage semantics;
- public rights/access/abuse boundaries;
- one DOM owner;
- coherent normal and degraded experience;
- production falsifiability.

## 3. Ordered child operations

R1A is one user capability but requires two modifying children because GitHub ownership spans two repositories and one logical modification binds to one carrier.

### R1A-T — Terminal regular-only owner contract

Repository: `mastermindx-market-intelligence/mastermind-terminal`.

Mission:

> Extend the existing loopback `/quotes` endpoint with a closed `view=regular` option that preserves regular quote demand and response semantics while producing zero extended-hours demand or fields.

This child stops after reviewed merge, host deployment and loopback production proof. It does not edit Macro or create the user-facing Market Pulse.

### R1A-M — Macro Market Pulse consumer

Repository: `mastermindx-market-intelligence/macro`.

Mission:

> Consume only the production-proven Terminal `view=regular` contract, expose one bounded debranded public batch projection, hydrate the exact rendered Intelligence Hub roster, and prove the full browser journey.

R1A-M cannot START merely because R1A-T code exists. It requires R1A-T merged/deployed/proven and its own operation/carrier/receiver/ACK/START.

## 4. Exact rendered roster

The roster is the ordered unique union of:

```text
hub.command[:30]
hub.emerging[:14]
hub.discovery[:14]
```

`hub.discovery` is the builder's existing diversified presentation list — `engine/intel_hub.py` builds it internally as the local `discovery_shown` and exports it under the key `discovery`. It does not mean the full Discovery candidate corpus.

Rules:

- At most 58 unique candidates before dedupe.
- API cap: 60 unique symbols.
- First rendered occurrence establishes request order.
- Coverage counts unique symbols, not DOM nodes.
- `exhausted`, catalyst-only and hidden Discovery names are excluded.
- Non-US-routable symbols are excluded from the request set and from the coverage denominator, and carry no Market Pulse cluster (Terminal omits `cn/hk/ca` routes from the flat response; the batch route validates US symbols only).
- A symbol may appear in several panels; all of its targets form one atomic visual unit.
- The nightly builder remains roster and baseline authority.

## 5. Terminal owner extension

### 5.1 Current problem

At the Terminal archaeology pin:

- `hub/hub.js::handleQuotes()` calls `applyDemand()` for every requested symbol.
- `hub/lib/quotes.js::applyDemand()` sends each US symbol to SnapshotFeed, Polygon, AnchorCache and `ExtFeed` while the Polygon leg is healthy.
- `hub/lib/extfeed.js::ExtFeed` is a global singleton with a 30-symbol LRU shared by all users.
- Ordinary `/quotes` therefore spends and refreshes extended-hours slots even when a caller needs only regular-session fields.

A public 60-second refresh over up to 58 Intelligence Hub names would churn that LRU and evict active Terminal demand outside regular hours. Dropping `ext*` fields in Macro does not prevent the demand-side effect.

### 5.2 Frozen endpoint contract

Existing default:

```http
GET /quotes?syms=NVDA,AAPL
GET /quotes?syms=NVDA,AAPL&view=full
```

New closed option:

```http
GET /quotes?syms=NVDA,AAPL&view=regular
```

Allowed view vocabulary:

```text
full | regular
```

Missing view is exactly `full`. Unknown or repeated-conflicting view input is HTTP `400` with an opaque error.

### 5.3 `view=regular` behavior

For every eligible US symbol:

- `snapshotFeed.demand(sym, now)` still runs;
- healthy Polygon subscription still runs;
- AnchorCache warm still runs;
- `extFeed.demand(sym)` does **not** run;
- response assembly does not receive/use `extFeed`;
- every extended-hours key (`extPrice`, `extChg`, `extTs`, `extSession`, `extSource`, `extBasis`) is stripped from every returned row before serialization — the regular view is closed at both boundaries: zero ExtFeed demand/read, and no `ext*` key in any emitted row even when a Store test double or legacy Store row already contains one;
- the flat `{SYM: quote}` and present-entries-only response contract remains unchanged;
- crypto/macro/daily-only/non-US routing remains exactly as current code defines it;
- no second route, feed, store, cache, scheduler, service or credential is created.

The default full view must remain byte-for-semantic compatible with existing callers and tests.

### 5.4 Suggested pure interfaces

Modify the current owners rather than branching around them:

```javascript
function parseQuoteView(rawValues) {
  // takes url.searchParams.getAll("view"); returns "full" | "regular",
  // or null for unknown/conflicting/repeated-invalid input (caller sends 400)
}

function applyDemand(syms, nowMs, deps = {}, options = { includeExtended: true }) {}

function buildQuotesResponse(
  syms,
  nowMs,
  deps = {},
  options = { includeExtended: true }
) {}
```

The exact parameter shape may be simplified during implementation, but the behavioral contract is frozen. `view=regular` must mechanically map to `includeExtended=false` in both demand and response assembly. It must not rely on current clock/session to skip demand.

### 5.5 Terminal acceptance tests

Extend `hub/tests/quotes.test.js`. Endpoint-level coverage is MANDATORY, not optional: the `make unknown view default to full` and `make default view regular` mutations live in `hub/hub.js` wiring, so at least one test must drive `handleQuotes` (or an equivalent seam over the real wiring) and prove `?view=regular` produces zero `extFeed.demand` calls, `?view=full` and a missing `view` still produce them, and an unknown `view` returns 400 — a pure-library suite cannot catch an inverted boolean at the wiring layer.

Required discriminators:

```javascript
it("regular view keeps regular demand and spends zero ext slots", () => {
  applyDemand(["AAPL", "NVDA"], NOW, deps, { includeExtended: false });
  assert.deepEqual(seen.snapshot, ["AAPL", "NVDA"]);
  assert.deepEqual(seen.polygon, ["AAPL", "NVDA"]);
  assert.deepEqual(seen.anchor, ["AAPL", "NVDA"]);
  assert.deepEqual(seen.ext, []);
});

it("regular response never merges ext fields", () => {
  const out = buildQuotesResponse(["AAPL"], NOW, deps, { includeExtended: false });
  assert.equal(calls.storeExtFeed, null);
  assert.equal("extPrice" in out.AAPL, false);
});

it("view=regular strips ext fields even when Store returns a legacy row containing them", () => {
  const store = {
    getQuotes() {
      return { NVDA: {
        sym: "NVDA", last: 100, prevClose: 95, chg: 5.263,
        ts: 1, basis: "LIVE", source: "polygon",
        extPrice: 101, extChg: 1, extTs: 2,
        extSession: "post", extSource: "webull",
      }};
    },
  };
  const out = buildQuotesResponse(["NVDA"], NOW, { store }, { includeExtended: false });
  assert.equal(Object.keys(out.NVDA).some((k) => k.startsWith("ext")), false);
});

it("default full view remains unchanged", () => {
  // existing response and ext-demand fixtures remain byte/semantic equal
});
```

Mutation tests must fail when:

- regular mode calls `extFeed.demand()`;
- regular response passes `extFeed` into Store;
- regular response returns a legacy Store row's `ext*` keys unstripped;
- unknown view silently becomes full;
- full default stops demanding/merging extended fields;
- regular mode skips SnapshotFeed/Polygon/AnchorCache.

Production proof on the actual Terminal host must compare ExtFeed health/LRU membership immediately before and after a 58-symbol regular-view request and show no change attributable to that request.

## 6. Shared Macro public quote semantics

Create or extract:

```text
app/public_quote_projection.py
```

Responsibilities:

- validate/normalize one allowlisted US symbol;
- parse one Terminal regular-view row;
- separate feed freshness from market session;
- compute absolute move from price and regular reference;
- treat upstream `chg` as percent, never dollars;
- classify session-aware staleness;
- emit only public/debranded fields;
- return typed deterministic refusal codes.

Both `app/dossier_quote.py` and R1A-M use this owner. The extraction must preserve the dossier API's public schema and semantics.

Internal vocabulary:

```text
freshness = live | delayed | stale
session = regular | pre | post | closed
```

A UI may say “live” only for `freshness=live && session=regular`. A non-stale closed regular row is a settled close.

## 7. Macro batch projection route

Create:

```text
app/intelligence_hub_market_pulse.py
```

Register directly in `app/main.py` under existing API ownership.

Public contract:

```http
GET /api/intelligence-hub/market-pulse?symbols=NVDA,AAPL,MSFT
```

### 7.1 Deliberate access decision

The route is deliberately public because:

- the Intelligence Hub shell is public;
- the response contains allowlisted quote observations only;
- it contains no intelligence rows/scores, personal data or private state;
- the enterprise entitlement record permits external display/API redistribution;
- the dossier route is the existing debranded precedent.

The module docstring and anonymous-access test must print this decision. Accidental absence of auth is a defect.

### 7.2 Constraints

- GET/read-only.
- 1–60 unique normalized US symbols.
- Input order preserved.
- One Terminal request for the full set:

```http
/quotes?syms=<CSV>&view=regular
```

- No fallback to missing/default/full view.
- Require proof that returned rows contain no `ext*` field; any such field is a contract failure.
- Loopback-only upstream.
- 2.5-second timeout.
- 256 KiB read cap.
- Redirects refused.
- No retry.
- Existing private/no-store API middleware.
- Symbol-weighted client and peer rolling budgets; one unique symbol consumes one unit.
- Bounded identity-cardinality cleanup.
- Opaque errors.
- No provider/source/basis/anchor-source field in public output.

The budgets must allow the 58-name page at 60-second cadence plus bounded manual/resume refreshes while rejecting amplification.

### 7.3 Stateless schema

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
    "requested": 3,
    "resolved": 2,
    "live": 2,
    "delayed": 0,
    "stale": 0,
    "missing": 1
  },
  "items": [
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
      "regular_session_date": "2026-08-28",
      "revision": "opaque-content-fingerprint"
    }
  ],
  "errors": [{"symbol":"MSFT","code":"quote_unavailable"}]
}
```

Laws:

```text
resolved + missing == requested
live + delayed + stale == resolved
coverage=complete iff missing=0
freshness=conservative worst resolved item
page session=regular only when every resolved item session=regular; any mix renders conservative mixed/settled language, never live/regular
source_view must equal regular
```

There is no server sequence, cursor or correction ledger. `snapshot_id` is identity only.

HTTP:

- `200` when at least one trustworthy item exists.
- `400` invalid query, empty, >60 unique or invalid symbol.
- `429` symbol-weighted budget exceeded.
- `503` no trustworthy item, unsupported Terminal regular view, ext-field leak, malformed/oversized/redirected upstream.

## 8. Durable page markup

Modify:

```text
templates/intelligence_hub.html.j2
```

Render:

- one compact page-level Market Pulse instrument;
- baseline as-of text;
- separate availability/freshness/session/coverage slots;
- quote clusters for exact roster rows;
- canonical symbol and baseline-value data attributes;
- distinct R1A selectors, never generic `.nb-px[data-sym]` / `.nb-chg[data-sym]` ownership selectors;
- `aria-live="polite"` on one non-spammy status;
- complete primary markup before JavaScript.

Each eligible occurrence carries:

```text
data-ihmp-symbol
[data-ihmp-price]
[data-ihmp-abs]
[data-ihmp-pct]
```

The ticker `.tk` and existing Terminal-open interaction remain unchanged.

## 9. Route-scoped browser controller

Create:

```text
site/assets/js/intelligence-hub-market-pulse.js
```

Expose:

```javascript
window.IntelligenceHubMarketPulse = {
  refresh() {},
  pause() {},
  resume() {},
  state() {}
};
```

Responsibilities:

1. Traverse eligible roster targets in rendered order.
2. Build `Map<string, HTMLElement[]>` and ordered unique symbols.
3. Refuse more than 58 rendered unique symbols even though the route cap is 60.
4. Make one batch request.
5. Validate exact schema, projection, `source_view=regular`, state axes, arithmetic, identities and absence of forbidden fields.
6. Build an immutable candidate model before DOM mutation.
7. Reject stale local request generations.
8. Enforce per-symbol source-time/revision ordering.
9. Recompute truthful coverage after any item suppression.
10. Commit state and every occurrence of every accepted symbol in one `requestAnimationFrame`.
11. Preserve baked values for missing/suppressed rows.
12. Pause while hidden; issue one immediate refresh on visibility resume.
13. Respect the existing live-prices setting.
14. Retain only page-lifetime in-memory last-good/order state.

Refresh cadence: 60 seconds. One in-flight request. Manual/resume refresh aborts the old request and increments local generation. No localStorage, IndexedDB, service worker, queue or background truth store.

Ordering:

- newer generation + newer source time: accept;
- newer generation + older source time: suppress;
- equal source time + equal revision: idempotent;
- equal source time + changed revision on a later generation: correction; accept and measure.

Every DOM occurrence receives the same accepted tuple in the same frame. `snapshot_id` is not an ordering key.

## 10. Generic controller and serving boundary

R1A target nodes must not be owned by `templates/live.js`. Pure formatters may be shared only after explicit extraction.

Node-disjointness alone is not compliance. Generic `live.js` repaints `.nb-px[data-sym]` on the current Command/Emerging/Discovery rows today (wired once through the global nav include), so R1A-M must remove that generic markup from the roster rows it takes over: the rendered Intelligence Hub page contains zero `.nb-px[data-sym]` quote nodes, generic `live.js` issues zero quote fetches on this route, and each roster row shows exactly one visible price — the R1A instrument.

The new controller path must be listed in both:

```text
config/site_access.yml
app/deploy/Caddyfile
```

No broad `/assets/` or signal-data prefix may be opened. `tests/test_site_access_boundary.py` must prove byte-for-byte parity and anonymous JavaScript delivery.

## 11. User states

### Baked

Complete nightly page, baseline timestamp, no network when live setting is disabled.

### Loading

Baseline remains; one quiet “Checking current prices” status; no row spinners or intelligence skeleton removal.

### Live complete / partial

All accepted occurrences paint atomically. Partial leaves missing rows baked and prints unique coverage. Animation is allowed only for live+regular.

### Delayed complete / partial

Values may update, but delayed language and source time are explicit. No live animation.

### Settled complete / partial

Closed market with a non-stale regular print. Say “Settled close,” never “Live market.”

### Stale

Last-good may remain only within a hard client bound with unmistakable stale status; then return to baked values.

### Unavailable

Baseline and ticker interaction remain; concise current-price unavailable status.

## 12. Dark, light, responsive and language

Evidence matrix:

```text
dark/light × EN/ZH × 1440/390
```

Also verify 820 where layout changes, 200% zoom, reduced motion, keyboard/screen-reader behavior, long Chinese labels and zero horizontal overflow.

Dark is a graphite command instrument with restrained semantic luminance. Light is a white research material on cool canvas with hairline/shadow and no translated glow. Use `--ink-up` / `--ink-down` so Chinese direction-color semantics remain correct. Add no token root, literal palette family or runtime stylesheet.

## 13. Data and identity rules

- Symbols originate in server-rendered roster markup, not free-form input.
- Client deduplicates by exact canonical symbol and keeps all target occurrences.
- Server independently validates every symbol.
- Unrequested or duplicate response symbols invalidate the envelope.
- Output follows request order.
- Currency is allowlisted; unknown currency gets no guessed glyph.
- Numeric values must be finite; booleans/strings/NaN/Infinity are invalid.
- Negative price/reference is invalid.
- Zero reference cannot produce percentage.
- `-100%` reconstruction division is refused.
- Extended fields in a regular-view response invalidate the upstream contract.

## 14. Freshness and correction landmines

The shared projector must preserve:

- `chg` is percent;
- `ts` is market/source print time, not fetch time;
- a final regular print legitimately stops after close;
- `regularSession` does not prove the provenance of every primary field;
- regular and extended moves can have opposite signs;
- unknown realtime basis fails closed;
- request/projection time never refreshes source freshness;
- `view=regular` must not merely hide ext fields after spending ext demand.

## 15. Failure and abuse controls

- 60-symbol cap and length validation.
- Symbol-weighted client/peer budgets.
- One browser request and one Terminal request per refresh.
- One in-flight browser request.
- Loopback assertion per server request.
- Refuse redirects.
- Bounded read.
- Opaque logs/errors.
- No edge response caching.
- No provider brand or raw upstream body.
- No retries faster than normal cadence.
- No fallback from regular to full view.
- Controller failure leaves baseline usable.
- Public asset/Caddy parity test.

## 16. Test matrix

### Terminal R1A-T

- closed view parser;
- default full compatibility;
- regular demand keeps SnapshotFeed/Polygon/AnchorCache;
- regular demand calls ExtFeed zero times;
- regular response receives no ExtFeed and emits no ext field;
- 58-symbol regular call leaves ext LRU membership/order unchanged;
- endpoint-level `handleQuotes` coverage: regular → zero ext demand, full/missing → ext demand, unknown view → 400;
- invalid/conflicting view refuses;
- existing `hub/tests/quotes.test.js` and `hub/tests/extfeed.test.js` stay green;
- mutation proof for every load-bearing branch.

### Shared Macro semantics

- dossier regressions;
- percent-vs-dollar discriminator;
- closed settled freshness;
- delayed cannot become live;
- missing clock fails downward;
- extended opposite-sign fields ignored/refused;
- future/NaN/boolean/unknown basis refusal.

### Macro batch API

- one Terminal call with `view=regular` for up to 58 names;
- no fallback full call;
- deliberate anonymous access;
- order/dedupe/60 cap;
- complete/partial/zero usable;
- exact state arithmetic;
- ext-field leak refusal;
- redirect/timeout/oversize/malformed;
- debranding;
- symbol-weighted limit;
- no retry/sequence/cursor/correction store.

### Surface and controller

- exact Command/Emerging/Discovery roster;
- one symbol to many targets;
- generic live owner exclusion;
- ticker routing unchanged;
- EN/ZH and governed themes;
- one fetch, hidden pause/resume and live-disabled no request;
- atomic RAF commit;
- partial keeps baked missing rows;
- stale generation/source suppression;
- equal-time revision correction;
- score/order/stage immutability.

### Production/browser proof

- Terminal host regular-view no-LRU-effect canary;
- the same canary records Polygon subscription-map size/membership and SnapshotFeed pending/flush counters, unchanged or bounded per the freeze §5 ruling;
- real public Macro route and controller;
- one browser call / one Terminal call;
- zero generic `live.js` quote fetches and zero `.nb-px[data-sym]` quote nodes on the rendered hub page;
- visible tuple coherence;
- normal, delayed, partial, settled, malformed/upstream-unavailable states;
- dark/light × EN/ZH × 1440/390;
- zero console errors/overflow;
- intelligence fingerprint unchanged;
- ticker opens Terminal.

## 17. Deployment, canary and rollback

### R1A-T

Deploy through the existing Terminal hub owner. Verify running commit, default full behavior, regular-view contract, no ExtFeed LRU change and health. Roll back the Terminal commit if any existing caller or demand behavior regresses.

### R1A-M

Deploy through existing Macro API/static/render paths. Verify API running commit, public asset and route, cache stamps, known tuple, browser matrix and symbol-unit/error telemetry.

Feature disable makes the page remain baked. There is no database migration or durable live state to unwind.

## 18. R1B hold

R1A contains no SSE/WebSocket. R1B starts only after Sol accepts R1A production proof and measurement shows snapshot pull cannot meet the user/cost target. It must reuse this semantic contract and add only ordered stream transport, heartbeat, gap resync and backpressure.
