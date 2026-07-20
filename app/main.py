"""macro API — FastAPI serving tier for the SaaS (Slice 2).

Minimal by design: health + overlay now; Supabase-JWT-gated routes activate the
moment ``SUPABASE_JWT_SECRET`` is set in the service environment. This wraps the
existing build artifacts under /opt/macro — it does NOT recompute the engine.

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
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field, field_validator

# Add repo root to sys.path so engine.neuralweb can be imported from /opt/macro
_REPO_ROOT_FOR_IMPORT = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
if str(_REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT_FOR_IMPORT))

REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
SITE = REPO / "site"
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


def _commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"], text=True
        ).strip()
    except Exception:
        return "unknown"


@app.get("/api/health")
def health() -> dict:
    """Liveness + which build is being served. Unauthenticated."""
    return {"status": "ok", "commit": _commit()}


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


@app.post("/api/collect")
async def collect(request: Request, background: BackgroundTasks) -> Response:
    """Anonymous first-party analytics beacon sink (see block header)."""
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > 16384:
        return Response(status_code=413)
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
    ip = _mm_client_ip(request)
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
    f = SITE / "live" / "overlay.json"
    if not f.exists():
        raise HTTPException(503, "overlay not built yet")
    return JSONResponse(json.loads(f.read_text()))


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

    # overlay — the 5-min live engine-scoring loop
    ov = SITE / "live" / "overlay.json"
    if ov.exists():
        try:
            d = json.loads(ov.read_text())
            checks["overlay"] = {
                "built": d.get("built"), "n": d.get("n"),
                "fresh": d.get("n_fresh"), "age_min": age_min(ov),
            }
        except Exception as e:  # noqa: BLE001
            checks["overlay"] = {"error": str(e)}
    else:
        checks["overlay"] = {"status": "missing"}

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
            checks["terminal_data"] = {"error": str(e)}
    else:
        checks["terminal_data"] = {"status": "missing"}

    return {"status": "ok", "commit": _commit(), "checks": checks}


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
        raise HTTPException(502, f"auth check failed: {e}") from None


@app.get("/api/me")
def me(user: dict = Depends(require_user)) -> dict:
    """Whoami — first authenticated route; proves the Supabase login works."""
    return {"id": user.get("id"), "email": user.get("email"), "role": user.get("role")}


# ---------------------------------------------------------------------------
# /api/ask — interrogable, cited, never-advising brain (W8b PR2)
# ---------------------------------------------------------------------------

class AskRequest(BaseModel):
    question: str = Field(..., max_length=500, description="Plain-language question (max 500 chars)")
    context_ticker: str | None = Field(None, description="Optional ticker to focus the query (e.g. 'NVDA')")


@app.post("/api/ask")
def ask_brain(body: AskRequest, user: dict = Depends(require_user)) -> dict:
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
        raise HTTPException(503, f"ask_brain module unavailable: {exc}") from exc

    user_id = user.get("id") or user.get("email") or "unknown"
    result = ask(
        question=body.question,
        user_id=user_id,
        context_ticker=body.context_ticker,
        root=REPO,
    )
    return result


@app.post("/api/ask/stream")
def ask_brain_stream(body: AskRequest, user: dict = Depends(require_user)):
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
        raise HTTPException(503, f"ask_brain module unavailable: {exc}") from exc

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


def _brain_module():
    """Lazy import brain_gateway; raises HTTP 503 if unavailable."""
    try:
        from engine.neuralweb import brain_gateway  # noqa: PLC0415
        return brain_gateway
    except ImportError as exc:
        raise HTTPException(503, f"brain_gateway unavailable: {exc}") from exc


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
               user: dict = Depends(require_user)):
    """Brain chat — non-streaming.

    POST body: {message, lane?, thread_id?, history?, context?}
    Response: {ok, reply, citations, annotations?, symbol?, lane, model, thread_id,
               quota: {lane, remaining, limit, period}, filtered, degraded, is_context_only}
    HTTP 402 when quota exhausted; 429 when the burst throttle trips.
    """
    gw = _brain_module()
    # mode validation: only 'chat' and 'research' are accepted
    mode = body.mode if body.mode in ("chat", "research") else "chat"
    # research mode forces pro lane (gateway also enforces this, but be explicit here)
    lane = "pro" if mode == "research" else (body.lane if body.lane in ("fast", "pro") else "fast")
    user_id = user.get("id") or user.get("email") or "unknown"
    # CXI-R23a: email comes ONLY from the Supabase-verified require_user result — never body/headers.
    user_email = (user.get("email") or "").strip().lower()

    # Burst throttle FIRST — a throttled request must not consume quota.
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
    )

    if result.get("quota_exhausted"):
        raise HTTPException(402, detail=result)

    return result


@app.post("/api/brain/stream")
def brain_stream(body: BrainChatRequest, request: Request, background: BackgroundTasks,
                 user: dict = Depends(require_user)):
    """Brain chat — SSE streaming.

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
    mode = body.mode if body.mode in ("chat", "research") else "chat"
    lane = "pro" if mode == "research" else (body.lane if body.lane in ("fast", "pro") else "fast")
    user_id = user.get("id") or user.get("email") or "unknown"
    # CXI-R23a: email comes ONLY from the Supabase-verified require_user result — never body/headers.
    user_email = (user.get("email") or "").strip().lower()

    # Burst throttle FIRST — a throttled request must not consume quota.
    _brain_throttle_check(user_id)

    # Device-linked identity (PART A) + admin cross-tracking event.
    aid, ip, device_hash = _brain_identity(request)
    background.add_task(_brain_track_event, aid, ip, user_id)

    history = (body.history or [])[:24]

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
        )

    return StreamingResponse(_gen(), media_type="text/event-stream", headers=_SSE_BRAIN_HEADERS)


@app.get("/api/brain/me")
def brain_me(user: dict = Depends(require_user)):
    """Return tier + quota status for both lanes.

    Response: {tier, quotas: {fast: {remaining, limit, period}, pro: {...}}}
    """
    gw = _brain_module()
    user_id = user.get("id") or user.get("email") or "unknown"
    return gw.get_user_quotas(user_id, root=REPO)


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
