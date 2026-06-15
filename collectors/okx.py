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

import numpy as np
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
        lsr = self._ls_account_ratio()
        if lsr is not None:
            out["ls_account_ratio"] = lsr
        tk = self._taker_volume()
        if tk is not None:
            out["taker_volume"] = tk
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

    def _ls_account_ratio(self) -> pd.DataFrame | None:
        """Rubik retail long/short ACCOUNT ratio (#accounts net-long ÷ #accounts
        net-short) — the breadth of retail positioning, distinct from funding (the
        price of leverage) and OI (notional). DISPLAY-ONLY contrarian context."""
        r = self.http_get(self.cfg["ls_ratio_url"], retries=self.cfg["retries"],
                          params={"ccy": "BTC", "period": "1D"}, timeout=30)
        data = r.json().get("data", [])
        if not data:
            return None
        # rows: [ts_ms, ratio]   ratio = #accounts long / #accounts short
        df = pd.DataFrame(data, columns=["ts", "ls_ratio"])
        df["date"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms").dt.normalize()
        df["ls_ratio"] = pd.to_numeric(df["ls_ratio"], errors="coerce")
        return df.set_index("date")[["ls_ratio"]].dropna().sort_index()

    def _taker_volume(self) -> pd.DataFrame | None:
        """Rubik aggregate taker buy/sell volume → buy share = buy/(buy+sell).
        instType=CONTRACTS = the leveraged perp/futures aggressive-flow read
        (on-thesis for the leverage card; SPOT is the broader spot-only series).
        DISPLAY-ONLY short-horizon order-flow imbalance context."""
        r = self.http_get(self.cfg["taker_url"], retries=self.cfg["retries"],
                          params={"ccy": "BTC", "instType": "CONTRACTS", "period": "1D"},
                          timeout=30)
        data = r.json().get("data", [])
        if not data:
            return None
        # rows: [ts_ms, sellVol, buyVol] (OKX v5 order is sell-then-buy — do NOT flip)
        df = pd.DataFrame(data, columns=["ts", "sell_vol", "buy_vol"])
        df["date"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms").dt.normalize()
        buy = pd.to_numeric(df["buy_vol"], errors="coerce")
        sell = pd.to_numeric(df["sell_vol"], errors="coerce")
        df["taker_buy_ratio"] = buy / (buy + sell).replace(0, np.nan)
        return df.set_index("date")[["taker_buy_ratio"]].dropna().sort_index()
