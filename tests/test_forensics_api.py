"""Authenticated API tests for the private Filing Forensics state route."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi", reason="forensics API tests need fastapi")
pytest.importorskip("httpx", reason="FastAPI TestClient needs httpx")

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import app.forensics as forensics_api  # noqa: E402
import engine.fundamental_forensics.attested_query_snapshots as attested_snapshots  # noqa: E402
from engine.fundamental_forensics.private_state import STATE_SCHEMA  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]

SNAPSHOT_ID = f"ffqsv2_{'a' * 64}"
BASE_SNAPSHOT_ID = f"ffqs_{'b' * 64}"
QUERY_HASH = "c" * 64
ATTESTATION_ID = f"ffatt_{'d' * 64}"
MATCH_ID = f"ffatt_match_{'e' * 64}"
ROOT_ALL = f"metric_cell_{'1' * 64}"
ROOT_NONE = f"metric_cell_{'2' * 64}"
ROOT_PARTIAL = f"metric_cell_{'3' * 64}"
ROOT_UNEVALUABLE = f"metric_cell_{'4' * 64}"

PRIVATE_HEADERS = {
    "cache-control": "private, no-store",
    "vary": "Authorization",
    "x-content-type-options": "nosniff",
    "x-robots-tag": "noindex, noarchive",
}


def _assert_private_headers(response) -> None:
    for name, expected in PRIVATE_HEADERS.items():
        assert response.headers[name] == expected


def _history_index() -> SimpleNamespace:
    """A receipt-safe engine seam; its raw attestations must never reach HTTP."""
    projection = {
        "attestation_id": ATTESTATION_ID,
        "authority_snapshot_id": "authority-snapshot-safe",
        "package_id": "package-safe",
        "extraction_id": "extraction-safe",
        "cik": "0000320193",
        "accession": "0000320193-26-000001",
        "companyfacts_capture_id": "capture-safe",
        "companyfacts_manifest_id": "manifest-safe",
        "companyfacts_response_sha256": "f" * 64,
        "companyfacts_match_count": 1,
        "attested_at": "2026-08-02T00:00:00Z",
    }
    conversion_receipt = {
        "receipt_id": "cffledger_" + "9" * 64,
        "schema": "fundamental_forensics.companyfacts_ledger_receipt/v2",
        "adapter_version": "companyfacts-ledger/v2",
        "capture_id": "capture-safe",
        "manifest_id": "manifest-safe",
        "cik": "0000320193",
        "clocks": {
            "acquisition_started_at": "2026-08-02T00:00:00Z",
            "captured_at": "2026-08-02T00:00:00Z",
            "recorded_at": "2026-08-02T00:00:00Z",
            "source_snapshot_at": "2026-08-02T00:00:00Z",
            "submissions_recorded_at": "2026-08-02T00:00:00Z",
        },
        "availability": "available",
        "occurrence_count": 4,
        "output_occurrence_count": 4,
        "pit_eligible_count": 3,
        # These must remain in the private immutable reader, not in HTTP.
        "submission_sources": ["private-source-record"],
        "mapped_accessions": ["private-accession-list"],
    }
    manifest = {
        "policy": {"version": "ffqsv2_exact_join/v1", "fingerprint": "7" * 64},
        "clocks": {"published_at": "2026-08-02T00:01:00Z"},
        "coverage_summary": {
            "coverage_scope": "selected_raw_fact_leaves_only",
            "positive_label": "B3_selected_member_companyfacts_row_correspondence_only",
            "root_cell_count": 4,
            "all_leaves_attested": 1,
            "partially_attested": 1,
            "not_attested": 1,
            "not_evaluable": 1,
        },
        "companyfacts_conversion_receipt": conversion_receipt,
        "attestation_projections": [projection],
        "nonclaims": {
            "filing_complete": False,
            "trading_authority": False,
            "neural_web_authority": False,
        },
        "objects": [{"object_key": "fundamental_forensics/private/never-expose"}],
    }
    roots = (
        {
            "root_cell_id": ROOT_ALL,
            "selected_leaf_occurrence_ids": ["occ-all"],
            "eligible_leaf_occurrence_ids": ["occ-all"],
            "attested_occurrence_ids": ["occ-all"],
            "status": "all_leaves_attested",
        },
        {
            "root_cell_id": ROOT_NONE,
            "selected_leaf_occurrence_ids": ["occ-none"],
            "eligible_leaf_occurrence_ids": ["occ-none"],
            "attested_occurrence_ids": [],
            "status": "not_attested",
        },
        {
            "root_cell_id": ROOT_PARTIAL,
            "selected_leaf_occurrence_ids": ["occ-partial-attested", "occ-partial-open"],
            "eligible_leaf_occurrence_ids": ["occ-partial-attested", "occ-partial-open"],
            "attested_occurrence_ids": ["occ-partial-attested"],
            "status": "partially_attested",
        },
        {
            "root_cell_id": ROOT_UNEVALUABLE,
            "selected_leaf_occurrence_ids": [],
            "eligible_leaf_occurrence_ids": [],
            "attested_occurrence_ids": [],
            "status": "not_evaluable",
        },
    )
    companyfacts = {
        "cik": "0000320193",
        "accession": "0000320193-26-000001",
        "taxonomy": "us-gaap",
        "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "unit": "USD",
        "start": "2025-10-01",
        "end": "2025-12-31",
        "value": "124300000000",
        "capture_id": "not-exposed-in-detail",
        "dimensions_known": False,
    }
    bindings = {
        "occ-all": {
            "attestation_id": ATTESTATION_ID,
            "match_id": MATCH_ID,
            "companyfacts": companyfacts,
        },
        "occ-partial-attested": {
            "attestation_id": ATTESTATION_ID,
            "match_id": MATCH_ID,
            "companyfacts": companyfacts,
        },
    }
    return SimpleNamespace(
        snapshot_id=SNAPSHOT_ID,
        base_snapshot_id=BASE_SNAPSHOT_ID,
        query_hash=QUERY_HASH,
        published_at="2026-08-02T00:01:00Z",
        manifest=manifest,
        roots=roots,
        root_ids=tuple(row["root_cell_id"] for row in roots),
        roots_by_id={row["root_cell_id"]: row for row in roots},
        bindings_by_occurrence=bindings,
        # The engine index makes only its pre-sanitized manifest projection
        # available to the transport layer; raw B3 records do not enter HTTP.
        attestations_by_id={ATTESTATION_ID: projection},
    )


def _b4_publication_helpers():
    """Load B4's real sealed-fixture builder without duplicating its contract."""
    path = ROOT / "tests" / "test_fundamental_forensics_attested_query_snapshots.py"
    spec = importlib.util.spec_from_file_location("_b4_api_integration_fixture_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _blob() -> bytes:
    document = {
        "schema": STATE_SCHEMA,
        "generated_at": "2026-08-01T12:00:00Z",
        "companies": {"AAPL": {"ticker": "AAPL", "findings": []}},
    }
    return gzip.compress(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8"),
        mtime=0,
    )


@pytest.fixture
def entitled_client():
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {
        "id": "paid-user",
        "tier": "pro",
    }
    with TestClient(app) as client:
        yield client


def test_missing_private_state_returns_503(entitled_client, monkeypatch) -> None:
    monkeypatch.setattr(forensics_api, "load_state_blob", lambda _root: None)
    response = entitled_client.get("/api/forensics/state")
    assert response.status_code == 503
    assert response.json() == {"detail": "forensics state temporarily unavailable"}
    _assert_private_headers(response)


def test_valid_state_returns_gzip_with_private_no_store_headers(entitled_client, monkeypatch) -> None:
    expected = _blob()
    monkeypatch.setattr(forensics_api, "load_state_blob", lambda _root: expected)
    response = entitled_client.get("/api/forensics/state")
    assert response.status_code == 200
    assert response.content == expected
    assert response.headers["content-type"] == "application/gzip"
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["content-disposition"] == 'inline; filename="forensics-state.json.gz"'
    assert response.headers["vary"] == "Authorization"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-robots-tag"] == "noindex, noarchive"


def test_route_declares_the_site_full_dependency() -> None:
    route = next(route for route in forensics_api.router.routes if route.path == "/api/forensics/state")
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
    assert forensics_api.require_site_full_user in dependency_calls


def test_site_full_wrapper_checks_user_then_entitlement(monkeypatch) -> None:
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
    assert forensics_api.require_site_full_user("Bearer paid-token") == entitled
    assert calls == [
        ("require_user", "Bearer paid-token"),
        ("enforce_site_full", (user, True)),
    ]


def test_free_user_is_denied_even_while_global_paywall_is_off(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setenv("PAYWALL_ENABLED", "0")
    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})
    monkeypatch.setattr(paywall_mod, "_entitled", lambda _user_id, _feature: (False, "free"))

    with pytest.raises(HTTPException) as exc_info:
        forensics_api.require_site_full_user("Bearer signed-in-free-user")

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["required_feature"] == "site_full"


