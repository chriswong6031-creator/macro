"""Adversarial contract tests for the paid BioCatalyst trial API.

The API is deliberately a read-only, fact-only edge over the worker-promoted
public generation.  These tests create a real B2 generation through the
worker fixture, then exercise the authentication, availability, and disclosure
boundaries without reaching private worker state or external services.
"""
from __future__ import annotations

import base64
from hashlib import sha256
import json
from pathlib import Path
from types import SimpleNamespace
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


def _history_authority() -> dict[str, Any]:
    return {
        "classification": "source_fact",
        "decision_authority": False,
        "allowed_uses": ["display", "context", "explain"],
        "forbidden_uses": [
            "originate_signal",
            "rank_security",
            "select_security",
            "size_position",
            "gate_decision",
            "execute_trade",
            "raise_authority",
        ],
    }


def _history_model(*, changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    model: dict[str, Any] = {
        "contract_id": "trial_history_read_model.v1",
        "schema_version": "1.0.0",
        "history_model_id": "trial_history_model_NCT00000001_fixture",
        "nct_id": "NCT00000001",
        "available": True,
        "source_name": "ClinicalTrials.gov",
        "source_history_url": "https://clinicaltrials.gov/study/NCT00000001?tab=history",
        "coverage_class": "record_history_complete",
        "current_only": False,
        "unavailable_reason": None,
        "retrieved_at": "2026-08-01T15:00:02.000000Z",
        "versions": [
            {
                "display_version": 1,
                "source_submitted_at": "2026-07-01",
                "url": "https://clinicaltrials.gov/study/NCT00000001?a=1&tab=history",
            },
            {
                "display_version": 2,
                "source_submitted_at": "2026-08-01",
                "url": "https://clinicaltrials.gov/study/NCT00000001?a=2&tab=history",
            },
        ],
        "changes": changes
        if changes is not None
        else [
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "NOT_YET_RECRUITING",
                "after_value": "RECRUITING",
            }
        ],
        "authority": _history_authority(),
        "generated_at": "2026-08-01T15:00:02.000000Z",
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model["model_payload_sha256"] = canonical_json_sha256(model)
    return model


def _unavailable_history_model(reason: str = "incomplete_chain") -> dict[str, Any]:
    model = _history_model(changes=[])
    model.update(
        {
            "available": False,
            "coverage_class": "unavailable",
            "unavailable_reason": reason,
            "retrieved_at": None,
            "versions": [],
        }
    )
    model["model_payload_sha256"] = canonical_json_sha256(
        {key: value for key, value in model.items() if key != "model_payload_sha256"}
    )
    return model


def _replace_v12_history_model(config: Any, model: dict[str, Any]) -> None:
    """Replace one public B2 artifact to exercise request-time redactions."""

    pointer_path = config.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = config.public_root / "generations" / pointer["generation_id"]
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    history_path = generation / "history" / "NCT00000001.json"
    history_path.parent.mkdir(exist_ok=True)
    history_bytes = canonical_json_bytes(model) + b"\n"
    history_path.write_bytes(history_bytes)
    prospective_root = generation / "prospective"
    if prospective_root.exists():
        for artifact_path in prospective_root.iterdir():
            artifact_path.unlink()
        prospective_root.rmdir()
    manifest["schema_version"] = "1.2.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["name"] != "history/NCT00000001.json"
        and not artifact["name"].startswith("prospective/")
    ]
    manifest["artifacts"].append(
        {
            "name": "history/NCT00000001.json",
            "sha256": sha256(history_bytes).hexdigest(),
            "byte_count": len(history_bytes),
        }
    )
    manifest["artifacts"].sort(key=lambda row: row["name"])
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


def _assert_private_headers(response) -> None:
    for name, expected in _PRIVATE_HEADERS.items():
        assert response.headers[name] == expected
    assert response.headers["content-type"].startswith("application/json")


def _assert_private_exception(exc: HTTPException) -> None:
    headers = {name.casefold(): value for name, value in (exc.headers or {}).items()}
    for name, expected in _PRIVATE_HEADERS.items():
        assert headers[name] == expected


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
    """Publish a genuine B2 generation by the worker's normal seam."""

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


def _observed(value: Any) -> dict[str, Any]:
    return {"state": "observed", "value": value}


def _milestone_snapshot(
    nct_id: str,
    *,
    primary_completion: tuple[str, str | None] | None = None,
    completion: tuple[str, str | None] | None = None,
    title: str | None = None,
    phases: list[str] | None = None,
    status: str = "RECRUITING",
    conditions: list[str] | None = None,
) -> dict[str, Any]:
    """Small public-shaped projection fixture for registry-date monitor tests."""

    def registry_date(value: tuple[str, str | None] | None) -> dict[str, Any]:
        if value is None:
            return {"state": "source_missing", "value": None}
        raw_date, date_type = value
        return _observed({"date": raw_date, "type": date_type})

    rendered_title = title or f"Registry study {nct_id}"
    return {
        "nct_id": nct_id,
        "facts": {
            "official_title": _observed(rendered_title),
            "brief_title": _observed(rendered_title),
            "overall_status": _observed(status),
            "phases": _observed(phases or ["PHASE2"]),
            "conditions": _observed(conditions or ["Oncology"]),
            "primary_completion_date": registry_date(primary_completion),
            "completion_date": registry_date(completion),
        },
        "source_attribution": {
            "source_uri": f"https://clinicaltrials.gov/study/{nct_id}",
            "source_last_update_posted_at": "2026-02-28",
        },
        "coverage_class": "current_only",
        "retrieved_at": "2026-02-28T12:00:00.000000Z",
    }


def _milestone_projection(
    snapshots: list[dict[str, Any]],
    *,
    as_of: str = "2026-02-28T23:30:00Z",
    generation_id: str = "ctgov_run_20260228_fixture",
):
    generation = SimpleNamespace(
        generation_id=generation_id,
        last_success_at=as_of,
        source_dataset_timestamp_raw="2026-02-28T23:00:00",
        configured_nct_count=len(snapshots),
        observed_nct_count=len(snapshots),
        last_attempt_at=as_of,
    )
    return SimpleNamespace(generation=generation, trials=tuple(snapshots))


def _milestone_operational(as_of: str = "2026-02-28T23:30:00Z") -> dict[str, Any]:
    return {
        "state": "fresh",
        "last_attempt_at": as_of,
        "last_success_at": as_of,
        "last_error_code": None,
    }


