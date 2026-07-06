# Signal Lab frontier study - 2026-07-06

Purpose: expand `signal_lab.html` with new signal hypotheses while preserving the
page's core law: hypotheses are not verdicts. A candidate can appear on the page
as frontier research, but it cannot enter the scored/confirmer/display/killed
registry until a pre-registered Phase-0 run writes a report and survives the
same validation battery as every other row.

Update: the initial 10-candidate frontier below was expanded into a 60-candidate
Phase-0 admission docket in `research/SIGNAL_LAB_FRONTIER_PHASE0_2026-07-06.md`
and the machine-readable ledger
`research/signal_lab_frontier_phase0_2026-07-06.json`. That run advanced 23
candidates for Fable review, kept 30 in local Phase-0, marked 5 as data-contract
first, and rejected/graveyarded 2.

## Starting point

The current Signal Lab is already large and harsh: 62 registry rows, 6 scored,
20 confirmer, 27 display, 9 killed, plus the live factor IC panel. Prior in-repo
expansion work concluded that the free-data scored frontier is mostly saturated:
new scored rows probably require new data, not another 200dma/VRP/term-structure
variant. This study therefore prioritizes:

1. Data that the repo does not yet validate deeply.
2. Signals with real literature or official data behind them.
3. Candidates that can become a graveyard row if they fail.
4. Features that improve an existing scored signal's timing or risk gating rather
   than pretending to be standalone alpha.

## External discipline from the literature

- The factor zoo is dangerous. Hou, Xue and Zhang replicate 447 anomaly variables
  and find most do not survive once microcaps, multiple testing and value-weighted
  construction are handled. Use that as the anti-p-hacking north star.
- McLean and Pontiff find that published anomaly returns decay materially after
  publication. Treat well-known textbook effects as prior art, not automatic edge.
- Stronger opportunities tend to be in hard-to-arbitrage or hard-to-source data:
  borrow fees, FTDs, option order-flow, EDGAR attention, clean futures positioning
  and microstructure decomposition.

## Top candidates surfaced on signal_lab.html

| Priority | Candidate | Data | Feature | Baseline to beat | Likely home |
|---|---|---|---|---|---|
| P0 | SEC fails-to-deliver pressure | SEC semi-monthly FTD files | `ftd_shares / float`, `ftd_usd / adv_usd`, rising-FTD z | size, price, short volume, momentum, low-liquidity | confirmer or killed |
| P0-data | Borrow-fee / loan-fee anomaly | paid securities-lending vendor | fee percentile, utilization, fee change | FTD + FINRA SI + short volume + microcap controls | scored only if vendor quality is high |
| P1 | Option informed-flow lens | existing options plumbing + richer history | buyer-open put/call proxy, O/S volume, IV spread | GEX, 200dma, public put/call, scheduled-news controls | confirmer/graveyard |
| P1 | EDGAR attention shock | SEC EDGAR logs, 2020-2025 first | abnormal human filing views by form/ticker | filing type, size, volatility, news, Google Trends proxy | event confirmer |
| P1 | Overnight/intraday tug-of-war | OHLC already available | close-open and open-close decomposition by strategy | close-to-close strategy, open spread/impact | entry-timing overlay |
| P1 | Treasury auction absorption | existing `treasury_auctions` collector | bid-to-cover z, indirect share, dealer takedown, issue size | term premium, MOVE, 200dma duration trend | display/confirmer |
| P2 | COT exhaustion matrix | existing COT store | 3y spec-position percentile and change | price trend, VIX, existing capitulation leg | confirmer/graveyard |
| P2 | Crypto funding + on-chain stress | Coin Metrics + perp funding | funding extremes, MVRV delta, realized-cap stress | BTC Vector raw engine, brake-matched 200dma | confirmer |
| P2 | Supply-chain pressure impulse | NY Fed GSCPI | level, change, percentile, local surprise | NFCI/OFR for macro; sector own trend | sector context |
| P2 | Lottery/MAX anti-chase flag | price-only | prior-month MAX, idio-skew, extreme single-day run | liquidity, microcap, volatility, extension | subtract-only display |

## Candidate details

