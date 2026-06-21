"""Regression test for the sticky/flexible CPI double-annualization bug.

The Atlanta-Fed M157 sticky/flexible CPI series are published as 'Percent Change at
Annual Rate' (already annual-rate, ~2-6%). A prior version re-annualized them via
((1+x/100)**12-1)*100, turning 3.2% into ~46%. _smooth_annual_rate must smooth WITHOUT
re-annualizing — units in == units out."""
import numpy as np
import pandas as pd

from engine.conditions import _smooth_annual_rate


def test_smooth_annual_rate_does_not_reannualize():
    idx = pd.bdate_range("2020-01-01", periods=400)
    for level in (2.0, 3.2, 6.0):
        out = _smooth_annual_rate(pd.Series(level, index=idx), 3).iloc[-1]
        assert abs(out - level) < 0.5, f"{level}% re-annualized to {out:.1f}% (the bug)"
        assert out < 12, f"output {out:.1f}% is in the impossible double-annualized range"


def test_smooth_annual_rate_is_monotone_preserving():
    """The qualitative read (sticky >= flexible) must survive the smoothing."""
    idx = pd.bdate_range("2020-01-01", periods=400)
    sticky = _smooth_annual_rate(pd.Series(4.0, index=idx), 3).iloc[-1]
    flexible = _smooth_annual_rate(pd.Series(2.5, index=idx), 3).iloc[-1]
    assert sticky > flexible
