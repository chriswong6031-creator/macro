"""Public, context-only Company Intelligence API boundary.

The producer's verified reader already follows the immutable public R2
``marker -> generation -> company object`` chain and emits a deliberately
bounded projection.  This router gives the static Mastermind ticker dossiers a
same-origin way to read that projection without granting the browser access to
the reader's network controls or broadening its authority.

This endpoint is explanatory only.  It cannot create a signal, ranking,
position size, gate, or escalation.
"""
from __future__ import annotations

from collections import deque
import logging
import math
from threading import Lock
import time
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Query, Request, Response

from engine.company_intelligence.contracts import ContractError, safe_ticker
from engine.neuralweb import company_intelligence_reader as _reader


router = APIRouter()
log = logging.getLogger("macro.api.company_intelligence")

# This is intentionally *not* the reader's public contract.  The reader has a
# larger, authenticated/internal context contract used by Neural Web and
# Terminal.  This browser endpoint is the no-login teaser: enough verified
# information to make a company dossier useful, but not enough history or
# transport lineage to enumerate the underlying corpus.
#
# Keep this boundary recursively allowlisted.  Allowing ``latest_event`` as a
# top-level mapping would otherwise let a future reader field pass through to
# the browser by accident.
_TEASER_SCALAR_KEYS = (
    "available",
    "ticker",
    "company",
    "schema",
    "generated_at",
    "status",
    "is_context_only",
    "display_only",
    "authority",
    "untrusted_source_data",
    "latest_event",
    "note",
)
_COMPANY_KEYS = ("ticker", "display_name", "exchange")
_EVENT_SCALAR_KEYS = (
    "event_id",
    "fiscal_year",
    "fiscal_quarter",
    "call_date",
    "summary",
    "key_quote",
    "claim_citations_pending",
)
_PUBLIC_METRIC_KEYS = (
    "analyst_criticism",
    "analysts_count",
    "call_positivity",
    "combined",
    "confidence",
    "eps_growth_pct",
    "future_outlook",
    "gross_margin_pct",
    "management_confidence",
    "performance",
    "questions_count",
    "revenue_growth_pct",
    "sentiment",
)
_SOURCE_KEYS = ("kind", "status", "citation_precision")
_FIELD_LINEAGE_SCALAR_KEYS = ("summary", "key_quote")
_FIELD_LINEAGE_LIST_KEYS = (
    ("positive_highlights", 3),
    ("negative_highlights", 3),
    ("highlights", 6),
)
_NOT_COVERED_NOTE = "Company Intelligence does not cover this ticker"

# A teaser page can be CDN-cached safely because it contains no per-user data.
# Errors deliberately remain under app.main's default ``private, no-store``.
_PUBLIC_CACHE_CONTROL = "public, max-age=300, stale-while-revalidate=900"

# Keep the inexpensive unauthenticated endpoint from becoming an R2 fetch
# amplifier.  Client-IP headers are attacker-suppliable by the time a request
# reaches the app, so this intentionally uses two independent budgets:
#
# * the claimed client identity is tight (60/min) and protects normal traffic;
# * the Caddy-injected TCP peer is looser (600/min) and catches someone who
#   rotates claimed EO/CF headers to burn a fresh client bucket every request.
#
# ``X-MM-Peer`` is trusted specifically because the production Caddy contract
# uses ``header_up`` to overwrite any inbound value before proxying.  It is not
# an application-level authentication header.  The CDN cache is the primary
# steady-state protection; these bounded process-local counters are the origin
# backstop.
_RATE_LIMIT_REQUESTS = 60
_PEER_RATE_LIMIT_REQUESTS = 600
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_KEYS = 8_192
_TRUSTED_PEER_HEADER = "x-mm-peer"
_rate_limit_lock = Lock()
_rate_limit_buckets: dict[str, deque[float]] = {}


def _is_public_scalar(value: Any) -> bool:
    """Return whether ``value`` is a finite JSON scalar (or null)."""
    return (
        value is None
        or isinstance(value, (str, bool, int))
        or (isinstance(value, float) and math.isfinite(value))
    )


