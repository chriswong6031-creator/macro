"""tests/test_marketing_emails.py — app/marketing_emails.py (SEE W4, gates G4 + no-mass-mail).

Two things this suite exists to prove, and everything else is support:

**1. The welcome sweeper cannot mass-mail the existing user base.** "Every account with no
``welcome:{user_id}`` ledger row" is, on a first run, every account that has ever existed.
The idempotency key stops a second send; it does nothing about the first one going to ten
thousand people. So the bound is tested directly: unset activation floor ⇒ ZERO sends even
with every switch armed; a floor that is older than the lookback ceiling does not reopen
the backlog; and only accounts inside the window are offered to the mailer.

**2. G4 — a suppressed address and an opted-out user are both skipped by the campaign
drain, and transactional mail is unaffected.** These two tests deliberately run the REAL
``mailer.send`` against a faked PostgREST rather than a stubbed mailer: a fake that returns
``'suppressed'`` would prove only that the fake works. What is asserted is that the real
suppression path runs, that SMTP is never reached for those recipients, and that the
transactional class never even performs the lookup.

Fully offline. Three seams: ``mailer._pg`` (the ledger + suppression tables),
``mailer.smtplib`` (the relay), and ``marketing_emails._pg`` / ``_auth_page`` (entitlements,
campaigns and the GoTrue roster). No network, no database, no clock dependency — every
time-sensitive call takes an explicit ``now``.
"""
from __future__ import annotations

import sys
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import mailer, marketing_emails as me  # noqa: E402

NOW = datetime(2026, 7, 26, 12, 0, tzinfo=timezone.utc)
U1 = "11111111-1111-4111-8111-111111111111"
U2 = "22222222-2222-4222-8222-222222222222"
U3 = "33333333-3333-4333-8333-333333333333"

