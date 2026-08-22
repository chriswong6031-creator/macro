"""FIF-2C API tests: HTTP transport, auth, private headers, exact packet bytes."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.forensics as forensics_api
from engine.fundamental_forensics.financial_intelligence_packet import (
    EntityInput,
    PacketQueryRequest,
    assemble_financial_intelligence_packet,
    canonical_packet_bytes,
    packet_digest,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.query_service import (
    CanonicalEntityBinding,
    FinancialQueryAdmissionError,
)
from engine.fundamental_forensics.revision_service import (
    FinancialPacketDataset,
    fip1_packet_dataset,
    packet_dataset_from_fixture,
)
from engine.fundamental_forensics.synthetic_filing_package import (
    build_multihop_revenue_fixture,
)

ROOT = Path(__file__).resolve().parents[1]
_PACKET_PATH = "/api/forensics/v1/financial/packet"
_PACKET_SCHEMA = "fundamental_forensics.financial_packet_request/v1"

T2_SOURCE = "2025-12-31T23:59:59Z"
T2_RECORDED = "2026-08-03T12:00:00Z"
T3_SOURCE = "2025-12-31T23:59:59Z"
T3_RECORDED = "2026-08-05T12:00:02Z"
HOP_C_SOURCE = "2026-08-05T12:00:02Z"
HOP_B_SYSTEM_READY = "2026-08-04T17:59:59Z"
DELAYED_MAPPING_AFTER = "2026-08-07T00:00:00Z"

_EXPECTED_PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _make_request(
    *,
    schema: str = _PACKET_SCHEMA,
    entity_id: str = "mmx.issuer.fip1",
    policy: dict | None = None,
    metric_ids: list | None = None,
    periods: list | None = None,
) -> bytes:
    if policy is None:
        policy = {
            "selection": "latest_known_as_of",
            "source_snapshot_at": T3_SOURCE,
            "recorded_at": T3_RECORDED,
        }
    if metric_ids is None:
        metric_ids = ["revenue"]
    if periods is None:
        periods = [{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}]
    return json.dumps(
        {"schema": schema, "entity_id": entity_id, "policy": policy, "metric_ids": metric_ids, "periods": periods},
        separators=(",", ":"),
    ).encode("utf-8")


def _assert_private_headers(response) -> None:
    for name, expected in _EXPECTED_PRIVATE_HEADERS.items():
        assert response.headers.get(name) == expected, f"Missing or wrong header {name!r}"


def _assert_error(response, status: int, detail: str | None = None) -> None:
    assert response.status_code == status
    _assert_private_headers(response)
    payload = response.json()
    assert "detail" in payload
    if detail is not None:
        assert detail in payload["detail"] or payload["detail"] == detail


def _fip1_provider(resolve_calls: list | None = None):
    dataset = fip1_packet_dataset(ROOT)

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            if resolve_calls is not None:
                resolve_calls.append(entity_id)
            if entity_id == "mmx.issuer.fip1":
                return dataset
            raise FinancialQueryAdmissionError(400, "unknown entity")

    return _Provider()


def _asgi_post(app, path: str, *, body: bytes, extra_headers: list[tuple[bytes, bytes]]):
    import asyncio

    messages: list[dict] = []
    sent = {"done": False}

    async def receive():
        if not sent["done"]:
            sent["done"] = True
            return {"type": "http.request", "body": body, "more_body": False}
        return {"type": "http.disconnect"}

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode("ascii"),
        "root_path": "",
        "query_string": b"",
        "headers": extra_headers,
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }
    asyncio.run(app(scope, receive, send))
    start = next(m for m in messages if m["type"] == "http.response.start")
    body_out = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    header_map = {k.decode().lower(): v.decode() for k, v in start.get("headers", [])}
    return start["status"], header_map, body_out


@pytest.fixture
def router_app() -> FastAPI:
    app = FastAPI()
    app.include_router(forensics_api.router)
    return app


@pytest.fixture
def anon_client(router_app) -> TestClient:
    with TestClient(router_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def paid_client(router_app) -> TestClient:
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    with TestClient(router_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def fip1_paid_client(router_app, monkeypatch) -> TestClient:
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    monkeypatch.setattr(forensics_api, "_financial_packet_provider", _fip1_provider)
    with TestClient(router_app, raise_server_exceptions=False) as client:
        yield client


def test_anonymous_post_returns_401_with_private_headers(anon_client, monkeypatch) -> None:
    resolve_calls: list = []
    monkeypatch.setattr(
        forensics_api,
        "_financial_packet_provider",
        lambda: _fip1_provider(resolve_calls),
    )
    response = anon_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401
    _assert_private_headers(response)
    assert resolve_calls == []


def test_free_user_returns_403_with_private_headers(router_app, monkeypatch) -> None:
    from fastapi import HTTPException
    import app.main as app_main
    import app.paywall as paywall_mod

    resolve_calls: list = []
    monkeypatch.setattr(
        forensics_api, "_financial_packet_provider", lambda: _fip1_provider(resolve_calls)
    )
    monkeypatch.setattr(app_main, "require_user", lambda auth: {"id": "free-user", "tier": "free"})
    monkeypatch.setattr(
        paywall_mod,
        "enforce_site_full",
        lambda user, always=False: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="site_full required")
        ),
    )
    with TestClient(router_app, raise_server_exceptions=False) as client:
        response = client.post(
            _PACKET_PATH,
            content=_make_request(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 403
    _assert_private_headers(response)
    assert resolve_calls == []


def test_success_returns_exact_canonical_packet_bytes(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    sha256_header = response.headers.get("x-fif-response-sha256")
    assert sha256_header == hashlib.sha256(response.content).hexdigest()
    payload = response.json()
    assert payload["schema"] == "financial_intelligence_packet.v1"
    assert "cells" in payload
    assert "packet" not in payload
    dataset = fip1_packet_dataset(ROOT)
    packet = assemble_financial_intelligence_packet(
        entity=dataset.entity,
        ledger=dataset.ledger,
        filing_metadata=dataset.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=dataset.registry,
        context=dataset.context,
        input_digests=dataset.input_digests,
    )
    assert response.content == canonical_packet_bytes(packet)
    assert payload == packet
    assert payload["packet_id"] == packet["packet_id"]
    assert payload["content_sha256"] == packet["content_sha256"]
    assert payload["content_sha256"] == packet_digest(payload)
    assert payload["packet_id"] == "fip_" + payload["content_sha256"][:24]
    assert payload["entity"]["entity_id"] == "mmx.issuer.fip1"
    assert payload["entity"]["cik"] == "0000999999"
    assert payload["entity"]["source_entity_id"] == "0000999999"


def test_customercount_http_is_200_with_unsupported_cells(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _PACKET_PATH,
        content=_make_request(metric_ids=["CustomerCount"]),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    cells = [cell for cell in payload["cells"] if cell["metric_id"] == "CustomerCount"]
    assert cells
    assert all(cell["non_value_state"] == "unsupported" for cell in cells)
    assert all(cell["value"] is None for cell in cells)


def test_t2_http_does_not_leak_revision(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _PACKET_PATH,
        content=_make_request(
            policy={
                "selection": "latest_known_as_of",
                "source_snapshot_at": T2_SOURCE,
                "recorded_at": T2_RECORDED,
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["revisions"] == []
    assert b"1060" not in response.content


def test_default_provider_returns_503(paid_client) -> None:
    response = paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial packet temporarily unavailable")


def test_source_misbound_dataset_returns_503(paid_client, monkeypatch) -> None:
    fip1 = fip1_packet_dataset(ROOT)
    misbound = FinancialPacketDataset(
        binding=CanonicalEntityBinding(
            entity_id="mmx.issuer.fip1",
            cik="0000111111",
            ticker="FIP1",
            source_entity_id="0000111111",
        ),
        entity=fip1.entity,
        ledger=fip1.ledger,
        filing_metadata=fip1.filing_metadata,
        registry=fip1.registry,
        context=fip1.context,
        input_digests=fip1.input_digests,
    )

    class _SourceMisbound:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return misbound

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", lambda: _SourceMisbound())
    response = paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial packet temporarily unavailable")


def test_same_source_wrong_canonical_entity_returns_503(paid_client, monkeypatch) -> None:
    fip1 = fip1_packet_dataset(ROOT)
    misbound = FinancialPacketDataset(
        binding=fip1.binding,
        entity=EntityInput(
            entity_id="mmx.issuer.other",
            cik="0000999999",
            ticker="FIP1",
            name=fip1.entity.name,
            identity_basis=fip1.entity.identity_basis,
            source_entity_id="0000999999",
        ),
        ledger=fip1.ledger,
        filing_metadata=fip1.filing_metadata,
        registry=fip1.registry,
        context=fip1.context,
        input_digests=fip1.input_digests,
    )

    class _WrongCanonical:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return misbound

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", lambda: _WrongCanonical())
    response = paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial packet temporarily unavailable")


def test_repeat_request_is_byte_deterministic(fip1_paid_client, monkeypatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    r1 = fip1_paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    r2 = fip1_paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert r1.status_code == 200
    assert r1.content == r2.content
    assert r1.headers["x-fif-response-sha256"] == r2.headers["x-fif-response-sha256"]
    assert r1.json()["packet_id"] == r2.json()["packet_id"]
    assert r1.json()["content_sha256"] == r2.json()["content_sha256"]


def test_oversized_body_returns_413_provider_not_opened(paid_client, monkeypatch) -> None:
    created: list[str] = []
    resolve_calls: list = []

    def _factory():
        created.append("opened")
        return _fip1_provider(resolve_calls)

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", _factory)
    big_body = b"x" * 65537
    response = paid_client.post(
        _PACKET_PATH,
        content=big_body,
        headers={"content-type": "application/json", "content-length": str(len(big_body))},
    )
    _assert_error(response, 413)
    assert created == []
    assert resolve_calls == []


def test_no_content_length_oversize_returns_413_without_opening_provider(
    router_app, monkeypatch
) -> None:
    created: list[str] = []

    def _factory():
        created.append("opened")
        return _fip1_provider()

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", _factory)
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    status, _headers, body = _asgi_post(
        router_app,
        _PACKET_PATH,
        body=b"x" * 70000,
        extra_headers=[(b"content-type", b"application/json")],
    )
    assert status == 413
    assert b"request body exceeds bound" in body
    assert created == []


def test_non_json_content_type_returns_400_without_opening_provider(
    paid_client, monkeypatch
) -> None:
    created: list[str] = []

    def _factory():
        created.append("opened")
        return _fip1_provider()

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", _factory)
    response = paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "text/plain"},
    )
    _assert_error(response, 400, "malformed request")
    assert created == []


def test_duplicate_period_label_returns_400_provider_not_opened(
    paid_client, monkeypatch
) -> None:
    created: list[str] = []
    resolve_calls: list = []

    def _factory():
        created.append("opened")
        return _fip1_provider(resolve_calls)

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", _factory)
    response = paid_client.post(
        _PACKET_PATH,
        content=_make_request(
            periods=[
                {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"},
                {"kind": "duration", "start": "2024-01-01", "end": "2024-12-31", "label": "FY2023"},
            ]
        ),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "request contract violation")
    assert created == []
    assert resolve_calls == []


def test_multihop_intermediate_http_shows_b_hides_c(paid_client, monkeypatch) -> None:
    dataset = packet_dataset_from_fixture(ROOT, build_multihop_revenue_fixture())

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return dataset

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", lambda: _Provider())
    mid = paid_client.post(
        _PACKET_PATH,
        content=_make_request(
            policy={
                "selection": "latest_known_as_of",
                "source_snapshot_at": HOP_C_SOURCE,
                "recorded_at": HOP_B_SYSTEM_READY,
            }
        ),
        headers={"content-type": "application/json"},
    )
    mid_packet = assemble_financial_intelligence_packet(
        entity=dataset.entity,
        ledger=dataset.ledger,
        filing_metadata=dataset.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=HOP_C_SOURCE,
                recorded_at=HOP_B_SYSTEM_READY,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=dataset.registry,
        context=dataset.context,
        input_digests=dataset.input_digests,
    )
    assert mid.status_code == 200
    assert mid.content == canonical_packet_bytes(mid_packet)
    hops = {
        row["revision_hop"]: row
        for row in mid.json()["revisions"]
        if row["metric_id"] == "revenue"
    }
    assert 1 in hops
    assert 2 not in hops
    assert hops[1]["revised_value"] == "1060"
    assert b"1070" not in mid.content

    later = paid_client.post(
        _PACKET_PATH,
        content=_make_request(
            policy={
                "selection": "latest_known_as_of",
                "source_snapshot_at": HOP_C_SOURCE,
                "recorded_at": T3_RECORDED,
            }
        ),
        headers={"content-type": "application/json"},
    )
    assert later.status_code == 200
    later_hops = {
        row["revision_hop"]: row
        for row in later.json()["revisions"]
        if row["metric_id"] == "revenue"
    }
    assert later_hops[2]["revised_value"] == "1070"


def test_delayed_mapping_http_before_and_after(paid_client, monkeypatch) -> None:
    from tests.test_fundamental_forensics_financial_intelligence_packet_r3 import (
        FUTURE_CONCEPT_QNAME,
        _mini_revision_fixture,
        _register_future_concept,
        _registry_with_future_revenue_mapping,
    )

    _register_future_concept(monkeypatch)
    fixture = _mini_revision_fixture(
        child_recorded="2026-08-04T12:00:00Z",
        parent_recorded="2024-02-15T16:05:00Z",
        concept=FUTURE_CONCEPT_QNAME,
    )
    dataset = replace(
        packet_dataset_from_fixture(ROOT, fixture),
        registry=_registry_with_future_revenue_mapping(datetime(2026, 8, 6, tzinfo=timezone.utc)),
    )

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialPacketDataset:
            return dataset

    monkeypatch.setattr(forensics_api, "_financial_packet_provider", lambda: _Provider())
    before = paid_client.post(
        _PACKET_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    before_packet = assemble_financial_intelligence_packet(
        entity=dataset.entity,
        ledger=dataset.ledger,
        filing_metadata=dataset.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=T3_RECORDED,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=dataset.registry,
        context=dataset.context,
        input_digests=dataset.input_digests,
    )
    assert before.status_code == 200
    assert before.content == canonical_packet_bytes(before_packet)
    assert before.json()["revisions"] == []

    after = paid_client.post(
        _PACKET_PATH,
        content=_make_request(
            policy={
                "selection": "latest_known_as_of",
                "source_snapshot_at": T3_SOURCE,
                "recorded_at": DELAYED_MAPPING_AFTER,
            }
        ),
        headers={"content-type": "application/json"},
    )
    after_packet = assemble_financial_intelligence_packet(
        entity=dataset.entity,
        ledger=dataset.ledger,
        filing_metadata=dataset.filing_metadata,
        query_request=PacketQueryRequest(
            policy=QueryPolicy(
                source_snapshot_at=T3_SOURCE,
                recorded_at=DELAYED_MAPPING_AFTER,
                selection="latest_known_as_of",
            ),
            metrics=("revenue",),
            periods=(PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),),
        ),
        metric_registry=dataset.registry,
        context=dataset.context,
        input_digests=dataset.input_digests,
    )
    assert after.status_code == 200
    assert after.content == canonical_packet_bytes(after_packet)
    rows = [row for row in after.json()["revisions"] if row["metric_id"] == "revenue"]
    assert len(rows) == 1
    assert rows[0]["root_value"] == "1050"
    assert rows[0]["revised_value"] == "1060"


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE", "HEAD"])
def test_non_post_is_private_405(fip1_paid_client, method: str) -> None:
    response = fip1_paid_client.request(method, _PACKET_PATH)
    assert response.status_code == 405
    _assert_private_headers(response)
