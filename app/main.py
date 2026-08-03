"""macro API — FastAPI serving tier for the SaaS (Slice 2).

Minimal by design: health + overlay now; Supabase-JWT-gated routes activate the
moment ``SUPABASE_JWT_SECRET`` is set in the service environment. This wraps the
existing build artifacts under /opt/macro — it does NOT recompute the engine.

DEPLOY NOTE (2026-07-23, CMX W4): this docstring touch intentionally rides with
the app/deploy/update.sh restart-trigger widening (brain_gateway/chart_perception/
doctrine) — main.py matches the OLD trigger regex still running on the box, so
this pull restarts macro-api and brings the already-merged W4 doctrine injection
live; the widened regex takes over from the next cron tick.

W8b PR2 — /api/ask and /api/ask/stream
---------------------------------------
POST /api/ask          — authed (require_user); interrogate the Neural Web brain
                         with a plain-language question.  Read tools only; write
                         tools structurally absent from the schema (Article 1).
POST /api/ask/stream   — SSE streaming variant of the same; tool-calling turns
                         run synchronously, final synthesis turn is streamed.

Live Options Flow Feed — /api/flow/*
--------------------------------------
GET /api/flow/feed          — unauthenticated; live-flow feed (events + unusual_names)
GET /api/flow/heat          — unauthenticated; per-sector/group heat map
GET /api/flow/meta          — unauthenticated; poller meta / cadence info
GET /api/flow/tide          — unauthenticated; market tide (NCP/NPP/gross/vol minute series)
GET /api/flow/dte           — unauthenticated; DTE-bucket tide (5 buckets)
GET /api/flow/ticker/{root} — unauthenticated; per-root drill (root sanitized [A-Z.]{1,8})

All are server-side read-throughs of the R2 live_flow/ objects with a 30-second
in-memory TTL cache.  On fetch failure the last-cached copy is returned with
{"stale":true} merged.  503 only if the object was never successfully fetched.

Options Hub analytics — /api/hub/* (routed from app/hub.py, lane B)
--------------------------------------
GET /api/hub/vol/{root}, /api/hub/gex/{root}, /api/hub/oi, /api/hub/hot
(loaded via try-import at module bottom; no-op if app/hub.py is absent)

KEY-OPTIONAL: when ANTHROPIC_API_KEY is absent from /etc/macro-api.env the
endpoints return mode='memo-quote' (degraded=True) — a relevant excerpt from
data/neuralweb/cortex/memo.json.  The operator arms live mode by adding
ANTHROPIC_API_KEY to /etc/macro-api.env and restarting macro-api.service.

DEPLOY NOTE: the per-user/global quota ledger is written to MACRO_API_STATE_DIR
(default /var/lib/macro-api/).  The VPS setup must create this dir once:
    mkdir -p /var/lib/macro-api && chown root:root /var/lib/macro-api && chmod 700 /var/lib/macro-api
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import subprocess
import sys
import threading
import time
from collections import deque
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.datastructures import MutableHeaders

# Server-side brain runs: a chat turn is owned by the registry, not by the socket
# that started it, so a backgrounded tab or a culled connection can never destroy
# an answer the model already produced. Pure stdlib, no app import cycle.
from app import brain_runs

# Add repo root to sys.path so engine.neuralweb can be imported from /opt/macro
_REPO_ROOT_FOR_IMPORT = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

# Stored user preferences (lang/theme/brain_depth). MUST come after the sys.path insert
# above — `lib` lives at the repo root, not under app/. Pure stdlib, no app import cycle.
from lib import user_prefs  # noqa: E402

REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
SITE = REPO / "site"
# VPS live artifacts live outside the git work-tree so a frequent
# ``git reset --hard``/site rsync can never roll them back or expose an
# in-progress write. Local/test installs transparently fall back to SITE/live.
LIVE = Path(os.environ.get("MACRO_LIVE_DIR", "/var/lib/macro-live/public/live"))
# The Terminal's data manifest (refreshed by the daily terminal-data cron) — read-only
# freshness check for /api/status.
TERMINAL_MANIFEST = Path(
    os.environ.get("TERMINAL_MANIFEST", "/opt/terminal/terminal/public/data/manifest.json")
)

# Public Supabase project coordinates (the anon key is publishable — it already
# ships in the browser via site/auth.js — so committing it here is fine). Override
# via env if the project changes.
SUPABASE_URL = os.environ.get(
    "SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co"
).rstrip("/")
SUPABASE_ANON_KEY = os.environ.get(
    "SUPABASE_ANON_KEY", "sb_publishable_f33VG8fZuyIZPl_lZIDX3w_RFuuZtpv"
)

app = FastAPI(title="macro API", version="0.1.0")

log = logging.getLogger("macro.api")


class _NoStoreAPI:
    """Every /api/* response is per-user — never let a shared cache keep one.

    FOUND LIVE (2026-07-25 Stripe go-live audit): macro-api sent NO Cache-Control on
    /api/*, so the EdgeOne edge applied its own default and cached **404** responses,
    with a cache key that IGNORES the Authorization header. `GET /api/billing/portal`
    404s for every user without a Stripe customer (i.e. every free user), and that 404
    was then replayed from the edge to PAYING subscribers — who saw "no billing account
    yet" and could not reach the billing portal at all (the only self-serve path to
    update a card, cancel, or downgrade). Reproduced twice with `eo-cache-status: HIT`.

    Measured scope at the time: 404 was cached; 401 and 200 were not — so /api/me and
    /api/account happened to be safe. That is a CDN heuristic, not a guarantee, and it
    can change under us. This removes the dependency entirely: the origin now states the
    caching rule for its own responses instead of leaving it to the edge.

    `setdefault` semantics — a route that already set Cache-Control (the SSE streams'
    `no-cache`, the regwall/paywall gates' `no-store`) keeps its own value.

    Deliberately a RAW ASGI middleware, not @app.middleware("http"): the latter is
    Starlette's BaseHTTPMiddleware, which wraps the response body in an anyio stream and
    has a long history of interfering with StreamingResponse. This app serves several
    long-lived SSE streams under /api/ — the brain lane and its re-attach stream
    (app/brain_runs.py) among them — and a header-only concern has no business in the
    body path for any of them. This touches exactly one dict on the `http.response.start`
    message and passes every body chunk straight through.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not scope.get("path", "").startswith("/api/"):
            await self.app(scope, receive, send)
            return

        async def _send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "cache-control" not in headers:
                    headers["cache-control"] = "private, no-store"
            await send(message)

        await self.app(scope, receive, _send)


app.add_middleware(_NoStoreAPI)


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


# The build this PROCESS is serving — captured once at import. The VPS pull loop
# advances the /opt/macro checkout every 3 minutes, but macro-api restarts only
# when the deploy regex matches its own code (app/deploy/update.sh), so a
# per-request _commit() reports the CHECKOUT, not the running code: observed live
# 2026-07-31, health flipped to a freshly pulled sha while the pid was still
# serving the import from six minutes earlier.
_PROCESS_COMMIT = _commit()


@app.get("/api/health")
def health() -> dict:
    """Liveness + which build is being served. Unauthenticated.

    ``commit`` is the build the running process imported; ``checkout`` is the
    working tree at request time. They differ whenever the pull loop has
    advanced /opt/macro past the last macro-api restart — visible drift, so an
    operator confirming an API deploy reads the truthful field.
    """
    return {"status": "ok", "commit": _PROCESS_COMMIT, "checkout": _commit()}


# ── First-party analytics collector — POST /api/collect ─────────────────────────
# Same-origin beacon sink for the macro static site (templates/theme.js loadMMAnalytics).
# Anonymous by default — every visitor is measured. Signed-in visitors are ADDITIONALLY
# attributed to their VERIFIED Supabase user (user_id, a uuid FK to auth.users) by reading
# the shared session cookie off the same-origin beacon (see _mm_supabase_access_token +
# _mm_verify_uid_cached) — a client-claimed identity is never trusted. The visitor id (mm_aid,
# httpOnly, Domain=.mastermind-x.com, shared with the Terminal at app.mastermind-x.com), the raw
# client IP, and the user-agent are stamped HERE; geolocation is backfilled off the hot path by
# scripts/geo_enrich.py. Rows go to the shared Supabase `analytics_events` table
# (charting-app supabase/migrations/0004_analytics.sql) via PostgREST using the service-role key
# (deny-all RLS — the anon key never touches it). The DB write runs as a BackgroundTask so the
# beacon returns immediately and never blocks on Supabase.
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
MM_COOKIE_DOMAIN = os.environ.get("MM_COOKIE_DOMAIN", ".mastermind-x.com")
_MM_ANON_COOKIE = "mm_aid"
_MM_MAX_BATCH = 40
_MM_EVENT_TYPES = {
    "pageview", "route", "ticker_view", "search", "terminal_jump",
    "click", "scroll", "session_start", "heartbeat", "exit",
    # Ad Central Plane O (research/AD_CENTRAL_MASTERPLAN.md §2): which split-test
    # variant a visitor was shown. The arm rides in `meta` as {arena, creative};
    # the unit identity is the mm_aid `visitor_id` this endpoint stamps, NOT
    # anything the client sends — which is what keeps the denominator honest when
    # the client is the thing choosing the arm. Read by engine/marketing/ad_ingest.py.
    "ad_exposure",
}


def _mm_is_loggable_ip(ip: str) -> bool:
    """True only for a globally-routable public visitor IP. Loopback/private/link-local/
    unspecified/'unknown' are same-box or non-visitor traffic and are never logged, mirroring
    the `_routable` filter in scripts/geo_enrich.py so what we log is what geo-enrich can place."""
    if not ip or ip == "unknown":
        return False
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def _mm_client_ip(request: Request) -> str:
    # Real VISITOR IP, not the CDN edge. mastermind-x.com is behind Tencent EdgeOne. EdgeOne does NOT
    # send a real-client-IP header by default, so X-Forwarded-For is the EdgeOne EDGE IP (e.g.
    # "Tucumcari NM" / a Singapore PoP for China traffic), not the person. Once the operator adds the
    # EdgeOne rule "Client IP Header" = EO-Client-IP (Network Optimization), the real IP arrives here.
    # Precedence: the configured real-IP header first (EO-Client-IP), then the other CDN real-client
    # headers, then XFF/x-real-ip. All of these pass through Caddy untouched. See app/deploy/SITE_GATE.md
    # and the edgeone-real-ip-headers note.
    h = request.headers
    for k in ("eo-client-ip", "eo-connecting-ip", "cf-connecting-ip", "true-client-ip"):
        v = (h.get(k) or "").strip()
        if v:
            return v[:64]
    xff = h.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (h.get("x-real-ip") or "").strip()[:64] or "unknown"


# ── Registered-visitor identity (attribute authenticated visitors to their user) ──
# The beacon is same-origin to mastermind-x.com and sends cookies, so /api/collect
# receives the SHARED Supabase session cookie (sb-<ref>-auth-token, written by
# templates/theme.js COOKIE_STORAGE and scoped to .mastermind-x.com). We read the
# access token from it, VERIFY it secretlessly against Supabase (never trust a
# client-claimed identity — user_id is a uuid FK to auth.users), and stamp the
# verified user UUID on the rows. Email stays out of the row (resolved at read time
# by the admin via auth.users). Verification is cached by token and runs off the
# beacon's hot path (inside the background insert task).


def _sb_storage_key() -> str:
    """The @supabase/ssr cookie key: sb-<project-ref>-auth-token (ref = SUPABASE_URL subdomain)."""
    try:
        ref = SUPABASE_URL.split("://", 1)[-1].split(".", 1)[0]
    except Exception:  # noqa: BLE001
        ref = ""
    return f"sb-{ref}-auth-token"


_SB_STORAGE_KEY = _sb_storage_key()


def _mm_supabase_access_token(request: Request) -> str | None:
    """Extract the Supabase access_token from the shared session cookie.

    Value format (matches templates/theme.js): "base64-" + base64url(session JSON),
    single cookie or chunked as <key>.0, <key>.1, … Returns the token or None. Never raises.
    """
    try:
        ck = request.cookies
        raw = ck.get(_SB_STORAGE_KEY)
        if raw is None:
            parts, i = [], 0
            while i < 33:
                c = ck.get(f"{_SB_STORAGE_KEY}.{i}")
                if c is None:
                    break
                parts.append(c)
                i += 1
            if not parts:
                return None
            raw = "".join(parts)
        if not raw.startswith("base64-"):
            return None
        b = raw[len("base64-"):].replace("-", "+").replace("_", "/")
        b += "=" * (-len(b) % 4)
        session = json.loads(base64.b64decode(b).decode("utf-8"))
        tok = session.get("access_token")
        return tok if isinstance(tok, str) and tok else None
    except Exception:  # noqa: BLE001
        return None


_MM_UID_CACHE: dict = {}          # access_token -> (uid_or_None, expiry_monotonic)
_MM_UID_CACHE_TTL = 600.0         # 10 min — many beacons per session reuse one token
_MM_UID_CACHE_LOCK = threading.Lock()


def _mm_verify_uid_cached(token: str) -> str | None:
    """Verify the access token against Supabase and return the user's UUID (auth.users.id).

    Secretless (GET /auth/v1/user with the public anon key, same idiom as require_user),
    cached by token. Invalid/expired tokens cache as None so bad tokens aren't re-checked.
    Never raises.
    """
    now = time.monotonic()
    with _MM_UID_CACHE_LOCK:
        hit = _MM_UID_CACHE.get(token)
        if hit and hit[1] > now:
            return hit[0]
    uid = None
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            data = json.loads(resp.read())
        u = data.get("id")
        if isinstance(u, str) and u:
            try:
                uuid.UUID(u)   # user_id is a uuid FK to auth.users — never stamp a non-uuid
                uid = u
            except (ValueError, TypeError):
                uid = None
    except Exception:  # noqa: BLE001 — invalid/expired token or upstream down; stay anonymous
        uid = None
    with _MM_UID_CACHE_LOCK:
        if len(_MM_UID_CACHE) > 5000:   # coarse cap; never unbounded
            _MM_UID_CACHE.clear()
        _MM_UID_CACHE[token] = (uid, now + _MM_UID_CACHE_TTL)
    return uid


def _mm_clamp(v: Any, n: int):
    if v is None:
        return None
    s = str(v)
    return s[:n] if s else None


def _mm_int(v: Any, lo: int, hi: int):
    try:
        x = int(float(v))
    except (TypeError, ValueError):
        return None
    return max(lo, min(hi, x))


def _mm_analytics_insert(rows: list, access_token: str | None = None) -> None:
    """Best-effort PostgREST insert into analytics_events. Never raises (runs as a background task).

    When a Supabase access token is present, verify it (cached) and stamp the resulting
    user UUID on every row so authenticated visitors are attributed to their account.
    user_id is a uuid FK to auth.users, so only a VERIFIED id is ever written.
    """
    if not rows or not SUPABASE_SERVICE_ROLE_KEY:
        return
    if access_token:
        uid = _mm_verify_uid_cached(access_token)
        if uid:
            for r in rows:
                r["user_id"] = uid
    try:
        req = urllib.request.Request(
            f"{SUPABASE_URL}/rest/v1/analytics_events",
            data=json.dumps(rows).encode(),
            method="POST",
            headers={
                "apikey": SUPABASE_SERVICE_ROLE_KEY,
                "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
        )
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:
        pass  # analytics ingest is best-effort; never surface to the caller


# Per-IP burst throttle for the anonymous analytics beacon. An in-memory sliding
# window mirroring _brain_throttle_check (below): max 60 requests / 60s per client
# IP -> 429, so an anonymous client can't flood the beacon into minting unbounded
# mm_aid cookies + Supabase inserts. The dict is capped so it can never grow unbounded.
_COLLECT_THROTTLE_MAX = 60
_COLLECT_THROTTLE_WINDOW = 60.0
_COLLECT_THROTTLE_CAP = 20000
_collect_throttle: dict[str, deque] = {}
_collect_throttle_lock = threading.Lock()


def _collect_throttle_ok(ip: str) -> bool:
    """False when ip exceeds the per-IP sliding-window budget (caller returns 429).
    Prunes on access; the dict is capped so it can never grow unbounded."""
    now = time.monotonic()
    cutoff = now - _COLLECT_THROTTLE_WINDOW
    with _collect_throttle_lock:
        dq = _collect_throttle.get(ip)
        if dq is None:
            if len(_collect_throttle) >= _COLLECT_THROTTLE_CAP:
                # Evict the oldest-inserted entry (dict preserves insertion order).
                try:
                    _collect_throttle.pop(next(iter(_collect_throttle)))
                except StopIteration:
                    pass
            dq = deque()
            _collect_throttle[ip] = dq
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _COLLECT_THROTTLE_MAX:
            return False
        dq.append(now)
        return True


@app.post("/api/collect")
async def collect(request: Request, background: BackgroundTasks) -> Response:
    """Anonymous first-party analytics beacon sink (see block header)."""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > 16384:
        return Response(status_code=413)
    ip = _mm_client_ip(request)
    if not _collect_throttle_ok(ip):
        # Per-IP burst cap (see _collect_throttle_ok): shed the flood cheaply,
        # before parsing the body or touching Supabase.
        return Response(status_code=429, headers={"retry-after": "60"})
    try:
        payload = json.loads(await request.body() or b"{}")
    except Exception:
        return Response(status_code=400)

    if isinstance(payload, dict):
        events = payload.get("events")
    elif isinstance(payload, list):
        events = payload
    else:
        events = [payload]
    if not isinstance(events, list) or not events:
        return Response(status_code=204)

    anon = _mm_clamp(request.cookies.get(_MM_ANON_COOKIE), 64)
    mint = anon is None
    if mint:
        anon = str(uuid.uuid4())
    ua = _mm_clamp(request.headers.get("user-agent") or "", 256)

    rows: list = []
    for e in events[:_MM_MAX_BATCH]:
        if not isinstance(e, dict):
            continue
        etype = _mm_clamp(e.get("type"), 32)
        if not etype or etype not in _MM_EVENT_TYPES:
            continue
        meta = e.get("meta")
        if not isinstance(meta, dict):
            meta = None
        else:
            try:
                if len(json.dumps(meta, default=str)) > 2000:
                    meta = None
            except Exception:
                meta = None
        client_ts = None
        try:
            ms = float(e.get("t") or 0)
            if 0 < ms < 4102444800000:
                client_ts = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
        tk = e.get("ticker")
        rows.append({
            "type": etype,
            "site": _mm_clamp(e.get("site"), 16) or "macro",
            "path": _mm_clamp(e.get("path"), 512),
            "ref": _mm_clamp(e.get("ref"), 512),
            "ticker": (str(tk).upper()[:64] if tk else None),
            "dwell_ms": _mm_int(e.get("dwell_ms"), 0, 86400000),
            "scroll": _mm_int(e.get("scroll"), 0, 100),
            "fp": _mm_clamp(e.get("fp"), 64),
            "session_id": _mm_clamp(e.get("sid"), 64),
            "visitor_id": anon,
            "user_id": None,
            "ip": ip,
            "ua": ua,
            "client_ts": client_ts,
            "meta": meta,
        })

    # Registered visitors: pull the shared Supabase session token off the cookie and
    # attribute the batch to their verified user (done inside the background task so
    # the beacon still returns immediately; anonymous visitors are unaffected).
    # Loopback / private / unspecified client IPs (same-box health checks, SSR, uptime
    # probes) are not real visitors — skip the insert so they never land as phantom
    # '(unknown)'-geo rows that geo-enrich can't resolve.
    if rows and _mm_is_loggable_ip(ip):
        access_token = _mm_supabase_access_token(request)
        background.add_task(_mm_analytics_insert, rows, access_token)

    resp = Response(status_code=204, headers={"cache-control": "no-store"})
    if mint:
        resp.set_cookie(
            _MM_ANON_COOKIE, anon, max_age=63072000, path="/",
            domain=(MM_COOKIE_DOMAIN or None), httponly=True, secure=True, samesite="lax",
        )
    return resp


@app.get("/api/overlay")
def overlay():
    """The intraday live overlay the nightly/fast loop emits (read-through)."""
    f = _live_artifact("overlay.json")
    if not f.exists():
        raise HTTPException(503, "overlay not built yet")
    return JSONResponse(json.loads(f.read_text()))


def _live_artifact(name: str) -> Path:
    """Prefer the VPS-owned store, with a development/back-compat fallback."""
    primary = LIVE / name
    return primary if primary.exists() else SITE / "live" / name


@app.get("/api/status")
def status() -> dict:
    """At-a-glance health of the VPS loops — the freshness each cron is producing.

    Pure read-only (file mtimes + emitted stamps); no privileged calls. Lets you (or a
    monitor) see if any loop has silently stopped: the 3-min site pull, the 5-min live
    overlay, or the daily Terminal-data refresh.
    """
    import time

    now = time.time()

    def age_min(p: Path):
        try:
            return round((now - p.stat().st_mtime) / 60, 1)
        except Exception:
            return None

    checks: dict = {}

    # site — the 3-min macro-update pull loop
    try:
        ctime = subprocess.check_output(
            ["git", "-C", str(REPO), "log", "-1", "--format=%cI"], text=True
        ).strip()
    except Exception:
        ctime = None
    checks["site"] = {"commit": _commit(), "commit_time": ctime}

    # VPS-owned live lanes. The external store is primary; local/test installs
    # continue to read the historical SITE/live location.
    for key, filename in (
        ("overlay", "overlay.json"),
        ("risk_state", "risk_state.json"),
        ("china_risk_state", "china_risk_state.json"),
        ("quotes", "quotes.json"),
        ("basket_pulse", "basket_pulse.json"),
        ("flow_pulse", "flow_pulse.json"),
        ("release_publications", "release_publications.json"),
        ("orchestrator", "orchestrator_status.json"),
    ):
        artifact = _live_artifact(filename)
        if artifact.exists():
            try:
                data = json.loads(artifact.read_text())
                checks[key] = {
                    "schema": data.get("schema"),
                    "built": data.get("built") or data.get("updated_at") or data.get("as_of"),
                    "age_min": age_min(artifact),
                }
                if key == "overlay":
                    checks[key].update({"n": data.get("n"), "fresh": data.get("n_fresh")})
                elif key == "quotes":
                    meta = data.get("meta") or {}
                    checks[key].update(
                        {
                            "requested": meta.get("requested"),
                            "resolved": meta.get("resolved"),
                        }
                    )
                elif key == "release_publications":
                    event_status: dict[str, int] = {}
                    max_lag_min = 0.0
                    now_utc = datetime.fromtimestamp(now, tz=timezone.utc)
                    for event in data.get("events") or []:
                        state = str(event.get("status") or "unknown")
                        event_status[state] = event_status.get(state, 0) + 1
                        if state not in (
                            "awaiting_publication",
                            "published_unparsed",
                            "verification_delayed",
                        ):
                            continue
                        try:
                            scheduled = datetime.fromisoformat(
                                f"{event['date']}T{event['time_et']}:00"
                            ).replace(tzinfo=ZoneInfo("America/New_York"))
                            max_lag_min = max(
                                max_lag_min,
                                (now_utc - scheduled.astimezone(timezone.utc))
                                .total_seconds()
                                / 60,
                            )
                        except (KeyError, TypeError, ValueError):
                            pass
                    checks[key].update(
                        {
                            "due": len(data.get("due") or []),
                            "published": len(data.get("publications") or []),
                            "verified_publications": sum(
                                1
                                for publication in (data.get("publications") or [])
                                if publication.get("data_ready") is True
                            ),
                            "unparsed_publications": sum(
                                1
                                for publication in (data.get("publications") or [])
                                if publication.get("status") == "published_unparsed"
                                or (
                                    publication.get("data_ready") is False
                                    and publication.get("parser")
                                )
                            ),
                            "event_status": event_status,
                            "source_errors": sum(
                                1
                                for source in (data.get("source_health") or [])
                                if source.get("status") == "error"
                            ),
                            "max_publication_lag_min": round(max_lag_min, 1),
                            "schedule_status": (
                                (data.get("schedule_coverage") or {}).get("status")
                            ),
                            "missing_schedule_types": (
                                (data.get("schedule_coverage") or {}).get(
                                    "missing_or_too_distant"
                                )
                                or []
                            ),
                        }
                    )
                elif key == "orchestrator":
                    lanes = {}
                    for lane_name, lane in (data.get("lanes") or {}).items():
                        finished = lane.get("finished_at")
                        lane_age = None
                        if finished:
                            try:
                                stamp = datetime.fromisoformat(str(finished).replace("Z", "+00:00"))
                                lane_age = round(
                                    (datetime.now(timezone.utc) - stamp.astimezone(timezone.utc))
                                    .total_seconds()
                                    / 60,
                                    1,
                                )
                            except (TypeError, ValueError):
                                pass
                        lanes[lane_name] = {
                            "ok": lane.get("ok"),
                            "finished_at": finished,
                            "age_min": lane_age,
                        }
                    checks[key]["lanes"] = lanes
            except Exception as e:  # noqa: BLE001
                # Coarsen the client-facing error: str(e) on a FileNotFoundError /
                # JSON parse error echoes the absolute artifact path to any anonymous
                # caller (this endpoint is public, unauthenticated). Keep the real
                # detail server-side; monitoring still sees WHICH check failed via the
                # per-check key + age_min. (CWE-209, same class as PR #3615.)
                log.warning("status: %s artifact unreadable (%s): %s", key, artifact, e)
                checks[key] = {"error": "unavailable", "age_min": age_min(artifact)}
        else:
            checks[key] = {"status": "missing"}

    # terminal_data — the daily Terminal-data refresh loop
    if TERMINAL_MANIFEST.exists():
        try:
            d = json.loads(TERMINAL_MANIFEST.read_text())
            checks["terminal_data"] = {
                "as_of": d.get("as_of"),
                "symbols": len(d.get("symbols", {})),
                "age_min": age_min(TERMINAL_MANIFEST),
            }
        except Exception as e:  # noqa: BLE001
            # Coarsen the client-facing error (see the live-lane branch above); the
            # raw str(e) would leak the manifest's absolute path to anonymous callers.
            log.warning("status: terminal_data manifest unreadable (%s): %s", TERMINAL_MANIFEST, e)
            checks["terminal_data"] = {"error": "unavailable"}
    else:
        checks["terminal_data"] = {"status": "missing"}

    # Top-level commit = the running process's build (same contract as /api/health);
    # the live checkout sha is already reported by checks["site"] above.
    return {"status": "ok", "commit": _PROCESS_COMMIT, "checks": checks}


# ---- auth: secretless — verify the access token against Supabase ------------
def require_user(authorization: str | None = Header(default=None)) -> dict:
    """Verify a Supabase access token without any server-side secret.

    Calls Supabase's ``GET /auth/v1/user`` with the bearer token + the public
    anon key. Valid token -> 200 + the user record; bad/expired -> 401. No JWT
    secret to store or leak; the trade-off is one short upstream call per
    request (fine at MVP scale; cache later if needed).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    token = authorization.split(" ", 1)[1]
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/user",
        headers={"Authorization": f"Bearer {token}", "apikey": SUPABASE_ANON_KEY},
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise HTTPException(401, f"invalid token ({e.code})") from None
    except Exception as e:  # noqa: BLE001 - network/upstream failure, not the user's fault
        log.warning("auth check upstream failure (%s)", e)
        raise HTTPException(502, "auth check failed, please try again") from None


def require_site_full_user(user: dict = Depends(require_user)) -> dict:
    """Registered user now; site_full user when the paid launch switch is armed."""
    from app.paywall import enforce_site_full  # noqa: PLC0415
    return enforce_site_full(user)


def _user_display_name(user: dict) -> str | None:
    """Return the best non-empty profile name from a Supabase user record."""
    metadata = user.get("user_metadata") or user.get("raw_user_meta_data") or {}
    if not isinstance(metadata, dict):
        return None
    for key in ("display_name", "name", "full_name"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    first = metadata.get("first_name") or metadata.get("given_name")
    last = metadata.get("last_name") or metadata.get("family_name")
    parts = [value.strip() for value in (first, last)
             if isinstance(value, str) and value.strip()]
    return " ".join(parts) or None


@app.get("/api/me")
def me(user: dict = Depends(require_user)) -> dict:
    """Whoami + entitlement + chat budget.

    {id, name, email, role, tier, features, status, current_period_end, chat_budget}.
    Entitlement fields fail-safe to the free default; chat_budget mirrors
    /api/brain/me's quota shape.
    """
    out: dict[str, Any] = {
        "id": user.get("id"),
        "name": _user_display_name(user),
        "email": user.get("email"),
        "role": user.get("role"),
    }
    user_id = user.get("id") or user.get("email") or ""
    try:
        from app import billing  # noqa: PLC0415
        out.update(billing.read_entitlement(user_id))
    except Exception:  # noqa: BLE001
        out.update({"tier": "free", "features": [], "status": "none", "current_period_end": None})
    try:
        gw = _brain_module()
        q = gw.get_user_quotas(user_id, root=REPO, user_email=(user.get("email") or "").strip().lower())
        out["chat_budget"] = q.get("quotas")
        if q.get("tier") == "unlimited":  # operator allowlist — surface the uncapped tier
            out["tier"] = "unlimited"
    except Exception:  # noqa: BLE001
        out["chat_budget"] = None
    return out


# Wire tier -> DISPLAY name (rendered by account.js as the plan pill). Two keys, one label:
# 'essential' is the wire value config/plans.yml stores now, 'insider' is what rows written
# before the rename still carry, and BOTH are the product the catalog names "Essential"
# (config/plans.yml products.essential.name — app/billing_emails.plan_name() reads it, so a
# receipt said "Essential" while this pill said "Insider").
_PLAN_LABELS = {"free": "Free", "essential": "Essential", "insider": "Essential",
                "pro": "Pro", "unlimited": "Unlimited"}


@app.get("/api/account")
def account(user: dict = Depends(require_user)) -> dict:
    """Plan-display payload for the shared account.js card — macro-hosted, so the macro site
    no longer depends on the Terminal repo for plan display (masterplan §3.2 / MNZ-OD4)."""
    user_id = user.get("id") or user.get("email") or ""
    ent = {"tier": "free", "features": [], "status": "none", "current_period_end": None}
    try:
        from app import billing  # noqa: PLC0415
        ent = billing.read_entitlement(user_id)
    except Exception:  # noqa: BLE001
        pass
    tier = ent["tier"]
    return {
        "authenticated": True,
        "name": _user_display_name(user),
        "email": user.get("email"),
        "email_confirmed": bool(user.get("email_confirmed_at") or user.get("confirmed_at")),
        "tier": tier,
        "plan_label": _PLAN_LABELS.get(tier, tier.title()),
        "status": ent["status"],
        "features": ent["features"],
        "current_period_end": ent["current_period_end"],
        # Billing cadence for the plan card ('monthly'|'annual'); None for free/comp. read_entitlement
        # returns it, but this handler rebuilds the payload explicitly, so it must be listed here.
        "interval": ent.get("interval"),
        # Display preferences, the read side of POST /api/account/prefs (app/account_prefs.py).
        # account.js::applyPrefs has always looked for `prefs` and never found it; the values
        # ride the auth record require_user already fetched, so this costs no extra call.
        "prefs": {
            "lang": (user.get("user_metadata") or {}).get("lang"),
            "theme": (user.get("user_metadata") or {}).get("theme"),
        },
        "plans_url": "/plans.html",
    }


# ---------------------------------------------------------------------------
# /api/ask — interrogable, cited, never-advising brain (W8b PR2)
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., max_length=500, description="Plain-language question (max 500 chars)")
    context_ticker: str | None = Field(None, description="Optional ticker to focus the query (e.g. 'NVDA')")


@app.post("/api/ask")
def ask_brain(body: AskRequest, user: dict = Depends(require_site_full_user)) -> dict:
    """Ask the Neural Web brain a question.

    Read-only cortex tools; write tools are absent from the schema (Article 1).
    Returns a cited, non-advising answer with is_context_only=True.

    Key-optional: when ANTHROPIC_API_KEY is absent, returns mode='memo-quote'
    (degraded=True) — a relevant excerpt from the committed cortex memo.

    Per-user hourly quota: ASK_BRAIN_HOURLY_QUOTA (default 10).
    Per-day global quota:  ASK_BRAIN_DAILY_QUOTA  (default 200).
    Both fail-open to memo-quote on I/O errors.
    """
    try:
        from engine.neuralweb.ask_brain import ask  # noqa: PLC0415
    except ImportError as exc:
        log.warning("ask_brain module unavailable (%s)", exc)
        raise HTTPException(503, "brain service unavailable") from exc

    user_id = user.get("id") or user.get("email") or "unknown"
    result = ask(
        question=body.question,
        user_id=user_id,
        context_ticker=body.context_ticker,
        root=REPO,
    )
    return result


@app.post("/api/ask/stream")
def ask_brain_stream(body: AskRequest, user: dict = Depends(require_site_full_user)):
    """SSE streaming variant of /api/ask.

    Tool-calling turns run synchronously; the final synthesis turn is streamed
    as text/event-stream.  Each event is a JSON object:

        data: {"delta": "..text chunk.."}
        data: {"done": true, "tool_call_census": {...}, "is_context_only": true}

    On quota/key failure a single event with degraded=True is yielded.
    On advice-pattern detection, a filtered=True event replaces the delta stream.
    """
    try:
        from engine.neuralweb.ask_brain import ask_stream  # noqa: PLC0415
    except ImportError as exc:
        log.warning("ask_brain module unavailable (%s)", exc)
        raise HTTPException(503, "brain service unavailable") from exc

    user_id = user.get("id") or user.get("email") or "unknown"

    def _generator():
        yield from ask_stream(
            question=body.question,
            user_id=user_id,
            context_ticker=body.context_ticker,
            root=REPO,
        )

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx/Caddy buffering
        },
    )


# ---------------------------------------------------------------------------
# /api/brain/* — MNZ-W6a brain gateway (§3.5 + Amendment 2)
# ---------------------------------------------------------------------------

class BrainChatRequest(BaseModel):
    message: str = Field(..., max_length=2000, description="User message (max 2000 chars)")
    lane: str = Field("fast", description="'fast' or 'pro'")
    thread_id: str | None = Field(None, description="Optional thread id for conversation continuity")
    history: list[dict] | None = Field(None, description="Client-sent fallback history (max 12 turns; used only when thread store is absent)")
    context: dict | None = Field(None, description="Optional page/symbol context hint")
    mode: str = Field("chat", description="'chat' (default) or 'research' (W6b Deep Research — forces pro lane, raises tool budget, structured multi-section cited report; requires pro quota)")
    images: list[str] | None = Field(None, max_length=4, description="Optional image attachments (W6c vision) — base64 data URIs or https URLs; served by a vision model (Haiku on Fast, Opus on Pro). Invalid/oversized dropped. Max 4.")

    @field_validator("images")
    @classmethod
    def _bound_images(cls, v: list[str] | None) -> list[str] | None:
        """Drop oversized image strings at parse time so a giant payload can't ride in.

        The client downscales to ~1024px JPEGs (typically <300KB); ~7M chars ≈ 5MB
        decoded is a generous per-item ceiling. The gateway's _image_blocks re-checks
        media type + a 3.5MB decoded cap; this is the outer body-size backstop.
        """
        if not v:
            return v
        return [s for s in v if isinstance(s, str) and len(s) <= 7_000_000][:4]


_SSE_BRAIN_HEADERS = {
    "Cache-Control": "no-cache",
    "X-Accel-Buffering": "no",
}

# Idle-cull guard + run durability for the brain SSE stream — both now live in
# app/brain_runs.py, which owns the pump thread that used to be inlined here.
#
# The brain generator has long DEAD-AIR gaps with zero bytes on the wire: the
# blocking tool-calling turns (the model thinks for 10-15s before the first
# `tool` event) and — the big one — synthesis, which is BUFFERED server-side
# (the advice-filter must run on the full answer before any delta can be sent),
# so a slow model (a DeepSeek fallback, a long research report) can go 40-60s
# without emitting a single byte. An idle SSE socket that quiet gets culled by a
# proxy / the browser / an intermediate (the tape websocket already ships a 20s
# heartbeat for exactly this reason — see app/tape.py), so brain_runs.follow()
# emits `: keepalive` comments through every gap.
#
# The keepalive alone was never enough: it keeps a LIVE socket warm, but cannot
# help a socket that is gone (the tab was backgrounded, the phone slept, the
# laptop lid closed). brain_runs.start() therefore detaches the generator from the
# connection entirely — the turn finishes, buffers, and persists to the thread
# regardless — and the client re-attaches with GET /api/brain/runs/{id}/stream.


def _brain_module():
    """Lazy import brain_gateway; raises HTTP 503 if unavailable."""
    try:
        from engine.neuralweb import brain_gateway  # noqa: PLC0415
        return brain_gateway
    except ImportError as exc:
        log.warning("brain_gateway unavailable (%s)", exc)
        raise HTTPException(503, "brain service unavailable") from exc


# ── Brain security: burst throttle + device-linked identity (PART A/B) ─────────
# Burst throttle: an in-memory per-user sliding window shared across chat + stream.
# max 10 requests / 60s → 429. Applied BEFORE the quota check so a throttled request
# does not consume quota. The dict is capped so it can never grow unbounded.
_BRAIN_THROTTLE_MAX = 10
_BRAIN_THROTTLE_WINDOW = 60.0
_BRAIN_THROTTLE_CAP = 5000
_brain_throttle: dict[str, deque] = {}
_brain_throttle_lock = threading.Lock()


def _brain_throttle_check(user_id: str) -> None:
    """Raise 429 when user_id exceeds the sliding-window request budget. Prunes on access."""
    now = time.monotonic()
    cutoff = now - _BRAIN_THROTTLE_WINDOW
    with _brain_throttle_lock:
        dq = _brain_throttle.get(user_id)
        if dq is None:
            if len(_brain_throttle) >= _BRAIN_THROTTLE_CAP:
                # Evict the oldest-inserted entry (dict preserves insertion order).
                try:
                    _brain_throttle.pop(next(iter(_brain_throttle)))
                except StopIteration:
                    pass
            dq = deque()
            _brain_throttle[user_id] = dq
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= _BRAIN_THROTTLE_MAX:
            raise HTTPException(429, detail={"error": "rate_limited", "note": "slow down"})
        dq.append(now)


def _brain_identity(request: Request) -> tuple[str, str, str]:
    """Derive (aid, ip, device_key_hash) for the brain request.

    aid    = the mm_aid first-party visitor cookie (empty when absent).
    ip     = the real client IP (EO-Client-IP aware, via _mm_client_ip).
    TRUSTED PROXY OVERRIDE: the Terminal's server-side proxy forwards the real visitor's
    identity as x-mm-aid / x-mm-ip. We accept those headers ONLY when the request carries
    the shared BRAIN_PROXY_SECRET — a source-IP check is NOT enough: macro-api sits behind
    Caddy on 127.0.0.1, so EVERY public request appears to originate from 127.0.0.1 and a
    browser could otherwise forge a fresh device per request. The secret is known only to
    the co-located Terminal service; public traffic can't produce it (and Caddy strips
    x-mm-* on the public hosts as defense-in-depth). No secret configured → never trust the
    headers (dashboard traffic reads its own cookie/IP directly, which is correct).
    device_key = 'aid:<aid>' when aid present, else 'ip:<ip>' when ip known, else ''.
    Returns the sha256[:16] hash of device_key (empty string when device_key is empty).
    """
    aid = request.cookies.get(_MM_ANON_COOKIE) or ""
    ip = _mm_client_ip(request)

    secret = os.environ.get("BRAIN_PROXY_SECRET", "")
    supplied = (request.headers.get("x-mm-proxy-secret") or "")
    if secret and hmac.compare_digest(supplied, secret):
        hdr_aid = (request.headers.get("x-mm-aid") or "").strip()
        if hdr_aid:
            aid = hdr_aid
        hdr_ip = (request.headers.get("x-mm-ip") or "").strip()
        if hdr_ip:
            ip = hdr_ip

    if aid:
        device_key = "aid:" + aid
    elif ip and ip != "unknown":
        device_key = "ip:" + ip
    else:
        device_key = ""

    device_hash = hashlib.sha256(device_key.encode()).hexdigest()[:16] if device_key else ""
    return aid, ip, device_hash


def _brain_guest_identity(request: Request) -> tuple[str, str, str]:
    """Derive (user_id, aid_hash, ip_hash) for a GUEST (anonymous) brain request.

    Unlike _brain_identity (which collapses to ONE device key), a guest needs BOTH the cookie
    and the IP hashed SEPARATELY so the quota is debited against each ledger independently
    (the per cookie + IP anti-farm). Reuses the same aid/ip source + trusted-proxy override.
    user_id = 'guest:<aid>' (or 'guest:ip:<iphash>' when no cookie, else 'guest:anon') — NEVER
    a Supabase id, so it can never collide with a real user's ledger."""
    aid, ip, _ = _brain_identity(request)
    aid_hash = hashlib.sha256(("aid:" + aid).encode()).hexdigest()[:16] if aid else ""
    ip_hash = (hashlib.sha256(("ip:" + ip).encode()).hexdigest()[:16]
               if ip and ip != "unknown" else "")
    if aid:
        user_id = "guest:" + aid[:48]
    elif ip_hash:
        user_id = "guest:ip:" + ip_hash
    else:
        user_id = "guest:anon"
    return user_id, aid_hash, ip_hash


def _guest_access_enabled() -> bool:
    """True iff the operator has turned anonymous free Fast access ON (gitignored config)."""
    try:
        return bool(_brain_module()._guest_cfg(REPO).get("enabled"))
    except Exception:  # noqa: BLE001 — config/module trouble must fail CLOSED (no guest access)
        return False


def _brain_user_or_guest(request: Request,
                         authorization: str | None = Header(default=None)) -> dict:
    """Auth for the public brain routes: a verified Supabase user when a valid Bearer is sent;
    otherwise, when guest access is ENABLED, a synthetic guest identity; else 401.

    Security invariants:
      * A real, valid token ALWAYS wins (verified via require_user's secretless check) — the
        guest path is only reached on a MISSING/INVALID token (401), never a transient 502.
      * A guest's email is ALWAYS '' → the internals/unlimited allowlists can never match a
        guest, and the CXI-R23a internals tools stay off.
      * Guests are marked with _is_guest=True and carry their split cookie/IP hashes.
    Returns a user dict shaped like require_user's, plus _is_guest/_guest_aid/_guest_ip.
    """
    try:
        user = require_user(authorization)
        user["_is_guest"] = False
        user["_guest_aid"] = ""
        user["_guest_ip"] = ""
        return user
    except HTTPException as exc:
        # Only a bad/absent token (401) may degrade to guest; a 502 (upstream auth down) or any
        # other status is a real failure and must surface unchanged.
        if exc.status_code != 401 or not _guest_access_enabled():
            raise
    guest_id, aid_hash, ip_hash = _brain_guest_identity(request)
    return {"id": guest_id, "email": "", "_is_guest": True,
            "_guest_aid": aid_hash, "_guest_ip": ip_hash}


def _brain_track_event(aid: str, ip: str, user_id: str) -> None:
    """Fire-and-forget admin cross-tracking row (type 'brain_chat'), mirroring the beacon's
    row columns. If the analytics table's type CHECK rejects it, the insert silently no-ops
    (_mm_analytics_insert never raises)."""
    row = {
        "type": "brain_chat",
        "site": "macro",
        "path": None,
        "ref": None,
        "ticker": None,
        "dwell_ms": None,
        "scroll": None,
        "fp": None,
        "session_id": None,
        "visitor_id": (aid or None),
        "user_id": (user_id if user_id and user_id != "unknown" else None),
        "ip": ip,
        "ua": None,
        "client_ts": None,
        "meta": None,
    }
    _mm_analytics_insert([row])


@app.post("/api/brain/chat")
def brain_chat(body: BrainChatRequest, request: Request, background: BackgroundTasks,
               user: dict = Depends(_brain_user_or_guest)):
    """Brain chat — non-streaming.

    Verified users AND (when guest access is enabled) anonymous guests. Guests get the free
    Fast lane only, day-capped per cookie+IP; Pro/research/vision are locked for them.

    POST body: {message, lane?, thread_id?, history?, context?}
    Response: {ok, reply, citations, annotations?, symbol?, lane, model, thread_id,
               quota: {lane, remaining, limit, period}, filtered, degraded, is_context_only}
    HTTP 402 when quota exhausted; 429 when the burst throttle trips.
    """
    gw = _brain_module()
    is_guest = bool(user.get("_is_guest"))
    # mode validation: only 'chat' and 'research' are accepted
    mode = body.mode if body.mode in ("chat", "research") else "chat"
    # research mode forces pro lane (gateway also enforces this, but be explicit here)
    lane = "pro" if mode == "research" else (body.lane if body.lane in ("fast", "pro") else "fast")
    user_id = user.get("id") or user.get("email") or "unknown"
    # CXI-R23a: email comes ONLY from the Supabase-verified session — never body/headers, and
    # ALWAYS '' for a guest (so internals/unlimited allowlists can never match).
    user_email = (user.get("email") or "").strip().lower()

    # Burst throttle FIRST — a throttled request must not consume quota. (Guest user_id is
    # 'guest:<aid>'/'guest:ip:<h>', so throttling is per-guest-identity too.)
    _brain_throttle_check(user_id)

    # Device-linked identity (PART A): aid/ip → hashed device_key for the free-credit pool.
    aid, ip, device_hash = _brain_identity(request)
    # Best-effort admin cross-tracking event (never blocks; no-ops if the type is rejected).
    background.add_task(_brain_track_event, aid, ip, user_id)

    # History cap: max 12 turns (24 messages)
    history = (body.history or [])[:24]

    result = gw.chat(
        message=body.message,
        user_id=user_id,
        lane=lane,
        thread_id=body.thread_id,
        history=history,
        context=body.context,
        root=REPO,
        mode=mode,
        images=body.images,
        device_key=device_hash,
        user_email=user_email,
        is_guest=is_guest,
        guest_aid=user.get("_guest_aid") or "",
        guest_ip=user.get("_guest_ip") or "",
        # Analyst OS W3: stored depth/language, read off the record the auth dependency
        # already returned — ZERO extra network calls. Server-derived like user_email, so
        # the body can never set it; a guest record carries none and reads as {}.
        account_prefs=user_prefs.read_user_prefs(user),
    )

    if result.get("quota_exhausted"):
        raise HTTPException(402, detail=result)

    return result


@app.post("/api/brain/stream")
def brain_stream(body: BrainChatRequest, request: Request, background: BackgroundTasks,
                 user: dict = Depends(_brain_user_or_guest)):
    """Brain chat — SSE streaming.

    Verified users AND (when guest access is enabled) anonymous guests (free Fast lane only).
    POST body: same as /api/brain/chat.
    SSE events (always in this order):
        {"type":"meta","lane":...,"model":...,"thread_id":...,"quota":{...}}
        {"type":"tool","name":"..."}            (progress, 0+ — during tool-calling phase)
        {"type":"annotate","symbol":...,...}    (when annotate_chart called, 0+)
        {"type":"delta","text":"..."}           (full buffered answer, after all tool turns)
        {"type":"done","citations":[...],"quota":{...},"usage":{...},"filtered":false,"degraded":false,"is_context_only":true}
    HTTP 429 when the burst throttle trips.
    """
    gw = _brain_module()
    is_guest = bool(user.get("_is_guest"))
    mode = body.mode if body.mode in ("chat", "research") else "chat"
    lane = "pro" if mode == "research" else (body.lane if body.lane in ("fast", "pro") else "fast")
    user_id = user.get("id") or user.get("email") or "unknown"
    # CXI-R23a: email comes ONLY from the verified session (never body/headers); '' for guests.
    user_email = (user.get("email") or "").strip().lower()
    guest_aid = user.get("_guest_aid") or ""
    guest_ip = user.get("_guest_ip") or ""

    # Burst throttle FIRST — a throttled request must not consume quota.
    _brain_throttle_check(user_id)

    # Device-linked identity (PART A) + admin cross-tracking event.
    aid, ip, device_hash = _brain_identity(request)
    background.add_task(_brain_track_event, aid, ip, user_id)

    history = (body.history or [])[:24]
    # Analyst OS W3: stored depth/language off the already-fetched record (no extra fetch).
    # Resolved OUTSIDE the generator so it is computed on this request's thread, not on the
    # brain_runs pump thread that may outlive the socket.
    account_prefs = user_prefs.read_user_prefs(user)

    def _gen():
        yield from gw.chat_stream(
            message=body.message,
            user_id=user_id,
            lane=lane,
            thread_id=body.thread_id,
            history=history,
            context=body.context,
            root=REPO,
            mode=mode,
            images=body.images,
            device_key=device_hash,
            user_email=user_email,
            is_guest=is_guest,
            guest_aid=guest_aid,
            guest_ip=guest_ip,
            account_prefs=account_prefs,
        )

    # The turn is registered as a server-side RUN before a single byte goes out.
    # brain_runs pumps the generator on its own thread into an ordered event buffer,
    # so the answer is produced (and persisted to the thread) whether or not this
    # socket survives — a backgrounded tab, a slept laptop or a culled connection no
    # longer destroys the reply. `follow` streams that buffer to the current client,
    # injecting `: keepalive` comments through the brain's dead-air gaps (blocking
    # tool turns + buffered synthesis) so an idle-culling proxy never cuts us off.
    # The leading `run` event hands the client the id + cursor it needs to re-attach
    # via GET /api/brain/runs/{run_id}; it is deliberately NOT buffered, so a buffer
    # index stays equal to the client's count of received brain events.
    run = brain_runs.start(_gen(), user_id=user_id, thread_id=body.thread_id,
                           lane=lane, mode=mode)

    def _attach():
        yield brain_runs.run_event(run)
        yield from brain_runs.follow(run)

    return StreamingResponse(_attach(), media_type="text/event-stream", headers=_SSE_BRAIN_HEADERS)


@app.get("/api/brain/runs/active")
def brain_runs_active(user: dict = Depends(_brain_user_or_guest)):
    """Recent brain runs for the caller, newest first.

    The recovery path for a signed-in client that lost its stored run id (cleared
    storage, a second tab, another device). Response: {runs: [{run_id, thread_id,
    lane, mode, done, events, ...}]}.

    NEVER enumerates for a GUEST. A guest principal is not a user: it is
    `guest:<mm_aid cookie>`, or `guest:ip:<hash>` / `guest:anon` when there is no
    cookie — so every anonymous visitor behind one office/CGNAT egress IP shares it,
    and the cookie half is client-settable. Listing run ids to that principal would
    hand one visitor another's question and answer verbatim, which is a capability the
    quota ledger it was designed for never granted (guests write no thread rows at
    all). A guest's own run id lives in its browser and nowhere else; a 128-bit
    unguessable id IS the guest's capability, and it is only ever sent to the client
    that started the run. The throttle applies here because this is the one run route
    that could otherwise be polled to discover ids.
    """
    if user.get("_is_guest"):
        return {"runs": []}
    user_id = user.get("id") or user.get("email") or "unknown"
    _brain_throttle_check(user_id)
    return {"runs": brain_runs.active_for(user_id)}


@app.get("/api/brain/runs/{run_id}")
def brain_run_status(run_id: str, user: dict = Depends(_brain_user_or_guest)):
    """Status of one run (no stream). 404 when unknown, expired, or not the caller's.

    Lets a returning client decide cheaply whether to re-attach (still running),
    replay (finished inside the TTL), or fall back to re-reading the thread.
    """
    user_id = user.get("id") or user.get("email") or "unknown"
    run = brain_runs.get(run_id, user_id)
    if run is None:
        raise HTTPException(404, "run not found or expired")
    return run.status()


@app.get("/api/brain/runs/{run_id}/stream")
def brain_run_resume(run_id: str, cursor: int = 0,
                     user: dict = Depends(_brain_user_or_guest)):
    """Re-attach to a run's SSE stream from `cursor` (SSE).

    Replays every buffered event from `cursor` at once, then follows the run live to
    its `done`. No quota is debited and the model is not re-run — this is a second
    reader on a turn that is already paid for. 404 when unknown/expired/not owned.
    """
    user_id = user.get("id") or user.get("email") or "unknown"
    run = brain_runs.get(run_id, user_id)
    if run is None or run.cancelled:
        # A cancelled run would otherwise `follow` to an instant empty body, and the
        # client would spend its whole backoff budget re-attaching to nothing.
        raise HTTPException(404, "run not found or expired")
    return StreamingResponse(brain_runs.follow(run, cursor=max(0, cursor)),
                             media_type="text/event-stream", headers=_SSE_BRAIN_HEADERS)


@app.post("/api/brain/runs/{run_id}/cancel")
def brain_run_cancel(run_id: str, user: dict = Depends(_brain_user_or_guest)):
    """Mark a run cancelled (the user pressed Stop) so it is not re-attached to.

    The in-flight provider call cannot be interrupted, so the gateway still finishes
    and still persists what it produced — same as today's Stop. 404 when unknown.
    """
    user_id = user.get("id") or user.get("email") or "unknown"
    if not brain_runs.cancel(run_id, user_id):
        raise HTTPException(404, "run not found or expired")
    return {"ok": True}


@app.get("/api/brain/me")
def brain_me(request: Request, user: dict = Depends(_brain_user_or_guest)):
    """Return tier + quota status for both lanes.

    Verified users get {tier, quotas:{fast,pro}}. When guest access is enabled, an anonymous
    caller gets {tier:'guest', quotas:{fast:{remaining,limit,period:'day'}, pro:{0,0,'day'}}}
    so the widget shows the chat UI (not the sign-in gate). When guest access is DISABLED, an
    anonymous caller gets today's 401 exactly (via _brain_user_or_guest re-raising).
    """
    gw = _brain_module()
    if user.get("_is_guest"):
        return gw.get_guest_quotas(user.get("_guest_aid") or "", user.get("_guest_ip") or "", root=REPO)
    user_id = user.get("id") or user.get("email") or "unknown"
    # email from the Supabase-verified session only (never body/headers) — drives the
    # unlimited-operator UI unlock, matching the backend's BRAIN_UNLIMITED_ALLOWLIST bypass.
    user_email = (user.get("email") or "").strip().lower()
    return gw.get_user_quotas(user_id, root=REPO, user_email=user_email)


# ── CMX W2 — Chart state mirror (Terminal → gateway; masterplan §2.2) ──────────
# The Terminal proxies the live chart's state here on change; the Brain's read_chart_state
# tool reads it back. Telemetry, NOT a chat turn: no quota debit, no throttle.
# Auth is identical to the other brain routes: require_user verifies the Bearer the Terminal
# proxy injects for the REAL visitor, so the session keys by that verified user_id — the same
# user_id the chat route's read_chart_state reads under. (aid/ip device identity is only
# needed by the chat routes' free-credit pool, so it is not derived here.)

_CHART_STATE_BODY_MAX = 64 * 1024   # ~64KB serialized body cap (reject bigger states)


class ChartStateRequest(BaseModel):
    client: str = Field(..., max_length=32, description="Chart client id, e.g. 'terminal'")
    session: dict = Field(..., description="Current chart session (symbol/tf/indicators/range/capabilities/drawings)")
    acks: list[dict] | None = Field(None, description="Optional command acks with fit metrics")

    @model_validator(mode="after")
    def _bound_body(self) -> "ChartStateRequest":
        """Reject an oversized payload — the session/acks JSON must fit the body cap."""
        try:
            size = len(json.dumps({"session": self.session, "acks": self.acks or []}, default=str))
        except Exception:  # noqa: BLE001 — unserializable → treat as too large/bad
            raise ValueError("chart state not serializable")
        if size > _CHART_STATE_BODY_MAX:
            raise ValueError("chart state too large")
        return self


@app.post("/api/brain/chart/state")
def brain_chart_state(body: ChartStateRequest,
                      user: dict = Depends(require_user)):
    """Store the latest chart state for this user + client (CMX W2, masterplan §2.2).

    POST body: {client, session, acks?}. Auth: verified user (401 without a valid session).
    No quota is debited — this is telemetry the Brain reads via read_chart_state.
    Response: {ok: true}.
    """
    gw = _brain_module()
    user_id = user.get("id") or user.get("email") or "unknown"
    client = (body.client or "").strip().lower()[:32] or "terminal"
    gw.put_chart_state(user_id, client, body.session)
    return {"ok": True}


@app.get("/api/brain/threads")
def brain_threads(user: dict = Depends(require_user)):
    """Return thread list for the authenticated user.

    Response: {threads: [{id, title, lane, updated_at}]}
    Empty list when thread store is absent or user has no threads.
    """
    gw = _brain_module()
    user_id = user.get("id") or user.get("email") or "unknown"
    threads = gw.list_threads(user_id)
    return {"threads": threads}


@app.get("/api/brain/threads/{thread_id}")
def brain_thread_detail(thread_id: str, user: dict = Depends(require_user)):
    """Return thread + messages for thread_id owned by the authenticated user.

    Response: {thread: {...}, messages: [{role, content, created_at}]}
    HTTP 404 if not found or not owner.
    """
    gw = _brain_module()
    user_id = user.get("id") or user.get("email") or "unknown"
    result = gw.get_thread(thread_id, user_id)
    if result is None:
        raise HTTPException(404, "thread not found or not authorized")
    return result


class ThreadRenameRequest(BaseModel):
    """Body for PATCH /api/brain/threads/{thread_id}. An empty/whitespace-only title
    is a 422 (validation error); a valid title is trimmed + clamped to 80 chars, matching
    the store's own normalization so the two never disagree."""
    title: str = Field(..., description="New thread title (trimmed, clamped to 80 chars)")

    @field_validator("title")
    @classmethod
    def _clean_title(cls, v: str) -> str:
        cleaned = " ".join((v or "").split()).strip()[:80]
        if not cleaned:
            raise ValueError("title must not be empty")
        return cleaned


@app.patch("/api/brain/threads/{thread_id}")
def brain_thread_rename(thread_id: str, body: ThreadRenameRequest,
                        user: dict = Depends(require_user)):
    """Rename a thread owned by the authenticated user (verified user required — a guest
    or anonymous caller gets 401 via require_user; guests own no threads).

    PATCH body: {title}. Response: 200 {ok: true} | 404 {ok: false} when the thread is
    absent or not owned | 422 when the title is empty/invalid.
    """
    gw = _brain_module()
    user_id = user.get("id") or user.get("email") or "unknown"
    if not gw.rename_thread(thread_id, user_id, body.title):
        return JSONResponse({"ok": False}, status_code=404)
    return {"ok": True}


@app.delete("/api/brain/threads/{thread_id}")
def brain_thread_delete(thread_id: str, user: dict = Depends(require_user)):
    """Delete a thread (and its messages) owned by the authenticated user (verified user
    required — a guest or anonymous caller gets 401 via require_user).

    Response: 200 {ok: true} | 404 {ok: false} when the thread is absent or not owned.
    """
    gw = _brain_module()
    user_id = user.get("id") or user.get("email") or "unknown"
    if not gw.delete_thread(thread_id, user_id):
        return JSONResponse({"ok": False}, status_code=404)
    return {"ok": True}


# ---------------------------------------------------------------------------
# /api/portfolio/brief — Pro-only personalized daily brief (Portfolio-Aware W1)
# ---------------------------------------------------------------------------
# The deterministic composer (engine/portfolio_brief.compose_brief) joins the signed-in
# user's holdings against the nightly portfolio_ctx.v1 artifact and renders a bilingual
# descriptive brief. Charter: research/PORTFOLIO_BRIEF_MASTERPLAN_BY_FABLE.md §1/§2/§4.
# Homes served: this endpoint (terminal Portfolio page consumes it via its proxy) + the
# Brain tool get_portfolio_brief (engine/neuralweb/brain_gateway.py). Display-tier only,
# never prescriptive; no per-user compute runs in the nightly.

_PORTFOLIO_CACHE: dict[tuple[str, float], tuple[dict, float]] = {}  # (uid,mtime) → (resp, exp)
_PORTFOLIO_CACHE_TTL = 300.0  # seconds
_PORTFOLIO_CTX_PATH = "site/data/portfolio_ctx.json"


def _portfolio_resolve_tier(uid: str) -> dict:
    """Resolve {tier, status} for a user, reusing the brain gateway's PostgREST resolver.

    The gateway already runs in-process; its _resolve_tier reads user_entitlements with
    the service-role key and fail-safes to free. Any import/lookup error → free (deny)."""
    try:
        from engine.neuralweb.brain_gateway import _resolve_tier  # noqa: PLC0415
        ent = _resolve_tier(uid, root=REPO)
        return {"tier": ent.get("tier") or "free", "status": ent.get("status") or "active"}
    except Exception:  # noqa: BLE001
        return {"tier": "free", "status": "active"}


def _portfolio_load_holdings(uid: str) -> list[dict]:
    """Load the user's holdings as compose_brief rows: {ticker, shares, entry_price}.

    Positions mode first: open portfolio_positions (status=open) → shares + entry_price
    (exactly like brain_gateway._tool_get_watchlist). When there are no open positions,
    fall back to the watchlist symbols (equal-weight; shares/entry_price None). Reads via
    the gateway's service-role _sb_get; any error → empty list (→ empty-book brief)."""
    try:
        from engine.neuralweb.brain_gateway import _sb_get  # noqa: PLC0415
        import urllib.parse as _up  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    quid = _up.quote(str(uid))

    rows: list[dict] = []
    pos_rows = _sb_get(
        f"portfolio_positions?user_id=eq.{quid}&status=eq.open"
        f"&select=ticker,shares,entry_price")
    if pos_rows:
        for r in pos_rows:
            if isinstance(r, dict) and r.get("ticker"):
                rows.append({"ticker": r.get("ticker"), "shares": r.get("shares"),
                             "entry_price": r.get("entry_price")})
    if rows:
        return rows

    # Equal-weight fallback: watchlists → watchlist_symbols.
    lists = _sb_get(f"watchlists?user_id=eq.{quid}&select=id&order=position")
    list_ids = [str(r.get("id")) for r in (lists or [])
                if isinstance(r, dict) and r.get("id") is not None]
    if list_ids:
        id_filter = ",".join(list_ids)
        sym_rows = _sb_get(
            f"watchlist_symbols?watchlist_id=in.({id_filter})"
            f"&select=symbol,position&order=position")
        seen: set = set()
        for r in (sym_rows or []):
            s = r.get("symbol") if isinstance(r, dict) else None
            if s and s not in seen:
                seen.add(s)
                rows.append({"ticker": s, "shares": None, "entry_price": None})
    return rows


@app.get("/api/portfolio/brief")
def portfolio_brief(response: Response, user: dict = Depends(require_user)):
    """Pro-only personalized daily portfolio brief (portfolio_brief.v1).

    401 (require_user) → not signed in. 403 {error:pro_required,tier} → not Pro.
    503 {error:ctx_unavailable} → the nightly ctx artifact is missing/corrupt.
    Cache: in-process per (uid, ctx-file-mtime), TTL 300s; Cache-Control private,no-store.
    """
    from datetime import date as _date  # noqa: PLC0415
    response.headers["Cache-Control"] = "private, no-store"

    uid = user.get("id") or user.get("email") or ""

    # Pro gate. status active/trialing counts as entitled (mirrors _get_allowance).
    ent = _portfolio_resolve_tier(uid)
    tier = ent.get("tier") or "free"
    status = ent.get("status") or "active"
    entitled = tier in ("pro", "unlimited") and status in ("active", "trialing")
    if not entitled:
        raise HTTPException(403, detail={"error": "pro_required", "tier": tier})

    # ctx artifact from disk (same idiom the gateway uses for site/ artifacts).
    ctx_path = REPO / _PORTFOLIO_CTX_PATH
    try:
        mtime = ctx_path.stat().st_mtime
    except OSError:
        raise HTTPException(503, detail={"error": "ctx_unavailable"}) from None

    # Per-(uid, mtime) response cache with TTL.
    now = time.monotonic()
    ckey = (uid, mtime)
    hit = _PORTFOLIO_CACHE.get(ckey)
    if hit and hit[1] > now:
        return hit[0]

    try:
        ctx = json.loads(ctx_path.read_text(encoding="utf-8"))
        if not isinstance(ctx, dict):
            raise ValueError("ctx not an object")
    except Exception:  # noqa: BLE001
        raise HTTPException(503, detail={"error": "ctx_unavailable"}) from None

    holdings = _portfolio_load_holdings(uid)

    try:
        from engine.portfolio_brief import compose_brief  # noqa: PLC0415
    except ImportError as exc:
        log.warning("portfolio_brief module unavailable (%s)", exc)
        raise HTTPException(503, "portfolio brief unavailable") from exc

    today = _date.today().isoformat()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    brief = compose_brief(ctx, holdings, today, generated_at)

    if len(_PORTFOLIO_CACHE) > 5000:
        _PORTFOLIO_CACHE.clear()
    _PORTFOLIO_CACHE[ckey] = (brief, now + _PORTFOLIO_CACHE_TTL)
    return brief


# ---------------------------------------------------------------------------
# /api/flow/* — live options-flow feed (unauthenticated read-through of R2)
# ---------------------------------------------------------------------------

# In-memory TTL cache: key → (payload_dict, fetched_at_monotonic)
_FLOW_CACHE: dict[str, tuple[dict, float]] = {}
_FLOW_CACHE_TTL = 30.0          # seconds
_FLOW_UA = "mastermind-feed/1.0"

# R2 public base URL (config-driven; falls back to env)
def _flow_r2_base() -> str:
    base = os.environ.get("R2_PUBLIC_BASE", "")
    if base:
        return base.rstrip("/")
    try:
        import yaml  # noqa: PLC0415
        _cfg_path = REPO / "config.yml"
        if _cfg_path.exists():
            with open(_cfg_path) as _f:
                _c = yaml.safe_load(_f)
            return (_c.get("r2_data_plane", {}).get("public_base") or "").rstrip("/")
    except Exception:  # noqa: BLE001
        pass
    return ""


def _flow_fetch(name: str) -> dict:
    """Fetch live_flow/<name>.json from R2 with TTL caching and stale fallback.

    Returns the parsed JSON dict.  On failure, returns last-cached dict with
    {"stale": true} merged.  Raises HTTPException(503) only if never fetched.
    """
    cached = _FLOW_CACHE.get(name)
    now = time.monotonic()

    # Fresh cache hit
    if cached is not None and (now - cached[1]) < _FLOW_CACHE_TTL:
        return cached[0]

    base = _flow_r2_base()
    if not base:
        if cached:
            return {**cached[0], "stale": True}
        raise HTTPException(503, f"flow/{name}: R2 base URL not configured")

    url = f"{base}/live_flow/{name}.json"
    req = urllib.request.Request(url, headers={"User-Agent": _FLOW_UA})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            data: dict = json.loads(resp.read())
        _FLOW_CACHE[name] = (data, now)
        return data
    except Exception:  # noqa: BLE001
        if cached:
            return {**cached[0], "stale": True}
        raise HTTPException(503, f"flow/{name} unavailable and no cached copy") from None


@app.get("/api/flow/feed")
def flow_feed() -> dict[str, Any]:
    """Live options-flow feed (events + unusual names). Unauthenticated.

    Display-tier read-through. Events are labeled heuristics — not
    directional recommendations.
    """
    return _flow_fetch("feed_current")


@app.get("/api/flow/heat")
def flow_heat() -> dict[str, Any]:
    """Options-flow sector/group heat map. Unauthenticated.

    Aggregates gross premium by sector. Display-tier context only.
    """
    return _flow_fetch("heat_current")


@app.get("/api/flow/meta")
def flow_meta() -> dict[str, Any]:
    """Live options-flow poller metadata (cadence, universe size, notes). Unauthenticated."""
    return _flow_fetch("meta")


@app.get("/api/flow/tide")
def flow_tide() -> dict[str, Any]:
    """Market tide: cumulative NCP/NPP/gross/vol per minute + sector breakdown.

    Display-tier context only. Direction labeled ~-soft (signing_source=tape).
    Schema: live_flow.tide/v1 published by the live-flow poller each cycle.
    Unauthenticated.
    """
    return _flow_fetch("tide_current")


@app.get("/api/flow/dte")
def flow_dte() -> dict[str, Any]:
    """DTE-bucket tide: cumulative NCP/NPP per minute across 5 DTE buckets
    (0d, 1_7d, 8_30d, 31_90d, 90p). Display-tier context only.
    Schema: live_flow.dte_tide/v1. Unauthenticated.
    """
    return _flow_fetch("dte_tide_current")


# Root symbol validation: [A-Z.] 1–8 chars (e.g. SPY, BRK.B, QQQ)
import re as _re
_ROOT_RE = _re.compile(r'^[A-Z.]{1,8}$')


@app.get("/api/flow/ticker/{root}")
def flow_ticker(root: str) -> dict[str, Any]:
    """Per-root options-flow drill (minute net-prem series, strike/expiry rollups,
    top contracts, day stats). Display-tier context only.
    Schema: live_flow.ticker/v1 published by the poller for the top ~40 roots.
    Unauthenticated.

    root is sanitized to [A-Z.]{1,8} — other characters return 422.
    """
    root_upper = root.upper()
    if not _ROOT_RE.match(root_upper):
        raise HTTPException(422, f"root must match [A-Z.]{{1,8}}, got: {root!r}")
    return _flow_fetch(f"tickers/{root_upper}")


# ---------------------------------------------------------------------------
# Site-access gate — /api/gate/check and /api/gate/status
# ---------------------------------------------------------------------------
try:
    from app import gate as _gate_mod  # noqa: PLC0415
except ImportError:
    _gate_mod = None  # type: ignore[assignment]


@app.get("/api/gate/check")
def gate_check(request: Request) -> Response:
    """Unauthenticated.  Called by Caddy on the origin for every inbound request.

    Returns:
      204  No Content  — ALLOW (visitor passes).
      403  text/html   — BLOCK (coming-soon page returned).

    Always sets Cache-Control: no-store and X-Gate: <verdict>.
    """
    if _gate_mod is None:
        # gate module unavailable — fail-open
        return Response(status_code=204, headers={"Cache-Control": "no-store", "X-Gate": "allow"})

    ip = _mm_client_ip(request)
    # Pass headers as a plain dict (gate.decide accepts dict-like)
    raw_headers: dict = dict(request.headers)
    verdict = _gate_mod.decide(ip, raw_headers)

    if verdict == "allow":
        return Response(
            status_code=204,
            headers={"Cache-Control": "no-store", "X-Gate": "allow"},
        )

    page_html = _gate_mod.coming_soon_page()
    return Response(
        content=page_html,
        status_code=403,
        media_type="text/html; charset=utf-8",
        headers={"Cache-Control": "no-store", "X-Gate": verdict},
    )


@app.get("/api/gate/status")
def gate_status() -> dict:
    """Unauthenticated.  Returns gate state + country-detection health for the admin panel."""
    if _gate_mod is None:
        return {"ok": False, "error": "gate module unavailable"}
    return _gate_mod.status()


# ---------------------------------------------------------------------------
# Options Hub analytics router (lane B — app/hub.py)
# Wrapped in try/except so this file stays green if hub.py lands later.
# ---------------------------------------------------------------------------
try:
    from app.hub import router as hub_router  # noqa: E402  (lane B ships app/hub.py)
    app.include_router(hub_router)
except ImportError:
    pass  # app/hub.py not yet present — hub routes unavailable until lane B merges

# ---------------------------------------------------------------------------
# Vertical Intelligence Workbench — Government Revenue Foresight.
# Read-only serving of the compact official-data artifact; no request-time model
# or procurement calculations.  Other vertical desks can reuse this router
# boundary without coupling their specialist engines to app/main.py.
# ---------------------------------------------------------------------------
try:
    from app.government_revenue import router as government_revenue_router  # noqa: E402
    app.include_router(government_revenue_router)
except Exception as _government_revenue_exc:  # noqa: BLE001
    log.warning("government revenue router not mounted: %r", _government_revenue_exc)

# ---------------------------------------------------------------------------
# Research Vault serving tier (RV W2 — app/research.py)
# /api/research/* : public catalog+search read-throughs + paid view/download gate.
# Wrapped in try/except so this file stays green if research.py lands later.
# ---------------------------------------------------------------------------
try:
    from app.research import router as research_router  # noqa: E402
    app.include_router(research_router)
except ImportError:
    pass  # app/research.py not yet present — vault routes unavailable until RV W2

# Public per-ticker event context for the static dossier layer.  The router
# delegates retrieval and immutable-receipt verification to the existing
# context-only Company Intelligence reader; it is deliberately not a signal or
# recommendation surface.
from app.company_intelligence import router as company_intelligence_router  # noqa: E402
app.include_router(company_intelligence_router)

# Filing Forensics private state transport. The public page is only a shell;
# this route enforces the same authenticated site_full entitlement as the paid
# site before reading the private Research Vault bucket.
try:
    from app.forensics import router as forensics_router  # noqa: E402
    app.include_router(forensics_router)
except ImportError:
    pass  # additive route remains unavailable if its module is absent

# BioCatalyst Intelligence serves only the worker's pointer-bound normalized
# product projection. Its router performs early site_full enforcement before
# touching the isolated read-only public generation root. This route is a paid
# product contract, so router wiring errors fail startup loudly. The route
# module also probes its heavier validation runtime at startup whenever the
# operator-provisioned public root exists; an intentionally dark absent lane
# does not couple unrelated API consumers to those optional product packages.
from app.biocatalyst import router as biocatalyst_router  # noqa: E402
app.include_router(biocatalyst_router)

# Capital Structure observed filing-state desk.  This is an authenticated
# artifact-serving boundary: it reads the verified projection only and does not
# calculate financing terms, capacity, runway, or probability in the API tier.
try:
    from app.capital_structure import router as capital_structure_router  # noqa: E402
    app.include_router(capital_structure_router)
except Exception as _capital_structure_exc:  # noqa: BLE001
    log.warning("capital structure router not mounted: %r", _capital_structure_exc)

# Warm the SHARED corpus cache off the request path (Analyst OS W4). The chat
# tool's mode="report" and the vault routes now read one process-wide copy
# (engine/research_vault/corpus.py); without this, the first report call in a
# cold process pays the full R2 download INSIDE a chat turn. Best-effort daemon
# thread: no creds / no R2 → the fetch no-ops and report mode serves excerpts.
try:
    from engine.research_vault import corpus as _rv_corpus  # noqa: E402
    from app.research import _build_store as _rv_store  # noqa: E402

    def _warm_corpus() -> None:
        try:
            conn = _rv_corpus.corpus_connection(store_factory=_rv_store)
            if conn is not None:
                conn.close()
        except Exception:  # noqa: BLE001 — warmth is optional, never load-bearing
            pass

    threading.Thread(target=_warm_corpus, name="rv-corpus-warm", daemon=True).start()
except Exception:  # noqa: BLE001
    pass

# ---------------------------------------------------------------------------
# Billing spine router (MNZ W2 — app/billing.py): /api/billing/checkout|webhook|portal.
# Included after require_user is defined (app/billing._current_user lazy-imports it),
# so there is no import cycle. Routes 503 cleanly when STRIPE_SECRET_KEY is unset.
# ---------------------------------------------------------------------------
try:
    from app.billing import router as billing_router  # noqa: E402
    app.include_router(billing_router)
except Exception as _billing_exc:  # noqa: BLE001 — never let a billing wiring error crash the whole API
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("billing router not mounted: %r", _billing_exc)

# ---------------------------------------------------------------------------
# Support intake router (SEE W1 — app/support.py): POST /api/support/ticket.
# PUBLIC by design (the contact form must work for a signed-out visitor), but it
# honours a Bearer token when one is offered — hence the mount AFTER require_user
# is defined, exactly like the billing block above (app/support._resolve_user
# lazy-imports it, so there is no import cycle). Wrapped so a wiring error can
# never crash the whole API: the worst case is that the contact form 404s while
# every other route keeps serving.
# ---------------------------------------------------------------------------
try:
    from app.support import router as support_router  # noqa: E402
    app.include_router(support_router)
except Exception as _support_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("support router not mounted: %r", _support_exc)

# ---------------------------------------------------------------------------
# Registration wall (app/regwall.py): /api/regwall/check — Caddy's second gate
# stage for all non-public HTML (operator lockdown 2026-07-24). NOTE the
# asymmetry with the blocks above: if THIS router fails to mount, gated pages
# fail CLOSED at the Caddy layer (non-2xx sub-request → redirect to the
# landing), so a wiring error here can never silently open the wall.
# ---------------------------------------------------------------------------
try:
    from app.regwall import router as regwall_router  # noqa: E402
    app.include_router(regwall_router)
except Exception as _regwall_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("regwall router not mounted (wall fails CLOSED at Caddy): %r", _regwall_exc)

# ---------------------------------------------------------------------------
# Live Tape relay (app/tape.py): GET /ws/tape — server-fanout websocket for the
# six-instrument macro.html futures tape (research/LIVE_TAPE_SCOREBOARD_MASTERPLAN.md
# Phase 1). One upstream connection (keyless Yahoo streamer) fans out to all
# browsers; a dead-upstream REST poll fallback keeps the socket serving. Wrapped
# so a wiring error can never crash the API — the page just degrades to live.js
# polling (worker/snapshot -> baked), which is the whole fallback ladder's point.
# ---------------------------------------------------------------------------
try:
    from app.tape import register_tape  # noqa: E402
    register_tape(app)
except Exception as _tape_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("tape relay not mounted (page degrades to polling): %r", _tape_exc)

# ---------------------------------------------------------------------------
# Paid site wall (app/paywall.py): /api/paywall/check — a distinct fail-closed
# entitlement stage after registration. PAYWALL_ENABLED=0 keeps it in observe/
# pass-through mode until the paid-launch prerequisites are verified. If the
# router cannot mount, Caddy receives a non-2xx and serves no protected file.
# ---------------------------------------------------------------------------
try:
    from app.paywall import router as paywall_router  # noqa: E402
    app.include_router(paywall_router)
except Exception as _paywall_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("paywall router not mounted (wall fails CLOSED at Caddy): %r", _paywall_exc)

# ---------------------------------------------------------------------------
# Account preferences (SEE W3 — app/account_prefs.py): POST /api/account/prefs.
# The server side of a call templates/account.js has been making all along. Bearer-authed
# through require_user, so it mounts AFTER that definition like the billing/support blocks.
# ---------------------------------------------------------------------------
try:
    from app.account_prefs import router as account_prefs_router  # noqa: E402
    app.include_router(account_prefs_router)
except Exception as _prefs_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("account prefs router not mounted: %r", _prefs_exc)

# ---------------------------------------------------------------------------
# Lifecycle mail sweeper (SEE W3 — app/billing_emails.py): the behaviour-triggered
# trial-ending T-2 reminder. DEFAULT OFF — register_lifecycle is a no-op unless the
# operator sets MAIL_LIFECYCLE_ENABLED (docs/ops/email-support-setup.md §5b), so this is
# inert on every machine that has not opted in, tests included. Cursor-free and
# idempotent through email_log, so a restart mid-sweep costs nothing.
# ---------------------------------------------------------------------------
try:
    from app.billing_emails import register_lifecycle as _register_lifecycle  # noqa: E402
    _register_lifecycle(app)   # logs the armed interval itself; silent when disabled
except Exception as _lifecycle_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("lifecycle mail sweeper not armed: %r", _lifecycle_exc)

# ---------------------------------------------------------------------------
# Public unsubscribe endpoint (SEE W4 — app/unsubscribe.py): POST /api/email/unsubscribe.
# PUBLIC and UNAUTHENTICATED by design, like the support intake above: the authorisation
# is the HMAC token in the URL, and RFC 8058 one-click cannot present a session. Mounted
# in a try/except like every block above — but note the failure mode is not symmetric
# with the wall's: if THIS router does not mount, marketing mail can still go out while
# the unsubscribe link 404s, which is the one combination that is a compliance problem
# rather than a degraded feature. It is logged at ERROR for that reason.
# ---------------------------------------------------------------------------
try:
    from app.unsubscribe import router as unsubscribe_router  # noqa: E402
    app.include_router(unsubscribe_router)
except Exception as _unsub_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").error(
        "unsubscribe router not mounted — DO NOT send marketing mail until this is fixed: %r",
        _unsub_exc)

# ---------------------------------------------------------------------------
# Marketing sweeper (SEE W4 — app/marketing_emails.py): the signup-triggered welcome,
# the campaign queue drain, and the completion of rows W3 parked when its suppression
# lookup was unavailable. DEFAULT OFF at three levels — MAIL_MARKETING_ENABLED gates the
# loop, MAIL_WELCOME_ENABLED and MAIL_CAMPAIGNS_ENABLED gate a leg each, and the welcome
# leg additionally sends NOTHING until MAIL_WELCOME_AFTER names the activation date. So
# this is inert on every machine that has not opted in, tests included, and merging it
# cannot mail anyone.
# ---------------------------------------------------------------------------
try:
    from app.marketing_emails import register_marketing as _register_marketing  # noqa: E402
    _register_marketing(app)   # logs the armed interval itself; silent when disabled
except Exception as _marketing_exc:  # noqa: BLE001
    import logging as _logging  # noqa: PLC0415
    _logging.getLogger("macro.api").warning("marketing sweeper not armed: %r", _marketing_exc)
