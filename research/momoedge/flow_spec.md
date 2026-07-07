# MomoEdge Flow (Options Tape) — Reverse-Engineered Spec

> Source files analysed: `flow-core.js`, `flow.js`, `flow-filters.js`, `flow-watchlist.js`, `flow-inspector.js`, `flow-ask-oracle.js`, `flow-view-v2.js`
> All identifiers, thresholds and formulas are quoted verbatim from the client code.

---

## 1. Flow Card / Event Object

Every scored row in `window.FLOW_DATA` carries these fields (produced by `scoreRawFlowData` or `serverRowToDisplay` in `flow-core.js`):

| Field | Source field(s) | Meaning |
|---|---|---|
| `id` | `row.id` (or synthesised) | Unique trade ID |
| `ticker` | `row.ticker_symbol \|\| row.ticker` | Underlying symbol (uppercased) |
| `type` | `row.put_call \|\| row.type` | `'CALL'` or `'PUT'` |
| `strike` | `row.strike_price \|\| row.strike \|\| row.option_strike` | Strike formatted as string (`$250`) |
| `strikeNum` | same, parsed as float | Raw numeric strike |
| `expiry` | `row.expires_at \|\| row.expiry \|\| row.expiration_date` | Expiry date string |
| `prem` | `fmtPremium(row.total_premium \|\| row.premium)` | Formatted premium string |
| `premRaw` | `parseFloat(...)` | Premium in raw dollars |
| `contracts` | `row.total_size \|\| row.size \|\| row.volume` | Contract count (lot size) |
| `oi` | `row.open_interest \|\| row.oi \|\| row.option_open_interest` | Open interest |
| `vol` | `row.daily_volume \|\| row.option_volume \|\| row.volume_today \|\| row.volume` | Daily option volume |
| `oiRatio` | `(contracts / oi * 100).toFixed(0) + '%'` | % of OI traded |
| `sizeOi` | `sizeOiRaw.toFixed(2)` | Size ÷ OI (string) |
| `sizeOiRaw` | `size / oi` (if oi > 0, else -1) | Size ÷ OI (numeric) |
| `sizeVol` | `(size / vol).toFixed(2)` | Size ÷ volume (string) |
| `distPct` | `abs((strike - spot) / spot) * 100` | % distance from spot (string) |
| `isITM` | call: `strike < spot`; put: `strike > spot` | In-the-money boolean |
| `itmDepth` | `distPct` when ITM | Depth in-the-money (string) |
| `spotPrice` | `row.underlying_price \|\| row.stock_price` | Underlying price at alert |
| `sent` | Computed from type + tradeDir | `'BULLISH'` or `'BEARISH'` |
| `alertRule` | `row.alert_rule \|\| row.rule` | Alert rule name (e.g. `'sweep'`) |
| `hasSweep` | `row.has_sweep === true` | Sweep flag |
| `hasFloor` | `row.has_floor === true` | Floor/block flag |
| `hasMultileg` | `row.has_multileg === true` | Multileg flag |
| `sideRaw` | `row.trade_side \|\| row.side \|\| row.execution` | Raw execution side string |
| `execLabel` | Derived (see §4) | Display label: `'At Ask'`, `'Near Ask'`, `'Above Mid'`, `'Mid'`, `'Near Bid'`, `'At Bid'` |
| `tradeDir` | Derived (see §4) | `'Bought'` or `'Sold'` |
| `score` | Legacy client score (mostly 0 post–Wave 1) | Deprecated |
| `score_v2` | `row.score_v2` | Server-pinned score V2 |
| `score_v2_macd` | `row.score_v2_macd` (fallback: score_v2) | Score V2 with MACD |
| `score_v3` | `row.score_v3` | Score V3 |
| `score_v5` | `row.score_v5` | Score V5 (bearish trades) |
| `score_v6` | `row.score_v6` | Score V6 (current display score) |
| `dte` | `row.dte_at_exec` (server) or computed from expiry | Days to expiry at execution |
| `grade` | `flowScoreGrade(0)` stub | Legacy; not displayed |
| `grade_v2` | `flowScoreGrade(displayScore, sent, whaleQualified)` | Badge object (see §3) |
| `whaleQualified` | `row.whale_gate === true` | Server whale gate flag |
| `deathWatchQualified` | `row.death_watch_gate === true` | Death-watch gate |
| `classification` | `row.classification` | Server-assigned classification |
| `flowClass` | `row.flow_class` | Flow class |
| `relPrem` | `row.rel_prem` | Relative premium vs. ticker average |
| `optPrice` | `row.price \|\| row.avg_price \|\| ...` or `premium / (size * 100)` | Per-contract option price |
| `contractsVerified` | `'UNVERIFIED'` if `premium / (size * price * 100)` outside [0.1, 10] | Sanity check |
| `distLabel` | `computeDistLabel(distPct, isITM)` | OTM label (see §5) |
| `oiLabel` | `computeOiLabel(sizeOiRaw)` | OI conviction label (see §5) |
| `implied_volatility` | `row.implied_volatility \|\| row.iv` | IV (may be fraction 0–1 or percent 0–100) |
| `executed_at` | `row.executed_at \|\| row.created_at \|\| row.timestamp` | Execution timestamp |
| `optSymbol` | `row.option_symbol` | OCC option symbol for mark polling |
| `oiPrev` | `row.oi_prev` | Prior-session OI |
| `volAvg7d` | `row.vol_avg_7d` | 7-day average volume |
| `cluster_type` | `row.cluster_type` | Cluster type (server-assigned) |
| `cluster_size` | `row.cluster_size` | Number of legs in cluster |
| `cluster_total_size` | `row.cluster_total_size` | Total contracts in cluster |
| `cluster_total_prem` | `row.cluster_total_prem` | Total premium in cluster |
| `spread_type` | `row.spread_type` | Spread type label |
| `spread_note` | `row.spread_note` | Spread description |
| `cluster_note` | `row.cluster_note` | Cluster description |
| `source` | `'uw'` | Data source identifier |

