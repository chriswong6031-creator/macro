Now I have everything needed. Let me compile the final report.

## Findings: Ticker-universe & popularity data available for scaling marketing to many more US tickers

**1. UNIVERSE — existing ticker-universe registries**

- `data/universe/membership.parquet` (`engine/universe_history.py:33-34`) — point-in-time index-membership ledger for S&P 500 / S&P 400 / S&P 600 / Russell 2000 (`GROUPS` at `engine/universe_history.py:32`). Measured: 2,841 unique active tickers (503 SP500 + 400 SP400 + 603 SP600 + 1,954 R2000, with overlap). Refreshed every `collect.py` run (`scripts/collect.py:722-723`).
- `data/symbol_directory/` (`collectors/symbol_directory.py:1-33`) — **whole-exchange** listed-symbol directory from Nasdaq Trader + SEC, keyless, refreshed daily. Manifest: 13,081 symbols, ~7,099 estimated common stocks, 5,563 ETFs, 386 preferreds (`data/symbol_directory/manifest.json`). Explicitly "no consumers yet" (`collectors/symbol_directory.py:5`) — cheapest full-universe reference to build from.
- Finviz screener universes: Nasdaq-100 = 103 names, Russell 2000 = 1,954 names, with sector/industry tags (`data/finviz_screener/idx_ndx.json`, `idx_rut.json`; builder `scripts/fetch_finviz_screener.py:1-16`).
- Narrative baskets: `data/baskets/membership.json` — 47 baskets, 691 unique active single-name US tickers (`collectors/universe.py:17-31`); this is the "alt-data watchlist" several per-ticker collectors key off of.
- Options universe: `engine/options_universe.gex_symbols()` (`engine/options_universe.py:53-79`) = 25 index/sector-ETF anchors ∪ basket members, capped `max_underlyings: 375` (`config.yml:583`, `include_baskets: true` at `config.yml:582`).
- The "34-symbol VPS live plane" is **not an equity universe** — `DISPLAY_SYMBOLS`/`CORE_SYMBOLS` in `scripts/build_live_quotes.py:60-110` are index/futures/FX/commodity/crypto tiles only ("kept tiny (~34 symbols…)" comment at `scripts/build_live_quotes.py:98-99`); confirmed in `tests/test_prophet_live_vps_lane.py:229-232`, which also documents the real per-name plane: `quotes_full.json` carries ~2,100 symbols vs. ~1,700 "armed" (scored) names.
- The prophet-live scored universe is `scripts.build_stock_library.universe()` (`scripts/build_stock_library.py:438-476`), unioning `data/stocks` (232 deep-history holdings names) + S&P 500/400/600 breadth caches + Russell 2000 cache — measured 1,742 names (`engine/prophet_live/armed_pack.py:32`).
- S&P/Nasdaq-100/Russell membership changes also tracked separately under `data/sp_index_changes/` and `data/index_reconstitution/` (not inspected in depth; directories exist).

**2. OHLCV COVERAGE — three usable stores, very different breadth**

- **`data/massive_stock_day/`** (`collectors/massive_stock_day.py:1-115`) — whole-market daily OHLCV from Massive/Polygon flat files, **20,677 tickers**, rolling 5-year window (first day 2021-07-06) (`data/massive_stock_day/_manifest.json`). Schema: open/high/low/close/volume/transactions (`collectors/massive_stock_day.py:80-84`). ~617MB / ~20k parquets, canonical home is Cloudflare R2 (`collectors/massive_stock_day.py:12-13`); **not split-adjusted** (`engine/marketing/hot_tape_pack.py:31-34`).
- **`data/baskets/ohlcv/`** (`scripts/fetch_basket_ohlcv.py:1-30`) — deep, **split-adjusted (yfinance auto-adjusted)** OHLCV for baskets ∪ Nasdaq-100 ∪ Russell 2000 (nightly call chain `scripts/collect.py:766-775`). Measured: 2,768 tickers, e.g. NVDA has 3,163 rows back to 2014-01-02. Keyless, free, additive/non-fatal merge.
- **`data/stocks/`** (`collectors/sector_holdings.py:1-11`) — top-20 holdings per sector SPDR, ~235 tickers, full history since 1980 (AAPL: 11,500 rows back to 1980-12-12), Yahoo-sourced.
- `engine/marketing/hot_tape_pack.py:12-19` already **unions all three stores** (freshest-bar-wins per ticker), applies `min_adv_dollars=$25M` / `max_tickers=3000` filter (`engine/marketing/hot_tape.py:141-149`), and ships a nightly JSON pack (`data/marketing/hot_tape_pack.json`) — measured **1,315 tickers**, each carrying `adv20_dollars`, `adv_rank` (dollar-volume rank), `mcap_usd`, sector, RSI, 52w/ATH stats, streaks, and **`earn_next_date`/`earn_next_time`**.
- **Bottom line for "fetch 2-5y of daily bars for an arbitrary liquid US ticker":** already solved for basket/NDX100/Russell2000 names (`data/baskets/ohlcv`, split-adjusted, 12y+ deep) and for anything else covered by `data/massive_stock_day` (5y, whole market, needs split-adjustment care). Extending to the full `data/symbol_directory` list (~7,099 common stocks) is a straightforward incremental yfinance/massive pull, not new infrastructure.

**3. OPTIONS VOLUME — ingested, but capped to ~375-390 underlyings**

