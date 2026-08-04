"""Operator boundaries for isolated share-count R2 conformance."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "probe_capital_structure_share_count_r2.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "capital-share-count-r2-conformance.yml"


def _operator_module():
    spec = importlib.util.spec_from_file_location("_share_count_r2_operator_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _workflow() -> dict:
    # PyYAML treats YAML 1.1 ``on`` as a boolean, so parse then normalize it.
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    if True in parsed:
        parsed["on"] = parsed.pop(True)
    return parsed


def _set_dedicated_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "R2_SHARE_COUNT_CONFORMANCE_ENDPOINT",
        "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
    )
    monkeypatch.setenv(
        "R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef"
    )
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_BUCKET", "share-count-conformance")
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID", "A" * 32)
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY", "B" * 48)


def _set_github_env(monkeypatch) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "chriswong6031-creator/macro")
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "chriswong6031-creator/macro/.github/workflows/capital-share-count-r2-conformance.yml@refs/heads/main",
    )
    monkeypatch.setenv("GITHUB_RUN_ID", "123")
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_EVENT_NAME", "workflow_dispatch")
    monkeypatch.setenv("GITHUB_ACTOR", "operator")


def _set_execution_env(monkeypatch) -> None:
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_R2_CONFORMANCE_SOURCE_ARCHIVE_SHA256", "b" * 64
    )
    monkeypatch.setenv(
        "CAPITAL_STRUCTURE_R2_CONFORMANCE_DEPENDENCY_LOCK_SHA256", "c" * 64
    )


def test_workflow_is_manual_main_only_protected_and_has_no_write_permission():
    workflow = _workflow()
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"] == {
        "run_conformance": {
            "description": "Explicitly run the isolated conditional R2 conformance witness",
            "required": True,
            "default": False,
            "type": "boolean",
        }
    }
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {
        "group": "capital-share-count-r2-conformance",
        "cancel-in-progress": False,
    }
    job = workflow["jobs"]["conformance"]
    assert job["if"] == "${{ inputs.run_conformance == true && github.ref == 'refs/heads/main' }}"
    assert job["environment"] == "capital-share-count-r2-conformance"
    assert job["timeout-minutes"] == 5
    checkout = job["steps"][0]
    assert checkout["with"]["persist-credentials"] is False
    rendered = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "id-token:" not in rendered
    assert "contents: write" not in rendered
    assert "git push" not in rendered
    assert "workflow_dispatch" in rendered and "schedule:" not in rendered and "push:" not in rendered


def test_workflow_exposes_only_the_five_dedicated_environment_secrets_and_artifacts_receipt_on_failure():
    workflow = _workflow()
    job = workflow["jobs"]["conformance"]
    probe = next(
        step
        for step in job["steps"]
        if step.get("name") == "run isolated conditional conformance probe"
    )
    assert set(probe["env"]) == {
        "R2_SHARE_COUNT_CONFORMANCE_ENDPOINT",
        "R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID",
        "R2_SHARE_COUNT_CONFORMANCE_BUCKET",
        "R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID",
        "R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY",
        "CAPITAL_STRUCTURE_R2_CONFORMANCE_SOURCE_ARCHIVE_SHA256",
        "CAPITAL_STRUCTURE_R2_CONFORMANCE_DEPENDENCY_LOCK_SHA256",
    }
    upload = job["steps"][-1]
    assert upload["if"] == "${{ always() }}"
    assert "capital_structure_share_count_r2_conformance_receipt.json" in upload["with"]["path"]
    assert "review-only" in upload["name"]
    rendered = WORKFLOW_PATH.read_text(encoding="utf-8")
    assert "R2_CAPITAL_STRUCTURE" not in rendered
    assert "R2_RESEARCH" not in rendered
    assert "R2_ENDPOINT" not in rendered
    assert "capital-share-r2-conformance-macos-arm64-py312.lock" in rendered
    assert "git archive" in rendered
    assert "archive_sha256" in rendered
    assert "contracts/capital_structure_share_count_r2_conformance_receipt.schema.json" in rendered
    assert "engine/capital_structure/share_count_r2_conformance.py" in rendered
    assert ".github/workflows/capital-share-count-r2-conformance.yml" in rendered
    assert "retention-days: 90" in rendered
    assert "smoke-test reviewed execution tree without credentials" in rendered
    assert '"$VENV/bin/python" -E -s -m scripts.probe' in rendered
    assert '"$VENV/bin/python" -m pip --isolated install' in rendered

    lock = (
        ROOT / "requirements" / "capital-share-r2-conformance-macos-arm64-py312.lock"
    ).read_text(encoding="utf-8")
    assert "boto3==" in lock and "botocore==" in lock
    assert "numpy==" not in lock and "pandas==" not in lock and "pyarrow==" not in lock


def test_config_requires_exact_dedicated_values_and_fails_closed_on_cloudflare_binding(monkeypatch):
    operator = _operator_module()
    for name in operator._REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_RESEARCH_BUCKET", "must-not-be-read")
    with pytest.raises(operator.ShareCountR2ConformanceError, match="dedicated"):
        operator.read_conformance_config()

    _set_dedicated_env(monkeypatch)
    config = operator.read_conformance_config()
    assert config.endpoint == "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com"
    monkeypatch.setenv(
        "R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID", "fedcba9876543210fedcba9876543210"
    )
    with pytest.raises(operator.ShareCountR2ConformanceError, match="does not bind"):
        operator.read_conformance_config()

    for jurisdiction in ("eu.", "fedramp."):
        _set_dedicated_env(monkeypatch)
        monkeypatch.setenv(
            "R2_SHARE_COUNT_CONFORMANCE_ENDPOINT",
            f"https://0123456789abcdef0123456789abcdef.{jurisdiction}r2.cloudflarestorage.com",
        )
        assert operator.read_conformance_config().endpoint.endswith(
            f".{jurisdiction}r2.cloudflarestorage.com"
        )

    _set_dedicated_env(monkeypatch)
    for endpoint in (
        "http://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com:443",
        "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com/not-a-root",
        "https://operator@0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
    ):
        monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_ENDPOINT", endpoint)
        with pytest.raises(operator.ShareCountR2ConformanceError, match="endpoint"):
            operator.read_conformance_config()


def test_sdk_preflight_requires_the_exact_conditional_operation_members():
    operator = _operator_module()

    class Shape:
        def __init__(self, members):
            self.members = members

    class ServiceModel:
        def operation_model(self, name):
            members = {
                "PutObject": {"IfMatch": object(), "IfNoneMatch": object()},
                "GetObject": {"IfMatch": object()},
            }[name]
            return type("Operation", (), {"input_shape": Shape(members)})()

    client = type("Client", (), {"meta": type("Meta", (), {"service_model": ServiceModel()})()})()
    operator._preflight_r2_sdk_models(client)

    class MissingGetIfMatch(ServiceModel):
        def operation_model(self, name):
            members = {"IfMatch": object(), "IfNoneMatch": object()} if name == "PutObject" else {}
            return type("Operation", (), {"input_shape": Shape(members)})()

    missing = type("Client", (), {"meta": type("Meta", (), {"service_model": MissingGetIfMatch()})()})()
    with pytest.raises(operator.ShareCountR2ConformanceError, match="lacks required"):
        operator._preflight_r2_sdk_models(missing)


def test_core_receives_only_exact_fresh_key_capabilities_and_requires_a_pass_result(monkeypatch):
    operator = _operator_module()

    class Backing:
        def head_object(self, **kwargs):
            return {"Key": kwargs["Key"]}

        def get_object(self, **kwargs):
            return {"Key": kwargs["Key"]}

        def put_object(self, **kwargs):
            return {"Key": kwargs["Key"]}

    key = "capital_structure/share_counts/conformance/v1/" + "a" * 32 + ".json"
    capability = operator.ConformanceR2ObjectClient(Backing(), bucket="bucket", key=key)
    assert capability.head_object(Bucket="bucket", Key=key)["Key"] == key
    assert capability.get_object(
        Bucket="bucket", Key=key, Range="bytes=0-0", IfMatch='"etag"'
    )["Key"] == key
    assert capability.put_object(
        Bucket="bucket", Key=key, Body=b"conditional-only",
        ContentType="application/json", IfNoneMatch="*",
    )["Key"] == key
    with pytest.raises(operator.ShareCountR2ConformanceError, match="parameters"):
        capability.put_object(
            Bucket="bucket", Key=key, Body=b"unconditional",
            ContentType="application/json",
        )
    with pytest.raises(operator.ShareCountR2ConformanceError, match="parameters"):
        capability.head_object(Bucket="bucket", Key=key, VersionId="escape")
    with pytest.raises(operator.ShareCountR2ConformanceError, match="not admitted"):
        capability.list_objects_v2(Bucket="bucket")
    with pytest.raises(operator.ShareCountR2ConformanceError, match="not admitted"):
        capability.delete_object(Bucket="bucket", Key="never")
    with pytest.raises(operator.ShareCountR2ConformanceError, match="not admitted"):
        _ = capability._client
    with pytest.raises(operator.ShareCountR2ConformanceError, match="unadmitted"):
        capability.head_object(Bucket="bucket", Key="other")

    provenance = {
        "repository": "chriswong6031-creator/macro",
        "workflow_ref": "chriswong6031-creator/macro/.github/workflows/capital-share-count-r2-conformance.yml@refs/heads/main",
        "run_id": "1",
        "run_attempt": 1,
        "commit_sha": "a" * 40,
        "event_name": "workflow_dispatch",
        "actor": "operator",
    }
    execution_provenance = {
        "source_archive_sha256": "b" * 64,
        "dependency_lock_sha256": "c" * 64,
    }

    class PassingCore:
        @staticmethod
        def run_conformance(**kwargs):
            assert kwargs["key"] == key
            assert kwargs["endpoint_host"].endswith(".r2.cloudflarestorage.com")
            assert kwargs["github_provenance"] == provenance
            assert kwargs["execution_provenance"] == execution_provenance
            assert kwargs["observed_at"].tzinfo is not None
            assert kwargs["deadline_seconds"] > 0
            return {
                "status": "passed",
                "receipt": {"status": "passed", "checked": "conditional-fresh-key"},
            }

        @staticmethod
        def canonical_receipt_bytes(receipt):
            return json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode("utf-8") + b"\n"

    monkeypatch.setattr(operator, "_load_conformance_core", lambda: PassingCore)
    result = operator.invoke_conformance_core(
        client=capability,
        bucket="bucket",
        key=key,
        endpoint_host="0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
        github_provenance=provenance,
        execution_provenance=execution_provenance,
        observed_at=operator._utc_now(),
        deadline=operator.time.monotonic() + 5,
    )
    assert result["receipt"] == {"status": "passed", "checked": "conditional-fresh-key"}
    assert result["receipt_bytes"] == b'{"checked":"conditional-fresh-key","status":"passed"}\n'

    class FailingCore:
        @staticmethod
        def run_conformance(**_kwargs):
            return {"status": "failed"}

    monkeypatch.setattr(operator, "_load_conformance_core", lambda: FailingCore)
    with pytest.raises(operator.ShareCountR2ConformanceError, match="did not pass"):
        operator.invoke_conformance_core(
            client=capability,
            bucket="bucket",
            key=key,
            endpoint_host="0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com",
            github_provenance=provenance,
            execution_provenance=execution_provenance,
            observed_at=operator._utc_now(),
            deadline=operator.time.monotonic() + 5,
        )


def test_reviewed_core_loads_from_the_minimal_archive_without_package_initializer(tmp_path):
    execution_root = tmp_path / "reviewed"
    script_target = execution_root / "scripts" / SCRIPT_PATH.name
    core_source = ROOT / "engine" / "capital_structure" / "share_count_r2_conformance.py"
    core_target = execution_root / "engine" / "capital_structure" / core_source.name
    script_target.parent.mkdir(parents=True)
    core_target.parent.mkdir(parents=True)
    shutil.copy2(SCRIPT_PATH, script_target)
    shutil.copy2(core_source, core_target)
    (core_target.parent / "__init__.py").write_text(
        "raise RuntimeError('broad package initializer must not run')\n",
        encoding="utf-8",
    )

    spec = importlib.util.spec_from_file_location("_isolated_r2_operator", script_target)
    assert spec and spec.loader
    isolated = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = isolated
    spec.loader.exec_module(isolated)
    previous_core = sys.modules.pop(isolated._CORE_MODULE_NAME, None)
    try:
        loaded = isolated._load_conformance_core()
        assert loaded.RECEIPT_SCHEMA == "capital_structure.share_count_r2_conformance_receipt/v1"
    finally:
        sys.modules.pop(isolated._CORE_MODULE_NAME, None)
        if previous_core is not None:
            sys.modules[isolated._CORE_MODULE_NAME] = previous_core


def test_main_writes_a_canonical_failed_local_receipt_when_config_is_unavailable(monkeypatch, tmp_path):
    operator = _operator_module()
    _set_github_env(monkeypatch)
    _set_execution_env(monkeypatch)
    for name in operator._REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("R2_CAPITAL_STRUCTURE_ENDPOINT", "must-not-be-used")
    assert operator.main(["--output-dir", str(tmp_path)]) == 1
    receipt_path = tmp_path / operator.RECEIPT_FILENAME
    body = receipt_path.read_bytes()
    receipt = json.loads(body)
    core = operator._load_conformance_core()
    assert body == core.canonical_receipt_bytes(receipt)
    core.validate_conformance_receipt(receipt)
    assert receipt["status"] == "failed"
    assert receipt["failure"] == {
        "stage": "setup",
        "category": "configuration",
    }
    assert receipt["scope"]["admitted"] is False
    assert receipt["scope"]["endpoint_host"] is None
    assert receipt["scope"]["bucket_sha256"] is None
    assert "must-not-be-used" not in body.decode("utf-8")


def test_main_uses_the_shared_closed_failure_receipt_after_admitted_config(monkeypatch, tmp_path):
    operator = _operator_module()
    _set_dedicated_env(monkeypatch)
    _set_github_env(monkeypatch)
    _set_execution_env(monkeypatch)

    def unavailable_client(_config):
        raise RuntimeError("do-not-contact-R2-in-test")

    monkeypatch.setattr(operator, "build_sigv4_client", unavailable_client)
    assert operator.main(["--output-dir", str(tmp_path)]) == 1
    receipt_path = tmp_path / operator.RECEIPT_FILENAME
    body = receipt_path.read_bytes()
    receipt = json.loads(body)
    core = operator._load_conformance_core()
    assert body == core.canonical_receipt_bytes(receipt)
    core.validate_conformance_receipt(receipt)
    assert receipt["status"] == "failed"
    assert receipt["failure"] == {"stage": "setup", "category": "configuration"}


def test_main_preserves_core_stage_and_completed_prefix_in_failure_receipt(monkeypatch, tmp_path):
    operator = _operator_module()
    _set_dedicated_env(monkeypatch)
    _set_github_env(monkeypatch)
    _set_execution_env(monkeypatch)

    class Body:
        def __init__(self, value):
            self.value = value
            self.done = False

        def read(self, _size):
            if self.done:
                return b""
            self.done = True
            return self.value

        def close(self):
            return None

    class MalformedReadback:
        body = None
        etag = '"etag-a"'

        @staticmethod
        def _response(status, **extra):
            return {"ResponseMetadata": {"HTTPStatusCode": status}, **extra}

        def put_object(self, **kwargs):
            self.body = kwargs["Body"]
            return self._response(200)

        def head_object(self, **_kwargs):
            return self._response(
                200,
                ContentLength=len(self.body),
                ContentType="application/json",
                ETag=self.etag,
            )

        def get_object(self, **_kwargs):
            return self._response(
                206,
                ContentLength=len(self.body),
                ContentType="application/json",
                ContentRange="bytes 0-0/1",
                ETag=self.etag,
                Body=Body(self.body),
            )

    monkeypatch.setattr(operator, "build_sigv4_client", lambda _config: MalformedReadback())
    assert operator.main(["--output-dir", str(tmp_path)]) == 1
    receipt = json.loads((tmp_path / operator.RECEIPT_FILENAME).read_bytes())
    core = operator._load_conformance_core()
    core.validate_conformance_receipt(receipt)
    assert receipt["status"] == "inconclusive"
    assert receipt["failure"] == {"stage": "get_a", "category": "malformed_response"}
    assert receipt["steps"] == {"completed_steps": ["create_a", "head_a"]}
