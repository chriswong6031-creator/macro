"""Read-only API tests for the Wave 8 Government Revenue evidence rails."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException

import collectors.usaspending_idv_graph as idv_collector
from app import government_revenue as api
from engine.government_revenue.dossiers import build_dossier_payload
from engine.government_revenue.idv_dossiers import (
    build_idv_dossier_payload,
    idv_dossier_content_id,
)


_AWARD_KEY = "generated:CONT_AWD_CHILD_1010"
_CHILD_ID = "CONT_AWD_CHILD_1010"
_PARENT_ID = "CONT_IDV_PARENT_1010"
_LINE_KEY = "dod:p1:department-of-army:2031a:p1-line-item:10:fy2026:president-budget-request"
_PROGRAM_KEY = "dod-program:procurement-line-item:department-of-army:2031a:10"


def _prime() -> dict:
    return {
        "content_id": "grd1-" + "a" * 24,
        "awards": [{
            "award_key": _AWARD_KEY,
            "identity": {"generated_award_id": _CHILD_ID},
        }],
    }


def _budget_graph() -> dict:
    return {
        "contract": "government_budget_program_graph.v1",
        "schema_version": "1.0.0",
        "content_id": "grbg1-" + "b" * 24,
        "as_of": "2026-08-02",
        "known_at": "2026-08-02T00:00:00+00:00",
        "authority": {
            "tier": "display", "context_only": True, "can_rank": False,
            "can_size": False, "can_gate": False, "can_originate_signal": False,
            "can_add_candidates": False, "can_escalate": False,
        },
        "source_coverage": {
            "president_budget_request": {"status": "ok", "reason": "Official request exhibit."},
            "authorization": {"status": "uncollected", "reason": "Not collected."},
            "appropriation_enacted": {"status": "uncollected", "reason": "Not collected."},
            "execution": {"status": "uncollected", "reason": "Not collected."},
            "reviewed_award_edges": {"status": "partial", "reason": "No reviewed edges."},
        },
        "documents": [],
        "limitations": ["Request evidence only."],
        "lines": [{
            "line_key": _LINE_KEY,
            "program_name": "Example Program",
            "document_stage": "president_budget_request",
        }],
        "programs": [{
            "program_key": _PROGRAM_KEY,
            "kind": "procurement_line_item",
            "native_identifier": "10",
            "name": "Example Program",
            "line_keys": [_LINE_KEY],
        }],
        "edges": [{
            "contract": "government_budget_edge.v1",
            "edge_id": "budget-edge:" + "c" * 24,
            "from_type": "budget_line",
            "from_id": _LINE_KEY,
            "to_type": "program",
            "to_id": _PROGRAM_KEY,
            "edge_type": "source_native_identifier",
            "review_state": "official",
            "economic_weight": None,
            "effective_at": "2026-08-02T00:00:00+00:00",
            "known_at": "2026-08-02T00:00:00+00:00",
            "evidence": [],
        }],
    }


def _idv_payload() -> dict:
    return {
        "schema_version": "1.0.0",
        "content_id": "griv1-" + "d" * 24,
        "as_of": "2026-08-02",
        "known_at": "2026-08-02T00:00:00+00:00",
        "authority": {
            "tier": "display", "context_only": True, "can_rank": False,
            "can_size": False, "can_gate": False, "can_originate_signal": False,
            "can_add_candidates": False, "can_escalate": False,
        },
        "source_coverage": {"status": "ok"},
        "freshness": {"status": "ok"},
        "selection_provenance": {
            "status": "verified",
            "selection_source": "reviewed_source_native_idv_manifest",
            "selection_manifest_id": "idvsel1-" + "f" * 24,
            "reviewed_at": None,
            "selected_parent_count": 1,
            "scope_hashes": {
                "recipient_scope_sha256": None,
                "filters_semantic_sha256": None,
                "reviewed_manifest_sha256": "f" * 64,
            },
        },
        "limitations": ["Relationship evidence only."],
        "idvs": [{"idv_generated_award_id": _PARENT_ID}],
        "relationships": [{
            "relationship_key": "idvrel:" + "e" * 32,
            "child_award_key": _AWARD_KEY,
            "identity": {
                "idv_generated_award_id": _PARENT_ID,
                "child_generated_award_id": _CHILD_ID,
                "relationship_depth": "direct_child",
            },
            "recipient_name": "Official recipient",
            "agency": "Department of Defense",
            "dates": {}, "amounts": {},
            "source": {"activity_url": "https://api.usaspending.gov/api/v2/idvs/activity/"},
            "provenance": {"collection_scope_ticker": "LMT"},
        }],
    }


def test_budget_routes_only_project_precomputed_request_evidence(monkeypatch) -> None:
    graph = _budget_graph()
    monkeypatch.setattr(api, "_load_budget_program_graph", lambda: graph)

    listing = api.budget_programs()
    line = api.budget_line(_LINE_KEY)
    program = api.budget_program(_PROGRAM_KEY)

    assert listing["authority"]["can_rank"] is False
    assert listing["source_coverage"]["authorization"]["status"] == "uncollected"
    assert line["line"]["document_stage"] == "president_budget_request"
    assert line["source_native_edges"][0]["economic_weight"] is None
    assert program["program"]["line_keys"] == [_LINE_KEY]
    assert "beneficiar" not in json.dumps({"listing": listing, "line": line, "program": program}).casefold()

    with pytest.raises(HTTPException) as exc:
        api.budget_program("not-a-program")
    assert exc.value.status_code == 400


def test_public_scrubber_keeps_only_bounded_budget_authorization_coverage() -> None:
    safe = api._scrub_public({
        "authorization": {"status": "uncollected", "reason": "Not collected."},
    })
    assert safe == {"authorization": {"status": "uncollected", "reason": "Not collected."}}
    assert api._scrub_public({"authorization": "Bearer definitely-not-public"}) == {}


def test_award_idv_route_uses_only_the_exact_child_award_bridge(monkeypatch) -> None:
    monkeypatch.setattr(api, "_load_dossiers", _prime)
    monkeypatch.setattr(api, "_load_idv_dossiers", _idv_payload)

    result = api.award_idv_relationships(_AWARD_KEY)

    assert result["award_key"] == _AWARD_KEY
    assert result["total"] == 1
    relationship = result["relationships"][0]
    assert relationship["child_award_key"] == _AWARD_KEY
    assert relationship["identity"]["idv_generated_award_id"] == _PARENT_ID
    assert relationship["identity"]["relationship_depth"] == "direct_child"
    assert result["selection_provenance"]["selection_manifest_id"].startswith("idvsel1-")
    assert result["award_coverage"] == {
        "status": "observed",
        "exhaustive": False,
        "exact_relationship_count": 1,
        "selected_parent_count": 1,
        "selection_manifest_id": "idvsel1-" + "f" * 24,
        "reason": "Published exact generated-ID relationship observations for this award in the bounded active IDV cut.",
    }
    assert "issuer" not in json.dumps(result).casefold()


def test_idv_loader_requires_exact_canonical_public_twins(tmp_path: Path, monkeypatch) -> None:
    prime = build_dossier_payload(tmp_path, as_of="2026-08-02")
    idv = build_idv_dossier_payload(
        tmp_path,
        as_of="2026-08-02",
        prime_award_key_by_generated_id={},
    )
    data = tmp_path / "data" / "government_revenue"
    site = tmp_path / "site" / "government-revenue-data"
    data.mkdir(parents=True)
    site.mkdir(parents=True)
    prime_raw = json.dumps(prime, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    idv_raw = json.dumps(idv, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    data.joinpath("dossiers.json").write_text(prime_raw, encoding="utf-8")
    site.joinpath("dossiers.json").write_text(prime_raw, encoding="utf-8")
    data.joinpath("idv_dossiers.json").write_text(idv_raw, encoding="utf-8")
    site.joinpath("idv-dossiers.json").write_text(idv_raw, encoding="utf-8")
    monkeypatch.setattr(api, "_DOSSIER_PATHS", (data / "dossiers.json", site / "dossiers.json"))
    monkeypatch.setattr(api, "_IDV_DOSSIER_PATHS", (data / "idv_dossiers.json", site / "idv-dossiers.json"))
    api._DOSSIER_CACHE.update(state=None, payload=None)
    api._IDV_DOSSIER_CACHE.update(state=None, payload=None)

    assert api._load_idv_dossiers()["content_id"] == idv["content_id"]

    site.joinpath("idv-dossiers.json").write_text(idv_raw + " ", encoding="utf-8")
    api._IDV_DOSSIER_CACHE.update(state=None, payload=None)
    with pytest.raises(HTTPException) as exc:
        api._load_idv_dossiers()
    assert exc.value.status_code == 503


def _write_prime_twins(tmp_path: Path) -> dict:
    data = tmp_path / "data" / "government_revenue"
    site = tmp_path / "site" / "government-revenue-data"
    data.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{
        "ticker": "LMT",
        "award_id": "CHILD-1010",
        "generated_award_id": _CHILD_ID,
        "recipient_name": "Official recipient",
        "known_at": "2026-08-02T00:00:00+00:00",
        "effective_at": "2026-08-02",
        "start_date": "2026-08-02",
        "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
    }]).to_parquet(data / "awards.parquet", index=False)
    data.joinpath("entities.json").write_text(json.dumps({
        "entities": {"LMT": {"name": "Lockheed Martin"}},
    }), encoding="utf-8")
    data.joinpath("ingest_status.json").write_text(json.dumps({
        "bounded": True,
        "observed_at": "2026-08-02T00:00:00+00:00",
    }), encoding="utf-8")
    prime = build_dossier_payload(tmp_path, as_of="2026-08-02")
    assert prime["awards"][0]["award_key"] == _AWARD_KEY
    raw = json.dumps(prime, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    data.joinpath("dossiers.json").write_text(raw, encoding="utf-8")
    site.joinpath("dossiers.json").write_text(raw, encoding="utf-8")
    return prime


def _write_idv_twins(tmp_path: Path, payload: dict) -> None:
    data = tmp_path / "data" / "government_revenue"
    site = tmp_path / "site" / "government-revenue-data"
    data.mkdir(parents=True, exist_ok=True)
    site.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    data.joinpath("idv_dossiers.json").write_text(raw, encoding="utf-8")
    site.joinpath("idv-dossiers.json").write_text(raw, encoding="utf-8")


def _wire_artifact_paths(tmp_path: Path, monkeypatch) -> None:
    data = tmp_path / "data" / "government_revenue"
    site = tmp_path / "site" / "government-revenue-data"
    monkeypatch.setattr(api, "_DOSSIER_PATHS", (data / "dossiers.json", site / "dossiers.json"))
    monkeypatch.setattr(api, "_IDV_DOSSIER_PATHS", (data / "idv_dossiers.json", site / "idv-dossiers.json"))
    api._DOSSIER_CACHE.update(state=None, payload=None)
    api._IDV_DOSSIER_CACHE.update(state=None, payload=None)


def _collect_idv(tmp_path: Path, *, total: int, observed_at: str = "2026-08-02T01:00:00+00:00") -> None:
    class Response:
        status_code = 200

        def __init__(self, payload: dict) -> None:
            self.payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self.payload

    class Session:
        def post(self, *_args, **_kwargs) -> Response:
            rows = [] if total == 0 else [{
                "generated_unique_award_id": _CHILD_ID,
                "parent_generated_unique_award_id": _PARENT_ID,
                "grandchild": False,
                "parent_award_piid": "PARENT-1010",
                "piid": "CHILD-1010",
                "recipient_name": "Official recipient",
                "awarding_agency": "Department of Defense",
                "period_of_performance_start_date": "2026-08-02",
            }]
            return Response({
                "results": rows,
                "page_metadata": {"page": 1, "total": total, "hasNext": False},
            })

    idv_collector.UsaspendingIdvGraphCollector(
        root=tmp_path,
        session=Session(),
        reviewed_idv_ids=[_PARENT_ID],
        request_pacing_seconds=0,
    ).collect(observed_at=observed_at)


def test_idv_actual_artifact_distinguishes_unavailable_from_verified_zero(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_prime_twins(tmp_path)
    unavailable = build_idv_dossier_payload(
        tmp_path,
        as_of="2026-08-02",
        prime_award_key_by_generated_id={_CHILD_ID: _AWARD_KEY},
    )
    _write_idv_twins(tmp_path, unavailable)
    _wire_artifact_paths(tmp_path, monkeypatch)

    unavailable_result = api.award_idv_relationships(_AWARD_KEY)
    assert unavailable_result["source_coverage"]["status"] == "unavailable"
    assert unavailable_result["selection_provenance"]["status"] == "unavailable"
    assert unavailable_result["award_coverage"]["status"] == "unavailable"
    assert unavailable_result["award_coverage"]["exhaustive"] is False
    assert unavailable_result["relationships"] == []

    _collect_idv(tmp_path, total=0)
    verified_zero = build_idv_dossier_payload(
        tmp_path,
        as_of="2026-08-02",
        prime_award_key_by_generated_id={_CHILD_ID: _AWARD_KEY},
    )
    assert verified_zero["idvs"][0]["coverage"]["collection_state"] == "zero"
    _write_idv_twins(tmp_path, verified_zero)
    api._IDV_DOSSIER_CACHE.update(state=None, payload=None)

    zero_result = api.award_idv_relationships(_AWARD_KEY)
    assert zero_result["source_coverage"]["status"] == "ok"
    assert zero_result["selection_provenance"]["status"] == "verified"
    assert zero_result["selection_provenance"]["selected_parent_count"] == 1
    assert zero_result["award_coverage"]["status"] == "not_observed"
    assert zero_result["award_coverage"]["exhaustive"] is False
    assert "absence is not evidence" in zero_result["award_coverage"]["reason"]
    assert zero_result["relationships"] == []


def test_idv_actual_artifact_route_enforces_source_allowlist_and_bounded_selection_receipt(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_prime_twins(tmp_path)
    _collect_idv(tmp_path, total=1)
    payload = build_idv_dossier_payload(
        tmp_path,
        as_of="2026-08-02",
        prime_award_key_by_generated_id={_CHILD_ID: _AWARD_KEY},
    )
    _write_idv_twins(tmp_path, payload)
    _wire_artifact_paths(tmp_path, monkeypatch)

    result = api.award_idv_relationships(_AWARD_KEY)
    assert result["relationships"][0]["source"] == {
        "publisher": "USAspending.gov",
        "activity_url": idv_collector.IDV_ACTIVITY_URL,
    }
    assert result["selection_provenance"]["selection_source"] == "reviewed_source_native_idv_manifest"
    assert result["award_coverage"]["status"] == "observed"
    rendered = json.dumps(result, sort_keys=True)
    assert "selected_parent_ids" not in rendered
    assert "discovery_receipts" not in rendered
    assert "request_payload" not in rendered
    assert "parent_award_key" not in rendered
    assert set(result["selection_provenance"]["scope_hashes"]) == {
        "recipient_scope_sha256",
        "filters_semantic_sha256",
        "reviewed_manifest_sha256",
    }

    poisoned = json.loads(json.dumps(payload))
    poisoned["relationships"][0]["source"]["activity_url"] = "https://example.com/not-official"
    poisoned["content_id"] = idv_dossier_content_id(poisoned)
    _write_idv_twins(tmp_path, poisoned)
    api._IDV_DOSSIER_CACHE.update(state=None, payload=None)
    with pytest.raises(HTTPException) as exc:
        api.award_idv_relationships(_AWARD_KEY)
    assert exc.value.status_code == 503


def test_idv_state_status_mismatch_cannot_publish_an_api_artifact(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_prime_twins(tmp_path)
    _collect_idv(tmp_path, total=1)
    status_path = tmp_path / "data" / "government_revenue" / idv_collector.IDV_INGEST_STATUS_FILENAME
    status = json.loads(status_path.read_text(encoding="utf-8"))
    status["run_id"] = "usaspending-idv-mismatched-run"
    status_path.write_text(json.dumps(status), encoding="utf-8")

    with pytest.raises(ValueError, match="not publication eligible"):
        build_idv_dossier_payload(
            tmp_path,
            as_of="2026-08-02",
            prime_award_key_by_generated_id={_CHILD_ID: _AWARD_KEY},
        )

    _wire_artifact_paths(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        api.award_idv_relationships(_AWARD_KEY)
    assert exc.value.status_code == 503
