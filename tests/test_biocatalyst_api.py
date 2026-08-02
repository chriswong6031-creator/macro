"""Adversarial contract tests for the paid BioCatalyst trial API.

The API is deliberately a read-only, fact-only edge over the worker-promoted
public generation.  These tests create a real v1.1 generation through the
worker fixture, then exercise the authentication, availability, and disclosure
boundaries without reaching private worker state or external services.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

import pytest

pytest.importorskip("fastapi", reason="BioCatalyst API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.biocatalyst as biocatalyst_api  # noqa: E402
from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256  # noqa: E402
import scripts.biocatalyst_worker as worker  # noqa: E402
from tests.test_biocatalyst_worker import (  # noqa: E402
    FakeCollectorFactory,
    MemoryStore,
    NOW,
    config as worker_config,
)


_PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}
_FORBIDDEN_KEY_FRAGMENTS = (
    "canonical_study",
    "canonical_content",
    "source_snapshot",
    "source_record_ref",
    "raw_object",
    "receipt",
    "object_key",
    "source_json_path",
    "manifest_sha",
    "generation_id",
    "snapshot_id",
    "query_sha",
)


def _assert_private_headers(response) -> None:
    for name, expected in _PRIVATE_HEADERS.items():
        assert response.headers[name] == expected
    assert response.headers["content-type"].startswith("application/json")


def _walk_keys(value: Any) -> Iterator[str]:
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk_keys(nested)


@pytest.fixture
def promoted_config(tmp_path: Path):
    """Publish a genuine v1.1 product projection by the worker's normal seam."""

    config = worker_config(tmp_path)
    result = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )
    assert result.status == "success"
    return config


@pytest.fixture
def entitled_client(promoted_config, monkeypatch) -> Iterator[TestClient]:
    monkeypatch.setattr(biocatalyst_api, "_PUBLIC_ROOT", promoted_config.public_root)
    app = FastAPI()
    app.include_router(biocatalyst_api.router)
    app.dependency_overrides[biocatalyst_api.require_site_full_user] = lambda: {
        "id": "paid-user",
        "tier": "pro",
    }
    with TestClient(app) as client:
        yield client


def test_entitled_health_list_and_detail_read_a_real_v11_projection(entitled_client) -> None:
    health = entitled_client.get("/api/biocatalyst/v1/health")
    assert health.status_code == 200
    _assert_private_headers(health)
    health_payload = health.json()
    assert health_payload["schema_version"] == "biocatalyst_api.v1"
    assert health_payload["source"] == {
        "name": "ClinicalTrials.gov",
        "dataset_timestamp_raw": "2026-08-01T09:00:00",
    }
    assert health_payload["coverage"] == {"class": "current_only", "configured": 1, "observed": 1}
    assert health_payload["authority"]["classification"] == "source_fact"
    assert health_payload["authority"]["decision_authority"] is False

    listed = entitled_client.get("/api/biocatalyst/v1/trials?limit=1&sort=nct")
    assert listed.status_code == 200
    _assert_private_headers(listed)
    list_payload = listed.json()
    assert list_payload["pagination"] == {"limit": 1, "total": 1, "next_cursor": None}
    assert list_payload["query"] == {
        "q": None,
        "phase": None,
        "status": None,
        "condition": None,
        "sort": "nct",
    }
    assert len(list_payload["trials"]) == 1
    summary = list_payload["trials"][0]
    assert summary == {
        "nct_id": "NCT00000001",
        "title": "Synthetic Phase 2 Study",
        "brief_title": "Synthetic Phase 2 Study",
        "status": "RECRUITING",
        "study_type": None,
        "phases": [],
        "sponsor": None,
        "conditions": [],
        "enrollment": {"count": 160, "type": "ESTIMATED"},
        "dates": {
            "start": None,
            "primary_completion": {"date": "2026-12", "type": "ESTIMATED"},
            "completion": None,
        },
        "updated_at": "2026-08-01",
        "retrieved_at": "2026-08-01T15:00:02.000000Z",
    }

    detail = entitled_client.get("/api/biocatalyst/v1/trials/NCT00000001")
    assert detail.status_code == 200
    _assert_private_headers(detail)
    detail_payload = detail.json()
    assert detail_payload["trial"].items() >= summary.items()
    assert detail_payload["trial"]["interventions"] == []
    assert detail_payload["trial"]["endpoints"] == {"primary": [], "secondary": []}
    # The fixture omits the source locations field; missing is not an observed
    # empty list and must never be flattened into a synthetic zero-site claim.
    assert detail_payload["trial"]["site_count"] is None
    assert detail_payload["trial"]["countries"] == []
    assert detail_payload["trial"]["evidence"] == {
        "provider": "ClinicalTrials.gov",
        "record_id": "NCT00000001",
        "url": "https://clinicaltrials.gov/study/NCT00000001",
        "updated_at": "2026-08-01",
        "retrieved_at": "2026-08-01T15:00:02.000000Z",
        "coverage": "current_only",
    }
    assert detail_payload["trial"]["history"] == {
        "available": False,
        "reason": "current_only_source_cut",
    }


