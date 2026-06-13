# Swissblock Hawkeye — feature extraction (analyzed 2026-06-13)

Sources: swissblock.net product pages (hawkeye, sem, expert-insights) + the
Willy Woo substack launch post. 17 images saved in `research/hawkeye_images/`.
Companion to `VECTOR_SKELETON.md` (Vector spec) — this doc is the **v2 idea mine**.

## Confirmed: Vector is Hawkeye's retail skin

- Hawkeye's alert examples live under `/bitcoin-vector/alerts/` on swissblock.net —
  same engine, same cards.
- Hawkeye copy: "Investor Strategy aligns asset allocation ... dynamically
  adjusting exposure to **Bitcoin, Altcoins, and Cash** across market phases" —
  the donut we saw (80/5/15) is **3-way**, not BTC/Cash. Vector's BTC/Cash
  version is the simplification.
- Product family: Hawkeye (institutional dashboard, demo-only) → Bitcoin Vector
  ($749/mo Telegram) → **Bitcoin Vector Lite** ($29/mo weekly Substack, with
  Willy Woo, launched Aug 2025). FAQ confirms the engine: "macro regimes,
  liquidity conditions, dominance dynamics, and momentum signals into a unified view."

## What the screenshots show (catalog)

| Image | Contents |
|---|---|
| `hawkeye_asset-screener` | Web app: Overview/Asset Screener nav; filters (Reference asset BTC/ETH/SOL, Strategy High-Risk/Neutral/Low-Risk, Time Horizon S/M/L); **Quadrants 2×2 scatter (RISK AREA / HOT OPPORTUNITY / RECOVERY / WARMING UP)**; "Factors Outperformer: Mean Reversion ▼50%" + chips (Breakout, Mean R., Up Beta); **Impulse: Positive 34% / Negative 100% bars**; asset table w/ Numbers↔Charts toggle |
| `hawkeye_comparison` | Asset Comparison view: dual-asset overlay; right rail of 0–1 gauges: **Support/Resistance position, Spot CVD, Perpetuals CVD, Open Interest** (selling↔buying pressure); **Correlation panel** (pairwise 30d-ish: 0.89 / −0.07 / 0.12); sub-chart toggles RSI/CVD/UpB; dark-mode toggle + API menu |
| `hawkeye_slide1` | Investor Strategy card: Optimal/Aggressive/Moderate/Conservative chips + **3-way donut (80/5/15)** + "SB Strategy Performance" tab |
| `hawkeye_slide2` | **"Market Effects"** panel: 3 named effects (Mean Reversion, Breakout, Up Beta) as cards + their PnL lines over time ("Market Effects with PnLs") |
| `hawkeye_slide3` | Stacked: Bitcoin Price / **"BTC vs Alt Cycle"** step-regime ribbon / "SB Strategies" allocation lines |
| `bitcoin-vector_alerts_block1` | Alert card: **"Market Allocation changed to: Tactical"** — binary Tactical(red)/Strategic(blue) regime + state bar + last-month price chart with regime ribbon + price badges |
| `bitcoin-vector_alerts_block2` | Alert card: **"BTC vs Alts Cycle changed to: Bitcoin"** — 5-tier regime **BTC / ETH / Large / Mid / Small Caps**, segmented state bar + month ribbon |
| `bitcoin-vector_alerts_block3` | **Daily "Bitcoin Price update" card**: price, 24h%, **7d-range slider** ($74.8K–$95.6K w/ position dot); chips: Market Regime=Tactical, BTC vs Alt cycle=Bitcoin, Factor Outperformer=Up Beta; 1-month chart with **dotted Support & Resistance step-lines**; mini ribbons (Regime, BTC vs Alts) |
| `bitcoin-vector_alerts_block4` | Alert card: "Risk Off Signal changed to: High Risk" — 0–100 bar with 25 marker; month chart with risk line **two-toned at the 25 threshold** (blue below / red above) |
| `sem_market-cycles` | SEM: business-cycle sine (Expansion→Slowdown→Contraction→Recovery) + leading/coincident/lagging indicator positions |
| `sem_info-feature_1` | SEM: Elliott-wave projection with **"Validation Zone" / "Invalidation Zone"** dashed levels + "Now" marker |
| `sem_info-feature_3` | SEM: analyst chat (Henrik Zeberg Q&A) — human product |

Willy Woo substack: Vector Lite = weekly briefing, macro-cycle position, and
**"Optimal Prices to Buy BTC — buy-the-dip price targets"** per issue.

## Adoption decisions

### Adopt into core build (free data, high value)
1. **BTC vs Alts Cycle regime** — start 3-tier (BTC / ETH / Alts) from CoinGecko
   dominance + ETH/BTC + alt-aggregate RS; 5-tier (Large/Mid/Small) later via
   CoinGecko category mcaps. New ribbon panel + cross-asset card column + alert type.
2. **Tactical/Strategic allocation regime** — named binary regime over the
   allocation model (Strategic = trend-following exposure OK; Tactical = chop/
   risk-off, defensive). Ribbon + alert. Maps cleanly onto momentum×risk states.
3. **Alert-card anatomy as the timeline template** — "X changed to: Y" headline +
   segmented state bar + last-month context chart with regime ribbon. Extends
   VECTOR_ALERTS_DESIGN.md entries (expandable rows get the mini ribbon chart).
4. **Validation/Invalidation zones on scenarios** (from SEM) — each 3d scenario in
   the Market State card gets target + invalidation level, both mechanical.
5. **S/R step-lines + range-position slider** — daily price card shows dotted
   mechanical support/resistance and a 7d-range slider with current-position dot
   (alert block 3 is the exact visual spec for our daily Telegram/brief card).
6. **Correlation mini-panel** — rolling 30/90d correlations BTC vs SPY, Gold,
   DXY, ETH from existing Yahoo parquet (zero quota). Slots into cross-asset card.
7. **Buy-zone ladder** (Vector Lite's "optimal prices to buy") — accumulation
   zones from cost-basis bands (STH realized price, realized price, balanced
   price, true market mean — all on bgeo/CM). MUST pass the house calibration
   rule before being labeled anything stronger than "historical cost-basis levels".

### Defer to v2 backlog
8. **Quadrant scatter** (risk × momentum; Risk Area / Hot Opportunity / Recovery /
   Warming Up) for BTC/ETH/SOL/alt-tiers — macro dashboard already has a quadrant
   popup precedent; do after core ships.
9. **Market Effects panel** (Mean Reversion / Breakout / Up Beta strategy PnLs +
   "Factor Outperformer" chip) — three toy strategies computed on BTC daily data;
   medium effort, fun and informative; needs calibration pass.
10. **Per-asset OI/funding pressure gauges** — BTC-only v1 already planned;
    multi-asset later.
11. Dark-mode toggle (Hawkeye has one; we ship light-first per Vector styling).

### Skip (with reasons)
- **Spot/Perp CVD gauges** — needs tick/taker-flow data; not in our free set at
  daily quality (OKX taker-vol could proxy later; bgeo taker-vol is 1h/paid-ish).
- **Asset Screener / Asset Comparison tools** — Hawkeye's altcoin-universe
  features; we are BTC-focused and the macro dashboard covers cross-asset.
- **Elliott-wave projections + analyst chat (SEM)** — human/discretionary product features, not signals; out of scope.
- **Business-cycle sine-wave page** — the macro dashboard's quad engine already
  owns this domain; a cosmetic duplicate adds nothing mechanical.
