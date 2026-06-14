"""Pure-function tests for the funding/repo-stress leaf — no network."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import funding_stress as fs  # noqa: E402

_IDX = pd.date_range("2022-01-03", periods=600, freq="B")


def _flat(v):
    return pd.Series(np.full(len(_IDX), float(v)), index=_IDX)


def test_compute_calm_when_spread_low_in_range():
    # spread declines from +10bp to -2bp and dispersion from 20bp to 5bp -> the
    # current reading sits at the BOTTOM of its 2y range -> calm.
    sofr = pd.Series(np.linspace(3.10, 2.98, len(_IDX)), index=_IDX)
    p99 = sofr + np.linspace(0.20, 0.05, len(_IDX))
    out = fs.compute({"sofr": sofr, "effr": _flat(3.00), "sofr_p99": p99},
                     {"pctile_lookback_d": 252})
    assert out["spread_bp"] == -2.0 and out["dispersion_bp"] == 5.0
    assert out["rows"][0]["pctile"] <= 5            # bottom of the window
    assert out["state"] == "calm"


def test_compute_stressed_when_sofr_spikes_above_effr():
    sofr = _flat(3.00).copy()
    sofr.iloc[-1] = 3.30                       # SOFR spikes +30bp over EFFR at the end
    p99 = sofr + 0.02
    p99.iloc[-1] = 3.60                        # right tail blows out too
    out = fs.compute({"sofr": sofr, "effr": _flat(3.00), "sofr_p99": p99},
                     {"pctile_lookback_d": 252})
    assert out["spread_bp"] == 30.0
    assert out["rows"][0]["pctile"] >= 99       # top of the window
    assert out["state"] == "stressed" and out["score"] >= 90


def test_compute_none_without_core_rates():
    assert fs.compute({"sofr": _flat(3.0)}, {}) is None       # no EFFR
    assert fs.compute({}, {}) is None


def test_dispersion_optional():
    out = fs.compute({"sofr": _flat(3.0), "effr": _flat(3.0)}, {"pctile_lookback_d": 252})
    assert out is not None and out["dispersion_bp"] is None    # no SOFR_p99 -> still works


def test_snapshot_degrades(monkeypatch):
    monkeypatch.setattr(fs, "_read", lambda mn: None)
    assert fs.snapshot() is None
