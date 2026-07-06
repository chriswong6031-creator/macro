# Signal Lab expanded frontier Phase-0 - 2026-07-06

This is the expanded docket behind `signal_lab.html`. It extends the initial
10 frontier rows to 60 total candidates and runs the same admission screen
over every candidate. The screen is intentionally pre-empirical: it does not
claim rank-IC, HAC t-stat, FDR q, or Deflated Sharpe unless a real harness
exists. Instead it decides which candidates deserve that expensive harness.

No candidate below is promoted into Signal Lab. `ADVANCE TO FABLE` means the
candidate survived the Phase-0 admission gates and is ready for Fable to
challenge, confirm the data contract, and authorize a real validation run.

## Verdict counts

- Total candidates screened: 60
- Advance to Fable: 19
- Local Phase-0 ready but not Fable-priority: 33
- Data contract first: 6
- Watchlist/reject: 1
- Graveyard now: 1

## Fable-ready survivors

| ID | Candidate | Market | Feature | First empirical gate | Baseline | Score |
|---|---|---|---|---|---|---|
| SLF-001 | SEC fails-to-deliver pressure | US equities | FTD shares/float, FTD USD/ADV, rising FTD z-score. | 21d/63d rank-IC plus incremental IC after short-volume controls. | Size, low price, liquidity, momentum, FINRA short volume. | 10.85 |
| SLF-005 | Overnight/intraday tug-of-war | US equities | Close-open and open-close return legs for existing factors and entries. | Net-of-open-spread IC and split-half stability; no alpha claim unless tradable. | Close-to-close signal, spread/impact estimates, volatility regime. | 11.2 |
| SLF-006 | Treasury auction absorption | US rates | Bid-to-cover z, indirect share, dealer takedown, issue size. (Auction tail struck — paid when-issued data required.) | Event study on TLT/IEF/curve; scoring barred unless pre-auction predictors work. | Term premium, MOVE, duration trend, same-tenor trailing auctions. | 11.3 |
| SLF-007 | COT exhaustion matrix | Cross-asset futures | 3y spec-position percentile, flow change, cross-asset crowding clusters. | Forward returns after crowding extremes; confirm only if it beats dumb trend gates. | Price trend, VIX/MOVE, existing capitulation legs. | 10.4 |
| SLF-010 | Lottery/MAX anti-chase flag | US equities | Prior-month MAX, idiosyncratic skew, extreme one-day winner flag. | Liquid-universe IC; expect graveyard unless incremental after HXZ controls. | Momentum, size, liquidity, volatility, NYSE breakpoints. | 10.4 |
| SLF-012 | FINRA short-volume stress | US equities | Short-volume ratio shock crossed with price strength/weakness and borrow proxies. | Cross-sectional IC and event buckets; never score unless it beats FTD/borrow proxies. | Price momentum/reversal, FTD, size, liquidity. | 10.4 |
| SLF-025 | Opportunistic insider cluster | US equities | Non-routine insider buys, cluster buys, role-weighted net USD/market cap. | Incremental IC over current insider factor; routine-trader filter required. | Current insider row, size, liquidity, value, post-drawdown state. | 11.6 |
| SLF-026 | Insider sponsorship after solvency repair | US equities | Insider buying after balance-sheet and cash-flow repair, not generic dip-buying. | Cross-sectional IC and bottom-rebound event buckets. | Insider buying alone, value, leverage, momentum. | 10.8 |
| SLF-027 | Net issuance / dilution shock | US equities | Share-count growth, ATM/convertible/securities issuance, dilution acceleration. | Monthly IC and exclusion value for long-only board. | Size, momentum, asset growth, profitability, sector financing windows. | 10.8 |
| SLF-031 | EDGAR lazy-prices text-change signal | US filings | Year-over-year 10-K/10-Q textual change and neglected section deltas. | Post-filing 21/63/126d IC; require incremental edge over tone and attention. | Filing tone, size, volatility, post-filing drift, EDGAR attention. | 10.35 |
| SLF-034 | 8-K item taxonomy surprise | US filings | Item-level 8-K surprise clusters, filing-time abnormal volume, stale vs fresh attention. | Event-window abnormal returns and post-event drift by item family. | Event calendar, earnings, news sentiment, volatility. | 10.8 |
| SLF-035 | Guidance revision language | US equities | Guidance raise/cut, uncertainty language, management narrowing/widening. | Forward IC and event drift; must beat analyst revision breadth. | Analyst revisions, SUE, earnings date, sector. | 10.8 |
| SLF-038 | Gross-margin inflection | US equities | Gross margin acceleration and recovery from trough, sector-relative. | Quarterly PIT IC; reject if subsumed by profitability/revisions. | Profitability, value, revisions, industry trend. | 10.4 |
| SLF-039 | Inventory build versus sales slowdown | US equities | Inventory growth minus sales growth, adjusted by industry seasonality. | Quarterly IC; must show negative forward edge outside retailers/energy quirks. | Accruals, asset growth, margins, sector. | 10.4 |
| SLF-051 | China margin-financing impulse | China A | Margin balance acceleration, sector concentration, margin/turnover ratio. | Forward IC and crash-risk test; separate informed leverage from sentiment leverage. | Turnover, valuation, northbound flow, policy tone. | 10.4 |
| SLF-053 | A-H premium dislocation convergence | China / HK | Pair-level A-H premium z-score, flow gating, currency stress. | Pair convergence IC; forbid broad-market claim unless portfolio construction works. | Southbound/northbound flow, CNH basis, market regime. | 10.4 |
| SLF-055 | Primary-dealer Treasury inventory/fails stress | US rates | Dealer Treasury positions, financing, fails-to-deliver/receive, inventory absorption. | Rates/curve event study and SPY/TLT drawdown context; likely confirmer. | Auction absorption, MOVE, term premium, repo/SOFR stress. | 10.05 |
| SLF-056 | Repo/SOFR tail stress | US funding | SOFR p99, repo specialness proxies, funding-tail z-score. | Forward drawdown AUC and event study; likely display/confirmer. | OFR FSI, NFCI, HY OAS, dealer inventory. | 10.4 |
| SLF-059 | EIA petroleum inventory surprise | Energy / commodities | Crude/gasoline/distillate seasonal-model error (inventory surprise not buildable free — API consensus is paywalled), refinery runs, days-of-supply. | CL/XLE/OIH event study using seasonal-model error only (no true consensus surprise); prior ruling: EIA inventory display-only; 38y carry phase-0 wrong-signed. | Oil trend, COT, dollar, seasonality, crack spreads. | 10.4 |

