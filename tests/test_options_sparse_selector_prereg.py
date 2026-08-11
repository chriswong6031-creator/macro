from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from scripts.build_options_sparse_selector_prereg import (
    ABSTENTION_REASON_CODES,
    BENCHMARK_PATH,
    BENCHMARK_SCHEMA_PATH,
    LEGACY_CAMPAIGN_PATH,
    LEGACY_CAMPAIGN_SCHEMA_PATH,
    RECEIPT_PATH,
    RECEIPT_SCHEMA_PATH,
    RegistrationError,
    build_receipt,
    canonical_bytes,
    receipt_bytes,
)


ROOT = Path(__file__).resolve().parents[1]


def _copy(root: Path, relative: Path) -> None:
    destination = root / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / relative, destination)


def _minimal_repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for relative in (
        BENCHMARK_PATH,
        BENCHMARK_SCHEMA_PATH,
        LEGACY_CAMPAIGN_PATH,
        LEGACY_CAMPAIGN_SCHEMA_PATH,
        RECEIPT_SCHEMA_PATH,
    ):
        _copy(root, relative)
    return root


def _campaign_rows(root: Path) -> list[dict]:
    return [json.loads(line) for line in (root / LEGACY_CAMPAIGN_PATH).read_text().splitlines()]


def _write_campaign_rows(root: Path, rows: list[dict]) -> None:
    (root / LEGACY_CAMPAIGN_PATH).write_bytes(
        b"".join(canonical_bytes(row) + b"\n" for row in rows)
    )


def _content_id(prefix: str, value: dict, field: str) -> str:
    core = copy.deepcopy(value)
    core[field] = ""
    return prefix + hashlib.sha256(canonical_bytes(core)).hexdigest()


def test_contract_and_committed_receipt_are_exact_fresh_build() -> None:
    schema = json.loads((ROOT / RECEIPT_SCHEMA_PATH).read_text())
    Draft202012Validator.check_schema(schema)
    receipt = build_receipt(ROOT)
    Draft202012Validator(schema).validate(receipt)
    assert (ROOT / RECEIPT_PATH).read_bytes() == receipt_bytes(ROOT)


def test_receipt_and_embedded_rule_are_content_identified() -> None:
    receipt = build_receipt(ROOT)
    assert receipt["receipt_id"] == _content_id("ossr_", receipt, "receipt_id")
    assert receipt["registration"]["selector_rule_sha256"] == hashlib.sha256(
        canonical_bytes(receipt["selector_rule"])
    ).hexdigest()
    manifest = receipt["activation_manifest"]
    assert manifest["manifest_id"] == _content_id("ossm_", manifest, "manifest_id")


def test_current_eight_legacy_campaigns_are_permanently_ineligible() -> None:
    receipt = build_receipt(ROOT)
    source = receipt["activation_manifest"]["source"]
    rows = _campaign_rows(ROOT)
    assert len(rows) == source["records"] == 8
    assert source["sha256"] == hashlib.sha256(
        (ROOT / LEGACY_CAMPAIGN_PATH).read_bytes()
    ).hexdigest()
    assert {row["schema"] for row in rows} == {"options.signal_campaign/v1"}
    assert {row["evidence_phase"] for row in rows} == {"retrospective_discovery"}
    assert all(row["disposition"] == "abstain" for row in rows)
    assert all(row["training_eligible"] is False for row in rows)
    assert all(not any(row["authority"].values()) for row in rows)
    assert receipt["selector_rule"]["version_fence"]["legacy_campaign_v1_policy"] == (
        "permanently_ineligible"
    )


def test_empty_denominator_is_reconciled_without_claiming_sparse_gate() -> None:
    receipt = build_receipt(ROOT)
    manifest = receipt["activation_manifest"]
    reconciliation = receipt["reconciliation"]
    empty_digest = hashlib.sha256(canonical_bytes([])).hexdigest()
    assert manifest["candidate_count"] == manifest["prospective_source_count"] == 0
    assert manifest["excluded_legacy_source_count"] == 8
    assert manifest["candidate_ids_sha256"] == empty_digest
    assert reconciliation == {
        "candidate_count": 0,
        "decision_count": 0,
        "abstain_decision_count": 0,
        "propose_decision_count": 0,
        "candidate_ids_sha256": empty_digest,
        "decision_candidate_ids_sha256": empty_digest,
        "exactly_one_reconciled": True,
        "coverage_ratio": 1.0,
        "empty_set_policy": "vacuous_one_to_one_not_sparse_gate_evidence",
        "silent_drop_count": 0,
        "minimum_proposals_per_nyse_session": 0,
        "maximum_proposals_per_nyse_session": 3,
    }
    assert receipt["activation_disposition"] == {
        "action": "abstain",
        "reason_codes": ["NO_PROSPECTIVE_CANDIDATES"],
        "selector_active": False,
        "future_rows_policy": "new_governed_implementation_required",
    }
    assert not any(receipt["claim_boundary"].values())


