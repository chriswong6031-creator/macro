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

Analyst OS W3: the enum table and the GoTrue merge-write moved to ``lib/user_prefs.py``,
because the chat gateway now writes a preference too (``set_chat_preference`` — "answer
shorter from now on"). Two hand-rolled merge-writes is how one path clobbers the other's
key. This route keeps its own shape (400 with the offending field named, per-sink booleans,
the ``email_prefs`` mirror) and gains ``brain_depth`` on the body.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from lib import user_prefs

log = logging.getLogger("macro.account_prefs")
router = APIRouter()

# Back-compat aliases: the value sets now live in lib/user_prefs.PREF_VALUES (one table,
# shared with the chat tool). Kept as names so nothing importing them breaks.
LANGS = user_prefs.PREF_VALUES["lang"]
THEMES = user_prefs.PREF_VALUES["theme"]
DEPTHS = user_prefs.PREF_VALUES["brain_depth"]


def _current_user(authorization: str | None = Header(default=None)) -> dict:
    """Lazy import mirrors app/billing.py::_current_user — no app.main import cycle."""
    from app.main import require_user  # noqa: PLC0415
    return require_user(authorization)


def _supabase() -> tuple[str, str]:
    from app import billing  # noqa: PLC0415 — one place owns these constants
    return billing.SUPABASE_URL, billing.SUPABASE_SERVICE_ROLE_KEY


def _write_user_metadata(user_id: str, patch: dict, base: dict) -> bool:
    """Merge ``patch`` into the user's auth ``user_metadata``. False on any failure.

    Thin delegate to ``lib.user_prefs.write_user_prefs``. The merge base is passed in from
    the record the token verification already returned, so this path still makes exactly ONE
    network call (a PUT) — the lib's own admin GET is for callers that hold only a user id.
    ``app.billing``'s constants are injected so this process has one credential source.
    """
    if not user_id:
        return False
    return user_prefs.write_user_prefs(str(user_id), patch, base=base, supabase=_supabase())


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
    # Analyst OS W3: how many WORDS the chat answers with. Same evidence bar at every
    # setting — 'concise' buys a shorter answer, never a thinner-sourced one.
    brain_depth: str | None = Field(None, description="'concise' | 'standard' | 'deep'")


@router.post("/api/account/prefs")
def save_prefs(body: PrefsRequest, user: dict = Depends(_current_user)) -> dict:
    """Store the caller's preferences. Body ``{lang?, theme?, brain_depth?}``; at least one.

    Returns ``{"ok", "prefs", "metadata", "email_prefs"}`` — the two booleans say which
    sinks actually took the write, so a partial failure is visible instead of silently
    reported as success. 400 on an unknown value; 502 only when NOTHING was stored.
    """
    user_id = user.get("id")
    if not user_id:
        raise HTTPException(401, "no user id")

    # One validation loop over the lib's enum table — a value the lib would refuse is
    # rejected HERE, by name, so the client learns which field was wrong.
    patch: dict[str, Any] = {}
    for key, raw in (("lang", body.lang), ("theme", body.theme),
                     ("brain_depth", body.brain_depth)):
        if raw is None:
            continue
        val = user_prefs.normalize_pref(key, raw)
        if val is None:
            raise HTTPException(400, f"unknown {key} '{raw}'")
        patch[key] = val
    if not patch:
        raise HTTPException(400, "nothing to save (send lang, theme and/or brain_depth)")

    stored = _write_user_metadata(str(user_id), patch,
                                  dict(user.get("user_metadata") or {}))

    mirrored = False
    if "lang" in patch:
        mirrored = _mirror_email_lang(str(user_id), patch["lang"])

    if not stored and not mirrored:
        raise HTTPException(502, "could not save preferences, please try again")
    return {"ok": True, "prefs": patch, "metadata": stored, "email_prefs": mirrored}