_MAIL_ENV = ("MAIL_SMTP_HOST", "MAIL_SMTP_PORT", "MAIL_SMTP_USER", "MAIL_SMTP_PASS",
             "MAIL_FROM", "MAIL_REPLY_TO", "MAIL_SUPPORT_TO", "MAIL_UNSUB_SECRET",
             "MAIL_UNSUB_MAILTO", "MAIL_SITE_BASE",
             "MAIL_MARKETING_ENABLED", "MAIL_WELCOME_ENABLED", "MAIL_CAMPAIGNS_ENABLED",
             "MAIL_WELCOME_AFTER", "MAIL_WELCOME_LOOKBACK_HOURS", "MAIL_THROTTLE_PER_MIN",
             "MAIL_MARKETING_INTERVAL_SEC")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts with mail OFF and every switch unset (the #3553 lesson).

    The repo's .env is loaded into os.environ whenever an admin module is imported in the
    same session, so an operator with real values on disk would otherwise change what
    these tests assert. Each test opts INTO the env it needs.
    """
    for k in _MAIL_ENV:
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setattr(mailer, "SUPABASE_SERVICE_ROLE_KEY", "svc-key")
    # the throttle must never make a test wait
    monkeypatch.setattr(me.time, "sleep", lambda *_a, **_k: None)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _Ledger:
    """In-memory email_log / email_suppression / email_prefs, for mailer._pg."""

    def __init__(self, *, suppressed=None, opted_out=None):
        self.rows: dict[str, dict] = {}
        self.suppressed = {(e or "").lower(): r for e, r in (suppressed or {}).items()}
        self.opted_out = set(opted_out or [])
        self.lookups: list[str] = []

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        path = urllib.parse.unquote(path)
        if method == "POST" and path.startswith("email_log"):
            row = (body or [{}])[0]
            key = row.get("idem_key")
            if key in self.rows:
                raise mailer.DuplicateKey("duplicate key value violates unique constraint")
            self.rows[key] = dict(row)
            return None
        if method == "PATCH" and path.startswith("email_log"):
            key = path.split("idem_key=eq.", 1)[1].split("&", 1)[0]
            self.rows.setdefault(key, {}).update(body or {})
            return None
        if method == "GET" and path.startswith("email_suppression"):
            self.lookups.append(path)
            addr = path.split("email=eq.", 1)[1].split("&", 1)[0]
            reason = self.suppressed.get(addr.lower())
            return [{"email": addr, "reason": reason}] if reason else []
        if method == "GET" and path.startswith("email_prefs"):
            self.lookups.append(path)
            uid = path.split("user_id=eq.", 1)[1].split("&", 1)[0]
            return [{"marketing_opt_out": uid in self.opted_out}]
        raise AssertionError(f"unexpected mailer PostgREST call {method} {path}")

    def status(self, key):
        return (self.rows.get(key) or {}).get("status")


class _Smtp:
    """Stand-in for the smtplib module; records every message actually transmitted."""

    class SMTPException(Exception):
        pass

    def __init__(self):
        self.sent: list = []
        outer = self

        class _Conn:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def ehlo(self):
                pass

            def starttls(self, **k):
                pass

            def login(self, *a):
                pass

            def send_message(self, msg):
                outer.sent.append(msg)

        self.SMTP = _Conn
        self.SMTP_SSL = _Conn
        # the real module's exception classes, needed by mailer's except clauses
        for name in ("SMTPAuthenticationError", "SMTPRecipientsRefused", "SMTPSenderRefused",
                     "SMTPDataError", "SMTPNotSupportedError", "SMTPServerDisconnected",
                     "SMTPConnectError"):
            setattr(self, name, type(name, (Exception,), {}))


class _Api:
    """marketing_emails._pg + _auth_page: the roster, entitlements and campaigns."""

    def __init__(self, users=None, ents=None, campaigns=None, log_keys=None):
        self.users = users if users is not None else []
        self.ents = ents or {}
        self.campaigns = {c["id"]: dict(c) for c in (campaigns or [])}
        self.log_keys = list(log_keys or [])
        self.patches: list[tuple[str, dict]] = []
        self.parked: list[dict] = []

    def auth_page(self, page, per_page=200):
        return self.users if page == 1 else []

    def pg(self, method, path, body=None, prefer=None, timeout=8):
        path = urllib.parse.unquote(path)
        if method == "GET" and path.startswith("user_entitlements"):
            return [{"user_id": uid, **v} for uid, v in self.ents.items()]
        if method == "GET" and path.startswith("email_log?select=idem_key"):
            return [{"idem_key": k} for k in self.log_keys]
        if method == "GET" and path.startswith("email_log?status=eq.queued"):
            return list(self.parked)
        if method == "GET" and path.startswith("email_campaigns?status=in."):
            return [c for c in self.campaigns.values() if c.get("status") in ("queued", "sending")]
        if method == "GET" and path.startswith("email_campaigns?id=eq."):
            cid = path.split("id=eq.", 1)[1].split("&", 1)[0]
            c = self.campaigns.get(cid)
            return [dict(c)] if c else []
        if method == "PATCH" and path.startswith("email_campaigns?id=eq."):
            cid = path.split("id=eq.", 1)[1].split("&", 1)[0]
            self.patches.append((cid, dict(body or {})))
            self.campaigns.setdefault(cid, {}).update(body or {})
            return None
        raise AssertionError(f"unexpected marketing PostgREST call {method} {path}")


def _user(uid, email, created):
    return {"id": uid, "email": email, "created_at": created.isoformat()}


@pytest.fixture
def wired(monkeypatch):
    """(ledger, smtp, api) with every seam replaced. Mail stays OFF unless a test arms it."""
    led, smtp, api = _Ledger(), _Smtp(), _Api()
    monkeypatch.setattr(mailer, "_pg", led.pg)
    monkeypatch.setattr(mailer, "smtplib", smtp)
    monkeypatch.setattr(me, "_pg", api.pg)
    monkeypatch.setattr(me, "_auth_page", api.auth_page)
    return led, smtp, api


def _mail_on(monkeypatch):
    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("MAIL_SMTP_USER", "u")
    monkeypatch.setenv("MAIL_SMTP_PASS", "p")
    monkeypatch.setenv("MAIL_FROM", "Mastermind <hello@example.com>")
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "unsub-secret")


def _arm(monkeypatch, **extra):
    monkeypatch.setenv("MAIL_MARKETING_ENABLED", "1")
    monkeypatch.setenv("MAIL_WELCOME_ENABLED", "1")
    monkeypatch.setenv("MAIL_CAMPAIGNS_ENABLED", "1")
    for k, v in extra.items():
        monkeypatch.setenv(k, v)


# ===========================================================================
# THE BLAST RADIUS — the welcome sweeper's bound
# ===========================================================================
def test_every_switch_defaults_off():
    assert me.marketing_enabled() is False
    assert me.welcome_enabled() is False
    assert me.campaigns_enabled() is False


def test_registering_the_sweeper_is_a_no_op_when_unarmed():
    """Merging this PR must not start a loop anywhere."""
    class _App:
        def __init__(self):
            self.handlers = []

        def add_event_handler(self, *a):
            self.handlers.append(a)

    app = _App()
    assert me.register_marketing(app) is False
    assert app.handlers == []


def test_no_activation_floor_means_no_candidates_at_all(monkeypatch, wired):
    """THE mass-mail guard. MAIL_WELCOME_AFTER unset is not "everyone" and not "since
    boot" — it is nobody. An operator who arms the feature without naming the day it went
    live sends zero email, which is the only outcome that cannot be regretted."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    api.users = [_user(U1, "a@example.com", NOW - timedelta(hours=1)),
                 _user(U2, "b@example.com", NOW - timedelta(days=400)),
                 _user(U3, "c@example.com", NOW - timedelta(minutes=5))]

    floor, _ = me.welcome_window(NOW)
    assert floor is None
    assert me.welcome_candidates(NOW) == []

    out = me.sweep_welcome(now=NOW)
    assert out["scanned"] == 0 and out["sent"] == 0
    assert led.rows == {}, "not one ledger row may be claimed"
    assert smtp.sent == [], "not one message may leave the building"


