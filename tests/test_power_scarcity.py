"""engine.power_scarcity — the physical bottleneck read for the power cluster from FRED
electricity series. Verifies graceful None without FRED, and a TIGHT band on rising demand/
price. FRED access (_first) is monkeypatched so no network/store is needed.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import power_scarcity as ps


def _accel(n=60):
    # flat then a recent surge -> YoY rising AND the latest level well above its history (so both
    # _z(_yoy(.)) and _z(level) are positive — a genuine recent tightening, not a linear drift)
    idx = pd.date_range("2020-01-01", periods=n, freq="MS")
    vals = np.concatenate([np.full(n - 12, 100.0), np.linspace(102.0, 140.0, 12)])
    return pd.Series(vals, index=idx)


def test_none_without_fred(monkeypatch):
    monkeypatch.setattr(ps, "_first", lambda ids: None)
    monkeypatch.setattr(ps, "_queue_pull", lambda: None)
    assert ps.compute_power_scarcity(write_ledger=False) is None


def test_tight_on_rising_demand_and_price(monkeypatch):
    monkeypatch.setattr(ps, "_first", lambda ids: _accel())      # every leg gets a surging series
    monkeypatch.setattr(ps, "_queue_pull", lambda: None)
    out = ps.compute_power_scarcity(write_ledger=False)
    assert out is not None
    assert out["band"] in ("TIGHTENING", "TIGHT", "SOLD_OUT") and out["tightness"] > 0
    assert out["regime"] is True                                 # all present legs positive
    # the read is applied to every power-cluster theme
    assert "data_center_power" in out["themes"] and "nuclear_power" in out["themes"]
    assert out["themes"]["data_center_power"]["band"] == out["band"]


def test_queue_pull_from_cache(monkeypatch, tmp_path):
    (tmp_path / "eia").mkdir(parents=True, exist_ok=True)
    (tmp_path / "eia" / "interconnection_queue.json").write_text('{"total_gw_yoy": 40.0}')
    monkeypatch.setattr(ps.config, "data_dir", lambda: tmp_path)
    assert ps._queue_pull() == 2.0                               # +40%/yr -> clamped to +2 z
