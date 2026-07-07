# MomoEdge PRISM / Heat Seeker — Reverse-Engineering Spec

**Source file:** `js/heatseeker-init.js` (4,426 lines, unminified)
**Supporting file:** `gex-engine.js` (1,994 lines, unminified)
**Build tag:** `PRISM r8.0` (Phase 0.4, from `const PRISM_BUILD = 'PRISM r8.0'`)
**Auth backend:** Netlify Functions + Supabase (`pojiqfeemksvocnaellu.supabase.co`)

---

## 1. Black-Scholes Foundations

### Risk-free rate
```js
const BS_RISK_FREE_RATE = 0.05;  // hardcoded 5%; added in AUDIT-4 (2026-05-10), previously r=0
```
Note in comment: "keep `gex-snapshotter.js` in sync if this value changes."

### Gamma computation (`bsGamma`)
```
T = max(dte/365, 0.001)
sqrtT = sqrt(T)
d1 = [ln(S/K) + (r + 0.5*iv^2)*T] / (iv*sqrtT)
gamma = normPdf(d1) / (S * iv * sqrtT)
```
where `normPdf(x) = exp(-0.5*x^2) / sqrt(2*pi)`.

If `iv <= 0`, falls back to `fallbackIV || 0.30` (population median IV). If `dte <= 0`, uses `dte = 0.5`.

### Vanna magnitude (`bsVannaMag`)
```
d1 = same as above
d2 = d1 - iv*sqrtT
vannaRaw = -normPdf(d1) * d2 / iv
vannaMag = |vannaRaw|
```

### Dividend yields (gex-engine.js only — NOT used in heatseeker-init.js)
`gex-engine.js` has a separate `_bsGammaWithYield` with a dividend-adjusted d1 `(r - q + 0.5*iv^2)` and a `yieldFactor = exp(-q*T)`. Hardcoded per-ticker `DIVIDEND_YIELDS` table (SPY=0.013, QQQ=0.006, IWM=0.011, etc.). This is **not** applied in `heatseeker-init.js`; its `bsGamma` uses `r` only.

---

## 2. Matrix Construction (`MatrixEngine`)

### Config defaults
```js
DEFAULT_CONFIG: {
  contractMultiplier: 100,   // standard equity option multiplier
  volPctScale: 0.01,         // converts "per 1% move" — the 1% expressed as 0.01
  minDTE: 0.1,               // floor DTE for any contract
  dteWeightCap: 3.0,         // cap on VEX DTE weight
  maxExpirations: 4,         // nearest N expirations shown (user-adjustable via toolbar)
  referenceTime: null,       // if set (number), overrides Date.now() for build
}
```

### Expiration filtering
Only expirations with `expirationMs > now - 86400000` (i.e., not expired more than 24 hours ago) are kept. Then the `maxExpirations` nearest by calendar date are retained.

### Cell key
`"${strike}|${expiration}"` — one cell per (strike, expiration) pair.

### DTE weight (used only for VEX)
```
dte = max(0.01, max(minDTE, (expirationMs - buildNow) / 86400000))
dteWeight = min(1/sqrt(dte), dteWeightCap)   // cap = 3.0
```

### IV fallback
Population median of all per-contract IVs in range `(0.01, 5.0)`. If a contract's `iv <= 0`, the median is substituted. Default median if no valid IVs: `0.30`.

### Per-contract GEX dollar value
```
gamma = raw contract gamma (abs) if non-zero, else bsGamma(spot, strike, iv, dte, medianIV)
gexDollar = oi * gamma * spot * spot * contractMultiplier * volPctScale
```
Units: **dollar gamma exposure per 1% spot move** (the `spot^2 * 0.01` factor converts raw gamma to dollar P&L for a 1% move, times OI*100).

### Per-contract VEX dollar value
```
vannaMag = raw |vanna| if non-zero, else bsVannaMag(spot, strike, iv, dte, medianIV)
vexDollar = oi * vannaMag * spot * dteWeight * contractMultiplier * volPctScale
```
Units: **dollar vanna load**, DTE-weighted (shorter expirations get higher weight via `1/sqrt(dte)`).

