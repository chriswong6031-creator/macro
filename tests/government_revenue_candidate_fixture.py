"""Canonical input boundary shared by the Government Revenue candidate suites.

Both candidate suites deliberately project the *live* committed generation under
``data/government_revenue/`` rather than a pinned copy: that makes them a live
probe over the artifact the site actually ships, which a frozen fixture cannot
be.  The price is that the suites inherit the collection lane's clock.

``build_government_revenue_candidates`` refuses any source whose ``known_at`` is
after the frozen ``generated_at`` it was handed (``_validate_canonical_latest_
workspace``).  That guard is correct -- publishing a projection stamped earlier
than the data it read would put the generation ahead of its own declared vintage
-- but pairing it with a hand-typed wall-clock literal makes the suite a
scheduled failure.  #4406 minted ``2026-08-03T15:00:00+00:00`` just after the
then-current vintage; the guard stayed quiet while ``known_at`` sat at
2026-08-02T00:14:34Z, then fired the moment the ``govrev`` collection lane
advanced it to 2026-08-07T02:37:59Z (commit ``f5e34a86abb``).  Thirty tests went
red with no code change involved, and re-typing a fresher literal only re-arms
the same bomb for the next collection.

Deriving the run clock from the very documents the fixture root copies keeps the
clock and the data one coherent vintage *by construction*, so no future
collection can re-arm it.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
import json
from pathlib import Path
import shutil
from typing import Any, Iterator


ROOT = Path(__file__).resolve().parents[1]
CANONICAL_DIRECTORY = Path("data/government_revenue")

#: The materializer's immutable input boundary -- the only documents the suites
#: copy out of the live tree.  The derived clock is computed from exactly these,
#: so the fixture root and the clock can never describe different vintages.
CANONICAL_INPUTS = ("latest.json", "workspace.json", "recipient_entity_graph.json")

#: Floor for the derived clock.  The suites also synthesize hand-authored
#: fixtures whose clocks are fixed (``tests/test_government_revenue_candidates``
#: tops out at 2026-08-02T18:00Z; the API suite pins an observation at
#: 2026-08-02T13:00Z), so the run clock must stay forward of those even if the
#: canonical source were rolled back.  This is #4406's original literal, which
#: means the derivation reproduces that constant exactly on the vintage that
#: shipped it -- the change is a strict generalization, not a re-baseline.
_FLOOR = datetime(2026, 8, 3, 15, 0, tzinfo=timezone.utc)


def canonical_fixture_root(tmp_path: Path) -> Path:
    """Copy only the materializer's immutable input boundary into a temp root."""
    data_dir = tmp_path / CANONICAL_DIRECTORY
    data_dir.mkdir(parents=True)
    for name in CANONICAL_INPUTS:
        shutil.copy2(ROOT / CANONICAL_DIRECTORY / name, data_dir / name)
    return tmp_path


