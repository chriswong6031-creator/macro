# Vector/Hawkeye signal reconstruction — deep recon (2026-06-13)

Goal: match their signals at component level, not just behavior level. Key source:
Swissblock's FREE Compass posts on substack leak their real internal panels with
13 months of signal history + named components. Panels saved in
`research/swissblock_panels/`. D33 rescinded — LLM allowed anywhere; signals
keep mechanical cores so they remain backtestable.

## 1. Their component inventory (now evidence-based, not inferred)

From Compass #173 ("The Double-Edged Sword", 2025-04-29, full free post with
8 real panels) + Vector marketing + BVL previews + news quotes:

### Risk family
- **Bitcoin Risk Index** — 0–100, red>25/blue<25 two-tone, **pins at 0 for whole
  quarters** (Oct24–Jan25 bull leg), spikes to 100 in corrections (Jul24, Sep24).
  News: *negatively correlated with ETF flows since Nov 2023* → ETF flows are an
  input or near-proxy. Saturating weighted composite.
- **Risk Oscillator** — [0,1], **parks at exactly 0.50 when quiet** (mechanical
  neutral state), swings 0.2–0.85; "holding ~0.5 sets stage for healthy structure".
  Likely bounded momentum-of-risk / short-horizon instability gauge.
- **Market Risk Indicator** — third member, "declining" = stabilizing (slower).
- **Key Risk Elements** — decomposition panel:
  - **intraday volatility vs interday volatility** split (their words: intraday↓
    + interday↑ = "momentum stalled, profit-taking intensified")
  - loss-selling level ("loss-selling still low but rising") = realized-loss/SOPR class
  - cohort exit behavior: "buyers who entered around $94–95K… exiting with small
    gain or limited loss" = STH cost-basis cluster analysis

### Momentum family
- **Bitcoin Price Momentum** — [-1,+1], blue/red by sign, **pins at ±1 for
  weeks**, mid-range churn otherwise → ensemble-vote architecture confirmed.
  Narrative ties it to *selling pressure fading/intensifying*, so SOPR-class
  inputs sit alongside trend inputs. Vector's ±0.5 = bull/bear trigger.
- **Structure Shift** — [-1,+1] (from Vector flash cards; same vote family).

### Fundamentals family
- **BFI (Bitcoin Fundamental Index)** — 0–100 with **bands at 40/60**: red <40
  (negative), "neutral channel" 40–60, blue >60 (positive). Slow composite.
  Stays ≥ neutral through Feb–Mar 25 pressure = their long-term bull anchor.
- **Network Growth vs Liquidity** — the two engines under BFI. Both rendered as
  20–80 oscillators (percentile-style) with current badges (NG=43, Liq=54 on
  2025-04-29). Narrative: "mid-Feb marked the bottom in liquidity, steady inflow
  since"; "participant count declined (STH exiting)".
  → NG = address/participant growth momentum; Liq = capital inflow composite
  (realized-cap inflows / stablecoins / ETF flows / exchange flows).

### Levels methodology (the "zones" recipe)
- **"Bitcoin's Price in Context"** panel = price + TWO side histograms:
  **On-chain volume by price (URPD/cost-basis distribution)** and **trading
  volume profile**. Zones ($94–95K mid-range "point of control", $89–92K
  "zone of interest", $97–98.5K boundary) come from cost-basis + volume-profile
  clusters — fully mechanical, replicable.
- BVL012: "upside **short-liquidation targets** ~$113.1k / ~$114.7k" → they also
  use liquidation clusters; free proxy = OI+funding-derived estimates (approximate)
  or skip precise liq maps (Coinglass-paid). Non-critical.
- TradingView used for tactical S/R boxes (nothing exotic).

### UI details worth copying
- **Speedometer gauges with TWO dots: current (filled) + one-week-ago (white)** —
  instant "what changed this week" without reading a chart.
- Every panel: BTC price in gray behind the signal, current-value badge at right
  edge, "Data source: Swissblock Technologies" footer, timestamp UTC.

## 2. Our matching implementation (per component, all free-verified)

