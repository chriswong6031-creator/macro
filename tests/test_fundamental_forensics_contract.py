"""Contract, golden replay, dependency isolation, and honesty tests."""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator
import requests

from engine.fundamental_forensics import load_registry, run_fixture_slice


ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "fundamental_forensics"
REGISTRY_PATH = ROOT / "config" / "fundamental_forensics.yml"
SCHEMA_PATH = ROOT / "contracts" / "fundamental_forensics_run.schema.json"
DECIMAL_RE = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$")


def _load(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _run(companyfacts=None, submissions=None):
    return run_fixture_slice(
        companyfacts or _load("companyfacts_versions.json"),
        submissions or _load("submissions_versions.json"),
        load_registry(REGISTRY_PATH),
        as_of="2025-12-31T23:59:59Z",
        recorded_at="2026-08-01T12:00:00Z",
        computed_at="2026-08-01T12:05:00Z",
        knowledge_clock="source_event",
        vintage_policy="latest_known",
    )


def test_run_validates_against_governed_json_schema() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=Draft202012Validator.FORMAT_CHECKER)
    errors = sorted(validator.iter_errors(_run().to_dict()), key=lambda error: list(error.path))
    assert errors == [], "\n".join(
        f"{list(error.absolute_path)}: {error.message}" for error in errors
    )


def test_fixed_run_matches_golden_digest_run_id_coverage_and_findings() -> None:
    result = _run()
    canonical = result.canonical_json().encode("utf-8")
    expected = _load("expected_run_v1.json")
    assert len(canonical) == expected["canonical_bytes"]
    assert hashlib.sha256(canonical).hexdigest() == expected["canonical_sha256"]
    assert result.run_id == expected["run_id"]
    assert result.coverage.to_dict() == expected["coverage"]
    assert {item.detector_id: item.state.value for item in result.findings} == expected[
        "finding_states"
    ]


def test_complete_pipeline_is_byte_stable_under_source_array_reordering() -> None:
    companyfacts = _load("companyfacts_versions.json")
    submissions = _load("submissions_versions.json")
    shuffled_facts = deepcopy(companyfacts)
    for concepts in shuffled_facts["facts"].values():
        for concept in concepts.values():
            for entries in concept["units"].values():
                entries.reverse()
    shuffled_submissions = deepcopy(submissions)
    for values in shuffled_submissions["filings"]["recent"].values():
        if isinstance(values, list):
            values.reverse()
    assert _run(companyfacts, submissions).canonical_json() == _run(
        shuffled_facts, shuffled_submissions
    ).canonical_json()


def test_pipeline_has_no_network_dependency(monkeypatch) -> None:
    def blocked(*_args, **_kwargs):
        raise AssertionError("network access is forbidden in fixture kernel")

    monkeypatch.setattr(requests, "get", blocked)
    assert _run().coverage.findings_triggered == 5


def test_financial_and_formula_numbers_are_decimal_strings() -> None:
    result = _run().to_dict()
    values = [item["value"] for item in result["fact_occurrences"]]
    values += [item["value"] for item in result["observations"]]
    values += [input_["value"] for finding in result["findings"] for input_ in finding["inputs"]]
    values += [value for finding in result["findings"] for value in finding["thresholds"].values()]
    values += [value for finding in result["findings"] for value in finding["derived_values"].values()]
    assert values
    assert all(isinstance(value, str) and DECIMAL_RE.fullmatch(value) for value in values)


def test_output_contains_no_score_rank_peer_llm_or_intent_claim() -> None:
    payload = _run().to_dict()

    def keys(value):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key.lower()
                yield from keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from keys(child)

    forbidden_keys = {"score", "rank", "peer", "llm", "fraud", "intent"}
    assert forbidden_keys.isdisjoint(set(keys(payload)))
    lower = json.dumps(payload, sort_keys=True).lower()
    assert all(term not in lower for term in ("fraud", "llm", "peer rank", "management intent"))


def test_kernel_sources_do_not_use_an_implicit_current_clock() -> None:
    source_dir = ROOT / "engine" / "fundamental_forensics"
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_dir.glob("*.py"))
    assert "datetime.now(" not in source
    assert "datetime.utcnow(" not in source
