# MomoEdge Oracle — Canonical Build Specification

**Surface:** Oracle signal dashboard (alert stream, signal brief, trade geometry, confidence index, oracle option card, history/performance, guides)
**Product:** MomoEdge terminal (momoedge.ai)
**Source:** screenshot-analysis notes `/tmp/momoedge_specs/raw/oracle_1.md`, `/tmp/momoedge_specs/raw/oracle_2.md`
**Purpose:** faithful competitor spec for a feature-complete rebuild inside our own Terminal app. No our-stack mapping in this document.

> NOTE ON CROSS-REFERENCE: The prior competitive study at
> `research/MOMOEDGE_ORACLE_COMPETITIVE_FEATURE_STUDY_FOR_FABLE.md` was **not present** in this
> worktree (only unrelated internal Oracle-research docs exist under `research/`). This spec is
> therefore built solely from the two raw note files. Reconciling against that study — if it exists
> elsewhere — is listed as an open gap (§7, G0).

---

## 1. Surface Overview & Layout

### 1.1 Product framing
- Branding header: **"MOMOEDGE // LIVE ORACLE TERMINAL"** (one screenshot reads "ORACLE // LIVE ORACLE TERMINAL" — treat MOMOEDGE as canonical).
- Engine identity strings observed: **"ORACLE SKYNET V4.0"** (splash), **"ENGINE: UPFRONT V4.0"** (bottom status). SKYNET is the marketing engine name; V4.0 the version.
- The Oracle tab is the **default landing view** of the terminal.

### 1.2 Global chrome (persistent)
- **Top nav bar:** brand (left) · primary tab row (center) · user/settings + utility controls (right).
  - Primary tabs: **ORACLE · FLOW · HEATMAP · EGS · PRISM** (the 4th tab is variously transcribed "EGS" / "EGS" / "DEV"; treat as one product section, label unconfirmed — see §7).
  - Right-side utility controls: **"ORACLE GUIDE"** button (opens guide modal), **"CONSOLE BLOG"** button, a **bell/notification** icon (opens Alerts drawer), a **chart** icon button.
- **Oracle Sphere** (top of Oracle tab, above the 3-column grid): a glowing orb reading broad market sentiment. See §3.2 and §4.1.
- **Top status strip** (near sphere): `SIGNALS ACTIVE: <n>` · `AVG CONFIDENCE / WIN CONFIDENCE: <pct>` · `STATUS: ENGAGED` · `STREAM: <ticker>`.
- **Bottom status bar:** `ORACLE ONLINE` · `UPTIME: HH:MM:SS` · `SIGNALS: <n> ACTIVE` · `<n> MARKET CLOSED` · `ENGINE: UPFRONT V4.0`.

### 1.3 Oracle tab — three-column dashboard (desktop)
Per guide slide 1 (verbatim): Alert Stream drives the other two columns.

- **LEFT — ALERT STREAM:** master list of every active trade/signal, newest activity first. Clicking a card updates both center and right columns. Has its own sub-tab row (ANALYSIS / HISTORY) and a sort/expand control row.
- **CENTER — ANALYSIS:** full breakdown of the selected signal — ticker header + direction badge + lifecycle state, trade-geometry price bar (STOP/ENTRY/LIVE/T1/T2), **SIGNAL BRIEF — LIVE VIEW** (numbered actionable bullets), **5 PROFIT TAKING PLAN**, **SIGNAL THESIS** long-form text, and the asset chart.
- **RIGHT — CONFIDENCE INDEX:** live conviction gauge (degrees) + trigger-zone label + timestamp, **SIGNAL COMPONENTS** (5 bars), **TRADE GEOMETRY** (STOP LOSS / T1 TARGET / T2 TARGET / HORIZON), **RISK / REWARD at Entry** (ratio + $ risk + $ reward). Guide calls this cluster: confidence score + component bars + execution snapshot + thesis.

