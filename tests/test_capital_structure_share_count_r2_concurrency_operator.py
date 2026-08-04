"""Static and capability-boundary checks for the manual concurrency wrapper."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import time

from botocore.awsrequest import AWSResponse
from botocore.exceptions import ClientError
import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = ROOT / "scripts" / "probe_capital_structure_share_count_r2_concurrency.py"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "capital-share-count-r2-concurrency.yml"
SCHEMA_PATH = ROOT / "contracts" / "capital_structure_share_count_r2_concurrency_receipt.schema.json"


def _operator_module():
    spec = importlib.util.spec_from_file_location("_share_count_r2_concurrency_operator_test", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _workflow() -> dict:
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    if True in parsed:
        parsed["on"] = parsed.pop(True)
    return parsed


def test_workflow_is_manual_main_only_and_reuses_the_protected_conformance_mutex() -> None:
    workflow = _workflow()
    assert set(workflow["on"]) == {"workflow_dispatch"}
    assert workflow["on"]["workflow_dispatch"]["inputs"]["run_concurrency"]["type"] == "boolean"
    assert workflow["permissions"] == {"contents": "read"}
    assert workflow["concurrency"] == {"group": "capital-share-count-r2-conformance", "cancel-in-progress": False}
    job = workflow["jobs"]["concurrency"]
    assert job["if"] == "${{ inputs.run_concurrency == true && github.ref == 'refs/heads/main' }}"
    assert job["environment"] == "capital-share-count-r2-conformance"
    assert job["runs-on"] == ["self-hosted", "macstudio-light"]
    assert job["timeout-minutes"] == 5
    probe = next(item for item in job["steps"] if item.get("name") == "run isolated concurrent-writer witness")
    assert set(probe["env"]) == {
        "R2_SHARE_COUNT_CONFORMANCE_ENDPOINT", "R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID",
        "R2_SHARE_COUNT_CONFORMANCE_BUCKET", "R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID",
        "R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY",
        "CAPITAL_STRUCTURE_R2_CONCURRENCY_SOURCE_ARCHIVE_SHA256",
        "CAPITAL_STRUCTURE_R2_CONCURRENCY_DEPENDENCY_LOCK_SHA256",
    }
    rendered = WORKFLOW_PATH.read_text(encoding="utf-8")
    for forbidden in ("schedule:", "push:", "workflow_call:", "contents: write", "git push", "R2_SHARE_COUNT_CONCURRENCY_"):
        assert forbidden not in rendered
    for required in ("test ! -e \"$SOURCE_ARCHIVE\"", "git archive", "archive_sha256", "test -d \"$EXEC_ROOT\"", "capital-share-r2-conformance-macos-arm64-py312.lock"):
        assert required in rendered


def test_wrapper_uses_spawn_persistent_pipes_distinct_sessions_and_exact_event_hooks() -> None:
    rendered = SCRIPT_PATH.read_text(encoding="utf-8")
    for required in (
        'multiprocessing.get_context("spawn")', "Pipe(duplex=False)",
        'register_first("before-send.s3.PutObject"', 'register_last("needs-retry.s3.PutObject"',
        'boto3.session.Session()', '"retries": {"mode": "standard", "total_max_attempts": 1}',
        "R2ConcurrencyInFlight", "process.kill()", "Metadata={\"sha256\": sha256(command[\"body\"]).hexdigest()}",
        'os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID", None)',
        'os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY", None)',
    ):
        assert required in rendered
    assert rendered.index('os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY", None)') < rendered.index("PersistentWorkerPair(config=config")
    assert "list_objects" not in rendered and "delete_object" not in rendered


def test_config_capability_and_contract_are_closed(monkeypatch) -> None:
    operator = _operator_module()
    for name in operator._REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(operator.ShareCountR2ConcurrencyError):
        operator.read_concurrency_config()
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_ENDPOINT", "https://0123456789abcdef0123456789abcdef.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID", "0123456789abcdef0123456789abcdef")
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_BUCKET", "share-count-concurrency")
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID", "A" * 32)
    monkeypatch.setenv("R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY", "B" * 48)
    config = operator.read_concurrency_config()

    class Backing:
        def put_object(self, **kwargs): return kwargs
        def head_object(self, **kwargs): return kwargs
        def get_object(self, **kwargs): return kwargs

    key = "capital_structure/share_counts/concurrency-witness/v1/" + "a" * 32 + "/round-1.json"
    client = operator.ConcurrencyR2ObjectClient(Backing(), bucket=config.bucket, keys=frozenset({key}))
    assert client.put_object(Bucket=config.bucket, Key=key, Body=b"x", ContentType="application/json", Metadata={"sha256": "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881"}, IfNoneMatch="*")["Key"] == key
    with pytest.raises(operator.ShareCountR2ConcurrencyError):
        client.put_object(Bucket=config.bucket, Key=key, Body=b"x", ContentType="application/json", Metadata={}, IfNoneMatch="*")
    with pytest.raises(operator.ShareCountR2ConcurrencyError):
        client.delete_object(Bucket=config.bucket, Key=key)
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["$defs"]["stale"]["additionalProperties"] is False
    assert schema["$defs"]["topology"]["additionalProperties"] is False
    assert schema["$defs"]["outputAuthority"]["additionalProperties"] is False


class _RawResponse:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def stream(self, amt=None, decode_content=False):
        del amt, decode_content
        if self._body:
            yield self._body


class _FakeHTTPSession:
    def __init__(self, *, status: int, headers: dict[str, str], body: bytes) -> None:
        self._status = status
        self._headers = headers
        self._body = body
        self.calls = 0

    def send(self, request):
        self.calls += 1
        return AWSResponse(request.url, self._status, self._headers, _RawResponse(self._body))


def _sdk_config(operator):
    return operator.ConcurrencyR2Config(
        endpoint="https://" + "0" * 32 + ".r2.cloudflarestorage.com",
        account_id="0" * 32,
        bucket="concurrency-witness",
        access_key_id="A" * 32,
        secret_access_key="B" * 48,
    )


@pytest.mark.parametrize(
    ("status", "headers", "body", "expected_error"),
    [
        (200, {"etag": '"test"', "content-length": "0", "x-amz-request-id": "rid"}, b"", None),
        (
            412,
            {
                "content-type": "application/xml",
                "content-length": str(len(b"<Error><Code>PreconditionFailed</Code><Message>x</Message></Error>")),
                "x-amz-request-id": "rid",
            },
            b"<Error><Code>PreconditionFailed</Code><Message>x</Message></Error>",
            "PreconditionFailed",
        ),
    ],
)
def test_exact_botocore_put_attempt_instrumentation_is_one_shot(
    status: int,
    headers: dict[str, str],
    body: bytes,
    expected_error: str | None,
) -> None:
    operator = _operator_module()
    raw_client = operator.build_sigv4_client(_sdk_config(operator))
    fake_http = _FakeHTTPSession(status=status, headers=headers, body=body)
    raw_client._endpoint.http_session = fake_http
    instrument = operator._PutInstrumentation(raw_client, label=f"test-{status}")
    kwargs = {
        "Bucket": "concurrency-witness",
        "Key": "capital_structure/share_counts/concurrency-witness/v1/" + "a" * 32 + "/round-1.json",
        "Body": b"{}",
        "ContentType": "application/json",
        "Metadata": {"sha256": "test"},
        "IfNoneMatch": "*",
    }
    if expected_error is None:
        response = raw_client.put_object(**kwargs)
        assert response["ResponseMetadata"]["RetryAttempts"] == 0
    else:
        with pytest.raises(ClientError) as raised:
            raw_client.put_object(**kwargs)
        assert type(raised.value) is ClientError
        assert raised.value.response["Error"]["Code"] == expected_error
        assert raised.value.response["ResponseMetadata"]["HTTPStatusCode"] == 412
        assert raised.value.response["ResponseMetadata"]["RetryAttempts"] == 0
    assert raw_client.meta.config.retries == {"mode": "standard", "total_max_attempts": 1}
    assert fake_http.calls == 1
    assert len(instrument.before_send_ns) == 1
    assert instrument.needs_retry_attempts == [1]


def test_spawn_pair_reports_isolated_clients_without_network() -> None:
    program = r'''
import json
import time
from scripts import probe_capital_structure_share_count_r2_concurrency as op

core = op._load_concurrency_core()
config = op.ConcurrencyR2Config(
    endpoint="https://" + "0" * 32 + ".r2.cloudflarestorage.com",
    account_id="0" * 32,
    bucket="concurrency-witness",
    access_key_id="A" * 32,
    secret_access_key="B" * 48,
)
keys = tuple(item.key for item in core.build_precommitted_plan(run_nonce="a" * 32))
pair = op.PersistentWorkerPair(config=config, keys=keys, core=core, deadline=time.monotonic() + 15)
try:
    identities = pair.identities
    print(json.dumps({
        "pids": [item.process_id for item in identities],
        "sessions": [item.session_instance_sha256 for item in identities],
        "clients": [item.client_instance_sha256 for item in identities],
        "modes": [item.retry_mode for item in identities],
        "max_attempts": [item.total_max_attempts for item in identities],
        "hooks": [[item.before_send_hook_installed, item.needs_retry_hook_installed] for item in identities],
        "in_flight": pair.may_be_in_flight,
    }, sort_keys=True))
finally:
    pair.close()
'''
    result = subprocess.run(
        [sys.executable, "-c", program],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=25,
        check=True,
    )
    observed = json.loads(result.stdout)
    assert len(set(observed["pids"])) == 2
    assert len(set(observed["sessions"])) == 2
    assert len(set(observed["clients"])) == 2
    assert observed["modes"] == ["standard", "standard"]
    assert observed["max_attempts"] == [1, 1]
    assert observed["hooks"] == [[True, True], [True, True]]
    assert observed["in_flight"] is False


def test_worker_receive_uses_the_stricter_core_deadline(monkeypatch) -> None:
    operator = _operator_module()

    class Connection:
        remaining: float | None = None

        def poll(self, remaining: float) -> bool:
            self.remaining = remaining
            return True

        def recv(self) -> dict[str, bool]:
            return {"received": True}

    pair = object.__new__(operator.PersistentWorkerPair)
    pair._deadline = 100.0
    connection = Connection()
    monkeypatch.setattr(time, "monotonic", lambda: 90.0)
    assert pair._receive(connection, in_flight=False, deadline=95.0) == {"received": True}
    assert connection.remaining == 5.0