### Cell accumulation
Calls and puts are tracked in separate half-cells per `(strike, expiration)`:
- `callGex += gexDollar` for calls; `putGex += gexDollar` for puts
- `callVex += vexDollar`; `putVex += vexDollar`
- `callOI`, `putOI`, `callVol`, `putVol` accumulated directly
- IVs are averaged: `callIV = sum(iv) / count`

### OI change tracking (for OI Movers)
Fields from server: `oi_prev` / `openInterestPrev` / `open_interest_prev`.

OI-change gating constants:
```js
NEAR_EXPIRY_MS = 12 * 60 * 60 * 1000   // 12 hours; near-expiry excluded from movers
MIN_BASE_OI    = 100                    // prev OI must be >= 100 to compute pct change
MIN_ABS_CHANGE = 200                    // |curr - prev| must be >= 200
MIN_NEW_STRIKE_OI = 500                 // new strike needs >= 500 OI to be flagged
```

OI change percent = `(curr - prev) / prev`, emitted as `callOIChangePct` / `putOIChangePct`.

A strike is `callIsNew` / `putIsNew` when `oiPrev === 0 && oi >= 500 && !isNearExpiry`.

`totalOIChangePct` uses the dominant side by absolute magnitude.

---

## 3. Lens Definitions

### 3.1 GEX
- **Net signed**: `callGex - putGex` per cell
- **Display value**: `|net|` with sign in prefix (`+$` / `−$`)
- **Side**: `'positive'` when net >= 0, `'negative'` otherwise
- **showsCallsPutsSeparately**: `false` (single net cell)
- **Description**: `"Dollar gamma exposure · per 1% spot move"`

### 3.2 VEX
- **Value**: `callVex + putVex` (total magnitude, not net)
- **Side**: always `'magnitude'` (no sign — vanna load is magnitude-focused)
- **showsCallsPutsSeparately**: `false`
- **Description**: `"DTE-weighted vanna load · normalized across expirations"`

### 3.3 OI
- **Value per side**: `callOI` or `putOI` in contracts
- **showsCallsPutsSeparately**: `true` (separate call/put columns per expiration)
- **Description**: `"Open interest contracts · positioning by strike"`

### 3.4 VOL
- **Value per side**: `callVol` or `putVol` in contracts traded today
- **showsCallsPutsSeparately**: `true`
- **Description**: `"Today's volume · contracts traded"`

### 3.5 UNUSUAL
- **Value**: `todayVol / median30d` (ratio = multiple)
- **Threshold**: `UNUSUAL_THRESHOLD = 3.0` — cells with multiple >= 3.0 get `side = 'unusual'`
- **Min samples**: `MIN_SAMPLES = 10` — if `volumeSampleCount < 10` or `median <= 0`, cell returns `side = 'insufficient'`, displayText `'NO HIST'`
- **showsCallsPutsSeparately**: `true`
- **Description**: `"Today's volume vs trailing trading-day median · unusual activity"`

The 30-day median and sample count are server-side fields: `volume_median_30d` / `volume_sample_count`. The server only computes these when `include_volume_baseline=true` is passed in the fetch (triggered only when UNUSUAL lens is active).

---

## 4. Intensity Tiers (Color Ramp)

Distribution-aware — NOT linear against the max. Breakpoints are quantiles of non-zero magnitude values across the matrix:

```js
function computeTierBreaks(mags) {
  // arr = sorted non-zero magnitudes
  q(p) = arr[floor(p * arr.length)]
  returns [q(0.20), q(0.40), q(0.60), q(0.80)]
}
```

Tier assignment:
- `tier 0`: zero / empty
- `tier 1`: > 0 but below q(0.20)
- `tier 2`: >= q(0.20)
- `tier 3`: >= q(0.40)
- `tier 4`: >= q(0.60)
- `tier 5`: >= q(0.80)

CSS class mapping:
- GEX: `pos s1..s5` (call-dominant green ramp) / `neg s1..s5` (put-dominant red ramp)
- VEX/OI/VOL: `flow t1..t5` (cyan ramp)
- UNUSUAL unusual cells: `unusual-cell t1..t5` (magenta ramp)

