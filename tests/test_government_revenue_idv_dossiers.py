"""Contract tests for the source-native, display-only IDV dossier projector."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import collectors.usaspending_idv_graph as collector
from engine.government_revenue.idv_dossiers import (
    build_idv_dossier_payload,
    idv_dossier_content_id,
    is_valid_idv_dossier_payload,
)


PARENT = "CONT_IDV_PARENT_1010"
CHILD = "CONT_AWD_CHILD_A_1010_PARENT_1010"
GRANDCHILD = "CONT_AWD_GRANDCHILD_B_1010_PARENT_1010"
OBSERVED = "2026-08-02T00:00:00+00:00"
FIXTURE = Path(__file__).parent / "fixtures" / "usaspending_idv_activity_page.json"


def _write_bundle(
    tmp_path: Path,
    *,
    high_count_only: bool = False,
    observed_at: str = OBSERVED,
) -> None:
    data = tmp_path / "data" / "government_revenue"
    data.mkdir(parents=True, exist_ok=True)
    response = json.loads(FIXTURE.read_text(encoding="utf-8"))
    reported_count = 501 if high_count_only else len(response["results"])
    receipt = collector.UsaspendingIdvGraphCollector._receipt(
        request_payload={"award_id": PARENT, "page": 1, "limit": 100, "hide_edge_cases": False},
        response_payload=response,
        idv_generated_award_id=PARENT,
        observed_at=observed_at,
        page=1,
        record_count=100 if high_count_only else len(response["results"]),
        reported_child_award_count=reported_count,
    )
    rows = [] if high_count_only else [
        collector.normalize_idv_relationship(raw, PARENT, receipt, observed_at)
        for raw in response["results"]
    ]
    active_relationships = [
        {
            "child_generated_award_id": row["child_generated_award_id"],
            "grandchild": row["grandchild"],
            "idv_relationship_state_sha256": row["idv_relationship_state_sha256"],
            "source_receipt_id": row["source_receipt_id"],
        }
        for row in rows
    ]
    active_relationships.sort(key=collector._canonical_json_bytes)
    frame = pd.DataFrame(rows, columns=collector.IDV_RELATIONSHIP_SNAPSHOT_COLUMNS)
    state_name = "high_count_count_only" if high_count_only else "complete"
    parent_state = {
        "idv_generated_award_id": PARENT,
        "child_award_count": reported_count,
        "count_verified": True,
        "collection_state": state_name,
        "detail_rows": 0 if high_count_only else len(rows),
        "pages_fetched": 0 if high_count_only else 1,
        "source_exhausted": not high_count_only,
        "count_receipt_id": receipt["receipt_id"],
        "count_receipt_binding": {
            "receipt_id": receipt["receipt_id"],
            "idv_generated_award_id": PARENT,
            "reported_child_award_count": reported_count,
        },
        "detail_receipt_ids": [] if high_count_only else [receipt["receipt_id"]],
        "active_relationships": active_relationships,
        "active_relationships_semantic_sha256": collector.idv_active_relationships_semantic_sha256(active_relationships),
    }
    generation = collector.idv_projection_generation(frame)
    selection_manifest = {
        "schema_version": collector.SCHEMA_VERSION,
        "contract": collector.IDV_SELECTION_MANIFEST_SCHEMA,
        "selection_source": "reviewed_source_native_idv_manifest",
        "observed_at": observed_at,
        "reviewed_at": None,
        "endpoint": None,
        "collection_scope_tickers": [],
        "recipient_scope_sha256": None,
        "filters_semantic_sha256": None,
        "reviewed_manifest_sha256": collector._sha256_json([PARENT]),
        "discovery_receipts": [],
        "selected_parent_ids": [PARENT],
        "semantic_sha256": "",
    }
    selection_manifest["semantic_sha256"] = collector.idv_selection_manifest_semantic_sha256(selection_manifest)
    bounds = {
        "max_idvs": collector.MAX_IDVS,
        "selected_idv_limit": collector.MAX_IDVS,
        "page_size": collector.PAGE_SIZE,
        "max_pages_per_idv": collector.MAX_PAGES_PER_IDV,
        "max_detail_rows_per_idv": collector.MAX_DETAIL_ROWS_PER_IDV,
        "max_detail_rows_per_run": collector.MAX_DETAIL_ROWS_PER_RUN,
        "public_downstream_row_cap": collector.PUBLIC_DOWNSTREAM_ROW_CAP,
    }
    run_id = "usaspending-idv-test-generation"
    state = {
        "schema_version": collector.SCHEMA_VERSION,
        "contract": collector.IDV_PROJECTION_STATE_SCHEMA,
        "activation_state": "live",
        "bounded_collection_complete": True,
        "projection_eligible": True,
        "run_id": run_id,
        "observed_at": observed_at,
        "last_successful_observed_at": observed_at,
        "selected_idv_count": 1,
        "selection_source": "reviewed_source_native_idv_manifest",
        "selection_manifest_semantic_sha256": selection_manifest["semantic_sha256"],
        "selection_manifest": selection_manifest,
        "detail_rows_this_run": len(rows),
        "bounds": bounds,
        "public_downstream_row_cap": 2000,
        "parents": [parent_state],
        "parent_coverage_semantic_sha256": collector.idv_parent_coverage_semantic_sha256([parent_state]),
        **generation,
    }
    status = {
        "schema_version": collector.SCHEMA_VERSION,
        "contract": collector.IDV_INGEST_STATUS_SCHEMA,
        "status": "ok",
        "partial": False,
        "collection_complete": True,
        "projection_eligible": True,
        "observed_at": observed_at,
        "last_successful_observed_at": observed_at,
        "run_id": run_id,
        "projection_generation_id": generation["projection_generation_id"],
        "bounded": True,
        "source_only": True,
        "daily_lane": True,
        "idvs_selected": 1,
        "detail_rows_seen": len(rows),
        "snapshot_versions_total": len(frame),
        "selection_source": "reviewed_source_native_idv_manifest",
        "selection_manifest_semantic_sha256": selection_manifest["semantic_sha256"],
        "bounds": bounds,
        "errors": [],
    }
    frame.to_parquet(data / collector.IDV_RELATIONSHIP_SNAPSHOTS_FILENAME, index=False)
    (data / collector.IDV_COLLECTION_RECEIPTS_FILENAME).write_text(json.dumps(receipt) + "\n", encoding="utf-8")
    (data / collector.IDV_PROJECTION_STATE_FILENAME).write_text(json.dumps(state), encoding="utf-8")
    (data / collector.IDV_INGEST_STATUS_FILENAME).write_text(json.dumps(status), encoding="utf-8")


def test_empty_first_payload_is_honest_and_valid(tmp_path: Path) -> None:
    payload = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")

    assert payload["source_coverage"]["status"] == "unavailable"
    assert payload["selection_provenance"] == {
        "status": "unavailable",
        "selection_source": None,
        "selection_manifest_id": None,
        "reviewed_at": None,
        "selected_parent_count": 0,
        "scope_hashes": {
            "recipient_scope_sha256": None,
            "filters_semantic_sha256": None,
            "reviewed_manifest_sha256": None,
        },
    }
    assert payload["idvs"] == []
    assert payload["relationships"] == []
    assert is_valid_idv_dossier_payload(payload)


def test_projector_keeps_idv_parent_standalone_and_exactly_bridges_child(tmp_path: Path) -> None:
    _write_bundle(tmp_path)

    payload = build_idv_dossier_payload(
        tmp_path,
        prime_award_key_by_generated_id={CHILD: "generated:child-a", "CONT_AWD_NEAR_MATCH": "generated:other"},
        collection_scope_ticker="LMT",
        as_of="2026-08-02",
    )

    assert payload["idvs"][0]["idv_generated_award_id"] == PARENT
    assert "award_key" not in payload["idvs"][0]
    direct = next(row for row in payload["relationships"] if row["identity"]["child_generated_award_id"] == CHILD)
    grandchild = next(row for row in payload["relationships"] if row["identity"]["child_generated_award_id"] == GRANDCHILD)
    assert direct["child_award_key"] == "generated:child-a"
    assert grandchild["child_award_key"] is None
    assert grandchild["identity"]["relationship_depth"] == "grandchild_award"
    assert all("parent_award_key" not in row for row in payload["relationships"])
    assert direct["provenance"]["collection_scope_ticker"] == "LMT"
    provenance = payload["selection_provenance"]
    assert provenance["status"] == "verified"
    assert provenance["selection_source"] == "reviewed_source_native_idv_manifest"
    assert provenance["selection_manifest_id"].startswith("idvsel1-")
    assert provenance["selected_parent_count"] == 1
    assert provenance["scope_hashes"]["reviewed_manifest_sha256"] is not None
    assert is_valid_idv_dossier_payload(payload)
    assert idv_dossier_content_id(payload) == payload["content_id"]


def test_official_discovery_projects_only_hashed_selection_scope(tmp_path: Path) -> None:
    class Response:
        status_code = 200

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class Session:
        def post(self, endpoint: str, **_kwargs) -> Response:
            if endpoint == collector.IDV_DISCOVERY_URL:
                return Response({
                    "results": [{"generated_internal_id": PARENT}],
                    "page_metadata": {"page": 1, "hasNext": False},
                })
            return Response(json.loads(FIXTURE.read_text(encoding="utf-8")))

    filters = {
        "recipient_search_text": ["REVIEWED COLLECTION TERM"],
        "award_type_codes": list(collector.IDV_DISCOVERY_AWARD_TYPE_CODES),
    }
    collector.UsaspendingIdvGraphCollector(
        root=tmp_path,
        session=Session(),
        idv_discovery_request={
            "filters": filters,
            "reviewed_at": "2026-08-01T12:00:00+00:00",
            "collection_scope_tickers": ["LMT"],
        },
        request_pacing_seconds=0,
    ).collect(observed_at=OBSERVED)

    payload = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")
    provenance = payload["selection_provenance"]
    assert provenance["status"] == "verified"
    assert provenance["selection_source"] == "official_usaspending_idv_discovery"
    assert provenance["reviewed_at"] == "2026-08-01T12:00:00+00:00"
    assert provenance["scope_hashes"]["recipient_scope_sha256"] is not None
    assert provenance["scope_hashes"]["filters_semantic_sha256"] is not None
    assert provenance["scope_hashes"]["reviewed_manifest_sha256"] is None
    rendered = json.dumps(payload)
    assert "REVIEWED COLLECTION TERM" not in rendered
    assert "selected_parent_ids" not in rendered
    assert "discovery_receipts" not in rendered
    assert is_valid_idv_dossier_payload(payload)


def test_projector_rejects_tampered_snapshot_state_hash(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "data" / "government_revenue" / collector.IDV_RELATIONSHIP_SNAPSHOTS_FILENAME
    frame = pd.read_parquet(path)
    frame.loc[0, "idv_relationship_state_sha256"] = "0" * 64
    frame.to_parquet(path, index=False)

    with pytest.raises(ValueError, match="activation generation"):
        build_idv_dossier_payload(tmp_path)


def test_high_count_parent_exposes_count_coverage_but_no_sampled_relationships(tmp_path: Path) -> None:
    _write_bundle(tmp_path, high_count_only=True)

    payload = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")

    envelope = payload["idvs"][0]
    assert envelope["coverage"]["collection_state"] == "high_count_count_only"
    assert envelope["coverage"]["status"] == "partial"
    assert envelope["coverage"]["reported_count"] == 501
    assert payload["relationships"] == []
    assert is_valid_idv_dossier_payload(payload)


def test_complete_parent_becoming_count_only_never_leaks_historical_details(tmp_path: Path) -> None:
    class Response:
        status_code = 200

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class Session:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def post(self, *_args, **_kwargs) -> Response:
            return Response(self.payload)

    def source_row(index: int) -> dict:
        return {
            "generated_unique_award_id": f"CONT_AWD_CHILD_{index}",
            "parent_generated_unique_award_id": PARENT,
            "grandchild": False,
            "parent_award_piid": "IDV-PIID",
            "piid": f"CHILD-{index}",
            "period_of_performance_start_date": "2026-01-01",
        }

    first = {"results": [source_row(1)], "page_metadata": {"page": 1, "total": 1, "hasNext": False}}
    collector.UsaspendingIdvGraphCollector(
        root=tmp_path,
        session=Session(first),
        reviewed_idv_ids=[PARENT],
        request_pacing_seconds=0,
    ).collect(observed_at="2026-08-02T01:00:00+00:00")
    complete = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")
    assert [row["identity"]["child_generated_award_id"] for row in complete["relationships"]] == [
        "CONT_AWD_CHILD_1"
    ]

    count_only = {
        "results": [source_row(index) for index in range(100)],
        "page_metadata": {"page": 1, "total": 501, "hasNext": True},
    }
    collector.UsaspendingIdvGraphCollector(
        root=tmp_path,
        session=Session(count_only),
        reviewed_idv_ids=[PARENT],
        request_pacing_seconds=0,
    ).collect(observed_at="2026-08-02T02:00:00+00:00")
    projected = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")

    envelope = projected["idvs"][0]
    assert envelope["coverage"]["collection_state"] == "high_count_count_only"
    assert envelope["coverage"]["status"] == "partial"
    assert envelope["coverage"]["reported_count"] == 501
    assert envelope["relationship_count"] == 0
    assert envelope["relationship_keys"] == []
    assert projected["relationships"] == []
    historical = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / collector.IDV_RELATIONSHIP_SNAPSHOTS_FILENAME
    )
    assert "CONT_AWD_CHILD_1" in set(historical["child_generated_award_id"])
    assert is_valid_idv_dossier_payload(projected)


def test_public_validator_rejects_contradictory_complete_coverage(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    payload = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")
    poisoned = json.loads(json.dumps(payload))
    poisoned["relationships"] = []
    poisoned["idvs"][0]["relationship_keys"] = []
    poisoned["idvs"][0]["relationship_count"] = 0
    poisoned["idvs"][0]["coverage"]["records_published"] = 0
    poisoned["content_id"] = idv_dossier_content_id(poisoned)

    assert not is_valid_idv_dossier_payload(poisoned)


def test_projector_rejects_mixed_state_status_generation(tmp_path: Path) -> None:
    _write_bundle(tmp_path)
    path = tmp_path / "data" / "government_revenue" / collector.IDV_INGEST_STATUS_FILENAME
    status = json.loads(path.read_text(encoding="utf-8"))
    status["run_id"] = "usaspending-idv-different-run"
    path.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(ValueError, match="not publication eligible"):
        build_idv_dossier_payload(tmp_path)


def test_projector_labels_old_complete_generation_stale(tmp_path: Path) -> None:
    _write_bundle(tmp_path, observed_at="2020-01-02T00:00:00+00:00")

    payload = build_idv_dossier_payload(tmp_path, as_of="2020-01-02")

    assert payload["source_coverage"]["status"] == "ok"
    assert payload["freshness"]["status"] == "stale"
    assert "4-day freshness window" in payload["freshness"]["reason"]
    assert is_valid_idv_dossier_payload(payload)


def test_active_generation_handles_roster_rotation_reobservation_and_removal(tmp_path: Path) -> None:
    class Response:
        status_code = 200

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class Session:
        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def post(self, *_args, **_kwargs) -> Response:
            return Response(self.payload)

    def collect(parent: str, child: str | None, observed_at: str) -> None:
        rows = [] if child is None else [{
            "generated_unique_award_id": child,
            "parent_generated_unique_award_id": parent,
            "grandchild": False,
            "parent_award_piid": "IDV-PIID",
            "piid": "CHILD-PIID",
            "period_of_performance_start_date": "2026-01-01",
        }]
        payload = {
            "results": rows,
            "page_metadata": {"page": 1, "total": len(rows), "hasNext": False},
        }
        collector.UsaspendingIdvGraphCollector(
            root=tmp_path,
            session=Session(payload),
            reviewed_idv_ids=[parent],
            request_pacing_seconds=0,
        ).collect(observed_at=observed_at)

    parent_a, parent_b = "CONT_IDV_PARENT_A", "CONT_IDV_PARENT_B"
    child_a, child_b = "CONT_AWD_CHILD_A", "CONT_AWD_CHILD_B"
    collect(parent_a, child_a, "2026-08-02T01:00:00+00:00")
    collect(parent_b, child_b, "2026-08-02T02:00:00+00:00")
    rotated = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")
    assert [row["identity"]["child_generated_award_id"] for row in rotated["relationships"]] == [child_b]

    collect(parent_b, child_b, "2026-08-02T03:00:00+00:00")
    frame = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / collector.IDV_RELATIONSHIP_SNAPSHOTS_FILENAME
    )
    assert len(frame) == 2
    reconfirmed = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")
    assert reconfirmed["relationships"][0]["dates"]["known_at"] == "2026-08-02T03:00:00+00:00"

    collect(parent_b, None, "2026-08-02T04:00:00+00:00")
    removed = build_idv_dossier_payload(tmp_path, as_of="2026-08-02")
    assert removed["relationships"] == []
    assert removed["idvs"][0]["coverage"]["collection_state"] == "zero"
