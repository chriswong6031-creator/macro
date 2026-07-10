"""Tests for expanding_mean walk-forward benchmark (MRI-R28b).

Verifies:
1. No lookahead: expanding_mean at step j uses only actuals from steps 0..j-1.
2. First valid index: result_pos=0 yields None, result_pos=1+ yields a value.
3. Matches manual calculation on a toy series.
4. Correct behavior with None/NaN actuals (skip them).
"""
import math
import numpy as np
import pytest

# Import the helper from the backtest harness (no engine dependency)
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from research.release_forecast.backtest_release_forecast import _attach_expanding_mean


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_results(actuals: list) -> list[dict]:
    """Build a minimal results list with result_pos set."""
    rows = []
    for i, a in enumerate(actuals):
        rows.append({
            "result_pos": i,
            "actual": a,
            "predicted": 0.0,  # not needed for expanding mean
        })
    return rows


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_first_row_is_none():
    """result_pos=0 must yield None (no prior observations)."""
    results = _make_results([0.1, 0.2, 0.3])
    _attach_expanding_mean(results)
    assert results[0]["baseline_expanding_mean"] is None, (
        "First row must have expanding_mean=None (no prior observations)"
    )


def test_second_row_equals_first_actual():
    """result_pos=1 must equal actuals[0] (only one prior)."""
    actuals = [0.2, 0.4, 0.6]
    results = _make_results(actuals)
    _attach_expanding_mean(results)
    assert results[1]["baseline_expanding_mean"] == pytest.approx(actuals[0]), (
        "Second row expanding_mean must equal first actual"
    )


def test_no_lookahead_property():
    """At each step j, expanding_mean[j] must NOT depend on actuals[j] or later."""
    actuals = [0.1, 0.3, 0.2, 0.5, 0.4]
    results = _make_results(actuals)
    _attach_expanding_mean(results)

    # Manually verify: expanding_mean[j] = mean(actuals[:j])
    for j, r in enumerate(results):
        em = r["baseline_expanding_mean"]
        if j == 0:
            assert em is None
        else:
            expected = float(np.mean(actuals[:j]))
            assert em == pytest.approx(expected, abs=1e-10), (
                f"At j={j}: expected expanding_mean={expected:.6f}, got {em:.6f}"
            )


def test_matches_manual_calculation():
    """Toy series: exact match against manually computed expanding means."""
    actuals = [1.0, 2.0, 3.0, 4.0, 5.0]
    expected_ems = [
        None,         # j=0: no prior
        1.0,          # j=1: mean([1.0])
        1.5,          # j=2: mean([1.0, 2.0])
        2.0,          # j=3: mean([1.0, 2.0, 3.0])
        2.5,          # j=4: mean([1.0, 2.0, 3.0, 4.0])
    ]
    results = _make_results(actuals)
    _attach_expanding_mean(results)

    for j, (r, exp) in enumerate(zip(results, expected_ems)):
        em = r["baseline_expanding_mean"]
        if exp is None:
            assert em is None, f"j={j}: expected None, got {em}"
        else:
            assert em == pytest.approx(exp, abs=1e-10), (
                f"j={j}: expected {exp}, got {em}"
            )


def test_none_actual_skipped():
    """None actuals are skipped — they should not appear in the expanding mean."""
    actuals = [1.0, None, 3.0, 4.0]
    results = _make_results(actuals)
    _attach_expanding_mean(results)

    # j=0: None (no prior)
    assert results[0]["baseline_expanding_mean"] is None

    # j=1: mean([1.0]) = 1.0 (None at j=0 skipped for update, but 1.0 at j=0 is valid)
    assert results[1]["baseline_expanding_mean"] == pytest.approx(1.0)

    # j=2: actual[1] was None -> skipped; expanding mean still = mean([1.0]) = 1.0
    assert results[2]["baseline_expanding_mean"] == pytest.approx(1.0)

    # j=3: actual[2]=3.0 contributed; expanding_mean = mean([1.0, 3.0]) = 2.0
    assert results[3]["baseline_expanding_mean"] == pytest.approx(2.0)


def test_unsorted_result_pos_handled():
    """Function should sort by result_pos and compute expanding mean correctly even if
    rows are passed in non-sequential order."""
    # Create rows in reverse order
    actuals = [0.1, 0.3, 0.5, 0.7]
    results = _make_results(actuals)
    # Shuffle
    shuffled = [results[3], results[1], results[0], results[2]]
    _attach_expanding_mean(shuffled)

    # After attachment, find row by result_pos
    by_pos = {r["result_pos"]: r for r in shuffled}
    assert by_pos[0]["baseline_expanding_mean"] is None
    assert by_pos[1]["baseline_expanding_mean"] == pytest.approx(actuals[0])
    assert by_pos[2]["baseline_expanding_mean"] == pytest.approx(np.mean(actuals[:2]))
    assert by_pos[3]["baseline_expanding_mean"] == pytest.approx(np.mean(actuals[:3]))


def test_single_row():
    """Single row: no prior obs, expanding_mean must be None."""
    results = _make_results([0.5])
    _attach_expanding_mean(results)
    assert results[0]["baseline_expanding_mean"] is None


def test_two_rows():
    """Two rows: first None, second equals first actual."""
    actuals = [0.25, 0.75]
    results = _make_results(actuals)
    _attach_expanding_mean(results)
    assert results[0]["baseline_expanding_mean"] is None
    assert results[1]["baseline_expanding_mean"] == pytest.approx(0.25)


def test_negative_and_zero_actuals():
    """Expanding mean works correctly with negative and zero values."""
    actuals = [-0.2, 0.0, 0.4, -0.1]
    results = _make_results(actuals)
    _attach_expanding_mean(results)

    expected = [None, -0.2, -0.1, 0.2 / 3]
    for j, (r, exp) in enumerate(zip(results, expected)):
        em = r["baseline_expanding_mean"]
        if exp is None:
            assert em is None
        else:
            assert em == pytest.approx(exp, abs=1e-10), f"j={j}: expected {exp}, got {em}"
