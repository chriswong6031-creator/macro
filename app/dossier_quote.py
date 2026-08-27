"""Bounded public projection of one US quote for the static stock dossier.

Why this exists
---------------
The dossier pages are nightly-rendered static HTML.  The price was baked into
that HTML and a decorative "Live" stamp sat beside it, driven by the *build's*
freshness rather than the *quote's*.  Measured 2026-08-27: ``/stocks/NVDA.html``
served $209.66 with a static ``-$3.39 · -1.59%`` and a green "Live" chip, while
the measured regular-session close was $227.98 (+8.74%).  The baked figure was
the PREVIOUS close and the move was the PREVIOUS day's — presented as live.

Authority boundary
------------------
Market-data authority stays with the Terminal Quote Plane.  This module is a
*projection*, not a second publisher: it owns no quote store, no scheduler, no
socket, and no vendor credential.  It reads the already-running Quote Hub over
localhost and republishes an allowlisted, debranded subset.

Honesty law (the whole point)
-----------------------------
``freshness`` describes the FEED; ``session`` describes the MARKET.  A caller
may only claim "live" when both agree — a measured realtime row *and* an open
regular session.  Every uncertainty resolves DOWNWARD:

* a delayed basis is never "live", however recently it was fetched;
* a realtime basis whose own clock has aged past the bound is "stale";
* a missing or unparseable clock is "stale", never assumed fresh;
* an upstream failure is a 503, never a 200 carrying a plausible price.

Debrand law (research/licenses/MASSIVE_ENTITLEMENT_RECORD.md): the vendor is
never named on a public surface, so ``source``/``basis``/``anchor_source`` and
every other transport field are dropped rather than forwarded.
"""
from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Request, Response

from app import edge_client
from engine.company_intelligence.contracts import ContractError, safe_ticker

router = APIRouter()
log = logging.getLogger("macro.api.dossier_quote")

SCHEMA = "dossier_quote_public.v1"

# The Quote Hub is a localhost peer on the same box as this app.  It is not
# configurable to a remote host by accident: a non-local default would turn a
# projection into an egress path.
_HUB_BASE = os.environ.get("DOSSIER_QUOTE_HUB_URL", "http://127.0.0.1:3100").rstrip("/")
_HUB_TIMEOUT_SECONDS = float(os.environ.get("DOSSIER_QUOTE_HUB_TIMEOUT_SECONDS", "2.5"))
# A quote payload for ONE symbol is a few hundred bytes.  The cap stops a
# misconfigured or wedged upstream from streaming an unbounded body into the
# request path.
_HUB_MAX_BYTES = 64 * 1024

# A realtime row is allowed to be this old before it stops being "live".  Two
# of the hub's 60s snapshot TTLs (8s in realtime mode) — the tightest bound
# that cannot flicker on a healthy feed.
#
# DELIBERATELY TIGHTER THAN UPSTREAM.  The hub stamps `basis:"REALTIME"` when
# the FEED's print-age floor is realtime and THIS name printed within 15
# minutes (its `NAME_REALTIME_MAX_LAG_MS`), a bound it makes generous so a
# quiet ticker on a genuinely realtime feed still reads live.  That is the
# right call for a watchlist of many names; it is the wrong one for a dossier,
# which is a single page a reader stares at expecting the current price.  A
# two-minute-old print called "Live" is defensible there; a fourteen-minute-old
# one is not, however fresh a sibling ticker was.  The cost is under-claiming on
# a genuinely quiet name — the safe direction, and the one this whole route
# exists to choose.
_LIVE_MAX_AGE_SECONDS = 120.0
# Past this the row is not merely late, it is unrepresentative — the hub has
# stopped refreshing and the client must fall back to the baked value.  The
# bound is SESSION-AWARE on purpose.  Upstream stamps ``ts`` from the vendor's
# bar/print clock, so during RTH a gap this long means the feed is broken; but
# once the session closes the regular-session print is FINAL and legitimately
# stops advancing.  A single flat bound would therefore mark every correct
# after-hours close "stale" and send the page back to its baked value — which
# is the exact failure this route exists to remove.
_STALE_MAX_AGE_SECONDS = 900.0
# Outside RTH only a genuinely dead hub should fail: a settled close stays
# valid until the next session, and a row older than that is not a close we
# should be repainting from.
_CLOSED_STALE_MAX_AGE_SECONDS = 5 * 24 * 3600.0

