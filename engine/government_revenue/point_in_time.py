"""Strict, reusable point-in-time helpers for Government Revenue Foresight.

The government data rails are revised after the fact.  These helpers deliberately
require both a knowledge clock (when MastermindX could have known a record) and,
when requested, an effective clock (when the underlying government fact applied).
They fail closed for missing clocks so a historical replay cannot quietly consume
future revisions.
"""

from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Iterable, Sequence

import pandas as pd


KNOWLEDGE_CLOCK_COLUMNS: tuple[str, ...] = ("known_at", "first_seen_at", "_first_seen_at")
EFFECTIVE_CLOCK_COLUMNS: tuple[str, ...] = ("effective_at", "action_date", "base_obligation_date")
_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def timestamp(value: Any) -> pd.Timestamp | None:
    """Return a UTC timestamp, or ``None`` for an absent/unparseable value."""

    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        parsed = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(parsed):
        return None
    if parsed.tzinfo is None:
        return parsed.tz_localize("UTC")
    return parsed.tz_convert("UTC")


def iso_instant(value: Any) -> str | None:
    """Normalize a timestamp to a timezone-explicit ISO-8601 instant."""

    parsed = timestamp(value)
    return parsed.isoformat() if parsed is not None else None


def analysis_clock(as_of: Any) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Return ``(analysis_day, inclusive_utc_cutoff)`` for a PIT query.

    A date-only ``as_of`` is intentionally interpreted as the inclusive end of
    that UTC day (at nanosecond precision), matching the public workspace's
    daily replay convention.  A time-bearing timestamp is a precise cutoff and
    is never silently rounded up to the end of its day.
    """

    parsed = timestamp(as_of)
    if parsed is None:
        raise ValueError("as_of must be a parseable date or timestamp")
    day = parsed.normalize()
    is_date_only = (
        isinstance(as_of, date)
        and not isinstance(as_of, datetime)
    ) or (isinstance(as_of, str) and bool(_DATE_ONLY.fullmatch(as_of.strip())))
    if is_date_only:
        return day, day + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return day, parsed


def first_present_column(frame: pd.DataFrame, candidates: Sequence[str]) -> str | None:
    """Find the first candidate column carried by a frame."""

    return next((column for column in candidates if column in frame.columns), None)


def _series_timestamps(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True, errors="coerce")


def _coalesced_timestamps(frame: pd.DataFrame, candidates: Sequence[str]) -> pd.Series | None:
    """Coalesce clock aliases row-by-row, rather than trusting a blank column."""

    present = [column for column in candidates if column in frame.columns]
    if not present:
        return None
    result = _series_timestamps(frame[present[0]])
    for column in present[1:]:
        result = result.fillna(_series_timestamps(frame[column]))
    return result


def filter_dual_clock(
    frame: pd.DataFrame,
    *,
    knowledge_cutoff: Any,
    effective_cutoff: Any | None = None,
    knowledge_columns: Sequence[str] = KNOWLEDGE_CLOCK_COLUMNS,
    effective_columns: Sequence[str] = EFFECTIVE_CLOCK_COLUMNS,
) -> pd.DataFrame:
    """Return only records visible under strict knowledge/effective cutoffs.

    Missing knowledge timestamps are never treated as historical knowledge.  If
    ``effective_cutoff`` is supplied, records without an effective timestamp are
    likewise excluded.  The returned frame is always a copy and carries two
    normalized private columns used only by pure projectors:
    ``_pit_known_at`` and (when requested) ``_pit_effective_at``.
    """

    if frame.empty:
        return frame.copy()

    known_cutoff = timestamp(knowledge_cutoff)
    if known_cutoff is None:
        raise ValueError("knowledge_cutoff must be a parseable timestamp")

    known = _coalesced_timestamps(frame, knowledge_columns)
    if known is None:
        return frame.iloc[0:0].copy()

    visible = frame.copy()
    mask = known.notna() & (known <= known_cutoff)
    visible = visible.loc[mask].copy()
    visible["_pit_known_at"] = known.loc[mask]

    if effective_cutoff is None:
        return visible

    effective_cutoff_at = timestamp(effective_cutoff)
    if effective_cutoff_at is None:
        raise ValueError("effective_cutoff must be a parseable timestamp")

    effective = _coalesced_timestamps(visible, effective_columns)
    if effective is None:
        return visible.iloc[0:0].copy()

    effective_mask = effective.notna() & (effective <= effective_cutoff_at)
    visible = visible.loc[effective_mask].copy()
    visible["_pit_effective_at"] = effective.loc[effective_mask]
    return visible


def canonical_award_identity(row: pd.Series | dict[str, Any]) -> str | None:
    """Return an award identity without collapsing generated IDs onto PIIDs.

    USAspending can legitimately expose the same PIID under multiple generated
    award IDs.  Generated IDs are therefore preferred and PIID is only a
    last-resort identity.  This is intentionally not a broad vendor join key.
    """

    def value(name: str) -> str | None:
        raw = row.get(name) if hasattr(row, "get") else None
        if raw is None or pd.isna(raw):
            return None
        rendered = str(raw).strip()
        return rendered or None

    generated = value("generated_unique_award_id") or value("generated_award_id")
    if generated:
        return f"generated:{generated.removeprefix('generated:')}"
    award_key = value("award_key")
    if award_key:
        return award_key
    piid = value("award_id") or value("piid")
    return f"piid:{piid}" if piid else None


def with_award_identity(frame: pd.DataFrame, *, column: str = "_award_identity") -> pd.DataFrame:
    """Return a copy with the canonical award identity attached, dropping none."""

    result = frame.copy()
    result[column] = result.apply(canonical_award_identity, axis=1)
    return result


def visible_versions(
    frame: pd.DataFrame,
    *,
    key_columns: Iterable[str],
    knowledge_cutoff: Any,
    effective_cutoff: Any | None = None,
) -> pd.DataFrame:
    """Return the latest visible version per key under the strict dual clock."""

    visible = filter_dual_clock(
        frame,
        knowledge_cutoff=knowledge_cutoff,
        effective_cutoff=effective_cutoff,
    )
    keys = [column for column in key_columns if column in visible.columns]
    if visible.empty or not keys:
        return visible
    ordered = visible.sort_values([*keys, "_pit_known_at"], kind="mergesort")
    return ordered.groupby(keys, dropna=False, sort=False, as_index=False).tail(1).copy()


def is_true(value: Any) -> bool:
    """Parse an intentionally conservative explicit eligibility boolean."""

    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y"}
