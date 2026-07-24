"""Hermetic contract tests for the fail-closed paid static-site wall."""
from __future__ import annotations

from fastapi.testclient import TestClient
import pytest

from app import paywall
from app.main import app

client = TestClient(app, follow_redirects=False)
UID = "11111111-1111-1111-1111-111111111111"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.delenv("PAYWALL_ENABLED", raising=False)
    monkeypatch.delenv("PAYWALL_GRACE_SECONDS", raising=False)
    monkeypatch.delenv("PAYWALL_ENTITLEMENT_CACHE_SECONDS", raising=False)
    paywall._AUTH_CACHE.clear()
    paywall._ENT_CACHE.clear()
    paywall._CONFIG_CACHE = None


def _check(path="/neuralwebdata/ruling_graph.json", kind="asset", cookies=None):
    return client.get(
        "/api/paywall/check",
        headers={"X-Original-Uri": path, "X-Original-Kind": kind},
        cookies=cookies or {},
    )


def _arm(monkeypatch):
    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: "tok")
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: UID)


def test_staged_off_allows_premium_but_is_never_cacheable():
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "off"
    assert r.headers["cache-control"] == "private, no-store"


def test_internal_preview_is_404_even_while_switch_off():
    r = _check("/_mockup_research_vault.html", "document")
    assert r.status_code == 404
    assert r.headers["x-paywall"] == "not-found"


def test_free_registered_path_does_not_require_paid_feature(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_fresh_uid", lambda token: (_ for _ in ()).throw(AssertionError))
    assert _check("/macro.html", "document").status_code == 204
    assert _check("/news/latest.json", "asset").status_code == 204


def test_active_site_full_allows(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "insider", "status": "active", "features": ["site_full"]}, True),
    )
    r = _check()
    assert r.status_code == 204
    assert r.headers["x-paywall"] == "allow-insider"


@pytest.mark.parametrize(
    "row",
    [
        {"tier": "free", "status": "active", "features": []},
        {"tier": "insider", "status": "past_due", "features": ["site_full"]},
        {"tier": "pro", "status": "active", "features": []},
        {"tier": "pro", "status": "canceled", "features": ["site_full"]},
    ],
)
def test_non_entitled_rows_fail_closed(monkeypatch, row):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_store_entitlement", lambda uid: (row, True))
    r = _check()
    assert r.status_code == 403
    assert r.json()["locked"] is True
    assert r.json()["required_feature"] == "site_full"


def test_document_denial_is_self_contained_bilingual_html(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(
        paywall,
        "_store_entitlement",
        lambda uid: ({"tier": "free", "status": "none", "features": []}, True),
    )
    r = _check("/committee.html", "document")
    assert r.status_code == 403
    assert "Insider members" in r.text
    assert "会员" in r.text
    assert "text/html" in r.headers["content-type"]
    assert r.headers["cache-control"] == "private, no-store"


def test_missing_or_invalid_auth_never_uses_entitlement_grace(monkeypatch):
    monkeypatch.setenv("PAYWALL_ENABLED", "1")
    monkeypatch.setattr("app.main._mm_supabase_access_token", lambda request: None)
    paywall._ENT_CACHE[UID] = paywall._EntitlementVerdict(True, "pro", "active", 1.0, 10**12)
    assert _check().status_code == 403


def test_store_outage_graces_only_recent_positive(monkeypatch):
    _arm(monkeypatch)
    clock = [1000.0]
    monkeypatch.setattr(paywall.time, "monotonic", lambda: clock[0])
    monkeypatch.setenv("PAYWALL_ENTITLEMENT_CACHE_SECONDS", "5")
    monkeypatch.setenv("PAYWALL_GRACE_SECONDS", "100")
    state = {"reachable": True}

    def store(uid):
        if state["reachable"]:
            return {"tier": "pro", "status": "trialing", "features": ["site_full"]}, True
        return None, False

    monkeypatch.setattr(paywall, "_store_entitlement", store)
    assert _check().status_code == 204
    state["reachable"] = False
    clock[0] += 6
    assert _check().status_code == 204
    paywall.invalidate_entitlement(UID)
    assert _check().status_code == 403


def test_policy_load_failure_denies(monkeypatch):
    _arm(monkeypatch)
    monkeypatch.setattr(paywall, "_load_config", lambda: (_ for _ in ()).throw(ValueError("bad")))
    assert _check().status_code == 403


@pytest.mark.parametrize("path", ["//evil.test/x", "/a/../index.html", "/bad%00.json", "/a\\b.json"])
def test_noncanonical_paths_deny(monkeypatch, path):
    _arm(monkeypatch)
    assert _check(path).status_code == 403