# Substrings that disqualify a basis from being called realtime.  This is a
# fail-closed screen, not an enumeration of every basis the hub can emit: an
# unrecognised basis is only ever accepted as realtime when the hub's own
# ``live`` boolean independently agrees.
_NON_REALTIME_BASIS_MARKERS = ("delay", "eod", "close", "snapshot", "stale")

_RATE_LIMIT_REQUESTS = 120
_PEER_RATE_LIMIT_REQUESTS = 1_200
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_KEYS = 8_192
_TRUSTED_PEER_HEADER = "x-mm-peer"

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[str, deque[float]] = {}


# ── time (injected so freshness is testable without sleeping) ───────────────

def _now_epoch_seconds() -> float:
    return time.time()


# ── rate limiting (same two-bucket shape as app/company_intelligence.py) ────

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


def _book_rate_limit(key: str, *, limit: int, current: float, cutoff: float) -> bool:
    """Book one bounded rate slot.  Caller must hold ``_rate_limit_lock``."""
    bucket = _rate_limit_buckets.get(key)
    if bucket is None:
        if len(_rate_limit_buckets) >= _RATE_LIMIT_MAX_KEYS:
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
    with _rate_limit_lock:
        _rate_limit_buckets.clear()


# ── upstream read ───────────────────────────────────────────────────────────

def _read_hub_quotes(symbol: str) -> Mapping[str, Any]:
    """Fetch one symbol from the localhost Quote Hub.

    Raises on any transport or decode fault; the caller turns that into a 503.
    Never retries: a dossier page that missed one tick keeps its baked value,
    which is a better outcome than queueing work behind a wedged upstream.
    """
    url = f"{_HUB_BASE}/quotes?syms={urllib.parse.quote(symbol, safe='')}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=_HUB_TIMEOUT_SECONDS) as resp:
        raw = resp.read(_HUB_MAX_BYTES + 1)
    if len(raw) > _HUB_MAX_BYTES:
        raise ValueError("quote hub response exceeded the bounded read size")
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("quote hub response was not an object")
    return decoded


# ── projection ──────────────────────────────────────────────────────────────

def _finite_number(value: Any) -> float | None:
    """Return a finite float, or None.  Booleans are rejected on purpose."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def _is_realtime_basis(basis: Any) -> bool:
    if not isinstance(basis, str) or not basis.strip():
        return False  # absent basis is never evidence of realtime
    lowered = basis.strip().lower()
    return not any(marker in lowered for marker in _NON_REALTIME_BASIS_MARKERS)


def _session_of(row: Mapping[str, Any]) -> str:
    """Map the hub's market session onto the four states the dossier renders."""
    raw = row.get("marketSession")
    token = raw.strip().lower() if isinstance(raw, str) else ""
    if token in ("regular", "rth", "open"):
        return "regular"
    if token in ("pre", "premarket", "pre-market"):
        return "pre"
    if token in ("post", "after", "afterhours", "after-hours", "extended"):
        return "post"
    return "closed"


def _freshness_of(row: Mapping[str, Any], *, session: str, now: float) -> str:
    """Classify the FEED.  Every uncertain input resolves downward."""
    stamped = _finite_number(row.get("ts"))
    if stamped is None:
        return "stale"  # no clock we can check == no freshness we can claim
    age = now - stamped
    if age < -_LIVE_MAX_AGE_SECONDS:
        # A far-future stamp is a broken clock, not a fresh quote.
        return "stale"
    bound = _STALE_MAX_AGE_SECONDS if session == "regular" else _CLOSED_STALE_MAX_AGE_SECONDS
    if age > bound:
        return "stale"
    # Two independent upstream assertions must agree before this is "live":
    # the hub's own measured realtime flag AND a basis that is not a delayed
    # tier.  The age gate is the third, because the hub keeps serving a row
    # with a stalled socket until its idle sweep evicts it.
    if row.get("live") is True and _is_realtime_basis(row.get("basis")) and age <= _LIVE_MAX_AGE_SECONDS:
        return "live"
    return "delayed"


