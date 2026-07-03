# China A-share Data Inventory — Phase 1
> Authored 2026-07-03. Repo root: `.claude/worktrees/lucid-knuth-523979`. Every claim is cited to a command run or a file:line read during this session. "Local" means present in the worktree; "Main fallback" means read from `/Users/chriswong/Documents/Cluade/Macro Dashboard/data/` (not applicable here — all data confirmed present locally).

---

## 1. Per-name OHLCV — the critical sub-question answered first

**The OVERHAUL doc (`research/CHINA_STOCKS_OVERHAUL.md:64`) states "A-shares are close-only per stock". This is WRONG as of 2026-07-03.**

Two per-stock OHLCV stores exist in the worktree:

| Store | Path | Cols | Universe | History | Raw/Adj | Consumer |
|---|---|---|---|---|---|---|
| `china_stocks` | `data/china_stocks/<TICKER>.parquet` | `close, high, low, volume, open` | 1,520 files (1,506 in search panel + ~14 others) | 1991-01-02 → 2026-07-02 (000001.SZ: 8,891 rows) | **Adjusted** (yfinance `auto_adjust=True` total-return) | `build_china_library.py` via `_overlay_deep_ohlc`; `china_liquidity.py` reads `close,volume` |
| `china_stocks_raw` | `data/china_stocks_raw/<TICKER>.parquet` | `open, close, high, low, volume` | 1,506 files (exact search panel) | 1991-01-02 → 2026-07-02 | **Raw/nominal** (yfinance `auto_adjust=False`, never re-adjusted) | `china_signals.py` extension_read for raw-close logic; `build_china_library.py:59` tries both groups |

Evidence:
- `python3 -c "import pandas as pd; df = pd.read_parquet('data/china_stocks_raw/002544.SZ.parquet'); print(df.shape, list(df.columns))"` → `(3742, 5) ['open', 'close', 'high', 'low', 'volume']`
- `python3 -c "import pandas as pd; df = pd.read_parquet('data/china_stocks/002544.SZ.parquet'); print(df.shape, list(df.columns))"` → `(3742, 5) ['close', 'high', 'low', 'volume', 'open']`
- Adjusted vs raw comparison (000001.SZ): max close diff = 5.01 (historical splits/dividends), recent rows identical — confirms both planes are current.
- `collectors/china_stock_prices.py:1` docstring: "per-name daily OHLC via yfinance (group=china_stocks)… auto_adjust=True total-return"
- `collectors/china_stock_raw.py:1` docstring: "China A-share per-name RAW (nominal) daily OHLC… auto_adjust=False"
- `collectors/china_stock_raw.py:42-43`: `all_tickers()` reads from `china_search/closes.parquet`; same 1,506-name universe.

**Why the OVERHAUL doc says "close-only":** The engine `china_signals.py:5` says "all CLOSE-ONLY (A-shares carry no per-stock OHLCV in the panel)" — this refers to the OLD `china_search/closes.parquet` WIDE panel (1,224 rows × 1,506 cols, close only), which is the fast lookup for backtests. The OHLCV is in per-ticker parquets, not the panel. The builder uses `_overlay_deep_ohlc` (build_china_library.py:581) to promote to full OHLCV for each name at display time. **Volume and high/low are available per stock since 2011 at minimum (back to 1991 for large caps).**

**Volume availability conclusion:** Dollar-ADV (close × volume), turnover-ratio (5d/60d volume), and OBV/CMF are all computable. `engine/china_liquidity.py` already computes ADV (median close×volume) and turnover_ratio from `china_stocks` OHLCV. Turnover-shape signals are BUILDABLE on the 1,506-name universe back to 2011.

---

## 2. Master Data Inventory Table

### 2A. Per-stock OHLCV & Search Panel

