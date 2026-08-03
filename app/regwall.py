"""app/regwall.py — the registration wall (operator lockdown order, 2026-07-24).

Every macro-dashboard product path EXCEPT the deliberately small public funnel
and reviewed SEO estate now requires a signed-in account of AT LEAST the free
tier. That includes HTML, generated JSON, data-bearing JavaScript, images, and
other static artifacts.
Caddy consults this endpoint before serving any protected file:

    204  → registered visitor (valid Supabase session cookie) — serve the file.
    302  → no/invalid session on a document navigation — Location:
           /?signin=1&ret=<original path>.
    401  → no/invalid session on an asset/data request — a small JSON lock
           response, never a redirect that fetch() could mistake for data.

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

import json
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
#
# EXACT public pages (the marketing funnel, plus the support desk).
#
# /support.html (SEE W2) is public by construction, not by convenience: the people
# who most need it are the ones who cannot sign in, so a contact form behind the
# registration wall would never receive the account/billing tickets it exists for.
# It ships no signals and no customer data, and its one write surface
# (POST /api/support/ticket) carries its own abuse posture in app/support.py.
#
# /about.html is the ENTITY page (research/SEO_SUPERCHARGE_MASTERPLAN_BY_FABLE.md
# §0.10). It is public for the same structural reason the legal pages are: a page
# whose whole job is to tell a stranger — and a crawler that has never had a
# session — who we are cannot sit behind a wall that asks them to prove who THEY
# are first. It ships no signals, no data and no write surface.
PUBLIC_PATHS = {
    "/",
    "/index.html",
    "/about.html",
    "/plans.html",
    "/confluence_screener.html",
    "/macro.html",
    "/start.html",
    "/us_stocks.html",
    "/research_vault.html",
    "/support.html",
    "/unsubscribe.html",
}
# Public PREFIXES — whole trees that stay FREE + crawlable (operator order
# 2026-07-24). A registration wall that carries no crawler exception 302s
# Googlebot (which never has a session) off every page, so the SEO estate must
# sit OUTSIDE the wall. These are mirrored EXACTLY by the Caddyfile @reg_html /
# @reg_html_err `not path` exclusions (app/deploy/Caddyfile) — the edge is the
# real enforcer, so the two lists MUST stay identical. Every entry is a live
# sitemap.xml prefix:
#   /stocks/  ~1.6k per-ticker SEO dossiers    /products/ platform explainers
#   /learn/   learning center
#   /tools/   tools hub + calculators + sheets  /blog/   blog + feed
#   /research/ per-report SEO landing pages + crawl hub (#3392/#3487 — public
#   teaser + in-page paywall; the PDFs stay in private R2 behind /api auth)
PUBLIC_PREFIXES = (
    "/stocks/",
    "/products/",
    "/tools/",
    "/learn/",
    "/blog/",
    "/research/",
)


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


def _is_public(path: str) -> bool:
    clean = urllib.parse.urlsplit(path or "").path
    return clean in PUBLIC_PATHS or any(clean.startswith(prefix) for prefix in PUBLIC_PREFIXES)


def _is_document(request: Request, ret: str) -> bool:
    """True only for a top-level HTML navigation.

    Caddy sends the explicit X-Original-Kind marker.  The conservative suffix
    fallback keeps direct endpoint tests and older Caddy installs compatible.
    """
    # Browser navigations to extensionless directory indexes (for example
    # /learn/) ride the asset matcher in Caddy, but Sec-Fetch-Dest still names
    # them correctly. Prefer that signal over the matcher hint.
    if (request.headers.get("sec-fetch-dest") or "").strip().lower() == "document":
        return True
    kind = (request.headers.get("x-original-kind") or "").strip().lower()
    if kind:
        return kind == "document"
    path = urllib.parse.urlsplit(ret).path.lower()
    return not path or path == "/" or path.endswith(".html")


def _deny(ret: str, *, document: bool = True) -> Response:
    common = {
        # A cached deny would lock registered users out; a cached allow would
        # leak content. Nothing from this endpoint is ever cacheable.
        "Cache-Control": "no-store",
        "Vary": "Cookie",
        "X-Regwall": "deny",
        "X-Robots-Tag": "noindex, noarchive",
    }
    if not document:
        return Response(
            content=json.dumps(
                {
                    "locked": True,
                    "reason": "authentication_required",
                    "signin_url": "/?signin=1",
                },
                separators=(",", ":"),
            ),
            status_code=401,
            media_type="application/json",
            headers=common,
        )

    loc = "/?signin=1"
    if ret and not _is_public(ret):
        loc += "&ret=" + urllib.parse.quote(ret, safe="/")
    return Response(
        status_code=302,
        headers={**common, "Location": loc},
    )


@router.get("/api/regwall/check")
def regwall_check(request: Request) -> Response:
    """Fail-closed registration check for protected static content."""
    ret = ""
    try:
        ret = _safe_ret(request.headers.get("x-original-uri"))
        document = _is_document(request, ret)
        if _is_public(ret):
            return Response(
                status_code=204,
                headers={"X-Regwall": "public", "Cache-Control": "no-store"},
            )
        if not _enabled():
            return Response(
                status_code=204,
                headers={"X-Regwall": "off", "Cache-Control": "no-store", "Vary": "Cookie"},
            )
        # Late imports keep startup order irrelevant; failure → deny (fail-closed).
        from app.main import _mm_supabase_access_token, _mm_verify_uid_cached  # noqa: PLC0415

        token = _mm_supabase_access_token(request)
        if not token:
            return _deny(ret, document=document)
        uid = _mm_verify_uid_cached(token)
        if not uid:
            return _deny(ret, document=document)
        return Response(
            status_code=204,
            headers={"X-Regwall": "allow", "Cache-Control": "no-store", "Vary": "Cookie"},
        )
    except Exception as exc:  # noqa: BLE001 — FAIL-CLOSED: any error denies, never serves
        log.warning("regwall: check failed closed (%s)", exc)
        return _deny(ret, document=_is_document(request, ret))
