"""Tests for engine.risk_sizing (vol-managed sizing) + engine.dispersion (regime gate)."""
from __future__ import annotations
import numpy as np
import pandas as pd

from engine import risk_sizing, dispersion


def _series(daily_vol, n=400, start=100.0, seed=0):
    rng = np.random.default_rng(seed)
    r = rng.normal(0.0003, daily_vol, n)
    return pd.Series(start * np.cumprod(1 + r), index=pd.bdate_range("2023-01-01", periods=n))


def test_high_vol_name_gets_smaller_size():
    calm = risk_sizing.assess(_series(0.008, seed=1))      # ~13% ann
    wild = risk_sizing.assess(_series(0.040, seed=2))      # ~64% ann
    assert calm and wild
    assert calm["size_mult"] > wild["size_mult"]           # bet less on the high-vol name
    assert calm["inv_vol_mult"] >= 1.0 and wild["inv_vol_mult"] <= 1.0


def test_regime_gross_scales_size():
    s = _series(0.015, seed=3)
    base = risk_sizing.assess(s, regime_gross=1.0)
    hi = risk_sizing.assess(s, regime_gross=1.2)
    lo = risk_sizing.assess(s, regime_gross=0.75)
    assert hi["size_mult"] > base["size_mult"] > lo["size_mult"]


def test_inverse_vol_weights_favor_low_vol():
    w = risk_sizing.inverse_vol_weights({"A": 0.10, "B": 0.40})
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert w["A"] > w["B"]                                  # low-vol A gets more weight


def test_vol_target_scalar_caps_and_degrosses():
    assert risk_sizing.vol_target_scalar(0.10, target_vol_ann=0.22) == 1.5   # calm -> capped at 1.5
    assert risk_sizing.vol_target_scalar(0.44, target_vol_ann=0.22) == 0.5   # stress -> de-gross
    assert risk_sizing.vol_target_scalar(0.0) == 1.0                          # guard


def test_book_vol_between_idio_and_fully_correlated():
    vols = {"A": 0.20, "B": 0.20, "C": 0.20}
    w = {"A": 1 / 3, "B": 1 / 3, "C": 1 / 3}
    v = risk_sizing.book_forecast_vol_ann(w, vols, avg_corr=0.35)
    assert 0.20 / np.sqrt(3) < v < 0.20                     # between diversified and undiversified


def test_dispersion_lean_in_when_names_fan_out():
    n, idx = 300, pd.bdate_range("2023-01-01", periods=300)
    rng = np.random.default_rng(5)
    # LOW dispersion early (everything moves together), HIGH dispersion recently (names fan out)
    low = pd.DataFrame(rng.normal(0, 0.005, (200, 40)), index=idx[:200]) \
        .add(rng.normal(0, 0.02, (200, 1)))                # shared market shock => high corr
    high = pd.DataFrame(rng.normal(0, 0.05, (100, 40)), index=idx[200:])  # idiosyncratic => dispersed
    panel = pd.concat([low, high])
    r = dispersion.assess(panel)
    assert r is not None and r["state"] == "lean_in" and r["gross_mult"] > 1.0


def test_dispersion_thin_panel_is_none():
    assert dispersion.assess(pd.DataFrame(np.zeros((10, 5)))) is None