Server-enriched display-fast-path fields (`d_*` from `flow-cache-read`):

| DB column | Meaning |
|---|---|
| `d_sent` | Pre-computed `sent` (`BULLISH`/`BEARISH`) |
| `d_exec` | Pre-computed `execLabel` |
| `d_dir` | Pre-computed `tradeDir` |
| `d_side` | Pre-computed `sideRaw` |
| `d_opt_price` | Pre-computed option price |
| `d_dist_label` | Pre-computed distance label |
| `d_oi_label` | Pre-computed OI label |
| `d_prem_ok` | Pre-computed premium verification |
| `d_ds` | Pre-computed display score |
| `dist_pct` | OTM distance % |
| `is_itm` | ITM boolean |
| `itm_depth` | Depth ITM |
| `size_oi` | Pre-computed size/OI |
| `size_vol` | Pre-computed size/vol |

---

## 2. Scoring System

### 2.1 Score Version Hierarchy

The **display score** follows this cascade (from `flow-core.js _displayScore` and `flow-ask-oracle.js displayScore`):

```
score_v6  (current primary for BULLISH)
score_v5  (BEARISH trades; checked if sent=BEARISH)
score_v3  (fallback V3)
score_v2  (fallback V2)
score     (legacy fallback)
```

In `flow-core.js _displayScore` the cascade is:
```js
if (typeof r.score_v3 === 'number') return r.score_v3;
if (typeof r.score_v2 === 'number') return r.score_v2;
return r.score || 0;
```
But `flow-ask-oracle.js` has the full V6-first chain:
```js
if (typeof r.score_v6 === 'number') return r.score_v6;
if (r.sent === 'BEARISH' && typeof r.score_v5 === 'number') return r.score_v5;
if (typeof r.score_v3 === 'number') return r.score_v3;
if (typeof r.score_v2 === 'number') return r.score_v2;
return num(r.score);
```

**Conclusion:** `score_v6` is the intended current display score. All scoring computation is **server-side**; the client receives pinned values from `flow_cache`. The client's `computeFlowScore` produces only `score: 0` as a structural shell (the actual field is empty/zero).

### 2.2 Server Score Columns (all server-side — client only reads)

| Column | Known use |
|---|---|
| `score_v1` | Legacy baseline |
| `score_v2` | V2 (whale gate basis: `score_v2 >= 90` + whale profile) |
| `score_v2_macd` | V2 with MACD overlay |
| `score_v3` | V3 (current modular-base; production display) |
| `score_v3_macd` | V3 with MACD |
| `score_v3_1` | V3.1 variant |
| `score_v4` | V4 |
| `score_v5` | V5 (bearish) |
| `score_v6` | V6 (current top-line) |
| `whale_gate` | Boolean: `score_v2 >= 90` + whale profile |
| `death_watch_gate` | Boolean: bearish "death watch" qualification |
| `market_tape_used` | Market tape context used in scoring |
| `bull_premium_share_14d` | 14-day bull premium share |
| `signal_count_7d` | 7-day signal count |

### 2.3 Grade / Tier Thresholds

From `config.js`:
```js
SCORE_GRADE_THRESHOLDS: { WHALE: 90, INSTITUTIONAL: 80, HIGH_CONVICTION: 70, MODERATE: 60, LOW: 50 }
```

