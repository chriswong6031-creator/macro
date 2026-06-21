"""Tests for engine.expansion_gate — the leadership/trend tailwind read."""
from __future__ import annotations
import numpy as np
import pandas as pd

from engine import expansion_gate


def _series(slope, n=300, start=100.0):
    idx = pd.bdate_range("2023-01-01", periods=n)
    return pd.Series(start * (1 + slope) ** np.arange(n), index=idx)


def test_leader_above_rising_trend_scores_high():
    # stock strongly outpaces a flat benchmark and is above a rising 200d
    bench = _series(0.0)
    stock = _series(0.004)
    r = expansion_gate.assess(stock, bench)
    assert r["ok"] is True and r["leader"] is True
    assert r["rs_rank"] > 0.7 and r["above_200d"] is True


def test_laggard_below_falling_trend_scores_low():
    # stock falls while the benchmark rises => weak RS, below a falling trend
    bench = _series(0.003)
    stock = _series(-0.004)
    r = expansion_gate.assess(stock, bench)
    assert r["ok"] is False and r["leader"] is False
    assert r["rs_rank"] < 0.4


def test_theme_accel_nudges_score():
    bench = _series(0.0)
    stock = _series(0.001)
    base = expansion_gate.assess(stock, bench)
    hot = expansion_gate.assess(stock, bench, theme_accel=1.0)
    cold = expansion_gate.assess(stock, bench, theme_accel=-1.0)
    assert hot["score"] >= base["score"] >= cold["score"]


def test_no_bench_or_thin_is_neutral_not_ok():
    r = expansion_gate.assess(_series(0.004), None)
    assert r["ok"] is False and r["score"] == 0.5
    assert expansion_gate.assess(_series(0.004, n=50), _series(0.0, n=50))["score"] == 0.5
