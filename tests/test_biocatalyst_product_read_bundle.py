"""Request-local single-validation product reads for BioCatalyst.

These tests prove one logical product bundle fully validates the pointer-bound
generation once, without a process-lifetime or cross-request trust cache.
"""
from __future__ import annotations

from datetime import timedelta
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable

import pytest

from engine.biocatalyst.publication import (
    ProductReadBundle,
    PublicationError,
    PublicGenerationPublisher,
    ValidatedPointerBoundGeneration,
)
from engine.sector_intelligence import canonical_json_bytes, canonical_json_sha256
import scripts.biocatalyst_worker as worker
from tests.test_biocatalyst_worker import (
    FakeCollectorFactory,
    MemoryStore,
    NOW,
    config as worker_config,
)


@pytest.fixture
def committed_generation(tmp_path):
    config = worker_config(tmp_path)
    result = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )
    assert result.status == "success"
    return config, PublicGenerationPublisher(config.public_root)


def _count_loads(monkeypatch: pytest.MonkeyPatch, sink: list[str]) -> None:
    orig = PublicGenerationPublisher._load_generation_manifest

    def wrapped(self: PublicGenerationPublisher, generation_id: str) -> dict[str, Any]:
        sink.append(generation_id)
        return orig(self, generation_id)

    monkeypatch.setattr(PublicGenerationPublisher, "_load_generation_manifest", wrapped)


def _generation_paths(publisher: PublicGenerationPublisher) -> tuple[Path, Path, dict[str, Any]]:
    pointer_path = publisher.pointer_path
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = publisher.public_root / "generations" / pointer["generation_id"]
    return pointer_path, generation, pointer


