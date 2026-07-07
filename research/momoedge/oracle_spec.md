# MomoEdge Oracle Engine — Competitive Feature Study Spec

> **Source files read:** `js/engines/oracle-engine.js` (2314 lines), `js/modules/signals.js` (1573 lines), `js/modules/analysis.js` (407 lines), `js/modules/trade-glance.js` (386 lines), `js/modules/performance.js` (1574 lines).
> All identifiers, weights, thresholds, and formulas are quoted verbatim from the client-side JavaScript.

---

## 1. Architecture: Client vs. Server Split

### Server-side (NOT in these JS files)

- **Signal creation**: The `public.signals` Supabase table is populated entirely server-side. The JS only **reads** rows via `db.select('signals', query)`. There is no client-side code that creates base signal rows (asset, thesis, entry zone, targets, invalidation, horizon, etc.). The picker that originates signals is an upstream server process.
- **Admin-gated writes via Netlify function**: All writes from the client are routed through `/.netlify/functions/oracle-write` (comment: "Hardening Plan B1b prerequisite (2026-05-30)"). This function verifies JWT server-side, checks `is_admin` via `public.trader_profiles`, and uses service-role credentials. Non-admins receive HTTP 403. Actions routed through this endpoint: `advance-tranche`, `log-flow-signal`, `enrich-flow-signal`, `dedup-flow-signal`.
- **Price batch and price fetching**: Option prices and spot prices come from `/.netlify/functions/price-batch` and `/.netlify/functions/price` (Polygon/Massive backend).
- **MACD/technical data**: `cfg.TECHNICAL_API + '?symbol=' + ticker` — a separate Netlify/API endpoint.
- **Oracle stance**: `oracle_stance` field on `public.app_settings`, read via `db.rpc('get_public_app_settings')`. Set server-side only.
- **Performance records**: `public.performance` table; written by admin via `db.upsert('performance', row)`. The JS can write performance rows if admin-authed.

### Client-side (in these JS files)

- All live confidence calculations (V1 and V2).
- Signal rendering, list sorting, card building.
- Flow signal auto-logging gate logic (admin-only, 7-gate filter).
- Trigger state stamping and auto-tranche advancement (UI-side; DB write admin-gated).
- Option P&L live rendering via OCC symbol lookup.
- Performance stats, equity curve, period breakdown, trade detail modal.

---

## 2. Signal Object Schema

Signals are rows from `public.signals`, fetched with:
```
or=(is_active.eq.true,and(is_active.eq.false,closed_at.gte.<today_start>))&order=sort_order.asc
```

**Fields observed in code** (all string unless noted):

| Field | Type | Notes |
|---|---|---|
| `id` | UUID | Primary key |
| `asset` | string | Ticker, possibly with suffix (e.g. "NVDA 2x") |
| `direction` | string | `"BULL"` or `"BEAR"` |
| `thesis` | string | Full thesis text (typewriter-revealed in UI) |
| `trigger` | string | Free-text containing price, e.g. "above $910" — first number parsed |
| `entry_price` | string/number | Numeric string; parsed as `parseFloat` |
| `targets` | string | Free-text, e.g. "T1=$950, T2=$980, T3=$1050" — regex parsed |
| `invalidation` | string | Free-text, e.g. "below $870" — first number parsed |
| `horizon` | string | Free-text, e.g. "3-6 months", "2 weeks" — parsed to days |
| `min_duration` | string | Free-text, e.g. "14d", "3w" — parsed to days |
| `signal_date` | ISO timestamp | Issuance date |
| `confidence` | number | Base confidence score (0-100); stored in DB |
| `level` | string | Label shown in card header |
| `stream_label` | string | Display label (becomes `streamLabel` on JS object) |
| `sort_order` | integer | Card list ordering |
| `is_active` | boolean | `true` = open, `false` = closed today |
| `closed_at` | ISO timestamp | Present on recently-closed signals |
| `oracle_tranche` | integer | 1 = initial, 2 = trigger confirmed |
| `tranche_2_date` | ISO timestamp | When tranche advanced to 2 |
| `option_contracts` | JSON string | Array of option contract objects (see §4) |
| `option_symbol` | string | Pre-computed OCC symbol override |
| `option_price` | number | Legacy: single premium value |
| `flow_snapshot` | object | Attached flow trade snapshot |
| `directive` | string | Used in terminal template context |
| `bias` | string | Used in terminal template context |
| `close_price` | number | Price at close (for frozen P&L) |
| `closed_pnl_pct` | number | Frozen P&L percentage on closed signals |
| `stop_pips` / `target_pips` | number | Forex pip-based R:R (optional) |
| `target_pips` | number | For sidebar R:R display on forex |

