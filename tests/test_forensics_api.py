"""Authenticated API tests for the private Filing Forensics state route."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="forensics API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.forensics as forensics_api  # noqa: E402
from engine.fundamental_forensics.private_state import STATE_SCHEMA  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def _blob() -> bytes:
    document = {
        "schema": STATE_SCHEMA,
        "generated_at": "2026-08-01T12:00:00Z",
        "companies": {"AAPL": {"ticker": "AAPL", "findings": []}},
    }
    return gzip.compress(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        mtime=0,
    )


@pytest.fixture
def entitled_client():
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {
        "id": "paid-user",
        "tier": "pro",
    }
    with TestClient(app) as client:
        yield client


def test_missing_private_state_returns_503(entitled_client, monkeypatch) -> None:
    monkeypatch.setattr(forensics_api, "load_state_blob", lambda _root: None)
    response = entitled_client.get("/api/forensics/state")
    assert response.status_code == 503
    assert response.json() == {"detail": "forensics state temporarily unavailable"}


def test_valid_state_returns_gzip_with_private_no_store_headers(entitled_client, monkeypatch) -> None:
    expected = _blob()
    monkeypatch.setattr(forensics_api, "load_state_blob", lambda _root: expected)
    response = entitled_client.get("/api/forensics/state")
    assert response.status_code == 200
    assert response.content == expected
    assert response.headers["content-type"] == "application/gzip"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"] == 'inline; filename="forensics-state.json.gz"'
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"


def test_route_declares_the_site_full_dependency() -> None:
    route = next(route for route in forensics_api.router.routes if route.path == "/api/forensics/state")
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
    assert forensics_api.require_site_full_user in dependency_calls


def test_site_full_wrapper_checks_user_then_entitlement(monkeypatch) -> None:
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
    assert forensics_api.require_site_full_user("Bearer paid-token") == entitled
    assert calls == [
        ("require_user", "Bearer paid-token"),
        ("enforce_site_full", (user, True)),
    ]


def test_free_user_is_denied_even_while_global_paywall_is_off(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setenv("PAYWALL_ENABLED", "0")
    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})
    monkeypatch.setattr(paywall_mod, "_entitled", lambda _user_id, _feature: (False, "free"))

    with pytest.raises(HTTPException) as exc_info:
        forensics_api.require_site_full_user("Bearer signed-in-free-user")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["required_feature"] == "site_full"


def test_site_full_denial_happens_before_private_state_read(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(402, "site_full required")

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)

    def state_must_not_be_read(_root):
        raise AssertionError("state read must happen only after entitlement")

    monkeypatch.setattr(forensics_api, "load_state_blob", state_must_not_be_read)
    app = FastAPI()
    app.include_router(forensics_api.router)
    with TestClient(app) as client:
        response = client.get(
            "/api/forensics/state",
            headers={"Authorization": "Bearer free-token"},
        )
    assert response.status_code == 402
    assert response.json() == {"detail": "site_full required"}


def test_production_app_mounts_the_authenticated_forensics_route() -> None:
    import app.main as main_mod

    # Current FastAPI stores include_router() entries as lazy _IncludedRouter
    # nodes whose own ``path`` is None.  OpenAPI expansion is the stable public
    # seam and proves the production app actually resolves the child route.
    assert "/api/forensics/state" in main_mod.app.openapi().get("paths", {}), (
        "app.main must include app.forensics.router or the paid API is unreachable"
    )


def test_private_research_r2_credentials_are_delivered_to_macro_api_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-api-secrets.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "R2_RESEARCH_ENDPOINT",
        "R2_RESEARCH_ACCESS_KEY_ID",
        "R2_RESEARCH_SECRET_ACCESS_KEY",
        "R2_RESEARCH_BUCKET",
    ):
        assert f"secrets.{name}" in workflow
        assert f"_add {name} " in workflow
    assert (
        'grep -vE "^R2_RESEARCH_(ENDPOINT|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)="'
        in workflow
    )
    # The second job updates macro-admin. Filing Forensics object credentials
    # belong only in the first macro-api delivery block.
    assert workflow.count("secrets.R2_RESEARCH_SECRET_ACCESS_KEY") == 1
