# GEX — Dealer Gamma Exposure Terminal — Canonical Build Spec

**Source surface:** MomoEdge terminal (momoedge.ai), GEX tab (`gex.html` + GEX market-state widget).
**Engine tell:** `ENGINE: SKYNET v2.2` / `SKYNET v3.2` (version varies across captures — see §6).
**Scope of this spec:** faithful reconstruction of the competitor's GEX surface from screenshot-analysis notes + the competitive study. No our-stack implementation mapping. Confidence flagged per item; unknowns collected in §7.

---

## 1. Surface Overview & Layout (desktop)

The GEX Terminal is one of five top-level modes in the "LIVE ORACLE TERMINAL": **ORACLE · FLOW · HEATMAP · GEX · PRISM**. GEX is a two-pane surface: a **strike ladder** (left, dominant) and a **market-state widget** (right rail). Per the competitive study, GEX is a split view of a `gex.html` iframe (left, the ladder) plus a GEX market-state widget (right), synced to the terminal ticker and PRISM ticker via `postMessage`.

**Vertical structure (top → bottom):**

1. **Global header bar** — `MOMOEDGE // LIVE ORACLE TERMINAL` branding (top-left); top-right cluster = green status dot + `STATUS: ENGAGED` badge + notification bell + user chip (`BL`).
2. **Mode tab bar** — `ORACLE | FLOW | HEATMAP | GEX (active/highlighted) | PRISM`; far-right pill button `GEX GUIDE`.
3. **Sub-header** — `GEX TERMINAL` label + ticker control row: ticker input (e.g. `SPY`), live price + change (`751.28 +4.06 (0.97%)`), and a row of expiry filter chips.
4. **Summary metrics bar** — a horizontal strip of computed levels: `NET GEX (+42% VISIBLE): +1367.1M`, `CALL WALL: 760`, `HVL: 750`, `PUT SUPPORT: 740`, `P/C RATIO: 2.03`, `CALL OI: 2.0M`, `PUT OI: 4.0M`.
5. **Legend / color-key row** — colored dots for Positive GEX, Negative GEX, Call Wall, Magnet-HVL, Gamma Flip + a `HOW TO READ ▼` toggle.
6. **Main body — two panes:**
   - **LEFT: strike ladder** — vertical list of strikes; each row = one strike with horizontal bar(s) (left = negative/red, right = positive/teal) and a signed dollar value on the right (`+421.4M`, `-387.0M`). Scrollable along the price axis. Key strikes get colored badges/row-highlights (Magnet, Flip, Call Wall). One capture ("scroll down 2") shows the ladder split into **two side-by-side bar columns per strike, headed `ORACLE` and `FLOW`** — a dual-source GEX rendering (proprietary model vs live flow).
   - **RIGHT: market-state rail** — `<TICKER> MARKET STATE` card: large state label (TRANSITION/RANGE/CASCADE/DRIFT/PIN…), one-line thesis, `STRUCTURAL RANGE`, `WHAT IF FLIP BREAKS?` (three scenario boxes), `REGIME`, then metric cards `GRAVITY`, `γ POLARITY`, `HEDGE PRESSURE`, `PIN TARGET`, and a collapsible `ASK ORACLE` accordion.
7. **Footer status bar** — `● ORACLE ONLINE | UPTIME: 00:06:36 | SIGNALS: 5 ACTIVE | STALE: ~32s ago | ENGINE: SKYNET v2.2`.

**Mobile evidence:** The competitive study (not the screenshots) states the mobile terminal promotes GEX to first-class navigation with a "GEX pane: ticker search, market-state card, structural range rail, telemetry, Ask Oracle, embedded chart." No GEX mobile screenshots were captured; treat mobile layout as inferred.

---

## 2. Complete Control Inventory

