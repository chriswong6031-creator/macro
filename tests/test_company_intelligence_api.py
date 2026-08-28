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
    # EO-Connecting-IP, not EO-Client-IP: the resolver reads only the header the edge
    # overwrites (app/edge_client.py). With the old header this test would still pass —
    # every request would silently key on TestClient's socket host instead — so it would
    # have stopped exercising per-client keying without ever going red.
    headers = {"EO-Connecting-IP": "203.0.113.7"}

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

    A client that reaches the origin DIRECTLY can fabricate a fresh EO-Connecting-IP
    per request — ufw permits 80,443/tcp from Anywhere, and no header check can tell
    that value apart from the edge's. Caddy replaces any inbound X-MM-Peer with the TCP
    peer before the app sees it, which for such a caller is their own address. The app
    may therefore trust this one header as a looser shared backstop, and that backstop
    is the ONLY thing bounding a direct-to-origin rotator.
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
            # Each claimed IP is intentionally different, simulating a direct-to-origin
            # caller forging a fresh real-client header.  The post-Caddy peer is unchanged.
            "EO-Connecting-IP": f"203.0.113.{suffix + 1}",
            "X-MM-Peer": trusted_peer,
        })
        assert response.status_code == 200, response.text

    blocked = client.get("/api/company-intelligence/AAPL", headers={
        "EO-Connecting-IP": "203.0.113.250",
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


# ---------------------------------------------------------------------------
# E2-D: GET /api/event-workspace/{ticker}  (H)
# ---------------------------------------------------------------------------

import gzip  # noqa: E402
from pathlib import Path  # noqa: E402

from engine.company_intelligence.event_workspace import (  # noqa: E402
    FLAGSHIP_EVENT_ID,
    LIVE_NARRATIVE_ALIAS,
    write_workspace_generation,
)
from engine.company_intelligence.event_workspace_build import build_event_workspace  # noqa: E402
from engine.company_intelligence.identity import IssuerRegistry  # noqa: E402
from engine.company_intelligence.event_workspace import apple_registry, flagship_fiscal_period  # noqa: E402
from engine.company_intelligence.event_workspace import AAPL_CALL_DATE  # noqa: E402

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "company_intelligence"
_EXHIBIT = _FIXTURES / "aapl_fy2026_q3_ex99_1.htm"
_TRANSCRIPT_GZ = _FIXTURES / "aapl_fy2026_q3.json.gz"
_FILING_JSON = _FIXTURES / "aapl_fy2026_q3_filing.json"

WORKSPACE_PUBLIC_CACHE = "public, max-age=60, stale-while-revalidate=240"
NOT_COVERED_WORKSPACE_NOTE = "Event workspace does not cover this ticker"


def _workspace_success_reader_result(tmp_path: Path) -> dict:
    """Build a fully-stamped reader result from the flagship workspace."""
    from hashlib import sha256
    transcript_gz = gzip.decompress(_TRANSCRIPT_GZ.read_bytes())
    tx = json.loads(transcript_gz.decode())
    tx_sha = sha256(transcript_gz).hexdigest()
    filing = json.loads(_FILING_JSON.read_text())
    exhibit = _EXHIBIT.read_text()
    from engine.company_intelligence.resolution import claim_citations_pending
    from tests.test_company_intelligence_event_workspace import (
        _build_flagship,
        BASE,
    )
    flagship = _build_flagship()
    out = tmp_path / "ci"
    gen_dir = write_workspace_generation(out, {flagship["event_id"]: flagship})
    workspace = json.loads(
        (gen_dir / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_bytes()
    )
    return {
        "available": True,
        "ticker": "AAPL",
        "event_id": FLAGSHIP_EVENT_ID,
        "event_alias": LIVE_NARRATIVE_ALIAS,
        "workspace": workspace,
        "is_context_only": True,
        "display_only": True,
        "authority": "context_only",
        "untrusted_source_data": True,
        "receipt": {"generation_id": gen_dir.name},
        "note": "context only",
    }


def test_event_workspace_glance_200_and_leak_denylist(client, monkeypatch, tmp_path) -> None:
    """(H) 200 returns glance; v1 reader must not be called; no leaks."""
    success = _workspace_success_reader_result(tmp_path)
    v1_called: list[bool] = []

    monkeypatch.setattr(
        company_intelligence_api, "_read_current_event_workspace", lambda _p: success
    )
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda *a, **kw: v1_called.append(True) or {},
    )

    response = client.get("/api/event-workspace/AAPL")

    assert response.status_code == 200, response.text
    assert response.headers.get("cache-control") == WORKSPACE_PUBLIC_CACHE
    assert v1_called == [], "v1 reader must not be called by event-workspace endpoint"

    payload = response.json()
    # Use ensure_ascii=False so Unicode characters (en-dash, middle-dot) are
    # not escaped and can be found by simple string membership tests.
    dumped = json.dumps(payload, sort_keys=True, ensure_ascii=False)

    # Required content
    assert FLAGSHIP_EVENT_ID in dumped
    assert LIVE_NARRATIVE_ALIAS in dumped
    assert "$109.4B" in dumped
    assert "9\u201311%" in dumped
    assert "unlicensed" in dumped
    assert "not_joined" in dumped

    # Forbidden
    for forbidden in (
        "r2.dev",
        "workspace_url",
        "marker_url",
        "source_sha256",
        "text_sha256",
        "segment_sha256",
        "span_start_byte",
        "locator",
        "warnings",
        "score_overlay",
        "prophet",
        "http://",
        "https://",
        "beat",
        "miss",
        "bullish",
        '"summary"',
        "claim_text",
    ):
        assert forbidden not in dumped, f"leak: {forbidden!r} found in 200 glance"

    qs = next((s for s in payload["coverage_states"] if s.get("id") == "questions_count"), None)
    assert qs is not None
    assert qs["state"] == "7 exchanges"
    assert '"questions_count": 14' not in dumped


def test_event_workspace_glance_empty_qa_stays_unstructured(client, monkeypatch, tmp_path) -> None:
    """Empty Q&A keeps the honest unstructured/absence glance and the leak denylist."""
    success = _workspace_success_reader_result(tmp_path)
    workspace = dict(success["workspace"])
    workspace["qa_exchanges"] = []
    facts = [fact for fact in list(workspace.get("facts") or []) if fact.get("metric") != "questions_count"]
    facts.append({
        "schema": "event_fact.v1",
        "fact_id": "fact_questions_count",
        "event_id": FLAGSHIP_EVENT_ID,
        "metric": "questions_count",
        "typed_absence": {
            "schema": "typed_absence.v1",
            "authority": "context_only",
            "reason": "no_span_addressable_evidence",
            "subject": "questions_count",
            "detail": "analyst questions are not span-addressable on the held transcript",
            "event_id": FLAGSHIP_EVENT_ID,
            "document_id": "tx:AAPL/2026Q3",
            "missing_fields": [],
        },
    })
    workspace["facts"] = facts
    success = {**success, "workspace": workspace}
    v1_called: list[bool] = []
    monkeypatch.setattr(
        company_intelligence_api, "_read_current_event_workspace", lambda _p: success
    )
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda *a, **kw: v1_called.append(True) or {},
    )

    response = client.get("/api/event-workspace/AAPL")
    assert response.status_code == 200, response.text
    assert v1_called == []
    payload = response.json()
    dumped = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    for forbidden in (
        "r2.dev",
        "workspace_url",
        "marker_url",
        "source_sha256",
        "text_sha256",
        "segment_sha256",
        "span_start_byte",
        "locator",
        "warnings",
        "score_overlay",
        "prophet",
        "http://",
        "https://",
        "beat",
        "miss",
        "bullish",
        '"summary"',
        "claim_text",
    ):
        assert forbidden not in dumped, f"leak: {forbidden!r} found in empty-Q&A glance"
    qs = next((s for s in payload["coverage_states"] if s.get("id") == "questions_count"), None)
    assert qs is not None
    assert qs["state"] == "unstructured"
    assert '"questions_count": 14' not in dumped
    assert "7 exchanges" not in dumped


def test_event_workspace_glance_404_uncovered_ticker(client, monkeypatch) -> None:
    """(H) 404 when reader returns not-covered note; v1 reader not called."""
    v1_called: list[bool] = []

    monkeypatch.setattr(
        company_intelligence_api,
        "_read_current_event_workspace",
        lambda _p: {
            "available": False,
            "ticker": "TSLA",
            "note": NOT_COVERED_WORKSPACE_NOTE,
        },
    )
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda *a, **kw: v1_called.append(True) or {},
    )

    response = client.get("/api/event-workspace/TSLA")

    assert response.status_code == 404, response.text
    assert response.headers.get("cache-control") == WORKSPACE_PUBLIC_CACHE
    assert response.json() == {
        "code": "event_workspace_not_covered",
        "ticker": "TSLA",
    }
    assert v1_called == []


