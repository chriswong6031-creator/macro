"""Per-index directional model — OOS primitives, the membership gate, honest
calibration, and point-in-time guarantees. Reads the repo data store; skips cleanly
if absent.

Run: python3 -m tests.test_index_direction
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import anticipation, index_direction as idr, validation as V  # noqa: E402

Y = Path("data/yahoo")


def _c(t):
    f = Y / f"{t}.parquet"
    return pd.read_parquet(f)["close"].dropna() if f.exists() else None


def test_oos_r2_and_clark_west():
    rng = np.random.default_rng(1)
    n = 400
    x = rng.standard_normal(n)
    r = 0.3 * np.r_[np.nan, x[:-1]] + rng.standard_normal(n)          # x[t-1] predicts r[t]
    f = 0.3 * np.r_[np.nan, x[:-1]]
    sig = V.oos_r2(r, f)
    assert sig.get("oos_r2", -1) > 0.05, sig
    cw = V.clark_west(r, f)
    assert cw.get("cw_p", 1) < 0.05, cw
    # pure noise forecast must NOT beat the mean meaningfully
    noise = V.oos_r2(rng.standard_normal(n), rng.standard_normal(n) * 0.01)
    assert noise.get("oos_r2", 1) < 0.03, noise
    print("ok test_oos_r2_and_clark_west")


def test_n_trials_frozen():
    from scripts import index_direction_phase0 as p0
    assert p0.N_TRIALS == 400, "n_trials must stay frozen (DSR multiple-testing honesty)"
    print("ok test_n_trials_frozen")


def test_membership_gate_fires_for_index_not_stock():
    spy = _c("SPY")
    if spy is None:
        print("skip test_membership (no data)"); return
    qqq = _c("QQQ")
    a_idx = anticipation.anticipate(qqq, bench=spy, asset="QQQ", asset_class="index")
    assert "direction_model" in a_idx, "index membership must trigger the directional model"
    nv = pd.read_parquet("data/stocks/NVDA.parquet")["close"] if Path("data/stocks/NVDA.parquet").exists() else None
    if nv is not None:
        a_stk = anticipation.anticipate(nv, bench=spy, asset="NVDA", asset_class="us_equity")
        assert "direction_model" not in a_stk, "single names must NOT get the index directional model"
    print("ok test_membership_gate_fires_for_index_not_stock")


def test_forecast_scored_vs_unscored():
    qqq = _c("QQQ")
    if qqq is None:
        print("skip test_forecast_scored (no data)"); return
    go = idr.forecast(qqq, asset="QQQ", gate={"medium": {
        "scored": True, "legs": {"real_rate": "GO"}, "platt": {"a": 0.46, "b": 0.0},
        "p_up_band": [0.40, 0.62]}})
    m = go["horizons"]["medium"]
    assert m["scored"] and m["r_hat"] is not None
    assert 0.40 <= m["p_up"] <= 0.62, m["p_up"]
    # no gate ⇒ honest coin-flip
    off = idr.forecast(qqq, asset="QQQ", gate={})
    assert off["horizons"]["medium"]["p_up"] == 0.5 and not off["horizons"]["medium"]["scored"]
    print(f"ok test_forecast_scored_vs_unscored (scored p_up={m['p_up']}, off=0.5)")


def test_p_up_band_clamps():
    # an absurd forecast must still clamp to the honest band — never overconfident
    assert idr.forecast_to_p_up(99.0, 5.0, band=(0.40, 0.62)) == 0.62
    assert idr.forecast_to_p_up(-99.0, 5.0, band=(0.40, 0.62)) == 0.40
    assert idr.forecast_to_p_up(0.0, 5.0) == 0.5
    print("ok test_p_up_band_clamps")


def test_no_preset_returns_empty():
    s = pd.Series(np.linspace(100, 120, 1000), index=pd.date_range("2010-01-01", periods=1000, freq="B"))
    assert idr.forecast(s, asset="NVDA", gate={}) == {}      # not an index
    print("ok test_no_preset_returns_empty")


def test_legs_point_in_time():
    qqq = _c("QQQ")
    if qqq is None:
        print("skip test_legs_pit (no data)"); return
    T = qqq.index[-400]
    cmp_end = qqq.index[-520]
    full = idr.build_legs(qqq)
    trunc = idr.build_legs(qqq.loc[:T])
    bad = []
    for col in ("vrp", "tsmom", "real_rate", "credit", "term"):
        if col not in full or col not in trunc:
            continue
        a = full[col].loc[:cmp_end].dropna()
        b = trunc[col].loc[:cmp_end].dropna()
        idx = a.index.intersection(b.index)[-150:]
        if not len(idx):
            continue
        diff = (a.loc[idx] - b.loc[idx]).abs().max()
        if diff > 0.02:
            bad.append((col, round(float(diff), 4)))
    assert not bad, f"look-ahead in index legs: {bad}"
    print("ok test_legs_point_in_time")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
    print(f"\n{len(fns)} index-direction tests passed.")
