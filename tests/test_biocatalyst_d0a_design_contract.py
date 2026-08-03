"""BC-D0a design-contract tests: finite references, immutable bytes, fail-closed approval.

The PNGs are deliberate draft contract-state plates, not browser approvals. These
tests therefore prove integrity and rejection behavior, never a fictitious UI release.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
import yaml

from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    _biocatalyst_product_repo_file,
    canonical_json_sha256,
    validate_biocatalyst_product_acceptance_manifest,
)


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "config" / "biocatalyst_product_acceptance.yml"
CONTRACT_ID = "biocatalyst_product_acceptance_manifest.v1"


def _manifest() -> dict:
    value = yaml.safe_load(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _rebind(value: dict) -> dict:
    rebound = deepcopy(value)
    payload = {
        key: item
        for key, item in rebound.items()
        if key not in {"manifest_id", "content_sha256"}
    }
    digest = canonical_json_sha256(payload)
    rebound["content_sha256"] = digest
    rebound["manifest_id"] = f"biocatalyst_product_acceptance_{digest[:24]}"
    return rebound


def _reference_verifier_module():
    target = ROOT / "scripts" / "verify_biocatalyst_d0a_references.py"
    spec = importlib.util.spec_from_file_location("biocatalyst_d0a_reference_verifier", target)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_d0a_registers_an_executable_non_authorizing_product_acceptance_contract() -> None:
    registry = ContractRegistry(ROOT)
    assert CONTRACT_ID in registry.contract_ids
    schema = registry.schema_for(CONTRACT_ID)
    assert schema["properties"]["authority"]["properties"]["authorizes_ui_release"]["const"] is False
    assert schema["$defs"]["visual"]["properties"]["cells"]["maxItems"] == 24


def test_d0a_reference_corpus_is_exact_finite_and_rendered_at_frozen_dimensions() -> None:
    manifest = _manifest()
    verifier = _reference_verifier_module()
    assert verifier.reference_integrity_issues(manifest) == []

    cells = manifest["visual"]["cells"]
    assert len(cells) == 24
    combinations = {
        (cell["viewport"]["name"], cell["theme"], cell["language"], cell["motion"])
        for cell in cells
    }
    assert len(combinations) == 24
    assert {cell["ui_state"] for cell in cells} == set(manifest["visual"]["required_state_codes"])
    assert all(cell["masks"] == [] for cell in cells), "deterministic plates do not need masks"
    assert all(cell["zero_structural_diff"] is True for cell in cells)
    assert all("no_hover_only_meaning" in cell["accessibility_assertions"] for cell in cells)


def test_d0a_draft_remains_fail_closed_until_named_human_browser_and_measurement_receipts_exist() -> None:
    manifest = _manifest()
    issues = ContractRegistry(ROOT).issues(CONTRACT_ID, manifest)
    assert {issue.code for issue in issues} == {
        "product_acceptance.human_approval_pending",
        "product_acceptance.measurement_receipt_pending",
        "product_acceptance.performance_not_measured",
    }
    with pytest.raises(ContractValidationError, match="product_acceptance.human_approval_pending"):
        validate_biocatalyst_product_acceptance_manifest(manifest, repo_root=ROOT)


def test_d0a_rejects_a_mutated_reference_or_an_unbounded_mask_even_when_rebound() -> None:
    bad_hash = _manifest()
    bad_hash["visual"]["cells"][0]["reference_png_sha256"] = "0" * 64
    bad_hash = _rebind(bad_hash)
    issues = ContractRegistry(ROOT).issues(CONTRACT_ID, bad_hash)
    assert "product_acceptance.reference_hash" in {issue.code for issue in issues}

    bad_mask = _manifest()
    first = bad_mask["visual"]["cells"][0]
    first["masks"] = [{
        "id": "too_large",
        "x": 0,
        "y": 0,
        "width": first["viewport"]["width"],
        "height": first["viewport"]["height"],
        "reason": "would hide the entire reference",
    }]
    bad_mask = _rebind(bad_mask)
    issues = ContractRegistry(ROOT).issues(CONTRACT_ID, bad_mask)
    assert "product_acceptance.unbounded_mask" in {issue.code for issue in issues}


def test_d0a_rejects_cross_kind_bindings_and_escaped_or_symlinked_artifact_paths(
    tmp_path: Path,
) -> None:
    good = tmp_path / "committed.json"
    good.write_text("{}", encoding="utf-8")
    linked = tmp_path / "linked.json"
    linked.symlink_to(good)
    assert _biocatalyst_product_repo_file(tmp_path, "committed.json") == good.resolve()
    assert _biocatalyst_product_repo_file(tmp_path, "linked.json") is None
    assert _biocatalyst_product_repo_file(tmp_path, "../outside.json") is None

    manifest = _manifest()
    spec = ROOT / manifest["design_spec_ref"]
    manifest["reference_fixture"]["path"] = manifest["design_spec_ref"]
    manifest["reference_fixture"]["sha256"] = hashlib.sha256(spec.read_bytes()).hexdigest()
    manifest = _rebind(manifest)
    issues = ContractRegistry(ROOT).issues(CONTRACT_ID, manifest)
    assert "product_acceptance.binding_path" in {issue.code for issue in issues}


def test_d0a_rejects_matrix_and_approval_performance_pass_smuggling() -> None:
    matrix = _manifest()
    matrix["visual"]["cells"][1]["theme"] = "light"
    matrix = _rebind(matrix)
    codes = {issue.code for issue in ContractRegistry(ROOT).issues(CONTRACT_ID, matrix)}
    assert "product_acceptance.visual_matrix" in codes
    assert "product_acceptance.visual_cell_identity" in codes

    smuggled = _manifest()
    smuggled["state"] = "approved"
    smuggled["approval"].update(
        status="approved",
        named_reviewer="Fable Design Owner",
        recorded_at="2026-08-02T16:30:00Z",
        reason="Attempted manifest-only approval without a verified browser receipt.",
    )
    smuggled["performance"]["state"] = "measured_passed"
    for cell in smuggled["visual"]["cells"]:
        cell.update(
            approval_status="approved",
            reviewer_name="Fable Design Owner",
            browser_verification_state="passed",
            approval_reason="Attempted manifest-only approval without a trusted verifier.",
        )
    smuggled = _rebind(smuggled)
    codes = {issue.code for issue in ContractRegistry(ROOT).issues(CONTRACT_ID, smuggled)}
    assert "product_acceptance.measurement_receipt_pending" in codes
    assert "product_acceptance.trusted_browser_verifier_unavailable" in codes


def test_d0a_benchmark_is_content_addressed_and_complete_enough_to_block_a_fake_measurement_pass() -> None:
    manifest = _manifest()
    corpus_path = ROOT / manifest["benchmark_corpus"]["path"]
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    assert corpus["projection_sha256"] == hashlib.sha256(
        (ROOT / corpus["projection_path"]).read_bytes()
    ).hexdigest()
    assert any(
        endpoint["path"] == "/api/biocatalyst/v1/trial-peer-sets:resolve"
        for endpoint in corpus["primary_endpoints"]
    )
    assert corpus["future_measurement_receipt"]["state"] == "not_run"
    for field in ("run_id", "raw_samples_path", "summary_code_path", "summary_code_version", "summary_sha256", "pass_fail_digest"):
        assert corpus["future_measurement_receipt"][field] is None


def test_d0a_draft_receipt_is_explicitly_nonportable_and_not_a_browser_approval() -> None:
    manifest = _manifest()
    receipt_path = ROOT / manifest["visual"]["artifact"]["path"]
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["state"] == "reference_only_not_browser_verified"
    assert receipt["reference_truth_class"] == "draft_contract_state_plate"
    assert receipt["portable_across_browser_or_font_environments"] is False
    assert receipt["reviewer"] is None