### 1. SEC fails-to-deliver pressure

Why it is interesting: FTDs are a free, official proxy for settlement stress and
short-sale pressure. Stratmann and Welborn find FTD stocks experience negative
abnormal returns proportional to FTD levels. SEC data is messy: the daily value is
an aggregate net balance, not a daily flow, and missing rows mean zero balance
after 2008.

Implementation:

- New collector: `collectors/sec_ftd.py`.
- Write `data/sec_ftd/panel.parquet` keyed by settlement date, CUSIP, ticker.
- Map CUSIP with existing OpenFIGI/CUSIP utilities where possible.
- Construct PIT features at the first date the half-month file is available:
  `ftd_shares / shares_out`, `ftd_usd / adv_usd`, `ftd_days_present_20`,
  `ftd_change_z`.

Validation:

- Monthly or semi-monthly rebalance, 21d and 63d forward returns.
- Rank-IC and quintile L/S net of shorting feasibility assumptions.
- FDR across level, change, persistence and normalized variants.
- Incremental IC after size, price, liquidity, momentum and FINRA short-volume.

Expected honest outcome: likely a confirmer or killed row, but this is the best
free-data short-pressure candidate because it adds a dimension the current
short-volume context does not.

### 2. Borrow-fee / loan-fee anomaly

Why it is interesting: this is the most compelling literature-backed signal in
the study, but it needs paid data. Engelberg et al. report loan fees as the best
cross-sectional predictor among a broad set of anomalies and short-selling
measures. Free short interest and daily short volume are weaker substitutes.

Implementation:

- Do not build until a vendor is chosen. Candidate vendors: DataLend/IHS Markit,
  S3, ORATS/LiveVol-like borrow fields, IBKR indicative borrow if PIT terms allow.
- Required columns: date, ticker/CUSIP, borrow fee, lendable supply, utilization,
  rebate/loan fee, locate difficulty if available.
- Archive raw snapshots. No overwrite-only store.

Validation:

- High-fee underperformance at 21/63d.
- Long-only exclusion value: does removing top-fee names improve the board?
- Incremental test vs FTD, FINRA short interest/volume, price, size and liquidity.
- Liquidity/capacity curve because high-fee names are often hard to trade.

Expected honest outcome: this is the only candidate here that could plausibly
challenge for a scored row, but only with proper PIT vendor history.

### 3. Option informed-flow lens

Why it is interesting: Pan and Poteshman show buyer-initiated option volume has
information about next-day/week stock returns. The problem is not the idea; the
problem is that the strongest variable is not the same as a public EOD put/call
ratio. The repo already has options plumbing, GEX, IV spread and options-entry
state, so the right move is a targeted validation, not a new dashboard toy.

Implementation:

- Extend `engine/options_flow.py` and `scripts/build_options_flow.py`.
- Separate index hedging from single-name speculation.
- Track option/stock volume ratio, put/call OI changes, IV spread, skew, volume
  concentration by delta/expiry and scheduled-news flags.
- If buyer-open classification is unavailable, label the proxy as weak.

Validation:

- 1d, 5d, 21d event-window returns.
- Scheduled-news vs unscheduled-news split.
- Baselines: GEX regime, IV spread alone, 200dma, public put/call.
- DSR with a declared option-feature trial budget.

Expected honest outcome: likely confirmer around news windows; public proxies may
fail and deserve the graveyard.

### 4. EDGAR attention shock

Why it is interesting: SEC EDGAR log files are official and current enough for a
2020-2025 prototype. They directly measure demand for filings, unlike generic
Google Trends. The heavy lift is de-roboting and joining log CIK/accession data to
tickers and filing events.

Implementation:

- Prototype collector off the nightly path: `scripts/backfill_edgar_logs.py`.
- Use a small target universe and 2020-2025 logs first.
- De-robot using SEC variables plus repeated-hit filters.
- Aggregate by filing-day: human views, unique IP blocks, abnormal views vs
  issuer/form baseline, stale-filing vs fresh-filing mix.

Validation:

- 8-K/10-Q/10-K event returns and drift.
- Separate "attention to stale file" from "information acquisition around fresh
  material filing."
