"""tests/test_mailer.py — app/mailer.py (SEE W1 transport + send ledger).

Fully offline: no SMTP, no Supabase, no network. Two seams are stubbed —
``mailer._pg`` (the service-role PostgREST call, which serves BOTH the ledger writes and
the suppression/preference lookups) and ``mailer.smtplib`` (a fake module recording every
connection). Everything between them is the real code path.

Coverage maps to the mission's asks:
  - LEDGER-FIRST idempotency: a duplicate idem_key writes ONE ledger row and makes ZERO
    SMTP calls.
  - mail-off mode → 'skipped_no_smtp', ledger row patched, no connection attempted.
  - marketing is suppressed by address AND by the per-user opt-out.
  - transactional NEVER consults either.
  - List-Unsubscribe + One-Click headers ride marketing mail when a url is supplied,
    and never ride transactional mail.
  - unsubscribe token round-trip + tamper rejection.
  - render_email carries BOTH languages in html and text.
  - send() never raises: an exploding relay returns 'failed'.
"""
from __future__ import annotations

import sys
import urllib.parse
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mailer  # noqa: E402

IDEM = "ticket-notify:abc"
_MAIL_ENV = ("MAIL_SMTP_HOST", "MAIL_SMTP_PORT", "MAIL_SMTP_USER", "MAIL_SMTP_PASS",
             "MAIL_FROM", "MAIL_REPLY_TO", "MAIL_SUPPORT_TO", "MAIL_UNSUB_SECRET")


@pytest.fixture(autouse=True)
def _clean_mail_env(monkeypatch):
    """Start every test in mail-OFF mode with no operator-local values leaking in.

    The repo's <repo>/.env is loaded into os.environ by admin.paths whenever an admin
    module is imported in the same pytest session, so a developer who has real relay
    credentials on disk would otherwise change what these tests assert (the #3553
    operator-state-leak failure mode). Each test opts INTO the env it needs.
    """
    for k in _MAIL_ENV:
        monkeypatch.delenv(k, raising=False)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeSMTP:
    """Context-manager stand-in for smtplib.SMTP / SMTP_SSL. Records what it was asked."""

    def __init__(self, log, kind, host, port, timeout=None, context=None):
        self.log = log
        log.append({"kind": kind, "host": host, "port": port, "timeout": timeout,
                    "logins": [], "messages": []})
        self._rec = log[-1]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self._rec["ehlo"] = self._rec.get("ehlo", 0) + 1

    def starttls(self, context=None):
        self._rec["starttls"] = True

    def login(self, user, password):
        self._rec["logins"].append(user)

    def send_message(self, msg):
        self._rec["messages"].append(msg)


class _FakeSmtplib:
    """Minimal replacement for the smtplib module inside mailer._smtp_send.

    The exception tuples (_PERMANENT/_TRANSIENT) were bound at import time from the REAL
    module, so swapping this in never changes which failures are retried.
    """

    def __init__(self):
        self.connections: list[dict] = []

    def SMTP(self, host, port, timeout=None):  # noqa: N802 — mirrors the stdlib name
        return _FakeSMTP(self.connections, "starttls", host, port, timeout)

    def SMTP_SSL(self, host, port, timeout=None, context=None):  # noqa: N802
        return _FakeSMTP(self.connections, "ssl", host, port, timeout, context)


