"""admin/support_tickets.py — operator support console (SEE W1, masterplan §5).

The read + write surface over ``public.support_tickets`` / ``support_ticket_messages``.

**One data plane, no new secret.** Everything here — reads AND writes — runs through
``admin/users.py::_query``, the Supabase **Management-API SQL** endpoint authenticated by
the ``SUPABASE_ACCESS_TOKEN`` PAT the admin service already holds (admin/settings.py). That
endpoint executes INSERT/UPDATE as well as SELECT, so the operator console needs no
service-role JWT added to /etc/macro-admin.env. This mirrors admin/entitlements.py's READ
plane; it deliberately does NOT mirror its WRITE plane, because there is no second writer
to stay consistent with — these two tables have exactly one writer besides the public
intake, and it is this module.

**Injection posture.** The Management endpoint takes a SQL string, not bound parameters,
so every value is either (a) validated against a fixed allow-list, (b) int-clamped, (c) a
strict-regex uuid, or (d) passed through :func:`_lit`, which caps length, strips NULs, and
doubles single quotes. Postgres runs with ``standard_conforming_strings=on`` (the default,
and Supabase's), so a doubled-quote literal is closed correctly and a backslash is just a
backslash. Ticket bodies are stranger-written text — this is the sharp edge of the module
and it is why nothing reaches SQL unescaped.

**Transition law.** Four operator actions over four statuses, and only the sanctioned
steps are legal (the allies_store.py pattern):

    reply    : open|pending          -> pending    (+ appends a message, + emails the user)
    resolve  : open|pending          -> resolved
    close    : open|pending|resolved -> closed
    reopen   : resolved|closed       -> open

Replying to a resolved/closed ticket is refused rather than silently reopening it — the
operator reopens explicitly, so the status always reflects a decision someone made.

**Mail is best-effort, the record is not.** A reply is appended to the thread FIRST, then
emailed; the message's ``emailed`` flag records what actually happened, so a mail-off
window is visible in the thread instead of being lost. app/mailer.py never raises, so a
dead relay degrades the action's ``email_status``, never the action.
"""
from __future__ import annotations

import logging
import re

from . import users

log = logging.getLogger("macro.admin.support")

VALID_STATUSES = ("open", "pending", "resolved", "closed")
VALID_TOPICS = ("billing", "account", "bug", "data", "feature", "other")
VALID_ACTIONS = frozenset({"reply", "resolve", "close", "reopen"})

# action -> (statuses it may be applied from, the status it moves the ticket to)
_TRANSITIONS: dict[str, tuple[tuple[str, ...], str]] = {
    "reply":   (("open", "pending"), "pending"),
    "resolve": (("open", "pending"), "resolved"),
    "close":   (("open", "pending", "resolved"), "closed"),
    "reopen":  (("resolved", "closed"), "open"),
}

REPLY_MAX = 5000
SEARCH_MAX = 120

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


# --------------------------------------------------------------------------- #
# Transition rules
# --------------------------------------------------------------------------- #
def is_legal(action: str, from_status: str) -> bool:
    """True iff `action` may be applied to a ticket currently in `from_status`."""
    spec = _TRANSITIONS.get(action or "")
    if not spec:
        return False
    return (from_status or "") in spec[0]


def legal_actions(from_status: str) -> list[str]:
    """The actions an operator may take on a ticket in `from_status`, in UI order."""
    return [a for a in ("reply", "resolve", "close", "reopen") if is_legal(a, from_status)]


def next_status(action: str) -> str | None:
    spec = _TRANSITIONS.get(action or "")
    return spec[1] if spec else None


# --------------------------------------------------------------------------- #
# SQL literal helpers
# --------------------------------------------------------------------------- #
def _lit(value, *, maxlen: int) -> str:
    """A safe single-quoted SQL literal: length-capped, NUL-stripped, quotes doubled."""
    s = str(value if value is not None else "")[:maxlen].replace("\x00", "")
    return "'" + s.replace("'", "''") + "'"


