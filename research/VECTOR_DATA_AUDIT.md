# Bitcoin Vector — Phase 0 Data Audit (all endpoints live-tested 2026-06-12)

Companion to `VECTOR_SKELETON.md`. Maps every skeleton signal to a verified free
data source. Zero-cost constraint holds — no paid tier required.

---

## 1. Verified sources (live-tested today)

| Source | Status | History depth | Limits / notes |
|--------|--------|--------------|----------------|
| **CoinMetrics Community API** (no key) | ✅ | 2010 → today | 6000 req / 20s sliding window per IP — effectively unlimited. Available for BTC @1d: `PriceUSD, CapMrktCurUSD, CapMVRVCur, AdrActCnt, HashRate, SplyCur`. **Blocked** on community: `CapRealUSD, NVTAdj, TxTfrValAdjUSD, FeeTotUSD, VtyDayRet30d, SplyAct1yr`. Derivations: realized cap = mcap ÷ MVRV; **NUPL = 1 − 1/MVRV** (exact identity) |
| **bitcoin-data.com** (BGeometrics, no key) | ✅ | **last 4 years only** (free tier), fresh to T-1 | **10 req/hour, 15 req/day per IP.** 614 endpoints incl. SOPR (+STH/LTH), STH/LTH realized price & MVRV, NUPL, supply-in-profit, exchange/miner flows, **funding-rate ✅ tested**, open-interest-futures, liquidations, **etf-flow-btc ✅ tested**, stablecoin supply/SSR, hash ribbons, reserve risk, RHODL. Params: `day, startday, endday, page, size`; `/{metric}/last` for latest row |
| **checkonchain.com** chart JSON | ✅ | **2011-07 → today** (SOPR verified: 5,460 pts) | One-time backfill source for pre-2022 history of SOPR-class metrics: parse `Plotly.newPlot` JSON from chart HTML (~1.7 MB/page). Archive into `data/archive/` with provenance — same pattern as FRED OAS |
| **alternative.me F&G** | ✅ | 2018-02 → today (3,050 rows, `limit=0`) | Free, keyless, no practical limit |
| **OKX public API** | ✅ | OI daily: works; funding: paging semantics TBD at build time | Free, keyless, works from US. Funding history beyond recent pages unclear — bgeo `/v1/funding-rate` (4y daily) is the calibration source; OKX is the live daily append |
| **Deribit public API** | ✅ | DVOL: ~Mar 2021 → today (2019 query returns empty) | Free, keyless. DVOL = BTC implied-vol index, daily OHLC |
| **Yahoo Finance** (existing collector) | ✅ | BTC-USD 2014-09 →; ETH-USD 2017-11 →; SOL-USD 2020-04 →; ^DJI 1992 →; SI=F 2000 →; BZ=F 2007 → | All six new tickers resolve |
| **CFTC COT** (existing collector) | ✅ | `BITCOIN - CHICAGO MERCANTILE EXCHANGE` in the same Socrata dataset, current to 2026-06-09 | Add prefix `"BITCOIN - C"` to `config.yml` markets (excludes BITCOIN CASH PERP / MICRO BITCOIN) |
| ~~Binance futures~~ | ❌ HTTP 451 | — | US geo-blocked (also blocks GitHub Actions) — do not use |
| ~~Bybit~~ | ❌ HTTP 403 | — | CloudFront geo-block — do not use |

## 2. bgeo daily request budget (12 of 15/day, 3 spare)

One call per metric per day with `?startday=<last stored date>`:

1. `sopr` 2. `sth-sopr` 3. `lth-sopr` 4. `sth-realized-price` 5. `realized-price`
6. `supply-profit` 7. `exchange-netflow-btc` 8. `miner-sell-pressure`
9. `funding-rate` 10. `open-interest-futures` 11. `etf-flow-btc` 12. `ssr`

Skipped as derivable from CoinMetrics (full history, no quota): `nupl`, `mvrv`,
`mvrv-zscore`, `realized-cap`. bgeo's own composites (`onchain-risk-index`,
`sth-risk-index`) — never inputs; optional validation comparisons only.

**Risks & mitigations:**
- Quota is per-IP → GitHub Actions shared runner IPs may collide with other bgeo
  users. Mitigation: (a) register free account → API key (may pin quota to key —
  verify at signup; "Sign up free" exists), (b) collector must treat HTTP 429 as
  soft-fail (adapter pattern already guarantees this), (c) backfill stays in
  archive so a missed day only delays freshness, never destroys history.
