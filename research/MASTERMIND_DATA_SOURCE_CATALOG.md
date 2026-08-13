# Mastermind Data Source Catalog — 2026-08-12

Status: reference document. Companion to the Data OS design decisions (D0–D12); this file is the
INVENTORY those decisions operate on, not a second set of decisions.
Authority: `context_only`. Nothing here ranks, gates, sizes, or scores anything.
Scope: the three-repo product — `Macro Dashboard` (engines + nightly render), `charting-app`
(Terminal), `Mastermind` (trading bot).

## 0 · How to read this catalog

**Every row is a claim about data, so every row carries a way to check it.** Three markers:

| Marker | Means |
|---|---|
| `[V]` | Verified in THIS pass. The command or the `path:LINE` is given inline. |
| `[C]` | Verified by a census lane, cited by `path:LINE`, **not re-run here**. Trustworthy but second-hand. |
| `[I]` | Inferred. Reasoning is given; no one ran it. Treat as a hypothesis. |

Standing adjudications are cited by stable key, never by row number: `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT`
(`research/DO_NOT_REBUILD.md:130`), `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` (`research/DO_NOT_REBUILD.md:169`). `[V]`

A dataset that has no rows is listed in **§4 DECLARED-BUT-UNMATERIALIZED**, never in the vendor sections.
The rule this enforces is the house's own: a catalog listing a dataset that does not exist as described is
worse than no catalog, because the next session builds against it.

### 0.1 Two checkouts, and why it matters for every number below

Measurements in this document come from two different trees, and the difference is load-bearing:

| Tree | Path | What it has | Trust |
|---|---|---|---|
| CODE worktree | `…/Macro Dashboard/.claude/worktrees/mastermind-data-os-arch-070441` | current `origin/main` code; `data/` NOT materialized | code citations authoritative |
| DATA checkout | `/Users/chriswong/Documents/Cluade/Macro Dashboard` | `data/` materialized, 329 top-level dirs (`ls -d data/*/ \| wc -l` → 329) `[V]` | file CONTENTS trustworthy; git log and mtimes NOT |

**Caveat that binds every staleness statement in this file:** the DATA checkout is itself in a broken git
state — detached HEAD, an unresolved merge conflict in `config/dag.yml`, ~4,560 dirty entries, HEAD ~1,119
commits behind `origin/main` `[C]`. Therefore: a parquet's *contents* read out of that tree are real (the
bytes are on disk), but **no claim in this catalog rests on that tree's `git log` or file mtimes**, and where
a lane's finding did rest on them it is labelled as needing corroboration. "Store X tips at date D" below
means "the last index value in the parquet on disk in that checkout is D" — it does not establish whether
the live Mac Studio pipeline is further ahead.

---

## 1 · THE FOUR US DAILY PRICE STORES

This is the table this document exists for. Four physically separate per-ticker daily stores cover US
equities. They are not tiers of one pipeline; they are four independently coded, independently scheduled
fetches, and they disagree.

| | `data/stocks` | `data/yahoo` | `data/baskets/ohlcv` | `data/massive_stock_day` |
|---|---|---|---|---|
| **Coverage** (parquet files) | **229** | **824** | **2,519** | **20,476** |
| **Vendor** | yfinance | yfinance | yfinance | massive.com (Polygon-compatible) flatfiles |
| **Producer** | `collectors/sector_holdings.py:259 class StockPriceAdapter`, `:262 name="stock_prices"`, `:263 group="stocks"` `[V]` | `collectors/yahoo.py` `[V]` | `scripts/fetch_basket_ohlcv.py`, invoked from `scripts/collect.py:789-795` `[V]` | `collectors/massive_stock_day.py` `[V]` |
| **Columns** | `close, high, low, volume` — **no `open`**, 229/229 files, one schema `[C]`; re-read here on HON `[V]` | `close_price, close, volume` `[V]` | `open, high, low, close, volume` `[V]` | `open, high, low, close, volume, transactions` `[V]` |
| **Basis** | total-return (`close_tradj`) — `collectors/sector_holdings.py:264` records `auto_adjust=True`; the 192.57 reading in §1.1 confirms it `[V]` | `close` = total-return; `close_price` = split-adjusted, dividend-UNadjusted (`collectors/yahoo.py:6-12`) `[V]` | total-return (`auto_adjust`, `scripts/fetch_basket_ohlcv.py:19`) `[V]` | raw printed price (`close_raw`) — 207.70 vs the ~192s in §1.1 `[V]` |
| **Adjustment vintage** | `collectors/sector_holdings.py:264 overwrite_overlap = True  # …seam-free re-adjust of the refresh window` `[V]` — the refresh window is overwritten with newly re-adjusted values | re-adjusted by Yahoo at every fetch; `store.basis_shifted` re-pulls `period='max'` on detection (`collectors/yahoo.py:15-19`) `[V]` | independent fetch ⇒ independent vintage `[I]` | none (never adjusted) |
| **History depth** | deepest: WMT 1972-08-25 (13,577 rows), AAPL 1980-12-12 (11,483) `[V]` | **inconsistent within the store**: NVDA 6,906 rows from 1999-01-22; AAPL/WMT/CMG 756 rows from 2023-07-03 `[V]` | uniform 2014-01-02, 3,146 rows `[V]` | uniform 2021-07-06, 1,254 rows `[V]` |
| **Tip on disk (DATA checkout)** | 2026-07-08 (AAPL/WMT/NVDA); **HON 2026-06-29** `[V]` | 2026-07-08 `[V]` | 2026-07-08 (AAPL/WMT/NVDA); **CMG 2026-06-29** `[V]` | 2026-07-02 `[V]` |
| **Coverage holes** | CMG has NO file at all `[V]` | — | per-ticker tip skew (CMG 9 sessions behind AAPL) `[V]` | manifest declares `n_tickers: 19133` vs 20,476 files on disk; `n_processed_days: 471`; `max_missing_run_weekdays: 832` since `first_day 2021-07-06` `[V]` |
| **Canonical home** | local `data/` | local `data/` | local `data/` | **R2**, key prefix `massive_stock_day/`; git holds only 2 JSON sidecars (`collectors/massive_stock_day.py:17-22`) `[V]` |
| **Lawful use** (normative — from the D4 basis law, not a measurement) | return math | `close`→return math; `close_price`→structure math | return math | limit/tick/exchange-rule work, execution sim |

Counts measured 2026-08-12: `for d in stocks yahoo baskets/ohlcv massive_stock_day; do ls data/$d | grep -c '\.parquet$'; done` → `229 / 824 / 2519 / 20476` `[V]`.
Manifest read: `python3 -c "import json;print(json.load(open('data/massive_stock_day/_manifest.json')))"` → `n_tickers 19133, latest_date 2026-07-02, updated_at 2026-07-04T00:41:55…, coverage{first_day 2021-07-06, n_processed_days 471, max_missing_run_weekdays 832}` `[V]`.

### 1.1 The HON witness — one ticker, one date, five numbers

Re-measured independently in this pass (not carried from the census). HON, 2025-09-25:

| Store / column | Value on 2025-09-25 | Same store on 2026-06-29 |
|---|---|---|
| `data/stocks/HON.parquet` `close` | **192.573517** | 227.800003 |
| `data/yahoo/HON.parquet` `close` | **192.419067** | 227.800003 |
| `data/yahoo/HON.parquet` `close_price` | **195.758713** | 227.800003 |
| `data/baskets/ohlcv/HON.parquet` `close` | **201.964905** | 227.800003 |
| `data/massive_stock_day/HON.parquet` `close` | **207.700000** | 227.800000 |

Command: `pandas.read_parquet` on each path, `.loc['2025-09-25']` / `.loc['2026-06-29']`, run 2026-08-12 `[V]`.

Read the table twice. Horizontally it is the price-basis problem: 207.70 is the raw print, 195.76 is
split-adjusted, and the ~192s are total-return. **Vertically it is the harder problem** — 192.573517 vs
192.419067 vs 201.964905 are all nominally the SAME basis (total return, splits + distributions
reinvested) and they disagree by up to 4.96%. Nothing distinguishes them semantically. They differ because
each store was back-adjusted through a different set of subsequent corporate actions, i.e. they carry
different **adjustment vintages**, and all five converge to 227.80 at the tape tip because there is nothing
left to back-adjust through.

**Therefore: `adjusted` is a `(basis, as-of-vintage)` pair, never a boolean.** Any schema, flag, or API that
answers `adjusted: true/false` is under-specified by exactly one dimension, and the missing dimension is the
one that moved 4.96% here.

