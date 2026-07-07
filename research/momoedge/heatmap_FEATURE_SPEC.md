# MomoEdge Heatmap — Canonical Feature Specification

**Surface:** "HEATMAP" tab of MomoEdge // Live Oracle Terminal (momoedge.ai)
**Purpose:** Dual-layer market heatmap — a **PRICE layer** (performance treemap) and a **FLOW layer** (options-premium treemap) over the same sector-grouped tile canvas, plus a tabular equivalent, filters, and hover/detail read-outs.
**Sources:** `/tmp/momoedge_specs/raw/heatmap_1.md`, `/tmp/momoedge_specs/raw/heatmap_2.md` (15 screenshots, single live session, market-closed EOD data). Cross-referenced with §19, §26, and Lane 6 of the internal competitive study.

> Fidelity note: This spec describes the competitor product as observed. Screenshot text was partially occluded/low-res; every uncertain read is flagged inline and consolidated in §7 (Gap list). No implementation mapping to our stack is included.

---

## 1. Surface Overview & Layout (desktop)

The Heatmap is one of five primary terminal modes. Top-to-bottom chrome:

1. **Top bar** — Logo "MOMOEDGE // LIVE ORACLE TERMINAL" (left); "STATUS ENGAGED" indicator + user/account icons (right); **"HEATMAP GUIDE"** button (far right).
2. **Primary nav row** — `ORACLE | FLOW | HEATMAP | GEX | PRISM`. HEATMAP active.
3. **Sub-header / summary strip** — a **mode label** (color-coded) with an inline **red/green breadth bar** and two summary metrics. The label and metrics change by active layer:
   - PRICE layer: mode ∈ `MIXED` (amber/green) | `BULLISH` (green) | (implied `BEARISH`); shows `<breadth%> … <aggregate return%>` e.g. `BULLISH (Breadth) 65% … +15.75%`.
   - FLOW layer: mode ∈ `CALL-HEAVY` (amber/green) | `MIXED` (amber) | (implied `PUT-HEAVY`); shows `<call-share%> … <total premium $>` plus standout callouts e.g. `CALL-HEAVY 62% … $195.0M. But: DDOG MSFT then: CISCO GE` and, in TABLE, `Bull [<tickers>]` / `Bear <ticker> <n>$`.
4. **Layer + view + filter row** — leftmost segment is the **layer/view switcher** `PRICE | FLOW | MAP | TABLE | CAP`; to its right, a context-dependent set of filter chips (differs PRICE vs FLOW — see §2). Includes the **SEARCH TICKER…** box (right).
5. **Sector chip / tab row** — one chip per GICS-style sector, each with a live suffix value that changes by layer/mode/timeframe (see §2/§3). In TABLE view this row renders as horizontal **sector tabs** with an `ALL` tab.
6. **Main canvas** — the treemap (MAP/heatmap) or the data table (TABLE).
7. **Bottom status/hover bar** — left: live **hover read-out** of the tile/row under cursor (2–3 fields); right: **engine telemetry** `ORACLE ONLINE | UPTIME: hh:mm:ss | SIGNALS: <n> ACTIVE | STALE: <age> | ENGINE: SKYNET v3.2`.

**Timeframe controls** `1D | 1W | 1M | YTD` sit at the top-right of the canvas/filter area (raw notes twice mis-transcribed as `1H | 1H | 1W | YTD`; the canonical set inferred from later frames and the study is **1D | 1W | 1M | YTD**).

**Mobile:** No mobile screenshots captured. Unknown (see §7).

---

## 2. Complete Control Inventory

### 2.1 Layer / View switcher (`PRICE | FLOW | MAP | TABLE | CAP`)
This single segmented control conflates two orthogonal axes (a builder should treat them as two):
- **Data layer:** `PRICE` (color = price change) vs `FLOW` (color = call/put flow bias). Mutually exclusive.
- **Render view:** `MAP` (treemap) vs `TABLE` (sortable list). Mutually exclusive.
- **CAP:** appears in the switcher row and again as a sizing chip. Interpreted as a **tile-sizing mode = market-cap-weighted** (see EQUAL below). May double as a distinct rightmost control; role uncertain (§7).

