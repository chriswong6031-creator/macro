"""tests/test_plans_catalog.py — W0 pricing-alignment guard (onboarding masterplan §2).

Pins config/plans.yml to the LOCKED 2026-07-27 pricing so config, the Stripe
sandbox objects (scripts/stripe_bootstrap.py re-creates drifted prices from this
file), and the landing page can't silently diverge:

    Insider  $99/mo · $900/yr ($75/mo-equivalent, save 24%) · 7-day trial
    Pro      $149/mo · $1,308/yr ($109/mo-equivalent, save 27%) · 7-day trial
    Founding Pro  $900/yr ($75/mo-equivalent, save $408/year) · first 2,000

Also verifies the billing endpoints are mounted by hitting them with a TestClient
(401/503 responses). NOTE (repo memory fastapi-includedrouter-route-verify): this
FastAPI wraps routers in _IncludedRouter, so endpoint existence is verified via
TestClient RESPONSES, never by scanning app.routes for .path.

Run:
    python -m pytest tests/test_plans_catalog.py -v
"""
from __future__ import annotations

import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# The locked table (onboarding masterplan §2; landing templates/index.html shows the same).
LOCKED = {
    "insider": {"monthly": 9900, "annual": 90000, "trial_days": 7,
                "annual_pm": 75, "save_pct": 24},
    "pro":     {"monthly": 14900, "annual": 130800, "trial_days": 7,
                "annual_pm": 109, "save_pct": 27},
}

TERMINAL_INDICATORS = {
    "core_count": 21,
    "advanced_total": 31,
    "access": {"free": 1, "insider": 15, "pro": 31},
}


def _catalog() -> dict:
    with (ROOT / "config" / "plans.yml").open() as fh:
        return yaml.safe_load(fh)


def test_catalog_locked_pricing():
    cat = _catalog()
    assert cat["schema"] == "plans_catalog.v1"
    assert cat["currency"] == "usd"
    for key, want in LOCKED.items():
        prod = cat["products"][key]
        assert int(prod["trial_days"]) == want["trial_days"], f"{key}: trial drifted"
        prices = prod["prices"]
        assert int(prices["monthly"]["unit_amount"]) == want["monthly"], f"{key}: monthly drifted"
        assert int(prices["annual"]["unit_amount"]) == want["annual"], f"{key}: annual drifted"
        assert prices["monthly"]["lookup_key"] == f"{key}_2026_v2_monthly"
        assert prices["annual"]["lookup_key"] == f"{key}_2026_v2_annual"
        assert prices["monthly"]["interval"] == "month"
        assert prices["annual"]["interval"] == "year"


def test_terminal_indicator_access_is_explicit_and_cumulative():
    """Pricing copy must describe the same tier ladder the Terminal enforces."""
    indicator_access = _catalog()["terminal_indicators"]
    assert indicator_access == TERMINAL_INDICATORS
    assert list(indicator_access["access"].values()) == sorted(
        indicator_access["access"].values()
    )
    assert indicator_access["access"]["pro"] == indicator_access["advanced_total"]


def test_savings_badges_derive_from_config():
    """Replicates the §2.1 display-law formula build_site._plans_view_model uses."""
    cat = _catalog()
    for key, want in LOCKED.items():
        m = int(cat["products"][key]["prices"]["monthly"]["unit_amount"])
        a = int(cat["products"][key]["prices"]["annual"]["unit_amount"])
        assert round(a / 12 / 100) == want["annual_pm"]
        assert round((m - a / 12) / m * 100) == want["save_pct"]


def test_founding_pro_is_limited_annual_pro_offer():
    offer = _catalog()["offers"]["founding_pro"]
    assert offer["tier"] == "pro" and offer["interval"] == "annual"
    assert int(offer["unit_amount"]) == 90000
    assert round(offer["unit_amount"] / 12 / 100) == 75
    assert int(130800 - offer["unit_amount"]) == 40800
    assert offer["base_lookup_key"] == "pro_2026_v2_annual"
    assert int(offer["base_unit_amount"]) == 130800
    assert int(offer["max_redemptions"]) == 2000
    assert int(offer["public_count_threshold"]) == 25
    assert offer["entitlement_metadata_key"] == "mm_founding_pro_entitled"
    assert offer["duration"] == "forever"


def test_billing_maps_tiers_trials_and_lookup_keys():
    """app/billing.py resolves both paid tiers, both intervals, and 7-day trials."""
    from app import billing

    for tier in ("insider", "pro"):
        assert billing._tier_trial_days(tier) == 7
        for interval in ("monthly", "annual"):
            lk = billing._tier_to_lookup_key(tier, interval)
            assert lk == f"{tier}_2026_v2_{interval}"
    lk2t = billing._lookup_key_to_tier()
    assert lk2t == {
        "insider_2026_v2_monthly": "insider", "insider_2026_v2_annual": "insider",
        "insider_2026_monthly": "insider", "insider_2026_annual": "insider",
        "insider_monthly": "insider", "insider_annual": "insider",
        "pro_2026_v2_monthly": "pro", "pro_2026_v2_annual": "pro",
        "pro_2026_monthly": "pro", "pro_2026_annual": "pro",
        "pro_monthly": "pro", "pro_annual": "pro",
    }
    assert billing._tier_features("pro") == ["site_full", "terminal_live_options", "chat_opus"]
    assert billing._tier_features("insider") == ["site_full", "terminal_live_options"]


def test_founding_price_anchor_survives_a_future_regular_pro_increase(monkeypatch):
    """A returning founder must stay at $900 when the public Pro rack price changes."""
    from app import billing

    future = copy.deepcopy(_catalog())
    future["products"]["pro"]["prices"]["annual"] = {
        "lookup_key": "pro_2027_annual",
        "unit_amount": 180000,
        "interval": "year",
    }
    monkeypatch.setattr(billing, "_CATALOG", future)
    assert billing._tier_to_lookup_key("pro", "annual") == "pro_2027_annual"
    assert billing._purchase_lookup_key(
        "pro", "annual", "founding_pro") == "pro_2026_v2_annual"


def test_billing_endpoints_mounted(monkeypatch):
    """TestClient hits — 401 (auth) / 503 (unconfigured), never 404."""
    from fastapi.testclient import TestClient
    from app import billing
    from app.main import app

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    monkeypatch.delenv("STRIPE_SECRET_KEY", raising=False)
    billing._PROMO_CACHE.clear()
    client = TestClient(app)

    r = client.post("/api/billing/checkout", json={"tier": "insider", "interval": "annual"})
    assert r.status_code == 401, f"checkout should require auth, got {r.status_code}"
    r = client.get("/api/billing/portal")
    assert r.status_code == 401, f"portal should require auth, got {r.status_code}"
    r = client.get("/api/billing/offers/founding_pro")
    assert r.status_code == 503, f"unprovisioned public offer should 503, got {r.status_code}"
    r = client.post("/api/billing/webhook", content=b"{}",
                    headers={"stripe-signature": "t=0,v1=bad"})
    assert r.status_code == 503, f"webhook without secret should 503, got {r.status_code}"