| Store | Path | Fields | Freq | Universe | Max Date | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| A-share search panel (wide close) | `data/china_search/closes.parquet` | wide [date × ticker] adjusted close | daily | 1,506 names | 2026-07-02 | 2026-07-03 04:45 | Yes | No | `build_china_library.py`, `china_reversal`, `china_lowvol`, `china_alpha` |
| A-share members | `data/china_search/members.parquet` | name, name_zh, name_en, sector, mktcap_yi | static | 1,495 names | — | 2026-07-03 04:45 | Yes | No | all builders reading universe |
| A-share dropped names | `data/china_search/dropped.parquet` | ticker, dropped_date | event | 11 entries | 2026-07-02 | 2026-07-03 04:45 | Yes | No | `china_universe.py` |
| A-share coverage | `data/china_search/coverage.parquet` | n_stocks daily count | daily | 14 rows | 2026-07-02 | 2026-07-03 04:45 | Yes | No | run_status |
| Per-stock adj OHLCV | `data/china_stocks/<TICKER>.parquet` | close, high, low, volume, open | daily | 1,520 files | 2026-07-02 | 2026-07-03 04:45 | Yes | No | `china_liquidity`, `build_china_library`, `stock_technicals` |
| Per-stock raw OHLCV | `data/china_stocks_raw/<TICKER>.parquet` | open, close, high, low, volume | daily | 1,506 files | 2026-07-02 | 2026-07-03 04:45 | Yes | No | `china_signals.extension_read`, `china_signals.ashare_tech` |

### 2B. Shenwan Sector Indices

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| Shenwan L1 sector OHLCV | `data/china_sectors/<CODE>.parquet` (31 codes + valuation file) | close, open, high, low, volume, amount | daily | 31 Shenwan L1 sectors | 1999-12-30 → 2026-07-01 | 2026-07-03 04:45 | Yes | No | `china_regime`, sector builders, cycle builders |
| Shenwan sector valuation | `data/china_sectors/valuation.parquet` | {code}_pe_ttm, {code}_pb, {code}_div × 31 sectors | weekly (7 rows) | 31 sectors | 2026-06-26 | 2026-07-03 04:45 | Yes | No | sector_desk |

Collector: `collectors/china_sectors.py` — calls `ak.index_hist_sw(symbol=code, period='day')` and `ak.sw_index_first_info()`.

**Note:** No per-stock Shenwan membership crosswalk is stored as a separate file. The `china_search/members.parquet` carries `sector` (Yahoo Finance GICS-style, not Shenwan codes) for 1,495 names. Shenwan code → label mapping is in `config.yml` under `china.shenwan`.

### 2C. THS Concept Baskets

| Store | Path | Fields | Freq | Universe | Max Date | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| THS basket membership | `data/baskets_china_ths/membership.json` | 237 concept baskets, member lists | per-build | 237 baskets | 2026-07-02 (inferred from mtime) | 2026-07-03 | Yes | No | `build_baskets_china_ths.py` |
| THS concept-English map | `data/baskets_china_ths/concept_en_map.json` | code → EN label | static | 237 concepts | — | 2026-07-03 | Yes | No | render |
| THS basket levels (today only) | `data/basket_levels/china_ths.parquet` | level_tr, level_price, mhash, n_members × 237 | 2 rows (build artifact) | 237 × 4 = 948 cols | 2026-07-03 | 2026-07-03 | Yes | No | `baskets_china.html` |

Collector: `collectors/china_ths_concepts.py` — uses `ak.stock_board_concept_name_ths()` for names; per-concept price via custom THS scrape (py_mini_racer for anti-scrape cookie, same as akshare). **akshare's historical per-concept OHLCV endpoint is noted as "no longer working" in the collector comment** — only membership is reliably fetched.

### 2D. Curated China Baskets (22 themes)

| Store | Path | Fields | Universe | Max Date | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|
| Basket membership | `data/baskets_china/membership.json` | 22 baskets, member lists, benchmark | 22 baskets (cn_semis 22 members, cn_ai_compute 17 … ) | 2026-07-02 | 2026-07-03 | Yes | No | `build_baskets_china.py` |
| Basket OHLCV levels | `data/basket_levels/china.parquet` | level_tr, level_price, mhash, n_members × 22 | 22 baskets, 88 cols | 2026-07-03 | 2026-07-03 | Yes | No | `baskets_china.html` |

### 2E. Limit-Up Pool (ZT pool) — 涨停板

