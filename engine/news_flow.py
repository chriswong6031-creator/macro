"""Modeled per-theme NEWS FLOW — velocity / acceleration of the macro-narrative slice.

The repo's built-in "modeled news flow" is the point-in-time GDELT narrative log
(the news bus accrues data/news_vector/events.parquet): reputable-source headlines
classified into MACRO narrative buckets (geopolitics / trade / industrial_policy /
monetary / …). This module maps each thematic basket onto the macro buckets it's
exposed to and reads the news VELOCITY (tier-weighted article count, last 7d) and
ACCELERATION (vs the prior 7d) for that basket — one leg of the multi-source
real-activity observable (engine/real_activity.py).

LEAF DISCIPLINE: news_flow is a scoring-path leg, so it must NOT import the display-only
bus module — it reads the bus's OUTPUT parquet directly via lib.config (see _events_path).

HONEST + COARSE BY DESIGN: the news store is macro-narrative-scoped, not per-ticker, so
only baskets with a clear macro channel (defense→geopolitics, semis→industrial_policy,
…) get a news leg; the rest return None and the fuser simply down-weights them. The leg
carries a LOW fusion weight. Display/context only — never a score input on its own.
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# basket_id -> the macro narrative buckets (the bus's macro-narrative themes) it rides.
# Coarse + curated; absent baskets get no news leg (honest — the store can't resolve them).
BASKET_TO_GDELT_THEME: dict[str, list[str]] = {
    "defense":           ["geopolitics", "industrial_policy"],
    "space_economy":     ["geopolitics", "industrial_policy"],
    "nuclear_power":     ["geopolitics", "industrial_policy"],
    "uranium_miners":    ["geopolitics", "industrial_policy"],
    "energy_complex":    ["geopolitics", "industrial_policy"],
    "power_grid":        ["industrial_policy", "geopolitics"],
    "ai_infra":          ["industrial_policy"],
    "ai_semiconductors": ["industrial_policy"],
    "ai_software":       ["industrial_policy"],
    "ai_neoclouds":      ["industrial_policy"],
    "ai_agents":         ["industrial_policy"],
    "semicap_equipment": ["industrial_policy", "trade"],
    "reshoring":         ["industrial_policy", "trade"],
    "critical_minerals": ["industrial_policy", "trade"],
}

WINDOW_D = 7          # recent vs prior comparison window
_TIER_W = {1: 1.0}    # tier-1 wires full weight; everything else 0.6
_OTHER_TIER_W = 0.6


def _events_path(root=None) -> Path:
    """Path to the bus's accrued PIT event parquet, resolved WITHOUT importing the bus
    module (LEAF discipline). Mirrors news_vector's own location: <data_dir>/news_vector/.
    A read path, so it does not create the directory."""
    base = (root / "data") if root is not None else config.data_dir()
    return base / "news_vector" / "events.parquet"


def load_events(root=None) -> pd.DataFrame | None:
    """The PIT narrative-news log with a parsed UTC timestamp. None if absent/empty."""
    try:
        p = _events_path(root)
        if not p.exists():
            return None
        df = pd.read_parquet(p)
        if df is None or df.empty:
            return None
        df = df.copy()
        df["ts"] = pd.to_datetime(df["first_seen_utc"], utc=True, errors="coerce")
        return df.dropna(subset=["ts"])
    except Exception as e:  # noqa: BLE001 — context-only, never break the build
        log.debug("news_flow load_events failed: %s", e)
        return None


def _tier_weighted(rows: pd.DataFrame) -> float:
    if rows.empty:
        return 0.0
    tiers = pd.to_numeric(rows.get("source_tier"), errors="coerce").fillna(2)
    return float(((tiers == 1) * _TIER_W[1] + (tiers != 1) * _OTHER_TIER_W).sum())


def theme_flow(basket_id: str, events: pd.DataFrame | None, today=None, win: int = WINDOW_D) -> dict | None:
    """Per-basket news velocity/acceleration over the mapped macro buckets. None when the
    basket has no macro channel or the store can't cover it."""
    themes = BASKET_TO_GDELT_THEME.get(basket_id)
    if not themes or events is None or events.empty:
        return None
    sub = events[events["theme"].isin(themes)]
    if sub.empty:
        return None
    today = pd.Timestamp(today) if today is not None else sub["ts"].max()
    if today.tzinfo is None:
        today = today.tz_localize("UTC")
    w = pd.Timedelta(days=win)
    recent = sub[(sub["ts"] > today - w) & (sub["ts"] <= today)]
    prior = sub[(sub["ts"] > today - 2 * w) & (sub["ts"] <= today - w)]
    v_rec, v_prev = _tier_weighted(recent), _tier_weighted(prior)
    if v_rec <= 0 and v_prev <= 0:
        return None
    acceleration = (v_rec - v_prev) / max(v_prev, 1.0)
    n = int(len(recent))
    sched = recent.get("scheduled_ref")
    unscheduled_share = float((sched.fillna("") == "").mean()) if n and sched is not None else None
    tier1_share = float((pd.to_numeric(recent["source_tier"], errors="coerce") == 1).mean()) if n else None
    return {
        "n_articles_7d": n,
        "velocity": round(v_rec, 2),
        "acceleration": round(acceleration, 3),
        "metric": float(acceleration),            # cross-sectional fusion input
        "unscheduled_share": None if unscheduled_share is None else round(unscheduled_share, 2),
        "tier1_share": None if tier1_share is None else round(tier1_share, 2),
        "buckets": themes,
        "is_context_only": True,
    }
