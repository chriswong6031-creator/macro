"""app/support.py — public support-ticket intake (SEE W1, masterplan §5).

One route, deliberately:

    POST /api/support/ticket   — unauthenticated; file a support request.

It is the only *public write* surface on macro-api besides the Stripe webhook, so the
abuse posture is the design, not a decoration:

  * **honeypot** — a ``website`` field that a human never sees and never fills. Non-empty
    means a bot; we answer 200 with a well-formed body and write NOTHING (a 400 would
    teach the bot which field betrayed it).
  * **time-to-fill** — ``t0`` is the epoch-ms the form was rendered. A submission under
    3 seconds old was not typed by a person. Generic 400.
  * **per-IP rate limit** — 5 tickets per clock hour, in-process fixed window, keyed on
    the real visitor IP (``app.main._mm_client_ip``: EO-Client-IP first, then the other
    CDN real-client headers, then XFF — the same precedence the analytics beacon uses,
    because mastermind-x.com sits behind EdgeOne and a bare XFF is the edge PoP).
  * **size caps** — subject ≤ 200, message ≤ 5000, request body ≤ 20 KB.

Identity law: a Bearer token, when present and valid, WINS. The server-verified email
replaces whatever the body claimed and the ticket carries the real ``user_id`` plus a
tier snapshot read through the billing spine. A client-sent user id is never trusted and
is not even accepted. An INVALID/expired bearer does not 401 — the form is public, so we
simply file the ticket as signed-out rather than making a user retype it because their
session lapsed.

Privacy: the row stores the user agent and a keyed, truncated HASH of the client IP. The
raw IP is never written — abuse triage needs "was this the same submitter", not an
address.

Mail-off safe: the operator notification goes through app/mailer.py, which returns a
status string and never raises. A dead relay produces a ledger row and a filed ticket,
never a 500 at the user.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
import urllib.request
import uuid
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

log = logging.getLogger("macro.support")
router = APIRouter()

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

TOPICS = ("billing", "account", "bug", "data", "feature", "other")
LANGS = ("en", "zh")

SUBJECT_MAX = 200
MESSAGE_MAX = 5000
BODY_BYTES_MAX = 20_000        # a support message is text; 20 KB is generous
MIN_FILL_MS = 3_000            # under 3s of form time = not a human
RATE_LIMIT = 5                 # tickets…
RATE_WINDOW_SEC = 3_600        # …per clock hour, per IP
NOTIFY_EXCERPT = 200           # chars of the first message in the operator alert

# Deliberately loose: this is a SHAPE check, not an RFC 5322 parser. The address's real
# validation is whether our reply reaches it; over-strict regexes reject valid addresses
# (plus-tags, long TLDs, unicode domains) and that costs us a real support request.
_EMAIL_RE = re.compile(r"^[^@\s,;]{1,128}@[^@\s,;.]+(\.[^@\s,;.]+)+$")


# --------------------------------------------------------------------------- #
# PostgREST helper (service-role — same shape as app/billing.py::_pg)
# --------------------------------------------------------------------------- #
def _pg(method: str, path: str, body: Any = None, prefer: str | None = None, timeout: int = 6) -> Any:
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY unset")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Accept": "application/json",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw) if raw else None


# --------------------------------------------------------------------------- #
# Rate limiter — in-process fixed window
#
# In-process is honest about what it is: macro-api runs as ONE uvicorn service on one
# VPS, so a process-local counter IS the whole-service counter today. If the API ever
# runs multi-worker this becomes per-worker and the effective ceiling multiplies — at
# which point the limiter moves to a shared store, not to a bigger dict.
# --------------------------------------------------------------------------- #
_rate: dict[str, tuple[int, int]] = {}      # ip -> (window_index, count_in_window)
_rate_lock = threading.Lock()
_RATE_MAX_KEYS = 10_000                     # bounded: a spray attack must not grow the map forever


def _rate_ok(ip: str) -> bool:
    """True if this IP may file another ticket right now (and books the attempt)."""
    if not ip or ip == "unknown":
        return True     # never punish an un-attributable request; the honeypot still applies
    window = int(time.time() // RATE_WINDOW_SEC)
    with _rate_lock:
        if len(_rate) > _RATE_MAX_KEYS:
            # Drop everything from older windows in one sweep — cheap, and the only state
            # lost is counters that were about to expire anyway.
            for k in [k for k, (w, _n) in _rate.items() if w != window]:
                _rate.pop(k, None)
        w, n = _rate.get(ip, (window, 0))
        if w != window:
            w, n = window, 0
        if n >= RATE_LIMIT:
            _rate[ip] = (w, n)
            return False
        _rate[ip] = (w, n + 1)
        return True


def _reset_rate_limiter() -> None:
    """Test hook — clears the in-process window state."""
    with _rate_lock:
        _rate.clear()


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _client_ip(request: Request) -> str:
    """The real visitor IP via app.main's EdgeOne-aware resolver (lazy import, no cycle)."""
    try:
        from app.main import _mm_client_ip  # noqa: PLC0415
        return _mm_client_ip(request)
    except Exception:  # noqa: BLE001
        return "unknown"


