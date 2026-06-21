"""Shared ticker-universe helper for per-ticker alt-data collectors.

Several beyond-Quiver feeds (Finnhub, Polygon news) are PARAMETRIZED by ticker — one HTTP
call per symbol — so they query a capped watchlist of narrative-basket members rather than the
whole market. This centralizes "the alt-data watchlist" so every collector agrees on it.
"""
from __future__ import annotations

import json
import logging

from lib import config

log = logging.getLogger(__name__)


def basket_members(cap: int | None = None) -> list[str]:
    """Unique active narrative-basket members, deterministic order, optionally capped.
    Order = first appearance across baskets (membership.json order), so the cap is stable."""
    try:
        baskets = json.loads((config.data_dir() / "baskets" / "membership.json").read_text()).get("baskets", {})
    except Exception:  # noqa: BLE001
        return []
    seen, out = set(), []
    for b in baskets.values():
        for m in b.get("members", []):
            t = m.get("ticker")
            if t and not m.get("removed") and t not in seen:
                seen.add(t)
                out.append(t)
    return out[:cap] if cap else out