`flowScoreGrade(score, direction, isWhaleQualified)` → badge object:

| Condition | Label | Color |
|---|---|---|
| `isWhaleQualified === true && isBull` | `'WHALE POSITION'` | `#ff4444` |
| `score >= 90` + isBull | `'INSTITUTIONAL BULL'` | `#ff9500` |
| `score >= 90` + isBear | `'INSTITUTIONAL BEAR'` | `#ff9500` |
| `score >= 90` (no dir) | `'INSTITUTIONAL'` | `#ff9500` |
| `score >= 80` + isBull | `'INSTITUTIONAL BULL'` | `#ff9500` |
| `score >= 80` + isBear | `'INSTITUTIONAL BEAR'` | `#ff9500` |
| `score >= 80` (no dir) | `'INSTITUTIONAL'` | `#ff9500` |
| `score >= 70` + isBull | `'HIGH CONVICTION BULL'` | `#ffd700` |
| `score >= 70` + isBear | `'HIGH CONVICTION BEAR'` | `#ffd700` |
| `score >= 70` (no dir) | `'HIGH CONVICTION'` | `#ffd700` |
| `score >= 60` + isBull | `'MODERATE BULL'` | `#4fc3f7` |
| `score >= 60` + isBear | `'MODERATE BEAR'` | `#4fc3f7` |
| `score >= 60` (no dir) | `'MODERATE'` | `#4fc3f7` |
| `score >= 50` + isBull | `'LOW SIGNAL BULL'` | `#4a6a8a` |
| `score >= 50` + isBear | `'LOW SIGNAL BEAR'` | `#4a6a8a` |
| `score >= 50` (no dir) | `'LOW SIGNAL'` | `#4a6a8a` |
| `score < 50` | `'NOISE'` | `#333` |

Note: `INSTITUTIONAL` appears at both `>= 90` and `>= 80` bands (same label/color), meaning the practical label tiers visible to users are WHALE → INSTITUTIONAL → HIGH CONVICTION → MODERATE → LOW SIGNAL → NOISE.

### 2.4 Tier Labels in flow-view-v2.js

`tierInfo(score)` provides CSS class + short label:

| Score | Class | Label |
|---|---|---|
| >= 90 | `fc2-elite` | `'ELITE'` |
| >= 80 | `fc2-strong` | `'STRONG'` |
| >= 70 | `fc2-solid` | `'HIGH'` |
| < 70 | `fc2-moderate` | `'MODERATE'` |

### 2.5 Score Floor / Display Gates

| Context | Threshold |
|---|---|
| Default filter floor (`flowScoreMin`, `FLOW_SCORE_FLOOR`) | **60** |
| Bearish PUT offset (floor lowered by 5 at default 60 floor): | **55** (`BEARISH_PUT_FLOOR_OFFSET = 5`) |
| flow-view-v2 `SCORE_GATE` (gating `_ownData`) | **50** |
| flow-view-v2 ticker-filter lower gate (`TICKER_GATE`) | **50** |
| flow-inspector `SCORE_GATE` | **65** |
| Score expectations band boundaries | `85+`, `75-84`, `65-74`, `<65` |
| Gate alert fires at score | **>= 90** (score_90 alert) |

### 2.6 Score Expectations (DB-backed)

Table `score_expectations` keyed on `direction + ':' + score_band`. Score bands: `'85+'`, `'75-84'`, `'65-74'`, `'<65'`. Minimum sample size to surface: `n_with_outcomes >= 10`. Cached in localStorage key `momoedge_score_exp_v1` with 30-day TTL.

---

## 3. Badges

### 3.1 Whale Badge
- **Gate:** `whale_gate === true` (server-pinned boolean)
- **Basis:** `score_v2 >= 90` plus the "V2 whale profile" (server-side; profile definition not in client code)
- **Client flag:** `whaleQualified`
- **Display:** Only shown on BULLISH direction (`isWhaleQualified === true && isBull`)
- **Alert:** `fireAlert('urgent', '🐋', ticker + ' WHALE qualified', ...)` fires when newly seen

### 3.2 Sweep Badge
- **Gate:** `has_sweep === true` (server field on `flow_cache`)
- **Alert rule check:** `uwAlertBadge` also checks `alertRule.toLowerCase().includes('sweep')`
- **CSS/label:** `{ label: 'SWEEP', color: '#A78BFA', bg: 'rgba(167,139,250,.12)', bdr: 'rgba(167,139,250,.35)' }`

