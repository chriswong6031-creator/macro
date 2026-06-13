"""Yahoo Finance collector via yfinance — unofficial API, replaceable by design.

Stores EOD adjusted close (+ volume) per ticker under data/yahoo/. Daily runs
fetch a short overlap window and upsert; backfill fetches max history.
"""
from __future__ import annotations

import logging
import time

import pandas as pd
import yfinance as yf

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class YahooAdapter(Adapter):
    name = "yahoo"
    group = "yahoo"

    def __init__(self) -> None:
        self.cfg = config.load()["yahoo"]

    def all_tickers(self) -> list[str]:
        out: list[str] = []
        for grp in self.cfg["tickers"].values():
            out.extend(grp)
        # stock_search.extra_tickers must be collected here or they can never be
        # searched (build_stock_library reads data/yahoo/<t>.parquet for them).
        # Skip ^-prefixed index symbols — they belong in the tickers groups.
        extra = config.load().get("stock_search", {}).get("extra_tickers", []) or []
        out.extend(t for t in extra if not str(t).startswith("^"))
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
                    log.warning("yahoo: no data for %s", t)
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"yahoo returned only {len(frames)}/{len(tickers)} tickers")
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
                log.warning("yfinance batch failed (%s); retry in %.0fs", e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]