- Free tier = 4y rolling window → like FRED OAS: as time passes, old data falls
  out. **Archive everything we pull, forever, in parquet** (repo-is-the-database
  already does this).

## 3. Skeleton section → signal → source mapping

| Skeleton component | Signal(s) | Primary data (verified) |
|---|---|---|
| A/B. Risk Index (0–100, 25 threshold) | composite: MVRV-z (CM, 2010→), supply-in-profit (bgeo + checkonchain backfill), SOPR 7d (bgeo + coc backfill), leverage = funding + OI/mcap (bgeo/OKX), realized-vol percentile (Yahoo OHLCV), DVOL (Deribit), F&G (alt.me) | CM + bgeo + coc + Yahoo + Deribit |
| A/B. Momentum [-1,+1] | EMA-slope ensemble, MACD regime, price vs STH realized price (their 1m/6m cost-basis crossover ≈ `realized-price-sth-30d` vs `realized-price-sth-90d`/155d), RSI regime | Yahoo (2014→) + bgeo STH realized prices |
| A/B. Volatility gauge (Low/Sweet/High) | realized-vol percentile bands + DVOL percentile; upside/downside semivol for the qualifier | Yahoo + Deribit |
| A/B. Flow gauge (Low/Sweet/High) | spot volume z, ETF flows, exchange netflow, stablecoin supply 30d Δ | Yahoo + bgeo |
| A/B. Cycle stage slider (Defensive/Fragile/Recovery/Expansion) | 2-axis state: momentum sign × risk level → continuous knob position | derived |
| A. Environment now + 7d probability | trend classifier + historical base rates P(state in 7d \| state, risk band) — empirical transition matrix, like macro next-regime odds | derived from price history (2014→, ~4,300 days) |
| A. Scenarios (3d) + targets | P(up/down 3d \| regime) base rates; mechanical levels: swing highs/lows, ATR bands, round numbers | derived |
| C/D. Allocation model {0,½,1} × 4 variants | momentum × risk threshold grid per variant; tuned via tune.py-style sweep with whipsaw constraint | derived |
| C. Sharpe/Sortino/MaxDD vs HODL | strategy equity curve math | derived |
| E. Cross-asset map | 3d trend chip + conviction (1–3 dots) per asset: SPY/QQQ/^DJI/DXY; GC=F/SI=F/BZ=F; BTC/ETH/SOL/alts-proxy | Yahoo — macro repo already has SPY, QQQ, DX-Y.NYB, GC=F; add ^DJI, SI=F, BZ=F, ETH-USD, SOL-USD |
| F. Structure Shift [-1,+1] | higher-high/higher-low structure score + breakout/breakdown events + episode day-counts | Yahoo OHLCV |
| G. Flash Crash state machine | return/vol z-score triggers: normal → tail risk event → stabilizing price → normal; Impulse = sign of short-horizon impulse | Yahoo daily + intraday-ish refinement optional |
| H. Alerts | reuse engine/alerts.py + scripts/notify.py | existing |
| Sentiment overlay | F&G (2018→), COT BITCOIN net positioning (CME) | alt.me + existing cot.py |

## 4. Calibration depth (honest accounting)

- **Price/technical signals: 2014→ (~3.5 cycles)** — momentum, structure, vol,
  flash crash, environment probabilities, allocation backtest.
- **MVRV/NUPL (via CM): 2010→** — the deepest pillar of the Risk Index.
- **SOPR-class: 2011→ via checkonchain backfill**, then bgeo daily.
- **Cohort (STH/LTH) metrics: 2022→ only (one cycle)** — display + confirmation
  inputs, NOT calibration anchors.
- **Derivatives (funding 4y, DVOL 2021→, OI 4y): one cycle** — same demotion rule.
- House rule applies: every Risk Index band and momentum trigger gets measured
  forward-return records (split-half). Components that fail → context, not signal.

## 4a. User-recommended source list — reconciliation (tested 2026-06-13)

User supplied a 10-source recommendation list. Verdicts:

