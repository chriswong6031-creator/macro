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
def canonical_frozen_at() -> str:
    """Return a run clock coherent with the canonical inputs currently on disk.

    Every ``*known_at`` in the copied boundary must be at or before the frozen
    clock, so the clock is the next whole hour after the newest of them, never
    below :data:`_FLOOR`.  Rounding up to the hour keeps the value strictly
    forward of every source clock -- the realistic ordering, since a run happens
    after its inputs are known -- and keeps it legible in failure output so the
    suites' relative offsets (-1s, +30m, +1h, +9h) stay unambiguous.

    The value is normalized exactly the way the writer normalizes it
    (``datetime.isoformat`` on a UTC instant), so tests may compare it verbatim
    against the ``generated_at`` the writer persists.
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
