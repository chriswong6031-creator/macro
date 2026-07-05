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
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Request
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