Any layer × any view is reachable (observed: PRICE+MAP, PRICE+TABLE, FLOW+MAP, FLOW+TABLE).

### 2.2 Tile-sizing chips
- **CAP** — size tiles by **market capitalization** (PRICE layer default) or, in FLOW layer, sizing can flip to premium (see PREMIUM).
- **EQUAL** — size all tiles **equally** (one stock = one equal cell); produces the dense full-market grid. Highlighted when active. In MAP/PRICE this yields the "every stock" density view.
- **PREMIUM** — (FLOW layer only) size tiles by **options premium dollar volume**. PREMIUM and CAP are a two-way sizing toggle inside the FLOW layer.
- **CB** — a chip labeled `CB` carrying a signed numeric value, e.g. `CB +3.53 → +3.55 → +3.59` (increments live during session). Rendered with a clearable `×`. Interpreted as **Cap-Balance / breadth balance metric** — a live computed cap-weighted breadth number, also usable as an active filter (the `×` clears it). Exact definition unknown (§7).

### 2.3 Timeframe (PRICE layer)
`1D | 1W | 1M | YTD` — selects the return window the color encodes and drives the summary breadth/return metrics. Observed values by frame: 1D, 1W (`87% … +2.43%`), YTD (`86% … +0.76%`).

### 2.4 FLOW-layer-specific chips
- **ALL FLOW** — flow-direction filter. Inferred options: `ALL FLOW | CALL FLOW | PUT FLOW` (only `ALL FLOW` observed).
- **ALL / UNUSUAL** — universe/quality filter (mutually exclusive):
  - `ALL` — all optionable names with flow.
  - `UNUSUAL` — restrict to names flagged **unusual** by the engine (collapses canvas to ~8 tiles; §6). Distinct filter, not a sort.
- **DTE / expiry-range chips** — days-to-expiration buckets. Bucket set **changes with the active filter**:
  - Under `ALL`: `1D | 1-30d | 20d+` (also seen `1-30d | 30d+`).
  - Under `UNUSUAL`: `0-7d | 7-30d | 30d+`.
  - Selection behavior (single vs multi-select) unknown (§7).
- **Intraday time-snapshot chip** — e.g. `4:59 PM`, `4:30 PM`, `4:25 PM`, `4:29 PM`, `1:13`. Selects an **EOD/intraday snapshot time** for the flow data. In the TABLE variant appears as a time chip alongside DTE.
- **OTM % range chips (TABLE/FLOW)** — `0-7% | 7-35% | 7-45% | 7-74%` observed. Interpreted as **out-of-the-money percentage bands** for the strikes included. Range set appears dynamic/mislabeled across frames (§7).
- **MATRIX / RETS / OTC-UNUSUAL toggle** — a sub-row in the FLOW/TABLE view with `MATRIX | RETS | REAL E | OTC/UNUSUAL` plus a repeat of the sector labels. Interpreted as a **secondary display-mode selector** (matrix layout vs returns vs unusual-only), with sector sub-tabs. Semantics uncertain (§7).

### 2.5 Sector chips / tabs
Full sector set (labels truncated in UI; canonical expansion):
`TECH | COMM (Communication) | CONS D / CONS DISC (Consumer Discretionary) | CONS G / STAPLE (Consumer Staples) | FINANCE | HEALTH | ENERGY | INDUST (Industrials) | MATERI (Materials) | UTILITY | REAL E (Real Estate)`.
- In **MAP** view: chips act as **sector highlight/filter** and carry a **live suffix value** (`×0`, `×+2`, `×+4.2`, `×+27B`, `×+279`, `×+11.8`, `×+74`, `×+1.3`) — interpreted as per-sector aggregate (flow $ or bullish-signal count / net breadth), which recomputes by layer × mode × timeframe. Exact unit unknown (§7).
- In **TABLE** view: chips become **sector tabs** with an `ALL` tab (default active) that filter table rows. Extra labels seen: `SPLIT`, `COVID D`, `COMM I`, `COMM D`, `DONEG` — likely OCR artifacts of the standard sectors (§7).

