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
        # Keep intraday High/Low for the volatility group (^VIX etc.) — the daily
        # VIX wick (intraday high vs close) is a washout / thin-quote tell that
        # engine/dislocation.py reads. Everything else stays close+volume to avoid
        # churning ~1500 parquets.
        ohlc = set(self.cfg["tickers"].get("vol", []))
        frames: dict[str, pd.DataFrame] = {}
        bs = self.cfg["batch_size"]
        for i in range(0, len(tickers), bs):
            batch = tickers[i:i + bs]
            df = self._download(batch, period)
            for t in batch:
                try:
                    sub = df[t] if isinstance(df.columns, pd.MultiIndex) else df
                    want = ["High", "Low", "Close", "Volume"] if t in ohlc else ["Close", "Volume"]
                    sub = sub[[c for c in want if c in sub.columns]].rename(
                        columns={"Close": "close", "Volume": "volume",
                                 "High": "high", "Low": "low"}).dropna(subset=["close"])
                    if not sub.empty:
                        frames[t] = sub
                except KeyError:
                    log.warning("yahoo: no data for %s", t)
        # Stooq fallback for searchable single stocks Yahoo refused this run.
        extras = config.load().get("stock_search", {}).get("extra_tickers", []) or []
        self._fill_missing_extras(frames, extras)
        if len(frames) < len(tickers) * 0.7:
            raise RuntimeError(f"yahoo returned only {len(frames)}/{len(tickers)} tickers")
        return frames

    def _fill_missing_extras(self, frames: dict[str, pd.DataFrame],
                             extras: list[str]) -> dict[str, pd.DataFrame]:
        """Best-effort Stooq backfill for extra_tickers Yahoo returned no data for.

        Yahoo intermittently 404s live large-caps (e.g. Marsh MMC, Fiserv FI —
        served only under stale symbols); without a fallback they never reach the
        store and drop out of the library. Bounded to the extra_tickers set (plain
        US symbols Stooq's ``.us`` feed understands, not crypto/futures/indices)
        and never fatal — Stooq is IP-gated, so a block just leaves the name
        missing, no worse than before."""
        missing = [t for t in extras if not str(t).startswith("^") and t not in frames]
        if not missing:
            return frames
        from lib import stooq
        recovered = []
        for t in missing:
            s = stooq.stooq_daily(t)
            if s is not None and not s.empty:
                frames[t] = s
                recovered.append(t)
        if recovered:
            log.info("yahoo: Stooq fallback recovered %d name(s): %s", len(recovered), recovered)
        still = [t for t in missing if t not in frames]
        if still:
            log.warning("yahoo: no data from Yahoo or Stooq for %s", still)
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
