"""Don't silently ship a thinner desk than the one already live.

The render express lane rebuilds a desk PAGE from the COMMITTED store
(``--no-refresh``, no network). That is safe for a template fix and wrong when
the machine running it lacks the collector progress that only a successful
nightly publishes: the rebake then quietly replaces a full board with a partial
one — no error, no warning, just fewer rows.

2026-07-25 is the case this exists for. A ``scope=sits`` render on a fresh Mac
runner rebuilt the Special Situations desk from main's event store and took the
live page from 1129 situations to 641, because ``collectors.special_situations``
enrich_* progress accumulates in the nightly runner's working copy and main's
snapshot was three days stale (``built=07-22``). Aging never removes a quarter
of a board in a day, so a cliff that deep is a machine-state mismatch, and the
honest response is to keep the last-known page and say so loudly.

Deliberately dependency-free (stdlib only): it is imported by page builders that
already pull the heavy stack, and by CI lanes that must not.
"""
from __future__ import annotations

import json
from pathlib import Path

# A no-refresh rebake that would drop MORE than this fraction of the shipped
# desk is treated as a machine-state mismatch, not as news.
THIN_FLOOR = 0.75

_ROW_MARKER = 'class="ss-row-card"'


def shipped_row_count(page: Path, payload: Path | None = None,
                      row_marker: str = _ROW_MARKER) -> int | None:
    """Rows the CURRENTLY COMMITTED artifacts carry, or None if unreadable.

    Counted from the shipped BYTES — the page's rows plus the tier payload's
    ``locked`` count — never from a ``data/`` snapshot, because that snapshot can
    be staler than the page it supposedly describes; that drift is the bug this
    guards, so it cannot also be the reference.
    """
    try:
        rows = page.read_text(encoding="utf-8").count(row_marker)
    except Exception:  # noqa: BLE001 — no shipped page yet: nothing to protect
        return None
    if not rows:
        return None
    locked = 0
    if payload is not None:
        try:
            locked = int(json.loads(payload.read_text(encoding="utf-8")).get("locked") or 0)
        except Exception:  # noqa: BLE001 — ungated/absent payload: the page is the whole desk
            locked = 0
    return rows + locked


def would_thin(new_total: int, prior: int | None, floor: float = THIN_FLOOR) -> bool:
    """True when writing ``new_total`` rows would gut the shipped desk.

    Growth and ordinary aging pass. A first build (``prior`` None/0) always
    passes — a guard must never block the thing it has no baseline for.
    """
    if not prior:
        return False
    return new_total < prior * floor
