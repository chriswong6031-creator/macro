"""Expanded Signal Lab research docket and Phase-0 admission screen.

This is deliberately not a validation engine. It is the pre-registration docket
for deciding which hypotheses deserve a real empirical harness. A candidate can
advance here only if its data path, PIT treatment, baseline, sample, and
incremental thesis are explicit enough for Fable to challenge.
"""
from __future__ import annotations

from collections import Counter


def _c(cid, name, market, family, data_state, pit, history_years, literature,
       orthogonality, complexity, prior, feature, data_path, baseline, first_gate,
       source, source_url, expected_home="confirmer", note=""):
    return {
        "id": cid,
        "name": name,
        "market": market,
        "family": family,
        "data_state": data_state,
        "pit": pit,
        "history_years": history_years,
        "literature": literature,
        "orthogonality": orthogonality,
        "complexity": complexity,
        "prior": prior,
        "feature": feature,
        "data_path": data_path,
        "baseline": baseline,
        "first_gate": first_gate,
        "source": source,
        "source_url": source_url,
        "expected_home": expected_home,
        "note": note,
    }


CANDIDATES: list[dict] = [
    _c("SLF-001", "SEC fails-to-deliver pressure", "US equities", "short-side", "free_new", "lagged", 22, 3, 3, 2, "fresh",
       "FTD shares/float, FTD USD/ADV, rising FTD z-score.",
       "SEC half-month FTD files; new collector needed.",
       "Size, low price, liquidity, momentum, FINRA short volume.",
       "21d/63d rank-IC plus incremental IC after short-volume controls.",
       "SEC FTD data; Stratmann/Welborn", "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"),
    _c("SLF-002", "Borrow-fee / loan-fee anomaly", "US equities", "short-side", "paid", "paid_unknown", 18, 3, 3, 3, "fresh",
       "Daily borrow fee percentile, utilization, lendable supply, fee change.",
       "DataLend/S3/IHS/IBKR-like PIT vendor history.",
       "FTD, FINRA short interest, short volume, microcap and liquidity controls.",
       "Monthly high-fee underperformance and long-only exclusion value after costs.",
       "Engelberg et al. loan-fee anomaly", "https://pubsonline.informs.org/doi/10.1287/mnsc.2023.00152", "data-contract"),
    _c("SLF-003", "Option informed-flow lens", "US options", "options", "partial", "lagged", 4, 3, 3, 3, "extension",
       "Buyer-open put/call proxy, option/stock volume, IV spread, skew by delta/expiry.",
       "Existing options/GEX plumbing plus richer historical chain/flow store.",
       "GEX, 200dma, public put/call, scheduled-news controls.",
       "Event-window and 1d/5d/21d tests; require improvement over GEX baseline.",
       "Pan/Poteshman option volume", "https://www.nber.org/papers/w10925"),
    _c("SLF-004", "EDGAR attention shock", "US filings", "attention", "free_new", "lagged", 5, 2, 3, 3, "fresh",
       "Human filing views by ticker/form, stale-vs-fresh filing attention shock.",
       "SEC EDGAR log files; de-robot and join to filing index.",
       "Filing type, size, volatility, news, Google/Wikipedia attention proxies.",
       "Filing-day and post-filing drift; Brier if used as event-probability.",
       "SEC EDGAR logs; EDGAR attention literature", "https://www.sec.gov/data-research/sec-markets-data/edgar-log-file-data-sets"),
    _c("SLF-005", "Overnight/intraday tug-of-war", "US equities", "microstructure", "ready", "clean", 5, 3, 2, 1, "fresh",
       "Close-open and open-close return legs for existing factors and entries.",
       "Adjusted OHLC already present in price stores.",
       "Close-to-close signal, spread/impact estimates, volatility regime.",
       "Net-of-open-spread IC and split-half stability; no alpha claim unless tradable.",
       "Lou/Polk/Skouras overnight-intraday", "https://personal.lse.ac.uk/polk/research/TugOfWar.pdf"),
    _c("SLF-006", "Treasury auction absorption", "US rates", "rates", "ready", "release_lag", 18, 2, 3, 1, "extension",
       "Bid-to-cover z, indirect share, dealer takedown, issue size. (Auction tail struck — paid when-issued data required.)",
       "Existing Treasury auction collector and FiscalData/TreasuryDirect records.",
       "Term premium, MOVE, duration trend, same-tenor trailing auctions.",
       "Event study on TLT/IEF/curve; scoring barred unless pre-auction predictors work.",
       "TreasuryDirect auction query", "https://www.treasurydirect.gov/auctions/auction-query/"),
    _c("SLF-007", "COT exhaustion matrix", "Cross-asset futures", "positioning", "ready", "release_lag", 30, 2, 2, 1, "extension",
       "3y spec-position percentile, flow change, cross-asset crowding clusters.",
       "Existing CFTC COT store.",
       "Price trend, VIX/MOVE, existing capitulation legs.",
       "Forward returns after crowding extremes; confirm only if it beats dumb trend gates.",
       "CFTC COT", "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"),
    _c("SLF-008", "Crypto funding + on-chain stress", "Crypto", "crypto", "partial", "clean", 5, 2, 2, 2, "extension",
       "Perp funding extremes, OI/funding divergence, MVRV/realized-cap stress.",
       "Existing OKX/Coin Metrics/CheckOnChain pieces.",
       "BTC Vector raw engine, 200dma brake, ETF-flow legs.",
       "Leave-one-cycle-out and DSR with explicit crypto trial ledger.",
       "Coin Metrics community API", "https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data"),
    _c("SLF-009", "Supply-chain pressure impulse", "Macro / sectors", "macro", "free_new", "release_lag", 25, 2, 2, 1, "fresh",
       "GSCPI level/change/surprise mapped to inflation-sensitive sectors.",
       "NY Fed GSCPI spreadsheet/API pull.",
       "OFR/NFCI, breakevens, sector own trend.",
       "Sector-relative IC; no broad-risk claim unless it beats NFCI/OFR.",
       "NY Fed GSCPI", "https://www.newyorkfed.org/research/policy/gscpi"),
    _c("SLF-010", "Lottery/MAX anti-chase flag", "US equities", "price", "ready", "clean", 5, 2, 2, 1, "fresh",
       "Prior-month MAX, idiosyncratic skew, extreme one-day winner flag.",
       "Daily OHLC/returns already available.",
       "Momentum, size, liquidity, volatility, NYSE breakpoints.",
       "Liquid-universe IC; expect graveyard unless incremental after HXZ controls.",
       "Bali/Cakici/Whitelaw MAX", "https://pages.stern.nyu.edu/~rwhitela/papers/max%20jfe11.pdf", "graveyard-or-confirmer"),
    _c("SLF-011", "FINRA ATS dark-flow imbalance", "US equities", "microstructure", "ready", "lagged", 10, 1, 3, 2, "fresh",
       "ATS share of volume, ATS average trade size, non-ATS off-exchange share shock.",
       "Existing FINRA ATS/OTC transparency collector candidates.",
       "Total volume, market cap, short volume, volatility, liquidity.",
       "Weekly 5d/21d IC; require incremental lift vs RVOL and short-volume.",
       "FINRA OTC transparency", "https://www.finra.org/filing-reporting/otc-transparency"),
    _c("SLF-012", "FINRA short-volume stress", "US equities", "short-side", "ready", "lagged", 16, 2, 2, 1, "extension",
       "Short-volume ratio shock crossed with price strength/weakness and borrow proxies.",
       "Existing FINRA short-volume collector.",
       "Price momentum/reversal, FTD, size, liquidity.",
       "Cross-sectional IC and event buckets; never score unless it beats FTD/borrow proxies.",
       "FINRA short-sale volume data", "https://www.finra.org/finra-data/browse-catalog/short-sale-volume-data",
       note="Off-exchange-only coverage (non-ATS excluded); short-ratio denominator is non-stationary as off-exchange share drifted up over the sample. Use 2018+ backfill as control store for SLF-001 only."),
    _c("SLF-013", "Short-interest days-to-cover squeeze/informed-short split", "US equities", "short-side", "partial", "lagged", 5, 2, 2, 2, "extension",
       "Days-to-cover level and change, split into squeeze-risk vs informed-short baskets.",
       "FINRA short-interest collector, but PIT depth and identifier drift must be audited.",
       "FTD, short volume, borrow fee if available, momentum.",
       "Bi-monthly rebalance; separate high-short winners from high-short deteriorators.",
       "FINRA equity short interest", "https://www.finra.org/finra-data/browse-catalog/equity-short-interest"),
    _c("SLF-014", "Securities-lending utilization shock", "US equities", "short-side", "paid", "paid_unknown", 10, 3, 3, 3, "fresh",
       "Utilization spike, lendable supply collapse, rebate deterioration.",
       "Paid securities-lending vendor required.",
       "Loan fee, short interest, FTD, size/liquidity.",
       "Must add unique IC over loan-fee level and survive cost/capacity curves.",
       "Shorting-market demand literature", "https://www.hbs.edu/faculty/Pages/item.aspx?num=31698", "data-contract"),
    _c("SLF-015", "Borrow recall / locate scarcity event", "US equities", "short-side", "paid", "paid_unknown", 10, 2, 3, 3, "fresh",
       "Hard-to-borrow flags, recall events, locate failures.",
       "Paid prime/borrow data or broker snapshots.",
       "Borrow fee, FTD, short interest.",
       "Event study around recall/locate shock; likely short-exclusion tool.",
       "Securities-lending literature", "https://www.hbs.edu/faculty/Pages/item.aspx?num=31698", "data-contract"),
    _c("SLF-016", "Dealer gamma flip migration", "US options", "options", "partial", "lagged", 2, 2, 3, 2, "extension",
       "Distance-to-flip, flip migration speed, net-GEX sign stability.",
       "Existing GEX plumbing; history still accruing.",
       "SPY 200dma, realized vol, VIX term structure.",
       "Forward vol/drawdown calibration; scoring blocked until history grows.",
       "CBOE / options GEX plumbing", "https://www.cboe.com/tradable-products/vix/term-structure/"),
    _c("SLF-017", "Option/stock volume ratio", "US options", "options", "partial", "lagged", 3, 3, 3, 2, "fresh",
       "O/S volume ratio by ticker, direction by put/call and delta bucket.",
       "Polygon/ThetaData/options-flow history.",
       "Equity volume, GEX, IV spread, scheduled events.",
       "1d/5d returns and event-news split; require single-name, not index-hedge, evidence.",
       "Johnson/So and option-flow literature", "https://cdi-icd.org/wp-content/uploads/2020/05/DR-20-03_Muravyev_Vasquez_Wang-1.pdf"),
    _c("SLF-018", "IV minus realized-vol spread", "US options", "options", "partial", "lagged", 3, 3, 2, 2, "fresh",
       "ATM IV minus trailing realized volatility; straddle-rich/cheap cross-section.",
       "Options history plus OHLC realized-vol store.",
       "GEX, volatility regime, earnings calendar, liquidity.",
       "Delta-hedged option returns where possible; equity confirmer only if stock-return IC appears.",
       "Goyal/Saretto RV-IV spread", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=889947"),
    _c("SLF-019", "Put-call parity deviation", "US options", "options", "paid", "paid_unknown", 8, 2, 3, 3, "fresh",
       "Synthetic stock mispricing from put-call parity violations.",
       "Clean option quotes, borrow/dividend/rate inputs, bid-ask history.",
       "Borrow fee, short-sale constraints, IV spread.",
       "Only advance with transaction-cost-aware parity construction.",
       "Cremers/Weinbaum parity deviations", "https://papers.ssrn.com/sol3/Delivery.cfm/SSRN_ID968237_code254274.pdf?abstractid=968237&mirid=1&type=2", "data-contract"),
    _c("SLF-020", "Skew term-structure kink", "US volatility", "options", "ready", "clean", 12, 1, 2, 1, "prior_killed_level",
       "VIX9D/VIX/VIX3M/VIX6M curve kink, not raw SKEW level.",
       "CBOE index history.",
       "VIX term structure, realized vol, SPY trend.",
       "Treat as graveyard unless kink beats already-killed SKEW and VIX-TS variants.",
       "CBOE VIX term structure", "https://www.cboe.com/tradable-products/vix/term-structure/", "graveyard"),
    _c("SLF-021", "ETF creation-redemption pressure", "US ETFs / equities", "flows", "ready", "lagged", 5, 2, 2, 2, "fresh",
       "Daily shares-outstanding delta times NAV, normalized by underlying liquidity.",
       "Existing ETF holdings/share outstanding flow store.",
       "Sector momentum, market beta, ETF AUM, index rebalance windows.",
       "Underlying basket IC and same-direction ETF-flow persistence.",
       "ETF flow and price pressure literature", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1468382"),
    _c("SLF-022", "Sector ETF flow divergence", "US sectors", "flows", "ready", "lagged", 5, 1, 2, 1, "extension",
       "Sector flow thrust when price trend is weak, or outflow washout while breadth improves.",
       "Existing sector ETF flow plus sector breadth.",
       "Sector momentum, relative strength, breadth, macro regime.",
       "Sector-relative IC and drawdown-control overlay; likely confirmer.",
       "ETF flow pressure literature", "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1468382"),
    _c("SLF-023", "13F crowded ownership unwind", "US equities", "ownership", "ready", "lagged", 12, 2, 2, 2, "settled_display",
       "Super-investor/common-holder concentration, crowding change, overlap clusters.",
       "Existing EDGAR 13F/smart-money store.",
       "Size, quality, momentum, sector, prior fund-crowding row.",
       "Quarterly IC and drawdown risk; must beat current fund-crowding display row.",
       "13F ownership pressure", "https://www.sec.gov/edgar/search-and-access"),
    _c("SLF-024", "Mutual-fund fire-sale pressure", "US equities", "flows", "external_heavy", "lagged", 15, 3, 3, 3, "fresh",
       "Projected stock-level selling pressure from fund outflows and overlapping holdings.",
       "N-PORT/CRSP mutual fund holdings and flows; not fully in repo.",
       "Momentum, size, liquidity, 13F crowding.",
       "Reversal after forced-selling buckets; capacity and liquidity gates required.",
       "Coval/Stafford fire sales", "https://www.nber.org/system/files/working_papers/w11357/w11357.pdf", "data-contract"),
    _c("SLF-025", "Opportunistic insider cluster", "US equities", "insider", "ready", "lagged", 10, 3, 3, 2, "extension",
       "Non-routine insider buys, cluster buys, role-weighted net USD/market cap.",
       "Existing SEC Form 4 insider store.",
       "Current insider row, size, liquidity, value, post-drawdown state.",
       "Incremental IC over current insider factor; routine-trader filter required.",
       "Cohen/Malloy/Pomorski insiders", "https://www.nber.org/papers/w16454"),
    _c("SLF-026", "Insider sponsorship after solvency repair", "US equities", "insider/fundamental", "ready", "lagged", 8, 2, 3, 2, "fresh",
       "Insider buying after balance-sheet and cash-flow repair, not generic dip-buying.",
       "SEC insiders plus fundamentals panel.",
       "Insider buying alone, value, leverage, momentum.",
       "Cross-sectional IC and bottom-rebound event buckets.",
       "Insider and repair literature", "https://www.nber.org/papers/w16454"),
    _c("SLF-027", "Net issuance / dilution shock", "US equities", "fundamental", "ready", "lagged", 8, 2, 3, 2, "fresh",
       "Share-count growth, ATM/convertible/securities issuance, dilution acceleration.",
       "Existing EDGAR dilution collector.",
       "Size, momentum, asset growth, profitability, sector financing windows.",
       "Monthly IC and exclusion value for long-only board.",
       "Net issuance / asset-growth anomaly literature", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a"),
    _c("SLF-028", "Buyback authorization versus actual shrink", "US equities", "capital return", "partial", "lagged", 8, 2, 2, 2, "fresh",
       "Announced buybacks filtered by subsequent diluted-share shrink and cash capacity.",
       "EDGAR filings, dilution/share-count store, news/special situations.",
       "Payout factor, net issuance, quality, leverage.",
       "Forward IC only on actual shrink-confirmed authorizations; avoid headline-only bias.",
       "Repurchase / payout factor literature", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a"),
    _c("SLF-029", "Secondary / ATM offering overhang", "US equities", "supply", "partial", "lagged", 6, 1, 2, 2, "fresh",
       "Shelf/ATM/equity offering filings, overhang size versus ADV and market cap.",
       "Special situations and EDGAR filing collectors.",
       "Dilution factor, momentum, liquidity.",
       "Event study from filing to completion; likely display/exclusion only.",
       "SEC filings / offering data", "https://www.sec.gov/search-filings"),
    _c("SLF-030", "IPO lockup supply overhang", "US equities", "supply", "ready", "lagged", 5, 1, 2, 2, "settled_display",
       "Lockup expiry date, float unlock size, borrow availability, momentum into expiry.",
       "Existing IPO calendar / lockup phase0 harness.",
       "IPO age, float, momentum, volume.",
       "Reuse existing IPO-lockup Phase-0; only retest as exclusion overlay.",
       "IPO lockup literature", "reports/ipo-lockup-phase0.md", "display"),
    _c("SLF-031", "EDGAR lazy-prices text-change signal", "US filings", "text", "free_new", "lagged", 20, 3, 3, 3, "fresh",
       "Year-over-year 10-K/10-Q textual change and neglected section deltas.",
       "SEC filings plus LM/cleaned 10-X summaries; new text pipeline.",
       "Filing tone, size, volatility, post-filing drift, EDGAR attention.",
       "Post-filing 21/63/126d IC; require incremental edge over tone and attention.",
       "Cohen/Malloy/Nguyen lazy prices", "https://www.nber.org/system/files/working_papers/w25084/revisions/w25084.rev0.pdf"),
    _c("SLF-032", "10-K risk-tone inflection", "US filings", "text", "free_new", "lagged", 20, 2, 2, 2, "fresh",
       "LM negative/uncertainty/litigious tone changes in risk factors and MD&A.",
       "LM dictionary and SEC 10-X summaries.",
       "Text length, sector, size, filing lag, prior returns.",
       "Filing-window and post-filing drift; reject if only crisis-coincident.",
       "Loughran-McDonald dictionary", "https://sraf.nd.edu/loughranmcdonald-master-dictionary/"),
    _c("SLF-033", "MD&A boilerplate / similarity drift", "US filings", "text", "free_new", "lagged", 15, 2, 2, 3, "fresh",
       "Cosine similarity and boilerplate increase after large operating change.",
       "SEC filing text pipeline.",
       "10-K risk tone, firm operating changes, sector, size.",
       "Crash-risk and return-drift tests; likely risk-display unless IC survives.",
       "Brown/Tucker MD&A similarity", "https://www.stephenvbrown.com/publications/papers/annual-mda-modifications/"),
    _c("SLF-034", "8-K item taxonomy surprise", "US filings", "events", "ready", "lagged", 8, 2, 3, 2, "fresh",
       "Item-level 8-K surprise clusters, filing-time abnormal volume, stale vs fresh attention.",
       "Existing EDGAR 8-K / earnings 8-K collectors.",
       "Event calendar, earnings, news sentiment, volatility.",
       "Event-window abnormal returns and post-event drift by item family.",
       "SEC EDGAR APIs", "https://www.sec.gov/search-filings/edgar-application-programming-interfaces"),
    _c("SLF-035", "Guidance revision language", "US equities", "fundamental/text", "ready", "lagged", 6, 2, 3, 2, "fresh",
       "Guidance raise/cut, uncertainty language, management narrowing/widening.",
       "Existing EDGAR guidance collector.",
       "Analyst revisions, SUE, earnings date, sector.",
       "Forward IC and event drift; must beat analyst revision breadth.",
       "SEC guidance filings", "https://www.sec.gov/search-filings"),
    _c("SLF-036", "Analyst revision breadth", "US equities", "fundamental", "ready", "lagged", 1, 2, 2, 1, "extension",
       "Up/down estimate revision breadth and acceleration by ticker/sector.",
       "Existing equity_revisions/fundamentals revision proxy.",
       "SUE, momentum, quality, sector trend.",
       "Deep-history PIT audit; require incremental IC over existing stock-score revision axis.",
       "Analyst revision literature", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a"),
    _c("SLF-037", "Analyst disagreement / dispersion", "US equities", "fundamental", "paid", "paid_unknown", 10, 2, 2, 2, "fresh",
       "Estimate dispersion, target-price disagreement, revision disagreement.",
       "IBES/FactSet/Starmine-like paid history likely required.",
       "Size, liquidity, analyst coverage, short interest.",
       "Cross-sectional IC and interaction with short-sale constraints.",
       "Disagreement literature", "https://diether.org/research.html", "data-contract"),
    _c("SLF-038", "Gross-margin inflection", "US equities", "quality", "ready", "lagged", 8, 2, 2, 1, "fresh",
       "Gross margin acceleration and recovery from trough, sector-relative.",
       "Existing fundamentals panel.",
       "Profitability, value, revisions, industry trend.",
       "Quarterly PIT IC; reject if subsumed by profitability/revisions.",
       "Profitability anomaly literature", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a"),
    _c("SLF-039", "Inventory build versus sales slowdown", "US equities", "quality", "ready", "lagged", 8, 2, 2, 1, "fresh",
       "Inventory growth minus sales growth, adjusted by industry seasonality.",
       "Existing fundamentals panel.",
       "Accruals, asset growth, margins, sector.",
       "Quarterly IC; must show negative forward edge outside retailers/energy quirks.",
       "Inventory/accrual anomaly literature", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a"),
    _c("SLF-040", "Asset-growth / net-operating-assets quality", "US equities", "quality", "ready", "lagged", 8, 2, 2, 1, "factor_zoo",
       "Asset growth, net operating assets, working-capital investment intensity.",
       "Existing fundamentals panel.",
       "Value, profitability, accruals, size.",
       "Deep panel IC with HXZ controls; expect display unless incremental.",
       "Replicating Anomalies", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a", "graveyard-or-display"),
    _c("SLF-041", "R&D innovation intensity shock", "US equities", "fundamental", "ready", "lagged", 8, 1, 2, 2, "fresh",
       "R&D/sales acceleration, capitalized software/intangible growth, margin context.",
       "Existing fundamentals panel.",
       "Growth, profitability, sector, size, valuation.",
       "Sector-relative IC; reject if it is just expensive-growth beta.",
       "Innovation/asset-pricing literature", "https://academic.oup.com/rfs/advance-article/doi/10.1093/rfs/hhy131/5236964?guestAccessKey=7fd97e02-18ad-4e38-aec9-44cac1b9f75a"),
    _c("SLF-042", "Patent assignment / innovation shock", "US equities", "innovation", "free_new", "lagged", 15, 2, 3, 3, "fresh",
       "Patent grants/assignments/citations mapped to public tickers and sector peers.",
       "USPTO Open Data Portal; identifier mapping required.",
       "R&D intensity, size, industry, momentum.",
       "Event and 12m drift tests; biotech/tech separate from broad equity.",
       "USPTO Open Data Portal", "https://data.uspto.gov/"),
    _c("SLF-043", "Headcount disclosure shock", "US equities", "fundamental/text", "ready", "lagged", 6, 1, 3, 2, "fresh",
       "Employee-count change, hiring freeze language, layoff disclosure extracted from filings.",
       "Existing EDGAR headcount collector.",
       "Revenue growth, margins, sector, macro labor state.",
       "Forward operating repair and return IC; likely sector-specific confirmer.",
       "SEC filings", "https://www.sec.gov/search-filings"),
    _c("SLF-044", "Clinical-trial transition catalyst", "Healthcare", "events", "free_new", "lagged", 10, 1, 3, 2, "fresh",
       "Trial phase transition, completion, termination, results-posting delays by sponsor/ticker.",
       "ClinicalTrials.gov API plus sponsor-to-ticker mapping.",
       "Market cap, pipeline breadth, FDA calendar, volatility.",
       "Event study by phase and sponsor materiality; likely healthcare-only.",
       "ClinicalTrials.gov API", "https://clinicaltrials.gov/data-api"),
    _c("SLF-045", "FDA shortage / disruption pressure", "Healthcare", "events", "ready", "lagged", 8, 1, 3, 2, "fresh",
       "Drug/device shortage starts/resolutions mapped to manufacturers and competitors.",
       "Existing FDA shortage/openFDA collectors.",
       "Healthcare subsector, revenue exposure, news sentiment.",
       "Event study; separate beneficiary read-through from issuer disruption.",
       "FDA/openFDA data", "https://open.fda.gov/apis/"),
    _c("SLF-046", "Government contract award surprise", "US equities", "policy/flow", "ready", "lagged", 8, 1, 3, 2, "fresh",
       "USAspending award amount surprise normalized by revenue/market cap.",
       "Existing USAspending collector or API.",
       "Defense/industrial sector trend, backlog, news.",
       "Award-date and quarterly drift; require materiality and no look-ahead award edits.",
       "USAspending API", "https://api.usaspending.gov/"),
    _c("SLF-047", "Federal grants / SAM procurement momentum", "US equities", "policy/flow", "ready", "lagged", 6, 1, 3, 2, "fresh",
       "Grant and procurement award velocity by theme and likely beneficiary.",
       "Existing grants_gov/SAM.gov collectors.",
       "USAspending awards, sector trend, policy theme.",
       "Theme-basket relative returns; likely display unless mapped to revenue exposure.",
       "Grants.gov / SAM.gov", "https://www.grants.gov/"),
    _c("SLF-048", "Wikipedia attention shock", "US equities", "attention", "ready", "lagged", 1, 2, 3, 1, "fresh",
       "Ticker/product/company pageview z-score, stale-vs-news-adjusted attention.",
       "Existing Wikimedia pageviews collector.",
       "News sentiment, EDGAR attention, volume, volatility, size.",
       "Post-attention drift and reversal; distinguish informed attention from retail chase.",
       "Wikimedia Analytics API", "https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/"),
    _c("SLF-049", "GitHub developer momentum", "Software / crypto", "attention", "ready", "lagged", 5, 1, 2, 2, "fresh",
       "Stars/forks/commit velocity for repo-linked public software companies or crypto projects.",
       "Existing GitHub repos collector; ticker mapping is hard.",
       "Wikipedia/news attention, price momentum, sector beta.",
       "Sector-specific IC; reject if mapping coverage too sparse.",
       "GitHub API", "https://docs.github.com/en/rest"),
    _c("SLF-050", "China northbound flow / turnover impulse", "China A", "flows", "blocked", "lagged", 8, 2, 3, 1, "fresh",
       "Northbound net buy as share of turnover, persistence, and flow exhaustion by stock/sector.",
       "Existing China Connect / flows collectors.",
       "CSI trend, sector momentum, RMB, global risk, valuation.",
       "Stock/sector IC and reversal-after-crowding tests.",
       "Stock Connect flow literature", "https://www.hkex.com.hk/Mutual-Market/Connect-Hub/Stock-Connect?sc_lang=en",
       note="Feed dead: HKEX ended daily northbound net-buy disclosure 2024-08 (NORTHBOUND_FROZEN='2024-08-16' in engine/flow_velocity.py). Net columns null since 2024-08-19. Graveyard; deep-discount blocks already wired as replacement."),
    _c("SLF-051", "China margin-financing impulse", "China A", "leverage", "ready", "lagged", 8, 2, 2, 1, "fresh",
       "Margin balance acceleration, sector concentration, margin/turnover ratio.",
       "Existing China margin collectors.",
       "Turnover, valuation, northbound flow, policy tone.",
       "Forward IC and crash-risk test; separate informed leverage from sentiment leverage.",
       "China margin trading literature", "https://ideas.repec.org/a/bla/acctfi/v65y2025i1p81-108.html"),
    _c("SLF-052", "China limit-up breadth exhaustion", "China A", "market-structure", "ready", "clean", 1, 2, 3, 1, "fresh",
       "Limit-up count, failed limit-up, consecutive boards, post-limit reversal pressure.",
       "Existing China zt_pool / limit-up collectors.",
       "Turnover, index trend, northbound flow, policy tone.",
       "Event and breadth IC; test revised momentum excluding limit-up days.",
       "China up-limit overreaction literature", "https://www.sciencedirect.com/science/article/abs/pii/S0264999322001560"),
    _c("SLF-053", "A-H premium dislocation convergence", "China / HK", "cross-listing", "ready", "clean", 8, 2, 2, 1, "extension",
       "Pair-level A-H premium z-score, flow gating, currency stress.",
       "Existing HK A-H panel.",
       "Southbound/northbound flow, CNH basis, market regime.",
       "Pair convergence IC; forbid broad-market claim unless portfolio construction works.",
       "Stock Connect / A-H premium literature", "https://www.hkex.com.hk/Mutual-Market/Connect-Hub/Stock-Connect?sc_lang=en"),
    _c("SLF-054", "HK short-turnover capitulation", "Hong Kong", "short-side", "ready", "lagged", 8, 1, 2, 1, "fresh",
       "HK short turnover spike crossed with drawdown, southbound support, and borrow proxies.",
       "Existing HK shorts collector.",
       "Global beta, HK residual alpha, southbound flow, liquidity.",
       "Event buckets; likely bounce confirmer only.",
       "HKEX short-selling data", "https://www.hkex.com.hk/Market-Data/Securities-Prices/Short-Selling?sc_lang=en"),
    _c("SLF-055", "Primary-dealer Treasury inventory/fails stress", "US rates", "funding/rates", "free_new", "lagged", 28, 2, 3, 2, "fresh",
       "Dealer Treasury positions, financing, fails-to-deliver/receive, inventory absorption.",
       "NY Fed Primary Dealer Statistics; OFR mirror possible.",
       "Auction absorption, MOVE, term premium, repo/SOFR stress.",
       "Rates/curve event study and SPY/TLT drawdown context; likely confirmer.",
       "NY Fed Primary Dealer Statistics", "https://www.newyorkfed.org/markets/counterparties/primary-dealers-statistics"),
    _c("SLF-056", "Repo/SOFR tail stress", "US funding", "funding", "ready", "clean", 7, 2, 2, 1, "extension",
       "SOFR p99, repo specialness proxies, funding-tail z-score.",
       "Existing OFR short-term funding monitor collector.",
       "OFR FSI, NFCI, HY OAS, dealer inventory.",
       "Forward drawdown AUC and event study; likely display/confirmer.",
       "OFR short-term funding monitor", "https://www.financialresearch.gov/short-term-funding-monitor/"),
    _c("SLF-057", "Net-liquidity impulse", "US macro", "liquidity", "ready", "release_lag", 15, 1, 2, 1, "crowded",
       "Fed balance sheet minus TGA/RRP impulse, flow windows, tax-date drains.",
       "Existing FRED/Treasury/RRP series.",
       "SPY trend, HY OAS, VIX, seasonality, rates.",
       "Out-of-sample drawdown control; graveyard if it only tracks risk-on trend.",
       "FRED/Treasury liquidity data", "https://fred.stlouisfed.org/docs/api/fred/"),
    _c("SLF-058", "Credit ETF flow versus HY-OAS divergence", "US credit", "flows/credit", "ready", "lagged", 5, 2, 2, 2, "fresh",
       "HYG/LQD/EMB flow thrust or outflow stress versus spread move.",
       "ETF flow store plus FRED HY/OAS.",
       "HY OAS z, credit SMA, equity trend, rates.",
       "Forward equity and credit drawdown tests; must beat existing HY-OAS timer.",
       "ETF flow / credit spread literature", "https://fred.stlouisfed.org/series/BAMLH0A0HYM2"),
    _c("SLF-059", "EIA petroleum inventory surprise", "Energy / commodities", "commodity", "ready", "release_lag", 20, 2, 2, 1, "fresh",
       "Crude/gasoline/distillate seasonal-model error (inventory surprise not buildable free — API consensus is paywalled), refinery runs, days-of-supply.",
       "Existing EIA collector and weekly petroleum report data.",
       "Oil trend, COT, dollar, seasonality, crack spreads.",
       "CL/XLE/OIH event study using seasonal-model error only (no true consensus surprise); prior ruling: EIA inventory display-only; 38y carry phase-0 wrong-signed.",
       "EIA weekly petroleum status", "https://www.eia.gov/petroleum/supply/weekly/"),
    _c("SLF-060", "Stablecoin supply / exchange-liquidity impulse", "Crypto", "crypto/liquidity", "partial", "clean", 5, 1, 3, 2, "fresh",
       "Stablecoin market-cap impulse, exchange reserves if available, ETF-flow interaction.",
       "DefiLlama quarantine stablecoins plus Coin Metrics / Farside flows.",
       "BTC Vector, funding, OI, macro liquidity.",
       "BTC/ETH forward returns and drawdown tests with leave-one-cycle-out.",
       "Stablecoin and Coin Metrics data", "https://gitbook-docs.coinmetrics.io/packages/coin-metrics-community-data"),
]


DATA_PASS = {"ready", "partial", "free_new"}
PIT_PASS = {"clean", "lagged", "release_lag"}

# ---------------------------------------------------------------------------
# Fable adjudication verdicts (2026-07-06) — display metadata ONLY.
# These do NOT feed any score; they annotate the frontier panel for transparency.
# Source: research/SIGNAL_LAB_FRONTIER_FABLE_ADJUDICATION_2026-07-06.md
# ---------------------------------------------------------------------------
# Covered IDs = the 23 original advance_to_fable candidates.
FABLE_VERDICTS: dict[str, dict] = {
    # KILLED (11) — duplicates, prior kills, dead feeds, or ruling-blocked
    "SLF-005": {"verdict": "KILLED", "note": "Ruling-blocked (Signal Commons price-memory → EI P1.3); data also fails: massive_stock_day is 5y rolling with unadjusted opens."},
    "SLF-007": {"verdict": "KILLED", "note": "Cross-asset matrix shape illegal per Signal Commons R3; single-ingredient COT leg already in esx_pos_reset (ESX A2) and capitulation gauge."},
    "SLF-010": {"verdict": "KILLED", "note": "Prior kill (China MAX NO-GO); US lottery penalty already live in engine/stock_score.py; F3 anti-chase is the production gate."},
    "SLF-012": {"verdict": "KILLED", "note": "FINRA short-volume confirmer already live (engine/short_volume.py); off-exchange-only with non-stationary denominator — structurally biased as standalone."},
    "SLF-025": {"verdict": "KILLED", "note": "ESX A2 ran exactly this (opportunistic net_usd_mcap≥p80 filter) 2026-07-05: unconditional strata adverse, opportunistic filter null/adverse."},
    "SLF-027": {"verdict": "KILLED", "note": "net_issuance is an existing signal_factory leg; edgar_dilution tripwires live; investment factor FDR-killed. Residual = conditional pairlet behind SLF-038."},
    "SLF-034": {"verdict": "KILLED", "note": "Duplicate: eightk_velocity (material-8K Poisson surprise z) is an existing factor leg; Special Situations desk runs 16-category 8-K taxonomy in nightly production."},
    "SLF-035": {"verdict": "KILLED", "note": "Duplicate: engine/guidance_gap.py (Foresight T3) already computes RAISING/CUTTING bands; store has 9 rows across 7 tickers — nothing to backtest."},
    "SLF-039": {"verdict": "KILLED", "note": "Inventory exists only in annual statements at 55% coverage; quarterly construction impossible from EDGAR crawl; adjacent Sloan accruals factor FDR-killed."},
    "SLF-050": {"verdict": "KILLED", "note": "Feed dead: HKEX ended daily northbound net-buy disclosure 2024-08 (NORTHBOUND_FROZEN='2024-08-16' in engine/flow_velocity.py); aggregate timing IC ≈ dead."},
    "SLF-059": {"verdict": "KILLED", "note": "Surprise not buildable free (API bulletin is paywalled); EIA inventory already display-only by ruling; 38y carry phase-0 killed wrong-signed."},
    # ROUTED (1)
    "SLF-026": {"verdict": "ROUTED", "note": "ESX Amendment 2 reserve docket — distinct conditioning, genuinely untested, but ESX A2's 2-trial reserve is the only legal entry point for new insider strata."},
    # ACCRUING (1)
    "SLF-036": {"verdict": "ACCRUE", "note": "Come back ≥2027-01-15: equity_revisions store began 2026-06-16 (~12 daily snapshots), no PIT history to backtest; forward store accruing the right fields."},
    # QUEUED (1)
    "SLF-038": {"verdict": "QUEUED", "note": "Legitimate pairlet on statements_quarterly (2009+, PIT via filed date); runs when factor-family budget opens — not a frontier family."},
    # TESTED — W1 phase-0 results (2026-07-06). 'tested' verdicts append to BUILD;
    # they do NOT overwrite history. Source: reports/slf*-phase0.md.
    "SLF-001": {"verdict": "TESTED-NULL(G3)", "note": "SEC FTD collector built; 22M-row panel live. Phase-0: all 6 variants null at 21/63d (rank-IC ≈ 0, none survive BH-FDR). G3 confound confirmed: T+30 lag concentrates at quarter-end + redemption cycles. Panel ships for sector-level tracking; signal barred.",
                "phase0_report": "reports/slf001-sec-ftd-phase0.md"},
    "SLF-006": {"verdict": "TESTED-NULL", "note": "Event-study of treasury_supply.absorption_z: 12 tested variants (belly/front/long, 1/5/21d, quintile-contrast/continuous-IC). All null. Auction tail leg struck (paid when-issued required). No engine change.",
                "phase0_report": "reports/slf006-auction-absorption-phase0.md"},
    "SLF-048": {"verdict": "TESTED-NULL", "note": "Wikipedia attention backfill 2015-07→2026 (966 tickers). Phase-0: attention z-shock predicts neither fade nor confirm direction at 5/21d in any cap tercile. Pre-registered fade gate not met. Backfill ships; signal display-only.",
                "phase0_report": "reports/slf048-wiki-attention-phase0.md"},
    "SLF-051": {"verdict": "TESTED-NULL", "note": "China margin ROC impulse: 8 trials (4 signals × 2 horizons), all null at 21/63d on CSI300_ETF_510300. De-escalation/conditioning framing confirmed wrong-ruler; market-level null holds across 2015 crisis.",
                "phase0_report": "reports/slf051-cn-margin-impulse-phase0.md"},
    "SLF-053": {"verdict": "TESTED-ACCRUE", "note": "A/H premium dislocation: 25-pair panel 2001→2026 (hk_canada_h3 family, 11 trial rows). Phase-0 shows spreads and pairlet structure viable; directional gate requires further accrual under HK/Canada program clock.",
                "phase0_report": "reports/hk-canada-h3-phase0.md"},
    "SLF-055": {"verdict": "TESTED-PARTIAL", "note": "NY Fed PD data built (1998→, weekly, era-aware). Phase-0: z-score legs partially signal vs MOVE/term-slope at TLT horizon (T3 alignment undefined → skipped). 15 trial rows. De-escalation candidacy partial; T3 gate deferred.",
                "phase0_report": "reports/slf055-dealer-stress-phase0.md"},
    "SLF-056": {"verdict": "TESTED-PASS", "note": "Repo/SOFR p99-dispersion AUC 0.61 vs SPY ≥5% drawdown at 21d; LOO-stable; beats VIX baseline. Promoted to confirmer tier (display-only). De-escalation panel candidacy pending program review.",
                "phase0_report": "reports/slf056-funding-tail-phase0.md"},
    # AUTHORIZED — PROBE (1) → result: ACCRUE-CONFIRMED (history unmanufacturable)
    "SLF-052": {"verdict": "ACCRUE-CONFIRMED", "note": "zt_pool akshare backfill: only ~5 snapshots exist historically — full PIT history unmanufacturable. Append-only going forward. Display-only ruling confirmed; no signal test possible until ≥2y of daily data.",
                "phase0_report": "reports/slf052-ztpool-backfill-probe.md"},
    # AUTHORIZED — PILOT (1)
    "SLF-031": {"verdict": "PILOT", "note": "Feasibility pilot: 20-ticker lazy-prices spike (EDGAR full text, 10 req/s law, similarity metrics, cost model) + design doc + draft pre-registration. No signal claims."},
}


def screen_candidate(c: dict) -> dict:
    gates = {
        "data_path": c["data_state"] in DATA_PASS,
        "pit_plan": c["pit"] in PIT_PASS,
        "sample": c["history_years"] >= 5,
        "baseline": bool(c["baseline"]),
        "novelty": c["prior"] not in {"known_killed", "duplicate", "prior_killed_level"},
        "incremental": c["orthogonality"] >= 2,
        "evidence": c["literature"] >= 2,
    }
    score = 0.0
    score += {"ready": 2.0, "partial": 1.5, "free_new": 1.25, "external_heavy": 0.75, "paid": 0.0, "blocked": 0.0}.get(c["data_state"], 0.0)
    score += 1.5 if gates["pit_plan"] else 0.0
    score += 1.0 if gates["sample"] else 0.0
    score += min(c["literature"], 3) * 0.8
    score += min(c["orthogonality"], 3) * 0.9
    score += {1: 1.0, 2: 0.5, 3: 0.0}.get(c["complexity"], 0.0)
    score += 0.8 if gates["baseline"] else 0.0
    score += 0.7 if c["prior"] in {"fresh", "extension"} else 0.0
    if c["prior"] in {"prior_killed_level", "known_killed"}:
        score -= 1.5
    score = round(score, 2)

    blockers = [name for name, ok in gates.items() if not ok]
    if c["prior"] in {"prior_killed_level", "known_killed"}:
        verdict = "graveyard_now"
    elif c["data_state"] in {"paid", "external_heavy", "blocked"}:
        verdict = "data_contract_first" if score >= 6.5 else "watchlist_or_reject"
    elif all(gates.values()) and score >= 10.0:
        verdict = "advance_to_fable"
    elif gates["data_path"] and gates["pit_plan"] and gates["baseline"] and score >= 6.5:
        verdict = "local_phase0_ready"
    elif score < 5.0:
        verdict = "graveyard_now"
    else:
        verdict = "watchlist_or_reject"

    out = dict(c)
    if verdict == "local_phase0_ready" and not blockers and score < 10.0:
        blockers = ["score_threshold"]
    out.update({
        "gates": gates,
        "score": score,
        "blockers": blockers,
        "phase0_verdict": verdict,
        "present_to_fable": verdict == "advance_to_fable",
    })
    return out


def screen_candidates() -> list[dict]:
    return [screen_candidate(c) for c in CANDIDATES]


def phase0_summary(rows: list[dict] | None = None) -> dict:
    """Stable summary — no drifting timestamp so build artifacts are deterministic.

    The timestamp is written only in the research/ outputs produced by
    scripts/signal_lab_frontier_phase0.py, not here.
    """
    rows = rows or screen_candidates()
    counts = Counter(r["phase0_verdict"] for r in rows)
    # Fable verdict tally (post-adjudication counts for display)
    build_ids = {k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "BUILD"}
    probe_ids = {k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "PROBE"}
    pilot_ids = {k for k, v in FABLE_VERDICTS.items() if v["verdict"] == "PILOT"}
    return {
        "total": len(rows),
        "advance_to_fable": counts.get("advance_to_fable", 0),
        "local_phase0_ready": counts.get("local_phase0_ready", 0),
        "data_contract_first": counts.get("data_contract_first", 0),
        "watchlist_or_reject": counts.get("watchlist_or_reject", 0),
        "graveyard_now": counts.get("graveyard_now", 0),
        "verdict_counts": dict(counts),
        "build_count": len(build_ids),
        "probe_count": len(probe_ids),
        "pilot_count": len(pilot_ids),
    }


def _id_suffix(cid: str) -> int:
    """Extract integer suffix from SLF-NNN for ordering/range comparisons."""
    return int(cid.split("-")[1])


# ---------------------------------------------------------------------------
# zh-CN translations for the 14 docket-derived advance_to_fable rows.
# Finance-register zh-CN; consistent with hand-row translations in signal_lab.py.
# Keys: id -> (name_zh, thesis_zh, build_zh, gate_zh)
# ---------------------------------------------------------------------------
_DOCKET_ZH: dict[str, tuple[str, str, str, str]] = {
    "SLF-012": (
        "FINRA卖空量压力",
        "卖空量比率冲击与价格强弱及借券成本代理交叉验证。",
        "现有FINRA卖空量采集器。",
        "截面IC与事件分桶；得分须超越FTD/借券代理基线。",
    ),
    "SLF-025": (
        "机会性内部人集中买入",
        "非常规内部人买入、集中买入事件及角色加权净美元/市值。",
        "现有SEC Form 4内部人数据库。",
        "超越现有内部人因子的增量IC；须通过常规交易者过滤。",
    ),
    "SLF-026": (
        "偿债修复后内部人增持",
        "资产负债表与现金流修复后（非普通低位买入）的内部人买入。",
        "SEC内部人数据与基本面面板。",
        "截面IC与底部反弹事件分桶。",
    ),
    "SLF-027": (
        "净增发/稀释冲击",
        "股本增长、ATM/可转债/证券增发及稀释加速。",
        "现有EDGAR稀释采集器。",
        "月度IC与长仅多头剔除价值；不得得分，除非超越FTD/借券代理。",
    ),
    "SLF-031": (
        "EDGAR懒价格文本变化信号",
        "10-K/10-Q年度文本变化及被忽视章节增量差异。",
        "SEC备案文本与LM/清洗后10-X摘要；需新文本处理流水线。",
        "备案后21/63/126日IC；须超越语调与关注度基线的增量优势。",
    ),
    "SLF-034": (
        "8-K条款类别异常",
        "8-K条款级异常集群、备案时交易量异常及陈旧vs新鲜关注度。",
        "现有EDGAR 8-K/财报8-K采集器。",
        "事件窗口异常收益与事件后漂移（按条款族分类）。",
    ),
    "SLF-035": (
        "业绩指引修订语言",
        "指引上调/下调、不确定性语言及管理层收窄/扩宽幅度。",
        "现有EDGAR指引采集器。",
        "前向IC与事件漂移；须超越分析师修订广度基线。",
    ),
    "SLF-038": (
        "毛利率拐点",
        "毛利率加速及从低谷回升（相对行业）。",
        "现有基本面面板。",
        "季度PIT IC；若被盈利能力/修订因子所涵盖则否决。",
    ),
    "SLF-039": (
        "库存积压对比销售放缓",
        "库存增长减去销售增长（按行业季节性调整）。",
        "现有基本面面板。",
        "季度IC；须在零售/能源以外呈现负向前瞻优势。",
    ),
    "SLF-051": (
        "中国融资余额冲量",
        "融资余额加速、行业集中度及融资/成交额比率。",
        "现有中国融资数据采集器。",
        "前向IC与崩盘风险检验；区分理性杠杆与情绪杠杆。",
    ),
    "SLF-053": (
        "A-H溢价错位收敛",
        "配对A-H溢价Z值、资金流门控及汇率压力。",
        "现有HK A-H面板。",
        "配对收敛IC；除非组合构建可行，否则禁止宽市场主张。",
    ),
    "SLF-055": (
        "一级交易商国债库存/失交压力",
        "交易商国债持仓、融资、失交/待收以及库存消化。",
        "纽约联储一级交易商统计；OFR镜像可用。",
        "利率/曲线事件研究与SPY/TLT回撤背景；可能作为辅助确认因子。",
    ),
    "SLF-056": (
        "回购/SOFR尾部压力",
        "SOFR第99百分位、回购专项溢价代理及资金尾部Z值。",
        "现有OFR短期资金监控采集器。",
        "前向回撤AUC与事件研究；可能作为展示/辅助确认因子。",
    ),
    "SLF-059": (
        "EIA石油库存意外",
        "原油/汽油/馏分油季节性模型误差、炼油运行量及供应天数。",
        "现有EIA采集器及每周石油报告数据。",
        "仅使用季节性模型误差（无真实一致预期）的CL/XLE/OIH事件研究。",
    ),
}


def page_frontier_rows() -> list[dict]:
    """Rows to add under the compact Signal Lab frontier panel.

    The first ten hand-curated rows live in engine.signal_lab. This function adds
    only additional Phase-0 survivors from the expanded docket, with real zh-CN
    translations derived from the candidate data and Fable verdict applied.
    """
    rows = []
    for r in screen_candidates():
        # Use integer suffix compare — SLF-010 = 10, so include rows with suffix > 10
        if _id_suffix(r["id"]) <= 10 or r["phase0_verdict"] != "advance_to_fable":
            continue
        fv = FABLE_VERDICTS.get(r["id"], {})
        fable_verdict = fv.get("verdict", "PENDING")
        # Real zh-CN translations for docket-derived rows (finance-register zh-CN)
        zh = _DOCKET_ZH.get(r["id"])
        if zh is None:
            # Fallback: should not happen for any known advance_to_fable docket row,
            # but guard defensively so new candidates surface visibly as English stubs.
            name_zh = r["name"]
            thesis_zh = r["feature"]
            build_zh = r["data_path"]
            gate_zh = r["first_gate"]
        else:
            name_zh, thesis_zh, build_zh, gate_zh = zh
        rows.append({
            "name": r["name"],
            "name_zh": name_zh,
            "market": r["market"],
            "readiness": "Phase-0 存活候选",
            "readiness_zh": "Phase-0 存活候选",
            "thesis": r["feature"],
            "thesis_zh": thesis_zh,
            "build": r["data_path"],
            "build_zh": build_zh,
            "gate": r["first_gate"],
            "gate_zh": gate_zh,
            "source": r["source"],
            "priority": "Fable",
            "fable_verdict": fable_verdict,
        })
    return rows
