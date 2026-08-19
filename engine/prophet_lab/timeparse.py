"""engine/prophet_lab/timeparse.py — the ONE instant-comparison helper for the
observation-class honesty path (LAB-0 §4).

TEMPORAL CORRECTNESS AMENDMENT (day-2 reconciliation, 2026-08-19)
-------------------------------------------------------------------
Every comparison in ``observation.classify_observation`` and
``sources.baseline_coverage_verified`` (plus the timestamp-ordering helpers
in ``sources.py`` that feed them: ``extract_events``'s "earliest per event",
``earliest_pass_ts``, ``latest_envelope``) used to compare RAW STRINGS with
``<``/``>``/``min()``/``max()``. That is only correct when every timestamp in
the comparison shares the exact same UTC-offset notation. It is WRONG in
general: ``"2026-08-19T09:00:00-04:00"`` (13:00 UTC) sorts lexicographically
BEFORE ``"2026-08-19T10:00:00Z"`` (10:00 UTC) — '0' < '1' as characters — even
though the first string names the LATER instant. A spool envelope, a Radar
producer, or an operator-edited baseline marker that ever emits a non-'Z'
offset (a legal ISO-8601 form nothing here forbids) could silently flip a
``retrospective_seed``/``live_forward`` classification, or falsely "verify"
baseline coverage that does not actually reach back far enough — exactly the
failure mode LAB-0 §4's fail-honest design exists to prevent.

:func:`parse_instant` is the single place this package parses a timestamp for
COMPARISON purposes in that honesty path; every caller compares the returned
``datetime`` objects (tz-aware, normalized to UTC) rather than the original
strings.

ROUND 2 (2026-08-19): three more of the same bug class, all still inside the
honesty/EVIDENCE path (never display): ``boards._live_forward_lead_anchor``
(picking which multi-expert-card event a measured lead is attributed to —
was ``candidates.sort(key=lambda pair: pair[0])`` over raw strings),
``observation.measured_lead_days``'s LAB-side date extraction (was
``str(first_observed_at)[:10]``, which reads the OFFSET-LOCAL calendar date
and silently gets the wrong day whenever the offset crosses midnight UTC),
and ``sources.earliest_pass_ts`` (now wired through
:func:`earliest_instant_string` below instead of re-implementing the same
scan). All three now go through this module.

Scope note — the ONE deliberate exemption, and it does not grow: this module
is NOT used by ``engine.prophet_lab.boards._parse_sort_ts`` (the row DISPLAY
ORDER helper). Sorting and classifying/measuring have different,
legitimately different failure semantics — see ``parse_instant``'s docstring
for why a naive timestamp is REJECTED here but boards.py's own sort key
treats one as UTC. Reusing this parser there would silently change which
rows sort last for a naive ``sort_ts`` (e.g. a bare ``YYYY-MM-DD`` Prophet
plan date), which is a board DISPLAY semantic this amendment is explicitly
forbidden from touching. Every OTHER raw timestamp comparison in the
observation/coverage/lead-measurement path is EVIDENCE-tier, not display,
and belongs in this module, not on the exemption list — that list names
exactly one function (``_parse_sort_ts``) and stays that length.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable


def parse_instant(ts: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp to a tz-AWARE UTC ``datetime``, or ``None``.

    Accepts a ``Z``/``z`` suffix (converted to ``+00:00``) or an explicit
    numeric UTC offset. Returns ``None`` — never raises — for: an empty/falsy
    input, a string that does not parse as ISO-8601 at all, AND a string that
    parses but carries NO offset (a naive timestamp).

    FAIL CLOSED ON NAIVE, DELIBERATELY (day-2 mandate: "treat-as-UTC only if
    you can defend it, else reject to seed"). This package's own producers are
    documented to always emit an explicit UTC offset: the Radar spool
    envelope's ``pass_ts`` (``engine.entry_radar.live_ledger.build_event_payload``
    — every committed fixture and the real producer both use a ``Z`` suffix)
    and the observation-baseline marker's ``baseline_started_at``/
    ``continuous_through`` (``sources.read_observation_baseline``'s own
    documented shape: ``"<ISO-8601 timestamp>"``, i.e. a full instant, not a
    bare date). A naive string reaching this parser therefore signals an
    UPSTREAM CONTRACT VIOLATION — a hand-edited baseline marker, a corrupted
    spool file — not a legitimate ambiguity this module should resolve by
    guessing UTC. This package never originates a signal (LAB-0 §1); silently
    promoting a naive timestamp to UTC risks manufacturing a ``live_forward``
    classification (and a measured Lab->Prophet lead) from an instant whose
    zone was never actually known. Returning ``None`` here routes straight
    into each caller's existing "could not parse" branch, which already
    means "fail toward retrospective_seed" — the same honest, recoverable
    failure a wholly garbled string already produced before this amendment.
    """
    if not ts:
        return None
    text = str(ts).strip()
    if not text:
        return None
    normalized = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None  # naive -> reject, never guess (see docstring DEFEND note)
    return parsed.astimezone(timezone.utc)


def earliest_instant_string(timestamps: Iterable[str | None]) -> str | None:
    """The ORIGINAL string whose parsed instant is earliest, or ``None``.

    Compares by parsed INSTANT, not by string value; an unparseable or naive
    entry is skipped entirely (it can never win "earliest") rather than
    corrupting the comparison. Ties keep the FIRST string encountered whose
    instant matches the running minimum.
    """
    best_raw: str | None = None
    best_instant: datetime | None = None
    for raw in timestamps:
        parsed = parse_instant(raw)
        if parsed is None:
            continue
        if best_instant is None or parsed < best_instant:
            best_instant = parsed
            best_raw = raw
    return best_raw


__all__ = ["parse_instant", "earliest_instant_string"]