def test_site_full_denial_happens_before_private_state_read(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "u-free"})

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(402, "site_full required")

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)

    def state_must_not_be_read(_root):
        raise AssertionError("state read must happen only after entitlement")

    monkeypatch.setattr(forensics_api, "load_state_blob", state_must_not_be_read)
    app = FastAPI()
    app.include_router(forensics_api.router)
    with TestClient(app) as client:
        response = client.get(
            "/api/forensics/state",
            headers={"Authorization": "Bearer free-token"},
        )
    assert response.status_code == 402
    assert response.json() == {"detail": "site_full required"}


def test_production_app_mounts_the_authenticated_forensics_route() -> None:
    import app.main as main_mod

    # Current FastAPI stores include_router() entries as lazy _IncludedRouter
    # nodes whose own ``path`` is None.  OpenAPI expansion is the stable public
    # seam and proves the production app actually resolves the child route.
    assert "/api/forensics/state" in main_mod.app.openapi().get("paths", {}), (
        "app.main must include app.forensics.router or the paid API is unreachable"
    )


def test_private_research_r2_credentials_are_delivered_to_macro_api_only() -> None:
    workflow = (ROOT / ".github" / "workflows" / "deploy-api-secrets.yml").read_text(
        encoding="utf-8"
    )
    for name in (
        "R2_RESEARCH_ENDPOINT",
        "R2_RESEARCH_ACCESS_KEY_ID",
        "R2_RESEARCH_SECRET_ACCESS_KEY",
        "R2_RESEARCH_BUCKET",
    ):
        assert f"secrets.{name}" in workflow
        assert f"_add {name} " in workflow
    assert (
        'grep -vE "^R2_RESEARCH_(ENDPOINT|ACCESS_KEY_ID|SECRET_ACCESS_KEY|BUCKET)="'
        in workflow
    )
    # The second job updates macro-admin. Filing Forensics object credentials
    # belong only in the first macro-api delivery block.
    assert workflow.count("secrets.R2_RESEARCH_SECRET_ACCESS_KEY") == 1