- Brier calibration if converted into event probabilities.

Expected honest outcome: likely an event-context confirmer. It may be too heavy
for nightly, but it can feed offline Signal Lab rows.

### 5. Overnight/intraday tug-of-war

Why it is interesting: Lou, Polk and Skouras document continuation within
overnight and intraday components plus cross-period reversal. This does not need
new data. It may improve execution/timing for existing signals, especially
momentum, reversal, insider, payout and index-event rows.

Implementation:

- New script: `scripts/overnight_intraday_phase0.py`.
- Use adjusted OHLC where available; label dividend/split basis.
- For each existing candidate family, decompose returns into:
  `overnight = open / prev_close - 1`, `intraday = close / open - 1`.
- Test whether entry should happen at close, open, or next close.

Validation:

- Net of open-spread/impact assumptions.
- Split-half and era stability.
- No alpha claim unless the trade is executable at the needed time.

Expected honest outcome: best as an entry-timing overlay, not a new scored row.

### 6. Treasury auction absorption

Why it is interesting: the collector already exists and official Treasury data
includes bid-to-cover, bidder takedown and issue size. But auction results are
mostly ex-post, so this is likely event context unless pre-auction variables can
predict auction weakness.

Implementation:

- Use `data/treasury_auctions/auctions.parquet`.
- Add same-day market context: MOVE, 10y trend, term premium, issuance z.
- If a reliable when-issued source exists, add auction tail; otherwise do not
  fake it from high yield alone.

Validation:

- Event study on TLT/IEF, 2s10s/5s30s, dollar and equities.
- Split by tenor and reopening.
- Separate post-auction reaction from pre-auction predictor.

Expected honest outcome: display or confirmer. Scored is unlikely without a
pre-auction predictor that beats term premium and trend.

### 7. COT exhaustion matrix

Why it is interesting: COT already contributes to capitulation context. A broader
matrix could show cross-asset crowding and exhaustion, especially in rates,
gold/copper/oil, DXY and equity futures. CFTC data is official and long history.

Implementation:

- Build `engine/cot_exhaustion.py` from existing COT store.
- Features: 3y percentile, z-score, 2-week change, crowded-long/short flags,
  cross-asset cluster count.
- Honor CFTC's Tuesday-as-of / Friday-release lag.

Validation:

- Asset-specific forward returns and drawdowns.
- Cross-asset overlay vs simple price trend and VIX.
- Leave-crisis-out, because COT can look great in a small number of washouts.

Expected honest outcome: confirmer or graveyard.

### 8. Crypto funding + on-chain stress

Why it is interesting: the repo already has Coin Metrics and BTC vector plumbing.
Funding rates and valuation metrics can add tail/cycle context, but crypto has
only a few independent cycles. The previous BTC gate contamination audit makes
separating raw engine and human gates mandatory.

Implementation:

- Add or backfill perp funding from exchange APIs only if ToS and retention are
  acceptable.
- Use Coin Metrics MVRV/realized-cap derivatives already supported.
- Test funding extremes and valuation deltas as confirmers, not primary direction.

Validation:

- Leave-one-cycle-out.
- Brake-matched 200dma baseline.
- Explicit DSR trial ledger. No "n=thousands daily bars" overconfidence.

Expected honest outcome: confirmer; scored is very unlikely because independent-N
is tiny.

### 9. Supply-chain pressure impulse

Why it is interesting: the NY Fed GSCPI is an official, monthly macro signal that
should matter more for inflation-sensitive sectors and goods cyclicals than broad
SPY. This is probably a sector conditioner, not a market-timing leg.

Implementation:

- New collector for FRBNY GSCPI if not already reachable through FRED/local files.
- Features: level percentile, 3m change, local surprise vs AR(1), easing/tightening.
- Targets: breakevens, CPI/PPI revisions, transports, semis, retail, commodity
  sectors, China export proxies.

Validation:

- Sector-relative IC with macro controls.
- Must beat OFR/NFCI for broad risk claims.
- Print nulls by sector to avoid story-fitting.

Expected honest outcome: display/sector context.

### 10. Lottery/MAX anti-chase flag