### 1.4 History sub-view (within Oracle tab)
When the LEFT sub-tab **HISTORY** is active, the CENTER column swaps to **ORACLE PERFORMANCE** (equity curve, overview metrics, performance breakdown, closed alerts). RIGHT column remains the Confidence Index. See §1.6.

### 1.5 Overlays / secondary surfaces
- **Alerts drawer** (right-side full-height overlay, opened by bell): header "ALERTS" + MARK READ + CLEAR + X; empty state message; alert rows when present.
- **Oracle Guide modal:** multi-section collapsible help panel (8 sections). See §5.4.
- **Macro Bias overlay:** center-panel regime panel (BULLISH/NEUTRAL/BEARISH) with a 3×3 asset-class matrix. Appears on launch or macro state change. See §3.2.
- **VIEWING dropdown** (History/Performance): selects which active signal drives the performance panel.

### 1.6 History center panel — ORACLE PERFORMANCE regions
1. Header row: **"ORACLE PERFORMANCE"** + **EXPORT CSV** button.
2. **"BETTER AVERAGE — LIVE"** header + live ticker row (SOFI/TNA/DIA/BTX/ASTS with price + % strip).
3. **OVERVIEW & EQUITY**: metrics grid (WIN RATE, AVG WIN, AVG LOSS, WIN RATIO, TOTAL RETURN) + **BEST TRADE** / **WORST TRADE** callouts + cumulative equity curve (green line, per-trade dots) + `TOTAL: +<pct>% TRADES <n>`.
4. **PERFORMANCE BREAKDOWN**: MONTHLY/QUARTERLY toggle + per-period table with expandable rows.
5. **CLOSED ALERTS**: historical signal ledger table (see §3.5).

### 1.7 Mobile evidence
None. All screenshots are desktop three-column layouts. Mobile behavior is unknown (§7, G12).

---

## 2. Complete Control Inventory

### 2.1 Primary navigation
| Control | Type | Options / Behavior |
|---|---|---|
| Primary tab row | tab set | ORACLE, FLOW, HEATMAP, EGS(/DEV), PRISM — switch product section |
| ORACLE GUIDE | button | opens 8-section guide modal |
| CONSOLE BLOG | button | opens blog/console (destination unconfirmed) |
| Bell / notification | icon button | opens Alerts drawer |
| Chart | icon button | function unconfirmed (likely toggles/expands center chart) |

### 2.2 Alert Stream (left) controls
| Control | Type | Options / Behavior |
|---|---|---|
| Sub-tab: ANALYSIS / HISTORY | tab toggle | ANALYSIS = live signals + center analysis; HISTORY = Oracle Performance panel |
| Sort toggle | cycling button (single control that cycles) | **NEW** (newest signal first) → **BEST** (best-performing trades in order) → **GAINERS / CONVICTION** (see note) |
| Expand/collapse-all toggle | button | expands or collapses all signal cards at once; cards collapsed by default |
| Signal card | clickable row | click loads that trade into CENTER + RIGHT columns; card also individually expands to reveal Oracle Option sub-card |

> **Sort-mode label reconciliation (IMPORTANT):** Across screenshots the third sort mode is labeled **"TRANSITION"** (early front screenshots), **"GAINERS"** (guide slide 3, verbatim: "lists trades from best to worst daily gainers"), and **"CONVICTION"** (2026-07-06 screenshot). The guide is the authoritative source → canonical set is **NEW / BEST / GAINERS**, but the product has shipped a **CONVICTION** variant. Confirm current live labels (§7, G1). Behaviors: NEW = sort by issue time desc; BEST = sort by trade performance; GAINERS = sort by daily % change best→worst; CONVICTION (if present) = sort by confidence score.

### 2.3 Alerts drawer controls
| Control | Type | Behavior |
|---|---|---|
| MARK READ | button (outlined) | marks all alerts read |
| CLEAR | button (red/danger) | clears all alerts |
| X | icon button | closes drawer |

