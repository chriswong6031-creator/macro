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


# ---- silent-freeze guard regressions --------------------------------------- #
# The guard that reports a frozen Tushare feed had itself been silently frozen: on
# pandas >= 3 `Timestamp.utcnow()` is tz-AWARE while frame_asof() returns tz-NAIVE, so
# staleness_badge() raised TypeError for every PRESENT table. build_china_library caught
# that in its own try/except ("tushare health registration failed"), so run_status never
# carried a `tushare` block and the STALE/DEAD warning could never fire.
#
# The pre-existing test above missed it because "nonexistent_table_xyz" returns at the
# `asof is None` early exit — the ONE branch that never reaches the subtraction — and it
# passed an explicit tz-naive `ref`, which is not what production uses. These tests use a
# REAL table and the production default (ref=None).

def _write_table(tmp_path, table: str, trade_date: str) -> None:
    """Write a minimal Tushare-shaped parquet into a temp data dir."""
    d = tmp_path / "tushare"
    d.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"ticker": ["600519.SS", "000001.SZ"],
                  "net_amount": [1.0, -1.0],
                  "trade_date": [trade_date, trade_date]}).to_parquet(d / f"{table}.parquet",
                                                                     index=False)


def test_staleness_badge_present_table_does_not_raise(monkeypatch, tmp_path):
    """REGRESSION: a PRESENT table with the production default ref (None) must not raise.

    This is the exact call build_china_library makes; it raised TypeError before the fix."""
    monkeypatch.setattr(tf.config, "data_dir", lambda: tmp_path)
    _write_table(tmp_path, "moneyflow", pd.Timestamp.now("UTC").strftime("%Y%m%d"))
    badge = tf.staleness_badge("moneyflow", expected_cadence_days=1)   # ref=None on purpose
    assert badge["asof"] is not None, "a present, dated table must report an asof"
    assert badge["lag_days"] is not None
    assert badge["state"] == "fresh"


def test_staleness_badge_flags_ten_day_stale_feed(monkeypatch, tmp_path):
    """REGRESSION: a feed 10 days stale must be flagged, not read as fresh.

    This is the assertion that would have caught a money-flow feed going 10 days stale."""
    monkeypatch.setattr(tf.config, "data_dir", lambda: tmp_path)
    ref = pd.Timestamp("2026-07-26")
    _write_table(tmp_path, "moneyflow", "20260716")          # 10 days behind ref
    badge = tf.staleness_badge("moneyflow", expected_cadence_days=1, ref=ref)
    assert badge["asof"] == "2026-07-16"
    assert badge["lag_days"] == 10
    assert badge["state"] in ("stale", "dead"), \
        f"a 10-day-stale daily feed must not read {badge['state']!r}"


def test_staleness_badge_tz_aware_ref_is_accepted(monkeypatch, tmp_path):
    """A tz-AWARE ref must be normalised, not raise — the shape production passes."""
    monkeypatch.setattr(tf.config, "data_dir", lambda: tmp_path)
    _write_table(tmp_path, "valuation", "20260716")
    badge = tf.staleness_badge("valuation", expected_cadence_days=1,
                               ref=pd.Timestamp("2026-07-26", tz="UTC"))
    assert badge["lag_days"] == 10 and badge["state"] in ("stale", "dead")


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
