"""Cross-sectional confirmation receipts for international turn states.

The primary turn state intentionally remains index-led.  This leaf adds an
independent breadth check from liquid peer gauges (sector ETF or bellwethers)
so a broad rebound cannot be hidden by the index's drawdown memory.  It is
descriptive, causal, deterministic, and never promotes a trade or changes risk
sizing.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Optional

import numpy as np
import pandas as pd


def _clean_asof(series: pd.Series, as_of: pd.Timestamp) -> pd.Series:
    """Return finite observations at or before ``as_of`` with a naive index."""
    s = pd.to_numeric(series, errors="coerce").dropna().sort_index()
    if s.empty:
        return s
    idx = pd.DatetimeIndex(pd.to_datetime(s.index))
    if idx.tz is not None:
        idx = idx.tz_convert(None)
    s = pd.Series(s.to_numpy(dtype=float), index=idx)
    return s.loc[:as_of]


def breadth_snapshot(
    peers: Mapping[str, pd.Series],
    *,
    as_of: Optional[pd.Timestamp] = None,
    max_stale_business_days: int = 3,
) -> dict:
    """Summarize 5/20-session breadth across independent peer price series.

    Each peer is evaluated on its own trading calendar.  A stale series is
    excluded instead of forward-filled through an unknown move.
    """
    if as_of is None:
        last_dates = [
            pd.Timestamp(s.dropna().index[-1])
            for s in peers.values()
            if s is not None and not s.dropna().empty
        ]
        if not last_dates:
            return {}
        as_of = max(last_dates)
    as_of = pd.Timestamp(as_of)
    if as_of.tz is not None:
        as_of = as_of.tz_convert(None)
    as_of = as_of.normalize()

    rows: list[dict] = []
    for name, raw in peers.items():
        if raw is None:
            continue
        s = _clean_asof(raw, as_of)
        if s.empty:
            continue
        last_date = pd.Timestamp(s.index[-1]).normalize()
        stale_days = int(np.busday_count(last_date.date(), as_of.date()))
        if stale_days > max_stale_business_days or len(s) < 21:
            continue
        r5 = (float(s.iloc[-1]) / float(s.iloc[-6]) - 1.0) * 100.0
        r20 = (float(s.iloc[-1]) / float(s.iloc[-21]) - 1.0) * 100.0
        rows.append({
            "name": name,
            "as_of": last_date.strftime("%Y-%m-%d"),
            "ret5_pct": round(r5, 2),
            "ret20_pct": round(r20, 2),
        })

    def _window(days: int) -> dict:
        key = f"ret{days}_pct"
        vals = [float(row[key]) for row in rows]
        positive = sum(v > 0.0 for v in vals)
        n = len(vals)
        return {
            "positive": positive,
            "available": n,
            "breadth_pct": round(100.0 * positive / n, 1) if n else None,
            "median_return_pct": round(float(np.median(vals)), 2) if vals else None,
        }

    w5 = _window(5)
    w20 = _window(20)
    n = len(rows)
    if not n:
        return {}

    broad_rebound = (
        (w20["breadth_pct"] or 0.0) >= 75.0
        and (w20["median_return_pct"] or 0.0) >= 3.0
    )
    short_fading = (
        (w5["breadth_pct"] or 0.0) <= 50.0
        or (w5["median_return_pct"] is not None and w5["median_return_pct"] < 0.0)
    )
    broad_decline = (
        (w20["breadth_pct"] or 100.0) <= 25.0
        and (w20["median_return_pct"] or 0.0) <= -3.0
    )

    if broad_rebound and short_fading:
        direction = "broad_rebound_fading"
        read_en = (
            f"Breadth check: {w20['positive']}/{w20['available']} liquid tech gauges "
            f"are still up over 20 sessions, but only {w5['positive']}/{w5['available']} "
            "are up over 5 — a broad rebound whose short-term momentum is fading."
        )
        read_zh = (
            f"广度核验：{w20['available']}个高流动性科技指标中有{w20['positive']}个近20日仍上涨，"
            f"但近5日仅{w5['positive']}/{w5['available']}上涨——反弹广泛，但短期动能正在减弱。"
        )
    elif broad_rebound:
        direction = "broad_rebound"
        read_en = (
            f"Breadth check: {w20['positive']}/{w20['available']} liquid tech gauges "
            "are up over 20 sessions — the rebound is broad, not a one-stock illusion."
        )
        read_zh = (
            f"广度核验：{w20['available']}个高流动性科技指标中有{w20['positive']}个近20日上涨"
            "——反弹覆盖面广，并非由单一个股造成。"
        )
    elif broad_decline:
        direction = "broad_decline"
        read_en = (
            f"Breadth check: only {w20['positive']}/{w20['available']} liquid tech gauges "
            "are up over 20 sessions — weakness is broad."
        )
        read_zh = (
            f"广度核验：{w20['available']}个高流动性科技指标中近20日仅{w20['positive']}个上涨"
            "——弱势覆盖面广。"
        )
    else:
        direction = "mixed"
        read_en = (
            f"Breadth check: {w20['positive']}/{w20['available']} liquid tech gauges "
            f"are up over 20 sessions and {w5['positive']}/{w5['available']} over 5 — mixed."
        )
        read_zh = (
            f"广度核验：近20日上涨{w20['positive']}/{w20['available']}，"
            f"近5日上涨{w5['positive']}/{w5['available']}——表现分化。"
        )

    return {
        "as_of": as_of.strftime("%Y-%m-%d"),
        "n": n,
        "direction": direction,
        "windows": {"5d": w5, "20d": w20},
        "read_en": read_en,
        "read_zh": read_zh,
        "members": rows,
    }
