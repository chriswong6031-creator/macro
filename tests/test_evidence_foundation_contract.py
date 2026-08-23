from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import importlib
import json
from pathlib import Path
import subprocess

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    compute_reference_id,
    load_vocabulary,
    semantic_violations,
)


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_DIR = ROOT / "contracts" / "evidence_foundation"
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence_foundation"
SCHEMA_PATH = CONTRACT_DIR / "reference.v1.schema.json"
VOCABULARY_PATH = CONTRACT_DIR / "vocabulary.v1.json"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def schema() -> dict:
    return _json(SCHEMA_PATH)


@pytest.fixture(scope="module")
def validator(schema: dict) -> Draft202012Validator:
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.fixture(scope="module")
def vocabulary() -> dict:
    return load_vocabulary(VOCABULARY_PATH)


def test_contract_and_vocabulary_are_frozen_v1(schema: dict, vocabulary: dict) -> None:
    assert schema["properties"]["schema"]["const"] == "evidence_foundation.reference.v1"
    assert schema["properties"]["version"]["const"] == "1.0.0"
    assert vocabulary["schema"] == "evidence_foundation.vocabulary.v1"
    assert vocabulary["version"] == "1.0.0"
    assert len(vocabulary["owner_stores"]) == 17
    assert "institutional_13f.raw_receipt" in vocabulary["owner_stores"]
    assert "ticker_store_key" not in vocabulary["subject_key_types"]
    assert "ticker_store_key" in vocabulary["excluded_identity_types"]
    assert "qledger.evidence_clock_start" in vocabulary["excluded_derived_heads"]


def test_owner_identity_clock_and_synapse_bindings_are_exact(vocabulary: dict) -> None:
    owners = vocabulary["owner_stores"]
    assert all("synapse_asof_field" in owner for owner in owners.values())
    assert owners["fif.raw_occurrence"]["clock_bindings"] == {
        "clocks.accepted_at": "source_published",
        "clocks.recorded_at": "system_recorded",
    }
    assert owners["govrev.event.v2"]["clock_bindings"] == {
        "change.effective_at": "world_valid",
        "change.known_at": "knowable",
        "change.first_seen_at": "observed",
    }
    assert owners["biocatalyst.ctgov_current"]["native_identity_fields"] == [
        "source_snapshot_id"
    ]
    assert owners["biocatalyst.ctgov_history"]["native_identity_fields"] == [
        "source_snapshot_id"
    ]
    assert owners["qledger.claim"]["synapse_asof_field"] == "asof"
    assert owners["qledger.claim"]["clock_bindings"]["check_by"] == "review_due"
    assert owners["market_memory.outcome_record"]["native_identity_fields"] == [
        "outcome_record_id"
    ]
    assert owners["market_memory.outcome_record"]["object_classes"] == [
        "world_observation"
    ]


def test_vocabulary_refuses_an_unspecified_or_unbound_synapse_asof(
    vocabulary: dict, tmp_path: Path
) -> None:
    missing = deepcopy(vocabulary)
    del missing["owner_stores"]["qledger.claim"]["synapse_asof_field"]
    missing_path = tmp_path / "missing.json"
    missing_path.write_text(json.dumps(missing), encoding="utf-8")
    with pytest.raises(ValueError, match="vocabulary_synapse_asof_unspecified"):
        load_vocabulary(missing_path)

    unbound = deepcopy(vocabulary)
    unbound["owner_stores"]["qledger.claim"]["synapse_asof_field"] = "invented_at"
    unbound_path = tmp_path / "unbound.json"
    unbound_path.write_text(json.dumps(unbound), encoding="utf-8")
    with pytest.raises(ValueError, match="vocabulary_synapse_asof_unbound"):
        load_vocabulary(unbound_path)


def test_fixture_manifest_is_complete_and_byte_receipted() -> None:
    manifest = _json(MANIFEST_PATH)
    assert manifest["schema"] == "evidence_foundation.fixture_manifest.v1"
    assert len(manifest["fixtures"]) == 8
    assert len({row["file"] for row in manifest["fixtures"]}) == 8
    for row in manifest["fixtures"]:
        payload = (FIXTURE_DIR / row["file"]).read_bytes()
        assert payload.endswith(b"\n")
        assert len(payload) == row["size_bytes"]
        assert sha256(payload).hexdigest() == row["sha256"]


def _resolve_reader(path: str) -> object:
    parts = path.split(".")
    for split in range(len(parts), 0, -1):
        module_name = ".".join(parts[:split])
        try:
            value: object = importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name and not module_name.startswith(f"{exc.name}."):
                raise
            continue
        for attribute in parts[split:]:
            value = getattr(value, attribute)
        return value
    raise AssertionError(f"reader module is not importable: {path}")


def test_every_owner_reader_resolves_on_current_base(vocabulary: dict) -> None:
    for name, owner in vocabulary["owner_stores"].items():
        assert _resolve_reader(owner["reader"]) is not None, name


EXPECTED_SEMANTIC_VIOLATIONS = {
    "duplicate_corroboration_hostile.json": {
        "relation_0_automatic_forbidden",
        "relation_0_non_deterministic_effect",
    },
    "replay_lookahead_hostile.json": {
        "replay_lookahead:clocks.accepted_at",
        "replay_lookahead:clocks.recorded_at",
    },
    "authority_leak_hostile.json": {"authority_leak"},
}