The mechanism (HON's Solstice Advanced Materials spinoff) is `[I]` and **cannot be verified in-repo** —
precisely because no corporate-action event store exists to check the ex-date and factor against (§5.2).

### 1.2 The existing resolver, and its false premise

`engine/price_ladder.py` is the de-facto price-resolution contract and the best prior art in the repo. It
declares `ADJUSTED_SOURCES = ("baskets_ohlcv", "yahoo", "data_stocks", "baskets_extras")` at
`engine/price_ladder.py:104`, with `UNADJUSTED_SOURCES = ("closes_cache_UNADJUSTED",)` at `:105` and the
resolution ladder `LADDER = ADJUSTED_SOURCES + UNADJUSTED_SOURCES` at `:106` `[V]`. It resolves a name
through the first rung that hits (`_FILE_RUNGS`, `engine/price_ladder.py:113`, consumed at `:303`) `[V]`
and returns `adjusted=True` for every adjusted rung (`:131`) `[V]`.

Its own premise (docstring ~lines 5-8) is that an excess return is only meaningful when both legs are on the
SAME adjustment basis `[C]`. §1.1 shows the three adjusted rungs are **not** the same basis. Measured by the
census lane: on 2024-06-03, 31/223 tickers present in both `data/stocks` and `data/baskets/ohlcv` disagree
by >0.01%, 18 by >0.5%, max 4.877% (HON); over full history 25/86 sampled tickers have
`data/stocks != data/yahoo` `[C]`. There is **no consistent precedence**: for HON, yahoo == baskets and
stocks is the outlier; for PEP, stocks == yahoo and baskets is the outlier `[C]`.

Consequence for any study: a universe that resolves some names via rung 1 and others via rung 3 mixes two
vintages into one cross-section, and `r.adjusted == True` for both, so the divergence is invisible to every
consumer. The module already measured ONE pair and found it clean (extras vs baskets/ohlcv bit-identical on
400 shared names) `[C]` — it never measured baskets vs stocks vs yahoo.

`engine/price_ladder.py` also discloses a standing coverage hole the Data OS should not re-litigate: the
`baskets_extras` rung recovers ZERO of the 154 board-admitted names that fall through to the raw cache, so
20.6% of freshly-graded `us_board` rows resolve UNADJUSTED — and the module deliberately falls through
rather than dropping names, stamping `r.adjusted=False` `[C]`. That is the correct pattern to generalize:
**disclose the basis you actually served; never delete the population a study exists to measure.**

### 1.3 The `open` question, restated correctly

`data/stocks` has no `open` column — universally, 229/229 files, one schema `[C]`. But opens ARE obtainable:

- `data/baskets/ohlcv` carries a real `open` for 2,519 names `[V]` (columns verified above), a fact already
  known in-repo at `engine/marketing/chart_render.py:254` and `engine/marketing/hot_tape_pack.py:13` `[C]`;
- `engine/ohlc_reconstruct.py` synthesizes `open := prior close` and high/low from close ± ATR-proxy/2,
  documented as deliberately biased wide and explicitly NOT trustworthy for tail-risk stop sizing
  (`engine/ohlc_reconstruct.py:1-24`) `[V]`.

**So the defect is undisclosed MIXTURE, not absence.** A gap feature built from a baskets `open` against a
stocks `close` crosses two adjustment vintages (§1.1), and nothing stamps which open a caller received.
Two builders give up instead: `scripts/build_stock_personality.py:152` and
`scripts/personality_compat_phase0.py:873` emit the literal disclosure
`gap-features-unavailable: data/stocks has no open column` `[C]`.

Reader count for the store: `grep -rl 'data/stocks' engine scripts collectors lib app | wc -l` → **135**
files in the CODE worktree, 2026-08-12 `[V]`. (The adversarial verifier measured 133 on an earlier tree
state; the number moves with the tree — cite the command, not the constant.)

### 1.4 Store-choice is a published-number input, and one module proves it

`engine/washout_turn.py:55-72` documents that `_load_close` prefers `data/baskets/ohlcv`, which for
long-listed names is the SHORTEST store, then extends backward with the longest available store via a
ratio-aligned prepend splice — and explicitly refuses to resolve the disagreement for SIGNAL legs, because
"recent-close disagreements between stores are real (split/dividend adjustment epochs differ)". Measured in
the same docstring: the 2026-07-31 MCD cross reads depth 8.6 / n=8 off the preferred store and 6.3 / n=36
off the full store — same state, same date, different published percentile `[C]`.

That is the whole thesis in one module: **store choice changed a published statistic, and it lives in an
implementation detail of a private loader.**

---

## 2 · SOURCES AND VENDORS

Format per source: identity and entitlement first, then the physical facts, then what breaks.

### 2.1 US equity prices

#### massive.com (Polygon.io-compatible flatfile vendor)

- **Datasets:** `us_stocks_sip/day_aggs_v1` (whole-market equity daily bars); `us_options_opra/day_aggs_v1`
  and `minute_aggs_v1` (per-contract options aggregates).
- **Asset classes / markets:** US equities, US listed options (OPRA). `[V]`
- **Entitlement — the binding constraint:** the account is entitled to **AGGREGATE products only**. It is
  NOT entitled to the per-trade tape (`trades_v1`) or NBBO quotes (`quotes_v1`) — **both return 403 via
  flatfile AND REST** (`collectors/massive_flatfiles.py:1-15`) `[V]`. This is why the options flow engine
  signs volume with a minute tick-rule rather than a quote rule (`collectors/massive_flatfiles.py:11-15`) `[V]`.
- **Coverage / history:** equity day aggs are a rolling ~5-year window; probe-verified earliest available
  day 2021-07-06 = first trading day on/after today−5y, **days before the floor return 403**
  (`collectors/massive_stock_day.py:3-6`) `[V]`. Options aggregates: rolling recent window ~2025→present
  (`collectors/massive_flatfiles.py:10`) `[V]`.
- **Cadence / latency:** EOD flatfiles, nightly incremental. No realtime tier.
- **Timezone / identifiers:** equity index = date at UTC midnight (`collectors/massive_stock_day.py:12`) `[V]`;
  options `ticker` = raw OPRA/OCC `O:<ROOT><YYMMDD><C|P><strike×1000, 8 digits>`, variable-length root,
  no padding (`collectors/massive_flatfiles.py:22-23`) `[V]`; aggregate bars stamped `window_start` (ns) `[C]`.
- **Adjustment:** none — raw printed prices. This is the only unadjusted US plane in the estate.
- **Revision:** append-only upsert; no vendor revision mechanism.
- **Ingestion:** `collectors/massive_flatfiles.py` (reader/cache), `collectors/massive_stock_day.py`
  (derived per-ticker store).
- **Canonical storage:** **R2**, prefix `massive_stock_day/` (~617 MB, ~20k parquets). The nightly job runs
  `scripts/fetch_r2 --dirs massive_stock_day` → `run_incremental()` → `scripts/publish_r2`, with publish
  gated on the restore outcome so a partial tree cannot overwrite the deep copy
  (`collectors/massive_stock_day.py:17-27`) `[V]`. Local `data/massive_stock_day/` is a materialization.
  Options aggregates cache to `data/massive_flat/` (gitignored, transient) `[V]`.
- **Consumers:** `engine/us_scan_universe.py` (widened "seen but not admitted" scan universe) `[C]`;
  `scripts/backfill_options_flow.py` and `scripts/options_tape_signed_pilot.py` for the options leg `[C]`.
- **Fallback:** none. No S3 creds / 403 / missing file → empty frame, never raises
  (`collectors/massive_flatfiles.py:19-21`) `[V]`.
- **Known quality issues:** the store is ~37% populated against its own declared window (471 processed days
  against ~1,255 sessions) with an 832-weekday maximum missing run, and the manifest/disk count disagree by
  1,345 files `[V]`. **Treating this as "the raw reference" without a freshness+gap contract would move every
  structure calculation onto the stalest and gappiest store in the estate.**

#### Yahoo / yfinance

- **Datasets:** `data/yahoo` (dual-basis daily), `data/stocks` (sector-SPDR top-N union daily),
  `data/baskets/ohlcv` (basket-membership daily, volume-bearing), `data/china_stocks_raw`, `data/hk_stocks`,
  `data/stock_fundamentals` (ratio snapshots), plus Canada/Intl price stores.
- **Asset classes / markets:** equities in US / CN (`.SS`/`.SZ`) / HK (`.HK`) / Canada (`.TO`) / Intl; some
  FX and index symbols.
- **Adjustment methodology — read this twice:** `collectors/yahoo.py:6-12` `[V]`:
  `close` = total-return (split+dividend adjusted) = `Adj Close` at `auto_adjust=False`;
  `close_price` = split-adjusted, dividend-UNadjusted = `Close`, described in-repo as
  *"the correct basis for all structure math (ZigZag, detrended osc, DCL/failed-cycle, drawdown-from-ATH)"*.
  **The names invert intuition**, and the basis the house itself calls correct for structure math is absent
  from `data/stocks`, the store 135 files read (§1.3).
- **Revision behaviour:** both stored bases are **re-adjusted by Yahoo at every fetch**, so a 1-month window
  pulled after an ex-div/split disagrees with stored history on every overlap date; `store.basis_shifted`
  detects this and re-pulls `period='max'` instead of splicing (`collectors/yahoo.py:15-19`) `[V]`. This is
  the mechanism that manufactures the vintage divergence in §1.1: three stores, three re-pull histories.
- **Cadence / latency:** nightly; short overlap window on daily runs, `period='max'` on backfill
  (`collectors/yahoo.py:3-4`) `[V]`. EOD only.
- **Identifiers:** bare ticker (Yahoo notation, `.` → `-`), with a 2-row fetch alias map (§5.1).
- **Licensing / entitlement:** unofficial API, "replaceable by design" (`collectors/yahoo.py:1`) `[V]`.
  **No rights field exists on any of these stores** — no `redistribution_class`, no `license_class`. The
  yfinance personal-use terms question against a paid product is written down in exactly one place, and that
  place is the untracked prototype registry (§5.4). This is an exposure, not a resolved question.
- **Known quality issues:** coverage-loss reporting is a 70% threshold —
  `collectors/yahoo.py:167 _report_missing_symbols(...)` raises only when coverage drops below 70%, and its
  own docstring at `:39-42` records why ("a warning that is always on is a warning nobody reads, which is
  how CTRA/TPH sat frozen for three months") `[C]`. **A 30% silent loss passes.**
- **Known discrepancies:** §1.1; plus `data/yahoo` stores `volume` as int64 while `data/stocks` stores it as
  float64, so a missing bar **cannot even be represented as null** in the yahoo store `[C]`.

#### Polygon.io (direct REST — distinct from the massive.com flatfile path)

- **Datasets:** options snapshot chains (per-strike OI + IV + vendor greeks), grouped daily equity aggs
  (Terminal only), ticker news with per-article sentiment insights, intraday minute aggs (Terminal only).
- **Entitlement:** verified entitled on the stocks+options plan; **index/futures/FX/crypto are NOT** — index
  spot `I:SPX` returns 403, so SPX is excluded from the Polygon GEX universe
  (`collectors/polygon_options.py:4-7`) `[V]`.
- **Realtime/delayed:** the spot used for chain snapshots is the **15-minute delayed** stock snapshot,
  "fine for an EOD build" `[C]`. Nothing in the Macro repo consumes a Polygon realtime tier.
- **Adjustment:** Terminal's `refresh_ohlc.py` calls
  `https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=true`
  (`charting-app/ingest/refresh_ohlc.py:39-41`) `[V]`. Polygon documents `adjusted` as **split-only**; that
  is a vendor-doc fact, **not asserted anywhere in either repo's code** — `[I]`, and it is the load-bearing
  inference under §2.8.1. It should be pinned by a receipt before anything depends on it.
- **Ingestion:** `collectors/polygon_options.py` (NOT in the `scripts/collect.py` adapter registry — driven
  by `scripts/build_polygon_gex.py:accrue()`) `[C]`; `collectors/polygon_news.py`.
- **Canonical storage:** `data/polygon_gex/chains/<date>.parquet` + `data/polygon_gex/summary_<TICKER>.parquet`
  (404 entries on disk) `[V]`.
- **Known quality issues:** **three independent hand-rolled Polygon/massive HTTP clients** each
  re-implementing the same `POLYGON_API_KEY`/`MASSIVE_API_KEY` fallback —
  `collectors/polygon_news.py:135-138`, `collectors/polygon_options.py:93-107`,
  `scripts/build_polygon_universe.py:153-171` (raw urllib, **no retry/backoff**) `[C]`. A key rotation or
  base-URL migration must land in three places.
- **Known discrepancies:** vendor greeks are persisted raw (`collectors/polygon_options.py:83-88`) while
  `engine/gex_engine.py:62-70` independently recomputes gamma via Black-Scholes from `iv/oi/K/T/is_call`,
  ignoring the persisted columns. **Two different `gamma` values exist per contract with no reconciliation
  test found** `[C]`.

#### ThetaData (out-of-band EOD options backfill)

- **Datasets:** historical options chains, EOD snapshots + greeks.
- **Ingestion:** a long-running process driven by ThetaTerminal v3 REST plus a launchd keepalive
  (`com.macro.thetadata-backfill.plist`), **run in a separate ops worktree** `/Users/chriswong/theta-ops-wt`
  (`research/THETADATA_OPS_RUNBOOK.md:9-17`) `[V]`.
- **Cadence:** idempotent, resumable; `_backfill_state.json` records completed `root+date` pairs `[V]`.
- **Canonical storage:** `data/thetadata_eod/`.
- **Consumers:** 50 files in the CODE worktree reference `thetadata_eod`/`thetadata_store`
  (`grep -rl 'thetadata_eod\|thetadata_store' engine scripts collectors lib | wc -l` → 50), including
  `engine/options_hub.py`, `engine/options_matrix.py`, `engine/options_surface.py`, `engine/tape_flow.py`,
  `engine/prophet_bridge.py` `[V]`. **This corrects the census options lane, which recorded consumers as
  "NOT VERIFIED — no reader module found".**
- **Status: DECLARED, ZERO ROWS.** See §4.

### 2.2 Options

#### Cboe (free delayed chain + VIX futures)

- **Datasets:** SPX/index dealer-gamma (GEX), put/call ratios, skew, VVIX, **VIX futures settlements and the
  full M1..M6 VX term structure**.
- **Realtime/delayed:** *"Delayed chain, EOD cadence: a regime/vol-context input, not a day-trading tool"*
  (`collectors/cboe.py:14-15`) `[V]`.
- **Canonical storage:** `data/cboe/` — 16 files including `gex.parquet`, `gex_<TICKER>.parquet` ×10,
  `putcall.parquet`, `skew.parquet`, `vix_curve.parquet`, `vix_futures.parquet`, `vvix.parquet` `[V]`.
- **Ingestion:** `collectors/cboe.py`; VX curve `collectors/cboe_vix_futures.py`.
- **Why the VX store exists (worth preserving in any consolidation):** on 2024-08-05 spot VIX printed ~65
  intraday on thin early-session SPX quotes while front VX stayed below ~35; storing the VX settlement lets
  `engine/dislocation.py` flag the spot print UNRELIABLE rather than treat it as a real panic trigger
  (`collectors/cboe_vix_futures.py:1-8`) `[V]`. **This is a working precedent for cross-source
  reconciliation as a first-class output, not a cleanup step.**
- **Known quality issues:** the GEX dealer long-call/short-put SIGN is an assumption, not ground truth, and
  the module says so (`collectors/cboe.py:2-15`) `[V]`. Index symbols carry a leading-underscore convention
  (`_SPX`) distinct from the plain-ticker single-name path in the same collector `[C]`.
- **Hardcoded inputs:** `r = 0.043` flat regardless of tenor or date (`collectors/cboe.py:230`,
  `scripts/build_polygon_gex.py:109`) and a 4-entry dividend-yield dict
  (`collectors/cboe.py:142 GEX_Q = {'_SPX':0.013,'SPY':0.013,'QQQ':0.006,'IWM':0.013}`), so **every
  single-name underlying gets q=0.0** `[C]` — while `data/massive_options_day/_effr_dff.parquet` sits inside
  the same store, apparently purpose-built to supply the rate, unreferenced `[C]`.

#### Databento (metered NBBO calibration)

- **Datasets:** OPRA trades + prevailing NBBO (`tbbo` schema).
- **Purpose and limit:** the ONE optional, ~$0 data add — the Databento signup credit covers a focused
  universe; used to compute gold-standard quote-rule signs and **calibrate** the tick-rule fallback that
  massive.com's entitlement forces (`collectors/databento_tbbo.py:1-8`) `[V]`.
- **Cadence:** occasional, manual — `python -m scripts.calibrate_flow_signing`. **NOT in the daily build**
  (`collectors/databento_tbbo.py:10-13`) `[V]`.
- **Fallback:** INERT until `DATABENTO_API_KEY` is set and the package installed; no key → empty frame,
  never raises (`collectors/databento_tbbo.py:10-11`) `[V]`.
- **Cost gate:** `MAX_COST_USD = 2.0` per fetch `[C]`.

#### Options stores on disk (all four vendors land here)

| Store | Entries on disk `[V]` | Grain / identifier | Note |
|---|---|---|---|
| `data/polygon_gex` | 404 | `underlying` + `strike_ticker` (`O:`-prefixed) + `expiry` + `K` + `is_call` | per-strike raw chain, retained because **open interest is point-in-time only and cannot be backfilled** (`collectors/polygon_options.py:5-8`) `[V]` |
| `data/massive_options_day` | 5 | OPRA `ticker`, `window_start` ns | includes `_effr_dff.parquet` (unwired rate series) `[C]` |
| `data/options_tape_signed` | 22 | `underlying` + `date` — **no per-contract identity retained** `[C]` | tick-rule signed, not quote-rule |
| `data/options_flow` | 371 | `ticker` | census lane flagged its schema fields as *not deep-inspected* `[C]` — treat identifier/cadence as unconfirmed |
| `data/options_skew`, `data/options_ivspread` | 2 each | `underlying` + nearest-expiry | `engine/options_ivspread.py:64,179` documents an **acknowledged, uncorrected** vendor-IV call/put offset from dividends/borrow `[C]` |
| `data/index_gex_history` | 5 | index ticker | |

**Options contract identity has FOUR mutually incompatible encodings in simultaneous use, with no
crosswalk module** `[C]`: fixed-width OCC-21 (`engine/options_focused_quote.py:641-646`), Polygon's raw
variable-root `O:` ticker (`collectors/polygon_options.py`, verified on disk as
`O:SPY260710C00525000`), a synthetic sha256 `contract:uchain:<hash>` (`engine/options_focused_quote.py:636-638`),
and a bare `(root, strike, exp, right)` tuple (`engine/options_structure.py:249-261`). Field-name drift
compounds it: `expiry` vs `expiration` coexist **inside single files** (`options_hub.py` 47×/5×,
`options_nbbo_cohort.py` 20×/16×, `options_structure.py` 3×/14×) `[C]`, and right/type has four encodings
(`C`/`P`, `CALL`/`PUT`, `is_call` bool, `option_type` str) while the standard OPRA `cp_flag` **never
appears anywhere** `[C]`.

**Already-realized cost, not a hypothetical:** `scripts/build_polygon_gex.accrue` stamped
`datetime.now(timezone.utc).date()` — the RUN date, not the session — so the write-side `is_session` gate
refused every Saturday-UTC run (= a Friday-evening ET accrual), silently dropping Fridays from the store.
The repair reclassified 42 files → 29 sessions: 24 redated, 13 collision duplicates removed, 5 quarantined
because their `spot` column was a live intraday tape contaminating every spot-derived GEX field
(`scripts/migrate_polygon_gex_session_stamps.py:1-31`) `[C]`. A second one-shot,
`scripts/quarantine_polygon_gex_20260807_preopen.py:1-18`, quarantines a pre-open capture as an
unrecoverable gap rather than re-dating it `[C]`. The verification lesson is in that docstring: **"SPY alone
called the 08-06 file 0.175% fine while 59% of its names disagreed"** — a single-name spot check cannot
validate a whole-chain snapshot's timestamp.

### 2.3 China and Hong Kong

#### TuShare — two entirely separate code paths, one live, one dormant

**(a) `collectors/tushare_client.py` + the add-on family (LIVE).**
- **Datasets:** `data/tushare/{broker,chips,valuation,margin,moneyflow,forecast,cn_company,cn_disclosure,cn_holdernum,cn_reports,mainbz,report_rc}.parquet` — 20 entries on disk `[V]`.
- **Identifiers:** `ts_code`, normalized by `collectors/tushare_client.py:61-68 norm_ticker()` — `.SH → .SS`
  only, `.SZ`/`.BJ` passthrough `[C]`.
- **Cadence:** nightly, throttled (1 call/hr for `report_rc`, else a shared 500/min pool) `[C]`.

**(b) `collectors/china_tushare_spine.py` — the full-A provenance spine (CODE-COMPLETE, ZERO ROWS).**
- **Design authority:** `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md`, which pins every vendor
  endpoint contract by URL and states the stop-ship boundary: *"It does not authorize TuShare use… Until
  that real receipt exists and a scalable cap plan is reviewed, this lane is
  `foundation_only_no_live_entitlement_or_scalable_backfill`"* (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:16-24`) `[V]`.
- **Licensing — the strictest gate in the estate:** TuShare's service agreement describes ordinary personal
  authorization as private/noncommercial; before ANY network or store mutation the collector requires a
  separately issued **written** vendor or institutional grant covering API access, bulk local retention,
  quantitative strategy research, commercial use, and private internal derivatives
  (same file, `:16-24`) `[V]`. A token is not permission
  (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:38`) `[V]`.
- **Adjustment:** `daily` is declared **unadjusted nominal price authority**;
  `price_source_basis = 'tushare.daily_unadjusted_nominal'`; `stk_limit` is the **exact legal-band
  authority**; canonical event prices are integer CNY cents (`collectors/china_tushare_spine.py:47-50`) `[C]`.
  `pro_bar` adjusted-price construction is listed under `not_tested`
  (`research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md:294`) `[C]`; **`adj_factor` is never called** `[C]`.
- **Identifiers:** `CN-XSHG-600519`-style listing keys via `canonical_identity()`, plus the 3-way tables
  `MIC_BY_SOURCE_EXCHANGE` / `REPO_SUFFIX_BY_SOURCE_EXCHANGE` / `SOURCE_EXCHANGE_BY_SUFFIX`
  (`collectors/china_tushare_spine.py:177-179`) `[C]`. Board classification is a pure code-range function
  with a runtime guard that raises `SpineError` when TuShare's declared market disagrees with the code range
  (`collectors/china_tushare_spine.py:465-480`, guard at `:1873-1876`) `[C]`.
- **Status: DECLARED, ZERO ROWS.** Declared default store root
  `~/.local/share/macro-dashboard/china_tushare_spine` (`collectors/china_tushare_spine.py:16-18`) `[V]`;
  `ls ~/.local/share/macro-dashboard` → *No such file or directory*, 2026-08-12 `[V]`. See §4.

#### akshare / Eastmoney / Sina (the live CN plane)

- **Datasets:** `data/china_stocks_raw` (1,592 entries) `[V]`, `data/china_zt_pool` (limit-up pool, 1 entry) `[V]`,
  `data/china_fundamentals`, `data/china_analyst`, `data/china_macro` (13) `[V]`, `data/china_connect` (2) `[V]`,
  `data/china_news`, plus ~40 further `collectors/china_*.py` lanes.
- **Adjustment:** `data/china_stocks_raw` is the **Yahoo/yfinance auto_adjust total-return plane**
  (`collectors/_stock_ohlc.py:92`) `[C]`. TuShare's native qfq/hfq planes are **not ingested at all** `[C]`.
  So the CN adjustment options are exactly two — "Yahoo TR-adjusted" (live) and "TuShare unadjusted"
  (dormant) — **not** the classic qfq/hfq/none triad.
- **Standing prohibition:** `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` forbids the Yahoo-plane adjusted CN tape
  for any limit-band/legal-limit math; the REOPEN PATH is authorized unadjusted TuShare `daily` × same-key
  vendor `stk_limit` with integer-cent equality and exchange half-up validation
  (`research/DO_NOT_REBUILD.md:130`) `[V]`. **The only sanctioned CN limit-band source has zero rows.** A
  correct CN limit architecture must therefore be designed against a dataset that does not yet exist —
  that is a build sequencing fact, not a blocker to state.
- **Two limit-up sources with very different trust levels:** `data/china_zt_pool` (akshare
  `stock_zt_pool_em`) is self-labelled *"DISPLAY-ONLY context… never a validated buy ranking"*
  (`collectors/china_zt_pool.py:1-16`) `[C]`, versus the spine's `stk_limit` exact-legal-band authority.
  Name them distinctly (`zt_pool_display` vs `stk_limit_authority`) or a future consumer will conflate them.
- **Known quality issue (the canonical silent-death case):** Stock Connect northbound `net`/`buy`/`sell`
  **all three** died together after 2024-08-16 (CSRC rule change) and sat unnoticed for ~2 years behind a
  live `turnover` sibling column; `ColumnContract` now makes each column's expected-null state explicit
  (`collectors/china_connect.py:14-32`, contract block `:109-139`) `[C]`. 450 fake-zero `hold_mktcap` values
  were healed 2026-08-04 by coercing 0 → NaN so `store.upsert`'s `combine_first` could not let a stale
  stored 0.0 win `[C]`.

#### Hong Kong

- **Datasets:** `data/hk_stocks` (159 entries) `[V]`, `data/hk_breadth`, `data/hk_fundamentals`.
- **Identifiers:** 4-digit zero-padded code + `.HK` (e.g. `0700.HK`) — yfinance's native format already
  matches the repo namespace, **no remap needed** (`collectors/hk_stock_prices.py:1-30`) `[C]`.
- **FX:** CN/HK cross-asset math derives `cny_per_hkd = usdcny / usdhkd` — a cross-rate through two USD
  legs, not a quoted CNYHKD pair — and `engine/hk_ah.py:1-16` explicitly disclaims level accuracy versus the
  official Hang Seng AH Premium Index `[C]`. HKD is modelled as a hard peg with a hardcoded 7.75–7.85 band
  used only for a peg-distance annotation (`engine/country_fx.py:89`, `:63`, `:239-243`) `[C]`.
- **Calendars — a dated, monitored expiry:** `lib/cn_calendar.py:33-40` is a hand-curated holiday frozenset
  sourced from the Mastermind bot repo, with `HOLIDAY_COVERAGE_END = date(2027, 12, 31)` at `:76`; past that
  it degrades to weekday-only math with a warning `[C]`. `lib/hk_calendar.py` computes most holidays by rule
  but hardcodes Lunar New Year and Ching Ming through 2030 (`:100-111`) and carries only 4 historical
  typhoon/rainstorm closures in `ONE_OFF_CLOSURES` (`:33-38`), appendable only after the fact `[C]`.
- **Missing entirely:** no `lot_size` / `board_lot` / round-lot source exists anywhere in
  `collectors`/`lib`/`engine` for CN or HK `[C]`. CN 100-share lots, per-name HK board lots, and the STAR
  board's 200-share minimum have **no data source in this repo**. Net-new if needed.

### 2.4 Macro

#### FRED (live series) and ALFRED (vintages) — one collector, two very different guarantees

- **Datasets:** `data/fred/<SID>.parquet` — **166 files on disk** `[V]`; `data/fred_vintage/vintages.parquet`
  plus `alfred_depth_audit.json` `[V]`.
- **Ingestion:** `collectors/fred.py` — official API when `FRED_API_KEY` is set, keyless `fredgraph.csv`
  fallback with aggressive retries (`collectors/fred.py:1-9`) `[V]`. Vintages require the key; the keyless
  path has **no vintage endpoint at all** (`collectors/fred.py:197-226`) `[C]`.
- **Timestamps:** the live store's index is the **reference period** the observation describes (native FRED
  stamping) with **no release-date column** `[C]`. The vintage store carries `(series, period)` +
  `realtime_start` (first publish) + `realtime_end` `[C]`.
- **Revision behaviour — the defining property of this source:** FRED series revise; ALFRED is the only
  place the pre-revision value survives. `output_type=4` = initial-release only `[C]`.
- **Deliberate exclusions that are CORRECT, not gaps:** market data (rates, OAS, VIX, FX, dollar) is never
  revised and is excluded from vintage tracking by design (`collectors/fred.py:36-41`) `[C]`.
- **Known quality issue — history is truncated at the vendor:** since April 2026 FRED serves only a rolling
  3-year window for the ICE BofA OAS series (`BAMLH0A0HYM2`, `BAMLC0A0CM`); the store's upsert is
  append-only so everything ever seen is kept permanently, and pre-window history lives in `data/archive/`
  (`collectors/fred.py:8-13`) `[V]`. **This is the house's best "vendor window slides, our parquet does not
  forget" pattern** and it recurs at `collectors/bgeo.py:6-9` `[V]`.
- **Known discrepancy — config declares more than the store holds:** `config.yml:124-169` declares a
  54-series vintage superset; the on-disk `vintages.parquet` carries 26 series / 10,103 rows, so **28
  configured series — including UNRATE, RSAFS, JTSJOL, ADPMNUSNERSA — are declared PIT-tracked and have zero
  rows** `[C]`. A caller asking `as_of_series('UNRATE', …)` silently gets an empty Series and
  `engine/pit.py` falls back to reference/latest `[C]`. GDP/GDPC1 is not collected from FRED at all — only
  the GDPNow nowcast `[C]`.
- **The adoption gap that matters more than any of the above:** a leak-free PIT accessor exists and is
  well-engineered (`engine/pit.py`, `basis='release'`, per-series modelled release-lag calendar at
  `engine/pit.py:110-140`, effective-lag resolution preferring learned > measured > prior at
  `engine/pit.py:181-191`) `[C]`, but **every live scored consumer calls `build_features()` with the default
  `pit_basis=None`**, i.e. latest-revised values — `scripts/build_site.py:4664`, `engine/equity_alloc.py`
  (5 sites), `engine/strategies.py:72`, `engine/masterminds.py:196`, `scripts/build_bonds.py:1381`, and
  ~15 more, all zero-arg `[C]`. `basis='release'` appears only in shadow/audit scripts
  (`scripts/build_regime_v2_pit.py:376`, `scripts/validate_drawdown_risk_pit.py:172`,
  `scripts/shadow_pit_regime.py:199-200`) `[C]`. **The fix is built and unused.**

#### Other macro sources

| Vendor | Datasets (entries on disk `[V]`) | Ingestion | Key facts |
|---|---|---|---|
| BIS | `data/bis` (5) | `collectors/bis.py` | keyless SDMX REST v2, permissive attribution-only licence; credit-to-GDP gap + DSR, quarterly (`collectors/bis.py:1-8`) `[V]` |
| Bank of Canada VALET + StatsCan WDS + FRED comparables | `data/canada_macro` (16) | `collectors/canada_macro.py` | three independently-degrading sources, keyless, one parquet per column; **no release-date tracking** `[C]` |
| Eastmoney datacenter (CN macro) | `data/china_macro` (13) | `collectors/china_macro.py` | scraper plane, keyless, degrade-never-raise `[C]` |
| FRED CSV OECD/Eurostat repack (+ optional official ECB/Eurostat) | `data/intl_macro` (37) | `collectors/intl_macro.py` | per-column fallback to FRED if an official endpoint fails; **never erases last-known-good**; `provenance.json` sidecar `[C]` |
| Cleveland Fed daily inflation nowcast | `data/cleveland_nowcast` (2) | `collectors/cleveland_nowcast.py` | **genuinely PIT by construction** — keyed `(target_period, series, obs_date)`, `keep='first'`, so `obs_date` IS a first-seen vintage record `[C]`. The cleanest PIT primitive in the macro estate. |
| CFTC Commitments of Traders | `data/cot` (17) | `collectors/cot.py` | Socrata API, keyless, weekly Friday ~15:30 ET for **Tuesday** data; *"the 3-day lag is labeled wherever this is displayed"*; ZIP fallback (`collectors/cot.py:1-8`) `[V]` |
| SEC Fails-to-Deliver | `data/sec_ftd` (1) | `collectors/sec_ftd.py` | semi-monthly pipe-delimited zips; **pre-registered PIT law**: `availability_date = period_end + 30 calendar days` (`collectors/sec_ftd.py:1-9`) `[V]`. A ~37-day-old mtime here is CORRECT cadence — the canonical counter-example to naive staleness ranking `[C]` |
| US Census international trade (HS imports) | **ABSENT** | `collectors/census_trade.py` | endpoint verified live 2026-07-09 (`collectors/census_trade.py:1-9`) `[V]`; needs an API key; **0 files on disk** `[V]` — see §4 |
| BLS print-integrity / work stoppages | **ABSENT** | `collectors/bls_print_integrity.py`, `collectors/bls_work_stoppages.py` | function-based, not `Adapter` subclasses ⇒ outside the nightly adapter loop; **0 files on disk** `[V]` — see §4 |
| BLS CPI relative-importance weights | `data/release_forecast/component_weights/*.yml` | `collectors/bls_cpi_weights.py` | YAML by design, fail-open to committed YAML — **not** expected under `data/bls_cpi_weights/` `[C]` |

### 2.5 Fundamentals and corporate filings

#### SEC EDGAR — four surfaces, three generations of the same lesson

| Store | Rows `[C]` | Timestamps | Restatement handling |
|---|---|---|---|
| `data/edgar/fundamentals.parquet` | latest-FY snapshot | none per-row | **leaky** — own docstring: a backtest on it *"would use TODAY's restated numbers at every past date (look-ahead) and only TODAY's listed tickers (survivorship)"* (`collectors/edgar.py:463-465`) `[C]` |
| `data/edgar/fundamentals_panel.parquet` | 22,014 | `period_end` + `asof_date = period_end + 120d` (frames API has no true SEC `filed` timestamp, `collectors/edgar.py:469-471`) | the leak-free upgrade; capex PIT-gate-joined `collectors/edgar.py:492-527` |
| `data/edgar/statements.parquet` (annual) | 8,784 | `period_end`, **no `filed` column** | *latest-filed wins on restatement* — prior vintages discarded (`collectors/edgar_facts.py:154`) |
| `data/edgar/statements_quarterly.parquet` | 62,253 | `period_end` **and `filed`** and `as_of` | **the only US fundamentals store with a genuine per-row filing timestamp** — the anchor for any TTM/PIT policy (`engine/capital_allocation.py:57`) |

`data/edgar` holds 34 entries on disk `[V]`.

- **GAAP vs adjusted:** effectively **out of scope** across every production fundamentals surface —
  `grep` for `adjusted`/`non-GAAP` across `engine/fundamental_forensics/normalize.py` and `models.py`
  returns zero hits; the codebase works entirely off SEC-reported GAAP XBRL facts `[C]`.
- **Survivorship:** the panel includes delisted filers in historical frames, but current
  `company_tickers.json` cannot map a delisted CIK back to a ticker, so the panel is current-universe
  tickers carrying their own history (`collectors/edgar.py:474-478`) `[C]`. `collectors/edgar_deadnames.py`
  documents the downstream cost: **0 of 1,083 dead-only tickers** in
  `data/breadth/sp1500_pit_membership.parquet` carry fundamentals `[C]`.
- **Standing hold:** `DNR:HOLD-FF-DETECTOR-PERIOD-BASIS` (`research/DO_NOT_REBUILD.md:169`) `[V]` — four
  shared forensic detector ids exist in three implementations pairing periods on three different bases with
  three different PIT gates. **Deliberately held. Do not unify one leg in isolation** — the same
  `detector_id` MEANS "quarterly YoY" on `site/fundamental_forensics.html` and "annual YoY" on
  `site/stock.html`, so unifying silently republishes a live surface `[V]`.

#### SEC Company Facts (Wave 3A bitemporal substrate)

- **Vendor:** SEC EDGAR Company Facts API. Rights recorded per artifact:
  `"rights": {"redistribution_class": "public_source_link", "attribution_required": True,
  "license_note": "United States SEC EDGAR public Company Facts response"}`
  (`collectors/sec_capital_structure_companyfacts.py:5393`) `[C]`.
- **Clocks — five, and they are named:** `accepted_at` (EDGAR made it knowable), `recorded_at` (we retained
  it), `mapping_available_at` (the mapping rule became available), `computed_at`, `published_at`
  (`research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md:41-51`) `[V]`, pinned in
  `contracts/fundamental_forensics_run.schema.json:10,25` `[V]`.
- **The ruling that governs all replay work:** *"Running a 2022 filing through a rule written in 2026 is a
  current-rule recomputation, not a 2022 system replay"*
  (`research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md:56-57`) `[V]`. Company
  Facts is a **mutable** endpoint: a snapshot taken today may contain facts filed years ago but was not
  knowable to us until today, and the collector must never backdate a retained snapshot using a
  caller-supplied cutoff (same file, `:36-39`) `[V]`.
- **Storage — breaks the filesystem-first pattern by design:** generation-atomic, immutable, append-only CAS
  in **R2**, plus a separate DEDICATED attested-history bucket read via `FF_ATTESTED_R2_READONLY_*` env vars
  that deliberately never imports `engine.research_vault.r2_store` (`engine/fundamental_forensics/attested_history_store.py:1-8`) `[C]`.
- **Status: no local materialization.** `data/capital_structure` does not exist in the DATA checkout
  (`ls -d data/capital_structure` → *No such file or directory*, 2026-08-12) `[V]`. See §4.
- **Note for the catalog's own honesty:** this lane is also the only one in the estate that REQUIRES a
  producing-code provenance block — `{repository, workflow_ref, run_id, run_attempt, commit_sha, event_name,
  actor}` with a 40-hex `_COMMIT_SHA_RE` (`engine/capital_structure/share_count_r2_conformance.py:750,766-767`) `[C]`.
  Everything else in `data/` carries a wall clock and no code version (§5.5).

#### Calcbench — NOT a vendor. Correction.

The brief and the design premise both name "Calcbench 5-clock bitemporal fundamentals" as an in-repo
pattern. **Calcbench is a parity TARGET, not an ingested source.** `grep -rli calcbench --include='*.py'`
over `collectors engine scripts lib` returns only the untracked `lib/dataos/` prototype `[V]`; the name
appears exclusively in `research/CALCBENCH_PARITY_*.md` dockets `[V]`. There is no Calcbench API key, no
Calcbench collector, and no Calcbench data. The 5-clock model is **ours**, built over SEC EDGAR Company
Facts, to reach parity with what Calcbench sells. The design decision is unaffected; the attribution is.

#### Finnhub

- **Datasets:** earnings-call transcript LIST (metadata only — id, symbol, event time, quarter, year; bodies
  are NOT fetched nightly) (`collectors/finnhub_transcripts.py:1-6`) `[V]`; and an alt-data trio
  (recommendation trends, insider MSPR, earnings surprises) over a capped watchlist on the free 60 req/min
  tier (`collectors/finnhub_altdata.py:1-7`) `[V]`.
- **Status of the alt-data trio: DEAD STORE.** `data/finnhub` does not exist in the DATA checkout
  (`ls -d data/finnhub` → *No such file or directory*, 2026-08-12) `[V]`. The collector's own docstring
  records that `data/finnhub/recommendation.parquet` **has never existed** and that seven consumers have
  been reading a missing store and failing open to null the whole time; root cause was a 401/403
  auth-plan-gate misclassified as a transient outage (`collectors/finnhub_altdata.py:19-21`) `[C]`.
  `engine/analyst_revisions.py:27-34` reads it; `:29-30` returns None when absent `[C]`. See §4.

#### Earnings and consensus — the leakage answer

**There is no append-only, locally-timestamped consensus-before-earnings store anywhere in the codebase.** `[C]`

Every estimate/consensus surface is a mutate-in-place snapshot: `data/earnings/earnings.parquet` (1,364 rows,
**2 distinct `as_of` values across the whole universe**; `eps_forecast` rebuilt wholesale every sweep at
`collectors/equity_earnings.py:396-403`), and the identical `{ticker, payload, asof}` shape in
`data/china_analyst/forecast.parquet` (2,787 rows), `data/china_fundamentals/fundamentals.parquet` (801),
`data/canada_fundamentals`, `data/canada_earnings`, `data/hk_fundamentals` `[C]`. `contracts/` holds **zero**
schema files matching earning/estimate/consensus, against 30 for capital_structure `[C]`.

The one place a pre-print consensus is retained historically is `surprises_json` inside
`data/earnings/earnings.parquet` (`collectors/equity_earnings.py:184-194`), sourced from Nasdaq's own
**retrospective** surprise table — it carries no independently captured `known_at`, so it trusts the
vendor's post-hoc labelling by fiscal quarter `[C]`.

Consequence: joining `eps_forecast` to a past earnings date uses TODAY's most-recently-fetched estimate.
Structurally identical to the pre-panel `edgar.py` leak the codebase already diagnosed and fixed once — and
never generalized to estimates or to the non-US lanes.

Genuine exception worth naming: `data/stock_fundamentals/snapshots.parquet` (yfinance `.info` ratios,
weekly, wide `TICKER__field` columns) is the **only** US fundamentals-ratio store that is genuinely
append-only time series — 22 distinct collection dates × 1,610 columns `[C]`. Its own producer marks it LOW
CONFIDENCE (unofficial yfinance `.info` fields, `collectors/sector_holdings.py:404-406`) `[C]`.

**Producer note the census missed:** `collectors/sector_holdings.py` writes BOTH `data/stocks` (price,
`class StockPriceAdapter`, `:259/:263`) and `data/stock_fundamentals` (`name='stock_fundamentals'`) `[C]` —
one collector module, two unrelated datasets, which is why the price store's producer was hard to find.

### 2.6 News and alt data

| Source | Store (entries `[V]`) | Ingestion | Entity mapping | Notes |
|---|---|---|---|---|
| Multi-desk wire (qbus) | `data/qbus` (4) | `engine/qbus.py`, written by 7 desk modules | entity/theme clusters | the ONE real cross-source event identity: `item_id` per article, `event_key` per clustered event via union-find on shared entity/theme + 3-day window + title-shingle Jaccard ≥ 0.6 (`engine/qbus.py:176-236`), `echo_stats()` at `:502-557` `[C]` |
| — | `data/news` (1) | `engine/news_event_ledger.py` | — | `event_id` = hash(title, domain); **deliberately per-article, NOT cross-source** (`engine/qkernel.py:193-204`) `[C]` |
| — | `data/news_vector` (2), `data/china_news_vector` (1) | `engine/news_vector.py`, `engine/china_news_intel.py` | tickers column (CN only) | **no embedding column in either** — verified column lists `[C]`. LLM extraction stubbed off (`engine/news_vector.py:45-47`) `[C]` |
| Polygon news insights | (rolls into convergence kernel) | `collectors/polygon_news.py` | ticker | tiered universe 120 → 500 names behind a runtime budget probe (`collectors/polygon_news.py:9-16`) `[V]` |
| CCTV / flash wires (CN) | `data/china_news` | `collectors/china_news.py`, `collectors/china_news_wire.py` | none | **aggregate daily tone numbers only** — no article rows, no publication times (`collectors/china_news.py:24-29`, `collectors/china_news_wire.py:14-16`) `[C]`. The article-level CN data is built at BUILD time by the engine, not by a collector. |
| ClinicalTrials.gov v2 | `data/clinicaltrials` (3) | `collectors/clinicaltrials.py` | **curated sponsor-name → ticker JSON**, `data/clinicaltrials/sponsor_ticker.json` `[C]` | keyless; Phase-3 START/COMPLETE events per curated sponsor (`collectors/clinicaltrials.py:1-10`) `[V]`. Rights recorded as `"license_class": "us_government_source_facts"` (`collectors/biocatalyst/clinicaltrials_v2.py:925,980`) `[C]` — **a different key name from the SEC collectors' `redistribution_class`** (§5.4) |
| Quiver (congress/insiders/13F/lobbying) | via `engine/altdata.py` `DATASETS` | — | raw ticker string + `lib/ticker_aliases` + `engine/ticker_shape` hygiene regex (`engine/altdata_models.py:30-35`) `[C]` | |
| SEC beneficial ownership | — | `collectors/beneficial_ownership.py` | **CIK → ticker via the SEC company_tickers master**, plus FILED-BY custodian parsed from free-text SGML (`collectors/beneficial_ownership.py:1-11`) `[C]` | a third identity mechanism in one lane |

**Publication vs ingestion time is modelled well here and nowhere else as well:** `engine/qbus.py:45-52`
defines a `TIMESTAMP_QUALITY` enum — `CRAWL_BOUNDED | PUBLISHER_STATED (+15min tolerance, reject
pubDate < crawl−48h) | DISCLOSURE_DATE (EDGAR, +1 business day) | EVENT_DATE (never an entry anchor) |
SNAPSHOT_DATE (display-only) | CORRUPTED (blocked+alert)` `[C]`. That is effectively a **trust tier on the
timestamp itself**, a dimension the rest of the estate lacks.

**Naming collision to avoid inheriting:** four unrelated top-level stores are named `*vector*` —
`data/vector`, `data/spvector`, `data/news_vector`, `data/china_news_vector` — and **none contains
embeddings** `[C]`. There is no vector/embedding store in this repo. Reserve the name.

### 2.7 Crypto and on-chain

| Source | Store (entries `[V]`) | Ingestion | Facts |
|---|---|---|---|
| CoinMetrics Community API | `data/coinmetrics` (10) | `collectors/coinmetrics.py` | free, keyless; MVRV/mcap/addresses/hashrate back to 2010 at 1d. **Community tier serves only the configured metrics — others return 403, verified 2026-06-12** (`collectors/coinmetrics.py:1-6`) `[V]` |
| bitcoin-data.com (BGeometrics) | `data/bgeo` (13) | `collectors/bgeo.py` | **10 req/hour, 15/day PER IP**; CI shared-runner IPs may collide with strangers, so quota exhaustion is routine not exceptional; rolling ~4-year window ⇒ archive-forever upsert (`collectors/bgeo.py:1-9`) `[V]` |
| Coinbase Exchange public candles | — | `collectors/coinbase.py` | free, keyless; BTC daily from 2015-07, BTC hourly from 2016 (~92k rows), ETH/SOL daily (`collectors/coinbase.py:1-9`) `[V]` |
| Checkonchain | `data/checkonchain` (2) | `scripts/backfill_crypto.py` | **NOT a collector** — a one-time manual backfill script scraping Plotly JSON; no `Adapter` subclass exists `[C]`. Any freshness monitor pointed at this directory will misfire forever. Classify as manual-archive. |

### 2.8 Cross-repo consumers

#### 2.8.1 charting-app (Terminal)

- **Daily chart OHLC** (`terminal/public/data/<SYM>.json`) is **not one pipeline**. It is seeded once by a
  direct local-filesystem read of Macro's parquet stores —
  `charting-app/ingest/build_universe.py:49 MACRO = Path(os.environ.get('MACRO_REPO', '/Users/chriswong/Documents/Cluade/Macro Dashboard'))` `[C]`
  — then topped up forever by `charting-app/ingest/refresh_ohlc.py:39-41`, which calls Polygon grouped-daily
  with `adjusted=true` `[V]`.
- **Consequence:** a single symbol's own file carries a **TR-adjusted historical segment followed by
  split-only-adjusted appended bars**, with no field distinguishing the two segments `[I]` (the inference is
  Polygon's documented split-only semantics — see §2.1 Polygon). The UI asserts otherwise unconditionally:
  `terminal/components/ChartFrameBar.tsx:379-381` renders a static `ADJ` chip whose tooltip reads
  *"Adjusted data (split & dividend adjusted)"* (`terminal/lib/i18n.tsx:285`), with no conditional on
  `src`/`bar_quality` `[C]`.
- **Filesystem coupling:** `grep -rln 'Cluade/Macro Dashboard' --include='*.py' ingest | wc -l` → **17
  files** in charting-app, 2026-08-12 `[V]`, e.g. `charting-app/ingest/collect_us_deep.py:37-39`, which
  reads Macro's `site/stockdata/` for its universe, calls yfinance itself, and **writes the result back into
  Macro's `data/tushare/us_deep.parquet`** `[V]`. The three "separate services" share one filesystem tree on
  one machine.
- **Intraday** is Polygon-direct (US/crypto) or Tencent-direct (CN/HK), never Macro, never R2, never Supabase
  (`terminal/lib/intradaySources.ts:51-83,96-118,149-173`) `[C]`, mediated for US/crypto quotes by an
  undocumented localhost sidecar ("Quote Hub", `127.0.0.1:3100`, `terminal/lib/intradaySources.ts:285-301`)
  whose failure mode is a silent fallback to stale manifest EOD `[C]`.
- **User-data plane:** Supabase Postgres with RLS, owner-scoped by `auth.uid() = user_id`
  (`charting-app/supabase/migrations/0001_init.sql:2-6`) `[C]`. Its own header states the boundary:
  *"Market data, signals, regime, and backtests are NOT stored here — they are read from the
  macro/Mastermind publish-pull side"* `[C]`. **This is a real, stated contract the Data OS can cite rather
  than invent.**
- **`public.portfolio_positions` — a live production table whose `CREATE TABLE` is in no merged branch of
  any repo.** Recovered only by read-only PostgREST error-probing into an unmerged sibling worktree
  (`charting-app/.claude/worktrees/wp-w1b-canonical-watchlists/supabase/migrations/0007_portfolio_positions.sql:1-24`) `[C]`;
  only its RLS policies were version-controlled, on the Macro side, at
  `templates/uwp_supabase.sql:1-21` `[C]`. Written by Macro's `templates/watchstore.js`, read by the
  Terminal portfolio UI `[C]`.

#### 2.8.2 Mastermind (trading bot)

- **`vendor/macro` is a floating sparse checkout, not a pinned submodule**, despite `Mastermind/AGENTS.md:10-11`
  calling it pinned `[C]`. Allowlist:
  `Mastermind/data_layer/macro_refresh.py:96-99 _SPARSE_PATHS = ("site", "data/regime", "engine", "lib", "data/yahoo", "data/risk_radar", "data/china_regime", "data/stage_analysis/context", "data/metabolism")` `[V]`.
- **`data/stocks` is absent from that allowlist** `[V]`, so `portfolio/held_risk.py`'s documented Tier-1
  source (`data/stocks`) **cannot exist on the bot host and always falls through to Tier-2 (`data/yahoo`)** `[C]`.
  A documented tier that is structurally dead is exactly the kind of thing a catalog exists to catch.
- **`Mastermind/portfolio/marks.py:12-19` ranks a raw/split-adjusted Polygon EOD close ABOVE the TR-adjusted
  Yahoo parquet** in its mark precedence `[C]`. On days Polygon succeeds the book marks on one convention;
  on fallback days it marks on another — **an adjustment-convention flip inside a single book's own NAV
  history**, structurally identical to §1.1 but inside one repo.
- **Machine contract plane:** `site/feeds/*.json` + `_manifest.json`, produced by `scripts/build_feeds.py`,
  which enforces byte-verbatim copy discipline — *"Copies are byte-verbatim — the source engine owns the
  schema; this script never reshapes what it copies"* (`scripts/build_feeds.py:13-14`) `[C]`, normalizing
  only the `asof` key and keeping build time separately in `feeds_meta.json:generated_utc` `[C]`. **Cite
  this as the positive precedent for the contract plane.** Materialized only during the daily lane and
  shipped to R2, never committed `[C]`.

---

## 3 · STORAGE TIERS (where the bytes actually live)

| Tier | What | Access | Notes |
|---|---|---|---|
| Local parquet | `data/<group>/<name>.parquet` via `lib/store.py:29-33 _path()` `[V]` | `lib/store.py:36 read()` / `:60 upsert()` `[V]` | `upsert` guarantees append-only history: new values win on date collision, rows only on disk are always kept (`lib/store.py:62-64`) `[V]`. **43 importers, all in `collectors/`, ingest-side `engine/`, `scripts/`, `tests/` — ZERO in `app/` or `admin/`** `[C]`: this is a WRITE-time abstraction, not a serving-tier data-access layer. |
| R2 (single bucket, prefix per store) | ~700 MB of per-ticker OHLC + search-library JSON; `massive_stock_day/` (~617 MB); capital-structure CAS; attested-history bucket | `scripts/publish_r2.py` (publish), `scripts/fetch_r2` (restore) `[C]` | md5-vs-ETag delta upload; publish independently refuses data-dir trees under ~100 files `[C]` |
| Supabase Postgres | user/billing/entitlement/analytics ONLY — no market-data tables `[C]` | `app/*.py` | **different governance model entirely** (RLS + Postgres), not filesystem+receipts |
| SQLite | derived indices only (`engine/context_index/schema.py`, `engine/research_vault/r2_store.py`, `collectors/biocatalyst/drugs_at_fda.py`) `[C]` | | not a general RDBMS |
| VPS LIVE dir | `$MACRO_LIVE_DIR` (prod `/var/lib/macro-live/public/live`), read-through by `app/main.py:98,549-554` `[C]` | | the ONLY thing `app/*.py` reads for market state — `grep -c read_parquet` across all 29 `app/*.py` and 58 `admin/*.py` = 0 `[C]` |
| Redis | **does not exist** | — | `grep -rl 'import redis\|redis.Redis(\|REDIS_URL\|from redis' --include='*.py' .` → **0 files** `[C]`. The earlier "28 files" was a substring match on *redistribution*. The masterplans explicitly reject it: *"Boring wins"* (`research/NEURAL_WEB_MASTERPLAN_BY_FABLE.md:44`, `research/BREATHING_PLATFORM_MASTERPLAN_BY_FABLE.md:151`) `[C]`. **Do not design around a cache tier that is not there.** |

Caching today is 100% in-process: ~19 module-level dicts with no invalidation, e.g.
`engine/ai_desk.py:186 _CLOSE_MEMO` keyed `(root, ticker)` with **no as-of/date dimension**, safe only
because a fresh process runs per nightly batch (`engine/ai_desk.py:210-218`) `[C]`. Any resident/live tier
must either keep process-per-batch isolation permanent or retrofit a data-version dimension first.

---

## 4 · DECLARED-BUT-UNMATERIALIZED

Datasets whose code is complete, whose docstrings read like shipped capability, and whose store has zero
rows. **A catalog that listed these alongside live stores would be exactly the lie this project exists to
make impossible.** All existence checks run 2026-08-12 against the DATA checkout.

| Dataset | Declared by | Store status `[V]` | What breaks if you assume it exists |
|---|---|---|---|
| **CN TuShare full-A spine** — `daily`, `daily_basic`, `stk_limit`, `suspend_d`, `stock_st` + `reference/{security_master,identity_aliases,instrument_classification}` | `collectors/china_tushare_spine.py` (~3,600 lines), contract `research/CN_TUSHARE_FULL_A_SPINE_CONTRACT_2026-08-08.md` | declared root `~/.local/share/macro-dashboard/china_tushare_spine`; `ls ~/.local/share/macro-dashboard` → **No such file or directory** | The `DNR:KILL-CN-ADJUSTED-TAPE-LEGAL-LIMIT` reopen path routes through this store. **The only lawful CN limit-band source has zero rows.** Collection is disabled by an immutable operational gate (`collectors/china_tushare_spine.py:38-41`) `[C]` pending a written vendor grant. |
| **GMI theme graph** — `nodes/edges/evidence` with `valid_from/valid_to`, `evidence_time`, `belief_time`, `confidence_basis`, and 3 weight axes | `engine/theme_graph/store.py:44-66` `[C]`, `engine/theme_graph/materialize.py` | `ls -d data/theme_graph` → **No such file or directory** | This is the architecturally-correct answer to weighted, PIT, evidence-backed theme membership. **Cite it as a target schema, never as a source.** The three shipping theme surfaces are all binary/unweighted; `economic_share`/`trading_beta`/`attention_share` are W1b-stubbed nulls awaiting W2 `[C]`. |
| **`data/thetadata_eod`** | `research/THETADATA_OPS_RUNBOOK.md:9-17`, `engine/thetadata_store.py` | 2 files: `_backfill_state.json`, `_manifest.json`. Manifest reads `{"store":"thetadata_eod","n_roots":0,"per_root":{},"updated_at":null}`. **Zero ticker parquets.** The producing ops worktree `/Users/chriswong/theta-ops-wt` also **does not exist on this machine** | **50 files reference this store** `[V]` including `engine/options_hub.py`, `options_matrix.py`, `options_surface.py`, `tape_flow.py`, `prophet_bridge.py`. Every one of them is reading an empty store on this host. |
| **`data/us_stocks`** | — | 1 file: `latest.json`. **Not a price store.** | Any census counting "stores" by directory over-counts this. |
| **`data/capital_structure`** (Company Facts generations, coverage, source manifests) | `collectors/sec_capital_structure_companyfacts.py:421-424` (`_data_root() -> config.data_dir()/capital_structure/companyfacts`) `[C]` | `ls -d data/capital_structure` → **No such file or directory** | Correct by design — this lane is **R2-CAS-native**, not filesystem-first. A catalog/lineage layer must treat R2 object paths as first-class store locations. Absence here is not a defect; assuming presence is. |
| **`data/finnhub`** (recommendation, insider_sentiment, earnings) | `collectors/finnhub_altdata.py`; read by `engine/analyst_revisions.py:27-34` | `ls -d data/finnhub` → **No such file or directory** | **Seven consumers fail open to null and have done so since inception** (`collectors/finnhub_altdata.py:19-21`) `[C]`. The only evidence the store is dead is a docstring — not a queryable state. |
| **`data/narrative_flare`** (`source_registry.json`, `first_coverage.parquet`) | `engine/source_registry.py:12,16` `[V]` | `ls -d data/*narrative*` → **no matches** | The census listed these as datasets. They are declared, not materialized, in this checkout. `engine/source_registry.py` remains the best in-repo TEMPLATE for evidence-accruing derived intelligence (AUTHORITY block `tier='display'`, `may_rank/may_gate/may_size/may_escalate` all False, `:54-60`; Beta-Bernoulli `cred=(hits+2)/(calls+7)`, `:134-141`) `[C]` — cite the pattern, not the data. |
| **`data/census_trade`**, **`data/bls_print_integrity`**, **`data/bls_work_stoppages`** | `collectors/census_trade.py`, `collectors/bls_print_integrity.py`, `collectors/bls_work_stoppages.py` | all three: **ABSENT** (0 files) | Function-based collectors, not `Adapter` subclasses ⇒ outside the nightly adapter loop `[C]`. `census_trade` additionally needs an API key `[V]`. `engine/release_integrity.py:4-6` states its own consumer *"is not yet called from the nightly pipeline"* `[C]`. |
| **`membership_history.parquet`** for ALL 8 basket suites | `engine/basket_membership_pit.py:97-99 ALL_SUITES` `[C]` | `find data -iname '*membership_history*'` → **zero results**; per-suite `stat` → all 8 MISSING `[C]` | **`members_asof()` falls back to current membership with `pit=False` for every suite on every date, today** — the exact look-ahead the module was built to prevent is the live behavior. Only raw evidence: 2 dated JSON snapshots under `data/baskets_china_ths/snapshots/` `[C]` (`data/baskets_china_ths` holds 5 entries `[V]`). |
| **`data/china_block_tape`** as a wired pipeline | `collectors/china_block_tape.py:73-81` *documents* `Adapter("china_block_tape", refresh, hosts=["akshare"], serial=True)` — inside the module **docstring**, as instructions for wiring that was never applied (`ast.parse` puts the docstring at lines 1-92; `grep -c '^class '` → 0) `[V]` | files exist on disk, but `grep -c 'china_block_tape' scripts/collect.py` → **0** `[V]` | The producer was never wired at all — no `Adapter` is ever constructed. From the filesystem alone that is indistinguishable both from a wired pipeline that broke and from a wired-but-empty one. |

**The general rule this section argues for:** wiring state (`WIRED` / `CODED_NOT_WIRED` / `MANUAL_ARCHIVE` /
`DECLARED_EMPTY` / `DEAD`) must be a first-class queryable field per dataset. Today the only way to tell
these apart is to read each producer's docstring by hand.

---

## 5 · CROSS-CUTTING FACTS EVERY CONSUMER MUST KNOW

### 5.1 Identity: at least TEN seams, three incompatible id schemes, demonstrable disagreement

`lib/ticker_aliases.py` is **not** the identity layer. It is 53 lines with exactly two entries —
`YAHOO_FETCH_ALIASES = {"FI": "FISV", "MMC": "MRSH"}` (`lib/ticker_aliases.py:36-41`) `[V]` — plus its
inverse `YAHOO_STORE_KEYS` at `:44` `[V]`, and its own comment scopes it: *"membership ticker → yfinance
symbol… a wrong entry silently stores another company's tape under this ticker, which no downstream check
can see"* (`lib/ticker_aliases.py:33-35`) `[V]`.

The census enumerated at least ten independently-governed identity surfaces `[C]`:
`lib/ticker_aliases.py`; `lib/delisted_symbols.py` + `config/delisted_symbols.yml` (*"the SECURITY STOPPED
EXISTING — it is not a rename"*, three consumers acting differently on it);
`lib/symbol_directory_receipts.py` (833 lines); `engine/entity_resolver.py` (a five-layer text→ticker
ladder with its own CN code-adjacency, ~280 中文 basket names, and a CUSIP→ticker map);
`engine/name_resolver.py`; `engine/ledger_identity.py` (372 lines); `collectors/edgar_deadnames.py`;
`config/theme_graph_identity_breaks.yml`; `config/biocatalyst_sponsor_ticker_map.yml` (1,057 lines);
`config/us_search_aliases_zh.json`.

**They disagree, provably.** `engine/ledger_identity.py:28-30` documents SATS→ECHO (2026-06-24) causing a
DOUBLE COUNT in `data/signal_archive/track_record.parquet`, and states that SATS is absent from the
dead-name registry `[C]`. SATS/ECHO is **not** in `lib/ticker_aliases.py` `[V]` — two rename registries that
do not agree. Three incompatible collision-suffix conventions coexist: `CN-XSHG-600519` (CN spine),
`co:<market>:<SYMBOL>#2` (`config/theme_graph_identity_breaks.yml`), and `US-XNYS-MMC.2` (the untracked
prototype) `[C]`.

**The measured cost of the fragmentation:** MMC→MRSH was carried by `scripts/fetch_basket_extras` but not by
`scripts/fetch_basket_ohlcv`, so `data/baskets/ohlcv/MMC.parquet` never existed and the insurance basket
silently rendered **18/19 members for 7 months** `[C]`.

Downstream, nothing outside Macro uses any of it: every user-owned and bot-owned plane keys securities by a
bare ticker text string with no market qualifier — `watchlist_symbols.symbol`, `alerts.symbol`,
`favorites.value` (`charting-app/supabase/migrations/0001_init.sql:43,79,90-91`) `[C]`,
`portfolio_positions.ticker` `[C]`, and the bot's parquet filenames `[C]`.

Also live and unresolved: **26 `engine/*.py` China modules hardcode yfinance-suffix ticker strings as
first-class dict keys**, e.g. `engine/china_market_drivers.py:263 extra['semis_rs'] = f['512760.SS'] / f['510300.SS']`
and an entire allocation-role table at `engine/china_allocation.py:45-59` `[C]`. The CN-XSHG spine cannot
become the identity layer while dozens of modules join on raw vendor suffixes.

### 5.2 There is no corporate-action event store, and the repo says so

No ex-date/type/factor event table exists for US or CN. The absence is **declared by the repo's own
contract**: `contracts/market_memory/spy_daily_price_source_observation.v1.schema.json:246-249` pins
`"point_in_time_corporate_actions": {"const": false}` alongside `"total_return": {"const": false}` `[V]`,
with both listed as required limitations at `:232-233` `[V]`.

Searches grounding the absence `[C]`: `grep -rn 'adj_factor' --include='*.py' .` → zero production sites
(only a cross-store ratio derivation at `scripts/reconcile_prophet_live.py:119` and a synthetic test);
`grep -rniE 'split_ratio|split_factor|ex_date|ex_div|dividend_amount|Stock Splits|corporate action'` over
`collectors engine lib scripts` → zero corporate-action hits; yfinance is called with `auto_adjust=True/False`
across 20+ collectors but **never with `actions=True`** and never touching `.splits`/`.dividends`.

Adjustment is therefore consumed as an **opaque, un-versioned vendor side-effect**. That is the mechanism
behind §1.1.

Four anchor points already exist and should be built on rather than replaced `[C]`:
the `"corporate_action"` family enum value in `contracts/capital_structure_event.schema.json`;
`corporate_action_basis` in `contracts/cn_tushare_minutes_manifest.v1.schema.json`;
`corporate_action_adjusted` in `contracts/market_memory/spy_experience_*.v1.schema.json`; and the one
derivable detector that exists today — `collectors/china_tushare_spine.py:4684` documents `pre_close` as an
**ex-rights adjusted vendor field**, so `pre_close != prior close` IS a CN corporate-action detector. Its
only current consumer uses it for limit-band arithmetic, not adjustment `[C]`.

### 5.3 Sessions, halts, auctions

- **Early closes are modelled four times and three of the four declare the concept out of scope:**
  `lib/nyse_calendar.py:11-14` (*"Early closes (13:00 ET) are NOT modeled"*),
  `engine/marketing/market_clock.py:77-78`, `engine/live_overlay.py:119,144` (*"ADVISORY hint only — no
  exchange holiday calendar and no half-days"*), versus `engine/session_digest.py:176,199,211` which DOES
  model it but *"never gates, filters or labels"* `[C]`. **No consumer can get an authoritative answer to
  "was 2025-11-28 a half day".**
- **Halts have no store at all.** `ls data | grep -iE 'halt|luld|auction|suspend'` returns only
  `treasury_auctions` (unrelated) `[C]`. Halts are inferred as zero-variance and then **dropped**:
  `engine/theme_crowding.py:47` and `engine/group_flow.py:91` drop *"zero-variance (halted / constant-price)
  members"*; `engine/synthetic_control.py:454` and `engine/bar_derive.py:365` route around them `[C]`. A
  halted name and a genuinely flat name are indistinguishable, and the resolution is silent exclusion —
  **an unmeasured, daily-grain survivorship mechanism inside every cross-sectional statistic the site
  publishes.**
- **Auctions:** only CN and HK have any notion (`collectors/tushare_addons.py:191,914`;
  `scripts/build_basket_pulse.py:166-170` for HKEX pre-open 09:00–09:30 and closing auction ~16:08 HKT) `[C]`.
  For US, nothing in any schema distinguishes a consolidated-tape last print from the official closing
  auction price.
- **27 files hardcode 09:30/16:00-style session literals** independently rather than sourcing
  `lib/*_calendar.py`; most sampled are tz-labelled in comments, so it is a single-source-of-truth gap
  rather than a naive/aware bug today `[C]`. `engine/live_overlay.py:95-104 _REGION_HOURS` is a parallel,
  non-holiday-aware session table sitting beside the canonical calendars `[C]`.
- **Dormant tz landmine:** `engine/bar_derive.py:63-70` documents that calling `derive_daily_close()`
  without an explicit tz on a non-US ticker silently mis-buckets the trading date (a Shanghai 09:30 CST bar
  becomes a Monday NY midnight cross instead of a Tuesday CN trading date) `[C]`. Currently inert — nothing
  in production calls it — but it needs a hard gate, not a docstring, before any intraday-derived bar ships.

### 5.4 Licensing and redistribution — modelled three times, with three key names

| Where | Key shape | Citation |
|---|---|---|
| SEC collectors | `"rights": {"redistribution_class", "attribution_required", "license_note"}` | `collectors/sec_capital_structure_companyfacts.py:5393`, `collectors/sec_capital_structure.py:1474-1476` `[C]` |
| Biocatalyst collectors | `"license_class": "us_government_source_facts"` | `collectors/biocatalyst/clinicaltrials_v2.py:925,980`, `collectors/biocatalyst/drugs_at_fda.py:957` `[C]` |
| CN spine | `AUTHORIZATION_RECORDED_SCOPE = (*AUTHORIZATION_REQUIRED_SCOPE, "redistribution", "public_derivatives")`; 8 call sites classify vendor refusals as `"vendor_unavailable_or_unlicensed"` | `collectors/china_tushare_spine.py:140` and `:2926,2965,2999,3067,3137,3211,3301,3403` `[C]` |

Two key names for one fact, in collectors sitting in the same directory. **A rights query across the estate
cannot be written today**, and the fifth vendor onboarded will pick whichever file it copies from.

**The uncovered surface is the important one: no PRICE and no MACRO store carries any rights field at all.**
`data/yahoo`, `data/stocks`, `data/baskets/ohlcv`, `data/china_stocks_raw`, `data/hk_stocks` are all
yfinance-sourced (unofficial API, personal-use terms) and are republished into a paid product. The only
place that exposure is written down is the untracked prototype registry (§6).

### 5.5 Reproducibility: published artifacts carry a wall clock and no code version

Store manifests carry a store name and a timestamp and nothing else — `data/massive_stock_day/_manifest.json`
has `{store, n_tickers, latest_date, updated_at, coverage{…}, anchor{…}}` and **no git sha, no producer
version, no config hash** `[V]` (read above). `data/index_gex_history/_manifest.json` names
`"engine": "engine.gex_engine.compute_gex"` but carries no version of it `[C]`.

Exactly three subsystems stamp provenance `[C]`: `engine/context_index/ingest.py:159,415-447` (per-document
`git_sha` + `indexed_git_sha`); `engine/capital_structure/share_count_r2_conformance.py:750,766-767` and
`share_count_r2_concurrency.py:1297-1309` (the required GitHub Actions provenance block);
`engine/neuralweb/capability_broker.py:249` (`GITHUB_SHA`).

Consequence, stated plainly: for the other ~329 `data/` stores, **"the number changed" cannot be
distinguished from "the code changed"**. The Prophet lane proves the cost with a measured case — the same
`as_of` board rendered differently by render-host timezone AND silently swapped ranker version
(`us_prophet_v1` → `us_prophet_v2`), flapping board membership 78 ↔ 81 rows on an identical `as_of`
(`scripts/backfill_prophet_outage.py:9-19`) `[C]`. Full git-commit + input-content-hash pinning exists in
exactly 3 receipt files in all of git history, all from one force-majeure backfill, covering ~25–39 of ~162
live plans `[C]`.

The R2 capital-structure lane already proves the house has the right pattern. It stops at one subsystem.

### 5.6 Freshness: five implementations, one registry, 45% coverage, frozen

- **Five independent staleness mechanisms with no shared constant or module** `[C]`: `app/main.py`
  `/api/status` file-mtime `age_min`; `admin/health.py:15 _STALE_HOURS=96.0`;
  `scripts/freshness_sentinel.py` (1,346 lines of per-artifact budgets);
  `lib/project_runtime_state.py:69-79 _CADENCE_SPECS`; `engine/neuralweb/market_packet.py:173 QUOTES_STALE_MIN=45.0`.
- **The registry that does exist covers 45% and is frozen:** `data/run_status.json` tracks 149 of 329
  top-level `data/` dirs, with all `checked_at` values clustered 2026-07-05…07-09 `[C]`. ~19 "additive,
  never fatal" bolt-on collector calls in `scripts/collect.py` bypass the adapter-registry loop that writes
  it (`scripts/collect.py:861-868` for `sec_ftd`), so `sec_ftd`, `redfin_hf`, `baskets`, and `stocks` are
  absent from it entirely `[C]`. **Adding a new collector the way the last ~19 were added silently opts it
  out of freshness tracking.**
- **Page-bake stamps are not producer watermarks.** `scripts/freshness_sentinel.py:39-42` documents the
  2026-08-08 case: `data/us_prophet_rank/candidates/2026-08.parquet` froze at `stamp_date 2026-08-05` while
  `us_stocks.html` kept re-baking daily, so two independent freshness checks stayed green through 0/7
  nightlies `[V]` (docstring read 2026-08-12). Any freshness primitive must anchor on the **deepest
  producer's own watermark**. *Illustrating §0.1 in one store:* `git ls-files data/us_prophet_rank` in the
  CODE worktree returns `README.md` + `candidates/2026-07.parquet` + `candidates/2026-08.parquet`, while
  `ls data/us_prophet_rank` in the DATA checkout returns **No such file or directory** `[V]` — the DATA
  checkout's pinned HEAD predates the store's introduction. **Reading that tree alone would conclude the
  store has never existed.**
- **And staleness is not uniformly a defect:** `sec_ftd`'s 37-day-old mtime is its correct 30-day PIT
  cadence `[C]`; `checkonchain` is a manual archive that will never refresh `[C]`. A "stalest N stores"
  report without per-store expected-cadence metadata is a false-positive generator.

### 5.7 Multi-vendor conflict: no policy exists

There is no cross-store reconciliation job anywhere. The only per-store audits
(`scripts/audit_stocks_freshness.py`, `scripts/check_price_store_freshness.py`) **cannot see a basis
disagreement** `[C]`. The one real resolver is `engine/washout_turn.py`'s ratio-aligned prepend splice
(§1.4), which explicitly refuses to resolve the conflict for signal legs `[C]`.

Referential integrity is likewise three-way and ad hoc: `scripts/fetch_basket_ohlcv.py:167,296`
(*"N basket member(s) have NO price series on any store rung"*), `engine/prophet_stage_fusion.py:25,1280`,
and `collectors/yahoo.py:167-169` (the 70% threshold) each report the same violation class differently `[C]`.
Only two places enforce FK-style integrity in a store: `engine/context_index/schema.py:70 PRAGMA foreign_keys=ON`
and `scripts/check_entity_thesis_registry.py:12,193-199` `[C]`. **And there is a principled
counter-example that any general rule must accommodate:** `collectors/biocatalyst/drugs_at_fda.py:647,661`
turns FKs OFF deliberately — *"source-native orphans are facts to retain"* `[C]`.

### 5.8 Ownership: a real registry exists, and it does not cover market data

`config/sector_intelligence_ownership.yml` — 477 lines, `schema: sector_intelligence_ownership.v1`,
`effective_at: 2026-08-11T06:57:31Z`, policy block `one_writer_required: true`,
`cross_domain_access: versioned_read_adapter_only`, `unresolved_owner_behavior: block_or_degrade`,
`duplicate_writer_behavior: hard_fail`, `user_state_owner: terminal_supabase`,
`authority_owner: neural_web_a5_governor` (lines 6-13) `[C]`. Test-enforced by
`tests/test_sector_intelligence_ownership.py`, and referenced BY SHA from
`config/biocatalyst_closed_beta_source_manifest.yml:17-18` `[C]`.

**Extend this file; do not create a second one** — a duplicate would violate its own
`duplicate_writer_behavior: hard_fail` spirit and the standing cross-repo prohibition on duplicate control
planes. Its scope is sector-intelligence / biocatalyst / corporate-intelligence / capital-structure only:
**no price, macro, options, news, or CN store has a `canonical_owner` row.** That is the actual gap.

### 5.9 Metric duplication — corrected counts, and why "duplicate" is the wrong word for ~23 of them

- `engine/canon.py` **has NO `atr` and NO `realized_vol`.** Its full export list is `net_liquidity_bn`,
  `dollar_liquidity_roc`, `net_liquidity_bn_change`, `load_net_liquidity_components`,
  `credit_impulse_level`, `credit_impulse_accel`, `vix_term`, `vix_term_scalar`,
  `sector_macro_beta_blend`, `rma`, `ema`, `rsi`, `resample_sessions`, `crossover`, `crossunder`,
  `bars_since`, `rsi_macd`, `stoch_rsi_kd`, `confluence_signals` `[C]`. Therefore the 13 `atr` and 10
  `realized_vol` definitions have **no canonical referent to violate — they are canon GAPS, not canon
  violations.**
- Corrected counts `[C]`: **103** files import canon (55 in production trees); **56** production files
  define an `rsi`/`atr`/`realized_vol`-named function; only **6** do both. On an 8-site adjudication,
  **5 of 8 compute a genuinely different quantity** (ConnorsRSI is a composite; `atr_proxy` is a
  deliberately close-only proxy; `_atr_word` maps an ATR to a natural-language word). Do not call a
  legitimate difference a violation.
- Where the divergence IS real, it is severe: `realized_vol` producers differ by up to ~1,587× because
  three axes stack — annualization (×√252 or not), units (fraction vs ×100), and return type (simple vs
  log) `[C]`. `percentile_rank` has four incompatible tie conventions that answer 0 vs 50 vs 100 on a
  frozen/tied input `[C]`. `credit_impulse` has a THIRD live formula (12-month YoY) in three modules that
  canon's own docstring does not mention `[C]`.
- **A canon entry is not a fix until consumption is verified.** `engine/canon.py:228-236` marks
  `sector_macro_beta` a SHADOW artifact explicitly NOT consumed; the physically-impossible `XLC: 1.0` prior
  it was built to retire is still live at `config.yml:2994`, still read by `engine/conditions.py:1199-1211`,
  still feeding the user-facing heat penalty at `engine/playbook.py:666` `[C]`.

### 5.10 Null / zero — target the idiom, not the class

**Do not write a rule against `fillna(0)`.** On a 15-site adjudicated sample only ~13% are genuine
null-as-zero defects; 53% are semantically correct zeros (a count, a day-0 return, an explicit
"too thin → neutral" assignment); 20% are arithmetically inert because they sit one line above an
availability-weighted denominator; one was a `fillna(0.5)` false positive `[C]`. The raw counts are also
regex-dependent and should not be quoted as facts `[C]`.

**Two high-yield targets with mechanical detectors:**

1. `(1 + <returns>.fillna(0)).cumprod()` — **22 sites, only 2 with an aliveness guard**
   (`engine/indicators.py:55` uses `.where(closes[cols].notna().any(axis=1))`;
   `engine/oracle/timemachine.py:247` uses `.where(alive)`). The other 20 compound a halted / suspended /
   not-yet-listed / delisted session as a flat day, so the index continues through a period where the
   constituent did not trade — `engine/baskets_intl.py:100`, `engine/china_narrative_tags.py:181`,
   `engine/commodity_index.py:182`, `engine/china_sector_index.py:98,215`,
   `engine/momentum_crash_gate.py:108`, `scripts/build_intl.py:675`, `scripts/oracle_nightly.py:763`,
   `scripts/oracle_screen.py:139`, `scripts/oracle_reversion_screen.py:323,668`, +8 more `[C]`.
2. **The volume cluster** — `engine/stock_technicals.py:345,258`, `engine/volume_signature.py:89`,
   `engine/leader_lifecycle.py:547`, `engine/basket_tape.py:184` `[C]`. A missing-volume session becomes a
   zero-volume session, which is a **different market state** (no trades vs no data), and it flows straight
   into OBV/CMF/accumulation reads. Compounded by the int64/float64 split in §2.1: a missing bar cannot even
   be represented as null in `data/yahoo`.

---

## 6 · WHAT THIS CATALOG DOES NOT ESTABLISH

Honest limits. Each of these is a real open question, not a rhetorical one.

1. **Whether any store is genuinely stale in production.** Every tip date here is "last index value in the
   parquet in the DATA checkout on 2026-08-12". That checkout's git state is broken (§0.1), and the
   self-hosted runner may write to a different live tree `[C]`. **Corroborate against the runner before
   calling anything stale.**
2. **The Polygon `adjusted=true` split-only semantics** (§2.1, §2.8.1) are a vendor-doc fact asserted
   nowhere in either repo. The whole Terminal chart-drift finding rests on it. Pin it with a probe receipt.
3. **The HON spinoff mechanism** — direction and magnitude are consistent with a spinoff, but with no
   corporate-action store there is nothing in-repo to check the ex-date and factor against (§1.1, §5.2).
4. **A partial Data OS implementation sits UNTRACKED in the CODE worktree** — `lib/dataos/` (6 modules),
   `config/dataset_registry.yml` (310 lines), and 5 test files, all `??` in `git status --porcelain`, all
   written 2026-08-12 13:43–13:50, imported by nothing `[C]`. It is one `git clean` from gone and its tests
   have never run in CI. **This catalog deliberately does not cite it as evidence for any claim about what
   exists**, other than to note that the ONLY written record of the yfinance licensing exposure (§5.4) and
   of the `HALTED`/`SUPPRESSED_LICENSE` null vocabulary (§5.3, §5.4) currently lives there. Resolve its
   ownership before treating it as prior art (house law: `git worktree list` before claiming a lane).
5. **Five census dataset rows carry producer/identifier/cadence fields that the lane admits it never
   opened** `[C]`: `data/options_flow`; `data/options_entry`/`data/options_exit`; the Canada/HK fundamentals
   rows; `data/china_stocks_raw`'s producer (recorded as *"china_universe.py OR _stock_ohlc.py"* — an OR is
   not an attribution). Those fields are marked as unconfirmed above and **must enter any registry as
   `PROPOSED`, never as `PRODUCED`.**
6. **Whether `data/thetadata_eod` is materialized anywhere.** It is empty here and its declared ops worktree
   does not exist on this machine `[V]`. 50 modules read it. Someone should find out where the rows are, or
   whether there are any.
7. **Lot size / tick size / board lot for CN and HK** — absent from Macro `[C]`; the bot repo was not
   searched for exchange-microstructure constants, and a trading bot is the likeliest place for them.
8. **Whether the two remaining `data/theme_graph` and CN-spine gates are scheduled.** Neither
   `engine/theme_graph/materialize.py` nor the spine's collection path was traced to a workflow file `[C]`.

---

## 7 · CITATION COUNT

Distinct `path:LINE` citations in this document (sections 0–6): **206**, spanning **147** distinct files.
Distinct files referenced at all, with or without a line anchor: **219**.
Commands with inline output shown: 11 (store parquet counts ×4, `massive_stock_day` manifest read, the HON
five-store read, the 2026-06-29 convergence read, the history-depth read, the `data/stocks` reader grep,
the `thetadata_eod` reader grep, and the store-existence checks).

Counted 2026-08-12 with:
`python3 -c "import re;t=open('research/MASTERMIND_DATA_SOURCE_CATALOG.md').read().split('## 7 ')[0];p=re.compile(r'[A-Za-z0-9_./\-]+\.(?:py|json|yml|yaml|md|sql|ts|tsx):[0-9]+(?:[-,][0-9]+)*');c={m.group(0) for m in p.finditer(t)};print(len(c), len({x.rsplit(':',1)[0] for x in c}))"`
→ `205 147`.
