from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
import inspect
from pathlib import Path
from time import perf_counter_ns

import pytest

from lib.evidence_foundation import (
    ALL_FALSE_AUTHORITY,
    EvidenceFoundationError,
    combined_block_violations,
    combined_recipe_violations,
    combined_violations,
    compile_recipe,
    compute_block_id,
    compute_recipe_id,
    compute_reference_id,
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


def _retarget_single_reference(block: dict, reference: dict) -> dict:
    """Point a one-reference fixture block at a rehashed same-owner reference."""
    assert len(block["reference_ids"]) == 1
    old_reference_id = block["reference_ids"][0]
    new_reference_id = reference["reference_id"]
    retargeted = json.loads(
        json.dumps(block).replace(old_reference_id, new_reference_id)
    )
    retargeted["clock_summary"]["entries"] = [
        {"reference_id": new_reference_id, **clock}
        for clock in reference["clocks"]
    ]
    retargeted["evidence_block_id"] = compute_block_id(retargeted)
    return retargeted


def _single_required_recipe(
    block: dict,
    *,
    subject_type: str,
    subject_key: str,
    output_field: str,
) -> dict:
    recipe = deepcopy(_json("aapl_security_state_recipe_valid.json"))
    recipe["recipe_name"] = f"test.{block['block_key']}"
    recipe["subject_instance"] = {
        "key_type": subject_type,
        "key": subject_key,
    }
    recipe["subject_key_types"] = [subject_type]
    recipe["identity_joins"] = []
    recipe["block_specs"] = [
        {
            "order": 1,
            "block_key": block["block_key"],
            "requirement": "required",
            "allowed_owner_stores": block["owner_stores"],
            "allowed_object_classes": block["object_classes"],
            "evidence_class": block["evidence_class"],
            "minimum_references": len(block["reference_ids"]),
            "maximum_references": len(block["reference_ids"]),
            "on_absent": "refuse",
            "output_fields": [output_field],
        }
    ]
    recipe["output_mappings"] = [
        {
            "output_field": output_field,
            "block_key": block["block_key"],
            "when_unavailable": "refuse",
        }
    ]
    recipe["recipe_id"] = compute_recipe_id(recipe)
    return recipe


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
    assert len(manifest["fixtures"]) == 17
    assert len({entry["file"] for entry in manifest["fixtures"]}) == 17
    for entry in manifest["fixtures"]:
        payload = (FIXTURE_DIR / entry["file"]).read_bytes()
        assert payload.endswith(b"\n")
        assert len(payload) == entry["size_bytes"]
        assert sha256(payload).hexdigest() == entry["sha256"]


def test_reference_contract_materializes_rights_freshness_and_authority_class() -> None:
    allowed = {
        "world_observation": {"fact"},
        "derived_view": {"deterministic", "model", "human"},
        "system_belief": {"deterministic", "model"},
        "forward_claim": {"model", "human"},
        "instrument_state": {"deterministic"},
    }
    for reference in _references().values():
        assert validate_reference(reference) == reference
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
        validate_reference(hostile)


def test_all_product_fixtures_use_combined_validators() -> None:
    references = _references()
    for entry in _json("product_manifest.json")["fixtures"]:
        payload = _json(entry["file"])
        if entry["kind"] == "reference":
            assert validate_reference(payload) == payload
            continue
        if entry["kind"] == "block":
            violations = combined_block_violations(payload, references=references)
            assert set(entry["expected_violations"]) <= set(violations)
            if entry["expected"] == "valid":
                assert validate_block(payload, references=references) == payload
            else:
                with pytest.raises(EvidenceFoundationError):
                    validate_block(payload, references=references)
            continue
        if entry["kind"] == "recipe":
            violations = combined_recipe_violations(payload)
            assert set(entry["expected_violations"]) <= set(violations)
            if entry["expected"] == "valid":
                assert validate_recipe(payload) == payload
            else:
                with pytest.raises(EvidenceFoundationError):
                    validate_recipe(payload)
            continue
        assert entry["kind"] == "receipt"
        assert payload["schema"] == "evidence_foundation.recipe_compilation_receipt.v1"


def test_product_validation_surface_cannot_rebind_the_canonical_vocabulary() -> None:
    public_functions = (
        combined_block_violations,
        validate_block,
        combined_recipe_violations,
        validate_recipe,
        compile_recipe,
    )
    for function in public_functions:
        assert "vocabulary" not in inspect.signature(function).parameters

    with pytest.raises(TypeError):
        validate_block(
            _json("aapl_theme_context_block_valid.json"),
            references=_references(),
            vocabulary={"schema": "attacker.schema"},  # type: ignore[call-arg]
        )


def test_golden_aapl_security_state_recipe_refuses_unverified_cross_type_joins() -> None:
    references = _references()
    recipe = _json("aapl_security_state_recipe_valid.json")
    blocks = _golden_blocks()
    receipt = compile_recipe(recipe, blocks=blocks, references=references)
    assert receipt == _json("aapl_security_state_compilation_expected.json")
    assert receipt["state"] == "refused"
    assert receipt["dominant_degradation"] == "identity_unresolved"
    assert receipt["block_ids"] == []
    assert receipt["missing_required_blocks"] == []
    assert receipt["missing_optional_blocks"] == []
    assert receipt["identity_unresolved_blocks"] == [
        "earnings_change",
        "fundamental_context",
        "theme_context",
        "forward_context",
    ]
    assert receipt["denominator"] == {
        "total": 4,
        "included": 0,
        "excluded": 4,
        "missing": 0,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
        "identity_unresolved": 4,
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
        "theme_graph.edge_belief",
        "qledger.claim",
    }


def test_golden_native_output_fixtures_project_actual_owner_rows(monkeypatch) -> None:
    from engine import qledger
    from engine.fundamental_forensics.financial_intelligence_packet import (
        validate_packet_semantics,
    )
    from engine.theme_graph.materialize import edge_id_for
    from engine.theme_graph.store import EDGE_COLUMNS, EDGE_KEY

    packet = json.loads(
        (
            ROOT
            / "tests/fixtures/fundamental_forensics/expected_financial_intelligence_packet_v1.json"
        ).read_text(encoding="utf-8")
    )
    validate_packet_semantics(packet)
    fif_ref = _json("fif_packet_valid.json")
    assert fif_ref["native_identity"] == {"packet_id": packet["packet_id"]}
    assert fif_ref["native_digest"] == {
        "state": "known",
        "sha256": packet["content_sha256"],
    }
    assert fif_ref["subject"] == {
        "key_type": "fif_packet_id",
        "key": packet["packet_id"],
    }
    fif_clocks = {row["field"]: row["value"] for row in fif_ref["clocks"]}
    assert fif_clocks == {
        "query.source_event_cutoff": packet["query"]["source_event_cutoff"],
        "query.system_recorded_cutoff": packet["query"]["system_recorded_cutoff"],
        "governance.governance_recorded_at": packet["governance"][
            "governance_recorded_at"
        ],
        "built_at": packet.get("built_at"),
    }

    monkeypatch.setattr(qledger, "_now_iso", lambda: "2026-08-23T12:00:00Z")
    monkeypatch.setattr(
        qledger,
        "_regime_stamp_for_asof",
        lambda asof: {"vector_asof": asof},
    )
    claim = qledger.make_claim(
        desk="market_os",
        asof="2026-08-23",
        scope_type="entity",
        scope_key="AAPL",
        direction=1,
        horizon_d=21,
        timestamp_quality="DISCLOSURE_DATE",
        subject_level=227.76,
        bench="SPY",
        bench_level=645.30,
        falsifier="fixture falsifier",
        check_by="2026-09-30",
    )
    stored_claim = qledger._prepare_claim(claim)
    assert stored_claim["status"] == qledger.STATUS_OPEN
    qledger_ref = _json("qledger_claim_valid.json")
    assert qledger_ref["native_identity"] == {
        "claim_id": stored_claim["claim_id"]
    }
    assert qledger_ref["subject"] == {
        "key_type": "claim_id",
        "key": stored_claim["claim_id"],
    }
    qledger_clocks = {row["field"]: row["value"] for row in qledger_ref["clocks"]}
    assert qledger_clocks == {
        field: stored_claim[field]
        for field in ("asof", "vector_asof", "timestamp", "check_by")
    }

    edge_ref = _json("theme_graph_evidence_valid.json")
    edge_id = edge_id_for(
        "MEMBER_OF",
        "co:us:AAPL",
        "basket:baskets:ai-infrastructure",
        "2026-07-30",
    )
    owner_row = {field: None for field in EDGE_COLUMNS}
    owner_row.update(
        edge_id=edge_id,
        type="MEMBER_OF",
        src="co:us:AAPL",
        dst="basket:baskets:ai-infrastructure",
        valid_from="2026-07-30",
        evidence_time="2026-07-30",
        belief_time="2026-07-31",
        computed_at="2026-07-31T00:15:00Z",
    )
    assert tuple(owner_row[field] for field in EDGE_KEY) == (
        edge_ref["native_identity"]["edge_id"],
        edge_ref["native_identity"]["belief_time"],
    )
    assert edge_ref["subject"] == {
        "key_type": "theme_node",
        "key": owner_row["src"],
    }
    edge_clocks = {row["field"]: row["value"] for row in edge_ref["clocks"]}
    assert edge_clocks == {
        field: owner_row[field]
        for field in ("valid_from", "valid_to", "evidence_time", "belief_time", "computed_at")
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
    assert _json("aapl_security_state_compilation_expected.json")["state"] == "refused"


def test_golden_absence_receipts_remain_explicit_beside_identity_refusal() -> None:
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
        "included": 0,
        "excluded": 4,
        "missing": 1,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
        "identity_unresolved": 3,
    }

    optional_absent = compile_recipe(
        recipe,
        blocks=[block for block in blocks if block["block_key"] != "forward_context"],
        references=references,
    )
    assert optional_absent["state"] == "refused"
    assert optional_absent["dominant_degradation"] == "identity_unresolved"
    assert optional_absent["missing_optional_blocks"] == ["forward_context"]
    assert optional_absent["identity_unresolved_blocks"] == [
        "earnings_change",
        "fundamental_context",
        "theme_context",
    ]
    assert optional_absent["denominator"] == {
        "total": 4,
        "included": 0,
        "excluded": 4,
        "missing": 1,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
        "identity_unresolved": 3,
    }


def test_bound_optional_absence_is_an_explicit_partial_receipt() -> None:
    block = _json("aapl_theme_context_block_valid.json")
    recipe = deepcopy(_json("aapl_security_state_recipe_valid.json"))
    recipe["recipe_name"] = "test.bound_optional_absence"
    recipe["subject_instance"] = {
        "key_type": "theme_node",
        "key": "co:us:AAPL",
    }
    recipe["subject_key_types"] = ["theme_node"]
    recipe["identity_joins"] = []
    recipe["block_specs"] = [
        {
            "order": 1,
            "block_key": "theme_context",
            "requirement": "required",
            "allowed_owner_stores": ["theme_graph.edge_belief"],
            "allowed_object_classes": ["system_belief"],
            "evidence_class": "deterministic",
            "minimum_references": 1,
            "maximum_references": 1,
            "on_absent": "refuse",
            "output_fields": ["opportunity.theme_context"],
        },
        {
            "order": 2,
            "block_key": "second_theme_context",
            "requirement": "optional",
            "allowed_owner_stores": ["theme_graph.edge_belief"],
            "allowed_object_classes": ["system_belief"],
            "evidence_class": "deterministic",
            "minimum_references": 1,
            "maximum_references": 1,
            "on_absent": "degrade",
            "output_fields": ["opportunity.second_theme_context"],
        },
    ]
    recipe["output_mappings"] = [
        {
            "output_field": "opportunity.theme_context",
            "block_key": "theme_context",
            "when_unavailable": "refuse",
        },
        {
            "output_field": "opportunity.second_theme_context",
            "block_key": "second_theme_context",
            "when_unavailable": "explicit_unavailable",
        },
    ]
    recipe["recipe_id"] = compute_recipe_id(recipe)
    receipt = compile_recipe(recipe, blocks=[block], references=_references())
    assert receipt["state"] == "partial"
    assert receipt["dominant_degradation"] == "unknown"
    assert receipt["block_ids"] == [block["evidence_block_id"]]
    assert receipt["missing_optional_blocks"] == ["second_theme_context"]
    assert receipt["identity_unresolved_blocks"] == []
    assert receipt["denominator"] == {
        "total": 2,
        "included": 1,
        "excluded": 1,
        "missing": 1,
        "stale": 0,
        "rights_blocked": 0,
        "fallback": 0,
        "identity_unresolved": 0,
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


def test_recipe_output_mappings_are_an_exact_executable_contract() -> None:
    base = _json("aapl_security_state_recipe_valid.json")
    undeclared = deepcopy(base)
    undeclared["output_mappings"].append(
        {
            "output_field": "state.invented",
            "block_key": "fundamental_context",
            "when_unavailable": "explicit_unavailable",
        }
    )
    undeclared["recipe_id"] = compute_recipe_id(undeclared)
    assert (
        "recipe_output_fields_not_exact:fundamental_context"
        in combined_recipe_violations(undeclared)
    )
    with pytest.raises(EvidenceFoundationError):
        validate_recipe(undeclared)

    omitted = deepcopy(base)
    omitted["output_mappings"] = omitted["output_mappings"][:-1]
    omitted["recipe_id"] = compute_recipe_id(omitted)
    assert (
        "recipe_output_fields_not_exact:forward_context"
        in combined_recipe_violations(omitted)
    )

    absence = deepcopy(base)
    absence["output_mappings"][0]["when_unavailable"] = "explicit_unavailable"
    absence["recipe_id"] = compute_recipe_id(absence)
    assert "recipe_output_absence_behavior_mismatch:0" in combined_recipe_violations(
        absence
    )


def test_recipe_rule_codes_and_effects_are_frozen_exactly() -> None:
    base = _json("aapl_security_state_recipe_valid.json")
    extra = deepcopy(base)
    extra["refusal_degradation_rules"].append(
        {"code": "INVENTED_RULE", "condition": "attacker condition", "effect": "degrade"}
    )
    extra["recipe_id"] = compute_recipe_id(extra)
    assert "recipe_rule_codes_not_exact" in combined_recipe_violations(extra)

    changed = deepcopy(base)
    rights_rule = next(
        rule
        for rule in changed["refusal_degradation_rules"]
        if rule["code"] == "RIGHTS_BLOCKED"
    )
    rights_rule["effect"] = "degrade"
    changed["recipe_id"] = compute_recipe_id(changed)
    assert "recipe_rule_effect_mismatch:RIGHTS_BLOCKED" in combined_recipe_violations(
        changed
    )
    with pytest.raises(EvidenceFoundationError):
        validate_recipe(changed)


def test_present_required_rights_blocked_block_refuses() -> None:
    block = _json("rights_blocked_block_valid.json")
    recipe = _single_required_recipe(
        block,
        subject_type="fif_packet_id",
        subject_key="fip_666666666666666666666666",
        output_field="state.financial_context",
    )
    receipt = compile_recipe(recipe, blocks=[block], references=_references())
    assert receipt["state"] == "refused"
    assert receipt["dominant_degradation"] == "rights_blocked"


def test_present_required_conflicted_block_follows_declared_abstention() -> None:
    block = _json("conflicting_observations_block_valid.json")
    recipe = _single_required_recipe(
        block,
        subject_type="theme_node",
        subject_key="co:us:AAPL",
        output_field="opportunity.theme_context",
    )
    receipt = compile_recipe(recipe, blocks=[block], references=_references())
    assert receipt["state"] == "abstained"
    assert receipt["dominant_degradation"] == "conflicted"


@pytest.mark.parametrize(
    ("fixture_name", "block_name", "hostile_subject_key", "output_field"),
    [
        (
            "qledger_claim_valid.json",
            "aapl_forward_context_block_valid.json",
            "b" * 16,
            "opportunity.forward_context",
        ),
        (
            "fif_packet_valid.json",
            "aapl_fundamental_context_block_valid.json",
            "fip_" + "b" * 24,
            "state.financial_context",
        ),
        (
            "theme_graph_evidence_valid.json",
            "aapl_theme_context_block_valid.json",
            "co:us:MSFT",
            "opportunity.theme_context",
        ),
    ],
)
def test_same_native_object_valid_different_subject_fails_ref_block_and_recipe(
    fixture_name: str,
    block_name: str,
    hostile_subject_key: str,
    output_field: str,
) -> None:
    references = _references()
    original = _json(fixture_name)
    hostile = deepcopy(original)
    hostile["subject"]["key"] = hostile_subject_key
    hostile["reference_id"] = compute_reference_id(hostile)
    subject_type = hostile["subject"]["key_type"]
    mismatch = f"subject_0_subject_native_identity_mismatch:{subject_type}"
    with pytest.raises(EvidenceFoundationError, match=mismatch):
        validate_reference(hostile)

    references.pop(original["reference_id"])
    references[hostile["reference_id"]] = hostile
    block = _retarget_single_reference(_json(block_name), hostile)
    assert f"block_reference_invalid:{hostile['reference_id']}" in combined_block_violations(
        block, references=references
    )
    with pytest.raises(EvidenceFoundationError, match="block_reference_invalid"):
        validate_block(block, references=references)

    coherent_recipe = _single_required_recipe(
        block,
        subject_type=subject_type,
        subject_key=hostile_subject_key,
        output_field=output_field,
    )
    assert validate_recipe(coherent_recipe) == coherent_recipe
    with pytest.raises(EvidenceFoundationError, match="block_reference_invalid"):
        compile_recipe(
            coherent_recipe,
            blocks=[block],
            references=references,
        )


@pytest.mark.parametrize(
    ("fixture_name", "hostile_subject"),
    [
        (
            "qledger_claim_valid.json",
            {"key_type": "security_id", "key": "SEC:US-XNAS-MSFT"},
        ),
        (
            "fif_packet_valid.json",
            {"key_type": "issuer_id", "key": "ISS:US-XNAS-MSFT"},
        ),
    ],
)
def test_owner_native_ids_cannot_be_retyped_as_unverified_dataos_subjects(
    fixture_name: str,
    hostile_subject: dict[str, str],
) -> None:
    hostile = _json(fixture_name)
    hostile["subject"] = hostile_subject
    hostile["reference_id"] = compute_reference_id(hostile)
    assert "subject_0_not_owned" in combined_violations(hostile)
    with pytest.raises(EvidenceFoundationError, match="subject_0_not_owned"):
        validate_reference(hostile)


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
    assert "block_dependence_groups_not_derived" in combined_block_violations(
        hostile, references=_references()
    )


def test_rehashed_shared_upstream_block_cannot_claim_independence() -> None:
    hostile = deepcopy(_json("shared_upstream_block_valid.json"))
    hostile["dependence"] = {
        "state": "independent",
        "independent_evidence_count": 2,
        "groups": [],
    }
    hostile["evidence_block_id"] = compute_block_id(hostile)
    violations = set(combined_block_violations(hostile, references=_references()))
    assert {
        "block_dependence_state_not_derived",
        "block_independent_count_not_derived",
        "block_dependence_groups_not_derived",
    } <= violations
    with pytest.raises(EvidenceFoundationError):
        validate_block(hostile, references=_references())


def test_rehashed_block_dependence_key_cannot_be_invented() -> None:
    hostile = deepcopy(_json("shared_upstream_block_valid.json"))
    hostile["dependence"]["groups"][0]["deterministic_key"] = "x"
    hostile["evidence_block_id"] = compute_block_id(hostile)
    violations = combined_block_violations(hostile, references=_references())
    assert "block_dependence_key_not_source_derived:0" in violations
    assert "block_dependence_groups_not_derived" in violations


def test_rehashed_conflict_block_cannot_launder_conflicting_references() -> None:
    hostile = deepcopy(_json("conflicting_observations_block_valid.json"))
    hostile["coverage"]["state"] = "complete"
    hostile["supported_claim"]["state"] = "supported"
    hostile["conflict_correction"] = {"state": "none", "reference_ids": []}
    hostile["evidence_block_id"] = compute_block_id(hostile)
    violations = set(combined_block_violations(hostile, references=_references()))
    assert {
        "block_coverage_state_not_derived",
        "block_supported_claim_coverage_mismatch",
        "block_conflict_state_not_derived",
        "block_conflict_references_not_derived",
    } <= violations
    with pytest.raises(EvidenceFoundationError):
        validate_block(hostile, references=_references())


def test_rehashed_typed_missingness_block_cannot_launder_absence_to_support() -> None:
    missing = _json("typed_missingness_valid.json")
    hostile = _retarget_single_reference(
        _json("aapl_forward_context_block_valid.json"), missing
    )
    assert validate_reference(missing) == missing
    violations = set(combined_block_violations(hostile, references=_references()))
    assert {
        "block_denominator_included_mismatch",
        "block_denominator_excluded_mismatch",
        "block_denominator_missing_mismatch",
        "block_coverage_state_not_derived",
        "block_supported_claim_coverage_mismatch",
    } <= violations
    with pytest.raises(EvidenceFoundationError):
        validate_block(hostile, references=_references())


def test_rehashed_corrected_block_cannot_launder_correction_or_lineage() -> None:
    hostile = deepcopy(_json("corrected_context_block_valid.json"))
    hostile["coverage"]["state"] = "complete"
    hostile["supported_claim"]["state"] = "supported"
    hostile["conflict_correction"] = {"state": "none", "reference_ids": []}
    hostile["lineage"] = {
        "state": "original",
        "predecessor_block_ids": [],
        "invalidated_by_reference_ids": [],
    }
    hostile["evidence_block_id"] = compute_block_id(hostile)
    violations = set(combined_block_violations(hostile, references=_references()))
    assert {
        "block_coverage_state_not_derived",
        "block_supported_claim_coverage_mismatch",
        "block_conflict_state_not_derived",
        "block_conflict_references_not_derived",
        "block_correction_missing_recompile_receipt",
    } <= violations
    with pytest.raises(EvidenceFoundationError):
        validate_block(hostile, references=_references())


def test_reference_map_key_must_equal_the_cited_reference_identity() -> None:
    block = _json("aapl_theme_context_block_valid.json")
    cited_id = block["reference_ids"][0]
    references = _references()
    references[cited_id] = _json("qledger_claim_valid.json")
    violations = combined_block_violations(block, references=references)
    assert f"block_reference_key_mismatch:{cited_id}" in violations
    with pytest.raises(EvidenceFoundationError, match="block_reference_key_mismatch"):
        validate_block(block, references=references)


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
