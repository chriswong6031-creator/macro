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
    manifest["schema_version"] = "1.2.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if artifact["name"] != "history/NCT00000001.json"
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
    manifest["schema_version"] = "1.1.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if not artifact["name"].startswith("history/")
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
    manifest["schema_version"] = "1.0.0"
    manifest["artifacts"] = [
        artifact
        for artifact in manifest["artifacts"]
        if not artifact["name"].startswith("trial_snapshots/")
        and not artifact["name"].startswith("history/")
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
        "/api/biocatalyst/v1/trials/{nct_id}",
    ):
        assert biocatalyst_api.require_site_full_user in route_dependencies[path]

    import app.main as main_mod

    public_paths = main_mod.app.openapi().get("paths", {})
    assert {
        "/api/biocatalyst/v1/health",
        "/api/biocatalyst/v1/trials",
        "/api/biocatalyst/v1/trials/milestones",
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
    assert denied.status_code == 402
    assert denied.json() == {"detail": "site_full required"}
    _assert_private_headers(denied)
    assert denied.headers["retry-after"] == "60"
    assert milestone_denied.status_code == 402
    assert milestone_denied.json() == {"detail": "site_full required"}
    _assert_private_headers(milestone_denied)
    assert milestone_denied.headers["retry-after"] == "60"
