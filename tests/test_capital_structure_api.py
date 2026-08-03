"""Offline contract tests for the paid observed-filing-state desk API.

The API is intentionally an artifact reader.  These tests pin its actual
product boundary: entitlement before a read, strict artifact validation,
stable issuer-key pagination, ticker ambiguity refusal, and private/noindex
headers even when the router is mounted without app.main's global middleware.
"""
from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

pytest.importorskip("fastapi", reason="capital structure API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import capital_structure as api  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
PREFIX = "/api/capital-structure/v1"


def _bundle() -> dict:
    """The committed projection is the compact production-shaped test fixture."""
    return json.loads((ROOT / "data" / "capital_structure" / "projection.json").read_text())


def test_clean_serving_requirements_include_the_projection_validator() -> None:
    requirements = (ROOT / "app" / "requirements.txt").read_text(encoding="utf-8")
    assert re.search(r"(?m)^jsonschema==4\.26\.0$", requirements), (
        "the serving venv installs only app/requirements.txt; drifting or omitting "
        "jsonschema invalidates the sealed authority runtime"
    )


def test_unknown_parser_runtime_does_not_silently_unmount_serving_router() -> None:
    probe = """
import sys

sys.implementation.cache_tag = "unsupported-cpython-312-api-mount-probe"
import app.main as serving
import engine.capital_structure.document_terms as document_terms

paths = set(serving.app.openapi()["paths"])
required = {
    "/api/capital-structure/v1/coverage",
    "/api/capital-structure/v1/overview",
}
if not required.issubset(paths):
    raise SystemExit(f"CAPITAL_STRUCTURE_ROUTER_UNMOUNTED:{sorted(paths)}")
try:
    document_terms._registered_parser(document_terms.PARSER_VERSION)
except ValueError as exc:
    if "runtime fingerprint is not released" not in str(exc):
        raise
    print("UNKNOWN_RUNTIME_ROUTER_MOUNTED_PARSER_REJECTED")
else:
    raise SystemExit("UNKNOWN_RUNTIME_PARSER_AUTHORITY_MINTED")
"""
    result = subprocess.run(
        [sys.executable, "-B", "-c", probe],
        cwd=ROOT,
        env={
            **os.environ,
            "MACRO_REPO": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(ROOT),
        },
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (
        "UNKNOWN_RUNTIME_ROUTER_MOUNTED_PARSER_REJECTED"
    )


@pytest.fixture()
def artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "projection.json"
    path.write_text(json.dumps(_bundle()), encoding="utf-8")
    monkeypatch.setattr(api, "PROJECTION_PATH", path)
    api._reset_cache()
    yield path
    api._reset_cache()


@pytest.fixture()
def client(artifact: Path):
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_site_full_user] = lambda: {"id": "paid-user"}
    with TestClient(app) as test_client:
        yield test_client


def _headers(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"


def test_coverage_is_entitled_private_and_context_only(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/coverage")
    assert response.status_code == 200
    _headers(response)
    body = response.json()
    assert body["schema"] == "capital_structure.projection_bundle.v1"
    assert body["authority"] == {
        "is_context_only": True,
        "rank_authority": False,
        "sizing_authority": False,
        "entry_authority": False,
        "prophet_authority": False,
    }
    assert "source_receipt" not in body
    assert "financing_probability" in body["unavailable"]


def test_overview_uses_stable_issuer_keyset_pagination(client: TestClient) -> None:
    first = client.get(f"{PREFIX}/overview", params={"limit": 2})
    assert first.status_code == 200
    _headers(first)
    page_one = first.json()
    assert page_one["page"] == {
        "cursor": None,
        "next_cursor": page_one["records"][-1]["issuer_id"],
        "limit": 2,
        "returned": 2,
        "total": len(_bundle()["records"]),
    }
    assert [row["issuer_id"] for row in page_one["records"]] == sorted(
        row["issuer_id"] for row in page_one["records"]
    )
    assert "timeline" not in page_one["records"][0]

    second = client.get(
        f"{PREFIX}/overview",
        params={"cursor": page_one["page"]["next_cursor"], "limit": 2},
    )
    assert second.status_code == 200
    page_two = second.json()
    assert page_two["page"]["cursor"] == page_one["page"]["next_cursor"]
    assert not ({row["issuer_id"] for row in page_one["records"]} & {
        row["issuer_id"] for row in page_two["records"]
    })


def test_overview_rejects_unknown_cursor_with_private_headers(client: TestClient) -> None:
    response = client.get(f"{PREFIX}/overview", params={"cursor": "sec:cik:does-not-exist"})
    assert response.status_code == 400
    _headers(response)
    assert response.json() == {"detail": "invalid cursor"}


def test_resolver_returns_stable_issuer_not_ticker_identity(client: TestClient) -> None:
    expected = next(
        record for record in _bundle()["records"] if record["identity"].get("ticker")
    )
    ticker = expected["identity"]["ticker"]
    response = client.get(f"{PREFIX}/issuers/resolve", params={"ticker": ticker.lower()})
    assert response.status_code == 200
    _headers(response)
    body = response.json()
    assert body["query"] == {"ticker": ticker}
    assert body["issuer"]["issuer_id"] == expected["issuer_id"]
    assert body["issuer"]["identity"]["ticker"] == ticker


def test_resolver_refuses_ambiguous_observed_ticker(client: TestClient, artifact: Path) -> None:
    bundle = _bundle()
    first, second = bundle["records"][0], bundle["records"][1]
    ticker = first["identity"]["ticker"] or first["identity"]["observed_tickers"][0]
    second["identity"]["observed_tickers"] = sorted(
        set(second["identity"]["observed_tickers"]) | {ticker}
    )
    artifact.write_text(json.dumps(bundle), encoding="utf-8")
    api._reset_cache()

    response = client.get(f"{PREFIX}/issuers/resolve", params={"ticker": ticker})
    assert response.status_code == 409
    _headers(response)
    detail = response.json()["detail"]
    assert detail["code"] == "ambiguous_ticker"
    assert detail["ticker"] == ticker
    assert {item["issuer_id"] for item in detail["matches"]} == {
        first["issuer_id"], second["issuer_id"],
    }


def test_dossier_and_event_pages_keep_original_event_evidence(client: TestClient) -> None:
    bundle = _bundle()
    record = max(bundle["records"], key=lambda row: len(row["timeline"]))
    issuer_id = record["issuer_id"]

    dossier = client.get(f"{PREFIX}/issuers/{issuer_id}")
    assert dossier.status_code == 200
    _headers(dossier)
    assert dossier.json()["issuer"]["issuer_id"] == issuer_id
    assert "timeline" not in dossier.json()["issuer"]

    events = client.get(f"{PREFIX}/issuers/{issuer_id}/events", params={"limit": 1})
    assert events.status_code == 200
    _headers(events)
    body = events.json()
    assert body["issuer"]["issuer_id"] == issuer_id
    assert body["page"]["total"] == len(record["timeline"])
    assert body["events"][0] == record["timeline"][0]
    assert set(body["events"][0]["source"]) == {
        "source_system", "source_id", "filing_url", "manifest_ids", "evidence",
    }
    if len(record["timeline"]) > 1:
        follow = client.get(
            f"{PREFIX}/issuers/{issuer_id}/events",
            params={"cursor": body["page"]["next_cursor"], "limit": 1},
        )
        assert follow.status_code == 200
        assert follow.json()["events"][0] == record["timeline"][1]


def test_invalid_or_explicitly_unavailable_artifacts_fail_closed(client: TestClient, artifact: Path) -> None:
    artifact.write_text("{not-json", encoding="utf-8")
    api._reset_cache()
    invalid = client.get(f"{PREFIX}/coverage")
    assert invalid.status_code == 503
    _headers(invalid)
    assert invalid.json() == {"detail": "capital structure observed filing state unavailable"}

    bundle = _bundle()
    bundle["coverage"]["state"] = "unavailable"
    artifact.write_text(json.dumps(bundle), encoding="utf-8")
    api._reset_cache()
    unavailable = client.get(f"{PREFIX}/coverage")
    assert unavailable.status_code == 503
    _headers(unavailable)


def test_wrapper_requires_entitlement_before_the_artifact_can_be_read(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    calls: list[tuple[str, object]] = []

    def require_user(authorization):
        calls.append(("require_user", authorization))
        return {"id": "u-free"}

    def deny(user, *, always=False):
        calls.append(("enforce_site_full", (user, always)))
        raise HTTPException(403, {"locked": True, "required_feature": "site_full"})

    monkeypatch.setattr(main_mod, "require_user", require_user)
    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)
    with pytest.raises(HTTPException) as exc_info:
        api.require_site_full_user("Bearer signed-in-free-user")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["required_feature"] == "site_full"
    assert exc_info.value.headers["Cache-Control"] == "private, no-store"
    assert calls == [
        ("require_user", "Bearer signed-in-free-user"),
        ("enforce_site_full", ({"id": "u-free"}, True)),
    ]


def test_site_full_denial_happens_before_projection_read(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(403, {"locked": True, "required_feature": "site_full"})

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)
    monkeypatch.setattr(
        api,
        "_load",
        lambda: (_ for _ in ()).throw(AssertionError("projection read must follow entitlement")),
    )
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as test_client:
        response = test_client.get(
            f"{PREFIX}/coverage",
            headers={"Authorization": "Bearer signed-in-free-user"},
        )
    assert response.status_code == 403
    _headers(response)
    assert response.json()["detail"]["required_feature"] == "site_full"


def test_routes_declare_always_on_site_full_and_production_mounts_them() -> None:
    route_paths = {route.path for route in api.router.routes}
    assert route_paths == {
        f"{PREFIX}/coverage",
        f"{PREFIX}/overview",
        f"{PREFIX}/issuers/resolve",
        f"{PREFIX}/issuers/{{issuer_id}}",
        f"{PREFIX}/issuers/{{issuer_id}}/events",
    }
    for route in api.router.routes:
        calls = {dependency.call for dependency in route.dependant.dependencies}
        assert api.require_site_full_user in calls

    import app.main as main_mod

    mounted = main_mod.app.openapi().get("paths", {})
    assert f"{PREFIX}/coverage" in mounted
    assert f"{PREFIX}/issuers/{{issuer_id}}/events" in mounted