| Store | Path | Fields | Freq | Universe | History in file | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| ZT pool snapshot | `data/china_zt_pool/pool.parquet` | ticker, name, consec_boards, seal_fund_yi, failed_seals, turnover_pct, sector, date, asof | daily snapshot (last 3 days retained) | 385 rows, 3 dates: 2026-06-30 / 07-01 / 07-02 | 2026-06-30 → 2026-07-02 | 2026-07-03 04:45 | Yes | No | `china_extras.zt_pool()`, `china_crowding`, `china_discovery`, `build_china_library.py:617` |
| Limit breadth | `data/china_flows/limit_breadth.parquet` | zt (count), dt (count), zb (breadth ratio), seal_rate | daily | 27 rows | 2026-05-27 → 2026-07-02 | 2026-07-03 04:45 | Yes | No | `build_china_radar.py` (likely) |

Collector: `collectors/china_zt_pool.py` via `ak.stock_zt_pool_em(date=date)`. **Only current-day pool is live; no historical archive beyond 3-day rolling window.** This is a structural limitation: you cannot backtest ZT pool dynamics without rebuilding from daily snapshots.

### 2F. Margin Financing (融资余额)

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| Market-level margin balance | `data/china_margin/balance.parquet` | margin_total, fin_balance, fin_pct_float, net_fin_buy, sec_lending | daily | 1 row/day | 2010-03-31 → 2026-07-01 | 2026-07-03 04:45 | Yes | No | `china_signals.margin_crowding()` |
| Market-level daily trade | `data/china_margin/daily_trade.parquet` | margin_balance, balance_ratio, margin_trade_amt, trade_amt_ratio, guarantee_ratio, liab_investors | daily | 1 row/day | 2014-02-11 → 2026-07-01 | 2026-07-03 04:45 | Yes | No | regime builders |
| Per-name margin (akshare) | `data/china_margin_detail/detail.parquet` | ticker, fin_balance, fin_balance_prior, date, prior_date, asof | drip (last 2 dates only) | 3,471 tickers, 2 dates | 2026-06-30 → 2026-07-01 | 2026-07-03 04:45 | Yes | No | `china_extras.margin_positioning()`, `build_china_library.py:762` |
| Per-name margin (Tushare) | `data/tushare/margin.parquet` | ticker, fin_balance, short_balance, fin_buy, total_balance, fin_pctile, trade_date, asof | daily snapshot | 4,372 tickers, single date: 2026-07-01 | 2026-07-01 | 2026-07-03 04:45 | Yes (Tushare-gated) | No | `china_extras` (GATED) |

Collector: `collectors/china_margin.py` (market-level via akshare `ak.stock_margin_detail_szse`); `collectors/china_margin_detail.py` (per-name akshare drip); `collectors/tushare_margin.py` (Tushare per-name with percentile).

**Note:** Per-name margin detail (`china_margin_detail/detail.parquet`) holds only 2 recent dates — no historical archive. For margin velocity over time, only market-level `balance.parquet` (2010→) has time series. Per-name history is in `tushare/margin.parquet` (single-day snapshot, no history).

### 2G. Dragon-Tiger Board (LHB) — 龙虎榜

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| LHB detail (aggregated) | `data/china_lhb/detail.parquet` | ticker, name, net_buy_yi, n_appearances, inst_net_buy_yi, n_inst_buy, n_inst_sell, reasons, last_date, asof | rolling window | 642 names, last_date range: 2026-06-24 → 2026-07-01 | ~1-week window | 2026-07-03 04:45 | Yes | No | `china_extras.lhb()`, `china_discovery.lhb_inst()`, `flow_velocity.py:355` |
| LHB events (raw) | `data/china_lhb/events.parquet` | ticker, name, net_buy_yi, date, reason | event | 446 events, 4 dates: 2026-06-26 → 2026-07-01 | ~1-week window | 2026-07-03 04:45 | Yes | No | `china_extras.lhb()` |

Collector: `collectors/china_lhb.py` via `ak.stock_lhb_detail_em()` and `ak.stock_lhb_jgmmtj_em()`. The collector comment (line 198) notes ~21k events available from 2024-07 → 2026-06 via range backfill, but the live store holds only a rolling ~1-week window. No deep historical archive is committed.