def test_an_unparseable_floor_is_treated_as_unset(monkeypatch):
    """A typo'd date must not silently become the epoch — which would be the mass-mail."""
    monkeypatch.setenv("MAIL_WELCOME_AFTER", "26/07/2026")
    assert me.welcome_window(NOW)[0] is None
    monkeypatch.setenv("MAIL_WELCOME_AFTER", "yesterday")
    assert me.welcome_window(NOW)[0] is None


def test_the_lookback_ceiling_beats_an_old_activation_floor(monkeypatch):
    """Even a correctly-set floor cannot reopen a year of backlog: the later of the two
    bounds wins, so a sweeper that was off for a year still only looks at the last 72h.
    A welcome email three months after signup is worse than none."""
    monkeypatch.setenv("MAIL_WELCOME_AFTER", "2020-01-01")
    floor, _ = me.welcome_window(NOW)
    assert floor == NOW - timedelta(hours=me.DEFAULT_LOOKBACK_HOURS)


def test_a_recent_activation_floor_beats_the_lookback(monkeypatch):
    """The other direction: arming it today does not reach back 72h into yesterday's
    signups, who never expected a welcome."""
    monkeypatch.setenv("MAIL_WELCOME_AFTER", (NOW - timedelta(hours=2)).isoformat())
    floor, _ = me.welcome_window(NOW)
    assert floor == NOW - timedelta(hours=2)


