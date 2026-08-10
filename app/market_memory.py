"""Authenticated, read-only API for the Market Memory product surface."""

from __future__ import annotations

import copy
import ipaddress
import json
import os
import socket
import time
import urllib.parse
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from concurrent.futures import CancelledError, Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeoutError
from pathlib import Path
from threading import BoundedSemaphore, Lock
from typing import Any

import yaml
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi import Path as ApiPath
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from engine.neuralweb import market_memory, market_memory_pit

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
_SYMBOL_DATA_CACHE_TTL_SECONDS = 300.0
_SYMBOL_DATA_CACHE_MAX_ENTRIES = 256
_SYMBOL_FETCH_NEGATIVE_TTL_SECONDS = 5.0
_SYMBOL_FETCH_CONNECT_TIMEOUT_SECONDS = 2.0
_SYMBOL_FETCH_READ_TIMEOUT_SECONDS = 3.0
_SYMBOL_FETCH_TIMEOUT_SECONDS = (
    _SYMBOL_FETCH_CONNECT_TIMEOUT_SECONDS,
    _SYMBOL_FETCH_READ_TIMEOUT_SECONDS,
)
_SYMBOL_FETCH_TOTAL_DEADLINE_SECONDS = 6.0
_SYMBOL_FETCH_CALLER_GRACE_SECONDS = 0.25
_SYMBOL_FETCH_MAX_INFLIGHT = 6
_SYMBOL_FETCH_BUSY_RETRY_SECONDS = 2
_SYMBOL_FETCH_USER_AGENT = "MastermindMarketMemory/1.0"
_symbol_rate_lock = Lock()
_symbol_rate_buckets: dict[str, deque[float]] = {}
_symbol_base_lock = Lock()
_symbol_data_lock = Lock()
_symbol_data_cache: dict[
    tuple[str, str], tuple[float, dict[str, Any]]
] = {}
_symbol_negative_cache: dict[tuple[str, str], tuple[float, bool]] = {}
_symbol_fetch_inflight: dict[tuple[str, str], Future[dict[str, Any]]] = {}
_symbol_base_cache: dict[tuple[str, str, int, int], str] = {}
_symbol_fetch_slots = BoundedSemaphore(_SYMBOL_FETCH_MAX_INFLIGHT)
_symbol_fetch_executor = ThreadPoolExecutor(
    max_workers=_SYMBOL_FETCH_MAX_INFLIGHT,
    thread_name_prefix="market-memory-stockdata",
)


class _PrivateMarketMemoryRoute(APIRoute):
    """Apply private-cache headers even when a dependency rejects the request."""

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