@pytest.fixture
def attested_history_client(monkeypatch):
    """Standalone router client: route-local private headers are mandatory here."""
    index = _history_index()
    seen: list[str | None] = []
    store = object()

    monkeypatch.setattr(forensics_api, "_build_store", lambda: store)

    def load(candidate_store, *, snapshot_id=None):
        assert candidate_store is store
        seen.append(snapshot_id)
        return index

    monkeypatch.setattr(forensics_api, "load_attested_query_receipt_index", load)
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    with TestClient(app) as client:
        yield client, seen


def test_attested_history_latest_is_private_and_receipt_safe(attested_history_client) -> None:
    client, seen = attested_history_client
    response = client.get("/api/forensics/v1/attested-history/latest")

    assert response.status_code == 200
    _assert_private_headers(response)
    assert seen == [None]
    payload = response.json()
    assert payload["snapshot_id"] == SNAPSHOT_ID
    assert payload["base_snapshot_id"] == BASE_SNAPSHOT_ID
    assert payload["query_hash"] == QUERY_HASH
    assert payload["companyfacts_conversion_receipt"] == {
        "receipt_id": "cffledger_" + "9" * 64,
        "schema": "fundamental_forensics.companyfacts_ledger_receipt/v2",
        "adapter_version": "companyfacts-ledger/v2",
        "capture_id": "capture-safe",
        "manifest_id": "manifest-safe",
        "cik": "0000320193",
        "clocks": {
            "acquisition_started_at": "2026-08-02T00:00:00Z",
            "captured_at": "2026-08-02T00:00:00Z",
            "recorded_at": "2026-08-02T00:00:00Z",
            "source_snapshot_at": "2026-08-02T00:00:00Z",
            "submissions_recorded_at": "2026-08-02T00:00:00Z",
        },
        "availability": "available",
        "occurrence_count": 4,
        "output_occurrence_count": 4,
        "pit_eligible_count": 3,
    }
    assert payload["authority"] == {
        "positive_claim": "B3_selected_member_companyfacts_row_correspondence_only",
        "coverage_scope": "selected_raw_fact_leaves_only",
        "claim_basis": "sealed_publication_receipt",
        "source_reverified_at_read": False,
        "match_body_replayed_at_read": False,
        "nonclaims": {
            "filing_complete": False,
            "trading_authority": False,
            "neural_web_authority": False,
        },
    }
    rendered = response.text
    for forbidden in (
        "object_key",
        "fundamental_forensics/private/never-expose",
        "private_raw_b3_record",
        "never-expose",
        "submission_sources",
        "mapped_accessions",
        "source_reverified_at_read\":true",
    ):
        assert forbidden not in rendered