PRISM redesign layer uses a different (sparse-fill) approach: two percentile thresholds:
```js
PRISM_TIERS = { P_FAINT: 0.75, P_STRONG: 0.92 }
```
Cells below P_FAINT: transparent background. Between P_FAINT and P_STRONG: faint tint. At/above P_STRONG: strong tint. Leaders (top 3 per column above faint floor): vivid highlight + bold text. Gold star marks the gated pick; cyan/amber ⚡ marks the largest visible cell.

---

## 5. Heat Seeker Pick Gates (`StandoutPicker`)

### Default gates (all lenses)
```js
DEFAULT_GATES: {
  minTotalOI: 5000,       // total chain OI must exceed this
  minStandoutRatio: 1.2,  // top vs 2nd-best ratio floor
  minConfidence: 0.15,    // confidence floor (derived from ratio)
  excludeSpotRow: true,   // the nearest-to-spot row is excluded from candidates
}
```

### Per-lens gate overrides
```js
LENS_GATES: {
  GEX:     { minStandoutRatio: 1.5, applyDtePenalty: true },
  VEX:     { minStandoutRatio: 1.5, applyDtePenalty: true },
  OI:      { minStandoutRatio: 1.5 },
  VOL:     { minStandoutRatio: 1.5, applyProximityPenalty: true },
  UNUSUAL: { minStandoutRatio: 1.2 },
}
```

All candidates with value > 0 are collected. For `showsCallsPutsSeparately` lenses, both call and put sides are evaluated as separate candidates.

### DTE penalty (GEX, VEX)
Applied when `dte > 0 && dte < FLOOR_DTE` where `FLOOR_DTE = 0.5` days:
```
scoredValue = value * sqrt(dte / 0.5)
```
Penalizes cells within 12h of expiry without zeroing them.

### Proximity penalty (VOL)
```
distPct = |strike - spot| / spot
proximityFactor = distPct >= 0.02 ? 1.0 : (0.6 + distPct/0.02 * 0.4)
scoredValue = value * proximityFactor
```
Cells within 2% of spot get a factor between 0.6 and 1.0 (ATM is penalized 40%).

### Standout ratio and confidence
```
ratio = topScoredValue / secondScoredValue   (or 999 if second = 0)
confidence = min(1, (ratio - 1) / 3)
```
Pick is rejected if `ratio < minStandoutRatio` OR `confidence < 0.15`.

### Pick return fields
```
{
  strike,          // exact strike value
  expiration,      // date string YYYY-MM-DD
  side,            // 'call' | 'put' | 'net'
  value,           // unsigned magnitude
  signedValue,     // signed (GEX positive = call-dominant)
  displayText,     // formatted string e.g. "+$34M"
  confidence,      // float 0..1 (rounded to 2dp)
  standoutRatio,   // float (rounded to 2dp)
}
```

A secondary `rawPick` (largest cell by raw value, no gates) is also computed and displayed with a ⚡ marker if different from the gated pick.

### Diagnostic mode
`?pickdiag=1` in the URL activates `_PICKDIAG = true`, which emits `console.table` rows showing per-lens gate attribution (lens, totalOI, passedOI, cells, spotRowDrop, candidates, topValue, topScored, topStrike, topExp, secValue, secScored, ratio, passedRatio, confidence, outcome).

---

## 6. OI Movers Rail (`OIMovers.extract`)

`limit = 8` (top 8 movers returned).

Two categories:
1. **New strikes** (`isNew: true`): `oiPrev === 0 && oi >= MIN_NEW_STRIKE_OI (500) && !isNearExpiry` — sorted descending by current OI, shown first.
2. **Movers** (`isNew: false`): `|absChange| >= MIN_ABS_CHANGE (200) && prev >= MIN_BASE_OI (100)` — sorted descending by `|pct|`, tie-broken by `|absChange|`.

Deduplication: a `Set` keyed by `"${strike}|${side}"` — if the same strike appears in multiple expirations, only the first one (highest-priority) is kept.

Fields per mover:
```
{ strike, expiration, side ('call'|'put'), pct (null if new), oi, oiPrev, absChange, isNew, direction ('new'|'up'|'down') }
```

The OI movers panel header shows the baseline age via `_baselineAgeDays(_oiPrevSnapshotDate)` if > 1 day old.

---

## 7. GEX Level Computation (`computeLevelsLocal`)

Client-side, matches `gex-engine.js LevelDetector`. Operates on per-strike aggregates from `_aggregateStrikes()`.

