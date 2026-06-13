# Commodity Vector — Data Audit (Section 5)

**Verified 2026-06-13.** Commission: a 5th dashboard section for the core four
commodities — **gold, silver, oil (WTI), copper** — built like Bitcoin Vector: a
clear-cut regime/allocation read per commodity, plus how each cycles with the US
dollar, rates/treasuries, equities, and supply/geopolitical shocks. House rule
applies (mechanical, backtestable core; LLM/news = context, never a scoring input).

Scope decisions (user, 2026-06-13):
- **One** Commodity Vector page with a 4-asset selector + a commodity-complex
  "macro regime" overview at top (NOT four separate pages).
- Shock/event intelligence: build the **quantitative** shock engine now
  (residual/decoupling + oil curve + COT extremes + price/vol sentinel); **defer**
  the news/LLM annotation layer to a final gated phase (annotation-only).

This runs alongside the in-progress Greater China sections (parallel agent owns
`collectors/china_*.py`, the `china:` config block, and the landing-hub card list —
**coordinate, never `git add -A`, additive edits only**).

---

## 1. Headline: the foundation already exists

The macro dashboard already collects ~90% of what a commodity dashboard needs, with
**~25 years of history** (multi-cycle) — far deeper than Bitcoin Vector's ~1-cycle
derivatives, so commodity calibration will be much more robust.

### 1a. Prices — already collected (Yahoo, `data/yahoo/`, EOD close+volume)
| Symbol | Series | Span | Rows |
|---|---|---|---|
| `GC=F` | Gold front future | 2000-08-30 → current | 6470 |
| `SI=F` | Silver front future | 2000-08-30 → current | 6472 |
| `CL=F` | WTI crude front future | 2000-08-23 → current | 6479 |
| `BZ=F` | Brent crude front future | 2007-07-30 → current | 4697 |
| `HG=F` | Copper front future | 2000-08-30 → current | 6475 |
| `DX-Y.NYB` | US Dollar Index (DXY) | **1971-01-04** → current | 14079 |

Stored as `data/yahoo/{GC_F,SI_F,CL_F,BZ_F,HG_F,DX-Y.NYB}.parquet` (Yahoo `=`→`_`).
Front-month only (no continuous-adjusted / curve) — fine for trend/cycle; curve
shape for oil is a separate optional add (§4).

### 1b. COT positioning — gold/copper/dollar already collected; **silver + oil added this audit**
| Series | Span | Rows | Notes |
|---|---|---|---|
| `cot_gold` | 1995 → current | 1641 | `GOLD - COMMODITY EXCHANGE` |
| `cot_copper` | 1995 → current | 1641 | `COPPER- #1 …` |
| `cot_dollar` | 1995 → current | 1576 | `USD INDEX …` |
| `cot_silver` | **1995 → current** | 1641 | `SILVER - COMMODITY EXCHANGE` (COMEX 5000oz) — **added** |
| `cot_oil` | **1995 → current** | 1640 | WTI, **spliced** (see gotcha below) — **added** |

Each row: `net_spec` (non-commercial long−short), `open_interest`, `net_spec_pct_oi`.
Weekly (Tue data, Fri release, ~3-day lag). Legacy futures-only report.

### 1c. Macro drivers — already collected (FRED, `data/fred/`)
| Series | Driver | Span |
|---|---|---|
| `DFII10` | 10y TIPS real yield | 2003 → current |
| `T10YIE`, `T5YIFR` | 10y breakeven, 5y5y fwd inflation | 2003 → current |
| `DGS10`, `DGS2`, `T10Y2Y` | nominal 10y/2y, 2s10s | 1962/1976 → current |
| `WALCL`, `RRPONTSYD`, `DFF` | Fed balance sheet, RRP, fed funds | 2002/2003/1954 → |
| `INDPRO`, `PAYEMS` | industrial production, payrolls (growth) | → current |

`copper_gold` ratio is already constructed and used in the macro engine's growth axis.

---

## 2. Gotchas (locked down this audit)

1. **WTI COT contract renamed AND moved exchanges.** The NYMEX physical light-sweet
   contract (`CRUDE OIL, LIGHT 'SWEET' - NEW YORK …`, note the **literal apostrophe**
   in the pre-~2010 name) ran 1986→2022-02 then **dropped out of the legacy report**.
   The current liquid WTI positioning series is `CRUDE OIL, LIGHT SWEET-WTI - ICE
   FUTURES EUROPE` (2014→current, OI ~875k). Config lists all three prefixes; the
   collector's per-date **max-OI dedup** stitches NYMEX (1986-2022) → ICE (2022→) into
   one continuous series automatically.
