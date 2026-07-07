# Chain Heat — Competitive Feature Spec

**Source files analyzed:**
- `/tmp/momoedge_src/js/modules/chain-heat.js` (primary, 247 lines, unminified)
- `/tmp/momoedge_src/chain-cache.js` (caching layer, 77 lines, unminified)
- Supporting context: `terminal.html`, `sw.js` (cross-references only)

**Purpose of this document:** Internal competitive reference for building an equivalent feature on our own data. No code is copied; identifiers and thresholds are quoted for fidelity.

---

## 1. Feature Concept

Chain Heat surfaces **contract-day accumulation campaigns** — cases where institutional flow splits a large position across many small alerts that individually fall below scoring thresholds. The module header gives a concrete worked example:

> "e.g. SMH 6/18 530P, $11.97M over 29 alerts in 91 min at 91% ask, every fragment scoring <50. Per-alert gating can never see the campaign; this rail shows the contract-day aggregate as ONE card."

The product rationale is explicit: per-alert flow feeds are blind to accumulation; Chain Heat provides the aggregate view.

---

## 2. Data Backend

### 2.1 Database Table

The module header states: **DB lane: `chain_heat` table** refreshed by `pg_cron` every 2 min during market hours.

- Table name (exact): `chain_heat`
- Refresh mechanism: `pg_cron` scheduled job (server-side, not in client code)
- Refresh cadence: every 2 minutes, market hours only

The aggregation logic, grouping query, and `pg_cron` job definition are **entirely server-side** — not present in the client JS.

### 2.2 API Endpoint

```
/.netlify/functions/chain-heat-read
```

- Stored in `var EP = '/.netlify/functions/chain-heat-read';`
- Authentication: JWT via `window.netlifyFetch` (the auth-injecting fetch wrapper defined in `terminal-init.js`; falls back to plain `fetch` if `netlifyFetch` is absent)
- Method: GET (no body params observed; server returns `{ campaigns: [...] }`)
- Response shape: `d.campaigns` — an array of campaign objects

The server-side function (`chain-heat-read`) performs the premium threshold gate, ordering/ranking, and any additional filters. None of those are exposed in client code beyond the `$3M` label in the UI (see §3).

---

## 3. Premium Threshold

The UI label rendered in `railHTML()` is:

```js
'contract-day accumulation ≥ <b>$3M</b>'
```

This is a **display-only** confirmation of the threshold; the actual `>= 3_000_000` filter is applied server-side in `chain-heat-read`. No client-side numeric filtering occurs — if the server returns a campaign, it is rendered regardless of value.

---

## 4. Polling Interval

```js
var POLL_MS = 120000;   // matches the 2-min DB refresh cadence
```

- Client polls every **120 seconds (2 minutes)**, explicitly matched to the `pg_cron` DB refresh cadence.
- Polling is **skipped while the tab is backgrounded**: `if (document.hidden) return;`
- On tab return from background, an **immediate poll fires**: `document.addEventListener('visibilitychange', function () { if (!document.hidden) poll(); });`
- Skeleton (3 placeholder cards) is shown on first load only (`_loaded` flag); subsequent polls preserve the last good data on transient errors.

---

## 5. Aggregation Grouping Keys

The grouping keys are **server-side** (inside `chain_heat` table population logic, not exposed to the client). However, the client's change-detection hash reveals the unique identifier per campaign:

```js
var key = JSON.stringify([_collapsed, campaigns.map(function (c) {
  return [c.option_symbol, c.alert_count, c.total_premium, c.side];
})]);
```

The natural key used for dedup/change detection is: **`option_symbol` + `alert_count` + `total_premium` + `side`**.

From the card renderer (`cardHTML`), the fields present on each campaign object are:

| Client field | Meaning | Notes |
|---|---|---|
| `c.option_symbol` | OCC symbol for the contract | Used as dedup key |
| `c.ticker` | Underlying ticker symbol | Displayed in ch-tk span |
| `c.type` | Option type (CALL / PUT) | Drives `dirCol` coloring |
| `c.strike` | Strike price (numeric) | Rendered as `$<Number(c.strike)>` |
| `c.expiry` | Expiry date `YYYY-MM-DD` | Formatted as `MM/DD` |
| `c.side` | Aggressor side: `'BOUGHT'`, `'SOLD'`, or `'MIXED'` | Controls background wash + badge + premium color |
| `c.trade_dir` | Directional read: `'BEARISH'` or else bullish | Controls contract type color (`ch-sell` vs `ch-buy`) |
| `c.total_premium` | Aggregate premium (numeric, dollars) | Formatted: `>=1e6` → `$XM`, `>=1e3` → `$XK` |
| `c.alert_count` | Number of component alerts in the campaign | Shown as `N hits` |
| `c.span_minutes` | Duration of the campaign in minutes | Formatted: `<1m`, `Nm`, `XhYm` |
| `c.first_seen` | ISO timestamp of the first alert | Formatted to ET time via `toLocaleTimeString` |
| `c.ask_share` | Fraction filled at ask (0–1) | Rendered as `Math.round(ask_share * 100) + '% at ask'` |
| `c.dte` | Days to expiry | Rendered as `N DTE`; omitted if null |

### Side Classification Logic (client rendering)

```js
var side = (c.side === 'BOUGHT' || c.side === 'SOLD' || c.side === 'MIXED') ? c.side : 'BOUGHT';
var mixed = side === 'MIXED';
var col = mixed ? 'var(--ch-accent)' : side === 'BOUGHT' ? 'var(--ch-buy)' : 'var(--ch-sell)';
var sideLabel = mixed ? 'CONTESTED' : side;
```

