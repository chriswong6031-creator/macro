"""tests/test_support_api.py — app/support.py (SEE W1 public ticket intake).

Fully offline. The route function is called directly with a fake Request (the
test_billing_webhook.py idiom) so nothing imports the heavy app.main module and no HTTP
client is needed. Three seams are stubbed:

  * ``support._pg``        — the service-role PostgREST insert (captures rows).
  * ``support._client_ip`` — app.main's EdgeOne-aware resolver (lazy-imported in prod).
  * ``support._resolve_user`` — app.main.require_user (the Bearer verification).

Coverage maps to the mission's asks: happy path signed-out; honeypot silent drop with NO
write; t0-too-fast 400; rate limit 429 on the 6th; topic/subject/message/email/lang
validation; the Bearer path overriding the body email and snapshotting tier; the operator
notification firing; and — the acceptance gate — the route never 500s when mail is off or
the mailer itself explodes.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import support  # noqa: E402

UID = "11111111-1111-1111-1111-111111111111"


class _FakeRequest:
    def __init__(self, headers: dict | None = None):
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}


class _Store:
    """In-memory stand-in for support_tickets / support_ticket_messages."""

    def __init__(self, ticket_id="7f000000-0000-4000-8000-000000000001"):
        self.tickets: list[dict] = []
        self.messages: list[dict] = []
        self.ticket_id = ticket_id
        self.fail_ticket_insert = False

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        if method == "POST" and path.startswith("support_tickets"):
            if self.fail_ticket_insert:
                raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY unset")
            row = dict((body or [{}])[0])
            row["id"] = self.ticket_id
            self.tickets.append(row)
            return [row]
        if method == "POST" and path.startswith("support_ticket_messages"):
            self.messages.append(dict((body or [{}])[0]))
            return None
        raise AssertionError(f"unexpected PostgREST call {method} {path}")


@pytest.fixture
def wired(monkeypatch):
    """Stub the three seams and reset the process-wide rate limiter.

    The limiter is module state shared across tests, so it is cleared here rather than
    left to leak a previous test's five bookings into the next one.
    """
    store = _Store()
    notifies: list[dict] = []
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.9")
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    monkeypatch.setattr(support, "_notify_operator",
                        lambda **kw: (notifies.append(kw), "sent")[1])
    support._reset_rate_limiter()
    yield store, notifies
    support._reset_rate_limiter()


def _body(**kw):
    args = {"email": "ada@example.com", "topic": "billing",
            "subject": "Card declined", "message": "My card was declined at checkout."}
    args.update(kw)
    return support.TicketRequest(**args)


def _post(body=None, request=None, authorization=None):
    return support.create_ticket(body or _body(), request or _FakeRequest(),
                                 authorization=authorization)


# ===========================================================================
# Happy path
# ===========================================================================
def test_happy_path_signed_out(wired):
    store, notifies = wired
    out = _post(_body(lang="zh"))
    assert out["ok"] is True and out["ticket_id"] == store.ticket_id

    assert len(store.tickets) == 1
    t = store.tickets[0]
    assert t["email"] == "ada@example.com" and t["topic"] == "billing"
    assert t["subject"] == "Card declined" and t["status"] == "open"
    assert t["lang"] == "zh"
    assert t["user_id"] is None and t["tier"] is None

    assert len(store.messages) == 1
    m = store.messages[0]
    assert m["ticket_id"] == store.ticket_id and m["author"] == "user"
    assert m["body"] == "My card was declined at checkout." and m["emailed"] is False

    assert len(notifies) == 1 and notifies[0]["ticket_id"] == store.ticket_id


def test_meta_stores_a_hash_never_the_raw_ip(wired, monkeypatch):
    store, _n = wired
    monkeypatch.setattr(support, "_client_ip", lambda request: "198.51.100.42")
    _post(request=_FakeRequest({"User-Agent": "Mozilla/5.0 (probe)"}))
    meta = store.tickets[0]["meta"]
    assert meta["ua"] == "Mozilla/5.0 (probe)"
    assert meta["ip_hash"] and len(meta["ip_hash"]) == 16
    assert "198.51.100.42" not in str(meta)
    assert meta["authed"] is False


def test_topic_and_lang_are_normalised(wired):
    store, _n = wired
    _post(_body(topic="  BILLING ", lang="EN"))
    assert store.tickets[0]["topic"] == "billing" and store.tickets[0]["lang"] == "en"


# ===========================================================================
# Abuse hardening
# ===========================================================================
def test_honeypot_is_a_silent_drop(wired):
    """A bot gets a well-formed 200 and nothing is written — a 400 would teach it."""
    store, notifies = wired
    out = _post(_body(website="http://spam.example"))
    assert out["ok"] is True and out["ticket_id"]
    assert store.tickets == [] and store.messages == [] and notifies == []


def test_empty_honeypot_is_fine(wired):
    store, _n = wired
    _post(_body(website=""))
    assert len(store.tickets) == 1


def test_t0_too_fast_is_rejected(wired):
    store, _n = wired
    now_ms = int(time.time() * 1000)
    with pytest.raises(HTTPException) as ei:
        _post(_body(t0=now_ms - 500))
    assert ei.value.status_code == 400
    assert store.tickets == []


def test_t0_slow_enough_passes(wired):
    store, _n = wired
    now_ms = int(time.time() * 1000)
    _post(_body(t0=now_ms - 30_000))
    assert len(store.tickets) == 1


def test_future_t0_is_treated_as_clock_skew_not_a_pass(wired):
    """A t0 ahead of the server clock is skew; it must not become a bot bypass or a 400."""
    store, _n = wired
    now_ms = int(time.time() * 1000)
    _post(_body(t0=now_ms + 60_000))
    assert len(store.tickets) == 1


def test_rate_limit_allows_five_then_429s(wired):
    store, _n = wired
    for i in range(support.RATE_LIMIT):
        assert _post(_body(subject=f"s{i}"))["ok"] is True
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject="sixth"))
    assert ei.value.status_code == 429
    assert len(store.tickets) == support.RATE_LIMIT


def test_rate_limit_is_per_ip(wired, monkeypatch):
    store, _n = wired
    for i in range(support.RATE_LIMIT):
        _post(_body(subject=f"s{i}"))
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.77")
    assert _post(_body(subject="different visitor"))["ok"] is True


def test_oversized_body_is_refused_before_any_work(wired):
    store, _n = wired
    req = _FakeRequest({"Content-Length": str(support.BODY_BYTES_MAX + 1)})
    with pytest.raises(HTTPException) as ei:
        _post(request=req)
    assert ei.value.status_code == 413
    assert store.tickets == []


# ===========================================================================
# Validation
# ===========================================================================
@pytest.mark.parametrize("topic", ["", "spam", "BILLING;drop", "support"])
def test_bad_topic_rejected(wired, topic):
    store, _n = wired
    with pytest.raises(HTTPException) as ei:
        _post(_body(topic=topic))
    assert ei.value.status_code == 400
    assert store.tickets == []


@pytest.mark.parametrize("subject", ["", "   ", "x" * (support.SUBJECT_MAX + 1)])
def test_bad_subject_rejected(wired, subject):
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject=subject))
    assert ei.value.status_code == 400


@pytest.mark.parametrize("message", ["", "  ", "x" * (support.MESSAGE_MAX + 1)])
def test_bad_message_rejected(wired, message):
    with pytest.raises(HTTPException) as ei:
        _post(_body(message=message))
    assert ei.value.status_code == 400


@pytest.mark.parametrize("email", ["", "nope", "a@b", "a b@c.com", "two@addr,x@y.com"])
def test_bad_email_rejected(wired, email):
    with pytest.raises(HTTPException) as ei:
        _post(_body(email=email))
    assert ei.value.status_code == 400


@pytest.mark.parametrize("email", ["ada+tag@example.co.uk", "a.b@sub.domain.io"])
def test_real_world_addresses_accepted(wired, email):
    store, _n = wired
    _post(_body(email=email))
    assert store.tickets[0]["email"] == email


def test_bad_lang_rejected(wired):
    with pytest.raises(HTTPException) as ei:
        _post(_body(lang="fr"))
    assert ei.value.status_code == 400


def test_max_length_boundaries_accepted(wired):
    store, _n = wired
    _post(_body(subject="s" * support.SUBJECT_MAX, message="m" * support.MESSAGE_MAX))
    assert len(store.tickets[0]["subject"]) == support.SUBJECT_MAX


# ===========================================================================
# Identity — a valid Bearer WINS
# ===========================================================================
def test_bearer_overrides_body_email_and_snapshots_tier(wired, monkeypatch):
    store, _n = wired
    monkeypatch.setattr(support, "_resolve_user",
                        lambda auth: {"id": UID, "email": "real@account.com"})
    from app import billing
    monkeypatch.setattr(billing, "read_entitlement",
                        lambda uid: {"tier": "pro", "features": [], "status": "active",
                                     "current_period_end": None, "source": "stripe",
                                     "interval": "annual"})
    out = _post(_body(email="spoofed@attacker.test"), authorization="Bearer good-token")
    assert out["ok"] is True
    t = store.tickets[0]
    assert t["email"] == "real@account.com"     # the CLAIMED address never wins
    assert t["user_id"] == UID and t["tier"] == "pro"
    assert t["meta"]["authed"] is True


def test_expired_bearer_files_as_signed_out_not_401(wired, monkeypatch):
    """A lapsed session must not throw away a support request the user just typed."""
    store, _n = wired
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    out = _post(_body(email="ada@example.com"), authorization="Bearer expired")
    assert out["ok"] is True
    assert store.tickets[0]["user_id"] is None
    assert store.tickets[0]["email"] == "ada@example.com"


def test_tier_snapshot_failure_is_not_fatal(wired, monkeypatch):
    store, _n = wired
    monkeypatch.setattr(support, "_resolve_user",
                        lambda auth: {"id": UID, "email": "real@account.com"})
    from app import billing
    monkeypatch.setattr(billing, "read_entitlement",
                        lambda uid: (_ for _ in ()).throw(RuntimeError("supabase down")))
    out = _post(authorization="Bearer good")
    assert out["ok"] is True and store.tickets[0]["tier"] is None


# ===========================================================================
# Mail-off safety — the route never 500s because of email (G2/G7)
# ===========================================================================
def test_route_succeeds_when_mail_is_off(monkeypatch):
    """No SMTP configured → the real mailer returns a status; the ticket still files."""
    store = _Store()
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    support._reset_rate_limiter()
    from app import mailer
    for k in ("MAIL_SMTP_HOST", "MAIL_SMTP_USER", "MAIL_SMTP_PASS", "MAIL_FROM"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("MAIL_SUPPORT_TO", "ops@mastermind-x.com")
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "skipped_no_smtp")[1])

    out = _post()
    assert out["ok"] is True and len(store.tickets) == 1
    assert len(sent) == 1
    assert sent[0]["template"] == "ticket_operator_notify"
    assert sent[0]["cls"] == "transactional"
    assert sent[0]["idem_key"] == f"ticket-notify:{store.ticket_id}"
    assert sent[0]["to_email"] == "ops@mastermind-x.com"
    support._reset_rate_limiter()


def test_no_support_recipient_configured_is_a_clean_skip(monkeypatch):
    store = _Store()
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.11")
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    support._reset_rate_limiter()
    from app import mailer
    monkeypatch.delenv("MAIL_SUPPORT_TO", raising=False)
    monkeypatch.setattr(mailer, "send", lambda **kw: pytest.fail("must not send with no recipient"))
    assert _post()["ok"] is True
    support._reset_rate_limiter()


def test_exploding_mailer_never_500s_the_ticket(monkeypatch):
    """The acceptance gate: mail failure is never the user's problem."""
    store = _Store()
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.12")
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    support._reset_rate_limiter()
    from app import mailer
    monkeypatch.setenv("MAIL_SUPPORT_TO", "ops@mastermind-x.com")
    monkeypatch.setattr(mailer, "send",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("relay exploded")))
    out = _post()
    assert out["ok"] is True and len(store.tickets) == 1
    support._reset_rate_limiter()


def test_notify_excerpt_is_capped(monkeypatch):
    store = _Store()
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.13")
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    support._reset_rate_limiter()
    from app import mailer
    monkeypatch.setenv("MAIL_SUPPORT_TO", "ops@mastermind-x.com")
    captured: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (captured.append(kw), "sent")[1])
    long_msg = "z" * 1000
    _post(_body(message=long_msg))
    text = captured[0]["text"]
    assert "z" * support.NOTIFY_EXCERPT in text
    assert "z" * (support.NOTIFY_EXCERPT + 1) not in text
    support._reset_rate_limiter()


# ===========================================================================
# Storage failures never leak internals
# ===========================================================================
def test_ticket_insert_failure_is_a_generic_503(wired):
    store, _n = wired
    store.fail_ticket_insert = True
    with pytest.raises(HTTPException) as ei:
        _post()
    assert ei.value.status_code == 503
    # the honest, non-leaking message — no table name, no key name, no stack
    assert "SUPABASE" not in str(ei.value.detail)
    assert ei.value.detail == "support intake is temporarily unavailable"
