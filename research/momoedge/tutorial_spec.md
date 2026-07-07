# MomoEdge Interactive Tutorial — Reverse-Engineered Spec

**Source files:** `js/modules/learning/{coach,fixtures,lesson-flow,lesson-gex,lesson-heatmap,lesson-oracle,lesson-risk,lesson-signals,preview}.js` + `js/learning-init.js` + `js/modules/course-gate.js`

---

## 1. Overall Architecture

### 1.1 Module namespace

All learning code hangs off `window.MomoLearn`:
- `window.MomoLearn.coach` — the narrator/step engine (coach.js)
- `window.MomoLearn.FIX` — static demo data fixtures (fixtures.js)
- `window.MomoLearn.lessons.<id>` — per-lesson objects (lesson-*.js)
- `window.MomoLearn.preview` — terminal-preview overlay (preview.js)

### 1.2 Layout (Hybrid A+B, locked 2026-06-10)

Two persistent UI regions on `learning.html`:

1. **Left module rail** (`#lpNav`) — numbered list of modules with state icons (🔒 locked, ▶ active, ✓ done). Shows "MODULES · N OF 6 DONE" count. Only unlocked/done modules are clickable (`.lp-mod--go`).
2. **Bottom Momo bar** — always-visible narrator strip containing:
   - `#momoText` — lesson narration HTML (inner HTML, not text)
   - `#momoHint` — small hint line (plain text)
   - `#momoStep` — "STEP N OF M" pill; in free-explore shows "FREE EXPLORE" with class `lp-momo-step--free`
   - `#momoChecks` — inline checklist for `advance:'checks'` steps
   - `#momoBack` / `#momoNext` — Back / Next buttons
   - `#momoInput` / `#momoSend` — Ask-Momo AI chat input (streams from `/.netlify/functions/momo-ai` — **server-side**)

3. **Spotlight ring** (`#lpSpot`) — absolutely positioned `<div>` with CSS transition `all .45s`. Placed via `getBoundingClientRect()` with ±8px padding on all sides. Hidden via class `lp-spot--off`. On first reveal, suppresses transition via `style.transition = 'none'` then restores it after a `void offsetWidth` reflow flush.

4. **Lesson host** (`#lpLessonHost`) — cleared and re-rendered on each module load.

### 1.3 Top-bar progress

`#lpProgLabel` (text "N / 6 COMPLETE") and `#lpProgFill` (width CSS % = `n/6 * 100`) update on every `onComplete` call.

---

## 2. Lesson Module Metadata

Defined on each lesson object (used by the nav rail and lesson header):

```
{ id, num, name, sub, eyebrow, title, objective }
```

| id       | num | name     | sub                  |
|----------|-----|----------|----------------------|
| oracle   | 1   | ORACLE   | Read the environment |
| flow     | 2   | FLOW     | Read the tape        |
| signals  | 3   | SIGNALS  | Anatomy of a trade   |
| gex      | 4   | GEX      | Gamma, flip & walls  |
| heatmap  | 5   | HEATMAP  | Price & flow layers  |
| risk     | 6   | RISK     | Size & survive       |

**Canonical order** (hardcoded in `learning-init.js`):
```js
var ORDER = ['oracle','flow','signals','gex','heatmap','risk'];
```

---

## 3. Coach Engine (coach.js)

### 3.1 Step shape

```js
{
  target: '#css-selector',      // element to spotlight; null = no ring
  text: 'html string',          // narrator text (innerHTML)
  hint: '',                     // small secondary hint (textContent)
  advance: 'next'               // how this step self-advances:
           | 'target'           //   user clicks the spotted element
           | 'checks'           //   all need[] keys checked off
           | 'event',           //   window custom event fires
  need: ['key1','key2'],        // advance:'checks' — keys to collect
  event: 'lp:eventName',       // advance:'event' — event name
  onEnter: function(){},        // called before place() — use to reveal hidden targets
  auto: function(){}            // optional: what Next/hotkey does instead of bare advance
                                // (calls forceNext() when gesture is complete)
}
```

### 3.2 Step flow

1. `coach.start(steps, onComplete)` — clears preview, resets `seen={}`, `done=false`, calls `show(0)`.
2. `show(i)` — sets narrator text + pill, enables/disables Back/Next, calls `onEnter()`, then calls `place(target)`.
3. **Next button** calls `requestNext()`:
   - If step has `auto()` AND advance is not `'next'`: calls `auto()` (lesson performs the gesture for the user); `auto()` must itself call `coach.forceNext()` when ready.
   - Otherwise: calls `next()` which increments to `show(i+1)` or calls `finish()`.