2. **Apostrophe broke SoQL.** The WTI name's literal `'` terminated the `starts_with`
   string → HTTP 400. Fixed in `collectors/cot.py`: single quotes are now doubled
   (`p.replace("'", "''")`) — the SoQL escape. General-purpose, helps any apostrophe
   contract.
3. **Oil splice has a level shift.** At the 2022-02 handoff `net_spec_pct_oi` jumps
   ~18% (NYMEX, OI ~2.1M) → ~0.5% (ICE, OI ~510k): the two contracts have structurally
   different spec positioning even normalized by OI. **Design constraint:** the oil
   positioning signal must use **rolling-window** percentile/z-score (like the BTC
   engine's `_pctile` lookback), NOT full-history. A rolling ≤3y window is internally
   clean within each era; 2022-2025 backtests carry a transition smear (flag honestly).
   Live 2026 reads are clean (fully post-handoff). Silver/gold/copper/dollar have no
   such handoff.

---

## 3. The "intelligent" shock layer — proven quantitatively (no news needed)

Instead of scraping news to guess a cause, detect the **footprint** a shock leaves: a
commodity moving in a way its normal macro drivers cannot explain. Tested on gold for
the China-CB/Tether-buying era — the signal is unmistakable:

- **Driver decoupling.** Gold's normally-strong negative correlation to 10y real yields
  collapsed: −0.70 (2020-23) → **−0.28 / −0.15 / −0.14** (2024/25/26). Directly
  measurable as a rolling correlation breaking down.
- **Residual bid.** Gold monthly return regressed on real-yield change + dollar (fit
  **pre-2021**), then measured forward: persistent unexplained positive residual
  **+0.45σ (2024), +0.66σ (2025)**, with discrete shock months at **+3.3, +4.3, +4.9σ**.
  That residual *is* central-bank/Tether buying — captured with zero headlines.

Each commissioned "anomaly" maps to a quant proxy:

| Shock example | Quant footprint (feed-free) |
|---|---|
| Gold/silver — China CB + Tether buying | residual vs real-yield+dollar model; real-yield decoupling (both **proven**) |
| Oil — Iran war / Strait of Hormuz | futures-curve **backwardation** spike + realized-vol shock (flash sentinel) + oil residual vs dollar |
| Copper — data-center buildout | copper strength residual vs dollar+growth; copper/gold breakout; COT spec build |
| OPEC / US supply | oil curve shape + COT positioning + inventory draw/build |

**Two-track design:** (A) quant shock engine in the core (residual/decoupling + oil
curve + COT extremes + flash-vol state machine reused from `engine/btc_alerts.py` +
`scripts/vector_sentinel.py`) — backtestable, no feeds. (B) news/LLM layer deferred,
gated, **annotation-only** (labels a detected residual's likely cause; never scores) —
fragile feeds, hard to backtest, LLM-in-CI cost. An events-**calendar** (OPEC/FOMC
dates) is a cheaper, more reliable forward-watch than open news scraping.

---

## 4. Driver → signal map (Phase 2 engine design)

Asset-agnostic price layer ports ~verbatim from `engine/btc_signals.py`
(momentum vote-ensemble, structure, risk index = vol+drawdown, gauges, allocation
grid, tactical/strategic, cycle_stage). Commodity-specific layer replaces BTC's
on-chain block:

- **Gold / Silver** — macro-driver axis: real yields (DFII10, inverse), dollar (DXY,
  inverse), breakevens/inflation, Fed liquidity (WALCL). Silver adds an industrial/
  growth leg + the gold/silver ratio (risk-appetite/cycle gauge).
- **Copper** — "Dr. Copper": dollar (inverse), global-growth proxy (copper/gold,
  INDPRO/PMI, optionally the China dashboard's data), real yields. Data-center demand
  shows as copper strength residual vs the growth model.
- **Oil** — dollar, **futures-curve shape** (backwardation = supply tightness — the
  OPEC/war tell), inventories (EIA, optional). Real yields less relevant.
- **Positioning** — COT spec `net_spec_pct_oi` rolling-window extremes = squeeze/washout
  detector (silver 2021, etc.). 30y depth for gold/silver/copper/dollar.
- **Cross-commodity** — gold/silver, copper/gold, oil/gold ratios → a commodity-complex
  **macro-regime quadrant** (Reflation / Deflation-scare / Stagflation / Goldilocks)
  shown at top = the "where are we, allocate?" headline.

### Optional future collectors (not needed for v1)
- **EIA** crude/product inventories + an oil **futures-curve** (front vs deferred →
  backwardation/contango) — strongest oil supply-shock proxy.
- Broad dollar `DTWEXBGS`, `TIP`/`GLD`/`SLV` ETFs (flow proxy), natural gas / platinum /
  ags as a later expansion.

---

## 5. Phase status
- **Phase 0 (this audit): DONE.** Data verified; silver + oil COT added & stored
  (1995→current); `cot.py` apostrophe-escape fix landed; gotchas documented.
- Next: Phase 1 `engine/commodity_inputs.py` (load price + drivers per asset) →
  Phase 2 `engine/commodity_signals.py` → Phase 3 `scripts/calibrate_commodities.py`
  → Phase 4 `scripts/build_commodities.py` + `templates/commodities.html.j2` + hub card
  + CI → Phase 5 sentinel → Phase 6 (deferred) news annotation.
