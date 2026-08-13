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

#: The reviewed historical suppression manifest.  Its entry count is the one
#: candidate cardinality no collection lane can move -- it changes only when a
#: human re-reviews the cohort -- so it is the floor the derived counts below are
#: checked against.
REVIEWED_SUPPRESSIONS = Path(
    "config/government_revenue/candidate_historical_suppressions.v1.json"
)

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


@lru_cache(maxsize=1)
def canonical_reviewed_cohort_size() -> int:
    """Return the reviewed historical suppression manifest's entry count.

    This is the floor every derived cardinality is checked against.  Without it
    an all-derived assertion set is satisfiable by zero: an engine that went
    blind and produced no candidates at all would agree with itself across every
    artifact and read green.  The manifest is human-maintained, so a collection
    lane can never move this number to hide such a regression.
    """
    manifest = json.loads((ROOT / REVIEWED_SUPPRESSIONS).read_text(encoding="utf-8"))
    return len(manifest["entries"])


@lru_cache(maxsize=1)
def canonical_candidate_count() -> int:
    """Return the exact-linked candidate count derivable from the copied boundary.

    The suites deliberately project the live committed generation, so this
    cardinality is weather rather than a constant: the collection lane's rolling
    500-event window derived eight candidates through 2026-08-12T16:14Z and
    twenty-three at 2026-08-13T02:18Z (commit ``40baa147fa2``), with no code
    change involved.  Every hand-typed ``== 8`` in both candidate suites went red
    at once on that write -- packs 6 and 8, fleet-wide.

    Deriving the number from the very documents :func:`canonical_fixture_root`
    copies keeps the expectation and the data one vintage by construction.  It is
    the fix this module's header applied to the run clock, one quantity over, and
    for the same reason: re-typing a fresher literal only re-arms the bomb for the
    next collection.

    What the suites still pin literally is everything a collection cannot move --
    the reviewed graph's coverage and issuer roster, the mapping backlog, and
    :func:`canonical_reviewed_cohort_size`.

    The engine import is function-local on purpose.  This module is imported by
    suites in three separate CI jobs, and ``engine.government_revenue.candidates``
    pulls ``jsonschema`` at module scope; all three install lines carry it today,
    but a module-scope import here would make every one of them a hard import
    dependency of the *fixture*, so the next thin lane that borrows this helper
    reds on a wheel it never needed.  Keeping it local costs nothing -- the
    result is cached -- and keeps the fixture importable on a bare install.
    """
    from engine.government_revenue.candidates import build_candidate_queue

    latest = json.loads(
        (ROOT / CANONICAL_DIRECTORY / "latest.json").read_text(encoding="utf-8")
    )
    graph = json.loads(
        (ROOT / CANONICAL_DIRECTORY / "recipient_entity_graph.json").read_text(
            encoding="utf-8"
        )
    )
    queue = build_candidate_queue(latest, graph, generated_at=canonical_frozen_at())
    return int(queue["counts"]["total"])


def _event_known_at(event: Any) -> datetime | None:
    """Return an award event's own clock, or ``None`` when it has none to read."""
    if not isinstance(event, dict):
        return None
    change = event.get("change")
    if not isinstance(change, dict):
        return None
    known_at = change.get("known_at")
    return _instant(known_at) if isinstance(known_at, str) else None


def restrict_boundary_to_known_through(root: Path, known_through: str) -> int:
    """Drop copied award events the lane learned after ``known_through``.

    A replay of a closed historical incident is only closed if its *inputs* are.
    ``_incident_correction_root`` pairs a byte-frozen eight-row ledger with the
    live canonical boundary, so the night the lane admitted fifteen further
    events (2026-08-13) the activation run issued them, grew the ledger the
    frozen state blob binds by ``byte_count``/``sha256``, and the replay died on
    "candidate correction activation changed the incident ledger" -- again with
    no code change involved.

    Point-in-time is the honest boundary: an event the lane learned *after* the
    incident was issued is by construction not part of the incident.
    ``known_through`` is read off the reviewed correction manifest
    (``incident.issued_projection_generated_at``) rather than hand-typed, so it
    moves only when a human re-reviews the incident.  The reviewed cohort itself
    is never at risk, because the collector preserves each event's first-seen
    ``known_at`` across runs: the incident's eight sat at 2026-08-08T11:58:31Z
    while the newcomers arrived stamped 2026-08-12T23:50:04Z.

    An event's own clock is ``change.known_at`` -- the exact field the engine
    admits on (``engine/government_revenue/candidates.py``, the
    ``known_at <= analysis_as_of`` gate), not a top-level key, which award events
    do not carry.  An event whose clock is missing or unparseable is KEPT: the
    prune removes only what it can prove is late, never what it cannot read.

    Returns the number of events dropped.
    """
    from scripts import build_government_revenue

    boundary = _instant(known_through)
    if boundary is None:
        raise ValueError(f"not an offset-aware ISO-8601 instant: {known_through!r}")

    workspace_path = root / CANONICAL_DIRECTORY / "workspace.json"
    latest_path = root / CANONICAL_DIRECTORY / "latest.json"
    workspace = json.loads(workspace_path.read_text(encoding="utf-8"))
    events = workspace.get("events")
    if not isinstance(events, list):
        return 0
    kept = [
        event
        for event in events
        if not ((clock := _event_known_at(event)) is not None and clock > boundary)
    ]
    dropped = len(events) - len(kept)
    if dropped == 0:
        return 0

    workspace["events"] = kept
    # ``bundle_id`` is a CONTENT digest over the workspace, so a pruned bundle has
    # to be re-identified or the builder refuses the whole boundary with
    # "canonical workspace bundle identity mismatch".
    workspace["bundle_id"] = build_government_revenue._workspace_bundle_id(workspace)
    workspace_path.write_text(
        json.dumps(workspace, ensure_ascii=False), encoding="utf-8"
    )

    # ``latest`` embeds the same bundle and the builder compares the two
    # canonically, so they must be the SAME document rather than two documents
    # pruned alike.
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    latest["procurement_workspace"] = workspace
    latest_path.write_text(json.dumps(latest, ensure_ascii=False), encoding="utf-8")
    return dropped
