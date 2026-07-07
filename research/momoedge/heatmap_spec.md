# MomoEdge Market/Flow Heatmap — Reverse-Engineering Spec

> Source files: `js/heatmap-widget.js` (911 lines, compiled React/JSX bundle) + `js/heatmap-init.js` (133 lines, auth bootstrap). Extracted 2026-07-06 for lawful competitive feature study. No code is copied; only interface/behavior contracts are documented.

---

## 1. Data Endpoints

All live data is pulled from a single Supabase project: `https://pojiqfeemksvocnaellu.supabase.co/rest/v1`.

Two parallel fetches on every poll cycle:

### 1a. Price / market view
```
GET /heatmap_view
?select=ticker,name,sector,sub_industry,price,change_pct,change_1w,change_1m,
        change_ytd,volume,prev_volume,opt_call_vol,opt_put_vol,opt_call_oi,
        opt_put_oi,opt_iv,opt_contracts,market_cap,updated_at
&order=market_cap.desc.nullslast
```
This is a **server-side Supabase view** — the underlying table schema and any joins are not in client code.

### 1b. Aggregated flow
```
GET /heatmap_flow_agg
?select=ticker,bullish_premium,bearish_premium,total_premium,sentiment,sweeps,
        whales,unusual,avg_dte,trade_count,top_trades,agg_date,updated_at
```
Also server-side. `top_trades` is a JSON column (array of trade objects). Flow data falls back to a prior-day snapshot if `agg_date` does not match today's ET date; the banner reads "Showing <date> flow · Live data resumes at market open."

### 1c. Live intraday flow (terminal injection)
If `window.FLOW_DATA` is populated (injected by the terminal/flow desk page), the widget skips endpoint 1b and computes aggregates client-side from the raw trade array. Field mapping from raw trade objects:

| Raw field | Used as |
|---|---|
| `ticker` | ticker |
| `premRaw` | premium (float) |
| `type` | "CALL" / "PUT" |
| `tradeDir` | "Sold" → bearish/bullish logic |
| `isSweep` | boolean |
| `isUnusual` | boolean |
| `dte` | days to expiration |
| `strikeNum` / `strike` | strike price |
| `expiry` / `expires_at` / `expiration_date` | expiration |
| `contracts` / `size` | contract volume |
| `oi` / `open_interest` | open interest |
| `executedAt` / `executed_at` / `time` | execution time |

### Auth
`heatmap-init.js` bootstraps Supabase auth (anon key hardcoded as fallback: `eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9…`). The init publishes `window._sbAuthClient` so the widget can call `getSession()` for JWT refresh before each fetch. Poll interval: **30,000 ms** (passed as `refreshInterval` prop; default in component is 60,000 ms but init overrides to 30,000 ms). Staleness threshold: data older than **300,000 ms (5 min)** triggers a stale-close banner.

---

## 2. Sector Grouping

Stocks are grouped by the `sector` field from `heatmap_view`. The 11 GICS sectors are mapped to short display labels via:

```js
var SN = {
  "Information Technology": "TECH",
  "Healthcare":             "HEALTH",
  "Financials":             "FINANCE",
  "Consumer Discretionary": "CONS DISC",
  "Energy":                 "ENERGY",
  "Communication Services": "COMM",
  "Industrials":            "INDUSTRIAL",
  "Consumer Staples":       "STAPLES",
  "Utilities":              "UTILITIES",
  "Real Estate":            "REAL EST",
  "Materials":              "MATERIALS"
};
```

Each stock also carries `sub_industry` (sub-industry label from the view). Sectors are sorted by aggregate tile value (market cap or flow premium) descending before treemap layout.

---

## 3. Layer Toggle: PRICE vs FLOW

Two layers selectable via `PRICE` / `FLOW` buttons (state: `layer ∈ {"price","flow"}`). Switching layers resets `selectedTicker`.

### PRICE layer
- Tile **color** encodes `change_pct` (1D) or `change_1w/1m/ytd` for other timeframes.
- Default tile **size** mode: `cap` (market cap).
- Default table sort: `ch` descending.
- Default sz modes available: `cap`, `equal`.

### FLOW layer
- Tile **color** encodes `flow.sent` (sentiment, range −1…+1).
- Default tile **size** mode: `premium` (switches automatically on layer change).
- Default table sort: `tp` (total premium) descending.
- Additional sz mode: `premium` (tile area ∝ `max(flow.tp, 10000)`).
- Filter controls enabled: `UNUSUAL` toggle, DTE bucket selector.
- Sz modes available: `premium`, `cap`, `equal`.