- `data/thetadata_eod/` (per-contract EOD chains + OI + Greeks) — 380 roots × 2012–2026, ~60GB, ~13k parquets, hosted on an ops Mac / synced nightly to R2 (`ops/THETADATA_R2_SYNC_RUNBOOK.md:3-5, 34-38`); universe = `engine.options_universe.gex_symbols()` ∪ ETF anchors ∪ `SPX/SPXW` (`scripts/backfill_thetadata_eod.py:29-32, 205-210`).
- `data/options_flow/summary_<TICKER>.parquet` (`engine/options_flow.py:1-30`) — per-ticker daily aggregate: `volume` (total contract volume), `premium_mn`, `net_premium_mn`, `pc_ratio`, `gamma_flow_bn`, `fresh_contracts`, `net_doi`. Measured: **383 tickers**. This is the closest thing to an "options volume by ticker" table and could directly drive a most-active-by-options-volume ranking, but only within the ~375-390-name gex/options universe.
- `data/polygon_gex/summary_<TICKER>.parquet` — per-strike GEX chain snapshots, 404 tickers (same universe family).
- `engine/flow_leaders.py` (Flow Leaders Desk, `engine/flow_leaders.py:1-16`) ranks by net-impact z-score (not raw volume), top 20 slots, over the same ~370-underlying universe (`scripts/build_flow_leaders.py:190`).
- "Quanted" (`research/quanted_options/`) is vendor-evaluation research only — no python collector, not integrated.
- No aggregate options-volume ranking exists for tickers **outside** the ~375-390 gex/options universe; raising `max_underlyings` in `config.yml:583` (or dropping `include_baskets` cap) is the direct lever to widen this, at additional Massive REST-call and ThetaData-backfill cost.

**4. TRADED VOLUME / MOVERS**

- `engine/marketing/movers_source.py:1-14` reads `site/marketdata/sp500_heatmap.json` (503 S&P 500 names, daily OHLC-derived %moves, multiple timeframes) and `site/marketdata/themes_heatmap.json` (268 theme tiles / 941 unique member tickers) — this is the current feed for `mover`/`theme_list` marketing posts, capped at S&P 500 + theme membership.
- `scripts/hot_tape_radar.py` / `engine/marketing/hot_tape.py` — the */5-minute intraday radar — is the **broadest** existing movers infra: universe filter `min_adv_dollars=$25,000,000`, `max_tickers=3000` (`engine/marketing/hot_tape.py:141-148`), sourced from the union of the three OHLCV stores above via `hot_tape_pack.py`. Shipped pack currently carries 1,315 ADV-ranked tickers with `adv_rank`/`adv20_dollars` fields ready to use as a "top traded volume" list.
- No dedicated `movers_source`-style feed currently reads the hot-tape pack for the *evergreen* mover/theme post types — that's a gap/opportunity: the ADV-ranked, 1,300+-name pack already exists but `movers_source.py` only consumes the 503-name S&P heatmap.

**5. RETAIL SEARCH/ATTENTION — exists, but thin and NOT used by marketing**

- `data/quiver/wallstreetbets.parquet` (`collectors/quiver.py:219-222`) — r/wallstreetbets mention count + sentiment per ticker/day, **whole-market-agnostic (not capped to a fixed watchlist)**, measured 307 unique tickers on the latest day (top: SMCI 373, SPY 249, NVDA 207, HIMS 117…). Already wired into stock-page display via `engine/altdata.py:1033-1035` (`wsb_top`) and `engine/altdata_models.py:379` (`retail_attention`), and into `engine/radar_plus.py:140-148` (crowd-penalty), but **not consumed anywhere in `engine/marketing/`** (verified via grep — zero hits in movers_source.py, hot_tape*.py, build_movers_page.py).
- `data/stocktwits/sentiment.parquet` (`collectors/stocktwits.py:1-24`) — messages/bull-bear ratio/`watchlist_count` (follower count), but capped to `TOP_N=150`/day rotating over the ~691-name basket universe (`collectors/stocktwits.py:47`, `collectors/universe.py`); 678 unique tickers seen historically.
- `data/attention/*.parquet` — Wikipedia pageviews attention (`collectors/wiki_pageviews.py:1-11`), shipped as `site/factordata/attention.json` — **1,221 tickers** with a z-score, "fade-risk caution" framing, S&P1500-ish universe (via `profiles.parquet` wiki-title resolution, 1,222 of 1,540 resolved).
- `collectors/google_trends.py:1-24` — search interest, but hand-curated to just **45 consumer-brand tickers** (`config/narrative_sources.yml:148-188`), 20/night rotation.
- `collectors/quiver.py:225-233` `TwitterAdapter` is **tombstoned** — Twitter/X API discontinued 2023, dead feed. No live X/cashtag-mention ingestion exists (the "x_intel" module found is for our own outbound marketing-post analytics, not inbound retail chatter).
- **Net**: real retail-attention signals exist (WSB mentions ~307 names/day being the broadest and least capped; Wikipedia attention ~1,221 names) but none currently feed marketing's ticker-selection/prioritization logic.

**6. EARNINGS CALENDAR**

- `data/earnings/earnings.parquet` (`collectors/equity_earnings.py:1-27`) — per-ticker `next_date`, `next_time`, `eps_forecast`, surprise history, keyed by ticker index. Sourced from Nasdaq's public (unofficial) calendar API, sweeping the union of S&P500+400+600 breadth (`_universe()` at `collectors/equity_earnings.py:101-108`). Measured 1,364 rows populated of a ~1,506-name target universe (`collectors/equity_earnings.py:53-54`). This is also re-surfaced per-ticker inside `data/marketing/hot_tape_pack.json` (`earn_next_date`/`earn_next_time` fields, sourced `earnings_asof` stamp).
- Coverage does **not** extend to Russell 2000 or the wider massive_stock_day universe — widening the earnings sweep to those names is a config change to `_universe()`, not new infra (same free Nasdaq endpoint).
