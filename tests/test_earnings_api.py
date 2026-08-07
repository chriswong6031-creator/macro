"""Authenticated transport tests for member Earnings Wire records."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="earnings API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.earnings as earnings_api  # noqa: E402
from engine.earnings_narrative.private_publication import (  # noqa: E402
    EarningsPrivatePublicationError,
    EarningsPrivateRecordNotFound,
)


ROOT = Path(__file__).resolve().parents[1]
PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _assert_private(response) -> None:
    for name, value in PRIVATE_HEADERS.items():
        assert response.headers[name] == value


@pytest.fixture
def entitled_client(monkeypatch):
    earnings_api._reset_private_caches()
    store = object()
    manifest = {"generation_id": "earnpriv_" + "a" * 32}
    monkeypatch.setattr(earnings_api, "_build_store", lambda: store)
    monkeypatch.setattr(
        earnings_api,
        "_current_manifest",
        lambda candidate, *, force=False: manifest,
    )
    app = FastAPI()
    app.include_router(earnings_api.router)
    app.dependency_overrides[earnings_api.require_site_full_user] = lambda: {
        "id": "paid-user",
        "tier": "essential",
    }
    with TestClient(app) as client:
        yield client, store, manifest
    earnings_api._reset_private_caches()


def test_member_record_returns_only_after_paid_dependency(entitled_client, monkeypatch) -> None:
    client, store, manifest = entitled_client
    expected = {
        "schema": "earnings.tier_payload/v1",
        "page": "earnings_wire_article",
        "slug": "aapl-2026q1-call-record",
        "required_tier": "essential",
        "public_facts": 2,
        "locked_facts": 3,
        "facts_html": "<article>member fact</article>",
        "receipt_rows_html": "<tr><td>receipt</td></tr>",
    }

    def load(candidate, slug, *, manifest: object):
        assert candidate is store
        assert slug == expected["slug"]
        assert manifest is entitled_client[2]
        return expected

    monkeypatch.setattr(earnings_api, "load_private_record", load)
    response = client.get(f"/api/earnings/v1/records/{expected['slug']}")
    assert response.status_code == 200
    assert response.json() == expected
    _assert_private(response)


def test_member_record_maps_absence_and_store_failure_without_detail(entitled_client, monkeypatch) -> None:
    client, _store, _manifest = entitled_client
    monkeypatch.setattr(
        earnings_api,
        "load_private_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(EarningsPrivateRecordNotFound("secret")),
    )
    missing = client.get("/api/earnings/v1/records/aapl-2026q1-call-record")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "earnings record not found"}
    _assert_private(missing)

    monkeypatch.setattr(
        earnings_api,
        "load_private_record",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(EarningsPrivatePublicationError("bucket detail")),
    )
    failed = client.get("/api/earnings/v1/records/aapl-2026q1-call-record")
    assert failed.status_code == 503
    assert failed.json() == {"detail": "earnings evidence temporarily unavailable"}
    assert "bucket" not in failed.text
    _assert_private(failed)


def test_valid_new_slug_forces_one_pointer_refresh_before_404(
    entitled_client, monkeypatch,
) -> None:
    client, store, stale_manifest = entitled_client
    fresh_manifest = {"generation_id": "earnpriv_" + "b" * 32}
    manifest_reads: list[bool] = []
    record_reads: list[object] = []

    def current(candidate, *, force=False):
        assert candidate is store
        manifest_reads.append(force)
        return fresh_manifest if force else stale_manifest

    def load(candidate, slug, *, manifest):
        assert candidate is store
        assert slug == "aapl-2026q2-call-record"
        record_reads.append(manifest)
        if manifest is stale_manifest:
            raise EarningsPrivateRecordNotFound("stale pointer cache")
        return {
            "schema": "earnings.tier_payload/v1",
            "page": "earnings_wire_article",
            "slug": slug,
            "required_tier": "essential",
            "public_facts": 2,
            "locked_facts": 1,
            "facts_html": "<article>new member fact</article>",
            "receipt_rows_html": "<tr><td>new receipt</td></tr>",
        }

    monkeypatch.setattr(earnings_api, "_current_manifest", current)
    monkeypatch.setattr(earnings_api, "load_private_record", load)
    response = client.get("/api/earnings/v1/records/aapl-2026q2-call-record")
    assert response.status_code == 200
    assert manifest_reads == [False, True]
    assert record_reads == [stale_manifest, fresh_manifest]
    _assert_private(response)


def test_invalid_and_encoded_path_probes_stay_private(entitled_client) -> None:
    client, _store, _manifest = entitled_client
    invalid = client.get("/api/earnings/v1/records/UPPERCASE")
    assert invalid.status_code == 400
    _assert_private(invalid)
    encoded = client.get("/api/earnings/v1/records/aapl%2Fescape")
    assert encoded.status_code == 404
    _assert_private(encoded)


def test_denial_happens_before_private_store_construction(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "free-user"})

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(403, {"locked": True, "required_feature": "site_full"})

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)
    monkeypatch.setattr(
        earnings_api,
        "_build_store",
        lambda: (_ for _ in ()).throw(AssertionError("private store opened before entitlement")),
    )
    app = FastAPI()
    app.include_router(earnings_api.router)
    with TestClient(app) as client:
        response = client.get(
            "/api/earnings/v1/records/aapl-2026q1-call-record",
            headers={"Authorization": "Bearer free-token"},
        )
    assert response.status_code == 403
    assert response.json()["detail"]["required_feature"] == "site_full"
    _assert_private(response)


def test_production_app_mounts_private_earnings_route() -> None:
    import app.main as main_mod

    assert "/api/earnings/v1/records/{slug}" in main_mod.app.openapi().get("paths", {})


# Every paid route this router owns, in the form a client actually requests.
# The private catch-all is deliberately include_in_schema=False, so the OpenAPI
# assertion above can never see it: only a real request proves it is mounted.
_MOUNTED_PAID_PATHS = (
    "/api/earnings/v1/records/aapl-2026q1-call-record",
    "/api/earnings/v1/records/malformed/extra/segments",
)


def test_every_paid_route_is_mounted_on_the_assembled_production_app() -> None:
    """A dropped router presents only as a 404 on a paid endpoint, never as an error.

    Mounting used to be wrapped in ``except ImportError: pass``, so a renamed
    dependency or a package missing on the VPS deleted both entitled routes with
    no startup failure and no log line.  Assert what production proves:
    unauthenticated requests reach the entitlement boundary (401) instead of
    falling through to the app's 404.
    """
    import app.main as main_mod

    # No context manager on purpose: mounting is import-time state, and running
    # the app's lifespan here would start its background warm threads.
    client = TestClient(main_mod.app, raise_server_exceptions=False)
    statuses = {path: client.get(path).status_code for path in _MOUNTED_PAID_PATHS}
    assert statuses == dict.fromkeys(_MOUNTED_PAID_PATHS, 401)

    # Control: 404 must still be reachable on this prefix, or the assertion
    # above would pass for a reason that has nothing to do with mounting.
    assert client.get("/api/earnings/not-a-route").status_code == 404


def test_router_wiring_fails_startup_loudly_instead_of_swallowing_importerror() -> None:
    """Pin the wiring shape, not just today's happy import.

    The route test above only fails once the import is genuinely broken.  This
    one fails the moment the mount is put back inside a ``try``: paid product
    contracts fail startup loudly here, exactly as the BioCatalyst block does.
    """
    module = ast.parse((ROOT / "app" / "main.py").read_text(encoding="utf-8"))

    top_level_import = [
        node
        for node in module.body
        if isinstance(node, ast.ImportFrom) and node.module == "app.earnings"
    ]
    top_level_include = [
        node
        for node in module.body
        if isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Attribute)
        and node.value.func.attr == "include_router"
        and any(
            isinstance(arg, ast.Name) and arg.id == "earnings_router"
            for arg in node.value.args
        )
    ]
    assert top_level_import, (
        "app/main.py must import app.earnings at module level; an import nested "
        "in a try/except can be swallowed into a silent 404 on a paid route"
    )
    assert top_level_include, (
        "app/main.py must call app.include_router(earnings_router) at module "
        "level so a wiring error fails startup instead of dropping both paid routes"
    )


def test_public_client_fetches_api_with_supabase_bearer() -> None:
    script = (ROOT / "templates" / "earnings_wire" / "earnings-wire.js").read_text(
        encoding="utf-8"
    )
    article = (
        ROOT / "templates" / "earnings_wire" / "earnings_wire_article.html.j2"
    ).read_text(encoding="utf-8")
    assert "'Authorization':'Bearer '+token" in script
    assert "sb.auth.getSession()" in script
    assert "fetch(gate.payload" in script
    assert "earnings-gate-state" in article
    assert "/premiumdata/" not in script


def test_workflow_publishes_private_r2_before_staging_public_html() -> None:
    workflow = (ROOT / ".github" / "workflows" / "earnings-public-wire.yml").read_text(
        encoding="utf-8"
    )
    assert "R2_RESEARCH_BUCKET" in workflow
    assert "--private-out-dir" in workflow
    assert "scripts.publish_earnings_private_store" in workflow
    assert "git add site/stocks/earnings" in workflow
    assert "git add site/stocks/earnings site/premiumdata/earnings" not in workflow
    assert "git clean -fd -- site/stocks/earnings site/premiumdata/earnings" not in workflow
    assert workflow.index("scripts.publish_earnings_private_store") < workflow.index(
        "git add site/stocks/earnings"
    )
    assert "/site/premiumdata/earnings/" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_private_research_credentials_already_reach_macro_api() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-api-secrets.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "R2_RESEARCH_ENDPOINT",
        "R2_RESEARCH_ACCESS_KEY_ID",
        "R2_RESEARCH_SECRET_ACCESS_KEY",
        "R2_RESEARCH_BUCKET",
    ):
        assert name in workflow


def test_private_publication_changes_restart_macro_api() -> None:
    update = (ROOT / "app" / "deploy" / "update.sh").read_text(encoding="utf-8")
    assert "private_publication" in update
