"""Raw-month unit contract for the display-only Atlanta-Fed inflation read."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.conditions import (
    annualized_monthly_percent_windows,
    conditions_snapshot,
    raw_atlanta_inflation_history,
)
from scripts.build_site import nowcast_history


def _raw(column: str, values: list[float], dates: list[str] | None = None) -> pd.DataFrame:
    index = (
        pd.to_datetime(dates)
        if dates is not None
        else pd.date_range("2025-01-01", periods=len(values), freq="MS")
    )
    return pd.DataFrame({column: values}, index=index)


def _annualized(rates: list[float]) -> float:
    return (np.prod([1.0 + rate / 100.0 for rate in rates]) ** (12.0 / len(rates)) - 1.0) * 100.0


def test_exact_window_compounds_monthly_percent_changes() -> None:
    rates = [1.0, -0.5, 0.25]
    out = annualized_monthly_percent_windows(_raw("value", rates), 3, value_column="value")
    assert out.iloc[:2].isna().all()
    assert out.iloc[-1] == pytest.approx(_annualized(rates), rel=1e-12)


def test_equal_prints_in_adjacent_months_are_distinct_observations() -> None:
    out = annualized_monthly_percent_windows(
        _raw("value", [0.2, 0.2, 0.2]), 3, value_column="value"
    )
    assert out.iloc[-1] == pytest.approx(_annualized([0.2, 0.2, 0.2]), rel=1e-12)


@pytest.mark.parametrize(
    "frame",
    [
        _raw("value", [0.1, 0.2, 0.3], ["2025-01-01", "2025-03-01", "2025-04-01"]),
        _raw("value", [0.1, np.nan, 0.3], ["2025-01-01", "2025-02-01", "2025-03-01"]),
    ],
)
def test_missing_source_month_or_null_never_forms_a_window(frame: pd.DataFrame) -> None:
    out = annualized_monthly_percent_windows(frame, 3, value_column="value")
    assert out.isna().all()


def test_forward_filled_daily_rows_are_rejected_as_non_monthly() -> None:
    monthly = pd.Series(
        [0.1, 0.2, 0.3], index=pd.date_range("2025-01-01", periods=3, freq="MS")
    )
    daily = monthly.reindex(pd.date_range("2025-01-01", "2025-03-31", freq="D")).ffill()
    out = annualized_monthly_percent_windows(daily, 3)
    assert out.empty


def test_raw_loader_does_not_fallback_between_lobes() -> None:
    calls: list[str] = []

    def reader(group: str, series_id: str) -> pd.DataFrame | None:
        assert group == "fred"
        calls.append(series_id)
        if series_id == "STICKCPIM157SFRBATL":
            return _raw("sticky_cpi", [0.2, 0.2, 0.2])
        return None

    out = raw_atlanta_inflation_history(3, reader=reader)
    assert out["sticky"].iloc[-1] == pytest.approx(_annualized([0.2] * 3), rel=1e-12)
    assert out["flexible"].empty
    assert calls == ["STICKCPIM157SFRBATL", "FLEXCPIM157SFRBATL"]


def test_raw_loader_clips_future_observation_periods() -> None:
    frame = _raw("sticky_cpi", [0.1, 0.2, 0.3, 9.9])

    def reader(group: str, series_id: str) -> pd.DataFrame | None:
        if group == "fred" and series_id == "STICKCPIM157SFRBATL":
            return frame
        return None

    out = raw_atlanta_inflation_history(3, reader=reader, as_of="2025-03-31")
    assert out["sticky"].index[-1] == pd.Timestamp("2025-03-01")
    assert out["sticky"].iloc[-1] == pytest.approx(_annualized([0.1, 0.2, 0.3]), rel=1e-12)


def test_snapshot_and_site_history_use_raw_store_not_feature_ffill(monkeypatch) -> None:
    sticky_rates = [0.10, 0.20, 0.30, 0.40, 0.40, 0.50]
    flexible_rates = [0.50, 0.40, 0.30, 0.20, 0.10, 0.00]
    raw = {
        "STICKCPIM157SFRBATL": _raw("sticky_cpi", sticky_rates),
        "FLEXCPIM157SFRBATL": _raw("flex_cpi", flexible_rates),
    }

    def reader(group: str, series_id: str) -> pd.DataFrame | None:
        return raw.get(series_id) if group == "fred" else None

    monkeypatch.setattr("engine.conditions.store.read", reader)
    idx = pd.bdate_range("2024-01-01", periods=400)
    # Deliberately absurd daily values prove the display does not consume the
    # forward-filled feature-frame columns.
    features = pd.DataFrame(
        {
            "SPY": np.linspace(400.0, 420.0, len(idx)),
            "sticky_cpi": 99.0,
            "flex_cpi": -99.0,
        },
        index=idx,
    )
    expected_sticky = _annualized(sticky_rates[-3:])
    expected_flexible = _annualized(flexible_rates[-3:])

    inflation = conditions_snapshot(features)["inflation_nowcast"]
    assert inflation["sticky_ann"] == pytest.approx(expected_sticky, rel=1e-12)
    assert inflation["flexible_ann"] == pytest.approx(expected_flexible, rel=1e-12)
    assert inflation["window_months"] == 3
    assert inflation["source_units"] == "percent_change_from_month_ago"
    assert inflation["output_units"] == "percent_change_at_annual_rate"
    assert inflation["source_series"]["sticky"]["observation_month"] == "2025-06"

    history = nowcast_history(features)
    assert history["sticky"]["last"] == round(expected_sticky, 1)
    assert history["flexible"]["last"] == round(expected_flexible, 1)


def test_missing_latest_raw_window_is_null_and_not_charted(monkeypatch) -> None:
    raw = {
        "STICKCPIM157SFRBATL": _raw(
            "sticky_cpi", [0.1, 0.2, 0.3], ["2025-01-01", "2025-03-01", "2025-04-01"]
        ),
        "FLEXCPIM157SFRBATL": _raw(
            "flex_cpi", [0.1, np.nan, 0.3], ["2025-01-01", "2025-02-01", "2025-03-01"]
        ),
    }

    def reader(group: str, series_id: str) -> pd.DataFrame | None:
        return raw.get(series_id) if group == "fred" else None

    monkeypatch.setattr("engine.conditions.store.read", reader)
    idx = pd.bdate_range("2025-01-01", periods=160)
    features = pd.DataFrame({"SPY": np.linspace(400.0, 410.0, len(idx))}, index=idx)
    inflation = conditions_snapshot(features)["inflation_nowcast"]
    assert inflation["sticky_ann"] is None
    assert inflation["flexible_ann"] is None
    history = nowcast_history(features)
    assert "sticky" not in history
    assert "flexible" not in history


def test_invalid_window_is_rejected() -> None:
    with pytest.raises(ValueError, match="window_months"):
        annualized_monthly_percent_windows(_raw("value", [0.2]), 0)
