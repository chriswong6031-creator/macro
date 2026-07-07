# GEX Terminal — UI Spec (Competitive Reference)

Extracted from `/tmp/momoedge_src/gex.html` + `/tmp/momoedge_src/js/gex-init.js` + `/tmp/momoedge_src/gex-engine.js`.
All identifiers, class names, and threshold values are quoted verbatim from source.

---

## 1. Page Identity and Theme

- Page title: `"MOMOEDGE — GEX Terminal"`
- Standalone mode (own tab): full-page layout, particle field, hex-grid overlay, radial glow backgrounds, corner-bracket chrome.
- Embedded mode (iframe inside terminal): `html.embedded` class applied at `<head>` parse time (`try{if(window.self!==window.top)...}`); suppresses all decorative chrome (canvas, hexGrid, `.field`), removes border/shadow from `.panel`, flattens to transparent bg `#020408`.

### Color palette (CSS vars declared on `:root`)

| Var | Value | Semantic role |
|---|---|---|
| `--bg` | `#070d16` | page background |
| `--panel` | `#0a1220` | card background |
| `--border` | `rgba(0,224,255,.15)` | primary border |
| `--border2` | `rgba(0,224,255,.09)` | hairline separator |
| `--text` | `#d6eeff` | body text |
| `--muted` | `#5a7a9a` | de-emphasized |
| `--core` | `#00e5ff` | cyan accent (positive gamma, call wall) |
| `--purple` | `#8b5cf6` | gamma flip |
| `--red` | `#ff3b3b` | negative gamma, put support, trigger |
| `--green` | `#00ffa3` | expansion, up arrows |
| `--amber` | `#ffb300` | HVL/magnet, current price row |
| `--lbl` | `#8ea7c4` | section labels (AA-compliant) |
| `--meta` | `#a8c0db` | sentence-level metadata |
| `--mono` | `'Geist Mono',ui-monospace,monospace` | primary typeface |
| `--display` | `'Inter',sans-serif` | label/badge typeface |
| `--r` | `16px` | border radius |

Embedded mode overrides: `--bg:#020408`, `--panel:#060c14`, `--muted:#4a6a8a`.

---

## 2. Top Bar

```
.topbar  →  flex row, padding 11px 20px
  .page-id              "GEX TERMINAL"  (Inter 900, 12px, 2.5px letter-spacing, cyan glow)
  .divider              1px × 18px
  #dataChip             pulsing-dot + status label (clickable → toggleDataMode())
  #clockChip            "HH:MM:SS ET"  (ticks every 1 s)
```

`#dataChipLabel` text states (and border-color changes on `#dataChip`):
- `"LOADING..."` — fetch in flight
- `"SERVER · N strikes"` — served from `computed-grid` function (border `rgba(0,255,136,.5)`)
- `"SNAPSHOT · N strikes"` — served from `gex_snapshots_live` Supabase table, ≤5 min old (border `rgba(0,229,255,.4)`)
- `"LIVE · N contracts"` — computed from raw chain (border `rgba(0,255,163,.4)`)
- `"LIVE · N (PARTIAL)"` — chain has ≤1 strike above or below spot (border `rgba(255,179,0,.4)`)
- `"CACHED · N strikes"` — LRU memory hit (<2 min old)
- `"MOCK DATA"` — mock fallback active

---

## 3. Controls Bar (sticky, `z-index:20`)

Layout: `flex row, gap 16px, padding 10px 20px`, `position:sticky; top:0`.
Background is an opaque layered gradient so it stays solid on scroll.

### 3.1 Ticker Input

```
#tickerInput  (.ticker-select)
  type="text", 100px wide, centered, text-transform:uppercase
  Commits on Enter or blur
  On commit: posts { source:'gexFrame', ticker } to parent if in iframe (no `target` field — see §7)
```

Default ticker: `SPY`. URL param `?ticker=` or `?symbol=` is read at init.
On ticker change, default range resets: index ETFs (`SPY QQQ IWM DIA SPX NDX RUT VIX XSP XND SPXW`) → `0.05` (±5%); single names → `0.15` (±15%).

