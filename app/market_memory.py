"""Authenticated, read-only API for the Market Memory product surface."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi import Path as ApiPath
from fastapi.responses import JSONResponse

from engine.neuralweb import market_memory

router = APIRouter(prefix="/api/market-memory/v1", tags=["market-memory"])

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent
_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
}


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Resolve the existing site-full entitlement lazily to avoid a cycle."""

    from app.main import require_user
    from app.paywall import enforce_site_full

    return enforce_site_full(require_user(authorization), always=True)


def _repo_root() -> Path:
    return Path(os.environ.get("MACRO_REPO", str(_DEFAULT_ROOT))).resolve()


def _response(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code, headers=_PRIVATE_HEADERS)


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
    ticker: str = ApiPath(min_length=1, max_length=20),
    _user: dict = Depends(require_site_full_user),  # noqa: B008 - FastAPI injection
) -> JSONResponse:
    """Return the existing Signal Episode Atlas receipts for one symbol."""

    try:
        payload = market_memory.symbol_context(_repo_root(), ticker)
    except market_memory.InvalidTicker as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers=_PRIVATE_HEADERS,
        ) from exc
    return _response(payload, status_code=200 if payload.get("available") else 404)
