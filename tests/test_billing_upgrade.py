"""Unit tests for the upgrade lane in app/billing.py — POST /api/billing/upgrade.

Same offline idiom as tests/test_billing_subscribe.py: no network, no real Stripe, no
Supabase. `billing._stripe`, `billing._existing_customer`, `billing._price_id`, and the
same-module authority triad (`_compute_entitlement`/`_upsert_entitlement`/`_invalidate`)
are monkeypatched; the route is called directly with a stub `user` dict. The one exception
— the unauthenticated 401 — goes through a TestClient hit against the mounted app, since
that is the only way to exercise the `Depends(_current_user)` gate (and per repo memory
fastapi-includedrouter-route-verify, endpoints are verified via RESPONSES, never by
scanning app.routes for .path).

The Subscription.modify kwargs are asserted LITERALLY (billing-truth law, masterplan §6):
the proration semantics the operator asked for — item id swap to the Pro price,
always_invoice, error_if_incomplete — are enforced HERE, not in the sheet.

The upgrade matrix (insider/pro × monthly/annual, never a downgrade, never a no-op) is enforced by
the pure helper billing._upgrade_allowed; its per-lane truth table is unit-tested in
tests/test_billing_upgrade_matrix.py. The endpoint tests here cover the wiring: the matrix gate
runs before Stripe, the target tier+interval reach modify, and the response carries them.

Coverage:
  401 — unauthenticated (TestClient).
  400 — unknown interval override; unknown tier override.
  404 — no customer for the user; customer but no live subscription.
  409 — an out-of-matrix move (already on the top plan; a downgrade attempt) — never touches Stripe.
  happy — active Insider -> modify kwargs asserted literally (item id, Pro price,
          always_invoice, error_if_incomplete, mm_user_id) + entitlement upserted to Pro +
          cache invalidated + prorated:true + invoice_total_cents surfaced + tier/interval echoed.
  trialing — trial preserved (status stays trialing), prorated:false / trialing:true.
  decline — CardError from error_if_incomplete -> 402 carrying Stripe's message.

Run:
    python -m pytest tests/test_billing_upgrade.py -v
"""
from __future__ import annotations

import types

import pytest
import stripe
from fastapi import HTTPException

from app import billing

USER = {"id": "user_1", "email": "buyer@example.com"}


# --------------------------------------------------------------------------- #
# fakes
# --------------------------------------------------------------------------- #
class _ListResp:
    def __init__(self, data):
        self.data = data


def _price(lk, interval="month"):
    return types.SimpleNamespace(lookup_key=lk, interval=interval)


def _sub(status, lk="insider_monthly", *, sub_id="sub_ins", item_id="si_ins", interval="month"):
    """A live subscription object shaped like the real Stripe SDK (attr access, items.data)."""
    return types.SimpleNamespace(
        id=sub_id,
        status=status,
        items=types.SimpleNamespace(data=[
            types.SimpleNamespace(id=item_id, price=_price(lk, interval), current_period_end=1900000000),
        ]),
        current_period_end=None,
    )


class _FakeStripe:
    """Records Subscription.modify kwargs for literal assertions; can raise a CardError."""

    error = stripe.error  # so `stripe.error.CardError` resolves against the fake

    def __init__(self, *, subs=None, modify_raises=None, invoice_total=1234):
        self._subs = subs or []
        self._modify_raises = modify_raises
        self._invoice_total = invoice_total
        self.calls: dict = {}

        outer = self

        class _Subscription:
            @staticmethod
            def list(**kw):
                return _ListResp(outer._subs)

            @staticmethod
            def modify(sub_id, **kw):
                outer.calls["modify"] = {"sub_id": sub_id, **kw}
                if outer._modify_raises is not None:
                    raise outer._modify_raises
                # The upgraded subscription: now on the Pro price, with an expanded latest_invoice.
                return types.SimpleNamespace(
                    id=sub_id,
                    status="active",
                    latest_invoice=types.SimpleNamespace(total=outer._invoice_total),
                    items=types.SimpleNamespace(data=[
                        types.SimpleNamespace(price=_price("pro_monthly"), current_period_end=1900000000),
                    ]),
                    current_period_end=None,
                )

        class _Customer:
            @staticmethod
            def retrieve(customer_id):
                outer.calls["customer_retrieve"] = customer_id
                return types.SimpleNamespace(id=customer_id, metadata={})

            @staticmethod
            def modify(customer_id, **kw):
                outer.calls["customer_modify"] = {"customer_id": customer_id, **kw}
                return types.SimpleNamespace(id=customer_id, metadata=kw.get("metadata", {}))

        self.Subscription = _Subscription
        self.Customer = _Customer


# --------------------------------------------------------------------------- #
# 401 — the mounted, gated endpoint
# --------------------------------------------------------------------------- #
def test_upgrade_401_unauthenticated():
    """Endpoint is mounted and gated: no bearer -> 401 (never 404). TestClient, not route scan."""
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    r = client.post("/api/billing/upgrade", json={"interval": "annual"})
    assert r.status_code == 401, f"upgrade should require auth, got {r.status_code}"