- `BOUGHT` → green (`--ch-buy: #00ffa3`) + `BOUGHT` badge
- `SOLD` → red (`--ch-sell: #ff3b3b`) + `SOLD` badge
- `MIXED` → amber (`--ch-accent: #ffb300`) + `CONTESTED` badge (label rewrite client-side)
- Any other value defaults to `BOUGHT`

---

## 6. Dedup Logic

Dedup is **change-detection only** on the client — no per-campaign dedup filter exists in client JS. The render function skips a full re-render if the serialized key is unchanged:

```js
if (key === _lastKey) return;
_lastKey = key;
```

Where `key = JSON.stringify([_collapsed, campaigns.map(c => [c.option_symbol, c.alert_count, c.total_premium, c.side])])`.

The actual dedup of alerts into campaigns (i.e., collapsing N flow alerts for the same `option_symbol` on the same trade date into one campaign row) is **server-side** in the `chain_heat` table population job.

---

## 7. Ranking / Surfacing

Campaign ordering is **server-side only**. The client renders campaigns in whatever order the API returns them — there is no client-side sort. The server presumably orders by `total_premium DESC` or by recency, but this is not confirmable from the client source.

The rail displays campaigns as a horizontal scroll; all campaigns meeting the $3M threshold are surfaced (no client-side cap is visible in the code, though `SKELETON_COUNT = 3` suggests the UI was designed with roughly 3 campaigns in mind as a common case).

---

## 8. UI Rail Architecture

### Injection Points

Two parallel rail instances are maintained:

| Kind | Host element ID | Inserted before |
|---|---|---|
| `desktop` | `chainHeatDesktop` | `#flowFeed` |
| `mobile` | `chainHeatMobile` | `#mFlowCards` |

Both share the same `_collapsed` state (keyed by `kind`) and re-render from the same `_lastData` cache on collapse toggle.

### Rail Card Fields (display order)

1. **Row 1:** `ticker` | `type + strike` (colored by `trade_dir`) | `expiry` | side badge
2. **Row 2 (premium row):** `total_premium` (large, colored by side) | `alert_count` hits · `span_minutes`
3. **Meta row:** `ask_share`% at ask | `first_seen` ET | `dte` DTE (if present)

### Collapse / Expand

- Toggle button (`ch-header`) is the only interactive element; cards are **static info tiles** (no per-card click action).
- `aria-expanded` and `hidden` attributes are managed; focus-visible ring on toggle button.

---

## 9. Caching Layer (chain-cache.js)

`chain-cache.js` is **not used by chain-heat.js** — it is a separate module serving `gex.js` / `gex-init.js` for option-chain data (`/.netlify/functions/uw-chain?endpoint=option-contracts`).

### What chain-cache.js Does

The file is self-described as a **"passthrough stub"** that replaced a broken localStorage-backed cache (the original stored 4–8 MB of option chain data in localStorage, silently causing `QuotaExceededError` that broke Supabase session persistence).

Current behavior:
- On init: purges any leftover `chainCache:*` keys from localStorage
- `ChainCache.fetch(ticker, fetchFn, opts)`: constructs the URL, deduplicates in-flight requests via `_inFlight` map, calls `fetchFn(url)`, returns `{ payload, fromCache: false, stale: false, truncated: bool }`
- `ChainCache.clear()` / `ChainCache.invalidate()`: no-ops
- `ChainCache.inspect()`: returns `{ entries: 0, totalBytes: 0, index: [] }` (stub)
- `ChainCache.VERSION = 1`

### URL Construction (chain-cache.js)

```
/.netlify/functions/uw-chain
  ?ticker=<encoded>
  &endpoint=option-contracts
  [&windowed=true]
  [&strike_pct=<N>]
  [&max_dte=<N>]
```

Cache key: `ticker` (non-windowed) or `ticker + ':w' + strikePct + maxDte` (windowed).

In-flight dedup: a second call with the same cache key returns the existing Promise; the `_inFlight` entry is deleted on resolution or rejection.

Chain Heat's own polling uses `window.netlifyFetch(EP, {})` directly — it does **not** go through `ChainCache`.

---

## 10. Deployment / Feature Flag Status

As of the analyzed snapshot, Chain Heat is **commented out** in `terminal.html`:

```html
<!-- <script defer src="js/modules/chain-heat.js"></script> -->
```

The module is built and deployed to the asset path but not loaded in production. The service worker (`sw.js` line 92) explicitly lists `chain-heat` in the network-first bypass group alongside `net-timeout`, `flow-watchlist`, and `flow-detail` — indicating it was anticipated in the SW cache strategy even before going live.

---

## 11. What Is Purely Server-Side (Not in Client Code)

| Concern | Status |
|---|---|
| SQL aggregation query / GROUP BY keys | Server-side only |
| `>= $3M` numeric filter | Server-side only (client only labels it) |
| Campaign ranking / sort order | Server-side only |
| `pg_cron` job definition | Server-side only |
| `side` classification logic (BOUGHT/SOLD/MIXED) | Server-side only (client just renders what it receives) |
| `trade_dir` (BEARISH/bullish) classification | Server-side only |
| `dte` calculation | Server-side only |
| `span_minutes` calculation | Server-side only |

---

## 12. Key Numbers Summary

| Parameter | Exact value |
|---|---|
| Premium threshold | `>= $3M` (labeled in UI; filtered server-side) |
| Poll interval | `120000 ms` (2 min) |
| DB refresh cadence | `pg_cron` every 2 min, market hours |
| Skeleton card count | `3` |
| Side values | `'BOUGHT'`, `'SOLD'`, `'MIXED'` (→ displayed as `'CONTESTED'`) |
| API endpoint | `/.netlify/functions/chain-heat-read` |
| Chain-cache endpoint | `/.netlify/functions/uw-chain?endpoint=option-contracts` |
| Auth | JWT Bearer via `window.netlifyFetch` |