def _ip_hash(ip: str) -> str:
    """Truncated, keyed hash of a client IP — an abuse-correlation token, not an address.

    Keyed with MAIL_UNSUB_SECRET when it is set. A BARE sha256 of an IPv4 address is
    trivially reversible (the whole space is 2^32), so without a key this is a
    space-saver, not anonymisation — set the secret. Documented in
    docs/ops/email-support-setup.md §2.
    """
    raw = (ip or "").encode()
    secret = (os.environ.get("MAIL_UNSUB_SECRET") or "").strip()
    if secret:
        return hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()[:16]
    return hashlib.sha256(raw).hexdigest()[:16]


def _resolve_user(authorization: str | None) -> dict | None:
    """Verified Supabase user for a Bearer header, or None.

    Uses app.main.require_user — the same secretless GET /auth/v1/user check every authed
    route uses, so there is exactly one notion of "who is this". Any failure (absent
    header, expired token, upstream hiccup) returns None and the ticket files as
    signed-out; a public form must not 401 someone for a stale session.
    """
    if not authorization or not authorization.startswith("Bearer "):
        return None
    try:
        from app.main import require_user  # noqa: PLC0415
        return require_user(authorization)
    except Exception as exc:  # noqa: BLE001
        log.debug("support: bearer present but unresolved (%s) — filing as signed-out", type(exc).__name__)
        return None


def _tier_for(user_id: str) -> str | None:
    """Tier snapshot at submission time, via the billing spine's read path. None on failure."""
    if not user_id:
        return None
    try:
        from app import billing  # noqa: PLC0415
        return billing.read_entitlement(user_id).get("tier")
    except Exception as exc:  # noqa: BLE001
        log.debug("support: tier snapshot failed for %s (%s)", user_id, type(exc).__name__)
        return None


def _notify_operator(*, ticket_id: str, topic: str, subject: str, message: str,
                     email: str, tier: str | None, lang: str | None) -> str:
    """Tell the operator a ticket arrived. Never raises; returns the mailer status."""
    to = ""
    try:
        from app import mailer  # noqa: PLC0415
        to = mailer.support_to()
        if not to:
            return "skipped_no_recipient"
        excerpt = message[:NOTIFY_EXCERPT] + ("…" if len(message) > NOTIFY_EXCERPT else "")
        html, text = mailer.render_email(
            f"New support ticket — {topic}",
            f"新的客服工单 — {topic}",
            [
                {"kind": "kv",
                 "en": [("From", email), ("Topic", topic), ("Tier", tier or "unknown"),
                        ("Language", lang or "unknown"), ("Ticket", ticket_id)],
                 "zh": [("发件人", email), ("主题", topic), ("套餐", tier or "未知"),
                        ("语言", lang or "未知"), ("工单", ticket_id)]},
                {"en": subject, "zh": subject},
                {"kind": "quote", "en": excerpt, "zh": excerpt},
            ],
        )
        return mailer.send(
            template="ticket_operator_notify",
            cls="transactional",
            to_email=to,
            subject=f"[support/{topic}] {subject[:120]}",
            html=html,
            text=text,
            idem_key=f"ticket-notify:{ticket_id}",
        )
    except Exception as exc:  # noqa: BLE001 — a notification failure never fails the ticket
        log.warning("support: operator notify failed for %s (%s)", ticket_id, type(exc).__name__)
        return "failed"


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #
class TicketRequest(BaseModel):
    email: str = Field("", description="reply address; overridden by the Bearer identity when signed in")
    topic: str = Field("", description="billing|account|bug|data|feature|other")
    subject: str = Field("", description=f"1..{SUBJECT_MAX} chars")
    message: str = Field("", description=f"1..{MESSAGE_MAX} chars")
    lang: str | None = Field(None, description="'en' | 'zh' | null")
    website: str | None = Field(None, description="honeypot — must be empty")
    t0: int | None = Field(None, description="epoch-ms the form was rendered")


