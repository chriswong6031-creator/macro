"""Offline tests for the truthful, Stripe-backed Founding Pro inventory."""
from __future__ import annotations

import datetime as dt
import types

import pytest
from fastapi import HTTPException

from app import billing

BASELINE = dt.date(2026, 7, 27)  # plans.yml allotment_pacing.baseline_date


@pytest.fixture(autouse=True)
def _isolated_allotment(monkeypatch, tmp_path):
    """Pin the pacing clock to baseline day and keep the ledger off /var/lib."""
    monkeypatch.setenv("MACRO_API_STATE_DIR", str(tmp_path))
    monkeypatch.setattr(billing, "_pacing_today", lambda pacing: BASELINE)


def _step_clock(monkeypatch, days: int):
    monkeypatch.setattr(
        billing, "_pacing_today", lambda pacing: BASELINE + dt.timedelta(days=days))


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
                return _ListResp([] if promo is None else [promo])

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
        "claimed": 37,                    # real Stripe redemptions, undisguised
        "reserved": 207,                  # withdrawn so day-0 unavailable == 244 baseline
        "unavailable": 244,
        "remaining": 1756,
        "cap": 2000,
        "public_count_threshold": 25,
        "unit_amount": 90000,
        "regular_unit_amount": 130800,
        "currency": "usd",
        "renews_at_offer_rate": True,
    }
    assert billing._offer_discount("founding_pro") == [
        {"promotion_code": "promo_founder"}]


def test_quiet_day_withdraws_the_daily_step(monkeypatch):
    promo = _promo(claimed=37)
    _wire(monkeypatch, promo)
    assert billing._offer_status("founding_pro")["unavailable"] == 244
    _step_clock(monkeypatch, 1)           # next day, zero new redemptions
    status = billing._offer_status("founding_pro")
    assert status["reserved"] == 209
    assert status["unavailable"] == 246
    assert status["remaining"] == 1754


def test_redemption_day_advances_by_real_signups_only(monkeypatch):
    promo = _promo(claimed=37)
    _wire(monkeypatch, promo)
    assert billing._offer_status("founding_pro")["unavailable"] == 244
    promo.times_redeemed = 40             # 3 real signups land during the day
    _step_clock(monkeypatch, 1)
    status = billing._offer_status("founding_pro")
    assert status["reserved"] == 207      # no synthetic step on a redemption day
    assert status["unavailable"] == 247   # 244 + 3 real signups
    # a second read the same day is a no-op
    assert billing._offer_status("founding_pro")["unavailable"] == 247


def test_multi_day_gap_steps_only_the_quiet_days(monkeypatch):
    promo = _promo(claimed=37)
    _wire(monkeypatch, promo)
    assert billing._offer_status("founding_pro")["unavailable"] == 244
    promo.times_redeemed = 39             # 2 signups somewhere in a 3-day gap
    _step_clock(monkeypatch, 3)
    status = billing._offer_status("founding_pro")
    assert status["reserved"] == 207 + 2  # one quiet day's step (3 days - 2 signup days)
    assert status["unavailable"] == 209 + 39


def test_lost_ledger_reseeds_as_if_every_day_was_quiet(monkeypatch, tmp_path):
    _wire(monkeypatch, _promo(claimed=50))
    _step_clock(monkeypatch, 5)
    status = billing._offer_status("founding_pro")
    assert status["reserved"] == (244 - 50) + 2 * 5
    assert status["unavailable"] == 254


def test_heavily_redeemed_offer_needs_no_reserve(monkeypatch):
    _wire(monkeypatch, _promo(claimed=300))
    status = billing._offer_status("founding_pro")
    assert status["reserved"] == 0        # real demand already exceeds the baseline
    assert status["unavailable"] == 300
    assert status["remaining"] == 1700


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


def test_unprovisioned_offer_is_a_clean_503(monkeypatch, caplog):
    """An unbootstrapped Stripe mode must not leak the operator runbook to clients.

    On 2026-07-31 the live VPS served 85/85 requests to /api/billing/offers/founding_pro
    as 503s whose public detail said "run scripts/stripe_bootstrap.py" — the runbook
    belongs in the server log, never in the response body.
    """
    _wire(monkeypatch, None)
    with caplog.at_level("ERROR", logger="macro.billing"):
        with pytest.raises(HTTPException) as ei:
            billing._offer_status("founding_pro")
    assert ei.value.status_code == 503
    detail = str(ei.value.detail)
    assert "temporarily unavailable" in detail
    for leak in ("stripe_bootstrap", "scripts/", "provisioned", "Stripe"):
        assert leak not in detail
    assert any("stripe_bootstrap" in r.message for r in caplog.records)


def test_promo_without_id_is_a_clean_503(monkeypatch):
    _wire(monkeypatch, types.SimpleNamespace(id=None, times_redeemed=0, active=True))
    with pytest.raises(HTTPException) as ei:
        billing._offer_discount("founding_pro")
    assert ei.value.status_code == 503
    detail = str(ei.value.detail)
    assert "temporarily unavailable" in detail
    assert "Stripe" not in detail


def test_missing_price_is_a_clean_503(monkeypatch, caplog):
    billing._PRICE_CACHE.clear()
    fake = types.SimpleNamespace(
        Price=types.SimpleNamespace(list=lambda **kwargs: _ListResp([])))
    monkeypatch.setattr(billing, "_stripe", lambda: fake)
    with caplog.at_level("ERROR", logger="macro.billing"):
        with pytest.raises(HTTPException) as ei:
            billing._price_id("pro_2026_v2_annual")
    assert ei.value.status_code == 503
    detail = str(ei.value.detail)
    assert "temporarily unavailable" in detail
    for leak in ("stripe_bootstrap", "scripts/", "pro_2026_v2_annual", "Stripe"):
        assert leak not in detail
    assert any("stripe_bootstrap" in r.message for r in caplog.records)
