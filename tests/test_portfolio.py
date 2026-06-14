"""Cross-asset risk budgeting + stress replay (Phase D). ERC must EQUALIZE risk
contributions (and not collapse onto a corner when one leg is high-vol — the bug
the damping fixes); inverse-vol must down-weight vol; stress replay must surface
crisis drawdowns. Pure-math on synthetic data; snapshot() smoke-tested vs the store.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.portfolio import (_risk_contrib, erc_weights, risk_budget, snapshot,
                               stress_replay)


def _cov(vols, corr):
    v = np.array(vols)
    return np.outer(v, v) * corr


def test_erc_equalizes_risk_contributions():
    n = 4
    corr = np.full((n, n), 0.3)
    np.fill_diagonal(corr, 1.0)
    cov = _cov([0.1, 0.2, 0.3, 0.4], corr)        # widely different vols
    w = erc_weights(cov)
    rc = _risk_contrib(w, cov)
    assert abs(rc.max() - rc.min()) < 1e-3         # all risk contributions equal
    assert abs(rc.max() - 1.0 / n) < 1e-3          # = 1/n
    assert abs(w.sum() - 1.0) < 1e-9 and (w > 0).all()


def test_erc_does_not_collapse_with_one_high_vol_leg():
    # the failure mode the damping fixes: an undamped solver dumps all weight onto a
    # 2-asset corner. With crypto-like vol dispersion, ERC must still spread risk.
    n = 6
    corr = np.full((n, n), 0.4)
    np.fill_diagonal(corr, 1.0)
    cov = _cov([0.12, 0.6, 0.18, 0.16, 0.2, 0.07], corr)   # one very high-vol (0.6) leg
    w = erc_weights(cov)
    rc = _risk_contrib(w, cov)
    assert rc.max() < 2.0 / n                       # no single market hogs the risk
    assert (w > 1e-3).sum() >= n - 1                # weight is spread, not a corner


def test_inverse_vol_downweights_volatile_markets():
    rb = risk_budget(_synth_returns(), window=120, cfg={"erc_iters": 2000, "erc_tol": 1e-9})
    iv = rb["inverse_vol"]["weights"]
    # the synthetic 'hi' column has the largest vol -> smallest inverse-vol weight
    assert iv["hi"] == min(iv.values())


def _synth_returns() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    idx = pd.date_range("2020-01-01", periods=300, freq="B")
    return pd.DataFrame({
        "lo": rng.normal(0, 0.005, 300), "mid": rng.normal(0, 0.01, 300),
        "hi": rng.normal(0, 0.04, 300), "x": rng.normal(0, 0.012, 300),
    }, index=idx)


def test_stress_replay_surfaces_drawdown():
    rng = np.random.default_rng(1)
    idx = pd.date_range("2019-06-01", "2020-12-31", freq="B")
    r = pd.DataFrame({"a": rng.normal(0, 0.01, len(idx)), "b": rng.normal(0, 0.01, len(idx))}, index=idx)
    r.loc["2020-02-19":"2020-04-30"] -= 0.03        # inject the COVID crash
    out = {w["crisis"]: w for w in stress_replay(r)}
    assert "2020 COVID" in out
    assert out["2020 COVID"]["book_maxdd_pct"] < 0
    assert out["2020 COVID"]["book_return_pct"] < 0


def test_snapshot_smoke():
    s = snapshot()
    assert "headline" in s or s.get("verdict") == "unknown"
    if "risk_budget" in s:
        for sch in ("equal_weight", "inverse_vol", "erc"):
            assert sch in s["risk_budget"]
