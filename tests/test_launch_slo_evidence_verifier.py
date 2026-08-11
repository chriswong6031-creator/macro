from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest
import yaml

import engine.sector_intelligence.launch_slo_verifier as launch_slo_verifier
from engine.sector_intelligence.contracts import (
    ContractRegistry,
    ContractValidationError,
    canonical_json_bytes,
    canonical_json_sha256,
    validate_contract,
)
from engine.sector_intelligence.launch_slo_verifier import (
    LAUNCH_SLO_EVIDENCE_ARTIFACT_CONTRACT_ID,
    LAUNCH_SLO_RECOVERY_OBJECT_CONTRACT_ID,
    LaunchSloEvidenceError,
    verify_biocatalyst_launch_slo_evidence,
)


ROOT = Path(__file__).resolve().parents[1]
STAGES = (
    "fetch",
    "parse",
    "contract_validation",
    "completeness_reconciliation",
    "publication",
    "watermark_or_pointer",
)
START = "2026-08-04T00:00:00Z"
END = "2026-08-18T00:00:00Z"
CAPTURED = "2026-08-18T00:00:00Z"
GENERATION = "biocatalyst_soak_generation_0123456789abcdef01234567"
TRUSTED_NOW = datetime(2026, 8, 19, 0, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _freeze_trusted_utc_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(launch_slo_verifier, "_trusted_utc_now", lambda: TRUSTED_NOW)


def _load_configured_manifest() -> dict:
    payload = yaml.safe_load(
        (ROOT / "config" / "biocatalyst_launch_slo_manifest.yml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(payload, dict)
    return payload


def _rebind(payload: dict) -> dict:
    rebound = deepcopy(payload)
    content = {
        key: value
        for key, value in rebound.items()
        if key not in {"manifest_id", "content_sha256"}
    }
    digest = canonical_json_sha256(content)
    rebound["content_sha256"] = digest
    rebound["manifest_id"] = f"biocatalyst_launch_slo_{digest[:24]}"
    return rebound


def _scheduled_predecessor() -> dict:
    base = _load_configured_manifest()
    scheduled = deepcopy(base)
    scheduled["state"] = "soak_scheduled"
    scheduled["effective_at"] = START
    scheduled["supersedes_manifest_id"] = base["manifest_id"]
    scheduled["supersedes_manifest_content_sha256"] = base["content_sha256"]
    scheduled["sources"][0]["activation_state"] = "armed"
    scheduled["soak"].update(
        {
            "window_start": START,
            "window_end": END,
            "telemetry_generation_ref": None,
            "raw_telemetry_refs": [],
            "correction_replay_evidence_refs": [],
            "rollback_restore_evidence_refs": [],
            "ci_validation_receipt_ref": None,
            "source_results": [],
            "aggregate_passed": False,
            "scheduling_blockers": [],
        }
    )
    return _rebind(scheduled)


def _opportunity(index: int, *, miss: bool = False) -> dict:
    opened = datetime(2026, 8, 4, tzinfo=timezone.utc) + timedelta(hours=index)
    completed = opened + timedelta(seconds=900 if miss else 60)
    timestamp = opened.strftime("%Y-%m-%dT%H:%M:%SZ")
    completed_at = completed.strftime("%Y-%m-%dT%H:%M:%SZ")
    if miss:
        return {
            "opportunity_at": timestamp,
            "attempted_at": timestamp,
            "completed_at": completed_at,
            "outcome": "miss",
            "stage_results": {stage: False for stage in STAGES},
            "freshness_seconds": None,
            "completeness_ratio": None,
            "prior_scope_ratio": None,
            "upstream_unavailable": True,
            "critical_failure_types": [],
        }
    return {
        "opportunity_at": timestamp,
        "attempted_at": timestamp,
        "completed_at": completed_at,
        "outcome": "success",
        "stage_results": {stage: True for stage in STAGES},
        "freshness_seconds": 60,
        "completeness_ratio": 1.0,
        "prior_scope_ratio": 1.0,
        "upstream_unavailable": False,
        "critical_failure_types": [],
    }


def _artifact_document(
    kind: str,
    predecessor: dict,
    *,
    source_id: str | None,
    **extra: object,
) -> dict:
    return {
        "contract_id": "biocatalyst_launch_slo_evidence_artifact.v1",
        "schema_version": "1.0.0",
        "kind": kind,
        "generation_id": GENERATION,
        "scheduled_manifest_id": predecessor["manifest_id"],
        "scheduled_manifest_content_sha256": predecessor["content_sha256"],
        "source_id": source_id,
        "window_start": START,
        "window_end": END,
        "captured_at": CAPTURED,
        **extra,
    }


def _write_canonical(path: Path, payload: dict) -> tuple[int, str]:
    raw = canonical_json_bytes(payload)
    path.write_bytes(raw)
    return len(raw), hashlib.sha256(raw).hexdigest()


def _artifact_ref(kind: str, source_id: str | None, document: dict, artifacts: Path) -> dict:
    byte_count, digest = _write_canonical(artifacts / "pending.json", document)
    target = artifacts / f"{digest}.json"
    (artifacts / "pending.json").replace(target)
    return {
        "artifact_id": f"biocatalyst_artifact_{digest[:24]}",
        "kind": kind,
        "object_ref": f"r2://biocatalyst-soak/{kind}/{digest}.json",
        "content_sha256": digest,
        "byte_count": byte_count,
        "captured_at": CAPTURED,
        "scheduled_manifest_id": document["scheduled_manifest_id"],
        "scheduled_manifest_content_sha256": document[
            "scheduled_manifest_content_sha256"
        ],
        "source_id": source_id,
        "window_start": START,
        "window_end": END,
    }


def _recovery_ref(store: Path, role: str, document: dict) -> dict:
    raw = canonical_json_bytes(document)
    digest = hashlib.sha256(raw).hexdigest()
    (store / role / f"{digest}.json").write_bytes(raw)
    return {
        "object_ref": f"r2://biocatalyst-soak/{role}/{digest}.json",
        "content_sha256": digest,
    }


def _full_commit_oid() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _claim(*, misses: int = 0) -> dict:
    successes = 336 - misses
    return {
        "source_id": "clinicaltrials_gov_v2",
        "expected_opportunities": 336,
        "excluded_predeclared_maintenance": 0,
        "excluded_source_native_nonpublication": 0,
        "denominator": 336,
        "stage_successes": {stage: successes for stage in STAGES},
        "successful_opportunities": successes,
        "misses": misses,
        "upstream_unavailable_observations": misses,
        "maximum_consecutive_misses_observed": 1 if misses else 0,
        "freshness_p95_seconds": 60,
        "minimum_completeness_ratio_observed": 1.0,
        "minimum_vs_prior_scope_ratio_observed": 1.0,
        "critical_failure_types": [],
        "passed": True,
    }


def _build_store(tmp_path: Path, *, miss: bool = False) -> tuple[dict, Path]:
    store = tmp_path / "trusted-evidence"
    artifacts = store / "artifacts"
    manifests = store / "manifests"
    artifacts.mkdir(parents=True)
    manifests.mkdir()
    (store / "recovery_input").mkdir()
    (store / "recovery_readback").mkdir()
    (store / ".biocatalyst_launch_slo_offline_store.v1").write_bytes(
        b"biocatalyst_launch_slo_offline_store.v1\n"
    )
    predecessor = _scheduled_predecessor()
    _write_canonical(manifests / f"{predecessor['content_sha256']}.json", predecessor)

    raw_document = _artifact_document(
        "raw_telemetry",
        predecessor,
        source_id="clinicaltrials_gov_v2",
        observations=[_opportunity(index, miss=miss and index == 12) for index in range(336)],
    )
    raw_ref = _artifact_ref("raw_telemetry", "clinicaltrials_gov_v2", raw_document, artifacts)
    generation_document = _artifact_document(
        "telemetry_generation",
        predecessor,
        source_id=None,
        raw_telemetry_refs=[
            {"source_id": "clinicaltrials_gov_v2", "content_sha256": raw_ref["content_sha256"]}
        ],
    )
    generation_ref = _artifact_ref("telemetry_generation", None, generation_document, artifacts)
    correction_input = _recovery_ref(
        store,
        "recovery_input",
        {
            "contract_id": "biocatalyst_launch_slo_recovery_object.v1",
            "schema_version": "1.0.0",
            "role": "input",
            "source_id": "clinicaltrials_gov_v2",
            "generation_id": GENERATION,
            "operation_kind": "correction_replay",
            "operation_id": "biocatalyst_correction_replay_0123456789abcdef01234567",
            "captured_at": CAPTURED,
            "expected_result_sha256": "c" * 64,
        },
    )
    correction_readback = _recovery_ref(
        store,
        "recovery_readback",
        {
            "contract_id": "biocatalyst_launch_slo_recovery_object.v1",
            "schema_version": "1.0.0",
            "role": "readback",
            "source_id": "clinicaltrials_gov_v2",
            "generation_id": GENERATION,
            "operation_kind": "correction_replay",
            "operation_id": "biocatalyst_correction_replay_0123456789abcdef01234567",
            "captured_at": CAPTURED,
            "input_content_sha256": correction_input["content_sha256"],
            "observed_result_sha256": "c" * 64,
            "readback_verified": True,
        },
    )
    correction_document = _artifact_document(
        "correction_replay",
        predecessor,
        source_id="clinicaltrials_gov_v2",
        drill_id="biocatalyst_correction_replay_0123456789abcdef01234567",
        procedure_version="biocatalyst_correction_replay_procedure.v1",
        started_at=CAPTURED,
        completed_at=CAPTURED,
        input_evidence=correction_input,
        target_evidence=correction_readback,
        expected_result_sha256="c" * 64,
        observed_result_sha256="c" * 64,
        verification_checks={
            "input_bound": True,
            "target_bound": True,
            "operation_applied": True,
            "readback_verified": True,
        },
        result="passed",
    )
    correction_ref = _artifact_ref("correction_replay", "clinicaltrials_gov_v2", correction_document, artifacts)
    rollback_input = _recovery_ref(
        store,
        "recovery_input",
        {
            "contract_id": "biocatalyst_launch_slo_recovery_object.v1",
            "schema_version": "1.0.0",
            "role": "input",
            "source_id": "clinicaltrials_gov_v2",
            "generation_id": GENERATION,
            "operation_kind": "rollback_restore",
            "operation_id": "biocatalyst_rollback_restore_0123456789abcdef01234567",
            "captured_at": CAPTURED,
            "expected_result_sha256": "f" * 64,
        },
    )
    rollback_readback = _recovery_ref(
        store,
        "recovery_readback",
        {
            "contract_id": "biocatalyst_launch_slo_recovery_object.v1",
            "schema_version": "1.0.0",
            "role": "readback",
            "source_id": "clinicaltrials_gov_v2",
            "generation_id": GENERATION,
            "operation_kind": "rollback_restore",
            "operation_id": "biocatalyst_rollback_restore_0123456789abcdef01234567",
            "captured_at": CAPTURED,
            "input_content_sha256": rollback_input["content_sha256"],
            "observed_result_sha256": "f" * 64,
            "readback_verified": True,
        },
    )
    rollback_document = _artifact_document(
        "rollback_restore",
        predecessor,
        source_id="clinicaltrials_gov_v2",
        drill_id="biocatalyst_rollback_restore_0123456789abcdef01234567",
        procedure_version="biocatalyst_rollback_restore_procedure.v1",
        started_at=CAPTURED,
        completed_at=CAPTURED,
        input_evidence=rollback_input,
        target_evidence=rollback_readback,
        expected_result_sha256="f" * 64,
        observed_result_sha256="f" * 64,
        verification_checks={
            "input_bound": True,
            "target_bound": True,
            "operation_applied": True,
            "readback_verified": True,
        },
        result="passed",
    )
    rollback_ref = _artifact_ref("rollback_restore", "clinicaltrials_gov_v2", rollback_document, artifacts)
    ci_document = _artifact_document(
        "ci_validation",
        predecessor,
        source_id=None,
        result="passed",
        run_id="biocatalyst_launch_slo_verify_0123456789abcdef01234567",
        commit_oid=_full_commit_oid(),
        hash_algorithm="git-sha1",
        workflow_id="biocatalyst_launch_slo_offline_verifier.v1",
        started_at=CAPTURED,
        completed_at=CAPTURED,
        check_outcomes={
            "contract_validation": True,
            "evidence_integrity": True,
            "source_recomputation": True,
        },
    )
    ci_ref = _artifact_ref("ci_validation", None, ci_document, artifacts)

    completed = deepcopy(predecessor)
    completed["state"] = "soak_complete_passed"
    completed["supersedes_manifest_id"] = predecessor["manifest_id"]
    completed["supersedes_manifest_content_sha256"] = predecessor["content_sha256"]
    completed["soak"].update(
        {
            "telemetry_generation_ref": generation_ref,
            "raw_telemetry_refs": [raw_ref],
            "correction_replay_evidence_refs": [correction_ref],
            "rollback_restore_evidence_refs": [rollback_ref],
            "ci_validation_receipt_ref": ci_ref,
            "source_results": [_claim(misses=int(miss))],
            "aggregate_passed": True,
        }
    )
    completed = _rebind(completed)
    return completed, store


def _replace_artifact(store: Path, ref: dict, payload: dict) -> None:
    """Replace one evidence object and keep its content-addressed manifest ref honest."""
    old = store / "artifacts" / f"{ref['content_sha256']}.json"
    raw = canonical_json_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    (store / "artifacts" / f"{digest}.json").write_bytes(raw)
    old.unlink()
    ref.update(
        artifact_id=f"biocatalyst_artifact_{digest[:24]}",
        object_ref=f"r2://biocatalyst-soak/{ref['kind']}/{digest}.json",
        content_sha256=digest,
        byte_count=len(raw),
        captured_at=payload["captured_at"],
    )


def _replace_recovery_object(store: Path, ref: dict, role: str, payload: dict) -> None:
    old = store / role / f"{ref['content_sha256']}.json"
    raw = canonical_json_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    (store / role / f"{digest}.json").write_bytes(raw)
    if old.name != f"{digest}.json":
        old.unlink()
    ref.update(
        object_ref=f"r2://biocatalyst-soak/{role}/{digest}.json",
        content_sha256=digest,
    )


def _refresh_generation_raw_ref(manifest: dict, store: Path) -> None:
    generation_ref = manifest["soak"]["telemetry_generation_ref"]
    generation_path = store / "artifacts" / f"{generation_ref['content_sha256']}.json"
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation["raw_telemetry_refs"][0]["content_sha256"] = manifest["soak"][
        "raw_telemetry_refs"
    ][0]["content_sha256"]
    _replace_artifact(store, generation_ref, generation)


def test_generic_registry_stays_fail_closed_while_explicit_offline_verifier_accepts_exact_pass(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path, miss=True)

    with pytest.raises(ContractValidationError, match="launch_slo.trusted_evidence_verifier_unavailable"):
        validate_contract(manifest, repo_root=ROOT)
    assert "launch_slo.trusted_evidence_verifier_unavailable" in {
        issue.code
        for issue in ContractRegistry(ROOT).issues(manifest["contract_id"], manifest)
    }

    result = verify_biocatalyst_launch_slo_evidence(
        manifest, evidence_root=store, repo_root=ROOT
    )
    assert result.aggregate_passed is True
    assert result.generation_id == GENERATION
    assert result.sources[0].misses == 1
    assert result.sources[0].upstream_unavailable_observations == 1


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        (
            lambda manifest, store: manifest["soak"]["source_results"][0].update(misses=0),
            "launch_slo.source_pass",
        ),
        (
            lambda manifest, store: manifest["soak"]["raw_telemetry_refs"][0].update(
                object_ref=(
                    "r2://biocatalyst-soak/raw_telemetry/nested/"
                    + manifest["soak"]["raw_telemetry_refs"][0]["content_sha256"]
                    + ".json"
                )
            ),
            "launch_slo.evidence.object_ref",
        ),
        (
            lambda manifest, store: (store / ".biocatalyst_launch_slo_offline_store.v1").unlink(),
            "launch_slo.evidence.missing",
        ),
    ],
)
def test_verifier_fails_closed_for_claim_or_store_mutation(tmp_path: Path, mutation, expected: str) -> None:
    manifest, store = _build_store(tmp_path, miss=True)
    mutation(manifest, store)
    if expected == "launch_slo.evidence.object_ref":
        manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match=expected):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_rejects_unfrozen_policy_edit_even_if_manifest_self_hash_is_rebound(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    manifest["sources"][0]["error_budget"]["minimum_opportunity_success_ratio"] = 0.994
    manifest["sources"][0]["error_budget"]["maximum_error_budget_fraction"] = 0.006
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.frozen_policy"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_rejects_missing_or_extra_scheduled_observation(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    digest = manifest["soak"]["raw_telemetry_refs"][0]["content_sha256"]
    path = store / "artifacts" / f"{digest}.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    document["observations"].pop()
    raw = canonical_json_bytes(document)
    path.write_bytes(raw)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.byte_count"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_rejects_hash_correct_duplicate_observations(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    old_ref = manifest["soak"]["raw_telemetry_refs"][0]
    old_path = store / "artifacts" / f"{old_ref['content_sha256']}.json"
    document = json.loads(old_path.read_text(encoding="utf-8"))
    document["observations"][-1]["opportunity_at"] = document["observations"][0]["opportunity_at"]
    raw = canonical_json_bytes(document)
    digest = hashlib.sha256(raw).hexdigest()
    (store / "artifacts" / f"{digest}.json").write_bytes(raw)
    old_path.unlink()
    old_ref.update(
        artifact_id=f"biocatalyst_artifact_{digest[:24]}",
        object_ref=f"r2://biocatalyst-soak/raw_telemetry/{digest}.json",
        content_sha256=digest,
        byte_count=len(raw),
    )
    generation_ref = manifest["soak"]["telemetry_generation_ref"]
    generation_path = store / "artifacts" / f"{generation_ref['content_sha256']}.json"
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    generation["raw_telemetry_refs"][0]["content_sha256"] = digest
    gen_raw = canonical_json_bytes(generation)
    gen_digest = hashlib.sha256(gen_raw).hexdigest()
    (store / "artifacts" / f"{gen_digest}.json").write_bytes(gen_raw)
    generation_path.unlink()
    generation_ref.update(
        artifact_id=f"biocatalyst_artifact_{gen_digest[:24]}",
        object_ref=f"r2://biocatalyst-soak/telemetry_generation/{gen_digest}.json",
        content_sha256=gen_digest,
        byte_count=len(gen_raw),
    )
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.observation_time"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_rejects_failed_recovery_drill(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    ref = manifest["soak"]["rollback_restore_evidence_refs"][0]
    path = store / "artifacts" / f"{ref['content_sha256']}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["result"] = "failed"
    raw = canonical_json_bytes(payload)
    digest = hashlib.sha256(raw).hexdigest()
    (store / "artifacts" / f"{digest}.json").write_bytes(raw)
    path.unlink()
    ref.update(
        artifact_id=f"biocatalyst_artifact_{digest[:24]}",
        object_ref=f"r2://biocatalyst-soak/rollback_restore/{digest}.json",
        content_sha256=digest,
        byte_count=len(raw),
    )
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.recovery"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_accepts_true_prefix_stage_failures_and_recomputes_each_stage(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    raw_ref = manifest["soak"]["raw_telemetry_refs"][0]
    raw_path = store / "artifacts" / f"{raw_ref['content_sha256']}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    observation = raw["observations"][12]
    observation.update(
        outcome="miss",
        stage_results={
            "fetch": True,
            "parse": False,
            "contract_validation": False,
            "completeness_reconciliation": False,
            "publication": False,
            "watermark_or_pointer": False,
        },
        freshness_seconds=60,
        completeness_ratio=None,
        prior_scope_ratio=None,
        upstream_unavailable=False,
    )
    _replace_artifact(store, raw_ref, raw)
    _refresh_generation_raw_ref(manifest, store)
    claim = manifest["soak"]["source_results"][0]
    claim.update(
        stage_successes={"fetch": 336, **{stage: 335 for stage in STAGES[1:]}},
        successful_opportunities=335,
        misses=1,
        upstream_unavailable_observations=0,
        maximum_consecutive_misses_observed=1,
    )
    manifest = _rebind(manifest)

    generic_issues = ContractRegistry(ROOT).issues(manifest["contract_id"], manifest)
    assert {issue.code for issue in generic_issues} == {
        "launch_slo.trusted_evidence_verifier_unavailable"
    }
    result = verify_biocatalyst_launch_slo_evidence(
        manifest, evidence_root=store, repo_root=ROOT
    )
    assert dict(result.sources[0].stage_successes) == {
        "fetch": 336,
        "parse": 335,
        "contract_validation": 335,
        "completeness_reconciliation": 335,
        "publication": 335,
        "watermark_or_pointer": 335,
    }


def test_verifier_rejects_nonmonotone_stage_or_upstream_after_fetch(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    raw_ref = manifest["soak"]["raw_telemetry_refs"][0]
    raw_path = store / "artifacts" / f"{raw_ref['content_sha256']}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["observations"][0]["outcome"] = "miss"
    raw["observations"][0]["stage_results"]["parse"] = False
    raw["observations"][0]["stage_results"]["contract_validation"] = True
    raw["observations"][0]["completeness_ratio"] = None
    raw["observations"][0]["prior_scope_ratio"] = None
    _replace_artifact(store, raw_ref, raw)
    _refresh_generation_raw_ref(manifest, store)
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.stage_order"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_requires_post_window_artifacts_and_resolved_recovery_objects(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    ci_ref = manifest["soak"]["ci_validation_receipt_ref"]
    ci_path = store / "artifacts" / f"{ci_ref['content_sha256']}.json"
    ci = json.loads(ci_path.read_text(encoding="utf-8"))
    ci["captured_at"] = START
    _replace_artifact(store, ci_ref, ci)
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.capture_time"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)

    manifest, store = _build_store(tmp_path / "second")
    recovery = manifest["soak"]["correction_replay_evidence_refs"][0]
    recovery_path = store / "artifacts" / f"{recovery['content_sha256']}.json"
    recovery_doc = json.loads(recovery_path.read_text(encoding="utf-8"))
    missing = recovery_doc["target_evidence"]["content_sha256"]
    (store / "recovery_readback" / f"{missing}.json").unlink()
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.missing"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_derives_ci_and_recovery_outcomes_from_typed_resolved_receipts(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    ci_ref = manifest["soak"]["ci_validation_receipt_ref"]
    ci_path = store / "artifacts" / f"{ci_ref['content_sha256']}.json"
    ci = json.loads(ci_path.read_text(encoding="utf-8"))
    ci["check_outcomes"]["source_recomputation"] = False
    _replace_artifact(store, ci_ref, ci)
    manifest = _rebind(manifest)
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.ci_result"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)

    manifest, store = _build_store(tmp_path / "second")
    recovery_ref = manifest["soak"]["correction_replay_evidence_refs"][0]
    recovery_path = store / "artifacts" / f"{recovery_ref['content_sha256']}.json"
    recovery = json.loads(recovery_path.read_text(encoding="utf-8"))
    readback_ref = recovery["target_evidence"]
    readback_path = store / "recovery_readback" / f"{readback_ref['content_sha256']}.json"
    readback = json.loads(readback_path.read_text(encoding="utf-8"))
    readback["observed_result_sha256"] = "0" * 64
    readback_raw = canonical_json_bytes(readback)
    readback_digest = hashlib.sha256(readback_raw).hexdigest()
    (store / "recovery_readback" / f"{readback_digest}.json").write_bytes(readback_raw)
    readback_path.unlink()
    recovery["target_evidence"] = {
        "object_ref": f"r2://biocatalyst-soak/recovery_readback/{readback_digest}.json",
        "content_sha256": readback_digest,
    }
    _replace_artifact(store, recovery_ref, recovery)
    manifest = _rebind(manifest)
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.recovery_result"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


@pytest.mark.parametrize(
    ("role", "field", "value"),
    [
        ("raw_telemetry", "result", "passed"),
        ("telemetry_generation", "observations", []),
        ("correction_replay", "commit_oid", "a" * 40),
        ("ci_validation", "drill_id", "biocatalyst_correction_replay_0123456789abcdef01234567"),
    ],
)
def test_artifact_kind_payloads_are_mutually_exclusive(tmp_path: Path, role: str, field: str, value: object) -> None:
    manifest, store = _build_store(tmp_path)
    if role == "raw_telemetry":
        ref = manifest["soak"]["raw_telemetry_refs"][0]
    elif role == "telemetry_generation":
        ref = manifest["soak"]["telemetry_generation_ref"]
    elif role == "correction_replay":
        ref = manifest["soak"]["correction_replay_evidence_refs"][0]
    else:
        ref = manifest["soak"]["ci_validation_receipt_ref"]
    payload = json.loads(
        (store / "artifacts" / f"{ref['content_sha256']}.json").read_text(encoding="utf-8")
    )
    payload[field] = value
    with pytest.raises(ContractValidationError, match="False schema does not allow"):
        ContractRegistry(ROOT).validate(payload["contract_id"], payload)


@pytest.mark.parametrize(
    ("oid", "algorithm"),
    [
        ("a" * 39, "git-sha1"),
        ("A" * 40, "git-sha1"),
        ("a" * 40, "git-sha256"),
    ],
)
def test_ci_commit_oid_rejects_short_uppercase_or_hash_algorithm_mismatch(
    tmp_path: Path, oid: str, algorithm: str
) -> None:
    manifest, store = _build_store(tmp_path)
    ref = manifest["soak"]["ci_validation_receipt_ref"]
    payload = json.loads(
        (store / "artifacts" / f"{ref['content_sha256']}.json").read_text(encoding="utf-8")
    )
    payload["commit_oid"] = oid
    payload["hash_algorithm"] = algorithm
    with pytest.raises(ContractValidationError, match="does not match"):
        ContractRegistry(ROOT).validate(payload["contract_id"], payload)


def test_verifier_rejects_symlinked_artifact_and_noncanonical_bytes(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    ref = manifest["soak"]["raw_telemetry_refs"][0]
    path = store / "artifacts" / f"{ref['content_sha256']}.json"
    outside = tmp_path / "outside.json"
    outside.write_bytes(path.read_bytes())
    path.unlink()
    path.symlink_to(outside)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.symlink"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)

    path.unlink()
    path.write_bytes(outside.read_bytes() + b"\n")
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.byte_count"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="platform has no FIFO support")
@pytest.mark.parametrize("target", ["sentinel", "artifact"])
def test_fifo_evidence_leaf_fails_closed_in_timed_subprocess(
    tmp_path: Path, target: str
) -> None:
    manifest, store = _build_store(tmp_path)
    if target == "sentinel":
        fifo = store / ".biocatalyst_launch_slo_offline_store.v1"
    else:
        artifact_ref = manifest["soak"]["raw_telemetry_refs"][0]
        fifo = store / "artifacts" / f"{artifact_ref['content_sha256']}.json"
    fifo.unlink()
    os.mkfifo(fifo)
    manifest_path = tmp_path / "completed-manifest.json"
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    verifier_script = """
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

import engine.sector_intelligence.launch_slo_verifier as verifier

verifier._trusted_utc_now = lambda: datetime(2026, 8, 19, tzinfo=timezone.utc)
manifest = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
try:
    verifier.verify_biocatalyst_launch_slo_evidence(
        manifest,
        evidence_root=Path(sys.argv[2]),
        repo_root=Path(sys.argv[3]),
    )
except verifier.LaunchSloEvidenceError as exc:
    print(exc)
    raise SystemExit(0 if "launch_slo.evidence.file" in str(exc) else 2)
raise SystemExit(3)
"""
    started = time.monotonic()
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            verifier_script,
            str(manifest_path),
            str(store),
            str(ROOT),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    elapsed = time.monotonic() - started
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "launch_slo.evidence.file" in completed.stdout
    assert elapsed < 5


def test_verifier_refuses_relative_evidence_root_and_nonpass_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, store = _build_store(tmp_path)
    monkeypatch.chdir(tmp_path)
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.root"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root="trusted-evidence", repo_root=ROOT)

    manifest["state"] = "soak_complete_failed"
    manifest["soak"]["aggregate_passed"] = False
    manifest = _rebind(manifest)
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.claim_state"):
        verify_biocatalyst_launch_slo_evidence(manifest, evidence_root=store, repo_root=ROOT)


def test_verifier_freezes_trusted_clock_once_after_soak_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, store = _build_store(tmp_path)
    calls: list[datetime] = []

    def frozen_now() -> datetime:
        calls.append(TRUSTED_NOW)
        return TRUSTED_NOW

    monkeypatch.setattr(launch_slo_verifier, "_trusted_utc_now", frozen_now)
    result = verify_biocatalyst_launch_slo_evidence(
        manifest, evidence_root=store, repo_root=ROOT
    )
    assert result.aggregate_passed is True
    assert calls == [TRUSTED_NOW]


def test_verifier_rejects_future_soak_end_and_future_artifact_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, store = _build_store(tmp_path)
    before_end = datetime(2026, 8, 17, 23, 59, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(launch_slo_verifier, "_trusted_utc_now", lambda: before_end)
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.future_time"):
        verify_biocatalyst_launch_slo_evidence(
            manifest, evidence_root=store, repo_root=ROOT
        )

    manifest, store = _build_store(tmp_path / "future-capture")
    ci_ref = manifest["soak"]["ci_validation_receipt_ref"]
    ci_path = store / "artifacts" / f"{ci_ref['content_sha256']}.json"
    ci = json.loads(ci_path.read_text(encoding="utf-8"))
    ci["captured_at"] = "2026-08-19T00:00:01Z"
    _replace_artifact(store, ci_ref, ci)
    manifest = _rebind(manifest)
    monkeypatch.setattr(launch_slo_verifier, "_trusted_utc_now", lambda: TRUSTED_NOW)
    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.future_time"):
        verify_biocatalyst_launch_slo_evidence(
            manifest, evidence_root=store, repo_root=ROOT
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("attempted_at", "2026-08-03T23:59:59Z"),
        ("attempted_at", "2026-08-04T00:02:00Z"),
        ("completed_at", "2026-08-04T00:15:01Z"),
    ],
)
def test_verifier_enforces_attempt_and_completion_inside_frozen_opportunity_window(
    tmp_path: Path, field: str, value: str
) -> None:
    manifest, store = _build_store(tmp_path)
    raw_ref = manifest["soak"]["raw_telemetry_refs"][0]
    raw_path = store / "artifacts" / f"{raw_ref['content_sha256']}.json"
    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    raw["observations"][0][field] = value
    _replace_artifact(store, raw_ref, raw)
    _refresh_generation_raw_ref(manifest, store)
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.opportunity_window"):
        verify_biocatalyst_launch_slo_evidence(
            manifest, evidence_root=store, repo_root=ROOT
        )


def test_miss_may_complete_exactly_at_frozen_window_close(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path, miss=True)
    raw_ref = manifest["soak"]["raw_telemetry_refs"][0]
    raw = json.loads(
        (store / "artifacts" / f"{raw_ref['content_sha256']}.json").read_text(
            encoding="utf-8"
        )
    )
    assert raw["observations"][12]["completed_at"] == "2026-08-04T12:15:00Z"
    result = verify_biocatalyst_launch_slo_evidence(
        manifest, evidence_root=store, repo_root=ROOT
    )
    assert result.sources[0].misses == 1


@pytest.mark.parametrize("field", ["attempted_at", "completed_at"])
def test_opportunity_timing_fields_are_required_canonical_contract_fields(
    field: str,
) -> None:
    payload = json.loads(
        (
            ROOT
            / "data/biocatalyst/fixtures/launch_slo_evidence/biocatalyst_launch_slo_evidence_artifact.v1.valid.json"
        ).read_text(encoding="utf-8")
    )
    payload["observations"][0].pop(field)
    with pytest.raises(ContractValidationError, match=f"{field!r} is a required property"):
        ContractRegistry(ROOT).validate(payload["contract_id"], payload)


@pytest.mark.parametrize(
    ("role", "captured_at"),
    [
        ("recovery_input", "2026-08-17T23:59:59Z"),
        ("recovery_input", "2026-08-18T00:00:01Z"),
        ("recovery_readback", "2026-08-18T00:00:01Z"),
    ],
)
def test_verifier_rejects_hostile_recovery_chronology(
    tmp_path: Path, role: str, captured_at: str
) -> None:
    manifest, store = _build_store(tmp_path)
    artifact_ref = manifest["soak"]["correction_replay_evidence_refs"][0]
    artifact_path = store / "artifacts" / f"{artifact_ref['content_sha256']}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    ref_field = "input_evidence" if role == "recovery_input" else "target_evidence"
    object_ref = artifact[ref_field]
    object_path = store / role / f"{object_ref['content_sha256']}.json"
    recovery_object = json.loads(object_path.read_text(encoding="utf-8"))
    recovery_object["captured_at"] = captured_at
    _replace_recovery_object(store, object_ref, role, recovery_object)
    _replace_artifact(store, artifact_ref, artifact)
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match="launch_slo.evidence.recovery_time"):
        verify_biocatalyst_launch_slo_evidence(
            manifest, evidence_root=store, repo_root=ROOT
        )


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("input", "launch_slo.evidence.recovery_time"),
        ("started_at", "launch_slo.evidence.recovery_time"),
        ("completed_at", "launch_slo.evidence.recovery_time"),
        ("readback", "launch_slo.evidence.recovery_time"),
        ("captured_at", "launch_slo.evidence.future_time"),
    ],
)
def test_verifier_rejects_every_future_recovery_instant(
    tmp_path: Path, location: str, expected: str
) -> None:
    manifest, store = _build_store(tmp_path)
    artifact_ref = manifest["soak"]["correction_replay_evidence_refs"][0]
    artifact_path = store / "artifacts" / f"{artifact_ref['content_sha256']}.json"
    artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
    future = "2026-08-19T00:00:01Z"
    if location in {"input", "readback"}:
        ref_field = "input_evidence" if location == "input" else "target_evidence"
        role = "recovery_input" if location == "input" else "recovery_readback"
        object_ref = artifact[ref_field]
        object_path = store / role / f"{object_ref['content_sha256']}.json"
        recovery_object = json.loads(object_path.read_text(encoding="utf-8"))
        recovery_object["captured_at"] = future
        _replace_recovery_object(store, object_ref, role, recovery_object)
    else:
        artifact[location] = future
    _replace_artifact(store, artifact_ref, artifact)
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match=expected):
        verify_biocatalyst_launch_slo_evidence(
            manifest, evidence_root=store, repo_root=ROOT
        )


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("started_at", "launch_slo.evidence.ci_time"),
        ("completed_at", "launch_slo.evidence.ci_time"),
        ("captured_at", "launch_slo.evidence.future_time"),
    ],
)
def test_verifier_rejects_every_future_ci_instant(
    tmp_path: Path, field: str, expected: str
) -> None:
    manifest, store = _build_store(tmp_path)
    ci_ref = manifest["soak"]["ci_validation_receipt_ref"]
    ci_path = store / "artifacts" / f"{ci_ref['content_sha256']}.json"
    ci = json.loads(ci_path.read_text(encoding="utf-8"))
    ci[field] = "2026-08-19T00:00:01Z"
    _replace_artifact(store, ci_ref, ci)
    manifest = _rebind(manifest)

    with pytest.raises(LaunchSloEvidenceError, match=expected):
        verify_biocatalyst_launch_slo_evidence(
            manifest, evidence_root=store, repo_root=ROOT
        )