---

## 4. Tile Coloring — Exact Formulas

Colors are computed as linear/quadratic interpolations. Both functions accept a colorblind flag `cb`.

### 4a. Price tile color — `priceTileColor(change, cb)`
```js
const t  = Math.min(Math.abs(change) / 4, 1);   // saturates at ±4%
const t2 = t * t;
// Dead zone: |change| < 0.1 → rgb(24,28,36) / rgb(16,20,26)
// Standard green (up, cb=false):
  top = rgb(5+t*3,   25+t2*175, 15+t2*68)
  bot = rgb(3+t*2,   12+t2*80,  8+t2*30)
// Standard red (down, cb=false):
  top = rgb(40+t2*215, 8+t*15,  12+t2*56)
  bot = rgb(20+t2*95,  5+t*8,   8+t2*24)
// CB blue (up): top = rgb(15+t*15, 45+t2*140, 80+t2*175) / ...
// CB orange (down): top = rgb(70+t2*185, 40+t2*90, 8+t*8) / ...
```

### 4b. Flow tile color — `flowTileColor(sentiment, cb)`
```js
const t = Math.min(Math.abs(sentiment), 1);   // sentiment ∈ [−1, +1]
// Dead zone: t < 0.08 → rgb(30,35,42) / rgb(22,26,32)
// Standard bull (sent > 0, cb=false):
  top = rgb(5+t*5,  35+t*156, 30+t*135)
  bot = rgb(3+t*3,  18+t*65,  16+t*55)
// Standard bear (sent < 0, cb=false):
  top = rgb(40+t*215, 18+t*89, 18+t*89)
  bot = rgb(22+t*85,  10+t*35, 10+t*35)
```

Both functions return `{ top, bot }` (gradient stops). Applied via SVG `<linearGradient>` defs with 41 precomputed stops per layer.

---

## 5. Timeframes

Four buttons: **1D**, **1W**, **1M**, **YTD**.

Column mapping:
```js
{ "1D": "change_pct", "1W": "change_1w", "1M": "change_1m", "YTD": "change_ytd" }
```

If the selected period column is null for more than 50% of stocks, a **"⚠ 1D FALLBACK"** badge appears and `change_pct` is substituted. Period change resets `selectedTicker`.

---

## 6. Views: MAP and TABLE

### 6a. MAP view
SVG treemap using the **squarify** algorithm (`squarify(items, x, y, w, h)` — standard Bruls squarified treemap, implemented inline). Canvas dimensions are measured live via `ResizeObserver` with 120 ms debounce. Initial size: `min(900, window.innerWidth − 4)` × `420 px`.

- **Sector blocks**: clickable to zoom into a single sector (state: `zoom`). Header bar shows short sector name, breadth (`advances/total`), leader ticker, and avg change.
- **Tile minimum area**: `64 px²` — tiles below this threshold are not rendered.
- **Tile minimum value thresholds** (pre-layout filter):
  - FLOW layer: `flow.tp >= 25,000`
  - PRICE layer: `mc >= 5` (billion)
- **Zoom**: mouse wheel (factor 1.15 in / 0.87 out), pinch-to-zoom on touch, range `[1, 6]`. Pan by dragging when `svgZoom > 1`.
- **Volume spike indicator**: price layer tiles with `v/av > 1.2` display a small blue rectangle in the bottom-right corner.
- **Badges on flow tiles** (shown when tile ≥ 45×35 px): up to 3 emoji from `flow.badges`.
- **Tile label in flow mode**: formatted premium (e.g. "1.2M"); in price mode: change pct (e.g. "+2.3%").

### 6b. TABLE view
Sortable table. Column sets differ by layer:

**PRICE columns** (sort keys in parens):
`Ticker (t)`, `Name (n)`, `Industry (sub)`, `Cap (mc)`, `Price (p)`, `Chg% (ch)`, `RS (rs)`, `Vol (vr)`

**FLOW columns**:
`Ticker (t)`, `Name (n)`, `Premium (tp)`, `Sent. (sent)`, `B/B (pc)`, `Score (fs)`, `Industry (sub)`

Filters active in table view: sector pill buttons, search field, unusual-only toggle, DTE bucket filter. All same state as map.

---

## 7. Tile Sizing Modes

