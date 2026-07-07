# MomoEdge GEX Analytics Engine — Reverse-Engineering Spec

Extracted from `/tmp/momoedge_src/gex-engine.js` (1,994 lines) and
`/tmp/momoedge_src/js/modules/gex.js` (1,731 lines).  
Date of analysis: 2026-07-06.

> **Dealer-sign assumption (explicit):** nowhere stated in client code.  
> The engine treats **calls as positive GEX** (dealers long gamma, stabilizing)  
> and **puts as negative GEX** (dealers short gamma, amplifying). This is the  
> standard "net-long-dealer" convention used by SpotGamma/SocGen, i.e. the  
> code assumes dealers **sold** the options the chain records as OI.

---

## 1. Input / Data Pipeline

### 1.1 Options-chain source
- **Primary (Wave 2 / server grid):** `/.netlify/functions/computed-grid?ticker=<TICKER>`  
  Returns a pre-built JSON blob with keys `spot`, `levels`, `classification`,
  `analytics`, `totals`, `strikes`, `step`, `unique_strikes`,
  `server_duration_ms`, `grid_cached`.  
  Called first; falls back to client compute on any error or spot divergence > 3%.
- **Supabase live-snapshot table:** `gex_snapshots_live` (Supabase project
  `pojiqfeemksvocnaellu.supabase.co`).  
  Fresh threshold: **3 minutes** in market hours, **30 minutes** when market
  closed. Fields consumed: `computed_at`, `levels`, `classification`,
  `spot`, `gamma_flip`, `call_wall`, `put_support`, `hvl`, `regime`,
  `net_gex`, `gamma_flip_dislocated`, `gamma_flip_confidence`,
  `volatility_trigger`, `vol_trigger_confidence`, `stability_pct`,
  `gravity_up_pct`, `strike_data`.
- **Historical snapshot table:** `gex_snapshots` — upserted per
  `(ticker, snap_date)`; used only for snapshot-diff.
- **Raw chain fallback:** Netlify function `config.UW_CHAIN_API` (variable
  `STRUCT_CHAIN_URL`); called via `window.ChainCache.fetch()` with options
  `{ windowed: true, strike_pct: 50, max_dte: 180 }` for admin users.
- **Spot price source hierarchy:** `ws.PRICE_CACHE[ticker].price` →
  `underlying_price` / `stock_price` from chain rows → `config.PRICE_API`
  REST call → OI-weighted strike centroid fallback (if all else fails; flagged
  as approximate).

### 1.2 Contract normalization (`Validators.contract`)
Fields read (with aliases):
- `strike` / `strike_price` — parsed as float, must be > 0
- `openInterest` / `oi` / `open_interest` — parsed as int, must be ≥ 0
- `gamma` — parsed as float; stored as `Math.abs(gamma)`
- `type` / `optionType` / `option_type` / `side` — coerced to lowercase,
  must equal `"call"` or `"put"`
- `delta` — parsed as float, default 0
- `impliedVolatility` / `iv` — parsed as float, default 0
- `expiration` / `expirationDate` / `expires_at`
- `volume` — parsed as int, default 0

Contracts with invalid strike, non-finite OI, non-finite gamma, or invalid
type are **dropped and counted**. Up to 10 drop reasons are logged.

### 1.3 Expiry handling
Expiry string is split at `T`, appended `T20:00:00Z` (i.e. 8 PM UTC),
parsed to ms. Contracts where `expMs < now - 6h` are dropped as expired.
`dteDays = max(0.01, max(config.minDTE, (expMs - now) / 86_400_000))`.

---

## 2. Per-Strike GEX Computation (`GexCalculator.compute`)

### 2.1 Configuration defaults
```
contractMultiplier : 100
pctScale           : 0.01
minOI              : 0
minGamma           : 0
groupByStrike      : true
dteWeighting       : false
minDTE             : 0.1
```

### 2.2 Raw GEX formula
For each contract:
```
rawGex = oi * effectiveGamma * spot² * dteWeight * 100 * 0.01
```
Expanding: `rawGex = oi * γ * S² * dteWeight`  
(`contractMultiplier * pctScale = 100 * 0.01 = 1`, so the 1% dollar-move
convention is embedded in pctScale.)

