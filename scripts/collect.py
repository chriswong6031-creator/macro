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
        ("eia", "collectors.eia", "EiaAdapter"),                       # petroleum supply (Weekly Petroleum Status)
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
        # China A-share dashboard — see research/CHINA_DATA_AUDIT.md
        ("china_prices", "collectors.china_prices", "ChinaPriceAdapter"),
        ("china_macro", "collectors.china_macro", "ChinaMacroAdapter"),
        ("china_breadth", "collectors.china_breadth", "ChinaBreadthAdapter"),
        ("china_universe", "collectors.china_universe", "ChinaUniverseAdapter"),  # broad A-share SEARCH set (decoupled from breadth)
        ("china_margin", "collectors.china_margin", "ChinaMarginAdapter"),     # 融资融券 crowd meter
        ("china_connect", "collectors.china_connect", "ChinaConnectAdapter"),  # 沪深港通 flows (repairs connect_flow)
        ("china_flows", "collectors.china_flows", "ChinaFlowsAdapter"),        # AH premium / limit-up / ETF shares
        ("china_credit", "collectors.china_credit", "ChinaCreditAdapter"),     # 社融 TSF (mofcom, legacy-SSL)
        # Hong Kong / Hang Seng dashboard — see research/HK_DATA_AUDIT.md
        # (macro reused from china_macro; flows reused from china_connect/china_flows)
        ("hk_prices", "collectors.hk_prices", "HkPriceAdapter"),
        ("hk_breadth", "collectors.hk_breadth", "HkBreadthAdapter"),
        ("hkma", "collectors.hkma", "HkmaAdapter"),                            # peg-funding: Aggregate Balance + HIBOR + TWI
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
    for key, cls in registry.items():
        log.info("=== running %s ===", key)
        try:
            adapter = cls()
        except Exception as e:  # noqa: BLE001
            log.error("init %s failed: %s", key, e)
            continue
        res = run_adapter(adapter, full_history=args.full_history)
        res.source = key
        results.append(res)
        log.info("%s -> %s (%d rows, last %s)%s", key, res.status, res.rows,
                 res.last_date, f" err={res.error}" if res.error else "")

    # ALFRED point-in-time vintages — slow-moving (revisions accrue over months),
    # so refresh weekly via an mtime gate. Additive: a separate store the live
    # engine doesn't read (feeds point-in-time macro backtests). Runs only when
    # FRED is in scope; failure never aborts collection.
    if "fred" in registry:
        try:
            import time

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

    status = store.read_status()
    status["last_run"] = datetime.now(timezone.utc).isoformat()
    # merge: a partial --only run must not wipe the health of sources it skipped
    sources = status.get("sources", {})
    for r in results:
        sources[r.source] = {**asdict(r),
                             "checked_at": datetime.now(timezone.utc).isoformat()}
    status["sources"] = sources
    status["circuit_breaker"] = update_breaker(results)
    store.write_status(status)

    ok = sum(1 for r in results if r.status in ("ok", "stale"))
    log.info("collection done: %d/%d sources usable", ok, len(results))
    return 0 if ok > 0 else 1


if __name__ == "__main__":
    sys.exit(main())