### Call wall
Strike above spot with maximum `callOI * callGamma`. Falls back to all strikes if no strikes above spot.

### Put support
Strike below spot with maximum `putOI * putGamma`. Falls back to all strikes if no strikes below spot.

### HVL (High Volatility Level / gamma magnet)
```
score(s) = totalOI * avgGamma * proximity
proximity = 1 / (1 + |strike - spot| / (avgStep * 3))
```
`avgStep` = median of successive strike differences.

### Gamma flip
Cumulative net GEX (sorted low → high) zero-crossing, linearly interpolated:
```
ratio = |cumulative_before| / (|cumulative_before| + |next|)
crossing = strikes[i] + ratio * (strikes[i+1] - strikes[i])
```
If multiple crossings exist, the one closest to spot is used.

### Regime
`totalNet >= 0 → 'long'`, else `'short'`. Displayed as "LONG GAMMA · range-bound · absorbs vol" or "SHORT GAMMA · trending · amplifies vol".

These levels are rendered as "band" rows in the matrix table, mapped to the nearest rendered strike:
- `callWall` → class `level-cw`, label `CALL WALL`
- `maxPain` → class `level-mp`, label `MAX PAIN`
- `hvl` → class `level-hvl`, label `HVL`
- `putSupport` → class `level-ps`, label `PUT SUPPORT`

---

## 8. Max Pain (`computeMaxPain`)

```
payout(K) = Σ_{s<K}(K - s) * callOI_s * 100 + Σ_{s>K}(s - K) * putOI_s * 100
```
Best strike = argmin over all candidate strikes. Uses raw chain OI (not per-expiration filtered). Returns `null` on empty input.

---

## 9. Cell Hover Tooltip (Raw Inputs)

Each cell carries a `title="..."` attribute with 4 lines:
```
$STRIKE · MM/DD
Call OI XXXX · Put OI XXXX
Call Vol XXXX · Put Vol XXXX
Net GEX +$XXM
```
Format uses compact notation (1.2M / 34K / 850). This is the "explainable levels" differentiator — raw inputs visible on hover.

PRISM redesign uses `data-tip` attributes (JSON-encoded) with a floating `div.pr-tip` tooltip showing: title (colored), key-value rows, and an interpretive note line from `TOOLTIP_READS`:

```js
TOOLTIP_READS = {
  GEX: {
    positive: 'Call-dominant. Dealer hedging dampens moves; price tends to pin and mean-revert.',
    negative: 'Put-dominant. Dealer hedging amplifies moves; price gets choppy and can overshoot.',
  },
  VEX: {
    positive: 'Call-side vanna load. A vol drop here pulls hedging flows toward this strike over sessions.',
    negative: 'Put-side vanna load. Rising vol here pushes hedging flows away — expect expansion.',
  },
  OI: {
    positive: 'Call-heavy open interest. More call contracts are parked at this strike than puts.',
    negative: 'Put-heavy open interest. More put contracts are parked at this strike than calls.',
  },
  VOL: {
    positive: 'Call-side volume dominates today. Fresh buying interest concentrated at this strike.',
    negative: 'Put-side volume dominates today. Fresh protective or directional flow here.',
  },
  UNUSUAL: {
    positive: 'Bullish activity well above its normal baseline. Someone is positioning aggressively here.',
    negative: 'Bearish unusual activity. Concentrated protective or directional flow.',
  },
}
```

Tooltip also includes rows for Strike (with % from spot), Expiry (date + DTE), and the metric value.

---

## 10. Historical GEX Snapshot Scrubber (Phase 7)

### Data source
Supabase table `gex_snapshots`. Fetched read-only via `window._sbAuthClient` (anon key).

Columns read: `snap_date, spot, call_wall, put_support, hvl, gamma_flip, regime, net_gex, strike_data, computed_at, max_pain`.

`strike_data` schema: array of `{s: strike, c: callOI, p: putOI, g: netGex}` (compact).

### Date list
`fetchSnapshotDates(ticker)`: descending `snap_date`, deduplicated, capped at 30 sessions.