4. **Back button**: calls `show(idx-1)`; disabled at step 0.
5. **Keyboard**: `Space` / `ArrowRight` → `requestNext()`; `ArrowLeft` → back. Suppressed when focus is on `input`, `textarea`, `select`, `button`, `a`, or `contentEditable`.

### 3.3 Advance modes

| mode     | Next enabled?                        | Advances when                        |
|----------|--------------------------------------|--------------------------------------|
| `next`   | Always                               | User clicks Next / Space / →         |
| `target` | Disabled (unless `auto()` present)   | `coach.advanceFromTarget()` called   |
| `event`  | Disabled (unless `auto()` present)   | `window.dispatchEvent(new Event(name))` |
| `checks` | Disabled until all keys seen         | All keys checked, then user clicks Next |

### 3.4 Checks mechanic

- `coach.check(key)` marks a key in `seen{}`, re-renders `#momoChecks`.
- When all `need[]` keys are present: enables Next, sets hint to `'all done — hit Next'`.
- Checklist renders as: `<span class="lp-check [lp-check--on]">[✓ ]KEY</span>`.

### 3.5 Free-explore mode

After `finish()`:
- Spotlight hidden, Next/Back disabled.
- `coach.freeSay(html)` writes narrator with `step='FREE EXPLORE'` (class `lp-momo-step--free`).
- Each lesson wires its interactive elements so clicks call `coach.freeSay(EXPLAIN[key])` with the relevant explanation snippet.

### 3.6 Spotlight placement algorithm

```js
spot.style.left   = (r.left + window.scrollX - 8) + 'px';
spot.style.top    = (r.top  + window.scrollY - 8) + 'px';
spot.style.width  = (r.width  + 16) + 'px';
spot.style.height = (r.height + 16) + 'px';
```

Refreshed on `resize` and `scroll` (passive) events.

### 3.7 AI chat (server-side)

Streams token-by-token from `POST /.netlify/functions/momo-ai` with JSON body `{ question, lesson, step }`. Requires Bearer JWT from Supabase session (`window._sbAuthClient`). HTTP status codes: 401 = "Sign in again", 429 = rate limit message, 503 = offline message. Degrades gracefully on missing `ReadableStream`. **This function is server-side only; not in the client bundle.**

---

## 4. Progress Tracking & Gating

### 4.1 localStorage store

Key: `'momoedge_learning_progress_v1'`

Shape:
```json
{
  "modules": {
    "oracle": { "done": true, "completedAt": "ISO-8601" },
    ...
  },
  "lastModule": "risk"
}
```

### 4.2 Unlock logic

```js
function isUnlocked(id){
  var i = ORDER.indexOf(id);
  return i === 0 || isDone(ORDER[i - 1]);
}
```

Module 1 (oracle) is always unlocked. Each subsequent module unlocks only when the prior one is marked done. Users can always re-visit already-done modules.

### 4.3 Server-side flag (MOM-403)

When all 6 modules complete: writes to Supabase table `user_onboarding` column `learning_completed_at` (ISO timestamp) via:
```js
sb.from('user_onboarding')
  .upsert({ user_id: session.user.id, learning_completed_at: new Date().toISOString() },
           { onConflict: 'user_id' })
```

**This is the enforcement flag.** The localStorage progress is per-device UX only.

### 4.4 Course gate (course-gate.js)

Invoked by `terminal-init.js` as `window.MomoEdge.courseGate.show()` when:
- User is entitled (paid)
- `user_onboarding.learning_completed_at` is null (server-side check — **server-side**)
- No bypass flag

Gate behavior: injects a full-screen blocking modal (z-index `2147483646`), Esc suppressed, focus trapped. Only action: "START THE COURSE →" button navigates to `/learning.html?return=terminal`. On completion, `finalDest()` returns `/terminal.html` (because `?return=terminal` is present). New-user post-checkout flow uses `?flow=onboarding` and routes to `/oracle-entry.html` instead.

### 4.5 Backfill shim

On page load, if `doneCount() === 6` but server flag is absent, calls `markCourseComplete()` once to sync pre-MOM-403 users.

