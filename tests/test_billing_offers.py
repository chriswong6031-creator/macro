"""Offline tests for the truthful, Stripe-backed Founding Pro inventory."""
from __future__ import annotations

import types

import pytest
from fastapi import HTTPException

from app import billing


class _ListResp:
    def __init__(self, data):
        self.data = data


class _FakeStripe:
    def __init__(self, promo, *, customer_metadata=None, subscriptions=None):
        self.customer_metadata = dict(customer_metadata or {})
        self.subscriptions = list(subscriptions or [])
        self.modified_metadata = None
        outer = self

        class _PromotionCode:
            @staticmethod
            def list(**kwargs):
                assert kwargs["code"] == "FOUNDINGPRO2026V2"
                return _ListResp([promo])

        class _Customer:
            @staticmethod
            def retrieve(customer_id):
                assert customer_id == "cus_founder"
                return types.SimpleNamespace(metadata=outer.customer_metadata)

            @staticmethod
            def modify(customer_id, **kwargs):
                assert customer_id == "cus_founder"
                outer.modified_metadata = kwargs["metadata"]
                outer.customer_metadata.update(kwargs["metadata"])
                return types.SimpleNamespace(id=customer_id, metadata=outer.customer_metadata)

        class _Subscription:
            @staticmethod
            def list(**kwargs):
                assert kwargs["customer"] == "cus_founder"
                assert kwargs["status"] == "all"
                return _ListResp(outer.subscriptions)

        self.PromotionCode = _PromotionCode
        self.Customer = _Customer
        self.Subscription = _Subscription


def _promo(*, claimed=0, active=True):
    return types.SimpleNamespace(
        id="promo_founder", times_redeemed=claimed, active=active)


def _wire(monkeypatch, promo, **kwargs):
    billing._PROMO_CACHE.clear()
    fake = _FakeStripe(promo, **kwargs)
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    return fake


def test_offer_is_only_valid_for_pro_annual():
    assert billing._offer_key("founding_pro", "pro", "annual") == "founding_pro"
    with pytest.raises(HTTPException) as ei:
        billing._offer_key("founding_pro", "pro", "monthly")
    assert ei.value.status_code == 400
    with pytest.raises(HTTPException) as ei:
        billing._offer_key("founding_pro", "insider", "annual")
    assert ei.value.status_code == 400


def test_offer_status_uses_real_stripe_redemption_count(monkeypatch):
    _wire(monkeypatch, _promo(claimed=37))
    status = billing._offer_status("founding_pro")
    assert status == {
        "key": "founding_pro",
        "name": "Founding Pro",
        "tier": "pro",
        "interval": "annual",
        "active": True,
        "claimed": 37,
        "remaining": 1963,
        "cap": 2000,
        "public_count_threshold": 25,
        "unit_amount": 90000,
        "regular_unit_amount": 130800,
        "currency": "usd",
        "renews_at_offer_rate": True,
    }
    assert billing._offer_discount("founding_pro") == [
        {"promotion_code": "promo_founder"}]


def test_offer_sells_out_at_stripe_cap(monkeypatch):
    _wire(monkeypatch, _promo(claimed=2000))
    status = billing._offer_status("founding_pro")
    assert status["active"] is False
    assert status["remaining"] == 0
    with pytest.raises(HTTPException) as ei:
        billing._offer_discount("founding_pro")
    assert ei.value.status_code == 410


def test_offer_create_race_rechecks_stripe_without_cached_inventory(monkeypatch):
    promo = _promo(claimed=1999)
    _wire(monkeypatch, promo)
    assert billing._offer_status("founding_pro")["active"] is True

    # Another checkout wins the final redemption after our initial availability
    # check but before Stripe accepts this request.
    promo.times_redeemed = 2000
    assert billing._offer_sold_out_after_error("founding_pro") is True


def test_grandfathered_customer_bypasses_new_member_cap(monkeypatch):
    _wire(
        monkeypatch,
        _promo(claimed=2000, active=False),
        customer_metadata={"mm_founding_pro_entitled": "true"},
    )
    assert billing._offer_discount("founding_pro", "cus_founder") == [
        {"coupon": "mastermind_founding_pro_annual_2026_v2"}]
    assert billing._effective_offer_key(None, "pro", "annual", "cus_founder") == "founding_pro"


def test_subscription_history_repairs_missing_customer_marker(monkeypatch):
    fake = _wire(
        monkeypatch,
        _promo(claimed=2000, active=False),
        subscriptions=[
            types.SimpleNamespace(
                status="canceled",
                metadata={"mm_offer": "founding_pro"},
            )
        ],
    )
    assert billing._customer_offer_entitled("cus_founder", "founding_pro") is True
    assert fake.modified_metadata == {"mm_founding_pro_entitled": "true"}
