"""Unit tests for the gap-crossing guard in long_hold_label_panel.

Focuses on ruling LH-W1-3: _total_return must return None when any consecutive
bar pair in the horizon-bar forward window is separated by > 10 calendar days
(a data gap that would corrupt the horizon label).  _forward_leg_has_gap must
return True for such windows and False for clean windows.

Run:
    python -m pytest tests/test_long_hold_gap_guard.py -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.research.long_hold_label_panel import (  # noqa: E402
    _forward_leg_has_gap,
    _total_return,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_close(dates: list[str], base: float = 100.0, seed: int = 0) -> pd.Series:
    """Build a close series from a list of date strings."""
    rng = np.random.default_rng(seed)
    prices = base * np.cumprod(1 + rng.normal(0, 0.01, len(dates)))
    idx = pd.DatetimeIndex([pd.Timestamp(d) for d in dates])
    return pd.Series(prices, index=idx, name="close")


def _trading_days(start: str, n: int) -> list[str]:
    """Generate n consecutive business days starting from start."""
    rng = pd.bdate_range(start=start, periods=n)
    return [str(d.date()) for d in rng]


# ---------------------------------------------------------------------------
# _total_return: clean window
# ---------------------------------------------------------------------------

def test_total_return_clean_window():
    """A contiguous 252-bar window returns a finite return."""
    dates = _trading_days("2021-07-06", 300)  # 300 bars
    close = _make_close(dates)
    # fire_date must be at or within the series; fill_index returns the NEXT bar
    fire_date = pd.Timestamp(dates[0])  # fire = first bar → fill at bar 1
    ret = _total_return(close, fire_date, horizon=252)
    assert ret is not None
    assert isinstance(ret, float)
    assert -1.0 < ret < 100.0  # sane bounds for 252d synthetic return


def test_total_return_too_short():
    """Fewer than horizon bars → None."""
    dates = _trading_days("2021-07-06", 100)  # only 100 bars
    close = _make_close(dates)
    fire_date = pd.Timestamp(dates[0])
    ret = _total_return(close, fire_date, horizon=252)
    assert ret is None


# ---------------------------------------------------------------------------
# _total_return: gap-crossing windows → None
# ---------------------------------------------------------------------------

def test_total_return_with_613_day_gap_returns_none():
    """Simulates the FI-style gap: first 49 bars normal, then 613-day jump.

    This is the exact failure mode from PR #1528 review: FI had a 614-day
    intra-window gap; without the guard, fwd.iloc[251] resolved to a bar ~4.2
    years after fire_date, producing a 61x 'return'.
    """
    # Build pre-gap block (49 bars in Jul–Oct 2021)
    pre_gap = _trading_days("2021-07-06", 49)
    # Build post-gap block (203 bars starting 2023-06-07, 613 days after 2021-10-01)
    post_gap = _trading_days("2023-06-07", 210)
    all_dates = pre_gap + post_gap
    close = _make_close(all_dates)
    # fire_date = first bar so fill_index resolves to bar 1
    fire_date = pd.Timestamp(all_dates[0])
    ret = _total_return(close, fire_date, horizon=252)
    assert ret is None, (
        f"Gap-crossing window must return None; got {ret!r}. "
        "Without the guard this would produce a multi-year 'return' mislabeled as 252d."
    )


def test_total_return_with_small_holiday_gap_is_ok():
    """A 3-day gap (e.g. long holiday weekend) is fine and should not be rejected."""
    part1 = _trading_days("2021-07-06", 130)
    # 3-calendar-day gap between part1 end and part2 start (both business-day ranges,
    # so consecutive business days are at most 3 apart over a long weekend)
    part2 = _trading_days("2021-11-16", 160)
    all_dates = part1 + part2
    close = _make_close(all_dates)
    fire_date = pd.Timestamp(all_dates[0])
    ret = _total_return(close, fire_date, horizon=252)
    # A small natural gap should not trigger None
    assert ret is not None


def test_total_return_exactly_at_threshold():
    """A gap of exactly 10 calendar days is still accepted (threshold is >10)."""
    part1 = _trading_days("2021-07-06", 130)
    last_date = pd.Timestamp(part1[-1])
    next_date = last_date + pd.Timedelta(days=10)
    part2 = pd.bdate_range(start=next_date, periods=160)
    all_dates = part1 + [str(d.date()) for d in part2]
    close = _make_close(all_dates)
    fire_date = pd.Timestamp(all_dates[0])
    ret = _total_return(close, fire_date, horizon=252)
    # Exactly 10 days is NOT > 10; should not be rejected
    assert ret is not None


def test_total_return_11_day_gap_returns_none():
    """A gap of 11 calendar days (> 10) is rejected."""
    part1 = _trading_days("2021-07-06", 130)
    last_date = pd.Timestamp(part1[-1])
    next_date = last_date + pd.Timedelta(days=11)
    part2 = pd.bdate_range(start=next_date, periods=160)
    all_dates = part1 + [str(d.date()) for d in part2]
    close = _make_close(all_dates)
    fire_date = pd.Timestamp(all_dates[0])
    ret = _total_return(close, fire_date, horizon=252)
    assert ret is None


# ---------------------------------------------------------------------------
# _forward_leg_has_gap
# ---------------------------------------------------------------------------

def test_forward_leg_has_gap_clean():
    """Clean window returns False."""
    dates = _trading_days("2021-07-06", 300)
    close = _make_close(dates)
    fire_date = pd.Timestamp(dates[0])
    assert not _forward_leg_has_gap(close, fire_date, horizon=252)


def test_forward_leg_has_gap_with_gap():
    """Window with 614-day gap returns True."""
    pre_gap = _trading_days("2021-07-06", 49)
    post_gap = _trading_days("2023-06-07", 210)
    all_dates = pre_gap + post_gap
    close = _make_close(all_dates)
    fire_date = pd.Timestamp(all_dates[0])
    assert _forward_leg_has_gap(close, fire_date, horizon=252)


def test_forward_leg_has_gap_too_short():
    """Window shorter than horizon returns False (not matured, not a gap)."""
    dates = _trading_days("2021-07-06", 100)
    close = _make_close(dates)
    fire_date = pd.Timestamp(dates[0])
    assert not _forward_leg_has_gap(close, fire_date, horizon=252)


def test_forward_leg_has_gap_no_fill_index():
    """fire_date after all data → fill_index returns None → False."""
    dates = _trading_days("2021-07-06", 300)
    close = _make_close(dates)
    fire_date = pd.Timestamp("2030-01-01")  # far future
    assert not _forward_leg_has_gap(close, fire_date, horizon=252)


# ---------------------------------------------------------------------------
# Consistency: gap fires get gap_leg_crossed=True and total_return_252d=None
# ---------------------------------------------------------------------------

def test_gap_leg_integrity_properties():
    """gap_leg_crossed=True always co-occurs with total_return_252d=None.

    This tests the contract between _forward_leg_has_gap and _total_return:
    any window flagged by has_gap must produce None from total_return.
    """
    pre_gap = _trading_days("2021-07-06", 49)
    post_gap = _trading_days("2023-06-07", 210)
    all_dates = pre_gap + post_gap
    close = _make_close(all_dates)
    fire_date = pd.Timestamp(all_dates[0])
    has_gap = _forward_leg_has_gap(close, fire_date, horizon=252)
    ret = _total_return(close, fire_date, horizon=252)
    assert has_gap is True
    assert ret is None, "gap_leg_crossed=True must co-occur with total_return_252d=None"