def test_list_filters_sorting_cursor_and_bounds_are_deterministic(entitled_client) -> None:
    status = entitled_client.get("/api/biocatalyst/v1/trials?status=recruiting&sort=updated_desc")
    assert status.status_code == 200
    assert status.json()["pagination"]["total"] == 1

    query = entitled_client.get("/api/biocatalyst/v1/trials?q=synthetic")
    assert query.status_code == 200
    assert query.json()["trials"][0]["nct_id"] == "NCT00000001"

    # These source facts are deliberately absent in the genuine B1 fixture;
    # filtering must return an empty result, never infer fields from the title.
    phase = entitled_client.get("/api/biocatalyst/v1/trials?phase=phase2")
    condition = entitled_client.get("/api/biocatalyst/v1/trials?condition=oncology")
    assert phase.status_code == condition.status_code == 200
    assert phase.json()["pagination"]["total"] == 0
    assert condition.json()["pagination"]["total"] == 0

    empty_page = entitled_client.get("/api/biocatalyst/v1/trials?cursor=djE6MQ&limit=1")
    assert empty_page.status_code == 200
    assert empty_page.json()["pagination"] == {"limit": 1, "total": 1, "next_cursor": None}
    assert empty_page.json()["trials"] == []

    malformed = entitled_client.get("/api/biocatalyst/v1/trials?cursor=not-a-valid-cursor")
    assert malformed.status_code == 400
    assert malformed.json() == {"detail": "invalid cursor"}
    _assert_private_headers(malformed)

    invalid_sort = entitled_client.get("/api/biocatalyst/v1/trials?sort=outcome_score")
    invalid_limit = entitled_client.get("/api/biocatalyst/v1/trials?limit=251")
    assert invalid_sort.status_code == invalid_limit.status_code == 400
    assert invalid_sort.json() == {"detail": "invalid sort"}
    assert invalid_limit.json() == {"detail": "invalid limit"}
    # Request validation happens before the endpoint body; it still belongs to
    # a paid, private data route and must not lose the response privacy policy.
    _assert_private_headers(invalid_sort)
    _assert_private_headers(invalid_limit)


def test_detail_validates_id_before_any_public_generation_read(
    entitled_client, monkeypatch
) -> None:
    def must_not_read() -> tuple[object, dict[str, Any]]:
        raise AssertionError("malformed identifiers must be rejected before disk access")

    monkeypatch.setattr(biocatalyst_api, "_read_bundle", must_not_read)
    response = entitled_client.get("/api/biocatalyst/v1/trials/not-an-nct")
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid NCT ID"}
    _assert_private_headers(response)


def test_unknown_canonical_id_is_private_404(entitled_client) -> None:
    response = entitled_client.get("/api/biocatalyst/v1/trials/NCT99999999")
    assert response.status_code == 404
    assert response.json() == {"detail": "trial not covered"}
    _assert_private_headers(response)


def test_recursive_api_payload_has_no_private_provenance_or_integrity_keys(entitled_client) -> None:
    payloads = [
        entitled_client.get("/api/biocatalyst/v1/health").json(),
        entitled_client.get("/api/biocatalyst/v1/trials").json(),
        entitled_client.get("/api/biocatalyst/v1/trials/NCT00000001").json(),
    ]
    for payload in payloads:
        for key in _walk_keys(payload):
            lowered = key.casefold()
            assert not any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS), key
        encoded = json.dumps(payload, sort_keys=True)
        assert "test-secret" not in encoded
        assert "biocatalyst/raw/" not in encoded
        assert "biocatalyst/receipts/" not in encoded
        assert "biocatalyst/source_snapshots/" not in encoded