### 4.6 Hash routing

URL hash = active module id (e.g. `#gex`). Updated via `history.replaceState`. `hashchange` event triggers `load(id)`. On initial boot, loads `location.hash || firstOpen()`.

### 4.7 Replay

"Replay lesson" button calls `load(id, replay=true)`, which forces `coach.start()` even on already-done modules.

---

## 5. Lesson Step Sequences

### 5.1 ORACLE (lesson-oracle.js) — 5 steps

Demo widget: animated `#lpOrb` sphere (144×144px circle) cycling through GREEN → YELLOW → RED environments on click.

Environment configs (all in `ENVS` constant):
```js
green:  { label:'GREEN',  tag:'RISK-ON ENVIRONMENT',  accent:'#00ffa3', ... }
yellow: { label:'YELLOW', tag:'MIXED / TRANSITION',   accent:'#ffb300', ... }
red:    { label:'RED',    tag:'DOWNTREND ENVIRONMENT', accent:'#ff5a5a', ... }
```

Each env defines `dir` (trade direction text) and `pos` (posture text).

| Step | Target    | Advance  | Action required          |
|------|-----------|----------|--------------------------|
| 1    | `#lpOrb`  | next     | Read, hit Next           |
| 2    | `#lpOrb`  | target   | Click sphere (→ YELLOW)  |
| 3    | `#lpOrb`  | target   | Click sphere (→ RED)     |
| 4    | `#lpOrb`  | target   | Click sphere (→ GREEN)   |
| 5    | `#lpOrb`  | next     | Read, hit Finish         |

`auto()` on steps 2–4: `document.getElementById('lpOrb').click()`.

Free-explore: each click cycles the env and calls `coach.freeSay('<b>ENV</b> — dir text')`.

Preview offered: step 1 `onEnter` (ORACLE tab preview).

Complete text: `'GREEN = press the trend · YELLOW = stay light · RED = play defense...'`

---

### 5.2 FLOW (lesson-flow.js) — 4 steps

Demo widget: full-width feed (`#lpFeed`) with filter chips (ALL / CALLS / PUTS) and 7 fixture rows.

| Step | Target           | Advance  | Action required                                      |
|------|------------------|----------|------------------------------------------------------|
| 1    | `#lpFeed`        | next     | Read, hit Next                                       |
| 2    | `#lpFlowRows`    | target   | Click any NVDA row (highlights `lp-frow--target`)    |
| 3    | `#lpFlowFilters` | target   | Click CALLS filter chip                              |
| 4    | `#lpFlowRows`    | checks   | Click all 3 cluster rows (need: `['c1','c2','c3']`)  |

Step 2: clicking an NVDA row calls `coach.say(rec.read, ...)` + `coach.unlockNext('hit Next when ready')`. Does NOT auto-advance; user reads then hits Next.

Step 4: each cluster row click increments `clustersSeen`; `coach.check('c' + Math.min(clustersSeen,3))`. After 3rd row: unlocks Next and offers FLOW tab preview.

Row expand mechanic: clicking a row toggles `.lp-frow-expand[hidden]`. In cluster step (step 4), `keepOthers=true` so rows stack side by side; otherwise collapses others first.

EXPLAIN keys: `row`, `sweep`, `block`, `score`, `cluster`, `filter`.

Complete text: `'You can read a tape now — prints, sweeps vs blocks, and the clusters...'`

---

### 5.3 SIGNALS (lesson-signals.js) — 4 steps

Demo widget: signal card (`#lpSig`) with levels rail and confidence gauge.

Fixture values (from `FIX.signal`):
- `tkr:'NVDA', dir:'bull', conf:85.0, confDelta:18.0, price:142.30, pct:1.4`
- `stop:118.00, entry:131.00, t1:148.00, t2:160.00, rr:2.3`
- Pick: `CALL · NVDA $145 · EXP Feb 12 · PREM $4.20 · STRIKE $145 · now $8.40 · gain +100.0%`

Rail layout formula:
```js
var lo = F.stop - 4;   // 114.00
var hi = F.t2   + 4;   // 164.00
var x = ((px - lo) / (hi - lo) * 100).toFixed(1) + '%';
```

Rail levels: STOP($118) | ENTRY($131) | LIVE($142.30) | T1($148) | T2($160).

