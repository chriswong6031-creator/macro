"""Offline contract test for Founding Pro Stripe object provisioning."""
from __future__ import annotations

import types

import stripe

from scripts import stripe_bootstrap as bootstrap


class _ListResp:
    def __init__(self, data):
        self.data = data


class _FakeStripe:
    error = stripe.error

    def __init__(self):
        self.calls = {}
        outer = self

        class _Coupon:
            @staticmethod
            def retrieve(coupon_id):
                raise stripe.error.InvalidRequestError(
                    f"No such coupon: {coupon_id}", param="id")

            @staticmethod
            def create(**kwargs):
                outer.calls["coupon"] = kwargs
                return types.SimpleNamespace(id=kwargs["id"])

        class _PromotionCode:
            @staticmethod
            def list(**kwargs):
                outer.calls["promo_list"] = kwargs
                return _ListResp([])

            @staticmethod
            def create(**kwargs):
                outer.calls["promo"] = kwargs
                return types.SimpleNamespace(id="promo_founder")

        self.Coupon = _Coupon
        self.PromotionCode = _PromotionCode


def test_bootstrap_creates_product_scoped_forever_coupon_and_real_cap(monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr(bootstrap, "stripe", fake)
    spec = {
        "name": "Founding Pro",
        "unit_amount": 82800,
        "max_redemptions": 250,
        "coupon_id": "mastermind_founding_pro_annual_2026",
        "promotion_code": "FOUNDINGPRO2026",
        "duration": "forever",
    }

    coupon_id, promo_id = bootstrap._ensure_offer(
        "founding_pro", spec, "prod_pro", 106800, "usd", False)

    assert (coupon_id, promo_id) == (
        "mastermind_founding_pro_annual_2026", "promo_founder")
    assert fake.calls["coupon"] == {
        "id": "mastermind_founding_pro_annual_2026",
        "name": "Founding Pro",
        "amount_off": 24000,
        "currency": "usd",
        "duration": "forever",
        "max_redemptions": 250,
        "applies_to": {"products": ["prod_pro"]},
        "metadata": {"mnz_offer": "founding_pro"},
    }
    assert fake.calls["promo"] == {
        "coupon": "mastermind_founding_pro_annual_2026",
        "code": "FOUNDINGPRO2026",
        "max_redemptions": 250,
        "metadata": {"mnz_offer": "founding_pro"},
    }


def test_bootstrap_reuses_owned_coupon_when_api_omits_product_scope(monkeypatch):
    coupon = types.SimpleNamespace(
        id="mastermind_founding_pro_annual_2026",
        amount_off=24000,
        currency="usd",
        duration="forever",
        max_redemptions=250,
        metadata={"mnz_offer": "founding_pro"},
    )
    promo = types.SimpleNamespace(
        id="promo_founder",
        coupon=types.SimpleNamespace(id=coupon.id),
        max_redemptions=250,
        active=True,
        times_redeemed=0,
    )

    class _ExistingStripe:
        error = stripe.error
        Coupon = types.SimpleNamespace(retrieve=lambda coupon_id: coupon)
        PromotionCode = types.SimpleNamespace(
            list=lambda **kwargs: _ListResp([promo]))

    monkeypatch.setattr(bootstrap, "stripe", _ExistingStripe())
    spec = {
        "name": "Founding Pro",
        "unit_amount": 82800,
        "max_redemptions": 250,
        "coupon_id": coupon.id,
        "promotion_code": "FOUNDINGPRO2026",
        "duration": "forever",
    }

    assert bootstrap._ensure_offer(
        "founding_pro", spec, "prod_pro", 106800, "usd", True
    ) == (coupon.id, promo.id)
