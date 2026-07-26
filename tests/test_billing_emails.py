"""tests/test_billing_emails.py — app/billing_emails.py (SEE W3 billing + lifecycle mail).

Fully offline: no Stripe, no Supabase, no SMTP, no network. Four seams are stubbed and
everything between them is the real code path:

  ``mailer._pg``        the email_log ledger (and, for marketing, suppression — unused here)
  ``mailer.smtplib``    a fake module that records every connection and message
  ``billing._pg``       PostgREST for read_entitlement + the sweeper's candidate query
  ``billing._stripe``   the customer/subscription lookups behind recipient + price resolution

Coverage maps to the W3 acceptance gates:
  - G2 REPLAY: the identical webhook event fired twice writes ONE email_log row and makes
    ONE SMTP send — asserted at both the composer level and through billing._handle_event.
  - MAIL-OFF: with SMTP unconfigured every path ledgers 'skipped_no_smtp' and the webhook
    still returns 200.
  - Event -> template selection, including the checkout.session.completed ABSTENTION that
    keeps the two buy lanes from double-sending.
  - Tier-rank comparison reads config/plans.yml ordering (proven with a tier INSERTED into
    the middle of tier_rank).
  - Amounts/dates come off the objects: a non-USD, non-69.00, zero-decimal fixture renders
    correctly and no template contains a hardcoded price.
  - A composer that raises cannot break entitlement processing.
  - No resolvable address skips cleanly.
  - Both languages ship in every body.
  - Sweeper: window selection, per-period idem key, a second sweep sends nothing, a bad row
    does not abort the run.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import hmac
import json
import sys
import time
import types
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import billing, billing_emails as be, mailer  # noqa: E402

WHSEC = "whsec_test_secret_123"
_MAIL_ENV = ("MAIL_SMTP_HOST", "MAIL_SMTP_PORT", "MAIL_SMTP_USER", "MAIL_SMTP_PASS",
             "MAIL_FROM", "MAIL_REPLY_TO", "MAIL_SUPPORT_TO", "MAIL_UNSUB_SECRET",
             "MAIL_SITE_BASE", "MAIL_LIFECYCLE_ENABLED", "MAIL_LIFECYCLE_INTERVAL_SEC")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Every test starts mail-OFF with no operator-local values leaking in (#3553)."""
    for k in _MAIL_ENV:
        monkeypatch.delenv(k, raising=False)


def ep(y, m, d) -> int:
    return int(datetime(y, m, d, tzinfo=timezone.utc).timestamp())


def body_of(msg) -> str:
    """Decoded text/plain part of a sent message (EmailMessage encodes quoted-printable)."""
    part = msg.get_payload()[0] if msg.is_multipart() else msg
    return part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8")


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #
class _FakeSMTP:
    def __init__(self, log, host, port, timeout=None, context=None):
        log.append({"host": host, "port": port, "messages": []})
        self._rec = log[-1]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        pass

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        self._rec["messages"].append(msg)


class _FakeSmtplib:
    def __init__(self):
        self.connections: list[dict] = []

    def SMTP(self, host, port, timeout=None):  # noqa: N802 — mirrors the stdlib name
        return _FakeSMTP(self.connections, host, port, timeout)

    def SMTP_SSL(self, host, port, timeout=None, context=None):  # noqa: N802
        return _FakeSMTP(self.connections, host, port, timeout, context)

    @property
    def sent(self) -> list:
        return [m for c in self.connections for m in c["messages"]]


class _Ledger:
    """In-memory email_log with the real UNIQUE(idem_key) behaviour."""

    def __init__(self):
        self.inserts: list[dict] = []
        self.patches: list[tuple[str, dict]] = []
        self.keys: set[str] = set()

    def pg(self, method, path, body=None, prefer=None, timeout=6):
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
            key = path.split("idem_key=eq.", 1)[1]
            self.patches.append((key, body or {}))
            return None
        return []

    def status_of(self, idem_key: str) -> str | None:
        for k, patch in self.patches:
            if k == idem_key:
                return patch.get("status")
        return None


@pytest.fixture
def ledger(monkeypatch) -> _Ledger:
    led = _Ledger()
    monkeypatch.setattr(mailer, "_pg", led.pg)
    return led


@pytest.fixture
def smtp(monkeypatch) -> _FakeSmtplib:
    """Mail ON, through a fake relay."""
    fake = _FakeSmtplib()
    monkeypatch.setattr(mailer, "smtplib", fake)
    monkeypatch.setenv("MAIL_SMTP_HOST", "smtp.example.test")
    monkeypatch.setenv("MAIL_SMTP_USER", "relay-user")
    monkeypatch.setenv("MAIL_SMTP_PASS", "relay-pass")
    monkeypatch.setenv("MAIL_FROM", "Mastermind <no-reply@mastermind-x.com>")
    return fake