### 2.4 History / Performance controls
| Control | Type | Options / Behavior |
|---|---|---|
| EXPORT CSV | button | exports performance/history data as CSV |
| MONTHLY / QUARTERLY | toggle | switches Performance Breakdown grouping |
| Period row expander (►) | per-row toggle | drills into individual trades within a period |
| VIEWING dropdown | dropdown | selects which active signal drives the performance panel; options = all currently active signals (observed: SOFI, TSM, DIA, RTX, ASTS); selected item highlighted |

### 2.5 Closed Alerts filter bar (historical log)
Two filter groups observed (behavior = filter the closed-alerts table):
- **Direction:** ALL · BULL · BEAR
- **Asset/source class:** ALL · STOCKS · OPTIONS · SMART · ALERT · SIGNAL
(Exact grouping and multi-select vs single-select unconfirmed — §7, G7.)

### 2.6 Guide modal controls
| Control | Type | Behavior |
|---|---|---|
| X CLOSE | button | dismisses guide modal |
| Section collapse arrow (▲/▼) | per-section toggle | collapses/expands each guide section |
| `admin@momoedge.ai` | mailto link | support contact (Quick Tips section) |

---

## 3. Data Model — Displayed Fields

### 3.1 Top status / system fields
| Field | Type/Unit | Semantics |
|---|---|---|
| SIGNALS ACTIVE | integer | count of live signals (observed 6, 9) |
| AVG CONFIDENCE / WIN CONFIDENCE | percent | system-wide mean confidence across active signals (66.8%, 66.9%) |
| STATUS | enum | `ENGAGED` = system live |
| STREAM | ticker | currently selected symbol (updates on card click) |
| UPTIME | HH:MM:SS | session uptime |
| ENGINE | string | `UPFRONT V4.0` / `SKYNET V4.0` |

### 3.2 Oracle Sphere / Macro Bias
| Field | Type | Semantics |
|---|---|---|
| Sphere glow color | enum | GREEN=Bullish, YELLOW=Neutral, RED=Bearish |
| Active signal count | integer | on sphere |
| Avg confidence score | percent | on sphere; "Above 70% is great" |
| Macro bias headline | enum | BULLISH / NEUTRAL / BEARISH + subtext ("Oracle is leaning long...") |
| Macro regime matrix | 3×3 grid | rows EQUITIES / BONDS / RISK APPETITE × cols DOLLAR INDEX / METALS / CRYPTO, each cell BULLISH/NEUTRAL/BEARISH |
| Regime summary | ratio | `60% BULL / 0% BEAR` |

### 3.3 Alert Stream signal card (collapsed → expanded)
Collapsed card fields (per guide slide 4): symbol · direction · live P/L since issue · days in trade · live price · T1 Progress Bar · Minimum Hold Bar.

| Field | Type/Unit | Semantics |
|---|---|---|
| Symbol | ticker | instrument |
| Direction badge | enum | `▲ BULL` (green, BUY/up) / `▼ BEAR` (red, SELL/down) |
| Live price + today % | $ + % | e.g. `$200.60 +0.68%` |
| Archetype tag | enum (open set) | signal type/phase pill: observed **Resumption** (amber), **Recovery** (teal); see §4.4 |
| ENTRY | $ | entry price of underlying |
| DAYS ACTIVE | integer d | days since signal issued |
| P&L pill | % | live gain/loss since issue (green/red) |
| Hold horizon label | duration | intended hold: `1 MONTH`, `3 MONTHS` |
| T1 PROGRESS | % + bar | progress toward T1: `70% → T1` with proportional green bar |
| Minimum Hold bar | `Xd / Yd min` + lock + status | days elapsed / minimum days; 🔒 = still in mandatory hold; status `HOLD` |
| TRIGGER | $ or badge | either `⚡ TRIGGER CONFIRMED @ $190.60` (green, trigger hit) or plain `TRIGGER: 18.85` (not yet confirmed) |

