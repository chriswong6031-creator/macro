"""app/mailer.py — outbound email transport + send ledger (SEE W1, masterplan §5).

One send path for the whole estate. Every caller goes through :func:`send`, which is
LEDGER-FIRST (SEE-R3): the ``public.email_log`` row is written BEFORE SMTP is touched,
and the row's UNIQUE ``idem_key`` is the idempotency gate. A duplicate key means the
message already went out (or is going out right now) and the send is skipped entirely —
that is what makes a webhook retry or a double-clicked operator button safe.

    send(template=…, cls='transactional'|'marketing', to_email=…, subject=…,
         html=…, text=…, idem_key=…, user_id=…, headers=…) -> status str

Returned status is one of: ``'sent'``, ``'failed'``, ``'skipped_no_smtp'``,
``'suppressed'``, ``'queued'``, ``'duplicate'``. **send() never raises for a mail reason.**
Its callers are a Stripe-style webhook and a public unauthenticated form (G2/G7): a broken
SMTP relay, a suppressed address, or an unreachable Supabase must degrade to a status string
and a log line, never to a 500 that makes an upstream retry forever.

Class law
---------
``cls='marketing'`` consults ``email_suppression`` (by address) and
``email_prefs.marketing_opt_out`` (by user, when a user id is known) and refuses to send
when either says no. ``cls='transactional'`` NEVER consults them — a user who opted out of
marketing has not opted out of being answered about their own support ticket or of getting
their receipt. An unrecognised class is coerced to ``'marketing'``, i.e. to the STRICTER
path, so a future typo can never turn a broadcast into unsuppressable mail.

Marketing is additionally **fail-closed on the lookup itself**: if the suppression/opt-out
read errors, the message is NOT sent — the ledger row is parked at ``status='queued'`` with
``detail='suppression_lookup_failed'`` and ``'queued'`` is returned. Mailing an unsubscriber
because Supabase blinked is a compliance problem and a reputation hit; a delayed campaign is
neither. **Drain contract (W4):** the drain re-checks suppression for ``queued`` rows and
completes them by PATCHing THAT row — it must never call :func:`send` again with the same
idem_key, which would hit the unique constraint and return ``'duplicate'`` without sending.

Mail-off mode
-------------
With no SMTP credentials configured, :func:`is_configured` is False and every send lands a
``skipped_no_smtp`` ledger row and returns. The whole product works in this mode — tickets
file, replies append, the operator just does not get email until the creds land
(docs/ops/email-support-setup.md §4).

Secrets (MAIL_SMTP_*, MAIL_FROM, MAIL_UNSUB_SECRET, SUPABASE_SERVICE_ROLE_KEY) come from
/etc/macro-api.env — never the repo. Every one of them is optional; nothing here raises on
a missing key.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import html as _html
import json
import logging
import os
import smtplib
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from typing import Any

log = logging.getLogger("macro.mailer")

# --------------------------------------------------------------------------- #
# Config / environment
# --------------------------------------------------------------------------- #
# Supabase is read at IMPORT time, mirroring app/billing.py's module-level constants —
# tests monkeypatch the module attribute (or _pg itself), which is the house idiom for
# this pair.
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://fsldfzlxyavsuwqbceod.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

_DEFAULT_SMTP_PORT = 587
_SMTP_TIMEOUT = 10          # seconds, connect + command; two attempts bound the wall clock
_SEND_ATTEMPTS = 2          # one retry, only on a transient connection failure
_RETRY_BACKOFF_SEC = 1.5    # a 421 "too many connections" needs a beat, not an instant retry

CLASSES = ("transactional", "marketing")
STATUSES = ("sent", "failed", "skipped_no_smtp", "suppressed", "queued")


def _env(name: str, default: str = "") -> str:
    """Mail settings are read at CALL time (not import time) so a systemd env reload — and a
    test's monkeypatch.setenv — takes effect without a process restart. Mail-off vs mail-on is
    a live operational state, not a boot flag (billing._stripe() / regwall._enabled() idiom)."""
    return (os.environ.get(name) or default).strip()


def smtp_host() -> str:
    return _env("MAIL_SMTP_HOST")


def smtp_port() -> int:
    try:
        return int(_env("MAIL_SMTP_PORT") or _DEFAULT_SMTP_PORT)
    except ValueError:
        return _DEFAULT_SMTP_PORT


def smtp_user() -> str:
    return _env("MAIL_SMTP_USER")


def smtp_pass() -> str:
    # Whitespace-stripped like every other value: surrounding whitespace on a relay
    # password is a paste artifact, and deploy-api-secrets.yml's _add strips it on the
    # way to /etc/macro-api.env anyway, so stripping here keeps the two consistent.
    return _env("MAIL_SMTP_PASS")


def mail_from() -> str:
    return _env("MAIL_FROM")


def reply_to() -> str:
    return _env("MAIL_REPLY_TO")


def support_to() -> str:
    """Where new-ticket operator notifications go. Empty → notifications are skipped."""
    return _env("MAIL_SUPPORT_TO")


def is_configured() -> bool:
    """True only when a real authenticated relay is fully specified.

    Host + user + pass + from. A partial config is treated as mail-off rather than
    attempted-and-failed: half a relay produces a slow timeout on every request, which is
    a worse failure than an honest ``skipped_no_smtp``.
    """
    return bool(smtp_host() and smtp_user() and smtp_pass() and mail_from())


# --------------------------------------------------------------------------- #
# PostgREST helper (service-role — same shape as app/billing.py::_pg)
# --------------------------------------------------------------------------- #
class DuplicateKey(Exception):
    """The email_log unique idem_key already exists — this message was already handled."""


class SuppressionUnavailable(Exception):
    """The suppression / opt-out lookup could not be completed. Marketing must NOT send."""


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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as exc:
        # PostgREST answers 409 with SQLSTATE 23505 on a unique violation. Translate it
        # into the sentinel the idempotency gate reads, so the caller never has to parse
        # an HTTP error body.
        if exc.code == 409:
            raise DuplicateKey(str(exc)) from None
        raise
    return json.loads(raw) if raw else None


# --------------------------------------------------------------------------- #
# Ledger operations
# --------------------------------------------------------------------------- #
def _ledger_insert(*, idem_key: str, template: str, cls: str, to_email: str,
                   user_id: str | None) -> None:
    """Claim the idem_key with a status='queued' row. Raises DuplicateKey on a replay."""
    _pg("POST", "email_log",
        body=[{
            "idem_key": idem_key,
            "template": template,
            "class": cls,
            "to_email": to_email,
            "user_id": user_id,
            "status": "queued",
        }],
        prefer="return=minimal")


def _ledger_finish(idem_key: str, status: str, detail: str | None = None) -> None:
    """Move the claimed row to its terminal status. Best-effort — a ledger write failure
    must never turn a delivered email into an exception at the caller."""
    try:
        _pg("PATCH", f"email_log?idem_key=eq.{urllib.parse.quote(idem_key, safe='')}",
            body={"status": status, "detail": detail},
            prefer="return=minimal")
    except Exception as exc:  # noqa: BLE001
        log.warning("mailer: ledger finish %s -> %s failed (%s)", idem_key, status, type(exc).__name__)


def _suppression_reason(to_email: str, user_id: str | None) -> str | None:
    """Why this MARKETING message must not be sent, or None when it may go.

    Two independent gates: the address-level kill list (covers people who never
    registered) and the per-user preference.

    FAIL-CLOSED. A lookup error raises SuppressionUnavailable rather than returning None,
    and the caller parks the message as 'queued' instead of sending it. Mailing someone who
    unsubscribed because Supabase blinked is a CAN-SPAM/GDPR problem and a complaint that
    costs sender reputation; a delayed campaign is neither. The transactional class never
    reaches this function at all, so its fail-open behaviour is unaffected.
    """
    addr = (to_email or "").strip().lower()
    if addr:
        try:
            rows = _pg("GET", f"email_suppression?email=eq.{urllib.parse.quote(addr, safe='')}&select=email,reason")
        except Exception as exc:  # noqa: BLE001
            log.warning("mailer: suppression lookup failed for %s (%s)", addr, type(exc).__name__)
            raise SuppressionUnavailable(type(exc).__name__) from None
        if rows:
            return str(rows[0].get("reason") or "suppressed")
    if user_id:
        try:
            rows = _pg("GET", f"email_prefs?user_id=eq.{urllib.parse.quote(str(user_id), safe='')}"
                              "&select=marketing_opt_out")
        except Exception as exc:  # noqa: BLE001
            log.warning("mailer: prefs lookup failed for %s (%s)", user_id, type(exc).__name__)
            raise SuppressionUnavailable(type(exc).__name__) from None
        if rows and rows[0].get("marketing_opt_out"):
            return "marketing_opt_out"
    return None


# --------------------------------------------------------------------------- #
# SMTP transport
# --------------------------------------------------------------------------- #
# NOTE ordering: smtplib.SMTPException subclasses OSError, so a bare `except OSError`
# would swallow authentication and recipient failures too. The send loop lists
# _PERMANENT FIRST so those break out immediately; only what falls through to
# _TRANSIENT (connection dropped / refused / timed out) is worth the one retry.
# Retrying a bad password or a refused recipient just burns the wall-clock budget and
# reproduces the same error.
_PERMANENT = (
    smtplib.SMTPAuthenticationError,
    smtplib.SMTPRecipientsRefused,
    smtplib.SMTPSenderRefused,
    smtplib.SMTPDataError,
    smtplib.SMTPNotSupportedError,
)
_TRANSIENT = (
    smtplib.SMTPServerDisconnected,
    smtplib.SMTPConnectError,
    ConnectionError,
    TimeoutError,
    OSError,          # socket-level failures raised straight out of SMTP.connect()
)


def _smtp_send(msg: EmailMessage) -> None:
    """Deliver one message over the configured relay. Raises on failure.

    Port 465 is implicit TLS (SMTP_SSL); everything else is STARTTLS on a plain
    connection — the shape used by the greydeercapital intake relay, stdlib only.
    """
    host, port = smtp_host(), smtp_port()
    ctx = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=_SMTP_TIMEOUT, context=ctx) as s:
            s.login(smtp_user(), smtp_pass())
            s.send_message(msg)
        return
    with smtplib.SMTP(host, port, timeout=_SMTP_TIMEOUT) as s:
        s.ehlo()
        s.starttls(context=ctx)
        s.ehlo()
        s.login(smtp_user(), smtp_pass())
        s.send_message(msg)


def _header_safe(value: str, *, limit: int = 400) -> str:
    """Collapse a value to ONE line so it can never inject an email header.

    A CR/LF that reaches ``msg["Subject"]`` makes Python's email library raise, which — on
    this estate — would not merely garble one message: the operator notification and EVERY
    future reply on that ticket (subject = ``Re: <stored subject>``) would fail forever. The
    ticket subject is stranger-written text, so this is the chokepoint that has to hold, and
    it holds for every caller rather than trusting each one to sanitise first.
    """
    return " ".join(str(value or "").split())[:limit]


def _build_message(*, to_email: str, subject: str, html: str, text: str,
                   cls: str, headers: dict | None) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = _header_safe(subject)
    msg["From"] = mail_from()
    # Same one-line rule for every other header we set. To/Reply-To come from validated or
    # operator-configured sources today, but "today" is not a security boundary.
    msg["To"] = _header_safe(to_email, limit=320)
    rt = reply_to()
    if rt:
        msg["Reply-To"] = _header_safe(rt, limit=320)
    msg.set_content(text or "")
    if html:
        msg.add_alternative(html, subtype="html")

    extra = dict(headers or {})
    # One-click unsubscribe (RFC 8058) — REQUIRED by Gmail/Yahoo bulk-sender rules for
    # marketing mail, and forbidden noise on transactional mail. The caller supplies the
    # signed URL (see unsub_token); we only wire the headers.
    unsub_url = extra.pop("unsubscribe_url", None) or extra.pop("List-Unsubscribe-URL", None)
    if cls == "marketing" and unsub_url:
        # RFC 8058 wants the https URI (the one-click target). A mailto: alternative is
        # optional but real: it is the only unsubscribe route that still works for a
        # reader whose client cannot or will not make the POST, and for the operator
        # reading a bounce mailbox. Listed FIRST because the RFC's grammar puts the
        # non-http alternative first and Gmail reads the https one regardless. Absent
        # MAIL_UNSUB_MAILTO the header is byte-identical to what W1 shipped.
        mailto = _env("MAIL_UNSUB_MAILTO")
        prefix = f"<mailto:{_header_safe(mailto, limit=320)}>, " if mailto else ""
        msg["List-Unsubscribe"] = f"{prefix}<{_header_safe(unsub_url, limit=1000)}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    for k, v in extra.items():
        if v is None:
            continue
        try:
            msg[_header_safe(k, limit=100)] = _header_safe(v, limit=1000)
        except Exception:  # noqa: BLE001 — a malformed custom header never blocks the send
            log.warning("mailer: dropped malformed header %r", k)
    return msg


# --------------------------------------------------------------------------- #
# The single send path
# --------------------------------------------------------------------------- #
def send(*, template: str, cls: str, to_email: str, subject: str, html: str, text: str,
         idem_key: str, user_id: str | None = None, headers: dict | None = None) -> str:
    """Send one email through the ledger. Returns the final status; never raises.

    Order (SEE-R3, ledger-first):
      1. INSERT email_log(status='queued') keyed on ``idem_key``. A unique violation →
         return ``'duplicate'`` WITHOUT sending. This is the whole idempotency gate.
      2. marketing only: suppression / opt-out → PATCH ``'suppressed'``, return it.
      3. mail-off → PATCH ``'skipped_no_smtp'``, return it.
      4. SMTP (one retry on a transient connection failure) → PATCH ``'sent'`` or
         ``'failed'``. ``detail`` on failure is the exception CLASS NAME only — never a
         message body, an address list, or anything that could carry a credential.
    """
    cls = cls if cls in CLASSES else "marketing"   # unknown → the stricter (suppressible) class
    to_email = (to_email or "").strip()
    if not to_email:
        log.warning("mailer: %s has no recipient — dropped", template)
        return "failed"
    if not idem_key:
        log.warning("mailer: %s has no idem_key — dropped (idempotency is not optional)", template)
        return "failed"

    # ---- 1. ledger claim -------------------------------------------------------
    ledgered = True
    try:
        _ledger_insert(idem_key=idem_key, template=template, cls=cls,
                       to_email=to_email, user_id=user_id)
    except DuplicateKey:
        log.info("mailer: %s duplicate idem_key %s — not sending", template, idem_key)
        return "duplicate"
    except Exception as exc:  # noqa: BLE001
        # The ledger is unreachable (no service-role key, network, table absent). We
        # proceed WITHOUT the idempotency guarantee rather than dropping the message:
        # for the traffic on this path (a support reply, an operator alert) a lost mail
        # is a real product failure and a rare duplicate is an annoyance. Logged loudly
        # so the degraded mode is visible, and every later PATCH is skipped.
        ledgered = False
        log.warning("mailer: ledger unavailable for %s (%s) — sending WITHOUT idempotency",
                    template, type(exc).__name__)

    def _finish(status: str, detail: str | None = None) -> str:
        if ledgered:
            _ledger_finish(idem_key, status, detail)
        return status

    # ---- 2. marketing suppression (FAIL-CLOSED) --------------------------------
    if cls == "marketing":
        try:
            reason = _suppression_reason(to_email, user_id)
        except SuppressionUnavailable as exc:
            # We could not prove this address is still willing to hear from us, so we do
            # not send. The row is PARKED at 'queued' with a detail the W4 drain looks for.
            #
            # DRAIN CONTRACT (W4, documented here because it constrains this row's shape):
            # the drain re-checks suppression for rows left at status='queued' and, on a
            # clean lookup, sends and PATCHes THIS row to its terminal status. It must NOT
            # call send() again with the same idem_key — that would hit the unique
            # constraint and return 'duplicate' without ever sending. The claimed row is
            # the work item; the drain completes it in place.
            log.warning("mailer: %s parked as queued — suppression lookup unavailable (%s)",
                        template, exc)
            return _finish("queued", "suppression_lookup_failed")
        if reason:
            log.info("mailer: %s suppressed (%s)", template, reason)
            return _finish("suppressed", reason)

    # ---- 3. mail-off ------------------------------------------------------------
    if not is_configured():
        log.info("mailer: %s skipped — SMTP not configured", template)
        return _finish("skipped_no_smtp", "MAIL_SMTP_* unset")

    # ---- 4. transport ------------------------------------------------------------
    try:
        msg = _build_message(to_email=to_email, subject=subject, html=html, text=text,
                             cls=cls, headers=headers)
    except Exception as exc:  # noqa: BLE001
        log.warning("mailer: %s could not be composed (%s)", template, type(exc).__name__)
        return _finish("failed", type(exc).__name__)

    last: Exception | None = None
    for attempt in range(_SEND_ATTEMPTS):
        try:
            _smtp_send(msg)
            log.info("mailer: %s sent (%s)", template, cls)
            return _finish("sent")
        except _PERMANENT as exc:   # listed first: these subclass OSError, see above
            last = exc
            break
        except _TRANSIENT as exc:
            last = exc
            if attempt + 1 < _SEND_ATTEMPTS:
                # A short beat, not an instant retry: the common transient here is a relay
                # 421 ("too many connections"), and hammering it again in the same
                # millisecond reproduces the throttle rather than clearing it.
                log.info("mailer: %s transient %s — retrying once after %.1fs",
                         template, type(exc).__name__, _RETRY_BACKOFF_SEC)
                time.sleep(_RETRY_BACKOFF_SEC)
                continue
        except Exception as exc:  # noqa: BLE001 — anything else: no retry, it will repeat
            last = exc
            break
    log.warning("mailer: %s send failed (%s)", template, type(last).__name__ if last else "unknown")
    return _finish("failed", type(last).__name__ if last else "unknown")


# --------------------------------------------------------------------------- #
# Base template — the W-D DESIGN PIN
#
# This IS mockups/support_email/email_base.html, expressed as a renderer. W1 shipped a
# deliberately plain functional base and said W2 would swap it; this is that swap, so
# every send in the estate (ticket ack, ticket reply, operator alert, and W3's billing
# receipts) already comes out of the pinned shell.
#
# The seven hard rules from PIN §6.2, every one of which exists because breaking it
# breaks a real client:
#   1. Tables for layout, `role="presentation" border=0 cellpadding=0 cellspacing=0`.
#      No flex, no grid, no float.
#   2. All CSS inline on the element. The <style> block is PROGRESSIVE ENHANCEMENT ONLY
#      (dark + mobile) — Gmail strips <style> in several contexts, so nothing in it may
#      be load-bearing.
#   3. NO IMAGES. The brand is text. A blocked logo makes a billing email look like
#      phishing.
#   4. width="600" + max-width:600px; fluid below 620px via the media query.
#   5. background-color AND color on the SAME element, always — Gmail/Outlook.com
#      force-invert regardless of `color-scheme`, and an inverter that flips only the
#      background is what produces black-on-black.
#   6. Buttons are table-based (bulletproof). border-radius is decoration; Outlook drops
#      it and renders a square button. Accepted degrade.
#   7. Every sentence obeys docs/DESIGN_DOCTRINE.md: plain words, no internal vocabulary.
#
# The signature detail is the brand gradient rendered as THREE SOLID <td>s at 4px
# (PIN §6.4): a CSS gradient silently disappears in Outlook and a gradient image would be
# blocked, but three solid cells paint identically everywhere.
#
# Class discipline (PIN §6.7 / masterplan R5): the unsubscribe slot renders ONLY when the
# caller passes an unsubscribe_url — i.e. only for marketing. A receipt or a ticket
# acknowledgment is information the reader is owed and the send happens regardless of
# marketing opt-out, so an unsubscribe link on one would lie about what it does.
# --------------------------------------------------------------------------- #
_BRAND = "MASTERMIND"
_FOOTER_BRAND = "Mastermind"
_SITE_URL = "https://www.mastermind-x.com"
_SITE_LABEL = "mastermind-x.com"
_SUPPORT_ADDR = "support@mastermind-x.com"
_WHY_EN = "You received this because you contacted Mastermind support or hold an account with us."
_WHY_ZH = "你收到这封邮件，是因为你联系了 Mastermind 客服，或拥有我们的账户。"

# PIN §6.1 palette. Light-first; the dark values live in the media query below.
_C_CANVAS = "#eef1f5"
_C_CARD = "#ffffff"
_C_BAND = "#0f1115"      # dark in BOTH schemes — it is the product's identity, and an
_C_TEXT = "#1c2430"      # already-dark band is the safest thing to hand an inverter.
_C_MUTED = "#5d6b7e"
_C_RULE = "#e3e7ee"
_C_SLIP = "#f6f8fb"
_C_CTA = "#285fff"
_C_FOOT = "#7b8798"
_C_DIM = "#8b93a1"       # eyebrow + 中文 divider chip, on both schemes
_G1, _G2, _G3 = "#3b82f6", "#6366f1", "#7c5cff"

# PIN §6.3. The ZH stacks lead with a CJK sans: the mono/Latin stacks carry no Hanzi, so
# a ZH string falls through to whatever the system picks — on some machines a serif.
_F_UI = ("-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,"
         "'PingFang SC','Microsoft YaHei',sans-serif")
_F_ZH = ("-apple-system,BlinkMacSystemFont,'PingFang SC','Hiragino Sans GB',"
         "'Microsoft YaHei',sans-serif")
_F_MONO = "SFMono-Regular,Consolas,'Liberation Mono',Menlo,monospace"
_F_MONO_ZH = "SFMono-Regular,Consolas,'Liberation Mono',Menlo,'PingFang SC',monospace"

# Progressive enhancement only (rule 2): mobile reflow + the Apple/iOS/Outlook-macOS dark
# overlay. Gmail honours neither reliably, which is what the paired bg+color protects.
_STYLE = f"""  @media (max-width:620px) {{
    .mx-shell   {{ width:100% !important; max-width:100% !important; }}
    .mx-pad     {{ padding-left:22px !important; padding-right:22px !important; }}
    .mx-band    {{ padding-left:22px !important; padding-right:22px !important; }}
    .mx-h1      {{ font-size:23px !important; line-height:1.25 !important; }}
    .mx-btn a   {{ display:block !important; text-align:center !important; }}
    .mx-slip-k  {{ width:auto !important; }}
  }}
  @media (prefers-color-scheme: dark) {{
    .mx-canvas  {{ background-color:#0b0d11 !important; }}
    .mx-card    {{ background-color:#181b21 !important; }}
    .mx-text    {{ color:#d7dce3 !important; }}
    .mx-muted   {{ color:#96a0b0 !important; }}
    .mx-rule    {{ border-color:#2a2f3a !important; }}
    .mx-slip    {{ background-color:#1e222a !important; border-color:#2a2f3a !important; }}
    .mx-slip-v  {{ color:#d7dce3 !important; }}
    .mx-slip-k  {{ color:#96a0b0 !important; }}
    .mx-link    {{ color:#7aa7e0 !important; }}
    .mx-foot    {{ color:#8b93a1 !important; }}
  }}"""


def _esc(s: Any) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def _ui(lang: str) -> str:
    return _F_ZH if lang == "zh" else _F_UI


def _slip_html(rows: list, lang: str) -> str:
    """PIN §6.5 detail slip — deliberately the same key/value anatomy as the ticket slip
    on /support.html, so the site and the inbox read as one product. Values are mono so
    money and dates align; ZH KEYS use the UI face at 11.5px with no tracking (§2.1)."""
    if not rows:
        return ""
    k_font = (f"font-family:{_F_ZH}; font-size:11.5px; font-weight:600;"
              if lang == "zh" else
              f"font-family:{_F_MONO}; font-size:10px; font-weight:600;"
              " letter-spacing:1.3px; text-transform:uppercase;")
    v_font = _F_MONO_ZH if lang == "zh" else _F_MONO
    cells = []
    last = len(rows) - 1
    for i, (k, v) in enumerate(rows):
        edge = "" if i == last else f" border-bottom:1px solid {_C_RULE};"
        cells.append(
            f'<tr>'
            f'<td class="mx-slip-k" width="150" style="padding:11px 16px;{edge} {k_font}'
            f' color:{_C_MUTED}; vertical-align:top;">{_esc(k)}</td>'
            f'<td class="mx-slip-v" style="padding:11px 16px 11px 0;{edge}'
            f' font-family:{v_font}; font-size:13px; color:{_C_TEXT};">{_esc(v)}</td>'
            f'</tr>'
        )
    return (f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"'
            f' class="mx-slip" bgcolor="{_C_SLIP}" style="background-color:{_C_SLIP};'
            f' border:1px solid {_C_RULE}; border-radius:10px; margin:0 0 22px;">'
            + "".join(cells) + "</table>")


def _block_html(b: dict, lang: str) -> str:
    kind = (b.get("kind") or "p").lower()
    val = b.get(lang)
    if val in (None, "", []):
        return ""
    face = _ui(lang)
    if kind == "kv":
        return _slip_html(list(val), lang)
    if kind == "quote":
        # The reader's own words handed back (PIN §7.7): muted, mono-free, line breaks
        # kept. <br /> rather than white-space:pre-wrap alone — several clients drop the
        # declaration, and a quote that collapses to one paragraph loses the shape of
        # what the person actually wrote.
        body = _esc(val).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br />")
        return (f'<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"'
                f' class="mx-slip" bgcolor="{_C_SLIP}" style="background-color:{_C_SLIP};'
                f' border:1px solid {_C_RULE}; border-radius:10px; margin:0 0 22px;">'
                f'<tr><td class="mx-muted" style="padding:14px 16px; font-family:{face};'
                f' font-size:14px; line-height:1.65; color:{_C_MUTED};">{body}</td></tr></table>')
    if kind == "button":
        # Bulletproof table button (rule 6). One CTA per email, maximum; the label is the
        # verb of what happens, never "Click here".
        url = b.get("url") or _SITE_URL
        return (f'<table role="presentation" border="0" cellpadding="0" cellspacing="0"'
                f' class="mx-btn" style="margin:0 0 20px;"><tr>'
                f'<td align="center" bgcolor="{_C_CTA}" style="background-color:{_C_CTA};'
                f' border-radius:8px;">'
                f'<a href="{_esc(url)}" style="display:inline-block; padding:13px 26px;'
                f' font-family:{face}; font-size:15px; font-weight:600; line-height:1;'
                f' color:#ffffff; text-decoration:none; border-radius:8px;">{_esc(val)}</a>'
                f'</td></tr></table>')
    if kind == "links":
        # PIN §7.6 — "three one-line links, NOT a slip". A slip is for facts you read
        # (plan, price, date); this is a list of places you go, and rendering it as a
        # key/value table would make three destinations look like three data points.
        # One <a> per row, no bullets, no button styling — the CTA below is the one
        # thing meant to look pressable.
        rows = []
        for label, url in list(val):
            rows.append(
                f'<tr><td style="padding:0 0 9px; font-family:{face}; font-size:14.5px;'
                f' line-height:1.5;">'
                f'<a class="mx-link" href="{_esc(url)}" style="color:{_C_CTA};'
                f' text-decoration:none; border-bottom:1px solid {_C_RULE};">{_esc(label)}</a>'
                f'</td></tr>')
        return ('<table role="presentation" border="0" cellpadding="0" cellspacing="0"'
                ' width="100%" style="margin:0 0 22px;">' + "".join(rows) + "</table>")
    if kind == "fine":
        lh = "1.7" if lang == "zh" else "1.55"
        return (f'<p class="mx-muted" style="margin:0 0 14px; font-family:{face};'
                f' font-size:13px; line-height:{lh}; color:{_C_MUTED};">{_esc(val)}</p>')
    lh = "1.75" if lang == "zh" else "1.6"
    size = "14.5px" if lang == "zh" else "15px"
    return (f'<p class="mx-muted" style="margin:0 0 22px; font-family:{face};'
            f' font-size:{size}; line-height:{lh}; color:{_C_MUTED};">{_esc(val)}</p>')


def _block_text(b: dict, lang: str) -> str:
    kind = (b.get("kind") or "p").lower()
    val = b.get(lang)
    if val in (None, "", []):
        return ""
    if kind == "kv":
        return "\n".join(f"{k}: {v}" for k, v in val)
    if kind == "quote":
        return "\n".join("> " + line for line in str(val).splitlines())
    if kind == "button":
        return f"{val}: {b.get('url') or _SITE_URL}"
    if kind == "links":
        return "\n".join(f"{label}: {url}" for label, url in val)
    return str(val)


def _shared_section_html(blocks: list[dict]) -> str:
    """The ``once`` blocks, rendered ONCE below both language halves.

    Some content belongs to neither language: a quote of the reader's own words IS their
    words, untranslated, so rendering it inside each half printed the same text twice and
    doubled the size of every message carrying one — a 5000-char support message shipped
    ~10000 chars of duplicated quote. A ``once`` block renders here instead, under its own
    bilingual micro-label so it still says what it is in whichever language the reader has.

    ``label_en`` / ``label_zh`` are optional; without them the block renders bare.
    """
    once = [b for b in blocks if b.get("once")]
    if not once:
        return ""
    out = []
    for b in once:
        body = _block_html(b, "en") or _block_html(b, "zh")
        if not body:
            continue
        label = ""
        l_en, l_zh = b.get("label_en") or "", b.get("label_zh") or ""
        if l_en or l_zh:
            joined = " · ".join(x for x in (l_en, l_zh) if x)
            label = (f'<p style="margin:0 0 8px; font-family:{_F_MONO_ZH}; font-size:10px;'
                     f' font-weight:600; letter-spacing:1.3px; text-transform:uppercase;'
                     f' color:{_C_DIM};">{_esc(joined)}</p>')
        out.append(f'<tr><td class="mx-pad" style="padding:0 32px;">{label}{body}</td></tr>')
    return "".join(out)


def _lang_section_html(title: str, blocks: list[dict], lang: str) -> str:
    """One language's half of the card: heading + every block, in order.

    ``once`` blocks are skipped here — :func:`_shared_section_html` renders them a single
    time below both halves.
    """
    body = "".join(_block_html(b, lang) for b in blocks if not b.get("once"))
    if lang == "zh":
        head = (f'<h2 class="mx-text" style="margin:0 0 10px; font-family:{_F_ZH};'
                f' font-size:20px; line-height:1.35; font-weight:700; color:{_C_TEXT};">'
                f'{_esc(title)}</h2>')
        pad = "22px 32px 0"
    else:
        head = (f'<h1 class="mx-h1 mx-text" style="margin:0 0 10px; font-family:{_F_UI};'
                f' font-size:25px; line-height:1.22; font-weight:700; letter-spacing:-0.4px;'
                f' color:{_C_TEXT};">{_esc(title)}</h1>')
        pad = "30px 32px 0"
    return f'<tr><td class="mx-pad" style="padding:{pad};">{head}{body}</td></tr>'


def render_email(title_en: str, title_zh: str, blocks: list[dict], *,
                 eyebrow: str = "", preheader: str = "",
                 why_en: str | None = None, why_zh: str | None = None,
                 unsubscribe_url: str = "") -> tuple[str, str]:
    """Render one dual-language message in the pinned shell. Returns ``(html, text)``.

    ``blocks`` is a list of dicts, each carrying an ``en`` and a ``zh`` value plus an
    optional ``kind``:

        {"en": "…", "zh": "…"}                          lede / body paragraph (default)
        {"kind": "fine",   "en": "…", "zh": "…"}        fine print — the honest caveat
        {"kind": "quote",  "en": "…", "zh": "…"}        the reader's own words, verbatim
        {"kind": "kv",     "en": [(k, v), …], "zh": […]} the detail slip
        {"kind": "button", "en": "…", "zh": "…", "url": "…"}   at most ONE per email

    Any block may add ``"once": True``: it is then rendered a SINGLE time below both
    language halves rather than inside each, with an optional ``label_en`` / ``label_zh``
    micro-label above it. That is for content which is not translated because it cannot be
    — a quote of the sender's own message — where printing it in both halves is pure
    duplication and, on a long message, doubles the size of the email.

    Keyword extras (all optional, all named by PIN §6):
        eyebrow          the email's class label in the dark band — 1-2 words, English,
                         uppercase (RECEIPT · TRIAL · UPGRADE · PAYMENT · SUPPORT · REPLY).
                         It is a filing label, not a sentence, so it is never translated.
        preheader        the ~90 chars the inbox list shows beside the subject. Say the ONE
                         fact the reader needs before opening; never repeat the subject.
        why_en / why_zh  the "why you received this" line. State the actual trigger.
        unsubscribe_url  MARKETING ONLY. Passing it renders the unsubscribe slot; leaving
                         it empty deletes the whole block, which is what every
                         transactional send must do (PIN §6.7).

    Both languages ship in EVERY message, English first, then a labelled 中文 rule, then
    the Chinese half — we do not guess which one the reader wants from a stored preference
    that may be stale or absent (masterplan R4). Every value is HTML-escaped: a support
    ticket body is untrusted text written by a stranger, and it lands in an inbox.
    """
    blocks = list(blocks or [])
    why_en = _WHY_EN if why_en is None else why_en
    why_zh = _WHY_ZH if why_zh is None else why_zh
    shared = _shared_section_html(blocks)

    # The trailing entity run stops Gmail pulling body copy in after the preheader.
    pre = ""
    if preheader:
        filler = "&#8199;&#65279;" * 8
        pre = (f'<div style="display:none; font-size:1px; color:{_C_CANVAS}; line-height:1px;'
               f' max-height:0; max-width:0; opacity:0; overflow:hidden;">{_esc(preheader)}'
               f' {filler}</div>')

    eyebrow_td = (
        f'<td align="right" style="font-family:{_F_MONO}; font-size:10px; font-weight:600;'
        f' letter-spacing:1.6px; color:{_C_DIM}; white-space:nowrap;">{_esc(eyebrow)}</td>'
        if eyebrow else ""
    )

    unsub = ""
    if unsubscribe_url:
        unsub = (
            f'<p class="mx-foot" style="margin:0 0 8px; font-family:{_F_UI}; font-size:12px;'
            f' line-height:1.6; color:{_C_FOOT};">'
            f'<a class="mx-link" href="{_esc(unsubscribe_url)}" style="color:{_C_MUTED};'
            f' text-decoration:underline;">Unsubscribe</a>&nbsp;·&nbsp;'
            f'<a class="mx-link" href="{_esc(unsubscribe_url)}" style="color:{_C_MUTED};'
            f' text-decoration:underline;">退订</a></p>'
        )

    html = f"""<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" lang="en">
<head>
<meta http-equiv="Content-Type" content="text/html; charset=UTF-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="color-scheme" content="light dark" />
<meta name="supported-color-schemes" content="light dark" />
<title>{_esc(title_en)}</title>
<style type="text/css">
{_STYLE}
</style>
</head>
<body class="mx-canvas" bgcolor="{_C_CANVAS}" style="margin:0; padding:0; width:100%;
  background-color:{_C_CANVAS}; -webkit-text-size-adjust:100%; -ms-text-size-adjust:100%;">
{pre}
<table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%"
  class="mx-canvas" bgcolor="{_C_CANVAS}" style="background-color:{_C_CANVAS};">
<tr>
<td align="center" style="padding:28px 12px 40px;">

  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="600"
    class="mx-shell" style="width:600px; max-width:600px;">

    <tr><td>
      <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse:collapse;">
        <tr>
          <td width="33.33%" height="4" bgcolor="{_G1}" style="background-color:{_G1}; height:4px; font-size:0; line-height:0;">&nbsp;</td>
          <td width="33.33%" height="4" bgcolor="{_G2}" style="background-color:{_G2}; height:4px; font-size:0; line-height:0;">&nbsp;</td>
          <td width="33.34%" height="4" bgcolor="{_G3}" style="background-color:{_G3}; height:4px; font-size:0; line-height:0;">&nbsp;</td>
        </tr>
      </table>
    </td></tr>

    <tr>
      <td class="mx-band" bgcolor="{_C_BAND}" style="background-color:{_C_BAND}; padding:18px 32px;">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
          <tr>
            <td align="left" style="font-family:{_F_UI}; font-size:14px; font-weight:700;
              letter-spacing:2.2px; color:#ffffff; white-space:nowrap;">{_BRAND}</td>
            {eyebrow_td}
          </tr>
        </table>
      </td>
    </tr>

    <tr>
      <td class="mx-card" bgcolor="{_C_CARD}" style="background-color:{_C_CARD};">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
          {_lang_section_html(title_en, blocks, "en")}
          <tr>
            <td class="mx-pad" style="padding:26px 32px 0;">
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td class="mx-rule" style="border-top:1px solid {_C_RULE}; font-size:0; line-height:0;">&nbsp;</td>
                  <td width="52" align="center" style="font-family:{_F_ZH}; font-size:11px;
                    font-weight:600; letter-spacing:1px; color:{_C_DIM}; padding:0 4px;">中文</td>
                  <td class="mx-rule" style="border-top:1px solid {_C_RULE}; font-size:0; line-height:0;">&nbsp;</td>
                </tr>
              </table>
            </td>
          </tr>
          {_lang_section_html(title_zh, blocks, "zh")}
          {shared}
          <tr><td style="height:30px; font-size:0; line-height:0;">&nbsp;</td></tr>
        </table>
      </td>
    </tr>

    <tr>
      <td class="mx-pad" style="padding:22px 32px 0;">
        <p class="mx-foot" style="margin:0 0 8px; font-family:{_F_UI}; font-size:12px; line-height:1.6; color:{_C_FOOT};">
          {_FOOTER_BRAND} · <a class="mx-link" href="{_SITE_URL}" style="color:{_C_MUTED}; text-decoration:underline;">{_SITE_LABEL}</a>
        </p>
        <p class="mx-foot" style="margin:0 0 8px; font-family:{_F_UI}; font-size:12px; line-height:1.6; color:{_C_FOOT};">
          {_esc(why_en)}<br />{_esc(why_zh)}
        </p>
        {unsub}
        <p class="mx-foot" style="margin:0; font-family:{_F_UI}; font-size:12px; line-height:1.6; color:{_C_FOOT};">
          Questions? Reply to this email, or write to
          <a class="mx-link" href="mailto:{_SUPPORT_ADDR}" style="color:{_C_MUTED}; text-decoration:underline;">{_SUPPORT_ADDR}</a>.<br />
          有问题？直接回复本邮件，或发送至 <a class="mx-link" href="mailto:{_SUPPORT_ADDR}" style="color:{_C_MUTED}; text-decoration:underline;">{_SUPPORT_ADDR}</a>。
        </p>
      </td>
    </tr>

  </table>

</td>
</tr>
</table>

</body>
</html>"""

    halves = [b for b in blocks if not b.get("once")]
    en_text = "\n\n".join(t for t in (_block_text(b, "en") for b in halves) if t)
    zh_text = "\n\n".join(t for t in (_block_text(b, "zh") for b in halves) if t)
    # The text part mirrors the HTML exactly, `once` included — a plain-text client must
    # not be the one place a 5000-char message is still pasted twice.
    shared_text = ""
    for b in blocks:
        if not b.get("once"):
            continue
        body = _block_text(b, "en") or _block_text(b, "zh")
        if not body:
            continue
        label = " · ".join(x for x in (b.get("label_en") or "", b.get("label_zh") or "") if x)
        shared_text += (f"{label}\n" if label else "") + body + "\n\n"
    unsub_text = f"\nUnsubscribe / 退订: {unsubscribe_url}\n" if unsubscribe_url else ""
    text = (
        f"{_BRAND}{(' · ' + eyebrow) if eyebrow else ''}\n\n"
        f"{title_en}\n\n{en_text}\n\n"
        f"{'-' * 46}\n\n"
        f"{title_zh}\n\n{zh_text}\n\n"
        f"{shared_text}"
        f"{'-' * 46}\n"
        f"{_FOOTER_BRAND} · {_SITE_LABEL}\n{why_en}\n{why_zh}\n{unsub_text}"
    )
    return html, text


# --------------------------------------------------------------------------- #
# Unsubscribe tokens
#
# HMAC-SHA256 over (ACTION, identity) with MAIL_UNSUB_SECRET, where the identity is a user
# id or a bare email address. The token CARRIES its identity so a one-click unsubscribe URL
# is self-contained — the W4 endpoint verifies and acts without a session. Ships + tested
# in W1; wired to a route in W4; action-scoped after the W4 review (see _token_payload).
# --------------------------------------------------------------------------- #
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


#: The actions a token may be minted FOR. The action is inside the MAC, so a token is a
#: capability for exactly one of them.
TOKEN_ACTIONS = ("unsubscribe", "resubscribe")


def _token_payload(identity: str, action: str) -> str:
    """What the MAC actually covers.

    THE ACTION IS BOUND INTO THE SIGNATURE. Before this, one token authorised both
    directions and the action was read from the query string, so
    ``POST /api/email/unsubscribe?t=<footer token>&action=resubscribe`` silently reversed
    someone's opt-out — and that token appears in every marketing footer and in the
    ``List-Unsubscribe`` header, i.e. anyone who can read one of the target's emails could
    put them back on the list. Revoking it meant rotating MAIL_UNSUB_SECRET and killing
    every link ever sent.

    ``unsubscribe`` covers the bare identity, unchanged, so every link already printed in a
    footer keeps working — stopping mail is the direction that is legally required to be
    one-click and must never be made harder. Every OTHER action is namespaced, so an
    unsubscribe token cannot satisfy the verification for one of them.
    """
    return identity if action == "unsubscribe" else f"{action}:{identity}"


def unsub_token(identity: str, action: str = "unsubscribe") -> str:
    """Signed, url-safe token authorising ONE ``action`` for ``identity``.

    Empty string when MAIL_UNSUB_SECRET is unset — fail-closed: no secret means no
    valid token can be minted, and verify_unsub_token rejects everything in turn. Also
    empty for an unknown action, and for an identity that is already shaped like a
    namespaced payload (``resubscribe:…``), which is the only way the two payload forms
    could be made to collide.
    """
    secret = _env("MAIL_UNSUB_SECRET")
    ident = (identity or "").strip()
    if not secret or not ident or action not in TOKEN_ACTIONS:
        return ""
    if any(ident.startswith(f"{a}:") for a in TOKEN_ACTIONS):
        return ""
    payload = _token_payload(ident, action)
    mac = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return f"{_b64e(ident.encode())}.{_b64e(mac)}"


def verify_unsub_token(t: str, action: str = "unsubscribe") -> str | None:
    """Return the identity a token attests to FOR ``action``, or None.

    Constant-time MAC comparison (hmac.compare_digest); any malformed input, any
    tampered payload, an unset secret, an unknown action, and a token minted for a
    DIFFERENT action all return None.
    """
    secret = _env("MAIL_UNSUB_SECRET")
    if not secret or not t or "." not in t or action not in TOKEN_ACTIONS:
        return None
    ident_b64, _, mac_b64 = t.partition(".")
    try:
        ident = _b64d(ident_b64).decode()
        given = _b64d(mac_b64)
    except Exception:  # noqa: BLE001
        return None
    payload = _token_payload(ident, action)
    expect = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expect, given):
        return None
    return ident
