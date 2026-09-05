"""Authenticated, read-only API for the F04-X1 ontology explorer.

`/ontology.html` is a public, discoverable shell that contains no current value.
Every current value reaches the researcher through this one route, behind the
existing authority — `app.main.require_user` then
`app.paywall.enforce_site_full(always=True)` — and nothing else. There is no
second identity path and no second entitlement check here; minting either is how
a paywall quietly stops being one.

`always=True` is deliberate: this surface fails closed in every environment
rather than following the staging switch, because the payload is premium in
staging too.

The private header set is applied through a route class rather than at the end
of the handler, because the outcomes most likely to leak are the ones that never
reach the handler at all — a 401 or 403 raised inside a dependency, or a 422
raised during request validation. Serving those cacheable and indexable is the
realistic failure, so they are covered first.

There is no fallback. When an owner artifact is missing or the artifacts cannot
be trusted together, the route returns a typed 503; it does not serve a
remembered answer, because a stale state read as the current one is precisely
the harm this product exists to prevent.
"""
from __future__ import annotations

import logging
import os
import re
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from engine.ontology_explorer import (
    DEFAULT_CHAIN,
    ERROR_SCHEMA_ID,
    SourceIncoherent,
    SourceUnavailable,
    compose_snapshot,
)

log = logging.getLogger(__name__)

_DEFAULT_ROOT = Path(__file__).resolve().parent.parent

_PRIVATE_HEADERS = {
    "Cache-Control": "private, no-store",
    "Vary": "Authorization",
    "X-Content-Type-Options": "nosniff",
    "X-Robots-Tag": "noindex, noarchive",
}

_CHAIN_PARAM_RE = re.compile(r"^[a-z0-9][a-z0-9_]{0,80}$")


class _PrivateOntologyRoute(APIRoute):
    """Stamp the private header set on every outcome, not just on success."""

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original = super().get_route_handler()

        async def private_handler(request: Request) -> Response:
            try:
                response = await original(request)
            except RequestValidationError as exc:
                return JSONResponse(
                    {"detail": jsonable_encoder(exc.errors())},
                    status_code=422,
                    headers=_PRIVATE_HEADERS,
                )
            except HTTPException as exc:
                headers = dict(exc.headers or {})
                headers.update(_PRIVATE_HEADERS)
                raise HTTPException(status_code=exc.status_code, detail=exc.detail,
                                    headers=headers) from exc
            response.headers.update(_PRIVATE_HEADERS)
            return response

        return private_handler


router = APIRouter(
    prefix="/api/ontology/explorer",
    tags=["ontology-explorer"],
    route_class=_PrivateOntologyRoute,
)


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Resolve the existing site-full entitlement lazily to avoid an import cycle."""
    from app.main import require_user  # noqa: PLC0415 — shared authority, not a second one
    from app.paywall import enforce_site_full  # noqa: PLC0415

    return enforce_site_full(require_user(authorization), always=True)


def _repo_root() -> Path:
    return Path(os.environ.get("MACRO_REPO", str(_DEFAULT_ROOT))).resolve()


def _unavailable(code: str, reason: str) -> HTTPException:
    """A typed failure the client can branch on — and nothing else.

    The reason is a stable machine token. No owner reading, no partial path and
    no remembered snapshot travels in an error body.
    """
    return HTTPException(
        503,
        detail={"schema": ERROR_SCHEMA_ID, "code": code, "reason": reason},
        headers=_PRIVATE_HEADERS,
    )


@router.get("/v1")
def read_snapshot(
    _user: dict = Depends(require_site_full_user),
    chain: str | None = Query(default=None, max_length=81),
) -> JSONResponse:
    """Return the current tenant-neutral `ontology_explorer_snapshot.v1`."""
    slug = chain or DEFAULT_CHAIN
    if not _CHAIN_PARAM_RE.match(slug):
        raise HTTPException(
            400,
            detail={"schema": ERROR_SCHEMA_ID, "code": "unknown_chain",
                    "reason": "chain_slug_rejected"},
            headers=_PRIVATE_HEADERS,
        )
    try:
        snapshot: dict[str, Any] = compose_snapshot(_repo_root(), chain=slug)
    except SourceUnavailable as exc:
        log.warning("ontology explorer source unavailable (%s)", exc)
        raise _unavailable("source_unavailable", str(exc).split(":", 1)[0]) from exc
    except SourceIncoherent as exc:
        log.warning("ontology explorer source incoherent (%s)", exc)
        raise _unavailable("source_incoherent", str(exc).split(":", 1)[0]) from exc
    return JSONResponse(snapshot, headers=_PRIVATE_HEADERS)
