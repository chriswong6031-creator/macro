"""FIF-2A API tests: HTTP transport, auth, private headers, determinism, error paths."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.forensics as forensics_api
from engine.fundamental_forensics.financial_intelligence_packet import canonical_json
from engine.fundamental_forensics.query import PeriodRequest, QueryBounds, QueryPolicy, BitemporalMetricQueryEngine
from engine.fundamental_forensics.query_service import (
    FinancialQueryAdmissionError,
    FinancialQueryDataset,
    FinancialQueryUnavailableError,
    UnavailableFinancialQueryProvider,
    fip1_fixture_dataset,
)

ROOT = Path(__file__).resolve().parents[1]
_QUERY_PATH = "/api/forensics/v1/financial/query"

T0_SOURCE = "2024-01-01T00:00:00Z"
T1_SOURCE = "2024-12-31T23:59:59Z"
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
    schema: str = "fundamental_forensics.financial_query_request/v1",
    entity_id: str = "mmx.issuer.fip1",
    policy: dict | None = None,
    metric_ids: list | None = None,
    periods: list | None = None,
) -> bytes:
    if policy is None:
        policy = {
            "selection": "latest_known_as_of",
            "source_snapshot_at": T1_SOURCE,
            "recorded_at": T2_RECORDED,
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


def _fip1_provider(resolve_calls: list | None = None):
    dataset = fip1_fixture_dataset(ROOT)

    class _Provider:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            if resolve_calls is not None:
                resolve_calls.append(entity_id)
            if entity_id == "mmx.issuer.fip1":
                return dataset
            raise FinancialQueryAdmissionError(400, "unknown entity")

    return _Provider()


# ---------------------------------------------------------------------------
# Fixtures: router-only app vs production app
# ---------------------------------------------------------------------------


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
    """Paid client with FIP1 provider injected."""
    router_app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    monkeypatch.setattr(forensics_api, "_financial_query_provider", _fip1_provider)
    with TestClient(router_app, raise_server_exceptions=False) as client:
        yield client


# ---------------------------------------------------------------------------
# Auth / entitlement guards
# ---------------------------------------------------------------------------


def test_anonymous_post_returns_401_with_private_headers(anon_client, monkeypatch) -> None:
    resolve_calls: list = []
    monkeypatch.setattr(
        forensics_api,
        "_financial_query_provider",
        lambda: _fip1_provider(resolve_calls),
    )
    response = anon_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401
    _assert_private_headers(response)
    assert resolve_calls == [], "provider.resolve must not be called before auth"


def test_free_user_returns_403_with_private_headers(router_app, monkeypatch) -> None:
    """Free user (require_user ok, enforce_site_full deny) gets 403; private headers apply."""
    from fastapi import HTTPException
    import app.main as app_main
    import app.paywall as paywall_mod

    resolve_calls: list = []
    monkeypatch.setattr(forensics_api, "_financial_query_provider", lambda: _fip1_provider(resolve_calls))

    # Do NOT override require_site_full_user — monkeypatch the underlying callees.
    monkeypatch.setattr(app_main, "require_user", lambda auth: {"id": "free-user", "tier": "free"})
    monkeypatch.setattr(
        paywall_mod,
        "enforce_site_full",
        lambda user, always=False: (_ for _ in ()).throw(HTTPException(status_code=403, detail="site_full required")),
    )

    with TestClient(router_app, raise_server_exceptions=False) as client:
        response = client.post(
            _QUERY_PATH,
            content=_make_request(),
            headers={"content-type": "application/json"},
        )
    assert response.status_code == 403
    _assert_private_headers(response)
    assert resolve_calls == [], "provider.resolve must not be called before entitlement"


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


def test_paid_fip1_200_with_private_headers_and_sha256(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    sha256_header = response.headers.get("x-fif-response-sha256")
    assert sha256_header is not None
    computed = hashlib.sha256(response.content).hexdigest()
    assert sha256_header == computed


def test_paid_fip1_receipt_equals_direct_matrix(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(
            metric_ids=["revenue", "gross_margin"],
            periods=[{"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"}],
            policy={"selection": "latest_known_as_of", "source_snapshot_at": T1_SOURCE, "recorded_at": T2_RECORDED},
        ),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    envelope = response.json()

    dataset = fip1_fixture_dataset(ROOT)
    binding = dataset.binding
    policy = QueryPolicy(source_snapshot_at=T1_SOURCE, recorded_at=T2_RECORDED, selection="latest_known_as_of")
    engine = BitemporalMetricQueryEngine(
        ledger=dataset.ledger,
        registry=dataset.registry,
        entities={binding.ticker: binding.source_entity_id},
        filing_metadata=dataset.filing_metadata,
        bounds=QueryBounds(max_tickers=1, max_metrics=50, max_periods=8, max_cells=400),
    )
    matrix = engine.query_matrix(
        tickers=[binding.ticker],
        metrics=["revenue", "gross_margin"],
        periods=[PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")],
        policy=policy,
    )
    assert envelope["receipt"] == matrix.to_dict()
    assert envelope["receipt"]["query_hash"] == matrix.query_hash


@pytest.mark.parametrize(
    ("selection", "source", "recorded"),
    [
        ("as_reported", T1_SOURCE, T2_RECORDED),
        ("latest_known_as_of", T3_SOURCE, T3_RECORDED),
        ("latest_restated", T3_SOURCE, T3_RECORDED),
    ],
)
def test_http_receipt_equals_direct_matrix_for_each_policy(
    fip1_paid_client, selection: str, source: str, recorded: str
) -> None:
    body = _make_request(
        metric_ids=["revenue"],
        policy={"selection": selection, "source_snapshot_at": source, "recorded_at": recorded},
    )
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=body,
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    dataset = fip1_fixture_dataset(ROOT)
    binding = dataset.binding
    matrix = BitemporalMetricQueryEngine(
        ledger=dataset.ledger,
        registry=dataset.registry,
        entities={binding.ticker: binding.source_entity_id},
        filing_metadata=dataset.filing_metadata,
        bounds=QueryBounds(max_tickers=1, max_metrics=50, max_periods=8, max_cells=400),
    ).query_matrix(
        tickers=[binding.ticker],
        metrics=["revenue"],
        periods=[PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023")],
        policy=QueryPolicy(source_snapshot_at=source, recorded_at=recorded, selection=selection),
    )
    envelope = response.json()
    assert envelope["receipt"] == matrix.to_dict()
    assert envelope["receipt"]["query_hash"] == matrix.query_hash


def test_paid_fip1_response_content_is_canonical_envelope_bytes(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    envelope = response.json()
    canonical = canonical_json(envelope).encode("utf-8")
    assert response.content == canonical


def test_repeated_identical_request_produces_identical_bytes_and_sha(fip1_paid_client, monkeypatch) -> None:
    monkeypatch.setattr(time, "time", lambda: 1_700_000_000.0)
    r1 = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    monkeypatch.setattr(time, "time", lambda: 1_800_000_000.0)
    r2 = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.content == r2.content
    assert r1.headers["x-fif-response-sha256"] == r2.headers["x-fif-response-sha256"]


# ---------------------------------------------------------------------------
# 400 error paths
# ---------------------------------------------------------------------------


def _assert_error(response, status_code: int, detail_fragment: str | None = None) -> None:
    assert response.status_code == status_code
    _assert_private_headers(response)
    body = response.json()
    if detail_fragment:
        assert detail_fragment in body.get("detail", "")
    # Must not contain any internal paths, R2 keys, user ids, or stack traces
    detail_str = str(body)
    for forbidden in ("/Users/", "/opt/", "traceback", "Traceback", "R2", "paid-user"):
        assert forbidden not in detail_str, f"Leaked content in error: {forbidden!r}"


def test_malformed_json_returns_400(paid_client) -> None:
    response = paid_client.post(
        _QUERY_PATH,
        content=b"{broken json",
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "malformed")


def test_duplicate_keys_returns_400(paid_client) -> None:
    response = paid_client.post(
        _QUERY_PATH,
        content=b'{"schema":"fundamental_forensics.financial_query_request/v1","entity_id":"mmx.issuer.fip1","entity_id":"dup","policy":{"selection":"latest_known_as_of","source_snapshot_at":"2024-12-31T23:59:59Z","recorded_at":"2026-08-03T12:00:00Z"},"metric_ids":["revenue"],"periods":[{"kind":"duration","start":"2023-01-01","end":"2023-12-31","label":"FY2023"}]}',
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "duplicate json key")


def test_invalid_policy_returns_400(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(policy={
            "selection": "invalid_policy",
            "source_snapshot_at": T1_SOURCE,
            "recorded_at": T2_RECORDED,
        }),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "invalid policy")


def test_missing_cutoff_returns_400(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(policy={
            "selection": "latest_known_as_of",
            "source_snapshot_at": "",
            "recorded_at": T2_RECORDED,
        }),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "missing cutoff")


def test_unsupported_metric_returns_400(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(metric_ids=["not_a_real_metric_xyz_9999"]),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "unsupported metric")


def test_duplicate_metric_returns_400(paid_client, monkeypatch) -> None:
    monkeypatch.setattr(forensics_api, "_financial_query_provider", _fip1_provider)
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(metric_ids=["revenue", "revenue"]),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "duplicate metric")


def test_duplicate_period_returns_400(paid_client, monkeypatch) -> None:
    monkeypatch.setattr(forensics_api, "_financial_query_provider", _fip1_provider)
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(periods=[
            {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023"},
            {"kind": "duration", "start": "2023-01-01", "end": "2023-12-31", "label": "FY2023-copy"},
        ]),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "duplicate period")


def test_wrong_content_type_returns_400(paid_client) -> None:
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "text/plain"},
    )
    _assert_error(response, 400, "malformed request")


def test_wrong_method_returns_405_with_private_headers(fip1_paid_client) -> None:
    response = fip1_paid_client.get(_QUERY_PATH)
    _assert_error(response, 405, "method not allowed")


def test_misbound_provider_returns_503(paid_client, monkeypatch) -> None:
    fip1 = fip1_fixture_dataset(ROOT)

    class _Misbound:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            return fip1

    monkeypatch.setattr(forensics_api, "_financial_query_provider", lambda: _Misbound())
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(entity_id="mmx.issuer.someoneelse"),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial query temporarily unavailable")
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "text/plain"},
    )
    _assert_error(response, 400, "malformed request")


# ---------------------------------------------------------------------------
# 413 paths
# ---------------------------------------------------------------------------


def test_oversized_body_returns_413_provider_not_opened(paid_client, monkeypatch) -> None:
    resolve_calls: list = []
    monkeypatch.setattr(
        forensics_api,
        "_financial_query_provider",
        lambda: _fip1_provider(resolve_calls),
    )
    big_body = b"x" * 65537
    response = paid_client.post(
        _QUERY_PATH,
        content=big_body,
        headers={"content-type": "application/json", "content-length": str(len(big_body))},
    )
    _assert_error(response, 413)
    assert resolve_calls == []


# ---------------------------------------------------------------------------
# 503 paths
# ---------------------------------------------------------------------------


def test_default_unavailable_provider_returns_503(paid_client) -> None:
    """Paid user, no FIP1 inject → default UnavailableFinancialQueryProvider → 503."""
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial query temporarily unavailable")
    # Must not contain exception text
    assert "UnavailableFinancialQueryProvider" not in response.text
    assert "FinancialQueryUnavailableError" not in response.text


def test_provider_generic_exception_returns_503_no_leak(paid_client, monkeypatch) -> None:
    class _BrokenProvider:
        def resolve(self, entity_id: str) -> FinancialQueryDataset:
            raise RuntimeError("secret internal path /data/private/stuff")

    monkeypatch.setattr(forensics_api, "_financial_query_provider", lambda: _BrokenProvider())
    response = paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 503, "financial query temporarily unavailable")
    assert "secret internal path" not in response.text


# ---------------------------------------------------------------------------
# Production app integration: unauthenticated POST → 401 not 404
# ---------------------------------------------------------------------------


def test_production_app_unauthenticated_post_returns_401() -> None:
    import app.main as main_mod

    client = TestClient(main_mod.app, raise_server_exceptions=False)
    response = client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 401
    _assert_private_headers(response)


# ---------------------------------------------------------------------------
# No credential / key / user identity leakage in 200 response
# ---------------------------------------------------------------------------


def test_200_response_contains_no_credentials_or_user_id(fip1_paid_client) -> None:
    response = fip1_paid_client.post(
        _QUERY_PATH,
        content=_make_request(),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    text = response.text
    for forbidden in ("paid-user", "R2", "r2.cloudflarestorage", "/opt/", "/Users/", "Bearer", "AKIA"):
        assert forbidden not in text, f"Leaked {forbidden!r} in 200 response"
