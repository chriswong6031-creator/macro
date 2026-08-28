"""China A-share per-name daily OHLC via yfinance + guarded Tencent tail repair.

The real HIGH/LOW feed the multi-country MACD-RSI x StochRSI confluence + buy-filter
need — versus the close+volume the index/ETF store ``data/china/`` keeps. Universe =
the committed A-share SEARCH universe (``data/china_search/closes.parquet``, ~1.5k
names) the China library already analyzes, unioned with a small config ``seed``
(committed up front; the rest backfills nightly — ``store.upsert`` is incremental).
Store mirrors ``data/stocks/*.parquet``: one parquet per ticker at
``data/china_stocks/<CODE>.SS|.SZ.parquet``.

Yahoo remains the canonical primary/deep-history source.  Tencent is a recent-tail
repair source only: after the primary pull, missing or market-stale names are checked
against Tencent qfq daily bars and may be extended only when the overlapping adjusted
close basis agrees.  Persistence still flows through this adapter's one existing
``china_stocks`` store; no second data plane is created.  See
``research/signal_engine/MULTICOUNTRY_DATA.md`` and
``research/china_native_data/SOURCE_CATALOG_MARKET.md``.
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors._stock_ohlc import fetch_ohlc, universe_columns
from collectors.base import Adapter
from collectors.china_stock_tencent import heal_adjusted_tails
from lib import config

log = logging.getLogger(__name__)


class ChinaStockPriceAdapter(Adapter):
    name = "china_stocks"
    group = "china_stocks"
    overwrite_overlap = True   # adjusted series: fresh window owns its whole overlap span

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["stock_prices"]

    def all_tickers(self) -> list[str]:
        return universe_columns("china_search/closes.parquet", self.cfg.get("seed", []))

    def fetch(self, full_history: bool = False,
              tickers: list[str] | None = None) -> dict[str, pd.DataFrame]:
        uni = tickers if tickers is not None else self.all_tickers()
        primary_error: RuntimeError | None = None
        try:
            frames = fetch_ohlc(uni, self.group, self.cfg, full_history)
        except RuntimeError as exc:
            # fetch_ohlc intentionally raises when Yahoo returns zero names.  For China,
            # that is precisely the outage class the independent Tencent repair lane is
            # meant to survive.  Do not call the run healthy unless Tencent actually
            # recovers at least one frame; otherwise re-raise the original primary error.
            primary_error = exc
            frames = {}
            log.warning("china_stocks: primary Yahoo plane returned zero frames; trying Tencent repair")

        frames = heal_adjusted_tails(frames, uni, self.group, self.cfg)
        if not frames:
            if primary_error is not None:
                raise primary_error
            raise RuntimeError(f"china_stocks: 0/{len(uni)} tickers returned data after repair")
        return frames
