# Voltick competitive sweep → Mastermind "Gamma Levels" build plan

Author: Fable
Date: 2026-07-16
Scope: full feature/UX/engine sweep of voltick.io and a phased plan to bring its capabilities
into the Mastermind Terminal live intraday options suite + Macro Dashboard engine.
Status: assessment + program of record. No directional-alpha claim; display-tier honesty rules apply.

Reconnaissance basis: full read of voltick.io home, /learn (17-lesson academy + 7 worked
examples), /calibration (Track Record), /trust (Trust Index), /ledger, /daily, /features, /flow,
plus operator-supplied screenshots (Tools menu, GEX/VEX scanner, Levels card, Dark Pool Flow).
The live member tape is a server-side gate (data not delivered to the DOM), but its full
mechanism is documented in Learn Lesson 17 — enough to reproduce.

IP note: functional concepts and generic industry terms (gamma flip, call/put wall, confluence,
sticky/slippery, air pocket, expected move, initial balance, net drift, dark pool, GEX/VEX) are
not protectable and we copy them faithfully. Voltick's specific coined node names (Volt, Coil,
Surge as a node, Rug) and brand prose are theirs — we define our OWN equivalent vocabulary
(mapping table in §4) and write our own copy. Same engine, same UX, our identity.

---

## 1. The core insight: what Voltick actually beats us on

Voltick does NOT have better raw options data. We have far more: a 60 GB / 380-root / 2012→
ThetaData store with full greeks, live tape, FS-0/FS-1 outcome ledgers (7.3M events), and the
new U-CHAIN 15-min chain-greeks lane. Their moat is three layers we are weak on:

1. **A translation layer.** They turn raw GEX/VEX into a plain-English weather map: named
   levels with single-meaning colors, a ribbon that "reads the board aloud," and tap-anything-
   explains-itself. Our surfaces show gamma/delta/vanna bars; a novice cannot read them.
2. **A honesty/integrity trifecta.** Self-grading Track Record (every level scored on touch,
   misses shown), a per-ticker Trust Index, and a SHA-256-sealed pre-open Ledger anyone can
   verify. This is exactly our house doctrine (falsifiable, published misses, PIT no-leakage) —
   they've productized it and we haven't surfaced it.
3. **Presentation + teaching.** Colorblind mode, built-in tour/tooltips/academy, shareable
   Levels card, morning brief. Low-friction, institutional-clean.

Strategic verdict: build a **Levels Engine** (the named-level taxonomy + narration over our
existing gex/hub/matrix data) and its Terminal surface, then wire the honesty trifecta on top of
our FS-0 grader. This is the highest-leverage options work available and it matches the
operator's standing aesthetic bar (institutional/Perplexity, honest framing).

## 2. Voltick full feature inventory (what we're cloning)

### 2.1 The board (Voltmap) — the gamma heat map
- Per-strike heat column, live, recomputed every 5s (member) / 15-min delayed (free).
- Color law: green = sticky (positive gamma, hedging leans against moves, price holds);
  red = slippery (negative gamma, hedging chases, price slides). **Brighter = bigger.**
  Every color has exactly ONE meaning (amber/violet/magenta/blue reserved for specific nodes).
- Sticky is NOT support: a sticky level works from both sides (floor from above, ceiling from
  below) — the strongest green strike is usually the ceiling.
- Net-gamma ribbon at top: one sentence — positive (range/pin day) vs negative (trend/overshoot).

### 2.2 Named levels (the node taxonomy)
- **Volt ★** (amber): single biggest hedging-weight strike, from OI, static all day = day's magnet/pivot.
- **Surge ↯**: the LIVE counterpart to the Volt — where today's flow is heaviest right now; drifts intraday.
- **Reversal ↘** (magenta): heaviest strike on the opposite side of the gamma-zero from the Volt;
  far edge of the range; its color says whether it turns (green) or breaks (red).
- **Coil ◆** (blue ring): any strike ≥ 50% of the Volt's weight; green coil = speed bump, red coil = fast lane.
- **Flip ⚡** (violet dashed): price where cumulative gamma (bottom-up) crosses negative→positive;
  calm above, wild below.
- **Air pocket ≋**: 3+ consecutive near-zero strikes → price travels through fast.
- **Rug ⚠**: sticky green shelf directly on top of a heavy red strike → break below accelerates.
- **Squeeze ⤴**: mirror of the rug — red lid above a sticky shelf → break up runs fast.
- **Call wall / Put wall**: strongest positive strike (sticky ceiling) / biggest strike below price (slippery floor).
- **Confluence ⊕**: tagged when several marks stack on one strike; popover quotes the recorded hold rate.

