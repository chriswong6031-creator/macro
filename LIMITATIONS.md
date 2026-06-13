# Known limitations — honest and maintained

Update this file whenever a weakness is discovered or fixed. Every item lists
the consequence, not just the cause.

## Crypto data sources (Bitcoin Vector)

- **bitcoin-data.com (BGeometrics) free tier: 10 req/hour, 15/day PER IP, and
  only the last ~4 years of history.** Consequence: on shared GitHub Actions
  runner IPs, strangers' usage can eat our quota — metrics skipped that day
  self-heal on the next run (each call covers the full gap since last stored
  date). Every row ever pulled is archived forever (append-only parquet), so
  the rolling window never erases our history. `exchange-netflow-btc` is
  403-gated on the free tier (verified 2026-06-13) and excluded.
- **Cohort/on-chain metrics have unequal depth**: SOPR 2011→ (checkonchain
  one-time backfill, spliced; `data/archive/checkonchain/` holds provenance),
  STH/LTH cohort series 2022→ only, bgeo funding 2023-07→, DVOL 2021→, ETF
  flows 2024→. Consequence: deep calibration leans on price (2014→ Yahoo,
  2015→ Coinbase) and CoinMetrics MVRV-family (2010→); one-cycle metrics are
  confirmation inputs, not calibration anchors.
- **checkonchain backfills parse embedded Plotly JSON from chart pages** — a
  scrape, not an API. It is used once per series (then bgeo maintains it), but
  re-runs may break silently if the site redesigns. Provenance JSON records
  pull date and point count.
- **OKX funding history only pages back ~3 months** (observed at build);
  deep funding history comes from bgeo. Binance (HTTP 451) and Bybit (HTTP 403)
  are US geo-blocked — also from CI — and must not be used.
- **CoinGecko keyless /global has no history** — dominance history comes from
  bgeo `bitcoin-dominance` (4y window); the CoinGecko snapshot keeps it alive
  going forward. A gap between bgeo's window edge and snapshot start is
  possible if the bgeo backfill is ever lost.
- **Deribit options summary is a daily snapshot, not history** — put/call and
  IV aggregates accumulate only from 2026-06-13 onward. DVOL has true history.
- **Entity-adjusted metrics (exchange/whale clustering) have no free source.**
  Our UTXO-based proxies will sometimes disagree with Glassnode/Swissblock's
  entity-adjusted versions; signal-matching targets account for this.

## Data sources

- **Everything Yahoo (yfinance) is an unofficial API.** It breaks several
  times a year. All Yahoo access goes through one adapter so a replacement
  (Stooq, Tiingo free tier) is a single-module swap. Consequence of breakage:
  sector RS, factor ratios, VIX term structure and futures inputs go stale and
  the affected axis confidence degrades; the run does not crash.
- **FRED OAS series are a rolling 3-year window since April 2026** (confirmed
  live during the build). Mitigated by an append-only cache plus archived
  1996–2025 history from Wayback captures of FRED's own endpoints
  (`data/archive/PROVENANCE.md`). Residual risk: if a value was *revised* by
  ICE after our capture date, we keep the older vintage.
- **FRED's keyless fredgraph.csv endpoint 504s for extended windows**
  (observed: a full hour during the build). With `FRED_API_KEY` set the
  official API is used instead — set the key in GitHub secrets; the keyless
  path is a degraded fallback, and `scripts/fred_wayback_fallback.py` is the
  fallback's fallback (history only, up to a few days stale).
- **Rate-cut pricing is a proxy, LOW CONFIDENCE.** CME FedWatch has no free
  API. We use ZQ front-month futures via Yahoo where quotable, plus
  (2Y yield − fed funds) as an expectations spread. Directionally useful,
  not meeting-by-meeting precise. Paid fix: CME market data (~$.
  Would give true meeting-dated probabilities).
- **Breadth uses *current* S&P 500 constituents** (Wikipedia scrape).
  Live signal: fine. Backtest: survivorship-biased — dropped members
  (Lehman, etc.) are invisible, so historical breadth is flattered in
  drawdowns. The validation report's breadth-dependent components carry this
  bias; treat pre-2015 breadth readings as approximate.
- **A-D line is approximated** from constituent daily up/down counts of the
  current membership, not true NYSE breadth.
- **COT data lags 3 days** (released Friday for Tuesday positioning) and the
  legacy report's spec categories are blunt instruments.
- **AAII is currently 403-blocked for non-browser clients** (verified at
  build time) — the adapter exists but the source is dead until a licit access
  path appears; the weekly report runs without it. NAAIM works (full
  since-inception history from their published workbook) but is a small-sample
  survey of active managers, and the workbook link is rediscovered from the
  page each week — a rename breaks it loudly, not silently.