| Mode key | Available in | Tile area proportional to |
|---|---|---|
| `cap` | PRICE + FLOW | `stock.mc` (market cap in $B; missing cap → `5`) |
| `equal` | PRICE + FLOW | `1` (all tiles equal area) |
| `premium` | FLOW only | `max(flow.tp, 10_000)` (total options premium in $) |

Switching to FLOW layer auto-selects `premium`; switching to PRICE layer auto-selects `cap`.

---

## 8. Filters

### 8a. Unusual / All Flow toggle (FLOW layer only)
State: `unusualOnly`. When on, only tickers with `flow.badges.length > 0` pass through (i.e., at least one of: whales ≥ 2, unusual ≥ 3, sweeps ≥ 3).

### 8b. DTE buckets (FLOW layer, desktop only)
State: `dteFilter ∈ {"all","short","mid","long"}`.

| Label | Filter condition |
|---|---|
| `ALL` | no filter |
| `0-7d` | `flow.dte <= 7` |
| `7-30d` | `flow.dte > 7 && flow.dte <= 30` |
| `30d+` | `flow.dte > 30` |

In map view, dimming is applied client-side to tiles that don't match the active DTE bucket.

### 8c. Sector filter
Pill buttons generated from `pa.ss` / `fa.ss`. Clicking a sector sets `secFilt`; clicking again clears it. In map view, `zoom` (double-click sector block) is an alternative sector focus. These are independent states.

### 8d. Ticker search
Free-text filter on `ticker` and `name`, lowercased.

---

## 9. Top Strip (above map/table)

All fields computed from `calcPrice()` (PRICE layer) or `calcFlow()` (FLOW layer).

### PRICE layer strip fields
| Label | Value |
|---|---|
| Direction label | `"BULLISH"` if breadth ≥ 60% AND SPY > 0.2%; `"BEARISH"` if ≤ 40% AND SPY < −0.2%; else `"MIXED"` |
| Breadth bar | `bP %` advance/decline ratio |
| SPY | Market-cap-weighted average `ch` across all stocks (proxy for SPY) |
| Leaders | Top-2 tickers by `ch` |
| Laggards | Bottom-2 tickers by `ch` |
| Sector performance bar | Sectors ranked by avg `ch`; each shows avg, breadth, leader |

### FLOW layer strip fields
| Label | Value |
|---|---|
| Direction label | `"CALL-HEAVY"` if `totalCall > totalPut * 1.2 AND fBP >= 50`; `"PUT-HEAVY"` if `totalPut > totalCall * 1.2 AND fBP <= 50`; else `"MIXED"` |
| Flow breadth bar | `fBP %` (% of flow-active tickers with positive sentiment) |
| Premium | Total premium across all tickers (`fa.tP`) |
| Bull leaders | Top-2 by `flow.sent` |
| Bear laggards | Bottom-2 by `flow.sent` |

### Snapshot / "Since Open" comparison
- **SNAP button**: captures `openSnapshot` at first data load; can be reset manually.
- **SINCE OPEN button**: toggles `vsOpen`. When on, the strip shows "N flips" — count of tickers whose price direction (PRICE layer) or sentiment sign (FLOW layer) flipped vs the open snapshot.
- Snapshot delta is shown in tooltip per ticker when `vsOpen` is on.

---

## 10. Detail Panel — Full Field List

Appears below the map/table when a tile is clicked (state: `selectedTicker`). Dismissed by clicking again or pressing Escape.

### Always shown (both layers)
| Label | Source | Notes |
|---|---|---|
| `Price` | `selected.p` | `$X.XX` |
| `Change` | `selected.ch` | `±X.XX%`, colored pos/neg |
| `Mkt Cap` | `selected.mc` | via `fC()`: T/B format |
| `Volume` | `selected.v` | `X.XM (X.Xx avg)`; blue if `v/av > 1.2` |
| `RS` | `selected.ch − spy` | relative strength vs market-cap-weighted universe |
| `Rank` | `pa.ranks[t]` | `#N/M` within sector, sorted by `ch` |