### Historical matrix reconstruction
`buildMatrixFromSnapshotData(strikeData, spot)`:
- Single synthetic expiration column `'snapshot'`
- `callGex = max(0, g)`, `putGex = max(0, -g)` (splits signed net GEX)
- Vol / VEX / UNUSUAL fields set to 0 (historical = GEX only)
- `meta.isSnapshot = true`

### Mode behavior
- Lens **locked to GEX** in historical mode; other lens buttons disabled
- OI Movers panel hidden
- Trinity/Confluence mode forced off
- Historical banner shown with `snapDate`
- ESC key exits back to live

### Auto-refresh interval
```
base = isMarketHours() ? 87000ms : 300000ms
delay = base * (0.95 + Math.random() * 0.10)   // ±5% jitter
```
87s is described as "non-harmonic with flow 30s / GEX 173s" to avoid poll collisions.

---

## 11. Confluence Mode (SPX / SPY / QQQ) — Phase 8 / PRISM

Two related but distinct rendering paths exist:

### Legacy Trinity (`enterTrinity`) — GEX-pinned
Uses `renderTrinity()` + `renderMatrixPct()` with the GEX-specific bucket grid. Lens is pinned to GEX.

### PRISM Confluence (`enterConfluence`) — metric-agnostic
Uses `renderPrismConfluence()`. Lens is NOT pinned — all 5 metrics work. Fixed to **0DTE** expiration only (or nearest if no 0DTE). Shows `PR_CONF_BANDS`:
```js
PR_CONF_BANDS = [2.4, 2.0, 1.6, 1.2, 0.8, 0.4, 0, -0.4, -0.8, -1.2, -1.6, -2.0, -2.4]
```
These are fixed % offsets from spot (13 rows). Each panel maps the nearest actual strike to each % offset for display.

### Pct-bucket grid (legacy Trinity / GEX mode)
`buildPctBucketGrid()`:
- Tight core `±2%` in `0.25%` steps
- Wings `±2%` to `±5%` in `0.5%` steps
- Capped at `±5%` (was `±10%` but left most rows empty)
- Total ~25 buckets, descending

### Strike normalization
```
pct = (strike - spot) / spot * 100
```
Each strike maps to the nearest bucket (`halfStep = 0.30` tolerance at edges).

### Net GEX bucketization
Sums net GEX (`callGex - putGex`) per strike first, then maps each strike's pct to nearest bucket.

### Confluence detection (`detectTrinityAlignments`)
```
threshold = 0.5% (default)
```
For each level type `['gammaFlip', 'callWall', 'putSupport', 'hvl']`:
- Computes each index's pct-from-spot for that level
- If `max(pcts) - min(pcts) <= 0.5%`, level is "aligned" → bucket highlighted across all panels

**CONFLUENCE banner trigger**: all 3 indices present AND their gamma flips agree within `1.0%` (hard-coded):
```js
if (flips.length === 3 && spread <= 1.0) confluence = true;
```

### PRISM Confluence chip logic
A chip appears in the "Confl" column when >= 2 indices have a significant value (>= `th.strong` or is a leader) at the same % row AND same sign:
- `2/3` chip: semi-transparent green/red border
- `3/3` chip: solid green/red background + ⚡ icon

---

## 12. Fetch Layer

### API endpoint (server-side)
`/.netlify/functions/uw-chain?ticker=XXX&endpoint=option-contracts&include_prev=true&windowed=true&strike_pct=20&max_dte=14`

Parameters:
- `include_prev=true` — fetches `oi_prev` for OI movers
- `windowed=true` — server caps DTE at 60 (overridden by `max_dte`)
- `strike_pct=20` — ±20% around spot
- `max_dte=14` — only returns next 14 days of expirations (changed from 60 to reduce truncation)
- `include_volume_baseline=true` — only added when UNUSUAL lens is active; triggers "a ~200k-row, 35-day Supabase scan" server-side
- Confluence fetch: `strikePct=10, maxDte=14` (narrower window)

Server returns: `{ data: { data: [...contracts] }, timestamp, oi_prev_snapshot_date, volume_baseline_snapshot_date, truncated }`.

Timeout: 15,000 ms client-side abort.

### Session chain cache
Key: `prismChain:<ticker>` in `sessionStorage`. Max age: `10 * 60 * 1000` (10 minutes). Max entries: `CHAIN_CACHE_MAX = 8` (LRU eviction). Used for instant first-paint on page reload.