@pytest.fixture(autouse=True)
def _no_live_lookups(monkeypatch):
    """Recipient resolution never touches Stripe or Supabase unless a test says so."""
    monkeypatch.setattr(be, "_stripe_customer_email", lambda cid: "reader@example.com")
    monkeypatch.setattr(be, "_supabase_user_email", lambda uid: None)


# --------------------------------------------------------------------------- #
# Fixtures: Stripe objects, shaped exactly like webhook payloads (plain dicts)
# --------------------------------------------------------------------------- #
def sub_obj(*, status="trialing", lookup_key="insider_monthly", unit_amount=6900,
            currency="usd", cpe=None, **extra) -> dict:
    o = {
        "id": "sub_1", "object": "subscription", "customer": "cus_1", "status": status,
        "items": {"data": [{
            "id": "si_1",
            "price": {"lookup_key": lookup_key, "unit_amount": unit_amount,
                      "currency": currency,
                      "interval": "year" if lookup_key.endswith("annual") else "month"},
            "current_period_end": cpe if cpe is not None else ep(2026, 8, 1),
        }]},
        "metadata": {"mm_user_id": "user_1"},
    }
    o.update(extra)
    return o


def event(etype: str, obj: dict, event_id: str = "evt_1", created: int | None = None) -> dict:
    return {"id": event_id, "type": etype, "created": created or ep(2026, 7, 25),
            "data": {"object": obj}}


TRIAL_SUB = dict(status="trialing", trial_start=ep(2026, 7, 25), trial_end=ep(2026, 8, 1),
                 current_period_start=ep(2026, 7, 25))

ENT_INSIDER_TRIAL = {"tier": "insider", "status": "trialing", "plan_interval": "monthly",
                     "current_period_end": "2026-08-01T00:00:00+00:00",
                     "features": ["site_full", "terminal_live_options"]}
ENT_INSIDER = {"tier": "insider", "status": "active", "plan_interval": "monthly",
               "interval": "monthly", "current_period_end": "2026-08-14T00:00:00+00:00",
               "features": ["site_full", "terminal_live_options"]}
ENT_PRO = {"tier": "pro", "status": "active", "plan_interval": "monthly",
           "interval": "monthly", "current_period_end": "2026-08-14T00:00:00+00:00",
           "features": ["site_full", "terminal_live_options", "chat_opus"]}
ENT_FREE = {"tier": "free", "status": "none", "plan_interval": None, "interval": None,
            "current_period_end": None, "features": []}


# --------------------------------------------------------------------------- #
# 1. event -> template selection
# --------------------------------------------------------------------------- #
def test_event_template_selection():
    cases = [
        (event("customer.subscription.created", sub_obj(**TRIAL_SUB)), ENT_INSIDER_TRIAL, {},
         "billing_purchase"),
        (event("customer.subscription.updated", sub_obj(status="active", lookup_key="pro_monthly",
                                                        unit_amount=9900)),
         ENT_PRO, ENT_INSIDER, "billing_upgrade"),
        (event("invoice.payment_failed", {"object": "invoice", "customer": "cus_1",
                                          "amount_due": 9900, "currency": "usd",
                                          "created": ep(2026, 7, 26)}),
         ENT_FREE, ENT_PRO, "billing_payment_failed"),
        (event("customer.subscription.deleted",
               sub_obj(status="canceled", lookup_key="pro_annual", unit_amount=82800,
                       canceled_at=ep(2026, 7, 20), ended_at=ep(2026, 7, 26))),
         ENT_FREE, {}, "billing_cancellation"),
    ]
    for ev, ent, pre, expected in cases:
        spec = be.build_spec(ev, ent=ent, pre=pre)
        assert spec is not None, ev["type"]
        assert spec.template == expected, ev["type"]


def test_checkout_session_completed_sends_nothing():
    """The Elements lane never produces this event, and hosted Checkout also produces a
    customer.subscription.created — handling BOTH would double-send (different event ids,
    so the per-event idem key cannot dedupe them)."""
    ev = event("checkout.session.completed",
               {"object": "checkout.session", "customer": "cus_1",
                "client_reference_id": "user_1", "subscription": "sub_1"})
    assert be.build_spec(ev, ent=ENT_INSIDER_TRIAL, pre={}) is None


def test_unhandled_event_sends_nothing():
    assert be.build_spec(event("invoice.payment_succeeded", {"customer": "cus_1"}),
                         ent=ENT_INSIDER, pre={}) is None


def test_free_subscription_earns_no_receipt():
    """An unrecognised price resolves to no tier — do not mail a receipt for nothing."""
    ev = event("customer.subscription.created", sub_obj(lookup_key="legacy_unknown", **TRIAL_SUB))
    assert be.build_spec(ev, ent=ENT_FREE, pre={}) is None


