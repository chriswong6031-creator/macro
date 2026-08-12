"""Unit cover for the derived-clock helpers the candidate suites share.

These run in seconds and touch no fixture root, which is the whole point: the
offsets they exercise are derived from a live vintage, so a margin too thin to
absorb one should fail HERE, with the margin printed, rather than eight minutes
into the projection suite behind a builder guard whose message ("canonical
latest known_at is after the frozen generated_at clock") names the symptom and
hides the cause.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from tests.government_revenue_candidate_fixture import (
    _clamped_rewind,
    canonical_frozen_at,
    canonical_newest_known_at,
    rewound,
    shifted,
)
from tests.test_government_revenue_candidate_projection import (
    BEFORE_FROZEN_AT,
    CORRECTION_ACTIVATED_AT,
    FORWARD_DURING_ACTIVATION_AT,
    FROZEN_AT,
)

#: A round-up clock and the microsecond-precision source instant beneath it,
#: shaped exactly like a real vintage.
ANCHOR = "2026-08-11T05:00:00+00:00"
ROOMY_FLOOR = "2026-08-11T04:46:22.127559+00:00"


def _parsed(instant: str) -> datetime:
    return datetime.fromisoformat(instant)


def test_generous_margin_returns_the_nominal_rewind_unchanged() -> None:
    """The healthy path must be bit-identical to the subtraction it replaces."""
    assert _clamped_rewind(
        ANCHOR, timedelta(minutes=3), floor=ROOMY_FLOOR
    ) == shifted(ANCHOR, minutes=-3)


def test_margin_equal_to_the_rewind_clamps_to_the_midpoint() -> None:
    """Nominal lands exactly ON the floor, which the ordering guards reject."""
    floor = "2026-08-11T04:57:00+00:00"
    result = _parsed(_clamped_rewind(ANCHOR, timedelta(minutes=3), floor=floor))
    assert _parsed(floor) < result < _parsed(ANCHOR)
    assert result == _parsed("2026-08-11T04:58:30+00:00")


def test_margin_smaller_than_the_rewind_clamps_to_the_midpoint() -> None:
    floor = "2026-08-11T04:59:00+00:00"
    result = _parsed(_clamped_rewind(ANCHOR, timedelta(minutes=3), floor=floor))
    assert _parsed(floor) < result < _parsed(ANCHOR)
    assert result == _parsed("2026-08-11T04:59:30+00:00")


def test_sub_second_margin_with_a_microsecond_floor_stays_strictly_inside() -> None:
    """The minimal realistic vintage: half a second of room, a 1s rewind."""
    floor = "2026-08-11T04:59:59.500000+00:00"
    result = _parsed(_clamped_rewind(ANCHOR, timedelta(seconds=1), floor=floor))
    assert _parsed(floor) < result < _parsed(ANCHOR)


def test_two_microsecond_interval_still_lands_strictly_inside() -> None:
    floor = "2026-08-11T04:59:59.999998+00:00"
    result = _parsed(_clamped_rewind(ANCHOR, timedelta(seconds=1), floor=floor))
    assert _parsed(floor) < result < _parsed(ANCHOR)


def test_one_microsecond_interval_degrades_to_equality_with_the_floor() -> None:
    """The single pathological interval, and why equality is still admissible.

    A one-microsecond interval has no interior point, so the midpoint collapses
    onto the floor.  Every builder ordering guard fires on a strict ``>`` -- a
    source known AFTER the run clock -- never on equality, so a synthesized clock
    that merely coincides with the newest source instant still passes them.  The
    result stays strictly below the anchor, which is the property the callers'
    "before the run" semantics actually depend on.
    """
    floor = "2026-08-11T04:59:59.999999+00:00"
    result = _parsed(_clamped_rewind(ANCHOR, timedelta(seconds=1), floor=floor))
    assert result == _parsed(floor)
    assert result < _parsed(ANCHOR)


def test_absent_floor_is_a_plain_rewind() -> None:
    """No canonical instants exist, so there is nothing to clamp against."""
    assert _clamped_rewind(ANCHOR, timedelta(seconds=1), floor=None) == shifted(
        ANCHOR, seconds=-1
    )


@pytest.mark.parametrize(
    "anchor",
    ["2026-08-11T04:46:22.127559+00:00", "2026-08-11T04:00:00+00:00"],
)
def test_anchor_at_or_behind_the_floor_is_refused(anchor: str) -> None:
    """An empty interval is misuse -- the derived clock never produces one."""
    with pytest.raises(ValueError):
        _clamped_rewind(anchor, timedelta(seconds=1), floor=ROOMY_FLOOR)


def test_non_instant_anchor_is_refused() -> None:
    with pytest.raises(ValueError):
        _clamped_rewind("2026-08-11 05:00:00", timedelta(seconds=1), floor=None)


@pytest.mark.parametrize(
    "delta",
    [
        {"seconds": 0},
        {"seconds": -1},
        {"minutes": 1, "seconds": -90},
    ],
)
def test_non_positive_rewind_is_refused(delta: dict[str, float]) -> None:
    """``delta`` is a rewind MAGNITUDE; a zero or negative one is a caller bug."""
    with pytest.raises(ValueError):
        rewound(ANCHOR, **delta)


def test_live_vintage_offsets_stay_inside_the_shipped_margin() -> None:
    """Canary over the REAL shipped constants, not a re-derivation of them."""
    frozen = _parsed(FROZEN_AT)
    assert FROZEN_AT == canonical_frozen_at()
    assert _parsed(CORRECTION_ACTIVATED_AT) == frozen

    raw_newest = canonical_newest_known_at()
    assert raw_newest is None or _parsed(raw_newest) < frozen, (
        f"derived run clock {FROZEN_AT} is not forward of the newest source "
        f"instant {raw_newest}"
    )
    if raw_newest is None:
        return

    newest = _parsed(raw_newest)
    margin = frozen - newest
    for name, value in (
        ("BEFORE_FROZEN_AT", BEFORE_FROZEN_AT),
        ("FORWARD_DURING_ACTIVATION_AT", FORWARD_DURING_ACTIVATION_AT),
    ):
        offset = _parsed(value)
        # `>=` rather than `>`: on a one-microsecond margin the clamp lands the
        # offset exactly on the newest source instant, which the builder's
        # ordering guards admit -- they fire on a strict `>` (source after the
        # clock), never on equality.
        assert offset >= newest, (
            f"{name}={value} is behind the newest source instant {raw_newest}; "
            f"vintage margin is {margin}"
        )
        assert offset < frozen, (
            f"{name}={value} is not before the run clock {FROZEN_AT}; "
            f"vintage margin is {margin}"
        )
