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
import os
import threading
import time
import urllib.parse
import urllib.request
from collections import deque
from typing import Any, Mapping

from fastapi import APIRouter, HTTPException, Request, Response

from app import edge_client
from app.public_quote_projection import (
    QuoteProjectionError,
    finite_number as _shared_finite_number,
    project_regular_quote,
)
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

# The realtime-basis allowlist, extended-session-tag set and percent-
# consistency epsilon that used to live here moved with the projection logic
# to app/public_quote_projection.py (see the block comment above
# `_public_projection`) — this module no longer classifies a row itself.

_RATE_LIMIT_REQUESTS = 120
_PEER_RATE_LIMIT_REQUESTS = 1_200
_RATE_LIMIT_WINDOW_SECONDS = 60.0
_RATE_LIMIT_MAX_KEYS = 8_192
_TRUSTED_PEER_HEADER = "x-mm-peer"

_rate_limit_lock = threading.Lock()
_rate_limit_buckets: dict[str, deque[float]] = {}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse every redirect rather than following it off the loopback."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D102
        raise urllib.error.HTTPError(
            req.full_url, code, "quote hub attempted a redirect", headers, fp,
        )


_NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirects)


def _assert_loopback(base: str) -> None:
    """Refuse a non-loopback hub.

    The hub is a same-box peer holding a vendor credential.  Pointing this at a
    remote host would turn a bounded projection into an egress path that
    republishes an unknown third party as our price.

    Called per REQUEST, deliberately not at import.  As a module-level check it
    did close the hole, but a mistyped env var then raised during
    ``app.main`` import and took the ENTIRE macro-api down with it — billing,
    auth, paywall, every unrelated route — measured, not theorised.  A dossier
    price must not be able to do that.  Per-request, the same misconfiguration
    disables exactly this route, as a 503, and nothing else.
    """
    host = (urllib.parse.urlsplit(base).hostname or "").lower()
    if host not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError(
            f"DOSSIER_QUOTE_HUB_URL must be loopback; refusing host {host!r}"
        )


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
    _assert_loopback(_HUB_BASE)
    url = f"{_HUB_BASE}/quotes?syms={urllib.parse.quote(symbol, safe='')}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    # _NO_REDIRECT_OPENER, not urlopen: urlopen FOLLOWS redirects, so a hub
    # answering `302 Location: http://elsewhere/` would make this app fetch a
    # third party and republish their numbers as the price — and a payload with
    # live:true + basis:"REALTIME" is all it takes to mint the green pip. The
    # loopback assertion on _HUB_BASE closes the same hole from the config side;
    # together they make the module docstring's "localhost only" claim true
    # rather than merely default.
    with _NO_REDIRECT_OPENER.open(req, timeout=_HUB_TIMEOUT_SECONDS) as resp:
        raw = resp.read(_HUB_MAX_BYTES + 1)
    if len(raw) > _HUB_MAX_BYTES:
        raise ValueError("quote hub response exceeded the bounded read size")
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("quote hub response was not an object")
    return decoded


# ── projection ──────────────────────────────────────────────────────────────
#
# The honesty-law arithmetic (freshness/session classification, percent-vs-
# dollar derivation, anchor reconstruction, extended-field refusal) moved to
# app/public_quote_projection.py (R1A-M, 2026-09) so the Intelligence Hub
# batch route shares the SAME owner rather than re-implementing it. This
# module keeps its own historical, deliberately tighter freshness bounds
# (_LIVE_MAX_AGE_SECONDS etc. above) and its own response schema
# (price/prev_close/change_abs/change_pct/freshness/session/as_of/
# regular_session_date/display_only) — both preserved byte-for-semantic
# identical to before the extraction; every test in this file exercises only
# the public HTTP surface and is unchanged by this refactor.


def _finite_number(value: Any) -> float | None:
    """Return a finite float, or None.  Booleans are rejected on purpose."""
    return _shared_finite_number(value)


def _public_projection(row: Mapping[str, Any], *, ticker: str, now: float) -> dict[str, Any]:
    """Build the allowlisted browser payload from the REGULAR-session fields.

    Thin adapter over ``project_regular_quote``: this module's own bounds
    (tighter than the shared defaults — see the module docstring for why) are
    passed explicitly, and the shared tuple is reshaped into the dossier's
    historical field names. ``project_regular_quote`` raises
    ``QuoteProjectionError`` (a ``ValueError``) on the same refusal cases this
    function used to raise ``ValueError`` for directly, so the caller's
    ``except ValueError`` -> 503 path is unchanged.
    """
    try:
        projected = project_regular_quote(
            row,
            ticker=ticker,
            now=now,
            published_at="",  # dossier schema does not surface published_at
            live_max_age_seconds=_LIVE_MAX_AGE_SECONDS,
            stale_max_age_seconds=_STALE_MAX_AGE_SECONDS,
            closed_stale_max_age_seconds=_CLOSED_STALE_MAX_AGE_SECONDS,
        )
    except QuoteProjectionError as exc:
        raise ValueError(str(exc)) from exc

    return {
        "schema": SCHEMA,
        "ticker": ticker,
        "price": projected.price,
        "prev_close": projected.prev_close,
        "change_abs": projected.change_abs,
        "change_pct": projected.change_pct,
        "freshness": projected.freshness,
        "session": projected.session,
        "as_of": (
            int(_shared_finite_number(row.get("ts")))
            if _shared_finite_number(row.get("ts")) is not None
            else None
        ),
        "regular_session_date": projected.regular_session_date,
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
    # Validate BEFORE booking a slot.  The peer bucket is shared by everyone
    # behind one edge node, so letting a stream of garbage tickers consume it
    # would let one caller 429 real readers without ever naming a real symbol.
    # The check is a regex; it cannot itself be the expensive path.
    normalized = _normalized_ticker_or_422(ticker)
    if not _allow_request(request):
        raise HTTPException(
            status_code=429,
            detail="Too many quote requests. Please retry shortly.",
            headers={"Retry-After": str(int(_RATE_LIMIT_WINDOW_SECONDS))},
        )
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
    # The identity must be PRESENT, not merely non-contradictory: guarding on
    # `isinstance(row_sym, str) and ...` meant a row with no `sym` at all
    # skipped the check entirely and published whatever price it carried.
    row_sym = row.get("sym")
    if not isinstance(row_sym, str) or row_sym.strip().upper() != normalized:
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
