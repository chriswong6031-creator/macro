"""International regime engine tests (engine/intl_regime.py).

Synthetic per-country feature frame -> uniform growth/inflation axis scoring, quad
classification, the central-bank liquidity overlay and the DISPLAY-ONLY recession
composite. A clean Goldilocks construction (growth rising, inflation falling, late
rate cuts) must classify Q1; the recession gauge must stay a bounded 0-100 display.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import intl_regime as ir  # noqa: E402


def _frame(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2015-01-01", periods=n)
    f = pd.DataFrame(index=idx)
    # growth-positive
    f["gdp_yoy"] = np.linspace(0.0, 3.0, n)
    f["unemployment"] = np.linspace(7.0, 4.0, n)        # falling -> growth+ (inverted)
    f["index"] = np.linspace(15000.0, 23000.0, n)
    f["copper_gold"] = np.linspace(0.0010, 0.0013, n)
    # inflation-negative (disinflation: cpi, oil, long yields all falling)
    f["cpi_yoy"] = np.linspace(4.0, 1.5, n)
    f["oil"] = np.linspace(90.0, 60.0, n)
    f["yield_10y"] = np.linspace(4.5, 3.2, n)
    # rates / regime
    f["short_3m"] = np.concatenate([np.full(n // 2, 4.5), np.linspace(4.5, 2.5, n - n // 2)])
    f["policy_rate"] = f["short_3m"]
    f["curve"] = f["yield_10y"] - f["short_3m"]
    f["real_yield"] = f["yield_10y"] - f["cpi_yoy"]
    f["drawdown"] = np.zeros(n)                          # at highs
    return f


def test_growth_axis_positive():
    s = ir.score_axis(_frame(), "growth")["growth_score"].dropna()
    assert not s.empty and -1.0 <= s.iloc[-1] <= 1.0
    assert s.iloc[-1] > 0.5


def test_inflation_axis_negative():
    s = ir.score_axis(_frame(), "inflation")["inflation_score"].dropna()
    assert not s.empty
    assert s.iloc[-1] < -0.4


def test_classify_goldilocks():
    reg = ir.classify(_frame())
    for col in ("quad", "quad_name", "liquidity", "recession_score", "regime_confidence"):
        assert col in reg.columns
    assert reg["raw_quad"].iloc[-1] == "Q1"
    assert reg["quad_name"].dropna().iloc[-1] == "Goldilocks"


def test_recession_composite_bounded():
    rc = ir.recession_composite(_frame()).dropna()
    assert not rc.empty
    assert rc.min() >= 0.0 and rc.max() <= 100.0
    assert ir.recession_band(rc.iloc[-1]) in {"low", "watch", "elevated"}
    assert ir.recession_band(None) == "n/a"


def test_liquidity_expanding_on_cuts():
    lo = ir.liquidity_overlay(_frame())
    assert lo.iloc[-1] in {"expanding", "contracting", "neutral", "unknown"}
    assert lo.iloc[-1] == "expanding"


def test_axis_renormalises_on_missing_components():
    """A thin frame (only the equity tape) must not crash and must yield a
    low-component, low-confidence read — the Taiwan / stale-CPI degrade path."""
    f = _frame()
    thin = f[["index", "oil", "yield_10y"]].copy()        # no gdp/unemployment/cpi/copper_gold
    reg = ir.classify(thin)
    assert "quad" in reg.columns
    # growth axis has only index_trend present -> n_components < min -> 0 confidence
    assert float(reg["growth_n_components"].iloc[-1]) <= 2