# --------------------------------------------------------------------------- #
# 400 / 404 / 409 — the guard rails
# --------------------------------------------------------------------------- #
def test_upgrade_400_unknown_interval(monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: pytest.fail("must reject before Stripe"))
    monkeypatch.setattr(billing, "_existing_customer",
                        lambda uid: pytest.fail("must reject before customer lookup"))
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(interval="weekly"), user=USER)
    assert ei.value.status_code == 400


def test_upgrade_404_no_customer(monkeypatch):
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: None)
    monkeypatch.setattr(billing, "_stripe", lambda: pytest.fail("no Stripe call without a customer"))
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)
    assert ei.value.status_code == 404 and ei.value.detail == "no subscription"


def test_upgrade_404_no_live_subscription(monkeypatch):
    # customer exists but holds no active/trialing sub (e.g. canceled) -> 404.
    fake = _FakeStripe(subs=[])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)
    assert ei.value.status_code == 404 and ei.value.detail == "no subscription"
    assert "modify" not in fake.calls


def test_upgrade_409_noop_already_on_target(monkeypatch):
    # pro·monthly with the default target (pro, current cadence) is a no-op -> 409 naming the plan.
    fake = _FakeStripe(subs=[_sub("active", "pro_monthly", sub_id="sub_pro")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)
    assert ei.value.status_code == 409 and ei.value.detail == "already on pro monthly"
    assert "modify" not in fake.calls  # never touch Stripe.modify for an out-of-matrix move


def test_upgrade_409_downgrade_refused(monkeypatch):
    # pro·annual asking for insider·monthly steps down on BOTH axes -> 409, no Stripe call.
    fake = _FakeStripe(subs=[_sub("active", "pro_annual", sub_id="sub_pro", interval="year")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(tier="insider", interval="monthly"), user=USER)
    assert ei.value.status_code == 409
    assert "downgrade" in ei.value.detail.lower()
    assert "modify" not in fake.calls


def test_upgrade_400_unknown_tier(monkeypatch):
    monkeypatch.setattr(billing, "_stripe", lambda: pytest.fail("must reject before Stripe"))
    monkeypatch.setattr(billing, "_existing_customer",
                        lambda uid: pytest.fail("must reject before customer lookup"))
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(tier="enterprise"), user=USER)
    assert ei.value.status_code == 400


# --------------------------------------------------------------------------- #
# happy path — active Insider -> Pro, prorated + invoiced now
# --------------------------------------------------------------------------- #
def test_upgrade_active_insider_to_pro_prorates_and_syncs(monkeypatch):
    fake = _FakeStripe(subs=[_sub("active", "insider_monthly")], invoice_total=1234)
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    synced: dict = {}
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "active",
                                     "current_period_end": None, "features": ["site_full", "chat_opus"]})
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda uid, cid, ent: synced.update(uid=uid, cid=cid, ent=ent))
    monkeypatch.setattr(billing, "_invalidate", lambda uid: synced.update(invalidated=uid))

    out = billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)

    # LITERAL modify kwargs — the proration contract is enforced here.
    kw = fake.calls["modify"]
    assert kw["sub_id"] == "sub_ins"
    assert kw["items"] == [{"id": "si_ins", "price": "price_pro_2026_v2_monthly"}]  # kept monthly cadence
    assert kw["proration_behavior"] == "always_invoice"
    assert kw["payment_behavior"] == "error_if_incomplete"
    assert kw["metadata"] == {"mm_user_id": "user_1"}

    # response contract
    assert out["status"] == "ok"
    assert out["tier"] == "pro"
    assert out["interval"] == "monthly"  # kept the current cadence, echoed back
    assert out["prorated"] is True
    assert out["trialing"] is False
    assert out["invoice_total_cents"] == 1234

    # same-module authority: entitlement upserted to Pro + cache busted
    assert synced["ent"]["tier"] == "pro" and synced["ent"]["status"] == "active"
    assert synced["uid"] == "user_1" and synced["cid"] == "cus_1"
    assert synced["invalidated"] == "user_1"


