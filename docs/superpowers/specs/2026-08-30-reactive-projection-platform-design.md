# Reactive Projection R1A — Intelligence Hub Market Pulse Design

**Architecture parent:** `research/reactive_projection/MASTERMIND_REACTIVE_PROJECTION_PLATFORM_ARCHITECTURE_FREEZE_2026-08-30.md`  
**Operation parent:** `modernize-mastermind-architecture-20260830-sol-001`  
**Design state:** **FROZEN FOR IMPLEMENTATION AFTER R0 ACCEPTANCE**  
**Implementation state:** `NOT_BUILT`  
**Original archaeology base:** `mastermindx-market-intelligence/macro@20748fccbb9777f7e43c39acf19499bac4d011be`  
**Latest R0 correction procedure:** `mastermindx-market-intelligence/Mastermind@dcce6f7ab6efad360f4854d748ad0d65dc9e0f7c`

## 1. Observable capability

On `intelligence_hub.html`, every eligible US ticker that the nightly Intelligence Hub already chose shows a current regular-session price and coherent day move from the canonical Terminal Quote Plane. One compact page-level instrument separately states feed freshness, market session and coverage. The update is atomic and never changes intelligence ranking, stage, score, stance or entry state.

## 2. Why this is the first slice

This page already combines high-value intelligence with ticker interaction, but its user trust is weakened when current observations and nightly conclusions are visually indistinguishable. The dossier quote projection proved a safe server-side read-through pattern. R1A extends that existing owner to one page-wide, batched, visibly useful vertical.

It deliberately does not begin with a generic bus, streaming platform or site rewrite. R1A must prove product, access and truth semantics before infrastructure is generalized.

## 3. Component boundaries

### 3.1 Shared public quote semantics

Create or extract a pure module, provisionally:

```text
app/public_quote_projection.py
```

Responsibilities:

- validate/normalize an allowlisted US symbol;
- parse one Terminal Quote Plane row;
- distinguish feed freshness from market session;
- distinguish regular from extended fields;
- compute absolute move from price/reference;
- accept upstream percentage only when consistent, otherwise derive it;
- classify session-aware staleness;
- emit only public/debranded fields;
- return typed deterministic refusal codes.

Both `app/dossier_quote.py` and the R1A batch route use the same pure semantic owner. R1A must not copy the dossier's freshness/percent/session logic into a second implementation.

The extraction must preserve the dossier API's public schema and behavior byte-for-semantic-byte. Existing dossier tests are regression authority. The shared internal vocabulary stays aligned with the proven route:

```text
freshness = live | delayed | stale
session = regular | pre | post | closed
```

A UI may say “current” only when `freshness=live` and `session=regular`; it says “settled close” for a non-stale closed session.

### 3.2 Batch projection route

Create:

```text
app/intelligence_hub_market_pulse.py
```

Register it directly through the existing Macro FastAPI owner in `app/main.py`. Current deploy law already restarts Macro API for `app/*.py`; only change `app/deploy/update.sh` if fresh current-main inspection disproves that fact.

Public contract:

```http
GET /api/intelligence-hub/market-pulse?symbols=NVDA,AAPL,MSFT
```

#### Access decision

The route is **deliberately public**, not accidentally unauthenticated:

- the Intelligence Hub HTML shell is anonymously reachable under current serving law;
- the response contains quote observations only—no intelligence rows/scores, personal data or private state;
- the repository licensing record permits external API/display redistribution;
- the public dossier projection is the existing precedent.

The module docstring must print this decision and tests must prove anonymous access. Absence of `Depends(...)` by accident is a defect.

#### Constraints

- GET/read-only;
- 1–80 unique normalized US symbols;
- input order preserved in output/accounting;
- one upstream Quote Hub request for the full set;
- loopback-only upstream;
- 2.5-second upstream timeout;
- 256 KiB upstream response cap;
- redirects refused;
- no retry;
- existing API `private, no-store` middleware;
- route-local **symbol-weighted** client and peer rolling budgets, where each unique requested symbol consumes one unit;
- bounded key/cardinality cleanup using the existing edge-resolved identity pattern;
- opaque error codes;
- provider names/keys/basis/anchor source removed.

