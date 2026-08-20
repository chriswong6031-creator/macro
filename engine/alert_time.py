"""Alert Command Center time contract — three clocks, one board day.

WHY THIS EXISTS
---------------
The Alert Center is a triage layer: its ranking, its "today / 1d ago" wording, its
recency points and its catalyst countdown all decide what a PM looks at FIRST.  Until
this module existed those all derived from ``datetime.now(timezone.utc).date()`` and
from whatever ``ts`` an engine happened to serialize — which let two different clocks
collapse into one and made a build-time stamp masquerade as an event time.  The two
measured regressions:

  * ``engine.subsector_rotation_alerts`` stamped its events with the rotation payload's
    ``generated_utc`` (the moment our builder ran) instead of its ``asof`` (the settled
    session the read is about), so conclusions drawn from the Aug-19 tape displayed as
    "2026-08-20 · today";
  * the board's own "today" was UTC midnight, so between 00:00Z and 05:00Z (a window the
    nightly pipeline runs straight through) a US cross-asset desk rolled its day over
    while New York was still in the previous afternoon.

THREE CLOCKS, NEVER INTERCHANGEABLE
-----------------------------------
  1. ``event_date`` / ``event_ts``  — when the thing actually happened.
  2. ``source_asof``                — the market/data observation it was derived from.
  3. ``recorded_at``                — when Mastermind processed / serialized it.

``recorded_at`` is never promoted to ``event_*`` merely because it is easier to obtain.

BOARD DAY
---------
The Alert Center is a US cross-asset desk, so its user-facing "today" / "yesterday" and
its catalyst countdown project onto ``America/New_York`` — NOT UTC, and NOT the host's
naive local clock.  Storage stays source-native: date/session events keep their own event
date and absolute events keep their offset-aware instant; only the *projection* is ET.

PRECISION
---------
  ``date``       a market-session event ("rotation observed from the 2026-08-19 close").
                 It has no clock time and never gains a fabricated one — an Aug-19 session
                 event is Aug-19 on the board, not ``2026-08-19T00:00 ET``.
  ``timestamp``  a real instant (crypto / intraday).  It stays offset-aware internally and
                 projects to a board day for labelling: ``2026-08-20T00:30Z`` is still that
                 instant, and it is an Aug-19 event for this desk.
  ``unknown``    no usable event time.  Earns NO recency credit and is never called "today";
                 the caller discloses the unknown date rather than inventing one.

NOTE on legacy naive stamps: every jsonl alert engine in this repo serializes a session
date as ``YYYY-MM-DDT00:00:00`` (no offset).  That midnight is a serialization artifact of
a date, not a claim about a clock time, so it is read back as ``date`` precision — the same
reading ``engine.alert_triage`` already applied via its ``ts.hour == 0 and ts.minute == 0``
heuristic.  A producer that genuinely means midnight-as-an-instant says so explicitly with
``date_precision`` / an offset-aware ``event_ts``.

Deterministic and injectable: every entry point takes ``now`` so nothing here is tested
against a wall clock.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

# The board's user-facing day.  This is a US cross-asset desk.
BOARD_TZ_NAME = "America/New_York"
BOARD_TZ = ZoneInfo(BOARD_TZ_NAME)

PRECISION_DATE = "date"
PRECISION_TIMESTAMP = "timestamp"
PRECISION_UNKNOWN = "unknown"

# The normalized time block every consumer reads.  Always the SAME key set (None where a
# clock genuinely does not exist) so a template can never trip Jinja's missing-key
# Undefined, and so "absent" is always distinguishable from "not applicable".
_EMPTY = {
    "event_date": None,
    "event_ts": None,
    "source_asof": None,
    "recorded_at": None,
    "board_date": None,
    "date_precision": PRECISION_UNKNOWN,
}


def _aware_utc(now: datetime | None) -> datetime:
    """Coerce an injected ``now`` to an aware UTC instant (naive is read as UTC)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return now.astimezone(timezone.utc)


def board_now(now: datetime | None = None) -> datetime:
    """``now`` as a wall clock in the board's timezone."""
    return _aware_utc(now).astimezone(BOARD_TZ)


def board_date(now: datetime | None = None) -> date:
    """The board's TODAY.

    At ``2026-08-20T00:30:00Z`` New York is still ``2026-08-19 20:30``, so the board day
    is 2026-08-19 — the whole point of not using UTC midnight on a US desk.
    """
    return board_now(now).date()


