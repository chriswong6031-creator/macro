"""Offline contract tests for hosted Stripe Checkout pricing and offers."""
from __future__ import annotations

import types

from app import billing


USER = {"id": "user_1", "email": "buyer@example.com"}


class _FakeStripe:
    def __init__(self):
        self.calls = {}
        outer = self

        class _Session:
            @staticmethod
            def create(**kwargs):
                outer.calls["create"] = kwargs
                return types.SimpleNamespace(
                    id="cs_test_1", url="https://checkout.stripe.com/c/pay/test")

        self.checkout = types.SimpleNamespace(Session=_Session)


def test_founding_checkout_uses_regular_price_plus_capped_promotion(monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: None)
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")
    monkeypatch.setattr(
        billing, "_offer_discount",
        lambda key, customer_id=None: [{"promotion_code": "promo_founder"}] if key else None)

    out = billing.checkout(
        billing.CheckoutRequest(
            tier="pro", interval="annual", offer="founding_pro"),
        user=USER,
    )

    assert out["id"] == "cs_test_1"
    args = fake.calls["create"]
    assert args["line_items"] == [
        {"price": "price_pro_2026_v2_annual", "quantity": 1}]
    assert args["discounts"] == [{"promotion_code": "promo_founder"}]
    assert "allow_promotion_codes" not in args
    assert args["subscription_data"]["trial_period_days"] == 7
    assert args["subscription_data"]["metadata"] == {
        "mm_user_id": "user_1", "mm_offer": "founding_pro"}
    assert args["metadata"] == {
        "mm_user_id": "user_1", "mm_offer": "founding_pro"}


def test_regular_checkout_does_not_expose_manual_promotion_code_entry(monkeypatch):
    fake = _FakeStripe()
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    monkeypatch.setattr(billing, "_existing_customer", lambda uid: "cus_1")
    monkeypatch.setattr(billing, "_price_id", lambda lk: f"price_{lk}")

    billing.checkout(
        billing.CheckoutRequest(tier="insider", interval="annual"), user=USER)

    args = fake.calls["create"]
    assert args["line_items"] == [
        {"price": "price_essential_2026_v2_annual", "quantity": 1}]
    assert "allow_promotion_codes" not in args
    assert "discounts" not in args
