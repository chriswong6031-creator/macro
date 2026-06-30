"""Password + signed-cookie session auth for the admin console.

Single operator, one shared password (ADMIN_PASSWORD). On success we mint a
stateless, HMAC-signed session cookie (no server-side session store) plus a
double-submit CSRF token. Writes require BOTH a valid session AND a matching
CSRF header, on top of the same-origin checks in server.py — defense in depth.

There is no user database here: this gates a single-operator control panel, not
a multi-tenant product.
"""
from __future__ import annotations

import base64
import hmac
import json
import secrets
import threading
import time
from hashlib import sha256

from . import settings

SESSION_COOKIE = "admin_session"
CSRF_COOKIE = "admin_csrf"
CSRF_HEADER = "X-CSRF-Token"


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(msg: bytes) -> str:
    return _b64e(hmac.new(settings.session_secret(), msg, sha256).digest())


def mint_session() -> str:
    now = int(time.time())
    payload = {"iat": now, "exp": now + settings.session_ttl_hours() * 3600}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    return f"{body}.{_sign(body.encode())}"


def valid_session(cookie: str | None) -> bool:
    if not cookie or "." not in cookie:
        return False
    body, _, sig = cookie.partition(".")
    # constant-time signature check before trusting any payload bytes
    if not hmac.compare_digest(sig, _sign(body.encode())):
        return False
    try:
        payload = json.loads(_b64d(body))
        return int(payload.get("exp", 0)) > int(time.time())
    except Exception:  # noqa: BLE001
        return False


def new_csrf() -> str:
    return secrets.token_urlsafe(24)


def csrf_ok(cookie_token: str | None, header_token: str | None) -> bool:
    return bool(cookie_token and header_token
                and hmac.compare_digest(cookie_token, header_token))


# ---- login throttle ----------------------------------------------------------
# PER-CLIENT, not global: a global lockout would let any anonymous internet client
# DoS the single operator out of their own console by spamming wrong passwords
# (the panel is public + direct-to-origin, no upstream WAF). Each client id (the
# real peer IP, via X-Forwarded-For from the local Caddy) gets its own counter, so
# one attacker can only lock out *themselves*. The gate-check and the attempt
# increment happen in ONE held critical section (the count is reserved up front,
# BEFORE the unlocked compare), so concurrent guesses can't slip past the lockout.
_LOCK = threading.Lock()
_attempts: dict[str, dict] = {}   # client_id -> {"fails": int, "until": float, "ts": float}
_LOCKOUT_AT = 5                   # failures before the first lockout
_TTL = 3600.0                     # forget idle, unlocked clients after an hour


def _prune(now: float) -> None:
    stale = [k for k, e in _attempts.items() if e["until"] <= now and e["ts"] < now - _TTL]
    for k in stale:
        _attempts.pop(k, None)


def password_ok(submitted: str | None, client_id: str = "-") -> tuple[bool, str | None]:
    """Constant-time password check with per-client escalating lockout. (ok, error)."""
    expected = settings.admin_password()
    if not expected:
        return False, "no password configured"
    now = time.time()
    with _LOCK:
        _prune(now)
        e = _attempts.setdefault(client_id, {"fails": 0, "until": 0.0, "ts": now})
        e["ts"] = now
        if e["until"] > now:
            return False, f"too many attempts — locked for {int(e['until'] - now) + 1}s"
        e["fails"] += 1            # reserve this attempt atomically with the gate check
        if e["fails"] >= _LOCKOUT_AT:
            e["until"] = now + min(300, 15 * (2 ** (e["fails"] - _LOCKOUT_AT)))
    time.sleep(0.25)              # fixed cost slows brute force without hurting the operator
    if hmac.compare_digest(submitted or "", expected):
        with _LOCK:
            _attempts.pop(client_id, None)   # a correct password clears this client's record
        return True, None
    return False, "invalid password"
