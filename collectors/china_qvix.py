"""China implied-volatility ("the China VIX") — Plane A sentiment input.

Option-implied 30-day vol for the 300ETF (沪深300 510300) and 50ETF (上证50
510050) index options, the de-facto A-share fear gauges. Source = optbbs QVIX
(1.optbbs.com), the long-running free aggregator akshare wraps — keyless, history
back to 2015 (~2700 rows). Single non-exchange host, so this degrades to
"missing" if it's down (the circuit breaker notices); the engine never depends
on it. Stored under group `china_qvix`, one parquet per underlying:
  qvix300 · qvix50   (columns: close = the headline 30d IV, open = prior session)

We store TWO columns so store.upsert's single-column outlier guard stays off — a
volatility series legitimately spikes (2015 crash, 2024 Feb), and we must keep
those prints, not clip them as outliers.
"""
from __future__ import annotations

import logging

import akshare as ak
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# stored series -> akshare fetcher
_FETCHERS = {
    "qvix300": ak.index_option_300etf_qvix,
    "qvix50": ak.index_option_50etf_qvix,
}


class ChinaQvixAdapter(Adapter):
    name = "china_qvix"
    group = "china_qvix"
    stale_after_days = 6   # trading-day series; tolerate a long weekend / holiday

    def __init__(self) -> None:
        self.cfg = config.load().get("china", {}).get("qvix", {}) or {}
        want = self.cfg.get("series") or list(_FETCHERS)
        self.series = [s for s in want if s in _FETCHERS]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for name in self.series:
            try:
                raw = _FETCHERS[name]()
                if raw is None or raw.empty or "date" not in raw.columns:
                    raise ValueError("empty / no date column")
                df = pd.DataFrame(index=pd.to_datetime(raw["date"]))
                df["close"] = pd.to_numeric(raw["close"], errors="coerce").to_numpy()
                if "open" in raw.columns:
                    df["open"] = pd.to_numeric(raw["open"], errors="coerce").to_numpy()
                df = df.dropna(subset=["close"]).sort_index()
                if df.empty:
                    raise ValueError("no usable close values")
                frames[name] = df
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{name}: {e}")
                log.warning("china_qvix series %s failed: %s", name, e)
        if not frames:
            raise RuntimeError("china_qvix: all series failed — " + " | ".join(errors))
        if errors:
            log.info("china_qvix: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
