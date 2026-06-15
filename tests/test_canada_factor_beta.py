"""Per-stock commodity/FX factor-beta engine test (engine/canada_factor_beta.py).

A synthetic stock built to load 0.6 on oil and 0.3 on the market (nothing else) must
have its oil beta recovered (market-controlled), gold/CAD ~0, and be tagged oil-driven.
CONTEXT, not a signal — the test asserts the regression mechanics only."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import canada_factor_beta as cfb  # noqa: E402


def _series_from_ret(ret: np.ndarray, idx) -> pd.Series:
    return pd.Series(100.0 * np.cumprod(1.0 + ret), index=idx)


def test_compute_betas_recovers_oil_loading():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2024-01-01", periods=320)
    mkt = rng.normal(0, 0.01, len(idx))
    oil = rng.normal(0, 0.02, len(idx))
    gold = rng.normal(0, 0.015, len(idx))
    usdcad = rng.normal(0, 0.008, len(idx))
    fs = {"spy": _series_from_ret(mkt, idx), "oil": _series_from_ret(oil, idx),
          "gold": _series_from_ret(gold, idx), "usdcad": _series_from_ret(usdcad, idx)}
    stock_ret = 0.3 * mkt + 0.6 * oil                 # loads on oil + market only
    closes = pd.DataFrame({"XYZ.TO": 100.0 * np.cumprod(1.0 + stock_ret)}, index=idx)
    out = cfb.compute_betas(closes, fs, min_obs=100)
    b = out["XYZ.TO"]
    assert abs(b["oil"] - 0.6) < 0.05                 # oil loading recovered
    assert abs(b["gold"]) < 0.05 and abs(b["cad"]) < 0.05
    assert b["primary"] == "oil" and b["primary_label"] == "Oil"
    assert b["r2"] is not None and b["r2"] > 0.95
    assert b["n"] == len(idx) - 1


def test_compute_betas_empty_when_thin():
    idx = pd.bdate_range("2024-01-01", periods=20)
    fs = {"spy": pd.Series(range(20), index=idx, dtype=float),
          "oil": pd.Series(range(20), index=idx, dtype=float)}
    closes = pd.DataFrame({"A.TO": pd.Series(range(20), index=idx, dtype=float)})
    assert cfb.compute_betas(closes, fs, min_obs=180) == {}