def test_real_published_receipt_index_serializes_all_history_routes(monkeypatch, tmp_path) -> None:
    """Exercise the recursively frozen engine index, not a mutable API seam."""
    helper = _b4_publication_helpers()
    store, _base, material, conversion, _binding, prepared = helper._prepared(monkeypatch, tmp_path)
    snapshot = attested_snapshots.publish_attested_query_snapshot(
        store,
        prepared,
        attestation_materials=(material,),
        companyfacts_conversion=conversion,
    )
    root_cell_id = snapshot.cell_coverage[0]["root_cell_id"]
    attested_snapshots.reset_attested_query_receipt_index_cache()
    monkeypatch.setattr(forensics_api, "_build_store", lambda: store)
    monkeypatch.setattr(
        forensics_api,
        "load_attested_query_receipt_index",
        attested_snapshots.load_attested_query_receipt_index,
    )
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    paths = (
        "/api/forensics/v1/attested-history/latest",
        f"/api/forensics/v1/attested-history/snapshots/{snapshot.snapshot_id}/roots",
        f"/api/forensics/v1/attested-history/snapshots/{snapshot.snapshot_id}/roots/{root_cell_id}",
    )

    try:
        with TestClient(app) as client:
            responses = tuple(client.get(path) for path in paths)
    finally:
        attested_snapshots.reset_attested_query_receipt_index_cache()

    forbidden_fields = (
        '"objects":',
        '"object_key":',
        '"submission_sources":',
        '"mapped_accessions":',
        '"unmapped_accessions":',
        '"record":',
        '"matches":',
        '"ledger":',
        '"occurrences":',
        '"company_facts":',
        '"source_paths":',
    )
    private_object_keys = tuple(item["object_key"] for item in snapshot.manifest["objects"])
    for response in responses:
        assert response.status_code == 200
        _assert_private_headers(response)
        assert response.json()["snapshot_id"] == snapshot.snapshot_id
        for forbidden in (*forbidden_fields, *private_object_keys):
            assert forbidden not in response.text


def test_attested_history_roots_is_stable_keyset_pagination(attested_history_client) -> None:
    client, seen = attested_history_client
    response = client.get(
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots?limit=2"
    )

    assert response.status_code == 200
    _assert_private_headers(response)
    first = response.json()
    assert [row["root_cell_id"] for row in first["roots"]] == [ROOT_ALL, ROOT_NONE]
    assert first["page"] == {
        "cursor": None,
        "next_cursor": ROOT_NONE,
        "limit": 2,
        "returned": 2,
        "total": 4,
    }
    assert set(first["roots"][0]) == {
        "root_cell_id",
        "selected_leaf_occurrence_ids",
        "eligible_leaf_occurrence_ids",
        "attested_occurrence_ids",
        "status",
    }

    second = client.get(
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots",
        params={"cursor": first["page"]["next_cursor"], "limit": "2"},
    )
    assert second.status_code == 200
    _assert_private_headers(second)
    assert [row["root_cell_id"] for row in second.json()["roots"]] == [ROOT_PARTIAL, ROOT_UNEVALUABLE]
    assert second.json()["page"]["next_cursor"] is None
    assert seen == [SNAPSHOT_ID, SNAPSHOT_ID]