## Local Phase-0 queue

| ID | Candidate | Why not Fable yet | First empirical gate | Score |
|---|---|---|---|---|
| SLF-003 | Option informed-flow lens | sample | Event-window and 1d/5d/21d tests; require improvement over GEX baseline. | 9.6 |
| SLF-004 | EDGAR attention shock | score_threshold | Filing-day and post-filing drift; Brier if used as event-probability. | 9.55 |
| SLF-008 | Crypto funding + on-chain stress | score_threshold | Leave-one-cycle-out and DSR with explicit crypto trial ledger. | 9.4 |
| SLF-009 | Supply-chain pressure impulse | score_threshold | Sector-relative IC; no broad-risk claim unless it beats NFCI/OFR. | 9.65 |
| SLF-011 | FINRA ATS dark-flow imbalance | evidence | Weekly 5d/21d IC; require incremental lift vs RVOL and short-volume. | 10.0 |
| SLF-013 | Short-interest days-to-cover squeeze/informed-short split | score_threshold | Bi-monthly rebalance; separate high-short winners from high-short deteriorators. | 9.4 |
| SLF-016 | Dealer gamma flip migration | sample | Forward vol/drawdown calibration; scoring blocked until history grows. | 9.3 |
| SLF-017 | Option/stock volume ratio | sample | 1d/5d returns and event-news split; require single-name, not index-hedge, evidence. | 10.1 |
| SLF-018 | IV minus realized-vol spread | sample | Delta-hedged option returns where possible; equity confirmer only if stock-return IC appears. | 9.2 |
| SLF-021 | ETF creation-redemption pressure | score_threshold | Underlying basket IC and same-direction ETF-flow persistence. | 9.9 |
| SLF-022 | Sector ETF flow divergence | evidence | Sector-relative IC and drawdown-control overlay; likely confirmer. | 9.6 |
| SLF-023 | 13F crowded ownership unwind | score_threshold | Quarterly IC and drawdown risk; must beat current fund-crowding display row. | 9.2 |
| SLF-028 | Buyback authorization versus actual shrink | score_threshold | Forward IC only on actual shrink-confirmed authorizations; avoid headline-only bias. | 9.4 |
| SLF-029 | Secondary / ATM offering overhang | evidence | Event study from filing to completion; likely display/exclusion only. | 8.6 |
| SLF-030 | IPO lockup supply overhang | evidence | Reuse existing IPO-lockup Phase-0; only retest as exclusion overlay. | 8.4 |
| SLF-032 | 10-K risk-tone inflection | score_threshold | Filing-window and post-filing drift; reject if only crisis-coincident. | 9.15 |
| SLF-033 | MD&A boilerplate / similarity drift | score_threshold | Crash-risk and return-drift tests; likely risk-display unless IC survives. | 8.65 |
| SLF-036 | Analyst revision breadth | sample | Deep-history PIT audit; require incremental IC over existing stock-score revision axis. | 9.4 |
| SLF-040 | Asset-growth / net-operating-assets quality | score_threshold | Deep panel IC with HXZ controls; expect display unless incremental. | 9.7 |
| SLF-041 | R&D innovation intensity shock | evidence | Sector-relative IC; reject if it is just expensive-growth beta. | 9.1 |
| SLF-042 | Patent assignment / innovation shock | score_threshold | Event and 12m drift tests; biotech/tech separate from broad equity. | 9.55 |
| SLF-043 | Headcount disclosure shock | evidence | Forward operating repair and return IC; likely sector-specific confirmer. | 10.0 |
| SLF-044 | Clinical-trial transition catalyst | evidence | Event study by phase and sponsor materiality; likely healthcare-only. | 9.25 |
| SLF-045 | FDA shortage / disruption pressure | evidence | Event study; separate beneficiary read-through from issuer disruption. | 10.0 |
| SLF-046 | Government contract award surprise | evidence | Award-date and quarterly drift; require materiality and no look-ahead award edits. | 10.0 |
| SLF-047 | Federal grants / SAM procurement momentum | evidence | Theme-basket relative returns; likely display unless mapped to revenue exposure. | 10.0 |
| SLF-048 | Wikipedia attention shock | sample | Post-attention drift and reversal; distinguish informed attention from retail chase. | 10.3 |
| SLF-049 | GitHub developer momentum | evidence | Sector-specific IC; reject if mapping coverage too sparse. | 9.1 |
| SLF-052 | China limit-up breadth exhaustion | sample | Event and breadth IC; test revised momentum excluding limit-up days. | 10.3 |
| SLF-054 | HK short-turnover capitulation | evidence | Event buckets; likely bounce confirmer only. | 9.6 |
| SLF-057 | Net-liquidity impulse | evidence | Out-of-sample drawdown control; graveyard if it only tracks risk-on trend. | 8.9 |
| SLF-058 | Credit ETF flow versus HY-OAS divergence | score_threshold | Forward equity and credit drawdown tests; must beat existing HY-OAS timer. | 9.9 |
| SLF-060 | Stablecoin supply / exchange-liquidity impulse | evidence | BTC/ETH forward returns and drawdown tests with leave-one-cycle-out. | 9.5 |