### 3.3 Floor / Block Badge (Golden Sweep)
- **Gate:** `has_floor === true`
- **uwAlertBadge logic:** `rule.includes('golden') || flowRow.hasFloor` → `'GOLDEN SWEEP'`; otherwise `rule.includes('sweep') || flowRow.hasSweep` → `'SWEEP'`; `rule.includes('block')` → `'BLOCK'`
- **Golden sweep:** `{ label: 'GOLDEN SWEEP', color: '#ffd700', bg: 'rgba(255,215,0,.1)', bdr: 'rgba(255,215,0,.3)' }`
- **Block:** `{ label: 'BLOCK', color: '#ffb300', bg: 'rgba(255,179,0,.1)', bdr: 'rgba(255,179,0,.3)' }`

### 3.4 Cluster Badge
- **Gate:** `cluster_type` non-null (server-assigned label)
- **Fields:** `cluster_type`, `cluster_size`, `cluster_total_size`, `cluster_total_prem`, `cluster_note`
- **In filter:** badge key `'cluster'` matched via `record.clusterType` (non-null)
- **Detection:** entirely server-side; client just passes through

### 3.5 Multileg Badge
- **Gate:** `has_multileg === true`
- **Fields:** `spread_type`, `spread_note`
- **Detection:** server-side

### 3.6 Death Watch Badge
- **Gate:** `death_watch_gate === true`
- **Flag:** `deathWatchQualified`
- **Client switch:** `DEATH_WATCH_BADGE_ENABLED = false` (disabled in client at time of analysis)
- **Alert:** fires if prefs have `death_watch` enabled

---

## 4. Direction Classifier

### 4.1 Primary: Server `trade_dir`
The server's `trade_dir` column (`BULLISH` / `BEARISH`) is the **authoritative source of truth**:

```js
var _srvDir = (r.trade_dir || '').toUpperCase();
if (_srvDir === 'BULLISH' || _srvDir === 'BEARISH') {
  var _isCallDir = (r.put_call || r.type || '').toUpperCase() === 'CALL';
  tradeDir = ((_srvDir === 'BULLISH') === _isCallDir) ? 'Bought' : 'Sold';
}
```

Mapping: `BULLISH CALL → Bought`, `BULLISH PUT → Sold`, `BEARISH CALL → Sold`, `BEARISH PUT → Bought`.

`sent` (BULLISH/BEARISH) comes directly from `trade_dir` when present, or falls back to execution-side heuristic.

### 4.2 Fallback: Execution-Side Heuristic

When `trade_dir` is absent, the client computes from `sideRaw`:

| `sideRaw` keyword | `execLabel` | `tradeDir` |
|---|---|---|
| `near_ask`, `n_a` | `'Near Ask'` | `'Bought'` |
| `above_ask`, `a_a`, `ask` | `'At Ask'` | `'Bought'` |
| `above_mid`, `a_m`, `above mid` | `'Above Mid'` | `'Bought'` |
| `near_bid`, `n_b` | `'Near Bid'` | `'Sold'` |
| `mid` | `'Mid'` | `'Bought'` |
| `bid`, `below` | `'At Bid'` | `'Sold'` |
| `buy`, `bought` | `'Bought'` | `'Bought'` |
| `sell`, `sold` | `'Sold'` | `'Sold'` |

When no `sideRaw`, bid/ask/price are used:
```
pct = (price - bid) / (ask - bid)
>= 0.85  → At Ask / Bought
>= 0.65  → Near Ask / Bought
>= 0.50  → Above Mid / Bought
>= 0.40  → Mid / Bought
>= 0.20  → Near Bid / Sold
else     → At Bid / Sold
```
Or when only `total_ask_side_prem` / `total_bid_side_prem` are available:
```
asp > bsp * 2  → At Ask / Bought
bsp > asp * 2  → At Bid / Sold
asp > bsp      → Above Mid / Bought
else           → Near Bid / Sold
```

### 4.3 Sentiment Computation
```js
sent = (isCall && !isSold) || (!isCall && isSold) ? 'BULLISH' : 'BEARISH';
```

---

## 5. Moneyness and OI Labels

### computeDistLabel(distPct, isITM)
```js
if (isITM) return 'IN THE MONEY';
if (abs <= 1) return 'AT THE MONEY';
if (abs <= 3) return 'NEAR THE MONEY';
if (abs <= 8) return 'MODERATE OTM';
if (abs <= 15) return 'FAR OTM';
return 'DEEP OTM — LOTTO';
```

### computeOiLabel(sizeOi)
```js
if (sizeOi >= 0.60) return 'DOMINANT — NEW POSITION LIKELY';
if (sizeOi >= 0.30) return 'SIGNIFICANT POSITIONING';
if (sizeOi >= 0.15) return 'NOTABLE SIZE';
if (sizeOi >= 0.05) return 'MODERATE';
return 'LOW CONVICTION';
```

