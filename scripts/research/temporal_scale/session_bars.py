"""Civil-session aggregation of locally attested lower-grain OHLCV bars."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import math
from numbers import Integral, Real
import re
from types import MappingProxyType
from typing import Iterable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import pandas as pd

from scripts.research.temporal_scale.contracts import BAR_RECEIPT_SCHEMA, BarReceipt, strict_json_dumps


class SessionBarsError(ValueError):
    """Civil grammar or observed lower-grain evidence is unsafe."""


_TIME = re.compile(r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
_REQUIRED = ("open_ms", "close_ms", "open", "high", "low", "close", "volume")
_CONFIRMED = ("confirmed", "is_confirmed", "TG_is_confirmed")


@dataclass(frozen=True, slots=True)
class SessionInterval:
    start_local: str
    end_local: str
    label: str

    def __post_init__(self) -> None:
        if (not all(isinstance(v, str) and v for v in (self.start_local, self.end_local, self.label))
                or not _TIME.fullmatch(self.start_local) or not _TIME.fullmatch(self.end_local)):
            raise SessionBarsError("interval endpoints must be HH:MM and label nonempty")


@dataclass(frozen=True, slots=True)
class BarGridSpec:
    grid_id: str
    timezone: str
    nominal_minutes: int
    phase_minutes: int
    intervals: tuple[SessionInterval, ...]
    include_empty: bool
    close_delay_minutes: int
    date_overrides: Mapping[str, tuple[SessionInterval, ...]] | None = None

    def __post_init__(self) -> None:
        raw_overrides = {} if self.date_overrides is None else self.date_overrides
        if not isinstance(raw_overrides, Mapping):
            raise SessionBarsError("date_overrides must be a mapping")
        normalized_overrides: dict[str, tuple[SessionInterval, ...]] = {}
        for day, intervals in raw_overrides.items():
            try:
                date.fromisoformat(day)
            except (TypeError, ValueError) as exc:
                raise SessionBarsError("date override keys must be ISO dates") from exc
            if isinstance(intervals, (str, bytes)) or not isinstance(intervals, (list, tuple)):
                raise SessionBarsError("date overrides must contain interval sequences")
            normalized = tuple(intervals)
            if any(not isinstance(item, SessionInterval) for item in normalized):
                raise SessionBarsError("date overrides must contain SessionInterval records")
            normalized_overrides[day] = normalized
        object.__setattr__(self, "date_overrides", MappingProxyType(normalized_overrides))
        self.validate()

    def validate(self) -> None:
        if (not isinstance(self.grid_id, str) or not self.grid_id or type(self.nominal_minutes) is not int or self.nominal_minutes < 1
                or type(self.phase_minutes) is not int or not 0 <= self.phase_minutes < self.nominal_minutes
                or type(self.close_delay_minutes) is not int or self.close_delay_minutes < 0 or type(self.include_empty) is not bool):
            raise SessionBarsError("invalid grid scalar")
        try:
            ZoneInfo(self.timezone)
        except (TypeError, ValueError, ZoneInfoNotFoundError) as exc:
            raise SessionBarsError("timezone must be IANA") from exc
        if not isinstance(self.intervals, tuple) or not self.intervals or any(not isinstance(v, SessionInterval) for v in self.intervals):
            raise SessionBarsError("intervals must be nonempty SessionInterval tuple")
        if len({item.label for item in self.intervals}) != len(self.intervals):
            raise SessionBarsError("duplicate interval label")
        spans = []
        for item in self.intervals:
            start = time.fromisoformat(item.start_local).hour * 60 + time.fromisoformat(item.start_local).minute
            end = time.fromisoformat(item.end_local).hour * 60 + time.fromisoformat(item.end_local).minute
            spans.append((start, end + (1440 if end <= start else 0)))
        for index, (start, end) in enumerate(spans):
            for other_start, other_end in spans[index + 1:]:
                if any(max(start, other_start + shift) < min(end, other_end + shift) for shift in (-1440, 0, 1440)):
                    raise SessionBarsError("declared intervals overlap")
        for intervals in self.date_overrides.values():
            override_spans = []
            for item in intervals:
                start = time.fromisoformat(item.start_local).hour * 60 + time.fromisoformat(item.start_local).minute
                end = time.fromisoformat(item.end_local).hour * 60 + time.fromisoformat(item.end_local).minute
                override_spans.append((start, end + (1440 if end <= start else 0)))
            for index, (start, end) in enumerate(override_spans):
                for other_start, other_end in override_spans[index + 1:]:
                    if any(max(start, other_start + shift) < min(end, other_end + shift) for shift in (-1440, 0, 1440)):
                        raise SessionBarsError("declared override intervals overlap")


def generate_phase_variants(base: BarGridSpec, phase_minutes: Iterable[int]) -> tuple[BarGridSpec, ...]:
    if not isinstance(base, BarGridSpec):
        raise SessionBarsError("base must be BarGridSpec")
    try:
        phases = sorted(set(phase_minutes))
    except Exception as exc:
        raise SessionBarsError("phases must be iterable") from exc
    if any(type(v) is not int or not 0 <= v < base.nominal_minutes for v in phases):
        raise SessionBarsError("phases must be true ints within grid")
    return tuple(BarGridSpec(f"{base.grid_id}-p{p}", base.timezone, base.nominal_minutes, p, base.intervals, base.include_empty, base.close_delay_minutes, base.date_overrides) for p in phases)


def _endpoint(day: date, value: str, zone: ZoneInfo) -> datetime:
    naive = datetime.combine(day, time.fromisoformat(value))
    candidates = []
    for fold in (0, 1):
        candidate = naive.replace(tzinfo=zone, fold=fold)
        round_trip = candidate.astimezone(timezone.utc).astimezone(zone)
        if round_trip.replace(tzinfo=None) == naive and round_trip.fold == fold and not any(candidate.timestamp() == x.timestamp() for x in candidates):
            candidates.append(candidate)
    if not candidates:
        raise SessionBarsError(f"nonexistent local endpoint: {naive.isoformat()} {zone.key}")
    if len(candidates) != 1:
        raise SessionBarsError(f"ambiguous local endpoint: {naive.isoformat()} {zone.key}")
    return candidates[0]


def _bounds(day: date, interval: SessionInterval, zone: ZoneInfo) -> tuple[int, int]:
    start = _endpoint(day, interval.start_local, zone)
    end = _endpoint(day + timedelta(days=interval.end_local <= interval.start_local), interval.end_local, zone)
    a, b = int(start.timestamp() * 1000), int(end.timestamp() * 1000)
    if a >= b:
        raise SessionBarsError("interval must resolve to positive UTC elapsed time")
    return a, b


def _valid(value: object, integer: bool = False) -> bool:
    try:
        return (not isinstance(value, bool) and isinstance(value, Integral if integer else Real)
                and math.isfinite(float(value)) and (not integer or int(value) == value))
    except (OverflowError, TypeError, ValueError):
        return False


def _validate(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not set(_REQUIRED).issubset(rows.columns):
        raise SessionBarsError("missing lower-grain columns")
    # Caller labels are not evidence identity and must never affect positional
    # provisional checks or exactly-once allocation accounting.
    frame = rows.copy(deep=True).reset_index(drop=True)
    for name in ("open_ms", "close_ms"):
        if not frame[name].map(lambda v: _valid(v, True)).all():
            raise SessionBarsError("lower-grain bounds must be finite integer milliseconds")
        frame[name] = frame[name].map(int)
    for name in ("open", "high", "low", "close", "volume"):
        if not frame[name].map(_valid).all():
            raise SessionBarsError("lower-grain cells must be finite real values")
        frame[name] = frame[name].map(float)
    if frame.open_ms.duplicated().any():
        raise SessionBarsError("duplicate lower-grain open")
    if not frame.open_ms.is_monotonic_increasing:
        raise SessionBarsError("lower-grain rows must be monotone")
    if (frame.open_ms >= frame.close_ms).any() or (frame.close_ms.shift(1).iloc[1:] > frame.open_ms.iloc[1:]).any() or (frame.volume < 0).any() or (frame.high < frame[["open", "close"]].max(axis=1)).any() or (frame.low > frame[["open", "close"]].min(axis=1)).any():
        raise SessionBarsError("invalid lower-grain bounds or OHLC")
    present = [name for name in _CONFIRMED if name in frame]
    if len(present) > 1:
        raise SessionBarsError("multiple confirmation columns")
    provisional = frame.iloc[0:0].copy()
    if present:
        confirmed = frame[present[0]]
        if not confirmed.map(
            lambda value: type(value) is bool
            or (not isinstance(value, bool) and isinstance(value, Integral) and int(value) in {0, 1})
        ).all():
            raise SessionBarsError("confirmation values must be boolean or exact 0/1")
        confirmed_mask = confirmed.map(bool).to_numpy(dtype=bool)
        false_positions = [int(position) for position in pd.RangeIndex(len(frame)) if not confirmed_mask[position]]
        if false_positions and false_positions != [len(frame) - 1]:
            raise SessionBarsError("interior provisional lower-grain row")
        if false_positions:
            provisional = frame.iloc[-1:].copy()
            frame = frame.iloc[:-1].copy()
    return frame, provisional


def _actual(frame: pd.DataFrame, name: str, integer: bool = False) -> int | float | None:
    if name not in frame or frame.empty:
        return None
    values = frame[name]
    missing = values.map(pd.isna)
    present = values[~missing]
    def valid_activity(value: object) -> bool:
        if isinstance(value, bool) or not isinstance(value, Real):
            return False
        try:
            normalized = float(value)
        except (OverflowError, TypeError, ValueError):
            return False
        return (
            math.isfinite(normalized)
            and normalized >= 0
            and (not integer or normalized.is_integer())
        )

    if not present.map(valid_activity).all():
        raise SessionBarsError(f"invalid actual {name} evidence")
    if present.empty or bool(missing.any()):
        return None
    result = sum(present)
    if not _valid(result, integer):
        raise SessionBarsError(f"invalid actual {name} aggregate")
    return int(result) if integer else float(result)


def _flags(interval: SessionInterval, number: int, total: int) -> dict[str, bool]:
    regular = interval.label in {"regular", "market"}
    return {"premarket": interval.label == "premarket", "market": regular, "postmarket": interval.label == "postmarket", "first_session_bar": number == 0, "last_session_bar": number == total - 1, "first_regular_bar": regular and number == 0, "last_regular_bar": regular and number == total - 1}


def _strict_records(frame: pd.DataFrame, columns: Iterable[str]) -> list[dict[str, object]]:
    names = [name for name in columns if name in frame.columns]
    return [
        {
            name: (
                None
                if pd.isna(row[name])
                else bool(row[name])
                if name in _CONFIRMED
                else int(row[name])
                if name in {"open_ms", "close_ms", "traded_minutes", "trade_count"}
                else float(row[name])
            )
            for name in names
        }
        for _, row in frame.iterrows()
    ]


def _hash(
    grid: BarGridSpec,
    interval: SessionInterval,
    start: int,
    end: int,
    frame: pd.DataFrame,
) -> str:
    cols = [name for name in frame.columns if name in (*_REQUIRED, *_CONFIRMED, "traded_minutes", "trade_count", "realized_variance")]
    text = strict_json_dumps(
        {
            "grid": {
                "close_delay_minutes": grid.close_delay_minutes,
                "grid_id": grid.grid_id,
                "include_empty": grid.include_empty,
                "active_interval": {
                    "end_local": interval.end_local,
                    "label": interval.label,
                    "start_local": interval.start_local,
                },
                "intervals": [
                    {
                        "end_local": item.end_local,
                        "label": item.label,
                        "start_local": item.start_local,
                    }
                    for item in grid.intervals
                ],
                "date_overrides": {
                    day: [
                        {"end_local": item.end_local, "label": item.label, "start_local": item.start_local}
                        for item in intervals
                    ]
                    for day, intervals in grid.date_overrides.items()
                },
                "nominal_minutes": grid.nominal_minutes,
                "phase_minutes": grid.phase_minutes,
                "timezone": grid.timezone,
            },
            "open_ms": start,
            "close_ms": end,
            "rows": _strict_records(frame, cols),
        }
    )
    return hashlib.sha256(text.encode()).hexdigest()


def _provisional_evidence(frame: pd.DataFrame) -> tuple[tuple[int, ...], str | None]:
    if frame.empty:
        return (), None
    timestamps = tuple(int(value) for value in frame["open_ms"].tolist())
    digest = hashlib.sha256(
        strict_json_dumps(
            {
                "excluded_provisional_rows": _strict_records(
                    frame,
                    (*_REQUIRED, *_CONFIRMED, "traded_minutes", "trade_count", "realized_variance"),
                )
            }
        ).encode()
    ).hexdigest()
    return timestamps, digest


def _attach_attrs(
    result: pd.DataFrame,
    *,
    missing_minutes: int,
    provisional: pd.DataFrame,
) -> pd.DataFrame:
    timestamps, digest = _provisional_evidence(provisional)
    result.attrs["missing_minutes"] = missing_minutes
    result.attrs["excluded_provisional_count"] = len(provisional)
    result.attrs["excluded_provisional_open_ms"] = timestamps
    result.attrs["excluded_provisional_row_sha256"] = digest
    return result


def _buckets(start: int, end: int, grid: BarGridSpec) -> Iterable[tuple[int, int]]:
    phase_end = start + grid.phase_minutes * 60_000
    if grid.phase_minutes:
        yield start, min(phase_end, end)
    cursor = phase_end if grid.phase_minutes else start
    while cursor < end:
        finish = min(cursor + grid.nominal_minutes * 60_000, end)
        yield cursor, finish
        cursor = finish


def _intervals_for_day(grid: BarGridSpec, day: date) -> tuple[SessionInterval, ...]:
    return grid.date_overrides.get(day.isoformat(), grid.intervals)


def _build_session_bars(
    rows: pd.DataFrame,
    *,
    recipe_id: str,
    grid: BarGridSpec,
) -> tuple[pd.DataFrame, tuple[BarReceipt, ...]]:
    if not isinstance(recipe_id, str) or not recipe_id.strip() or not isinstance(grid, BarGridSpec) or not isinstance(rows, pd.DataFrame):
        raise SessionBarsError("invalid recipe, grid, or rows")
    columns = list(_REQUIRED)
    frame, provisional = _validate(rows)
    if frame.empty:
        return _attach_attrs(pd.DataFrame(columns=columns), missing_minutes=0, provisional=provisional), ()
    zone = ZoneInfo(grid.timezone)
    candidate_days = {datetime.fromtimestamp(v / 1000, zone).date() for v in frame.open_ms}
    candidate_days |= {day - timedelta(days=1) for day in tuple(candidate_days)}
    days: list[date] = []
    for day in sorted(candidate_days):
        if any(
            not frame[
                (frame.open_ms >= interval_open) & (frame.close_ms <= interval_close)
            ].empty
            for interval_open, interval_close in (
                _bounds(day, interval, zone) for interval in _intervals_for_day(grid, day)
            )
        ):
            days.append(day)
    bars, receipts, allocated = [], [], set()
    missing_minutes = 0
    for day in days:
        for interval in _intervals_for_day(grid, day):
            interval_open, interval_close = _bounds(day, interval, zone)
            buckets = tuple(_buckets(interval_open, interval_close, grid))
            for position, (open_ms, close_ms) in enumerate(buckets):
                member = frame[(frame.open_ms >= open_ms) & (frame.close_ms <= close_ms)]
                allocated.update(member.index)
                effective = (close_ms - open_ms) // 60_000
                empty = member.empty
                observed = sum(min(int(row.close_ms), close_ms) - max(int(row.open_ms), open_ms) for _, row in member.iterrows()) // 60_000
                missing_minutes += effective - observed
                if empty and not grid.include_empty:
                    continue
                volume = None if empty else float(member.volume.sum())
                if volume is not None and not math.isfinite(volume):
                    raise SessionBarsError("invalid volume aggregate")
                receipts.append(BarReceipt(BAR_RECEIPT_SCHEMA, recipe_id, open_ms // 60_000, open_ms, close_ms, grid.nominal_minutes, effective, None if empty else _actual(member, "traded_minutes", True), volume, None if empty else _actual(member, "trade_count", True), None if empty else _actual(member, "realized_variance"), _flags(interval, position, len(buckets)), effective < grid.nominal_minutes, True, empty, close_ms + grid.close_delay_minutes * 60_000, _hash(grid, interval, open_ms, close_ms, member)))
                if not empty:
                    bars.append({"open_ms": open_ms, "close_ms": close_ms, "open": float(member.open.iloc[0]), "high": float(member.high.max()), "low": float(member.low.min()), "close": float(member.close.iloc[-1]), "volume": float(member.volume.sum())})
    if len(allocated) != len(frame):
        raise SessionBarsError("lower-grain row outside every declared session")
    result = _attach_attrs(
        pd.DataFrame(bars, columns=columns),
        missing_minutes=missing_minutes,
        provisional=provisional,
    )
    return result, tuple(receipts)


def build_session_bars(rows: pd.DataFrame, *, recipe_id: str, grid: BarGridSpec) -> tuple[pd.DataFrame, tuple[BarReceipt, ...]]:
    """Build pure UTC-elapsed buckets and totalize malformed evidence errors."""
    try:
        return _build_session_bars(rows, recipe_id=recipe_id, grid=grid)
    except SessionBarsError:
        raise
    except Exception as exc:
        raise SessionBarsError("invalid session-bar evidence") from exc
