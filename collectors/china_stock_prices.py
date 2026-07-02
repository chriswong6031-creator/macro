"""China A-share per-name daily OHLC via yfinance (group=china_stocks).

The real HIGH/LOW feed the multi-country MACD-RSI x StochRSI confluence + buy-filter
need — versus the close+volume the index/ETF store ``data/china/`` keeps. Universe =
the committed A-share SEARCH universe (``data/china_search/closes.parquet``, ~1.5k
names) the China library already analyzes, unioned with a small config ``seed``
(committed up front; the rest backfills nightly — ``store.upsert`` is incremental).
Store mirrors ``data/stocks/*.parquet``: one parquet per ticker at
``data/china_stocks/<CODE>.SS|.SZ.parquet``. yfinance ``.SS``/``.SZ`` already match
the ``data/china`` namespace -> no remap. See research/signal_engine/MULTICOUNTRY_DATA.md.
"""
from __future__ import annotations

import pandas as pd

from collectors._stock_ohlc import fetch_ohlc, universe_columns
from collectors.base import Adapter
from lib import config


class ChinaStockPriceAdapter(Adapter):
    name = "china_stocks"
    group = "china_stocks"
    overwrite_overlap = True   # yfinance auto_adjust=True → seam-free re-adjust of the refresh window

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["stock_prices"]

    def all_tickers(self) -> list[str]:
        return universe_columns("china_search/closes.parquet", self.cfg.get("seed", []))

    def fetch(self, full_history: bool = False,
              tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
        uni = tickers if tickers is not None else self.all_tickers()
        return fetch_ohlc(uni, self.group, self.cfg, full_history)