def _change_history_model(
    nct_id: str,
    *,
    versions: list[tuple[int, str]] | None = None,
    changes: list[dict[str, Any]] | None = None,
    retrieved_at: str = "2026-08-02T12:00:00.000000Z",
    available: bool = True,
    authority: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Public-shaped B2 model for request-only Change Tape tests."""

    model = _history_model(changes=changes or [])
    model.update(
        {
            "history_model_id": f"trial_history_model_{nct_id}_change_fixture",
            "nct_id": nct_id,
            "available": available,
            "source_history_url": f"https://clinicaltrials.gov/study/{nct_id}?tab=history",
            "coverage_class": "record_history_complete" if available else "unavailable",
            "unavailable_reason": None if available else "incomplete_chain",
            "retrieved_at": retrieved_at if available else None,
            "versions": [
                {
                    "display_version": display_version,
                    "source_submitted_at": submitted_at,
                    "url": f"https://clinicaltrials.gov/study/{nct_id}?a={display_version}&tab=history",
                }
                for display_version, submitted_at in (
                    versions
                    or [
                        (1, "2026-06-01"),
                        (2, "2026-07-01"),
                    ]
                )
            ]
            if available
            else [],
            "changes": changes or [] if available else [],
            "authority": authority or _history_authority(),
        }
    )
    return model


def _change_projection(
    snapshots: list[dict[str, Any]],
    history_models: dict[str, dict[str, Any]],
    *,
    as_of: str = "2026-08-02T23:30:00Z",
    generation_id: str = "ctgov_run_20260802_change_fixture",
):
    base = _milestone_projection(
        snapshots,
        as_of=as_of,
        generation_id=generation_id,
    )
    return SimpleNamespace(
        generation=base.generation,
        trials=base.trials,
        history_models_by_nct=history_models,
    )


def _prospective_event(
    nct_id: str,
    *,
    suffix: str | None = None,
    after: str = "2026-08-01T12:00:00.000000Z",
    at_or_before: str = "2026-08-02T12:00:00.000000Z",
    changes: list[dict[str, Any]] | None = None,
    total_exact_operation_count: int | None = None,
) -> dict[str, Any]:
    rendered_changes = changes if changes is not None else [
        {
            "kind": "registry_status",
            "op": "replace",
            "before_state": "present",
            "before_value": "NOT_YET_RECRUITING",
            "after_state": "present",
            "after_value": "RECRUITING",
        }
    ]
    total = total_exact_operation_count if total_exact_operation_count is not None else len(rendered_changes)
    public_seed = {
        "nct_id": nct_id,
        "observed_interval": {"after": after, "at_or_before": at_or_before},
        "total_exact_operation_count": total,
        "changes": rendered_changes,
    }
    return {
        "change_id": f"prospective_change_{nct_id}_{suffix or canonical_json_sha256(public_seed)[:24]}",
        "first_observed_at": at_or_before,
        "observed_interval": {"after": after, "at_or_before": at_or_before},
        "total_exact_operation_count": total,
        "display_change_count": len(rendered_changes),
        "omitted_operation_count": total - len(rendered_changes),
        "changes": rendered_changes,
        "evidence": {
            "source_name": "ClinicalTrials.gov",
            "source_uri": f"https://clinicaltrials.gov/study/{nct_id}",
            "retrieved_at": at_or_before,
        },
        "interpretation": "registry_record_changed",
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _history_authority(),
    }


def _prospective_model(
    nct_id: str,
    *,
    events: list[dict[str, Any]] | None = None,
    accrual_state: str = "accruing",
    coverage_started_at: str = "2026-08-01T12:00:00.000000Z",
    last_observed_at: str = "2026-08-02T12:00:00.000000Z",
) -> dict[str, Any]:
    rendered_events = events if events is not None else [_prospective_event(nct_id)]
    model: dict[str, Any] = {
        "contract_id": "trial_prospective_change_read_model.v1",
        "schema_version": "1.0.0",
        "nct_id": nct_id,
        "available": True,
        "unavailable_reason": None,
        "accrual_state": accrual_state,
        "coverage_class": "current_only",
        "coverage_method": "prospective_api_polling",
        "coverage_epoch_id": f"ctgov_coverage_{nct_id}_fixture",
        "coverage_started_at": coverage_started_at,
        "baseline_established_at": coverage_started_at,
        "last_observed_at": last_observed_at,
        "observation_count": 1 if accrual_state == "baseline_established" else 2,
        "events": rendered_events,
        "generated_at": last_observed_at,
        "interpretation": "registry_record_changed",
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "authority": _history_authority(),
        "hash_scope": "canonical_payload_excluding_model_payload_sha256",
    }
    model["model_payload_sha256"] = canonical_json_sha256(model)
    return model


def _prospective_projection(
    snapshots: list[dict[str, Any]],
    models: dict[str, dict[str, Any]],
    *,
    as_of: str = "2026-08-02T23:30:00Z",
    generation_id: str = "ctgov_run_20260802_prospective_fixture",
):
    base = _milestone_projection(
        snapshots,
        as_of=as_of,
        generation_id=generation_id,
    )
    return SimpleNamespace(
        generation=base.generation,
        trials=base.trials,
        history_models_by_nct={},
        prospective_models_by_nct=models,
    )


def _replace_v13_prospective_model(config: Any, model: dict[str, Any]) -> None:
    """Add one pointer-bound prospective artifact to the real B2 fixture."""

    _replace_v12_history_model(config, _history_model())
    pointer_path = config.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = config.public_root / "generations" / pointer["generation_id"]
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    prospective_path = generation / "prospective" / "NCT00000001.json"
    prospective_path.parent.mkdir(exist_ok=True)
    prospective_bytes = canonical_json_bytes(model) + b"\n"
    prospective_path.write_bytes(prospective_bytes)
    manifest["schema_version"] = "1.3.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["name"] != "prospective/NCT00000001.json"
    ]
    manifest["artifacts"].append(
        {
            "name": "prospective/NCT00000001.json",
            "sha256": sha256(prospective_bytes).hexdigest(),
            "byte_count": len(prospective_bytes),
        }
    )
    manifest["artifacts"].sort(key=lambda row: row["name"])
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")


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
    # The default B2-disabled lane publishes an explicit unavailable artifact
    # instead of treating its current registry cut as a historical version feed.
    assert detail_payload["trial"]["history"] == {
        "available": False,
        "state": "unavailable",
        "reason": "disabled",
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


def test_registry_milestones_are_paid_private_and_generation_anchored(
    entitled_client, monkeypatch
) -> None:
    projection = _milestone_projection(
        [
            _milestone_snapshot(
                "NCT00000001",
                primary_completion=("2026-02-28", "ACTUAL"),
                completion=("2026-03-01", "ESTIMATED"),
            ),
            _milestone_snapshot(
                "NCT00000002",
                primary_completion=("2026-03", "ESTIMATED"),
            ),
            _milestone_snapshot(
                "NCT00000003",
                primary_completion=("2026", None),
            ),
            _milestone_snapshot(
                "NCT00000004",
                primary_completion=("2026-05-28", "ACTUAL"),
            ),
        ]
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational()),
    )

    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?"
        "q=registry%20study&phase=phase2&status=recruiting&condition=onco"
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    assert payload["query"] == {
        "milestone_kind": "primary_completion",
        "window": "next_90d",
        "from_date": None,
        "to_date": None,
        "q": "registry study",
        "phase": "phase2",
        "status": "recruiting",
        "condition": "onco",
    }
    # The committed cut is February 28, and a next_90d window is exactly 90
    # inclusive civil days.  No wall-clock date participates in this result.
    assert payload["effective_window"] == {
        "from_date": "2026-02-28",
        "to_date": "2026-05-28",
        "anchor_date": "2026-02-28",
    }
    assert [row["trial"]["nct_id"] for row in payload["milestones"]] == [
        "NCT00000001",
        "NCT00000002",
        "NCT00000004",
    ]
    first = payload["milestones"][0]
    assert first["registry_milestone"] == {
        "kind": "primary_completion",
        "date": "2026-02-28",
        "type": "ACTUAL",
        "precision": "day",
    }
    assert first["evidence"] == {
        "provider": "ClinicalTrials.gov",
        "record_id": "NCT00000001",
        "url": "https://clinicaltrials.gov/study/NCT00000001",
        "coverage": "current_only",
    }
    # A source year is not a point on January 1: it cannot fit inside this
    # short window and must not be silently shown as an invented daily date.
    assert "NCT00000003" not in {row["trial"]["nct_id"] for row in payload["milestones"]}

    completion = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?milestone_kind=completion&window=next_30d"
    )
    assert completion.status_code == 200
    assert completion.json()["milestones"][0]["registry_milestone"] == {
        "kind": "completion",
        "date": "2026-03-01",
        "type": "ESTIMATED",
        "precision": "day",
    }


def test_registry_milestones_respect_partial_precision_and_leap_day_boundaries(
    entitled_client, monkeypatch
) -> None:
    projection = _milestone_projection(
        [
            _milestone_snapshot(
                "NCT00000001",
                primary_completion=("2024-02-29", "ACTUAL"),
            ),
            _milestone_snapshot(
                "NCT00000002",
                primary_completion=("2024-02", "ESTIMATED"),
            ),
            _milestone_snapshot(
                "NCT00000003",
                primary_completion=("2024", None),
            ),
            _milestone_snapshot(
                "NCT00000004",
                primary_completion=("2024-03-29", "mystery"),
            ),
        ],
        as_of="2024-02-29T23:30:00Z",
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2024-02-29T23:30:00Z")),
    )

    leap_day = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?window=all&from_date=2024-02-29&to_date=2024-02-29"
    )
    assert leap_day.status_code == 200
    assert [row["registry_milestone"] for row in leap_day.json()["milestones"]] == [
        {
            "kind": "primary_completion",
            "date": "2024-02-29",
            "type": "ACTUAL",
            "precision": "day",
        }
    ]

    full_leap_month = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?window=all&from_date=2024-02-01&to_date=2024-02-29"
    )
    assert [row["registry_milestone"] for row in full_leap_month.json()["milestones"]] == [
        {
            "kind": "primary_completion",
            "date": "2024-02",
            "type": "ESTIMATED",
            "precision": "month",
        },
        {
            "kind": "primary_completion",
            "date": "2024-02-29",
            "type": "ACTUAL",
            "precision": "day",
        },
    ]

    next_30 = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?window=next_30d"
    )
    assert next_30.json()["effective_window"] == {
        "from_date": "2024-02-29",
        "to_date": "2024-03-29",
        "anchor_date": "2024-02-29",
    }
    # The unknown source type stays unknown, and the monthly partial does not
    # enter a window that holds only part of March.
    assert [row["registry_milestone"] for row in next_30.json()["milestones"]] == [
        {
            "kind": "primary_completion",
            "date": "2024-02-29",
            "type": "ACTUAL",
            "precision": "day",
        },
        {
            "kind": "primary_completion",
            "date": "2024-03-29",
            "type": "UNKNOWN",
            "precision": "day",
        },
    ]


def test_registry_milestones_order_by_interval_then_nct_not_date_type_and_bind_cursor(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot(
            "NCT00000012", primary_completion=("2026-03-01", "ESTIMATED")
        ),
        _milestone_snapshot("NCT00000010", primary_completion=("2026-03-01", "ACTUAL")),
        _milestone_snapshot("NCT00000011", primary_completion=("2026-03-01", None)),
        _milestone_snapshot("NCT00000013", primary_completion=("2026-03-02", "ACTUAL")),
    ]
    projection = _milestone_projection(snapshots)
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational()),
    )

    first_page = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?window=all&limit=2"
    )
    assert first_page.status_code == 200
    first_payload = first_page.json()
    assert [row["trial"]["nct_id"] for row in first_payload["milestones"]] == [
        "NCT00000010",
        "NCT00000011",
    ]
    assert [row["registry_milestone"]["type"] for row in first_payload["milestones"]] == [
        "ACTUAL",
        "UNKNOWN",
    ]
    cursor = first_payload["pagination"]["next_cursor"]
    assert isinstance(cursor, str)
    assert "NCT00000010" not in cursor
    assert "ctgov_run_20260228_fixture" not in cursor

    second_page = entitled_client.get(
        f"/api/biocatalyst/v1/trials/milestones?window=all&limit=2&cursor={cursor}"
    )
    assert [row["trial"]["nct_id"] for row in second_page.json()["milestones"]] == [
        "NCT00000012",
        "NCT00000013",
    ]

    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("signed query mismatch must be rejected before disk access")
        ),
    )
    changed_query = entitled_client.get(
        f"/api/biocatalyst/v1/trials/milestones?window=all&limit=2&q=registry&cursor={cursor}"
    )
    assert changed_query.status_code == 400
    assert changed_query.json() == {"detail": "cursor query mismatch"}
    _assert_private_headers(changed_query)

    changed_generation = _milestone_projection(
        snapshots,
        generation_id="ctgov_run_20260301_fixture",
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (changed_generation, _milestone_operational()),
    )
    restarted = entitled_client.get(
        f"/api/biocatalyst/v1/trials/milestones?window=all&limit=2&cursor={cursor}"
    )
    assert restarted.status_code == 409
    assert restarted.json() == {"detail": "trial data changed; restart pagination"}
    _assert_private_headers(restarted)


def test_registry_milestone_cursor_signature_rejects_offset_and_query_forgery_before_read(
    entitled_client, monkeypatch
) -> None:
    binding = biocatalyst_api._milestone_query_binding(
        milestone_kind="primary_completion",
        window="all",
        from_date=None,
        to_date=None,
        q=None,
        phase=None,
        status=None,
        condition=None,
        limit=2,
    )
    cursor = biocatalyst_api._encode_milestone_cursor(
        2,
        generation_id="ctgov_run_20260228_fixture",
        query_binding=binding,
    )

    def rewrite_cursor(*, offset: str | None = None, query: str | None = None) -> str:
        raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
        parts = raw.decode("ascii").split(":")
        assert parts[0] == "m2"
        if offset is not None:
            parts[1] = offset
        if query is not None:
            forged_binding = dict(binding)
            forged_binding["q"] = query
            parts[3] = biocatalyst_api._opaque_digest(forged_binding)
        return base64.urlsafe_b64encode(":".join(parts).encode("ascii")).decode(
            "ascii"
        ).rstrip("=")

    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("unauthenticated cursor payload must fail before disk access")
        ),
    )
    forged_offset = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?window=all&limit=2&cursor="
        + rewrite_cursor(offset="100001")
    )
    assert forged_offset.status_code == 400
    assert forged_offset.json() == {"detail": "invalid cursor"}
    _assert_private_headers(forged_offset)

    forged_query = entitled_client.get(
        "/api/biocatalyst/v1/trials/milestones?window=all&limit=2&q=registry&cursor="
        + rewrite_cursor(query="registry")
    )
    assert forged_query.status_code == 400
    assert forged_query.json() == {"detail": "invalid cursor"}
    _assert_private_headers(forged_query)


def test_registry_milestone_signed_cursor_round_trips_above_legacy_100k_boundary() -> None:
    binding = biocatalyst_api._milestone_query_binding(
        milestone_kind="primary_completion",
        window="all",
        from_date=None,
        to_date=None,
        q=None,
        phase=None,
        status=None,
        condition=None,
        limit=250,
    )
    cursor_key = b"k" * 32
    cursor = biocatalyst_api._encode_milestone_cursor(
        100_250,
        generation_id="ctgov_run_20260228_fixture",
        query_binding=binding,
        cursor_key=cursor_key,
    )
    offset, generation_digest, query_digest = biocatalyst_api._decode_milestone_cursor(
        cursor,
        cursor_key=cursor_key,
    )
    assert offset == 100_250
    assert generation_digest == biocatalyst_api._opaque_digest(
        {"generation_id": "ctgov_run_20260228_fixture"}
    )
    assert query_digest == biocatalyst_api._opaque_digest(binding)


def test_registry_milestone_short_configured_cursor_secret_fails_closed_before_read(
    entitled_client, monkeypatch
) -> None:
    monkeypatch.setenv("BIOCATALYST_CURSOR_SECRET", "x" * 31)
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("invalid cursor-key configuration must fail before disk access")
        ),
    )
    response = entitled_client.get("/api/biocatalyst/v1/trials/milestones?window=all")
    assert response.status_code == 503
    assert response.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(response)


@pytest.mark.parametrize(
    "suffix",
    (
        "milestone_kind=pdufa",
        "window=NEXT_90D",
        "window=next_90d&from_date=2026-02-28",
        "window=all&from_date=2026-02",
        "window=all&from_date=2026-03-01&to_date=2026-02-28",
        "window=all&limit=251",
        "window=all&cursor=not-a-valid-cursor",
    ),
)
def test_registry_milestone_invalid_queries_fail_before_any_public_read(
    entitled_client, monkeypatch, suffix: str
) -> None:
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("invalid milestone queries must be rejected before disk access")
        ),
    )
    response = entitled_client.get(f"/api/biocatalyst/v1/trials/milestones?{suffix}")
    assert response.status_code == 400
    _assert_private_headers(response)


def test_registry_change_tape_reads_available_history_from_real_public_generation(
    entitled_client, promoted_config
) -> None:
    """Exercise the route through the pointer/manifest/artifact reader, not a stub."""

    _replace_v12_history_model(promoted_config, _history_model())

    response = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all")
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["history_coverage"]["available_trials"] == 1
    assert payload["changes"][0]["registry_change"]["changes"] == [
        {
            "kind": "registry_status_changed",
            "before_value": "NOT_YET_RECRUITING",
            "after_value": "RECRUITING",
        }
    ]


def test_registry_change_tape_groups_exact_history_values_with_current_record_filters(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot(
            "NCT00000001",
            title="Alpha current registry study",
            phases=["PHASE2"],
            conditions=["Oncology"],
        ),
        _milestone_snapshot(
            "NCT00000002",
            title="Beta current registry study",
            phases=["PHASE3"],
            conditions=["Neurology"],
        ),
        _milestone_snapshot("NCT00000003", title="Unavailable history study"),
    ]
    projection = _change_projection(
        snapshots,
        {
            "NCT00000001": _change_history_model(
                "NCT00000001",
                versions=[(1, "2026-06-01"), (2, "2026-06-15"), (3, "2026-07-05")],
                changes=[
                    {
                        "kind": "registry_status_changed",
                        "before_display_version": 1,
                        "after_display_version": 2,
                        "before_value": "NOT_YET_RECRUITING",
                        "after_value": "RECRUITING",
                    },
                    {
                        "kind": "enrollment_changed",
                        "before_display_version": 1,
                        "after_display_version": 2,
                        "before_value": {"count": 80, "type": "ESTIMATED"},
                        "after_value": {"count": 120, "type": "ESTIMATED"},
                    },
                    {
                        "kind": "endpoint_added",
                        "before_display_version": 2,
                        "after_display_version": 3,
                        "before_value": None,
                        "after_value": {"measure": "Registry measure"},
                    },
                ],
            ),
            "NCT00000002": _change_history_model(
                "NCT00000002",
                versions=[(1, "2026-06-01"), (2, "2026-07-05")],
                changes=[
                    {
                        "kind": "study_date_changed",
                        "before_display_version": 1,
                        "after_display_version": 2,
                        "before_value": "2026-10",
                        "after_value": "2026-11",
                    }
                ],
            ),
            "NCT00000003": _change_history_model("NCT00000003", available=False),
        },
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )

    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?window=all&from_date=2026-06-15&"
        "to_date=2026-07-05&q=alpha%20current&phase=phase2&status=recruiting&condition=onco"
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    assert payload["query"] == {
        "change_kind": "all",
        "window": "all",
        "from_date": "2026-06-15",
        "to_date": "2026-07-05",
        "q": "alpha current",
        "phase": "phase2",
        "status": "recruiting",
        "condition": "onco",
    }
    assert payload["effective_window"] == {
        "from_date": "2026-06-15",
        "to_date": "2026-07-05",
        "anchor_date": "2026-08-02",
        "date_basis": "source_submitted_at",
    }
    assert payload["history_coverage"] == {
        "class": "record_history_complete",
        "selection_basis": "current_trial_record",
        "available_trials": 1,
        "unavailable_trials": 0,
        "knowledge_cutoff": "2026-08-02T12:00:00.000000Z",
    }
    assert [item["registry_change"]["after_display_version"] for item in payload["changes"]] == [
        3,
        2,
    ]
    first = payload["changes"][0]
    assert first["trial"]["nct_id"] == "NCT00000001"
    assert first["registry_change"] == {
        "before_display_version": 2,
        "after_display_version": 3,
        "source_submitted_at": "2026-07-05",
        "interpretation": "registry_record_changed",
        "protocol_change_asserted": False,
        "materiality_assessed": False,
        "total_display_safe_changes": 1,
        "shown_change_count": 1,
        "changes": [
            {
                "kind": "endpoint_added",
                "before_value": None,
                "after_value": {"measure": "Registry measure"},
            }
        ],
    }
    assert first["evidence"] == {
        "provider": "ClinicalTrials.gov",
        "record_id": "NCT00000001",
        "version_url": "https://clinicaltrials.gov/study/NCT00000001?a=3&tab=history",
        "history_url": "https://clinicaltrials.gov/study/NCT00000001?tab=history",
        "retrieved_at": "2026-08-02T12:00:00.000000Z",
        "coverage": "record_history_complete",
    }
    assert first["authority"] == _history_authority()

    exact_kind = entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?change_kind=registry_status_changed&"
        "window=all&q=alpha%20current"
    )
    assert exact_kind.status_code == 200
    selected = exact_kind.json()["changes"]
    assert len(selected) == 1
    assert selected[0]["registry_change"]["total_display_safe_changes"] == 2
    assert selected[0]["registry_change"]["shown_change_count"] == 1
    assert selected[0]["registry_change"]["changes"] == [
        {
            "kind": "registry_status_changed",
            "before_value": "NOT_YET_RECRUITING",
            "after_value": "RECRUITING",
        }
    ]


def test_registry_change_tape_preserves_exact_bounded_json_strings(
    entitled_client, monkeypatch
) -> None:
    long_before = "x" * 12_000
    long_after = "y" * 12_000
    exact_whitespace = "  line one\n\tline two  "
    longest_key = "k" * 256
    model = _change_history_model(
        "NCT00000001",
        changes=[
            {
                "kind": "endpoint_description_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "",
                "after_value": exact_whitespace,
            },
            {
                "kind": "endpoint_measure_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": long_before,
                "after_value": long_after,
            },
            {
                "kind": "site_listing_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": {longest_key: ""},
                "after_value": {longest_key: "  "},
            },
        ],
    )
    projection = _change_projection(
        [_milestone_snapshot("NCT00000001")],
        {"NCT00000001": model},
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )

    response = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all")
    assert response.status_code == 200
    rendered = response.json()["changes"][0]["registry_change"]["changes"]
    assert rendered[0]["before_value"] == ""
    assert rendered[0]["after_value"] == exact_whitespace
    assert rendered[1]["before_value"] == long_before
    assert rendered[1]["after_value"] == long_after
    assert rendered[2]["before_value"] == {longest_key: ""}
    assert rendered[2]["after_value"] == {longest_key: "  "}

    model["changes"][1]["after_value"] += "z"
    oversized = _change_projection(
        [_milestone_snapshot("NCT00000001")],
        {"NCT00000001": model},
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (oversized, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    rejected = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all")
    assert rejected.status_code == 503
    _assert_private_headers(rejected)

    model["changes"][1]["after_value"] = long_after
    model["changes"][2]["after_value"] = {"k" * 257: "value"}
    mismatched_key_bound = entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?window=all"
    )
    assert mismatched_key_bound.status_code == 503
    _assert_private_headers(mismatched_key_bound)

    model["changes"][2]["after_value"] = {longest_key: "  "}
    model["changes"][1]["after_value"] = float("nan")
    nonfinite_number = entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?window=all"
    )
    assert nonfinite_number.status_code == 503
    _assert_private_headers(nonfinite_number)


def test_registry_change_tape_as_of_covers_later_history_knowledge_time(
    entitled_client, monkeypatch
) -> None:
    retrieved_at = "2026-08-02T12:00:00.000000Z"
    model = _change_history_model(
        "NCT00000001",
        versions=[(1, "2026-07-01"), (2, "2026-08-02")],
        changes=[
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "A",
                "after_value": "B",
            }
        ],
        retrieved_at=retrieved_at,
    )
    projection = _change_projection(
        [_milestone_snapshot("NCT00000001")],
        {"NCT00000001": model},
        as_of="2026-08-01T23:30:00Z",
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-01T23:30:00Z")),
    )

    response = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=last_30d")
    assert response.status_code == 200
    payload = response.json()
    assert payload["as_of"] == retrieved_at
    assert payload["history_coverage"]["knowledge_cutoff"] == retrieved_at
    assert payload["effective_window"] == {
        "from_date": "2026-07-04",
        "to_date": "2026-08-02",
        "anchor_date": "2026-08-02",
        "date_basis": "source_submitted_at",
    }
    assert payload["pagination"]["total"] == 1


def test_registry_change_tape_uses_after_version_dates_inclusive_windows_and_current_summary(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot("NCT00000001", title="Current Alpha record"),
        _milestone_snapshot("NCT00000002", title="Current Beta record"),
        _milestone_snapshot("NCT00000003", title="Current Gamma record"),
    ]
    projection = _change_projection(
        snapshots,
        {
            "NCT00000001": _change_history_model(
                "NCT00000001",
                versions=[(1, "2026-06-01"), (2, "2026-07-04")],
                changes=[
                    {
                        "kind": "registry_status_changed",
                        "before_display_version": 1,
                        "after_display_version": 2,
                        "before_value": "A",
                        "after_value": "B",
                    }
                ],
            ),
            "NCT00000002": _change_history_model(
                "NCT00000002",
                versions=[(1, "2026-06-01"), (2, "2026-07-03")],
                changes=[
                    {
                        "kind": "registry_status_changed",
                        "before_display_version": 1,
                        "after_display_version": 2,
                        "before_value": "A",
                        "after_value": "B",
                    }
                ],
            ),
            "NCT00000003": _change_history_model(
                "NCT00000003",
                versions=[(1, "2026-06-01"), (2, "2026-08-02")],
                changes=[
                    {
                        "kind": "registry_status_changed",
                        "before_display_version": 1,
                        "after_display_version": 2,
                        "before_value": "A",
                        "after_value": "B",
                    }
                ],
            ),
        },
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )

    last_30 = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=last_30d")
    assert last_30.status_code == 200
    assert last_30.json()["effective_window"] == {
        "from_date": "2026-07-04",
        "to_date": "2026-08-02",
        "anchor_date": "2026-08-02",
        "date_basis": "source_submitted_at",
    }
    assert [item["trial"]["nct_id"] for item in last_30.json()["changes"]] == [
        "NCT00000003",
        "NCT00000001",
    ]
    assert entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?window=all&from_date=2026-07-03&to_date=2026-07-03"
    ).json()["changes"][0]["trial"]["nct_id"] == "NCT00000002"
    # Selection never searches stale history values; it is intentionally a
    # filter over the current trial summary at the committed projection cut.
    assert entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?window=all&q=current%20alpha"
    ).json()["pagination"]["total"] == 1
    assert entitled_client.get(
        "/api/biocatalyst/v1/trials/changes?window=all&q=not_yet_recruiting"
    ).json()["pagination"]["total"] == 0


def test_registry_change_tape_pagination_binds_query_and_generation_before_returning_rows(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot("NCT00000011"),
        _milestone_snapshot("NCT00000010"),
        _milestone_snapshot("NCT00000012"),
    ]
    def model(nct_id: str, submitted_at: str) -> dict[str, Any]:
        return _change_history_model(
            nct_id,
            versions=[(1, "2026-06-01"), (2, submitted_at)],
            changes=[
                {
                    "kind": "registry_status_changed",
                    "before_display_version": 1,
                    "after_display_version": 2,
                    "before_value": "A",
                    "after_value": "B",
                }
            ],
        )

    projection = _change_projection(
        snapshots,
        {
            "NCT00000010": model("NCT00000010", "2026-07-01"),
            "NCT00000011": model("NCT00000011", "2026-07-01"),
            "NCT00000012": model("NCT00000012", "2026-06-30"),
        },
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    first = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all&limit=2")
    assert first.status_code == 200
    first_payload = first.json()
    assert [item["trial"]["nct_id"] for item in first_payload["changes"]] == [
        "NCT00000010",
        "NCT00000011",
    ]
    cursor = first_payload["pagination"]["next_cursor"]
    assert isinstance(cursor, str)
    assert "NCT00000010" not in cursor
    assert "ctgov_run_20260802_change_fixture" not in cursor
    second = entitled_client.get(
        f"/api/biocatalyst/v1/trials/changes?window=all&limit=2&cursor={cursor}"
    )
    assert [item["trial"]["nct_id"] for item in second.json()["changes"]] == ["NCT00000012"]

    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("signed change cursor query mismatch must fail before disk access")
        ),
    )
    changed_query = entitled_client.get(
        f"/api/biocatalyst/v1/trials/changes?window=all&limit=2&q=current&cursor={cursor}"
    )
    assert changed_query.status_code == 400
    assert changed_query.json() == {"detail": "cursor query mismatch"}
    _assert_private_headers(changed_query)

    changed_generation = _change_projection(
        snapshots,
        {
            "NCT00000010": model("NCT00000010", "2026-07-01"),
            "NCT00000011": model("NCT00000011", "2026-07-01"),
            "NCT00000012": model("NCT00000012", "2026-06-30"),
        },
        generation_id="ctgov_run_20260803_change_fixture",
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (changed_generation, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    restarted = entitled_client.get(
        f"/api/biocatalyst/v1/trials/changes?window=all&limit=2&cursor={cursor}"
    )
    assert restarted.status_code == 409
    assert restarted.json() == {"detail": "trial data changed; restart pagination"}
    _assert_private_headers(restarted)


def test_registry_change_cursor_rejects_forgery_before_read_and_is_endpoint_separated(
    entitled_client, monkeypatch
) -> None:
    binding = biocatalyst_api._change_query_binding(
        change_kind="all",
        window="all",
        from_date=None,
        to_date=None,
        q=None,
        phase=None,
        status=None,
        condition=None,
        limit=2,
    )
    cursor = biocatalyst_api._encode_change_cursor(
        2,
        generation_id="ctgov_run_20260802_change_fixture",
        query_binding=binding,
    )
    raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
    parts = raw.decode("ascii").split(":")
    assert parts[0] == "c1"
    parts[1] = "100001"
    forged = base64.urlsafe_b64encode(":".join(parts).encode("ascii")).decode("ascii").rstrip("=")
    milestone_cursor = biocatalyst_api._encode_milestone_cursor(
        2,
        generation_id="ctgov_run_20260802_change_fixture",
        query_binding=biocatalyst_api._milestone_query_binding(
            milestone_kind="primary_completion",
            window="all",
            from_date=None,
            to_date=None,
            q=None,
            phase=None,
            status=None,
            condition=None,
            limit=2,
        ),
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("unauthenticated or cross-route cursor must fail before disk access")
        ),
    )
    for candidate in (forged, milestone_cursor):
        response = entitled_client.get(
            "/api/biocatalyst/v1/trials/changes?window=all&limit=2&cursor=" + candidate
        )
        assert response.status_code == 400
        assert response.json() == {"detail": "invalid cursor"}
        _assert_private_headers(response)


@pytest.mark.parametrize(
    "suffix",
    (
        "change_kind=protocol_delayed",
        "window=LAST_90D",
        "window=last_90d&from_date=2026-08-01",
        "window=all&from_date=2026-08",
        "window=all&from_date=2026-08-03&to_date=2026-08-02",
        "window=all&limit=251",
        "window=all&cursor=not-a-valid-cursor",
    ),
)
def test_registry_change_invalid_queries_fail_before_any_public_read(
    entitled_client, monkeypatch, suffix: str
) -> None:
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("invalid Change Tape queries must be rejected before disk access")
        ),
    )
    response = entitled_client.get(f"/api/biocatalyst/v1/trials/changes?{suffix}")
    assert response.status_code == 400
    _assert_private_headers(response)


def test_registry_change_tape_fails_closed_for_future_or_mismatched_history_versions(
    entitled_client, monkeypatch
) -> None:
    snapshot = _milestone_snapshot("NCT00000001")
    future = _change_history_model(
        "NCT00000001",
        versions=[(1, "2026-07-01"), (2, "2026-08-03")],
        changes=[
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "A",
                "after_value": "B",
            }
        ],
    )
    projection = _change_projection([snapshot], {"NCT00000001": future})
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    future_response = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all")
    assert future_response.status_code == 503
    assert future_response.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(future_response)

    after_retrieval = _change_history_model(
        "NCT00000001",
        versions=[(1, "2026-07-01"), (2, "2026-08-02")],
        changes=[
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "A",
                "after_value": "B",
            }
        ],
        retrieved_at="2026-08-01T23:59:59.000000Z",
    )
    after_retrieval_projection = _change_projection(
        [snapshot], {"NCT00000001": after_retrieval}
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (after_retrieval_projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    retrieval_response = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all")
    assert retrieval_response.status_code == 503
    assert retrieval_response.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(retrieval_response)

    mismatch = _change_history_model(
        "NCT00000001",
        versions=[(1, "2026-07-01"), (2, "2026-08-02")],
        changes=[
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "A",
                "after_value": "B",
            }
        ],
    )
    mismatch["versions"][1]["url"] = "https://clinicaltrials.gov/study/NCT00000001?a=1&tab=history"
    mismatched_projection = _change_projection([snapshot], {"NCT00000001": mismatch})
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (mismatched_projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    mismatch_response = entitled_client.get("/api/biocatalyst/v1/trials/changes?window=all")
    assert mismatch_response.status_code == 503
    assert mismatch_response.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(mismatch_response)


def test_prospective_change_tape_reads_one_real_pointer_bound_v13_artifact(
    entitled_client, promoted_config
) -> None:
    _replace_v13_prospective_model(promoted_config, _prospective_model("NCT00000001"))

    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    assert payload["pagination"]["total"] == 1
    assert payload["prospective_coverage"] == {
        "class": "prospective_current_only",
        "selection_basis": "current_trial_record",
        "coverage_state": "active",
        "coverage_started_at": "2026-08-01T12:00:00.000000Z",
        "last_observed_at": "2026-08-02T12:00:00.000000Z",
        "active_trials": 1,
        "pre_baseline_trials": 0,
        "unavailable_trials": 0,
    }
    change = payload["prospective_changes"][0]
    assert change["prospective_change"]["observed_interval"] == {
        "after": "2026-08-01T12:00:00.000000Z",
        "at_or_before": "2026-08-02T12:00:00.000000Z",
    }
    assert change["evidence"] == {
        "provider": "ClinicalTrials.gov",
        "record_id": "NCT00000001",
        "url": "https://clinicaltrials.gov/study/NCT00000001",
        "retrieved_at": "2026-08-02T12:00:00.000000Z",
        "coverage": "current_only",
    }


def test_prospective_change_tape_uses_current_filters_and_keeps_all_omitted_events(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot(
            "NCT00000001",
            title="Alpha current registry study",
            phases=["PHASE2"],
            conditions=["Oncology"],
        ),
        _milestone_snapshot(
            "NCT00000002",
            title="Baseline current registry study",
            phases=["PHASE3"],
            conditions=["Neurology"],
        ),
        _milestone_snapshot(
            "NCT00000003",
            title="Gamma current registry study",
            phases=["PHASE2"],
            conditions=["Oncology"],
        ),
    ]
    alpha_change = _prospective_event(
        "NCT00000001",
        changes=[
            {
                "kind": "registry_status",
                "op": "replace",
                "before_state": "present",
                "before_value": "NOT_YET_RECRUITING",
                "after_state": "present",
                "after_value": "RECRUITING",
            },
            {
                "kind": "endpoint_record",
                "op": "replace",
                "before_state": "present",
                "before_value": {"reference": "  existing clinical text  "},
                "after_state": "present",
                "after_value": {"reference": "  revised clinical text  "},
            }
        ],
    )
    gamma_change = _prospective_event(
        "NCT00000003",
        suffix="b" * 24,
        changes=[],
        total_exact_operation_count=2,
    )
    projection = _prospective_projection(
        snapshots,
        {
            "NCT00000001": _prospective_model("NCT00000001", events=[alpha_change]),
            "NCT00000002": _prospective_model(
                "NCT00000002",
                events=[],
                accrual_state="baseline_established",
                coverage_started_at="2026-08-02T12:00:00.000000Z",
                last_observed_at="2026-08-02T12:00:00.000000Z",
            ),
            "NCT00000003": _prospective_model("NCT00000003", events=[gamma_change]),
        },
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )

    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=last_30d&phase=phase2&condition=onco"
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["query"] == {
        "change_kind": "all",
        "window": "last_30d",
        "from_date": None,
        "to_date": None,
        "q": None,
        "phase": "phase2",
        "status": None,
        "condition": "onco",
    }
    assert payload["effective_window"] == {
        "from_date": "2026-07-04",
        "to_date": "2026-08-02",
        "anchor_at": "2026-08-02T12:00:00.000000Z",
        "anchor_date": "2026-08-02",
        "date_basis": "observation_at_or_before_utc",
    }
    assert payload["prospective_coverage"] == {
        "class": "prospective_current_only",
        "selection_basis": "current_trial_record",
        "coverage_state": "active",
        "coverage_started_at": "2026-08-01T12:00:00.000000Z",
        "last_observed_at": "2026-08-02T12:00:00.000000Z",
        "active_trials": 2,
        "pre_baseline_trials": 0,
        "unavailable_trials": 0,
    }
    assert [row["trial"]["nct_id"] for row in payload["prospective_changes"]] == [
        "NCT00000001",
        "NCT00000003",
    ]
    assert payload["prospective_changes"][0]["prospective_change"]["changes"][1][
        "after_value"
    ] == {"reference": "  revised clinical text  "}
    omitted = payload["prospective_changes"][1]["prospective_change"]
    assert omitted["total_exact_operation_count"] == 2
    assert omitted["display_change_count"] == 0
    assert omitted["omitted_operation_count"] == 2
    assert omitted["changes"] == []

    # Current-record filters never search an old or changed value.
    assert entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all&q=NOT_YET_RECRUITING"
    ).json()["pagination"]["total"] == 0
    kind_filtered = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all&change_kind=endpoint_record"
    ).json()
    assert kind_filtered["pagination"]["total"] == 1
    # A category filter selects the event, not a subset of an event's bounded
    # display record: display_change_count must remain the array's length.
    filtered_change = kind_filtered["prospective_changes"][0]["prospective_change"]
    assert filtered_change["display_change_count"] == len(filtered_change["changes"]) == 2
    assert [change["kind"] for change in filtered_change["changes"]] == [
        "registry_status",
        "endpoint_record",
    ]


def test_prospective_coverage_clock_is_selection_scoped_while_window_anchor_is_global(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot("NCT00000001", title="Alpha selected current study"),
        _milestone_snapshot("NCT00000002", title="Beta excluded current study"),
    ]
    alpha_event = _prospective_event(
        "NCT00000001",
        after="2026-08-01T12:00:00.000000Z",
        at_or_before="2026-08-02T12:00:00.000000Z",
    )
    beta_event = _prospective_event(
        "NCT00000002",
        after="2026-08-04T12:00:00.000000Z",
        at_or_before="2026-08-05T12:00:00.000000Z",
    )
    projection = _prospective_projection(
        snapshots,
        {
            "NCT00000001": _prospective_model(
                "NCT00000001",
                events=[alpha_event],
                last_observed_at="2026-08-02T12:00:00.000000Z",
            ),
            "NCT00000002": _prospective_model(
                "NCT00000002",
                events=[beta_event],
                coverage_started_at="2026-08-04T12:00:00.000000Z",
                last_observed_at="2026-08-05T12:00:00.000000Z",
            ),
        },
        as_of="2026-08-05T23:30:00Z",
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-05T23:30:00Z")),
    )

    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=last_30d&q=alpha"
    )
    assert response.status_code == 200
    payload = response.json()
    # The global newest committed observation keeps the effective date window
    # invariant when a current-record filter is added or removed.
    assert payload["effective_window"] == {
        "from_date": "2026-07-07",
        "to_date": "2026-08-05",
        "anchor_at": "2026-08-05T12:00:00.000000Z",
        "anchor_date": "2026-08-05",
        "date_basis": "observation_at_or_before_utc",
    }
    # Coverage, however, describes only Alpha; Beta's later observation cannot
    # make the selected population look fresher than it is.
    assert payload["prospective_coverage"]["last_observed_at"] == (
        "2026-08-02T12:00:00.000000Z"
    )
    assert payload["prospective_coverage"]["active_trials"] == 1
    assert [row["trial"]["nct_id"] for row in payload["prospective_changes"]] == [
        "NCT00000001"
    ]


def test_prospective_change_tape_baseline_and_legacy_generations_stay_empty(
    entitled_client, monkeypatch
) -> None:
    snapshot = _milestone_snapshot("NCT00000001")
    baseline_model = _prospective_model(
        "NCT00000001",
        events=[],
        accrual_state="baseline_established",
        coverage_started_at="2026-08-01T12:00:00.000000Z",
        last_observed_at="2026-08-02T12:00:00.000000Z",
    )
    # A scope's coverage epoch may begin before a particular NCT first enters
    # its baseline.  The API must preserve that honest ordering rather than
    # incorrectly demanding equal timestamps.
    baseline_model["baseline_established_at"] = "2026-08-02T12:00:00.000000Z"
    baseline = _prospective_projection(
        [snapshot],
        {"NCT00000001": baseline_model},
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (baseline, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert response.status_code == 200
    assert response.json()["prospective_changes"] == []
    assert response.json()["prospective_coverage"] == {
        "class": "prospective_current_only",
        "selection_basis": "current_trial_record",
        "coverage_state": "pre_baseline",
        "coverage_started_at": "2026-08-01T12:00:00.000000Z",
        "last_observed_at": "2026-08-02T12:00:00.000000Z",
        "active_trials": 0,
        "pre_baseline_trials": 1,
        "unavailable_trials": 0,
    }

    legacy = _milestone_projection([snapshot], as_of="2026-08-02T23:30:00Z")
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (legacy, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    older_generation = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert older_generation.status_code == 200
    assert older_generation.json()["prospective_changes"] == []
    assert older_generation.json()["prospective_coverage"] == {
        "class": "prospective_current_only",
        "selection_basis": "current_trial_record",
        "coverage_state": "unavailable",
        "coverage_started_at": None,
        "last_observed_at": None,
        "active_trials": 0,
        "pre_baseline_trials": 0,
        "unavailable_trials": 1,
    }


def test_prospective_change_tape_reports_real_b2_pointer_as_unavailable_not_history(
    entitled_client, promoted_config
) -> None:
    _replace_v12_history_model(promoted_config, _history_model())

    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    assert payload["prospective_changes"] == []
    assert payload["prospective_coverage"] == {
        "class": "prospective_current_only",
        "selection_basis": "current_trial_record",
        "coverage_state": "unavailable",
        "coverage_started_at": None,
        "last_observed_at": None,
        "active_trials": 0,
        "pre_baseline_trials": 0,
        "unavailable_trials": 1,
    }
    assert "history" not in json.dumps(payload).casefold()
    assert "submission" not in json.dumps(payload).casefold()


def test_prospective_change_cursor_is_p1_signed_and_binds_query_before_read(
    entitled_client, monkeypatch
) -> None:
    snapshots = [
        _milestone_snapshot("NCT00000010"),
        _milestone_snapshot("NCT00000011"),
        _milestone_snapshot("NCT00000012"),
    ]
    projection = _prospective_projection(
        snapshots,
        {
            nct_id: _prospective_model(
                nct_id,
                events=[_prospective_event(nct_id, suffix=f"{index:024x}")],
            )
            for index, nct_id in enumerate(("NCT00000010", "NCT00000011", "NCT00000012"), 1)
        },
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    first = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all&limit=2"
    )
    assert first.status_code == 200
    cursor = first.json()["pagination"]["next_cursor"]
    assert isinstance(cursor, str)
    raw = base64.urlsafe_b64decode((cursor + "=" * (-len(cursor) % 4)).encode("ascii"))
    assert raw.decode("ascii").startswith("p1:")
    assert "NCT00000010" not in cursor
    assert entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all&limit=2&cursor=" + cursor
    ).json()["pagination"]["total"] == 3

    change_cursor = biocatalyst_api._encode_change_cursor(
        2,
        generation_id="ctgov_run_20260802_prospective_fixture",
        query_binding=biocatalyst_api._change_query_binding(
            change_kind="all",
            window="all",
            from_date=None,
            to_date=None,
            q=None,
            phase=None,
            status=None,
            condition=None,
            limit=2,
        ),
    )
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("foreign or query-mismatched p1 cursor read public state")
        ),
    )
    for candidate in (
        change_cursor,
        cursor,
    ):
        suffix = (
            "window=all&limit=2&cursor=" + candidate
            if candidate == change_cursor
            else "window=all&limit=2&q=alpha&cursor=" + candidate
        )
        rejected = entitled_client.get("/api/biocatalyst/v1/trials/prospective-changes?" + suffix)
        assert rejected.status_code == 400
        _assert_private_headers(rejected)


@pytest.mark.parametrize(
    "suffix",
    (
        "change_kind=endpoint_added",
        "window=LAST_90D",
        "window=last_90d&from_date=2026-08-01",
        "window=all&from_date=2026-08",
        "window=all&from_date=2026-08-03&to_date=2026-08-02",
        "window=all&limit=251",
        "window=all&cursor=not-a-valid-cursor",
    ),
)
def test_prospective_change_invalid_queries_fail_before_any_public_read(
    entitled_client, monkeypatch, suffix: str
) -> None:
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (_ for _ in ()).throw(
            AssertionError("invalid prospective queries must be rejected before disk access")
        ),
    )
    response = entitled_client.get(
        f"/api/biocatalyst/v1/trials/prospective-changes?{suffix}"
    )
    assert response.status_code == 400
    _assert_private_headers(response)


def test_prospective_change_tape_rejects_private_envelopes_and_never_leaks_model_hashes(
    entitled_client, monkeypatch
) -> None:
    snapshot = _milestone_snapshot("NCT00000001")
    model = _prospective_model("NCT00000001")
    projection = _prospective_projection([snapshot], {"NCT00000001": model})
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )
    response = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert response.status_code == 200
    assert not any(
        any(fragment in key.casefold() for fragment in _FORBIDDEN_KEY_FRAGMENTS)
        for key in _walk_keys(response.json())
    )

    model["events"][0]["source_receipt_ref"] = "ctgov_receipt_private"
    rejected = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert rejected.status_code == 503
    assert rejected.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(rejected)


def test_prospective_change_tape_rejects_nested_internal_provenance_but_allows_reference(
    entitled_client, monkeypatch
) -> None:
    snapshot = _milestone_snapshot("NCT00000001")
    event = _prospective_event(
        "NCT00000001",
        changes=[
            {
                "kind": "site_set",
                "op": "replace",
                "before_state": "present",
                "before_value": {
                    "summary": {"reference": "ordinary clinical source text"}
                },
                "after_state": "present",
                "after_value": {
                    "summary": {"reference": "ordinary revised clinical text"},
                    "diagnosis": {"hashimotoDisease": "stable"},
                },
            }
        ],
    )
    model = _prospective_model("NCT00000001", events=[event])
    projection = _prospective_projection([snapshot], {"NCT00000001": model})
    monkeypatch.setattr(
        biocatalyst_api,
        "_read_bundle",
        lambda: (projection, _milestone_operational("2026-08-02T23:30:00Z")),
    )

    allowed = entitled_client.get(
        "/api/biocatalyst/v1/trials/prospective-changes?window=all"
    )
    assert allowed.status_code == 200
    assert allowed.json()["prospective_changes"][0]["prospective_change"]["changes"][0][
        "after_value"
    ] == {
        "summary": {"reference": "ordinary revised clinical text"},
        "diagnosis": {"hashimotoDisease": "stable"},
    }

    for private_key in (
        "source_record_ref",
        "sourceRecordRef",
        "sha256",
        "payloadHash",
        "contentHash",
        "sourceHash",
        "payloadhash",
        "content_hash",
        "source-hash",
        "objectkey",
        "jsonpath",
        "hashscope",
        "receiptId",
        "rawObject",
        "transactionFrom",
    ):
        model["events"][0]["changes"][0]["after_value"] = {
            "summary": {private_key: "internal-only"}
        }
        injected = entitled_client.get(
            "/api/biocatalyst/v1/trials/prospective-changes?window=all"
        )
        assert injected.status_code == 503, private_key
        assert injected.json() == {"detail": "trial intelligence temporarily unavailable"}
        _assert_private_headers(injected)


def test_v12_detail_serves_only_the_pointer_bound_public_history_model(
    entitled_client, promoted_config
) -> None:
    _replace_v12_history_model(promoted_config, _history_model())

    detail = entitled_client.get("/api/biocatalyst/v1/trials/NCT00000001")
    assert detail.status_code == 200
    _assert_private_headers(detail)
    history = detail.json()["trial"]["history"]
    assert history == {
        "available": True,
        "state": "available",
        "source": {
            "name": "ClinicalTrials.gov",
            "url": "https://clinicaltrials.gov/study/NCT00000001?tab=history",
        },
        "coverage": "record_history_complete",
        "retrieved_at": "2026-08-01T15:00:02.000000Z",
        "versions": [
            {
                "display_version": 1,
                "submitted_at": "2026-07-01",
                "url": "https://clinicaltrials.gov/study/NCT00000001?a=1&tab=history",
            },
            {
                "display_version": 2,
                "submitted_at": "2026-08-01",
                "url": "https://clinicaltrials.gov/study/NCT00000001?a=2&tab=history",
            },
        ],
        "changes": [
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": "NOT_YET_RECRUITING",
                "after_value": "RECRUITING",
            }
        ],
    }
    for key in _walk_keys(history):
        lowered = key.casefold()
        assert not any(fragment in lowered for fragment in _FORBIDDEN_KEY_FRAGMENTS), key


def test_history_nested_provenance_is_rejected_even_after_the_public_tree_is_rehashed(
    entitled_client, promoted_config
) -> None:
    model = _history_model(
        changes=[
            {
                "kind": "registry_status_changed",
                "before_display_version": 1,
                "after_display_version": 2,
                "before_value": {"raw_object_key": "must-not-escape"},
                "after_value": "RECRUITING",
            }
        ]
    )
    _replace_v12_history_model(promoted_config, model)

    response = entitled_client.get("/api/biocatalyst/v1/trials/NCT00000001")
    assert response.status_code == 503
    assert response.json() == {"detail": "trial intelligence temporarily unavailable"}
    _assert_private_headers(response)


def test_v12_explicit_unavailable_history_artifact_is_served_honestly(
    entitled_client, promoted_config
) -> None:
    _replace_v12_history_model(
        promoted_config,
        _unavailable_history_model("incomplete_chain"),
    )

    detail = entitled_client.get("/api/biocatalyst/v1/trials/NCT00000001")
    assert detail.status_code == 200
    _assert_private_headers(detail)
    assert detail.json()["trial"]["history"] == {
        "available": False,
        "state": "unavailable",
        "reason": "incomplete_chain",
    }


def test_v11_generation_remains_readable_with_an_explicit_history_unavailable_state(
    entitled_client, promoted_config
) -> None:
    pointer_path = promoted_config.public_root / "current.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    generation = promoted_config.public_root / "generations" / pointer["generation_id"]
    manifest_path = generation / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    history = generation / "history" / "NCT00000001.json"
    history.unlink()
    history.parent.rmdir()
    prospective = generation / "prospective"
    if prospective.exists():
        for artifact_path in prospective.iterdir():
            artifact_path.unlink()
        prospective.rmdir()
    manifest["schema_version"] = "1.1.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if not artifact["name"].startswith("history/")
        and not artifact["name"].startswith("prospective/")
    ]
    manifest["manifest_sha256"] = canonical_json_sha256(
        {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    )
    manifest_path.write_bytes(canonical_json_bytes(manifest) + b"\n")
    pointer["manifest_sha256"] = manifest["manifest_sha256"]
    pointer_path.write_bytes(canonical_json_bytes(pointer) + b"\n")

    response = entitled_client.get("/api/biocatalyst/v1/trials/NCT00000001")
    assert response.status_code == 200
    _assert_private_headers(response)
    assert response.json()["trial"]["history"] == {
        "available": False,
        "state": "unavailable",
        "reason": "not_collected",
    }


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
        entitled_client.get("/api/biocatalyst/v1/trials/milestones").json(),
        entitled_client.get("/api/biocatalyst/v1/trials/changes").json(),
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
    history = generation / "history" / "NCT00000001.json"
    history.unlink()
    (generation / "history").rmdir()
    prospective = generation / "prospective"
    if prospective.exists():
        for artifact_path in prospective.iterdir():
            artifact_path.unlink()
        prospective.rmdir()
    manifest["schema_version"] = "1.0.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if not artifact["name"].startswith("trial_snapshots/")
        and not artifact["name"].startswith("history/")
        and not artifact["name"].startswith("prospective/")
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
        "/api/biocatalyst/v1/trials/milestones",
        "/api/biocatalyst/v1/trials/changes",
        "/api/biocatalyst/v1/trials/prospective-changes",
        "/api/biocatalyst/v1/trials/{nct_id}",
    ):
        assert biocatalyst_api.require_site_full_user in route_dependencies[path]

    import app.main as main_mod

    public_paths = main_mod.app.openapi().get("paths", {})
    assert {
        "/api/biocatalyst/v1/health",
        "/api/biocatalyst/v1/trials",
        "/api/biocatalyst/v1/trials/milestones",
        "/api/biocatalyst/v1/trials/changes",
        "/api/biocatalyst/v1/trials/prospective-changes",
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
            HTTPException(
                401,
                "missing credentials",
                headers={"WWW-Authenticate": "Bearer realm=mastermind"},
            )
        ),
    )
    with pytest.raises(HTTPException) as anonymous:
        biocatalyst_api.require_site_full_user(None)
    assert anonymous.value.status_code == 401
    _assert_private_exception(anonymous.value)
    assert anonymous.value.headers["WWW-Authenticate"] == "Bearer realm=mastermind"

    monkeypatch.setenv("PAYWALL_ENABLED", "0")
    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})
    monkeypatch.setattr(paywall_mod, "_entitled", lambda _user_id, _feature: (False, "free"))
    with pytest.raises(HTTPException) as free:
        biocatalyst_api.require_site_full_user("Bearer signed-in-free-user")
    assert free.value.status_code == 403
    assert free.value.detail["required_feature"] == "site_full"
    _assert_private_exception(free.value)

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(402, "site_full required", headers={"Retry-After": "60"})

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
        milestone_denied = client.get(
            "/api/biocatalyst/v1/trials/milestones",
            headers={"Authorization": "Bearer free-token"},
        )
        changes_denied = client.get(
            "/api/biocatalyst/v1/trials/changes",
            headers={"Authorization": "Bearer free-token"},
        )
    assert denied.status_code == 402
    assert denied.json() == {"detail": "site_full required"}
    _assert_private_headers(denied)
    assert denied.headers["retry-after"] == "60"
    assert milestone_denied.status_code == 402
    assert milestone_denied.json() == {"detail": "site_full required"}
    _assert_private_headers(milestone_denied)
    assert milestone_denied.headers["retry-after"] == "60"
    assert changes_denied.status_code == 402
    assert changes_denied.json() == {"detail": "site_full required"}
    _assert_private_headers(changes_denied)
    assert changes_denied.headers["retry-after"] == "60"
