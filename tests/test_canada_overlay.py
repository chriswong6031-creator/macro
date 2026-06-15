"""Canada commodity/CAD/BoC overlay tests (engine/canada_overlay.py).

Pure terms-of-trade logic + the composite's min-factor gating (monkeypatching the
store-backed factor_series so the test needs no data). The overlay is DISPLAY-FIRST
context, so these guard its mechanics, not a forward-return edge."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import canada_overlay as co  # noqa: E402


def test_terms_of_trade():
    # commodities up + CAD strong (usdcad down) -> improving
    assert co._terms_of_trade({"oil": 1.0, "gold": 1.0, "usdcad": -1.0}) == "improving"
    # commodities down + CAD weak (usdcad up) -> deteriorating
    assert co._terms_of_trade({"oil": -1.0, "gold": -1.0, "usdcad": 1.0}) == "deteriorating"
    # crossed signals -> mixed
    assert co._terms_of_trade({"oil": 1.0, "gold": -1.0, "usdcad": 1.0}) == "mixed"


_IDX0 = pd.bdate_range("2020-01-01", periods=300)
_IDX = _IDX0[150:]          # eval window fully inside the factor-series span


def _series(direction: float) -> pd.Series:
    return pd.Series(np.linspace(100.0, 100.0 + direction * 30.0, len(_IDX0)), index=_IDX0)


def test_composite_risk_on_when_factors_align(monkeypatch):
    # oil/gold/spy rising (sign +1) -> risk-on; usdcad rising would be risk-off, omit it
    monkeypatch.setattr(co, "factor_series", lambda: {
        "oil": _series(1), "gold": _series(1), "spy": _series(1)})
    comp = co.composite(_IDX)
    assert "risk_state" in comp.columns
    assert comp["risk_state"].iloc[-1] == "Risk-on"


def test_composite_unknown_below_min_factors(monkeypatch):
    # only 2 factors present but min_factors is 3 -> score NaN -> state 'unknown'
    monkeypatch.setattr(co, "factor_series", lambda: {"oil": _series(1), "gold": _series(1)})
    comp = co.composite(_IDX)
    assert comp["risk_state"].iloc[-1] == "unknown"