- **Put/call ratios are computed proxies, not the official CBOE series.** The
  official market-statistics CSVs moved behind an SPA (verified at build
  time); we compute index P/C from the SPX delayed chain and an equity proxy
  from SPY+QQQ+IWM chains. Levels differ from the discontinued official
  series; use them as their own time series, not against historical
  official-ratio thresholds.
- **Sector-flow shares-outstanding history starts at deployment.** SO is exact
  (AUM/NAV from SSGA's same-dated fund data) but there is no free history, so
  flow percentiles are meaningless until a few months of daily rows accrue.
- **WGMI holdings URL is not yet configured** — CoinShares' site is an SPA
  with no statically-discoverable holdings file. The coinshares adapter is
  ready; set `holdings.watchlist.WGMI.url` in config when located.
- **GEX is computed from delayed CBOE chains under the standard assumption
  (dealers long calls / short puts).** That is an assumption, not ground
  truth; readings near zero are especially ambiguous. Daily EOD cadence only —
  a regime/vol-context input, not a day-trading tool. No free history exists,
  so the GEX transition flag is live-only (False throughout the backtest).
- **Sector ETF flows = ΔSO × NAV are T+1** and miss heartbeat-trade nuance and
  intra-day creations. Good for direction and magnitude rank, not exact dollars.
- **Sponsor holdings scrapers are per-sponsor fragile**: ARK (clean CSV,
  reliable), SSGA/sectorspdrs (semi-stable JSON), iShares (ajax CSV with
  shifting product IDs), WGMI/CoinShares (bespoke page — most fragile).
  Circuit breaker marks a sponsor dead after 3 consecutive failures and
  alerts rather than crashing.
- **N-PORT validation is quarterly with ~60d lag** — it validates the scraper,
  never the live signal.
- **Earnings-revision breadth has no good free source.** The module is a
  best-effort mix of sparse yfinance analyst fields, optional Finnhub free
  tier, and a price-derived proxy. It is excluded from the regime engine by
  design and marked LOW CONFIDENCE everywhere it appears. Paid fix:
  LSEG I/B/E/S or Zacks (hundreds of $/mo) would make it a real input.

## Infrastructure

- **GitHub Actions schedule jitter**: runs can start 0–40 min late at busy
  times. The 22:40 UTC slot mitigates but does not eliminate this; data is
  EOD so lateness affects delivery time, not correctness.
- **The repo-as-database grows forever.** Parquet appends are small, but the
  breadth close-matrix cache is deliberately kept OUT of git (actions/cache
  instead) to avoid uncompressible churn. If the repo nears GitHub's soft
  limits in a few years, archive old `data/holdings/` snapshots.
- **Monthly econ confirmations (payrolls, INDPRO) are step-filled forward** up
  to ~2 months — they are slow confirmations by design, but the fill means a
  turning point appears in the axis only after the next release.
- **WALCL is weekly (Wed release)** and forward-filled within the week; net
  liquidity is therefore up to 4 business days stale by Friday. The dashboard
  flags this rather than hiding it.

- **Seasonality is weak evidence by construction** — ~28 observations per
  calendar month per ETF, no significance testing. It's displayed as context
  with its sample size and deliberately excluded from the heat score.
- **The heat score describes confirmation, not future returns** — its own
  calibration (shown in every tooltip) found the hottest band *under*performed
  forward; treat high heat as hold/trim territory. See DECISIONS D31.

- **Cycle counts are interpretive.** Trough detection is mechanical, but real
  cycles stretch, shorten and fail; the sources themselves put timing-band
  accuracy at ~60-70%. The drill-down pages state this, and every buy state
  requires price confirmation (swing low + 10-day MA) precisely because the
  band alone is unreliable. Treat cycle-day counts as a probability lens, not
  a schedule.
- **Per-stock fundamentals are sparse, unofficial yfinance fields** refreshed
  weekly — display-only context, never inputs to any signal.

## Engine

- **Quad boundaries are scores around zero**; hysteresis (5d / ±0.7 shock)
  suppresses whipsaw but adds up to a week of lag on slow regime turns — this
  is the accepted trade-off, tuned in Phase 2e validation.
- **The transition detector's GEX flag adds no historical evidence** (no free
  GEX history) — its live usefulness is unvalidated until enough live data
  accumulates.
- **Cycle tag (early/mid/late) is heuristic** — curve shape + credit + breadth
  rules, not a fitted model. Treat as context, not signal.