def test_upgrade_interval_override_switches_cadence(monkeypatch):
    # user is on insider_monthly but asks to upgrade to the ANNUAL Pro price.
    fake = _FakeStripe(subs=[_sub("active", "insider_monthly")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "active", "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda *a: None)
    monkeypatch.setattr(billing, "_invalidate", lambda *a: None)

    billing.upgrade(billing.UpgradeRequest(interval="annual"), user=USER)
    assert fake.calls["modify"]["items"] == [{"id": "si_ins", "price": "price_pro_2026_v2_annual"}]


def test_upgrade_insider_monthly_to_insider_annual(monkeypatch):
    # Same-tier interval bump (insider·m -> insider·a) — the pre-matrix endpoint blocked this as a
    # same-tier no-op; the matrix allows it (annual outranks monthly). tier defaults to 'pro' back-
    # compat, so this lane MUST pass the tier explicitly. It passes the PRE-RENAME spelling
    # on purpose: a far-future-cached onboard.js keeps sending it, and the request must
    # still resolve to the current price.
    fake = _FakeStripe(subs=[_sub("active", "insider_monthly")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "essential", "status": "active",
                                     "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda *a: None)
    monkeypatch.setattr(billing, "_invalidate", lambda *a: None)

    out = billing.upgrade(billing.UpgradeRequest(tier="insider", interval="annual"), user=USER)
    assert fake.calls["modify"]["items"] == [{"id": "si_ins", "price": "price_essential_2026_v2_annual"}]
    assert out["tier"] == "essential" and out["interval"] == "annual"


def test_upgrade_insider_monthly_to_pro_annual(monkeypatch):
    # Diagonal jump (insider·m -> pro·a): both tier AND interval override, both step up.
    fake = _FakeStripe(subs=[_sub("active", "insider_monthly")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "active",
                                     "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda *a: None)
    monkeypatch.setattr(billing, "_invalidate", lambda *a: None)

    out = billing.upgrade(billing.UpgradeRequest(tier="pro", interval="annual"), user=USER)
    assert fake.calls["modify"]["items"] == [{"id": "si_ins", "price": "price_pro_2026_v2_annual"}]
    assert out["tier"] == "pro" and out["interval"] == "annual"


def test_upgrade_to_founding_pro_applies_promotion_and_keeps_proration(monkeypatch):
    fake = _FakeStripe(subs=[_sub("active", "insider_annual", interval="year")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    monkeypatch.setattr(
        billing, "_offer_discount",
        lambda key, customer_id=None: [{"promotion_code": "promo_founder"}] if key else None)
    monkeypatch.setattr(
        billing, "_compute_entitlement",
        lambda cid: {"tier": "pro", "status": "active", "current_period_end": None,
                     "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda *a: None)
    monkeypatch.setattr(billing, "_invalidate", lambda *a: None)

    billing.upgrade(
        billing.UpgradeRequest(
            tier="pro", interval="annual", offer="founding_pro"),
        user=USER,
    )

    kw = fake.calls["modify"]
    assert kw["items"] == [{"id": "si_ins", "price": "price_pro_2026_v2_annual"}]
    assert kw["discounts"] == [{"promotion_code": "promo_founder"}]
    assert kw["proration_behavior"] == "always_invoice"
    assert kw["payment_behavior"] == "error_if_incomplete"
    assert kw["metadata"] == {"mm_user_id": "user_1", "mm_offer": "founding_pro"}
    assert fake.calls["customer_modify"] == {
        "customer_id": "cus_1",
        "metadata": {"mm_founding_pro_entitled": "true"},
    }


# --------------------------------------------------------------------------- #
# trialing — price swapped, trial preserved, no proration
# --------------------------------------------------------------------------- #
def test_upgrade_trialing_preserves_trial_no_proration(monkeypatch):
    fake = _FakeStripe(subs=[_sub("trialing", "insider_monthly")])
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    monkeypatch.setattr(billing, "_compute_entitlement",
                        lambda cid: {"tier": "pro", "status": "trialing", "current_period_end": None, "features": []})
    monkeypatch.setattr(billing, "_upsert_entitlement", lambda *a: None)
    monkeypatch.setattr(billing, "_invalidate", lambda *a: None)

    out = billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)

    # Still always_invoice at the API level (Stripe no-ops proration during a trial); but the
    # RESPONSE tells the honest truth: trialing, and nothing was prorated/charged now.
    kw = fake.calls["modify"]
    assert kw["proration_behavior"] == "always_invoice"
    assert kw["items"] == [{"id": "si_ins", "price": "price_pro_2026_v2_monthly"}]
    assert out["trialing"] is True
    assert out["prorated"] is False
    assert out["tier"] == "pro"


# --------------------------------------------------------------------------- #
# decline — error_if_incomplete raises CardError -> 402 with Stripe's message
# --------------------------------------------------------------------------- #
def test_upgrade_card_decline_402(monkeypatch):
    decline = stripe.error.CardError("Your card was declined.", param=None, code="card_declined")
    fake = _FakeStripe(subs=[_sub("active", "insider_monthly")], modify_raises=decline)
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    # entitlement sync must NOT run on a decline (the switch never happened).
    monkeypatch.setattr(billing, "_upsert_entitlement",
                        lambda *a: pytest.fail("no entitlement write on a declined upgrade"))
    monkeypatch.setattr(billing, "_invalidate", lambda *a: pytest.fail("no cache bust on a declined upgrade"))

    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)
    assert ei.value.status_code == 402
    assert ei.value.detail == "Your card was declined."


def test_upgrade_other_stripe_error_502(monkeypatch):
    boom = stripe.error.InvalidRequestError("no such price", param="price")
    fake = _FakeStripe(subs=[_sub("active", "insider_monthly")], modify_raises=boom)
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    with pytest.raises(HTTPException) as ei:
        billing.upgrade(billing.UpgradeRequest(interval=None), user=USER)
    assert ei.value.status_code == 502
