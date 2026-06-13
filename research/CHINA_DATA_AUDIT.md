# China A-share Dashboard — Data Audit

Live-tested 2026-06-12/13. Two free data planes, both reachable from a global IP
(proxy for GitHub Actions CI). Mirrors the discipline of `VECTOR_DATA_AUDIT.md`.

## Plane A — prices/sectors/stocks via `yfinance` (collectors/china_prices.py, china_breadth.py)

Stored under group `china` (headline) and `china_breadth` (constituents). Verified:

| Class | Symbols | History | Notes |
|---|---|---|---|
| A-share indices | `000001.SS` Shanghai Composite, `399001.SZ` Shenzhen Component | **1997→** | deep calibration anchor |
| Broad ETFs | `510300` CSI300 (benchmark), `510050` SSE50, `510500` CSI500, `159915` ChiNext, `588000` STAR50 | ~2019-21→ | index symbols `000300.SS` etc. shallow/flaky → use ETFs |
| Sector ETFs (16) | banks `512800`, brokers `512880`, baijiu `512690`, staples `159928`, healthcare `512170`, drugs `159992`, semis `512760`, tech `515000`, NEV `515030`, solar `515790`, defense `512660`, nonferrous `512400`, coal `515220`, real-estate `512200`, auto `515250`, media `512980` | ~2019-21→ (~5y) | **more granular than 11 US SPDRs**; ~5y drives calibration design |
| Single stocks | Moutai `600519.SS` 2001→, Ping An, CATL, CMB, Zijin … | deep | TradingView speaks `SSE:`/`SZSE:` |
| FX | `CNY=X` USDCNY | OK | `CNH=X` offshore unreliable on Yahoo |

Backfill result (2026-06-13): china_prices 66,573 rows / 24 tickers; china_breadth
**80/82 curated constituents resolved (98%)**. Dead curated tickers pruned:
`600837.SS` (Haitong, merged into Guotai Junan 2025) → `601995.SS` CICC;
`002013.SZ` (absorbed) → `002179.SZ` Jonhon.

## Plane B — macro via Eastmoney datacenter JSON (collectors/china_macro.py)

The free source `akshare` wraps. `https://datacenter-web.eastmoney.com/api/data/v1/get`
needs a browser User-Agent + `Referer: https://data.eastmoney.com/`. **All `200` from a
global IP.** Stored under group `china_macro`, archive-forever (datacenter serves recent
history only). Verified backfill 2026-06-13:

| Series | reportName | Stored cols | History |
|---|---|---|---|
| PMI | `RPT_ECONOMY_PMI` | pmi_mfg (MAKE_INDEX), pmi_nonmfg (NMAKE_INDEX) | 2008→ (221 mo) |
| CPI | `RPT_ECONOMY_CPI` | cpi_yoy (NATIONAL_SAME), cpi_index | 2008→ |
| PPI | `RPT_ECONOMY_PPI` | ppi_yoy (BASE_SAME), ppi_index | 2006→ (245 mo) |
| Money supply | `RPT_ECONOMY_CURRENCY_SUPPLY` | m2_yoy, m1_yoy, m0_yoy (*_SAME) | 2008→ |
| Industrial prod | `RPT_ECONOMY_INDUS_GROW` | indpro_yoy (BASE_SAME) | 2008→ |
| Interbank rates | `RPT_IMP_INTRESTRATEN` | rate_3m/1y/on (SHIBOR pivot) | shallow (~14d) — direction only |
| Stock Connect | `push2his .../kamt.kline/get` | northbound_cum, southbound_cum | 2014→ (2693) |

**Gotchas:** (1) datacenter rows carry a RangeIndex — must assign by `.to_numpy()` or they
align to NaN against the DatetimeIndex (fixed). (2) Northbound Connect disclosure was
curtailed by regulators **Aug-2024** → `northbound_cum` flattens (expected, labeled). (3)
`southbound_cum` leg parsing imperfect (latest NaN) — best-effort context, non-load-bearing.
(4) SHIBOR report returns only a short recent window → liquidity axis anchors on M2 YoY.

## Deferred (fiddlier hosts; engine degrades gracefully without them)
- Social financing / 社会融资规模 — `data.mofcom.gov.cn` POST, legacy SSL (akshare `macro_china_shrzgm`).
- CGB bond yields (10Y/2Y curve) — chinabond / akshare bond module, not in the datacenter.
- Live ETF holdings / index constituents — Eastmoney returns HTML-in-JS (quarterly) + the
  csindex OSS xls 403s → we use the **curated** sector→constituent map instead (robust, editable).

## Engine implications
- Calibrate the **cycle ladder** on the deep single-stock + index panel (1997-2001→); render
  the ~5y sector ETFs through the same engine but labeled "short history, display-not-calibrated".
- Regime macro inputs (PMI/CPI/PPI/M2/IndPro) are monthly back to 2006-08 → calibratable at a
  **monthly** horizon, shorter + more regime-unstable than the US (2007/2015 bubbles). House
  rule: measured forward-return-by-state, split-half robustness, demote no-edge → context.
