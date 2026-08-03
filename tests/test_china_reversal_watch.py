"""Washout reversal_watch lane — the invariants that keep it a MEASUREMENT surface.

Prereg: charting-app docs/PREREG_WASHOUT_REVERSAL.md §5.4. Two hard rules:
  1. Watch cohorts must NEVER own the headline Prophet grade — grade()'s
     definition resolution excludes WATCH_DEFINITIONS regardless of append order.
  2. detect() is fail-quiet and PIT-shaped: short/garbage series → None, never raise.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.china_standout_track import (  # noqa: E402
    WATCH_DEFINITIONS, _latest_definition_frame,
)
from engine.china_reversal_watch import BOARD_DEFINITION, detect  # noqa: E402


def test_watch_definition_is_registered():
    assert BOARD_DEFINITION in WATCH_DEFINITIONS


def test_watch_rows_never_own_the_headline_grade():
    """Appending watch rows LAST on the newest date must not flip the graded cohort
    (the pre-fix resolution took the last row's definition on the newest date)."""
    df = pd.DataFrame([
        {"date": "2026-07-30", "ticker": "A", "board_definition": "cn_prophet_v2"},
        {"date": "2026-08-01", "ticker": "B", "board_definition": "cn_prophet_v2"},
        {"date": "2026-08-01", "ticker": "C", "board_definition": BOARD_DEFINITION},
    ])
    frame, definition = _latest_definition_frame(df)
    assert definition == "cn_prophet_v2"
    assert set(frame["ticker"]) == {"A", "B"}


def test_legacy_nan_rows_keep_all_row_behavior():
    df = pd.DataFrame([
        {"date": "2026-07-01", "ticker": "A", "board_definition": None},
        {"date": "2026-07-02", "ticker": "B", "board_definition": None},
    ])
    frame, definition = _latest_definition_frame(df)
    assert definition is None
    assert len(frame) == 2


def test_detect_fail_quiet_on_short_or_garbage():
    idx = pd.bdate_range("2026-01-01", periods=50)
    assert detect(pd.Series(np.linspace(10, 12, 50), index=idx)) is None
    assert detect(pd.Series(dtype=float)) is None
    # non-datetime index must degrade to None, never raise
    assert detect(pd.Series([1.0] * 400)) is None


def test_detect_ignores_uptrend_names():
    """A steadily rising name (no washout, no bear regime) can never be admitted."""
    idx = pd.bdate_range("2020-01-01", periods=1600)
    rng = np.random.default_rng(7)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0.0008, 0.01, 1600)), index=idx)
    close = close * np.linspace(1.0, 2.2, 1600)  # force an uptrend envelope
    assert detect(close) is None
