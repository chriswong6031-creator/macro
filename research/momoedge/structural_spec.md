# MomoEdge Structural Engine — Reverse-Engineering Spec

**Source file:** `structural-engine.js`
**Engine version:** `1.2.0` (constant `VERSION = '1.2.0'`)
**Architecture:** Fully stateless. The terminal orchestrates data flow. Receives `(flowEvent, gexSnapshot)` and returns structural analysis; no internal state is maintained between calls.

---

## 1. Data Contracts

### 1.1 `gexSnapshot` (input)

| Field | Type | Notes |
|---|---|---|
| `spot` | float | Current underlying price; required and must be > 0 |
| `gamma_flip` | float | Gamma-flip level; optional if cw or ps present |
| `call_wall` | float | Call wall level |
| `put_support` | float | Put support level |
| `net_gex` | float | Net gamma exposure; sign is decisive for CASCADE |
| `regime` | string | `'CASCADE'` / `'TRANSITION'` / `'TREND'` (case-insensitive, uppercased internally) |
| `gamma_flip_dislocated` | bool | Flag — if true and spot is not near the alternate level, setup detection short-circuits |
| `ticker` | string | Used in `getTickerState` output |

Validation: at least one of `gamma_flip`, `call_wall`, `put_support` must be a finite positive number, otherwise all analysis returns an empty/neutral result.

### 1.2 `flowEvent` (input — "normalized flow object from the Flow Engine")

| Field | Aliases | Notes |
|---|---|---|
| `ticker` | — | Required; uppercased |
| `type` / `put_call` | — | `'CALL'` or `'PUT'` |
| `strikeNum` / `strike` | — | Numeric; falls back to `spot` if missing |
| `execLabel` / `execution_type` / `sideRaw` | — | Execution side; see §3 normalization |
| `alertRule` / `alert_rule` | — | Used to detect sweep prefix |
| `classification` | — | `'HEDGE'` / `'LIKELY HEDGE'` / `'CLOSING/ROLL'` / `'AMBIGUOUS'` / directional |
| `sizeOi` / `size_to_oi` | — | Size-to-OI ratio (float) |
| `premRaw` / `premium` | — | Raw premium in dollars |
| `score` / `conviction_score` | — | 0–100 conviction score; drives relevance weighting |
| `contracts` | — | Contract count (used in aggregation) |
| `oi` | — | Open interest (used in aggregation) |
| `expiry` | — | ISO date string; first 10 chars used as aggregation key |
| `_timestamp` | — | Unix ms; used for aggregation/clustering |
| `id` | — | Used in aggregated ID arrays |

---

## 2. Distance and Proximity Computations

### 2.1 Distance formulas (`computeDistances`)

All distances are **absolute percentage** of the reference level:

```
distance_to_flip        = |spot   - gamma_flip|  / gamma_flip      (or 999 if flip <= 0)
distance_to_call_wall   = |spot   - call_wall|   / call_wall       (or 999 if cw <= 0)
distance_to_put_support = |spot   - put_support| / put_support     (or 999 if ps <= 0)

strike_to_flip          = |strike - gamma_flip|  / gamma_flip      (or 999)
strike_to_call_wall     = |strike - call_wall|   / call_wall       (or 999)
strike_to_put_support   = |strike - put_support| / put_support     (or 999)
```

Strike defaults to `spot` when `strikeNum`/`strike` is absent or zero.

### 2.2 Proximity thresholds (`computeProximityFlags`)

```javascript
var FLIP_PROXIMITY = 0.01;   // 1% — used for gamma-flip proximity
var WALL_PROXIMITY = 0.02;   // 2% — used for call wall and put support proximity
```

Boolean flags:

| Flag | Condition |
|---|---|
| `is_near_flip` | `distance_to_flip <= 0.01` |
| `is_near_call_wall` | `distance_to_call_wall <= 0.02` |
| `is_near_put_support` | `distance_to_put_support <= 0.02` |
| `strike_near_flip` | `strike_to_flip <= 0.01` |
| `strike_near_call_wall` | `strike_to_call_wall <= 0.02` |
| `strike_near_put_support` | `strike_to_put_support <= 0.02` |