### 2H. QVIX (Volatility Index)

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| QVIX-300 | `data/china_qvix/qvix300.parquet` | close, open | daily | CSI300 options | 2019-12-23 → 2026-06-26 | 2026-07-03 04:45 | Yes | No | `china_signals.qvix_regime()`, `build_china_library.py:747` |
| QVIX-50 | `data/china_qvix/qvix50.parquet` | close, open | daily | SSE50 options | 2015-02-09 → 2026-06-26 | 2026-07-03 04:45 | Yes | No | same |

Collector: `collectors/china_qvix.py` via `ak.index_option_300etf_qvix` and `ak.index_option_50etf_qvix`. **QVIX is fresh and consumed: `build_china_library.py:747-755` reads `qvix300.parquet["close"]`, computes `qvix_regime()`, and applies as a CN macro risk overlay taxing chases.** QVIX-300 history is shorter (2020 vs 2015 for 50) reflecting CSI300 options launch date.

### 2I. Stock Connect (Northbound / Southbound)

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | R2-gated | Engines |
|---|---|---|---|---|---|---|---|---|---|
| Northbound | `data/china_connect/northbound.parquet` | net, buy, sell, turnover, hold_mktcap | daily | aggregate | 2014-11-17 → 2026-07-02 | 2026-07-03 04:45 | **DEAD (net/buy/sell all null from 2024-08-16 onward)** | No | `flow_velocity.py:129` (reads it; all recent net values NaN) |
| Southbound | `data/china_connect/southbound.parquet` | net, buy, sell, turnover, hold_mktcap | daily | aggregate | 2014-11-17 → 2026-07-02 | 2026-07-03 04:45 | **LIVE** | No | `flow_velocity.py:129` |

Confirmed by inspection: `northbound.parquet`'s last 100 rows all have `net=NaN`. Last non-null `net` date: 2024-08-16. Collector comment (`collectors/china_connect.py:12-13`): "northbound — daily NET disclosure was curtailed by regulators Aug-2024 (recent rows null); historical net (pre-2024-08) + turnover are kept". **Northbound turnover is still live (numerical) but net flow is permanently null — confirmed dead for signal purposes.**

### 2J. Tushare Cross-Sectional Stores (API-gated)

These all require a Tushare API token. The `tushare_client.py` says it no-ops gracefully without the key. Run log (`data/china_tushare/run_log.parquet`) shows last run 2026-07-02 for all legs.

| Store | Path | Fields | Freq | Universe | Max Date | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| Per-name valuation | `data/tushare/valuation.parquet` | ticker, close, pe, pe_ttm, pb, ps_ttm, dv_ttm, **turnover_rate**, total_mv_yi, circ_mv_yi, pe_pctile, pb_pctile | daily snapshot | 5,589 names | 2026-07-01 | 2026-07-03 04:45 | Yes | `build_china_library.py:693` for mktcap; `china_extras` |
| Per-name money flow | `data/tushare/moneyflow.parquet` | ticker, name, close, pct_change, net_amount, net_amount_rate, **main_net**, main_net_rate | daily snapshot | 5,970 names | 2026-07-01 | 2026-07-03 04:45 | Yes | `china_extras.fundflow()`, `flow_velocity.py:201`, `china_radar.py:198` (sector version) |
| Per-name money flow (sector) | `data/tushare/moneyflow_sector.parquet` | sector_code, name, net_amount, net_amount_rate, content_type, rank | daily snapshot | 1,022 rows (sector × type) | 2026-07-01 | 2026-07-03 04:45 | Yes | `china_radar.py:198` |
| Per-name chip distribution | `data/tushare/chips.parquet` | ticker, winner_rate, weight_avg, cost_50pct, cost_5pct, cost_95pct, his_low, his_high | daily snapshot | 5,511 names | 2026-07-01 | 2026-07-03 04:45 | Yes | `china_extras.chips()` |
| Chip/flow history | `data/tushare/chips_hist.parquet` | ticker, date, winner | weekly grid | 1,522 names | 2026-05-26 → 2026-06-26 (~13 months) | 2026-07-03 04:45 | Yes | `tushare_history.py` (validation only) |
| Fund flow history | `data/tushare/flow_hist.parquet` | ticker, date, flow | weekly grid | 1,523 names | 2025-05-26 → 2026-06-26 (~13 months) | 2026-07-03 04:45 | Yes | `tushare_history.py` (validation only) |
| Sell-side forecast | `data/tushare/forecast.parquet` | ticker, type, p_change_min, p_change_max, guidance_score, end_date, ann_date | drip | 3,124 names | ann_date 2026-07-02 | 2026-07-03 04:45 | Yes | `china_extras.forecast_guidance()` |
| Forecast history | `data/tushare/forecast_hist.parquet` | ticker, ann_date, guidance_score | drip | 3,563 names | 2026-07-02 | 2026-07-03 04:45 | Yes | validation |
| Broker gold picks | `data/tushare/broker.parquet` | ticker, name, n_brokers, brokers, month | monthly | 234 picks | asof 2026-07-02 | 2026-07-03 04:45 | Yes | `china_extras.broker_gold()` |
| Research ratings | `data/tushare/report_rc.parquet` | ticker, name, report_date, rating, tp, … (22 cols) | drip | 4,869 reports | 2026-07-01 | 2026-07-03 04:45 | Yes | not yet wired to per-stock JSON |