The exact symbol-unit budgets must allow the largest intended page refresh at 60-second cadence with margin, while rejecting high-rate batch amplification. Tests pin both normal cadence and exhaustion.

#### Schema

R1A is a stateless snapshot. There is no server sequence/cursor and no server correction ledger.

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

Required arithmetic:

```text
resolved + missing == requested
live + delayed + stale == resolved
state.coverage = complete iff missing == 0, else partial
state.freshness = conservative worst freshness among resolved items
```

No majority rule may hide one delayed/stale row. Freshness and coverage are independent; a response may be `live + partial` or `delayed + complete`.

#### HTTP behavior

- `200` for at least one trustworthy item, whether coverage is complete or partial.
- `400` for invalid query shape, empty list, >80 unique symbols or invalid symbol.
- `429` through symbol-weighted limiter semantics.
- `503` when no trustworthy item exists.
- Malformed/oversized/redirected upstream is `503`, not a plausible empty `200`.

### 3.3 Durable page markup

Modify:

```text
templates/intelligence_hub.html.j2
```

The builder already knows surfaced tickers and nightly display prices. It must render:

- one compact Market Pulse instrument near the page command/state area;
- explicit baseline as-of text;
- separate slots for feed freshness, session and coverage;
- stable quote clusters for each eligible row;
- data attributes containing canonical symbol and baseline values;
- distinct controller selectors, not the generic `.nb-px` ownership selector;
- accessible live-region status with non-spammy `aria-live="polite"`;
- no JavaScript-generated primary markup.

The row quote cluster includes:

- price;
- absolute move;
- percent move;
- existing ticker label/anchor controlled by shared Terminal routing.

Rows without a valid nightly quote still render their ticker/intelligence content; their live quote slot uses an honest em dash.

### 3.4 Route-scoped browser controller

Create:

```text
site/assets/js/intelligence-hub-market-pulse.js
```

Export:

```javascript
window.IntelligenceHubMarketPulse = {
  refresh: function refresh() {},
  pause: function pause() {},
  resume: function resume() {},
  state: function state() {}
};
```

Responsibilities:

1. Discover eligible row targets and unique symbols.
2. Make one batch request.
3. Validate schema, projection identity, three state axes, coverage arithmetic and item identities.
4. Build an immutable candidate view model.
5. Reject responses from stale local request generations.
6. Enforce per-symbol source-time/revision ordering.
7. Commit page state and all accepted row values in one `requestAnimationFrame`.
8. Preserve baked values for missing rows under partial coverage.
9. Pause while `document.hidden`; issue one immediate refresh on visibility resume.
10. Respect the existing live-prices user setting.
11. Expose state for tests/diagnostics without becoming a durable store.

Refresh cadence starts at 60 seconds because that matches the existing product cadence and limits load. The implementation must not shorten it without production measurement. Only one in-flight request exists. A new manual/resume refresh aborts the old request and increments a **local** generation; an aborted or older-generation response has no effect.

The controller may retain one in-memory last-good response and per-symbol `{observedAt, revision}` map for the current page lifetime. It may not use localStorage, IndexedDB or a service worker as a quote truth store.

Ordering rules:

- newer local generation + newer source time: accept;
- newer local generation + older source time: suppress item and recompute truthful coverage;
- equal source time + equal revision: idempotent;
- equal source time + changed revision in a later generation: accept as a correction and emit `same_timestamp_revision_change` telemetry.

`snapshot_id` is never an ordering key. R1A has no server sequence. R1B owns stream sequence if later commissioned.

### 3.5 Existing generic live controller interaction

R1A nodes must not carry `.nb-px[data-sym]` or `.nb-chg[data-sym]` if that would make `templates/live.js` a second owner. Reuse only pure formatting/semantic helpers after an explicit extraction, or implement route-local display formatting under the frozen schema.

The `.tk` ticker labels and `theme.js` Terminal overlay behavior remain unchanged. Price repaint must not consume click/pointer events or wrap the ticker in a second conflicting link.

### 3.6 Static asset serving boundary

The new controller is required presentation code for an anonymous-public HTML shell. Add the exact asset path to:

```text
config/site_access.yml
app/deploy/Caddyfile
```