---

## 3. Flow Intent Computation (`determineFlowIntent`)

### 3.1 Execution type normalization (`normalizeExecType`)

Input: `flow.execLabel || flow.execution_type || flow.sideRaw`, lowercased and camelCase-split with spaces. Also reads `alertRule`/`alert_rule` for sweep detection.

Normalization rules (in priority order):

| Raw contains | Sweep flag? | Normalized output |
|---|---|---|
| `near_ask` / `near ask` / `n_a` | yes | `sweep_ask` |
| `near_ask` / `near ask` / `n_a` | no | `near_ask` |
| `near_bid` / `near bid` / `n_b` | yes | `sweep_bid` |
| `near_bid` / `near bid` / `n_b` | no | `near_bid` |
| `above_mid` / `above mid` / `a_m` | yes | `sweep_ask` |
| `above_mid` / `above mid` / `a_m` | no | `ask` |
| `ask` or `above` | yes | `sweep_ask` |
| `ask` or `above` | no | `ask` |
| `bid` or `below` | yes | `sweep_bid` |
| `bid` or `below` | no | `bid` |
| `mid` | — | `mid` |
| (no match) | yes | `sweep_ambiguous` |
| (no match) | no | `unknown` |

Sweep detection: `alertRule.indexOf('sweep') >= 0`.

### 3.2 Directional classification sets

```javascript
var BULLISH_EXEC_TYPES = ['ask', 'sweep_ask', 'near_ask', 'at ask', 'above ask', 'above_ask'];
var BEARISH_EXEC_TYPES = ['bid', 'sweep_bid', 'near_bid', 'at bid', 'below bid', 'below_bid'];
```

### 3.3 Hedge/irrelevant classification set (penalty / early exit)

```javascript
var HEDGE_CLASSIFICATIONS = ['HEDGE', 'LIKELY HEDGE', 'CLOSING/ROLL', 'AMBIGUOUS'];
```

If `classification` matches any of these, `determineFlowIntent` immediately returns `{ flow_intent: 'neutral', intent_confidence: 'low' }`.

### 3.4 Intent decision matrix

| put_call | exec in BULLISH_EXEC_TYPES | exec in BEARISH_EXEC_TYPES + sizeOi >= 0.25 AND premium >= $250K | result |
|---|---|---|---|
| CALL | yes | — | `bullish`, confidence `high` |
| CALL | — | yes | `bearish`, confidence `medium` |
| PUT | yes | — | `bearish`, confidence `high` |
| PUT | — | yes | `bullish`, confidence `medium` |
| any | neither | neither | `neutral`, confidence `low` |

The `sizeOi >= 0.25 && premium >= 250000` gating applies only to the **contrarian** leg (call bought at bid = bearish, put bought at bid = bullish).

---

## 4. Setup Detection

### 4.1 UPSIDE SQUEEZE (`detectUpsideSqueeze` → `structural_setup = 'SQUEEZE_CONTRIBUTOR'`)

All conditions must pass (AND logic):

1. `flow_intent === 'bullish'`
2. `classification` NOT in `HEDGE_CLASSIFICATIONS`
3. `conviction_score >= 55`
4. Size gate: `sizeOi >= 0.20` OR `(premium >= 1_000_000 AND sizeOi >= 0.10)` — large-premium bypass at half the size threshold
5. Level proximity: `is_near_flip OR is_near_call_wall`
6. Dislocation guard: if `NOT is_near_call_wall AND gex.gamma_flip_dislocated` → REJECT (prevents spurious flip proximity when flip level is stale/wide)
7. Above-flip limit: if `flip > 0` and `spot > flip` and `(spot - flip)/flip > 0.005` (>0.5% above flip) → REJECT
8. Regime check: `regime` must be in `['TRANSITION', 'CASCADE', 'TREND']` (NOTE: all three valid regimes are listed, so this is effectively a validity check that regime is non-empty/known)

