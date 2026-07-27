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
    def __init__(self, promo):
        class _PromotionCode:
            @staticmethod
            def list(**kwargs):
                assert kwargs["code"] == "FOUNDINGPRO2026"
                return _ListResp([promo])

        self.PromotionCode = _PromotionCode


def _promo(*, claimed=0, active=True):
    return types.SimpleNamespace(
        id="promo_founder", times_redeemed=claimed, active=active)


def _wire(monkeypatch, promo):
    billing._PROMO_CACHE.clear()
    monkeypatch.setattr(billing, "_stripe", lambda: _FakeStripe(promo))


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
        "remaining": 213,
        "cap": 250,
        "unit_amount": 82800,
        "regular_unit_amount": 106800,
        "currency": "usd",
        "renews_while_uninterrupted": True,
    }
    assert billing._offer_discount("founding_pro") == [
        {"promotion_code": "promo_founder"}]


def test_offer_sells_out_at_stripe_cap(monkeypatch):
    _wire(monkeypatch, _promo(claimed=250))
    status = billing._offer_status("founding_pro")
    assert status["active"] is False
    assert status["remaining"] == 0
    with pytest.raises(HTTPException) as ei:
        billing._offer_discount("founding_pro")
    assert ei.value.status_code == 410


def test_offer_create_race_rechecks_stripe_without_cached_inventory(monkeypatch):
    promo = _promo(claimed=249)
    _wire(monkeypatch, promo)
    assert billing._offer_status("founding_pro")["active"] is True

    # Another checkout wins the final redemption after our initial availability
    # check but before Stripe accepts this request.
    promo.times_redeemed = 250
    assert billing._offer_sold_out_after_error("founding_pro") is True
