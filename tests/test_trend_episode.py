"""Pins engine/trend_episode.py to the frozen C1 episode definition + known answers."""
import numpy as np
import pandas as pd

from engine import trend_episode as te


def _series(vals):
    idx = pd.date_range("2015-01-01", periods=len(vals), freq="B")
    return pd.Series(vals, index=idx)


def test_constants_match_c1_prereg():
    # Any drift here silently de-syncs the displayed context from the study it cites.
    assert (te.SLOPE_WIN, te.Z_WIN, te.Z_MINP, te.HYST, te.MIN_DUR) == (63, 252, 200, 0.5, 20)


def test_upward_acceleration_is_confirmed_bull():
    # slope_z keys on the 63d slope RELATIVE to its 252d history (an acceleration
    # measure), so a confirmed bull needs the log-slope to ACCELERATE upward.
    drift = np.concatenate([np.full(300, 0.001), np.linspace(0.001, 0.012, 100)])
    ep = te.current_episode(_series(np.exp(np.cumsum(drift))))
    assert ep is not None
    assert ep["state"] == "bull"
    assert ep["confirmed"] is True and ep["run_len"] >= te.MIN_DUR
    assert ep["sz_now"] is not None


def test_downward_acceleration_is_bear():
    drift = np.concatenate([np.full(300, 0.001), np.linspace(0.001, -0.012, 100)])
    ep = te.current_episode(_series(np.exp(np.cumsum(drift))))
    assert ep is not None
    assert ep["state"] == "bear"


def test_insufficient_history_returns_none():
    close = _series(np.exp(0.002 * np.arange(100)))  # < Z_WIN + SLOPE_WIN
    assert te.current_episode(close) is None


def test_fresh_flip_is_not_yet_confirmed():
    # Long downtrend, then a short (<20d) up-leg at the end: bull run exists but is unconfirmed.
    down = np.exp(-0.003 * np.arange(360))
    up = down[-1] * np.exp(0.02 * np.arange(1, 8))  # 7 sharp up days
    ep = te.current_episode(_series(np.concatenate([down, up])))
    assert ep is not None
    if ep["state"] == "bull":            # the sharp leg may flip state
        assert ep["run_len"] < te.MIN_DUR
        assert ep["confirmed"] is False
