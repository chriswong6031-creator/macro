"""Contracts for the inert, zero-write B4 read-only operator."""
from __future__ import annotations

import importlib.util
import base64
import json
from copy import deepcopy
from pathlib import Path
import sys
from dataclasses import replace
from types import SimpleNamespace

from jsonschema import Draft202012Validator, FormatChecker
import pytest
import yaml

from engine.fundamental_forensics.attested_query_snapshots import AttestationMaterial
from engine.fundamental_forensics.filing_attestation import build_filing_attestation


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "run_fundamental_forensics_attested_history.py"
RECEIPT_SCHEMA_PATH = ROOT / "contracts" / "fundamental_forensics_attested_history_preflight_receipt.schema.json"


def _operator_module():
    spec = importlib.util.spec_from_file_location("_attested_history_operator_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _b4_helpers():
    path = ROOT / "tests" / "test_fundamental_forensics_attested_query_snapshots.py"
    spec = importlib.util.spec_from_file_location("_operator_b4_fixture_helpers", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validate_receipt(receipt: dict) -> None:
    schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(receipt))
    assert not errors, [error.message for error in errors]


def _packet(*, latest: bool = False, extra: bool = False) -> dict:
    token = "latest.json" if latest else "snapshots/companyfacts/manifest.json"
    result = {
        "schema": "fundamental_forensics.attested_history_operator/v1",
        "base_query_snapshot_id": "ffqs_" + ("a" * 64),
        "source_snapshot_id": "ffsecsrc_" + ("b" * 64),
        "packet": {
            "cik": "0000320193",
            "ixbrl_document_name": "aapl-20240928.htm",
            "filing": {
                "accession": "0000320193-24-000123",
                "manifest_id": "ffsec_manifest_" + ("c" * 64),
                "archive_index_document": {"document_id": "index"},
                "member_states": {"aapl-20240928.htm": {"state": "stored"}},
                "policy_profile": "operator_fixture/v1",
                "policy_version": "1",
            },
            "companyfacts": {
                "manifest_path": token,
                "capture_path": "snapshots/companyfacts/capture.json",
                "response_path": "snapshots/companyfacts/response.json.gz",
                "submissions_recorded_at": "2026-08-03T00:00:00Z",
                "recent_submissions": {
                    "source_name": "recent",
                    "receipt_path": "submissions/recent.receipt.json",
                    "object_path": "submissions/recent.json.gz",
                    "is_older": False,
                },
                "older_submissions": [],
                "conversion_limits": {
                    "max_occurrences": 250000,
                    "max_payload_bytes": 67108864,
                    "max_total_input_bytes": 134217728,
                    "max_submission_rows": 100000,
                    "max_older_submissions_files": 128,
                    "max_revision_evidence": 10000,
                    "max_revision_evidence_bytes": 4194304,
                },
            },
        },
    }
    if extra:
        result["unsafe"] = True
    return result


def _fixture_inputs(operator, monkeypatch, tmp_path):
    helper = _b4_helpers()
    store, base, material, conversion, _expected = helper._material(monkeypatch, tmp_path)
    inputs = operator.MaterializedOperatorInputs(
        base_snapshot=base,
        package=material.package,
        extraction=material.extraction,
        attestation=material.attestation,
        material=material,
        conversion=conversion,
    )
    return store, inputs


def _fixture_spec(operator, inputs):
    spec = operator.spec_from_dict(_packet())
    return replace(
        spec,
        base_query_snapshot_id=inputs.base_snapshot.snapshot_id,
        source_snapshot_id=inputs.material.authority.snapshot_id,
    )


def test_packet_is_exact_and_refuses_latest_or_unknown_fields():
    operator = _operator_module()
    spec = operator.spec_from_dict(_packet())
    assert spec.base_query_snapshot_id.startswith("ffqs_")
    assert spec.packet.recent_submissions.source_name == "recent"
    with pytest.raises(operator.OperatorPreflightError):
        operator.spec_from_dict(_packet(latest=True))
    with pytest.raises(operator.OperatorPreflightError):
        operator.spec_from_dict(_packet(extra=True))


def test_packet_file_read_is_fd_bound_and_rejects_symlink_growth_or_midread_change(monkeypatch, tmp_path):
    operator = _operator_module()
    packet = tmp_path / "packet.json"
    packet.write_text("{}", encoding="utf-8")
    link = tmp_path / "packet-link.json"
    link.symlink_to(packet)
    with pytest.raises(operator.OperatorPreflightError, match="opened safely"):
        operator.load_operator_spec(link)

    monkeypatch.setattr(
        Path,
        "read_bytes",
        lambda _path: pytest.fail("packet ingress must not use Path.read_bytes"),
    )
    with pytest.raises(operator.OperatorPreflightError, match="unsupported"):
        operator.load_operator_spec(packet)

    original_fstat = operator.os.fstat
    calls = 0

    def changed_after_read(descriptor):
        nonlocal calls
        calls += 1
        observed = original_fstat(descriptor)
        if calls == 2:
            fields = list(observed)
            fields[6] += 1  # st_size: emulate a concurrent writer after the bounded read.
            return operator.os.stat_result(fields)
        return observed

    monkeypatch.setattr(operator.os, "fstat", changed_after_read)
    with pytest.raises(operator.OperatorPreflightError, match="changed"):
        operator.load_operator_spec(packet)

    oversized = tmp_path / "oversized.json"
    oversized.write_bytes(b"x" * (operator.MAX_SPEC_BYTES + 1))
    with pytest.raises(operator.OperatorPreflightError, match="bounded regular"):
        operator.load_operator_spec(oversized)


def test_read_only_store_blocks_writes_and_discovery():
    operator = _operator_module()

    class Backing:
        def get_bytes(self, key):
            return b"bytes"

        def get_bytes_strict(self, key):
            return b"bytes"

        def get_bytes_strict_bounded(self, key, maximum_bytes):
            return b"bytes"

        def put_bytes(self, key, data, content_type="application/octet-stream"):
            raise AssertionError("backing write must not be reached")

        def put_bytes_strict_conditional(
            self, key, data, *, expected_version, content_type="application/octet-stream"
        ):
            raise AssertionError("backing conditional write must not be reached")

        def list_prefix(self, prefix):
            return []

        def exists(self, key):
            return False

        def upload_time(self, key):
            return None

        def delete(self, key):
            raise AssertionError("backing delete must not be reached")

    store = operator.ReadOnlyStrictStore(Backing())
    assert store.get_bytes_strict_bounded("immutable/key", 128) == b"bytes"
    with pytest.raises(operator.OperatorPreflightError, match="unbounded"):
        store.get_bytes_strict("immutable/key")
    with pytest.raises(operator.OperatorPreflightError, match="unbounded"):
        store.get_bytes("immutable/key")
    with pytest.raises(operator.ReadOnlyWriteAttempt) as captured:
        store.put_bytes("immutable/key", b"never")
    conditional_store = operator.ReadOnlyStrictStore(Backing())
    with pytest.raises(operator.ReadOnlyWriteAttempt) as conditional:
        conditional_store.put_bytes_strict_conditional(
            "immutable/key",
            b"never",
            expected_version=None,
        )
    with pytest.raises(operator.OperatorPreflightError):
        store.list_prefix("fundamental_forensics/")
    with pytest.raises(operator.OperatorPreflightError):
        store.exists("fundamental_forensics/object")
    with pytest.raises(operator.OperatorPreflightError):
        store.upload_time("fundamental_forensics/object")
    delete_store = operator.ReadOnlyStrictStore(Backing())
    with pytest.raises(operator.ReadOnlyWriteAttempt) as deletion:
        delete_store.delete("fundamental_forensics/object")
    assert captured.value.write_attempts == 1
    assert conditional.value.write_attempts == 1
    assert deletion.value.write_attempts == 1
    assert store.write_attempts == 1
    failure = operator.failed_receipt(
        observed_at="2026-08-03T00:00:00Z",
        phase="materialization",
        error=conditional.value,
        write_attempts=conditional.value.write_attempts,
    )
    assert failure["publication"]["storage_write_attempts"] == 1
    assert failure["failure"]["phase"] == "materialization"
    _validate_receipt(failure)


def test_production_store_refuses_to_fall_back_to_shared_research_credentials(monkeypatch):
    operator = _operator_module()
    for name in (
        "FF_ATTESTED_R2_READONLY_ENDPOINT",
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID",
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY",
        "FF_ATTESTED_R2_READONLY_BUCKET",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_RESEARCH_BUCKET", "shared-bucket-must-not-be-used")
    with pytest.raises(operator.OperatorPreflightError, match="dedicated read-only"):
        operator.build_readonly_operator_store()


def test_production_store_reports_a_value_free_credential_reason(monkeypatch):
    operator = _operator_module()
    invalid_endpoint = "0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
    values = {
        "FF_ATTESTED_R2_READONLY_ENDPOINT": invalid_endpoint,
        "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID": "A" * 32,
        "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY": "reader-parent-secret",
        "FF_ATTESTED_R2_READONLY_BUCKET": "attested-history",
    }
    for name, value in values.items():
        monkeypatch.setenv(name, value)

    with pytest.raises(operator.OperatorPreflightError, match="R2 endpoint is invalid") as caught:
        operator.build_readonly_operator_store()

    assert invalid_endpoint not in str(caught.value)


def test_production_packet_captures_once_then_binds_that_exact_byte_packet_to_head_and_index(monkeypatch, tmp_path):
    operator = _operator_module()
    packet = tmp_path / "arbitrary.json"
    packet.write_text("{}", encoding="utf-8")
    with pytest.raises(operator.OperatorPreflightError, match="canonical tracked"):
        operator._production_packet_bytes(packet)

    repository = tmp_path / "repository"
    canonical = repository / operator.CANONICAL_OPERATOR_PACKET_RELATIVE_PATH
    canonical.parent.mkdir(parents=True)
    original = json.dumps(_packet(), sort_keys=True, separators=(",", ":")).encode("utf-8")
    canonical.write_bytes(original)
    monkeypatch.setattr(operator, "REPOSITORY_ROOT", repository)
    git_calls: list[tuple[Path, str, int]] = []

    def matching_blob(*, root: Path, object_name: str, maximum_bytes: int) -> bytes:
        git_calls.append((root, object_name, maximum_bytes))
        return original

    real_packet_reader = operator._read_regular_file_bounded

    def capture_then_replace(location: Path, *, maximum_bytes: int) -> bytes:
        captured = real_packet_reader(location, maximum_bytes=maximum_bytes)
        canonical.write_bytes(b'{"tampered_after_capture":true}')
        return captured

    monkeypatch.setattr(operator, "_read_git_blob_bounded", matching_blob)
    monkeypatch.setattr(operator, "_read_regular_file_bounded", capture_then_replace)
    spec = operator.load_production_operator_spec(canonical)
    assert spec.base_query_snapshot_id == _packet()["base_query_snapshot_id"]
    assert canonical.read_bytes() != original
    assert git_calls == [
        (
            repository,
            f"HEAD:{operator.CANONICAL_OPERATOR_PACKET_RELATIVE_PATH.as_posix()}",
            operator.MAX_SPEC_BYTES,
        ),
        (
            repository,
            f":{operator.CANONICAL_OPERATOR_PACKET_RELATIVE_PATH.as_posix()}",
            operator.MAX_SPEC_BYTES,
        ),
    ]

    monkeypatch.setattr(operator, "_read_regular_file_bounded", real_packet_reader)
    canonical.write_bytes(original)
    monkeypatch.setattr(
        operator,
        "_read_git_blob_bounded",
        lambda **kwargs: original if kwargs["object_name"].startswith("HEAD:") else b"different-index-blob",
    )
    with pytest.raises(operator.OperatorPreflightError, match="exactly match HEAD and index"):
        operator.load_production_operator_spec(canonical)


def test_production_rejects_arbitrary_packet_but_local_mode_allows_hermetic_packet(tmp_path, capsys):
    operator = _operator_module()
    packet = tmp_path / "arbitrary.json"
    packet.write_text("{}", encoding="utf-8")

    production_output = tmp_path / "production-output"
    assert operator.main(
        [
            "--config",
            str(packet),
            "--output-dir",
            str(production_output),
            "--operator-verification-observed-at",
            "2026-08-03T00:00:00Z",
        ]
    ) == 1
    production_receipt = json.loads(
        (production_output / "attested_history_preflight_receipt.json").read_text(encoding="utf-8")
    )
    assert production_receipt["failure"] == {
        "phase": "packet_admission",
        "error_type": "OperatorPreflightError",
    }
    assert str(packet).encode() not in (production_output / "attested_history_preflight_receipt.json").read_bytes()
    assert "ffqs_" not in capsys.readouterr().out
    _validate_receipt(production_receipt)

    local_output = tmp_path / "local-output"
    assert operator.main(
        [
            "--config",
            str(packet),
            "--output-dir",
            str(local_output),
            "--operator-verification-observed-at",
            "2026-08-03T00:00:00Z",
            "--local-store",
            str(tmp_path / "local-store"),
        ]
    ) == 1
    local_receipt = json.loads(
        (local_output / "attested_history_preflight_receipt.json").read_text(encoding="utf-8")
    )
    assert local_receipt["failure"]["phase"] == "packet_read"
    _validate_receipt(local_receipt)


def test_local_source_store_and_private_artifact_cannot_overlap(tmp_path):
    operator = _operator_module()
    local_store = tmp_path / "source-store"
    assert operator.main(
        [
            "--config",
            str(tmp_path / "does-not-matter.json"),
            "--output-dir",
            str(local_store),
            "--operator-verification-observed-at",
            "2026-08-03T00:00:00Z",
            "--local-store",
            str(local_store),
        ]
    ) == 2
    assert not local_store.exists()
    with pytest.raises(operator.OperatorPreflightError, match="overlap"):
        operator._reject_local_artifact_overlap(
            output_dir=tmp_path,
            local_store=tmp_path / "nested-source-store",
        )


def test_preflight_prepares_only_in_memory_and_proves_zero_writes(monkeypatch, tmp_path):
    operator = _operator_module()
    store, inputs = _fixture_inputs(operator, monkeypatch, tmp_path)
    spec = _fixture_spec(operator, inputs)
    writes: list[tuple] = []

    def forbidden_write(*args, **kwargs):
        writes.append((args, kwargs))
        raise AssertionError("operator attempted a backing-store write")

    monkeypatch.setattr(store, "put_bytes", forbidden_write)
    monkeypatch.setattr(
        operator,
        "materialize_operator_inputs",
        lambda *, spec, store, observed_at: inputs,
    )
    receipt = operator.run_readonly_preflight(
        spec=spec,
        store=store,
        operator_verification_observed_at="2026-08-03T00:00:00Z",
    )
    assert receipt["status"] == "prepared"
    assert receipt["candidate"]["prepared_in_memory"] is True
    assert receipt["publication"] == {
        "publication_performed": False,
        "pointer_advanced": False,
        "immutable_objects_written": False,
        "storage_write_attempts": 0,
    }
    assert writes == []
    serialized = operator._receipt_bytes(receipt)
    assert len(serialized) <= operator.MAX_RECEIPT_BYTES
    assert b"storage_key" not in serialized
    assert b"R2_RESEARCH" not in serialized
    _validate_receipt(receipt)


def test_operator_runs_the_actual_b4d_partial_coverage_planner_and_projects_its_real_rejection_code(monkeypatch, tmp_path):
    operator = _operator_module()
    helper = _b4_helpers()
    store, base, material, conversion, _prepared = helper._mixed_coverage_prepared(monkeypatch, tmp_path)
    inputs = operator.MaterializedOperatorInputs(
        base_snapshot=base,
        package=material.package,
        extraction=material.extraction,
        attestation=material.attestation,
        material=material,
        conversion=conversion,
    )
    spec = _fixture_spec(operator, inputs)
    phases: list[str] = []
    monkeypatch.setattr(
        operator,
        "materialize_operator_inputs",
        lambda *, spec, store, observed_at: inputs,
    )
    receipt = operator.run_readonly_preflight(
        spec=spec,
        store=store,
        operator_verification_observed_at="2026-08-03T00:00:00Z",
        phase_callback=phases.append,
    )
    assert phases == ["materialization", "binding_plan", "candidate_prepare"]
    assert receipt["status"] == "prepared"
    assert receipt["binding_plan"]["rejection_reason_counts"] == {
        "selected_occurrence_not_in_companyfacts_conversion": 1
    }
    assert {
        item["status"] for item in receipt["binding_plan"]["coverage"]
    } == {
        "all_leaves_attested",
        "not_attested",
        "not_evaluable",
        "partially_attested",
    }
    _validate_receipt(receipt)


def test_zero_binding_is_a_successful_non_publishable_diagnostic(monkeypatch, tmp_path):
    operator = _operator_module()
    store, inputs = _fixture_inputs(operator, monkeypatch, tmp_path)
    spec = _fixture_spec(operator, inputs)
    monkeypatch.setattr(
        operator,
        "materialize_operator_inputs",
        lambda *, spec, store, observed_at: inputs,
    )
    monkeypatch.setattr(
        operator,
        "enumerate_attested_binding_candidates",
        lambda **_kwargs: operator.AttestedBindingReport(
            base_snapshot_id=inputs.base_snapshot.snapshot_id,
            companyfacts_conversion_receipt_id=inputs.conversion.receipt.receipt_id,
            attestation_ids=(inputs.attestation.attestation_id,),
            leaves=(),
            bindings=(),
            coverage=(),
        ),
    )
    receipt = operator.run_readonly_preflight(
        spec=spec,
        store=store,
        operator_verification_observed_at="2026-08-03T00:00:00Z",
    )
    assert receipt["status"] == "non_publishable"
    assert receipt["candidate"] == {
        "prepared_in_memory": False,
        "candidate_snapshot_id": None,
        "candidate_published_at_is_not_an_actual_publication": False,
    }
    assert receipt["publication"]["storage_write_attempts"] == 0
    assert receipt["binding_plan"]["rejection_reason_counts"] == {}
    _validate_receipt(receipt)


def test_rejection_reason_counts_are_bounded_and_receipt_schema_rejects_unsafe_summary(monkeypatch, tmp_path):
    operator = _operator_module()
    report = SimpleNamespace(
        leaves=tuple(
            SimpleNamespace(rejection_reasons=(reason,))
            for reason in sorted(operator._REJECTION_REASON_CODES)
        )
    )
    assert operator._rejection_reason_counts(report) == {
        reason: 1 for reason in sorted(operator._REJECTION_REASON_CODES)
    }
    monkeypatch.setattr(operator, "MAX_RECEIPT_REJECTION_REASON_COUNT", 1)
    excessive = SimpleNamespace(
        leaves=(
            SimpleNamespace(rejection_reasons=("no_exact_b3_match",)),
            SimpleNamespace(rejection_reasons=("no_exact_b3_match",)),
        )
    )
    with pytest.raises(operator.OperatorPreflightError, match="reason count"):
        operator._rejection_reason_counts(excessive)

    store, inputs = _fixture_inputs(operator, monkeypatch, tmp_path)
    spec = _fixture_spec(operator, inputs)
    monkeypatch.setattr(
        operator,
        "materialize_operator_inputs",
        lambda *, spec, store, observed_at: inputs,
    )
    receipt = operator.run_readonly_preflight(
        spec=spec,
        store=store,
        operator_verification_observed_at="2026-08-03T00:00:00Z",
    )
    poisoned = deepcopy(receipt)
    poisoned["binding_plan"]["rejection_reason_counts"] = {"bad-reason": 1}
    schema = json.loads(RECEIPT_SCHEMA_PATH.read_text(encoding="utf-8"))
    assert list(Draft202012Validator(schema).iter_errors(poisoned))


def test_cli_failure_writes_a_redacted_bounded_receipt(tmp_path):
    operator = _operator_module()
    config = tmp_path / "broken.json"
    config.write_text("{}", encoding="utf-8")
    output = tmp_path / "private-artifact"
    assert operator.main(
        [
            "--config",
            str(config),
            "--output-dir",
            str(output),
            "--operator-verification-observed-at",
            "2026-08-03T00:00:00Z",
            "--local-store",
            str(tmp_path / "store"),
        ]
    ) == 1
    payload = (output / "attested_history_preflight_receipt.json").read_bytes()
    receipt = json.loads(payload)
    assert receipt["status"] == "failed"
    assert receipt["failure"] == {
        "phase": "packet_read",
        "error_type": "OperatorPreflightError",
    }
    assert str(config).encode() not in payload
    assert b"operator packet has unsupported" not in payload
    assert len(payload) <= operator.MAX_RECEIPT_BYTES
    _validate_receipt(receipt)


def test_cli_redacts_a_receipt_write_failure_with_its_own_stable_phase(monkeypatch, tmp_path):
    operator = _operator_module()
    attempted_receipts: list[dict] = []

    monkeypatch.setattr(operator, "load_operator_spec", lambda _path: object())
    monkeypatch.setattr(operator, "build_readonly_operator_store", lambda *, local_dir=None: object())
    monkeypatch.setattr(operator, "run_readonly_preflight", lambda **_kwargs: {"private": "receipt"})

    def fail_once_then_capture(_output_dir, receipt):
        attempted_receipts.append(dict(receipt))
        if len(attempted_receipts) == 1:
            raise OSError("private output failure")
        return tmp_path / "captured-failure-receipt.json"

    monkeypatch.setattr(operator, "write_private_receipt", fail_once_then_capture)
    assert operator.main(
        [
            "--config",
            str(tmp_path / "hermetic.json"),
            "--output-dir",
            str(tmp_path / "private-artifact"),
            "--operator-verification-observed-at",
            "2026-08-03T00:00:00Z",
            "--local-store",
            str(tmp_path / "source-store"),
        ]
    ) == 1
    assert attempted_receipts[1]["failure"] == {
        "phase": "receipt_write",
        "error_type": "OSError",
    }
    _validate_receipt(attempted_receipts[1])


def test_success_logs_never_emit_the_private_receipt_or_snapshot_ids(monkeypatch, tmp_path, capsys):
    operator = _operator_module()
    monkeypatch.setattr(operator, "load_operator_spec", lambda _path: object())
    monkeypatch.setattr(operator, "build_readonly_operator_store", lambda *, local_dir=None: object())
    monkeypatch.setattr(
        operator,
        "run_readonly_preflight",
        lambda **_kwargs: {"private_snapshot_id": "ffqs_" + "a" * 64},
    )
    output = tmp_path / "private-artifact"
    assert operator.main(
        [
            "--config",
            str(tmp_path / "hermetic.json"),
            "--output-dir",
            str(output),
            "--operator-verification-observed-at",
            "2026-08-03T00:00:00Z",
            "--local-store",
            str(tmp_path / "source-store"),
        ]
    ) == 0
    stdout = capsys.readouterr().out
    assert "ffqs_" not in stdout
    assert "private_snapshot_id" not in stdout
    assert "completed" in stdout


def test_contracts_and_workflow_are_inert_and_no_production_packet_exists():
    for name in (
        "fundamental_forensics_attested_history_operator.schema.json",
        "fundamental_forensics_attested_history_preflight_receipt.schema.json",
    ):
        payload = json.loads((ROOT / "contracts" / name).read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    workflow = (ROOT / ".github" / "workflows" / "attested-history-operator.yml").read_text(
        encoding="utf-8"
    )
    assert "enable_readonly_preflight" in workflow
    assert "default: false" in workflow
    assert "github.ref == 'refs/heads/main'" in workflow
    parsed_workflow = yaml.load(workflow, Loader=yaml.BaseLoader)
    job = parsed_workflow["jobs"]["preflight"]
    assert "environment" not in job
    assert "env" not in job
    secret_steps = [
        step
        for step in job["steps"]
        if "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY" in step.get("env", {})
    ]
    assert len(secret_steps) == 1
    assert secret_steps[0]["name"] == "sealed read-only preflight"
    assert "\n  schedule:" not in workflow
    assert "contents: read" in workflow
    assert "publish_attested_query_snapshot" not in workflow
    assert "git push" not in workflow
    assert "FF_ATTESTED_R2_READONLY_ENDPOINT: ${{ secrets.R2_ATTESTED_HISTORY_ENDPOINT }}" in workflow
    assert "FF_ATTESTED_R2_READONLY_ACCESS_KEY_ID: ${{ secrets.R2_ATTESTED_HISTORY_READONLY_ACCESS_KEY_ID }}" in workflow
    assert "FF_ATTESTED_R2_READONLY_SECRET_ACCESS_KEY: ${{ secrets.R2_ATTESTED_HISTORY_READONLY_SECRET_ACCESS_KEY }}" in workflow
    assert "FF_ATTESTED_R2_READONLY_BUCKET: ${{ secrets.R2_ATTESTED_HISTORY_BUCKET }}" in workflow
    assert "R2_RESEARCH_" not in workflow
    assert "requirements.txt" not in workflow
    assert "--require-hashes" in workflow
    assert "attested-history-macos-arm64-py312.lock" in workflow
    assert 'git show "$GITHUB_SHA:requirements/attested-history-macos-arm64-py312.lock"' in workflow
    assert "persist-credentials: false" in workflow
    assert "verify exact reviewed execution tree" in workflow
    assert 'git diff --quiet "$GITHUB_SHA" -- .' in workflow
    assert "git ls-files --others --ignored --exclude-standard -- ." in workflow
    assert "git archive --format=tar" in workflow
    assert '"$GITHUB_SHA" -- "${execution_paths[@]}"' in workflow
    assert "engine/fundamental_forensics" in workflow
    assert "config/fundamental_forensics" in workflow
    assert 'tar -xf "$SOURCE_ARCHIVE" -C "$EXEC_ROOT"' in workflow
    assert 'cd "$EXEC_ROOT"' in workflow
    assert "attested_history_preflight_bundle_receipt.json" in workflow
    assert "${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}" in workflow
    assert ".replace(microsecond=0)" not in workflow
    success_upload = next(
        step
        for step in job["steps"]
        if step.get("name") == "upload review-only successful preflight receipt"
    )
    assert "if" not in success_upload
    assert "if-no-files-found: error" in workflow
    assert "review-only" in workflow
    assert workflow.count("attested_history_preflight_bundle_receipt.json") >= 3
    assert not (ROOT / "config" / "fundamental_forensics" / "attested_history_operator.v1.json").exists()
    source = SCRIPT_PATH.read_text(encoding="utf-8")
    assert "publish_attested_query_snapshot(" not in source
    assert "publish_query_snapshot(" not in source
    assert "print(json.dumps(receipt" not in source


def test_r2_temporary_credentials_match_cloudflare_local_signing_contract():
    operator = _operator_module()
    credentials = operator.mint_r2_temporary_credentials(
        endpoint="https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        parent_access_key_id="ABCDEF0123456789ABCDEF0123456789",
        parent_secret_access_key="known-parent-secret",
        bucket="attested-history",
        scope="object-read-only",
        actions=("GetObject", "HeadObject"),
        ttl_seconds=900,
        issued_at=1_800_000_000,
    )
    assert credentials.access_key_id == "ABCDEF0123456789ABCDEF0123456789"
    assert credentials.expires_at == 1_800_000_900
    decoded = base64.b64decode(credentials.session_token).decode("ascii")
    assert decoded.startswith("jwt/")
    signed_jwt = decoded.removeprefix("jwt/")
    header_segment, payload_segment, _signature = signed_jwt.split(".")

    def decode_segment(value: str) -> dict:
        padding = "=" * (-len(value) % 4)
        return json.loads(base64.urlsafe_b64decode(value + padding))

    assert decode_segment(header_segment) == {"alg": "HS256", "typ": "JWT"}
    assert decode_segment(payload_segment) == {
        "actions": ["GetObject", "HeadObject"],
        "aud": "0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        "bucket": "attested-history",
        "exp": 1_800_000_900,
        "iat": 1_800_000_000,
        "iss": "ABCDEF0123456789ABCDEF0123456789",
        "paths": {
            "objectPaths": [],
            "prefixPaths": ["fundamental_forensics/"],
        },
        "scope": "object-read-only",
        "sub": "0123456789abcdef0123456789abcdef",
    }
    assert credentials.secret_access_key == operator.sha256(
        signed_jwt.encode("ascii")
    ).hexdigest()
    assert credentials.secret_access_key == "f7cf79a084d44ca81dd54c9cf805f52def622dd5eb3525879ff700bf8c578890"
    assert credentials.session_token == (
        "and0L2V5SmhiR2NpT2lKSVV6STFOaUlzSW5SNWNDSTZJa3BYVkNKOS5leUpoWTNScGIyNXpJanBiSWtk"
        "bGRFOWlhbVZqZENJc0lraGxZV1JQWW1wbFkzUWlYU3dpWVhWa0lqb2lNREV5TXpRMU5qYzRPV0ZpWTJS"
        "bFpqQXhNak0wTlRZM09EbGhZbU5rWldZdWNqSXVZMnh2ZFdSbWJHRnlaWE4wYjNKaFoyVXVZMjl0SWl3"
        "aVluVmphMlYwSWpvaVlYUjBaWE4wWldRdGFHbHpkRzl5ZVNJc0ltVjRjQ0k2TVRnd01EQXdNRGt3TUN3"
        "aWFXRjBJam94T0RBd01EQXdNREF3TENKcGMzTWlPaUpCUWtORVJVWXdNVEl6TkRVMk56ZzVRVUpEUkVWR"
        "01ERXlNelExTmpjNE9TSXNJbkJoZEdoeklqcDdJbTlpYW1WamRGQmhkR2h6SWpwYlhTd2ljSEpsWm1sNF"
        "VHRjBhSE1pT2xzaVpuVnVaR0Z0Wlc1MFlXeGZabTl5Wlc1emFXTnpMeUpkZlN3aWMyTnZjR1VpT2lKdll"
        "tcGxZM1F0Y21WaFpDMXZibXg1SWl3aWMzVmlJam9pTURFeU16UTFOamM0T1dGaVkyUmxaakF4TWpNME5U"
        "WTNPRGxoWW1Oa1pXWWlmUS41RE1YU1NscTJNZG1LSmduX1k5T2lyQ3BlZVIyaTdST0J6T21SV2ZtWHVV"
    )
    writer = operator.mint_r2_temporary_credentials(
        endpoint="https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        parent_access_key_id="ABCDEF0123456789ABCDEF0123456789",
        parent_secret_access_key="known-parent-secret",
        bucket="attested-history",
        scope="object-read-write",
        actions=("GetObject", "HeadObject", "PutObject"),
        ttl_seconds=1_800,
        issued_at=1_800_000_000,
    )
    writer_jwt = base64.b64decode(writer.session_token).decode("ascii").removeprefix("jwt/")
    writer_payload = decode_segment(writer_jwt.split(".")[1])
    assert writer_payload["actions"] == ["GetObject", "HeadObject", "PutObject"]
    assert writer_payload["paths"] == {
        "objectPaths": [],
        "prefixPaths": ["fundamental_forensics/"],
    }
    assert writer_payload["exp"] - writer_payload["iat"] == 1_800


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"ttl_seconds": 1801}, "TTL"),
        ({"actions": ("GetObject", "HeadObject", "PutObject")}, "exact role"),
        ({"prefix": "other/"}, "prefix"),
        ({"endpoint": "https://example.com"}, "host"),
        ({"endpoint": "http://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"}, "endpoint"),
    ],
)
def test_r2_temporary_credentials_fail_closed_on_scope_expansion(override, message):
    operator = _operator_module()
    values = {
        "endpoint": "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        "parent_access_key_id": "ABCDEF0123456789ABCDEF0123456789",
        "parent_secret_access_key": "known-parent-secret",
        "bucket": "attested-history",
        "scope": "object-read-only",
        "actions": ("GetObject", "HeadObject"),
        "ttl_seconds": 900,
        "issued_at": 1_800_000_000,
    }
    values.update(override)
    with pytest.raises(operator.R2TemporaryCredentialError, match=message):
        operator.mint_r2_temporary_credentials(**values)


def test_operator_packet_bytes_enforce_exact_two_mib_boundary():
    operator = _operator_module()
    with pytest.raises(operator.OperatorPreflightError, match="valid UTF-8 JSON"):
        operator.operator_spec_from_bytes(b" " * operator.MAX_SPEC_BYTES)
    with pytest.raises(operator.OperatorPreflightError, match="outside the bounded range"):
        operator.operator_spec_from_bytes(b" " * (operator.MAX_SPEC_BYTES + 1))
