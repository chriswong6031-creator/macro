"""Bitcoin Vector FORWARD-RISK (drawdown) tests — reconcile the live helper with
the stored calibration so the card and the calibration table can never disagree.
Reads the repo data store (repo-is-the-database); skips cleanly if absent.

Run: .venv/bin/python -m tests.test_vector_forward_risk
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from scripts.build_vector import forward_risk, _band_of  # noqa: E402

SIG = Path("data/vector/signals.parquet")
CAL = Path("data/vector/calibration.json")


def test_band_edges_right_closed():
    # right-closed (lo, hi] to match calibrate's pd.cut(include_lowest=True)
    assert _band_of(0.0) == (0, 25)
    assert _band_of(25.0) == (0, 25)
    assert _band_of(50.0) == (25, 50)      # exact boundary -> lower band
    assert _band_of(75.0) == (50, 75)
    assert _band_of(100.0) == (75, 100)
    assert _band_of(40.8) == (25, 50)


def test_reconciles_with_calibration():
    if not (SIG.exists() and CAL.exists()):
        print("  skip (no data store)"); return
    sig = pd.read_parquet(SIG)
    R7 = forward_risk(sig, 7)
    cal = {x["band"]: x for x in json.load(open(CAL))["risk_drawdown"]["full"]}
    b = cal[R7["band"]]
    assert abs(R7["avg"] - b["avgDD_7d"]) <= 0.6, (R7["avg"], b["avgDD_7d"])
    assert abs(R7["tail"] - b["p05DD_7d"]) <= 2.0, (R7["tail"], b["p05DD_7d"])


def test_3d_is_direct_window_not_a_haircut():
    if not SIG.exists():
        print("  skip (no data store)"); return
    sig = pd.read_parquet(SIG)
    R3, R7 = forward_risk(sig, 3), forward_risk(sig, 7)
    ratio = R3["tail"] / R7["tail"]
    assert 0.35 <= ratio <= 0.75, f"3d/7d tail ratio {ratio:.2f} off vol-time band (~0.65)"


def test_excess_over_calm_and_flags():
    if not SIG.exists():
        print("  skip (no data store)"); return
    sig = pd.read_parquet(SIG)
    R = forward_risk(sig, 7)
    for k in ("avg", "tail", "calm_avg", "calm_tail", "word_en", "head_en", "main_en", "guard_en"):
        assert R.get(k) is not None, f"missing {k}"
    # the live band must be at least as severe as the calm baseline (excess-over-calm)
    assert R["tail"] <= R["calm_tail"]
    # contrarian guard fires ONLY for the high bands
    assert R["contrarian"] == (R["band"] in ("50-75", "75-100"))


if __name__ == "__main__":
    for fn in [test_band_edges_right_closed, test_reconciles_with_calibration,
               test_3d_is_direct_window_not_a_haircut, test_excess_over_calm_and_flags]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector forward-risk tests passed")
