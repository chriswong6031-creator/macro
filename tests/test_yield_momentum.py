"""Contract tests for the display-only, correction-safe yield momentum read."""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import yield_momentum


def _build(frame: pd.DataFrame) -> dict:
    return yield_momentum.build_yield_momentum(frame)


def _frame(n: int = 100) -> pd.DataFrame:
    index = pd.bdate_range("2026-01-01", periods=n)
    out = pd.DataFrame(index=index)
    for offset, column in enumerate(("us2y", "us5y", "us10y", "us20y", "us30y")):
        out[column] = 3.0 + offset / 10 + np.linspace(0.0, 0.5, n)
    return out


def test_multi_horizon_read_is_display_only_and_includes_ccw_us20y():
    read = _build(_frame())

    assert read["schema"] == "yield_momentum.v1"
    assert read["display_only"] is True
    assert read["authority"] is False
    assert all(read[key] is False for key in ("can_score", "can_size", "can_trade"))
    assert set(read["series"]) == {"2y", "5y", "10y", "20y", "30y"}
    twenty = read["series"]["20y"]
    assert twenty["source_column"] == "us20y"
    assert twenty["status"] == "available"
    assert twenty["level"] is not None
    assert set(twenty["velocity_bp"]) == {"5d", "22d", "63d"}
    assert twenty["velocity_bp"]["63d"] > 0


def test_missing_and_short_series_are_explicit_null_states():
    read = _build(_frame(20).drop(columns=["us20y"]))

    missing = read["series"]["20y"]
    assert missing["status"] == "missing"
    assert missing["level"] is None
    assert missing["null_reason"] == "source column us20y unavailable"

    short = read["series"]["10y"]
    assert short["status"] == "insufficient_history"
    assert short["velocity_bp"]["63d"] is None
    assert short["null_reason"] == "requires 64 observed points for 63d velocity"


def test_turn_watch_is_trailing_and_correction_rebuild_is_idempotent():
    values = np.concatenate([
        np.linspace(2.0, 3.8, 1000),
        np.linspace(3.8, 4.0, 100),
        np.linspace(4.0, 3.84, 22),
    ])
    frame = _frame(len(values))
    frame["us20y"] = values

    first = _build(frame)
    second = _build(frame.copy())
    corrected = frame.copy()
    corrected.loc[corrected.index[-23], "us20y"] -= 0.10
    corrected_once = _build(corrected)
    corrected_twice = _build(corrected.copy())

    assert first == second
    assert corrected_once == corrected_twice
    twenty = first["series"]["20y"]
    assert twenty["turn_watch"] == "rolldown_forming"
    assert twenty["velocity_bp"]["22d"] <= -12
    assert twenty["available_at"] is None
    assert twenty["availability_status"] == "not_provided_by_feature_frame"
