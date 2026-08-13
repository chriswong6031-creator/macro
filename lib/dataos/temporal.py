"""Temporal model — the mechanism that actually prevents leakage (Data OS §D3).

WHY THIS FILE EXISTS.  The house already owns point-in-time discipline in at least
six independent, locally-correct places — Calcbench 5-clock bitemporal fundamentals,
FRED/ALFRED vintage as-of reads (``collectors/fred.py::as_of_series``), the CN
TuShare generation-atomic PIT universe, ``basket_membership_pit`` append-only
snapshots, ``ColumnContract`` per-column freshness, and ``engine/canon.py``'s golden
concept canon — which share **no vocabulary, no registry and no enforcement**.
Correctness is therefore per-module and globally unverifiable, and the failure mode
when a caller reaches a store that has none of it is not an exception: it is a
silent latest-vintage return.  A backtest reads today's revised CPI into 2019 and
scores beautifully.  Nothing goes red.

THE PIT LAW::

    known_at := coalesce(published_at, ingested_at)     -- the dataset declares which it has

A research or backtest read must go through an ``as_of(t)`` reader that filters
``known_at <= t``.  **A dataset whose profile lacks the clock needed to answer
known_at is FORBIDDEN from point-in-time reads and must RAISE** — never silently
return the latest value.  That is :func:`assert_pit_readable`, and it is the whole
point of the module: fail closed, loudly, at the boundary.

SEVEN NAMED TIMES, NOT SEVEN MANDATORY COLUMNS.  §D3's seven are one interval LABEL
(``period_start``/``period_end`` — two columns, one concept: the interval the
observation describes, not a clock) plus six instants (``event_at``,
``effective_at``, ``published_at``, ``ingested_at``, ``computed_at``, ``served_at``).
No dataset carries all of them.  Each dataset declares a :class:`TemporalProfile`
from a closed vocabulary and the profile decides which are mandatory — which is what
keeps this from becoming the thing §D11 forbids (full bitemporal modelling of
datasets that never revise; bars never revise, and forcing them into a bitemporal
table is pure cost).

REPRODUCE != REPLAY.  Adopting the Calcbench ruling verbatim
(``research/CALCBENCH_PARITY_WAVE_3A_BITEMPORAL_QUERY_BUILD_DOCKET_2026-08-02.md``):
"running a 2022 filing through a rule written in 2026 is a current-rule
recomputation, not a 2022 system replay".  Two distinct guarantees:

* **Recomputable** — same inputs + same code version -> same output.  Required of L3
  (``DERIVED``).
* **Replayable** — what the system ACTUALLY emitted at time t, retrieved from an
  append-only served-artifact log.  Required of L4 (``INTELLIGENCE``) only; the house
  already has the primitive in the Prophet forward logs.

This is why ``DERIVED`` is deliberately NOT point-in-time readable here: its
mandatory clocks are ``computed_at`` + code version + input cutoffs, which answer
"can I recompute this" and cannot answer "what did we know at t".  Letting a DERIVED
table serve an as-of read is precisely the current-rule recomputation the ruling
names.  ``INTELLIGENCE`` answers it with ``served_at``, because that IS the replay
clock.

NAIVE DATETIMES RAISE.  :func:`utc` refuses a tz-naive datetime rather than assuming
UTC or local time.  Guessing is the bug being eliminated: the repo's CI runs UTC
while the operator's evening is the next day there, so a naive stamp silently means
two different instants depending on where it was produced.

STDLIB ONLY.  No pandas at import time; :func:`as_of_filter` is pure
list-of-dicts in / list-of-dicts out so it runs in the thin CI lanes.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from enum import Enum, StrEnum

__all__ = [
    "TemporalError",
    "PointInTimeError",
    "Clock",
    "INSTANT_CLOCKS",
    "INTERVAL_CLOCKS",
    "TemporalProfile",
    "KNOWN_AT_CLOCKS",
    "utc",
    "known_at",
    "assert_pit_readable",
    "pit_refusal_reason",
    "as_of_filter",
]


class TemporalError(ValueError):
    """A time that cannot be interpreted without guessing."""


class PointInTimeError(TemporalError):
    """A point-in-time read that cannot be answered honestly.

    Raised instead of returning the latest value.  The message always carries the
    REASON, because the caller's next move (declare a clock, change the profile, stop
    doing a PIT read against this dataset) depends entirely on which of them it is.
    """


class Clock(StrEnum):
    """The named times of §D3.  ``StrEnum`` so a value is also the column name."""

    PERIOD_START = "period_start"
    PERIOD_END = "period_end"
    EVENT_AT = "event_at"
    EFFECTIVE_AT = "effective_at"
    PUBLISHED_AT = "published_at"
    INGESTED_AT = "ingested_at"
    COMPUTED_AT = "computed_at"
    SERVED_AT = "served_at"


#: The interval LABEL — what the observation describes.  Not a clock; a bar's
#: period_end is not a moment anyone learned anything.
INTERVAL_CLOCKS: frozenset[Clock] = frozenset({Clock.PERIOD_START, Clock.PERIOD_END})

#: The six real instants.
INSTANT_CLOCKS: frozenset[Clock] = frozenset(set(Clock) - INTERVAL_CLOCKS)


class TemporalProfile(Enum):
    """Closed vocabulary of temporal shapes (§D3).

    The profile — not the table, not the caller — decides which clocks are mandatory
    and whether a point-in-time read is lawful at all.
    """

    BARS = "BARS"
    REVISABLE_RELEASE = "REVISABLE_RELEASE"
    SNAPSHOT_SERIES = "SNAPSHOT_SERIES"
    EVENT = "EVENT"
    DERIVED = "DERIVED"
    INTELLIGENCE = "INTELLIGENCE"

    @property
    def required_clocks(self) -> frozenset[Clock]:
        """Clocks a dataset on this profile MUST carry."""
        return _REQUIRED_CLOCKS[self]

    @property
    def required_fields(self) -> frozenset[str]:
        """Non-clock columns the profile also mandates (revision chain, versions).

        ``revision_seq``/``code_version``/``data_cutoff_at``/``expires_at`` are
        obligations of the same table but are not times on the §D3 clock list, so
        they live here rather than being smuggled into :class:`Clock`.
        """
        return _REQUIRED_FIELDS[self]

    @property
    def pit_readable(self) -> bool:
        """Can an ``as_of(t)`` read be answered from this profile's mandatory clocks?"""
        return bool(KNOWN_AT_CLOCKS[self])