| Control | Type | Options / values observed | Behavior (observed / inferred) |
|---|---|---|---|
| **Mode tabs** | Tab bar | ORACLE, FLOW, HEATMAP, GEX, PRISM | Switch top-level terminal surface. GEX highlighted when active. |
| **Ticker input** | Text input / search | `SPY`, `NVDA`(~194.70), `QQQ?`(~720.34), `COIN`(~169.02), `JNJ`(~260.30) | Sets the analyzed symbol; drives price, ladder, summary bar, market state. Synced to terminal + PRISM ticker via `postMessage`. Works on ETFs and single names. |
| **Price display** | Read-only | `751.28 +4.06 (0.97%)` | Live last / abs change / pct change for selected ticker. |
| **Expiry filter chips** | Chip row (multi/toggle) | `ALL` (default selected), plus per-date chips `YYYY-MM-DD` (2025-07-07 … 2025-07-18), and mode chips seen: `CLOSEST`, `EXPIRY`, `LOTS`. | Filters the option chain feeding GEX by expiry. `ALL` = all expiries aggregated. Individual dates selectable. `CLOSEST` likely = nearest expiry; `EXPIRY` / `LOTS` semantics unconfirmed (§7). |
| **"all expiries" dropdown** | Dropdown | Vertical list of expiry dates (`YYYY-MM-DD`) | Opens a full list of available expiries to pick from (alternative to chips). |
| **`40%` chips** | Chips (×3 recurring) | `40%` shown 2–3× per capture | Recurring percentage chips of unconfirmed meaning — likely a "% of GEX visible / strike-range width / concentration filter" control. NET GEX header shows a paired `(+42% VISIBLE)` readout, strongly implying these chips set the **visible fraction** of the chain rendered (see §6/§7). |
| **GEX GUIDE** | Pill button (top-right) | — | Opens the education/glossary overlay (distinct from the inline `HOW TO READ`). |
| **HOW TO READ ▼** | Toggle in legend row | expanded / collapsed | Expands an inline guide panel of 6 concept cards (definitions in §4). |
| **ASK ORACLE** | Accordion header (right rail) | expanded / collapsed; has `×` close button when open | Expands a list of ~10 pre-built GEX question chips (§5). Not a modal — inline collapsible. |
| **Ask Oracle question chips** | Clickable prompt items | 10 prompts (verbatim §5) | Click sends a GEX-context question to the Oracle AI assistant. |
| **Strike ladder scroll** | Scroll region | — | Pans the ladder up/down the price axis to expose strikes above/below spot. |
| **Watchlist selector** (peripheral) | Dropdown + `+` + `...` | `Default ▼` watchlist; columns SYMBOL / LAST / CHG% | A watchlist/symbol picker captured in the GEX batch; may be a shared terminal sidebar rather than GEX-specific. Rows clickable to select symbol; LAST/CHG% show `—` until priced. |

**Sort / view modes:** No explicit sort control observed. The ladder is implicitly sorted by strike (descending, high strikes at top). No table/chart view-mode toggle beyond the dual `ORACLE`/`FLOW` bar columns (which appear to be a rendering mode, not a user toggle — unconfirmed §7).

---

## 3. Data Model — Displayed Fields

### 3.1 Header / ticker
| Field | Type / units | Semantics |
|---|---|---|
| ticker | string | Selected symbol (ETF or single name). |
| price | float, price | Last traded price. |
| change_abs | float, price | Absolute change on day. |
| change_pct | float, % | Percent change on day. |
| status | enum | `ENGAGED` (green) — session/engine engaged. |

### 3.2 Summary metrics bar
| Field | Type / units | Semantics |
|---|---|---|
| NET GEX | signed $M (can be $B) | Aggregate net dealer gamma exposure across visible chain. Header appends `(+N% VISIBLE)` = fraction of total GEX rendered. Observed: `+2595.5M`, `+1367.1M`, `+1497.5M`, `+1587.1M`, `-306.4M`, `+38.9M`, `+28.3M`. Colored teal when positive. |
| CALL WALL | strike (int) | Strongest call-gamma/OI strike above spot; acts as ceiling. Yellow. |
| HVL | strike (int) | High-Volume Level / magnet strike price gets pulled toward. Purple. Can coincide with CALL WALL. |
| PUT SUPPORT | strike (int) | Strongest put-gamma/OI strike below spot; acts as floor. |
| P/C RATIO | float | Put/Call ratio. Observed 0.53, 0.77, 1.09, 1.30, 2.03, 2.08. |
| CALL OI | count (M) | Total call open interest (millions). |
| PUT OI | count (M) | Total put open interest (millions). |

