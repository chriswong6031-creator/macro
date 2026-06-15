"""Bitcoin Vector crypto-breadth: SOL/ETH high-beta ratio + breadth_view aggregator
(D-vec-BREADTH). Pure compute on synthetic inputs. No network.

Run: .venv/bin/python -m tests.test_vector_breadth
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine import alt_cycle  # noqa: E402

CFG = {"ethbtc_ma_d": 350, "slope_window_d": 56, "pctile_lookback_d": 1095,
       "alt_season_line": 0.07, "btc_season_line": 0.05, "btc_season_max": 25,
       "alt_season_min": 75, "soleth_ma_d": 100, "soleth_slope_d": 56,
       "soleth_pctile_d": 730}


def _idx(n):
    return pd.date_range("2021-01-01", periods=n, freq="D")


def test_beta_ratio_rising_trend():
    n = 400
    eth = pd.Series(np.full(n, 2000.0), index=_idx(n))
    sol = pd.Series(np.linspace(50, 150, n), index=_idx(n))   # SOL grinds up vs flat ETH
    se = alt_cycle.beta_ratio(sol, eth, CFG)
    assert se["trend"] == "rising"
    assert se["above_ma"] is True
    assert se["slope"] > 0
    assert 0 <= se["pctile"] <= 100


def test_beta_ratio_falling_trend():
    n = 400
    eth = pd.Series(np.full(n, 2000.0), index=_idx(n))
    sol = pd.Series(np.linspace(150, 50, n), index=_idx(n))   # SOL bleeds vs ETH
    se = alt_cycle.beta_ratio(sol, eth, CFG)
    assert se["trend"] == "falling"
    assert se["above_ma"] is False


def test_beta_ratio_guards():
    assert alt_cycle.beta_ratio(None, pd.Series([1.0, 2.0, 3.0]), CFG) == {}
    short = pd.Series(np.arange(50.0), index=_idx(50))
    assert alt_cycle.beta_ratio(short, short, CFG) == {}       # < 120 obs -> empty


def test_breadth_view_assembles_and_handles_empties():
    n = 400
    eth = pd.Series(np.full(n, 2000.0), index=_idx(n))
    btc = pd.Series(np.full(n, 40000.0), index=_idx(n))
    eb = alt_cycle.ethbtc_signal(eth, btc, CFG)
    se = alt_cycle.beta_ratio(pd.Series(np.linspace(50, 150, n), index=_idx(n)), eth, CFG)
    score, bucket = alt_cycle.alt_season_score(eb, 58.0, CFG)
    bv = alt_cycle.breadth_view(eb, se, 58.0, 12.0, score, bucket)
    assert bv["bucket"] == bucket and bv["dom"] == 58.0 and bv["ethdom"] == 12.0
    assert bv["ethbtc"] is not None and bv["soleth"] is not None
    assert bv["soleth_trend"] == "rising"
    # graceful empties -> every numeric field None, never raises
    empty = alt_cycle.breadth_view({}, {}, None, None, None, "—")
    assert empty["ethbtc"] is None and empty["soleth"] is None and empty["dom"] is None


if __name__ == "__main__":
    for fn in [test_beta_ratio_rising_trend, test_beta_ratio_falling_trend,
               test_beta_ratio_guards, test_breadth_view_assembles_and_handles_empties]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector crypto-breadth tests passed")