**Important: `tushare/valuation.parquet` has `turnover_rate` (% float shares traded that day) for 5,589 names.** This is a non-null daily turnover figure for a universe 3.7× broader than the search panel. It confirms turnover data is AVAILABLE, though only for the single most-recent day via this snapshot (no tushare turnover time series in the committed files beyond the weekly chip/flow history grids).

### 2K. Valuation & Fundamentals

| Store | Path | Fields | Freq | Universe | Max Date | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| Market-level PE/PB | `data/china_a_val/pe.parquet` | median_pe_ttm, avg_pe_ttm, close, pe_pctile_10y, pe_pctile_all | daily | aggregate | 2026-07-01 | 2026-07-03 04:45 | Yes | regime |
| Market-level PB | `data/china_a_val/pb.parquet` | median_pb, pb_pctile_10y, pb_pctile_all, close | daily | aggregate | 2026-07-02 | 2026-07-03 04:45 | Yes | regime |
| Per-name valuation percentiles | `data/china_valuation/percentiles.parquet` | ticker, payload (JSON blob), asof | drip (≤60/build) | 1,536 names | 2026-07-02 | 2026-07-03 04:45 | Yes | `china_extras.valuation_percentile()` |
| Per-name fundamentals | `data/china_fundamentals/fundamentals.parquet` | ticker, payload (JSON blob), asof | drip | 801 names | 2026-06-18 | 2026-07-03 04:45 | Yes | `china_extras`, `build_china_library.py:1073` |

Collector: `collectors/china_valuation.py` via `ak.stock_zh_valuation_baidu()` (5y band, per-name, drip). `collectors/china_fundamentals.py` via `ak.stock_financial_abstract()` + `ak.stock_financial_hk_analysis_indicator_em()`.

### 2L. Per-name Comment / Attention (千股千评)

| Store | Path | Fields | Freq | Universe | Max Date | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| Comment snapshot | `data/china_comment/detail.parquet` | ticker, name, attention, inst_participation, main_cost, score, rank, rank_delta, price, asof | daily | 5,185 names | 2026-07-02 | 2026-07-03 04:45 | Yes | `china_extras.comment()`, `china_discovery.attention_rising()` |
| Attention history | `data/china_comment/attention_hist.parquet` | ticker, date, attention | daily | 46,667 rows (~30 names × days ~= 1,500+) | 2026-07-01 | 2026-07-03 04:45 | Yes | `china_extras.comment_velocity()` |

Collector: `collectors/china_comment.py` via `ak.stock_comment_em()`. **Coverage is 5,185 names — 3.5× broader than the 1,506-name OHLCV panel.** The `attention_hist` goes back to 2026-06-18 (14 days), providing short-term velocity only.

### 2M. Pledge / Share Pledge Risk (股权质押)

| Store | Path | Fields | Freq | Universe | Quarter | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| Pledge ratios | `data/china_pledge/pledge.parquet` | ticker, name, pledge_ratio, pledge_mktcap_yi, sector, quarter, asof | quarterly | 2,249 tickers | 2025-12-31 (Q4 2025) | 2026-07-03 04:45 | Yes (data is 1 quarter stale) | `china_extras` (wired but stale) |

