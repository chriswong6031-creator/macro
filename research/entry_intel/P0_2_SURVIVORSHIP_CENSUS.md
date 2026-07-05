# P0.2 Survivorship Census

**Program:** Entry Intelligence (EI) — Phase 0, Task 2
**Produced by:** Sonnet subagent, 2026-07-04
**Consumed by:** P0 Measurement Memo (Opus)
**Status:** COMPLETE — all four questions answered from actual store counts.

---

## §1 PIT Member-Months vs Price Panel Coverage

### Data Sources Inventoried

| Store | Path | Tickers | Date Range |
|-------|------|---------|------------|
| Production: data/stocks | `data/stocks/*.parquet` | 224 | 1980–2026 (deep history, sector holdings) |
| Production: breadth cache | `data/breadth/_closes_cache.parquet` | 509 | 2025-03-18 → 2026-07-02 (~15 months) |
| Production: yahoo | `data/yahoo/*.parquet` | 391 | Varies (ETFs + extras) |
| Research: closes_deep | `data/breadth/_closes_deep.parquet` | 1,498 | 1962-01-02 → 2026-06-15 |
| Research: closes_delisted | `data/breadth/_closes_delisted.parquet` | 199 | 1962–2026 (manually backfilled) |
| Massive (whole-market) | `data/massive_stock_day/*.parquet` | 20,476 | 2021-07-06 → 2026-07-02 (rolling 5y) |

**Production pipeline** (what `build_stock_library.py universe()` actually loads): `data/stocks` + `data/breadth/_closes_cache` + `data/yahoo` = **816 unique tickers**.

**Full research panel** (adding `_closes_deep` + `_closes_delisted`): **1,951 unique tickers**.

### PIT Membership File

- File: `data/breadth/sp500_pit_membership.parquet`
- Shape: 1,255 rows × 3 columns (`ticker`, `start_date`, `end_date`)
- Unique tickers: **1,202** (S&P 500 members since 1996)
- Active (end_date = NaT): **503** tickers
- Removed (end_date set): **730** tickers (includes M&A targets and failures; not all are exchange-delisted)
- Date range: 1996-01-02 to 2026-06-01

Also available: `data/breadth/sp1500_pit_membership.parquet` — 3,286 rows, 2,589 unique tickers (S&P 500 + 400 + 600), with `src` column. SP400: 930, SP500: 1,202, SP600: 1,048 unique tickers.

### Member-Months by Era (Overlap Method)

Member-months computed as days of overlap between each membership span and each era window, divided by 30.44. The "overlap method" correctly allocates membership spans that span era boundaries.

#### Panel A: Production Pipeline (data/stocks + breadth/_closes_cache + data/yahoo)

| Era | Total MM | Covered MM | Missing MM | % Missing |
|-----|----------|------------|------------|-----------|
| pre-2012 | 94,872 | 43,599 | 51,273 | **54.0%** |
| 2012–2020 | 54,243 | 37,242 | 17,002 | **31.3%** |
| 2021+ | 33,247 | 30,030 | 3,217 | **9.7%** |
| **TOTAL** | **182,363** | **110,871** | **71,492** | **39.2%** |

#### Panel B: Full Research Panel (+ closes_deep + closes_delisted)

| Era | Total MM | Covered MM | Missing MM | % Missing |
|-----|----------|------------|------------|-----------|
| pre-2012 | 94,872 | 67,816 | 27,056 | **28.5%** |
| 2012–2020 | 54,243 | 44,935 | 9,309 | **17.2%** |
| 2021+ | 33,247 | 31,798 | 1,449 | **4.4%** |
| **TOTAL** | **182,363** | **144,549** | **37,813** | **20.7%** |

#### Best-Source Coverage (per ticker, using most complete available store)

| Source | Tickers | Total MM |
|--------|---------|----------|
| prod_panel (primary) | 515 | 110,871 |
| closes_deep | 126 | 15,386 |
| closes_delisted | 195 | 18,292 |
| massive | 105 | 13,794 |
| **ABSENT (no price anywhere)** | **261** | **24,019** |