def test_the_lookback_is_configurable_and_clamped(monkeypatch):
    monkeypatch.setenv("MAIL_WELCOME_AFTER", "2020-01-01")
    monkeypatch.setenv("MAIL_WELCOME_LOOKBACK_HOURS", "6")
    assert me.welcome_window(NOW)[0] == NOW - timedelta(hours=6)
    monkeypatch.setenv("MAIL_WELCOME_LOOKBACK_HOURS", "99999")
    assert me.welcome_window(NOW)[0] == NOW - timedelta(hours=24 * 30)
    monkeypatch.setenv("MAIL_WELCOME_LOOKBACK_HOURS", "nonsense")
    assert me.welcome_window(NOW)[0] == NOW - timedelta(hours=me.DEFAULT_LOOKBACK_HOURS)


def test_only_accounts_inside_the_window_are_mailed(monkeypatch, wired):
    """Three accounts, one window: the old one and the pre-activation one are not
    candidates, and the mailer is never even offered them."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch, MAIL_WELCOME_AFTER=(NOW - timedelta(hours=6)).isoformat())
    api.users = [
        _user(U1, "old@example.com", NOW - timedelta(days=400)),      # long before the floor
        _user(U2, "edge@example.com", NOW - timedelta(hours=7)),      # just before the floor
        _user(U3, "new@example.com", NOW - timedelta(hours=1)),       # inside
    ]
    assert [c["user_id"] for c in me.welcome_candidates(NOW)] == [U3]

    out = me.sweep_welcome(now=NOW)
    assert out["scanned"] == 1 and out["sent"] == 1
    assert list(led.rows) == [f"welcome:{U3}"]
    assert len(smtp.sent) == 1
    assert smtp.sent[0]["To"] == "new@example.com"


def test_a_second_sweep_sends_nothing_more(monkeypatch, wired):
    """Cursor-free and idempotent: the ledger's unique idem_key is the only bookkeeping."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch, MAIL_WELCOME_AFTER=(NOW - timedelta(hours=6)).isoformat())
    api.users = [_user(U3, "new@example.com", NOW - timedelta(hours=1))]

    first = me.sweep_welcome(now=NOW)
    second = me.sweep_welcome(now=NOW)
    assert first["sent"] == 1 and second["sent"] == 0 and second["duplicate"] == 1
    assert len(smtp.sent) == 1


def test_candidates_are_capped_per_wake(monkeypatch, wired):
    led, smtp, api = wired
    _arm(monkeypatch, MAIL_WELCOME_AFTER=(NOW - timedelta(hours=6)).isoformat())
    api.users = [_user(f"{i:08d}-0000-4000-8000-000000000000", f"u{i}@example.com",
                       NOW - timedelta(minutes=i + 1))
                 for i in range(me._WELCOME_MAX_PER_WAKE + 40)]
    assert len(me.welcome_candidates(NOW)) == me._WELCOME_MAX_PER_WAKE


def test_the_roster_skips_banned_deleted_anonymous_and_addressless(monkeypatch, wired):
    """base_match is shared with the admin console's SQL — an account we may not mail is
    excluded before the window is even considered."""
    led, smtp, api = wired
    _arm(monkeypatch, MAIL_WELCOME_AFTER=(NOW - timedelta(hours=6)).isoformat())
    created = (NOW - timedelta(hours=1)).isoformat()
    api.users = [
        {"id": U1, "email": "ok@example.com", "created_at": created},
        {"id": U2, "email": "banned@example.com", "created_at": created,
         "banned_until": "2030-01-01T00:00:00Z"},
        {"id": U3, "email": "gone@example.com", "created_at": created,
         "deleted_at": "2026-01-01T00:00:00Z"},
        {"id": "44444444-4444-4444-8444-444444444444", "email": "", "created_at": created},
        {"id": "55555555-5555-4555-8555-555555555555", "email": "anon@example.com",
         "created_at": created, "is_anonymous": True},
    ]
    assert [c["user_id"] for c in me.welcome_candidates(NOW)] == [U1]