Collector: `collectors/china_pledge.py` via `ak.stock_gpzy_pledge_ratio_em()`. One quarter of lag is structural (regulatory reporting cycle). The mtime shows daily collection runs but the Q1 2026 data is not yet published.

### 2N. ETF Flows & AH Premium

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| ETF share count | `data/china_flows/etf_shares.parquet` | 21 ETF tickers as cols (sh_159915, sh_510300, etc.) | daily | 21 sector ETFs | 2026-06-13 → 2026-07-02 (~20 trading days only) | 2026-07-03 04:45 | Yes | `build_china_radar.py` likely |
| AH premium index | `data/china_flows/ah_premium.parquet` | hsahp | daily | 1 series (HSAHPI) | 2026-06-12 → 2026-07-02 (~14 trading days) | 2026-07-03 04:45 | Yes | regime |

**ETF flows store has only ~20 trading days of history — insufficient for multi-week trend signals.** This is a known shallow store (collector appears to not backfill).

### 2O. Analyst Forecasts & Buyback

| Store | Path | Fields | Freq | Universe | Max Date | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| Analyst forecast | `data/china_analyst/forecast.parquet` | ticker, name, payload (JSON blob), asof | drip | 2,353 tickers | 2026-07-02 | 2026-07-03 04:45 | Yes | `china_extras.analyst_consensus()` |
| Buyback | `data/china_buyback/buyback.parquet` | ticker, name, plan_amt_yi, done_amt_yi, pct_shares, progress, asof | daily | 2,855 tickers | 2026-07-02 | 2026-07-03 04:45 | Yes | `china_discovery.buyback()` |
| Block trades | `data/china_block_trades/detail.parquet` | ticker, name, avg_premium_pct, block_amt_yi, n_blocks, last_date, asof | rolling | 525 names | 2026-07-01 | 2026-07-03 04:45 | Yes | `china_extras.block_trades()` |

### 2P. Breadth

| Store | Path | Fields | Freq | Universe | History | mtime | Alive | Engines |
|---|---|---|---|---|---|---|---|---|
| China large-cap breadth | `data/china_breadth/breadth.parquet` | n_members, pct_above_50, pct_above_200, nh, nl, adv, dec, ad_line | daily | 82 curated large-caps | 1991-03-12 → 2026-07-02 | 2026-07-03 04:45 | Yes | `china_radar`, regime engines |
| Breadth constituents | `data/china_breadth/constituents.parquet` | name, sector | static | 82 names, 15 sectors | — | 2026-07-03 04:45 | Yes | renderer |

**Important limitation:** This is NOT full-market breadth (3,000+ names). It is a 82-name hand-curated large-cap sample matching CSI300-style names. Daily per-sector breadth from the full 1,506-name panel is NOT stored anywhere — it would need to be computed on-the-fly from `china_stocks` + `china_search/members.parquet`.

### 2Q. Other Relevant Stores

| Store | Path | Fields | Max Date | Alive | Engines |
|---|---|---|---|---|---|
| QVIX regime | see 2H above | | | | |
| China breadth + name score | `data/china_name_score/calls.parquet` | date, ticker, score, tier, fuel, trigger, level | 2026-07-02 | Yes | `build_china_library.py` |
| Sector central calls | `data/china_sector_central/calls.parquet` | date, id, kind, shenwan_code, basket_id, name, score, label, dir, confluence, fwd_cond_rate, fwd_lift, gate_factor, level | 2026-07-02 | Yes | `sector_central_china.html` |
| Standout board track | `data/china_standout_track/board.parquet` | date, ticker, board_rank, tier, setup, extended, washout, level, coiled, coiled_star, … | 2026-07-02 | Yes | forward-grading |
| China regime | `data/china_regime/latest.json` + `regime_history.parquet` | liquidity_overlay, regime fields | 2026-07-02 | Yes | all China builders |
| Macro series | `data/china_macro/{pmi,cpi,ppi,m2,indpro,…}.parquet` | monthly | 2026-06-30 | Yes | regime |

---

## 3. Collectors Summary — Akshare vs Tushare Wiring