def test_future_rule_freezes_sparse_no_quota_exactly_one_policy() -> None:
    rule = build_receipt(ROOT)["selector_rule"]
    assert rule["candidate_manifest"]["manifest_before_decisions"] is True
    assert rule["candidate_manifest"]["first_observed_revision_frozen"] is True
    assert rule["decisions"]["actions"] == ["abstain", "propose"]
    assert rule["decisions"]["exactly_one_per_candidate"] is True
    assert rule["decisions"]["minimum_proposals_per_nyse_session"] == 0
    assert rule["decisions"]["maximum_proposals_per_nyse_session"] == 3
    assert rule["decisions"]["quota_or_forced_fill"] is False
    assert rule["decisions"]["ranking_or_scoring"] is False
    assert rule["decisions"]["proposal_semantics"] == (
        "private_research_review_only_not_issued_plan"
    )


def test_future_rule_requires_exact_contract_and_all_truth_receipts() -> None:
    rule = build_receipt(ROOT)["selector_rule"]
    assert rule["exact_contract"]["campaign_required_fields"] == [
        "ticker",
        "right",
        "expiration",
        "strike",
        "strike_key",
    ]
    assert rule["exact_contract"]["mark_and_lifecycle_required_fields"] == [
        "root",
        "right",
        "expiry",
        "strike",
        "strike_millis",
        "occ_symbol",
    ]
    assert rule["exact_contract"]["fuzzy_or_derived_substitution"] is False
    truth = rule["required_truth_receipts"]
    assert set(truth) == {"options", "konseki", "mark", "lifecycle"}
    assert truth["options"]["missing_action"] == "abstain"
    assert truth["konseki"]["exact_absence_reason"] == (
        "exact_requested_as_of_context_absent"
    )
    assert truth["konseki"]["missing_or_absent_action"] == "abstain"
    assert truth["mark"]["nbbo_or_execution_authority"] is False
    assert truth["mark"]["missing_or_unavailable_action"] == "abstain"
    assert truth["lifecycle"]["require_prior_durable_enrollment_or_terminal"] is True
    assert truth["lifecycle"]["missing_drift_or_unavailable_action"] == "abstain"
    assert rule["abstention_reason_codes"] == ABSTENTION_REASON_CODES


def test_every_authority_and_promotion_claim_is_false() -> None:
    receipt = build_receipt(ROOT)
    assert not any(receipt["authority"].values())
    assert not any(receipt["selector_rule"]["authority"].values())
    assert not any(receipt["claim_boundary"].values())


def test_prospective_relabel_of_legacy_row_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    rows = _campaign_rows(root)
    rows[0]["evidence_phase"] = "prospective_after_rule_freeze"
    _write_campaign_rows(root, rows)
    with pytest.raises(RegistrationError, match="frozen benchmark baseline|retrospective"):
        build_receipt(root)


def test_authority_mutation_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    rows = _campaign_rows(root)
    rows[0]["authority"]["may_select"] = True
    _write_campaign_rows(root, rows)
    with pytest.raises(RegistrationError, match="schema validation|benchmark baseline"):
        build_receipt(root)


def test_duplicate_campaign_identity_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    rows = _campaign_rows(root)
    rows.append(copy.deepcopy(rows[0]))
    _write_campaign_rows(root, rows)
    with pytest.raises(RegistrationError, match="duplicate legacy campaign identity"):
        build_receipt(root)


@pytest.mark.parametrize("defect", ["torn", "blank", "noncanonical", "duplicate_key"])
def test_ledger_serialization_defects_fail_closed(tmp_path: Path, defect: str) -> None:
    root = _minimal_repo(tmp_path)
    path = root / LEGACY_CAMPAIGN_PATH
    raw = path.read_bytes()
    if defect == "torn":
        path.write_bytes(raw.rstrip(b"\n"))
    elif defect == "blank":
        path.write_bytes(raw.replace(b"\n", b"\n\n", 1))
    elif defect == "noncanonical":
        first, *rest = raw.splitlines()
        path.write_bytes(json.dumps(json.loads(first), indent=2).encode() + b"\n" + b"\n".join(rest) + b"\n")
    else:
        first, *rest = raw.splitlines()
        forged = first[:-1] + b',"schema":"options.signal_campaign/v1"}'
        path.write_bytes(forged + b"\n" + b"\n".join(rest) + b"\n")
    with pytest.raises(RegistrationError):
        build_receipt(root)


def test_benchmark_digest_mutation_fails_closed(tmp_path: Path) -> None:
    root = _minimal_repo(tmp_path)
    path = root / BENCHMARK_PATH
    benchmark = json.loads(path.read_text())
    benchmark["benchmark"]["completion_rule"]["current_state_at_registration"] = "surpass"
    path.write_text(json.dumps(benchmark))
    with pytest.raises(RegistrationError, match="schema validation|digest drift"):
        build_receipt(root)


def test_cli_check_proves_tracked_bytes() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_options_sparse_selector_prereg.py"),
            "--check",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK research/options_estate/sparse_selector_preregistration_receipt_v1.json" in (
        completed.stdout
    )
