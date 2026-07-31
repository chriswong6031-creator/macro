"""Latest completed-session share volume for navigation search ranking.

The ticker libraries remain the browser's search authority.  This helper adds a
small, display-only ``v`` field to each index row so the empty search state can
rank names by actual trading activity instead of falling back to alphabetical
file order.  It never participates in an engine score, signal, gate or sizing
decision.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from lib import config


_DEEP_DIR = {
    "us": "stocks",
    "cn": "china_stocks",
    "hk": "hk_stocks",
}

_MEMBERS_DIR = {
    "ca": "canada_search",
    "intl": "intl_search",
}


def _positive_number(value) -> int | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(number) or number <= 0:
        return None
    return int(round(number))


def _last_volume(path: Path) -> int | None:
    try:
        frame = pd.read_parquet(path, columns=["volume"])
    except Exception:
        return None
    if "volume" not in frame.columns:
        return None
    values = pd.to_numeric(frame["volume"], errors="coerce").dropna()
    return _positive_number(values.iloc[-1]) if not values.empty else None


@lru_cache(maxsize=8)
def latest_volume_map(market: str) -> dict[str, int]:
    """Return ticker -> latest completed-session share volume.

    US/CN/HK use the canonical per-ticker OHLCV stores.  Canada/International
    use the search-universe member snapshot populated by their yfinance
    collectors.  Missing coverage is omitted so the client can retain its
    deterministic curated-order fallback.
    """
    root = config.data_dir()
    out: dict[str, int] = {}
    deep = _DEEP_DIR.get(market)
    if deep:
        directory = root / deep
        if directory.exists():
            for path in directory.glob("*.parquet"):
                volume = _last_volume(path)
                if volume is not None:
                    out[path.stem] = volume
        return out

    members_dir = _MEMBERS_DIR.get(market)
    if not members_dir:
        return out
    path = root / members_dir / "members.parquet"
    if not path.exists():
        return out
    try:
        members = pd.read_parquet(path)
    except Exception:
        return out
    if "volume" not in members.columns:
        return out
    for ticker, value in members["volume"].items():
        volume = _positive_number(value)
        if volume is not None:
            out[str(ticker)] = volume
    return out


def attach_latest_volume(index_row: dict, ticker: str, volumes: dict[str, int]) -> None:
    """Attach the compact browser field only when a real volume is available."""
    volume = volumes.get(ticker)
    if volume is not None:
        index_row["v"] = volume