### Moneyness bands (filter module ATM_BAND_PCT)
```js
var ATM_BAND_PCT = 1.0; // |distPct| <= 1% counts as ATM
```
Filter options: `['ITM', 'ATM', 'OTM']`

---

## 6. Filters (Full Taxonomy)

### 6.1 flow-filters.js — Full Filter State Schema

`createDefault()` returns:
```js
{
  type: 'all',           // 'all' | 'CALL' | 'PUT'
  scoreMin: 60,          // DEFAULT = 60
  scoreMax: 100,
  dte: { min: null, max: null },
  sentiment: 'all',      // 'all' | 'BULLISH' | 'BEARISH'
  symbol: '',            // ticker substring search
  moneyness: [],         // array of 'ITM' | 'ATM' | 'OTM'
  strike: { min: null, max: null },
  expiry: { min: null, max: null },  // date strings
  premMin: null, premMax: null,      // raw premium in dollars
  optPriceMin: null, optPriceMax: null,  // per-contract option price
  exec: [],              // subset of EXEC_LABELS
  grade: [],             // subset of GRADE_TIERS
  side: 'all',           // 'all' | 'Bought' | 'Sold'
  badges: [],            // subset of BADGES
  sizeOiMin: null,
  sizeVolMin: null,
  volMin: null,
  oiMin: null,
  ivMin: null, ivMax: null,    // IV in percent (normalised from fraction if < 5)
  relPremMin: null,
  universe: 'all',       // 'all' | 'etf' | 'stock'
  moveMin: null, moveMax: null,  // % move since alert (requires live mark)
  sort: [{ key: 'score', dir: 'desc' }]
}
```

### 6.2 Filter Constants

```js
var EXEC_LABELS = ['At Ask', 'Above Mid', 'Mid', 'Below Mid', 'At Bid'];
var GRADE_TIERS = ['ELITE', 'STRONG', 'MODERATE', 'SOFT', 'UNGRADED'];
var BADGES = ['whale', 'sweep', 'floor', 'multileg', 'cluster'];
var MONEYNESS = ['ITM', 'ATM', 'OTM'];
var SORT_KEYS = ['time', 'score', 'premium', 'size', 'sizeOi', 'move', 'dte', 'iv'];
```

Note: `GRADE_TIERS` here (`ELITE`/`STRONG`/`MODERATE`/`SOFT`/`UNGRADED`) differs from the grade labels produced by `flowScoreGrade`. These appear to be legacy tier names from a prior version or mapped differently in the filter UI.

### 6.3 Filter Match Logic

Each condition is ANDed:
- `type`: exact match on `record.type`
- `scoreMin`/`scoreMax`: `scoreOf(record)` (uses `score_v2` or `score`)  
  + bearish PUT offset: if `record.sent === 'BEARISH' && record.type === 'PUT' && effMin <= 60`, then `effMin -= 5`
- `sentiment`: `record.sent === s.sentiment`
- `symbol`: case-insensitive substring of `record.ticker`
- `dte`: `inRange(record.dte, s.dte.min, s.dte.max)`
- `moneyness`: derived via `moneynessOf` (ITM/ATM/OTM)
- `strike`: `inRange(record.strikeNum, ...)`
- `expiry`: string comparison of `record.expiry.slice(0,10)`
- `premMin`/`premMax`: `inRange(record.premRaw, ...)`
- `optPriceMin`/`optPriceMax`: `inRange(record.optPrice, ...)`
- `exec`: `record.execLabel` must be in array
- `grade`: `(record.grade_v2 && record.grade_v2.label) || 'UNGRADED'` must be in array
- `side`: `record.tradeDir === s.side`
- `badges`:
  - `'whale'` → `record.whaleQualified`
  - `'sweep'` → `record.hasSweep`
  - `'floor'` → `record.hasFloor`
  - `'multileg'` → `record.hasMultileg`
  - `'cluster'` → `record.clusterType` (non-null/falsy check)
- `sizeOiMin`: `record.sizeOiRaw >= s.sizeOiMin`
- `sizeVolMin`: `record.sizeVol >= s.sizeVolMin`
- `volMin`: `record.vol >= s.volMin`
- `oiMin`: `record.oi >= s.oiMin`
- `ivMin`/`ivMax`: IV normalised (if `iv < 5` then `iv *= 100`)
- `relPremMin`: `record.relPrem >= s.relPremMin`
- `universe`: checks `isETF(record.ticker)` against ETF_TICKERS set
- `moveMin`/`moveMax`: `(mark - optPrice) / optPrice * 100` (only applied when live mark is available; rows without marks pass through)