Gauge arc: `stroke-dasharray = (conf * 0.75) + ' 100'` at 400ms delay.

| Step | Target        | Advance  | Action required                            |
|------|---------------|----------|--------------------------------------------|
| 1    | `#lpSig`      | target   | Click closed card to open it               |
| 2    | `#lpGaugeCard`| next     | Read confidence gauge text, hit Next       |
| 3    | `#lpRailWrap` | checks   | Click STOP, ENTRY, T1, T2 (need all 4)    |
| 4    | `#lpRR`       | next     | Read R:R explanation, hit Finish           |

Step 3 `need: ['stop','entry','t1','t2']` — clicking LIVE level is ignored (not in need[]).

`auto()` step 3: walks `['stop','entry','t1','t2']` in order, clicks first unseen; when all seen, calls `forceNext()`.

Preview offered: step 4 `onEnter` (ORACLE view).

EXPLAIN keys: `stop`, `entry`, `live`, `t1`, `t2`, `gauge`, `rr`, `card`.

Complete text: `'Module done — that card has no secrets left...'`

---

### 5.4 GEX (lesson-gex.js) — 4 steps

Demo widget: SVG gamma chart (`#lpGexSvg`) with draggable spot marker and market-state panel.

Fixture values (from `FIX.gex`):
- `ticker:'SPY', flip:5910, spotStart:5942`
- `callWall:6000, putWall:5860`
- `netGexPos:'+$1.8B', netGexNeg:'-$0.6B'`
- 8 strikes: 5840(−26), 5860(−34), 5880(−20), 5900(−12), 5930(+24), 5950(+36), 5970(+28), 6000(+44)

SVG coordinate system:
```js
var lo = 5820, hi = 6020;
var x = (strike - lo) / (hi - lo) * 600 + 20;  // maps to [20,620] in 640px viewBox
```

Bar rendering: `y = gex >= 0 ? mid - h : mid` where `mid=130, scale=1.9`. Colors: green `#00ffa3` for positive, red `#ff5b5b` for negative.

Spot drag: converts clientX → SVG coords via `svg.getScreenCTM().inverse()`, clamps to `[lo+10, hi-10]` = `[5830, 6010]`. Fires `lp:gexFlipCrossed` on every downward cross (wasPos && !isPos).

| Step | Target        | Advance  | Action required                                          |
|------|---------------|----------|----------------------------------------------------------|
| 1    | `#lpGexChart` | next     | Read, hit Next                                           |
| 2    | `#lpGexFlip`  | target   | Click the flip line (→ unlocks Next with explanation)    |
| 3    | `#lpGexSpot`  | event    | Drag spot below flip 5910 (fires `lp:gexFlipCrossed`)   |
| 4    | `#lpGexChart` | checks   | Click call wall (6000) and put wall (5860) bars          |

Step 2: click → `coach.say(EXPLAIN.flip, ...)` + `coach.unlockNext('hit Next when ready')`.

Step 3 `onEnter`: resets spot to `spotStart=5942`, shows animated drag hint ("DRAG ◀" arrow). `auto()`: `_setSpot(flip - 20 = 5890)` + dispatch `lp:gexFlipCrossed`.

Step 4: animated amber dashed outlines appear over call wall and put wall bars (`lpWallHintCall`, `lpWallHintPut`). Clicking each: removes its hint, calls `coach.check('call wall')` or `coach.check('put wall')`.

`need: ['call wall', 'put wall']`

Preview offered: step 4 `onEnter` (GEX tab preview).

EXPLAIN keys: `flip`, `posBar`, `negBar`, `callWall`, `putWall`, `state`, `spot`.

Complete text: `'Calm above the flip, chaos below, walls as magnets...'`

---

### 5.5 HEATMAP (lesson-heatmap.js) — 4 steps

Demo widget: two-layer heatmap grid (`#lpHmGrid`) with PRICE/FLOW toggle toolbar.

Tile sizing formula:
```js
var span = v / max > .6 ? ' lp-hmtile--big' : (v / max > .25 ? ' lp-hmtile--mid' : '');
var depth = Math.min(.34, .10 + (v / max) * .24);  // rgba opacity
```

Color: positive (call-heavy or green price) = `rgba(0,255,163,depth)`, negative = `rgba(255,91,91,depth)`.

FLOW sub-label format: `'$' + prem + 'M · ' + sweeps + ' sweeps' + (whales ? ' · N whales' : '')`.

