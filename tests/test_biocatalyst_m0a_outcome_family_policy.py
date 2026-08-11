"""Tests for the M0a outcome-family policy contract.

The policy is contract only.  These tests pin that it validates, that it
extends the seed policy without contradicting it, and above all that it opens
nothing: every family's clock is closed and every entry gate is unsatisfied.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from engine.biocatalyst.operational_store import RECORD_KINDS
from engine.sector_intelligence.contracts import ContractRegistry


ROOT = Path(__file__).resolve().parents[1]
FAMILY_POLICY = ROOT / "config" / "biocatalyst_outcome_family_policy.yml"
SEED_POLICY = ROOT / "config" / "biocatalyst_outcomes.yml"
OWNERSHIP = ROOT / "config" / "sector_intelligence_ownership.yml"
SOURCE_REGISTRY = ROOT / "config" / "biocatalyst_sources.yml"
FAMILY_POLICY_CONTRACT_ID = "biocatalyst_outcome_family_policy.v1"

EXPECTED_FAMILIES = (
    "trial_progression_termination",
    "endpoint_readout",
    "timing_slip",
    "enrollment_site_change",
    "regulatory_outcome",
    "financing_dilution_event",
    "partnership_event",
    "market_reaction",
    "forecast_calibration",
)


def _load_yaml(path: Path) -> dict:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


@pytest.fixture(scope="module")
def policy() -> dict:
    return _load_yaml(FAMILY_POLICY)


@pytest.fixture(scope="module")
def seed() -> dict:
    return _load_yaml(SEED_POLICY)


def test_family_policy_contract_is_registered() -> None:
    assert FAMILY_POLICY_CONTRACT_ID in ContractRegistry(ROOT).contract_ids


def test_family_policy_instance_validates_against_its_contract(policy: dict) -> None:
    ContractRegistry(ROOT).validate(FAMILY_POLICY_CONTRACT_ID, policy)


def test_exactly_the_nine_named_families_are_declared(policy: dict) -> None:
    assert tuple(sorted(policy["families"])) == tuple(sorted(EXPECTED_FAMILIES))


def test_every_family_clock_is_closed_and_no_entry_gate_is_satisfied(
    policy: dict,
) -> None:
    assert policy["state"] == "contract_only_no_clock_opened"
    for name, family in policy["families"].items():
        assert family["state"] == "clock_not_opened", name
        gate = family["entry_gate"]
        assert gate["satisfied"] is False, name
        assert gate["unsatisfied_preconditions"], name
        assert gate["blockers"], name
        # Every family still requires the O1b writer; m0a.3 retains that
        # discharge while distinguishing rights permission from activation.
        assert "o1b_outcome_writer" in gate["required_preconditions"], name
        assert "o1b_outcome_writer" not in gate["unsatisfied_preconditions"], name
        assert "o1b_outcome_writer_absent" not in gate["blockers"], name
        assert set(gate["unsatisfied_preconditions"]) <= set(
            gate["required_preconditions"]
        ), name


def test_the_o1b_outcome_writer_contract_now_exists(policy: dict) -> None:
    writer = policy["family_registration"]["writer_contract"]
    assert writer == "biocatalyst_outcome_record.v1"
    assert policy["family_registration"]["writer_contract_state"] == "built_in_bc_o1b"
    assert writer in ContractRegistry(ROOT).contract_ids
    for family in policy["families"].values():
        assert family["entry_gate"]["required_writer_contract"] == writer


def test_the_clock_state_of_record_is_the_receipt_and_never_this_file(
    policy: dict,
) -> None:
    activation = policy["clock_activation"]
    assert activation["clock_state_authority"] == "activation_receipt_not_this_file"
    assert activation["backfill"] == "forbidden_no_history_recorded"
    assert activation["model_may_open_a_clock"] is False
    assert activation["source_eligibility_rule"] == (
        "required_source_ids_must_be_rights_allowed_and_any_runtime_universe_controls_armed"
    )
    assert activation["activation_record_contract"] in ContractRegistry(ROOT).contract_ids
    assert activation["activation_record_kind"] in RECORD_KINDS


def test_registration_is_an_operator_act_and_never_a_model_act(policy: dict) -> None:
    registration = policy["family_registration"]
    assert registration["registration_authority"] == "operator_review"
    assert registration["model_may_register"] is False
    assert registration["unsatisfied_precondition_behavior"] == "clock_stays_closed"
    assert sorted(registration["required_preconditions"]) == [
        "eligible_identity_contract",
        "eligible_source_registration",
        "frozen_policy_version",
        "o1b_outcome_writer",
    ]


def test_policy_extends_the_seed_without_contradicting_it(
    policy: dict, seed: dict
) -> None:
    extends = policy["extends"]
    assert extends["seed_policy_schema"] == seed["schema"]
    assert extends["seed_policy_file"] == "config/biocatalyst_outcomes.yml"
    assert extends["executable_outcome_contract"] == (
        seed["resolution"]["executable_contract"]["contract_id"]
    )
    # Correction behavior is the seed's exact phrase, not a rewrite of it.
    assert policy["correction_grammar"]["behavior"] == (
        seed["resolution"]["correction_behavior"]
    )
    # The seed forbids model resolution; the extension may not loosen that.
    assert seed["resolution"]["model_may_resolve"] is False
    assert policy["correction_grammar"]["model_may_correct"] is False
    assert policy["outcome_envelope"]["model_may_originate_value"] is False
    # Seed policy booleans carried forward, never inverted.
    assert seed["policy"]["missing_is_not_negative"] is True
    assert seed["policy"]["unresolved_is_not_failure"] is True
    assert policy["censoring"]["missing_is_not_negative"] is True
    assert policy["censoring"]["unresolved_is_not_failure"] is True


def test_every_seed_mapped_family_names_a_real_seed_layer(
    policy: dict, seed: dict
) -> None:
    seed_layers = set(seed["layers"])
    for name, family in policy["families"].items():
        layer = family["seed_layer"]
        if layer == "not_in_seed_policy":
            continue
        assert layer in seed_layers, name


def test_seed_forbidden_inferences_are_carried_forward_not_dropped(
    policy: dict, seed: dict
) -> None:
    families_by_layer: dict[str, set[str]] = {}
    for family in policy["families"].values():
        layer = family["seed_layer"]
        if layer == "not_in_seed_policy":
            continue
        families_by_layer.setdefault(layer, set()).update(family["forbidden_inference"])
    for layer, declared in families_by_layer.items():
        seed_forbidden = set(seed["layers"][layer].get("forbidden_inference", []))
        assert seed_forbidden <= declared, layer


def test_outcome_envelope_forbids_scoring_and_security_identity_fields(
    policy: dict,
) -> None:
    envelope = policy["outcome_envelope"]
    forbidden = set(envelope["forbidden_fields"])
    assert {
        "probability",
        "score",
        "rank",
        "position_size",
        "expected_return",
        "ticker",
        "issuer_id",
        "security_id",
    } <= forbidden
    assert envelope["value_authority"] == "source_native_status_only"
    assert not forbidden & set(envelope["required_fields"])
    for field in ("known_at", "observed_at", "effective_at", "censoring_state", "revision_of"):
        assert field in envelope["required_fields"], field


def test_known_at_clock_orders_effective_known_and_observed(policy: dict) -> None:
    clock = policy["known_at_clock"]
    assert clock["ordering_rule"] == "effective_at_le_known_at_le_observed_at"
    assert clock["timezone"] == "utc_only"
    assert clock["timestamp_format"] == "iso8601_utc_z"
    assert clock["backfill_behavior"] == "forbidden_after_clock_open"
    assert clock["unknown_known_at_behavior"] == "record_stays_uncensored_and_unresolved"
    assert set(clock["clock_fields"]) == {"effective_at", "known_at", "observed_at"}


def test_only_a_terminal_source_statement_resolves_an_outcome(policy: dict) -> None:
    censoring = policy["censoring"]
    assert censoring["censoring_state_required"] is True
    resolving = {
        name for name, rule in censoring["rules"].items() if rule["resolves_outcome"]
    }
    assert resolving == {"not_censored_terminal_event"}
    for name, rule in censoring["rules"].items():
        expected = "terminal" if rule["resolves_outcome"] else "non_terminal"
        assert rule["terminality"] == expected, name
    for name, family in policy["families"].items():
        assert family["censoring_rule"] in censoring["rules"], name


def test_correction_grammar_binds_to_the_o1a_lineage_record(policy: dict) -> None:
    grammar = policy["correction_grammar"]
    assert grammar["correction_is_a_new_record"] is True
    assert grammar["original_snapshot_is_never_rewritten"] is True
    assert grammar["lineage_record_contract"] == "biocatalyst_operational_record.v1"
    assert grammar["lineage_record_kind"] == "correction_lineage"
    assert grammar["lineage_record_kind"] in RECORD_KINDS
    assert grammar["lineage_record_contract"] in ContractRegistry(ROOT).contract_ids


def test_identity_dependent_families_cite_owned_adapters_and_keep_a_closed_gate(
    policy: dict,
) -> None:
    adapters = _load_yaml(OWNERSHIP)["read_adapters"]
    cited = False
    for name, family in policy["families"].items():
        for adapter_id in family["entry_gate"]["required_identity_adapters"]:
            cited = True
            assert adapter_id in adapters, f"{name} cites unknown adapter {adapter_id}"
            adapter = adapters[adapter_id]
            if adapter["biocatalyst_eligible"]:
                assert adapter["blocker"] is None, adapter_id
            else:
                assert adapter["blocker"] in (
                    family["entry_gate"]["blockers"]
                ), adapter_id
                assert "eligible_identity_contract" in (
                    family["entry_gate"]["unsatisfied_preconditions"]
                ), name
        if family["entry_gate"]["required_identity_adapters"]:
            assert family["entry_gate"]["satisfied"] is False
            assert family["state"] == "clock_not_opened"
    assert cited


def test_nct_only_families_declare_no_identity_adapter(policy: dict) -> None:
    for name in (
        "trial_progression_termination",
        "endpoint_readout",
        "timing_slip",
        "enrollment_site_change",
        "regulatory_outcome",
    ):
        gate = policy["families"][name]["entry_gate"]
        assert gate["required_identity_adapters"] == [], name
        assert "eligible_identity_contract" not in gate["required_preconditions"], name


def test_every_required_source_id_exists_in_the_source_registry(policy: dict) -> None:
    sources = _load_yaml(SOURCE_REGISTRY)["sources"]
    for name, family in policy["families"].items():
        for source_id in family["entry_gate"]["required_source_ids"]:
            assert source_id in sources, f"{name} cites unknown source {source_id}"


def test_the_forecast_calibration_family_is_the_most_gated(policy: dict) -> None:
    gate = policy["families"]["forecast_calibration"]["entry_gate"]
    assert sorted(gate["unsatisfied_preconditions"]) == [
        "eligible_identity_contract",
        "eligible_source_registration",
        "frozen_policy_version",
    ]
    assert "no_graded_family_clock_is_open" in gate["blockers"]
    assert "prediction_is_an_outcome" in (
        policy["families"]["forecast_calibration"]["forbidden_inference"]
    )
