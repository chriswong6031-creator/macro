"""Premium /api surfaces enforce the same site_full authority as static files."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app import paywall
from app.main import app, require_user

client = TestClient(app)
UID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv("PAYWALL_ENABLED", raising=False)
    paywall._ENT_CACHE.clear()
    app.dependency_overrides[require_user] = lambda: {"id": UID, "email": "u@example.test"}
    yield
    app.dependency_overrides.clear()
    paywall._ENT_CACHE.clear()


def test_ask_keeps_registered_behavior_while_paid_switch_off(monkeypatch):
    monkeypatch.setattr(
        "engine.neuralweb.ask_brain.ask",
        lambda **kwargs: {"ok": True, "mode": "test"},
    )
    r = client.post("/api/ask", json={"question": "What is the current regime?"})
    assert r.status_code == 200
    assert r.json()["mode"] == "test"


def test_ask_refuses_user_without_site_full_when_armed(monkeypatch):
    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "free", "status": "none", "features": []}, True),
    )
    r = client.post("/api/ask", json={"question": "Show the neural web state"})
    assert r.status_code == 403
    assert r.json()["detail"]["locked"] is True
    assert r.json()["detail"]["required_feature"] == "site_full"


def test_ask_allows_active_site_full_when_armed(monkeypatch):
    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "essential", "status": "active", "features": ["site_full"]}, True),
    )
    monkeypatch.setattr(
        "engine.neuralweb.ask_brain.ask",
        lambda **kwargs: {"ok": True, "mode": "test"},
    )
    r = client.post("/api/ask", json={"question": "Show the neural web state"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