Tickers with zero price coverage in any store: **261** (24,019 MM = **13.2% of total member-months**). All 261 have `end_date` set (confirmed removed, not active), and their last S&P500 removal predates the Massive window (pre-2021-07-06). Examples: AGN (Allergan, removed 2020), RTN (Raytheon merger 2020), UTX (merger 2020), CBS (merger 2019).

---

## §2 Board Universe Size vs Store Coverage

### Universe Definition

The board universe is defined by `build_stock_library.py universe()` as the union of:

1. `data/stocks/*.parquet` — 224 tickers: deep-history holdings from sector ETF constituent snapshots (S&P sector XLK/XLF etc.), preferred source when available.
2. `data/breadth/_closes_cache.parquet` — 509 tickers: current S&P 500 constituents (~15-month window).
3. `data/smallcap_breadth/_closes_cache.parquet` — 605 tickers: S&P 600 small-cap constituents.
4. `data/midcap_breadth/_closes_cache.parquet` — 400 tickers: S&P 400 mid-cap constituents.
5. `data/yahoo/*.parquet` — 188 tickers: ETFs, sector proxies, FX, commodities, crypto extras.

**Total board universe (union): ~1,687 tickers** (after deduplication across sources).

Current S&P 500 constituents (`data/breadth/constituents.parquet`): **503 tickers** — this is the core scoring universe for the standout board.

**Key limitation:** `_closes_cache` has only ~325 bars (~15 months). The production pipeline does not load `_closes_deep` (1,498 tickers, 60+ year history) for the live board. Any replay study using `universe()` as-is gets only a 15-month trailing window from the breadth cache — insufficient for multi-year replay. The replay harness (P0.1) must substitute `_closes_deep` for `_closes_cache` to unlock the 2012–2024 window.

---

## §3 Massive Whole-Market Store: Delisted Ticker Probe

Store: `data/massive_stock_day/` — **20,476 tickers**, rolling 5-year window: **2021-07-06 to 2026-07-02**.

### 2021–2026 Delistings/Acquisitions (17 probed)

| Ticker | Category | Status | Bars | Last Bar | Reason |
|--------|----------|--------|------|----------|--------|
| ATVI | M&A | **PRESENT** | 573 | 2023-10-12 | Acquired by MSFT |
| SGEN | M&A | **PRESENT** | 616 | 2023-12-13 | Acquired by Pfizer |
| SIVB | Bank failure | **PRESENT** | 423 | 2023-03-09 | Failed |
| FRC | Bank failure | **PRESENT** | 458 | 2023-04-28 | Failed |
| VMW | M&A | **PRESENT** | 601 | 2023-11-21 | Acquired by AVGO |
| SPLK | M&A | **PRESENT** | 679 | 2024-03-15 | Acquired by Cisco |
| TWTR | Take-private | **PRESENT** | 333 | 2022-10-27 | Musk |
| CERN | M&A | **PRESENT** | 234 | 2022-06-07 | Acquired by Oracle |
| XLNX | M&A | **PRESENT** | 155 | 2022-02-11 | Acquired by AMD |
| MXIM | M&A | **PRESENT** | 37 | 2021-08-25 | Acquired by ADI |
| NUAN | M&A | **PRESENT** | 168 | 2022-03-03 | Acquired by MSFT |
| ZNGA | M&A | **PRESENT** | 223 | 2022-05-20 | Acquired by TTWO |
| PBCT | M&A | **PRESENT** | 189 | 2022-04-01 | Acquired by MTB |
| Y | M&A | **PRESENT** | 326 | 2022-10-18 | Acquired by BRK |
| JNPR | M&A | **PRESENT** | 1,002 | 2025-07-01 | Acquired by HPE |
| NLSN | Take-private | **PRESENT** | 321 | 2022-10-11 | PE take-private |
| CTLT | M&A | **PRESENT** | 870 | 2024-12-17 | Acquired by Novo |

**Result: 17/17 (100%) of probed 2021–2026 delistings are present in the Massive store.**

### Pre-2021 Control (outside 5y window)