| Step | Target        | Advance  | Action required                                       |
|------|---------------|----------|-------------------------------------------------------|
| 1    | `#lpHm`       | next     | Read PRICE layer, hit Next                            |
| 2    | `#lpHmToolbar`| target   | Click FLOW chip                                       |
| 3    | `#lpHmGrid`   | target   | Click NVDA tile (opens trade detail)                  |
| 4    | `#lpHmGrid`   | target   | Click TSLA tile (right answer); wrong answers get hint|

Step 4: clicking TSLA → opens detail + `coach.say('Right — TSLA, $21.4M in puts...')` + `coach.unlockNext('hit Finish when ready')`. Wrong ticker: `coach.say('Not that one — look for the red tile...')`.

Preview offered: step 3 `onEnter` (HEATMAP tab preview).

EXPLAIN keys: `price`, `flow`, `tile`, `unusual`, `layers`.

Complete text: `'PRICE = what happened, FLOW = what\'s being paid for...'`

---

### 5.6 RISK (lesson-risk.js) — 4 steps

Demo widget: position sizing calculator (`#lpRisk`) with range slider, 3 output cards, and quiz box.

Fixture values (from `FIX.risk`):
- `account:25000, defaultRiskPct:2.0`
- `entry:131.00, stop:118.00, wideStop:124.00`
- Slider: `min=0.5, max=10, step=0.5, value=2.0`

Sizing formula (exact):
```js
var loss   = account * pct / 100;        // = 25000 * 2.0 / 100 = $500
var dist   = entry - stop;               // = 131.00 - 118.00 = $13.00
var shares = Math.floor(loss / dist);    // = Math.floor(500/13) = 38
```

Wide-stop scenario (quiz1): if stop=124.00, dist=$7.00, shares=71 at 2% — but quiz asks conceptually (no separate fixture calculation).

| Step | Target            | Advance  | Action required                                      |
|------|-------------------|----------|------------------------------------------------------|
| 1    | `#lpRisk`         | next     | Read the calculator, hit Next                        |
| 2    | `#lpRiskSliderRow`| event    | Move slider (fires `lp:riskSliderMoved` internally)  |
| 3    | `#lpRiskQuiz`     | event    | Answer quiz 1 correctly (fires `lp:riskQuiz1`)       |
| 4    | `#lpRiskQuiz`     | event    | Answer quiz 2 correctly (fires `lp:riskQuiz2`)       |

Step 2: first slider move → `coach.say(...)` + `coach.unlockNext('hit Next when ready')`. If pct > 5: `'See it? At N% one loss erases weeks. I cap my playbook at 2%.'`

**Quiz 1:**
- Q: `'Your stop moves wider — same 2% account risk. Do you size UP or DOWN?'`
- Answer: `'down'`
- Options: `['up','SIZE UP'], ['down','SIZE DOWN']`
- Right: `'Down. Wider stop = more risk per share, so fewer shares carry the same $500 max loss...'`
- Wrong: `'Other way. Wider stop = more risk per share...'`

**Quiz 2:**
- Q: `'Which bleeds an account faster: one 10%-risk trade, or five 2%-risk trades that all lose?'`
- Answer: `'one'`
- Options: `['one','THE ONE 10% TRADE'], ['five','THE FIVE 2% TRADES']`
- Right: `'The single 10% hit — and it\'s not close psychologically...'`
- Wrong: `'Both lose 10% of the account — but the five 2% losses happen across five separate decisions...'`

Wrong answer: quiz stays open (no next unlock). Right answer: disables all buttons, unlocks Next, offers preview on quiz 2.

Preview offered: step 4 right-answer (ORACLE/plan view).

EXPLAIN keys: `slider`, `maxloss`, `stopdist`, `shares`.

Complete text: `'That\'s the whole course — tape, signals, gamma, heat, and the math that keeps you solvent...'`

---

## 6. Static Fixtures (fixtures.js)

All demo data in `window.MomoLearn.FIX`. **Zero live endpoints.** Shapes mirror live components.

### 6.1 FIX.signal

```js
{ tkr:'NVDA', dir:'bull', conf:85.0, confDelta:18.0, price:142.30, pct:1.4,
  stop:118.00, entry:131.00, t1:148.00, t2:160.00, rr:2.3,
  pick:{ type:'CALL', name:'NVDA $145', meta:'EXP Feb 12 · PREM $4.20 · STRIKE $145',
         now:'$8.40', gain:'+100.0%' },
  thesis:'AI infrastructure cycle accelerating; institutional call flow dominant on every retest.' }
```