def test_welcome_is_marketing_class_and_carries_an_unsubscribe_url(monkeypatch, wired):
    """PIN §7.6: the welcome is marketing, so it is suppressible AND it must offer a way
    out — the one-click headers and the footer link both."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch, MAIL_WELCOME_AFTER=(NOW - timedelta(hours=6)).isoformat())
    api.users = [_user(U3, "new@example.com", NOW - timedelta(hours=1))]
    me.sweep_welcome(now=NOW)

    assert led.rows[f"welcome:{U3}"]["class"] == "marketing"
    msg = smtp.sent[0]
    assert msg["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "/api/email/unsubscribe?t=" in msg["List-Unsubscribe"]
    body = msg.get_payload()[1].get_payload(decode=True).decode()
    assert "/unsubscribe.html?t=" in body, "the human-facing footer link is the PAGE"


def test_the_header_url_is_the_api_and_the_footer_url_is_the_page(monkeypatch):
    """RFC 8058 one-click POSTs to the List-Unsubscribe URI. Pointing it at the static
    page would make Gmail's button post at a file and fail silently."""
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s")
    monkeypatch.setenv("MAIL_SITE_BASE", "https://www.example.com")
    assert me.unsub_page_url(U1).startswith("https://www.example.com/unsubscribe.html?t=")
    assert me.unsub_api_url(U1).startswith("https://www.example.com/api/email/unsubscribe?t=")
    assert me.unsub_page_url(U1) != me.unsub_api_url(U1)


def test_no_unsub_secret_means_no_url_rather_than_a_broken_one(monkeypatch):
    assert me.unsub_page_url(U1) == "" and me.unsub_api_url(U1) == ""


# ===========================================================================
# G4 — the compliance proof, through the REAL mailer
# ===========================================================================
def _campaign(segment="all"):
    return {"id": "c0000000-0000-4000-8000-000000000001",
            "subject": "What changed this week · 本周更新",
            "body_md": "One honest paragraph.\n\n===zh===\n\n一段实话。",
            "segment": segment, "status": "queued"}


@pytest.fixture
def drain_world(monkeypatch, wired):
    """Three recipients: clean, suppressed-by-address, opted-out-by-user."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    api.users = [_user(U1, "clean@example.com", NOW - timedelta(days=10)),
                 _user(U2, "suppressed@example.com", NOW - timedelta(days=10)),
                 _user(U3, "optedout@example.com", NOW - timedelta(days=10))]
    api.campaigns = {c["id"]: c for c in [_campaign()]}
    led.suppressed = {"suppressed@example.com": "unsubscribe"}
    led.opted_out = {U3}
    return led, smtp, api


def test_g4_campaign_drain_skips_a_suppressed_address_and_an_opted_out_user(drain_world):
    """The gate, proven end to end against the real suppression path.

    Not a stubbed mailer returning 'suppressed' — that would prove the stub works. The
    real mailer.send runs, reads the real (faked) tables, and the assertion is that SMTP
    was reached exactly once out of three."""
    led, smtp, api = drain_world
    out = me.drain_campaigns()

    assert out["sent"] == 1 and out["skipped"] == 2 and out["failed"] == 0
    assert len(smtp.sent) == 1, "only the clean recipient may be transmitted"
    assert smtp.sent[0]["To"] == "clean@example.com"

    cid = _campaign()["id"]
    assert led.status(f"campaign:{cid}:{U1}") == "sent"
    assert led.status(f"campaign:{cid}:{U2}") == "suppressed"
    assert led.status(f"campaign:{cid}:{U3}") == "suppressed"


def test_g4_the_campaign_counters_report_the_skips_honestly(drain_world):
    """A campaign that skips two thirds of its segment must say so — `sent_n` alone would
    read as a successful broadcast."""
    led, smtp, api = drain_world
    me.drain_campaigns()
    cid = _campaign()["id"]
    final = api.campaigns[cid]
    assert final["sent_n"] == 1 and final["skipped_n"] == 2 and final["failed_n"] == 0
    assert final["status"] == "done"


def test_g4_suppression_is_re_read_at_send_time_not_taken_from_the_segment(drain_world):
    """Membership is resolved once; the compliance decision is made per recipient, at the
    moment of sending. `marketing_eligible` is not pre-filtered on this plane precisely so
    that the mailer stays the only authority."""
    led, smtp, api = drain_world
    # the segment itself does not exclude anyone: all three are members
    assert len(me.segment_members("all")) == 3
    me.drain_campaigns()
    # ...and yet only one was transmitted, because the lookup happened at send time
    assert len(smtp.sent) == 1
    assert any("suppressed%40example.com" in p or "suppressed@example.com" in p
               for p in led.lookups)


def test_g4_transactional_mail_ignores_a_marketing_opt_out(monkeypatch, wired):
    """The other half of the class law: a user who opted out of marketing has NOT opted
    out of being answered about their own ticket or of getting their receipt. The
    transactional path must not even perform the lookup."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    led.opted_out = {U3}
    led.suppressed = {"optedout@example.com": "unsubscribe"}

    status = mailer.send(template="ticket_reply", cls="transactional",
                         to_email="optedout@example.com", subject="Re: your ticket",
                         html="<p>hi</p>", text="hi",
                         idem_key="ticket-reply:1:abc", user_id=U3)

    assert status == "sent"
    assert len(smtp.sent) == 1
    assert led.lookups == [], "transactional must never consult suppression or prefs"