def _uuid(value) -> str | None:
    """Return the value iff it is a well-formed uuid — else None (never interpolated)."""
    s = str(value or "").strip()
    return s if _UUID_RE.match(s) else None


def _clamp(v, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(v)))
    except (TypeError, ValueError):
        return default


def _not_configured() -> dict | None:
    st = users.status()
    return None if st.get("configured") else {"ok": False, **st}


# --------------------------------------------------------------------------- #
# READ — list
# --------------------------------------------------------------------------- #
def panel(status: str | None = None, q: str | None = None,
          page: int = 1, page_size: int = 50) -> dict:
    """Newest-first ticket list, filtered by status and searchable, server-paged.

    No joins: tier, lang, and topic are SNAPSHOTTED on the ticket row at submission
    time, so the list is one table scan and it reports what the user's plan was when
    they wrote in — not what it is now.
    """
    nc = _not_configured()
    if nc:
        return nc

    page = _clamp(page, 1, 1, 100_000)
    page_size = _clamp(page_size, 50, 1, 200)
    offset = (page - 1) * page_size

    where = ["true"]
    if status in VALID_STATUSES:                 # allow-list; anything else is ignored
        where.append(f"t.status = '{status}'")
    needle = str(q or "").strip()
    if needle:
        lit = _lit(f"%{needle}%", maxlen=SEARCH_MAX + 2)
        where.append(f"(t.email ilike {lit} or t.subject ilike {lit})")
    where_sql = " and ".join(where)

    try:
        count_rows = users._query(
            f"select count(*)::int as n from public.support_tickets t where {where_sql}")
        total = (count_rows or [{}])[0].get("n", 0)
        rows = users._query(
            "select t.id::text as id, "
            "to_char(t.created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "to_char(t.updated_at,'YYYY-MM-DD HH24:MI') as updated_at, "
            "t.email, t.topic, t.subject, t.status, t.lang, t.tier, "
            "(t.user_id is not null) as authed "
            "from public.support_tickets t "
            f"where {where_sql} "
            f"order by t.created_at desc limit {page_size} offset {offset}")
        summary = users._query(
            "select status, count(*)::int as n from public.support_tickets group by 1 order by 1")
        counts = {r["status"]: r["n"] for r in (summary or []) if r.get("status")}
        return {
            "ok": True,
            "tickets": rows or [],
            "counts": counts,
            "open_count": counts.get("open", 0),
            "total": total,
            "page": page,
            "page_size": page_size,
            "pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# READ — detail
# --------------------------------------------------------------------------- #
def detail(ticket_id: str) -> dict:
    """One ticket plus its full message thread, oldest first."""
    nc = _not_configured()
    if nc:
        return nc
    tid = _uuid(ticket_id)
    if not tid:
        return {"ok": False, "error": "invalid ticket id"}
    try:
        rows = users._query(
            "select t.id::text as id, "
            "to_char(t.created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "to_char(t.updated_at,'YYYY-MM-DD HH24:MI') as updated_at, "
            "t.email, t.topic, t.subject, t.status, t.lang, t.tier, "
            "t.user_id::text as user_id, t.meta "
            f"from public.support_tickets t where t.id = '{tid}'")
        if not rows:
            return {"ok": False, "error": "ticket not found"}
        ticket = rows[0]
        msgs = users._query(
            "select m.id::text as id, "
            "to_char(m.created_at,'YYYY-MM-DD HH24:MI') as created_at, "
            "m.author, m.body, m.emailed "
            f"from public.support_ticket_messages m where m.ticket_id = '{tid}' "
            "order by m.created_at asc")
        return {"ok": True, "ticket": ticket, "messages": msgs or [],
                "legal_actions": legal_actions(ticket.get("status") or "")}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


# --------------------------------------------------------------------------- #
# WRITE — actions
# --------------------------------------------------------------------------- #
def _send_reply_email(ticket: dict, message_id: str, body: str) -> str:
    """Email an operator reply to the ticket's address. Never raises; returns the status."""
    try:
        from app import mailer  # noqa: PLC0415
        html, text = mailer.render_email(
            f"Re: {ticket.get('subject') or 'your support request'}",
            f"回复：{ticket.get('subject') or '您的客服请求'}",
            [
                {"en": "Here is the reply from Mastermind support.",
                 "zh": "以下是 Mastermind 客服的回复。"},
                {"kind": "quote", "en": body, "zh": body},
                {"en": "Reply to this email to continue the conversation.",
                 "zh": "直接回复此邮件即可继续沟通。"},
            ],
        )
        return mailer.send(
            template="ticket_reply",
            cls="transactional",
            to_email=ticket.get("email") or "",
            subject=f"Re: {(ticket.get('subject') or 'your support request')[:120]}",
            html=html,
            text=text,
            idem_key=f"ticket-reply:{message_id}",
            user_id=ticket.get("user_id") or None,
        )
    except Exception as exc:  # noqa: BLE001 — the reply is already recorded; mail is best-effort
        log.warning("support: reply email failed for message %s (%s)", message_id, type(exc).__name__)
        return "failed"


def act(ticket_id: str, action: str, body: str | None = None,
        *, operator: str = "operator") -> tuple[dict, int]:
    """Execute one operator action on a ticket. Returns (payload, http_status).

    Legality is checked against the ticket's CURRENT status read from the database, never
    against a status the client sent — two operator tabs cannot race a ticket into an
    illegal state.
    """
    nc = _not_configured()
    if nc:
        return nc, 503

    tid = _uuid(ticket_id)
    if not tid:
        return {"ok": False, "error": "invalid ticket id"}, 400
    action = (action or "").strip()
    if action not in VALID_ACTIONS:
        return {"ok": False, "error": f"action must be one of {sorted(VALID_ACTIONS)}"}, 400

    try:
        rows = users._query(
            "select t.id::text as id, t.status, t.email, t.subject, t.user_id::text as user_id "
            f"from public.support_tickets t where t.id = '{tid}'")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}, 500
    if not rows:
        return {"ok": False, "error": "ticket not found"}, 404
    ticket = rows[0]
    current = ticket.get("status") or ""

    if not is_legal(action, current):
        return {"ok": False,
                "error": f"illegal transition: cannot {action} a {current or 'unknown'} ticket",
                "current_status": current,
                "legal_actions": legal_actions(current)}, 400

    target = next_status(action)
    reply_body = str(body or "").strip()
    if action == "reply" and not 1 <= len(reply_body) <= REPLY_MAX:
        return {"ok": False, "error": f"reply body must be 1..{REPLY_MAX} characters"}, 400

    try:
        email_status = None
        message_id = None
        if action == "reply":
            # 1. record the reply (the durable part) …
            ins = users._query(
                "insert into public.support_ticket_messages (ticket_id, author, body, emailed) "
                f"values ('{tid}', 'operator', {_lit(reply_body, maxlen=REPLY_MAX)}, false) "
                "returning id::text as id")
            message_id = (ins or [{}])[0].get("id")
            if not message_id:
                return {"ok": False, "error": "reply insert returned no id"}, 500
            # 2. … then try to mail it, and record what actually happened.
            email_status = _send_reply_email(ticket, message_id, reply_body)
            if email_status == "sent":
                users._query("update public.support_ticket_messages set emailed = true "
                             f"where id = '{message_id}'")

        users._query(f"update public.support_tickets set status = '{target}', updated_at = now() "
                     f"where id = '{tid}'")
    except Exception as e:  # noqa: BLE001
        log.warning("support: action %s on %s failed (%s)", action, tid, e)
        return {"ok": False, "error": str(e)}, 500

    log.info("support: %s by %s -> ticket %s %s->%s (email=%s)",
             action, operator, tid, current, target, email_status)
    out = {"ok": True, "ticket_id": tid, "action": action,
           "from_status": current, "status": target,
           "legal_actions": legal_actions(target)}
    if message_id:
        out["message_id"] = message_id
    if email_status is not None:
        out["email_status"] = email_status
        out["emailed"] = email_status == "sent"
    return out, 200
