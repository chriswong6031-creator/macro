"""Authenticated, read-only API for the Market Memory product surface."""

from __future__ import annotations

import os
import time
from collections import deque
from collections.abc import Awaitable, Callable
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi import Path as ApiPath
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from engine.neuralweb import market_memory

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
}
_SYMBOL_USER_LIMIT = 60
_SYMBOL_PEER_LIMIT = 600
_SYMBOL_RATE_WINDOW_SECONDS = 60.0
_SYMBOL_RATE_MAX_KEYS = 8_192
_SYMBOL_TRUSTED_PEER_HEADER = "x-mm-peer"
_symbol_rate_lock = Lock()
_symbol_rate_buckets: dict[str, deque[float]] = {}


class _PrivateMarketMemoryRoute(APIRoute):
    """Apply private-cache headers even when a dependency rejects the request."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def private_handler(request: Request) -> Response:
            try:
                response = await original(request)
            except HTTPException as exc:
                headers = dict(exc.headers or {})
                headers.update(_PRIVATE_HEADERS)
                raise HTTPException(
                    status_code=exc.status_code,
                    detail=exc.detail,
                    headers=headers,
                ) from exc
            response.headers.update(_PRIVATE_HEADERS)
            return response

        return private_handler


router = APIRouter(
    prefix="/api/market-memory/v1",
    tags=["market-memory"],
    route_class=_PrivateMarketMemoryRoute,
)


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Resolve the existing site-full entitlement lazily to avoid a cycle."""

    from app.main import require_user
    from app.paywall import enforce_site_full

    return enforce_site_full(require_user(authorization), always=True)


def _repo_root() -> Path:
    return Path(os.environ.get("MACRO_REPO", str(_DEFAULT_ROOT))).resolve()


def _response(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_PRIVATE_HEADERS)


def _book_symbol_rate(key: str, *, limit: int, now: float) -> bool:
    """Book one bounded process-local rate slot. Caller holds the lock."""

    bucket = _symbol_rate_buckets.get(key)
    if bucket is None:
        if len(_symbol_rate_buckets) >= _SYMBOL_RATE_MAX_KEYS:
            oldest = min(
                _symbol_rate_buckets,
                key=lambda item: (
                    _symbol_rate_buckets[item][-1]
                    if _symbol_rate_buckets[item]
                    else float("-inf")
                ),
            )
            del _symbol_rate_buckets[oldest]
        bucket = deque()
        _symbol_rate_buckets[key] = bucket
    cutoff = now - _SYMBOL_RATE_WINDOW_SECONDS
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(now)
    return True


def _allow_symbol_request(
    request: Request, user: dict, *, now: float | None = None
) -> bool:
    """Consume independent entitled-user and trusted-peer request budgets."""

    current = time.monotonic() if now is None else now
    user_id = str(user.get("id") or user.get("sub") or "unknown")[:160]
    peer = str(
        request.headers.get(_SYMBOL_TRUSTED_PEER_HEADER)
        or (request.client.host if request.client else "unknown")
    )[:160]
    with _symbol_rate_lock:
        user_ok = _book_symbol_rate(
            f"user:{user_id}", limit=_SYMBOL_USER_LIMIT, now=current
        )
        peer_ok = _book_symbol_rate(
            f"peer:{peer}", limit=_SYMBOL_PEER_LIMIT, now=current
        )
    return user_ok and peer_ok


def _reset_symbol_rate_limit_for_tests() -> None:
    with _symbol_rate_lock:
        _symbol_rate_buckets.clear()


@router.get("/macro")
def macro(
    limit: int = Query(default=6, ge=1, le=8),
    _user: dict = Depends(require_site_full_user),  # noqa: B008 - FastAPI injection
) -> JSONResponse:
    """Return today's macro-state query and a bounded set of dated episodes."""

    payload = market_memory.macro_context(_repo_root(), limit=limit)
    return _response(payload, status_code=200 if payload.get("available") else 503)


@router.get("/symbol/{ticker}")
def symbol(
    request: Request,
    ticker: str = ApiPath(min_length=1, max_length=20),
    _user: dict = Depends(require_site_full_user),  # noqa: B008 - FastAPI injection
) -> JSONResponse:
    """Return the existing Signal Episode Atlas receipts for one symbol."""

    if not _allow_symbol_request(request, _user):
        raise HTTPException(
            status_code=429,
            detail="Too many Market Memory symbol requests. Please retry shortly.",
            headers={"Retry-After": str(int(_SYMBOL_RATE_WINDOW_SECONDS))},
        )
    try:
        payload = market_memory.symbol_context(_repo_root(), ticker)
    except market_memory.InvalidTicker as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers=_PRIVATE_HEADERS,
        ) from exc
    return _response(payload, status_code=200 if payload.get("available") else 404)
