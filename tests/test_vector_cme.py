"""Bitcoin Vector CME (regulated) futures-basis context (D-vec-CME).
Pure compute on synthetic inputs. No network.

Run: .venv/bin/python -m tests.test_vector_cme
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from engine.btc_signals import cme_basis  # noqa: E402

CFG = {"ann_mult": 12, "pctile_lookback_d": 365, "froth_pct": 0.7, "stress_pct": -0.2}


def _inputs(spot, fut):
    idx = pd.date_range("2018-01-01", periods=len(spot), freq="D")
    return {"price": pd.DataFrame({"close": np.asarray(spot)}, index=idx),
            "btc_future": pd.Series(np.asarray(fut), index=idx)}


def test_basis_sign_and_regime():
    n = 500
    spot = pd.Series(np.linspace(40000, 60000, n))
    rich = cme_basis(_inputs(spot, spot * 1.012), CFG)          # +1.2% premium -> contango
    back = cme_basis(_inputs(spot, spot * 0.995), CFG)          # -0.5% -> backwardation
    flat = cme_basis(_inputs(spot, spot * 1.002), CFG)          # +0.2% -> flat
    assert round(rich["cme_basis"].iloc[-1], 1) == 1.2
    assert rich["cme_basis_regime"].iloc[-1] == "contango"
    assert back["cme_basis_regime"].iloc[-1] == "backwardation"
    assert flat["cme_basis_regime"].iloc[-1] == "flat"
    assert round(rich["cme_basis_ann"].iloc[-1]) == round(1.2 * 12)   # annualized x mult


def test_missing_future_returns_empty():
    spot = pd.Series(np.full(50, 50000.0))
    out = cme_basis({"price": pd.DataFrame({"close": spot},
                     index=pd.date_range("2020-01-01", periods=50)), "btc_future": None}, CFG)
    assert "cme_basis" not in out.columns


if __name__ == "__main__":
    for fn in [test_basis_sign_and_regime, test_missing_future_returns_empty]:
        fn()
        print(f"  ok  {fn.__name__}")
    print("all vector CME-basis tests passed")