`effectiveGamma` is taken from chain data (`|gamma|`). If `gamma == 0` and
`dteDays` and `iv` are available, it is computed via `_bsGamma` (see §3).

`dteWeight` = 1 by default; if `dteWeighting` is enabled:
`dteWeight = min(4.0, 1/√dteDays)`.

### 2.3 Aggregation per strike
Each strike bucket accumulates:
- `callGex` += rawGex (calls only)
- `putGex` += rawGex (puts only)
- `callOI`, `putOI` summed
- `callGamma`, `putGamma` = **max** (not sum) of effectiveGamma across expirations
- `callVolume`, `putVolume` summed

Output per-strike row:
```
netGex   = round(callGex - putGex)
callGex  = round(callGex)
putGex   = round(-putGex)   ← sign-flipped for chart display
totalOI  = callOI + putOI
```

### 2.4 Totals
```
netGex      = round(totalCallGex - totalPutGex)
pcRatio     = totalPutOI / totalCallOI   (0 if no calls)
```

---

## 3. Black-Scholes Gamma Fallback

### 3.1 Simple BS gamma (`_bsGamma`) — Method 1 and client-side fallback
Inputs: `S` (spot), `K` (strike), `iv` (decimal), `dteDays`, `fallbackIV`
```
r  = 0.05   (BS_RISK_FREE_RATE, hardcoded)
T  = max(dteDays / 365, 0.001)
d1 = [ln(S/K) + (r + 0.5·σ²)·T] / (σ·√T)
γ  = φ(d1) / (S·σ·√T)
```
`φ(x) = exp(-0.5·x²) / √(2π)` (standard normal PDF).  
If `iv <= 0`, uses `fallbackIV` (defaulting to 0.30).  
Returns 0 on any non-finite result.

### 3.2 BS gamma with continuous dividend yield (`_bsGammaWithYield`) — Method 2
Inputs add `q` (continuous yield) and per-ticker dividend yield table:
```
d1 = [ln(S/K) + (r - q + 0.5·σ²)·T] / (σ·√T)
γ  = exp(-q·T) · φ(d1) / (S·σ·√T)
```
Dividend yields hardcoded in `DIVIDEND_YIELDS` map (selected entries):
```
SPY: 0.013   QQQ: 0.006   IWM: 0.011   DIA: 0.018
XLE: 0.030   XLU: 0.030   XLRE: 0.035
TLT: 0.038   HYG: 0.060
GLD: 0.000   SLV: 0.000   USO: 0.000
```
Any ticker not in the map uses `q = 0` (same as `_bsGamma`).

### 3.3 Client-side IV fallback (gex.js)
When computing via raw chain, median IV is computed across all contracts
with `0.01 < iv < 5.0` and used as the per-contract fallback when `iv` is
missing/invalid. Default of 0.30 used if no contracts have valid IV.

---

## 4. Level Detection (`LevelDetector.detect`)

### 4.1 Strike step estimation
Median of pairwise differences among the first 20 sorted strikes.
Used to set proximity thresholds:
```
minCwAbove = avgStep * 2    (minimum distance above spot for call-wall candidates)
minPsBelow = avgStep * 2    (minimum distance below spot for put-support candidates)
minSpread  = avgStep * 5    (minimum CW−PS spread enforced)
```

### 4.2 Call Wall
Score function: `callOI * callGamma` (or `callGamma = 0.001` if zero).  
Candidates: strikes where `strike >= spot + minCwAbove`.  
Winner selected via `_pickWithHysteresis(candidates, scoreFn, spot, tolerance=0.05)`:
- Find best (max score) candidate.
- Collect all candidates within 5% of the best score (i.e., `score >= bestScore * 0.95`).
- Among tied candidates, pick the one **closest to spot**.

Fallback if no candidate above threshold: `findMax(strikes_above_spot, 'callGex')`.  
Fallback if no strikes above spot: highest-strike in chain.

### 4.3 Put Support
Score function: `putOI * putGamma`.  
Candidates: strikes where `strike <= spot - minPsBelow`.  
Same hysteresis logic, same 5% tolerance.  
Fallback: `findMax(strikes_below_spot, 'putOI')`.

