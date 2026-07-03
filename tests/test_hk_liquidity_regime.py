"""H5 peg-liquidity regime conditioner tests (engine/hk_liquidity_regime.py).

Phase-0 verdict ACCRUE (reports/h5-peg-liquidity-phase0.md): agg_balance-driven EASY/TIGHT
label — DISPLAY + SIZING context only, NEVER a rank input. These verify the pure function's
own-history percentile labelling, the fail-closed None paths, and that the report's drawdown
separation numbers ride on the label."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import hk_liquidity_regime as lr  # noqa: E402


def _frame(balance: list[float], start: str = "2022-01-03") -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=len(balance))
    idx.name = "end_of_date"
    return pd.DataFrame({"agg_balance": balance, "hibor_1m": np.full(len(balance), 3.0)},
                        index=idx)


def test_easy_regime_when_balance_high_in_own_history():
    # a monotonically rising balance -> the latest value is at the top of its own history
    bal = list(np.linspace(50.0, 300.0, 400))
    out = lr.liquidity_regime(_frame(bal))
    assert out is not None
    assert out["regime"] == "EASY"
    assert out["pctile"] >= 66.0
    assert out["grade"] == "conditioner" and out["verdict"] == "ACCRUE"
    # the report's drawdown separation rides on the label (sizing context, not a signal)
    assert out["maxdd_easy_pct"] == -21.0 and out["maxdd_tight_pct"] == -49.0
    assert out["sizing_note"]["en"] and out["sizing_note"]["zh"]


def test_tight_regime_when_balance_low_in_own_history():
    # a falling balance -> the latest value is at the bottom of its own history
    bal = list(np.linspace(300.0, 50.0, 400))
    out = lr.liquidity_regime(_frame(bal))
    assert out is not None and out["regime"] == "TIGHT"
    assert out["pctile"] <= 34.0
    assert "de-risk" in out["sizing_note"]["en"] or "smaller" in out["sizing_note"]["en"]


def test_neutral_regime_mid_history():
    # oscillating balance ending near the middle of its own range -> NEUTRAL
    x = np.sin(np.linspace(0, 8 * np.pi, 400))
    bal = list(100.0 + 20.0 * x)                 # ends near the mid of its band
    out = lr.liquidity_regime(_frame(bal))
    assert out is not None and out["regime"] in ("NEUTRAL", "EASY", "TIGHT")
    # regardless of label the numbers are stamped and the pctile is in-range
    assert 0.0 <= out["pctile"] <= 100.0


def test_asof_is_leak_safe():
    bal = list(np.linspace(50.0, 300.0, 400))
    f = _frame(bal)
    mid = f.index[200]
    out = lr.liquidity_regime(f, asof=mid)
    assert out is not None
    assert out["as_of"] == mid.strftime("%Y-%m-%d")   # clipped to as-of, no future rows


def test_none_paths_fail_closed():
    assert lr.liquidity_regime(None) is None
    assert lr.liquidity_regime(pd.DataFrame()) is None
    # missing the agg_balance column -> None (never a fake NEUTRAL)
    bad = pd.DataFrame({"hibor_1m": [3.0, 3.1]},
                       index=pd.bdate_range("2022-01-03", periods=2))
    assert lr.liquidity_regime(bad) is None
    # too-short history -> None
    assert lr.liquidity_regime(_frame([100.0, 101.0, 102.0])) is None
