"""OKX public API collector (free, keyless, works from US — Binance/Bybit are
geo-blocked 451/403, verified 2026-06-12).

- funding_rate: BTC-USDT-SWAP 8h funding, aggregated to a daily mean. OKX pages
  backward 100 rows/req; we walk back until we meet stored history (or a page
  cap on first run). Deep funding history comes from bgeo (4y); OKX is the
  live append + cross-check.
- open_interest: rubik daily OI (USD) — recent window only; bgeo
  open-interest-futures carries the 4y history.
"""
from __future__ import annotations

import time

import pandas as pd

from collectors.base import Adapter
from lib import config, store

MAX_PAGES_FIRST_RUN = 30  # ~3000 funding prints ~ 1000 days


class OkxAdapter(Adapter):
    name = "okx"
    group = "okx"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load()["okx"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out = {}
        fr = self._funding(full_history)
        if fr is not None:
            out["funding_rate"] = fr
        oi = self._open_interest()
        if oi is not None:
            out["open_interest"] = oi
        if not out:
            raise ValueError("okx returned nothing")
        return out

    def _funding(self, full_history: bool) -> pd.DataFrame | None:
        last_stored = store.last_date(self.group, "funding_rate")
        rows: list[dict] = []
        after = ""  # cursor: returns records EARLIER than this fundingTime
        for _ in range(MAX_PAGES_FIRST_RUN):
            params = {"instId": self.cfg["inst_id"], "limit": "100"}
            if after:
                params["after"] = after
            r = self.http_get(self.cfg["funding_url"], retries=self.cfg["retries"],
                              params=params, timeout=30)
            data = r.json().get("data", [])
            if not data:
                break
            rows.extend(data)
            oldest = min(int(x["fundingTime"]) for x in data)
            after = str(oldest)
            if last_stored and not full_history:
                oldest_date = pd.to_datetime(oldest, unit="ms").date()
                if oldest_date <= last_stored:
                    break
            time.sleep(0.2)
        if not rows:
            return None
        df = pd.DataFrame(rows)
        df["rate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
        df["date"] = pd.to_datetime(pd.to_numeric(df["fundingTime"]), unit="ms").dt.normalize()
        daily = df.groupby("date")["rate"].mean().to_frame("funding_rate_okx")
        return daily.dropna()

    def _open_interest(self) -> pd.DataFrame | None:
        r = self.http_get(self.cfg["oi_url"], retries=self.cfg["retries"],
                          params={"ccy": "BTC", "period": "1D"}, timeout=30)
        data = r.json().get("data", [])
        if not data:
            return None
        # rows: [ts_ms, oi_usd, volume_usd]
        df = pd.DataFrame(data, columns=["ts", "oi_usd", "vol_usd"])
        df["date"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms").dt.normalize()
        df["oi_usd"] = pd.to_numeric(df["oi_usd"], errors="coerce")
        return df.set_index("date")[["oi_usd"]].dropna().sort_index()