### 6.2 FIX.flow — 7 rows

```js
{ id, tkr, side ('call'|'put'), kind ('CALL SWEEP'|'PUT BLOCK'|...), detail, ts, score, cluster (bool),
  spot, vol, oi, read }
```

Key rows:
- id 1: NVDA CALL SWEEP $145C FEB 12 $2.1M score:92 cluster:true ts:'14:02:11'
- id 3: NVDA CALL SWEEP $145C FEB 12 $3.4M score:94 cluster:true ts:'14:09:48'
- id 6: NVDA CALL SWEEP $145C FEB 12 $5.0M score:96 cluster:true ts:'14:16:33'
- id 2: TSLA PUT BLOCK $215P FEB 19 $1.8M score:71 cluster:false
- ids 4,5,7: AAPL CALL BLOCK, AMD PUT SWEEP, MSFT CALL BLOCK

### 6.3 FIX.gex

```js
{ ticker:'SPY', flip:5910, spotStart:5942, callWall:6000, putWall:5860,
  netGexPos:'+$1.8B', netGexNeg:'-$0.6B',
  strikes:[...8 entries...] }
```

### 6.4 FIX.heatmap

```js
{ summary:{ price:'Breadth · BULLISH', flow:'Flow · CALL-HEAVY' },
  tiles:[5 tickers: NVDA(cap:3.4,prem:48.2), MSFT, AAPL, TSLA(sent:'put',prem:21.4), AMD] }
```

### 6.5 FIX.risk

```js
{ account:25000, defaultRiskPct:2.0, entry:131.00, stop:118.00, wideStop:124.00,
  quiz1:{...}, quiz2:{...} }
```

---

## 7. Preview Mechanism (preview.js)

**Status: DEFERRED as of 2026-06-16 (MOM-361/MOM-418).** The `offer()` function has an early `return;` at its top — the preview chip never appears. The rest of the feature is dormant and restorable by deleting that early return.

### 7.1 When it would fire

Each lesson calls `window.MomoLearn.preview.offer(self.PREVIEW)` at its "aha" moment:
- Oracle: step 1 `onEnter`
- Flow: after 3rd cluster row read
- Signals: step 4 `onEnter`
- GEX: step 4 `onEnter`
- Heatmap: step 3 `onEnter`
- Risk: quiz 2 right answer

### 7.2 Preview config shape

```js
{ tab:'GEX', view:'gex', label:'Preview the GEX tab', caption:'html string' }
```

`tab` = active tab highlighted in the terminal nav strip (one of `['ORACLE','FLOW','HEATMAP','GEX']`).
`view` = one of `['flow','oracle','gex','heatmap','plan']`.

### 7.3 Chip + overlay flow

1. `offer(cfg)`: inserts `#lpPreviewRow` chip before `.lp-momo-ask` element. Two buttons: "▶ label" → `open(cfg)`, "Later" → collapses to ghost button.
2. `open(cfg)`: injects full-screen `#lpPvOverlay`. Frame contains: tab strip, coded terminal viewport, caption with "◎" avatar icon, "Got it" close button. Click backdrop or press Esc to close.
3. `clear()`: removes overlay AND the chip row. Called by `coach.start()` to reset between lessons.

### 7.4 Coded terminal views (VIEWS map)

All views are purely JS-rendered DOM/SVG mock-ups of the terminal (no screenshots). They share the same `MOMOEDGE · ORACLE/FLOW/GEX/HEATMAP` topbar rendered by `vp(tab, bodyHtml)`.

| view key | Content |
|----------|---------|
| `flow`   | Full-width feed, 4 filter chips, all 7 FIX.flow rows |
| `oracle` | 3-col: signal list left, selected NVDA signal center with rail + gauge, alerts/macro right |
| `gex`    | 2-col: SVG gamma bars + flip line left, MARKET STATE widget right |
| `heatmap`| Full-bleed grid: PRICE/FLOW/MAP/TABLE chips + 8-tile premium treemap |
| `plan`   | Oracle tab, trade-plan focus: rail + sizing cards (RISK 2.0% / MAX LOSS $500 / SIZE 38 sh) |

