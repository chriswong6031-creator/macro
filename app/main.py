"""macro API — FastAPI serving tier for the SaaS (Slice 2).

Minimal by design: health + overlay now; Supabase-JWT-gated routes activate the
moment ``SUPABASE_JWT_SECRET`` is set in the service environment. This wraps the
existing build artifacts under /opt/macro — it does NOT recompute the engine.
"""
from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
SITE = REPO / "site"

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
