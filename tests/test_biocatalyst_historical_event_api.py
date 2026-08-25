from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import app.biocatalyst as api
from engine.biocatalyst.historical_events import HistoricalEventPublisher


def _event(event_id: str = "bpcjv_event_" + "a" * 24) -> dict:
    return {
        "contract_id": "biocatalyst_historical_event_record.v1",
        "schema_version": "1.0.0",
        "event_id": event_id,
        "source": {"provider": "BioPharmCatalyst", "source_id": "biopharmcatalyst_jv_snapshot", "license_class": "licensed_finite_snapshot", "family": "historical_fda", "source_ordinal": 1, "capture_observed_at": "2026-08-17T07:55:47Z", "source_published_at": None, "source_published_at_state": "unknown"},
        "company": {"ticker_evidence": "ABC", "name_evidence": "Alpha", "resolution_state": "unresolved", "security_id": None, "issuer_id": None, "resolution_basis": "none", "issuer_relationship_state": "unavailable"},
        "event": {"date": "2024-01-01", "date_precision": "day", "family": "regulatory", "stage": "Approved", "description": "Approved", "source_available_at": None, "observed_at": "2026-08-17T07:55:47Z"},
        "asset": {"kind": "drug", "label": "Drug A", "indication": "Cancer"},
        "historical_market": {"price_at_event": "$10", "price_movement": "+5%"},
        "normalization": {"state": "deterministic", "repair": "none"},
        "unsafe_fields": ["capture_only_overlays_unavailable"],
        "authority": {"classification": "licensed_historical_context", "decision_authority": False, "allowed_uses": ["display", "context", "explain"], "forbidden_uses": ["originate_signal", "rank_security", "select_security", "size_position", "gate_decision", "execute_trade", "raise_authority"]},
    }


@pytest.fixture
def client(tmp_path: Path, monkeypatch) -> TestClient:
    root = tmp_path / "public" / "historical_events"
    HistoricalEventPublisher(root).publish(
        [_event()],
        coverage={"state": "partial", "source_rows": 15700, "normalized_rows": 1, "identity_resolved": 0, "identity_unresolved": 1, "duplicates_collapsed": 0, "families": {"historical_fda": 1}, "family_source_rows": {"historical_fda": 15700, "device_history": 0, "device_pipeline_history": 0}},
        capture_observed_at="2026-08-17T07:55:47Z",
        published_at="2026-08-24T20:00:00Z",
    )
    monkeypatch.setattr(api, "_PUBLIC_ROOT", tmp_path / "public")
    monkeypatch.setattr(api, "_HISTORICAL_EVENT_CURSOR_PROCESS_KEY", b"test-key")
    app = FastAPI()
    app.include_router(api.router)
    app.dependency_overrides[api.require_site_full_user] = lambda: {"id": "paid"}
    with TestClient(app) as test_client:
        yield test_client


def _assert_private(response) -> None:
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"


def test_history_api_returns_entitled_context_only_projection(client: TestClient) -> None:
    response = client.get("/api/biocatalyst/v1/historical-events?q=ABC&family=regulatory")
    assert response.status_code == 200
    _assert_private(response)
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["state"] == "partial"
    assert payload["coverage"]["source_rows"] == 15700
    assert payload["pagination"] == {"limit": 50, "total": 1, "next_cursor": None}
    assert len(payload["historical_events"]) == 1
    assert payload["authority"]["decision_authority"] is False
    rendered = response.text
    for forbidden in ("generation_id", "manifest_sha", "object_key", "company_url", "catalyst_url"):
        assert forbidden not in rendered


def test_history_api_rejects_invalid_query_before_read(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(api, "_read_historical_event_projection", lambda: (_ for _ in ()).throw(AssertionError("must not read")))
    assert client.get("/api/biocatalyst/v1/historical-events?family=bogus").status_code == 400
    assert client.get("/api/biocatalyst/v1/historical-events?from_date=2025-01-01&to_date=2024-01-01").status_code == 400
    assert client.get("/api/biocatalyst/v1/historical-events?cursor=bogus").status_code == 400


def test_history_api_denies_before_projection_read() -> None:
    def deny() -> dict:
        raise HTTPException(401, "missing credentials", headers=api._PRIVATE_HEADERS)

    application = FastAPI()
    application.include_router(api.router)
    application.dependency_overrides[api.require_site_full_user] = deny
    with TestClient(application) as test_client:
        with mock.patch.object(api, "_read_historical_event_projection", side_effect=AssertionError("must not read")):
            response = test_client.get("/api/biocatalyst/v1/historical-events")
    assert response.status_code == 401
    _assert_private(response)


def test_history_api_unavailable_is_typed_and_private(client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(api, "_read_historical_event_projection", lambda: None)
    response = client.get("/api/biocatalyst/v1/historical-events")
    assert response.status_code == 503
    assert response.json() == {"detail": "historical event history temporarily unavailable"}
    _assert_private(response)
