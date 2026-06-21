"""Modeled news-flow tests (hermetic — synthetic events frame)."""
from __future__ import annotations

import pandas as pd

from engine import news_flow

TODAY = pd.Timestamp("2026-06-19", tz="UTC")


def _events(rows):
    """rows: list of (days_ago, theme, source_tier)."""
    recs = [{"first_seen_utc": (TODAY - pd.Timedelta(days=d)).isoformat(),
             "theme": t, "source_tier": tier, "scheduled_ref": "", "title": "x"}
            for d, t, tier in rows]
    df = pd.DataFrame(recs)
    df["ts"] = pd.to_datetime(df["first_seen_utc"], utc=True)
    return df


def test_velocity_and_acceleration():
    ev = _events([(1, "geopolitics", 1), (2, "geopolitics", 2), (3, "industrial_policy", 1), (10, "geopolitics", 1)])
    out = news_flow.theme_flow("defense", ev, today=TODAY)  # defense -> geopolitics+industrial_policy
    assert out is not None
    assert out["n_articles_7d"] == 3                       # 3 within the last 7d
    assert out["velocity"] == 2.6                          # tier1(1.0)+tier2(0.6)+tier1(1.0)
    assert out["acceleration"] > 0                         # recent 2.6 vs prior 1.0
    assert out["tier1_share"] is not None and out["metric"] == out["acceleration"]


def test_unmapped_basket_returns_none():
    ev = _events([(1, "geopolitics", 1)])
    assert news_flow.theme_flow("retail", ev, today=TODAY) is None      # no macro channel
    assert news_flow.theme_flow("payments_fintech", ev, today=TODAY) is None


def test_empty_or_irrelevant_returns_none():
    assert news_flow.theme_flow("defense", None) is None
    ev = _events([(1, "monetary", 1)])                     # defense doesn't ride 'monetary'
    assert news_flow.theme_flow("defense", ev, today=TODAY) is None