def _known_at_values(node: Any) -> Iterator[str]:
    """Yield every ``*known_at`` string anywhere in a canonical document.

    The writer guards the top-level ``known_at`` of ``latest``/``workspace`` and
    the recipient graph's ``graph_known_at``, but a nested receipt clock that
    outran them would be just as much a source-newer-than-run violation, so the
    walk is exhaustive rather than schema-pinned.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(value, str) and key.endswith("known_at"):
                yield value
            else:
                yield from _known_at_values(value)
    elif isinstance(node, list):
        for value in node:
            yield from _known_at_values(value)


def _instant(value: str) -> datetime | None:
    """Parse an offset-aware ISO-8601 instant, or ``None`` if it is not one."""
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


@lru_cache(maxsize=1)
def canonical_newest_known_at() -> str | None:
    """Return the newest ``*known_at`` across the copied boundary, or ``None``.

    This is the raw source instant the derived clock is built on top of, and the
    boundary every backward offset has to stay clear of: a synthesized clock at
    or behind it describes a run that read documents it could not yet have seen.
    ``None`` means no parseable ``*known_at`` exists anywhere in the inputs, so
    there is no such boundary to respect.

    Normalized exactly the way the writer normalizes it (``datetime.isoformat``
    on a UTC instant), like every other instant this module hands out.
    """
    newest: datetime | None = None
    for name in CANONICAL_INPUTS:
        document = json.loads(
            (ROOT / CANONICAL_DIRECTORY / name).read_text(encoding="utf-8")
        )
        for raw in _known_at_values(document):
            parsed = _instant(raw)
            if parsed is not None and (newest is None or parsed > newest):
                newest = parsed
    return None if newest is None else newest.isoformat()


@lru_cache(maxsize=1)
def canonical_frozen_at() -> str:
    """Return a run clock coherent with the canonical inputs currently on disk.

    Every ``*known_at`` in the copied boundary must be at or before the frozen
    clock, so the clock is the next whole hour after the newest of them (see
    :func:`canonical_newest_known_at`), never below :data:`_FLOOR`.  Rounding up
    to the hour keeps the value strictly forward of every source clock -- the
    realistic ordering, since a run happens after its inputs are known -- and
    keeps it legible in failure output so the suites' relative offsets stay
    unambiguous: the forward ones (+30m, +1h, +9h) read straight off the hour,
    and the backward ones route through :func:`rewound`, which cannot be read as
    a plain subtraction because the round-up leaves it no guaranteed room.

    The value is normalized exactly the way the writer normalizes it
    (``datetime.isoformat`` on a UTC instant), so tests may compare it verbatim
    against the ``generated_at`` the writer persists.
    """
    raw_newest = canonical_newest_known_at()
    newest = None if raw_newest is None else _instant(raw_newest)
    if newest is None:
        return _FLOOR.isoformat()
    run_at = (newest + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    return max(run_at, _FLOOR).isoformat()


def utc_date(instant: str) -> str:
    """Return the UTC calendar date of ``instant`` as ``YYYY-MM-DD``."""
    parsed = _instant(instant)
    if parsed is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {instant!r}")
    return parsed.date().isoformat()


def shifted(instant: str, **delta: float) -> str:
    """Return ``instant`` moved by ``delta``, in the writer's normalized form."""
    parsed = _instant(instant)
    if parsed is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {instant!r}")
    return (parsed + timedelta(**delta)).isoformat()


def _clamped_rewind(anchor: str, rewind: timedelta, *, floor: str | None) -> str:
    """Return ``anchor`` pulled back by ``rewind``, never at or behind ``floor``.

    A backward offset taken from :func:`canonical_frozen_at` inherits that
    clock's round-up: the anchor is the next whole hour after the newest source
    instant, so the room between the two is whatever the minute hand happened to
    leave -- uniform in (0, 60] minutes, and in principle as thin as a single
    microsecond.  Subtracting a fixed literal from it is this module's header
    bomb one level down.  ``shifted(FROZEN_AT, seconds=-1)`` reads green on every
    vintage whose margin exceeds a second and reds the fleet the night the
    collection lane lands one that does not, with no code change involved; worse,
    it reds it with the wrong message, because the builder's canonical guard
    ("canonical latest known_at is after the frozen generated_at clock") fires
    before the semantics under test ever get a turn.  That guard is right -- a run
    clock at or behind a source it read is exactly the violation
    ``_validate_canonical_latest_workspace`` exists to catch -- so the fix belongs
    in the offset, never in the guard.

    While the margin is healthy the nominal rewind is returned untouched,
    bit-identical to the arithmetic it replaces.  When the margin is too thin to
    absorb it, the result is the midpoint of ``(floor, anchor)``: the point that
    stays maximally clear of BOTH strict boundaries.  It is strictly inside the
    interval whenever that interval spans two microseconds or more, and degrades
    to equality with the floor only when the interval is a single microsecond --
    admissible even then, because every builder ordering guard fires on a strict
    ``>`` (a source *after* the clock), never on equality.  It always stays
    strictly below the anchor, so every "before the run" semantic the callers
    build on survives the clamp.
    """
    parsed = _instant(anchor)
    if parsed is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {anchor!r}")
    if rewind <= timedelta(0):
        raise ValueError(f"rewind must be a positive magnitude, not {rewind!r}")
    if floor is None:
        return (parsed - rewind).isoformat()
    boundary = _instant(floor)
    if boundary is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {floor!r}")
    if parsed <= boundary:
        raise ValueError(
            f"anchor {anchor!r} is not after the floor {floor!r}: nothing to rewind into"
        )
    nominal = parsed - rewind
    if nominal > boundary:
        return nominal.isoformat()
    return (boundary + (parsed - boundary) / 2).isoformat()


def rewound(instant: str, **delta: float) -> str:
    """Return ``instant`` moved back by ``delta``, clamped strictly inside the vintage.

    ``delta`` is a rewind magnitude, so its components are positive; see
    :func:`_clamped_rewind` for what the clamp defends against.
    """
    return _clamped_rewind(instant, timedelta(**delta), floor=canonical_newest_known_at())