Valid regimes constant: `var SQUEEZE_REGIMES = ['TRANSITION', 'CASCADE', 'TREND']`

### 4.2 DOWNSIDE CASCADE (`detectDownsideCascade` → `structural_setup = 'CASCADE_CONTRIBUTOR'`)

All conditions must pass:

1. `flow_intent === 'bearish'`
2. `classification` NOT in `HEDGE_CLASSIFICATIONS`
3. `conviction_score >= 55`
4. Size gate: same as above — `sizeOi >= 0.20` OR `(premium >= 1_000_000 AND sizeOi >= 0.10)`
5. Level proximity: `is_near_flip` OR `(is_near_put_support AND (flip <= 0 OR spot < flip))`
   - Put-support proximity only counts when spot is BELOW the gamma flip (or no flip exists)
6. Dislocation guard: if `NOT is_near_put_support AND gex.gamma_flip_dislocated` → REJECT
7. Regime check: `regime` must be in `['CASCADE', 'TRANSITION', 'TREND']`
8. **GEX sign gate: `net_gex < 0`** — cascade requires negative net GEX (dealers are short gamma); this is the hardest gate distinguishing CASCADE from SQUEEZE

Valid regimes constant: `var CASCADE_REGIMES = ['CASCADE', 'TRANSITION', 'TREND']`

**Key asymmetry:** SQUEEZE has an "above-flip distance cap" (>0.5% rejects); CASCADE has a net_gex sign gate. These encode different market mechanics.

---

## 5. Structural Relevance Score (`computeRelevanceScore`)

Score range: 0–100 (clamped with `Math.max(0, Math.min(100, Math.round(score)))`).

### 5.1 Positive contributions

| Component | Formula / Value |
|---|---|
| Conviction score | `conviction_score * 0.30` (so a score of 100 contributes 30 pts) |
| Intent confidence = `high` | +15 |
| Intent confidence = `medium` | +8 |
| Intent confidence = `low` | +2 |
| Spot near flip (`is_near_flip`) | +15 |
| Spot near call wall (`is_near_call_wall`) | +12 |
| Spot near put support (`is_near_put_support`) | +12 |
| Strike near flip (`strike_near_flip`) | +3 |
| Strike near call wall (`strike_near_call_wall`) | +3 |
| Strike near put support (`strike_near_put_support`) | +3 |
| Regime = `CASCADE` | +10 |
| Regime = `TRANSITION` | +6 |
| Regime = `TREND` | +4 |
| Setup = `SQUEEZE_CONTRIBUTOR` | +20 |
| Setup = `CASCADE_CONTRIBUTOR` | +20 |

### 5.2 Penalties

| Condition | Value |
|---|---|
| classification = `HEDGE` | −20 |
| classification = `CLOSING/ROLL` | −12 |
| classification = `LIKELY HEDGE` | −10 |
| classification = `AMBIGUOUS` | −10 |
| structural_setup = `NONE` | −10 |

### 5.3 Score ceiling analysis

Maximum theoretical score (conviction=100, high confidence, near flip + call wall, CASCADE regime, SQUEEZE/CASCADE contributor):
`30 + 15 + 15 + 12 + 3 + 3 + 10 + 20 = 108` → clamped to 100.

---

## 6. Output Object (`analyze` return value)

```
{
  flow_intent,                  // 'bullish' | 'bearish' | 'neutral'
  intent_confidence,            // 'high' | 'medium' | 'low'
  structural_setup,             // 'SQUEEZE_CONTRIBUTOR' | 'CASCADE_CONTRIBUTOR' | 'NONE'
  structural_relevance_score,   // 0–100 integer
  structural_label,             // human-readable string
  structural_explanation,       // generated narrative string

  is_near_flip,                 // bool
  is_near_call_wall,            // bool
  is_near_put_support,          // bool
  strike_near_flip,             // bool
  strike_near_call_wall,        // bool
  strike_near_put_support,      // bool

  _engine_version,              // '1.2.0'
  _gex_regime,                  // uppercased regime string
  _gex_spot,                    // float
  _gex_flip,                    // float
  _gex_net                      // float
}
```

