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

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

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
# Anonymous by design — every visitor is measured. The visitor id (mm_aid, httpOnly,
# Domain=.mastermind-x.com, shared with the Terminal at app.mastermind-x.com), the raw client IP,
# and the user-agent are stamped HERE; geolocation is backfilled off the hot path by
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


def _mm_client_ip(request: Request) -> str:
    # Real VISITOR IP, not the CDN edge. mastermind-x.com is behind Tencent EdgeOne, which carries the
    # client IP in EO-Connecting-IP; Caddy's trusted_proxies=private_ranges does NOT trust the public
    # CDN, so X-Forwarded-For is the EdgeOne EDGE IP (e.g. "Tucumcari NM"), not the person. Prefer the
    # CDN real-client header (EO- for EdgeOne, CF-/True-Client-IP for a Cloudflare-fronted path), then
    # fall back to XFF/x-real-ip. These CDN headers pass through Caddy untouched.
    h = request.headers
    for k in ("eo-connecting-ip", "cf-connecting-ip", "true-client-ip"):
        v = (h.get(k) or "").strip()
        if v:
            return v[:64]
    xff = h.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (h.get("x-real-ip") or "").strip()[:64] or "unknown"


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


def _mm_analytics_insert(rows: list) -> None:
    """Best-effort PostgREST insert into analytics_events. Never raises (runs as a background task)."""
    if not rows or not SUPABASE_SERVICE_ROLE_KEY:
        return
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

    background.add_task(_mm_analytics_insert, rows)

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
# Options Hub analytics router (lane B — app/hub.py)
# Wrapped in try/except so this file stays green if hub.py lands later.
# ---------------------------------------------------------------------------
try:
    from app.hub import router as hub_router  # noqa: E402  (lane B ships app/hub.py)
    app.include_router(hub_router)
except ImportError:
    pass  # app/hub.py not yet present — hub routes unavailable until lane B merges
