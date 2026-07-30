"""Coinbase Exchange public candles collector (free, keyless).

Four series:
- btc_daily:  OHLCV from 2015-07 (intraday-quality, complements Yahoo's 2014->)
- btc_hourly: OHLCV from 2016 (~92k rows) — REQUIRED for Phase 2 flash-crash
  state-machine calibration (intraday vs interday vol split, Key Risk Elements).
- eth_daily:  ETH-USD OHLCV from its Coinbase listing date.
- sol_daily:  SOL-USD OHLCV from its Coinbase listing date.

API: GET /products/{product}/candles?start&end&granularity
     -> [[epoch, low, high, open, close, volume], ...] newest-first, max 300/req.
Public rate limit ~10 req/s; we pace at cfg.pace_seconds. Full hourly backfill
is ~310 requests (~2 min) and runs only with --full-history or when the series
is missing; daily runs append the gap since the last stored candle.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

COLS = ["low", "high", "open", "close", "volume"]


class CoinbaseAdapter(Adapter):
    name = "coinbase"
    group = "coinbase"
    stale_after_days = 2
    normalize_index = False  # btc_hourly keeps intraday timestamps; daily is
    # normalized in validate() below

    def __init__(self) -> None:
        self.cfg = config.load()["coinbase"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        out["btc_daily"] = self._candles(
            "btc_daily", "BTC-USD", 86400, self.cfg["earliest"], full_history
        )
        out["btc_hourly"] = self._candles(
            "btc_hourly", "BTC-USD", 3600, self.cfg["hourly_earliest"], full_history
        )
        out["eth_daily"] = self._candles(
            "eth_daily", "ETH-USD", 86400, self.cfg["eth_earliest"], full_history
        )
        out["sol_daily"] = self._candles(
            "sol_daily", "SOL-USD", 86400, self.cfg["sol_earliest"], full_history
        )
        return out

    def _candles(self, series: str, product: str, granularity: int, earliest: str,
                 full_history: bool) -> pd.DataFrame:
        stored = store.read(self.group, series)
        if full_history or stored is None or stored.empty:
            start = datetime.fromisoformat(earliest).replace(tzinfo=timezone.utc)
        else:
            # hourly index is stored naive-UTC; resume a little before the end
            start = stored.index.max().to_pydatetime().replace(tzinfo=timezone.utc) \
                    - timedelta(seconds=2 * granularity)
        end = datetime.now(timezone.utc)

        frames: list[pd.DataFrame] = []
        step = timedelta(seconds=granularity * 300)
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + step, end)
            r = self.http_get(
                self.cfg["candles_url"].format(product=product),
                retries=self.cfg["retries"],
                params={"granularity": str(granularity),
                        "start": cursor.isoformat(),
                        "end": chunk_end.isoformat()},
                timeout=30,
            )
            data = r.json()
            if isinstance(data, list) and data:
                df = pd.DataFrame(data, columns=["ts", *COLS])
                frames.append(df)
            cursor = chunk_end
            time.sleep(float(self.cfg["pace_seconds"]))

        if not frames:
            raise ValueError(f"coinbase {series}: no candles returned")
        allf = pd.concat(frames, ignore_index=True)
        allf["date"] = pd.to_datetime(allf["ts"], unit="s")
        allf = allf.drop(columns=["ts"]).set_index("date").sort_index()
        allf = allf[~allf.index.duplicated(keep="last")]
        return allf.astype(float)

    def validate(self, name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Hourly candles must keep their intraday timestamps — skip the
        base-class .normalize() (which would collapse 24 rows/day to 1)."""
        if df is None or df.empty:
            raise ValueError(f"{self.name}/{name}: empty frame")
        df = df.copy()
        df.index = pd.to_datetime(df.index)
        if name.endswith("_daily"):
            df.index = df.index.normalize()
        df = df[~df.index.duplicated(keep="last")].sort_index().dropna(how="all")
        if df.empty:
            raise ValueError(f"{self.name}/{name}: all-NaN after cleaning")
        return df