| # | Recommendation | Verdict |
|---|---------------|---------|
| 1 | CoinMetrics Community | ✅ Already primary. Tested extras: `TxCnt, TxTfrCnt, IssTotUSD, BlkCnt` OK; `DiffMean, RevUSD, FeeMeanUSD, TxTfrValUSD` BLOCKED on community tier. Miner revenue ≈ IssTotUSD + fees (fees via mempool.space/bgeo); difficulty via mempool.space |
| 2 | Binance Futures REST/WS | ❌ **HTTP 451 US geo-block** (verified) — also blocks GitHub Actions runners. Replaced by OKX (tested ✅) + bgeo funding/OI (4y). Liquidation WebSocket additionally incompatible with our architecture: no 24/7 process on free CI — daily liquidation aggregates via bgeo `btc-liquidations` instead |
| 3 | Bybit V5 | ❌ **HTTP 403 CloudFront geo-block** (verified). Same replacement as #2 |
| 4 | Deribit | ✅ Tested deeper: `get_book_summary_by_currency?kind=option` returns **952 BTC option instruments with per-instrument `open_interest` + `mark_iv`** in one call → total options OI (432,660 BTC today), put/call ratio, expiry term structure, and an IV-skew proxy all derivable. Options panel = Phase-later enhancement; DVOL already in plan |
| 5 | CoinGecko | ✅ NEW — keyless `/global` (BTC dominance + total mcap → the **"Alts" aggregate** for the cross-asset card) and `/coins/bitcoin/market_chart` both work. Keyless ≈ 5–15 req/min: fine for a few calls/day. Optional hardening: free Demo key (30/min, 10k/mo) |
| 6 | mempool.space | ✅ NEW — `fees/recommended` + `mining/hashrate` tested. Use for fee pressure (network-activity input to Flow gauge) + difficulty/hashrate redundancy |
| 7 | alternative.me F&G | ✅ Already verified (2018→) |
| 8 | FRED | ✅ Already in repo via macro collectors (rates, OAS, VIX, WALCL/RRP → net liquidity, payrolls, INDPRO) — Vector reads the shared parquet; **macro net-liquidity becomes a cross-asset context input free of charge** |
| 9 | DefiLlama (optional) | ✅ NEW — `stablecoins.llama.fi/stablecoins` tested (USDT $186.8B circulating). Adopted as the stablecoin-supply primary: keyless, no quota pain → frees one bgeo slot (drop `ssr` from the daily-12, derive SSR = BTC mcap ÷ stablecoin supply) |
| 10 | Bitcoin Core RPC / Esplora (optional) | ⏸ Deferred. Esplora is fine for raw block/tx lookups but deriving realized-cap-class metrics needs a full UTXO index → requires running a node + indexer (not zero-cost on CI). Noted as the long-term independence milestone if bgeo/CM ever rug their free tiers |

**Paid-tier verdict (user asked):** nothing paid is critical. The only watch-item
is bgeo's 15/day per-IP quota under CI shared IPs — if it proves flaky, the
escalation ladder is: free-account API key → reshuffle metrics to CM/DefiLlama/
checkonchain → only then consider bgeo Advanced. Entity-adjusted Glassnode data
has no free equivalent at any tier we can reach; proxies are the accepted cost.

## 4b. Glassnode Studio verdict (researched 2026-06-12)

- **API: unusable free.** Docs state the Glassnode API is "available exclusively
  to Professional subscribers" and is credit-metered (`docs.glassnode.com/basic-api/api`).
  Catalog endpoint 401s without a key. The free Studio web account only renders
  charts in-browser (JS app, not scrapeable server-side). → No glassnode.py collector.
- **Docs are still gold (free):** `docs.glassnode.com/llms.txt` exposes their full
  metric-guide catalog as markdown — canonical definitions for everything we're
  rebuilding (STH/LTH = 155-day lifespan cutoff, MVRV-Z, aSOPR ≥1h filter,
  Reserve Risk, Puell, Binary CDD, Liveliness, SSR). Use as the methodology
  reference when implementing engine metrics.
- **Their "timing long-term opportunities" canon** (dashboard + metric guides):
  MVRV (>3.5 late-bull distribution zone), NUPL (>0.75 euphoria, <0 capitulation),
  realized-price reclaim as despair→recovery marker. All available via our
  verified sources: MVRV/NUPL via CoinMetrics (2010→), realized price via bgeo +
  derivation; cohort variants via bgeo (4y).
- **Coinbase public API ✅ tested** (added for alerts sentinel): keyless spot
  price + OHLC candles; daily history ≥2016, hourly granularity available —
  one-time hourly backfill planned in Phase 1 for flash-crash calibration.

## 5. Deferred to collector build (non-blocking)

- bgeo free-account signup → test whether API key lifts the per-IP quota issue in CI.
- OKX funding-history pagination semantics (only needed if bgeo funding proves gappy).
- checkonchain URL inventory for the 2–3 other backfills (supply-in-profit, NUPL-by-cohort).
- Farside ETF-flow scrape unnecessary — bgeo `etf-flow-btc` covers it (tested: -3,766.6 BTC on 2026-06-10).
