from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
OWNERSHIP_REGISTRY = ROOT / "config" / "sector_intelligence_ownership.yml"


def _registry() -> dict:
    payload = yaml.safe_load(OWNERSHIP_REGISTRY.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def test_ownership_policy_is_one_writer_and_fail_closed() -> None:
    registry = _registry()

    assert registry["schema"] == "sector_intelligence_ownership.v1"
    assert registry["status"] == "partial_freeze"
    policy = registry["policy"]
    assert policy["one_writer_required"] is True
    assert policy["cross_domain_access"] == "versioned_read_adapter_only"
    assert policy["unresolved_owner_behavior"] == "block_or_degrade"
    assert policy["duplicate_writer_behavior"] == "hard_fail"


def test_biocatalyst_owns_only_the_source_canonical_trial_lane() -> None:
    registrations = _registry()["registrations"]
    owned = {
        name
        for name, registration in registrations.items()
        if registration["canonical_owner"] == "biocatalyst"
    }

    assert owned == {
        "clinicaltrials_source_record",
        "trial_snapshot_and_exact_diff",
        "biocatalyst_read_projection",
    }
    for name in owned:
        registration = registrations[name]
        assert registration["implementation_state"] == "frozen_for_b0a"
        assert registration["writer"] is not None
        assert registration["operational_owner"] == "mastermindx_platform_ops"


def test_shared_company_document_and_capital_lanes_are_not_faked() -> None:
    registrations = _registry()["registrations"]

    for name, expected_owner in {
        "generic_company_identity": "corporate_intelligence",
        "corporate_documents_and_spans": "corporate_intelligence",
        "capital_structure_projection": "capital_structure",
    }.items():
        registration = registrations[name]
        assert registration["canonical_owner"] == expected_owner
        assert registration["writer"] is None
        assert registration["implementation_state"] in {
            "blocked_pending_executable_contract",
            "planning_only",
        }


def test_neural_web_and_prophet_cannot_mutate_domain_truth() -> None:
    registrations = _registry()["registrations"]

    federation = registrations["cross_sector_read_federation"]
    assert federation["canonical_owner"] == "neural_web"
    assert {
        "domain_truth_writes",
        "source_record_mutation",
        "prediction_origination",
    } <= set(federation["prohibited_uses"])

    prophet = registrations["final_technical_selection"]
    assert prophet["canonical_owner"] == "prophet"
    assert {"candidate_origination", "candidate_reordering", "gating", "sizing"} <= set(
        prophet["prohibited_biocatalyst_fallbacks"]
    )


def test_full_b0_remains_explicitly_open() -> None:
    closure = _registry()["b0_closure"]

    assert closure["state"] == "open"
    assert closure["b0a_may_ship"] is True
    assert {
        "generic_company_identity_executable_contract",
        "complete_market_data_security_master_registration",
        "corporate_documents_and_spans_executable_contract",
        "capital_structure_projection_executable_contract",
    } == set(closure["blockers"])
    assert "source_canonical_nct_identity" in closure["unblocked_scope"]
    assert "exact_registry_record_diffs" in closure["unblocked_scope"]