def test_missing_tampered_and_symlinked_public_state_returns_coarse_503(
    entitled_client, promoted_config, monkeypatch, tmp_path: Path
) -> None:
    missing_root = tmp_path / "missing-public-root"
    monkeypatch.setattr(biocatalyst_api, "_PUBLIC_ROOT", missing_root)
    missing = entitled_client.get("/api/biocatalyst/v1/trials")
    assert missing.status_code == 503
    assert missing.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(missing)

    monkeypatch.setattr(biocatalyst_api, "_PUBLIC_ROOT", promoted_config.public_root)
    pointer = promoted_config.public_root / "current.json"
    pointer.write_text("{not-json", encoding="utf-8")
    tampered = entitled_client.get("/api/biocatalyst/v1/trials")
    assert tampered.status_code == 503
    assert tampered.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(tampered)

    # Re-promote an isolated generation so the symlink case does not rely on a
    # corrupted pointer left by the preceding assertion.
    isolated = worker_config(tmp_path / "symlink-fixture")
    result = worker.run_once(
        isolated,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )
    assert result.status == "success"
    monkeypatch.setattr(biocatalyst_api, "_PUBLIC_ROOT", isolated.public_root)
    source_pointer = isolated.public_root / "current.json"
    outside = tmp_path / "outside-current.json"
    outside.write_bytes(source_pointer.read_bytes())
    source_pointer.unlink()
    source_pointer.symlink_to(outside)
    symlinked = entitled_client.get("/api/biocatalyst/v1/trials")
    assert symlinked.status_code == 503
    assert symlinked.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(symlinked)


def test_legacy_projection_is_not_silently_served(entitled_client, promoted_config) -> None:
    """A structurally valid B1 receipt generation must remain product-unavailable."""

    pointer_path = promoted_config.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = promoted_config.public_root / "generations" / pointer["generation_id"]
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    trial_snapshot = generation / "trial_snapshots" / "NCT00000001.json"
    trial_snapshot.unlink()
    (generation / "trial_snapshots").rmdir()
    manifest["schema_version"] = "1.0.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if not artifact["name"].startswith("trial_snapshots/")
    ]
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")

    response = entitled_client.get("/api/biocatalyst/v1/trials")
    assert response.status_code == 503
    assert response.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(response)


def test_route_declares_paid_dependency_and_production_openapi_mounts_all_routes() -> None:
    route_dependencies = {
        route.path: {dependency.call for dependency in route.dependant.dependencies}
        for route in biocatalyst_api.router.routes
    }
    for path in (
        "/api/biocatalyst/v1/health",
        "/api/biocatalyst/v1/trials",
        "/api/biocatalyst/v1/trials/{nct_id}",
    ):
        assert biocatalyst_api.require_site_full_user in route_dependencies[path]

    import app.main as main_mod

    public_paths = main_mod.app.openapi().get("paths", {})
    assert {
        "/api/biocatalyst/v1/health",
        "/api/biocatalyst/v1/trials",
        "/api/biocatalyst/v1/trials/{nct_id}",
    }.issubset(public_paths)


def test_authentication_then_paid_entitlement_order(monkeypatch) -> None:
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
    assert biocatalyst_api.require_site_full_user("Bearer paid-token") == entitled
    assert calls == [
        ("require_user", "Bearer paid-token"),
        ("enforce_site_full", (user, True)),
    ]


def test_anonymous_and_free_users_are_denied_before_public_disk_read(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(
        main_mod,
        "require_user",
        lambda _authorization: (_ for _ in ()).throw(
            HTTPException(401, "missing credentials")
        ),
    )
    with pytest.raises(HTTPException) as anonymous:
        biocatalyst_api.require_site_full_user(None)
    assert anonymous.value.status_code == 401

    monkeypatch.setenv("PAYWALL_ENABLED", "0")
    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})
    monkeypatch.setattr(paywall_mod, "_entitled", lambda _user_id, _feature: (False, "free"))
    with pytest.raises(HTTPException) as free:
        biocatalyst_api.require_site_full_user("Bearer signed-in-free-user")
    assert free.value.status_code == 403
    assert free.value.detail["required_feature"] == "site_full"

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(402, "site_full required")

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("disk must not be read before entitlement")
        ),
    )
    app = FastAPI()
    app.include_router(biocatalyst_api.router)
    with TestClient(app) as client:
        denied = client.get(
            "/api/biocatalyst/v1/trials",
            headers={"Authorization": "Bearer free-token"},
        )
    assert denied.status_code == 402
    assert denied.json() == {"detail": "site_full required"}
