"""CoinMetrics Community API collector (free, no key).

Deep-history backbone for the Bitcoin Vector engine: MVRV/mcap/addresses/
hashrate back to 2010 at 1d frequency. Community tier serves only the metrics
listed in config (others return 403 'forbidden' — verified 2026-06-12).

Derivations downstream (engine, not here): realized_cap = mcap/mvrv,
NUPL = 1 - 1/mvrv.

Rate limits: 6000 req / 20s sliding window per IP — irrelevant at our 1 call/run.
All requested metrics come back in a single paged call.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from collectors.base import Adapter
from lib import config, store


class CoinMetricsAdapter(Adapter):
    name = "coinmetrics"
    group = "coinmetrics"
    stale_after_days = 4  # community data lands T-1/T-2

    def __init__(self) -> None:
        self.cfg = config.load()["coinmetrics"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        metrics = self.cfg["metrics"]
        if full_history:
            start = self.cfg["start_date"]
        else:
            last = self.last_good_date() or date.fromisoformat(self.cfg["start_date"])
            start = str(last - timedelta(days=5))

        params = {
            "assets": self.cfg["asset"],
            "metrics": ",".join(metrics.keys()),
            "frequency": "1d",
            "page_size": str(self.cfg["page_size"]),
            "start_time": start,
        }
        rows: list[dict] = []
        url = self.cfg["base_url"]
        while True:
            r = self.http_get(url, retries=self.cfg["retries"], params=params, timeout=120)
            j = r.json()
            rows.extend(j.get("data", []))
            nxt = j.get("next_page_token")
            if not nxt:
                break
            params["next_page_token"] = nxt

        if not rows:
            raise ValueError("coinmetrics returned no rows")

        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["time"]).dt.tz_localize(None).dt.normalize()
        out: dict[str, pd.DataFrame] = {}
        for metric, col in metrics.items():
            if metric not in df.columns:
                continue  # metric absent from response — soft-skip, others proceed
            s = pd.to_numeric(df[metric], errors="coerce")
            frame = pd.DataFrame({col: s.values}, index=df["date"]).dropna()
            if not frame.empty:
                out[col] = frame
        if not out:
            raise ValueError("coinmetrics: no usable metric columns in response")
        return out
