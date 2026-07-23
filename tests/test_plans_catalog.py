"""tests/test_plans_catalog.py — W0 pricing-alignment guard (onboarding masterplan §2).

Pins config/plans.yml to the LOCKED 2026-07-23 pricing so config, the Stripe
sandbox objects (scripts/stripe_bootstrap.py re-creates drifted prices from this
file), and the landing page can't silently diverge:

    Insider  $69/mo · $588/yr ($49/mo-equivalent, save 29%) · 7-day trial
    Pro      $99/mo · $828/yr ($69/mo-equivalent, save 30%) · 7-day trial

Also verifies the billing endpoints are mounted by hitting them with a TestClient
(401/503 responses). NOTE (repo memory fastapi-includedrouter-route-verify): this
FastAPI wraps routers in _IncludedRouter, so endpoint existence is verified via
TestClient RESPONSES, never by scanning app.routes for .path.

Run:
    python -m pytest tests/test_plans_catalog.py -v
"""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# The locked table (onboarding masterplan §2; landing templates/index.html shows the same).
LOCKED = {
    "insider": {"monthly": 6900, "annual": 58800, "trial_days": 7,
                "annual_pm": 49, "save_pct": 29},
    "pro":     {"monthly": 9900, "annual": 82800, "trial_days": 7,
                "annual_pm": 69, "save_pct": 30},
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
        assert prices["monthly"]["lookup_key"] == f"{key}_monthly"
        assert prices["annual"]["lookup_key"] == f"{key}_annual"
        assert prices["monthly"]["interval"] == "month"
        assert prices["annual"]["interval"] == "year"


def test_savings_badges_derive_from_config():
    """Replicates the §2.1 display-law formula build_site._plans_view_model uses."""
    cat = _catalog()
    for key, want in LOCKED.items():
        m = int(cat["products"][key]["prices"]["monthly"]["unit_amount"])
        a = int(cat["products"][key]["prices"]["annual"]["unit_amount"])
        assert round(a / 12 / 100) == want["annual_pm"]
        assert round((m - a / 12) / m * 100) == want["save_pct"]


def test_billing_maps_tiers_trials_and_lookup_keys():
    """app/billing.py resolves both paid tiers, both intervals, and 7-day trials."""
    from app import billing

    for tier in ("insider", "pro"):
        assert billing._tier_trial_days(tier) == 7
        for interval in ("monthly", "annual"):
            lk = billing._tier_to_lookup_key(tier, interval)
            assert lk == f"{tier}_{interval}"
    lk2t = billing._lookup_key_to_tier()
    assert lk2t == {
        "insider_monthly": "insider", "insider_annual": "insider",
        "pro_monthly": "pro", "pro_annual": "pro",
    }
    assert billing._tier_features("pro") == ["site_full", "terminal_live_options", "chat_opus"]
    assert billing._tier_features("insider") == ["site_full", "terminal_live_options"]


def test_billing_endpoints_mounted(monkeypatch):
    """TestClient hits — 401 (auth) / 503 (unconfigured), never 404."""
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    client = TestClient(app)

    r = client.post("/api/billing/checkout", json={"tier": "insider", "interval": "annual"})
    assert r.status_code == 401, f"checkout should require auth, got {r.status_code}"
    r = client.get("/api/billing/portal")
    assert r.status_code == 401, f"portal should require auth, got {r.status_code}"
    r = client.post("/api/billing/webhook", content=b"{}",
                    headers={"stripe-signature": "t=0,v1=bad"})
    assert r.status_code == 503, f"webhook without secret should 503, got {r.status_code}"