### 2.3 Views (view picker)
Single · Multi (up to 4 boards, opens SPX+SPY, cross-check line) · Chart (candles + levels drawn,
1/2/4 up) · Grid (all boards, one tile each) · Scanner (filter by calm/fast, above/below flip,
near Volt, **Far Volt** = heaviest level 5–10%+ from price, all-dates or ≤3mo) · Context (board
read aloud level-by-level) · Replay (scrub any of last 30 days like a movie) · Week (today→Friday) ·
Flow (tape + dark pool on the board). Toggles: **GEX ↔ VEX**; expiration scope chips
(0DTE, Week, ≤1mo, ≤3mo, Σ all).

### 2.4 GEX vs VEX
GEX = hedging response to PRICE moves (the speed bumps/danger zones). VEX = hedging response to
VOLATILITY moves (short-vega dealers forced to hedge a vol jump can fuel multi-day moves). Same
board, one toggle. Operator screenshots confirm a VEX strike-ladder Levels card (Net VEX, ATM IV,
±Move chips + Volt/Call wall/Put wall/Coil/Surge chips + plain-English "The read").

### 2.5 Reading tools
- Plain-English ribbon (board in a sentence).
- **✦ Intel**: pattern flags, unusual activity with reasons, the Daily Report, and **Echoes**
  (past sessions most like today + what they did).
- **Expected Move**: option-priced 1σ band to next expiry + week's end; graded nightly; learned
  ×1.96 tuned, sticky/slippery separately.
- **Initial Balance**: 9:30–10:30 ET first-hour high/low/mid/range + broke-or-held; real break-rate banks over time.
- **⇆ Compare** (two levels on one chart), **⇲ Range Lens** (territory between two strikes vs expected move).
- **Level day-chart**: click any strike → its full-day chart, recent track record ("Volt on 4 of last 5"), touch count.
- **Daily Report**: whole session's story in plain English, copyable as image.
- **☾ Overnight strip**: names strikes whose levels grew/faded most since yesterday's close.

### 2.6 Flow page (6 panes)
⚡ Options Flow (live tape) · ✦ Net Drift · $ Premium by Expiry · ◐ Dark Pool Flow ·
⊞ Sector Flow · ▤ Leaders. Sub-modes: By ticker / Live tape.
- **Flow tape**: every print read out loud. Aggressor first (at/above ask = true buy; at/below
  bid = true sell; mid = negotiated/none). Then what it opened: call bought = bullish; put bought
  = bearish; call sold/written = capped upside; put sold = willing-to-own = bullish. **Opening**
  flag when volume > prior OI. Screener: filter by ticker, direction, call/put, buy/sell, premium,
  DTE, opening-only; one-tap screens (bullish opening, 0DTE, whales); sort by premium. Tally of
  bullish vs bearish premium.
- **Net Drift**: cumulative bought-vs-sold option premium through the session (a sold put counts bullish).
- **Dark pool / off-exchange**: share of a ticker's volume printed off-exchange (dark pools, ATS,
  wholesaler internalization), the price levels carrying most of it, biggest prints; also drawn on
  the Chart as purple levels. Honest naming: "off-exchange," never oversold.

### 2.7 The honesty trifecta (the crown jewels)
- **Track Record (/calibration)**: every level graded nightly on touch, pooled across 490+ boards,
  per level type — Volt "drew price to it" 61%, Coil "held on touch" 90%, Reversal "turned price"
  92%, Walls "close inside" 73%, Flip "pivot on touch" 96%, Surge "reached" 75%, Rug "break ran
  fast" 47% — each with N, misses shown, sticky/slippery split, and post-touch move magnitude
  (turned ~X% / broke ran ~Y%). Per-ticker cards (band held, came to Volt, closed in walls,
  reversals turned). The **10:00 read** (engine writes chop-vs-stretch call at 10:00, checks vs
  close). **Week band held**. **Range by day type** (sticky vs slippery travel). **Band learning**
  (×1.96, sticky ×2 / slippery ×1.42). Session-by-session table, none removed.
- **Trust Index (/trust)**: 388 boards ranked by composite reliability (Volt reached + band held +
  closed in walls), N sessions, worst names shown too, <8-session boards held out. Free embeddable
  self-updating badge (site-wide or per-ticker).