### 3.4 Oracle Option sub-card (revealed on expand)
| Field | Type/Unit | Semantics |
|---|---|---|
| ◆ ORACLE OPTION | label | section header (teal diamond) |
| CALL / PUT badge | enum | option type (CALL observed green) |
| Contract display | `<TICKER> <strike>` | e.g. `RTX $200` |
| EXP | date | expiration (e.g. `Aug 21`, `Oct 16`) |
| PREM | $ | entry premium paid (e.g. `$5.10`) |
| STRIKE | $ | strike price |
| NOW | $ + % | current premium + % gain vs entry (e.g. `$9.72 +90.7%`) |

### 3.5 Center — selected-signal analysis
| Field | Type | Semantics |
|---|---|---|
| Ticker + direction badge | ticker + enum | e.g. SOFI `+BULL` |
| Lifecycle state | enum | `PENDING TRIGGER` (amber) / `• TRIGGERED` (green) — see §4.3 |
| Price + today % | $ + % | underlying live price + daily change |
| Trade-geometry price bar | 4–5 levels | STOP · ENTRY · LIVE · T1 · (T2) with positional coloring |
| SIGNAL BRIEF — LIVE VIEW | numbered text | 3 actionable, dynamically-updating bullets ("What To Do Now") |
| 5 PROFIT TAKING PLAN | $ + label + status | target value, `T1` label, action (`Close`), `ACTIVE` badge; specifies proportion + price per exit level |
| SIGNAL THESIS | long text | Oracle-generated fundamental/technical reasoning for entry |
| Chart | chart | asset chart below analysis |

**Trade-geometry price-bar level semantics:**
- **Bull:** STOP (red, below) < ENTRY < LIVE < T1 < T2 (green, above).
- **Bear (inverted):** STOP (red, above) > ENTRY > LIVE > T1 (green, below).
- LIVE marker highlighted cyan = current price.

### 3.6 Right — Confidence Index
| Field | Type/Unit | Semantics |
|---|---|---|
| Confidence score | **degrees** | live conviction, e.g. `72.2°`, `80.3°`, `66.1°`; "Above 70%/70° = strong conviction" |
| Options-flow / SETUP number | integer (~71,314) | large number above gauge; changes slightly per refresh (e.g. `+9.2`, `→.1`); likely aggregate options-flow $ — see §7, G4 |
| Trigger-zone label | enum | `DEEP IN TRIGGER ZONE`, `P1 TRIGGER`, `GOLD IN TRIGGER ZONE`, `ONE TRIGGER` — tiered trigger classification, see §4.3 |
| Signal date / timestamp | datetime | `Jul 1, 2026 10:05 PM`, `As of 2026.06.09 06:09 AM` |
| SIGNAL COMPONENTS | 5 bars 0–100 | VALIDITY · PROGRESS · PACE · OVERLAP · (5th unlabeled/unconfirmed) — see §4.2 |
| TRADE GEOMETRY | rows | STOP LOSS, T1 TARGET, T2 TARGET, HORIZON — see below |
| RISK / REWARD at Entry | ratio + $ | R/R ratio (e.g. 1.95) + ENTRY TO STOP ($ risk/share or contract) + ENTRY TO T1 ($ reward) |

**Trade Geometry rows (right panel):**
- STOP LOSS: value + `AWAY` (distance to stop; unit % or $, unconfirmed — §7, G5).
- T1 TARGET / T2 TARGET: distance to targets (same unit).
- HORIZON: `% USED` — time elapsed vs total intended duration (0% early → 62% mid-life).

### 3.7 Oracle Performance (History)
| Field | Type/Unit | Semantics |
|---|---|---|
| WIN RATE | % (+ NW/NL) | e.g. `66.2% (96W/49L)` — raw win/loss counts exposed |
| AVG WIN / AVG LOSS | % | mean winning / losing trade return |
| WIN RATIO | days? | `10.7d` (label ambiguous — possibly avg hold or win/loss ratio; §7, G8) |
| TOTAL RETURN | % | cumulative (`+1231.6%`) |
| TRADES | integer | total count (145 / 148 across shots) |
| AVG RETURN | % | per-trade mean (`+8.5%`) |
| AVG DAYS | days | mean hold (`11d`) |
| BEST TRADE | ticker + tag + % | `TER — Breakout +134.6%` |
| WORST TRADE | ticker + % | `BABA — <neg>` |
| Equity curve | series | cumulative P&L% over time, per-trade green/red dots |

