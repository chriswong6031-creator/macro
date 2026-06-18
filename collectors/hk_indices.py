"""Hang Seng TECH index — true HSTECH OHLCV, retiring the 3033.HK ETF proxy.

Plane-A price input for the HK / Hang Seng dashboard. ^HSTECH is NOT on Yahoo, so
collectors/hk_prices.py has been standing in the CSOP HS TECH ETF (3033.HK, 2020->)
for the tech-growth tilt. This collector pulls the *actual* Hang Seng TECH index
level so engine/hk_inputs can read it identically to data/hk/_HSI.parquet (same
'close' column + DatetimeIndex), no ETF tracking-error / dividend-drag baggage.

Source (akshare, keyless):
  PRIMARY  ak.stock_hk_index_daily_sina(symbol="HSTECH")
             -> columns: date, open, high, low, close, volume, amount  (history from
                2020-08-17, ~1.4k rows; clean English column names, live-verified
                2026-06-17). Single free host (新浪) so it degrades to "missing".
  BACKUP   ak.stock_hk_index_daily_em(symbol="HSTECH")
             -> Eastmoney mirror with CHINESE column names (日期/开盘/收盘/最高/最低/
                成交量/成交额). Only consulted when sina yields nothing.

Stored under group "hk" (so it lands next to _HSI / _HSCE / _HSCC), one parquet:
  HSTECH   columns: open, high, low, close, volume  (DatetimeIndex)

GOTCHAS
- akshare raises ConnectionError / RemoteDisconnected (NOT HTTP status codes) when
  the upstream host blips, so every akshare call is wrapped in an explicit
  retry/backoff loop (self.http_get only covers requests-based scrapers).
- The Eastmoney `_em` mirror is the flakier of the two (observed RemoteDisconnected
  in-sandbox); it is a best-effort fallback only — the run never depends on it.
- Multi-column OHLCV frame -> the runner passes outlier_col=None, so legitimate
  index spikes are never clipped (same reasoning as china_qvix's 2-column store).
- DISPLAY-ONLY price history; absence is tolerated (stale_after_days=6 covers a
  long weekend / HK public holiday).
"""
from __future__ import annotations

import logging
import time

import akshare as ak
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_SYMBOL = "HSTECH"
# canonical stored cols -> possible source headers (sina English, em Chinese)
_COLMAP = {
    "open":   ("open", "开盘"),
    "high":   ("high", "最高"),
    "low":    ("low", "最低"),
    "close":  ("close", "收盘"),
    "volume": ("volume", "成交量"),
}
_DATE_KEYS = ("date", "日期")


class HkIndicesAdapter(Adapter):
    """True Hang Seng TECH (HSTECH) index OHLCV, stored under group `hk`."""

    name = "hk_indices"
    group = "hk"
    stale_after_days = 6   # trading-day series; tolerate a long weekend / HK holiday

    def __init__(self) -> None:
        self.cfg = config.load().get("hk", {}).get("indices", {}) or {}
        self.symbol = self.cfg.get("hstech_symbol", _SYMBOL)
        # stored name is PINNED to the constant (not config-overridable): build_hk reads
        # store('hk','HSTECH') by literal, so a config override would silently desync them.
        self.stored_name = _SYMBOL
        self.retries = int(self.cfg.get("retries", 3))
        self.backoff_base = float(self.cfg.get("backoff_base_s", 3.0))

    # -- akshare call wrapped in the canonical retry loop ----------------------
    def _ak_call(self, fn) -> pd.DataFrame:
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                return fn(symbol=self.symbol)
            except Exception as e:  # noqa: BLE001 — akshare raises ConnectionError, not HTTP
                last_exc = e
                if attempt == self.retries - 1:
                    raise
                wait = self.backoff_base * (2 ** attempt)
                log.warning("hk_indices %s attempt %d/%d failed (%s); retry in %.0fs",
                            getattr(fn, "__name__", "ak"), attempt + 1, self.retries, e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _normalize(self, raw: pd.DataFrame) -> pd.DataFrame:
        if raw is None or raw.empty:
            raise ValueError("empty frame")
        date_col = next((k for k in _DATE_KEYS if k in raw.columns), None)
        if date_col is None:
            raise ValueError(f"no date column (have {list(raw.columns)})")
        out = pd.DataFrame(index=pd.to_datetime(raw[date_col]))
        for stored, candidates in _COLMAP.items():
            src = next((c for c in candidates if c in raw.columns), None)
            if src is not None:
                out[stored] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
        if "close" not in out.columns:
            raise ValueError(f"no close column (have {list(raw.columns)})")
        out = out.dropna(subset=["close"]).sort_index()
        if out.empty:
            raise ValueError("no usable close values")
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # both wrappers return the full daily history; there is no incremental param,
        # so full_history is moot — store.upsert merges the overlap append-only.
        sources = (
            ("sina", ak.stock_hk_index_daily_sina),
            ("em", ak.stock_hk_index_daily_em),
        )
        errors: list[str] = []
        for label, fn in sources:
            try:
                df = self._normalize(self._ak_call(fn))
                if errors:
                    log.info("hk_indices: served HSTECH via %s backup (sina skipped: %s)",
                             label, "; ".join(errors))
                return {self.stored_name: df}
            except Exception as e:  # noqa: BLE001 — per-source isolation, fall through to backup
                errors.append(f"{label}: {e}")
                log.warning("hk_indices %s source failed: %s", label, e)
        # every source dead -> raise so the circuit breaker can act (this is a real
        # outage, not a fragile single-purpose source: two independent hosts)
        raise RuntimeError("hk_indices: all HSTECH sources failed — " + " | ".join(errors))
