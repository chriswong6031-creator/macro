"""FIF-3A1 API tests: auth, private headers, golden AAPL statement consumer."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.forensics as forensics_api
from engine.fundamental_forensics.statement_service import GoldenAaplStatementProvider

ROOT = Path(__file__).resolve().parents[1]
_PATH = "/api/forensics/v1/financial/statements"
_SCHEMA = "fundamental_forensics.financial_statement_request/v1"
_RESPONSE_SHA = "25e5562e81cb80bd42d0feb544c212c4471e11736601aaee418a60981a457184"

_EXPECTED_PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _body(
    *,
    entity_id: str = "ISS:US-XNAS-AAPL",
    accession: str = "0000320193-25-000079",
) -> bytes:
    return json.dumps(
        {"schema": _SCHEMA, "entity_id": entity_id, "accession": accession},
        separators=(",", ":"),
    ).encode("utf-8")


def _assert_private_headers(response) -> None:
    for name, expected in _EXPECTED_PRIVATE_HEADERS.items():
        assert response.headers.get(name) == expected, name


def _assert_error(response, status: int, detail: str | None = None) -> None:
    assert response.status_code == status
    _assert_private_headers(response)
    payload = response.json()
    assert "detail" in payload
    if detail is not None:
        assert detail in payload["detail"] or payload["detail"] == detail


@pytest.fixture
def router_app(monkeypatch) -> FastAPI:
    monkeypatch.setattr(forensics_api, "REPO", ROOT)
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


def test_anonymous_post_returns_401_with_private_headers(anon_client, monkeypatch) -> None:
    calls: list[str] = []

    class _P(GoldenAaplStatementProvider):
        def resolve(self, entity_id: str, accession: str):
            calls.append(entity_id)
            raise AssertionError("provider opened before auth")

    monkeypatch.setattr(forensics_api, "_financial_statement_provider", lambda: _P(ROOT))
    response = anon_client.post(_PATH, content=_body(), headers={"content-type": "application/json"})
    assert response.status_code == 401
    _assert_private_headers(response)
    assert calls == []


def test_free_user_returns_403_with_private_headers(router_app, monkeypatch) -> None:
    from fastapi import HTTPException
    import app.main as app_main
    import app.paywall as paywall_mod

    calls: list[str] = []

    class _P(GoldenAaplStatementProvider):
        def resolve(self, entity_id: str, accession: str):
            calls.append(entity_id)
            raise AssertionError("provider opened before entitlement")

    monkeypatch.setattr(forensics_api, "REPO", ROOT)
    monkeypatch.setattr(forensics_api, "_financial_statement_provider", lambda: _P(ROOT))
    monkeypatch.setattr(app_main, "require_user", lambda auth: {"id": "free-user", "tier": "free"})
    monkeypatch.setattr(
        paywall_mod,
        "enforce_site_full",
        lambda user, always=False: (_ for _ in ()).throw(
            HTTPException(status_code=403, detail="site_full required")
        ),
    )
    with TestClient(router_app, raise_server_exceptions=False) as client:
        response = client.post(_PATH, content=_body(), headers={"content-type": "application/json"})
    assert response.status_code == 403
    _assert_private_headers(response)
    assert calls == []


def test_paid_golden_aapl_returns_three_statement_trees(paid_client) -> None:
    response = paid_client.post(_PATH, content=_body(), headers={"content-type": "application/json"})
    assert response.status_code == 200
    _assert_private_headers(response)
    assert response.headers.get("x-fif-response-sha256") == _RESPONSE_SHA
    assert hashlib.sha256(response.content).hexdigest() == _RESPONSE_SHA
    payload = response.json()
    assert payload["schema"] == "fundamental_forensics.financial_statement_response/v1"
    assert payload["entity"]["entity_id"] == "ISS:US-XNAS-AAPL"
    assert payload["entity"]["cik"] == "0000320193"
    assert payload["entity"]["entity_id"] != payload["entity"]["cik"]
    assert payload["filing"]["accession"] == "0000320193-25-000079"
    assert len(payload["statements"]) == 3
    by_type = {item["statement_type"]: item for item in payload["statements"]}
    assert by_type["income_statement"]["row_count"] == 24
    assert by_type["balance_sheet"]["row_count"] == 35
    assert by_type["cash_flow"]["row_count"] == 35
    sales = next(
        row
        for row in by_type["income_statement"]["rows"]
        if row["as_reported_label"] == "Total net sales"
    )
    assert sales["cells"][0]["source_receipt"]["source_span"]
    assert sales["cells"][0]["value"] == "416161000000"
    products = next(
        row
        for row in by_type["income_statement"]["rows"]
        if row["as_reported_label"] == "Products"
        and "RevenueFromContractWithCustomerExcludingAssessedTax" in (row["concept"] or "")
    )
    assert products["cells"][0]["value"] == "307003000000"
    assert products["cells"][0]["dimensions"]
    assert products["standardized_metric_id"] is None
    assert products["mapping_state"] == "unmapped"
    assert sales["standardized_metric_id"] == "revenue"
    assert payload["authority"] == {"class": "context_only", "display_only": True}
    assert payload["delivery"]["kind"] == "committed_golden_fixture"
    assert payload["delivery"]["attested"] is False
    assert payload["delivery"]["production_issuer_service"] is False
    assert "authority" not in payload["delivery"]
    sga = next(
        row
        for row in by_type["income_statement"]["rows"]
        if row["as_reported_label"] == "Selling, general and administrative"
    )
    assert sga["mapping_state"] == "unmapped"
    assert "/api/forensics/v1/financial/trace" not in json.dumps(payload)
    assert "related_event_ref" not in payload
    assert "related_event_ref" not in payload


def test_malformed_json_is_private_400_and_does_not_open_provider(paid_client, monkeypatch) -> None:
    calls: list[str] = []

    class _P(GoldenAaplStatementProvider):
        def resolve(self, entity_id: str, accession: str):
            calls.append(entity_id)
            return super().resolve(entity_id, accession)

    monkeypatch.setattr(forensics_api, "_financial_statement_provider", lambda: _P(ROOT))
    response = paid_client.post(_PATH, content=b"{nope", headers={"content-type": "application/json"})
    _assert_error(response, 400, "malformed")
    assert calls == []


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE", "HEAD"])
def test_non_post_is_private_405(paid_client, method: str) -> None:
    response = paid_client.request(method, _PATH)
    assert response.status_code == 405
    _assert_private_headers(response)


_Q3_ACCESSION = "0000320193-26-000020"
_Q3_RESPONSE_SHA = "b98602a299996ff7ea58b842364031547df795d1458b51134eef0e37159b7918"
_Q3_EVENT_ID = "evt_cik0000320193_2026q3_results"
_Q3_8K_ACCESSION = "0000320193-26-000018"


def test_paid_q3_returns_quarterly_trees_and_event_ref(paid_client) -> None:
    response = paid_client.post(
        _PATH,
        content=_body(accession=_Q3_ACCESSION),
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 200
    _assert_private_headers(response)
    assert response.headers.get("x-fif-response-sha256") == _Q3_RESPONSE_SHA
    payload = response.json()
    assert payload["filing"]["accession"] == _Q3_ACCESSION
    assert payload["filing"]["form"] == "10-Q"
    by_type = {item["statement_type"]: item for item in payload["statements"]}
    assert by_type["income_statement"]["row_count"] == 24
    assert by_type["balance_sheet"]["row_count"] == 36
    assert by_type["cash_flow"]["row_count"] == 35
    income = by_type["income_statement"]
    assert len(income["columns"]) == 4
    assert income["columns"][0]["end"] == income["columns"][2]["end"]
    assert income["columns"][0]["start"] != income["columns"][2]["start"]
    ref = payload["related_event_ref"]
    assert ref["event_id"] == _Q3_EVENT_ID
    assert ref["source_filing_distinction"]["earnings_release_8k_accession"] == _Q3_8K_ACCESSION
    assert ref["source_filing_distinction"]["periodic_report_accession"] == _Q3_ACCESSION
    assert "generation_id" not in ref
    assert payload["authority"] == {"class": "context_only", "display_only": True}
    assert payload["delivery"]["attested"] is False
    assert payload["delivery"]["production_issuer_service"] is False
    a1 = paid_client.post(_PATH, content=_body(), headers={"content-type": "application/json"})
    assert a1.headers.get("x-fif-response-sha256") == _RESPONSE_SHA


def test_paid_results_eight_k_is_unknown_filing(paid_client) -> None:
    response = paid_client.post(
        _PATH,
        content=_body(accession=_Q3_8K_ACCESSION),
        headers={"content-type": "application/json"},
    )
    _assert_error(response, 400, "unknown filing")
