"""Factor portfolio return-series engine (engine.factor_series).

Covers the cap-weighting (5% single-name cap, weights sum to 1), the month-end grid,
and an end-to-end smoke with mocked compute_factors/_closes: the payload must carry
per-factor long-only + Q5-Q1 series, horizon z's, bootstrap-CI stats, a crowding
matrix, rotation and a quilt — and be STRICT-JSON serializable (native types).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from engine import factor_series as fsx


def test_cap_weight_enforces_cap_and_sums_to_one():
    # 30 names (cap feasible: 30*0.05=1.5>1), one mega-cap that would dominate uncapped
    mc = pd.Series({"BIG": 9000.0, **{f"N{i}": float(10 + i) for i in range(29)}})
    w = fsx._cap_weight(mc, cap=0.05)
    assert abs(w.sum() - 1.0) < 1e-9
    assert w.max() <= 0.05 + 1e-6          # the mega-cap is capped, not ~90%
    assert (w > 0).all()


def test_cap_weight_infeasible_falls_back_to_equal_weight():
    mc = pd.Series({"BIG": 900.0, "A": 40.0, "B": 30.0, "C": 20.0, "D": 10.0})  # 5 names, 5% cap infeasible
    w = fsx._cap_weight(mc, cap=0.05)
    assert abs(w.sum() - 1.0) < 1e-9
    assert np.allclose(w.values, 0.2)      # equal weight fallback


def test_month_ends_picks_last_trading_day():
    idx = pd.bdate_range("2024-01-01", "2024-03-29")
    me = fsx._month_ends(idx)
    assert me[0] == pd.Timestamp("2024-01-31")
    assert me[-1] == pd.Timestamp("2024-03-29")   # last business day available in March
    assert len(me) == 3


def _mock(monkeypatch, n_tickers=120, n_days=260):
    tickers = [f"T{i:03d}" for i in range(n_tickers)]
    idx = pd.bdate_range("2025-01-01", periods=n_days)
    rng = np.random.default_rng(0)
    closes = pd.DataFrame(100 * np.cumprod(1 + rng.normal(0, 0.01, (n_days, n_tickers)), axis=0),
                          index=idx, columns=tickers)
    monkeypatch.setattr(fsx, "_closes", lambda *a, **k: closes)

    def fake_compute(asof=None, universe="broad"):
        z = rng.normal(0, 1, n_tickers)
        rows = []
        for i, t in enumerate(tickers):
            row = {"ticker": t, "mktcap_bn": float(5 + i)}
            for f in fsx.SERIES_FACTORS:
                row[f] = float(z[i] + hash(f) % 3 * 0.01)
            rows.append(row)
        return {"table": rows}
    monkeypatch.setattr(fsx, "compute_factors", fake_compute)
    monkeypatch.setattr(fsx.store, "read", lambda g, n: None)   # no SPY -> benchmark None, fine


def test_compute_series_smoke_and_json(monkeypatch):
    _mock(monkeypatch)
    out = fsx.compute_factor_series()
    assert out is not None
    assert set(out["factors"]) <= set(fsx.SERIES_FACTORS) and out["factors"]
    f0 = out["factors"][0]
    s = out["series"][f0]
    assert "long_only" in s and "long_short" in s
    assert isinstance(s["long_only"]["spark"], list) and len(s["long_only"]["spark"]) > 1
    # horizon cells carry native types
    cell = out["horizons"][f0]["long_short"]["d20"]
    assert set(cell) == {"ret_pct", "z", "pct", "flag"}
    assert cell["flag"] in (True, False)
    # stats carry a bootstrap CI; crowding/rotation/quilt present
    assert "sharpe_ls_ci" in out["stats"][f0]
    assert out["crowding"] is None or "matrix" in out["crowding"]
    assert "leader" in out["rotation"]
    assert out["quilt"]["months"]
    # STRICT json (proves native types throughout) + reasonable size
    js = json.dumps(out)
    assert len(js) < 200_000


def test_degrades_without_caches(monkeypatch):
    monkeypatch.setattr(fsx, "_closes", lambda *a, **k: pd.DataFrame())
    assert fsx.compute_factor_series() is None


def test_universe_param_backcompat():
    """The new universe= keyword must default to 'broad' so existing callers
    (baskets / residual_alpha / discovery) are unchanged; 'narrow' ⊆ 'broad'."""
    import pytest
    from engine.equity_factors import _closes, _names_sectors
    b = _closes()
    if b is None or b.empty:
        pytest.skip("no price caches in this checkout")
    assert _closes("broad").shape == b.shape          # no-arg == broad (back-compat)
    assert _names_sectors() == _names_sectors("broad")
    n = _closes("narrow")
    if not n.empty:
        assert set(n.columns).issubset(set(b.columns))  # S&P 500 ⊆ S&P 1500
        assert n.shape[1] <= b.shape[1]
        assert set(_names_sectors("narrow")).issubset(set(_names_sectors("broad")))
