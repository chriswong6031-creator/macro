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
    # B-F08-1a: alert delivery preferences (MO-PAID-085, preferences half only).
    alert_email_optin: bool | str | None = Field(None, description="email alerts on/off")
    alert_categories: list[str] | None = Field(
        None, description="subset of user_prefs.ALERT_CATEGORIES")
    tz: str | None = Field(None, description="IANA zone, e.g. 'Asia/Hong_Kong'")
    quiet_hours: dict | str | None = Field(
        None,
        description="{'start':'HH:MM','end':'HH:MM'} or the literal string 'off' to clear "
                    "(quiet_hours is skipped-as-unchanged on a bare None like every other "
                    "field, so clearing needs its own sentinel — never {} )")


#: Plain-word 400 detail per rejected field (EN/ZH). Chairman plain-language law
#: 2026-09-06: never a machine string like "unknown tz 'Mars/Olympus'".
_FIELD_ERR: dict[str, tuple[str, str]] = {
    "tz": ("That time zone isn't one we know. Pick one from the list.",
           "无法识别该时区，请从列表中选择。"),
    "alert_categories": ("That isn't an alert type we send. Pick from the list.",
                          "这不是我们发送的提醒类型，请从列表中选择。"),
    "quiet_hours": ("Quiet hours need a start and an end time, like 22:00 and 07:00.",
                     "免打扰时段需要开始和结束时间，例如 22:00 与 07:00。"),
    "alert_email_optin": ("That setting is on or off — nothing else.",
                           "该设置只有开或关两种状态。"),
}
_DEFAULT_ERR = ("We don't recognise that choice.", "无法识别该选项。")


def _field_error(key: str) -> dict:
    en, zh = _FIELD_ERR.get(key, _DEFAULT_ERR)
    return {"field": key, "en": en, "zh": zh}


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

    # One validation loop over the lib's kind table — a value the lib would refuse is
    # rejected HERE, by name, so the client learns which field was wrong. quiet_hours'
    # wire sentinel for "clear" is the literal string "off" (see PrefsRequest docstring);
    # everything else skips a bare None as "don't change".
    patch: dict[str, Any] = {}
    response_prefs: dict[str, Any] = {}
    for key, raw in (("lang", body.lang), ("theme", body.theme),
                     ("brain_depth", body.brain_depth),
                     ("alert_email_optin", body.alert_email_optin),
                     ("alert_categories", body.alert_categories),
                     ("tz", body.tz),
                     ("quiet_hours", body.quiet_hours)):
        if raw is None:
            continue
        if key == "quiet_hours":
            if raw == "off":
                # Wire sentinel for "clear". Kept as the literal string through to the lib
                # writer (never bare None here) — the lib's own None-means-"don't touch"
                # convention would otherwise silently no-op this clear.
                patch[key] = "off"
                response_prefs[key] = None
                continue
            if not user_prefs.quiet_hours_shape_ok(raw):
                raise HTTPException(400, detail=_field_error(key))
            # Shape is valid; normalize_value may still legally collapse start==end to None
            # (a real clear, not a rejection) — route it through the same "off" sentinel.
            val = user_prefs.normalize_value(key, raw)
            patch[key] = val if val is not None else "off"
            response_prefs[key] = val
            continue
        val = user_prefs.normalize_value(key, raw)
        if val is None:
            raise HTTPException(400, detail=_field_error(key))
        patch[key] = val
        response_prefs[key] = val
    if not patch:
        raise HTTPException(400, "nothing to save (send lang, theme and/or brain_depth)")

    existing_meta = dict(user.get("user_metadata") or {})

    # B-F08-1a freeze §8: alerts turned on with no IANA zone known -- neither sent on
    # this call nor already stored -- get an explicit default rather than shipping with
    # an unset zone (quiet hours and any future delivery-window math need a real tz to
    # mean anything). Never overwrites a tz the caller/account already has.
    if patch.get("alert_email_optin") is True and "tz" not in patch \
            and not existing_meta.get("tz"):
        lang = patch.get("lang") or existing_meta.get("lang")
        default_tz = user_prefs.default_tz_for_lang(lang)
        patch["tz"] = default_tz
        response_prefs["tz"] = default_tz

    stored = _write_user_metadata(str(user_id), patch, existing_meta)

    mirrored = False
    if "lang" in patch:
        mirrored = _mirror_email_lang(str(user_id), patch["lang"])

    if not stored and not mirrored:
        raise HTTPException(502, "could not save preferences, please try again")
    return {"ok": True, "prefs": response_prefs, "metadata": stored, "email_prefs": mirrored}


@router.get("/api/account/prefs")
def read_prefs(user: dict = Depends(_current_user)) -> dict:
    """Readback for the alert-preferences surface (B-F08-1a). Zero network — rides the
    already-verified record, same as ``lib.user_prefs.read_user_prefs`` everywhere else.

    ``unset`` names every stored-preference key that has never been written, so the client
    can render an honest default (browser tz, "nothing chosen yet") instead of a fabricated
    saved value — null disclosure, not a hidden empty state.
    """
    stored = user_prefs.read_user_prefs(user)
    return {
        "ok": True,
        "prefs": stored,
        "unset": [k for k in user_prefs.PREF_KEYS if k not in stored],
        "categories_available": list(user_prefs.ALERT_CATEGORIES),
    }
