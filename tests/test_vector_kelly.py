"""Bitcoin Vector conviction -> capped fractional-Kelly sizing (D-vec-KELLY).
Pure logic on synthetic + (if present) the real store. No network.

Run: .venv/bin/python -m tests.test_vector_kelly
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from scripts.build_vector import kelly_sizing  # noqa: E402

CFG = {"kelly_frac": 0.5, "dd_budget": 0.25, "pos_max": 1.0}
SIG = Path("data/vector/signals.parquet")


def _synth(stance, drift, n=2500, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2016-01-01", periods=n, freq="D")
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(drift, 0.03, n))), index=idx)
    # risk_index needed by forward_risk; keep it mid-band so a band exists
    ri = pd.Series(np.clip(40 + rng.normal(0, 8, n), 1, 99), index=idx)
    return pd.DataFrame({"close": close, "risk_index": ri, "composite_state": stance}, index=idx)


def test_positive_edge_sizes_up_negative_zeroes():
    up = kelly_sizing(_synth("ACCUMULATE", 0.0015, seed=1), CFG)   # strong up-drift -> +90d edge
    dn = kelly_sizing(_synth("RISK-OFF", -0.0012, seed=2), CFG)    # down-drift -> non-positive edge
    assert up and dn
    assert up["edge_90"] > 0 and up["size_pct"] > dn["size_pct"]
    assert dn["size_pct"] == 0                                      # non-positive edge -> hold nothing
    assert up["f_kelly"] >= 0 and 0 <= up["size_pct"] <= 100


def test_size_is_the_binding_minimum():
    s = kelly_sizing(_synth("RISK-ON", 0.001, seed=3), CFG)
    assert s
    expected = round(100 * max(0.0, min(s["f_kelly"], s["f_tail"], CFG["pos_max"])))
    assert s["size_pct"] == expected
    assert s["binding"] in ("edge", "tail")
    assert (s["binding"] == "edge") == (s["f_kelly"] <= s["f_tail"])


def test_live_sizing_is_valid():
    if not SIG.exists():
        print("  skip (no data store)"); return
    sig = pd.read_parquet(SIG)
    s = kelly_sizing(sig, CFG)
    assert s is not None
    assert 0 <= s["size_pct"] <= 100
    assert s["stance"] == sig["composite_state"].iloc[-1]
    assert s["tail_90"] < 0 and s["vol_90"] > 0


if __name__ == "__main__":
    for fn in [test_positive_edge_sizes_up_negative_zeroes, test_size_is_the_binding_minimum,
               test_live_sizing_is_valid]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector kelly-sizing tests passed")
