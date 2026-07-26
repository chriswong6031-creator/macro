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

W2 adds the submitter's acknowledgment and moves BOTH sends off the request path. The
route now takes a ``BackgroundTasks`` with no fallback, so ``_post`` supplies one and
drains it by hand; that is what lets the suite assert the ordering property M4 exists for
— at the moment the caller is told ``ok: true`` the row is stored and NOTHING has been
mailed yet.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from fastapi import BackgroundTasks, HTTPException

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


def _drain(bt: BackgroundTasks) -> int:
    """Run the queued background jobs the way Starlette would after the response.

    Every task this route queues is a plain sync callable, so no event loop is needed —
    and calling them by hand is what lets a test assert the ORDER: nothing has been mailed
    at the moment the caller gets `ok: true`, and both sends happen only afterwards.
    """
    tasks = list(getattr(bt, "tasks", []))
    for task in tasks:
        task.func(*task.args, **task.kwargs)
    return len(tasks)


def _post(body=None, request=None, authorization=None, bt=None, drain=True):
    """Call the route and, by default, run its background mail job.

    The route takes BackgroundTasks with no fallback (SEE W2 / M4: mail must never run on
    the request path), so a direct caller supplies one. Pass ``drain=False`` to inspect the
    queue before it runs.
    """
    bt = bt if bt is not None else BackgroundTasks()
    out = support.create_ticket(body or _body(), request or _FakeRequest(), bt,
                                authorization=authorization)
    if drain:
        _drain(bt)
    return out


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


def test_rate_limit_is_per_claimed_ip(wired, monkeypatch):
    store, _n = wired
    for i in range(support.RATE_LIMIT):
        _post(_body(subject=f"s{i}"))
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.77")
    assert _post(_body(subject="different visitor"))["ok"] is True


def test_oversized_declared_content_length_is_refused(wired):
    """The app-side cap only sees a DECLARED Content-Length.

    A chunked request declares none, so this check cannot be the real body cap — that is
    `request_body { max_size 64KB }` on /api/support/* in app/deploy/Caddyfile, enforced
    at the edge before the body is read. This asserts the cheap early refusal, nothing more.
    """
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
    # Two sends per ticket since W2: the operator alert and the submitter's ack.
    assert [s["template"] for s in sent] == ["ticket_operator_notify", "ticket_ack"]
    assert {s["cls"] for s in sent} == {"transactional"}
    assert sent[0]["idem_key"] == f"ticket-notify:{store.ticket_id}"
    assert sent[0]["to_email"] == "ops@mastermind-x.com"
    assert sent[1]["idem_key"] == f"ticket-ack:{store.ticket_id}"
    assert sent[1]["to_email"] == "ada@example.com"
    support._reset_rate_limiter()


def test_no_support_recipient_configured_still_acks_the_submitter(monkeypatch):
    """An unconfigured operator inbox is the operator's problem, not the customer's.

    MAIL_SUPPORT_TO unset skips the operator alert cleanly (W1 behaviour). The
    acknowledgment is addressed to the person who wrote in, so it is unaffected — the
    submitter must never lose their ticket number because ops has not set an env var.
    """
    store = _Store()
    monkeypatch.setattr(support, "_pg", store.pg)
    monkeypatch.setattr(support, "_client_ip", lambda request: "203.0.113.11")
    monkeypatch.setattr(support, "_resolve_user", lambda auth: None)
    support._reset_rate_limiter()
    from app import mailer
    monkeypatch.delenv("MAIL_SUPPORT_TO", raising=False)
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])
    assert _post()["ok"] is True
    assert [s["template"] for s in sent] == ["ticket_ack"]
    assert sent[0]["to_email"] == "ada@example.com"
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


# ===========================================================================
# B1 regression — a CRLF subject is collapsed BEFORE it can reach a header
# ===========================================================================
def test_subject_is_collapsed_to_one_line(wired):
    store, _n = wired
    _post(_body(subject="Card declined\r\nBcc: attacker@evil.test"))
    stored = store.tickets[0]["subject"]
    assert "\n" not in stored and "\r" not in stored
    assert stored == "Card declined Bcc: attacker@evil.test"


def test_subject_length_is_measured_after_collapsing(wired):
    """A subject that is only over-length because of padding whitespace is accepted."""
    store, _n = wired
    _post(_body(subject="  hello" + " " * 400 + "world  "))
    assert store.tickets[0]["subject"] == "hello world"


def test_whitespace_only_subject_is_still_rejected(wired):
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject="\r\n\t   "))
    assert ei.value.status_code == 400


