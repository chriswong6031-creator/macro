"""Test-suite conftest.py — repo-wide pytest configuration.

COLLECT_LANE sentinel
---------------------
Forward-ledger writers gate on ``COLLECT_LANE=nightly`` (or the legacy alias
``US_LANE=nightly``).  All pre-existing tests that call a writer function and
expect a write to succeed were written before the gate existed; rather than
touching every test file we set the sentinel here at session scope via an
autouse fixture.

Tests that explicitly verify the *blocked* path (e.g. TestUsLaneGate in
test_basket_turn_watch.py) pop COLLECT_LANE / US_LANE directly via
``os.environ.pop`` — that overrides the autouse value and the gate fires as
expected.  Monkeypatch-based gate tests work identically (``monkeypatch.delenv``
removes the key before the assertion, and monkeypatch restores after).
"""
import os
import pytest


@pytest.fixture(autouse=True)
def _set_nightly_lane(monkeypatch):
    """Ensure forward-ledger writes are allowed in all tests by default.

    Tests that need to verify the gate is *off* must pop COLLECT_LANE (and
    US_LANE) explicitly inside their body — the pop takes precedence because
    monkeypatch.setenv uses the live os.environ dict.
    """
    monkeypatch.setenv("COLLECT_LANE", "nightly")