def test_g4_the_same_person_is_blocked_on_the_marketing_class(monkeypatch, wired):
    """Same recipient, same tables, only the class differs — so the previous test cannot
    be passing because the fixture forgot to suppress anyone."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    led.opted_out = {U3}
    led.suppressed = {"optedout@example.com": "unsubscribe"}

    status = mailer.send(template="campaign", cls="marketing",
                         to_email="optedout@example.com", subject="news",
                         html="<p>hi</p>", text="hi",
                         idem_key="campaign:x:1", user_id=U3)

    assert status == "suppressed"
    assert smtp.sent == []


def test_an_unknown_class_is_coerced_to_the_stricter_one(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    led.suppressed = {"optedout@example.com": "unsubscribe"}
    status = mailer.send(template="oops", cls="promotional", to_email="optedout@example.com",
                         subject="s", html="", text="t", idem_key="k1")
    assert status == "suppressed"


# ===========================================================================
# Campaign mechanics
# ===========================================================================
def test_campaigns_default_off_so_merging_cannot_send(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    api.campaigns = {c["id"]: c for c in [_campaign()]}
    out = me.drain_campaigns()
    assert out == {"campaigns": 0, "sent": 0, "duplicate": 0, "skipped": 0, "failed": 0}
    assert smtp.sent == []


def test_the_master_switch_alone_does_not_arm_campaigns(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    monkeypatch.setenv("MAIL_MARKETING_ENABLED", "1")
    api.campaigns = {c["id"]: c for c in [_campaign()]}
    assert me.drain_campaigns()["campaigns"] == 0
    assert smtp.sent == []


def test_already_sent_recipients_are_not_re_offered_to_the_mailer(monkeypatch, wired):
    """Resuming a half-drained campaign costs one query, not one duplicate per head."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    cid = _campaign()["id"]
    api.users = [_user(U1, "a@example.com", NOW), _user(U2, "b@example.com", NOW)]
    api.campaigns = {cid: _campaign()}
    api.log_keys = [f"campaign:{cid}:{U1}"]
    me.drain_campaigns()
    assert [m["To"] for m in smtp.sent] == ["b@example.com"]


def test_an_aborted_campaign_keeps_its_status_after_the_drain(monkeypatch, wired):
    """The operator's decision outranks the drain's opinion that it finished."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    cid = _campaign()["id"]
    api.users = [_user(U1, "a@example.com", NOW)]
    api.campaigns = {cid: {**_campaign(), "status": "aborted"}}
    me._bump(cid, {"sent": 1, "skipped": 0, "failed": 0}, done=True)
    assert api.campaigns[cid]["status"] == "aborted"


def test_a_campaign_naming_an_unknown_segment_is_aborted_not_broadcast(monkeypatch, wired):
    """Failing open here would mean 'segment we cannot resolve' becoming 'everyone'."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    cid = _campaign()["id"]
    api.users = [_user(U1, "a@example.com", NOW)]
    api.campaigns = {cid: {**_campaign(), "segment": "everyone-ish"}}
    me.drain_campaigns()
    assert api.campaigns[cid]["status"] == "aborted"
    assert smtp.sent == []


