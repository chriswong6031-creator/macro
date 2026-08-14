"""engine/entry_radar/producers/ipo.py — the IPO / young-listing lane.

``data/ipo/calendar.parquet`` (Track C row #21, ``collectors/ipo_calendar.py``)
— seeded and committed, so it survives the vendor bot-wall.

WHY THE IPO LANE IS FIRST-CLASS (contract §6)
-----------------------------------------------
"IPO/small caps not rejected for index non-membership" is an explicit product
gate (§0 P-6).  A newly-listed name is in no index, carries no 20-day dollar
volume, and would fail every Layer-B and most Layer-C thresholds — so without
this adapter the whole young cohort would be invisible to Radar exactly when it
is most interesting.  It is admitted on the listing FACT, not on a threshold.

"Young history is not low-quality data" (§6).  So this adapter also supplies
``history_age_sessions`` — the field that routes a name into the young cohort's
SEPARATE calibration (§12) rather than into a warm-up exclusion.  A name with
40 sessions of history is a name with 40 sessions of history; it is not a name
with bad data.

ARTIFACT SHAPE (verified from ``collectors/ipo_calendar.py``:142-155, confirmed
by the consumer ``engine/ipo_radar.py``:278-322): index ``deal_id``; columns
``ticker, company, exchange, status`` (priced/upcoming/filed/withdrawn),
``offer_price, range_low, range_high, range_mid, shares, offer_value_usd,
priced_date, expected_date, filed_date, withdraw_date, is_spac, as_of,
marketed_low, marketed_high``.

Only ``priced`` and ``upcoming`` rows nominate.  ``filed`` and ``withdrawn``
are real facts but not tradable-now facts, and admitting them would spend probe
budget on names with no tape.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from engine.entry_radar.contracts import Nomination, NominationError, ProducerRead, parse_ts, utcnow
from engine.entry_radar.producers.base import (
    AdapterResult,
    grade_staleness,
    stale_after,
    unavailable,
)

log = logging.getLogger(__name__)

IPO_SOURCE_ID = "ipo:calendar"

#: Rows worth probe budget, with their date column and reason code.
_ACTIVE_STATUSES: tuple[tuple[str, str, str], ...] = (
    ("priced", "priced_date", "ipo.recent_listing"),
    ("upcoming", "expected_date", "ipo.upcoming_listing"),
)


def read_ipo_calendar(path: Path | None = None, *,
                      rows: Sequence[Mapping[str, Any]] | None = None,
                      loader: Any = None,
                      recent_days: int = 120,
                      now: datetime | None = None,
                      cfg: Mapping[str, Any] | None = None) -> AdapterResult:
    """``data/ipo/calendar.parquet`` → special_situation nominations + history ages.

    ``rows`` (or ``loader``) short-circuits the parquet read, which is what
    tests use — this worktree is sparse, and an absent parquet must read as
    ``unavailable``, never as "no IPOs happened".

    ``recent_days`` bounds the priced lane to the trailing window
    ``engine/ipo_radar.py`` uses; upcoming rows are taken whole.
    """
    stamp = now or utcnow()
    today = stamp.date()

    records: list[Mapping[str, Any]]
    if rows is not None:
        records = [r for r in rows if isinstance(r, Mapping)]
    elif loader is not None or path is not None:
        try:
            if loader is not None:
                frame = loader(path)
            else:
                import pandas as pd  # noqa: PLC0415
                frame = pd.read_parquet(path)
            if isinstance(frame, list):
                records = [r for r in frame if isinstance(r, Mapping)]
            else:
                records = frame.reset_index().to_dict("records")
        except FileNotFoundError:
            return AdapterResult(unavailable(IPO_SOURCE_ID, f"{path} absent", now=stamp))
        except Exception as exc:  # noqa: BLE001
            return AdapterResult(unavailable(IPO_SOURCE_ID, f"{path}: {exc}", now=stamp))
    else:
        return AdapterResult(
            unavailable(IPO_SOURCE_ID, "no path, loader or rows supplied", now=stamp))

    if not records:
        return AdapterResult(unavailable(
            IPO_SOURCE_ID, "IPO calendar yielded zero rows — treated as an outage, not "
                           "an empty pipeline", now=stamp))

    asof: datetime | None = None
    for row in records:
        got = parse_ts(row.get("as_of"))
        if got is not None:
            asof = got if asof is None else max(asof, got)

    stale_min = stale_after(cfg, IPO_SOURCE_ID)
    status, age = grade_staleness(asof, now=stamp, stale_after_minutes=stale_min)
    ttl = stamp + timedelta(minutes=max(1.0, stale_min))
    noms: list[Nomination] = []
    history_age: dict[str, int] = {}

    for row in records:
        sym = str(row.get("ticker") or "").strip().upper()
        if not sym:
            continue
        row_status = str(row.get("status") or "").strip().lower()
        for want, date_col, reason_code in _ACTIVE_STATUSES:
            if row_status != want:
                continue
            when = _as_date(row.get(date_col))
            if when is None:
                continue
            if want == "priced":
                aged = (today - when).days
                if aged < 0 or aged > max(1, recent_days):
                    continue
                sessions = _sessions_between(when, today)
                history_age[sym] = sessions
                text = (f"{sym} listed {when.isoformat()} — {sessions} session(s) of "
                        "history (young cohort: separate calibration, not low-quality data)")
            else:
                if when < today:
                    continue
                history_age[sym] = 0
                text = f"{sym} expected to list {when.isoformat()}"
            if row.get("is_spac"):
                text += " · SPAC"
            value = None
            for key in ("offer_value_usd", "offer_price", "range_mid"):
                try:
                    if row.get(key) is not None:
                        value = float(row[key])
                        break
                except (TypeError, ValueError):
                    continue
            row_asof = parse_ts(row.get("as_of")) or asof or stamp
            try:
                noms.append(Nomination(
                    ticker=sym, source_id=IPO_SOURCE_ID, source_family="special_situation",
                    reason_code=reason_code, reason_text=text,
                    observed_at=stamp, source_asof=min(row_asof, stamp),
                    source_value=value, source_horizon="listing", ttl_until=ttl,
                    evidence_ref=f"ipo/calendar.parquet#{row.get('deal_id') or sym}",
                    data_quality="ok" if parse_ts(row.get("as_of")) else "degraded",
                ))
            except NominationError as exc:
                log.warning("entry_radar.producers.ipo: row dropped (%s)", exc)

    read = ProducerRead(source_id=IPO_SOURCE_ID, status=status, nominations=tuple(noms),
                        source_asof=asof, observed_at=stamp, age_seconds=age,
                        stale_after_seconds=stale_min * 60.0,
                        detail=f"{len(noms)} listing nomination(s) from {len(records)} row(s)")
    return AdapterResult(read, history_age=history_age)


def _as_date(raw: Any) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    got = parse_ts(raw)
    return got.date() if got is not None else None


def _sessions_between(start: date, end: date) -> int:
    """NYSE sessions from listing to today.  Weekday fallback if the calendar fails."""
    try:
        from lib.nyse_calendar import sessions_between  # noqa: PLC0415
        return max(0, len(sessions_between(start, end)))
    except Exception:  # noqa: BLE001
        days = max(0, (end - start).days)
        return int(days * 5 / 7)
