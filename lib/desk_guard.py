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


# ── staleness: a desk that stopped ADVANCING is the other silent degradation ───
#
# ``would_thin`` catches a desk that lost rows. This catches the desk that keeps
# every row and stops moving — the failure that hid for 12 days in
# site/flowdata/desk.json: its A-share legs froze at 2026-07-24 while still
# declaring ``cadence: "daily"``, because the gated Tushare plane went dark
# upstream. Nothing was red. The page rendered, the JSON was rewritten nightly
# with a fresh mtime, and the one consumer that DOES check freshness
# (engine/cn_theme_tape, 7-day budget) silently dropped its flow chips.
#
# TWO gates, because either alone is blind to the other's case:
#
#   * RELATIVE — a live leg that falls behind the payload's freshest live leg.
#     Market holidays freeze every leg together, so the gap stays ~0 and the
#     holiday cannot fire it. This is the gate that catches a PARTIAL freeze
#     (one dead source among healthy siblings) — the actual 2026-07-24 bug.
#   * WALL-CLOCK — the freshest leg itself measured against the build date. A
#     purely self-relative gate agrees with itself when EVERYTHING freezes at
#     once, so the relative gate needs this backstop to see a total outage.

#: A live leg may trail the freshest live leg by this many days before it is
#: called stale. Matches ChinaTushareAdapter.stale_after_days (4) — the repo's
#: own weekend/holiday-tolerant budget for this plane — and fires three days
#: before cn_theme_tape's 7-day gate starts dropping chips, so the warning
#: always precedes the silent breakage rather than trailing it.
LEG_LAG_MAX_DAYS = 4

#: The freshest live leg may trail the build date by this many days before the
#: whole desk is called frozen. Sized to clear a mainland Golden Week / Spring
#: Festival closure (~8 calendar days including flanking weekends) so a planned
#: market holiday never cries wolf.
DESK_MAX_AGE_DAYS = 10


def _as_date(value):
    """Parse an ISO ``YYYY-MM-DD`` stamp, or None when it is not one."""
    from datetime import date, datetime

    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def stale_legs(legs: dict, today,
               lag_max_days: int = LEG_LAG_MAX_DAYS,
               age_max_days: int = DESK_MAX_AGE_DAYS) -> list[dict]:
    """Legs of a desk payload that have stopped advancing.

    ``legs`` maps a display name to a leg dict carrying an ``as_of`` stamp.
    Returns one finding per problem, each ``{leg, as_of, lag_days, age_days,
    reason}`` with ``reason`` in:

      ``lagging``      — trails the freshest live leg by more than ``lag_max_days``
      ``desk_frozen``  — the freshest live leg itself is older than ``age_max_days``
      ``unreadable``   — carries an ``as_of`` that will not parse

    DELIBERATELY DISCONTINUED legs are skipped: a leg marked ``live: False`` or
    carrying ``frozen_since`` is frozen on purpose (the northbound aggregate,
    ended 2024-08-16 under the Stock Connect home-market rule). Warning on those
    nightly and forever would train every reader to ignore this alarm, which
    costs more than the alarm buys.

    A leg with no ``as_of`` key is skipped rather than reported — not every leg
    stamps one, and the caller chooses what to pass. An ``as_of`` that is
    PRESENT and unparseable is reported: a guard that goes quiet when the field
    it reads changes shape is a guard that stops guarding.
    """
    today = _as_date(today)
    checked: dict[str, "object"] = {}
    findings: list[dict] = []

    for name, leg in (legs or {}).items():
        if not isinstance(leg, dict) or "as_of" not in leg:
            continue
        if leg.get("live") is False or leg.get("frozen_since"):
            continue
        stamped = _as_date(leg.get("as_of"))
        if stamped is None:
            findings.append({"leg": name, "as_of": leg.get("as_of"),
                             "lag_days": None, "age_days": None,
                             "reason": "unreadable"})
            continue
        checked[name] = stamped

    if not checked:
        return findings

    newest_name = max(checked, key=lambda k: checked[k])
    newest = checked[newest_name]

    for name, stamped in sorted(checked.items()):
        lag = (newest - stamped).days
        age = (today - stamped).days if today else None
        if lag > lag_max_days:
            findings.append({"leg": name, "as_of": str(stamped), "lag_days": lag,
                             "age_days": age, "reason": "lagging"})

    if today is not None and (today - newest).days > age_max_days:
        findings.append({"leg": newest_name, "as_of": str(newest), "lag_days": 0,
                         "age_days": (today - newest).days, "reason": "desk_frozen"})

    return findings
