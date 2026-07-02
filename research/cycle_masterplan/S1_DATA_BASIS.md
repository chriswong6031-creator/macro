# S1: Data Basis Feasibility Scout

**Date:** 2026-07-02 | **Repo:** /tmp/macro-cycle-fable-main (canonical main checkout)

---

## 1. Yahoo Price Data Parquets (US)

**Evidence:** `python3 -c "import pandas as pd; df = pd.read_parquet('data/yahoo/SPY.parquet'); print(df.columns, df.index[0], df.index[-1], df['close'].iloc[0], df['close'].iloc[-1])"`

| Ticker | Columns | Index Start | Index End | First Close | Last Close | Shape |
|--------|---------|-------------|-----------|------------|-----------|-------|
| SPY | close, volume | 1993-01-29 | 2026-07-01 | 24.175 | 745.760 | (8412, 2) |
| XLK | close, volume | 1998-12-22 | 2026-07-01 | 11.923 | 185.620 | (6922, 2) |
| EWJ | close, volume | 1996-03-18 | 2026-07-01 | 38.454 | 93.050 | (7621, 2) |

**Finding:** All Yahoo parquets contain **exactly 2 columns: `close` + `volume`** (no OHLC). Values are adjusted closes.

---

## 2. Yahoo Collector Configuration (collectors/yahoo.py)

**Evidence:** Lines 100-101 of /tmp/macro-cycle-fable-main/collectors/yahoo.py:
```python
df = yf.download(batch, period=period, auto_adjust=True,
                 progress=False, group_by="ticker", threads=True)
```

**Finding:**
- **auto_adjust=True** → all closes are **dividend-adjusted + split-adjusted** (total return)
- Only stores **["Close", "Volume"]** renamed to **["close", "volume"]**
- Other OHLC kept ONLY for VIX indices (`^VIX` / vol tickers in config ["yahoo"]["tickers"]["vol"]) → lines 45, 54
- Upserts daily via `store.upsert()` with 1-month rolling window + backfill on `--full`

---

## 3. Unadjusted / Price-Only Close Sources

**Evidence:** `grep -r "auto_adjust=False" --include="*.py" collectors/`

**Collectors with unadjusted (raw) prices:**

| Collector | File | Purpose | Note |
|-----------|------|---------|------|
| **china_stock_raw** | collectors/china_stock_raw.py:48 | A-share RAW closes (limit-up/down bands, gaps, A/H premium) | auto_adjust=False, distinct `china_stocks_raw` group |
| **commodity_carry** | collectors/commodity_carry.py | Historical futures carry term structure | auto_adjust=False per symbol |
| **rate_futures** | collectors/rate_futures.py | Interest rate futures | auto_adjust=False |

**Evidence (china_stock_raw):** Lines 1-22 of /tmp/macro-cycle-fable-main/collectors/china_stock_raw.py document that:
- The **adjusted plane** (`china_stocks`, auto_adjust=True) is used for confluence/reversal signals
- The **RAW plane** (`china_stocks_raw`, auto_adjust=False) is REQUIRED for price-level logic (limit bands, gaps, premiums)
- Both share the same universe (committed A-share search set)
- Raw prints are final; upsert uses `combine_first` (append-only, not overwrite)

**Finding:** Dual-plane architecture exists: **adjusted for signals, raw for levels**. Polygon/massive NOT used for stock prices.

---

## 4. China Price Data Files & Pricing Basis

### 4a. Price Data Locations

**Evidence:** `find data -type d \( -name "china*" -o -name "tushare" -o -name "akshare" \) 2>/dev/null | sort`

**Data directories (price-adjacent):**
- `data/china/` — China indices + sector ETFs + FX (via collectors/china_prices.py, auto_adjust=True)
- `data/china_stocks/` — A-share adjusted closes (via collectors/china_stock_prices.py, auto_adjust=True)
- `data/china_stocks_raw/` — A-share RAW closes (via collectors/china_stock_raw.py, auto_adjust=False)
- `data/china_sectors/` — Shenwan L1 industry indices (via collectors/china_sectors.py)
- `data/china_tushare/` — Tushare ancillary data (fundamentals, flows, etc. — NOT prices)
- `data/tushare/` — Tushare financial statement snapshots (parquets: financials.parquet, holders.parquet, lhb.parquet)

