"""Per-basket crowding texture (engine.theme_crowding) — DISPLAY-ONLY, asymmetric.

Verify: the composite z is built from the available legs, the 'crowded' flag fires off the
high tail only, the read carries the display-only / down-size-only contract, and the module
degrades gracefully on thin/empty inputs (never raises, never emits a directional buy).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import theme_crowding as tc


def _resid(n=400, k=4, corr=0.0, seed=0):
    """Synthetic residual-return panel with a tunable common factor (→ co-movement)."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    rng = np.random.default_rng(seed)
    common = rng.normal(0, 0.01, n)
    cols = {}
    for i in range(k):
        cols[f"M{i}"] = corr * common + (1 - corr) * rng.normal(0, 0.01, n)
    return pd.DataFrame(cols, index=idx)


def test_composite_and_legs_present():
    resid = _resid(corr=0.6)
    rs = pd.Series(np.cumprod(1 + np.full(400, 0.0006)), index=resid.index)   # RS rising = stretched
    ext_rows = [{"ext_z": 2.4, "grade": "parabolic"}, {"ext_z": 1.5, "grade": "stretched"},
                {"ext_z": 1.2, "grade": "stretched"}, {"ext_z": 0.9, "grade": "steady"}]
    out = tc.basket_crowding(resid, rs, ext_rows)
    assert out["crowding_z"] is not None
    assert out["n_legs"] >= 2
    assert {"comovement", "rs_stretch", "extension"} <= set(out["legs"])
    assert out["extension"]["pct_parabolic"] == 25       # 1 of 4 parabolic
    # display-only / asymmetric contract is always carried
    assert out["directional"] is False and out["use"] == "size_down_only"


def test_crowded_flag_is_high_tail_only():
    calm_resid = _resid(corr=0.05, seed=1)
    rs = pd.Series(np.cumprod(1 + np.full(400, -0.0004)), index=calm_resid.index)  # RS falling
    calm = [{"ext_z": -0.3, "grade": "steady"}, {"ext_z": 0.1, "grade": "steady"},
            {"ext_z": -0.5, "grade": "steady"}, {"ext_z": 0.2, "grade": "steady"}]
    out = tc.basket_crowding(calm_resid, rs, calm)
    assert out["crowded"] is False                        # calm + un-stretched → not crowded

    # genuinely crowded: legs ALIGN — high residual co-movement, RS stretched, all parabolic
    hot_resid = _resid(corr=0.05, seed=3).copy()
    common = np.random.default_rng(9).normal(0, 0.012, 400)
    for c in hot_resid.columns:                           # spike co-movement in the recent window
        hot_resid[c] = hot_resid[c].values
        hot_resid.iloc[-120:, hot_resid.columns.get_loc(c)] = 0.9 * common[-120:] + 0.1 * hot_resid[c].iloc[-120:].values
    hot = [{"ext_z": 3.0, "grade": "parabolic"}, {"ext_z": 2.6, "grade": "parabolic"},
           {"ext_z": 2.2, "grade": "parabolic"}, {"ext_z": 1.8, "grade": "stretched"}]
    rs_hot = pd.Series(np.cumprod(1 + np.r_[np.full(380, 0.0002), np.full(20, 0.004)]),
                       index=hot_resid.index)
    out_hot = tc.basket_crowding(hot_resid, rs_hot, hot)
    assert out_hot["crowding_z"] >= tc.CROWDED_Z and out_hot["crowded"] is True


def test_graceful_on_empty():
    out = tc.basket_crowding(pd.DataFrame(), pd.Series(dtype=float), None)
    assert out["crowding_z"] is None and out["crowded"] is False
    assert out["directional"] is False                   # still never directional


def test_short_interest_is_context_not_in_composite():
    resid = _resid(corr=0.3, seed=2)
    rs = pd.Series(np.cumprod(1 + np.full(400, 0.0003)), index=resid.index)
    ext = [{"ext_z": 0.5, "grade": "steady"}] * 4
    a = tc.basket_crowding(resid, rs, ext, dtc=None)
    b = tc.basket_crowding(resid, rs, ext, dtc=[5.0, 6.0, 7.0])
    # adding days-to-cover changes only the context block, never the composite z
    assert a["crowding_z"] == b["crowding_z"]
    assert b["extension"].get("avg_days_to_cover") == 6.0
