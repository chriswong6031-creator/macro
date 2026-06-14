# Known limitations — honest and maintained

Update this file whenever a weakness is discovered or fixed. Every item lists
the consequence, not just the cause.

## China A-share dashboard

- **Macro is a scraper plane (Eastmoney), not a clean API.** PMI/CPI/PPI/M2/
  industrial-production come from Eastmoney's datacenter JSON — free and verified,
  but a layout/endpoint change can silently drop a series. Each is circuit-breaker
  isolated and archived forever (the datacenter only serves recent history), so a
  gap self-heals, but the macro layer is structurally more fragile than FRED.
- **China macro history is short and regime-unstable.** Monthly series start
  ~2006–08, so the regime is calibrated on ~18 years vs the US's decades, across a
  market reshaped by the 2007/2015 bubbles and heavy policy intervention. Only the
  **Growth-scare** quad (contrarian) and **expanding-liquidity** overlay survive
  split-half robustness; Goldilocks/Stagflation flip between halves and ship as
  *context, not allocation rules* (stated on the dashboard + brief).
- **No real ETF holdings — sector membership is curated.** There is no free
  Chinese-ETF holdings feed comparable to SSGA's XLSX, so each sector's
  constituents are a hand-curated large-cap list in `config.yml` (also the breadth
  denominator). This makes breadth a **large-cap (CSI300-style) gauge**, and the
  sector drill-down shows *representative* names, not the ETF's true holdings.
- **Sector-ETF RS is display-grade (~5y history).** The 16 mainland sector ETFs
  mostly launched 2019–21, so their relative-strength ranks are short-history; the
  ladder/regime are calibrated on the **deep** stock/index panel (1997–2026), and
  the sector ETFs are rendered through the same engine but not independently
  calibrated. Labeled on the page footer.
- **Stock Connect northbound froze Aug-2024 + southbound parsing is imperfect.**
  Regulators curtailed real-time northbound disclosure, so `northbound_cum` goes
  flat (expected, not a bug); the southbound leg parsing is best-effort and
  non-load-bearing. Connect flows are context only, not a regime input.
- **SHIBOR series is shallow** (the rates report returns only a short recent
  window), so the liquidity overlay anchors on M2-YoY; SHIBOR is a secondary tilt.
- **Constituent stock names are tickers** (no free Chinese-name map wired yet) —
  the A-share search matches by ticker/sector, not company name in either language.
- **Global cross-border factors are NOT yet in the China regime** (deferred by the
  user). Measured separately (research): global risk/dollar factors drive Hong Kong
  ~2× more than A-shares; that overlay now ships in the **Hong Kong** dashboard.

## Hong Kong / Hang Seng dashboard

- **The fundamental read is China's, not HK's.** ~75% of HSI market cap is China
  earnings, so the growth/inflation axes consume the Mainland PMI/CPI/PPI/M2
  (`china_macro`). That is the right call for HSI, but it means HK macro stress that
  is *not* China-sourced (e.g. a pure HKD-funding squeeze) only reaches the regime
  through the price-based legs (peg distance, H-share leadership, breadth), not the
  fundamentals.
- **HS-TECH is proxied by an ETF (2020→).** `^HSTECH` is not on Yahoo, so the
  HS-TECH/HSI growth-tilt component uses the CSOP HS-TECH ETF (3033.HK), which only
  starts in 2020 — shorter than the other legs, so it drops out of the deep
  pre-2020 classification (the axis renormalizes over what exists).
