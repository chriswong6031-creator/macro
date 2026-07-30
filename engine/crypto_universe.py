"""Display-only crypto market universe accrued from CoinGecko snapshots.

This module owns no trading authority.  It turns the one-row-per-day asset
parquets written by ``CryptoUniverseAdapter`` into a ranked market board and
reports history coverage honestly so a fresh series is never drawn as a
ninety-day chart.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from lib import config


def _number(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if np.isfinite(out) else None


def _state(change_30d: float | None, change_7d: float | None) -> tuple[str, str]:
    """Return restrained display state and tone from price follow-through."""
    guide = change_30d if change_30d is not None else change_7d
    if guide is None:
        return "Building", "neutral"
    if guide >= 15:
        return "Leading", "bull"
    if guide >= 3:
        return "Firm", "bull"
    if guide <= -15:
        return "Weak", "bear"
    if guide <= -3:
        return "Fading", "bear"
    return "Range", "neutral"


def _history_chip(days: int) -> str:
    if days >= 90:
        return "90D"
    if days >= 30:
        return f"{days}D"
    return "Building"


def load_universe(top_n: int = 50, root: Path | None = None) -> list[dict]:
    """Load ranked latest observations plus available daily price history."""
    root = root or (config.data_dir() / "crypto_universe")
    if not root.exists():
        return []

    rows: list[dict] = []
    for path in sorted(root.glob("market_*.parquet")):
        try:
            frame = pd.read_parquet(path).sort_index()
        except Exception:
            continue
        if frame.empty:
            continue
        current = frame.iloc[-1]
        rank = _number(current.get("market_cap_rank"))
        if rank is None or rank > top_n:
            continue
        prices = pd.to_numeric(frame.get("current_price"), errors="coerce").dropna()
        if prices.empty:
            continue
        c24 = _number(current.get("change_24h_pct"))
        c7 = _number(current.get("change_7d_pct"))
        c30 = _number(current.get("change_30d_pct"))
        state, tone = _state(c30, c7)
        hist = prices.tail(90)
        rows.append(
            {
                "id": str(current.get("coin_id") or path.stem.removeprefix("market_")),
                "source": str(current.get("source") or "CoinGecko"),
                "symbol": str(current.get("symbol") or "").upper(),
                "name": str(current.get("name") or current.get("symbol") or ""),
                "rank": int(rank),
                "price": _number(current.get("current_price")),
                "change_24h": c24,
                "change_7d": c7,
                "change_30d": c30,
                "market_cap": _number(current.get("market_cap")),
                "volume": _number(current.get("total_volume")),
                "state": state,
                "tone": tone,
                "history_days": int(len(hist)),
                "history_chip": _history_chip(int(len(hist))),
                "spark_dates": [str(pd.Timestamp(x).date()) for x in hist.index],
                "spark_values": [round(float(x), 8) for x in hist.to_numpy()],
                "as_of": str(pd.Timestamp(frame.index[-1]).date()),
            }
        )
    return sorted(rows, key=lambda x: (x["rank"], x["symbol"]))[:top_n]


def breadth_read(rows: list[dict]) -> dict:
    """Breadth receipt from accrued histories; absent until coverage is real."""
    eligible = [r for r in rows if r.get("history_days", 0) >= 30]
    if len(eligible) < 10:
        return {
            "available": False,
            "eligible": len(eligible),
            "required": 10,
            "value": None,
            "state": "Building history",
            "tone": "neutral",
        }
    positive = sum(1 for r in eligible if (r.get("change_30d") or 0) > 0)
    pct = round(100 * positive / len(eligible))
    tone = "bull" if pct >= 60 else ("bear" if pct <= 40 else "neutral")
    state = "Broad" if pct >= 60 else ("Narrow" if pct <= 40 else "Mixed")
    return {
        "available": True,
        "eligible": len(eligible),
        "required": 10,
        "value": pct,
        "state": state,
        "tone": tone,
    }