### Flow fields (shown when `flow.tp > 0`)
| Label | Source field | Formula / notes |
|---|---|---|
| `Flow Premium` | `flow.tp` | `round(sum of premRaw)` |
| `Bullish` | `flow.cP` | `round(sum of call-side prem × weight)` |
| `Bearish` | `flow.pP` | `round(sum of put-side prem × weight)` |
| `Sentiment` | `flow.sent` | `clamp((cP−pP)/max(tp,1), −1, 1)`, 3dp |
| `Bear/Bull` | `flow.pcR` | `min(99, pP/max(cP,1))`, 2dp |
| `Flow Intensity` | `flow.fs` | `min(10, 1 + tp/500_000 + sw*0.5 + wh*1.5 + un*0.8)`, 1dp |
| `Sweeps` | `flow.sw` | count of `isSweep` trades |
| `Whales` | `flow.wh` | count of trades with `prem >= 1_000_000` |
| `Unusual` | `flow.un` | count of `isUnusual` trades |
| `Avg DTE` | `flow.dte` | `round(dteSum / count)` |
| `Badges` | `flow.badges` | shown if non-empty; badge rules below |
| `Divergence` | computed | `selected.ch > 0.05 === selected.flow.sent > 0.05` → "✓ Aligned" or "⚠ Divergent" |

#### Badge thresholds
```js
if (wh >= 2)  badges.push("🐋");   // whale badge
if (un >= 3)  badges.push("🔥");   // unusual badge
if (sw >= 3)  badges.push("⚡");   // sweep badge
```

#### Bullish premium weighting for sold contracts
```js
var _cw = trade.tradeDir === "Sold" ? 0.5 : 1;
if (isBullish) fa.cP += prem * _cw;
else           fa.pP += prem * _cw;
```
Sold options get 50% weight; bought options get 100% weight.

### Options data — shown when `flow.tp === 0 AND opt.contracts > 0` (Polygon fallback)
Source: `heatmap_view` columns `opt_call_vol`, `opt_put_vol`, `opt_call_oi`, `opt_put_oi`, `opt_iv`, `opt_contracts`.

| Label | Value |
|---|---|
| `Call Volume` | `opt_call_vol` (formatted as `XK`) |
| `Put Volume` | `opt_put_vol` |
| `P/C Vol Ratio` | `opt_put_vol / opt_call_vol` |
| `Call OI` | `opt_call_oi` |
| `Put OI` | `opt_put_oi` |
| `OI P/C` | `opt_put_oi / opt_call_oi` |
| `IV` | `opt_iv * 100` → `X.X%` |
| `Contracts` | `opt_contracts` |

### Options data — when both `flow.tp > 0` AND `opt.contracts > 0` (combined view)
Both flow metrics (above) **and** these options fields are shown together:
`Opt Call Vol`, `Opt Put Vol`, `Vol P/C`, `Call OI`, `Put OI`, `IV`.
(No `Contracts` in combined view.)

### Flow Trades table (up to 50 rows, sorted by premium desc)
Shown below the metrics when `flowTradesRef.current[ticker]` is non-empty.

Columns:
| Column | Source field |
|---|---|
| `Side` | `"BUY"` or `"SELL"` (from `tradeDir === "Sold"`) |
| `Type` | `"CALL"` / `"PUT"` |
| `Strike` | `$X` |
| `Exp` | `expiry` / `expires_at` / `expiration_date` |
| `Premium` | `premRaw` |
| `DTE` | `dte`; highlighted amber if `<= 7` |
| `Flags` | ⚡ sweep, 🔥 unusual, 🐋 whale (prem ≥ $1M) |
| `Contracts` | `contracts` / `size` (desktop only) |
| `OI` | `oi` / `open_interest` (desktop only) |
| `Time` | `executedAt` / `executed_at` / `time` (desktop only) |

---

## 11. Hover Tooltip Fields

Shown as a floating overlay (160 px min-width) when hovering over a tile in MAP view. Position is clamped to stay within the canvas; vertical clearance is 170 px (price) or 230 px (flow) from bottom.

**PRICE layer tooltip:**
`Ticker`, `Name`, `Sector · Sub-industry`, `Price ($X.XX)`, `Cap (XB)`, `Vol (X.Xx avg)`, `RS (±X.XX)`, `Rank (#N/M)`, `Flow (▲/▼ $XM)`

When `vsOpen` is on and snapshot exists: delta change and flip indicator.

**FLOW layer tooltip:**
`Ticker`, `Name`, `Sector · Sub-industry`, `Premium`, `Bull ($XM)`, `Bear ($XM)`, `B/B (X.XX)`, `Score (X.X)`, `Sweeps`, `Whales` (blue if `wh >= 2`), `DTE (Xd)`, `Rank (#N/M)`, `Price (±X.X% ✓/DIV)`

DIV appears when `(ch >= 0) !== (flow.sent >= 0)` — price direction opposes flow sentiment.

When `vsOpen` is on: sentiment delta and flip indicator per ticker. When badges exist: `Signals` row with badge emojis.

