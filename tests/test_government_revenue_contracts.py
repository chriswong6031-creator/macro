"""Machine-readable contract gates for Government Revenue Wave 2."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from engine.government_revenue.opportunities import build_opportunity_intelligence
from engine.government_revenue.workspace import build_procurement_workspace
from tests.test_government_revenue_opportunities import _company_payloads, _write_fixture


CONTRACTS = Path(__file__).parents[1] / "contracts" / "government_revenue"


def _schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _artifacts(tmp_path):
    _write_fixture(tmp_path)
    companies = _company_payloads()
    opportunity = build_opportunity_intelligence(
        tmp_path,
        companies,
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )
    workspace = build_procurement_workspace(
        opportunity,
        companies,
        as_of="2026-07-31",
        known_at="2026-08-01T23:59:59.999999+00:00",
        award_freshness={"status": "ok"},
    )
    return opportunity, workspace


def test_government_revenue_schemas_are_valid_draft_2020_12():
    for path in sorted(CONTRACTS.glob("*.schema.json")):
        Draft202012Validator.check_schema(json.loads(path.read_text(encoding="utf-8")))


def test_normalized_opportunities_satisfy_public_contract(tmp_path):
    opportunity, _ = _artifacts(tmp_path)
    validator = Draft202012Validator(
        _schema("government_opportunity.v1.schema.json"),
        format_checker=FormatChecker(),
    )
    for row in opportunity["opportunities"]:
        validator.validate(row)


def test_opportunity_contract_rejects_missing_point_in_time_clocks(tmp_path):
    opportunity, _ = _artifacts(tmp_path)
    validator = Draft202012Validator(
        _schema("government_opportunity.v1.schema.json"),
        format_checker=FormatChecker(),
    )
    for field in ("known_at", "effective_at"):
        row = dict(opportunity["opportunities"][0])
        row[field] = None
        assert list(validator.iter_errors(row)), f"{field} must fail closed"


def test_workspace_and_each_event_satisfy_contract(tmp_path):
    _, workspace = _artifacts(tmp_path)
    event_schema = _schema("government_procurement_event.v2.schema.json")
    workspace_schema = _schema("government_procurement_workspace.v2.schema.json")
    event_validator = Draft202012Validator(event_schema, format_checker=FormatChecker())
    for event in workspace["events"]:
        event_validator.validate(event)
        if event["kind"] in {"opportunity", "recompete"}:
            assert event["award_change"] is None

    registry = Registry().with_resource(
        event_schema["$id"], Resource.from_contents(event_schema)
    )
    Draft202012Validator(
        workspace_schema,
        registry=registry,
        format_checker=FormatChecker(),
    ).validate(workspace)


def test_contract_rejects_any_attempt_to_promote_display_authority(tmp_path):
    _, workspace = _artifacts(tmp_path)
    workspace["events"][0]["authority"]["can_rank"] = True
    validator = Draft202012Validator(_schema("government_procurement_event.v2.schema.json"))
    errors = list(validator.iter_errors(workspace["events"][0]))
    assert errors
    assert any("False was expected" in error.message for error in errors)
