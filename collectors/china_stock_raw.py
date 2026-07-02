"""China A-share per-name RAW (nominal) daily OHLC via yfinance (group=china_stocks_raw).

THE RAW PRICE PLANE. Every other A-share close in this repo is dividend/split-ADJUSTED
(``auto_adjust=True`` total-return — collectors/_stock_ohlc.py + collectors/china_universe.py),
which is correct for the confluence/reversal SIGNALS but WRONG for anything that reads a
price LEVEL: 5%/10%/20% limit-up/limit-down bands, overnight gaps, the pinned-at-limit
reference-close flag, and an honest A/H premium (an adjusted H-share close back-adjusts
more on high-yield pairs, biasing the premium structurally low). Before this collector
NO raw A-share close existed anywhere in the repo, so all of that logic ran on a plane
that silently drifts from the tradable print after every ex-dividend.

This collector mirrors the adjusted ``china_stocks`` store byte-for-byte EXCEPT for
``auto_adjust=False`` and a distinct group, so the two planes never mix. Same universe
(the committed A-share SEARCH set), same OHLC columns, same incremental backfill.

Store: one parquet per ticker at ``data/china_stocks_raw/<CODE>.SS|.SZ.parquet``,
columns ``[close, high, low, volume]`` — RAW (never re-adjusted; a raw print is final,
so upsert stays combine_first / append-only, NOT overwrite_overlap).

Coverage accrues forward + a one-off ``--full`` backfill of whatever yfinance serves
(yfinance returns full raw history for .SS/.SZ when auto_adjust=False). See
research/ENGINE_FIX_MASTERPLAN.md §W6-CN fix 3.
"""
from __future__ import annotations

from collectors._stock_ohlc import fetch_ohlc, universe_columns
from collectors.base import Adapter
from lib import config


class ChinaStockRawPriceAdapter(Adapter):
    name = "china_stocks_raw"
    group = "china_stocks_raw"
    stale_after_days = 5
    # RAW prints are final and never re-adjusted → the default append-only combine_first
    # is correct here (unlike the adjusted plane, which needs overwrite_overlap).
    overwrite_overlap = False

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["stock_prices"]

    def all_tickers(self) -> list[str]:
        return universe_columns("china_search/closes.parquet", self.cfg.get("seed", []))

    def fetch(self, full_history: bool = False,
              tickers: list[str] | None = None) -> dict:
        uni = tickers if tickers is not None else self.all_tickers()
        return fetch_ohlc(uni, self.group, self.cfg, full_history, auto_adjust=False)