## Data-contract queue

| ID | Candidate | Data path | Blockers | Source | Score |
|---|---|---|---|---|---|
| SLF-002 | Borrow-fee / loan-fee anomaly | DataLend/S3/IHS/IBKR-like PIT vendor history. | data_path, pit_plan | Engelberg et al. loan-fee anomaly | 7.6 |
| SLF-014 | Securities-lending utilization shock | Paid securities-lending vendor required. | data_path, pit_plan | Shorting-market demand literature | 7.6 |
| SLF-015 | Borrow recall / locate scarcity event | Paid prime/borrow data or broker snapshots. | data_path, pit_plan | Securities-lending literature | 6.8 |
| SLF-019 | Put-call parity deviation | Clean option quotes, borrow/dividend/rate inputs, bid-ask history. | data_path, pit_plan | Cremers/Weinbaum parity deviations | 6.8 |
| SLF-024 | Mutual-fund fire-sale pressure | N-PORT/CRSP mutual fund holdings and flows; not fully in repo. | data_path | Coval/Stafford fire sales | 9.85 |
| SLF-050 | China northbound flow / turnover impulse | Existing China Connect / flows collectors. | data_path | Stock Connect flow literature | 9.3 |

Note: SLF-050 has `data_state='blocked'` and `score=9.3 ≥ 6.5`, so `screen_candidate()` routes it to `data_contract_first` (blocked feed is treated as a data-contract barrier, not a prior-kill). The actual `graveyard_now` row is SLF-020 (prior_killed_level prior).