# --------------------------------------------------------------------------- #
# 2. G2 — replay proof
# --------------------------------------------------------------------------- #
def test_replay_of_same_event_sends_exactly_once(ledger, smtp):
    """THE G2 GATE: the identical event twice -> one email_log row, one SMTP attempt."""
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), event_id="evt_replay")

    first = be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_INSIDER_TRIAL)
    second = be.on_event(copy.deepcopy(ev), user_id="user_1", customer_id="cus_1",
                         ent=ENT_INSIDER_TRIAL)

    assert first == "sent"
    assert second == "duplicate"
    assert len(ledger.inserts) == 1
    assert ledger.inserts[0]["idem_key"] == "stripe:evt_replay:billing_purchase"
    assert len(smtp.sent) == 1


def test_replay_through_handle_event_sends_once(ledger, smtp, monkeypatch):
    """Same proof one layer up: two passes through billing._handle_event, one email."""
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: dict(ENT_INSIDER_TRIAL))
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda u, c, e: None)
    monkeypatch.setattr(billing, "_invalidate", lambda u: None)
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), event_id="evt_hh")
    billing._handle_event(copy.deepcopy(ev))
    billing._handle_event(copy.deepcopy(ev))
    assert len(ledger.inserts) == 1
    assert len(smtp.sent) == 1


def test_idem_key_shape_is_per_event_and_template(ledger, smtp):
    ev = event("customer.subscription.deleted",
               sub_obj(status="canceled", ended_at=ep(2026, 7, 26)), event_id="evt_zz")
    be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_FREE)
    assert ledger.inserts[0]["idem_key"] == "stripe:evt_zz:billing_cancellation"
    assert ledger.inserts[0]["class"] == "transactional"


def test_missing_event_id_refuses_to_send(ledger, smtp):
    """No event id means no idempotency key — refusing beats a send that can repeat."""
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB))
    ev["id"] = ""
    assert be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_INSIDER_TRIAL) is None
    assert ledger.inserts == [] and smtp.sent == []


# --------------------------------------------------------------------------- #
# 3. mail-off mode
# --------------------------------------------------------------------------- #
def test_mail_off_ledgers_skipped_no_smtp(ledger):
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), event_id="evt_off")
    status = be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_INSIDER_TRIAL)
    assert status == "skipped_no_smtp"
    assert ledger.status_of("stripe:evt_off:billing_purchase") == "skipped_no_smtp"


def test_webhook_still_200_in_mail_off_mode(ledger, monkeypatch):
    """G2/G7: mail never decides the webhook's status code."""
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    monkeypatch.setattr(billing, "_event_seen", lambda eid: False)
    monkeypatch.setattr(billing, "_record_event", lambda eid, t: None)
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: dict(ENT_INSIDER_TRIAL))
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda u, c, e: None)
    monkeypatch.setattr(billing, "_invalidate", lambda u: None)

    payload = json.dumps(event("customer.subscription.created", sub_obj(**TRIAL_SUB),
                               event_id="evt_wh")).encode()
    ts = int(time.time())
    mac = hmac.new(WHSEC.encode(), f"{ts}.".encode() + payload, hashlib.sha256).hexdigest()

    class _Req:
        headers = {"stripe-signature": f"t={ts},v1={mac}"}

        async def body(self):
            return payload

    out = asyncio.run(billing.webhook(_Req()))
    assert out["status"] == "ok"
    assert ledger.status_of("stripe:evt_wh:billing_purchase") == "skipped_no_smtp"


# --------------------------------------------------------------------------- #
# 4. tier ordering comes from config/plans.yml
# --------------------------------------------------------------------------- #
@pytest.fixture
def catalog_with_new_tier(monkeypatch):
    """A catalog with 'starter' INSERTED between free and insider.

    Nothing in app/billing_emails.py knows this tier exists, so if the comparison still
    ranks correctly the ordering is genuinely coming from the config.
    """
    cat = {
        "currency": "usd",
        "features": [{"key": "site_full", "name": "Full site access"},
                     {"key": "chat_opus", "name": "Mastermind Pro chat (Opus)"}],
        "products": {
            "starter": {"tier": "starter", "name": "Starter", "trial_days": 7,
                        "features": ["site_full"],
                        "prices": {"monthly": {"lookup_key": "starter_monthly",
                                               "unit_amount": 2900, "interval": "month"},
                                   "annual": {"lookup_key": "starter_annual",
                                              "unit_amount": 29000, "interval": "year"}}},
            "insider": {"tier": "insider", "name": "Insider", "trial_days": 7,
                        "features": ["site_full"],
                        "prices": {"monthly": {"lookup_key": "insider_monthly",
                                               "unit_amount": 6900, "interval": "month"}}},
            "pro": {"tier": "pro", "name": "Pro", "trial_days": 7,
                    "features": ["site_full", "chat_opus"],
                    "prices": {"monthly": {"lookup_key": "pro_monthly",
                                           "unit_amount": 9900, "interval": "month"}}},
        },
        "tier_rank": ["free", "starter", "insider", "pro"],
    }
    monkeypatch.setattr(billing, "_CATALOG", cat)
    return cat


