"""lib/user_prefs.py — the ONE reader/writer for a signed-in user's stored preferences.

Three keys live in the Supabase Auth ``user_metadata`` object:

* ``lang``        — ``en`` | ``zh``               (UI language; the account route also
                                                  mirrors it into ``email_prefs.lang``)
* ``theme``       — ``light`` | ``dark``
* ``brain_depth`` — ``concise`` | ``standard`` | ``deep``  (Analyst OS W3: how many WORDS
                    the user wants back. The evidence bar never moves with it — only the
                    length; a concise answer is not a thinner-sourced answer.)

Why this is a lib module and not private to ``app/account_prefs.py``: the chat gateway now
WRITES a preference too — "answer shorter from now on" is a thing people say mid-turn, so
``set_chat_preference`` is a tool — and a second hand-rolled GoTrue merge-write is exactly
how one of the two paths ends up clobbering a key the other stores.

**The merge happens on OUR side, never GoTrue's.** GoTrue versions have differed on whether
a partial ``user_metadata`` PUT merges or REPLACES the object, and losing an unrelated key a
future feature stored would be silent data loss. So:

* a caller holding the user record passes it as ``base`` (``app/account_prefs.py`` has the
  verified token's record in hand — that path makes exactly one network call, a PUT);
* a caller holding only a user id (the chat tool) pays one admin GET first, and a FAILED
  read REFUSES the write rather than PUTting a partial object.

Enum validation is the other half of the point: an illegal value is dropped on read and
refuses the write, so nothing downstream has to defend against ``sepia`` or ``klingon``.

Credentials are env-resolved with **no baked-in default project** — the same idiom as the
gateway's own Supabase readers (``brain_gateway._resolve_tier`` et al): an unset env no-ops
the write instead of aiming a service-role PUT at whatever project is hard-coded. A caller
that already owns the pair injects it via ``supabase=`` so one process has one credential
source rather than two that can drift apart.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from typing import Any

log = logging.getLogger("macro.user_prefs")

#: Every stored preference and its CLOSED value set.
PREF_VALUES: dict[str, tuple[str, ...]] = {
    "lang": ("en", "zh"),
    "theme": ("light", "dark"),
    "brain_depth": ("concise", "standard", "deep"),
}
PREF_KEYS: tuple[str, ...] = tuple(PREF_VALUES)

_TIMEOUT = 6


# --------------------------------------------------------------------------- #
# validation
# --------------------------------------------------------------------------- #
def normalize_pref(key: str, value: Any) -> str | None:
    """The canonical value for ``key``, or None when it is not a legal one.

    Normalisation is what the account route has always done: strip + lowercase (so ``ZH``
    and ``" en "`` are the same choice). An unknown KEY is None too — no caller can smuggle
    a fourth preference into ``user_metadata`` through this door.
    """
    allowed = PREF_VALUES.get(str(key))
    if not allowed or not isinstance(value, str):
        return None
    val = value.strip().lower()
    return val if val in allowed else None


def validate_prefs(patch: dict | None) -> tuple[dict, list[str]]:
    """Split ``patch`` into (legal prefs, rejected keys). Never raises.

    ``None`` values are skipped rather than rejected — an absent field in a partial body is
    "don't change this", not junk. Rejected keys are returned by NAME so the caller can tell
    the user which value was wrong instead of a blanket failure.
    """
    clean: dict[str, str] = {}
    rejected: list[str] = []
    for key, raw in (patch or {}).items():
        if raw is None:
            continue
        val = normalize_pref(key, raw)
        if val is None:
            rejected.append(str(key))
        else:
            clean[str(key)] = val
    return clean, rejected


def read_user_prefs(user: dict | None) -> dict:
    """This user's stored preferences, straight off a record already in hand.

    ZERO network: ``require_user`` has already returned the Supabase record, so the prefs
    ride along with the identity — which is why the chat routes can thread them without a
    second round trip. Unknown keys and illegal values are dropped, so the result is always
    a subset of :data:`PREF_VALUES` holding legal values only (a guest dict, which carries
    no ``user_metadata`` at all, reads as ``{}``).
    """
    meta = (user or {}).get("user_metadata") if isinstance(user, dict) else None
    if not isinstance(meta, dict):
        return {}
    out: dict[str, str] = {}
    for key in PREF_KEYS:
        val = normalize_pref(key, meta.get(key))
        if val is not None:
            out[key] = val
    return out


# --------------------------------------------------------------------------- #
# GoTrue admin API
# --------------------------------------------------------------------------- #
def _supabase(supabase: tuple[str, str] | None = None) -> tuple[str, str]:
    """``(base_url, service_role_key)`` — injected pair if given, else env."""
    if supabase:
        url, key = supabase
        return str(url or "").rstrip("/"), str(key or "")
    return (os.environ.get("SUPABASE_URL", "").rstrip("/"),
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY", ""))


def _admin_headers(key: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}",
            "Content-Type": "application/json", "Accept": "application/json"}


def _admin_url(base_url: str, user_id: str) -> str:
    # safe="" (not urllib's default "/"): the id is a whole path SEGMENT, and this request
    # carries the service-role key. A '/' or '..' getting through would let an id steer a
    # privileged call at another admin path. Real ids are UUIDs, so nothing changes for them.
    return f"{base_url}/auth/v1/admin/users/{urllib.parse.quote(str(user_id), safe='')}"


def fetch_user_metadata(user_id: str, *, supabase: tuple[str, str] | None = None) -> dict | None:
    """The user's CURRENT ``user_metadata``, or None when we could not read it.

    None is NOT ``{}``: it means "we do not know what is stored", and that distinction is
    load-bearing — :func:`write_user_prefs` refuses to write on a None rather than sending a
    PUT that could replace an object it never saw.
    """
    base_url, key = _supabase(supabase)
    if not user_id or not base_url or not key:
        return None
    req = urllib.request.Request(_admin_url(base_url, user_id), method="GET",
                                 headers=_admin_headers(key))
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            body = json.loads((resp.read() or b"{}").decode() or "{}")
    except Exception as exc:  # noqa: BLE001
        log.warning("user_prefs: metadata read failed for %s (%s)", user_id, type(exc).__name__)
        return None
    meta = body.get("user_metadata") if isinstance(body, dict) else None
    return meta if isinstance(meta, dict) else {}


def write_user_prefs(user_id: str, patch: dict, *, base: dict | None = None,
                     supabase: tuple[str, str] | None = None) -> bool:
    """Merge validated prefs into the user's ``user_metadata``. False on ANY failure.

    ``base`` is the current metadata when the caller already holds it (the account route
    does — it comes from the verified token's own record), which keeps the write to a single
    PUT. Without a base we read it first, and a failed read returns False instead of writing.

    Fail-soft by contract: a display preference is never worth a 500. A rejected enum value
    makes the WHOLE call False and writes nothing — validate first (:func:`validate_prefs`)
    when you want to tell the user which value was wrong.
    """
    clean, rejected = validate_prefs(patch)
    if not clean or rejected:
        return False
    base_url, key = _supabase(supabase)
    if not user_id or not base_url or not key:
        return False
    if base is None:
        base = fetch_user_metadata(user_id, supabase=(base_url, key))
    if not isinstance(base, dict):
        # Same refusal as a failed read: we do not know what is stored, so a PUT could
        # replace an object we never saw.
        return False
    merged = dict(base)
    merged.update(clean)
    try:
        # Encoding lives INSIDE the try with the request: `base` is somebody else's dict,
        # and a non-serialisable value in it must be a False, not a raise out of a
        # fire-and-forget preference write.
        req = urllib.request.Request(
            _admin_url(base_url, user_id),
            data=json.dumps({"user_metadata": merged}).encode(),
            method="PUT",
            headers=_admin_headers(key),
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            resp.read()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("user_prefs: metadata write failed for %s (%s)", user_id, type(exc).__name__)
        return False