def test_store_root_descriptor_survives_path_swap(tmp_path: Path) -> None:
    manifest, store = _build_store(tmp_path)
    artifact_ref = manifest["soak"]["raw_telemetry_refs"][0]
    reader = launch_slo_verifier._OfflineEvidenceStore(store)
    pinned = tmp_path / "pinned-original-store"
    try:
        store.rename(pinned)
        store.mkdir()
        (store / ".biocatalyst_launch_slo_offline_store.v1").write_bytes(
            b"biocatalyst_launch_slo_offline_store.v1\n"
        )
        document = reader.artifact(artifact_ref, label="$.race.root")
        assert document["kind"] == "raw_telemetry"
    finally:
        reader.close()


def test_store_parent_descriptor_survives_swap_after_openat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, store = _build_store(tmp_path)
    artifact_ref = manifest["soak"]["raw_telemetry_refs"][0]
    reader = launch_slo_verifier._OfflineEvidenceStore(store)
    real_open = launch_slo_verifier.os.open
    swapped = False
    external = tmp_path / "attacker-artifacts"
    external.mkdir()

    def racing_open(
        path: object,
        flags: int,
        mode: int = 0o777,
        *,
        dir_fd: int | None = None,
    ) -> int:
        nonlocal swapped
        descriptor = real_open(path, flags, mode, dir_fd=dir_fd)
        if path == "artifacts" and dir_fd is not None and not swapped:
            swapped = True
            (store / "artifacts").rename(store / "artifacts-pinned")
            (store / "artifacts").symlink_to(external, target_is_directory=True)
        return descriptor

    monkeypatch.setattr(launch_slo_verifier.os, "open", racing_open)
    try:
        document = reader.artifact(artifact_ref, label="$.race.parent")
        assert document["kind"] == "raw_telemetry"
        assert swapped is True
        assert (store / "artifacts").is_symlink()
    finally:
        reader.close()


