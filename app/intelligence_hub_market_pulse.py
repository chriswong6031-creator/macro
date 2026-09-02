"""Deliberately public quote-only projection for the Intelligence Hub roster.

Why this route is public — printed here per the freeze's requirement that the
access decision be stated in the module that makes it, not only in a design
doc — and asserted directly by ``test_route_is_reachable_without_authentication``:

  * the Intelligence Hub shell (``intelligence_hub.html``) is already public;
  * the response contains allowlisted quote OBSERVATIONS only — price, move,
    freshness, session — never intelligence rows, scores, ranks or any
    personal/account state;
  * the enterprise entitlement record (research/licenses/
    MASSIVE_ENTITLEMENT_RECORD.md) permits external display/API
    redistribution of a debranded regular-session quote;
  * ``app/dossier_quote.py`` is the existing, already-shipped debranded
    precedent for exactly this class of route.

Accidental absence of auth on a route that SHOULD be private is a defect
elsewhere in this codebase; this route's absence of auth is the deliberate
design, not an omission.

Authority boundary
-------------------
Market-data authority stays with the Terminal Quote Plane. This module owns
no quote store, scheduler, socket, sequence counter or correction ledger — it
is a single bounded read of the already-running Quote Hub, projected through
the shared ``app.public_quote_projection`` owner and served as one stateless
snapshot per request. There is no server-side history: two consecutive
requests are two independent projections, never a diff or a stream.

Contract with the Terminal Quote Hub
-------------------------------------
Exactly ONE upstream request per incoming request, always
``?view=regular`` — never the default/full view, and never a fallback to it
on failure. A response row carrying ANY extended-hours key
(``extPrice``/``extChg``/``extTs``/``extSession``/``extSource``/``extBasis``)
is an upstream CONTRACT failure (the regular view promised none), not
something this route stripped and continued past.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from fastapi import APIRouter, HTTPException, Request, Response

from app import edge_client
from app.public_quote_projection import (
    QuoteProjectionError,
    project_regular_quote,
)
from engine.company_intelligence.contracts import ContractError, safe_ticker

router = APIRouter()
log = logging.getLogger("macro.api.intelligence_hub_market_pulse")

SCHEMA = "intelligence_hub.market_pulse.v1"
PROJECTION = "intelligence_hub.market_pulse"
SOURCE_OWNER = "terminal-market-data"
SOURCE_VIEW = "regular"

# Same same-box-peer posture as app/dossier_quote.py: never configurable to a
# remote host by accident.
_HUB_BASE = os.environ.get("INTEL_HUB_MARKET_PULSE_HUB_URL", "http://127.0.0.1:3100").rstrip("/")
_HUB_TIMEOUT_SECONDS = float(os.environ.get("INTEL_HUB_MARKET_PULSE_HUB_TIMEOUT_SECONDS", "2.5"))
# Up to 60 symbols at a few hundred bytes each is comfortably inside this cap;
# a misconfigured/wedged upstream cannot stream an unbounded body through here.
_HUB_MAX_BYTES = 256 * 1024

_MAX_SYMBOLS = 60

# Every extended-hours key the Terminal `view=regular` contract promises to
# never emit. Its presence anywhere in a returned row is a contract failure —
# refused outright, never stripped-and-continued (freeze line ~628).
_EXT_FIELD_PREFIXES = ("ext",)

# Client bucket stays symbol-weighted: one unique symbol costs one unit, and
# the 58-name roster refreshing every 60s plus manual/resume margin must
# clear this comfortably.
_RATE_LIMIT_UNITS = 58 * 5           # ~5 full-roster refreshes per window
# Peer bucket is charged per-REQUEST, not per-symbol (freeze review MAJOR
# b1). A symbol-weighted peer bucket let one shared edge identity behind many
# concurrent readers spend its whole window on a handful of full-roster
# requests, but also let a flood of tiny requests (amplification: many cheap
# 1-symbol calls) buy far more requests than a legitimate multi-reader
# workload ever needs. 600 requests/60s per peer identity clears many
# concurrent readers polling the full 58-name roster every 60s with margin
# for manual refresh/resume, while still 429-ing a request-count flood.
_PEER_RATE_LIMIT_REQUESTS = 600
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_KEYS = 8_192
_TRUSTED_PEER_HEADER = "x-mm-peer"

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[str, deque[tuple[float, int]]] = {}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect rather than following it off the loopback."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise urllib.error.HTTPError(
            req.full_url, code, "quote hub attempted a redirect", headers, fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirects)


def _assert_loopback(base: str) -> None:
    """Refuse a non-loopback hub. Checked per REQUEST (see app/dossier_quote.py
    for why: a mistyped env var must disable only this route, as a 503, never
    take the whole macro-api down at import time)."""
    host = (urllib.parse.urlsplit(base).hostname or "").lower()
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError(
            f"INTEL_HUB_MARKET_PULSE_HUB_URL must be loopback; refusing host {host!r}"
        )


def _now_epoch_seconds() -> float:
    return time.time()


# ── input parsing ────────────────────────────────────────────────────────────

class _InvalidSymbols(ValueError):
    """Raised for any malformed/empty/oversized symbols query."""


def _parse_symbols(raw: str | None) -> list[str]:
    """Validate and dedupe the requested symbols, preserving first occurrence.

    Every member must independently validate (``safe_ticker``); an invalid
    member REFUSES the whole request rather than being silently dropped —
    a caller asking for a typo'd symbol should see a 400, not a quietly
    smaller roster.
    """
    if raw is None or not raw.strip():
        raise _InvalidSymbols("symbols is required")
    parts = raw.split(",")
    ordered: list[str] = []
    seen: set[str] = set()
    for part in parts:
        if not part.strip():
            raise _InvalidSymbols("symbols may not contain an empty member")
        try:
            normalized = safe_ticker(part)
        except ContractError as exc:
            raise _InvalidSymbols(str(exc)) from exc
        if normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    if not ordered:
        raise _InvalidSymbols("symbols is required")
    if len(ordered) > _MAX_SYMBOLS:
        raise _InvalidSymbols(f"more than {_MAX_SYMBOLS} unique symbols")
    return ordered


# ── rate limiting (symbol-weighted; same two-bucket shape as dossier_quote) ─

def _claimed_client_identity(request: Request) -> str:
    resolved = edge_client.client_ip(request.headers)
    if resolved != edge_client.UNKNOWN:
        return resolved[:128]
    return str(request.client.host if request.client else "unknown")[:128]


def _trusted_peer_identity(request: Request) -> str:
    peer = str(request.headers.get(_TRUSTED_PEER_HEADER) or "").strip()
    if peer:
        return peer[:128]
    return str(request.client.host if request.client else "unknown")[:128]


def _book_rate_limit(key: str, *, units: int, limit: int, current: float, cutoff: float) -> bool:
    """Book one bounded symbol-weighted slot. Caller must hold the lock."""
    bucket = _rate_limit_buckets.get(key)
    if bucket is None:
        if len(_rate_limit_buckets) >= _RATE_LIMIT_MAX_KEYS:
            oldest = min(_rate_limit_buckets, key=lambda item: _rate_limit_buckets[item][-1][0])
            del _rate_limit_buckets[oldest]
        bucket = deque()
        _rate_limit_buckets[key] = bucket
    while bucket and bucket[0][0] <= cutoff:
        bucket.popleft()
    spent = sum(u for _, u in bucket)
    if spent + units > limit:
        return False
    bucket.append((current, units))
    return True


def _allow_request(request: Request, *, units: int, now: float | None = None) -> bool:
    current = time.monotonic() if now is None else now
    cutoff = current - _RATE_LIMIT_WINDOW_SECONDS
    client = _claimed_client_identity(request)
    peer = _trusted_peer_identity(request)
    with _rate_limit_lock:
        ok_client = _book_rate_limit(
            f"client:{client}", units=units, limit=_RATE_LIMIT_UNITS, current=current, cutoff=cutoff,
        )
        # Peer bucket: one unit per REQUEST regardless of symbol count (b1) —
        # never `units` here, that would re-introduce the symbol weighting.
        ok_peer = _book_rate_limit(
            f"peer:{peer}", units=1, limit=_PEER_RATE_LIMIT_REQUESTS, current=current, cutoff=cutoff,
        )
        return ok_client and ok_peer


def _reset_rate_limit_for_tests() -> None:
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


# ── upstream read: exactly ONE call, view=regular, never a fallback ────────

def _fetch_hub_quotes(symbols: Sequence[str], view: str) -> Mapping[str, Any]:
    """The ONE Terminal Hub request this route ever makes per incoming call.

    ``view`` is a required, explicit parameter (never a hardcoded literal
    inside this function) precisely so a caller cannot silently drop it —
    the route handler always passes ``view="regular"``, and no code path in
    this module may call this function with anything else or a second time.
    Never retries and never falls back to the default/full view on any
    failure — a caller that missed one refresh keeps the roster's baked
    values, which is a better outcome than a route that quietly spent
    ExtFeed demand it promised never to spend.
    """
    _assert_loopback(_HUB_BASE)
    csv = ",".join(symbols)
    query = urllib.parse.urlencode({"syms": csv, "view": view})
    url = f"{_HUB_BASE}/quotes?{query}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    # _NO_REDIRECT_OPENER, not urlopen: see app/dossier_quote.py — urlopen
    # FOLLOWS redirects, which would make this route fetch and republish a
    # third party's numbers as Terminal's.
    with _NO_REDIRECT_OPENER.open(req, timeout=_HUB_TIMEOUT_SECONDS) as resp:
        raw = resp.read(_HUB_MAX_BYTES + 1)
    if len(raw) > _HUB_MAX_BYTES:
        raise ValueError("quote hub response exceeded the bounded read size")
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("quote hub response was not an object")
    return decoded


def _row_leaks_extended_fields(row: Mapping[str, Any]) -> bool:
    return any(
        isinstance(key, str) and key.startswith(_EXT_FIELD_PREFIXES)
        for key in row.keys()
    )


# ── envelope assembly ───────────────────────────────────────────────────────

_FRESHNESS_RANK = {"live": 0, "delayed": 1, "stale": 2}  # higher = more conservative


def _worst_freshness(freshnesses: Sequence[str]) -> str:
    return max(freshnesses, key=lambda f: _FRESHNESS_RANK.get(f, 2))


def _page_session(sessions: Sequence[str]) -> str:
    """The page-level session axis is conservative, never a snap vote.

    All-regular is the only case allowed to say "regular"; an all-closed
    resolved set says "closed" (a settled read); any mix of sessions (some
    open, some closed, some pre/post) collapses to "mixed" so the client
    never renders live/regular language over a page where not every accepted
    tuple actually shares that session (freeze §7.3 "any mix renders
    conservative mixed/settled language, never live/regular").
    """
    unique = set(sessions)
    if unique == {"regular"}:
        return "regular"
    if unique == {"closed"}:
        return "closed"
    return "mixed"


def _build_envelope(
    *,
    requested: Sequence[str],
    hub_payload: Mapping[str, Any],
    now: float,
    generated_at_iso: str,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    freshnesses: list[str] = []
    sessions: list[str] = []
    live = delayed = stale = 0

    for symbol in requested:
        row = hub_payload.get(symbol)
        if not isinstance(row, Mapping):
            errors.append({"symbol": symbol, "code": "quote_unavailable"})
            continue
        if _row_leaks_extended_fields(row):
            # A single leaking row invalidates the whole upstream contract —
            # this is not a per-symbol refusal, it is proof the "view=regular"
            # promise was broken. Raise all the way out to the route handler.
            # Checked BEFORE the sym-mismatch skip below (freeze review g2): a
            # row that leaks an extended field AND carries the wrong `sym`
            # must still 503 the whole request — the sym-mismatch branch is a
            # per-symbol refusal, and a contract violation must never be
            # silently downgraded into one just because the leaking row also
            # happened to be mismatched.
            raise QuoteProjectionError(f"upstream row for {symbol} leaked an extended field")
        row_sym = row.get("sym")
        if not isinstance(row_sym, str) or row_sym.strip().upper() != symbol:
            errors.append({"symbol": symbol, "code": "quote_unavailable"})
            continue
        try:
            projected = project_regular_quote(
                row, ticker=symbol, now=now, published_at=generated_at_iso,
            )
        except QuoteProjectionError:
            errors.append({"symbol": symbol, "code": "quote_unavailable"})
            continue

        item = asdict(projected)
        # dossier-only field: the public batch item keeps the frozen 12-key
        # intelligence_hub.market_pulse.v1 shape (spec §7.3); prev_close is
        # derivable client-side from price - change_abs and is not shipped.
        item.pop("prev_close", None)
        items.append(item)
        freshnesses.append(projected.freshness)
        sessions.append(projected.session)
        if projected.freshness == "live":
            live += 1
        elif projected.freshness == "delayed":
            delayed += 1
        else:
            stale += 1

    resolved = len(items)
    missing = len(requested) - resolved

    return {
        "schema": SCHEMA,
        "projection": PROJECTION,
        "snapshot_id": os.urandom(8).hex(),
        "generated_at": generated_at_iso,
        "source_owner": SOURCE_OWNER,
        "source_view": SOURCE_VIEW,
        "state": {
            "availability": "available" if resolved else "unavailable",
            "freshness": _worst_freshness(freshnesses) if freshnesses else "stale",
            "session": _page_session(sessions) if sessions else "mixed",
            "coverage": "complete" if missing == 0 else "partial",
        },
        "coverage": {
            "requested": len(requested),
            "resolved": resolved,
            "live": live,
            "delayed": delayed,
            "stale": stale,
            "missing": missing,
        },
        "items": items,
        "errors": errors,
    }


@router.get("/api/intelligence-hub/market-pulse")
def market_pulse(symbols: str | None = None, *, request: Request, response: Response) -> dict[str, Any]:
    """Return one stateless regular-session quote snapshot for the requested
    Intelligence Hub roster symbols. Deliberately public — see module
    docstring. Never cached: the whole point is currency."""
    try:
        ordered_symbols = _parse_symbols(symbols)
    except _InvalidSymbols:
        # Fixed opaque literal — never echo caller input into the response
        # (freeze review MINOR a1). `_InvalidSymbols` messages can themselves
        # carry the caller's own malformed text (via `safe_ticker`'s
        # ContractError), so the exception text may never reach the client.
        raise HTTPException(status_code=400, detail="invalid_symbols") from None

    # Validate BEFORE booking a slot — an invalid/oversized request must not
    # spend real budget (same discipline as app/dossier_quote.py).
    if not _allow_request(request, units=len(ordered_symbols)):
        raise HTTPException(
            status_code=429,
            detail="Too many quote requests. Please retry shortly.",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_SECONDS))},
        )
    response.headers["Cache-Control"] = "private, no-store"

    now = _now_epoch_seconds()
    generated_at_iso = (
        datetime.fromtimestamp(now, tz=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    )

    try:
        hub_payload = _fetch_hub_quotes(ordered_symbols, view="regular")
    except Exception:  # noqa: BLE001 - an upstream boundary must fail closed
        log.warning("market pulse hub unavailable for %d symbols", len(ordered_symbols), exc_info=True)
        raise HTTPException(status_code=503, detail="quote_projection_unavailable") from None

    try:
        envelope = _build_envelope(
            requested=ordered_symbols, hub_payload=hub_payload, now=now,
            generated_at_iso=generated_at_iso,
        )
    except QuoteProjectionError:
        log.warning("market pulse upstream contract violation", exc_info=True)
        raise HTTPException(status_code=503, detail="quote_projection_unavailable") from None

    if not envelope["items"]:
        raise HTTPException(status_code=503, detail="quote_projection_unavailable")

    return envelope
