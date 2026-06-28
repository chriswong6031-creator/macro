"""Hong Kong per-name daily OHLC via yfinance (group=hk_stocks).

The real HIGH/LOW feed the multi-country MACD-RSI x StochRSI confluence + buy-filter
need — versus the close+volume the index store ``data/hk/`` keeps (and the close-only
``site/hkstockdata/<CODE>.HK.json`` charts). Universe = the committed HK breadth /
search universe (``data/hk_breadth/_closes_cache.parquet``, ~160 names), unioned with
a small config ``seed`` (committed up front; the rest backfills nightly —
``store.upsert`` is incremental). Store mirrors ``data/stocks/*.parquet``: one parquet
per ticker at ``data/hk_stocks/<CODE>.HK.parquet``. yfinance ``.HK`` already matches
the ``data/hk`` namespace -> no remap. See research/signal_engine/MULTICOUNTRY_DATA.md.
"""
from __future__ import annotations

import pandas as pd

from collectors._stock_ohlc import fetch_ohlc, universe_columns
from collectors.base import Adapter
from lib import config


class HkStockPriceAdapter(Adapter):
    name = "hk_stocks"
    group = "hk_stocks"

    def __init__(self) -> None:
        self.cfg = config.load()["hk"]["stock_prices"]

    def all_tickers(self) -> list[str]:
        return universe_columns("hk_breadth/_closes_cache.parquet", self.cfg.get("seed", []))

    def fetch(self, full_history: bool = False,
              tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
        uni = tickers if tickers is not None else self.all_tickers()
        return fetch_ohlc(uni, self.group, self.cfg, full_history)