### 4.4 HVL (High-Value Level / Magnet)
Score function:
```
totalOI = callOI + putOI
avgGamma = (callGamma + putGamma) / 2
distFromSpot = |strike - spot|
proximity = 1 / (1 + distFromSpot / (avgStep * 3))
score = totalOI * avgGamma * proximity
```
Pool: strikes between putSupport and callWall (falls back to all strikes if < 2).  
Hysteresis tolerance = 0.03 (3%).  
HVL position is then constrained:
- If `hvl <= putSupport + 0.15*(cw-ps)`: snap to `putSupport + 0.4*(cw-ps)`
- If `hvl >= callWall - 0.15*(cw-ps)`: snap to `putSupport + 0.6*(cw-ps)`

### 4.5 Level validation / sanity clamps
- If `callWall.strike <= spot`: push to `spot + minCwAbove`
- If `putSupport.strike >= spot`: push to `spot - minPsBelow`
- If `cw - ps < minSpread`: expand symmetrically around midpoint

---

## 5. Gamma Flip Detection

### 5.1 Method 1 — Cumulative zero-crossing (`_findGammaFlip`)
Walk strikes ascending; accumulate `cumulative += netGex`.  
Between adjacent strikes, detect sign change in cumulative; interpolate:
```
ratio = |cumulative_a| / (|cumulative_a| + |cumulative_b|)
crossing = strike_a + ratio * (strike_b - strike_a)
```
Filter crossings to `|crossing - spot| / spot <= 0.15` (plausible-flip window).  
From plausible crossings, pick the one closest to spot.

If no plausible crossing: fallback to local sign-change in per-strike netGex
(same interpolation), still within 15% window.

Confidence:
- `flipDistPct < 5%` → `'high'`
- `5% ≤ flipDistPct < 10%` → `'medium'`
- `flipDistPct ≥ 10%` → `'low'`, `dislocated = true`
- No crossing found → `confidence = 'none'`, `flipStrike = spot`

### 5.2 Method 2 — Gamma Profile (institutional standard, `_findGammaFlipProfile`)
Preferred when per-contract `_contracts` array is available (has iv + dteDays).

Grid: `±10%` around spot in `1%` steps (default `gridPct=0.10, gridStep=0.01`).  
For each hypothetical spot `S_hat`:
```
netGex(S_hat) = Σ_{contracts} sign(c) * [c.oi * γ(S_hat,K,σ,T,q) * S_hat² * 100 * 0.01]
```
where `sign = +1` for calls, `-1` for puts.  
`γ` uses the dividend-adjusted formula (`_bsGammaWithYield`).  
Identifies **upcrosses** only (netGex going negative→positive as spot rises).  
Picks the upcross closest to current spot.

Method 2 confidence thresholds:
- `flipDistPct < 3%` → `'high'`
- `3% ≤ flipDistPct < 7%` → `'medium'`
- `flipDistPct ≥ 7%` → `'low'`, `dislocated = true`
- No crossing → `'none'`

Method 2 is tried first. If it fails or returns null, Method 1 is used.
Result carries `method: 'profile'` or `method: 'cumulative'`.

### 5.3 Volatility Trigger (Method 2 only)
Computed when `confidence !== 'none'`.  
Below the flip point, scans for a spot where:
1. `netGex(S_hat) <= -0.10 * maxPosGexAboveFlip`
2. Slope of gamma profile is positive (approaching zero from below)
3. Accumulated negative area below flip `<= -0.25 * positiveArea above flip`

First point satisfying all three becomes `volatilityTrigger.strike`.  
Trigger confidence: same distance thresholds as flip (3% / 7%).

---

## 6. Regime Classifier (`StrikeClassifier.classify`)

### 6.1 Stability ratio
```
posGex  = Σ max(0, netGex_i)    over strikes within 20% of spot
negGex  = Σ |min(0, netGex_i)|
ratio   = posGex / (posGex + negGex)
stabilityPct = round(ratio * 100)
```
Noise floor guard: if `|posGex| + |negGex| < max(1000, spot * 100)`, returns
`UNKNOWN` state.

