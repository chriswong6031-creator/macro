from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter_ns

import pytest

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    EvidenceFoundationError,
    combined_block_violations,
    combined_recipe_violations,
    compile_recipe,
    compute_block_id,
    compute_recipe_id,
    compute_reference_id,
    load_vocabulary,
    validate_block,
    validate_recipe,
    validate_reference,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = Path(__file__).parent / "fixtures" / "evidence_foundation"
PRODUCT_MANIFEST = FIXTURE_DIR / "product_manifest.json"
REFERENCE_MANIFEST = FIXTURE_DIR / "manifest.json"


def _json(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _references() -> dict[str, dict]:
    rows: list[dict] = []
    for entry in _json("manifest.json")["fixtures"]:
        if entry["expected"] == "valid":
            rows.append(_json(entry["file"]))
    for entry in _json("product_manifest.json")["fixtures"]:
        if entry["kind"] == "reference":
            rows.append(_json(entry["file"]))
    return {row["reference_id"]: row for row in rows}


def _golden_blocks() -> list[dict]:
    return [
        _json("aapl_earnings_change_block_valid.json"),
        _json("aapl_fundamental_context_block_valid.json"),
        _json("aapl_theme_context_block_valid.json"),
        _json("aapl_forward_context_block_valid.json"),
    ]


def test_product_contract_schemas_are_closed_and_pointer_only() -> None:
    block = json.loads(
        (ROOT / "contracts/evidence_foundation/block.v1.schema.json").read_text()
    )
    recipe = json.loads(
        (ROOT / "contracts/evidence_foundation/recipe.v1.schema.json").read_text()
    )
    assert block["additionalProperties"] is False
    assert recipe["additionalProperties"] is False
    assert block["properties"]["schema"]["const"] == "evidence_foundation.block.v1"
    assert recipe["properties"]["schema"]["const"] == "evidence_foundation.recipe.v1"
    assert "owner_payload" not in block["properties"]
    assert "owner_payloads" not in block["properties"]
    assert "owner_payload" not in recipe["properties"]
    assert recipe["$defs"]["integrity"]["properties"]["owner_payload_copy_allowed"] == {
        "const": False
    }


def test_product_fixture_manifest_is_complete_and_byte_receipted() -> None:
    manifest = _json("product_manifest.json")
    assert manifest["schema"] == "evidence_foundation.product_fixture_manifest.v1"
    assert len(manifest["fixtures"]) == 16
    assert len({entry["file"] for entry in manifest["fixtures"]}) == 16
    for entry in manifest["fixtures"]:
        payload = (FIXTURE_DIR / entry["file"]).read_bytes()
        assert payload.endswith(b"\n")
        assert len(payload) == entry["size_bytes"]
        assert sha256(payload).hexdigest() == entry["sha256"]


def test_reference_contract_materializes_rights_freshness_and_authority_class() -> None:
    vocabulary = load_vocabulary()
    allowed = {
        "world_observation": {"fact"},
        "derived_view": {"deterministic", "model", "human"},
        "system_belief": {"deterministic", "model"},
        "forward_claim": {"model", "human"},
        "instrument_state": {"deterministic"},
    }
    for reference in _references().values():
        assert validate_reference(reference, vocabulary=vocabulary) == reference
        assert set(reference["freshness"]) == {"state", "clock_field", "policy_id"}
        assert set(reference["rights"]) == {"state", "policy_id"}
        assert reference["authority_class"] in allowed[reference["object_class"]]

    rights = _json("rights_blocked_reference_valid.json")
    assert rights["rights"]["state"] == "rights_blocked"
    assert rights["missingness"]["reason"] == "rights_blocked"
    hostile = deepcopy(rights)
    hostile["rights"]["state"] = "permitted"
    hostile["reference_id"] = compute_reference_id(hostile)
    with pytest.raises(EvidenceFoundationError, match="rights_missingness_mismatch"):
        validate_reference(hostile, vocabulary=vocabulary)


def test_all_product_fixtures_use_combined_validators() -> None:
    references = _references()
    vocabulary = load_vocabulary()
    for entry in _json("product_manifest.json")["fixtures"]:
        payload = _json(entry["file"])
        if entry["kind"] == "reference":
            assert validate_reference(payload, vocabulary=vocabulary) == payload
            continue
        if entry["kind"] == "block":
            violations = combined_block_violations(
                payload, references=references, vocabulary=vocabulary
            )
            assert set(entry["expected_violations"]) <= set(violations)
            if entry["expected"] == "valid":
                assert validate_block(
                    payload, references=references, vocabulary=vocabulary
                ) == payload
            else:
                with pytest.raises(EvidenceFoundationError):
                    validate_block(
                        payload, references=references, vocabulary=vocabulary
                    )
            continue
        if entry["kind"] == "recipe":
            violations = combined_recipe_violations(payload, vocabulary=vocabulary)
            assert set(entry["expected_violations"]) <= set(violations)
            if entry["expected"] == "valid":
                assert validate_recipe(payload, vocabulary=vocabulary) == payload
            else:
                with pytest.raises(EvidenceFoundationError):
                    validate_recipe(payload, vocabulary=vocabulary)
            continue
        assert entry["kind"] == "receipt"
        assert payload["schema"] == "evidence_foundation.recipe_compilation_receipt.v1"


def test_golden_aapl_security_state_recipe_compiles_from_four_owner_fixture_reads() -> None:
    references = _references()
    recipe = _json("aapl_security_state_recipe_valid.json")
    blocks = _golden_blocks()
    receipt = compile_recipe(recipe, blocks=blocks, references=references)
    assert receipt == _json("aapl_security_state_compilation_expected.json")
    assert receipt["state"] == "partial"
    assert receipt["dominant_degradation"] == "unknown"
    assert receipt["missing_required_blocks"] == []
    assert receipt["missing_optional_blocks"] == []
    assert receipt["denominator"] == {
        "total": 4,
        "included": 4,
        "excluded": 0,
        "missing": 0,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
    }
    assert receipt["owner_payloads_persisted"] is False
    assert receipt["authority"] == ALL_FALSE_AUTHORITY
    assert {
        reference["owner_store"]
        for reference in references.values()
        if reference["reference_id"]
        in {
            reference_id
            for block in blocks
            for reference_id in block["reference_ids"]
        }
    } == {
        "earnings.workspace_generation",
        "fif.packet",
        "theme_graph.evidence",
        "qledger.claim",
    }


def test_direct_fixture_reader_composition_baseline_is_measured_not_self_certified() -> None:
    recipe_name = "aapl_security_state_recipe_valid.json"
    block_names = [
        "aapl_earnings_change_block_valid.json",
        "aapl_fundamental_context_block_valid.json",
        "aapl_theme_context_block_valid.json",
        "aapl_forward_context_block_valid.json",
    ]
    samples: list[int] = []
    for _ in range(25):
        started = perf_counter_ns()
        references = _references()
        compile_recipe(
            _json(recipe_name),
            blocks=[_json(name) for name in block_names],
            references=references,
        )
        samples.append(perf_counter_ns() - started)
    assert len(samples) == 25
    assert min(samples) > 0
    # K1 records the measurement but imposes no invented pass/fail latency budget.
    assert _json("aapl_security_state_compilation_expected.json")["state"] == "partial"


def test_required_absence_refuses_and_optional_absence_is_explicit_partial() -> None:
    references = _references()
    recipe = _json("aapl_security_state_recipe_valid.json")
    blocks = _golden_blocks()
    required_absent = compile_recipe(
        recipe,
        blocks=[block for block in blocks if block["block_key"] != "earnings_change"],
        references=references,
    )
    assert required_absent["state"] == "refused"
    assert required_absent["dominant_degradation"] == "required_block_absent"
    assert required_absent["missing_required_blocks"] == ["earnings_change"]
    assert required_absent["denominator"] == {
        "total": 4,
        "included": 3,
        "excluded": 1,
        "missing": 1,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
    }

    optional_absent = compile_recipe(
        recipe,
        blocks=[block for block in blocks if block["block_key"] != "forward_context"],
        references=references,
    )
    assert optional_absent["state"] == "partial"
    assert optional_absent["dominant_degradation"] == "unknown"
    assert optional_absent["missing_optional_blocks"] == ["forward_context"]
    assert optional_absent["denominator"] == {
        "total": 4,
        "included": 3,
        "excluded": 1,
        "missing": 1,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
    }


def test_recipe_rejects_blocks_outside_its_frozen_composition() -> None:
    references = _references()
    with pytest.raises(EvidenceFoundationError, match="compile_block_not_in_recipe"):
        compile_recipe(
            _json("aapl_security_state_recipe_valid.json"),
            blocks=[*_golden_blocks(), _json("rights_blocked_block_valid.json")],
            references=references,
        )


def test_forbidden_cik_symbol_directory_join_is_killed() -> None:
    hostile = _json("forbidden_cik_join_recipe_hostile.json")
    assert hostile["recipe_id"] == compute_recipe_id(hostile)
    assert "recipe_identity_join_forbidden:0" in combined_recipe_violations(hostile)
    with pytest.raises(EvidenceFoundationError, match="recipe_identity_join_forbidden"):
        validate_recipe(hostile)


def test_forward_claim_cannot_masquerade_as_fact() -> None:
    hostile = _json("belief_as_fact_block_hostile.json")
    assert hostile["evidence_block_id"] == compute_block_id(hostile)
    violations = combined_block_violations(hostile, references=_references())
    assert "block_evidence_class_masquerade" in violations
    with pytest.raises(EvidenceFoundationError, match="block_evidence_class_masquerade"):
        validate_block(hostile, references=_references())


def test_shared_upstream_does_not_inflate_independent_evidence() -> None:
    block = _json("shared_upstream_block_valid.json")
    assert validate_block(block, references=_references()) == block
    assert block["coverage"]["included"] == 2
    assert block["dependence"]["independent_evidence_count"] == 1
    assert block["dependence"]["state"] == "shared_upstream"
    assert block["dependence"]["groups"][0]["deterministic_key"] is None
    hostile = deepcopy(block)
    hostile["dependence"]["groups"][0]["reference_ids"] = [
        hostile["reference_ids"][0]
    ]
    hostile["evidence_block_id"] = compute_block_id(hostile)
    assert "block_shared_upstream_relation_missing:0" in combined_block_violations(
        hostile, references=_references()
    )


def test_conflict_rights_and_correction_are_typed_dominant_states() -> None:
    references = _references()
    conflict = _json("conflicting_observations_block_valid.json")
    rights = _json("rights_blocked_block_valid.json")
    corrected = _json("corrected_context_block_valid.json")
    assert validate_block(conflict, references=references)["coverage"]["state"] == "conflicted"
    assert validate_block(rights, references=references)["coverage"]["state"] == "rights_blocked"
    assert rights["coverage"]["included"] == 0
    assert rights["coverage"]["excluded"] == rights["coverage"]["total"] == 1
    assert validate_block(corrected, references=references)["lineage"]["state"] == "recompiled"
    assert corrected["lineage"]["predecessor_block_ids"]
    assert corrected["lineage"]["invalidated_by_reference_ids"] == corrected["reference_ids"]


def test_corrected_reference_rebuilds_without_rewriting_predecessor_block() -> None:
    references = _references()
    corrected = _json("corrected_context_block_valid.json")
    predecessor_id = corrected["lineage"]["predecessor_block_ids"][0]
    frozen_before = json.dumps(corrected, sort_keys=True)
    rebuilt = deepcopy(corrected)
    rebuilt["lineage"]["predecessor_block_ids"] = [corrected["evidence_block_id"]]
    rebuilt["evidence_block_id"] = compute_block_id(rebuilt)
    assert rebuilt["evidence_block_id"] != corrected["evidence_block_id"]
    assert rebuilt["lineage"]["predecessor_block_ids"] == [corrected["evidence_block_id"]]
    assert corrected["lineage"]["predecessor_block_ids"] == [predecessor_id]
    assert json.dumps(corrected, sort_keys=True) == frozen_before
    assert validate_block(rebuilt, references=references) == rebuilt


def test_probability_cannot_appear_without_derivation_and_calibration_receipts() -> None:
    references = _references()
    hostile = deepcopy(_json("aapl_forward_context_block_valid.json"))
    hostile["uncertainty"]["probability"] = 0.7
    hostile["evidence_block_id"] = compute_block_id(hostile)
    assert "block_probability_without_calibration" in combined_block_violations(
        hostile, references=references
    )


def test_claim_state_and_next_observable_cannot_overstate_adverse_coverage() -> None:
    references = _references()
    hostile = deepcopy(_json("aapl_forward_context_block_valid.json"))
    hostile["supported_claim"]["state"] = "supported"
    hostile["next_observable"] = {
        "state": "unknown",
        "description": "Invented certainty about a next observable",
        "owner_clock_field": None,
    }
    hostile["evidence_block_id"] = compute_block_id(hostile)
    violations = combined_block_violations(hostile, references=references)
    assert "block_supported_claim_coverage_mismatch" in violations
    assert "block_next_observable_nonknown_has_value" in violations