@pytest.mark.parametrize(
    ("suffix", "detail"),
    [
        ("?cursor=unknown-root", "invalid cursor"),
        ("?cursor=bad%2Froot", "invalid cursor"),
        ("?limit=0", "invalid limit"),
        ("?limit=101", "invalid limit"),
        ("?limit=1.0", "invalid limit"),
        ("?limit=1&limit=2", "invalid limit"),
    ],
)
def test_attested_history_invalid_keyset_controls_are_private_400(
    attested_history_client,
    suffix,
    detail,
) -> None:
    client, _seen = attested_history_client
    response = client.get(
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots{suffix}"
    )
    assert response.status_code == 400
    assert response.json() == {"detail": detail}
    _assert_private_headers(response)


def test_attested_history_rejects_hostile_snapshot_and_root_before_store_read(attested_history_client) -> None:
    client, seen = attested_history_client
    bad_snapshot = "ffqsv2_" + "A" * 64
    response = client.get(f"/api/forensics/v1/attested-history/snapshots/{bad_snapshot}/roots")
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid attested snapshot id"}
    _assert_private_headers(response)

    response = client.get(
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/bad.root"
    )
    assert response.status_code == 400
    assert response.json() == {"detail": "invalid root_cell_id"}
    _assert_private_headers(response)
    assert seen == []


def test_attested_history_detail_has_one_selected_leaf_waterfall_and_no_raw_b3(attested_history_client) -> None:
    client, _seen = attested_history_client
    response = client.get(
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/{ROOT_PARTIAL}"
    )

    assert response.status_code == 200
    _assert_private_headers(response)
    payload = response.json()
    assert payload["root"]["status"] == "partially_attested"
    assert payload["waterfall"] == [
        {
            "occurrence_id": "occ-partial-attested",
            "eligible": True,
            "attested": True,
            "attestation_id": ATTESTATION_ID,
            "match_id": MATCH_ID,
            "companyfacts": {
                "cik": "0000320193",
                "accession": "0000320193-26-000001",
                "taxonomy": "us-gaap",
                "concept": "RevenueFromContractWithCustomerExcludingAssessedTax",
                "unit": "USD",
                "period": {"start": "2025-10-01", "end": "2025-12-31"},
                "value": "124300000000",
            },
            "stored_b3_projection": _history_index().manifest["attestation_projections"][0],
        },
        {
            "occurrence_id": "occ-partial-open",
            "eligible": True,
            "attested": False,
        },
    ]
    assert "private_raw_b3_record" not in response.text
    assert "not-exposed-in-detail" not in response.text


def test_attested_history_missing_root_is_private_404(attested_history_client) -> None:
    client, _seen = attested_history_client
    response = client.get(
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/metric_cell_{'5' * 64}"
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "root cell not covered"}
    _assert_private_headers(response)


def test_attested_history_refuses_unsafe_b3_index_instead_of_serializing_it(monkeypatch) -> None:
    """A raw record accidentally handed to the router is a closed 503, never JSON."""
    index = _history_index()
    index.attestations_by_id = {ATTESTATION_ID: {"private_raw_b3_record": "never-expose"}}
    monkeypatch.setattr(forensics_api, "_build_store", lambda: object())
    monkeypatch.setattr(
        forensics_api,
        "load_attested_query_receipt_index",
        lambda _store, *, snapshot_id=None: index,
    )
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    with TestClient(app) as client:
        response = client.get(
            f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/{ROOT_PARTIAL}"
        )
    assert response.status_code == 503
    _assert_private_headers(response)
    assert "private_raw_b3_record" not in response.text
    assert "never-expose" not in response.text


def _client_for_history_index(monkeypatch, index):
    monkeypatch.setattr(forensics_api, "_build_store", lambda: object())
    monkeypatch.setattr(
        forensics_api,
        "load_attested_query_receipt_index",
        lambda _store, *, snapshot_id=None: index,
    )
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    return TestClient(app)


def test_attested_history_oversized_single_root_fails_before_waterfall_allocation(monkeypatch) -> None:
    index = _history_index()
    oversized = {
        "root_cell_id": ROOT_ALL,
        "selected_leaf_occurrence_ids": tuple(f"occ-{number}" for number in range(1_025)),
        "eligible_leaf_occurrence_ids": (),
        "attested_occurrence_ids": (),
        "status": "not_attested",
    }
    index.roots = (oversized,)
    index.root_ids = (ROOT_ALL,)
    index.roots_by_id = {ROOT_ALL: oversized}
    with _client_for_history_index(monkeypatch, index) as client:
        response = client.get(
            f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/{ROOT_ALL}"
        )
    assert response.status_code == 503
    _assert_private_headers(response)
    assert response.json() == {"detail": "attested query history temporarily unavailable"}


