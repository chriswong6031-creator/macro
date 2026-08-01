"""Unit tests for app/billing.py — the Stripe billing spine (MNZ W2).

Fully offline: no network, no real Stripe, no Supabase. Stripe/PostgREST calls are
monkeypatched; the only "real" Stripe code exercised is the pure-crypto webhook
signature verification (stripe.Webhook.construct_event does no I/O).

Categories:
  1. Pure reducer (_entitlement_from_state) — tier precedence + negative path.
  2. Subscription field extraction (_sub_tier / _sub_period_end) incl. the
     API-version change that moved current_period_end to the item level.
  3. Live-state recompute (_compute_entitlement) against a fake Stripe.
  4. Webhook signature verification — good sig dispatches, bad sig -> 400.
  5. Idempotency — seen-event short-circuits; recompute is replay-stable.
  6. Negative propagation — subscription.deleted -> tier 'free', cache busted.

Run:
    python -m pytest tests/test_billing_webhook.py -v
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
import types

import pytest
from fastapi import HTTPException

from app import billing

WHSEC = "whsec_test_secret_123"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _price(lk):
    return types.SimpleNamespace(lookup_key=lk, metadata={})


def _item(lk, cpe=None):
    return types.SimpleNamespace(price=_price(lk), current_period_end=cpe)


def _sub(status, lk, cpe, top_cpe=None):
    return types.SimpleNamespace(
        status=status,
        current_period_end=top_cpe,
        items=types.SimpleNamespace(data=[_item(lk, cpe)]),
    )


class _ListResp:
    def __init__(self, data):
        self.data = data


def _fake_stripe(subs, ent_keys):
    ents = [types.SimpleNamespace(lookup_key=k) for k in ent_keys]
    return types.SimpleNamespace(
        Subscription=types.SimpleNamespace(list=lambda **kw: _ListResp(subs)),
        entitlements=types.SimpleNamespace(
            ActiveEntitlement=types.SimpleNamespace(list=lambda **kw: _ListResp(ents))
        ),
    )


class _FakeRequest:
    def __init__(self, body: bytes, headers: dict):
        self._body = body
        self.headers = headers

    async def body(self) -> bytes:
        return self._body


def _sign(payload: bytes, secret: str = WHSEC) -> str:
    ts = int(time.time())
    signed = f"{ts}.".encode() + payload
    mac = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return f"t={ts},v1={mac}"


def _event(etype: str, obj: dict, event_id: str = "evt_1") -> bytes:
    return json.dumps({"id": event_id, "type": etype, "data": {"object": obj}}).encode()


# --------------------------------------------------------------------------- #
# 1. pure reducer
# --------------------------------------------------------------------------- #
def test_reducer_picks_highest_active_tier():
    r = billing._entitlement_from_state(
        [
            {"status": "active", "current_period_end": 1900000000, "tier": "pro"},
            {"status": "active", "current_period_end": 1900000000, "tier": "essential"},
        ],
        [],
    )
    assert r["tier"] == "pro" and r["status"] == "active"
    # empty entitlement keys -> config fallback features for the tier
    assert "chat_opus" in r["features"]


def test_reducer_uses_entitlement_keys_when_present():
    r = billing._entitlement_from_state(
        [{"status": "trialing", "current_period_end": 1, "tier": "essential"}],
        ["site_full", "terminal_live_options"],
    )
    assert r["tier"] == "essential" and r["status"] == "trialing"
    assert r["features"] == ["site_full", "terminal_live_options"]


def test_reducer_no_active_sub_is_free():
    r = billing._entitlement_from_state(
        [{"status": "canceled", "current_period_end": 5, "tier": "pro"}], []
    )
    assert r["tier"] == "free" and r["features"] == [] and r["status"] == "canceled"


def test_reducer_empty_is_free_none():
    r = billing._entitlement_from_state([], [])
    assert r["tier"] == "free" and r["status"] == "none" and r["current_period_end"] is None


# --------------------------------------------------------------------------- #
# 2. subscription field extraction
# --------------------------------------------------------------------------- #
def test_sub_tier_from_lookup_key():
    assert billing._sub_tier(_sub("active", "pro_annual", 1)) == "pro"
    # a retired lookup_key still resolves, via the catalog's legacy_lookup_keys
    assert billing._sub_tier(_sub("active", "insider_monthly", 1)) == "essential"


def test_sub_period_end_prefers_item_level():
    # top-level absent (new API), item-level present -> item wins
    s = _sub("active", "pro_monthly", cpe=1755555555, top_cpe=None)
    assert billing._sub_period_end(s) == 1755555555
    # legacy top-level present -> used
    s2 = _sub("active", "pro_monthly", cpe=None, top_cpe=1700000000)
    assert billing._sub_period_end(s2) == 1700000000


# --------------------------------------------------------------------------- #
# 3. live-state recompute
# --------------------------------------------------------------------------- #
def test_compute_entitlement_active(monkeypatch):
    subs = [_sub("active", "pro_monthly", 1755555555)]
    monkeypatch.setattr(billing, "_stripe", lambda: _fake_stripe(subs, ["site_full", "chat_opus"]))
    ent = billing._compute_entitlement("cus_x")
    assert ent["tier"] == "pro" and ent["status"] == "active"
    assert ent["features"] == ["site_full", "chat_opus"]
    assert ent["current_period_end"].startswith("20")  # ISO


def test_compute_entitlement_canceled_is_free(monkeypatch):
    subs = [_sub("canceled", "pro_monthly", 1755555555)]
    monkeypatch.setattr(billing, "_stripe", lambda: _fake_stripe(subs, []))
    ent = billing._compute_entitlement("cus_x")
    assert ent["tier"] == "free" and ent["features"] == []


# --------------------------------------------------------------------------- #
# 4. webhook signature verification
# --------------------------------------------------------------------------- #
def test_webhook_good_signature_dispatches(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    seen = {}
    monkeypatch.setattr(billing, "_event_seen", lambda eid: False)
    monkeypatch.setattr(billing, "_record_event", lambda eid, t: seen.setdefault("recorded", (eid, t)))
    monkeypatch.setattr(billing, "_handle_event", lambda ev: seen.setdefault("handled", ev["id"]))

    payload = _event("customer.subscription.updated", {"customer": "cus_1"}, "evt_good")
    req = _FakeRequest(payload, {"stripe-signature": _sign(payload)})
    out = asyncio.run(billing.webhook(req))
    assert out["status"] == "ok" and out["id"] == "evt_good"
    assert seen["handled"] == "evt_good" and seen["recorded"][0] == "evt_good"


def test_webhook_bad_signature_400(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    monkeypatch.setattr(billing, "_handle_event", lambda ev: pytest.fail("must not dispatch on bad sig"))
    payload = _event("customer.subscription.updated", {"customer": "cus_1"})
    req = _FakeRequest(payload, {"stripe-signature": "t=1,v1=deadbeef"})
    with pytest.raises(HTTPException) as ei:
        asyncio.run(billing.webhook(req))
    assert ei.value.status_code == 400


def test_webhook_missing_secret_503(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    payload = _event("customer.subscription.updated", {"customer": "cus_1"})
    req = _FakeRequest(payload, {"stripe-signature": _sign(payload)})
    with pytest.raises(HTTPException) as ei:
        asyncio.run(billing.webhook(req))
    assert ei.value.status_code == 503


# --------------------------------------------------------------------------- #
# 5. idempotency
# --------------------------------------------------------------------------- #
def test_webhook_duplicate_short_circuits(monkeypatch):
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    monkeypatch.setattr(billing, "_event_seen", lambda eid: True)  # already processed
    monkeypatch.setattr(billing, "_handle_event", lambda ev: pytest.fail("duplicate must not re-dispatch"))
    payload = _event("customer.subscription.updated", {"customer": "cus_1"}, "evt_dup")
    req = _FakeRequest(payload, {"stripe-signature": _sign(payload)})
    out = asyncio.run(billing.webhook(req))
    assert out["status"] == "duplicate" and out["id"] == "evt_dup"


def test_handle_event_is_replay_stable(monkeypatch):
    """Processing the same event twice writes the identical entitlement (minus timestamp)."""
    upserts = []
    monkeypatch.setattr(billing, "_customer_id_for_event", lambda t, o: "cus_1")
    monkeypatch.setattr(billing, "_user_id_for_event", lambda t, o, c: "user_1")
    monkeypatch.setattr(
        billing, "_compute_entitlement",
        lambda cid: {"tier": "pro", "status": "active", "current_period_end": "2026-08-21T00:00:00+00:00",
                     "features": ["site_full", "chat_opus"]},
    )
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda uid, cid, ent: upserts.append((uid, cid, ent)))
    monkeypatch.setattr(billing, "_invalidate", lambda uid: None)

    ev = {"id": "evt_x", "type": "customer.subscription.updated", "data": {"object": {"customer": "cus_1"}}}
    billing._handle_event(ev)
    billing._handle_event(ev)
    assert len(upserts) == 2
    assert upserts[0] == upserts[1]  # same user, customer, entitlement — convergent


# --------------------------------------------------------------------------- #
# 6. negative propagation
# --------------------------------------------------------------------------- #
def test_subscription_deleted_downgrades_and_busts_cache(monkeypatch):
    captured = {}
    subs = [_sub("canceled", "pro_monthly", 1755555555)]
    monkeypatch.setattr(billing, "_stripe", lambda: _fake_stripe(subs, []))
    monkeypatch.setattr(billing, "_customer_id_for_event", lambda t, o: "cus_1")
    monkeypatch.setattr(billing, "_user_id_for_event", lambda t, o, c: "user_1")
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda uid, cid, ent: captured.update(ent=ent, uid=uid))
    monkeypatch.setattr(billing, "_invalidate", lambda uid: captured.update(invalidated=uid))

    ev = {"id": "evt_del", "type": "customer.subscription.deleted", "data": {"object": {"customer": "cus_1"}}}
    billing._handle_event(ev)
    assert captured["ent"]["tier"] == "free" and captured["ent"]["features"] == []
    assert captured["invalidated"] == "user_1"  # cache bust fired


# --------------------------------------------------------------------------- #
# 7. review remediation — chargeback, multi-item tier, out-of-order resolution
# --------------------------------------------------------------------------- #
def test_multi_item_sub_resolves_highest_tier():
    # M2: a sub carrying both an essential and a pro price resolves to pro, not item order.
    item = lambda lk: types.SimpleNamespace(price=types.SimpleNamespace(lookup_key=lk, metadata={}), current_period_end=1)
    sub = types.SimpleNamespace(status="active", current_period_end=None,
                                items=types.SimpleNamespace(data=[item("insider_monthly"), item("pro_monthly")]))
    assert billing._sub_tier(sub) == "pro"


def test_chargeback_cancels_subs_then_downgrades(monkeypatch):
    # C1: a dispute must cancel the live subs (so the free downgrade sticks) AND downgrade the row.
    calls = {}
    monkeypatch.setattr(billing, "_customer_id_for_event", lambda t, o: "cus_1")
    monkeypatch.setattr(billing, "_user_id_for_event", lambda t, o, c: "user_1")
    monkeypatch.setattr(billing, "_cancel_subscriptions", lambda cid: calls.__setitem__("canceled", cid))
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "free", "status": "canceled", "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda u, c, e: calls.__setitem__("ent", e))
    monkeypatch.setattr(billing, "_invalidate", lambda u: None)
    billing._handle_event({"id": "evt_disp", "type": "charge.dispute.created", "data": {"object": {"charge": "ch_1"}}})
    assert calls.get("canceled") == "cus_1"       # subs cancelled on chargeback
    assert calls["ent"]["tier"] == "free"         # ...and entitlement revoked


def test_subscription_created_before_checkout_resolves_via_metadata(monkeypatch):
    # H2: out-of-order — subscription.created arrives before checkout.session.completed, so no
    # persisted customer->user row exists yet; the mm_user_id we stamp on the sub must resolve it.
    monkeypatch.setattr(billing, "_user_for_customer", lambda cid: None)  # mapping row not written yet
    obj = {"customer": "cus_9", "metadata": {"mm_user_id": "user_9"}}
    assert billing._user_id_for_event("customer.subscription.created", obj, "cus_9") == "user_9"


def test_unresolved_subscription_event_without_metadata_or_row_is_dropped(monkeypatch):
    # H2 corollary: no metadata AND no mapping row → unresolved → None (event is skipped, not misapplied).
    monkeypatch.setattr(billing, "_user_for_customer", lambda cid: None)
    assert billing._user_id_for_event("customer.subscription.updated", {"customer": "cus_x"}, "cus_x") is None


# --------------------------------------------------------------------------- #
# 8. SEE W3 — the handler must not block the event loop, and one user's events
#    must not interleave now that they can run concurrently.
# --------------------------------------------------------------------------- #
def test_webhook_runs_the_handler_off_the_event_loop(monkeypatch):
    """_handle_event is fully blocking (Supabase + Stripe + SMTP). Left inline in the
    async route it stalls EVERY other request on this single-process API, so it has to
    take the threadpool hop."""
    import threading

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_dummy")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", WHSEC)
    monkeypatch.setattr(billing, "_event_seen", lambda eid: False)
    monkeypatch.setattr(billing, "_record_event", lambda eid, t: None)

    seen = {}

    def _slow(ev):
        seen["thread"] = threading.current_thread().name

    monkeypatch.setattr(billing, "_handle_event", _slow)

    async def _drive():
        seen["loop_thread"] = threading.current_thread().name
        payload = _event("customer.subscription.updated", {"customer": "cus_1"}, "evt_tp")
        req = _FakeRequest(payload, {"stripe-signature": _sign(payload)})
        return await billing.webhook(req)

    out = asyncio.run(_drive())
    assert out["status"] == "ok"
    assert seen["thread"] != seen["loop_thread"], "_handle_event ran ON the event loop"


def test_concurrent_events_for_one_user_do_not_interleave(monkeypatch):
    """The email hook compares the entitlement before the upsert with the one after, so
    two events for the SAME user must be serialised — otherwise both read the same
    'before' and both can decide an upgrade happened. Guards the threadpool change."""
    import threading

    order: list[str] = []
    barrier_hit = threading.Event()

    def _snapshot(etype, uid):
        order.append(f"snap-{threading.current_thread().name}")
        barrier_hit.set()
        time.sleep(0.05)          # a window wide enough for the other thread to race in
        return {"tier": "essential"}

    def _upsert(uid, cid, ent):
        order.append(f"write-{threading.current_thread().name}")

    fake_emails = types.SimpleNamespace(
        pre_upsert_snapshot=_snapshot,
        on_event=lambda *a, **kw: None,
    )
    monkeypatch.setattr(billing, "_billing_emails", lambda: fake_emails)
    monkeypatch.setattr(billing, "_customer_id_for_event", lambda t, o: "cus_1")
    monkeypatch.setattr(billing, "_user_id_for_event", lambda t, o, c: "user_same")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "active",
                                     "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", _upsert)
    monkeypatch.setattr(billing, "_invalidate", lambda uid: None)

    ev = {"id": "evt_race", "type": "customer.subscription.updated",
          "data": {"object": {"customer": "cus_1"}}}
    threads = [threading.Thread(target=billing._handle_event, args=(dict(ev),), name=f"w{i}")
               for i in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    # Each snapshot must be followed by ITS OWN write before the other thread snapshots.
    assert len(order) == 4, order
    assert order[0].startswith("snap-") and order[1].startswith("write-")
    assert order[0].split("-")[1] == order[1].split("-")[1], f"interleaved: {order}"
    assert order[2].split("-")[1] == order[3].split("-")[1], f"interleaved: {order}"


def test_different_users_are_not_serialised_against_each_other(monkeypatch):
    """The lock is per user — one customer's slow SMTP must not queue everyone else's."""
    assert billing._user_lock("a") is billing._user_lock("a")
    assert billing._user_lock("a") is not billing._user_lock("b")


def test_the_send_happens_outside_the_per_user_lock(monkeypatch):
    """N2 — the lock covers the DECISION, not the SMTP conversation.

    mailer.send is ledger-first on a UNIQUE idem_key, so delivery needs no serialisation;
    holding the lock across it would make the second of two events that arrive together
    (invoice.payment_failed + customer.subscription.updated on a failed renewal) wait out
    the first's entire send while pinning an anyio threadpool token.
    """
    from app import billing_emails as be

    seen = {}

    def _spy_deliver(outbox):
        seen["locked_during_send"] = billing._user_lock("user_1").locked()
        return "sent"

    monkeypatch.setattr(be, "deliver", _spy_deliver)
    monkeypatch.setattr(be, "prepare", lambda *a, **kw: "an-outbox")
    monkeypatch.setattr(billing, "_customer_id_for_event", lambda t, o: "cus_1")
    monkeypatch.setattr(billing, "_user_id_for_event", lambda t, o, c: "user_1")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "active",
                                     "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda u, c, e: None)
    monkeypatch.setattr(billing, "_invalidate", lambda u: None)

    billing._handle_event({"id": "evt_lk", "type": "customer.subscription.updated",
                           "data": {"object": {"customer": "cus_1"}}})
    assert seen["locked_during_send"] is False, "the SMTP send ran while holding the lock"


def test_the_decision_still_happens_inside_the_lock(monkeypatch):
    """The other half of N2: prepare() must stay serialised or the upgrade comparison
    can straddle another event's write."""
    from app import billing_emails as be

    seen = {}
    monkeypatch.setattr(be, "prepare",
                        lambda *a, **kw: seen.setdefault(
                            "locked_during_decide", billing._user_lock("user_1").locked()))
    monkeypatch.setattr(be, "deliver", lambda outbox: None)
    monkeypatch.setattr(billing, "_customer_id_for_event", lambda t, o: "cus_1")
    monkeypatch.setattr(billing, "_user_id_for_event", lambda t, o, c: "user_1")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "active",
                                     "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda u, c, e: None)
    monkeypatch.setattr(billing, "_invalidate", lambda u: None)

    billing._handle_event({"id": "evt_lk2", "type": "customer.subscription.updated",
                           "data": {"object": {"customer": "cus_1"}}})
    assert seen["locked_during_decide"] is True