def test_upgrade_detection_uses_catalog_ordering(catalog_with_new_tier):
    up = {"tier": "insider", "plan_interval": "monthly"}
    assert be.is_upgrade({"tier": "starter", "interval": "monthly"}, up) is True
    assert be.is_upgrade({"tier": "pro", "interval": "monthly"}, up) is False
    assert be.is_upgrade({"tier": "insider", "interval": "monthly"}, up) is False
    # the inserted tier is a real rung, not a synonym for free
    assert be.is_upgrade({"tier": "free", "interval": None},
                         {"tier": "starter", "plan_interval": "monthly"}) is False


def test_upgrade_detection_interval_axis():
    """monthly -> annual on the same tier is an upgrade; annual -> monthly is not."""
    assert be.is_upgrade({"tier": "pro", "interval": "monthly"},
                         {"tier": "pro", "plan_interval": "annual"}) is True
    assert be.is_upgrade({"tier": "pro", "interval": "annual"},
                         {"tier": "pro", "plan_interval": "monthly"}) is False


def test_free_to_paid_is_a_purchase_not_an_upgrade():
    """Guards the out-of-order webhook: `updated` arriving before the `created` row exists
    must not add a second email on top of the receipt."""
    assert be.is_upgrade(ENT_FREE, ENT_PRO) is False
    ev = event("customer.subscription.updated", sub_obj(status="active", lookup_key="pro_monthly"))
    assert be.build_spec(ev, ent=ENT_PRO, pre=ENT_FREE) is None


def test_trial_to_active_conversion_sends_nothing():
    """The commonest subscription.updated of all — same plan, new status. Not an upgrade."""
    ev = event("customer.subscription.updated", sub_obj(status="active"))
    prev = dict(ENT_INSIDER_TRIAL, interval="monthly")
    assert be.build_spec(ev, ent=ENT_INSIDER, pre=prev) is None


def test_plan_names_come_from_the_catalog(catalog_with_new_tier):
    assert be.plan_name("starter") == "Starter"
    assert be.catalog_price("starter", "annual") == (29000, "usd")


# --------------------------------------------------------------------------- #
# 5. numbers are read off the objects — nothing hardcoded
# --------------------------------------------------------------------------- #
def test_money_formatting_handles_currency_and_scale():
    assert be.money_en(6900, "usd") == "US$69.00"
    assert be.money_en(74400, "eur") == "€744.00"
    assert be.money_zh(74400, "eur") == "744.00 欧元"
    # zero-decimal: Stripe already hands us the major unit
    assert be.money_en(9800, "jpy") == "¥9,800"
    assert be.money_zh(9800, "jpy") == "9,800 日元"
    # unmapped currency still renders honestly
    assert be.money_en(50000, "sek") == "500.00 SEK"


def test_non_usd_non_default_amount_renders_from_the_object():
    ev = event("customer.subscription.created",
               sub_obj(lookup_key="pro_annual", unit_amount=74400, currency="eur",
                       status="active", current_period_start=ep(2026, 7, 26),
                       cpe=ep(2027, 7, 26)))
    spec = be.build_spec(ev, ent=dict(ENT_PRO, plan_interval="annual"), pre={})
    _, html, text = be._render(spec)
    assert "€744.00" in text and "744.00 欧元" in text
    assert "69" not in text.replace("2026", "").replace("2027", "")   # no catalog default leaked
    assert "26 Jul 2027" in text and "2027 年 7 月 26 日" in text
    assert "€744.00" in html


def test_no_hardcoded_prices_in_the_module():
    """The catalog is the source of truth (MNZ-R12) — no literal price may live in code."""
    src = (Path(__file__).resolve().parent.parent / "app" / "billing_emails.py").read_text()
    for literal in ("6900", "9900", "58800", "82800", "$69", "$99", "US$69"):
        assert literal not in src, f"hardcoded price literal {literal!r} in app/billing_emails.py"


def test_dates_come_off_the_subscription_not_the_clock():
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), created=ep(2026, 7, 25))
    spec = be.build_spec(ev, ent=ENT_INSIDER_TRIAL, pre={})
    _, _, text = be._render(spec)
    assert "1 Aug 2026" in text                 # trial_end, off the object
    assert "1 Aug – 1 Sep 2026" in text         # the period the first charge covers
    assert "25 Jul 2026" in text                # event created


