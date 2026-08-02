"""Authenticated read API for the Capital Structure observed-filing-state desk.

This router is deliberately a transport boundary, not another capital-structure
engine.  It reads only the compiler-verified ``projection.json`` artifact and
returns its observed filing-state records without deriving terms, capacity,
runway, dilution, severity, or financing probability at request time.

All routes require the paid ``site_full`` entitlement even while the global
paywall switch is in observe mode.  The artifact is public-safe, but issuer
research remains a private product surface: every response is private,
uncacheable, and noindex.
"""
from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response

from engine.capital_structure.projection import (
    PROJECTION_BUNDLE_SCHEMA,
    PROJECTION_SCHEMA,
    validate_projection_bundle,
)


router = APIRouter()

REPO = Path(os.environ.get("MACRO_REPO") or Path(__file__).resolve().parents[1])
PROJECTION_PATH = REPO / "data" / "capital_structure" / "projection.json"

_TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,9}$")
_LOCK = threading.Lock()
_CACHE: dict[str, Any] = {
    "path": None,
    "mtime_ns": None,
    "size": None,
    "payload": None,
}

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Authenticate, then apply the same always-on site_full gate as Forensics."""
    from app.main import require_user as _require_user  # noqa: PLC0415
    from app.paywall import enforce_site_full  # noqa: PLC0415

    try:
        return enforce_site_full(_require_user(authorization), always=True)
    except HTTPException as exc:
        # This dependency also runs in isolated router tests, before app.main's
        # API middleware has a chance to attach the cache/noindex policy.
        raise _private_error(exc.status_code, exc.detail, exc.headers) from None


def _private(response: Response) -> None:
    """Set the standalone-router response policy (main's API middleware reinforces it)."""
    response.headers.update(_PRIVATE_HEADERS)


def _private_error(
    status_code: int,
    detail: Any,
    extra_headers: dict[str, str] | None = None,
) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={**_PRIVATE_HEADERS, **(extra_headers or {})},
    )


def _unavailable(detail: str = "capital structure observed filing state unavailable") -> HTTPException:
    return _private_error(503, detail)


def _reset_cache() -> None:
    """Test seam; a failed reload is intentionally never cached."""
    with _LOCK:
        _CACHE.update(path=None, mtime_ns=None, size=None, payload=None)


