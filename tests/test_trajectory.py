"""Pure-function tests for engine/trajectory.py — the shared price-trajectory spine.

Synthetic close series only (passed via the ``closes=`` param), so no disk I/O and no
yahoo parquet is read for the value assertions. Three canonical shapes:
  - a crashed-and-still-falling series  → rolling_over True, basing False
  - a crashed-but-basing (reclaimed 50d) series → basing True, rolling_over False
  - a steady uptrend near its highs      → neither
Plus degrade cases: too-short series → None; missing parquet → None.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from engine import trajectory as T  # noqa: E402


def _series(vals: list[float]) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(vals), freq="B")
    return pd.Series(vals, index=idx, dtype="float64")


def _crashed_falling() -> pd.Series:
    # ramp to 100 over ~200 bars, then a sustained decline to ~45 over the last ~60 bars,
    # with the last 20 bars still dropping and the price well below its 50d average.
    up = [50 + 50 * (i / 199) for i in range(200)]        # 50 -> 100
    down = [100 - 55 * (j / 79) for j in range(80)]       # 100 -> 45, monotone down
    return _series(up + down)


def _crashed_basing() -> pd.Series:
    # deep drawdown, then a stabilizing base that RECLAIMS the 50d MA and ticks up the last month.
    up = [50 + 50 * (i / 199) for i in range(200)]        # 50 -> 100
    down = [100 - 40 * (j / 59) for j in range(60)]       # 100 -> 60 decline
    base = [60 + 6 * (k / 39) for k in range(40)]         # 60 -> 66 recovery (reclaims falling 50d)
    return _series(up + down + base)


def _steady_uptrend() -> pd.Series:
    return _series([50 + 40 * (i / 279) for i in range(280)])   # smooth 50 -> 90, near highs


# ── rolling_over: crashed-and-falling ─────────────────────────────────────── #
def test_crashed_falling_is_rolling_over():
    s = T.snapshot("X", closes=_crashed_falling())
    assert s is not None
    assert s["off_high_252"] <= -0.15          # materially off its high
    assert s["ret_20d"] < 0                     # last month down
    assert s["above_50d"] is False              # below the 50d MA
    assert s["rolling_over"] is True
    assert s["basing"] is False


# ── basing: crashed-but-stabilizing ───────────────────────────────────────── #
def test_crashed_basing_is_not_rolling_over():
    s = T.snapshot("X", closes=_crashed_basing())
    assert s is not None
    assert s["off_high_252"] <= -0.15          # still deep off the high
    assert s["rolling_over"] is False           # reclaimed 50d + up month ⇒ NOT rolling over
    assert s["basing"] is True


# ── steady uptrend near highs ─────────────────────────────────────────────── #
def test_steady_uptrend_neither():
    s = T.snapshot("X", closes=_steady_uptrend())
    assert s is not None
    assert s["off_high_252"] > -0.15            # near its highs
    assert s["above_50d"] is True
    assert s["above_200d"] is True
    assert s["rolling_over"] is False
    assert s["basing"] is False


def test_rolling_over_and_basing_mutually_exclusive():
    for maker in (_crashed_falling, _crashed_basing, _steady_uptrend):
        s = T.snapshot("X", closes=maker())
        assert not (s["rolling_over"] and s["basing"])


# ── degrade cases ─────────────────────────────────────────────────────────── #
def test_too_short_series_returns_none():
    assert T.snapshot("X", closes=_series([10.0] * 10)) is None


def test_missing_parquet_returns_none(tmp_path):
    # no data/yahoo/NOPE.parquet under tmp_path ⇒ honest None, never a guess
    assert T.snapshot("NOPE", root=tmp_path) is None


def test_empty_ticker_returns_none():
    assert T.snapshot("", closes=_steady_uptrend()) is None


def test_fields_present_and_typed():
    s = T.snapshot("X", closes=_steady_uptrend())
    for k in ("off_high_252", "rs_vs_spy_60d", "ret_20d", "ret_60d",
              "above_50d", "above_200d", "rolling_over", "basing", "asof"):
        assert k in s
    assert isinstance(s["rolling_over"], bool)
    assert isinstance(s["basing"], bool)
    assert s["off_high_252"] <= 0              # drawdown is a non-positive fraction
