"""Tests for the M7C-R8 basket-store staleness warning in scripts/build_baskets.py.

Covers:
  (1) Fresh store (as_of == expected session) → no ::warning emitted
  (2) Stale store (as_of one session behind) → ::warning printed, ops alert attempted
  (3) Missing as_of key → no crash, no warning
  (4) Staleness check exception → never propagates (build must not be broken)
  (5) push_ops_alert unreachable → warn still fires (fail-open)
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from unittest import mock

import pytest

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Import the function under test directly
from scripts.build_baskets import _check_basket_store_staleness  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FRESH_DATE = date(2026, 7, 10)   # a Thursday — treated as "expected last session"
_STALE_DATE = date(2026, 7, 9)    # one session behind


def _patch_expected(expected: date):
    """Patch lib.nyse_calendar.expected_last_session to return a fixed date.

    The function is imported lazily inside _check_basket_store_staleness, so we
    patch the function on the nyse_calendar module directly (not on build_baskets).
    """
    return mock.patch(
        "lib.nyse_calendar.expected_last_session",
        return_value=expected,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_fresh_store_no_warning(capsys):
    """When as_of matches expected session, no ::warning should be emitted."""
    with _patch_expected(_FRESH_DATE):
        _check_basket_store_staleness({"as_of": _FRESH_DATE.isoformat()})
    captured = capsys.readouterr()
    assert "::warning" not in captured.out


def test_stale_store_emits_warning(capsys):
    """When as_of is behind expected session, ::warning must be printed."""
    with _patch_expected(_FRESH_DATE):
        with mock.patch("engine.alert_triage.push_ops_alert", return_value=True):
            _check_basket_store_staleness({"as_of": _STALE_DATE.isoformat()})
    captured = capsys.readouterr()
    assert "::warning" in captured.out
    assert "basket store stale" in captured.out
    assert str(_STALE_DATE) in captured.out
    assert str(_FRESH_DATE) in captured.out


def test_stale_store_calls_push_ops_alert():
    """When stale, push_ops_alert should be called with the correct source/type."""
    with _patch_expected(_FRESH_DATE):
        with mock.patch(
            "engine.alert_triage.push_ops_alert", return_value=True
        ) as mock_alert:
            _check_basket_store_staleness({"as_of": _STALE_DATE.isoformat()})
    mock_alert.assert_called_once()
    call_kwargs = mock_alert.call_args
    assert call_kwargs.kwargs.get("source") == "build_baskets" or \
           (call_kwargs.args and call_kwargs.args[0] == "build_baskets")


def test_missing_as_of_no_crash_no_warning(capsys):
    """Missing as_of key must not raise and must not emit a warning."""
    with _patch_expected(_FRESH_DATE):
        _check_basket_store_staleness({})  # no 'as_of'
    captured = capsys.readouterr()
    assert "::warning" not in captured.out


def test_none_as_of_no_crash(capsys):
    """as_of=None must not raise."""
    with _patch_expected(_FRESH_DATE):
        _check_basket_store_staleness({"as_of": None})
    captured = capsys.readouterr()
    assert "::warning" not in captured.out


def test_exception_in_check_does_not_propagate():
    """If nyse_calendar is broken, staleness check must swallow the exception."""
    with mock.patch(
        "lib.nyse_calendar.expected_last_session",
        side_effect=RuntimeError("calendar exploded"),
    ):
        # Must not raise
        _check_basket_store_staleness({"as_of": "2026-07-09"})


def test_push_ops_alert_failure_does_not_suppress_warning(capsys):
    """When push_ops_alert raises, the ::warning annotation must still appear."""
    with _patch_expected(_FRESH_DATE):
        # Patch the import path so it raises when called
        with mock.patch(
            "engine.alert_triage.push_ops_alert",
            side_effect=RuntimeError("alert_triage unavailable"),
        ):
            _check_basket_store_staleness({"as_of": _STALE_DATE.isoformat()})
    captured = capsys.readouterr()
    assert "::warning" in captured.out
    assert "basket store stale" in captured.out
