"""Unit tests for the Elements subscription lane in app/billing.py (MNZ onboarding W2).

Same offline idiom as tests/test_billing_webhook.py: no network, no real Stripe, no
Supabase. `billing._stripe` and the `billing._pg` PostgREST helper are monkeypatched;
route functions are called directly with a stub `user` dict (mirroring how the webhook
tests call `_handle_event` directly), so no real auth round trip is needed. The one
exception — the unauthenticated 401 — goes through a TestClient hit against the mounted
app, since that is the only way to exercise the `Depends(_current_user)` gate.

NOTE (repo memory fastapi-includedrouter-route-verify): this FastAPI wraps routers in
_IncludedRouter, so endpoints are verified via TestClient RESPONSES, never by scanning
app.routes for .path.

Coverage:
  config    — 503 when STRIPE_PUBLISHABLE_KEY unset; 200 + key when set.
  init      — 401 unauthenticated (TestClient); creates+persists customer when absent and
              returns the SetupIntent client_secret; 409 on an existing active/trialing sub;
              400 on unknown tier / interval.
  complete  — 400 when the SI is not succeeded; 400 on SI customer mismatch; creates the sub
              with trial_period_days=7, the SI's payment method, on-subscription PM save, and
              cancel-on-missing-PM trial settings; upserts the entitlement row (status trialing)
              and busts the tier cache; 409 double-subscribe.

The subscription-create kwargs are asserted LITERALLY — the billing-truth law (masterplan
§6) is that UI copy ("7-day trial", "cancel costs nothing") is enforced HERE, not in the sheet.

Run:
    python -m pytest tests/test_billing_subscribe.py -v
"""
from __future__ import annotations

import types

import pytest
from fastapi import HTTPException

from app import billing

USER = {"id": "user_1", "email": "buyer@example.com"}


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _ListResp:
    def __init__(self, data):
        self.data = data


def _sub(status: str):
    return types.SimpleNamespace(id="sub_x", status=status)


class _FakeStripe:
    """Records SetupIntent / Subscription / Customer create kwargs for literal assertions."""

    def __init__(self, *, subs=None, si=None, new_customer_id="cus_new"):
        self._subs = subs or []
        self._si_on_retrieve = si
        self._new_customer_id = new_customer_id
        self.calls: dict = {}

        outer = self

        class _Customer:
            @staticmethod
            def create(**kw):
                outer.calls["customer_create"] = kw
                return types.SimpleNamespace(id=outer._new_customer_id)

        class _SetupIntent:
            @staticmethod
            def create(**kw):
                outer.calls["si_create"] = kw
                return types.SimpleNamespace(client_secret="seti_abc_secret_123", id="seti_abc")

            @staticmethod
            def retrieve(sid):
                outer.calls["si_retrieve"] = sid
                return outer._si_on_retrieve

        class _Subscription:
            @staticmethod
            def list(**kw):
                return _ListResp(outer._subs)

            @staticmethod
            def create(**kw):
                outer.calls["sub_create"] = kw
                return types.SimpleNamespace(id="sub_new", status="trialing", trial_end=1900000000)

        self.Customer = _Customer
        self.SetupIntent = _SetupIntent
        self.Subscription = _Subscription


def _make_si(status="succeeded", customer="cus_1", pm="pm_123"):
    return types.SimpleNamespace(status=status, customer=customer, payment_method=pm)


# --------------------------------------------------------------------------- #
# config
# --------------------------------------------------------------------------- #
def test_config_503_when_env_unset(monkeypatch):
    monkeypatch.delenv("STRIPE_PUBLISHABLE_KEY", raising=False)
    with pytest.raises(HTTPException) as ei:
        billing.billing_config()
    assert ei.value.status_code == 503


def test_config_200_returns_key(monkeypatch):
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_test_xyz")
    out = billing.billing_config()
    assert out == {"publishable_key": "pk_test_xyz"}