### 6.2 State classification (exact thresholds)
```
nearFlip  = flipDistPct < 0.2%
closeFlip = flipDistPct < 0.5%

if flipIsKnown AND nearFlip:                       → TRANSITION
elif ratio > 0.75:                                 → DRIFT
elif ratio > 0.65:                                 → PIN
elif ratio > 0.55:                                 → RANGE
elif flipIsKnown AND closeFlip AND ratio > 0.35:   → TRANSITION
elif ratio > 0.45:                                 → RANGE
elif ratio > 0.30:                                 → TREND
else:                                              → CASCADE
```

State descriptions:
- `PIN`: "Strong dealer stabilization — price pinned near magnet"
- `DRIFT`: "Saturated positive gamma — passive positioning, weaker pinning"
- `RANGE`: "Positive gamma — mean-reverting, bounded by walls"
- `TRANSITION`: "Near gamma flip — regime change possible, high sensitivity" (displayed as "SHIFT")
- `TREND`: "Negative gamma — moves amplified by dealer hedging"
- `CASCADE`: "Deep negative gamma — sharp moves likely, hedging cascades"

State confidence: `round(0.5 + |ratio - 0.5| * 0.9, 2)`

### 6.3 Call Wall / Put Support in classifier (`StrikeClassifier`)
Uses a separate scoring path from `LevelDetector`:
- **Call Wall score**: `max(0, netGex) + callOI * callGamma`, hysteresis 5%
- **Put Support score**: `|min(0, netGex)| + putOI * putGamma`, hysteresis 5%
- `minGammaForLevel = 0.0001`