_REQUIRED_CLOCKS: dict[TemporalProfile, frozenset[Clock]] = {
    TemporalProfile.BARS: frozenset(
        {Clock.PERIOD_START, Clock.PERIOD_END, Clock.INGESTED_AT}
    ),
    TemporalProfile.REVISABLE_RELEASE: frozenset(
        {Clock.PERIOD_END, Clock.PUBLISHED_AT, Clock.INGESTED_AT}
    ),
    TemporalProfile.SNAPSHOT_SERIES: frozenset(
        {Clock.EFFECTIVE_AT, Clock.INGESTED_AT}
    ),
    TemporalProfile.EVENT: frozenset(
        {Clock.EVENT_AT, Clock.PUBLISHED_AT, Clock.INGESTED_AT}
    ),
    TemporalProfile.DERIVED: frozenset({Clock.COMPUTED_AT}),
    TemporalProfile.INTELLIGENCE: frozenset({Clock.COMPUTED_AT, Clock.SERVED_AT}),
}

_REQUIRED_FIELDS: dict[TemporalProfile, frozenset[str]] = {
    TemporalProfile.BARS: frozenset(),
    TemporalProfile.REVISABLE_RELEASE: frozenset({"revision_seq"}),
    TemporalProfile.SNAPSHOT_SERIES: frozenset(),
    TemporalProfile.EVENT: frozenset(),
    TemporalProfile.DERIVED: frozenset({"code_version", "input_cutoffs"}),
    TemporalProfile.INTELLIGENCE: frozenset(
        {"code_version", "input_cutoffs", "data_cutoff_at", "expires_at"}
    ),
}

#: Ordered coalesce list per profile — the literal ``coalesce(published_at,
#: ingested_at)`` of the PIT law, plus the one deliberate variation: INTELLIGENCE
#: answers with ``served_at``, its replay clock.  An EMPTY tuple means the profile
#: cannot answer ``known_at`` at all, and every PIT read against it must RAISE.
KNOWN_AT_CLOCKS: dict[TemporalProfile, tuple[Clock, ...]] = {
    TemporalProfile.BARS: (Clock.PUBLISHED_AT, Clock.INGESTED_AT),
    TemporalProfile.REVISABLE_RELEASE: (Clock.PUBLISHED_AT, Clock.INGESTED_AT),
    TemporalProfile.SNAPSHOT_SERIES: (Clock.PUBLISHED_AT, Clock.INGESTED_AT),
    TemporalProfile.EVENT: (Clock.PUBLISHED_AT, Clock.INGESTED_AT),
    TemporalProfile.DERIVED: (),
    TemporalProfile.INTELLIGENCE: (Clock.SERVED_AT,),
}