def test_all_golden_fixtures_reach_their_declared_verdict(
    validator: Draft202012Validator,
    vocabulary: dict,
) -> None:
    manifest = _json(MANIFEST_PATH)
    for row in manifest["fixtures"]:
        payload = _json(FIXTURE_DIR / row["file"])
        schema_errors = tuple(validator.iter_errors(payload))
        semantic_errors = set(semantic_violations(payload, vocabulary=vocabulary))
        assert payload["reference_id"] == compute_reference_id(payload), row["file"]
        if row["expected"] == "valid":
            assert not schema_errors, (row["file"], [error.message for error in schema_errors])
            assert not semantic_errors, (row["file"], sorted(semantic_errors))
        else:
            assert schema_errors or semantic_errors, row["file"]
            assert EXPECTED_SEMANTIC_VIOLATIONS[row["file"]] <= semantic_errors


def test_fif_fixture_is_pointer_only_and_owner_native(validator: Draft202012Validator) -> None:
    payload = _json(FIXTURE_DIR / "fif_packet_valid.json")
    validator.validate(payload)
    assert payload["owner_store"] == "fif.packet"
    assert payload["native_schema"] == "financial_intelligence_packet.v1"
    assert payload["native_identity"] == {"packet_id": "fip_0123456789abcdef01234567"}
    assert payload["provenance"]["pointer_only"] is True
    assert payload["provenance"]["body_embedded"] is False
    assert "body" not in payload and "payload" not in payload


def test_earnings_fixture_preserves_canonical_event_and_generation_identity(
    validator: Draft202012Validator,
) -> None:
    payload = _json(FIXTURE_DIR / "earnings_workspace_valid.json")
    validator.validate(payload)
    assert payload["native_identity"]["event_id"] == "evt_cik0000320193_2026q3_results"
    assert payload["native_identity"]["generation_id"] == "0123456789abcdef01234567"
    assert payload["subject"] == {"key_type": "cik", "key": "0000320193"}


def test_correction_is_append_supersede_and_preserves_predecessor(
    validator: Draft202012Validator,
    vocabulary: dict,
) -> None:
    payload = _json(FIXTURE_DIR / "correction_append_valid.json")
    validator.validate(payload)
    assert semantic_violations(payload, vocabulary=vocabulary) == ()
    correction = payload["correction"]
    assert correction["kind"] == "superseding_generation"
    assert correction["append_only"] is True
    assert correction["mutates_predecessor"] is False
    assert correction["predecessor_reference_ids"]
    assert payload["relations"][0]["automatic_effect"] is False


def test_replay_refuses_lookahead_and_distinguishes_recomputation(vocabulary: dict) -> None:
    valid = _json(FIXTURE_DIR / "replay_valid.json")
    hostile = _json(FIXTURE_DIR / "replay_lookahead_hostile.json")
    assert semantic_violations(valid, vocabulary=vocabulary) == ()
    violations = set(semantic_violations(hostile, vocabulary=vocabulary))
    assert "replay_lookahead:clocks.accepted_at" in violations
    assert "replay_lookahead:clocks.recorded_at" in violations

    mislabeled = deepcopy(valid)
    mislabeled["replay"]["vintage_state"] = "current_rule_recomputation"
    mislabeled["reference_id"] = compute_reference_id(mislabeled)
    assert "recomputation_mislabeled_replay" in semantic_violations(
        mislabeled, vocabulary=vocabulary
    )


def test_typed_missingness_never_substitutes_zero(
    validator: Draft202012Validator,
    vocabulary: dict,
) -> None:
    payload = _json(FIXTURE_DIR / "typed_missingness_valid.json")
    validator.validate(payload)
    assert semantic_violations(payload, vocabulary=vocabulary) == ()
    assert payload["missingness"] == {
        "state": "absent",
        "reason": "unsupported",
        "zero_substituted": False,
    }

    hostile = deepcopy(payload)
    hostile["missingness"]["zero_substituted"] = True
    hostile["reference_id"] = compute_reference_id(hostile)
    assert tuple(validator.iter_errors(hostile))
    assert "missingness_zero_substitution" in semantic_violations(
        hostile, vocabulary=vocabulary
    )


def test_authority_is_materialized_and_all_false(
    validator: Draft202012Validator,
    vocabulary: dict,
) -> None:
    valid = _json(FIXTURE_DIR / "fif_packet_valid.json")
    assert valid["authority"] == ALL_FALSE_AUTHORITY
    validator.validate(valid)

    leak = _json(FIXTURE_DIR / "authority_leak_hostile.json")
    assert tuple(validator.iter_errors(leak))
    assert "authority_leak" in semantic_violations(leak, vocabulary=vocabulary)

    absent = deepcopy(valid)
    del absent["authority"]
    absent["reference_id"] = compute_reference_id(absent)
    assert tuple(validator.iter_errors(absent))
    assert "authority_not_materialized" in semantic_violations(
        absent, vocabulary=vocabulary
    )


def test_pointer_contract_rejects_embedded_body(validator: Draft202012Validator) -> None:
    payload = _json(FIXTURE_DIR / "fif_packet_valid.json")
    payload["body"] = {"copied_owner_truth": True}
    payload["reference_id"] = compute_reference_id(payload)
    assert tuple(validator.iter_errors(payload))


def test_reference_id_is_deterministic_and_has_no_write_clock() -> None:
    payload = _json(FIXTURE_DIR / "fif_packet_valid.json")
    assert compute_reference_id(payload) == payload["reference_id"]
    replayed = json.loads(json.dumps(payload, sort_keys=False))
    assert compute_reference_id(replayed) == payload["reference_id"]
    assert "join_recorded_at" not in payload
    assert "join_as_of" not in payload


def test_k1_creates_no_physical_mesh_store() -> None:
    inventory = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    forbidden_prefixes = (
        "data/evidence_mesh/",
        "data/evidence_foundation/",
        "engine/evidence_mesh/",
    )
    assert not [
        path for path in inventory if any(path.startswith(prefix) for prefix in forbidden_prefixes)
    ]
