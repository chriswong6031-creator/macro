"""Authenticated, fact-only API for BioCatalyst trial intelligence.

The serving process reads only the pointer-bound public projection created by
the isolated BioCatalyst worker.  It never opens the worker state tree, raw
ClinicalTrials.gov responses, source receipts, or private object storage.
"""
from __future__ import annotations

import base64
import binascii
import logging
import os
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

router = APIRouter()
log = logging.getLogger("macro.biocatalyst")

_NCT_ID = re.compile(r"^NCT[0-9]{8}$")
_PUBLIC_ROOT = Path(
    os.environ.get("BIOCATALYST_PUBLIC_ROOT", "/var/lib/macro-biocatalyst/public")
)
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}
_AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}
_HISTORY_PRIVATE_KEY_FRAGMENTS = (
    "raw",
    "hash",
    "receipt",
    "ref",
    "object_key",
    "path",
    "json_path",
    "provenance",
)


def _publication_runtime() -> tuple[type[Exception], type[Any]]:
    """Load the heavy projection validator only for this product surface."""

    from engine.biocatalyst.publication import (  # noqa: PLC0415
        PublicationError,
        PublicGenerationPublisher,
    )

    return PublicationError, PublicGenerationPublisher


def _verify_serving_runtime() -> None:
    """Fail startup loudly once the operator-provisioned lane exists."""

    _publication_runtime()