### 2.6 Search & other
- **SEARCH TICKER…** — free-text ticker filter/lookup (right of filter row). Behavior on match (highlight vs isolate) unknown (§7).
- **Exchange/index chip** — a top-right label toggles among `AMEX`, `NDXA`/`NDXGS` (Nasdaq), possibly `NYSE`. Interpreted as an **exchange/index universe filter**. Presence intermittent; role uncertain (§7).
- **Column sort (TABLE)** — headers sortable; observed `Premium ▼` (descending). PRICE-TABLE appears sorted by timeframe %Chg descending (top rows +362%, +347%).

---

## 3. Data Model (displayed fields)

### 3.1 PRICE-layer tile
| Field | Type / units | Semantics |
|---|---|---|
| Ticker | string | Symbol shown in tile. |
| Price change % | signed % | Return over active timeframe; drives color. |
| Tile size | area | = market cap (CAP) or equal (EQUAL). |
| Sector | categorical | Placement region in treemap. |

### 3.2 FLOW-layer tile
| Field | Type / units | Semantics |
|---|---|---|
| Ticker | string | Symbol. |
| Premium $ | USD (e.g. `$28.9M`, `26.9M`, `~4M`) | Options premium dollar volume; drives tile size when PREMIUM sizing. |
| Flow direction | categorical (green=call / red=put) | Net call vs put bias; drives color (teal/cyan seen for CALL-HEAVY state — possibly a distinct call accent). |
| Price change % | signed % | Same-period price move, shown inside box (e.g. `NVDA +6.48`). |
| Tile size | area | = premium (PREMIUM) or market cap (CAP) or equal (EQUAL). |

### 3.3 PRICE-layer TABLE columns
Ticker | Company name | Sector(?) | **Col4 numeric** (2016 / 600 / 8090 / 4348 … — likely market cap $M or volume; ambiguous §7) | Price ($) | **Chg%** (green positive) | Vol/secondary metric | **Sparkline** (mini price chart, green/red).
Sort: %Chg descending default.

### 3.4 FLOW-layer TABLE columns
| Col | Field | Type / units | Notes |
|---|---|---|---|
| 1 | Ticker + direction arrow | string + ↑/↓ | ↑ green = call-heavy, ↓ red = put-heavy. |
| 2 | Company name | string | e.g. "Lam Research". |
| 3 | **Premium ▼** | USD $M | Total flow premium; default sort desc. |
| 4 | Chg% | signed % | Same-day price change, green/red. |
| 5 | **Score** | float ~0.00–5.91 | Flow intensity / unusualness score (see §6). Near-0 = baseline; 3–6 = elevated. |
| 6 | **Rank** | integer | Two scales seen: 0–100 percentile (90s, e.g. 96/99) in file 2, and small ints 5–62 in file 1 — likely two different fields conflated (§7). |
| 7 | Sentiment / bar | categorical + color | Red/green pill or bar. |
| 8 | **Analytics / annotation** | categorical label | Tier labels incl. `Baseline`; higher tiers implied ("Unusual"/"Extreme"). Header reads `Analytics`. |

### 3.5 Summary strip metrics
| Field | Layer | Meaning |
|---|---|---|
| Mode label | both | Market-mood classifier: PRICE `{MIXED, BULLISH, BEARISH?}`; FLOW `{CALL-HEAVY, MIXED, PUT-HEAVY?}`. |
| Breadth % | PRICE | % of names positive / above threshold (e.g. 65%, 86%, 87%). Labeled "(Breadth)" in MAP. |
| Aggregate return % | PRICE | Cap/equal-weighted aggregate move (e.g. +0.76%, +2.43%, +15.75%). |
| Call share % | FLOW | % of premium that is call-side (e.g. 62%, ~92%). |
| Total premium $ | FLOW | Market-wide premium in filter (e.g. $195.0M, $105.1M, $84.66M). |
| Standouts | FLOW | `But: <tickers> then: <tickers>` and `Bull […]` / `Bear <ticker> <n>$` — notable unusual names. |

