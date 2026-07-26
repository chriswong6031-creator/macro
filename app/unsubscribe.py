"""app/unsubscribe.py — the public unsubscribe endpoint (SEE W4, masterplan R5).

``POST /api/email/unsubscribe`` — **public and unauthenticated by design.** The person
clicking this link is, very often, precisely the person who cannot or will not sign in;
requiring a session to stop email would make the unsubscribe a dark pattern and would
break RFC 8058 one-click, which no mail client can authenticate. Authorisation comes from
the token instead: an HMAC over the identity with ``MAIL_UNSUB_SECRET``
(``mailer.unsub_token`` / ``verify_unsub_token``, constant-time compare, shipped in W1).
No token, a tampered token, or an unset secret — nothing happens and the caller is told
the link is not valid.

Two callers, one route
----------------------
1. **A human** on ``/unsubscribe.html?t=…`` presses the button; the page sends JSON.
2. **A mail client** doing RFC 8058 one-click POSTs ``List-Unsubscribe=One-Click`` as
   form data to the URL in the ``List-Unsubscribe`` header, with the token in the query
   string. Gmail and Yahoo require this of bulk senders.

So the token is read from the query string OR the JSON body, and a body that is not JSON
is not an error — it is case 2.

**Nothing mutates on GET.** Corporate mail scanners and link-preview bots fetch every URL
in an inbound message; a GET that unsubscribed would silently opt people out who never
touched the link. The page loads inert and the mutation is a POST the reader initiates.

Idempotent by construction
--------------------------
The suppression write is an upsert and the preference write is an upsert, so a second
click is a success that reports ``already: true`` — never an error, never a duplicate-key
500 shown to someone who just wants the mail to stop.

Resubscribe is a SEPARATE action, never the default, and it deliberately refuses to lift
a suppression whose reason is ``bounce`` or ``complaint``: those are not preferences the
reader gets to overrule from a link. A hard bounce means the address rejected us and a
complaint means someone pressed "spam" — sending again because a link was clicked is how
a domain's reputation dies. Only an ``unsubscribe`` (and an operator's ``manual``, from
the Email Center) is theirs to undo.

THE TOKEN IS SCOPED TO ONE ACTION
---------------------------------
The footer token authorises ``unsubscribe`` and nothing else: the action is inside the
MAC (``mailer._token_payload``), and the action is read from OUR JSON body only — never
from the query string, which is where a mail client's one-click POST cannot put it and
where an attacker could. Before that, ``?t=<any footer token>&action=resubscribe``
reversed someone's opt-out, and that token rides in every marketing footer and in the
``List-Unsubscribe`` header.

Undoing is therefore a capability the SERVER hands out, and only to the party that just
performed the opt-out in this very request: a successful, NEWLY-recorded unsubscribe
answers with a short-lived-by-construction ``resubscribe_token`` the page keeps in memory.
An already-suppressed address gets no such token, so replaying a stolen footer link cannot
manufacture one — which is precisely the escalation path that made the old design
reversible by anyone who could read one of the target's emails.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app import email_segments, mailer

log = logging.getLogger("macro.unsubscribe")
router = APIRouter()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co").rstrip("/")

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: Reasons a reader may lift themselves. `bounce` and `complaint` are deliberately absent —
#: read from the one place both writers read it, so the console and this page cannot come
#: to different conclusions about what "not removable" means.
RESUBSCRIBABLE = email_segments.SOFT_REASONS

ACTIONS = ("unsubscribe", "resubscribe")

#: Fixed-width local-part mask. Deliberately NOT `len(local) - len(head)` bullets: the
#: reply is a public answer to a bearer token, and a bullet count is the exact length of
#: the address's local part, which narrows a guess for anyone holding the reply.
_MASK = "•" * 6


def _service_key() -> str:
    """Read at CALL time so a test's monkeypatch and a systemd env reload both land."""
    return mailer.SUPABASE_SERVICE_ROLE_KEY


def _pg(method: str, path: str, body: Any = None, prefer: str | None = None,
        timeout: int = 6) -> Any:
    """Service-role PostgREST, same shape as mailer._pg / support._pg."""
    key = _service_key()
    if not key:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY unset")
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
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