**Performance table fields** (from `loadPerf` and `openTradeDetail`):

| Field | Notes |
|---|---|
| `result` | Float — % return of the stock-side move |
| `days` | Integer — days to outcome |
| `status` | `"ACTIVE"`, `"T1_HIT"`, `"T2_HIT"`, `"INVALIDATED"`, `"CLOSE_BEFORE_T1"`, `"CLOSED_EARLY"`, `"EXPIRED"` |
| `entry_price`, `exit_price` | Floats |
| `date` | Issue date string `MM-DD-YYYY` |
| `exit_date` | Close date string |
| `conf` | Base confidence at issuance |
| `direction` | `"BULL"` / `"BEAR"` |
| `vehicle` | `"STOCK"` / `"OPTIONS"` |
| `opt_strike`, `opt_type`, `opt_expiry` | Option contract details |
| `opt_prem_entry`, `opt_prem_exit` | Premium paid/received at open/close |
| `opt_contracts` | Contract count |
| `spy_return` | SPY return over same period |
| `aftermath_1d`, `aftermath_3d`, `aftermath_1w`, `aftermath_1m`, `aftermath_3m` | Post-close price tracking |
| `type`, `signal` | Signal type label |
| `notes` | Trade notes |

---

## 3. Confidence Model V1 (9-Factor, additive delta on base)

`calculateLiveConfidence(sig)` — falls through to V2 immediately if `window.computeOracleLiveConfidenceV2` is defined (which it always is). V1 is kept for backward-compat; in practice V2 is the live path.

### V1 Factor Definitions

All factors are **delta adjustments on `baseConf`** (the stored `confidence` field, typically 50-80).

**F1 — Trigger Confirmation** (one-time step-change)
```js
if (triggerHit) {
  F1_trigger = 7;  // base bonus
  // clean-break bonus: up to +2 extra based on (pastTrigger / distToT1) * 10, capped at 2
  F1_trigger += Math.min(2, (pastTrigger / distToT1) * 10);
} else if (progressToT1 < 0.05 && daysElapsed > 5) {
  F1_trigger = -Math.min(4, (daysElapsed - 5) * 0.25);  // −0.25/day penalty
}
```
Range: −4 to +9

**F2 — Price Zone Adjustment** (non-linear zone curves)

| Zone | Formula |
|---|---|
| `stopBreached` | `-(baseConf - 12)` — collapses toward floor |
| `danger` (ddPct 66-100%) | `t = (ddPct-0.66)/0.34; -22 - Math.pow(t,1.5) * 30` (−22 to −52) |
| `drawdown` (33-66%) | `t = (ddPct-0.33)/0.33; -8 - t*14` (−8 to −22) |
| `drawdown_mild` (0-33%) | `-(ddPct/0.33)*8` (0 to −8) |
| `t3_hit` | +9 |
| `t2_hit` | `6 + t3Prog*2` (6 to +8) |
| `t1_hit` | `3 + t2Prog*3` (3 to +6) |
| `winning` (0 < p < T1) | `Math.pow(Math.min(1,progressToT1), 0.75) * 10` (0 to +10) |

**F3 — Velocity Amplifier** (applied to positive F2 only)
```js
velocityMultiplier = Math.max(0.8, Math.min(1.5, rawVel));
// rawVel = (progressToT1/expectedProgress); expectedProgress = min(daysElapsed/horizonDays, 1)
amplifiedF2 = F2_price > 0 ? F2_price * velocityMultiplier : F2_price;
```
Multiplier range: 0.8x to 1.5x

**F4 — Horizon-Aware Time Decay** (subtracted; suppressed when making progress)
```js
baseRate = 0.16;
horizonScale = Math.min(2.5, Math.max(0.3, 30 / Math.sqrt(horizonDays)));
dailyRate = baseRate * horizonScale;
suppression = Math.min(1, Math.max(0, progressToT1) / 0.15);
effectiveRate = dailyRate * (1 - suppression);
F4_decay = Math.min(15, daysElapsed * effectiveRate);
// Zone multipliers: danger 1.5×, drawdown 1.3×, drawdown_mild 1.1×
// Hard cap: 18
```
Range: 0 to −18

**F5 — Post-Target Decay** (holding past T1 without closing)
```js
// After 3-day grace period post T1:
// Days 4-14: -0.4/day
// Day 15+: -0.7/day additional
F5_postTarget = Math.max(-15, ...);
// Suppressed proportionally when approaching T2: *=(1 - toT2*0.8)
```
Range: 0 to −15

