"""China A-share prices via yfinance — Plane A of the China dashboard.

Stores EOD adjusted close (+ volume) per ticker under data/china/, exactly like
collectors/yahoo.py does for the US universe (the US data/yahoo/ namespace is left
untouched). Universe = headline indices + the mainland sector-ETF complex + FX,
all from config["china"]["yahoo"]. The curated constituent stocks are pulled
separately by collectors/china_breadth.py (they power breadth + the search library).

yfinance handles .SS/.SZ symbols cleanly (verified 2026-06-12: Shanghai Composite
000001.SS -> 1997, sector ETFs ~2019-21->). Unofficial API, replaceable by design.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class ChinaPriceAdapter(Adapter):
    name = "china_prices"
    group = "china"

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["yahoo"]

    def all_tickers(self) -> list[str]:
        out: list[str] = list(self.cfg["indices"].keys())
        out += list(self.cfg["sector_etfs"].keys())
        out += list(self.cfg["fx"].keys())
        return list(dict.fromkeys(out))

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        tickers = self.all_tickers()
        period = "max" if full_history else "1mo"
        frames: dict[str, pd.DataFrame] = {}
        bs = self.cfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            df = self._download(batch, period)
            for t in batch:
                try:
                    sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                    sub = sub[["Close", "Volume"]].rename(
                        columns={"Close": "close", "Volume": "volume"}).dropna(subset=["close"])
                    if not sub.empty:
                        frames[t] = sub
                except KeyError:
                    log.warning("china_prices: no data for %s", t)
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"china_prices returned only {len(frames)}/{len(tickers)} tickers")
        return frames

    def _download(self, batch: list[str], period: str) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.cfg["retries"]):
            try:
                df = yf.download(batch, period=period, auto_adjust=True,
                                 progress=False, group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty yfinance response")
                return df
            except Exception as e:  # noqa: BLE001
                last_exc = e
                wait = self.cfg["backoff_base_s"] * (2 ** attempt)
                log.warning("china_prices batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]