Note MOM-361 TODO: swap coded views for real captures once terminal tabs ship.

---

## 8. Auto-Launch & Re-Launch Logic

### 8.1 Auto-launch on first entry

The `learning.html` page itself IS the tutorial. Users arrive here either:
- **Post-checkout onboarding**: redirect from checkout-success to `/learning?flow=onboarding`
- **Terminal course gate**: modal on terminal that redirects to `/learning.html?return=terminal`
- **Direct/replays**: any visit

On load, `gate()` checks Supabase session, then calls `load(firstOpen())` which returns the first incomplete module.

### 8.2 Triggering from the terminal ("Tutorial button")

The terminal-init.js invokes `window.MomoEdge.courseGate.show()` when `learning_completed_at` is null (server check). To make this re-launchable as a voluntary "Tutorial" button:

1. Call `window.MomoEdge.courseGate.show()` directly — or navigate to `/learning.html` (landing resumes at current progress).
2. To force a full replay, navigate to `/learning.html#oracle` (hash overrides `firstOpen()`).
3. On the learning page, "Replay lesson" resets the coach for the current module without clearing localStorage.

### 8.3 Session gate (learning.html)

Session-only (not subscription) gate. On injected builds: checks `window._sbAuthClient.auth.getSession()` with an 8-second timeout Promise.race. If no session: `location.href = '/login.html?next=/learning.html'`. On local/un-injected builds (placeholder SB_URL or no `window.supabase`): gate is skipped entirely.

---

## 9. Completion Flow

When all 6 modules are done:
1. `doneCount() === ORDER.length` → calls `markCourseComplete()` → upserts `user_onboarding.learning_completed_at`.
2. Final module (`risk`) shows optional newsletter opt-in band before CTA.
3. CTA: `<a href="finalDest()">Enter the Terminal →</a>`
   - `?flow=onboarding` in URL → `/oracle-entry.html`
   - Any other case → `/terminal.html`
4. Newsletter insert: `sb.from('newsletter_subscribers').insert({ email, source:'learning' })`. Duplicate (PG error 23505) treated as success but skips welcome email.

---

## 10. Rebuild Checklist — Equivalent Guided Tour

To rebuild an equivalent tutorial for our options flow section:

### Required DOM elements on the host page
- `#lpSpot` — spotlight overlay div (position:absolute, CSS transition for movement)
- `#momoText`, `#momoHint`, `#momoStep`, `#momoChecks` — narrator bar slots
- `#momoBack`, `#momoNext` — navigation buttons
- `#momoInput`, `#momoSend` — optional AI chat (server-side)

### Coach API surface to implement
- `coach.start(steps, onComplete)` — begin lesson
- `coach.stop()` — reset all state
- `coach.say(html, {hint, step, free})` — narrator update
- `coach.freeSay(html)` — free-explore narrator
- `coach.check(key)` — mark a checks-step key
- `coach.advanceFromTarget()` — signal target was clicked
- `coach.forceNext()` — programmatic advance (from auto())
- `coach.unlockNext(hint)` — enable Next without advancing
- `coach.refreshSpot()` — recalculate spotlight on scroll/resize
- `coach.isDone()`, `coach.stepIndex()` — state queries

### Progress store interface
- localStorage key: choose your own (not the MomoEdge one)
- Schema: `{ modules: { [id]: { done: bool, completedAt: ISO } } }`
- Server flag: write to your equivalent of `user_onboarding` on all-complete

### Auto-launch trigger
- First visit: check server flag; if null, redirect to `/learning` (or inject inline tour)
- Re-launch button: navigate to `/learning#<first-module>` or call `coach.start()` directly

### Fixture data
- Create static JSON objects mirroring your live data shapes
- For options flow: replicate the 7-row tape with sweep/block/score/cluster/read fields
- For signals: replicate the levels rail (stop/entry/t1/t2 + confidence %)

### What is server-side only (not rebuildable from client JS)
- `/.netlify/functions/momo-ai` — AI chat streaming endpoint
- `user_onboarding.learning_completed_at` — Supabase table/column (RLS: user self-upsert)
- Session authentication (`window._sbAuthClient`, Supabase JWT)
- `/.netlify/functions/send-newsletter-welcome` — welcome email function
- The "entitled user" check that triggers the course gate (read from `user_onboarding` server-side)