def _records(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Validate the API's identity assumptions on top of the serialized contract."""
    records = payload.get("records")
    if not isinstance(records, list):
        raise _unavailable("capital structure observed filing state invalid")

    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for record in records:
        if not isinstance(record, dict) or record.get("schema") != PROJECTION_SCHEMA:
            raise _unavailable("capital structure observed filing state invalid")
        issuer_id = record.get("issuer_id")
        if not isinstance(issuer_id, str) or not issuer_id or issuer_id in seen:
            # A ticker may legitimately map to more than one stable issuer, but
            # canonical issuer IDs may never collide.  Do not pick a winner.
            raise _unavailable("capital structure observed filing state invalid")
        seen.add(issuer_id)
        normalized.append(record)
    return sorted(normalized, key=lambda item: str(item["issuer_id"]))


def _load() -> dict[str, Any]:
    """Read one validated canonical artifact; absent, stale-invalid, and unavailable fail closed."""
    try:
        stat = PROJECTION_PATH.stat()
    except OSError as exc:
        raise _unavailable() from exc

    with _LOCK:
        if (
            _CACHE["payload"] is not None
            and _CACHE["path"] == str(PROJECTION_PATH)
            and _CACHE["mtime_ns"] == stat.st_mtime_ns
            and _CACHE["size"] == stat.st_size
        ):
            return _CACHE["payload"]

        try:
            value = json.loads(PROJECTION_PATH.read_text(encoding="utf-8"))
            if not isinstance(value, dict) or value.get("schema") != PROJECTION_BUNDLE_SCHEMA:
                raise ValueError("schema mismatch")
            validate_projection_bundle(value)
            _records(value)
            coverage = value.get("coverage")
            if not isinstance(coverage, dict) or coverage.get("state") == "unavailable":
                raise ValueError("unavailable artifact")
        except Exception as exc:  # noqa: BLE001 — source artifact is an all-or-nothing boundary
            raise _unavailable() from exc

        _CACHE.update(
            path=str(PROJECTION_PATH),
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            payload=value,
        )
        return value


def _envelope(bundle: dict[str, Any]) -> dict[str, Any]:
    """Shared observed-state receipt carried by every API response."""
    return {
        "schema": bundle["schema"],
        "projection_version": bundle["projection_version"],
        "generation_id": bundle["generation_id"],
        "as_of": bundle["as_of"],
        "generated_at": bundle["generated_at"],
        "authority": bundle["authority"],
        "coverage": bundle["coverage"],
        "unavailable": bundle["unavailable"],
    }


def _overview_record(record: dict[str, Any]) -> dict[str, Any]:
    """A compact issuer card, directly selected from the projection—not computed."""
    return {
        "issuer_id": record["issuer_id"],
        "identity": record["identity"],
        "latest_observed_event": record["latest_observed_event"],
        "what_changed": record["what_changed"],
        "coverage": record["coverage"],
        "authority": record["authority"],
        "unavailable": record["unavailable"],
    }


def _issuer(bundle: dict[str, Any], issuer_id: str) -> dict[str, Any]:
    record = next(
        (row for row in _records(bundle) if row["issuer_id"] == issuer_id),
        None,
    )
    if record is None:
        raise _private_error(404, "issuer not covered")
    return record


def _page_after_id(rows: list[dict[str, Any]], cursor: str | None, key: str) -> tuple[list[dict[str, Any]], str | None]:
    """Stable keyset pagination; unknown cursors never silently restart a listing."""
    if cursor is None:
        return rows, None
    index = next((idx for idx, row in enumerate(rows) if row.get(key) == cursor), None)
    if index is None:
        raise _private_error(400, "invalid cursor")
    return rows[index + 1 :], cursor


@router.get("/api/capital-structure/v1/coverage")
def coverage(response: Response, _user: dict = Depends(require_site_full_user)) -> dict[str, Any]:
    """Coverage/freshness receipt for observed filing state; no inferred risk fields."""
    _private(response)
    return _envelope(_load())


@router.get("/api/capital-structure/v1/overview")
def overview(
    response: Response,
    cursor: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=25, ge=1, le=100),
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Stable-issuer paginated overview for the observed filing-state desk."""
    _private(response)
    bundle = _load()
    candidates, requested_cursor = _page_after_id(_records(bundle), cursor, "issuer_id")
    page_records = candidates[:limit]
    has_more = len(candidates) > len(page_records)
    return _envelope(bundle) | {
        "page": {
            "cursor": requested_cursor,
            "next_cursor": page_records[-1]["issuer_id"] if has_more and page_records else None,
            "limit": limit,
            "returned": len(page_records),
            "total": len(_records(bundle)),
        },
        "records": [_overview_record(record) for record in page_records],
    }


@router.get("/api/capital-structure/v1/issuers/resolve")
def resolve_issuer(
    response: Response,
    ticker: str = Query(min_length=1, max_length=16),
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Resolve an observed ticker without treating a ticker as a stable issuer identity."""
    _private(response)
    normalized = ticker.strip().upper()
    if not _TICKER_RE.fullmatch(normalized):
        raise _private_error(400, "invalid ticker")

    bundle = _load()
    matches = []
    for record in _records(bundle):
        identity = record["identity"]
        tickers = {
            str(identity.get("ticker") or "").upper(),
            *(str(value).upper() for value in identity.get("observed_tickers") or []),
        }
        if normalized in tickers:
            matches.append(record)

    if not matches:
        raise _private_error(404, "ticker not covered")
    if len(matches) > 1:
        raise _private_error(
            status_code=409,
            detail={
                "code": "ambiguous_ticker",
                "ticker": normalized,
                "matches": [
                    {"issuer_id": record["issuer_id"], "identity": record["identity"]}
                    for record in matches
                ],
            },
        )

    return _envelope(bundle) | {
        "query": {"ticker": normalized},
        "issuer": _overview_record(matches[0]),
    }


@router.get("/api/capital-structure/v1/issuers/{issuer_id}")
def issuer_dossier(
    issuer_id: str,
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Return one issuer's observed-state dossier (timeline remains paginated separately)."""
    _private(response)
    bundle = _load()
    record = _issuer(bundle, issuer_id)
    return _envelope(bundle) | {"issuer": _overview_record(record)}


@router.get("/api/capital-structure/v1/issuers/{issuer_id}/events")
def issuer_events(
    issuer_id: str,
    response: Response,
    cursor: str | None = Query(default=None, min_length=1, max_length=128),
    limit: int = Query(default=25, ge=1, le=100),
    _user: dict = Depends(require_site_full_user),
) -> dict[str, Any]:
    """Paginate the artifact's issuer timeline, including its bounded SEC evidence refs."""
    _private(response)
    bundle = _load()
    record = _issuer(bundle, issuer_id)
    timeline = list(record["timeline"])
    candidates, requested_cursor = _page_after_id(timeline, cursor, "event_id")
    events = candidates[:limit]
    has_more = len(candidates) > len(events)
    return _envelope(bundle) | {
        "issuer": {
            "issuer_id": record["issuer_id"],
            "identity": record["identity"],
            "coverage": record["coverage"],
            "authority": record["authority"],
            "unavailable": record["unavailable"],
        },
        "page": {
            "cursor": requested_cursor,
            "next_cursor": events[-1]["event_id"] if has_more and events else None,
            "limit": limit,
            "returned": len(events),
            "total": len(timeline),
        },
        "events": events,
    }


__all__ = ["router", "require_site_full_user"]
