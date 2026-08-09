"""Unit tests for exact sticky/flexible CPI trailing-rate annualization."""
import numpy as np
import pandas as pd
import pytest

from engine.conditions import _smooth_annual_rate


def _monthly(values: list[float]) -> pd.Series:
    return pd.Series(values, index=pd.date_range("2025-01-01", periods=len(values), freq="MS"))


def test_constant_monthly_rate_is_compounded_and_annualized_exactly():
    monthly_pct = 0.25
    out = _smooth_annual_rate(_monthly([monthly_pct] * 3), 3).iloc[-1]
    expected = ((1.0 + monthly_pct / 100.0) ** 12 - 1.0) * 100.0
    assert out == pytest.approx(expected, rel=1e-12)


def test_mixed_three_month_window_uses_product_not_arithmetic_mean():
    rates = [1.0, -0.5, 0.25]
    out = _smooth_annual_rate(_monthly(rates), 3).iloc[-1]
    expected = (np.prod([1.0 + r / 100.0 for r in rates]) ** 4 - 1.0) * 100.0
    assert out == pytest.approx(expected, rel=1e-12)


def test_requires_a_full_trailing_window():
    out = _smooth_annual_rate(_monthly([0.2, 0.3, 0.4]), 3)
    assert out.iloc[:2].isna().all()
    assert np.isfinite(out.iloc[-1])


def test_repeated_monthly_prints_are_not_deduplicated():
    out = _smooth_annual_rate(_monthly([0.2, 0.2, 0.2]), 3)
    assert np.isfinite(out.iloc[-1])
    expected = ((1.002**3) ** 4 - 1.0) * 100.0
    assert out.iloc[-1] == pytest.approx(expected, rel=1e-12)


def test_daily_forward_fill_maps_each_calendar_month_once():
    monthly = _monthly([0.1, 0.2, 0.3, 0.4])
    daily_idx = pd.date_range("2025-01-01", "2025-04-30", freq="D")
    daily = monthly.reindex(daily_idx).ffill()
    out = _smooth_annual_rate(daily, 3)
    march_expected = (np.prod([1.001, 1.002, 1.003]) ** 4 - 1.0) * 100.0
    assert out.loc["2025-03-01":"2025-03-31"].nunique() == 1
    assert out.loc["2025-03-31"] == pytest.approx(march_expected, rel=1e-12)


def test_missing_calendar_month_does_not_form_a_false_trailing_window():
    series = pd.Series(
        [0.1, 0.2, 0.3],
        index=pd.to_datetime(["2025-01-01", "2025-03-01", "2025-04-01"]),
    )
    out = _smooth_annual_rate(series, 3)
    assert out.isna().all()


def test_smooth_annual_rate_is_monotone_preserving():
    """The qualitative read (sticky >= flexible) must survive the smoothing."""
    sticky = _smooth_annual_rate(_monthly([0.4, 0.4, 0.4]), 3).iloc[-1]
    flexible = _smooth_annual_rate(_monthly([0.2, 0.2, 0.2]), 3).iloc[-1]
    assert sticky > flexible


def test_invalid_window_rejected():
    with pytest.raises(ValueError, match="smooth_months"):
        _smooth_annual_rate(_monthly([0.2]), 0)
