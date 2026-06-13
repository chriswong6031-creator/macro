# Hong Kong / Hang Seng Dashboard — Data Audit (Section 4)

Section 4 is a **full clone of the US Macro Regime Dashboard**, paralleling the
China A-share build (Section 3) but **fully re-thought for Hong Kong**: HK indices,
HK sectors, and — the distinctive piece — HK's actual market-rotation dynamics
(global risk transmission + the HKD peg + Stock-Connect southbound flow). Free,
keyless, CI-reachable sources only. All tickers live-verified 2026-06-13.

## Why HK is modeled differently from the Mainland

Measured on our own 15y data (see memory `china-global-factors`): **Hong Kong is
~2× more globally sensitive than the A-shares** (SPY beta ~0.55 vs ~0.30; stronger
dollar/USDCNY/VIX correlations). HK is the *transmission intermediary* of US
monetary-policy and volatility shocks into China — the HKD peg makes HK rates
shadow the Fed, and HSI earnings are ~75% China-driven. So the HK engine is built
on three legs, not one:

1. **China fundamentals** (PMI/CPI/PPI/M2 — HSI earnings are China-driven) → reuse
   the `china_macro` plane already in the store. *No new macro scraper needed.*
2. **A primary Global Risk Overlay** (DXY/VIX/SPY/copper-gold/USDCNY/EEM) — HK's
   dominant high-frequency driver. This is the HK-distinctive engine module.
3. **HK-internal price structure** (H-share leadership, HS-TECH tilt, cyclical/
   defensive rotation, breadth) built from the deep constituent panel.

## Plane A — prices (group `hk`, yfinance)

| Ticker | What | History | Role |
|---|---|---|---|
| `^HSI` | Hang Seng Index | 1986→ (9,734 d) | **market_index** anchor + RS benchmark |
| `^HSCE` | HSCEI / H-shares | 1993→ (8,116 d) | H-share leadership (risk appetite) |
| `^HSCC` | HS China-Affiliated (red chips) | 2011→ | context |
| `3033.HK` | CSOP HS TECH ETF | 2020→ | **HS-TECH proxy** (`^HSTECH` NOT on Yahoo) |
| `2800.HK` | Tracker Fund (HSI ETF) | 2008→ | search/reference |
| `HKD=X` | USD/HKD | 2001→ | **peg-distance** capital-flow gauge (7.75 strong ↔ 7.85 weak) |
| `EEM` | MSCI EM ETF | 2003→ | global-risk factor (only missing factor; pulled here) |

`^HSTECH` is unavailable on Yahoo (confirmed) — the CSOP/iShares HS-TECH ETFs
(3033.HK 2020→, 3067.HK) stand in for the tech-growth tilt.

## Global-risk factors — already in the store (read, not re-collected)

| Factor | Store location | Maps to file |
|---|---|---|
| US Dollar (DXY) | `yahoo / DX-Y.NYB` | `DX-Y.NYB.parquet` |
| VIX | `yahoo / ^VIX` | `_VIX.parquet` |
| S&P 500 | `yahoo / SPY` | `SPY.parquet` |
| Copper | `yahoo / HG=F` | `HG_F.parquet` |
| Gold | `yahoo / GC=F` | `GC_F.parquet` |
| USD/CNY | `china / CNY=X` | `CNY_X.parquet` |
| USD/HKD (peg) | `hk / HKD=X` | `HKD_X.parquet` (new) |
| EM equity (EEM) | `hk / EEM` | `EEM.parquet` (new) |

## Plane B — macro: REUSE `china_macro`

HSI earnings are China-driven, so the HK growth/inflation axes consume the same
PMI/CPI/PPI/M2 series the China dashboard collects (`group china_macro`). The
HK-specific capital-flow signal is **Stock-Connect SOUTHBOUND** (mainland money
into HK) — already collected in `china_macro / connect_flow` (`southbound_cum`).
Northbound froze Aug-2024 (regulatory) and is irrelevant to HK; southbound is the
live, meaningful HK flow. No new macro collector.

## Sectors = deep synthetic baskets (the key HK adaptation)

HK has **thin sector-ETF coverage** (unlike the Mainland's 16 granular ETFs). But
HK constituent **stock** history is deep (most names 2000–2006→). So HK "sectors"
are **equal-weight synthetic baskets** built with `engine.indicators.basket_index`
over curated constituents — giving *15–25y of history for every sector* (richer
than China's ~5y ETFs). 12 Hang-Seng-industry baskets, RS-ranked vs `^HSI`.

Curated universe — **73/75 names usable** (probed 2026-06-13; dropped 0011.HK,
0489.HK as no-data), ~6/sector:

- **Internet & Tech** 0700 9988 3690 9618 1810 9888 1024 0992 0981
- **Financials & Banks** 1398 0939 3988 0005 2388 3328 1288
- **Insurance** 2318 1299 2628 2601 0966
- **Energy** 0883 0857 0386 1088 0934
- **Materials** 2600 0358 1378 3993 0486
- **Property** 0016 1109 0688 0823 0017 1997 0012
- **Consumer** 2020 2331 1929 6862 0291 0288 2319 1044
- **Healthcare & Pharma** 1093 1177 2269 2359 6160 1099
- **Auto & EV** 1211 2015 9868 0175 2238
- **Telecom & Utilities** 0941 0762 0728 0002 0003 1038 0006
- **Gaming & Leisure** 0027 1928 0880 2282
- **Exchange & Diversified** 0388 0001 0019 0066 0083

This doubles as breadth denominator + per-sector drill-down + stock-search seed.

## Engine design (mirror of china_regime, HK legs)

- **Growth axis:** China PMI (level vs 50) · H-share/HSI ratio · HS-TECH/HSI ratio
  · cyclical/defensive basket · breadth direction · copper/gold (global cyclical).
- **Inflation axis:** China CPI direction · China PPI direction (upweighted, the
  stable Mainland signal) · HK inflation-beta basket (energy+materials vs tech).
- **Dual liquidity overlay:** PBoC stance (China M2 direction) **and** Fed-via-peg
  (HKD peg distance + southbound flow direction). HK has two liquidity taps.
- **Global Risk Overlay (`engine/hk_global.py`)** — PRIMARY. Composite risk-on/off
  z-score from DXY(−)/VIX(−)/SPY(+)/Cu-Au(+)/USDCNY(−)/EEM(+), plus HKD peg state.
  Framed as a **concurrent** risk gauge, not a forecast (lead-lag is ~coincident).
- **Cycle tag:** HSI near-high vs fading breadth (same as China).

TradingView symbols: `0700.HK → HKEX:700` (strip leading zeros), indices via the
ETF proxy or `HSI`.

## Calibration (honest, split-half — Phase-2 gate)

`scripts/calibrate_hk.py`: regime quad → fwd return of `^HSI` (deep history);
dual-liquidity → fwd return; **global-risk state → fwd return** (the key HK test:
does risk-on vs risk-off differentiate HSI forward returns?); cycle ladder on the
deep HK panel (endpoint return + drawdown). Same house rule: no measured edge →
ships as *context, not a signal*.

## Honest limitations

- `^HSTECH` proxied by an ETF (2020→) — shorter than the index.
- HK macro fundamentals are China's (the right call given HSI composition), so the
  growth/inflation read is a *China-earnings* read viewed through an HK risk lens.
- Global factors are **coincident** at weekly frequency — risk STATE, not a lead.
- Sector baskets are equal-weight curated large-caps (CSI/HSI-style), not float-cap
  index reconstructions — labeled as such on the dashboard.