### 3.3 Strike ladder (per row)
| Field | Type / units | Semantics |
|---|---|---|
| strike | float | Strike price; whole-dollar and 0.5 increments seen (743.5, 742.5) for index-like names. |
| gex_value | signed $M/$B | Net GEX at that strike. Bar length ∝ magnitude; sign = direction (teal right = +, red left = −). |
| gex_oracle / gex_flow | signed $ (dual col) | In dual-source view: left bar column = `ORACLE` (model), right = `FLOW` (live flow). |
| level_badge | enum tag | Optional per-strike tag: `MAGNET` (orange), `FLIP` (red), `CALL WALL` (yellow), row-highlight for key strikes. |
| row_highlight | color band | Marks flip/wall strikes (red/orange full-row tint). |

Axis/legend labels near ladder: `# STRIKES`, `IN RANGE`; bottom labels `−STRIKES−`, `<TICKER> PINS` (e.g. `COIN PINS`).

### 3.4 Market-state rail
| Field | Type / units | Semantics |
|---|---|---|
| market_state | enum | One of PIN, DRIFT, RANGE, TRANSITION, TREND, CASCADE (§4). Large colored label. |
| thesis | string | One-line generated trading thesis (state-specific, §4). |
| STRUCTURAL RANGE / RANGE-STRUCT | `low — high` strikes | Computed structural price range (e.g. `764 — 756`, `195 — 196`, `259 — 264`). |
| WHAT IF FLIP BREAKS? | 3 scenario boxes | Three labeled levels, e.g. `740 (PUT SUPP / BUY SUPP)`, `750 (FLIP / FLIP-MAN)`, `760 (CALL WALL)`. Labels vary: `FLIP/MAGNET`, `MARKET`, `CALL WALL`. |
| REGIME | indicator | Regime label on right edge (regime confidence per study). |
| GRAVITY | two signed % | Paired values, e.g. `+82% / -80% ↓`, `+44% / +41%`. Likely up-gravity vs down-gravity pull toward magnet. |
| γ POLARITY | enum + % | `LONG γ DOMINANT` (white) or `SHORT γ DOMINANT` (red) + a % (e.g. `56%`). Sub-text: "Net dealer gamma regime." % = share of GEX that is positive/dominant polarity. |
| HEDGE PRESSURE | enum + detail | `HIGH` (orange) / `LOW` (green). Sub-text: "Size of dealer hedging flow." Detail: `(last γ: ~$1,298)` / `(last 24h: 51%)`. |
| PIN TARGET | strike + prob | e.g. `780` + `31% prob`. Sub-text: "Strike dealers pin toward." / "Strike Gaussian pin toward" / "Pin theta distribution center." |

### 3.5 Footer telemetry
| Field | Type | Semantics |
|---|---|---|
| oracle_online | bool | `● ORACLE ONLINE`. |
| uptime | HH:MM:SS | Live session timer. |
| signals_active | int | `5 ACTIVE` / `6 ACTIVE`. |
| stale | duration | Data freshness `~32s ago`. |
| engine | string | `SKYNET v2.2` / `v3.2`. |

---

## 4. Scoring / Legend / Tier Semantics (verbatim where transcribed)

### 4.1 Legend color key (verbatim dots)
- **Positive GEX** — blue/teal dot
- **Negative GEX** — red dot
- **Call Wall** — yellow dot
- **Magnet-HVL** — purple/violet dot
- **Gamma Flip** — orange dot
- **Net γ Positive** — blue dot (same as Positive GEX)

### 4.2 GEX GUIDE / HOW TO READ concept definitions (verbatim)
- **GEX (Gamma Exposure):** "A map of where the biggest options bets sit, and where dealer hedging is likely to push or pin price."
- **Call Wall:** "A ceiling. Price often stalls into it as dealers sell into rallies."
- **Put Support:** "A floor. Selloffs slow here as downside protection cushions the drop."
- **Magnet (HVL):** "The high-volume level price gets pulled toward and pins."
- **Gamma Flip:** "Below it, hedging amplifies moves and volatility rises."
- **Net γ Positive:** "Above the flip: a calm, mean-reverting, range-bound regime."