### 3.2 Price Badge

```
#spotPrice     "NNN.NN"
#spotChange    "+N.NN (+N.NN%)"  class "up"/"down"
```

### 3.3 Range Pills

ID `#rangeGroup`. Pill set (hard-coded):

| Label | `ST.range` value |
|---|---|
| `±5%` | `0.05` |
| `±10%` | `0.10` |
| `±15%` | `0.15` |
| `±25%` | `0.25` |
| `ALL` | `null` |

Active pill: `.pill.active` (cyan bg, border, text-shadow). Clicking any pill calls `render()`.
Auto-expansion: if the selected range would yield 0 strikes, the range is forced to `null` (ALL) without user interaction.

### 3.4 Expiry Dropdown

`.exp-dropdown` with `.exp-dd-trigger` + `.exp-dd-menu` (custom listbox, ARIA `role=listbox/option`).
- Trigger shows selected value; caret rotates 180° on open.
- Menu: max-height 300px, scrollable, `backdrop-filter:blur(8px)`.
- First option always `"ALL"` (hint: "all expiries").
- Each other option shows date `YYYY-MM-DD` + DTE hint (`"0DTE"` or `"Nd"`).
- Active option styled `.exp-dd-opt.active`: amber (`var(--amber)`, `rgba(255,179,0,.1)` bg).
- Closes on outside click or Escape.

Expiry list sourcing:
- Standalone windowed chain expiries (≤60 DTE from `uw-chain?windowed=true`) fill the dropdown immediately.
- A background call to `/.netlify/functions/uw-chain?endpoint=option-expirations` fetches up to ~1 yr of dates (`ALL_EXP[ticker]`); on arrival the dropdown rebuilds.
- On-demand load: if user picks an expiry not in the local chain, `ensureExpiryChain` fetches `uw-chain?endpoint=option-strikes&expiration_date=DATE`, adapts contracts, injects into `D._chain`, then re-renders.

---

## 4. Strike Bar Chart

### 4.1 Layout

Each strike row: `.strike-row`, CSS grid `grid-template-columns: 116px 1fr 84px`, height 20px (desktop standalone), 30px (mobile standalone, `max-width:768px`), 16px (embedded mobile).
Zero-axis center line: `.bar-center` (1px cyan-tinted hairline at `left:50%`). Hidden in embedded mode.

Row ordering: strikes rendered **descending** (highest strike at top), matching the GEX engine sort (`strikes.sort((a,b) => b.strike - a.strike)`).

### 4.2 Bar Length Formula

```js
// _gexBarMetrics(s, mx) in gex-init.js
const pct = mx > 0 ? Math.abs(s.gex) / mx : 0;
const shaped = Math.pow(pct, 0.7);          // power-curve, not linear
return { bw: Math.max(shaped * 48, 3), pos: s.gex >= 0, big: pct > 0.35 };
```

- `mx` = `Math.max(...strikes.map(s => Math.abs(s.gex)), 1)` — the single largest |GEX| in the visible range.
- Bar width = `max(shaped × 48, 3)%` of the half-chart area (max 48% = never crosses axis).
- Floor: `3%` minimum so non-zero strikes always render a visible stub.
- `big` flag: strikes with `|gex|/mx > 0.35` get the `.bar.big` class (breathing animation `barBreathPos`/`barBreathNeg`).

### 4.3 Bar Color Rules

| Condition | CSS class | Color |
|---|---|---|
| `s.gex >= 0` | `.bar.positive` | cyan gradient `rgba(0,229,255,.45) → rgba(0,229,255,.85)`, grows left→right |
| `s.gex < 0` | `.bar.negative` | red gradient `rgba(255,59,59,.45) → rgba(255,59,59,.85)`, grows right→left |

The wrapper `.bar-wrapper` is `positive` (left-anchored, grows right) or `negative` (right-anchored, grows left from center).

