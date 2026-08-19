"""Transport-layer contract tests for ``GET /api/prophet/lab/v1``.

These tests exercise auth, the kill switch, response framing, and app.main
router registration in isolation from the projection itself (that is
exhaustively covered, fixture-by-fixture, in tests/test_prophet_lab.py).
``app.prophet_lab.build_lab_response`` is monkeypatched to a canned payload
throughout so a failure here can only be a transport-layer regression.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="Prophet Lab API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.prophet_lab as prophet_lab_api  # noqa: E402
from engine.prophet_lab.contracts import ALL_FALSE_AUTHORITY, KILL_SWITCH_ENV, SCHEMA_LAB_BOARD  # noqa: E402

_PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _assert_private_headers(response) -> None:
    for name, value in _PRIVATE_HEADERS.items():
        assert response.headers.get(name) == value


def _canned_payload() -> dict:
    return {
        "schema": SCHEMA_LAB_BOARD,
        "health": {"radar_spool_readable": False},
        "authority": dict(ALL_FALSE_AUTHORITY),
        "boards": {},
    }


@pytest.fixture()
def app_client(monkeypatch):
    monkeypatch.setattr(prophet_lab_api, "build_lab_response", lambda roots: _canned_payload())
    app = FastAPI()
    app.include_router(prophet_lab_api.router)
    app.dependency_overrides[prophet_lab_api.require_site_full_user] = lambda: {"id": "u-paid"}
    with TestClient(app) as client:
        yield client


# ---------------------------------------------------------------------------
# happy path
# ---------------------------------------------------------------------------
def test_paid_user_gets_200_with_frozen_schema_and_all_false_authority(app_client) -> None:
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 200
    body = response.json()
    assert body["schema"] == SCHEMA_LAB_BOARD
    assert body["authority"] == ALL_FALSE_AUTHORITY
    assert all(v is False for v in body["authority"].values())
    _assert_private_headers(response)


# ---------------------------------------------------------------------------
# auth: anonymous -> 401, free tier -> 403, paid -> 200 (house pattern)
# ---------------------------------------------------------------------------
def test_anonymous_caller_is_401(monkeypatch) -> None:
    monkeypatch.setattr(prophet_lab_api, "build_lab_response", lambda roots: _canned_payload())
    import app.main as main_mod

    monkeypatch.setattr(
        main_mod,
        "require_user",
        lambda _authorization: (_ for _ in ()).throw(HTTPException(401, "missing bearer token")),
    )
    app = FastAPI()
    app.include_router(prophet_lab_api.router)
    with TestClient(app) as client:
        response = client.get("/api/prophet/lab/v1")
    assert response.status_code == 401
    _assert_private_headers(response)


def test_free_tier_caller_is_403(monkeypatch) -> None:
    monkeypatch.setattr(prophet_lab_api, "build_lab_response", lambda roots: _canned_payload())
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})
    monkeypatch.setattr(paywall_mod, "_entitled", lambda _user_id, _feature: (False, "free"))
    app = FastAPI()
    app.include_router(prophet_lab_api.router)
    with TestClient(app) as client:
        response = client.get(
            "/api/prophet/lab/v1", headers={"Authorization": "Bearer free-token"},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["required_feature"] == "site_full"
    _assert_private_headers(response)


def test_paid_caller_authenticates_then_entitles_in_order(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    calls: list[tuple[str, object]] = []
    user = {"id": "u-paid"}
    entitled = {"id": "u-paid", "tier": "pro"}

    def require_user(authorization):
        calls.append(("require_user", authorization))
        return user

    def enforce_site_full(candidate, *, always=False):
        calls.append(("enforce_site_full", (candidate, always)))
        return entitled

    monkeypatch.setattr(main_mod, "require_user", require_user)
    monkeypatch.setattr(paywall_mod, "enforce_site_full", enforce_site_full)
    assert prophet_lab_api.require_site_full_user("Bearer paid-token") == entitled
    assert calls == [
        ("require_user", "Bearer paid-token"),
        ("enforce_site_full", (user, True)),
    ]


def test_402_from_enforce_site_full_propagates_with_private_headers(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(402, "site_full required", headers={"Retry-After": "60"})

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)
    with pytest.raises(HTTPException) as excinfo:
        prophet_lab_api.require_site_full_user("Bearer free-token")
    assert excinfo.value.status_code == 402
    assert excinfo.value.headers["Retry-After"] == "60"
    assert excinfo.value.headers.get("Cache-Control") == "private, no-store"
    assert excinfo.value.headers.get("Vary") == "Authorization"


# ---------------------------------------------------------------------------
# kill switch (PROPHET_LAB_DISABLED) — independent of Radar's own switches
# ---------------------------------------------------------------------------
def test_kill_switch_returns_503_and_skips_the_projection(app_client, monkeypatch) -> None:
    def _boom(roots):
        raise AssertionError("projection must not run while PROPHET_LAB_DISABLED=1")

    monkeypatch.setattr(prophet_lab_api, "build_lab_response", _boom)
    monkeypatch.setenv(KILL_SWITCH_ENV, "1")
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 503
    body = response.json()
    assert body["error"] == "prophet_lab_disabled"
    _assert_private_headers(response)


@pytest.mark.parametrize("off_value", ["0", "false", "False", ""])
def test_kill_switch_off_values_serve_normally(app_client, monkeypatch, off_value) -> None:
    monkeypatch.setenv(KILL_SWITCH_ENV, off_value)
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 200


def test_kill_switch_is_independent_of_radar_live_switches(app_client, monkeypatch) -> None:
    # Radar's own kill switch must have zero effect on the Lab API — LAB-0 §5:
    # "Kill switch: PROPHET_LAB_DISABLED stands the API down independently of
    # Radar's own ENTRY_RADAR_LIVE_ENABLE".
    monkeypatch.setenv("ENTRY_RADAR_LIVE_DISABLED", "1")
    monkeypatch.delenv(KILL_SWITCH_ENV, raising=False)
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# a failed projection is a clean 503, never a 500
# ---------------------------------------------------------------------------
def test_projection_failure_is_503_not_500(app_client, monkeypatch) -> None:
    def _boom(roots):
        raise RuntimeError("boom")

    monkeypatch.setattr(prophet_lab_api, "build_lab_response", _boom)
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 503
    assert response.json()["error"] == "prophet_lab_unavailable"
    _assert_private_headers(response)


# ---------------------------------------------------------------------------
# app.main registration
# ---------------------------------------------------------------------------
def test_route_declares_the_paid_dependency() -> None:
    route_dependencies = {
        route.path: {dependency.call for dependency in route.dependant.dependencies}
        for route in prophet_lab_api.router.routes
    }
    assert prophet_lab_api.require_site_full_user in route_dependencies["/api/prophet/lab/v1"]


def test_route_is_mounted_on_the_production_app() -> None:
    import app.main as main_mod

    public_paths = main_mod.app.openapi().get("paths", {})
    assert "/api/prophet/lab/v1" in public_paths
