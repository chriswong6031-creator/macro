"""Structural invariants for templates/committee.html.j2.

The synapse map went dark for 3 days (PR #1635 -> fixed here) because a
botched paste left (a) a duplicate panel with duplicate DOM ids, so
getElementById wired the wrong canvas, and (b) an orphan fragment of the old
renderer referencing identifiers (now/asofTs/PULSE_WINDOW_MS/COL_MUTED) that
no longer exist, throwing a ReferenceError on every animation frame that the
fetch-promise .catch silently swallowed.  These checks make both defect
classes fail CI instead of blanking the page.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / "templates" / "committee.html.j2"

# Identifiers from renderers that have been deleted; any reappearance means a
# stale fragment was pasted back in.
FORBIDDEN_IDENTIFIERS = ("PULSE_WINDOW_MS", "COL_MUTED", "asofTs")

# ids legitimately created only at runtime (insertAdjacentHTML etc.) may be
# added here; keep it empty until one actually exists.
DYNAMIC_ID_ALLOWLIST: frozenset[str] = frozenset()


def _src() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_no_duplicate_dom_ids():
    ids = re.findall(r'id="([a-zA-Z0-9_-]+)"', _src())
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    assert not dupes, (
        f"duplicate DOM ids in committee.html.j2: {dupes} — getElementById "
        "resolves only the first, so the later panel renders permanently blank"
    )


def test_no_forbidden_dead_identifiers():
    src = _src()
    hits = [w for w in FORBIDDEN_IDENTIFIERS if w in src]
    assert not hits, (
        f"dead renderer identifiers reintroduced: {hits} — these are undefined "
        "at runtime and throw ReferenceError inside drawFrame"
    )


def test_every_getelementbyid_target_exists():
    src = _src()
    targets = set(re.findall(r"getElementById\('([a-zA-Z0-9_-]+)'\)", src))
    missing = sorted(
        t for t in targets if f'id="{t}"' not in src and t not in DYNAMIC_ID_ALLOWLIST
    )
    assert not missing, (
        f"getElementById targets absent from the static DOM: {missing} — "
        "add to DYNAMIC_ID_ALLOWLIST only if the id is really created at runtime"
    )