The two lists must remain byte-for-byte aligned under the existing boundary test. This change exposes JavaScript presentation logic only; it does not expose any static signal payload. The quote route self-declares and tests its separate public API access policy.

## 4. User experience

### Initial/baked

- Page paints fully from static HTML.
- Status: “Prices from the latest settled build” / equivalent Chinese.
- The baseline timestamp is visible.
- No false pulse animation.

### Loading

- Baseline remains.
- Status quietly says “Checking current prices.”
- No skeleton that hides intelligence.
- No per-row spinner.

### Live + complete

- One atomic update changes all price/move clusters.
- Status says “Live market pulse · 30/30 names.”
- The live indicator may animate only while the market session is regular.
- Intelligence score/order/stage remains fixed.

### Live + partial

- Resolved rows update together.
- Missing rows keep baseline values.
- Status says “Live prices for 27 of 30 names.”
- Coverage detail remains visible; feed freshness is still live.

### Delayed

- Rows update with valid delayed values.
- Status combines both axes, e.g. “Delayed prices · 27/30 names.”
- Source time is disclosed in plain language.
- No green live pulse.

### Settled

- Session is closed and the source row is not stale.
- Status says “Settled close · 30/30 names” (or partial equivalent).
- The regular-session close and day move remain valid; no open-market animation.

### Stale

- Last-good layer may remain visible only with unmistakable stale status and time.
- After the hard client bound, return to baked values.
- A settled close is not stale merely because the exchange is closed.

### Unavailable

- Baseline remains.
- Status says current prices are temporarily unavailable.
- Ticker-to-Terminal action still works.

### Live disabled

- No network request.
- Status remains baseline and indicates live prices are disabled in settings where useful.

## 5. Dark and light art directions

### Dark — command center

- Existing graphite canvas/panel depth.
- Live status uses restrained luminance and the semantic health token, not broad glow.
- Price/move remains numerically dominant but secondary to the page's intelligence hierarchy.
- Delayed/partial/stale use semantic rails and plain words.

### Light — research workspace

- White material on cool canvas, hairline border and measured shadow.
- No copied dark glow or dirty transparent wash.
- Status uses a quiet left rail/background tint and deep ink.
- Direction colors use `--ink-up`/`--ink-down` and preserve the Chinese red-up/green-down flip.
- Neutral/baseline state remains legible against white without relying on opacity alone.

No new token root, literal palette family or runtime stylesheet. Reuse existing theme tokens and canonical component geometry.

## 6. Responsive and language behavior

Evidence matrix:

```text
dark/light × EN/ZH × desktop 1440 × narrow 390
```

Also verify:

- 820/tablet behavior if the row layout changes;
- 200% zoom;
- reduced motion;
- keyboard focus and screen-reader status;
- long Chinese labels;
- no horizontal page overflow.

On narrow screens:

- page-level status becomes a compact two-line instrument;
- row quote cluster remains together;
- absolute move may demote visually but cannot disagree with percent;
- no independent cards are added solely to fit mobile.

## 7. Data and identity rules

- Symbols come from server-rendered nightly markup, not a free-form user input.
- Client query is built from those exact canonical symbols and deduplicated.
- Server revalidates every symbol.
- Response items not requested make the response malformed; they are not silently accepted.
- Duplicate response symbols make the response malformed.
- Output order follows request order.
- Currency is allowlisted; unknown currency prints no guessed glyph.
- Numbers must be finite; booleans, strings, NaN and Infinity are invalid.
- Negative prices/references are invalid.
- Zero reference cannot produce a percentage.
- A `-100%` reconstruction division is refused.
- Extended-session fields are never rendered as regular day move.

## 8. Freshness and correction

The shared projector must preserve the dossier's proven landmines:

- upstream `chg` is percentage, not dollar change;
- upstream `ts` is the market print clock, not fetch time;
- after close, that print clock legitimately stops;
- `regularSession` describes regular-session state, not necessarily the provenance of the primary field;
- regular and extended moves can have opposite signs;
- unrecognized realtime basis fails closed.

Client correction/order rules are local and stateless as defined in §3.4. The canonical upstream owns source correction; the browser prevents visual regression within its own page lifetime. It never claims a durable correction ledger.

## 9. Failure and abuse controls

