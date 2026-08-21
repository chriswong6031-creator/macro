"""Regression tests for the OPEX calendar boundary contract."""

from __future__ import annotations

import numpy as np
import pandas as pd

from engine import opex


def _history_ending_before_august_opex() -> pd.DatetimeIndex:
    """A realistic daily history whose final bar precedes the 2026-08-21 OPEX."""
    return pd.bdate_range("2024-01-02", "2026-08-19")


def test_expiration_days_does_not_project_future_opex_onto_last_bar() -> None:
    idx = _history_ending_before_august_opex()

    expirations = opex.expiration_days(idx)

    assert pd.Timestamp("2026-08-19") not in expirations.index
    assert expirations.index[-1] == pd.Timestamp("2026-07-17")
    assert expirations.index.is_unique


def test_tag_leaves_next_expiry_unknown_when_history_ends_before_it() -> None:
    tagged = opex.tag(_history_ending_before_august_opex())

    last = tagged.loc[pd.Timestamp("2026-08-19")]
    assert pd.isna(last["td_to"])
    assert bool(last["in_opex_week"]) is False
    assert bool(last["is_quad_cycle"]) is False
    assert last["phase"] == "mid_cycle"


def test_snapshot_does_not_publish_zero_day_or_quad_for_august_19() -> None:
    idx = _history_ending_before_august_opex()
    close = pd.Series(np.linspace(100.0, 150.0, len(idx)), index=idx)

    snap = opex.snapshot(close)

    assert snap["available"] is True
    assert snap["td_to_opex"] is None
    assert snap["in_opex_week"] is False
    assert snap["is_quad_cycle"] is False
    assert snap["phase"] == "mid_cycle"


def test_later_months_cannot_collapse_onto_a_truncated_history_tail() -> None:
    idx = _history_ending_before_august_opex()

    expirations = opex.expiration_days(idx)

    assert pd.Timestamp("2026-09-18") not in expirations.index
    assert pd.Timestamp("2026-12-18") not in expirations.index
    assert not expirations.index.to_series().gt(idx[-1]).any()


def test_holiday_expiry_rolls_back_to_previous_trading_day() -> None:
    # Good Friday 2025 was the third Friday in April and the market was closed.
    # Include the following session so the index proves the Friday is a historical
    # holiday rather than an unobserved future date at a truncated series boundary.
    idx = pd.bdate_range("2025-01-02", "2025-04-21").drop(pd.Timestamp("2025-04-18"))

    expirations = opex.expiration_days(idx)

    assert pd.Timestamp("2025-04-17") in expirations.index
    assert bool(expirations.loc[pd.Timestamp("2025-04-17")]) is False


def test_real_quarterly_expiries_remain_quad() -> None:
    idx = pd.bdate_range("2025-01-02", "2025-12-19")

    expirations = opex.expiration_days(idx)

    for expiry in ("2025-03-21", "2025-06-20", "2025-09-19", "2025-12-19"):
        assert bool(expirations.loc[pd.Timestamp(expiry)]) is True


def test_actual_august_expiry_remains_zero_day_and_non_quad() -> None:
    idx = pd.bdate_range("2024-01-02", "2026-08-21")

    last = opex.tag(idx).loc[pd.Timestamp("2026-08-21")]

    assert last["td_to"] == 0
    assert last["td_since"] == 0
    assert bool(last["in_opex_week"]) is True
    assert bool(last["is_quad_cycle"]) is False


def test_empty_index_is_a_truthful_empty_result() -> None:
    idx = pd.DatetimeIndex([])

    expirations = opex.expiration_days(idx)
    tagged = opex.tag(idx)

    assert expirations.empty
    assert list(tagged.columns) == [
        "td_since",
        "td_to",
        "in_opex_week",
        "in_post_opex",
        "is_quad_cycle",
        "phase",
    ]
    assert tagged.empty