### 4.3 Market-state taxonomy (enum + observed thesis strings)
Six states inferred (competitive study §21 lists **PIN, DRIFT, RANGE, TRANSITION, TREND, CASCADE**). Observed in screenshots: 5 of 6 (TREND not captured).

| State | Color | Observed thesis (verbatim / partial) |
|---|---|---|
| **TRANSITION** | yellow/gold | "Near gamma flip at 750. Regime shift possible. Reduce size." |
| **RANGE** | white | "Flip at 193 has broken to the upside (past 1.22x above). Trading at TRANSITION — below 194, do not fade. Regimes downgrade at 193.52 on a sustained close-above flip." |
| **CASCADE** | red/orange | "Deep negative γ. Fragile structure. Sharp moves likely on limit breaks." |
| **DRIFT** | white | "Scattered γ mix. Positive positioning — no reliable flip detected in current chain." |
| **PIN** | white | "Dealers stabilizing near magnet. Fade extremes inside band. No edge trading [~259] the band around 259 flip." |
| **TREND** | (not captured) | — |

### 4.4 Polarity / pressure tiers
- **γ POLARITY:** `LONG γ DOMINANT` (positive-gamma regime, white) vs `SHORT γ DOMINANT` (negative-gamma regime, red). Percentage = dominance strength.
- **HEDGE PRESSURE:** two-tier `HIGH` (orange) / `LOW` (green) — magnitude of dealer hedging flow.

---

## 5. States & Interactions

- **Ask Oracle prompts (verbatim, 10):**
  1. Any structural events?
  2. What if I'm long?
  3. What if I'm short?
  4. Why range-bound?
  5. Will walls hold?
  6. Where are the real edges?
  7. How to trade this?
  8. How wide is the range?
  9. Where does trade fail?
  10. RANGE vs PIN — same idea?
  - Accordion header `ASK ORACLE` (teal accent) with expand/collapse chevron; `×` close inside body; prompt rows have teal bullet dots on lighter dark cards.
- **GEX GUIDE overlay / HOW TO READ:** expands 6 concept cards (§4.2) with colored dot + bold title + one-sentence definition. Read-only, no interactive elements. Guide can be open simultaneously with Ask Oracle.
- **Hover:** not directly captured. Ladder rows presumably tooltip per-strike GEX/OI (inferred, §7).
- **Empty / fallback states:** DRIFT state = "no reliable flip detected in current chain" is the empty-structure case (positive positioning but no clean flip → multiple candidate flip labels on ladder). Watchlist LAST/CHG% show `—` / `—%` until priced.
- **Live update:** footer uptime timer runs; `STALE ~30-32s ago` implies polling refresh cadence ~30s. State/values change between near-identical captures (NET GEX 1497.5M → 1587.1M), confirming live re-render.
- **Keyboard shortcuts:** none observed (§7).
- **Color-state coupling:** state label color encodes risk (yellow=TRANSITION caution, red=CASCADE danger, white=stable RANGE/DRIFT/PIN); hedge pressure color inverts (orange=HIGH risk, green=LOW).

---

## 6. Engine Inferences (thresholds / formulas / components)

From screenshots + competitive study §20–22 (`gex_engine.py`/`gex_model.py` analogue, "GEX analytics/regime classifier"):

