"""app/account_prefs.py — POST /api/account/prefs (SEE W3, masterplan R4).

``templates/account.js`` has been calling this route (debounced, on ``themechange`` and
``langchange``) since the account card shipped, and nothing implemented it server-side.
This is that implementation — the client is deployed, so the server matches the client:
a one-key body (``{"lang":"zh"}`` or ``{"theme":"dark"}``), fire-and-forget.

Two sinks, one request:

* **Supabase auth ``user_metadata``** — the durable home for a display preference, and
  what ``GET /api/account`` reads back so a signed-in visitor lands in their own theme and
  language on any device.
* **``email_prefs.lang``** — the mirror that makes single-language sends possible later
  without a migration (SEE-R4). Emails ship dual-language in v1; the column is the
  plumbing, filled now so it is populated when the switch is worth flipping.

Identity comes from the Bearer token ONLY (``app.main.require_user``, the same secretless
verification every authed route uses). Any ``user_id`` in the body is ignored — it is not
a field on the model and it is never read.
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

log = logging.getLogger("macro.account_prefs")
router = APIRouter()

LANGS = ("en", "zh")
THEMES = ("light", "dark")


def _current_user(authorization: str | None = Header(default=None)) -> dict:
    """Lazy import mirrors app/billing.py::_current_user — no app.main import cycle."""
    from app.main import require_user  # noqa: PLC0415
    return require_user(authorization)


def _supabase() -> tuple[str, str]:
    from app import billing  # noqa: PLC0415 — one place owns these constants
    return billing.SUPABASE_URL, billing.SUPABASE_SERVICE_ROLE_KEY


def _write_user_metadata(user_id: str, patch: dict) -> bool:
    """Merge ``patch`` into the user's auth ``user_metadata``. False on any failure.

    The merge is done HERE, from the record the token verification already returned,
    rather than trusting the admin endpoint's own merge semantics — GoTrue versions have
    differed on whether a partial ``user_metadata`` replaces or merges, and losing an
    unrelated key a future feature stored would be a silent data loss.
    """
    base_url, key = _supabase()
    if not user_id or not key:
        return False
    body = json.dumps({"user_metadata": patch}).encode()
    req = urllib.request.Request(
        f"{base_url}/auth/v1/admin/users/{urllib.parse.quote(str(user_id))}",
        data=body,
        method="PUT",
        headers={"apikey": key, "Authorization": f"Bearer {key}",
                 "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            resp.read()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("account_prefs: metadata write failed for %s (%s)", user_id, type(exc).__name__)
        return False


def _mirror_email_lang(user_id: str, lang: str) -> bool:
    """Upsert ``email_prefs.lang``. False on any failure — the mirror is not load-bearing."""
    from app import billing  # noqa: PLC0415
    try:
        billing._pg(
            "POST", "email_prefs?on_conflict=user_id",
            body=[{"user_id": user_id, "lang": lang,
                   "updated_at": datetime.now(timezone.utc).isoformat()}],
            prefer="resolution=merge-duplicates,return=minimal",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("account_prefs: email_prefs mirror failed for %s (%s)",
                    user_id, type(exc).__name__)
        return False


class PrefsRequest(BaseModel):
    lang: str | None = Field(None, description="'en' | 'zh'")
    theme: str | None = Field(None, description="'light' | 'dark'")


@router.post("/api/account/prefs")
def save_prefs(body: PrefsRequest, user: dict = Depends(_current_user)) -> dict:
    """Store the caller's display preferences. Body ``{lang?, theme?}``; at least one.

    Returns ``{"ok", "prefs", "metadata", "email_prefs"}`` — the two booleans say which
    sinks actually took the write, so a partial failure is visible instead of silently
    reported as success. 400 on an unknown value; 502 only when NOTHING was stored.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")

    patch: dict[str, Any] = {}
    if body.lang is not None:
        lang = body.lang.strip().lower()
        if lang not in LANGS:
            raise HTTPException(400, f"unknown lang '{body.lang}'")
        patch["lang"] = lang
    if body.theme is not None:
        theme = body.theme.strip().lower()
        if theme not in THEMES:
            raise HTTPException(400, f"unknown theme '{body.theme}'")
        patch["theme"] = theme
    if not patch:
        raise HTTPException(400, "nothing to save (send lang and/or theme)")

    existing = dict(user.get("user_metadata") or {})
    existing.update(patch)
    stored = _write_user_metadata(str(user_id), existing)

    mirrored = False
    if "lang" in patch:
        mirrored = _mirror_email_lang(str(user_id), patch["lang"])

    if not stored and not mirrored:
        raise HTTPException(502, "could not save preferences, please try again")
    return {"ok": True, "prefs": patch, "metadata": stored, "email_prefs": mirrored}