def utc(value: datetime | str) -> datetime:
    """Normalize a datetime or ISO string to tz-aware UTC.  RAISES on naive input.

    A tz-naive datetime is not "probably UTC": CI runs UTC while this repo's operator
    works US-eastern evenings, so the same naive stamp means two different instants
    depending on which machine produced it.  Attaching a timezone here would make
    that ambiguity permanent and invisible, so it is refused instead — the fix is at
    the producer, and this is the only place that can force it.
    """
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise TemporalError("empty string is not a timestamp")
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as exc:
            raise TemporalError(f"{value!r} is not an ISO-8601 timestamp") from exc
        value = parsed
    if isinstance(value, datetime):
        if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
            raise TemporalError(
                f"naive datetime {value!r} — refusing to guess a timezone. Stamp it at the "
                "producer (datetime.now(timezone.utc)) or pass an offset-bearing ISO string."
            )
        return value.astimezone(timezone.utc)
    if isinstance(value, date):
        raise TemporalError(
            f"{value!r} is a date, not an instant — a date has no timezone, so promoting "
            "it to a timestamp is the same guess this function refuses"
        )
    raise TemporalError(f"cannot interpret {type(value).__name__} as a timestamp")


def pit_refusal_reason(profile: TemporalProfile) -> str | None:
    """Why *profile* cannot answer ``known_at``, or ``None`` when it can."""
    if KNOWN_AT_CLOCKS.get(profile):
        return None
    if profile is TemporalProfile.DERIVED:
        return (
            "DERIVED carries computed_at + code_version + input cutoffs, which answer "
            "'can I recompute this' (RECOMPUTABLE) and cannot answer 'what did we know "
            "at t' (REPLAYABLE). Serving an as-of read from it is the current-rule "
            "recomputation the Calcbench reproduce!=replay ruling names. Promote the "
            "dataset to INTELLIGENCE (which carries served_at) or read its inputs as-of."
        )
    return (
        f"{getattr(profile, 'name', profile)!r} declares no published_at/ingested_at/"
        "served_at clock, so known_at is unanswerable"
    )


def assert_pit_readable(profile: TemporalProfile) -> None:
    """Fail CLOSED before a point-in-time read (§D3).

    Raises :class:`PointInTimeError` — carrying the reason — when the profile cannot
    answer ``known_at``.  Never returns a degraded answer, because the degraded answer
    (the latest vintage) looks exactly like the right one.
    """
    reason = pit_refusal_reason(profile)
    if reason is not None:
        raise PointInTimeError(
            f"point-in-time read refused for temporal_profile={getattr(profile, 'name', profile)}: "
            f"{reason}"
        )


def known_at(row: Mapping[str, object], profile: TemporalProfile) -> datetime:
    """``coalesce(published_at, ingested_at)`` for one row, as tz-aware UTC.

    Raises :class:`PointInTimeError` when the profile cannot answer known_at at all,
    or when this particular row carries none of the clocks its profile promised.  A
    row that cannot say when it became knowable is not silently included (leakage) or
    silently dropped (a hole nobody can see) — it is an error at the boundary.
    """
    assert_pit_readable(profile)
    for clock in KNOWN_AT_CLOCKS[profile]:
        value = row.get(clock.value) if isinstance(row, Mapping) else None
        if value is not None:
            return utc(value)  # type: ignore[arg-type]
    wanted = " or ".join(c.value for c in KNOWN_AT_CLOCKS[profile])
    have = ", ".join(sorted(row.keys())) if isinstance(row, Mapping) else repr(row)
    raise PointInTimeError(
        f"row carries no {wanted} so known_at is unanswerable (columns present: {have or 'none'})"
    )


def as_of_filter(
    rows: Iterable[Mapping[str, object]],
    t: datetime | str,
    profile: TemporalProfile,
) -> list[dict]:
    """The ``as_of(t)`` reader: keep rows with ``known_at <= t``.  Pure.

    List-of-dicts in, list-of-dicts out, input order preserved, no pandas — so it is
    callable from a collector, a thin CI lane, or a notebook without dragging a
    dataframe stack in.  Refuses non-PIT-readable profiles before touching a row.
    """
    assert_pit_readable(profile)
    cutoff = utc(t)
    return [dict(row) for row in rows if known_at(row, profile) <= cutoff]