def parse_instant(value) -> datetime | None:
    """Parse an absolute, offset-aware instant.  Returns None if ``value`` is not one.

    A naive string is NOT an instant here — the caller decides what a missing offset means
    (see ``normalize_event``).  This function never invents a timezone.
    """
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else None
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00").replace("z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def parse_date(value) -> date | None:
    """Parse a source-native event/session DATE.  Never fabricates a clock time.

    Accepts ``date`` / ``datetime`` objects, ``"YYYY-MM-DD"``, and the
    ``"YYYY-MM-DDT..."`` serializations the jsonl engines emit (the date part is taken
    verbatim — no timezone shift, because shifting a session date has no meaning).
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value.strip()) < 10:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def _is_bare_midnight(value) -> bool:
    """True for the ``YYYY-MM-DDT00:00:00`` (no offset) session-date serialization."""
    if isinstance(value, datetime):
        return (value.tzinfo is None and value.hour == 0 and value.minute == 0
                and value.second == 0)
    if not isinstance(value, str):
        return False
    raw = value.strip()
    if len(raw) == 10:          # bare "YYYY-MM-DD"
        return True
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return False
    return (dt.tzinfo is None and dt.hour == 0 and dt.minute == 0 and dt.second == 0)


def to_board_date(event_date: date | None, event_ts: datetime | None) -> date | None:
    """Project an event onto the board day.

    A date-precision event keeps its source-native date (a session date is already a board
    day; re-projecting it would invent a clock time it never had).  An absolute instant is
    converted into the board timezone — ``2026-08-20T00:30Z`` → ``2026-08-19``.
    """
    if event_date is not None:
        return event_date
    if event_ts is not None:
        return event_ts.astimezone(BOARD_TZ).date()
    return None


def normalize_event(ev: dict, *, assume_naive_utc: bool = True) -> dict:
    """Derive the normalized time block for one raw alert event.

    Field precedence — most explicit first, so a producer that states its clocks wins over
    the legacy ``ts``:

      ``event_date``  an explicit source-native session date            → ``date``
      ``event_ts``    an explicit offset-aware instant                  → ``timestamp``
      ``source_asof`` the observation the read was derived from; used as the event date
                      when the producer supplies no ``event_date``      → ``date``
      ``ts``          legacy.  A bare date or a bare ``T00:00:00`` is a serialized session
                      date (``date``); an offset-aware value is an instant (``timestamp``);
                      a naive value carrying a real clock time is a legacy build stamp —
                      read as UTC when ``assume_naive_utc`` (disclosed via
                      ``tz_source='assumed_utc'``), otherwise ``unknown``.

    ``recorded_at`` is read from ``recorded_at`` / ``generated_utc`` and is NEVER used as an
    event time.  Returns the always-same key set of ``_EMPTY`` plus ``tz_source`` when a
    naive clock had to be interpreted.
    """
    out = dict(_EMPTY)

    asof = parse_date(ev.get("source_asof") or ev.get("asof"))
    if asof is not None:
        out["source_asof"] = asof.isoformat()

    rec = ev.get("recorded_at") or ev.get("generated_utc")
    rec_ts = parse_instant(rec)
    if rec_ts is not None:
        out["recorded_at"] = rec_ts.isoformat()
    elif isinstance(rec, str) and rec.strip():
        out["recorded_at"] = rec.strip()      # keep the source string verbatim, unparsed

    # explicit precision override wins over shape-sniffing
    declared = ev.get("date_precision")

    if declared == PRECISION_UNKNOWN:
        # The producer KNOWS it has no event time.  Its ``ts`` (if any) is a record clock
        # kept only so the append-only store stays sortable, and must never be read as an
        # event time — so we stop here with board_date None.
        return out

    ev_date = parse_date(ev.get("event_date"))
    ev_ts = parse_instant(ev.get("event_ts"))

    if ev_date is not None and declared != PRECISION_TIMESTAMP:
        out["event_date"] = ev_date.isoformat()
        out["date_precision"] = PRECISION_DATE
    elif ev_ts is not None:
        out["event_ts"] = ev_ts.isoformat()
        out["date_precision"] = PRECISION_TIMESTAMP
    elif asof is not None and "ts" not in ev:
        out["event_date"] = asof.isoformat()
        out["date_precision"] = PRECISION_DATE
    else:
        legacy = ev.get("ts")
        inst = parse_instant(legacy)
        if declared == PRECISION_DATE:
            d = parse_date(legacy)
            if d is not None:
                out["event_date"] = d.isoformat()
                out["date_precision"] = PRECISION_DATE
        elif inst is not None:
            # offset-aware: KEEP the offset.  The old code ran tz_localize(None) here,
            # which destroyed the provenance this whole module exists to preserve.
            out["event_ts"] = inst.isoformat()
            out["date_precision"] = PRECISION_TIMESTAMP
        elif _is_bare_midnight(legacy):
            d = parse_date(legacy)
            if d is not None:
                out["event_date"] = d.isoformat()
                out["date_precision"] = PRECISION_DATE
        elif legacy is not None and assume_naive_utc:
            # A naive stamp with a real clock time — a legacy build clock.  We read it as
            # UTC and SAY SO rather than silently treating it as a board-local wall time.
            try:
                naive = datetime.fromisoformat(str(legacy).strip())
            except ValueError:
                naive = None
            if naive is not None:
                out["event_ts"] = naive.replace(tzinfo=timezone.utc).isoformat()
                out["date_precision"] = PRECISION_TIMESTAMP
                out["tz_source"] = "assumed_utc"

    bd = to_board_date(parse_date(out["event_date"]), parse_instant(out["event_ts"]))
    out["board_date"] = bd.isoformat() if bd is not None else None
    return out


def age_days(block: dict, today: date) -> int | None:
    """Whole board-days between an event's board day and the board's today.

    None when the event time is unknown — the caller must then withhold the recency bonus
    rather than defaulting the alert to "fresh".  Clamped at 0 so a same-day event never
    reads negative.
    """
    bd = parse_date(block.get("board_date"))
    if bd is None:
        return None
    return max(0, (today - bd).days)


def is_future(block: dict, today: date) -> bool:
    """True when the event claims a board day AFTER today — a scheduled catalyst leaking
    into the fired-alert feed, or a clock defect.  Such rows are quarantined, not ranked."""
    bd = parse_date(block.get("board_date"))
    return bd is not None and bd > today