def test_the_throttle_paces_the_drain(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch, MAIL_THROTTLE_PER_MIN="12")
    naps: list[float] = []
    monkeypatch.setattr(me.time, "sleep", lambda s: naps.append(s))
    cid = _campaign()["id"]
    api.users = [_user(U1, "a@example.com", NOW), _user(U2, "b@example.com", NOW)]
    api.campaigns = {cid: _campaign()}
    me.drain_campaigns()
    assert naps == [5.0, 5.0], "12 per minute is one every five seconds"


def test_the_throttle_is_clamped_to_something_sane(monkeypatch):
    monkeypatch.setenv("MAIL_THROTTLE_PER_MIN", "0")
    assert me.throttle_per_min() == 1
    monkeypatch.setenv("MAIL_THROTTLE_PER_MIN", "99999")
    assert me.throttle_per_min() == 600
    monkeypatch.setenv("MAIL_THROTTLE_PER_MIN", "junk")
    assert me.throttle_per_min() == me.DEFAULT_THROTTLE_PER_MIN


def test_campaign_body_splits_into_two_languages():
    en, zh = me.split_langs("Hello there.\n\n===zh===\n\n你好。")
    assert en == "Hello there." and zh == "你好。"


def test_a_single_language_body_is_used_for_both_halves():
    """A blank 中文 section reads as a broken email, so one language is mirrored."""
    en, zh = me.split_langs("Only English here.")
    assert en == zh == "Only English here."


def test_only_one_call_to_action_survives_the_composer():
    """PIN §7.9 allows at most one CTA — two primary buttons is a design failure the
    composer must not be able to ship."""
    blocks = me._blocks("intro\n\n[First](https://a.example)\n\n[Second](https://b.example)")
    buttons = [b for b in blocks if b["kind"] == "button"]
    assert len(buttons) == 1 and buttons[0]["url"] == "https://a.example"


def test_a_non_http_link_line_is_not_turned_into_a_button():
    blocks = me._blocks("[Click](javascript:alert(1))")
    assert [b["kind"] for b in blocks] == []


def test_campaign_subject_keeps_both_languages(monkeypatch, wired):
    monkeypatch.setenv("MAIL_UNSUB_SECRET", "s")
    subject, html, text = me.campaign_message(_campaign(), U1)
    assert subject == "What changed this week · 本周更新"
    assert "What changed this week" in html and "本周更新" in html


# ===========================================================================
# The parked-row drain (W3's documented contract)
# ===========================================================================
def _parked(idem_key, template, to_email, user_id):
    return {"idem_key": idem_key, "template": template, "class": "marketing",
            "to_email": to_email, "user_id": user_id}


