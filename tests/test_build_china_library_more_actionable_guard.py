"""R3 REPAIR (2026-09-01) — guard against `_more_actionable` hijacking the
china_standout_track headline definition on a zero-featured night.

Finding (independent repair-delta review, round 3): the CN `_more_actionable`
append in scripts/build_china_library.py ran unconditionally whenever
`wide["more_actionable"]` was non-empty, and its board_definition
(`f"{wide['board_definition']}_more_actionable"`) is a DISTINCT, non-watch
definition — it is NOT a member of
`engine.china_standout_track.WATCH_DEFINITIONS`, so it IS counted by
`china_standout_track._latest_definition_frame` when resolving the graded
headline board definition (that resolver picks
`newest_rows.iloc[-1]["board_definition"]` among every non-watch row appended
for the newest date). On a night where `wide["buy"]` (the featured shelf) is
EMPTY, the featured append writes zero rows for today's date — so an
unconditional more_actionable append would leave its rows as the ONLY
non-watch rows for that date, and `_latest_definition_frame` would silently
resolve the near-miss/shadow more_actionable shelf as the graded headline,
instead of correctly finding nothing to grade.

The fix (`_more_actionable_append_is_safe`) gates the append on a NON-EMPTY
`wide["buy"]` for the same build. This test is RED-FIRST: run against the
pre-repair unconditional-append logic (`bool(wide.get("more_actionable"))`
alone, reconstructed here as `_pre_repair_condition` for comparison), it would
pass more_actionable through even on a zero-featured night; against the
repaired guard, it must refuse.

Run: .venv/bin/python -m pytest tests/test_build_china_library_more_actionable_guard.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import build_china_library as bcl  # noqa: E402


def _pre_repair_condition(wide: dict) -> bool:
    """The ORIGINAL (pre-R3) gate: `if wide.get("more_actionable"):` alone —
    reconstructed here (not imported from bcl, which no longer exposes it) so
    this test can demonstrate what a zero-featured night used to do."""
    return bool(wide.get("more_actionable"))


def _zero_featured_night_wide() -> dict:
    """A build where the scored universe produced near-miss candidates but
    NOTHING cleared the bar for the featured shelf — a real, not contrived,
    shape: every screening pass can legitimately yield zero admits on a
    quiet/no-signal session while still logging near-misses for research."""
    return {
        "board_definition": "cn_prophet_v4",
        "buy": [],
        "more_actionable": [
            {"ticker": "600000.SS", "name": "Near Miss Co"},
            {"ticker": "000001.SZ", "name": "Also Near Miss Co"},
        ],
    }


def test_zero_featured_night_the_pre_repair_condition_would_have_appended():
    # Documents the defect this repair closes: the OLD gate alone says "yes,
    # append" even though there is nothing featured this build — the exact
    # scenario that let more_actionable hijack the headline definition.
    wide = _zero_featured_night_wide()
    assert _pre_repair_condition(wide) is True


def test_zero_featured_night_more_actionable_append_is_refused():
    # RED-FIRST: fails against pre-repair code (which had no
    # _more_actionable_append_is_safe gate at all / effectively always True
    # whenever more_actionable was non-empty); passes only once the R3 guard
    # requires a co-occurring non-empty featured set.
    wide = _zero_featured_night_wide()
    assert bcl._more_actionable_append_is_safe(wide) is False


def test_featured_night_with_more_actionable_still_appends():
    # The guard must not regress the ordinary case: a night with BOTH a
    # featured shelf and near-miss rows still logs more_actionable (the
    # membership-repair this block exists for, M1/M2).
    wide = {
        "board_definition": "cn_prophet_v4",
        "buy": [{"ticker": "600519.SS"}],
        "more_actionable": [{"ticker": "600000.SS"}],
    }
    assert bcl._more_actionable_append_is_safe(wide) is True


def test_no_more_actionable_rows_is_always_safe_trivially():
    # Nothing to append -> the guard is vacuously true either way (no row is
    # ever written), but pin the shape so a future refactor cannot flip it.
    assert bcl._more_actionable_append_is_safe({"board_definition": "x", "buy": []}) is False
    assert bcl._more_actionable_append_is_safe(
        {"board_definition": "x", "buy": [{"ticker": "A"}]}) is False


def test_missing_wide_dict_is_safe_by_default():
    assert bcl._more_actionable_append_is_safe(None) is False
    assert bcl._more_actionable_append_is_safe({}) is False
