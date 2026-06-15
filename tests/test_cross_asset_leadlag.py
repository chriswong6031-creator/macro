"""Cross-asset lead/lag transmission gauge (engine/cross_asset.py:leadlag_*).

The whole point of the gauge is to be honest about a noisy, unstable measurement,
so the tests assert: (1) an INJECTED lead is detected at the right lag and
direction, (2) the reverse direction is NOT spuriously strong (no look-ahead leak
from the z_F(t)·z_L(t-k) construction), (3) pure noise yields ~no FDR survivors,
(4) thin / <3-market data degrades to empty, and (5) the live snapshot has the
right shape with only lag>=1 links.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine import cross_asset as ca


def _frame(cols: dict, start: str = "2015-01-01") -> pd.DataFrame:
    n = len(next(iter(cols.values())))
    idx = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({k: np.asarray(v, float) for k, v in cols.items()}, index=idx)


def test_detects_injected_lead_and_direction():
    rng = np.random.default_rng(0)
    n = 700
    L = rng.normal(size=n)
    F = 0.6 * np.concatenate([[0.0], L[:-1]]) + rng.normal(scale=0.5, size=n)  # F(t)=0.6 L(t-1)+noise
    X = rng.normal(size=n)                                                     # independent
    df = _frame({"L": L, "F": F, "X": X})
    recs = ca.leadlag_pairs(df, [1, 2, 3], window=len(df), hac_lags=10, alpha=0.10)

    def get(leader, follower, lag):
        return next(r for r in recs if r["leader"] == leader
                    and r["follower"] == follower and r["lag"] == lag)

    lf = get("L", "F", 1)
    assert lf["r"] > 0.2 and lf["t"] > 4 and lf["sig"]          # the real link
    assert get("L", "F", 2)["r"] < lf["r"]                      # lag-1 dominates lag-2
    assert abs(get("F", "L", 1)["r"]) < lf["r"]                 # reverse is weaker (no leak)
    assert not get("X", "F", 1)["sig"]                          # independent market not flagged


def test_pure_noise_has_almost_no_fdr_survivors():
    rng = np.random.default_rng(3)
    n = 700
    df = _frame({c: rng.normal(size=n) for c in "ABCD"})
    recs = ca.leadlag_pairs(df, [1, 2, 3, 5], window=n, hac_lags=10, alpha=0.05)
    assert sum(r["sig"] for r in recs) <= 2                     # FDR keeps false positives ~0


def test_degrades_on_thin_or_too_few_markets():
    big = _frame({c: range(40) for c in "ABC"})
    assert ca.leadlag_pairs(big, [1], window=252) == []        # too few rows
    wide = _frame({c: np.random.default_rng(1).normal(size=400) for c in "AB"})
    assert ca.leadlag_pairs(wide, [1], window=300) == []       # <3 markets


def test_snapshot_shape_real_or_skips():
    snap = ca.leadlag_snapshot()
    assert "verdict" in snap
    if snap["verdict"] == "unknown":
        return                                                  # data absent in this checkout
    assert snap["verdict"] in ("lead", "weak_lead", "contemporaneous")
    assert snap["markets"] and "links" in snap and "evidence" in snap
    for l in snap["links"]:
        assert l["lag"] >= 1                                    # lead/lag only, never lag-0
        assert {"leader", "follower", "r", "t", "q"} <= set(l)
    if snap["verdict"] in ("lead", "weak_lead"):
        assert snap["n_significant"] >= 1 and snap["lead_asset"]