### 3.6 Bottom hover / status read-outs
- PRICE hover: `Hovering: <TICKER> <±%>` (2 names) + `<TICKER> <n>x` (a multiplier, e.g. `AAL 12x`, `13x` — unusual-activity multiple, §6).
- PRICE MAP hover: `Impact ↓: <TICKER> +147.0%` / `Impact ↑: <TICKER> +58.8%` / `Active: <TICKER> 13x` — directional top-impact names + active multiplier.
- FLOW hover: `Top Flow: <TICKER> $<n>M` or `Top Premium: <TICKER> $<n>M` + `<TICKER> ♦` (pivot/diamond marker).
- FLOW TABLE bottom: `Top Premium: AMD $29.5M` + `Pivot: NVDA 0`.
- Telemetry: `UPTIME` (hh:mm:ss, live), `SIGNALS: n ACTIVE` (dynamic 5/6/8), `STALE: <age>` (from `~11m ago` to `~329s ago` to `17ms ago`), `ENGINE: SKYNET v3.2`, `⚑ MARKET CLOSED` flag.

---

## 4. Scoring / Legend / Tier Semantics

**Color legend (both layers):**
- PRICE: **green = positive**, **red = negative**, dark/near-black = flat; saturation ∝ magnitude.
- FLOW: **green/teal = net call-biased**, **red = net put-biased**, dark = no significant flow; intensity ∝ bias strength. In FLOW MAP, most tiles are dark (flow concentrated in few names) — the visual signature that distinguishes the flow layer from price.

**Tile-size legend:** area ∝ market cap (CAP) | premium $ (PREMIUM) | uniform (EQUAL).

**Mode classifiers (discrete, session/market-wide):**
- PRICE: `BULLISH` / `MIXED` / (`BEARISH`) — set by breadth.
- FLOW: `CALL-HEAVY` / `MIXED` / (`PUT-HEAVY`) — set by call vs put premium share (CALL-HEAVY seen at 62% and ~92%).

**Flow Score tiers (Col5 / Analytics):** float score with a categorical tier label. Only `Baseline` transcribed verbatim (RTX, score 0.00). Observed score→label pattern: ~0.00 → `Baseline`; 3.24–5.91 → elevated/unusual tier (label not transcribed). No verbatim legend copy captured — the **HEATMAP GUIDE** is the canonical source (§5, §7).

**Unusual multiplier (`<n>x`):** hover/bottom-bar field (`AAL 12x`, `13x`) — a volume-vs-baseline multiple flagging unusual activity.

---

## 5. States & Interactions

- **Hover:** bottom bar updates live with the hovered tile's fields (see §3.6). Per-tile tooltip likely but not captured.
- **Click-through:** study §19 states click-to-detail opens a **detail panel** with: price, change, market cap, volume, relative strength, rank, flow premium, bull/bear premium, sentiment, sweeps, whales, unusual count, flow intensity, average DTE, badges, call/put volume, OI, volume P/C, IV, divergence, and flow trades. **No detail-panel screenshot was captured** — fields are from the study, not observed (§7).
- **Empty / sparse state:** `UNUSUAL` filter collapses the MAP to ~8 tiles over a dark canvas; empty sectors render as faint labeled outlines. TABLE+UNUSUAL can show as few as 2 rows (AMD, NVDA).
- **Guide overlay:** **HEATMAP GUIDE** button opens an in-app guide covering price vs flow layers, tile sizing, timeframes, views, DTE filters, unusual filter, search, hover/click, and divergences (per study §26). Overlay content not captured (§7).
- **Live/stale states:** session shows live UPTIME counter, dynamic SIGNALS count, and a STALE freshness field that degrades when the feed lags (11m → 329s) and recovers when fresh (17ms). `⚑ MARKET CLOSED` shown EOD.
- **Keyboard shortcuts:** none observed (§7).

---

## 6. Engine Inferences (thresholds / formulas / components — observed or implied)