# The unprovisioned product is intentionally dark and must not force every
# unrelated app.main consumer to install the BioCatalyst validation stack.
# Once setup creates the public root, a missing serving dependency is a startup
# error rather than a silently absent or request-time-only product route.
if _PUBLIC_ROOT.exists():
    _verify_serving_runtime()


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Authenticate first and enforce the paid payload even while staging."""

    from app.main import require_user as _require_user  # noqa: PLC0415
    from app.paywall import enforce_site_full  # noqa: PLC0415

    return enforce_site_full(_require_user(authorization), always=True)


def _publisher() -> Any:
    _publication_error, publisher_type = _publication_runtime()
    return publisher_type(_PUBLIC_ROOT)


def _unavailable(exc: Exception | None = None) -> HTTPException:
    if exc is not None:
        code = getattr(exc, "code", type(exc).__name__)
        log.warning("BioCatalyst public projection unavailable (%s)", code)
    return HTTPException(
        status_code=503,
        detail="trial intelligence temporarily unavailable",
        headers=_PRIVATE_HEADERS,
    )


def _read_bundle() -> tuple[Any, dict[str, Any]]:
    publication_error, publisher_type = _publication_runtime()
    publisher = publisher_type(_PUBLIC_ROOT)
    try:
        projection = publisher.read_trial_projection()
    except (OSError, publication_error) as exc:
        raise _unavailable(exc) from None
    if projection is None:
        raise _unavailable()
    try:
        health = publisher.read_operational_health()
    except (OSError, publication_error) as exc:
        log.warning("BioCatalyst operational health unavailable (%s)", getattr(exc, "code", type(exc).__name__))
        health = {
            "state": "unavailable",
            "last_success_at": projection.generation.last_success_at,
            "last_attempt_at": projection.generation.last_attempt_at,
            "last_error_code": "OPERATIONAL_HEALTH_UNAVAILABLE",
        }
    return projection, health


def _response(payload: Mapping[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=dict(payload),
        status_code=status_code,
        headers=_PRIVATE_HEADERS,
    )


def _fact(facts: Mapping[str, Any], key: str) -> Any:
    value = facts.get(key)
    if not isinstance(value, Mapping) or value.get("state") != "observed":
        return None
    return value.get("value")


def _text(value: object, *, maximum: int = 4096) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split()).strip()
    if not cleaned:
        return None
    return cleaned if len(cleaned) <= maximum else cleaned[: maximum - 1].rstrip() + "…"


def _text_list(value: object, *, limit: int = 100, maximum: int = 512) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[str] = []
    seen: set[str] = set()
    for item in value:
        rendered = _text(item, maximum=maximum)
        if rendered is None or rendered in seen:
            continue
        rows.append(rendered)
        seen.add(rendered)
        if len(rows) >= limit:
            break
    return rows


def _named_rows(value: object, *, kind: str, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return []
    rows: list[dict[str, Any]] = []
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        if kind == "intervention":
            row = {
                "name": _text(raw.get("name"), maximum=512),
                "type": _text(raw.get("type"), maximum=80),
                "description": _text(raw.get("description"), maximum=4000),
                "other_names": _text_list(
                    raw.get("otherNames") if "otherNames" in raw else raw.get("other_names"),
                    limit=20,
                    maximum=256,
                ),
            }
            if row["name"] is None:
                continue
        else:
            row = {
                "measure": _text(raw.get("measure"), maximum=1000),
                "time_frame": _text(
                    raw.get("timeFrame") if "timeFrame" in raw else raw.get("time_frame"),
                    maximum=1000,
                ),
                "description": _text(raw.get("description"), maximum=6000),
            }
            if row["measure"] is None:
                continue
        rows.append(row)
        if len(rows) >= limit:
            break
    return rows


def _date_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    date_value = _text(value.get("date"), maximum=10)
    if date_value is None:
        return None
    return {
        "date": date_value,
        "type": _text(value.get("type"), maximum=20),
    }


def _sponsor_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    name = _text(value.get("name"), maximum=512)
    if name is None:
        return None
    return {"name": name, "class": _text(value.get("class"), maximum=80)}


def _enrollment_value(value: object) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    count = value.get("count")
    if not isinstance(count, int) or isinstance(count, bool) or count < 0:
        return None
    return {"count": count, "type": _text(value.get("type"), maximum=20)}


def _countries(value: object) -> tuple[int | None, list[str]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None, []
    countries: list[str] = []
    seen: set[str] = set()
    count = 0
    for raw in value:
        if not isinstance(raw, Mapping):
            continue
        count += 1
        country = _text(raw.get("country"), maximum=128)
        if country and country not in seen:
            countries.append(country)
            seen.add(country)
    return count, countries[:100]


def _history_json_value(value: object, *, depth: int = 0) -> Any:
    """Copy a bounded historical value or reject leaked provenance recursively."""

    if depth > 12:
        raise _unavailable()
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _text(value, maximum=12_000)
    if isinstance(value, Mapping):
        if len(value) > 100:
            raise _unavailable()
        copied: dict[str, Any] = {}
        for key, nested in value.items():
            if not isinstance(key, str) or any(
                fragment in key.casefold()
                for fragment in _HISTORY_PRIVATE_KEY_FRAGMENTS
            ):
                raise _unavailable()
            copied[key] = _history_json_value(nested, depth=depth + 1)
        return copied
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        if len(value) > 200:
            raise _unavailable()
        return [_history_json_value(item, depth=depth + 1) for item in value]
    raise _unavailable()


def _history_url(value: object, *, nct_id: str, version: int | None = None) -> str:
    rendered = _text(value, maximum=512)
    if rendered is None:
        raise _unavailable()
    expected = f"https://clinicaltrials.gov/study/{nct_id}"
    if version is None:
        if rendered != expected + "?tab=history":
            raise _unavailable()
    elif rendered != expected + f"?a={version}&tab=history":
        raise _unavailable()
    return rendered


def _history_for_api(model: Mapping[str, Any], *, nct_id: str) -> dict[str, Any]:
    """Serve only the pointer-bound, public-safe B2 history read model.

    The model carries an integrity self-hash for publication validation, but
    product clients must never receive hash, receipt, object, reference, or
    source-path provenance.  Every nested before/after value is copied through
    the same denylist to make this boundary robust to future model additions.
    """

    available = model.get("available")
    if available is False:
        reason = _text(
            model.get("unavailable_reason")
            if "unavailable_reason" in model
            else model.get("reason"),
            maximum=80,
        )
        return {
            "available": False,
            "state": "unavailable",
            "reason": reason or "not_collected",
        }
    if available is not True or model.get("nct_id") != nct_id:
        raise _unavailable()
    source_name = _text(model.get("source_name"), maximum=80)
    if source_name != "ClinicalTrials.gov":
        raise _unavailable()
    versions = model.get("versions")
    changes = model.get("changes")
    if (
        not isinstance(versions, Sequence)
        or isinstance(versions, (str, bytes))
        or not isinstance(changes, Sequence)
        or isinstance(changes, (str, bytes))
        or len(versions) > 500
        or len(changes) > 2_000
    ):
        raise _unavailable()
    public_versions: list[dict[str, Any]] = []
    for row in versions:
        if not isinstance(row, Mapping):
            raise _unavailable()
        display_version = row.get("display_version")
        submitted_at = _text(row.get("source_submitted_at"), maximum=10)
        if (
            not isinstance(display_version, int)
            or isinstance(display_version, bool)
            or display_version < 1
            or submitted_at is None
            or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", submitted_at)
        ):
            raise _unavailable()
        public_versions.append(
            {
                "display_version": display_version,
                "submitted_at": submitted_at,
                "url": _history_url(
                    row.get("url"), nct_id=nct_id, version=display_version
                ),
            }
        )
    public_changes: list[dict[str, Any]] = []
    for row in changes:
        if not isinstance(row, Mapping):
            raise _unavailable()
        kind = _text(row.get("kind"), maximum=120)
        before_version = row.get("before_display_version")
        after_version = row.get("after_display_version")
        if (
            kind is None
            or not isinstance(before_version, int)
            or isinstance(before_version, bool)
            or not isinstance(after_version, int)
            or isinstance(after_version, bool)
            or before_version < 1
            or after_version <= before_version
        ):
            raise _unavailable()
        public_changes.append(
            {
                "kind": kind,
                "before_display_version": before_version,
                "after_display_version": after_version,
                "before_value": _history_json_value(row.get("before_value")),
                "after_value": _history_json_value(row.get("after_value")),
            }
        )
    return {
        "available": True,
        "state": "available",
        "source": {
            "name": source_name,
            "url": _history_url(model.get("source_history_url"), nct_id=nct_id),
        },
        "coverage": _text(model.get("coverage_class"), maximum=80),
        "retrieved_at": _text(model.get("retrieved_at"), maximum=64),
        "versions": public_versions,
        "changes": public_changes,
    }


def _public_trial(
    snapshot: Mapping[str, Any],
    *,
    detail: bool,
    history_model: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    facts = snapshot.get("facts")
    attribution = snapshot.get("source_attribution")
    if not isinstance(facts, Mapping) or not isinstance(attribution, Mapping):
        raise _unavailable()
    official_title = _text(_fact(facts, "official_title"), maximum=2000)
    brief_title = _text(_fact(facts, "brief_title"), maximum=1000)
    title = official_title or brief_title
    locations = _fact(facts, "locations")
    site_count, countries = _countries(locations)
    row: dict[str, Any] = {
        "nct_id": snapshot["nct_id"],
        "title": title,
        "brief_title": brief_title,
        "status": _text(_fact(facts, "overall_status"), maximum=80),
        "study_type": _text(_fact(facts, "study_type"), maximum=80),
        "phases": _text_list(_fact(facts, "phases"), limit=12, maximum=80),
        "sponsor": _sponsor_value(_fact(facts, "sponsor")),
        "conditions": _text_list(_fact(facts, "conditions"), limit=100, maximum=512),
        "enrollment": _enrollment_value(_fact(facts, "enrollment")),
        "dates": {
            "start": _date_value(_fact(facts, "start_date")),
            "primary_completion": _date_value(_fact(facts, "primary_completion_date")),
            "completion": _date_value(_fact(facts, "completion_date")),
        },
        "updated_at": attribution.get("source_last_update_posted_at"),
        "retrieved_at": snapshot.get("retrieved_at"),
    }
    if detail:
        row.update(
            {
                "interventions": _named_rows(
                    _fact(facts, "interventions"), kind="intervention", limit=100
                ),
                "endpoints": {
                    "primary": _named_rows(
                        _fact(facts, "primary_outcomes"), kind="outcome", limit=100
                    ),
                    "secondary": _named_rows(
                        _fact(facts, "secondary_outcomes"), kind="outcome", limit=200
                    ),
                },
                "site_count": site_count,
                "countries": countries,
                "evidence": {
                    "provider": "ClinicalTrials.gov",
                    "record_id": snapshot["nct_id"],
                    "url": attribution.get("source_uri"),
                    "updated_at": attribution.get("source_last_update_posted_at"),
                    "retrieved_at": snapshot.get("retrieved_at"),
                    "coverage": snapshot.get("coverage_class"),
                },
                "history": _history_for_api(
                    history_model
                    if isinstance(history_model, Mapping)
                    else {"available": False, "unavailable_reason": "not_collected"},
                    nct_id=snapshot["nct_id"],
                ),
            }
        )
    return row


def _encode_cursor(offset: int) -> str:
    return base64.urlsafe_b64encode(f"v1:{offset}".encode("ascii")).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    if len(cursor) > 32 or not re.fullmatch(r"[A-Za-z0-9_-]+", cursor):
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    try:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        version, offset_text = raw.decode("ascii").split(":", 1)
        offset = int(offset_text)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS) from exc
    if version != "v1" or offset < 0 or offset > 100_000:
        raise HTTPException(status_code=400, detail="invalid cursor", headers=_PRIVATE_HEADERS)
    return offset


def _query_text(
    value: str | None,
    *,
    name: str,
    maximum: int,
) -> str | None:
    """Validate query text inside the route so every error keeps private headers."""

    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > maximum:
        raise HTTPException(
            status_code=400,
            detail=f"invalid {name}",
            headers=_PRIVATE_HEADERS,
        )
    return cleaned


def _query_limit(value: str) -> int:
    if not re.fullmatch(r"[0-9]{1,3}", value):
        raise HTTPException(
            status_code=400,
            detail="invalid limit",
            headers=_PRIVATE_HEADERS,
        )
    limit = int(value)
    if limit < 1 or limit > 250:
        raise HTTPException(
            status_code=400,
            detail="invalid limit",
            headers=_PRIVATE_HEADERS,
        )
    return limit


def _meta(projection: Any, health: Mapping[str, Any]) -> dict[str, Any]:
    generation = projection.generation
    return {
        "schema_version": "biocatalyst_api.v1",
        "as_of": generation.last_success_at,
        "source": {
            "name": "ClinicalTrials.gov",
            "dataset_timestamp_raw": generation.source_dataset_timestamp_raw,
        },
        "health": {
            "state": health.get("state"),
            "last_attempt_at": health.get("last_attempt_at"),
            "last_success_at": health.get("last_success_at"),
            "last_error_code": health.get("last_error_code"),
        },
        "coverage": {
            "class": "current_only",
            "configured": generation.configured_nct_count,
            "observed": generation.observed_nct_count,
        },
        "authority": dict(_AUTHORITY),
    }


@router.get("/api/biocatalyst/v1/health")
def health(_user: dict = Depends(require_site_full_user)) -> JSONResponse:
    projection, operational = _read_bundle()
    return _response(_meta(projection, operational))


@router.get("/api/biocatalyst/v1/trials")
def trials(
    q: str | None = None,
    phase: str | None = None,
    status: str | None = None,
    condition: str | None = None,
    sort: str = "updated_desc",
    cursor: str | None = None,
    limit: str = "100",
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    q = _query_text(q, name="query", maximum=100)
    phase = _query_text(phase, name="phase", maximum=40)
    status = _query_text(status, name="status", maximum=40)
    condition = _query_text(condition, name="condition", maximum=100)
    if sort not in {"updated_desc", "completion_asc", "nct"}:
        raise HTTPException(
            status_code=400,
            detail="invalid sort",
            headers=_PRIVATE_HEADERS,
        )
    page_limit = _query_limit(limit)
    projection, operational = _read_bundle()
    query = q.casefold().strip() if q else None
    phase_value = phase.casefold().strip() if phase else None
    status_value = status.casefold().strip() if status else None
    condition_value = condition.casefold().strip() if condition else None
    rows: list[dict[str, Any]] = []
    for snapshot in projection.trials:
        row = _public_trial(snapshot, detail=False)
        if query:
            sponsor = row.get("sponsor") or {}
            haystack = " ".join(
                [
                    str(row.get("nct_id") or ""),
                    str(row.get("title") or ""),
                    str(row.get("brief_title") or ""),
                    str(sponsor.get("name") or ""),
                    *row.get("conditions", []),
                ]
            ).casefold()
            if query not in haystack:
                continue
        if phase_value and phase_value not in {str(item).casefold() for item in row["phases"]}:
            continue
        if status_value and status_value != str(row.get("status") or "").casefold():
            continue
        if condition_value and not any(
            condition_value in str(item).casefold() for item in row["conditions"]
        ):
            continue
        rows.append(row)
    if sort == "nct":
        rows.sort(key=lambda item: item["nct_id"])
    elif sort == "completion_asc":
        rows.sort(
            key=lambda item: (
                str(((item.get("dates") or {}).get("primary_completion") or {}).get("date") or "9999-12-31"),
                item["nct_id"],
            )
        )
    else:
        rows.sort(key=lambda item: (str(item.get("updated_at") or ""), item["nct_id"]), reverse=True)
    offset = _decode_cursor(cursor)
    total = len(rows)
    page = rows[offset : offset + page_limit]
    next_offset = offset + len(page)
    payload = _meta(projection, operational)
    payload.update(
        {
            "query": {
                "q": q,
                "phase": phase,
                "status": status,
                "condition": condition,
                "sort": sort,
            },
            "pagination": {
                "limit": page_limit,
                "total": total,
                "next_cursor": _encode_cursor(next_offset) if next_offset < total else None,
            },
            "trials": page,
        }
    )
    return _response(payload)


@router.get("/api/biocatalyst/v1/trials/{nct_id}")
def trial_detail(
    nct_id: str,
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    if not _NCT_ID.fullmatch(nct_id):
        raise HTTPException(status_code=400, detail="invalid NCT ID", headers=_PRIVATE_HEADERS)
    projection, operational = _read_bundle()
    snapshot = next(
        (item for item in projection.trials if item.get("nct_id") == nct_id),
        None,
    )
    if snapshot is None:
        raise HTTPException(status_code=404, detail="trial not covered", headers=_PRIVATE_HEADERS)
    history_model = projection.history_models_by_nct.get(nct_id)
    if not isinstance(history_model, Mapping):
        raise _unavailable()
    payload = _meta(projection, operational)
    payload["trial"] = _public_trial(
        snapshot,
        detail=True,
        history_model=history_model,
    )
    return _response(payload)