## Rejected / graveyard-now queue

| ID | Candidate | Verdict | Blockers | Reason note |
|---|---|---|---|---|
| SLF-020 | Skew term-structure kink | graveyard_now | novelty | prior_killed_level prior — already-killed SKEW/VIX-TS variants |
| SLF-037 | Analyst disagreement / dispersion | watchlist_or_reject | data_path, pit_plan |  |

## Full 60-candidate docket

| ID | Candidate | Family | Market | Data | PIT | Years | Verdict | Source |
|---|---|---|---|---|---|---|---|---|
| SLF-001 | SEC fails-to-deliver pressure | short-side | US equities | free_new | lagged | 22 | advance_to_fable | SEC FTD data; Stratmann/Welborn |
| SLF-002 | Borrow-fee / loan-fee anomaly | short-side | US equities | paid | paid_unknown | 18 | data_contract_first | Engelberg et al. loan-fee anomaly |
| SLF-003 | Option informed-flow lens | options | US options | partial | lagged | 4 | local_phase0_ready | Pan/Poteshman option volume |
| SLF-004 | EDGAR attention shock | attention | US filings | free_new | lagged | 5 | local_phase0_ready | SEC EDGAR logs; EDGAR attention literature |
| SLF-005 | Overnight/intraday tug-of-war | microstructure | US equities | ready | clean | 5 | advance_to_fable | Lou/Polk/Skouras overnight-intraday |
| SLF-006 | Treasury auction absorption | rates | US rates | ready | release_lag | 18 | advance_to_fable | TreasuryDirect auction query |
| SLF-007 | COT exhaustion matrix | positioning | Cross-asset futures | ready | release_lag | 30 | advance_to_fable | CFTC COT |
| SLF-008 | Crypto funding + on-chain stress | crypto | Crypto | partial | clean | 5 | local_phase0_ready | Coin Metrics community API |
| SLF-009 | Supply-chain pressure impulse | macro | Macro / sectors | free_new | release_lag | 25 | local_phase0_ready | NY Fed GSCPI |
| SLF-010 | Lottery/MAX anti-chase flag | price | US equities | ready | clean | 5 | advance_to_fable | Bali/Cakici/Whitelaw MAX |
| SLF-011 | FINRA ATS dark-flow imbalance | microstructure | US equities | ready | lagged | 10 | local_phase0_ready | FINRA OTC transparency |
| SLF-012 | FINRA short-volume stress | short-side | US equities | ready | lagged | 16 | advance_to_fable | FINRA short-sale volume data |
| SLF-013 | Short-interest days-to-cover squeeze/informed-short split | short-side | US equities | partial | lagged | 5 | local_phase0_ready | FINRA equity short interest |
| SLF-014 | Securities-lending utilization shock | short-side | US equities | paid | paid_unknown | 10 | data_contract_first | Shorting-market demand literature |
| SLF-015 | Borrow recall / locate scarcity event | short-side | US equities | paid | paid_unknown | 10 | data_contract_first | Securities-lending literature |
| SLF-016 | Dealer gamma flip migration | options | US options | partial | lagged | 2 | local_phase0_ready | CBOE / options GEX plumbing |
| SLF-017 | Option/stock volume ratio | options | US options | partial | lagged | 3 | local_phase0_ready | Johnson/So and option-flow literature |
| SLF-018 | IV minus realized-vol spread | options | US options | partial | lagged | 3 | local_phase0_ready | Goyal/Saretto RV-IV spread |
| SLF-019 | Put-call parity deviation | options | US options | paid | paid_unknown | 8 | data_contract_first | Cremers/Weinbaum parity deviations |
| SLF-020 | Skew term-structure kink | options | US volatility | ready | clean | 12 | graveyard_now | CBOE VIX term structure |
| SLF-021 | ETF creation-redemption pressure | flows | US ETFs / equities | ready | lagged | 5 | local_phase0_ready | ETF flow and price pressure literature |
| SLF-022 | Sector ETF flow divergence | flows | US sectors | ready | lagged | 5 | local_phase0_ready | ETF flow pressure literature |
| SLF-023 | 13F crowded ownership unwind | ownership | US equities | ready | lagged | 12 | local_phase0_ready | 13F ownership pressure |
| SLF-024 | Mutual-fund fire-sale pressure | flows | US equities | external_heavy | lagged | 15 | data_contract_first | Coval/Stafford fire sales |
| SLF-025 | Opportunistic insider cluster | insider | US equities | ready | lagged | 10 | advance_to_fable | Cohen/Malloy/Pomorski insiders |
| SLF-026 | Insider sponsorship after solvency repair | insider/fundamental | US equities | ready | lagged | 8 | advance_to_fable | Insider and repair literature |
| SLF-027 | Net issuance / dilution shock | fundamental | US equities | ready | lagged | 8 | advance_to_fable | Net issuance / asset-growth anomaly literature |
| SLF-028 | Buyback authorization versus actual shrink | capital return | US equities | partial | lagged | 8 | local_phase0_ready | Repurchase / payout factor literature |
| SLF-029 | Secondary / ATM offering overhang | supply | US equities | partial | lagged | 6 | local_phase0_ready | SEC filings / offering data |
| SLF-030 | IPO lockup supply overhang | supply | US equities | ready | lagged | 5 | local_phase0_ready | IPO lockup literature |
| SLF-031 | EDGAR lazy-prices text-change signal | text | US filings | free_new | lagged | 20 | advance_to_fable | Cohen/Malloy/Nguyen lazy prices |
| SLF-032 | 10-K risk-tone inflection | text | US filings | free_new | lagged | 20 | local_phase0_ready | Loughran-McDonald dictionary |
| SLF-033 | MD&A boilerplate / similarity drift | text | US filings | free_new | lagged | 15 | local_phase0_ready | Brown/Tucker MD&A similarity |
| SLF-034 | 8-K item taxonomy surprise | events | US filings | ready | lagged | 8 | advance_to_fable | SEC EDGAR APIs |
| SLF-035 | Guidance revision language | fundamental/text | US equities | ready | lagged | 6 | advance_to_fable | SEC guidance filings |
| SLF-036 | Analyst revision breadth | fundamental | US equities | ready | lagged | 1 | local_phase0_ready | Analyst revision literature |
| SLF-037 | Analyst disagreement / dispersion | fundamental | US equities | paid | paid_unknown | 10 | watchlist_or_reject | Disagreement literature |
| SLF-038 | Gross-margin inflection | quality | US equities | ready | lagged | 8 | advance_to_fable | Profitability anomaly literature |
| SLF-039 | Inventory build versus sales slowdown | quality | US equities | ready | lagged | 8 | advance_to_fable | Inventory/accrual anomaly literature |
| SLF-040 | Asset-growth / net-operating-assets quality | quality | US equities | ready | lagged | 8 | local_phase0_ready | Replicating Anomalies |
| SLF-041 | R&D innovation intensity shock | fundamental | US equities | ready | lagged | 8 | local_phase0_ready | Innovation/asset-pricing literature |
| SLF-042 | Patent assignment / innovation shock | innovation | US equities | free_new | lagged | 15 | local_phase0_ready | USPTO Open Data Portal |
| SLF-043 | Headcount disclosure shock | fundamental/text | US equities | ready | lagged | 6 | local_phase0_ready | SEC filings |
| SLF-044 | Clinical-trial transition catalyst | events | Healthcare | free_new | lagged | 10 | local_phase0_ready | ClinicalTrials.gov API |
| SLF-045 | FDA shortage / disruption pressure | events | Healthcare | ready | lagged | 8 | local_phase0_ready | FDA/openFDA data |
| SLF-046 | Government contract award surprise | policy/flow | US equities | ready | lagged | 8 | local_phase0_ready | USAspending API |
| SLF-047 | Federal grants / SAM procurement momentum | policy/flow | US equities | ready | lagged | 6 | local_phase0_ready | Grants.gov / SAM.gov |
| SLF-048 | Wikipedia attention shock | attention | US equities | ready | lagged | 1 | local_phase0_ready | Wikimedia Analytics API |
| SLF-049 | GitHub developer momentum | attention | Software / crypto | ready | lagged | 5 | local_phase0_ready | GitHub API |
| SLF-050 | China northbound flow / turnover impulse | flows | China A | blocked | lagged | 8 | data_contract_first | Stock Connect flow literature |
| SLF-051 | China margin-financing impulse | leverage | China A | ready | lagged | 8 | advance_to_fable | China margin trading literature |
| SLF-052 | China limit-up breadth exhaustion | market-structure | China A | ready | clean | 1 | local_phase0_ready | China up-limit overreaction literature |
| SLF-053 | A-H premium dislocation convergence | cross-listing | China / HK | ready | clean | 8 | advance_to_fable | Stock Connect / A-H premium literature |
| SLF-054 | HK short-turnover capitulation | short-side | Hong Kong | ready | lagged | 8 | local_phase0_ready | HKEX short-selling data |
| SLF-055 | Primary-dealer Treasury inventory/fails stress | funding/rates | US rates | free_new | lagged | 28 | advance_to_fable | NY Fed Primary Dealer Statistics |
| SLF-056 | Repo/SOFR tail stress | funding | US funding | ready | clean | 7 | advance_to_fable | OFR short-term funding monitor |
| SLF-057 | Net-liquidity impulse | liquidity | US macro | ready | release_lag | 15 | local_phase0_ready | FRED/Treasury liquidity data |
| SLF-058 | Credit ETF flow versus HY-OAS divergence | flows/credit | US credit | ready | lagged | 5 | local_phase0_ready | ETF flow / credit spread literature |
| SLF-059 | EIA petroleum inventory surprise | commodity | Energy / commodities | ready | release_lag | 20 | advance_to_fable | EIA weekly petroleum status |
| SLF-060 | Stablecoin supply / exchange-liquidity impulse | crypto/liquidity | Crypto | partial | clean | 5 | local_phase0_ready | Stablecoin and Coin Metrics data |