- **Per-strike GEX:** call/put OI × volume × gamma → net GEX per strike; **Black-Scholes gamma fallback** when chain greeks missing. Units = dollar gamma ($M/$B, "$ per 1% move" notional).
- **Call Wall** = strongest call gamma/OI strike above spot. **Put Support** = strongest put gamma/OI below spot. **HVL/Magnet** = strike by total OI + average gamma + proximity. **Gamma Flip** = cumulative net GEX zero-crossing or recomputed gamma profile.
- **Regime classifier** → {PIN, DRIFT, RANGE, TRANSITION, TREND, CASCADE}. Coincidence rule observed: when CALL WALL = HVL = PUT SUPPORT (all 260 for JNJ) → **PIN**; deep negative net GEX + fragile structure → **CASCADE**; no clean flip + positive mix → **DRIFT**.
- **Flip-break thresholds (verbatim tells):** "past 1.22x above" (flip-multiplier ratio computed), "Regimes downgrade at 193.52 on a sustained close-above flip" (numeric regime-transition trigger), "below 194, do not fade" (state-specific advice level). Structural detector (study §22): **~1% proximity to flip, ~2% proximity to walls** as trigger thresholds.
- **γ POLARITY %** = share of GEX in dominant sign (e.g. 56% long). **NET GEX (+N% VISIBLE)** = fraction of total chain GEX currently rendered — the `40%` chips likely set this visible fraction / strike window.
- **GRAVITY (two %)** = up-pull vs down-pull toward magnet (`+82% / -80% ↓`). **HEDGE PRESSURE** = scalar dealer hedging-flow size with a dollar reference `(last γ: ~$1,298)`.
- **PIN TARGET** = probabilistic pin via **Gaussian/theta distribution over strikes** → strike + `31% prob`. "Strike Gaussian pin toward" / "Pin theta distribution center."
- **Snapshot diffs (study §21):** level shifts, OI deltas, new/exit OI clusters, liquidity expansion/drain, flow direction — feed the `SIGNALS: N ACTIVE` count.
- **Data source:** `uw-chain` option-chain endpoint + price endpoint + cached/live GEX snapshots (Supabase) + computed-grid fallback. Dual `ORACLE`/`FLOW` ladder columns = model-vs-flow reconciliation.

---

## 7. Gap List — Unknowns for Builder / Source-Code Confirmation

1. **`40%` chips** — exact meaning (visible-fraction? concentration threshold? strike-window width?) and whether the value is user-adjustable or a preset set. NET GEX `(+42% VISIBLE)` correlation strongly suspected but unconfirmed.
2. **Expiry chip modes** `CLOSEST` / `EXPIRY` / `LOTS` — precise semantics and whether they are mutually exclusive with `ALL` / date chips.
3. **Dual `ORACLE`/`FLOW` ladder columns** — is this a user toggle, an always-on dual render, or a specific view state? Only one capture shows it.
4. **Sort/view controls** — no explicit sort or view-mode toggle observed; confirm whether ladder ordering or bar-scaling is user-configurable.
5. **TREND state** — 6th regime per study but never captured; need its thesis string, color, and trigger rule.
6. **Hover/tooltip behavior** on ladder rows and metric cards — content (per-strike OI/gamma breakdown?) unconfirmed.
7. **GRAVITY** — exact definition of the two paired percentages and the `↓` arrow (which is up vs down; sign convention when both positive `+44% / +41%`).
8. **HEDGE PRESSURE detail line** varies (`last γ: ~$1,298` vs `last 24h: 51%`) — the underlying metric and its units/reference need confirmation.
9. **PIN TARGET numbers** occasionally read far from spot (e.g. "660/675 zone" on a ~169–260 name) — likely OCR error or a secondary distribution readout; confirm.
10. **Ask Oracle response format** — chips send questions but the AI answer surface (inline card? modal? streaming?) is not captured. Prompt set may be state-dependent (only 3 shown in some captures).
11. **Keyboard shortcuts** — none observed; confirm existence.
12. **Refresh cadence** — `~30s stale` implies ~30s polling; confirm exact interval and whether push/websocket.
13. **Strike granularity / range window** — how many strikes rendered, centering rule around spot, and 0.5 vs 1.0 increment selection logic.
14. **Engine version drift** — `SKYNET v2.2` vs `v3.2` across captures; confirm which is current and whether behavior differs.
15. **Watchlist panel** — whether it's GEX-owned or a shared terminal component (columns SYMBOL/LAST/CHG%, `Default` list, `+`/`...` actions).
16. **`STRUCTURAL RANGE` vs `RANGE-STRUCT` vs `WHAT IF FLIP BREAKS?`** — confirm these are distinct computed artifacts (structural band vs scenario levels) and their exact formulas.
17. **Mobile GEX layout** — only described in study, no screenshots; confirm pane order and which controls survive.