### 6.4 flow-view-v2 Internal Filter State

The v2 view uses a simplified 6-field state (separate from the advanced `flowFilterState`):
```js
_filterState = {
  type: 'all',       // 'all' | 'CALL' | 'PUT'
  direction: 'all',  // 'all' | 'bull' | 'bear'
  scoreMin: 50,      // SCORE_GATE
  premMin: null,     // dollars
  sweepOnly: false,
  whaleOnly: false,
  symbol: ''
}
```

Score chip presets exposed in v2 UI: `50+`, `60+`, `70+`, `80+`, `90+`.

### 6.5 Saved Views Mechanism

Two parallel saved-views stores:

**v1 (advanced filter):**
- localStorage key: `momoFlowViews`
- Format: array of `{ name, query (URL-serialized filter state), builtin }`
- No built-in presets (`BUILTIN_VIEWS = []` — presets retired)
- Serialization via `serializeToURL` / `parseFromURL` (URL query params)

**v2 (simplified filter):**
- localStorage key: `fv2FlowViews`
- Format: array of `{ name, type, direction, scoreMin, premMin, sweepOnly, whaleOnly, symbol, sortMode, sortDir }`

Active filters persist to `momoFlowFilters` (localStorage) and also to URL params via `replaceState`.

### 6.6 Sort Keys
Default: `score desc`. Available sort keys: `time`, `score`, `premium`, `size`, `sizeOi`, `move`, `dte`, `iv`.

---

## 7. Watchlist Rail

**Endpoint:** `/.netlify/functions/flow-watchlist` (GET to list, POST `{ticker}` to add, DELETE `?ticker=` to remove)
**localStorage mirror:** key `momoedge_flow_watchlist` (array of ticker strings)
**Max tickers:** 50
**Ticker validation regex:** `/^[A-Z][A-Z0-9.]{0,9}$/`

**Per-row stats** (via `getTickerPCStats(ticker)`):
- `callPrem`, `putPrem`, `callCount`, `putCount`, `totalCount`
- `pcRatio`: `putPrem / callPrem` (null if callPrem = 0)
- `sentiment`: `callPrem > putPrem ? 'BULLISH' : putPrem > callPrem ? 'BEARISH' : 'NEUTRAL'`

**Displayed net delta:** `callPrem - putPrem` with sign (`+` / `-`) in green/red.

**Price feeds:** via `ws.PRICE_CACHE` (websocket module). Batch-prefetches via `ws.batchFetchPrices(tickers)`. Live updates via `priceUpdate` events. Off-hours: shows "Closed" if `|pct| < 0.005`.

**Flow count badge:** `todayFlowCount(ticker)` — counts FLOW_DATA rows for today by ticker.

---

## 8. Smart Money Radar

`buildSmartMoneyRadar(rows)` — ranking algorithm for the radar widget:

**Per-ticker accumulations:**
- `prem`: total premium
- `count`: trade count
- `scoreSum` / `avgScore`: score-based averages
- `unusual`: count where `displayScore >= 80`
- `sweeps`: count where `hasSweep || hasFloor`
- `soiSum`/`soiCount`/`sweetSpotSoi`: size/OI metrics; "sweet spot" is `sizeOi >= 3 && sizeOi <= 10`

**Normalised dimensions:**
- `normScorePrem`: `scoreWeightedPrem / maxScoreWeighted` (where `scoreWeightedPrem = prem * (avgScore / 100)`)
- `normCount`: `count / maxCount`
- `normRelActivity`: `min(relActivity, 20) / min(maxRelActivity, 20)` (capped at 20×)  
  `relActivity = todayPrem / historicalDailyAvg[6 prior days]`
- `normSoi`: composite `soiQuality / maxSoiQuality`  
  `soiQuality = sweetPct * 0.6 + (avgSoi ∈ [3,10] ? 0.4 : avgSoi >= 1 ? 0.2 : 0)`

**Rank formula:**
```
rank = (normRelActivity * 0.30)
     + (normSoi * 0.25)
     + (normScorePrem * 0.25)
     + (normCount * 0.10)
     + min(unusualBonus, 0.10)   // unusualBonus = 0.1 * unusual_count
```

Tickers in `config.RADAR_EXCLUSIONS` are excluded. Result sorted by `rank desc`, top N displayed. Cached by hash; invalidated when FLOW_DATA changes.

---

## 9. Flow Gauge (Summary Stats)

`renderFlowSummary(rows)` and `getTickerPCStats(ticker)` power the gauge:

