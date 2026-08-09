"""Run the manual-only, disposable R2 concurrent-writer witness.

This is a deliberately small operator boundary.  It starts two persistent
``spawn`` children, each with a distinct boto session/client, and gives the
reviewed core only HEAD/GET/conditional-PUT capability over eight fresh keys.
It never lists, deletes, publishes, signs, or writes a receipt to R2.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import importlib.util
import multiprocessing
import os
from pathlib import Path
import re
import secrets
import signal
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence
from urllib.parse import urlsplit


RECEIPT_FILENAME = "capital_structure_share_count_r2_concurrency_receipt.json"
CLI_DEADLINE_SECONDS = 240
PROCESS_ALARM_SECONDS = 245
MAX_RECEIPT_BYTES = 256 * 1024
_RELEASE_LEAD_NS = 100_000_000
_ACCOUNT_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_ACCESS_KEY_RE = re.compile(r"^[A-Za-z0-9]{16,128}$")
_BUCKET_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$")
_R2_HOST_RE = re.compile(r"^(?P<account_id>[a-f0-9]{32})\.(?:(?:eu|fedramp)\.)?r2\.cloudflarestorage\.com$")
_RANGE_RE = re.compile(r"^bytes=0-(?P<end>[0-9]{1,4})$")
_HEX64_RE = re.compile(r"^[a-f0-9]{64}$")
_GITHUB_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
_GITHUB_ACTOR_RE = re.compile(r"^[A-Za-z0-9-]{1,39}$")
_EXPECTED_REPOSITORY = "mastermindx-market-intelligence/macro"
_WORKFLOW_NAME = "capital-share-count-r2-concurrency.yml"
_REQUIRED_ENV = (
    "R2_SHARE_COUNT_CONFORMANCE_ENDPOINT",
    "R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID",
    "R2_SHARE_COUNT_CONFORMANCE_BUCKET",
    "R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID",
    "R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY",
)
_EXECUTION_ENV = (
    "CAPITAL_STRUCTURE_R2_CONCURRENCY_SOURCE_ARCHIVE_SHA256",
    "CAPITAL_STRUCTURE_R2_CONCURRENCY_DEPENDENCY_LOCK_SHA256",
)
_CORE_MODULE_NAME = "_capital_structure_share_count_r2_concurrency_reviewed"
_CORE_PATH = Path(__file__).resolve().parents[1] / "engine" / "capital_structure" / "share_count_r2_concurrency.py"


class ShareCountR2ConcurrencyError(RuntimeError):
    """The isolated concurrent-writer witness cannot safely proceed."""


class ConcurrencyDeadlineExceeded(ShareCountR2ConcurrencyError):
    workers_may_be_in_flight = True


@dataclass(frozen=True)
class ConcurrencyR2Config:
    endpoint: str
    account_id: str
    bucket: str
    access_key_id: str
    secret_access_key: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_text(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _canonical_endpoint(*, endpoint: str, account_id: str) -> str:
    if not isinstance(account_id, str) or _ACCOUNT_ID_RE.fullmatch(account_id) is None:
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 account ID is invalid")
    if not isinstance(endpoint, str) or len(endpoint) > 256:
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 endpoint is invalid")
    try:
        parsed, port = urlsplit(endpoint), urlsplit(endpoint).port
    except ValueError as exc:
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 endpoint is invalid") from exc
    host = parsed.hostname
    if (
        parsed.scheme != "https" or parsed.username is not None or parsed.password is not None
        or port is not None or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
        or host is None or endpoint not in {f"https://{host}", f"https://{host}/"}
    ):
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 endpoint is invalid")
    match = _R2_HOST_RE.fullmatch(host)
    if match is None or match.group("account_id") != account_id:
        raise ShareCountR2ConcurrencyError("dedicated concurrency endpoint does not bind account ID")
    return f"https://{host}"


def read_concurrency_config() -> ConcurrencyR2Config:
    values = {name: os.environ.get(name, "") for name in _REQUIRED_ENV}
    if any(not values[name] for name in _REQUIRED_ENV):
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 credential is unavailable")
    endpoint = _canonical_endpoint(
        endpoint=values["R2_SHARE_COUNT_CONFORMANCE_ENDPOINT"],
        account_id=values["R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID"],
    )
    bucket = values["R2_SHARE_COUNT_CONFORMANCE_BUCKET"]
    if _BUCKET_RE.fullmatch(bucket) is None or ".." in bucket:
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 bucket is invalid")
    access = values["R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID"]
    secret = values["R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY"]
    if _ACCESS_KEY_RE.fullmatch(access) is None or not secret or len(secret.encode("utf-8")) > 512 or any(c.isspace() for c in secret):
        raise ShareCountR2ConcurrencyError("dedicated concurrency R2 credentials are invalid")
    return ConcurrencyR2Config(endpoint, values["R2_SHARE_COUNT_CONFORMANCE_ACCOUNT_ID"], bucket, access, secret)


def _config_wire(config: ConcurrencyR2Config) -> dict[str, str]:
    return {"endpoint": config.endpoint, "account_id": config.account_id, "bucket": config.bucket, "access_key_id": config.access_key_id, "secret_access_key": config.secret_access_key}


def _config_from_wire(value: Mapping[str, Any]) -> ConcurrencyR2Config:
    if not isinstance(value, Mapping) or set(value) != {"endpoint", "account_id", "bucket", "access_key_id", "secret_access_key"} or not all(isinstance(item, str) for item in value.values()):
        raise ShareCountR2ConcurrencyError("worker concurrency configuration is invalid")
    return ConcurrencyR2Config(**dict(value))


def build_sigv4_client(config: ConcurrencyR2Config, *, session: Any | None = None) -> Any:
    """Create one standard/no-retry S3 client from exactly one boto session."""
    try:
        import boto3
        from botocore.config import Config
    except ImportError as exc:
        raise ShareCountR2ConcurrencyError("boto3 is unavailable for concurrency witness") from exc
    boto_session = session if session is not None else boto3.session.Session()
    options = {"region_name": "auto", "signature_version": "s3v4", "max_pool_connections": 1, "retries": {"mode": "standard", "total_max_attempts": 1}, "connect_timeout": 5, "read_timeout": 15}
    try:
        client_config = Config(**options, request_checksum_calculation="when_required", response_checksum_validation="when_required")
    except TypeError:
        client_config = Config(**options)
    client = boto_session.client("s3", endpoint_url=config.endpoint, aws_access_key_id=config.access_key_id, aws_secret_access_key=config.secret_access_key, config=client_config)
    _preflight_r2_sdk_models(client)
    return client


def _preflight_r2_sdk_models(client: Any) -> None:
    try:
        model = client.meta.service_model
        put = model.operation_model("PutObject").input_shape.members
        get = model.operation_model("GetObject").input_shape.members
        head = model.operation_model("HeadObject").input_shape.members
    except Exception as exc:
        raise ShareCountR2ConcurrencyError("boto3 SDK cannot preflight concurrency operations") from exc
    if not {"IfMatch", "IfNoneMatch", "Metadata"}.issubset(put) or "IfMatch" not in get or not {"Bucket", "Key"}.issubset(head):
        raise ShareCountR2ConcurrencyError("boto3 SDK lacks concurrency conditional operations")


class ConcurrencyR2ObjectClient:
    """The only remote capability: three methods over an exact fresh-key set."""
    __slots__ = ("__client", "_bucket", "_keys")

    def __init__(self, client: Any, *, bucket: str, keys: frozenset[str]) -> None:
        if not keys:
            raise ShareCountR2ConcurrencyError("concurrency key capability is empty")
        self.__client, self._bucket, self._keys = client, bucket, keys

    def _target(self, kwargs: Mapping[str, Any]) -> None:
        if kwargs.get("Bucket") != self._bucket or kwargs.get("Key") not in self._keys:
            raise ShareCountR2ConcurrencyError("concurrency operation attempted an unadmitted R2 target")

    @staticmethod
    def _condition(value: Any) -> None:
        if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 1024 or any(ord(c) < 32 or ord(c) == 127 for c in value):
            raise ShareCountR2ConcurrencyError("concurrency condition is invalid")

    def head_object(self, **kwargs: Any) -> Any:
        self._target(kwargs)
        if set(kwargs) != {"Bucket", "Key"}:
            raise ShareCountR2ConcurrencyError("concurrency HEAD parameters are not admitted")
        return self.__client.head_object(**kwargs)

    def get_object(self, **kwargs: Any) -> Any:
        self._target(kwargs)
        match = _RANGE_RE.fullmatch(kwargs.get("Range", ""))
        if set(kwargs) != {"Bucket", "Key", "Range", "IfMatch"} or match is None or int(match.group("end")) >= 4096:
            raise ShareCountR2ConcurrencyError("concurrency GET parameters are not admitted")
        self._condition(kwargs["IfMatch"])
        return self.__client.get_object(**kwargs)

    def put_object(self, **kwargs: Any) -> Any:
        self._target(kwargs)
        base = {"Bucket", "Key", "Body", "ContentType", "Metadata"}
        conditions = {name for name in ("IfMatch", "IfNoneMatch") if name in kwargs}
        body = kwargs.get("Body")
        metadata = kwargs.get("Metadata")
        if set(kwargs) != base | conditions or len(conditions) != 1 or not isinstance(body, bytes) or not 1 <= len(body) <= 4096 or kwargs.get("ContentType") != "application/json" or metadata != {"sha256": sha256(body).hexdigest()}:
            raise ShareCountR2ConcurrencyError("concurrency PUT parameters are not admitted")
        if "IfNoneMatch" in conditions:
            if kwargs["IfNoneMatch"] != "*":
                raise ShareCountR2ConcurrencyError("concurrency IfNoneMatch condition is invalid")
        else:
            self._condition(kwargs["IfMatch"])
        return self.__client.put_object(**kwargs)

    def __getattr__(self, name: str) -> Any:
        raise ShareCountR2ConcurrencyError(f"concurrency client capability is not admitted: {name}")


class _PutInstrumentation:
    def __init__(self, client: Any, *, label: str) -> None:
        self.before_send_ns: list[int] = []
        self.needs_retry_attempts: list[int] = []
        self._client = client
        self._client.meta.events.register_first("before-send.s3.PutObject", self._before_send, unique_id=f"capital-share-r2-concurrency-before-{label}")
        self._client.meta.events.register_last("needs-retry.s3.PutObject", self._needs_retry, unique_id=f"capital-share-r2-concurrency-retry-{label}")

    def reset(self) -> None:
        self.before_send_ns.clear()
        self.needs_retry_attempts.clear()

    def _before_send(self, **_kwargs: Any) -> None:
        self.before_send_ns.append(time.monotonic_ns())
        return None

    def _needs_retry(self, **kwargs: Any) -> None:
        attempt = kwargs.get("attempts")
        self.needs_retry_attempts.append(attempt if isinstance(attempt, int) and not isinstance(attempt, bool) else -1)
        return None


def _metadata_retry(response: Any) -> int | None:
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    value = metadata.get("RetryAttempts") if isinstance(metadata, Mapping) else None
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _request_id_hash(response: Any) -> str | None:
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    request_id = metadata.get("RequestId") if isinstance(metadata, Mapping) else None
    return _hash_text(request_id) if isinstance(request_id, str) and request_id else None


def _client_error_details(error: BaseException) -> tuple[str | None, int | None, int | None, str | None]:
    response = getattr(error, "response", None)
    details = response.get("Error") if isinstance(response, Mapping) else None
    metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
    code = details.get("Code") if isinstance(details, Mapping) else None
    status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
    retries = metadata.get("RetryAttempts") if isinstance(metadata, Mapping) else None
    return (code if isinstance(code, str) else None, status if isinstance(status, int) and not isinstance(status, bool) else None, retries if isinstance(retries, int) and not isinstance(retries, bool) else None, _request_id_hash(response))


def _wait_until(release_at_ns: int) -> None:
    while time.monotonic_ns() < release_at_ns:
        time.sleep(0.001)


def _worker_main(worker_id: str, config_wire: Mapping[str, Any], keys: tuple[str, ...], command_recv: Any, result_send: Any) -> None:
    """Spawn-only child target. It owns exactly one session and one S3 client."""
    try:
        import boto3
        from botocore.exceptions import ClientError
        config = _config_from_wire(config_wire)
        session = boto3.session.Session()
        raw_client = build_sigv4_client(config, session=session)
        instrument = _PutInstrumentation(raw_client, label=worker_id)
        client = ConcurrencyR2ObjectClient(raw_client, bucket=config.bucket, keys=frozenset(keys))
        retry_config = getattr(getattr(raw_client, "meta", None), "config", None)
        retry_values = getattr(retry_config, "retries", None)
        retry_mode = retry_values.get("mode") if isinstance(retry_values, Mapping) else None
        total_max_attempts = retry_values.get("total_max_attempts") if isinstance(retry_values, Mapping) else None
        result_send.send({"kind": "identity", "worker_id": worker_id, "process_id": os.getpid(), "session_instance_sha256": _hash_text(f"{os.getpid()}:{id(session)}"), "client_instance_sha256": _hash_text(f"{os.getpid()}:{id(raw_client)}"), "retry_mode": retry_mode, "total_max_attempts": total_max_attempts, "before_send_hook_installed": True, "needs_retry_hook_installed": True})
    except Exception:
        result_send.send({"kind": "startup_error"})
        return
    while True:
        try:
            command = command_recv.recv()
        except EOFError:
            return
        if not isinstance(command, Mapping) or command.get("kind") == "stop":
            result_send.send({"kind": "stopped"})
            return
        if set(command) != {"kind", "round_id", "phase", "key", "body", "condition_name", "condition_value", "round_token", "release_at_ns"} or command.get("kind") != "race" or command.get("key") not in keys or command.get("condition_name") not in {"IfMatch", "IfNoneMatch"} or not isinstance(command.get("body"), bytes) or not isinstance(command.get("round_token"), str):
            result_send.send({"kind": "worker_error"})
            return
        instrument.reset()
        issued = 0
        started_ns: int | None = None
        completed_ns: int | None = None
        http_status: int | None = None
        error_code: str | None = None
        error_status: int | None = None
        retries: int | None = None
        request_hash: str | None = None
        exact_error = False
        outcome = "unknown"
        try:
            release_at_ns = command["release_at_ns"]
            if isinstance(release_at_ns, bool) or not isinstance(release_at_ns, int):
                raise ShareCountR2ConcurrencyError("worker release time is invalid")
            _wait_until(release_at_ns)
            issued = 1
            response = client.put_object(Bucket=config.bucket, Key=command["key"], Body=command["body"], ContentType="application/json", Metadata={"sha256": sha256(command["body"]).hexdigest()}, **{command["condition_name"]: command["condition_value"]})
            completed_ns = time.monotonic_ns()
            metadata = response.get("ResponseMetadata") if isinstance(response, Mapping) else None
            raw_status = metadata.get("HTTPStatusCode") if isinstance(metadata, Mapping) else None
            http_status = raw_status if isinstance(raw_status, int) and not isinstance(raw_status, bool) else None
            retries, request_hash = _metadata_retry(response), _request_id_hash(response)
            outcome = "success" if http_status == 200 else "unknown"
        except ClientError as exc:
            completed_ns = time.monotonic_ns()
            error_code, error_status, retries, request_hash = _client_error_details(exc)
            exact_error = type(exc) is ClientError
            outcome = "conflict" if exact_error and error_code == "PreconditionFailed" and error_status == 412 else "error"
        except Exception:
            completed_ns = time.monotonic_ns()
            outcome = "transport"
        started_ns = instrument.before_send_ns[0] if len(instrument.before_send_ns) == 1 else None
        result_send.send({"kind": "race", "worker_id": worker_id, "round_id": command["round_id"], "phase": command["phase"], "round_token": command["round_token"], "attempt": {"worker_id": worker_id, "process_id": os.getpid(), "issued_puts": issued, "before_send_count": len(instrument.before_send_ns), "needs_retry_attempts": tuple(instrument.needs_retry_attempts), "transport_started_ns": started_ns, "completed_ns": completed_ns, "http_status": http_status, "error_code": error_code, "error_status": error_status, "retry_attempts": retries, "exact_client_error": exact_error, "request_id_sha256": request_hash, "outcome": outcome}})


class InstrumentedVerifier:
    def __init__(self, client: ConcurrencyR2ObjectClient, raw_client: Any, *, core: Any) -> None:
        self._client, self._instrument, self._core = client, _PutInstrumentation(raw_client, label="verifier"), core
        self._issued = 0
        self._retry_attempts: int | None = None
        self._exact_client_error = False
        self._request_id_sha256: str | None = None

    def head_object(self, **kwargs: Any) -> Any:
        return self._client.head_object(**kwargs)

    def get_object(self, **kwargs: Any) -> Any:
        return self._client.get_object(**kwargs)

    def put_object(self, **kwargs: Any) -> Any:
        self._issued += 1
        try:
            return self._client.put_object(**kwargs)
        except Exception as exc:
            response = getattr(exc, "response", None)
            self._retry_attempts = _metadata_retry(response)
            self._request_id_sha256 = _request_id_hash(response)
            try:
                from botocore.exceptions import ClientError
                self._exact_client_error = type(exc) is ClientError
            except ImportError:
                self._exact_client_error = False
            raise

    def reset_put_attempt_evidence(self) -> None:
        self._instrument.reset()
        self._issued = 0
        self._retry_attempts = None
        self._exact_client_error = False
        self._request_id_sha256 = None

    def take_put_attempt_evidence(self) -> Any:
        # The core has already classified the typed ClientError. No exception
        # object is carried into the receipt; only reviewed scalar evidence is.
        return self._core.VerifierPutAttempt(issued_puts=self._issued, before_send_count=len(self._instrument.before_send_ns), needs_retry_attempts=tuple(self._instrument.needs_retry_attempts), retry_attempts=self._retry_attempts, exact_client_error=self._exact_client_error, request_id_sha256=self._request_id_sha256)


class PersistentWorkerPair:
    """Two long-lived spawned children; a missing response is an in-flight stop."""
    def __init__(self, *, config: ConcurrencyR2Config, keys: Sequence[str], core: Any, deadline: float) -> None:
        self._context = multiprocessing.get_context("spawn")
        self._core, self._deadline, self._pairs = core, deadline, []
        self._in_flight = False
        identities: list[Any] = []
        for worker_id in ("left", "right"):
            command_recv, command_send = self._context.Pipe(duplex=False)
            result_recv, result_send = self._context.Pipe(duplex=False)
            process = self._context.Process(target=_worker_main, args=(worker_id, _config_wire(config), tuple(keys), command_recv, result_send), daemon=True)
            process.start()
            command_recv.close(); result_send.close()
            self._pairs.append((worker_id, process, command_send, result_recv))
        try:
            for worker_id, _process, _command_send, result_recv in self._pairs:
                payload = self._receive(result_recv, in_flight=False)
                if not isinstance(payload, Mapping) or payload.get("kind") != "identity" or payload.get("worker_id") != worker_id:
                    raise ShareCountR2ConcurrencyError("spawned worker identity is unavailable")
                identity = dict(payload); identity.pop("kind", None)
                identities.append(core.WorkerIdentity(**identity))
        except Exception:
            self._terminate_all()
            raise
        self._identities = tuple(identities)

    @property
    def identities(self) -> tuple[Any, Any]:
        return self._identities

    @property
    def may_be_in_flight(self) -> bool:
        return self._in_flight

    def _receive(self, connection: Any, *, in_flight: bool, deadline: float | None = None) -> Any:
        effective_deadline = self._deadline if deadline is None else min(self._deadline, deadline)
        remaining = effective_deadline - time.monotonic()
        if remaining <= 0 or not connection.poll(remaining):
            if in_flight:
                self._abort_inflight()
                raise self._core.R2ConcurrencyInFlight("concurrent worker response timed out")
            raise ShareCountR2ConcurrencyError("spawned worker startup timed out")
        return connection.recv()

    def race(self, *, round_id: int, phase: str, key: str, left_body: bytes, right_body: bytes, condition_name: str, condition_value: str, deadline: float) -> tuple[Any, Any]:
        if self._in_flight:
            raise self._core.R2ConcurrencyInFlight("concurrent worker state is not safe")
        effective_deadline = min(self._deadline, deadline)
        if time.monotonic() + (_RELEASE_LEAD_NS / 1_000_000_000) >= effective_deadline:
            raise self._core.R2ConcurrencyInconclusive("concurrent race lacks release-time budget")
        token = secrets.token_hex(16)
        release_at_ns = time.monotonic_ns() + _RELEASE_LEAD_NS
        self._in_flight = True
        try:
            for worker_id, _process, command_send, _result_recv in self._pairs:
                body = left_body if worker_id == "left" else right_body
                command_send.send({"kind": "race", "round_id": round_id, "phase": phase, "key": key, "body": body, "condition_name": condition_name, "condition_value": condition_value, "round_token": token, "release_at_ns": release_at_ns})
            raw_results: list[Mapping[str, Any]] = []
            for worker_id, _process, _command_send, result_recv in self._pairs:
                payload = self._receive(result_recv, in_flight=True, deadline=effective_deadline)
                if not isinstance(payload, Mapping) or payload.get("kind") != "race" or payload.get("worker_id") != worker_id or payload.get("round_id") != round_id or payload.get("phase") != phase or payload.get("round_token") != token:
                    self._abort_inflight()
                    raise self._core.R2ConcurrencyInFlight("worker returned stale or malformed race result")
                raw_results.append(payload)
            self._in_flight = False
            return tuple(self._core.WorkerAttempt(**item["attempt"]) for item in raw_results)  # type: ignore[return-value]
        except self._core.R2ConcurrencyInFlight:
            raise
        except Exception as exc:
            self._abort_inflight()
            raise self._core.R2ConcurrencyInFlight("concurrent worker transport failed") from exc

    def _terminate_all(self) -> None:
        for _worker_id, process, command_send, result_recv in self._pairs:
            try: command_send.close()
            except Exception: pass
            try: result_recv.close()
            except Exception: pass
            if process.is_alive(): process.terminate()
            process.join(timeout=1)
            if process.is_alive():
                process.kill()
                process.join(timeout=1)

    def _abort_inflight(self) -> None:
        self._in_flight = True
        self._terminate_all()

    def close(self) -> None:
        if self._in_flight:
            self._abort_inflight()
            return
        for _worker_id, _process, command_send, _result_recv in self._pairs:
            try: command_send.send({"kind": "stop"})
            except Exception: pass
        self._terminate_all()


def github_provenance_from_environment() -> dict[str, Any]:
    values = {"repository": os.environ.get("GITHUB_REPOSITORY", ""), "workflow_ref": os.environ.get("GITHUB_WORKFLOW_REF", ""), "run_id": os.environ.get("GITHUB_RUN_ID", ""), "run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT", ""), "commit_sha": os.environ.get("GITHUB_SHA", ""), "event_name": os.environ.get("GITHUB_EVENT_NAME", ""), "actor": os.environ.get("GITHUB_ACTOR", "")}
    expected_ref = f"{_EXPECTED_REPOSITORY}/.github/workflows/{_WORKFLOW_NAME}@refs/heads/main"
    if values["repository"] != _EXPECTED_REPOSITORY or values["workflow_ref"] != expected_ref or _GITHUB_SHA_RE.fullmatch(values["commit_sha"]) is None or values["event_name"] != "workflow_dispatch" or _GITHUB_ACTOR_RE.fullmatch(values["actor"]) is None or not values["run_id"].isdigit() or not values["run_attempt"].isdigit() or int(values["run_id"]) <= 0 or int(values["run_attempt"]) <= 0:
        raise ShareCountR2ConcurrencyError("GitHub concurrency provenance is invalid")
    return {**values, "run_attempt": int(values["run_attempt"])}


def execution_provenance_from_environment() -> dict[str, str]:
    values = {name: os.environ.get(name, "") for name in _EXECUTION_ENV}
    if any(_HEX64_RE.fullmatch(value) is None for value in values.values()):
        raise ShareCountR2ConcurrencyError("reviewed concurrency execution provenance is invalid")
    return {"source_archive_sha256": values[_EXECUTION_ENV[0]], "dependency_lock_sha256": values[_EXECUTION_ENV[1]], "dependency_lock_name": "capital-share-r2-conformance-macos-arm64-py312.lock"}


def _load_concurrency_core() -> Any:
    cached = sys.modules.get(_CORE_MODULE_NAME)
    if cached is not None: return cached
    try:
        spec = importlib.util.spec_from_file_location(_CORE_MODULE_NAME, _CORE_PATH)
        if spec is None or spec.loader is None: raise ImportError("reviewed core has no import specification")
        module = importlib.util.module_from_spec(spec); sys.modules[_CORE_MODULE_NAME] = module; spec.loader.exec_module(module)
        return module
    except Exception as exc:
        sys.modules.pop(_CORE_MODULE_NAME, None)
        raise ShareCountR2ConcurrencyError("concurrency core is unavailable") from exc


def write_local_receipt(output_dir: str | Path, receipt: bytes) -> Path:
    destination = Path(output_dir)
    if destination.exists() and destination.is_symlink(): raise ShareCountR2ConcurrencyError("receipt output directory cannot be a symlink")
    destination.mkdir(parents=True, exist_ok=True)
    if not destination.is_dir() or not receipt.endswith(b"\n") or len(receipt) > MAX_RECEIPT_BYTES: raise ShareCountR2ConcurrencyError("canonical concurrency receipt is invalid")
    final = destination / RECEIPT_FILENAME
    descriptor, temporary = tempfile.mkstemp(prefix=".share_count_r2_concurrency_", suffix=".tmp", dir=destination)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(receipt); handle.flush(); os.fsync(handle.fileno())
        os.replace(temporary, final)
    except Exception:
        try: os.unlink(temporary)
        except OSError: pass
        raise
    return final


def _deadline_handler(_signum: int, _frame: Any) -> None:
    raise ConcurrencyDeadlineExceeded("concurrency process watchdog elapsed")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, help="local review-only artifact directory")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    observed_at, phase = _utc_now(), "provenance"
    core: Any | None = None; workers: PersistentWorkerPair | None = None
    config: ConcurrencyR2Config | None = None; endpoint_host: str | None = None
    github: Mapping[str, Any] | None = None; execution: Mapping[str, Any] | None = None
    plan_commitment: str | None = None; timer_armed = False; previous_handler: Any = None
    deadline = time.monotonic() + CLI_DEADLINE_SECONDS
    try:
        if hasattr(signal, "SIGALRM") and hasattr(signal, "setitimer"):
            previous_handler = signal.signal(signal.SIGALRM, _deadline_handler); signal.setitimer(signal.ITIMER_REAL, PROCESS_ALARM_SECONDS); timer_armed = True
        github = github_provenance_from_environment(); phase = "execution_provenance"
        execution = execution_provenance_from_environment(); phase = "configuration"
        config = read_concurrency_config(); endpoint_host = urlsplit(config.endpoint).hostname
        if endpoint_host is None: raise ShareCountR2ConcurrencyError("dedicated concurrency endpoint host is invalid")
        core = _load_concurrency_core()
        rounds = core.build_precommitted_plan(run_nonce=secrets.token_hex(16)); plan_commitment = core.plan_commitment_sha256(rounds)
        phase = "client_initialization"
        parent_client = build_sigv4_client(config)
        # The parent client has captured its credential. Spawned children receive
        # the same reviewed values only through their explicit process arguments;
        # do not also leak them through each child's inherited environment.
        os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_ACCESS_KEY_ID", None)
        os.environ.pop("R2_SHARE_COUNT_CONFORMANCE_SECRET_ACCESS_KEY", None)
        keys = frozenset(item.key for item in rounds)
        verifier = InstrumentedVerifier(ConcurrencyR2ObjectClient(parent_client, bucket=config.bucket, keys=keys), parent_client, core=core)
        workers = PersistentWorkerPair(config=config, keys=tuple(keys), core=core, deadline=deadline)
        phase = "core_concurrency"
        # Preserve one shared budget from wrapper start.  The tiny handoff
        # margin prevents core-start overhead from extending that absolute cap.
        remaining = deadline - time.monotonic() - 0.05
        if remaining <= 0: raise ConcurrencyDeadlineExceeded("concurrency setup exceeded shared logical deadline")
        result = core.run_concurrency_witness(workers=workers, verifier=verifier, bucket=config.bucket, endpoint_host=endpoint_host, rounds=rounds, github_provenance=github, execution_provenance=execution, observed_at=observed_at, deadline_seconds=remaining)
        workers.close(); workers = None
        if not isinstance(result, Mapping) or result.get("status") != "passed" or not isinstance(result.get("receipt"), Mapping): raise ShareCountR2ConcurrencyError("concurrency core did not pass")
        payload = core.canonical_receipt_bytes(result["receipt"])
        phase = "receipt_write"; write_local_receipt(args.output_dir, payload)
    except Exception as exc:
        unsafe = bool(getattr(exc, "workers_may_be_in_flight", False)) or (workers is not None and workers.may_be_in_flight)
        if workers is not None: workers.close()
        if not unsafe:
            try:
                if core is None: core = _load_concurrency_core()
                if github is not None and execution is not None:
                    evidence = core.failure_receipt_evidence(exc) if phase == "core_concurrency" else {"status": "inconclusive", "failure_stage": "setup" if phase in {"provenance", "execution_provenance", "configuration", "client_initialization"} else "probe", "failure_category": "configuration" if phase in {"provenance", "execution_provenance", "configuration", "client_initialization"} else "transport_or_deadline", "completed_rounds": ()}
                    receipt = core.build_failure_receipt(status=evidence["status"], failure_stage=evidence["failure_stage"], failure_category=evidence["failure_category"], bucket=config.bucket if config else None, endpoint_host=endpoint_host, plan_commitment=plan_commitment, github_provenance=github, execution_provenance=execution, observed_at=observed_at, deadline_seconds=CLI_DEADLINE_SECONDS, completed_rounds=evidence["completed_rounds"])
                    write_local_receipt(args.output_dir, core.canonical_receipt_bytes(receipt))
            except Exception: pass
        print(f"::error title=share_count_r2_concurrency::{phase} failed", flush=True)
        return 1
    finally:
        if timer_armed:
            signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, previous_handler)
    print("::notice title=share_count_r2_concurrency::review-only receipt is available as an artifact", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
