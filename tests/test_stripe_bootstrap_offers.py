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
        "unit_amount": 90000,
        "max_redemptions": 2000,
        "coupon_id": "mastermind_founding_pro_annual_2026_v2",
        "promotion_code": "FOUNDINGPRO2026V2",
        "duration": "forever",
    }

    coupon_id, promo_id = bootstrap._ensure_offer(
        "founding_pro", spec, "prod_pro", 130800, "usd", False)

    assert (coupon_id, promo_id) == (
        "mastermind_founding_pro_annual_2026_v2", "promo_founder")
    assert fake.calls["coupon"] == {
        "id": "mastermind_founding_pro_annual_2026_v2",
        "name": "Founding Pro",
        "amount_off": 40800,
        "currency": "usd",
        "duration": "forever",
        "applies_to": {"products": ["prod_pro"]},
        "metadata": {"mnz_offer": "founding_pro"},
    }
    assert fake.calls["promo"] == {
        "coupon": "mastermind_founding_pro_annual_2026_v2",
        "code": "FOUNDINGPRO2026V2",
        "max_redemptions": 2000,
        "metadata": {"mnz_offer": "founding_pro"},
    }


def test_bootstrap_reuses_owned_coupon_when_api_omits_product_scope(monkeypatch):
    coupon = types.SimpleNamespace(
        id="mastermind_founding_pro_annual_2026_v2",
        amount_off=40800,
        currency="usd",
        duration="forever",
        max_redemptions=None,
        metadata={"mnz_offer": "founding_pro"},
    )
    promo = types.SimpleNamespace(
        id="promo_founder",
        coupon=types.SimpleNamespace(id=coupon.id),
        max_redemptions=2000,
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
        "unit_amount": 90000,
        "max_redemptions": 2000,
        "coupon_id": coupon.id,
        "promotion_code": "FOUNDINGPRO2026V2",
        "duration": "forever",
    }

    assert bootstrap._ensure_offer(
        "founding_pro", spec, "prod_pro", 130800, "usd", True
    ) == (coupon.id, promo.id)


def test_bootstrap_retires_superseded_acquisition_code(monkeypatch):
    promo = types.SimpleNamespace(id="promo_old", active=True)
    modified = {}

    class _PromotionCode:
        @staticmethod
        def list(**kwargs):
            assert kwargs == {"code": "FOUNDINGPRO2026", "limit": 10}
            return _ListResp([promo])

        @staticmethod
        def modify(promo_id, **kwargs):
            modified.update(id=promo_id, **kwargs)

    monkeypatch.setattr(
        bootstrap,
        "stripe",
        types.SimpleNamespace(PromotionCode=_PromotionCode),
    )
    bootstrap._retire_promotion_codes(
        ["FOUNDINGPRO2026"], "FOUNDINGPRO2026V2", False)
    assert modified == {"id": "promo_old", "active": False}


def test_founding_base_price_can_be_reprovisioned_independently(monkeypatch):
    """A fresh Stripe environment can recreate the immutable anchor after rack-price changes."""
    created = {}

    class _Price:
        @staticmethod
        def list(**kwargs):
            return _ListResp([])

        @staticmethod
        def create(**kwargs):
            created.update(kwargs)
            return types.SimpleNamespace(id="price_founding_anchor")

    monkeypatch.setattr(bootstrap, "stripe", types.SimpleNamespace(Price=_Price))
    assert bootstrap._ensure_price(
        "prod_pro",
        {
            "lookup_key": "pro_2026_v2_annual",
            "unit_amount": 130800,
            "interval": "year",
        },
        "usd",
        False,
    ) == "price_founding_anchor"
    assert created == {
        "product": "prod_pro",
        "currency": "usd",
        "unit_amount": 130800,
        "recurring": {"interval": "year"},
        "lookup_key": "pro_2026_v2_annual",
        "transfer_lookup_key": True,
    }