- Symbol cap and length validation.
- Symbol-weighted client and peer rate limits.
- One request per refresh; no per-row calls.
- One in-flight request; AbortController on supersession.
- Loopback assertion per request.
- No redirect opener.
- Bounded read.
- Opaque logs and public errors.
- No response caching across users/visitors at an edge.
- No provider brand on public UI or payload.
- No raw upstream logging in normal operation.
- Controller catches all failures and leaves baseline usable.
- No retry loop faster than normal cadence.
- Public controller/Caddy/site-access parity is tested.

## 10. Testing strategy

### Shared semantic tests

- Dossier fixtures remain green after extraction.
- `chg`-as-percent discriminator.
- closed-session settled close not stale.
- delayed basis cannot become live.
- missing/unknown clock fails downward.
- opposite-sign extended fields are ignored.
- degenerate `prevClose == price` with previous-session move stays coherent.
- future/NaN/boolean/unknown basis refusal.
- mutation tests delete each load-bearing guard and red the suite.

### Batch API tests

- deliberately public anonymous access is explicit and stable;
- one upstream call for 30 symbols;
- order/dedupe/80-symbol cap;
- complete/partial/zero-usable responses;
- exact orthogonal state and coverage arithmetic;
- upstream redirect/timeout/oversize/malformed JSON;
- provider fields absent;
- symbol-weighted rate limiting and normal-cadence allowance;
- no retry;
- session-aware mixed states;
- schema and opaque errors;
- no server sequence/cursor/correction state.

### Serving-boundary tests

- controller asset appears in `config/site_access.yml` and matching Caddy list;
- anonymous request receives JavaScript, not registration/paywall content;
- quote-only API route is intentionally public;
- no signal-bearing JSON path is opened by the change.

### Surface tests

- durable quote/status markup exists for command/emerging/discovery rows;
- no R1A node matches generic live.js owner selectors;
- ticker `.tk` routing contract remains;
- both languages present;
- no title-attribute i18n leak;
- theme treatments use governed CSS, not runtime injected stylesheet.

### Controller tests

- one fetch, not N;
- hidden tab pause/resume;
- disabled-live no request;
- atomic requestAnimationFrame commit;
- partial keeps missing baked rows;
- malformed envelope/coverage no repaint;
- stale local generation suppression;
- older source-time item suppression with truthful coverage recompute;
- equal-time changed revision correction acceptance;
- snapshot id never used for order;
- unavailable and last-good aging;
- no score/order/stage mutation;
- ticker click route unaffected.

### Browser/production proof

- real route response from the served origin as anonymous and signed-in clients;
- controller asset loads from the anonymous shell;
- one network call per refresh;
- visible tuple consistency;
- live/delayed/partial/settled/unavailable states;
- dark/light × EN/ZH × 1440/390 screenshots;
- zero console errors and horizontal overflow;
- page source/order/score fingerprint unchanged;
- live setting and background-tab behavior;
- actual ticker opens Terminal.

## 11. Deployment and rollback

Deployment uses the existing Macro merge/render/API restart paths. Current `app/deploy/update.sh` already restarts Macro API for `app/*.py`; implementation must verify that current fact rather than edit the deploy owner reflexively. The controller must be added to the existing public asset boundary and cache-stamp path.

Canary:

1. merge reviewed exact head;
2. deploy API and static assets through existing path;
3. verify `/api/health` running commit;
4. verify anonymous route and controller access;
5. verify one known ticker tuple against canonical hub;
6. open Intelligence Hub with cache-busted assets;
7. run browser matrix and failure drills;
8. observe symbol-unit budgets, telemetry and error rate.

Rollback:

- server feature flag or route-disable setting makes controller remain baked;
- remove controller include to stop requests;
- baseline remains complete throughout;
- public asset-list entry may remain harmless presentation code or be removed with matching Caddy parity;
- no data migration or durable live state to unwind.

## 12. R1B hold

Do not add SSE/WebSocket in R1A. R1B is commissioned only after Sol accepts R1A production proof and measurement shows snapshot pull cannot meet the user/cost target. R1B must reuse these semantics and add only ordered stream transport, heartbeat, gap resync and backpressure—not a new quote owner.
