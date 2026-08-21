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


@pytest.mark.parametrize(
    "off_value",
    # review N4: the OFF set is case-insensitive, and "no"/"off" join the
    # original "0"/"false"/"" set.
    ["0", "false", "False", "FALSE", "", "no", "No", "NO", "off", "OFF", "Off"],
)
def test_kill_switch_off_values_serve_normally(app_client, monkeypatch, off_value) -> None:
    monkeypatch.setenv(KILL_SWITCH_ENV, off_value)
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 200


@pytest.mark.parametrize("on_value", ["1", "true", "TRUE", "yes", "banana"])
def test_kill_switch_any_unrecognized_or_truthy_value_disables(
    app_client, monkeypatch, on_value,
) -> None:
    # review N4: fail TOWARD disabled — an operator typo or an unexpected
    # value takes the Lab down rather than silently leaving it up.
    monkeypatch.setenv(KILL_SWITCH_ENV, on_value)
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 503
    assert response.json()["error"] == "prophet_lab_disabled"


def test_kill_switch_is_independent_of_radar_live_switches(app_client, monkeypatch) -> None:
    # Radar's own kill switch must have zero effect on the Lab API — LAB-0 §5:
    # "Kill switch: PROPHET_LAB_DISABLED stands the API down independently of
    # Radar's own ENTRY_RADAR_LIVE_ENABLE".
    monkeypatch.setenv("ENTRY_RADAR_LIVE_DISABLED", "1")
    monkeypatch.delenv(KILL_SWITCH_ENV, raising=False)
    response = app_client.get("/api/prophet/lab/v1")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# review S2 (cheap half) — the spool-source label the health block echoes
# ---------------------------------------------------------------------------
def test_resolve_roots_labels_the_primary_env_var(monkeypatch) -> None:
    monkeypatch.setenv("PROPHET_LAB_RADAR_SPOOL_DIR", "/tmp/prophet-lab-spool")
    monkeypatch.delenv("ENTRY_RADAR_SPOOL_DIR", raising=False)
    roots = prophet_lab_api._resolve_roots()  # noqa: SLF001
    assert roots.radar_spool_source_label == "PROPHET_LAB_RADAR_SPOOL_DIR"
    assert str(roots.radar_spool_dir) == "/tmp/prophet-lab-spool"


def test_resolve_roots_labels_the_fallback_env_var(monkeypatch) -> None:
    monkeypatch.delenv("PROPHET_LAB_RADAR_SPOOL_DIR", raising=False)
    monkeypatch.setenv("ENTRY_RADAR_SPOOL_DIR", "/tmp/entry-radar-spool")
    roots = prophet_lab_api._resolve_roots()  # noqa: SLF001
    assert roots.radar_spool_source_label == "ENTRY_RADAR_SPOOL_DIR"
    assert str(roots.radar_spool_dir) == "/tmp/entry-radar-spool"


def test_resolve_roots_labels_unconfigured_when_neither_env_var_is_set(monkeypatch) -> None:
    monkeypatch.delenv("PROPHET_LAB_RADAR_SPOOL_DIR", raising=False)
    monkeypatch.delenv("ENTRY_RADAR_SPOOL_DIR", raising=False)
    roots = prophet_lab_api._resolve_roots()  # noqa: SLF001
    assert roots.radar_spool_source_label == "unconfigured"
    assert roots.radar_spool_dir is None


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
    assert "/api/hub/prophet" in public_paths


# ---------------------------------------------------------------------------
# GET /api/hub/prophet — INTERNAL-ONLY (DEC:B1-PROPHET-PUBLIC-SPLIT)
#
# The guard reads request.client + headers directly rather than through a
# FastAPI Depends, so it is exercised as a plain function against hand-built
# Starlette Requests (deterministic — no TestClient transport ambiguity about
# what "client host" a test harness uses) and the route itself is exercised
# through TestClient with the guard monkeypatched, matching how every other
# test in this file isolates the transport layer from its dependency.
# ---------------------------------------------------------------------------
from starlette.requests import Request  # noqa: E402


