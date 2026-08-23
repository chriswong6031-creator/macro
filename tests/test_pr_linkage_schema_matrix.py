"""Closed-wire schema and receipt matrix for MAS-28 V1."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from lib import pr_linkage_validator as validator
from tests.test_pr_linkage_validator import MANIFEST, VALID, observation, report

ROOT = Path(__file__).parents[1]
SCHEMAS = {
    "observation": ROOT / "contracts/pr_linkage/pr_linkage_observation.v1.schema.json",
    "report": ROOT / "contracts/pr_linkage/pr_linkage_report.v1.schema.json",
    "manifest": ROOT / "contracts/pr_linkage/pr_linkage_rule_manifest.v1.schema.json",
    "execution_error": ROOT / "contracts/pr_linkage/pr_linkage_execution_error.v1.schema.json",
}


def load(name):
    return json.loads(SCHEMAS[name].read_text())


def envelope(route):
    error = {"code": route["error_code"], "component": route["component"], "reason_code": route["reason_code"], "limit": None, "observed": None}
    return {"schema": "mastermind.pr_linkage_execution_error.v1", "enforcement": "REPORT_ONLY", "error": error, "execution_error_hash": validator.digest(error), "receipt": {"input_sha256": None, "source_sha": None, "producer": "test"}}


@pytest.mark.parametrize("name,value", [
    ("manifest", MANIFEST),
    ("observation", observation(VALID)),
    ("report", report()),
    ("execution_error", envelope(MANIFEST["execution_error"]["routes"][0])),
])
def test_all_four_v1_schemas_accept_canonical_examples(name, value):
    jsonschema.Draft202012Validator(load(name)).validate(value)


@pytest.mark.parametrize("route", MANIFEST["execution_error"]["routes"], ids=lambda r: r["reason_code"])
def test_all_twenty_execution_routes_have_closed_schema_envelopes(route):
    result = envelope(route)
    jsonschema.Draft202012Validator(load("execution_error")).validate(result)
    assert result["execution_error_hash"] == validator.digest(result["error"])


def test_receipt_projection_covers_all_ten_frozen_components():
    o = observation(VALID)
    projection = validator.receipt_projection(o, MANIFEST)
    assert list(projection) == ["OBSERVATION", "BODY", "CUTOVER", "RULESET", "AUTHORING_EPOCH", "CHANGED_PATHS", "AGENTOS", "LINEAR", "PATH_OWNERSHIP", "NATIVE_LINKAGE"]
    for component in projection:
        mutant = json.loads(validator.canonical_json(o))
        key = {"OBSERVATION": "observation_sha256", "BODY": "body_sha256", "CUTOVER": "cutover_receipt_sha256", "RULESET": "ruleset_digest"}.get(component)
        if key:
            mutant["receipt"][key] = "0" * 64 if component != "CUTOVER" else "0" * 64
        else:
            mutant["receipt"]["snapshot_digests"][component.lower()] = "0" * 64
        matches = [f for f in validator.analyze(mutant, MANIFEST)["semantic"]["findings"] if f["rule_id"] == "R060" and f["evidence"]["component"] == component]
        assert len(matches) == 1
        assert matches[0]["location"] == "RECEIPT:" + component


def test_schema_measurement(capsys):
    print(f"schemas={len(SCHEMAS)} rules={len(MANIFEST['rules'])}")
    assert len(SCHEMAS) == 4 and len(MANIFEST["rules"]) == 46
