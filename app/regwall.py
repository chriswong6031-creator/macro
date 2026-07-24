"""app/regwall.py — the registration wall (operator lockdown order, 2026-07-24).

Every macro-dashboard HTML page EXCEPT the public funnel (the landing `/` +
`/index.html`, `/plans.html`) now requires a signed-in account of AT LEAST the
free tier. Caddy consults this endpoint (second sub-request stage, after the
fail-open IP gate) before serving any gated .html file:

    204  → registered visitor (valid Supabase session cookie) — serve the file.
    302  → no/invalid session — Location: /?signin=1&ret=<original path>; the
           landing opens the onboarding sheet, and onboard.js returns the
           visitor to `ret` after sign-in.

FAIL-CLOSED (the exact inverse of app/gate.py, per the MNZ-R1 doctrine): any
exception in this module denies (302 to the landing). The Caddy side mirrors
it — the gated matcher's error branch redirects instead of serving the file
(see app/deploy/Caddyfile). The one-page-still-up guarantee (CSP-R1) is
carried by the landing, which is never gated.

Session verification reuses app/main.py's secretless machinery:
_mm_supabase_access_token (chunked-cookie parse) + _mm_verify_uid_cached
(GET /auth/v1/user, 10-min positive/negative cache, never raises). The
resulting staleness bound: a signed-out-elsewhere session can pass for up to
one cache TTL (10 min) — acceptable for a REGISTRATION wall (the paid wall,
MNZ W3, keeps its own tighter bound when it lands).

Kill switch: REGWALL_ENABLED=0 in /etc/macro-api.env turns the wall off
(204 for everyone) without a deploy — the rollback lever if anything goes
sideways at the edge.
"""
from __future__ import annotations

import logging
import os
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import Response

log = logging.getLogger("macro.regwall")
router = APIRouter()

# Public funnel — everything else *.html is gated. Kept in code (not config):
# the list is the PRODUCT boundary, and moving a page across it should be a
# reviewed change, not an ops edit.
PUBLIC_PATHS = {"/", "/index.html", "/plans.html"}


def _enabled() -> bool:
    return os.environ.get("REGWALL_ENABLED", "1") not in ("0", "false", "no", "")


def _safe_ret(raw: str | None) -> str:
    """Same-origin path only: must start with '/', never '//' (off-origin)."""
    if not raw:
        return ""
    try:
        p = urllib.parse.unquote(raw)
    except Exception:  # noqa: BLE001
        return ""
    if p.startswith("/") and not p.startswith("//") and len(p) < 2000:
        return p
    return ""


def _deny(ret: str) -> Response:
    loc = "/?signin=1"
    if ret and ret not in PUBLIC_PATHS:
        loc += "&ret=" + urllib.parse.quote(ret, safe="/")
    return Response(
        status_code=302,
        headers={
            "Location": loc,
            # A cached redirect would lock REGISTERED users out; a cached allow
            # would leak content. Nothing from this endpoint is ever cacheable.
            "Cache-Control": "no-store",
            "X-Regwall": "deny",
        },
    )


@router.get("/api/regwall/check")
def regwall_check(request: Request) -> Response:
    """Fail-closed registration check for gated HTML (Caddy sub-request)."""
    ret = ""
    try:
        ret = _safe_ret(request.headers.get("x-original-uri"))
        if not _enabled():
            return Response(status_code=204, headers={"X-Regwall": "off"})
        # Late imports keep startup order irrelevant; failure → deny (fail-closed).
        from app.main import _mm_supabase_access_token, _mm_verify_uid_cached  # noqa: PLC0415

        token = _mm_supabase_access_token(request)
        if not token:
            return _deny(ret)
        uid = _mm_verify_uid_cached(token)
        if not uid:
            return _deny(ret)
        return Response(status_code=204, headers={"X-Regwall": "allow", "Cache-Control": "no-store"})
    except Exception as exc:  # noqa: BLE001 — FAIL-CLOSED: any error denies, never serves
        log.warning("regwall: check failed closed (%s)", exc)
        return _deny(ret)
