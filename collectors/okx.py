"""OKX public API collector (free, keyless, works from US — Binance/Bybit are
geo-blocked 451/403, verified 2026-06-12).

- funding_rate: BTC-USDT-SWAP 8h funding, aggregated to a daily mean. OKX pages
  backward 100 rows/req; we walk back until we meet stored history (or a page
  cap on first run). Deep funding history comes from bgeo (4y); OKX is the
  live append + cross-check.
- open_interest: rubik daily OI (USD) — recent window only; bgeo
  open-interest-futures carries the 4y history.
- spot_usdt_daily: BTC-USDT SPOT daily candles (UTC) — the offshore-USDT reference
  the Coinbase Premium is measured against (Coinbase USD − OKX USDT). Self-owned and
  fresh, vs the quota-limited bgeo coinbase-premium-index. Paginates back to OKX's
  BTC-USDT spot floor (~2019) via the history-candles `after` cursor.
"""
from __future__ import annotations

import logging
import time

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

MAX_PAGES_FIRST_RUN = 30  # ~3000 funding prints ~ 1000 days


class OkxAdapter(Adapter):
    name = "okx"
    group = "okx"
    stale_after_days = 3
    # taker_volume_hourly keeps intraday timestamps; every DAILY series here
    # already self-normalizes its index to midnight (.dt.normalize()), so a
    # non-normalizing upsert is a no-op for them and only preserves the hourly
    # series (verified: all stored okx daily series are all-midnight).
    normalize_index = False

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
        try:                                  # rubik hourly outage must degrade ONLY this
            tkh = self._taker_volume_hourly()  # series, never fail the whole okx adapter
            if tkh is not None:                # (which would freeze the daily series + trip
                out["taker_volume_hourly"] = tkh  # the circuit breaker)
        except Exception as e:  # noqa: BLE001
            log.warning("okx taker_volume_hourly fetch failed (non-fatal): %s", e)
        sp = self._spot_candles(full_history)
        if sp is not None:
            out["spot_usdt_daily"] = sp
        if not out:
            raise ValueError("okx returned nothing")
        return out

    def validate(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        """taker_volume_hourly MUST keep its intraday timestamps — skip the
        base-class .normalize() for it (which would collapse 24 rows/day to 1 and
        silently defeat the hourly-CVD accrual). Every other okx series is daily
        and IS normalized. Mirrors CoinbaseAdapter.validate for btc_hourly."""
        if df is None or df.empty:
            raise ValueError(f"{self.name}/{name}: empty frame")
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        if name != "taker_volume_hourly":
            df.index = df.index.normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index().dropna(how="all")
        if df.empty:
            raise ValueError(f"{self.name}/{name}: all-NaN after cleaning")
        return df

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

    def _spot_candles(self, full_history: bool) -> pd.DataFrame | None:
        """BTC-USDT spot daily (UTC) OHLCV, paginated back via the history-candles
        `after` cursor (returns bars OLDER than the cursor ts). Incremental runs stop
        once they reach stored history; first runs walk back to OKX's spot floor."""
        last_stored = store.last_date(self.group, "spot_usdt_daily")
        inst = self.cfg.get("spot_inst_id", "BTC-USDT")
        bar = self.cfg.get("spot_bar", "1Dutc")
        max_pages = int(self.cfg.get("spot_max_pages_first_run", 40))
        pages = max_pages if (full_history or last_stored is None) else 4
        rows: list[list] = []
        after = ""  # cursor: history-candles returns records EARLIER than this ts
        for _ in range(pages):
            params = {"instId": inst, "bar": bar, "limit": "100"}
            if after:
                params["after"] = after
            r = self.http_get(self.cfg["spot_history_url"], retries=self.cfg["retries"],
                              params=params, timeout=30)
            data = r.json().get("data", [])
            if not data:
                break
            rows.extend(data)
            oldest = min(int(x[0]) for x in data)
            after = str(oldest)
            if last_stored and not full_history:
                if pd.to_datetime(oldest, unit="ms").date() <= last_stored:
                    break
            time.sleep(0.2)
        if not rows:
            return None
        # OKX candle row: [ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm]
        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "vol",
                                         "volccy", "volccyq", "confirm"])
        df = df[df["confirm"] == "1"]                       # closed candles only (no partial day)
        df.index = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms").dt.normalize()
        for c in ("open", "high", "low", "close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df["volume"] = pd.to_numeric(df["vol"], errors="coerce")
        out = df[["open", "high", "low", "close", "volume"]].dropna(subset=["close"])
        return out[~out.index.duplicated(keep="last")].sort_index()

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

    def _taker_volume_hourly(self) -> pd.DataFrame | None:
        """Rubik aggregate taker buy/sell volume at HOURLY granularity, raw
        volumes kept (not just the ratio) so engine/btc_intraday_cvd can build a
        cumulative-volume-delta (CVD = Σ(buy−sell)). The rubik 1H window is the
        last ~720 hours (~30 days), recent-only; store.upsert ACCUMULATES it
        forward so a deep hourly aggressor-flow history builds over time (the
        genuine sub-daily order-flow feed the impulse-radar screens lacked).
        DISPLAY-ONLY / accruing — never scored until it has the history to be
        validated by the falsifier gate."""
        r = self.http_get(self.cfg["taker_url"], retries=self.cfg["retries"],
                          params={"ccy": "BTC", "instType": "CONTRACTS", "period": "1H"},
                          timeout=30)
        data = r.json().get("data", [])
        if not data:
            return None
        # rows: [ts_ms, sellVol, buyVol] (OKX v5 order is sell-then-buy — do NOT flip)
        df = pd.DataFrame(data, columns=["ts", "sell_vol", "buy_vol"])
        df["ts"] = pd.to_datetime(pd.to_numeric(df["ts"]), unit="ms")
        df["taker_buy_vol"] = pd.to_numeric(df["buy_vol"], errors="coerce")
        df["taker_sell_vol"] = pd.to_numeric(df["sell_vol"], errors="coerce")
        return (df.set_index("ts")[["taker_buy_vol", "taker_sell_vol"]]
                .dropna().sort_index())