def test_drill_and_operation_ids_are_conditionally_bound_to_recovery_kind(
    tmp_path: Path,
) -> None:
    manifest, store = _build_store(tmp_path)
    correction_ref = manifest["soak"]["correction_replay_evidence_refs"][0]
    correction = json.loads(
        (store / "artifacts" / f"{correction_ref['content_sha256']}.json").read_text(
            encoding="utf-8"
        )
    )
    correction["drill_id"] = "biocatalyst_rollback_restore_0123456789abcdef01234567"
    with pytest.raises(ContractValidationError, match="does not match"):
        ContractRegistry(ROOT).validate(correction["contract_id"], correction)

    recovery = json.loads(
        (
            ROOT
            / "data/biocatalyst/fixtures/launch_slo_evidence/biocatalyst_launch_slo_recovery_object.v1.valid.json"
        ).read_text(encoding="utf-8")
    )
    recovery["operation_id"] = "biocatalyst_rollback_restore_0123456789abcdef01234567"
    with pytest.raises(ContractValidationError, match="does not match"):
        ContractRegistry(ROOT).validate(recovery["contract_id"], recovery)


def test_verifier_changes_route_to_biocatalyst_contract_ci_lane() -> None:
    ci_text = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    for path in (
        "engine/sector_intelligence/launch_slo_verifier.py",
        "tests/test_launch_slo_evidence_verifier.py",
        "docs/BIOCATALYST_LAUNCH_SLO_OFFLINE_VERIFIER.md",
    ):
        assert f'- "{path}"' in ci_text

    jobs = yaml.safe_load(
        (ROOT / ".github/ci/legacy-jobs.yml").read_text(encoding="utf-8")
    )["jobs"]
    steps = jobs["biocatalyst-contracts"]["steps"]
    pytest_step = next(step for step in steps if "run" in step and "python -m pytest" in step["run"])
    assert "tests/test_launch_slo_evidence_verifier.py" in pytest_step["run"]


def test_artifact_contract_fixture_is_registered_but_duplicate_opportunity_is_a_verifier_not_schema_problem() -> None:
    valid = json.loads(
        (ROOT / "data/biocatalyst/fixtures/launch_slo_evidence/biocatalyst_launch_slo_evidence_artifact.v1.valid.json").read_text(encoding="utf-8")
    )
    invalid = json.loads(
        (ROOT / "data/biocatalyst/fixtures/launch_slo_evidence/biocatalyst_launch_slo_evidence_artifact.v1.invalid_duplicate_observation.json").read_text(encoding="utf-8")
    )
    registry = ContractRegistry(ROOT)
    assert LAUNCH_SLO_EVIDENCE_ARTIFACT_CONTRACT_ID in registry.contract_ids
    assert LAUNCH_SLO_RECOVERY_OBJECT_CONTRACT_ID in registry.contract_ids
    registry.validate(valid["contract_id"], valid)
    registry.validate(invalid["contract_id"], invalid)