# --------------------------------------------------------------------------- #
# init
# --------------------------------------------------------------------------- #
def test_init_401_unauthenticated():
    """Endpoint is mounted and gated: no bearer -> 401 (never 404). TestClient, not route scan."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post("/api/billing/subscribe/init", json={"tier": "insider", "interval": "annual"})
    assert r.status_code == 401, f"init should require auth, got {r.status_code}"


def test_init_creates_customer_persists_mapping_and_returns_secret(monkeypatch):
    fake = _FakeStripe(subs=[], new_customer_id="cus_new")
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: None)  # no customer yet
    persisted: dict = {}
    monkeypatch.setattr(billing, "_persist_customer",
                        lambda uid, cid: persisted.update(uid=uid, cid=cid))

    body = billing.SubscribeInitRequest(tier="pro", interval="monthly")
    out = billing.subscribe_init(body, user=USER)

    assert out == {"client_secret": "seti_abc_secret_123", "customer_id": "cus_new"}
    # customer created with email + mm_user_id metadata
    assert fake.calls["customer_create"] == {
        "email": "buyer@example.com", "metadata": {"mm_user_id": "user_1"}}
    # mapping persisted (mapping-only helper, not the full upsert)
    assert persisted == {"uid": "user_1", "cid": "cus_new"}
    # SetupIntent carries off_session usage + tier/interval metadata for /complete + the webhook,
    # and card-family-only automatic payment methods (redirect PMs would demand a return_url on
    # confirm and navigate away from the floating sheet — found live in the sandbox E2E).
    assert fake.calls["si_create"] == {
        "customer": "cus_new",
        "usage": "off_session",
        "automatic_payment_methods": {"enabled": True, "allow_redirects": "never"},
        "metadata": {"mm_user_id": "user_1", "mm_tier": "pro", "mm_interval": "monthly"},
    }


def test_init_reuses_existing_customer_no_persist(monkeypatch):
    fake = _FakeStripe(subs=[])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_persist_customer",
                        lambda uid, cid: pytest.fail("must not persist when customer already exists"))

    out = billing.subscribe_init(
        billing.SubscribeInitRequest(tier="insider", interval="annual"), user=USER)
    assert out["customer_id"] == "cus_1"
    assert "customer_create" not in fake.calls  # reused, not created
    assert fake.calls["si_create"]["customer"] == "cus_1"


def test_init_409_when_active_subscription_exists(monkeypatch):
    fake = _FakeStripe(subs=[_sub("active")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_init(billing.SubscribeInitRequest(tier="pro", interval="annual"), user=USER)
    assert ei.value.status_code == 409 and ei.value.detail == "already subscribed"
    assert "si_create" not in fake.calls  # no SetupIntent created for an already-subscribed user


def test_init_409_when_trialing_subscription_exists(monkeypatch):
    fake = _FakeStripe(subs=[_sub("trialing")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_init(billing.SubscribeInitRequest(tier="pro", interval="annual"), user=USER)
    assert ei.value.status_code == 409


def test_init_400_unknown_tier(monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: pytest.fail("must reject before Stripe"))
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_init(billing.SubscribeInitRequest(tier="platinum", interval="annual"), user=USER)
    assert ei.value.status_code == 400


def test_init_400_unknown_interval(monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: pytest.fail("must reject before Stripe"))
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_init(billing.SubscribeInitRequest(tier="pro", interval="weekly"), user=USER)
    assert ei.value.status_code == 400


# --------------------------------------------------------------------------- #
# complete
# --------------------------------------------------------------------------- #
def _complete_body(tier="pro", interval="monthly", sid="seti_abc"):
    return billing.SubscribeCompleteRequest(setup_intent_id=sid, tier=tier, interval=interval)


def test_complete_400_when_si_not_succeeded(monkeypatch):
    fake = _FakeStripe(si=_make_si(status="requires_payment_method", customer="cus_1"))
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_complete(_complete_body(), user=USER)
    assert ei.value.status_code == 400
    assert "sub_create" not in fake.calls  # no subscription created


def test_complete_400_when_si_customer_mismatch(monkeypatch):
    # SI belongs to a DIFFERENT customer than this user's — never trust the client.
    fake = _FakeStripe(si=_make_si(status="succeeded", customer="cus_evil"))
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_complete(_complete_body(), user=USER)
    assert ei.value.status_code == 400
    assert "sub_create" not in fake.calls


def test_complete_400_when_si_has_no_payment_method(monkeypatch):
    fake = _FakeStripe(si=_make_si(status="succeeded", customer="cus_1", pm=None))
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_complete(_complete_body(), user=USER)
    assert ei.value.status_code == 400


def test_complete_creates_sub_with_trial_and_syncs_entitlement(monkeypatch):
    # succeeded SI for THIS customer, no live sub yet -> create the trialing subscription.
    fake = _FakeStripe(subs=[], si=_make_si(status="succeeded", customer="cus_1", pm="pm_777"))
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    # same-module authority sync: recompute -> upsert -> invalidate (like _handle_event)
    synced: dict = {}
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "trialing",
                                     "current_period_end": None, "features": ["site_full", "chat_opus"]})
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda uid, cid, ent: synced.update(uid=uid, cid=cid, ent=ent))
    monkeypatch.setattr(billing, "_invalidate", lambda uid: synced.update(invalidated=uid))

    out = billing.subscribe_complete(_complete_body(tier="pro", interval="monthly"), user=USER)

    # return contract
    assert out == {"status": "trialing", "subscription_id": "sub_new", "trial_end": 1900000000}

    # LITERAL subscription-create kwargs — the billing-truth law is enforced here (7-day trial,
    # captured PM, save-on-subscription, cancel-on-missing-PM, mm_user_id metadata).
    kw = fake.calls["sub_create"]
    assert kw["customer"] == "cus_1"
    assert kw["items"] == [{"price": "price_pro_monthly"}]
    assert kw["trial_period_days"] == 7
    assert kw["default_payment_method"] == "pm_777"
    assert kw["payment_settings"] == {"save_default_payment_method": "on_subscription"}
    assert kw["trial_settings"] == {"end_behavior": {"missing_payment_method": "cancel"}}
    assert kw["metadata"] == {"mm_user_id": "user_1"}

    # entitlement row synced to trialing + cache busted
    assert synced["ent"]["status"] == "trialing" and synced["ent"]["tier"] == "pro"
    assert synced["uid"] == "user_1" and synced["cid"] == "cus_1"
    assert synced["invalidated"] == "user_1"


def test_complete_409_double_subscribe(monkeypatch):
    # A live sub already exists (a second tab beat this /complete) -> 409, no new sub.
    fake = _FakeStripe(subs=[_sub("active")], si=_make_si(status="succeeded", customer="cus_1"))
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    with pytest.raises(HTTPException) as ei:
        billing.subscribe_complete(_complete_body(), user=USER)
    assert ei.value.status_code == 409 and ei.value.detail == "already subscribed"
    assert "sub_create" not in fake.calls