class _Ledger:
    """In-memory stand-in for the email_log / email_suppression / email_prefs tables."""

    def __init__(self, *, suppressed=None, opted_out=None):
        self.inserts: list[dict] = []
        self.patches: list[tuple[str, dict]] = []
        self.keys: set[str] = set()
        self.suppressed = {(e or "").lower(): r for e, r in (suppressed or {}).items()}
        self.opted_out = set(opted_out or [])
        self.lookups: list[str] = []
        self.lookup_outage = False

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        # mailer url-quotes every filter value (safe=''), so '@' and ':' arrive
        # percent-encoded. Decode before matching, exactly as PostgREST would.
        path = urllib.parse.unquote(path)
        if method == "POST" and path.startswith("email_log"):
            row = (body or [{}])[0]
            key = row.get("idem_key")
            if key in self.keys:
                raise mailer.DuplicateKey("duplicate key value violates unique constraint")
            self.keys.add(key)
            self.inserts.append(row)
            return None
        if method == "PATCH" and path.startswith("email_log"):
            self.patches.append((path, body or {}))
            return None
        if method == "GET" and path.startswith("email_suppression"):
            self.lookups.append(path)
            if self.lookup_outage:
                raise RuntimeError("supabase unreachable")
            addr = path.split("email=eq.", 1)[1].split("&", 1)[0]
            reason = self.suppressed.get(addr.lower())
            return [{"email": addr, "reason": reason}] if reason else []
        if method == "GET" and path.startswith("email_prefs"):
            self.lookups.append(path)
            if self.lookup_outage:
                raise RuntimeError("supabase unreachable")
            uid = path.split("user_id=eq.", 1)[1].split("&", 1)[0]
            return [{"marketing_opt_out": uid in self.opted_out}]
        raise AssertionError(f"unexpected PostgREST call {method} {path}")


@pytest.fixture
def wired(monkeypatch):
    """Stub both seams; return (ledger, fake_smtplib)."""
    led, smtp = _Ledger(), _FakeSmtplib()
    monkeypatch.setattr(mailer, "_pg", led.pg)
    monkeypatch.setattr(mailer, "smtplib", smtp)
    return led, smtp


def _mail_on(monkeypatch, port="587"):
    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.relay.test")
    monkeypatch.setenv("MAIL_SMTP_PORT", port)
    monkeypatch.setenv("MAIL_SMTP_USER", "relay-user")
    monkeypatch.setenv("MAIL_SMTP_PASS", "relay-pass")
    monkeypatch.setenv("MAIL_FROM", "Mastermind <hello@mastermind-x.com>")


def _send(**kw):
    args = {"template": "t", "cls": "transactional", "to_email": "user@example.com",
            "subject": "Subject", "html": "<p>hi</p>", "text": "hi", "idem_key": IDEM}
    args.update(kw)
    return mailer.send(**args)


def _patched_status(led, idem=IDEM):
    """The status the ledger row was moved to (last PATCH for this idem_key)."""
    for path, body in reversed(led.patches):
        if idem in urllib.parse.unquote(path):
            return body.get("status")
    return None


# ===========================================================================
# is_configured / mail-off
# ===========================================================================
def test_is_configured_requires_all_four(monkeypatch):
    assert mailer.is_configured() is False
    monkeypatch.setenv("MAIL_SMTP_HOST", "h")
    monkeypatch.setenv("MAIL_SMTP_USER", "u")
    monkeypatch.setenv("MAIL_SMTP_PASS", "p")
    assert mailer.is_configured() is False      # MAIL_FROM still missing → mail-off
    monkeypatch.setenv("MAIL_FROM", "f@x.com")
    assert mailer.is_configured() is True


def test_mail_off_skips_without_connecting(wired):
    led, smtp = wired
    assert _send() == "skipped_no_smtp"
    assert len(led.inserts) == 1 and led.inserts[0]["status"] == "queued"
    assert _patched_status(led) == "skipped_no_smtp"
    assert smtp.connections == []               # never dialled the relay