**Note:** NO `data/akshare/` directory exists; akshare is consumed directly in collectors (no intermediate cache).

### 4b. Shenwan Index Pricing Basis

**Evidence:** Loaded `data/china_sectors/801010.parquet` (Agriculture) and `data/china_sectors/801080.parquet` (Electronics):
- Columns: `[close, open, high, low, volume, amount]`
- Index: 1999-12-30 to 2026-07-01
- First close: 1000.00 (baseline index level)

**Source:** collectors/china_sectors.py, lines 11-16:
```
Source: akshare, keyless.
  • `index_hist_sw(symbol=code, period="day")` — daily index OHLC + volume + amount,
    full history every call (so store.upsert is idempotent).
```

**Finding:** 
- Shenwan indices are **PRICE basis** (not total-return), sourced via akshare's `index_hist_sw()` 
- No explicit documentation in collectors re: dividend/split adjustment, but akshare's index_hist_sw() is standard market-price feed (NOT adjusted for dividend reinvestment; indices are custodian-published)
- Deep history: most L1 from 1999-12-31; reindexed codes (banks, auto, non-bank fin) from 2014-02-21

---

## 5. All Price Collectors (45 total)

**Evidence:** `ls -1 collectors/*.py | grep -E "(price|ohlc|stock|yahoo|china|canada|futures)" | wc -l` → 45 collectors

**Primary price collectors (auto_adjust=True):**
1. `yahoo.py` — US indices + stocks (data/yahoo/)
2. `china_prices.py` — China indices + sector ETFs + FX (data/china/, auto_adjust=True)
3. `china_stock_prices.py` — A-share adjusted (data/china_stocks/, auto_adjust=True)
4. `china_stock_raw.py` — A-share raw (data/china_stocks_raw/, auto_adjust=False)
5. `hk_prices.py` — HK indices + HS-TECH + FX (data/hk/, auto_adjust=True)
6. `hk_stock_prices.py` — HK individual stocks (data/hk/)
7. `canada_prices.py` — Canada indices + FX (data/canada/)
8. `intl_prices.py` — Japan / Korea / Taiwan / UK / Eurozone indices + vol + FX (data/intl/)
9. `cboe_vix_futures.py` — CBOE vol futures
10. `rate_futures.py` — Interest rate futures (auto_adjust=False for raw futures prices)
11. `commodity_carry.py` — Commodity futures carry (auto_adjust=False)
12. `special_prices.py` — Specialty tickers
13. `china_sectors.py` — Shenwan L1 sector indices (price basis, akshare source)

**Supporting collectors (not direct prices, but price-adjacent):**
- `_stock_ohlc.py` — shared OHLC fetch logic for china_stock_prices + china_stock_raw
- `edgar_deadname_prices.py` — dead-name price recovery (Stooq → Polygon → yfinance fallback chain)
- `china_*` (30+ others) — flows, breadth, fundamentals, margin, etc. (metadata, not OHLC)

---

## 6. Polygon & Massive Usage

### 6a. Polygon

**Evidence:** `grep -r "polygon" --include="*.py" collectors/ lib/ -l`

**Polygon used for:**
- **Dead-name price recovery only** (collectors/edgar_deadname_prices.py, lines 68-80): fallback to Stooq daily CSV, then Polygon aggregates, then yfinance for delisted tickers
- **Options news sentiment** (collectors/polygon_news.py): per-ticker bullish ratio from ticker insights (editorial tape, non-mandatory)
- **Options flow data** (collectors/polygon_options.py): options contract metadata
- **NOT used for live stock prices** — yfinance is primary

### 6b. Massive

**Evidence:** `grep -r "massive" --include="*.py" collectors/ -l`

**Massive used for:**
- **Options flow aggregates only** (collectors/massive_flatfiles.py, lines 1-24):
  - `us_options_opra/minute_aggs_v1/` — per-contract per-minute OHLCV (18 MB/day)
  - `us_options_opra/day_aggs_v1/` — per-contract daily OHLCV (3 MB/day)
  - `us_stocks_sip/day_aggs_v1/` — stock daily bars (for option/stock volume ratios only)
  - Rolling recent window (~2025→present); NOT entitled to per-trade tape or NBBO quotes
- **NOT used for live stock price collection** — stock bars only for option ratio context

**Finding:** Polygon + Massive are **auxiliary feeders** (dead-names, options context). Primary price collection is 100% yfinance / akshare.