**Displayed fields:**
- `fsBull` (element id): total call premium (formatted)
- `fsBear` (element id): total put premium (formatted)
- `fsLargest` (element id): P/C ratio = `putPrem / callPrem` (to 2 decimal places, `'—'` if callPrem = 0)

**Per-ticker gauge** (`computeSentiment`):
- Same call/put premium split per ticker
- Net = `callPrem - putPrem`
- Sentiment: `callPrem > putPrem → BULLISH`, `putPrem > callPrem → BEARISH`, equal → `NEUTRAL`
- Gauge can be cycled through time ranges: `['1D', '3D', '7D']` and direction filters: `['all', 'BULLISH', 'BEARISH']`

**fv2 rail "Total Option Premium"** (id `fv2PremBody`):
- Call premium, put premium, P/C ratio — same formula

---

## 10. Ask Oracle for Flow

**Endpoint:** `/.netlify/functions/ask-oracle` (POST, JWT via `window.netlifyFetch`)

**Request payload:**
```json
{
  "mode": "read" | "deep",
  "question": null | "string",
  "trade": {
    "ticker": "AAPL",
    "type": "CALL" | "PUT",
    "direction": "BULLISH" | "BEARISH" | null,
    "score": 87,
    "premium": 1250000,
    "size_oi": 2.3,
    "strike": 200,
    "spot": 195.5,
    "dte": 14,
    "exec": "At Ask",
    "classification": "...",
    "whale": false
  }
}
```

**Modes:**
- `'read'`: auto-triggered 280ms after row selection (debounced). Returns compact verdict only (no `detail` paragraph).
- `'deep'`: triggered by chip button clicks with specific question text.

**Question chips (generated dynamically per row):**
1. `"Why is this [bullish/bearish]? What in the flow supports or weakens that read?"`
2. `"What is the historical edge for this score tier and direction? Cite hit rates, avg peak, and sample size."`
3. `"Show outcomes for similar setups — same direction and score tier."`
4. `"How does [TICKER] flow recently compare — recent scored signals and their outcomes?"`

**Response shape:**
```json
{
  "answer": {
    "verdict": "string",
    "what_it_is": "string",
    "detail": "string",
    "edge": {
      "n": 42,
      "low_confidence": false,
      "avg_peak_pct": 12.5,
      "hit_50_pct": 65,
      "hit_100_pct": 38,
      "avg_drawdown_pct": 4.2,
      "avg_hold_days": 8
    },
    "confidence": "high" | "medium" | "low",
    "caveat": "string"
  }
}
```
OR legacy: `{ "text": "plain prose" }`

Score expectations lookup (from `score_expectations` DB table): `direction + ':' + score_band` where bands are `'85+'`, `'75-84'`, `'65-74'`, `'<65'`. Only surfaced if `n_with_outcomes >= 10`.

---

## 11. API / Netlify Endpoints

| Endpoint | Method | Params | Purpose |
|---|---|---|---|
| `/.netlify/functions/flow-cache-read` | GET | `mode=day`, `date=YYYY-MM-DD`, `page=N` | Main data fetch; returns `{ rows, has_more }`. Pages 0-2 fired speculatively in parallel; max 10 pages. Rows include all `d_*` enrichment fields and all `score_v*` columns. |
| `/.netlify/functions/flow-cache-read` | GET | `mode=live` | 30-second live refresh (from app.js, not shown in these files) |
| `/.netlify/functions/flow-history-read` | GET | `ticker=SYM`, `page=N`, `limit=N` | Per-ticker 7-day history; returns `{ rows, has_more }`. Head fetch: `limit=80`. Max 5 pages (flow-view-v2) or 4+1 (flow.js). |
| `/.netlify/functions/flow-feed-query` | GET | `source=wide`, `sort=time`, `limit=200`, `min_score=50`, `ticker=SYM`, `before_ts=ISO`, `cursor_ts`, `cursor_id` | Deep history (>7 days, up to 30 days). Cursor-paginated. |
| `/.netlify/functions/flow-watchlist` | GET | — | Load user watchlist |
| `/.netlify/functions/flow-watchlist` | POST | `{ ticker }` | Add ticker |
| `/.netlify/functions/flow-watchlist` | DELETE | `?ticker=SYM` | Remove ticker |
| `/.netlify/functions/ask-oracle` | POST | see §10 | AI oracle for flow analysis |
| Supabase `flow_cache` table | SELECT | direct via `MomoEdge.db.select(...)` | Fallback last-trading-day lookup |
| Supabase `score_expectations` table | SELECT | `select=*` | Score tier outcome stats |

**Auth:** `window.netlifyFetch` wraps standard `fetch` with a Supabase JWT bearer token (`Authorization: Bearer <access_token>`). Token extracted via `_sbAuthClient.auth.getSession()`.