def test_add_interval_clamps_the_day_of_month():
    assert be.add_interval(datetime(2026, 1, 31, tzinfo=timezone.utc), "monthly").date().isoformat() \
        == "2026-02-28"
    assert be.add_interval(datetime(2024, 2, 29, tzinfo=timezone.utc), "annual").date().isoformat() \
        == "2025-02-28"


# --------------------------------------------------------------------------- #
# 6. dual language
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("ev, ent, pre", [
    (event("customer.subscription.created", sub_obj(**TRIAL_SUB)), ENT_INSIDER_TRIAL, {}),
    (event("customer.subscription.updated", sub_obj(status="active", lookup_key="pro_monthly",
                                                    unit_amount=9900)), ENT_PRO, ENT_INSIDER),
    (event("invoice.payment_failed", {"object": "invoice", "customer": "cus_1",
                                      "amount_due": 9900, "currency": "usd",
                                      "created": ep(2026, 7, 26),
                                      "next_payment_attempt": ep(2026, 7, 29)}),
     ENT_FREE, ENT_PRO),
    (event("customer.subscription.deleted",
           sub_obj(status="canceled", ended_at=ep(2026, 7, 26))), ENT_FREE, {}),
])
def test_every_body_ships_both_languages(ev, ent, pre):
    spec = be.build_spec(ev, ent=ent, pre=pre)
    subject, html, text = be._render(spec)
    assert " · " in subject
    for body in (html, text):
        assert any("一" <= ch <= "鿿" for ch in body), "no Chinese in the body"
        assert "Mastermind" in body
    # both halves carry the headline, so the reader finds their language in one scan
    assert spec.headline_en in text and spec.headline_zh in text
    assert spec.why_en and spec.why_zh
    assert spec.eyebrow and spec.preheader_en and spec.preheader_zh


def test_transactional_class_carries_no_unsubscribe(ledger, smtp):
    """PIN §6.7 — a receipt is owed information; an unsubscribe link on one would lie."""
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), event_id="evt_cls")
    be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_INSIDER_TRIAL)
    msg = smtp.sent[0]
    assert msg["List-Unsubscribe"] is None
    assert msg["List-Unsubscribe-Post"] is None


def test_cta_points_at_the_portal_handler():
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB))
    spec = be.build_spec(ev, ent=ENT_INSIDER_TRIAL, pre={})
    assert spec.cta_url == "https://www.mastermind-x.com/plans.html?billing=portal"


def test_cancellation_cta_points_at_plans():
    ev = event("customer.subscription.deleted",
               sub_obj(status="canceled", ended_at=ep(2026, 7, 26)))
    spec = be.build_spec(ev, ent=ENT_FREE, pre={})
    assert spec.cta_url == "https://www.mastermind-x.com/plans.html"


# --------------------------------------------------------------------------- #
# 7. fail-soft — G2/G7
# --------------------------------------------------------------------------- #
def test_composer_exception_never_raises(monkeypatch, ledger, smtp):
    def _boom(*a, **kw):
        raise ValueError("template bug")

    monkeypatch.setattr(be, "build_spec", _boom)
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), event_id="evt_boom")
    assert be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_INSIDER_TRIAL) is None
    assert ledger.inserts == [] and smtp.sent == []


def test_composer_exception_cannot_break_entitlement_processing(monkeypatch):
    """The DB write is the source of truth; mail is a side effect that must not block it."""
    def _boom(*a, **kw):
        raise RuntimeError("composer exploded")

    upserts, busted = [], []
    monkeypatch.setattr(be, "on_event", _boom)
    monkeypatch.setattr(be, "pre_upsert_snapshot", _boom)
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: dict(ENT_INSIDER_TRIAL))
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda u, c, e: upserts.append((u, c, e)))
    monkeypatch.setattr(billing, "_invalidate", lambda u: busted.append(u))

    billing._handle_event(event("customer.subscription.created", sub_obj(**TRIAL_SUB)))
    assert len(upserts) == 1 and upserts[0][0] == "user_1"
    assert busted == ["user_1"]          # cache bust still fired


def test_missing_email_module_does_not_break_the_webhook(monkeypatch):
    """The import boundary is guarded too — a module that will not import means no mail."""
    upserts = []
    monkeypatch.setattr(billing, "_billing_emails", lambda: None)
    monkeypatch.setattr(billing, "_compute_entitlement", lambda cid: dict(ENT_INSIDER_TRIAL))
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda u, c, e: upserts.append(u))
    monkeypatch.setattr(billing, "_invalidate", lambda u: None)
    billing._handle_event(event("customer.subscription.created", sub_obj(**TRIAL_SUB)))
    assert upserts == ["user_1"]


