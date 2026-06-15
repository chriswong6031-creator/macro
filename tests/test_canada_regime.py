"""Canada regime engine tests (engine/canada_axes.py + engine/canada_regime.py).

Synthetic feature frame -> growth/inflation axis scoring, quad classification, the
BoC liquidity overlay (policy-rate direction) and the cycle tag. A clean Goldilocks
construction (growth rising, inflation falling, late-period rate cuts) must classify
Q1 with an expanding liquidity overlay."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import canada_regime as cr  # noqa: E402
from engine.canada_axes import score_axis  # noqa: E402


def _frame(n: int = 400) -> pd.DataFrame:
    idx = pd.bdate_range("2015-01-01", periods=n)
    f = pd.DataFrame(index=idx)
    # growth inputs (all point growth-positive)
    f["gdp_yoy"] = np.linspace(0.0, 3.0, n)
    f["unemployment"] = np.linspace(7.0, 6.0, n)        # falling -> growth+ (inverted)
    f["cyc_def"] = np.linspace(1.0, 1.3, n)             # cyclicals leading
    f["copper_gold"] = np.linspace(0.0010, 0.0012, n)
    f["pct_above_50"] = np.linspace(40.0, 70.0, n)
    f["tsx_spx"] = np.linspace(0.90, 1.00, n)
    # inflation inputs (all point inflation-negative)
    f["cpi_yoy"] = np.linspace(3.0, 1.5, n)
    f["breakeven"] = np.linspace(2.2, 1.8, n)
    f["infl_basket"] = np.linspace(1.10, 0.95, n)
    # rates / regime
    f["policy_rate"] = np.concatenate([np.full(n // 2, 4.5), np.linspace(4.5, 2.5, n - n // 2)])
    f["goc_2y"] = np.linspace(4.2, 2.6, n)
    f["goc_10y"] = np.linspace(3.8, 3.2, n)
    f["curve_2s10s"] = f["goc_10y"] - f["goc_2y"]
    f["market_index"] = np.linspace(15000.0, 22000.0, n)
    return f


def test_growth_axis_positive():
    gx = score_axis(_frame(), "growth")
    s = gx["growth_score"].dropna()
    assert not s.empty
    assert -1.0 <= s.iloc[-1] <= 1.0
    assert s.iloc[-1] > 0.5            # clean growth-positive construction


def test_inflation_axis_negative():
    ix = score_axis(_frame(), "inflation")
    s = ix["inflation_score"].dropna()
    assert not s.empty
    assert s.iloc[-1] < -0.5           # clean disinflation construction


def test_classify_goldilocks():
    reg = cr.classify(_frame())
    for col in ("quad", "quad_name", "liquidity", "cycle", "regime_confidence"):
        assert col in reg.columns
    assert reg["raw_quad"].iloc[-1] == "Q1"
    assert reg["quad_name"].dropna().iloc[-1] == "Goldilocks"


def test_liquidity_overlay_expanding_on_cuts():
    lo = cr.liquidity_overlay(_frame())
    assert lo.iloc[-1] in {"expanding", "contracting", "neutral", "unknown"}
    assert lo.iloc[-1] == "expanding"   # policy rate cut over the last ~3 months


def test_cycle_tag_valid():
    ct = cr.cycle_tag(_frame())
    assert ct.iloc[-1] in {"early", "mid", "late", "unknown"}