- **Sectors are curated synthetic baskets, not float-cap indices.** HK sector-ETF
  coverage is thin, so each "sector" is an **equal-weight basket** of ~6 curated
  large-caps (`config.yml hk.sectors`). This gives deep history (most names
  2000–2006→, *richer* than China's ~5y ETFs) but it is a large-cap basket, not a
  reconstruction of the Hang Seng industry indices — labeled on the page.
- **The global risk overlay is a CONCURRENT state, not a forecast.** Global factors
  are coincident at weekly frequency (lead-lag ~0). The composite is honest as a
  *risk regime gauge*; calibration (2000→2026) shows it differentiates HSI forward
  returns monotonically (Risk-on +0.9%/21d 57% hit > Risk-off > Neutral) but that is
  a base rate over a few thousand days, not a timing signal.
- **Measured records (split-half, on the Hang Seng Index).** Unlike China (where
  only Growth-scare survived), HK's quad ordering is **stable**: Goldilocks best
  (+1.3%/21d, positive both halves), Stagflation worst (−0.9%, negative both); dual
  liquidity (PBoC + Fed-via-peg) is monotone (expanding > contracting). Still framed
  as risk context + the cycle ladder as a drawdown tool, never a standalone trigger.
- **HK charts are drawn from our own stored prices, not a live symbol feed.** The
  free TradingView *symbol* widget gates HKEX data behind a login ("only available
  on TradingView"), so the HK stock-analyzer and sector pages render an
  adjusted-close + 50/200-DMA chart from our nightly EOD store via TradingView
  Lightweight Charts (open-source). Consequence: HK charts are EOD close only (no
  intraday, no candles/volume — we don't store OHLC for constituents) and span ~2y;
  the deeper cycle/MTF analysis is unaffected. China/US/crypto pages still use the
  live TradingView widget (their exchanges aren't gated on the free tier).
- **AH premium is a COMPUTED basket, not the official index.** The Hang Seng AH index
  source is dead, so `engine/hk_ah.py` computes a 12-pair equal-weight basket from
  dual-listed H-shares (HKD) vs A-share twins (CNY), FX-adjusted. It assumes 1:1
  A/H share-equivalence and ignores share-class/float weighting, so the absolute level
  differs from the official index — read the **trend + percentile**, not the level. ~3y
  of history (bounded by the A-share close store starting 2021/the HK cache ~3y).
- **VHSI (`^HSIL`) is correlated with US VIX** — both are in the Global Risk Overlay
  (modest 0.75 weight on VHSI), so "fear" is mildly double-counted by design (HK-local
  fear legitimately matters more for HK). It's also surfaced as a standalone hero gauge.
- **HKMA Aggregate Balance is daily but the funding leg is a slow signal** — it moves on
  peg-defense episodes, not day to day; the liquidity overlay reads its 63-day trend.
  HIBOR 3m/12m tenors aren't in the liquidity endpoint (O/N + 1m only).
- **Southbound flow starts 2017** (Stock-Connect era), so that liquidity leg renormalizes
  in only from then; the China credit/RRR backdrop is monthly and lagged (a context
  strip, not a high-frequency signal). The HK playbook/exposure-dial is a risk-context
  map with measured odds, not a forecast.

## Bitcoin Vector alerts

- **"Real-time" is honest near-real-time (~15–45 min), price-only intraday.**
  The flash-crash sentinel runs on a 30-min GitHub Actions cron, which is
  best-effort (can slip to 45 min at busy times). On-chain, regime, momentum,
  structure and allocation alerts refresh on the daily run only. Glassnode/
  Swissblock's "real-time" is likely minute-level; the timeline footer states
  ours plainly rather than implying a live feed.
- **Flash-crash thresholds are provisional**, set from known episodes (covid,
  Luna, FTX, Aug-2024 yen-carry) not a formal sweep: 6h drop must be ≥3.5σ AND
  ≤−7%, or 24h ≤−12% (tail ≤−18%). They catch the genuine acute crashes
  (~10 acute entries/yr) and ignore ordinary −3% grind days, but the exact
  boundary is a judgement call documented in config `vector.alerts.flash`.
- **The sentinel commits only on a flash-state change** (no per-eval heartbeat),
  so the live site's "last evaluation" is the last *build* time, not the last
  sentinel tick — the 30-min checks are invisible until something actually fires.
- **Home-page combined feed is filtered, not exhaustive**: macro shows act+warn
  (circuit-breaker operational alerts excluded), vector shows high+medium,
  deduped within 5 days, capped at 12. The full, granular Vector feed is on
  vector.html#timeline. Macro alerts are date-resolution (no intraday time).

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
- **Sector-ETF accumulation signal (Accumulation Watch) is a PASSIVE-fund
  residual, not manager conviction.** `engine/holdings_signals.py` decomposes
  each top-10 holding's weight change into a price part and a residual
  (`active_change`). On the sector SPDRs — which are passive, market-cap-weighted
  index funds — that residual is index reconstitution / float-weight flow (forced
  index-fund buying), NOT a discretionary manager favoring a name. The
  conviction interpretation only applies to the *active* funds planned for the
  Phase-2 top-200 page. Further caveats: (1) top-10 holdings only, so accumulation
  outside the top 10 is invisible; (2) stored weights are rounded to 0.01% — the
  noise floor is ~0.01pp, well below the 0.15pp flag threshold but worth knowing;
  (3) `r_fund` uses the ETF's market close as a proxy for NAV (tiny premium/discount
  on liquid SPDRs); (4) the estimated $-flow (active_change × AUM) is approximate;
  (5) thresholds are UNCALIBRATED — only one snapshot exists at launch (2026-06-11),
  so signals are empty until ≥2 daily snapshots accumulate and thresholds should be
  re-tuned once weeks of residual history exist. See DECISIONS D70.
- **Top-200 ETF flow radar (etfs.html) coverage is sponsor-limited — ~30-40% of
  top-200 AUM, but a large share of the fund COUNT.** The broad `etf_holdings`
  universe uses share-based flow-normalized active decisions, which need full daily
  holdings WITH shares. VERIFIED free server-fetchable feeds (recon 2026-06-13):
  **SPDR/State Street** (daily XLSX incl. Shares Held), **ARK** (CSV), **Invesco**
  (the `dng-api.invesco.com` cache JSON — use `idType=cusip`; `idType=ticker` 500s
  for all but the flagship QQQ), and **Global X** (dated full-holdings CSV; walk back
  a few business days on 404). BLOCKED and intentionally NOT seeded: **iShares/
  BlackRock** (~30% of top-200 AUM — Akamai Bot Manager serves a consent-wall HTML
  body under a deceptive `text/csv` header even with consent cookies; needs a headless
  browser — `_fetch_ishares` is retained for that future path), **Schwab** (403/JS),
  and **Invesco non-flagship pages**. **Vanguard** (~25-29% of AUM) publishes no free
  daily holdings feed (month-end + quarterly N-PORT only) — do not fake a daily signal
  for it. ProShares was evaluated and dropped: its consolidated CSV is mostly
  leveraged swap/futures funds with no stock-level conviction signal. A degraded
  third-party layer (stockanalysis.com scrape) could cover the wall-blocked mega-caps
  later, clearly labelled non-official. Same passive-vs-active honesty caveat as the
  sector signal applies; signals need ≥2 daily snapshots per fund. See DECISIONS D71.
- **Volume-surge confirmation activates late.** Stock volume is now captured by
  `StockPriceAdapter`, but parquets written before this change have no `volume`
  column — the 📊 surge marker stays dark until either a `--full-history` backfill
  runs or ~25 daily snapshots with volume accrue. It is a confirmation enhancer,
  never required for a signal.
- **Earnings-revision breadth has no good free source.** The module is a
  best-effort mix of sparse yfinance analyst fields, optional Finnhub free
  tier, and a price-derived proxy. It is excluded from the regime engine by
  design and marked LOW CONFIDENCE everywhere it appears. Paid fix:
  LSEG I/B/E/S or Zacks (hundreds of $/mo) would make it a real input.

## Quant-factor expansion — conditions layer & factor engine

(research/QUANT_FACTOR_EXPANSION.md — added to broaden the methodology beyond
technical/momentum into the Fed-research feeds, option-implied risk, and
cross-sectional equity factors.)

- **The conditions/nowcast/risk-appetite layer is COMPLEMENTARY, not the
  validated quad.** `engine/conditions.py` (Financial Conditions, recession risk,
  growth/inflation nowcasts, equity VRP, RORO, stock-bond correlation) runs
  *alongside* the split-half-validated growth/inflation regime and never alters
  it — agreement strengthens conviction, divergence is a heads-up. Unlike the
  quad it is **not independently split-half-backtested**; it is shipped as honest
  context built from standard, free Fed/CBOE series.
- **Nowcast & financial-conditions series get revised.** GDPNow, WEI, NFCI, the
  Cleveland/Atlanta inflation nowcasts and the Sahm rule are model outputs that
  Fed banks revise; a same-day read is the current vintage, not a final value.
  The recession-risk composite is a transparent weighted blend, not a fitted
  probit. The **term-premium-adjusted curve** is `2s10s + ACM 10y term premium` —
  a heuristic to flag the 2019/2022-24 "inverted-but-no-recession" episodes, not
  a calibrated model.
- **Stock-bond correlation uses a yield-change proxy for Treasury returns**
  (−Δ10y yield), ignoring convexity/level — fine for the correlation *sign*
  (the "bonds aren't hedging" 2022-style regime), not a duration-accurate return.
- **Inflation-nowcast annualization is jumpy.** Sticky/flexible CPI are monthly
  %-change prints annualized over a 3-month smooth; the *flexible* leg swings
  widely (energy) so its absolute annualized number is noisy — the signal is the
  persistent-vs-transitory *comparison*, not the flexible level.
- **CBOE SKEW is a tail-pricing gauge, weak as a standalone timing tool.** It is
  a regime conditioner (how much the market pays for crash protection), not a
  trigger; shipped as a percentile, not against historical absolute levels.

### Cross-sectional equity factor engine (factors.html)

- **Not a backtested alpha — a live cross-sectional ranking.** Factors are
  winsorized cross-sectional z-scores over the S&P 1500 *as of today*. EDGAR
  serves only **published** filings, so the live snapshot is point-in-time-honest
  (no future data leaks in), but there is **no historical factor backtest** here —
  the records are documented in the literature, not measured on our data. Factors
  decay post-publication (~58%, McLean-Pontiff) and crowd; book/price is weak for
  intangible-heavy firms; long-only *unlevered* low-beta/BAB is far weaker than
  the levered academic Sharpe. Treat ranks as a research lens, not a buy list.
- **Free fundamentals are sparse for some us-gaap tags.** Coverage on the S&P
  1500 (recon 2026-06): Assets/CFO/NetIncome/equity ~90-100%, **GrossProfit only
  ~40%** (many filers tag COGS instead), **dividends ~39% / buybacks ~72%**. So
  *profitability* and *payout* rank fewer names than value/quality; the composite
  requires ≥3 available legs. Payout uses **actual dividend + repurchase cash
  flows** (not a shares-outstanding-change proxy, which would conflate buybacks
  with issuance/dilution).
- **The ticker→CIK map has a name-matching fallback.** SEC's
  `company_tickers.json` (on www.sec.gov) rate-limits/403s hard; when unavailable
  the collector matches the XBRL `entityName` against our universe company names
  (normalized). That maps ~1340/1500 names and can mis-map a handful of ambiguous
  names; ~160 stay unmapped until the exact file is reachable (cached 30 days once
  fetched). CIK mappings spot-checked (AAPL/MSFT/JPM/NVDA/JNJ/WMT correct).
- **US-GAAP tag ratios are noisier for non-standard reporters.** Banks, insurers
  and REITs report on different templates, so their gross-profitability /
  investment / book ratios are less comparable to industrials — no
  sector-neutralization is applied in this first version.
- **Market cap is approximate** (adjusted close × latest reported shares); the
  "leadership" read (top- minus bottom-quintile trailing 63d return) is
  descriptive of what has been rewarded, **not** a forecast.
- **Fundamentals refresh weekly (cached); ranks recompute daily** with prices.
  The fetch is ~25 EDGAR calls/run, paced under the 10 req/s fair-access limit
  with a descriptive User-Agent (set your own contact in `config.yml edgar`).

### Four-phase build-out (carry · EIA supply · short interest · insider)

- **Commodity carry: the LIVE roll yield is exact; the reconstructed history is
  approximate.** `collectors/commodity_carry.py` computes the front-vs-second
  annualized roll yield from Yahoo DATED contracts. Today's reading is the true
  nearest two contracts, but Yahoo DELISTS expired contracts, so for older dates
  the engine falls back to the still-listed (more deferred) contracts — the
  historical curve slope is therefore measured further out and is damped/
  approximate. Dated contracts are also thinner than the continuous front. Treat
  the backwardation/contango STATE and the live roll yield as the signal, the
  history as context. Fetched weekly (the curve shape is slow).
- **EIA supply is via the keyless dnav .xls download, not an API.** `collectors/
  eia.py` parses EIA's "Download Series History" .xls (Weekly Petroleum Status).
  Weekly (Wed release), revised, and a layout change to the .xls could break a
  series (each is isolated; a failure leaves that series at its last value). The
  supply "state" (low-stocks-percentile + draw = tightening) is a heuristic
  context read on the oil page, not a calibrated signal.
- **FINRA short interest is bi-monthly with a publication lag.** `collectors/
  finra.py` pulls the consolidated (exchange-listed) short interest from the free
  FINRA Query API. It settles twice a month and publishes ~8 business days later,
  so days-to-cover is up to ~3 weeks stale. The factor uses days-to-cover (short
  interest / avg daily volume) and short-as-%-of-shares (shares from EDGAR); the
  high-DTC negative-return relationship (Hong-Li-Rajan-Sherman) is real but
  decayed and crowded, and squeeze dynamics cut the other way — it is one
  standalone factor leg, not in the core composite.
- **Insider data is the most recent COMPLETED quarter, not real-time.** `collectors/
  sec_insider.py` uses the SEC "Insider Transactions Data Sets" — a single
  quarterly bulk zip — so a mid-quarter run still shows last quarter's Form-4s (a
  slow conviction read; the panel labels the quarter). It keeps only open-market
  purchases (code P) and sales (code S) — grants, option exercises and gifts are
  excluded — and clustered BUYING is the more informative side. Small/illiquid
  issuers are noisy. **sec.gov rate-limits / 403s hard** (the same wall as the
  EDGAR `company_tickers.json`), so both the insider and EDGAR fetches can fail a
  run; both degrade gracefully (cached value, or the panel simply hides) and
  recover on a later run / a cleaner CI IP.

## Forex Vector (forex.html)

Read this before trusting any currency verdict. The whole section ships as **risk
context, not alpha** — see `research/FOREX_DASHBOARD.md` and the `## 2026-06-13 —
Forex Vector` entry in DECISIONS.md.

- **UIP failure / forward-premium puzzle.** Uncovered interest parity does not hold
  and the Fama regression slope flipped sign at the short end post-2008. A static
  "carry sign" can be wrong in the current regime, so the directional LONG/SHORT-base
  label is SECONDARY to the risk-context headline, and carry's weight will come from
  split-half calibration (Phase 2), never a hardcoded prior alone.
- **Carry crash skew.** The carry factor is short global volatility / long funding
  liquidity with a fat left tail that clusters with equity crises (1998 / 2008 / 2015
  / 2020 / 2024). A Gaussian read overstates it; we vol-penalize carry and (Phase 2)
  regime-condition it down as VIX/NFCI rise, but the tail cannot be removed — the
  caveat ships inline on the carry tile.
- **Pegs & intervention truncate the distribution.** `USD/CNH` is managed (forced
  FLAT); `USD/JPY` near the MoF zone (≈150–162) is capped; `USD/CHF` carries 2015 SNB
  gap risk. Backtests over peg eras are unrepresentative; Phase-2 calibration must
  excise those windows or it will confirm a dangerously high carry weight.
- **Calibration is deliberately conservative.** `calibrate_forex` measures each
  factor's Spearman IC vs forward base-vs-USD returns, split-half (split 2015), peg
  windows excised. It does NOT replace the prior with raw-IC weights (that overfits
  short FX history and lets one noisy factor dominate) — it keeps the stable prior
  magnitude and uses the measurement only to FLIP signs of robustly-INVERTED factors
  and down-weight unstable ones. FX ICs are tiny (|IC| below ~0.04 is noise), so most
  factors land DIRECTIONAL/CONTEXT; a pair shows full confidence only with ≥2 factors
  that held sign in both halves — otherwise confidence stays dampened ×0.6. The
  measured carry sign comes out INVERTED for several pairs (the forward-premium
  puzzle), which is honest for this sample but horizon/regime-dependent. A Gaussian
  split-half still cannot fully price the carry crash tail — see the carry note above.
- **Carry data is coarse and partial.** No free clean daily cross-currency 2y exists,
  so carry uses policy/short rates (some monthly, lagged 2–5 months). This is fine for
  step-function policy rates (ffill is correct) but means carry is slow; EM (MXN/BRL/
  CNH) have no usable free front-end rate at all → `carry: context`, no weight.
- **COT positioning depends on CFTC uptime.** The contrarian positioning factor needs
  the CFTC Socrata endpoint, which has outages (it was 503 at this build, so FX COT is
  temporarily empty — the page flags this and the factor simply drops until the next
  successful collect). COT is also as-of-Tuesday / released-Friday: a contrarian
  MODIFIER, never a timing trigger.
- **Residual / orthogonalization caveats.** Per-pair signals are computed on the
  dollar-orthogonalized residual (rolling causal beta vs `DTWEXBGS`); the residual is a
  derived index, not a tradeable instrument. `CNH=X` has no usable Yahoo history (one
  current print) — its tile is China-proxy context only until backfilled from FRED.
- **REER value & 10y-rate-diff factors are slow and lagged.** Both are now wired but
  fed from monthly, lagged data: REER (BIS, ~6wk lag) and foreign 10y (OECD monthly,
  2–5mo lag). The engine shifts each by a publication lag (`_lag_to_daily`) before use,
  so the daily factor never sees a value before it was released — but the signals are
  inherently slow/coarse. The 10y rate-diff factor lands mostly CONTEXT in calibration
  (weak IC) and carries little weight; value is CONFIRMED for some pairs and INVERTED
  for JPY (the yen kept cheapening without mean-reverting). EM pairs have no foreign 10y,
  so they get no rate-diff factor.
- **USD/CNH uses an onshore proxy for history.** Yahoo `CNH=X` has only a current print,
  so the tile's history is backfilled from FRED `DEXCHUS` (onshore CNY). Onshore CNY ≠
  offshore CNH (the spread is itself a stress signal we don't yet model), and it's a
  managed regime — the tile is China-proxy risk-context only (forced FLAT).
- **MTF confluence is a pure technical overlay, not return-validated for FX.** It runs an
  FX-MEASURED cycle preset (`CYCLE_PRESETS["fx"]`: a ~35-trading-day daily cycle — wider/
  noisier than equities' 36–42 — and a ~34-week intermediate cycle vs equities' 16–26;
  measured across the G10 majors, see `research/FOREX_DASHBOARD.md`). For FX the macro-fusion
  (driver/trend lean) intentionally zeroes out, so what ships is the asset-agnostic
  D/3D/W/2W/ME RSI/Stoch/MACD + cycle-ladder read — a tactical TIMING overlay. The cycle
  LENGTHS are now measured, but the ladder's forward edge was NOT return-validated for FX
  (FX range-trades differently); treat it as indicative timing context, not alpha.
- **CNH offshore−onshore basis uses a futures proxy.** The USD/CNH tile prices off the CME
  offshore-CNH futures continuous (`CNH=F`, 2013→) because Yahoo's `CNH=X` spot has no
  history; the basis is `CNH=F` minus FRED onshore `DEXCHUS`. A continuous-futures splice
  carries roll artifacts, the onshore series lags ~1 week, and CNH is a managed regime — so
  the basis is a STRESS/flow STATE (positive = depreciation/outflow), never a tradeable signal.
- **Alerts are daily-only.** There is no intraday FX feed in the repo, so the alert engine
  recomputes deterministic DAILY state-change events (shock/risk/trend/momentum/structure,
  plus FX-specific carry-inversion, peg-zone approach, dollar-smile regime) — no intraday
  price-shock state machine like the commodity sentinel. COT-positioning events stay empty
  until CFTC recovers. All events are context, never trade signals.
- **Everything Yahoo is an unofficial API** (same caveat as the rest of the site).

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
- **Pre-emptive ("early reversal") signals do not beat waiting on average.**
  RSI divergence / MACD histogram trough / StochRSI pops fire earlier, but our
  own calibration (BOTTOM WATCH +early-bull 57.8%/+1.16% vs no-early
  58.8%/+1.58%, fwd 21d) shows no average edge — they trade a higher false-alarm
  rate for catching the occasional sharp V-bottom. They are framed everywhere as
  a "watch closely" heads-up, not a trigger, and the comparison is printed on
  every drill-down. RSI-divergence repaints (the second pivot only confirms a
  few bars after the actual low), so "anticipation" is partly hindsight.

## Engine

- **Quad boundaries are scores around zero**; hysteresis (5d / ±0.7 shock)
  suppresses whipsaw but adds up to a week of lag on slow regime turns — this
  is the accepted trade-off, tuned in Phase 2e validation.
- **The transition detector's GEX flag adds no historical evidence** (no free
  GEX history) — its live usefulness is unvalidated until enough live data
  accumulates.
- **Cycle tag (early/mid/late) is heuristic** — curve shape + credit + breadth
  rules, not a fitted model. Treat as context, not signal.