def test_attested_history_root_detail_enforces_production_serialized_byte_budget(monkeypatch) -> None:
    """Legal leaf counts cannot authorize an enormous detail response."""
    index = _history_index()
    leaf_count = forensics_api._MAX_LEAF_REFS_PER_ROOT
    occurrence_ids = tuple(f"rawfact_{number:064x}" for number in range(leaf_count))
    oversized_value = "9" * 8_192
    companyfacts = {
        "cik": "0000320193",
        "accession": "0000320193-26-000001",
        "taxonomy": "us-gaap",
        "concept": "Revenue",
        "unit": "USD",
        "start": "2025-10-01",
        "end": "2025-12-31",
        "value": oversized_value,
    }
    oversized = {
        "root_cell_id": ROOT_ALL,
        "selected_leaf_occurrence_ids": occurrence_ids,
        "eligible_leaf_occurrence_ids": occurrence_ids,
        "attested_occurrence_ids": occurrence_ids,
        "status": "all_leaves_attested",
    }
    projection = dict(index.attestations_by_id[ATTESTATION_ID])
    projection["companyfacts_match_count"] = leaf_count
    index.manifest["attestation_projections"] = [projection]
    index.attestations_by_id = {ATTESTATION_ID: projection}
    index.roots = (oversized,)
    index.root_ids = (ROOT_ALL,)
    index.roots_by_id = {ROOT_ALL: oversized}
    index.bindings_by_occurrence = {
        occurrence_id: {
            "attestation_id": ATTESTATION_ID,
            "match_id": f"ffatt_match_{number:064x}",
            "companyfacts": companyfacts,
        }
        for number, occurrence_id in enumerate(occurrence_ids)
    }

    # Exercise the real production constants: all three arrays are exactly at
    # their admitted count ceilings, while their actual response fields exceed
    # the independent 4 MiB serialized-detail ceiling.
    assert len(occurrence_ids) == forensics_api._MAX_LEAF_REFS_PER_ROOT
    assert 3 * len(occurrence_ids) == forensics_api._MAX_LEAF_REFS_PER_ROOT_RESPONSE
    with _client_for_history_index(monkeypatch, index) as client:
        response = client.get(
            f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/{ROOT_ALL}"
        )
    assert response.status_code == 503
    _assert_private_headers(response)
    assert response.json() == {"detail": "attested query history temporarily unavailable"}


def test_attested_history_oversized_roots_page_fails_before_row_serialization(monkeypatch) -> None:
    index = _history_index()
    roots = []
    for number in range(1, 101):
        root_id = f"metric_cell_{number:064x}"
        selected = tuple(f"occ-{number}-{leaf}" for leaf in range(200))
        roots.append(
            {
                "root_cell_id": root_id,
                "selected_leaf_occurrence_ids": selected,
                "eligible_leaf_occurrence_ids": selected,
                "attested_occurrence_ids": (),
                "status": "not_attested",
            }
        )
    index.roots = tuple(roots)
    index.root_ids = tuple(root["root_cell_id"] for root in roots)
    index.roots_by_id = {root["root_cell_id"]: root for root in roots}
    with _client_for_history_index(monkeypatch, index) as client:
        response = client.get(
            f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots?limit=100"
        )
    assert response.status_code == 503
    _assert_private_headers(response)
    assert response.json() == {"detail": "attested query history temporarily unavailable"}


@pytest.mark.parametrize("failure", [None, RuntimeError("strict bounded read failed")])
def test_attested_history_missing_or_corrupt_private_reader_maps_to_private_503(monkeypatch, failure) -> None:
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    if failure is None:
        monkeypatch.setattr(forensics_api, "_build_store", lambda: None)
    else:
        monkeypatch.setattr(forensics_api, "_build_store", lambda: object())

        def raise_corrupt(_store, *, snapshot_id=None):
            raise failure

        monkeypatch.setattr(forensics_api, "load_attested_query_receipt_index", raise_corrupt)
    with TestClient(app) as client:
        response = client.get("/api/forensics/v1/attested-history/latest")
    assert response.status_code == 503
    assert response.json() == {"detail": "attested query history temporarily unavailable"}
    _assert_private_headers(response)