| Ticker | Status | End Date | Reason |
|--------|--------|----------|--------|
| CBS | **ABSENT** | 2019-12-05 | Merged into Viacom |
| MYL | **ABSENT** | 2020-11-17 | Merged into Viatris |
| RTN | **ABSENT** | 2020-04-06 | Merged into RTX |
| UTX | **ABSENT** | 2020-04-03 | Merged into RTX |
| AGN | **ABSENT** | 2020-05-12 | Acquired by AbbVie |

Pre-2021 absences are expected by design — they fall outside the rolling-5y entitlement window.

### Massive Store Coverage Confirmation

All 105 names removed from S&P 500 since 2021-07-06 (the Massive window start) are present in the store. Active controls (PNFP, VRSK, GOOGL): 1,254 bars each (full window). The Massive store achieves **100% recall** of S&P 500 removals/delistings within its 5-year entitlement.

---

## §4 Bias Direction and Magnitude Estimate

### Fraction of Delisted Member-Months Invisible to the Production Replay

| Panel | Delisted MM total | Covered | Missing | % of delisted MM invisible |
|-------|------------------|---------|---------|---------------------------|
| Production pipeline | 77,081 | 5,589 | 71,492 | **92.7%** |
| Full research panel | 77,081 | ~53,000 | ~24,000 | **~31%** |

### Bias Direction

The absent names in S&P 500 PIT are predominantly **M&A targets removed at acquisition premiums** (positive outcomes for shareholders), plus a smaller fraction of distress/failures. This creates a **mixed bias**:

- **Missing M&A wins** (ATVI, CERN, Y, etc.): production replay cannot see signals that fired before an acquisition close. These are exits at a PREMIUM — missing them **deflates measured hit rates** (we miss wins from the denominator of durable-bottom moves).
- **Missing failures** (pre-2021 distress, e.g., J.C. Penney JCP end_date 2013, Avon AVP 2015): missing negative outcomes **inflates apparent win rates** (classic survivorship bias direction).
- **Net direction**: approximately offsetting at the S&P 500 level; S&P 500 removal ≠ bankruptcy. The production panel bias is **mild positive** (more M&A wins missing than catastrophic failures), but the magnitude is difficult to bound without outcome tagging.
- **For pre-2012 era (54% missing from prod panel, 28.5% missing from full panel)**: the true magnitude of win-rate inflation is unknown. Cannot make verdict-grade claims.

### Era-Stamped Reliability Table

| Era | Prod-panel coverage | Full-panel coverage | Massive window | Replay use |
|-----|--------------------|--------------------|----------------|------------|
| pre-2012 | 46% | 72% | Not covered | **Context-only; survivor-bias stamp required** |
| 2012–2020 | 69% | 83% | Not covered | **Context-only; survivor-bias stamp on all verdicts** |
| 2021+ | 90% | 96% | 100% recall | **Verdict-grade claims possible** |

**Mandate from spec (§4/P0.2, inherited §3):** every pre-2021 replay output must carry the stamp: *"survivor-biased panel: [X]% of member-months lack price history; verdicts are context-only."*

---

## Plain English Bottom Line

The S&P 500 PIT membership file tracks 1,202 unique tickers since 1996 — roughly 182,000 member-months in total. The production standout pipeline's live price panel covers only 816 tickers (a ~15-month trailing window from the breadth cache), leaving **39% of all member-months invisible** to a naive replay. The gap is worst in the pre-2012 era (54% missing) and much smaller post-2021 (10% missing), because the Massive whole-market store captures all 20,476+ US tickers on a rolling 5-year window. In fact, every single one of the 17 major 2021–2026 delistings and acquisitions tested — including Silicon Valley Bank, First Republic, Twitter, Activision, and 13 other M&A targets — is present in the Massive store with complete price history through their last trading day. This means the 2021+ era can support unbiased replay verdicts if the replay harness reads Massive directly. The remaining 261 tickers with zero price coverage anywhere are all pre-2021 removals; their 24,000 missing member-months (13% of the total) carry an indeterminate bias because S&P 500 removals are mostly acquisition wins, not failures — missing them modestly deflates measured hit rates rather than inflating them. The practical recommendation is: use `_closes_deep` (1,498 tickers from 1962) as the replay backbone for 2012–2020, integrate Massive for 2021+, and stamp all pre-2012 and 2012–2020 outputs as context-only until the deeper backfill is validated.