**Performance Breakdown table columns:** PERIOD · TRADES · WIN RATE (with `NW/NL`) · TOTAL RETURN · AVG RETURN · AVG DAYS. One row per month (MONTHLY) or quarter (QUARTERLY) + ALL TIME summary; rows expandable to individual trades. Full monthly dataset (OCT 2023 → JUL 2026, ALL TIME 145 trades / 66.2% / +1231.6% / +8.5% / 11d) transcribed in source `oracle_2.md` "Performance Breakdown.png".

### 3.8 Closed Alerts table
Columns: Ticker (+ green=bull/red=bear dot) · Company · SIGNAL (BULL/BEAR pill) · OPENED (MM-DD-YYYY) · STOCK % · OPT % · STATUS · DAYS.
STATUS enum: `INVALIDATED` (amber; signal failed/reversed) / `CLOSED EARLY` (grey-teal; rule/manual early close). OPT % tracks option P&L separately from underlying STOCK %. Many signals = 30-day.

### 3.9 VIEWING footer metrics
`-3.37% - 1.6R` (stop %/R-multiple risk) · `+1.31% P&L` (current options P&L) · `LIVE`.

---

## 4. Scoring / Legend / Tier Semantics (verbatim where transcribed)

### 4.1 Oracle Sphere color legend (verbatim, guide slide 2)
- "GREEN — Bullish: favorable conditions for long positions"
- "YELLOW — Neutral: mixed signals, proceed with caution"
- "RED — Bearish: defensive positioning recommended"
- "The sphere also shows the number of active signals as well as the average confidence score across all signals. Above 70% is great."

### 4.2 Confidence Index (verbatim, guide slide 6)
- "The right panel shows Oracle's live proprietary confidence score index which assesses a trade signal using a comprehensive list of factors to compute a live confidence score."
- "A trade is initially issued with a base score and updates as time goes on or the trade progresses toward T1. The pace to T1, time decay, overall market environment, retention of price movements, and more are all factored into the confidence index."
- "Signal Components: underneath the confidence score, the individual scores of the 5 separate components used to compute the overall live confidence score are shown as component bars."
- "Trade Geometry: underneath the signal components, this shows the current live risk/reward at the time of viewing."
- **Explicit threshold:** scores above 70% indicate strong conviction (guide slide 8).
- Observed 4 named component bars: **VALIDITY, PROGRESS, PACE, OVERLAP** — guide states there are **5**; the 5th is not transcribed (§7, G3).

### 4.3 Signal lifecycle / trigger-zone tiers (observed labels)
- Center lifecycle states: **PENDING TRIGGER** (amber, not yet triggered) → **• TRIGGERED** (green, entry trigger hit). Alert-stream also shows an **ENTRY DEAL** phase and **TRIGGER CONFIRMED**.
- Right-panel trigger-zone labels (appear tied to score bands): **P1 TRIGGER**, **DEEP IN TRIGGER ZONE**, **GOLD IN TRIGGER ZONE**, **ONE TRIGGER**. Exact band thresholds unconfirmed (§7, G6).
- Eligibility: alert-stream `<count> / <count> min = ELIGIBLE` — ratio ≥100% flips card to ELIGIBLE.

### 4.4 Signal archetype tags (open enum)
`Resumption` (amber), `Recovery` (teal), `Breakout` (seen in Best Trade). Named signal-type/phase pills. Full enumeration unknown (§7, G2).