GEX value column (`.gex-value`): `var(--core)` for positive, `var(--red)` for negative. Formatted by `fmtG()`:

```js
function fmtG(v){
  if(!Number.isFinite(v)) return '—';
  const s=v>=0?'+':'', a=Math.abs(v);
  if(a>=1e6) return s+(v/1e6).toFixed(1)+'M';
  if(a>=1e3) return s+(v/1e3).toFixed(1)+'K';
  return s+Math.round(v);
}
```

### 4.4 Spot Highlight (Current-Price Row)

Row with `s.isCurrent === true` (strike within `step * 0.6` of spot):
- Class `.strike-row.current-price`
- Background: `rgba(255,179,0,.06)` pulsing: `@keyframes currentPulse` (0%→.05, 50%→.10, 100%→.05)
- Border: `1px solid rgba(255,179,0,.2)` top and bottom (amber)
- Strike price: `var(--amber)`, `font-weight:700`, text-shadow `0 0 10px rgba(255,179,0,.5)`

Border collision with flip marker resolved: `.gex-flip-marker + .strike-row.current-price { border-top:none }` and `.strike-row.current-price:has(+ .gex-flip-marker) { border-bottom:none }`.

### 4.5 Zone Shading

Strikes within `step * 2` of a level get a background tint class:

| Zone | Class | Background |
|---|---|---|
| Call Wall | `.zone-cw` | `rgba(0,229,255,.04)` |
| HVL/Magnet | `.zone-hvl` | `rgba(255,179,0,.04)` |
| Put Support | `.zone-ps` | `rgba(255,59,59,.04)` |

These are mutually exclusive. Hover shading doubles the opacity.

### 4.6 Strike-Price Tinting

Strikes carrying a classification or level-proximity badge also get a `.sp-*` class that tints the price number (unless the row is also `.current-price`, which wins via specificity):

| Tone | Class | Color |
|---|---|---|
| Call Wall / WALL | `.sp-cyan` | `#00e5ff` |
| HVL / MAGNET | `.sp-amber` | `var(--amber)` |
| Put Support / SUPPORT / TRIGGER | `.sp-red` | `#ff5c5c` |

### 4.7 Badges (Single Card per Strike)

Classification source priority:
1. `StrikeClassifier.classify()` result with `confidence >= 0.5` (engine-confirmed role).
2. Fallback: level-proximity tag (`s.levelTag ∈ {'cw','hvl','ps'}`).

```js
const CARD_BY_CLS = {
  CALL_WALL:          { tag: 'WALL',    tone: 'cyan',  name: 'Call Wall' },
  PUT_SUPPORT:        { tag: 'SUPPORT', tone: 'red',   name: 'Put Support' },
  MAGNET:             { tag: 'MAGNET',  tone: 'amber', name: 'High-Value Level (Magnet)' },
  PIN_LEVEL:          { tag: 'MAGNET',  tone: 'amber', name: 'High-Value Level (Magnet)' },
  VOLATILITY_TRIGGER: { tag: 'TRIGGER', tone: 'red',   name: 'Volatility Trigger' },
};
const CARD_BY_LEVEL = {
  cw:  { tag: 'WALL',    tone: 'cyan',  name: 'Call Wall' },
  hvl: { tag: 'MAGNET',  tone: 'amber', name: 'High-Value Level (Magnet)' },
  ps:  { tag: 'SUPPORT', tone: 'red',   name: 'Put Support' },
};
```

Badge element: `<span class="cls-badge t-{tone}">TAG</span>`. `title` attribute carries the full name (no translated text — CI-enforced upstream). Unified font: 8px, weight 800, letter-spacing 1px, padding 2px 6px, border-radius 4px, static glow via `box-shadow`.

OI-change badges (`.oi-badge`): shown above bar tip, `NEW OI` (green) or `EXIT OI` (red), animate `oiBadgePulse` (opacity 0.7↔1, 3s). Positioned right side for positive bars, left side for negative.

### 4.8 Row Selection

