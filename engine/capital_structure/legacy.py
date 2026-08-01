"""Deterministic compatibility projection for the pre-Capital-Structure feed.

The old consumers read exactly six fields from
``data/edgar/dilution_events.parquet``.  This adapter intentionally preserves
that narrow shape while the canonical ledger grows elsewhere.  It is append
only after its cutover: historical rows are seed evidence, not a backfill
target.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any

import pandas as pd


LEGACY_COLUMNS: tuple[str, ...] = (
    "accession", "cik", "ticker", "form", "filing_date", "_first_seen",
)
LEGACY_FORMS = frozenset({
    "S-3", "S-3ASR", "S-3/A", "424B1", "424B2", "424B3", "424B4", "424B5",
})


def _as_utc(value: Any) -> datetime | None:
    """Parse an explicit observation time; absent/invalid is not eligible."""
    if value is None or value is pd.NaT:
        return None
    try:
        stamp = pd.Timestamp(value)
    except (TypeError, ValueError):
        return None
    if pd.isna(stamp):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.tz_localize("UTC")
    else:
        stamp = stamp.tz_convert("UTC")
    return stamp.to_pydatetime()


def _cutover_utc(value: date | datetime | str) -> datetime:
    stamp = _as_utc(value)
    if stamp is None:
        raise ValueError("cutover_at must be a valid date or timestamp")
    return stamp


def _records(seed: pd.DataFrame | Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(seed, pd.DataFrame):
        missing = [column for column in LEGACY_COLUMNS if column not in seed.columns]
        if missing:
            raise ValueError(f"seed is missing legacy columns: {', '.join(missing)}")
        return [{column: row[column] for column in LEGACY_COLUMNS}
                for _, row in seed.loc[:, list(LEGACY_COLUMNS)].iterrows()]
    rows: list[dict[str, Any]] = []
    for row in seed:
        missing = [column for column in LEGACY_COLUMNS if column not in row]
        if missing:
            raise ValueError(f"seed row is missing legacy columns: {', '.join(missing)}")
        rows.append({column: row[column] for column in LEGACY_COLUMNS})
    return rows


def _json_object(value: Any, *, label: str) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (str, bytes, bytearray)):
        try:
            parsed = json.loads(value)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError(f"{label} is not valid JSON") from exc
        if isinstance(parsed, Mapping):
            return dict(parsed)
    raise ValueError(f"{label} must contain a JSON object")


def _canonical_event(event: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """Unwrap strict events from canonical objects or serialized ledger rows."""
    for key in ("event_json", "canonical_event", "event_payload"):
        if key not in event:
            continue
        value = event.get(key)
        if value is None or value is pd.NaT:
            raise ValueError(f"{key} must contain a JSON object")
        if not isinstance(value, (Mapping, str, bytes, bytearray)):
            try:
                if pd.isna(value):
                    raise ValueError(f"{key} must contain a JSON object")
            except (TypeError, ValueError):
                raise ValueError(f"{key} must contain a JSON object") from None
        return _json_object(value, label=key)
    # Some integrations expose the event envelope under one nested ``event``
    # column.  Do not confuse that with the canonical event's semantic
    # ``event`` section when filing/issuer clocks are already top-level.
    nested = event.get("event")
    if not all(key in event for key in ("filing", "issuer", "point_in_time")):
        if isinstance(nested, (Mapping, str, bytes, bytearray)):
            candidate = _json_object(nested, label="event")
            if all(key in candidate for key in ("filing", "issuer", "point_in_time")):
                return candidate
    if all(key in event for key in ("filing", "issuer", "point_in_time")):
        return event
    return None


def _nested_object(event: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = event.get(key)
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (str, bytes, bytearray)):
        return _json_object(value, label=key)
    raise ValueError(f"canonical event requires object column {key!r}")


def _legacy_row(event: Mapping[str, Any]) -> dict[str, Any]:
    """Select the legacy contract from flat, canonical, or ledger-row input."""
    canonical = _canonical_event(event)
    if canonical is not None:
        filing = _nested_object(canonical, "filing")
        issuer = _nested_object(canonical, "issuer")
        point_in_time = _nested_object(canonical, "point_in_time")
        return {
            "accession": filing.get("accession"),
            "cik": issuer.get("cik"),
            "ticker": issuer.get("ticker"),
            "form": filing.get("form"),
            "filing_date": filing.get("filing_date"),
            "_first_seen": (
                point_in_time.get("available_at")
                or point_in_time.get("system_available_at")
                or point_in_time.get("first_seen_at")
            ),
        }

    first_seen = event.get(
        "_first_seen", event.get("available_at", event.get("first_seen"))
    )
    return {
        "accession": event.get("accession"),
        "cik": event.get("cik"),
        "ticker": event.get("ticker"),
        "form": event.get("form"),
        "filing_date": event.get("filing_date"),
        "_first_seen": first_seen,
    }


def _event_records(
    events: Iterable[Mapping[str, Any]] | pd.DataFrame,
) -> Iterable[Mapping[str, Any]]:
    if isinstance(events, pd.DataFrame):
        yield from events.to_dict(orient="records")
        return
    for event in events:
        if not isinstance(event, Mapping):
            raise ValueError("legacy projection events must be mapping rows")
        yield event


def project_legacy_rows(
    seed_rows: pd.DataFrame | Sequence[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]] | pd.DataFrame,
    *,
    cutover_at: date | datetime | str,
) -> list[dict[str, Any]]:
    """Append post-cutover eligible events to an untouched legacy seed.

    Events need an explicit first-seen timestamp.  Filing date is deliberately
    *not* a fallback, because using it would silently backfill pre-cutover
    history.  Seed accessions always win; duplicate candidate accessions retain
    their first canonical observation for stable output.
    """
    cutover = _cutover_utc(cutover_at)
    projected = _records(seed_rows)
    seen_accessions = {str(row["accession"]) for row in projected if row.get("accession") is not None}

    for event in _event_records(events):
        row = _legacy_row(event)
        accession = row["accession"]
        if accession is None or str(accession) in seen_accessions:
            continue
        if row["form"] not in LEGACY_FORMS:
            continue
        first_seen = _as_utc(row["_first_seen"])
        # Cutover is inclusive: the first nightly using the new ledger is not
        # historical backfill merely because its observation is at midnight.
        if first_seen is None or first_seen < cutover:
            continue
        projected.append(row)
        seen_accessions.add(str(accession))
    return projected


def project_legacy_events(
    seed: pd.DataFrame | Sequence[Mapping[str, Any]],
    events: Iterable[Mapping[str, Any]] | pd.DataFrame,
    *,
    cutover_at: date | datetime | str,
) -> pd.DataFrame:
    """Return the exact six-column legacy DataFrame, preserving nulls as nulls."""
    rows = project_legacy_rows(seed, events, cutover_at=cutover_at)
    return pd.DataFrame(rows, columns=list(LEGACY_COLUMNS), dtype=object)


def write_legacy_projection(
    seed_path: str | Path,
    events: Iterable[Mapping[str, Any]] | pd.DataFrame,
    *,
    cutover_at: date | datetime | str,
    output_path: str | Path | None = None,
) -> pd.DataFrame:
    """Materialize a legacy parquet projection without rewriting an unchanged seed.

    When there are no eligible post-cutover additions, a separate output path
    receives a byte-for-byte copy of the seed.  This keeps the baseline artifact
    immutable and makes an empty first migration run a true no-op.
    """
    source = Path(seed_path)
    target = Path(output_path) if output_path is not None else source
    seed = pd.read_parquet(source)
    projected = project_legacy_events(seed, events, cutover_at=cutover_at)
    if len(projected) == len(seed):
        if target != source:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        return projected

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".parquet", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        projected.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, target)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    return projected
