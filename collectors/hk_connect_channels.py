"""Per-channel Southbound Stock Connect history (港股通) — mainland buying HK.

Eastmoney historical Southbound flows, split into the TWO mainland legs that feed
Hong Kong, wrapped keyless by akshare:

  ak.stock_hsgt_hist_em(symbol="港股通沪")  Shanghai → HK leg   (~2.6k rows, back to 2014-11)
  ak.stock_hsgt_hist_em(symbol="港股通深")  Shenzhen → HK leg   (~2.2k rows, back to 2016-12)

Each frame is a clean DAILY series. Stored under group `hk_connect`, one parquet
per channel:
  southbound_sh · southbound_sz

Columns (snake_case, mirroring collectors/china_connect.py where they overlap):
  net          当日成交净买额  — daily net buy (亿元 / 100M yuan); z-scored downstream
  buy          买入成交额      — daily buy turnover
  sell         卖出成交额      — daily sell turnover
  cum          历史累计净买额  — cumulative net since inception (亿元, monotone-ish)
  hold_mktcap  持股市值        — cumulative mainland holdings of HK shares (raw yuan)
  hsi          恒生指数        — the Hang Seng level on that date (context, display-only)

This is ADDITIVE to the canonical combined Southbound leg in
data/china_connect/southbound (RPT_MUTUAL_DEAL_HISTORY, MUTUAL_TYPE 006), which
stays the primary source; this collector exposes the SH/SZ channel split.

GOTCHAS:
  * akshare hits its own backends and raises ConnectionError / RemoteDisconnected
    (not HTTP status codes) when the host is flaky, so every ak call is wrapped in
    an explicit retry loop with exponential backoff (akshare ignores requests-level
    retry helpers entirely).
  * `历史累计净买额` is already denominated in 亿元 (~3.1), NOT raw yuan — do NOT
    rescale it; `持股市值` IS raw yuan (~6e12).
  * Per-channel isolation: a single dead leg logs a warning and the other proceeds;
    only an all-channels failure raises so the circuit breaker can act.
  * Multi-column frames keep store.upsert's single-column outlier guard OFF — flows
    legitimately spike and those prints must be preserved, not clipped.
"""
from __future__ import annotations

import logging
import time

import akshare as ak
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# stored series -> akshare channel symbol
_CHANNELS = {
    "southbound_sh": "港股通沪",
    "southbound_sz": "港股通深",
}
# stored_col -> source column (akshare Chinese header)
_FIELDS = {
    "net":         "当日成交净买额",
    "buy":         "买入成交额",
    "sell":        "卖出成交额",
    "cum":         "历史累计净买额",
    "hold_mktcap": "持股市值",
    "hsi":         "恒生指数",
}


class HkConnectChannelsAdapter(Adapter):
    name = "hk_connect_channels"
    group = "hk_connect"
    stale_after_days = 6   # trading-day series; tolerate a long weekend / holiday

    def __init__(self) -> None:
        self.cfg = config.load().get("hk", {}).get("connect_channels", {}) or {}
        want = self.cfg.get("series") or list(_CHANNELS)
        self.series = [s for s in want if s in _CHANNELS]
        self.retries = 3
        self.backoff_base = 3.0

    def _ak_hist(self, symbol: str) -> pd.DataFrame:
        """akshare call wrapped in the explicit retry loop (it raises ConnectionError
        / RemoteDisconnected, not HTTP codes, so requests-level retries don't apply)."""
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                return ak.stock_hsgt_hist_em(symbol=symbol)
            except Exception as e:  # noqa: BLE001 — retried, then surfaced per-series
                last_exc = e
                if attempt < self.retries - 1:
                    wait = self.backoff_base * (2 ** attempt)
                    log.warning("hk_connect_channels ak %s attempt %d/%d failed (%s); "
                                "retry in %.0fs", symbol, attempt + 1, self.retries, e, wait)
                    time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def _channel(self, symbol: str) -> pd.DataFrame:
        raw = self._ak_hist(symbol)
        if raw is None or raw.empty or "日期" not in raw.columns:
            raise ValueError("empty / no date column")
        out = pd.DataFrame(index=pd.to_datetime(raw["日期"]))
        for stored, src in _FIELDS.items():
            if src in raw.columns:
                out[stored] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
        out = out.dropna(how="all").sort_index()
        if out.empty or "net" not in out.columns:
            raise ValueError("no usable net rows")
        return out

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # stock_hsgt_hist_em always returns the FULL daily history; incremental and
        # backfill runs are identical (store.upsert dedupes on date).
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for name in self.series:
            try:
                frames[name] = self._channel(_CHANNELS[name])
            except Exception as e:  # noqa: BLE001 — per-channel isolation
                errors.append(f"{name}: {e}")
                log.warning("hk_connect_channels %s failed: %s", name, e)
        if not frames:
            raise RuntimeError("hk_connect_channels: all channels failed — "
                               + " | ".join(errors))
        if errors:
            log.info("hk_connect_channels: %d/%d channels ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