### Akshare-wired collectors (keyless, no API token needed):
| Collector | Akshare Endpoint | Output |
|---|---|---|
| `china_qvix.py` | `ak.index_option_300etf_qvix`, `ak.index_option_50etf_qvix` | `china_qvix/qvix*.parquet` |
| `china_fundamentals.py` | `ak.stock_financial_abstract()` | `china_fundamentals/fundamentals.parquet` |
| `china_ths_concepts.py` | `ak.stock_board_concept_name_ths()` + custom THS scrape | `baskets_china_ths/membership.json` |
| `china_comment.py` | `ak.stock_comment_em()` | `china_comment/detail.parquet` |
| `china_lhb.py` | `ak.stock_lhb_detail_em()`, `ak.stock_lhb_jgmmtj_em()` | `china_lhb/{detail,events}.parquet` |
| `china_zt_pool.py` | `ak.stock_zt_pool_em(date=)` | `china_zt_pool/pool.parquet` |
| `china_sectors.py` | `ak.index_hist_sw()`, `ak.sw_index_first_info()` | `china_sectors/*.parquet` |
| `china_pledge.py` | `ak.stock_gpzy_pledge_ratio_em()` | `china_pledge/pledge.parquet` |
| `china_valuation.py` | `ak.stock_zh_valuation_baidu()` | `china_valuation/percentiles.parquet` |
| `china_buyback.py` | `ak.stock_repurchase_em()` | `china_buyback/buyback.parquet` |
| `china_breadth.py` | via yfinance (not akshare directly) | `china_breadth/breadth.parquet` |
| `china_a_valuation.py` | `ak.stock_a_all_pb()`, `ak.stock_a_ttm_lyr()` | `china_a_val/*.parquet` |
| `hk_valuation.py` | `ak.stock_hk_valuation_baidu()` | `hk_valuation/*.parquet` |

### Tushare-wired collectors (API-gated):
| Collector | Output | Notes |
|---|---|---|
| `tushare_valuation.py` | `tushare/valuation.parquet` | includes `turnover_rate` |
| `tushare_moneyflow.py` | `tushare/moneyflow.parquet`, `tushare/moneyflow_sector.parquet` | main-force (超大+大单) net |
| `tushare_margin.py` | `tushare/margin.parquet` | per-name with percentile |
| `tushare_chips.py` | `tushare/chips.parquet` | winner_rate, cost basis |
| `tushare_history.py` | `tushare/chips_hist.parquet`, `tushare/flow_hist.parquet` | 13-month weekly grid |
| `tushare_broker.py` | `tushare/broker.parquet` | monthly broker gold picks |
| `tushare_forecast.py` | `tushare/forecast.parquet`, `tushare/forecast_hist.parquet` | earnings guidance |

### Plausible akshare endpoints NOT yet wired:
Based on `ak.*` namespace (akshare ~1.18): `ak.stock_dzjy_mrtj` (block trades — alternate to current collector), `ak.stock_zh_a_gdhs_detail_em` (shareholder count changes, unwired), `ak.index_stock_cons` (index constituent list — could build Shenwan membership crosswalk), daily per-sector SSE/SZSE volume/turnover aggregates (not currently wired). No tushare history endpoint for turnover-rate time series is wired.

---

## 4. Buildable-Signals Appendix