def _rehash_generation(
    *,
    pointer_path: Path,
    generation: Path,
    mutate: Callable[[dict[str, Any], dict[str, Any]], None],
) -> None:
    """Model a deliberate on-disk rehash attack, not an accidental corruption."""

    health_path = generation / "health.json"
    manifest_path = generation / "manifest.json"
    health = json.loads(health_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(health, manifest)
    health_bytes = canonical_json_bytes(health) + b"\n"
    health_path.write_bytes(health_bytes)
    for artifact in manifest["artifacts"]:
        if artifact["name"] == "health.json":
            artifact["sha256"] = sha256(health_bytes).hexdigest()
            artifact["byte_count"] = len(health_bytes)
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


def _rehash_trial_projection(
    *,
    pointer_path: Path,
    generation: Path,
    mutate: Callable[[dict[str, Any]], None],
) -> None:
    """Model a full-chain rehash attempt against one normalized trial DTO."""

    snapshot_path = generation / "trial_snapshots" / "NCT00000001.json"
    manifest_path = generation / "manifest.json"
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mutate(snapshot)
    snapshot["projection_sha256"] = canonical_json_sha256(
        {key: value for key, value in snapshot.items() if key != "projection_sha256"}
    )
    snapshot_bytes = canonical_json_bytes(snapshot) + b"\n"
    snapshot_path.write_bytes(snapshot_bytes)
    for artifact in manifest["artifacts"]:
        if artifact["name"] == "trial_snapshots/NCT00000001.json":
            artifact["sha256"] = sha256(snapshot_bytes).hexdigest()
            artifact["byte_count"] = len(snapshot_bytes)
            break
    else:
        raise AssertionError("normalized trial projection artifact missing")
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


def test_product_bundle_matches_independent_projection_and_health(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    _, publisher = committed_generation
    independent = publisher.read_trial_projection()
    health = publisher.read_operational_health(now=NOW)
    bundle = publisher.read_product_bundle(now=NOW)

    assert independent is not None
    assert bundle is not None
    assert isinstance(bundle, ProductReadBundle)
    assert bundle.projection.generation == independent.generation
    assert tuple(trial["nct_id"] for trial in bundle.projection.trials) == tuple(
        trial["nct_id"] for trial in independent.trials
    )
    assert bundle.operational_health["generation_id"] == bundle.projection.generation.generation_id
    assert bundle.operational_health["state"] == health["state"]
    assert bundle.operational_health["last_success_at"] == health["last_success_at"]
    assert bundle.operational_health["observed_nct_count"] == health["observed_nct_count"]


def test_unchanged_product_bundle_loads_generation_once(
    committed_generation: tuple[Any, PublicGenerationPublisher],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, publisher = committed_generation
    loads: list[str] = []
    _count_loads(monkeypatch, loads)

    bundle = publisher.read_product_bundle(now=NOW)

    assert bundle is not None
    assert len(loads) == 1
    assert loads == [bundle.projection.generation.generation_id]
    assert bundle.operational_health["generation_id"] == loads[0]


def test_second_independent_bundle_revalidates_instead_of_trusting_publisher_lifetime(
    committed_generation: tuple[Any, PublicGenerationPublisher],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, publisher = committed_generation
    loads: list[str] = []
    _count_loads(monkeypatch, loads)

    first = publisher.read_product_bundle(now=NOW)
    second = publisher.read_product_bundle(now=NOW)

    assert first is not None and second is not None
    assert len(loads) == 2
    assert loads[0] == loads[1] == first.projection.generation.generation_id
    assert not any(
        isinstance(value, (ValidatedPointerBoundGeneration, ProductReadBundle))
        for value in vars(publisher).values()
    )


def test_second_logical_read_rejects_post_success_rehash(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    _, publisher = committed_generation
    first = publisher.read_product_bundle(now=NOW)
    assert first is not None
    pointer_path, generation, _ = _generation_paths(publisher)

    def mutate(health: dict[str, Any], manifest: dict[str, Any]) -> None:
        changed = "2026-08-01T16:00:01.000000Z"
        health["last_attempt_at"] = changed
        manifest["last_attempt_at"] = changed

    _rehash_generation(pointer_path=pointer_path, generation=generation, mutate=mutate)

    with pytest.raises(PublicationError) as raised:
        publisher.read_product_bundle(now=NOW)
    assert raised.value.code == "GENERATION_HEALTH_BINDING_MISMATCH"


def test_rehashed_trial_projection_still_rejected_on_product_bundle(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    _, publisher = committed_generation
    pointer_path, generation, _ = _generation_paths(publisher)
    _rehash_trial_projection(
        pointer_path=pointer_path,
        generation=generation,
        mutate=lambda snapshot: snapshot.__setitem__(
            "source_snapshot_ref", "ctgov_snapshot_NCT00000001_rebound"
        ),
    )

    with pytest.raises(PublicationError) as raised:
        publisher.read_product_bundle(now=NOW)
    assert raised.value.code == "TRIAL_PROJECTION_BINDING_MISMATCH"


def test_product_bundle_derives_stale_at_read_time_without_rewriting_files(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    _, publisher = committed_generation
    health_before = publisher.health_path.read_bytes()
    published_at = NOW
    fresh = publisher.read_product_bundle(now=published_at)
    stale = publisher.read_product_bundle(
        now=published_at + timedelta(seconds=7200, microseconds=1)
    )

    assert fresh is not None and stale is not None
    assert fresh.operational_health["state"] == "fresh"
    assert stale.operational_health["state"] == "stale"
    assert stale.operational_health["last_error_code"] == "FRESHNESS_BUDGET_EXCEEDED"
    assert stale.projection.generation.generation_id == fresh.projection.generation.generation_id
    assert stale.operational_health["generation_id"] == fresh.projection.generation.generation_id
    assert publisher.health_path.read_bytes() == health_before


def test_root_health_from_another_generation_cannot_join_the_bundle(
    committed_generation: tuple[Any, PublicGenerationPublisher],
) -> None:
    _, publisher = committed_generation
    projection_id = publisher.read_committed().generation_id
    mutable_health = json.loads(publisher.health_path.read_text(encoding="utf-8"))
    mutable_health["generation_id"] = "ctgov_run_20260801T160000000000Z_abcdef123456"
    publisher.health_path.write_bytes(canonical_json_bytes(mutable_health) + b"\n")

    bundle = publisher.read_product_bundle(now=NOW)

    assert bundle is not None
    assert bundle.projection.generation.generation_id == projection_id
    assert bundle.operational_health["state"] == "unavailable"
    assert bundle.operational_health["last_error_code"] == "OPERATIONAL_HEALTH_UNAVAILABLE"
    assert bundle.operational_health.get("generation_id") is None


def test_pointer_advance_retries_once_against_the_new_generation(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = worker_config(tmp_path)
    store = MemoryStore()
    first = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: store,
        now_fn=lambda: NOW,
    )
    assert first.status == "success"
    publisher = PublicGenerationPublisher(config.public_root)
    first_pointer = publisher.pointer_path.read_bytes()
    first_health = publisher.health_path.read_bytes()
    first_id = publisher.read_committed().generation_id
    second = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(
            source_timestamp="2026-08-01T10:00:00",
            watermark_after="2026-08-01T17:00:05Z",
        ),
        store_factory=lambda _: store,
        now_fn=lambda: NOW + timedelta(hours=1),
    )
    assert second.status == "success"
    second_id = publisher.read_committed().generation_id
    assert second_id != first_id

    loads: list[str] = []
    _count_loads(monkeypatch, loads)
    seen = {"flipped": False}
    orig = PublicGenerationPublisher._pointer_matches_validated

    def flip_once(self: PublicGenerationPublisher, validated: ValidatedPointerBoundGeneration) -> bool:
        if not seen["flipped"]:
            seen["flipped"] = True
            self.pointer_path.write_bytes(first_pointer)
            self.health_path.write_bytes(first_health)
        return orig(self, validated)

    monkeypatch.setattr(PublicGenerationPublisher, "_pointer_matches_validated", flip_once)

    bundle = publisher.read_product_bundle(now=NOW)

    assert bundle is not None
    assert bundle.projection.generation.generation_id == first_id
    assert bundle.operational_health["generation_id"] == first_id
    assert loads == [second_id, first_id]


def test_second_pointer_change_during_bundle_read_fails_closed(
    committed_generation: tuple[Any, PublicGenerationPublisher],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, publisher = committed_generation
    monkeypatch.setattr(
        PublicGenerationPublisher,
        "_pointer_matches_validated",
        lambda self, validated: False,
    )

    with pytest.raises(PublicationError) as raised:
        publisher.read_product_bundle(now=NOW)
    assert raised.value.code == "PUBLIC_GENERATION_CHANGED"


def test_entitled_health_endpoint_uses_one_generation_load(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pytest.importorskip("fastapi", reason="BioCatalyst API tests need fastapi")
    pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import app.biocatalyst as biocatalyst_api

    config = worker_config(tmp_path)
    result = worker.run_once(
        config,
        collector_factory=FakeCollectorFactory(),
        store_factory=lambda _: MemoryStore(),
        now_fn=lambda: NOW,
    )
    assert result.status == "success"
    monkeypatch.setattr(biocatalyst_api, "_PUBLIC_ROOT", config.public_root)
    loads: list[str] = []
    _count_loads(monkeypatch, loads)
    app = FastAPI()
    app.include_router(biocatalyst_api.router)
    app.dependency_overrides[biocatalyst_api.require_site_full_user] = lambda: {
        "id": "paid-user",
    }
    with TestClient(app) as client:
        response = client.get("/api/biocatalyst/v1/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert len(loads) == 1
    payload = response.json()
    assert payload["health"]["state"] in {"fresh", "stale"}
    assert payload["coverage"]["observed"] == 1
