# Reactive Projection R1A — Intelligence Hub Market Pulse Design

**Architecture parent:** `research/reactive_projection/MASTERMIND_REACTIVE_PROJECTION_PLATFORM_ARCHITECTURE_FREEZE_2026-08-30.md`  
**Operation parent:** `modernize-mastermind-architecture-20260830-sol-001`  
**Design state:** **FROZEN FOR IMPLEMENTATION AFTER R0 ACCEPTANCE**  
**Implementation state:** `NOT_BUILT`  
**Base examined:** `mastermindx-market-intelligence/macro@20748fccbb9777f7e43c39acf19499bac4d011be`  
**Protected procedure:** `mastermindx-market-intelligence/Mastermind@eccf0a3fae8b8597c2ad0bc4f830e31b220415d2`

## 1. Observable capability

On `intelligence_hub.html`, every US ticker that the nightly Intelligence Hub already chose shows a current regular-session price and coherent day move from the canonical Terminal Quote Plane. One compact page-level status states whether the pulse is current, delayed, partial, stale, unavailable or still the baked baseline. The update is atomic and never changes intelligence ranking, stage, score, stance or entry state.

## 2. Why this is the first slice

This page already combines high-value intelligence with ticker interaction, but its user trust is weakened when current observations and nightly conclusions are visually indistinguishable. The dossier quote projection proved a safe server-side read-through pattern. R1A extends that existing owner to one page-wide, batched, visibly useful vertical.

It deliberately does not begin with a generic bus, streaming platform or site rewrite. R1A must prove the product and truth semantics before infrastructure is generalized.

## 3. Component boundaries

### 3.1 Shared public quote semantics

Create or extract a pure module, provisionally:

```text
app/public_quote_projection.py
```

Responsibilities:

- validate/normalize an allowlisted US symbol;
- parse one Terminal Quote Plane row;
- distinguish regular from extended session;
- compute absolute move from price/reference;
- accept upstream percentage only when consistent, otherwise derive it;
- classify source/session-aware freshness;
- emit only public/debranded fields;
- return typed deterministic refusal codes.

Both `app/dossier_quote.py` and the R1A batch route use the same pure semantic owner. R1A must not copy the dossier's freshness/percent/session logic into a second implementation.

The extraction must preserve the dossier API's public schema and behavior byte-for-semantic-byte. Existing dossier tests are regression authority.

### 3.2 Batch projection route

Create:

```text
app/intelligence_hub_market_pulse.py
```

Register through the existing Macro FastAPI app and deployment-restart mechanism.

Public contract:

```http
GET /api/intelligence-hub/market-pulse?symbols=NVDA,AAPL,MSFT
```

Constraints:

- GET/read-only, no auth required unless current product access law says the page itself is gated;
- 1–80 unique normalized US symbols;
- input order preserved in output/accounting;
- one upstream Quote Hub request for the full set;
- loopback-only upstream;
- 2.5-second upstream timeout;
- 256 KiB upstream response cap;
- redirects refused;
- no retry;
- existing API `private, no-store` middleware;
- existing client and peer rate-limit pattern;
- opaque error codes;
- provider names/keys/basis/anchor source removed.

Schema:

```json
{
  "schema": "intelligence_hub.market_pulse.v1",
  "projection": "intelligence_hub.market_pulse",
  "snapshot_id": "uuid-or-content-derived-opaque-id",
  "sequence": 1,
  "generated_at": "2026-08-31T14:31:10.214Z",
  "status": "partial",
  "coverage": {
    "requested": 3,
    "resolved": 2,
    "current": 2,
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
      "freshness": "current",
      "observed_at": "2026-08-28T19:55:58Z",
      "received_at": "2026-08-28T19:56:01Z",
      "regular_session_date": "2026-08-28",
      "revision": "opaque",
      "correction": false
    }
  ],
  "errors": [{"symbol":"MSFT","code":"quote_unavailable"}]
}
```

HTTP behavior:

- `200` for valid complete or partial projection.
- `400` for invalid query shape, empty list, >80 unique symbols or invalid symbol.
- `429` through existing limiter semantics.
- `503` when no upstream data can produce a trustworthy item.
- Malformed/oversized/redirected upstream is `503`, not a plausible empty `200`.

The route may emit `partial` only if at least one trustworthy item exists.

### 3.3 Durable page markup

Modify:

```text
templates/intelligence_hub.html.j2
```

The builder already knows surfaced tickers and nightly display prices. It must render:

- one compact Market Pulse status near the page command/state area;
- explicit baseline as-of text;
- stable quote clusters for each eligible row;
- data attributes containing canonical symbol and baseline values;
- distinct controller selectors, not the generic `.nb-px` ownership selector;
- accessible live-region status with non-spammy `aria-live="polite"`;
- no JavaScript-generated primary markup.

The row quote cluster includes:

- price;
- absolute move;
- percent move;
- compact freshness state at the page/panel level rather than a pulsing dot on every row;
- existing ticker label/anchor remains controlled by shared Terminal routing.

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
3. Validate schema, projection identity, coverage arithmetic and item identities.
4. Build an immutable candidate view model.
5. Reject stale generation/sequence/revision responses.
6. Commit status and all accepted row values in one `requestAnimationFrame`.
7. Preserve baked values for missing rows under `partial`.
8. Pause while `document.hidden`; issue one immediate refresh on visibility resume.
9. Respect the existing live-prices user setting.
10. Expose state for tests/diagnostics without becoming a durable store.

Refresh cadence starts at 60 seconds because that matches the existing product cadence and limits load. The implementation must not shorten it without production measurement. Only one in-flight request exists. A new manual/resume refresh aborts the old request and increments the local generation; an aborted old response has no effect.