def _hub_request(*, client_host: str | None, headers: dict[str, str] | None = None) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/hub/prophet",
        "raw_path": b"/api/hub/prophet",
        "query_string": b"",
        "headers": [
            (k.lower().encode("latin-1"), v.encode("latin-1"))
            for k, v in (headers or {}).items()
        ],
        "client": (client_host, 51000) if client_host is not None else None,
        "server": ("testserver", 80),
        "scheme": "http",
        "http_version": "1.1",
    }
    return Request(scope)


def test_hub_prophet_guard_allows_loopback_with_no_peer_header() -> None:
    assert prophet_lab_api._hub_prophet_authorized(  # noqa: SLF001
        _hub_request(client_host="127.0.0.1")
    ) is True
    assert prophet_lab_api._hub_prophet_authorized(  # noqa: SLF001
        _hub_request(client_host="::1")
    ) is True


def test_hub_prophet_guard_denies_loopback_carrying_a_peer_header() -> None:
    """Caddy's header_up REPLACES any inbound X-MM-Peer with the real TCP peer on
    every edge-proxied /api/* request, so its PRESENCE means this request came
    through the public edge even though the TCP peer still reads 127.0.0.1."""
    assert prophet_lab_api._hub_prophet_authorized(  # noqa: SLF001
        _hub_request(client_host="127.0.0.1", headers={"x-mm-peer": "203.0.113.7"})
    ) is False


def test_hub_prophet_guard_denies_non_loopback_peer() -> None:
    assert prophet_lab_api._hub_prophet_authorized(  # noqa: SLF001
        _hub_request(client_host="10.0.0.5")
    ) is False


def test_hub_prophet_guard_denies_when_client_is_unknown() -> None:
    assert prophet_lab_api._hub_prophet_authorized(  # noqa: SLF001
        _hub_request(client_host=None)
    ) is False


@pytest.fixture()
def hub_client(monkeypatch):
    app = FastAPI()
    app.include_router(prophet_lab_api.router)
    with TestClient(app) as client:
        yield client


def test_hub_prophet_denied_caller_gets_401_json_no_detail(hub_client, monkeypatch) -> None:
    monkeypatch.setattr(prophet_lab_api, "_hub_prophet_authorized", lambda request: False)
    response = hub_client.get("/api/hub/prophet")
    assert response.status_code == 401
    assert response.json() == {"error": "unauthorized"}


def test_hub_prophet_authorized_caller_gets_the_same_canonical_bytes(
    hub_client, monkeypatch, tmp_path
) -> None:
    index_path = tmp_path / "index.json"
    index_path.write_bytes(b'{"schema": "prophet.index/v1", "plans": []}')
    monkeypatch.setattr(prophet_lab_api, "_hub_prophet_authorized", lambda request: True)
    monkeypatch.setattr(
        prophet_lab_api,
        "_resolve_roots",
        lambda: prophet_lab_api.LabRoots(prophet_index_path=index_path),
    )
    response = hub_client.get("/api/hub/prophet")
    assert response.status_code == 200
    assert response.content == index_path.read_bytes()
    assert response.headers.get("content-type", "").startswith("application/json")
    assert response.headers.get("cache-control") == "no-store"


def test_hub_prophet_missing_index_file_is_503(hub_client, monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(prophet_lab_api, "_hub_prophet_authorized", lambda request: True)
    monkeypatch.setattr(
        prophet_lab_api,
        "_resolve_roots",
        lambda: prophet_lab_api.LabRoots(prophet_index_path=tmp_path / "missing.json"),
    )
    response = hub_client.get("/api/hub/prophet")
    assert response.status_code == 503
    assert response.json() == {"error": "prophet_index_unavailable"}


def test_hub_prophet_reuses_the_lab_routes_own_path_resolution(monkeypatch) -> None:
    """Both routes must serve ONE file — this pins that hub_prophet reads through
    the exact same _resolve_roots() helper lab_v1 uses, not a second invented path."""
    sentinel = object()
    calls: list[object] = []
    monkeypatch.setattr(
        prophet_lab_api,
        "_resolve_roots",
        lambda: calls.append(sentinel) or prophet_lab_api.LabRoots(prophet_index_path=None),
    )
    monkeypatch.setattr(prophet_lab_api, "_hub_prophet_authorized", lambda request: True)
    request = _hub_request(client_host="127.0.0.1")
    prophet_lab_api.hub_prophet(request)
    assert calls == [sentinel]
