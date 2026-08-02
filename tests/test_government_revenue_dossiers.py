"""Focused public-contract tests for the read-only Government Revenue dossier rail."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from fastapi import HTTPException
from jsonschema import Draft202012Validator, FormatChecker

from app import government_revenue as api
from engine.government_revenue.dossiers import (
    COLLECTION_SCOPE_STATEMENT,
    build_dossier_payload,
    is_valid_dossier_payload,
)
from engine.government_revenue.workspace import build_procurement_workspace
from scripts import build_government_revenue


ROOT = Path(__file__).parents[1]
SCHEMA_PATH = ROOT / "contracts/government_revenue/government_revenue_dossiers.v1.schema.json"


def _write_sources(tmp_path: Path) -> None:
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    awards = pd.DataFrame([
        {
            "ticker": "LMT",
            "award_id": "SAME-PIID",
            "generated_award_id": "CONT/AWARD?ONE",
            "award_key": "generated:CONT/AWARD?ONE",
            "recipient_name": "Example Defense <b>Systems</b>",
            "recipient_uei": "UEI-ONE",
            "description": "Official <script>ignored()</script> award description",
            "start_date": "2026-01-02",
            "end_date": "2028-01-01",
            "base_obligation_date": "2026-01-02",
            "last_modified_date": "2026-06-01",
            "total_obligated": 125.0,
            "current_award_amount": 200.0,
            "potential_award_amount": 500.0,
            "total_outlays": 55.0,
            "awarding_agency": "Department of Defense",
            "awarding_sub_agency": "Air Force",
            "funding_agency": "Department of Defense",
            "funding_sub_agency": "Air Force",
            "award_type": "DEFINITIVE CONTRACT",
            "naics": "336414",
            "psc": "1510",
            "program": "Official Program",
            "known_at": "2026-06-02T01:00:00Z",
            "effective_at": "2026-06-01",
            "first_seen_at": "2026-06-02T01:00:00Z",
            "last_seen_at": "2026-06-02T01:00:00Z",
            "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/?api_key=secret&safe=1",
            "award_page_url": "https://www.usaspending.gov/award/CONT/AWARD?ONE/?token=secret&safe=1",
            "detail_source_url": "https://api.usaspending.gov/api/v2/awards/CONT/AWARD?ONE/?token=secret&safe=1",
            "raw_response": "must never serialize",
        },
        {
            "ticker": "LMT",
            "award_id": "SAME-PIID",
            "generated_award_id": "CONT_AWD_TWO",
            "award_key": "generated:CONT_AWD_TWO",
            "recipient_name": "Second Official Recipient",
            "recipient_uei": "UEI-TWO",
            "description": "Second official award",
            "start_date": "2026-02-02",
            "end_date": "2027-02-02",
            "base_obligation_date": "2026-02-02",
            "last_modified_date": "2026-06-02",
            "total_obligated": 20.0,
            "current_award_amount": 30.0,
            "potential_award_amount": 40.0,
            "total_outlays": 2.0,
            "awarding_agency": "Department of Energy",
            "awarding_sub_agency": "Office of Test",
            "funding_agency": "Department of Energy",
            "funding_sub_agency": "Office of Test",
            "award_type": "DELIVERY ORDER",
            "naics": "541512",
            "psc": "DA01",
            "program": "Second Program",
            "known_at": "2026-06-03T01:00:00Z",
            "effective_at": "2026-06-02",
            "first_seen_at": "2026-06-03T01:00:00Z",
            "last_seen_at": "2026-06-03T01:00:00Z",
            "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
            "award_page_url": "https://www.usaspending.gov/award/CONT_AWD_TWO/",
            "detail_source_url": "https://api.usaspending.gov/api/v2/awards/CONT_AWD_TWO/",
        },
    ])
    actions = pd.DataFrame([
        {
            "ticker": "LMT",
            "award_id": "SAME-PIID",
            "generated_award_id": "CONT/AWARD?ONE",
            "award_key": "generated:CONT/AWARD?ONE",
            "action_id": "NATIVE-ACTION-ONE",
            "action_date": "2026-06-01",
            "action_type": "A",
            "action_type_description": "OFFICIAL ACTION",
            "modification_number": "P00001",
            "federal_action_obligation": 12.0,
            "description": "Official action",
            "known_at": "2026-06-02T01:00:00Z",
            "effective_at": "2026-06-01",
            "first_seen_at": "2026-06-02T01:00:00Z",
            "source_url": "https://api.usaspending.gov/api/v2/transactions/?authorization=secret&safe=1",
            "award_page_url": "https://www.usaspending.gov/award/CONT/AWARD?ONE/",
            "token": "must not serialize",
        },
        {
            "ticker": "LMT",
            "award_id": "SAME-PIID",
            "generated_award_id": "CONT_AWD_TWO",
            "award_key": "generated:CONT_AWD_TWO",
            "action_id": "NATIVE-ACTION-TWO",
            "action_date": "2026-06-02",
            "action_type": "B",
            "action_type_description": "SECOND OFFICIAL ACTION",
            "modification_number": "P00002",
            "federal_action_obligation": -3.0,
            "description": "Second action",
            "known_at": "2026-06-03T01:00:00Z",
            "effective_at": "2026-06-02",
            "first_seen_at": "2026-06-03T01:00:00Z",
            "source_url": "https://api.usaspending.gov/api/v2/transactions/",
            "award_page_url": "https://www.usaspending.gov/award/CONT_AWD_TWO/",
        },
    ])
    awards.to_parquet(data_dir / "awards.parquet", index=False)
    actions.to_parquet(data_dir / "award_actions.parquet", index=False)
    (data_dir / "entities.json").write_text(json.dumps({
        "entities": {"LMT": {"name": "Lockheed Martin"}},
    }), encoding="utf-8")
    (data_dir / "ingest_status.json").write_text(json.dumps({
        "bounded": True,
        "effective_at": "2026-06-03",
        "observed_at": "2026-06-03T02:00:00Z",
    }), encoding="utf-8")


def _write_dossier_twins(tmp_path: Path) -> dict:
    payload = build_dossier_payload(tmp_path, as_of="2026-06-03")
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    canonical = tmp_path / "data" / "government_revenue" / "dossiers.json"
    site = tmp_path / "site" / "government-revenue-data" / "dossiers.json"
    site.parent.mkdir(parents=True)
    canonical.write_text(raw, encoding="utf-8")
    site.write_text(raw, encoding="utf-8")
    return payload


def test_dossier_contract_preserves_generated_identity_and_never_collapses_piid(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    payload = build_dossier_payload(tmp_path, as_of="2026-06-03")

    assert is_valid_dossier_payload(payload)
    assert payload["content_id"].startswith("grd1-") and len(payload["content_id"]) == 29
    assert len(payload["awards"]) == 2
    assert len({row["award_key"] for row in payload["awards"]}) == 2
    unsafe = next(row for row in payload["awards"] if row["identity"]["generated_award_id"] == "CONT/AWARD?ONE")
    assert "/" not in unsafe["award_key"]
    assert unsafe["identity"]["piid"] == "SAME-PIID"
    assert unsafe["values"] == {
        "obligated": 125.0,
        "current_award_value": 200.0,
        "ceiling": 500.0,
        "total_outlays": 55.0,
        "currency": "USD",
    }
    assert payload["companies"][0]["collection_scope"]["statement"] == COLLECTION_SCOPE_STATEMENT
    assert payload["source_coverage"]["issuer_attribution"]["records_attributed"] == 0
    rendered = json.dumps(payload)
    assert "must never serialize" not in rendered
    assert "api_key=secret" not in rendered
    assert "authorization=secret" not in rendered
    assert "token=secret" not in rendered


def test_dossier_schema_rejects_secret_shape_and_content_id_tampering(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    payload = build_dossier_payload(tmp_path, as_of="2026-06-03")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

    poisoned = json.loads(json.dumps(payload))
    poisoned["awards"][0]["private_receipt"] = "secret"
    assert not is_valid_dossier_payload(poisoned)


def test_dossier_rejects_synthetic_action_ids(tmp_path: Path) -> None:
    _write_sources(tmp_path)
    action_path = tmp_path / "data" / "government_revenue" / "award_actions.parquet"
    actions = pd.read_parquet(action_path)
    synthetic = actions.iloc[0].copy()
    synthetic["action_id"] = "SYNTHETIC-ACTION"
    synthetic["action_id_synthetic"] = True
    pd.concat([actions, pd.DataFrame([synthetic])], ignore_index=True).to_parquet(
        action_path, index=False
    )

    payload = build_dossier_payload(tmp_path, as_of="2026-06-03")

    assert "SYNTHETIC-ACTION" not in {row["action_id"] for row in payload["actions"]}
    assert payload["source_coverage"]["actions"]["status"] == "partial"
    poisoned = json.loads(json.dumps(payload))
    poisoned["content_id"] = "grd1-" + "0" * 24
    assert not is_valid_dossier_payload(poisoned)


def test_builder_publishes_byte_identical_dossier_twins(tmp_path: Path, monkeypatch) -> None:
    _write_sources(tmp_path)
    templates = tmp_path / "templates"
    templates.mkdir()
    (templates / "government_revenue.html.j2").write_text(
        "<main>{{ payload_json|safe }}</main>", encoding="utf-8"
    )
    workspace = build_procurement_workspace(
        {"freshness": {"status": "ok"}},
        [],
        as_of="2026-06-03",
        known_at="2026-06-03T02:00:00Z",
        award_freshness={"status": "ok"},
        award_event_freshness={"status": "unavailable"},
    )
    monkeypatch.setattr(build_government_revenue, "build_payload", lambda **_kwargs: {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-06-03",
        "known_at": "2026-06-03T02:00:00Z",
        "authority": {"tier": "display", "can_rank": False},
        "companies": [],
        "procurement_workspace": workspace,
    })

    build_government_revenue.build(tmp_path)

    canonical = tmp_path / "data" / "government_revenue" / "dossiers.json"
    site = tmp_path / "site" / "government-revenue-data" / "dossiers.json"
    assert canonical.exists() and canonical.read_bytes() == site.read_bytes()
    assert is_valid_dossier_payload(json.loads(canonical.read_text(encoding="utf-8")))


@pytest.fixture()
def dossier_artifact(tmp_path: Path, monkeypatch):
    _write_sources(tmp_path)
    payload = _write_dossier_twins(tmp_path)
    canonical = tmp_path / "data" / "government_revenue" / "dossiers.json"
    site = tmp_path / "site" / "government-revenue-data" / "dossiers.json"
    monkeypatch.setattr(api, "_DOSSIER_PATHS", (canonical, site))
    api._DOSSIER_CACHE.update(state=None, payload=None)
    return payload, canonical, site


def test_api_uses_precomputed_cursor_bound_dossier_records(dossier_artifact) -> None:
    payload, _, _ = dossier_artifact
    first = api.company_awards(
        "LMT", q="official", agency=None, naics=None, psc=None, award_type=None,
        sort="effective_desc", cursor=None, limit=1,
    )
    assert set(first) == {
        "schema_version", "content_id", "as_of", "known_at", "source_coverage",
        "freshness", "results", "next_cursor", "total",
    }
    assert first["content_id"] == payload["content_id"]
    assert first["total"] == 2 and len(first["results"]) == 1
    assert first["results"][0]["collection_scope_tickers"] == ["LMT"]
    assert first["results"][0]["source"]["award_search_url"].startswith("https://api.usaspending.gov/")
    assert "secret" not in json.dumps(first)
    second = api.company_awards(
        "LMT", q="official", agency=None, naics=None, psc=None, award_type=None,
        sort="effective_desc", cursor=first["next_cursor"], limit=1,
    )
    assert second["next_cursor"] is None
    assert second["results"][0]["award_key"] != first["results"][0]["award_key"]
    with pytest.raises(HTTPException) as exc:
        api.company_awards(
            "LMT", q="different", agency=None, naics=None, psc=None, award_type=None,
            sort="effective_desc", cursor=first["next_cursor"], limit=1,
        )
    assert exc.value.status_code == 400


def test_api_award_detail_actions_and_twin_mismatch_fail_closed(dossier_artifact) -> None:
    payload, canonical, site = dossier_artifact
    award_key = payload["awards"][0]["award_key"]
    detail = api.award(award_key)
    assert detail["award"]["award_key"] == award_key
    actions = api.award_actions(
        award_key, q=None, action_type=None, sort="effective_desc", cursor=None, limit=50,
    )
    assert actions["total"] == 1
    assert actions["results"][0]["source"]["native_action_id"] is True
    assert "issuer" not in json.dumps(detail["award"]["collection_scope_tickers"])

    site.write_text(site.read_text(encoding="utf-8") + " ", encoding="utf-8")
    api._DOSSIER_CACHE.update(state=None, payload=None)
    with pytest.raises(HTTPException) as exc:
        api.award(award_key)
    assert exc.value.status_code == 503
    assert canonical.exists()


def test_live_workflow_owns_both_dossier_twins() -> None:
    workflow = (ROOT / ".github" / "workflows" / "government-revenue-live.yml").read_text(
        encoding="utf-8"
    )
    for path in (
        "data/government_revenue/dossiers.json",
        "site/government-revenue-data/dossiers.json",
    ):
        assert workflow.count(path) >= 3