| Their component | Our build | Data |
|---|---|---|
| Network Growth | percentile oscillator (20–80 scale) of active+new address momentum | CM `AdrActCnt` 2010→; bgeo sender/receiver addresses |
| Liquidity | percentile composite: realized-cap 30d Δ (CM-derived), stablecoin supply Δ (DefiLlama), ETF flows (bgeo), exchange netflow (bgeo) | all verified |
| BFI | 0–100 blend of NG+Liq with 40/60 bands, slow smoothing | derived |
| Key Risk Elements | intraday vol = Parkinson/Garman-Klass from OHLC; interday vol = close-to-close σ; loss-selling = realized-loss + SOPR<1 streaks; cohort exits = STH-SOPR + nrpl-sth | Coinbase hourly/daily OHLC; bgeo |
| Risk Index | saturating weighted composite: vol regime + drawdown + interday/intraday split + loss-selling + leverage (funding, OI/mcap) + ETF-flow stress; floor-clamped at 0 | calibrated vs digitized series |
| Risk Oscillator | bounded short-horizon risk-momentum, neutral-parked at 0.5 under quiet conditions | derived |
| Price Momentum | vote ensemble: trend conditions (EMA slopes, MACD, cost-basis crossovers) + selling-pressure conditions (SOPR momentum, netflow) → mean vote in [-1,+1] | Yahoo + bgeo |
| S/R zones | URPD clusters (bgeo `/v1/urpd` ✅ exists) + volume profile from candle history → zone bands, range midpoint/POC logic | bgeo + Coinbase |
| Liquidation targets | OI/funding-cluster approximation, labeled approximate — or omitted | OKX/bgeo |

## 3. Screenshot digitization (committed Phase 2 step — user approved)

Pixel-extract series by color from clean flat-color charts; map axes; save as
parquet fixtures under `data/fixtures/swissblock/` with provenance + capture date.

Inventory of digitizable ground truth already in repo:
| Series | Image | Range |
|---|---|---|
| Risk Index | `swissblock_panels/fe675282…` | Apr 2024 – Apr 2025 |
| Risk Index | `vector_images/chart-moderate-2.png`, `chart-value-*.png` | ~Nov 2024 – Mar 2026 |
| Price Momentum | `swissblock_panels/605ed6f3…` | Apr 2024 – Apr 2025 |
| Risk Oscillator | `swissblock_panels/1aa9a470…` | Apr 2024 – Apr 2025 |
| BFI | `swissblock_panels/b0a92c01…` | Apr 2024 – Apr 2025 |
| NG vs Liquidity | `swissblock_panels/a08e3754…` | Apr 2024 – Apr 2025 |
| Allocation ribbon (Moderate) | `vector_images/chart-moderate-*.png` | 2025 – 2026 |
| Structure Shift | `vector_images/chart-flash-1.png` | Oct 2025 – Mar 2026 |

**Expansion source:** every free Compass post on swissblock.substack.com carries
the same panels at different dates → enumerate via `sitemap.xml`, harvest panels
+ dated badge readings. Builds a multi-year anchor set without any subscription.

Validation metrics (Phase 2 calibration report): state-agreement % (risk
high/low, momentum sign), event-timing deltas (days between their flip and ours),
and correlation of levels. Targets: ≥80% state agreement, median timing delta ≤5d.

## 4. Dated-readings ledger (ground truth from public quotes)

Seed entries (to be grown to 30+ in Phase 2 from news/X archives):
- 2025-04-29: Risk Index → 0 (falling from high-risk since late Feb, lower highs);
  Risk Osc ~0.45; BFI neutral; NG=43, Liq=54; resistance 94–95K, zone 89–92K (Compass 173)
- 2025-09-11: BTC $114k; short-liq targets 113.1k/114.7k hit (BVL012)
- 2026-04-x: Momentum = 1, Risk = 0 → "excellent window for strategic
  accumulation" (Bitget/WEEX coverage of Vector)
- 2026-03-25±: Flash Crash Index: tail risk event (−4.61% 24h) → stabilizing
  price (−3.35% 24h), Impulse negative (Vector cards)
- 2026-06-10: BVL051 "capitulation, revisited $60k zone first time since Feb"
- 2026-06-12: their Vector charts show Risk pinned ~100, allocation 0, BTC ~70K→63K

## 5. Updated fidelity estimates (post-recon)

| Signal | Pre-recon | Now | Why |
|---|---|---|---|
| Risk Index | medium-high | **high** | 2yr digitizable target + component list + ETF-flow correlation hint |
| Momentum | high | **high+** | architecture + 13mo target series + selling-pressure inputs confirmed |
| BFI / NG / Liquidity | (unknown) | **high** | axes, scales, bands, and inputs all read off their own panels |
| Risk Oscillator | (unknown) | **medium-high** | behavior fully observed; exact construction inferred |
| S/R zones | medium | **high** | URPD + volume profile = their visible method; bgeo has URPD |
| Liquidation targets | — | low/skip | needs liq-map data (paid); approximate or omit |

Fallback (user-approved): if calibration against digitized series stalls, get a
Hawkeye demo or 1-month Vector sub ($749) for true daily series → backtest-fit.