def test_private_store_factory_is_singleton_until_explicit_test_reset(monkeypatch) -> None:
    from engine.research_vault import r2_store

    calls: list[object] = []
    first = object()
    second = object()

    def build_once():
        calls.append(object())
        return first if len(calls) == 1 else second

    forensics_api._reset_store_cache()
    monkeypatch.setattr(r2_store, "build_store", build_once)
    assert forensics_api._build_store() is first
    assert forensics_api._build_store() is first
    assert len(calls) == 1
    forensics_api._reset_store_cache()
    assert forensics_api._build_store() is second
    assert len(calls) == 2
    forensics_api._reset_store_cache()


def test_attested_history_auth_and_entitlement_denial_happen_before_store(monkeypatch) -> None:
    import app.main as main_mod
    import app.paywall as paywall_mod

    reads: list[object] = []
    monkeypatch.setattr(main_mod, "require_user", lambda _authorization: {"id": "free-user"})

    def deny(_user, *, always=False):
        assert always is True
        raise HTTPException(402, "site_full required")

    monkeypatch.setattr(paywall_mod, "enforce_site_full", deny)
    monkeypatch.setattr(forensics_api, "_build_store", lambda: reads.append(object()))
    app = FastAPI()
    app.include_router(forensics_api.router)
    with TestClient(app) as client:
        response = client.get(
            "/api/forensics/v1/attested-history/latest",
            headers={"Authorization": "Bearer signed-in-free-user"},
        )
    assert response.status_code == 402
    assert response.json() == {"detail": "site_full required"}
    _assert_private_headers(response)
    assert reads == []


def test_authentication_error_cannot_weaken_route_private_headers(monkeypatch) -> None:
    import app.main as main_mod

    def deny_auth(_authorization):
        raise HTTPException(
            401,
            "missing bearer token",
            headers={
                "cache-control": "public, max-age=3600",
                "vArY": "Cookie",
                "x-content-TYPE-options": "unsafe",
                "X-ROBOTS-TAG": "index",
                "WWW-Authenticate": 'Bearer realm="members"',
            },
        )

    monkeypatch.setattr(main_mod, "require_user", deny_auth)
    with pytest.raises(HTTPException) as exc_info:
        forensics_api.require_site_full_user(None)
    assert exc_info.value.headers == {
        "WWW-Authenticate": 'Bearer realm="members"',
        "Cache-Control": "private, no-store",
        "Vary": "Authorization",
        "X-Content-Type-Options": "nosniff",
        "X-Robots-Tag": "noindex, noarchive",
    }


@pytest.mark.parametrize(
    "path",
    [
        "/api/forensics/v1/attested-history/latest/extra",
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/{ROOT_ALL}/extra",
        f"/api/forensics/v1/attested-history/snapshots/{SNAPSHOT_ID}/roots/{ROOT_ALL}%2Fextra",
    ],
)
def test_attested_history_extra_paths_are_private_and_never_read_store(monkeypatch, path) -> None:
    reads: list[object] = []
    monkeypatch.setattr(forensics_api, "_build_store", lambda: reads.append(object()))
    app = FastAPI()
    app.include_router(forensics_api.router)
    app.dependency_overrides[forensics_api.require_site_full_user] = lambda: {"id": "paid-user"}
    with TestClient(app) as client:
        response = client.get(path)
    assert response.status_code == 404
    assert response.json() == {"detail": "attested history route not found"}
    _assert_private_headers(response)
    assert reads == []


def test_attested_history_private_catchall_is_hidden_and_authenticated() -> None:
    route = next(
        route
        for route in forensics_api.router.routes
        if route.path == "/api/forensics/v1/attested-history/{remainder:path}"
    )
    dependency_calls = {dependency.call for dependency in route.dependant.dependencies}
    assert forensics_api.require_site_full_user in dependency_calls
    assert route.include_in_schema is False


def test_production_openapi_mounts_every_attested_history_route() -> None:
    import app.main as main_mod

    paths = main_mod.app.openapi().get("paths", {})
    assert "/api/forensics/v1/attested-history/latest" in paths
    assert "/api/forensics/v1/attested-history/snapshots/{snapshot_id}/roots" in paths
    assert "/api/forensics/v1/attested-history/snapshots/{snapshot_id}/roots/{root_cell_id}" in paths
