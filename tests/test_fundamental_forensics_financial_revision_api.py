"""FIF-2B API tests: HTTP transport, auth, private headers, determinism."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.forensics as forensics_api
from engine.fundamental_forensics.financial_intelligence_packet import (
    PacketQueryRequest,
    assemble_financial_intelligence_packet,
    canonical_json,
)
from engine.fundamental_forensics.query import PeriodRequest, QueryPolicy
from engine.fundamental_forensics.query_service import (
    CanonicalEntityBinding,
    FinancialQueryAdmissionError,
)
from engine.fundamental_forensics.revision_service import (
    FinancialPacketDataset,
    fip1_packet_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
_REVISIONS_PATH = "/api/forensics/v1/financial/revisions"
_REVISION_SCHEMA = "fundamental_forensics.financial_revision_request/v1"

T2_SOURCE = "2025-12-31T23:59:59Z"
T2_RECORDED = "2026-08-03T12:00:00Z"
T3_SOURCE = "2025-12-31T23:59:59Z"
T3_RECORDED = "2026-08-05T12:00:02Z"

_EXPECTED_PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _make_request(
    *,
    schema: str = _REVISION_SCHEMA,
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
def paid_client(router_app, monkeypatch) -> TestClient:
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    with TestClient(router_app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def fip1_paid_client(router_app, monkeypatch) -> TestClient:
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    monkeypatch.setattr(forensics_api, "_financial_revision_provider", _fip1_provider)
    with TestClient(router_app, raise_server_exceptions=False) as client:
        yield client


def test_anonymous_post_returns_401_with_private_headers(anon_client, monkeypatch) -> None:
    resolve_calls: list = []
    monkeypatch.setattr(
        forensics_api,
        "_financial_revision_provider",
        lambda: _fip1_provider(resolve_calls),
    )
    response = anon_client.post(
        _REVISIONS_PATH,
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
        forensics_api, "_financial_revision_provider", lambda: _fip1_provider(resolve_calls)
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
            _REVISIONS_PATH,
            content=_make_request(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 403
    _assert_private_headers(response)
    assert resolve_calls == []


def test_success_returns_canonical_revisions_and_sha(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _REVISIONS_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    sha256_header = response.headers.get("x-fif-response-sha256")
    assert sha256_header == hashlib.sha256(response.content).hexdigest()
    payload = response.json()
    assert payload["schema"] == "fundamental_forensics.financial_revision_response/v1"
    assert canonical_json(payload).encode("utf-8") == response.content
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
    assert payload["revisions"] == packet["revisions"]
    assert payload["packet_ref"]["packet_id"] == packet["packet_id"]


def test_t2_http_does_not_leak_revision(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _REVISIONS_PATH,
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
        _REVISIONS_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial revisions temporarily unavailable")


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

    monkeypatch.setattr(forensics_api, "_financial_revision_provider", lambda: _SourceMisbound())
    response = paid_client.post(
        _REVISIONS_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial revisions temporarily unavailable")
    assert response.status_code != 200


def test_unsupported_metric_returns_400(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _REVISIONS_PATH,
        content=_make_request(metric_ids=["not_a_real_metric_xyz"]),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "unsupported metric")


def test_repeat_request_is_byte_deterministic(fip1_paid_client, monkeypatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    r1 = fip1_paid_client.post(
        _REVISIONS_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    r2 = fip1_paid_client.post(
        _REVISIONS_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert r1.status_code == 200
    assert r1.content == r2.content
    assert r1.headers["x-fif-response-sha256"] == r2.headers["x-fif-response-sha256"]
    assert r1.json()["packet_ref"]["packet_id"] == r2.json()["packet_ref"]["packet_id"]
    assert r1.json()["revisions"] == r2.json()["revisions"]


def test_oversized_body_returns_413_provider_not_opened(paid_client, monkeypatch) -> None:
    created: list[str] = []
    resolve_calls: list = []

    def _factory():
        created.append("opened")
        return _fip1_provider(resolve_calls)

    monkeypatch.setattr(forensics_api, "_financial_revision_provider", _factory)
    big_body = b"x" * 65537
    response = paid_client.post(
        _REVISIONS_PATH,
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

    monkeypatch.setattr(forensics_api, "_financial_revision_provider", _factory)
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    status, _headers, body = _asgi_post(
        router_app,
        _REVISIONS_PATH,
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

    monkeypatch.setattr(forensics_api, "_financial_revision_provider", _factory)
    response = paid_client.post(
        _REVISIONS_PATH,
        content=_make_request(),
        headers={"content-type": "text/plain"},
    )
    _assert_error(response, 400, "malformed request")
    assert created == []


def test_get_is_private_405(fip1_paid_client) -> None:
    response = fip1_paid_client.get(_REVISIONS_PATH)
    assert response.status_code == 405
    _assert_private_headers(response)
