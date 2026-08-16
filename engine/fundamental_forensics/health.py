"""Operational and source freshness for Filing Forensics.

This module tells the truth about clocks the workbench already has.  It does
not fetch SEC documents, run detectors, or mint a new history store.  Render
and evaluation wall-clocks may appear as ``evaluated_at`` so a reader can see
when the check ran; they are never used as source freshness.

The composed state's ``generated_at`` is a source-snapshot clock (the latest
EDGAR ``as_of`` / filed time the builder already stamps).  Health reports that
value as ``broad_source_at`` only.  It is never relabelled as a composition,
build, publication, or private-object clock.  Those fields stay null until a
durable independent stamp exists — gzip mtime is 0, and ``public_summary.json``
``generated_at`` is the same source-snapshot family plus a 30-day page-shell
failsafe, not a build or publication receipt.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Mapping

from engine.fundamental_forensics.models import parse_utc
from engine.fundamental_forensics.private_state import (
    ORIGIN_LAST_GOOD,
    ORIGIN_MISSING,
    LoadedState,
    decode_state_blob,
    load_state_record,
)

HEALTH_SCHEMA = "fundamental_forensics.health.v1"
# Daily pipeline SLA with weekend + one missed-nightly slack.  Distinct from
# scripts.build_fundamental_forensics.PUBLIC_SUMMARY_MAX_AGE_DAYS (30), which
# only stops frozen anonymous counts from advertising — not a freshness claim.
# Four days: Friday bake → Monday is three, plus one extra outage night.  A
# source that has not moved for a week cannot report Current.
FRESHNESS_SLA_DAYS = 4
FRESHNESS_BUDGET_SECONDS = FRESHNESS_SLA_DAYS * 24 * 60 * 60
STATUSES = ("current", "stale", "degraded", "unavailable")
REASON_SOURCE_CURRENT = "SOURCE_CURRENT"
REASON_SOURCE_STALE = "SOURCE_STALE"
REASON_LAST_GOOD_STALE = "LAST_GOOD_STALE"
REASON_STATE_MISSING = "STATE_MISSING"
REASON_STATE_INVALID = "STATE_INVALID"
REASON_SOURCE_CLOCK_MISSING = "SOURCE_CLOCK_MISSING"

_LEAK_TOKENS = (
    "object_key",
    "STATE_KEY",
    "fundamental_forensics/state.json.gz",
    "R2_ACCESS_KEY",
    "R2_SECRET",
    "SECRET_ACCESS_KEY",
    "ACCESS_KEY_ID",
    "aws_secret",
    "credential",
)


def _aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_clock(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return _aware_utc(value)
    try:
        parsed = parse_utc(str(value), field="health_clock")
    except ValueError:
        text = str(value).strip()
        if len(text) == 10 and text[4] == "-" and text[7] == "-":
            try:
                parsed = parse_utc(f"{text}T00:00:00Z", field="health_clock")
            except ValueError:
                return None
        else:
            return None
    return parsed


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware_utc(value).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _date_text(value: Any) -> str | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    if len(text) >= 10 and text[4] == "-" and text[7] == "-":
        return text[:10]
    parsed = _parse_clock(value)
    if parsed is None:
        return None
    return parsed.date().isoformat()


def _disclosure_projection_clock(document: Mapping[str, Any]) -> datetime | None:
    """Latest source-side disclosure clock, never a computed/render clock."""
    companies = document.get("companies")
    if not isinstance(companies, Mapping):
        return None
    latest: datetime | None = None
    for company in companies.values():
        if not isinstance(company, Mapping):
            continue
        disclosures = company.get("disclosures")
        if not isinstance(disclosures, Mapping):
            continue
        clocks = disclosures.get("clocks")
        if not isinstance(clocks, Mapping):
            continue
        for key in ("as_of", "accepted_at", "filed_on", "recorded_at"):
            candidate = _parse_clock(clocks.get(key))
            if candidate is not None and (latest is None or candidate > latest):
                latest = candidate
    return latest


def _payload(
    *,
    status: str,
    reason_code: str,
    now: datetime,
    age_seconds: int | None,
    clocks: Mapping[str, str | None],
    origin: str,
    present: bool,
    digest: str | None,
) -> dict[str, Any]:
    return {
        "schema": HEALTH_SCHEMA,
        "status": status,
        "reason_code": reason_code,
        "age_seconds": age_seconds,
        "freshness_budget_seconds": FRESHNESS_BUDGET_SECONDS,
        "evaluated_at": _iso(_aware_utc(now)),
        "clocks": {
            "broad_source_at": clocks.get("broad_source_at"),
            "latest_source_filing_date": clocks.get("latest_source_filing_date"),
            "composed_state_at": clocks.get("composed_state_at"),
            "private_object_at": clocks.get("private_object_at"),
            "disclosure_projection_at": clocks.get("disclosure_projection_at"),
            "last_successful_build_at": clocks.get("last_successful_build_at"),
            "last_publication_at": clocks.get("last_publication_at"),
        },
        "private_object": {
            "present": present,
            "sha256": digest,
            "origin": origin,
        },
    }


def health_from_inputs(
    *,
    loaded: LoadedState,
    document: Mapping[str, Any] | None,
    now: datetime,
) -> dict[str, Any]:
    """Classify one already-loaded envelope.  ``now`` is evaluation time only."""
    evaluated = _aware_utc(now)
    empty_clocks = {
        "broad_source_at": None,
        "latest_source_filing_date": None,
        "composed_state_at": None,
        "private_object_at": None,
        "disclosure_projection_at": None,
        "last_successful_build_at": None,
        "last_publication_at": None,
    }
    if loaded.origin == ORIGIN_MISSING or loaded.blob is None:
        return _payload(
            status="unavailable",
            reason_code=REASON_STATE_MISSING,
            now=evaluated,
            age_seconds=None,
            clocks=empty_clocks,
            origin=ORIGIN_MISSING,
            present=False,
            digest=None,
        )
    digest = sha256(loaded.blob).hexdigest()
    if document is None:
        try:
            document = decode_state_blob(loaded.blob)
        except Exception:  # noqa: BLE001 - invalid state is an unavailable health
            return _payload(
                status="unavailable",
                reason_code=REASON_STATE_INVALID,
                now=evaluated,
                age_seconds=None,
                clocks=empty_clocks,
                origin=loaded.origin,
                present=True,
                digest=digest,
            )

    source_clock = _parse_clock(document.get("generated_at"))
    summary = document.get("summary") if isinstance(document.get("summary"), Mapping) else {}
    filing_date = _date_text(document.get("as_of") or summary.get("latest_filing"))
    disclosure_clock = _disclosure_projection_clock(document)
    clocks = {
        "broad_source_at": _iso(source_clock),
        "latest_source_filing_date": filing_date,
        "composed_state_at": None,
        "private_object_at": None,
        "disclosure_projection_at": _iso(disclosure_clock),
        "last_successful_build_at": None,
        "last_publication_at": None,
    }
    if source_clock is None:
        return _payload(
            status="unavailable",
            reason_code=REASON_SOURCE_CLOCK_MISSING,
            now=evaluated,
            age_seconds=None,
            clocks=clocks,
            origin=loaded.origin,
            present=True,
            digest=digest,
        )

    age = max(0, int((evaluated - source_clock).total_seconds()))
    stale = age > FRESHNESS_BUDGET_SECONDS
    if loaded.origin == ORIGIN_LAST_GOOD and stale:
        status = "degraded"
        reason = REASON_LAST_GOOD_STALE
    elif stale:
        status = "stale"
        reason = REASON_SOURCE_STALE
    else:
        status = "current"
        reason = REASON_SOURCE_CURRENT
    return _payload(
        status=status,
        reason_code=reason,
        now=evaluated,
        age_seconds=age,
        clocks=clocks,
        origin=loaded.origin,
        present=True,
        digest=digest,
    )


def evaluate_health(
    root: str | Path,
    *,
    now: datetime | None = None,
    store_factory: Callable[[], Any] | None = None,
    cache_seconds: float | None = None,
    loaded: LoadedState | None = None,
    document: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the private health contract for one repository root."""
    evaluated = _aware_utc(now or datetime.now(timezone.utc))
    record = loaded if loaded is not None else load_state_record(
        root,
        store_factory=store_factory,
        cache_seconds=cache_seconds,
    )
    parsed = document
    if parsed is None and record.blob is not None:
        try:
            parsed = decode_state_blob(record.blob)
        except Exception:  # noqa: BLE001
            parsed = None
    return health_from_inputs(
        loaded=record,
        document=parsed,
        now=evaluated,
    )


def assert_no_private_leak(payload: Mapping[str, Any]) -> None:
    """Fail if a health document carries rows, keys, or credentials."""
    if "companies" in payload or "ranked_findings" in payload or "findings" in payload:
        raise AssertionError("health payload must not include private rows")
    rendered = str(payload)
    for token in _LEAK_TOKENS:
        if token in rendered:
            raise AssertionError(f"health payload leaked {token!r}")
