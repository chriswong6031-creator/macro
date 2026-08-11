"""How a Prophet plan came to exist — and who is allowed to count it.

``origination_mode`` answers a question no other field on a plan answers: was this
row written by the nightly bake on the night its ``recorded_at`` names, or
reconstructed afterwards?  Almost every plan is the former, and says so by carrying
no value at all — the null IS "live", printed rather than defaulted to a word, the
same way ``selection_era`` is null on every pre-era plan.

The only non-null value today is the 2026-08-09 force-majeure outage replay
(``research/PROPHET_OUTAGE_BACKFILL_2026_08.md``; every minted row enumerated in
``data/prophet/backfill_disclosures.json``).

WHY THIS IS A SHARED MODULE AND NOT A ONE-LINE CHECK AT EACH SITE.  The predicate is
used by six unrelated consumers — the published record summary, three marketing
surfaces, the stage-shadow cohort that feeds live plan geometry, and the chat
gateway.  Written out six times it would drift six ways, and the failure mode is
silent: a surface that forgets the check does not error, it just quietly presents a
reconstructed pick as a live historical call.  One predicate, one place to audit.

FAIL-CLOSED ON THE UNKNOWN.  Anything that is not recognisably live is treated as
NOT live.  A future mode this module has never heard of is excluded from live
aggregates until someone teaches it otherwise — the opposite default would let a new
reconstruction lane leak into published win rates on the day it ships.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

#: The values that mean "a nightly bake originated this on its own recorded_at".
#: ``None``/absent is the overwhelmingly common one; the explicit strings exist so a
#: producer that wants to be loud can be, without changing any consumer.
LIVE_MODES = frozenset({"", "live", "nightly"})

#: Prefix of every reconstruction lane.  Matched as a prefix, not an equality, so a
#: second authorised window (which would need its own operator order and its own
#: disclosure row) is excluded by these consumers the moment it exists rather than
#: after someone remembers to update a list.
BACKFILL_PREFIX = "outage_backfill"


def origination_mode(record: Mapping[str, Any] | Any) -> str | None:
    """The record's mode, normalised, or None when it declares none."""
    if not isinstance(record, Mapping):
        return None
    raw = record.get("origination_mode")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    return text or None


def is_live_origination(record: Mapping[str, Any] | Any) -> bool:
    """True when this plan/ledger/index row was originated by a live nightly bake.

    The question every published rate, receipt and historical-call surface must ask
    before counting a row.
    """
    mode = origination_mode(record)
    return mode is None or mode in LIVE_MODES


def is_backfilled(record: Mapping[str, Any] | Any) -> bool:
    """True when this row was reconstructed by a disclosed backfill lane."""
    mode = origination_mode(record)
    return bool(mode) and mode.startswith(BACKFILL_PREFIX)


def live_only(records: "list[Any] | tuple[Any, ...] | None") -> list[Any]:
    """Drop every non-live row.  The one-liner the marketing surfaces call."""
    return [row for row in (records or []) if is_live_origination(row)]


def split_by_origination(
    records: "list[Any] | tuple[Any, ...] | None",
) -> tuple[list[Any], list[Any]]:
    """``(live, reconstructed)`` — for surfaces that report both rather than one."""
    live: list[Any] = []
    other: list[Any] = []
    for row in records or []:
        (live if is_live_origination(row) else other).append(row)
    return live, other