def test_no_resolvable_address_skips_cleanly(monkeypatch, ledger, smtp):
    monkeypatch.setattr(be, "_stripe_customer_email", lambda cid: None)
    monkeypatch.setattr(be, "_supabase_user_email", lambda uid: None)
    ev = event("customer.subscription.created", sub_obj(**TRIAL_SUB), event_id="evt_noaddr")
    assert be.on_event(ev, user_id="user_1", customer_id="cus_1", ent=ENT_INSIDER_TRIAL) is None
    assert ledger.inserts == [] and smtp.sent == []


def test_recipient_prefers_the_object_then_stripe_then_supabase(monkeypatch):
    monkeypatch.setattr(be, "_stripe_customer_email", lambda cid: "stripe@example.com")
    monkeypatch.setattr(be, "_supabase_user_email", lambda uid: "supabase@example.com")
    assert be.resolve_recipient({"customer_email": "invoice@example.com"}, "cus_1", "u1") \
        == "invoice@example.com"
    assert be.resolve_recipient({}, "cus_1", "u1") == "stripe@example.com"
    monkeypatch.setattr(be, "_stripe_customer_email", lambda cid: None)
    assert be.resolve_recipient({}, "cus_1", "u1") == "supabase@example.com"


def test_stripe_customer_lookup_failure_is_soft(monkeypatch):
    def _boom():
        raise RuntimeError("no stripe key")

    monkeypatch.setattr(billing, "_stripe", _boom)
    monkeypatch.undo()   # keep the autouse patch of _stripe_customer_email out of the way
    monkeypatch.setattr(billing, "_stripe", _boom)
    assert be._stripe_customer_email("cus_1") is None


# --------------------------------------------------------------------------- #
# 8. content honesty
# --------------------------------------------------------------------------- #
def test_payment_failed_says_paused_when_access_is_actually_gone():
    """`past_due` is unentitled in _entitlement_from_state, so the recomputed row already
    reads free. The email must not promise a grace window the product does not give."""
    ev = event("invoice.payment_failed",
               {"object": "invoice", "customer": "cus_1", "amount_due": 9900, "currency": "usd",
                "created": ep(2026, 7, 26), "next_payment_attempt": ep(2026, 7, 29)})
    spec = be.build_spec(ev, ent=ENT_FREE, pre=ENT_PRO)
    _, _, text = be._render(spec)
    assert "paused" in spec.lede_en
    assert "stays on until" not in spec.lede_en
    assert "US$99.00" in text                       # the invoice's own amount
    assert "29 Jul 2026" in text                    # next_payment_attempt, off the object
    assert "Pro" in text                            # tier survives on the pre-upsert row


def test_payment_failed_states_access_end_when_access_survives():
    ev = event("invoice.payment_failed",
               {"object": "invoice", "customer": "cus_1", "amount_due": 9900, "currency": "usd",
                "created": ep(2026, 7, 26)})
    spec = be.build_spec(ev, ent=ENT_PRO, pre=ENT_PRO)
    assert "stays on until 14 Aug 2026" in spec.lede_en
    assert "not try this card again" in spec.fine_en   # no next_payment_attempt on the object


def test_payment_failed_has_no_blame_or_urgency():
    ev = event("invoice.payment_failed",
               {"object": "invoice", "customer": "cus_1", "amount_due": 9900, "currency": "usd"})
    spec = be.build_spec(ev, ent=ENT_FREE, pre=ENT_PRO)
    blob = " ".join([spec.headline_en, spec.lede_en, spec.fine_en, spec.subject_en]).lower()
    assert "!" not in blob and "urgent" not in blob and "sorry" not in blob


def test_cancellation_reads_the_plan_off_the_deleted_subscription():
    """The recomputed row says free by now; the object still carries the price that ended."""
    ev = event("customer.subscription.deleted",
               sub_obj(status="canceled", lookup_key="pro_annual", unit_amount=82800,
                       canceled_at=ep(2026, 7, 20), ended_at=ep(2026, 7, 26)))
    spec = be.build_spec(ev, ent=ENT_FREE, pre={})
    _, _, text = be._render(spec)
    assert "Pro — annual" in text
    assert "20 Jul 2026" in text and "26 Jul 2026" in text
    assert "no" not in spec.headline_en.lower().split()       # no win-back plea
    assert "why" not in " ".join([spec.lede_en, spec.fine_en]).lower()


def test_cancellation_scheduled_for_the_future_says_you_keep_access():
    future = int((datetime.now(timezone.utc) + timedelta(days=20)).timestamp())
    ev = event("customer.subscription.deleted",
               sub_obj(status="canceled", cancel_at=future, canceled_at=ep(2026, 7, 20)),
               created=int(datetime.now(timezone.utc).timestamp()))
    spec = be.build_spec(ev, ent=ENT_FREE, pre={})
    assert "You keep" in spec.lede_en