### 4.5 Reading Signal Cards (verbatim, guide slide 4)
- Collapsed card: "the symbol of the instrument being traded, the direction ( BUY + up, SELL + down), the live P/L since the signal was issued, the days in trade and the live price of the asset."
- "T1 Progress Bar: T1 is the first target price of the trade. As the trade progresses or reverses, this progress bar adjusts accordingly in real-time."
- "Minimum Hold Bar: every trade has a minimum recommended hold time..."
- "[GREEN] Neither T1 nor minimum hold time reached: hold the trade"
- "[GREEN] Either T1 or minimum hold time reached: exit allowed"
- "We will typically hold a trade for the minimum hold time or until T1 is reached. If T1 isn't reached but minimum hold time is, we reassess the trade and either hold or close it."
- "Expanding a card reveals the Oracle option recommendation. The precise strike price and expiration the Oracle recommends for this trade bias. The option's live P/L is tracked in real-time."

### 4.6 Execution Snapshot & Thesis (verbatim, guide slide 7)
- "The trade direction is reaffirmed by a badge showing [BULL] or [BEAR] bias."
- "• Signal Date: date and exact time the signal was issued"
- "• Entry Price: price of the underlying asset when signal was issued"
- "• Live Price: current live price of the underlying asset"
- "• P/L From Entry: unrealized gain or loss since entry"
- "Risk / Reward at Entry: shows the risk/reward ratio at the time the signal was issued. It displays the dollar amount of risk per share or contract as well as the expected reward at T1."
- "Signal Thesis: Oracle's reasoning for entering the trade. These are the fundamental and technical factors that triggered the signal."

### 4.7 Analysis center (verbatim, guide slide 5)
- "Oracle Analysis: detailed information on how to enter the trade, when to adjust stops, when to add to the position, and more. This assessment adjusts dynamically to the trade's progress and market conditions."
- "What To Do Now: actionable next steps based on where the trade currently stands."
- "Profit Taking Plan: details what proportion of your position to close at what price levels."
- "Chart: below the analysis, you'll see the current chart of the asset being traded."

### 4.8 Alert Stream (verbatim, guide slide 3)
- "NEW — shows the newest signal first / BEST — shows best-performing trades in order / GAINERS — lists trades from best to worst daily gainers"
- "Signals are collapsed by default so you can quickly scan the list."

### 4.9 Quick Tips (verbatim, guide slide 8)
- "Click any signal in the Alert Stream to load its full analysis"
- "Use the sort toggle to find the best-performing or newest signals"
- "Watch the Confidence Index: scores above 70% indicate strong conviction"
- "Follow the Profit Taking Plan: don't deviate from Oracle's exit levels"
- "Respect the Minimum Hold Time: early exits often miss the move"
- "The Signal Thesis explains why Oracle entered, so read it to understand the trade"

---

## 5. States & Interactions

### 5.1 Selection / click-through
- Clicking any Alert Stream card sets it as `STREAM: <ticker>` and updates CENTER (analysis/chart) + RIGHT (confidence + snapshot + thesis). One selection at a time.
- Cards collapsed by default; individual expand reveals Oracle Option sub-card; expand/collapse-all toggle acts on all.

### 5.2 Empty states
- **Alerts drawer empty:** "No alerts yet. You'll see alerts here when targets hit, triggers confirm, or signals approach invalidation." (implies 3 alert trigger types).

### 5.3 Live/real-time behavior
- T1 Progress bar, Minimum Hold bar, live price, option NOW premium, confidence score all update in real time.
- Confidence score initialized at base value at issue, then evolves.
- Macro Bias overlay appears on launch or macro state change.

### 5.4 Guide / tutorial overlay (8 sections, collapsible)
1. WHAT THE ORACLE TAB SHOWS · 2. ORACLE SPHERE & MARKET SENTIMENT · 3. ALERT STREAM (LEFT) · 4. READING SIGNAL CARDS · 5. ANALYSIS (CENTER) · 6. CONFIDENCE INDEX (RIGHT) · 7. EXECUTION SNAPSHOT & THESIS · 8. QUICK TIPS. Modal has X CLOSE; each section has ▲/▼ collapse; icons per section (diamond, star, lightning, gem, target/crosshair, bar-chart, lightbulb).

