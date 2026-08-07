"""BC-D0a successor contract: v2 is a NEW contract, and it is actually satisfiable.

Two things are proven here.

1. **v1 is untouched.** ``config/biocatalyst_product_acceptance.yml`` and its v1 schema
   stay exactly as committed -- ``state`` const-locked, both ``supersedes_*`` const null,
   all six ``authorizes_*`` const false. v2 is a separate contract id with a separate
   schema, which is the only lawful shape for a successor.

2. **v2 fails closed today and can be cleared tomorrow.** The committed instance states
   honestly that the browser matrix has not been captured. When -- and only when -- the
   independent verifier has written a passing receipt whose bytes hash to the bound
   digest, the same contract validates clean. That is the difference between this and v1,
   whose ``trusted_browser_verifier_unavailable`` gate no artifact can ever clear.

No test here opens a browser, a socket, or a file outside ``tmp_path``.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest
import yaml

from engine.biocatalyst.acceptance_v2 import (
    PRODUCT_ACCEPTANCE_V1_CONFIG_REF,
    PRODUCT_ACCEPTANCE_V2_CONFIG_REF,
    PRODUCT_ACCEPTANCE_V2_CONTRACT_ID,
    expected_cell_ids,
    expected_gate_parameters,
    load_browser_verifier,
    load_product_acceptance_v2_manifest,
    product_acceptance_v2_semantic_issues,
    validate_biocatalyst_product_acceptance_manifest_v2,
)
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    canonical_json_sha256,
)


ROOT = Path(__file__).resolve().parents[1]
V1_CONTRACT_ID = "biocatalyst_product_acceptance_manifest.v1"
V1_SCHEMA_PATH = ROOT / "contracts" / "biocatalyst" / "biocatalyst_product_acceptance_manifest.v1.schema.json"
V2_SCHEMA_PATH = ROOT / "contracts" / "biocatalyst" / "biocatalyst_product_acceptance_manifest.v2.schema.json"
RULING_REF = "research/BIOCATALYST_D0A_DESIGN_ADJUDICATION_2026-08-06.md"
VERIFIER_REF = "scripts/biocatalyst_browser_verifier.py"

# The pending codes the committed instance is EXPECTED to carry on this base.
# ``design_adjudication_pending_base`` heals by itself once the named ruling lands on
# main; ``trusted_browser_capture_pending`` heals only when the verifier has run.
COMMITTED_PENDING_CODES = {
    "product_acceptance_v2.design_adjudication_pending_base",
    "product_acceptance_v2.trusted_browser_capture_pending",
}

STATE_CODES = (
    "catalyst_radar", "explorer_dense", "trial_peer_matrix", "company_partial",
    "asset_ambiguous_identity", "regulatory_mixed_sources", "change_tape_correction",
    "evidence_thread_expanded", "historical_mode", "source_outage", "locked", "empty",
)

_STAND_IN_RULING = (
    "# BC-D0a named design adjudication (test stand-in)\n\n"
    "Byte-for-byte content is irrelevant to the binding mechanism under test: the\n"
    "contract binds this file by path AND SHA-256, so any edit must break the bind.\n"
)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _codes(issues) -> set[str]:
    return {issue.code for issue in issues}


def _rebind(root: Path, document: dict[str, Any]) -> dict[str, Any]:
    """Re-derive every self-referential digest after a deliberate mutation."""

    rebound = deepcopy(document)
    payload = {k: v for k, v in rebound.items() if k not in {"manifest_id", "content_sha256"}}
    digest = canonical_json_sha256(payload)
    rebound["content_sha256"] = digest
    rebound["manifest_id"] = f"biocatalyst_product_acceptance_v2_{digest[:24]}"
    return rebound


@pytest.fixture
def materialized(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    """A minimal repo where every bound file exists, including a stand-in ruling.

    The real ruling is not on this base yet, so the fixture writes a stand-in and
    re-binds the hash. What is under test is the binding *mechanism*, never the
    ruling's prose.
    """

    root = tmp_path.resolve() / "repo"
    root.mkdir()
    shutil.copytree(ROOT / "contracts", root / "contracts")
    for relative in (
        PRODUCT_ACCEPTANCE_V1_CONFIG_REF,
        PRODUCT_ACCEPTANCE_V2_CONFIG_REF,
        VERIFIER_REF,
        "research/BIOCATALYST_D0A_IA_STATE_CONTENT_CONTRACT.md",
        "data/biocatalyst/fixtures/biocatalyst_d0a_reference_fixture.v1.json",
        "data/biocatalyst/fixtures/biocatalyst_d0a_benchmark_corpus.v1.json",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    ruling = root / RULING_REF
    ruling.parent.mkdir(parents=True, exist_ok=True)
    ruling.write_text(_STAND_IN_RULING, encoding="utf-8")

    document = yaml.safe_load((root / PRODUCT_ACCEPTANCE_V2_CONFIG_REF).read_text(encoding="utf-8"))
    document["design_adjudication_sha256"] = _sha256_file(ruling)
    return root, _rebind(root, document)


# --------------------------------------------------------------------------------------
# v1 is not mutated, and cannot be.
# --------------------------------------------------------------------------------------


def test_v1_stays_const_locked_and_v2_is_a_separate_contract() -> None:
    v1 = json.loads(V1_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert v1["properties"]["contract_id"]["const"] == V1_CONTRACT_ID
    assert v1["properties"]["state"]["const"] == "draft_human_approval_pending"
    assert v1["properties"]["supersedes_manifest_id"]["const"] is None
    assert v1["properties"]["supersedes_manifest_content_sha256"]["const"] is None
    assert all(
        definition["const"] is False
        for definition in v1["properties"]["authority"]["properties"].values()
    )

    v2 = json.loads(V2_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert V2_SCHEMA_PATH != V1_SCHEMA_PATH
    assert v2["properties"]["contract_id"]["const"] == PRODUCT_ACCEPTANCE_V2_CONTRACT_ID
    assert v2["$id"] != v1["$id"]

    registry = ContractRegistry(ROOT)
    assert V1_CONTRACT_ID in registry.contract_ids
    assert PRODUCT_ACCEPTANCE_V2_CONTRACT_ID in registry.contract_ids


def test_v1_config_still_declares_the_draft_state_v2_supersedes() -> None:
    v1 = yaml.safe_load((ROOT / PRODUCT_ACCEPTANCE_V1_CONFIG_REF).read_text(encoding="utf-8"))
    assert v1["state"] == "draft_human_approval_pending"
    assert v1["supersedes_manifest_id"] is None
    assert v1["supersedes_manifest_content_sha256"] is None

    v2 = load_product_acceptance_v2_manifest(ROOT)
    assert v2["supersedes_manifest_ref"] == PRODUCT_ACCEPTANCE_V1_CONFIG_REF
    assert v2["supersedes_manifest_id"] == v1["manifest_id"]
    assert v2["supersedes_manifest_content_sha256"] == v1["content_sha256"]


# --------------------------------------------------------------------------------------
# The committed instance is honest: capture has NOT happened.
# --------------------------------------------------------------------------------------


def test_committed_v2_instance_is_schema_clean_and_states_capture_is_pending() -> None:
    document = load_product_acceptance_v2_manifest(ROOT)
    registry = ContractRegistry(ROOT)
    assert list(registry.issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, document)) == []

    assert document["state"] == "draft_awaiting_browser_capture"
    assert document["trusted_verifier"]["capture_state"] == "not_run"
    assert document["trusted_verifier"]["receipt_path"] is None
    assert document["trusted_verifier"]["receipt_sha256"] is None
    assert document["matrix"]["reference_plates_are_the_implementation_target"] is False
    assert all(value is False for value in document["authority"].values())

    assert _codes(product_acceptance_v2_semantic_issues(document, repo_root=ROOT)) == COMMITTED_PENDING_CODES
    with pytest.raises(ContractValidationError, match="trusted_browser_capture_pending"):
        validate_biocatalyst_product_acceptance_manifest_v2(document, repo_root=ROOT)


def test_committed_v2_instance_records_the_named_ruling_without_claiming_a_capture() -> None:
    approval = load_product_acceptance_v2_manifest(ROOT)["approval"]
    assert approval["status"] == "approved_with_amendments"
    assert approval["ruling"] == "amend"
    assert approval["reviewer_role"] == "fable_or_opus_design_owner"
    assert isinstance(approval["named_reviewer"], str) and approval["named_reviewer"].strip()
    assert approval["recorded_at"] == "2026-08-06T00:00:00Z"
    assert approval["browser_receipt_required"] is True
    # A recorded design ruling is necessary and never sufficient.
    assert "pending capture" in approval["reason"]


def test_committed_v2_instance_binds_the_named_ruling_and_the_verifier_by_hash() -> None:
    document = load_product_acceptance_v2_manifest(ROOT)
    assert document["design_adjudication_ref"] == RULING_REF
    assert len(document["design_adjudication_sha256"]) == 64
    verifier_block = document["trusted_verifier"]
    assert verifier_block["module_path"] == VERIFIER_REF
    assert verifier_block["module_sha256"] == _sha256_file(ROOT / VERIFIER_REF)
    assert verifier_block["trust_basis"] == "receipt_digest_over_bytes_written_by_the_verifier"
    assert verifier_block["required_checks"] == list(load_browser_verifier(ROOT).REQUIRED_CHECKS)
    assert document["gates"] == expected_gate_parameters(ROOT)
    assert document["matrix"]["cell_ids"] == expected_cell_ids(STATE_CODES, ROOT)


# --------------------------------------------------------------------------------------
# The successor lineage v1 structurally could not declare.
# --------------------------------------------------------------------------------------


def test_v2_requires_a_non_null_predecessor_that_matches_the_committed_v1(materialized) -> None:
    root, document = materialized
    registry = ContractRegistry(root)
    assert _codes(product_acceptance_v2_semantic_issues(document, repo_root=root)) == {
        "product_acceptance_v2.trusted_browser_capture_pending"
    }

    for field in ("supersedes_manifest_id", "supersedes_manifest_content_sha256"):
        nulled = _rebind(root, {**document, field: None})
        assert any(issue.code == "schema" for issue in registry.issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, nulled))

    wrong = _rebind(root, {**document, "supersedes_manifest_id": "biocatalyst_product_acceptance_" + "0" * 24})
    assert list(registry.issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, wrong)) == []
    assert "product_acceptance_v2.supersession_binding" in _codes(
        product_acceptance_v2_semantic_issues(wrong, repo_root=root)
    )


def test_the_named_ruling_is_bound_by_bytes_not_by_name(materialized) -> None:
    root, document = materialized
    assert "product_acceptance_v2.design_adjudication_hash" not in _codes(
        product_acceptance_v2_semantic_issues(document, repo_root=root)
    )
    (root / RULING_REF).write_text(_STAND_IN_RULING + "one more sentence.\n", encoding="utf-8")
    assert "product_acceptance_v2.design_adjudication_hash" in _codes(
        product_acceptance_v2_semantic_issues(document, repo_root=root)
    )
    (root / RULING_REF).unlink()
    assert "product_acceptance_v2.design_adjudication_pending_base" in _codes(
        product_acceptance_v2_semantic_issues(document, repo_root=root)
    )


# --------------------------------------------------------------------------------------
# Design acceptance is not a release authorization.
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "flag",
    [
        "authorizes_ui_release",
        "authorizes_source_activation",
        "authorizes_entitlement_change",
        "authorizes_model_promotion",
        "authorizes_neural_web_authority",
        "authorizes_prophet_behavior",
    ],
)
def test_no_authority_flag_can_ever_be_raised(materialized, flag: str) -> None:
    root, document = materialized
    raised = _rebind(root, {**document, "authority": {**document["authority"], flag: True}})
    schema_issues = ContractRegistry(root).issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, raised)
    assert any(issue.code == "schema" for issue in schema_issues)
    assert "product_acceptance_v2.authority_must_not_authorize" in _codes(
        product_acceptance_v2_semantic_issues(raised, repo_root=root)
    )


def test_a_recorded_ruling_without_a_named_reviewer_is_rejected(materialized) -> None:
    root, document = materialized
    anonymous = _rebind(root, {**document, "approval": {**document["approval"], "named_reviewer": None}})
    assert any(issue.code == "schema" for issue in ContractRegistry(root).issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, anonymous))
    assert "product_acceptance_v2.approval_incomplete" in _codes(
        product_acceptance_v2_semantic_issues(anonymous, repo_root=root)
    )

    undated = _rebind(root, {**document, "approval": {**document["approval"], "recorded_at": None}})
    assert "product_acceptance_v2.approval_incomplete" in _codes(
        product_acceptance_v2_semantic_issues(undated, repo_root=root)
    )


# --------------------------------------------------------------------------------------
# The gates the ruling minted are machine-checkable, and the VERIFIER owns them.
# --------------------------------------------------------------------------------------


def test_the_decision_sentence_budget_is_pinned_by_the_schema(materialized) -> None:
    root, document = materialized
    registry = ContractRegistry(root)
    for field, value in (("max_words_en", 15), ("max_characters_zh", 25)):
        loosened = deepcopy(document)
        loosened["gates"]["decision_sentence"][field] = value
        assert any(issue.code == "schema" for issue in registry.issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, _rebind(root, loosened)))


def test_gate_parameters_must_agree_with_the_verifier_not_the_other_way_round(materialized) -> None:
    root, document = materialized
    widened = deepcopy(document)
    widened["gates"]["bilingual_gate"]["zh_tier1_latin_whitelist"] = [
        *widened["gates"]["bilingual_gate"]["zh_tier1_latin_whitelist"][:5],
        "any English field name",
    ]
    widened = _rebind(root, widened)
    assert list(ContractRegistry(root).issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, widened)) == []
    assert "product_acceptance_v2.gate_parameters_disagree_with_verifier" in _codes(
        product_acceptance_v2_semantic_issues(widened, repo_root=root)
    )

    restanced = deepcopy(document)
    restanced["gates"]["decision_sentence"]["research_stances_en"] = [
        "Act", "Get ready", "Watch", "Protect gains", "Stand aside", "Ignore",
    ]
    assert "product_acceptance_v2.gate_parameters_disagree_with_verifier" in _codes(
        product_acceptance_v2_semantic_issues(_rebind(root, restanced), repo_root=root)
    )


def test_the_capture_matrix_identifiers_are_derived_by_the_verifier(materialized) -> None:
    root, document = materialized
    shuffled = deepcopy(document)
    shuffled["matrix"]["cell_ids"] = list(reversed(shuffled["matrix"]["cell_ids"]))
    assert "product_acceptance_v2.matrix_cell_ids" in _codes(
        product_acceptance_v2_semantic_issues(_rebind(root, shuffled), repo_root=root)
    )


def test_required_checks_must_be_exactly_the_verifiers_named_checks(materialized) -> None:
    root, document = materialized
    dropped = deepcopy(document)
    dropped["trusted_verifier"]["required_checks"] = list(reversed(dropped["trusted_verifier"]["required_checks"]))
    assert "product_acceptance_v2.required_checks_disagree_with_verifier" in _codes(
        product_acceptance_v2_semantic_issues(_rebind(root, dropped), repo_root=root)
    )


def test_the_verifier_module_is_bound_by_its_exact_committed_bytes(materialized) -> None:
    root, document = materialized
    (root / VERIFIER_REF).write_text(
        (root / VERIFIER_REF).read_text(encoding="utf-8") + "\n# drifted\n", encoding="utf-8"
    )
    assert "product_acceptance_v2.verifier_module_hash" in _codes(
        product_acceptance_v2_semantic_issues(document, repo_root=root)
    )
    (root / VERIFIER_REF).unlink()
    assert "product_acceptance_v2.verifier_module_unavailable" in _codes(
        product_acceptance_v2_semantic_issues(document, repo_root=root)
    )


# --------------------------------------------------------------------------------------
# The acceptance path: a receipt whose bytes the verifier actually wrote.
# --------------------------------------------------------------------------------------


def _write_passing_receipt(root: Path) -> tuple[str, str]:
    """Run the real verifier against a fake page driver and return (path, digest)."""

    verifier = load_browser_verifier(root)
    import tests.test_biocatalyst_browser_verifier as harness

    driver = harness.FakeDriver(
        lambda cell: verifier.CellObservation(
            **{
                **{
                    key: value
                    for key, value in vars(harness._good_observation(cell)).items()
                    if key not in {"braid_marks", "focus_observations"}
                },
                "braid_marks": tuple(
                    verifier.BraidMark(mark.mark_id, mark.keyboard_reachable, mark.text_equivalent)
                    for mark in harness._good_observation(cell).braid_marks
                ),
                "focus_observations": tuple(
                    verifier.FocusObservation(f.selector, f.outline_style, f.outline_width_px, f.box_shadow)
                    for f in harness._good_observation(cell).focus_observations
                ),
            }
        )
    )
    run = verifier.run_matrix(
        url="http://127.0.0.1:0/biocatalyst.html",
        cells=verifier.matrix_from_axes(STATE_CODES),
        driver=driver,
        output_dir=root / "mockups" / "refs" / "biocatalyst" / "d0b" / "artifacts",
        now_fn=harness.FrozenClock(),
    )
    assert run.state == "passed"
    return str(run.receipt_path.relative_to(root)), run.receipt_sha256


def _accepted(root: Path, document: dict[str, Any], receipt_path: str, digest: str) -> dict[str, Any]:
    accepted = deepcopy(document)
    accepted["state"] = "design_accepted_capture_complete"
    accepted["trusted_verifier"]["capture_state"] = "passed"
    accepted["trusted_verifier"]["receipt_path"] = receipt_path
    accepted["trusted_verifier"]["receipt_sha256"] = digest
    return _rebind(root, accepted)


def test_a_verifier_written_passing_receipt_clears_the_contract(materialized) -> None:
    root, document = materialized
    receipt_path, digest = _write_passing_receipt(root)
    accepted = _accepted(root, document, receipt_path, digest)

    assert list(ContractRegistry(root).issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, accepted)) == []
    assert product_acceptance_v2_semantic_issues(accepted, repo_root=root) == []
    validate_biocatalyst_product_acceptance_manifest_v2(accepted, repo_root=root)
    # ... and it still authorizes nothing.
    assert all(value is False for value in accepted["authority"].values())


def test_a_claimed_capture_with_no_receipt_file_is_rejected(materialized) -> None:
    root, document = materialized
    receipt_path, digest = _write_passing_receipt(root)
    accepted = _accepted(root, document, receipt_path, digest)
    (root / receipt_path).unlink()
    assert "product_acceptance_v2.verifier_receipt_unavailable" in _codes(
        product_acceptance_v2_semantic_issues(accepted, repo_root=root)
    )


def test_one_tampered_byte_in_the_receipt_breaks_the_bind(materialized) -> None:
    root, document = materialized
    receipt_path, digest = _write_passing_receipt(root)
    accepted = _accepted(root, document, receipt_path, digest)
    target = root / receipt_path
    target.write_bytes(target.read_bytes().replace(b'"passed"', b'"PASSED"', 1))
    assert "product_acceptance_v2.verifier_receipt_digest_mismatch" in _codes(
        product_acceptance_v2_semantic_issues(accepted, repo_root=root)
    )


def test_a_hand_authored_receipt_is_not_produced_by_the_trusted_verifier(materialized) -> None:
    root, document = materialized
    receipt_path, digest = _write_passing_receipt(root)
    forged_body = json.loads((root / receipt_path).read_text(encoding="utf-8"))
    forged_body["verifier_module_sha256"] = "0" * 64
    forged_bytes = json.dumps(forged_body, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    forged_path = root / "mockups" / "refs" / "biocatalyst" / "d0b" / "artifacts" / "forged.json"
    forged_path.write_bytes(forged_bytes)
    forged = _accepted(
        root,
        document,
        str(forged_path.relative_to(root)),
        hashlib.sha256(forged_bytes).hexdigest(),
    )
    codes = _codes(product_acceptance_v2_semantic_issues(forged, repo_root=root))
    assert "product_acceptance_v2.receipt_not_produced_by_trusted_verifier" in codes


def test_a_failed_capture_can_never_be_recorded_as_design_acceptance(materialized) -> None:
    root, document = materialized
    verifier = load_browser_verifier(root)
    import tests.test_biocatalyst_browser_verifier as harness

    run = verifier.run_matrix(
        url="http://127.0.0.1:0/biocatalyst.html",
        cells=verifier.matrix_from_axes(STATE_CODES),
        driver=harness.FakeDriver(
            lambda cell: verifier.CellObservation(
                cell_id=cell.cell_id, language=cell.language, loaded=False, load_error="HTTP 502"
            )
        ),
        output_dir=root / "mockups" / "refs" / "biocatalyst" / "d0b" / "artifacts",
        now_fn=harness.FrozenClock(),
    )
    assert run.state == "failed"
    claimed = _accepted(root, document, str(run.receipt_path.relative_to(root)), run.receipt_sha256)
    codes = _codes(product_acceptance_v2_semantic_issues(claimed, repo_root=root))
    assert "product_acceptance_v2.verifier_reported_failure" in codes
    with pytest.raises(ContractValidationError, match="verifier_reported_failure"):
        validate_biocatalyst_product_acceptance_manifest_v2(claimed, repo_root=root)


def test_a_capture_claim_with_null_receipt_fields_fails_the_schema(materialized) -> None:
    root, document = materialized
    smuggled = deepcopy(document)
    smuggled["state"] = "design_accepted_capture_complete"
    smuggled["trusted_verifier"]["capture_state"] = "passed"
    schema_issues = ContractRegistry(root).issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, _rebind(root, smuggled))
    assert any(issue.code == "schema" for issue in schema_issues)


def test_acceptance_state_without_a_passing_capture_is_rejected(materialized) -> None:
    root, document = materialized
    receipt_path, digest = _write_passing_receipt(root)
    mismatched = deepcopy(document)
    mismatched["state"] = "design_accepted_capture_complete"
    mismatched["trusted_verifier"]["capture_state"] = "failed"
    mismatched["trusted_verifier"]["receipt_path"] = receipt_path
    mismatched["trusted_verifier"]["receipt_sha256"] = digest
    mismatched = _rebind(root, mismatched)
    assert any(issue.code == "schema" for issue in ContractRegistry(root).issues(PRODUCT_ACCEPTANCE_V2_CONTRACT_ID, mismatched))
    assert "product_acceptance_v2.state_capture_disagreement" in _codes(
        product_acceptance_v2_semantic_issues(mismatched, repo_root=root)
    )


def test_manifest_identity_and_content_hash_are_self_binding(materialized) -> None:
    root, document = materialized
    drifted = deepcopy(document)
    drifted["effective_at"] = "2026-08-07T00:00:00Z"
    codes = _codes(product_acceptance_v2_semantic_issues(drifted, repo_root=root))
    assert {"product_acceptance_v2.hash", "product_acceptance_v2.identity"} <= codes