def test_event_workspace_glance_503_verification_failure_does_not_leak_note(client, monkeypatch) -> None:
    """(H) 503 for verification failure; internal note must not appear in body."""
    internal_note = "event workspace failed immutable receipt verification"
    v1_called: list[bool] = []

    monkeypatch.setattr(
        company_intelligence_api,
        "_read_current_event_workspace",
        lambda _p: {"available": False, "ticker": "AAPL", "note": internal_note},
    )
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_company_intelligence",
        lambda *a, **kw: v1_called.append(True) or {},
    )

    response = client.get("/api/event-workspace/AAPL")

    assert response.status_code == 503, response.text
    assert response.headers.get("cache-control") == NO_STORE
    body = json.dumps(response.json())
    assert internal_note not in body
    assert response.json() == {"detail": "Verified event temporarily unavailable."}
    assert v1_called == []


def test_event_workspace_glance_422_invalid_ticker(client, monkeypatch) -> None:
    """(H) 422 for invalid ticker before reader is touched."""
    called: list[bool] = []
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_current_event_workspace",
        lambda _p: called.append(True) or {},
    )

    response = client.get("/api/event-workspace/AAPL..")

    assert response.status_code == 422, response.text
    assert response.headers.get("cache-control") == NO_STORE
    assert "ticker must be" in response.json()["detail"]
    assert called == []


