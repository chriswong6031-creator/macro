"""Survivorship disclosure in the US board track / surfaced-outcome data.

grade_boards() silently drops any board ticker with no usable series in the broad
closes cache (current-membership only — delisted names are invisible). A name that
left the buy board BECAUSE it collapsed and got delisted therefore vanishes from the
graded outcomes, tilting the displayed win/loss mix toward survivors. These tests pin
the fix: build_track() must emit a `survivorship` block with `n_skipped_no_price`
(distinct excluded tickers) computed from the FULL boards x names history, on both
the populated and the empty:true paths, so the dashboard strip can disclose
"(N names excluded: no price / delisted)".
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.grade_us_board import build_track, grade_boards  # noqa: E402
from tests.test_grade_us_board import _minimal_grade_df  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _names(**cols):
    """Broad-cache stand-in: 30 sessions, one column per kwarg (value or NaN)."""
    idx = pd.bdate_range("2026-01-02", periods=30)
    return pd.DataFrame({k: v for k, v in cols.items()}, index=idx)


def _board(as_of, tickers):
    return {"as_of": as_of, "rank_by": "test",
            "rows": [{"ticker": t, "lane": "buy", "position": i}
                     for i, t in enumerate(tickers)]}


# ---------------------------------------------------------------------------
# survivorship block emission
# ---------------------------------------------------------------------------

def test_skipped_count_emitted_in_track():
    """A board ticker absent from the closes cache must be counted and named."""
    names = _names(AAA=100.0, BBB=50.0)
    boards = [_board("2026-01-05", ["AAA", "BBB", "GONE"])]
    track = build_track(_minimal_grade_df(n=3), boards, names)
    surv = track["survivorship"]
    assert surv["n_skipped_no_price"] == 1
    assert surv["n_rows_skipped_no_price"] == 1
    assert surv["n_board_rows_total"] == 3
    assert "GONE" in surv["tickers_skipped"]
    assert "delisted" in surv["note"] or "survivor" in surv["note"]


def test_all_nan_series_counts_as_skipped():
    """A column that exists but is all-NaN is unusable — grade_boards skips it
    (nser.empty), so the survivorship count must treat it identically."""
    names = _names(AAA=100.0, DEAD=np.nan)
    boards = [_board("2026-01-05", ["AAA", "DEAD"])]
    track = build_track(_minimal_grade_df(n=2), boards, names)
    assert track["survivorship"]["n_skipped_no_price"] == 1
    assert track["survivorship"]["tickers_skipped"] == ["DEAD"]


def test_repeat_appearances_count_rows_but_dedupe_tickers():
    """The same delisted name on many boards is ONE excluded name, N excluded rows."""
    names = _names(AAA=100.0)
    boards = [_board("2026-01-05", ["AAA", "GONE"]),
              _board("2026-01-06", ["AAA", "GONE"]),
              _board("2026-01-07", ["GONE"])]
    track = build_track(_minimal_grade_df(n=3), boards, names)
    surv = track["survivorship"]
    assert surv["n_skipped_no_price"] == 1
    assert surv["n_rows_skipped_no_price"] == 3
    assert surv["n_board_rows_total"] == 5


def test_survivorship_block_on_empty_track():
    """The empty:true early-return (no matured rows yet) still discloses exclusions —
    the strip's first render must not imply full coverage."""
    names = _names(AAA=100.0)
    boards = [_board("2026-01-05", ["AAA", "GONE"])]
    track = build_track(pd.DataFrame(), boards, names)
    assert track.get("empty") is True
    assert track["survivorship"]["n_skipped_no_price"] == 1


def test_zero_skips_emits_zero_not_missing():
    """Full coverage => the block is still present with an explicit zero, so the
    template can distinguish 'nothing excluded' from 'field not wired'."""
    names = _names(AAA=100.0, BBB=50.0)
    boards = [_board("2026-01-05", ["AAA", "BBB"])]
    track = build_track(_minimal_grade_df(n=2), boards, names)
    assert track["survivorship"]["n_skipped_no_price"] == 0
    assert track["survivorship"]["tickers_skipped"] == []


def test_grade_boards_skip_matches_survivorship_count():
    """The block must mirror grade_boards' own skip rule exactly: what the grader
    drops (missing column OR all-NaN series) is what the block counts."""
    names = _names(AAA=100.0, DEAD=np.nan)
    boards = [_board("2026-01-05", ["AAA", "DEAD", "GONE"])]
    etfs = pd.DataFrame()  # no benchmarks needed to exercise the skip path
    df = grade_boards(boards, names, etfs)
    assert df.attrs["skipped_no_price"] == 2
    track = build_track(_minimal_grade_df(n=1), boards, names)
    assert track["survivorship"]["n_rows_skipped_no_price"] == 2