The controller may retain one in-memory last-good response for the current page lifetime. It may not use localStorage/IndexedDB/service worker as a quote truth store.

### 3.5 Existing generic live controller interaction

R1A nodes must not carry `.nb-px[data-sym]` or `.nb-chg[data-sym]` if that would make `templates/live.js` a second owner. Reuse only pure formatting/semantic helpers after an explicit extraction, or implement route-local display formatting under the frozen schema.

The `.tk` ticker labels and `theme.js` Terminal overlay behavior remain unchanged. Price repaint must not consume click/pointer events or wrap the ticker in a second conflicting link.

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

### Current

- One atomic update changes price and move clusters.
- Status says “Current market pulse” with the observation time and `resolved/requested`.
- Only the page-level current indicator may animate, and only when source/session rules permit.
- Intelligence score/order/stage remains fixed.

### Delayed

- Rows update with valid delayed values.
- Status says “Delayed market pulse” and prints the delay/source-time meaning in plain language.
- No green live pulse.

### Partial

- Resolved rows update together.
- Missing rows keep baseline values and gain no per-row error essay.
- Status states “Current prices for 27 of 30 names” and the conservative freshness state.
- Tooltip/study detail may name missing codes.

### Stale

- Last-good current layer may remain visible only with an unmistakable stale status and time.
- After the design's hard stale bound, return to baked values rather than displaying an increasingly misleading current layer.
- Session-aware close semantics apply: a settled close is not stale merely because the exchange is closed.

### Unavailable

- Baseline remains.
- Status says current prices are temporarily unavailable.
- Ticker-to-Terminal action still works.

### Live disabled

- No network request.
- Status remains baseline and, where appropriate, indicates live prices are disabled in settings.

## 5. Dark and light art directions

### Dark — command center

- Existing graphite canvas/panel depth.
- Current status uses restrained luminance and the semantic current/health token, not broad glow.
- Price/move remains numerically dominant but secondary to the page's intelligence hierarchy.
- Delayed/partial/stale use semantic token rails and plain words.

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

- Symbols come from the server-rendered nightly surface, not user text.
- Client query is built from those exact canonical symbols and deduplicated.
- Server revalidates every symbol.
- Response items not requested are ignored and counted as contract violation.
- Duplicates are rejected or deterministically collapsed before coverage calculation.
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

Client correction rules:

- response generation older than current controller generation: discard;
- response sequence lower than committed: discard;
- same symbol + lower source revision/time without `correction=true`: discard;
- explicit correction with winning revision: accept;
- all accepted items commit atomically.

R1A does not persist a correction ledger. The canonical upstream owns source correction; the browser only prevents visual regression within its session.

## 9. Failure and abuse controls

- Symbol cap and length validation.
- One request per refresh; no per-row calls.
- One in-flight request; AbortController on supersession.
- Loopback assertion per request.
- No redirect opener.
- Bounded read.
- Opaque logs and public errors.
- Rate limiting using existing edge-resolved client/peer identity.
- No response caching across users/visitors at an edge.
- No provider brand on public UI or payload.
- No raw upstream logging in normal operation.
- Controller catches all failures and leaves baseline usable.
- No retry loop faster than normal cadence.

## 10. Testing strategy

### Shared semantic tests

- Dossier fixtures remain green after extraction.
- `chg`-as-percent discriminator.
- closed-session settled close not stale.
- delayed basis cannot become current.
- missing/unknown clock fails downward.
- opposite-sign extended fields are ignored.
- degenerate `prevClose == price` with previous-session move stays coherent.
- future/NaN/boolean/unknown basis refusal.
- mutation tests delete each load-bearing guard and red the suite.

### Batch API tests

- one upstream call for 30 symbols;
- order/dedupe/80-symbol cap;
- complete/partial/zero-usable responses;
- exact coverage arithmetic;
- upstream redirect/timeout/oversize/malformed JSON;
- provider fields absent;
- rate limiting;
- no retry;
- session-aware mixed states;
- schema and opaque errors.

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
- malformed envelope no repaint;
- stale sequence/revision suppression;
- correction wins;
- unavailable and last-good aging;
- no score/order/stage mutation;
- ticker click route unaffected.

### Browser/production proof

- real route response from the served origin;
- one network call per refresh;
- visible tuple consistency;
- normal + delayed/partial/unavailable fixture/proxy states;
- dark/light × EN/ZH × 1440/390 screenshots;
- zero console errors and horizontal overflow;
- page source/order/score fingerprint unchanged;
- live setting and background-tab behavior;
- actual ticker opens Terminal.

## 11. Deployment and rollback

Deployment uses the existing Macro merge/render/API restart paths. The API module and controller must be included in current deploy/restart/integrity inventories rather than creating a new service.

Canary:

1. merge reviewed exact head;
2. deploy API and static assets through existing path;
3. verify `/api/health` running commit;
4. verify one known ticker tuple against canonical hub;
5. open Intelligence Hub with cache-busted assets;
6. run browser matrix and failure drills;
7. observe telemetry/error budget.

Rollback:

- server feature flag or route-disable setting makes controller remain baked;
- remove controller include to stop requests;
- baseline remains complete throughout;
- no data migration or durable live state to unwind.

## 12. R1B hold

Do not add SSE/WebSocket in R1A. R1B is commissioned only after Sol accepts R1A production proof and the measurement shows snapshot pull cannot meet the user/cost target. R1B must reuse this schema's semantics and add only ordered transport, heartbeat, gap resync and backpressure—not a new quote owner.
