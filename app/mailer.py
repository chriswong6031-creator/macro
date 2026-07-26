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
        msg["List-Unsubscribe"] = f"<{_header_safe(unsub_url, limit=1000)}>"
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
# Base template
#
# DELIBERATELY MINIMAL. This is the functional base so W1 can ship working mail; the
# W-D pinned design (mockups/support_email/) REPLACES it in W2. Do not grow features
# here — take the pinned markup instead. What it must be until then: clean, readable in
# every client (600px table, inline CSS, no external assets), bilingual, and honest about
# why the message arrived.
# --------------------------------------------------------------------------- #
_BRAND = "MASTERMIND"
_FOOTER_BRAND = "Mastermind · mastermind-x.com"
_WHY_EN = "You received this because you contacted Mastermind support or hold an account with us."
_WHY_ZH = "您收到此邮件，是因为您联系了 Mastermind 客服或拥有我们的账户。"

_BG = "#f4f5f7"
_CARD = "#ffffff"
_INK = "#14161a"
_MUTED = "#5b6270"
_RULE = "#e3e6eb"
_ACCENT = "#14161a"


def _esc(s: Any) -> str:
    return _html.escape(str(s if s is not None else ""), quote=True)


def _block_html(b: dict, lang: str) -> str:
    kind = (b.get("kind") or "p").lower()
    val = b.get(lang)
    if val in (None, "", []):
        return ""
    if kind == "kv":
        rows = "".join(
            f'<tr><td style="padding:3px 14px 3px 0;color:{_MUTED};font-size:13px;'
            f'white-space:nowrap">{_esc(k)}</td>'
            f'<td style="padding:3px 0;color:{_INK};font-size:13px">{_esc(v)}</td></tr>'
            for k, v in val
        )
        return f'<table role="presentation" cellpadding="0" cellspacing="0" style="margin:0 0 16px">{rows}</table>'
    if kind == "quote":
        return (f'<div style="margin:0 0 16px;padding:12px 14px;background:{_BG};'
                f'border-left:3px solid {_RULE};color:{_INK};font-size:14px;line-height:1.6;'
                f'white-space:pre-wrap">{_esc(val)}</div>')
    if kind == "button":
        url = b.get("url") or "#"
        return (f'<div style="margin:0 0 16px"><a href="{_esc(url)}" '
                f'style="display:inline-block;padding:10px 18px;background:{_ACCENT};color:#ffffff;'
                f'text-decoration:none;font-size:14px;font-weight:600;border-radius:4px">{_esc(val)}</a></div>')
    return f'<p style="margin:0 0 14px;color:{_INK};font-size:14px;line-height:1.65">{_esc(val)}</p>'


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
        return f"{val}: {b.get('url') or ''}"
    return str(val)