Labels:
- `SQUEEZE_CONTRIBUTOR` → `'BULLISH FLOW NEAR GAMMA FLIP'`
- `CASCADE_CONTRIBUTOR` → `'BEARISH FLOW IN CASCADE ZONE'`
- `NONE` → `'NO STRUCTURAL SIGNAL'`

---

## 7. Near-Duplicate Flow Aggregation (`aggregateFlows`)

### 7.1 Time window

```javascript
var AGGREGATION_WINDOW_MS = 2000;  // 2 seconds
```

Flows within 2 seconds of each other sharing the same group key are collapsed into a single synthetic flow.

### 7.2 Group key

Five-part key: `ticker | strike | expiry(first 10 chars) | sideBucket | ruleBucket`

- `sideBucket`: `'ask'` (contains 'ask'/'above'), `'bid'` (contains 'bid'/'below'), `'mid'`, or `'unknown'`
- `ruleBucket`: `'sweep'` (alertRule contains 'sweep'), `'block'` (contains 'block'), or `'other'`

### 7.3 Merge logic

When N flows collapse:

| Field | Merge rule |
|---|---|
| `premRaw` | SUM of all |
| `prem` (display) | Reformatted: `$X.XM` if >= $1M, else `$XXXK` |
| `contracts` | SUM of all |
| `oi` | MAX of all (not sum — avoids double-counting OI) |
| `sizeOi` | `totalContracts / maxOi` (recomputed) |
| `score` | MAX of all |
| `_aggregated` | `true` |
| `_aggregatedCount` | N |
| `_aggregatedIds` | array of original flow IDs |
| All other fields | Inherited from the chronologically first flow in the group |

---

## 8. Ticker State Build (`getTickerState`)

### 8.1 Inputs

Takes an array of already-analyzed (enriched) flow events (output of `analyzeBatch`) plus the `gexSnapshot`.

### 8.2 20-minute clustering (`countClustered`)

```javascript
var WINDOW_MS = 20 * 60 * 1000;  // 20 minutes = 1,200,000 ms
```

For flows with valid `_timestamp`, finds the maximum count of flows within any rolling 20-minute window. Flows without timestamps all count individually (no clustering penalty).

### 8.3 State thresholds

For both `squeeze_state` and `cascade_state`, using the 20-min cluster count and top relevance score:

| Condition | State |
|---|---|
| clustered >= 6 | `ACTIVE` |
| clustered >= 4 AND topScore > 80 | `ACTIVE` |
| clustered >= 4 | `BUILDING` |
| flowCount >= 2 AND topScore >= 70 | `BUILDING` |
| otherwise | `NONE` |

Constant: `var BUILDING_SINGLE_FLOW_MIN_SCORE = 70`

### 8.4 Strike dispersion / vol-ladder suppression

```javascript
var VOL_LADDER_THRESHOLD = 0.02;  // 2% of spot price

strikeDispersion = (maxStrike - minStrike) / spot
```

If `strikeDispersion > 0.02` for an `ACTIVE` state, it is **demoted to `BUILDING`**. This prevents a "vol ladder" (strikes spread across different expiries/levels) from being reported as a concentrated squeeze/cascade signal.

Exposed in output as `squeeze_dispersion`, `cascade_dispersion`, and `_vol_ladder_suppressed`.

### 8.5 Ticker state output object