**Magnet** (classifier's HVL equivalent):
```
score = totalOI * proximity * (0.5 + min(cpRatio, 1/cpRatio) * 0.5)
proximity = 1 / (1 + distancePct / 0.01)
```
Magnet is set to null if `cpRatio < 0.3` (call/put ratio too lopsided;
`cpRatio = callOI / putOI`).

`isBalanced = (cpRatio >= 0.6 AND cpRatio <= 1.67)`.

### 6.4 Cascade / Upside trigger selection
Below-flip (cascade): from negative-netGex strikes below flip, score:
```
cascadeThreshold = 75th-percentile intensity of negative strikes   (or 0.05 if ≤3)
intensity = |netGex| / maxAbsGex
proximity = 1 / (1 + distToFlip / avgStep)
score = intensity * (0.6 + proximity * 0.4)
```
Pick highest-scored strike not equal to putSupport. Excluded if score
< cascadeThreshold or netGex ≥ 0.

Above-flip (upside trigger): same scoring on positive-netGex strikes above flip,
excluding callWall.

Trigger confidence: `0.4 + intensity * 0.4`.

### 6.5 Gravity calculation (within classifier)
```
for each strike s:
  dist   = |s.strike - spot|
  weight = 1 / (dist + avgStep)
  if s.strike > spot:
    if netGex > 0: pullUp   += netGex * weight
    else:          pullDown += -netGex * weight
  elif s.strike < spot:
    if netGex < 0: pullDown += -netGex * weight
    else:          pullUp   += netGex * weight

gravUpPct   = round(pullUp / (pullUp + pullDown) * 100)
gravDownPct = 100 - gravUpPct
direction = 'up' if gravUpPct > 60 else 'down' if gravDownPct > 60 else 'neutral'
```

### 6.6 Dealer Bands (`_computeDealerBands`)
Walks cumulative GEX data; identifies contiguous zones where `cumGex >= 0`
(`STABILITY` / `DEALER_LONG_GAMMA`) and `< 0` (`VOLATILITY` / `DEALER_SHORT_GAMMA`).
Returns:
- `stabilityBand`: zone containing spot or nearest positive-cumGex zone
- `volatilityBand`: nearest negative-cumGex zone
- `accelerationBands`: top-5 strike pairs by `|Δcum| / Δstrike` (steepest
  GEX gradient)

---

## 7. GEX Analytics (`GexAnalytics.analyze`)

### 7.1 Gamma Acceleration
Window: 3 strikes above spot, 3 below (centered at first strike ≥ spot).
```
slopeUp   = avg(|ΔGEX / Δstrike|) over up-window
slopeDown = avg(|ΔGEX / Δstrike|) over down-window
avgSlope  = (|slopeUp| + |slopeDown|) / 2
relScore  = min(100, round(avgSlope / maxAbsGex * 500))
absScale  = min(1, (maxAbsGex / 1000)^0.5)
score     = round(relScore * absScale)
```
Thresholds: `score > 70` → `'high'`, `> 35` → `'medium'`, else `'low'`.

### 7.2 Liquidity Gravity (`_liquidityGravity`)
Same formula as §6.5 but using `levels` (LevelDetector output) not classifier.
`direction = 'up' if upPct > 60, 'down' if downPct > 60, else 'neutral'`
`magnetStrike = levels.hvl.strike`

### 7.3 Path Projection
Positive-gamma regime: `likelyDirection = 'down_to_magnet'` if `spot > hvl`,
else `'up_to_magnet'`.  
Negative-gamma regime: follows `gravity.direction` (`trending_higher` /
`trending_lower`).

### 7.4 Pin Probability
```
for each strike s:
  totalOI = callOI + putOI
  avgGamma = (callGamma + putGamma) / 2
  dNorm = |strike - spot| / (spot * 0.01)
  score = (totalOI * avgGamma) / (1 + dNorm²)
  totalScore += score

probability = min(95, round(bestScore / totalScore * 100))
top3 = top-3 strikes by score
```

### 7.5 Market Bias (`_marketBias`)
Positive-gamma regime:
```
rangeLow  = round(hvl - (hvl - ps) * 0.6)
rangeHigh = round(hvl + (cw - hvl) * 0.6)
verdict   = "Range expected {rangeLow}–{rangeHigh}"
```
Negative-gamma: verdict follows gravity direction toward CW or PS.

---

## 8. Snapshot Diff (`SnapshotPipeline.diff`)

Compares current `levels` (CW, HVL, PS) against prior snapshot row from
`gex_snapshots` table (most recent date < today).

**Level shifts:**
```
cwDelta  = current.callWall.strike - prior.call_wall
hvlDelta = current.hvl.strike - prior.hvl
psDelta  = current.putSupport.strike - prior.put_support
avgShift = (cwDelta + hvlDelta + psDelta) / 3
```
`shiftDirection`:
- `'higher'` if `avgShift > 0.5`
- `'lower'` if `avgShift < -0.5`
- `'mixed'` if not unchanged but one or more individual deltas > 0
- `'unchanged'` otherwise

**OI delta per strike:**
Prior OI stored as `strike_data[].{s, c, p, g}` (strike, callOI, putOI, netGex).
```
delta   = currTotal - prevTotal
pctChange = delta / prevTotal * 100   (100% if no prior)
oiAboveSpot += delta  (for strikes >= spot)
oiBelowSpot += delta  (for strikes < spot)
```

**Top clusters:**
- `newOI`: top-3 strikes by positive delta
- `exitOI`: top-3 strikes by negative delta

**Liquidity flow:**
```
totalOIDelta > 0 → 'expansion'
  oiAboveSpot > oiBelowSpot * 1.5  → direction = 'higher'
  oiBelowSpot > oiAboveSpot * 1.5  → direction = 'lower'
  else                               → direction = 'broad'
totalOIDelta < 0 → 'drain'   (similar logic for 'from_above' / 'from_below')
totalOIDelta = 0 → 'neutral'
```

---

## 9. Market-State Card Fields (`renderOracleMarketStructure`)

Rendered as 4-column grid. Every field name and source:

| Display label | Source field | Notes |
|---|---|---|
| MARKET STATE (regime) | `regime.state` / `snap.regime` | COLOR: CASCADE/TREND=#ff6b5a, TRANSITION=#ffb300, PIN=#00ff88, DRIFT/RANGE=#00e5ff |
| Regime description | `regime.stateDescription` | |
| Net γ badge | `regime.netGamma` / `snap.net_gex >= 0` | POSITIVE/NEGATIVE/UNKNOWN |
| Stability bar | `regime.stabilityPct` or `analytics.stabilityPct` | vol% = 100 - stability% |
| MAGNET | `snap.hvl` / `regime.pricePull.strike` | |
| Flip distance text | `snap.gamma_flip`, `snap.spot` | "Flip at X · Spot ±Y" |
| Vol zone badge | Derived from `flipDistPct` and regimeState | STABLE / TRANSITION ZONE / VOLATILITY ZONE |
| CASCADE TRIGGER | `regime.cascadeLevel.strike` (if `confidence >= 0.4`) | Shown only for CASCADE/TRANSITION/TREND |
| CALL WALL | `snap.call_wall` | |
| PUT SUPPORT | `snap.put_support` | |
| Spot-in-range slider | Computed `spotPct = (spot - ps) / (cw - ps) * 100` | |
| Gamma flip tick | `flipPct = (flip - ps) / (cw - ps) * 100` | |
| Bias verdict | `analytics.bias.verdict` | |
| Bias dot color | `analytics.gravity.direction` | up=#00ff88, down=#ff4466 |
| Hedging pressure | `analytics.acceleration.level` | high=#ff4466, medium=#ffb300, low=#00ff88 |
| Gravity pull | `analytics.gravity.upPct / downPct` | |
| Pin target | `analytics.pin.strike`, `pin.probability` | |

Secondary card ("ORACLE STRUCTURAL STATE"):
- `structState.squeeze_state` / `structState.cascade_state`: NONE / BUILDING / ACTIVE
- `structState.contributing_flows`, `structState.top_relevance_score`
- `structState.explanation` (auto-generated narrative)
- `structState._fading`: state TTL preservation for 2 hours (`STRUCT_STATE_TTL = 2h`)

Alert-fire gate:
- Only ACTIVE (not BUILDING) states trigger DB writes
- `top_relevance_score >= 68` required
- Total contributor premium >= $500K
- Dedup: 8-hour per-`ticker:alertType` window
- Market hours only (Mon–Fri, times from `config.MARKET_OPEN_MINS` /
  `config.MARKET_CLOSE_MINS`, default close = 975 minutes = 16:15 ET)

---

## 10. Supabase Tables Referenced

| Table | Operation | Notes |
|---|---|---|
| `gex_snapshots_live` | SELECT | Live computed snapshot; freshness gate 3min/30min |
| `gex_snapshots` | UPSERT + SELECT | Historical per `(ticker, snap_date)` |
| `structural_alerts` | SELECT + INSERT + PATCH | Squeeze/cascade event log; admin-gated writes |
| `trader_profiles` | SELECT `is_admin` | Admin check for write access |

---

## 11. Caching Architecture

| Layer | TTL (market hours) | TTL (closed) |
|---|---|---|
| In-memory `STRUCT_CACHE` | `config.STRUCT_CACHE_TTL_MS` | 30 minutes |
| Prewarm (background tiles) | 8 minutes | 30 minutes |
| `gex_snapshots_live` freshness | 3 minutes | 30 minutes |
| State history (`STRUCT_STATE_HISTORY`) | 2 hours (TTL, fading) | same |
| In-memory eviction age | 30 minutes | same |
| In-memory cap | 20 tickers | same |

Spot-divergence bypass: if live price has moved > 3% from cached/snapshot spot,
the cache or snapshot is bypassed and a fresh chain fetch is triggered.

---

## 12. Server-Side Components (not in client code)

The following are **inferred from client fetch patterns**; implementation
is server-side and not visible:

- `/.netlify/functions/computed-grid` — pre-builds full GEX grid, levels,
  classification, analytics for a ticker. Cached server-side (flag `grid_cached`
  in response). Likely runs same `GexCalculator` + `StrikeClassifier` logic.
- `config.UW_CHAIN_API` — options chain data supplier (likely Unusual Whales
  endpoint, per `UW_CHAIN_API` naming and `uw-chain.js` reference).
- `config.PRICE_API` — price feed endpoint.
- `window.ChainCache` (`chain-cache.js`) — shared cache layer for raw chain
  data; handles windowing and pagination.
- `window.StructuralEngine` (`structural-engine.js`) — flow-to-structure bridge
  that classifies individual option flows as `SQUEEZE_CONTRIBUTOR` or
  `CASCADE_CONTRIBUTOR` relative to GEX snapshot. Called via
  `StructuralEngine.analyzeBatch(flows, gexSnapshot)` and
  `StructuralEngine.getTickerState(analyzed, gexSnapshot)`.

---

## 13. Index Blacklist

Tickers excluded from structural ticker bar and flow analysis:
```
['SPX', 'SPXW', 'RUT', 'RUTW', 'VIX', 'NDX', 'DJX', 'XSP']
```
SPY is always inserted as the default ticker.
