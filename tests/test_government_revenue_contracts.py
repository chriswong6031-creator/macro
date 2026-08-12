"""Machine-readable contract gates for Government Revenue Wave 2."""
from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import json
from pathlib import Path

import pandas as pd
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from engine.government_revenue.opportunities import build_opportunity_intelligence
from engine.government_revenue.workspace import (
    build_procurement_workspace,
    is_valid_procurement_workspace,
)
from tests.test_government_revenue_opportunities import _company_payloads, _write_fixture


ROOT = Path(__file__).parents[1]
CONTRACTS = ROOT / "contracts" / "government_revenue"
CANONICAL = ROOT / "data" / "government_revenue"


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


@lru_cache(maxsize=None)
def _committed(name: str) -> dict:
    """Parse a committed canonical Government Revenue artifact once per session."""
    return json.loads((CANONICAL / name).read_text(encoding="utf-8"))


def _workspace_errors(workspace: dict) -> list[str]:
    """Name every contract violation the reader gate can only report as ``False``."""
    event_schema = _schema("government_procurement_event.v2.schema.json")
    registry = Registry()
    for schema in (
        event_schema,
        _schema("government_entity_coverage.v1.schema.json"),
        _schema("government_recipient_resolution_coverage.v1.schema.json"),
    ):
        registry = registry.with_resource(schema["$id"], Resource.from_contents(schema))
    validator = Draft202012Validator(
        _schema("government_procurement_workspace.v2.schema.json"),
        registry=registry,
        format_checker=FormatChecker(),
    )
    return [
        f"{'/'.join(str(part) for part in error.absolute_path)}: {error.validator}"
        for error in validator.iter_errors(workspace)
    ]


def test_committed_canonical_generation_still_satisfies_the_shipped_contract():
    """A contract edit must never retroactively invalidate already-published bytes.

    #4951 made ``recipient_query_terms`` required without bumping the manifest
    version, invalidating the canonical generation for render, API, and candidate
    readers; #5131 relaxed it until the committed bytes carried the field, and
    requiredness returned on 2026-08-11 once they did. This test preserves #5141's
    unique tooth by validating the real committed bytes and naming paths — it is
    what makes a retightening evidence-led instead of retroactive.
    """
    latest = _committed("latest.json")
    workspace = _committed("workspace.json")
    for label, document in (
        ("latest.procurement_workspace", latest.get("procurement_workspace")),
        ("workspace.json", workspace),
    ):
        assert isinstance(document, dict), f"{label} is not an object"
        assert is_valid_procurement_workspace(document), (
            f"{label} no longer satisfies the shipped workspace contract: "
            f"{_workspace_errors(document)}"
        )


def test_coverage_manifest_requires_query_terms_and_stays_typed():
    """The enriched v1 entity is now the only entity shape the manifest reads.

    ``recipient_query_terms`` returned to ``required`` on 2026-08-11, once every
    entity of the committed manifest carried it — the precondition #5131 wrote
    into the schema when it relaxed #4951's too-early requirement. The legacy
    pre-field shape that the compatibility window admitted is therefore rejected
    from here on, and the typed rejections keep the field itself honest.
    """
    manifest_schema = _schema("government_procurement_workspace.v2.schema.json")["$defs"][
        "coverageManifest"
    ]
    validator = Draft202012Validator(manifest_schema, format_checker=FormatChecker())
    committed = deepcopy(
        _committed("latest.json")["procurement_workspace"]["freshness"]["award_events"][
            "coverage_manifest"
        ]
    )
    assert committed["entities"], "the committed coverage manifest declares no entities"
    assert all(
        entity.get("recipient_query_terms") for entity in committed["entities"]
    ), "the committed manifest must carry recipient_query_terms on every entity"
    assert not list(validator.iter_errors(committed))

    enriched = deepcopy(committed)
    for entity in enriched["entities"]:
        entity["recipient_query_terms"] = [entity["recipient_search_text"]]
    assert not list(validator.iter_errors(enriched))

    legacy = deepcopy(committed)
    for entity in legacy["entities"]:
        entity.pop("recipient_query_terms", None)
    empty_terms = deepcopy(enriched)
    empty_terms["entities"][0]["recipient_query_terms"] = []
    non_string_terms = deepcopy(enriched)
    non_string_terms["entities"][0]["recipient_query_terms"] = [7]
    unknown_key = deepcopy(enriched)
    unknown_key["entities"][0]["recipient_query_terms_dropped"] = ["X"]
    missing_primary = deepcopy(enriched)
    missing_primary["entities"][0].pop("recipient_search_text")
    for rejected in (legacy, empty_terms, non_string_terms, unknown_key, missing_primary):
        assert list(validator.iter_errors(rejected))
