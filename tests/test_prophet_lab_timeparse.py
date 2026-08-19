"""Adversarial tests for engine/prophet_lab/timeparse.py (day-2 temporal
correctness amendment, 2026-08-19).

These pin the ONE canonical instant-parsing/comparison helper the honesty
path (engine/prophet_lab/observation.py + sources.py) now uses instead of
raw lexicographic string compares. See timeparse.py's module docstring for
the measured failure mode this replaces:
``"2026-08-19T09:00:00-04:00"`` (13:00 UTC) sorts lexicographically BEFORE
``"2026-08-19T10:00:00Z"`` (10:00 UTC) even though it names the LATER
instant.
"""
from __future__ import annotations

from datetime import datetime, timezone

from engine.prophet_lab.timeparse import earliest_instant_string, parse_instant


# ---------------------------------------------------------------------------
# parse_instant — normalization and offset-form coverage
# ---------------------------------------------------------------------------
def test_parse_instant_normalizes_z_suffix() -> None:
    parsed = parse_instant("2026-08-19T10:00:00Z")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_normalizes_lowercase_z_suffix() -> None:
    parsed = parse_instant("2026-08-19T10:00:00z")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_accepts_explicit_positive_offset() -> None:
    # 2026-08-19T18:00:00+08:00 -> 10:00:00 UTC
    parsed = parse_instant("2026-08-19T18:00:00+08:00")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_accepts_explicit_negative_offset() -> None:
    # 2026-08-19T06:00:00-04:00 -> 10:00:00 UTC
    parsed = parse_instant("2026-08-19T06:00:00-04:00")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


def test_parse_instant_accepts_explicit_utc_offset_form() -> None:
    parsed = parse_instant("2026-08-19T10:00:00+00:00")
    assert parsed == datetime(2026, 8, 19, 10, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# EQUAL INSTANTS, DIFFERENT OFFSET NOTATION — must compare/classify identically
# ---------------------------------------------------------------------------
def test_parse_instant_equal_instant_different_offset_forms_compare_equal() -> None:
    z_form = parse_instant("2026-08-19T10:00:00Z")
    offset_form = parse_instant("2026-08-19T06:00:00-04:00")
    assert z_form is not None and offset_form is not None
    assert z_form == offset_form


def test_parse_instant_all_four_offset_forms_of_the_same_instant_are_equal() -> None:
    # The SAME instant (10:00:00 UTC) named four different ways.
    forms = [
        "2026-08-19T10:00:00Z",
        "2026-08-19T10:00:00+00:00",
        "2026-08-19T06:00:00-04:00",
        "2026-08-19T18:00:00+08:00",
    ]
    parsed = [parse_instant(f) for f in forms]
    assert all(p is not None for p in parsed)
    assert len(set(parsed)) == 1, "all four forms must parse to the SAME instant"


# ---------------------------------------------------------------------------
# fail-closed: naive and unparseable input
# ---------------------------------------------------------------------------
def test_parse_instant_rejects_naive_timestamp() -> None:
    # No UTC offset at all -> reject, never guess (see timeparse.py DEFEND note).
    assert parse_instant("2026-08-19T10:00:00") is None


def test_parse_instant_rejects_bare_date() -> None:
    assert parse_instant("2026-08-19") is None


def test_parse_instant_rejects_garbage_string() -> None:
    assert parse_instant("not-a-timestamp") is None


def test_parse_instant_rejects_empty_and_none() -> None:
    assert parse_instant("") is None
    assert parse_instant(None) is None
    assert parse_instant("   ") is None


# ---------------------------------------------------------------------------
# before/after across offset forms, on BOTH sides of a reference instant
# ---------------------------------------------------------------------------
def test_parse_instant_before_across_offset_forms() -> None:
    reference = parse_instant("2026-08-19T10:00:00Z")  # 10:00 UTC
    before_forms = [
        "2026-08-19T09:59:59Z",           # 09:59:59 UTC
        "2026-08-19T09:59:59+00:00",      # 09:59:59 UTC
        "2026-08-19T05:59:59-04:00",      # 09:59:59 UTC
        "2026-08-19T17:59:59+08:00",      # 09:59:59 UTC
    ]
    for form in before_forms:
        parsed = parse_instant(form)
        assert parsed is not None
        assert parsed < reference, f"{form} must parse before the reference instant"


def test_parse_instant_after_across_offset_forms() -> None:
    reference = parse_instant("2026-08-19T10:00:00Z")  # 10:00 UTC
    after_forms = [
        "2026-08-19T10:00:01Z",           # 10:00:01 UTC
        "2026-08-19T10:00:01+00:00",      # 10:00:01 UTC
        "2026-08-19T06:00:01-04:00",      # 10:00:01 UTC
        "2026-08-19T18:00:01+08:00",      # 10:00:01 UTC
    ]
    for form in after_forms:
        parsed = parse_instant(form)
        assert parsed is not None
        assert parsed > reference, f"{form} must parse after the reference instant"


# ---------------------------------------------------------------------------
# earliest_instant_string
# ---------------------------------------------------------------------------
def test_earliest_instant_string_picks_the_correct_earliest_across_offset_forms() -> None:
    # "2026-08-19T09:00:00-04:00" is 13:00 UTC -- LATER than the other two,
    # despite sorting FIRST lexicographically ('09' < '10' < '18').
    candidates = [
        "2026-08-19T09:00:00-04:00",  # 13:00 UTC
        "2026-08-19T10:00:00Z",       # 10:00 UTC -- the true earliest
        "2026-08-19T18:00:00+08:00",  # 10:00 UTC (ties the Z form at 10:00 UTC)
    ]
    assert earliest_instant_string(candidates) == "2026-08-19T10:00:00Z"


def test_earliest_instant_string_skips_unparseable_and_naive_entries() -> None:
    candidates = [
        "not-a-timestamp",
        "2026-08-19T10:00:00",       # naive -> skipped
        "2026-08-19T09:00:00-04:00",  # 13:00 UTC -- the only valid entry
    ]
    assert earliest_instant_string(candidates) == "2026-08-19T09:00:00-04:00"


def test_earliest_instant_string_all_unparseable_returns_none() -> None:
    assert earliest_instant_string(["garbage", "", None, "2026-08-19"]) is None


def test_earliest_instant_string_empty_input_returns_none() -> None:
    assert earliest_instant_string([]) is None


# ---------------------------------------------------------------------------
# THE REGRESSION CASE — proves the OLD lexicographic bug is gone
# ---------------------------------------------------------------------------
def test_regression_lexicographic_compare_would_have_picked_the_wrong_earliest() -> None:
    """The exact pairing named in the day-2 mandate.

    ``"2026-08-19T10:00:00Z"`` (10:00 UTC) and ``"2026-08-19T09:00:00-04:00"``
    (13:00 UTC) — the second string is LEXICOGRAPHICALLY SMALLER ('09' < '10')
    but names the LATER instant. A raw ``min()``/``<`` over the strings would
    have picked the -04:00 form as "earliest", which is backwards.
    """
    a = "2026-08-19T10:00:00Z"           # 10:00 UTC -- the TRUE earlier instant
    b = "2026-08-19T09:00:00-04:00"      # 13:00 UTC -- actually LATER
    assert b < a, (
        "sanity check: 'b' sorts BEFORE 'a' lexicographically ('09' < '10') "
        "even though 'b' names the later instant -- this is the exact bug"
    )
    assert parse_instant(a) < parse_instant(b), "the TRUE earlier instant is `a`, not `b`"
    assert earliest_instant_string([a, b]) == a, (
        "a raw min()/`<` over the strings would have returned `b` here -- backwards"
    )