def test_event_workspace_glance_429_after_bursting(client, monkeypatch) -> None:
    """(H) 429 after exhausting client rate limit."""
    monkeypatch.setattr(
        company_intelligence_api,
        "_read_current_event_workspace",
        lambda _p: {
            "available": False,
            "ticker": "AAPL",
            "note": NOT_COVERED_WORKSPACE_NOTE,
        },
    )
    headers = {"EO-Connecting-IP": "203.0.113.42"}
    for _ in range(company_intelligence_api._RATE_LIMIT_REQUESTS):
        r = client.get("/api/event-workspace/AAPL", headers=headers)
        assert r.status_code == 404  # uncovered but not rate-limited yet

    limited = client.get("/api/event-workspace/AAPL", headers=headers)
    assert limited.status_code == 429
    assert limited.headers.get("cache-control") == NO_STORE
    assert limited.headers.get("retry-after") == "60"


def test_event_workspace_glance_503_on_reader_exception(client, monkeypatch) -> None:
    """(H) Unexpected reader exception maps to 503 without internal details."""
    def _raise(_p: dict) -> dict:
        raise RuntimeError("upstream explosion with internal url https://r2.dev/secret")

    monkeypatch.setattr(company_intelligence_api, "_read_current_event_workspace", _raise)

    response = client.get("/api/event-workspace/AAPL")

    assert response.status_code == 503
    body = json.dumps(response.json())
    assert "r2.dev" not in body
    assert "internal url" not in body
    assert response.json() == {"detail": "Verified event temporarily unavailable."}