def test_a_parked_row_for_a_now_suppressed_address_is_closed_not_sent(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    key = f"welcome:{U2}"
    led.rows[key] = {"idem_key": key, "status": "queued", "detail": "suppression_lookup_failed"}
    led.suppressed = {"b@example.com": "complaint"}
    api.parked = [_parked(key, "welcome", "b@example.com", U2)]

    out = me.drain_parked()
    assert out["suppressed"] == 1 and out["sent"] == 0
    assert led.rows[key]["status"] == "suppressed"
    assert led.rows[key]["detail"] == "complaint"
    assert smtp.sent == []


def test_a_parked_row_that_is_clear_is_completed_in_place(monkeypatch, wired):
    """The row is the work item. The message is rebuilt and handed to the transport, and
    THIS row is PATCHed — mailer.send is never called again with the same idem_key, which
    would hit the unique constraint and return 'duplicate' without sending anything."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    key = f"welcome:{U1}"
    led.rows[key] = {"idem_key": key, "status": "queued", "detail": "suppression_lookup_failed"}
    api.parked = [_parked(key, "welcome", "a@example.com", U1)]

    out = me.drain_parked()
    assert out["sent"] == 1
    assert led.rows[key]["status"] == "sent" and led.rows[key]["detail"] == "drained"
    assert len(smtp.sent) == 1 and smtp.sent[0]["To"] == "a@example.com"
    # exactly one ledger row still exists for this key — nothing was re-claimed
    assert list(led.rows) == [key]


def test_a_parked_row_with_no_rebuild_rule_is_left_alone(monkeypatch, wired):
    """email_log stores no body, so a template this module does not own cannot be
    reconstructed. Guessing at content nobody stored is worse than a row an operator has
    to look at."""
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    key = "some_future_template:9"
    led.rows[key] = {"idem_key": key, "status": "queued", "detail": "suppression_lookup_failed"}
    api.parked = [_parked(key, "some_future_template", "a@example.com", U1)]

    out = me.drain_parked()
    assert out["skipped"] == 1 and out["sent"] == 0
    assert led.rows[key]["status"] == "queued", "still parked, for a human to decide"
    assert smtp.sent == []


def test_a_parked_row_stays_parked_while_the_lookup_is_still_broken(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    _arm(monkeypatch)
    key = f"welcome:{U1}"
    led.rows[key] = {"idem_key": key, "status": "queued", "detail": "suppression_lookup_failed"}
    api.parked = [_parked(key, "welcome", "a@example.com", U1)]

    def _broken(method, path, **kw):
        if method == "GET" and path.startswith("email_suppression"):
            raise RuntimeError("supabase unreachable")
        return led.pg(method, path, **kw)

    monkeypatch.setattr(mailer, "_pg", _broken)
    out = me.drain_parked()
    assert out["skipped"] == 1 and out["sent"] == 0
    assert led.rows[key]["status"] == "queued"
    assert smtp.sent == []


def test_parked_drain_is_inert_when_marketing_is_off(monkeypatch, wired):
    led, smtp, api = wired
    _mail_on(monkeypatch)
    api.parked = [_parked("welcome:x", "welcome", "a@example.com", U1)]
    assert me.drain_parked()["scanned"] == 0


def test_mail_off_parks_a_drained_row_as_skipped_rather_than_sent(monkeypatch, wired):
    """With no relay the row still reaches a terminal state — it is never left claimed
    but unexplained."""
    led, smtp, api = wired
    _arm(monkeypatch)                      # note: no _mail_on
    key = f"welcome:{U1}"
    led.rows[key] = {"idem_key": key, "status": "queued", "detail": "suppression_lookup_failed"}
    api.parked = [_parked(key, "welcome", "a@example.com", U1)]
    me.drain_parked()
    assert led.rows[key]["status"] == "skipped_no_smtp"
    assert smtp.sent == []


# ===========================================================================
# Sweep ordering + the CLI
# ===========================================================================
def test_sweep_runs_all_three_legs(monkeypatch):
    order: list[str] = []
    monkeypatch.setattr(me, "drain_parked", lambda: order.append("parked") or {})
    monkeypatch.setattr(me, "sweep_welcome", lambda: order.append("welcome") or {})
    monkeypatch.setattr(me, "drain_campaigns", lambda: order.append("campaigns") or {})
    me.sweep()
    assert order == ["parked", "welcome", "campaigns"]


def test_the_window_cli_reports_the_bound_and_sends_nothing(monkeypatch, capsys, wired):
    import json

    _arm(monkeypatch, MAIL_WELCOME_AFTER="2026-07-25")
    assert me._main(["--window"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["armed"] is True and out["floor"].startswith("2026-07-")
    assert wired[1].sent == []
