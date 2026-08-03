"""Public Company Intelligence teaser API contract tests.

The reader's immutable-generation verification is tested separately.  These
tests pin the browser boundary: one latest event only, no transport/corpus
locators, useful evidence labels, per-client throttling, and cache behavior.
"""
from __future__ import annotations

import json

import pytest


pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

from app import company_intelligence as company_intelligence_api  # noqa: E402
from app.main import app  # noqa: E402


NO_STORE = "private, no-store"
PUBLIC_CACHE = "public, max-age=300, stale-while-revalidate=900"


def _success_projection() -> dict:
    return {
        "available": True,
        "ticker": "AAPL",
        "company": {"ticker": "AAPL", "display_name": "Apple Inc.", "exchange": None},
        "schema": "company_intelligence_context.v1",
        "generation_id": "a" * 24,
        "generated_at": "2026-08-02T00:00:00Z",
        "status": "degraded",
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
        "untrusted_source_data": True,
        "latest_event": {
            "event_id": "AAPL:2026Q2",
            "fiscal_year": 2026,
            "fiscal_quarter": 2,
            "call_date": "2026-07-31",
            "summary": "Revenue grew on iPhone demand.",
            "key_quote": "We saw broad-based demand.",
            "positive_highlights": ["Revenue grew 10% year over year."],
            "negative_highlights": ["Foreign exchange remained a headwind."],
            "tags": ["revenue_growth"],
            "metrics": {
                "revenue_growth_pct": 10.0,
                "eps_growth_pct": 12.5,
                "gross_margin_pct": 45.0,
                "questions_count": 18,
                "sentiment": 0.8,
                "performance": 0.7,
                "confidence": 0.9,
                "combined": 0.8,
                "call_positivity": 0.75,
                "management_confidence": 0.82,
                "analyst_criticism": 0.12,
                "future_outlook": 0.73,
                "analysts_count": 22,
                "secret_metric": 99,
            },
            "field_lineage": {
                "summary": "earnings_history",
                "metrics": {
                    "revenue_growth_pct": "earnings_history",
                    "eps_growth_pct": "earnings_history",
                    "gross_margin_pct": "earnings_history",
                    "questions_count": "earnings_history",
                    "sentiment": "score_overlay",
                    "combined": "score_overlay",
                    "secret_metric": "raw",
                },
                "tags": {"revenue_growth": "earnings_history", "secret_tag": "raw"},
                "internal": "must not leak",
            },
            "previous_event_deltas": {
                "revenue_growth_pct": 2.0,
                "eps_growth_pct": 1.5,
                "gross_margin_pct": 0.5,
                "questions_count": -2,
                "sentiment": 0.2,
                "combined": 0.1,
                "secret_metric": 999,
            },
            "sources": [
                {
                    "source_ref": "transcript",
                    "kind": "transcript",
                    "status": "present",
                    "citation_precision": "document",
                    "url": "https://private.example/generations/aapl.json",
                    "receipt": {"source_hash": "b" * 64, "object_key": "data/private/aapl"},
                }
            ],
            "claim_citations_pending": True,
            "raw_context": {"prompt": "latest-secret"},
        },
        "history": [{"event_id": "AAPL:2026Q1", "internal_receipt": {"token": "history-secret"}}],
        "topics": {"timeline": [{"tag": "secret-topic"}], "added": ["secret-topic"]},
        "source_completeness": {"transcripts": {"status": "partial", "event_count": 2}},
        "warnings": ["transcripts_partial"],
        "missing_sources": ["transcripts_for_some_events"],
        "receipt": {
            "marker_url": "https://private.example/manifest.json",
            "immutable_manifest_url": "https://private.example/generation.json",
            "marker_sha256": "c" * 64,
            "company_url": "https://private.example/aapl.json",
            "company_sha256": "d" * 64,
            "object_key": "generations/a/aapl.json",
        },
        "note": "Verified company event context only.",
        # A deliberately unknown future/internal field must never reach the
        # browser just because a reader return value grows.
        "internal_only": {"raw_context": "must not leak"},
    }