@router.post("/api/support/ticket")
def create_ticket(body: TicketRequest, request: Request,
                  authorization: str | None = Header(default=None)) -> dict:
    """File a support ticket. Public — no auth required, auth honoured when offered."""
    # ---- body size ------------------------------------------------------------
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > BODY_BYTES_MAX:
        raise HTTPException(413, "message too long")

    # ---- honeypot: answer like a success, write nothing -----------------------
    if (body.website or "").strip():
        log.info("support: honeypot tripped — dropped")
        return {"ok": True, "ticket_id": str(uuid.uuid4())}

    # ---- time-to-fill ---------------------------------------------------------
    # Optional by contract (the W2 form always sends it). A t0 in the FUTURE is clock
    # skew, not evidence of a human, so it is treated as absent rather than as a pass.
    if body.t0:
        elapsed_ms = int(time.time() * 1000) - int(body.t0)
        if 0 <= elapsed_ms < MIN_FILL_MS:
            log.info("support: submission %dms after render — rejected", elapsed_ms)
            raise HTTPException(400, "could not accept this submission")

    # ---- rate limit -----------------------------------------------------------
    ip = _client_ip(request)
    if not _rate_ok(ip):
        log.info("support: rate limit hit")
        raise HTTPException(429, "too many requests — please try again later")

    # ---- validation -----------------------------------------------------------
    topic = (body.topic or "").strip().lower()
    if topic not in TOPICS:
        raise HTTPException(400, f"topic must be one of {list(TOPICS)}")
    subject = (body.subject or "").strip()
    if not 1 <= len(subject) <= SUBJECT_MAX:
        raise HTTPException(400, f"subject must be 1..{SUBJECT_MAX} characters")
    message = (body.message or "").strip()
    if not 1 <= len(message) <= MESSAGE_MAX:
        raise HTTPException(400, f"message must be 1..{MESSAGE_MAX} characters")
    lang = (body.lang or "").strip().lower() or None
    if lang is not None and lang not in LANGS:
        raise HTTPException(400, f"lang must be one of {list(LANGS)} or omitted")

    # ---- identity: a valid Bearer OVERRIDES the body email --------------------
    user = _resolve_user(authorization)
    user_id = (user or {}).get("id") or None
    verified_email = ((user or {}).get("email") or "").strip()
    email = verified_email or (body.email or "").strip()
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "a valid email address is required")
    tier = _tier_for(user_id) if user_id else None

    # ---- write ----------------------------------------------------------------
    row = {
        "email": email,
        "user_id": user_id,
        "topic": topic,
        "subject": subject,
        "status": "open",
        "lang": lang,
        "tier": tier,
        "meta": {
            "ua": (request.headers.get("user-agent") or "")[:300],
            "ip_hash": _ip_hash(ip),
            "authed": bool(user_id),
        },
    }
    try:
        rows = _pg("POST", "support_tickets", body=[row], prefer="return=representation")
        ticket_id = (rows or [{}])[0].get("id")
        if not ticket_id:
            raise RuntimeError("insert returned no id")
    except Exception as exc:  # noqa: BLE001 — never echo the internal error to the caller
        log.warning("support: ticket insert failed (%s)", type(exc).__name__)
        raise HTTPException(503, "support intake is temporarily unavailable") from None

    try:
        _pg("POST", "support_ticket_messages",
            body=[{"ticket_id": ticket_id, "author": "user", "body": message, "emailed": False}],
            prefer="return=minimal")
    except Exception as exc:  # noqa: BLE001
        # The ticket exists; losing the first message body would make it useless, so this
        # is loud — but the user still gets their id rather than a 500 on a filed ticket.
        log.error("support: first message insert failed for %s (%s)", ticket_id, type(exc).__name__)

    status = _notify_operator(ticket_id=str(ticket_id), topic=topic, subject=subject,
                              message=message, email=email, tier=tier, lang=lang)
    log.info("support: ticket %s filed (topic=%s authed=%s notify=%s)",
             ticket_id, topic, bool(user_id), status)
    return {"ok": True, "ticket_id": str(ticket_id)}
