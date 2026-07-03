"""Canada thematic baskets — the TSX analogue of engine.baskets_china.

Loads the Canada data plane and delegates the equal-weight/perf compute to
engine.baskets_region: member closes from the canada_search cache (the full ~220-name
S&P/TSX Composite, names like RY.TO Royal Bank / SHOP.TO Shopify / ABX.TO Barrick),
benchmarked to the S&P/TSX Composite (XIC.TO). Member display name = the English name
carried in membership.json. Rich iShares sector-ETF coverage gives most baskets a clean
cross-check (Banks ZEB.TO / Energy XEG.TO / Gold XGD.TO / Tech XIT.TO …).

Additive — any failure returns None and the page is skipped.
"""
from __future__ import annotations

import json
import logging

import pandas as pd

from engine.baskets_region import compute_region_baskets
from lib import config, store

log = logging.getLogger(__name__)

BENCHMARK_DEFAULT = "XIC.TO"   # iShares Core S&P/TSX Composite


def _membership() -> dict | None:
    p = config.data_dir() / "baskets_canada" / "membership.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("canada baskets membership unreadable: %s", e)
        return None


def _closes() -> pd.DataFrame | None:
    """Wide [Date × ticker] adjusted closes for the canada_search universe (~220 TSX names)."""
    p = config.data_dir() / "canada_search" / "closes.parquet"
    if not p.exists():
        return None
    try:
        df = pd.read_parquet(p)
        df.index = pd.DatetimeIndex(df.index)
        return df.sort_index()
    except Exception as e:  # noqa: BLE001
        log.warning("canada_search closes unreadable: %s", e)
        return None


def compute_canada_baskets() -> dict | None:
    """Load the Canada data plane (canada_search closes + S&P/TSX benchmark + iShares
    sector-ETF proxies) and delegate the compute to engine.baskets_region. The loaders stay
    here so the tests can patch them."""
    mem = _membership()
    if not mem or not mem.get("baskets"):
        return None
    closes = _closes()
    bench = store.read("canada", mem.get("benchmark", BENCHMARK_DEFAULT))
    return compute_region_baskets(closes, mem, bench,
                                  lambda s: store.read("canada", s), name_key="name")


def member_closes_getter(closes: pd.DataFrame | None):
    """Return a callable(basket_dict) -> wide [Date × member-ticker] closes for the
    sector-ignition layer (engine.sector_ignition). Read-path only; None-safe."""
    def _get(b: dict) -> pd.DataFrame | None:
        if closes is None or closes.empty:
            return None
        tickers = [m.get("ticker") or m.get("symbol") for m in (b.get("members") or [])
                   if (m.get("ticker") or m.get("symbol"))]
        present = [t for t in tickers if t in closes.columns]
        if len(present) < 3:
            return None
        return closes[present]
    return _get
