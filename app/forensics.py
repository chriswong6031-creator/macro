"""Authenticated serving route for the private Filing Forensics state."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import Response

from engine.fundamental_forensics.private_state import load_state_blob

router = APIRouter()
REPO = Path(os.environ.get("MACRO_REPO", "/opt/macro"))


def require_site_full_user(authorization: str | None = Header(default=None)) -> dict:
    """Lazy wrapper avoids importing partially initialized app.main at mount time."""
    from app.main import require_user as _require_user  # noqa: PLC0415
    from app.paywall import enforce_site_full  # noqa: PLC0415
    return enforce_site_full(_require_user(authorization), always=True)


@router.get("/api/forensics/state")
def forensics_state(_user: dict = Depends(require_site_full_user)) -> Response:
    """Return the validated gzip object to an entitled user, never a public URL."""
    blob = load_state_blob(REPO)
    if blob is None:
        raise HTTPException(503, "forensics state temporarily unavailable")
    return Response(
        content=blob,
        media_type="application/gzip",
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": 'inline; filename="forensics-state.json.gz"',
            "Vary": "Authorization",
            "X-Content-Type-Options": "nosniff",
            "X-Robots-Tag": "noindex, noarchive",
        },
    )
