"""macro API — FastAPI serving tier for the SaaS (Slice 2).

Minimal by design: health + overlay now; Supabase-JWT-gated routes activate the
moment ``SUPABASE_JWT_SECRET`` is set in the service environment. This wraps the
existing build artifacts under /opt/macro — it does NOT recompute the engine.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))
SITE = REPO / "site"

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


# ---- auth: inactive until SUPABASE_JWT_SECRET is configured ----------------
def require_user(authorization: str | None = Header(default=None)) -> dict:
    """Verify a Supabase access token (HS256, aud=authenticated).

    Returns 503 until the JWT secret is provided, so the gate is obviously
    inactive rather than silently open. Supabase signs user JWTs with the
    project's JWT secret (Dashboard -> Settings -> API -> JWT Secret).
    """
    secret = os.environ.get("SUPABASE_JWT_SECRET")
    if not secret:
        raise HTTPException(503, "auth not configured (set SUPABASE_JWT_SECRET)")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "missing bearer token")
    import jwt  # PyJWT

    token = authorization.split(" ", 1)[1]
    try:
        claims = jwt.decode(
            token, secret, algorithms=["HS256"], audience="authenticated"
        )
    except Exception as e:  # noqa: BLE001 - surface the reason, never the secret
        raise HTTPException(401, f"invalid token: {e}") from None
    return claims


@app.get("/api/me")
def me(user: dict = Depends(require_user)) -> dict:
    """Whoami — first authenticated route; proves the Supabase gate works."""
    return {"sub": user.get("sub"), "email": user.get("email"), "role": user.get("role")}