def _user_email(user_id: str) -> str | None:
    """The address on a Supabase auth record (billing_emails._supabase_user_email idiom)."""
    key = _service_key()
    if not key:
        return None
    req = urllib.request.Request(
        f"{SUPABASE_URL}/auth/v1/admin/users/{urllib.parse.quote(str(user_id))}",
        headers={"apikey": key, "Authorization": f"Bearer {key}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            row = json.loads(resp.read() or b"{}")
    except Exception as exc:  # noqa: BLE001
        log.debug("unsubscribe: user email lookup failed (%s)", type(exc).__name__)
        return None
    email = (row or {}).get("email")
    return str(email).strip() if email else None


def mask(email: str) -> str:
    """``ada.lovelace@example.com`` -> ``ad••••••@example.com``.

    The page says which address it just acted on, because "we stopped the emails" is not
    an answer when someone holds three addresses. It is masked anyway: the reply is a
    public response to a token, and printing a full address back would turn a guessed or
    shoulder-surfed link into an address disclosure.

    The bullet run is FIXED WIDTH. A run sized to the local part disclosed its exact
    length to whoever presented the token — the one fact a mask is supposed to withhold,
    and the one that turns "some address at example.com" into a much smaller search.
    """
    addr = (email or "").strip()
    local, sep, domain = addr.partition("@")
    if not sep:
        return ""
    head = local[:2] if len(local) > 3 else local[:1]
    return f"{head}{_MASK}@{domain}"


# --------------------------------------------------------------------------- #
# The two mutations
# --------------------------------------------------------------------------- #
def _suppress(email: str) -> bool:
    """Put the address on the kill list. Returns whether it was ALREADY there.

    A PLAIN INSERT, and the unique violation is the success path. It used to be an upsert
    with ``resolution=merge-duplicates`` — a blanket ``do update set reason =
    excluded.reason`` — so a reader already suppressed as ``complaint`` who clicked an old
    footer link DOWNGRADED their own row to ``unsubscribe``, which :data:`RESUBSCRIBABLE`
    then let them delete from the page. Marketing resumed to an address that had filed a
    spam complaint, and the ledger recorded the removal of a mere unsubscribe. PostgREST
    cannot express a conditional ``on conflict``, so the conditional is removed instead:
    the row is never written a second time and its reason is therefore structurally
    unable to move in the weaker direction.

    The unique constraint is still what arbitrates, so the two-tabs race the upsert was
    protecting against is unchanged — a concurrent second click gets the 409 and reports
    ``already``, never a duplicate-key error shown to someone who wants the mail to stop.
    """
    addr = email.strip().lower()
    try:
        _pg("POST", "email_suppression",
            body=[{"email": addr, "reason": "unsubscribe"}],
            prefer="return=minimal")
    except urllib.error.HTTPError as exc:
        if exc.code != 409:               # 409 = 23505, the row is already there
            raise
        return True
    return False


def _unsuppress(email: str) -> str | None:
    """Lift a reader-liftable suppression. Returns the reason we REFUSED, or None on success."""
    addr = email.strip().lower()
    rows = _pg("GET", f"email_suppression?email=eq.{urllib.parse.quote(addr, safe='')}"
                      "&select=email,reason")
    if not rows:
        return None                       # nothing to lift — already subscribed
    reason = str((rows[0] or {}).get("reason") or "")
    if reason not in RESUBSCRIBABLE:
        return reason                     # bounce / complaint — not theirs to undo
    _pg("DELETE", f"email_suppression?email=eq.{urllib.parse.quote(addr, safe='')}",
        prefer="return=minimal")
    return None


def _set_opt_out(user_id: str, value: bool) -> None:
    """Upsert email_prefs.marketing_opt_out for a known user."""
    _pg("POST", "email_prefs",
        body=[{"user_id": user_id, "marketing_opt_out": value, "updated_at": "now()"}],
        prefer="resolution=merge-duplicates,return=minimal")


def apply(identity: str, action: str = "unsubscribe") -> dict:
    """Run ``action`` for a VERIFIED identity (a user id or a bare address).

    Split out from the route so the sweeper, a test, or a future operator CLI can reuse
    it without minting an HTTP request. The caller is responsible for having verified the
    token — this function trusts its argument.

    Both gates are written when the identity is a user: the address goes on
    ``email_suppression`` (which also covers a second account on the same address) and the
    per-user ``marketing_opt_out`` is set. When only one of the two can be written — no
    address on the auth record, say — the other still lands, and either alone is a
    complete stop, because ``mailer.send`` consults both.
    """
    ident = (identity or "").strip()
    action = action if action in ACTIONS else "unsubscribe"
    want_off = action == "unsubscribe"

    user_id = ident if _UUID_RE.match(ident) else None
    email = _user_email(user_id) if user_id else ident
    if not user_id and "@" not in ident:
        raise ValueError("identity is neither a user id nor an address")

    already = True
    refused: str | None = None

    if want_off:
        if email:
            already = _suppress(email)
        if user_id:
            _set_opt_out(user_id, True)
            if not email:
                already = False   # we cannot prove it was already off; report the action
    else:
        if email:
            refused = _unsuppress(email)
        if user_id and not refused:
            _set_opt_out(user_id, False)
        already = False

    out = {
        "ok": True,
        "state": "unsubscribed" if want_off else ("unsubscribed" if refused else "subscribed"),
        "already": bool(already) if want_off else False,
        "email_masked": mask(email or ""),
    }
    if refused:
        # Told plainly rather than silently ignored: a reader who presses "turn them back
        # on" and sees nothing change would reasonably assume the site is broken.
        out["refused"] = refused
    if want_off and not already:
        # THE UNDO, AND WHY IT IS CONDITIONAL. The footer token authorises `unsubscribe`
        # only, so the page needs a resubscribe-scoped token to offer "turn them back on".
        # It is minted ONLY when this request is the one that actually recorded the
        # opt-out: handing one to a caller who merely re-presented a footer link for an
        # ALREADY-suppressed address would restore the exact escalation the action scope
        # closes — read one of the target's emails, POST it, get an undo capability, put
        # them back on the list. Undoing something you did a second ago is a courtesy;
        # undoing somebody else's standing choice is the vulnerability.
        tok = mailer.unsub_token(ident, "resubscribe")
        if tok:
            out["resubscribe_token"] = tok
    return out


# --------------------------------------------------------------------------- #
# Route
# --------------------------------------------------------------------------- #
async def _read_token_and_action(request: Request) -> tuple[str, str]:
    """Token from a JSON body or the query string; action from the JSON body ONLY.

    The query string is the token's fallback because that is where RFC 8058's one-click
    POST carries it: the mail client re-posts the List-Unsubscribe URI verbatim with a
    form-encoded ``List-Unsubscribe=One-Click`` body it invented itself, and it will never
    send our JSON.

    THE ACTION IS NOT READ FROM THE QUERY STRING. It used to be, and that was the door
    that actually worked: ``POST /api/email/unsubscribe?t=<footer token>&action=resubscribe``
    with a one-click body returned 200 and deleted the suppression. No legitimate caller
    needs it there — a mail client never sends an action at all, and our own page posts
    JSON — so the parameter is simply not consulted. Belt and braces: the token itself is
    action-scoped now, so even a request that got an action past this function would fail
    verification.
    """
    token = (request.query_params.get("t") or "").strip()
    action = ""
    try:
        raw = await request.body()
    except Exception:  # noqa: BLE001
        raw = b""
    if raw:
        try:
            body = json.loads(raw)
            if isinstance(body, dict):
                token = str(body.get("t") or body.get("token") or token).strip()
                action = str(body.get("action") or "").strip()
        except Exception:  # noqa: BLE001 — a form body (one-click) is not an error
            pass
    return token, (action if action in ACTIONS else "unsubscribe")


@router.post("/api/email/unsubscribe")
async def unsubscribe(request: Request) -> dict:
    """Stop (or restart) marketing email for whoever the token attests to.

    400 for a missing/invalid token — deliberately the same answer for both, so the route
    cannot be used to test whether an address or a user id exists.

    503, never 500, when the database write fails: this is a compliance surface, and the
    difference between "we could not record your choice, try again" and "something broke"
    is the difference between a reader who retries and a reader who reports us.
    """
    token, action = await _read_token_and_action(request)
    # Verified AGAINST THE ACTION: an unsubscribe token does not verify for a resubscribe,
    # so the answer to a footer link asking to be put back on a list is the same 400 a
    # forged token gets.
    identity = mailer.verify_unsub_token(token, action) if token else None
    if not identity:
        log.info("unsubscribe: rejected a token that is invalid, absent, or not scoped to %s",
                 action)
        raise HTTPException(400, "this unsubscribe link is not valid")

    try:
        out = apply(identity, action)
    except ValueError:
        raise HTTPException(400, "this unsubscribe link is not valid") from None
    except Exception as exc:  # noqa: BLE001 — never echo the internal error
        log.warning("unsubscribe: %s failed (%s)", action, type(exc).__name__)
        raise HTTPException(503, "could not record that right now — please try again") from None

    log.info("unsubscribe: %s applied (already=%s refused=%s)",
             action, out.get("already"), out.get("refused"))
    return out
