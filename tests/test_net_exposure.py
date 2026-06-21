"""Net-exposure timing overlay (engine.net_exposure) — leg logic + state mapping."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import net_exposure as nx  # noqa: E402


def _up(n=260):
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.Series(np.linspace(100, 200, n), index=idx)            # steadily above its 200dma


def _down(n=260):
    idx = pd.bdate_range("2023-01-02", periods=n)
    return pd.Series(np.linspace(200, 100, n), index=idx)            # below its 200dma


def test_trend_up_no_netliq_is_full_exposure():
    r = nx.assess(_up())
    assert r["exposure"] == 1.0 and r["state"] == "risk_on" and r["n_legs"] == 1


def test_trend_down_is_risk_off():
    r = nx.assess(_down())
    assert r["exposure"] == 0.0 and r["state"] == "risk_off"


def test_netliq_leg_joins_and_halves_on_disagreement():
    nl = pd.Series(np.linspace(6000, 5000, 200))                     # contracting (RoC < 0) → 0
    r = nx.assess(_up(), nl)
    assert r["n_legs"] == 2 and r["exposure"] == 0.5 and r["state"] == "neutral"
    assert r["legs"]["trend"] == 1.0 and r["legs"]["netliq"] == 0.0


def test_both_risk_on():
    nl = pd.Series(np.linspace(5000, 6000, 200))                     # expanding (RoC > 0) → 1
    r = nx.assess(_up(), nl)
    assert r["exposure"] == 1.0 and r["state"] == "risk_on" and r["n_legs"] == 2


def test_thin_series_returns_none():
    assert nx.assess(pd.Series(np.arange(50, dtype=float))) is None
