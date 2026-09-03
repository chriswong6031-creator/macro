"""Pure-function invariants for the S-MLC-3 harness (scripts/s_mlc_3_weekly_wait_cost.py).

No network, no parquet reads — these test the rank/universe/confirm building
blocks against the frozen pre-reg (research/S_MLC_3_WEEKLY_WAIT_COST_PREREG.md)
in isolation. Runs in well under a second.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.s_mlc_3_weekly_wait_cost import (  # noqa: E402
    CORE9,
    XLRE_INCEPTION,
    XLC_INCEPTION,
    universe_for_date,
    next_friday_on_or_after,
    confirm_fires,
    rank_descending,
)


# --------------------------------------------------------------------------- #
# universe_for_date — time-varying 9 -> 10 -> 11 (Ruling 2)
# --------------------------------------------------------------------------- #

def test_universe_pre_xlre_is_core9_only():
    u = universe_for_date(pd.Timestamp("2010-01-04"))
    assert set(u) == set(CORE9)
    assert len(u) == 9


def test_universe_at_xlre_inception_adds_xlre():
    u = universe_for_date(XLRE_INCEPTION)
    assert "XLRE" in u
    assert "XLC" not in u
    assert len(u) == 10


def test_universe_day_before_xlre_inception_excludes_it():
    u = universe_for_date(XLRE_INCEPTION - pd.Timedelta(days=1))
    assert "XLRE" not in u
    assert len(u) == 9


def test_universe_at_xlc_inception_is_full_11():
    u = universe_for_date(XLC_INCEPTION)
    assert "XLRE" in u and "XLC" in u
    assert len(u) == 11


def test_universe_day_before_xlc_inception_is_10():
    u = universe_for_date(XLC_INCEPTION - pd.Timedelta(days=1))
    assert "XLRE" in u
    assert "XLC" not in u
    assert len(u) == 10


def test_universe_recent_date_is_full_11():
    u = universe_for_date(pd.Timestamp("2026-08-01"))
    assert len(u) == 11


# --------------------------------------------------------------------------- #
# next_friday_on_or_after — pure calendar arithmetic (§1.5)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("date_str,expected", [
    ("2026-08-31", "2026-09-04"),  # Monday -> that week's Friday
    ("2026-09-04", "2026-09-04"),  # Friday -> itself
    ("2026-09-05", "2026-09-11"),  # Saturday -> next Friday
    ("2026-09-06", "2026-09-11"),  # Sunday -> next Friday
    ("2026-09-03", "2026-09-04"),  # Thursday -> next day
])
def test_next_friday_on_or_after(date_str, expected):
    got = next_friday_on_or_after(pd.Timestamp(date_str))
    assert got == pd.Timestamp(expected)


def test_next_friday_is_always_a_friday():
    for offset in range(14):
        d = pd.Timestamp("2026-01-01") + pd.Timedelta(days=offset)
        f = next_friday_on_or_after(d)
        assert f.weekday() == 4
        assert f >= d


# --------------------------------------------------------------------------- #
# confirm_fires — delta=0 PRIMARY strict rule (Ruling 3)
# --------------------------------------------------------------------------- #

def test_confirm_fires_strict_delta0_at_or_above():
    assert confirm_fires(ref_close=100.0, entry_close=100.0, delta=0.0) is True
    assert confirm_fires(ref_close=100.01, entry_close=100.0, delta=0.0) is True


def test_confirm_fails_strict_delta0_below_entry():
    assert confirm_fires(ref_close=99.99, entry_close=100.0, delta=0.0) is False


def test_confirm_delta_sensitivity_tolerates_drawdown():
    # 1% below entry: fails at delta=0, fires at delta=0.01
    assert confirm_fires(ref_close=99.0, entry_close=100.0, delta=0.0) is False
    assert confirm_fires(ref_close=99.0, entry_close=100.0, delta=0.01) is True


def test_confirm_fires_handles_missing_data():
    assert confirm_fires(ref_close=None, entry_close=100.0, delta=0.0) is False
    assert confirm_fires(ref_close=float("nan"), entry_close=100.0, delta=0.0) is False


# --------------------------------------------------------------------------- #
# rank_descending — cross-sectional RS rank, min-tie method
# --------------------------------------------------------------------------- #

def test_rank_descending_basic_order():
    ranks = rank_descending({"A": 0.10, "B": 0.05, "C": -0.02})
    assert ranks["A"] == 1
    assert ranks["B"] == 2
    assert ranks["C"] == 3


def test_rank_descending_ties_get_min_rank():
    ranks = rank_descending({"A": 0.10, "B": 0.10, "C": 0.01})
    assert ranks["A"] == 1
    assert ranks["B"] == 1
    assert ranks["C"] == 3  # next distinct value skips to 3, not 2


def test_rank_descending_drops_nan_and_none():
    ranks = rank_descending({"A": 0.10, "B": float("nan"), "C": None, "D": 0.02})
    assert set(ranks.keys()) == {"A", "D"}
    assert ranks["A"] == 1
    assert ranks["D"] == 2


def test_rank_descending_empty():
    assert rank_descending({}) == {}
    assert rank_descending({"A": None, "B": float("nan")}) == {}