## Source anchors

- SEC FTD data; Stratmann/Welborn: https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data
- Engelberg et al. loan-fee anomaly: https://pubsonline.informs.org/doi/10.1287/mnsc.2023.00152
- Pan/Poteshman option volume: https://www.nber.org/papers/w10925
- SEC EDGAR logs; EDGAR attention literature: https://www.sec.gov/data-research/sec-markets-data/edgar-log-file-data-sets
- Lou/Polk/Skouras overnight-intraday: https://personal.lse.ac.uk/polk/research/TugOfWar.pdf
- TreasuryDirect auction query: https://www.treasurydirect.gov/auctions/auction-query/
- CFTC COT: https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm
- Coin Metrics community API: https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data
- NY Fed GSCPI: https://www.newyorkfed.org/research/policy/gscpi
- Bali/Cakici/Whitelaw MAX: https://pages.stern.nyu.edu/~rwhitela/papers/max%20jfe11.pdf
- FINRA OTC transparency: https://www.finra.org/filing-reporting/otc-transparency
- FINRA short-sale volume data: https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data
- FINRA equity short interest: https://www.finra.org/finra-data/browse-catalog/equity-short-interest
- Shorting-market demand literature: https://www.hbs.edu/faculty/Pages/item.aspx?num=31698
- CBOE / options GEX plumbing: https://www.cboe.com/tradable-products/vix/term-structure/
- Johnson/So and option-flow literature: https://cdi-icd.org/wp-content/uploads/2020/05/DR-20-03_Muravyev_Vasquez_Wang-1.pdf
- Goyal/Saretto RV-IV spread: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=889947
- Cremers/Weinbaum parity deviations: https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID968237_code254274.pdf?abstractid=968237&mirid=1&type=2
- ETF flow and price pressure literature: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1468382
- 13F ownership pressure: https://www.sec.gov/edgar/search-and-access
- Coval/Stafford fire sales: https://www.nber.org/system/files/working_papers/w11357/w11357.pdf
- Cohen/Malloy/Pomorski insiders: https://www.nber.org/papers/w16454
- Net issuance / asset-growth anomaly literature: https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a
- SEC filings / offering data: https://www.sec.gov/search-filings
- IPO lockup literature: reports/ipo-lockup-phase0.md
- Cohen/Malloy/Nguyen lazy prices: https://www.nber.org/system/files/working_papers/w25084/revisions/w25084.rev0.pdf
- Loughran-McDonald dictionary: https://sraf.nd.edu/loughranmcdonald-master-dictionary/
- Brown/Tucker MD&A similarity: https://www.stephenvbrown.com/publications/papers/annual-mda-modifications/
- SEC EDGAR APIs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Disagreement literature: https://diether.org/research.html
- USPTO Open Data Portal: https://data.uspto.gov/
- ClinicalTrials.gov API: https://clinicaltrials.gov/data-api
- FDA/openFDA data: https://open.fda.gov/apis/
- USAspending API: https://api.usaspending.gov/
- Grants.gov / SAM.gov: https://www.grants.gov/
- Wikimedia Analytics API: https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/
- GitHub API: https://docs.github.com/en/rest
- Stock Connect flow literature: https://www.hkex.com.hk/Mutual-Market/Connect-Hub/Stock-Connect?sc_lang=en
- China margin trading literature: https://ideas.repec.org/a/bla/acctfi/v65y2025i1p81-108.html
- China up-limit overreaction literature: https://www.sciencedirect.com/science/article/abs/pii/S0264999322001560
- HKEX short-selling data: https://www.hkex.com.hk/Market-Data/Securities-Prices/Short-Selling?sc_lang=en
- NY Fed Primary Dealer Statistics: https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics
- OFR short-term funding monitor: https://www.financialresearch.gov/short-term-funding-monitor/
- FRED/Treasury liquidity data: https://fred.stlouisfed.org/docs/api/fred/
- ETF flow / credit spread literature: https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- EIA weekly petroleum status: https://www.eia.gov/petroleum/supply/weekly/
