"""Daily collection entrypoint.

Usage:
    python -m scripts.collect [--full-history] [--only fred,yahoo,...]

Runs every adapter through the circuit-breaker runner. Never exits nonzero
because one source broke — the engine consumes whatever is fresh and the
dashboard surfaces staleness. Exits 1 only if EVERY source failed.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from collectors.base import run_adapter, update_breaker  # noqa: E402
from lib import store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("collect")


# Pure-REST collectors that are SAFE to run CONCURRENTLY. Verified by the collector
# audit: no akshare (segfaults under threads) and no yfinance (self-parallelizes and
# gets Yahoo-banned under an outer pool). The VALUE is the upstream HOST GROUP — members
# of the same group share one upstream host, so they run SERIALLY within the group (SEC
# fair-access <10 req/s across *.sec.gov; a single Quiver API host with no internal rate
# limit; CFTC); distinct groups run in PARALLEL. Each adapter writes its OWN per-source
# parquet and run_adapter only READS the shared status (written once, at the end), so the
# concurrency is write-safe. Everything NOT listed here stays in the serial loop —
# akshare china/hk, yfinance *_prices/*_universe/breadth, the crypto pullers, and
# canada_macro (multi-host incl. sandbox-unreachable FRED).
_QUIVER_KEYS = (
    "quiver_congress", "quiver_senate", "quiver_house", "quiver_lobbying",
    "quiver_govcontracts", "quiver_offexchange", "quiver_insiders", "quiver_flights",
    "quiver_patents", "quiver_wsb", "quiver_twitter", "quiver_sec13f",
    "quiver_sec13f_changes", "quiver_cnbc", "quiver_spacs", "quiver_trump",
    "quiver_corpdonors", "quiver_news", "quiver_congressholdings", "quiver_bills",
    "quiver_appratings", "quiver_watchlist",
)
_CONCURRENT_HOSTS: dict[str, str] = {
    # SEC EDGAR — fair-access <10 req/s shared across data.sec.gov / www.sec.gov / efts.sec.gov
    "edgar_8k": "sec", "edgar_13f": "sec", "edgar_trumpflow": "sec",
    "beneficial_ownership": "sec", "edgar_dilution": "sec",
    # Quiver — single API host (api.quiverquant.com), no internal pacing
    **{k: "quiver" for k in _QUIVER_KEYS},
    # CFTC — publicreporting.cftc.gov / www.cftc.gov
    "cot": "cftc",
    # fully-independent distinct hosts — each its own group (runs fully in parallel)
    "worldbank": "worldbank", "eia": "eia", "usaspending": "usaspending",
    "prediction_markets": "polymarket", "treasury_auctions": "treasurydirect",
    "jodi": "jodi", "french": "french", "frbsf_sentiment": "frbsf",
    "bis": "bis", "uncertainty_indices": "uncertainty",
    "federal_register": "federalregister",  # federalregister.gov — distinct host, runs in parallel
    "cleveland_nowcast": "clevelandfed",    # clevelandfed.org — distinct host, runs in parallel (MRI-PR-A)
    "kalshi_releases": "kalshi",           # api.elections.kalshi.com — keyless, distinct host (MRI PR-K)
}


def _run_one(key: str, cls, full_history: bool):
    """Run a single adapter through the circuit-breaker runner. Returns (result, secs)
    or None if the adapter couldn't even be constructed. Pure per-source work — no
    shared mutable state — so it is safe to call from a worker thread."""
    log.info("=== running %s ===", key)
    try:
        adapter = cls()
    except Exception as e:  # noqa: BLE001
        log.error("init %s failed: %s", key, e)
        return None
    t0 = time.perf_counter()
    res = run_adapter(adapter, full_history=full_history)
    dt = time.perf_counter() - t0
    res.source = key
    log.info("%s -> %s (%d rows, last %s) [%.1fs]%s", key, res.status, res.rows,
             res.last_date, dt, f" err={res.error}" if res.error else "")
    # PIT release-lag recorder (masterplan W1a): append {source, fetch_ts, last_obs_date}
    # so a first-party release calendar accrues going forward. Wrapped so it can NEVER
    # break the collect pipeline; the live engine never reads this log.
    try:
        from engine.pit_lag_recorder import record_fetch_result
        record_fetch_result(res, group=getattr(adapter, "group", key))
    except Exception:  # noqa: BLE001 — additive, never fatal
        pass
    return res, round(dt, 1)


def all_adapters() -> dict:
    """Import lazily so one module's import-time failure can't kill the run."""
    registry = {}
    specs = [
        ("fred", "collectors.fred", "FredAdapter"),
        ("yahoo", "collectors.yahoo", "YahooAdapter"),
        ("treasury", "collectors.treasury", "TreasuryAdapter"),
        ("nyfed", "collectors.nyfed", "NyFedAdapter"),
        ("breadth", "collectors.breadth", "BreadthAdapter"),
        ("smallcap_breadth", "collectors.smallcap_breadth", "SmallCapBreadthAdapter"),
        ("midcap_breadth", "collectors.midcap_breadth", "MidCap400BreadthAdapter"),
        ("cot", "collectors.cot", "CotAdapter"),
        ("cboe_putcall", "collectors.cboe", "PutCallAdapter"),
        ("cboe_gex", "collectors.cboe", "GexAdapter"),
        ("cboe_skew", "collectors.cboe_indices", "CboeSkewAdapter"),   # tail-risk index (research/QUANT_FACTOR_EXPANSION.md)
        ("cboe_vvix", "collectors.cboe_indices", "CboeVvixAdapter"),   # vol-of-vol 2006+ -> engine/vol_regime VVIX-VIX leg (research/VOL_REGIME_DATA_ACCRUAL.md)
        ("cboe_vix_futures", "collectors.cboe_vix_futures", "CboeVixFuturesAdapter"),  # front VX settle (sanitizer) + full M1..M6 curve (forward-accruing; research/VOL_REGIME_DATA_ACCRUAL.md)
        ("fedboard_ebp", "collectors.fedboard", "EbpAdapter"),         # Excess Bond Premium (credit risk-appetite)
        ("sovereign", "collectors.sovereign", "SovereignAdapter"),     # ECB euro-area + JGB sovereign yields (Bonds Phase 5)
        ("frbsf_sentiment", "collectors.frbsf", "NewsSentimentAdapter"),  # SF Fed Daily News Sentiment (real-activity nowcast)
        ("french", "collectors.french", "FrenchAdapter"),             # Ken French monthly factors -> deep-history factor seasonality
        ("eia", "collectors.eia", "EiaAdapter"),                       # petroleum supply (Weekly Petroleum Status)
        ("jodi", "collectors.jodi", "JodiAdapter"),                    # JODI monthly closing oil stocks by country (Strategic Reserves page)
        ("worldbank", "collectors.worldbank", "WorldBankAdapter"),     # World Bank reserve assets -> gold value/share (Strategic Reserves page)
        ("ofr_fsi", "collectors.ofr_fsi", "OfrFsiAdapter"),            # OFR Financial Stress Index (functional + regional decomposition)
        ("cleveland_nowcast", "collectors.cleveland_nowcast", "ClevelandNowcastAdapter"),  # Cleveland Fed daily CPI/PCE nowcast (MRI-PR-A; fail-open, keyless)
        ("rate_futures", "collectors.rate_futures", "RateFuturesAdapter"),  # ZQ/SR3 implied Fed-policy path (display-only, research/DATA_SIGNAL_EXPANSION_2026.md #2)
        ("uncertainty_indices", "collectors.uncertainty_indices", "UncertaintyIndicesAdapter"),  # EPU + GPR (threat/act) daily text-uncertainty (display-only, narrative-quant-framework P0)
        # FINRA short interest (Phase 3) is ticker-indexed, fetched from build_factors (like EDGAR), not here.
        ("sentiment_naaim", "collectors.sentiment", "NaaimAdapter"),
        ("sentiment_aaii", "collectors.sentiment", "AaiiAdapter"),
        ("wiki_pageviews", "collectors.wiki_pageviews", "WikiPageviewsAdapter"),  # offshore attention (display-only; Phase-0 scripts/wiki_attention_phase0.py)
        ("sector_flows", "collectors.sponsors", "SectorFlowAdapter"),
        ("holdings", "collectors.holdings", "HoldingsAdapter"),
        ("etf_holdings", "collectors.etf_holdings", "EtfHoldingsAdapter"),
        ("sector_holdings", "collectors.sector_holdings", "SectorHoldingsAdapter"),
        ("stock_prices", "collectors.sector_holdings", "StockPriceAdapter"),
        ("fundamentals", "collectors.fundamentals", "FundamentalsAdapter"),
        ("stock_fundamentals", "collectors.sector_holdings", "StockFundamentalsAdapter"),
        ("edgar_13f", "collectors.edgar_13f", "Edgar13FAdapter"),  # curated super-investor 13F holdings (smart money)
        ("openfigi", "collectors.openfigi", "OpenFigiAdapter"),    # keyless CUSIP->ticker master -> unhides foreign/ADR 13F lines (engine/smart_money.full_cusip_map)
        ("ofr", "collectors.ofr", "OfrAdapter"),                   # OFR short-term funding monitor (repo/SOFR plumbing)
        ("prediction_markets", "collectors.prediction_markets", "PredictionMarketsAdapter"),  # Polymarket macro-event odds
        ("kalshi_releases", "collectors.kalshi_releases", "KalshiReleasesAdapter"),  # Kalshi CPI/NFP/claims bracket markets → implied distribution snapshots (MRI PR-K; keyless)
        ("usaspending", "collectors.usaspending", "UsaspendingAdapter"),  # federal contract obligations + ASSISTANCE grants/loans per curated ticker -> Divergence Radar + gov_grant convergence channel
        # Beyond-Quiver alt-data/divergence sources (keyless except grants_gov; all degrade gracefully)
        ("edgar_8k", "collectors.edgar_8k", "Edgar8KAdapter"),     # SEC 8-K material-event velocity (theme_event radar leg) + per-ticker material_8k convergence channel
        ("beneficial_ownership", "collectors.beneficial_ownership", "BeneficialOwnershipAdapter"),  # keyless SC 13D/13G sweep + filer enrichment -> per-ticker ownership-regime (engine/beneficial_ownership.py)
        ("edgar_dilution", "collectors.edgar_dilution", "EdgarDilutionAdapter"),  # S-3/S-3ASR/424B* daily-index sweep -> data/edgar/dilution_events.parquet (nwqs-c dilution context; display-only)
        ("openfda", "collectors.openfda", "OpenFdaAdapter"),       # Drugs@FDA approvals/label-expansions -> fda_approval/fda_label_expansion channels (healthcare blind spot)
        ("huggingface", "collectors.huggingface", "HuggingFaceAdapter"),  # HF model-download velocity -> hf_model_momentum channel (AI adoption blind spot)
        ("grants_gov", "collectors.grants_gov", "GrantsGovAdapter"),      # Simpler Grants.gov pre-award FOA flow (theme_event radar leg); GATED on free GRANTS_GOV_API_KEY -> 'blocked' without it
        ("clinicaltrials", "collectors.clinicaltrials", "ClinicalTrialsAdapter"),  # keyless ClinicalTrials.gov Phase-3 starts/halts -> clinical_phase3_start channel
        ("finnhub_altdata", "collectors.finnhub_altdata", "FinnhubAltdataAdapter"),  # analyst trends + insider MSPR + earnings surprises (existing FINNHUB key) -> 3 convergence channels
        ("finra_short_volume", "collectors.finra_short_volume", "FinraShortVolumeAdapter"),  # keyless daily consolidated short-VOLUME (fresher than bi-monthly short interest) -> stock-page short_flow confirmer
        ("finra_ats_transparency", "collectors.finra_ats_transparency", "FinraAtsTransparencyAdapter"),  # keyless FINRA OTC Transparency weekly per-ATS venue breakdown (T2e; 2-4wk lag) -> darkpool.html venue table
        ("polygon_news", "collectors.polygon_news", "PolygonNewsAdapter"),  # Polygon news-sentiment roll-up (existing POLYGON key) -> news_sentiment channel
        ("github_repos", "collectors.github_repos", "GithubReposAdapter"),  # GitHub star velocity (optional GITHUB_TOKEN) -> github_momentum channel
        ("sam_gov", "collectors.sam_gov", "SamGovAdapter"),               # SAM.gov pre-award solicitations by NAICS (theme_event radar leg); GATED on SAM_API_KEY -> 'blocked' without it
        ("federal_register", "collectors.federal_register", "FederalRegisterAdapter"),  # Federal Register policy-doc velocity (keyless; two-stage AGENCY-SLUG x TERM filter; theme_event radar leg); degrades gracefully when absent
        ("bis", "collectors.bis", "BisAdapter"),                   # BIS global credit-cycle (credit-gap + DSR)
        ("treasury_auctions", "collectors.treasury_auctions", "TreasuryAuctionsAdapter"),  # TreasuryDirect auction RESULTS -> supply-absorption panel (display-only)
        # China A-share dashboard — see research/CHINA_DATA_AUDIT.md
        ("china_prices", "collectors.china_prices", "ChinaPriceAdapter"),
        ("china_stocks", "collectors.china_stock_prices", "ChinaStockPriceAdapter"),  # per-NAME daily OHLC (high/low, ADJUSTED) for the signal engine — research/signal_engine/MULTICOUNTRY_DATA.md
        ("china_stocks_raw", "collectors.china_stock_raw", "ChinaStockRawPriceAdapter"),  # RAW (nominal) per-NAME OHLC for level/limit/gap/A-H logic — masterplan §W6-CN fix 3
        ("china_macro", "collectors.china_macro", "ChinaMacroAdapter"),
        ("china_breadth", "collectors.china_breadth", "ChinaBreadthAdapter"),
        ("china_universe", "collectors.china_universe", "ChinaUniverseAdapter"),  # broad A-share SEARCH set (decoupled from breadth)
        ("china_margin", "collectors.china_margin", "ChinaMarginAdapter"),     # 融资融券 crowd meter
        ("china_margin_detail", "collectors.china_margin_detail", "ChinaMarginDetailAdapter"),  # per-name 融资余额+融券余量 daily accrual (W3-C margin-velocity substrate)
        ("china_lhb", "collectors.china_lhb", "ChinaLhbAdapter"),              # 龙虎榜 daily append + events tape (W3-C LHB substrate)
        ("china_connect", "collectors.china_connect", "ChinaConnectAdapter"),  # 沪深港通 flows (repairs connect_flow)
        ("china_flows", "collectors.china_flows", "ChinaFlowsAdapter"),        # AH premium / limit-up / ETF shares
        ("china_qvix", "collectors.china_qvix", "ChinaQvixAdapter"),           # 300/50ETF option-implied vol ("China VIX") — fear/euphoria + drawdown
        ("china_credit", "collectors.china_credit", "ChinaCreditAdapter"),     # 社融 TSF (mofcom, legacy-SSL)
        ("china_tushare", "collectors.china_tushare", "ChinaTushareAdapter"),  # gated Tushare plane (mktcap/moneyflow/margin/chips) — never CI-invoked before, froze 2026-06-21
        ("china_property", "collectors.china_property", "ChinaPropertyAdapter"),  # 70-city price breadth + climate + CGB + rebar/iron-ore
        ("china_pboc", "collectors.china_pboc", "ChinaPbocAdapter"),           # PBoC corridor legs: FX reserves+gold / repo fixings FR007 / USD-CNY ref (engine/china_policy_watch.py)
        ("china_yield_spread", "collectors.china_yield_spread", "ChinaYieldSpreadAdapter"),  # CN vs US sovereign curve + slope + CN-US spread — ACCRUING (no engine consumer yet)
        ("china_cgb_curve", "collectors.china_cgb_curve", "ChinaCgbCurveAdapter"),  # full CGB term structure — ACCRUING (no engine consumer yet)
        ("china_a_valuation", "collectors.china_a_valuation", "ChinaAValuationAdapter"),  # whole-A median PE/PB + 10y/all percentiles (hub valuation anchor / anti-chase)
        ("china_sectors", "collectors.china_sectors", "ChinaSectorsAdapter"),  # Shenwan (申万) L1 industry indices — authoritative deep sector history (1999/2014->) for the Sector Desk + pathway engine (free analogue of the GS China sector baskets)
        ("china_news", "collectors.china_news", "ChinaNewsAdapter"),           # CCTV 新闻联播 official policy-tone series (keyless; display-only news/sentiment panel)
        ("china_news_wire", "collectors.china_news_wire", "ChinaNewsWireAdapter"),  # multi-source flash-wire daily tone -> media-sentiment index (engine/china_news_intel.py)
        ("china_official_corpora", "collectors.china_official_corpora", "ChinaOfficialCorporaAdapter"),  # official policy corpora (State Council/PBOC/NDRC/CSRC/People's Daily) -> date-keyed parquet + qbus; feeds the Communiqué Diff (engine/communique_diff.py, W4 B1)
        ("china_filings", "collectors.china_filings", "ChinaFilingsAdapter"),  # CNInfo A-share filing metadata (SSE+SZSE): investigation/inquiry/earnings/restructuring events → data/china_filings/filings.parquet (W3.2)
        # Hong Kong / Hang Seng dashboard — see research/HK_DATA_AUDIT.md
        # (macro reused from china_macro; flows reused from china_connect/china_flows)
        ("hk_prices", "collectors.hk_prices", "HkPriceAdapter"),
        ("hk_stocks", "collectors.hk_stock_prices", "HkStockPriceAdapter"),  # per-NAME daily OHLC (high/low) for the signal engine — research/signal_engine/MULTICOUNTRY_DATA.md
        ("hk_breadth", "collectors.hk_breadth", "HkBreadthAdapter"),
        ("hkma", "collectors.hkma", "HkmaAdapter"),                            # peg-funding: Aggregate Balance + HIBOR + TWI
        ("hk_indices", "collectors.hk_indices", "HkIndicesAdapter"),           # true Hang Seng TECH (HSTECH) index OHLCV — retires the 3033.HK ETF proxy
        ("hk_ah_official", "collectors.hk_ah_official", "HkAhOfficialAdapter"),  # official ~190-pair A/H premium snapshot + reconstructed daily index
        ("hk_ah_panel", "collectors.hk_ah_panel", "HkAhPanelAdapter"),          # A/H matched-pair premium panel (25 pairs, 2001->): pure-compute from in-tree stores, no network
        ("hk_connect_channels", "collectors.hk_connect_channels", "HkConnectChannelsAdapter"),  # 港股通沪/深 per-channel southbound history (additive to china_connect)
        ("hk_southbound_holdings", "collectors.hk_southbound_holdings", "HkSouthboundHoldingsAdapter"),  # per-STOCK southbound holdings (mainland smart-money) — feeds the HK Stock Desk conviction
        ("hk_valuation", "collectors.hk_valuation", "HkValuationAdapter"),     # Baidu PE/PB market-median (currency-neutral; the read hk_fundamentals skips)
        ("hk_property", "collectors.hk_property", "HkPropertyAdapter"),         # Centaline CCL weekly HK home-price index (+ CVI/CSI) — DISPLAY only (fragile->blocked)
        ("hk_full_breadth", "collectors.hk_full_breadth", "HkFullBreadthAdapter"),  # full HK main-board adv/dec participation (Eastmoney spot; fragile->blocked)
        ("hk_closes_deep", "collectors.hk_closes_deep", "HkClosesDeepAdapter"),  # nightly incremental refresh of data/hk_search/closes_deep.parquet (HKCA-3 fix)
        # HK short-data plane (W1/Slice-F): two DISTINCT sub-stores (see collectors/hk_shorts.py)
        # hk_shorts_positions = SFC aggregated weekly POSITIONS (≥0.02% of issued, T+7, 2012→)
        # hk_shorts_turnover  = HKEX daily short-sell TURNOVER (today-only, accrue-forward)
        # CRITICAL: positions ≠ turnover; never conflate (masterplan §3 H2 + red-team)
        ("hk_shorts_positions", "collectors.hk_shorts", "HkShortsPositionsAdapter"),
        ("hk_shorts_turnover", "collectors.hk_shorts", "HkShortsTurnoverAdapter"),
        ("hk_universe", "collectors.hk_universe", "HkUniverseAdapter"),  # expanded HSCI universe (~537 names) deep OHLCV (R2: data/hk_stocks_ext/) — H4 reversal + breadth ignition (masterplan §3 H4, §8 W1)
        ("hk_placements", "collectors.hk_placements", "HkPlacementsAdapter"),  # H-PLC (§3, W1c): HKEX placing/rights/open-offer headline events (2007->) — ripe-list dilution risk gate + post-placement drift accrual
        ("hk_cbbc", "collectors.hk_cbbc", "HkCbbcAdapter"),  # H-CBB (W1 data-plane): HKEX CBBC+DW daily outstanding — leverage-map + magnet-zone context organ (display-only, accrues forward ledger)
        ("hk_hkexnews", "collectors.hk_hkexnews", "HkHkexnewsAdapter"),  # H-FBus (W1 data-plane): HKEXnews headline-category filing bus — buyback/results/mandate/shareholder event tape (display-only, accrues forward ledger)
        ("hk_gdelt", "collectors.hk_gdelt", "HkGdeltAdapter"),          # H-NAR (W1 data-plane): GDELT DOC 2.0 vol+tone for HK platform-tech bellwethers — narrative/attention-shock context organ (display-only, accrues forward ledger)
        ("massive_stock_day", "collectors.massive_stock_day", "MassiveStockDayAdapter"),  # whole-market US daily OHLCV nightly incremental (R2: data/massive_stock_day/) — Setup-Species §7 W0.6a
        # Canada / S&P/TSX dashboard — keyless: yfinance prices + BoC VALET / StatsCan WDS / FRED macro
        ("canada_prices", "collectors.canada_prices", "CanadaPriceAdapter"),
        ("canada_macro", "collectors.canada_macro", "CanadaMacroAdapter"),     # BoC VALET + StatsCan WDS + FRED comparables
        ("canada_breadth", "collectors.canada_breadth", "CanadaBreadthAdapter"),
        ("canada_universe", "collectors.canada_universe", "CanadaUniverseAdapter"),  # full S&P/TSX Composite SEARCH set (iShares XIC; decoupled from breadth)
        # international comparative dashboard (JP/KR/TW/GB/EZ) — all keyless
        ("intl_prices", "collectors.intl_prices", "IntlPriceAdapter"),         # yfinance indices + vol + FX
        ("intl_macro", "collectors.intl_macro", "IntlMacroAdapter"),           # FRED OECD CSV + ECB (degrade per-series)
        ("intl_universe", "collectors.intl_universe", "IntlUniverseAdapter"),  # pooled top-N per market via iShares UCITS holdings CSVs
        # W0-1 INTL substrate: 23-ticker country-ETF total-return OHLCV store (NOT in daily
        # critical path — lives in intl_etf.yml weekly workflow; registered here so
        # `scripts/collect --only intl_etf` works for manual / backfill runs).
        ("intl_etf", "collectors.intl_etf", "IntlEtfAdapter"),                 # data/intl_etf/<TICKER>.parquet, weekly
        # crypto (Bitcoin Vector) — see research/VECTOR_DATA_AUDIT.md
        ("coinmetrics", "collectors.coinmetrics", "CoinMetricsAdapter"),
        ("bgeo", "collectors.bgeo", "BgeoAdapter"),
        ("coinbase", "collectors.coinbase", "CoinbaseAdapter"),
        ("okx", "collectors.okx", "OkxAdapter"),
        ("deribit", "collectors.deribit", "DeribitAdapter"),
        ("feargreed", "collectors.crypto_misc", "FearGreedAdapter"),
        ("coingecko", "collectors.crypto_misc", "CoinGeckoAdapter"),
        ("defillama", "collectors.crypto_misc", "DefiLlamaAdapter"),
        ("mempool", "collectors.crypto_misc", "MempoolAdapter"),
        ("wikipedia_btc", "collectors.crypto_misc", "WikipediaBtcAdapter"),  # keyless attention axis
        ("farside", "collectors.farside", "FarsideAdapter"),  # per-fund spot-BTC-ETF flows (US$m, 2024->)
        # Quiver Quantitative alt-data suite (Trader plan) — cross-sectional EVENT
        # feeds -> data/quiver/<dataset>.parquet (append-only, key-deduped). Feeds the
        # Alternative Data desk + the Claude-CLI brain feed. Each needs QUIVER_API_KEY
        # (else reports 'blocked'). See collectors/quiver.py.
        ("quiver_congress", "collectors.quiver", "CongressAdapter"),
        ("quiver_senate", "collectors.quiver", "SenateAdapter"),
        ("quiver_house", "collectors.quiver", "HouseAdapter"),
        ("quiver_lobbying", "collectors.quiver", "LobbyingAdapter"),
        ("quiver_govcontracts", "collectors.quiver", "GovContractsAdapter"),
        ("quiver_offexchange", "collectors.quiver", "OffExchangeAdapter"),
        ("quiver_insiders", "collectors.quiver", "InsidersAdapter"),
        ("quiver_flights", "collectors.quiver", "FlightsAdapter"),
        ("quiver_patents", "collectors.quiver", "PatentsAdapter"),
        ("quiver_wsb", "collectors.quiver", "WallStreetBetsAdapter"),
        ("quiver_twitter", "collectors.quiver", "TwitterAdapter"),
        ("quiver_sec13f", "collectors.quiver", "Sec13FAdapter"),
        ("quiver_sec13f_changes", "collectors.quiver", "Sec13FChangesAdapter"),
        ("quiver_cnbc", "collectors.quiver", "CnbcAdapter"),
        ("quiver_spacs", "collectors.quiver", "SpacsAdapter"),
        ("quiver_trump", "collectors.quiver", "TrumpTradesAdapter"),
        ("quiver_corpdonors", "collectors.quiver", "CorporateDonorsAdapter"),
        ("quiver_news", "collectors.quiver", "QuiverNewsAdapter"),
        ("quiver_congressholdings", "collectors.quiver", "CongressHoldingsAdapter"),
        ("quiver_bills", "collectors.quiver", "BillSummariesAdapter"),
        ("quiver_appratings", "collectors.quiver", "AppRatingsAdapter"),
        # Per-ticker (Top Shareholders + Exec-Comp) over a focused watchlist (graph +
        # convergent names) — these Quiver endpoints take a ticker, no bulk cross-section.
        ("quiver_watchlist", "collectors.quiver_watchlist", "QuiverWatchlistAdapter"),
        # SEC EDGAR full-text search for Trump-linked entity filings — the genuinely-early
        # channel (8-K/S-4/425/EX-99 at filing time). Keyless (UA only). See collectors/edgar_trumpflow.py.
        ("edgar_trumpflow", "collectors.edgar_trumpflow", "EdgarTrumpflowAdapter"),
        # LBNL "Queued Up" annual interconnection-queue — total queued GW -> YoY% ->
        # data/eia/interconnection_queue.json; arms engine.power_scarcity._queue_pull()
        # (the queue_buildout leg). Keyless; emp.lbl.gov is Cloudflare-gated so a
        # committed seed JSON keeps the engine live when network fetches fail.
        ("lbnl_queue", "collectors.lbnl_queue", "LbnlQueueAdapter"),
        # ---- Day-3 SLF consolidation adapters (2026-07-07) ----
        # w2061_tsa_throughput (SLF-A5): TSA checkpoint passenger throughput 2019->
        # -> data/tsa/throughput.parquet; incremental (current year); keyless.
        ("tsa", "collectors.tsa_throughput", "TsaThroughputAdapter"),
        # w4_multistate_gaming_tape (SLF-B1): NY/NJ/PA/NV state gaming revenue collectors
        # -> data/gaming_tape/; DATA-BLOCKED without network; adapters degrade gracefully.
        ("gaming_ny", "collectors.gaming_ny", "NYGamingAdapter"),
        ("gaming_nj", "collectors.gaming_nj", "NJGamingAdapter"),
        ("gaming_pgcb", "collectors.gaming_pgcb", "PGCBGamingAdapter"),
        ("gaming_nv", "collectors.gaming_nv", "NVGamingAdapter"),
    ]
    for key, mod, cls in specs:
        try:
            m = __import__(mod, fromlist=[cls])
            registry[key] = getattr(m, cls)
        except Exception as e:  # noqa: BLE001
            log.error("could not import %s.%s: %s", mod, cls, e)
    return registry


# ------------------------------------------------------------------ shards ----
# Named collector GROUPS for time-sharded runs (see .github/workflows/asia-close.yml,
# the US-evening nightly, etc.). A regional/cadence shard passes --group <name> (keep
# only these); the nightly US run passes --exclude-group asia (everything but China/HK).
# `asia` is a bulletproof china*/hk* PREFIX match, so a new china_/hk_ adapter is
# auto-classified. `crypto`/`slow` are explicit sets consumed by shards added later —
# inert until a workflow references them; verify before enabling those shards.
_CRYPTO = {"coinmetrics", "bgeo", "coinbase", "okx", "deribit", "feargreed",
           "coingecko", "defillama", "mempool", "wikipedia_btc", "farside"}
_SLOW = set(_QUIVER_KEYS) | {
    "edgar_8k", "edgar_13f", "edgar_trumpflow", "beneficial_ownership",
    "edgar_dilution",  # nwqs-c: S-3/424B daily-index sweep; nightly-only
    "cot",
    "openfda", "huggingface", "grants_gov", "clinicaltrials", "finnhub_altdata",
    "polygon_news", "github_repos", "sam_gov", "usaspending", "prediction_markets",
    "lbnl_queue", "federal_register",
}


def group_members(name: str, registry: dict) -> set:
    """Resolve a time-shard GROUP name to the adapter keys present in `registry`."""
    keys = set(registry)
    if name == "asia":
        return {k for k in keys if k.startswith("china") or k.startswith("hk")}
    if name == "crypto":
        return keys & _CRYPTO
    if name == "slow":
        return keys & _SLOW
    if name == "us":                 # everything that is NOT China/HK (nightly US run)
        return {k for k in keys if not (k.startswith("china") or k.startswith("hk"))}
    raise SystemExit(f"unknown group {name!r} (known: asia, crypto, slow, us)")


def run_quality_audits(cfg: dict | None = None, audit_fns: list | None = None) -> dict:
    """End-of-collection DATA-QUALITY GATE (read-only over the stores; writes only data/quality/*).

    Runs the three deterministic audits — prices, macro, universe — each of which writes its own
    data/quality/<name>_audit.json (committed, so the trend is visible run-over-run), then enforces
    the governance thresholds from the config `quality:` block:
      - any non-skipped universe failing > `abort_fail_pct` (5%) of its members -> RuntimeError (aborts
        the run; surfaces as a failed CI step) — the ONE place collect.py intentionally exits nonzero;
      - the `warn_fail_pct`..`abort_fail_pct` band (1-5%) -> warn + log, never fatal;
      - soft FLAGS (big single-day moves, macro z-outliers, staleness) -> logged, never fatal.

    NEVER emails: the `quality.email_alerts` flag is honored ONLY as a conspicuous log line (no email
    backend is wired) — results live in data/quality/*_audit.json and this log. Returns a summary dict.
    audit_fns lets tests inject crafted audit docs to exercise the gate without real corrupt data."""
    from scripts import audit_common
    cfg = cfg or audit_common.quality_cfg()
    if audit_fns is None:
        from scripts import (audit_prices, audit_macro, audit_universe,
                             audit_fred_groups, audit_massive_store, audit_price_basis)
        audit_fns = [
            ("prices", lambda: audit_prices.run(cfg=cfg)),
            ("macro", lambda: audit_macro.run(cfg=cfg)),
            ("universe", lambda: audit_universe.run(cfg=cfg)),
            ("fred_groups", lambda: audit_fred_groups.audit_groups()),
            # W2.2 (D4 §6/§8): the price-basis contract guard — dual-basis presence,
            # basis preservation, no-TR-in-structure AST scan, golden-fixture flip proof,
            # forward-log basis homogeneity, narrative epoch versioning.
            ("price_basis", lambda: audit_price_basis.run(cfg=cfg)),
            # 2026-07-03 incident: manifest claimed freshness over a 110-day content
            # hole. Anchor-parquet continuity + manifest-lie tripwire; skips itself on
            # checkouts without the heavy store (CI runners).
            ("massive_store", lambda: audit_massive_store.run(cfg=cfg)),
        ]

    docs: list[tuple[str, dict]] = []
    for name, fn in audit_fns:
        try:
            docs.append((name, fn()))
        except Exception as e:  # noqa: BLE001 — an audit is a safety net; its own crash must not abort the run
            log.error("[quality] audit %s crashed (non-fatal): %s", name, e)

    # Email policy: deterministic file + conspicuous log; we DO NOT send email.
    if cfg.get("email_alerts"):
        log.warning("[quality] !!! quality.email_alerts=true but NO email backend is wired — "
                    "audit results are FILE + LOG ONLY (data/quality/*_audit.json); no email sent.")
    else:
        log.info("[quality] email disabled (quality.email_alerts=false) — "
                 "results in data/quality/*_audit.json (committed for trend).")

    abort_pct = float(cfg.get("abort_fail_pct", 5.0))
    warn_pct = float(cfg.get("warn_fail_pct", 1.0))
    aborts: list[str] = []
    warns: list[str] = []
    total_fail = total_n = total_flags = 0
    for name, doc in docs:
        total_flags += int(doc.get("n_flags", 0) or 0)
        for u in doc.get("universes", []):
            if u.get("skipped"):
                continue
            n = int(u.get("n", 0) or 0)
            if n == 0:
                continue
            total_n += n
            total_fail += int(u.get("n_failed", 0) or 0)
            fp = float(u.get("fail_pct", 0.0) or 0.0)
            line = f"{name}/{u.get('name')}: {u.get('n_failed')}/{n} failed ({fp:.1f}%)"
            if fp > abort_pct:
                aborts.append(line)
            elif fp > warn_pct:
                warns.append(line)
        # group-coverage audits (fred_groups) key on `groups`+`any_dark`, not `universes` —
        # surface dark groups in the gate summary so a repeat of the P0-A silent collection
        # gap lands in warns, not just a log line buried inside the audit
        if doc.get("any_dark"):
            for g in doc.get("groups", []):
                if g.get("dark"):
                    warns.append(f"{name}/{g.get('group')}: {g.get('n_present')}/"
                                 f"{g.get('n_total')} series present — group DARK")
        if doc.get("n_flags"):
            log.info("[quality] %s: %d soft flag(s) — logged, non-fatal", name, doc["n_flags"])

    for w in warns:
        log.warning("[quality] elevated failure rate (%.0f-%.0f%%): %s", warn_pct, abort_pct, w)

    summary = {"audits": len(docs), "n": total_n, "n_failed": total_fail,
               "n_flags": total_flags, "aborts": aborts, "warns": warns}
    if aborts:
        msg = ("[quality] DATA-QUALITY GATE FAILED — >%.0f%% of a universe failed:\n  - %s"
               % (abort_pct, "\n  - ".join(aborts)))
        log.error(msg)
        raise RuntimeError(msg)
    log.info("[quality] gate passed — %d audit(s), %d/%d members failed, %d soft flag(s); "
             "0 universes over %.0f%%.", len(docs), total_fail, total_n, total_flags, abort_pct)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-history", action="store_true")
    ap.add_argument("--only", default="")
    ap.add_argument("--group", default="",
                    help="run ONLY collectors in this named shard group (asia|crypto|slow|us)")
    ap.add_argument("--exclude-group", default="",
                    help="run everything EXCEPT collectors in this named shard group")
    ap.add_argument("--skip-quality", action="store_true",
                    help="skip the end-of-collection data-quality audit gate")
    args = ap.parse_args()

    registry = all_adapters()
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        registry = {k: v for k, v in registry.items() if k in keep}
    if args.group:
        keep = group_members(args.group, registry)
        registry = {k: v for k, v in registry.items() if k in keep}
    if args.exclude_group:
        drop = group_members(args.exclude_group, registry)
        registry = {k: v for k, v in registry.items() if k not in drop}
    log.info("collect scope: %d adapters%s", len(registry),
             f" (group={args.group or '-'} exclude={args.exclude_group or '-'} only={args.only or '-'})")

    results = []
    timings: dict[str, float] = {}

    # SERIAL phase — everything that is NOT a proven-independent pure-REST source stays
    # here, in registry order, exactly as before: the akshare adapters (segfault under
    # threads), the yfinance pullers (*_prices/*_universe/breadth — already parallelise
    # internally; an outer pool stacks Yahoo concurrency into throttle/ban territory),
    # and canada_macro (multi-host). store.upsert writes ONE parquet per source, so the
    # only thing that must stay single-writer is same-file writes — which can't happen
    # across distinct sources. Runs first so config/imports are warm before the pool.
    serial_keys = [k for k in registry if k not in _CONCURRENT_HOSTS]
    for key in serial_keys:
        out = _run_one(key, registry[key], args.full_history)
        if out is None:
            continue
        res, dt = out
        results.append(res)
        timings[key] = dt

    # CONCURRENT phase — pure-REST sources grouped by upstream HOST (see _CONCURRENT_HOSTS).
    # ONE task per host-group runs its members SERIALLY (shared host / rate ceiling: SEC
    # <10 req/s, the single Quiver API host, CFTC); the GROUPS run in PARALLEL (distinct
    # hosts). One-task-per-group means no locks are needed and no host is ever hit
    # concurrently. Wall-clock collapses from the serial sum of these sources to the
    # slowest single host-group (the Quiver chain). This is the "thread only the
    # proven-heavy, proven-independent sources" cut the serial loop's note called for.
    concurrent_keys = [k for k in registry if k in _CONCURRENT_HOSTS]
    if concurrent_keys:
        groups: dict[str, list[str]] = {}
        for k in concurrent_keys:
            groups.setdefault(_CONCURRENT_HOSTS[k], []).append(k)

        def _run_group(keys: list[str]) -> list:
            out = []
            for k in keys:                       # serial WITHIN a host group
                r = _run_one(k, registry[k], args.full_history)
                if r is not None:
                    out.append(r)
            return out

        log.info("collect: running %d REST sources across %d host-groups in parallel",
                 len(concurrent_keys), len(groups))
        with ThreadPoolExecutor(max_workers=min(len(groups), 16)) as ex:
            for grp_results in ex.map(_run_group, list(groups.values())):
                for res, dt in grp_results:
                    results.append(res)
                    timings[res.source] = dt

    # Per-adapter wall-clock: the EVIDENCE for safely targeting the next collect cut.
    if timings:
        slow = sorted(timings.items(), key=lambda kv: kv[1], reverse=True)
        log.info("collect timing total %.0fs · slowest: %s", sum(timings.values()),
                 ", ".join(f"{k} {v:.0f}s" for k, v in slow[:12]))

    # ALFRED point-in-time vintages — slow-moving (revisions accrue over months),
    # so refresh weekly via an mtime gate. Additive: a separate store the live
    # engine doesn't read (feeds point-in-time macro backtests). Runs only when
    # FRED is in scope; failure never aborts collection.
    if "fred" in registry:
        try:
            from collectors.fred import FredAdapter, _vintage_path
            vp = _vintage_path()
            stale = not vp.exists() or (time.time() - vp.stat().st_mtime) / 86400.0 >= 7
            if stale or args.full_history:
                log.info("=== refreshing FRED ALFRED vintages ===")
                FredAdapter().fetch_vintages()
            else:
                log.info("FRED vintages fresh — skip")
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("FRED vintages step failed: %s", e)
        # PIT release-lag recorder, PER FRED SERIES (a release calendar needs series-level
        # granularity, not one adapter-wide last_date). Reads each stored series' last obs
        # date from the store — cheap, additive, and can never break collection.
        try:
            from collectors.fred import FredAdapter as _FA
            from engine.pit_lag_recorder import record
            from lib import store as _store
            for _sid in _FA()._all_series():
                _ld = _store.last_date("fred", _sid)
                if _ld is not None:
                    record(_sid, _ld, group="fred")
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.debug("FRED per-series PIT lag record skipped: %s", e)

    # SEC company_tickers.json — monthly refresh (30-day mtime gate, same idiom as FRED
    # vintages). engine/name_resolver reads this at query time; without it, coverage falls
    # from ~10,528 to ~4,101 names, degrading silently on every entity-resolution call.
    # Emit a coverage line so degradation is auditable in the collect log. Additive, never fatal.
    try:
        from collectors.edgar import fetch_company_tickers as _fetch_ct
        from lib import config as _cfg_mod
        import json as _ct_json
        _ct_path = _cfg_mod.data_dir() / "edgar" / "company_tickers.json"
        _ct_stale = (not _ct_path.exists() or
                     (time.time() - _ct_path.stat().st_mtime) / 86400.0 >= 30)
        if _ct_stale or args.full_history:
            log.info("=== refreshing SEC company_tickers.json (monthly) ===")
            ok = _fetch_ct(max_age_days=30, force=args.full_history)
            if ok and _ct_path.exists():
                _n_sec = len(_ct_json.loads(_ct_path.read_text()))
                log.info("name_resolver coverage: %d SEC filers (company_tickers.json)", _n_sec)
            else:
                log.warning("name_resolver coverage: company_tickers.json fetch failed; "
                            "coverage floor ~4,101 names (SEC file absent)")
        else:
            if _ct_path.exists():
                _n_sec = len(_ct_json.loads(_ct_path.read_text()))
            else:
                _n_sec = 0
            log.info("name_resolver coverage: %d SEC filers (company_tickers.json fresh, skip fetch)",
                     _n_sec)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("company_tickers step failed: %s", e)

    # Point-in-time index-membership ledger (go-forward survivorship fix): record
    # who is in the S&P 1500 each run so the universe history compounds. Cheap,
    # additive, never fatal. See engine/universe_history.py.
    try:
        from engine.universe_history import update_membership
        update_membership(datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("universe membership step failed: %s", e)

    # Baskets-only DEEP close store: off-index names (recent IPOs + crypto/nuclear) PLUS a deep
    # (~3y) tape for the large-caps the breadth cache only holds shallowly (~15m rolling window),
    # all derived from membership.json. A separate store engine.baskets prefers — the breadth/factor
    # universe stays pure. Batched + merged onto prior, additive, never fatal. See
    # scripts/fetch_basket_extras.py.
    try:
        from scripts.fetch_basket_extras import main as fetch_basket_extras
        log.info("=== refreshing thematic-basket extras ===")
        fetch_basket_extras()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("basket extras step failed: %s", e)

    # Nasdaq-100 / Russell-2000 subsector universes: refresh the Finviz industry classification
    # (the sub-industry → subsector partition), then re-author the curated memberships. The desk +
    # cycle families render off data/baskets_<ns>/membership.json. Additive, never fatal.
    for idx in ("ndx", "rut"):
        try:
            from scripts.fetch_finviz_screener import fetch as _fv_fetch, INDEX_FILTER, OUT_DIR
            import json as _json
            flt = INDEX_FILTER[idx]
            log.info("=== refreshing Finviz %s classification ===", flt)
            payload = _fv_fetch(flt)
            out = config.data_dir() / OUT_DIR / f"{flt}.json"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(_json.dumps(payload, indent=0, separators=(",", ":")))
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("finviz %s classification step failed: %s", idx, e)

    # Baskets-only DEEP OHLCV store (data/baskets/ohlcv/<T>.parquet): full open/high/low/
    # close/VOLUME per member, the candle the consolidated-index engines (basket_index ->
    # basket_mtf + basket_tape) render whale accumulation / Chaikin money-flow / vol-hole on.
    # The close-only extras store above can't feed volume. Also pulls the Nasdaq/Russell subsector
    # universes (idx_rut covers the small-caps the breadth cache only holds shallowly). Separate
    # per-ticker store, merged onto prior, additive, never fatal. See scripts/fetch_basket_ohlcv.py.
    try:
        from scripts.fetch_basket_ohlcv import main as fetch_basket_ohlcv
        log.info("=== refreshing thematic-basket + index-subsector OHLCV (volume) ===")
        fetch_basket_ohlcv(["--finviz", "idx_ndx,idx_rut"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("basket OHLCV step failed: %s", e)

    # Re-author the Nasdaq/Russell subsector + amalgamation memberships from the fresh Finviz
    # classification + the refreshed OHLCV (the correlation-validated bulk-outs need prices).
    try:
        from scripts.build_subsector_membership import main as build_subsector_membership
        log.info("=== rebuilding Nasdaq/Russell subsector memberships ===")
        build_subsector_membership([])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("subsector membership step failed: %s", e)

    # Polygon options-OI accrual: snapshot the GEX universe's chains and store the RAW
    # per-strike open interest the Cboe path throws away (the one thing that can't be
    # backfilled — OI is point-in-time only). Foundation for the validate-gated GEX
    # drawdown leg. No-op without POLYGON_API_KEY. Additive, never fatal.
    # W0.4: capture the result dict so the status write below makes missed days
    # circuit-breaker-visible (the accrual ran before store.write_status previously,
    # so any failure was invisible in run_status.json).
    _polygon_gex_status: dict = {"status": "not_run"}
    try:
        from scripts.build_polygon_gex import accrue as accrue_polygon_gex
        log.info("=== accruing Polygon options OI (GEX foundation) ===")
        _polygon_gex_status = accrue_polygon_gex(datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        _polygon_gex_status = {"status": "failed", "error": str(e)}
        log.warning("Polygon GEX accrual step failed: %s", e)

    # Polygon intraday (hourly) US bars -> data/intraday/<T>.parquet, powering the 4H
    # timeframe on US single-stock charts. No-op without the key. Additive, never fatal.
    try:
        from scripts.build_polygon_intraday import accrue as accrue_polygon_intraday
        log.info("=== accruing Polygon intraday (4H chart data) ===")
        accrue_polygon_intraday(datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("Polygon intraday accrual step failed: %s", e)

    # W0.4: options-flow accrual status — build_options_flow runs in the render job
    # (daily.yml render step, not here), but we record whether the S3 creds that power
    # it are present so daily collect can surface the "creds absent" state as a
    # circuit-breaker warning rather than a silent no-op.
    _options_flow_status: dict = {"status": "not_run"}
    try:
        from collectors import massive_flatfiles as _mf
        _options_flow_status = ({"status": "creds_present"}
                                if _mf.enabled() else {"status": "no_creds"})
    except Exception as e:  # noqa: BLE001
        _options_flow_status = {"status": "check_failed", "error": str(e)}

    status = store.read_status()
    status["last_run"] = datetime.now(timezone.utc).isoformat()
    # merge: a partial --only run must not wipe the health of sources it skipped
    sources = status.get("sources", {})
    for r in results:
        sources[r.source] = {**asdict(r), "elapsed_sec": timings.get(r.source),
                             "checked_at": datetime.now(timezone.utc).isoformat()}
    # W0.4: register additive accrual steps so their health is circuit-breaker-visible.
    # These run outside the FetchResult loop above (they are not Adapter subclasses), so
    # they would otherwise be invisible in run_status.json.
    _now = datetime.now(timezone.utc).isoformat()
    sources["polygon_gex_accrual"] = {**_polygon_gex_status, "checked_at": _now}
    sources["options_flow_creds"] = {**_options_flow_status, "checked_at": _now}
    status["sources"] = sources
    status["circuit_breaker"], status["circuit_breaker_probe"] = update_breaker(
        results, status.get("circuit_breaker_probe"))
    store.write_status(status)

    ok = sum(1 for r in results if r.status in ("ok", "stale"))
    log.info("collection done: %d/%d sources usable", ok, len(results))

    # End-of-collection DATA-QUALITY GATE. Runs LAST so it audits everything just collected.
    # Skipped on a partial `--only` run (the universe/macro audits would falsely flag the
    # sources that run never refreshed) and behind an explicit opt-out. A >5% universe
    # failure raises RuntimeError here — the intended, conspicuous abort.
    if args.skip_quality:
        log.info("[quality] data-quality gate skipped (--skip-quality).")
    elif args.only or args.group or args.exclude_group:
        log.info("[quality] data-quality gate skipped on partial run "
                 "(only=%s group=%s exclude=%s) — the all-universe audit would false-flag "
                 "sources this shard did not refresh.", args.only or "-",
                 args.group or "-", args.exclude_group or "-")
    else:
        # Membership↔cache reconciler runs FIRST: it may prune basket members that drifted
        # off a rebuilt *_search close cache (dated changelog entry), so the read-only
        # audits grade the healed state. Its guard refusals abort like the gate; its own
        # crash is non-fatal like any audit's.
        from scripts import reconcile_membership
        try:
            reconcile_membership.run()
        except reconcile_membership.PruneGuardError:
            raise
        except Exception as e:  # noqa: BLE001 — a safety net's crash must not abort the run
            log.error("[reconcile] membership reconciler crashed (non-fatal): %s", e)
        run_quality_audits()

    # importance_v0 SHADOW lane (W3) — score the qbus store + register the
    # novelty-first challenger's HIGH/LOW band claims BEFORE the grader so the
    # same-night grade pass picks them up. Shadow-only; never rendered. Non-fatal.
    try:
        from scripts.shadow_importance_v0 import run_as_collect_step as _shadow_impv0
        _shadow_impv0()
    except Exception as e:  # noqa: BLE001 — a shadow-lane crash must not abort the run
        log.error("[shadow_importance_v0] step crashed (non-fatal): %s", e)

    # importance_v0 PIT-correct tape (W4) — the _pit families are the PRIMARY
    # leak-free tape on the duel scoreboard (report_importance_duel), so they must
    # accrue nightly alongside the W3 tape, not freeze at the one-shot backfill.
    try:
        from scripts.shadow_importance_v0_pit import run_as_collect_step as _shadow_impv0_pit
        _shadow_impv0_pit()
    except Exception as e:  # noqa: BLE001 — a shadow-lane crash must not abort the run
        log.error("[shadow_importance_v0_pit] step crashed (non-fatal): %s", e)

    # news_vector daily ingest — GDELT narrative-scope accrual (keep-FIRST, additive).
    # The freshness check always runs so a stale store is never quiet. Retry-next-collect:
    # if today's fetch was rate-limited or errored, the WARNING appears in this run's log
    # and the next collect run will re-attempt (the 12h cache gate is bypassed on failure,
    # so a failed fetch never silently blocks the next run). Non-fatal.
    try:
        from engine import news_vector as _nv
        _nv_result = _nv.ingest()
        if _nv_result is not None:
            _nv_freshness = _nv_result.get("freshness", {})
            _nv_stale_d = _nv_freshness.get("newest_event_age_days")
            if _nv_result.get("degraded_reason"):
                log.warning("news_vector ingest degraded (%s); will retry next collect "
                            "(stale=%s days)", _nv_result["degraded_reason"],
                            f"{_nv_stale_d:.1f}" if _nv_stale_d is not None else "?")
            else:
                log.info("news_vector: +%d events (%d total, newest age %.1fd)",
                         _nv_result.get("n_new", 0), _nv_result.get("n_total", 0),
                         _nv_stale_d if _nv_stale_d is not None else 0)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("news_vector ingest step failed: %s", e)

    # qledger adapters — register today's claims from each desk so the nightly
    # grader can grade them at maturity. Idempotent; non-fatal.
    try:
        from scripts.backfill_qledger_intel_hub import run as _hub_backfill
        _hub_result = _hub_backfill(config.ROOT)
        log.info("qledger intel_hub adapter: +%d claims (blocked=%d rejected=%d)",
                 _hub_result.get("n_registered", 0),
                 _hub_result.get("n_blocked", 0),
                 _hub_result.get("n_rejected", 0))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("qledger intel_hub adapter failed: %s", e)

    # qledger nightly grader — runs after quality audits so the parquet layer is
    # fully refreshed. Non-fatal: a grader crash must not abort the collection run.
    from scripts.grade_qledger import run_as_collect_step as _grade_qledger
    _grade_qledger()

    # CCTV 新闻联播 backfill-finalization watcher (W4/D5) — drives a three-state
    # machine (SCRAPING → FINALIZING → FINALIZED) that monitors the long-running
    # backfill process, self-heals stalls, and runs the idempotent finalize pipeline
    # once coverage ≥ 97 %.  On the FINALIZED transition it removes the gitignore
    # shard line so the subsequent `git add data/` in the nightly workflow picks up
    # the one-time ~43–60 MB shard payload.  Idempotent forever after (cheap no-op).
    # Non-fatal: a watcher crash must not abort the collection run.
    try:
        from scripts.cctv_finalize_watcher import run_as_collect_step as _cctv_watcher
        _cctv_watcher()
    except Exception as e:  # noqa: BLE001 — a watcher crash must not abort the run
        log.error("[cctv_watcher] step crashed (non-fatal): %s", e)

    # PR-A2 — breadth-divergence forward-log grader (end-of-collect, seconds-scale).
    # Grades matured rows (stamp_date + 21 business days <= today) of
    # data/breadth_divergence/forward_log.parquet in-place; idempotent re-runs.
    # Runs BEFORE the closure audit so the audit sees freshly graded state.
    # NIGHTLY-ONLY gate: forward ledgers must only be advanced in the nightly lane
    # (house law: "nightly is the sole advancer of forward ledgers; intraday lanes
    # discard data/ writes"). The daily.yml collect step sets COLLECT_LANE=nightly;
    # asia-close.yml, weekly.yml, and intl_etf.yml leave it unset so this block is
    # a no-op in those lanes.
    if os.environ.get("COLLECT_LANE") == "nightly":
        try:
            from scripts.grade_breadth_divergence import run_as_collect_step as _bd_grader
            _bd_grader()
        except Exception as e:  # noqa: BLE001 — a grader crash must not abort the run
            log.error("[grade_breadth_divergence] step crashed (non-fatal): %s", e)
    else:
        log.debug("[grade_breadth_divergence] skipped — not the nightly lane (COLLECT_LANE=%r)",
                  os.environ.get("COLLECT_LANE"))

    # PR-A2 — foresight policy-calendar date-accuracy grader (end-of-collect, seconds-scale).
    # After next_comment_close_date passes, checks the federal_register store to confirm
    # whether the predicted comment-close event occurred.  Idempotent re-runs.
    # NIGHTLY-ONLY gate: same rationale as grade_breadth_divergence above.
    if os.environ.get("COLLECT_LANE") == "nightly":
        try:
            from scripts.grade_policy_calendar import run_as_collect_step as _pol_grader
            _pol_grader()
        except Exception as e:  # noqa: BLE001 — a grader crash must not abort the run
            log.error("[grade_policy_calendar] step crashed (non-fatal): %s", e)
    else:
        log.debug("[grade_policy_calendar] skipped — not the nightly lane (COLLECT_LANE=%r)",
                  os.environ.get("COLLECT_LANE"))

    # NW Rails PR-6 — grading-closure standing audit (RUL-P10 path b).
    # Walks all declared forward ledgers, classifies each as CLOSED / GRADER-STARVED
    # / LOG-ONLY, and writes data/governance/grading_closure.json + docs/GRADING_CLOSURE.md.
    # Runs LAST (after graders) so it audits the state graders just updated. Seconds
    # only; never fatal.
    try:
        from scripts.audit_grading_closure import run_as_collect_step as _grading_closure_audit
        _grading_closure_audit()
    except Exception as e:  # noqa: BLE001 — a governance audit must not abort the run
        log.error("[grading_closure] audit step crashed (non-fatal): %s", e)

    # NW Codex Three Lobes W-A (PR-B) — claim-accountability standing audit (RUL-C9).
    # Reads claims.jsonl + grades.jsonl + track_record.json; writes
    # data/governance/claim_accountability.json + docs/CLAIM_ACCOUNTABILITY.md.
    # Read-only over qledger (RUL-C3). Runs after grading-closure so both
    # governance artifacts are updated together. Seconds only; never fatal.
    try:
        from scripts.audit_claim_accountability import run_as_collect_step as _claim_accountability_audit
        _claim_accountability_audit()
    except Exception as e:  # noqa: BLE001 — a governance audit must not abort the run
        log.error("[claim_accountability] audit step crashed (non-fatal): %s", e)

    # NEXT3 W-OC — options accrual freshness tripwire (previously unwired).
    # Checks polygon_gex/chains/ freshness + Massive S3 creds + flow summary accrual.
    # Writes data/quality/options_accrual_audit.json.  Runs BEFORE the coverage audit
    # so coverage.json can surface the accrual audit's last-run status.  Non-fatal.
    try:
        from scripts.audit_options_accrual import run_as_collect_step as _opts_accrual_audit
        _opts_accrual_audit()
    except Exception as e:  # noqa: BLE001 — an accrual audit must not abort the run
        log.error("[audit_options_accrual] step crashed (non-fatal): %s", e)

    # NEXT3 W-OC (PR-β) — options entry feature coverage audit.
    # Reads state.parquet + gate.json + board ledger; emits
    # data/options_entry/coverage.json (feature non-null coverage, family stamp
    # coverage, readiness forecast, structural-null ledger, consistency rows).
    # RUL-U5: read-only over all inputs; single-writer on coverage.json.  Non-fatal.
    try:
        from scripts.audit_options_entry_coverage import run_as_collect_step as _opts_coverage_audit
        _opts_coverage_audit()
    except Exception as e:  # noqa: BLE001 — a coverage audit must not abort the run
        log.error("[options_entry_coverage] step crashed (non-fatal): %s", e)

    # NEXT3 W-EX — operator exposure log (RUL-U6; measurement-substrate-only).
    # Reads previously committed site artifacts (experiments.json, us_standouts.json,
    # wh_banner.json, rr_banner.json); writes data/operator/exposure_log.jsonl
    # (gitignored host-local, append+dedup) and data/governance/operator_exposure_summary.json
    # (committed, 90-day bounded). No statistics, no contrasts, no trials. Seconds only;
    # never fatal.
    try:
        from scripts.build_operator_exposure_log import run_as_collect_step as _op_exposure
        _op_exposure()
    except Exception as e:  # noqa: BLE001 — a governance audit must not abort the run
        log.error("[operator_exposure] build step crashed (non-fatal): %s", e)

    # SEC Fails-to-Deliver (SLF-001) — incremental daily append.
    # Fetches semi-monthly FTD files whose availability_date has passed since the
    # last panel date (uniform 30-day PIT lag enforced in the collector).
    # Store: data/sec_ftd/panel.parquet. Additive, never fatal.
    try:
        from collectors.sec_ftd import incremental as _sec_ftd_incremental
        _ftd_result = _sec_ftd_incremental()
        log.info("sec_ftd incremental: fetched=%d skipped=%d errors=%d",
                 _ftd_result.get("fetched", 0), _ftd_result.get("skipped", 0),
                 _ftd_result.get("errors", 0))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("sec_ftd incremental step failed: %s", e)

    # NY Fed Primary Dealer Statistics (SLF-055) — Thursday weekly refresh.
    # Published Thursdays ~16:15 ET for prior Wednesday; gated to Thursdays to
    # avoid redundant fetches on other days. Store: data/nyfed_pd/pd_weekly.parquet.
    # Additive, never fatal.
    if datetime.now(timezone.utc).isoweekday() == 4:  # Thursday
        try:
            from collectors.nyfed_primary_dealer import run as _run_pd
            _run_pd(config.data_dir() / "nyfed_pd")
            log.info("nyfed_pd: Thursday refresh complete")
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.warning("nyfed_pd step failed: %s", e)

    # ---- Day-3 SLF consolidation standalone collectors (2026-07-07) ----

    # w2104_cmdi_conditioning (SLF-A4): NY Fed CMDI weekly -> data/nyfed_cmdi/
    # Idempotent; fetches the interactive-data Excel; parses Market/IG/HY sub-indices.
    # Recommended: weekly (Friday after NY Fed update). Standalone function, not Adapter.
    try:
        from scripts.collect_nyfed_cmdi import collect_nyfed_cmdi as _collect_cmdi
        _collect_cmdi()
        log.info("nyfed_cmdi: refresh complete")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("nyfed_cmdi step failed: %s", e)

    # w2051_housing_hf (SLF-A7): Redfin high-frequency national + metro housing data
    # -> data/redfin_hf/; ZORI (Zillow observed rent index) -> data/zori/
    # Standalone scripts; idempotent; degrade gracefully if upstream unavailable.
    try:
        from scripts.collect_redfin_hf import run as _collect_redfin_hf
        _collect_redfin_hf()
        log.info("redfin_hf: refresh complete")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("redfin_hf step failed: %s", e)
    try:
        from scripts.collect_zori import run as _collect_zori
        _collect_zori()
        log.info("zori: refresh complete")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("zori step failed: %s", e)

    # d2_cn_holder_sale_calendar (SLF-B3): Eastmoney 减持 plan execution windows
    # -> data/cn_holder_sales/; china-altdata section; ~10-15 min full backfill, ~1 min incremental.
    try:
        from collectors.cn_holder_sale_calendar import collect as _cn_holder_collect
        _cn_holder_collect()
        log.info("cn_holder_sale_calendar: refresh complete")
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("cn_holder_sale_calendar step failed: %s", e)

    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