Click toggles `SELECTED_STRIKE` (stored as the strike's dataset string, e.g. `"580.5"`):
- Selected row: `.strike-row.selected` — background `rgba(214,238,255,.09)`, `box-shadow:inset 0 0 0 1px rgba(214,238,255,.4)`, left 3px accent bar in `var(--text)`.
- `selected .bar` gets `filter:brightness(1.3)`.
- Clicking the already-selected row deselects it.

### 4.9 Scroll / Animation

During scroll (`_gexScrolling = true`, cleared after 150ms idle), `.chart-scroll.scrolling` is applied, which:
- Pauses `.bar.big` breathing and `.current-price` pulse animations.
- Removes `.strike-row` hover transitions.
- Tooltip is hidden.

Bar grow animation: `@keyframes barGrow { from{transform:scaleX(0)} to{transform:scaleX(1)} }`, 0.5s `cubic-bezier(.22,1,.36,1)`. Each row gets `animationDelay: i * 0.018s` (staggered at 18ms per row).
In-place refresh (same strike set on data update): bars are NOT re-created (no animation replay). Only `_applyRow()` mutates existing DOM.

### 4.10 Tooltip

On `mouseenter` (delegated at `#chartScroll`):
```
$NNN.NN — LEVEL_TAG
Net GEX    +NNN.NK
─────────────────
Call OI    NNN.NK
Put OI     NNN.NK
OI Δ 24h   +NNN.NK   (only if D._hasDoDBaseline === true)
─────────────────
Call Γ     N.NNNN
Put Γ      N.NNNN
```
Fixed-position; hides on scroll. Call OI colored `var(--core)`, Put OI `var(--red)`, OI Δ green/red by sign.

### 4.11 Loading Skeleton

16 rows of `.gex-skel-row` (grid `116px 1fr 84px`, height 18px) with animated shimmer bars at preset widths: `34%, 52%, 41%, 63%, 48%, 72%, 57%, 85%, 68%, 78%, 55%, 44%, 60%, 38%, 50%, 30%`. Cleared by `renderChart()` on first data arrival. 20s watchdog replaces skeleton with error message if no `.strike-row` appears.

---

## 5. Gamma Flip Line

The flip marker is a full-width divider inserted **between** the two strikes that straddle the flip level (i.e., `strikes[i].strike >= flipStrike && flipStrike > strikes[i+1].strike`).

```js
// _makeFlipMarker(engineFlipStrike)
marker.style.cssText = 'display:flex;align-items:center;gap:10px;padding:4px 20px;height:32px;'
  + 'background:rgba(139,92,246,.08);'
  + 'border-top:1px solid rgba(139,92,246,.32);'
  + 'border-bottom:1px solid rgba(139,92,246,.32);'
  + 'box-shadow:0 0 9px rgba(139,92,246,.1);'
  + 'animation:flipLineIn .5s ease-out, flipLinePulse 5s ease-in-out infinite .5s;';
```

Content: `"Γ FLIP"` label (Inter 900, 9px, 3px letter-spacing, purple glow) + a purple gradient line + the flip strike price in mono 8px.

`flipLinePulse` keyframes:
```css
0%,100%{ background:rgba(139,92,246,.05); box-shadow:0 0 6px rgba(139,92,246,.07) }
50%    { background:rgba(139,92,246,.085); box-shadow:0 0 11px rgba(139,92,246,.14) }
```

On live in-place refresh, existing flip markers are removed and re-inserted at the (possibly changed) position.

Flip strike source: `D._engine.classification.regime.flipStrike` (engine Method 2 profile-scan, ±10% grid at 1% steps, prefers `upcross` direction). Confidence levels: `'high'` (≤3% from spot), `'medium'` (3–7%), `'low'` (>7%), `'none'` (no crossing found → flip line suppressed, `flipStrike` set to spot).

---

## 6. Oracle Market Structure Panel (Standalone only)

Section ID `#intelSection`, class `intel-section`. **Not rendered in embedded mode** (`el.innerHTML=''; el.style.display='none'`).

Section title: "Oracle Market Structure" (uppercase, letter-spacing 2.2px, teal separator line).

### 6.1 Grid Layout

Three-column `intel-grid` (equal `1fr 1fr 1fr`). Collapses to 1 column at `max-width:900px`.

### Card 1: Market State

- IC label: "Market State"
- Hero value: `clsRegime.state` ∈ `{PIN, DRIFT, RANGE, TRANSITION, TREND, CASCADE, UNKNOWN}` displayed as `.state-value.{stateCls}`.

State colors:
| State | Color |
|---|---|
| `stable`, `pin` | `var(--green)` |
| `range`, `drift` | `var(--core)` |
| `transition`, `volatile` | `var(--amber)` |
| `trend`, `explosive`, `cascade` | `var(--red)` |
| `unknown` | `var(--muted)` |

- Subtitle: `clsRegime.stateDescription` (engine text, sanitized by `omsClean()`).
- "Net γ" tag: `POSITIVE` (`.mode-tag.range`) / `NEGATIVE` (`.mode-tag.trend`) / unknown (`.mode-tag.muted`).
- **Stability pressure bar**: `width: clsRegime.stabilityPct + '%'`. Fill gradient is cyan in positive regime, cyan-low-opacity in negative (`neg-fill`), gray in unknown (`muted-fill`). Right label shows `100 - stabilityPct` as "volatility share".

State thresholds computed in `StrikeClassifier.classify()`:
```js
if (_flipIsKnown && nearFlip)                       state = 'TRANSITION';  // flipDistPct < 0.002
else if (ratio > 0.75)                              state = 'DRIFT';
else if (ratio > 0.65)                              state = 'PIN';
else if (ratio > 0.55)                              state = 'RANGE';
else if (_flipIsKnown && closeToFlip && ratio > 0.35) state = 'TRANSITION'; // flipDistPct < 0.005
else if (ratio > 0.45)                              state = 'RANGE';
else if (ratio > 0.30)                              state = 'TREND';
else                                                state = 'CASCADE';
```
where `ratio = posGex / (posGex + |negGex|)` across all pruned strikes (within ±20% of spot).

Degenerate chain gate: `if (totalAbs < max(1000, spot * 100)) → return _emptyResult()`.

### Card 2: Magnet

- IC label: "Magnet"
- Hero value: `clsRegime.pricePull.strike` (HVL from classifier), falls back to `D.hvl`. Formatted by `fmtLvl()`.
- Sub-line (if flip is known): `"Flip at NNN · Spot +/-N.N (N.NN%)"`.
- Zone badge (`.flip-zone`): shown unless it would echo the state card.

Zone logic:
```js
if (!_hasFlip || netGammaState === 'UNKNOWN')      → 'unk', '◇ ZONE UNKNOWN'
else if (flipDistPct < 0.5 || state === 'TRANSITION') → 'volatile', '● TRANSITION ZONE'
else if (flipDist >= 0 && isPos)                   → 'stable',   '● STABLE ZONE'
else if (flipDist < 0 && isPos)                    → 'stable',   '● SUPPORT ZONE'
else                                               → 'volatile', '● VOLATILITY ZONE'
```

- **Cascade Trigger** (inlined below the flip info, only if `cascadeLevel.confidence >= 0.4`):
  - Shows `cascadeLevel.strike` in red 18px with `.cls-badge.trigger` + direction text.
  - `cascadeTrigger` is the strongest negative-gamma strike below the flip, scored by `intensity * (0.6 + proximity * 0.4)`.

### Card 3: Positioning Flow

- IC label: "Positioning Flow" (if expiry-filtered, adds "FULL CHAIN" note).
- Direction arrow + label:
  - `▲ EXPANSION` (green) — `hasBaseline && totalOIDelta > 0 && |delta| >= noiseFloor`
  - `▼ DRAIN` (red) — `hasBaseline && totalOIDelta < 0 && |delta| >= noiseFloor`
  - `◆ NEUTRAL` (amber) — baseline exists but signal below noise floor
  - `◇ AWAITING` (amber flat) — no prior-day baseline yet
  - Noise floor: `max(chainTotalOI * 0.005, 100)`.
- Metric: `+/- totalOIDelta` formatted as contracts (24h label).
- Sub-text: context string per state.
- **Top OI cluster**: the strike within ±15% of spot with the largest `|oiDelta|`, shown if non-zero. Green if expansion, red if drain. Strike price + formatted delta.

---

## 7. Market Bias Strip (Standalone only)

ID `#biasStrip`, class `bias-strip`. Suppressed in embedded mode.

4 cells, flex row:

| Cell | Source | Colors |
|---|---|---|
| **Market Bias** (flex 1.6) | `analytics.bias.verdict` + sub-lines from `bias.magnetLevel`, `bias.upResistance`, `bias.downTrigger` | text only |
| **Liquidity Pull** | `clsRegime.gravity` (preferred) or `analytics.gravity`; direction string + `upPct/downPct` bar | green=up, red=down, amber=neutral |
| **Pin Target** (if `isPositive && pin.probability > 0`) OR **Likely Path** | `analytics.pin.strike` + `probability%` OR 3-step path from `analytics.path.steps` | purple for pin; path steps typed: current=text, target=amber, resistance=cyan, support=red, speedbump=muted |
| **Hedging Pressure** | `analytics.acceleration.level` ∈ {high,medium,low,unknown} → 5-segment bar | high=red, medium=amber, low=green, unknown=muted; segments `[1,2,3,4,5].map(i => i <= threshold)` with thresholds `{high:5, medium:3, low:1, unknown:0}` |

Gravity display bar: `height:5px`, two div segments `.gravity-up` (green) + `.gravity-down` (red), widths = `upPct%` / `downPct%`.

---

## 8. Summary Bar and Legend

`.summary-bar` — rendered above the chart (lifted in 2026-06-08 redesign, was previously below). Contains:

```
Net GEX (±N% visible)  [breathing hero, pos=cyan neg=red]
Call Wall  [cyan]
HVL        [amber]
Put Support [red]
P/C Ratio  [green if ≤1, red if >1]
Call OI    [cyan]
Put OI     [red]
```

Net GEX hero animation `netGexBreath`: `filter:brightness(1)` → `brightness(1.35)` → `brightness(1)`, 3s.

### Legend / How-to-read

`.gex-howto` — collapsed by default. Collapsed state IS the color legend:
- `Positive GEX` (cyan dot)
- `Negative GEX` (red dot)
- `Call Wall` (cyan, 50% opacity)
- `Magnet · HVL` (amber)
- `Gamma Flip` (purple)

Expands to a `3×2` grid of term cards (1 column on mobile `<768px`):

| Term | Description text |
|---|---|
| GEX (Gamma Exposure) | "A map of where the biggest options bets sit, and where dealer hedging is likely to push or pin price." |
| Call Wall | "A ceiling. Price often stalls into it as dealers sell into rallies." |
| Put Support | "A floor. Selloffs slow here as downside protection cushions the drop." |
| Magnet (HVL) | "The high-volume level price gets pulled toward and pins." |
| Gamma Flip | "Below it, hedging amplifies moves and volatility rises." |
| Net γ Positive | "Above the flip: a calm, mean-reverting, range-bound regime." |

Toggle: `button#gexHowtoToggle` flips `.open` on `#gexHowto`. Aria attributes sync. Caret rotates 180°.

---

## 9. Chart Terminator

`.chart-end` — last element inside `#chartScroll`. Label text:
```
"{N} STRIKE(S) · ±{X}% RANGE"   (or "FULL CHAIN" if range = null)
```
Rendered by `renderChartEnd()`. Flanked by two gradient lines (`linear-gradient(90deg, transparent, rgba(0,229,255,.28), transparent)`). Prevents empty-panel "still loading" impression on short chains.

---

## 10. Embedded Mode: OMS Row Strips

When inside the terminal iframe, `renderIntel()` and `renderBias()` are suppressed. Instead the parent terminal's right pane drives the structural read.

The embedded left shows a compact instrument strip (`#biasStrip` cleared, `#intelSection` cleared). The parent terminal receives structure data via postMessage (see §11).

Three OMS rows (`.oms-rows`) defined for a possible alternate embedded layout:
- `.oms-row.magnet` — purple, 5-column grid (label | hero | 3 cells)
- `.oms-row.flow` — green
- `.oms-row.bias` — amber

Mobile embed collapses each strip to `grid-template-columns: 1fr 1fr 1fr` with label + hero spanning first row, 3 cells below.

---

## 11. postMessage: Ticker Sync and Struct

### Parent → GEX iframe

```js
// All messages must have target: 'gexFrame'
{ target: 'gexFrame', ticker: 'SPY' }          // change ticker (silent: no echo back)
{ target: 'gexFrame', kind: 'parentScroll' }   // notify of scroll for tooltip hiding
{ target: 'gexFrame', kind: 'pause' }          // pause animations/refresh
{ target: 'gexFrame', kind: 'resume' }         // resume; if paused >90s → immediate refresh
```

Validation: `if (e.origin !== location.origin) return`.

### GEX iframe → Parent

```js
// Ticker change by user (only if not triggered silently by parent)
{ source: 'gexFrame', ticker: 'NVDA' }

// Ready handshake (on init, embedded only)
{ source: 'gexFrame', kind: 'ready' }

// Height bridge (embedded, every render + 1s interval + ResizeObserver)
{ source: 'gexFrame', kind: 'height', height: N }   // N = scrollHeight in px

// Struct payload (every render, same-origin only)
{
  source: 'gexFrame',
  kind: 'struct',
  ticker: 'SPY',
  expiry: 'ALL',                  // currently selected expiry
  struct: {
    gexSnapshot: {
      ticker, spot, gamma_flip, gamma_flip_dislocated, gamma_flip_confidence,
      call_wall, put_support, hvl, net_gex, regime
    },
    levels: { callWall, putSupport, hvl, gammaFlip },
    regime: { state, stabilityPct, stateConfidence, netGamma, gravity: {upPct, downPct} },
    analytics: { gravity: {upPct, downPct}, bias: {rangeLow, rangeHigh}, pin: {strike, probability} },
    timestamp,
    truncated: false
  }
}
```

`gamma_flip_dislocated = true` when `|flip - spot| / spot > 0.10`.

---

## 12. Levels and Wall / Support / Magnet Detection

All level detection runs client-side in `gex-engine.js`.

### Call Wall (CW)
Candidates: strikes with `strike >= spot + avgStep * 2`. Scored by `callOI * callGamma`. Hysteresis: if a candidate within 5% of the winner's score is closer to spot, it wins instead. Fallback chain: any strike above spot → max callGex → highest strike available.

### Put Support (PS)
Mirror of CW: strikes with `strike <= spot - avgStep * 2`, scored by `putOI * putGamma`.

### HVL / Magnet
Candidates: strikes strictly between PS and CW. Scored by `totalOI * avgGamma * proximity` where `proximity = 1 / (1 + distFromSpot / (avgStep * 3))`. Hysteresis tolerance 3%. Spacing guard: HVL is pushed to `PS + (CW - PS) * 0.4` if too close to PS, `PS + (CW - PS) * 0.6` if too close to CW. `marginPct = 0.15`.

### Gamma Flip (Method 2 — preferred)
Grid: ±10% from spot in 1% steps (21 points). For each hypothetical spot `S_hat`, recomputes BS gamma with dividend yield for every contract in chain, sums signed GEX, finds `upcross` zero crossing. Returns `gammaProfile: [{spot, netGex}]` array.

Fallback (Method 1): walks cumulative netGex through sorted strikes; interpolates between adjacent strikes where sign changes. Window filter: crossings outside ±15% of spot are discarded.

Confidence levels (Method 2): `'high'` ≤3%, `'medium'` 3–7%, `'low'` >7%, `'none'` no crossing.

### Volatility Trigger
Below-flip strikes with `netGex < 0`, intensity ≥ 75th-percentile of negative intensities, scored by `intensity * (0.6 + proximity * 0.4)`. Must differ from the designated Put Support strike.

---

## 13. Data Fetch Architecture

Server fast-paths (in priority order):
1. **`gex_snapshots_live` Supabase table** — if age < 5 min (`_SNAPSHOT_FRESH_MS = 300000`) and state not UNKNOWN.
2. **`/.netlify/functions/computed-grid?ticker=`** — server-precomputed strikes + levels + classification + analytics JSON. Spot divergence guard: if cached price differs >3%, falls back.
3. **Client-side computation** — fetches `uw-chain` (windowed, ≤60 DTE) + `price` proxy, runs full GEX engine locally.

LRU cache: `_LIVE_MAX = 5` tickers kept in `LIVE{}`. Evicted on 6th ticker.
In-memory cache: serves same ticker if timestamp < 2 min old.
Auto-refresh: every `~173s * (0.95 + random()*0.10)` during market hours (weekdays, `570 <= totalMinutesET < 975`, i.e. 09:30–16:15 ET). Deferred if `_gexScrolling`.

Baseline (day-over-day OI diff):
- Primary: `gex_snapshots` Supabase table, prior trading day.
- Fallback: `localStorage`, key pattern `gex_baseline_oi_{TICKER}_{YYYY-MM-DD}`, scans up to 7 prior days.
- Written today's baseline to localStorage under today's key (skips if already written this session).
- LRU prune: keeps most recent 4 + today's keys; cross-ticker sweep purges keys older than 7 trading days.

---

## 14. Background Decoration

**Particle field** (`#bgCanvas`): 80 particles, radii 0.2–1.4, speed ±0.25 px/frame (slight upward bias `vy - 0.05`). Two hues: `hue=192` (cyan, 85% probability) or `hue=280` (purple, 15% probability). Connecting lines between particles within 90px: `rgba(0,229,255, (1-dist/90)*0.08)`. On mobile (`innerWidth<768`), lines drawn every 3rd frame. Paused in embedded mode and when `_parentPaused`.

**Hex grid overlay** (`.hexGrid`): SVG background-image at 56×100px tile, `opacity:.032`, no animation (drift removed as it caused full-screen repaint).

**Radial field** (`.field`): `fieldPulse` animation 8s, opacity oscillates 0.7↔1.

---

## 15. Auth Guard

Supabase project: `pojiqfeemksvocnaellu.supabase.co`. SDK loaded from jsdelivr CDN (`@supabase/supabase-js@2.106.1`). 8s `getSession` timeout. Shared `access-gate.js` module (`MomoEdge.accessGate`). Body hidden (`opacity:0`) until guard passes. Redirect paths: `/login.html` (no session), `/waitlist-confirmation` (unclaimed), `/checkout` (claimed-but-unpaid).

---

## 16. What Is Server-Side (Not in Client Code)

- GEX computation behind `computed-grid` Netlify function: the function runs the same `gex-engine.js` modules on the server with a complete options chain and writes to `gex_snapshots_live`. The client receives pre-computed `levels`, `classification`, `analytics`, and strike array.
- Raw options chain sourced from `uw-chain` Netlify function (proxies Unusual Whales API with JWT auth). Client never calls UW directly.
- Price proxy: `/.netlify/functions/price?symbol=TICKER` — actual data provider not visible in client code.
- `option-expirations` and `option-strikes` endpoints on `uw-chain` function — used for far-dated expiry on-demand loads.
- Supabase tables: `gex_snapshots` (daily EOD snapshots), `gex_snapshots_live` (intraday, ≤5 min fresh), `beta_codes`, `trader_profiles` (access gate).
- Real-time GEX computation cadence and `computed-grid` caching logic are server-side.