@pytest.fixture
def client() -> TestClient:
    company_intelligence_api._reset_rate_limit_for_tests()
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client
    company_intelligence_api._reset_rate_limit_for_tests()


def test_company_intelligence_is_a_one_event_cacheable_teaser(client, monkeypatch) -> None:
    calls: list[dict] = []

    def fake_reader(params: dict) -> dict:
        calls.append(params)
        return _success_projection()

    monkeypatch.setattr(company_intelligence_api, "_read_company_intelligence", fake_reader)

    response = client.get("/api/company-intelligence/aapl?limit=12")

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == PUBLIC_CACHE
    assert calls == [{"ticker": "AAPL", "limit": 1}]
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["latest_event"]["event_id"] == "AAPL:2026Q2"
    assert payload["latest_event"]["metrics"] == {
        "revenue_growth_pct": 10.0,
        "eps_growth_pct": 12.5,
        "gross_margin_pct": 45.0,
        "questions_count": 18,
    }
    assert payload["latest_event"]["previous_event_deltas"] == {
        "revenue_growth_pct": 2.0,
        "eps_growth_pct": 1.5,
        "gross_margin_pct": 0.5,
        "questions_count": -2,
    }
    assert payload["latest_event"]["sources"] == [{
        "kind": "transcript", "status": "present", "citation_precision": "document",
    }]
    assert "history" not in payload
    assert "topics" not in payload
    assert "source_completeness" not in payload
    assert "receipt" not in payload
    assert "generation_id" not in payload


def test_company_intelligence_recursively_withholds_transport_and_internal_fields(client, monkeypatch) -> None:
    reader_result = _success_projection()
    reader_result["company"]["internal_id"] = "company-secret"
    reader_result["latest_event"]["sources"][0]["object_key"] = "source-object-secret"

    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: reader_result,
    )

    response = client.get("/api/company-intelligence/AAPL")

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["company"] == {
        "ticker": "AAPL",
        "display_name": "Apple Inc.",
        "exchange": None,
    }
    assert payload["latest_event"]["field_lineage"] == {
        "summary": "earnings_history",
        "metrics": {
            "revenue_growth_pct": "earnings_history",
            "eps_growth_pct": "earnings_history",
            "gross_margin_pct": "earnings_history",
            "questions_count": "earnings_history",
        },
        "tags": {"revenue_growth": "earnings_history"},
    }
    serialized = json.dumps(payload, sort_keys=True)
    for forbidden in (
        "private.example",
        "history-secret",
        "secret-topic",
        "company-secret",
        "latest-secret",
        "source-object-secret",
        "object_key",
        "source_hash",
        "marker_sha256",
        "company_sha256",
        "marker_url",
        "immutable_manifest_url",
        "company_url",
        "source_ref",
        "raw_context",
        "secret_metric",
        "sentiment",
        "performance",
        "confidence",
        "combined",
        "call_positivity",
        "management_confidence",
        "analyst_criticism",
        "future_outlook",
        "analysts_count",
    ):
        assert forbidden not in serialized


@pytest.mark.parametrize("requested_limit", ["1", "8", "12"])
def test_company_intelligence_never_forwards_requested_history_depth(client, monkeypatch, requested_limit) -> None:
    calls: list[dict] = []

    def fake_reader(params: dict) -> dict:
        calls.append(params)
        return _success_projection()

    monkeypatch.setattr(company_intelligence_api, "_read_company_intelligence", fake_reader)

    response = client.get(f"/api/company-intelligence/AAPL?limit={requested_limit}")

    assert response.status_code == 200, response.text
    assert calls == [{"ticker": "AAPL", "limit": 1}]
    assert "history" not in response.json()


@pytest.mark.parametrize("limit", ["0", "13", "not-a-number"])
def test_company_intelligence_rejects_invalid_history_limit(client, monkeypatch, limit) -> None:
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: (_ for _ in ()).throw(AssertionError("reader must not run")),
    )

    response = client.get(f"/api/company-intelligence/AAPL?limit={limit}")

    assert response.status_code == 422
    assert response.headers.get("cache-control") == NO_STORE