---

## 12. Data Flow Architecture

```
Supabase (flow_cache table)
    ↓
Netlify function: flow-cache-read (enriches with d_*, score_v*, cluster_*, etc.)
    ↓
flow.js: _loadFlowFromUWInner()
    → serverRowsToDisplay() [fast path: d_* fields present]
    → OR _rowToParsed() + scoreRawFlowData() [legacy path]
    → FLOW_DATA[] (global, window-scoped)
    ↓
flow-view-v2.js: reads FLOW_DATA, applies filters, renders 3-pane grid
flow-filters.js: pure filter/sort model, no DOM
flow-inspector.js: derives detail/breakdown/premium charts from selected row
flow-ask-oracle.js: sends compact trade context to oracle proxy
flow-watchlist.js: sidebar + chip rail, persists to Netlify function
```

**localStorage keys:**
- `momoFlowFilters`: serialized active filter state
- `momoFlowViews`: v1 saved views
- `fv2FlowViews`: v2 saved views
- `momoedge_flow_watchlist`: watchlist mirror
- `momoedge_score_exp_v1`: score expectations cache (30-day TTL)
- `momoedge_fhist_YYYY-MM-DD`: historical flow day cache (7-day, for prior trading days only)
- `flow_v2`: kill-switch (`'0'` = revert to v1 render)
- `flow_v1_retired`: kill-switch (`'0'` = restore v1)
- `flow_v2_reconcile`: kill-switch (`'0'` = force full rebuild)
- `flow_rail_collapsed`: left rail collapse state
- `fv2FiltersCollapsed`: filter grid collapse state (desktop)

---

## 13. Dynamic Premium Threshold (Relative Premium)

`computeDynamicPremiumThreshold(ticker, flowData)`:
- If fewer than 5 trades for ticker: use static fallback (`INDEX_TICKERS_PREM` → $1M; `LARGECAP_TICKERS` → $500K; else $150K)
- Else: `max($150K, avgTradeSize * 3)` where `avgTradeSize = totalPrem / tradeCount`

Index tickers (higher static threshold): `SPY QQQ IWM DIA TLT VIX SPX SPXW NDX`
Large-cap tickers: `AAPL MSFT NVDA META GOOGL AMZN TSLA NFLX`

---

## 14. Premium Verification

```js
function computePremVerified(rawPrice, sizeVal, totalPremium) {
  var expected = sizeVal * rawPrice * 100;
  if (expected > 0 && (totalPremium / expected < 0.1 || totalPremium / expected > 10)) return 'UNVERIFIED';
  return null;
}
```
`'UNVERIFIED'` if `totalPremium / (size * price * 100)` is outside [0.1, 10].

---

## 15. ETF Universe

The `ETF_TICKERS` Set contains ~100 tickers (full list in `flow-core.js` lines 21-36) covering: major index ETFs (SPY/QQQ/IWM/DIA/VOO), sector ETFs (XL*), commodity ETFs, bond ETFs (TLT/HYG/JNK), ARK funds, leverage/inverse ETFs, crypto ETFs (IBIT/BITO/GBTC), international ETFs, and various thematic ETFs.

---

## 16. Inspector Panel Derivations

`deriveInspector(row, allRows)` returns:

- **Detail grid** (`deriveDetailGrid`): `strike`, `expiry`, `dte`, `otmPct`/`otmLabel`, `type`, `time`, `executedAt`, `premium`, `underlying`, `iv` (normalised to percent if < 5)
- **Flow breakdown** (`deriveFlowBreakdown`):
  - `totalPremium`, `contracts`, `avgPremium` (= totalPremium / contracts)
  - `direction` (BULLISH/BEARISH), `sweep` (= `hasSweep || hasFloor`), `sweepPct` (100% or 0%)
  - `orderType`: `'Sweep'` | `'Block'` | `'Cluster'` | `'Single'`
  - `tradeDir`, `execLabel`
- **Premium flow 1D** (`derivePremiumFlow1D`): bucketed into 30-minute intervals (market hours 09:30–16:00 ET = 13 buckets). Returns `[{ time, label, premium, count }]`.
- **Cumulative premium flow**: running sum over buckets.
- **Market context** (`deriveMarketContext`): SPY + QQQ from `ws.PRICE_CACHE` — `price`, `change`, `changePct`, `isUp`.

---

*All scoring computation (score_v1 through score_v6, whale_gate, death_watch_gate, cluster detection, spread detection) is server-side. The client receives pinned values and displays them. The client's `computeFlowScore` produces only structural metadata (DTE, distPct, sizeOi, sizeVol) with `score: 0`.*