- **Dual-layer core:** same tile universe, two encodings. PRICE = color(price Δ) × size(cap|equal). FLOW = color(call/put net bias) × size(premium|cap|equal). The **divergence** (price up but flow put-heavy, or vice-versa) is the intended read (study §19, §516).
- **Breadth %:** PRICE mode threshold = share of names with positive return over timeframe (labeled "(Breadth)").
- **Mode classifier:** CALL-HEAVY when call premium share exceeds a cutoff (62% and 92% both classified CALL-HEAVY, so cutoff ≲ 60%; MIXED below). PRICE BULLISH vs MIXED by breadth cutoff (65–87% = BULLISH; ~47% MIXED) — cutoff between 47% and 65% (§7 exact).
- **UNUSUAL filter:** engine-side flag; per study §509/§949/§1160, "volume vs trailing per-strike median" with a sample-count minimum (study elsewhere cites ~3× median). Collapses to flagged names only; DTE buckets re-segment to `0-7d/7-30d/30d+`.
- **Flow Score (Col5):** intensity/unusualness metric; ~0 baseline, 3–6 elevated. Plausibly call/put premium ratio or a normalized standout z — two candidate readings in notes; unresolved (§7).
- **CB (Cap-Balance):** live signed cap-weighted breadth balance (~+3.5), increments intraday; clearable as a filter.
- **Sector chip aggregates:** per-sector net flow $ or bullish-signal count; recompute by layer×mode×timeframe.
- **Premium sizing:** tile area ∝ total options premium $ (labels like `$28.9M`, `26.9M`, `~4M`).
- **Snapshot time chips** imply the flow layer is backed by **intraday time-series snapshots** queryable at a chosen clock time.

---

## 7. Gap List (unknowns for the builder to decide or confirm from source)

1. **Timeframe set** — confirm `1D|1W|1M|YTD` (notes twice showed a duplicate `1H`).
2. **CAP vs sizing** — is `CAP` in the switcher a separate control or the same as the CAP sizing chip? Confirm the full sizing model (CAP/EQUAL/PREMIUM) and defaults per layer.
3. **CB metric** — exact definition, formula, and units of the "Cap-Balance" number; what its `×`-clear does.
4. **Sector-chip suffix units** — `×+27B` vs `×+279` vs `×+11.8` vs `×0`: dollars? signal counts? net breadth? Confirm formula and per-layer meaning.
5. **DTE buckets** — canonical bucket set(s); single- vs multi-select; why buckets differ between ALL (`1-30d/20d+/30d+`) and UNUSUAL (`0-7d/7-30d/30d+`).
6. **OTM % range chips** (`0-7%/7-35%/7-45%/7-74%`) — canonical set, whether they are moneyness bands, and select behavior.
7. **MATRIX / RETS / OTC-UNUSUAL sub-toggle** — what these display modes actually render; relation to MAP/TABLE.
8. **ALL FLOW options** — confirm `ALL FLOW | CALL FLOW | PUT FLOW`.
9. **Exchange/index chip** (`AMEX`/`NDXA`) — is it a universe filter, and full option set (NYSE?).
10. **Flow Score** — exact formula/units and full tier ladder (only `Baseline` captured; need "Unusual"/"Extreme" thresholds & labels).
11. **Rank** — reconcile the two scales (0–100 percentile vs 5–62 integer); confirm which column is which.
12. **PRICE-TABLE Col4** — is the `2016/8090/4348` column market cap $M, volume, or something else? Many company names/tickers in that frame look like data-quality artifacts ("TIN = Tesla Inc") — verify against clean data.
13. **Detail panel** — never screenshotted; the full field list (§5) is from the study, not observed. Confirm layout, fields, and click-through target.
14. **HEATMAP GUIDE** — capture verbatim guide copy (legend text, tier definitions, divergence explanation).
15. **Search behavior** — highlight vs isolate vs zoom on ticker match.
16. **Hover tooltip** — per-tile tooltip content (only the bottom-bar read-out was captured).
17. **`♦` / Pivot** — meaning of the `NVDA ♦` marker and `Pivot: NVDA 0`.
18. **BEARISH / PUT-HEAVY modes** — implied but never observed; confirm they exist and their thresholds.
19. **Mode cutoffs** — exact breadth cutoff for BULLISH/MIXED and call-share cutoff for CALL-HEAVY/MIXED.
20. **Mobile** — no mobile evidence; responsive behavior entirely unknown.
21. **Keyboard shortcuts** — none observed; confirm none exist.
22. **Sector label set** — confirm 11 GICS sectors and treat `SPLIT/COVID D/COMM I/COMM D/DONEG` as OCR artifacts unless source says otherwise.