def test_upgrade_names_the_capability_not_the_tier():
    ev = event("customer.subscription.updated",
               sub_obj(status="active", lookup_key="pro_monthly", unit_amount=9900))
    spec = be.build_spec(ev, ent=ENT_PRO, pre=ENT_INSIDER)
    assert "Mastermind Pro chat (Opus)" in spec.lede_en     # from config/plans.yml features
    assert "Opus" in spec.lede_zh


def test_upgrade_during_a_trial_states_no_charge():
    ev = event("customer.subscription.updated",
               sub_obj(status="trialing", lookup_key="pro_monthly", unit_amount=9900))
    spec = be.build_spec(ev, ent=dict(ENT_PRO, status="trialing"), pre=ENT_INSIDER)
    assert "Nothing was charged" in spec.fine_en


# --------------------------------------------------------------------------- #
# 9. trial-ending sweeper
# --------------------------------------------------------------------------- #
NOW = datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc)


class _EntStore:
    """Fake PostgREST for user_entitlements, recording the exact query it was asked."""

    def __init__(self, rows):
        self.rows = rows
        self.paths: list[str] = []

    def pg(self, method, path, body=None, prefer=None, timeout=6):
        self.paths.append(urllib.parse.unquote(path))
        return list(self.rows)


def _trial_row(user_id="user_1", cpe="2026-08-01T00:00:00+00:00", tier="insider",
               interval="monthly", cid="cus_1") -> dict:
    return {"user_id": user_id, "stripe_customer_id": cid, "tier": tier,
            "plan_interval": interval, "current_period_end": cpe}


@pytest.fixture
def sweeper(monkeypatch):
    """Catalog pricing only — no live Stripe reach-out during a sweep test."""
    monkeypatch.setattr(be, "_sweep_pricing", lambda cid, t, i: be.catalog_price(t, i))
    return None


def test_sweep_query_selects_only_trialing_inside_the_window(monkeypatch, ledger, smtp, sweeper):
    store = _EntStore([_trial_row()])
    monkeypatch.setattr(billing, "_pg", store.pg)
    be.sweep_trial_ending(now=NOW)
    path = store.paths[0]
    assert "status=eq.trialing" in path
    assert f"current_period_end=gte.{NOW.isoformat()}" in path
    assert f"current_period_end=lte.{(NOW + timedelta(hours=48)).isoformat()}" in path


def test_sweep_sends_the_reminder_with_catalog_pricing(monkeypatch, ledger, smtp, sweeper):
    monkeypatch.setattr(billing, "_pg", _EntStore([_trial_row()]).pg)
    out = be.sweep_trial_ending(now=NOW)
    assert out == {"scanned": 1, "sent": 1, "duplicate": 0, "skipped": 0, "failed": 0}
    assert ledger.inserts[0]["idem_key"] == "trial_ending:user_1:2026-08-01"
    assert ledger.inserts[0]["template"] == "trial_ending"
    body = body_of(smtp.sent[0])
    assert "US$69.00" in body and "69.00 美元" in body


def test_second_sweep_sends_nothing(monkeypatch, ledger, smtp, sweeper):
    monkeypatch.setattr(billing, "_pg", _EntStore([_trial_row()]).pg)
    be.sweep_trial_ending(now=NOW)
    out = be.sweep_trial_ending(now=NOW + timedelta(hours=6))
    assert out["sent"] == 0 and out["duplicate"] == 1
    assert len(ledger.inserts) == 1 and len(smtp.sent) == 1


def test_sweep_is_restart_safe_mid_run(monkeypatch, ledger, smtp, sweeper):
    """Cursor-free: a crash after the first row is sent leaves the rest to the next wake,
    and the already-sent row never goes out twice."""
    rows = [_trial_row("user_1", cid="cus_1"), _trial_row("user_2", cid="cus_2")]
    monkeypatch.setattr(billing, "_pg", _EntStore(rows).pg)

    real_send = mailer.send
    calls = {"n": 0}

    def _crash_after_first(**kw):
        calls["n"] += 1
        if calls["n"] == 2:
            raise RuntimeError("process died")
        return real_send(**kw)

    monkeypatch.setattr(mailer, "send", _crash_after_first)
    first = be.sweep_trial_ending(now=NOW)
    assert first["sent"] == 1 and first["failed"] == 1

    monkeypatch.setattr(mailer, "send", real_send)
    second = be.sweep_trial_ending(now=NOW)
    assert second["sent"] == 1 and second["duplicate"] == 1     # only the missing one goes
    assert len(smtp.sent) == 2
    assert {r["idem_key"] for r in ledger.inserts} == {
        "trial_ending:user_1:2026-08-01", "trial_ending:user_2:2026-08-01"}