def _response(
    payload: dict[str, Any],
    *,
    status_code: int = 200,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    private_headers = {**_PRIVATE_HEADERS, **dict(headers or {})}
    return JSONResponse(payload, status_code=status_code, headers=private_headers)


def _pit_reader() -> market_memory_pit.FileAsKnownAtReader:
    root = market_memory_pit.default_store_root(_repo_root())
    return market_memory_pit.FileAsKnownAtReader(root)


def _stored_context_response(
    stored: market_memory_pit.StoredMarketMemoryContext,
) -> JSONResponse:
    receipt = stored.capture_receipt
    return _response(
        stored.response_payload(),
        headers={
            "ETag": f'"{receipt["packet_sha256"]}"',
            "X-Market-Memory-Capture-Id": receipt["capture_id"],
            "X-Market-Memory-Query-Id": receipt["query_id"],
        },
    )


def _exact_pit_query(request: Request) -> dict[str, str]:
    expected = {
        "subject_id",
        "instrument_id",
        "event_time",
        "as_known_at",
        "mode",
    }
    items = list(request.query_params.multi_items())
    keys = [key for key, _value in items]
    if set(keys) != expected or len(keys) != len(expected):
        raise market_memory_pit.MarketMemoryQueryError(
            "exact PIT query requires subject_id, instrument_id, event_time, as_known_at, and mode once each"
        )
    return {key: value for key, value in items}


class _SymbolDataError(RuntimeError):
    """The public stockdata object failed transport or projection checks."""


class _SymbolDataBusy(_SymbolDataError):
    """The bounded stockdata fetch lane is already occupied."""


class _SymbolDataNotFound(_SymbolDataError):
    """The canonical public stockdata object does not exist."""


def _origin_tuple(parsed: urllib.parse.SplitResult) -> tuple[str, str, int]:
    try:
        port = parsed.port
    except ValueError as exc:
        raise _SymbolDataError("stockdata origin has an invalid port") from exc
    host = (parsed.hostname or "").rstrip(".").lower()
    if not host:
        raise _SymbolDataError("stockdata origin has no host")
    return parsed.scheme.lower(), host, port or 443


def _is_public_address(address: str) -> bool:
    try:
        return ipaddress.ip_address(address).is_global
    except ValueError:
        return False


def _require_public_hostname(host: str) -> None:
    normalized = host.rstrip(".").lower()
    if normalized in {"localhost", "localhost.localdomain"} or normalized.endswith(
        ".localhost"
    ):
        raise _SymbolDataError("stockdata origin must not be local")
    try:
        literal = ipaddress.ip_address(normalized)
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise _SymbolDataError("stockdata origin must not be private")
        return
    try:
        records = socket.getaddrinfo(normalized, None, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise _SymbolDataError("stockdata origin cannot be resolved") from exc
    addresses = {
        str(record[4][0])
        for record in records
        if len(record) >= 5 and isinstance(record[4], tuple) and record[4]
    }
    if not addresses or any(not _is_public_address(address) for address in addresses):
        raise _SymbolDataError("stockdata origin must resolve only to public hosts")


def _stockdata_base(root: Path) -> str:
    env_base = os.environ.get("R2_PUBLIC_BASE", "").strip()
    config_path = Path(root) / "config.yml"
    config_mtime_ns = -1
    config_size = -1
    if not env_base:
        try:
            stat = config_path.stat()
            config_mtime_ns = stat.st_mtime_ns
            config_size = stat.st_size
        except OSError:
            pass
    cache_key = (
        str(Path(root).resolve()),
        env_base,
        config_mtime_ns,
        config_size,
    )
    with _symbol_base_lock:
        cached = _symbol_base_cache.get(cache_key)
        if cached is not None:
            return cached
        raw = env_base
        if not raw:
            try:
                with config_path.open(encoding="utf-8") as handle:
                    config = yaml.safe_load(handle)
                if isinstance(config, Mapping):
                    plane = config.get("r2_data_plane")
                    if isinstance(plane, Mapping):
                        raw = str(plane.get("public_base") or "").strip()
            except (OSError, TypeError, ValueError, yaml.YAMLError):
                raw = ""
        raw = raw.rstrip("/")
        parsed = urllib.parse.urlsplit(raw)
        if (
            parsed.scheme.lower() != "https"
            or not parsed.netloc
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise _SymbolDataError("stockdata origin is not a safe HTTPS URL")
        _origin_tuple(parsed)
        _symbol_base_cache.clear()
        _symbol_base_cache[cache_key] = raw
        return raw


def _stockdata_url(base: str, symbol: str) -> str:
    safe_symbol = symbol.replace("=", "_").replace("^", "_")
    name = urllib.parse.quote(f"{safe_symbol}.json", safe="._-")
    return f"{base}/stockdata/{name}"


def _reject_duplicate_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key")
        result[key] = value
    return result


def _fetch_stock_record(base: str, symbol: str) -> dict[str, Any]:
    try:
        import requests as http
    except ImportError as exc:
        raise _SymbolDataError("stockdata HTTP client is unavailable") from exc
    deadline = time.monotonic() + _SYMBOL_FETCH_TOTAL_DEADLINE_SECONDS
    url = _stockdata_url(base, symbol)
    expected_origin = _origin_tuple(urllib.parse.urlsplit(url))
    _require_public_hostname(expected_origin[1])
    try:
        response = http.get(
            url,
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "User-Agent": _SYMBOL_FETCH_USER_AGENT,
            },
            timeout=_SYMBOL_FETCH_TIMEOUT_SECONDS,
            stream=True,
            allow_redirects=False,
        )
        with response:
            response_url = urllib.parse.urlsplit(
                str(getattr(response, "url", url) or url)
            )
            status = int(getattr(response, "status_code", 0) or 0)
            if (
                getattr(response, "is_redirect", False)
                or 300 <= status < 400
                or _origin_tuple(response_url) != expected_origin
            ):
                raise _SymbolDataError("stockdata source redirected or changed host")
            if status == 404:
                raise _SymbolDataNotFound("stockdata object was not found")
            response.raise_for_status()
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if not content_type.startswith("application/json"):
                raise _SymbolDataError("stockdata source is not JSON")
            encoding = str(response.headers.get("Content-Encoding") or "identity")
            if encoding.lower() != "identity":
                raise _SymbolDataError("compressed stockdata is not accepted")
            content_length = response.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared_length = int(content_length)
                    if declared_length < 0:
                        raise ValueError
                    if declared_length > market_memory._MAX_STOCKDATA_BYTES:
                        raise _SymbolDataError("stockdata exceeds the safe size bound")
                except ValueError:
                    raise _SymbolDataError(
                        "stockdata has an invalid Content-Length"
                    ) from None
            chunks: list[bytes] = []
            used = 0
            for chunk in response.iter_content(chunk_size=65_536):
                if time.monotonic() > deadline:
                    raise _SymbolDataError("stockdata fetch exceeded its total deadline")
                if not chunk:
                    continue
                used += len(chunk)
                if used > market_memory._MAX_STOCKDATA_BYTES:
                    raise _SymbolDataError("stockdata exceeds the safe size bound")
                chunks.append(chunk)
            if time.monotonic() > deadline:
                raise _SymbolDataError("stockdata fetch exceeded its total deadline")
            body = b"".join(chunks)
    except _SymbolDataError:
        raise
    except http.RequestException as exc:
        raise _SymbolDataError("stockdata source unavailable") from exc

    def reject_nonfinite(token: str) -> None:
        raise ValueError(f"non-finite JSON token {token}")

    try:
        record = json.loads(
            body.decode("utf-8"),
            parse_constant=reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise _SymbolDataError("stockdata is not strict JSON") from exc
    if not isinstance(record, dict):
        raise _SymbolDataError("stockdata must be a JSON object")
    return record


def _fetch_projected_symbol(root: Path, base: str, symbol: str) -> dict[str, Any]:
    record = _fetch_stock_record(base, symbol)
    return market_memory.symbol_context(root, symbol, stock_record=record)


def _prune_symbol_caches_locked(now: float) -> None:
    for key in [key for key, value in _symbol_data_cache.items() if value[0] <= now]:
        _symbol_data_cache.pop(key, None)
    for key in [
        key for key, value in _symbol_negative_cache.items() if value[0] <= now
    ]:
        _symbol_negative_cache.pop(key, None)


def _cache_symbol_payload_locked(
    cache_key: tuple[str, str], payload: Mapping[str, Any], now: float
) -> None:
    _prune_symbol_caches_locked(now)
    while len(_symbol_data_cache) >= _SYMBOL_DATA_CACHE_MAX_ENTRIES:
        oldest = min(_symbol_data_cache, key=lambda key: _symbol_data_cache[key][0])
        _symbol_data_cache.pop(oldest, None)
    _symbol_data_cache[cache_key] = (
        now + _SYMBOL_DATA_CACHE_TTL_SECONDS,
        copy.deepcopy(dict(payload)),
    )


def _finish_symbol_fetch(
    cache_key: tuple[str, str], future: Future[dict[str, Any]]
) -> None:
    payload: dict[str, Any] | None = None
    not_found = False
    failed = future.cancelled()
    if not failed:
        exception = future.exception()
        if exception is None:
            payload = future.result()
        else:
            failed = True
            not_found = isinstance(exception, _SymbolDataNotFound)
    now = time.monotonic()
    try:
        with _symbol_data_lock:
            if _symbol_fetch_inflight.get(cache_key) is future:
                _symbol_fetch_inflight.pop(cache_key, None)
            if payload is not None:
                _cache_symbol_payload_locked(cache_key, payload, now)
            elif failed:
                _symbol_negative_cache[cache_key] = (
                    now + _SYMBOL_FETCH_NEGATIVE_TTL_SECONDS,
                    not_found,
                )
    finally:
        _symbol_fetch_slots.release()


def _load_symbol_context(root: Path, symbol: str) -> dict[str, Any]:
    base = _stockdata_base(root)
    cache_key = (base, symbol)
    now = time.monotonic()
    with _symbol_data_lock:
        _prune_symbol_caches_locked(now)
        cached = _symbol_data_cache.get(cache_key)
        if cached is not None and cached[0] > now:
            return copy.deepcopy(cached[1])
        negative = _symbol_negative_cache.get(cache_key)
        if negative is not None and negative[0] > now:
            if negative[1]:
                raise _SymbolDataNotFound("stockdata object was not found")
            raise _SymbolDataBusy("stockdata source is temporarily unavailable")
        if cache_key in _symbol_fetch_inflight:
            raise _SymbolDataBusy("stockdata fetch is already in progress")
        if not _symbol_fetch_slots.acquire(blocking=False):
            raise _SymbolDataBusy("stockdata fetch lane is saturated")
        try:
            future = _symbol_fetch_executor.submit(
                _fetch_projected_symbol, root, base, symbol
            )
        except RuntimeError:
            _symbol_fetch_slots.release()
            raise _SymbolDataBusy("stockdata fetch lane could not accept work") from None
        _symbol_fetch_inflight[cache_key] = future
    future.add_done_callback(
        lambda completed, key=cache_key: _finish_symbol_fetch(key, completed)
    )
    try:
        payload = future.result(
            timeout=(
                _SYMBOL_FETCH_TOTAL_DEADLINE_SECONDS
                + _SYMBOL_FETCH_CALLER_GRACE_SECONDS
            )
        )
    except FutureTimeoutError:
        raise _SymbolDataBusy("stockdata fetch exceeded its caller deadline") from None
    except _SymbolDataNotFound:
        raise
    except _SymbolDataError:
        raise
    except CancelledError:
        raise _SymbolDataBusy("stockdata fetch was cancelled") from None
    return copy.deepcopy(payload)


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
        if not user_ok:
            return False
        peer_ok = _book_symbol_rate(
            f"peer:{peer}", limit=_SYMBOL_PEER_LIMIT, now=current
        )
    return peer_ok


def _reset_symbol_rate_limit_for_tests() -> None:
    with _symbol_rate_lock:
        _symbol_rate_buckets.clear()
    with _symbol_data_lock:
        _symbol_data_cache.clear()
        _symbol_negative_cache.clear()
    with _symbol_base_lock:
        _symbol_base_cache.clear()


@router.get("/as-known-at")
def as_known_at(
    request: Request,
    _user: dict = Depends(require_site_full_user),  # noqa: B008 - FastAPI injection
) -> JSONResponse:
    """Read one exact, previously captured operational PIT packet.

    W1A deliberately has no nearest-date, latest-state, reconstruction, or
    on-request materialization fallback.  Missing exact captures return 404.
    """

    if not _allow_symbol_request(request, _user):
        raise HTTPException(
            status_code=429,
            detail="Too many Market Memory context requests. Please retry shortly.",
            headers={"Retry-After": str(int(_SYMBOL_RATE_WINDOW_SECONDS))},
        )
    try:
        params = _exact_pit_query(request)
        reader = _pit_reader()
        if params["mode"] != reader.mode:
            raise market_memory_pit.MarketMemoryQueryError(
                "W1A supports operational_pit mode only"
            )
        stored = reader.read_stored_as_known_at(
            subject={
                "subject_id": params["subject_id"],
                "instrument_id": params["instrument_id"],
            },
            event_time=params["event_time"],
            as_known_at=params["as_known_at"],
        )
    except market_memory_pit.MarketMemoryQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except market_memory_pit.MarketMemoryContextNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="No exact Market Memory operational capture exists.",
        ) from exc
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail="Market Memory PIT storage is temporarily unavailable.",
            headers={"Retry-After": str(_SYMBOL_FETCH_BUSY_RETRY_SECONDS)},
        ) from exc
    return _stored_context_response(stored)


@router.get("/context/{context_id}")
def context_by_id(
    request: Request,
    context_id: str,
    _user: dict = Depends(require_site_full_user),  # noqa: B008 - FastAPI injection
) -> JSONResponse:
    """Read one published immutable capture by its W0 context identifier."""

    if not _allow_symbol_request(request, _user):
        raise HTTPException(
            status_code=429,
            detail="Too many Market Memory context requests. Please retry shortly.",
            headers={"Retry-After": str(int(_SYMBOL_RATE_WINDOW_SECONDS))},
        )
    try:
        stored = _pit_reader().read_stored_context_id(context_id)
    except market_memory_pit.MarketMemoryQueryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except market_memory_pit.MarketMemoryContextNotFound as exc:
        raise HTTPException(
            status_code=404,
            detail="No published Market Memory context exists for this identifier.",
        ) from exc
    except market_memory_pit.MarketMemoryStoreError as exc:
        raise HTTPException(
            status_code=503,
            detail="Market Memory PIT storage is temporarily unavailable.",
            headers={"Retry-After": str(_SYMBOL_FETCH_BUSY_RETRY_SECONDS)},
        ) from exc
    return _stored_context_response(stored)


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
        symbol = market_memory.normalize_ticker(ticker)
        payload = _load_symbol_context(_repo_root(), symbol)
    except market_memory.InvalidTicker as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers=_PRIVATE_HEADERS,
        ) from exc
    except _SymbolDataNotFound:
        payload = market_memory.symbol_context(_repo_root(), ticker)
    except _SymbolDataBusy as exc:
        raise HTTPException(
            status_code=503,
            detail="Market Memory symbol context is busy. Please retry shortly.",
            headers={"Retry-After": str(_SYMBOL_FETCH_BUSY_RETRY_SECONDS)},
        ) from exc
    except _SymbolDataError as exc:
        raise HTTPException(
            status_code=503,
            detail="Market Memory symbol context is temporarily unavailable.",
            headers={"Retry-After": str(_SYMBOL_FETCH_BUSY_RETRY_SECONDS)},
        ) from exc
    return _response(payload, status_code=200 if payload.get("available") else 404)