| Signal class | Data present? | Fresh? | History depth | Gap / blocker |
|---|---|---|---|---|
| **Limit-up pool dynamics** (ZT pool: consec boards, seal rate, sector breadth by zt count) | YES — `china_zt_pool/pool.parquet` + `china_flows/limit_breadth.parquet` | YES (2026-07-02) | 3-day rolling window for pool; 27 days for limit_breadth | **No historical archive for backtesting.** Can compute sector-level zt breadth from daily snapshots going forward only. |
| **Margin velocity** (market-level: expansion rate, absolute level) | YES — `china_margin/balance.parquet` (2010→2026-07-01) | YES | 16 years daily | Per-name margin velocity needs time series; only 2-day akshare snapshot exists. Tushare daily history would need tushare_history extension. |
| **Turnover shape** (5d/60d turnover ratio per name) | YES — computed in `engine/china_liquidity.py` from `china_stocks/*.parquet` | YES (2026-07-02) | 2011→2026 for most names (full history for 000001 = 1991) | Already wired and consumed in `build_china_library.py:927` as `turn_ratio`. Also `tushare/valuation.turnover_rate` for 5,589 names (single day). Fully BUILDABLE. |
| **LHB smart-money** (institutional net buying on dragon-tiger board) | YES — `china_lhb/detail.parquet` + `events.parquet` | YES (last_date up to 2026-07-01) | ~1-week rolling window | **No historical archive.** Backfill to 2024-07 is documented as possible via `ak.stock_lhb_jgmmtj_em` range call but not committed. Signal is computed per-build only, not backtestable without archiving. |
| **Daily per-sector breadth** (% names above MA, adv/dec by Shenwan sector) | PARTIALLY — `china_breadth` covers 82 large-caps; full-panel breadth NOT stored | YES (82-name) | 1991→2026 (82-name); none for full 1,506 | Full-market daily sector breadth is **BUILDABLE** from `china_stocks` + `china_search/members.parquet` (sectors present). Needs a new engine function / collector to compute and store daily. |
| **THS concept indices daily** | LIMITED — basket_levels/china_ths.parquet holds only current day (2 rows); no daily history | build artifact only | 2026-07-02 to 2026-07-03 | **Deep daily THS index history is NOT stored.** akshare's per-concept OHLCV endpoint is noted as non-functional in the collector. What exists: membership + today's EW level only. |
| **QVIX** | YES — `china_qvix/qvix300.parquet` (2020→) + `qvix50.parquet` (2015→) | YES (2026-06-26, 5 trading days behind — QVIX site lag) | 6 years / 11 years | Already consumed by `china_signals.qvix_regime()`. Mild freshness lag (5 days) due to upstream optbbs.com update cadence. |
| **ETF flows** (share-count proxy for money in/out of sector ETFs) | YES but shallow — `china_flows/etf_shares.parquet` 21 ETFs | YES (2026-07-02) | **Only 20 trading days (since 2026-06-13)** | History is too shallow for any signal calibration. Would need full backfill (ETF inception dates ~2019) to be useful. |
| **Southbound flows** (HK→mainland) | YES — `china_connect/southbound.parquet` | YES (2026-07-02) | 2014-11-17 → 2026-07-02 | LIVE and consumed by `flow_velocity.py`. Good history. |
| **Northbound flows** (foreign → A-shares) | DEAD for net/buy/sell — `china_connect/northbound.parquet` | Turnover live; net DEAD since 2024-08-16 | 2014→2024-08 (net); 2014→2026-07-02 (turnover) | Northbound net permanently null by regulatory decree. Turnover only survives. Cannot reconstruct foreign-buying signal. |

---

## 5. Key Structural Notes

1. **Tushare dependency:** Six key cross-sectional stores (moneyflow, chips, margin-with-percentile, broker-picks, forecast, history grids) require a Tushare API token. The client gracefully no-ops without it but all `china_extras.fundflow()`, `chips()`, `broker_gold()`, and `forecast_guidance()` return empty. These are in use in the main builder at `build_china_library.py:643`.

2. **Two-plane price architecture:** `china_stocks` (adjusted, used for signals) and `china_stocks_raw` (raw, used for AH premium comparison and reference prices). The adjusted close is the source for all technical signals. Volume is IDENTICAL in both planes (volume does not adjust for splits/dividends).

3. **The "close-only" label in code comments is misleading:** `china_signals.py` and `CHINA_STOCKS_OVERHAUL.md` say "close-only" but the code already reads OHLCV via `china_liquidity.py` (volume, close) and `build_china_library.py:581` (`_overlay_deep_ohlc` promoting to high+close). The per-stock parquets have full OHLCV. The "close-only" label refers to the `china_search/closes.parquet` WIDE panel used for fast batch backtests — not to the individual per-ticker stores.

4. **No Shenwan per-stock membership crosswalk file:** There is no `china_sectors/<code>_members.parquet` or similar. The search panel `members.parquet` has GICS-style `sector` (11 categories), not Shenwan codes. Per-stock Shenwan classification would require calling `ak.index_stock_cons()` per sector code — this endpoint is wired in config references but no membership table is committed.

5. **ZT pool and LHB are rolling-window only:** Neither store has a committed historical archive. Both are used as current-state signals (is this name on the board today?), not as backtestable time series.