def _public_projection(row: Mapping[str, Any], *, ticker: str, now: float) -> dict[str, Any]:
    """Build the allowlisted browser payload from the REGULAR-session fields.

    ``last``/``close``/``prevClose``/``chg`` are the regular session.
    ``extPrice``/``extChg``/``extTs`` are the extended session and are dropped
    entirely — rendering an after-hours print as the day move would invert the
    sign the reader acts on (measured 2026-08-27: regular +8.74%, ext -0.76%).
    """
    price = _finite_number(row.get("last"))
    if price is None:
        price = _finite_number(row.get("close"))
    prev_close = _finite_number(row.get("prevClose"))
    if price is None or price <= 0 or prev_close is None or prev_close <= 0:
        raise ValueError("quote hub row carried no usable regular-session price")

    # `chg` upstream is a PERCENT despite the name; the dollar move is derived.
    change_pct = _finite_number(row.get("chg"))
    if change_pct is None:
        change_pct = (price - prev_close) / prev_close * 100.0
    change_abs = price - prev_close

    # Upstream can hand back the LAST COMPLETED session's move rather than
    # today's before an RTH open (its ``usePreviousSession`` path).  We cannot
    # tell those apart from the numbers, so ``regular_session_date`` is part of
    # the contract and the client dates the move instead of assuming "today".
    session_date = row.get("regularSessionDate")
    stamped = _finite_number(row.get("ts"))
    session = _session_of(row)

    return {
        "schema": SCHEMA,
        "ticker": ticker,
        "price": price,
        "prev_close": prev_close,
        "change_abs": change_abs,
        "change_pct": change_pct,
        "freshness": _freshness_of(row, session=session, now=now),
        "session": session,
        "as_of": int(stamped) if stamped is not None else None,
        "regular_session_date": session_date if isinstance(session_date, str) else None,
        "display_only": True,
    }


def _normalized_ticker_or_422(ticker: str) -> str:
    try:
        return safe_ticker(ticker)
    except ContractError as exc:
        raise HTTPException(
            status_code=422,
            detail="ticker must be a listed symbol using A-Z, 0-9, dots, or dashes",
        ) from exc


@router.get("/api/dossier-quote/{ticker}")
def dossier_quote(ticker: str, request: Request, response: Response) -> dict[str, Any]:
    """Return one debranded regular-session quote for a static dossier page.

    Never cached: a quote whose whole purpose is currency must not be served
    from an intermediary.  Upstream faults are 503 rather than a 200 carrying
    a stale-but-plausible price, so the browser can keep its baked value and
    say so honestly instead of silently repainting a wrong number.
    """
    if not _allow_request(request):
        raise HTTPException(
            status_code=429,
            detail="Too many quote requests. Please retry shortly.",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_SECONDS))},
        )
    normalized = _normalized_ticker_or_422(ticker)
    response.headers["Cache-Control"] = "private, no-store"

    try:
        payload = _read_hub_quotes(normalized)
    except Exception:  # noqa: BLE001 - an API source boundary must fail closed
        log.warning("quote hub unavailable for %s", normalized, exc_info=True)
        raise HTTPException(
            status_code=503, detail="Live quote is temporarily unavailable.",
        ) from None

    row = payload.get(normalized)
    if not isinstance(row, Mapping):
        raise HTTPException(
            status_code=404, detail=f"No live quote is published for {normalized}.",
        )
    # A row must identify itself as the symbol we asked for.  Without this a
    # hub-side aliasing bug would paint one company's price onto another's page.
    row_sym = row.get("sym")
    if isinstance(row_sym, str) and row_sym.strip().upper() != normalized:
        raise HTTPException(
            status_code=404, detail=f"No live quote is published for {normalized}.",
        )

    try:
        return _public_projection(row, ticker=normalized, now=_now_epoch_seconds())
    except ValueError:
        log.warning("quote hub row for %s was unusable", normalized)
        raise HTTPException(
            status_code=503, detail="Live quote is temporarily unavailable.",
        ) from None