# ===========================================================================
# M1 — dual-key rate limiting: the spoofable key is no longer the only key
# ===========================================================================
def _peer_req(peer="10.0.0.1"):
    return _FakeRequest({"X-MM-Peer": peer})


def test_spoofed_rotating_client_ip_is_still_caught_by_the_peer_key(wired, monkeypatch):
    """The attack the claimed key cannot stop: a bot rotating EO-Client-IP per request.

    Every hit lands in a fresh claimed bucket, so only the trusted peer key — which Caddy
    overwrites and a client cannot set — holds the line.
    """
    store, _n = wired
    seq = iter(f"198.51.100.{i}" for i in range(1, 500))
    monkeypatch.setattr(support, "_client_ip", lambda request: next(seq))
    for i in range(support.PEER_RATE_LIMIT):
        assert _post(_body(subject=f"s{i}"), request=_peer_req())["ok"] is True
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject="over"), request=_peer_req())
    assert ei.value.status_code == 429
    assert len(store.tickets) == support.PEER_RATE_LIMIT


def test_peer_key_is_per_peer(wired, monkeypatch):
    store, _n = wired
    seq = iter(f"198.51.100.{i}" for i in range(1, 500))
    monkeypatch.setattr(support, "_client_ip", lambda request: next(seq))
    for i in range(support.PEER_RATE_LIMIT):
        _post(_body(subject=f"s{i}"), request=_peer_req("10.0.0.1"))
    assert _post(_body(subject="other edge"), request=_peer_req("10.0.0.2"))["ok"] is True


def test_claimed_key_still_applies_when_a_peer_header_is_present(wired):
    """Both keys are live at once: the tight claimed limit still bites behind a peer."""
    store, _n = wired
    for i in range(support.RATE_LIMIT):
        assert _post(_body(subject=f"s{i}"), request=_peer_req())["ok"] is True
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject="sixth"), request=_peer_req())
    assert ei.value.status_code == 429


def test_no_peer_header_direct_dev_still_rate_limits_on_the_claimed_key(wired):
    """Local/dev with no Caddy in front must keep working — and keep limiting."""
    store, _n = wired
    for i in range(support.RATE_LIMIT):
        assert _post(_body(subject=f"s{i}"))["ok"] is True
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject="sixth"))
    assert ei.value.status_code == 429


def test_unknown_claimed_ip_no_longer_fail_opens(wired, monkeypatch):
    """'unknown' used to be a free pass; now it just means the peer key carries it."""
    store, _n = wired
    monkeypatch.setattr(support, "_client_ip", lambda request: "unknown")
    for i in range(support.PEER_RATE_LIMIT):
        assert _post(_body(subject=f"s{i}"), request=_peer_req())["ok"] is True
    with pytest.raises(HTTPException) as ei:
        _post(_body(subject="over"), request=_peer_req())
    assert ei.value.status_code == 429


def test_rate_limit_is_checked_before_the_honeypot(wired):
    """A bot tripping the honeypot must still burn quota, or the limit is free to dodge."""
    store, _n = wired
    for i in range(support.RATE_LIMIT):
        _post(_body(subject=f"s{i}", website="http://spam.test"))
    assert store.tickets == []                       # honeypot: nothing written…
    with pytest.raises(HTTPException) as ei:         # …but the budget was spent
        _post(_body(subject="real user now"))
    assert ei.value.status_code == 429


# ===========================================================================
# M2 — the rate map is bounded even inside a single window
# ===========================================================================
def test_rate_map_is_hard_capped_within_one_window(wired, monkeypatch):
    """The spray this bound exists for arrives in ONE window, so expiring stale windows
    frees nothing — the cap has to evict live keys."""
    support._reset_rate_limiter()
    for i in range(35_000):
        support._rate_ok(f"203.0.113.{i}", "")
    assert len(support._rate) <= support._RATE_MAX_KEYS
    support._reset_rate_limiter()


# ===========================================================================
# W2 / M4 — mail runs AFTER the response, and the ack reaches the submitter
#
# `create_ticket` is a sync def, so FastAPI runs it in the 40-slot anyio threadpool that
# every other sync route shares. With SMTP inline, one stalled relay costs a whole slot
# for the mailer's full retry budget, and 40 concurrent submissions to a route a stranger
# can call would stall the entire API. These tests pin the property that fixes it: at the
# moment the caller is told ok:true, NOTHING has been mailed yet.
# ===========================================================================
def test_mail_is_queued_not_sent_on_the_request_path(wired, monkeypatch):
    store, _n = wired
    from app import mailer
    monkeypatch.setattr(support, "_notify_operator", lambda **kw: "sent")
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])

    bt = BackgroundTasks()
    out = _post(bt=bt, drain=False)

    # the row exists…
    assert out["ok"] is True and len(store.tickets) == 1
    # …and not one byte has gone near a relay yet
    assert sent == []
    assert len(bt.tasks) == 1
    assert bt.tasks[0].func is support._send_ticket_mail

    _drain(bt)
    assert [s["template"] for s in sent] == ["ticket_ack"]