---

## 12. Divergence Detection

Two divergence signals are computed client-side:

### 12a. Tooltip inline "DIV" flag
```js
hov.ch >= 0 === hov.flow.sent >= 0 ? "✓" : "DIV"
```
No threshold — any sign mismatch between `ch` and `flow.sent` triggers "DIV".

### 12b. Detail panel "Divergence" field
```js
selected.ch > 0.05 === selected.flow.sent > 0.05 ? "✓ Aligned" : "⚠ Divergent"
```
Uses a **0.05 threshold** on both sides (not just sign). A stock is only "Aligned" if both price change AND sentiment are both > 0.05 or both ≤ 0.05.

### 12c. Since-Open flip tracking (`vsOpen` mode)
```js
// Price layer flip:
s.ch >= 0 !== snap.ch >= 0
// Flow layer flip:
s.flow.sent >= 0 !== snap.flow.sent >= 0
```
Counted in strip as "N flips" since session open.

### 12d. Tile flip indicator in map
Tiles that flipped direction since the open snapshot get a visual highlight (border or overlay — exact CSS in render loop).

---

## 13. Sector Performance Bar

Displayed between top strip and map. Each sector shown as a compact pill with:
- Abbreviation (from `SN` map)
- Average `ch` (price layer) or average `flow.sent` (flow layer)
- Color coded green/red

Sector pills also function as filter buttons; clicking sets `secFilt`.

---

## 14. Computed Fields and Formulas Summary

| Field | Identifier | Formula |
|---|---|---|
| Sentiment | `flow.sent` | `clamp((cP−pP)/max(tp,1), −1, 1)` |
| Bear/Bull ratio | `flow.pcR` | `min(99, pP/max(cP,1))` |
| Flow Intensity Score | `flow.fs` | `min(10, 1 + tp/500_000 + sw*0.5 + wh*1.5 + un*0.8)` |
| Avg DTE | `flow.dte` | `round(dteSum / count)` |
| RS | (display only) | `stock.ch − spy` where `spy = Σ(ch × mc) / Σ(mc)` |
| Price direction | `pa.dir` | BULLISH: bP≥60 & spy>0.2; BEARISH: bP≤40 & spy<−0.2; MIXED |
| Flow direction | `fa.netDir` | CALL-HEAVY: `tC > tPut*1.2 & fBP≥50`; PUT-HEAVY: `tPut > tC*1.2 & fBP≤50`; MIXED |
| Volume ratio | `v/av` | `volume / prev_volume` (threshold 1.2x for highlight) |
| Market cap fallback | `mc` | Raw `market_cap / 1e9`; if missing/zero → `5` (to keep tile visible) |

---

## 15. Access Gate (heatmap-init.js)

Server-side concern. The client calls `window.MomoEdge.accessGate.fetchGateInputs(sb, uid)` and `gate.decideAccess({session, profile, hasClaimedCode, courseCompleted, waitlistEnabled, ctx:{surface:'heatmap'}})`. The entitlement logic (Stripe subscription check, comp tier bypass, waitlist flag) is entirely in `access-gate.js` (not in these two files). On verdict `!== 'grant'`, `gate.applyVerdict(verdict)` redirects (to `/checkout`, `/waitlist-confirmation`, etc.). The `waitlistEnabled` flag is hardcoded `false` in the bundle as of extraction date (MOM-443 "open mode").

---

## 16. Default Watchlist

```js
var DEFAULT_WATCHLIST = new Set(["NVDA","TSLA","AAPL","AMD","META","AMZN","GOOG","NFLX","MSFT","BA"]);
```
Used when no `watchlist` prop is passed. Not used for filtering in the heatmap itself — appears to be a prop-API contract for embedding.

---

## 17. What Is NOT in Client Code

- Supabase view schema for `heatmap_view` (joins, aggregation, data source)
- Supabase view schema for `heatmap_flow_agg` (how institutional flow is classified, aggregated, and scored server-side)
- `top_trades` construction logic (JSON built server-side or by another pipeline)
- Access gate entitlement rules (Stripe/comp tier logic in `access-gate.js`)
- Options data sourcing from Polygon (just field names visible in client)
- Historical OHLC data pipeline that populates `change_1w`, `change_1m`, `change_ytd`
- Any ML or rule-based sweep/unusual/whale classification (only thresholds for display are visible: `prem >= 1_000_000` for whale display; `isSweep`/`isUnusual` are boolean flags set upstream)
