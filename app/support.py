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
  * **dual-key rate limit** — every real-client header the app can read (EO-Client-IP,
    CF-Connecting-IP, XFF …) is attacker-suppliable at the origin, so a bot that rotates
    one lands every hit in a fresh bucket. Two independent in-process fixed windows,
    and EITHER can refuse:
      - the CLAIMED ip (``app.main._mm_client_ip``) at 5/hour — tight, but spoofable;
      - the TRUSTED peer (``X-MM-Peer``, which Caddy's ``header_up`` overwrites with the
        real TCP peer, so a client cannot set it) at 60/hour — unspoofable, but loose,
        because CN traffic legitimately aggregates behind a few EdgeOne edge IPs.
    An absent key simply does not apply; it is no longer a free pass, because the other
    key still does.
  * **size caps** — subject ≤ 200, message ≤ 5000. The declared-Content-Length check here
    is a cheap early refusal only: a chunked request declares no length, so the REAL cap
    is ``request_body { max_size 64KB }`` on ``/api/support/*`` in app/deploy/Caddyfile —
    the edge is the only place that sits before the body is read.

Header safety: the subject is whitespace-collapsed to a single line BEFORE length
validation, so an embedded CRLF can never reach an email header (app/mailer.py collapses
again at the chokepoint). Left unhandled this is not a garbled message but a permanent
outage for that ticket: every reply's subject is derived from the stored one.

Identity law: a Bearer token, when present and valid, WINS. The server-verified email
replaces whatever the body claimed and the ticket carries the real ``user_id`` plus a
tier snapshot read through the billing spine. A client-sent user id is never trusted and
is not even accepted. An INVALID/expired bearer does not 401 — the form is public, so we
simply file the ticket as signed-out rather than making a user retype it because their
session lapsed.

Privacy: the row stores the user agent and a keyed, truncated HASH of the client IP. The
raw IP is never written — abuse triage needs "was this the same submitter", not an
address.

Mail-off safe: both sends go through app/mailer.py, which returns a status string and
never raises. A dead relay produces a ledger row and a filed ticket, never a 500 at the
user.

Persist first, mail after (SEE W2 / reviewer M4). The two sends — the operator alert and
the submitter's acknowledgment — run in a FastAPI ``BackgroundTasks`` job, AFTER the
response is written. This route is a sync ``def``, so FastAPI runs it in the 40-slot
anyio threadpool that every other sync route shares: with SMTP inline, one stalled relay
costs up to ``_SMTP_TIMEOUT × _SEND_ATTEMPTS`` per request (~24s today, and up to ~120s if
the timeouts are ever relaxed), and 40 concurrent submissions would occupy every slot and
stall the whole API — from a route a stranger can call. Moving mail off the request path
means ``ok: true`` keeps its literal meaning: the ticket is STORED. The email is a
consequence of that, not a precondition for it.
"""
from __future__ import annotations

import datetime as _dt
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

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request
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

# The reader's own words back at them. Same labels as the <select> on /support.html
# (mockups/support_email/PIN.md §5), so the page, the email and the admin thread all
# name a topic the same way — a stored slug is never shown to a customer.
TOPIC_LABELS: dict[str, tuple[str, str]] = {
    "billing": ("Billing & payments", "账单与付款"),
    "account": ("Account & sign-in", "账户与登录"),
    "bug": ("Something is broken", "有功能坏了"),
    "data": ("Question about the data", "数据相关问题"),
    "feature": ("Idea for something new", "功能建议"),
    "other": ("Something else", "其他"),
}
_ZH_MONTHS = ("1 月", "2 月", "3 月", "4 月", "5 月", "6 月",
              "7 月", "8 月", "9 月", "10 月", "11 月", "12 月")

SUBJECT_MAX = 200
MESSAGE_MAX = 5000
BODY_BYTES_MAX = 20_000        # DECLARED Content-Length only — the real cap is Caddy's
MIN_FILL_MS = 3_000            # under 3s of form time = not a human
RATE_LIMIT = 5                 # tickets per window per CLAIMED (spoofable) ip…
PEER_RATE_LIMIT = 60           # …and per TRUSTED Caddy peer, looser: CN traffic aggregates
RATE_WINDOW_SEC = 3_600        # …per clock hour
PEER_HEADER = "x-mm-peer"      # set by header_up in app/deploy/Caddyfile; unspoofable
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
_rate: dict[str, tuple[int, int]] = {}      # key -> (window_index, count_in_window)
_rate_lock = threading.Lock()
_RATE_MAX_KEYS = 10_000                     # HARD cap: a spray must not grow the map, ever


def _book(key: str, limit: int, window: int) -> bool:
    """Count one attempt against `key` and report whether it stayed under `limit`.

    Caller holds _rate_lock. A key at its limit is left at the limit (not incremented),
    so a sustained flood cannot overflow the counter.
    """
    w, n = _rate.get(key, (window, 0))
    if w != window:
        w, n = window, 0
    if n >= limit:
        _rate[key] = (w, n)
        return False
    _rate[key] = (w, n + 1)
    return True


# Eviction runs BEFORE the two bookings, so it must leave room for them or the map
# settles one or two keys above the cap forever.
_RATE_EVICT_TARGET = _RATE_MAX_KEYS - 2


def _evict(window: int) -> None:
    """Keep the map at or under _RATE_MAX_KEYS. Caller holds _rate_lock.

    Two passes because the first is not sufficient on its own: dropping expired windows
    frees nothing when a flood arrives inside ONE window (35k distinct spoofed IPs in the
    same hour), which is exactly the attack this bound exists for. The second pass evicts
    oldest-inserted — dicts preserve insertion order, and re-booking an existing key
    reassigns its value without moving it, so "oldest inserted" stays meaningful.
    """
    if len(_rate) <= _RATE_EVICT_TARGET:
        return
    for k in [k for k, (w, _n) in _rate.items() if w != window]:
        _rate.pop(k, None)
    while len(_rate) > _RATE_EVICT_TARGET:
        _rate.pop(next(iter(_rate)), None)


def _rate_ok(claimed_ip: str, peer: str) -> bool:
    """True if this caller may file another ticket right now (and books the attempt).

    Both keys are booked whenever they are present, and EITHER exceeding its limit
    refuses — so burning the claimed-ip budget by spoofing still consumes peer budget.
    An absent key contributes nothing; if BOTH are absent (direct local dev, no proxy)
    there is nothing to key on and the request passes.
    """
    claimed = (claimed_ip or "").strip()
    if claimed == "unknown":
        claimed = ""
    peer = (peer or "").strip()[:64]
    if not claimed and not peer:
        return True
    window = int(time.time() // RATE_WINDOW_SEC)
    with _rate_lock:
        _evict(window)
        ok_claimed = _book(f"ip:{claimed}", RATE_LIMIT, window) if claimed else True
        ok_peer = _book(f"peer:{peer}", PEER_RATE_LIMIT, window) if peer else True
        return ok_claimed and ok_peer


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


def ticket_ref(ticket_id: str) -> str:
    """Human-facing short form of a ticket id: ``MX-`` + the first 8 hex, uppercased.

    Design pin §4.3b. The SAME string appears on /support.html's success slip, in the ack
    email's subject (in braces, so replies thread) and in the admin thread — a customer
    who quotes "MX-7F3A2B91" must be findable by it everywhere. A full uuid is not a thing
    anyone reads aloud or types back.
    """
    hexpart = str(ticket_id or "").replace("-", "")[:8].upper()
    return f"MX-{hexpart}" if hexpart else ""


def _sent_stamp() -> tuple[str, str, str]:
    """(slip value, EN date, ZH date) for now, in UTC.

    UTC and SAID so — the submitter's timezone is not knowable server-side, and a
    timestamp whose zone is a guess is worse than one that names itself.
    """
    now = _dt.datetime.now(_dt.timezone.utc)
    slip = f"{now.day} {now.strftime('%b')} {now.year}, {now:%H:%M} UTC"
    return slip, f"{now.day} {now.strftime('%B')} {now.year}", f"{now.year} 年 {_ZH_MONTHS[now.month - 1]} {now.day} 日"


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
        ref = ticket_ref(ticket_id)
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
            eyebrow="SUPPORT",
            preheader=f"{ref} · {topic} · {email}",
            why_en="You received this because you are the Mastermind support operator.",
            why_zh="你收到这封邮件，是因为你是 Mastermind 的客服负责人。",
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


def _ack_submitter(*, ticket_id: str, topic: str, subject: str, message: str,
                   email: str, user_id: str | None) -> str:
    """Acknowledge the ticket to the person who filed it. Never raises.

    Design pin §7.7. The content is fixed by the pin: what happened, the ticket number
    worth keeping, their own words quoted back so they can see we have them, and the one
    instruction that matters — reply to THIS email to add anything. No CTA: there is
    nothing for them to click, and inventing one would be theatre.

    CLASS = transactional (masterplan R5): an acknowledgment is information the sender is
    owed, it is never suppressed by a marketing opt-out, and it carries NO unsubscribe
    link — the pinned base leaves that slot unrendered whenever no URL is passed.

    The ref rides the subject IN BRACES so replies thread and the operator lane can match
    them back to the row.
    """
    try:
        from app import mailer  # noqa: PLC0415
        if not email:
            return "skipped_no_recipient"
        ref = ticket_ref(ticket_id)
        topic_en, topic_zh = TOPIC_LABELS.get(topic, TOPIC_LABELS["other"])
        slip, date_en, date_zh = _sent_stamp()
        html, text = mailer.render_email(
            "We got your message.",
            "我们已收到你的消息。",
            [
                {"en": "A person reads every request — not a bot. You will usually have a "
                       "reply within one business day.",
                 "zh": "每一条请求都由真人阅读，不是机器人。通常一个工作日内你就会收到回复。"},
                {"kind": "kv",
                 "en": [("Ticket", ref), ("Topic", topic_en), ("Sent", slip)],
                 "zh": [("工单号", ref), ("类型", topic_zh), ("发送时间", slip)]},
                {"kind": "quote", "en": message, "zh": message},
                {"kind": "fine",
                 "en": "Reply to this email to add anything — a screenshot, a date, "
                       "the address on the receipt. It lands on the same ticket.",
                 "zh": "回复这封邮件即可补充信息——截图、日期、收据上的邮箱都可以，它们会记到同一个工单上。"},
            ],
            eyebrow="SUPPORT",
            preheader="A person reads it. Reply to this email to add anything.",
            why_en=f"You received this because you wrote to support on {date_en}.",
            # Space BEFORE the date only — a Latin-digit run needs air on its left, but a
            # space after 日 prints as a gap in the middle of a Chinese sentence
            # (email_receipt_sample.html sets the same rhythm).
            why_zh=f"你收到这封邮件，是因为你在 {date_zh}联系了客服。",
        )
        return mailer.send(
            template="ticket_ack",
            cls="transactional",
            to_email=email,
            subject=f"{{{ref}}} We got your message · 我们已收到你的消息",
            html=html,
            text=text,
            idem_key=f"ticket-ack:{ticket_id}",
            user_id=user_id,
        )
    except Exception as exc:  # noqa: BLE001 — the ticket is filed; mail is best-effort
        log.warning("support: ticket ack failed for %s (%s)", ticket_id, type(exc).__name__)
        return "failed"


def _send_ticket_mail(*, ticket_id: str, topic: str, subject: str, message: str,
                      email: str, tier: str | None, lang: str | None,
                      user_id: str | None) -> None:
    """Both sends for one new ticket, off the request path (see the module docstring).

    Operator FIRST: if only one of the two gets out before the process is restarted, the
    one that must survive is the one that puts a human on the ticket. Neither can raise —
    each helper swallows its own failure — but the whole job is wrapped anyway, because a
    background task that raises is logged and forgotten, and silence is the worst outcome
    for a queue nobody watches.
    """
    try:
        notified = _notify_operator(ticket_id=ticket_id, topic=topic, subject=subject,
                                    message=message, email=email, tier=tier, lang=lang)
        acked = _ack_submitter(ticket_id=ticket_id, topic=topic, subject=subject,
                               message=message, email=email, user_id=user_id)
        log.info("support: ticket %s mail (notify=%s ack=%s)", ticket_id, notified, acked)
    except Exception as exc:  # noqa: BLE001
        log.warning("support: ticket %s mail job failed (%s)", ticket_id, type(exc).__name__)


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
                  background_tasks: BackgroundTasks,
                  authorization: str | None = Header(default=None)) -> dict:
    """File a support ticket. Public — no auth required, auth honoured when offered.

    ``background_tasks`` is injected by FastAPI off the type annotation and is REQUIRED,
    with no in-route fallback: making it optional would leave a second, untested code path
    where mail runs inline again, which is precisely the failure this route was changed to
    remove. A direct in-process caller passes ``BackgroundTasks()`` and drains it.
    """
    # ---- body size (cheap early refusal; the real cap is Caddy's request_body) --
    try:
        declared = int(request.headers.get("content-length") or 0)
    except ValueError:
        declared = 0
    if declared > BODY_BYTES_MAX:
        raise HTTPException(413, "message too long")

    # ---- rate limit -----------------------------------------------------------
    # Deliberately BEFORE the honeypot and the t0 gate: those are cheap to satisfy, and a
    # bot that trips them should still burn its quota. Both keys are header-only, so this
    # costs nothing but a dict lookup.
    ip = _client_ip(request)
    peer = request.headers.get(PEER_HEADER) or ""
    if not _rate_ok(ip, peer):
        log.info("support: rate limit hit")
        raise HTTPException(429, "too many requests — please try again later")

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

    # ---- validation -----------------------------------------------------------
    topic = (body.topic or "").strip().lower()
    if topic not in TOPICS:
        raise HTTPException(400, f"topic must be one of {list(TOPICS)}")
    # Collapse to ONE line BEFORE the length check: a CRLF here would otherwise reach an
    # email header and permanently break every send on this ticket (see the module
    # docstring). Same idiom as app/main.py's thread-title validator.
    subject = " ".join((body.subject or "").split())
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

    # ---- mail: AFTER the response, never inside it ----------------------------
    # The row exists by this point, so `ok: true` already means "stored". Handing the two
    # sends to BackgroundTasks keeps a stalled relay out of the shared sync threadpool
    # (module docstring) — the response is written first, the relay is talked to second.
    background_tasks.add_task(
        _send_ticket_mail,
        ticket_id=str(ticket_id), topic=topic, subject=subject, message=message,
        email=email, tier=tier, lang=lang, user_id=user_id,
    )
    log.info("support: ticket %s filed (topic=%s authed=%s mail=deferred)",
             ticket_id, topic, bool(user_id))
    return {"ok": True, "ticket_id": str(ticket_id)}
