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
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from collectors.base import run_adapter, update_breaker  # noqa: E402
from lib import store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("collect")


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
        ("cboe_vix_futures", "collectors.cboe_vix_futures", "CboeVixFuturesAdapter"),  # front VX settle -> VIX thin-quote sanitizer (engine/dislocation.py)
        ("fedboard_ebp", "collectors.fedboard", "EbpAdapter"),         # Excess Bond Premium (credit risk-appetite)
        ("sovereign", "collectors.sovereign", "SovereignAdapter"),     # ECB euro-area + JGB sovereign yields (Bonds Phase 5)
        ("frbsf_sentiment", "collectors.frbsf", "NewsSentimentAdapter"),  # SF Fed Daily News Sentiment (real-activity nowcast)
        ("french", "collectors.french", "FrenchAdapter"),             # Ken French monthly factors -> deep-history factor seasonality
        ("eia", "collectors.eia", "EiaAdapter"),                       # petroleum supply (Weekly Petroleum Status)
        ("jodi", "collectors.jodi", "JodiAdapter"),                    # JODI monthly closing oil stocks by country (Strategic Reserves page)
        ("worldbank", "collectors.worldbank", "WorldBankAdapter"),     # World Bank reserve assets -> gold value/share (Strategic Reserves page)
        ("ofr_fsi", "collectors.ofr_fsi", "OfrFsiAdapter"),            # OFR Financial Stress Index (functional + regional decomposition)
        ("rate_futures", "collectors.rate_futures", "RateFuturesAdapter"),  # ZQ/SR3 implied Fed-policy path (display-only, research/DATA_SIGNAL_EXPANSION_2026.md #2)
        ("uncertainty_indices", "collectors.uncertainty_indices", "UncertaintyIndicesAdapter"),  # EPU + GPR (threat/act) daily text-uncertainty (display-only, narrative-quant-framework P0)
        # FINRA short interest (Phase 3) is ticker-indexed, fetched from build_factors (like EDGAR), not here.
        ("sentiment_naaim", "collectors.sentiment", "NaaimAdapter"),
        ("sentiment_aaii", "collectors.sentiment", "AaiiAdapter"),
        ("sector_flows", "collectors.sponsors", "SectorFlowAdapter"),
        ("holdings", "collectors.holdings", "HoldingsAdapter"),
        ("etf_holdings", "collectors.etf_holdings", "EtfHoldingsAdapter"),
        ("sector_holdings", "collectors.sector_holdings", "SectorHoldingsAdapter"),
        ("stock_prices", "collectors.sector_holdings", "StockPriceAdapter"),
        ("fundamentals", "collectors.fundamentals", "FundamentalsAdapter"),
        ("stock_fundamentals", "collectors.sector_holdings", "StockFundamentalsAdapter"),
        ("edgar_13f", "collectors.edgar_13f", "Edgar13FAdapter"),  # curated super-investor 13F holdings (smart money)
        ("ofr", "collectors.ofr", "OfrAdapter"),                   # OFR short-term funding monitor (repo/SOFR plumbing)
        ("prediction_markets", "collectors.prediction_markets", "PredictionMarketsAdapter"),  # Polymarket macro-event odds
        ("bis", "collectors.bis", "BisAdapter"),                   # BIS global credit-cycle (credit-gap + DSR)
        ("treasury_auctions", "collectors.treasury_auctions", "TreasuryAuctionsAdapter"),  # TreasuryDirect auction RESULTS -> supply-absorption panel (display-only)
        # China A-share dashboard — see research/CHINA_DATA_AUDIT.md
        ("china_prices", "collectors.china_prices", "ChinaPriceAdapter"),
        ("china_macro", "collectors.china_macro", "ChinaMacroAdapter"),
        ("china_breadth", "collectors.china_breadth", "ChinaBreadthAdapter"),
        ("china_universe", "collectors.china_universe", "ChinaUniverseAdapter"),  # broad A-share SEARCH set (decoupled from breadth)
        ("china_margin", "collectors.china_margin", "ChinaMarginAdapter"),     # 融资融券 crowd meter
        ("china_connect", "collectors.china_connect", "ChinaConnectAdapter"),  # 沪深港通 flows (repairs connect_flow)
        ("china_flows", "collectors.china_flows", "ChinaFlowsAdapter"),        # AH premium / limit-up / ETF shares
        ("china_qvix", "collectors.china_qvix", "ChinaQvixAdapter"),           # 300/50ETF option-implied vol ("China VIX") — fear/euphoria + drawdown
        ("china_credit", "collectors.china_credit", "ChinaCreditAdapter"),     # 社融 TSF (mofcom, legacy-SSL)
        ("china_property", "collectors.china_property", "ChinaPropertyAdapter"),  # 70-city price breadth + climate + CGB + rebar/iron-ore
        ("china_news", "collectors.china_news", "ChinaNewsAdapter"),           # CCTV 新闻联播 official policy-tone series (keyless; display-only news/sentiment panel)
        # Hong Kong / Hang Seng dashboard — see research/HK_DATA_AUDIT.md
        # (macro reused from china_macro; flows reused from china_connect/china_flows)
        ("hk_prices", "collectors.hk_prices", "HkPriceAdapter"),
        ("hk_breadth", "collectors.hk_breadth", "HkBreadthAdapter"),
        ("hkma", "collectors.hkma", "HkmaAdapter"),                            # peg-funding: Aggregate Balance + HIBOR + TWI
        ("hk_indices", "collectors.hk_indices", "HkIndicesAdapter"),           # true Hang Seng TECH (HSTECH) index OHLCV — retires the 3033.HK ETF proxy
        ("hk_ah_official", "collectors.hk_ah_official", "HkAhOfficialAdapter"),  # official ~190-pair A/H premium snapshot + reconstructed daily index
        ("hk_connect_channels", "collectors.hk_connect_channels", "HkConnectChannelsAdapter"),  # 港股通沪/深 per-channel southbound history (additive to china_connect)
        ("hk_southbound_holdings", "collectors.hk_southbound_holdings", "HkSouthboundHoldingsAdapter"),  # per-STOCK southbound holdings (mainland smart-money) — feeds the HK Stock Desk conviction
        ("hk_valuation", "collectors.hk_valuation", "HkValuationAdapter"),     # Baidu PE/PB market-median (currency-neutral; the read hk_fundamentals skips)
        ("hk_property", "collectors.hk_property", "HkPropertyAdapter"),         # Centaline CCL weekly HK home-price index (+ CVI/CSI) — DISPLAY only (fragile->blocked)
        ("hk_full_breadth", "collectors.hk_full_breadth", "HkFullBreadthAdapter"),  # full HK main-board adv/dec participation (Eastmoney spot; fragile->blocked)
        # Canada / S&P/TSX dashboard — keyless: yfinance prices + BoC VALET / StatsCan WDS / FRED macro
        ("canada_prices", "collectors.canada_prices", "CanadaPriceAdapter"),
        ("canada_macro", "collectors.canada_macro", "CanadaMacroAdapter"),     # BoC VALET + StatsCan WDS + FRED comparables
        ("canada_breadth", "collectors.canada_breadth", "CanadaBreadthAdapter"),
        ("canada_universe", "collectors.canada_universe", "CanadaUniverseAdapter"),  # full S&P/TSX Composite SEARCH set (iShares XIC; decoupled from breadth)
        # international comparative dashboard (JP/KR/TW/GB/EZ) — all keyless
        ("intl_prices", "collectors.intl_prices", "IntlPriceAdapter"),         # yfinance indices + vol + FX
        ("intl_macro", "collectors.intl_macro", "IntlMacroAdapter"),           # FRED OECD CSV + ECB (degrade per-series)
        ("intl_universe", "collectors.intl_universe", "IntlUniverseAdapter"),  # pooled top-N per market via iShares UCITS holdings CSVs
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
    ]
    for key, mod, cls in specs:
        try:
            m = __import__(mod, fromlist=[cls])
            registry[key] = getattr(m, cls)
        except Exception as e:  # noqa: BLE001
            log.error("could not import %s.%s: %s", mod, cls, e)
    return registry


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--full-history", action="store_true")
    ap.add_argument("--only", default="")
    args = ap.parse_args()

    registry = all_adapters()
    if args.only:
        keep = {s.strip() for s in args.only.split(",")}
        registry = {k: v for k, v in registry.items() if k in keep}

    results = []
    timings: dict[str, float] = {}
    for key, cls in registry.items():
        log.info("=== running %s ===", key)
        try:
            adapter = cls()
        except Exception as e:  # noqa: BLE001
            log.error("init %s failed: %s", key, e)
            continue
        t0 = time.perf_counter()
        res = run_adapter(adapter, full_history=args.full_history)
        dt = time.perf_counter() - t0
        timings[key] = round(dt, 1)
        res.source = key
        results.append(res)
        log.info("%s -> %s (%d rows, last %s) [%.1fs]%s", key, res.status, res.rows,
                 res.last_date, dt, f" err={res.error}" if res.error else "")

    # Per-adapter wall-clock: the EVIDENCE for safely targeting the next collect cut.
    # The top-level loop stays SERIAL on purpose — 14 akshare adapters segfault under
    # threads (see akshare notes) and the yfinance pullers (china/hk_prices, *_universe)
    # already parallelise internally via threads=True / their own ThreadPoolExecutor, so
    # an outer pool would stack Yahoo concurrency into throttle/ban territory while
    # store.upsert writes parquet non-atomically. So MEASURE first, then thread only the
    # proven-heavy, proven-independent sources (or raise the existing internal pools).
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

    # Polygon options-OI accrual: snapshot the GEX universe's chains and store the RAW
    # per-strike open interest the Cboe path throws away (the one thing that can't be
    # backfilled — OI is point-in-time only). Foundation for the validate-gated GEX
    # drawdown leg. No-op without POLYGON_API_KEY. Additive, never fatal.
    try:
        from scripts.build_polygon_gex import accrue as accrue_polygon_gex
        log.info("=== accruing Polygon options OI (GEX foundation) ===")
        accrue_polygon_gex(datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("Polygon GEX accrual step failed: %s", e)

    # Polygon intraday (hourly) US bars -> data/intraday/<T>.parquet, powering the 4H
    # timeframe on US single-stock charts. No-op without the key. Additive, never fatal.
    try:
        from scripts.build_polygon_intraday import accrue as accrue_polygon_intraday
        log.info("=== accruing Polygon intraday (4H chart data) ===")
        accrue_polygon_intraday(datetime.now(timezone.utc))
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("Polygon intraday accrual step failed: %s", e)

    status = store.read_status()
    status["last_run"] = datetime.now(timezone.utc).isoformat()
    # merge: a partial --only run must not wipe the health of sources it skipped
    sources = status.get("sources", {})
    for r in results:
        sources[r.source] = {**asdict(r), "elapsed_sec": timings.get(r.source),
                             "checked_at": datetime.now(timezone.utc).isoformat()}
    status["sources"] = sources
    status["circuit_breaker"] = update_breaker(results)
    store.write_status(status)

    ok = sum(1 for r in results if r.status in ("ok", "stale"))
    log.info("collection done: %d/%d sources usable", ok, len(results))
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