def _scalar_projection(raw: Mapping[str, Any], keys: tuple[str, ...]) -> dict[str, Any]:
    """Copy explicitly named scalar fields and nothing else."""
    return {
        key: raw[key]
        for key in keys
        if key in raw and _is_public_scalar(raw[key])
    }


def _string_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    return [item for item in value[:limit] if isinstance(item, str)]


def _company_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return _scalar_projection(raw, _COMPANY_KEYS)


def _metric_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    return _scalar_projection(raw, _PUBLIC_METRIC_KEYS)


def _source_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    # Do not expose source URL, receipt/hash, source_ref, or storage locator.
    # The three retained fields are semantic evidence labels only.
    return _scalar_projection(raw, _SOURCE_KEYS)


def _field_lineage_projection(value: Any, *, tags: list[str]) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    projected = _scalar_projection(raw, _FIELD_LINEAGE_SCALAR_KEYS)
    if isinstance(raw.get("metrics"), Mapping):
        projected["metrics"] = _scalar_projection(raw["metrics"], _PUBLIC_METRIC_KEYS)
    for key, limit in _FIELD_LINEAGE_LIST_KEYS:
        if key in raw:
            projected[key] = _string_list(raw[key], limit=limit)
    tag_lineage = raw.get("tags")
    if isinstance(tag_lineage, Mapping):
        projected["tags"] = {
            tag: tag_lineage[tag]
            for tag in tags[:24]
            if tag in tag_lineage and _is_public_scalar(tag_lineage[tag])
        }
    return projected


def _event_projection(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, Mapping) else {}
    projected = _scalar_projection(raw, _EVENT_SCALAR_KEYS)
    for key, limit in (
        ("positive_highlights", 3),
        ("negative_highlights", 3),
        ("tags", 24),
    ):
        if key in raw:
            projected[key] = _string_list(raw[key], limit=limit)
    tags = projected.get("tags") if isinstance(projected.get("tags"), list) else []
    if isinstance(raw.get("metrics"), Mapping):
        projected["metrics"] = _metric_projection(raw["metrics"])
    if isinstance(raw.get("field_lineage"), Mapping):
        projected["field_lineage"] = _field_lineage_projection(raw["field_lineage"], tags=tags)
    if isinstance(raw.get("previous_event_deltas"), Mapping):
        projected["previous_event_deltas"] = _metric_projection(raw["previous_event_deltas"])
    if isinstance(raw.get("sources"), (list, tuple)):
        projected["sources"] = [
            _source_projection(source)
            for source in raw["sources"][:3]
            if isinstance(source, Mapping)
        ]
    return projected


def _public_projection(result: Mapping[str, Any]) -> dict[str, Any]:
    """Build a recursive, single-event public teaser projection.

    ``history``, topic rollups, completeness diagnostics, and every receipt or
    source locator are intentionally absent.  This endpoint must remain a
    teaser even if its internal reader receives a broader context object.
    """
    projected = _scalar_projection(result, tuple(
        key for key in _TEASER_SCALAR_KEYS if key not in {"company", "latest_event"}
    ))
    if "company" in result:
        projected["company"] = _company_projection(result["company"])
    if "latest_event" in result:
        projected["latest_event"] = (
            _event_projection(result["latest_event"])
            if isinstance(result["latest_event"], Mapping)
            else None
        )
    return projected


def _claimed_client_identity(request: Request) -> str:
    """Return the claimed edge-client identity, with a safe local fallback.

    EO/CF headers are useful for a fair per-visitor bucket but are not trusted
    for a hard abuse boundary — an attacker at the origin can rotate them.  We
    intentionally omit arbitrary ``X-Forwarded-For`` chains, which are even
    easier to spoof before a proxy normalizes them.
    """
    for header in ("eo-client-ip", "cf-connecting-ip"):
        value = str(request.headers.get(header) or "").strip()
        if value:
            return value[:128]
    return str(request.client.host if request.client else "unknown")[:128]


def _trusted_peer_identity(request: Request) -> str:
    """Return the Caddy-overwritten peer key, or a local-development fallback."""
    peer = str(request.headers.get(_TRUSTED_PEER_HEADER) or "").strip()
    if peer:
        return peer[:128]
    return str(request.client.host if request.client else "unknown")[:128]


