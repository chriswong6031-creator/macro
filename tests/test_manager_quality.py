"""Manager-Quality Score: forward-return mechanics, market-adjustment, grading."""
from __future__ import annotations

import pandas as pd
import pytest

from engine import manager_quality as mq


def _closes(**series) -> pd.DataFrame:
    idx = pd.bdate_range("2025-01-01", periods=80)
    return pd.DataFrame({k: v for k, v in series.items()}, index=idx)


def test_forward_return_basic_and_horizon_guard():
    c = _closes(AAA=[100.0 + i for i in range(80)])      # +1/day
    # entry day 0, horizon 10 -> price 100 -> 110 = +10%
    r = mq.forward_return(c, "AAA", "2025-01-01", horizon=10)
    assert abs(r - 0.10) < 1e-6
    # horizon running past the data end -> None (never score an unfinished window)
    assert mq.forward_return(c, "AAA", c.index[-3].isoformat(), horizon=10) is None
    # unknown ticker -> None
    assert mq.forward_return(c, "ZZZ", "2025-01-01", horizon=5) is None


def test_market_forward_return_is_equal_weight_mean():
    c = _closes(A=[100.0 + i for i in range(80)],         # +10% over 10d from day0
                B=[100.0 + 2 * i for i in range(80)])      # +20% over 10d from day0
    m = mq.market_forward_return(c, "2025-01-01", 10, {})
    assert abs(m - 0.15) < 1e-6                            # (0.10 + 0.20)/2


def test_market_relative_excess_strips_beta():
    # A outruns the 2-name market; its excess is positive even in a rising tide.
    c = _closes(A=[100.0 + 2 * i for i in range(80)],
                B=[100.0 + i for i in range(80)])
    ret = mq.forward_return(c, "A", "2025-01-01", 10)
    bench = mq.market_forward_return(c, "2025-01-01", 10, {})
    assert ret - bench > 0


def test_blend_and_grade():
    assert mq._blend([0.1, 0.2], [0.0]) == pytest.approx(0.075)
    assert mq._blend([0.1], []) == pytest.approx(0.1)     # one-sided
    assert mq._blend([], []) is None
    assert mq._grade(1.0) == "A" and mq._grade(0.2) == "B"
    assert mq._grade(-0.2) == "C" and mq._grade(-1.0) == "D"
    assert mq._grade(None) == "n/a"


def test_compute_degrades_without_prices(monkeypatch):
    monkeypatch.setattr(mq, "load_closes", lambda: None)
    assert mq.compute_manager_quality() == {}