def test_sweep_rearms_for_a_later_period(monkeypatch, ledger, smtp, sweeper):
    monkeypatch.setattr(billing, "_pg", _EntStore([_trial_row()]).pg)
    be.sweep_trial_ending(now=NOW)
    monkeypatch.setattr(billing, "_pg",
                        _EntStore([_trial_row(cpe="2026-09-01T00:00:00+00:00")]).pg)
    out = be.sweep_trial_ending(now=datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc))
    assert out["sent"] == 1
    assert {r["idem_key"] for r in ledger.inserts} == {
        "trial_ending:user_1:2026-08-01", "trial_ending:user_1:2026-09-01"}


def test_sweep_skips_a_row_with_no_address(monkeypatch, ledger, smtp, sweeper):
    monkeypatch.setattr(be, "_stripe_customer_email", lambda cid: None)
    monkeypatch.setattr(be, "_supabase_user_email", lambda uid: None)
    monkeypatch.setattr(billing, "_pg", _EntStore([_trial_row()]).pg)
    out = be.sweep_trial_ending(now=NOW)
    assert out["skipped"] == 1 and out["sent"] == 0 and ledger.inserts == []


def test_sweep_survives_a_query_failure(monkeypatch, ledger, smtp, sweeper):
    def _boom(*a, **kw):
        raise RuntimeError("postgrest down")

    monkeypatch.setattr(billing, "_pg", _boom)
    assert be.sweep_trial_ending(now=NOW)["failed"] == 1


def test_sweep_prefers_the_live_stripe_price(monkeypatch, ledger, smtp):
    """The live price is what the card is actually charged; the catalog is the fallback."""
    monkeypatch.setattr(billing, "_pg", _EntStore([_trial_row()]).pg)
    monkeypatch.setattr(billing, "_live_subscription",
                        lambda cid: sub_obj(unit_amount=4900, currency="gbp"))
    be.sweep_trial_ending(now=NOW)
    body = body_of(smtp.sent[0])
    assert "£49.00" in body


def test_sweep_falls_back_to_the_catalog_when_stripe_is_down(monkeypatch, ledger, smtp):
    def _boom(cid):
        raise RuntimeError("stripe down")

    monkeypatch.setattr(billing, "_pg", _EntStore([_trial_row()]).pg)
    monkeypatch.setattr(billing, "_live_subscription", _boom)
    be.sweep_trial_ending(now=NOW)
    body = body_of(smtp.sent[0])
    assert "US$69.00" in body


def test_trial_ending_wording_tracks_the_real_gap():
    spec = be.spec_trial_ending(tier="insider", interval="monthly",
                                period_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
                                amount=6900, currency="usd",
                                now=datetime(2026, 7, 30, 12, 0, tzinfo=timezone.utc))
    assert spec.subject_en == "Your trial ends in 2 days"
    one_day = be.spec_trial_ending(tier="insider", interval="monthly",
                                   period_end=datetime(2026, 8, 1, tzinfo=timezone.utc),
                                   amount=6900, currency="usd",
                                   now=datetime(2026, 7, 31, 12, 0, tzinfo=timezone.utc))
    assert one_day.subject_en == "Your trial ends tomorrow"


# --------------------------------------------------------------------------- #
# 10. lifecycle wiring
# --------------------------------------------------------------------------- #
def test_lifecycle_is_off_by_default():
    assert be.lifecycle_enabled() is False
    app = types.SimpleNamespace(add_event_handler=lambda *a: pytest.fail("must not arm"),
                                state=types.SimpleNamespace())
    assert be.register_lifecycle(app) is False


def test_lifecycle_arms_only_when_the_operator_sets_the_env(monkeypatch):
    monkeypatch.setenv("MAIL_LIFECYCLE_ENABLED", "1")
    handlers: list[str] = []
    app = types.SimpleNamespace(add_event_handler=lambda ev, fn: handlers.append(ev),
                                state=types.SimpleNamespace())
    assert be.register_lifecycle(app) is True
    assert handlers == ["startup", "shutdown"]


def test_pre_snapshot_only_for_events_that_need_it(monkeypatch):
    reads = []
    monkeypatch.setattr(billing, "read_entitlement", lambda uid: reads.append(uid) or ENT_PRO)
    assert be.pre_upsert_snapshot("customer.subscription.created", "user_1") is None
    assert be.pre_upsert_snapshot("invoice.payment_succeeded", "user_1") is None
    assert be.pre_upsert_snapshot("customer.subscription.updated", "user_1") == ENT_PRO
    assert be.pre_upsert_snapshot("invoice.payment_failed", "user_1") == ENT_PRO
    assert reads == ["user_1", "user_1"]