### 5.5 Hover / keyboard
- No hover tooltips or keyboard shortcuts evidenced (§7, G11).

---

## 6. Engine Inferences (observed or strongly implied)

- **Confidence score** = composite, expressed in **degrees** (0–~90° gauge), base at issue, evolving with: pace to T1, time decay, market environment, price-movement retention, + more. 70° = strong-conviction threshold. Built from 5 weighted component sub-scores (VALIDITY, PROGRESS, PACE, OVERLAP, +1).
- **Trade geometry / R:R:** R/R ratio ≈ (T1 − Entry) / (Entry − Stop) in absolute terms (bull); inverted for bear. ENTRY TO STOP and ENTRY TO T1 are $ per share/contract, entry-time snapshot (static). Sample checks: SOFI 1.95, RTX 1.06, ASTS 1.88, DIA 1.43.
- **HORIZON** = time-based progress (% of intended duration elapsed).
- **Minimum Hold** = time gate (`Xd / Yd min`); exit "allowed" once T1 OR min-hold reached; 🔒 while locked.
- **Eligibility** = `count/count` ratio ≥ 100% → ELIGIBLE.
- **Options recommendation** engine emits a specific contract (type/strike/expiry) per signal, tracked to live premium (NOW vs PREM).
- **Trigger tiers** (P1 / DEEP / GOLD / ONE) map to score/proximity bands.
- **Closure taxonomy:** INVALIDATED (failed/reversed) vs CLOSED EARLY (rule/manual). Many signals default to 30-day windows.
- **Macro regime engine:** 3×3 asset-class matrix → aggregate `%BULL / %BEAR` → sphere color + macro headline.
- **Signal archetypes** (Resumption/Recovery/Breakout) = named setup classifiers driving brief language.

---

## 7. Gap List — Unknowns a builder must confirm

- **G0.** Prior competitive study `MOMOEDGE_ORACLE_COMPETITIVE_FEATURE_STUDY_FOR_FABLE.md` was absent from this worktree; reconcile this spec against it if located.
- **G1.** Third Alert-Stream sort label is inconsistent (TRANSITION / GAINERS / CONVICTION). Confirm the current live set and whether it's 3 or 4 modes; confirm cycle-button vs separate-tabs.
- **G2.** Full enumeration of signal archetype tags (Resumption, Recovery, Breakout, …) and their color mapping.
- **G3.** Identity of the **5th** Signal Component bar (only 4 named).
- **G4.** Meaning/units of the large **SETUP / ~71,314** number above the confidence gauge (options-flow $? cumulative flow?).
- **G5.** Unit of Trade-Geometry `X.XX AWAY` rows (% vs $) and of the STOP LOSS / T1 / T2 rows.
- **G6.** Exact score bands for trigger-zone tiers (P1 / DEEP IN / GOLD IN / ONE TRIGGER) and how ENTRY DEAL / PENDING / TRIGGERED / CONFIRMED sequence.
- **G7.** Closed-Alerts filter bar grouping — which chips are direction vs class, single vs multi-select, and definition of SMART / ALERT / SIGNAL.
- **G8.** "WIN RATIO 10.7d" label meaning (avg hold vs a ratio) and why two WIN RATE rows appear in Overview (options vs underlying?).
- **G9.** Exact confidence-score formula and per-component weights (proprietary; guide only names factors).
- **G10.** Alert generation rules: what counts as "target hit / trigger confirm / approaching invalidation"; alert row schema.
- **G11.** Hover tooltips, keyboard shortcuts, and per-card right-click/context actions — none observed.
- **G12.** Mobile/responsive layout — no evidence.
- **G13.** Data feed cadence (real-time push vs poll), and whether option NOW premium is live NBBO or delayed.
- **G14.** EXPORT CSV schema; CONSOLE BLOG destination; chart icon function; VIEWING-dropdown effect scope.
- **G15.** How T2 is surfaced in Profit Taking Plan (only T1 shown as ACTIVE in shots) and multi-target scaling proportions.