# ===========================================================================
# LEDGER-FIRST idempotency (SEE-R3) — the whole point of the module
# ===========================================================================
def test_duplicate_idem_key_writes_one_row_and_sends_once(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    assert _send() == "sent"
    assert _send() == "duplicate"
    assert _send() == "duplicate"
    assert len(led.inserts) == 1                      # ONE ledger row for three calls
    assert len(smtp.connections) == 1                 # ...and exactly one send
    assert len(smtp.connections[0]["messages"]) == 1


def test_duplicate_never_touches_smtp_at_all(wired, monkeypatch):
    """A replay must short-circuit BEFORE the transport, even with a live relay."""
    led, smtp = wired
    _mail_on(monkeypatch)
    led.keys.add(IDEM)                                # pretend a prior run claimed it
    assert _send() == "duplicate"
    assert smtp.connections == [] and led.inserts == []


def test_ledger_outage_still_sends_without_idempotency(wired, monkeypatch):
    """Degraded mode: no ledger → deliver anyway (a lost support reply beats a duplicate)."""
    led, smtp = wired
    _mail_on(monkeypatch)
    monkeypatch.setattr(mailer, "_pg", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no key")))
    assert _send() == "sent"
    assert len(smtp.connections) == 1


def test_missing_idem_key_is_refused(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    assert _send(idem_key="") == "failed"
    assert led.inserts == [] and smtp.connections == []


# ===========================================================================
# Class law — marketing is suppressible, transactional is not
# ===========================================================================
def test_marketing_suppressed_by_address(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    led.suppressed["user@example.com"] = "unsubscribe"
    assert _send(cls="marketing") == "suppressed"
    assert _patched_status(led) == "suppressed"
    assert led.patches[-1][1]["detail"] == "unsubscribe"
    assert smtp.connections == []


def test_marketing_suppressed_by_user_opt_out(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    led.opted_out.add("user-9")
    assert _send(cls="marketing", user_id="user-9") == "suppressed"
    assert led.patches[-1][1]["detail"] == "marketing_opt_out"
    assert smtp.connections == []


def test_marketing_sends_when_not_suppressed(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    assert _send(cls="marketing", user_id="user-1") == "sent"
    assert len(smtp.connections) == 1


def test_transactional_ignores_suppression_and_opt_out(wired, monkeypatch):
    """A user who opted out of marketing has NOT opted out of being answered."""
    led, smtp = wired
    _mail_on(monkeypatch)
    led.suppressed["user@example.com"] = "unsubscribe"
    led.opted_out.add("user-9")
    assert _send(cls="transactional", user_id="user-9") == "sent"
    assert len(smtp.connections) == 1
    assert led.lookups == []          # the suppression tables were never even queried


def test_unknown_class_falls_back_to_the_stricter_path(wired, monkeypatch):
    """A typo'd class must not become unsuppressable mail."""
    led, smtp = wired
    _mail_on(monkeypatch)
    led.suppressed["user@example.com"] = "bounce"
    assert _send(cls="transactionel") == "suppressed"
    assert led.inserts[0]["class"] == "marketing"
    assert smtp.connections == []


# ===========================================================================
# Headers / transport shape
# ===========================================================================
def test_marketing_carries_one_click_unsubscribe_headers(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    url = "https://mastermind-x.com/api/email/unsubscribe?t=tok"
    assert _send(cls="marketing", headers={"unsubscribe_url": url}) == "sent"
    msg = smtp.connections[0]["messages"][0]
    assert msg["List-Unsubscribe"] == f"<{url}>"
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


def test_transactional_never_carries_unsubscribe_headers(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    assert _send(cls="transactional",
                 headers={"unsubscribe_url": "https://x.test/u"}) == "sent"
    msg = smtp.connections[0]["messages"][0]
    assert msg["List-Unsubscribe"] is None


def test_message_shape_from_reply_to_and_alternative(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    monkeypatch.setenv("MAIL_REPLY_TO", "support@mastermind-x.com")
    assert _send() == "sent"
    msg = smtp.connections[0]["messages"][0]
    assert msg["From"] == "Mastermind <hello@mastermind-x.com>"
    assert msg["To"] == "user@example.com"
    assert msg["Reply-To"] == "support@mastermind-x.com"
    assert msg.is_multipart()
    subtypes = {p.get_content_subtype() for p in msg.iter_parts()}
    assert {"plain", "html"} <= subtypes


def test_port_587_is_starttls_and_465_is_implicit_tls(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch, port="587")
    _send()
    assert smtp.connections[0]["kind"] == "starttls" and smtp.connections[0]["starttls"] is True
    _mail_on(monkeypatch, port="465")
    _send(idem_key="second")
    assert smtp.connections[1]["kind"] == "ssl"


# ===========================================================================
# Fail-softness — send() never raises at its callers (G2/G7)
# ===========================================================================
def test_send_failure_returns_failed_and_records_class_only(wired, monkeypatch):
    led, _smtp = wired
    _mail_on(monkeypatch)

    def _boom(msg):
        raise ValueError("relay said no: secret-token-abc")

    monkeypatch.setattr(mailer, "_smtp_send", _boom)
    assert _send() == "failed"                       # no exception escaped
    detail = led.patches[-1][1]["detail"]
    assert detail == "ValueError"                    # class name only…
    assert "secret-token-abc" not in str(led.patches) # …never the message


def test_transient_disconnect_is_retried_once_then_succeeds(wired, monkeypatch):
    import smtplib as real_smtplib
    led, _smtp = wired
    _mail_on(monkeypatch)
    calls = {"n": 0}

    def _flaky(msg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise real_smtplib.SMTPServerDisconnected("dropped")

    monkeypatch.setattr(mailer, "_smtp_send", _flaky)
    assert _send() == "sent" and calls["n"] == 2


def test_auth_failure_is_not_retried(wired, monkeypatch):
    """SMTPException subclasses OSError — a bad password must NOT ride the transient retry."""
    import smtplib as real_smtplib
    led, _smtp = wired
    _mail_on(monkeypatch)
    calls = {"n": 0}

    def _bad_auth(msg):
        calls["n"] += 1
        raise real_smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(mailer, "_smtp_send", _bad_auth)
    assert _send() == "failed" and calls["n"] == 1


def test_missing_recipient_is_dropped_not_raised(wired):
    led, smtp = wired
    assert _send(to_email="  ") == "failed"
    assert led.inserts == [] and smtp.connections == []


# ===========================================================================
# render_email — both languages, always
# ===========================================================================
def test_render_email_carries_en_and_zh_in_html_and_text():
    html, text = mailer.render_email(
        "Your ticket", "您的工单",
        [
            {"en": "We got your message.", "zh": "我们已收到您的留言。"},
            {"kind": "kv", "en": [("Topic", "billing")], "zh": [("主题", "账单")]},
            {"kind": "quote", "en": "my card failed", "zh": "my card failed"},
            {"kind": "button", "en": "Open dashboard", "zh": "打开面板",
             "url": "https://mastermind-x.com/"},
        ],
    )
    for needle in ("Your ticket", "您的工单", "We got your message.", "我们已收到您的留言。",
                   "billing", "账单", "my card failed", "Open dashboard", "打开面板"):
        assert needle in html, needle
    assert "https://mastermind-x.com/" in html
    # The wordmark is TEXT (no logo image, PIN §6.2 rule 3) and the footer carries the
    # company line. Since W2 the site link inside that line is an anchor, so the brand
    # and the domain are asserted as the two parts they now are.
    assert "MASTERMIND" in html
    assert "Mastermind ·" in html and ">mastermind-x.com</a>" in html
    assert "Mastermind · mastermind-x.com" in text
    # plain-text alternative carries both languages too
    for needle in ("Your ticket", "您的工单", "We got your message.", "我们已收到您的留言。"):
        assert needle in text, needle


def test_render_email_escapes_untrusted_ticket_text():
    """A ticket body is stranger-written and lands in the operator's inbox."""
    html, _text = mailer.render_email(
        "T", "T", [{"kind": "quote", "en": "<script>alert(1)</script>", "zh": "x"}])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_render_email_skips_empty_blocks():
    html, text = mailer.render_email("T", "T", [{"en": "only english", "zh": ""}])
    assert "only english" in html and "only english" in text


# ===========================================================================
# Unsubscribe tokens
# ===========================================================================
def test_unsub_token_round_trip(monkeypatch):
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s3cr3t-unsub")
    for ident in ("user@example.com", "11111111-1111-1111-1111-111111111111"):
        tok = mailer.unsub_token(ident)
        assert tok and "." in tok
        assert mailer.verify_unsub_token(tok) == ident


def test_unsub_token_rejects_tampering(monkeypatch):
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s3cr3t-unsub")
    tok = mailer.unsub_token("victim@example.com")
    ident_b64, _, mac = tok.partition(".")
    forged = mailer._b64e(b"attacker@example.com") + "." + mac       # swapped identity
    assert mailer.verify_unsub_token(forged) is None
    assert mailer.verify_unsub_token(ident_b64 + ".AAAA") is None    # swapped mac
    assert mailer.verify_unsub_token(tok + "x") is None              # mutated tail
    assert mailer.verify_unsub_token("garbage") is None
    assert mailer.verify_unsub_token("") is None


def test_unsub_token_fails_closed_without_a_secret(monkeypatch):
    monkeypatch.delenv("MAIL_UNSUB_SECRET", raising=False)
    assert mailer.unsub_token("user@example.com") == ""
    assert mailer.verify_unsub_token("anything.here") is None


def test_unsub_token_is_secret_scoped(monkeypatch):
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "secret-a")
    tok = mailer.unsub_token("user@example.com")
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "secret-b")
    assert mailer.verify_unsub_token(tok) is None


def test_the_token_is_scoped_to_ONE_action(monkeypatch):
    """The action is inside the MAC, so a token is a capability for exactly one of them.

    One token used to authorise both directions with the action read from the query
    string, so the link in every marketing footer and every ``List-Unsubscribe`` header
    doubled as a re-subscribe capability: anyone who could read one of the target's emails
    could reverse their opt-out, and revoking it meant rotating MAIL_UNSUB_SECRET and
    killing every link ever sent."""
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s3cr3t-unsub")
    ident = "user@example.com"
    off = mailer.unsub_token(ident, "unsubscribe")
    on = mailer.unsub_token(ident, "resubscribe")

    assert off and on and off != on
    assert mailer.verify_unsub_token(off, "unsubscribe") == ident
    assert mailer.verify_unsub_token(on, "resubscribe") == ident
    assert mailer.verify_unsub_token(off, "resubscribe") is None, "the whole point"
    assert mailer.verify_unsub_token(on, "unsubscribe") is None


def test_the_unsubscribe_scope_is_the_bare_identity_so_printed_links_keep_working(monkeypatch):
    """Stopping mail is the direction that is legally required to be one-click, so it is
    the one whose wire format may not move: an ``unsubscribe`` token is the MAC over the
    identity alone, exactly as W1 shipped it."""
    import hashlib
    import hmac

    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s3cr3t-unsub")
    ident = "user@example.com"
    expect = hmac.new(b"s3cr3t-unsub", ident.encode(), hashlib.sha256).digest()
    assert mailer.unsub_token(ident) == f"{mailer._b64e(ident.encode())}.{mailer._b64e(expect)}"
    assert mailer.unsub_token(ident, "unsubscribe") == mailer.unsub_token(ident)


def test_an_unknown_action_mints_and_verifies_nothing(monkeypatch):
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s3cr3t-unsub")
    assert mailer.unsub_token("user@example.com", "delete-account") == ""
    tok = mailer.unsub_token("user@example.com")
    assert mailer.verify_unsub_token(tok, "delete-account") is None


def test_an_identity_shaped_like_a_scoped_payload_is_refused(monkeypatch):
    """The only way the two payload forms could be made to collide: an ``unsubscribe``
    token minted for the literal identity ``resubscribe:ada@example.com`` would carry the
    MAC a resubscribe token for ``ada@example.com`` needs. No real identity looks like
    that — an identity is a uuid or an address — so minting one is simply refused."""
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s3cr3t-unsub")
    assert mailer.unsub_token("resubscribe:ada@example.com") == ""
    assert mailer.unsub_token("unsubscribe:ada@example.com") == ""
    assert mailer.unsub_token("ada@example.com") != ""


# ===========================================================================
# B1 regression — header injection must never reach an email header
#
# A raw CR/LF in a Subject makes Python's email library raise on send. On this estate
# that is not one garbled message: the operator notification AND every future reply on
# that ticket (subject = "Re: <stored subject>") would fail forever. _build_message is
# the chokepoint, so the guarantee is asserted there and end-to-end through send().
# ===========================================================================
_DIRTY_SUBJECT = "Card declined\r\nBcc: attacker@evil.test\nX-Injected: yes"


def test_build_message_collapses_a_crlf_subject_to_one_line():
    msg = mailer._build_message(to_email="user@example.com", subject=_DIRTY_SUBJECT,
                                html="<p>x</p>", text="x", cls="transactional", headers=None)
    subject = msg["Subject"]
    assert "\n" not in subject and "\r" not in subject
    assert subject == "Card declined Bcc: attacker@evil.test X-Injected: yes"
    # the injected names are inert text inside Subject, not headers of their own
    assert msg["Bcc"] is None and msg["X-Injected"] is None


def test_send_succeeds_with_a_crlf_subject(wired, monkeypatch):
    """End-to-end: a dirty subject sends cleanly instead of raising forever."""
    led, smtp = wired
    _mail_on(monkeypatch)
    assert _send(subject=_DIRTY_SUBJECT) == "sent"
    msg = smtp.connections[0]["messages"][0]
    assert "\n" not in msg["Subject"] and msg["Bcc"] is None
    assert _patched_status(led) == "sent"


def test_header_injection_blocked_on_recipient_and_custom_headers(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    monkeypatch.setenv("MAIL_REPLY_TO", "support@x.test\r\nBcc: leak@evil.test")
    assert _send(headers={"X-Ticket": "abc\r\nBcc: leak2@evil.test"}) == "sent"
    msg = smtp.connections[0]["messages"][0]
    assert "\n" not in msg["Reply-To"] and "\n" not in msg["X-Ticket"]
    assert msg["Bcc"] is None


def test_header_safe_helper():
    assert mailer._header_safe("a\r\nb\tc   d") == "a b c d"
    assert mailer._header_safe(None) == ""
    assert len(mailer._header_safe("x" * 900)) == 400


# ===========================================================================
# M5 — marketing suppression is FAIL-CLOSED; transactional stays fail-open
# ===========================================================================
def test_marketing_parks_as_queued_when_the_suppression_lookup_fails(wired, monkeypatch):
    led, smtp = wired
    _mail_on(monkeypatch)
    led.lookup_outage = True
    assert _send(cls="marketing", user_id="user-1") == "queued"
    assert smtp.connections == []                       # NOTHING was sent
    assert _patched_status(led) == "queued"
    assert led.patches[-1][1]["detail"] == "suppression_lookup_failed"
    assert len(led.inserts) == 1                        # the row exists for the W4 drain


def test_transactional_sends_through_a_suppression_lookup_outage(wired, monkeypatch):
    """Transactional never consults those tables, so an outage cannot delay a reply."""
    led, smtp = wired
    _mail_on(monkeypatch)
    led.lookup_outage = True
    assert _send(cls="transactional", user_id="user-1") == "sent"
    assert len(smtp.connections) == 1
    assert led.lookups == []


def test_marketing_opt_out_lookup_outage_also_parks(wired, monkeypatch):
    """The second gate (per-user prefs) fails closed too, not just the address list."""
    led, smtp = wired
    _mail_on(monkeypatch)
    monkeypatch.setattr(mailer, "_pg", lambda method, path, **kw:
                        led.pg(method, path, **kw) if not path.startswith("email_prefs")
                        else (_ for _ in ()).throw(RuntimeError("prefs down")))
    assert _send(cls="marketing", user_id="user-1") == "queued"
    assert smtp.connections == []


# ===========================================================================
# Retry backoff (a 421 throttle needs a beat, not an instant second punch)
# ===========================================================================
def test_transient_retry_waits_before_the_second_attempt(wired, monkeypatch):
    import smtplib as real_smtplib
    led, _smtp = wired
    _mail_on(monkeypatch)
    slept: list[float] = []
    monkeypatch.setattr(mailer.time, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def _flaky(msg):
        calls["n"] += 1
        if calls["n"] == 1:
            raise real_smtplib.SMTPServerDisconnected("421 too many connections")

    monkeypatch.setattr(mailer, "_smtp_send", _flaky)
    assert _send() == "sent"
    assert slept == [mailer._RETRY_BACKOFF_SEC]


def test_permanent_failure_does_not_sleep(wired, monkeypatch):
    import smtplib as real_smtplib
    led, _smtp = wired
    _mail_on(monkeypatch)
    slept: list[float] = []
    monkeypatch.setattr(mailer.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(mailer, "_smtp_send",
                        lambda msg: (_ for _ in ()).throw(
                            real_smtplib.SMTPAuthenticationError(535, b"nope")))
    assert _send() == "failed"
    assert slept == []
