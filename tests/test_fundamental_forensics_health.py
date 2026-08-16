"""FF-0 freshness truth: source clocks, status, last-good, and the health API."""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from engine.fundamental_forensics import health as ff_health
from engine.fundamental_forensics.health import (
    FRESHNESS_BUDGET_SECONDS,
    HEALTH_SCHEMA,
    REASON_LAST_GOOD_STALE,
    REASON_SOURCE_CURRENT,
    REASON_SOURCE_STALE,
    REASON_STATE_MISSING,
    assert_no_private_leak,
    evaluate_health,
    health_from_inputs,
)
from engine.fundamental_forensics.private_state import (
    ORIGIN_LAST_GOOD,
    ORIGIN_LOCAL,
    ORIGIN_MISSING,
    ORIGIN_R2,
    STATE_KEY,
    STATE_SCHEMA,
    LoadedState,
    clear_state_cache,
    load_state_record,
)
from scripts.build_fundamental_forensics import compose_state

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "contracts" / "fundamental_forensics_health.schema.json"
AUGUST = datetime(2026, 8, 16, tzinfo=timezone.utc)
JULY12 = datetime(2026, 7, 12, 11, 23, 15, tzinfo=timezone.utc)
CURRENT_SOURCE = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)

pytest.importorskip("fastapi", reason="forensics health API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.forensics as forensics_api  # noqa: E402


def _document(
    *,
    generated_at: str,
    as_of: str | None = "2026-07-12",
    disclosure_as_of: str | None = None,
    extra_company: dict | None = None,
) -> dict:
    company = extra_company or {"ticker": "AAPL"}
    if disclosure_as_of is not None:
        company = {
            **company,
            "disclosures": {
                "clocks": {
                    "as_of": disclosure_as_of,
                    "computed_at": "2099-01-01T00:00:00Z",
                }
            },
        }
    return {
        "schema": STATE_SCHEMA,
        "generated_at": generated_at,
        "as_of": as_of,
        "companies": {"AAPL": company},
        "ranked_findings": [{"symbol": "AAPL", "finding_id": "secret-row"}],
        "summary": {"companies": 1, "findings": 1, "latest_filing": as_of},
    }


def _blob(document: dict) -> bytes:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return gzip.compress(payload.encode("utf-8"), mtime=0)


def _loaded(document: dict, origin: str) -> LoadedState:
    return LoadedState(blob=_blob(document), origin=origin)  # type: ignore[arg-type]


def _validate(payload: dict) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(payload)
    assert_no_private_leak(payload)


def test_july12_source_fixture_is_stale_under_an_injected_august_clock() -> None:
    document = _document(generated_at="2026-07-12T11:23:15+00:00", as_of="2026-07-12")
    payload = health_from_inputs(
        loaded=_loaded(document, ORIGIN_R2),
        document=document,
        now=AUGUST,
    )
    _validate(payload)
    assert payload["status"] == "stale"
    assert payload["reason_code"] == REASON_SOURCE_STALE
    assert payload["clocks"]["broad_source_at"] == "2026-07-12T11:23:15Z"
    assert payload["clocks"]["latest_source_filing_date"] == "2026-07-12"
    assert payload["age_seconds"] == int((AUGUST - JULY12).total_seconds())
    assert payload["age_seconds"] > FRESHNESS_BUDGET_SECONDS
    assert payload["evaluated_at"] == "2026-08-16T00:00:00Z"
    assert payload["evaluated_at"] != payload["clocks"]["broad_source_at"]


def test_current_source_fixture_is_current() -> None:
    document = _document(
        generated_at="2026-08-15T12:00:00Z",
        as_of="2026-08-15",
        disclosure_as_of="2026-08-14T18:00:00Z",
    )
    payload = health_from_inputs(
        loaded=_loaded(document, ORIGIN_LOCAL),
        document=document,
        now=AUGUST,
        public_summary_at=CURRENT_SOURCE,
    )
    _validate(payload)
    assert payload["status"] == "current"
    assert payload["reason_code"] == REASON_SOURCE_CURRENT
    assert payload["clocks"]["broad_source_at"] == "2026-08-15T12:00:00Z"
    assert payload["clocks"]["latest_source_filing_date"] == "2026-08-15"
    assert payload["clocks"]["disclosure_projection_at"] == "2026-08-14T18:00:00Z"
    assert payload["clocks"]["disclosure_projection_at"] != "2099-01-01T00:00:00Z"
    assert payload["age_seconds"] == int((AUGUST - CURRENT_SOURCE).total_seconds())
    assert payload["age_seconds"] <= FRESHNESS_BUDGET_SECONDS
    assert payload["private_object"]["origin"] == ORIGIN_LOCAL
    assert payload["private_object"]["sha256"] == hashlib.sha256(_blob(document)).hexdigest()


def test_missing_state_returns_unavailable() -> None:
    payload = health_from_inputs(
        loaded=LoadedState(blob=None, origin=ORIGIN_MISSING),
        document=None,
        now=AUGUST,
    )
    _validate(payload)
    assert payload["status"] == "unavailable"
    assert payload["reason_code"] == REASON_STATE_MISSING
    assert payload["age_seconds"] is None
    assert payload["private_object"]["present"] is False
    assert payload["private_object"]["sha256"] is None


def test_last_good_fallback_becomes_degraded_when_stale() -> None:
    document = _document(generated_at="2026-07-12T11:23:15+00:00")
    payload = health_from_inputs(
        loaded=_loaded(document, ORIGIN_LAST_GOOD),
        document=document,
        now=AUGUST,
    )
    _validate(payload)
    assert payload["status"] == "degraded"
    assert payload["reason_code"] == REASON_LAST_GOOD_STALE
    assert payload["private_object"]["origin"] == ORIGIN_LAST_GOOD


def test_last_good_current_source_stays_current() -> None:
    document = _document(generated_at="2026-08-15T12:00:00Z", as_of="2026-08-15")
    payload = health_from_inputs(
        loaded=_loaded(document, ORIGIN_LAST_GOOD),
        document=document,
        now=AUGUST,
    )
    assert payload["status"] == "current"
    assert payload["reason_code"] == REASON_SOURCE_CURRENT


def test_rerendering_cannot_advance_source_freshness(tmp_path: Path) -> None:
    q_dir = tmp_path / "data" / "edgar"
    q_dir.mkdir(parents=True)
    import pandas as pd

    quarterly = pd.DataFrame(
        [
            {
                "ticker": "TST",
                "fiscal_year": 2025,
                "fiscal_quarter": 2,
                "period_end": "2025-06-30",
                "filed": "2025-08-01",
                "as_of": "2026-07-12T11:23:15+00:00",
                "revenue": 100.0,
                "gross_profit": 40.0,
                "receivables": 20.0,
                "inventory": 20.0,
                "cfo": 15.0,
                "capex": 10.0,
                "op_income": 15.0,
                "ni": 12.0,
                "contract_liabilities": 5.0,
            },
            {
                "ticker": "TST",
                "fiscal_year": 2026,
                "fiscal_quarter": 2,
                "period_end": "2026-06-30",
                "filed": "2026-07-12",
                "as_of": "2026-07-12T11:23:15+00:00",
                "revenue": 105.0,
                "gross_profit": 36.75,
                "receivables": 35.0,
                "inventory": 40.0,
                "cfo": 16.0,
                "capex": 30.0,
                "op_income": 16.0,
                "ni": 12.0,
                "contract_liabilities": 5.0,
            },
        ]
    )
    quarterly.to_parquet(q_dir / "statements_quarterly.parquet", index=False)
    pd.DataFrame(
        [
            {"ticker": "TST", "fy": 2023, "period_end": "2023-12-31", "ni": 10.0, "cfo": 14.0, "assets": 100.0},
            {"ticker": "TST", "fy": 2024, "period_end": "2024-12-31", "ni": 12.0, "cfo": 13.0, "assets": 100.0},
            {"ticker": "TST", "fy": 2025, "period_end": "2025-12-31", "ni": 18.0, "cfo": 10.0, "assets": 100.0},
        ]
    ).to_parquet(tmp_path / "data" / "edgar" / "statements.parquet", index=False)

    first = compose_state(tmp_path)
    later = datetime(2026, 8, 20, 15, 0, tzinfo=timezone.utc)

    class _LaterDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return later if tz is None else later.astimezone(tz)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr("scripts.build_fundamental_forensics.datetime", _LaterDateTime)
    try:
        second = compose_state(tmp_path)
    finally:
        monkeypatch.undo()

    assert first["generated_at"] == second["generated_at"]
    first_health = health_from_inputs(
        loaded=_loaded(first, ORIGIN_LOCAL),
        document=first,
        now=AUGUST,
    )
    second_health = health_from_inputs(
        loaded=_loaded(second, ORIGIN_LOCAL),
        document=second,
        now=later,
    )
    assert first_health["clocks"]["broad_source_at"] == second_health["clocks"]["broad_source_at"]
    assert first_health["clocks"]["latest_source_filing_date"] == second_health["clocks"]["latest_source_filing_date"]
    assert first_health["status"] == "stale"
    assert second_health["evaluated_at"] != first_health["evaluated_at"]
    assert second_health["evaluated_at"] != second_health["clocks"]["broad_source_at"]


class _MemoryStore:
    def __init__(self, *, read_back: bytes | None = None, fail: bool = False):
        self.read_back = read_back
        self.fail = fail
        self.get_calls: list[str] = []

    def get_bytes(self, key: str) -> bytes | None:
        self.get_calls.append(key)
        if self.fail:
            raise RuntimeError("r2 down")
        return self.read_back


@pytest.fixture(autouse=True)
def _isolated_cache():
    clear_state_cache()
    yield
    clear_state_cache()


def test_load_state_record_marks_last_good_after_r2_failure(tmp_path: Path) -> None:
    blob = _blob(_document(generated_at="2026-07-12T11:23:15+00:00"))
    store = _MemoryStore(read_back=blob)
    first = load_state_record(tmp_path, store_factory=lambda: store, cache_seconds=0)
    assert first.origin == ORIGIN_R2
    store.fail = True
    fallback = load_state_record(tmp_path, store_factory=lambda: store, cache_seconds=0)
    assert fallback.origin == ORIGIN_LAST_GOOD
    assert fallback.blob == blob
    health = evaluate_health(
        tmp_path,
        now=AUGUST,
        loaded=fallback,
        document=_document(generated_at="2026-07-12T11:23:15+00:00"),
    )
    assert health["status"] == "degraded"


def _entitled_client():
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {
        "id": "paid-user",
        "tier": "pro",
    }
    return TestClient(app)


def test_health_endpoint_is_private_no_store_and_does_not_leak(monkeypatch) -> None:
    document = _document(
        generated_at="2026-07-12T11:23:15+00:00",
        extra_company={
            "ticker": "AAPL",
            "secret_row": "never-expose",
            "object_key": "fundamental_forensics/private/never-expose",
        },
    )
    blob = _blob(document)
    monkeypatch.setattr(
        ff_health,
        "load_state_record",
        lambda *_args, **_kwargs: LoadedState(blob=blob, origin=ORIGIN_R2),
    )
    monkeypatch.setattr(ff_health, "read_public_summary_stamp", lambda _root: JULY12)
    monkeypatch.setattr(
        ff_health,
        "datetime",
        type("Frozen", (), {"now": staticmethod(lambda tz=None: AUGUST), "fromisoformat": datetime.fromisoformat}),
    )
    # evaluate_health uses datetime.now only when now= is omitted; pin it.
    monkeypatch.setattr(
        forensics_api,
        "evaluate_health",
        lambda _root: evaluate_health(
            ROOT,
            now=AUGUST,
            loaded=LoadedState(blob=blob, origin=ORIGIN_R2),
            document=document,
            public_summary_at=JULY12,
        ),
    )
    with _entitled_client() as client:
        response = client.get("/api/forensics/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"
    payload = response.json()
    _validate(payload)
    assert payload["status"] == "stale"
    rendered = response.text
    for forbidden in (
        "never-expose",
        "secret_row",
        "object_key",
        STATE_KEY,
        "ranked_findings",
        "ACCESS_KEY",
        "SECRET_ACCESS_KEY",
        '"companies"',
    ):
        assert forbidden not in rendered


def test_health_endpoint_missing_state_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(
        forensics_api,
        "evaluate_health",
        lambda _root: health_from_inputs(
            loaded=LoadedState(blob=None, origin=ORIGIN_MISSING),
            document=None,
            now=AUGUST,
        ),
    )
    with _entitled_client() as client:
        response = client.get("/api/forensics/health")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store"
    assert response.json()["status"] == "unavailable"
    assert response.json()["reason_code"] == REASON_STATE_MISSING


def test_health_route_requires_site_full() -> None:
    route = next(route for route in forensics_api.router.routes if getattr(route, "path", None) == "/api/forensics/health")
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
    assert forensics_api.require_site_full_user in dependency_calls


def test_unauthenticated_health_does_not_open_state(monkeypatch) -> None:
    def deny(_authorization=None):
        raise forensics_api._private_error(401, "not authenticated")

    def must_not_evaluate(_root):
        raise AssertionError("health evaluation must not run before entitlement")

    monkeypatch.setattr(forensics_api, "require_site_full_user", deny)
    monkeypatch.setattr(forensics_api, "evaluate_health", must_not_evaluate)
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = deny
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/forensics/health")
    assert response.status_code == 401
    assert response.headers["cache-control"] == "private, no-store"
    assert "never-expose" not in response.text
    assert STATE_KEY not in response.text