**F6 — Momentum Pulse** (today's session daily % change; aligned vs. direction)
```js
if (Math.abs(dailyChgPct) > 0.3) {
  alignedMove = isBull ? dailyChgPct : -dailyChgPct;
  F6_momentum = Math.sign(alignedMove) * Math.min(2, Math.pow(Math.abs(alignedMove)*0.5, 0.75));
  // amplified 1.3× in danger/drawdown zones when opposing
}
// Clamped: -2.5 to +2
```

**F7 — Recovery Scar** (subtracted from amplifiedF2 to prevent instant confidence recovery)
```js
if (progressToT1 >= 0 && daysElapsed > 4 && amplifiedF2 > 0) {
  scarFactor = Math.min(0.25, daysElapsed * 0.007);
  F7_scar = amplifiedF2 * scarFactor;  // up to 25% of F2 subtracted
}
```

**F8 — Macro Regime Alignment**
```js
// window._lastStance: 'bull' | 'bear' | 'neutral' (from oracle_stance DB setting)
if aligned: F8_regime = +2
if opposed: F8_regime = -4
```

**F9 — Futures / Macro Overlay** (SPY + QQQ daily % change; non-forex only; market hours only)
```js
avgFutChg = (spyChg + qqqChg) / count;
alignedFut = isBull ? avgFutChg : -avgFutChg;
if alignedFut < 0: F9_futures = Math.max(-10, alignedFut * 2.5)  // up to -10, ×1.4 in danger zones
if alignedFut > 0: F9_futures = Math.min(2, alignedFut * 0.8)    // reduced tailwind
```

### V1 Combination and Bounds

```js
raw = baseConf + F1_trigger + amplifiedF2 - F7_scar - F4_decay + F5_postTarget + F6_momentum + F8_regime + F9_futures;

HARD_CEILING = window.MomoEdge.config.CONFIDENCE_CEILING  // ~92 (config constant)

// Zone-specific floor/ceiling:
stopBreached:   floor=10,   ceiling=18
danger:         floor=max(14, baseConf-55),  ceiling=min(CAP, max(floor+5, baseConf-18))
drawdown:       floor=max(22, baseConf-40),  ceiling=min(CAP, max(floor+5, baseConf-3))
drawdown_mild:  floor=max(35, baseConf-22),  ceiling=min(CAP, baseConf+3)
normal:         floor=max(30, baseConf-28),  ceiling=min(CAP, baseConf+8)

liveConf = clamp(raw, floor, ceiling)
delta    = liveConf - baseConf
```

**Return object** (V1-path, rarely used since V2 short-circuits):
`{ conf, delta, zone, t1Hit, t2Hit, t3Hit, triggerHit, velocityMultiplier, direction, price, ddPct, progressToT1, F1, F2, F3, F4, F5, F6, F9 }`

---

## 4. Confidence Model V2 (Phase-Aware Weighted Scoring)

`computeOracleLiveConfidenceV2(sig)` — this is the **live path**. V1 immediately delegates to it.

### V2 Step 1: Live State Memory (in-memory per signal session)

```js
window.MomoEdge.signalLiveState[signalId] = {
  first_trigger_ts: null,   // timestamp of first trigger entry
  first_t1_ts: null,        // timestamp of first T1 hit
  first_t2_ts: null,
  first_t3_ts: null,
  mfe: 0,                   // max favorable excursion (in price terms, direction-adjusted)
  mae: 0,                   // max adverse excursion
  prev_live_conf: null,
  prev_raw_conf: null,
  prev_display_conf: null,
  last_phase: null,
  bars_since_trigger: 0,
  bars_since_t1: 0,
  max_progress_to_t1: 0
}
```
State is NOT persisted to Supabase — resets on page reload.

### V2 Step 2: Geometry (computed each tick)

```js
dir = signal.direction === 'BULL' ? 1 : -1
move = dir * (price - entry)       // positive = favorable
distFromStop = dir * (price - inval)
p1 = move / d1  (d1 = |t1 - entry|)
p2 = move / d2  (d2 = |t2 - entry|)
p3 = move / d3  (d3 = |t3 - entry|)
risk = |entry - inval|  (or |t1-entry| if no invalidation)
moveR = move / risk
distToStopR = distFromStop / risk
distToT1R = (d1 - max(0, move)) / risk
distToT2R = (d2 - max(0, move)) / risk  (null if no T2)
```

### V2 Step 3: Phase Detection

Phases (in priority order):
1. **`invalidated`** — `distFromStop <= 0`
2. **`overtime`** — `tau > 1.0 AND first_t1_ts == null` (horizon exceeded, T1 never hit)
3. **`post_t2`** — `first_t2_ts AND p2 >= 1.0`
4. **`post_t1_failed_hold`** — `first_t1_ts AND p1 < 0.50` (T1 hit but gave back >50%)
5. **`post_t1_pre_t2`** — `first_t1_ts AND p1 >= 0.50` (or simply T1 was hit)
6. **`triggered_pre_t1`** — price has entered trigger zone or trigger was previously hit
7. **`pre_trigger`** — default

`tau = daysElapsed / horizonDays` (0 to ∞)

### V2 Step 4: Phase-Aware Weights

```js
PHASE_WEIGHTS = {
  pre_trigger:         { base:0.28, trigger:0.18, validity:0.26, objective:0.10, pace:0.12, retention:0.00, overlay:0.06 },
  triggered_pre_t1:   { base:0.10, trigger:0.10, validity:0.24, objective:0.28, pace:0.22, retention:0.00, overlay:0.06 },
  post_t1_pre_t2:     { base:0.08, trigger:0.04, validity:0.18, objective:0.26, pace:0.16, retention:0.22, overlay:0.06 },
  post_t1_failed_hold:{ base:0.10, trigger:0.02, validity:0.22, objective:0.20, pace:0.14, retention:0.26, overlay:0.06 },
  post_t2:            { base:0.04, trigger:0.00, validity:0.14, objective:0.20, pace:0.10, retention:0.38, overlay:0.14 },
  overtime:           { base:0.16, trigger:0.04, validity:0.32, objective:0.14, pace:0.28, retention:0.00, overlay:0.06 },
  invalidated:        { base:0.00, trigger:0.00, validity:1.00, objective:0.00, pace:0.00, retention:0.00, overlay:0.00 }
}
```
Weights sum to 1.00 for each phase.

### V2 Step 5: Component Scores (all normalized 0-1)

**Validity** — how far from stop (steeper near danger zone):
```js
ratio = clamp(distFromStop / risk, 0, 1)
if ratio > 0.25: validity = Math.pow(ratio, 1.35)
else (danger zone): validity = baseDanger * Math.pow(dangerRatio, 2.2)
// where baseDanger = Math.pow(0.25, 1.35) ≈ 0.146
```

**Objective / Progress**:
```js
// Before T1: steeper curve
if p1 < 1: objective = 0.68 * Math.pow(clamp(p1,0,1), 0.75)
// At T1 (no T2): 0.35-0.65 minus giveback penalty
// T1→T2 leg: 0.40-0.90 based on leg progress
// T2 hit: 0.60-1.00
```
Giveback penalty: `if givebackFrac > 0.4: penalty = (givebackFrac-0.4)*0.3`

**Pace** — progress vs. expected schedule:
```js
// Horizon-length schedule:
if horizonDays < 14:  t1ExpectedBy=0.45, t2ExpectedBy=0.80
if horizonDays < 60:  t1ExpectedBy=0.55, t2ExpectedBy=0.90
else:                 t1ExpectedBy=0.65, t2ExpectedBy=0.95

expectedT1 = smoothstep(0.05, t1ExpectedBy, tau)
paceT1 = clamp(1 - max(0, expectedT1 - clamp(p1,0,1)), 0, 1.0)
// Before T1: pace = 0.80*paceT1 + 0.20*paceT2
// After T1:  pace = 0.40*paceT1 + 0.60*paceT2
// Overtime: max(0, 0.3 - shortfall*0.6)
```

**Retention** — how much of MFE is retained:
```js
retained = clamp(move / mfe, 0, 1)
// post_t1_failed_hold amplification:
if p1 < 0.50: ampFactor = 1.6
if p1 < 0.70: ampFactor = 1.3
// pre_trigger / triggered_pre_t1: returns 0.5 (neutral)
```

**Trigger Zone Score** (continuous, not binary):
```js
if price past triggerPrice:
  depthFrac = clamp(pastTrigger / (d1 * 0.15), 0, 1)
  score = 0.65 + 0.23 * depthFrac  // 0.65 to 0.88
else (approaching):
  approachFrac = clamp(1 - (distToTrigger / d1), 0, 1)
  score = 0.40 + 0.15 * approachFrac  // 0.40 to 0.55
// No trigger defined: 0.5
```

**Overlay** (macro + market conditions composite):
```js
overlay = 0.5  // baseline
// Trigger confirmed: +0.06
// Momentum pulse: ±0.03 (aligned daily move)
// Macro regime aligned: +0.08; opposed: -0.20
// Futures (SPY+QQQ avg):
//   adverse: max(-0.14, alignedFut * 0.04)
//   tailwind: min(0.05, alignedFut * 0.015)
overlay = clamp(overlay, 0, 1)
```

**Path Quality Penalty**:
```js
maeFrac = clamp(mae / risk, 0, 1.25)
if move > 0: penalty = 4 * Math.pow(maeFrac, 1.2)
// Deep recovery extra: +3 * clamp((mae/risk - 0.8)/0.2, 0, 1) if mae/risk > 0.8
pathPenalty = penalty / 100  // normalized for subtraction from raw01
```

### V2 Step 6: Weighted Sum and Bounds

```js
raw01 = w.base*baseNorm + w.trigger*triggerScore + w.validity*validity +
        w.objective*objective + w.pace*pace + w.retention*retention + w.overlay*overlay
rawScore = (raw01 - pathPenalty) * 100
```

**Phase-Aware Bounds** (CAP = `window.MomoEdge.config.CONFIDENCE_CEILING`, ~92):

| Phase | Floor | Ceiling |
|---|---|---|
| `invalidated` | 8 | 16 |
| `pre_trigger` | max(25, base−30) | min(CAP, base+8) |
| `triggered_pre_t1` | max(22, base−36) | min(CAP, max(base+16, 82)); +4 if p1>0.85, +2 if p1>0.65 |
| `post_t1_pre_t2` (no T2) | max(52, base−10) | min(CAP, base+10) |
| `post_t1_pre_t2` (has T2) | max(36, base−20) | min(CAP, max(base+18, 86)); +2 if p2>0.5 |
| `post_t2` | max(48, base−10) | CAP |
| `post_t1_failed_hold` | max(28, base−28) | min(82, base+4) − phase-deductions by p1 level |
| `overtime` (p1<0.3) | max(20, base−40) | min(CAP, max(35, base−20)) |
| `overtime` (p1 0.3-0.6) | max(20, base−40) | min(CAP, max(42, base−14)) |
| `overtime` (p1>0.6) | max(20, base−40) | min(CAP, max(50, base−8)) |

Additional guard: if `tau > 1 AND p1 < 0.75`: `ceiling = min(ceiling, max(45, base-12))`

Pre-trigger stall guard: if `tau > 0.3 AND p1 < 0.05`: `ceiling = min(ceiling, max(50, base-8))`

**EMA Smoothing** (display confidence):
```js
if (phase changed from last tick): alpha = 0.85  // fast response to phase transitions
else:                              alpha = 0.45  // gradual
displayConf = (1-alpha)*prevDisplay + alpha*rawLiveConf
// Frozen if |rawLiveConf - prevRaw| < 0.03
```

### V2 Return Object

```js
{
  liveConf,          // rounded to 1dp — display value (EMA smoothed)
  rawLiveConf,       // rounded to 1dp — deterministic before smoothing
  baseConf,          // stored DB confidence
  delta,             // liveConf - baseConf (signed)
  phase,             // one of 7 phase strings
  state,             // human-readable: "Awaiting Trigger", "Advancing Cleanly", etc.
  triggerZoneScore,  // 0-100 (integer)
  p1, p2, p3,        // progress to T1/T2/T3 (float, can exceed 1.0)
  validity,          // 0-100
  objective,         // 0-100
  pace,              // 0-100
  retention,         // 0-100
  overlayScore,      // 0-100
  distToStopR,       // R-units to stop
  distToT1R,         // R-units to T1
  distToT2R,         // R-units to T2 (null if no T2)
  distToT3R,         // R-units to T3 (null if no T3)
  moveR,             // current move in R units
  mfeR, maeR,        // max favorable/adverse in R units
  tau,               // horizon fraction used (0-100)
  targetHits: { t1, t2, t3 },  // booleans
  hasT2, hasT3,
  changeReason,      // string or null (score change reason engine output)
  // V1-compat aliases:
  conf,              // = liveConf
  zone,              // V1 zone string mapped from phase
  t1Hit, t2Hit, t3Hit,
  triggerHit,
  direction,         // "up" | "down"
  price,
  ddPct,
  progressToT1,
  velocityMultiplier  // always 1 in V2
}
```

### V2 Diagnostics (rendered as component bars)

Five bars shown in `#v2Bars` panel:

1. **VALIDITY** — `validity` (0-100); color: ≥70 core-blue, ≥40 amber, else red
2. **PROGRESS** — live price progress % to T1
3. **PACE** — `pace` (0-100)
4. **RETENTION** — `retention` (0-100); hidden in `pre_trigger` and `triggered_pre_t1` phases
5. **OVERLAY** — `overlayScore` (0-100)

Tooltip text for each bar:
- Validity: "X.XR from stop — well protected / moderate safety / approaching danger / Dangerously close to stop level"
- Progress: "X% toward T1" / "T1 hit — X% toward T2" / "T1 target achieved"
- Pace: "Ahead/On/Behind/Significantly behind pace — X% of horizon used"
- Retention: "Holding/Retaining/Given back/Most gains surrendered"
- Overlay: "Macro and market conditions supportive/Neutral/creating headwind"

**Score Change Reason** (shown when `|delta| > 2`):
```js
// Phase transitions: "Trigger Confirmed", "T1 Target Hit", "T2 Target Hit", "Overtime — Horizon Exceeded", "Stop Level Breached"
// Component deltas (threshold 5-8 pts): "Nearing Invalidation", "Moving Away from Stop",
//   "Falling Behind Schedule", "Ahead of Schedule", "Giving Back Gains", "Extending Gains",
//   "Macro Headwind", "Macro Tailwind"
// Fallback: "Improving" | "Weakening"
```

**Geo rows** (`#v2GeoRows`):
- `STOP LOSS: X.XR away` — red if <0.5R, amber if <1.0R
- `T1 TARGET: X.XR away` (hidden once T1 hit)
- `T2 TARGET: X.XR away` (shown if hasT2 and T2 not hit)
- `HORIZON: X% used` — red if >100%, amber if >70%

---

## 5. T2 Gating — The SOFI Pattern

**T2 is only shown in the TradeGlance panel if it is present in `sig.targets`**. The JS parses targets via regex:
```js
t2m = sig.targets.match(/T2\s*[=:]\s*([\d,]+\.?\d*)/i)
```

If T1 is missing but T2 is present, T2 is promoted as the primary target:
```js
// In parseTargets (V2):
if (!t1 && t2) { t1 = t2; t2 = t3; t3 = null; }
```

In `hasT2` geometry: `hasT2 = targets[1] != null && targets[1] !== targets[0]`

**T2 target in UI** (`trade-glance.js`): `$t2Val.textContent = fmtPrice(t2, ticker)` — if `t2 == null`, shows "N/A". The T2 cell progress bar is blank until price reaches T1 territory. The TradeGlance widget shows T2 value/meta only if `tgs.t2` is non-null. There is no explicit "T2 locked until T1 hit" toggle — T2 is simply shown as its price, and shows "✓ HIT" only when price crosses it. The V2 engine produces `distToT2R` as null if `hasT2` is false, and the geo rows suppress T2 if `!v2.hasT2`.

---

## 6. Oracle Option Recommendation

Stored as `option_contracts` JSON array on the signal row (server-written). Structure:
```js
// sig.option_contracts is a JSON string, parsed to array:
[
  {
    type: "CALL" | "PUT",   // defaults to direction-based if missing
    strike: number,          // e.g. 910
    expiry: "YYYY-MM-DD",
    premium: number          // entry premium paid, per share (×100 = contract value)
    // (implied: contracts count stored separately if needed)
  }
]
```

Display fields rendered in the `oracleOptionCard`:
- **TYPE** badge (CALL/PUT, color-coded green/red)
- **EXP** — formatted `Mon DD` (e.g. "Mar 28")
- **PREM** — `$X.XX` (amber color)
- **STRIKE** — `$XXX` (core-blue color)
- **NOW** live price — fetched via OCC symbol lookup to `/.netlify/functions/price-batch`

OCC symbol construction:
```js
sym = ticker + YYMMDD + C/P + XXXXXXXX
// XXXXXXXX = Math.round(strike * 1000).padStart(8, '0')
// e.g. SOFI260320C00012000 for SOFI $12 call expiring 2026-03-20
```

Live P&L display:
```js
pnl = isSold ? -rawPct : rawPct
rawPct = ((currentPrice - entryPrem) / entryPrem) * 100
// Rendered: "NOW $X.XX +XX.X%" (color-coded)
```

`isSold` determined by: `sig.flow_snapshot.tradeDir === 'Sold'`

If `sig.option_symbol` is pre-set server-side, it overrides the computed OCC symbol.

---

## 7. Phase Map and Human States

| Phase | Human State (examples) | Zone mapping |
|---|---|---|
| `pre_trigger` | "Awaiting Trigger" / "Approaching Trigger" | `base` or `drawdown_mild` |
| `triggered_pre_t1` | "Advancing Cleanly" / "On Track" / "Needs Follow-Through" / "Stalling" | `winning`, `approaching_t1`, or `base` |
| `post_t1_pre_t2` | "Advancing to T2" / "T1 Hit — Holding" / "Target Achieved" / "Giveback Warning" | `t1_hit` |
| `post_t1_failed_hold` | (no explicit human state; maps to `drawdown` zone) | `drawdown` |
| `post_t2` | "High Conviction" / "Extended — Watch Giveback" | `t2_hit` |
| `overtime` | "Overtime Stall" | `drawdown` |
| `invalidated` | "Invalidated" | `invalidated` |

Phase label shown in UI (`phaseMap` in `setRightPanel`):
```js
pre_trigger → "PRE TRIGGER"
triggered_pre_t1 → "IN TRIGGER ZONE" or "DEEP IN TRIGGER ZONE" (if triggerZoneScore > 75)
post_t1_pre_t2 → "T1 HIT"
post_t2 → "T2 HIT"
overtime → "OVERTIME"
invalidated → "INVALIDATED"
```

---

## 8. Duration / Hold Status System

Parsed from `sig.min_duration` (free-text: "14d", "3w", "2m", "21 days", etc.):

```js
durationStatus(elapsed, minDays, t1Hit):
  if t1Hit: return 'eligible'        // T1 reached → always eligible regardless of time
  if n/minDays >= 1: return 'eligible'
  if n/minDays >= 0.75: return 'watch'  // within 25% of min hold
  return 'hold'
```

Status display colors: hold=core-blue, watch=amber, eligible=green, nomin=muted.

---

## 9. Oracle Tranche System

`oracle_tranche` field on signal:
- **1** = initial (waiting for trigger)
- **2** = trigger confirmed (advances automatically client-side when trigger is hit)

Auto-advance logic (in `applyTriggerStates`):
```js
if (isHit && sig.oracle_tranche === 1 && sig.id && !_triggerAdvanced.has(sig.id)) {
  _triggerAdvanced.add(sig.id);
  sig.oracle_tranche = 2;
  sig.tranche_2_date = new Date().toISOString();
  // Admin-gated DB write via oracle-write endpoint
  _oracleAdminWrite('advance-tranche', { signal_id, oracle_tranche: 2, tranche_2_date });
  // Fires "Hold full position" alert if oracle_full_position pref is ON (default ON)
}
```

---

## 10. Flow Signal Auto-Logging (Server-Side Gate)

Admin-only. 7 gates applied before logging a flow trade to `public.flow_signals`:

1. **Score gate**: `displayedScore >= 68` (uses `score_v2` if available, else `score`)
2. **Premium gate**: `prem >= cfg.PREMIUM_STANDARD` (reduced to `cfg.PREMIUM_CLUSTER` for RepeatedHits/AscendingFill pattern)
3. **Size/OI ratio**: `sizeOi >= 0.15`
4. **Ticker exclusion**: not in `['SPX','SPXW','SPY','QQQ','IWM','RUT','NDX','VIX','DJX']`
5. **Not hedge**: `classification !== 'HEDGE' && !== 'LIKELY HEDGE'`
6. **Not spread**: `!spreadType`
7. **DTE**: `dte >= 5`

Dedup: in-memory `ticker:strike:expiry:type` key + Supabase DB check for existing OPEN signal. If exists, calls `updateFlowSignal` (increments premium + trade_count).

Flow signal row schema stored in `public.flow_signals`:
```
ticker, type, score, score_v2, score_v2_macd, score_v3_1, death_watch_gate, score_v4,
bull_premium_share_14d, signal_count_7d, score_v5, market_tape_used, whale_gate,
premium, pattern, intent, fill_type, execution_type, size, open_interest, volume, dte,
moneyness, strike, expiry, option_symbol, spot_at_signal, option_price_at_signal,
iv_at_signal, relative_premium_score, size_oi_ratio, size_vol_ratio, trade_count,
flow_snapshot (JSON), status='OPEN'
```

---

## 11. Performance Engine

### Closed Signal Outcome Categories

- `T1_HIT` — T1 target reached
- `T2_HIT` — T2 target reached
- `T3_HIT` — T3 target reached
- `INVALIDATED` — stop breached
- `CLOSE_BEFORE_T1` / `CLOSED_EARLY` — closed before T1
- `EXPIRED` — horizon elapsed without outcome

### Stats Computed Client-Side

From `computeStats()`:
- Win rate, avg gain, avg loss, avg days to target
- Total alpha (sum of all `result` %)
- Bull win rate, bear win rate
- Max drawdown (worst consecutive loss run)
- Best win streak
- Best/worst individual trade

### Equity Curve

Cumulative sum of `result` values, sorted by `exit_date` (falls back to `date`). SVG with grid lines, gradient fill, interactive dots (hover tooltip: asset, result %, date, days).

### Period Breakdown

Groups closed trades by month/quarter/year with per-period stats: trades, win rate, total %, avg %, avg days. Expandable rows show individual trades. All-time footer row.

### Options Trade P&L in Detail Modal

```js
optPnlPct = (opt_prem_exit - opt_prem_entry) / opt_prem_entry * 100
optPnlDollar = (opt_prem_exit - opt_prem_entry) * 100 * opt_contracts
leverageMultiple = |optPnlPct| / |stockResult|
```
Leverage callout shown when `leverage > 1`.

---

## 12. Macro Regime (Oracle Stance)

`window._lastStance` = `'bull' | 'bear' | 'neutral'`

Loaded from `public.app_settings.oracle_stance` (server-written by admin). Used in both V1 (F8) and V2 (overlay). Cached in `localStorage['oracle_stance']` for offline fallback.

Applied via `applyStance(stance)` which updates CSS classes on `#coreWrap` and sets `--mo-color` CSS variables on the four mini-oracle tabs (Analysis, Macro, Flow, History).

---

## 13. Risk/Reward Calculator (Static, at Signal Issuance Price)

```js
entry, t1, inval parsed from sig.entry_price, sig.targets, sig.invalidation
reward = isBull ? t1 - entry : entry - t1
risk   = isBull ? entry - inval : inval - entry
rr = reward / risk
```

Grade thresholds:
- ≥4.0 → EXCEPTIONAL (gold `#ffd700`)
- ≥3.0 → EXCELLENT (`#00ffaa`)
- ≥2.0 → FAVORABLE (green)
- ≥1.0 → ACCEPTABLE (core)
- ≥0.5 → UNFAVORABLE (amber)
- <0.5 → POOR (red)

---

## 14. Zone Colors and Pulse Animations

```js
ZONE_CONFIG = {
  'base':           { color:'var(--core)',  label:'MONITORING',          pulse:'normal' },
  'drawdown_mild':  { color:'var(--amber)', label:'⚠ MILD DRAWDOWN',     pulse:'normal' },
  'winning':        { color:'var(--green)', label:'IN PROFIT ▲',         pulse:'normal' },
  'approaching_t1': { color:'#00ffaa',     label:'APPROACHING T1 ◆',    pulse:'fast'   },
  't1_hit':         { color:'#00ffcc',     label:'◉ T1 HIT',            pulse:'fast'   },
  't2_hit':         { color:'#ffe066',     label:'◉ T2 HIT',            pulse:'fast'   },
  't3_hit':         { color:'#ff9900',     label:'◉ T3 HIT',            pulse:'fast'   },
  'drawdown':       { color:'#ff9944',     label:'⚠ DRAWDOWN',          pulse:'slow'   },
  'danger':         { color:'var(--red)',  label:'✕ NEAR STOP',          pulse:'urgent' },
  'invalidated':    { color:'#ff2244',     label:'✕ INVALIDATED',        pulse:'urgent' },
}
```

Confidence arc is an SVG `<circle>` with `strokeDashoffset = 141.4 * (1 - liveConf/100)`.

---

## 15. Card Sort Modes

Three modes cycled via button: `new` (by `signal_date` desc), `best` (by live P&L desc), `conviction` (by `calculateLiveConfidence(sig).conf` desc).

---

## 16. Key Config Constants (not directly in these files but referenced)

- `window.MomoEdge.config.CONFIDENCE_CEILING` — hard ceiling (~92)
- `window.MomoEdge.config.PREMIUM_STANDARD` — flow signal standard premium gate
- `window.MomoEdge.config.PREMIUM_CLUSTER` — reduced premium gate for cluster patterns
- `window.MomoEdge.config.DEDUP_WINDOW_MS` — flow signal dedup window (ms)
- `window.MomoEdge.config.MARKET_OPEN_MINS`, `MARKET_CLOSE_MINS` — ET market hours in minutes
- `window.MomoEdge.config.isForex(asset)` — forex detection for F9 suppression
- `window.MomoEdge.config.getSignalPnl(sig, livePrice)` — normalized P&L (handles forex pips)
