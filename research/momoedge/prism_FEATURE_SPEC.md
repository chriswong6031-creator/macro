# PRISM / HeatSeeker — Feature Specification (Competitor: MomoEdge, momoedge.ai)

**Surface:** PRISM — strike × expiration options-structure matrix with five lenses (GEX / VEX / OI / VOL / UNUSUAL), single-ticker and confluence modes, a "HeatSeeker" standout-cell pick, hover raw-input tooltips, and a ranked ticker selector.
**Status observed:** PRISM carries a **BETA** badge everywhere. Engine footer: `ENGINE: SKYNET v3.2`.
**Source basis:** screenshot-analysis notes `/tmp/momoedge_specs/raw/prism_1..3.md` + §23–26 of the internal competitive study. This spec describes the competitor faithfully; it does NOT map to our stack. Anything not directly observed is flagged in §7.

---

## 1. Surface overview & layout (desktop)

PRISM is one of five top-level terminal tabs. Top-to-bottom structure:

1. **Top nav bar** — `MOMOEDGE // LIVE ORACLE TERMINAL` brand (left); top-level tabs `ORACLE | FLOW | HEATMAP | GEX | PRISM` (PRISM active); right side `STATUS ENGAGED` badge, user icon, bell icon. (Note: one early screenshot rendered the tab bar as `ORACLE | FLOW | HEATMAP | DEX | PRISM`; the stable label is **GEX**, not DEX.)
2. **Sub-controls bar** (PRISM's own toolbar) — `PRISM` label + `BETA` badge · ticker input · `SINGLE | CONFLUENCE` mode toggle · metric/lens tabs `GEX VEX OI VOL UNUSUAL` · `PRISM GUIDE` button (far right of content area).
3. **Secondary filter row** — strike-range presets · expiry scope (`DEFAULT | 0DTE | ALL`) · contract-side filter (`C | P`) · lookback (`1W | 1M`) · unit/value readout · `GLOBAL | PER-COL` (a.k.a. `PER-STKL`) normalization toggle · `Spot <price>` readout · sometimes a `LIVE` toggle and a `SORT: <n>` readout.
4. **Main content area** — left ~70% = the strike×expiration heat matrix (Single) OR three side-by-side ticker panels (Confluence); right ~30% = context/right-rail panel.
5. **Right rail** — dynamic "structure read" (regime + net exposure narrative), a **LEGEND** block, a **SIGNALS** block (label `MAGIC LENS KARMA`), and in Confluence an **AGREEMENT** panel + "REDUCE CONFLUENCE" explainer. Right rail is also referred to as `CONTACT`/`CONTEXT 1` tab in different captures.
6. **Bottom status bar** — `ORACLE ONLINE | UPTIME <hh:mm:ss> | SIGNALS: <n> ACTIVE | STALE: <n>s ago` (or `0 MARKET CLOSED`) `| ENGINE: SKYNET v3.2`.

**Matrix semantics (canonical, from guide):** rows = strikes, columns = expirations, each cell = a single number for the active lens. Color encodes sign+magnitude. The **spot row** (strike nearest current price) is banded and marked (dot `[·]`, highlighted teal/cyan). Sub-header pattern per lens: `<METRIC> HEATMAP <TICKER> strike × expiration — <description>` (e.g. "GEX HEATMAP NVDA strike × expiration — Gamma exposure"). A far-right **Σ column** aggregates each row across all expirations (visible in ALL scope). Each row can also carry aggregate/net values; a per-lens **aggregate readout** (e.g. `+$1.12B`, `-8M`, `+381K`) appears at the matrix bottom-right.

**Mobile evidence:** Study §Mobile notes that the mobile terminal promotes GEX and PRISM to first-class bottom-tab navigation (`Signals, Analysis, Flow, GEX, Macro, PRISM`) and embeds PRISM via `heatseeker.html?embed=1` iframe with ticker sync (postMessage). No PRISM mobile layout was screenshotted — treat mobile as "embedded iframe, ticker-synced" only.

---

## 2. Complete control inventory

### 2.1 Ticker selector
- **Input:** free-text search box with magnifying-glass icon; shows current ticker + live price + up/down arrow (e.g. `SPY $762.38 ↑`, `NVDA $844.78 ↑`). Type-to-filter.
- **Dropdown (ranked):** two columns — `TOP 50 BY OPTIONS VOLUME` (auto-ranked) and `PRESET LIST` (user-saved favorites, marked with a dot bullet). Each row = clickable ticker.
- **Row fields:** ticker · options volume (K/M) · integer **score** (0–100).
- **Observed ranking (verbatim):** SPY vol 5.2M score 94 · QQQ 3.8M 88 · TSLA 2.4M 86 · NVDA 2.1M 82 · SPX 1.8M 79 · COIN 982K 71 · AAPL 814K 68 · META 698K 64 · AMZN 612K 61 · SMCI 584K 58 · MSTR 521K 56 · MSFT 478K 52 · GOOGL 412K 48 · AMD 384K 44 · PLTR 342K 42.
- **Behavior:** selected row highlighted; selecting a ticker re-renders the matrix. Score appears to be an ordinal-rank→0–100 transform (≈ −3.5/rank), not a normalized volume value (see §6).

### 2.2 Mode toggle — `SINGLE | CONFLUENCE`
- **SINGLE:** one ticker, full strike×expiration matrix.
- **CONFLUENCE:** three fixed indices **SPX · SPY · QQQ** side-by-side (hardcoded bundle — NOT arbitrary user selection), strikes normalized to % from spot so rows align. Metric toggle applies to all three at once.

### 2.3 Lens / METRIC tabs — `GEX | VEX | OI | VOL | UNUSUAL`
One active at a time. Each has its own accent color: **GEX = teal/cyan**, **VEX = purple/violet**, **VOL = teal/cyan**, **UNUSUAL = orange/amber**, OI = (neutral/cyan). Selecting a lens changes the cell number, the sub-header description, the unit readout, the color-ramp legend, and the right-rail narrative.
- **OI sub-metric toggle:** `OI | NET CONTRACTS` (also seen as `NET MT CONTRACTS`).
- **VOL sub-metric toggle:** `NET VOLUME: C | P` (net-call vs net-put display).
- **VEX sub-metric toggle:** `# VANNA | $ | $ 2V` (count / dollar / dollar-per-2-vol-points).
- **UNUSUAL readout:** `NET UNUSUAL: -2P | 0A 440` style (put/all breakdown + value).

### 2.4 Expiry scope — `DEFAULT | 0DTE | ALL`
- **DEFAULT:** a default set of near-term expiration columns.
- **0DTE:** today's expiration only (matrix collapses to ~single column); dramatically changes aggregate (see §6 example).
- **ALL (Σ All):** every expiration summed; prominent far-right **Σ** column.
- **DTE preset chips** (secondary row, context-dependent — labels partly illegible): in ALL view `6ZD | 4ZD | 3TD | 8`; in 0DTE view `v15 | v20 | v30 | 4 | 8`. Interpreted as days-to-expiration / lookback presets that scope which expirations feed the view.

### 2.5 Strike-range presets (secondary row)
- Chips `+10 | +20 | +40` (also seen `+0 | +20 | +40 | +R`). Per guide **SHORTCUTS**: **Range 1 = ±10 strikes · 2 = ±20 · 3 = ±40** around spot. `+R` unconfirmed (likely "reset"/"raw range").

### 2.6 Contract-side filter — `C | P` (+ `N`, `1W | 1M`, `LIVE`)
- `C` = calls, `P` = puts, `N` = net (seen in UNUSUAL row). `1W | 1M` = lookback window for baseline/median metrics. `LIVE` = real-time vs EOD data mode toggle (seen in OI/VOL).

### 2.7 Normalization toggle — `GLOBAL | PER-COL` (a.k.a. `PER-STKL`)
- **GLOBAL:** color intensity normalized to the max absolute value across the whole matrix.
- **PER-COL / PER-STKL:** normalized within each expiration column (per-column) — screenshots use both labels; likely per-column vs per-strike-row variants.

### 2.8 Score scope — `SCORE: GLOBAL | PER-COL`
Distinct readout controlling whether the HeatSeeker/score normalization is global or per-column. `SORT: <n>` readout also appears (top-right of matrix) — a sort-mode indicator whose full option set was not captured.

### 2.9 Guide & onboarding
- `PRISM GUIDE` button → accordion modal (see §5).
- First-run onboarding modal with `GOT IT` dismiss.

### 2.10 Keyboard shortcuts (from guide, verbatim)
- **Metric:** `G` GEX · `V` VEX · `O` OI · `L` VOL · `U` UNUSUAL.
- **Range:** `1` = ±10 strikes · `2` = ±20 · `3` = ±40.
- (SCOPE and VIEW are documented as controls; no dedicated key captured.)

---

## 3. Data model (displayed fields, inferred type/units/semantics)

### Matrix cell (per lens)
| Lens | Cell value | Unit / type | Sign semantics |
|---|---|---|---|
| **GEX** | dollar gamma exposure per 1% spot move | $ (auto-scale K/M/B); signed | green = positive/call-dominant; red = negative/put-dominant |
| **VEX** | DTE-weighted vanna load, normalized across expirations | `$ VANNA / 1% IV` (also `#`/`$ 2V`); signed | green = call-side vanna; red = put-side vanna |
| **OI** | net open interest, calls − puts | contracts (K); signed (`C-P`) | green = more calls parked; red = more puts |
| **VOL** | net traded volume today, calls − puts | contracts (K); signed (`C-P`) | green = call-heavy; red = put-heavy |
| **UNUSUAL** | net excess volume above trailing per-strike median, calls − puts | ratio/z vs median, `C-P` | green = bullish; red = bearish; ≥~3× median = magenta |

### Axes & anchors
- **Strike** (row): absolute price in Single; **% from spot** bucket in Confluence (e.g. +3.2%, +2.8% … 0.0% SPOT … −1.2%). Half-strikes (`.5`) supported.
- **Expiration** (column): dates `M/D` (e.g. `7/7`, `7/8`, `7/18`); duplicate same-date columns occur (multiple listings / weeklies). Far-right **Σ** = row aggregate across all expirations.
- **Spot** (`Spot 751.28`): current underlying price; nearest-strike row is the **SPOT row** (teal band).

### Per-lens unit readouts (verbatim tooltip headers/bodies)
- **GEX · VALUE UNIT** — `$ Γ / 1% MOVE`: "Dollar gamma per 1% move, the notional dealers must hedge for a 1% move in the underlying. The field default; scaling differs by orders of magnitude between conventions, so it is always shown here." Freshness seen `● LIVE`.
- **VEX · VALUE UNIT** — `$ VANNA / 1% IV`: "Dollar vanna per 1% change in implied volatility, the hedging flow triggered as IV shifts. Reads as the forward-looking, multi-session signal." Freshness `● 1M AGO`.
- **OI · VALUE UNIT** — `NET CONTRACTS · C-P`: "Net open interest at the strike, calls minus puts, in contracts. Positive = more calls parked; negative = more puts."
- **VOL · VALUE UNIT** — `NET VOLUME · C-P`: "Net traded volume today, calls minus puts, in contracts. Fresh flow rather than standing positions."
- **UNUSUAL · VALUE UNIT** — `NET UNUSUAL · C-P`: "Net excess volume above the trailing per-strike median, calls minus puts. Positive = bullish, negative = bearish."

### Aggregates / net readouts (right rail + matrix)
- **NET GEX/VEX/VOL** (e.g. `+$124M`, `-8M`, `+238`, `+381K`) — signed lens aggregate, auto-scaled units.
- **Dominant-cell header triple:** `<strike> | <expiry> | <value>` (e.g. `$745 | 7/7 | -$20M`).
- **Confluence AGREEMENT counters:** `3/3 aligned: <n>` and `2/3 aligned: <n>`.
- **Data freshness badge:** `● LIVE` / `● 1M AGO` / `● 5M AGO` inline near unit; `STALE: <n>s ago` in status bar.

---

## 4. Scoring / legend / tier semantics (verbatim where transcribed)

### Onboarding legend (verbatim)
`● color = direction` · `● intensity = size` · `● gold = focus cell` · `● cyan = largest cell` · `● SPOT = current price`.

### Right-rail LEGEND (verbatim, canonical form)
- "Color = direction (green call-side / red put-side)"
- "Intensity = size"
- "● gold = focus cell, the level that leads the board"
- "● cyan = largest cell, biggest single value on the board"
- "● SPOT = current price"

(Some captures show OCR-garbled tokens `gex`/`spp`/`SPY` in place of gold/cyan/SPOT — treat those as noise; the clean legend above is authoritative.)

### Color ramp (guide, verbatim)
- "Color intensity tracks magnitude: a deeper, brighter fill means a larger value at that strike and expiration."
- Signed lenses (GEX): **[GREEN]** deep forest → bright green = positive/call-dominant gamma; **[RED]** deep crimson → bright red = negative/put-dominant gamma.
- UNUSUAL: cells at/above **~3× their median turn magenta** to flag genuinely unusual activity vs merely high volume.
- "The bottom legend always labels the ramp for the active lens." (Legend is dynamic per lens.)

### HeatSeeker pick (guide, verbatim)
- "The **[★ PICK]** highlights the single cell that stands out most for the active lens, after gating for minimum open interest and a clear margin over its neighbors. The callout above the matrix names the strike, expiration, and the inputs behind it."
- "A secondary **⚡ RAW** marker shows the largest raw cell when it differs from the gated pick, so you can see both the gated pick and the unfiltered maximum."
- "The pick is a **descriptive** read of where positioning concentrates. It is not a recommendation to buy or sell anything."
- Markers: `★ PICK` (amber/gold star, gated) vs `⚡ RAW` (lightning, unfiltered max). Onboarding equivalents: gold = focus cell, cyan = largest cell.

### SIGNALS block — `MAGIC LENS KARMA`
Composite signal readout with per-lens net value; advisory (verbatim): "Sign is an assumption, not a fact. Magnitude is the reliable read."

### Epistemic warning boxes (verbatim variants observed)
- "Magnitude over sign: Sign is an assumption, not a fact." (Confluence)
- "MODEL DEALER LONG GAMMA — Assume dealers are the counterparty unless marked otherwise." / "…Sign is an assumption, not a fact. Magnitude is the reliable read." (Single GEX/OI)
- "SIGNAL LEVEL GAMMA — Sign is an assumption, not a fact. Magnitude is the reliable read." (VEX/VOL)
- "PRISM — READS LIKE GRAMMAR. If a cell doesn't move, that's a fact." (OI variant — OCR-imperfect)

### Right-rail regime narrative (dynamic, verbatim examples)
- Positive aggregate: "Call-dominant overall. Dealer hedging dampens moves — expect mean-reversion between the strong levels."
- Negative aggregate: "Put-dominant overall. Dealer hedging chases price — moves tend to extend once started."
- Shared load: "Several levels of similar size share the load — expect competition between them." / sub-header note "→ No single standout — the load is shared."
- Single-cell behavior: "Hedging pressure amplifies moves through this strike — expect acceleration, not support." vs "Hedging pressure dampens moves near key strike — price tends to pin."
- Twin walls: "A big green and a big red cell are both strong draws — they pull behavior differently once price arrives."

### Confluence AGREEMENT explainer (verbatim)
- "A horizontal band reads as the same level across all three panels. When a strong level lands on the same normalized position in all indices, the band is flagged. This is descriptive: it flags agreement, it does not issue a call."
- "REDUCE CONFLUENCE: Strikes are normalized to % from spot so the three line up for row matching, trading at very different prices. Confluence is anti-0DTE, same-day gamma, and the metric toggle applies to all three at once."

### Disclaimers (verbatim)
- "PRISM describes options positioning. It never issues buy or sell instructions. For questions, contact admin@momoedge.ai."

---

## 5. States & interactions

### Hover
- **Cell hover:** tooltip reveals **raw inputs** behind the number — call OI, put OI, call volume, put volume, and net GEX for that strike×expiration. Cell becomes the **gold focus cell**.
- **Unit-label hover:** surfaces the per-lens VALUE UNIT tooltip (§3) with freshness badge.
- **Metric-button hover:** reveals its keyboard shortcut.

### Click-through
- Lens tab click → re-renders active number/ramp/narrative. Mode/scope/range/normalization clicks re-render live without data re-fetch (tab switch in 5s keeps identical UPTIME). Ticker-row click → new ticker. Cell click behavior not explicitly captured (likely selects/pins the focus cell).

### Empty / fallback states
- **UNUSUAL baseline missing** (verbatim banner): "Unusual baseline unavailable for SPY — no 30-day volume history yet, so this currently mirrors raw VOL." → UNUSUAL falls back to raw VOL.
- **No standout:** sub-header shows "→ No single standout — the load is shared" and HeatSeeker suppresses/downgrades the pick.
- **Market closed:** status bar shows `0 MARKET CLOSED`.

### Guide / tutorial overlays
- **First-run onboarding modal** (verbatim, §4 onboarding legend) with `GOT IT`.
- **PRISM GUIDE accordion** — modal, `X CLOSE`, cyan-accented; sections (icons): **WHAT PRISM SHOWS** (diamond), **THE LENSES** (square), **READING THE COLOR RAMP** (grid), **THE HEAT SEEKER PICK** (star), **SHORTCUTS & CONTROLS** (bars). Full verbatim text captured in §3/§4/§6. Guide is also delivered on mobile via iframe postMessage.

### Keyboard — see §2.10.

---

## 6. Engine inferences (thresholds, formulas, score components)

- **GEX** = net dollar gamma exposure per 1% spot move (`$ Γ / 1% MOVE`); signed; always shown with units because "scaling differs by orders of magnitude between conventions." Sign is dealer-assumption-dependent (heavily caveated). Alt unit `NET CONTRACTS`.
- **VEX** = DTE-weighted vanna load, normalized across expirations; unit `$ VANNA / 1% IV`; sub-modes `#` (count) / `$` (notional) / `$ 2V` (per 2 vol points). Framed as forward-looking, multi-session.
- **OI** = net open interest = calls − puts (contracts); "standing positions."
- **VOL** = net traded volume today = calls − puts (contracts); "fresh flow."
- **UNUSUAL** = net excess volume above **trailing per-strike median** (calls − puts). Threshold ≈ **3× median** → magenta; requires a **minimum sample count** and a **30-day volume baseline** (else fallback to raw VOL). Lookback window `1W | 1M`.
- **HeatSeeker pick gates:** (1) minimum total OI; (2) candidate cell must beat the 2nd-best cell by a **lens-specific standout ratio**; GEX/VEX require a **stronger standout ratio + DTE penalty**; OI/VOL have their own gates; UNUSUAL requires volume-vs-median + a **lower standout threshold**. Output: strike, expiration, side/net value, standout ratio, confidence. `⚡ RAW` = unfiltered argmax when it differs from the gated `★ PICK`.
- **Confluence flags** when **gamma flip, call wall, put support, or HVL** align across SPX/SPY/QQQ within a % threshold; strikes bucketed on a fixed **% from spot** grid centered at spot; displays 0DTE-aligned GEX across the three indices; AGREEMENT counts 3/3 and 2/3 aligned bands. Explicitly **anti-0DTE / same-day gamma** for the confluence read.
- **Normalization:** `GLOBAL` = whole-matrix max; `PER-COL`/`PER-STKL` = per-expiration (or per-strike) max — drives cell color intensity.
- **Ticker score:** ordinal-rank→0–100 map by daily options volume (observed ≈ −3.5 points/rank: rank1=94 … rank15=42).
- **0DTE scope example (NVDA):** ALL scope NET GEX `+$124M` "Call-dominant"; switching to 0DTE flips to NET GEX `-$42K` "Put-dominant" — units auto-scale, narrative regenerates from aggregate sign.
- **Regime narrative logic:** positive aggregate → "dampens moves / mean-reversion / pin"; negative aggregate → "chases price / moves extend"; near-equal top cells → "load is shared / competition."
- **Snapshot history (study §25):** GEX matrix reconstructable from stored snapshots; **historical mode locks lens to GEX** (snapshots lack VOL/VEX/UNUSUAL fields). **OI Movers rail (§24):** new strikes + large OI% changes, call/put separated, deduped by strike/side — surfaced as context around the matrix.

---

## 7. Gap list (unknowns — builder must decide or confirm from source `heatseeker.html` / PRISM JS)

1. **HeatSeeker exact numbers:** minimum-OI thresholds, per-lens standout ratios, DTE-penalty formula, confidence formula/range. Guide gives structure, not values.
2. **UNUSUAL exact math:** median window length (trading days), "minimum sample count" value, whether metric is a ratio, z-score, or raw excess; exact magenta breakpoint (~3×) and any ceiling.
3. **VEX definition:** "DTE-weighted vanna load" weighting scheme; what `$ 2V` (per-2-vol-points) precisely means vs `$ VANNA / 1% IV`; the `# VANNA` count.
4. **Confluence alignment threshold:** the % tolerance for "same normalized position"; the exact % bucket grid width/step; which of {gamma flip, call wall, put support, HVL} feed the 3/3 vs 2/3 counters.
5. **Normalization labels:** reconcile `PER-COL` vs `PER-STKL` — are these two distinct modes (per-column vs per-strike-row) or one relabeled control?
6. **Secondary DTE/range chips:** decode `6ZD | 4ZD | 3TD | 8` and `v15 | v20 | v30 | 4 | 8` — DTE presets? IV/delta cutoffs? Their exact filter effect.
7. **`SORT: <n>` control:** what dimensions the matrix sorts by; option set; default.
8. **`+R` range chip** and `N` contract-side option semantics.
9. **Cell-click behavior:** does clicking pin the focus cell, open a chain drill-down, or route to Flow/GEX? Not captured.
10. **Ticker score formula:** confirm whether purely ordinal-by-volume or a blended liquidity score; PRESET LIST save/manage UX.
11. **`MAGIC LENS KARMA`:** what the composite signal is and how its per-lens value is computed.
12. **`LIVE` toggle:** LIVE vs EOD data-source difference and which lenses honor it.
13. **Confluence right-panel structure read:** the exact regime/net-exposure fields shown in Confluence vs Single differ; full field list not captured.
14. **Expiration column duplication:** why same-date columns repeat (AM/PM settlement? weekly vs monthly listings?).
15. **Data cadence:** why GEX = `LIVE` but VEX = `1M AGO` / UNUSUAL = `5M AGO` — per-lens refresh intervals unconfirmed.
16. **Mobile PRISM layout:** only "embedded iframe, ticker-synced" is known; no responsive layout captured.
17. **Universe size:** dropdown says "TOP 50 BY OPTIONS VOLUME" but only 15 rows captured; confirm 50-row cap and refresh cadence.
18. **Historical snapshot scrubber UI:** study §25 says a scrubber exists (GEX-locked); no screenshot — controls/behavior unknown.

---

*End of spec. All quoted strings transcribed from screenshot notes; OCR-imperfect fragments are flagged inline. No implementation mapping to our stack included per instruction.*
