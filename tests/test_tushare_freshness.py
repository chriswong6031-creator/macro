"""Asof-aware Tushare preference (engine/tushare_freshness.py) — masterplan §W6-CN fix 4.

Proves a FROZEN gated Tushare plane no longer beats a FRESH free fallback on file
presence alone: the preference is now data-through-date aware, and a stale Tushare
frame loses to a fresher free one.

Run: .venv/bin/python -m pytest tests/test_tushare_freshness.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import tushare_freshness as tf  # noqa: E402


def _framed(trade_date: str, n: int = 3, col: str = "trade_date") -> pd.DataFrame:
    return pd.DataFrame({"ticker": [f"T{i}" for i in range(n)],
                         "val": range(n), col: [trade_date] * n})


def test_frame_asof_prefers_trade_date_over_build_asof():
    # a frozen plane stamps a FRESH build asof but a STALE trade_date — trade_date must win
    df = pd.DataFrame({"trade_date": ["20260618", "20260618"],
                       "asof": ["2026-07-01", "2026-07-01"]})
    assert tf.frame_asof(df) == pd.Timestamp("2026-06-18")


def test_frame_asof_ignores_period_end_over_announcement():
    # forecast table: end_date is the fiscal-PERIOD end (runs ahead), ann_date is the honest
    # data-through date. A plane frozen at ann_date must NOT read fresh via its period end.
    df = pd.DataFrame({"end_date": ["20260630", "20260630"],
                       "ann_date": ["20260618", "20260618"],
                       "asof": ["20260622", "20260622"]})
    assert tf.frame_asof(df) == pd.Timestamp("2026-06-18"), "must not overstate freshness via end_date"


def test_frame_asof_prefers_observation_date_over_build_stamp():
    # free margin frame carries both a build stamp (asof) and the observation date (date);
    # the honest data-through is the observation date, not the later build stamp.
    df = pd.DataFrame({"date": ["20260628", "20260628"], "asof": ["20260701", "20260701"]})
    assert tf.frame_asof(df) == pd.Timestamp("2026-06-28")


def test_stale_tushare_loses_to_fresh_free():
    tv = _framed("20260618")                       # gated, frozen
    free = _framed("2026-06-30", col="trade_date")  # free, fresh
    chosen, src = tf.prefer_tushare(tv, free)
    assert src == "free", "stale gated must not beat fresh free"


def test_fresh_tushare_wins_within_lag():
    tv = _framed("20260630")
    free = _framed("2026-07-01")                    # 1 session ahead — within default lag
    chosen, src = tf.prefer_tushare(tv, free)
    assert src == "tushare"


def test_tushare_wins_when_no_free_available():
    tv = _framed("20260618")
    chosen, src = tf.prefer_tushare(tv, None)
    assert src == "tushare"


def test_undatable_tushare_deprefers_itself():
    tv = pd.DataFrame({"ticker": ["A"], "val": [1]})   # no date column
    free = _framed("2026-06-30")
    chosen, src = tf.prefer_tushare(tv, free)
    assert src == "free", "conservative: undatable gated frame yields to fresh free"


def test_staleness_badge_states():
    ref = pd.Timestamp("2026-07-01")
    # inject a frame via monkeypatch-free direct call on frame_asof semantics
    assert tf.staleness_badge("nonexistent_table_xyz", ref=ref)["state"] == "dead"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
