"""Authenticated API transport for private Earnings Wire continuations."""
from __future__ import annotations

from collections.abc import Mapping
import threading
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.responses import JSONResponse

from engine.earnings_narrative.private_publication import (
    EarningsPrivatePublicationError,
    EarningsPrivateRecordNotFound,
    load_private_manifest,
    load_private_record,
    validate_slug,
)


router = APIRouter()

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}
_PRIVATE_HEADER_NAMES = frozenset(name.lower() for name in _PRIVATE_HEADERS)
_STORE_LOCK = threading.Lock()
_STORE: Any | None = None
_STORE_READY = False
_MANIFEST_LOCK = threading.Lock()
_MANIFEST_CACHE: tuple[int, dict[str, Any], float] | None = None
_MANIFEST_TTL_SECONDS = 30.0


def _private(response: Response) -> None:
    response.headers.update(_PRIVATE_HEADERS)


def _private_error(
    status_code: int,
    detail: Any,
    inherited: Mapping[str, str] | None = None,
) -> HTTPException:
    safe = {
        str(name): str(value)
        for name, value in dict(inherited or {}).items()
        if str(name).lower() not in _PRIVATE_HEADER_NAMES
    }
    return HTTPException(
        status_code=status_code,
        detail=detail,
        headers={**safe, **_PRIVATE_HEADERS},
    )


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Authenticate, then enforce the paid feature before opening private R2."""
    from app.main import require_user as _require_user  # noqa: PLC0415 - avoids mount cycle
    from app.paywall import enforce_site_full  # noqa: PLC0415

    try:
        return enforce_site_full(_require_user(authorization), always=True)
    except HTTPException as exc:
        raise _private_error(exc.status_code, exc.detail, exc.headers) from None


def _build_store():
    """Create one private Research Vault adapter per API process."""
    global _STORE, _STORE_READY
    with _STORE_LOCK:
        if _STORE_READY:
            return _STORE
        from engine.research_vault.r2_store import build_store  # noqa: PLC0415

        _STORE = build_store()
        _STORE_READY = True
        return _STORE


def _current_manifest(store: Any, *, force: bool = False) -> dict[str, Any]:
    """Short-cache only the receipt catalog; member bodies remain object reads."""
    global _MANIFEST_CACHE
    now = time.monotonic()
    key = id(store)
    with _MANIFEST_LOCK:
        hit = _MANIFEST_CACHE
        if not force and hit is not None and hit[0] == key and hit[2] > now:
            return hit[1]
    manifest = load_private_manifest(store)
    with _MANIFEST_LOCK:
        _MANIFEST_CACHE = (key, manifest, now + _MANIFEST_TTL_SECONDS)
    return manifest


def _reset_private_caches() -> None:
    """Hermetic test seam; production refreshes only through process lifetime/TTL."""
    global _STORE, _STORE_READY, _MANIFEST_CACHE
    with _STORE_LOCK:
        _STORE = None
        _STORE_READY = False
    with _MANIFEST_LOCK:
        _MANIFEST_CACHE = None


@router.get("/api/earnings/v1/records/{slug}")
def earnings_member_record(
    slug: str,
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> JSONResponse:
    """Return one exact member continuation from private R2 after entitlement."""
    del _user
    _private(response)
    try:
        normalized = validate_slug(slug)
    except EarningsPrivatePublicationError:
        raise _private_error(400, "invalid earnings record slug") from None
    try:
        store = _build_store()
        if store is None:
            raise EarningsPrivatePublicationError("private store unavailable")
        manifest = _current_manifest(store)
        try:
            payload = load_private_record(store, normalized, manifest=manifest)
        except EarningsPrivateRecordNotFound:
            # The private pointer is promoted before the corresponding public
            # shell is committed. A process may still hold the prior manifest
            # for up to 30 seconds, so force one pointer replay before treating
            # a valid newly deployed slug as absent.
            manifest = _current_manifest(store, force=True)
            payload = load_private_record(store, normalized, manifest=manifest)
    except EarningsPrivateRecordNotFound:
        raise _private_error(404, "earnings record not found") from None
    except Exception:  # noqa: BLE001 - storage details never cross the private API
        raise _private_error(503, "earnings evidence temporarily unavailable") from None
    return JSONResponse(content=payload, headers=_PRIVATE_HEADERS)


@router.get(
    "/api/earnings/v1/records/{remainder:path}",
    include_in_schema=False,
)
def earnings_member_record_private_not_found(
    remainder: str,
    response: Response,
    _user: dict = Depends(require_site_full_user),
) -> None:
    """Keep malformed and encoded-slash probes behind the paid private boundary."""
    del remainder, _user
    _private(response)
    raise _private_error(404, "earnings record not found")


__all__ = ["require_site_full_user", "router"]