- **The Ledger (/ledger)**: every morning 9:12 ET (18 min pre-open) writes all levels for every
  board to one canonical file, seals with SHA-256, publishes the hash immediately; file public +
  permanent + re-hashable (shasum -a 256); graded after close, misses shown; nothing back-filled.
  "The map came first, and you can check."

### 2.8 Alerts, share, learn, extras
- **Alerts**: level alerts (price within 0.10%, via email/Discord/phone), board alerts (new Volt/
  wall/flip/edge-of-move). Framed as location facts, never trade signals.
- **Share**: ◧ Levels card (clean on-brand image of live levels), copy chart image, public share links.
- **Learn**: 17-lesson academy, ? Guide cards over the board, one-time Tour, hover tooltips
  everywhere, ✦ Ask assistant ("what does this do?"), Calendar (Fed/CPI/OPEX), Gamma Levels page.
- **Extras (footer Tools)**: The Daily (close read + 9:00 ET Morning Brief email on starred
  boards), Weekly Map, **Moves** (expected-move table, every board's band + recorded hit rate),
  Earnings, Your Levels, Watchlist + stars, ⌘K quick search, Colorblind mode (◑ CB, repaints
  red/green → blue/orange, remembered).
- Cadence honesty everywhere: "OI updates once daily (OPRA); prices live; member map recomputes
  every 5s; free view 15-min delayed; we display only our own computed exposure figures, never raw
  exchange quotes." (This is the operator's ThetaData debrand/redistribution posture already.)

## 3. Mastermind current state vs Voltick (gap map)

| Voltick capability | Our current state | Gap |
|---|---|---|
| Gamma heat board, per-strike, live | gex_engine + options_hub gex/{ROOT}.json (by_strike gamma/delta/vanna/charm), Prism MatrixGrid (strike×expiry) | Have the DATA; missing the single-column live heat board + color law + narration |
| Named node taxonomy (Volt/Surge/Reversal/Coil/Flip/Air/Rug/Squeeze/walls/confluence) | walls + gamma flip exist in gex_engine; no coil/reversal/air/rug/squeeze/surge/confluence detection | **Build the Levels Engine** (new) |
| Plain-English ribbon + tap-explains | none | **Build narration layer** (new) |
| GEX ↔ VEX toggle | GEX yes; VEX (vega exposure) not surfaced as a board | Add VEX to the engine + toggle |
| Expiration scope (0DTE/Week/≤1mo/≤3mo/Σall) | matrix has expiries; not a scope selector on the board | Add scope selector |
| Single/Multi/Chart/Grid/Scanner/Context/Replay/Week views | Terminal has gex/prism/tickers; no Multi/Grid/Replay/Context/Scanner-by-structure | Build the view set |
| Live flow tape, plain-English, screener | live_flow feed + Terminal Tape/Desk tabs; aggressor labelled soft (F7 law) | Have tape; add plain-English row narration + full screener + one-tap screens |
| Net Drift | planned (WP-NETDRIFT-PANEL) + tide cumulative NCP/NPP | Ship the per-ticker panel w/ price overlay |
| Premium by Expiry | tape_flow has DTE buckets | New panel |
| Dark pool / off-exchange | NOT present; ThetaData is options OPRA; equity off-exchange = separate | **Data question — see §6** |
| Sector Flow | macro has sector data; not wired to flow | New panel |
| Leaders | flow_leaders.py + Terminal leaders/radar tabs | Have; add horizon/context |
| Track Record (per-level touch grading) | FS-0/FS-1 event grader (7.3M events) grades flow events, NOT level-behavior-on-touch | **Build level-behavior grader** on our recorded boards |
| Trust Index (per-ticker reliability) | none | Build (rides the level grader) |
| The Ledger (SHA-256 sealed pre-open) | PIT snapshot ledger planned; no public hash seal | Build the seal + verify page |
| Expected Move learned band (×1.96 sticky/slippery) | options_hub has straddle/expected move; not learned/graded | Add nightly band-tuning + grade |
| Initial Balance | none | Cheap add (first-hour OHLC) |
| Intel / Echoes / Daily Report | none (macro has some narrative) | Build (Echoes = nearest-neighbor over recorded boards) |
| Replay (30-day board movie) | U-CHAIN records chain snapshots; gex_history now dated (PR #2615) | Wire a replay reader |
| Alerts (level/board) | none in Terminal | Build alert lane |
| Levels card (share image) | none; macro has other card exports | Build (mirror our existing card pipeline) |
| Colorblind mode | none | Cheap add (palette swap) |
| Learn academy + tooltips + Ask + Tour | none in Terminal | Build our own academy (own copy) |
| Morning Brief / Daily | macro has narrative bits | Build |
| Moves table, Weekly Map, Calendar, Watchlist/stars, ⌘K | partial (watchlist exists in Terminal) | Fill in |

## 4. Our vocabulary (own naming, 1:1 concept map)

Generic industry terms we keep as-is: gamma flip, call wall, put wall, confluence, sticky,
slippery, air pocket, gamma squeeze, expected move, initial balance, net drift, off-exchange/dark
pool, GEX, VEX, 0DTE. Voltick-coined node names we replace with our own (concept identical):

| Voltick | Ours (proposal) | Concept |
|---|---|---|
| Volt ★ | **Anchor ★** | biggest OI-gamma strike, static all day, the magnet |
| Surge ↯ | **Pulse ↯** | live-flow-heaviest strike, drifts intraday |
| Reversal ↘ | **Counter ↘** | heaviest strike opposite the Anchor across gamma-zero |
| Coil ◆ | **Cluster ◆** | strike ≥50% of Anchor weight |
| Rug ⚠ | **Trapdoor ⚠** | sticky shelf over a slippery strike |
| Squeeze ⤴ | **Launchpad ⤴** | slippery lid over a sticky shelf |
| Flip ⚡ | Flip ⚡ (generic) | gamma-zero crossing |
| Air ≋ | Void ≋ | 3+ near-empty strikes |
| Confluence ⊕ | Stack ⊕ (generic ok) | marks stacked on one strike |

(Operator picks the final brand words; the engine uses stable internal keys either way.)

## 5. Architecture — where each piece lives

Boundary (per the options confluence program): the **engine, PIT store, grader, ledger** live in
Macro Dashboard (Python) and publish JSON to R2; the **Terminal (charting-app, Next.js)** is the
presentation surface reading those artifacts via /api/flow. No analytics re-implemented in the
frontend (avoids formula drift). New pieces:

- **engine/levels_engine.py** (new, macro): consumes options_hub gex/vex by_strike + tape/live_flow
  → emits the named-level taxonomy (Anchor/Pulse/Counter/Cluster/Flip/Void/Trapdoor/Launchpad/
  walls/Stack) + the color law (sticky/slippery, brightness) + the plain-English narration strings +
  net-gamma regime ribbon. One canonical `levels.v1` schema (extends OPTIONS_SENSOR_CONTRACT).
- **engine/vex_engine.py** (new): vega exposure by strike (mirror of gex_engine; VEX board).
- **engine/expected_move.py** (extend options_hub): option-priced band + nightly learned multiplier
  (sticky/slippery separately) + grading hooks.
- **engine/levels_grader.py** (new): every recorded board (we record via U-CHAIN + gex_history)
  graded on touch next session — per-level-type hit rates, sticky/slippery split, post-touch move.
  Reuses the FS-0 outcome-ledger discipline; writes `levels_track_record.v1`.
- **engine/trust_index.py** (new): per-ticker composite reliability from the grader; `trust_index.v1`.
- **scripts/seal_levels_ledger.py** (new): pre-open canonical levels file per board + SHA-256 seal +
  publish; post-close grade join. The public verify page reads it.
- **Terminal**: new OptionsHubView tabs / view-picker: **Levels board** (the Voltmap equivalent,
  Single/Multi/Grid/Chart/Scanner/Context/Replay/Week + GEX/VEX toggle + scope chips), plus
  standalone pages: Track Record, Trust Index, Ledger, Moves, Daily, Learn academy, Levels-card
  share, Colorblind toggle, Alerts. Reads `levels.v1`, `vex.v1`, `levels_track_record.v1`,
  `trust_index.v1`, `ledger/*.json` from R2.

All display-tier: our binding honesty laws apply (soft flow direction / F7, dealer-sign passport on
GEX, "positioning not prophecy," no "validated," cadence disclosure, EN/ZH i18n).

## 6. Data questions to resolve before building

1. **Dark pool / off-exchange read**: ThetaData is OPRA options. Equity off-exchange prints
   (dark pools/ATS/wholesaler internalization) need an equity-trade feed with venue/TRF
   classification. Check whether the private ThetaData sub includes stock trade conditions
   (venue/TRF/D-exchange) or whether we need Polygon/other. If unavailable, ship the other 5 panes
   and mark Dark Pool "data pending." (PROBE ITEM.)
2. **VEX**: our greeks store has vega — confirm vanna/vega coverage is sufficient to compute a VEX
   board across the universe (probe already showed second-order greeks incl. vega; good).
3. **5-second recompute**: Voltick recomputes the member board every 5s. Ours: live_flow ~36-min
   effective today; the U-CHAIN snapshot lane is 15-min; the FPSS stream (once the credential is
   fixed) enables true seconds-latency. Ship at 15-min/snapshot cadence now; upgrade to seconds
   when the stream lands. Disclose cadence honestly (we already do).
4. **Replay**: we now retain dated gex_history (PR #2615) + U-CHAIN chain snapshots — confirm the
   once-per-minute board recording granularity Voltick uses; our 15-min is coarser (acceptable v1,
   note it).

## 7. Phased build plan

**Phase A — Levels Engine + narration (the translation layer, highest value).**
- WP-A1 `levels_engine.py`: node taxonomy + color law + regime ribbon over existing gex by_strike;
  `levels.v1` schema; unit tests on synthetic + real SPY chain; deterministic reconstruction test.
- WP-A2 plain-English narration strings (ribbon + per-node one-liners + Context read-aloud),
  EN/ZH, our own copy.
- WP-A3 Terminal **Levels board** (Single view) reading `levels.v1`: heat column, colored nodes,
  ribbon, tap-explains, colorblind toggle. Institutional aesthetic per operator bar.

**Phase B — GEX/VEX + expected move + views.**
- WP-B1 `vex_engine.py` + GEX/VEX toggle + expiration scope chips.
- WP-B2 expected-move band + nightly learned multiplier (sticky/slippery) + Initial Balance.
- WP-B3 views: Multi, Grid, Chart-with-levels, Scanner (calm/fast, above/below flip, near/Far
  Anchor), Context, Week.

**Phase C — the honesty trifecta (our differentiator, aligns with house doctrine).**
- WP-C1 `levels_grader.py`: per-level-type touch grading on recorded boards → `levels_track_record.v1`;
  Terminal Track Record page (per-type hit rates, misses shown, sticky/slippery split, post-touch
  move, per-ticker cards, session table). Rides FS-0 discipline.
- WP-C2 `trust_index.py` + Terminal Trust Index page + embeddable badge.
- WP-C3 `seal_levels_ledger.py` (SHA-256 pre-open seal) + Terminal Ledger verify page.

**Phase D — Flow panes + Intel + Replay.**
- WP-D1 Flow tape plain-English row narration + full screener + one-tap screens + bullish/bearish
  tally (on top of live_flow; soft-direction language per F7).
- WP-D2 Net Drift panel (per-ticker, price overlay) + Premium by Expiry + Sector Flow + Leaders
  (extend flow_leaders).
- WP-D3 Dark Pool pane (gated on §6.1 data probe).
- WP-D4 ✦ Intel: pattern flags, unusual activity, Daily Report, **Echoes** (nearest-neighbor over
  recorded boards). Replay reader over gex_history/U-CHAIN snapshots. Overnight strip.

**Phase E — reach & polish.**
- WP-E1 Alerts (level within 0.10% + board-structure-shift) via existing alert infra + Discord.
- WP-E2 Levels card share image + copy-chart + public share links.
- WP-E3 Learn academy (our own copy), tour, tooltips, Ask assistant, Calendar, Moves table,
  Weekly Map, Daily/Morning Brief, ⌘K, watchlist/stars.

**Cadence upgrade (cross-cutting):** when the FPSS stream credential is fixed, the board goes from
15-min snapshot to seconds-latency using U-TAPE; disclosed honestly.

## 8. What ships first (this session)
1. This assessment/program doc (record of the sweep + plan). 
2. WP-A1 kickoff: `levels_engine.py` v1 (Anchor/Cluster/Flip/walls/Void + sticky-slippery + regime
   ribbon) over the existing options_hub gex by_strike, with tests and a real-SPY reconstruction —
   the tractable, highest-value first brick that everything else builds on.

## 9. Honesty guardrails (binding, inherited)
Positioning not prophecy. GEX/VEX carry the dealer-sign passport (assumed convention, not measured
inventory). Flow direction stays soft (F7). No "validated." Cadence disclosed. Track Record shows
misses and never becomes a win-rate or buy/sell ranking. The Ledger seal is integrity, not alpha.
Everything display-tier until our existing gates mature. EN/ZH for every surface.