def test_route_requires_background_tasks_so_there_is_no_inline_mail_path():
    """A guard against the fallback returning: an optional BackgroundTasks would silently
    restore the inline-SMTP path this change exists to remove, and nothing else in the
    suite would notice. FastAPI injects the parameter off its annotation."""
    import inspect
    import typing
    # app/support.py carries `from __future__ import annotations`, so the raw annotation
    # is the STRING "BackgroundTasks" — resolve it the way FastAPI does before comparing.
    assert typing.get_type_hints(support.create_ticket)["background_tasks"] is BackgroundTasks
    param = inspect.signature(support.create_ticket).parameters["background_tasks"]
    assert param.default is inspect.Parameter.empty


def test_exploding_mail_job_never_touches_the_stored_ticket(wired, monkeypatch):
    """Persist-first: the mail job is downstream of the row, so it cannot unmake it —
    and a background task that raises would be logged and forgotten, so it must not."""
    store, _n = wired
    from app import mailer
    monkeypatch.setattr(support, "_notify_operator", lambda **kw: "sent")
    monkeypatch.setattr(mailer, "send",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("relay exploded")))
    bt = BackgroundTasks()
    out = _post(bt=bt, drain=False)
    assert out["ok"] is True and len(store.tickets) == 1
    _drain(bt)                                   # must not raise
    assert len(store.tickets) == 1 and len(store.messages) == 1


def test_ack_goes_to_the_submitter_with_the_pinned_contract(wired, monkeypatch):
    store, _n = wired
    from app import mailer
    monkeypatch.setattr(support, "_notify_operator", lambda **kw: "sent")
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])
    _post(_body(email="ada@example.com", topic="billing", message="my card failed\non the 3rd"))

    assert len(sent) == 1
    ack = sent[0]
    assert ack["template"] == "ticket_ack"
    assert ack["cls"] == "transactional"          # never suppressed by a marketing opt-out
    assert ack["idem_key"] == f"ticket-ack:{store.ticket_id}"
    assert ack["to_email"] == "ada@example.com"
    # PIN §7.7: the ref rides the subject in braces so replies thread and the operator
    # lane can match them back to the row.
    ref = support.ticket_ref(store.ticket_id)
    assert ack["subject"].startswith("{" + ref + "}")
    assert "We got your message" in ack["subject"] and "我们已收到你的消息" in ack["subject"]


def test_ack_body_carries_the_ref_topic_and_the_senders_own_words(wired, monkeypatch):
    """The four things §7.7 says the ack owes the reader: the number, the topic in words,
    their message back, and the reply-to-this-email instruction."""
    store, _n = wired
    from app import mailer
    monkeypatch.setattr(support, "_notify_operator", lambda **kw: "sent")
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])
    _post(_body(topic="billing", message="my card failed"))

    html, text = sent[0]["html"], sent[0]["text"]
    ref = support.ticket_ref(store.ticket_id)
    for needle in (ref, "Billing &amp; payments", "账单与付款", "my card failed",
                   "We got your message.", "我们已收到你的消息。", "Reply to this email"):
        assert needle in html, needle
    assert ref in text and "my card failed" in text
    # transactional class: the pinned base's unsubscribe slot stays unrendered
    assert "unsubscribe.html" not in html.lower()
    assert "SUPPORT" in html                      # the band eyebrow (PIN §7.7)


def test_ack_attaches_the_verified_user_id_when_signed_in(wired, monkeypatch):
    """email_log.user_id is what lets the Email Center attribute a send to an account."""
    store, _n = wired
    from app import mailer, billing
    monkeypatch.setattr(support, "_notify_operator", lambda **kw: "sent")
    monkeypatch.setattr(support, "_resolve_user",
                        lambda auth: {"id": UID, "email": "signed@example.com"})
    monkeypatch.setattr(billing, "read_entitlement", lambda uid: {"tier": "insider"})
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "send", lambda **kw: (sent.append(kw), "sent")[1])
    _post(_body(email="typed@example.com"), authorization="Bearer tok")

    assert sent[0]["to_email"] == "signed@example.com"   # verified identity wins
    assert sent[0]["user_id"] == UID


def test_ticket_ref_is_the_pinned_short_form():
    assert support.ticket_ref("7f3a2b91-1111-4000-8000-000000000001") == "MX-7F3A2B91"
    assert support.ticket_ref("") == ""