def _book_rate_limit(key: str, *, limit: int, current: float, cutoff: float) -> bool:
    """Book one bounded rate slot. Caller must hold ``_rate_limit_lock``."""
    bucket = _rate_limit_buckets.get(key)
    if bucket is None:
        if len(_rate_limit_buckets) >= _RATE_LIMIT_MAX_KEYS:
            # Bounded global memory: discard the least-recently-used bucket.
            # This never relaxes an existing client's/peer's current limit.
            oldest = min(_rate_limit_buckets, key=lambda item: _rate_limit_buckets[item][-1])
            del _rate_limit_buckets[oldest]
        bucket = deque()
        _rate_limit_buckets[key] = bucket
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()
    if len(bucket) >= limit:
        return False
    bucket.append(current)
    return True


def _allow_request(request: Request, *, now: float | None = None) -> bool:
    """Consume both claimed-client and trusted-peer request slots.

    Both buckets are booked even when the first has already refused.  That is
    what prevents a spray of fabricated client headers from avoiding the peer
    backstop.
    """
    current = time.monotonic() if now is None else now
    cutoff = current - _RATE_LIMIT_WINDOW_SECONDS
    client = _claimed_client_identity(request)
    peer = _trusted_peer_identity(request)
    with _rate_limit_lock:
        ok_client = _book_rate_limit(
            f"client:{client}", limit=_RATE_LIMIT_REQUESTS, current=current, cutoff=cutoff,
        )
        ok_peer = _book_rate_limit(
            f"peer:{peer}", limit=_PEER_RATE_LIMIT_REQUESTS, current=current, cutoff=cutoff,
        )
        return ok_client and ok_peer


def _reset_rate_limit_for_tests() -> None:
    """Reset process-local limiter state for isolated API tests."""
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


def _normalized_ticker_or_422(ticker: str) -> str:
    try:
        return safe_ticker(ticker)
    except ContractError as exc:
        raise HTTPException(
            status_code=422,
            detail="ticker must be a listed symbol using A-Z, 0-9, dots, or dashes",
        ) from exc


@router.get("/api/company-intelligence/{ticker}")
def company_intelligence(
    ticker: str,
    request: Request,
    response: Response,
    # Retained temporarily for existing static dossiers.  It is accepted for
    # compatibility but never expands the public response or reader request.
    limit: int = Query(default=1, ge=1, le=12),
) -> dict[str, Any]:
    """Return one verified Company Intelligence event as a public teaser.

    A syntactically valid ticker missing from the immutable generation is a
    stable 404.  A source, verification, or projection failure is intentionally
    a 503: returning an empty-looking 200 would make a temporary upstream fault
    indistinguishable from an absence of earnings context.

    Successes set an explicit short public cache policy because the projection
    is non-personal and deliberately contains no corpus locator.  The global
    API middleware keeps errors ``private, no-store``.
    """
    if not _allow_request(request):
        raise HTTPException(
            status_code=429,
            detail="Too many Company Intelligence requests. Please retry shortly.",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_SECONDS))},
        )
    normalized = _normalized_ticker_or_422(ticker)
    # Never request or expose more than the one latest event on this anonymous
    # route.  ``limit`` remains parsed only to avoid a hard frontend break.
    del limit
    try:
        result = _reader.read_company_intelligence({"ticker": normalized, "limit": 1})
    except Exception:  # noqa: BLE001 - an API source boundary must fail closed
        log.exception("company intelligence reader raised for %s", normalized)
        raise HTTPException(
            status_code=503,
            detail="Company Intelligence is temporarily unavailable.",
        ) from None

    if result.get("available") is True:
        response.headers["Cache-Control"] = _PUBLIC_CACHE_CONTROL
        return _public_projection(result)

    # The reader has already normalized and verified the ticker.  Its one
    # explicit coverage absence is safe to expose as a stable not-found state;
    # every other unavailable result represents failed retrieval or validation.
    if result.get("note") == _NOT_COVERED_NOTE:
        raise HTTPException(
            status_code=404,
            detail=f"Company Intelligence is not available for {normalized}.",
        )

    log.warning("company intelligence unavailable for %s: %s", normalized, result.get("note"))
    raise HTTPException(
        status_code=503,
        detail="Company Intelligence is temporarily unavailable.",
    )