Why it is interesting: MAX and lottery demand are intuitive and easy to compute,
but the factor-zoo replication literature is a serious warning. This should only
be tried as a subtract-only "do not chase extreme one-day winners" flag in liquid
universes.

Implementation:

- Compute prior-month max daily return, average top-5 daily returns, idiosyncratic
  skew and distance from 52-week high.
- Filter out microcaps/low-price names; use NYSE breakpoints and value weights.

Validation:

- 21/63d forward excess return and drawdown.
- Incremental to realized vol, extension, short-volume, momentum and liquidity.
- Require liquid-universe pass before any UI chip.

Expected honest outcome: likely killed or display; useful even if it becomes a
graveyard row because it cautions against a popular trader heuristic.

## Secondary candidates not surfaced in the compact page panel

- Single-name credit/CDS-vs-equity lead-lag: strong mechanism, but practical data
  is paid. ETF credit proxies are too blunt for single-name stock timing.
- 13F crowding exits/initiations: already partially displayed; validation is
  hard because reporting lag is large and positions are stale.
- Analyst initiation vs revision: initiation is different from ordinary estimate
  revision and may be testable via EDGAR/news feeds, but clean PIT coverage is
  a blocker.
- Form 144 / ATM dilution pressure: promising for small caps if the repo can
  archive forms and measure forward issuance/sell pressure.
- Wikipedia/pageview demand: free attention proxy, but weaker than EDGAR logs and
  harder to keep commercial-use clean across providers.
- Customer/supplier momentum from 10-K relationship graphs: interesting but
  stale and costly to maintain without a proper relationship database.

## Admission policy for new rows

1. Frontier candidate appears only in the research-frontier panel.
2. Phase-0 preregistered script declares:
   - family ID and trial budget,
   - exact feature definitions,
   - PIT availability lag,
   - target horizons,
   - dumb baselines to beat,
   - promotion/demotion rule.
3. Script writes a report under `reports/`.
4. Only then does `engine/signal_lab.py` gain a normal registry row:
   - `scored` only if it passes DSR/FDR/split/beat-baseline and is wired,
   - `confirmer` if measured edge exists but cannot size standalone,
   - `display` if useful context but no validated edge,
   - `killed` if measured and refused.

## Source anchors

- Hou, Xue, Zhang, "Replicating Anomalies": https://www.nber.org/papers/w23394
- McLean, Pontiff, "Does Academic Research Destroy Stock Return Predictability?":
  https://www.fmg.ac.uk/sites/default/files/2020-08/Jeffrey-Pontiff.pdf
- Engelberg et al., "The Loan Fee Anomaly":
  https://pubsonline.informs.org/doi/10.1287/mnsc.2023.00152
- SEC fails-to-deliver data:
  https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data
- Stratmann/Welborn FTD study:
  https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2461088
- Pan/Poteshman option volume:
  https://www.nber.org/papers/w10925
- SEC EDGAR APIs:
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- SEC EDGAR log files:
  https://www.sec.gov/data-research/sec-markets-data/edgar-log-file-data-sets
- FINRA short interest:
  https://www.finra.org/finra-data/browse-catalog/equity-short-interest
- CFTC COT:
  https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- TreasuryDirect auction query:
  https://www.treasurydirect.gov/auctions/auction-query/
- CBOE VIX term structure:
  https://www.cboe.com/tradable-products/vix/term-structure/
- Coin Metrics Community API:
  https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data
- Coin Metrics realized cap docs:
  https://gitbook-docs.coinmetrics.io/network-data/network-data-overview/market/market-capitalization
- NY Fed GSCPI:
  https://www.newyorkfed.org/research/policy/gscpi
- OFR FSI:
  https://www.financialresearch.gov/financial-stress-index/
- Lou/Polk/Skouras overnight-intraday:
  https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- George/Hwang 52-week high:
  https://www.bauer.uh.edu/tgeorge/papers/gh4-paper.pdf
- Bali/Cakici/Whitelaw MAX:
  https://pages.stern.nyu.edu/~rwhitela/papers/max%20jfe11.pdf
- Loughran-McDonald dictionary:
  https://sraf.nd.edu/loughranmcdonald-master-dictionary/