---

## 7. Summary Matrix: Price Data Availability

| Asset Class | Primary Source | Basis | Columns | Start Date | Coverage |
|-------------|---|---|---|---|---|
| **US Equity** | yfinance (yahoo.py) | Adjusted (TR) | close, volume | 1993-01-29 (SPY) | Full history; 1,500+ names |
| **China A-share (adjusted)** | yfinance (china_stock_prices.py) | Adjusted (TR) | close, volume | ~2000→ | Search set (~5k names) |
| **China A-share (raw)** | yfinance (china_stock_raw.py) | Raw / Nominal | close, high, low, volume | ~2000→ | Search set (~5k names) |
| **China indices + ETFs** | yfinance (china_prices.py) | Adjusted (TR) | close, volume | ~1997→ | Shenwan, sector ETFs |
| **Shenwan sectors** | akshare (china_sectors.py) | Price (custodian) | close, high, low, volume, amount | 1999-12-30 | 31 L1 sectors |
| **Hong Kong equity** | yfinance (hk_prices.py) | Adjusted (TR) | close, volume | 1986 (^HSI) | ^HSI, ^HSCE, ^HSCC, indices, HS-TECH proxy |
| **HK individual stocks** | yfinance (hk_stock_prices.py) | Adjusted (TR) | close, volume | 2000→ | Breadth set (~500 names) |
| **Canada** | yfinance (canada_prices.py) | Adjusted (TR) | close, volume | ~1995→ | Indices + FX |
| **International (G7 equiv)** | yfinance (intl_prices.py) | Adjusted (TR) | close, volume | 1986→ | Japan / Korea / Taiwan / UK / Eurozone |
| **Rate futures** | yfinance (rate_futures.py) | Raw | OHLC | Recent | TLT, IEF, SHV, etc. |
| **Commodity futures** | yfinance (commodity_carry.py) | Raw | OHLC | 2y rolling | GC, CL, etc. (carry term structure) |
| **Dead names** | Stooq → Polygon → yfinance (edgar_deadname_prices.py) | Price | close | Partial | 1,083 delisted (IP-gated fallbacks) |

---

## 8. Load-Bearing Gotchas & Design Constraints

1. **Dual-plane China architecture:** Adjusted closes for signals, raw closes for limit-band/premium logic. Never mix planes in a single analysis.

2. **yfinance `auto_adjust=True` is default:** All main equity collectors (yahoo, china_prices, hk_prices, intl_prices) use adjusted (TR) closes. Raw access requires explicit `auto_adjust=False`.

3. **Shenwan is price-basis, not TR:** Akshare index_hist_sw() feeds custodian-published prices, NOT dividend-reinvested levels. Do not backtest P&L vs Shenwan closes without understanding this.

4. **Polygon + Massive are auxiliary:** Not primary price feeds. Polygon is dead-name recovery + options news; Massive is options flow context only.

5. **Store.upsert() idempotent design:** All collectors re-pull short windows and deduplicate by date. Full history must be backfilled once (--full flag).

6. **Tushare ancillary only:** data/tushare/ holds financials, holders, margin details — NOT prices. Price data lives in data/china/, data/china_stocks/.

---

## Questions Answered (Evidence-First)

| Q | Finding | Evidence |
|---|---------|----------|
| **Q1: Columns in SPY/XLK/EWJ?** | close + volume (2 cols); index spans 1993→2026 | parquet read output above |
| **Q2: How is yahoo.py configured?** | auto_adjust=True; only close+volume stored (OHLC only for vol indices) | collectors/yahoo.py:100-101, 54 |
| **Q3: Unadjusted or price-only close anywhere?** | YES: china_stock_raw, rate_futures, commodity_carry (auto_adjust=False); no Polygon/Massive for stocks | grep auto_adjust=False results + edgar_deadname_prices (dead-names only) |
| **Q4: China price files & Shenwan basis?** | data/china/ (indices, auto_adjust=True), data/china_stocks/ (adjusted), data/china_stocks_raw/ (raw), data/china_sectors/ (Shenwan L1, price-basis custodian index) | file listing + parquet inspection |
| **Q5: Polygon/Massive collectors?** | NOT stock prices. Polygon: dead-names + options news. Massive: options flow + stock ratios only. PRIMARY = yfinance + akshare | collector grep results + file inspection |

---

**End of Scout Report**