def test_company_intelligence_rate_limits_one_client_and_errors_are_not_cached(client, monkeypatch) -> None:
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: _success_projection(),
    )
    headers = {"EO-Client-IP": "203.0.113.7"}

    for _ in range(company_intelligence_api._RATE_LIMIT_REQUESTS):
        response = client.get("/api/company-intelligence/AAPL", headers=headers)
        assert response.status_code == 200
        assert response.headers.get("cache-control") == PUBLIC_CACHE

    limited = client.get("/api/company-intelligence/AAPL", headers=headers)
    assert limited.status_code == 429
    assert limited.headers.get("cache-control") == NO_STORE
    assert limited.headers.get("retry-after") == "60"


def test_company_intelligence_peer_backstop_stops_rotating_claimed_edge_ips(client, monkeypatch) -> None:
    """The X-MM-Peer value below represents Caddy's overwritten upstream header.

    A client can fabricate a fresh EO-Client-IP at the origin, but Caddy
    replaces any inbound X-MM-Peer with the TCP peer before the app sees it.
    The app may therefore trust this one header as a looser shared backstop.
    """
    monkeypatch.setattr(company_intelligence_api, "_PEER_RATE_LIMIT_REQUESTS", 3)
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: _success_projection(),
    )
    trusted_peer = "caddy-overwritten-peer-198.51.100.9"

    for suffix in range(3):
        response = client.get("/api/company-intelligence/AAPL", headers={
            # Each claimed IP is intentionally different, simulating a forged
            # EO/CF header at origin.  The post-Caddy peer is unchanged.
            "EO-Client-IP": f"203.0.113.{suffix + 1}",
            "X-MM-Peer": trusted_peer,
        })
        assert response.status_code == 200, response.text

    blocked = client.get("/api/company-intelligence/AAPL", headers={
        "EO-Client-IP": "203.0.113.250",
        "X-MM-Peer": trusted_peer,
    })
    assert blocked.status_code == 429
    assert blocked.headers.get("cache-control") == NO_STORE


def test_company_intelligence_rejects_unsafe_ticker_before_reader(client, monkeypatch) -> None:
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: (_ for _ in ()).throw(AssertionError("reader must not run")),
    )

    response = client.get("/api/company-intelligence/AAPL..")

    assert response.status_code == 422
    assert response.headers.get("cache-control") == NO_STORE
    assert "ticker must be" in response.json()["detail"]


def test_company_intelligence_maps_known_coverage_absence_to_404(client, monkeypatch) -> None:
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: {
            "available": False,
            "ticker": "MISSING",
            "note": "Company Intelligence does not cover this ticker",
        },
    )

    response = client.get("/api/company-intelligence/missing")

    assert response.status_code == 404
    assert response.headers.get("cache-control") == NO_STORE
    assert response.json() == {"detail": "Company Intelligence is not available for MISSING."}


def test_company_intelligence_maps_verification_failure_to_503_without_internal_note(client, monkeypatch) -> None:
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda _params: {
            "available": False,
            "ticker": "AAPL",
            "note": "Company Intelligence context failed immutable receipt verification",
        },
    )

    response = client.get("/api/company-intelligence/AAPL")

    assert response.status_code == 503
    assert response.headers.get("cache-control") == NO_STORE
    assert response.json() == {"detail": "Company Intelligence is temporarily unavailable."}


def test_company_intelligence_maps_unexpected_reader_exception_to_503(client, monkeypatch) -> None:
    def fail(_params: dict) -> dict:
        raise RuntimeError("unexpected upstream problem")

    monkeypatch.setattr(company_intelligence_api, "_read_company_intelligence", fail)

    response = client.get("/api/company-intelligence/AAPL")

    assert response.status_code == 503
    assert response.headers.get("cache-control") == NO_STORE
    assert response.json() == {"detail": "Company Intelligence is temporarily unavailable."}