Truncated chain responses are NOT cached (`if (!_chainTruncated) _persistChainCache(...)`).

### Spot price
Extracted from `underlying_price` or `stock_price` fields on any contract. Falls back to `/.netlify/functions/price?symbol=XXX`.

---

## 13. Keyboard Shortcuts

```js
LENS_KEYS = { g: 'GEX', v: 'VEX', o: 'OI', l: 'VOL', u: 'UNUSUAL' }
RANGE_KEYS = { '1': '10', '2': '20', '3': '40' }   // strikes each side of spot
```
Ignored with Meta/Ctrl/Alt held or when focus is in `INPUT`/`TEXTAREA`/contenteditable.

ESC: exits historical mode.

---

## 14. PRISM Single View Additional Details

### Scope filter (`activeScope`)
- `'default'` — shows all `maxExpirations` columns (4 by default)
- `'0dte'` — filters to `dte < 1` expirations; if none, uses first column. No Σ All column.
- `'all'` — hides individual expiration columns, shows only Σ All column (sum across all expirations per strike)

### Normalization (`activeNorm`)
- `'global'` — heat scale relative to the maximum across all cells
- `'column'` — heat scale independently per expiration column (`colMax` array per column)

### Strike range (`activeRange`)
Default `10` strikes each side of spot. Toolbar buttons: `±10 / ±20 / ±40`. Changes `activeRange`; `buildPrismModel` uses `activeRange` as `half` for the `(2*half+1)` nearest-strike window.

### Monthly expiration detection
```js
function _prIsMonthly(dateStr) {
  return d.getDay() === 5 && d.getDate() >= 15 && d.getDate() <= 21;
}
```
Friday in range [15th–21st] = monthly. Gets a landmark icon in the expiry header.

### Spot line interpolation
Exact spot price is between two strike rows. Fractional position computed by linear interpolation between bracketing rows where `pct` crosses zero:
```
spotFrac = i + 0.5 + pct_a / (pct_a - pct_b)  // fraction between row i and i+1
spotTop = (spotFrac / nRows) * 100  // percent from top of grid
```

### Pick log telemetry
Every pick change is POSTed to `/.netlify/functions/log-pick` with:
`{ ticker, lens, spot_at_pick, chain_age_minutes, regime, gated: {...}, raw: {...} }`. Deduplicated by `signature = ticker|lens|gatedKey|rawKey`.

---

## 15. What Is Server-Side (Not in Client Code)

The following are **not** in `heatseeker-init.js`:

1. **Raw option contract data source** — UnusualWhales (uw-chain) API or similar; client only parses the JSON response.
2. **30-day volume median computation** (`volume_median_30d`, `volume_sample_count`) — computed server-side in the Netlify function from a ~35-day Supabase scan.
3. **OI baseline snapshot** (`oi_prev_snapshot_date`) — server stores yesterday's OI and returns it as `oi_prev` per contract; client does not hold this independently.
4. **GEX snapshot nightly job** (`gex_snapshots` table population) — referenced as `gex-snapshotter.js` in a comment but not present in the source bundle.
5. **GEX level computation for the GEX sidebar** (`gex.html` / `gex-engine.js`) — heatseeker replicates the level formulas client-side but the gex.html page has its own engine.
6. **`/api/ask` AI endpoint** — mentioned in Neural Web context; not referenced here.

---

## 16. Summary Statistics Panel

Displayed stats:
- Spot price + `"<ticker> · IV XX.X%"` (using `matrix.meta.medianIV`)
- Total OI (contracts)
- Total Volume today
- Put/Call ratio OI (`totalPutOI / totalCallOI`)
- Per-lens stat:
  - GEX: net signed dollar; regime text ("LONG GAMMA · range-bound" or "SHORT GAMMA · trending")
  - VEX: total magnitude + skew (`(callVex - putVex) / totalVex`); balanced if |skew| < 0.15
  - OI: total OI + call/put split
  - VOL: total volume + call/put split
  - UNUSUAL: count of unusual cells (>= 3× median) or "building baseline" message

---

*Spec covers all client-visible math, thresholds, and identifiers found in source. Server-side gaps are explicitly noted.*