```
{
  ticker,
  squeeze_state,           // 'ACTIVE' | 'BUILDING' | 'NONE'
  cascade_state,           // 'ACTIVE' | 'BUILDING' | 'NONE'
  contributing_flows,      // count of all structural (squeeze + cascade) flows
  squeeze_flow_count,
  cascade_flow_count,
  top_relevance_score,     // highest structural_relevance_score across all contributors
  explanation,             // explanation string of the top-scoring flow
  squeeze_dispersion,      // float, 4 decimal places
  cascade_dispersion,
  _vol_ladder_suppressed,  // bool
  _gex_regime,
  _gex_spot,
  _gex_flip
}
```

---

## 9. Public API

```javascript
StructuralEngine.analyze(flowEvent, gexSnapshot)        // single flow → enriched result
StructuralEngine.analyzeBatch(flowEvents, gexSnapshot)  // array → aggregate then analyze each
StructuralEngine.aggregateFlows(flowEvents)             // dedupe/merge near-duplicate flows
StructuralEngine.getTickerState(flowEvents, gexSnapshot) // build ticker-level state summary
```

Internal helpers exposed under `StructuralEngine._test` for unit testing: `computeDistances`, `computeProximityFlags`, `determineFlowIntent`, `detectUpsideSqueeze`, `detectDownsideCascade`, `computeRelevanceScore`, `normalizeExecType`.

---

## 10. What Is Server-Side / Not in This File

The following are explicitly NOT present in `structural-engine.js` and must be server-side or in other modules:

- **GEX snapshot generation** — `gamma_flip`, `call_wall`, `put_support`, `net_gex`, `regime`, `gamma_flip_dislocated` are all consumed as pre-computed inputs; no GEX computation logic exists here.
- **Flow normalization / "Flow Engine"** — the comment says "normalized flow object from the Flow Engine"; the engine that produces `conviction_score`, `classification`, `execLabel`, `alertRule` etc. is external.
- **Conviction score computation** — `flow.score` / `flow.conviction_score` is read but never computed here.
- **Classification logic** — what makes a flow `'HEDGE'` vs `'LIKELY HEDGE'` vs directional is upstream.
- **Historical state / persistence** — engine is entirely stateless; the "terminal" that orchestrates repeated calls and stores ticker-state history is external.
- **Regime determination** — the `regime` string (`CASCADE`/`TRANSITION`/`TREND`) is assigned externally before this engine sees the GEX snapshot.
- **`gamma_flip_dislocated` flag** — computed upstream; used here as a boolean guard only.

---

## 11. Numerical Constants Summary

| Constant | Value | Meaning |
|---|---|---|
| `FLIP_PROXIMITY` | 0.01 (1%) | Spot/strike within 1% of gamma flip |
| `WALL_PROXIMITY` | 0.02 (2%) | Spot/strike within 2% of call wall or put support |
| Min conviction score | 55 | Gate for both SQUEEZE and CASCADE detection |
| Min size/OI (standard) | 0.20 | Standard size gate |
| Min size/OI (large-premium bypass) | 0.10 | Used when premium >= $1M |
| Large-premium bypass threshold | $1,000,000 | Halves size requirement |
| Contrarian intent: min size/OI | 0.25 | For call-at-bid bearish / put-at-bid bullish medium confidence |
| Contrarian intent: min premium | $250,000 | Paired with above |
| Above-flip max distance (SQUEEZE) | 0.005 (0.5%) | Rejects squeeze if spot >0.5% above flip |
| Aggregation dedup window | 2,000 ms | 2-second window for near-duplicate merging |
| Clustering window | 1,200,000 ms | 20-minute window for ticker state clustering |
| Vol-ladder threshold | 0.02 (2%) | Strike dispersion that demotes ACTIVE to BUILDING |
| BUILDING single-flow min score | 70 | Min top-score for 2-flow BUILDING state |
| ACTIVE cluster count | 6 | Unconditional ACTIVE threshold |
| ACTIVE cluster count (high score) | 4 + topScore > 80 | ACTIVE with score gate |
| BUILDING cluster count | 4 | Unconditional BUILDING threshold |