def render_email(title_en: str, title_zh: str, blocks: list[dict]) -> tuple[str, str]:
    """Render one dual-language message body. Returns ``(html, text)``.

    ``blocks`` is a list of dicts, each carrying an ``en`` and a ``zh`` value plus an
    optional ``kind``:

        {"en": "…", "zh": "…"}                          paragraph (default)
        {"kind": "quote",  "en": "…", "zh": "…"}        the user's own words, verbatim
        {"kind": "kv",     "en": [(k, v), …], "zh": […]} small label/value table
        {"kind": "button", "en": "…", "zh": "…", "url": "…"}

    Both languages ship in EVERY message, English first, then a divider, then 中文 —
    we do not guess which one the reader wants from a stored preference that may be
    stale or absent. Every value is HTML-escaped: a support ticket body is untrusted
    text written by a stranger, and it lands in the operator's inbox.
    """
    blocks = list(blocks or [])
    en_html = "".join(_block_html(b, "en") for b in blocks)
    zh_html = "".join(_block_html(b, "zh") for b in blocks)

    html = f"""<!-- W1 functional base — replaced by the W-D pinned design (mockups/support_email/) in W2 -->
<div style="margin:0;padding:0;background:{_BG}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};padding:28px 12px">
<tr><td align="center">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="width:100%;max-width:600px;background:{_CARD};border:1px solid {_RULE};border-radius:6px">
  <tr><td style="padding:22px 28px 0">
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;
                font-size:13px;font-weight:700;letter-spacing:.16em;color:{_INK}">{_BRAND}</div>
  </td></tr>
  <tr><td style="padding:18px 28px 0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
    <h1 style="margin:0 0 16px;font-size:19px;line-height:1.35;font-weight:700;color:{_INK}">{_esc(title_en)}</h1>
    {en_html}
  </td></tr>
  <tr><td style="padding:6px 28px 0">
    <div style="height:1px;background:{_RULE};margin:8px 0 20px"></div>
  </td></tr>
  <tr><td style="padding:0 28px 8px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
    <h2 style="margin:0 0 16px;font-size:17px;line-height:1.4;font-weight:700;color:{_INK}">{_esc(title_zh)}</h2>
    {zh_html}
  </td></tr>
  <tr><td style="padding:8px 28px 24px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif">
    <div style="height:1px;background:{_RULE};margin:0 0 14px"></div>
    <div style="color:{_MUTED};font-size:12px;line-height:1.6">{_FOOTER_BRAND}</div>
    <div style="color:{_MUTED};font-size:12px;line-height:1.6">{_esc(_WHY_EN)}</div>
    <div style="color:{_MUTED};font-size:12px;line-height:1.6">{_esc(_WHY_ZH)}</div>
  </td></tr>
</table>
</td></tr>
</table>
</div>"""

    en_text = "\n\n".join(t for t in (_block_text(b, "en") for b in blocks) if t)
    zh_text = "\n\n".join(t for t in (_block_text(b, "zh") for b in blocks) if t)
    text = (
        f"{_BRAND}\n\n"
        f"{title_en}\n\n{en_text}\n\n"
        f"{'-' * 46}\n\n"
        f"{title_zh}\n\n{zh_text}\n\n"
        f"{'-' * 46}\n"
        f"{_FOOTER_BRAND}\n{_WHY_EN}\n{_WHY_ZH}\n"
    )
    return html, text


# --------------------------------------------------------------------------- #
# Unsubscribe tokens
#
# HMAC-SHA256 over the identity (a user id or a bare email address) with
# MAIL_UNSUB_SECRET. The token CARRIES its identity so a one-click unsubscribe URL is
# self-contained — the W4 endpoint verifies and acts without a session. Ships + tested
# in W1; wired to a route in W4.
# --------------------------------------------------------------------------- #
def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def unsub_token(identity: str) -> str:
    """Signed, url-safe unsubscribe token for ``identity`` (user id or email).

    Empty string when MAIL_UNSUB_SECRET is unset — fail-closed: no secret means no
    valid token can be minted, and verify_unsub_token rejects everything in turn.
    """
    secret = _env("MAIL_UNSUB_SECRET")
    ident = (identity or "").strip()
    if not secret or not ident:
        return ""
    mac = hmac.new(secret.encode(), ident.encode(), hashlib.sha256).digest()
    return f"{_b64e(ident.encode())}.{_b64e(mac)}"


def verify_unsub_token(t: str) -> str | None:
    """Return the identity a token attests to, or None if it does not verify.

    Constant-time MAC comparison (hmac.compare_digest); any malformed input, any
    tampered payload, and an unset secret all return None.
    """
    secret = _env("MAIL_UNSUB_SECRET")
    if not secret or not t or "." not in t:
        return None
    ident_b64, _, mac_b64 = t.partition(".")
    try:
        ident = _b64d(ident_b64).decode()
        given = _b64d(mac_b64)
    except Exception:  # noqa: BLE001
        return None
    expect = hmac.new(secret.encode(), ident.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expect, given):
        return None
    return ident
