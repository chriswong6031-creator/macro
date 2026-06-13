# Bitcoin Vector — Framework Skeleton (reverse-engineered)

Source: visual analysis of the 10 product screenshots on glassnode.com/pricing/vector
(saved in `research/vector_images/`), page copy, and CSS. Date: 2026-06-12.

Their product is Telegram-delivered scorecards (images/PDFs), NOT a dashboard.
Ours will be a live dashboard page that renders the same components daily.

---

## 1. Design language (from screenshots + CSS)

- **Theme: LIGHT** (unlike macro dashboard's dark). Backgrounds `#F7F8FA`/`#F9FAFB`/white,
  cards = white with 1px `#EAECF0` border, large radius (~16px), generous whitespace.
- **Font: Inter** (Next.js optimized). Headlines bold ~28–40px; "Risk **OFF**" headline style =
  the state word in light periwinkle, the rest in gray. Section titles bold black ~20px.
- **Palette:**
  - Primary blue `#285FFF` / `#1F5EFF`; dark indigo `#4559DC`
  - Blue ramp (gauges, gradients, light→dark): `#E2E7FC → #B8C6FA → #8FA5F6 → #6888FB → #285FFF`
  - Text gray `#344054` / `#3D414B`; muted `#6F6F6F` / `#A0A0A0`
  - Red accents `#D30B0B` / `#FEB5B5` (bearish highlight boxes); amber `#F5AD42`
- **Signature elements:**
  - Two-tone series coloring: line is DARK blue in healthy/low-risk state, LIGHT blue in
    elevated state (Risk Index, price during broken structure)
  - Gray vertical shading bands on charts = "Risk = 0" periods (value-1/2, expert-3) or
    "Flash Crash period" (flash-2/3)
  - Bull/Bear **chips**: dark indigo fill = Bull, light periwinkle fill = Bear
  - **Conviction dots**: 3 circles, filled count = conviction strength
  - **Gradient slider gauges** with labeled stops and a knob
  - Current-value **badges** pinned to chart right edge (e.g. `71K`, `34`, `0.53`)

## 2. Information architecture (our build)

```
site/
  index.html      → NEW landing hub: two entry cards (Macro Dashboard | Bitcoin Vector)
  macro.html      → current macro dashboard (renamed from index.html; brief/history stay linked)
  vector.html     → Bitcoin Vector dashboard (light theme, all components below)
```

Vector reads macro-dashboard parquet data for the cross-asset card (one repo, one CI run:
collect → engine → vector engine → build_site).

## 3. Component catalog (exactly what's in their scorecards)

### A. Market State header (from chart-expert-1, "Market State")
- **Long term block:**
  - Giant state headline: `● Risk OFF` + change since last report (`▲ +3%`) + label `High Risk`
  - One-line narrative: "Cooling off, but still High Risk."
  - **Cycle-stage slider**: 4 gradient segments `Defensive | Fragile | Recovery | Expansion`
    with knob position (continuous)
  - 3 sub-gauges as text pairs: `Momentum: Weak` · `Volatility: Low` · `Flow: Low`
- **BTC Allocation bar** (Moderate Strategy, 1 Day): gradient pill showing `100% Cash`
  (or % BTC / % Cash split)
- **Mid term block:** `Environment Now: [Bull]` chip + `Environment Probability next 7d`:
  `[Bear] 35%  [Bull] 65%` chips with percentages
- **Short term block — Scenarios (3 days):**
  - Bear scenario: chip + probability bar `75%` + `Target: BTC < 67.6K` + Action sentence
  - Bull scenario: chip + probability bar `25%` + `Target: BTC > 70.4K > 71.9k` + Action sentence
  - (Their action text is analyst-written; ours = mechanical levels + templated or LLM-written text — D33 rescinded 2026-06-13)

### B. Long Term page (chart-expert-3, "01 Long Term — 1 month horizon")
- Top strip of 4 mini-cards:
  1. Risk gauge (the Defensive/Fragile/Recovery/Expansion slider, small)
  2. `Momentum: Weak` — Weak↔Strong mini slider + `178 days in this regime` +
     trigger proximity: "Improving. Close to bullish trigger"
  3. `Volatility: Low` — `Low | Sweet spot | High` slider + qualifier "Upside Volatility"
  4. `Flow: Low` — `Low | Sweet spot | High` slider + qualifier "Upside Flow"
- **BTC Risk Index chart (multi-year):** BTC price (log-ish) with gray `Risk = 0` bands,
  Risk Index subpanel (0–100, gridlines 0/25/50/75/100), current-value badge, dashed
  projection arrow on recent direction
- Right rail: short narrative paragraph with bold key phrases

### C. Investor Strategy card (chart-moderate-1 — their daily Insights scorecard)
- Strategy variant chips: `Optimal | Aggressive | Moderate | Conservative` (selectable)
- **Allocation donut**: Bitcoin X% / Cash Y% (current)
- Stacked 1Y panels, each with current-value badge:
  1. Bitcoin Price (1Y), $ axis
  2. Moderate Strategy allocation (1Y): step series in {0, 0.5, 1}
  3. Risk Index (1Y): two-tone coloring, axis 0/25/50/75/100
  4. Strategy performance vs `BTC Hold` (both normalized to 1), with metrics row:
     `Sharpe 0.22 · Max Drawdown -14.48% · Sortino 0.31`
- Footer: data-source attribution

### D. Risk Index vs Strategies chart (value-1/2, moderate-2 — the marketing money-shot)
- 3 stacked aligned panels, multi-year: Price + strategy equity (top), Risk Index (mid),
  Allocation (bottom); gray bands where risk pinned high / allocation 0; highlight boxes
  (blue = captured upside, red = avoided drawdown)

### E. Cross-Asset Regime Map (chart-expert-2, "Cross assets Context")
- **Crypto Recap** status row: `● Risk OFF · ● Weak Momentum · ● High Risk`
- 3 tables — Index: `S&P500, Nasdaq, Dow Jones, DXY`; Commodities: `Gold, Silver, UK Oil`;
  Crypto: `BTC, ETH, SOL, Alts`
- Columns: Asset | `Trend (3 days)` Bull/Bear chip | `Conviction` (3 dots, 1–3 filled)

### F. Structure Shift (chart-flash-1, "Flash Update: Structure Shift Bullish Trigger")
- BTC price line colored by structure state (dark = constructive, light = broken)
- **Structure Shift oscillator** in [-1, +1], dashed threshold ≈ +0.5, current badge (0.53)
- Annotations: vertical dashed lines at triggers, arrows + day-counts between
  trigger episodes ("60 days", "40 days", "53 days"), `Bullish trigger` flag at crossing

### G. Flash Crash Index card (flash-2/3)
- Headline state machine: `Flash Crash Index changed to: <state>` — observed states:
  `tail risk event` (↘ icon), `stabilizing price` (→ icon); implies a normal/no-event state
- BTC price + 24h % change
- **Impulse: positive / negative** label (short-term directional impulse)
- 30-day price chart with shaded `Flash Crash period` bands

### H. Alerts (Telegram) — reuse scripts/notify.py
- Flash Crash state change; Structure Shift trigger (bullish/bearish); Risk regime cross
  (25 threshold); allocation change; environment flip. Idempotent via engine/alerts.py pattern.

## 4. Signal inventory to build (the actual quant work)

| # | Signal | Output | Drives components |
|---|--------|--------|-------------------|
| 1 | **Risk Index** | 0–100, threshold 25; two-tone | A, B, C, D, E recap |
| 2 | **Momentum score** | [-1,+1], ±0.5 triggers; Weak/Strong label; days-in-regime; trigger distance | A, B, E recap |
| 3 | **Structure Shift** | [-1,+1] oscillator + trigger events + episode durations | F, H |
| 4 | **Volatility regime** | Low / Sweet spot / High + upside/downside qualifier | A, B |
| 5 | **Flow regime** | Low / Sweet spot / High + qualifier (volume/flow proxy) | A, B |
| 6 | **Cycle stage** | continuous position over Defensive/Fragile/Recovery/Expansion | A, B |
| 7 | **Environment classifier** | Bull/Bear now (mid-term, ~1w) | A |
| 8 | **Environment probability (7d)** | P(Bull), P(Bear) | A |
| 9 | **Scenarios (3d)** | P(bear)/P(bull) + mechanical price targets (S/R, ATR bands) | A |
| 10 | **Flash Crash state machine** | normal → tail risk event → stabilizing price → normal | G, H |
| 11 | **Impulse** | positive/negative (short-horizon return impulse) | G |
| 12 | **Allocation model** | {0, 0.5, 1} per strategy variant (Conservative/Moderate/Aggressive/Optimal) from momentum × risk | A, C, D |
| 13 | **Cross-asset trend+conviction** | per asset: Bull/Bear (3d) + conviction 1–3 | E |
| 14 | **Performance metrics** | Sharpe, Sortino, MaxDD (1Y) strategy vs HODL | C |

Calibration rule (house style): every signal gets measured forward-return records by band
(split-half robustness), published in tooltips; anything that fails = "context, not signal".

## 4c. Additions adopted from Hawkeye analysis (see HAWKEYE_NOTES.md)

Vector is confirmed to be the retail skin of Swissblock's Hawkeye dashboard.
Core-build additions extracted from Hawkeye imagery: BTC-vs-Alts cycle regime
(3-tier v1), Tactical/Strategic allocation regime, alert-card anatomy
("changed to:" + state bar + month ribbon) as the timeline template,
scenario validation/invalidation zones, S/R step-lines + 7d range-position
slider on the daily price card, rolling correlation mini-panel, and a
cost-basis buy-zone ladder (Vector Lite's "optimal buy prices"). Deferred:
risk×momentum quadrant scatter, Market Effects factor panel. Signal inventory
additions: #15 BTC-vs-Alts cycle, #16 Tactical/Strategic regime, #17 S/R levels
+ buy-zone ladder, #18 rolling correlations.

## 5. Honest deltas vs their product

- Their Risk Index is proprietary on-chain composite (entity-adjusted). Ours = free-data
  composite (MVRV-z, supply-in-profit, SOPR proxies, leverage, realized vol) — behaviorally
  similar, not identical.
- Their short-term targets/action text are analyst-written. Ours are mechanical levels with
  templated wording.
- "Expert Analysis" twice-weekly essays are out of scope; the daily brief generator covers it.
